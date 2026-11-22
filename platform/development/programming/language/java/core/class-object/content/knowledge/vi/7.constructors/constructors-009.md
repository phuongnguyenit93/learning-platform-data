# Quyền truy cập hàm khởi tạo và ngăn tạo đối tượng từ bên ngoài trong Java

Trong Java, **constructor (hàm khởi tạo)** quyết định cách một đối tượng được khởi tạo. Giống field và method, constructor có **mức truy cập** (*access level*), ảnh hưởng đến vị trí mã nào **được phép gọi constructor đó**. Nếu không muốn mã bên ngoài tùy ý viết `new ClassName(...)`, lập trình viên có thể **giới hạn quyền truy cập constructor**, thường gặp nhất là `private` hoặc package-private, rồi cung cấp một phương thức tạo đối tượng có kiểm soát khi cần.

Ví dụ:

```java
public final class Account {
    private final String owner;

    private Account(String owner) {
        this.owner = owner;
    }

    public static Account open(String owner) {
        return new Account(owner);
    }

    public String owner() {
        return owner;
    }
}
```

Với ví dụ này, mã bên ngoài `Account` **không thể gọi** `new Account("An")` theo quy tắc truy cập thông thường, nhưng có thể gọi `Account.open("An")`. Phương thức `open` chạy **bên trong** lớp `Account` nên được phép gọi constructor `private`.

Mục tiêu bài học: phân biệt `public`, `protected`, package-private và `private` trên constructor; hiểu giới hạn của `new` từ những phạm vi khác nhau; biết thiết kế factory, utility class và singleton đúng cách; nhận diện lỗi biên dịch; và hiểu chính xác việc **ngăn tạo đối tượng từ bên ngoài** có nghĩa gì.

## 1. Quyền truy cập của constructor là gì?

Một khai báo constructor có dạng cơ bản:

```java
[public | protected | private] ClassName(parameters) {
    // Khởi tạo đối tượng
}
```

Đây là **sơ đồ cú pháp**, không phải đoạn Java biên dịch nguyên xi. Có thể **bỏ access modifier** để constructor mang mức **package-private**. Không được dùng từ khóa `default` để khai báo “default access”.

Đối với constructor của lớp thông thường, bốn lựa chọn là:

| Khai báo | Mức truy cập | Ý nghĩa thực tế |
| --- | --- | --- |
| `public Person()` | `public` | Cho phép mã có quyền nhìn thấy lớp gọi constructor, tùy giới hạn module và các quy tắc Java khác |
| `protected Person()` | `protected` | Cho phép gọi trong cùng package; hỗ trợ gọi constructor superclass trong những trường hợp kế thừa hợp lệ từ package khác |
| `Person()` | Package-private | Cho phép gọi từ cùng package, kể cả lớp khác tệp; không công khai cho package khác |
| `private Person()` | `private` | Hạn chế lời gọi vào phạm vi kiểu và các ngữ cảnh được Java cho phép; bên ngoài thông thường không gọi được |

**Hai điều phải kiểm tra độc lập:**

1. **Lớp có truy cập được không?** Ví dụ lớp cấp cao nhất `class Person` không `public` thì mã package khác không thể trực tiếp dùng tên kiểu đó.
2. **Constructor được chọn có truy cập được không?** Một `public class Person` vẫn có thể chỉ cung cấp constructor `private` hoặc package-private.

Mức `public` của lớp **không tự động biến các constructor bạn khai báo thành `public`**. Cú pháp `new Person(...)` phải thỏa cả quy tắc truy cập kiểu, constructor, và các điều kiện overload/đối số.

## 2. Bảng so sánh các phạm vi gọi constructor

Xét một lớp `Base` ở package `core` và mã muốn gọi một constructor của nó:

| Vị trí lời gọi | `public` | `protected` | Package-private | `private` |
| --- | --- | --- | --- | --- |
| Trong chính lớp khai báo constructor | Có | Có | Có | Có |
| Lớp khác cùng package | Có | Có | Có | Không, trừ ngữ cảnh truy cập đặc biệt được ngôn ngữ cho phép |
| Lớp không liên quan ở package khác | Có nếu kiểu truy cập được | Không | Không | Không |
| Constructor của lớp con ở package khác gọi `super(...)` | Có | Có | Không | Không |
| Mã lớp con ở package khác viết `new Base(...)` trực tiếp | Có nếu kiểu truy cập được | **Không chỉ vì là lớp con** | Không | Không |

Bảng mô tả các tình huống thông thường với các lớp không lồng nhau và không có cơ chế truy cập đặc biệt. Điểm cần nhớ nhất là **`protected` không có nghĩa “mọi mã ở lớp con được tự do viết `new Base(...)`”**. Trong package khác, lớp con thường được phép gọi constructor `protected` của cha **để khởi tạo phần superclass** qua `super(...)`, nhưng không tự nhiên được tạo một đối tượng cha độc lập qua `new Base(...)`.

Đối với `private`, Java cho phép những ngữ cảnh truy cập trong cùng kiểu và giữa một số kiểu lồng nhau/nestmates theo quy tắc ngôn ngữ. Vì thế nói “private chỉ dùng được đúng ở dòng mã trong một object” là diễn đạt quá hẹp. Trong các ví dụ độc lập ở bài này, hãy hiểu `private constructor` chủ yếu ngăn mã của **lớp không liên quan** gọi trực tiếp.

## 3. `public constructor`: API cho phép tạo đối tượng trực tiếp

Ví dụ lớp có constructor công khai:

**Tệp `src/model/Student.java`**

```java
package model;

public class Student {
    private final String name;

    public Student(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên trống");
        }
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

**Tệp `src/app/Main.java`**

```java
package app;

import model.Student;

public class Main {
    public static void main(String[] args) {
        Student student = new Student("An");
        System.out.println(student.getName());
    }
}
```

Biên dịch và chạy bằng JDK 17+ từ thư mục chứa `src`:

```bash
javac -encoding UTF-8 -d out src/model/Student.java src/app/Main.java
java -cp out app.Main
```

Stdout:

```text
An
```

Ở đây:

- `Student` là kiểu top-level `public`, nên `app.Main` có thể sử dụng kiểu `model.Student` khi classpath và những điều kiện khác phù hợp.
- `Student(String name)` là constructor `public`, nên lời gọi `new Student("An")` từ package `app` hợp lệ.
- Field `name` là `private`, vì vậy `app.Main` không thể đọc trực tiếp `student.name`; nó sử dụng method `getName()`.
- Constructor vẫn thực hiện kiểm tra dữ liệu. `public` chỉ cho phép **gọi từ bên ngoài**, không có nghĩa constructor phải chấp nhận mọi giá trị đầu vào.

**Khi nên dùng:** kiểu dữ liệu mà việc tạo đối tượng trực tiếp rõ ràng, không cần kiểm soát nguồn tạo thể hiện, và constructor thể hiện đầy đủ các điều kiện bất biến của đối tượng.

## 4. Package-private constructor: cho phép tạo đối tượng trong cùng package

Bỏ access modifier trước tên constructor:

```java
package library;

public class Book {
    private final String title;

    Book(String title) {     // package-private constructor
        this.title = title;
    }

    public static Book of(String title) {
        return new Book(title);
    }

    public String title() {
        return title;
    }
}
```

Vì `Book` là `public` nhưng `Book(String)` **không** `public`, mã ở package khác có thể biết đến `Book` mà vẫn **không được** viết `new Book("Java")`.

### 4.1. Ví dụ chạy được qua hai package

**Tệp `src/library/Book.java`**

```java
package library;

public class Book {
    private final String title;

    Book(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is blank");
        }
        this.title = title;
    }

    public static Book of(String title) {
        return new Book(title);
    }

    public String title() {
        return title;
    }
}
```

**Tệp `src/app/Main.java`**

```java
package app;

import library.Book;

public class Main {
    public static void main(String[] args) {
        Book book = Book.of("Java Core");
        System.out.println(book.title());

        // Book other = new Book("Advanced");
        // SAI nếu bỏ comment: constructor Book(String) không public.
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 -d out src/library/Book.java src/app/Main.java
java -cp out app.Main
```

Stdout:

```text
Java Core
```

Cùng package `library`, một lớp **khác tệp** vẫn có thể gọi `new Book("Java")` vì constructor package-private cho phép mã cùng package sử dụng. Nhưng `app.Main` ở package khác phải dùng `Book.of(...)` hoặc một API công khai khác.

**Chú ý:** package dựa trên khai báo `package`, không dựa thuần vào việc các lớp ở cùng thư mục hay khác tệp. Một constructor package-private là lựa chọn phù hợp cho **mã nội bộ cùng package**, không phải cơ chế bảo mật tuyệt đối trước mọi hình thức can thiệp vào runtime.

## 5. `protected constructor`: phục vụ kế thừa có kiểm soát

`protected` trên constructor có hai lợi ích điển hình:

- Các lớp trong **cùng package** có thể gọi constructor theo quy tắc package.
- Lớp con ở **package khác** có thể gọi constructor `protected` của superclass qua `super(...)` để thực hiện khởi tạo.

Ví dụ với hai package:

**Tệp `src/core/Vehicle.java`**

```java
package core;

public class Vehicle {
    private final String brand;

    protected Vehicle(String brand) {
        this.brand = brand;
    }

    public String brand() {
        return brand;
    }
}
```

**Tệp `src/app/Car.java`**

```java
package app;

import core.Vehicle;

public class Car extends Vehicle {
    public Car(String brand) {
        super(brand); // Hợp lệ: gọi protected constructor của superclass
    }
}
```

**Tệp `src/app/Main.java`**

```java
package app;

import core.Vehicle;

public class Main {
    public static void main(String[] args) {
        Car car = new Car("Toyota");
        System.out.println(car.brand());

        // Vehicle vehicle = new Vehicle("Honda");
        // SAI: app.Main không được gọi protected constructor trực tiếp.
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 -d out src/core/Vehicle.java src/app/Car.java src/app/Main.java
java -cp out app.Main
```

Stdout:

```text
Toyota
```

Điểm quan trọng: **`app.Car` có thể kế thừa `core.Vehicle`** và sử dụng `super(brand)` dù constructor của `Vehicle` không public. Nhưng điều đó không công khai `new Vehicle("Honda")` cho mọi mã bên ngoài `core`.

Một lớp con có thể viết constructor `public` để người dùng khởi tạo **đối tượng lớp con**, nhưng không làm constructor cha tự trở thành `public`.

### 5.1. `protected` không phải “private dành riêng cho lớp con”

Khác với `private`, constructor `protected` cho phép **mọi lớp khác cùng package** gọi theo quyền package, không chỉ lớp con. Do đó nếu yêu cầu là **không ai khác ngoài chính lớp và mã lồng liên quan** được gọi, `protected` không đáp ứng.

Ở package khác, `protected` có quy tắc truy cập tinh tế: việc gọi constructor qua `super(...)` trong lớp con được phép; việc dùng `new Base(...)` để tạo một đối tượng `Base` độc lập không được tự động cho phép chỉ vì dòng mã nằm trong lớp con. Một số cú pháp liên quan đến lớp vô danh có quy tắc riêng; khi học cơ bản, hãy dùng `super(...)` để thể hiện mục đích gọi constructor cha.

### 5.2. Abstract class vẫn cần constructor

Một abstract class không thể được tạo trực tiếp bằng `new AbstractType()` nhưng vẫn cần constructor để khởi tạo trạng thái superclass:

```java
abstract class Shape {
    private final String color;

    protected Shape(String color) {
        this.color = color;
    }

    String color() {
        return color;
    }

    abstract int area();
}

final class Square extends Shape {
    private final int side;

    Square(String color, int side) {
        super(color);
        this.side = side;
    }

    @Override
    int area() {
        return side * side;
    }
}
```

`protected Shape(String)` phù hợp khi muốn lớp con khởi tạo phần chung nhưng không muốn biến superclass thành kiểu được tạo trực tiếp (ở đây bản thân `Shape` cũng là `abstract`).

**Đừng nhầm:** `abstract` là giới hạn **tạo thể hiện của lớp**, còn `protected` là giới hạn **vị trí có thể gọi constructor**. Hai cơ chế bổ sung nhau.

## 6. `private constructor`: không cho mã bên ngoài gọi `new` thông thường

Khai báo:

```java
class Secret {
    private Secret() {
    }
}
```

Mã thuộc một lớp độc lập bên ngoài `Secret` không thể viết `new Secret()` theo truy cập Java thông thường, dù lớp đó nằm trong cùng package.

Phần mềm có thể dùng private constructor vì nhiều mục đích:

1. **Kiểm soát đường tạo đối tượng** qua static factory method.
2. **Không muốn tạo instance** của một utility class chỉ chứa static methods.
3. **Giới hạn số instance** theo một thiết kế cụ thể, chẳng hạn singleton hoặc cache — cần thêm logic, không chỉ `private`.
4. **Buộc đầu vào được xác thực** hoặc chuẩn hóa trước khi tạo.
5. **Ẩn một lớp triển khai** bên trong API nhà máy của chính kiểu đó.

`private` là một **quy tắc truy cập ở mức ngôn ngữ** đối với lời gọi constructor. Nó không tự bảo đảm “vĩnh viễn không ai có thể tạo object” dưới mọi cơ chế như reflection, serialization, instrumentation hoặc các công cụ can thiệp runtime; phần lưu ý ở cuối bài sẽ phân biệt rõ.

## 7. Ví dụ chuẩn: private constructor + public static factory

Giả sử đối tượng tài khoản cần số dư ban đầu không âm. Ta muốn người dùng tạo tài khoản qua API dễ hiểu, thay vì gọi trực tiếp constructor.

Lưu toàn bộ chương trình thành **`AccountFactoryDemo.java`**:

```java
final class Account {
    private final String owner;
    private int balance;

    private Account(String owner, int balance) {
        this.owner = owner;
        this.balance = balance;
    }

    static Account open(String owner, int initialBalance) {
        if (owner == null || owner.isBlank()) {
            throw new IllegalArgumentException("owner must not be blank");
        }
        if (initialBalance < 0) {
            throw new IllegalArgumentException("negative balance");
        }
        return new Account(owner, initialBalance);
    }

    String owner() {
        return owner;
    }

    int balance() {
        return balance;
    }

    void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("deposit must be positive");
        }
        balance = Math.addExact(balance, amount);
    }
}

public class AccountFactoryDemo {
    public static void main(String[] args) {
        Account account = Account.open("An", 100);
        account.deposit(50);

        System.out.println(account.owner());
        System.out.println(account.balance());

        // new Account("An", 100);
        // SAI nếu bỏ comment: constructor Account(String, int) là private.
    }
}
```

Biên dịch/chạy JDK 17+:

```bash
javac -encoding UTF-8 AccountFactoryDemo.java
java AccountFactoryDemo
```

**Stdout chính xác:**

```text
An
150
```

Phân tích:

- `Account` là lớp top-level package-private, có một **private constructor**.
- `open(...)` là **static factory method**. Nó **không phải constructor** vì có kiểu trả về `Account`, có tên tùy chọn `open` và được khai báo `static`.
- Khi caller gọi `Account.open(...)`, việc kiểm tra dữ liệu xảy ra trước câu lệnh `new Account(...)`.
- Constructor vẫn đóng vai trò khởi tạo field sau khi factory đã xác nhận dữ liệu hợp lệ.
- `deposit` là instance method thay đổi trạng thái **đối tượng đã được tạo**, không phải constructor mới.
- Mã bên ngoài `Account` không gọi trực tiếp constructor `private` dù cùng package.

Ở đây factory `open` chỉ có quyền truy cập package-private để phù hợp với ví dụ cùng tệp. Nếu muốn API cho các package khác, thường khai báo **`public class Account`** trong **`Account.java`** và **`public static Account open(...)`**; giữ constructor `private`. Có thể cho caller bên ngoài truy cập lớp và factory nhưng không cho trực tiếp gọi `new Account(...)`.

### 7.1. Quyền gọi constructor khác với quyền gọi factory

Trong ví dụ trên, `Account.open(...)` là **static method** và có thể có mức truy cập khác với constructor `private Account(...)`. Vì vậy mã ngoài class có thể dùng một API tạo đối tượng được cho phép mà **không** được gọi `new Account(...)` trực tiếp. Factory có tên tự chọn và kiểu trả về; constructor phải cùng tên lớp và không khai báo return type.

Quan hệ access này là trọng tâm ở đây: **giới hạn constructor không đồng nghĩa cấm mọi cách tạo hoặc sử dụng object**. Những khả năng cao hơn của factory (đặt tên diễn đạt mục đích, cache/reuse, trả subtype/interface, trade-off và so sánh với constructor công khai) được phân tích đầy đủ trong bài **“Phương thức tạo đối tượng có tên và so sánh với hàm khởi tạo”**.

## 8. Không thể tạo instance từ ngoài nhưng vẫn có thể sử dụng object

Giới hạn gọi constructor **không có nghĩa không thể dùng đối tượng của lớp đó**. Một public factory hoặc API khác có thể cung cấp object cho caller:

```java
public final class Session {
    private final String token;

    private Session(String token) {
        this.token = token;
    }

    public static Session create(String token) {
        return new Session(token);
    }

    public String token() {
        return token;
    }
}
```

Nếu lưu thành **`Session.java`** trong package thích hợp, caller có thể viết:

```java
Session session = Session.create("abc");
System.out.println(session.token()); // abc
```

Nhưng không được gọi `new Session("abc")` từ lớp độc lập khác vì constructor private.

**Phân biệt ba quyền khác nhau**:

- **Nhìn thấy tên kiểu `Session`**: phụ thuộc quyền truy cập lớp.
- **Nhận/giữ tham chiếu `Session`**: có thể xảy ra từ giá trị trả về của API hợp lệ.
- **Tạo mới thông qua constructor `Session(...)`**: phụ thuộc riêng vào quyền truy cập constructor.

Một đối tượng vẫn có thể bị sử dụng thông qua interface hoặc superclass mà caller nhìn thấy, ngay cả khi lớp triển khai cụ thể bị ẩn. Điều này là nền tảng của thiết kế “program to an interface” và factory.

## 9. Utility class: constructor private để không bị `new` nhầm

**Utility class** chỉ gom các static methods hoặc constants không cần state gắn với từng đối tượng. Ví dụ `Math` trong thư viện chuẩn có các method `static` như `Math.max`.

Lưu **`UtilityDemo.java`**:

```java
final class TextUtil {
    private TextUtil() {
        throw new AssertionError("No instances");
    }

    static String normalize(String input) {
        if (input == null) {
            return "";
        }
        return input.trim().toLowerCase(java.util.Locale.ROOT);
    }
}

public class UtilityDemo {
    public static void main(String[] args) {
        System.out.println(TextUtil.normalize("  JAVA Core  "));

        // TextUtil util = new TextUtil();
        // SAI nếu bỏ comment: constructor private.
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 UtilityDemo.java
java UtilityDemo
```

Stdout:

```text
java core
```

Giải thích:

- `TextUtil.normalize` là static method, vì thế không cần `new TextUtil()` để gọi.
- `private TextUtil()` chặn việc tạo utility object thông thường từ lớp khác.
- `final class TextUtil` ngăn viết lớp con kế thừa utility class.
- `throw new AssertionError("No instances")` trong constructor là một lựa chọn phòng vệ bổ sung nếu constructor vô tình được gọi từ bên trong lớp. Nó không bắt buộc để `private` có hiệu lực.
- `java.util.Locale.ROOT` tránh thay đổi kết quả do locale của môi trường khi gọi `toLowerCase`.

**Một ngộ nhận:** khai báo các method là `static` **không khiến lớp tự động không thể khởi tạo**. Nếu không khai báo constructor, một lớp thông thường có thể được compiler tạo default constructor. Muốn ngăn lời gọi `new` từ mã ngoài, hãy chủ động khai báo private constructor hoặc chọn một kiểu thiết kế phù hợp.

## 10. Private constructor và singleton: không tự đồng nghĩa

**Singleton** là mẫu thiết kế nhằm cung cấp một instance dùng chung theo phạm vi quản lý định trước. Một private constructor **chỉ giới hạn đường tạo thông thường**; nếu không có instance được tạo hoặc API trả instance, nó không tự tạo singleton.

Một cách viết đơn giản, dùng khởi tạo eager:

Lưu thành **`SingletonDemo.java`**:

```java
final class Settings {
    private static final Settings INSTANCE = new Settings();

    private int level;

    private Settings() {
        level = 1;
    }

    static Settings getInstance() {
        return INSTANCE;
    }

    int getLevel() {
        return level;
    }

    void setLevel(int level) {
        this.level = level;
    }
}

public class SingletonDemo {
    public static void main(String[] args) {
        Settings first = Settings.getInstance();
        Settings second = Settings.getInstance();

        first.setLevel(3);

        System.out.println(first == second);
        System.out.println(second.getLevel());
    }
}
```

```bash
javac -encoding UTF-8 SingletonDemo.java
java SingletonDemo
```

**Stdout:**

```text
true
3
```

Ở ví dụ này:

- `Settings.INSTANCE` là một field `static final` được khởi tạo bằng constructor private từ **bên trong `Settings`**.
- `getInstance()` trả **cùng giá trị tham chiếu** qua các lần gọi.
- Gán lại một biến tham chiếu ở caller không thay đổi instance chung; sửa `level` qua một tham chiếu được thấy qua tham chiếu còn lại.
- `final class Settings` chặn kế thừa lớp, nhưng chưa tự động làm dữ liệu của nó bất biến hoặc thread-safe.
- Phạm vi “một instance” thực tế còn phụ thuộc môi trường nạp lớp, chẳng hạn các class loader khác nhau; cần xét kỹ nếu đòi hỏi bảo đảm đặc biệt.

### 10.1. Enum singleton trong những tình huống phù hợp

Java có mẫu **enum singleton**:

```java
enum GlobalCounter {
    INSTANCE;

    private int count;

    int next() {
        return ++count;
    }
}
```

Với `GlobalCounter.INSTANCE.next()`, không có đường `new GlobalCounter()` từ ứng dụng. Java áp dụng những bảo đảm chuyên biệt cho enum đối với cơ chế tạo các hằng, serialization và reflective constructor invocation so với lớp thường.

Tuy nhiên, `count++` trong ví dụ **không an toàn khi nhiều thread đồng thời tăng**. Enum singleton giúp giới hạn kiểu instance theo cơ chế ngôn ngữ, **không tự làm mọi phương thức thread-safe**. Khi cần đồng thời, hãy bổ sung `AtomicInteger`/đồng bộ hoặc thiết kế trạng thái bất biến.

Chọn singleton chỉ khi có lý do thực sự cần trạng thái chia sẻ; không dùng singleton chỉ để né việc truyền dependency trong một thiết kế dễ kiểm thử.

## 11. Constructor private và kế thừa

Một lớp con thông thường phải gọi một constructor superclass truy cập được, trực tiếp hoặc qua constructor chaining. Nếu superclass chỉ có constructor private và không có cơ chế truy cập cho lớp con trong ngữ cảnh thích hợp, một lớp ngoài không thể extends superclass đó theo cách thông thường.

Ví dụ minh họa lỗi:

```java
class Base {
    private Base() {
    }
}

class Derived extends Base {
    Derived() {
        // super() ngầm định không truy cập được Base().
    }
}
```

Lớp `Derived` không biên dịch vì constructor của superclass không truy cập được từ ngữ cảnh đó. Khai báo riêng `Derived()` không giải quyết khi không có constructor cha thích hợp để gọi.

**Nếu mục tiêu là cho phép lớp con nhưng cấm tạo superclass trực tiếp từ package ngoài**, thường dùng `protected constructor`, kết hợp abstract class nếu lớp cơ sở không nên được tạo:

```java
abstract class Base {
    protected Base() {
    }
}

class Derived extends Base {
    Derived() {
        super();
    }
}
```

**Nếu mục tiêu là cấm kế thừa một lớp**, dùng `final class` rõ ràng, không dựa hoàn toàn vào private constructors. Lý do: quyền truy cập private trong các ngữ cảnh lồng nhau và những cơ chế đặc biệt có thể khiến việc khẳng định tuyệt đối “private constructor thì không thể có subclass” không chính xác ở mọi trường hợp.

### Ví dụ tránh hiểu nhầm: subclass không “nhận” constructor từ cha

```java
class Parent {
    protected Parent(int code) {
    }
}

class Child extends Parent {
    Child(int code) {
        super(code);
    }
}
```

Constructor `Child(int)` là constructor **của Child**, không phải constructor `Parent(int)` được kế thừa. `super(code)` chỉ **gọi** constructor superclass như một bước trong quá trình tạo `Child`.

## 12. Default constructor: access mặc định không phải luôn `public`

Java có quy tắc riêng khi bạn **không khai báo constructor nào**. Trình biên dịch sẽ cung cấp **default constructor không tham số** nếu lớp thuộc loại được áp dụng quy tắc này, với mức truy cập tương ứng với **mức truy cập của lớp** theo quy tắc ngôn ngữ.

Ví dụ:

```java
public class PublicBox {
    int value;
}
```

Nếu không có superclass đặc biệt cản trở `super()` ngầm định, `PublicBox` nhận default constructor không tham số có mức truy cập public; mã bên ngoài có thể `new PublicBox()` nếu truy cập được kiểu.

So sánh:

```java
class PackageBox {
    int value;
}
```

`PackageBox` là top-level package-private; default constructor tương ứng không mở loại này thành API công khai cho package khác.

**Nhưng chỉ cần bạn khai báo bất kỳ constructor nào**, Java không tự bổ sung default no-arg constructor nữa:

```java
public class User {
    private User(String name) {
    }

    public static User create(String name) {
        return new User(name);
    }
}
```

Vì đã khai báo `private User(String)`, Java không tự thêm `public User()`. Ngoài ra không có constructor `User()` nào được khai báo. Vì vậy mã ngoài không thể gọi `new User()` hay `new User("An")`; chỉ dùng `User.create(...)`.

### 12.1. Khác biệt giữa “default constructor” và “no-arg constructor”

- **Default constructor** là constructor **do compiler tự tạo** khi không có constructor nào được khai báo.
- **Explicit no-arg constructor** là constructor `Type() { ... }` **do lập trình viên viết**, có mức truy cập tùy theo modifier của chính nó.

Ví dụ:

```java
public class Config {
    private Config() {
    }
}
```

Constructor ở đây là **private no-arg constructor tường minh**, không phải default constructor do compiler sinh. `new Config()` từ lớp khác bị chặn bởi `private`; đây là kỹ thuật thường gặp trong utility/factory.

## 13. Khác nhau giữa quyền truy cập lớp, constructor và method

Lưu ý ba khai báo riêng:

```java
public final class Report {
    private final String title;

    private Report(String title) {
        this.title = title;
    }

    public static Report of(String title) {
        return new Report(title);
    }

    public String title() {
        return title;
    }
}
```

Nếu lưu thành `Report.java`:

- `public final class Report`: bên ngoài có thể sử dụng kiểu `Report` nếu các điều kiện truy cập phù hợp; không được kế thừa `Report`.
- `private Report(String)`: bên ngoài thông thường không gọi constructor trực tiếp.
- `public static Report of(String)`: bên ngoài có thể yêu cầu tạo object qua factory.
- `public String title()`: bên ngoài có thể đọc tên thông qua method.
- `private final String title`: bên ngoài không đọc field trực tiếp bằng `report.title` và không được gán lại field sau khởi tạo.

**Tách biệt ba mức** giúp thiết kế API linh hoạt: người dùng thấy kiểu công khai và các thao tác cần thiết mà không biết hoặc không trực tiếp chọn cách tạo/khởi tạo.

### 13.1. Private constructor không bảo đảm mọi field/method đều private

`private` chỉ áp dụng cho **constructor được bổ nghĩa**, không tự lan sang toàn bộ lớp. Một lớp có constructor private vẫn có thể chứa các static/instance public methods, public constants, và các constructor khác ở mức truy cập khác nếu lập trình viên khai báo.

Ví dụ:

```java
class Token {
    private Token() {
    }

    Token(String value) {
    }
}
```

Constructor `Token()` là private nhưng `Token(String)` là package-private. Một lớp khác **cùng package** vẫn có thể viết `new Token("abc")`. Vì thế, nếu mục tiêu là **ngăn mọi caller bên ngoài kiểu gọi mọi đường `new`**, cần rà soát **tất cả constructor**, không chỉ một constructor.

## 14. Factory trả về interface hoặc implementation ẩn

Factory có thể tạo đối tượng thuộc một lớp triển khai mà mã gọi không cần biết constructor hoặc thậm chí không cần nhìn thấy kiểu cụ thể.

Lưu tệp **`ServiceDemo.java`**:

```java
interface MessageService {
    String send(String message);
}

final class ConsoleMessageService implements MessageService {
    private final String prefix;

    private ConsoleMessageService(String prefix) {
        this.prefix = prefix;
    }

    static ConsoleMessageService create(String prefix) {
        return new ConsoleMessageService(prefix);
    }

    @Override
    public String send(String message) {
        return prefix + ": " + message;
    }
}

public class ServiceDemo {
    static MessageService messageService() {
        return ConsoleMessageService.create("INFO");
    }

    public static void main(String[] args) {
        MessageService service = messageService();
        System.out.println(service.send("Hello"));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ServiceDemo.java
java ServiceDemo
```

Stdout:

```text
INFO: Hello
```

Trong chương trình:

- Mã gọi giữ tham chiếu qua **interface `MessageService`**, không cần `new ConsoleMessageService(...)`.
- `ConsoleMessageService` có constructor private; chỉ static factory nội bộ được gọi nó trong ví dụ.
- `ServiceDemo.messageService()` quyết định kiểu triển khai được dùng và trả về interface.
- Muốn thay một triển khai khác phù hợp, có thể sửa factory mà không đổi API dùng interface ở nơi gọi.

Ví dụ trên đặt các kiểu trong một tệp cho dễ học. Trong dự án thật, người ta thường tách public API, factory và implementation vào các tệp/package phù hợp, đặc biệt nếu implementation cần được ẩn bằng package-private.

**Không có yêu cầu mọi factory phải trả về đúng kiểu lớp chứa nó.** Factory có thể trả về interface, superclass hoặc implementation khác miễn phù hợp kiểu trả về đã khai báo.

## 15. Constructor với nhiều access level: chọn overload phù hợp

Một lớp có thể khai báo các constructor **khác số lượng/kiểu tham số**, mỗi constructor có mức truy cập riêng:

```java
class Measurement {
    private final double value;

    public Measurement(int value) {
        this.value = value;
    }

    private Measurement(double value) {
        this.value = value;
    }

    static Measurement exact(double value) {
        return new Measurement(value);
    }

    double value() {
        return value;
    }
}
```

Nếu caller nằm cùng tệp/package nhưng **ngoài lớp `Measurement`**, có thể gọi `new Measurement(5)` qua constructor `public`. Không được gọi trực tiếp `new Measurement(2.5)` bằng constructor `private`; hãy dùng `Measurement.exact(2.5)`.

**Điểm cần nhớ:** mỗi overload constructor có **quyền truy cập riêng**. Không phải “một constructor public làm mọi constructor của lớp thành public”.

Khi thiết kế overload, đặc biệt nếu có cả constructor private và public, kiểm tra kiểu đối số cũng như quy tắc chọn overload. Đừng dựa vào việc “compiler sẽ tự chuyển sang một overload public bất kỳ” nếu overload cụ thể nhất không truy cập được: quy tắc lựa chọn và kiểm tra truy cập có thể khiến lời gọi bị lỗi. Khi cần đường gọi rõ ràng, dùng factory hoặc ép kiểu một cách có chủ đích, phù hợp hợp đồng.

## 16. Constructor không phải phương thức: những quy tắc dễ nhầm

### 16.1. Constructor không có kiểu trả về

```java
class Device {
    Device() {            // Constructor
    }

    void Device(int id) { // Method, không phải constructor
    }
}
```

`void Device(int)` là method do có từ khóa `void` trước tên. Nó không được `new Device(5)` gọi như constructor. Constructor phải có **tên trùng lớp và không khai báo kiểu trả về**.

### 16.2. Constructor không được override

Một subclass không override constructor superclass; nó khai báo constructor **mang tên chính subclass** rồi có thể gọi `super(...)`. Constructor cũng không được ghi `static`, `abstract`, `final` hoặc `synchronized` như một số method.

### 16.3. Constructor private vẫn chạy trong quá trình `new` hợp lệ

`private` không có nghĩa constructor “không chạy”. Khi `Account.open(...)` gọi `new Account(...)` từ trong `Account`, constructor thực thi bình thường. Giới hạn chỉ là **ai được viết lời gọi hợp lệ**, không phải một chế độ tắt constructor.

### 16.4. `return` trong constructor không trả đối tượng

Constructor có thể dùng `return;` (không biểu thức) trong những vị trí hợp lệ để kết thúc sớm, nhưng **không thể viết `return new Object();`** để thay đối tượng đang được khởi tạo. Nếu cần chọn/return một object có sẵn, hãy dùng **factory method**.

### 16.5. `this(...)` và `super(...)` vẫn phải tuân thủ truy cập

Trong Java 17, lời gọi tường minh `this(...)` hoặc `super(...)` phải là câu lệnh đầu tiên của constructor. `this(...)` gọi constructor khác trong cùng lớp; `super(...)` gọi constructor superclass **có thể truy cập**. Constructor private của lớp cha không tự trở thành truy cập được chỉ vì nó đứng ở vị trí `super(...)`.

## 17. Những giới hạn thực tế của “ngăn tạo từ bên ngoài”

Quyền truy cập constructor là cơ chế **kiểm tra trong ngôn ngữ Java**. Nó rất hữu ích để định hình API, nhưng không phải một sandbox bảo mật chống lại mọi cách can thiệp vào JVM.

Cần phân biệt:

1. **Mã Java bình thường, tuân theo compile-time access checks:** constructor private chặn `new Type(...)` từ các lớp không có quyền.
2. **Reflection:** một số công cụ có thể thử truy cập constructor phi public; khả năng vượt access checks phụ thuộc module openness, quyền truy cập và quy tắc runtime. Java Platform Module System có thể hạn chế deep reflection.
3. **Serialization:** với một số cơ chế khôi phục đối tượng, quá trình tạo/khôi phục không đi qua constructor của lớp theo cách giống biểu thức `new` thông thường. Thiết kế singleton/factory có thể cần xem xét `readResolve` và ràng buộc khác.
4. **Các framework/ORM/DI:** có thể yêu cầu constructor không tham số và mức truy cập phù hợp, hoặc dùng reflection/proxy/bytecode. Đừng đóng private mọi constructor nếu framework đang dùng đòi một cách khởi tạo riêng.
5. **Class loader, instrumentation hoặc mã đặc quyền:** có thể tạo ra các tình huống ngoài mô hình gọi constructor bình thường. `private` không được quảng bá như rào cản an ninh tuyệt đối.

**Kết luận thực hành:** “Ngăn tạo đối tượng từ bên ngoài” ở đây nghĩa là **hạn chế lời gọi constructor trực tiếp theo access modifiers**. Nếu cần các bảo đảm mạnh hơn (ví dụ singleton bất kể serialization/reflection), phải xem cả cơ chế tạo object và môi trường chạy, không chỉ thêm `private`.

## 18. Lỗi phổ biến và cách xử lý

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `new Account(...)` báo constructor private | Caller không được truy cập private constructor | Dùng public factory hoặc thay đổi API có chủ đích |
| Lớp `public` nhưng `new Type(...)` từ package khác không biên dịch | Constructor được khai báo package-private/protected/private | Kiểm tra **access của constructor**, không chỉ lớp |
| `new Book(...)` không gọi được dù `Book` đã `import` | `import` không thay đổi quyền truy cập constructor | Sử dụng factory công khai hoặc constructor phù hợp |
| Constructor `protected` được `super(...)` gọi, nhưng `new Base(...)` thất bại | Quy tắc protected khác nhau theo ngữ cảnh kế thừa | Chỉ dùng `super(...)` trong subclass hoặc cung cấp public API |
| `new Type()` bất ngờ vẫn được phép khi không viết constructor nào | Compiler tự cung cấp default constructor khi đủ điều kiện | Khai báo constructor private nếu muốn hạn chế tạo ngoài |
| Đã viết `private Type(int)` nhưng tưởng vẫn có default `Type()` | Có một constructor tường minh nên compiler không tự thêm no-arg | Thêm no-arg constructor tường minh nếu cần |
| Chỉ một overload private, overload khác public vẫn tạo được | Quyền truy cập gắn với từng constructor | Rà soát tất cả constructor |
| Subclass không thể extends lớp cha có private constructor | Không gọi được superclass constructor | Dùng protected/package-private/public constructor phù hợp hoặc đổi thiết kế |
| Factory vẫn cho tạo dữ liệu sai | Factory không tự hợp lệ hóa mọi đầu vào | Viết kiểm tra dữ liệu và giữ invariant trong factory/constructor |
| Private constructor nhưng class vẫn bị subclass trong mã lồng liên quan | Quy tắc nested/nestmate có thể cho truy cập đặc biệt | Dùng `final class` khi thật sự muốn cấm kế thừa |
| Singleton có private constructor nhưng nhiều thread cập nhật sai | `private` không bảo đảm thread safety | Đồng bộ hoặc dùng kiểu dữ liệu đồng thời phù hợp |
| Framework không tạo được đối tượng | Constructor không đúng access/no-arg contract mà framework cần | Tuân thủ contract của framework hoặc cung cấp factory/adapter |
| `void User()` bị hiểu sai là constructor | Đây là method trùng tên lớp | Bỏ `void` nếu muốn khai báo constructor |
| Constructor `private` khiến thư viện khác không thể dùng kiểu trả về | Caller không được khởi tạo trực tiếp, không đồng nghĩa không thể **nhận instance** | Đưa ra factory/API trả về đối tượng đúng mức truy cập |

Các lỗi thông báo cụ thể có thể thay đổi theo JDK, package, module và chữ ký được chọn. Khi chẩn đoán, bắt đầu từ khai báo constructor, không chỉ xem dấu `new`.

## 19. Bài tự luyện: dự đoán quyền truy cập và đầu ra

### Bài 1 — Public class, private constructor

```java
public class Card {
    private Card() {
    }

    public static Card issue() {
        return new Card();
    }
}
```

Từ một lớp khác cùng package, lời gọi nào hợp lệ?

- `new Card()` → **Không**: constructor private.
- `Card.issue()` → **Có**: factory public thực thi `new Card()` trong chính lớp `Card`.
- Khai báo biến `Card card = Card.issue();` → **Có**: caller được dùng kiểu `Card` và instance do factory cung cấp.

### Bài 2 — Package-private constructor

```java
package store;

public class Item {
    Item() {
    }
}
```

**Đáp án:** `new Item()` hợp lệ từ một lớp khác **cùng package `store`** khi mã có thể truy cập. Từ package `app`, dù đã `import store.Item;`, `new Item()` vẫn **không được** vì constructor package-private.

### Bài 3 — Protected constructor và subclass ngoài package

Giả sử `core.Base`:

```java
package core;

public class Base {
    protected Base() {
    }
}
```

Và `app.Child`:

```java
package app;

public class Child extends core.Base {
    public Child() {
        super();
    }
}
```

**Đáp án:** `new Child()` hợp lệ từ nơi có quyền dùng `Child`; `super()` truy cập được protected constructor cha. Một lớp không liên quan trong package `app` không được gọi `new core.Base()` trực tiếp.

### Bài 4 — Utility class

```java
final class NumberUtil {
    private NumberUtil() {
    }

    static int doubleOf(int n) {
        return n * 2;
    }
}
```

**Đáp án:** `NumberUtil.doubleOf(6)` trả `12` mà không cần thể hiện `NumberUtil`. `new NumberUtil()` từ một lớp khác không hợp lệ vì constructor private. `final` cấm kế thừa lớp, còn `private` chặn gọi constructor từ bên ngoài.

### Bài 5 — Singleton có chắc bất biến?

```java
final class Holder {
    static final Holder INSTANCE = new Holder();
    int value;

    private Holder() {
    }
}
```

**Đáp án:** Không. `INSTANCE` là một field tham chiếu `static final`, nhưng `INSTANCE.value` vẫn có thể thay đổi từ mã có quyền truy cập field đó. `static final` không làm object được tham chiếu tự động immutable.

### Bài 6 — Constructor và factory khác nhau gì?

```java
class Message {
    private Message(String value) {
    }

    static Message create(String value) {
        return new Message(value);
    }
}
```

**Đáp án:** `Message(String)` là constructor (không có return type, tên trùng lớp). `create(String)` là static method có kiểu trả về `Message`. `new Message(value)` chỉ được gọi tại vị trí có quyền như trong `Message.create`. Không phải “constructor trả về Message”.

### Bài 7 — Tìm lỗi trong dự đoán

Có người nói: “Chỉ cần ghi `private User()` thì không bao giờ có instance `User`.”

**Đáp án:** Sai. Ngay bên trong lớp `User` có thể gọi private constructor và đưa đối tượng cho caller qua static factory. `private` giới hạn đường gọi từ bên ngoài; nó **không** cấm tạo object trong các ngữ cảnh có quyền.

## 20. Checklist thiết kế access cho constructor

1. **Lớp có public API không?** Nếu không, có thể đặt top-level class package-private; không nhất thiết cần public class với private constructor.
2. **Ai cần trực tiếp `new`?** Nếu bên ngoài phải tự tạo, cân nhắc public constructor; nếu chỉ nội bộ package, dùng package-private.
3. **Có cần subclass từ package khác không?** Cân nhắc protected constructor và thiết kế abstract superclass nếu phù hợp.
4. **Muốn chỉ API bên trong quyết định tạo object?** Dùng private constructor và một factory/entry point có quyền truy cập phù hợp.
5. **Có bao nhiêu constructor overload?** Kiểm tra access **từng constructor**, tránh để lộ một đường tạo mà không chủ định.
6. **Có constructor mặc định ngầm định không?** Khi không khai báo constructor nào, compiler có thể thêm default constructor. Khai báo tường minh để kiểm soát.
7. **API public có method và field phù hợp không?** Caller có thể sử dụng object được factory tạo ra, dù không tự `new`.
8. **Lớp có được kế thừa không?** Nếu muốn chặn kế thừa, ghi `final`; nếu cần kế thừa, bảo đảm constructor cha truy cập được.
9. **Constructor/factory có bảo vệ invariant không?** Kiểm tra null, dữ liệu rỗng, miền giá trị, tham chiếu mutable và điều kiện nghiệp vụ.
10. **Có framework liên quan không?** Kiểm tra yêu cầu no-arg constructor, access và reflection trước khi ẩn constructor.
11. **Có trạng thái chia sẻ/singleton không?** `private` không bảo đảm một instance hoặc thread safety; thêm thiết kế đồng bộ/khởi tạo thích hợp.
12. **Mã ví dụ có đúng package và tên tệp không?** Constructor public/protected/private phải nằm trong khai báo lớp; lớp top-level `public` phải được đặt ở tệp nguồn có tên khớp với kiểu trong quy trình biên dịch thông thường.

## Ghi nhớ

- **Quyền truy cập constructor khác với quyền truy cập lớp**. Một kiểu `public` vẫn có thể không cho mã ngoài gọi `new` trực tiếp.
- **`public`:** mở quyền gọi constructor cho mã có thể truy cập; **package-private:** chỉ cùng package; **`protected`:** cùng package và các tình huống kế thừa hợp lệ; **`private`:** giới hạn rất chặt lời gọi.
- **Private constructor không cấm lớp tự tạo object**. Nó thường kết hợp với **static factory**, utility class hoặc một thiết kế kiểm soát vòng đời đối tượng.
- **Default constructor** được compiler cung cấp khi **không khai báo constructor nào**; một constructor private đã khai báo sẽ ngăn việc tự sinh default constructor.
- **Constructor cha không được kế thừa**. Subclass phải có đường gọi superclass constructor truy cập được; protected constructor thường phục vụ mục tiêu này.
- **Ngăn `new` từ bên ngoài không có nghĩa object không thể tồn tại hoặc không thể được sử dụng**, và cũng không đồng nghĩa bảo mật tuyệt đối chống reflection/serialization.
