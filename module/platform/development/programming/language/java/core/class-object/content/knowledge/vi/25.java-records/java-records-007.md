# Quy tắc về trường đối tượng, kế thừa và hiện thực interface của record trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **record components** trong header với **instance fields** được compiler khai báo ngầm; hiểu `record Point(int x, int y)` đã có đủ hai component fields `private final` và accessors `x()`/`y()`.
- Giải thích vì sao record **không được tự khai báo thêm instance field** hoặc **instance initializer block**, trong khi vẫn có thể khai báo **static fields**, **static initializer blocks**, **static/instance methods** và nested types hợp lệ.
- Phân biệt *instance state thuộc từng record object* với *static state thuộc record class*, và biết static state không tham gia generated `equals`/`hashCode`/`toString`.
- Hiểu record **ngầm final** và trực tiếp kế thừa `java.lang.Record`; không thể ghi `extends SomeClass`, không thể làm superclass cho subclass khác hoặc khai `abstract record`, `sealed record`, `non-sealed record`.
- Hiểu khả năng `implements` một hoặc nhiều interfaces, đặc biệt khi generated component accessor tự đáp ứng method signature của interface.
- Sử dụng `@Override`, generic interfaces, interface default methods, sealed interfaces và record implementations theo quy tắc Java 17.
- Biết khi nào cần tự viết method để hiện thực interface, vì `record User(String name)` **chỉ có accessor `name()`**, không tự tạo `getName()` hoặc `get()`.
- Viết canonical/compact constructors đúng để validate và normalize component values; hiểu constructor không mở quyền khai thêm arbitrary instance state.
- Phân biệt **final component references** với **deep immutability** của nested mutable objects và xử lý bằng immutable component types hoặc defensive copies.
- Tránh nhầm **inheritance của methods từ Object/Record**, **inheritance của default methods từ interfaces** và **class inheritance bị cấm với record**.
- Biết các hạn chế của custom `equals`/`hashCode`, method overriding, interface contracts và Java record reflection/serialization ở mức cần thiết.
- Tự chạy chương trình Java 17+, so stdout, sửa lỗi biên dịch và chọn record hoặc normal class phù hợp với thiết kế domain.

> **Phạm vi:** Đây là bài về **trường đối tượng, kế thừa và hiện thực interface của record**, không phải bài tổng quan mọi tính năng Java record. Các snippets ghi rõ khi không có `main`; chỉ các mục có tên file, lệnh `javac`/`java` và stdout là chương trình hoàn chỉnh độc lập. Java records đã là tính năng chính thức từ Java 16; ví dụ dùng JDK 17 trở lên.

## 1. Record vẫn là class nhưng có giới hạn representation

Record là một dạng class chuyên dùng để mô tả một **nhóm component values có tên**. Ví dụ:

~~~java
record Point(int x, int y) {
}
~~~

Record header `(int x, int y)` cho compiler biết *representation* của Point gồm hai components. Theo JLS `8.10.3`, mỗi component tương ứng với:

- Một **component field** `private final`, **không static**, có cùng tên và kiểu với component.
- Một **public instance accessor** `x()` hoặc `y()`, do compiler khai báo ngầm nếu bạn không tự khai một method hợp lệ.
- Một canonical constructor có parameters tương ứng component list và các methods quản lý state như `equals`, `hashCode`, `toString` theo record semantics.

Nói cách khác, declaration này không “không có fields”; nó có **đúng những instance fields cần thiết do header xác định**. Điểm khác với class thường là bạn không được thêm instance fields ngoài những fields compiler đã khai báo cho components.

Một cách hình dung (để hiểu, **không phải Java source được phép khai cùng lúc**):

~~~java
// Mô phỏng ý tưởng do compiler cung cấp, KHÔNG paste vào record:
private final int x;
private final int y;

public int x() { return x; }
public int y() { return y; }
~~~

Bởi vì components là một phần của public structural contract, record có **representation minh bạch**: người dùng đọc record header là biết tập values được lưu theo record model.

## 2. Chương trình: component fields và accessor là hai khía cạnh khác nhau

Lưu **`RecordComponentAccessDemo.java`**:

~~~java
public class RecordComponentAccessDemo {
    record Point(int x, int y) {
        int sum() {
            return x + y;
        }

        String summary() {
            return "x=" + x() + ",y=" + y();
        }
    }

    public static void main(String[] args) {
        Point point = new Point(3, 4);

        System.out.println(point);
        System.out.println("x()=" + point.x());
        System.out.println("y()=" + point.y());
        System.out.println("sum=" + point.sum());
        System.out.println("summary=" + point.summary());

        // System.out.println(point.x); // Không accessible:
        // component field x là private.
    }
}
~~~

Chạy:

~~~bash
javac RecordComponentAccessDemo.java
java RecordComponentAccessDemo
~~~

**Stdout:**

~~~text
Point[x=3, y=4]
x()=3
y()=4
sum=7
summary=x=3,y=4
~~~

Bên trong record body, method `sum()` có thể đọc field `x`/`y` trực tiếp do cùng class, còn caller dùng `point.x()` hoặc `point.y()`. Java không sinh mặc định JavaBeans-style getters `getX()`/`getY()`.

**Quy tắc:** tên component xác định **tên field riêng tư** và **tên accessor công khai**; component declaration không cho caller sửa field bằng `point.x = 9`.

## 3. Cấm khai báo thêm instance fields trong record body

JLS `8.10.2` quy định: **record body có non-static field declaration là compile-time error**.

~~~java
record Point(int x, int y) {
    // private int z;            // Sai: additional instance field.
    // private final int extra=1; // Vẫn sai dù final.
    // int cache;                 // Sai dù package-private.
}
~~~

Tại sao? Record header phải là **mô tả đầy đủ instance state** mà record công khai là representation. Nếu cho thêm mutable hoặc hidden instance field ngoài header, generated equality, reconstruction và data transparency sẽ khó nhất quán.

### 3.1. Không khai trùng component field

~~~java
record Name(String value) {
    // private final String value; // Sai: compiler đã cung cấp field.
}
~~~

Đừng nhầm “record không được khai field” với “record không có field”. Record **có private final component fields**; chính bạn **không** được thêm non-static fields ở body.

### 3.2. Không lách bằng instance initializer block

~~~java
record Counter(int value) {
    // { System.out.println(value); } // Sai: instance initializer.
}
~~~

Record **không cho** instance initializer `{ ... }` ở body. Để validate/normalize object state, dùng **canonical constructor** (đặc biệt compact form). Static initializer `static { ... }` là chuyện khác và được phép.

### 3.3. Cấm cả `transient`/`volatile` của extra instance fields

Nếu bạn viết một declaration `private transient int cache;` hoặc `private volatile long lastUsed;` trong record body, nó vẫn là một **non-static field declaration**, nên vi phạm quy tắc. Thêm modifier không tạo ngoại lệ.

Nếu thật sự cần cache/transaction mutable state gắn riêng từng instance, hãy cân nhắc **normal class** thay vì ép record phá representation model.

## 4. Dữ liệu dẫn xuất: tính bằng method, không lưu additional instance field

Ví dụ rectangle:

~~~java
record Rectangle(int width, int height) {
    long area() {
        return (long) width * height;
    }
}
~~~

`area()` là instance method **được phép**. Nó không thêm persistent state vào record; kết quả được tính từ hai components.

Không viết:

~~~java
record InvalidRectangle(int width, int height) {
    // private final long area = (long) width * height;
    // Sai: record body không được khai thêm non-static field.
}
~~~

Nếu phép tính rất đắt và cần per-instance cache, record có thể không phải representation phù hợp. Dùng normal immutable class với explicit cache field, hoặc tính trước và đưa dữ liệu cache vào **component** chỉ khi nó thật sự là một phần của representation cần public API và equality.

### 4.1. Chương trình tính dữ liệu dẫn xuất

Lưu **`RecordDerivedStateDemo.java`**:

~~~java
public class RecordDerivedStateDemo {
    record Rectangle(int width, int height) {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }

        long area() {
            return (long) width * height;
        }

        long perimeter() {
            return 2L * (width + (long) height);
        }

        boolean isSquare() {
            return width == height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(4, 3);
        Rectangle b = new Rectangle(5, 5);

        System.out.println("a area=" + a.area());
        System.out.println("a perimeter=" + a.perimeter());
        System.out.println("a square=" + a.isSquare());
        System.out.println("b area=" + b.area());
        System.out.println("b square=" + b.isSquare());
    }
}
~~~

Chạy:

~~~bash
javac RecordDerivedStateDemo.java
java RecordDerivedStateDemo
~~~

Output:

~~~text
a area=12
a perimeter=14
a square=false
b area=25
b square=true
~~~

Dòng tính `area()` và `perimeter()` được gọi khi bạn gọi methods; không có third per-object field `area` bên trong record. Cast sang long giúp tránh overflow của phép toán int trong các trường hợp phổ biến; domain thực vẫn phải xét giới hạn của long nếu số cực lớn.

## 5. Static fields của record **được phép**

Record body có thể khai **static fields**; cấm chỉ áp dụng cho **non-static field declarations ngoài header**.

~~~java
record Point(int x, int y) {
    static final String KIND = "point";
    private static int created;
}
~~~

- `KIND` là static constant cho cả record class.
- `created` là static mutable field dùng chung giữa toàn bộ Point objects.
- Không field nào trong hai static fields này là record component. Chúng **không** xuất hiện trong `toString()` do compiler sinh và không tham gia component equality/hash.
- Static field mutable có thể gây data race/lifecycle vấn đề như ở class bình thường; record **không** làm static state tự động thread-safe.

### 5.1. Static initializer cũng hợp lệ

~~~java
record Status(int code) {
    private static final java.util.Map<Integer, String> LABELS;

    static {
        LABELS = java.util.Map.of(
                200, "OK",
                404, "Not Found");
    }

    String label() {
        return LABELS.get(code);
    }
}
~~~

Đây là static initializer chạy theo class initialization rules, không phải block chạy riêng cho mỗi Status instance. Nếu không cần block, có thể viết `private static final Map<...> LABELS = Map.of(...);`.

**Phân biệt rõ:** **instance initializer** bị cấm; **static initializer** được phép.

## 6. Chương trình: static shared state không đổi record components

Lưu **`RecordStaticFieldDemo.java`**:

~~~java
public class RecordStaticFieldDemo {
    record Ticket(String code) {
        private static int constructed;

        Ticket {
            constructed++;
        }

        static int constructedCount() {
            return constructed;
        }

        String label() {
            return "Ticket-" + code;
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket("A");
        Ticket second = new Ticket("A");

        System.out.println("same values=" + first.equals(second));
        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("count=" + Ticket.constructedCount());
    }
}
~~~

Chạy trong một JVM mới:

~~~bash
javac RecordStaticFieldDemo.java
java RecordStaticFieldDemo
~~~

Output:

~~~text
same values=true
first=Ticket[code=A]
second=Ticket[code=A]
count=2
~~~

`constructed` không thuộc record components, nên hai Tickets có `code="A"` vẫn `equals` true mặc dù đã tăng shared counter. Trong production đa luồng, `constructed++` không atomic; muốn đếm threadsafe nên cân nhắc `AtomicInteger` hoặc synchronization. Không làm side effects trong constructor chỉ vì code ngắn: ví dụ phục vụ phân biệt static vs instance state.

## 7. Static fields và interface constants không đồng nghĩa record instance fields

Một interface có thể khai field:

~~~java
interface Versioned {
    int CURRENT = 1;
}
~~~

Field đó **implicitly public static final** của interface. Khi record implement Versioned, nó không nhận một **per-record instance field** `CURRENT`. Truy cập rõ nhất là `Versioned.CURRENT`.

Tương tự, static fields của record là shared members của **record class**, không được “clone” theo mỗi instance như component field. Tư duy nên dùng khi thiết kế:

- **Instance data**: liệt kê trong **record header**.
- **Derived behavior**: viết instance methods.
- **Shared metadata/config**: static fields/methods, nếu thật sự thuộc record type.
- **Separate mutable workflow state**: service/entity/normal class, không nhét hidden fields vào record.

## 8. Constructor là nơi thiết lập invariant cho component fields

Cấm extra instance fields không cản record kiểm tra input hoặc normalize values.

~~~java
record AccountId(String value) {
    AccountId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value");
        }
        value = value.strip();
    }
}
~~~

Đây là **compact canonical constructor**. Parameter `value` được implicit từ record header. Khi block hoàn thành bình thường, Java tự gán transformed parameter vào backing component field. Bạn không khai thêm một field “normalizedValue” bên cạnh.

### 8.1. Normal canonical constructor

~~~java
record Pair(int left, int right) {
    Pair(int left, int right) {
        this.left = left;
        this.right = right;
    }
}
~~~

Nếu viết normal canonical constructor, bạn phải initialize đúng từng component field theo Java definite assignment rules. Ngược lại, compact constructor **không được tự gán component fields** trong body theo cơ chế viết `this.left = ...`; hãy mutate/normalize implicit parameters để Java gán sau.

### 8.2. Constructor overload khác canonical

~~~java
record Label(String text, int priority) {
    Label(String text) {
        this(text, 0);
    }
}
~~~

Non-canonical constructor phải delegate tới constructor cùng record bằng `this(...)` theo rules. Nó không mở quyền “có state riêng” bằng cách tự gán field khác.

## 9. Chương trình: validation, normalization và derived behavior

Lưu **`RecordInvariantDemo.java`**:

~~~java
import java.util.Objects;

public class RecordInvariantDemo {
    record User(String name, int age) {
        User {
            Objects.requireNonNull(name, "name");
            name = name.strip();

            if (name.isEmpty()) {
                throw new IllegalArgumentException("name blank");
            }
            if (age < 0 || age > 150) {
                throw new IllegalArgumentException("age");
            }
        }

        boolean adult() {
            return age >= 18;
        }
    }

    public static void main(String[] args) {
        User lan = new User("  Lan  ", 21);

        System.out.println("value=" + lan);
        System.out.println("adult=" + lan.adult());

        try {
            new User("  ", 30);
        } catch (IllegalArgumentException expected) {
            System.out.println("blank name rejected");
        }

        try {
            new User("Minh", -1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid age rejected");
        }
    }
}
~~~

Chạy:

~~~bash
javac RecordInvariantDemo.java
java RecordInvariantDemo
~~~

Output:

~~~text
value=User[name=Lan, age=21]
adult=true
blank name rejected
invalid age rejected
~~~

Record không cần instance initializer block để validate. Constructor bảo đảm ngay sau construction, object đã thỏa invariant. Nếu validation fail, construction không trả một value hợp lệ.

## 10. Record ngầm `final`: không có subclass

Java 17 quy định record class **implicitly final** (JLS `8.10`). Ví dụ:

~~~java
record Point(int x, int y) {
}
~~~

Record đã không cho subclass dù bạn không viết từ khóa `final`:

~~~java
// class ColoredPoint extends Point { } // Compile-time error.
// Point không thể bị extends vì record is final.
~~~

Bạn có thể ghi `final record Point(...)` như modifier thừa hợp lệ trong một số scopes phù hợp, nhưng thông thường không cần làm thế: record mặc định đã final.

### 10.1. Không khai `abstract`, `sealed` hoặc `non-sealed` record

~~~java
// abstract record Shape(int size) { } // Sai.
// sealed record Shape(int size) { }   // Sai.
// non-sealed record Shape(int size) {} // Sai.
~~~

Một abstract record yêu cầu khả năng có subclass để hoàn thiện abstract members, trong khi record được final. Hơn nữa JLS cấm trực tiếp các modifiers `abstract`, `sealed`, `non-sealed` cho record declarations.

Điểm dễ nhầm: **record không được là sealed class**, nhưng **record có thể implement một sealed interface** nếu được phép. Hai quy tắc không mâu thuẫn: `sealed` trên interface kiểm soát các implementors, còn record triển khai nó là một concrete final type.

## 11. Record kế thừa trực tiếp `java.lang.Record`

Mọi record class có **direct superclass** là `java.lang.Record` theo đặc tả. Vì record declaration không có `extends` clause, bạn không được viết:

~~~java
// record Data(int x) extends Object { } // Sai cú pháp.
// record Data(int x) extends Record { } // Cũng sai.
~~~

Với normal class, bạn có thể viết `class Child extends Parent`. Với record, superclass được ngôn ngữ chọn sẵn: `Record`. Dĩ nhiên class `java.lang.Record` cuối cùng nằm trong object hierarchy, tức object record vẫn là một `Object`.

### 11.1. Những method nào liên quan `Record` và `Object`?

- `equals(Object)`, `hashCode()`, `toString()` được record class cung cấp implementations phù hợp với record components (ngầm hoặc do bạn khai báo).
- Methods từ `Object` như `getClass()` vẫn sử dụng được; gọi `record.getClass()` trả runtime class.
- `Record` là superclass trừu tượng đặc thù, không phải nơi bạn khai báo per-instance fields.
- Constructor của Record không phải API bạn gọi trực tiếp từ record canonical constructor.
- Không khai thêm `extends Parent` để kế thừa fields/methods từ Parent.
- **Interfaces mới là cơ chế polymorphism thích hợp** khi cần nhiều record types chia sẻ một contract.

### 11.2. Không thể extends một record khác

~~~java
record Coordinate(int x, int y) {
}

// record Colored(int x, int y, String color)
//         extends Coordinate { } // Không hợp lệ.
~~~

Để compose values, khai:

~~~java
record Colored(Coordinate point, String color) {
}
~~~

Đây là **composition**, không phải inheritance. Component `point` là Coordinate value; `Colored` không trở thành subtype của Coordinate. Nếu muốn polymorphism, cả hai có thể implement chung một interface thích hợp.

## 12. Chương trình: kiểm chứng runtime class và superclass

Lưu **`RecordSuperclassDemo.java`**:

~~~java
public class RecordSuperclassDemo {
    record Point(int x, int y) {
    }

    public static void main(String[] args) {
        Point point = new Point(2, 5);

        System.out.println("record=" + point);
        System.out.println("is Object=" + (point instanceof Object));
        System.out.println("is Record=" + (point instanceof Record));
        System.out.println("superclass=" +
                point.getClass().getSuperclass().getName());
    }
}
~~~

Chạy:

~~~bash
javac RecordSuperclassDemo.java
java RecordSuperclassDemo
~~~

Output:

~~~text
record=Point[x=2, y=5]
is Object=true
is Record=true
superclass=java.lang.Record
~~~

Reflection ở đây chỉ kiểm tra **loại superclass** bằng JDK API, không giả định tên synthetic field/constructor của compiler. `Record` trong `instanceof Record` là `java.lang.Record` có sẵn trong Java 17.

## 13. Record có thể implements interfaces

Một record có thể khai một hoặc nhiều superinterfaces ngay sau record header:

~~~java
interface Named {
    String name();
}

record Person(String name, int age) implements Named {
}
~~~

`Person` không extends một user superclass; nó **implements Named**. Khi interface yêu cầu method `String name()`, **generated record accessor `name()`** có cùng signature và public accessibility nên tự đáp ứng contract. Không bắt buộc viết lại accessor nếu generated one đã đủ.

Đây là lợi thế: record components vừa là data representation, vừa có thể tham gia interface API **khi tên/type/parameters của methods tương ứng khớp**.

### 13.1. Method contract quyết định khả năng tự implement

Nếu interface yêu cầu:

~~~java
interface JavaBeanNamed {
    String getName();
}
~~~

Thì `record Person(String name) implements JavaBeanNamed {}` **không tự thỏa contract** bằng generated accessor `name()`, vì `getName()` khác tên và signature. Bạn cần tự viết:

~~~java
record Person(String name) implements JavaBeanNamed {
    @Override
    public String getName() {
        return name;
    }
}
~~~

Không suy luận “interface có ý nghĩa tên giống nhau thì Java tự ghép fields”. Java chọn bằng **method signatures**, không suy tên ý nghĩa nghiệp vụ.

## 14. Chương trình: generated accessor tự hiện thực interface

Lưu **`RecordAccessorInterfaceDemo.java`**:

~~~java
public class RecordAccessorInterfaceDemo {
    interface Named {
        String name();
    }

    record Employee(String name, int salary)
            implements Named {
    }

    static void printName(Named value) {
        System.out.println("name=" + value.name());
    }

    public static void main(String[] args) {
        Employee employee = new Employee("Lan", 100);

        printName(employee);
        System.out.println("salary=" + employee.salary());
        System.out.println("implements Named=" +
                (employee instanceof Named));
    }
}
~~~

Chạy:

~~~bash
javac RecordAccessorInterfaceDemo.java
java RecordAccessorInterfaceDemo
~~~

Output:

~~~text
name=Lan
salary=100
implements Named=true
~~~

Employee accessor `name()` được compiler sinh và có visibility `public`, nên chính nó thực hiện method `name()` của Named. Interface reference `Named value` chỉ công khai `name()`, vì `salary()` không thuộc interface contract.

## 15. Nếu interface yêu cầu method khác tên accessor, phải tự viết

Record có thể giữ một component và cung cấp adapter method:

~~~java
interface HasId {
    String getId();
}

record Account(String id) implements HasId {
    @Override
    public String getId() {
        return id;
    }
}
~~~

`getId()` ở đây là **custom method**. Record vẫn có generated `id()`. Hai methods cùng trả component value, nhưng caller thuộc API nào sẽ gọi method tương ứng.

### 15.1. Chương trình runnable

Lưu **`RecordExplicitInterfaceDemo.java`**:

~~~java
public class RecordExplicitInterfaceDemo {
    interface HasId {
        String getId();
    }

    record Account(String id, boolean active)
            implements HasId {
        @Override
        public String getId() {
            return id;
        }

        String label() {
            return id + (active ? ":active" : ":inactive");
        }
    }

    static void show(HasId item) {
        System.out.println("interface id=" + item.getId());
    }

    public static void main(String[] args) {
        Account account = new Account("A-1", true);

        show(account);
        System.out.println("component id=" + account.id());
        System.out.println("label=" + account.label());
    }
}
~~~

Chạy:

~~~bash
javac RecordExplicitInterfaceDemo.java
java RecordExplicitInterfaceDemo
~~~

Output:

~~~text
interface id=A-1
component id=A-1
label=A-1:active
~~~

**Bài học:** record hỗ trợ interface như class thường, nhưng không tự biến tất cả các component getters thành các method tên bất kỳ. Phải viết method nếu signature không trùng.

## 16. Interface default methods: record có thể kế thừa behavior

Interfaces trong Java có thể khai **default method**. Một record implement interface ấy có thể dùng default method mà không cần duplicate implementation nếu method không xung đột.

~~~java
interface Named {
    String name();

    default String label() {
        return "Hello " + name();
    }
}

record User(String name) implements Named {
}
~~~

Record `User` cung cấp `name()` qua generated accessor; default `label()` gọi method ấy qua interface contract.

### 16.1. Chương trình runnable

Lưu **`RecordDefaultInterfaceDemo.java`**:

~~~java
public class RecordDefaultInterfaceDemo {
    interface Named {
        String name();

        default String greeting() {
            return "Hello " + name();
        }
    }

    record User(String name) implements Named {
    }

    public static void main(String[] args) {
        Named person = new User("Lan");

        System.out.println("name=" + person.name());
        System.out.println("greeting=" + person.greeting());
    }
}
~~~

Chạy:

~~~bash
javac RecordDefaultInterfaceDemo.java
java RecordDefaultInterfaceDemo
~~~

Output:

~~~text
name=Lan
greeting=Hello Lan
~~~

Đây là **kế thừa hành vi từ interface**, không phải kế thừa instance fields từ một user superclass. Generated accessor trong User cung cấp data cho default method.

### 16.2. Có thể override default method

Nếu record muốn quy tắc khác, khai:

~~~java
record User(String name) implements Named {
    @Override
    public String greeting() {
        return "Xin chao " + name;
    }
}
~~~

Cần giữ đúng method signature/visibility. Interface default method không bắt buộc mọi implementor dùng cùng implementation.

## 17. Xung đột default methods từ nhiều interfaces

Một record được phép implements nhiều interfaces:

~~~java
record Point(int x, int y)
        implements java.io.Serializable, Comparable<Point> {
    @Override
    public int compareTo(Point other) {
        int byX = Integer.compare(x, other.x());
        return byX != 0 ? byX : Integer.compare(y, other.y());
    }
}
~~~

Nhưng nếu hai interfaces cung cấp **cùng một default method signature** và không có ưu tiên đủ rõ, record thường phải override để giải quyết xung đột. Nguyên tắc này giống normal class.

### 17.1. Chương trình hòa giải default methods

Lưu **`RecordDefaultConflictDemo.java`**:

~~~java
public class RecordDefaultConflictDemo {
    interface A {
        default String label() {
            return "A";
        }
    }

    interface B {
        default String label() {
            return "B";
        }
    }

    record Item(int id) implements A, B {
        @Override
        public String label() {
            return A.super.label() + "+" + B.super.label() +
                    ":" + id;
        }
    }

    public static void main(String[] args) {
        Item item = new Item(7);

        System.out.println(item.label());
        System.out.println("A=" + ((A) item).label());
        System.out.println("B=" + ((B) item).label());
    }
}
~~~

Chạy:

~~~bash
javac RecordDefaultConflictDemo.java
java RecordDefaultConflictDemo
~~~

Output:

~~~text
A+B:7
A=A+B:7
B=A+B:7
~~~

Dù cast receiver về A hoặc B, virtual dispatch vẫn chọn override của Item. Cú pháp `A.super.label()`/`B.super.label()` **chỉ được dùng bên trong Item override** để gọi riêng từng default implementation.

Nếu bỏ override, compiler từ chối vì default method conflict. Record không có ngoại lệ riêng cho xung đột này.

## 18. Interface static fields là shared constants, không instance state

Một interface:

~~~java
interface Measurement {
    String UNIT = "cm";

    int magnitude();
}
~~~

`UNIT` là `public static final`. Record có thể implement:

~~~java
record Length(int magnitude) implements Measurement {
}
~~~

Generated `magnitude()` thỏa interface method. Muốn dùng static constant, viết `Measurement.UNIT` để ý nghĩa rõ.

Điều này không sinh thêm component field `UNIT` trên mỗi Length object và không tham gia generated equality. Interface không chứa mutable instance fields để record “thừa hưởng”.

## 19. Chương trình: generic interface với generic record

Lưu **`RecordGenericInterfaceDemo.java`**:

~~~java
public class RecordGenericInterfaceDemo {
    interface ValueSource<T> {
        T value();

        default String describe() {
            return "value=" + value();
        }
    }

    record Box<T>(T value) implements ValueSource<T> {
    }

    public static void main(String[] args) {
        ValueSource<String> first = new Box<>("Java");
        ValueSource<Integer> second = new Box<>(17);

        System.out.println(first.describe());
        System.out.println(second.describe());
        System.out.println("string=" + first.value());
        System.out.println("integer=" + second.value());
    }
}
~~~

Chạy:

~~~bash
javac RecordGenericInterfaceDemo.java
java RecordGenericInterfaceDemo
~~~

Output:

~~~text
value=Java
value=17
string=Java
integer=17
~~~

Record `Box<T>` tự khai type variable T. Generated accessor `T value()` đáp ứng generic method `ValueSource<T>.value()` sau type substitution/erasure theo Java generic rules. Caller giữ compile-time typing an toàn hơn so với Object[].

**Cẩn trọng:** `Box<List<String>>` vẫn giữ một List reference; generic type parameter không làm nested list immutable.

## 20. Implement `Comparable` để xác định thứ tự

Generated record `equals`/`hashCode` **không tự làm record implement Comparable**. Nếu ứng dụng cần sort theo thứ tự tự nhiên, record có thể implements `Comparable<RecordType>` và tự viết `compareTo`.

~~~java
record Version(int major, int minor)
        implements Comparable<Version> {
    @Override
    public int compareTo(Version other) {
        int first = Integer.compare(major, other.major);
        return first != 0 ? first
                : Integer.compare(minor, other.minor);
    }
}
~~~

Dùng `Integer.compare` thay vì `major - other.major` để tránh integer overflow. Với records dùng trong sorted collections, nên thiết kế `compareTo` nhất quán với `equals` nếu hợp đồng collection/domain đòi hỏi. Nếu compareTo trả 0 cho hai records không equals, `TreeSet` có thể xem chúng trùng vị trí sắp xếp dù `HashSet` xem khác.

### 20.1. Chương trình sort

Lưu **`RecordComparableDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordComparableDemo {
    record Version(int major, int minor)
            implements Comparable<Version> {
        @Override
        public int compareTo(Version other) {
            int first = Integer.compare(major, other.major);
            return first != 0 ? first
                    : Integer.compare(minor, other.minor);
        }
    }

    public static void main(String[] args) {
        List<Version> versions = new ArrayList<>(
                List.of(new Version(2, 0),
                        new Version(1, 9),
                        new Version(1, 2)));

        versions.sort(null);
        for (Version version : versions) {
            System.out.println(version);
        }
    }
}
~~~

Chạy:

~~~bash
javac RecordComparableDemo.java
java RecordComparableDemo
~~~

Output:

~~~text
Version[major=1, minor=2]
Version[major=1, minor=9]
Version[major=2, minor=0]
~~~

Mỗi Version object vẫn final về component fields. Sắp xếp List thay đổi **thứ tự references trong collection**, không mutate record instances.

## 21. Record có thể triển khai sealed interface (Java 17)

Sealed interface giới hạn **danh sách các loại triển khai trực tiếp**. Record là implicitly final nên phù hợp làm một permitted concrete implementation.

~~~java
sealed interface Shape permits Circle, Rectangle {
    long area();
}

record Circle(int radius) implements Shape {
    @Override
    public long area() {
        return 3L * radius * radius; // Công thức giả lập có hệ số 3.
    }
}

record Rectangle(int width, int height) implements Shape {
    @Override
    public long area() {
        return (long) width * height;
    }
}
~~~

Đây là các **declarations minh họa**, không có main. Nếu dùng geometry thực cần công thức π/precision phù hợp. Sealed interface có ích khi tập variants biết trước, còn từng record đại diện immutable data cho mỗi variant.

### 21.1. Hai giới hạn không mâu thuẫn

- Record **không** được khai `sealed record`.
- Record **có thể implements một `sealed interface`** nếu được permitted theo Java rules.
- Record vẫn **final**, không thể bị subclass tiếp.
- Sealed interface không tự cho record kế thừa instance fields của kiểu khác.

## 22. Chương trình đầy đủ: sealed interface với record implementations

Lưu **`RecordSealedInterfaceDemo.java`**:

~~~java
public class RecordSealedInterfaceDemo {
    sealed interface Figure permits Square, Rectangle {
        long area();
    }

    record Square(int side) implements Figure {
        @Override
        public long area() {
            return (long) side * side;
        }
    }

    record Rectangle(int width, int height)
            implements Figure {
        @Override
        public long area() {
            return (long) width * height;
        }
    }

    static void show(Figure value) {
        System.out.println(value.getClass().getSimpleName() +
                "=" + value.area());
    }

    public static void main(String[] args) {
        show(new Square(3));
        show(new Rectangle(2, 5));
    }
}
~~~

Chạy:

~~~bash
javac RecordSealedInterfaceDemo.java
java RecordSealedInterfaceDemo
~~~

Output:

~~~text
Square=9
Rectangle=10
~~~

Mặc dù nested record classes nằm trong top-level demo, tên simple class `Square`/`Rectangle` xác định ổn định theo `getSimpleName()` đối với các named member record declarations này. Sealed interface kiểm soát direct implementations `Square`/`Rectangle`, không đổi ngữ nghĩa của record component fields.

## 23. Composition thay vì inheritance của record classes

Muốn một kiểu có thêm dữ liệu dựa trên một record khác, dùng **composition**:

~~~java
record Point(int x, int y) {
}

record ColoredPoint(Point point, String color) {
}
~~~

Không thể:

~~~java
// record ColoredPoint(int x, int y, String color)
//         extends Point { } // Sai.
~~~

Nếu domain cần polymorphism chung, thiết kế một interface:

~~~java
interface HasPoint {
    Point point();
}

record Marker(Point point) implements HasPoint {
}

record ColoredPoint(Point point, String color)
        implements HasPoint {
}
~~~

Hai record types implement cùng interface, nhưng không kế thừa fields từ nhau. Đây là Java **composition + interface polymorphism**, thường rõ ràng hơn ép record inheritance.

### 23.1. Chương trình composition

Lưu **`RecordCompositionDemo.java`**:

~~~java
public class RecordCompositionDemo {
    record Point(int x, int y) {
    }

    interface Located {
        Point point();
    }

    record Labelled(Point point, String label)
            implements Located {
    }

    record Colored(Point point, String color)
            implements Located {
    }

    static String coordinates(Located value) {
        return value.point().x() + "," +
                value.point().y();
    }

    public static void main(String[] args) {
        Point origin = new Point(1, 2);
        Located a = new Labelled(origin, "A");
        Located b = new Colored(origin, "red");

        System.out.println("a=" + coordinates(a));
        System.out.println("b=" + coordinates(b));
        System.out.println("shared point=" +
                (a.point() == b.point()));
    }
}
~~~

Chạy:

~~~bash
javac RecordCompositionDemo.java
java RecordCompositionDemo
~~~

Output:

~~~text
a=1,2
b=1,2
shared point=true
~~~

Hai records chia sẻ immutable Point value object an toàn về mutation vì Point chỉ có int components. Nếu component là một mutable object, chia sẻ reference cần ownership contract rõ.

## 24. Interfaces không biến record thành mutable bean

Một interface có thể yêu cầu setter-like method:

~~~java
interface Renameable {
    void rename(String name);
}
~~~

Về cú pháp, record có thể implement một method `void rename(String)` làm side effects với một external service, nhưng nó **không thể gán lại record component field**:

~~~java
record User(String name) implements Renameable {
    @Override
    public void rename(String newName) {
        // this.name = newName; // Compile-time error: final field.
        throw new UnsupportedOperationException("immutable value");
    }
}
~~~

Đây là **mảnh code minh họa**, không phải khuyến nghị implement Renameable chỉ để ném exception. Thiết kế tốt hơn là **không** ép record vào interface đòi mutable object identity/state. Dùng một interface immutable-value phù hợp hoặc trả record mới.

### 24.1. Thiết kế return-new-instance

~~~java
interface WithName<T> {
    T withName(String name);
}

record User(String name) implements WithName<User> {
    @Override
    public User withName(String next) {
        return new User(next);
    }
}
~~~

Đây là một immutable evolution API có behavior đúng hơn. Interface contract thể hiện operation tạo value mới thay vì sửa object hiện tại.

## 25. Chương trình: interface tạo record value mới

Lưu **`RecordWithInterfaceDemo.java`**:

~~~java
public class RecordWithInterfaceDemo {
    interface WithTitle<T> {
        T withTitle(String title);
    }

    record Document(String title, int pages)
            implements WithTitle<Document> {
        @Override
        public Document withTitle(String next) {
            return new Document(next, pages);
        }
    }

    public static void main(String[] args) {
        Document before = new Document("Draft", 2);
        Document after = before.withTitle("Final");

        System.out.println("before=" + before);
        System.out.println("after=" + after);
        System.out.println("same object=" + (before == after));
        System.out.println("same pages=" +
                (before.pages() == after.pages()));
    }
}
~~~

Chạy:

~~~bash
javac RecordWithInterfaceDemo.java
java RecordWithInterfaceDemo
~~~

Output:

~~~text
before=Document[title=Draft, pages=2]
after=Document[title=Final, pages=2]
same object=false
same pages=true
~~~

Record fields không bị thay đổi sau construction. Interface `WithTitle<Document>` mô tả rõ hoạt động trả một Document value mới.

## 26. Component fields final chưa chắc đối tượng sâu bên trong immutable

Đặc điểm `private final` của component field chỉ cố định **field reference/value**. Nếu record component là mutable container:

~~~java
record Basket(java.util.List<String> items) {
}
~~~

Caller có thể giữ same mutable List object và mutate nó, vì generated accessor `items()` trả reference. Record vẫn không khai thêm instance fields, nhưng **component itself** có thể chỉ tới mutable state.

Một record có components value-stable như primitives, String, LocalDate hoặc immutable value records sẽ dễ đảm bảo invariants hơn.

### 26.1. Chương trình: mutable list vẫn có thể thay đổi

Lưu **`RecordShallowFieldDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordShallowFieldDemo {
    record Basket(List<String> items) {
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket basket = new Basket(source);

        source.add("B");
        basket.items().add("C");

        System.out.println("source=" + source);
        System.out.println("record items=" + basket.items());
        System.out.println("same list=" +
                (source == basket.items()));
    }
}
~~~

Chạy:

~~~bash
javac RecordShallowFieldDemo.java
java RecordShallowFieldDemo
~~~

Output:

~~~text
source=[A, B, C]
record items=[A, B, C]
same list=true
~~~

Tính final của component field không có nghĩa `List.add` bị cấm. Khi dùng record để biểu diễn immutable value, **component type selection** và defensive-copy contract vẫn cần thiết.

## 27. Defensive copy ở constructor khi cần snapshot

Dùng compact constructor để chuẩn hóa một mutable List thành unmodifiable snapshot:

~~~java
record Basket(java.util.List<String> items) {
    Basket {
        items = java.util.List.copyOf(items);
    }
}
~~~

`List.copyOf` giữ immutable structure (không cho add/remove), đồng thời reject null elements. Với immutable String elements, đây thường là snapshot đủ an toàn. Nhưng nếu component là `List<MutableItem>`, values vẫn có thể thay đổi qua aliases đến từng MutableItem.

### 27.1. Chương trình snapshot

Lưu **`RecordDefensiveListDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordDefensiveListDemo {
    record Basket(List<String> items) {
        Basket {
            items = List.copyOf(items);
        }

        int count() {
            return items.size();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket snapshot = new Basket(source);
        source.add("B");

        System.out.println("source=" + source);
        System.out.println("snapshot=" + snapshot.items());
        System.out.println("count=" + snapshot.count());

        try {
            snapshot.items().add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot immutable structure");
        }
    }
}
~~~

Chạy:

~~~bash
javac RecordDefensiveListDemo.java
java RecordDefensiveListDemo
~~~

Output:

~~~text
source=[A, B]
snapshot=[A]
count=1
snapshot immutable structure
~~~

Không có hidden instance field nào được thêm: record `Basket` vẫn chỉ chứa một component `items`. Constructor normalization làm component reference trỏ tới unmodifiable list representation.

## 28. Array components và equality: một lưu ý quan trọng

Với:

~~~java
record Bytes(byte[] data) {
}
~~~

`Bytes` có private final array reference, nhưng array có mutable elements. Generated `equals`/`hashCode` **không** dùng `Arrays.equals`/`Arrays.hashCode` để so nội dung các mảng; arrays dùng reference equality semantics trong component comparison.

Nếu cần content-based value semantics, cân nhắc representation khác (immutable List of Byte hoặc domain type) hoặc custom `equals`/`hashCode` với defensive copies và kỹ thuật đúng.

Không override một method `equals` mà quên `hashCode` tương thích. Không dùng record với mutable component làm HashMap key trừ khi equality/hash relevant state được bảo vệ/ổn định.

### 28.1. Chương trình phân biệt reference và content

Lưu **`RecordArrayEqualityDemo.java`**:

~~~java
import java.util.Arrays;

public class RecordArrayEqualityDemo {
    record Bytes(byte[] data) {
    }

    public static void main(String[] args) {
        byte[] left = {1, 2};
        byte[] right = {1, 2};

        Bytes a = new Bytes(left);
        Bytes b = new Bytes(right);
        Bytes c = new Bytes(left);

        System.out.println("arrays content=" +
                Arrays.equals(left, right));
        System.out.println("a equals b=" + a.equals(b));
        System.out.println("a equals c=" + a.equals(c));
        System.out.println("same raw ref=" +
                (a.data() == c.data()));
    }
}
~~~

Chạy:

~~~bash
javac RecordArrayEqualityDemo.java
java RecordArrayEqualityDemo
~~~

Output:

~~~text
arrays content=true
a equals b=false
a equals c=true
same raw ref=true
~~~

Đây là ví dụ minh họa **generated array-component equality**, không chứng minh array là immutable. `a.data()`/`c.data()` trả same raw array reference khi không override accessor.

## 29. Custom record accessor vẫn là method của record class

Bạn có thể khai accessor tường minh khi cần defensive copy:

~~~java
record Packet(byte[] bytes) {
    Packet {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Accessor `bytes()` ở đây có return type đúng với component, public, không parameters, không `throws` clause. Phần thân trả cloned array để không expose internal array. Nó không tạo một instance field mới.

**Nhưng:** generated equality vẫn so array component references, không tự chuyển sang content equality. Hai Packet instances có cùng bytes contents mà constructor clone riêng arrays có thể `equals` false nếu không custom methods. Hãy kiểm tra toàn bộ contract: immutable snapshot, getters, equality, hashing và serialization.

## 30. Static nested member records và local records đều implicitly static

Một **member record** trong class được implicitly static:

~~~java
class Outer {
    private final String id;

    record Item(String code) {
    }
}
~~~

Tạo bằng `new Outer.Item("A")` nếu accessible, không cần `outer.new Item(...)`. Record `Item` không có enclosing Outer instance tự động nên không truy cập `Outer.this.id`.

Một **local record** trong method cũng implicitly static:

~~~java
void process(int amount) {
    record Result(int value) {
    }

    Result result = new Result(amount);
}
~~~

Local record không capture method variable `amount` trong body: caller truyền `amount` tường minh qua canonical constructor.

**Điểm quan trọng của chủ đề:** implicit-static nesting nói về việc **không giữ outer instance**, còn việc không được khai thêm instance fields là **quy tắc riêng của record representation**. Hai giới hạn có nguyên nhân khác nhau nhưng cùng giúp record làm value carrier minh bạch.

## 31. Chương trình: member record không kế thừa outer instance fields

Lưu **`RecordNestedStaticDemo.java`**:

~~~java
public class RecordNestedStaticDemo {
    static class Outer {
        private final String label;

        Outer(String label) {
            this.label = label;
        }

        record Item(String name) {
            String describe() {
                return name;
            }
        }

        String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer("Owner");
        Outer.Item item = new Outer.Item("Book");

        System.out.println("outer=" + outer.label());
        System.out.println("item=" + item.describe());
        System.out.println("value=" + item);
    }
}
~~~

Chạy:

~~~bash
javac RecordNestedStaticDemo.java
java RecordNestedStaticDemo
~~~

Output:

~~~text
outer=Owner
item=Book
value=Item[name=Book]
~~~

`Item` không giữ ngầm một Outer, nên không có `Outer.this.label` trong Item. Nếu Item cần owner data, truyền `label` hoặc reference Outer tường minh vào record component/method; điều đó lại tạo một **explicit reference path** có lifetime implications.

## 32. `Serializable` là interface, không phải mặc định của mọi record

Một record có thể khai `implements java.io.Serializable`:

~~~java
record Event(String type, long time)
        implements java.io.Serializable {
}
~~~

Không phải mọi record tự implements Serializable chỉ vì record có generated accessors/constructors. Nếu domain cần Java Object Serialization, đó là một **interface/format policy** riêng và record deserialization có semantics đặc thù: canonical constructor được sử dụng.

Trong ứng dụng hiện đại, JSON/protobuf/etc. tùy ecosystem cần library/tooling hỗ trợ records và schema migrations. Không dùng generated `toString()` làm wire format ổn định.

### 32.1. Tránh nhầm serialization với instance field rules

`Serializable` là marker interface không bắt record có additional mutable instance field. Record vẫn chỉ có component fields. Nếu record chứa component không serializable, cần xử lý theo serialization contract tương ứng; không giả định mọi graph tự serialize thành công.

## 33. Record generic và interface variance

Một generic record có thể implements một generic interface:

~~~java
interface Holder<T> {
    T get();
}

record Box<T>(T value) implements Holder<T> {
    @Override
    public T get() {
        return value;
    }
}
~~~

Vì `Holder<T>` yêu cầu `get()`, generated accessor `value()` không đáp ứng, nên cần custom method `get()`. Nếu interface yêu cầu `T value()`, generated accessor đã đủ.

### 33.1. Chương trình generic với adapter method

Lưu **`RecordGenericAdapterDemo.java`**:

~~~java
public class RecordGenericAdapterDemo {
    interface Holder<T> {
        T get();
    }

    record Box<T>(T value) implements Holder<T> {
        @Override
        public T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Holder<String> text = new Box<>("hello");
        Holder<Integer> number = new Box<>(42);

        System.out.println("text=" + text.get());
        System.out.println("number=" + number.get());
        System.out.println("box accessor=" +
                new Box<>("raw").value());
    }
}
~~~

Chạy:

~~~bash
javac RecordGenericAdapterDemo.java
java RecordGenericAdapterDemo
~~~

Output:

~~~text
text=hello
number=42
box accessor=raw
~~~

Không có anonymous adapter object được lưu trong record; method `get()` chỉ delegate tới component field. Type parameter T thuộc chính Box, hợp lệ theo Java generics.

## 34. Interface contract không tự định nghĩa component equality

Ví dụ hai record types:

~~~java
interface Identified {
    String id();
}

record Person(String id, String name)
        implements Identified {
}

record Product(String id, String description)
        implements Identified {
}
~~~

Cả hai implement `Identified`, nhưng generated equality của record **không** kết luận Person("A",...) equals Product("A",...) chỉ vì cùng id. Chúng là **khác record classes**, với component-based equality cho cùng record type.

Interface làm contract về **hành vi/accessors**, không biến nhiều classes thành một value type giống nhau.

### 34.1. Chương trình: đa hình không đồng nghĩa equals xuyên kiểu

Lưu **`RecordInterfaceEqualityDemo.java`**:

~~~java
public class RecordInterfaceEqualityDemo {
    interface Identified {
        String id();
    }

    record Person(String id, String name)
            implements Identified {
    }

    record Product(String id, String description)
            implements Identified {
    }

    public static void main(String[] args) {
        Identified person = new Person("X", "Lan");
        Identified product = new Product("X", "Book");

        System.out.println("same ids=" +
                person.id().equals(product.id()));
        System.out.println("record equals=" +
                person.equals(product));
        System.out.println("types=" +
                person.getClass().getSimpleName() + "/" +
                product.getClass().getSimpleName());
    }
}
~~~

Chạy:

~~~bash
javac RecordInterfaceEqualityDemo.java
java RecordInterfaceEqualityDemo
~~~

Output:

~~~text
same ids=true
record equals=false
types=Person/Product
~~~

`Identified` interface không tự thay đổi generated `equals`/`hashCode`. Nếu domain muốn entity identity based on id across types, một mutable identity entity/reference model có thể phù hợp hơn record generated value semantics.

## 35. Interface methods có thể có xung đột với component accessors

Giả sử:

~~~java
interface HasNumber {
    int value();
}
~~~

`record Count(int value) implements HasNumber {}` tự thỏa. Nhưng nếu interface yêu cầu `String value()` trong khi record component có kiểu `int value`, generated accessor `int value()` **không** có return type tương thích để implement method, nên record declaration không compile.

Compiler không chuyển đổi int→String bằng tên giống nhau. Chọn record component type phù hợp với interface contract hoặc thiết kế adapter method với **tên khác**. Bạn cũng không thể tự viết hai methods cùng parameter signature và chỉ khác return type trong cùng record body để “đáp ứng cả hai”.

Tương tự, component name không được xung đột với những no-args Object method names bị JLS cấm cho record components (ví dụ `toString`, `hashCode`, `getClass`). Đây là name/signature restrictions phục vụ record accessors hợp lệ.

## 36. Interface có thể chứa static methods: record không inherit chúng như instance methods

Interface:

~~~java
interface Identified {
    String id();

    static String normalize(String raw) {
        return raw.strip();
    }
}
~~~

Method `Identified.normalize(...)` là **static interface method**. Khi record implements Identified, không thể chỉ gọi `myRecord.normalize(...)` như thể đó là inherited instance method.

Một record có thể sử dụng static method qua **interface type name** trong compact constructor:

~~~java
record Id(String id) implements Identified {
    Id {
        id = Identified.normalize(id);
    }
}
~~~

Static method thuộc interface, không tạo state per record instance và không trở thành một component. Phân biệt instance/default interface behavior với static interface utilities.

## 37. Method overriding trong record có giới hạn gì?

Record **final**, nên subclass của record không thể override methods. Tuy nhiên **chính record** vẫn có thể:

- Override `Object/Record` methods `equals`, `hashCode`, `toString` phù hợp rules.
- Override concrete interface default methods.
- Implement abstract interface methods.
- Explicitly declare component accessor method với signature/visibility hợp lệ.
- Overload instance/static methods như class thông thường, trừ các restrictions cụ thể của record.

Một record **không được tự khai abstract/native method** trong record body (JLS `8.10.2`), vì record là complete final concrete value class. Nếu interface yêu cầu method abstract, record phải cung cấp implementation (trực tiếp hoặc qua phù hợp generated/inherited concrete method).

### 37.1. Override `toString()` có thể đổi presentation

~~~java
record Coordinate(int x, int y) {
    @Override
    public String toString() {
        return "(" + x + "," + y + ")";
    }
}
~~~

Generated equality/hashCode vẫn dựa components nếu bạn không override. Nhưng `toString()` giờ trả representation khác default record syntax. Không dùng `toString` làm JSON/persistent wire schema.

## 38. Khi nào interface/default method không còn phù hợp?

Nếu muốn reuse substantial mutable implementation state giữa nhiều classes, interface chỉ có default methods/static constants, không cung cấp per-object instance fields. Record lại không thể inherit một base class chứa state hay khai thêm fields.

Các hướng thiết kế hợp lý:

1. **Interface + component data**: khi behavior có thể được tính từ record components.
2. **Interface + helper service**: khi behavior cần services dài hạn, resource ownership, external dependencies.
3. **Composition**: record chứa immutable value components khác.
4. **Normal class**: khi cần mutable identity/state, inheritance of implementation, caches, locks, resources.
5. **Sealed interface + record variants**: khi domain là tổng hữu hạn các immutable case variants.
6. **Factory/validation layer**: khi constructor cần logic phức tạp, nhưng record representation vẫn đơn giản.

Không phải “record luôn tốt hơn class”; nó là lựa chọn phù hợp nếu **component-based transparent value semantics** thực sự mô tả object.

## 39. Bảng quy tắc tổng hợp

| Chủ đề | Record Java 17 | Ghi chú |
| --- | --- | --- |
| Component field | Có, khai ngầm `private final` | Một field cho mỗi header component |
| Tự khai additional instance field | **Không** | Cấm mọi non-static field declaration trong body |
| Tự khai instance initializer block | **Không** | Dùng constructor |
| Static field | Có | Shared theo record class, không phải component |
| Static initializer | Có | Chạy theo class init, không per instance |
| Instance method | Có | Derived behavior từ components |
| Static method | Có | Class-level helper/factory |
| Canonical constructor | Có | Generated, normal hoặc compact |
| Non-canonical constructor | Có | Delegates bằng `this(...)` |
| Extends user class | **Không** | Direct superclass là java.lang.Record |
| Record extends record | **Không** | Record final |
| Abstract/sealed/non-sealed record | **Không** | Bị cấm |
| Implicit final | Có | Không cho subclass |
| Explicit redundant final | Có thể | Thường không cần |
| Implements interface | Có | Một hoặc nhiều, theo Java rules |
| Implements generic interface | Có | Match type parameters/signatures |
| Generated accessor implements interface method | Có thể | Khi return type/signature compatible |
| Interface default method | Có thể kế thừa | Có thể override; xử lý conflict |
| Implements sealed interface | Có nếu permitted | Record final là một permitted implementation |
| Custom equals/hashCode/toString | Có | Tuân Object/record contract |
| Component reference sâu immutable | **Không đảm bảo** | Mutable nested graph cần ownership/copy |
| Member/local record implicitly static | Có | Không có enclosing instance ngầm |
| `implements Serializable` | Có thể | Không tự áp dụng cho mọi record |

## 40. Lỗi biên dịch thường gặp và hướng sửa

### 40.1. Additional instance field

~~~java
record R(int x) {
    // private int cache; // Compile-time error.
}
~~~

**Sửa:** tính cache từ component bằng method, dùng external service/cache hoặc normal class nếu caching per-instance là essential.

### 40.2. Instance initializer block

~~~java
record R(int x) {
    // { System.out.println(x); } // Compile-time error.
}
~~~

**Sửa:** compact constructor `R { ... }` nếu cần validate/normalize.

### 40.3. Cố kế thừa normal superclass

~~~java
class Base {
}

// record R(int x) extends Base {} // Compile-time error.
~~~

**Sửa:** record không có extends; dùng composition hoặc interface.

### 40.4. Cố subclass record

~~~java
record BaseRecord(int x) {
}

// class Child extends BaseRecord {} // Compile-time error.
~~~

**Sửa:** không extends final record; tạo record chứa BaseRecord component hoặc một interface chung.

### 40.5. Không implement interface đúng signature

~~~java
interface Named {
    String getName();
}

// record Person(String name) implements Named { } // Error.
~~~

**Sửa:** viết public `getName()` delegate `name()`, hoặc đổi interface contract sang `name()` nếu API cho phép.

### 40.6. Interface return type xung đột với accessor

~~~java
interface HasValue {
    String value();
}

// record R(int value) implements HasValue { } // Error.
~~~

**Sửa:** chọn component type/contract tương thích hoặc thiết kế phương thức chuyển đổi với tên khác. Không overload chỉ bằng return type.

### 40.7. Method abstract trong record body

~~~java
record R(int x) {
    // abstract int compute(); // Error.
}
~~~

**Sửa:** viết concrete method; hoặc dùng sealed interface với multiple implementing records nếu cần abstract behavior across variants.

### 40.8. Mutate final component field

~~~java
record R(int x) {
    // void change(int n) { this.x = n; } // Error.
}
~~~

**Sửa:** tạo record mới `new R(n)`; hoặc dùng mutable normal class nếu contract yêu cầu in-place update.

### 40.9. Coi static field là component

~~~java
record R(int x) {
    static int total;
}
~~~

`total` là static class field; generated equals, hashCode, toString chỉ xét `x`. Nếu muốn mỗi instance lưu total, thêm `total` vào header nếu đúng ý nghĩa representation.

### 40.10. Không hiểu shallow immutable

~~~java
record R(java.util.List<String> items) {
}
~~~

Nếu truyền mutable list, `items()` có thể cho mutate list. **Sửa** bằng immutable list snapshot khi contract yêu cầu; không cần thêm instance field.

## 41. Chương trình tích hợp: interface + record components + static catalog

Lưu **`RecordInterfaceIntegrationDemo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;

public class RecordInterfaceIntegrationDemo {
    interface ProductView {
        String sku();
        long total();

        default String summary() {
            return sku() + ":" + total();
        }
    }

    record Product(String sku, long unitPrice, int quantity)
            implements ProductView {
        static final Map<String, String> LABELS =
                Map.of("PEN", "Pen", "BOOK", "Book");

        Product {
            Objects.requireNonNull(sku, "sku");
            if (unitPrice < 0 || quantity < 0) {
                throw new IllegalArgumentException("numbers");
            }
        }

        @Override
        public long total() {
            return Math.multiplyExact(unitPrice, quantity);
        }

        String displayName() {
            return LABELS.getOrDefault(sku, sku);
        }
    }

    static void report(ProductView value) {
        System.out.println(value.summary());
    }

    public static void main(String[] args) {
        Product first = new Product("PEN", 10, 2);
        Product second = new Product("BOOK", 50, 1);

        report(first);
        report(second);

        System.out.println("first name=" + first.displayName());
        System.out.println("second name=" + second.displayName());
        System.out.println("same first value=" +
                first.equals(new Product("PEN", 10, 2)));
    }
}
~~~

Chạy:

~~~bash
javac RecordInterfaceIntegrationDemo.java
java RecordInterfaceIntegrationDemo
~~~

Output:

~~~text
PEN:20
BOOK:50
first name=Pen
second name=Book
same first value=true
~~~

Phân tích:

- Component `sku` tự sinh accessor public `sku()`, thỏa method của `ProductView`.
- Interface `total()` **không trùng component** nào, nên Product triển khai bằng explicit instance method.
- Interface default `summary()` gọi đúng `sku()`/`total()` của receiver record.
- Static `LABELS` là shared catalog, không được tính vào component equality.
- Compact constructor validate fields, không thêm instance field mới.
- Product record final, không cần/không thể subclass để thêm state.
- `Math.multiplyExact` phát hiện overflow của multiplication; code thực tế cần giá/currency quy chuẩn, ở đây ví dụ dùng đơn vị long nhỏ.

## 42. Kiểm thử hợp đồng bằng Java thuần (không cần JUnit)

Lưu **`RecordRulesContractTest.java`**:

~~~java
public class RecordRulesContractTest {
    interface Identified {
        String id();
    }

    record Item(String id, int count)
            implements Identified {
        static final String PREFIX = "ITEM";

        Item {
            if (count < 0) {
                throw new IllegalArgumentException("count");
            }
        }

        String display() {
            return PREFIX + ":" + id + ":" + count;
        }
    }

    static void check(boolean ok, String description) {
        if (!ok) {
            throw new AssertionError(description);
        }
    }

    public static void main(String[] args) {
        Item first = new Item("A", 2);
        Item second = new Item("A", 2);
        Identified view = first;

        check(first != second, "different objects");
        check(first.equals(second), "component equality");
        check(first.hashCode() == second.hashCode(),
                "hash consistency");
        check("A".equals(view.id()), "interface accessor");
        check(first.getClass().getSuperclass() == Record.class,
                "direct superclass");
        check("ITEM:A:2".equals(first.display()),
                "static shared constant");

        try {
            new Item("B", -1);
            throw new AssertionError("invalid item accepted");
        } catch (IllegalArgumentException expected) {
            // Invariant được bảo vệ tại construction.
        }

        System.out.println("record rules checks passed");
    }
}
~~~

Chạy:

~~~bash
javac RecordRulesContractTest.java
java RecordRulesContractTest
~~~

Output:

~~~text
record rules checks passed
~~~

Test kiểm tra identity, generated value equality/hash, interface implementation, direct superclass, static constant và invariant. Method `check` luôn chạy; không phụ thuộc Java `assert` có thể bị tắt mặc định.

## 43. Bài tập tự luyện

### Bài tập A: Tại sao khai thêm field sai?

~~~java
record Temperature(double celsius) {
    // private double fahrenheit; // Sai.
}
~~~

**Đáp án:** Record representation đã cố định bởi header. Hãy viết:

~~~java
double fahrenheit() {
    return celsius * 9.0 / 5.0 + 32.0;
}
~~~

đặt trong record body, hoặc đưa Fahrenheit thành một component riêng **chỉ khi domain thực sự coi nó là stored state** và muốn equality/constructor phản ánh giá trị đó.

### Bài tập B: Interface được hiện thực tự động không?

~~~java
interface Named {
    String name();
}

record User(String name) implements Named {
}
~~~

**Đáp án:** Có. Generated `public String name()` đáp ứng signature `Named.name()`.

### Bài tập C: JavaBeans method thì sao?

~~~java
interface NamedBean {
    String getName();
}

// record User(String name) implements NamedBean { }
~~~

**Đáp án:** Không đủ. Cần custom `public String getName(){return name;}` trong record.

### Bài tập D: Kế thừa class có fields được không?

~~~java
class Base {
    int id;
}

// record Item(int n) extends Base { }
~~~

**Đáp án:** Không. Record trực tiếp kế thừa Record, ngầm final; dùng composition/interface hoặc normal class tùy mục tiêu.

### Bài tập E: Static field được không?

~~~java
record Item(String code) {
    private static int count;
}
~~~

**Đáp án:** Được. `count` là shared class state và không tham gia generated record equality.

### Bài tập F: Sealed interface với record có hợp lệ không?

~~~java
sealed interface State permits Ready {
}
record Ready(int code) implements State {
}
~~~

**Đáp án:** Có trong scope/file hợp lệ. Record implicitly final, thỏa loại permitted implementation của sealed interface.

### Bài tập G: Interface constants có làm record thêm instance fields?

~~~java
interface Flags {
    int MASK = 7;
}
record Value(int amount) implements Flags {
}
~~~

**Đáp án:** Không. `Flags.MASK` là static constant, không phải record component field.

### Bài tập H: Default method có sẵn dùng được không?

~~~java
interface NameView {
    String name();
    default String title() {
        return "Mr/Ms " + name();
    }
}
record Person(String name) implements NameView {
}
~~~

**Đáp án:** Có. Record generated `name()` và inherited default `title()` làm việc với nhau. Cần xem business-specific title rules trước khi áp dụng thực tế.

### Bài tập I: Nếu hai interfaces có default method trùng?

**Đáp án:** Record thường phải tự khai override đủ signature để giải quyết conflict. Trong override có thể gọi `A.super.method()` khi Java cho phép.

### Bài tập J: Một final field tham chiếu List có bảo đảm deep immutable?

**Đáp án:** Không. Hãy xác định mutable aliases và dùng `List.copyOf`/immutable elements hoặc defensive copy phù hợp.

## 44. Câu hỏi ôn tập nhanh và đáp án

**Câu 1.** Mỗi component record sinh field có access gì?  
**Đáp án:** `private final` và không static.

**Câu 2.** Có tự khai thêm non-static field trong body record không?  
**Đáp án:** Không; compile-time error.

**Câu 3.** Có static field trong record body không?  
**Đáp án:** Có.

**Câu 4.** Có instance initializer block không?  
**Đáp án:** Không.

**Câu 5.** Có static initializer block không?  
**Đáp án:** Có.

**Câu 6.** Muốn validate component values thì dùng gì?  
**Đáp án:** Canonical constructor, thường compact canonical constructor.

**Câu 7.** Record có thể extends `SomeClass` không?  
**Đáp án:** Không, record không có extends clause.

**Câu 8.** Direct superclass record là gì?  
**Đáp án:** `java.lang.Record`.

**Câu 9.** Record ngầm định `final` không?  
**Đáp án:** Có.

**Câu 10.** Có khai `abstract record` không?  
**Đáp án:** Không.

**Câu 11.** Có khai `sealed record` không?  
**Đáp án:** Không.

**Câu 12.** Record có thể implements sealed interface không?  
**Đáp án:** Có, nếu record là một permitted implementation.

**Câu 13.** Record có thể implements nhiều interfaces không?  
**Đáp án:** Có, nếu không có conflict không giải quyết được.

**Câu 14.** Generated accessor `value()` có thể implement interface `value()` không?  
**Đáp án:** Có khi method return type/signature tương thích.

**Câu 15.** Generated accessor `value()` có tự implement `getValue()` không?  
**Đáp án:** Không.

**Câu 16.** Record implements `Comparable` có `compareTo` generated không?  
**Đáp án:** Không; phải cung cấp implementation phù hợp.

**Câu 17.** Record implements interface default method có cần viết lại không?  
**Đáp án:** Không nếu không có conflict và default implementation phù hợp.

**Câu 18.** `A.super.method()` dùng khi nào?  
**Đáp án:** Có thể gọi một default method cụ thể trong override khi xử lý multiple-interface conflict.

**Câu 19.** Interface field `int X=1` có trở thành instance field trong record không?  
**Đáp án:** Không; đó là static constant thuộc interface.

**Câu 20.** Generated `equals` có xét static field không?  
**Đáp án:** Không; equality dựa record components.

**Câu 21.** Hai record types khác nhau nhưng implement cùng interface và cùng ID có mặc nhiên equal không?  
**Đáp án:** Không; generated record equality có type và components semantics.

**Câu 22.** Record có thể tự override `toString()` không?  
**Đáp án:** Có; giữ behavior/presentation đúng hợp đồng.

**Câu 23.** Record có thể khai abstract instance method để subclass override không?  
**Đáp án:** Không; record final và abstract method declaration bị cấm.

**Câu 24.** Mutable component trong record có thể bị mutate ngoài record không?  
**Đáp án:** Có nếu reference được chia sẻ và data type mutable.

**Câu 25.** Static field mutable làm record thread-safe tự động không?  
**Đáp án:** Không.

**Câu 26.** Nếu cần per-instance mutable cache, nên làm gì?  
**Đáp án:** Cân nhắc normal class hoặc thiết kế cache external; record cấm extra instance fields.

**Câu 27.** Member/local record có enclosing instance ngầm không?  
**Đáp án:** Không; chúng implicitly static.

**Câu 28.** Interface `Serializable` có được records tự động implement không?  
**Đáp án:** Không; phải khai nếu cần.

**Câu 29.** Có thể khai generic record `Box<T>` implement generic interface không?  
**Đáp án:** Có nếu type arguments/signatures hợp lệ.

**Câu 30.** Khác biệt lớn nhất giữa inheritance và implements với record?  
**Đáp án:** Record **không thể extends user class hoặc bị subclass**, nhưng **có thể implement interfaces để tham gia polymorphism**.

## 45. Checklist code review

- [ ] Header đã liệt kê đầy đủ instance state có ý nghĩa representation chưa?
- [ ] Body có non-static field declaration bất hợp lệ không?
- [ ] Có instance initializer block bị cấm không?
- [ ] Validation/normalization nằm trong canonical constructor thích hợp chưa?
- [ ] Static fields chỉ chứa shared metadata/state thực sự cần thiết?
- [ ] Static mutable state đã xử lý concurrency/lifecycle chưa?
- [ ] Không dùng `extends SomeBase` hoặc kế thừa từ record khác?
- [ ] Không khai `abstract`/`sealed`/`non-sealed` trên record?
- [ ] Có dùng interfaces để biểu diễn behavior chung thay class inheritance?
- [ ] Generated accessor signature có đúng với interface method không?
- [ ] Interface yêu cầu getter JavaBeans khác tên thì đã viết adapter method?
- [ ] Multiple default methods có xung đột chưa xử lý không?
- [ ] Comparable comparator có overflow/collision/consistency risk không?
- [ ] Sealed interface `permits` đã đúng Java 17 rules?
- [ ] Các component fields `private final` không bị giả định là deep immutable?
- [ ] List/array/custom mutable types có defensive-copy policy phù hợp?
- [ ] Generated equals/hashCode có tương thích với cách dùng Map/Set key?
- [ ] Có custom equals/hashCode/toString vi phạm contract không?
- [ ] Record có bị ép làm mutable entity với in-place setter semantics không?
- [ ] Nếu có per-instance cache/resource/lock, normal class có đúng hơn không?
- [ ] Member/local record có đang vô tình dùng enclosing instance `this` không?
- [ ] Serialization/framework use-case có hỗ trợ Java records đúng contract?
- [ ] Ví dụ đã compile trên JDK17 và stdout được đối chiếu chưa?

## 46. Tài liệu tham khảo

- Java Language Specification Java SE 17, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record là class đặc biệt, ngầm final, superclass `Record`, có thể implements interfaces.
- JLS Java SE 17, [`8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): record header/components, tên và kiểu.
- JLS Java SE 17, [`8.10.2 — Record Body Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.2): cấm non-static field declarations, instance initializers, abstract/native methods; cho static fields/initializers.
- JLS Java SE 17, [`8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): private final component fields, public accessors, generated Object methods.
- JLS Java SE 17, [`8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): canonical/compact/non-canonical constructors.
- JLS Java SE 17, [`8.1.2 — Generic Classes and Type Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.2): type parameters.
- JLS Java SE 17, [`8.1.5 — Superinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.5): implements interfaces.
- JLS Java SE 17, [`8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6): sealed interface implementation constraints.
- JLS Java SE 17, [`9.4.3 — Interface Method Body](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.4.3): default/static interface methods.
- Oracle Java 17 Language Guide, [Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): mô hình record, giới hạn, interface support.
- OpenJDK [JEP 395 — Records](https://openjdk.org/jeps/395): thiết kế value-oriented transparent carriers.
- Java API 17, [java.lang.Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): superclass.
- Java API 17, [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable copies.
- Java API 17, [Comparable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html): natural ordering contract.
- Java API 17, [Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): marker interface, không mặc định cho mọi record.

## Tổng kết

Record mô tả **một nhóm giá trị có tên** thông qua record header; những values ấy được compiler lưu bằng **private final instance component fields**. Chính vì representation phải minh bạch, record **không cho tự khai additional instance fields hoặc instance initializer blocks**. Bạn vẫn được có static fields/static initializer blocks và instance/static methods, nhưng static data không tự trở thành component hay tham gia component equality.

Về kế thừa, record **ngầm final**, trực tiếp kế thừa `java.lang.Record` và không có `extends` clause. Nó không thể kế thừa một user superclass, không thể bị subclass, không là abstract/sealed record. Khi cần code reuse/polymorphism, hãy chọn **implements interfaces**, default methods, sealed interface variants và **composition**.

Generated accessor như `name()` có thể tự thực hiện interface method có signature tương ứng; một method khác tên như `getName()`, `get()` hoặc `compareTo()` thường cần bạn viết tường minh. Cuối cùng, nhớ rằng **final component field không đồng nghĩa deep immutable data**: nếu component giữ mutable objects, chọn snapshot/defensive-copy theo hợp đồng.

Hiểu đúng ba ranh giới **record header quyết định instance state — record final giới hạn class inheritance — interfaces cung cấp behavior polymorphism** sẽ giúp dùng Java 17 records chính xác và tránh thiết kế mutable object sai mô hình.
