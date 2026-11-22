# Phương thức tạo đối tượng có tên và so sánh với hàm khởi tạo trong Java

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **constructor (hàm khởi tạo)** với **named factory method (phương thức tạo đối tượng có tên)**, thường được triển khai dưới dạng phương thức `static`.
- Giải thích vì sao `new ClassName(...)` và `ClassName.of(...)` có thể cùng tạo hoặc cung cấp đối tượng nhưng có **cú pháp, quyền truy cập, kiểu trả về và hợp đồng** khác nhau.
- Thiết kế API dễ đọc qua những tên `of`, `from`, `valueOf`, `getInstance`, `newInstance`, `create`, `getDefault` hoặc tên phản ánh nghiệp vụ.
- Chọn giữa constructor và factory khi cần **diễn đạt ý nghĩa tham số**, **kiểm tra dữ liệu**, **cache/tái sử dụng instance**, **ẩn lớp triển khai**, hoặc **trả về subtype/interface**.
- Hiểu những giới hạn: phương thức factory **không phải constructor**; `static` method không được override qua dynamic dispatch; factory không tự bảo đảm singleton, thread safety hay object immutability.
- Nhận biết quan hệ với constructor chaining, access modifiers, `final` fields, exception và tên method reference trong Java 17+.
- Biên dịch và chạy ví dụ Java đầy đủ, đồng thời tránh các lỗi thường gặp khi thiết kế factory.

## 1. Hai cách cung cấp đối tượng

Trong Java, cách trực tiếp nhất để tạo đối tượng là gọi **constructor** bằng toán tử `new`:

~~~java
Book book = new Book("Java Core", 180);
~~~

Đây là **đoạn minh họa** đặt trong method có lớp `Book` và constructor tương ứng.

Một cách khác là định nghĩa **phương thức có tên mô tả mục đích tạo đối tượng**:

~~~java
Book book = Book.of("Java Core", 180);
~~~

`of` ở đây là một method do lớp `Book` khai báo, không phải cú pháp đặc biệt hay từ khóa của Java. Một static factory thường nhận đối số, thực hiện validation/chọn cách cung cấp instance rồi **trả về tham chiếu đối tượng**.

Ví dụ ý tưởng:

~~~java
public final class Book {
    private final String title;
    private final int pages;

    private Book(String title, int pages) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        if (pages <= 0) {
            throw new IllegalArgumentException("pages must be positive");
        }
        this.title = title;
        this.pages = pages;
    }

    public static Book of(String title, int pages) {
        return new Book(title, pages);
    }

    public String title() {
        return title;
    }

    public int pages() {
        return pages;
    }
}
~~~

Lưu lớp trên trong `Book.java` thì biên dịch được. `Book.of(...)` là **phương thức tĩnh** và có kiểu trả về `Book`; constructor `Book(...)` là **private** nên mã bên ngoài lớp không thể trực tiếp viết `new Book(...)`. Factory có quyền gọi private constructor vì nằm bên trong chính lớp.

Điểm quan trọng: **Factory không thay constructor theo nghĩa bỏ hẳn quá trình khởi tạo đối tượng**. Trong ví dụ, factory vẫn dùng `new Book(...)` ở bên trong; nó đóng vai trò **API công khai kiểm soát việc cung cấp đối tượng**.

## 2. Constructor và named factory method: so sánh chính xác

| Tiêu chí | Constructor | Named static factory method |
| --- | --- | --- |
| Cú pháp gọi thông thường | `new Book("Java", 180)` | `Book.of("Java", 180)` |
| Tên khai báo | Phải **trùng tên lớp** | Tên method bất kỳ hợp lệ, nên chọn có ý nghĩa |
| Kiểu trả về trong khai báo | **Không có** return type, kể cả `void` | **Có** return type, ví dụ `Book`, `Shape`, `Optional<T>` |
| Cách trả kết quả | Biểu thức `new` trả tham chiếu nếu khởi tạo thành công | Method dùng `return` theo kiểu khai báo |
| Có bắt buộc tạo instance mới? | Mỗi lần dùng `new` biểu thị một đối tượng mới theo ngữ nghĩa Java | **Không**: có thể trả instance mới, cached instance, singleton, subtype hoặc giá trị khác theo hợp đồng |
| Có trả subtype/implementation ẩn? | `new Book(...)` tạo đối tượng của lớp được chỉ định (theo cơ chế khởi tạo đó) | **Có thể** khai báo return type là interface/base class rồi trả implementation phù hợp |
| Kiểm tra đối số | Được | Được |
| Đổi tên theo ý nghĩa tham số | Không; constructor có cùng tên lớp | Được: `ofSeconds`, `ofMillis`, `fromText`… |
| Overload | Có, theo danh sách kiểu tham số | Có; ngoài ra có thể dùng tên method khác |
| Truy cập | Constructor có access modifier; không kế thừa | Static method có access modifier và quy tắc thành viên static riêng |
| `this(...)`/`super(...)` | Có thể dùng trong constructor theo quy tắc Java | **Không**: không thể gọi constructor invocation bằng cú pháp `this(...)`/`super(...)` trong thân method |
| Dùng `new ClassName()` từ bên ngoài | Cần constructor phù hợp, truy cập được | Có thể **không cho phép**, nếu constructor private |
| Đảm bảo thread safety? | Không tự bảo đảm | Không tự bảo đảm |

Một factory method **không nhất thiết luôn là `static`** trong mọi mẫu thiết kế phần mềm. Nhưng khi nói **named static factory** thay thế API constructor trong Java, ví dụ phổ biến là `Book.of(...)`, `LocalDate.of(...)`, `List.of(...)`. Điều này khác với **Factory Method pattern** theo GoF, nơi một phương thức tạo sản phẩm có thể được định nghĩa để lớp con override; phần này sẽ được phân biệt ở mục cuối.

### 2.1. Đừng nhầm chữ `factory` với từ khóa của Java

Java không có từ khóa `factory`. Các tên `of`, `from`, `valueOf`, `create` chỉ là **quy ước API**. Method tên `of` chỉ “tạo đối tượng” nếu implementation và hợp đồng của nó thực sự làm vậy. Không thể suy từ tên rằng method luôn tạo mới hoặc luôn dùng cache.

Ví dụ:

~~~java
Book first = Book.of("Java", 180);
Book second = Book.of("Java", 180);
~~~

Với implementation `Book.of` ở mục 1, `first` và `second` là **hai instance khác nhau**, vì mỗi lần factory đều gọi `new Book(...)`. Một factory khác có thể giữ cache và trả về cùng một instance.

## 3. Lợi ích 1 — Tên factory diễn đạt ý nghĩa và đơn vị

Constructor bị ràng buộc tên lớp. Khi hai cách tạo đối tượng đều nhận **cùng kiểu đối số**, constructor overloading không phân biệt được ý nghĩa chỉ bằng tên tham số.

Ví dụ độ dài có đơn vị mét và milimét:

~~~java
// Không thể có đồng thời hai constructor cùng chữ ký:
// Length(long meters) { ... }
// Length(long millimeters) { ... }
~~~

Dù tên tham số khác nhau, cả hai constructor đều có chữ ký `Length(long)`; chúng **không thể cùng xuất hiện trong một lớp**. Nếu chỉ để một constructor `Length(long)`, người dùng API phải nhớ đơn vị của con số.

Phương thức có tên giải quyết trực tiếp:

~~~java
Length a = Length.ofMeters(2);
Length b = Length.ofMillimeters(2);
~~~

Hai tên method mô tả **hai cách diễn giải đối số** dù cùng mang kiểu `long`. Điều đó giúp giảm lỗi nhầm đơn vị (độ dài, thời gian, nhiệt độ, khối lượng, byte/KB…).

Các API có sẵn trong Java cũng thể hiện tinh thần này:

- `java.time.Duration.ofSeconds(30)`: đơn vị giây.
- `java.time.Duration.ofMillis(500)`: đơn vị mili-giây.
- `java.time.LocalDate.of(2026, 10, 18)`: ngày, tháng, năm theo hợp đồng API.
- `java.util.List.of("A", "B")`: tạo/cung cấp danh sách **không sửa được** theo hợp đồng.
- `java.util.Optional.of(value)` và `Optional.ofNullable(value)`: khác nhau ở **cách xử lý null**.

**Tuy nhiên:** những tên này là API của các lớp cụ thể trong Java Standard Library; chúng không có cùng chính sách cache, validation hoặc null. Hãy đọc hợp đồng từng phương thức thay vì tự suy ra từ mẫu tên.

## 4. Lợi ích 2 — Có thể tái sử dụng instance, không bắt buộc `new`

Constructor được dùng với `new` mang ngữ nghĩa tạo đối tượng mới. Một static factory có thể quyết định:

- Luôn tạo một đối tượng mới.
- Trả một đối tượng **đã có** nếu hợp đồng cho phép.
- Trả một **singleton** hoặc một trong các instance cố định.
- Trả một object từ **cache/pool** được quản lý có chủ đích.

Ví dụ factory trả đối tượng cấu hình mặc định dùng chung:

~~~java
final class Settings {
    private static final Settings DEFAULT = new Settings("localhost", 8080);

    private final String host;
    private final int port;

    private Settings(String host, int port) {
        this.host = host;
        this.port = port;
    }

    static Settings defaultSettings() {
        return DEFAULT;
    }

    static Settings of(String host, int port) {
        return new Settings(host, port);
    }
}
~~~

Đây là khai báo lớp hợp lệ đặt trong tệp Java thích hợp, chưa có `main`. `Settings.defaultSettings()` trả cùng một tham chiếu `DEFAULT` ở những lần gọi thông thường. `Settings.of(...)` lại gọi `new`, nên mỗi lần trả instance mới.

**Điều kiện để chia sẻ an toàn:** trong ví dụ, hai field `host` và `port` là `final`, và `String` bất biến; đối tượng `Settings` không có thao tác thay đổi trạng thái công khai. Nếu factory trả chung một **đối tượng mutable**, các caller có thể ảnh hưởng lẫn nhau. Đừng áp dụng cache theo thói quen mà không có yêu cầu về identity, memory, concurrency và lifecycle.

Đừng mặc định rằng `newInstance` luôn trả object mới hoặc `getInstance` luôn trả object duy nhất nếu không có contract cụ thể. **Tên là lời gợi ý thiết kế, không phải bảo đảm runtime tự động.**

### 4.1. Phân biệt identity và equality

Với hai biến tham chiếu:

~~~java
Settings a = Settings.defaultSettings();
Settings b = Settings.defaultSettings();
// a == b có thể là true vì factory trả cùng instance.
~~~

Dấu `==` giữa hai tham chiếu kiểm tra chúng có **cùng object identity** không. `equals` phụ thuộc implementation của lớp; không được suy ra từ việc cùng giá trị field thì `==` phải đúng. Khi factory có quyền tái sử dụng instance, người dùng không nên đặt giả định về object identity trừ khi API công bố rõ.

Một API trả giá trị bất biến thường khuyến khích sử dụng **so sánh theo giá trị**, thay vì dùng `==` như hợp đồng cho mọi kết quả.

## 5. Lợi ích 3 — Trả interface hoặc subtype thay vì lộ class triển khai

Constructor biểu thị rõ class cụ thể ở phía `new`. Một factory có thể khai báo kiểu trả về **trừu tượng hơn**, chẳng hạn interface, rồi chọn class hiện thực ở bên trong.

Ví dụ ý tưởng:

~~~java
interface Message {
    String render();

    static Message text(String content) {
        return new TextMessage(content);
    }
}

final class TextMessage implements Message {
    private final String content;

    TextMessage(String content) {
        this.content = java.util.Objects.requireNonNull(content);
    }

    @Override
    public String render() {
        return content;
    }
}
~~~

Đây là mã hợp lệ trong tệp phù hợp khi các kiểu không `public` ở cấp top-level. Caller có thể viết `Message message = Message.text("Hello");` và chỉ phụ thuộc **interface `Message`**, thay vì cần biết tên implementation `TextMessage`.

Factory có thể thay đổi implementation về sau (ví dụ các dạng message đặc biệt, caching hoặc implementation tối ưu) **miễn giữ hợp đồng public đã công bố**. Việc thay implementation không có nghĩa mọi thay đổi đều tự tương thích: semantics, equality, serialization và hiệu năng vẫn có thể bị ảnh hưởng.

**Lưu ý:** `static` methods của interface **không được kế thừa** như instance methods; gọi chúng bằng tên interface, ví dụ `Message.text(...)`. Cũng không có dynamic dispatch để override một static factory trên đối tượng. Tính đa hình ở đây thể hiện ở **kiểu trả về `Message` và instance methods của đối tượng kết quả**.

## 6. Ví dụ hoàn chỉnh Java 17+: constructor bị ẩn và named factories

Lưu chương trình sau thành **`NamedFactoryDemo.java`**. Chương trình này biên dịch độc lập bằng JDK 17 trở lên.

~~~java
public class NamedFactoryDemo {
    static final class Length {
        private final long millimeters;

        private Length(long millimeters) {
            if (millimeters < 0) {
                throw new IllegalArgumentException("length must be nonnegative");
            }
            this.millimeters = millimeters;
        }

        static Length ofMillimeters(long value) {
            return new Length(value);
        }

        static Length ofMeters(long meters) {
            return new Length(Math.multiplyExact(meters, 1000));
        }

        long millimeters() {
            return millimeters;
        }
    }

    static final class Settings {
        private static final Settings DEFAULT =
                new Settings("localhost", 8080);

        private final String host;
        private final int port;

        private Settings(String host, int port) {
            if (host == null || host.isBlank()) {
                throw new IllegalArgumentException("host is required");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException("invalid port");
            }
            this.host = host;
            this.port = port;
        }

        static Settings defaultSettings() {
            return DEFAULT;
        }

        static Settings of(String host, int port) {
            return new Settings(host, port);
        }

        String describe() {
            return host + ":" + port;
        }
    }

    interface Greeting {
        String text();

        static Greeting forName(String name) {
            return new PersonalGreeting(name);
        }
    }

    static final class PersonalGreeting implements Greeting {
        private final String name;

        private PersonalGreeting(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name is required");
            }
            this.name = name;
        }

        @Override
        public String text() {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args) {
        Length meters = Length.ofMeters(2);
        Length millis = Length.ofMillimeters(250);
        System.out.println("lengths=" + meters.millimeters()
                + "," + millis.millimeters());

        Settings default1 = Settings.defaultSettings();
        Settings default2 = Settings.defaultSettings();
        Settings custom = Settings.of("db.internal", 5432);

        System.out.println("same default=" + (default1 == default2));
        System.out.println("default=" + default1.describe());
        System.out.println("custom=" + custom.describe());

        Greeting greeting = Greeting.forName("Lan");
        System.out.println("greeting=" + greeting.text());

        try {
            Length.ofMillimeters(-1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid length rejected");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NamedFactoryDemo.java
java NamedFactoryDemo
~~~

**Kết quả stdout:**

~~~text
lengths=2000,250
same default=true
default=localhost:8080
custom=db.internal:5432
greeting=Hello, Lan
invalid length rejected
~~~

Phân tích:

1. `Length.ofMeters(2)` và `Length.ofMillimeters(250)` đều trả về `Length`, nhưng tên factory mô tả **đơn vị của tham số**. `Math.multiplyExact(2, 1000)` bằng `2000`.
2. Constructor `Length(long)` được khai báo `private`, ngăn code ngoài lớp trực tiếp chọn số milimét mà không đi qua các factory được định nghĩa. Validation không cho độ dài âm.
3. `Settings.defaultSettings()` trả static final reference `DEFAULT`; hai lời gọi tạo hai **biến tham chiếu** trỏ chung một đối tượng, nên `default1 == default2` là `true`.
4. `Settings.of("db.internal", 5432)` trả **đối tượng cấu hình mới**. Cả hai cách tạo đều đi qua private constructor để kiểm tra host/port.
5. `Greeting.forName("Lan")` khai báo return type là **interface `Greeting`** nhưng trả một instance `PersonalGreeting`, giúp caller không cần phụ thuộc tên class triển khai.
6. Khi gọi `Length.ofMillimeters(-1)`, private constructor ném `IllegalArgumentException`; factory không nuốt lỗi nên khối `catch` in dòng cuối.

Các nested types chỉ được dùng để đặt mọi thứ vào **một tệp chạy độc lập**. Trong dự án lớn, bạn thường đặt các kiểu API riêng trong những file/package thích hợp.

**Cảnh báo ranh giới numeric:** `Math.multiplyExact` có thể ném `ArithmeticException` nếu phép nhân vượt miền `long`. Điều này có chủ đích tốt hơn việc âm thầm overflow thành số sai. Nếu một API chuyển đổi đơn vị cần báo lỗi đồng nhất, có thể xử lý overflow thành ngoại lệ nghiệp vụ theo hợp đồng của bạn.

## 7. Constructor vẫn có vai trò quan trọng khi dùng factory

Named factory **không loại bỏ constructor trong quá trình tạo instance mới**. Thường quy trình là:

~~~text
Caller
  |
  |  Money.ofCents(150)
  v
static factory ofCents(long)
  |
  | kiểm tra, chuyển đơn vị, quyết định cache/new
  v
private constructor Money(long)
  |
  | khởi tạo các final fields
  v
đối tượng Money được trả về cho caller
~~~

Khi bạn viết `new Money(150)` ở caller, caller đi **trực tiếp qua public constructor** nếu class cung cấp. Khi viết `Money.ofCents(150)`, caller đi qua một **method**, method đó có thể chọn khởi tạo mới hoặc trả instance khác.

### 7.1. Tập trung invariants trong constructor

Một thiết kế có ích là mọi factory **ủy quyền cho cùng private constructor**, nơi kiểm tra những invariants thiết yếu:

~~~java
final class Money {
    private final long cents;

    private Money(long cents) {
        if (cents < 0) {
            throw new IllegalArgumentException("negative money");
        }
        this.cents = cents;
    }

    static Money ofCents(long cents) {
        return new Money(cents);
    }

    static Money ofWholeUnits(long wholeUnits) {
        return new Money(Math.multiplyExact(wholeUnits, 100));
    }
}
~~~

Lớp này là đoạn độc lập biên dịch được, chưa có `main`. Hai factory diễn đạt đơn vị khác nhau, nhưng cả hai đi qua constructor kiểm tra `cents >= 0`.

Đối với dữ liệu như tiền tệ, mô hình `long` theo đơn vị nhỏ nhất chỉ là **một chiến lược khi có quy định về đơn vị/độ lớn phù hợp**; nhiều hệ thống cần `BigDecimal`, mã tiền tệ, scale, rounding và các invariants khác.

### 7.2. Constructor chaining khác với factory gọi constructor

Trong constructor, Java cho phép `this(...)` để **ủy quyền sang constructor khác của cùng lớp** và `super(...)` để chọn constructor lớp cha:

~~~java
class Point {
    final int x;
    final int y;

    Point() {
        this(0, 0);
    }

    Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    static Point origin() {
        return new Point();
    }
}
~~~

Đây là khai báo lớp hợp lệ. `Point()` ủy quyền bằng `this(0,0)`; `origin()` là **static factory**, nó không thể tự gọi `this(0,0)` vì không phải constructor. Nó dùng `new Point()` để tạo đối tượng. Phân biệt này giúp đọc code đúng khi thấy các lời gọi trông gần giống nhau.

## 8. Constructor public hay private: quyết định ranh giới API

Có hai thiết kế API phổ biến:

**Thiết kế A — public constructor:**

~~~java
public class Customer {
    private final String id;

    public Customer(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    public String id() {
        return id;
    }
}
~~~

Caller có thể viết `new Customer("C01")`. Lớp này có một đường tạo chính, trực tiếp, dễ phát hiện trong IDE, phù hợp khi việc tạo đối tượng đơn giản và mỗi lần `new` nên cho một instance mới.

**Thiết kế B — private constructor + public named factory:**

~~~java
public final class Customer {
    private final String id;

    private Customer(String id) {
        this.id = java.util.Objects.requireNonNull(id);
    }

    public static Customer fromId(String id) {
        return new Customer(id);
    }

    public String id() {
        return id;
    }
}
~~~

Caller phải viết `Customer.fromId("C01")`. Nhà thiết kế API có thể thêm các factory tên rõ theo nguồn dữ liệu mà không cần mở public constructor.

Hai đoạn trên là **hai phiên bản thay thế** của lớp `Customer`, không khai báo đồng thời trong cùng source set. Nếu dùng public class, hãy lưu phiên bản được chọn vào `Customer.java`.

**Nhưng:** một factory không bắt buộc đi kèm private constructor; class có thể cung cấp cả public constructor lẫn static factories. Quyết định phụ thuộc vào yêu cầu tương thích API, khả năng mở rộng và mức độ kiểm soát khởi tạo.

### 8.1. Không thể ép caller bên ngoài bỏ qua mọi cơ chế tạo đối tượng

Private constructor hạn chế những lời gọi `new` trực tiếp theo quy tắc truy cập Java. Nó **không phải cơ chế bảo mật tuyệt đối**, và không đảm bảo mọi kỹ thuật deserialization, reflection được cấp quyền, framework, cloning hoặc cơ chế runtime khác đều bị loại bỏ. Khi dùng Java modules, việc phản chiếu còn phụ thuộc cấu hình access/module. Hãy dùng private constructor để **thiết kế API và đóng gói**, không để tuyên bố ranh giới an ninh tổng quát.

## 9. Chọn tên factory thế nào cho rõ ý định?

Các tên thông dụng dưới đây là **quy ước**, không phải từ khóa hay quy tắc bắt buộc của compiler:

| Tên gợi ý | Cách hiểu thường gặp | Ví dụ |
| --- | --- | --- |
| `of(...)` | Tạo/cung cấp một giá trị từ các thành phần rõ ràng | `LocalDate.of(2026, 10, 18)` |
| `from(...)` | Chuyển đổi từ một biểu diễn/đối tượng khác | `MyValue.from(raw)` |
| `valueOf(...)` | Tạo/chuyển thành một giá trị theo API | `Integer.valueOf("12")` |
| `parse(...)` / `parseX(...)` | Phân tích cú pháp văn bản thành giá trị | `LocalDate.parse("2026-10-18")` |
| `getInstance(...)` | Lấy một instance, có thể dùng cache/chia sẻ | `SomeService.getInstance()` |
| `newInstance(...)` | Gợi ý một instance mới, nếu contract thật sự cam kết vậy | `Session.newInstance(...)` |
| `create(...)` | Tạo/cung cấp đối tượng qua một bước khởi tạo có chủ đích | `Report.create(...)` |
| `getDefault()` / `defaultX()` | Trả giá trị mặc định có ý nghĩa rõ | `Settings.defaultSettings()` |
| `ofSeconds`, `ofMillis` | Nêu trực tiếp đơn vị/nguồn giá trị | `Duration.ofSeconds(5)` |

Đừng lạm dụng những tên quá chung như `make()` nếu người đọc không biết đối tượng được tạo bằng cách nào. Cũng không nên đặt tên `getInstance()` để ngầm hứa singleton nếu implementation thực tế tạo một instance mới mỗi lần và API không có hợp đồng như vậy.

**Phân biệt `of` và `from`:** một quy ước phổ biến là `of` từ những thành phần tạo giá trị và `from` từ một biểu diễn cùng ý nghĩa; nhưng nhiều thư viện dùng khác nhau. Sự nhất quán **trong cùng API** quan trọng hơn việc bám cứng một từ.

## 10. Kiểm tra null, input và exception ở hai cách tạo

Constructor và factory đều có thể validate tham số. Sự khác nhau chủ yếu là factory có thể cung cấp **nhiều entry points được đặt tên** cho các chính sách khác nhau.

Ví dụ standard library:

- `Optional.of(value)` không chấp nhận `null`.
- `Optional.ofNullable(value)` cho phép `null`, trả empty optional khi giá trị null.
- `List.of(...)` không cho phép phần tử `null` và kết quả không sửa được.
- `List.copyOf(collection)` tạo/cung cấp danh sách không sửa được từ collection, đồng thời không chấp nhận phần tử null theo hợp đồng.

Điều này giúp tên factory **diễn đạt chính sách đầu vào và kết quả**, thay vì bắt caller ghi nhớ những overload constructor cùng tên. Tuy vậy, chính sách thực tế vẫn phải được mô tả trong tài liệu và kiểm thử.

### 10.1. Factory có thể trả `null` không?

Về mặt ngôn ngữ, static method có return type tham chiếu **có thể trả `null`**. Nhưng nếu mục đích là API tạo đối tượng, trả `null` bất ngờ thường khiến caller khó dùng. Có thể:

- Ném ngoại lệ phù hợp khi dữ liệu không hợp lệ.
- Trả một kết quả có kiểu `Optional<T>` nếu **không tìm thấy** là khả năng bình thường và API muốn biểu diễn rõ.
- Trả một giá trị mặc định/đặc biệt có hợp đồng rõ ràng.
- Không trả `null` khi hợp đồng đã quy định luôn có đối tượng.

Không nên kết luận “factory bắt buộc luôn trả object khác null”; đó là **quyết định hợp đồng API**, không phải quy tắc của Java.

### 10.2. Trả subtype cũng phải giữ hợp đồng

Một factory khai báo kiểu trả về `Shape` có thể trả `Circle`, `Rectangle`, hoặc implementation private. Nhưng caller chỉ được dựa trên **hợp đồng `Shape`** (trừ khi kiểm tra/cast có lý do). Nếu factory đổi subtype ở một phiên bản mới, mã gọi phụ thuộc vào class cụ thể, object identity hoặc implementation detail có thể hỏng.

## 11. Chi phí và hạn chế của static factory

Static factory mang nhiều lợi ích, nhưng không phải lựa chọn tốt hơn constructor trong mọi tình huống.

### 11.1. Khó khám phá hơn trong một số API

Constructor nổi bật trong IDE và tài liệu API khi người dùng tìm `new ClassName(...)`. Static factory chỉ là một method bình thường; nếu tên mơ hồ, người học có thể không tìm thấy cách tạo đối tượng.

**Giải pháp:** đặt tên nhất quán, tài liệu hóa cách dùng, cung cấp ví dụ tạo object đầu tiên và thiết kế javadoc rõ ràng.

### 11.2. Có thể hạn chế khả năng kế thừa

Nếu lớp chỉ có **private constructors**, một class bên ngoài không thể subclass theo đường `super(...)` cần truy cập constructor của lớp cha. Đây có thể là **chủ đích** nếu kiểu là immutable/final, nhưng không phù hợp nếu framework hoặc người dùng cần kế thừa.

Không có nghĩa “class có static factory thì không thể được kế thừa”. Vấn đề là **constructor của lớp cha có truy cập được cho subclass hay không**. Một lớp có static factory và constructor `protected` vẫn có thể hỗ trợ kế thừa.

### 11.3. Static factory không được override như instance method

~~~java
class Base {
    static Base create() {
        return new Base();
    }
}

class Derived extends Base {
    static Derived create() {
        return new Derived();
    }
}
~~~

Đây là đoạn khai báo lớp hợp lệ trong Java 17; phương thức `Derived.create()` có cùng chữ ký và kiểu trả về tham chiếu tương thích, nên **hide** (che giấu) static method của `Base`, **không override động**. Tránh dựa vào receiver runtime để kỳ vọng static factory được dispatch giống instance method.

Nếu cần cơ chế tạo có thể thay thế bằng đa hình, hãy cân nhắc **instance factory interface**, **supplier**, dependency injection hoặc kiểu mẫu thiết kế phù hợp, thay vì giả định static method sẽ được override.

### 11.4. Tái sử dụng object không luôn tốt

Một instance dùng chung có thể giảm chi phí tạo object, nhưng nếu giữ trạng thái mutable hoặc tài nguyên có lifecycle như file handle/network connection thì cache tùy tiện dễ gây chia sẻ lỗi, memory leak hoặc concurrency bug. Một factory có trách nhiệm phù hợp với bối cảnh đôi khi phải **luôn tạo mới** và mô tả rõ phương thức đóng tài nguyên.

### 11.5. Thêm tầng gọi có thể khiến debug khó hơn

Nếu factory chứa validation, cache, chọn subtype và nhiều nhánh logic, việc tìm nguyên nhân lỗi có thể khó hơn một constructor đơn giản. Hãy giữ factory nhỏ, có contract rõ, có test cho từng nhánh và tránh giấu side effects không cần thiết.

## 12. Ví dụ chạy độc lập: phân biệt luôn tạo mới và tái sử dụng

Lưu thành **`FactoryIdentityDemo.java`**:

~~~java
public class FactoryIdentityDemo {
    static final class Token {
        private static final Token SHARED = new Token("SHARED");
        private final String value;

        private Token(String value) {
            this.value = value;
        }

        static Token shared() {
            return SHARED;
        }

        static Token create(String value) {
            return new Token(value);
        }

        String value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Token first = Token.shared();
        Token second = Token.shared();

        Token third = Token.create("SHARED");
        Token fourth = Token.create("SHARED");

        System.out.println("shared identity=" + (first == second));
        System.out.println("fresh identity=" + (third == fourth));
        System.out.println("same text=" + first.value().equals(third.value()));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac FactoryIdentityDemo.java
java FactoryIdentityDemo
~~~

Output:

~~~text
shared identity=true
fresh identity=false
same text=true
~~~

Giải thích: `shared()` luôn trả về static field `SHARED`; `create(...)` mỗi lần gọi một `new Token(...)`. Hai token mới có thể chứa cùng giá trị chuỗi nhưng không có cùng identity. Factory **có quyền quyết định chính sách khởi tạo**, và cách đặt tên nên thông báo chính sách đó rõ ràng.

Ở đây `Token` là kiểu bất biến ở mức fields: field `value` là final và `String` là immutable. Nhờ đó việc trả chung `SHARED` không tạo vấn đề thay đổi trạng thái của chính `Token`.

## 13. Ví dụ tích hợp: cả constructor công khai và named factory cùng tồn tại

Không có quy tắc bắt buộc một lớp phải chọn duy nhất một trong hai cách. Ví dụ một lớp tọa độ có constructor công khai và factory cho một giá trị thường dùng.

Lưu thành **`ConstructorAndFactoryDemo.java`**:

~~~java
public class ConstructorAndFactoryDemo {
    public static final class Point {
        private final int x;
        private final int y;

        public Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        public static Point origin() {
            return new Point(0, 0);
        }

        public static Point of(int x, int y) {
            return new Point(x, y);
        }

        public String describe() {
            return "(" + x + "," + y + ")";
        }
    }

    public static void main(String[] args) {
        Point a = new Point(3, 4);
        Point b = Point.of(3, 4);
        Point center = Point.origin();

        System.out.println("constructor=" + a.describe());
        System.out.println("factory=" + b.describe());
        System.out.println("origin=" + center.describe());
        System.out.println("same instance=" + (a == b));
    }
}
~~~

Lệnh:

~~~bash
javac ConstructorAndFactoryDemo.java
java ConstructorAndFactoryDemo
~~~

Output:

~~~text
constructor=(3,4)
factory=(3,4)
origin=(0,0)
same instance=false
~~~

`new Point(3,4)` và `Point.of(3,4)` cùng biểu diễn tọa độ `(3,4)`, nhưng trong implementation này factory gọi `new Point`, nên mỗi biểu thức trả **instance riêng**. Nếu business cần so sánh tọa độ **theo giá trị**, nên triển khai `equals`/`hashCode` nhất quán hoặc dùng kiểu value-oriented phù hợp (chẳng hạn một record nếu yêu cầu thiết kế cho phép). Không nên thay phép so sánh giá trị bằng `==`.

**Khi nào giữ cả hai?** Khi constructor đơn giản, dễ dùng và không gây nhầm, nhưng một vài giá trị có cách biểu diễn hữu ích qua tên factory (`origin`, `identity`, `zero`…). Nếu API cần kiểm soát chặt đường tạo, factory với private constructor có thể phù hợp hơn.

## 14. Phân biệt named static factory với các mẫu factory khác

Từ “factory” được dùng trong nhiều ngữ cảnh:

| Khái niệm | Ý tưởng | Có cần `static` không? |
| --- | --- | --- |
| **Named static factory method** | Một phương thức có tên của lớp/kiểu để cung cấp object, ví dụ `Point.of(...)` | Thường **có** |
| **Factory Method design pattern (GoF)** | Định nghĩa phương thức tạo sản phẩm để implementation/subclass có thể quyết định kiểu sản phẩm | Không bắt buộc; thường dựa trên đa hình instance |
| **Abstract Factory design pattern** | Một đối tượng factory cung cấp **họ sản phẩm liên quan** | Không bắt buộc; thường có interface factory |
| **Builder** | Lắp từng tham số cấu hình rồi `build()` object cuối | Builder là object; method `builder()` ban đầu có thể static |
| **Dependency Injection container** | Công cụ cấu hình và cung cấp object/dependencies theo scope và vòng đời | Tùy framework |

Ví dụ interface đơn giản cho một **instance factory** có thể được thay thế theo đa hình:

~~~java
interface Greeter {
    String greet();
}

interface GreeterFactory {
    Greeter create(String name);
}
~~~

Đây là hai interface hợp lệ, chưa có implementation. Một class cụ thể có thể triển khai `GreeterFactory.create(...)`; caller giữ tham chiếu tới `GreeterFactory` và thay đổi implementation tại runtime. Cơ chế này **khác** với phương thức `static Greeter of(String)` chỉ được gọi trên kiểu khai báo.

Không cần học trọn bộ design patterns để hiểu named factory. Với bài hiện tại, trọng tâm là **lựa chọn một API tạo đối tượng có tên rõ thay vì chỉ dựa vào constructor**.

## 15. Constructor reference và factory method reference

Trong Java 8+, cả constructor và static factory có thể được tham chiếu dưới dạng method reference khi kiểu hàm mục tiêu phù hợp.

Ví dụ trong một method của lớp có `Point`:

~~~java
java.util.function.BiFunction<Integer, Integer, Point> viaConstructor =
        Point::new;

java.util.function.BiFunction<Integer, Integer, Point> viaFactory =
        Point::of;
~~~

Đây là **đoạn minh họa**, cần lớp `Point` có constructor `Point(int,int)` và static `Point of(int,int)` truy cập được như ví dụ trước. Hai method references có thể được áp dụng trong ngữ cảnh functional interface; `Integer` trong `BiFunction` có thể được unbox thành `int` khi cần.

- `Point::new` là **constructor reference**.
- `Point::of` là **static method reference**.

Lập trình viên nên chọn tham chiếu mô tả đúng hợp đồng. Nếu factory có thể cache/chọn subtype, `Point::of` phản ánh chính sách đó; `Point::new` gắn với constructor cụ thể.

## 16. Lỗi phổ biến và hướng khắc phục

| Nhầm lẫn / lỗi | Điều đúng hoặc cách xử lý |
| --- | --- |
| “`of` là constructor có tên khác.” | `of` là **method**, thường `static`, có return type; constructor phải trùng tên lớp và không có return type. |
| “Factory không bao giờ dùng `new`.” | Nhiều factory vẫn gọi private/public constructor ở bên trong để tạo object. |
| “Mọi factory đều trả singleton.” | Factory có thể trả object mới hoặc reused instance; cần xem implementation/hợp đồng. |
| “`create(...)` bắt buộc tạo instance mới.” | Tên chỉ gợi ý; muốn cam kết phải định nghĩa trong API contract và giữ nhất quán. |
| “Hai constructor `Length(long meters)` và `Length(long mm)` khác chữ ký.” | Không. Tên tham số không phân biệt constructor overload. Dùng factory với tên đơn vị. |
| “Factory `private Constructor()` không cần constructor nào.” | Khi factory tạo instance mới, nó vẫn phải dùng đường khởi tạo hợp lệ; private constructor là một lựa chọn thường gặp. |
| “Return type của factory bắt buộc là chính lớp chứa nó.” | Không. Method có thể trả interface/base type hoặc subtype tương thích. |
| “Static factory được override động theo object runtime.” | Không. Static methods không dynamic dispatch như instance methods. |
| “Private constructor ngăn mọi hình thức tạo đối tượng tuyệt đối.” | Chỉ là quy tắc truy cập của Java với những ngoại lệ/ngữ cảnh runtime khác; không phải cơ chế bảo mật tổng quát. |
| “Tái sử dụng chung mutable instance lúc nào cũng tốt hơn.” | Có thể gây trạng thái chia sẻ và lỗi concurrent; cân nhắc immutability và ownership. |
| “Nếu có factory thì không thể subclass.” | Tùy quyền truy cập constructor của superclass và thiết kế lớp; không phải do sự tồn tại của factory. |
| “Factory tự kiểm tra mọi đầu vào.” | Chỉ kiểm tra khi implementation được viết như vậy; hãy có validation thật và test lỗi. |
| “`Point.of(3,4)` luôn bằng `new Point(3,4)` theo `==`.” | Không; identity phụ thuộc chính sách factory, hai lần `new` tạo instance riêng. |
| “Factory method giống Builder/Abstract Factory.” | Chúng là các cách tạo object có mục tiêu và cấu trúc khác nhau, không đồng nghĩa. |
| “Thêm factory là chắc chắn tương thích mọi API cũ.” | Nếu xóa/ẩn constructor public đã tồn tại, caller có thể không biên dịch lại được; cần cân nhắc compatibility. |

### 16.1. Tại sao không sửa API public bằng cách chuyển constructor thành private tùy tiện?

Giả sử phiên bản cũ công bố `public Book(String title)`, và caller đang dùng `new Book("Java")`. Nếu phiên bản sau đổi constructor đó thành `private` rồi chỉ giữ `Book.of("Java")`, **mã nguồn cũ không thể biên dịch lại** nếu không sửa lời gọi. Thay đổi public API cũng có thể phá compatibility nhị phân đối với những class đã biên dịch.

Nếu cần chuyển hướng sang factory, hãy cân nhắc **thêm factory trước**, giữ constructor cũ có thời gian chuyển đổi, đánh dấu deprecation khi phù hợp và cung cấp hướng dẫn migration. Khả năng tương thích là một phần quan trọng của thiết kế thư viện Java.

## 17. Checklist lựa chọn constructor hay factory

Khi thiết kế một kiểu dữ liệu, tự hỏi:

1. **Mỗi lần tạo có thật sự cần một instance mới không?** Nếu không, named factory giúp giữ quyền reuse/cache, nhưng phải mô tả identity semantics.
2. **Có nhiều cách tạo với cùng kiểu tham số nhưng khác ý nghĩa không?** Nếu có, tên `ofCelsius`, `ofFahrenheit`, `fromHex`, `fromId` dễ hiểu hơn những constructor giống chữ ký.
3. **Caller cần thấy implementation class cụ thể không?** Nếu không, factory trả interface/base type giúp đóng gói.
4. **Có trạng thái bất biến cần kiểm tra ở mọi con đường tạo không?** Dồn validation vào constructor/private method chung; factory chỉ điều phối cách tạo.
5. **Đối tượng có mutable state hoặc tài nguyên phải đóng không?** Đừng cache/chia sẻ tùy tiện; xác định ownership, lifecycle và thread safety.
6. **Bạn có yêu cầu public subclassing không?** Kiểm tra access của constructor và khả năng kế thừa.
7. **Tên factory có thể tìm thấy dễ dàng trong API không?** Tài liệu và ví dụ cần cho thấy cách tạo object thực tế.
8. **Bạn có cần giữ tương thích mã cũ không?** Không đột ngột xóa public constructor khi người dùng đang gọi `new`.
9. **Có đang thêm factory chỉ để che một constructor đơn giản không?** Nếu không mang giá trị về readability hoặc chính sách tạo, constructor công khai có thể đơn giản hơn.

**Kết luận lựa chọn:** Không có quy tắc “mọi constructor đều nên bị thay bằng static factory”. Constructor thích hợp khi cách tạo đơn giản, dữ liệu rõ ràng, không cần đổi subtype/caching. Named static factory đặc biệt có giá trị khi **cách tạo mang ý nghĩa nghiệp vụ cần đặt tên hoặc cần kiểm soát instance được cung cấp**.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `public static Book of(String title)` có phải constructor không?  
**Đáp án:** Không. Nó là method có tên `of`, kiểu trả về `Book`, modifier `static`. Constructor của `Book` phải mang tên `Book` và không khai báo kiểu trả về.

**Câu 2.** Vì sao hai constructor `Temperature(double celsius)` và `Temperature(double fahrenheit)` không thể cùng tồn tại trong một lớp?  
**Đáp án:** Chúng có cùng chữ ký `Temperature(double)`. Tên tham số không phân biệt overload; factory `ofCelsius(double)` và `ofFahrenheit(double)` truyền đạt ý nghĩa khác nhau.

**Câu 3.** `Settings.defaultSettings()` có bắt buộc mỗi lần tạo object mới không?  
**Đáp án:** Không. Factory có thể trả cùng cached instance nếu hợp đồng cho phép, như implementation minh họa.

**Câu 4.** `new Settings()` và `Settings.of(...)` khác nhau thế nào về khả năng caller gọi?  
**Đáp án:** `new Settings()` cần constructor không tham số truy cập được; `Settings.of(...)` cần static method tương ứng truy cập được. Một lớp có thể chỉ công bố factory và giấu constructors.

**Câu 5.** Factory khai báo `static Shape create()` có thể trả về một `Circle implements Shape` không?  
**Đáp án:** Có, nếu `Circle` là kiểu tương thích `Shape`, lớp đáp ứng hợp đồng và factory tạo/cung cấp được đối tượng đó.

**Câu 6.** `private Book(...)` có nghĩa không method nào của lớp `Book` được gọi constructor này không?  
**Đáp án:** Không. Chính lớp `Book` có thể gọi constructor private trong static factory của nó, ví dụ `return new Book(...);`.

**Câu 7.** Nếu cả `Book.of(...)` lẫn `new Book(...)` tạo ra object chứa cùng field values, phép `==` luôn trả true không?  
**Đáp án:** Không. `==` so identity; kết quả phụ thuộc instance cụ thể mà factory trả, không chỉ giá trị field.

**Câu 8.** Static factory `Base.create()` được subclass override động như instance method không?  
**Đáp án:** Không. Static methods không được override theo dynamic dispatch; trong class inheritance có thể xảy ra static method hiding theo quy tắc Java.

**Câu 9.** Vì sao `Optional.ofNullable(x)` là ví dụ tốt của named factory?  
**Đáp án:** Tên method làm rõ **chính sách xử lý null**, khác với `Optional.of(x)`, đồng thời cung cấp object `Optional` qua API có tên.

**Câu 10.** Factory trả chung một `ArrayList` mutable có thể có vấn đề gì?  
**Đáp án:** Caller có thể sửa danh sách chung và tác động các caller khác; cần quyết định ownership, defensive copy, unmodifiable view hoặc instance riêng tùy hợp đồng.

**Câu 11.** `Point::new` và `Point::of` có cùng là constructor reference không?  
**Đáp án:** Không. `Point::new` là constructor reference; `Point::of` là method reference tới static factory.

**Câu 12.** Lớp đã có `public Book(String title)`; bạn đổi thành `private` và công bố `Book.of(String)`. Người dùng cũ có phải sửa mã không?  
**Đáp án:** Có thể phải sửa, vì `new Book(...)` không còn truy cập được; đây là thay đổi API cần đánh giá compatibility và lộ trình migration.

## Ghi nhớ

**Constructor** có tên trùng lớp, không có kiểu trả về và được gọi qua `new` hoặc constructor chaining theo quy tắc Java. **Named static factory method** là một **phương thức có tên và kiểu trả về**, ví dụ `Length.ofMeters(2)`, `Settings.defaultSettings()` hoặc `Message.text("Hi")`. Factory có thể gọi private constructor để tạo mới, trả instance được tái sử dụng, chuyển đổi cách biểu diễn dữ liệu hoặc cung cấp một subtype thông qua interface.

Chọn **constructor** khi cách tạo đơn giản và minh bạch; chọn **named factory** khi cần tên diễn đạt ý nghĩa, validation theo nhiều đường vào, kiểm soát reuse/identity hoặc che giấu implementation. Dù chọn cách nào, API vẫn phải bảo đảm object được sử dụng trong trạng thái hợp lệ, có hợp đồng rõ ràng và không vô tình chia sẻ mutable state.
