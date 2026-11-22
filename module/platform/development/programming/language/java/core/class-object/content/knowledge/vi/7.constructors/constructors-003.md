# Toán tử `new`: cấp phát, khởi tạo và nhận tham chiếu trong Java

Khi viết:

~~~java
Student student = new Student("Mai", 20);
~~~

Java không chỉ “gọi một hàm tên Student”. Biểu thức `new Student("Mai", 20)` yêu cầu tạo **một instance mới của class `Student`**, thực hiện quá trình khởi tạo theo quy tắc Java, rồi **cho ra một giá trị tham chiếu** đến object vừa tạo khi thành công. Cuối cùng, phép gán `=` lưu tham chiếu đó vào biến `student`.

Muốn hiểu class và object, hãy phân biệt những việc thường bị gộp lại thành một:

1. **Khai báo biến tham chiếu**: `Student student;` tạo một biến có kiểu `Student`, nhưng **không tự tạo Student object**.
2. **Biểu thức tạo instance**: `new Student("Mai", 20)` là *class instance creation expression*. Nó thực hiện những bước liên quan đến cấp phát và khởi tạo instance.
3. **Constructor**: `Student(String, int)` là constructor được lựa chọn; nó tham gia thiết lập trạng thái hợp lệ cho instance, không phải một method trả về kiểu `Student`.
4. **Nhận và lưu tham chiếu**: khi biểu thức `new` hoàn tất bình thường, caller có một giá trị tham chiếu; `student = ...` hoặc một cách dùng kết quả khác sẽ quyết định tham chiếu ấy được lưu hay sử dụng thế nào.

Bài viết sử dụng Java 17 trở lên, tập trung vào vòng đời một lần tạo object bằng `new`, thứ tự khởi tạo, sự khác nhau giữa object và reference, các trường hợp thất bại, và những lỗi thường gặp trong constructor.

## 1. Những thành phần trong một biểu thức `new`

Cú pháp cơ bản để tạo instance của class:

~~~java
new ClassName(argument1, argument2)
~~~

Trong đó:

- `new` là toán tử/từ khóa bắt đầu biểu thức tạo instance.
- `ClassName` xác định kiểu class cần tạo, ví dụ `Student`, `BankAccount` hoặc `ArrayList<String>`.
- Các biểu thức `argument1`, `argument2` được đánh giá rồi truyền cho **constructor** phù hợp.
- Kết quả của biểu thức `new` khi thành công là **reference value không null** đến instance được tạo.

Ví dụ:

~~~java
Student a;                    // Chỉ khai báo biến tham chiếu.
a = new Student("Mai", 20);   // Tạo instance, sau đó gán tham chiếu vào a.
Student b = a;                // Sao chép tham chiếu; KHÔNG có new Student.
Student c = new Student("Mai", 20); // Một instance khác.
~~~

Đây là đoạn minh họa, cần có class `Student` phù hợp và đặt trong phương thức hoặc khối lệnh hợp lệ.

Cần nhận ra ba dạng giá trị:

| Biểu thức | Có tạo Student mới không? | Ý nghĩa |
| --- | --- | --- |
| `Student a;` | Không | Khai báo biến tham chiếu |
| `a = new Student("Mai", 20);` | Có | Tạo instance, khởi tạo rồi gán reference |
| `Student b = a;` | Không | Hai biến cùng tham chiếu một object |
| `Student c = new Student("Mai", 20);` | Có | Tạo một object độc lập |
| `a = null;` | Không | Gán reference value đặc biệt `null` |
| `new Student("Mai", 20);` | Có, nếu hoàn tất bình thường | Tạo object nhưng không lưu trực tiếp reference ở biến từ biểu thức này |

Khi thấy `new` xuất hiện trong mã, đừng nhầm số **biến tham chiếu** với số **object**. Một object có thể được nhiều biến cùng tham chiếu; ngược lại một biến có thể được gán lần lượt những tham chiếu tới nhiều object khác nhau.

## 2. Ví dụ đầu tiên: tạo, sử dụng và phân biệt hai object

Lưu file **`FirstNewDemo.java`**:

~~~java
public class FirstNewDemo {
    static final class Student {
        private final String name;
        private int lessons;

        Student(String name, int lessons) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
            if (lessons < 0) {
                throw new IllegalArgumentException("lessons must be >= 0");
            }
            this.name = name;
            this.lessons = lessons;
        }

        void completeLesson() {
            lessons++;
        }

        String describe() {
            return name + ": " + lessons + " lessons";
        }
    }

    public static void main(String[] args) {
        Student first = new Student("Mai", 2);
        Student alias = first;
        Student second = new Student("Mai", 2);

        alias.completeLesson();

        System.out.println(first.describe());
        System.out.println(second.describe());
        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == second: " + (first == second));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FirstNewDemo.java
java FirstNewDemo
~~~

Stdout:

~~~text
Mai: 3 lessons
Mai: 2 lessons
first == alias: true
first == second: false
~~~

Giải thích:

- `new Student("Mai", 2)` được thực hiện **hai lần**, tạo hai instance riêng.
- Constructor kiểm tra tham số rồi gán `name` và `lessons` cho **instance tương ứng**.
- `Student alias = first;` không sử dụng `new`, chỉ sao chép giá trị tham chiếu.
- `alias.completeLesson()` cập nhật object chung của `first` và `alias` lên 3 bài học.
- Object `second` được tạo riêng nên vẫn giữ 2 bài.
- Toán tử `==` với hai giá trị reference kiểm tra có cùng trỏ tới một object hay không. Hai object có field bằng nhau **không tự nhiên** trở thành một object.

Trong ví dụ, class `Student` được khai báo là một `static nested class` để tất cả nằm trong một file độc lập. Từ `static` ở khai báo nested class **không có nghĩa** mọi Student instance đều dùng chung hai field `name`, `lessons`; đó vẫn là **instance fields**.

## 3. Các giai đoạn logic của `new Class(...)`

Có thể hình dung quy trình tạo class instance như sau:

~~~text
Mã bên gọi gặp biểu thức new Student(...)
                   |
                   v
Xác định kiểu class và constructor phù hợp
(được kiểm tra ở compile time; class cần sẵn sàng ở runtime)
                   |
                   v
Cấp phát không gian cho instance mới;
thiết lập các field về giá trị mặc định ban đầu
                   |
                   v
Đánh giá các biểu thức đối số theo thứ tự quy định
và thực hiện lời gọi constructor được chọn
                   |
                   v
Thực thi chuỗi khởi tạo liên quan:
superclass -> field/initializer block -> constructor body
                   |
           +-------+---------+
           |                 |
       Thành công         Exception/Error
           |                 |
           v                 v
new cho ra reference    new không trả reference
           |                 bình thường cho caller
           v
Bên gọi gán/cất/truyền/dùng reference
~~~

Đây là **mô hình logic**, không phải bản đồ máy ảo cấp phát từng byte hay lịch chạy JIT. Cơ chế JVM và tối ưu hóa có thể khiến cách tổ chức bộ nhớ thực tế khác sơ đồ, nhưng kết quả quan sát được phải phù hợp với quy tắc của Java.

Một số mốc quan trọng:

1. **Chọn constructor:** compiler dựa trên kiểu và số lượng đối số, quy tắc overload và quyền truy cập để xác định constructor phù hợp. Constructor không được chọn tùy ý theo giá trị runtime.
2. **Chuẩn bị class:** JVM phải có định nghĩa class phù hợp; việc sử dụng `new` có thể kích hoạt khởi tạo class nếu class chưa được khởi tạo. Static initialization được xử lý riêng với initialization của từng instance.
3. **Cấp phát instance:** runtime cần tạo một instance mới có những field tương ứng. Nếu không đủ tài nguyên, có thể có `OutOfMemoryError`.
4. **Giá trị mặc định:** các field có giá trị mặc định ban đầu trước khi bước khởi tạo tường minh liên quan đến chúng chạy. Đừng coi giá trị mặc định là trạng thái nghiệp vụ đã hợp lệ.
5. **Đánh giá đối số và chạy constructor:** biểu thức đối số có thể có side effect hoặc ném exception; constructor cũng có thể ném exception. Không có bảo đảm rằng `new` sẽ hoàn tất.
6. **Trả reference:** sau khi toàn bộ quá trình hoàn tất bình thường, biểu thức cho ra tham chiếu đến instance vừa tạo. **Constructor không khai báo kiểu trả về**; đó là một đặc điểm khác với phương thức trả object.
7. **Bên gọi nhận kết quả:** phép gán, lời gọi method hoặc biểu thức bao quanh mới quyết định reference được sử dụng như thế nào.

Việc khởi tạo class (`static`) chỉ diễn ra khi cần cho một class runtime tương ứng và theo các quy tắc liên quan, **không lặp lại mỗi lần `new` cùng class**. Ngược lại, instance field initializer và constructor chạy cho **mỗi instance mới** theo chuỗi khởi tạo áp dụng.

## 4. Trước hết phải phân biệt class initialization và instance initialization

Hai việc này có tên gần nhau nhưng mục đích khác nhau.

### Class initialization

Các `static field initializer` và `static initializer block` gắn với class runtime, không gắn với từng object. Trong chương trình đơn giản, khi `new Example()` lần đầu kích hoạt việc khởi tạo `Example`, các bước static initialization của `Example` (và superclass cần thiết) được chạy theo quy định.

~~~java
class Example {
    static int created = 0;

    static {
        System.out.println("Example static initialization");
    }

    Example() {
        created++;
    }
}
~~~

Đây là class minh họa, chưa có `main`. Nếu tạo hai object liên tiếp sau khi class đã được khởi tạo, static block không in hai lần; constructor có thể tăng `created` trong **mỗi lần `new`**.

Ở ứng dụng có class loader tùy biến, hai class cùng tên do các class loader khác nhau định nghĩa có thể là hai class runtime khác nhau và có static state khác nhau. Không nên diễn đạt “static chạy đúng một lần cho mọi thời đại” một cách tuyệt đối.

### Instance initialization

Mỗi lần tạo instance mới, quá trình khởi tạo các **instance fields**, **instance initializer blocks** và **constructor** của các class trong chuỗi kế thừa được thực hiện theo thứ tự Java quy định.

~~~java
class Counter {
    private int value = 10;  // Instance field initializer.

    {
        System.out.println("Counter instance block");
    }

    Counter() {
        System.out.println("Counter constructor");
    }
}
~~~

Ở đây field initializer và instance block là những bước tạo trạng thái **cho một Counter mới**. Chúng không phải static, nên được thực hiện cho từng lần khởi tạo instance thông thường.

## 5. Ví dụ chạy: thứ tự static, superclass, field và constructor

Một chương trình cụ thể giúp tránh suy đoán mơ hồ về thứ tự:

Lưu **`InitializationOrderDemo.java`**:

~~~java
public class InitializationOrderDemo {
    static int trace(String label, int value) {
        System.out.println(label);
        return value;
    }

    static class Base {
        static {
            System.out.println("Base static");
        }

        int baseValue = trace("Base field", 1);

        {
            System.out.println("Base block");
        }

        Base() {
            System.out.println("Base constructor");
        }
    }

    static final class Child extends Base {
        static {
            System.out.println("Child static");
        }

        int childValue = trace("Child field", 2);

        {
            System.out.println("Child block");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("main begin");

        Child first = new Child();
        System.out.println("second new");
        Child second = new Child();

        System.out.println("values="
                + first.baseValue + "," + second.childValue);
    }
}
~~~

~~~bash
javac -encoding UTF-8 InitializationOrderDemo.java
java InitializationOrderDemo
~~~

Stdout:

~~~text
main begin
Base static
Child static
Base field
Base block
Base constructor
Child field
Child block
Child constructor
second new
Base field
Base block
Base constructor
Child field
Child block
Child constructor
values=1,2
~~~

Lần tạo `Child` đầu tiên:

1. `main` in `main begin`.
2. JVM khởi tạo `Base` (static block) trước `Child` theo thứ tự superclass thích hợp, rồi static block của `Child`.
3. Instance `Child` được khởi tạo với phần superclass `Base` trước: `Base field` → `Base block` → `Base constructor`.
4. Sau đó các instance initializer của `Child` chạy: `Child field` → `Child block` → `Child constructor`.
5. `new Child()` hoàn tất và biến `first` nhận reference.

Lần tạo `Child` thứ hai:

- Static blocks **không chạy lại** do class đã được khởi tạo.
- Mỗi instance mới vẫn phải chạy chuỗi **Base field, Base block, Base constructor, Child field, Child block, Child constructor**.
- `first` và `second` tham chiếu đến **hai object khác nhau**.

**Không suy luận sai:** `Base constructor` không đồng nghĩa với tạo thêm một Base object độc lập. Trong ví dụ `new Child()`, bước khởi tạo superclass là **phần của việc khởi tạo một Child instance**, không tạo ra một Base instance thứ hai để trả về cho caller.

## 6. Giá trị mặc định tồn tại trước khi gán tường minh

Trước các instance initializer, trường của object được gán giá trị mặc định theo kiểu:

| Kiểu field | Giá trị mặc định |
| --- | --- |
| `byte`, `short`, `int`, `long` | 0 theo kiểu tương ứng |
| `float`, `double` | 0.0 theo kiểu tương ứng |
| `char` | `'\\u0000'`, đơn vị mã UTF-16 bằng 0 |
| `boolean` | `false` |
| Các kiểu tham chiếu, ví dụ `String`, `List<?>`, mảng | `null` |

Đừng nhầm giá trị mặc định của field với **biến cục bộ**: local variable phải được compiler xác định đã gán trước lần đọc; không có quy tắc “local int luôn mặc định 0”.

### Ví dụ khởi tạo theo thứ tự văn bản

Lưu file **`DefaultFieldDemo.java`**:

~~~java
public class DefaultFieldDemo {
    static final class Sample {
        int observed = this.value;
        int value = 7;

        Sample() {
            System.out.println("observed=" + observed);
            System.out.println("value=" + value);
        }
    }

    public static void main(String[] args) {
        new Sample();
    }
}
~~~

~~~bash
javac -encoding UTF-8 DefaultFieldDemo.java
java DefaultFieldDemo
~~~

Stdout:

~~~text
observed=0
value=7
~~~

Khi `observed = this.value` chạy, `value` chưa nhận giá trị tường minh `7`, nên vẫn là giá trị mặc định `0`. Sau đó field initializer của `value` gán `7`.

**Điểm tinh tế:** Dùng tên đơn giản `int observed = value;` khi `value` là instance field khai báo phía sau trong cùng class có thể gây lỗi `illegal forward reference`. Việc dùng `this.value` ở ví dụ trên làm biểu thức hợp lệ theo quy tắc forward reference, **nhưng có thể tạo lỗi logic**. Không nên tận dụng khả năng này để viết các initializer phụ thuộc field chưa được thiết lập.

## 7. Constructor thiết lập trạng thái hợp lệ nhưng không phải method trả object

Constructor có tên trùng tên class và **không có kiểu trả về**:

~~~java
class Book {
    private final String title;

    Book(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        this.title = title;
    }
}
~~~

Đây là định nghĩa class minh họa. Dòng `Book(String title)` là constructor; `this.title = title` lưu tham số vào field của **object đang được khởi tạo**.

Sai lầm thường gặp:

~~~java
class Book {
    void Book(String title) {
        // Đây là METHOD tên Book, không phải constructor.
    }
}
~~~

Đoạn class này hợp lệ về cú pháp Java nếu thân method hợp lệ: vì có kiểu trả về `void`, nó chỉ là một method tên `Book`. Nếu class không khai báo constructor nào, compiler có thể cung cấp default constructor không tham số theo quy tắc Java. Phương thức `void Book(String)` **không tự chạy** khi `new Book()`.

### Constructor không trả reference bằng `return object;`

Không viết:

~~~java
Book(String title) {
    return new Book(title); // KHÔNG hợp lệ trong constructor.
}
~~~

Đoạn trên là **minh họa lỗi biên dịch**, không phải code để chạy. Constructor có thể dùng `return;` không kèm biểu thức để kết thúc sớm theo quy tắc Java, nhưng không thể trả một object như method.

Reference là kết quả của **biểu thức `new Book(...)` khi thành công**, chứ không phải một giá trị do constructor `return` tường minh.

Nếu muốn tạo object bằng một **method có tên thể hiện nghiệp vụ**, có thể dùng static factory:

~~~java
static Book titled(String title) {
    return new Book(title);
}
~~~

Đây là method minh họa đặt trong ngữ cảnh thích hợp. Ở đây **method `titled` trả `Book`** theo cú pháp `return`; bản thân constructor `Book(String)` vẫn không trả giá trị.

## 8. Constructor chaining: `this(...)` và `super(...)`

Một class có thể có nhiều constructor với chữ ký khác nhau. Trong Java 17, lời gọi constructor khác bằng `this(...)` hoặc constructor superclass bằng `super(...)` phải được đặt ở vị trí **câu lệnh đầu tiên** trong constructor khi xuất hiện dưới dạng explicit constructor invocation.

- `this(...)` gọi một constructor khác của **cùng class**, không tạo thêm object mới.
- `super(...)` gọi một constructor của **superclass**, cũng là bước khởi tạo của cùng object đang được xây dựng.
- Nếu constructor không viết `this(...)` hoặc `super(...)`, compiler thông thường chèn lời gọi `super()` ngầm định, và superclass phải có constructor không tham số khả dụng.
- Một chuỗi `this(...)` cuối cùng phải dẫn đến một constructor gọi `super(...)` hoặc `super()` ngầm định; không được tạo vòng đệ quy constructor.

Lưu file **`ConstructorChainDemo.java`**:

~~~java
public class ConstructorChainDemo {
    static final class Ticket {
        private final String label;
        private final int quantity;

        Ticket() {
            this("DEFAULT");
            System.out.println("no-arg constructor");
        }

        Ticket(String label) {
            this(label, 1);
            System.out.println("one-arg constructor");
        }

        Ticket(String label, int quantity) {
            if (label == null || label.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("invalid ticket");
            }

            this.label = label;
            this.quantity = quantity;
            System.out.println("two-arg constructor");
        }

        String describe() {
            return label + " x" + quantity;
        }
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket();
        System.out.println(ticket.describe());
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorChainDemo.java
java ConstructorChainDemo
~~~

Stdout:

~~~text
two-arg constructor
one-arg constructor
no-arg constructor
DEFAULT x1
~~~

Dù constructor được gọi qua nhiều tầng `this(...)`, lệnh `new Ticket()` **chỉ tạo một Ticket instance**. Các constructor tham gia thiết lập **cùng một object**; khi chuỗi hoàn tất, biểu thức `new` trả reference đến object đó.

### Khi superclass không có constructor không tham số

~~~java
class Base {
    Base(int id) {}
}

class Child extends Base {
    Child() {
        super(1);
    }
}
~~~

Đoạn class trên hợp lệ. Nếu trong `Child()` bỏ `super(1);` mà không thay bằng lời gọi thích hợp, Java 17 sẽ cố dùng `super()` ngầm định nhưng `Base` không có constructor không tham số, dẫn đến lỗi biên dịch.

Câu hỏi cần nhớ không phải “mỗi constructor có tạo object mới không?” mà là “constructor nào được gọi **để khởi tạo object của biểu thức `new` hiện tại**?”.

## 9. Đánh giá đối số: kết quả có thể thay đổi trước constructor body

Một constructor invocation có thể nhận các biểu thức đối số chứa lời gọi method hoặc tác dụng phụ. Những biểu thức đối số được đánh giá theo thứ tự **từ trái sang phải**. Nếu một biểu thức ném exception, lời gọi constructor được chọn có thể chưa chạy body.

Lưu **`ConstructorArgumentsDemo.java`**:

~~~java
public class ConstructorArgumentsDemo {
    static int argument(String label, int value) {
        System.out.println("arg " + label);
        return value;
    }

    static final class Pair {
        private final int left;
        private final int right;

        Pair(int left, int right) {
            System.out.println("constructor");
            this.left = left;
            this.right = right;
        }

        int sum() {
            return left + right;
        }
    }

    public static void main(String[] args) {
        System.out.println("before new");
        Pair pair = new Pair(
                argument("left", 2),
                argument("right", 3));

        System.out.println("sum=" + pair.sum());
        System.out.println("after new");
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorArgumentsDemo.java
java ConstructorArgumentsDemo
~~~

Stdout:

~~~text
before new
arg left
arg right
constructor
sum=5
after new
~~~

Điều quan sát được là:

1. Hai biểu thức đối số được đánh giá **trước khi body của `Pair` constructor được thực thi**.
2. `argument("left", 2)` chạy trước `argument("right", 3)`.
3. Body constructor in `constructor`.
4. `pair` chỉ nhận reference qua phép gán nếu biểu thức `new Pair(...)` hoàn tất bình thường.
5. Sau đó, `pair.sum()` gọi instance method trên object mới.

Đừng đồng nhất thứ tự log trên với tất cả bước bên trong JVM. Ở mức ngôn ngữ, việc cấp phát và các bước thực thi bị ràng buộc bởi đặc tả; JIT có thể tối ưu hóa theo cách giữ nguyên các tác động quan sát được. Đối với việc viết code, câu hỏi thường là **khi constructor body bắt đầu, các đối số đã được tính xong chưa?** — có, nếu thân constructor thực sự được vào theo đường này.

### Khi một đối số ném exception

~~~java
static int fail() {
    throw new IllegalStateException("argument failed");
}

// Trong một method:
Pair pair = new Pair(1, fail());
~~~

Đây là mảnh mã minh họa; `Pair` là kiểu từ ví dụ trên nếu cùng ngữ cảnh, không phải chương trình độc lập. Vì `fail()` ném exception trong quá trình chuẩn bị đối số, body của `Pair(int, int)` **không được gọi** ở lời gọi đó. Cũng không có reference thành công để gán vào `pair`.

## 10. Thất bại khi khởi tạo: `new` không cho kết quả bình thường

Một constructor có thể ném `IllegalArgumentException` khi đầu vào không hợp lệ; initializer hoặc superclass constructor cũng có thể ném exception. Nếu exception lan ra khỏi toàn bộ quá trình tạo object, biểu thức `new` **hoàn tất bất thường**, không cung cấp reference bình thường cho caller.

Lưu file **`FailedConstructionDemo.java`**:

~~~java
public class FailedConstructionDemo {
    static final class Account {
        private final int balance;

        Account(int balance) {
            System.out.println("constructor balance=" + balance);

            if (balance < 0) {
                throw new IllegalArgumentException("negative balance");
            }

            this.balance = balance;
            System.out.println("constructed");
        }

        int balance() {
            return balance;
        }
    }

    public static void main(String[] args) {
        Account account = null;

        try {
            account = new Account(-5);
            System.out.println("assigned");
        } catch (IllegalArgumentException ex) {
            System.out.println("caught: " + ex.getMessage());
        }

        System.out.println("account is null: " + (account == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 FailedConstructionDemo.java
java FailedConstructionDemo
~~~

Stdout:

~~~text
constructor balance=-5
caught: negative balance
account is null: true
~~~

Ở đây:

- Constructor đã bắt đầu nhưng ném exception **trước khi hoàn tất**.
- Dòng `this.balance = balance` và `constructed` không chạy.
- Phép gán `account = new Account(-5)` không hoàn tất vì vế phải kết thúc bất thường.
- Biến `account` đã được khởi tạo `null` trước `try` và **vẫn là null** sau `catch`.
- Dòng `assigned` không được chạy.

**Không kết luận quá mức:** object đang được xây dựng có thể đã trải qua một phần quá trình cấp phát/khởi tạo trước khi exception xảy ra. Điều chắc chắn từ góc nhìn caller là **biểu thức `new` không trả một reference theo đường hoàn tất bình thường**. Các tác dụng phụ đã diễn ra trước exception (in log, cập nhật static counter, ghi dữ liệu bên ngoài...) không tự được hoàn tác.

### Nếu initializer hoặc static initialization thất bại

Một static initializer có thể kết thúc bằng exception; JVM thường báo `ExceptionInInitializerError` khi nguyên nhân thích hợp xảy ra trong khởi tạo class. Những lần dùng class sau đó có thể gặp lỗi tiếp theo như `NoClassDefFoundError` do class ở trạng thái khởi tạo thất bại, tùy bối cảnh. Đây là lỗi của **khởi tạo class runtime**, không phải vì constructor có từ khóa `return` khác.

Tương tự, nếu một instance initializer hoặc superclass constructor ném exception, constructor dưới không hoàn tất, và `new` không trả reference bình thường. Thay vì đoán rằng mọi vấn đề khi `new` là lỗi “thiếu bộ nhớ”, hãy đọc **exception type, message và stack trace**.

## 11. Nguy cơ lộ `this` trước khi object khởi tạo xong

Trong constructor, `this` biểu thị object đang được xây dựng. Nếu bạn gửi `this` ra bên ngoài (đăng ký callback, thêm vào static collection, tạo thread rồi cho chạy ngay...), mã bên ngoài có thể quan sát object **chưa hoàn tất quá trình khởi tạo**, gây lỗi trạng thái hoặc concurrency.

Ví dụ cần tránh (minh họa, không phải chương trình chạy độc lập):

~~~java
class Registry {
    static Object last;
}

class UnsafePublication {
    private final String name;

    UnsafePublication(String name) {
        Registry.last = this; // Cho nơi khác thấy object quá sớm.
        this.name = name;
    }
}
~~~

Khi `Registry.last = this` được thực hiện, field `name` chưa được gán tham số. Nếu một thành phần khác truy cập object đó đúng thời điểm, nó có thể quan sát trạng thái không đáp ứng invariant của class. Trong môi trường nhiều thread, còn phải xét các quy tắc publication và visibility của Java Memory Model.

Các nguyên tắc phòng tránh:

- Hoàn tất thiết lập trạng thái trong constructor trước khi công bố reference.
- Tránh gọi từ constructor một instance method có thể bị override rồi phụ thuộc vào field của subclass chưa khởi tạo.
- Không khởi chạy thread từ constructor nếu thread có thể chạy và dùng `this` trước khi khởi tạo xong.
- Dùng static factory khi cần một quy trình tạo object gồm nhiều bước và chỉ trả object sau khi đã hoàn tất cấu hình.

Lưu ý: chỉ viết `private final` cho field không tự bảo đảm an toàn nếu `this` đã bị xuất bản không đúng cách trước khi constructor kết thúc; cần thiết kế vòng đời object cẩn thận.

## 12. Vì sao không nên gọi method override được từ constructor?

Trong Java, instance method được override có thể dispatch theo **runtime type** của object ngay cả khi superclass constructor đang chạy. Trong khi đó, field/initializer của subclass có thể **chưa khởi tạo xong**, dẫn đến giá trị mặc định bất ngờ.

Lưu **`OverrideDuringConstructionDemo.java`**:

~~~java
public class OverrideDuringConstructionDemo {
    static class Base {
        Base() {
            System.out.println("Base constructor");
            describe();
        }

        void describe() {
            System.out.println("Base describe");
        }
    }

    static final class Child extends Base {
        private String label = "ready";

        Child() {
            System.out.println("Child constructor");
        }

        @Override
        void describe() {
            System.out.println("Child label=" + label);
        }
    }

    public static void main(String[] args) {
        Child child = new Child();
        child.describe();
    }
}
~~~

~~~bash
javac -encoding UTF-8 OverrideDuringConstructionDemo.java
java OverrideDuringConstructionDemo
~~~

Stdout:

~~~text
Base constructor
Child label=null
Child constructor
Child label=ready
~~~

Giải thích:

1. `new Child()` bắt đầu khởi tạo object kiểu runtime `Child`.
2. Superclass constructor `Base()` chạy trước khi initializer `label = "ready"` của `Child` chạy.
3. `Base()` gọi `describe()`. Vì đây là instance method có thể override, dynamic dispatch chọn **`Child.describe()`**.
4. Tại thời điểm đó, `Child.label` vẫn là giá trị mặc định `null`.
5. Sau khi superclass constructor hoàn tất, initializer của `Child` gán `label = "ready"`, constructor Child chạy.
6. Lời gọi `child.describe()` từ `main` sau khởi tạo sẽ in `Child label=ready`.

Mẫu code này **chạy được để minh họa rủi ro**, không phải cách nên thiết kế. Nếu constructor cần thao tác nội bộ, hãy dùng helper `private`/`static` thích hợp, hoặc cấu trúc quá trình khởi tạo sao cho không gọi phương thức có thể override trước khi subclass sẵn sàng.

## 13. `new` cho ra tham chiếu, nhưng caller không nhất thiết phải lưu nó

Các cách dùng một kết quả `new` hợp lệ:

~~~java
Student a = new Student("Mai", 1);       // Lưu vào biến cục bộ.
Student b;
b = new Student("Nam", 2);               // Gán sau khi khai báo.
someMethod(new Student("Lan", 3));       // Truyền thẳng làm đối số.
new Student("An", 4).completeLesson();   // Gọi method ngay trên kết quả new.
~~~

Đây là các **mảnh mã minh họa**; cần class `Student` và `someMethod` phù hợp. Biểu thức `new` không bắt buộc phải xuất hiện sau dấu `=`.

Ở dòng thứ tư, object được tạo và method `completeLesson()` chạy trên object đó, nhưng code không giữ trực tiếp tham chiếu vào biến. Điều đó không bảo đảm object bị GC ngay lập tức sau câu lệnh; object có thể được tham chiếu ở nơi khác nếu constructor/method đã chuyển nó ra ngoài, và JVM quyết định thời điểm thu hồi theo ngữ nghĩa GC.

### Có thể trả kết quả `new` trực tiếp

~~~java
static Student createStudent(String name) {
    return new Student(name, 0);
}
~~~

Đây là **method minh họa**. Lệnh `return` thuộc **method `createStudent`**, không thuộc constructor. Nếu caller viết `Student student = createStudent("Mai");`, tham chiếu từ biểu thức `new` được truyền qua giá trị trả về của method rồi gán cho `student`.

### Khác biệt giữa `new` và phép gán

~~~java
Student first = new Student("Mai", 1);
Student second = first;
first = new Student("Nam", 2);
~~~

Sau ba dòng:

~~~text
first  --------> Student #2 { name = "Nam", lessons = 2 }
second --------> Student #1 { name = "Mai", lessons = 1 }
~~~

Dòng thứ ba **không cập nhật object #1 thành Nam**; nó tạo Student #2 rồi thay **giá trị tham chiếu** của biến `first`. `second` vẫn giữ object #1. Đó là lý do phải phân biệt **gán reference** với **thay field trên object**.

## 14. `new`, `null` và khả năng truy cập object

`null` là giá trị tham chiếu đặc biệt không trỏ đến object nào. Khai báo:

~~~java
Student student = null;
~~~

không tạo Student instance. Trước khi gán reference hợp lệ, gọi `student.completeLesson()` sẽ ném `NullPointerException`.

Ngược lại, nếu biểu thức `new Student(...)` **hoàn tất bình thường**, kết quả của class instance creation expression là reference đến instance mới, không phải null. Tuy nhiên, **biến được gán từ một method factory** có thể nhận null nếu method được thiết kế trả null; điều này khác với bản thân biểu thức `new`.

### So sánh bằng `==`

Với hai reference cùng kiểu phù hợp:

- `a == b` là `true` nếu cùng trỏ đến một object, hoặc cả hai null.
- `a == b` là `false` nếu trỏ hai object khác nhau, kể cả khi dữ liệu bên trong bằng nhau.
- `a == null` kiểm tra tham chiếu không trỏ tới object.

`equals` là method có hợp đồng riêng: class có thể định nghĩa logic **bằng nhau theo giá trị**. Đừng dùng `equals` để chứng minh hai biến có cùng identity trừ khi hợp đồng equals của class thực sự là identity như `Object.equals` mặc định.

### Tên biến không phải địa chỉ bộ nhớ

Sơ đồ “biến trỏ đến object” là mô hình hữu ích, nhưng Java không công khai địa chỉ bộ nhớ object qua phép gán tham chiếu thông thường. Không cần và không nên dùng `System.identityHashCode(object)` để suy ra địa chỉ: giá trị hash này không phải địa chỉ vật lý và không được bảo đảm duy nhất cho mọi object.

## 15. `new` với array khác `new` với class

Java còn dùng `new` để tạo **array object**:

~~~java
int[] numbers = new int[3];
String[] names = new String[2];
int[] values = new int[] {4, 5, 6};
~~~

Đây là những **biểu thức tạo mảng**:

- `new int[3]` tạo một mảng dài 3, các phần tử `int` mặc định bằng 0.
- `new String[2]` tạo mảng dài 2, các phần tử reference `String` mặc định null.
- `new int[] {4, 5, 6}` tạo mảng ba phần tử đã có giá trị chỉ định.
- Biểu thức tạo mảng không gọi constructor do người học tự khai báo như `new Student(...)`.

Lưu file **`NewArrayDemo.java`**:

~~~java
import java.util.Arrays;

public class NewArrayDemo {
    public static void main(String[] args) {
        int[] numbers = new int[3];
        String[] names = new String[2];

        System.out.println("numbers=" + Arrays.toString(numbers));
        System.out.println("names=" + Arrays.toString(names));

        numbers[1] = 8;
        System.out.println("updated=" + Arrays.toString(numbers));

        int[] alias = numbers;
        System.out.println("same array=" + (alias == numbers));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NewArrayDemo.java
java NewArrayDemo
~~~

Stdout:

~~~text
numbers=[0, 0, 0]
names=[null, null]
updated=[0, 8, 0]
same array=true
~~~

Mảng là **reference type**, nên `alias = numbers` sao chép tham chiếu tới **cùng array object**, không tự sao chép các phần tử. Có thể tạo một mảng mới rồi sao chép nội dung bằng `Arrays.copyOf` khi cần; đó là hành vi tường minh khác với chỉ gán tham chiếu.

### Kích thước mảng không hợp lệ

`new int[-1]` có biểu thức hợp lệ về cú pháp nhưng sẽ ném `NegativeArraySizeException` lúc chạy. Một kích thước quá lớn còn có thể thất bại vì tài nguyên bộ nhớ hoặc giới hạn JVM. Phải phân biệt **lỗi khởi tạo mảng** với lỗi constructor class, dù cả hai dùng từ khóa `new`.

## 16. Chọn kiểu có thể khởi tạo: class, abstract class và interface

Không phải mọi kiểu tham chiếu đều có thể đứng trực tiếp sau `new` để tạo instance của chính kiểu đó.

Hợp lệ:

~~~java
java.util.ArrayList<String> names = new java.util.ArrayList<>();
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
~~~

Hai ví dụ này là **mảnh mã**, không phải chương trình độc lập. Lưu ý:

- `new ArrayList<>()` tạo một concrete instance; dấu `<>` là **diamond operator**, để compiler suy luận type arguments phù hợp trong ngữ cảnh.
- `new Runnable() { ... }` là cú pháp tạo instance của một **anonymous class** triển khai `Runnable`; không phải tạo trực tiếp object có kiểu runtime là interface `Runnable`.
- Không thể viết `new Runnable()` không kèm thân anonymous class vì interface không có constructor tạo instance trực tiếp.

Ví dụ sai:

~~~java
abstract class Shape {}

// new Shape();    // Không tạo trực tiếp abstract class.
// new Runnable(); // Không tạo trực tiếp interface.
~~~

Khi generic type variable chưa có concrete runtime type phù hợp, không thể mặc nhiên viết `new T()` trong một generic class/method chỉ vì đã khai báo `<T>`. Thay vào đó có thể nhận factory, `Supplier<T>` hoặc đối tượng đã được tạo từ caller. Đây là giới hạn của ngữ nghĩa generic và erasure, không phải “new không hỗ trợ generic”.

### Không thể gọi constructor như method thông thường

~~~java
Student s = new Student("Mai", 1);
// s.Student("Nam", 2); // Không hợp lệ: constructor không phải method.
~~~

Muốn thay dữ liệu của object đang tồn tại, hãy thiết kế một instance method hợp lệ hoặc tạo **object mới** bằng `new`; không “chạy lại constructor” bằng cú pháp method để tái khởi tạo một object có sẵn.

## 17. Lỗi biên dịch và lỗi khi chạy quanh `new`

| Biểu hiện | Nguồn gốc | Cách xử lý |
| --- | --- | --- |
| `cannot find symbol` khi viết `new Student(...)` | Tên class chưa được khai báo/import đúng hoặc sai package | Kiểm tra tên, import/package, tệp được biên dịch |
| `constructor Student ... cannot be applied to given types` | Số lượng/kiểu đối số không khớp constructor | So khớp chữ ký, kiểu và overload |
| `Student() has private access` | Constructor có access modifier không cho caller dùng | Dùng factory/cách tạo được class công khai |
| `no suitable constructor found` | Không tìm được constructor áp dụng cho đối số | Kiểm tra tham số bắt buộc và chuyển đổi kiểu |
| `reference to Student is ambiguous` | Nhiều overload constructor cùng áp dụng mà không chọn được cụ thể nhất | Làm rõ kiểu đối số, đặc biệt khi truyền null |
| `constructor ... is already defined` | Khai báo hai constructor trùng chữ ký | Đổi cấu trúc tham số hoặc tên factory |
| `constructor ... cannot be applied ... required: ... found: no arguments` | Class có constructor tham số, nhưng caller viết `new Class()` | Truyền đủ tham số hoặc thiết kế thêm constructor |
| `cannot instantiate abstract class` | Dùng `new` trực tiếp trên abstract type | Tạo một concrete subclass |
| `OutOfMemoryError` | Runtime không đủ bộ nhớ/tài nguyên cấp phát | Kiểm tra số lượng object, dữ liệu, vòng đời giữ reference, giới hạn bộ nhớ |
| `IllegalArgumentException` trong constructor | Dữ liệu vi phạm quy tắc do constructor xác định | Validate và truyền dữ liệu hợp lệ |
| `NullPointerException` sau khai báo biến | Biến đang null hoặc một reference trung gian khác null không hợp lệ | Xác định điểm tạo/gán object, kiểm tra giá trị |
| `NoClassDefFoundError` / lỗi initialization | JVM không thể nạp hoặc khởi tạo class theo ngữ cảnh | Đọc nguyên nhân và stack trace; kiểm tra classpath, static initializer |
| Kết quả ở object mới khác mong đợi | Field khởi tạo theo thứ tự chưa đúng, constructor bỏ sót gán hoặc bị shadowing | Dùng `this.field`, kiểm tra initializer/constructor chain |
| Hai biến đổi theo nhau | Hai biến giữ cùng reference chứ không có hai `new` độc lập | Vẽ sơ đồ alias và xác định nơi tạo instance |

**Đừng sửa lỗi bằng cách thêm constructor rỗng cho mọi class**. Nếu một object cần `id` hoặc `name` bắt buộc để hợp lệ, constructor không tham số có thể cho phép tạo state sai. Phải ưu tiên hợp đồng dữ liệu hơn việc compiler chấp nhận một cú pháp ngắn.

## 18. Quy tắc thiết kế constructor khi dùng `new`

Một constructor tốt nên đưa object tới một trạng thái hợp lệ và dễ dự đoán khi thành công. Những nguyên tắc thực hành:

1. **Xác định invariant ngay từ đầu:** object phải có thuộc tính nào? Ví dụ `price >= 0`, `name` khác null/trống.
2. **Validate tham số trước khi sửa state hay gọi dịch vụ bên ngoài** khi khả thi. Constructor ném exception có thể để lại side effect bên ngoài, nên không dùng constructor làm nơi thực hiện giao dịch khó hoàn tác.
3. **Dùng `this.field = parameter`** khi tên trùng nhau; tránh lỗi `field = field` tự gán tham số.
4. **Không công bố `this` quá sớm**, nhất là qua listener, static holder và thread.
5. **Hạn chế gọi method override được trong constructor** vì field của subclass có thể chưa được khởi tạo.
6. **Đừng thực hiện tác vụ nặng hoặc I/O phức tạp không rõ hợp đồng** trong constructor nếu có thể tách việc chuẩn bị và chạy tác vụ.
7. **Dùng `final` cho field thực sự chỉ gán một lần**, đồng thời hiểu rằng field `final` tham chiếu object mutable không tự làm object ấy immutable.
8. **Đừng đặt mutable shared state thành static một cách vô tình.** Static field khác bản chất so với instance field, dù cùng có thể xuất hiện trong class có constructor.
9. **Dùng constructor overload có chủ đích**, ủy quyền bằng `this(...)` để tránh lặp validation và cách khởi tạo khác nhau.
10. **Dùng static factory/builder khi tạo object cần nhiều bước diễn đạt**, nhưng hiểu rằng bên trong factory vẫn có thể có lời gọi `new` và constructor theo cách thích hợp.

Một kiểu kết quả có thể là immutable value object, một service mutable hoặc một đối tượng tài nguyên; những kiểu này có nhu cầu khởi tạo khác nhau. Không có một mẫu constructor áp dụng tối ưu cho mọi class.

## 19. Bài tập thực hành

### Bài 1 — Đếm số object, không đếm số biến

~~~java
Student a = new Student("A", 0);
Student b = a;
Student c = new Student("A", 0);
a = c;
~~~

Có **hai** lần `new Student(...)`, tạo hai Student instance nếu đều hoàn tất thành công. Cuối cùng `a` và `c` cùng trỏ object thứ hai; `b` trỏ object thứ nhất. Viết kết quả dự kiến của `a == b`, `a == c`, `b == c`: lần lượt **false**, **true**, **false**.

### Bài 2 — Dự đoán constructor chaining

Với `ConstructorChainDemo`, hãy sửa `new Ticket()` thành `new Ticket("VIP")`. Dự đoán stdout:

~~~text
two-arg constructor
one-arg constructor
VIP x1
~~~

Vì constructor không tham số không được gọi ở lần tạo này. Cả hai constructor `Ticket(String)` và `Ticket(String, int)` vẫn thiết lập **một object**.

### Bài 3 — Thứ tự initializer

Dựa vào `InitializationOrderDemo`, thêm hai field initializer mới của `Child` và một instance block giữa chúng. Dự đoán vị trí log. Chạy hai lần `new Child()` và chứng minh static block chỉ xuất hiện ở lần khởi tạo class, còn instance initializer xuất hiện cho mỗi object.

### Bài 4 — Constructor ném exception

Đổi `new Account(-5)` thành `new Account(0)` trong `FailedConstructionDemo`. Dự đoán constructor sẽ in:

~~~text
constructor balance=0
constructed
assigned
account is null: false
~~~

Nếu `balance = -5`, phép gán không hoàn tất và biến vẫn null. Giải thích chính xác điều kiện nào khiến constructor từ chối object.

### Bài 5 — Mảng và instance khác nhau

Tạo:

~~~java
int[] counts = new int[2];
Student[] students = new Student[2];
~~~

Một mảng `students` gồm hai **phần tử null** ban đầu không tương đương đã có hai Student object. Chỉ khi viết `students[0] = new Student("A", 0);` mới có Student instance ở phần tử đầu; phần tử thứ hai vẫn null cho đến khi gán reference hợp lệ.

### Bài 6 — Phân tích anti-pattern

Đọc `OverrideDuringConstructionDemo`, giải thích vì sao lời gọi `describe()` đầu tiên in `null`. Hãy đề xuất refactor để superclass constructor không gọi overridable method và chỉ sử dụng `label` sau khi object đã khởi tạo xong.

### Bài 7 — Tham chiếu trả từ factory

Tạo static factory:

~~~java
static Student newBeginner(String name) {
    return new Student(name, 0);
}
~~~

Trong caller viết `Student s = newBeginner("Mai");`. Chỉ ra: object được tạo ở đâu? Constructor có return một Student không? Method factory có return tham chiếu không? Đáp án: **object được tạo bởi biểu thức `new` bên trong factory; constructor không trả giá trị; method factory trả tham chiếu do biểu thức `new` cho ra khi thành công**.

## 20. Checklist nắm vững

- [ ] Tôi phân biệt `Student x;` và `new Student(...)`.
- [ ] Tôi giải thích được `new` hoàn tất bình thường mới cung cấp reference cho caller.
- [ ] Tôi nhận diện đúng constructor và biết constructor **không có kiểu trả về**.
- [ ] Tôi biết tham số constructor được đánh giá trước khi body constructor chạy.
- [ ] Tôi phân biệt class/static initialization với instance initialization.
- [ ] Tôi dự đoán được trình tự superclass → instance initializer → constructor khi tạo subclass.
- [ ] Tôi biết `this(...)` và `super(...)` là lời gọi constructor trong **cùng quy trình tạo một object**, không tự tạo object thứ hai.
- [ ] Tôi hiểu giá trị mặc định của instance fields trước bước khởi tạo tường minh.
- [ ] Tôi biết constructor ném exception khiến biểu thức `new` không trả reference bình thường và phép gán có thể không diễn ra.
- [ ] Tôi biết hai biến có thể chia sẻ object, và hai lần `new` riêng tạo hai instance khác nhau.
- [ ] Tôi phân biệt `new Class(...)` và `new int[n]` về constructor và khởi tạo phần tử.
- [ ] Tôi biết `new` không tạo trực tiếp instance của interface/abstract class.
- [ ] Tôi không coi `System.identityHashCode` là địa chỉ bộ nhớ.
- [ ] Tôi tránh xuất bản `this` sớm và tránh gọi overridable method trong constructor.
- [ ] Tôi tự biên dịch, chạy và giải thích chính xác stdout các chương trình Java 17+ trong bài.

**Tóm tắt:** Toán tử `new` gắn các khái niệm **cấp phát → khởi tạo → nhận tham chiếu** thành một biểu thức tạo object. Constructor là một bước trong quá trình khởi tạo, không phải method trả object. Sau khi biểu thức `new` thành công, Java cho caller một **giá trị tham chiếu** có thể được gán vào biến, truyền sang method hoặc dùng ngay. Nắm rõ ba bước này là nền tảng để hiểu state của object, aliasing, constructor chaining, kế thừa, lỗi khởi tạo và vòng đời đối tượng trong Java.
