# Giới hạn sử dụng `this` trong ngữ cảnh `static` của Java

## 1. Vấn đề cốt lõi: `this` luôn cần một đối tượng hiện tại

Trong Java, từ khóa **`this`** là cách một phần mã đang thực thi trong **ngữ cảnh instance** tham chiếu tới **đối tượng hiện tại**. Ví dụ, khi gọi `account.deposit(50)`, thân instance method `deposit` có thể dùng `this.balance` để chỉ tới field `balance` của tài khoản đang nhận lời gọi.

Trái lại, **ngữ cảnh `static`** không gắn với một instance làm đối tượng nhận lời gọi. Một `static method` được gọi thông thường qua tên lớp, một `static field` thuộc lớp, và một `static initializer` chạy trong quá trình khởi tạo lớp. Vì không tồn tại một `this` ngầm tương ứng, Java **không cho dùng `this` làm tham chiếu tới instance hiện tại trong static context**.

```java
class Counter {
    private int value;
    private static int total;

    void increase() {
        this.value++;         // Hợp lệ: this là Counter đang nhận lời gọi.
        Counter.total++;      // Hợp lệ: field chung của lớp.
    }

    static int getTotal() {
        return total;         // Hợp lệ: static field.
    }

    static void invalid() {
        // this.value++;      // LỖI nếu bỏ comment: static context không có this.
        // this.increase();   // LỖI tương tự.
    }
}
```

Đây là một **khai báo lớp hợp lệ** do hai dòng cố ý sai đã được comment; muốn chạy phải viết thêm `main`. Mỗi instance `Counter` có field `value` riêng, trong khi `total` là field chung thuộc lớp. Static method `getTotal()` không được truyền đối tượng `Counter` cụ thể làm `this`.

**Quy tắc ghi nhớ:** `static` không có nghĩa “cấm làm việc với object”; nó có nghĩa **không có object hiện tại được cung cấp ngầm**. Static method vẫn có thể nhận một tham chiếu object qua tham số, tạo một object bằng `new` hoặc truy cập instance member qua tham chiếu đã có.

## 2. Phân biệt `this`, thành viên instance và thành viên static

Một lớp có thể chứa cả thành phần **instance** và **static**:

| Thành phần | Thuộc về | Có cần một instance cụ thể để truy cập? | Có thể dùng `this` trực tiếp trong thân thích hợp? |
| --- | --- | --- | --- |
| Instance field `int balance` | Mỗi object | Có | Có, trong ngữ cảnh instance |
| Instance method `void deposit()` | Hành vi trên receiver object | Có receiver | Có, trong thân instance method |
| Static field `static int count` | Lớp | Không | Không cần; dùng tên lớp hoặc tên field theo phạm vi |
| Static method `static int total()` | Lớp | Không | **Không** có `this` trong thân static method |
| Instance initializer `{ ... }` | Quy trình khởi tạo mỗi object | Có object đang xây dựng | Có, theo các quy tắc khởi tạo |
| Static initializer `static { ... }` | Quy trình khởi tạo lớp | Không | **Không** được dùng `this` |
| Constructor `X(...) { ... }` | Xây dựng instance | Có object đang xây dựng | Có trong thân sau các ràng buộc constructor invocation |
| Static nested class `static class Nested` | Kiểu lồng nhau không có enclosing instance ngầm | Bản thân `Nested` có thể tạo instance | Trong instance method của `Nested`, `this` là **Nested instance**, không phải instance lớp ngoài |

Phân biệt hai cách hỏi:

1. “Có **đối tượng hiện tại** ngầm định hay không?” → quyết định `this` có tồn tại ở vị trí đó.
2. “Có thể **truy cập trạng thái của một đối tượng** không?” → có thể nếu có tham chiếu object cụ thể, kể cả khi mã đang nằm trong một static method.

Từ khóa `this` không phải một biến global, không phải tên lớp và không phải một tham chiếu tự động chọn “object được tạo gần nhất”.

## 3. Ví dụ chạy hoàn chỉnh: static method nhận tham chiếu đối tượng

Tạo tệp **`StaticContextDemo.java`** (Java 17+):

```java
class Wallet {
    private final String owner;
    private int balance;
    private static int created;

    Wallet(String owner, int openingBalance) {
        this.owner = owner;
        this.balance = openingBalance;
        created++;
    }

    void deposit(int amount) {
        this.balance += amount;
    }

    String summary() {
        return owner + ":" + balance;
    }

    static int numberCreated() {
        return created;
    }

    static void bonusTo(Wallet target, int amount) {
        target.deposit(amount);
    }
}

public class StaticContextDemo {
    public static void main(String[] args) {
        Wallet first = new Wallet("Mai", 100);
        Wallet second = new Wallet("Nam", 40);

        Wallet.bonusTo(first, 20);
        second.deposit(5);

        System.out.println(first.summary());
        System.out.println(second.summary());
        System.out.println("created=" + Wallet.numberCreated());
    }
}
```

Biên dịch và chạy:

```bash
javac StaticContextDemo.java
java StaticContextDemo
```

**Output:**

```text
Mai:120
Nam:45
created=2
```

Giải thích:

- `deposit` là instance method. Trong lời gọi `first.deposit(20)`, nếu có lời gọi ấy, `this` sẽ là `first`. Trong ví dụ, `bonusTo(first,20)` gọi `target.deposit(20)` trên object được tham số `target` trỏ tới.
- `bonusTo` là **static method**, hoàn toàn **không có `this`**. Tham số `target` là một **biến tham chiếu bình thường** do caller truyền vào. Static method dùng `target.deposit(...)` thay cho lời gọi sai kiểu `this.deposit(...)`.
- `second.deposit(5)` làm tăng số dư object thứ hai. `first` và `second` là hai object độc lập.
- Field `created` chỉ có một giá trị chung cho lớp `Wallet`. Hai lời gọi constructor làm `created` từ 0 thành 2, còn `numberCreated()` đọc field ấy mà không cần instance.
- Mặc dù `bonusTo` có thể truy cập một instance bằng tham số, nó **không biến thành instance method**. Đặc điểm static/instance được quyết định bởi **khai báo** method, không bởi việc nó làm gì trong thân.

> Ví dụ này minh họa phân biệt static/instance trong một luồng. Biến static `created++` không tự an toàn khi nhiều thread cùng tạo `Wallet` đồng thời; đó là vấn đề đồng bộ hóa riêng.

## 4. `static method`: nơi thường gặp lỗi “non-static variable this cannot be referenced from a static context”

Xét mã cố ý sai:

```java
// class User {
//     String name = "guest";
//
//     static void printName() {
//         System.out.println(this.name); // Không hợp lệ.
//     }
// }
```

Ở `printName()`, không có một `User` nào được chọn làm receiver. Compiler không thể biết `this` cần là **User thứ nhất**, **User thứ hai**, hay object nào. Việc có field `name` trong khai báo lớp không làm phát sinh đối tượng hiện tại ở static method.

### Ba cách sửa tùy mục đích

**Cách 1 — Nếu hành vi thuộc về mỗi object, chuyển thành instance method:**

```java
class User {
    String name = "guest";

    void printName() {
        System.out.println(this.name);
    }
}
```

Khi có `User u = new User();`, gọi `u.printName()`. Lúc chạy, `this` trong `printName` trỏ tới `u`.

**Cách 2 — Nếu method cần nhận object từ bên ngoài, giữ `static` và truyền tham số:**

```java
class User {
    String name = "guest";

    static void printName(User user) {
        System.out.println(user.name);
    }
}
```

Lời gọi `User.printName(u)` có nghĩa static method thao tác trên object mà `u` tham chiếu. Kiểu tham số giúp API nói rõ caller phải cung cấp object nào.

**Cách 3 — Nếu dữ liệu thực sự thuộc về lớp, dùng static field:**

```java
class User {
    private static String applicationName = "Learning";

    static void printApplicationName() {
        System.out.println(User.applicationName);
    }
}
```

Đây là dữ liệu chung của lớp, không phải tên riêng của từng `User`. Không chuyển một instance field thành static chỉ để “hết lỗi `this`” nếu yêu cầu nghiệp vụ cần giữ trạng thái riêng cho mỗi object.

Ba đoạn khai báo `User` là **ba phương án riêng biệt**, không đặt đồng thời trong một tệp vì trùng tên class.

## 5. Dùng tên field instance trực tiếp trong static method cũng sai

Lỗi không chỉ xuất hiện khi viết từ khóa `this`. Trong static method, một **instance field** không thể được đọc/ghi bằng tên đơn như thể JVM tự chọn object.

```java
class Device {
    private int power;
    private static int available = 10;

    static void inspect() {
        System.out.println(available); // Hợp lệ: static field.

        // System.out.println(power);
        // Lỗi nếu bỏ comment: non-static variable power
        // cannot be referenced from a static context.
    }
}
```

`power` là field gắn với từng `Device`, trong khi `available` thuộc lớp. Khi gọi `Device.inspect()`, không có instance nào nhất thiết đã được tạo. Static method không thể suy ra `power` của object nào.

Sửa bằng tham chiếu rõ ràng:

```java
static int readPower(Device device) {
    return device.power;
}
```

Mảnh method trên được đặt **bên trong lớp `Device`**. Quyền truy cập `private` cho phép mã trong cùng lớp đọc `device.power`, kể cả khi object đó không phải `this`. Nếu triển khai method ở một lớp khác, cần dùng getter hoặc quyền truy cập phù hợp.

Tương tự, gọi một **instance method** từ static method không thể viết tên đơn `turnOn()` nếu không có receiver hoặc ngữ cảnh hợp lệ:

```java
class Device {
    void turnOn() {
        System.out.println("on");
    }

    static void activate(Device device) {
        // turnOn();       // Sai: không có receiver.
        device.turnOn();    // Đúng: device là receiver.
    }
}
```

**Không nên nhầm lỗi compile-time này với `NullPointerException`:** `device.turnOn()` có thể biên dịch vì có tham chiếu kiểu `Device`; nếu `device == null` thì mới có khả năng lỗi ở **runtime** khi gọi instance method. Java không dùng `this` để tự thay thế tham số null.

## 6. `static field initializer` và `static initializer block` không có `this`

Không chỉ static method, các biểu thức khởi tạo static field và khối `static { ... }` cũng nằm trong ngữ cảnh static.

Ví dụ đúng:

```java
class AppConfig {
    private static final String ENVIRONMENT = "dev";
    private static final int PORT;

    static {
        PORT = 8080;
    }

    static String endpoint() {
        return ENVIRONMENT + ":" + PORT;
    }
}
```

`ENVIRONMENT` và `PORT` đều là static fields. `static { PORT = 8080; }` chạy trong quá trình khởi tạo lớp khi cần; nó không có receiver object.

Ví dụ sai, chỉ để minh họa:

```java
// class BadConfig {
//     String host = "localhost";
//     static String startupHost = this.host;
//     static {
//         System.out.println(this.host);
//     }
// }
```

Cả `this.host` trong static field initializer lẫn static initializer đều không hợp lệ. Dù code có lời gọi `new BadConfig()` ở một nơi khác, điều đó không cung cấp `this` cho **static context**.

### Được phép tạo instance từ static initializer, nhưng nên cân nhắc

```java
class Registry {
    private final String name;

    Registry(String name) {
        this.name = name;
    }

    private static final Registry DEFAULT = new Registry("default");

    static String defaultName() {
        return DEFAULT.name;
    }
}
```

Đây là khai báo hợp lệ. Static field initializer thực hiện `new Registry("default")` để tạo một instance riêng, rồi lưu **tham chiếu** ở static field `DEFAULT`. Sau đó static method `defaultName()` đọc field `name` qua tham chiếu `DEFAULT`, không dùng `this`.

Với `static` initialization, cần tránh logic phức tạp, side effect khó dự đoán hoặc phụ thuộc vòng tròn giữa static fields. Khả năng tạo object từ static context **không** đồng nghĩa an toàn nếu constructor, method hoặc class initialization phụ thuộc ngược vào trạng thái tĩnh chưa hoàn tất.

## 7. Chương trình hoàn chỉnh: thứ tự static initialization và instance initialization

Tạo tệp **`ContextOrderDemo.java`**:

```java
class Session {
    static int created = initClassCount();

    static {
        System.out.println("static block");
    }

    private int id = initId();

    {
        System.out.println("instance block");
    }

    Session() {
        created++;
        System.out.println("constructor");
    }

    static int initClassCount() {
        System.out.println("static field initializer");
        return 0;
    }

    int initId() {
        System.out.println("instance field initializer");
        return created + 1;
    }

    int id() {
        return this.id;
    }

    static int created() {
        return created;
    }
}

public class ContextOrderDemo {
    public static void main(String[] args) {
        System.out.println("begin");

        Session first = new Session();
        Session second = new Session();

        System.out.println("first id=" + first.id());
        System.out.println("second id=" + second.id());
        System.out.println("created=" + Session.created());
    }
}
```

Biên dịch/chạy:

```bash
javac ContextOrderDemo.java
java ContextOrderDemo
```

Output:

```text
begin
static field initializer
static block
instance field initializer
instance block
constructor
instance field initializer
instance block
constructor
first id=1
second id=2
created=2
```

Diễn giải:

1. `main` in `begin` trước `new Session()`.
2. Khi `Session` được khởi tạo lần đầu, static field initializer `created = initClassCount()` in một dòng rồi trả `0`; static block in dòng tiếp theo. Hai phần này không dùng `this`.
3. Lần tạo instance đầu tiên thực thi `id = initId()` (một **instance field initializer**). `initId()` là instance method và được gọi trên object đang xây dựng, nên thuộc ngữ cảnh instance; nó in thông báo và trả `created + 1 == 1`.
4. Instance initializer block in tiếp. Thân constructor tăng `created` lên `1` và in `constructor`.
5. Đối tượng thứ hai không chạy lại static initialization; field initializer `initId()` lần này thấy `created == 1` và trả `2`. Constructor tăng `created` lên `2`.
6. Sau khi cả hai object hoàn tất, `first.id()` và `second.id()` đọc các instance fields của từng receiver qua `this.id`, trả `1` và `2`.

Ví dụ phân biệt **thời điểm chạy** với **ngữ cảnh cú pháp**: dù field initializer của instance được biên dịch thành công việc chạy trong quy trình constructor, nó vẫn được phép truy cập instance state theo quy tắc; static field initializer thì không có receiver.

## 8. `main` là static: không có `this` dù là điểm vào chương trình

Trong ví dụ Java cổ điển:

```java
public static void main(String[] args) {
    // ...
}
```

`main` là **static method**. Nó là điểm vào chương trình khi được chạy theo mẫu truyền thống, không phải instance method của một object ứng dụng được Java tự tạo để cung cấp `this`.

```java
public class MainContextDemo {
    private int value = 10;

    void printValue() {
        System.out.println(this.value);
    }

    public static void main(String[] args) {
        // System.out.println(this.value); // Sai: không có this ở main.
        MainContextDemo demo = new MainContextDemo();
        demo.printValue();
        System.out.println(demo.value);
    }
}
```

Lưu tệp **`MainContextDemo.java`**, chạy:

```bash
javac MainContextDemo.java
java MainContextDemo
```

```text
10
10
```

Chương trình tạo `demo` một cách **tường minh**, dùng `demo.printValue()` để gọi instance method. Bên trong `printValue` có `this` vì method này nhận receiver `demo`. Lệnh `System.out.println(demo.value)` nằm trong static `main` nhưng vẫn hợp lệ vì truy cập field qua **tham chiếu object cụ thể `demo`**.

## 9. Gọi static method qua object không tạo `this` cho static method

Java vẫn chấp nhận một số cú pháp kiểu `object.staticMethod()`, nhưng điều đó **không biến static method thành instance method**.

```java
class Utility {
    static String version() {
        return "1.0";
    }
}
```

Những lời gọi dưới đây đều nhắm đến **cùng static method** khi đứng trong ngữ cảnh hợp lệ:

```java
System.out.println(Utility.version());

Utility utility = new Utility();
System.out.println(utility.version()); // Hợp lệ nhưng không nên viết như vậy.
```

Đoạn sau là mảnh mã trong method. Cách viết `Utility.version()` nêu rõ rằng method thuộc lớp, không có `this`. `utility.version()` thường gây hiểu nhầm thành lời gọi instance, và IDE có thể cảnh báo nên thay bằng tên lớp.

Một static method **không nhận receiver object** ngay cả khi người gọi viết cú pháp qua biến tham chiếu. Trong trường hợp biểu thức trước dấu chấm phức tạp, biểu thức ấy vẫn có thể được đánh giá theo quy tắc của Java, nên còn có thể mang side effect không mong muốn. Vì vậy, gọi static bằng **tên lớp** là lựa chọn rõ ràng nhất.

### `null` trong cú pháp gọi static method không giống `null` gọi instance method

```java
class Messages {
    static String common() {
        return "shared";
    }

    String personal() {
        return "instance";
    }
}
```

Nếu `Messages ref = null;` thì `ref.personal()` không có receiver object và sẽ ném `NullPointerException` khi thực thi. Ngược lại, lời gọi `ref.common()` có thể được phân giải là **static method** và không cần dereference một receiver instance, dù cách viết qua tham chiếu null **rất không nên dùng**. Viết `Messages.common()` để loại bỏ sự mập mờ.

Điều này chứng minh **nhìn thấy dấu chấm không đủ để biết có `this` hay không**; phải xem khai báo được chọn là static hay instance.

## 10. Static nested class: không có `Outer.this` nhưng vẫn có `this` của chính nó

Một lớp được khai báo lồng bên trong lớp khác với modifier `static` là **static nested class**. Các instance của nó **không có enclosing instance ngầm** của outer class.

```java
class School {
    private String name = "Central";

    static class Desk {
        private String label = "A1";

        String ownLabel() {
            return this.label; // Hợp lệ: this là Desk instance.
        }

        // String schoolName() {
        //     return School.this.name; // Sai: Desk không có School enclosing instance.
        // }
    }
}
```

**Không được suy luận rằng mọi chữ `this` bên trong một `static class Nested` đều sai.** Khi compiler xử lý **instance method của chính nested class**, nó có một receiver `Desk` hợp lệ, nên `this.label` là hợp lệ. Điều không tồn tại là `School.this`, vì `Desk` là static nested class và không gắn với một object `School` bên ngoài.

### Cách truyền enclosing object tường minh

Tạo tệp **`StaticNestedDemo.java`**:

```java
class School {
    private final String name;

    School(String name) {
        this.name = name;
    }

    static class Desk {
        private final School owner;
        private final String label;

        Desk(School owner, String label) {
            this.owner = owner;
            this.label = label;
        }

        String describe() {
            return this.owner.name + "/" + this.label;
        }
    }
}

public class StaticNestedDemo {
    public static void main(String[] args) {
        School school = new School("Central");
        School.Desk desk = new School.Desk(school, "A1");

        System.out.println(desk.describe());
    }
}
```

```bash
javac StaticNestedDemo.java
java StaticNestedDemo
```

```text
Central/A1
```

Ở đây, `Desk` lưu tham chiếu outer object trong field `owner` **vì người viết chủ động truyền vào constructor**, không phải vì Java tự cung cấp `School.this`. Trong method `Desk.describe()`, `this` là instance `Desk`, còn `this.owner` trỏ tới instance `School`.

Cách thiết kế này rõ ràng khi nested class cần làm việc với một object ngoài nhưng không muốn buộc mọi instance đều có enclosing instance ngầm.

## 11. Non-static inner class: `Outer.this` cần enclosing instance thật

Một **non-static member class** (*inner class*) được tạo trong quan hệ với một instance lớp ngoài. Vì vậy, một instance method của inner class có thể dùng:

- `this`: instance **inner** hiện tại.
- `Outer.this`: instance **outer** liên kết với inner instance ấy, trong ngữ cảnh hợp lệ.

Tệp **`InnerThisDemo.java`**:

```java
class Library {
    private final String name;

    Library(String name) {
        this.name = name;
    }

    class Shelf {
        private final String code;

        Shelf(String code) {
            this.code = code;
        }

        String describe() {
            return Library.this.name + "/" + this.code;
        }
    }
}

public class InnerThisDemo {
    public static void main(String[] args) {
        Library library = new Library("North");
        Library.Shelf shelf = library.new Shelf("S2");
        System.out.println(shelf.describe());
    }
}
```

```bash
javac InnerThisDemo.java
java InnerThisDemo
```

```text
North/S2
```

Bởi `Shelf` là non-static inner class, `library.new Shelf("S2")` cung cấp enclosing instance `library`. Trong `describe()`, `this.code` là field của `Shelf` còn `Library.this.name` là field của `Library`.

### Có thể tạo inner class từ static method không?

Có, nếu static method **có một outer instance rõ ràng**:

```java
static Library.Shelf createShelf(Library library, String code) {
    return library.new Shelf(code);
}
```

Đây là **method minh họa** để đặt trong lớp có quyền truy cập tới `Library.Shelf`. Static method không dùng `this`; nó dùng tham số `library` để cung cấp outer instance. Do vậy “static context không có `this`” không đồng nghĩa “static context không thể tạo inner object”.

Nếu viết `new Shelf("S2")` ngay trong static method của `Library` mà không có enclosing instance hợp lệ, Java không biết outer object nào gắn vào `Shelf`. Cần `library.new Shelf(...)` hoặc cấu trúc tương ứng.

## 12. Lớp được khai báo bên trong static method: nơi xuất hiện `this` hợp lệ ở phạm vi lồng

Một **local class** được khai báo bên trong static method có thể có **instance methods của chính local class**. Bản thân static method bên ngoài vẫn không có `this`, nhưng instance method của local class lại có receiver riêng.

Tệp **`LocalClassContextDemo.java`**:

```java
public class LocalClassContextDemo {
    static String makeMessage(String name) {
        class Message {
            private final String text;

            Message(String text) {
                this.text = text;
            }

            String read() {
                return this.text;
            }
        }

        Message message = new Message(name);
        return message.read();
    }

    public static void main(String[] args) {
        System.out.println(makeMessage("hello"));
    }
}
```

```bash
javac LocalClassContextDemo.java
java LocalClassContextDemo
```

```text
hello
```

`makeMessage` là static nên bản thân nó không có `LocalClassContextDemo.this`. Tuy nhiên, **thân `Message` là khai báo một kiểu mới**, và khi gọi `message.read()`, `this` trong `Message.read()` tham chiếu tới **Message instance**. Dòng `this.text = text` trong constructor `Message` cũng chỉ object `Message` hiện tại.

Vì vậy quy tắc phải gắn với **vị trí xuất hiện `this` và ngữ cảnh khai báo cụ thể**, không chỉ nhìn thấy dòng chứa `this` có nằm về mặt văn bản bên trong một static method hay không.

## 13. Lambda: `this` thuộc ngữ cảnh bao ngoài, không thuộc “đối tượng lambda”

Lambda expression có quy tắc `this` đáng chú ý:

- Lambda viết **trong instance context** có thể tham chiếu `this` của ngữ cảnh bao ngoài.
- Lambda viết **trong static context** không tự tạo một `this` hợp lệ chỉ vì lambda được biểu diễn bởi một functional object lúc chạy.
- `this` trong lambda không nên nhầm với `this` trong một anonymous class: anonymous class có **instance riêng của chính anonymous class**.

### Lambda trong instance method

Tệp **`LambdaThisDemo.java`**:

```java
public class LambdaThisDemo {
    private final String prefix;

    LambdaThisDemo(String prefix) {
        this.prefix = prefix;
    }

    Runnable makeJob() {
        return () -> System.out.println(this.prefix);
    }

    static Runnable makeStaticJob(String text) {
        // return () -> System.out.println(this.prefix); // Sai.
        return () -> System.out.println(text);
    }

    public static void main(String[] args) {
        LambdaThisDemo demo = new LambdaThisDemo("instance");
        Runnable first = demo.makeJob();
        Runnable second = makeStaticJob("static");

        first.run();
        second.run();
    }
}
```

```bash
javac LambdaThisDemo.java
java LambdaThisDemo
```

```text
instance
static
```

`makeJob()` là instance method; lambda được tạo trong ngữ cảnh có `this` là `demo`. Khi chạy `first.run()`, biểu thức `this.prefix` trong lambda tham chiếu đến instance `demo` ấy.

`makeStaticJob(...)` là static method, nên lambda **không có enclosing `this`** để sử dụng. Nhưng lambda có thể **capture** tham số `text` vì tham số đó là effectively final trong ví dụ; khi chạy `second.run()` nó in `static`.

### Anonymous class trong static method

```java
static Runnable makeAnonymous(String message) {
    return new Runnable() {
        @Override
        public void run() {
            System.out.println(this.getClass().getSimpleName());
            System.out.println(message);
        }
    };
}
```

Đây là **mảnh method để đặt trong một lớp**. Anonymous class tạo instance riêng, do đó `this` bên trong `run()` là **anonymous Runnable instance**, không phải object của lớp chứa static method. Điều này không mâu thuẫn với việc static method bao ngoài không có `this`.

Trong trường hợp tên do compiler sinh cho anonymous class, `getSimpleName()` có thể trả chuỗi không có nội dung theo đặc tả, nên ví dụ này **không dựa vào output cố định**; điểm cần quan sát là `this` tồn tại trong instance method của anonymous class.

## 14. Method reference: thay `this::method` bằng tham chiếu hợp lệ

Trong instance context, có thể viết **bound method reference** như `this::display` nếu `display` là instance method phù hợp với functional interface mục tiêu.

```java
class Screen {
    void display() {
        System.out.println("screen");
    }

    Runnable job() {
        return this::display; // Hợp lệ: có this.
    }
}
```

Trong static context, viết `this::display` trực tiếp là sai vì không có `this`. Có hai thay thế phổ biến:

1. Có sẵn object → dùng `object::instanceMethod`.
2. Muốn nhận object khi gọi hàm → dùng `TypeName::instanceMethod` ở dạng **unbound method reference** nếu chữ ký functional interface tương ứng; đối số đầu tiên đóng vai trò receiver.

Tệp **`MethodReferenceContextDemo.java`**:

```java
import java.util.function.Function;
import java.util.function.Supplier;

class Document {
    private final String title;

    Document(String title) {
        this.title = title;
    }

    String title() {
        return title;
    }
}

public class MethodReferenceContextDemo {
    public static void main(String[] args) {
        Document document = new Document("Guide");

        Supplier<String> bound = document::title;
        Function<Document, String> unbound = Document::title;

        System.out.println(bound.get());
        System.out.println(unbound.apply(new Document("Notes")));
    }
}
```

```bash
javac MethodReferenceContextDemo.java
java MethodReferenceContextDemo
```

```text
Guide
Notes
```

`main` là static và không có `this`, nhưng `document::title` dùng một instance cụ thể để tạo bound method reference. `Document::title` dùng dạng unbound instance method reference: đối tượng `Document` được truyền làm đối số khi functional method `apply` chạy. Không cần `this` trong `main`.

**Bẫy dễ gặp:** `ClassName::instanceMethod` trong method reference **không** có nghĩa instance method tự biến thành static. Đó là cú pháp đặc biệt để chỉ **loại instance method** mà receiver được cung cấp sau.

## 15. Explicit constructor invocation `this(...)` không phải biểu thức `this`

Trong một constructor có thể xuất hiện cả `this(...)` và `this.field`, nhưng hai dạng có nghĩa khác nhau:

- `this(...)` là **lời gọi constructor khác của cùng lớp**. Nó không phải cách đọc tham chiếu object `this` rồi gọi method.
- `this.field` là **biểu thức truy cập field của object hiện tại**.
- `super(...)` là **lời gọi constructor superclass**, không phải static method.

Ví dụ với Java 17/21:

```java
class Profile {
    private final String name;

    Profile() {
        this("guest");  // Constructor invocation đứng đầu constructor.
    }

    Profile(String name) {
        this.name = name;
    }
}
```

`this("guest")` được phép ở đây dù quy tắc về biểu thức `this` trong ngữ cảnh static/explicit constructor invocation có giới hạn riêng. **Không nên suy luận:** “vì `this(...)` hợp lệ trong constructor, nên `this` cũng hợp lệ trong static method”.

### Ngữ cảnh đối số của lời gọi constructor tường minh

Trong Java 17/21, **đối số** của explicit constructor invocation `this(...)` hoặc `super(...)` chịu hạn chế tương đương một **static context** về việc tham chiếu tới instance hiện tại. Vì vậy **không dùng `this.field`, `this.instanceMethod()` hoặc instance field/method không có receiver thích hợp** để tính đối số trước khi object hoàn tất khởi tạo.

Ví dụ cố ý sai:

```java
// class Wrong {
//     int value = 10;
//
//     Wrong() {
//         this(this.value); // Sai: không dùng this để tính đối số ở đây.
//     }
//
//     Wrong(int value) {
//     }
// }
```

Có thể sửa bằng literal, tham số hoặc **static helper**:

```java
class Correct {
    private final int value;

    Correct() {
        this(defaultValue());
    }

    Correct(int value) {
        this.value = value;
    }

    static int defaultValue() {
        return 10;
    }
}
```

Ví dụ `new Correct()` là hợp lệ, field `value` nhận `10`. Trình biên dịch chọn constructor nhận `int` từ `this(defaultValue())`; helper `defaultValue()` là static nên không cần đối tượng hiện tại.

**Điểm phiên bản:** Trong Java 17/21, lời gọi `this(...)` hoặc `super(...)` tường minh phải là statement đầu tiên của constructor. Các thay đổi quy tắc constructor body ở những bản Java mới hơn không nên áp ngược vào Java 17/21. Khi học từ nhiều nguồn, luôn kiểm tra phiên bản JDK thực sự được sử dụng.

## 16. `static synchronized` và `this`: khóa nào được sử dụng?

Từ khóa `synchronized` đôi khi khiến người học nhầm rằng static method đang có một object monitor nên có thể dùng `this`. Trên thực tế:

- **Instance synchronized method** khóa monitor của **receiver object** (tương đương khóa trên `this`).
- **Static synchronized method** khóa monitor của **`Class` object** đại diện cho lớp khai báo method.

Ví dụ:

```java
class Metrics {
    private static int total;
    private int local;

    static synchronized void increaseTotal() {
        total++;
        // this.local++; // Sai: không có this.
    }

    synchronized void increaseLocal() {
        this.local++;
    }

    static synchronized int readTotal() {
        return total;
    }

    synchronized int readLocal() {
        return this.local;
    }
}
```

`increaseTotal()` và `readTotal()` dùng monitor `Metrics.class`; **không** có `Metrics.this`. `increaseLocal()` và `readLocal()` khóa receiver `Metrics` của mỗi lời gọi. Vì vậy một static synchronized method vẫn không thể trực tiếp đọc instance field nếu không có object cụ thể.

Không nên dùng `synchronized` như “công tắc khiến mọi field an toàn”: hiệu lực phối hợp giữa các thread phụ thuộc việc **cùng dữ liệu được truy cập dưới cùng giao thức khóa**.

## 17. Getter, factory và utility: chọn static hay instance đúng mục đích

Không phải chỉ cần một method không viết `this` là nên đặt `static`. Điều quan trọng là method **có cần gắn với identity/state của object hiện tại không**.

Ví dụ thiết kế:

```java
class Temperature {
    private final double celsius;

    Temperature(double celsius) {
        this.celsius = celsius;
    }

    double fahrenheit() {
        return this.celsius * 9 / 5 + 32;
    }

    static Temperature fromFahrenheit(double fahrenheit) {
        return new Temperature((fahrenheit - 32) * 5 / 9);
    }

    static double convert(double celsius) {
        return celsius * 9 / 5 + 32;
    }
}
```

- `fahrenheit()` là instance method vì chuyển đổi **nhiệt độ đang lưu trong receiver**.
- `fromFahrenheit(double)` là **static factory method**: nó tạo instance mới theo đối số, không cần một `Temperature` hiện có làm `this`.
- `convert(double)` là utility static: chỉ cần đối số, không phụ thuộc state instance.
- Constructor `Temperature(double)` không phải static method, dù được factory gọi bằng `new Temperature(...)`.

Nếu một method có signature `static double fahrenheit()` mà cố đọc `this.celsius` thì thiết kế hoặc khai báo modifier bị sai. Chọn giữa **chuyển thành instance method**, **truyền `Temperature` làm tham số**, hoặc **truyền `double celsius`** tùy API mong muốn.

### Kiểm soát quyền truy cập vẫn áp dụng

Một static method ở **cùng lớp** có thể truy cập `private instance field` của một object khác cùng lớp qua tham chiếu:

```java
class Temperature {
    private final double celsius;

    Temperature(double celsius) {
        this.celsius = celsius;
    }

    static double difference(Temperature a, Temperature b) {
        return a.celsius - b.celsius;
    }
}
```

`difference(a,b)` không có `this`, nhưng được phép đọc `a.celsius` và `b.celsius` vì truy cập `private` được kiểm tra theo phạm vi của lớp khai báo, không theo điều kiện “đang ở instance method”. Đó là **hai object cụ thể**, không phải object hiện tại ngầm định.

## 18. Các lỗi thường gặp và cách sửa

| Lỗi/suy luận sai | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Dùng `this.field` trong static method | Không có object receiver hiện tại | Bỏ `static` nếu method thuộc từng object; hoặc dùng `object.field` |
| Gọi `instanceMethod()` bằng tên đơn trong static method | Không có receiver ngầm | Gọi `object.instanceMethod()` |
| Dùng `this` trong `static { ... }` | Static initializer không thuộc instance | Dùng static fields hoặc tạo/chuyển tham chiếu object rõ ràng |
| Dùng `this` ở biểu thức gán static field | Static field initializer không có receiver | Dùng static data, tham số hoặc tạo object |
| Viết `this` trong `static main` | JVM không tạo object ứng dụng làm `this` cho main | Tạo object với `new` hoặc gọi static member theo tên lớp |
| Cho rằng `static Nested` cấm mọi `this` | Lẫn outer instance với nested instance | `this` hợp lệ trong instance method của `Nested`; không có `Outer.this` ngầm |
| Cho rằng lambda luôn có `this` của lambda object | Lambda không tạo ngữ nghĩa `this` mới như anonymous class | Trong instance lambda, `this` là enclosing instance; trong static lambda không có enclosing `this` |
| Gọi `this::method` từ static method | Không có `this` để tạo bound method reference | Dùng `object::method` hoặc `Type::method` phù hợp |
| Dùng `this.field` làm đối số của `this(...)` trong Java 17/21 | Hạn chế explicit constructor invocation | Dùng tham số/literal/static helper |
| Viết `this(...)` ở giữa static method | `this(...)` chỉ là constructor invocation ở vị trí hợp lệ | Đặt lời gọi trong constructor, theo cú pháp và thứ tự JDK |
| Gọi static method qua `object.staticMethod()` rồi nghĩ có receiver | Static invocation vẫn không có `this` | Viết `ClassName.staticMethod()` |
| Cho rằng `static synchronized` khóa object `this` | Static synchronized khóa `Class` object | Xác định chính xác monitor và giao thức đồng bộ |
| Chuyển mọi field thành `static` để sửa compile error | Làm mất tính độc lập của trạng thái từng object | Chỉ dùng static khi dữ liệu **thực sự thuộc lớp** |
| Truyền `null` làm receiver instance method | Type đúng nhưng không có object để gọi | Kiểm tra `null`, khởi tạo object hoặc dùng API không nhận null |

Một số lỗi compile-time hay gặp có thông báo kiểu **“non-static variable this cannot be referenced from a static context”**, **“non-static variable X cannot be referenced from a static context”** hoặc **“non-static method m() cannot be referenced from a static context”**. Thông điệp cụ thể tùy dòng mã và trình biên dịch, nhưng cách giải quyết đều bắt đầu bằng việc xác định **receiver nào được dùng**.

## 19. Chương trình tổng hợp: static context phối hợp nhiều instance

Tạo tệp **`StaticInstanceBoundaryDemo.java`**:

```java
class Participant {
    private final String name;
    private int points;
    private static int totalParticipants;

    Participant(String name, int points) {
        this.name = name;
        this.points = points;
        totalParticipants++;
    }

    void addPoints(int amount) {
        this.points += amount;
    }

    String summary() {
        return this.name + "=" + this.points;
    }

    static int count() {
        return totalParticipants;
    }

    static void transfer(Participant from, Participant to, int amount) {
        from.points -= amount;
        to.points += amount;
    }

    static String compare(Participant first, Participant second) {
        return first.points >= second.points ? first.name : second.name;
    }

    static class Report {
        private final Participant subject;

        Report(Participant subject) {
            this.subject = subject;
        }

        String render() {
            return this.subject.summary();
        }
    }
}

public class StaticInstanceBoundaryDemo {
    public static void main(String[] args) {
        Participant an = new Participant("An", 12);
        Participant binh = new Participant("Binh", 7);

        an.addPoints(3);
        Participant.transfer(an, binh, 5);

        Participant.Report report = new Participant.Report(binh);

        System.out.println(an.summary());
        System.out.println(report.render());
        System.out.println("winner=" + Participant.compare(an, binh));
        System.out.println("count=" + Participant.count());
    }
}
```

Biên dịch/chạy:

```bash
javac StaticInstanceBoundaryDemo.java
java StaticInstanceBoundaryDemo
```

Output:

```text
An=10
Binh=12
winner=Binh
count=2
```

Giải thích:

1. `an` và `binh` trỏ tới hai object `Participant`, mỗi object giữ `name` và `points` riêng. Constructor dùng `this.name`, `this.points` vì đang khởi tạo mỗi instance.
2. `an.addPoints(3)` chạy instance method với `this == an` và tăng điểm từ 12 lên 15.
3. `Participant.transfer(an, binh, 5)` là static method **không có `this`**; nó dùng hai tham chiếu `from`, `to` được caller truyền để giảm 5 từ An và tăng 5 cho Binh. Vì vậy điểm thành `10` và `12`.
4. `Participant.Report` là **static nested class**. Constructor của `Report` có `this.subject` trỏ tới **Report instance**, không phải một `Participant` instance. Field `subject` lưu tham chiếu `binh` do caller cung cấp.
5. `report.render()` gọi `subject.summary()` trên `binh`, nên in `Binh=12`.
6. `Participant.compare(an, binh)` là static method dùng hai đối tượng cụ thể để đọc điểm. Binh cao hơn An, nên trả `Binh`.
7. `Participant.count()` là static method đọc static field `totalParticipants`; hai lần tạo `Participant` đưa số đếm lên 2. Việc tạo `Report` không tăng số đếm này.

Đây là ví dụ phân biệt rành mạch: **static method vẫn có thể xử lý nhiều object; instance method luôn có một receiver; static nested class có `this` riêng của nó**. Không cần lạm dụng biến static để chia sẻ trạng thái từng object.

## 20. Bài tập tự kiểm tra kèm đáp án

**Câu 1.** Trong `static void f() { System.out.println(this); }`, vì sao lỗi?

**Đáp án:** Static method không có instance receiver hiện tại, nên `this` không có ý nghĩa và bị compiler từ chối.

**Câu 2.** Nếu `static void show(Person p) { System.out.println(p.name); }`, việc đọc field instance có hợp lệ không?

**Đáp án:** Có nếu quyền truy cập cho phép, vì `p` là tham chiếu tới object cụ thể. Nếu `p == null` thì có thể gặp `NullPointerException` khi truy cập; vấn đề này khác việc không có `this`.

**Câu 3.** Có thể viết `this.count++` trong instance method nếu `count` là static field không?

**Đáp án:** Tùy cú pháp truy cập field, Java có thể cho phép truy cập static field qua biểu thức instance, nhưng cách viết này dễ gây nhầm. Nên dùng `ClassName.count++` để cho thấy field thuộc lớp, **không** thuộc riêng receiver. Trong static method, `this` vẫn bị cấm.

**Câu 4.** Trong static method của `Outer`, `new Inner()` có hợp lệ nếu `Inner` là non-static member class không?

**Đáp án:** Không theo cú pháp thiếu enclosing instance. Phải có object outer cụ thể và dùng `outer.new Inner()` trong ngữ cảnh phù hợp.

**Câu 5.** Trong instance method của `Outer.StaticNested`, `this` là đối tượng nào?

**Đáp án:** Instance `StaticNested`. `Outer.this` không tự tồn tại vì static nested class không có enclosing instance `Outer`.

**Câu 6.** Tại sao lambda khai báo trong static method không dùng được `this` nhưng anonymous class có thể dùng `this` trong `run()`?

**Đáp án:** Lambda giữ ngữ nghĩa `this` từ ngữ cảnh bao ngoài, vốn là static nên không có `this`. Anonymous class khai báo một lớp mới, và instance method của nó có receiver là anonymous class instance.

**Câu 7.** `Document::title` trong static `main` có nghĩa method `title` biến thành static không?

**Đáp án:** Không. Đây là **unbound instance method reference**; một `Document` được cung cấp ở thời điểm gọi functional method, ví dụ `Function<Document,String>.apply`.

**Câu 8.** `this("default")` trong constructor và `this.name` có phải cùng loại biểu thức không?

**Đáp án:** Không. `this(...)` là explicit constructor invocation; `this.name` là truy cập field qua tham chiếu đối tượng hiện tại. Quy tắc dùng trong static context/constructor invocation của chúng khác nhau.

**Câu 9.** Nếu một static method sửa field của object thông qua tham số, nó có biến thành instance method không?

**Đáp án:** Không. Modifier `static` là thuộc tính của khai báo. Method có thể xử lý object thông qua tham số nhưng không tự có `this`.

**Câu 10.** Trong `ContextOrderDemo`, vì sao hai instance fields `id` nhận 1 và 2 trong khi static initializer chỉ chạy một lần?

**Đáp án:** `created` là static field được tăng sau mỗi lần constructor `Session()` chạy. Mỗi instance field initializer `initId()` đọc giá trị hiện tại của `created`, lần lượt là 0 rồi 1, nên trả 1 và 2. Static initializer không cần chạy lại.

**Câu 11.** Nếu đổi `Wallet.bonusTo(first, 20)` thành `first.bonusTo(first, 20)`, `bonusTo` có nhận `this == first` không?

**Đáp án:** Không. `bonusTo` vẫn là static method; cú pháp gọi static qua instance không truyền receiver làm `this`. Dùng tên lớp là đúng và dễ hiểu hơn.

**Câu 12.** Khi `static synchronized` method chạy, nó có khóa `this` không?

**Đáp án:** Không. Nó dùng monitor `Class` object của lớp khai báo method; không tồn tại `this` trong static method.

## 21. Checklist khi gặp lỗi `this` trong static context

Trước khi sửa code theo kiểu “thêm/bớt `static`”, hãy xác định:

1. **Vị trí chính xác của `this`:** static method, static initializer, static field initializer, constructor, instance method, lambda, local/anonymous/nested class?
2. **Đối tượng cần thao tác là đối tượng nào?** Một đối tượng hiện có, đối tượng truyền từ caller, hay dữ liệu thật sự thuộc lớp?
3. **Có receiver tường minh không?** Nếu method muốn truy cập instance state, có thể truyền object bằng tham số hoặc dùng object có sẵn.
4. **Method có thực sự nên là instance method không?** Nếu hành vi gắn với state/danh tính từng object, bỏ `static` có thể là sửa đúng bản chất.
5. **Dữ liệu có đúng là dùng chung giữa mọi instance không?** Đừng chuyển field sang static nếu điều đó tạo chia sẻ sai ý nghĩa.
6. **Đang ở static nested class hay inner class?** Xác định `this` muốn chỉ đối tượng nested, hay muốn chỉ outer object. Chỉ inner class có enclosing instance thích hợp mới dùng `Outer.this`.
7. **Đang ở lambda/method reference?** Lambda trong static context không sinh `this`; dùng tham số/capture hợp lệ hoặc `object::method`/`Type::method`.
8. **Có nhầm `this(...)` với `this.field` không?** Trong Java 17/21, đối số constructor invocation không được tham chiếu instance hiện tại theo cách bị cấm, nhưng lời gọi `this(...)` có cú pháp riêng.
9. **Có nguy cơ `null` không?** Việc chuyển sang `object.instanceMethod()` giải quyết thiếu receiver ngầm nhưng vẫn yêu cầu tham chiếu object hợp lệ lúc runtime.
10. **Lỗi đã được giải quyết mà thiết kế vẫn đúng chưa?** Kiểm tra trạng thái có cần độc lập giữa instances, quyền truy cập và tính đồng thời trước khi kết luận.

---

**Ghi nhớ:** `this` chỉ **đối tượng hiện tại trong ngữ cảnh instance thích hợp**. Static method, static field initializer và static initializer **không có `this`**, vì chúng hoạt động ở cấp lớp, không có receiver object ngầm. Static code vẫn có thể xử lý instance nếu nhận/tạo **tham chiếu object cụ thể**; static nested class có `this` của **chính nested instance**, còn inner class có thể có `Outer.this`. Nhận diện đúng **ngữ cảnh khai báo và object thực sự cần thao tác** là chìa khóa để sửa lỗi static context mà không làm sai thiết kế hướng đối tượng.