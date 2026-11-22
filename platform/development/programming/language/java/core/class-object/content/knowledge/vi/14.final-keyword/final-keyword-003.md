# Trường `final` chưa có giá trị và nơi được phép gán trong Java

Từ khóa `final` có ý nghĩa đặc biệt khi áp dụng cho **trường (field)** của một lớp: sau khi trường được gán hợp lệ trong giai đoạn khởi tạo, chương trình Java thông thường **không thể gán lại trường đó**. Nhưng không phải trường `final` nào cũng cần nhận giá trị ngay trên dòng khai báo. Java cho phép khai báo một trường `final` **không có biểu thức khởi tạo**, thường gọi là **blank final field**.

Ví dụ:

~~~java
final class Book {
    private final String isbn;

    Book(String isbn) {
        this.isbn = isbn;
    }

    String isbn() {
        return isbn;
    }
}
~~~

`isbn` không có giá trị được chỉ định tại dòng khai báo, nhưng constructor gán nó trong quá trình tạo từng object `Book`. Sau khi object được tạo thành công, không có setter nào được phép gán lại `isbn` theo luật gán của `final`.

Bài này thuộc Java Core — **class-object**, phần **Từ khóa final**, tập trung vào những câu hỏi thực tế: *blank final* là gì; trường instance khác trường `static` như thế nào; được phép gán trong initializer, constructor và static initializer ra sao; compiler kiểm tra mọi nhánh như thế nào; và cần tránh những sai lầm nào khi thiết kế object bất biến. Ví dụ độc lập dùng **Java 17+**.

## 1. `final` trên trường bảo đảm điều gì?

Một trường có thể được khai báo như sau:

~~~java
private final int maxItems = 20;
private final String code;
private static final String APP_NAME = "Library";
private static final int DEFAULT_PORT;
~~~

Đây là **những khai báo minh họa** thuộc một class, chưa phải chương trình độc lập. Chúng thuộc hai nhóm:

| Khai báo | Loại trường | Có initializer trên dòng khai báo? |
| --- | --- | --- |
| `final int maxItems = 20` | Instance field | Có |
| `final String code;` | **Blank final instance field** | Không |
| `static final String APP_NAME = "Library"` | Static field | Có |
| `static final int DEFAULT_PORT;` | **Blank final static field** | Không |

Khi một trường `final` được gán bằng cách mà Java cho phép, mã Java thông thường không thể tiếp tục gán một giá trị khác vào **chính field đó**. Đây là giới hạn đối với **phép gán field**, không phải cam kết rằng mọi object được field tham chiếu đều bất biến.

Ví dụ, `final List<String> names` giữ cố định **tham chiếu field** sau khởi tạo, nhưng một `ArrayList` do field tham chiếu tới vẫn có thể bị `add`, `remove` hoặc `clear` nếu API và quyền sở hữu cho phép.

**Không đồng nhất `final` với `const` của mọi ngôn ngữ khác.** Trong Java, một trường `final` có thể nhận giá trị chỉ xác định tại runtime, chẳng hạn mã đơn hàng do constructor kiểm tra và lưu lại. Nó không nhất thiết là **hằng số compile-time**.

## 2. Blank final là gì?

**Blank final field** là một trường có modifier `final` nhưng **không có initializer ngay trong khai báo**.

~~~java
class Profile {
    private final String username; // Blank final instance field.

    Profile(String username) {
        this.username = username;
    }
}
~~~

Khác với:

~~~java
class FixedProfile {
    private final String username = "guest";
}
~~~

Trong `FixedProfile`, field đã có initializer; đây **không** phải blank final field. Trong `Profile`, mỗi lần `new Profile(value)` cung cấp giá trị khác nhau khi xây dựng object.

Điểm rất quan trọng: **“blank” không đồng nghĩa bộ nhớ của field hoàn toàn không có giá trị ở mọi thời điểm.** Trước khi các initializer và constructor chạy, vùng lưu trữ instance field được khởi tạo mặc định theo ngữ nghĩa Java (ví dụ `null` cho reference, `0` cho `int`). Tuy nhiên, **compiler bắt buộc** các blank final field được **gán chắc chắn** trước khi đường khởi tạo liên quan kết thúc bình thường. Không được coi giá trị mặc định đó như một cách hợp lệ để bỏ qua phép gán bắt buộc.

Một lớp với blank final field thường thích hợp khi:

- Mỗi object cần một mã hoặc thông số riêng, được truyền qua constructor.
- Object có invariant phải kiểm tra trước khi nhận giá trị cuối cùng.
- Có nhiều constructor overload, nhưng tất cả đều phải thiết lập đầy đủ trường bất biến.
- Một giá trị static chỉ tính được khi class initialization chạy thay vì khai báo bằng biểu thức đơn giản.

## 3. Những vị trí được phép gán: bản đồ nhanh

| Trường | Vị trí có thể gán lần đầu | Không được gán ở đâu? |
| --- | --- | --- |
| Blank final **instance** | Instance initializer block hoặc constructor của **lớp khai báo field** | Instance method thông thường, setter, constructor subclass, lambda chạy về sau |
| Blank final **static** | Static initializer block của **lớp khai báo field** | Constructor, instance initializer, method static thông thường, method instance |
| Final field **có initializer** | Đã gán trong biểu thức khai báo | Không được gán lần nữa trong constructor/static initializer |
| Biến local `final` | Theo các quy tắc definite assignment dành cho biến local | Không phải cùng quy tắc vị trí với blank final **field** |

Hãy phân biệt hai lớp quy tắc:

1. **Vị trí hợp lệ:** pháp luật ngôn ngữ cho phép phép gán diễn ra ở đâu.
2. **Definite assignment (DA) / definite unassignment (DU):** compiler chứng minh trường **đã được gán trước khi hoàn tất**, và **chưa từng được gán ở đường đi hiện tại trước phép gán mới**.

Không phải cứ đặt câu lệnh gán trong constructor là mặc nhiên hợp lệ. Nếu có một constructor khác chưa gán, một nhánh `if` bị bỏ sót, hoặc field đã được gán trong initializer trước đó, chương trình vẫn có thể không biên dịch.

## 4. Ví dụ hoàn chỉnh: blank final instance field qua constructor

Tạo tệp **`BlankFinalInstanceDemo.java`**:

~~~java
import java.util.Objects;

final class Ticket {
    private final String code;
    private final int priority;

    Ticket(String code) {
        this(code, 1);
    }

    Ticket(String code, int priority) {
        Objects.requireNonNull(code, "code");
        if (code.isBlank()) {
            throw new IllegalArgumentException("code rỗng");
        }
        if (priority < 1 || priority > 5) {
            throw new IllegalArgumentException("priority ngoài 1..5");
        }

        this.code = code.strip();
        this.priority = priority;
    }

    String label() {
        return code + "/" + priority;
    }
}

public class BlankFinalInstanceDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket("  AB-01  ");
        Ticket second = new Ticket("CD-02", 3);

        System.out.println("first=" + first.label());
        System.out.println("second=" + second.label());

        try {
            new Ticket(" ", 2);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        System.out.println("still=" + first.label());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 BlankFinalInstanceDemo.java
java BlankFinalInstanceDemo
~~~

**Stdout chính xác:**

~~~text
first=AB-01/1
second=CD-02/3
rejected=code rỗng
still=AB-01/1
~~~

### Vì sao chương trình hợp lệ?

- `Ticket.code` và `Ticket.priority` đều là **blank final instance fields**.
- Constructor hai tham số kiểm tra dữ liệu, sau đó **gán chính xác một lần trên đường khởi tạo thành công** vào từng field.
- Constructor một tham số gọi `this(code, 1)` để ủy quyền khởi tạo. Nó **không gán lại** hai trường sau khi constructor đích hoàn thành.
- Khi `code` toàn khoảng trắng, constructor ném `IllegalArgumentException` trước khi trả về object. Không có object `Ticket` được tạo thành công cho caller từ lời gọi ấy.
- Object `first` và `second` có giá trị trường `final` riêng, vì `final` không có nghĩa mọi instance phải có cùng giá trị.

**Giá trị khác nhau giữa các object là hoàn toàn hợp lệ.** `final` bảo vệ việc gán lại một field **trên chính một object**, không biến nó thành field static được chia sẻ giữa mọi object.

## 5. Constructor chaining với `this(...)`

Nếu có nhiều constructors, một cách tập trung khởi tạo là dùng `this(...)` để ủy quyền về **constructor đích duy nhất** gán blank final fields:

~~~java
final class ConnectionConfig {
    private final String host;
    private final int port;

    ConnectionConfig() { this("localhost", 8080); }
    ConnectionConfig(String host) { this(host, 8080); }

    ConnectionConfig(String host, int port) {
        if (host == null || host.isBlank() || port < 1 || port > 65535)
            throw new IllegalArgumentException("config");
        this.host = host;
        this.port = port;
    }
}
~~~

`this(...)` phải ở vị trí constructor invocation hợp lệ của Java 17, không được tạo chu trình và constructor ủy quyền không gán lại fields của constructor đích. Trọng tâm bài này là **nơi được phép thực hiện phép gán**; chứng minh definite assignment cho từng constructor path, nhánh return/throw và bảng luồng điều khiển được giải thích đầy đủ ở bài B144.

## 6. Kiểm tra mọi đường đi: definite assignment

Compiler Java áp dụng **definite assignment (DA)** và **definite unassignment (DU)**: không đủ nếu chỉ thấy một phép gán trong source; các đường thực thi và số lần có thể gán phải hợp lệ.

~~~java
class Valid {
    private final int code;
    Valid(boolean flag) {
        code = flag ? 1 : 2; // Gán đúng một lần.
    }
}
~~~

Một constructor có thể `throw` trước khi khởi tạo xong; nhưng không được **hoàn tất bình thường** khi blank final field chưa được gán. B144 là nơi dạy chi tiết phân tích nhánh; hãy dùng quy tắc này khi xác định constructor/initializer có được phép gán field hay không.

## 7. Ví dụ chạy được: gán qua các nhánh hợp lệ

Tạo tệp **`BranchFinalDemo.java`**:

~~~java
final class TargetRoute {
    private final String destination;

    TargetRoute(boolean offline) {
        if (offline) {
            destination = "LOCAL";
        } else {
            destination = "REMOTE";
        }
    }

    String destination() {
        return destination;
    }
}

public class BranchFinalDemo {
    public static void main(String[] args) {
        TargetRoute local = new TargetRoute(true);
        TargetRoute remote = new TargetRoute(false);

        System.out.println("offline=" + local.destination());
        System.out.println("online=" + remote.destination());
        System.out.println("again=" + local.destination());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BranchFinalDemo.java
java BranchFinalDemo
~~~

**Stdout:**

~~~text
offline=LOCAL
online=REMOTE
again=LOCAL
~~~

Có hai câu lệnh gán `destination = ...` trong source nhưng **chỉ một nhánh chạy cho mỗi lần tạo object**. Compiler có thể chứng minh rằng mỗi đường khởi tạo bình thường gán trường đúng một lần.

Ngược lại, nếu viết hai câu lệnh gán trên **cùng đường thực thi**:

~~~java
class DoubleAssignment {
    private final int number;

    DoubleAssignment() {
        number = 1;
        number = 2; // LỖI BIÊN DỊCH: field final đã được gán.
    }
}
~~~

thì compiler từ chối. Đây là ví dụ **cố ý không biên dịch**, không phải class cần chạy.

## 8. Instance initializer block có thể gán blank final instance field

Không bắt buộc mọi blank final instance field phải được gán trực tiếp trong thân constructor. **Instance initializer block** cũng có thể gán một field final còn blank:

~~~java
final class RecordStamp {
    private final int formatVersion;
    private final String key;

    {
        formatVersion = 2;
    }

    RecordStamp(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("key không hợp lệ");
        }
        this.key = key;
    }

    String describe() {
        return key + "@v" + formatVersion;
    }
}
~~~

Đây là **lớp minh họa hợp lệ**. Trường `formatVersion` không có initializer tại dòng khai báo, nhưng block instance gán `2` khi object được khởi tạo. Trường `key` được gán trong constructor.

**Thứ tự khởi tạo liên quan:** trong chuỗi khởi tạo object bình thường, phần khởi tạo superclass hoàn thành trước các instance field initializer/instance initializer của lớp con; các initializer thuộc một lớp chạy theo thứ tự xuất hiện trong source, rồi mới đến phần thân constructor thực sự của lớp đó (ngoại trừ việc constructor có thể ủy quyền bằng `this(...)` theo cơ chế đặc biệt).

Vì vậy, nếu `formatVersion` đã được gán trong instance initializer, **không được gán thêm** `formatVersion = 3;` trong constructor. Còn `key` vẫn cần được gán trên mọi đường constructor kết thúc bình thường.

Một static nested class hay inner class cũng tuân quy tắc gán field final **của chính lớp đó**. Việc nó nằm trong lớp bao không tự cho phép constructor của lớp bao đi gán blank final field khai báo trong một kiểu lồng khác.

## 9. `static final` chưa có initializer: chỉ gán trong static initializer thích hợp

Với trường class-level:

~~~java
private static final int BUFFER_SIZE;
~~~

đây là **blank final static field**. Nó thuộc **lớp**, không thuộc từng instance, nên constructor instance không phải nơi để gán nó.

Cách thông dụng là một **static initializer block**:

~~~java
private static final int BUFFER_SIZE;

static {
    int configured = 1024;
    if (configured <= 0) {
        throw new ExceptionInInitializerError("BUFFER_SIZE phải dương");
    }
    BUFFER_SIZE = configured;
}
~~~

Đây là đoạn khai báo minh họa trong một class. Phép gán `BUFFER_SIZE = configured` nằm trong static initializer của **lớp khai báo field**. Compiler yêu cầu blank final static field được gán chắc chắn khi phần static initialization của lớp hoàn tất bình thường và không bị gán lần thứ hai.

Phân biệt:

- `static final int LIMIT = 100;`: có field initializer, không phải blank final.
- `static final int LIMIT; static { LIMIT = 100; }`: blank final, gán trong static initializer.
- `static final int LIMIT; static void init() { LIMIT = 100; }`: **không hợp lệ** với phép gán field final trong static method thông thường, dù method chỉ định được gọi một lần.
- `static final int LIMIT; SomeClass() { LIMIT = 100; }`: cũng **không hợp lệ**; constructor tạo instance không được gán blank final static field.

**Lưu ý:** `static` không có nghĩa “có thể gán bất cứ lúc nào qua class name”. `static final` vẫn yêu cầu gán trong vùng khởi tạo cho phép và tuân DA/DU.

## 10. Chương trình chạy được: khởi tạo blank final static fields

Tạo tệp **`BlankFinalStaticDemo.java`**:

~~~java
import java.util.Locale;

final class RuntimeDefaults {
    private static final String PROFILE;
    private static final int RETRIES;

    static {
        String rawProfile = "production";
        String checkedProfile = rawProfile.strip()
                .toUpperCase(Locale.ROOT);

        if (checkedProfile.isEmpty()) {
            throw new ExceptionInInitializerError("profile rỗng");
        }

        PROFILE = checkedProfile;
        RETRIES = "PRODUCTION".equals(PROFILE) ? 3 : 1;
    }

    static String profile() {
        return PROFILE;
    }

    static int retries() {
        return RETRIES;
    }
}

public class BlankFinalStaticDemo {
    public static void main(String[] args) {
        System.out.println("profile=" + RuntimeDefaults.profile());
        System.out.println("retries=" + RuntimeDefaults.retries());
        System.out.println("again=" + RuntimeDefaults.profile());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 BlankFinalStaticDemo.java
java BlankFinalStaticDemo
~~~

**Stdout:**

~~~text
profile=PRODUCTION
retries=3
again=PRODUCTION
~~~

Cơ chế:

1. Khi class `RuntimeDefaults` được khởi tạo lần đầu theo quy tắc của Java, static initializer chạy.
2. Mã chuẩn hóa và kiểm tra profile, sau đó gán `PROFILE` và `RETRIES`.
3. Các lời gọi method `profile()`, `retries()` đọc hai field đã được gán.
4. `RuntimeDefaults` được khởi tạo theo cơ chế class initialization của JVM, **không chạy lại static initializer mỗi lần gọi method**.

Đây là ví dụ có dữ liệu đầu vào cố định để stdout xác định. Trong ứng dụng thật, `rawProfile` có thể xuất phát từ cấu hình runtime, nhưng việc đọc cấu hình và xử lý lỗi cần được thiết kế rõ. Một lỗi tại thời điểm khởi tạo class có thể khiến class không sẵn sàng dùng, nên tránh đặt logic phức tạp, tác dụng phụ khó kiểm soát hoặc phụ thuộc chu kỳ trong static initializer.

## 11. Static initializer cũng phải bao phủ mọi nhánh

Ví dụ **không biên dịch**:

~~~java
class BrokenStatic {
    private static final String MODE;

    static {
        boolean valid = false;
        if (valid) {
            MODE = "ACTIVE";
        }
        // Đường đi không gán MODE: lỗi definite assignment.
    }
}
~~~

Tương tự constructor instance, compiler phải có cơ sở rằng blank final static field được **gán chắc chắn** trước khi static initializer của lớp hoàn tất bình thường.

Cách tốt hơn:

~~~java
final class SafeStatic {
    private static final String MODE;

    static {
        boolean enabled = false;
        MODE = enabled ? "ACTIVE" : "INACTIVE";
    }

    static String mode() {
        return MODE;
    }
}
~~~

Đây là lớp minh họa hợp lệ. Biểu thức điều kiện tạo ra một giá trị, còn `MODE` được gán **một lần**.

Có thể phân chia các phép gán giữa nhiều static initializer blocks trong cùng class nếu compiler vẫn chứng minh được các điều kiện DA/DU; các block thực thi theo thứ tự văn bản khai báo. Nhưng nếu logic khởi tạo khó theo dõi, gom việc tính thành **biến cục bộ trong một static block** rồi gán field cuối cùng thường giúp dễ bảo trì.

## 12. Field initializer và constructor: chọn một nơi gán

Đối với field instance final, hai cách này đều hợp lệ **nếu chọn một cách phù hợp**:

~~~java
class InlineLimit {
    private final int limit = 10;
}
~~~

và:

~~~java
class ConstructorLimit {
    private final int limit;

    ConstructorLimit() {
        limit = 10;
    }
}
~~~

Nhưng đoạn sau **không biên dịch**:

~~~java
class WrongLimit {
    private final int limit = 10;

    WrongLimit() {
        limit = 20; // Lỗi: final field đã có initializer.
    }
}
~~~

Các ví dụ ở mục này là **các lớp khác nhau**, nhằm minh họa các lựa chọn độc lập. Lý do chọn:

- **Initializer tại khai báo:** giá trị cố định hoặc dễ diễn đạt, áp dụng đồng nhất cho mọi object; bớt lặp giữa constructors.
- **Constructor:** giá trị phụ thuộc đối số, cần kiểm tra invariant, hoặc chỉ biết lúc tạo object.
- **Instance initializer:** logic chung cho nhiều constructor, nhưng thường kém rõ ràng hơn việc dùng field initializer hoặc constructor trung tâm khi không thật sự cần một block riêng.
- **Static initializer:** phù hợp với blank final **class variable** cần tính/kiểm tra trong giai đoạn khởi tạo class.

Không nên tạo blank final chỉ vì muốn dời một initializer đơn giản vào block dài hơn: cách viết ngắn, dễ đọc là ưu tiên nếu vẫn biểu diễn đúng yêu cầu.

## 13. Method thông thường không được “lấp chỗ trống” của blank final field

Một nhầm lẫn thường gặp là định nghĩa method `initialize()` rồi gọi từ constructor:

~~~java
class BrokenInitializer {
    private final String token;

    BrokenInitializer(String token) {
        initialize(token);
    }

    private void initialize(String value) {
        token = value; // Lỗi biên dịch: không thể gán field final tại đây.
    }
}
~~~

Đây là ví dụ **cố ý không biên dịch**. Mặc dù `initialize` là `private` và chỉ có constructor gọi nó, Java **không cho phép** dùng phép gán thông thường vào blank final instance field từ một instance method. Compiler không dựa trên giả định “method chỉ được gọi đúng một lần”.

Thay vào đó, có thể **tính và kiểm tra giá trị trong helper**, rồi gán chính field từ constructor:

~~~java
final class SafeInitializer {
    private final String token;

    SafeInitializer(String value) {
        token = checkedToken(value);
    }

    private static String checkedToken(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("token không hợp lệ");
        }
        return value.strip();
    }

    String token() {
        return token;
    }
}
~~~

Đây là một lớp minh họa hợp lệ. Helper `checkedToken` **trả về một giá trị** và không cố gán field final; constructor thực hiện `token = checkedToken(value)` tại nơi được phép.

Mẫu này hữu ích khi nhiều constructor dùng chung quy tắc validation: **tách tính toán khỏi phép gán cuối cùng**, chứ không chuyển phép gán field final vào method thông thường.

## 14. Constructor ném exception và bảo đảm khởi tạo hoàn chỉnh

Constructor ném exception không tạo một instance hoàn chỉnh cho caller, nên không bắt buộc gán field final trên đường **kết thúc bất thường**. Nhưng nếu bắt lỗi và tiếp tục đến cuối constructor, mọi blank final fields vẫn phải thỏa DA.

Một quy trình dễ kiểm tra: validate input → tính kết quả vào locals → gán fields đúng một lần trong constructor/initializer được phép. Cần tránh công bố `this` trước khi các invariants đã sẵn sàng; các bảo đảm final-field visibility không biến object đang khởi tạo dở thành an toàn.

## 15. Field `final` không nhất thiết là hằng số compile-time

Cân nhắc:

~~~java
class Limits {
    static final int FIXED = 16;
    static final int RUNTIME;

    static {
        RUNTIME = 16;
    }
}
~~~

Đây là lớp minh họa hợp lệ. Cả hai trường đều là `static final int`, nhưng có khác biệt quan trọng:

- `FIXED` được khởi tạo bằng một **constant expression** có kiểu primitive `int`; nó là một **constant variable** theo JLS.
- `RUNTIME` là **blank final static field**, nhận giá trị trong static block. Dù sau khi khởi tạo cũng bằng 16, nó **không phải constant variable** vì không có initializer tại khai báo.

Phân biệt này có thể ảnh hưởng tới việc compiler dùng hằng số tại nơi gọi, những chỗ đòi constant expression và hiện tượng *inlining* của một số `static final` constants.

Ví dụ:

~~~java
static final int PORT = 8080; // Constant variable.
static final int DYNAMIC_PORT;
static {
    DYNAMIC_PORT = Integer.parseInt("8080");
}
~~~

Đây là các khai báo minh họa trong class. `DYNAMIC_PORT` là giá trị được tính khi class initialization chạy; **không thể coi nó như một constant expression** chỉ vì kết quả cuối cùng là 8080.

**Đừng thay nhầm khái niệm:** `final` hạn chế gán lại; `static` chỉ mức thuộc về lớp; **constant variable** là khái niệm có điều kiện chặt hơn, cần initializer kiểu constant expression. Một blank final field vốn không đáp ứng điều kiện ấy.

## 16. `final` trên tham chiếu khác với object bất biến

Tạo tệp độc lập **`FinalReferenceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

final class Notes {
    private final List<String> items;

    Notes(List<String> items) {
        this.items = List.copyOf(items);
    }

    List<String> items() {
        return items;
    }
}

public class FinalReferenceDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>(List.of("Java"));
        Notes notes = new Notes(input);

        input.add("OOP");
        System.out.println("source=" + input);
        System.out.println("notes=" + notes.items());

        try {
            notes.items().add("unsafe");
        } catch (UnsupportedOperationException ex) {
            System.out.println("items cannot be changed");
        }

        System.out.println("again=" + notes.items());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FinalReferenceDemo.java
java FinalReferenceDemo
~~~

**Stdout:**

~~~text
source=[Java, OOP]
notes=[Java]
items cannot be changed
again=[Java]
~~~

Đối với `Notes`:

- `items` là **blank final instance field**, được gán trong constructor.
- `List.copyOf(items)` cho ra một danh sách không hỗ trợ thay đổi qua API, ngăn caller sửa danh sách đầu vào rồi khiến field này nhìn thấy phần tử mới được thêm.
- Getter trả về một danh sách không hỗ trợ sửa, nên `add` ném `UnsupportedOperationException`.
- Nếu thay constructor bằng `this.items = items;` và `items` là `ArrayList`, field vẫn `final` nhưng caller có thể sửa list gốc và làm thay đổi các phần tử được quan sát qua field.

`List.copyOf` không thực hiện **deep copy** các đối tượng phần tử mutable. Ví dụ dùng `String` bất biến nên phù hợp. Khi field final trỏ tới mảng, `final int[] values` cũng **không khóa từng phần tử mảng**; nếu cần độc lập, sao chép phòng vệ ở cả đầu vào và đầu ra.

Đây là lý do `final` là công cụ **giới hạn phép gán lại field**, nhưng **đóng gói và bất biến** còn cần kiểm soát object graph, alias và mọi đường cập nhật.

## 17. Field final được gán trong superclass có được gán ở subclass?

Nếu một blank final field được khai báo trong superclass, constructor của **chính superclass** phải đáp ứng quy tắc khởi tạo trường ấy. Subclass không được tự gán lại field final của superclass.

Ví dụ:

~~~java
class BaseDocument {
    private final String documentId;

    BaseDocument(String documentId) {
        if (documentId == null || documentId.isBlank()) {
            throw new IllegalArgumentException("documentId rỗng");
        }
        this.documentId = documentId;
    }

    String documentId() {
        return documentId;
    }
}

class Invoice extends BaseDocument {
    private final long cents;

    Invoice(String documentId, long cents) {
        super(documentId);
        if (cents < 0) {
            throw new IllegalArgumentException("cents âm");
        }
        this.cents = cents;
    }

    long cents() {
        return cents;
    }
}
~~~

Hai lớp trên là một đoạn minh họa hợp lệ. Lớp `BaseDocument` gán `documentId`; lớp `Invoice` gọi `super(documentId)` để superclass khởi tạo phần của nó, rồi `Invoice` gán blank final field `cents` **do chính nó khai báo**.

Đối với constructor Java 17, nếu superclass không có constructor không tham số phù hợp thì subclass phải gọi một constructor superclass có sẵn một cách hợp lệ. Không được hy vọng “sẽ gán field final của BaseDocument từ Invoice về sau”, kể cả khi field là `protected final`: phép gán trong subclass vẫn không thay thế được trách nhiệm khởi tạo của lớp khai báo.

**Quyền truy cập và quyền gán lại là hai quy tắc khác nhau.** Một subclass có thể được phép *đọc* field `protected final` theo điều kiện của `protected`, nhưng không có nghĩa được quyền gán lại.

## 18. Record và blank final fields: có điểm liên quan gì?

Trong Java 17, một `record` có những **record components**, được biểu diễn trong trạng thái của record thông qua các field `private final` theo các quy tắc riêng. Constructor canonical của record chịu trách nhiệm thiết lập các component tương ứng.

Ví dụ:

~~~java
record Money(long cents) {
    Money {
        if (cents < 0) {
            throw new IllegalArgumentException("cents âm");
        }
    }

    Money add(long extra) {
        if (extra < 0) {
            throw new IllegalArgumentException("extra âm");
        }
        return new Money(Math.addExact(cents, extra));
    }
}
~~~

Đây là record minh họa hợp lệ. Compact canonical constructor `Money { ... }` cho phép kiểm tra `cents`; Java áp dụng cơ chế gán các component fields của record sau phần thân compact constructor theo quy tắc record, nên không cần tự viết `this.cents = cents;`.

Không nên nhầm rằng **mọi record component phải được khởi tạo y hệt một blank final field do người học tự khai báo trong ordinary class**. Record có **quy tắc constructor đặc thù**, và người dùng không được khai báo thêm instance fields tùy ý trong record.

Nếu muốn ví dụ trực quan về tự gán blank final field trong constructor, dùng một class thông thường như `Ticket` hoặc `UserKey` sẽ rõ hơn. Record thích hợp để biết cách Java giúp mô hình hóa value object bất biến.

## 19. Static blank final và thứ tự khởi tạo class

Các static field initializer và static initializer blocks được thực thi theo **thứ tự văn bản** trong quá trình class initialization phù hợp. Vì vậy:

~~~java
final class StaticOrder {
    private static final int VALUE;

    static {
        int source = 10;
        VALUE = source * 2;
    }

    static int value() {
        return VALUE;
    }
}
~~~

là lớp hợp lệ: `VALUE` được gán trong static initializer và có giá trị 20 sau khi class initialization hoàn tất.

Rủi ro không nằm ở việc dùng static block tự nó, mà ở **độ phức tạp của logic phụ thuộc**:

- Một static initializer gọi tới lớp khác có thể kích hoạt class initialization liên quan.
- Phụ thuộc vòng giữa các lớp/field static có thể tạo tình huống khó dự đoán hoặc giá trị quan sát quá sớm.
- Exception trong khởi tạo class có thể khiến các lần sử dụng tiếp theo thất bại; không nên giả định lỗi chỉ ảnh hưởng một object như khi constructor ném lỗi.
- Những thao tác I/O hoặc môi trường có thể thất bại; cần quyết định có chấp nhận class khởi tạo lỗi hay nên dời việc thiết lập cấu hình sang cơ chế riêng.

Với một giá trị đơn giản và không cần nhánh/phép kiểm tra, initializer ngay tại khai báo thường rõ ràng hơn static block. Static block có ích khi phải kiểm tra, chuẩn hóa hoặc xử lý nhiều giá trị **trước khi gán lần cuối**.

## 20. `final`, thread safety và việc công bố `this` quá sớm

Java Memory Model có các bảo đảm riêng cho **final fields của những object được khởi tạo đúng cách**, với điều kiện quan trọng là tham chiếu object không bị công bố quá sớm trong quá trình tạo.

Ví dụ thiết kế tốt:

~~~java
final class SessionKey {
    private final String key;

    SessionKey(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("key không hợp lệ");
        }
        this.key = key;
    }

    String key() {
        return key;
    }
}
~~~

Constructor thiết lập field trước khi trả về. Caller có thể dùng một cơ chế **safe publication** phù hợp khi chia sẻ object cho các luồng khác.

Ngược lại, trong constructor, không nên đăng ký `this` làm listener hoặc khởi động thread có khả năng đọc `key` **trước khi field được gán**. Điều này có thể lộ trạng thái khởi tạo dở và phá các điều kiện cần để dựa vào ngữ nghĩa final-field initialization an toàn.

**Cần phân biệt:**

- Blank final instance field được compiler kiểm tra **definite assignment**.
- `final` không làm các object con mutable trở nên bất biến.
- `final` không biến mọi method thành atomic hay thread-safe.
- Dùng object bất biến và công bố đúng cách giúp giảm rủi ro đồng thời, nhưng các trạng thái mutable chia sẻ giữa luồng vẫn cần cơ chế bảo vệ riêng.

Bài toán này khác với việc field chỉ có đúng một phép gán ở source: **một phép gán hợp lệ về cú pháp chưa tự chứng minh toàn bộ vòng đời object an toàn**.

## 21. Các lỗi biên dịch và hiểu nhầm thường gặp

| Trường hợp | Vì sao không đúng? | Cách sửa |
| --- | --- | --- |
| `final String id;` nhưng constructor không gán | Không definite assignment trước kết thúc bình thường | Gán trên mọi đường constructor |
| Gán field final hai lần trong cùng constructor | Vi phạm definite unassignment | Chọn một phép gán |
| Đã gán field final tại khai báo, constructor lại gán | Field không còn blank và đã được gán | Dùng một nơi khởi tạo |
| Một nhánh `if` gán, nhánh còn lại bỏ trống | Có đường hoàn thành bình thường mà field chưa gán | Gán ở cả hai nhánh hoặc tính một giá trị chung |
| `final` field được setter gán lần đầu | Gán final field ngoài constructor/initializer không hợp lệ | Tính giá trị trước và gán trong constructor |
| Gọi `initialize()` để method gán blank final field | Phép gán xảy ra trong method thông thường | Helper trả giá trị, constructor gán field |
| Blank `static final` được gán từ constructor | Static field không thuộc từng instance và không được gán ở đó | Static initializer block |
| Blank `static final` được gán từ static method | Static method thường không phải vị trí gán hợp lệ | Tính trong helper rồi static block gán |
| Gán field final của lớp cha trong constructor lớp con | Field thuộc phạm vi khởi tạo của lớp khai báo | Superclass constructor gán |
| Coi blank final là luôn null/0 sau khi tạo thành công | Compiler yêu cầu gán trước kết thúc bình thường | Hiểu DA/DU, không dựa vào mặc định |
| Coi `final List` là list không thể sửa | Final bảo vệ tham chiếu field, không khóa object | Dùng defensive copy/immutable collections |
| Coi `static final` luôn là compile-time constant | Blank final gán trong block không phải constant variable | Phân biệt initializer bằng constant expression |
| Dùng constructor public nhưng lộ `this` trước khi gán | Object có thể bị quan sát dở dang | Không publish object trong constructor |
| Gán field final rồi mong thay bằng setter để cấu hình | Không thể gán lại theo đường thông thường | Tạo object mới hoặc dùng field non-final có kiểm soát |
| Cho rằng `final` bảo đảm thread safety toàn bộ object | Mutable state/concurrency có yêu cầu riêng | Đồng bộ hóa và ownership thích hợp |

Những ví dụ **cố ý không biên dịch** trong bài được ghi chú riêng để giải thích lỗi. Khi kiểm tra một dự án, hãy sửa **nguyên nhân definite assignment/duality**, không bỏ `final` một cách máy móc chỉ để chương trình qua compiler.

## 22. Checklist thiết kế trường blank final

Khi một field được khai báo `final` mà không có initializer, hãy tự kiểm tra:

1. Field này **thuộc object** hay **thuộc class**? Có cần `static` không?
2. **Giá trị được biết lúc nào?** Ngay tại khai báo hay chỉ khi constructor/static initializer chạy?
3. Nếu là instance field, **mọi constructor** có gán trước khi hoàn tất bình thường không?
4. Nếu có `this(...)`, các phép gán có được tập trung tại constructor đích để tránh trùng không?
5. Nếu có `if`/`switch`/`try`, mọi nhánh thành công đã gán hợp lệ chưa?
6. Field có bị gán từ cả instance initializer và constructor không?
7. Nếu là `static final`, phép gán nằm ở **static initializer hợp lệ** hay nhầm trong static method?
8. Input có cần kiểm tra/chuẩn hóa trước khi giữ giá trị không?
9. Field tham chiếu tới object mutable có cần defensive copy hoặc ownership rõ không?
10. Constructor có thể công bố `this` quá sớm tới callback/thread không?
11. Trường được dùng cho một **hằng số compile-time** hay một giá trị runtime cuối cùng?
12. Khi nghiệp vụ cần giá trị mới, nên tạo instance thay thế hay chủ đích dùng field mutable thay vì chống lại `final`?

Tốt nhất là coi trường `final` như **một quyết định thiết kế trạng thái**, không phải một decorator để khiến code “trông an toàn”. Quy tắc của compiler giúp hạn chế gán lại, nhưng hợp đồng nghiệp vụ vẫn do tác giả class xác định.

## 23. Bài tập tự luyện

**Bài 1 — Điểm gán.** Lớp `Employee` có `private final String id;`. Constructor nhận `String id`. Viết phép gán hợp lệ và giải thích vì sao `setId` không thể gán lại về sau.

**Bài 2 — Hai constructors.** Một lớp có `final int level;`, constructor không tham số và constructor nhận `int`. Hai đường tạo cần làm gì để compiler chấp nhận? Có nên dùng `this(...)` không?

**Bài 3 — Thiếu nhánh.** Với `final String mode;` và constructor chỉ gán `mode` khi `debug == true`, compiler phản đối điều gì? Sửa theo hai cách.

**Bài 4 — Gán trùng.** Nếu `final int size = 10;` nhưng constructor còn `size = 20;`, tại sao sai? Chọn thiết kế nếu giá trị phải do constructor quyết định.

**Bài 5 — Initializer block.** Một blank final instance field đã được gán trong `{ field = 3; }`. Constructor có được gán `field = 4;` nữa không?

**Bài 6 — Static blank.** Viết một lớp có `private static final String MODE;` được gán theo một điều kiện trong static initializer. Vì sao không thể đưa phép gán đó sang static method `init()`?

**Bài 7 — Helper.** Constructor gọi `validateAndSet(token)`, và helper gán `this.token = ...` vào blank final field. Tại sao compiler từ chối? Hãy thiết kế helper trả kết quả thay thế.

**Bài 8 — Constant expression.** So sánh `static final int A = 10;` và `static final int B; static { B = 10; }` về khả năng là constant variable.

**Bài 9 — Kế thừa.** Lớp cha khai báo một blank `protected final int code;`. Lớp con có thể gán giá trị đó trong constructor của mình mà lớp cha không gán không? Vì sao?

**Bài 10 — Final reference.** `private final List<String> names;` được gán một `ArrayList`. Có thể viết `names = anotherList` trong setter không? Có thể viết `names.add("A")` không?

**Bài 11 — Exception.** Constructor ném `IllegalArgumentException` trước khi gán blank final field. Java có buộc constructor đó hoàn thành phép gán trên đường exception không? Có nên công bố `this` trước thời điểm ném lỗi không?

**Bài 12 — Record.** Với `record Price(long cents)`, compact canonical constructor kiểm tra `cents` ra sao và vì sao không cần `this.cents = cents;` trong thân compact constructor?

### Đáp án tham khảo

1. `this.id = id;` trong constructor; field `final` không được gán lại từ method setter.
2. Mọi đường constructor kết thúc bình thường phải gán field đúng một lần. Thường nên dùng `this(defaultLevel)` để tập trung gán trong constructor nhận `int`.
3. Có đường kết thúc bình thường thiếu gán. Sửa bằng `else { mode = "RELEASE"; }` hoặc tính `String selected = debug ? "DEBUG" : "RELEASE"; mode = selected;`.
4. Final field đã có initializer. Muốn constructor quyết định thì khai báo `final int size;` không initializer, rồi chỉ gán trong constructor.
5. Không; field đã được gán trong instance initializer trước thân constructor tương ứng.
6. Có thể dùng `static { MODE = condition ? "A" : "B"; }`; phép gán field `static final` không được chuyển vào static method thông thường.
7. Method thường không phải nơi được phép gán blank final field. Dùng `this.token = checkedToken(token);` trong constructor, với helper chỉ validate và trả giá trị.
8. `A` là constant variable khi `10` là constant expression; `B` không phải vì blank final nhận giá trị trong static block.
9. Không. Superclass phải khởi tạo field final do nó khai báo trước khi constructor superclass hoàn tất bình thường.
10. Setter không thể gán lại `names`, nhưng nếu object danh sách có thể sửa và API cho phép, `names.add("A")` hợp lệ. Cần defensive copy nếu muốn tính bất biến.
11. Không đòi gán trên đường ném exception; không nên công bố `this` khởi tạo dở cho mã ngoài.
12. Ví dụ `Price { if (cents < 0) throw new IllegalArgumentException("cents âm"); }`; component field được record tự gán theo cơ chế compact canonical constructor.

## 24. Tài liệu đối chiếu

- [Java Language Specification 17, §4.12.4 — `final` Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): blank final và quy tắc gán với biến final.
- [Java Language Specification 17, §8.3.1.2 — `final` Fields](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.1.2): ý nghĩa final đối với trường.
- [Java Language Specification 17, §8.3.2 — Field Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.2): khởi tạo trường.
- [Java Language Specification 17, §8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): khối khởi tạo static.
- [Java Language Specification 17, §8.6 — Instance Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.6): khối khởi tạo instance.
- [Java Language Specification 17, §8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructor và đường khởi tạo object.
- [Java Language Specification 17, §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se17/html/jls-16.html): DA/DU trên các đường điều khiển.
- [Java Language Specification 17, §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): cơ chế class initialization.
- [Java Language Specification 17, §17.5 — `final` Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): ngữ nghĩa final fields trong Java Memory Model.
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): các quy tắc đặc thù của record.

**Ghi nhớ:** `final` field **không bắt buộc có initializer tại dòng khai báo**. Với **blank final instance field**, hãy gán trong **instance initializer hoặc constructor của lớp khai báo**, bảo đảm đủ trên mọi đường khởi tạo thành công và không gán lần thứ hai. Với **blank final static field**, dùng **static initializer** của lớp. Không chuyển phép gán final sang method thường hay constructor lớp con; không nhầm final reference với object bất biến hoặc với hằng số compile-time. Compiler kiểm tra *definite assignment*, còn validation và an toàn công bố object là trách nhiệm thiết kế của bạn.
