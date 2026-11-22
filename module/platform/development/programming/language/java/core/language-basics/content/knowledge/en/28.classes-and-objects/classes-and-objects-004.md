# Hàm khởi tạo thiết lập giá trị ban đầu trong Java

## 1. Constructor là gì?

**Hàm khởi tạo** (*constructor*) là cơ chế khởi tạo đối tượng khi dùng biểu thức `new`. Constructor có **cùng tên với lớp**, **không khai báo kiểu trả về** (kể cả `void`) và được dùng để thiết lập trạng thái ban đầu hợp lệ cho mỗi instance.

```java
class Student {
    String name;
    int age;

    Student(String name, int age) {
        this.name = name;
        this.age = age;
    }
}

// Đặt trong phương thức:
// Student s = new Student("Lan", 18);
// s.name == "Lan" và s.age == 18
```

Biểu thức `new Student("Lan", 18)` tạo một đối tượng `Student` rồi thực thi quá trình khởi tạo, trong đó có constructor được chọn theo danh sách đối số. `this.name` và `this.age` là các **trường của đối tượng hiện tại**; `name` và `age` không có `this` trong constructor là **tham số**. Nếu viết `name = name;`, đó chỉ là tự gán tham số, không lưu giá trị vào trường.

Constructor chủ yếu để thiết lập **bất biến của đối tượng** (*invariant*): những điều kiện cần đúng ngay sau khi tạo, ví dụ tên không rỗng, tuổi không âm. Tùy yêu cầu, không phải trường nào cũng bắt buộc đặt qua constructor; trường có thể có giá trị mặc định hoặc giá trị khởi tạo tại khai báo.

## 2. Giá trị mặc định và khởi tạo trường

Ngay khi bộ nhớ đối tượng được cấp phát, các **trường instance** có giá trị mặc định của kiểu, trước khi các bộ khởi tạo trường và thân constructor thực hiện những phép gán có liên quan.

| Kiểu trường | Giá trị mặc định trước khi được gán rõ ràng |
| --- | --- |
| `byte`, `short`, `int`, `long` | `0` tương ứng với kiểu |
| `float`, `double` | `0.0` tương ứng với kiểu |
| `char` | `'\u0000'` |
| `boolean` | `false` |
| Mọi kiểu tham chiếu, kể cả `String`, mảng và đối tượng | `null` |

```java
class Settings {
    int retries;               // Ban đầu 0
    boolean enabled;           // Ban đầu false
    String mode = "standard";   // Field initializer: đặt giá trị rõ ràng

    Settings(int retries) {
        this.retries = retries;
        this.enabled = true;
    }
}
```

Sau khi `new Settings(3)` hoàn tất, đối tượng có `retries == 3`, `enabled == true`, `mode.equals("standard")`.

**Khác biệt với biến cục bộ:** Java không cho phép đọc một biến cục bộ nếu nó chưa được **definitely assigned** (chắc chắn đã được gán) trước điểm sử dụng; biến cục bộ không tự có giá trị mặc định để đọc như trường đối tượng.

```java
void example() {
    int count;
    // System.out.println(count); // LỖI biên dịch: count chưa được gán
    count = 2;
    System.out.println(count); // Hợp lệ
}
```

Đoạn `example()` là một phương thức minh họa cần được đặt trong lớp.

## 3. Cú pháp và điểm khác phương thức thông thường

```java
class Rectangle {
    private final int width;
    private final int height;

    public Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    public int area() {
        return width * height;
    }
}
```

- `Rectangle(...)` là **constructor**, không có kiểu trả về.
- `area()` là **phương thức** có kiểu trả về `int`; phương thức có thể được gọi trên đối tượng nhiều lần.
- Constructor chạy trong quá trình tạo instance. Gọi lại constructor như phương thức thông thường, ví dụ `object.Rectangle(2, 3)`, **không hợp lệ**.
- Constructor có thể có các mức truy cập `public`, `protected`, package-private (không ghi modifier) hoặc `private`. Quyền truy cập quyết định mã bên ngoài có được phép dùng `new` với constructor đó hay không.
- Constructor **không được kế thừa** và không bị override. Constructor không khai báo `static`, `abstract` hay `final`.
- `return;` có thể dùng để kết thúc sớm constructor trong một số trường hợp, nhưng constructor **không được trả về giá trị** bằng `return expression;`. Trong thiết kế tốt, nên đảm bảo kiểm tra đầu vào và khởi tạo đầy đủ trước khi hoàn tất bình thường.

Tên constructor phải đúng tên lớp, phân biệt hoa thường. Nếu viết `void Rectangle(...)`, đó là **phương thức tên `Rectangle`**, không phải constructor, và trình biên dịch không xem đó là constructor được khai báo.

## 4. Constructor mặc định, không tham số và có tham số

Cần phân biệt **constructor mặc định do trình biên dịch tự sinh** với **constructor không tham số do lập trình viên viết**:

```java
class Empty {
    // Không khai báo constructor nào.
    // Trình biên dịch cung cấp default constructor không tham số.
}

class Custom {
    Custom() {
        System.out.println("Custom()");
    }
}
```

Khi một lớp **không khai báo constructor nào**, trình biên dịch cấp một constructor mặc định không tham số. Constructor này gọi constructor lớp cha theo quy tắc ngôn ngữ và không tự suy ra các giá trị đầu vào đặc biệt. Mức truy cập của constructor mặc định phụ thuộc mức truy cập của lớp theo quy tắc Java; không nên mặc định cho rằng constructor tự sinh lúc nào cũng là `public`.

Nếu đã khai báo **bất kỳ constructor nào**, trình biên dịch **không còn tự thêm constructor mặc định không tham số**:

```java
class User {
    String name;

    User(String name) {
        this.name = name;
    }
}

// new User("Mai"); // Hợp lệ
// new User();      // LỖI biên dịch: không có constructor User()
```

Muốn cả hai cách tạo đối tượng, phải tự khai báo overload không tham số. Nếu không khai báo constructor trong lớp con, trình biên dịch sẽ sinh constructor mặc định cố gọi `super()`; nếu lớp cha không có constructor không tham số truy cập được, việc biên dịch thất bại. Khi đó lớp con cần tự khai báo constructor và gọi đúng `super(arguments)`.

## 5. Nạp chồng constructor và `this(...)`

**Nạp chồng** (*overloading*) cho phép nhiều constructor có danh sách tham số khác nhau; sử dụng để cung cấp cách tạo đối tượng linh hoạt nhưng vẫn giữ chung quy tắc khởi tạo.

```java
class Ticket {
    private final String title;
    private final int quantity;

    Ticket(String title) {
        this(title, 1); // Ủy quyền cho constructor khác cùng lớp
    }

    Ticket(String title, int quantity) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        this.title = title;
        this.quantity = quantity;
    }
}
```

Ở **Java 17**, lời gọi constructor khác `this(...)` hoặc lời gọi constructor lớp cha `super(...)`, nếu có, phải là **câu lệnh đầu tiên** của thân constructor. Vì vậy:

- `this(title, 1);` chuyển sang constructor cùng lớp nhận hai đối số.
- Constructor được ủy quyền thực hiện kiểm tra và gán trạng thái, tránh lặp logic ở nhiều nơi.
- Không thể gọi cả `this(...)` và `super(...)` trong cùng thân constructor: mỗi đường khởi tạo cuối cùng phải dẫn tới việc khởi tạo lớp cha đúng một lần.
- Không tạo vòng lặp `this()` lẫn nhau; trình biên dịch từ chối lời gọi constructor đệ quy.
- `this(...)` gọi constructor; `this.field` truy cập trường instance: hai dạng `this` có tác dụng khác nhau.
- Nếu bỏ cả `this(...)` và `super(...)`, trình biên dịch ngầm gọi `super()` khi hợp lệ.

Lưu ý ranh giới phiên bản: một số phiên bản Java mới hơn thay đổi chi tiết cho phép câu lệnh trước lời gọi constructor tường minh; ví dụ bài này giữ quy tắc **Java 17** và tương thích với `javac` 17.

## 6. Lớp cha được khởi tạo trước thân constructor lớp con

Java thực hiện chuỗi khởi tạo đối tượng theo quy tắc. Với các lớp thông thường trong ví dụ:

1. Các trường được đặt giá trị mặc định khi đối tượng được cấp phát.
2. Các constructor cha được gọi theo chuỗi kế thừa cho tới `Object`.
3. Trên đường hoàn tất các lớp trong chuỗi, các **field initializer** và **instance initializer block** của mỗi lớp chạy theo thứ tự xuất hiện trong lớp ấy trước phần thân constructor tương ứng (với constructor ủy quyền qua `this(...)`, các bộ khởi tạo instance của lớp chỉ chạy một lần).
4. Phần thân constructor của lớp cha hoàn tất trước phần thân constructor của lớp con.

Ví dụ độc lập của ý tưởng này khi đặt vào lớp:

```java
class Parent {
    Parent() {
        System.out.println("Parent constructor");
    }
}

class Child extends Parent {
    private int id = 7;

    Child() {
        super(); // Ngầm định nếu bỏ, khi Parent() truy cập được
        System.out.println("Child constructor: " + id);
    }
}
```

Tạo `new Child()` sẽ in `Parent constructor` trước `Child constructor: 7`. Không nên gọi phương thức instance có thể bị override từ constructor của lớp cha: khi override chạy trong lớp con, các trường của lớp con có thể chưa hoàn tất quá trình khởi tạo của nó.

## 7. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`ConstructorDemo.java`**:

```java
public class ConstructorDemo {
    static class Order {
        private final String item;
        private final int quantity;

        Order(String item) {
            this(item, 1); // Constructor overload
        }

        Order(String item, int quantity) {
            if (item == null || item.isBlank()) {
                throw new IllegalArgumentException("Invalid item");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Invalid quantity");
            }
            this.item = item;
            this.quantity = quantity;
        }

        void print() {
            System.out.println(item + ": " + quantity);
        }
    }

    static class Defaults {
        int count;
        String description;

        Defaults() {
            System.out.println("Before: " + count + ", " + description);
            count = 5;
            description = "ready";
        }

        void print() {
            System.out.println("After: " + count + ", " + description);
        }
    }

    static class Parent {
        Parent() {
            System.out.println("Parent()");
        }
    }

    static class Child extends Parent {
        private final int id = 42;

        Child() {
            super();
            System.out.println("Child(): " + id);
        }
    }

    public static void main(String[] args) {
        Order first = new Order("Pen");
        Order second = new Order("Book", 3);
        first.print();
        second.print();

        try {
            new Order("Paper", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        Defaults defaults = new Defaults();
        defaults.print();

        new Child();
    }
}
```

Mở terminal tại thư mục chứa tệp, sử dụng **JDK 17 trở lên** trên Windows PowerShell/CMD hoặc Linux/macOS:

```bash
javac -encoding UTF-8 ConstructorDemo.java
java ConstructorDemo
```

Kết quả **stdout chính xác** (lệnh biên dịch thành công không in gì):

```text
Pen: 1
Book: 3
Rejected: Invalid quantity
Before: 0, null
After: 5, ready
Parent()
Child(): 42
```

Giải thích kết quả:

- `new Order("Pen")` gọi constructor một tham số và ủy quyền qua `this(item, 1)`; `quantity` được khởi tạo thành `1`.
- `new Order("Book", 3)` dùng overload hai tham số và khởi tạo đủ hai trường `final`.
- Constructor từ chối `quantity == 0` bằng `IllegalArgumentException`; không có đối tượng `Order` được trả về cho lời gọi `new` thất bại.
- Trong `Defaults()`, hai trường chưa được gán tường minh có giá trị mặc định `0` và `null`; sau phép gán trong constructor, chúng thành `5` và `"ready"`.
- Với `new Child()`, constructor lớp cha in trước, rồi constructor lớp con đọc field `id` đã được khởi tạo thành `42`.

## 8. Khởi tạo `final`, validation và tham chiếu mutable

### Trường `final` khởi tạo một lần

Một **trường instance `final` chưa được khởi tạo tại khai báo** (*blank final field*) phải được gán chính xác theo các quy tắc *definite assignment* trước khi constructor hoàn tất bình thường:

```java
class Point {
    final int x;
    final int y;

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }
}
```

Nếu một nhánh constructor hoàn tất bình thường mà bỏ qua việc gán `x` hoặc `y`, mã không biên dịch được. Nếu field `final` đã được gán tại khai báo, không thể gán lại trường đó trong constructor.

Từ khóa `final` trên một **tham chiếu** ngăn gán lại tham chiếu sau khởi tạo, nhưng không tự biến trạng thái của đối tượng được tham chiếu thành bất biến:

```java
class Holder {
    private final int[] values;

    Holder(int[] input) {
        this.values = input.clone();
    }
}
```

`input.clone()` giúp không dùng chung mảng `int[]` ban đầu khi tạo đối tượng. Nếu getter trả thẳng `values`, mã bên ngoài vẫn có thể sửa phần tử; khi cần bất biến thực tế, phải kiểm soát cả cách công khai và cập nhật trạng thái.

### Kiểm tra dữ liệu ngay lúc tạo

Constructor là nơi phù hợp để từ chối đối số không hợp lệ, ví dụ `name == null`, chuỗi trống hoặc số lượng âm. Cần chọn rõ điều kiện miền dữ liệu; `quantity <= 0` hợp lý cho đơn hàng yêu cầu ít nhất một đơn vị, nhưng không phù hợp với mọi bài toán (ví dụ một bộ đếm hợp lệ có thể bằng 0).

Đừng để lộ `this` trong lúc constructor chưa hoàn tất (ví dụ đăng ký đối tượng vào cấu trúc công khai hoặc khởi chạy luồng dùng `this` quá sớm): mã khác có thể quan sát trạng thái chưa được khởi tạo xong.

## 9. Lỗi phổ biến và cách kiểm tra

| Lỗi | Hậu quả/cách sửa |
| --- | --- |
| Viết `name = name;` khi tham số trùng tên trường | Tham số tự gán cho chính nó; dùng `this.name = name;` |
| Thêm `void` trước tên constructor | Biến thành một phương thức thông thường, không còn là constructor |
| Gọi `new User()` sau khi chỉ khai báo `User(String name)` | Không có constructor không tham số tự sinh; viết overload `User()` nếu cần |
| Dùng `this(...)` sau câu lệnh khác ở Java 17 | Lỗi biên dịch: lời gọi constructor tường minh phải đứng đầu |
| Một constructor chỉ gán vài trường `final` rồi kết thúc | Lỗi *definite assignment*; mọi đường kết thúc bình thường phải gán đủ |
| Tưởng field và biến local đều có giá trị mặc định để đọc | Field có giá trị mặc định; local phải được gán chắc chắn trước khi đọc |
| Gọi phương thức có thể bị override từ constructor cha | Có thể chạy logic của lớp con trước khi trạng thái lớp con khởi tạo xong |
| Lưu trực tiếp mảng mutable được truyền vào rồi coi đối tượng là bất biến | Dữ liệu có thể bị sửa từ ngoài qua cùng tham chiếu; cân nhắc sao chép bảo vệ |

**Ghi nhớ:** constructor định nghĩa cách tạo một instance ở trạng thái ban đầu hợp lệ. Dùng `this.field` để gán đúng field, dùng `this(...)` để chia sẻ logic giữa các constructor, dùng `super(...)` khi cần khởi tạo lớp cha, và kiểm tra đối số trước khi công khai đối tượng.