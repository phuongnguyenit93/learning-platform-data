# Biến tham chiếu lưu gì và khác đối tượng ở điểm nào trong Java?

Khi nhìn vào câu lệnh:

~~~java
Student student = new Student("Mai");
~~~

người mới học dễ diễn giải rằng **biến `student` chính là đối tượng Student**. Đây là một cách nói tắt thiếu chính xác. Trong Java, `student` là **biến có kiểu tham chiếu `Student`**, còn `new Student("Mai")` tạo ra **một đối tượng (object) mới**. Nếu quá trình khởi tạo thành công, biểu thức `new` cung cấp **giá trị tham chiếu** đến đối tượng đó, và phép gán lưu giá trị tham chiếu vào biến `student`.

Nắm được khác biệt này là nền tảng để hiểu **aliasing**, **`null`**, **`==` so với `equals()`**, hành vi thay đổi trạng thái object, truyền tham số vào method, `final`, array, garbage collection và thiết kế class.

## 1. Mục tiêu học tập

Sau bài này, bạn cần giải thích và thực hành được:

1. **Biến tham chiếu (reference variable)** là gì, lưu loại giá trị nào, khác với một **instance/object**.
2. Phân biệt **khai báo biến**, **tạo object bằng `new`**, **gán tham chiếu**, **thay đổi field**.
3. Tại sao hai biến có thể **cùng tham chiếu một object**, và tại sao hai object có dữ liệu giống nhau vẫn là hai object.
4. Tại sao phép gán tham chiếu **không clone object** và cũng không tự thay đổi field của object cũ.
5. `null` nghĩa là gì, khác với object rỗng; thời điểm xuất hiện `NullPointerException`.
6. Khác biệt giữa giá trị **primitive** và giá trị **reference**, kể cả mảng và `String`.
7. Tại sao Java **luôn truyền tham số bằng giá trị**, kể cả khi tham số là object reference.
8. Phân biệt **object identity** và **value equality**, hiểu vai trò của `==` và `equals()`.
9. Hiểu vì sao **`final` tham chiếu** không tự biến object thành bất biến.
10. Tránh suy luận sai về địa chỉ bộ nhớ, stack/heap, vòng đời object và thời điểm garbage collector chạy.

Các ví dụ chạy độc lập sử dụng **Java 17 trở lên**. Những đoạn không phải chương trình hoàn chỉnh sẽ được ghi rõ là mã minh họa.

## 2. Ba khái niệm cần tách riêng: biến, giá trị tham chiếu và object

Xét:

~~~java
Book book = new Book("Java Core");
~~~

Có ba thành phần:

- **`Book`**: tên kiểu (class) do người lập trình định nghĩa.
- **`book`**: biến tham chiếu. Trong ngữ cảnh phù hợp, biến này có thể lưu một **giá trị tham chiếu đến Book object** hoặc `null`.
- **`new Book("Java Core")`**: biểu thức yêu cầu tạo một Book object mới; nếu hoàn tất bình thường, kết quả là tham chiếu đến object vừa tạo.

Mô hình suy nghĩ:

~~~text
Biến                    Object
+------------------+    +---------------------------+
| book             |    | Book instance             |
| reference value -+--->| title = "Java Core"       |
+------------------+    +---------------------------+
~~~

Mũi tên biểu thị **quan hệ tham chiếu**, không phải địa chỉ RAM cụ thể. Java định nghĩa cách giá trị tham chiếu hoạt động, nhưng không yêu cầu người lập trình nhìn thấy địa chỉ máy của đối tượng để dùng được tham chiếu.

Đặt câu hỏi:

- Biến là gì? `book`.
- Object là gì? Instance `Book` được tạo bởi `new Book(...)`.
- Field `title` nằm ở đâu về mặt **mô hình ngữ nghĩa**? Thuộc trạng thái của Book object.
- Gán `book` sang object khác có đồng nghĩa sửa `title` của object cũ không? **Không**.

### Một biến không chứa toàn bộ dữ liệu của object

Nếu class `Book` có mười field, việc gán:

~~~java
Book another = book;
~~~

không có nghĩa Java tự sao chép mười field sang một Book mới. Java sao chép **giá trị tham chiếu** của `book` vào biến `another`. Hai biến giờ có thể truy cập **cùng object**.

Muốn tạo một object khác, bạn thường cần một thao tác tạo object cụ thể như `new Book(...)`, một factory method hoặc một cơ chế copy do API định nghĩa. Chỉ viết `another = book` **không** tạo object mới.

## 3. Ví dụ đầu tiên: hai biến, một object, và object thứ hai

Tạo tệp **`ReferenceBasicsDemo.java`**:

~~~java
public class ReferenceBasicsDemo {
    static final class Book {
        private final String title;
        private int pagesRead;

        Book(String title) {
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("title required");
            }
            this.title = title;
        }

        void readPages(int pages) {
            if (pages <= 0) {
                throw new IllegalArgumentException("pages must be positive");
            }
            pagesRead = Math.addExact(pagesRead, pages);
        }

        String describe() {
            return title + ": " + pagesRead + " pages";
        }
    }

    public static void main(String[] args) {
        Book first = new Book("Java Core");
        Book alias = first;
        Book second = new Book("Java Core");

        alias.readPages(12);

        System.out.println("first: " + first.describe());
        System.out.println("alias: " + alias.describe());
        System.out.println("second: " + second.describe());
        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == second: " + (first == second));
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 ReferenceBasicsDemo.java
java ReferenceBasicsDemo
~~~

Stdout chính xác:

~~~text
first: Java Core: 12 pages
alias: Java Core: 12 pages
second: Java Core: 0 pages
first == alias: true
first == second: false
~~~

Từng bước:

1. `new Book("Java Core")` đầu tiên tạo **Book object số 1**; `first` giữ tham chiếu đến nó.
2. `Book alias = first;` **không tạo Book object mới**, chỉ sao chép tham chiếu.
3. `new Book("Java Core")` thứ hai tạo **Book object số 2**, dù giá trị `title` giống Book số 1.
4. `alias.readPages(12)` cập nhật field `pagesRead` trên object số 1.
5. `first.describe()` và `alias.describe()` đọc **cùng object số 1** nên cùng trả số trang 12.
6. `second.describe()` đọc object số 2 nên vẫn cho số trang 0.
7. Với tham chiếu, toán tử `==` kiểm tra hai giá trị tham chiếu có biểu thị **cùng object** hay không. Do đó `first == alias` là true, `first == second` là false.

Minh họa sau khi gọi `alias.readPages(12)`:

~~~text
first -----------+
                 +----> Book #1
alias -----------+      title = "Java Core"
                        pagesRead = 12

second ---------------> Book #2
                        title = "Java Core"
                        pagesRead = 0
~~~

**Kết luận:** Object có **danh tính** và **trạng thái**. Hai biến tham chiếu tới cùng object chia sẻ việc quan sát trạng thái; hai lần tạo object không trở thành một chỉ vì các field trùng nhau.

## 4. Khai báo biến không tạo object

Ba bước dưới đây có nghĩa khác nhau:

~~~java
Book book;                         // Chỉ khai báo biến cục bộ.
book = new Book("Java Core");      // Tạo object và gán tham chiếu.
Book another = book;               // Sao chép tham chiếu.
~~~

Nếu `Book book;` là **biến cục bộ**, Java yêu cầu biến được gán trước khi đọc. Viết:

~~~java
Book book;
// System.out.println(book); // Bỏ chú thích sẽ lỗi: biến cục bộ chưa gán.
~~~

không có chuyện local reference tự động mặc định `null` theo cách cho phép đọc ngay.

Ngược lại, **field kiểu tham chiếu** chưa được khởi tạo tường minh có giá trị mặc định là `null`:

~~~java
class Holder {
    Book current; // Instance field mặc định null.
}
~~~

Đây là class minh họa, yêu cầu kiểu `Book` có sẵn trong ngữ cảnh biên dịch. Với `Holder holder = new Holder();`, `holder.current` ban đầu là null, vì `current` là field và chưa được gán reference tới Book object.

### Không nhầm với `new`

~~~java
Book book = null;
~~~

chỉ lưu **giá trị null**, không tạo một Book object “trống”. Trong khi:

~~~java
Book book = new Book("Java Core");
~~~

mới yêu cầu tạo Book object. Biểu thức `new Book(...)` thành công cho giá trị tham chiếu không null. Nhưng một **method** trả Book vẫn có thể trả null nếu hợp đồng cho phép, ví dụ `Book findById(String id)` có thể trả null khi không tìm thấy.

## 5. Biến tham chiếu lưu “địa chỉ” hay “con trỏ”?

Có thể tưởng tượng reference là một “mũi tên” tới object, nhưng nói **“biến tham chiếu Java chắc chắn chứa địa chỉ bộ nhớ thô của object”** là quá mạnh và không chính xác theo đặc tả ngôn ngữ.

Theo mô hình Java:

- Một giá trị kiểu tham chiếu là **reference tới object** hoặc `null`.
- Reference cho phép thao tác với object theo các quy tắc truy cập field, method và array.
- Ngôn ngữ Java không có toán tử con trỏ thô thông dụng như phép cộng địa chỉ `pointer + 1` hay `&variable` của C/C++.
- JVM có thể dùng **địa chỉ, handle, compressed reference hoặc cách biểu diễn tối ưu hóa** tùy implementation. Java code thông thường không được phụ thuộc cách biểu diễn cụ thể.
- Tên biến `book` không phải tên vùng nhớ cố định nơi object phải nằm mãi; object có thể được GC di chuyển trong những implementation tương ứng mà tính đúng đắn của chương trình vẫn giữ nguyên.

Vì vậy trong học tập, có thể nói “biến tham chiếu trỏ tới object” theo nghĩa **quan hệ logic**. Nhưng đừng dùng sơ đồ mũi tên để khẳng định mọi reference thực chất là số địa chỉ 64-bit.

### `System.identityHashCode` không phải địa chỉ RAM

`System.identityHashCode(object)` cung cấp mã hash liên quan đến **identity** theo hợp đồng API, không công bố địa chỉ vật lý. Hai object khác nhau không được bảo đảm có hai identity hash khác nhau, và identity hash không phải một cách đáng tin để đo số lượng object.

Nếu cần biết hai biến có cùng object không, dùng `==` cho tham chiếu (nơi kiểu cho phép), **không** so sánh `identityHashCode`.

## 6. Giá trị tham chiếu có thể được gán lại mà object cũ không thay đổi

Tạo file **`ReferenceReassignmentDemo.java`**:

~~~java
public class ReferenceReassignmentDemo {
    static final class Box {
        private final int number;

        Box(int number) {
            this.number = number;
        }

        int number() {
            return number;
        }
    }

    public static void main(String[] args) {
        Box first = new Box(10);
        Box saved = first;

        first = new Box(20);

        System.out.println("first=" + first.number());
        System.out.println("saved=" + saved.number());
        System.out.println("same=" + (first == saved));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceReassignmentDemo.java
java ReferenceReassignmentDemo
~~~

Stdout:

~~~text
first=20
saved=10
same=false
~~~

Ban đầu `first` và `saved` cùng tham chiếu Box(10). Dòng `first = new Box(20);` thực hiện **hai việc**:

1. Tạo Box object mới có `number = 20`.
2. Gán reference mới vào **biến `first`**.

Không có câu lệnh nào sửa field `number` của Box(10). `saved` vẫn giữ reference đến Box(10), nên đọc `saved.number()` cho 10.

Sơ đồ:

~~~text
Trước gán:
first ----+
          +----> Box #1 { number = 10 }
saved ----+

Sau first = new Box(20):
first ---------> Box #2 { number = 20 }
saved ---------> Box #1 { number = 10 }
~~~

**Phép gán một biến reference khác với việc gọi method thay đổi object.** Cần đọc đúng vế trái: `first = ...` gán biến `first`, còn `first.setNumber(...)` có thể sửa object hiện được `first` tham chiếu.

## 7. Hai kiểu giá trị trong Java: primitive và reference

Java có hai nhóm kiểu chính:

| | Primitive type | Reference type |
| --- | --- | --- |
| Ví dụ | `int`, `long`, `double`, `boolean`, `char` | `Book`, `String`, `Integer`, `int[]`, `List<String>` |
| Giá trị biến lưu | Giá trị nguyên thủy của kiểu | Reference đến object hoặc null |
| Có thể lưu `null`? | Không | Có (nếu kiểu/logic cho phép) |
| Phép gán `b = a` | Sao chép giá trị primitive | Sao chép giá trị reference, **không copy object** |
| Dùng `==` | So sánh theo quy tắc kiểu primitive | So sánh identity cho hai reference phù hợp |
| Trạng thái object dùng chung qua alias? | Không có object primitive để alias | Có thể nếu nhiều reference cùng chỉ một mutable object |

Có đúng **tám kiểu primitive** trong Java: `byte`, `short`, `int`, `long`, `float`, `double`, `char`, `boolean`. `void` được dùng trong khai báo method return type nhưng không phải một primitive value type có thể khai báo biến lưu giá trị theo cách trên.

`String`, `Integer`, `Boolean` và `int[]` **đều là reference type**. Dù chúng chứa/biểu diễn giá trị văn bản hay số, không vì thế biến thuộc những kiểu này trở thành primitive.

### So sánh phép gán primitive và reference

~~~java
int left = 5;
int right = left;
right = 9;
// left vẫn là 5.

Book first = new Book("A");
Book second = first;
// first và second cùng trỏ một Book object.
~~~

Đây là mảnh mã minh họa; `Book` cần constructor phù hợp. Với primitive, `right = 9` thay đổi một biến độc lập. Với reference, `second = first` sao chép reference, nên đọc/chỉnh mutable fields qua hai biến có thể ảnh hưởng cùng object.

## 8. `null` là một giá trị tham chiếu đặc biệt, không phải object

Một biến reference có thể mang giá trị `null`:

~~~java
String text = null;
int[] numbers = null;
Object anything = null;
~~~

Điều đó **không tạo ba object rỗng**. Nó biểu thị các biến hiện không tham chiếu đến object nào.

Không nhầm:

| Biểu thức | Có object thực không? | Ý nghĩa |
| --- | --- | --- |
| `String text = null;` | Không có String object do phép gán này tạo | Biến không tham chiếu String |
| `String text = "";` | Reference tới String rỗng | Một giá trị String hợp lệ |
| `int[] numbers = null;` | Không có array object do phép gán này tạo | Không thể đọc `numbers.length` |
| `int[] numbers = new int[0];` | Có mảng dài 0 | `numbers.length == 0` |
| `new int[] {0}` | Có mảng dài 1 | Phần tử đầu là `0` |
| `new String[] {null}` | Có mảng dài 1 | Phần tử đầu là null |

### `NullPointerException` xảy ra khi nào?

Nếu một biểu thức cần sử dụng object làm receiver nhưng reference là null, có thể ném `NullPointerException`:

~~~java
String name = null;
// name.length(); // Nếu gọi, sẽ ném NullPointerException.
~~~

Phép so sánh `name == null` **không** làm dereference nên an toàn. `System.out.println(name)` có thể in `null` qua logic xử lý String, không phải vì `name` đã trở thành một object.

### Ví dụ chạy độc lập: kiểm tra null trước khi dùng

Tạo file **`NullReferenceDemo.java`**:

~~~java
public class NullReferenceDemo {
    static String describe(String value) {
        if (value == null) {
            return "(missing)";
        }
        return "length=" + value.length();
    }

    public static void main(String[] args) {
        String absent = null;
        String empty = "";
        String filled = "Java";

        System.out.println(describe(absent));
        System.out.println(describe(empty));
        System.out.println(describe(filled));
        System.out.println("absent == null: " + (absent == null));
    }
}
~~~

~~~bash
javac -encoding UTF-8 NullReferenceDemo.java
java NullReferenceDemo
~~~

Stdout:

~~~text
(missing)
length=0
length=4
absent == null: true
~~~

`describe` định nghĩa hợp đồng riêng rằng null nghĩa là thiếu dữ liệu. Với class khác, null có thể bị từ chối bằng `Objects.requireNonNull` hoặc `IllegalArgumentException`. **Java không tự quyết định rằng mọi null đều được phép về mặt nghiệp vụ.**

## 9. Alias và tác động qua object mutable

**Aliasing** là tình huống có nhiều đường tham chiếu tới **cùng một object**. Đây là nguồn gốc của nhiều thay đổi trạng thái tưởng như “ở nơi khác”.

Ví dụ:

~~~java
Account primary = new Account(100);
Account otherName = primary;
otherName.deposit(50);
~~~

Nếu `deposit(50)` sửa field `balance` của Account object, đọc qua `primary` cũng thấy số dư tăng. Không có phép gán trực tiếp nào vào biến `primary`, nhưng **trạng thái object chung** đã đổi.

Đừng nhầm các thao tác:

- `otherName = new Account(0);`: gán lại **biến `otherName`**.
- `otherName.deposit(50);`: có thể sửa **object đang được otherName tham chiếu**.
- `primary = otherName;`: gán một **reference value** vào `primary`.
- `primary.balance`: đọc field khi quyền truy cập cho phép; không tạo object mới.

### Ví dụ độc lập: alias bị sửa ở một method khác

Lưu **`AliasingDemo.java`**:

~~~java
public class AliasingDemo {
    static final class Cart {
        private int items;

        Cart(int items) {
            this.items = items;
        }

        void add(int quantity) {
            items += quantity;
        }

        int count() {
            return items;
        }
    }

    static void update(Cart cart) {
        cart.add(2);
    }

    public static void main(String[] args) {
        Cart first = new Cart(1);
        Cart alias = first;

        update(alias);

        System.out.println("first=" + first.count());
        System.out.println("alias=" + alias.count());
        System.out.println("same=" + (first == alias));
    }
}
~~~

~~~bash
javac -encoding UTF-8 AliasingDemo.java
java AliasingDemo
~~~

Stdout:

~~~text
first=3
alias=3
same=true
~~~

`update` nhận một **bản sao giá trị tham chiếu** tới Cart object. Lời gọi `cart.add(2)` sửa object chung; cả `first` và `alias` quan sát số lượng 3.

Nếu object được thiết kế immutable, một method sẽ không trực tiếp thay đổi trạng thái cũ bằng hành vi như `add`. Việc có reference **không tự cấp quyền sửa** object; điều đó phụ thuộc API và access modifiers.

## 10. Java luôn truyền tham số bằng giá trị, kể cả với object reference

Đây là quy tắc quan trọng nhất khi học biến tham chiếu:

**Java pass-by-value cho mọi tham số.** Với tham số kiểu class/array/interface, giá trị được sao chép là **giá trị tham chiếu**. Method không nhận “bí danh của biến ở caller”, nên **gán lại tham số không gán lại biến caller**.

Tạo file **`ReferenceParameterDemo.java`**:

~~~java
public class ReferenceParameterDemo {
    static final class Box {
        int value;

        Box(int value) {
            this.value = value;
        }
    }

    static void change(Box box) {
        box.value = 20;
        box = new Box(99);

        System.out.println("inside=" + box.value);
    }

    public static void main(String[] args) {
        Box original = new Box(5);

        change(original);

        System.out.println("outside=" + original.value);
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceParameterDemo.java
java ReferenceParameterDemo
~~~

Stdout:

~~~text
inside=99
outside=20
~~~

Phân tích:

1. `original` tham chiếu Box #1 có `value = 5`.
2. `change(original)` sao chép **reference value** vào parameter `box`. Lúc đầu cả hai biến cùng trỏ Box #1.
3. `box.value = 20` cập nhật **field của Box #1**, nên caller có thể đọc được 20.
4. `box = new Box(99)` tạo Box #2 và **gán lại parameter `box`**. Biến `original` ở caller vẫn trỏ Box #1.
5. `inside=99` đọc Box #2 qua tham số mới; `outside=20` đọc Box #1 qua biến caller.

Sơ đồ:

~~~text
Bắt đầu change:
original ---+
            +----> Box #1 { value=5 }
box --------+

Sau box.value = 20:
original ---+
            +----> Box #1 { value=20 }
box --------+

Sau box = new Box(99):
original --------> Box #1 { value=20 }
box -------------> Box #2 { value=99 }
~~~

**Kết luận chính xác:** Phương thức có thể sửa **trạng thái object chung**, nhưng không thể thay đổi biến reference của caller chỉ bằng câu lệnh `box = ...` bên trong method.

### Vậy tại sao người ta hay nói “truyền object theo tham chiếu”?

Đó là cách nói tắt dễ gây nhầm. Ngữ nghĩa chuẩn là **truyền bằng giá trị một tham chiếu**. Nếu thật sự truyền biến ở caller theo kiểu “pass-by-reference” như một số ngôn ngữ khác, việc gán lại parameter có thể làm caller trỏ sang object khác. Java không có hành vi đó cho method parameter thông thường.

## 11. Return object cũng là trả giá trị tham chiếu

Nếu method khai báo trả về một kiểu tham chiếu:

~~~java
static Book createBook(String title) {
    return new Book(title);
}
~~~

thì nó trả về **giá trị tham chiếu** đến Book object do `new` tạo, chứ không tự clone object thêm lần nữa. Đây là **method minh họa**; cần định nghĩa `Book` và đặt method trong class phù hợp.

Nếu method trả tham chiếu đã nhận:

~~~java
static Book identity(Book input) {
    return input;
}
~~~

thì caller nhận tham chiếu đến **chính object mà `input` biểu thị**; không có `new` trong method nên không có object mới do method này tạo.

### Cảnh giác khi trả field mutable trực tiếp

~~~java
class Library {
    private final java.util.List<String> books = new java.util.ArrayList<>();

    java.util.List<String> books() {
        return books;
    }
}
~~~

Đây là class minh họa. Caller nhận một **reference tới danh sách nội bộ**, nên nếu sửa danh sách đó, nó ảnh hưởng state của Library. Khai báo field `final` chỉ ngăn gán lại reference của field, không làm ArrayList trở nên immutable.

Nếu không muốn caller sửa danh sách nội bộ, có thể dùng `List.copyOf(books)` khi phần tử không null và hợp đồng phù hợp, hoặc cung cấp một API chỉ đọc. **Thiết kế encapsulation và aliasing** luôn đi cùng nhau.

## 12. `final` trên biến tham chiếu không làm object bất biến

Ví dụ:

~~~java
final StringBuilder builder = new StringBuilder("Java");
builder.append(" Core");             // Hợp lệ: sửa object.
 // builder = new StringBuilder();   // Nếu bỏ comment, lỗi biên dịch.
~~~

Biến `builder` được đánh dấu `final`: sau khi được gán giá trị theo quy tắc, nó **không thể được gán lại reference khác**. Nhưng `StringBuilder` là object mutable, nên `append` vẫn sửa nội dung.

Tương tự:

~~~java
final int[] numbers = {1, 2, 3};
numbers[0] = 9;                      // Hợp lệ.
 // numbers = new int[] {4, 5};     // Không hợp lệ.
~~~

`final` giữ cố định **giá trị tham chiếu của biến**, không đóng băng nội dung array object.

Phân biệt thêm:

- `private final Address address`: field không được gán lại sau khởi tạo hợp lệ; nếu `Address` mutable, object Address vẫn có thể thay đổi qua alias.
- `final class User`: không cho class khác kế thừa `User`; đây là ý nghĩa **khác** của `final`.
- Class bất biến (immutable) cần quy tắc thiết kế: không làm lộ mutable state, không cung cấp hành vi thay đổi trạng thái quan sát được, có defensive copy khi thích hợp.
- Một reference `final` không mặc nhiên kéo dài hoặc rút ngắn lifetime của object bằng một bảo đảm đơn giản.

### Ví dụ chạy `final` trên reference

Lưu **`FinalReferenceDemo.java`**:

~~~java
public class FinalReferenceDemo {
    public static void main(String[] args) {
        final StringBuilder builder = new StringBuilder("A");
        builder.append("B");

        final int[] values = {1, 2};
        values[0] = 7;

        System.out.println(builder);
        System.out.println(values[0] + "," + values[1]);
    }
}
~~~

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

Stdout:

~~~text
AB
7,2
~~~

Trong bài này, chính object mutable đã thay đổi, không có câu lệnh nào gán lại các biến `final`.

## 13. `String` là reference type nhưng immutable

`String` thường gây nhầm vì trông giống primitive khi nối chuỗi hoặc gán literal:

~~~java
String text = "Hello";
String alias = text;
text = text + " Java";
~~~

`String` vẫn là **reference type**. Biểu thức nối chuỗi tạo/cho ra một giá trị String mới theo ngữ nghĩa; phép gán `text = ...` thay reference của biến `text`. Nó **không thay đổi nội dung của String object** mà `alias` đang tham chiếu.

Tạo file **`ImmutableStringDemo.java`**:

~~~java
public class ImmutableStringDemo {
    public static void main(String[] args) {
        String first = "Hello";
        String alias = first;

        first = first + " Java";

        System.out.println("first=" + first);
        System.out.println("alias=" + alias);
        System.out.println("same=" + (first == alias));

        StringBuilder mutable = new StringBuilder("Hello");
        StringBuilder shared = mutable;
        mutable.append(" Java");

        System.out.println("mutable=" + mutable);
        System.out.println("shared=" + shared);
        System.out.println("same builder=" + (mutable == shared));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutableStringDemo.java
java ImmutableStringDemo
~~~

Stdout:

~~~text
first=Hello Java
alias=Hello
same=false
mutable=Hello Java
shared=Hello Java
same builder=true
~~~

Với `String`, thay đổi biến `first` không thể sửa nội dung chuỗi gốc. Với `StringBuilder`, method `append` sửa object chung nên `mutable` và `shared` cùng quan sát nội dung mới.

**Không kết luận rằng mọi reference type đều mutable.** Reference cho biết quan hệ tới object; **khả năng thay đổi trạng thái** là một thuộc tính của class và API.

## 14. Phân biệt object identity với bình đẳng logic

Hai câu hỏi khác nhau: `a == b` với các reference phù hợp kiểm tra có **cùng object** (hoặc cùng null) không; `a.equals(b)` hỏi hai giá trị có bằng nhau theo **hợp đồng của class** hay không. `Object.equals` mặc định dựa vào identity, còn record Java 17 định nghĩa equality từ record components.

Ví dụ chạy độc lập, tệp `ReferenceEqualityIntro.java`:

~~~java
public class ReferenceEqualityIntro {
    record Point(int x, int y) {}

    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point alias = a;
        System.out.println("same object=" + (a == b));
        System.out.println("same value=" + a.equals(b));
        System.out.println("alias=" + (a == alias));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ReferenceEqualityIntro.java
java ReferenceEqualityIntro
~~~

~~~text
same object=false
same value=true
alias=true
~~~

Với String, ưu tiên `equals` để so **nội dung**; interning có thể làm `==` cho true ở vài trường hợp mà code không nên phụ thuộc. `Objects.equals(a, b)` hỗ trợ nullable references. Các quy tắc sâu của `equals/hashCode`, wrapper caching và so sánh mảng được dạy chính ở bài `==`/`!=`; phần này chỉ thiết lập khác biệt cốt lõi.

## 15. Kiểu khai báo của biến có thể khác runtime class

Với `Dog extends Animal`, đoạn `Animal pet = new Dog();` là **snippet giả sử hai lớp đã được khai báo**. Biến pet có kiểu tĩnh `Animal` nhưng trỏ đến object có lớp thực tế `Dog`; việc upcast không tạo một object mới.

Compiler kiểm tra API gọi được dựa trên kiểu biểu thức `pet`. Khi gọi instance method được override, JVM có thể dispatch phiên bản của Dog. Cast một reference hợp lệ chỉ thay góc nhìn kiểu, **không clone object**. Nếu runtime class không tương thích, một downcast có thể ném `ClassCastException`.

Ở bài chuyên sâu về kiểu khai báo và lớp thực tế, người học sẽ đối chiếu overriding/overloading, field hiding, generics, interface và `getClass()`. Đối với bài nền tảng này, điều cần nhớ là **reference value và object identity không tự thay đổi khi đổi kiểu góc nhìn**.

## 16. Mảng là object; mỗi slot có thể là reference

~~~java
int[] values = {1, 2, 3};
int[] alias = values;
int[] copy = values.clone();
String[] names = new String[2];
~~~

Đây là snippet trong method. `values` và `names` là references tới **array objects**. Các phần tử `int[]` chứa primitive values; hai slots của `names` là references ban đầu bằng null. `alias = values` chia sẻ array object, nên sửa `alias[0]` sẽ hiện qua `values[0]`. `copy` là array object riêng có bản sao các giá trị nguyên thủy.

Với `new Student[3]`, Java tạo **một array** chứa ba slot null, không tự tạo ba Student objects. Với `Student[]`, `clone()` chỉ sao chép các references phần tử (shallow copy). Bài mảng đối tượng sẽ dạy sâu hơn các tầng aliasing, `Arrays.fill`, `Arrays.copyOf`, multidimensional arrays và `ArrayStoreException`.

## 17. Collection: cùng biến tham chiếu khác với bản sao cấu trúc

~~~java
java.util.List<String> original = new java.util.ArrayList<>();
original.add("A");
java.util.List<String> alias = original;
java.util.List<String> copy = new java.util.ArrayList<>(original);
~~~

Đây là snippet trong method. `alias` và `original` trỏ cùng List, nên các mutation cấu trúc của list hiện ở cả hai. `copy` có cấu trúc list riêng, nhưng các **element references** có thể tiếp tục chia sẻ với list cũ.

`List.copyOf(original)` tạo/nhận unmodifiable list, từ chối null elements, không bảo đảm deep copy và có thể tái sử dụng list immutable đủ điều kiện. Khi class nhận hoặc trả mutable collection, cần contract về **ownership** và defensive copying nếu muốn bảo vệ invariant. Bài aliasing đi sâu vào shallow/deep copy và chia sẻ các đối tượng con.

## 18. Từ khóa `this` cũng là tham chiếu, không phải object thứ hai

Bên trong constructor hoặc instance method:

~~~java
class Counter {
    private int value;

    Counter(int value) {
        this.value = value;
    }

    void add(int amount) {
        this.value += amount;
    }
}
~~~

`this` là một biểu thức chỉ **instance hiện tại**. Dòng `this.value = value`:

- Vế trái là field của object đang được khởi tạo.
- Vế phải `value` là tham số constructor cùng tên.
- Không tạo object mới chỉ vì dùng `this`.
- `this` trong mỗi instance method call biểu thị receiver của lời gọi đó.

Phân biệt `this` với `this(...)`: `this(...)` trong constructor là cú pháp **gọi constructor khác của cùng class**, không tạo thêm instance. Còn `new Counter(...)` mới là biểu thức yêu cầu tạo một instance mới.

## 19. Phạm vi biến và vòng đời object không phải một

Một biến cục bộ chỉ có thể được dùng theo **scope** của mã nguồn, nhưng object có thể tiếp tục được dùng sau khi method tạo nó kết thúc nếu có reference được truyền/return tới nơi khác.

Ví dụ minh họa:

~~~java
static Book create() {
    Book local = new Book("Java");
    return local;
}

// Ở caller:
Book result = create();
~~~

`local` là biến cục bộ của `create`. Khi method kết thúc, tên `local` không còn là biến cục bộ hoạt động của lần gọi đó. Nhưng giá trị reference đã được trả về; `result` có thể dùng **cùng Book object** sau khi method `create` kết thúc.

Do đó:

- “Biến ra khỏi scope” không có nghĩa “object bị hủy ngay”.
- Một object có thể được tham chiếu từ field, phần tử array, collection, biến cục bộ khác, static field hoặc dữ liệu khác.
- Một object không được giữ reference nào mà chương trình còn có thể dùng theo ngữ nghĩa thì có thể trở thành không còn reachable, nhưng **thời điểm GC thu hồi không được bảo đảm**.
- `System.gc()` không phải lệnh bắt buộc JVM thu hồi ngay một object cụ thể.
- Có thể có những tối ưu hóa runtime khiến mô hình cấp phát vật lý không đúng hoàn toàn với một sơ đồ “mỗi object luôn ở một vị trí heap cố định”; hãy dựa vào hành vi quan sát được và contract.

### Khi bỏ một reference, object có thể vẫn còn alias

~~~java
Book first = new Book("Java");
Book alias = first;
first = null;
~~~

`alias` vẫn tham chiếu Book object. Gán `first = null` không xóa Book object, cũng không làm `alias` trở thành null. Nếu code còn dùng `alias`, object vẫn cần có hành vi hợp lệ.

## 20. Static field có thể giữ tham chiếu lâu hơn bạn nghĩ

Một static field là thành viên của class runtime chứ không thuộc về một instance cụ thể. Nếu nó giữ reference tới object, object đó có thể tiếp tục reachable thông qua static field ngay cả khi các biến cục bộ ban đầu đã hết scope.

~~~java
class Cache {
    static Object latest;

    static void keep(Object item) {
        latest = item;
    }

    static void clear() {
        latest = null;
    }
}
~~~

Đây là class minh họa. `keep(item)` sao chép giá trị tham chiếu vào static field `latest`; không tạo object mới. `clear()` gán null vào static field, nhưng không ép JVM thu hồi ngay object cũ, và object đó có thể còn những reference khác.

Cần cẩn thận với static collections/cache không có giới hạn: nếu cứ giữ thêm object mà không có chính sách xóa phù hợp, chúng có thể giữ bộ nhớ lâu hơn dự kiến. Đây là một kiểu **memory retention** thường gặp trong ứng dụng chạy dài.

### Class loader và static state

Không nên nói “static field sống vĩnh viễn đến tận khi JVM tắt” như quy tắc tuyệt đối. Trạng thái static gắn với class runtime tương ứng; trong hệ thống dùng class loader động, class có thể được unload khi những điều kiện runtime thích hợp được thỏa. Với chương trình console nhỏ, có thể coi static reference là tồn tại khi class vẫn còn được dùng, nhưng đó là mô hình học tập đơn giản.

## 21. Khi truyền một biến tham chiếu vào constructor

Ví dụ:

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> members) {
        this.members = members;
    }
}
~~~

Constructor nhận **bản sao giá trị tham chiếu** tới list mà caller cung cấp; việc gán `this.members = members` khiến field giữ **cùng reference**. Nếu List mutable, caller có thể sửa cấu trúc list sau khi tạo Team, làm trạng thái Team thay đổi gián tiếp.

Nếu muốn tránh điều đó:

~~~java
class Team {
    private final java.util.List<String> members;

    Team(java.util.List<String> members) {
        this.members = java.util.List.copyOf(members);
    }

    java.util.List<String> members() {
        return members;
    }
}
~~~

Đây là **phiên bản thay thế** của class Team, không ghép hai định nghĩa cùng tên trong một package. `List.copyOf` giúp bảo vệ cấu trúc danh sách trong trường hợp này, với điều kiện đầu vào không null và không chứa phần tử null; nếu `members` null, phương thức ném `NullPointerException`. Không thể suy ra rằng các object phần tử mutable cũng tự trở thành immutable.

Tư duy đúng là: **Reference có thể được chia sẻ; quyền sửa object được chia sẻ cần được thiết kế và kiểm soát.**

## 22. Cách đọc một dòng code có reference để tránh nhầm lẫn

Khi gặp mã Java có nhiều biến và object, hãy xác định theo thứ tự:

1. **Biến nào?** Xem vế trái và kiểu khai báo: `Book book`, `Object value`, `List<Item> items`.
2. **Giá trị được gán là gì?** `null`, một reference từ biến khác, reference từ method return, hay kết quả `new`.
3. **Có object mới được tạo không?** Tìm biểu thức tạo object/factory/copy thực sự. Đừng coi phép gán là clone.
4. **Các biến nào đang alias cùng object?** Vẽ mũi tên theo từng phép gán.
5. **Câu lệnh sửa biến hay sửa object?** `a = b` khác `a.setValue(...)` và `a.field = ...`.
6. **Kiểu compile time và kiểu runtime có khác không?** Upcasting không tạo object mới; nó thay đổi khả năng truy cập thành viên qua reference.
7. **So sánh identity hay giá trị?** `==` cho tham chiếu hỏi cùng object; `equals` hỏi hợp đồng equality.
8. **Object mutable hay immutable?** Hai reference cùng String không có nghĩa một biến có thể thay nội dung String cũ.
9. **Có null không?** Kiểm tra các dereference trước khi dùng.
10. **Object có thể tiếp tục được giữ ở đâu?** Return values, fields, arrays, collections và static references đều có thể giữ object được dùng về sau.

### Ví dụ sơ đồ trước–sau

~~~java
Box a = new Box(1);
Box b = a;
b = new Box(2);
a.value = 3;
~~~

Giả sử `Box` cho phép truy cập field `value` ở ngữ cảnh này:

~~~text
Sau lệnh 1:
a ------> Box #1 { value=1 }

Sau lệnh 2:
a --+
    +----> Box #1 { value=1 }
b --+

Sau lệnh 3:
a ------> Box #1 { value=1 }
b ------> Box #2 { value=2 }

Sau lệnh 4:
a ------> Box #1 { value=3 }
b ------> Box #2 { value=2 }
~~~

Đây là mảnh mã minh họa; chỉ cần theo dõi **mỗi lần `new` và mỗi lần gán reference** là có thể vẽ chính xác quan hệ giữa biến và object.

## 23. Những lỗi hiểu sai thường gặp

| Nhận định sai hoặc thiếu | Giải thích chính xác |
| --- | --- |
| “Biến `Student s` chính là Student object.” | `s` là biến có kiểu reference; object là instance mà reference có thể trỏ tới. |
| “Khai báo `Student s;` tạo Student.” | Chỉ khai báo biến; chưa có `new`. |
| “`Student b = a;` copy mọi field.” | Nó sao chép reference, không tạo object mới. |
| “Hai object có cùng field thì `==` true.” | `==` so sánh reference identity, không so sánh field. |
| “`new` chỉ gán một giá trị vào biến.” | `new` yêu cầu tạo object; phép gán biến là thao tác khác. |
| “Gán `a = new X()` sửa object cũ của a.” | Nó thay giá trị reference của `a`; object cũ không tự bị chỉnh sửa. |
| “`String` là primitive vì dùng được literal.” | `String` là class, thuộc reference type. |
| “`Integer` lưu primitive y như `int`.” | `Integer` là wrapper reference type, có thể mang giá trị null ở biến tham chiếu. |
| “Java truyền object theo tham chiếu như C++ reference parameter.” | Java truyền **bản sao giá trị tham chiếu**. |
| “Gán lại tham số object làm biến caller trỏ object mới.” | Không; gán lại parameter chỉ đổi parameter. |
| “`final List<?>` không thể thay đổi phần tử.” | `final` ngăn gán lại biến/field reference; mutable object vẫn có thể bị sửa. |
| “Reference chính là địa chỉ RAM công khai.” | Java định nghĩa hành vi reference, không công bố representation là địa chỉ thô bắt buộc. |
| “Có `null` nghĩa đã có object rỗng.” | Null nghĩa không có object được reference đó chỉ tới. |
| “Biến local ra khỏi scope là object mất ngay.” | Object có thể có alias khác; GC không bảo đảm thu hồi ngay. |
| “`getClass()` và tên kiểu khai báo luôn giống nhau.” | Biến kiểu superclass có thể giữ reference tới subclass instance. |
| “`clone()` array là deep copy tất cả object phần tử.” | Array clone sao chép shallow; reference phần tử vẫn có thể dùng chung object. |
| “`equals()` luôn là identity.” | Class có thể override để định nghĩa equality theo giá trị; record/String có quy tắc riêng. |
| “`System.identityHashCode` là địa chỉ duy nhất.” | Identity hash không phải địa chỉ và không bảo đảm uniqueness. |

## 24. Bài tập luyện tập và đáp án

### Bài 1 — Đếm số object

~~~java
Book a = new Book("A");
Book b = a;
Book c = new Book("A");
b = c;
~~~

Giả sử mọi lần tạo object thành công. Có **hai** lần `new Book(...)` → **hai Book object**. Sau dòng cuối, `a` chỉ object #1, `b` và `c` chỉ object #2.

Kết quả:

- `a == b` → false.
- `b == c` → true.
- `a == c` → false.

### Bài 2 — Gán biến hay sửa field?

~~~java
Box first = new Box(1);
Box alias = first;
alias.value = 5;
alias = new Box(9);
~~~

Sau các dòng trên, object đầu có `value = 5` và vẫn được `first` tham chiếu. `alias` chuyển sang Box object mới có `value = 9`. `first.value` là 5, `alias.value` là 9. Dòng gán lại alias không phục hồi giá trị của object đầu.

### Bài 3 — Method nhận parameter

~~~java
static void replace(Box value) {
    value = new Box(100);
}

// Trong caller:
Box box = new Box(1);
replace(box);
~~~

`box` vẫn trỏ Box có `value = 1` vì method chỉ gán lại **parameter value**. Muốn caller đổi reference, một cách đúng là method `static Box replace(Box old) { return new Box(100); }` rồi caller gán `box = replace(box);`.

### Bài 4 — Null và mảng rỗng

~~~java
int[] missing = null;
int[] empty = new int[0];
int[] one = new int[1];
~~~

- `missing == null` → true; không được dùng `missing.length`.
- `empty.length` → 0.
- `one.length` → 1; phần tử `one[0]` mặc định 0.
- `empty == one` → false vì hai array objects khác nhau.

### Bài 5 — Mutable và immutable

~~~java
String s = "A";
String t = s;
s = s + "B";

StringBuilder x = new StringBuilder("A");
StringBuilder y = x;
x.append("B");
~~~

Sau đó `s` là `"AB"`, `t` là `"A"`; `x` và `y` đều thấy `"AB"`. `String` bất biến, `StringBuilder` mutable.

### Bài 6 — `final` có ngăn sửa object không?

~~~java
final java.util.ArrayList<String> names =
        new java.util.ArrayList<>();
names.add("Mai");
~~~

Hợp lệ: chỉ sửa object ArrayList, không gán lại biến `names`. Nếu viết `names = new ArrayList<>();` sau khi `names` đã được khởi tạo, compiler từ chối.

### Bài 7 — Hai kiểu equality

~~~java
record Key(int id) {}

Key a = new Key(7);
Key b = new Key(7);
Key c = a;
~~~

- `a == b` → false.
- `a.equals(b)` → true.
- `a == c` → true.
- `a.equals(c)` → true.

Các đoạn của bài 1–7 là **mảnh mã để ghép vào class/method thực hành**; các kiểu `Book`/`Box` cần có constructor/field thích hợp, không phải những chương trình độc lập.

## 25. Checklist hoàn thành

- [ ] Tôi biết phân biệt **biến có kiểu reference**, **giá trị reference** và **object instance**.
- [ ] Tôi biết khai báo biến không tự tạo object.
- [ ] Tôi biết `new Class(...)` hoàn tất bình thường cung cấp reference đến object mới.
- [ ] Tôi biết `a = b` sao chép reference, không tự sao chép object.
- [ ] Tôi vẽ được sơ đồ alias trước/sau những lần `new` và gán lại.
- [ ] Tôi phân biệt sửa biến reference và sửa field của object.
- [ ] Tôi hiểu `null` không trỏ đến object nào và khác với object rỗng.
- [ ] Tôi biết primitive type khác reference type, kể cả String, wrapper và mảng.
- [ ] Tôi có thể giải thích Java pass-by-value với method nhận object.
- [ ] Tôi phân biệt object identity (`==`) và equality theo hợp đồng (`equals`).
- [ ] Tôi hiểu `final` reference không đảm bảo object immutable.
- [ ] Tôi hiểu upcasting/cast có thể đổi cách nhìn kiểu nhưng không tạo bản sao object.
- [ ] Tôi biết `this` trong instance method chỉ object hiện tại, không tạo object khác.
- [ ] Tôi biết scope của biến và lifetime của object là hai khái niệm khác nhau.
- [ ] Tôi không suy luận địa chỉ object từ `identityHashCode` hoặc bắt JVM phải GC theo lịch định trước.
- [ ] Tôi tự chạy được các ví dụ Java 17+, đối chiếu output và giải thích đường tham chiếu của từng biến.

**Kết luận:** Biến tham chiếu **lưu một giá trị tham chiếu hoặc null**, chứ không phải chính object với tất cả field của nó. **Object** là thực thể có identity, kiểu runtime và trạng thái/hành vi; **reference** cho phép chương trình sử dụng object đó; **biến** chỉ là nơi lưu một giá trị reference theo quy tắc scope và gán. Khi luôn tách ba lớp khái niệm này, bạn sẽ hiểu chính xác phép `new`, aliasing, các tham số method, immutable objects, equality và vòng đời object trong Java.
