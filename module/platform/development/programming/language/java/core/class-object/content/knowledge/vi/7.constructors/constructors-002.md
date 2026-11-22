# Hàm khởi tạo (constructor) trong Java: cú pháp, tên và điểm khác biệt với phương thức

**Constructor (hàm khởi tạo)** là thành phần của lớp được thực thi trong quá trình tạo thể hiện nhằm thiết lập trạng thái ban đầu của đối tượng. Trong Java, constructor có hình thức giống một phương thức với tên và dấu ngoặc tham số, nhưng có **những quy tắc riêng**:

- **Tên constructor phải trùng chính xác tên đơn giản của lớp** đang khai báo (phân biệt chữ hoa/chữ thường).
- **Constructor không khai báo kiểu trả về**, kể cả `void`. Nếu thêm `void`, khai báo đó là **phương thức**, không phải constructor.
- Constructor của lớp thông thường được gọi trong quá trình tạo đối tượng bằng `new ClassName(...)` hoặc được gọi từ constructor khác thông qua `this(...)`/`super(...)`.
- Constructor có thể **nạp chồng** (*overload*) theo danh sách tham số, nhưng **không được kế thừa hoặc ghi đè (override)** như instance method.
- Constructor có thể kiểm tra dữ liệu, khởi tạo field và ném ngoại lệ khi đầu vào không hợp lệ.

Ví dụ ngắn:

```java
class Student {
    String name;

    Student(String name) {  // Constructor: không có kiểu trả về
        this.name = name;
    }

    void printName() {     // Method: có kiểu trả về void
        System.out.println(name);
    }
}
```

Trong `new Student("An")`, `Student(String name)` là constructor được gọi để khởi tạo một `Student` mới. `printName()` là phương thức được gọi **sau đó** trên đối tượng, ví dụ `student.printName()`. Hai thành phần khác mục đích và khác cú pháp, mặc dù đều có phần thân trong dấu ngoặc nhọn.

## 1. Cú pháp khai báo constructor

Dạng khai báo cơ bản với lớp thông thường:

```java
[accessModifier] ClassName(parameterList) [throws ExceptionType] {
    // Kiểm tra đầu vào và khởi tạo đối tượng
}
```

Đây là **sơ đồ**, không phải đoạn Java độc lập để biên dịch. Một constructor có thể có annotation, tham số kiểu generic, khai báo `throws` và các quy tắc đặc biệt khác; trong bài học ban đầu hãy ghi nhớ **tên lớp + danh sách tham số + thân**, không đặt kiểu trả về ở trước tên.

Ví dụ:

```java
class Book {
    String title;
    int pages;

    Book() {
        this.title = "Chưa đặt tên";
        this.pages = 0;
    }

    Book(String title, int pages) {
        this.title = title;
        this.pages = pages;
    }
}
```

`Book()` và `Book(String title, int pages)` đều là constructor của lớp `Book`. Tên `Book` khớp tên lớp. Hai constructor khác **số lượng tham số** nên có thể cùng tồn tại.

Các thành phần của một khai báo:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Access modifier tùy chọn | `public`, `protected`, `private` hoặc bỏ modifier | Kiểm soát nơi được phép gọi constructor |
| Tên constructor | `Book` | Phải trùng tên đơn giản của lớp |
| Danh sách tham số | `String title, int pages` | Dữ liệu đầu vào để khởi tạo |
| Mệnh đề `throws` tùy chọn | `throws IllegalArgumentException` | Khai báo loại ngoại lệ liên quan (unchecked exception không bắt buộc khai báo) |
| Thân constructor | `{ this.title = title; }` | Logic khởi tạo thể hiện |
| Kiểu trả về | **Không có** | Constructor khác method ở điểm này |

**Không nhầm constructor với lời gọi `new`:** trong biểu thức `new Book("Java", 250)`, từ khóa `new` tham gia **tạo và khởi tạo đối tượng** và biểu thức có kiểu `Book`. Bản thân constructor **không phải phương thức trả về `Book`**, cũng không viết `return this;`.

## 2. Tên constructor phải khớp tên lớp

Tên constructor là tên đơn giản của lớp chứa nó, phân biệt ký tự hoa và thường.

Ví dụ hợp lệ:

```java
class Employee {
    Employee() {
        System.out.println("Đã tạo Employee");
    }
}
```

Ví dụ **không hợp lệ**:

```java
class Employee {
    employee() {                 // SAI: khác chữ hoa/chữ thường
        System.out.println("Hi");
    }
}
```

Trong ví dụ sai, `employee()` không phải constructor của `Employee`. Vì thiếu kiểu trả về, nó cũng không phải khai báo method hợp lệ.

Tương tự, constructor không được mang một tên tùy ý:

```java
class Employee {
    CreateEmployee() {           // SAI: tên không trùng lớp và thiếu return type
    }
}
```

Nếu muốn có chức năng tên `createEmployee`, có thể viết một **phương thức factory** có kiểu trả về cụ thể thay vì giả lập constructor:

```java
class Employee {
    Employee() {
    }

    static Employee createEmployee() {
        return new Employee();
    }
}
```

Ở đây `Employee()` là constructor, còn `createEmployee()` là **static method** trả về tham chiếu `Employee`. Phương thức factory có thể đặt tên có nghĩa như `of(...)` hoặc `create(...)`, trong khi constructor bắt buộc mang đúng tên lớp.

### 2.1. Phương thức có tên trùng lớp vẫn có thể tồn tại

Một khai báo **có kiểu trả về** là phương thức ngay cả khi phần tên trùng tên lớp:

```java
class Robot {
    void Robot() {
        System.out.println("Đây là method, không phải constructor");
    }
}
```

`void Robot()` **không** là constructor. Vì lớp `Robot` chưa khai báo constructor thật nào nên, trong điều kiện lớp cha cho phép, Java tự cung cấp **default constructor không tham số**. `new Robot()` không tự in thông báo; chỉ lời gọi tường minh `robot.Robot()` mới thực thi method trên.

Dù có thể hợp lệ về ngôn ngữ, **không nên đặt method trùng tên lớp**: nó rất dễ bị nhầm với constructor. Dùng tên mô tả hành vi, chẳng hạn `initialize()`, `printStatus()`.

## 3. Ví dụ Java 17 hoàn chỉnh: constructor và phương thức cạnh nhau

Lưu toàn bộ mã sau vào **`ConstructorVsMethodDemo.java`**:

```java
class Person {
    private final String name;
    private int age;

    Person(String name) {
        this(name, 0);
    }

    Person(String name, int age) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        if (age < 0) {
            throw new IllegalArgumentException("Tuổi không hợp lệ");
        }
        this.name = name;
        this.age = age;
    }

    String describe() {
        return name + " (" + age + ")";
    }

    void birthday() {
        age++;
    }
}

public class ConstructorVsMethodDemo {
    public static void main(String[] args) {
        Person an = new Person("An");
        Person binh = new Person("Bình", 20);

        System.out.println(an.describe());
        System.out.println(binh.describe());

        binh.birthday();
        System.out.println(binh.describe());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 ConstructorVsMethodDemo.java
java ConstructorVsMethodDemo
```

**Stdout chính xác:**

```text
An (0)
Bình (20)
Bình (21)
```

Giải thích:

1. `Person(String name)` là constructor **một tham số**, còn `Person(String name, int age)` là constructor **hai tham số**. Cả hai có tên `Person` và không khai báo kiểu trả về.
2. `new Person("An")` chọn constructor một tham số. Câu lệnh `this(name, 0);` gọi constructor hai tham số **trong cùng lớp**, tạo giá trị tuổi mặc định `0`.
3. `new Person("Bình", 20)` gọi trực tiếp constructor hai tham số.
4. Cả hai đường khởi tạo đều đến logic kiểm tra tên/tuổi và gán các field `name`, `age`.
5. `describe()` là **method trả về `String`**; bên gọi có thể truyền giá trị nhận được cho `System.out.println`.
6. `birthday()` là **method `void`**; nó cập nhật field `age` của đối tượng đã tồn tại. Gọi `birthday()` không tạo một đối tượng `Person` mới.
7. `name` là `final instance field`, được gán trong quá trình khởi tạo; `age` có thể thay đổi qua method.

Chỉ `ConstructorVsMethodDemo` là top-level `public`, vì vậy tên tệp nguồn là `ConstructorVsMethodDemo.java`. `Person` là top-level package-private trong cùng tệp.

## 4. Những điểm khác biệt giữa constructor và method

| Tiêu chí | Constructor | Method |
| --- | --- | --- |
| Mục đích chính | Khởi tạo một thể hiện khi được tạo | Thực hiện hành vi; có thể đọc, sửa hoặc tính toán |
| Tên | Phải trùng tên đơn giản của lớp | Do lập trình viên đặt theo cú pháp tên hợp lệ |
| Kiểu trả về trong khai báo | **Không được ghi**, kể cả `void` | Phải khai báo một kiểu hoặc `void` |
| Cách gọi thông thường | `new Type(arguments)` hoặc qua `this(...)`/`super(...)` | `object.method(arguments)` hay `Type.staticMethod(arguments)` |
| Nạp chồng | Có, theo danh sách tham số | Có, theo danh sách tham số |
| Kế thừa | **Không**; lớp con không thừa hưởng constructor của lớp cha | Instance method phù hợp có thể được kế thừa |
| Ghi đè | **Không** | Instance method đủ điều kiện có thể được override |
| `static` | **Không được phép** | Được phép với static method |
| `abstract`/`final` | **Không áp dụng làm modifier constructor** | Có thể áp dụng cho phương thức trong ngữ cảnh hợp lệ |
| `return;` | Có thể dùng để kết thúc sớm, không kèm giá trị | Hợp lệ trong method `void` |
| `return expression;` | **Không được phép** | Bắt buộc/được phép tùy kiểu trả về của method |
| Tạo đối tượng mới? | Tham gia quá trình tạo một đối tượng được yêu cầu | Không tự động; chỉ tạo đối tượng nếu thân method có thao tác tương ứng |
| Quyền truy cập | Có các mức `public`/`protected`/package-private/`private` | Cũng có các mức phù hợp |

**Phân biệt rất quan trọng:** biểu thức `new Student(...)` **cho ra tham chiếu đến đối tượng**, nhưng không phải constructor có kiểu trả về `Student`. Kết quả biểu thức `new` và **return type của method** là hai khái niệm khác nhau.

### Constructor không phải “method đặc biệt có return type void”

Cách giải thích “constructor là phương thức `void` tự chạy” là **không đúng về cú pháp và mô hình ngôn ngữ**. Hai khai báo:

```java
class Demo {
    Demo() { }          // Constructor
    void run() { }      // Method void
}
```

khác nhau vì `Demo()` không có khai báo return type, còn `run()` có `void`. Nếu viết `void Demo() { }` thì đó là **method tên Demo**, không phải constructor.

## 5. `new` gọi constructor nào?

Khi một lớp có nhiều constructor khác nhau, Java chọn constructor phù hợp với **số lượng và kiểu biểu thức đối số**:

```java
class Box {
    int capacity;

    Box() {
        this.capacity = 0;
    }

    Box(int capacity) {
        this.capacity = capacity;
    }

    Box(String label) {
        this.capacity = label.length();
    }
}
```

Lời gọi ở một phương thức có quyền truy cập:

```java
Box a = new Box();             // Box()
Box b = new Box(10);           // Box(int)
Box c = new Box("Java");       // Box(String)
```

Khi đó các `capacity` lần lượt là `0`, `10` và `4`. Đây là **constructor overloading**. Các constructor cùng tên `Box` nhưng có **danh sách tham số khác nhau**.

Không thể khai báo hai constructor **chỉ khác tên tham số**:

```java
class Item {
    Item(int quantity) { }

    // Item(int amount) { }  // SAI nếu bỏ comment: cùng chữ ký Item(int)
}
```

Cũng không có chuyện “nạp chồng constructor bằng kiểu trả về” vì constructor **không có kiểu trả về để nạp chồng**.

### Constructor chỉ nhận các tham số được khai báo

`new Box("Java", 3)` không hợp lệ với ba constructor `Box` ở trên vì không có chữ ký nhận `(String, int)`. Nếu muốn hỗ trợ cách tạo đó, khai báo thêm constructor phù hợp hoặc dùng factory.

Trình biên dịch kiểm tra **kiểu và số lượng đối số tại compile time**, kể cả khi tham số dùng widening, boxing hay varargs theo quy tắc Java. Lựa chọn constructor không dựa vào tên biến đối số.

## 6. Constructor không tham số: mặc định khác tường minh

Có hai khái niệm thường bị gọi chung là “constructor mặc định”:

1. **Default constructor do trình biên dịch tự cung cấp:** chỉ xuất hiện nếu lớp **không khai báo constructor nào**.
2. **No-argument constructor do lập trình viên viết:** có danh sách tham số rỗng `()`, nhưng **không** phải default constructor được compiler sinh.

Ví dụ **không viết constructor**:

```java
class EmptyBox {
    int size;
}
```

Khi biên dịch, Java ngầm cung cấp constructor không tham số cho `EmptyBox` nếu các điều kiện về superclass cho phép. Có thể tạo:

```java
EmptyBox box = new EmptyBox();
System.out.println(box.size); // 0
```

Field `size` nhận giá trị mặc định `0` của `int`. **Không nên suy ra** default constructor tự đặt mọi field về “giá trị nghiệp vụ hợp lý”; nó chỉ tham gia khởi tạo thông thường của Java.

Ví dụ **đã viết một constructor có tham số**:

```java
class SizeBox {
    int size;

    SizeBox(int size) {
        this.size = size;
    }
}
```

`new SizeBox(5)` hợp lệ, nhưng `new SizeBox()` **không** hợp lệ. Khi người viết khai báo `SizeBox(int size)`, Java **không còn tự cung cấp** default no-arg constructor.

Muốn cả hai cách tạo, khai báo hai constructor:

```java
class SizeBox {
    int size;

    SizeBox() {
        this(0);
    }

    SizeBox(int size) {
        this.size = size;
    }
}
```

Một constructor `SizeBox()` do lập trình viên viết là **no-arg constructor tường minh**. Nó có thể thiết lập mặc định nghiệp vụ hoặc ủy quyền sang constructor khác.

### Ví dụ chạy được: mặc định và no-arg tường minh

Lưu thành **`DefaultConstructorDemo.java`**:

```java
class DefaultBox {
    int count;
}

class ManualBox {
    int count;

    ManualBox() {
        count = 10;
    }

    ManualBox(int count) {
        this.count = count;
    }
}

public class DefaultConstructorDemo {
    public static void main(String[] args) {
        DefaultBox first = new DefaultBox();
        ManualBox second = new ManualBox();
        ManualBox third = new ManualBox(7);

        System.out.println(first.count);
        System.out.println(second.count);
        System.out.println(third.count);
    }
}
```

```bash
javac -encoding UTF-8 DefaultConstructorDemo.java
java DefaultConstructorDemo
```

Stdout:

```text
0
10
7
```

`DefaultBox` không khai báo constructor nào nên compiler cung cấp constructor mặc định. `ManualBox` có hai constructor viết tường minh, gồm no-arg và constructor một tham số.

**Quan trọng về superclass:** default constructor phải gọi superclass constructor phù hợp; nếu lớp cha không có constructor không tham số truy cập được, lớp con không thể dựa vào `super()` ngầm định mà không khai báo phương án khác.

## 7. Constructor chaining: `this(...)` và `super(...)`

Constructor có thể gọi constructor khác trong quá trình khởi tạo:

- **`this(arguments);`**: gọi một constructor khác **trong cùng lớp**.
- **`super(arguments);`**: gọi constructor của **lớp cha trực tiếp**.

Trong **Java 17**, một lời gọi constructor tường minh bằng `this(...)` hoặc `super(...)` phải xuất hiện như **câu lệnh đầu tiên trong thân constructor**. Không được đặt lệnh in, phép gán hay xử lý khác trước lời gọi đó.

### 7.1. `this(...)` giảm trùng lặp logic

```java
class Rectangle {
    final int width;
    final int height;

    Rectangle() {
        this(1, 1);
    }

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    int area() {
        return width * height;
    }
}
```

`new Rectangle()` gọi `Rectangle()`, rồi `this(1, 1)` ủy quyền sang `Rectangle(int, int)`. Nhờ đó phép gán field chỉ nằm ở một constructor.

`this(...)` **không tạo thêm đối tượng thứ hai**. Nó chuyển sang một constructor khác để khởi tạo **cùng một đối tượng đang được tạo**.

Không viết:

```java
class Invalid {
    Invalid() {
        System.out.println("Trước");
        this(1);               // SAI trong Java 17: this(...) không đầu thân
    }

    Invalid(int value) {
    }
}
```

### 7.2. `super(...)` gọi constructor cha

```java
class Vehicle {
    final String brand;

    Vehicle(String brand) {
        this.brand = brand;
    }
}

class Car extends Vehicle {
    final int seats;

    Car(String brand, int seats) {
        super(brand);
        this.seats = seats;
    }
}
```

Với `new Car("Honda", 4)`, constructor `Car(String, int)` cần gọi `Vehicle(String)` để khởi tạo phần trạng thái của lớp cha trước khi tiếp tục khởi tạo phần riêng của `Car`.

Nếu không viết `this(...)` hay `super(...)`, compiler thông thường chèn **`super();` ngầm định** vào constructor (bao gồm default constructor được sinh). Điều này chỉ biên dịch khi lớp cha có constructor không tham số truy cập được. Ví dụ sau **sai**:

```java
class Parent {
    Parent(int number) {
    }
}

class Child extends Parent {
    Child() {
        // super() ngầm định bị lỗi vì Parent không có Parent()
    }
}
```

Sửa thành:

```java
class Child extends Parent {
    Child() {
        super(1);
    }
}
```

Hai phiên bản khai báo `Child` là **phương án minh họa thay thế**, không đặt cùng trong một lần biên dịch. Khi superclass không có constructor zero-argument, hãy gọi đúng `super(arguments)` theo hợp đồng của superclass.

### 7.3. Không gọi `this(...)` và `super(...)` cùng trong một constructor

Trong Java 17 chỉ có một vị trí câu lệnh đầu tiên để thực hiện **explicit constructor invocation**, vì vậy không thể viết:

```java
class Child extends Parent {
    Child() {
        this(1);
        super(1);              // SAI: không thể có hai invocation như vậy
    }

    Child(int value) {
        super(value);
    }
}
```

Nếu `Child()` gọi `this(1)`, constructor `Child(int)` được gọi rồi tự gọi `super(value)`. Đây là **một chuỗi hợp lệ về ý tưởng**: không cần và không được chèn thêm `super(...)` sau `this(...)`.

**Không được tạo vòng lặp constructor**:

```java
class Loop {
    Loop() {
        this(1);
    }

    Loop(int value) {
        this();                 // SAI: recursive constructor invocation
    }
}
```

Mỗi chuỗi `this(...)` phải cuối cùng đến một constructor hoàn thành việc gọi constructor cha cần thiết; không thể vòng lặp mãi.

## 8. Thứ tự khởi tạo khi tạo đối tượng

Constructor không phải là toàn bộ quá trình khởi tạo đối tượng. Trong một trường hợp đơn giản tạo lớp con:

1. Phần bộ nhớ của đối tượng được tạo và các instance fields nhận **giá trị mặc định**.
2. Chuỗi constructor của lớp con đi qua `this(...)` hoặc `super(...)` để khởi tạo superclass; chuỗi constructor lên tới `Object` theo quy tắc Java.
3. Các **instance field initializers** và **instance initializer blocks** của superclass chạy theo thứ tự văn bản trước thân constructor của superclass.
4. Sau khi superclass được khởi tạo, các field initializers và instance initializers của lớp con chạy trước thân constructor của lớp con.
5. Thân constructor lớp con tiếp tục chạy; biểu thức `new` hoàn tất bình thường và tạo ra giá trị tham chiếu đến đối tượng.

Lớp cũng có **static initialization** khi được khởi tạo ở cấp lớp; thứ tự đó là vấn đề khác với việc mỗi đối tượng thực hiện instance initialization.

### Ví dụ Java 17: lớp cha trước, lớp con sau

Lưu thành **`InitializationOrderDemo.java`**:

```java
class Base {
    int baseValue = trace("Base field");

    Base() {
        System.out.println("Base constructor");
    }

    static int trace(String text) {
        System.out.println(text);
        return 1;
    }
}

class Derived extends Base {
    int derivedValue = trace("Derived field");

    Derived() {
        super();
        System.out.println("Derived constructor");
    }
}

public class InitializationOrderDemo {
    public static void main(String[] args) {
        new Derived();
    }
}
```

Lệnh:

```bash
javac -encoding UTF-8 InitializationOrderDemo.java
java InitializationOrderDemo
```

**Stdout chính xác:**

```text
Base field
Base constructor
Derived field
Derived constructor
```

Đây là trình tự quan sát được bởi việc khởi tạo field và chạy constructor cha/con. Phương thức static `trace` chỉ hỗ trợ việc in dòng khi field initializer chạy; nó không thêm một constructor mới.

**Lưu ý thực hành:** tránh gọi các instance method có thể bị override từ constructor nếu phương thức đó phụ thuộc vào trạng thái lớp con chưa khởi tạo xong. Constructor superclass có thể chạy trước field initializers của subclass, khiến việc gọi method override thấy trạng thái chưa hoàn chỉnh.

## 9. Quyền truy cập của constructor

Constructor có thể khai báo access modifier:

- **`public`:** có thể được gọi từ mã có quyền truy cập lớp và đáp ứng điều kiện module/package/classpath liên quan.
- **`protected`:** cho phép các dạng truy cập trong cùng package và theo quy tắc truy cập `protected` khi kế thừa từ package khác.
- **Không có modifier (package-private):** chỉ truy cập được từ mã thuộc cùng package trong phạm vi ngôn ngữ cho phép.
- **`private`:** giới hạn việc gọi vào phạm vi kiểu và các ngữ cảnh được Java cho phép; hay dùng để kiểm soát cách tạo thể hiện.

Ví dụ:

```java
public class Service {
    private final String name;

    public Service(String name) {
        this.name = name;
    }

    private Service() {
        this("Mặc định");
    }

    public String name() {
        return name;
    }
}
```

Nếu lưu thành `Service.java`, constructor `Service(String)` công khai còn `Service()` là private. Mã trong lớp `Service` có thể gọi `new Service()` nếu cần; mã thuộc lớp khác không thể gọi constructor private chỉ vì lớp `Service` được khai báo `public`.

**Lớp public không đồng nghĩa constructor tự động public.** Nếu viết `public class User { User() {} }`, constructor `User()` là **package-private**, do đó mã từ package khác không thể gọi `new User()`.

### 9.1. Private constructor cho factory

Lưu thành **`FactoryDemo.java`**:

```java
final class Ticket {
    private final int code;

    private Ticket(int code) {
        this.code = code;
    }

    static Ticket of(int code) {
        if (code <= 0) {
            throw new IllegalArgumentException("code must be positive");
        }
        return new Ticket(code);
    }

    int code() {
        return code;
    }
}

public class FactoryDemo {
    public static void main(String[] args) {
        Ticket ticket = Ticket.of(12);
        System.out.println(ticket.code());

        // new Ticket(12); // SAI ở đây: constructor private
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 FactoryDemo.java
java FactoryDemo
```

Stdout:

```text
12
```

`Ticket.of(12)` là static factory method được phép gọi constructor private từ **bên trong lớp `Ticket`**. Mã bên ngoài chỉ dùng factory, nhờ đó logic tạo đối tượng được kiểm soát và có thể thay đổi trong tương lai.

### 9.2. Private constructor trong utility class

Một lớp chỉ chứa các phương thức static thường có thể dùng private constructor để ngăn tạo thể hiện không có ý nghĩa:

```java
final class TextUtils {
    private TextUtils() {
        throw new AssertionError("No instances");
    }

    static String upper(String input) {
        return input.toUpperCase();
    }
}
```

Đây là đoạn khai báo minh họa, không có `main`. `TextUtils.upper("java")` có thể được gọi từ nơi được phép, nhưng `new TextUtils()` từ mã ngoài `TextUtils` bị từ chối bởi access `private`.

Constructor private **không** làm lớp tự động thành bất biến hay singleton; đó là quyết định thiết kế khác.

## 10. Constructor có thể dùng `throws` và kiểm tra dữ liệu

Constructor có thể ném ngoại lệ nếu không thể tạo đối tượng hợp lệ:

```java
class Temperature {
    private final double celsius;

    Temperature(double celsius) {
        if (Double.isNaN(celsius)) {
            throw new IllegalArgumentException("Temperature is NaN");
        }
        this.celsius = celsius;
    }

    double getCelsius() {
        return celsius;
    }
}
```

Nếu constructor ném ngoại lệ trước khi hoàn tất, biểu thức tạo đối tượng **không hoàn tất bình thường** và bên gọi không nhận kết quả từ `new` như trường hợp thành công. Với một constructor dùng **checked exception**, người viết phải khai báo/tuân thủ quy tắc xử lý ngoại lệ.

Ví dụ cú pháp `throws`:

```java
class Config {
    Config(String file) throws java.io.IOException {
        if (file == null) {
            throw new java.io.IOException("File path is null");
        }
    }
}
```

Đoạn minh họa này kiểm tra đường dẫn `null` chứ không thực hiện thao tác đọc file. Vì constructor khai báo checked exception `IOException`, nơi gọi `new Config(...)` phải xử lý `try/catch` hoặc truyền tiếp theo quy tắc Java.

Constructor cũng có thể gọi các method phục vụ kiểm tra, nhưng cần cân nhắc việc để `this` “thoát” ra bên ngoài trước khi đối tượng khởi tạo đầy đủ, ví dụ đăng ký đối tượng vào một callback hoặc luồng khác ngay trong constructor. Điều đó có thể làm bên ngoài quan sát trạng thái chưa hoàn thiện.

## 11. `return` trong constructor: được gì và không được gì?

Constructor **không khai báo kiểu trả về** nhưng có thể dùng **`return;` không kèm biểu thức** để kết thúc thân constructor sớm khi hợp lệ.

Ví dụ:

```java
class Flag {
    boolean enabled;

    Flag(boolean enabled) {
        this.enabled = enabled;
        if (!enabled) {
            return;             // Hợp lệ: kết thúc thân constructor
        }
        System.out.println("Enabled");
    }
}
```

`new Flag(false)` vẫn tạo được một đối tượng `Flag` có `enabled == false`; `return;` không “trả về false”, không hủy đối tượng, và không thay đổi bản chất constructor. Đây chỉ là câu lệnh kết thúc sớm.

**Không** được dùng `return expression;` trong constructor:

```java
class InvalidReturn {
    InvalidReturn() {
        // return this;  // SAI: constructor không thể return một giá trị
        // return 1;     // SAI
    }
}
```

Nếu cần **trả về một đối tượng theo logic lựa chọn**, dùng static factory method có kiểu trả về:

```java
class Result {
    private Result() {
    }

    static Result create() {
        return new Result(); // Method trả về Result; constructor vẫn không có return type
    }
}
```

**Đối với các blank final fields**, Java còn kiểm tra quy tắc *definite assignment*: mọi đường constructor có thể hoàn tất bình thường phải gán các blank final instance fields hợp lệ. Không thể đặt `return;` ở nhánh khiến final field bắt buộc chưa được khởi tạo.

## 12. Những modifier không áp dụng cho constructor

Access modifier hợp lệ không có nghĩa có thể đặt bất kỳ modifier nào trước constructor.

| Từ khóa / dạng | Constructor thông thường | Vì sao |
| --- | --- | --- |
| `public`/`protected`/`private` hoặc không ghi | **Hợp lệ** tùy ngữ cảnh | Điều chỉnh khả năng truy cập |
| `static` | **Không hợp lệ** | Constructor gắn với tạo thể hiện, không là static method |
| `final` | **Không hợp lệ** | Constructor không thể override, nên không có khái niệm final constructor |
| `abstract` | **Không hợp lệ** | Constructor phải có thân; không phải abstract method |
| `synchronized` | **Không hợp lệ** | Không khai báo synchronized constructor |
| `native` | **Không hợp lệ** | Constructor có cú pháp và thân riêng, không là native method |
| `void` hoặc bất kỳ kiểu trả về | **Không còn là constructor** | Nếu tên trùng lớp và có kiểu trả về, đó là method; thiếu các phần hợp lệ sẽ lỗi |
| `throws SomeException` | **Hợp lệ** | Constructor có thể khai báo exception |
| `<T>` trước tên constructor | **Có thể hợp lệ** | Constructor có thể khai báo type parameter |

Các khai báo **sai**:

```java
class BadConstructors {
    // static BadConstructors() { }       // SAI: constructor không static
    // final BadConstructors() { }        // SAI: constructor không final
    // abstract BadConstructors();        // SAI: constructor không abstract
    // synchronized BadConstructors() { } // SAI: constructor không synchronized
}
```

Không thể giải quyết bằng cách đổi thứ tự các modifier: `static BadConstructors()` hay `BadConstructors()` không phải hai kiểu constructor khác nhau. Hãy bỏ modifier sai hoặc chuyển hành vi thành **method** nếu nhu cầu thực sự là tạo một thành viên static/final/abstract.

### 12.1. Generic constructor là hợp lệ

Constructor có thể khai báo tham số kiểu generic **riêng**, ngay cả khi lớp không phải generic:

```java
class Holder {
    final String value;

    <T> Holder(T input) {
        this.value = String.valueOf(input);
    }
}
```

Với `new Holder(123)`, constructor `<T> Holder(T input)` nhận giá trị `Integer` sau boxing; field `value` nhận chuỗi `"123"`. `<T>` là type parameter của constructor, **không phải kiểu trả về**.

Phần generic constructor cần phân biệt với cú pháp `public <T> T create(T value)`: có kiểu trả về `T` nên đó là **generic method**, không phải constructor.

## 13. Constructor trong kế thừa: không được kế thừa và override

Lớp con **không kế thừa** constructor của lớp cha, mặc dù constructor lớp con có thể gọi constructor cha.

```java
class Parent {
    Parent(int value) {
        System.out.println("Parent: " + value);
    }
}

class Child extends Parent {
    Child(int value) {
        super(value);
        System.out.println("Child: " + value);
    }
}
```

`Child(int)` **không phải** override của `Parent(int)`. Đây là **hai constructor khác nhau**, mỗi constructor mang tên chính lớp chứa nó và có vai trò trong chuỗi khởi tạo.

Nếu `Child` không khai báo constructor nhưng `Parent` chỉ có `Parent(int)`, constructor mặc định của `Child` sẽ cố dùng `super()` và gây **lỗi biên dịch** vì `Parent()` không tồn tại.

Constructor cũng không được gọi bằng cú pháp method thông thường:

```java
Child child = new Child(5);
// child.Child(5); // SAI: constructor không phải instance method để gọi lại
```

Nếu cần “đặt lại trạng thái” của đối tượng sau khi tạo, hãy thiết kế method riêng như `reset(...)` hoặc tạo đối tượng mới, thay vì cố gọi lại constructor.

**Quy tắc kế thừa và constructor được chọn tại compile time:** `new Child(5)` là biểu thức yêu cầu constructor của `Child` phù hợp. Bên trong constructor đó có thể có `super(5)`, được chọn theo các quy tắc gọi constructor cha. Đây không phải dynamic dispatch tới một constructor “override” ở runtime.

## 14. Trường hợp dễ nhầm: abstract class, enum và record

### 14.1. Abstract class vẫn có constructor

Không thể `new` trực tiếp một abstract class, nhưng constructor của nó **vẫn tồn tại** để khởi tạo phần trạng thái thuộc abstract superclass khi tạo thể hiện lớp con.

```java
abstract class Shape {
    final String color;

    Shape(String color) {
        this.color = color;
    }

    abstract double area();
}

class Square extends Shape {
    final double side;

    Square(String color, double side) {
        super(color);
        this.side = side;
    }

    @Override
    double area() {
        return side * side;
    }
}
```

`new Square("red", 3)` hợp lệ; `new Shape("red")` không hợp lệ vì `Shape` là abstract. Constructor `Shape(String)` được gọi qua `super(color)` trong constructor `Square`.

### 14.2. Enum có constructor nhưng không được `new` từ bên ngoài

Một enum có thể có constructor để khởi tạo dữ liệu của các hằng enum:

```java
enum Level {
    LOW(1),
    HIGH(2);

    private final int priority;

    Level(int priority) {
        this.priority = priority;
    }

    int priority() {
        return priority;
    }
}
```

Các hằng `LOW` và `HIGH` làm phát sinh các thể hiện enum theo quy tắc của Java. Không được viết `new Level(1)` trong mã ứng dụng để tạo hằng enum mới. Constructor của enum có các hạn chế riêng, chẳng hạn không được khai báo `public` hoặc `protected`.

### 14.3. Record có canonical constructor và compact constructor

Java 17 hỗ trợ `record` với cú pháp constructor đặc thù:

```java
record Point(int x, int y) {
    Point {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException("Tọa độ âm");
        }
    }
}
```

`Point { ... }` là **compact canonical constructor** của record `Point`: đây là dạng cú pháp đặc biệt được Java cho phép với record, không phải method thiếu kiểu trả về. Các tham số tương ứng với record components được cung cấp theo quy tắc ngôn ngữ và Java thực hiện các phép gán cần thiết cho fields sau phần thân compact constructor.

Với một lớp thông thường, không thể thay thế khai báo constructor `Point(int x, int y)` bằng cú pháp `Point { ... }` như trên. Khi học constructor, hãy phân biệt **class thường** và các **loại kiểu đặc biệt** như enum, record.

## 15. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `void Person()` không chạy khi `new Person()` | Đây là method tên `Person`, không phải constructor | Bỏ `void` nếu mục tiêu là khởi tạo |
| `employee()` không được coi là constructor `Employee` | Sai chữ hoa/chữ thường so với tên lớp | Đặt tên `Employee()` |
| `new Account()` báo không tồn tại constructor | Lớp chỉ khai báo `Account(int)`; default no-arg constructor không tự sinh | Viết `Account()` tường minh hoặc gọi `new Account(value)` |
| Constructor lớp con báo lỗi `super()` | Lớp cha không có no-arg constructor truy cập được | Gọi `super(arguments)` phù hợp ở câu lệnh đầu tiên |
| `this(...)` đặt sau lệnh in | Java 17 yêu cầu explicit constructor invocation đứng đầu thân | Đưa `this(...)` lên đầu hoặc cấu trúc lại |
| `this(...)` và `super(...)` cùng xuất hiện trong một constructor | Hai invocation cạnh tranh cùng vị trí | Dùng `this(...)` chuyển qua constructor cuối cùng gọi `super(...)` |
| Compiler báo recursive constructor invocation | Các constructor gọi vòng qua `this(...)` | Phá vòng; tạo chuỗi kết thúc hợp lệ |
| `new Child(5)` không gọi được constructor `Parent(int)` một cách tự động | Constructor cha không được kế thừa | Khai báo constructor `Child(int)` có `super(5)` |
| `static User()` hoặc `final User()` không hợp lệ | Constructor không nhận các modifier đó | Bỏ modifier hoặc viết method theo mục đích |
| `return new User();` bên trong constructor | Constructor không trả giá trị | Dùng static factory method trả về `User` |
| `private User()` khiến bên ngoài không thể `new User()` | Quyền truy cập constructor bị giới hạn | Đưa ra public factory hoặc constructor với mức truy cập phù hợp |
| Gán blank final field thiếu trên một nhánh | Quy tắc definite assignment | Đảm bảo field final được gán hợp lệ trên mọi đường constructor hoàn tất bình thường |
| Gọi overridable method từ constructor tạo kết quả lạ | Lớp con chưa khởi tạo toàn bộ trạng thái khi superclass constructor chạy | Tránh dynamic dispatch vào hành vi phụ thuộc trạng thái chưa hoàn chỉnh |
| Tên tệp không khớp public class chứa constructor | Ràng buộc tên tệp của public top-level class | Đặt đúng tên `ClassName.java`, không dựa trên tên method |

Thông báo `javac` có thể thay đổi theo JDK. Khi xử lý lỗi, hãy kiểm tra **tên lớp**, **có/không có kiểu trả về**, **danh sách tham số**, **quyền truy cập**, **constructor cha** và **vị trí `this(...)`/`super(...)`**.

## 16. Bài tự luyện có đáp án

### Câu 1. Đâu là constructor, đâu là method?

```java
class Sample {
    Sample() { }
    void Sample(int value) { }
    int getValue() { return 1; }
}
```

**Đáp án:** `Sample()` là constructor. `void Sample(int value)` là **method `void` có tên trùng lớp**, không phải constructor. `getValue()` là method trả về `int`. Vì đã có constructor `Sample()` tường minh, Java không tự sinh constructor mặc định nữa.

### Câu 2. Phần nào chạy khi tạo đối tượng?

```java
class Greeter {
    Greeter() {
        System.out.println("constructor");
    }

    void greet() {
        System.out.println("method");
    }
}
```

Với:

```java
Greeter item = new Greeter();
item.greet();
```

**Stdout:**

```text
constructor
method
```

Constructor chạy trong quá trình `new Greeter()`. Phương thức `greet()` chạy vì được gọi tường minh ở dòng tiếp theo.

### Câu 3. Có default constructor không?

```java
class Size {
    Size(int value) {
    }
}
```

**Đáp án:** **Không**. Một constructor tường minh đã tồn tại nên `new Size()` không hợp lệ. Muốn hỗ trợ, hãy thêm `Size() { this(0); }` hoặc gọi `new Size(0)`.

### Câu 4. Constructor có thể trả một đối tượng khác không?

**Đáp án:** Không thể viết `return other;` trong constructor của lớp thông thường. Nếu mục tiêu là chọn và trả về một thể hiện đã tồn tại, tạo một **static factory method** trả về kiểu lớp đó. Biểu thức `new Type(...)` cung cấp tham chiếu tới đối tượng được tạo, nhưng constructor không có return type.

### Câu 5. Dòng nào là constructor chaining hợp lệ?

```java
class Base {
    Base(int code) {
    }
}

class Derived extends Base {
    Derived() {
        this(1);
    }

    Derived(int code) {
        super(code);
    }
}
```

**Đáp án:** Hợp lệ với Java 17. `new Derived()` đi từ `Derived()` tới `Derived(int)` qua `this(1)`, rồi đến `Base(int)` qua `super(code)`. Không có chu trình và mỗi lời gọi constructor tường minh đứng đầu thân.

### Câu 6. Sửa lỗi khởi tạo field `final`

```java
class Task {
    final String id;

    Task(boolean enabled) {
        if (enabled) {
            id = "ACTIVE";
        }
    }
}
```

**Đáp án:** Lỗi vì nếu `enabled == false` thì blank final field `id` có thể chưa được gán khi constructor hoàn tất bình thường. Một cách sửa:

```java
class Task {
    final String id;

    Task(boolean enabled) {
        id = enabled ? "ACTIVE" : "INACTIVE";
    }
}
```

Lưu ý đây là **hai phiên bản thay thế** của lớp `Task`, không đặt cả hai cùng lúc trong một package khi biên dịch.

### Câu 7. Đọc đúng ý nghĩa của `new`

```java
class Box {
    Box() {
    }

    static Box make() {
        return new Box();
    }
}
```

**Đáp án:** `Box()` là constructor, không trả về giá trị theo cú pháp Java. `make()` là **static method** có kiểu trả về `Box`; lệnh `return new Box();` trả cho nơi gọi tham chiếu nhận được từ biểu thức `new Box()`. Không phải “constructor trả về Box”.

## 17. Checklist khi khai báo constructor Java

1. **Tên có trùng chính xác tên lớp** không? Java phân biệt hoa/thường.
2. **Có vô tình ghi `void` hoặc kiểu trả về** không? Nếu có, đó không phải constructor.
3. **Constructor nhận tham số nào**? Có cần nhiều overload hoặc một no-arg constructor không?
4. **Nếu lớp không viết constructor nào**, default constructor có thể được compiler cung cấp; **nếu đã viết một constructor**, cần tự thêm những overload khác nếu muốn.
5. **Constructor có được gọi từ phạm vi dự kiến** không? Kiểm tra `public`, `protected`, package-private hoặc `private`.
6. **Nếu lớp có cha**, superclass constructor nào cần gọi? Có no-arg `super()` truy cập được không?
7. **Java 17:** lời gọi `this(...)` hoặc `super(...)` tường minh phải đứng **đầu thân constructor** và không được tạo chu trình.
8. **Các field `final`** đã được gán hợp lệ trên mọi đường khởi tạo kết thúc bình thường chưa?
9. **Có lỗi khi kiểm tra dữ liệu**? Constructor có thể ném ngoại lệ để ngăn quá trình tạo đối tượng hoàn tất bình thường.
10. **Không dùng modifier của method cho constructor** như `static`, `abstract`, `final`, `synchronized`.
11. **Không gọi lại constructor qua dấu chấm** như `object.ClassName()`; nếu cần tái thiết lập trạng thái, tạo một method khác.
12. **Không nhầm constructor chaining với override**: constructor của cha không được kế thừa, còn việc gọi `super(...)` phục vụ khởi tạo phần superclass.

## Ghi nhớ

- Constructor là thành phần khởi tạo đối tượng: **`ClassName(parameters) { ... }`**, với **tên trùng lớp** và **không có kiểu trả về**.
- Phương thức luôn khai báo kiểu trả về hoặc `void`; **`void ClassName()` vẫn là method**, không phải constructor.
- `new Type(...)` tạo/khởi tạo đối tượng và cho ra tham chiếu nếu thành công; **không phải** constructor có kiểu trả về `Type`.
- Constructor được **nạp chồng**, nhưng **không kế thừa hoặc override**.
- Default no-arg constructor chỉ được compiler cung cấp khi **không có constructor tường minh nào**; no-arg constructor do người viết khai báo là khái niệm khác.
- Trong **Java 17**, `this(...)` và `super(...)` tường minh phải ở đầu thân constructor; chuỗi gọi giúp khởi tạo cùng một đối tượng theo các quy tắc superclass.
- Constructor có thể khai báo access modifier, tham số, `throws`, kiểm tra dữ liệu và cập nhật field; không dùng `static`, `final` hay `abstract` làm constructor modifier.
