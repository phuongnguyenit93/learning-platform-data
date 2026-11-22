# Truy cập thành viên đối tượng từ ngữ cảnh static trong Java

Một **thành viên đối tượng** (*instance member*) như instance field hoặc instance method gắn với **một thể hiện cụ thể** của lớp. Ngược lại, **thành viên `static`** thuộc về lớp theo cách khai báo của Java: có thể sử dụng khi **không tồn tại thể hiện nào**.

Do đó, trong một **ngữ cảnh static** (*static context*), Java **không cung cấp ngầm đối tượng nhận lời gọi** (*implicit receiver*) để đọc instance field hoặc gọi instance method. Muốn truy cập, cần **một tham chiếu đối tượng phù hợp** (hoặc đối tượng được tạo tường minh), rồi thực hiện thao tác **qua tham chiếu ấy**.

Ví dụ không hợp lệ:

```java
class Counter {
    private int value = 10;

    void increment() {
        value++;
    }

    static void printCurrent() {
        // System.out.println(value); // SAI: instance field
        // increment();                // SAI: instance method
        // System.out.println(this);   // SAI: không có this
    }
}
```

Cách sửa:

```java
static void printCurrent(Counter counter) {
    System.out.println(counter.value);
    counter.increment();
    System.out.println(counter.value);
}
```

Đây là phương thức `static` **nhận một đối tượng `Counter` làm tham số**. Việc phương thức thuộc lớp không cấm nó làm việc với object; điều bị cấm là **giả định có một receiver instance ngầm định** khi thực tế không có.

**Quy tắc cốt lõi:**
- Trong instance method: có thể dùng `this.field`, `this.method()` hoặc tên ngắn như `field`, `method()` khi hợp lệ.
- Trong static method: **không có `this` của lớp chứa phương thức**; phải chỉ rõ object như `counter.field`, `counter.method()`.
- `private`/`public` và `static` là **những khía cạnh khác nhau**: private quyết định **ai được phép truy cập**, static quyết định **có cần đối tượng nhận hay không**.
- Trong `public static void main(String[] args)`, bạn cũng phải tạo/nhận một đối tượng trước khi truy cập instance state của nó.

Bài viết dùng Java 17+, phân biệt đoạn minh họa với chương trình đầy đủ, kèm lệnh `javac`/`java`, stdout, nguyên nhân lỗi và cách thiết kế API phù hợp.

## 1. Phân biệt thành viên static và thành viên đối tượng

Ví dụ:

```java
class Student {
    static int totalStudents;
    String name;

    Student(String name) {
        this.name = name;
        totalStudents++;
    }

    void printName() {
        System.out.println(name);
    }

    static int getTotalStudents() {
        return totalStudents;
    }
}
```

Trong lớp trên:

| Thành viên | Loại | Cần receiver instance để dùng trực tiếp? |
| --- | --- | --- |
| `name` | Instance field | Có nếu mã không ở trong instance context tương ứng |
| `printName()` | Instance method | Có nếu mã không có implicit receiver |
| `totalStudents` | Static field | Không, có thể dùng `Student.totalStudents` khi quyền truy cập cho phép |
| `getTotalStudents()` | Static method | Không, có thể dùng `Student.getTotalStudents()` |
| `Student(String)` | Constructor | Được gọi để khởi tạo thể hiện, không phải static method |

Nếu tạo hai đối tượng:

```java
Student first = new Student("An");
Student second = new Student("Bình");
```

`first.name` và `second.name` là hai trường hợp đọc **trạng thái của các thể hiện khác nhau**. Trong khi đó `Student.getTotalStudents()` trả số lượng được lưu trong static field dùng chung của lớp.

**Static field không đồng nghĩa “hằng số”**: `static int totalStudents` vẫn có thể thay đổi. Ngược lại, một instance field `final` có thể bất biến về phép gán lại field nhưng vẫn gắn với **từng đối tượng**.

## 2. Thế nào là static context?

Các ví dụ phổ biến của static context trong Java:

- **Thân static method**, kể cả `main` hoặc static factory.
- **Static initialization block**: `static { ... }`.
- **Static field initializer** khi biểu thức không thuộc instance context.
- Một số vị trí mang ngữ cảnh static do cú pháp/quy tắc của Java, chẳng hạn các phần của khai báo static nested type.

Trong các ngữ cảnh trên, **`this` và `super` không có ý nghĩa receiver của lớp đang xét** và không thể truy cập instance field/method chỉ bằng cách gọi tên như khi ở một instance method.

Ví dụ:

```java
class Example {
    int instanceValue = 7;
    static int classValue = 9;

    static void show() {
        System.out.println(classValue);  // Hợp lệ
        // System.out.println(instanceValue); // SAI
    }

    void showInstance() {
        System.out.println(instanceValue); // Hợp lệ
        System.out.println(classValue);    // Hợp lệ
    }
}
```

Một instance method có **implicit receiver `this`**, nên `instanceValue` ở đây tương đương `this.instanceValue` khi không có tên bị che khuất. Còn static method thì không.

### Ngữ cảnh static không phải vùng “chỉ được gọi static”

Nói “static method không bao giờ gọi instance method” là **sai**. Nó có thể gọi instance method khi có object:

```java
static void display(Example example) {
    example.showInstance(); // Hợp lệ
}
```

Điều kiện là biến `example` có kiểu phù hợp, tham chiếu đến đối tượng hợp lệ lúc thực thi, và method được quyền truy cập.

## 3. Static context cần receiver tường minh khi thao tác instance

Static method không có **receiver ngầm** của một instance, nên không biết phải sửa state của đối tượng nào. Xét:

~~~java
class Light {
    boolean on;

    static void turnOn(Light receiver) {
        receiver.on = true;
    }
}
~~~

Cách sử dụng đặt trong một method hoặc block phù hợp:

~~~java
Light kitchen = new Light();
Light bedroom = new Light();
Light.turnOn(kitchen);
~~~

Chỉ `kitchen.on` được cập nhật; `bedroom.on` không đổi. Đây là giải pháp nhận **object reference làm parameter**, không phải chuyển field `on` sang static hay gọi một instance member trực tiếp không có receiver. Java vẫn **truyền giá trị tham chiếu theo giá trị**.

Nếu một static method viết `on = true` hoặc `this.on = true` mà không có instance receiver thích hợp, compiler báo lỗi; `super.instanceMethod()` cũng không thể dùng như một cách thay receiver từ static method.

Bài **“Ngữ cảnh static không có đối tượng this hiện tại”** giải thích sâu hơn ngữ nghĩa `this`, `super`, lambda, anonymous class và nested instance context. Trọng tâm tại đây là **cách gọi/đọc/sửa instance members hợp lệ từ static method** bằng object có chủ đích.

## 4. Ví dụ Java 17 hoàn chỉnh: `main` truy cập thành viên instance

Lưu toàn bộ thành **`StaticAccessDemo.java`**:

```java
class Counter {
    private int value;
    private static int created;

    Counter(int initial) {
        value = initial;
        created++;
    }

    void increment() {
        value++;
    }

    int value() {
        return value;
    }

    static int created() {
        return created;
    }

    static void report(Counter counter) {
        counter.increment();
        System.out.println("Value: " + counter.value());
        System.out.println("Created: " + created());
    }
}

public class StaticAccessDemo {
    public static void main(String[] args) {
        Counter first = new Counter(3);
        Counter second = new Counter(10);

        Counter.report(first);
        Counter.report(second);

        System.out.println("First: " + first.value());
        System.out.println("Second: " + second.value());
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 StaticAccessDemo.java
java StaticAccessDemo
```

**Stdout chính xác:**

```text
Value: 4
Created: 2
Value: 11
Created: 2
First: 4
Second: 11
```

Giải thích:

1. `main` là static method, nên không có một `StaticAccessDemo` receiver ngầm định.
2. `new Counter(3)` và `new Counter(10)` tạo hai instance `Counter`, mỗi instance giữ field `value` riêng.
3. Static field `Counter.created` tăng lên `2` sau hai lần gọi constructor.
4. `Counter.report(first)` là lời gọi static method. Bên trong `report`, tên tham số `counter` cung cấp receiver để gọi instance method `increment()` và `value()`.
5. `Counter.report(second)` sửa object thứ hai, không sửa `first`.
6. `created()` là static method nên có thể gọi không qua instance bên trong chính lớp `Counter`; mã ngoài gọi `Counter.created()` nếu method public hoặc quyền truy cập khác phù hợp.

Đoạn này đặt các lớp trong cùng tệp và default package để chạy độc lập. Trong thư viện có package riêng, hãy chọn quyền truy cập phù hợp với caller.

## 5. Cách truy cập instance member hợp lệ từ static context

Thông thường có bốn cách thực tế:

| Cách | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| **Nhận object làm tham số** | `static void show(User u) { u.print(); }` | Static utility xử lý một object do caller cung cấp |
| **Tạo object tường minh** | `User u = new User(); u.print();` | Có lý do tạo instance mới |
| **Dùng một object giữ trong static field** | `current.print();` với `static User current` | Thiết kế có shared/static state thật sự |
| **Nhận object từ factory/repository** | `User u = repo.find(id); u.print();` | Object có vòng đời được quản lý nơi khác |

**Cần phân biệt:** “Có object” không có nghĩa “object nào cũng hợp lệ”. Kiểm tra kiểu tĩnh, quyền truy cập, null và vòng đời instance.

### 5.1. Nhận tham số: cách dễ kiểm thử

```java
class Printer {
    static void printName(Person person) {
        System.out.println(person.name());
    }
}
```

Với class `Person` có instance method `name()`, static method `printName` không cần lưu global state mà chỉ sử dụng đối tượng được truyền vào.

Ưu điểm: dependency thể hiện rõ trong chữ ký, dễ dùng các instance khác nhau, dễ unit test hơn so với một static field toàn cục.

### 5.2. Tạo instance trong static method

```java
static void run() {
    Worker worker = new Worker();
    worker.execute();
}
```

Cách này hợp lệ nếu `Worker` có constructor khả dụng và `execute()` là instance method. Tuy nhiên, **đừng tự tạo object mới** khi chương trình cần trạng thái của object đã tồn tại ở caller: tạo mới có thể làm mất ý nghĩa dữ liệu.

### 5.3. Static field giữ một instance reference

```java
class ServiceHost {
    private static final Worker DEFAULT_WORKER = new Worker();

    static void runDefault() {
        DEFAULT_WORKER.execute();
    }
}
```

`DEFAULT_WORKER` là **static field**, nhưng giá trị của nó là **tham chiếu đến một instance `Worker`**. Vì vậy `DEFAULT_WORKER.execute()` hợp lệ.

Đây không phải trường hợp `execute()` tự trở thành static. Receiver vẫn là object `Worker`.

**Lưu ý:** shared mutable object có thể gây coupling, khó unit test và race condition. Chỉ dùng static owner nếu vòng đời chia sẻ toàn cục thực sự là yêu cầu thiết kế.

## 6. Phân biệt `ClassName.staticMethod()` và `object.instanceMethod()`

Trong Java, cách viết thường rõ ràng nhất là:

```java
Math.max(3, 5);           // Static method của Math
String text = "Java";
text.length();           // Instance method của String
```

- Với **static method**, nêu tên lớp/interface khi thích hợp.
- Với **instance method**, nêu receiver tham chiếu đến object.
- Một số cú pháp khác được Java cho phép, nhưng có thể gây hiểu lầm.

Ví dụ Java có thể cho viết `object.staticMethod()` trong vài tình huống, nhưng đó **không phải dynamic dispatch theo object**. Người đọc sẽ dễ hiểu nhầm, nên ưu tiên `ClassName.staticMethod()`.

Ngược lại, gọi `ClassName.instanceMethod()` mà không có object không thể hợp lệ chỉ vì method là public.

Ví dụ sai:

```java
class User {
    void printName() {
        System.out.println("An");
    }
}

// User.printName(); // SAI: printName là instance method
```

Cách đúng:

```java
User user = new User();
user.printName();
```

## 7. `private` và `static` là hai quy tắc độc lập

Đây là một nguồn nhầm lẫn quan trọng:

```java
class Account {
    private int balance = 100;

    private void deposit(int amount) {
        balance += amount;
    }

    static void process(Account account) {
        account.deposit(25);
        System.out.println(account.balance);
    }
}
```

`process` **được phép** gọi `account.deposit(25)` và đọc `account.balance` vì mã đang nằm **trong chính lớp `Account`**, nơi có quyền truy cập các private members của các instance `Account`.

**Nhưng** đoạn sau vẫn sai:

```java
static void invalid() {
    // deposit(25);              // SAI: thiếu instance receiver
    // System.out.println(balance); // SAI: thiếu instance receiver
}
```

Quyền private **không cấm** static method trong cùng lớp dùng private instance members của một object được nêu rõ. Ngược lại, việc một field là public **không cho phép** gọi trực tiếp tên field instance từ static context nếu thiếu receiver.

### Chương trình hoàn chỉnh kiểm tra private access

Lưu **`PrivateFromStaticDemo.java`**:

```java
class Account {
    private int balance;

    Account(int balance) {
        this.balance = balance;
    }

    private void add(int amount) {
        balance += amount;
    }

    static void transfer(Account from, Account to, int amount) {
        from.balance -= amount;
        to.add(amount);
    }

    int balance() {
        return balance;
    }
}

public class PrivateFromStaticDemo {
    public static void main(String[] args) {
        Account first = new Account(100);
        Account second = new Account(20);

        Account.transfer(first, second, 30);

        System.out.println(first.balance());
        System.out.println(second.balance());

        // first.balance = 0; // SAI tại đây: private của Account
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PrivateFromStaticDemo.java
java PrivateFromStaticDemo
```

Stdout:

```text
70
50
```

`Account.transfer` là static method nhưng được quyền xử lý **hai object Account cụ thể** và truy cập private state của chúng. Ví dụ chỉ minh họa access/static receiver; trong hệ thống tài chính thật cần kiểm tra số tiền, số dư, lỗi tràn và đồng bộ giao dịch.

## 8. Không thể dùng instance field để khởi tạo static field nếu thiếu object

Ví dụ sai:

```java
class Configuration {
    int timeout = 30;

    // static int defaultTimeout = timeout; // SAI
}
```

`timeout` là instance field. Một static field initializer có thể chạy khi lớp được khởi tạo, **trước khi có instance nào** của `Configuration`. Vì vậy không tồn tại receiver ngầm định.

Một số cách đúng:

```java
class Configuration {
    static final int DEFAULT_TIMEOUT = 30;
    int timeout = DEFAULT_TIMEOUT;

    static int initialTimeout() {
        return DEFAULT_TIMEOUT;
    }
}
```

Hoặc khi thực sự muốn đọc instance:

```java
static int fromNewInstance() {
    Configuration config = new Configuration();
    return config.timeout;
}
```

**Cảnh báo thiết kế:** `new Configuration()` tạo một object mới, không đọc state của object `Configuration` cụ thể mà caller đã có. Nếu yêu cầu là xử lý cấu hình của caller, nên nhận `Configuration` làm tham số.

## 9. Static initialization block và thứ tự khởi tạo

Một **static initializer** có thể thực hiện tính toán, tạo object và gán static fields khi lớp được khởi tạo. Nó **không** được dùng ngầm instance fields của lớp đang khai báo.

Ví dụ:

```java
class Registry {
    private static final Worker DEFAULT;

    static {
        DEFAULT = new Worker();
        DEFAULT.execute(); // Có object receiver tường minh
    }
}
```

`DEFAULT.execute()` hợp lệ vì static field `DEFAULT` chứa một tham chiếu `Worker`. Đoạn trên chỉ minh họa, giả sử `Worker` có constructor và method phù hợp.

### 9.1. Ví dụ Java 17 có stdout ổn định

Lưu **`StaticInitializationDemo.java`**:

```java
class Task {
    private int runs;

    void execute() {
        runs++;
    }

    int runs() {
        return runs;
    }
}

class TaskRegistry {
    static final Task DEFAULT_TASK;

    static {
        DEFAULT_TASK = new Task();
        DEFAULT_TASK.execute();
        System.out.println("Registry ready");
    }

    static void runDefault() {
        DEFAULT_TASK.execute();
    }

    static int totalRuns() {
        return DEFAULT_TASK.runs();
    }
}

public class StaticInitializationDemo {
    public static void main(String[] args) {
        System.out.println("Before access");
        TaskRegistry.runDefault();
        System.out.println(TaskRegistry.totalRuns());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 StaticInitializationDemo.java
java StaticInitializationDemo
```

Stdout:

```text
Before access
Registry ready
2
```

Diễn giải:
1. `main` in dòng đầu.
2. Lời gọi static method `TaskRegistry.runDefault()` làm lớp `TaskRegistry` được khởi tạo trước khi lời gọi thực hiện nếu lớp chưa được khởi tạo.
3. Static block tạo object `Task`, gọi `execute()` một lần rồi in `Registry ready`.
4. `runDefault()` gọi `execute()` thêm lần nữa trên **cùng object**.
5. `totalRuns()` trả `2`.

Static initialization chạy theo **quy tắc khởi tạo lớp** của Java, không có nghĩa JVM luôn chạy mọi static block của mọi class ngay khi ứng dụng khởi động.

### 9.2. Tránh phụ thuộc vòng khởi tạo

Nếu static initializers của nhiều lớp gọi chéo nhau, trạng thái có thể bị quan sát khi **chưa khởi tạo đầy đủ**. Đối tượng tham chiếu qua static field có thể chưa được gán như mong muốn trong một chuỗi khởi tạo phức tạp.

Hãy giữ static initialization đơn giản, tránh side effects khó kiểm soát; cân nhắc lazy holder, dependency injection hoặc initialization method có hợp đồng rõ khi vòng đời phức tạp.

## 10. Static method có thể gọi instance method qua một static reference

Một static field **có thể chứa object**:

```java
class Coordinator {
    private static final Worker WORKER = new Worker();

    static void execute() {
        WORKER.work();
    }
}
```

Ở đây:
- `WORKER` là một static field và được truy cập trực tiếp từ static method `execute`.
- Giá trị field là tham chiếu đến một instance `Worker`.
- `WORKER.work()` là lời gọi instance method trên object được field trỏ tới.

**Không có quy tắc “static không được chạm tới object”.** Quy tắc thật là **instance access phải có receiver phù hợp**.

### Null receiver

Nếu static field tham chiếu `null`:

```java
static Worker worker;

// Trong static method:
worker.work(); // Có thể ném NullPointerException lúc chạy
```

Phép truy cập có thể **biên dịch hợp lệ** vì `worker` là biến tham chiếu kiểu `Worker`, nhưng lúc chạy receiver `null` thì không có object để gọi instance method.

Phân biệt:
- **Lỗi biên dịch:** gọi instance member không có receiver.
- **Lỗi runtime:** có receiver expression về mặt cú pháp/kiểu, nhưng giá trị thực tế `null`.

## 11. `main` là static method: vì sao cần tạo object?

Entrypoint kinh điển:

```java
public static void main(String[] args) {
    // ...
}
```

không nhận đối tượng của lớp chứa nó qua tham số implicit. JVM gọi phương thức này theo cơ chế static.

Ví dụ đầy đủ **`MainObjectDemo.java`**:

```java
public class MainObjectDemo {
    private String greeting;

    MainObjectDemo(String greeting) {
        this.greeting = greeting;
    }

    void greet() {
        System.out.println(greeting);
    }

    public static void main(String[] args) {
        // greet(); // SAI: main không có this
        MainObjectDemo app = new MainObjectDemo("Xin chào Java");
        app.greet();
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 MainObjectDemo.java
java MainObjectDemo
```

Stdout:

```text
Xin chào Java
```

Ở đây `app` được tạo một cách tường minh, nên `app.greet()` hợp lệ. Nếu `main` cần xử lý một đối tượng được framework truyền vào hoặc lấy từ repository, có thể nhận/lấy object đó thay vì tự tạo.

**Đừng nhầm:** biến `args` được truyền vào `main` là một **tham số tham chiếu đến mảng `String[]`**. Nó cũng không phải implicit receiver của `MainObjectDemo`.

## 12. Instance method gọi static method: chiều ngược lại

Instance context thường có thể gọi static members có thể truy cập:

```java
class Temperature {
    private double celsius;

    Temperature(double celsius) {
        this.celsius = celsius;
    }

    double fahrenheit() {
        return toFahrenheit(celsius); // Static helper
    }

    static double toFahrenheit(double value) {
        return value * 9 / 5 + 32;
    }
}
```

`fahrenheit()` là instance method, có receiver `this` nên đọc được field `celsius`. Nó gọi static helper `toFahrenheit`, truyền **giá trị field của instance hiện tại**.

Để tăng độ rõ ràng, cũng có thể viết `Temperature.toFahrenheit(celsius)`.

Một static helper như `toFahrenheit(double)` thường dễ kiểm thử vì kết quả chỉ phụ thuộc đối số, không cần object state.

**Lưu ý:** chiều ngược lại (static method muốn đọc `celsius`) phải nhận một `Temperature` phù hợp và truy cập qua receiver như `temperature.celsius`.

## 13. Instance fields trùng tên tham số: `this` có ích nhưng static không dùng `this`

Trong instance constructor/method:

```java
class Person {
    private String name;

    Person(String name) {
        this.name = name;
    }

    void rename(String name) {
        this.name = name;
    }
}
```

`this.name` phân biệt **field của object hiện tại** với tham số `name`.

Trong static method:

```java
static void rename(Person person, String name) {
    person.name = name;
}
```

Mã bên trong `Person` có quyền truy cập field `name` private của đối tượng `person` được truyền vào, nhưng **không có `this.name`** vì đang ở static context.

Sự khác nhau chỉ ở cách xác định **receiver**:
- Instance method: implicit `this` có sẵn.
- Static method: caller phải cung cấp hoặc code phải tạo/lấy receiver.

## 14. Method overloading: static và instance không phân biệt chỉ bằng `static`

Hai method có cùng tên và **cùng danh sách tham số** không thể đồng thời tồn tại trong cùng lớp chỉ vì một method là static còn method kia là instance.

Ví dụ lỗi:

```java
class InvalidOverload {
    void execute(int value) {
    }

    // static void execute(int value) { } // SAI: trùng chữ ký
}
```

Modifier `static` **không tạo một chữ ký overload khác**. Overloading hợp lệ yêu cầu danh sách tham số khác theo quy tắc ngôn ngữ:

```java
class ValidOverload {
    void execute(int value) {
    }

    static void execute(String text) {
    }
}
```

Nhưng khi gọi `ValidOverload.execute(1)`, compiler không được phép coi instance method `execute(int)` là static chỉ vì có overload `execute(String)`. Chọn overload và kiểm tra tính hợp lệ của lời gọi vẫn theo các quy tắc kiểu và static/instance.

### Dynamic dispatch không áp dụng cho static method

Instance method được override có thể thực thi implementation theo runtime class của receiver; static method cùng tên có thể bị **hiding** nhưng không override động.

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

Với `Parent ref = new Child();`, viết `Parent.label()` cho ý định rõ ràng; cách gọi `ref.label()` có thể hợp lệ nhưng dùng static binding dựa trên kiểu compile-time, không có dispatch theo `Child`.

Tránh gọi static methods qua instance reference vì dễ che khuất bản chất static.

## 15. Kế thừa: static method không tự có `super`

Giả sử:

```java
class Parent {
    void show() {
        System.out.println("Parent");
    }
}

class Child extends Parent {
    static void report(Child child) {
        child.show(); // Hợp lệ: child là object receiver
        // super.show(); // SAI trong static method
    }
}
```

Trong static method `report`, không có `Child.this` hoặc `super` implicit. Có thể gọi `child.show()` nếu nhận được object.

Trong instance method:

```java
void reportInstance() {
    super.show(); // Hợp lệ trong instance context phù hợp
}
```

Đây là cú pháp đặc biệt cho gọi implementation từ superclass. Không thay bằng `((Parent) child).show()` nếu kỳ vọng cố định chạy bản `Parent.show()` khi method bị override; cast không vô hiệu hóa dynamic dispatch.

### Chương trình chạy được

Lưu **`StaticInheritanceDemo.java`**:

```java
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

    static String inspect(Parent value) {
        return value.label();
    }

    String parentLabel() {
        return super.label();
    }
}

public class StaticInheritanceDemo {
    public static void main(String[] args) {
        Child child = new Child();
        Parent parentView = child;

        System.out.println(Child.inspect(parentView));
        System.out.println(child.parentLabel());
        System.out.println(parentView.label());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 StaticInheritanceDemo.java
java StaticInheritanceDemo
```

Stdout:

```text
Child
Parent
Child
```

`inspect` là static method nhận tham chiếu `Parent`; instance method `label()` được gọi trên runtime object `Child` nên dispatch về `Child.label()`. Còn `parentLabel()` là **instance method** của `Child` nên được phép dùng `super.label()` để gọi bản cha.

## 16. Static nested class và inner class: receiver của lớp ngoài

Một **static nested class** không mang một tham chiếu ngầm định đến **instance của outer class**. Vì thế static nested class muốn truy cập instance field của outer object cần **tham chiếu outer tường minh**.

```java
class House {
    private String address;

    House(String address) {
        this.address = address;
    }

    static class LabelPrinter {
        static void print(House house) {
            System.out.println(house.address);
        }
    }
}
```

`house.address` hợp lệ vì đã có receiver. Static nested class `LabelPrinter` cũng nằm trong cùng nest với `House` nên được phép truy cập private member theo quy tắc Java.

Nhưng trong static nested class:

```java
// System.out.println(address);   // Không có House instance implicit
// System.out.println(House.this.address); // Không có enclosing House instance
```

### Non-static inner class khác

```java
class House {
    private String address;

    House(String address) {
        this.address = address;
    }

    class LabelPrinter {
        void print() {
            System.out.println(House.this.address);
        }
    }
}
```

Non-static member inner class có liên hệ với một instance outer phù hợp, nên có thể dùng `House.this` trong instance context của inner class.

**Lưu ý:** bản thân `this` bên trong instance method của inner class chỉ **inner object**, không phải outer object. Muốn chỉ định outer thì dùng `Outer.this` khi hợp lệ.

### 16.1. Chương trình đầy đủ đối chiếu hai loại nested class

Lưu **`NestedStaticAccessDemo.java`**:

```java
public class NestedStaticAccessDemo {
    private final String name;

    NestedStaticAccessDemo(String name) {
        this.name = name;
    }

    static class StaticPrinter {
        static void show(NestedStaticAccessDemo target) {
            System.out.println("Static: " + target.name);
        }
    }

    class InnerPrinter {
        void show() {
            System.out.println("Inner: " + NestedStaticAccessDemo.this.name);
        }
    }

    public static void main(String[] args) {
        NestedStaticAccessDemo outer =
                new NestedStaticAccessDemo("Java");

        StaticPrinter.show(outer);
        InnerPrinter inner = outer.new InnerPrinter();
        inner.show();
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 NestedStaticAccessDemo.java
java NestedStaticAccessDemo
```

Stdout:

```text
Static: Java
Inner: Java
```

Hai dòng cho cùng tên nhưng **đường lấy receiver khác nhau**: static nested method nhận tham số, inner instance method có enclosing instance đã gắn khi tạo `outer.new InnerPrinter()`.

## 17. Interface static methods và default methods

Trong interface:

```java
interface Validator {
    static boolean validName(String value) {
        return value != null && !value.isBlank();
    }

    default boolean hasValidName() {
        return Validator.validName(name());
    }

    String name();
}
```

- `validName` là static method của interface, không có `this` và nhận chuỗi cần kiểm tra qua tham số.
- `hasValidName` là **default instance method**; nó có receiver hiện tại nên có thể gọi instance method `name()`.
- `name()` là abstract instance method mà class triển khai phải cung cấp public implementation.

Không thể viết trong `validName`:

```java
// return !name().isBlank(); // SAI: thiếu object triển khai cụ thể
```

Nếu muốn validate một object qua static method, khai báo tham số:

```java
static boolean valid(Validator validator) {
    return validator != null && validName(validator.name());
}
```

### Chương trình Java 17 hoàn chỉnh

Lưu **`InterfaceStaticDemo.java`**:

```java
interface Named {
    String name();

    static boolean valid(String text) {
        return text != null && !text.isBlank();
    }

    default boolean isValid() {
        return Named.valid(name());
    }
}

class User implements Named {
    private final String text;

    User(String text) {
        this.text = text;
    }

    @Override
    public String name() {
        return text;
    }
}

public class InterfaceStaticDemo {
    public static void main(String[] args) {
        Named first = new User("An");
        Named second = new User(" ");

        System.out.println(Named.valid("Java"));
        System.out.println(first.isValid());
        System.out.println(second.isValid());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 InterfaceStaticDemo.java
java InterfaceStaticDemo
```

Stdout:

```text
true
true
false
```

Chú ý: static method trong interface thường được gọi qua **tên interface**, không kế thừa theo cách instance/default methods được triển khai. `Named.valid("Java")` thể hiện ý định rõ.

## 18. Record: static method vẫn cần tham chiếu record

Java 17 có `record`, nhưng quy tắc static/instance không thay đổi:

```java
record Point(int x, int y) {
    static Point origin() {
        return new Point(0, 0);
    }

    int sum() {
        return x + y;
    }
}
```

- `origin()` static: tạo và trả **một object `Point`**.
- `sum()` instance: đọc components `x`, `y` của object hiện tại.
- Trong static method `origin()` không thể đọc trực tiếp `x`/`y` vì chúng gắn với một record instance.

### Chương trình Java 17

Lưu **`RecordStaticDemo.java`**:

```java
record Point(int x, int y) {
    static Point origin() {
        return new Point(0, 0);
    }

    static int sum(Point point) {
        return point.x() + point.y();
    }

    int sum() {
        return x + y;
    }
}

public class RecordStaticDemo {
    public static void main(String[] args) {
        Point point = new Point(3, 4);
        Point origin = Point.origin();

        System.out.println(Point.sum(point));
        System.out.println(point.sum());
        System.out.println(origin.sum());
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 RecordStaticDemo.java
java RecordStaticDemo
```

Stdout:

```text
7
7
0
```

`Point.sum(Point)` là static method có object receiver được cung cấp qua **tham số**; `point.sum()` là instance method có receiver trực tiếp; `Point.origin()` tạo object mới. Các cách này diễn đạt những hợp đồng API khác nhau.

## 19. Enum: constant là đối tượng, static utility vẫn khác instance method

Enum trong Java tạo các instance cho enum constants, và có thể khai báo instance methods/static methods tùy nhu cầu.

```java
enum Status {
    NEW, DONE;

    boolean finished() {
        return this == DONE;
    }

    static int count() {
        return values().length;
    }
}
```

- `finished()` là instance method: cần một `Status` như `Status.DONE.finished()`.
- `count()` là static method: gọi `Status.count()`.
- Trong `count()` không có một enum constant hiện tại tự động được gán cho `this`.

Nếu muốn xử lý một enum value trong static method:

```java
static boolean isFinished(Status status) {
    return status.finished();
}
```

Ở đây tham số `status` cung cấp receiver. Cần guard null nếu hợp đồng cho phép null.

**Không nhầm:** việc enum constants tồn tại khi class được khởi tạo không khiến mọi static method tự biết caller đang quan tâm constant nào.

## 20. Lambda trong static method có thể dùng instance qua biến capture

Một lambda tạo trong static method **không tự sinh `this` của lớp chứa method**, nhưng nó vẫn có thể sử dụng **biến local/parameter được capture hợp lệ**, trong đó có biến tham chiếu object.

Ví dụ:

```java
class Counter {
    private int value;

    void increase() {
        value++;
    }

    int value() {
        return value;
    }

    static Runnable action(Counter counter) {
        return () -> counter.increase();
    }
}
```

`counter` là tham số của static method. Lambda capture giá trị tham chiếu phù hợp; khi chạy `Runnable.run()`, nó gọi `increase()` trên object ấy.

Điều kiện **effectively final** liên quan đến biến local/parameter bị capture: không thể tùy ý gán lại tham số `counter` sau khi nó được capture trong trường hợp các quy tắc Java không cho phép.

### Chương trình hoàn chỉnh

Lưu **`StaticLambdaDemo.java`**:

```java
class Counter {
    private int count;

    void increment() {
        count++;
    }

    int count() {
        return count;
    }

    static Runnable action(Counter target) {
        return () -> target.increment();
    }
}

public class StaticLambdaDemo {
    public static void main(String[] args) {
        Counter counter = new Counter();
        Runnable action = Counter.action(counter);

        action.run();
        action.run();

        System.out.println(counter.count());
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 StaticLambdaDemo.java
java StaticLambdaDemo
```

Stdout:

```text
2
```

Lambda không biến instance method thành static; nó chỉ **giữ khả năng truy cập đến receiver được capture**.

### `this` trong lambda của static context

`this` bên trong lambda có ý nghĩa từ **lexical context**. Nếu lambda được tạo trong static method, không có `this` của lớp chứa để dùng. Viết `() -> this.instanceMethod()` trong static method thông thường vẫn bị compiler từ chối.

Ngược lại, nếu lambda được tạo bên trong **instance method**, `this` có thể tham chiếu chính object instance của lớp bao quanh.

## 21. Method references: instance method cần receiver hoặc tham số receiver

Java hỗ trợ method reference, dễ gây nhầm giữa static và instance method.

### Reference tới static method

```java
java.util.function.IntUnaryOperator absolute = Math::abs;
System.out.println(absolute.applyAsInt(-5)); // 5
```

`Math::abs` tham chiếu một static overload phù hợp theo target functional interface.

### Bound instance method reference

```java
String text = "Java";
java.util.function.IntSupplier length = text::length;
System.out.println(length.getAsInt()); // 4
```

`text::length` có **receiver object `text`** được ràng buộc.

### Unbound instance method reference

```java
java.util.function.ToIntFunction<String> length = String::length;
System.out.println(length.applyAsInt("Java")); // 4
```

`String::length` trong ngữ cảnh functional interface phù hợp là **unbound instance method reference**: tham số đầu vào của functional method cung cấp receiver `String` cho `length()`, **không** biến `String.length()` thành static method.

### Chương trình Java 17 hoàn chỉnh

Lưu **`MethodReferenceDemo.java`**:

```java
import java.util.function.IntSupplier;
import java.util.function.ToIntFunction;

public class MethodReferenceDemo {
    public static void main(String[] args) {
        String word = "Java";

        IntSupplier bound = word::length;
        ToIntFunction<String> unbound = String::length;

        System.out.println(bound.getAsInt());
        System.out.println(unbound.applyAsInt("Spring"));
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 MethodReferenceDemo.java
java MethodReferenceDemo
```

Stdout:

```text
4
6
```

Method reference thay cách viết lời gọi, **không xóa sự cần thiết của receiver** đối với instance method.

## 22. Static utility method hay instance method: nên thiết kế thế nào?

Hãy hỏi **hành vi có phụ thuộc trạng thái của đối tượng cụ thể không?**

### Khi phù hợp với static

- Tính toán thuần từ tham số, ví dụ `Math.max`.
- Factory tạo object, ví dụ `Path.of(...)` theo API JDK.
- Parser hoặc converter không cần instance state, ví dụ một method nhận `String` rồi trả value object.
- Utility xử lý object được cung cấp tường minh khi thiết kế đòi hỏi, ví dụ `Collections.sort(list)`.

### Khi phù hợp với instance

- Hành vi dựa trên field hiện tại, ví dụ `account.deposit(amount)`.
- Một thao tác đại diện cho **trách nhiệm của object**, như `order.submit()`.
- Hành vi cần polymorphism/overriding giữa các subtype.
- Thay đổi trạng thái object theo quy tắc đóng gói.

Ví dụ cùng bài toán “đọc tên”:

```java
class Person {
    private String name;

    String name() {
        return name;
    }

    static String extractName(Person person) {
        return person.name();
    }
}
```

Cả hai method có thể hợp lệ, nhưng `name()` là hành vi tự nhiên của object `Person`. `extractName(Person)` là một utility/facade nhận object; nếu không có lý do, API instance trực tiếp thường rõ hơn.

**Tránh biến mọi method thành static** chỉ để gọi dễ dàng từ `main`: cách làm đó có thể phá đóng gói và làm mã phụ thuộc shared static state không cần thiết.

## 23. Static reference đến mutable object và concurrency

Một static field có thể giữ mutable singleton/shared object:

```java
class Store {
    static final java.util.List<String> ITEMS =
            new java.util.ArrayList<>();
}
```

`Store.ITEMS` là static field final **không thể gán lại tham chiếu** sau khởi tạo hợp lệ, nhưng `Store.ITEMS.add(...)` vẫn sửa object `ArrayList`.

Nếu nhiều thread cùng truy cập, cần xem vấn đề an toàn đồng thời:
- `ArrayList` thông thường không tự thread-safe cho mọi thao tác đồng thời.
- `static final` không đồng nghĩa “collection bất biến” hoặc “mọi mutation atomic”.
- Cần lựa chọn concurrent collection, synchronization hoặc immutable snapshot theo hợp đồng.
- Static method gọi instance method trên shared object vẫn tuân thủ chính sách thread-safety của object ấy.

### Static synchronized khác instance synchronized

```java
class Gate {
    static synchronized void globalAction() {
    }

    synchronized void localAction() {
    }
}
```

Trong ví dụ trên:
- `static synchronized` sử dụng monitor gắn với đối tượng `Class` đại diện cho lớp tương ứng.
- `synchronized` instance method sử dụng monitor của **receiver object**.
- Hai dạng này **không khóa cùng monitor theo mặc định**.

Đây là khác biệt về **đối tượng khóa**, không phải cách “static có thể ngầm truy cập instance field”. Muốn phối hợp cập nhật cùng state, phải chọn một cơ chế đồng bộ nhất quán.

## 24. Phương thức static không override instance method

Một class không thể “ghi đè” instance method bằng static method cùng chữ ký như một override hợp lệ:

```java
class Parent {
    void execute() {
    }
}

class Child extends Parent {
    // static void execute() { } // SAI: static không override instance
}
```

Chiều ngược lại cũng không hợp lệ đối với hành vi override một static method bằng instance method cùng chữ ký:

```java
class Parent {
    static void execute() {
    }
}

class Child extends Parent {
    // void execute() { } // SAI: instance không override static
}
```

Static method có cơ chế **hiding** phù hợp khi subclass khai báo static method tương ứng, còn instance method có **overriding**. Đây là hai loại binding khác nhau.

Nếu subclass cần hành vi khác tùy đối tượng, instance method override có thể là lựa chọn phù hợp hơn static dispatch.

## 25. Static access và generic type parameter của lớp

Một static method thuộc generic class **không thể dùng type parameter của chính lớp** như thể nó thuộc một instance đã được tham số hóa.

Ví dụ không hợp lệ:

```java
class Box<T> {
    private T value;

    // static T identity(T input) { // SAI: T của lớp
    //     return input;
    // }
}
```

Lý do: `T` được khai báo ở cấp generic class `Box<T>`, gắn với các kiểu sử dụng/instance theo hệ kiểu; static member không sở hữu một `T` cụ thể từ `Box<String>` hay `Box<Integer>` theo cùng cách.

Cách đúng là **khai báo type parameter riêng cho static method**:

```java
class Box<T> {
    private T value;

    static <U> U identity(U input) {
        return input;
    }
}
```

Khi gọi `Box.identity("Java")`, compiler suy luận `U` là `String`. Cách này **không yêu cầu instance `Box<String>`**.

Nếu static method cần đọc field `value` của object, nhận một object `Box<T>` làm tham số với method-generic phù hợp:

```java
static <U> U getValue(Box<U> box) {
    return box.value;
}
```

Static method ở trong chính `Box` được phép truy cập field private của object `box`; nó chỉ cần **receiver explicit** và type parameter method riêng.

## 26. Static import có giải quyết được instance access không?

`import static java.lang.Math.max;` cho phép gọi `max(3, 5)` mà không cần ghi `Math.max(3, 5)` ở nơi hợp lệ. Nhưng **static import không biến instance field/method thành static**.

Ví dụ:

```java
import static java.lang.Math.max;

public class Example {
    public static void main(String[] args) {
        System.out.println(max(3, 5));
    }
}
```

`max` là static method thật sự được import. Không có cú pháp static import hợp lệ nào biến `String.length()` thành method gọi không cần receiver theo cách tương tự.

Khi đọc code có method không ghi receiver trong static context, kiểm tra xem nó là **static member của chính lớp**, **static import** hay một callable thuộc scope khác; đừng tự kết luận nó là instance method.

## 27. Các lỗi biên dịch thường gặp

| Mã / tình huống | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `static void f() { System.out.println(value); }`, `value` là instance field | Không có implicit receiver | Truyền object và dùng `object.value` |
| `static void f() { update(); }`, `update` là instance method | Không có receiver | Gọi `object.update()` |
| `static void f() { this.update(); }` | Không có `this` trong static method | Nhận hoặc tạo/lấy object |
| `static void f() { super.update(); }` | Không có instance `super` ở static context | Dùng instance method thích hợp |
| `static int copy = instanceField;` | Static initializer dùng instance field | Dùng static value hoặc object cụ thể |
| `static { instanceMethod(); }` | Static block không có instance receiver | `object.instanceMethod()` |
| `main` gọi `show()` của instance | `main` là static | Tạo/nhận instance rồi `instance.show()` |
| `ClassName.instanceMethod()` | Dùng tên lớp như receiver instance | `new ClassName().instanceMethod()` nếu phù hợp |
| `this.field` trong static lambda | Lambda không cung cấp `this` cho static context | Capture object reference |
| `static void f() { Outer.this.field; }` | Không có enclosing outer instance thích hợp | Nhận `Outer` làm tham số |
| Static method gọi private instance member mà không có object | Private access và receiver là hai điều kiện khác nhau | Trong cùng lớp dùng `object.privateMember` |
| `static T f()` trong `class Box<T>` | Static không dùng được class type parameter `T` như vậy | Khai báo method-generic `static <U> U f(...)` |
| `object.instanceMethod()` khi `object == null` | Compile được nhưng runtime null dereference | Validate non-null hoặc thiết kế Optional/guard |
| Static field giữ mutable object rồi nhiều thread sửa | Shared state không tự thread-safe | Cơ chế đồng bộ hoặc immutable/concurrent type |
| Static method bị coi như override instance method | Static/instance binding khác nhau | Thiết kế method instance cho overriding |
| Lấy object mới chỉ để tránh lỗi static | Đọc sai object state cần thiết | Nhận đúng object từ caller |
| Public static utility truy cập private state của lớp khác | Access control không phụ thuộc việc static | API public/package phù hợp |
| Gọi `instance.staticMethod()` và tưởng có dynamic dispatch | Static method bị chọn theo compile-time rules | Gọi qua tên lớp |

**Thông báo `javac` thường gặp:** `non-static variable ... cannot be referenced from a static context` hoặc `non-static method ... cannot be referenced from a static context`. Đây là tín hiệu **thiếu instance receiver**, không có nghĩa cần đổi mọi field/method thành static.

## 28. Bài tập tự luyện và đáp án

### Bài 1 — Dự đoán lỗi

```java
class Example {
    int value = 5;

    static void show() {
        // System.out.println(value);
    }
}
```

**Câu hỏi:** vì sao bỏ comment dòng print lại lỗi?

**Đáp án:** `value` là instance field nhưng `show` là static method, không có implicit `this`. Có thể chuyển thành `static void show(Example object) { System.out.println(object.value); }`.

### Bài 2 — Static method có gọi private instance method được không?

```java
class Counter {
    private void increment() {
    }

    static void run(Counter counter) {
        counter.increment();
    }
}
```

**Đáp án:** Có. `run` ở trong cùng lớp `Counter` nên được quyền gọi private member, và `counter` cung cấp receiver. Lỗi chỉ xuất hiện nếu viết `increment()` đơn độc mà thiếu object.

### Bài 3 — Hai object, một static method

```java
class Item {
    int value;

    static void addOne(Item item) {
        item.value++;
    }
}
```

```java
Item a = new Item();
Item b = new Item();
Item.addOne(a);
Item.addOne(a);
Item.addOne(b);

System.out.println(a.value);
System.out.println(b.value);
```

**Đáp án:** `2` rồi `1`. Static method thao tác object được truyền vào, không có một object mặc định của `Item`.

### Bài 4 — Static field giữ object

```java
class Shared {
    static final StringBuilder BUILDER = new StringBuilder("A");

    static void add() {
        BUILDER.append("B");
    }
}
```

**Đáp án:** `add()` hợp lệ, vì `BUILDER` là static field và `append` được gọi trên receiver `StringBuilder` cụ thể. `final` không cấm sửa nội dung builder; sau hai lần `Shared.add()`, nội dung là `"ABB"`.

### Bài 5 — `main` và instance method

```java
class App {
    void hello() {
        System.out.println("Hello");
    }

    public static void main(String[] args) {
        // hello();
    }
}
```

**Đáp án:** dòng comment nếu bật sẽ lỗi do `main` là static. Cách đúng là `new App().hello();` nếu chương trình thực sự muốn dùng một object mới.

### Bài 6 — Dùng `this` trong static lambda

```java
class Person {
    int age;

    static Runnable task() {
        // return () -> System.out.println(this.age);
        return () -> System.out.println("OK");
    }
}
```

**Đáp án:** không thể dùng `this.age` trong static method, kể cả khi bên trong lambda. Muốn dùng trạng thái `Person`, nhận `Person person` làm tham số và capture `person.age` theo quy tắc.

### Bài 7 — Static method qua instance

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

```java
Parent value = new Child();
System.out.println(value.label());
```

**Đáp án:** `Parent`. Static method không dispatch theo runtime class của object. Cách gọi rõ nghĩa là `Parent.label()`; tránh dùng `value.label()`.

### Bài 8 — Static generic method

```java
class Box<T> {
    T value;

    // static T identity(T value) { return value; }
}
```

**Đáp án:** không được dùng class type parameter `T` từ static context kiểu này. Sửa thành `static <U> U identity(U value) { return value; }`, hoặc phương thức static nhận đối tượng `Box<U>` để đọc field theo receiver.

### Bài 9 — Static nested class đọc private field của outer

```java
class Outer {
    private int number = 7;

    static class Reader {
        static int read(Outer value) {
            return value.number;
        }
    }
}
```

**Đáp án:** hợp lệ. `value` là receiver `Outer`; nested class thuộc cùng nest nên được quyền đọc private field. Nhưng `number` đơn độc hoặc `Outer.this.number` trong ngữ cảnh static không có outer instance implicit.

### Bài 10 — Static initializer

```java
class Config {
    int level = 3;

    static int levelForNewObject() {
        Config config = new Config();
        return config.level;
    }
}
```

**Đáp án:** `levelForNewObject()` hợp lệ và trả `3` theo ví dụ. Static method tạo một instance `Config` tường minh, rồi dùng `config.level`. Nếu phải đọc object đã tồn tại ở caller, cần nhận/lấy đúng object đó, không tạo mới tùy tiện.

## 29. Checklist khi viết static method truy cập object

1. **Xác định loại thành viên cần dùng:** instance field/method hay static field/method?
2. **Nếu là instance member, receiver nằm ở đâu?** Tham số, biến cục bộ, static field chứa object, kết quả factory hay đối tượng vừa tạo?
3. **Có đang dùng `this` hoặc `super` không?** Trong static method của lớp, chúng không biểu thị instance receiver hợp lệ.
4. **Có thực sự muốn dùng object mới không?** Đừng dùng `new` chỉ để chữa lỗi khi state yêu cầu là object caller đã tạo.
5. **Kiểm tra kiểu tĩnh của receiver:** method/field có được khai báo/nhìn thấy qua kiểu đó không?
6. **Kiểm tra access modifier:** `private` không cấm truy cập từ static method trong cùng lớp, nhưng mã ngoài lớp vẫn phải tuân thủ access.
7. **Kiểm tra null:** cú pháp `object.method()` có thể biên dịch nhưng vẫn ném `NullPointerException` khi receiver null.
8. **Nếu có static field mutable**, đã xác định ownership và thread-safety chưa?
9. **Nếu dùng static initializer**, đã tránh phụ thuộc vòng đời/phụ thuộc chéo phức tạp chưa?
10. **Nếu làm việc với subclass**, đã phân biệt static hiding và instance overriding chưa?
11. **Nếu có lambda/method reference**, đã xác định receiver được capture hay cung cấp qua functional interface chưa?
12. **Nếu là static nested class**, đã cung cấp outer instance tường minh khi cần chưa?
13. **Nếu là generic class**, static method có type parameters riêng thay vì sử dụng trực tiếp class type parameter không?
14. **Nếu API gắn với hành vi của object**, có nên chuyển thành instance method để giữ đóng gói và đa hình không?
15. **Kiểm tra bằng ví dụ runnable:** khởi tạo hai instance khác nhau và in state mỗi object để chứng minh static method đang dùng đúng receiver.

## Ghi nhớ

- **Static context không có instance receiver ngầm định**; vì vậy không được đọc instance field hoặc gọi instance method chỉ bằng tên khi thiếu một object.
- **Static method vẫn có thể truy cập instance member**, miễn có tham chiếu object tường minh như `user.name()` hoặc `counter.increment()` và có quyền truy cập.
- **`this`/`super` không dùng để chỉ receiver của lớp chứa static method**; chúng cần instance context phù hợp.
- **`main` là static**, nên muốn gọi instance method của class ứng dụng phải tạo/nhận object trước.
- **Private access và static/instance là hai quy tắc khác nhau**: static method trong chính lớp có thể truy cập private instance field của bất kỳ object lớp đó được truyền vào.
- **Static fields có thể lưu tham chiếu tới mutable objects**; điều đó không làm instance method biến thành static và không tự bảo đảm thread safety.
- **Static nested class, lambda và method reference** cũng tuân thủ quy tắc receiver; chúng chỉ khác cách receiver được cung cấp hoặc capture.
- **Chọn static cho hành vi không phụ thuộc vào receiver instance**; chọn instance method khi hành vi là trách nhiệm/trạng thái/đa hình của một object cụ thể.
