# Thành viên thuộc lớp và thành viên thuộc từng đối tượng trong Java

Trong Java, một class có thể khai báo **thành viên thuộc lớp** (*class members*, thường gắn với từ khóa `static`) và **thành viên thuộc từng đối tượng** (*instance members*, không có `static`). Hai nhóm này khác nhau ở **đối tượng sở hữu trạng thái, thời điểm sử dụng, cách gọi method và hành vi khi có nhiều instance**.

Một instance field như `account.balance` thuộc về một đối tượng tài khoản cụ thể; mỗi `new Account(...)` có giá trị `balance` riêng. Ngược lại, một static field như `Account.createdCount` biểu diễn một giá trị được gắn với class ở runtime và được những instance của class đó cùng quan sát trong một ngữ cảnh class loading tương ứng.

**Quy tắc nền tảng:**

- `static` field: trạng thái **gắn với class**, không tạo một bản riêng cho mỗi object.
- Instance field: trạng thái **gắn với một object**, mỗi object có các field instance riêng.
- `static` method: được gọi qua **tên class** và không có receiver `this` ngầm định.
- Instance method: được gọi trên **một object** và có thể sử dụng `this` để đọc/ghi trạng thái của object hiện tại.
- Một static method vẫn có thể làm việc với object thông qua **tham số hoặc tham chiếu tường minh**; “static” không có nghĩa là không thể đụng tới đối tượng nào.
- Static state được chia sẻ **theo class thực tế và phạm vi class loader liên quan**, không có nghĩa là một biến chung tuyệt đối giữa mọi tiến trình Java.

Bài học áp dụng cho **Java 17+**, tập trung vào field/method, khởi tạo, truy cập, kế thừa, thiết kế API, bộ nhớ và concurrency. Các chương trình đầy đủ có tên tệp, lệnh `javac`/`java` và stdout đáng tin để tự kiểm tra.

## 1. Class, object và hai loại thành viên

Khi khai báo:

~~~java
class Student {
    static String schoolName = "Java Academy";
    String name;
    int grade;
}
~~~

Ta có:

- `schoolName` là **static field**: thông tin chung được đặt trên class `Student`.
- `name` và `grade` là **instance fields**: giá trị thuộc từng instance `Student`.

Đây là đoạn khai báo class, chưa có method `main` chạy độc lập.

Trong một method:

~~~java
Student first = new Student();
Student second = new Student();

first.name = "Lan";
first.grade = 9;

second.name = "Mai";
second.grade = 8;

System.out.println(Student.schoolName);
~~~

`first` và `second` trỏ tới **hai object khác nhau**, nên sửa `first.grade` không tự sửa `second.grade`. Nhưng cả hai object thuộc cùng class `Student` được mã nguồn này sử dụng, và thông tin chung `Student.schoolName` không bị tạo thành hai bản riêng cho hai object.

Sơ đồ ý niệm:

~~~text
Class Student
  static schoolName = "Java Academy"
             |
             | dùng chung theo class
             |
      +------+------+
      |             |
      v             v
Student A       Student B
name = "Lan"    name = "Mai"
grade = 9       grade = 8
~~~

Sơ đồ thể hiện **quan hệ sở hữu logic**, không phải địa chỉ bộ nhớ vật lý hay cách JVM bắt buộc sắp xếp object. Mọi static field không nhất thiết “nằm ở Method Area” theo cách một hình minh họa đơn giản; vị trí bộ nhớ cụ thể là chi tiết thực thi JVM.

## 2. Bảng so sánh nhanh: static và instance

| Tiêu chí | Thành viên `static` | Thành viên instance |
| --- | --- | --- |
| Khai báo field | `static int total;` | `int value;` |
| Mức sở hữu logic | Class tại runtime | Mỗi object |
| Số bản field khi tạo nhiều object | Một trạng thái của class theo bối cảnh class loading | Một bản trong mỗi object |
| Cách truy cập nên dùng | `ClassName.field`, `ClassName.method()` | `object.field`, `object.method()` |
| Cần object để gọi method? | Không | Có receiver object thông thường |
| Có `this` trong method? | Không | Có trong instance context |
| Có thể đọc instance field trực tiếp không? | Không, phải có object/receiver | Có thể dùng `this.field` |
| Có thể đọc static field? | Có | Có, dù nên chỉ rõ `ClassName.field` |
| Có polymorphic overriding? | Static methods bị **hiding**, không override | Instance methods phù hợp có thể override |
| Khởi tạo field | Khi class/interface được khởi tạo theo quy tắc liên quan | Khi mỗi object được khởi tạo |
| Rủi ro state chung | Shared mutable state, race, coupling | Object mutable vẫn có thể bị nhiều thread chia sẻ |

Một nhận xét chính xác hơn “static chỉ có một bản trong JVM”: **một class có thể được định nghĩa/khởi tạo trong các phạm vi class loader khác nhau**, mỗi runtime class tương ứng có static state riêng. Trong chương trình Java Core đơn giản với một class loader, thường quan sát một bộ static fields cho class ấy.

## 3. Static field: dữ liệu dùng chung thuộc class

Ví dụ bộ đếm số object tạo ra:

~~~java
class Order {
    private static int createdCount;

    private final String orderId;

    Order(String orderId) {
        this.orderId = orderId;
        createdCount++;
    }

    static int getCreatedCount() {
        return createdCount;
    }

    String getOrderId() {
        return orderId;
    }
}
~~~

`createdCount` không thuộc riêng một `Order` nào. Khi nhiều lời gọi constructor thành công và thực hiện `createdCount++`, chúng cùng cập nhật một static field.

`orderId` là instance field `final`: một order có ID riêng, không tự động trùng với order khác. `final` chỉ ngăn gán lại field tham chiếu theo quy tắc Java; **nó không thay đổi ý nghĩa instance**.

### 3.1. Truy cập qua tên class, không cần tạo instance

~~~java
System.out.println(Order.getCreatedCount());
~~~

Lời gọi static method qua `Order` không cần `new Order(...)`. Đây là code fragment trong method.

Một vài thành viên static quen thuộc trong JDK:

- `Math.max(a, b)` là static method tính giá trị.
- `Integer.parseInt("42")` là static method chuyển chuỗi.
- `System.out` là static field, giá trị tham chiếu tới một đối tượng `PrintStream`.
- `Collections.emptyList()` là static factory method trong utility class.
- `LocalDate.now()` là static factory method tạo/nhận một giá trị ngày.

Các method static không bắt buộc chỉ là toán học thuần túy; chúng có thể tạo object, đọc dữ liệu hệ thống hoặc thực hiện tác động khác theo hợp đồng. `static` nói về receiver/class membership, **không bảo đảm method là pure hoặc không side effect**.

### 3.2. Static field không phải “số bản sao bằng số object”

~~~java
class Flag {
    static boolean enabled = true;
}

Flag a = new Flag();
Flag b = new Flag();

Flag.enabled = false;
~~~

Sau phép gán, cả code làm việc với `a` và `b` đều có thể quan sát `Flag.enabled == false` trong cùng runtime class. Không có hai giá trị `enabled` tách biệt chỉ vì có hai object.

## 4. Instance field: dữ liệu thuộc từng object

~~~java
class Counter {
    private int value;

    void increment() {
        this.value++;
    }

    int current() {
        return this.value;
    }
}
~~~

Ví dụ fragment:

~~~java
Counter a = new Counter();
Counter b = new Counter();

a.increment();
a.increment();
b.increment();

System.out.println(a.current()); // 2
System.out.println(b.current()); // 1
~~~

Hai biến tham chiếu đến hai Counter objects nên có state riêng. Trong `a.increment()`, `this` là instance `a`; trong `b.increment()`, `this` là instance `b`.

**Quan trọng:** nếu viết `Counter alias = a;` rồi gọi `alias.increment()`, giá trị của `a.current()` cũng tăng, bởi `alias` và `a` trỏ tới **cùng object**. Instance state độc lập **giữa các object**, không phải giữa các biến tham chiếu.

### 4.1. Static field và instance field có thể cùng tên không?

Trong **cùng một class**, không thể khai báo hai field cùng tên chỉ khác `static`:

~~~java
class Wrong {
    static int value;

    // int value; // Lỗi compile: field cùng tên đã được khai báo
}
~~~

Một field không có hai “phiên bản” static và instance dựa theo cách truy cập. Các class khác nhau có thể khai báo field cùng tên; trong kế thừa, field hiding có những quy tắc riêng, nhưng không nên tận dụng nó chỉ để khiến state khó hiểu.

## 5. Ví dụ hoàn chỉnh: static dùng chung, instance độc lập

Tạo tệp **`StaticAndInstanceDemo.java`**:

~~~java
public class StaticAndInstanceDemo {
    static final class Ticket {
        private static int issuedCount;
        private static String prefix = "T";

        private final int number;
        private int usedCount;

        Ticket() {
            number = ++issuedCount;
        }

        void use() {
            this.usedCount++;
        }

        String description() {
            return prefix + number + "/used=" + usedCount;
        }

        static int totalIssued() {
            return issuedCount;
        }

        static void setPrefix(String nextPrefix) {
            if (nextPrefix == null || nextPrefix.isBlank()) {
                throw new IllegalArgumentException(
                        "Prefix không hợp lệ");
            }
            prefix = nextPrefix;
        }
    }

    public static void main(String[] args) {
        System.out.println("Initial issued = " + Ticket.totalIssued());

        Ticket first = new Ticket();
        Ticket second = new Ticket();

        first.use();
        first.use();
        second.use();

        System.out.println("First = " + first.description());
        System.out.println("Second = " + second.description());
        System.out.println("Total issued = " + Ticket.totalIssued());

        Ticket alias = first;
        alias.use();

        System.out.println("Same object = " + (alias == first));
        System.out.println("After alias = " + first.description());

        Ticket.setPrefix("X");

        System.out.println("First renamed = " + first.description());
        System.out.println("Second renamed = " + second.description());
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 StaticAndInstanceDemo.java
java StaticAndInstanceDemo
~~~

**Stdout chính xác:**

~~~text
Initial issued = 0
First = T1/used=2
Second = T2/used=1
Total issued = 2
Same object = true
After alias = T1/used=3
First renamed = X1/used=3
Second renamed = X2/used=1
~~~

Phân tích:

1. `Ticket.totalIssued()` là static method. Nó đọc `issuedCount` ban đầu bằng 0 **mà không cần tạo Ticket instance**.
2. Mỗi lần gọi constructor `Ticket()` thực hiện `++issuedCount` trên cùng static field. `first.number` nhận 1, `second.number` nhận 2. Hai instance fields `number` thuộc riêng mỗi object.
3. `first.use()` hai lần chỉ sửa `first.usedCount`, còn `second.use()` một lần chỉ sửa `second.usedCount`.
4. `Ticket.totalIssued()` trả 2 vì đã tạo hai Ticket objects qua constructor.
5. `alias = first` sao chép tham chiếu. `alias.use()` sửa chính object của `first`, nên số lần dùng của first tăng lên 3. Điều này là **aliasing của instance object**, không liên quan đến static.
6. `Ticket.setPrefix("X")` thay một static field chung. Cả hai object giờ định dạng nhãn với `X`, nhưng instance numbers và used counts của chúng vẫn độc lập.
7. Không có setter instance nào được gọi để thay prefix của từng Ticket: thay đổi shared state phát huy khi method `description()` đọc lại `prefix`.

**Giới hạn thực tế:** `issuedCount++` không an toàn khi nhiều thread đồng thời tạo Ticket. Chương trình này minh họa đơn luồng. Nếu ID phải duy nhất trong môi trường đồng thời, cần giải pháp atomic/synchronization hoặc cơ chế cấp ID phù hợp hơn.

## 6. Static method không có `this`

Một **instance method** được gọi trên một receiver:

~~~java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    String greeting() {
        return "Chào " + this.name;
    }
}
~~~

`this` trong `greeting()` đại diện cho object nhận lời gọi. Ngược lại, static method không được gọi trên một current instance mặc định:

~~~java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    static String normalize(String rawName) {
        // return this.name; // Lỗi compile: this trong static context
        return rawName.trim();
    }
}
~~~

`normalize` là static, nên không có `this`. Nó vẫn có thể thao tác với một String object thông qua tham số `rawName`. `rawName.trim()` gọi instance method của String trên receiver tường minh `rawName`, **không phải trên `this` của Person**.

### 6.1. Static method vẫn có thể truy cập instance members qua một object cụ thể

~~~java
class Employee {
    private final String name;

    Employee(String name) {
        this.name = name;
    }

    static String display(Employee employee) {
        return employee.name;
    }
}
~~~

Đây là đoạn khai báo. `display(Employee employee)` là static method nhưng dùng **tham chiếu parameter** `employee` làm receiver để đọc instance field. Vì code được khai báo trong `Employee`, nó có quyền đọc private field của một Employee object theo quy tắc access control.

**Không đúng** khi nói “static method không được đọc instance field trong mọi trường hợp”. Cách nói chính xác là **static method không thể dùng instance field mà không có receiver phù hợp**, và không thể dùng `this` vì không có current instance.

### 6.2. Instance method có thể sử dụng static members

~~~java
class Device {
    private static String manufacturer = "ACME";
    private final String serial;

    Device(String serial) {
        this.serial = serial;
    }

    String label() {
        return manufacturer + ":" + serial;
    }
}
~~~

`label()` là instance method, đọc static field `manufacturer` và instance field `serial`. Không có trở ngại ngôn ngữ nào cho việc phối hợp cả hai, miễn visibility và các điều kiện khác thỏa mãn.

Dù trong cùng class có thể bỏ tiền tố cho static field, với code dễ bảo trì nên cân nhắc viết `Device.manufacturer` thay vì `this.manufacturer` để người đọc nhận ra state gắn với class.

## 7. Truy cập static member qua tên class, không qua instance

Java **cho phép** nhiều lời gọi static thông qua một biểu thức object:

~~~java
class Example {
    static int count;

    static void report() {
        System.out.println(count);
    }
}

Example e = new Example();
e.report(); // Biên dịch được nhưng không nên dùng
~~~

Fragment minh họa này hợp lệ trong nhiều trường hợp, nhưng compiler/IDE thường cảnh báo rằng static method nên được gọi qua tên class:

~~~java
Example.report();
~~~

Tại sao?

- `Example.report()` nói rõ method thuộc class.
- `e.report()` dễ khiến người đọc nghĩ lời gọi phụ thuộc instance `e` hoặc có dynamic dispatch.
- Static method **không thực hiện polymorphic instance overriding** như instance method.
- Truy cập static thông qua biểu thức có thể liên quan đến **việc đánh giá biểu thức bên trái**; không nên dùng để suy ra một instance thật được method xử lý.

### 7.1. Trường hợp dễ nhầm: static call qua biến `null`

Ví dụ:

~~~java
class Utility {
    static String answer() {
        return "OK";
    }
}

Utility ref = null;
System.out.println(ref.answer()); // OK
~~~

Đây là code fragment. Lời gọi `ref.answer()` có thể biên dịch và in `OK` vì `answer` là static method; bản thân nó **không dereference một Utility object như instance method**. Nếu receiver expression chỉ là biến `ref` thì biểu thức đó được đánh giá nhưng không yêu cầu object non-null để thực thi static method.

Tuy nhiên, **đừng dùng `ref.answer()` để giảng rằng null an toàn khi gọi method**. Với instance method, `ref.instanceMethod()` sẽ gây `NullPointerException`. Ngay cả đối với static call, một biểu thức phức tạp ở bên trái dấu chấm vẫn có thể có side effect hoặc ném exception khi được đánh giá. Viết `Utility.answer()` là cách chuẩn và rõ hơn.

## 8. Thời điểm khởi tạo static state và instance state

Một câu hỏi thường gặp: “Static field được tạo lúc nào, còn instance field lúc nào?”

Ở mức khái niệm Java:

- **Class initialization** thực hiện các phép gán tĩnh và static initializer blocks theo quy tắc ngôn ngữ khi class được khởi tạo; không đồng nghĩa “mọi class có trên classpath đều chạy initializer ngay khi JVM bật”.
- **Instance initialization** diễn ra cho **mỗi object** được tạo bình thường bằng `new`, theo chuỗi constructor và initializer tương ứng.
- Trước initializer thích hợp, field có **giá trị mặc định** của kiểu (`0`, `false`, `null`...).
- Khi superclass và subclass có initializer, có quy tắc khởi tạo của từng loại và thứ tự constructor superclass/subclass; không nên suy luận chỉ từ thứ tự các file source.

### 8.1. Static field initializer và static initialization block

~~~java
class Configuration {
    static int timeoutSeconds = 10;

    static {
        timeoutSeconds += 5;
    }
}
~~~

Khi `Configuration` được khởi tạo theo quy tắc Java, field initializer đặt `timeoutSeconds` thành 10 rồi static initializer cộng 5; giá trị cuối là 15. Phần static initialization **không chạy lại cho mỗi `new Configuration()`** trong một class được khởi tạo bình thường.

### 8.2. Instance field initializer và instance initialization block

~~~java
class Session {
    int retries = 3;

    {
        retries += 1;
    }

    Session(int retries) {
        this.retries = retries;
    }
}
~~~

Khi `new Session(7)` khởi tạo thành công, instance initializer đặt `retries` thành 4 rồi constructor body gán 7. Khi tạo object khác, instance initializer thực hiện lại cho object mới. Đó là quy tắc **per-instance**, khác static initialization.

## 9. Chương trình chạy được: static initializer chỉ chạy một lần, instance initializer chạy mỗi object

Lưu tệp **`InitializationDemo.java`**:

~~~java
public class InitializationDemo {
    static final class Member {
        private static int createdCount;

        static {
            System.out.println("Static init");
        }

        private final int id;

        {
            System.out.println("Instance init");
        }

        Member() {
            id = ++createdCount;
            System.out.println("Constructor " + id);
        }

        static int created() {
            return createdCount;
        }

        int id() {
            return id;
        }
    }

    public static void main(String[] args) {
        System.out.println("Before first access");
        System.out.println("Count = " + Member.created());

        Member first = new Member();
        Member second = new Member();

        System.out.println("IDs = "
                + first.id() + "," + second.id());
        System.out.println("Final count = " + Member.created());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 InitializationDemo.java
java InitializationDemo
~~~

**Stdout chính xác:**

~~~text
Before first access
Static init
Count = 0
Instance init
Constructor 1
Instance init
Constructor 2
IDs = 1,2
Final count = 2
~~~

Phân tích:

1. Trước lời gọi `Member.created()`, chương trình in `Before first access`.
2. Lời gọi static method `Member.created()` là một trường hợp **active use** dẫn đến khởi tạo class Member nếu chưa khởi tạo; static initializer in `Static init` đúng một lần cho runtime class đó.
3. `Member.created()` trả 0 vì chưa có Member object nào được tạo.
4. Với mỗi `new Member()`, instance initializer in `Instance init`, sau đó constructor tăng static `createdCount` và in số thứ tự object.
5. Tạo hai Member objects khiến instance initializer chạy hai lần; static initializer không chạy lại.
6. `id` là final instance field, mỗi object giữ id 1 hoặc 2; `createdCount` là static field chung với giá trị 2.

Chú ý: `Member.createdCount++` dùng trong ví dụ **không phù hợp với tạo object đồng thời không có synchronization**. Bài chỉ quan sát vòng đời khởi tạo trong chương trình đơn luồng.

### 9.1. Static initialization và “khởi tạo một lần” cần hiểu chính xác

Một runtime class được JVM quản lý trong một ngữ cảnh class loader tương ứng; quá trình class initialization được phối hợp theo quy tắc JVM. Không nên diễn giải “một lần” thành “một lần cho mọi class loader, mọi JVM process hoặc mọi lần chạy ứng dụng”.

Nếu class initialization thất bại, những lần sử dụng sau có thể gặp lỗi liên quan đến class initialization (ví dụ `ExceptionInInitializerError` và lỗi sử dụng lớp ở trạng thái khởi tạo thất bại); **không** mặc nhiên nghĩ JVM sẽ thử chạy static initializer lại cho đến khi thành công.

## 10. `static final`: constant và shared reference

Modifier `static` cho biết member gắn với class; `final` có quy tắc riêng về khả năng gán lại.

~~~java
class Limits {
    public static final int MAX_ITEMS = 100;
    public static final String DEFAULT_LABEL = "general";
}
~~~

Những giá trị primitive hoặc String đáp ứng điều kiện **constant variable** của Java có thể là **compile-time constants**. Việc tham chiếu tới chúng từ class khác có thể được compiler inline giá trị, ảnh hưởng class initialization và binary compatibility khi thay đổi thư viện.

### 10.1. Static final reference không có nghĩa object bất biến

~~~java
import java.util.ArrayList;
import java.util.List;

class SharedCatalog {
    static final List<String> ITEMS = new ArrayList<>();
}
~~~

`ITEMS` là một **static final reference**: không thể gán lại field `ITEMS` thông thường sau khi được khởi tạo, nhưng `ITEMS.add("A")` vẫn có thể sửa **List object dùng chung** nếu mutable.

So sánh:

~~~java
class Constants {
    static final java.util.List<String> DEFAULT_TAGS =
            java.util.List.of("JAVA", "CORE");
}
~~~

`List.of(...)` tạo một List không sửa được qua API; kết hợp với các phần tử String immutable, đây là shared constant-style value phù hợp hơn. Tuy nhiên, các kiểu phần tử mutable vẫn cần xem xét khả năng thay đổi sâu.

**`static final` có hai phần độc lập:**
- `static`: field gắn với class.
- `final`: hạn chế gán lại field tham chiếu/giá trị sau khi khởi tạo theo quy tắc Java.

### 10.2. Quy ước tên và thiết kế constant

`UPPER_SNAKE_CASE` thường dùng cho các constant fields thực sự ổn định, ví dụ `MAX_RETRIES`. Không phải mọi static field đều là constant; `static int counter` đang thay đổi không nhất thiết nên đặt tên toàn chữ hoa.

Static mutable fields công khai thường gây **global coupling**. Ưu tiên `private static`, API có kiểm soát hoặc injection của dependency tùy nhu cầu.

## 11. Static method và instance method trong kế thừa

Đây là khác biệt quan trọng:

- **Instance methods** có thể được **override**, và Java chọn implementation tương ứng với runtime object khi áp dụng dynamic dispatch.
- **Static methods** được **hidden** (che khuất) bởi static method cùng chữ ký thích hợp trong subclass, **không override** theo polymorphism thông thường.
- Gọi static method qua một biến tham chiếu có thể hợp lệ nhưng method được chọn dựa trên **compile-time type** của biểu thức, không theo runtime class của object.
- `@Override` không dùng để đánh dấu static method hiding.

### 11.1. Chương trình chạy được: overriding khác static method hiding

Tạo tệp **`StaticHidingDemo.java`**:

~~~java
public class StaticHidingDemo {
    static class Parent {
        static String category() {
            return "Parent-static";
        }

        String label() {
            return "Parent-instance";
        }
    }

    static final class Child extends Parent {
        static String category() {
            return "Child-static";
        }

        @Override
        String label() {
            return "Child-instance";
        }
    }

    public static void main(String[] args) {
        Parent parent = new Parent();
        Parent polymorphic = new Child();
        Child child = new Child();

        System.out.println("Parent class = " + Parent.category());
        System.out.println("Child class = " + Child.category());

        System.out.println("Parent ref static = "
                + polymorphic.category());
        System.out.println("Child ref static = " + child.category());

        System.out.println("Parent instance = " + parent.label());
        System.out.println("Polymorphic instance = "
                + polymorphic.label());
        System.out.println("Child instance = " + child.label());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StaticHidingDemo.java
java StaticHidingDemo
~~~

**Stdout chính xác:**

~~~text
Parent class = Parent-static
Child class = Child-static
Parent ref static = Parent-static
Child ref static = Child-static
Parent instance = Parent-instance
Polymorphic instance = Child-instance
Child instance = Child-instance
~~~

Giải thích:

1. `Parent.category()` và `Child.category()` là static methods; chúng thuộc hai class tương ứng và Child che khuất static method cùng chữ ký của Parent.
2. `polymorphic` có **kiểu khai báo `Parent`** nhưng trỏ tới một object `Child`. `polymorphic.category()` vẫn chọn **Parent.category()** theo compile-time type Parent. Viết qua object như vậy được phép nhưng khó đọc; trong API thật nên dùng `Parent.category()`.
3. `child.category()` chọn Child.category() vì compile-time type Child.
4. `polymorphic.label()` là **instance method call**. Vì runtime receiver là Child, dynamic dispatch chọn `Child.label()`, in `Child-instance`.
5. Cặp kết quả `Parent ref static = Parent-static` và `Polymorphic instance = Child-instance` cùng trên biến `polymorphic` chứng minh khác biệt giữa **static hiding** và **instance overriding**.

### 11.2. Một static method không override instance method cùng chữ ký

Các trường hợp sau gây lỗi biên dịch nếu khai báo để cố thay đổi tính static/instance trên đường override:

~~~java
class Parent {
    void run() {
    }
}

class Child extends Parent {
    // static void run() {} // Không thể hide instance method
}
~~~

Ngược lại, không thể dùng instance method để override static method phù hợp từ superclass. Static/instance membership không phải một thuộc tính có thể tự do đổi khi kế thừa một method cùng chữ ký.

## 12. Static fields trong kế thừa: đừng mặc định subclass có “bản sao riêng”

Giả sử:

~~~java
class Base {
    static int total;
}

class Derived extends Base {
}
~~~

Vì Derived không khai báo field mới cùng tên, tham chiếu `Derived.total` (nếu quyền truy cập cho phép) thực tế liên quan đến static field được **khai báo trong Base**. Không có một bản `total` tự động được nhân bản chỉ bởi `extends Base`.

Nếu Derived **tự khai báo** một static field `total` khác, sẽ có hai field khác nhau theo cơ chế field hiding:

~~~java
class Base {
    static int total = 10;
}

class Derived extends Base {
    static int total = 20;
}
~~~

Khi truy cập `Base.total` nhận 10 và `Derived.total` nhận 20. Đây là **hai khai báo** riêng chứ không phải hai bản per-object.

Tránh cố tình hide static fields trùng tên nếu không có lý do rõ ràng: code thông qua các kiểu tĩnh khác nhau có thể nhìn thấy những trường riêng, gây nhầm với instance state hoặc inheritance.

## 13. Static nested class vẫn có instance của chính nó

Một **static nested class** là member type gắn với enclosing class về mặt khai báo; nhưng mỗi object được tạo từ static nested class vẫn có **instance fields của chính object đó**.

~~~java
class Container {
    private static int created;

    static class Item {
        private final int id;

        Item() {
            this.id = ++created;
        }

        int id() {
            return id;
        }
    }
}
~~~

Dù `Item` là **static nested class**, `id` của `Item` là **instance field**, và mỗi `new Container.Item()` có `id` riêng. `Container.created` là static field của Container được các Item constructors cập nhật.

Cú pháp:

~~~java
Container.Item a = new Container.Item();
Container.Item b = new Container.Item();
~~~

Không cần tạo `Container outer = new Container()` để tạo một instance `Item`, vì static nested class không giữ **enclosing Container instance ngầm định** như non-static inner class.

### 13.1. Khác non-static inner class

~~~java
class House {
    private String address;

    House(String address) {
        this.address = address;
    }

    class Room {
        String where() {
            return House.this.address;
        }
    }
}
~~~

Tạo non-static inner instance từ một outer instance:

~~~java
House house = new House("Hà Nội");
House.Room room = house.new Room();
~~~

`House.this` bên trong Room trỏ tới enclosing `House` object. `static nested class` không tự có outer `this` như vậy.

### 13.2. Static nested class có thể khai báo static lẫn instance members

~~~java
class Outer {
    static class Nested {
        static int shared;
        int own;

        static void resetShared() {
            shared = 0;
        }

        void increaseOwn() {
            own++;
        }
    }
}
~~~

Modifier `static` trên nested class **không biến mọi field và method của nó thành static**. Phải xem modifier của từng member.

## 14. Static trong interface, enum và top-level class

### 14.1. Interface có static fields và static methods theo quy tắc riêng

~~~java
interface Settings {
    int MAX_RETRIES = 3; // public static final ngầm định

    static boolean validRetryCount(int n) {
        return n >= 0 && n <= MAX_RETRIES;
    }
}
~~~

Trong interface, field `MAX_RETRIES` được ngầm định là `public static final`. Static method của interface `Settings.validRetryCount(2)` được gọi qua tên interface phù hợp; không được kế thừa thành instance method của implementing class theo cách một default method có thể cung cấp.

Interface cũng có default/abstract instance methods tùy khai báo. **Không phải mọi method của interface đều static** chỉ vì interface fields mặc định static.

### 14.2. Enum constants là instances, enum vẫn có static members

~~~java
enum Direction {
    NORTH, SOUTH;

    static boolean opposite(Direction a, Direction b) {
        return (a == NORTH && b == SOUTH)
                || (a == SOUTH && b == NORTH);
    }
}
~~~

`NORTH` và `SOUTH` là các enum constants — mỗi cái là một instance của enum type; `opposite` là static method gắn với enum class. Mô hình static-vs-instance vẫn áp dụng, dù enum có cơ chế tạo instance đặc biệt.

### 14.3. Không khai báo top-level class bằng từ khóa `static`

~~~java
// static class Utility {} // Không hợp lệ ở top level
~~~

`static` được phép với **member nested class** trong ngữ cảnh hợp lệ, không phải top-level class. Một top-level class có thể chứa static fields/methods, nhưng chính khai báo top-level class không được thêm `static`.

## 15. Static utility methods, factories và khi nào nên dùng instance method

### 15.1. Utility method độc lập với trạng thái object

Một phép tính chỉ phụ thuộc đối số thường phù hợp là static method:

~~~java
final class NumberRules {
    private NumberRules() {
        // Không cho tạo instance chỉ để gọi utility methods.
    }

    static boolean isPositive(int n) {
        return n > 0;
    }

    static int safeSum(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

`NumberRules.isPositive(3)` không cần object `NumberRules` vì phép kiểm tra không dựa trên instance state. `private` constructor ngăn tạo object thông thường từ code ngoài class, thể hiện ý định utility.

Nhưng **không phải** method nào không tham chiếu field hiện tại cũng bắt buộc là static. Có thể chọn instance method vì nó là hành vi trong interface, cần polymorphism/test doubles hoặc gắn với một object service có dependencies.

### 15.2. Static factory tạo và trả object

~~~java
class User {
    private final String username;

    private User(String username) {
        this.username = username;
    }

    static User of(String username) {
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("username rỗng");
        }
        return new User(username);
    }

    String username() {
        return username;
    }
}
~~~

`User.of(...)` là static method, nhưng **nó hoàn toàn có thể tạo một instance User** và trả tham chiếu tới instance đó. Static không có nghĩa “không liên quan object”; nó có nghĩa lời gọi factory không cần một User receiver đã tồn tại.

Static factory có thể đặt tên ý nghĩa như `of`, `from` hoặc `create`; điều kiện validate vẫn cần được bảo vệ.

### 15.3. Instance behavior khi phụ thuộc state hiện tại

~~~java
class PriceTag {
    private final long unitPrice;

    PriceTag(long unitPrice) {
        this.unitPrice = unitPrice;
    }

    long priceFor(int quantity) {
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

`priceFor` dựa trên `unitPrice` của một object cụ thể, nên là instance method tự nhiên. Nếu viết thành static, bạn phải truyền `unitPrice` (hoặc cả object) vào method một cách tường minh; việc đó có thể phù hợp ở utility API nhưng không nhất thiết rõ bằng hành vi trên chính `PriceTag`.

## 16. Static state không thay thế dependency injection

Một cách làm dễ tạo coupling là dùng static mutable field như nơi chứa cấu hình/đối tượng service toàn cục:

~~~java
class GlobalConfig {
    static String endpoint = "https://example.invalid";
}
~~~

Code ở nhiều nơi đọc/ghi `GlobalConfig.endpoint` sẽ phụ thuộc vào một **shared mutable global state**. Điều này dễ làm test ảnh hưởng lẫn nhau, thứ tự chạy test quyết định kết quả, và nhiều thành phần không thể dùng cấu hình độc lập.

Một lựa chọn khi cần nhiều cấu hình khác nhau:

~~~java
class ApiClient {
    private final String endpoint;

    ApiClient(String endpoint) {
        this.endpoint = java.util.Objects.requireNonNull(endpoint);
    }

    String endpoint() {
        return endpoint;
    }
}
~~~

Mỗi `ApiClient` instance nắm giữ state riêng; test có thể tạo nhiều client với endpoints khác nhau. Một static factory có thể hỗ trợ tạo ApiClient, nhưng shared static mutable dependency không phải mặc định bắt buộc.

**Khi nên dùng static shared state?** Khi dữ liệu thực sự là thuộc tính chung của class và có một vòng đời/chính sách đồng bộ rõ ràng: số liệu thống kê, cache có kiểm soát, immutable constant, factory/registry được thiết kế cẩn thận.

**Khi không nên?** Khi dữ liệu mô tả mỗi user/request/session/order, có nhiều cấu hình độc lập, hoặc cần cách ly giữa test và thành phần ứng dụng. Những dữ liệu đó thường phù hợp với instance state hoặc context rõ ràng.

## 17. Concurrency: nhiều instance vẫn cùng sửa một static field

Một trong những rủi ro lớn của mutable static fields là **chia sẻ trên nhiều thread**.

~~~java
class UnsafeStats {
    static int requests;

    static void record() {
        requests++;
    }
}
~~~

Nếu nhiều thread gọi `UnsafeStats.record()`, biểu thức `requests++` gồm các bước đọc/tính/ghi, **không nguyên tử**, nên có thể bị **lost updates**. `static` không tự cung cấp lock.

### 17.1. Dùng AtomicInteger cho shared counter

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class Stats {
    private static final AtomicInteger REQUESTS =
            new AtomicInteger();

    static int recordRequest() {
        return REQUESTS.incrementAndGet();
    }

    static int totalRequests() {
        return REQUESTS.get();
    }
}
~~~

`AtomicInteger` hỗ trợ thao tác tăng nguyên tử trên một giá trị được chia sẻ. `REQUESTS` là static final reference đến AtomicInteger object, nhưng **nội dung của AtomicInteger vẫn thay đổi có kiểm soát**.

Nếu count chỉ dùng cho quan sát hệ thống rất đông thread, có thể cân nhắc `LongAdder`; nếu cần snapshot hoàn toàn nhất quán giữa nhiều field, atomic counter đơn lẻ không đủ.

### 17.2. Instance field cũng có thể bị race

~~~java
class UnsafeAccount {
    private long balance;

    void add(long amount) {
        balance += amount;
    }
}
~~~

Nếu **hai thread chia sẻ cùng một instance** `UnsafeAccount`, instance field `balance` vẫn có race. `instance` không đồng nghĩa thread-safe; nó chỉ cho phép **các object khác nhau giữ state khác nhau** khi không có tham chiếu dùng chung.

### 17.3. `volatile` không biến counter thành atomic

~~~java
class Stats {
    static volatile int count;

    static void increment() {
        count++; // Vẫn không atomic
    }
}
~~~

`volatile` mang ngữ nghĩa visibility và ordering theo Java Memory Model, không tự biến chuỗi read-modify-write thành một thao tác nguyên tử. Chọn atomic variable, synchronized/lock hoặc thiết kế immutable phù hợp với hợp đồng.

## 18. Class initialization và concurrency

JVM phối hợp **class initialization** để các thread không tùy ý thực hiện lại static initializer đồng thời như những constructor độc lập. Nhưng điều đó **không bảo đảm mọi cập nhật static field sau khi class khởi tạo sẽ thread-safe**.

Ví dụ:

~~~java
class Settings {
    static final java.util.Map<String, String> FLAGS =
            java.util.Map.of("mode", "safe");
}
~~~

Static initialization tạo và gán shared reference tới immutable map. Việc chia sẻ constant-style state kiểu này dễ suy luận hơn static mutable HashMap bị nhiều thread cập nhật.

Ngược lại:

~~~java
class Cache {
    static final java.util.Map<String, String> DATA =
            new java.util.HashMap<>();
}
~~~

`DATA` là static final reference nhưng HashMap object vẫn mutable. Các thread dùng chung HashMap không có synchronization tương ứng có thể gặp race và lỗi logic. Nếu cần concurrent map, cân nhắc `ConcurrentHashMap` cùng các operation thread-safe cần thiết, hoặc mô hình immutable snapshots.

## 19. Static field và garbage collection

Một static field tham chiếu tới object có thể góp phần **giữ object còn reachable** trong khi class/static field tương ứng còn có thể truy cập được:

~~~java
class Holder {
    static Object current;
}
~~~

Nếu code viết `Holder.current = new Object();`, object mới được static field giữ tham chiếu. Nếu thay bằng `Holder.current = null;`, ta chỉ **gỡ một đường tham chiếu**. Object có thể còn những đường tham chiếu khác; Java không cam kết thu gom ngay.

Những hệ quả thường gặp:

- Một static collection tích lũy object không giới hạn có thể gây memory leak về mặt logic dù garbage collector đang hoạt động chính xác.
- Đăng ký listener hoặc cache bằng static fields có thể giữ object sống lâu hơn dự kiến.
- Static singleton/service có lifecycle cần quản lý resource riêng; garbage collection không tự đóng file/socket/database connection khi bạn không thiết kế cleanup phù hợp.
- Class unloading/class loader lifecycle trong môi trường plugin/container có thể bị ảnh hưởng bởi những tham chiếu còn tồn tại. Đây là vấn đề nâng cao, không nên đồng nhất với phạm vi “một static field duy nhất toàn JVM”.

Một instance field cũng có thể giữ object reachable, nhưng vòng đời của nó gắn với **object sở hữu field** và toàn bộ chuỗi tham chiếu tương ứng. Với static field, việc chia sẻ rộng khiến ta cần chú ý khả năng giữ dữ liệu lâu dài.

## 20. Static method trong `main` và vì sao entry point thường static

Trong chương trình Java phổ thông:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
~~~

`main` là static để Java launcher có thể gọi entry point theo hợp đồng mà không cần khởi tạo `Hello` instance trước. Điều đó không có nghĩa ứng dụng phải viết mọi method thành static:

~~~java
public class Hello {
    private final String audience;

    Hello(String audience) {
        this.audience = audience;
    }

    void greet() {
        System.out.println("Chào " + audience);
    }

    public static void main(String[] args) {
        Hello hello = new Hello("Java");
        hello.greet();
    }
}
~~~

Trong `main`, code tạo một instance `Hello` rồi gọi instance method `greet()` trên object đó. Phần static entry point chỉ là **điểm khởi động**, không thay thế design hướng đối tượng.

## 21. Một số bẫy phổ biến về static

### 21.1. Dùng static field cho dữ liệu của từng người dùng

~~~java
class WrongSession {
    static String currentUsername;
}
~~~

Nếu chương trình có nhiều phiên/người dùng, field static làm dữ liệu dùng chung và có thể bị ghi đè bởi session khác. Một session nên có instance field:

~~~java
class UserSession {
    private final String username;

    UserSession(String username) {
        this.username = username;
    }
}
~~~

Mỗi `UserSession` object mang username của nó, tránh gom tất cả users vào cùng một field.

### 21.2. Nhầm `static final` với deep immutability

`static final List<Item>` ngăn gán lại field reference, nhưng không ngăn thay đổi `Item` objects nếu chúng mutable. Cần thiết kế phần tử và collection theo hợp đồng bất biến mong muốn.

### 21.3. Dùng `this` trong static context

~~~java
class Wrong {
    int value;

    static int read() {
        // return this.value; // Không có this
        return 0;
    }
}
~~~

Method static cần nhận một object hoặc có state static để thao tác; không có implicit receiver.

### 21.4. Nghĩ constructor chạy một lần vì class đã khởi tạo

Static initialization thường một lần cho runtime class, nhưng **constructor body chạy cho mỗi object** được tạo bình thường qua constructor invocation thích hợp. Static field chung không “ngăn” các objects mới tồn tại.

### 21.5. Nghĩ static fields thuộc riêng mỗi subclass

Nếu subclass kế thừa một static field khai báo trong superclass mà không khai báo field mới, không có “bản static field tự động” riêng cho subclass. Chỉ có hai field nếu có hai **khai báo** khác nhau theo quy tắc field hiding.

### 21.6. Nghĩ static methods được override

Static methods bị hiding, không có dynamic dispatch theo runtime object như instance methods. `Parent ref = new Child(); ref.staticMethod();` được phân giải từ compile-time type của `ref`, dù cách viết qua instance không được khuyến khích.

### 21.7. Dùng static method để gọi instance field không có receiver

~~~java
class Example {
    int value;

    static int read() {
        // return value; // Lỗi compile: non-static variable...
        return 0;
    }
}
~~~

Thêm `static` lên method không làm biến `value` thành static. Nếu cần giá trị của một object, truyền tham chiếu hoặc đổi API thành instance method hợp lý.

### 21.8. Static shared counter bị đếm sai khi constructor ném exception

~~~java
class Item {
    static int attempts;

    Item(String name) {
        attempts++;
        if (name == null) {
            throw new IllegalArgumentException("name null");
        }
    }
}
~~~

`attempts` đếm **số lần đã thực hiện increment**, không bảo đảm số object khởi tạo thành công. Nếu muốn đếm object thành công, phải đặt thao tác đếm đúng ngữ nghĩa và xem xét side effect/exception; đếm số object đang sống còn cần cơ chế khác, không thể suy ra từ một bộ đếm constructor đơn giản.

### 21.9. Dùng `static` làm “global variable” không có ranh giới

Biến shared mutable tiện nhưng khiến kết quả phụ thuộc thứ tự sử dụng, đặc biệt qua các test. Chọn rõ phạm vi lifetime và ownership trước khi quyết định class-level state.

## 22. Bài tập tự kiểm tra

**Câu 1.** Một class có `static int total` và `int value`. Tạo ba object thì có bao nhiêu bản field theo mô hình logic thông thường?

**Đáp án:** Một static `total` trên runtime class tương ứng, và ba instance `value` — mỗi object một bản.

**Câu 2.** `Counter a = new Counter(); Counter b = new Counter(); a.value++;` có làm `b.value` tăng không?

**Đáp án:** Không, nếu `value` là instance field và `a`, `b` trỏ hai object khác nhau. Nếu hai biến alias cùng object thì thay đổi được nhìn thấy qua cả hai.

**Câu 3.** `static void report()` có thể dùng `this.field` không?

**Đáp án:** Không. Static method không có current object `this`. Có thể đọc `object.field` thông qua một receiver object thích hợp nếu visibility cho phép.

**Câu 4.** `Order.totalCreated()` có cần `new Order()` trước không?

**Đáp án:** Không cần một Order object để gọi static method. Tuy nhiên class initialization tương ứng có thể diễn ra trước lần sử dụng tích cực đầu tiên.

**Câu 5.** Gán `Device.manufacturer = "B"` có tự đổi một field riêng trong từng Device object không?

**Đáp án:** Không. Đây là thay static field chung. Khi instance methods đọc static field đó, chúng có thể thấy giá trị mới, nhưng không có phép gán vào từng instance field tương ứng.

**Câu 6.** `private static final List<String> DATA` có bảo đảm list không thể thêm phần tử không?

**Đáp án:** Không. `final` ngăn gán lại tham chiếu field; nếu List object mutable và code có quyền truy cập giữ tham chiếu, nó vẫn có thể bị sửa.

**Câu 7.** `Parent p = new Child(); p.staticMethod()` và `p.instanceMethod()` khác nhau thế nào nếu Child hide/override tương ứng?

**Đáp án:** Static method chọn theo compile-time type Parent (hiding), còn overridable instance method có thể dispatch tới Child implementation theo runtime type.

**Câu 8.** Static nested class có thể có instance field không?

**Đáp án:** Có. `static` trên nested class có nghĩa nó không có enclosing outer instance ngầm định; mỗi nested instance vẫn có các instance fields được khai báo trong nested class.

**Câu 9.** Static field `int requests` có tự thread-safe nếu nhiều thread gọi `requests++` không?

**Đáp án:** Không. Cần synchronization/atomic variable phù hợp. Thậm chí instance fields cũng có thể bị race khi một object được nhiều thread chia sẻ.

**Câu 10.** Khi Java gọi `main` static, chương trình có thể dùng instance methods không?

**Đáp án:** Có. `main` có thể tạo object hoặc nhận tham chiếu rồi gọi instance methods.

**Câu 11.** Nếu `class Base { static int total; }` và `class Child extends Base {}`, `Child.total` có một field static riêng mới không?

**Đáp án:** Không. Nếu không có khai báo field mới, nó sử dụng field được khai báo ở Base theo các quy tắc access/inheritance; Java không tự nhân đôi field chỉ vì subclass tồn tại.

**Câu 12.** Đọc `public static final int LIMIT = 10` có luôn kích hoạt static initializer của class khai báo không?

**Đáp án:** Không nhất thiết. Nếu là constant variable đủ điều kiện compile-time constant, code có thể được compiler inline; cần phân biệt tham chiếu compile-time constant với active uses dẫn đến class initialization.

**Câu 13.** Một static factory `User.of("Lan")` có thể tạo User instance không?

**Đáp án:** Có. Static method không cần current User object để chạy; nó hoàn toàn có thể gọi constructor và trả tham chiếu tới object mới.

**Câu 14.** Gán một biến local từng giữ tham chiếu đến object thành `null` có hủy object và xóa các static fields của class không?

**Đáp án:** Không. Biến local chỉ mất một tham chiếu; object có thể còn aliases. Static state có vòng đời riêng liên quan runtime class/class loader, không tự bị xóa khi một object hoặc biến tham chiếu không còn sử dụng.

## 23. Checklist khi chọn static hoặc instance cho thành viên

1. **Dữ liệu này thuộc về ai?** Mỗi user/order/session hay toàn bộ một class/runtime component?
2. **Có cần nhiều phiên bản độc lập?** Nếu có, ưu tiên instance fields hoặc dependency injection thay vì static mutable field.
3. **Method có đọc/ghi state của current object không?** Nếu có, instance method thường diễn đạt rõ hơn.
4. **Method chỉ là utility thuần từ tham số?** Static method có thể phù hợp nếu không cần polymorphic instance contract.
5. **Có cần overriding/dynamic dispatch không?** Static methods không hỗ trợ overriding theo receiver runtime.
6. **Có phải constant không?** Cân nhắc `static final` với dữ liệu immutable thật sự; đừng tưởng final reference làm object mutable trở nên bất biến.
7. **Class được khởi tạo khi nào?** Static initialization xảy ra theo quy tắc class initialization, không chạy lại cho từng object.
8. **Có shared mutable state không?** Xem test isolation, thread-safety, lifecycle và khả năng cache/memory retention.
9. **Có tên class rõ ràng khi gọi static không?** Ưu tiên `ClassName.member` thay vì `instance.member` cho static.
10. **Trong method static có dùng `this` không?** Không thể; cần object tường minh nếu muốn thao tác trên instance.
11. **Khi kế thừa, static field/method đang được khai báo ở class nào?** Phân biệt inherited field, hiding và overriding.
12. **Trong class lồng nhau, modifier static nằm ở type hay member?** Static nested class vẫn có instance fields/methods của riêng nó.
13. **Có nhiều JVM hoặc class loaders không?** Đừng xem static variable là trạng thái toàn hệ thống hoặc công cụ đồng bộ giữa các process.
14. **Có framework/service cần state theo request không?** Tránh tạm đưa vào static field chung chỉ vì việc truyền dependency khó hơn.

**Kết luận:** Thành viên `static` gắn với **class**, còn thành viên không static gắn với **từng object**. Static fields giúp biểu diễn dữ liệu chung; instance fields giúp mỗi object giữ trạng thái riêng. Static methods không có `this` và không dispatch theo runtime receiver như instance methods; instance methods có thể sử dụng cả state riêng lẫn state chung. Chọn đúng loại thành viên dựa trên **quyền sở hữu dữ liệu, vòng đời, tính thay đổi, polymorphism và concurrency** sẽ giúp code Java rõ ràng, đúng đắn và dễ bảo trì.
