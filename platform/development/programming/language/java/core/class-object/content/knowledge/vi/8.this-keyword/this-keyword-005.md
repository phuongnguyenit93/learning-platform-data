# Phân biệt `this`, `this()` và tên lớp trong Java

Ba cách viết sau xuất hiện rất gần nhau trong Java nhưng **không thể hoán đổi cho nhau**:

~~~java
this.name = name;                 // this: object đang thực thi
this("DEFAULT", 1);               // this(...): gọi constructor khác của cùng class
Product.createdCount();           // Product: tên class để truy cập thành viên static
~~~

Dòng `this("DEFAULT", 1)` chỉ hợp lệ ở đúng vị trí của **constructor**; nó không phải lệnh có thể đặt tùy ý cạnh hai dòng còn lại. `Product` vừa là tên kiểu dữ liệu, vừa có thể là phần của những biểu thức như `new Product(...)`, `Product.createdCount()` hoặc `Product.class`. Việc cả ba cùng nhắc đến một class không có nghĩa chúng cùng chỉ một object.

Bài học tập trung vào **từ khóa `this`**, lời gọi constructor `this(...)`, và việc dùng **tên class** trong Java 17+. Bạn sẽ học cách nhận diện từng cú pháp, giải thích thứ tự khởi tạo, chọn cách viết đúng khi tên field trùng tên tham số, phân biệt static với instance, và tránh các lỗi như gọi `this()` trong method hoặc coi tên class là một tham chiếu object.

## 1. Bảng phân biệt ngay từ đầu

| Cách viết | Bản chất | Dùng ở đâu / để làm gì? |
| --- | --- | --- |
| `this` | Biểu thức tham chiếu đến **instance hiện tại** | Instance method, constructor và ngữ cảnh instance hợp lệ |
| `this.field` | Truy cập field của instance hiện tại | Phân biệt field với tham số hoặc local variable cùng tên |
| `this.method()` | Gọi instance method trên instance hiện tại | Làm receiver tường minh; `method()` thường tương đương nếu không có xung đột |
| `this(...)` | **Explicit constructor invocation** | Gọi constructor khác **cùng class**, trong constructor và theo quy tắc vị trí Java 17 |
| `ClassName` | Tên một **kiểu/class** | Khai báo kiểu, `new`, tên qualifier cho static member, class literal |
| `ClassName.staticField` | Truy cập field static | Dữ liệu gắn với class runtime, không gắn riêng từng instance |
| `ClassName.staticMethod()` | Gọi static method | Không cần tự tạo instance chỉ để gọi |
| `new ClassName(...)` | Biểu thức tạo instance | Cấp phát/khởi tạo object mới và cho ra reference khi thành công |
| `ClassName.class` | Class literal, nhận `Class<?>` tương ứng | Lấy thông tin kiểu; **không tạo instance** |
| `Outer.this` | Tham chiếu tới enclosing instance | Trong non-static inner class có enclosing instance phù hợp |
| `super.field` / `super.method()` | Truy cập thành viên superclass theo quy tắc Java | Không phải `this(...)`; dùng khi cần hành vi/thành viên kế thừa cụ thể |

**Quy tắc ghi nhớ:** `this` là **một reference expression**; `this(...)` là **lời gọi constructor đặc biệt**; `ClassName` là **một tên kiểu**. Muốn tạo object mới, thường cần một biểu thức như `new ClassName(...)`, không phải chỉ viết `ClassName`.

## 2. `this` là tham chiếu đến object đang thực thi

Trong instance method hoặc constructor, `this` biểu thị object đang là receiver của lời gọi tương ứng.

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void increment() {
        this.value++;
    }

    int current() {
        return this.value;
    }
}
~~~

Đây là **class minh họa**, chưa có `main`. Khi chạy:

~~~java
Counter first = new Counter(2);
Counter second = new Counter(5);
first.increment();
~~~

`this` trong constructor của `first` chỉ object `first`, còn `this` trong constructor của `second` chỉ object `second`. Khi `first.increment()` chạy, `this` chính là object `first` nên field của `second` không thay đổi. `this` không phải “biến toàn cục chứa object tạo đầu tiên” và không phải tên class.

### Từ `this` đến reference identity

Với instance method:

~~~java
boolean sameAs(Counter other) {
    return this == other;
}
~~~

Phép `==` trên reference so sánh **có cùng trỏ đến một object** hay không. `sameAs` có thể trả true khi `other` là alias của instance hiện tại, dù hai biến có tên khác nhau. `this` không phải một object mới: nó là tham chiếu đến object đã được dùng để gọi method.

Trong constructor, `this` chỉ object đang được khởi tạo, nhưng object ấy **có thể chưa hoàn tất trạng thái**, nên việc truyền `this` ra bên ngoài quá sớm có thể gây lỗi. Các ví dụ an toàn dưới đây chỉ dùng `this` để gán field hoặc gọi hành vi thích hợp.

## 3. Vì sao viết `this.field = field` trong constructor?

Một constructor thường đặt tên tham số giống field:

~~~java
class Student {
    private final String name;
    private int lessons;

    Student(String name, int lessons) {
        this.name = name;
        this.lessons = lessons;
    }
}
~~~

Trong constructor:

- `name` bên phải phép gán là **tham số** `String name`.
- `this.name` bên trái là **instance field** `name` của Student đang được tạo.
- Tương tự, `lessons` bên phải là tham số, `this.lessons` là field.
- Nếu viết `name = name;` thì cả hai tên không có qualifier đều chỉ tham số `name`, gây **tự gán tham số**. Field không được gán theo ý định.

Với field `final` như `name`, nếu constructor không gán field trong mọi đường hợp lệ, compiler có thể báo lỗi vì blank final field chưa được khởi tạo. Với field thường như `lessons`, việc bỏ qua phép gán có thể khiến field giữ giá trị mặc định `0` và tạo lỗi logic khó phát hiện.

### Không phải cứ đọc field đều cần `this`

Nếu method không có local variable hoặc parameter cùng tên:

~~~java
int currentLessons() {
    return lessons;
}
~~~

Tên đơn giản `lessons` đã phân giải được đến field, nên `return lessons;` và `return this.lessons;` tương đương về hành vi trong tình huống này. Dùng `this.` thường là **quy ước phong cách** ngoài các trường hợp cần phân biệt tên.

Nếu có tham số trùng field:

~~~java
void addLessons(int lessons) {
    this.lessons += lessons;
}
~~~

`this.lessons` mới là field; `lessons` là lượng tăng được truyền vào. Đây là trường hợp sử dụng `this.` đặc biệt hữu ích.

## 4. Chương trình đầu tiên: `this`, hai object và tên class

Tạo file **`ThisBasicsDemo.java`**:

~~~java
public class ThisBasicsDemo {
    static final class Counter {
        private static int createdCount = 0;

        private final String name;
        private int value;

        Counter(String name, int value) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }

            this.name = name;
            this.value = value;
            createdCount++;
        }

        void add(int value) {
            this.value += value;
        }

        String describe() {
            return this.name + "=" + this.value;
        }

        boolean sameInstance(Counter other) {
            return this == other;
        }

        static int totalCreated() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        Counter a = new Counter("A", 2);
        Counter b = new Counter("B", 5);
        Counter alias = a;

        a.add(3);
        b.add(1);

        System.out.println(a.describe());
        System.out.println(b.describe());
        System.out.println("alias same: " + a.sameInstance(alias));
        System.out.println("b same: " + a.sameInstance(b));
        System.out.println("created: " + Counter.totalCreated());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 ThisBasicsDemo.java
java ThisBasicsDemo
~~~

Stdout:

~~~text
A=5
B=6
alias same: true
b same: false
created: 2
~~~

**Phân tích kết quả:**

1. `new Counter("A", 2)` và `new Counter("B", 5)` tạo hai instance riêng. Bên trong mỗi constructor, `this.name`/`this.value` thuộc instance đang được tạo.
2. `Counter alias = a;` không có `new`; nó chỉ sao chép reference nên `a` và `alias` cùng trỏ đến một object.
3. Khi gọi `a.add(3)`, `this.value` là field của object A và tăng từ 2 lên 5. Khi gọi `b.add(1)`, object B tăng từ 5 lên 6.
4. `a.sameInstance(alias)` là true vì parameter `other` chứa reference tới cùng object. `a.sameInstance(b)` là false.
5. `createdCount` là field **static**; mỗi constructor tăng một lần, vì thế `Counter.totalCreated()` trả 2. Cú pháp `Counter.totalCreated()` sử dụng **tên class** để gọi static method, không cần `this`.

Trong ví dụ, `Counter` là static nested class nằm trong `ThisBasicsDemo`. Cú pháp khai báo nested này chỉ phục vụ chương trình một file; mỗi Counter instance vẫn có `name` và `value` riêng.

## 5. `this.method()` khác `this()` như thế nào?

Hai cú pháp chỉ hơn kém một dấu chấm nhưng thuộc hai nhóm hành vi hoàn toàn khác:

~~~java
this.reset();  // Gọi một instance method tên reset trên object hiện tại.
this();        // Gọi constructor không tham số của cùng class.
~~~

`this.reset()` là **lời gọi method thông thường**. Nó có thể nằm trong instance method, constructor hoặc biểu thức thích hợp khi có method `reset`. Khi gọi method này, nó **không khởi tạo object mới**.

`this()` là **explicit constructor invocation** tới constructor cùng class. Trong Java 17, nó chỉ hợp lệ **ở đầu thân một constructor**, không thể xuất hiện trong instance method, static method hay một block thông thường.

### Hai dòng tạo hiệu ứng khác nhau

~~~java
class Example {
    Example() {
        System.out.println("constructor");
    }

    void reset() {
        System.out.println("reset method");
    }

    void demo() {
        this.reset(); // Hợp lệ.
        // this();    // Sai: constructor invocation không ở trong constructor.
    }
}
~~~

Đây là **class minh họa**, không phải một chương trình độc lập. Nếu một caller tạo `Example e = new Example();`, constructor in `constructor`. Gọi `e.demo()` sẽ gọi `reset()` và in `reset method`, **không gọi lại constructor**.

**Không thể “chạy lại constructor” trên một object đã tồn tại bằng cách viết `this()` trong method.** Nếu cần thiết lập lại trạng thái sau khi object được tạo, hãy thiết kế một phương thức như `reset()` với hợp đồng rõ ràng hoặc tạo instance mới bằng `new`.

## 6. `this(...)` gọi constructor khác của chính class

Một class có thể có nhiều constructor với danh sách tham số khác nhau (**constructor overloading**). `this(...)` cho phép một constructor **ủy quyền** sang constructor khác của **cùng class**, giúp tập trung logic kiểm tra và gán field.

Ví dụ:

~~~java
class Ticket {
    private final String code;
    private final int quantity;

    Ticket() {
        this("STANDARD", 1);
    }

    Ticket(String code) {
        this(code, 1);
    }

    Ticket(String code, int quantity) {
        this.code = code;
        this.quantity = quantity;
    }
}
~~~

Đây là **class minh họa**; chưa có `main`, và class chưa kiểm tra đầu vào. Với `new Ticket()`, chuỗi constructor là:

~~~text
new Ticket()
    -> Ticket()
         -> this("STANDARD", 1)
              -> Ticket(String, int)
                   -> thiết lập field
         <- quay về Ticket()
    <- new trả reference đến MỘT object
~~~

`this(...)` **không tạo thêm Ticket object**. Mỗi lần gọi `new Ticket(...)` thành công chỉ tạo **một instance Ticket**, dù quá trình khởi tạo đi qua nhiều constructor của cùng class.

### Phân biệt rõ ba cách viết

- `new Ticket("VIP")`: **tạo** một Ticket instance, chạy chuỗi khởi tạo rồi trả reference khi thành công.
- `this("VIP")`: **ủy quyền** từ một constructor Ticket sang constructor Ticket khác trên **chính instance đang được tạo**.
- `Ticket("VIP")`: viết như một lời gọi function thông thường **không phải cú pháp gọi constructor của Java**. Constructor được gọi thông qua `new` hoặc explicit constructor invocation `this(...)`/`super(...)` theo ngữ cảnh.

Java không có “gọi constructor bằng tên class như một method” sau khi object đã tồn tại.

## 7. Ví dụ chạy: thứ tự constructor khi dùng `this(...)`

Tạo file **`ThisConstructorChainDemo.java`**:

~~~java
public class ThisConstructorChainDemo {
    static final class Ticket {
        private final String code;
        private final int quantity;

        Ticket() {
            this("STD");
            System.out.println("constructor 0");
        }

        Ticket(String code) {
            this(code, 1);
            System.out.println("constructor 1");
        }

        Ticket(String code, int quantity) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code required");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }

            this.code = code;
            this.quantity = quantity;
            System.out.println("constructor 2");
        }

        String describe() {
            return code + " x" + quantity;
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket();
        System.out.println(first.describe());

        Ticket second = new Ticket("VIP", 3);
        System.out.println(second.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThisConstructorChainDemo.java
java ThisConstructorChainDemo
~~~

Stdout:

~~~text
constructor 2
constructor 1
constructor 0
STD x1
constructor 2
VIP x3
~~~

Với `new Ticket()`:

1. `Ticket()` bắt đầu bằng `this("STD")`, chuyển sang constructor một tham số.
2. `Ticket(String)` bắt đầu bằng `this(code, 1)`, chuyển sang constructor hai tham số.
3. Constructor hai tham số validate, gán `this.code` và `this.quantity` rồi in `constructor 2`.
4. Quay về constructor một tham số, in `constructor 1`.
5. Quay về constructor không tham số, in `constructor 0`.
6. Chỉ sau khi cả chuỗi hoàn tất, biểu thức `new Ticket()` trả reference để `first` nhận.

Với `new Ticket("VIP", 3)`, chỉ constructor hai tham số của Ticket được chọn trực tiếp; không chạy constructor một tham số hoặc không tham số. Vì thế chỉ in `constructor 2`.

Chú ý: lời gọi `this(...)` ở đây còn dẫn đến quá trình khởi tạo superclass theo các quy tắc Java, nhưng chuỗi `this(...)` **không lặp việc chạy instance field initializer mỗi lần chuyển constructor**. Đó vẫn là một lần tạo instance.

## 8. Quy tắc vị trí của `this(...)` trong Java 17

Trong constructor của Java 17, **explicit constructor invocation `this(...)` hoặc `super(...)` phải là câu lệnh đầu tiên** nếu có mặt. Viết các statement thông thường trước lời gọi này sẽ gây lỗi biên dịch.

Ví dụ **cố ý sai**:

~~~java
class Invalid {
    Invalid() {
        System.out.println("before");
        this(1); // Lỗi trong Java 17: constructor invocation phải đứng đầu.
    }

    Invalid(int number) {
    }
}
~~~

Đoạn trên **không biên dịch** theo Java 17; không ghép nó vào chương trình chạy. Nếu cần truyền giá trị đã được kiểm tra/chuẩn hóa sang constructor chính, dùng **biểu thức đối số** hoặc helper static:

~~~java
class Valid {
    private final String name;

    Valid(String rawName) {
        this(normalize(rawName), 1);
    }

    Valid(String name, int version) {
        this.name = name;
    }

    private static String normalize(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name required");
        }
        return name.strip();
    }
}
~~~

Trong `Valid(String)`, `this(normalize(rawName), 1)` vẫn là statement đầu tiên. Phép gọi `normalize(rawName)` được đánh giá khi chuẩn bị đối số. Nếu helper ném exception, constructor đích không hoàn tất theo đường bình thường.

**Phạm vi phiên bản:** Đây là quy tắc cho **Java 17** theo bài học. Những phiên bản Java mới hơn có thể bổ sung cú pháp/khả năng của constructor bodies; khi học Java 17 hoặc biên dịch với `--release 17`, hãy giữ quy tắc first statement này.

### Không thể dùng `this` như receiver trước constructor chaining

Trong biểu thức đối số của lời gọi `this(...)` hoặc `super(...)` trong Java 17, không được tùy tiện tham chiếu instance đang chưa qua bước khởi tạo superclass, ví dụ dùng `this.name` làm argument từ chỗ explicit constructor invocation. Một helper **static** nhận tham số đầu vào thường phù hợp hơn. Điều này tránh việc dùng trạng thái instance trước khi quá trình khởi tạo đúng của Java diễn ra.

## 9. `this()` không cho phép chuỗi constructor vòng tròn

Vì `this(...)` ủy quyền qua các constructor, chuỗi lời gọi phải có điểm kết thúc. Ví dụ **sai**:

~~~java
class Loop {
    Loop() {
        this(1);
    }

    Loop(int value) {
        this();
    }
}
~~~

Java phát hiện **recursive constructor invocation** và từ chối biên dịch. Đây không phải cách hợp lệ để “lặp khởi tạo” cho đến khi đạt điều kiện nào đó. Một chuỗi constructor của một class cần cuối cùng đi tới constructor thực hiện việc khởi tạo cơ sở (và nối tới superclass thích hợp), thay vì quay về constructor đã gọi.

Một cách sửa:

~~~java
class NoLoop {
    private final int value;

    NoLoop() {
        this(1);
    }

    NoLoop(int value) {
        this.value = value;
    }
}
~~~

Ở đây constructor một tham số kết thúc chuỗi `this(...)` và gán field. Từ khóa `this` trong `this.value = value` là **biểu thức tham chiếu đến object**, không phải một lời gọi constructor khác.

## 10. `this(...)` và `super(...)`: cả hai là constructor invocation nhưng khác đích

Trong class kế thừa, cần phân biệt:

| Cú pháp | Đích | Ý nghĩa |
| --- | --- | --- |
| `this(...)` | Constructor khác của **cùng class** | Ủy quyền giữa các overload |
| `super(...)` | Constructor thích hợp của **superclass trực tiếp** | Khởi tạo phần trạng thái superclass của cùng object |
| `this.field` | Field trên instance hiện tại | Tham chiếu/gán state của chính object |
| `super.field` | Field của superclass theo quy tắc truy cập | Phân biệt khi subclass có field cùng tên |
| `this.method()` | Instance method qua receiver hiện tại | Tham gia dynamic dispatch nếu method override được |
| `super.method()` | Triển khai phương thức superclass thích hợp | Không phải gọi constructor |

Nếu constructor không viết explicit `this(...)` hoặc `super(...)`, compiler Java 17 thông thường thêm `super()` ngầm định. Superclass phải có constructor không tham số **có thể truy cập**; nếu không, phải viết `super(arguments)` thích hợp từ constructor của subclass.

### Ví dụ chạy kế thừa

Lưu file **`ThisVersusSuperDemo.java`**:

~~~java
public class ThisVersusSuperDemo {
    static class Device {
        private final String id;

        Device(String id) {
            this.id = id;
            System.out.println("Device constructor");
        }

        String id() {
            return id;
        }
    }

    static final class Phone extends Device {
        private final String model;

        Phone(String model) {
            this("PHONE-01", model);
            System.out.println("Phone one-arg");
        }

        Phone(String id, String model) {
            super(id);
            this.model = model;
            System.out.println("Phone two-arg");
        }

        String label() {
            return id() + " / " + this.model;
        }
    }

    public static void main(String[] args) {
        Phone phone = new Phone("Pixel");
        System.out.println(phone.label());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThisVersusSuperDemo.java
java ThisVersusSuperDemo
~~~

Stdout:

~~~text
Device constructor
Phone two-arg
Phone one-arg
PHONE-01 / Pixel
~~~

Trong lời gọi `new Phone("Pixel")`:

1. `Phone(String)` gọi `this("PHONE-01", model)` sang constructor hai tham số của **Phone**.
2. `Phone(String, String)` gọi `super(id)` sang constructor **Device**.
3. `Device` khởi tạo field `id` và in `Device constructor`.
4. Sau khi superclass constructor hoàn tất, `Phone` gán `this.model` và in `Phone two-arg`.
5. Quay về constructor `Phone(String)`, in `Phone one-arg`.
6. Toàn bộ chuỗi là khởi tạo **một object Phone**, không phải tạo riêng một Device rồi một Phone.

Constructor `Phone(String, String)` không thể có **hai explicit constructor invocation** `this(...)` và `super(...)` làm hai statement liên tiếp. Nó phải chọn đường khởi tạo phù hợp với quy tắc: gọi constructor cùng class **hoặc** gọi superclass từ constructor hiện tại.

## 11. Tên lớp `ClassName` làm gì, khác `this` ở đâu?

Tên class như `Counter`, `Student`, `Phone` chủ yếu chỉ **kiểu**, không chỉ object cụ thể nào.

Xét các cách viết:

~~~java
Counter counter;                    // Counter là kiểu của biến.
Counter a = new Counter("A", 1);    // new Counter(...) tạo object.
Counter b = a;                      // Chỉ sao chép reference, không tạo mới.
int total = Counter.totalCreated(); // Tên class gọi static method.
Class<?> kind = Counter.class;      // Class literal.
~~~

Đây là các **mảnh minh họa**, có thể đặt vào chương trình có class `Counter` phù hợp.

- `Counter` trong khai báo biến giúp compiler kiểm tra kiểu.
- `new Counter(...)` dùng tên class để xác định kiểu **sẽ được tạo**.
- `Counter.totalCreated()` dùng tên class làm qualifier cho một **static method**.
- `Counter.class` tạo/nhận tham chiếu tới `Class` object đại diện kiểu, **không tạo Counter instance**.
- `this` bên trong instance method của Counter mới chỉ **Counter cụ thể đang thực thi**, không phải toàn bộ class.

### Tên class không thay thế được receiver của instance method

Nếu `Counter` có method instance `describe()`, cú pháp sau sai:

~~~java
Counter.describe(); // Lỗi nếu describe() chỉ là instance method.
~~~

Phải có một receiver cụ thể:

~~~java
Counter c = new Counter("A", 1);
System.out.println(c.describe());
~~~

Compiler không thể đoán bạn muốn mô tả instance nào chỉ từ tên class. Ngược lại, static method đúng kiểu `Counter.totalCreated()` không yêu cầu chọn riêng một Counter instance.

## 12. `ClassName.staticMember` so với `this.member`

Một class có hai loại thành viên dữ liệu quan trọng:

~~~java
class Example {
    static int total;
    int value;
}
~~~

- `total` là **static field**, gắn với class runtime tương ứng.
- `value` là **instance field**, gắn với từng Example object.

Trong instance method có thể viết `Example.total` để truy cập static field, hoặc `this.value` để đọc instance field. Từ một static method, không có `this` nên muốn đọc một instance field cần có reference object.

### Ví dụ chạy phân biệt static và instance

Tạo file **`ClassNameAccessDemo.java`**:

~~~java
public class ClassNameAccessDemo {
    static final class Notebook {
        private static int nextId = 0;
        private final int id;

        Notebook() {
            this.id = ++Notebook.nextId;
        }

        int id() {
            return this.id;
        }

        static int totalCreated() {
            return Notebook.nextId;
        }
    }

    public static void main(String[] args) {
        Notebook first = new Notebook();
        Notebook second = new Notebook();

        System.out.println("first id=" + first.id());
        System.out.println("second id=" + second.id());
        System.out.println("total=" + Notebook.totalCreated());
        System.out.println("same class=" +
                (first.getClass() == Notebook.class));
        System.out.println("type=" + Notebook.class.getSimpleName());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ClassNameAccessDemo.java
java ClassNameAccessDemo
~~~

Stdout:

~~~text
first id=1
second id=2
total=2
same class=true
type=Notebook
~~~

Giải thích:

1. `Notebook.nextId` thuộc class runtime Notebook; mỗi lần constructor chạy tăng cùng một static field.
2. `this.id` trong constructor chỉ field instance của Notebook mới được tạo; first và second giữ giá trị id khác nhau.
3. `Notebook.totalCreated()` là static method gọi qua tên class.
4. `first.getClass()` trả runtime class của first. Vì first được tạo trực tiếp bằng `new Notebook()`, kết quả là chính `Notebook.class`.
5. `Notebook.class.getSimpleName()` cho `Notebook`, không tạo Notebook object nào.

**Lưu ý:** Class literal `Notebook.class` không đồng nghĩa `new Notebook()`. Nó cung cấp thông tin về kiểu. Việc dùng class literal tự nó không phải là lời gọi constructor của Notebook.

### Có thể gọi static member qua instance không?

Java cho phép một số cách truy cập static member qua biểu thức reference như `instance.staticMethod()`, nhưng đó là phong cách **nên tránh** vì khiến người đọc tưởng method gắn với instance. Hãy ưu tiên `ClassName.staticMethod()`. Đặc biệt không dùng `this.staticMethod()` như một cách giả tạo để diễn đạt “method thuộc object”.

Trong instance context, viết trực tiếp `staticField` có thể hợp lệ nếu tên được phân giải rõ; `ClassName.staticField` thường biểu đạt sở hữu tốt hơn.

## 13. Static context không có `this`

Không thể dùng biểu thức `this` trong một static method:

~~~java
class Wrong {
    private int value;

    static void show() {
        // System.out.println(this.value); // Lỗi biên dịch.
    }
}
~~~

Vì static method gắn với class, lúc gọi `Wrong.show()` không cần tồn tại một Wrong instance để cung cấp receiver `this`. Tương tự, static initializer block không có `this` của một instance.

### Sửa bằng cách nhận tham chiếu object

~~~java
class Correct {
    private final int value;

    Correct(int value) {
        this.value = value;
    }

    static void show(Correct target) {
        System.out.println(target.value);
    }
}
~~~

Trong `Correct.show(target)`, target là **tham số tham chiếu**; có thể đọc field trên object được truyền vào theo quyền truy cập của class. `target` không phải `this` ẩn của static method.

### Không nhầm static nested class với inner class

Một **static nested class** không có enclosing instance tự động. Bên trong instance method của chính static nested class, `this` vẫn chỉ **nested class object hiện tại**. Nhưng nó không được dùng `Outer.this` vì không có outer instance đi kèm theo cách của **non-static inner class**.

Điều này quan trọng khi tách code từ non-static inner class thành static nested class: một số biểu thức `Outer.this` trước đây hợp lệ sẽ không còn hợp lệ.

## 14. `Outer.this`: khi có object của class bao ngoài

Với **non-static inner class**, Java có khái niệm enclosing instance. Khi một outer class và inner class có field cùng tên, `this.field` trong inner class là field inner object; `Outer.this.field` là field của enclosing outer object.

Lưu **`OuterThisDemo.java`**:

~~~java
public class OuterThisDemo {
    private final String label = "outer";

    class Inner {
        private final String label = "inner";

        void display(String label) {
            System.out.println("parameter=" + label);
            System.out.println("inner=" + this.label);
            System.out.println("outer=" + OuterThisDemo.this.label);
        }
    }

    public static void main(String[] args) {
        OuterThisDemo outer = new OuterThisDemo();
        OuterThisDemo.Inner inner = outer.new Inner();
        inner.display("argument");
    }
}
~~~

~~~bash
javac -encoding UTF-8 OuterThisDemo.java
java OuterThisDemo
~~~

Stdout:

~~~text
parameter=argument
inner=inner
outer=outer
~~~

Trong `display(String label)`, tên đơn giản `label` biểu thị **tham số**, `this.label` biểu thị **field của Inner**, còn `OuterThisDemo.this.label` biểu thị **field của outer instance**.

Phân biệt hai cách tạo:

- `new OuterThisDemo()`: tạo outer object.
- `outer.new Inner()`: tạo một inner object **gắn với outer object cụ thể**.
- `OuterThisDemo.this`: tham chiếu tới outer instance **khi đang ở một ngữ cảnh inner phù hợp**; đây không phải toán tử tạo object mới.

Viết `OuterThisDemo.this` trong static `main` ở ngoài ngữ cảnh enclosing instance không hợp lệ. Phải đặt biểu thức đó ở vùng có enclosing instance tương ứng.

## 15. `this` trong lambda và anonymous class không giống nhau

Đây là một trường hợp nâng cao nhưng hữu ích khi đọc code có callback.

- Trong **lambda expression**, `this` biểu thị instance của **enclosing context** thích hợp; lambda không tạo ra một `this` riêng kiểu anonymous class.
- Trong thân **anonymous class**, `this` biểu thị **instance anonymous class**. Nếu cần outer instance, dùng `OuterClass.this` theo ngữ cảnh hợp lệ.
- Trong static context, viết `this` trong lambda cũng không hợp lệ nếu không có instance context để tham chiếu.

Lưu file **`LambdaAndAnonymousThisDemo.java`**:

~~~java
public class LambdaAndAnonymousThisDemo {
    private final String label = "outer";

    Runnable createLambda() {
        return () -> System.out.println("lambda=" + this.label);
    }

    Runnable createAnonymous() {
        return new Runnable() {
            private final String label = "anonymous";

            @Override
            public void run() {
                System.out.println("anonymous=" + this.label);
                System.out.println("enclosing=" +
                        LambdaAndAnonymousThisDemo.this.label);
            }
        };
    }

    public static void main(String[] args) {
        LambdaAndAnonymousThisDemo demo =
                new LambdaAndAnonymousThisDemo();

        demo.createLambda().run();
        demo.createAnonymous().run();
    }
}
~~~

~~~bash
javac -encoding UTF-8 LambdaAndAnonymousThisDemo.java
java LambdaAndAnonymousThisDemo
~~~

Stdout:

~~~text
lambda=outer
anonymous=anonymous
enclosing=outer
~~~

Điều cần nhớ không phải là “lambda luôn tạo một object độc lập có field giống outer”, mà là **ngữ nghĩa của `this` trong lambda theo lexical context**. Anonymous class có một instance riêng và có thể có field riêng; vì vậy cần `Outer.this` khi muốn truy cập enclosing object.

## 16. `this` có thể được trả về để tạo fluent API

Đôi khi một instance method muốn cho caller gọi liên tiếp các hành vi trên **cùng object**. Method có thể trả `this`:

~~~java
class BuilderLike {
    private int count;

    BuilderLike add(int amount) {
        this.count += amount;
        return this;
    }
}
~~~

Trả `this` không tạo bản sao object. Đây là **cùng tham chiếu** mà instance method đang xử lý. Nó có thể hỗ trợ method chaining:

~~~java
BuilderLike item = new BuilderLike();
item.add(1).add(2).add(3);
~~~

### Chương trình chạy độc lập

Tạo file **`ReturnThisDemo.java`**:

~~~java
public class ReturnThisDemo {
    static final class Basket {
        private int items;

        Basket add(int count) {
            if (count <= 0) {
                throw new IllegalArgumentException("count must be positive");
            }

            this.items += count;
            return this;
        }

        int totalItems() {
            return this.items;
        }
    }

    public static void main(String[] args) {
        Basket basket = new Basket();
        Basket returned = basket.add(2).add(3);

        System.out.println("items=" + basket.totalItems());
        System.out.println("same=" + (basket == returned));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReturnThisDemo.java
java ReturnThisDemo
~~~

Stdout:

~~~text
items=5
same=true
~~~

Ở đây `basket.add(2)` sửa object thành 2 items và trả reference tới chính nó. Phương thức `add(3)` tiếp tục chạy trên cùng object, tổng thành 5. `returned` và `basket` cùng trỏ đến một Basket nên `==` là true.

**Nhược điểm cần đánh giá:** Method chaining này thao tác **mutable object**. Đừng nhầm với những API kiểu `withX(...)` có thể trả bản sao immutable. Hành vi sửa object hay tạo object mới phải được API nêu rõ, không thể suy ra chỉ từ dấu chấm trong chuỗi lời gọi.

## 17. Constructor không thể `return this`

Vì constructor không khai báo kiểu trả về, đoạn sau là **sai**:

~~~java
class InvalidConstructor {
    InvalidConstructor() {
        return this; // Lỗi: constructor không trả object.
    }
}
~~~

Một constructor có thể dùng `return;` không kèm giá trị trong những điều kiện ngôn ngữ cho phép, nhưng không thể trả tham chiếu `this` bằng cú pháp `return this;`.

Nếu cần một API tạo object có tên rõ ràng, dùng **static factory method**:

~~~java
class Widget {
    private final String name;

    private Widget(String name) {
        this.name = name;
    }

    static Widget named(String name) {
        return new Widget(name);
    }
}
~~~

`Widget.named("A")` là một **static method** và có thể dùng `return new Widget(name);`. Biểu thức `new` tạo object; constructor khởi tạo object; factory method trả tham chiếu. Ba thao tác khác nhau này rất dễ nhầm khi mới học.

Một constructor gọi `this(...)` cũng không có nghĩa nó “trả this”. Nó chỉ **ủy quyền** trong quá trình khởi tạo, còn kết quả thành công của `new` là reference đến object.

## 18. `ClassName.class` và `this.getClass()`: kiểu tĩnh và kiểu runtime

`ClassName.class` là một **class literal**, cung cấp đối tượng `Class` đại diện cho kiểu được chỉ định. `this.getClass()` gọi method trên **object hiện tại** và trả runtime class của object đó.

Với kế thừa, hai biểu thức có thể cho hai kiểu khác nhau nếu `this` mang runtime type là subclass:

~~~java
class Animal {
    Class<?> declaredType() {
        return Animal.class;
    }

    Class<?> runtimeType() {
        return this.getClass();
    }
}

class Dog extends Animal {}
~~~

Đây là hai class minh họa. Nếu có `Animal dog = new Dog();`, thì `dog.declaredType()` trả `Animal.class`, còn `dog.runtimeType()` trả `Dog.class`. Mã method `runtimeType()` được kế thừa nhưng `this` ở runtime là chính Dog object.

**Không nhầm class literal với object identity:** `Dog.class` đại diện cho một class runtime tương ứng, không phải một Dog instance; so sánh `dog.getClass() == Dog.class` nói về **kiểu runtime** của object, không nói hai Dog object có phải một.

## 19. `this`, `super` và phương thức override

`this.method()` thường tuân theo cơ chế **dynamic dispatch** của instance method: nếu object runtime là subclass có override tương ứng, phiên bản subclass được gọi. `super.method()` cho phép subclass gọi một triển khai thích hợp từ superclass trong ngữ cảnh được phép.

Lưu **`ThisAndSuperMethodDemo.java`**:

~~~java
public class ThisAndSuperMethodDemo {
    static class Parent {
        String describe() {
            return "parent";
        }
    }

    static final class Child extends Parent {
        @Override
        String describe() {
            return "child";
        }

        String show() {
            return this.describe() + " / " + super.describe();
        }
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child child = new Child();

        System.out.println(parentView.describe());
        System.out.println(child.show());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ThisAndSuperMethodDemo.java
java ThisAndSuperMethodDemo
~~~

Stdout:

~~~text
child
child / parent
~~~

`parentView` có kiểu khai báo `Parent` nhưng tham chiếu tới Child object; lời gọi `describe()` được dispatch đến `Child.describe()`. Trong `Child.show()`, `this.describe()` là method của Child, còn `super.describe()` gọi phiên bản Parent.

Chú ý `super.method()` không có nghĩa tạo object superclass mới, và `super(...)` trong constructor cũng không tạo object superclass độc lập. Cả hai thuộc ngữ cảnh của **cùng instance đang được xử lý hoặc khởi tạo**.

## 20. Phân biệt tên class, constructor, method và method reference

Những cú pháp sau giống nhau bề ngoài nhưng khác bản chất:

| Cú pháp | Diễn giải |
| --- | --- |
| `new Student("Mai")` | Tạo instance mới, gọi constructor được chọn |
| `Student("Mai")` | Không phải cú pháp constructor invocation thông thường nếu không có `new` |
| `this("Mai")` | Gọi constructor khác của Student, chỉ trong constructor Student và theo quy tắc Java 17 |
| `this.setName("Mai")` | Gọi instance method `setName` trên object hiện tại |
| `Student.create("Mai")` | Gọi static method `create` nếu method ấy được định nghĩa |
| `Student.class` | Class literal, không tạo Student |
| `Student::new` | **Constructor reference** dùng trong ngữ cảnh functional interface phù hợp |
| `this::setName` | Method reference tới instance method `setName` của object hiện tại |
| `Student::staticMethod` | Method reference tới static method, nếu tồn tại |

### Constructor reference không phải `this()`

Một ví dụ đơn giản về `ClassName::new`:

~~~java
java.util.function.Supplier<StringBuilder> factory =
        StringBuilder::new;
StringBuilder text = factory.get();
~~~

Đây là mảnh mã minh họa. `StringBuilder::new` là constructor reference, nghĩa là một functional operation sẽ tạo StringBuilder khi được gọi thích hợp. Lệnh `factory.get()` kích hoạt việc tạo object. Nó khác hoàn toàn với `this()`, vốn chỉ dùng để ủy quyền constructor của cùng object đang được khởi tạo.

### Instance method reference dùng `this`

~~~java
class Printer {
    void print() {
        System.out.println("printed");
    }

    Runnable action() {
        return this::print;
    }
}
~~~

Đây là class minh họa. `this::print` tạo một bound method reference trỏ tới method trên **instance Printer hiện tại**. Nó không gọi `print()` ngay tại thời điểm tạo reference; method có thể chạy về sau khi `Runnable.run()` được gọi.

## 21. Lỗi phổ biến và thông báo compiler

| Sai lầm | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| `this()` trong instance method | Constructor invocation chỉ hợp lệ trong constructor ở vị trí quy định | Dùng instance method như `reset()` |
| Statement đứng trước `this(...)` trong Java 17 | Explicit constructor invocation phải đứng đầu thân constructor | Đưa xử lý vào helper static/đối số hoặc constructor đích |
| Hai constructor gọi `this(...)` qua lại vô hạn | Recursive constructor invocation không hợp lệ | Có một constructor đích thật sự khởi tạo |
| `this.field` trong static method | Không có receiver instance `this` | Nhận object làm tham số hoặc gọi instance method từ object |
| `ClassName.instanceMethod()` | Chưa có object receiver cho instance method | `object.instanceMethod()` |
| `ClassName(...)` để tạo object | Thiếu biểu thức `new` hoặc không thuộc cú pháp constructor chaining | `new ClassName(...)` |
| `name = name;` trong constructor | Tham số che khuất field, dẫn đến tự gán tham số | `this.name = name;` |
| `return this;` trong constructor | Constructor không trả giá trị | Để `new` trả reference, hoặc dùng factory method |
| `this(...)` gọi constructor nhưng tưởng tạo thêm object | Chuỗi constructor dùng **cùng instance** | Đếm số biểu thức `new` được thực thi thành công |
| `ClassName.class` tưởng đã tạo instance | Class literal chỉ chỉ định kiểu | Dùng `new ClassName(...)` khi muốn object |
| Dùng `Outer.this` trong static nested class | Static nested class không có enclosing instance tự động | Truyền reference outer tường minh nếu cần |
| Dùng `this` trong lambda viết ở static context | Không có enclosing instance thích hợp | Dùng object receiver hoặc đổi ngữ cảnh |
| Gọi method override được trong constructor và đọc field subclass | Subclass có thể chưa khởi tạo field | Tránh dynamic dispatch trong giai đoạn khởi tạo |
| Dùng `this.staticMethod()` để thể hiện hành vi của object | Static method thuộc class, không gắn riêng instance | `ClassName.staticMethod()` |
| Nhầm `this` với biến mang tên class | `this` là reference expression, class name là type name | Xác định kiểu và receiver ở mỗi chỗ |

**Ví dụ lỗi compiler cố ý (không ghép vào chương trình chạy):**

~~~java
class InvalidCases {
    private int value;

    InvalidCases() {
        // System.out.println("before");
        // this(1); // Nếu cả hai dòng hoạt động: sai thứ tự Java 17.
    }

    InvalidCases(int value) {
        this.value = value;
    }

    static void staticMethod() {
        // System.out.println(this.value); // Sai: this trong static context.
    }

    void instanceMethod() {
        // this(); // Sai: không được gọi constructor từ method.
    }
}
~~~

Trong ví dụ này, các dòng sai được comment để class vẫn minh họa được bộ khung hợp lệ. Khi muốn kiểm tra thông báo lỗi, hãy bỏ comment **từng trường hợp một**, không mở tất cả cùng lúc rồi khó phân biệt nguồn lỗi.

## 22. Quy tắc chọn cú pháp theo ý định

Trước mỗi dòng code có `this` hoặc tên class, hãy tự hỏi mình muốn làm gì:

1. **Sửa field của object hiện tại** → `this.field = value`.
2. **Gọi hành vi trên object hiện tại** → `this.method()` hoặc `method()` khi không có xung đột tên.
3. **Ủy quyền khởi tạo tới constructor khác cùng class** → `this(arguments);` tại đầu constructor trong Java 17.
4. **Khởi tạo phần superclass** → `super(arguments);` trong constructor thích hợp, không dùng `new Parent()` thay thế.
5. **Tạo một object hoàn toàn mới** → `new ClassName(arguments)`.
6. **Dùng một object đã có** → biến reference như `student`, `account` hoặc `this` khi hợp lệ.
7. **Đọc/gọi thành viên static** → `ClassName.member`.
8. **Lấy thông tin kiểu** → `ClassName.class` hoặc `object.getClass()`, hiểu rõ static type khác runtime class.
9. **Tham chiếu tới enclosing instance** → `Outer.this` trong non-static inner class phù hợp.
10. **Truyền hàm tạo object dưới dạng functional value** → `ClassName::new` khi có target functional interface phù hợp.

Sắp xếp theo ý định trước rồi chọn cú pháp giúp tránh việc dùng `this()` chỉ vì thấy nó giống `this.method()`.

## 23. Bài tập tự thực hành

### Bài A — Sửa lỗi tự gán tham số

Cho class:

~~~java
class User {
    String name;

    User(String name) {
        name = name;
    }
}
~~~

Tạo `new User("Mai")` rồi dự đoán field `name`: nó giữ **null** vì tham số tự gán cho chính mình, còn field không nhận giá trị. Sửa thành `this.name = name;` và giải thích vì sao field giờ là `"Mai"`.

### Bài B — Vẽ chuỗi constructor

Với `ThisConstructorChainDemo`, vẽ sơ đồ `new Ticket()`, ba constructor được gọi, và thứ tự log. Thay `new Ticket()` bằng `new Ticket("PREMIUM")`, dự đoán các dòng:

~~~text
constructor 2
constructor 1
PREMIUM x1
~~~

Constructor không tham số không tham gia ở lời gọi thứ hai. Giải thích vì sao số object mới vẫn là một.

### Bài C — Static hay instance?

Dựa trên `ClassNameAccessDemo`:

~~~java
Notebook first = new Notebook();
Notebook second = new Notebook();
~~~

Hãy chỉ ra `Notebook.nextId` thuộc class, còn `first.id` và `second.id` thuộc hai object. Vì field `id` là private, muốn đọc từ `main` phải dùng accessor `id()` đã có; không tự ý sửa access modifier để bỏ lỗi.

### Bài D — Chọn `this` hay `this()`

Xét mục tiêu:
- Gán field `price` từ tham số `price` → viết `this.price = price;`.
- Constructor một tham số dùng giá trị mặc định cho tham số thứ hai → `this(value, defaultValue);`.
- Method `reset()` muốn xóa số lượng của object hiện tại → viết một instance method thao tác trên `this.quantity`; không gọi `this()`.
- Tạo một object khác có cùng dữ liệu → `new Product(...)`; không coi `this(...)` là phép clone.

### Bài E — Outer instance

Trong `OuterThisDemo`, đổi tham số `display(String label)` từ `"argument"` thành `"from caller"`. Dự đoán chỉ dòng `parameter=...` thay đổi, còn `inner=inner` và `outer=outer` vẫn như cũ. Phân biệt field của inner, field của outer và biến tham số.

### Bài F — Lambda và anonymous

Thử giải thích vì sao `this.label` trong `createLambda()` là `"outer"`, nhưng `this.label` trong phương thức `run()` của anonymous class là `"anonymous"`. Dùng `LambdaAndAnonymousThisDemo.this.label` để đọc field outer từ anonymous class.

### Bài G — Fluent method

Với `ReturnThisDemo`, gọi `Basket other = basket.add(1);`. Dự đoán `other == basket` là true. Sau đó tự thiết kế một method kiểu `Basket copy()` tạo object khác nếu cần; so sánh identity giữa copy và basket để chứng minh `return this` khác với `return new Basket(...)`.

## 24. Checklist hoàn thành

- [ ] Tôi nói rõ `this` là tham chiếu đến **instance hiện tại** trong ngữ cảnh instance hợp lệ.
- [ ] Tôi biết `this.field` giải quyết tham số hoặc local variable che khuất field.
- [ ] Tôi phân biệt `this.method()` với `this(...)` chỉ bằng cú pháp và mục đích.
- [ ] Tôi biết `this(...)` là constructor chaining của **cùng class**, không tạo thêm object.
- [ ] Tôi tuân thủ quy tắc explicit constructor invocation ở đầu constructor trong Java 17.
- [ ] Tôi nhận diện được vòng constructor chaining sai.
- [ ] Tôi phân biệt `this(...)` với `super(...)` và `super.method()`.
- [ ] Tôi biết một constructor không thể trả `this` bằng `return this;`.
- [ ] Tôi biết class name là **tên kiểu**, còn `new ClassName(...)` mới biểu thị tạo instance.
- [ ] Tôi truy cập static member bằng `ClassName.member` thay vì phụ thuộc receiver instance.
- [ ] Tôi biết static method không có `this`.
- [ ] Tôi biết `ClassName.class` không tạo instance và `object.getClass()` biểu diễn runtime class.
- [ ] Tôi phân biệt `this` trong non-static inner class, lambda và anonymous class.
- [ ] Tôi biết `this::method` và `ClassName::new` là method/constructor references, không phải constructor chaining.
- [ ] Tôi dự đoán được stdout của các ví dụ Java 17+ trong bài và chỉ ra số instance thực sự được tạo.

**Kết luận:** `this` trả lời câu hỏi **“object nào đang thực hiện hành vi này?”**; `this(...)` trả lời **“constructor nào của cùng class sẽ tiếp tục khởi tạo object hiện tại?”**; còn `ClassName` trả lời **“kiểu/class nào đang được nhắc tới?”**. Với quy tắc đó, bạn sẽ đọc chính xác phép gán field, constructor overloading, kế thừa, static member và những cú pháp tạo object trong Java mà không nhầm tham chiếu object với tên lớp.
