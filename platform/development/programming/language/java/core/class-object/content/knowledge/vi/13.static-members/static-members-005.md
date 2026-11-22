# Ngữ cảnh `static` không có đối tượng `this` hiện tại trong Java

Trong Java, từ khóa **`this`** biểu thị **đối tượng hiện tại (*current instance*)** khi mã được thực thi trong một ngữ cảnh instance hợp lệ. Ngược lại, trong **ngữ cảnh `static`** của một class, **không có đối tượng `this` hiện tại**. Đó là lý do bạn không thể viết `this.field`, `this.method()` hoặc sử dụng `this` như một biểu thức trong một static method hay static initializer của class ấy.

Một static method thuộc về **class về mặt khai báo**, không cần gọi trên một object đã được tạo. Trong khi đó, instance method cần một **receiver**: một object cụ thể mà method sẽ đọc hoặc thay đổi trạng thái. Đây là phân biệt về **ngữ cảnh thực thi và receiver**, không có nghĩa static method “không bao giờ được làm việc với object”.

~~~java
class Counter {
    private int value;
    private static int totalCreated;

    Counter() {
        totalCreated++;
    }

    int getValue() {
        return this.value; // Hợp lệ: instance context
    }

    static int getTotalCreated() {
        // return this.value; // Không hợp lệ: static context
        return totalCreated;  // Hợp lệ: static field
    }
}
~~~

Đoạn trên là khai báo Java minh họa, chưa có `main`. Mọi object `Counter` có field `value` riêng. Field `totalCreated` là trạng thái chung của runtime class tương ứng, nên `getTotalCreated()` đọc nó mà không cần biết “Counter object hiện tại” là object nào.

**Mấu chốt:** không có `this` trong static context vì **Java không cung cấp current instance receiver ở đó**. Không phải vì class không thể có object, cũng không phải vì object bị `null`, mà là vì **cú pháp và ngữ nghĩa của static member không gắn sẵn với một instance**.

Bài học sử dụng Java 17+; tập trung vào static methods, static field initializers, static initialization blocks, `main`, `this`/`super`, cách truyền hoặc tạo receiver tường minh, lambda/method reference, nested classes, kế thừa và những lỗi compiler thường gặp.

## 1. Phân biệt class và object trước khi hiểu `this`

Một **class** định nghĩa kiểu dữ liệu, các member và cách khởi tạo object. Khi dùng `new Counter()`, chương trình tạo một **object** cụ thể của class đó. Hai object của cùng class có thể có state instance độc lập:

~~~java
Counter first = new Counter();
Counter second = new Counter();
~~~

Ở đoạn code fragment này, `first` và `second` có thể tham chiếu tới **hai objects khác nhau**. Nhưng static method `Counter.getTotalCreated()` không được gọi với một trong hai object làm receiver ngầm định.

Sơ đồ khái niệm:

~~~text
Class Counter
  static totalCreated ------------------------> 2
       |
       +-- new Counter() --> object A: value = 0
       |
       +-- new Counter() --> object B: value = 0

first -------> object A
second ------> object B

first.getValue(): this = object A
second.getValue(): this = object B
Counter.getTotalCreated(): không có this
~~~

Không nên hiểu sơ đồ là một layout vùng nhớ được JVM bảo đảm; nó mô tả **quan hệ sở hữu logic**. Một runtime class có static state theo ngữ cảnh class loading, còn mỗi object có các instance fields riêng.

### 1.1. `this` xuất hiện ở ngữ cảnh instance

~~~java
class Student {
    private final String name;

    Student(String name) {
        this.name = name;
    }

    String describe() {
        return "Student: " + this.name;
    }

    boolean same(Student other) {
        return this == other;
    }
}
~~~

- Trong constructor `Student(String name)`, `this.name` chỉ field thuộc object đang được xây dựng.
- Trong instance method `describe()`, `this` chỉ object nhận lời gọi, ví dụ `lan.describe()`.
- `this == other` so sánh identity của object nhận lời gọi với object được tham chiếu bởi `other`.
- Không có object mới được tạo chỉ vì có `this`: keyword này chỉ tham chiếu đến object hiện tại ở nơi cú pháp cho phép.

Nếu gọi một instance method hợp lệ, receiver phải được xác định. Một static method thì **không có tham số receiver ngầm định kiểu này**, cho nên không có `this` tương ứng.

## 2. Ngữ cảnh static là gì?

Những vị trí phổ biến của **static context** trong một class gồm:

- **Phần thân static method**, như `static void reset() { ... }`.
- **Static initializer block**, như `static { ... }`.
- **Biểu thức khởi tạo static field**, như `static int count = initialValue();`.

Trong các vị trí này, `this` hoặc `super` của enclosing class không có ý nghĩa như một current instance và không được dùng theo cách trong instance code.

~~~java
class AppState {
    private static int limit = 10;
    private int localLimit = 5;

    static {
        limit = 20;             // Hợp lệ: static field
        // this.localLimit = 1; // Lỗi: this trong static context
    }

    static int readLimit() {
        return limit;            // Hợp lệ
    }

    static int wrongRead() {
        // return localLimit;    // Lỗi: instance field thiếu receiver
        // return this.localLimit; // Lỗi: this không hợp lệ
        return 0;
    }
}
~~~

Đây là khai báo minh họa; `wrongRead()` cố tình trả 0 để file có thể biên dịch. Các lệnh sai đã được comment.

### 2.1. Static field khác instance field

| Khai báo | Thuộc về logic | Truy cập thích hợp |
| --- | --- | --- |
| `static int total;` | Runtime class | `ClassName.total` hoặc không định danh ở ngữ cảnh hợp lệ |
| `int value;` | Mỗi object | `object.value`, `this.value` trong instance context |
| `static void reset()` | Class | `ClassName.reset()` |
| `void increment()` | Object | `object.increment()` hoặc `this.increment()` |
| `static final int MAX = 10;` | Class, field final | `ClassName.MAX` |
| `final String id;` | Mỗi object, field final | `object.id` hoặc `this.id` trong class hợp lệ |

**`static` không đồng nghĩa `final`.** Static field có thể mutable hoặc final; instance field cũng có thể final hoặc mutable. Không có `this` trong static context là quy tắc độc lập với `final`.

## 3. Vì sao `this` không có sẵn trong static method?

Hãy nghĩ về lời gọi:

~~~java
int count = Counter.getTotalCreated();
~~~

Đây là một lời gọi **không cung cấp Counter object nào**. Một Counter object có thể chưa từng được tạo, nhưng static method vẫn có thể được gọi nếu class được tải và khởi tạo theo quy tắc tương ứng.

Nếu Java cho phép `this.value` ngay trong `getTotalCreated()`, nó phải trả lời “`value` của object nào?” — `first`, `second` hay một Counter hoàn toàn khác? Không có câu trả lời mặc định, vì không có instance receiver.

Ngược lại:

~~~java
Counter a = new Counter();
int value = a.getValue();
~~~

Lời gọi instance `a.getValue()` cung cấp receiver `a`. Khi body `getValue()` chạy, `this` chính là object được `a` tham chiếu tại lời gọi đó.

### 3.1. Static method có thể được gọi trước khi có object

~~~java
class Calculator {
    static int add(int a, int b) {
        return Math.addExact(a, b);
    }
}
~~~

`Calculator.add(2, 3)` trả 5 mà không cần `new Calculator()`. Không có `Calculator` object nào được truyền ngầm vào method, nên không có `this`.

### 3.2. Static method không tự sở hữu instance state

~~~java
class Room {
    private int capacity;

    Room(int capacity) {
        this.capacity = capacity;
    }

    static int unknownCapacity() {
        // return capacity; // Lỗi: non-static variable...
        return -1;
    }
}
~~~

`capacity` có giá trị riêng ở mỗi `Room` object. Một static method không thể tự suy ra nên chọn `capacity` của room nào; hãy chọn API rõ ràng hơn, chẳng hạn một **instance method** hoặc một **static method nhận Room parameter**.

## 4. Lỗi biên dịch điển hình: dùng `this` hoặc instance field từ static method

~~~java
class Wrong {
    private int score = 7;

    static int readScore() {
        // return this.score; // Lỗi compile
        return 0;
    }
}
~~~

Nếu bỏ comment `return this.score;` và bỏ dòng `return 0;`, compiler có thể báo lỗi tương tự:

~~~text
non-static variable this cannot be referenced from a static context
~~~

Wording có thể khác theo phiên bản compiler và vị trí source. Lỗi nằm ở keyword `this` không hợp lệ từ static context.

Một lỗi khác:

~~~java
class WrongAgain {
    private int score = 7;

    static int readScore() {
        // return score; // Lỗi compile: non-static variable ...
        return 0;
    }
}
~~~

Khi viết `score` không định danh, compiler cũng không tìm thấy một instance receiver ngầm định để đọc field.

**Hai lỗi cùng nguồn gốc nhưng biểu hiện khác nhau:**

1. `this.score`: cú pháp dùng `this` sai ngữ cảnh.
2. `score`: cố sử dụng non-static member từ static context mà không có object receiver.

**Không nên sửa bằng cách biến `score` thành static nếu mỗi object cần score riêng.** Thay đổi modifier để code biên dịch được có thể làm thay đổi hoàn toàn semantics dữ liệu, dẫn đến score bị chia sẻ ngoài ý muốn.

## 5. Giải pháp thứ nhất: đổi thành instance method khi hành vi thuộc từng object

Nếu một method phải đọc hoặc sửa trạng thái **của object đang nhận lời gọi**, nó nên là instance method:

~~~java
class Player {
    private int score;

    Player(int startingScore) {
        this.score = startingScore;
    }

    int getScore() {
        return this.score;
    }

    void addPoints(int points) {
        if (points < 0) {
            throw new IllegalArgumentException("Điểm âm");
        }
        this.score = Math.addExact(this.score, points);
    }
}
~~~

Caller tạo object và gọi method trên object:

~~~java
Player lan = new Player(3);
Player mai = new Player(10);

lan.addPoints(2);

System.out.println(lan.getScore()); // 5
System.out.println(mai.getScore()); // 10
~~~

Các dòng caller là code fragment đặt trong một method. `addPoints` là instance behavior vì hành động tăng điểm tác động **chỉ object nhận lời gọi**. `this.score` trong method vì thế có ý nghĩa rất rõ.

Nếu viết `static int getScore()` rồi chuyển `score` sang static để đọc được, hai Player objects sẽ bắt đầu chia sẻ một giá trị score chung — không đúng nếu yêu cầu là mỗi người có điểm riêng.

## 6. Giải pháp thứ hai: static method nhận tham chiếu object làm parameter

Một static method vẫn có thể đọc hoặc thay đổi instance state khi **được cung cấp một receiver object tường minh**.

~~~java
class Player {
    private int score;

    Player(int score) {
        this.score = score;
    }

    static int readScore(Player target) {
        return target.score;
    }
}
~~~

`Player.readScore(lan)` có receiver tường minh là `target`, không phải `this`. Vì code của static method nằm trong cùng class `Player`, nó có quyền truy cập private field `target.score` theo quy tắc Java.

Tuy nhiên, nếu mục tiêu chính của API là “đọc điểm của player hiện tại”, `lan.getScore()` thường tự nhiên hơn. Static method nhận object có thể phù hợp khi thực sự là utility hoặc thao tác so sánh hai đối tượng:

~~~java
class Player {
    private final int score;

    Player(int score) {
        this.score = score;
    }

    static boolean hasHigherScore(Player a, Player b) {
        return a.score > b.score;
    }
}
~~~

Không cần `this` vì method nhận **hai đối tượng** để so sánh, không có “object hiện tại” duy nhất cho phép chọn tùy tiện.

### 6.1. Static method không bị cấm gọi instance method

~~~java
class Greeting {
    private final String name;

    Greeting(String name) {
        this.name = name;
    }

    String greet() {
        return "Chào " + name;
    }

    static String from(Greeting target) {
        return target.greet(); // Hoàn toàn hợp lệ
    }
}
~~~

Trong `from`, `target.greet()` hợp lệ vì có một `Greeting` object (giả sử target non-null). Điều **không** hợp lệ là `this.greet()` vì chính `from` không có current instance receiver.

Nếu `target == null` thì `target.greet()` ném `NullPointerException`. Đó là lỗi dereference null, không phải lỗi dùng `this` trong static context.

## 7. Giải pháp thứ ba: static method có thể tạo object rồi sử dụng

Khi method static cần object mới, nó có thể gọi constructor hoặc static factory rồi thao tác với object đó:

~~~java
class Report {
    private final String title;

    Report(String title) {
        this.title = title;
    }

    String render() {
        return "Report: " + title;
    }

    static String createAndRender(String title) {
        Report report = new Report(title);
        return report.render();
    }
}
~~~

`Report.createAndRender("Java")` được gọi qua tên class. Trong method static:

1. `new Report(title)` tạo một **instance**.
2. Biến local `report` giữ tham chiếu đến instance ấy.
3. `report.render()` gọi instance method trên receiver **report**.
4. Không hề cần `this` ở static method; `this` hợp lệ khi code vào body của `render()` bởi đó là instance method.

Một static factory cũng có thể trả object thay vì xử lý ngay:

~~~java
class User {
    private final String name;

    private User(String name) {
        this.name = name;
    }

    static User of(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name rỗng");
        }
        return new User(name);
    }
}
~~~

`User.of("Lan")` là static factory; constructor `User(...)` và các instance methods của User vẫn có ngữ cảnh instance riêng. Static factory là một use case hợp lệ, không phải sự phủ nhận quy tắc “static không có `this`”.

## 8. Chương trình hoàn chỉnh: static method gọi instance method qua receiver

Tạo tệp **`StaticContextDemo.java`**:

~~~java
public class StaticContextDemo {
    static final class Account {
        private static int createdCount;

        private final String owner;
        private int balance;

        Account(String owner, int openingBalance) {
            if (owner == null || owner.isBlank()) {
                throw new IllegalArgumentException("owner rỗng");
            }
            if (openingBalance < 0) {
                throw new IllegalArgumentException("balance âm");
            }
            this.owner = owner;
            this.balance = openingBalance;
            createdCount++;
        }

        void deposit(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount phải dương");
            }
            this.balance = Math.addExact(this.balance, amount);
        }

        String description() {
            return this.owner + "=" + this.balance;
        }

        static int count() {
            return createdCount;
        }

        static void depositTo(Account target, int amount) {
            // Không có this ở đây; target là receiver tường minh.
            target.deposit(amount);
        }

        static Account create(String owner, int openingBalance) {
            return new Account(owner, openingBalance);
        }
    }

    public static void main(String[] args) {
        System.out.println("Initial = " + Account.count());

        Account lan = Account.create("Lan", 10);
        Account mai = new Account("Mai", 20);

        Account.depositTo(lan, 5);
        mai.deposit(3);

        System.out.println("Lan = " + lan.description());
        System.out.println("Mai = " + mai.description());
        System.out.println("Created = " + Account.count());

        try {
            Account.depositTo(lan, -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println("Final Lan = " + lan.description());
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 StaticContextDemo.java
java StaticContextDemo
~~~

**Stdout chính xác:**

~~~text
Initial = 0
Lan = Lan=15
Mai = Mai=23
Created = 2
Rejected = amount phải dương
Final Lan = Lan=15
~~~

**Giải thích chi tiết:**

1. `Account.count()` là static method, đọc static field `createdCount` mà không cần tạo Account object.
2. `Account.create(...)` là static factory. Nó thực hiện `new Account(...)`, làm constructor chạy. Trong constructor, `this.owner` và `this.balance` **hợp lệ**, vì constructor có current Account object.
3. `Account.depositTo(lan, 5)` là static method nhận parameter `target`. Trong method, `target.deposit(5)` chọn object Lan làm receiver; body instance `deposit` dùng `this.balance` trên object Lan.
4. `mai.deposit(3)` là instance method call trực tiếp trên một object khác; số dư Mai tăng độc lập.
5. `Account.count()` trả 2 vì có hai lần tạo Account thành công. Static field dùng chung, khác với instance field `balance`.
6. Lời gọi `depositTo(lan, -1)` truyền tiếp vào instance method, nhận exception trước khi sửa số dư. Do đó dòng cuối vẫn 15.

**Một ví dụ có static và instance cùng làm việc là bình thường.** Quan trọng là **method nào có receiver `this` và method nào cần receiver tường minh**, không phải “method static không được tương tác với instance object”.

Lưu ý nâng cao: `createdCount++` và cập nhật `balance` không đủ để làm class an toàn với nhiều thread. Chương trình minh họa có luồng thực thi tuần tự.

## 9. `static main`: điểm vào chương trình không có `this`

Ở một chương trình Java thông thường, entry point:

~~~java
public static void main(String[] args)
~~~

là **static method**. Vì vậy trong body của `main`, không thể viết `this.someMethod()` để gọi instance method của class chứa `main`.

Ví dụ:

~~~java
public class MainExample {
    private final String message;

    MainExample(String message) {
        this.message = message;
    }

    void printMessage() {
        System.out.println(this.message);
    }

    public static void main(String[] args) {
        // this.printMessage(); // Lỗi: this trong static context

        MainExample app = new MainExample("Java 17");
        app.printMessage(); // Hợp lệ: có receiver app
    }
}
~~~

Lưu tệp **`MainExample.java`** và chạy:

~~~bash
javac MainExample.java
java MainExample
~~~

Stdout:

~~~text
Java 17
~~~

Static `main` có thể tạo một object và chuyển việc sang instance behavior. Đây là một cấu trúc hợp lý khi chương trình muốn đặt ứng dụng vào một object quản lý state/dependencies thay vì gom toàn bộ hoạt động vào các static methods.

### 9.1. Vì sao `main` không tự tạo object chứa nó?

Java launcher cần điểm bắt đầu chạy chương trình theo hợp đồng xác định. Với chữ ký entry point phổ biến của Java 17, nó có thể gọi static `main` mà không phải chọn một constructor của class và tự tạo một receiver tùy ý. Vì vậy **chính code trong `main`** quyết định cần tạo những objects nào.

Không suy rộng rằng các method khác của chương trình cũng phải static. Instance methods và objects thường là nơi thích hợp để quản lý trạng thái theo từng request, user hoặc phiên làm việc.

## 10. `static` field initializer và `static` initialization block cũng không có `this`

Đây là điều dễ bị bỏ sót: **quy tắc static context không chỉ áp dụng cho static methods**. Nó cũng áp dụng với **static variable initializers** và **static initializer blocks**.

~~~java
class Settings {
    private static final String DEFAULT_REGION = "VN";
    private static String region = DEFAULT_REGION;

    private final String accountRegion;

    Settings(String accountRegion) {
        this.accountRegion = accountRegion;
    }

    static {
        region = region.toUpperCase();
        // this.accountRegion = "SG"; // Lỗi compile
    }

    static String selectedRegion() {
        return region;
    }
}
~~~

Static initializer có thể sử dụng static fields của class, gọi static methods hoặc làm việc với những objects được tạo/tìm qua tham chiếu tường minh. Nhưng **không có Settings instance nào được chọn ngầm định làm `this`**.

### 10.1. Static field initializer có thể gọi static helper

~~~java
class Config {
    static final String MODE = normalize("  safe  ");

    static String normalize(String input) {
        return input.trim().toUpperCase(java.util.Locale.ROOT);
    }
}
~~~

`MODE` được khởi tạo bằng lời gọi static helper. Ngược lại, nếu `normalize` là **instance method**, `static final String MODE = normalize("safe");` sẽ không hợp lệ vì thiếu receiver.

Tuy nhiên, static initializer vẫn có thể **tạo object và gọi instance method trên object đó**:

~~~java
class Config {
    static final String MODE =
            new StringBuilder("safe").toString();
}
~~~

Ở đây receiver của `toString()` là **StringBuilder object vừa tạo**, không phải một ngầm định `Config.this`.

### 10.2. Static initialization không chạy lại cho mỗi object

Một static initializer gắn với quá trình khởi tạo runtime class theo quy tắc Java, không chạy cho mỗi lần `new ClassName()`. Trong khi đó, instance field initializer và instance initializer block chạy trong quá trình khởi tạo **mỗi instance** bình thường.

Không có `this` trong static initialization vì nó không nằm trong quá trình thực thi trên **một current instance do Java chọn mặc định**.

## 11. Chương trình hoàn chỉnh: static initialization đối lập instance initialization

Tạo tệp **`InitializationContextDemo.java`**:

~~~java
public class InitializationContextDemo {
    static final class Widget {
        static int created;

        static {
            System.out.println("Static initializer");
        }

        private final int id;

        {
            // Instance initializer: đây là ngữ cảnh instance.
            System.out.println("Instance initializer");
        }

        Widget() {
            this.id = ++created;
            System.out.println("Constructor id=" + this.id);
        }

        int id() {
            return this.id;
        }

        static int count() {
            // return this.id; // Không hợp lệ trong static method
            return created;
        }
    }

    public static void main(String[] args) {
        System.out.println("Start");
        System.out.println("Count = " + Widget.count());

        Widget first = new Widget();
        Widget second = new Widget();

        System.out.println("IDs = " + first.id()
                + "," + second.id());
        System.out.println("Final count = " + Widget.count());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 InitializationContextDemo.java
java InitializationContextDemo
~~~

Stdout chính xác:

~~~text
Start
Static initializer
Count = 0
Instance initializer
Constructor id=1
Instance initializer
Constructor id=2
IDs = 1,2
Final count = 2
~~~

Đọc trình tự:

1. `Start` được in bởi `main`.
2. `Widget.count()` là một active use của Widget khiến JVM khởi tạo class nếu cần; static initializer in `Static initializer`. Không có Widget instance được tạo ở bước này.
3. Static method `count()` đọc static field `created` ban đầu là 0.
4. Mỗi lời gọi `new Widget()` chạy instance initializer rồi constructor. Trong constructor, `this.id` hợp lệ vì object đang khởi tạo hiện diện.
5. `id` là instance final field; mỗi Widget object có id riêng. `created` là static field chung, tăng khi các constructors chạy.

Tuy nhiên, không suy luận “static initializer chạy chính xác một lần cho mọi JVM trong mọi hoàn cảnh” khi có nhiều class loaders hoặc vấn đề initialization failure. Với một runtime class bình thường được khởi tạo thành công, static initialization không lặp lại chỉ vì tạo nhiều instances.

## 12. `super` cũng không có ngữ cảnh receiver trong static method

Trong một **instance method của subclass**, `super.method()` có thể gọi implementation của superclass thích hợp trên current object:

~~~java
class Parent {
    String label() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String label() {
        return "Child";
    }

    String combined() {
        return this.label() + "/" + super.label();
    }
}
~~~

`new Child().combined()` trả `"Child/Parent"`. Cả `this` và `super` được sử dụng trong một instance context hợp lệ của Child.

Nhưng trong static method của Child:

~~~java
class Parent {
    String label() {
        return "Parent";
    }
}

class Child extends Parent {
    static String wrong() {
        // return super.label(); // Lỗi: super không hợp lệ tại đây
        return "N/A";
    }
}
~~~

Static method không có một current Child instance để lấy phần superclass của object ấy. `super` không có nghĩa “gọi một object Parent bất kỳ”, và không làm xuất hiện current instance khi `this` không tồn tại.

**Chú ý về constructor:** `super(...)` trong constructor là **explicit constructor invocation** tuân thủ quy tắc riêng, khác với `super.someMethod()` trong instance method. Không dùng constructor invocation trong static method.

## 13. `this(...)` khác `this.method()`, và cả hai không dành cho static method

Hai cú pháp:

- `this.method(arguments)`: **gọi instance method** trên current object.
- `this(arguments)`: **ủy quyền tới constructor khác cùng class** (*constructor chaining*), dùng trong constructor ở vị trí được Java 17 cho phép.

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle() {
        this(1, 1); // Constructor chaining
    }

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    int area() {
        return this.width * this.height;
    }

    static Rectangle square(int size) {
        // this(size, size); // Không hợp lệ từ static method
        return new Rectangle(size, size);
    }
}
~~~

Trong Java 17, `this(1, 1)` phải là **câu lệnh đầu tiên của constructor body** khi dùng lời gọi constructor tường minh. `square(...)` là static factory; nó phải gọi `new Rectangle(size, size)` để tạo object mới, thay vì gọi `this(...)` như constructor đã có current instance.

Không nên cố “sửa lỗi không có `this` trong static context” bằng cách đổi `this.method()` sang `this(...)`. Chúng là hai cấu trúc ngôn ngữ khác nhau.

## 14. Một static method có thể được gọi qua biến object, nhưng vẫn không có `this`

Java cho phép cú pháp:

~~~java
class Utility {
    static String version() {
        return "v1";
    }
}

Utility value = new Utility();
System.out.println(value.version());
~~~

Cách gọi `value.version()` **được chấp nhận** trong tình huống này, nhưng method vẫn là **static**, không nhận `value` như current instance receiver. Nên viết:

~~~java
System.out.println(Utility.version());
~~~

để thể hiện đúng ownership. Compiler/IDE có thể cảnh báo khi truy cập static method thông qua instance.

### 14.1. Trường hợp null làm người mới học hiểu lầm

~~~java
class Utility {
    static String version() {
        return "v1";
    }
}

Utility ref = null;
System.out.println(ref.version()); // v1
~~~

Dù `ref == null`, lời gọi static method được phân giải qua kiểu `Utility` và không dereference một Utility object để chạy body `version()`. **Điều đó không tạo `this`** trong `version()` và không có nghĩa là gọi instance method trên null thì an toàn.

Với `ref.instanceMethod()` nếu method thực sự là instance, receiver null sẽ gây `NullPointerException`.

Cần lưu ý Java vẫn đánh giá biểu thức bên trái dấu chấm theo quy tắc lời gọi. Nếu đó là một biểu thức phức tạp có side effect hoặc lỗi, tác động/lỗi của chính biểu thức ấy vẫn có thể xảy ra. **Hãy truy cập static member qua tên class** để tránh hiểu nhầm và tránh đánh giá receiver expression không cần thiết.

## 15. Static method trong kế thừa: method hiding không phải overriding

Vì static method **không có instance receiver dùng cho dynamic dispatch**, static methods cùng chữ ký ở subclass được xử lý như **method hiding**, khác với instance method **overriding**.

Tạo tệp **`StaticDispatchDemo.java`**:

~~~java
public class StaticDispatchDemo {
    static class Parent {
        static String type() {
            return "Parent-static";
        }

        String identity() {
            return "Parent-instance";
        }
    }

    static final class Child extends Parent {
        static String type() {
            return "Child-static";
        }

        @Override
        String identity() {
            return "Child-instance";
        }
    }

    public static void main(String[] args) {
        Parent ref = new Child();
        Child child = new Child();

        System.out.println("Parent = " + Parent.type());
        System.out.println("Child = " + Child.type());
        System.out.println("Ref static = " + ref.type());
        System.out.println("Child static = " + child.type());
        System.out.println("Ref instance = " + ref.identity());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StaticDispatchDemo.java
java StaticDispatchDemo
~~~

Stdout:

~~~text
Parent = Parent-static
Child = Child-static
Ref static = Parent-static
Child static = Child-static
Ref instance = Child-instance
~~~

**Giải thích:**

- `ref` có **compile-time type Parent** nhưng trỏ tới một Child object.
- `ref.type()` chọn static method Parent theo compile-time type, không có implicit `this` để dispatch đến Child.
- `ref.identity()` là instance call, nên dynamic dispatch theo runtime object Child chọn `Child.identity()`.
- `Child.type()` hide `Parent.type()`, không override nó. Không dùng `@Override` để đánh dấu static method hiding.

Nếu một subclass cố khai báo static method để “override” instance method của superclass cùng chữ ký, compiler từ chối; hướng ngược lại cũng không hợp lệ. Sự khác biệt static/instance là phần thiết yếu của method declaration, không được tự do đổi trên đường override.

## 16. Static nested class: có thể có `this` của **chính nested object**

Đây là ngoại lệ quan trọng để tránh phát biểu quá rộng:

> Không có `this` **trong static context**, nhưng một **instance method của static nested class** vẫn có `this` — vì method đó chạy trên một **nested class instance**.

~~~java
class Container {
    private final String name;

    Container(String name) {
        this.name = name;
    }

    static class Item {
        private final int id;

        Item(int id) {
            this.id = id;
        }

        String describe() {
            return "Item#" + this.id; // Hợp lệ
        }
    }
}
~~~

`Item` là static nested class: không có enclosing `Container` instance ngầm định. Tuy nhiên, một `new Container.Item(7)` tạo một **Item object**, và `Item.describe()` là instance method có `this` của **Item**.

Phân biệt:

- `this.id` trong `Item.describe()`: hợp lệ, vì `this` là **Item instance**.
- `Container.this.name` trong `Item.describe()`: **không hợp lệ**, vì static nested class không tự có enclosing Container instance.
- `this` trong `static void helper()` của Item: vẫn không hợp lệ, vì **chính method helper là static**.

### 16.1. Static nested class khác non-static inner class

~~~java
class Outer {
    private final String code;

    Outer(String code) {
        this.code = code;
    }

    class Inner {
        String describe() {
            return Outer.this.code;
        }
    }
}
~~~

Một non-static inner class như `Inner` gắn với một enclosing `Outer` instance, nên `Outer.this` có ý nghĩa trong ngữ cảnh hợp lệ. Tạo object kiểu này thường dùng `outer.new Inner()`.

Còn static nested class được tạo bằng `new Outer.Nested()` (nếu constructor/access cho phép) và không cần một Outer instance. Modifier `static` ở **khai báo nested class** không có nghĩa “mọi method nằm trong nested class đều là static”; phải xét modifier của **từng method**.

## 17. Lambda trong static context không tự tạo `this`

Java lambda có quy tắc *lexical scoping* cho `this`: khi một lambda được viết trong **instance context**, `this` thường chỉ đến enclosing instance như tại nơi lambda được khai báo. Nhưng khi một lambda xuất hiện trong **static context**, không có enclosing instance `this` để lambda tự “mượn”.

~~~java
class TaskOwner {
    private final String name;

    TaskOwner(String name) {
        this.name = name;
    }

    Runnable instanceTask() {
        return () -> System.out.println(this.name);
    }

    static Runnable wrongTask() {
        // return () -> System.out.println(this.name);
        // Lỗi: this không hợp lệ từ static context
        return () -> System.out.println("Static task");
    }
}
~~~

`instanceTask()` là instance method nên lambda sử dụng `this.name` hợp lệ và **bắt giữ tham chiếu đến enclosing TaskOwner object theo ngữ nghĩa lambda**. `wrongTask()` là static; lambda không tạo một current TaskOwner object ngầm định để có `this.name`.

**Cách đúng từ static:** nhận object vào parameter rồi đóng trên reference ấy:

~~~java
static Runnable forOwner(TaskOwner owner) {
    java.util.Objects.requireNonNull(owner, "owner");
    return () -> System.out.println(owner.name);
}
~~~

Đây là method fragment khai báo **bên trong TaskOwner**. Lambda được trả có thể giữ tham chiếu `owner` để dùng về sau; cần chú ý vòng đời callback nếu lưu lâu dài.

### 17.1. `this::method` cũng cần enclosing instance

Một **bound method reference**:

~~~java
this::handle
~~~

ràng buộc method với current receiver, nên không thể được viết để chỉ instance method trên một `this` không tồn tại trong static method của enclosing class.

Thay vào đó:

~~~java
class Dispatcher {
    void handle() {
        System.out.println("Handled");
    }

    static Runnable bind(Dispatcher target) {
        return target::handle;
    }
}
~~~

`Dispatcher.bind(dispatcher)` trả một `Runnable` gắn với object `dispatcher`. Khi gọi `run()`, `handle()` được gọi trên dispatcher. Đây là **receiver tường minh**, không phải `this` trong static context.

Ngoài bound method reference, có thể dùng **unbound instance method reference** dạng `ClassName::instanceMethod` khi functional interface nhận receiver thích hợp làm tham số. Ví dụ `java.util.function.Function<String, String> f = String::trim;` là hợp lệ; lời gọi `f.apply(" A ")` dùng String argument làm receiver. Không có enclosing `this` nào được tạo ra bởi cú pháp này.

## 18. Anonymous class tạo object có `this` riêng, ngay cả khi nó được tạo trong static method

Trường hợp này phải giải thích chính xác: **một static method không có `this` của enclosing class**, nhưng nó vẫn có thể **khai báo và tạo một anonymous class object**, mà **instance method của anonymous class có `this` của object anonymous ấy**.

~~~java
public class AnonymousContextDemo {
    public static Runnable makeTask() {
        return new Runnable() {
            private int calls;

            @Override
            public void run() {
                this.calls++;
                System.out.println("Calls=" + this.calls);
            }
        };
    }

    public static void main(String[] args) {
        Runnable task = makeTask();
        task.run();
        task.run();
    }
}
~~~

Lưu tệp **`AnonymousContextDemo.java`** và chạy:

~~~bash
javac AnonymousContextDemo.java
java AnonymousContextDemo
~~~

Stdout:

~~~text
Calls=1
Calls=2
~~~

`makeTask()` là static, **không có `AnonymousContextDemo.this`**. Nhưng phần thân `run()` là instance method của một anonymous class triển khai `Runnable`. Trong `run()`, `this.calls` hợp lệ và trỏ đến **anonymous object**. Điều này không mâu thuẫn với quy tắc: **`this` hợp lệ ở một instance context mới, không phải ở static context bao ngoài**.

Một **local class** được khai báo trong static method cũng có thể tạo object với instance methods dùng `this` của chính local class. Cần phân biệt **nơi định nghĩa class** với **ngữ cảnh method bên trong class mới**.

## 19. Static context không phải “không có object ở đâu cả”

Trong cùng chương trình Java, có thể có rất nhiều object đang tồn tại khi một static method thực thi. Việc thiếu `this` chỉ có nghĩa static method **không được Java gắn sẵn một object của enclosing class làm receiver**.

Ví dụ:

~~~java
class Printer {
    private final String prefix;

    Printer(String prefix) {
        this.prefix = prefix;
    }

    void print(String text) {
        System.out.println(prefix + text);
    }

    static void send(Printer printer, String text) {
        printer.print(text);
    }
}
~~~

Một static method có thể nhận `Printer` từ parameter, gọi instance method qua `printer`, tạo mới Printer, lấy Printer từ collection hoặc factory. Nhưng khi có nhiều Printer objects:

~~~java
Printer a = new Printer("A:");
Printer b = new Printer("B:");
~~~

static method `send(...)` không tự biết object nào “hiện tại” để viết `this.print(...)`. Caller quyết định bằng đối số `a` hay `b`.

**Từ khóa cần nhớ là receiver, không phải sự hiện diện của object trong heap.**

## 20. Không nên sửa lỗi static context bằng cách đưa dữ liệu instance lên static bừa bãi

Một lỗi thiết kế dễ gặp:

~~~java
class UnsafeUserSession {
    static String currentUser;

    static String greeting() {
        return "Chào " + currentUser;
    }
}
~~~

Code này biên dịch và không cần `this`, nhưng `currentUser` là **state chung cho class**, không phải tên người dùng riêng cho mỗi session. Với nhiều người dùng, việc gán từ session A có thể khiến session B đọc sai người dùng.

Thiết kế phù hợp hơn:

~~~java
class UserSession {
    private final String username;

    UserSession(String username) {
        this.username = java.util.Objects.requireNonNull(username);
    }

    String greeting() {
        return "Chào " + this.username;
    }
}
~~~

Nếu một static entry point cần xử lý nhiều sessions, nó tạo/nhận các `UserSession` objects rồi gọi `session.greeting()`.

**Tiêu chí chọn thiết kế:**

- Dữ liệu thuộc **mỗi object riêng**? Dùng instance field và instance behavior.
- Dữ liệu là **hằng số/chính sách chung**? Có thể dùng static member, chú ý tính immutable.
- Method là **utility thuần từ tham số**? Static method có thể phù hợp.
- Method cần **polymorphic dispatch** hoặc state của current object? Instance method thường tự nhiên hơn.
- Code muốn dùng instance state từ static? **Đưa receiver rõ ràng** vào API thay vì chuyển field sang static chỉ để biên dịch.

## 21. `static synchronized` không khóa một instance `this`

Một hệ quả sâu hơn: static method không có current instance, nên từ khóa `synchronized` trên static method sử dụng monitor của **Class object** tương ứng, không dùng monitor của một instance `this`.

~~~java
class Counter {
    private static int shared;
    private int own;

    static synchronized void incrementShared() {
        shared++;
    }

    synchronized void incrementOwn() {
        own++;
    }
}
~~~

Trong ví dụ này:

- `static synchronized incrementShared()` lấy monitor tương ứng với `Counter.class`.
- `synchronized incrementOwn()` là instance synchronized method, lấy monitor của **receiver object** khi gọi.
- Hai monitor **khác nhau**; khóa trên một instance không mặc nhiên khóa static method và ngược lại.
- Nhiều Counter objects khác nhau có các object monitors khác nhau, nhưng cùng dùng static lock để truy cập chung `shared` theo method trên.
- Cần bảo đảm mọi đường truy cập đến shared/instance mutable state tuân thủ cùng một synchronization protocol thích hợp. Chỉ thêm synchronized ở một method không tự sửa lỗi của các đường truy cập khác.

Trong static context không thể viết:

~~~java
// synchronized (this) { ... } // Lỗi: this không hợp lệ
~~~

Nếu cần explicit class-level lock, có thể cân nhắc `synchronized (Counter.class) { ... }` khi có lý do rõ; trong nhiều thiết kế, lock private riêng hoặc atomic variable giúp tránh coupling ngoài ý muốn với public Class monitor.

### 21.1. `Counter.class` không phải `this`

`Counter.class` là biểu thức class literal, nhận một `Class<Counter>` object đại diện cho runtime class theo quy tắc tương ứng. Static method có thể dùng biểu thức này; nhưng nó **không phải current Counter instance** và không cho phép đọc một instance field `value` tùy ý.

Không dùng `Counter.class` như “thay thế của `this`” cho mọi truy cập instance state.

## 22. Static method có cần đồng thời thread-safe vì không có `this` không?

Không. Thiếu `this` không mang lại thread safety.

~~~java
class Metrics {
    static int count;

    static void increment() {
        count++; // Read-modify-write không atomic
    }
}
~~~

Nhiều thread đồng thời gọi `Metrics.increment()` trên cùng runtime class có thể bị **lost updates**. Static mutable field là shared state, nên cần xác định khả năng concurrent access.

Một dạng phù hợp hơn cho counter:

~~~java
class Metrics {
    private static final java.util.concurrent.atomic.AtomicInteger COUNT =
            new java.util.concurrent.atomic.AtomicInteger();

    static int increment() {
        return COUNT.incrementAndGet();
    }

    static int current() {
        return COUNT.get();
    }
}
~~~

`AtomicInteger` cung cấp thao tác atomic cho counter. `static final` ở đây chỉ ngăn gán lại tham chiếu field `COUNT`; bản thân object AtomicInteger vẫn có trạng thái cập nhật được.

Instance fields cũng có thể bị race nếu **nhiều thread chia sẻ cùng object**. `this` không phải lock và absence of `this` không phải synchronization mechanism. Hai quyết định độc lập: **member thuộc class hay object**, và **mô hình đồng bộ cho state đó**.

## 23. Các vấn đề access control và static context

Static member có thể `private`, package-private, `protected` hoặc `public` theo quy tắc khai báo member thích hợp. **Khả năng truy cập không quyết định có `this` hay không**.

~~~java
class TokenStore {
    private static String secret = "internal";

    private String owner;

    TokenStore(String owner) {
        this.owner = owner;
    }

    static String redactedLabel() {
        return "protected";
    }

    static String describe(TokenStore store) {
        return store.owner; // Hợp lệ trong cùng class
    }
}
~~~

`describe` đọc private **instance field** của một TokenStore object vì nó nhận parameter `store` và code nằm trong class khai báo field. Nó không cần `this`.

Ngược lại, `redactedLabel` không truy cập đến current TokenStore object chỉ vì nó cũng nằm cùng class. `private static` field `secret` có thể được gọi/đọc bởi code trong TokenStore theo quy tắc access, nhưng không tự xuất hiện thành instance property riêng.

Một static method có thể dùng `new TokenStore(...)` trong khi constructor đang chạy có `this`; đây là **hai call frames/ngữ cảnh khác nhau**.

## 24. Quy tắc phạm vi nhìn thấy `this` khi có nhiều cấp nested classes

Cần phân biệt:

- **Outer instance method:** `this` là outer object.
- **Non-static inner instance method:** `this` là inner object, `Outer.this` có thể là enclosing outer object.
- **Static nested instance method:** `this` là static nested object; không có implicit `Outer.this`.
- **Static method của bất kỳ class nào:** không có `this` của class ấy.
- **Lambda trong instance context:** `this` lexical, chỉ instance của ngữ cảnh bao phù hợp.
- **Lambda trong static context:** không tự có outer `this`.
- **Instance method của anonymous/local class tạo trong static method:** có `this` của object anonymous/local class.

Một chương trình minh họa đối chiếu:

~~~java
public class NestedThisDemo {
    private final String name;

    NestedThisDemo(String name) {
        this.name = name;
    }

    class Inner {
        String who() {
            return "Inner: " + NestedThisDemo.this.name;
        }
    }

    static class Nested {
        private final String id;

        Nested(String id) {
            this.id = id;
        }

        String who() {
            return "Nested: " + this.id;
        }
    }

    public static void main(String[] args) {
        NestedThisDemo outer = new NestedThisDemo("Outer");
        NestedThisDemo.Inner inner = outer.new Inner();
        NestedThisDemo.Nested nested = new NestedThisDemo.Nested("N");

        System.out.println(inner.who());
        System.out.println(nested.who());

        // System.out.println(this.name); // Lỗi trong static main
    }
}
~~~

Lưu thành **`NestedThisDemo.java`**, chạy:

~~~bash
javac -encoding UTF-8 NestedThisDemo.java
java NestedThisDemo
~~~

Stdout:

~~~text
Inner: Outer
Nested: N
~~~

`Inner.who()` truy cập enclosing instance thông qua `NestedThisDemo.this`, còn `Nested.who()` truy cập **chính Nested object** thông qua `this`. Trong `static main`, không có current `NestedThisDemo` instance: `outer` là biến local được tạo tường minh, không phải `this`.

## 25. Lỗi thường gặp và cách sửa

| Lỗi hoặc nhầm lẫn | Giải thích và hướng xử lý |
| --- | --- |
| Viết `this.value` trong `static void f()` | Không có current instance; dùng instance method hoặc nhận object làm receiver |
| Viết `value` trong static method khi value là instance field | Thiếu receiver; dùng `object.value` với access hợp lệ |
| Viết `this.method()` trong `static main` | `main` không có `this`; tạo object rồi gọi `object.method()` |
| Viết `super.method()` trong static method | Không có current subclass instance; chuyển hành vi sang instance context phù hợp |
| Viết `this(...)` trong static factory | `this(...)` chỉ là constructor invocation; dùng `new ClassName(...)` hoặc factory khác |
| Nghĩ static method không thể tạo object | Có thể gọi constructor, nhận tham chiếu và gọi instance methods qua receiver tường minh |
| Nghĩ gọi `ref.staticMethod()` nghĩa là có current `this = ref` | Static method vẫn không có `this`; ưu tiên `ClassName.staticMethod()` |
| Đổi tất cả instance fields thành static để compiler hết báo lỗi | Có thể biến state từng object thành global shared state và gây bug |
| Nghĩ `static nested class` không thể dùng `this` ở bất kỳ đâu | Instance methods của nested class vẫn có `this` riêng |
| Nghĩ `Outer.this` hợp lệ trong static nested class | Static nested class không có enclosing Outer instance ngầm định |
| Nghĩ lambda khai báo ở static method tự sinh enclosing `this` | Lambda dùng lexical `this`, không tự tạo outer object |
| Nghĩ anonymous object tạo từ static method không có `this` | Instance method của anonymous object có `this` của chính anonymous class |
| Nghĩ static method bị override theo runtime class | Static method bị hiding, thường chọn theo compile-time type |
| Nghĩ `static synchronized` khóa mọi instance | Nó khóa Class object tương ứng; instance synchronized method dùng instance monitor |
| Nghĩ `static final List` là bất biến sâu | Final ngăn gán lại reference, không tự làm mutable object bất biến |
| Nghĩ thiếu `this` làm static method thread-safe | Mutable static state vẫn có thể race, cần đồng bộ phù hợp |

## 26. Bài tập tự kiểm tra

**Câu 1.** Vì sao `static int getScore() { return this.score; }` không biên dịch khi `score` là instance field?

**Đáp án:** Static method không có current object receiver, nên `this` không hợp lệ. Muốn đọc score của object, viết instance method hoặc nhận một `Player` parameter rồi đọc qua parameter.

**Câu 2.** `static void f(Player p) { p.addPoints(1); }` có hợp lệ không?

**Đáp án:** Có, khi `p` khác null, method có quyền truy cập và chữ ký `addPoints` phù hợp. Receiver tường minh là `p`, không phải `this` trong `f`.

**Câu 3.** Có thể gọi `new Player().getScore()` trong static method không?

**Đáp án:** Có, nếu constructor và method truy cập được. `new Player()` tạo receiver tường minh; không làm static method có `this`.

**Câu 4.** `public static void main(String[] args)` có thể đọc instance field bằng `this.field` không?

**Đáp án:** Không. `main` là static; tạo object và gọi `object.field` hoặc chuyển hành vi vào instance method.

**Câu 5.** Vì sao `static { this.value = 1; }` sai?

**Đáp án:** Static initializer là static context, không có current instance. Nó chỉ có thể thao tác với instance field khi có một receiver object tường minh hợp lệ.

**Câu 6.** Instance field initializer có dùng `this` được không?

**Đáp án:** Trong một instance initialization context hợp lệ, `this` có thể xuất hiện theo quy tắc Java. Cần cẩn thận không làm lộ object chưa khởi tạo đầy đủ hoặc gọi overridable methods thiếu kiểm soát.

**Câu 7.** `this(1, 2)` có phải lời gọi instance method `this` không?

**Đáp án:** Không. Đó là lời gọi constructor khác cùng class, chỉ dùng trong constructor theo quy tắc vị trí của Java 17.

**Câu 8.** Nếu `Parent p = new Child();`, `p.staticType()` chọn Parent hay Child khi hai class có static method cùng chữ ký?

**Đáp án:** Chọn static method theo compile-time type Parent (hiding), không theo runtime object Child như instance method overriding.

**Câu 9.** Trong instance method của static nested class, `this.id` hợp lệ không? `Outer.this.id` thì sao?

**Đáp án:** `this.id` hợp lệ nếu là instance field của nested class và truy cập đúng. `Outer.this` không có sẵn vì static nested class không tự có enclosing Outer instance.

**Câu 10.** Lambda được khai báo trong static method có thể dùng `this` của enclosing class không?

**Đáp án:** Không. Lambda không tự tạo enclosing instance; nếu cần object, nhận object hoặc tạo object rồi đóng trên reference tường minh.

**Câu 11.** Vì sao anonymous class được tạo trong static method vẫn có thể viết `this.count++` ở instance method của nó?

**Đáp án:** `this` trong anonymous class instance method là **anonymous object hiện tại**, không phải object của enclosing class chứa static method.

**Câu 12.** Static synchronized method khóa monitor nào?

**Đáp án:** Class object (`ClassName.class`) tương ứng với runtime class, không phải monitor của một instance `this`. Instance synchronized method dùng receiver object.

**Câu 13.** Static method thiếu `this` có đảm bảo thread-safe không?

**Đáp án:** Không. Shared mutable static fields vẫn có thể bị data race; cần synchronization hoặc atomic operations theo yêu cầu.

**Câu 14.** `Utility u = null; u.staticMethod();` có tự ném NPE vì `u` null không?

**Đáp án:** Không phải do một instance receiver bị dereference để chạy static method; trong trường hợp biểu thức receiver chỉ là biến `u`, lời gọi static method vẫn có thể chạy. Nhưng cú pháp đó dễ gây hiểu nhầm và nên viết `Utility.staticMethod()`.

**Câu 15.** Khi một static method gọi `target.instanceMethod()`, `this` bên trong `instanceMethod()` là gì?

**Đáp án:** Là chính object mà `target` tham chiếu ở lời gọi đó, miễn lời gọi hợp lệ. Static method gọi nó vẫn không có `this` riêng.

## 27. Checklist khi sửa lỗi “non-static variable this cannot be referenced from a static context”

1. **Nhìn vào vị trí lỗi:** code đang nằm trong static method, static field initializer hay static initializer block?
2. **Xác định member đang dùng:** member được khai báo `static` hay instance?
3. **Nếu dùng `this`:** có current instance hợp lệ không? Trong static context của enclosing class là không.
4. **Nếu dữ liệu thuộc mỗi object:** giữ instance field và chuyển logic sang instance method khi đó là hành vi tự nhiên.
5. **Nếu method phải static:** thêm receiver object tường minh bằng parameter, local variable, factory hoặc object được tạo phù hợp.
6. **Không chuyển dữ liệu per-user/per-request sang static chỉ để code biên dịch:** xem lại ownership và vòng đời.
7. **Nếu đang ở `main`:** tạo/nhận object rồi gọi instance method trên object đó.
8. **Nếu định gọi constructor:** dùng `new ClassName(...)` trong static method; `this(...)` chỉ trong constructor.
9. **Nếu dùng `super`:** kiểm tra liệu thao tác đó cần một current subclass object không.
10. **Nếu code có lambda/nested/anonymous class:** xác định chính xác `this` thuộc enclosing instance nào; static nested không tự có `Outer.this`.
11. **Nếu gặp static method hiding:** đừng suy luận lời gọi phụ thuộc runtime receiver như overridable instance method.
12. **Nếu có static shared mutable state:** xem thread-safety và thời gian sống dữ liệu riêng với câu hỏi về `this`.
13. **Kiểm tra tên và API:** `ClassName.staticMethod()` rõ hơn gọi static qua một instance variable.
14. **Chạy compiler khi thử lỗi:** bỏ comment từng dòng sai để xem Java từ chối vì ngữ cảnh nào; đừng sửa nhiều vấn đề cùng lúc rồi suy đoán nguyên nhân.

**Kết luận:** Static context của Java **không có đối tượng `this` hiện tại**, bởi nó không được thực thi trên một receiver instance ngầm định của enclosing class. Điều này áp dụng cho **static methods, static field initializers và static initializer blocks**. Static code vẫn có thể tạo/nhận object và gọi instance methods bằng **receiver tường minh**. Trong khi đó, instance methods và constructors có `this` theo ngữ cảnh hợp lệ; instance methods của static nested/anonymous classes cũng có `this` của **chính object của chúng**, không phải enclosing class đang ở static context. Khi gặp lỗi compiler liên quan `this`, hãy xác định **ai sở hữu state** và **receiver cần là object nào**, thay vì vội đổi mọi member thành static.
