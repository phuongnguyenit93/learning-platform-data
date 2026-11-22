# Truyền `this` làm đối số và trả về `this` trong Java

Trong Java, từ khóa **`this`** là một biểu thức tham chiếu đến **đối tượng hiện tại** (*current object*) khi mã đang thực thi trong ngữ cảnh thể hiện (*instance context*). Ngoài cách dùng quen thuộc `this.field` để chỉ trường dữ liệu và `this.method()` để gọi phương thức, `this` còn có thể được sử dụng như **một giá trị tham chiếu**:

- **Truyền `this` làm đối số:** `otherMethod(this)` gửi tham chiếu đến đối tượng đang thực thi cho phương thức khác.
- **Trả về `this`:** `return this;` cung cấp chính tham chiếu đối tượng hiện tại cho bên gọi, thường để xây dựng API **fluent** với chuỗi lời gọi (*method chaining*).

Điểm quan trọng: cả hai thao tác đều **không tạo đối tượng mới** và **không sao chép toàn bộ đối tượng**. Java truyền đối số **theo giá trị**; khi đối số là `this`, giá trị được sao chép là **tham chiếu** đến đối tượng. Với `return this`, giá trị trả về là tham chiếu đến **chính đối tượng hiện tại**.

Ví dụ giới thiệu:

```java
class Profile {
    String name;

    Profile(String name) {
        this.name = name;
    }

    void introduceTo(Printer printer) {
        printer.print(this);   // Truyền đối tượng Profile hiện tại
    }

    Profile rename(String newName) {
        this.name = newName;
        return this;          // Trả lại cùng đối tượng Profile
    }
}

class Printer {
    void print(Profile profile) {
        System.out.println(profile.name);
    }
}
```

Nếu `Profile p = new Profile("An");`, sau đó gọi `p.introduceTo(new Printer());` thì `Printer.print` nhận tham chiếu đến `p`. Câu lệnh `p.rename("Bình")` sửa tên rồi trả về **cùng thể hiện `p`**, cho phép viết `p.rename("Bình").introduceTo(new Printer());`.

Đoạn trên minh họa các khai báo lớp; chương trình hoàn chỉnh cùng lệnh biên dịch và stdout được trình bày bên dưới.

## 1. `this` là gì? Phân biệt các cú pháp có từ khóa `this`

Cùng một từ khóa nhưng các dạng viết phục vụ các mục đích khác nhau:

| Cú pháp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `this` | Tham chiếu đến đối tượng hiện tại | `register(this)` |
| `this.field` | Truy cập field của đối tượng hiện tại | `this.name = name` |
| `this.method()` | Gọi instance method qua receiver hiện tại | `this.validate()` |
| `this(arguments)` | Gọi **constructor khác trong cùng lớp** | `this("Mặc định", 0);` |
| `return this;` | Trả tham chiếu đối tượng hiện tại từ method phù hợp | `Builder step() { return this; }` |
| `Outer.this` | Chỉ thể hiện `Outer` bao ngoài từ một inner class phù hợp | `Printer.print(Outer.this)` |

**Không được đồng nhất `this` và `this(...)`:** `this` đứng độc lập là biểu thức tham chiếu; `this(...)` là cú pháp **constructor invocation**, phải tuân thủ các quy tắc vị trí đặc biệt của constructor (trong Java 17, lời gọi `this(...)` tường minh phải là câu lệnh đầu tiên).

Trong **instance method** và **constructor của một lớp thông thường**, `this` chỉ đối tượng hiện tại. Trong **static method**, không tồn tại đối tượng hiện tại, vì vậy **không dùng được `this`**.

`this` cũng không phải tên một biến có thể được gán lại:

```java
// SAI:
this = anotherObject;
```

Bạn có thể thay đổi trạng thái đối tượng qua `this.field = value` nếu field cho phép, nhưng không thể làm `this` “trỏ sang” một đối tượng khác.

## 2. Truyền `this` làm đối số: nguyên lý cốt lõi

Khi một instance method của lớp `A` gọi:

```java
receiver.process(this);
```

thì:

1. Compiler kiểm tra phương thức `process` có thể được gọi, có thể truy cập được, và kiểu của `this` có thể chuyển sang kiểu tham số tương ứng.
2. Giá trị của biểu thức `this` là **tham chiếu đến đối tượng `A` đang thực thi phương thức**.
3. Phương thức `process` nhận **một bản sao giá trị tham chiếu** đó qua biến tham số hình thức.
4. Đối tượng trong lời gọi ban đầu và biến tham số mới có thể là **cùng một đối tượng**.
5. Việc phương thức nhận đối số **gán lại biến tham số** không gán lại `this` hay biến tham chiếu của caller; việc **sửa field của đối tượng được cùng tham chiếu** có thể được quan sát từ nhiều nơi.

Chẳng hạn:

```java
class Document {
    String title;

    void sendTo(Inspector inspector) {
        inspector.inspect(this);
    }
}

class Inspector {
    void inspect(Document document) {
        System.out.println(document.title);
    }
}
```

`Document.sendTo` truyền đúng đối tượng đang nhận lời gọi vào `Inspector.inspect`. Không cần tạo một `new Document()` chỉ để cung cấp thông tin hiện tại.

### `this` không chỉ dùng cho đối số có kiểu trùng lớp

Một tham số có thể nhận `this` nếu kiểu của nó tương thích:

```java
class Task implements Runnable {
    @Override
    public void run() {
        System.out.println("Đang chạy");
    }

    void submit(Executor executor) {
        executor.execute(this); // this có thể dùng như Runnable
    }
}

interface Executor {
    void execute(Runnable job);
}
```

`Task` triển khai `Runnable`, do đó tham chiếu `this` trong instance method của `Task` được dùng như đối số kiểu `Runnable`. Tùy thiết kế, tham số còn có thể là superclass, interface hoặc `Object`.

Ví dụ này là **khai báo minh họa**: `Executor` là một interface tự định nghĩa trong đoạn code, không phải tên một lớp cụ thể phải có sẵn trong JDK. Không có `main` để chạy riêng.

## 3. Chương trình hoàn chỉnh: đối tượng tự truyền mình cho đối tượng khác

Lưu vào **`PassThisDemo.java`**:

```java
class Cart {
    private int quantity;

    Cart(int quantity) {
        this.quantity = quantity;
    }

    void add(int amount) {
        quantity += amount;
    }

    int quantity() {
        return quantity;
    }

    void sendTo(Auditor auditor) {
        auditor.inspect(this);
    }
}

class Auditor {
    void inspect(Cart cart) {
        cart.add(2);                   // Sửa đối tượng được chia sẻ
        cart = new Cart(99);           // Chỉ gán lại biến tham số
        System.out.println("Trong auditor: " + cart.quantity());
    }
}

public class PassThisDemo {
    public static void main(String[] args) {
        Cart cart = new Cart(3);
        Auditor auditor = new Auditor();

        cart.sendTo(auditor);
        System.out.println("Ngoài auditor: " + cart.quantity());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 PassThisDemo.java
java PassThisDemo
```

**Stdout chính xác:**

```text
Trong auditor: 99
Ngoài auditor: 5
```

**Vì sao kết quả khác nhau?**

- `cart.sendTo(auditor)` chạy trên đối tượng `Cart` có `quantity = 3`.
- Trong `Cart.sendTo`, `this` tham chiếu **chính đối tượng `Cart` đó**.
- Khi `Auditor.inspect(this)` chạy, biến tham số `cart` của `inspect` ban đầu cũng trỏ đến đối tượng `Cart` này.
- `cart.add(2)` sửa trạng thái đối tượng gốc: `quantity` thành `5`.
- `cart = new Cart(99)` **gán lại riêng biến tham số** `cart` trong `inspect`. Nó không sửa tham chiếu `this` bên `Cart.sendTo`, cũng không sửa biến `cart` ở `PassThisDemo.main`.
- Dòng trong `Auditor.inspect` in số lượng của đối tượng mới `99`; sau khi lời gọi kết thúc, `main` vẫn giữ đối tượng gốc có số lượng `5`.

Sơ đồ tham chiếu:

```text
Trước khi inspect gán lại tham số:

main.cart ─────────────────────┐
                               ├──> Cart #1 { quantity: 5 }
inspect.cart (bản sao ref) ────┘

Sau khi inspect thực hiện cart = new Cart(99):

main.cart ─────────────────────────> Cart #1 { quantity: 5 }
inspect.cart ──────────────────────> Cart #2 { quantity: 99 }
```

`#1` và `#2` chỉ là nhãn minh họa, không phải địa chỉ bộ nhớ JVM.

**Kết luận:** truyền `this` là **pass-by-value của tham chiếu**, không phải pass-by-reference của biến. Muốn giữ lại một đối tượng mới, phương thức nhận cần **trả về tham chiếu** rồi caller tự quyết định có gán vào biến bên ngoài hay không.

## 4. Truyền `this` và truyền các field của `this` khác nhau thế nào?

Xét hai API:

```java
static void printName(String name) {
    System.out.println(name);
}

static void printPerson(Person person) {
    System.out.println(person.name());
}
```

Và một lớp `Person`:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    void report() {
        Reporter.printName(this.name); // Truyền giá trị field String
        Reporter.printPerson(this);    // Truyền tham chiếu Person hiện tại
    }
}
```

Ở đây giả sử hai phương thức `printName`/`printPerson` là `static` của lớp `Reporter`. Những khai báo tách rời nhằm minh họa; không phải nguyên một tệp chạy được.

Khác biệt:

- `printName(this.name)` chỉ cung cấp **giá trị field `name`** cho bên nhận. Bên nhận không mặc nhiên có quyền truy cập các field khác của `Person`.
- `printPerson(this)` cung cấp **tham chiếu tới toàn bộ đối tượng**. Bên nhận có thể gọi những phương thức công khai/khả dụng của đối tượng theo kiểu tham số, và có thể thay đổi trạng thái nếu API cho phép.
- Truyền một tham chiếu không biến field `private` thành `public`. Bên nhận vẫn phải đi qua các quyền truy cập thông thường của Java.

**Thiết kế API:** nếu bên nhận chỉ cần `name`, ưu tiên truyền `String` hoặc một dữ liệu giới hạn khi phù hợp; không truyền cả `this` nếu việc đó khiến bên nhận có khả năng giữ hoặc thay đổi đối tượng ngoài ý muốn.

## 5. Truyền `this` để thông báo hoặc cộng tác với đối tượng khác

Một số trường hợp truyền `this` hợp lý:

- **Visitor/processor:** đối tượng hiện tại tự giao mình cho một bộ xử lý có thể truy cập qua interface.
- **Observer hoặc event source:** gửi tham chiếu nguồn phát sự kiện cho listener.
- **Hai chiều quan hệ:** đối tượng thêm mình vào một container hoặc nhóm.
- **Command/callback:** truyền tham chiếu đối tượng hiện tại cho thành phần điều phối.
- **Đăng ký sau khi khởi tạo:** cho một bộ đăng ký quản lý đối tượng đã tạo xong.

Ví dụ visitor đơn giản, tệp **`VisitorThisDemo.java`**:

```java
interface Printable {
    String text();
    void accept(PrintVisitor visitor);
}

class Note implements Printable {
    private final String content;

    Note(String content) {
        this.content = content;
    }

    @Override
    public String text() {
        return content;
    }

    @Override
    public void accept(PrintVisitor visitor) {
        visitor.visit(this);
    }
}

class PrintVisitor {
    void visit(Printable source) {
        System.out.println("Visit: " + source.text());
    }
}

public class VisitorThisDemo {
    public static void main(String[] args) {
        Printable note = new Note("Java");
        PrintVisitor visitor = new PrintVisitor();
        note.accept(visitor);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 VisitorThisDemo.java
java VisitorThisDemo
```

**Stdout:**

```text
Visit: Java
```

`Note.accept` gọi `visitor.visit(this)` để cung cấp **đối tượng `Note` hiện tại**. Phương thức `visit` nhận tham số kiểu interface `Printable`, nên lời gọi hợp lệ. Visitor có thể sử dụng `source.text()` mà không cần biết các field private trong `Note`.

**Chú ý về phạm vi nội dung:** đây là ví dụ phối hợp hai đối tượng, chưa phải cài đặt đầy đủ của *Visitor Design Pattern* với nhiều overload `visit(Type)`. Nếu dùng overload chuyên biệt theo lớp con, phải xem thêm cơ chế overload resolution ở compile time; riêng cú pháp truyền `this` vẫn như nhau.

## 6. Trả về `this`: chính đối tượng hiện tại được trả về

Một instance method có thể trả `this` nếu kiểu trả về được khai báo **tương thích với kiểu tham chiếu của đối tượng hiện tại**.

Ví dụ:

```java
class Counter {
    private int value;

    Counter increment() {
        value++;
        return this;
    }

    int getValue() {
        return value;
    }
}
```

Với `Counter counter = new Counter();`:

```java
Counter result = counter.increment();
System.out.println(result == counter); // true
```

`increment()` làm tăng field `value` của đối tượng `counter` và trả về **cùng tham chiếu** `counter`. Toán tử `==` trên hai biến tham chiếu trả `true` vì chúng chỉ cùng một đối tượng.

**`return this` không gọi constructor**, không sao chép đối tượng, không tự biến đối tượng thành bất biến, và cũng không bảo đảm rằng phương thức có tác dụng “xây dựng” gì nếu người viết không cập nhật trạng thái trước khi trả về.

### 6.1. Điều kiện kiểu trả về

Các khai báo sau có thể hợp lệ:

```java
class Base {
    Base self() {
        return this;
    }

    Object asObject() {
        return this;
    }
}
```

Trong lớp `Base`, `this` có kiểu phù hợp với `Base` và `Object`. Nếu `Base` triển khai interface `Named`, một instance method của `Base` có thể trả `Named` với `return this;`.

Ngược lại:

```java
class InvalidReturn {
    void self() {
        // return this; // SAI: void method không thể trả về giá trị
    }

    int number() {
        // return this; // SAI: tham chiếu InvalidReturn không là int
        return 0;
    }
}
```

Kiểu trả về phải phù hợp **tại compile time**, không chỉ dựa trên việc runtime đang dùng một lớp con nào đó.

### 6.2. `return this` khác `return new Type(...)`

| Cách viết | Kết quả | Ứng dụng |
| --- | --- | --- |
| `return this;` | Trả **chính đối tượng receiver hiện tại** | Fluent API thay đổi đối tượng tại chỗ |
| `return new Type(...);` | Trả một đối tượng mới do `new` tạo | Copy có chỉnh sửa, đối tượng bất biến, factory |
| `return other;` | Trả đối tượng mà biến `other` tham chiếu | Lựa chọn/ủy quyền trả về |
| `return null;` | Trả tham chiếu null nếu kiểu trả về cho phép | Cần hợp đồng rõ ràng; dễ gây lỗi khi chain |
| `return this.field;` | Trả giá trị một field của đối tượng | Getter hoặc trả dữ liệu liên quan |

Đừng mặc định phương thức có tên `withName(...)` là immutable: phải xem implementation dùng `return this` hay tạo đối tượng mới.

## 7. Method chaining: lợi ích điển hình của `return this`

**Method chaining** là cách gọi liên tiếp các phương thức trên giá trị do phương thức trước trả về. Với những method trả `this`, mỗi kết quả trung gian vẫn là **cùng một đối tượng**.

Ví dụ:

```java
draft.to("An").body("Chào").append(" Java").show();
```

Chuỗi lời gọi được hiểu tương đương về thứ tự tác động với:

```java
draft.to("An");
draft.body("Chào");
draft.append(" Java");
draft.show();
```

Vì mỗi method cập nhật trả lại `draft`, lời gọi tiếp theo có thể tiếp tục dùng receiver ấy.

### 7.1. Chương trình Java 17 hoàn chỉnh: fluent interface

Lưu toàn bộ vào **`FluentDemo.java`**:

```java
class MessageDraft {
    private String recipient = "";
    private String content = "";

    MessageDraft to(String recipient) {
        this.recipient = recipient;
        return this;
    }

    MessageDraft body(String content) {
        this.content = content;
        return this;
    }

    MessageDraft append(String suffix) {
        this.content += suffix;
        return this;
    }

    String build() {
        return "To: " + recipient + " | Body: " + content;
    }
}

public class FluentDemo {
    public static void main(String[] args) {
        MessageDraft draft = new MessageDraft();

        MessageDraft same = draft.to("An")
                .body("Chào")
                .append(" Java");

        System.out.println(same == draft);
        System.out.println(draft.build());

        same.append(" 17");
        System.out.println(draft.build());
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 FluentDemo.java
java FluentDemo
```

**Stdout chính xác:**

```text
true
To: An | Body: Chào Java
To: An | Body: Chào Java 17
```

Phân tích:

1. `new MessageDraft()` tạo **một thể hiện duy nhất** và lưu tham chiếu vào `draft`.
2. `draft.to("An")` cập nhật field `recipient` rồi `return this;`.
3. Kết quả của `to` được dùng làm receiver cho `body`; `body` cập nhật field `content` rồi cũng `return this;`.
4. `append(" Java")` sửa tiếp `content` và trả cùng đối tượng; vì vậy `same == draft` là `true`.
5. `same.append(" 17")` sửa trạng thái **chính đối tượng của `draft`**; dòng in cuối phản ánh thay đổi đó.

**Quan trọng:** đoạn mã trên là **mutable fluent API**. Chain chỉ thay đổi các field của **một đối tượng**. Nếu cần giữ phiên bản trước để dùng riêng, phải tạo bản sao hoặc thiết kế immutable API trả object mới.

### 7.2. Tại sao không cần viết `new` trong từng bước?

Vì `return this` duy trì cùng tham chiếu, mỗi bước có thể viết ngắn gọn:

```java
MessageDraft draft = new MessageDraft();
draft.to("An").body("Hello");
```

Không có `new MessageDraft()` ẩn trong `to` hoặc `body` của ví dụ. Java cũng không ngầm sao chép đối tượng khi nhận kết quả `return this`.

Điều này thường hữu ích với builder cấu hình, bộ xử lý trạng thái tuần tự hoặc đối tượng cần nhiều thao tác liên tiếp. Tuy vậy, việc trả cùng thể hiện có thể dẫn đến **chia sẻ mutable state** nếu nhiều phần mã cùng giữ một tham chiếu.

## 8. Một số thiết kế thực tế: trả `this` hay trả kết quả khác?

Không phải method nào cũng nên trả `this`.

| Hành vi | Return type hợp lý | Lý do |
| --- | --- | --- |
| Thay đổi cấu hình và cho phép gọi tiếp | Kiểu lớp hiện tại, `return this` | Fluent mutable |
| Chỉ thực thi một thao tác, bên gọi không cần chain | `void` | API đơn giản |
| Đọc giá trị | `String`, `int`, kiểu phù hợp | Caller cần kết quả |
| Tạo một phiên bản độc lập với thay đổi | Kiểu lớp, `return new ...` | Immutable/copy style |
| Kiểm tra thành công/thất bại | `boolean` hoặc kiểu kết quả | Trả thông tin nghiệp vụ |
| Kết thúc builder để tạo sản phẩm | Kiểu sản phẩm | `build()` không nhất thiết trả `this` |
| Tìm kiếm | Kiểu phần tử/`Optional<T>` | Trả dữ liệu được tìm thấy |

Ví dụ một builder có thể có:

```java
Builder setName(String name) {
    this.name = name;
    return this;
}

Product build() {
    return new Product(name);
}
```

Đây là **hai phương thức minh họa** trong một lớp `Builder` được giả định có field `name` và lớp `Product` phù hợp, không phải đoạn tự chạy. Các setter trả về `this` để chain; `build()` trả về một **đối tượng sản phẩm khác**, vì vậy `build()` không nên tự động dùng `return this` nếu kiểu sản phẩm khác.

### 8.1. Có nên đổi mọi setter `void` thành trả `this`?

Không bắt buộc. Một setter `void` đơn giản có thể rất rõ ràng:

```java
void setName(String name) {
    this.name = name;
}
```

Đổi thành:

```java
Person setName(String name) {
    this.name = name;
    return this;
}
```

chỉ hữu ích nếu API thực sự muốn hỗ trợ chuỗi thao tác và kiểu `Person` phù hợp. Với thư viện bên ngoài, thay đổi return type còn liên quan tương thích nhị phân/API; không nên tự tiện thay đổi hợp đồng đã công bố.

## 9. Phân biệt mutable fluent với immutable “with” methods

Hai cách viết có thể **trông giống nhau tại nơi gọi** nhưng có ngữ nghĩa khác hẳn.

### Mutable: `return this`

```java
class MutablePoint {
    int x;

    MutablePoint move(int delta) {
        x += delta;
        return this;
    }
}
```

`point.move(2).move(3);` cập nhật **cùng một đối tượng** hai lần.

### Immutable: tạo đối tượng mới

```java
final class ImmutablePoint {
    private final int x;

    ImmutablePoint(int x) {
        this.x = x;
    }

    ImmutablePoint move(int delta) {
        return new ImmutablePoint(x + delta);
    }

    int x() {
        return x;
    }
}
```

`original.move(2)` trả về đối tượng mới với `x` được cập nhật, còn `original` không đổi. Mặc dù đều có thể chain, dạng immutable phải được **sử dụng kết quả trả về**.

### Ví dụ độc lập kiểm tra danh tính đối tượng

Lưu thành **`MutableImmutableDemo.java`**:

```java
class MutablePoint {
    private int x;

    MutablePoint(int x) {
        this.x = x;
    }

    MutablePoint move(int delta) {
        this.x += delta;
        return this;
    }

    int x() {
        return x;
    }
}

final class ImmutablePoint {
    private final int x;

    ImmutablePoint(int x) {
        this.x = x;
    }

    ImmutablePoint move(int delta) {
        return new ImmutablePoint(x + delta);
    }

    int x() {
        return x;
    }
}

public class MutableImmutableDemo {
    public static void main(String[] args) {
        MutablePoint mutable = new MutablePoint(1);
        MutablePoint changed = mutable.move(2);

        ImmutablePoint immutable = new ImmutablePoint(1);
        ImmutablePoint next = immutable.move(2);

        System.out.println(mutable.x());
        System.out.println(mutable == changed);
        System.out.println(immutable.x());
        System.out.println(next.x());
        System.out.println(immutable == next);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 MutableImmutableDemo.java
java MutableImmutableDemo
```

Stdout:

```text
3
true
1
3
false
```

Kết quả cho thấy `return this` giữ **identity** của đối tượng mutable, còn `return new ImmutablePoint(...)` tạo đối tượng khác và không đổi đối tượng ban đầu.

**Một lời gọi chain chưa đủ để suy ra** API có mutable hay immutable. Hãy xem thân method và hợp đồng được ghi trong tài liệu.

## 10. `return this` và kiểu khai báo của receiver khi có kế thừa

Trong kế thừa, `this` biểu thị **đối tượng runtime hiện tại**, nhưng **kiểu trả về khai báo** của một phương thức quyết định những lời gọi tiếp theo có thể viết ở compile time.

Ví dụ:

```java
class BaseBuilder {
    BaseBuilder configure() {
        return this;
    }
}

class ExtendedBuilder extends BaseBuilder {
    void extra() {
        System.out.println("extra");
    }
}
```

Với:

```java
ExtendedBuilder builder = new ExtendedBuilder();
BaseBuilder result = builder.configure();
System.out.println(result == builder); // true

// builder.configure().extra(); // SAI: configure() được khai báo trả BaseBuilder
```

Dù đối tượng thực tế là `ExtendedBuilder` và `return this` trả cùng tham chiếu, **kiểu tĩnh của biểu thức `builder.configure()` vẫn là `BaseBuilder`**; lớp `BaseBuilder` không khai báo method `extra`.

### 10.1. Covariant return khi override

Lớp con có thể override method với kiểu trả về tham chiếu **cụ thể hơn** nếu các quy tắc Java cho phép:

```java
class BaseBuilder {
    BaseBuilder configure() {
        return this;
    }
}

class ExtendedBuilder extends BaseBuilder {
    @Override
    ExtendedBuilder configure() {
        super.configure();
        return this;
    }

    void extra() {
        System.out.println("extra");
    }
}
```

Với biến `ExtendedBuilder builder`, lời gọi `builder.configure().extra();` giờ **hợp lệ** vì phiên bản override khai báo trả `ExtendedBuilder`. Nếu receiver chỉ được khai báo kiểu `BaseBuilder`, compiler vẫn xét API nhìn thấy qua `BaseBuilder`.

**Không nhầm trả về `this` với chọn overload động:** `return this` không thay đổi nguyên tắc Java giải quyết overload theo kiểu compile-time của đối số/receiver. Để có fluent hierarchy phức tạp, có thể cần thiết kế kiểu trả về cụ thể hoặc generic self-type; không nên lạm dụng cast để ép compiler.

### 10.2. Generic self-type (kiến thức mở rộng)

Một số thư viện dùng dạng *self-referential generic* để giữ kiểu fluent cho lớp con:

```java
abstract class BaseBuilder<T extends BaseBuilder<T>> {
    abstract T self();

    T configured() {
        // Thay đổi cấu hình chung.
        return self();
    }
}

final class ConcreteBuilder extends BaseBuilder<ConcreteBuilder> {
    @Override
    ConcreteBuilder self() {
        return this;
    }

    ConcreteBuilder special() {
        return this;
    }
}
```

Nhờ trả `T`, phương thức `configured()` có thể cho ra kiểu phù hợp với `ConcreteBuilder` ở nơi dùng. Đây là đoạn khai báo minh họa, không có `main`.

**Giới hạn:** generic self-type là một mẫu thiết kế hữu ích nhưng có thể tăng độ phức tạp và cần hợp đồng chặt chẽ giữa lớp cha/con. Với builder nhỏ, dùng một lớp cụ thể và `return this` thường đơn giản hơn.

## 11. Dùng `this` trong constructor: lưu ý khi đưa ra bên ngoài

Trong constructor, `this` tham chiếu tới object **đang khởi tạo**, nhưng object đó có thể chưa đạt invariant cuối cùng. Lệnh `this.name = name;` chỉ cập nhật state tại chỗ; còn `registry.add(this)`, `executor.submit(this::run)` hoặc đăng ký callback có thể **công bố receiver trước khi constructor hoàn tất**.

Ví dụ không nên dùng trong constructor:

~~~java
class EarlyListener {
    private String token;

    EarlyListener(Registry registry) {
        registry.register(this);  // Có thể bị gọi lại ngay
        token = "READY";
    }
}
~~~

Đây là snippet minh họa; `Registry` là collaborator giả định và chưa khai báo để chạy riêng. Nếu registry dùng reference khi `token` chưa gán, nó có thể thấy null. Ưu tiên **khởi tạo đủ state trước**, sau đó đăng ký trong factory hoặc lifecycle method; nếu liên quan nhiều thread, còn phải xem xét cách **công bố an toàn**. Bài **Rủi ro để this thoát ra khi khởi tạo chưa hoàn tất** giải thích đầy đủ callback đồng bộ, dynamic dispatch ở constructor, `final` fields và Java Memory Model.

## 12. Không nhầm biểu thức `this` với ngữ cảnh static hoặc constructor chaining

| Cách viết | Hợp lệ khi nào? | Ý nghĩa |
| --- | --- | --- |
| `processor.accept(this)` | Trong instance context, kiểu tương thích | Chuyển **tham chiếu object hiện tại** cho `accept` |
| `return this;` | Trong instance method có kiểu trả về tương thích | Trả object hiện tại |
| `this(field)` | Ở vị trí explicit constructor invocation hợp lệ | Gọi **constructor khác cùng lớp**, không truyền receiver `this` |
| `this.field` | Có current instance hợp lệ | Truy cập field của object hiện tại |
| `return this;` trong constructor | Không hợp lệ | Constructor không trả một giá trị tham chiếu |
| `this` trong static method | Không hợp lệ | Không có current receiver |

Ở Java 17, lời gọi constructor `this(...)` hoặc `super(...)` tường minh phải ở **đầu thân constructor**; không thể đặt lệnh thường trước đó hoặc dựa vào receiver chưa hoàn tất khởi tạo trong argument expression. Bài **Phân biệt this, this() và tên lớp** trình bày quy tắc chaining cùng ví dụ compile-time.

## 13. `this` trong inner class và `Outer.this`

Trong một **non-static inner class**, `this` biểu thị **inner instance**; khi muốn truyền outer object, dùng qualified `Outer.this` nếu ngữ cảnh cho phép:

~~~java
class Outer {
    class Inner {
        void send(Receiver receiver) {
            receiver.accept(this);       // Inner object
            receiver.accept(Outer.this); // Outer object
        }
    }

    interface Receiver {
        void accept(Object value);
    }
}
~~~

Cùng là thao tác “truyền this” nhưng hai biểu thức chọn **hai receiver khác nhau**, nên callback nhận object nào phụ thuộc cú pháp. Static nested class không tự có enclosing `Outer.this`. Để hiểu nhiều tầng enclosing instances, hãy học bài chuyên sâu **Truy cập đối tượng bao ngoài bằng Outer.this**.

## 14. `this` trong lambda và anonymous class

Lambda **không sinh một receiver `this` mới**: `this` bên trong lambda mang nghĩa của ngữ cảnh bao quanh. Anonymous class lại có **instance riêng**, nên `this` trong body của nó là anonymous object:

~~~java
class Owner {
    Runnable lambda() {
        return () -> System.out.println(this == Owner.this);
    }

    Runnable anonymous() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println(this == Owner.this);
            }
        };
    }
}
~~~

Nếu gọi `new Owner().lambda().run()`, in `true`; với `anonymous().run()`, in `false`. Vì vậy code truyền `this` từ lambda hoặc anonymous callback có thể truyền **hai object khác nhau**. Trong static context, lambda không tự cấp thêm receiver `this`. Các ngoại lệ về lexical enclosing/qualified `this` được trình bày ở bài riêng.

## 15. `return this` trong interface default method

Một phương thức **default** của interface có thân và có thể sử dụng `this` khi được gọi trên đối tượng triển khai.

```java
interface Named {
    String name();

    default Named printName() {
        System.out.println(name());
        return this;
    }
}

class User implements Named {
    private final String value;

    User(String value) {
        this.value = value;
    }

    @Override
    public String name() {
        return value;
    }
}
```

`Named.printName()` trả về **chính đối tượng triển khai hiện tại**, nhưng kiểu trả về khai báo là `Named`. Khi chain tiếp, compiler chỉ cho phép các method có sẵn theo kiểu tĩnh `Named` (hoặc kiểu cụ thể hơn có thể chứng minh theo ngữ cảnh).

Ví dụ hoàn chỉnh **`DefaultThisDemo.java`**:

```java
interface Named {
    String name();

    default Named printName() {
        System.out.println(name());
        return this;
    }
}

class User implements Named {
    private final String value;

    User(String value) {
        this.value = value;
    }

    @Override
    public String name() {
        return value;
    }
}

public class DefaultThisDemo {
    public static void main(String[] args) {
        User user = new User("An");
        Named same = user.printName();
        System.out.println(same == user);
        same.printName();
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 DefaultThisDemo.java
java DefaultThisDemo
```

Stdout:

```text
An
true
An
```

Đây là ví dụ có ý nghĩa thực tế: interface có thể cung cấp method mặc định **vừa làm thao tác vừa trả lại receiver**. Việc trả interface type giúp giữ hợp đồng chung; nếu cần chain method chuyên biệt của `User`, phải thiết kế API hoặc kiểu trả về phù hợp.

## 16. Lỗi compile-time phổ biến khi truyền hoặc trả `this`

| Đoạn mã/tình huống | Lỗi hoặc hiểu nhầm | Cách xử lý |
| --- | --- | --- |
| `static void f() { use(this); }` | Không có `this` trong static context | Truyền đối tượng được cung cấp qua biến/tham số |
| `void f() { return this; }` | `void` không cho trả giá trị | Đổi kiểu trả về phù hợp hoặc dùng `return;` |
| `int f() { return this; }` | `this` là tham chiếu, không chuyển thành `int` | Trả field hoặc biểu thức kiểu `int` |
| `Constructor() { return this; }` | Constructor không có return type | Dùng instance method hoặc factory trả đối tượng |
| `target.use(this)` khi `use` nhận kiểu không tương thích | Không có overload phù hợp | Sửa kiểu tham số, interface hoặc API |
| `this = other;` | `this` không là biến có thể gán lại | Gán field hoặc biến bình thường |
| `this(...)` đặt sau câu lệnh khác trong constructor Java 17 | Vi phạm vị trí constructor invocation | Đặt `this(...)` làm câu lệnh đầu tiên |
| `return this;` nhưng kỳ vọng đối tượng mới | `this` là cùng receiver | Dùng `new`/copy factory nếu muốn bản sao |
| `Base fluent() { return this; }` rồi `sub.fluent().special()` | Kiểu tĩnh kết quả là `Base` | Dùng covariant return hoặc API self-type phù hợp |
| Truyền `this` từ constructor cho listener | Nguy cơ công bố object chưa hoàn thiện | Đăng ký sau khởi tạo hoặc thiết kế factory |
| Gọi fluent method trên đối tượng dùng chung | Mutating API thay đổi đối tượng cho mọi alias | Copy/immutable style nếu cần trạng thái độc lập |
| Truyền `this` tới nơi giữ tham chiếu dài hạn | Object có thể bị giữ sống quá lâu | Quản lý vòng đời/callback và hủy đăng ký |

Đọc lỗi `javac` theo **ngữ cảnh**: `this` đang nằm trong static hay instance context? Đối số có kiểu phù hợp không? Phương thức có kiểu trả về nào? Với method chaining, hãy xem **kiểu khai báo trả về**, không chỉ lớp thực tế của đối tượng.

## 17. Các bài tự luyện có đáp án

### Bài 1 — Danh tính đối tượng sau `return this`

```java
class Box {
    int value;

    Box add(int amount) {
        value += amount;
        return this;
    }
}
```

Nếu:

```java
Box box = new Box();
Box result = box.add(3).add(5);
System.out.println(result == box);
System.out.println(box.value);
```

**Đáp án:**

```text
true
8
```

Cả hai lời gọi `add` hoạt động trên **cùng một thể hiện `Box`**; `return this` duy trì identity.

### Bài 2 — Truyền `this` có thay đổi biến ở caller không?

```java
class Sender {
    int count = 1;

    void submit(Receiver receiver) {
        receiver.accept(this);
    }
}

class Receiver {
    void accept(Sender sender) {
        sender.count = 4;
        sender = new Sender();
        sender.count = 9;
    }
}
```

Trong một method:

```java
Sender original = new Sender();
original.submit(new Receiver());
System.out.println(original.count);
```

**Đáp án:** in `4`. Tham số `sender` ban đầu cùng tham chiếu đối tượng `original`, nên gán field `count = 4` có tác dụng. Gán lại `sender = new Sender()` chỉ thay đổi biến tham số, không chuyển `original` sang đối tượng mới.

### Bài 3 — Có thể dùng `return this` trong static method không?

```java
class Item {
    static Item self() {
        // return this;
        return new Item();
    }
}
```

**Đáp án:** không. `static Item self()` không có đối tượng `this`; cách viết được uncomment trong ví dụ sử dụng `new Item()` là trả một đối tượng mới, không phải trả đối tượng hiện tại của static method.

### Bài 4 — Phân biệt `this(...)` và `return this`

```java
class Node {
    int value;

    Node() {
        this(10);
    }

    Node(int value) {
        this.value = value;
    }

    Node increment() {
        value++;
        return this;
    }
}
```

**Đáp án:**

- `this(10);` trong constructor `Node()` gọi **constructor `Node(int)`** của cùng lớp.
- `this.value = value;` gán field.
- `return this;` trong `increment()` trả **chính đối tượng `Node` hiện tại**.
- `new Node().increment()` tạo một `Node` có giá trị khởi tạo `10`, tăng lên `11` rồi cho ra cùng tham chiếu đối tượng đó.

### Bài 5 — Mutable hay immutable?

```java
class Config {
    String value;

    Config withValue(String newValue) {
        this.value = newValue;
        return this;
    }
}
```

**Đáp án:** phương thức này **mutable**, bất chấp tên `withValue`. Nó sửa field `value` trên chính object trước khi `return this`. Nếu muốn một API immutable, cần tạo và trả đối tượng mới, đồng thời thiết kế tránh thay đổi object cũ.

### Bài 6 — Kiểu tĩnh sau fluent method

```java
class Parent {
    Parent chain() {
        return this;
    }
}

class Child extends Parent {
    void childOnly() {
    }
}
```

Với `Child child = new Child();`:

- `child.chain();` → hợp lệ.
- `Parent p = child.chain();` → hợp lệ.
- `child.chain().childOnly();` → **lỗi biên dịch** vì `chain()` khai báo trả kiểu `Parent`.

Muốn chain tiếp bằng API con, có thể override `chain` ở `Child` với kiểu trả về `Child` nếu quy tắc override cho phép.

## 18. Checklist thiết kế API truyền/trả `this`

1. **Xác định ngữ cảnh instance.** `this` chỉ dùng khi đang có đối tượng hiện tại; không dùng trực tiếp trong static method.
2. **Kiểm tra kiểu tại compile time.** `receiver.process(this)` cần tham số hoặc overload phù hợp với kiểu của `this`.
3. **Phân biệt giá trị tham chiếu và đối tượng.** Truyền `this` sao chép giá trị tham chiếu; không clone đối tượng và không cho bên nhận gán lại `this` của caller.
4. **Kiểm tra quyền truy cập.** Truyền tham chiếu không làm field private bị mở công khai; API bên nhận vẫn theo các access modifiers.
5. **Xem mục đích truyền.** Nếu bên nhận chỉ cần một chuỗi hoặc ID, cân nhắc truyền dữ liệu cần thiết thay vì cả object.
6. **Tránh this escape.** Hạn chế truyền `this` vào registry, thread, callback hoặc listener trong constructor trước khi đối tượng được khởi tạo hoàn chỉnh.
7. **Xác định kiểu trả về khi `return this`.** Nó phải tương thích với kiểu hiện tại; `void` và kiểu primitive không thể nhận tham chiếu này.
8. **Phân biệt mutable và immutable fluent API.** `return this` thường giữ cùng instance; `return new ...` thường tạo phiên bản mới.
9. **Kiểm tra chain khi kế thừa.** Kiểu tĩnh của kết quả do khai báo method xác định; cần covariant return/self-type khi API con yêu cầu.
10. **Quản lý alias.** Nhiều biến nhận `return this` đều chia sẻ cùng object; cập nhật từ một nơi có thể ảnh hưởng nơi khác.
11. **Cân nhắc đa luồng.** `return this` không cung cấp thread safety. Mutable state chia sẻ cần cơ chế đồng bộ hoặc thiết kế dữ liệu phù hợp.
12. **Phân biệt các dạng `this`.** `this.field`, `this.method()`, `this(...)`, `Outer.this` và `return this` là các cú pháp có vai trò riêng.

## Ghi nhớ

- **`this` là tham chiếu đến đối tượng hiện tại**, có thể được dùng làm một biểu thức đối số hoặc giá trị trả về trong instance context.
- **`other.process(this)` truyền giá trị tham chiếu** tới đối tượng; Java vẫn luôn **pass-by-value**, nên gán lại biến tham số không đổi biến bên gọi.
- **`return this;` trả về chính đối tượng đang thực thi**, không tạo mới/copy, nên thường dùng cho fluent API như `builder.step1().step2()`.
- **Method chaining không đồng nghĩa immutable.** Nếu các bước sửa field rồi `return this`, nhiều biến tham chiếu có thể quan sát cùng thay đổi.
- **Kiểu trả về tĩnh vẫn quan trọng** khi kế thừa: trả về cùng đối tượng runtime không tự mở khóa method chỉ có ở subtype.
- **`this(...)` là constructor chaining**, hoàn toàn khác việc truyền `this` làm đối số hoặc trả về `this`.
- **Tránh công bố `this` từ constructor quá sớm** và kiểm soát việc chia sẻ tham chiếu với callback hoặc thành phần khác.
