# `super`, chuỗi constructor và flexible constructor bodies trong Java 27

Khi tạo một đối tượng kế thừa, Java phải khởi tạo phần trạng thái thuộc lớp cha và phần trạng thái thuộc lớp con theo thứ tự xác định. `super(...)` chọn constructor của lớp cha trực tiếp, `this(...)` chuyển sang một constructor khác trong cùng lớp, còn `super.member` truy cập cách triển khai thành viên ở lớp cha. Ba cú pháp này có tên gần giống nhau nhưng phục vụ những mục đích khác nhau.

Từ Java 25, **flexible constructor bodies** đã trở thành tính năng chính thức (JEP 513). Trong Java 27, constructor có thể kiểm tra tham số, tính toán biến cục bộ hoặc gán một số field **trước** lời gọi `super(...)` hay `this(...)`. Tuy nhiên, đối tượng vẫn ở trạng thái *đang khởi tạo* tại thời điểm đó, nên việc đọc và sử dụng `this`/`super` chịu các hạn chế của ngữ cảnh khởi tạo sớm (*early construction context*).

Bài này thuộc chủ đề thiết kế đối tượng trong Java 27, dùng cú pháp Java SE hiện hành. Các ví dụ được ghi rõ là hợp lệ có thể biên dịch với JDK 27 thông thường, không cần bật preview.

## 1. Phân biệt các cách dùng `this` và `super`

| Cú pháp | Vai trò | Vị trí |
| --- | --- | --- |
| `super(args);` | Gọi một constructor có thể truy cập được của **lớp cha trực tiếp**, theo đối số tương ứng | Lời gọi constructor trong body của constructor lớp con |
| `this(args);` | Gọi một constructor khác của **chính lớp hiện tại** | Lời gọi constructor trong body của constructor hiện tại |
| `super.method(args)` | Gọi cách triển khai instance method từ lớp cha theo các quy tắc của ngôn ngữ | Instance method hoặc ngữ cảnh thích hợp **sau khi** đối tượng cho phép truy cập `super` |
| `super.field` | Tham chiếu một instance field được khai báo/thừa kế từ lớp cha, thường để phân biệt field bị che tên | Ngữ cảnh instance phù hợp, **sau** điểm hạn chế khởi tạo sớm |
| `this.field` | Tham chiếu field của đối tượng hiện tại; trong prologue chỉ có ngoại lệ hẹp cho phép **gán trực tiếp** field do chính lớp này khai báo | Instance context; bị hạn chế khi chưa gọi constructor cha |

**Constructor không được kế thừa như method.** Mỗi lớp có các constructor riêng và một constructor của lớp con phải dẫn tới quá trình gọi constructor cha hợp lệ. `super(args)` luôn xét constructor của lớp cha trực tiếp; nó không có nghĩa là có thể nhảy thẳng tới constructor của lớp ông.

### `super(...)` khác `super.method(...)`

Ví dụ sau minh họa hai ý nghĩa:

```java
class Device {
    private final String serial;

    Device(String serial) {
        this.serial = serial;
    }

    String description() {
        return "Device " + serial;
    }
}

class Printer extends Device {
    Printer(String serial) {
        super(serial);               // Gọi constructor lớp cha
    }

    @Override
    String description() {
        return "Printer / " + super.description(); // Gọi method lớp cha
    }
}
```

Ở đây `super(serial)` tham gia quá trình khởi tạo, còn `super.description()` gọi một instance method. Có thể đặt `super.description()` trong method override như ví dụ, nhưng **không** được đọc hoặc gọi instance member qua `super` trong phần prologue của constructor khi lớp cha chưa được khởi tạo.

## 2. Chuỗi constructor: `this(...)` rồi tới `super(...)`

Một lớp có thể khai báo nhiều constructor (constructor overloading). `this(...)` giúp các constructor cùng lớp dùng chung logic khởi tạo, tránh lặp lại những thao tác kiểm tra và gán field.

```java
class Account {
    final String owner;

    Account(String owner) {
        this.owner = owner;
        System.out.println("1. Account: " + owner);
    }
}

class SavingsAccount extends Account {
    final long balance;

    SavingsAccount(String owner) {
        System.out.println("A. Constructor một tham số: prologue");
        this(owner, 0L);
        System.out.println("D. Constructor một tham số: epilogue");
    }

    SavingsAccount(String owner, long balance) {
        String normalized = java.util.Objects.requireNonNull(owner, "owner").strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Owner must not be blank");
        }
        if (balance < 0) {
            throw new IllegalArgumentException("Balance must be non-negative");
        }
        System.out.println("B. Constructor hai tham số: prologue");
        super(normalized);
        this.balance = balance;
        System.out.println("C. Constructor hai tham số: epilogue");
    }
}

class ConstructorChainDemo {
    public static void main(String[] args) {
        SavingsAccount account = new SavingsAccount("  Linh  ");
        System.out.println(account.owner + ": " + account.balance);
    }
}
```

Kết quả theo đúng thứ tự thực thi:

```text
A. Constructor một tham số: prologue
B. Constructor hai tham số: prologue
1. Account: Linh
C. Constructor hai tham số: epilogue
D. Constructor một tham số: epilogue
Linh: 0
```

Diễn tiến:

1. Khi gọi `new SavingsAccount("  Linh  ")`, constructor một tham số chạy phần prologue rồi gọi `this(owner, 0L)`.
2. Constructor hai tham số kiểm tra và chuẩn hóa dữ liệu trong prologue, rồi gọi `super(normalized)`.
3. Constructor `Account(String)` của lớp cha thực thi.
4. Sau khi constructor cha trả về, constructor hai tham số gán `balance` và hoàn thành epilogue.
5. Cuối cùng, constructor một tham số tiếp tục epilogue; đối tượng được trả về khi toàn bộ chuỗi hoàn tất.

**Lưu ý:** Mỗi constructor chỉ có thể chứa **tối đa một** lời gọi constructor tường minh dạng `this(...)` hoặc `super(...)`. Lời gọi ấy phải xuất hiện trực tiếp trong body của constructor, sau prologue tùy chọn, không được đặt trong một nhánh `if`, vòng lặp hoặc lambda. Mọi chuỗi `this(...)` phải kết thúc bằng một constructor gọi constructor cha; một vòng gọi `this(...)` trực tiếp hoặc gián tiếp quay lại chính nó là lỗi biên dịch.

### Khi không ghi `super(...)` hay `this(...)`

Với một constructor thông thường không chứa lời gọi constructor tường minh, Java ngầm thực hiện `super();` **trước các câu lệnh đã viết** trong body (trừ constructor của `java.lang.Object`). Điều này chỉ hợp lệ nếu lớp cha có constructor không tham số và constructor đó có thể truy cập được.

```java
class Base {
    Base(String code) {
        System.out.println(code);
    }
}

class Derived extends Base {
    Derived() {
        super("D-01"); // Cần thiết vì Base không có constructor không tham số
    }
}
```

Nếu bỏ `super("D-01")` trong ví dụ này, compiler sẽ tìm `Base()` theo cơ chế gọi `super()` ngầm và báo lỗi. Nếu một class **không khai báo constructor nào**, Java sinh một *default constructor* cho class đó; nhưng nếu class đã tự khai báo ít nhất một constructor, compiler không sinh thêm default constructor.

## 3. Thứ tự khởi tạo đối tượng theo JLS Java 27

Tách biệt **cấp phát bộ nhớ**, **gọi chuỗi constructor** và **chạy các initializer** giúp giải thích vì sao giá trị field có thể khác nhau trong quá trình khởi tạo.

Theo JLS §12.5, với một class thông thường:

1. JVM cấp phát vùng nhớ cho đối tượng và đặt mọi instance field trong cả cây kế thừa về giá trị mặc định (`0`, `false`, `null`, ...).
2. Trong constructor đang được gọi, chạy **prologue** nếu có lời gọi `this(...)`/`super(...)` tường minh.
3. Đánh giá đối số của lời gọi constructor và thực hiện constructor được gọi. Việc này lặp lại theo chuỗi tới các lớp cha.
4. Khi constructor lớp cha trả về, chạy **instance field initializers** và **instance initializer blocks** của lớp hiện tại theo thứ tự xuất hiện trong mã nguồn.
5. Chạy **epilogue** của constructor hiện tại.
6. Nếu constructor đã gọi `this(...)`, sau khi constructor được ủy quyền hoàn tất thì chạy epilogue của constructor gọi; Java **không chạy lại** các field initializer/initializer block của cùng lớp trong nhánh ủy quyền đó.

Sơ đồ cho một constructor lớp con gọi trực tiếp `super(...)`:

```text
new Sub(...)
    |
    +-- Cấp phát đối tượng; field có giá trị mặc định
    |
    +-- Sub constructor: prologue (nếu có)
    |
    +-- super(args) --> Super constructor và chuỗi cha của nó
    |                      |
    |                      +-- Khởi tạo field/block của Super
    |                      +-- Epilogue của Super
    |
    +-- Khởi tạo field/block của Sub
    |
    +-- Sub constructor: epilogue
    |
    +-- Đối tượng khởi tạo xong
```

Ví dụ thực thi:

```java
class Parent {
    Parent() {
        System.out.println("2. Parent constructor");
    }
}

class Child extends Parent {
    int value = initializeValue();

    private static int initializeValue() {
        System.out.println("3. Child field initializer");
        return 10;
    }

    Child(int input) {
        System.out.println("1. Child prologue: " + input);
        super();
        System.out.println("4. Child epilogue, value = " + value);
    }
}

class InitializationDemo {
    public static void main(String[] args) {
        new Child(42);
    }
}
```

Kết quả:

```text
1. Child prologue: 42
2. Parent constructor
3. Child field initializer
4. Child epilogue, value = 10
```

Nếu prologue ném exception, lời gọi `super(...)` chưa xảy ra và việc khởi tạo kết thúc bằng exception. Nếu constructor cha ném exception, phần khởi tạo field/epilogue của lớp con không được thực hiện bình thường.

### Gán field trước `super()` có thể bị initializer ghi đè

Flexibility không thay đổi thứ tự chạy instance initializer. Với field **không `final`**, nếu gán field trong prologue rồi class có initializer cho chính field đó, initializer chạy **sau** constructor cha có thể ghi đè giá trị gán sớm. Với field `final`, phải tuân thủ các quy tắc definite assignment và không được gán hai lần. Vì vậy, khi chủ đích là bảo toàn giá trị khởi tạo sớm, nên dùng một *blank final field* không có field initializer, gán đúng một lần trên mọi đường đi hợp lệ.

## 4. Flexible constructor bodies: những gì đã thay đổi trong Java 27

JEP 513 đã chuẩn hóa tính năng ở Java 25. Trong Java 27, việc `super(...)`/`this(...)` **không còn bắt buộc là câu lệnh đầu tiên** của constructor. Chúng có thể được đặt sau một hoặc nhiều câu lệnh tạo thành prologue.

### 4.1. Kiểm tra input và tính toán trước khi gọi lớp cha

Đây là trường hợp sử dụng trực tiếp và phổ biến:

```java
class NamedResource {
    final String name;

    NamedResource(String name) {
        this.name = name;
    }
}

class FileResource extends NamedResource {
    FileResource(String rawName) {
        String normalized = java.util.Objects
                .requireNonNull(rawName, "rawName")
                .strip();

        if (normalized.isBlank()) {
            throw new IllegalArgumentException("Resource name must not be blank");
        }

        super(normalized);
    }
}
```

`normalized` là biến cục bộ được tính từ tham số; `Objects.requireNonNull(...)` và `strip()` không cần tham chiếu tới đối tượng `FileResource` đang được tạo. Nếu dữ liệu không hợp lệ, constructor ném exception trước khi gọi lớp cha.

Có thể dùng các câu lệnh thông thường như khai báo biến cục bộ, `if`, vòng lặp, hoặc gọi method `static` khi chúng không vi phạm quy tắc early construction context. Điều kiện quan trọng không phải tên câu lệnh, mà là **có truy cập hoặc để lộ đối tượng đang được khởi tạo hay không**.

### 4.2. Gán trực tiếp instance field của chính lớp trước `super()`

Java 27 cho phép một ngoại lệ có chủ đích: trong prologue, có thể **gán trực tiếp** field do **chính lớp hiện tại** khai báo, kể cả blank `final` field, để lớp cha có thể thấy giá trị khi gọi một method được override.

```java
class EventSource {
    EventSource() {
        report(); // Dispatch động tới cách override của lớp con
    }

    void report() {
        System.out.println("EventSource");
    }
}

final class IdentifiedSource extends EventSource {
    private final int id;

    IdentifiedSource(int id) {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        this.id = id;   // ĐƯỢC: chỉ gán field do IdentifiedSource khai báo
        super();
    }

    @Override
    void report() {
        System.out.println("id = " + id);
    }
}

class EarlyFieldDemo {
    public static void main(String[] args) {
        new IdentifiedSource(42);
    }
}
```

Kết quả:

```text
id = 42
```

Nếu chuyển việc gán `id` xuống epilogue sau `super()`, method `report()` được gọi từ constructor cha sẽ quan sát giá trị mặc định `0` của field `int`. Gán sớm giúp khắc phục **trường hợp cụ thể** này; nó không biến việc gọi method có thể override trong constructor cha thành một thiết kế an toàn nói chung.

**Khuyến nghị thiết kế:** Tránh gọi method có thể bị override từ constructor lớp cha nếu có thể. Một lớp con có thể còn nhiều field hoặc invariant chưa được khởi tạo khi method bị gọi; gán trước một field không bảo đảm trạng thái hoàn chỉnh của toàn bộ object. Cân nhắc `private`/`final` method cho logic khởi tạo nội bộ, hoặc tách việc khởi tạo phức tạp sang factory/bước hoàn thiện riêng khi thiết kế cho phép.

### 4.3. Ranh giới early construction context

*Early construction context* gồm prologue của constructor và các biểu thức nằm trong lời gọi constructor tường minh. Trong phạm vi đó, đối tượng hiện tại chưa sẵn sàng để được dùng như một instance đã khởi tạo hoàn chỉnh.

| Có thể thực hiện | Không được thực hiện trước `super(...)`/`this(...)` |
| --- | --- |
| Đọc tham số constructor, biến cục bộ đã khởi tạo | Đọc instance field của `this`, dù field đó thuộc lớp cha hay lớp con |
| Gọi static method hoặc thao tác với object độc lập được cung cấp qua tham số | Gọi instance method của đối tượng hiện tại, kể cả lời gọi không ghi `this.` |
| Kiểm tra input và ném exception | Truyền `this` cho method khác, in `this`, hay để `this` thoát ra ngoài |
| Gán **trực tiếp** field được khai báo trong lớp hiện tại | Đọc-sửa như `this.count++`, `count += 1`, hoặc truy cập `super.field`/`super.method()` |
| Tạo và xử lý object khác không cần instance hiện tại | Tạo inner class cần instance hiện tại làm enclosing instance; truy cập ngầm tới thành viên instance của chính đối tượng |

Những dòng được đánh dấu lỗi dưới đây **sẽ không biên dịch nếu bỏ comment**:

```java
class InvalidChild extends Parent {
    int count;

    InvalidChild(int value) {
        this.count = value;            // Hợp lệ: gán trực tiếp
        // System.out.println(count);  // Lỗi: đọc instance field trong prologue
        // this.count++;               // Lỗi: cần đọc count trước khi tăng
        // System.out.println(this);   // Lỗi: dùng đối tượng chưa khởi tạo
        // super.toString();           // Lỗi: truy cập instance method qua super
        super();
    }
}
```

Trong mẫu trên, các dòng gây lỗi đã được comment để phần mã còn lại có thể biên dịch khi có lớp `Parent` phù hợp. Lưu ý ngoại lệ gán field rất hẹp: `this.count = value;` có thể hợp lệ, nhưng không vì thế mà mọi biểu thức có `this` đều được phép trước `super()`.

### 4.4. `this(...)` cũng có prologue

Flexible constructor bodies áp dụng cho cả constructor ủy quyền qua `this(...)`:

```java
class PageSize {
    final int width;
    final int height;

    PageSize(int width, int height) {
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("Dimensions must be positive");
        }
        this.width = width;
        this.height = height;
    }

    PageSize(int side) {
        if (side > 10_000) {
            throw new IllegalArgumentException("Side is too large");
        }
        int normalized = Math.max(1, side);
        this(normalized, normalized);
    }
}
```

Constructor một tham số chạy prologue, rồi chuyển sang constructor hai tham số. Constructor hai tham số ở ví dụ không ghi `super()`, vì vậy `Object()` được gọi ngầm trước phần body của constructor hai tham số. Các lời gọi `this(...)` không làm khởi tạo lại field initializer của class sau mỗi mức ủy quyền.

## 5. `super` và các quy tắc cần nhớ khi thiết kế inheritance

### 5.1. Constructor cha phải truy cập được

Một lớp con chỉ được gọi constructor lớp cha mà luật truy cập cho phép. `private` constructor của lớp cha không thể được gọi trực tiếp từ lớp con. Constructor `protected` hoặc `public` có các điều kiện truy cập tương ứng. Nếu class cha không có constructor không tham số phù hợp, lớp con phải chọn constructor có tham số bằng `super(args)`.

Nếu `super(...)` có thể ném checked exception, constructor lớp con phải khai báo `throws` phù hợp. Không được bao lời gọi `super(...)` trong một khối `try` của cùng constructor để bắt exception; lời gọi constructor phải nằm trực tiếp trong body. Các thao tác prologue có thể tự kiểm tra dữ liệu và ném exception riêng.

### 5.2. Constructor gọi đúng một constructor khác, không gọi theo nhánh điều kiện

Cách viết sau là **không hợp lệ** vì `super(...)` không được đặt trong nhánh `if`:

```java
// KHÔNG HỢP LỆ
class ConditionalChild extends Account {
    ConditionalChild(boolean vip) {
        if (vip) {
            super("VIP");
        } else {
            super("NORMAL");
        }
    }
}
```

Thay bằng việc tính tham số trước rồi có một lời gọi `super(...)` trực tiếp:

```java
class ConditionalChild extends Account {
    ConditionalChild(boolean vip) {
        String owner = vip ? "VIP" : "NORMAL";
        super(owner);
    }
}
```

### 5.3. `super` không vô hiệu hóa dispatch động trong constructor

Khi constructor lớp cha gọi instance method có thể override, JVM vẫn dùng cách triển khai của lớp con ngay cả khi phần khởi tạo của lớp con chưa hoàn thành. Điều này giải thích ví dụ `EventSource`/`IdentifiedSource` ở trên. Ngược lại, lời gọi tường minh `super.method()` trong một method của lớp con chọn cách triển khai được xác định từ lớp cha, theo quy tắc đặc tả; đó là một công cụ hỗ trợ mở rộng hành vi, không phải một cách gọi constructor.

### 5.4. Chú ý record và enum

Record là một loại class đặc biệt:

- Record kế thừa `java.lang.Record`; constructor record không được viết lời gọi `super(...)` tường minh.
- Constructor *noncanonical* của record phải ủy quyền đến một constructor khác của record bằng `this(...)`; chuỗi này cuối cùng phải đến canonical constructor. Nó có thể có prologue để chuẩn hóa và kiểm tra dữ liệu.
- Compact canonical constructor dùng để kiểm tra/chuẩn hóa các tham số component; nó không được tự đặt `super(...)` hay `this(...)`.

Ví dụ record hợp lệ:

```java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }

    Range(int end) {
        if (end < 0) {
            throw new IllegalArgumentException("end must be non-negative");
        }
        this(0, end);
    }
}
```

Enum cũng có quy tắc tạo instance riêng của ngôn ngữ và không cho phép gọi `super(...)` tường minh. Không nên áp dụng máy móc ví dụ constructor của subclass thông thường cho record hoặc enum.

## 6. Các lỗi thường gặp khi nâng cấp sang Java 27

| Hiện tượng | Nguyên nhân chính | Cách xử lý |
| --- | --- | --- |
| `constructor ... cannot be applied` hoặc không tìm thấy `super()` | Lớp cha chỉ có constructor có tham số; compiler cố gọi `super()` ngầm | Chọn constructor cha phù hợp bằng `super(args)` |
| Trình biên dịch cũ báo `call to super must be first statement` | Project thực tế đang dùng source level trước Java 25, hoặc IDE/build tool chưa cấu hình đúng `--release` | Kiểm tra `java`/`javac`, build toolchain, source/target/release; Java 27 hỗ trợ prologue ổn định |
| Gán được `this.x = value` trước `super()` nhưng đọc `x` lại lỗi | Early construction context chỉ cho phép một số gán trực tiếp; không cho đọc instance state | Dùng biến cục bộ hoặc tham số để tính toán; đọc field sau constructor invocation |
| In hoặc truyền `this` trong prologue bị lỗi | Không được dùng đối tượng chưa khởi tạo hoàn chỉnh | Chỉ thao tác với dữ liệu độc lập; chuyển mã cần `this` xuống epilogue |
| `super(...)` bên trong `if`/`try` bị lỗi | Lời gọi constructor phải nằm trực tiếp trong body, tối đa một lời gọi tường minh | Chuẩn bị đối số trong prologue, rồi gọi một `super(...)` hoặc `this(...)` |
| Constructor báo `recursive constructor invocation` | Chuỗi `this(...)` trực tiếp/gián tiếp quay lại constructor cũ | Thiết kế một constructor đích gọi `super(...)` hoặc dùng `super()` ngầm |
| Field có giá trị bất ngờ sau khi gán sớm | Instance field initializer của lớp con chạy sau constructor cha và có thể ghi đè | Kiểm tra thứ tự tại JLS §12.5; dùng blank final field khi cần gán sớm một lần |
| Method override thấy field chưa khởi tạo | Constructor cha đã gọi method override trước khi hoàn tất khởi tạo lớp con | Tránh gọi overridable method trong constructor; cân nhắc gán sớm đúng field cần thiết |
| `return;` trong constructor bị lỗi | JLS Java 27 cấm `return` trong constructor body | Để constructor kết thúc bình thường hoặc ném exception khi không thể khởi tạo |

**Phân biệt lỗi cú pháp và lỗi thiết kế:** Java 27 cho phép nhiều việc hơn trong constructor, nhưng không bảo đảm mọi thiết kế kế thừa đều tốt. Với logic cần nhiều trạng thái, đối tượng bất biến hoặc tài nguyên bên ngoài, ưu tiên giữ constructor đơn giản, xác nhận invariant rõ ràng và tránh làm lộ `this` khi khởi tạo.

## 7. Checklist khi viết constructor trong Java 27

1. Xác định constructor cha trực tiếp nào cần gọi, tham số nào cần chuẩn hóa và exception nào có thể phát sinh.
2. Nếu có nhiều overload của cùng lớp, tạo chuỗi `this(...)` rõ ràng, không có vòng lặp; chỉ một đường khởi tạo cuối cùng đi qua constructor cha.
3. Dùng prologue để kiểm tra tham số và tạo biến cục bộ; không đọc instance field hoặc gọi instance method trước constructor invocation.
4. Chỉ gán sớm field thuộc **chính** lớp hiện tại khi có lý do cụ thể; kiểm tra definite assignment và khả năng field initializer ghi đè.
5. Khi cần gọi constructor tường minh, đặt tối đa một lời gọi `this(...)` hoặc `super(...)` trực tiếp trong body, sau prologue tùy chọn. Nếu không có lời gọi tường minh, bảo đảm lời gọi `super()` ngầm hợp lệ.
6. Hiểu thứ tự thực thi: prologue → constructor được gọi → field/instance initializers → epilogue; không giả định lớp con đã khởi tạo xong khi constructor cha chạy.
7. Tránh gọi method có thể override từ constructor cha; không để `this` thoát ra ngoài trước khi object sẵn sàng.
8. Với record hoặc enum, áp dụng quy tắc constructor riêng thay vì tự thêm `super(...)`.
9. Biên dịch bằng đúng Java release và toolchain mà dự án sử dụng, đặc biệt khi dùng mã nguồn có flexible constructor bodies.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 27 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/27/language/flexible-constructor-bodies.html) — prologue, epilogue, early construction context, giới hạn truy cập `this` và gán field trước `super(...)`.
- [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513) — đặc tả mục tiêu và việc chuẩn hóa tính năng trong JDK 25.
- [JLS Java SE 27 §8.8 — Constructor Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.8) — các khai báo constructor, `this(...)`, `super(...)`, lời gọi tường minh và constructor mặc định.
- [JLS Java SE 27 §12.5 — Creation of New Class Instances](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-12.html#jls-12.5) — thứ tự thực thi prologue, chuỗi constructor, initializer và epilogue.
- [JLS Java SE 27 §8.10.4 — Record Constructor Declarations](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-8.html#jls-8.10.4) — canonical, noncanonical và compact constructors của record.
- [Oracle Java SE 27 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-release.html) — trạng thái chính thức của các thay đổi ngôn ngữ theo phiên bản.
