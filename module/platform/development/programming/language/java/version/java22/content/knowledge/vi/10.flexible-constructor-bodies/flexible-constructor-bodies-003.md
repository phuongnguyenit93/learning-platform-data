# Kiểm tra tham số và chuẩn hóa dữ liệu trước khi gọi constructor của lớp cha

## Vì sao cần Flexible Constructor Bodies?

Trong Java, constructor của lớp con phải gọi constructor của lớp cha bằng `super(...)`, hoặc gọi một constructor khác cùng lớp bằng `this(...)`. Trước Java 22, lời gọi này phải xuất hiện ở đầu constructor. Điều đó khiến việc kiểm tra tham số hoặc chuẩn hóa dữ liệu trước khi gọi constructor lớp cha thường phải được nhồi vào biểu thức đối số, hoặc chuyển sang helper tĩnh.

Ví dụ, một lớp con cần chuẩn hóa tên trước khi truyền cho lớp cha:

~~~java
class Resource {
    Resource(String name) {
        System.out.println("Resource: " + name);
    }
}

class ImageResource extends Resource {
    ImageResource(String rawName) {
        super(normalize(rawName));
    }

    private static String normalize(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không được để trống");
        }
        return name.strip().toLowerCase();
    }
}
~~~

Cách này hợp lệ, nhưng khi phải kiểm tra nhiều điều kiện, tính toán nhiều giá trị hoặc chuẩn bị trạng thái cho lớp con, biểu thức trong `super(...)` dễ trở nên khó đọc.

Flexible Constructor Bodies cho phép đặt các câu lệnh trong phần đầu constructor trước lời gọi `super(...)` hoặc `this(...)`. Nhờ đó, constructor có thể kiểm tra tham số, chuẩn hóa dữ liệu và chuẩn bị đối số bằng các biến cục bộ trước khi chuyển quyền khởi tạo cho constructor khác.

## Trạng thái từ Java 22 đến JDK hiện hành

| Phiên bản | JEP | Trạng thái | Thay đổi |
|---|---|---|---|
| JDK 22 | JEP 447 – Statements before super(...) | Preview lần đầu | Cho phép một số câu lệnh xuất hiện trước lời gọi constructor, với giới hạn không truy cập instance đang được tạo. |
| JDK 23 | JEP 482 – Flexible Constructor Bodies | Preview lần hai | Đổi tên tính năng và bổ sung khả năng gán giá trị cho field của lớp đang khởi tạo trước `super(...)`. |
| JDK 24 | JEP 492 – Flexible Constructor Bodies | Preview lần ba | Tiếp tục hoàn thiện đặc tả trước khi chuẩn hóa. |
| JDK 25 | JEP 513 – Flexible Constructor Bodies | Chính thức | Tính năng trở thành một phần ổn định của Java. |
| JDK 26–27 | Java Language Specification | Chính thức | Tiếp tục được hỗ trợ như cú pháp Java chuẩn. |

Tính năng được giới thiệu ở Java 22 nhưng chỉ trở thành stable từ JDK 25. JDK 27 phát hành GA ngày 15/09/2026 và là feature release mới nhất tại ngày 25/11/2026; JDK 25 là LTS mới nhất. Vì vậy, mã mới nên dùng cú pháp chính thức từ JDK 25 trở lên. Không cần `--enable-preview`.

## Prologue, epilogue và early construction context

Một constructor có thể chia thành hai phần:

~~~java
import java.util.Objects;

class Parent {
    Parent(String value) { }
}

class Child extends Parent {
    Child(String value) {
        // Prologue: các câu lệnh trước constructor invocation
        String normalized = normalize(value);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("value rỗng");
        }

        super(normalized);

        // Epilogue: các câu lệnh sau constructor invocation
        System.out.println("Child đã được khởi tạo");
    }

    private static String normalize(String value) {
        return Objects.requireNonNull(value).strip();
    }
}
~~~

- **Prologue:** các câu lệnh nằm trước lời gọi constructor tường minh `super(...)` hoặc `this(...)`.
- **Epilogue:** các câu lệnh nằm sau lời gọi constructor đó.
- **Early construction context:** bao gồm prologue và cả các biểu thức đối số của lời gọi constructor. Trong ngữ cảnh này, chương trình chưa được phép truy cập instance đang khởi tạo theo cách thông thường.
- **Late construction context:** phần sau lời gọi `super(...)` hoặc `this(...)`. Tại đây, constructor có thể truy cập `this`, đọc field và gọi instance method như bình thường.

Mỗi constructor body có tối đa một lời gọi constructor tường minh (`super(...)` hoặc `this(...)`). Flexible Constructor Bodies không cho phép gọi `super(...)` ở nhiều nhánh điều kiện hoặc gọi cả `this(...)` lẫn `super(...)` trong cùng một constructor. Nếu không có lời gọi tường minh, Java tự chèn `super()` theo quy tắc mặc định.

## Kiểm tra tham số trước khi gọi constructor lớp cha

Giả sử lớp cha nhận tên tài nguyên và dung lượng. Lớp con muốn chuẩn hóa tên, kiểm tra dung lượng và chỉ gọi constructor lớp cha khi tất cả dữ liệu hợp lệ.

~~~java
import java.util.Locale;
import java.util.Objects;

class ResourceBase {
    ResourceBase(String name, int capacity) {
        System.out.printf(
            "ResourceBase: name=%s, capacity=%d%n",
            name,
            capacity
        );
    }
}

final class FileResource extends ResourceBase {
    private final String name;
    private final int capacity;

    FileResource(String rawName, int capacity) {
        String normalizedName = normalizeName(rawName);

        if (capacity <= 0) {
            throw new IllegalArgumentException(
                "capacity phải lớn hơn 0"
            );
        }

        this.name = normalizedName;
        this.capacity = capacity;

        super(normalizedName, capacity);
    }

    private static String normalizeName(String rawName) {
        Objects.requireNonNull(rawName, "rawName");

        String normalized = rawName.strip().toLowerCase(Locale.ROOT);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(
                "Tên tài nguyên không được để trống"
            );
        }

        return normalized;
    }

    String name() {
        return name;
    }

    int capacity() {
        return capacity;
    }
}

public class FlexibleConstructorDemo {
    public static void main(String[] args) {
        FileResource resource =
            new FileResource("  IMAGES/LOGO.PNG  ", 64);

        System.out.println("name = " + resource.name());
        System.out.println("capacity = " + resource.capacity());
    }
}
~~~

Kết quả:

~~~text
ResourceBase: name=images/logo.png, capacity=64
name = images/logo.png
capacity = 64
~~~

Trình tự thực hiện:

1. Constructor nhận `rawName` và `capacity`.
2. `normalizeName` kiểm tra null, loại bỏ khoảng trắng đầu/cuối và chuyển tên về chữ thường.
3. Constructor kiểm tra dung lượng phải lớn hơn 0.
4. Hai field `name` và `capacity` của lớp con được gán giá trị.
5. `super(normalizedName, capacity)` gọi constructor lớp cha bằng dữ liệu đã được chuẩn hóa.
6. Sau khi constructor lớp cha hoàn tất, phần epilogue (nếu có) mới được thực hiện.

Nếu tên hoặc dung lượng không hợp lệ, exception được ném ngay trong prologue và constructor lớp cha không được gọi. Điều này hữu ích khi constructor lớp cha có chi phí khởi tạo, mở tài nguyên hoặc tạo tác dụng phụ mà ứng dụng không muốn thực hiện với dữ liệu sai.

Trong ví dụ, `normalizeName` là static method. Prologue có thể gọi static method hoặc method trên tham số, nhưng không thể gọi instance method của đối tượng đang được tạo.

## Chuẩn hóa dữ liệu thành biến cục bộ trước super(...)

Một constructor có thể cần nhiều bước chuẩn hóa. Hãy tính từng giá trị vào biến cục bộ để lời gọi `super(...)` chỉ còn nhiệm vụ truyền các giá trị đã sẵn sàng.

~~~java
import java.util.Locale;
import java.util.Objects;

class EndpointBase {
    EndpointBase(String host, String scheme, int port) {
        System.out.printf("EndpointBase: %s://%s:%d%n", scheme, host, port);
    }
}

class NetworkEndpoint extends EndpointBase {
    NetworkEndpoint(String rawHost, String rawScheme, int port) {
        String host = normalizeHost(rawHost);
        String scheme = normalizeScheme(rawScheme);
        int normalizedPort = normalizePort(scheme, port);

        super(host, scheme, normalizedPort);
    }

    private static String normalizeHost(String rawHost) {
        Objects.requireNonNull(rawHost, "rawHost");

        String host = rawHost.strip().toLowerCase(Locale.ROOT);
        if (host.isEmpty()) {
            throw new IllegalArgumentException("Host rỗng");
        }
        return host;
    }

    private static String normalizeScheme(String rawScheme) {
        Objects.requireNonNull(rawScheme, "rawScheme");

        String scheme = rawScheme.strip().toLowerCase(Locale.ROOT);
        if (!scheme.equals("http") && !scheme.equals("https")) {
            throw new IllegalArgumentException("Scheme không hỗ trợ");
        }
        return scheme;
    }

    private static int normalizePort(String scheme, int port) {
        if (port == 0) {
            return scheme.equals("https") ? 443 : 80;
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Port không hợp lệ");
        }
        return port;
    }
}
~~~

Trong ví dụ này, `EndpointBase` là lớp cha có constructor nhận ba tham số `host`, `scheme` và `port`. Prologue thực hiện toàn bộ quy tắc chuẩn hóa trước khi gọi nó.

Cách tổ chức này có một số lợi ích:

- Mỗi quy tắc chuẩn hóa có thể được đọc và kiểm tra riêng.
- Biến cục bộ có tên mô tả rõ dữ liệu đã được chuẩn hóa.
- Lời gọi `super(...)` ngắn gọn, thể hiện rõ dữ liệu được truyền lên lớp cha.
- Nếu kiểm tra thất bại, constructor lớp cha không chạy.

Các helper dùng trong prologue nên là static method hoặc hàm độc lập, không phụ thuộc vào trạng thái của instance đang khởi tạo.

## Gán field của lớp con trước super(...)

Từ lần preview thứ hai ở JDK 23 và trong bản stable từ JDK 25, prologue còn cho phép gán trực tiếp một số field của lớp đang được khởi tạo trước lời gọi `super(...)`.

Điều này hữu ích khi constructor lớp cha gọi một method có thể bị override. Nếu method override đọc field của lớp con, field đó có thể còn mang giá trị mặc định nếu chỉ được gán sau khi constructor lớp cha chạy.

Ví dụ:

~~~java
class Base {
    Base() {
        report();
    }

    void report() {
        System.out.println("Base");
    }
}

class Child extends Base {
    private final String label;

    Child(String label) {
        this.label = Objects.requireNonNull(label);
        super();
    }

    @Override
    void report() {
        System.out.println("Child label = " + label);
    }
}
~~~

Khi tạo `new Child("ready")`, field `label` được gán trong prologue trước khi constructor `Base` chạy. Khi `Base()` gọi method `report()`, phiên bản override trong `Child` nhìn thấy giá trị `"ready"`.

Nếu viết constructor theo cách cũ và chỉ gán field sau khi constructor cha hoàn tất, lời gọi method override từ constructor cha có thể nhìn thấy giá trị mặc định của field con, chẳng hạn `null`, `0` hoặc `false`.

### Giới hạn khi gán field trước super(...)

Đây là ngoại lệ có kiểm soát cho prologue đứng trước lời gọi `super(...)`, không phải quyền truy cập instance nói chung:

- Chỉ được gán field instance được khai báo trong chính lớp đang khởi tạo, trước lời gọi `super(...)`.
- Field phải không có initializer tại chỗ khai báo (blank field). Dùng `final` blank field là trường hợp thường gặp.
- Dùng phép gán đơn `=`; không đọc giá trị field trước khi gán.
- Không được đọc field của lớp con hoặc field kế thừa trong prologue.
- Không thể gọi instance method để tính giá trị field.
- Không thể gán field của lớp cha bằng cách dùng `super.field`.

Ví dụ hợp lệ:

~~~java
class Base {
    Base() { }
}

class Child extends Base {
    private final int id;

    Child(int id) {
        this.id = id;
        super();
    }
}
~~~

Các cách sau không hợp lệ trong early construction context:

~~~java
class Base {
    Base() { }
}

class Child extends Base {
    private int count;
    private int id = 10;

    Child(int value) {
        int current = this.count; // Không được đọc field
        this.count += 1;          // Đọc rồi cập nhật field
        this.id = value;          // Field đã có initializer
        validate();               // Instance method của Child
        super();
    }

    private void validate() { }
}
~~~

Nếu field có initializer trong khai báo, initializer đó được thực hiện trong quá trình khởi tạo instance sau khi constructor lớp cha chạy. Vì vậy, hãy dùng blank field khi thật sự cần gán field trong prologue; không dựa vào việc gán sớm để ghi đè initializer.

Việc gán field sớm cũng không có nghĩa toàn bộ đối tượng đã sẵn sàng. Những field khác, initializer và invariant còn lại vẫn có thể chưa được thiết lập.

## Phân biệt super(...) và this(...)

Flexible Constructor Bodies áp dụng cho cả lời gọi constructor lớp cha và lời gọi constructor khác trong cùng lớp.

| Lời gọi | Mục đích | Điều xảy ra tiếp theo |
|---|---|---|
| `super(...)` | Chọn constructor của lớp cha trực tiếp | Chạy constructor lớp cha, rồi đến các initializer và epilogue của lớp con |
| `this(...)` | Chuyển việc khởi tạo sang constructor khác của cùng lớp | Chạy constructor được gọi; constructor đó tiếp tục chuỗi khởi tạo |

Ví dụ, constructor công khai kiểm tra và chuẩn hóa dữ liệu rồi chuyển cho constructor nội bộ:

~~~java
import java.util.Locale;
import java.util.Objects;

final class User {
    private final String name;
    private final String source;

    User(String rawName) {
        String normalized = normalize(rawName);

        if (normalized.length() > 40) {
            throw new IllegalArgumentException("Tên quá dài");
        }

        this(normalized, "api");
    }

    private User(String normalizedName, String source) {
        this.name = normalizedName;
        this.source = source;
    }

    private static String normalize(String value) {
        Objects.requireNonNull(value, "value");
        return value.strip().toLowerCase(Locale.ROOT);
    }
}
~~~

Constructor đầu tiên không gọi `super(...)` trực tiếp mà gọi `this(...)`. Constructor được ủy quyền chịu trách nhiệm tiếp tục khởi tạo object và gọi constructor lớp cha theo chuỗi thông thường.

Không được tạo chuỗi `this(...)` đệ quy dẫn tới chính constructor ban đầu. Trình biên dịch kiểm tra vòng lặp gọi constructor này.

## Vì sao phải ghi rõ super() khi muốn có prologue?

Nếu constructor không chứa lời gọi constructor tường minh, Java tự chèn lời gọi `super()`. Trong trường hợp đó, các câu lệnh trong thân constructor được xem là epilogue; constructor cha đã chạy trước khi các câu lệnh này được thực hiện.

Vì vậy, nếu muốn thực hiện kiểm tra hoặc gán field trước constructor cha không tham số, hãy viết rõ `super();` ở sau prologue:

~~~java
class Parent {
    Parent() { }
}

class Child extends Parent {
    Child(String value) {
        String normalized = normalize(value);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("value rỗng");
        }

        super();
    }
}
~~~

Nếu bỏ `super();`, lời gọi constructor cha mặc định sẽ diễn ra trước các câu lệnh trong thân constructor và bạn sẽ mất vị trí để đặt prologue.

## Những gì không được làm trước super(...) hoặc this(...)

Early construction context được giới hạn để tránh sử dụng một object chưa hoàn tất khởi tạo.

| Thao tác trong prologue | Được phép? | Giải thích |
|---|---|---|
| Kiểm tra tham số constructor | Có | Tham số đã được truyền vào constructor. |
| Khai báo biến cục bộ | Có | Biến cục bộ không truy cập instance đang tạo. |
| Gọi static method | Có | Không cần instance hiện tại. |
| Gọi method trên tham số hoặc object độc lập | Có | Miễn là không truy cập instance đang tạo. |
| Ném exception | Có | Có thể dừng khởi tạo trước khi gọi constructor cha. |
| Đọc `this.field` hoặc field instance không định danh | Không | Instance chưa được phép truy cập. |
| Gọi instance method của lớp đang tạo | Không | Method có thể đọc trạng thái chưa khởi tạo. |
| Dùng `super.field` hoặc gọi method qua `super` | Không | Chưa thể truy cập phần instance của lớp cha. |
| Gán trực tiếp blank field của lớp đang tạo bằng `=` trước `super(...)` | Có, có giới hạn | Đây là ngoại lệ được đặc tả cho Flexible Constructor Bodies. |
| Tạo inner class cần instance đang tạo làm enclosing instance | Không | Thao tác này sẽ sử dụng instance quá sớm. |

Ví dụ không hợp lệ:

~~~java
import java.util.Objects;

class Parent {
    Parent() { }
}

class Child extends Parent {
    private String name;

    Child(String rawName) {
        if (this.name == null) {  // Không được đọc this.name
            validate();           // Không được gọi instance method
        }
        super();
    }

    private void validate() { }
}
~~~

Hãy chuyển logic cần thiết sang biến cục bộ và static helper:

~~~java
import java.util.Objects;

class Parent {
    Parent() { }
}

class Child extends Parent {
    private final String name;

    Child(String rawName) {
        String normalized = normalize(rawName);

        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Tên rỗng");
        }

        this.name = normalized;
        super();
    }

    private static String normalize(String rawName) {
        return Objects.requireNonNull(rawName).strip();
    }
}
~~~

## Lưu ý thiết kế khi dùng Flexible Constructor Bodies

- **Validate càng sớm càng tốt:** Nếu tham số sai, ném exception trước khi constructor cha mở tài nguyên hoặc tạo tác dụng phụ.
- **Chuẩn hóa bằng helper độc lập:** Static method giúp tách quy tắc chuẩn hóa khỏi trạng thái của object.
- **Giữ prologue dễ đọc:** Tính toán thành biến cục bộ có tên, sau đó gọi `super(...)` hoặc `this(...)` với các giá trị đã sẵn sàng.
- **Chỉ gán field sớm khi có lý do:** Ví dụ cần bảo đảm field được thiết lập trước khi constructor cha gọi method override.
- **Hạn chế gọi method override từ constructor cha:** Gán field sớm có thể tránh một số giá trị mặc định, nhưng không làm cho việc gọi method có thể override từ constructor trở nên an toàn trong mọi trường hợp.
- **Không để lộ object đang khởi tạo:** Tránh đăng ký listener, callback hoặc đưa tham chiếu tới object chưa hoàn tất vào code bên ngoài.
- **Kiểm tra thứ tự initializer:** Field initializer và instance initializer có thứ tự chạy riêng trong quá trình khởi tạo. Nếu cần gán field trước super, hãy dùng blank field và xác định rõ nơi field được gán.

## Phiên bản Java cần dùng

| Mục tiêu | Phiên bản |
|---|---|
| Dùng tính năng như cú pháp stable | JDK 25 trở lên |
| Dùng bản LTS mới nhất tại 25/11/2026 | JDK 25 LTS |
| Dùng feature release mới nhất tại 25/11/2026 | JDK 27 |
| JDK 22 | Preview lần đầu, JEP 447 |
| JDK 23 | Preview lần hai, JEP 482 |
| JDK 24 | Preview lần ba, JEP 492 |

Từ JDK 25, không cần `--enable-preview` để biên dịch hoặc chạy Flexible Constructor Bodies. Nếu dự án vẫn phải chạy trên JDK 24 hoặc cũ hơn, không thể coi tính năng này là cú pháp stable trên các runtime đó. Không nên bật preview trong môi trường production chỉ để giữ cú pháp của giai đoạn thử nghiệm.

Có thể biên dịch mã stable bằng JDK 25 trở lên mà không bật preview:

~~~bash
javac --release 25 FlexibleConstructorDemo.java
java FlexibleConstructorDemo
~~~

Nếu dùng JDK 27, có thể biên dịch với `--release 25` để tạo bytecode hướng tới baseline Java 25, miễn là mã không dùng API mới hơn Java 25.

## Tài liệu tham khảo

- [JEP 447 – Statements before super(...) (JDK 22 Preview)](https://openjdk.org/jeps/447)
- [JEP 482 – Flexible Constructor Bodies (JDK 23 Second Preview)](https://openjdk.org/jeps/482)
- [JEP 492 – Flexible Constructor Bodies (JDK 24 Third Preview)](https://openjdk.org/jeps/492)
- [JEP 513 – Flexible Constructor Bodies (JDK 25 Final)](https://openjdk.org/jeps/513)
- [Flexible Constructor Bodies – Java SE 27 Language Guide](https://docs.oracle.com/en/java/javase/27/language/flexible-constructor-bodies.html)
- [Java Language Changes Summary – Java SE 27](https://docs.oracle.com/en/java/javase/27/language/java-language-changes-summary.html)
- [Java SE 27 – Java Downloads, Current Release and LTS](https://www.oracle.com/java/technologies/downloads/)
- [Java Language Specification – Java SE 27](https://download.java.net/java/early_access/jdk27/docs/specs/jls27.pdf)

