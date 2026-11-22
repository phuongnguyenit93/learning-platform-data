# Hàm khởi tạo có tham số và nạp chồng hàm khởi tạo trong Java

**Hàm khởi tạo (constructor)** là thành phần được thực thi trong quá trình tạo một đối tượng Java bằng `new` hoặc thông qua những cơ chế khởi tạo tương ứng. **Constructor có tham số** cho phép bên gọi cung cấp dữ liệu để đối tượng bắt đầu ở trạng thái có ý nghĩa. **Nạp chồng constructor (constructor overloading)** cho phép một lớp cung cấp nhiều cách tạo đối tượng, khác nhau ở số lượng, kiểu hoặc thứ tự các tham số, nhưng vẫn tuân thủ cùng những quy tắc hợp lệ của lớp.

Mục tiêu của bài: hiểu cú pháp, phân biệt constructor với method, thiết kế các overload dễ dùng, tổ chức chuỗi gọi `this(...)` và `super(...)`, kiểm soát trạng thái ban đầu, giải thích lỗi trùng chữ ký/mơ hồ và tự kiểm tra bằng chương trình **Java 17+** chạy được.

## 1. Constructor có tham số dùng để làm gì?

Xét một lớp `Book` dùng để mô hình hóa sách trong kho. Mỗi đối tượng cần có tên sách, tác giả và số bản sao. Thay vì khởi tạo một đối tượng chưa đủ thông tin rồi cho mã bên ngoài tùy ý sửa các trường, ta có thể yêu cầu dữ liệu ngay lúc tạo.

Đoạn minh họa đặt trong một lớp `Book`:

~~~java
private final String title;
private final String author;
private int copies;

Book(String title, String author, int copies) {
    if (title == null || title.isBlank()) {
        throw new IllegalArgumentException("Tên sách không hợp lệ");
    }
    if (author == null || author.isBlank()) {
        throw new IllegalArgumentException("Tác giả không hợp lệ");
    }
    if (copies < 0) {
        throw new IllegalArgumentException("Số bản sao không được âm");
    }

    this.title = title;
    this.author = author;
    this.copies = copies;
}
~~~

Lúc sử dụng:

~~~java
Book book = new Book("Java Core", "An", 5);
~~~

Đây là đoạn gọi minh họa, chưa phải chương trình độc lập. Biểu thức `new Book(...)` tạo đối tượng rồi thực hiện quá trình khởi tạo. Các đối số tương ứng với ba tham số của constructor. Constructor kiểm tra các dữ liệu trước khi gán để bảo đảm object được tạo thành công không mang `title` rỗng hoặc `copies` âm.

Nếu constructor ném ngoại lệ, biểu thức tạo đối tượng **không hoàn thành bình thường** và không trả tham chiếu mới về biến `book`. Điều đó không có nghĩa JVM hoàn tác mọi tác dụng phụ mà constructor đã thực hiện trước khi ném ngoại lệ: tránh ghi dữ liệu bên ngoài, đưa `this` ra ngoài hoặc cập nhật tài nguyên không thể hoàn tác trong một constructor chưa hoàn tất.

## 2. Cấu trúc và đặc điểm của constructor

Mẫu khai báo đơn giản:

~~~text
[access-modifier] ClassName(Type1 param1, Type2 param2, ...) {
    // kiểm tra và thiết lập trạng thái
}
~~~

Các thành phần trong ngoặc vuông là ký hiệu mô tả, không phải cú pháp Java để nhập nguyên văn.

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tên constructor | `Book` | Phải trùng với tên đơn giản của lớp khai báo |
| Danh sách tham số | `(String title, int copies)` | Cung cấp dữ liệu đầu vào khi khởi tạo |
| Quyền truy cập | `public`, `protected`, `private`, hoặc không ghi | Kiểm soát nơi được phép gọi constructor |
| Thân constructor | `{ ... }` | Thiết lập trạng thái và thực hiện logic khởi tạo |
| Khai báo ngoại lệ | `throws IOException` khi cần | Cho biết checked exception có thể phát sinh |
| Lời gọi ủy quyền | `this(...)` hoặc `super(...)` | Chuyển sang constructor cùng lớp hoặc lớp cha |

**Constructor không khai báo kiểu trả về**, kể cả `void`. Đây là khác biệt cú pháp quan trọng so với phương thức:

~~~java
class Sample {
    Sample(int value) {
        System.out.println("Constructor: " + value);
    }

    void Sample() {
        System.out.println("Đây là method, không phải constructor");
    }
}
~~~

`Sample(int)` là constructor vì tên trùng lớp và không có kiểu trả về. `void Sample()` là **phương thức** có tên `Sample`, dù người đọc dễ nhầm. Đoạn này chỉ minh họa một lớp, không có `main`.

Constructor **không kế thừa, không override**, không có `static`, `final`, `abstract`, `synchronized` như method tương ứng. Constructor có thể nạp chồng bằng các danh sách tham số khác nhau. `return;` không có giá trị có thể dùng để kết thúc constructor trong những ngữ cảnh hợp lệ, nhưng `return someValue;` không hợp lệ.

## 3. Constructor mặc định và constructor không tham số

Hai khái niệm thường bị gọi chung nhưng khác nhau:

- **Constructor mặc định do compiler cung cấp (*default constructor*):** xuất hiện khi lớp **không khai báo bất kỳ constructor nào**. Với lớp thông thường, constructor mặc định không tham số gọi constructor lớp cha không tham số qua `super()` theo quy tắc ngôn ngữ; quyền truy cập phụ thuộc khai báo lớp. Nó chỉ hoạt động nếu quá trình gọi constructor cha hợp lệ.
- **Constructor không tham số tự viết (*explicit no-arg constructor*):** do lập trình viên khai báo, có thể đặt giá trị mặc định, kiểm tra điều kiện và ủy quyền cho constructor khác.

Ví dụ minh họa riêng:

~~~java
class Plain {
    int value;
    // Không viết constructor: Java cung cấp default no-arg constructor.
}

class Configured {
    int value;

    Configured() {
        value = 10;
    }

    Configured(int value) {
        this.value = value;
    }
}
~~~

Với `new Plain()`, trường `value` nhận mặc định là 0. Với `new Configured()`, `value` được đặt thành 10.

**Điểm mấu chốt:** ngay khi lớp tự khai báo **bất kỳ constructor nào**, Java **không tự sinh thêm constructor mặc định**. Ví dụ cố ý không biên dịch:

~~~java
class OnlyParameterized {
    OnlyParameterized(String name) {
    }
}

class UseIt {
    void test() {
        new OnlyParameterized(); // Lỗi: không có constructor không tham số.
    }
}
~~~

Nếu API cần cho phép `new OnlyParameterized()`, phải tự khai báo overload không tham số và xác định giá trị mặc định hợp lệ. Không nên thêm constructor rỗng chỉ để tránh lỗi compile nếu object thật sự cần dữ liệu bắt buộc.

## 4. Nạp chồng constructor theo chữ ký

Trong một lớp, có thể định nghĩa nhiều constructor khác nhau:

~~~java
class Ticket {
    Ticket() { }
    Ticket(int seats) { }
    Ticket(String code) { }
    Ticket(String code, int seats) { }
    Ticket(int seats, String code) { }
}
~~~

Đây là **định nghĩa lớp minh họa**. Các overload khác nhau vì:

| Constructor | Số tham số | Danh sách kiểu theo thứ tự |
| --- | ---: | --- |
| `Ticket()` | 0 | Rỗng |
| `Ticket(int)` | 1 | `int` |
| `Ticket(String)` | 1 | `String` |
| `Ticket(String,int)` | 2 | `String`, rồi `int` |
| `Ticket(int,String)` | 2 | `int`, rồi `String` |

Giống phương thức, constructor không thể được nạp chồng **chỉ nhờ đổi tên tham số**:

~~~java
class Duplicate {
    Duplicate(int age) { }
    Duplicate(int count) { } // Lỗi: cả hai là Duplicate(int).
}
~~~

Constructor vốn **không có return type**, vì vậy càng không có chuyện dựa vào kiểu trả về để phân biệt overload. Thêm modifier quyền truy cập hay `throws` cũng không tạo được một chữ ký constructor khác.

Việc có thể khai báo cả `Ticket(String,int)` và `Ticket(int,String)` **không chứng minh thiết kế nên có cả hai**. Hai cách sắp xếp dễ gây nhầm nghĩa; hãy chọn quy ước nhất quán và chỉ bổ sung overload khi thật sự có lợi cho caller.

## 5. Thiết kế overload bằng cách ủy quyền qua `this(...)`

Nếu tất cả overload cùng thiết lập những trường giống nhau, sao chép nguyên phần validation vào mỗi constructor dễ dẫn đến lỗi không nhất quán. Java cho phép **một constructor gọi constructor khác trong chính lớp đó** bằng `this(...)`.

Ví dụ:

~~~java
Book() {
    this("Chưa đặt tên");
}

Book(String title) {
    this(title, "Chưa rõ");
}

Book(String title, String author) {
    this(title, author, 0);
}

Book(String title, String author, int copies) {
    // Kiểm tra và gán toàn bộ trạng thái ở đây.
}
~~~

Như vậy:

~~~text
new Book()
  -> Book("Chưa đặt tên")
    -> Book("Chưa đặt tên", "Chưa rõ")
      -> Book("Chưa đặt tên", "Chưa rõ", 0)
        -> validate và gán các trường
~~~

Những constructor ít tham số đóng vai trò **đặt mặc định**; constructor nhiều tham số là **điểm khởi tạo chính**. Nếu về sau điều chỉnh quy tắc hợp lệ của `copies`, chỉ cần thay đổi logic trung tâm.

### Quy tắc phải nhớ với `this(...)`

Trong **Java 17**, lời gọi constructor tường minh `this(...)` phải là **câu lệnh đầu tiên trong thân constructor**, không thể đặt phép gán, `println` hay `if` phía trước. Constructor đã chọn `this(...)` thì không được đồng thời gọi `super(...)` như một lời gọi constructor tường minh khác trong cùng thân.

Câu lệnh `this(...)` không có nghĩa là “tạo thêm một object”: nó tiếp tục **khởi tạo cùng một object** bằng constructor khác. Chuỗi ủy quyền không được tạo **vòng lặp**:

~~~java
class BrokenChain {
    BrokenChain() {
        this(1);
    }

    BrokenChain(int value) {
        this(); // Lỗi: recursive constructor invocation.
    }
}
~~~

Đây là **ví dụ lỗi cố ý**. Nếu bỏ sót một đường kết thúc ở constructor khởi tạo thực, compiler sẽ từ chối chuỗi gọi đệ quy.

## 6. Ví dụ hoàn chỉnh: các cách tạo Book với tham số

Tạo tệp **`ConstructorOverloadingDemo.java`** với hai lớp cấp cao nhất: lớp `Book` có quyền package-private, và lớp `public ConstructorOverloadingDemo` chứa `main`.

~~~java
import java.util.Objects;

class Book {
    private final String title;
    private final String author;
    private int copies;

    Book() {
        this("Chưa đặt tên");
    }

    Book(String title) {
        this(title, "Chưa rõ");
    }

    Book(String title, String author) {
        this(title, author, 0);
    }

    Book(String title, String author, int copies) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tên sách không hợp lệ");
        }
        if (author == null || author.isBlank()) {
            throw new IllegalArgumentException("Tác giả không hợp lệ");
        }
        if (copies < 0) {
            throw new IllegalArgumentException("Số bản sao không được âm");
        }

        this.title = title;
        this.author = author;
        this.copies = copies;
    }

    // Một copy constructor do ta tự định nghĩa, không phải tính năng
    // sao chép tự động được Java cung cấp.
    Book(Book source) {
        this(Objects.requireNonNull(source, "source").title,
                source.author, source.copies);
    }

    void addCopies(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số cộng phải dương");
        }
        copies = Math.addExact(copies, amount);
    }

    String summary() {
        return title + " | " + author + " | " + copies;
    }

    int copies() {
        return copies;
    }
}

public class ConstructorOverloadingDemo {
    public static void main(String[] args) {
        Book first = new Book();
        Book second = new Book("Java 17");
        Book third = new Book("Clean Architecture", "Lan");
        Book fourth = new Book("OOP thực hành", "Minh", 5);
        Book copy = new Book(fourth);

        System.out.println(first.summary());
        System.out.println(second.summary());
        System.out.println(third.summary());
        System.out.println(fourth.summary());
        System.out.println(copy.summary());
        System.out.println("Cùng object: " + (fourth == copy));

        fourth.addCopies(2);
        System.out.println("Bản gốc sau cộng: " + fourth.copies());
        System.out.println("Bản sao: " + copy.copies());

        try {
            new Book("Lỗi", "An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
    }
}
~~~

Mở terminal tại thư mục chứa tệp, sử dụng Java 17 trở lên:

~~~bash
javac -encoding UTF-8 ConstructorOverloadingDemo.java
java ConstructorOverloadingDemo
~~~

**Stdout:**

~~~text
Chưa đặt tên | Chưa rõ | 0
Java 17 | Chưa rõ | 0
Clean Architecture | Lan | 0
OOP thực hành | Minh | 5
OOP thực hành | Minh | 5
Cùng object: false
Bản gốc sau cộng: 7
Bản sao: 5
Từ chối: Số bản sao không được âm
~~~

### Đọc từng lời gọi constructor

| Biểu thức | Overload được chọn | Trạng thái ban đầu |
| --- | --- | --- |
| `new Book()` | `Book()` | Tên và tác giả mặc định, số bản sao 0 |
| `new Book("Java 17")` | `Book(String)` | Tác giả mặc định, bản sao 0 |
| `new Book("Clean Architecture", "Lan")` | `Book(String,String)` | Bản sao 0 |
| `new Book("OOP thực hành", "Minh", 5)` | `Book(String,String,int)` | Bản sao 5 |
| `new Book(fourth)` | `Book(Book)` | Sao chép giá trị ba trường tại thời điểm gọi |

Mọi đường tạo đều đi đến `Book(String,String,int)` và cùng kiểm tra dữ liệu. Các trường `title` và `author` là `final`, nên được gán một lần trong chuỗi khởi tạo; `copies` là trường thay đổi được qua hành vi `addCopies`.

`new Book(fourth)` **tạo một đối tượng khác**. Sau đó `fourth.addCopies(2)` chỉ tăng số bản sao trên `fourth`, không sửa trường nguyên thủy `copies` của `copy`. Vì `String` bất biến, việc chia sẻ giá trị tham chiếu chuỗi tên/tác giả trong ví dụ không cho phép sửa nội dung chuỗi tại chỗ.

**Lưu ý về copy constructor:** Java không tự tạo một constructor `Book(Book)`. Đây là overload do người viết tự định nghĩa. Nếu lớp chứa `List`, mảng hay đối tượng con có thể sửa, copy constructor cần quyết định rõ **sao chép nông hay sâu**, tránh tưởng rằng `new Book(other)` đương nhiên tạo bản sao sâu.

## 7. `this.field` và tham số trùng tên

Trong constructor chính:

~~~java
this.title = title;
this.author = author;
this.copies = copies;
~~~

Vế trái `this.title` chỉ **field** thuộc đối tượng đang được tạo; `title` ở vế phải là **tham số constructor**. Dùng `this` là cách phân biệt hai định danh cùng tên trong phạm vi hiện tại.

Nếu viết `title = title;` thì cả hai `title` có thể được hiểu là **tham số**, do tham số che tên field; câu lệnh không thiết lập field như mong đợi. Nếu field `title` là một blank final field, compiler còn có thể báo chưa được gán khi kết thúc constructor.

Hãy phân biệt:

- `this.title`: truy cập trường của object hiện tại.
- `this(...)`: **gọi constructor khác cùng lớp**.
- `super(...)`: **gọi constructor lớp cha**.
- `new Book(...)`: **tạo một object mới** rồi khởi tạo nó.

Bốn cách viết liên quan đến quá trình khởi tạo nhưng có ý nghĩa khác nhau. `this(...)` không tạo thêm object mới, còn `new` thường tạo object mới theo ngữ nghĩa biểu thức tạo lớp.

## 8. Constructor overloading và cơ chế chọn overload

Khi gặp `new Book("Java 17")`, compiler nhìn **các constructor truy cập được** có tên của lớp rồi xác định overload áp dụng và cụ thể nhất dựa trên **kiểu biểu thức đối số tại compile time**. Không phải JVM thử từng constructor từ trên xuống để xem constructor nào chấp nhận dữ liệu.

Những chuyển đổi như **mở rộng kiểu primitive**, **boxing/unboxing** và **varargs** có thể tham gia lựa chọn giống cơ chế chọn phương thức nạp chồng. Cách xử lý `null` cũng phụ thuộc kiểu tham chiếu của các tham số.

Tạo chương trình độc lập **`ConstructorResolutionDemo.java`**:

~~~java
class Ticket {
    Ticket(int seats) {
        System.out.println("int");
    }

    Ticket(long seats) {
        System.out.println("long");
    }

    Ticket(Integer seats) {
        System.out.println("Integer");
    }

    Ticket(int... seats) {
        System.out.println("varargs:" + seats.length);
    }
}

public class ConstructorResolutionDemo {
    public static void main(String[] args) {
        new Ticket(3);
        new Ticket(3L);
        new Ticket(Integer.valueOf(3));
        new Ticket();
        new Ticket(3, 4);
        new Ticket(new int[] {5, 6});
    }
}
~~~

Chạy:

~~~bash
javac ConstructorResolutionDemo.java
java ConstructorResolutionDemo
~~~

**Stdout:**

~~~text
int
long
Integer
varargs:0
varargs:2
varargs:2
~~~

**Vì sao?** `new Ticket(3)` dùng kiểu literal `int` và chọn `Ticket(int)`; `3L` là `long`; `Integer.valueOf(3)` đã là đối tượng `Integer`. Lời gọi không đối số chọn `Ticket(int...)` với mảng rỗng. Hai đối số `3, 4` được đưa vào varargs, còn `new int[]{5, 6}` truyền mảng có sẵn.

Chương trình này **không khai báo `Ticket()`**, nhưng `new Ticket()` vẫn hợp lệ nhờ constructor varargs nhận **0 phần tử**. Đây không phải default constructor do compiler tự tạo: vì lớp đã khai báo constructor, compiler không cung cấp default constructor.

### Lựa chọn có thể trở nên khó đoán

Nếu một lớp khai báo `Ticket(long)` và `Ticket(Integer)` nhưng **không có `Ticket(int)`**, lời gọi `new Ticket(3)` sẽ chọn `Ticket(long)` bởi mở rộng nguyên thủy được xét trước boxing. Khi thiết kế API, đừng dựa vào việc caller tự đoán các thứ tự chuyển đổi này; tránh đưa quá nhiều overload primitive/wrapper có hành vi khác biệt.

## 9. Các trường hợp `null` và constructor mơ hồ

Ví dụ **cố ý gây lỗi ở nơi gọi**:

~~~java
class Parcel {
    Parcel(String label) {
    }

    Parcel(Integer number) {
    }
}

class ParcelUsage {
    void use() {
        // new Parcel(null); // Lỗi nếu bỏ comment: ambiguous constructor.
        new Parcel((String) null);
        new Parcel((Integer) null);
    }
}
~~~

Cả `Parcel(String)` và `Parcel(Integer)` hợp lệ và khác chữ ký. Nhưng `new Parcel(null)` không có overload duy nhất cụ thể hơn: `null` phù hợp cả hai kiểu tham chiếu không có quan hệ subtype với nhau.

Viết `new Parcel((String) null)` có thể giải quyết **tính mơ hồ ở compile time**, nhưng không bảo đảm một constructor nào đó **chấp nhận null về mặt nghiệp vụ**. Nếu constructor có kiểm tra `Objects.requireNonNull`, lời gọi đã ép kiểu vẫn ném `NullPointerException`.

Nếu thay `Parcel(Integer)` bằng `Parcel(Object)`, khi gọi `new Parcel(null)`, compiler có thể chọn `Parcel(String)` vì `String` cụ thể hơn `Object`. Tuy nhiên việc chọn được overload không tự nói `null` là đầu vào hợp lệ.

**Thiết kế tốt** không nên yêu cầu người dùng phải ép kiểu `null` chỉ để chọn được một cách tạo object. Khi có hai cách khởi tạo khác bản chất, cân nhắc **static factory có tên riêng** hoặc kiểu yêu cầu rõ nghĩa.

## 10. Constructor với varargs

Varargs cũng hợp lệ trong constructor; tham số varargs, nếu có, phải là tham số cuối:

~~~java
class TagList {
    private final java.util.List<String> tags;

    TagList(String... tags) {
        if (tags == null) {
            throw new IllegalArgumentException("tags không được null");
        }
        this.tags = java.util.List.copyOf(
                java.util.Arrays.asList(tags));
    }
}
~~~

Đây là **định nghĩa lớp minh họa**, không có `main`. Những biểu thức sau đều hợp lệ nếu đặt trong một phương thức:

~~~java
new TagList();
new TagList("java");
new TagList("java", "oop");
new TagList(new String[] {"java", "oop"});
~~~

`new TagList()` truyền mảng varargs rỗng. `new TagList((String[]) null)` truyền **tham số mảng null** và sẽ bị kiểm tra ở constructor từ chối. `new TagList((String) null)` truyền một mảng có **một phần tử null**; `List.copyOf` từ chối phần tử null bằng `NullPointerException`.

Nếu lớp có cả constructor `TagList(String[] values)` và `TagList(String... values)` thì hai khai báo **đụng chữ ký**: tham số varargs tương ứng với kiểu mảng `String[]`.

Lời gọi đến varargs dùng mảng sẵn có có thể chia sẻ tham chiếu mảng với caller; trong ví dụ `TagList`, `List.copyOf(Arrays.asList(tags))` tạo danh sách riêng không cho sửa qua API, nhưng **không làm deep copy** các đối tượng con mutable nếu kiểu phần tử không bất biến.

## 11. Constructor của lớp cha và `super(...)`

Constructor **không được kế thừa** từ superclass. Khi khởi tạo một subclass, constructor của superclass phải tham gia quá trình khởi tạo trước khi phần khởi tạo của subclass hoàn tất.

Tạo tệp hoàn chỉnh **`ConstructorInheritanceDemo.java`**:

~~~java
class Person {
    private final String name;

    Person(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.name = name;
    }

    String describe() {
        return "Person: " + name;
    }
}

class Student extends Person {
    private final int grade;

    Student(String name, int grade) {
        super(name);
        if (grade < 1 || grade > 12) {
            throw new IllegalArgumentException("Khối lớp không hợp lệ");
        }
        this.grade = grade;
    }

    @Override
    String describe() {
        return super.describe() + "; grade=" + grade;
    }
}

public class ConstructorInheritanceDemo {
    public static void main(String[] args) {
        Student student = new Student("An", 8);
        System.out.println(student.describe());
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 ConstructorInheritanceDemo.java
java ConstructorInheritanceDemo
~~~

**Stdout:**

~~~text
Person: An; grade=8
~~~

Trong `Student(String,int)`, `super(name)` gọi constructor `Person(String)`. Sau khi phần khởi tạo superclass cần thiết hoàn thành, constructor `Student` kiểm tra và gán `grade`.

Trong **Java 17**, lời gọi constructor tường minh `super(...)` phải là **câu lệnh đầu tiên** của constructor subclass. Nếu không có lời gọi `this(...)` hoặc `super(...)` tường minh, Java sẽ chèn lời gọi `super()` ngầm theo các quy tắc tương ứng.

### Khi superclass không có constructor không tham số

Trong ví dụ trên, `Person` chỉ khai báo `Person(String)`, vì vậy **không có constructor `Person()` mặc định**. Nếu viết:

~~~java
class BrokenStudent extends Person {
    BrokenStudent() {
        // Compiler ngầm tìm super(); nhưng Person() không tồn tại.
    }
}
~~~

Đây là **ví dụ lỗi biên dịch cố ý**. Sửa bằng cách gọi một constructor superclass có thể truy cập, chẳng hạn `super("Ẩn danh");`, hoặc thiết kế lại dữ liệu bắt buộc của subclass. Không nên thêm `Person()` nếu mọi `Person` phải có tên hợp lệ.

**Không được hiểu `super(...)` là khởi tạo một object `Person` thứ hai độc lập.** Nó khởi tạo **phần superclass của cùng một object `Student`** đang được tạo.

## 12. Thứ tự khởi tạo và trường `final`

Khi tạo instance của lớp thông thường, Java thiết lập giá trị mặc định cho instance fields, thực hiện chuỗi khởi tạo superclass và xử lý các field initializers, instance initializer blocks, constructor bodies theo thứ tự được JLS quy định.

Một cách ghi nhớ thực dụng đối với lớp cha/con:

1. Đối tượng được cấp phát, các instance field trước tiên có **giá trị mặc định**.
2. Chuỗi constructor đến `Object` được thực hiện theo cơ chế `this(...)`/`super(...)`.
3. Các phần khởi tạo của superclass hoàn thành trước khi phần khởi tạo tương ứng của subclass hoàn thành.
4. Field initializers và instance initializer blocks của **mỗi lớp** chạy theo thứ tự văn bản của lớp đó tại giai đoạn khởi tạo thích hợp.
5. Cuối cùng hoàn tất thân constructor được chọn qua chuỗi ủy quyền, hoặc ném ngoại lệ nếu khởi tạo thất bại.

Không nên suy ra một thứ tự đơn giản “toàn bộ field initializer của mọi lớp đều chạy trước tất cả constructor”, bởi superclass/subclass và `this(...)` có những giai đoạn khác nhau.

Ví dụ nhỏ **`InitializationOrderDemo.java`**:

~~~java
class Base {
    int x = print("Base field");

    Base() {
        print("Base constructor");
    }

    static int print(String message) {
        System.out.println(message);
        return 1;
    }
}

class Derived extends Base {
    int y = print("Derived field");

    Derived() {
        print("Derived constructor");
    }
}

public class InitializationOrderDemo {
    public static void main(String[] args) {
        new Derived();
    }
}
~~~

~~~bash
javac InitializationOrderDemo.java
java InitializationOrderDemo
~~~

Stdout:

~~~text
Base field
Base constructor
Derived field
Derived constructor
~~~

Ở đây constructor `Derived()` không ghi `super()`, nên Java gọi constructor `Base()` ngầm. Field initializer của `Base` chạy trước thân `Base()`, rồi field initializer của `Derived` chạy trước thân `Derived()`.

### Trường `final` và nhiều constructor

Một *blank final instance field* phải được gán đầy đủ theo quy tắc **definite assignment** trong mọi con đường khởi tạo hợp lệ. Trong `Book`, ta gán `title` và `author` ở constructor lõi; các overload chỉ chuyển tiếp, tránh bỏ sót hoặc gán lại field `final`.

Viết riêng từng constructor mà quên gán một trường `final` là lỗi compile. Ngược lại, một field có initializer `private final int size = 1;` không được gán lại `size = 2;` trong constructor. `final` ngăn gán lại **field**, không mặc nhiên làm các object mà một field tham chiếu đến trở thành bất biến.

## 13. Kiểm tra dữ liệu đầu vào và tránh đối tượng khởi tạo sai

Constructor nên thiết lập **invariant** (quy tắc trạng thái luôn phải đúng) ngay từ đầu. Với `Book`:

- `title` khác `null` và không chỉ gồm khoảng trắng;
- `author` khác `null` và không chỉ gồm khoảng trắng;
- `copies >= 0`.

Đặt quy tắc này trong constructor lõi giúp tất cả overload nhất quán. Nếu dữ liệu không hợp lệ, constructor ném `IllegalArgumentException` trước khi gán các trường. Điều kiện hợp lệ cần được duy trì cả trong **các phương thức thay đổi trạng thái sau khi khởi tạo** như `addCopies`.

**Không phải mọi constructor đều nên có thật nhiều kiểm tra.** Việc cần kiểm tra gì phụ thuộc ranh giới API: dữ liệu bắt buộc, trạng thái tài nguyên, ý nghĩa nghiệp vụ, tính hợp lệ của chuỗi hoặc số lượng.

### Tính toán trước khi cập nhật

Nếu constructor tính các giá trị từ tham số, hãy xử lý lỗi tràn số, `null` hoặc dữ liệu không hợp lệ sớm và rõ ràng. Với các thao tác có nhiều tác dụng phụ bên ngoài (ghi file, gửi sự kiện, sửa object do caller giữ), việc constructor thất bại **không tự rollback các thay đổi đó**.

Trong lớp cần quản lý tài nguyên như socket hoặc file, thất bại một phần quá trình khởi tạo có thể cần đóng tài nguyên vừa mở. Đừng công bố tham chiếu `this` của object chưa khởi tạo hoàn chỉnh cho listener hoặc luồng khác; có thể khiến code khác quan sát trạng thái chưa sẵn sàng.

## 14. Constructor access modifier và static factory

Constructor có thể được khai báo `public`, `protected`, `private` hoặc để mặc định package-private. Quyền truy cập quyết định **ai được tạo object bằng constructor đó**, kết hợp với quyền truy cập của lớp và các quy tắc package/module liên quan.

Ví dụ:

~~~java
public final class UserId {
    private final String value;

    private UserId(String value) {
        this.value = value;
    }

    public static UserId of(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("User ID không hợp lệ");
        }
        return new UserId(value);
    }
}
~~~

Đây là **định nghĩa lớp minh họa**; nếu muốn biên dịch tách riêng, phải lưu vào tệp `UserId.java`. `new UserId("u1")` **không thể gọi từ mã bên ngoài lớp** vì constructor là `private`; caller dùng `UserId.of("u1")`.

Static factory có tên như `of`, `from`, `parse` giúp diễn đạt mục đích thay vì buộc phân biệt quá nhiều constructor overload. Nó còn có thể trả về object có sẵn, subtype phù hợp hoặc thực hiện cơ chế cache theo thiết kế; constructor với `new` tạo một object mới theo ngữ nghĩa tạo instance thông thường.

Khi có nhiều tham số tùy chọn độc lập, nên cân nhắc **builder hoặc request object**, thay vì tạo mọi tổ hợp overload:

~~~java
// Minh họa cách dùng một builder do ứng dụng tự định nghĩa.
OrderSettings settings = OrderSettings.builder()
        .currency("VND")
        .retryCount(3)
        .timeout(java.time.Duration.ofSeconds(5))
        .build();
~~~

Đây là **ý tưởng API, không phải code chạy độc lập**, vì chưa có định nghĩa `OrderSettings`. Builder có thể tốn thêm code; chỉ nên dùng khi số lựa chọn làm constructor khó đọc.

## 15. Những lỗi thường gặp với nạp chồng constructor

| Lỗi hoặc hiểu nhầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Viết `void Book(...)` và tưởng là constructor | Có kiểu trả về nên đây là **method** | Bỏ kiểu trả về, giữ tên trùng lớp |
| Định nghĩa một constructor có tham số rồi gọi `new Book()` | Compiler không còn tự tạo default constructor | Tự khai báo `Book()` nếu có giá trị mặc định hợp lý |
| Đổi tên tham số để tạo overload mới | `Book(int count)` và `Book(int copies)` trùng chữ ký | Đổi số lượng/kiểu/thứ tự tham số có ý nghĩa |
| Gọi `this(...)` sau một phép gán trong Java 17 | Lời gọi constructor tường minh phải đứng đầu | Đặt `this(...)` làm câu lệnh đầu |
| Cho `Book()` gọi `Book(String)` rồi ngược lại | Chuỗi constructor đệ quy | Kết thúc tại một constructor lõi |
| Gọi `super()` khi superclass chỉ có constructor có tham số | Không tìm thấy constructor cha không tham số | Gọi `super(args)` hợp lệ |
| Nghĩ constructor được kế thừa/override | Constructor là thành phần khởi tạo của đúng lớp | Khai báo constructor riêng ở subclass và gọi superclass |
| Viết nhiều overload với validation khác nhau | Có đường tạo object không hợp lệ | Đặt logic cốt lõi và kiểm tra tại constructor chung |
| Cho rằng `new Book(other)` tự động sao chép sâu | Copy constructor do người viết xác định | Quy định rõ shallow/deep copy cho field mutable |
| Viết hai overload `Book(String)` và `Book(Integer)` rồi gọi `new Book(null)` | Compiler không chọn được overload duy nhất | Tránh API mơ hồ hoặc ép kiểu có chủ đích |
| Gán giá trị `final` ở mọi constructor trong chuỗi `this(...)` | Một field `final` có thể bị gán lại | Chỉ gán ở vị trí khởi tạo hợp lệ |
| Tưởng lỗi constructor tự rollback tác dụng phụ | Ngoại lệ không hoàn tác mọi ghi ngoài object | Kiểm tra sớm và quản lý tài nguyên cẩn thận |
| Nghĩ một lệnh `this(...)` tạo object mới | Constructor delegation vẫn khởi tạo cùng instance | Phân biệt `this(...)` với `new ClassName(...)` |

## 16. Chọn overload nào là cần thiết?

Không phải cứ tăng số lượng tham số là nên thêm một constructor. Một tập overload dễ dùng thường thỏa:

1. **Mọi overload tạo cùng một khái niệm đối tượng**; khác nhau chủ yếu ở cách cung cấp dữ liệu hoặc mức cấu hình.
2. **Dữ liệu bắt buộc không bị che khuất** bởi constructor không tham số với giá trị mặc định tùy tiện.
3. **Thứ tự tham số và đơn vị đo rõ ràng**; tránh nhiều `String`, `int`, `boolean` dễ đảo vị trí.
4. **Một constructor lõi** quản lý validation và thiết lập invariant khi hợp lý; overload ngắn chỉ ủy quyền.
5. **Không gây mơ hồ ở `null`, varargs hoặc chuyển đổi primitive/wrapper** trong những lời gọi thường gặp.
6. **Trường `final` và tài nguyên được khởi tạo đúng**, không để object ở trạng thái dùng được nhưng thiếu dữ liệu.
7. **Có tài liệu về mặc định và lỗi**; caller biết `new Book("Java")` tạo tác giả và số bản sao nào.
8. **Kiểm thử từng đường khởi tạo** cùng các giá trị biên và tình huống thất bại.

Cần nhớ rằng overload được chọn tại **compile time** dựa trên kiểu đối số, không phải thứ tự constructor viết trong tệp. Chọn một constructor **không đồng nghĩa** code của các constructor khác không chạy: nếu constructor đó dùng `this(...)`, quá trình khởi tạo tiếp tục qua chuỗi ủy quyền đã định nghĩa.

## 17. Tự luyện tập và đáp án

**Câu 1.** Lớp khai báo `Member(String name)`. Gọi `new Member()` được không? Làm thế nào nếu muốn có constructor không tham số với tên mặc định?

**Câu 2.** Hai khai báo `Member(int age)` và `Member(int years)` có thể cùng tồn tại không? Nếu không, tại sao?

**Câu 3.** Trong `Book()` gọi `this("Chưa đặt tên")`, có bao nhiêu object `Book` được tạo bởi một lệnh `new Book()`? Các constructor khác có thể được thực thi không?

**Câu 4.** Tại sao cách viết dưới đây lỗi trong Java 17?

~~~java
Member(String name) {
    System.out.println("init");
    this(name, 0);
}
~~~

Hãy viết lại để constructor delegation hợp lệ. Đoạn trên là ví dụ cố ý lỗi, giả định có overload `Member(String,int)`.

**Câu 5.** Nếu superclass chỉ có `Parent(String)`, subclass `Child()` có thể bỏ `super(...)` và dựa vào `super()` ngầm không?

**Câu 6.** Với hai constructor `Packet(String)` và `Packet(Integer)`, `new Packet(null)` có hợp lệ không? `new Packet((String)null)` khác gì?

**Câu 7.** Trong ví dụ `Book(Book source)`, tại sao sau khi `fourth.addCopies(2)` thì `copy.copies()` vẫn là 5? Có thể tổng quát điều đó cho mọi field tham chiếu mutable không?

**Câu 8.** Nêu trường hợp nào nên dùng constructor nhiều overload và trường hợp nào nên dùng static factory hoặc builder.

**Đáp án gợi ý:**

1. Không: khai báo constructor có tham số khiến default constructor không được compiler tự thêm. Viết `Member() { this("Ẩn danh"); }` cùng overload `Member(String)` thích hợp.
2. Không; cả hai có chữ ký `Member(int)`; tên tham số không phân biệt overload.
3. Chỉ **một object**, nhưng các constructor trong chuỗi `this(...)` có thể lần lượt được thực thi để thiết lập object đó.
4. Trong Java 17, `this(...)` phải đứng đầu thân: `Member(String name) { this(name, 0); }`. Nếu cần log sau, đặt `println` sau lệnh `this(...)`.
5. Không nếu `Parent()` không tồn tại hoặc không truy cập được; cần một lời gọi `super(args)` hợp lệ.
6. Mơ hồ vì cả hai nhận `null` và không kiểu nào cụ thể hơn; ép kiểu `(String)null` chọn overload `String`, dù vẫn phải thỏa precondition.
7. Hai object có hai field `int copies` riêng, được chép **giá trị số** ở thời điểm khởi tạo. Với field tham chiếu mutable, copy nông vẫn có thể chia sẻ object con, nên không thể tổng quát.
8. Overload phù hợp khi có vài cách cung cấp dữ liệu cho **cùng cách tạo object**. Factory/builder phù hợp khi cần tên mục đích rõ, kiểm soát tạo object hoặc nhiều tùy chọn cấu hình.

## 18. Tài liệu đối chiếu

- [Java Language Specification 17, §8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): cú pháp constructor, chữ ký, nạp chồng, quyền truy cập, constructor mặc định và lời gọi `this`/`super`.
- [Java Language Specification 17, §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): quy trình tạo và khởi tạo instance.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): cách `new` chọn constructor và tạo instance.
- [Java SE 17 API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)): từ chối tham chiếu null trong copy constructor.

**Ghi nhớ:** constructor có tham số giúp object bắt đầu ở **trạng thái hợp lệ**; constructor overloading cung cấp **nhiều cách khởi tạo hợp lý**; `this(...)` giúp tập trung quy tắc mặc định và validation, còn `super(...)` khởi tạo phần superclass. Hãy phân biệt constructor không tham số do **bạn khai báo** với default constructor do **compiler chỉ cung cấp khi lớp không khai báo constructor nào**, và tránh overload khiến caller không biết sẽ chọn constructor nào.
