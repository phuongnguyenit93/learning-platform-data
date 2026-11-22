# Toàn cảnh trường, phương thức, hàm khởi tạo và thành viên static trong Java

Trong Java, một **class** mô tả kiểu đối tượng: dữ liệu được giữ ở đâu, hành vi được thực hiện ra sao và đối tượng được tạo hợp lệ bằng cách nào. Bốn thành phần cần phân biệt là **field (trường)**, **method (phương thức)**, **constructor (hàm khởi tạo)** và thành viên **static (thuộc lớp)**. Bài này áp dụng cho Java 17+ và tập trung vào cách đọc, viết, sử dụng chúng cùng nhau.

## 1. Nhìn một class như một bản thiết kế

~~~java
class BankAccount {
    private String owner;                    // field của từng đối tượng
    private long balance;                    // field của từng đối tượng
    private static int accountCount;         // field dùng chung ở cấp lớp

    BankAccount(String owner) {               // constructor
        this.owner = owner;
        accountCount++;
    }

    void deposit(long amount) {               // instance method
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        balance += amount;
    }

    long getBalance() {                       // instance method
        return balance;
    }

    static int getAccountCount() {            // static method
        return accountCount;
    }
}
~~~

Đây là **đoạn minh họa khai báo lớp**, chưa phải chương trình có phương thức `main` để chạy riêng. Nó cho thấy:

| Thành phần | Mục đích | Thuộc về | Cách sử dụng điển hình |
| --- | --- | --- | --- |
| Instance field (`owner`, `balance`) | Giữ trạng thái riêng | Mỗi đối tượng `BankAccount` | Truy cập qua phương thức của đối tượng |
| Instance method (`deposit`, `getBalance`) | Thao tác trên trạng thái và hành vi đối tượng | Đối tượng đang nhận lời gọi | `account.deposit(100)` |
| Constructor (`BankAccount(...)`) | Khởi tạo đối tượng mới | Quá trình tạo đối tượng | `new BankAccount("An")` |
| Static field (`accountCount`) | Giữ trạng thái chung của lớp | Lớp, trong một lần nạp lớp tương ứng | `BankAccount.getAccountCount()` |
| Static method (`getAccountCount`) | Cung cấp hành vi không phụ thuộc `this` | Lớp | `BankAccount.getAccountCount()` |

Ví dụ, hai tài khoản có `owner` và `balance` riêng nhưng đều quan sát cùng biến `accountCount`. **Biến tham số và biến cục bộ không phải field**: chúng tồn tại trong ngữ cảnh lời gọi phương thức hoặc constructor, không lưu thành trạng thái của đối tượng.

## 2. Field: trạng thái được lưu ở đâu?

**Field** là biến khai báo trực tiếp trong thân class (hoặc interface). Với class, field có kiểu, tên, phạm vi truy cập và có thể có các modifier như `static`, `final`, `volatile`. Instance field gắn với từng đối tượng; static field gắn với class tương ứng.

### 2.1. Giá trị ban đầu và vị trí khai báo

Khi tạo đối tượng, các instance field trước hết có giá trị mặc định: kiểu số nhận `0` (hoặc `0.0`), `boolean` nhận `false`, `char` nhận ký tự null (`'\u0000'`), kiểu tham chiếu nhận `null`. Sau đó các khởi tạo field và initializer block của đối tượng được thực hiện theo thứ tự khai báo, trước phần thân constructor của chính class đó. Static field cũng nhận giá trị mặc định trước khi chạy các static initializer của class.

~~~java
class Profile {
    int age;                       // mặc định 0
    boolean active;                // mặc định false
    String name = "Chưa đặt";      // được gán khi khởi tạo đối tượng
}
~~~

Khác với field, **biến cục bộ không có giá trị mặc định để dùng trực tiếp**: trình biên dịch yêu cầu biến được gán trước khi đọc. Ví dụ `int x; System.out.println(x);` trong cùng một phương thức sẽ bị lỗi biên dịch.

### 2.2. Truy cập, che giấu tên và bất biến

Thông thường nên để field là `private`, kiểm soát thay đổi thông qua constructor hoặc method. Nếu tham số trùng tên field, sử dụng `this.field` để chỉ rõ field của đối tượng hiện tại:

~~~java
class Person {
    private final String name;

    Person(String name) {
        this.name = name; // bên trái là field; bên phải là tham số
    }

    String getName() {
        return name;
    }
}
~~~

`final` với instance field nghĩa là trường chỉ được **gán giá trị một lần theo đường khởi tạo hợp lệ**. Một `final` field kiểu tham chiếu ngăn gán lại tham chiếu, nhưng **không tự làm đối tượng được tham chiếu trở nên bất biến**. Ví dụ, `final List<String> names` vẫn có thể trỏ tới một `ArrayList` cho phép thêm phần tử; `names = otherList` mới là thao tác bị cấm sau lần gán đầu tiên.

Đừng làm lộ trạng thái nội bộ có thể thay đổi nếu cần bảo vệ invariant: getter trả thẳng một danh sách mutable, chẳng hạn, vẫn cho mã bên ngoài sửa dữ liệu. Cần cân nhắc defensive copy hoặc collection không cho sửa khi phù hợp.

### 2.3. Đọc và ghi field

Bên trong instance method có thể viết `balance` hoặc `this.balance`. Từ bên ngoài, chỉ truy cập field nếu quy tắc truy cập Java cho phép. `private` chỉ truy cập trong phạm vi class khai báo (kể cả các ngữ cảnh lồng nhau được Java cho phép), không phải “mọi class cùng package”. Một field có thể chứa tham chiếu `null`: truy cập `p.name` khi `p == null` gây `NullPointerException`.

## 3. Method: hành vi, đầu vào và giá trị trả về

Cấu trúc điển hình của method gồm modifier, kiểu trả về, tên, danh sách tham số, các khai báo `throws` nếu có, và thân phương thức. Instance method được gọi trên đối tượng; static method thường được gọi bằng tên class.

~~~java
class Calculator {
    int add(int a, int b) {
        return a + b;
    }

    double add(double a, double b) {
        return a + b;
    }

    static boolean isPositive(int value) {
        return value > 0;
    }
}
~~~

Đây là đoạn minh họa. Hai method `add` được **overload (nạp chồng)** vì khác danh sách kiểu tham số; chỉ đổi kiểu trả về thì **không đủ** để overload. Trong Java, chữ ký dùng để phân biệt overload dựa trên tên và các kiểu tham số (không dựa trên kiểu trả về); quá trình chọn overload diễn ra lúc biên dịch dựa trên kiểu biểu thức truyền vào và các quy tắc áp dụng phương thức.

**Instance method** có `this`, nên thường đọc và sửa field của chính đối tượng. **Static method** không có `this`; vì vậy nó không thể trực tiếp dùng `this` hoặc instance field/method mà không có một tham chiếu đối tượng rõ ràng.

~~~java
class Rectangle {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    int area() {
        return width * height;
    }

    static Rectangle square(int side) {
        return new Rectangle(side, side);
    }
}
~~~

Ở đây `area()` cần trạng thái của một hình chữ nhật cụ thể; `square(int)` là **static factory method**, tự tạo và trả một đối tượng. Phương thức factory **không phải constructor** dù có thể thay constructor làm API tạo đối tượng.

**Giá trị trả về:** method có kiểu khác `void` phải trả về một giá trị phù hợp trên mọi đường kết thúc thông thường; `void` không trả về giá trị. Java truyền đối số **theo giá trị**: với kiểu primitive, method nhận bản sao giá trị; với kiểu tham chiếu, method nhận bản sao của tham chiếu. Do đó có thể sửa nội dung đối tượng mà tham chiếu trỏ tới (nếu đối tượng cho phép), nhưng gán lại chính tham số không làm biến tham chiếu ở caller trỏ sang đối tượng mới.

**Overriding khác overloading:** subclass có thể override instance method đủ điều kiện để thay đổi hành vi khi dispatch động; `static` method không override theo cơ chế đó mà có thể *hide* phương thức static của superclass. Field cũng bị *hide*, không dispatch đa hình như instance method. Đây là phân biệt quan trọng khi nhìn tổng quan các thành viên của lớp.

## 4. Constructor: thiết lập trạng thái hợp lệ khi tạo đối tượng

Constructor có **tên trùng chính xác với tên class** và **không khai báo kiểu trả về**, kể cả `void`. Nó được gọi trong quá trình tạo đối tượng bằng `new`; không gọi như một instance method thông thường. Constructor có thể overload bằng danh sách tham số khác nhau, nhưng **không được kế thừa** như method.

~~~java
class Product {
    private final String code;
    private int stock;

    Product(String code) {
        this(code, 0);
    }

    Product(String code, int initialStock) {
        if (code == null || code.isBlank() || initialStock < 0) {
            throw new IllegalArgumentException("Dữ liệu sản phẩm không hợp lệ");
        }
        this.code = code;
        this.stock = initialStock;
    }
}
~~~

Đây là đoạn minh họa cho **constructor chaining**. `Product(String)` gọi `this(code, 0)` để gom quy tắc kiểm tra và gán giá trị vào một chỗ. Trong Java 17, lời gọi `this(...)` hoặc `super(...)` tường minh phải là câu lệnh đầu tiên trong constructor; không được gọi cả hai trong cùng một constructor. Không được tạo chu trình gọi constructor (ví dụ A gọi B rồi B gọi A).

Các quy tắc dễ nhầm:

- **Constructor mặc định do compiler sinh** chỉ xuất hiện nếu class **không khai báo bất kỳ constructor nào**. Khi đã khai báo `Product(String)`, `new Product()` sẽ không còn tự hợp lệ trừ khi bạn tự viết constructor không tham số.
- Nếu constructor không gọi `this(...)` hoặc `super(...)` tường minh, Java chèn lời gọi `super()` phù hợp; code chỉ biên dịch nếu superclass có constructor không tham số mà subclass được phép truy cập.
- Constructor có thể là `private` để điều khiển cách tạo đối tượng, như với factory method; superclass constructor phải được gọi đúng quy tắc.
- Constructor có thể ném exception để từ chối trạng thái đầu vào sai. Không đưa đối tượng chưa hoàn tất khởi tạo ra ngoài qua biến static, callback hay luồng khác.
- `final` instance field phải được gán theo mọi đường khởi tạo hoàn tất bình thường. Dùng constructor để giữ bất biến, ví dụ số lượng tồn kho không âm.

Nếu constructor gọi method có thể bị subclass override, method đó có thể chạy **trước khi field riêng của subclass được khởi tạo xong**. Đây là lỗi thiết kế thường gặp: tránh gọi instance method có thể override từ constructor nếu method phụ thuộc trạng thái subclass.

## 5. Thành viên static: dùng chung ở cấp lớp

`static` dành cho **class field** và **class method**; class cũng có static initializer block và static nested class. Không có `static` constructor. Không khai báo biến cục bộ `static` trong một method Java thông thường. Class cấp cao nhất không được khai báo `static`; từ khóa này áp dụng được cho nested class ở vị trí hợp lệ.

### 5.1. Static field

~~~java
class AppSettings {
    static final int MAX_RETRIES = 3;    // hằng số nguyên thủy
    private static int activeSessions;   // trạng thái dùng chung
}
~~~

Một `static final` field chỉ được gán một lần, nhưng nếu nó trỏ tới đối tượng mutable thì nội dung đối tượng vẫn có thể đổi. Với `static final` kiểu primitive hoặc `String` có initializer là **constant expression** đúng quy tắc Java, giá trị là *constant variable* và có thể được biên dịch nhúng vào nơi sử dụng. Đừng dựa vào việc chỉ **đọc** constant variable như vậy để kích hoạt static initializer của class khai báo.

Static field mutable cần được xem như **trạng thái chia sẻ**: hai object khác nhau, và nhiều thread, đều có thể đụng tới nó. Phép `count++` không atomic; nếu nhiều thread cập nhật đồng thời có thể mất cập nhật. Trong tình huống đa luồng, cần dùng giải pháp đồng bộ phù hợp (ví dụ `AtomicInteger`, synchronized hoặc thiết kế tránh trạng thái mutable dùng chung). `static` tự nó không làm mã thread-safe.

### 5.2. Static method

Static method hợp lý cho phép tính thuần, utility function và factory không cần `this`. Lời gọi rõ ràng nhất là `ClassName.method(...)`. Java cho phép một số cách gọi static method qua biểu thức đối tượng, nhưng nên tránh vì dễ gây hiểu nhầm rằng lời gọi được dispatch theo object.

~~~java
class UnitConverter {
    private UnitConverter() { } // lớp tiện ích không có mục đích tạo instance

    static double centimetersToMeters(double centimeters) {
        return centimeters / 100.0;
    }
}
~~~

Đoạn trên minh họa utility class. Một static method vẫn **có thể** đọc hoặc gọi instance member khi nhận được đối tượng phù hợp, ví dụ `person.getName()`; điều bị cấm là dùng instance member **không có đối tượng** trong static context.

### 5.3. Static initialization và thời điểm diễn ra

Static field initializer và static initializer block chạy theo **thứ tự xuất hiện trong mã nguồn**, trong giai đoạn khởi tạo class. Việc khởi tạo này thường xảy ra ngay trước “active use” đầu tiên, như tạo instance, gọi static method hoặc truy cập static field không phải compile-time constant; JVM có các quy tắc cụ thể cho class/interface initialization. Mỗi class được khởi tạo một lần cho mỗi thực thể class được JVM nạp bằng class loader tương ứng; đừng hiểu rằng nó luôn chỉ chạy đúng một lần trong toàn bộ mọi JVM/class loader.

~~~java
class Configuration {
    static String mode = "development";

    static {
        mode = mode.toUpperCase();
    }
}
~~~

Sau khi class được khởi tạo, `Configuration.mode` là `"DEVELOPMENT"`. Tránh khởi tạo tĩnh phức tạp, phụ thuộc vòng hoặc có tác dụng phụ khó kiểm soát. Nếu static initializer thất bại vì exception, việc sử dụng class có thể dẫn đến lỗi khởi tạo như `ExceptionInInitializerError`.

## 6. Trình tự khởi tạo: ví dụ Java 17 chạy được

Một đối tượng được cấp bộ nhớ, field nhận giá trị mặc định, chuỗi constructor superclass được thực hiện, rồi các instance field initializer và instance initializer block của từng class chạy theo đúng thứ tự quy định trước phần thân constructor tương ứng. Khi có constructor gọi `this(...)`, phần khởi tạo instance của cùng class chỉ diễn ra **một lần**, ở mắt xích thực hiện lời gọi superclass. Với ví dụ chỉ có lớp lồng `Counter` dưới đây, có thể quan sát trực tiếp thứ tự static initializer, instance initializer và constructor.

Lưu nội dung sau vào tệp **MemberOverview.java**:

~~~java
public class MemberOverview {
    static class Counter {
        private static int nextId = 1;

        static {
            System.out.println("Khởi tạo lớp Counter");
        }

        private final int id;
        private String name = "chưa đặt";

        {
            System.out.println("Khởi tạo đối tượng");
        }

        Counter() {
            this("Khách");
        }

        Counter(String name) {
            this.id = nextId++;
            this.name = name;
            System.out.println("Constructor: " + id);
        }

        void rename(String newName) {
            this.name = newName;
        }

        String label() {
            return "#" + id + " " + name;
        }

        static int createdCount() {
            return nextId - 1;
        }
    }

    public static void main(String[] args) {
        Counter first = new Counter();
        Counter second = new Counter("An");

        first.rename("Bình");

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println("Đã tạo: " + Counter.createdCount());
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp (có JDK 17 trở lên):

~~~bash
javac MemberOverview.java
java MemberOverview
~~~

Kết quả chuẩn:

~~~text
Khởi tạo lớp Counter
Khởi tạo đối tượng
Constructor: 1
Khởi tạo đối tượng
Constructor: 2
#1 Bình
#2 An
Đã tạo: 2
~~~

**Giải thích theo từng bước:**

1. Lần đầu tạo `new Counter()`, JVM khởi tạo class `Counter`: gán `nextId = 1` rồi chạy static block, nên in “Khởi tạo lớp Counter” **một lần**.
2. Đối tượng thứ nhất nhận giá trị mặc định rồi chạy field initializer `name = "chưa đặt"` và instance initializer block, in “Khởi tạo đối tượng”. Constructor không tham số chuyển sang `Counter("Khách")`, và constructor có tham số gán `id = 1`, tăng `nextId` lên 2 rồi in “Constructor: 1”.
3. Tạo đối tượng thứ hai không chạy lại static block. Instance initializer chạy cho đối tượng thứ hai, constructor gán `id = 2`, tăng `nextId` lên 3 rồi in “Constructor: 2”.
4. `first.rename("Bình")` chỉ sửa `name` của đối tượng đầu. Đối tượng thứ hai vẫn có `name = "An"`. Hai field `id` là hai giá trị riêng; `nextId` là chung.
5. `Counter.createdCount()` trả `nextId - 1 = 2`, phản ánh số đối tượng đã được cấp id trong ví dụ. Trong ứng dụng thực tế, cách đếm này chỉ đúng khi mọi đường tạo đối tượng tăng số đếm phù hợp và không có vấn đề đồng thời.

### 6.1. Phân biệt bộ nhớ và vòng đời ở mức khái niệm

Instance field tồn tại như một phần trạng thái của object; static field gắn với class và cơ chế class loading. Biến cục bộ và tham số thuộc ngữ cảnh thực thi method/constructor. Không suy diễn rằng mọi static field bắt buộc nằm ở một “vùng nhớ vật lý” cụ thể hoặc mọi biến cục bộ luôn ở stack: JIT/JVM có quyền tối ưu cách lưu trữ. **Static không bảo đảm đối tượng tồn tại mãi**; việc thu gom object và khả năng unload class phụ thuộc tham chiếu còn sống cùng cơ chế runtime.

## 7. Quy tắc truy cập và chọn thiết kế

Các mức truy cập sau áp dụng theo ngữ cảnh hợp lệ cho field, method, constructor:

| Modifier | Ý nghĩa khái quát |
| --- | --- |
| `private` | Chỉ truy cập trong phạm vi class khai báo và các quyền truy cập lồng nhau theo Java |
| *package-private* (không ghi modifier) | Các class trong cùng package |
| `protected` | Cùng package, và subclass ở ngoài package theo các quy tắc truy cập `protected` |
| `public` | Mã ở nơi khác có thể truy cập nếu class/module chứa nó cũng cho phép |

Việc class nằm trong một named module với `module-info.java` có thể đặt thêm giới hạn ở ranh giới module. Một member `public` không bảo đảm mọi code ở mọi module truy cập được nếu package chưa được export.

Cách chọn thành phần dựa trên câu hỏi “thứ này thuộc một đối tượng cụ thể hay toàn lớp?”:

| Nhu cầu | Lựa chọn thường phù hợp | Ví dụ |
| --- | --- | --- |
| Mỗi đối tượng có dữ liệu khác nhau | `private` instance field | `BankAccount.balance` |
| Hành vi phụ thuộc trạng thái một đối tượng | Instance method | `account.deposit(...)` |
| Kiểm tra và thiết lập trạng thái khi tạo | Constructor | `new BankAccount("An")` |
| Tính toán không cần trạng thái object | Static method | `Math.max(a, b)` |
| Hằng số chia sẻ có giá trị cố định | `static final` | `MAX_RETRIES` |
| Trạng thái chia sẻ có thể thay đổi | Static field, chỉ khi thật cần | Bộ đếm chung có đồng bộ |

Constructor phải đảm bảo object hợp lệ; method nên đại diện cho hành vi hoặc truy vấn rõ nghĩa. Nếu đối tượng phải duy trì các invariant như số dư không âm, giới hạn quyền cập nhật field, không để caller tự đặt giá trị tùy tiện.

## 8. Những lỗi phổ biến và cách nhận diện

1. **Dùng instance field từ static method không có object**:
   ~~~java
   class Wrong {
       int value = 5;
       static int read() {
           // return value; // LỖI biên dịch: non-static variable
           return new Wrong().value; // hợp lệ vì có đối tượng
       }
   }
   ~~~
   Dòng bị comment cố ý minh họa lỗi và không được biên dịch nếu bỏ comment.
2. **Nhầm constructor với method**: `void Product()` là method tên `Product`, **không phải** constructor. Constructor không khai báo kiểu trả về.
3. **Tưởng vẫn có constructor rỗng tự động**: chỉ cần khai báo một constructor có tham số là constructor mặc định do compiler sinh không còn.
4. **Nhầm `final` là bất biến sâu**: final khóa phép gán lại biến/field, không khóa mọi trạng thái bên trong object được tham chiếu.
5. **Nhầm static method với instance dispatch**: static method được chọn theo kiểu ở compile time và có thể hide static method khác; instance method đủ điều kiện mới override/dispatch động.
6. **Coi mỗi object có bản sao static field**: các object cùng class được nạp chung nhìn thấy cùng field; thay đổi từ nơi này có thể ảnh hưởng nơi khác.
7. **Coi `counter++` trong static field là an toàn đa luồng**: đây là chuỗi thao tác đọc–tính–ghi, cần cơ chế đồng bộ hoặc giải pháp tránh trạng thái chia sẻ.
8. **Đọc field khi chưa thiết lập giá trị mong muốn**: giá trị mặc định như `0`/`null` có thể che giấu lỗi thiếu khởi tạo. Ưu tiên constructor xác lập invariant, sử dụng `final` nếu thích hợp.
9. **Lạm dụng static cho dữ liệu theo người dùng hoặc phiên**: dữ liệu có thể bị chia sẻ ngoài ý muốn; dùng object sở hữu trạng thái riêng thay vì static field toàn cục.
10. **Lộ `this` quá sớm từ constructor**: callback hoặc thread khác có thể nhìn thấy object chưa khởi tạo hoàn chỉnh, dẫn đến lỗi khó tái hiện.

## 9. Tự kiểm tra cách suy luận

**Tình huống A.** Có hai instance `a` và `b` của cùng class. `a.name = "A"` và `b.name = "B"`. Sau đó gán `a.name = "C"`. Điều gì xảy ra với `b.name`? Nếu `name` là instance field thì nó vẫn là `"B"`; mỗi object có trạng thái riêng.

**Tình huống B.** Một static field `total` tăng từ 0 lên 1 thông qua một object. Static method của class đọc `total` sẽ thấy gì trong cùng ngữ cảnh thực thi tuần tự? Giá trị 1, vì hai thao tác tác động cùng static field.

**Tình huống C.** Class định nghĩa `Book(String title)` nhưng không định nghĩa `Book()`. Lời gọi `new Book()` có chạy được không? Không, vì compiler không tự thêm no-arg constructor sau khi class đã khai báo constructor bất kỳ.

**Tình huống D.** Constructor mặc định, field initializer và static block có chạy mỗi lần gọi instance method không? Không: static initializer tuân theo thời điểm khởi tạo class; instance initializer và constructor diễn ra khi tạo object, không chạy lại chỉ vì gọi method.

Khi đọc một class mới, hãy xác định lần lượt: (1) field nào riêng cho mỗi instance và field nào là static; (2) đường tạo object và invariant trong constructor; (3) method nào cần `this`; (4) ai được phép truy cập hay sửa field; (5) liệu static mutable state có gây phụ thuộc toàn cục hoặc lỗi đồng thời. Nắm được năm điều này là nền tảng để hiểu đóng gói, kế thừa, đa hình, vòng đời đối tượng và các thiết kế Java lớn hơn.