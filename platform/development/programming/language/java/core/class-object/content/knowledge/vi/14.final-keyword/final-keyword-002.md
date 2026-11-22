# Trường `final` và yêu cầu gán giá trị trên mọi nhánh khởi tạo trong Java

Trong Java, một **field khai báo `final`** chỉ được phép nhận giá trị theo **quy tắc khởi tạo một lần**. Với một **blank final field** — field có từ khóa `final` nhưng **không có initializer tại chỗ khai báo** — compiler áp dụng **definite assignment**: mỗi đường thực thi khởi tạo có thể **hoàn tất bình thường** phải thiết lập giá trị cho field ấy, và không có đường gán hợp lệ nào được gán lần thứ hai.

Đây là chủ đề quan trọng của Java Core về **class, object, constructor và từ khóa `final`**. Nó giải thích vì sao có những constructor nhìn có vẻ đã “thường xuyên” gán field nhưng vẫn **không biên dịch**, vì sao `if/else` phải bao phủ tất cả nhánh hợp lệ, và vì sao constructor ném exception trước khi hoàn tất không giống một đường tạo object thành công.

Ví dụ tối giản:

~~~java
class User {
    private final String id;

    User(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        this.id = id;
    }

    String id() {
        return id;
    }
}
~~~

Đây là **đoạn khai báo class**, chưa có `main` chạy độc lập. Field `id` là **blank final instance field**. Constructor có hai hướng:

1. Input không hợp lệ: ném `IllegalArgumentException`, constructor **không hoàn tất bình thường** và không trả về một `User` được tạo thành công cho caller.
2. Input hợp lệ: thực hiện `this.id = id`, sau đó hoàn tất bình thường; field đã có giá trị duy nhất.

**Điều cần nhớ:** blank final phải được gán **đúng một lần trên mỗi đường khởi tạo hoàn tất bình thường**, không phải “đúng một lần trong mọi đường đi kể cả đường cố ý ném exception”.

Bài học dùng **Java 17+**. Các ví dụ minh họa lỗi compiler đều được comment hoặc đặt trong đoạn được ghi rõ là **không biên dịch**; các chương trình có `main` được tách riêng, có lệnh chạy và stdout chính xác.

## 1. Phân biệt các dạng field `final`

Một class Java có thể khai báo final fields với các hình thức khác nhau:

~~~java
class Config {
    final int maxRetries = 3;             // Instance final đã khởi tạo
    final String name;                     // Blank final instance field

    static final int DEFAULT_PORT = 8080; // Static final đã khởi tạo
    static final String ENVIRONMENT;       // Blank static final field

    static {
        ENVIRONMENT = "development";
    }

    Config(String name) {
        this.name = name;
    }
}
~~~

Các thành viên:

| Khai báo | Loại field | Nơi hoàn tất gán giá trị |
| --- | --- | --- |
| `final int maxRetries = 3;` | Instance final có initializer | Field initializer chạy khi tạo từng object |
| `final String name;` | Blank final instance | Constructor hoặc instance initializer thích hợp của chính class |
| `static final int DEFAULT_PORT = 8080;` | Static final có initializer | Field initializer trong quá trình khởi tạo class |
| `static final String ENVIRONMENT;` | Blank static final | Static initializer thích hợp của chính class |

**Instance field** thuộc từng object: mỗi `new Config("A")` có một `name` được gán trong constructor của object ấy. **Static field** gắn với runtime class tương ứng; `ENVIRONMENT` được khởi tạo theo đường class initialization, không phải gán lại khi tạo mỗi Config object.

### 1.1. `final` không có nghĩa “field phải viết initializer ngay trên dòng khai báo”

Cả hai đều hợp lệ:

~~~java
class IdA {
    final int id = 7;
}

class IdB {
    final int id;

    IdB(int id) {
        this.id = id;
    }
}
~~~

`IdA.id` được gán từ field initializer. `IdB.id` được gán trong constructor. Không cần bắt buộc dùng field initializer khi giá trị phải được chọn từ parameter, validation hoặc nhánh nghiệp vụ tại thời điểm tạo object.

### 1.2. `final` không giống `static` và cũng không giống `const`

- `final` trên field: hạn chế **phép gán lại** field theo quy tắc Java.
- `static`: field **thuộc class** thay vì thuộc mỗi object.
- `static final`: kết hợp cả hai thuộc tính.
- Java không có mô hình đặt một từ khóa `const` trước field để thay thế `final` trong các chương trình Java thông thường.

Những constant như `Math.PI` là static final, nhưng **không phải mọi static final field đều là compile-time constant**. Có loại final reference đến object được tạo ở runtime, và object đó vẫn có thể mutable.

## 2. “Definite assignment” là gì?

**Definite assignment (DA)** là phân tích compile time giúp compiler xác nhận một biến bắt buộc phải được gán **trước khi đọc** hoặc trước khi kết thúc một đường khởi tạo có thể hoàn tất bình thường. Với blank final, còn có quy tắc **definite unassignment (DU)** trước một phép gán: compiler cần bảo đảm phép gán đó không tái gán một final field đã được gán trên đường đi tương ứng.

**Compiler phân tích luồng điều khiển**, chứ không phải chạy thử chương trình với vài input ngẫu nhiên để đoán nhánh nào xảy ra. Vì vậy code phải thỏa quy tắc cho các nhánh mà compiler coi là có thể thực thi theo ngữ nghĩa được phân tích.

Ví dụ hợp lệ:

~~~java
class Message {
    final String text;

    Message(boolean english) {
        if (english) {
            text = "Hello";
        } else {
            text = "Xin chào";
        }
    }
}
~~~

Cả hai nhánh đều gán `text` đúng một lần. Sau câu `if/else`, compiler có thể xác định `text` đã được gán trên mọi đường hoàn tất bình thường.

Trái lại:

~~~java
class BrokenMessage {
    final String text;

    BrokenMessage(boolean english) {
        if (english) {
            text = "Hello";
        }
        // Lỗi compile: đường english == false không gán text
    }
}
~~~

Đoạn `BrokenMessage` **không biên dịch** vì constructor có thể hoàn tất bình thường khi `english == false` nhưng blank final `text` chưa được gán.

### 2.1. DA không phải kiểm tra xem giá trị có khác `null` hay không

~~~java
class Box {
    final String label;

    Box() {
        label = null; // Hợp lệ về definite assignment
    }
}
~~~

Field `label` được gán đúng một lần, dù **giá trị được gán là null**. `final` không có nghĩa reference non-null. Nếu nghiệp vụ không chấp nhận null, phải validation riêng:

~~~java
this.label = java.util.Objects.requireNonNull(
        input, "label");
~~~

**Definite assignment trả lời câu hỏi “đã gán chưa?”**, chứ không tự trả lời “giá trị có hợp lệ với nghiệp vụ không?”. Các annotation `@NonNull` của từng hệ sinh thái cũng không phải một thay thế phổ quát cho quy tắc DA của Java compiler chuẩn.

## 3. Khởi tạo blank final instance fields trong constructor

Một blank final instance field thường lấy giá trị từ constructor parameters:

~~~java
class Product {
    private final String sku;
    private final long price;

    Product(String sku, long price) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU rỗng");
        }
        if (price < 0) {
            throw new IllegalArgumentException("Giá âm");
        }

        this.sku = sku;
        this.price = price;
    }
}
~~~

Khi constructor hoàn tất bình thường, cả `sku` lẫn `price` đều đã được gán. Việc kiểm tra có thể ném exception; những đường đi đó **không tạo ra một Product thành công**, vì thế không yêu cầu hoàn thành hai phép gán trước khi ném.

### 3.1. Trình tự tốt: validate, tính toán, rồi gán

Một constructor nên tránh để object thoát ra ngoài khi chỉ có một số field đã khởi tạo. Bạn có thể xử lý:

1. Validate tất cả parameters bắt buộc.
2. Tính các giá trị dẫn xuất và kiểm tra phép toán có thể ném exception.
3. Gán các final fields sao cho compiler chứng minh đúng quy tắc.
4. Không gọi overridable method/đăng ký callback làm lộ `this` khi object chưa hoàn tất khởi tạo.

Ví dụ:

~~~java
class Invoice {
    private final long subtotal;
    private final long total;

    Invoice(long subtotal, long tax) {
        if (subtotal < 0 || tax < 0) {
            throw new IllegalArgumentException("Số âm");
        }
        long calculated = Math.addExact(subtotal, tax);
        this.subtotal = subtotal;
        this.total = calculated;
    }
}
~~~

`Math.addExact` có thể ném `ArithmeticException` khi tràn `long`. Phép tính xảy ra trước hai phép gán final fields; nếu lỗi, constructor không hoàn tất. Nếu thành công, hai final fields được gán.

Đây là một lựa chọn thiết kế tốt, nhưng **Java không tự rollback các tác dụng phụ khác** đã xảy ra trước exception. Chẳng hạn, ghi dữ liệu ra hệ thống ngoài hoặc thêm `this` vào một static collection trong constructor vẫn có thể tạo rủi ro dù việc gán final hợp lệ.

## 4. Nếu có `if/else`: mọi đường hoàn tất bình thường phải gán

So sánh hai đoạn:

**Đúng:**

~~~java
class AccessToken {
    private final String prefix;

    AccessToken(boolean administrator) {
        if (administrator) {
            prefix = "ADM";
        } else {
            prefix = "USR";
        }
    }
}
~~~

**Sai:**

~~~java
class AccessToken {
    private final String prefix;

    AccessToken(boolean administrator) {
        if (administrator) {
            prefix = "ADM";
        }
        // Không có else và cũng không có phép gán fallback.
    }
}
~~~

Đoạn thứ hai **không biên dịch**. Người dùng có thể chạy constructor với `administrator == false`; compiler không chấp nhận đường đi cho phép constructor hoàn tất bình thường mà `prefix` chưa được gán.

### 4.1. Có thể dùng toán tử ba ngôi để gán một lần

Nếu chỉ chọn một trong hai giá trị:

~~~java
class AccessToken {
    private final String prefix;

    AccessToken(boolean administrator) {
        prefix = administrator ? "ADM" : "USR";
    }
}
~~~

Cách này có **một phép gán** cho final field; phép toán điều kiện chọn giá trị. Với logic phức tạp, `if/else` có thể dễ đọc hơn.

### 4.2. Không “vá” bằng phép gán lần hai sau `if/else`

~~~java
class Wrong {
    final int code;

    Wrong(boolean flag) {
        if (flag) {
            code = 1;
        } else {
            code = 2;
        }

        // code = 3; // Lỗi compile: final field đã được gán
    }
}
~~~

`final` không cho phép bạn cập nhật field sau khi hoàn tất lựa chọn. Muốn tính toán linh hoạt, hãy tính bằng **biến local** trước rồi gán field một lần:

~~~java
class Correct {
    final int code;

    Correct(boolean flag) {
        int calculated = flag ? 1 : 2;
        calculated += 10;
        code = calculated;
    }
}
~~~

Local `calculated` không khai báo final nên có thể cập nhật. `code` chỉ nhận một giá trị cuối cùng.

## 5. Ví dụ hoàn chỉnh: gán final trên mọi nhánh hợp lệ

Tạo tệp **`FinalBranchesDemo.java`**:

~~~java
public class FinalBranchesDemo {
    static final class Badge {
        private final String label;
        private final int level;

        Badge(String name, boolean premium) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }

            if (premium) {
                label = "VIP-" + name;
                level = 2;
            } else {
                label = "STD-" + name;
                level = 1;
            }
        }

        String description() {
            return label + "/level=" + level;
        }
    }

    public static void main(String[] args) {
        Badge vip = new Badge("Lan", true);
        Badge normal = new Badge("Mai", false);

        System.out.println(vip.description());
        System.out.println(normal.description());

        try {
            new Badge(" ", true);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }

        System.out.println(vip.description());
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 FinalBranchesDemo.java
java FinalBranchesDemo
~~~

**Stdout chính xác:**

~~~text
VIP-Lan/level=2
STD-Mai/level=1
Rejected = Tên rỗng
VIP-Lan/level=2
~~~

**Phân tích:**

1. `new Badge("Lan", true)` chọn nhánh `premium == true`. Cả `label` và `level` đều được gán một lần.
2. `new Badge("Mai", false)` chọn nhánh `else`. Cả hai final fields cũng được gán.
3. `new Badge(" ", true)` vào nhánh invalid, ném exception trước khi gán fields. Constructor không hoàn tất bình thường; vì vậy điều này **không vi phạm quy tắc DA của blank final**.
4. `vip` là object khác đã khởi tạo thành công, nên vẫn có thể gọi `description()` sau khi lần tạo Badge thứ ba thất bại.

Ví dụ này chứng minh đúng quy tắc compile-time, không chỉ dựa trên vài giá trị test. Compiler nhìn thấy cả nhánh `if` và `else` gán đầy đủ hai final fields khi chúng có thể kết thúc bình thường.

## 6. Nhánh ném exception khác nhánh gán thiếu rồi return

Điều kiện quan trọng là **constructor có hoàn tất bình thường được không?**

**Hợp lệ:**

~~~java
class Port {
    final int number;

    Port(int number) {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException("Port sai");
        }
        this.number = number;
    }
}
~~~

Các input ngoài miền cho phép khiến constructor dừng bất thường bằng exception. Với input hợp lệ, field `number` được gán trước khi constructor hoàn tất.

**Không hợp lệ:**

~~~java
class Port {
    final int number;

    Port(int number) {
        if (number < 1 || number > 65535) {
            return; // Constructor kết thúc bình thường mà thiếu gán.
        }
        this.number = number;
    }
}
~~~

Đoạn thứ hai **không biên dịch**. Trong constructor Java, `return;` không trả object bằng biểu thức như method thông thường, nhưng nó vẫn có thể kết thúc constructor **bình thường**. Nếu nhánh này rời constructor trước khi blank final được gán, compiler phát hiện vi phạm.

### 6.1. Không cần gán final trước mọi câu lệnh `throw`

Một ngoại lệ cố ý báo lỗi input không hợp lệ có thể xảy ra trước phép gán final. Đừng tạo một giá trị giả như `id = "UNKNOWN"` rồi mới `throw` chỉ để “làm hài lòng compiler”; điều đó thường thừa và có thể gây tác dụng phụ không cần thiết.

Nhưng nếu bạn **bắt exception và tiếp tục** đến cuối constructor, cần bảo đảm final fields được gán cho đường tiếp tục đó. Để tránh logic rối, thường nên validate và tính toán bằng locals trước khi gán fields, hoặc ném exception ra ngoài khi trạng thái không thể khởi tạo.

## 7. Nhiều constructor: mỗi đường tạo object thành công đều phải hợp lệ

Một class có thể có nhiều constructor overload:

~~~java
class Task {
    private final String title;
    private final int priority;

    Task() {
        this("Untitled", 1);
    }

    Task(String title) {
        this(title, 1);
    }

    Task(String title, int priority) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Tiêu đề rỗng");
        }
        if (priority < 1 || priority > 5) {
            throw new IllegalArgumentException("Ưu tiên sai");
        }
        this.title = title;
        this.priority = priority;
    }
}
~~~

Các constructors không bắt buộc **mỗi cái đều chứa phép gán trực tiếp** cho cùng field. `Task()` và `Task(String)` gọi **constructor khác trong cùng class** qua `this(...)` (*constructor chaining*). Nếu chuỗi ủy quyền cuối cùng khởi tạo đầy đủ các blank final fields trước khi hoàn tất, các constructors đều hợp lệ.

### 7.1. `this(...)` không phải phép gán lại field

~~~java
Task() {
    this("Untitled", 1);
}
~~~

`this(...)` là một **explicit constructor invocation**, không phải gọi method có tên “this”. Trong Java 17, lời gọi như vậy phải là **câu lệnh đầu tiên** của constructor body, và cùng một constructor không thể vừa gọi `this(...)` vừa gọi `super(...)` tường minh. Constructor được gọi thông qua `this(...)` thực hiện công việc khởi tạo field.

Điều này giúp dồn validation và gán blank finals vào một constructor trung tâm, tránh sao chép logic qua nhiều overloads.

### 7.2. Constructor chaining không được tạo vòng lặp

~~~java
class Wrong {
    Wrong() {
        this(1);
    }

    Wrong(int n) {
        this();
    }
}
~~~

Đây là đoạn **không biên dịch** vì recursive constructor invocation. Không có đường khởi tạo hợp lệ đi tới phần thực hiện gán fields. Việc chain constructors phải dẫn đến một constructor thực hiện khởi tạo thực sự.

### 7.3. Constructor overload không chain phải tự bảo đảm final fields

~~~java
class Wrong {
    final String id;

    Wrong() {
        id = "AUTO";
    }

    Wrong(String id) {
        // Không gán this.id => lỗi compile
    }
}
~~~

Đoạn trên **không biên dịch**: một overload khác hợp lệ không “cứu” constructor `Wrong(String)` hoàn tất bình thường mà bỏ quên blank final.

## 8. Ví dụ hoàn chỉnh: constructor chaining và field `final`

Lưu tệp **`ConstructorChainDemo.java`**:

~~~java
public class ConstructorChainDemo {
    static final class ConnectionSettings {
        private final String host;
        private final int port;
        private final boolean secure;

        ConnectionSettings() {
            this("localhost", 8080, false);
        }

        ConnectionSettings(String host) {
            this(host, 443, true);
        }

        ConnectionSettings(String host, int port, boolean secure) {
            if (host == null || host.isBlank()) {
                throw new IllegalArgumentException("Host rỗng");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException("Port sai");
            }
            this.host = host;
            this.port = port;
            this.secure = secure;
        }

        String summary() {
            return host + ":" + port + "/secure=" + secure;
        }
    }

    public static void main(String[] args) {
        ConnectionSettings a = new ConnectionSettings();
        ConnectionSettings b = new ConnectionSettings("example.org");
        ConnectionSettings c =
                new ConnectionSettings("api.local", 8443, true);

        System.out.println("Default = " + a.summary());
        System.out.println("Host only = " + b.summary());
        System.out.println("Explicit = " + c.summary());

        try {
            new ConnectionSettings("example.org", 0, false);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ConstructorChainDemo.java
java ConstructorChainDemo
~~~

**Stdout chính xác:**

~~~text
Default = localhost:8080/secure=false
Host only = example.org:443/secure=true
Explicit = api.local:8443/secure=true
Rejected = Port sai
~~~

Ở đây:

- Constructors không tham số và một tham số **không gán ba final fields trực tiếp**; chúng gọi constructor ba tham số.
- Constructor ba tham số validate rồi gán `host`, `port`, `secure` một lần.
- Mọi đường hoàn tất bình thường đều đi qua ba phép gán ấy.
- Với port không hợp lệ, constructor ném exception trước khi hoàn tất và không tạo ra một `ConnectionSettings` sử dụng được.

**Gợi ý thiết kế:** constructor chaining làm giảm duplication. Nhưng nếu một constructor overload thực sự có semantic khác, đừng chain bừa sang một constructor có các tiền điều kiện mâu thuẫn; hãy thiết kế contract chung rõ ràng.

## 9. Field initializer và constructor không được cùng gán một final field

Nếu final field đã có initializer tại khai báo:

~~~java
class Settings {
    final int retries = 3;

    Settings() {
        // retries = 5; // Lỗi: cannot assign a value to final variable
    }
}
~~~

Field `retries` đã được gán bởi instance field initializer. Constructor không được gán lại nó. Với class được tạo bằng `new Settings()`, giá trị vẫn là 3.

**Sai lầm thường gặp:** viết initializer “tạm” như `final int retries = 0;` rồi muốn constructor thay bằng giá trị thật. `final` không hoạt động theo mô hình “có thể thay giá trị placeholder một lần sau đó”. Phép gán trong field initializer đã dùng quyền gán của field.

Muốn constructor chọn giá trị, hãy khai báo **blank final**:

~~~java
class Settings {
    final int retries;

    Settings(int retries) {
        if (retries < 0) {
            throw new IllegalArgumentException("retries âm");
        }
        this.retries = retries;
    }
}
~~~

## 10. Instance initializer block cũng có thể gán blank final

Java cho phép instance initializer blocks:

~~~java
class Sequence {
    private final int base;

    {
        base = 100;
    }

    Sequence() {
    }

    Sequence(String ignored) {
    }
}
~~~

Instance initializer chạy trong quá trình tạo **mỗi object**; nó gán `base` một lần, nên cả hai constructors không phải gán lại field đó.

Ngược lại, đoạn sau sai:

~~~java
class Wrong {
    final int base;

    {
        base = 100;
    }

    Wrong() {
        // base = 200; // Lỗi: final đã được gán
    }
}
~~~

### 10.1. Instance initializer có điều kiện vẫn phải đáp ứng DA

~~~java
class Feature {
    final String mode;

    {
        boolean debug = Boolean.getBoolean("feature.debug");
        mode = debug ? "DEBUG" : "NORMAL";
    }
}
~~~

Phần initializer luôn gán `mode` một lần, dù giá trị phụ thuộc vào system property. Code bên ngoài có thể quan sát chuỗi một trong hai giá trị khi object được khởi tạo thành công.

Nếu initializer chỉ gán một field trong nhánh `if (debug)` mà không có nhánh `else`/fallback và constructors không giải quyết trường hợp còn thiếu, class sẽ vi phạm definite assignment.

### 10.2. Lựa chọn thiết kế

Instance initializer blocks là tính năng hợp lệ nhưng dễ làm logic khởi tạo phân tán giữa field initializers, blocks và constructors. Với class thông thường cần validation input, **constructor chaining + phép gán có kiểm soát trong một constructor** thường dễ đọc hơn. Chỉ dùng initializer block khi nó thực sự giúp áp dụng hành vi khởi tạo chung cho nhiều constructors.

## 11. Blank `static final`: phải khởi tạo ở ngữ cảnh class, không chờ constructor

Blank static final khác blank instance final ở chỗ **không thuộc mỗi object** và cần được gán qua static initialization của class khai báo:

~~~java
class Environment {
    static final String NAME;

    static {
        NAME = "development";
    }
}
~~~

Compiler thấy đường static initializer hoàn tất bình thường gán `NAME` đúng một lần. Trong Java 17, static initialization theo thứ tự các static field initializers và static initializer blocks của class.

**Không hợp lệ:**

~~~java
class Wrong {
    static final String NAME;

    Wrong() {
        // NAME = "development"; // Không được gán blank static final từ constructor
    }
}
~~~

Static field có vòng đời class, còn constructor chạy mỗi object; đặt quyền gán static final trong constructor không đáp ứng cơ chế Java. Ngay cả khi bạn định “chỉ tạo một object”, compiler không lấy giả định runtime đó để hợp thức hóa phép gán sai ngữ cảnh.

### 11.1. Static final đã khởi tạo ngay tại khai báo

~~~java
class Limits {
    static final int MAX_ITEMS = 100;
    static final String DEFAULT_MODE = "safe";
}
~~~

Không cần static block chỉ để gán các biểu thức đơn giản. Với những giá trị được tính có validation hoặc cần cấu trúc nhiều bước, static initializer hoặc static helper hợp lệ có thể thích hợp.

### 11.2. Static final được tính có kiểm soát qua local

~~~java
class SystemMode {
    static final String MODE;

    static {
        String candidate = System.getProperty(
                "app.mode", "safe").trim();

        if (candidate.isEmpty()) {
            candidate = "safe";
        }

        MODE = candidate;
    }
}
~~~

Static block sử dụng local `candidate` (có thể gán lại) rồi gán `MODE` **một lần** ở cuối. Điều này hữu ích khi computation có nhiều bước nhưng final field chỉ nên nhận kết quả cuối.

Nếu `getProperty` hoặc `trim` ném exception, class initialization có thể thất bại, và field không nhất thiết được gán trên đường bất thường ấy. **Điều kiện definite assignment áp dụng cho những đường static initialization hoàn tất bình thường.**

## 12. Static initializer có nhánh cũng cần bao phủ đầy đủ

**Hợp lệ:**

~~~java
class AppProfile {
    static final String REGION;

    static {
        boolean domestic = Boolean.getBoolean("app.domestic");

        if (domestic) {
            REGION = "VN";
        } else {
            REGION = "GLOBAL";
        }
    }
}
~~~

Cả hai nhánh gán `REGION` một lần, nên khi class initialization hoàn tất bình thường thì final field đã được gán.

**Không hợp lệ:**

~~~java
class Wrong {
    static final String REGION;

    static {
        if (Boolean.getBoolean("app.domestic")) {
            REGION = "VN";
        }
        // Nếu false, static initializer vẫn kết thúc bình thường,
        // nhưng REGION chưa được gán.
    }
}
~~~

Đoạn thứ hai **không biên dịch** vì thiếu nhánh gán khi điều kiện false. Kết quả kiểm tra không dựa trên việc hệ thống của bạn có đang đặt property `app.domestic=true` hay không. Compiler phải chứng minh quy tắc DA theo cấu trúc code.

### 12.1. Không khởi tạo blank static final trong một static method thường

~~~java
class Wrong {
    static final String REGION;

    static void initialize() {
        // REGION = "VN"; // Không hợp lệ cho blank static final
    }

    static {
        initialize(); // Compiler không coi method này là phép gán final
    }
}
~~~

Blank static final cần được gán ở vị trí mà Java cho phép và chứng minh được definite assignment trong class initialization. Một static helper **có thể trả giá trị** để static initializer gán:

~~~java
class Correct {
    static final String REGION;

    static {
        REGION = readRegion();
    }

    private static String readRegion() {
        return System.getProperty("app.region", "VN");
    }
}
~~~

`readRegion()` làm computation; **phép gán vào `REGION` nằm trong static initializer**. Đây là cách phân tách công việc mà không cố gán blank final từ một method tùy ý.

## 13. Chương trình hoàn chỉnh: khởi tạo blank static final và instance final

Tạo tệp **`FinalInitializationDemo.java`**:

~~~java
public class FinalInitializationDemo {
    static final class Job {
        private static final String PREFIX;

        static {
            String proposed = "JOB";
            PREFIX = proposed + "-";
            System.out.println("Static prefix ready");
        }

        private final String id;
        private final int retries;

        Job(String id, boolean urgent) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("ID rỗng");
            }

            this.id = PREFIX + id;
            this.retries = urgent ? 1 : 3;
        }

        String summary() {
            return id + "/retries=" + retries;
        }

        static String prefix() {
            return PREFIX;
        }
    }

    public static void main(String[] args) {
        System.out.println("Start");
        System.out.println("Prefix = " + Job.prefix());

        Job first = new Job("A", true);
        Job second = new Job("B", false);

        System.out.println(first.summary());
        System.out.println(second.summary());

        try {
            new Job("", true);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected = " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 FinalInitializationDemo.java
java FinalInitializationDemo
~~~

**Stdout chính xác:**

~~~text
Start
Static prefix ready
Prefix = JOB-
JOB-A/retries=1
JOB-B/retries=3
Rejected = ID rỗng
~~~

Giải thích:

1. `Job.prefix()` là static method và kích hoạt khởi tạo runtime class Job nếu chưa khởi tạo. Static initializer gán blank static final `PREFIX` một lần và in `Static prefix ready`.
2. Tạo Job object không chạy lại static initializer; các constructors đọc chung `PREFIX`.
3. Mỗi Job instance có blank final fields `id` và `retries`, được constructor gán đúng một lần khi input hợp lệ.
4. `urgent ? 1 : 3` chọn giá trị; bản thân phép gán vào `retries` vẫn chỉ xảy ra một lần cho mỗi object.
5. Input id rỗng khiến constructor ném exception, không tạo Job thành công; nó không làm static final field thay đổi.

## 14. Có thể dùng `switch` hoặc switch expression để chọn giá trị final

Các nhánh `switch` truyền thống cần được tổ chức sao cho compiler thấy final field được gán đúng một lần và không bỏ sót đường hoàn tất.

Ví dụ dùng **switch expression** của Java 17 giúp tạo một giá trị rồi gán field một lần:

~~~java
enum Tier {
    BASIC, PRO, ENTERPRISE
}

class Subscription {
    private final int limit;

    Subscription(Tier tier) {
        if (tier == null) {
            throw new IllegalArgumentException("tier null");
        }

        this.limit = switch (tier) {
            case BASIC -> 10;
            case PRO -> 100;
            case ENTERPRISE -> 1_000;
        };
    }

    int limit() {
        return limit;
    }
}
~~~

Đây là khai báo Java 17 (không có `main`). Switch expression là **exhaustive** với tất cả enum constants đã liệt kê, nên tạo một `int` cho assignment. Dù ba lựa chọn khác nhau, `limit` chỉ được gán qua **một assignment statement** trong constructor.

Nếu về sau thêm một enum constant mới, việc thiếu case có thể làm compiler yêu cầu bạn cập nhật switch expression theo quy tắc exhaustiveness. Điều này có thể hữu ích để phát hiện case chưa xử lý.

### 14.1. Không nên gán final field trong một vòng lặp không chứng minh được DA/DU

Ví dụ sai:

~~~java
class Wrong {
    final int result;

    Wrong(int[] numbers) {
        for (int n : numbers) {
            // result = n; // Có thể gán nhiều lần nếu nhiều phần tử.
        }
    }
}
~~~

Nếu thực sự muốn lấy giá trị từ collection, hãy tính bằng biến local rồi gán một lần:

~~~java
class Sum {
    final long result;

    Sum(int[] numbers) {
        long calculated = 0;
        for (int n : numbers) {
            calculated = Math.addExact(calculated, n);
        }
        result = calculated;
    }
}
~~~

`calculated` là local variable có thể cập nhật nhiều lần; `result` là blank final field nhận đúng **một** kết quả. Đây là pattern tốt với logic tích lũy, validation nhiều bước hoặc những phép tính phức tạp.

## 15. Khác biệt giữa final field và final local variable

Xét:

~~~java
class Demo {
    private final int field;

    Demo(int input) {
        final int local = input + 1;
        field = local;
    }
}
~~~

`field` là **blank final instance field**, phải được gán hợp lệ trong quá trình khởi tạo object. `local` là **final local variable**, có phạm vi trong constructor. Cả hai chịu quy tắc hạn chế gán lại, nhưng trách nhiệm khởi tạo khác nhau.

Với local variable, compiler không cho phép đọc trước khi definite assignment:

~~~java
void example(boolean flag) {
    final int number;
    if (flag) {
        number = 1;
    } else {
        number = 2;
    }
    System.out.println(number);
}
~~~

Ví dụ method body này hợp lệ nếu đặt trong một class: cả hai nhánh gán number trước phép đọc. Không cần final local được khởi tạo tại dòng khai báo nếu mọi đường trước lần đọc đều gán đúng một lần.

### 15.1. Field có giá trị mặc định runtime không có nghĩa code được đọc tùy ý trước khi gán

Ở cấp JVM, fields có **giá trị mặc định** (0, false, null...) trước khi thực hiện những bước khởi tạo thích hợp. Nhưng blank final fields vẫn phải tuân thủ quy tắc DA/DU của Java source.

Không suy luận rằng một `final int id;` có thể bị bỏ trống trong constructor và “compiler tự lấy số 0 cho nó”. Đây là lỗi kiến thức phổ biến. Compiler yêu cầu code gán đúng theo đường khởi tạo, dù runtime object memory có trạng thái mặc định tạm thời trước đó.

Trong thiết kế tốt, không làm lộ `this` khi khởi tạo chưa xong. Nếu object bị công bố sớm, code khác có thể quan sát trạng thái chưa hoàn chỉnh trong những tình huống bất thường; điều này không phải một cách hợp thức hóa bỏ qua DA.

## 16. Blank final field thường không được gán từ method helper

Một cách viết dễ sai:

~~~java
class Wrong {
    private final String id;

    Wrong(String id) {
        initialize(id);
    }

    private void initialize(String id) {
        // this.id = id; // Không hợp lệ cho blank final field
    }
}
~~~

Dù `initialize` chỉ được gọi từ constructor trong ý định lập trình viên, **compiler không chứng minh final field được gán bằng cách phân tích side effect của method tùy ý**, và Java còn hạn chế vị trí thực hiện phép gán blank final field.

Cách đúng là để helper **trả giá trị**, sau đó constructor gán final field trực tiếp:

~~~java
class Correct {
    private final String id;

    Correct(String raw) {
        this.id = validate(raw);
    }

    private static String validate(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        return raw.trim();
    }
}
~~~

Cách này phân chia trách nhiệm:

- Helper tính và validate dữ liệu **không gán blank final field**.
- Constructor chịu trách nhiệm **gán đúng một lần**.
- Exception có thể thoát ra khỏi helper; nếu xảy ra thì constructor không hoàn tất bình thường.

**Không dùng reflection/Unsafe hoặc các thủ thuật runtime để thay final field** như một giải pháp thay cho logic khởi tạo đúng. Ngoài việc dễ lỗi và chịu giới hạn module/runtime, chúng phá vỡ kỳ vọng về bất biến và Java Memory Model.

## 17. Giá trị gán cho final field có thể là null, mutable object hoặc kết quả tính toán

`final` hạn chế phép gán lại **field**, không tự bảo đảm các tính chất khác.

### 17.1. `final` không tự bảo đảm non-null

~~~java
class Holder {
    final String text;

    Holder() {
        text = null; // Hợp lệ về luật final; có thể không hợp nghiệp vụ.
    }
}
~~~

Muốn non-null, constructor phải kiểm tra:

~~~java
this.text = java.util.Objects.requireNonNull(value, "value");
~~~

### 17.2. `final` trên reference không làm object được tham chiếu immutable

~~~java
import java.util.ArrayList;
import java.util.List;

class Cart {
    private final List<String> items;

    Cart() {
        this.items = new ArrayList<>();
    }

    void add(String name) {
        items.add(name);
    }

    List<String> snapshot() {
        return List.copyOf(items);
    }
}
~~~

`items` chỉ được gán một lần để trỏ tới ArrayList. Nhưng các lời gọi `items.add(...)` thay đổi **state của ArrayList object**, không gán lại `items`. Đây là hành vi hợp lệ khi List mutable.

### 17.3. Mảng final vẫn có phần tử thay đổi được

~~~java
class Scores {
    final int[] values;

    Scores() {
        values = new int[]{1, 2};
    }

    void changeFirst() {
        values[0] = 9; // Hợp lệ
        // values = new int[]{9}; // Không hợp lệ: gán lại final field
    }
}
~~~

Muốn immutable value semantics, cần bảo vệ aliasing và mutable contents bằng copying hoặc immutable representation. `final` không phải deep-freeze.

## 18. Trường `final` và tính đúng khi có nhiều threads

Final fields có các **quy tắc đặc biệt trong Java Memory Model (JMM)** giúp một object được xây dựng đúng cách có những bảo đảm về quan sát các giá trị final fields sau khi constructor hoàn tất, với các điều kiện nhất định.

Tuy nhiên, **đừng hiểu quá mức**:

- Final field không tự biến **mutable object được field tham chiếu** thành thread-safe.
- Final field không bảo vệ mọi mutable non-final fields khác của object.
- Không nên để `this` “escape” trong constructor, vì code khác có thể thấy object khi chưa khởi tạo xong; điều này có thể phá vỡ những giả định về an toàn khởi tạo.
- Những thao tác phối hợp trên nhiều fields vẫn có thể cần synchronization, immutable snapshots hoặc thiết kế khác.

Ví dụ rủi ro:

~~~java
class UnsafePublication {
    static UnsafePublication current;

    final String id;

    UnsafePublication(String id) {
        current = this;  // Nguy hiểm: công bố object trước khi khởi tạo xong
        this.id = id;
    }
}
~~~

Đoạn này nêu **vấn đề thiết kế**, không phải ví dụ để áp dụng. Về mặt DA, phép gán `id` vẫn có thể đáp ứng đường constructor kết thúc bình thường; nhưng object có thể bị một thread khác lấy từ `current` trước lúc final field được gán. **Definite assignment và safe publication là hai mối quan tâm khác nhau**.

Hướng phù hợp hơn là tạo xong object rồi công bố qua cơ chế an toàn thích hợp (ví dụ immutable holder, synchronized transfer hoặc concurrent structure), không đưa `this` ra nơi khác giữa constructor.

## 19. Constructor của superclass và subclass: mỗi class chịu trách nhiệm field của mình

Giả sử:

~~~java
class Parent {
    final String baseId;

    Parent(String baseId) {
        this.baseId = baseId;
    }
}

class Child extends Parent {
    final int childId;

    Child(String baseId, int childId) {
        super(baseId);
        this.childId = childId;
    }
}
~~~

`Parent` gán blank final `baseId` trong constructor **của Parent**. `Child` gán blank final `childId` trong constructor **của Child**.

Subclass không được tự ý thay blank final của superclass sau khi superclass đã khởi tạo. Nếu superclass muốn cho subclass xác định giá trị, thường truyền parameter qua `super(...)` để superclass tự validate và gán field của nó.

### 19.1. Overridable method trong constructor có thể quan sát state chưa đầy đủ

~~~java
class Base {
    Base() {
        show(); // Có thể dispatch sang override ở subclass!
    }

    void show() {
        System.out.println("Base");
    }
}

class Derived extends Base {
    final String label;

    Derived() {
        this.label = "ready";
    }

    @Override
    void show() {
        System.out.println(label);
    }
}
~~~

Nếu thực thi `new Derived()`, `Base()` có thể gọi override `Derived.show()` **trước** khi constructor Derived gán `label`. Dù `label` là final và compiler chấp nhận khởi tạo đúng trong Derived, lời gọi sớm có thể quan sát giá trị mặc định null trong tình huống này.

Do đó, tránh gọi overridable methods từ constructor khi chúng dựa trên subclass state. Bảo đảm definite assignment **không thay thế** thiết kế thứ tự khởi tạo an toàn.

## 20. `final` không đồng nghĩa field được gán trên mọi nhánh bằng cùng một giá trị

Các nhánh có thể chọn **giá trị khác nhau**:

~~~java
class Shipping {
    final int fee;

    Shipping(boolean international) {
        if (international) {
            fee = 50;
        } else {
            fee = 10;
        }
    }
}
~~~

Compiler chỉ quan tâm quy tắc assignment: mỗi đường hoàn tất bình thường gán fee đúng một lần. Không yêu cầu hai nhánh phải gán cùng một hằng số hoặc cùng biểu thức.

Tuy nhiên, các nhánh nên bảo đảm **hợp đồng nghiệp vụ**. Nếu fee phải luôn dương hoặc nhỏ hơn giới hạn, validation vẫn cần được thiết kế. Một final field có thể giữ giá trị sai nghiệp vụ mãi mãi nếu constructor gán sai rồi hoàn tất.

### 20.1. Tính trước rồi gán cuối giúp giảm lỗi khi nhiều nhánh phức tạp

~~~java
class Price {
    final long amount;

    Price(long base, boolean discount) {
        if (base < 0) {
            throw new IllegalArgumentException("Giá âm");
        }

        long calculated = base;
        if (discount) {
            calculated = Math.subtractExact(base, base / 10);
        }

        amount = calculated;
    }
}
~~~

Dùng local `calculated` giúp các nhánh tính toán dễ mở rộng, nhưng final field `amount` vẫn chỉ có một assignment ở cuối constructor. Với nghiệp vụ giá tiền thật, còn cần lựa chọn kiểu biểu diễn phù hợp (`BigDecimal`/đơn vị tiền), quy tắc làm tròn và validation riêng.

## 21. Những nhầm lẫn phổ biến

| Nhầm lẫn | Giải thích đúng |
| --- | --- |
| “Final field phải viết `= ...` ngay khi khai báo.” | Blank final có thể được gán trong constructor/initializer phù hợp |
| “Chỉ cần một nhánh `if` gán final field là đủ.” | Mọi đường khởi tạo có thể kết thúc bình thường phải gán đầy đủ |
| “Constructor ném exception vẫn phải gán hết final field trước khi ném.” | Đường hoàn tất bất thường không phải đường tạo object thành công |
| “`return;` trong constructor giống `throw` về definite assignment.” | `return;` kết thúc bình thường, không thể bỏ qua gán blank final |
| “Nếu đã gán ở `if/else` thì gán fallback thêm sau đó cho chắc.” | Phép gán thứ hai trái quy tắc final |
| “Constructor đã có field initializer `final int x=0` có thể đổi `x` thành giá trị thật.” | Không, field initializer đã gán final |
| “Mỗi constructor overload bắt buộc tự viết lệnh gán field.” | Có thể ủy quyền qua `this(...)` để constructor đích khởi tạo |
| “Một constructor đúng thì mọi overload khác cũng tự đúng.” | Mỗi đường overload hoàn tất bình thường phải hợp lệ |
| “Blank static final chờ tạo object đầu tiên rồi constructor gán.” | Không; static final khởi tạo ở static context của class |
| “Một method helper có thể gán blank final thay constructor mà compiler tự suy ra.” | Hạn chế vị trí gán và DA không cho phép mô hình đó |
| “Final String luôn non-null.” | Final bảo vệ assignment, null vẫn là giá trị reference hợp lệ |
| “Final List không sửa được.” | Final reference vẫn có thể trỏ mutable List |
| “Final field tạo ra object immutable.” | Cần xét toàn bộ state, object con và aliasing |
| “Vì JVM khởi tạo memory về 0/null nên compiler cho bỏ trống final.” | Không; phải thỏa definite assignment của Java source |
| “Final bảo đảm object luôn thread-safe.” | Không; còn vấn đề mutable state, publication và concurrency |
| “Superclass constructor có thể dựa vào final field subclass đã được gán.” | Subclass initialization chưa hoàn tất khi superclass constructor chạy |
| “Static initializer luôn chạy mỗi lần tạo object.” | Static initialization là hoạt động của class, không phải từng instance |
| “Final field không thể lấy kết quả tính toán phức tạp.” | Có thể tính qua locals/helpers rồi gán field một lần |

## 22. Bài tập tự kiểm tra có đáp án

**Câu 1.** Constructor sau có hợp lệ không?

~~~java
class Sample {
    final int x;
    Sample(boolean flag) {
        if (flag) x = 1;
        else x = 2;
    }
}
~~~

**Đáp án:** Có. Cả hai nhánh hoàn tất bình thường đều gán `x` đúng một lần.

**Câu 2.** Nếu bỏ `else x = 2;` thì sao?

**Đáp án:** Không biên dịch, vì `flag == false` có thể hoàn tất constructor bình thường mà `x` chưa được gán.

**Câu 3.** `final String name;` được gán `name = null;` trong constructor có hợp lệ không?

**Đáp án:** Hợp lệ về final/definite assignment. Nhưng nếu tên không được phép null theo nghiệp vụ, constructor cần validation riêng.

**Câu 4.** Vì sao field `final int x = 10;` không được gán `x = 20;` trong constructor?

**Đáp án:** Field initializer đã gán final field; phép gán trong constructor sẽ là lần gán khác.

**Câu 5.** Constructor có nhánh `if (invalid) throw new IllegalArgumentException();` trước khi gán final field có vi phạm DA không?

**Đáp án:** Không, miễn mọi đường hoàn tất bình thường còn lại gán field đúng quy tắc. Nhánh ném exception không tạo object thành công.

**Câu 6.** Thay `throw` bằng `return;` ở nhánh invalid thì sao?

**Đáp án:** `return;` là đường hoàn tất bình thường của constructor; nếu field chưa được gán, compiler từ chối.

**Câu 7.** Có cần gán `final String id` trong mọi overload constructor dù chúng gọi `this(...)` không?

**Đáp án:** Mọi đường tạo object thành công phải có field được gán đúng một lần; constructor ủy quyền qua `this(...)` có thể dựa trên constructor đích thực hiện assignment hợp lệ.

**Câu 8.** Blank `static final String ENV` có thể được gán trong constructor instance đầu tiên không?

**Đáp án:** Không. Static final thuộc class; gán nó ở static initializer/initializer hợp lệ của chính class, không ở constructor instance.

**Câu 9.** Vì sao `final List<String> values` không ngăn `values.add("A")`?

**Đáp án:** Final hạn chế gán lại field tham chiếu. `add` thay đổi state của List object được tham chiếu, không gán lại field.

**Câu 10.** Nếu static block có `if (flag) ENV = "A";` nhưng không có nhánh else hay fallback, có hợp lệ không?

**Đáp án:** Không nếu có đường static initialization hoàn tất bình thường mà ENV chưa được gán.

**Câu 11.** Có thể tính nhiều bước bằng một local variable rồi gán final field một lần ở cuối không?

**Đáp án:** Có; đây thường là cách rõ ràng để tách computation/validation khỏi assignment cuối.

**Câu 12.** Vì sao constructor superclass gọi overridable method có thể quan sát blank final field của subclass là null?

**Đáp án:** Dynamic dispatch có thể gọi override của subclass trước khi subclass constructor đã thực hiện phép gán field đó. Dù chương trình thỏa definite assignment khi constructor hoàn tất, không nên để code quan sát object trong lúc chưa khởi tạo đủ.

**Câu 13.** Record components trong Java 17 có thể được hiểu như final fields không?

**Đáp án:** Có, record components tương ứng với private final fields trong record; tuy nhiên record có constructor/accessor và quy tắc riêng. Compact constructor cho phép validate/chuẩn hóa parameters và compiler gán component fields theo quy tắc record sau thân compact constructor, không phải một bộ setter.

**Câu 14.** `final` field có tự làm class thread-safe không?

**Đáp án:** Không. Final fields có ngữ nghĩa khởi tạo quan trọng trong Java Memory Model, nhưng mutable object con, non-final state, this escape và các thao tác đa trường vẫn cần thiết kế đồng bộ an toàn.

## 23. Java 17 records: component fields là final nhưng cú pháp constructor khác class thường

Java 17 hỗ trợ **record** để mô tả các giá trị dữ liệu theo components. Ví dụ:

~~~java
record UserId(String value) {
    UserId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("ID rỗng");
        }
        value = value.trim();
    }
}
~~~

Đây là **compact constructor** của record. Nó có thể validate và gán lại **parameter** `value` để chuẩn hóa. Sau phần thân compact constructor, Java thực hiện quá trình gán các component fields cuối cùng từ parameters theo quy tắc record, không phải setter.

Vì thế, không lấy quy tắc mã nguồn class có blank final field rồi suy luận rằng phải viết `this.value = value;` trong compact constructor; dạng compact có cơ chế riêng. Đối với **canonical constructor khai báo đầy đủ** (không dùng dạng compact), việc thiết lập components phải theo quy tắc constructor của record.

### 23.1. Record components final không đồng nghĩa immutable object sâu

~~~java
import java.util.List;

record Tags(List<String> values) {
    Tags {
        values = List.copyOf(values);
    }
}
~~~

`values` là component reference; record field tương ứng final, nhưng nếu không copy, một mutable List do caller cung cấp có thể bị sửa ở ngoài sau constructor. `List.copyOf` tạo cấu trúc không sửa được, thích hợp ở đây vì String elements immutable.

Tương tự, một record chứa mutable object vẫn có thể bị tác động qua object đó nếu không có defensive-copy contract. Không nhầm final fields với deep immutability.

## 24. Checklist khi sửa lỗi compiler liên quan blank final

Khi gặp lỗi “variable might not have been initialized” hoặc “cannot assign a value to final variable”, kiểm tra:

1. **Field là instance hay static?** Blank instance final thuộc mỗi object; blank static final thuộc runtime class.
2. **Có field initializer không?** Nếu đã `= ...` tại khai báo, đừng gán lại trong constructor/static block.
3. **Có bao nhiêu constructor overload?** Mỗi đường tạo object thành công có được khởi tạo đầy đủ không?
4. **Có constructor chaining `this(...)` không?** Nó đã đi tới constructor thực hiện assignment hợp lệ chưa?
5. **Có nhánh `if/else`, switch hoặc early return nào bỏ sót field không?** Kiểm tra cả các trường hợp input không phổ biến.
6. **Nhánh dừng bằng `throw` hay kết thúc bình thường?** Hai tình huống có ý nghĩa DA khác nhau.
7. **Có gán một final field lần thứ hai không?** Kiểm tra field initializer + constructor, nhiều nhánh rồi gán fallback.
8. **Có cố gán blank final trong helper method không?** Để helper trả dữ liệu, gán field ở vị trí Java cho phép.
9. **Với static final, có gán từ constructor không?** Phải dùng static initializer/initializer của class khai báo.
10. **Có dùng vòng lặp trực tiếp để gán final field nhiều lần?** Chuyển sang local variable rồi gán field một lần.
11. **Field có cần non-null hay giá trị hợp lệ không?** DA không thay thế validation/invariant.
12. **Field có tham chiếu object mutable không?** Final không thay thế defensive copy hoặc immutable representation.
13. **Có gọi overridable method hoặc làm lộ `this` từ constructor không?** Tránh quan sát object khi final state chưa hoàn chỉnh.
14. **Nếu class là record:** xem quy tắc component/canonical/compact constructor thay vì áp dụng máy móc cú pháp class thường.
15. **Khi sửa code:** bỏ comment lỗi minh họa riêng từng trường hợp để xem compiler chính xác từ chối ở đâu; không đoán từ runtime mà bỏ qua phân tích compile-time.

**Kết luận:** Một **blank final field** của Java phải có **giá trị được gán đúng một lần trên mọi đường khởi tạo hoàn tất bình thường**. Với instance final field, các constructors và instance initializers chịu trách nhiệm; với static final field, class initialization là nơi phải khởi tạo. `if/else`, `switch`, overload constructors và `throw` quyết định compiler có chứng minh được quy tắc definite assignment/definite unassignment hay không. Sau khi gán thành công, final ngăn gán lại field, nhưng **không tự bảo đảm non-null, tính hợp lệ nghiệp vụ, deep immutability hoặc thread safety**. Cách thiết kế rõ ràng nhất thường là **validate/tính toán vào local variables, sau đó gán final fields một lần** tại ranh giới khởi tạo thích hợp.
