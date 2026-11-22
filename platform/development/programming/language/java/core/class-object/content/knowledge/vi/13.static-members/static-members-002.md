# Trường `static` và dữ liệu dùng chung giữa các thể hiện trong Java

Trong Java, mỗi lần tạo object bằng `new` thường tạo ra một **thể hiện (instance)** có trạng thái riêng. Nhưng không phải mọi field được khai báo trong class đều thuộc về từng object. Nếu khai báo field bằng từ khóa **`static`**, field đó thuộc về **class tại runtime**, và các instance của cùng class runtime có thể đọc hoặc thay đổi **cùng một vùng trạng thái logic** thông qua field ấy.

Ví dụ:

~~~java
class Student {
    String name;                // Instance field: mỗi Student có name riêng.
    static int studentCount;    // Static field: dùng chung trong class Student.

    Student(String name) {
        this.name = name;
        studentCount++;
    }
}
~~~

Nếu tạo hai Student, `name` của từng object độc lập, còn `studentCount` là **một field chung** cho class `Student`. Thay đổi field static không có nghĩa sửa đồng thời mọi instance field. Đây là cơ chế hữu ích để quản lý **cấu hình cấp class, số lượng instance đã tạo theo một định nghĩa cụ thể, hằng số, cache hoặc registry** — nhưng cũng là nguồn gây lỗi khi chia sẻ trạng thái mutable không kiểm soát.

Bài viết thuộc phần **Thành viên static** của Java Core — Class & Object, sử dụng Java 17+, giải thích từng bước cú pháp, ngữ nghĩa, thời điểm khởi tạo, hành vi giữa nhiều object, kế thừa, thử nghiệm, quản lý vòng đời và vấn đề đồng thời.

## 1. Kết quả cần đạt

Sau bài này, bạn cần:

1. Phân biệt **instance field** và **static field** về nơi lưu trạng thái logic, phạm vi dùng chung và cách truy cập.
2. Dự đoán kết quả khi nhiều object cùng đọc/ghi một static field.
3. Biết vì sao **`ClassName.staticField`** thường rõ nghĩa hơn `object.staticField`.
4. Hiểu static field có thể được dùng **khi chưa tạo instance**, nhưng việc sử dụng có thể khởi tạo class.
5. Hiểu giá trị mặc định, **static initializer**, thứ tự khởi tạo class và sự khác nhau với instance initialization.
6. Phân biệt **static field** với **static local variable** — Java không có cú pháp local static như một số ngôn ngữ khác.
7. Giải thích khi nào nên sử dụng **`static final`**, và tại sao `static final List` không tự trở thành bất biến.
8. Theo dõi **static fields khi có kế thừa**, field hiding và static method hiding.
9. Nhận biết rủi ro **shared mutable state**, mất an toàn đa luồng, trạng thái lây giữa test và memory retention.
10. Chọn phương án thiết kế thích hợp: instance field, static constant, singleton, dependency injection hoặc class-level service.

Các chương trình hoàn chỉnh có tên tệp và lệnh `javac`/`java`; ví dụ chưa độc lập sẽ được ghi rõ.

## 2. Sơ đồ trực quan: phần chung và phần riêng

Giả sử:

~~~java
class Counter {
    int value;
    static int totalCreated;

    Counter() {
        totalCreated++;
    }
}
~~~

Sau:

~~~java
Counter a = new Counter();
Counter b = new Counter();
a.value = 10;
b.value = 20;
~~~

Có hai Counter instances, mỗi instance có field `value` riêng; nhưng cả hai liên quan tới **cùng field `Counter.totalCreated`**:

~~~text
             Class Counter (runtime)
         +---------------------------+
         | static totalCreated = 2   |
         +---------------------------+
               ^                ^
               |                |
         +-----------+    +-----------+
a ------>| Counter #1|    | Counter #2|<------ b
         | value=10  |    | value=20  |
         +-----------+    +-----------+
~~~

Mũi tên từ object lên class là **minh họa ngữ nghĩa**, không phải khẳng định JVM thực sự cất static field ngay cạnh một block object nào đó trong RAM. Phần quan trọng:

- Mỗi `new Counter()` thành công thông thường tạo một Counter instance mới.
- Mỗi Counter instance có **field `value` riêng**.
- `totalCreated` gắn với class runtime `Counter`, nên không nhân bản theo số instance.
- Biến `a` và `b` là những tham chiếu đến hai object khác nhau; việc tạo alias `Counter c = a;` không chạy constructor và không làm counter tăng.

### Bảng nhanh

| Tiêu chí | Instance field | Static field |
| --- | --- | --- |
| Khai báo | `int score;` | `static int total;` |
| Gắn với | Một object cụ thể | Class runtime tương ứng |
| Mỗi `new` tạo bản field riêng? | Có, cho instance mới | Không tạo bản static field mới cho mỗi object |
| Cách truy cập phổ biến | `student.score` hoặc `this.score` | `Student.total` |
| Có dùng khi chưa có instance? | Cần instance để đọc/ghi thông thường | Có thể dùng qua class nếu quyền truy cập cho phép |
| Giá trị mặc định | Theo kiểu field, trong quá trình tạo instance | Theo kiểu field, trong quá trình chuẩn bị/khởi tạo class |
| Thay đổi có thể ảnh hưởng đối tượng khác? | Khi chia sẻ cùng object | Có: mọi code dùng cùng class runtime thấy cùng state theo quy tắc memory model |
| Có mặc nhiên thread-safe? | Không | Không |

## 3. Ví dụ chạy đầu tiên: hai object, một static counter

Lưu file **`StaticFieldBasicsDemo.java`**:

~~~java
public class StaticFieldBasicsDemo {
    static final class Student {
        private static int createdCount = 0;

        private final String name;
        private int lessons;

        Student(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            this.name = name;
            createdCount++;
        }

        void completeLesson() {
            lessons++;
        }

        String describe() {
            return name + ": " + lessons;
        }

        static int createdCount() {
            return createdCount;
        }
    }

    public static void main(String[] args) {
        System.out.println("before=" + Student.createdCount());

        Student mai = new Student("Mai");
        Student an = new Student("An");
        mai.completeLesson();
        mai.completeLesson();
        an.completeLesson();

        System.out.println(mai.describe());
        System.out.println(an.describe());
        System.out.println("after=" + Student.createdCount());

        Student alias = mai;
        alias.completeLesson();

        System.out.println("through alias=" + mai.describe());
        System.out.println("after alias=" + Student.createdCount());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 StaticFieldBasicsDemo.java
java StaticFieldBasicsDemo
~~~

Stdout:

~~~text
before=0
Mai: 2
An: 1
after=2
through alias=Mai: 3
after alias=2
~~~

Giải thích:

1. Khi gọi `Student.createdCount()`, class cần sẵn sàng để sử dụng; static field được khởi tạo thành 0, **không cần tạo Student instance trước**.
2. `new Student("Mai")` và `new Student("An")` thực hiện constructor hai lần; `createdCount` tăng lên 2.
3. `lessons` là instance field: Mai có 2 bài, An có 1 bài.
4. `Student alias = mai;` chỉ sao chép reference đến **cùng object Mai**, không có `new`.
5. `alias.completeLesson()` thay `lessons` của object Mai thành 3, nhưng không chạy constructor nên static `createdCount` vẫn là 2.

Trong ví dụ, `Student` là **static nested class** chỉ để gói chương trình trong một file. Từ `static` của nested class và từ `static` của field `createdCount` là **hai vai trò khác nhau**, không nên đánh đồng.

## 4. Cách khai báo và truy cập một static field

Cú pháp:

~~~java
class Configuration {
    static int timeoutSeconds = 30;
}
~~~

Truy cập theo tên class:

~~~java
int timeout = Configuration.timeoutSeconds;
Configuration.timeoutSeconds = 45;
~~~

Các đoạn này là **mã minh họa** đặt trong method/ngữ cảnh hợp lệ. `Configuration.timeoutSeconds` diễn đạt rõ field thuộc class `Configuration`.

### Có thể dùng reference instance để truy cập static field?

Với static field có quyền truy cập phù hợp, Java thường **cho phép**:

~~~java
Configuration config = new Configuration();
int timeout = config.timeoutSeconds;
~~~

Tuy nhiên cách viết này **không nên dùng**: nó khiến người đọc tưởng `timeoutSeconds` thuộc riêng `config`. Cách nên dùng:

~~~java
int timeout = Configuration.timeoutSeconds;
~~~

Còn một điểm tinh tế: trong cú pháp `expression.staticField`, biểu thức qualifier có thể được đánh giá để lấy side effect, nhưng **giá trị object của qualifier không phải nơi lưu static field**. Viết `object.staticField` không làm tạo thêm bản sao field.

### Không gọi static field qua `this` như một thiết kế thường xuyên

Trong instance method có thể đọc static field qua tên đơn giản khi được phép, nhưng ưu tiên tên class:

~~~java
class Session {
    private static int maxSessions = 100;

    boolean hasCapacity(int openSessions) {
        return openSessions < Session.maxSessions;
    }
}
~~~

`Session.maxSessions` mô tả trạng thái cấp class; `this.maxSessions` dù có thể biên dịch trong ngữ cảnh instance phù hợp nhưng che khuất ý nghĩa **shared state**.

## 5. Static field tồn tại khi không có object instance

Một static member có thể dùng theo tên class:

~~~java
System.out.println(Math.PI);
System.out.println(Integer.MAX_VALUE);
~~~

Không cần tạo `new Math()` hay `new Integer()` để lấy các static constants trên.

Một class tùy chỉnh:

~~~java
class AppSettings {
    static String environment = "development";
}

class Bootstrap {
    public static void main(String[] args) {
        System.out.println(AppSettings.environment);
    }
}
~~~

Đoạn gồm hai class có thể đặt trong một file thích hợp vì không khai báo public top-level class. `AppSettings.environment` có giá trị mà không cần bất kỳ `AppSettings` instance nào.

**Không kết luận ngược:** “static field có thể tồn tại khi chưa có instance” không có nghĩa mọi static class đều đã được khởi tạo ngay khi JVM chạy. Java khởi tạo các class theo các quy tắc **class initialization**; khi nào được kích hoạt phụ thuộc hành vi mã.

## 6. Một static field có giá trị mặc định trước static initializer

Mỗi static field có giá trị mặc định dựa trên kiểu, ví dụ:

| Kiểu field | Giá trị mặc định |
| --- | --- |
| `int` / `long` và các integral types | 0 theo kiểu |
| `float` / `double` | 0.0 theo kiểu |
| `boolean` | `false` |
| `char` | ký tự zero `'\\u0000'` |
| Reference type như `String`, `List<?>`, array | `null` |

Sau đó static field initializers và static initializer blocks được chạy theo **thứ tự văn bản** áp dụng trong class, theo quy tắc Java.

~~~java
class Example {
    static int count = 5;
    static String name = "Java";

    static {
        count += 2;
    }
}
~~~

Khi class `Example` được khởi tạo bình thường, `count` sau các bước trên là 7 và `name` là `"Java"`.

### Cùng kiểu nhưng khác thời điểm

- Static fields có quá trình chuẩn bị/khởi tạo gắn với **class runtime**.
- Instance fields được khởi tạo cho **từng object instance mới**.

Sự khác biệt giúp giải thích vì sao static initialization không chạy lại chỉ vì tạo thêm một object của cùng class runtime đã được khởi tạo.

## 7. Ví dụ chạy: static initializer so với instance constructor

Lưu **`StaticInitializationDemo.java`**:

~~~java
public class StaticInitializationDemo {
    static class Gadget {
        static int nextId = 1;

        static {
            System.out.println("Gadget static block");
        }

        private final int id;

        {
            System.out.println("Gadget instance block");
        }

        Gadget() {
            id = nextId++;
            System.out.println("Gadget constructor " + id);
        }

        int id() {
            return id;
        }
    }

    public static void main(String[] args) {
        System.out.println("main start");

        Gadget first = new Gadget();
        Gadget second = new Gadget();

        System.out.println("first=" + first.id());
        System.out.println("second=" + second.id());
        System.out.println("next=" + Gadget.nextId);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticInitializationDemo.java
java StaticInitializationDemo
~~~

Stdout:

~~~text
main start
Gadget static block
Gadget instance block
Gadget constructor 1
Gadget instance block
Gadget constructor 2
first=1
second=2
next=3
~~~

Diễn biến:

1. `main start` xuất hiện trước khi `Gadget` được sử dụng theo cách kích hoạt khởi tạo class.
2. Ở lần `new Gadget()` đầu, static field `nextId` được khởi tạo bằng 1, rồi static block in log.
3. Instance initializer block chạy cho Gadget #1, constructor lấy ID 1 và tăng static `nextId` thành 2.
4. `new Gadget()` lần thứ hai **không chạy lại static block**, nhưng instance block và constructor vẫn chạy cho object mới; ID là 2.
5. Sau hai lần tạo, `Gadget.nextId == 3`.

Nếu JVM hoặc tooling có các cơ chế class loading khác, thời điểm **load** class không nhất thiết trùng thời điểm **initialize** class. Quan sát trên chỉ mô tả trình tự được đảm bảo cho chương trình học này.

## 8. Khi nào class được khởi tạo?

Theo quy tắc Java/JVM, việc sử dụng một class theo các cách nhất định có thể kích hoạt **class initialization**, chẳng hạn:

- Tạo instance bằng `new`.
- Gọi static method do class khai báo.
- Đọc/ghi static field do class khai báo, trừ các trường hợp constant variable đặc biệt.
- Những trường hợp khác như reflective initialization theo API và các quy tắc JVM tương ứng.

Không nên nghĩ một class **chỉ** được khởi tạo khi lệnh `new` xuất hiện. Trong ví dụ đầu bài, `Student.createdCount()` có thể kích hoạt khởi tạo class trước khi có Student instance.

### Không phải lúc nào tham chiếu tới tên class cũng chạy static block

Ví dụ một **compile-time constant**:

~~~java
class Constants {
    static final int LIMIT = 10;

    static {
        System.out.println("Constants initialized");
    }
}
~~~

Một caller đọc `Constants.LIMIT` trong ngữ cảnh bình thường có thể không kích hoạt class initialization vì `LIMIT` là **constant variable** (`static final int` có constant expression initializer). Compiler có thể dùng chính giá trị hằng vào mã đã biên dịch.

Ngược lại, một static field **không phải constant variable**, kể cả `static final` field được gán thông qua method call, thường cần class initialization khi được đọc trực tiếp.

Đây là một sắc thái quan trọng: **`static final` không luôn có cùng hành vi khởi tạo với static field thường**.

## 9. Ví dụ chạy: hằng compile-time và static initialization

Lưu file **`StaticConstantInitializationDemo.java`**:

~~~java
public class StaticConstantInitializationDemo {
    static final class Constants {
        static final int LIMIT = 10;
        static final Integer BOXED_LIMIT = Integer.valueOf(20);

        static {
            System.out.println("Constants initialized");
        }
    }

    public static void main(String[] args) {
        System.out.println("limit=" + Constants.LIMIT);
        System.out.println("boxed=" + Constants.BOXED_LIMIT);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticConstantInitializationDemo.java
java StaticConstantInitializationDemo
~~~

Stdout:

~~~text
limit=10
Constants initialized
boxed=20
~~~

Ở dòng đầu, `LIMIT` là một constant variable kiểu `int` có initializer là compile-time constant expression, nên việc dùng nó ở đây không kích hoạt khởi tạo `Constants`.

Ở dòng hai, `BOXED_LIMIT` là `Integer` object reference và được tạo từ method call, **không phải constant variable** theo quy tắc Java; truy cập nó kích hoạt khởi tạo class, làm static block in log trước khi in `boxed=20`.

**Đừng đoán rằng mọi `static final` đều được compiler chèn giá trị vào caller.** Cần phân biệt loại field và dạng initializer.

## 10. Static fields được khởi tạo theo thứ tự văn bản

Một static initializer hoặc field initializer có thể đọc static field đã khai báo sau nó theo những đường biểu thức được Java cho phép. Ở thời điểm đọc, field đó có thể vẫn đang ở **giá trị mặc định**, tạo kết quả bất ngờ.

Lưu **`StaticOrderDemo.java`**:

~~~java
public class StaticOrderDemo {
    static class Example {
        static int observed = readLater();
        static int later = 9;

        static int readLater() {
            return later;
        }

        static {
            System.out.println("observed=" + observed);
            System.out.println("later=" + later);
        }
    }

    public static void main(String[] args) {
        System.out.println("final=" + Example.later);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticOrderDemo.java
java StaticOrderDemo
~~~

Stdout:

~~~text
observed=0
later=9
final=9
~~~

Giải thích:

1. Các static fields có giá trị mặc định, nên `later` ban đầu là 0.
2. `observed = readLater()` chạy trước initializer `later = 9`.
3. `readLater()` đọc `later` khi vẫn là 0, nên `observed = 0`.
4. Tiếp đó `later = 9`.
5. Static block in `observed=0`, `later=9`.
6. `main` đọc `Example.later` sau khởi tạo nên in 9.

**Đừng thiết kế logic nghiệp vụ phụ thuộc các lần đọc giá trị mặc định trong static initialization.** Thứ tự khởi tạo phức tạp thường giảm độ rõ và có thể tạo lỗi khó tìm khi nhiều class tham chiếu chéo nhau.

## 11. Static field có thể chứa primitive hoặc object reference

`static` không quy định kiểu của field:

~~~java
class SharedData {
    static int counter;                       // Primitive int.
    static String title = "Java";             // Reference tới String.
    static java.util.List<String> names =
            new java.util.ArrayList<>();      // Reference tới một ArrayList.
}
~~~

Đây là class minh họa.

- `counter` là giá trị primitive được lưu ở field static.
- `title` là reference tới String object; String immutable.
- `names` là reference tới List object mutable. Khi một method thêm phần tử, những method khác đọc cùng list sẽ nhìn thấy thay đổi theo quy tắc visibility áp dụng.

**Không nhầm:** “Static field dùng chung” không có nghĩa Java tự động tạo một object shared cho mỗi phép truy cập. Mỗi static field chỉ giữ **một giá trị** tại một thời điểm cho class runtime tương ứng; giá trị đó có thể là primitive, null hoặc một reference tới object.

## 12. Dữ liệu dùng chung giữa các instance: ví dụ registry nhỏ

Lưu **`SharedRegistryDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SharedRegistryDemo {
    static final class Employee {
        private static final List<String> NAMES = new ArrayList<>();

        private final String name;

        Employee(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }

            this.name = name;
            NAMES.add(name);
        }

        String name() {
            return name;
        }

        static List<String> namesSnapshot() {
            return List.copyOf(NAMES);
        }
    }

    public static void main(String[] args) {
        Employee first = new Employee("Mai");
        Employee second = new Employee("An");

        System.out.println("first=" + first.name());
        System.out.println("second=" + second.name());
        System.out.println("all=" + Employee.namesSnapshot());
    }
}
~~~

~~~bash
javac -encoding UTF-8 SharedRegistryDemo.java
java SharedRegistryDemo
~~~

Stdout:

~~~text
first=Mai
second=An
all=[Mai, An]
~~~

`name` là instance field riêng của từng Employee. `NAMES` là **static reference** tới một ArrayList object chung của `Employee`. Mỗi constructor ghi vào cùng List object.

`private static final` không tự làm ArrayList immutable:

- `private`: ngoài class không thể truy cập trực tiếp field theo quy tắc thông thường.
- `static`: field gắn với class.
- `final`: không thể gán lại field reference sau khởi tạo hợp lệ.
- `ArrayList` bên trong vẫn mutable và có thể nhận `add`.

Ở ví dụ, `namesSnapshot()` trả một list không sửa được bằng `List.copyOf`, nhằm tránh để caller thay đổi list nội bộ trực tiếp. Tuy nhiên **đăng ký người dùng/tên thực tế** có thể cần uniqueness, cleanup, đồng bộ và authorization; ví dụ chỉ minh họa khả năng chia sẻ.

## 13. Các trường hợp phù hợp để dùng static field

| Nhu cầu | Static có phù hợp? | Lưu ý |
| --- | --- | --- |
| Hằng số `MAX_ITEMS` của một class | Thường có | Dùng `static final` với giá trị immutable |
| Bộ đếm tạo instance trong demo | Có, khi định nghĩa rõ | Constructor có thể thất bại, subclass có thể ảnh hưởng cách đếm |
| Cấu hình cố định toàn ứng dụng | Có thể | Tránh static mutable global nếu cần cấu hình theo request/test/tenant |
| Logger theo class | Thường có | Ví dụ `private static final Logger LOG` theo framework |
| Stateless helper | Dùng static method, không nhất thiết cần static field | `Math.max` là ví dụ về static method |
| Cache toàn tiến trình | Có thể, nhưng phải cẩn thận | Thread-safety, giới hạn dung lượng, eviction, lifecycle |
| Một biến mô tả từng khách hàng | Không | Đó là instance data |
| Thông tin phiên đăng nhập hiện tại | Thường không nên là static field toàn cục | Dễ lẫn user/request/thread |
| Dữ liệu thay đổi theo tenant | Không nên chia sẻ toàn cục vô điều kiện | Dùng context/service có scope phù hợp |
| Counter có nhiều thread | Có thể nếu dùng công cụ đồng bộ | `static int count++` không atomic |

**Tiêu chí chính:** Dữ liệu này có thật sự là **một sự thật chung cho class/runtime scope** hay thuộc **một object, request, phiên, tenant hoặc service instance** cụ thể?

## 14. Lỗi điển hình: đặt state của từng người dùng thành static

Xét class thiếu đúng đắn:

~~~java
class UserSession {
    static String currentUser;

    UserSession(String user) {
        currentUser = user;
    }
}
~~~

Nếu tạo:

~~~java
UserSession alice = new UserSession("Alice");
UserSession bob = new UserSession("Bob");
~~~

thì field `UserSession.currentUser` cuối cùng là `"Bob"`. Đối tượng `alice` không sở hữu bản `currentUser` riêng. Nếu màn hình hiển thị thông tin Alice qua static field, nó có thể lại đọc `"Bob"`.

### Chương trình chạy thể hiện lỗi

Lưu file **`StaticPerUserBugDemo.java`**:

~~~java
public class StaticPerUserBugDemo {
    static final class BadSession {
        private static String currentUser;

        BadSession(String user) {
            currentUser = user;
        }

        String display() {
            return currentUser;
        }
    }

    static final class GoodSession {
        private final String currentUser;

        GoodSession(String user) {
            this.currentUser = user;
        }

        String display() {
            return currentUser;
        }
    }

    public static void main(String[] args) {
        BadSession badAlice = new BadSession("Alice");
        BadSession badBob = new BadSession("Bob");

        System.out.println("bad Alice=" + badAlice.display());
        System.out.println("bad Bob=" + badBob.display());

        GoodSession goodAlice = new GoodSession("Alice");
        GoodSession goodBob = new GoodSession("Bob");

        System.out.println("good Alice=" + goodAlice.display());
        System.out.println("good Bob=" + goodBob.display());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticPerUserBugDemo.java
java StaticPerUserBugDemo
~~~

Stdout:

~~~text
bad Alice=Bob
bad Bob=Bob
good Alice=Alice
good Bob=Bob
~~~

Câu trả lời không phải “static field tự sao chép dữ liệu sai”, mà là **hai session objects cùng ghi một field cấp class**. Với `GoodSession`, field là instance state, nên mỗi session giữ thông tin riêng.

**Bài học:** Dùng `static` cho dữ liệu người dùng hiện tại là một global-state bug đặc biệt nguy hiểm trong hệ thống nhiều user/request. Những thông tin này phải được gắn với context/instance có vòng đời phù hợp và có chiến lược bảo mật riêng.

## 15. Static field và constructor: bộ đếm thực sự đếm điều gì?

Một ví dụ giáo khoa thường viết:

~~~java
class Product {
    private static int created;

    Product() {
        created++;
    }
}
~~~

Trong một chương trình tuần tự đơn giản, `created` tăng mỗi lần constructor body đi qua câu lệnh increment. Nhưng hãy định nghĩa chính xác **ý nghĩa của counter**:

- Nó đếm **số lần body chạy đến lệnh `created++`**, không tự đếm “mọi object còn sống”.
- Nếu class có nhiều constructor và có `this(...)`, nên đặt increment ở chỗ phù hợp để tránh đếm lặp theo một lần tạo instance.
- Constructor có thể ném exception **sau khi đã tăng counter**. Khi đó counter tăng dù lời gọi `new` không hoàn tất thành công.
- Superclass constructor có thể tăng counter khi subclass constructor sau đó thất bại.
- Nếu object được tạo qua những cơ chế đặc biệt khác với lời gọi constructor thông thường, một constructor counter không nhất thiết bao quát mọi trường hợp.
- Trong nhiều thread, `created++` không bảo đảm đếm chính xác nếu không có synchronization/atomicity.

Nếu muốn đo **số yêu cầu tạo thành công** theo một hợp đồng nghiệp vụ, đôi khi tốt hơn là kiểm đếm trong factory/service tại ranh giới thành công thay vì suy ra từ mọi constructor call.

## 16. Ví dụ chạy: constructor từ chối dữ liệu và counter

Lưu **`StaticCounterFailureDemo.java`**:

~~~java
public class StaticCounterFailureDemo {
    static final class Ticket {
        private static int acceptedCount;

        private final String code;

        Ticket(String code) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code required");
            }

            this.code = code;
            acceptedCount++;
        }

        static int acceptedCount() {
            return acceptedCount;
        }

        String code() {
            return code;
        }
    }

    public static void main(String[] args) {
        Ticket first = new Ticket("A");
        System.out.println("first=" + first.code());

        try {
            new Ticket("");
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected invalid ticket");
        }

        Ticket second = new Ticket("B");
        System.out.println("second=" + second.code());
        System.out.println("accepted=" + Ticket.acceptedCount());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticCounterFailureDemo.java
java StaticCounterFailureDemo
~~~

Stdout:

~~~text
first=A
rejected invalid ticket
second=B
accepted=2
~~~

Trong ví dụ cụ thể, validation xảy ra **trước** increment, và không có bước khác trong constructor có khả năng ném exception sau increment. Vì vậy `acceptedCount` bằng 2. Tuy nhiên không nên diễn giải method `acceptedCount()` như một phép đo phổ quát về “số Ticket object hiện còn tồn tại”: Java garbage collector không tự giảm bộ đếm khi một object không còn reachable.

## 17. `static final`: hằng số có phạm vi class

Một số giá trị dùng chung không nên bị sửa:

~~~java
public final class Limits {
    public static final int MAX_ITEMS = 100;
    public static final String DEFAULT_LANGUAGE = "vi";

    private Limits() {
        throw new AssertionError("utility class");
    }
}
~~~

Đây là class minh họa; các constant values thuộc class và không cần instance. Việc tạo private constructor còn giúp bộc lộ ý định không cho caller tạo `new Limits()`.

Quy ước Java thường đặt tên static constants bằng **UPPER_SNAKE_CASE** (`MAX_ITEMS`). Đây là quy ước đặt tên, không phải điều kiện cú pháp compiler.

### Khi nào `static final` thật sự là constant variable?

Trong Java, một `final` field kiểu primitive hoặc `String` được khởi tạo bằng **constant expression** có thể là *constant variable* theo đặc tả. Nó có thể được nhúng giá trị vào class files của caller tại compile time.

~~~java
public static final int MAX_ITEMS = 100;
~~~

Nếu một thư viện thay giá trị thành 200 nhưng client **không biên dịch lại**, mã client cũ có thể vẫn dùng giá trị 100 được nhúng trước đó. Đó là lý do cần cân nhắc khi public một constant có thể thay đổi giữa các phiên bản.

Một field như:

~~~java
public static final java.time.Duration TIMEOUT =
        java.time.Duration.ofSeconds(5);
~~~

không phải compile-time constant variable theo cùng quy tắc primitive/String, dù reference là final và object Duration immutable.

## 18. `static final` reference không làm object mutable thành immutable

Xét:

~~~java
class SharedNames {
    static final java.util.List<String> NAMES =
            new java.util.ArrayList<>();
}
~~~

`NAMES` là **static final reference**, không thể được gán lại thành một List khác sau khởi tạo. Nhưng lời gọi:

~~~java
SharedNames.NAMES.add("Mai");
~~~

vẫn sửa **ArrayList object chung**.

Nếu muốn exposed data không bị thay đổi qua API mutation:

~~~java
public static final java.util.List<String> DEFAULT_NAMES =
        java.util.List.of("Mai", "An");
~~~

`List.of` cung cấp List không hỗ trợ các thao tác mutation thông thường và từ chối null elements. Trong trường hợp các phần tử là `String` immutable, đây là một cấu trúc mặc định tương đối dễ bảo vệ. Nếu phần tử là object mutable, ngay cả danh sách không cho add/remove cũng không tự ngăn sửa **state của element objects**.

### Hằng số hay global mutable state?

- `static final int MAX_RETRIES = 3`: một constant đơn giản.
- `static final List<String> NAMES = List.of(...)`: một static reference đến unmodifiable List.
- `static final List<String> NAMES = new ArrayList<>()`: một static reference không gán lại được, nhưng **shared mutable list**.
- `static int count`: mutable class-level primitive state.

Đừng coi từ `final` là bằng chứng “dữ liệu chung bất biến ở mọi tầng”.

## 19. Kế thừa: static field thuộc class khai báo, không thuộc object subtype riêng lẻ

Với class kế thừa:

~~~java
class Parent {
    static int count;
}

class Child extends Parent {
}
~~~

`Child` có thể tham chiếu member static `count` được kế thừa theo các quy tắc truy cập, nhưng điều đó **không nhất thiết tạo một field count mới trong Child**. Nếu Child **không khai báo field cùng tên**, `Parent.count` và `Child.count` đề cập đến **field được khai báo trong Parent** trong ngữ cảnh hợp lệ.

**Không suy luận:** “Mỗi subclass có bản copy riêng của toàn bộ static fields của superclass”. Không. Field static vẫn gắn với **class khai báo**.

### Ví dụ chạy: field static được dùng chung qua subclass

Lưu **`InheritedStaticFieldDemo.java`**:

~~~java
public class InheritedStaticFieldDemo {
    static class Parent {
        static int count = 0;
    }

    static final class Child extends Parent {
    }

    public static void main(String[] args) {
        Parent.count = 3;

        System.out.println("parent=" + Parent.count);
        System.out.println("child=" + Child.count);

        Child.count++;
        System.out.println("after parent=" + Parent.count);
        System.out.println("after child=" + Child.count);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InheritedStaticFieldDemo.java
java InheritedStaticFieldDemo
~~~

Stdout:

~~~text
parent=3
child=3
after parent=4
after child=4
~~~

Cả `Parent.count` và `Child.count` trong ví dụ cùng chỉ field static **khai báo ở Parent**. Cú pháp `Child.count` không có nghĩa Child tự lưu một count khác.

Về phong cách, nên truy cập bằng **class khai báo thực sự** (`Parent.count`) để người đọc không hiểu lầm rằng có một field riêng ở Child.

## 20. Field hiding: subclass khai báo static field trùng tên

Nếu Child khai báo field mới cùng tên, nó **hide** field của Parent thay vì override field:

~~~java
class Parent {
    static int count = 10;
}

class Child extends Parent {
    static int count = 20;
}
~~~

Giờ có **hai fields khác nhau**:

- `Parent.count` thuộc Parent.
- `Child.count` thuộc Child.

Việc lựa chọn field phụ thuộc vào **tên/kiểu compile-time của biểu thức truy cập**, không có dynamic dispatch như instance methods được override.

### Ví dụ chạy: hai static fields cùng tên

Lưu **`StaticFieldHidingDemo.java`**:

~~~java
public class StaticFieldHidingDemo {
    static class Parent {
        static int value = 10;
    }

    static final class Child extends Parent {
        static int value = 20;
    }

    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = new Child();

        System.out.println("Parent=" + Parent.value);
        System.out.println("Child=" + Child.value);
        System.out.println("parentView=" + parentView.value);
        System.out.println("childView=" + childView.value);

        Child.value = 99;
        System.out.println("after Parent=" + Parent.value);
        System.out.println("after Child=" + Child.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticFieldHidingDemo.java
java StaticFieldHidingDemo
~~~

Stdout:

~~~text
Parent=10
Child=20
parentView=10
childView=20
after Parent=10
after Child=99
~~~

`parentView` và `childView` đều tham chiếu runtime object kiểu Child (ở đây được tạo độc lập). Nhưng câu lệnh `parentView.value` được phân giải theo **kiểu khai báo Parent** của biểu thức và chọn `Parent.value`; `childView.value` chọn `Child.value`. Những cách truy cập static qua reference như vậy **hợp lệ nhưng không nên dùng** vì gây nhầm. Hãy dùng `Parent.value` và `Child.value`.

### Static method hiding khác instance method overriding

Static methods có thể bị hide bởi static methods cùng chữ ký trong subclass; lời gọi qua tên/kiểu tham chiếu được phân giải theo compile-time rules. Ngược lại, instance methods được override dùng dynamic dispatch theo runtime object. Đừng đánh đồng hai cơ chế.

## 21. Static member trong static context và instance context

Trong static method, **không có `this` của một object instance**:

~~~java
class Calculator {
    private int instanceValue = 5;
    private static int sharedValue = 10;

    static int readShared() {
        return sharedValue;
    }

    static int readOneInstance(Calculator instance) {
        return instance.instanceValue;
    }
}
~~~

Method `readShared()` đọc static field trực tiếp. Method `readOneInstance` muốn đọc instance field thì nhận **tham chiếu tới một Calculator object**.

Cố ý sai:

~~~java
static int invalid() {
    // return this.instanceValue; // Sai: this không có trong static context.
    // return instanceValue;      // Sai: không có instance receiver.
    return Calculator.readShared();
}
~~~

Các đoạn trên minh họa và cần đặt vào class phù hợp. Không thể dùng static method như một instance method ngầm định rồi mong `this` tồn tại.

### Lưu ý biến cục bộ

Java không hỗ trợ khai báo:

~~~java
void method() {
    // static int visits = 0; // Lỗi cú pháp trong Java.
}
~~~

Muốn lưu dữ liệu dùng chung giữa nhiều lần gọi method, có thể dùng **static field** trong class hoặc một object state có vòng đời thích hợp. Không biến mọi “biến cần giữ giữa các lần gọi” thành static vô điều kiện; nhiều trường hợp một instance field trên service object là tốt hơn.

## 22. Static nested class không phải static field

Đây là hai dạng khác nhau:

~~~java
class Outer {
    static int shared = 7;

    static class Nested {
        int ownValue = 3;
    }
}
~~~

- `Outer.shared` là **static field** thuộc Outer.
- `Outer.Nested` là **static nested class**, một kiểu lồng trong Outer không yêu cầu enclosing instance tự động.
- Mỗi `new Outer.Nested()` vẫn tạo một **Nested instance** có `ownValue` riêng.
- `Nested` cũng có thể có những static fields của riêng nó theo quy tắc Java.

Từ `static` trước khai báo nested class **không làm tất cả fields trong Nested thành static**.

### Ví dụ

~~~java
Outer.Nested a = new Outer.Nested();
Outer.Nested b = new Outer.Nested();
a.ownValue = 5;
b.ownValue = 9;
~~~

`a.ownValue` và `b.ownValue` khác nhau, dù class `Nested` có `static` ở khai báo. Nếu `Nested` có `static int sharedCounter`, đó mới là static field của `Nested`.

## 23. Shared mutable static state không tự an toàn đa luồng

Static field có thể được nhiều thread cùng đọc/ghi. Nhưng **`static` không đồng nghĩa synchronized, atomic hay volatile**.

Phản ví dụ:

~~~java
class UnsafeCounter {
    static int count;

    static void increment() {
        count++;
    }
}
~~~

`count++` bao gồm những bước logic đọc, tăng và ghi. Khi hai thread làm cùng lúc, một cập nhật có thể bị mất. Không thể suy luận nếu hai thread cùng tăng 1.000 lần thì counter cuối luôn đúng 2.000.

Ngoài atomicity, còn có **visibility**: một thread ghi field không được đồng bộ đúng cách thì thread khác không nhất thiết quan sát cập nhật theo cách bạn mong đợi.

### `volatile` giải quyết mọi thứ?

`volatile` hỗ trợ các bảo đảm visibility và ordering cụ thể theo Java Memory Model, nhưng **không làm `count++` thành atomic**. Nếu cần tăng/giảm số lượng an toàn, dùng `AtomicInteger` hoặc synchronization/lock phù hợp, tùy invariant.

## 24. Ví dụ chạy: static `AtomicInteger` dùng chung giữa threads

Lưu **`AtomicStaticCounterDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicStaticCounterDemo {
    static final class Counter {
        private static final AtomicInteger VALUE = new AtomicInteger();

        static void increment() {
            VALUE.incrementAndGet();
        }

        static int value() {
            return VALUE.get();
        }
    }

    static void work() {
        for (int i = 0; i < 1_000; i++) {
            Counter.increment();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Thread first = new Thread(AtomicStaticCounterDemo::work);
        Thread second = new Thread(AtomicStaticCounterDemo::work);

        first.start();
        second.start();

        first.join();
        second.join();

        System.out.println("count=" + Counter.value());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicStaticCounterDemo.java
java AtomicStaticCounterDemo
~~~

Stdout:

~~~text
count=2000
~~~

`VALUE` là static final reference tới một `AtomicInteger` object chung. Mỗi thread gọi `incrementAndGet()` trên cùng object. AtomicInteger bảo đảm increment là thao tác atomic theo API; `join()` bảo đảm `main` đợi hai thread hoàn tất trước khi đọc kết quả.

**Điểm cần phân biệt:**

- `static` chỉ xác định chia sẻ state cấp class.
- `final` chỉ ngăn gán lại reference `VALUE`.
- `AtomicInteger` mới là cơ chế hỗ trợ cập nhật atomic của giá trị đếm.

Nếu invariant gồm **nhiều fields phụ thuộc nhau**, dùng một AtomicInteger cho từng field **chưa chắc** làm toàn bộ operation đa trường trở nên nguyên tử. Cần thiết kế concurrency tổng thể.

## 25. Một static field chứa collection dùng chung cũng cần thread safety

~~~java
private static final java.util.List<String> EVENTS =
        new java.util.ArrayList<>();
~~~

Nếu nhiều threads cùng gọi `EVENTS.add(...)` mà không có đồng bộ, `ArrayList` không bảo đảm thread-safe. Một cuộc gọi đồng thời có thể gây race, kết quả thiếu/thừa hoặc trạng thái không hợp lệ tùy tình huống.

Các phương án tùy nhu cầu:

- Dùng collection concurrent phù hợp, ví dụ `ConcurrentHashMap` cho một số bài toán map.
- Dùng `Collections.synchronizedList(...)` rồi **đồng bộ đúng cách cả khi duyệt** theo hợp đồng của wrapper.
- Bảo vệ operation bằng lock/synchronized nhất quán.
- Tách state ra service instance và quản lý thread ownership.
- Dùng immutable snapshot khi chỉ cần đọc và không có thay đổi phức tạp.

Không đổi mọi ArrayList thành concurrent collection một cách máy móc: cần xác định **operation nào phải atomic**, những invariant nào liên quan nhiều bước và chi phí đồng bộ chấp nhận được.

## 26. Static state có thể làm các bài kiểm thử phụ thuộc nhau

Một static counter tồn tại xuyên suốt những test methods chạy trên **cùng runtime class**. Nếu test A gọi `visit()`, test B có thể nhìn thấy giá trị còn sót từ A, bất kể các test có tạo object `VisitCounter` mới hay không:

~~~java
class VisitCounter {
    static int visits;
    static void visit() { visits++; }
}
~~~

Vấn đề này khác với **race condition**: ngay cả khi chạy tuần tự, test order vẫn có thể làm kết quả thay đổi. Việc reset shared state là giải pháp chỉ nên dùng khi có boundary quản lý rõ; nếu chạy song song, test này có thể reset state giữa lúc test khác sử dụng.

Ở bài học về **static fields**, điều cần nhớ là field cấp lớp **không thuộc fixture instance** của từng test. Khi state phải độc lập, ưu tiên instance-owned counter. Cơ chế gây flaky tests, thiết kế test isolation, JUnit lifecycle, parallel execution, reset/cleanup và dependency injection được thực hành sâu ở bài **“Rủi ro trạng thái static có thể thay đổi và kiểm thử phụ thuộc nhau”**.

## 27. Ví dụ chạy: instance counter giúp tách state test

Lưu **`StaticVsInstanceCounterDemo.java`**:

~~~java
public class StaticVsInstanceCounterDemo {
    static final class StaticTracker {
        private static int calls;

        static void visit() {
            calls++;
        }

        static int calls() {
            return calls;
        }
    }

    static final class InstanceTracker {
        private int calls;

        void visit() {
            calls++;
        }

        int calls() {
            return calls;
        }
    }

    public static void main(String[] args) {
        StaticTracker.visit();
        StaticTracker.visit();

        InstanceTracker first = new InstanceTracker();
        InstanceTracker second = new InstanceTracker();

        first.visit();
        first.visit();
        second.visit();

        System.out.println("static=" + StaticTracker.calls());
        System.out.println("first=" + first.calls());
        System.out.println("second=" + second.calls());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticVsInstanceCounterDemo.java
java StaticVsInstanceCounterDemo
~~~

Stdout:

~~~text
static=2
first=2
second=1
~~~

`StaticTracker` có một field `calls` cấp class; các lời gọi method static tác động cùng giá trị. Với `InstanceTracker`, hai tracker instances có các `calls` riêng nên dễ tạo một tracker mới cho mỗi test hoặc một phiên làm việc.

Không có nghĩa instance fields tự thread-safe. Nếu hai thread chia sẻ cùng một `InstanceTracker`, vẫn phải xét race condition tương tự. **Sự khác biệt là phạm vi chia sẻ**, không phải cơ chế tự đồng bộ.

## 28. Static reference và vòng đời object/garbage collection

Khi một static field trỏ tới object, object đó có thể tiếp tục reachable trong khi class runtime và reference path tương ứng còn tồn tại.

~~~java
class Cache {
    static Object recent;

    static void keep(Object value) {
        recent = value;
    }

    static void clear() {
        recent = null;
    }
}
~~~

Nếu `Cache.keep(bigObject)` chạy, `Cache.recent` giữ một reference đến object đó; biến local `bigObject` ra khỏi scope không tự làm object bị thu hồi.

`Cache.clear()` bỏ reference từ static field, nhưng:

- Object có thể vẫn còn reference từ nơi khác.
- JVM không bắt buộc thu hồi object ngay.
- `System.gc()` không cho phép người dùng “hủy ngay object X” một cách chắc chắn.

### Memory retention ở cache static

Một static `Map` thêm dữ liệu vô hạn mà không eviction có thể giữ rất nhiều objects reachable trong ứng dụng chạy lâu. Các dấu hiệu:

- Dữ liệu tạm thời gắn vào static registry.
- Cache giữ mọi user/session mà không có TTL hoặc size cap.
- Event listeners vẫn ở collection static sau khi component kết thúc.
- Tham chiếu class loader/callback giữ cả một graph objects không cần thiết.

Giải pháp không chỉ là gọi GC; phải **quản lý sở hữu, vòng đời và chính sách xóa reference** một cách có chủ đích.

## 29. Class loader: “một bản static” cần nói chính xác

Câu tóm tắt giáo khoa thường là “mỗi class có một bản static field”. Trong Java runtime có class loaders, cần diễn đạt chính xác hơn:

> Mỗi **class runtime được định nghĩa** có trạng thái static tương ứng. Hai class có cùng tên nhị phân nhưng được định nghĩa bởi **hai class loaders khác nhau** có thể là hai class runtime riêng và vì thế có static state riêng.

Ở chương trình console đơn giản với một class loader thông thường, cứ coi `Student.createdCount` là một giá trị chung cho các Student instances trong chương trình. Nhưng ở application server, plugin systems, test isolation hoặc environments dùng class loaders, “static là duy nhất trên toàn JVM bất kể class loader” là **không chính xác**.

### Module và class loader không phải một thứ

Java module (JPMS) kiểm soát namespace, readability, exports và một số quyền truy cập. Class loading/defining class có cơ chế riêng. Khi nói về static state, cần xét **class runtime identity** chứ không chỉ tên package/module viết trong source.

Không cần thực hiện custom class loading để học bài này; điều cần nhớ là tránh tuyên bố quá mức rằng static luôn là một biến toàn cục duy nhất tuyệt đối.

## 30. Static initialization có thể thất bại

Một static field initializer hoặc static initializer block có thể ném exception.

~~~java
class DangerousConfig {
    static final int PORT = parsePort();

    static int parsePort() {
        throw new IllegalArgumentException("invalid configuration");
    }
}
~~~

Đây là class minh họa. Khi class được khởi tạo theo một đường yêu cầu đọc `PORT`, lỗi xảy ra trong **class initialization**; JVM có thể báo `ExceptionInInitializerError` cho unchecked exception như ví dụ và đánh dấu class ở trạng thái khởi tạo thất bại.

Những lần sử dụng class sau đó có thể gặp `NoClassDefFoundError` do class đã thất bại khi khởi tạo, tùy bối cảnh. Vì thế không nên đặt những tác vụ nặng, I/O thiếu phương án xử lý hoặc dữ liệu phụ thuộc môi trường dễ lỗi trực tiếp trong static initializers một cách tùy tiện.

**Phân biệt:** Static initialization xảy ra theo vòng đời của class runtime; constructor xử lý tạo **từng instance**. Lỗi ở hai giai đoạn khác nhau có đường chẩn đoán và tác động khác nhau.

## 31. Static initialization xuyên nhiều class: phụ thuộc vòng tròn

Giả sử class A khởi tạo static field bằng cách đọc static field của B, còn B lại đọc A trong lúc A chưa hoàn tất. Trạng thái quan sát được có thể chứa **giá trị mặc định hoặc giá trị chưa hoàn chỉnh** theo quy tắc initialization.

Đây là một dạng **circular static initialization dependency**. Nó khó đọc hơn cả vòng phụ thuộc constructor thông thường vì liên quan class initialization timing.

Cách phòng tránh:

- Tránh static fields khởi tạo chéo phức tạp.
- Giữ static initialization đơn giản, không thực hiện hành vi phụ thuộc class khác chưa sẵn sàng.
- Đặt dependency vào object được tạo tường minh hoặc factory có thứ tự setup rõ.
- Cân nhắc lazy holder pattern hoặc service lifecycle khi thực sự cần khởi tạo lười.

Không dùng static initializer làm nơi orchestration một mạng lưới phụ thuộc lớn chỉ vì nó tự chạy.

## 32. Singleton và static field có giống nhau không?

**Singleton** là một mô hình thiết kế hướng tới một instance được chia sẻ theo phạm vi đã chọn; một static field có thể được dùng để giữ reference đến instance đó. Nhưng static field và singleton là **hai khái niệm khác nhau**:

- `static int count`: một field cấp class, **không phải singleton object**.
- `static final Service INSTANCE = new Service()`: một static reference tới một Service instance.
- `new Service()`: tạo một instance; nếu constructor public, vẫn có thể có nhiều Service instances khác.
- Singleton pattern yêu cầu ràng buộc đường tạo instance, lifetime và semantics rõ ràng.

### Ví dụ enum singleton

~~~java
enum AppRegistry {
    INSTANCE;

    private int requests;

    void register() {
        requests++;
    }

    int requests() {
        return requests;
    }
}
~~~

`AppRegistry.INSTANCE` là enum constant, biểu thị một enum instance của class runtime tương ứng. Đây là cách thể hiện singleton theo phạm vi class runtime thường dùng trong Java, nhưng field `requests` vẫn **mutable** và không tự thread-safe.

### Vì sao không mặc định dùng singleton cho mọi service?

Shared global singleton có thể:

- Làm test phụ thuộc trạng thái.
- Khó thay bằng implementation khác.
- Tăng coupling.
- Khó có cấu hình riêng theo tenant/session.
- Gây race nếu service mutable.

Khi chỉ cần **một service object trong một phạm vi ứng dụng được điều phối**, dependency injection và lifecycle scope có thể phù hợp hơn hardcoded global static field.

## 33. Static factory không đồng nghĩa static shared data

Một static factory method có thể tạo object mới **mỗi lần được gọi**:

~~~java
class Ticket {
    private final String code;

    private Ticket(String code) {
        this.code = code;
    }

    static Ticket of(String code) {
        return new Ticket(code);
    }
}
~~~

`Ticket.of("A")` là **static method** nhưng mỗi lần gọi ở ví dụ này trả reference đến một **Ticket instance mới**. Sự hiện diện của `static` trong method **không đồng nghĩa** method phải trả một object chung.

Ngược lại, một static factory có thể cache và trả cùng instance, tùy contract. Không thể suy ra **object identity** chỉ từ việc factory mang từ khóa `static`; phải đọc triển khai/hợp đồng cụ thể.

## 34. Static imports không tạo bản sao dữ liệu

Cú pháp:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
~~~

cho phép dùng `PI` và `max(...)` bằng tên đơn giản trong ngữ cảnh hợp lệ.

Nó **không sao chép static field** sang class đang import, cũng không tạo thêm state. `import static` chỉ ảnh hưởng cách tên được phân giải tại compile time và vẫn tuân theo access rules.

### Cần cẩn thận với trùng tên

Nếu class tự có `PI` hoặc import hai static members trùng tên, có thể phát sinh xung đột/ambiguity theo quy tắc Java. Dùng qualifier `Math.PI` thường giúp code dễ đọc hơn khi một file có nhiều static imports.

## 35. Static fields và access modifiers

Static fields có thể `private`, package-private, `protected` hoặc `public` theo các quy tắc Java.

Ví dụ:

~~~java
public final class Statistics {
    private static int requests;

    public static void recordRequest() {
        requests++;
    }

    public static int requests() {
        return requests;
    }
}
~~~

Class này kiểm soát việc thay counter bằng API `recordRequest`, thay vì cho caller `Statistics.requests = -10`.

Tuy nhiên, private + public methods **không tự giải quyết concurrency**: `requests++` vẫn có thể race. Nếu nhiều thread cùng dùng class, cần chọn atomic/synchronized strategy.

### Không lộ mutable collection cấp class

~~~java
public static final java.util.List<String> ALL_USERS =
        new java.util.ArrayList<>();
~~~

Đây là một **public static final reference tới mutable List**, không phải hằng số bất biến. Bất kỳ caller có quyền truy cập đều có thể `add/remove/clear`; class mất quyền kiểm soát registry. Thường tốt hơn là:

~~~java
private static final java.util.List<String> USERS =
        new java.util.ArrayList<>();

public static java.util.List<String> usersSnapshot() {
    return java.util.List.copyOf(USERS);
}
~~~

Các đoạn là class-member illustrations; cần đặt trong class hợp lệ. Với môi trường đa luồng phải đồng bộ đúng cách khi thêm và snapshot, không chỉ copy tùy ý.

## 36. Tình huống thiết kế: cùng một config cho toàn ứng dụng hay riêng mỗi instance?

Giả sử `EmailSender` cần cấu hình timeout:

**Phương án static:**

~~~java
class EmailSender {
    static int timeoutMillis = 5_000;
}
~~~

Mọi EmailSender instances dùng chung một timeout nếu chúng đọc field này. Thay `EmailSender.timeoutMillis` sẽ ảnh hưởng các instance khác.

**Phương án instance:**

~~~java
class EmailSender {
    private final int timeoutMillis;

    EmailSender(int timeoutMillis) {
        if (timeoutMillis <= 0) {
            throw new IllegalArgumentException("timeout must be positive");
        }
        this.timeoutMillis = timeoutMillis;
    }
}
~~~

Mỗi EmailSender có timeout riêng. Có thể tạo một shared configuration object rồi truyền reference của nó cho các sender nếu muốn chung theo một scope cụ thể.

### Khi nào chọn?

- Nếu timeout là một **constant bất biến** áp dụng mọi nơi theo thiết kế, static final có thể hợp lý.
- Nếu timeout được phép thay đổi theo môi trường/request/tenant, instance configuration hoặc dependency injection thường dễ kiểm soát hơn.
- Nếu yêu cầu thay đổi cấu hình nóng, thiết kế cần **publication/visibility** an toàn giữa threads và chính sách cập nhật.
- Nếu thư viện được dùng ở nhiều ứng dụng bên trong cùng JVM, static mutable config có thể gây va chạm không mong muốn.

## 37. Những lỗi thường gặp về static field

| Hiểu sai hoặc sai lầm | Hệ quả | Cách nhìn đúng |
| --- | --- | --- |
| “`static` là field của từng object.” | Dự đoán mỗi instance có bộ đếm riêng | Static field gắn với class runtime |
| “Mỗi `new` tăng mọi static counter.” | Sai khi constructor không cập nhật | Chỉ code thực thi mới đổi giá trị |
| “`Student b = a;` tạo instance mới.” | Đếm sai đối tượng | Chỉ sao chép reference |
| “`object.staticField` truy cập field của object đó.” | Dễ nhầm state shared với state riêng | Dùng `ClassName.staticField` |
| “`static final ArrayList` không sửa được.” | Người dùng vẫn có thể add/remove | Final giữ reference, List vẫn mutable |
| “`static` là thread-safe.” | Lost updates, race conditions | Dùng atomic/synchronization phù hợp |
| “`volatile int count; count++` atomic.” | Có thể mất cập nhật | Volatile không làm compound update atomic |
| “`Child.count` luôn là field khác `Parent.count`.” | Đếm sai khi chỉ inherited | Xác định class **khai báo** field |
| “Static field được override như method.” | Dự đoán dynamic dispatch sai | Field hiding theo compile-time resolution |
| “Một JVM chỉ có đúng một bản static cho cùng tên class.” | Sai với class loaders | Gắn với runtime class identity |
| “Đọc mọi `static final` đều kích hoạt initialization.” | Sai với constant variables | Phân biệt constant expression |
| “Static block chạy mỗi lần tạo object.” | Dự đoán log sai | Class initialization không lặp theo mỗi instance |
| “Static counter là số object còn sống.” | Không có tương ứng GC | Counter chỉ theo logic cập nhật của code |
| “Static field mất ngay khi method tạo object kết thúc.” | Hiểu sai reachability | Static reference có thể giữ object |
| “Biến cục bộ `static int` hợp lệ.” | Lỗi cú pháp Java | Dùng static field ở class scope |
| “Static factory luôn trả cùng object.” | Suy luận identity sai | Factory có thể tạo mới/cache tùy contract |
| “Static import tạo field mới.” | Hiểu sai chia sẻ state | Import chỉ ảnh hưởng phân giải tên |
| “Đặt currentUser static tiện cho web app.” | Trộn dữ liệu người dùng/request | Scope đúng cho từng phiên/tenant |
| “Private static field chắc chắn không có shared mutation.” | Public methods vẫn sửa field | Review mọi đường cập nhật |
| “Singleton tương đương stateless.” | Singleton vẫn có mutable state | Thiết kế thread-safety và lifecycle |

## 38. Quy trình phân tích một đoạn code có static field

Khi đọc mã Java nhiều instance và static members, hãy thực hiện:

**Bước 1 — Xác định class runtime và class khai báo field.** Nếu có inheritance, kiểm tra field được định nghĩa trong superclass hay subclass, có hiding không.

**Bước 2 — Phân loại field.** Ghi rõ `instance field` hay `static field`; với `static final` ghi thêm có mutable object reference không.

**Bước 3 — Xác định thời điểm class initialization.** Static initializers chạy theo thứ tự nào? Có constant variable đặc biệt không?

**Bước 4 — Đếm các lần `new` thật sự.** Mỗi constructor chạy những statement nào? Có ném exception, constructor chaining, factory hay alias?

**Bước 5 — Theo dõi state riêng và chung trong hai bảng:**

| Mốc thực thi | Instance #1 | Instance #2 | Static state |
| --- | --- | --- | --- |
| Ban đầu | Chưa có | Chưa có | Chưa được dùng/giá trị khởi tạo khi class initialized |
| `new X()` lần 1 | Field riêng | Chưa có | Có thể thay |
| `new X()` lần 2 | Giữ nguyên | Field riêng | Có thể thay |
| `instance1.method()` | Có thể thay | Không nhất thiết thay | Có thể thay nếu method ghi static |
| `X.staticMethod()` | Không cần instance | Không cần instance | Có thể đọc/ghi |

**Bước 6 — Dự đoán output dựa trên giá trị tại đúng thời điểm.** Nhớ Java class initialization, thứ tự câu lệnh và khả năng thread interleaving.

**Bước 7 — Kiểm tra hợp đồng thiết kế.** Dữ liệu thật sự nên chia sẻ toàn class, hay thuộc object/request/tenant? Có cần thread safety hoặc lifecycle cleanup không?

## 39. Bài tập 1 — Dự đoán counter với hai object

Cho:

~~~java
class Device {
    static int total;
    int uses;

    Device() {
        total++;
    }

    void use() {
        uses++;
    }
}
~~~

Caller:

~~~java
Device first = new Device();
Device second = new Device();
first.use();
first.use();
second.use();
Device alias = first;
alias.use();

System.out.println(Device.total);
System.out.println(first.uses);
System.out.println(second.uses);
~~~

**Đáp án:**

~~~text
2
3
1
~~~

Có hai lần `new Device()`, nên `total = 2`. `alias = first` không tạo mới. `uses` của first tăng ba lần qua `first` và `alias`; của second tăng một lần.

Đây là các **mảnh mã luyện tập**, cần ghép vào file Java hợp lệ (caller đặt trong method) để chạy.

## 40. Bài tập 2 — Chọn static hay instance?

Chọn loại field cho từng dữ liệu và giải thích:

- `MAX_CART_ITEMS = 100` áp dụng cho mọi giỏ trong một module.
- `cart.items` là danh sách sản phẩm riêng của từng giỏ.
- `currentUserId` cho mỗi HTTP request.
- `createdCount` của một ví dụ giáo khoa đếm constructor calls trong class.
- `currency` của từng đơn hàng.
- `logger` gắn với class.
- `lastSearchResult` có thể khác theo mỗi người dùng.

Gợi ý: `MAX_CART_ITEMS` và logger thường là ứng viên static final. Danh sách của từng cart, user của request, currency của order, last search theo người dùng **không nên là global static state**. Bộ đếm static có thể phù hợp nếu đã định nghĩa rõ scope và thread safety.

## 41. Bài tập 3 — Phân tích inheritance và field hiding

Cho:

~~~java
class Parent {
    static int value = 1;
}

class Child extends Parent {
    static int value = 2;
}
~~~

Nếu:

~~~java
Parent p = new Child();
Child c = new Child();

System.out.println(Parent.value);
System.out.println(Child.value);
System.out.println(p.value);
System.out.println(c.value);
~~~

**Đáp án:**

~~~text
1
2
1
2
~~~

Hai static fields được khai báo riêng, không override. `p.value` và `c.value` phụ thuộc kiểu compile-time của reference; nên dùng trực tiếp `Parent.value` và `Child.value` thay vì cú pháp qua instance.

## 42. Bài tập 4 — Thiết kế shared registry

Một class `ClubMember` muốn ghi nhận tên thành viên. Hãy thiết kế:

- Instance field `name`, mỗi member giữ tên riêng.
- Một registry cấp class ghi nhận tên đã đăng ký.
- Không lộ mutable List reference trực tiếp ra caller.
- Reject null/blank name.
- Có chính sách trùng tên rõ ràng.
- Có phương án cleanup và giới hạn dung lượng nếu registry sống lâu.
- Nếu có nhiều threads, dùng synchronization hoặc concurrent structure thích hợp.

Sau đó trả lời: registry có thật sự phải global/static không? Một `ClubRegistry` instance được truyền vào nhiều ClubMember hoặc service có thể **dễ test và quản lý scope hơn** nếu có nhiều câu lạc bộ riêng biệt.

## 43. Bài tập 5 — Sửa lỗi bộ đếm đa luồng

Mã chưa an toàn:

~~~java
class Hits {
    static int count;

    static void hit() {
        count++;
    }
}
~~~

Hãy thay bằng `private static final AtomicInteger` và public static method `hit()` dùng `incrementAndGet()`. Thử chạy nhiều threads cùng tăng rồi `join()` trước khi đọc; giải thích vì sao kết quả trở nên dự đoán được và tại sao `final` chỉ cố định reference AtomicInteger chứ không cố định giá trị của nó.

## 44. Bài tập 6 — Hành vi của static final constant

Cho:

~~~java
class Constants {
    static final int A = 5;
    static final Integer B = Integer.valueOf(6);

    static {
        System.out.println("initialized");
    }
}
~~~

Tự viết `main` in `Constants.A` rồi `Constants.B`. Dự đoán `A` là constant variable kiểu primitive, nên việc đọc nó có thể không kích hoạt class initialization; `B` không phải constant variable, nên việc truy cập sẽ khởi tạo class và in `initialized`. So sánh với `StaticConstantInitializationDemo` để kiểm chứng.

## 45. Checklist cuối bài

- [ ] Tôi biết static field thuộc class runtime chứ không phải từng instance.
- [ ] Tôi biết instance field thuộc trạng thái riêng của mỗi object.
- [ ] Tôi theo dõi đúng kết quả khi nhiều object cùng đọc/ghi static field.
- [ ] Tôi không coi alias assignment là lời gọi constructor.
- [ ] Tôi truy cập static field bằng `ClassName.field` khi phù hợp.
- [ ] Tôi phân biệt static field với static method và static nested class.
- [ ] Tôi hiểu class initialization khác với instance initialization.
- [ ] Tôi dự đoán được thứ tự static field initializers và static blocks.
- [ ] Tôi biết static field có giá trị mặc định trước các initializer tường minh.
- [ ] Tôi nhận diện constant variable và giới hạn của compile-time inlining.
- [ ] Tôi biết `static final` reference không làm mutable object trở nên bất biến.
- [ ] Tôi biết inherited static field không tự tạo bản sao ở subclass.
- [ ] Tôi hiểu field hiding và khác biệt với overriding instance methods.
- [ ] Tôi không dùng static để giữ dữ liệu riêng của từng người dùng/request.
- [ ] Tôi biết static mutable fields cần chiến lược thread-safety.
- [ ] Tôi hiểu `volatile` không biến `++` thành atomic.
- [ ] Tôi dùng `AtomicInteger`/synchronization phù hợp khi cần.
- [ ] Tôi biết static collections có thể giữ object reachable lâu.
- [ ] Tôi hiểu static state có thể lây giữa các bài test.
- [ ] Tôi biết class loaders có thể dẫn tới nhiều class runtime cùng tên với static states riêng.
- [ ] Tôi không nhầm static field với singleton pattern.
- [ ] Tôi biết static factory có thể tạo object mới theo từng lần gọi.
- [ ] Tôi tự biên dịch, chạy và giải thích stdout các chương trình Java 17+ trong bài.

**Kết luận:** Từ khóa `static` trên một **field** có nghĩa field đó thuộc về **class runtime**, không được nhân bản theo từng object instance. Đây là cách chia sẻ dữ liệu có chủ đích giữa các thể hiện, hữu ích cho constants và một số class-level resources. Nhưng **shared mutable state** đòi hỏi kiểm soát rõ ràng về quyền cập nhật, concurrency, isolation, lifecycle và phạm vi sử dụng. Nếu dữ liệu thuộc riêng từng object, request hoặc user, **instance field hoặc service state có scope phù hợp** thường là lựa chọn đúng hơn.
