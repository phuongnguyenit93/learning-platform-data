# Xử lý ngoại lệ và tránh tác dụng phụ khi khởi tạo thất bại

> **Chương:** Hàm khởi tạo linh hoạt  
> **Phiên bản:** Java 25 — *Flexible Constructor Bodies*, JEP 513, đã là tính năng chính thức.  
> **Trọng tâm:** Đặt bước kiểm tra dữ liệu và xử lý ngoại lệ **trước** lời gọi `super(...)` hoặc `this(...)` khi phù hợp; hiểu thứ tự khởi tạo và thiết kế an toàn trước tác dụng phụ nếu việc tạo đối tượng thất bại.

## 1. Bài toán: đối tượng không được tạo nhưng hệ thống vẫn đã thay đổi

Giả sử lớp `Subscription` kế thừa `Account`. Constructor của `Account` ghi một sự kiện vào audit log; constructor của `Subscription` kiểm tra số tháng đăng ký.

Một thiết kế đặt validation **sau** `super(...)` có thể diễn ra như sau:

~~~text
new Subscription("CUS-01", -3)
  ├─ Account(...) ghi audit "account created"
  ├─ Subscription kiểm tra duration < 0
  └─ IllegalArgumentException
~~~

Ở cuối luồng, **không có `Subscription` hợp lệ được trả về**, nhưng audit, counter hoặc một tác dụng phụ khác đã xảy ra. Ngoại lệ Java không tự rollback những tác dụng phụ như ghi file, gọi HTTP, gửi message, thay đổi database hay tăng bộ đếm.

Java 25 cho phép đặt câu lệnh **trước** lời gọi constructor khác:

~~~java
Subscription(String customerId, int months) {
    if (months <= 0) {
        throw new IllegalArgumentException("months must be positive");
    }
    super(customerId);
    this.months = months;
}
~~~

Đây là khả năng được chuẩn hóa bởi **JEP 513**. Nó giúp *fail fast*: loại đầu vào không hợp lệ trước khi gọi superclass constructor. Tuy nhiên, **không biến việc tạo đối tượng thành giao dịch nguyên tử**. Nếu prologue tự tạo side effect, hoặc superclass constructor ném ngoại lệ sau khi làm việc bên ngoài, các side effect đó vẫn có thể tồn tại.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `prologue`, `super/this invocation` và `epilogue` của constructor Java 25.
2. Dùng validation, chuẩn hóa dữ liệu và `try/catch` trong prologue mà không truy cập trạng thái instance chưa hoàn tất.
3. Giải thích chuyện gì xảy ra nếu ngoại lệ đến từ prologue, `super(...)`, initializer hoặc epilogue.
4. Chứng minh việc ném ngoại lệ **không đồng nghĩa rollback**.
5. Thiết kế factory/two-phase activation để quản lý resource hoặc side effect khó hoàn tác.
6. Viết test xác nhận **superclass chưa được gọi** khi validation đầu vào thất bại.
7. Tránh pattern rủi ro như làm I/O sớm, để `this` thoát khỏi constructor hoặc bắt lỗi rồi tiếp tục với đối tượng không hợp lệ.

## 2. Quy tắc Java 25: prologue, constructor invocation, epilogue

Một constructor có explicit constructor invocation được mô tả khái quát:

~~~java
class Child extends Parent {
    Child(String raw, int amount) {
        // (1) PROLOGUE: được phép có câu lệnh trước invocation.
        String clean = java.util.Objects.requireNonNull(raw).strip();
        if (clean.isEmpty() || amount <= 0) {
            throw new IllegalArgumentException("invalid arguments");
        }

        // (2) EXPLICIT CONSTRUCTOR INVOCATION:
        super(clean);

        // (3) EPILOGUE:
        this.amount = amount;
    }

    private final int amount;
}
~~~

Ba pha có ý nghĩa:

| Pha | Thực hiện | Có thể làm | Ràng buộc chính |
|---|---|---|---|
| **Prologue** | Trước lời gọi `super(...)` / `this(...)` | Kiểm tra tham số, tính giá trị local, bắt lỗi tính toán, gán trực tiếp một số field của chính lớp | Bị giới hạn bởi **early construction context**, không được dùng instance như đối tượng đã khởi tạo xong |
| **Invocation** | Gọi constructor của superclass hoặc constructor khác trong cùng lớp | Chuyển dữ liệu đã chuẩn hóa và được kiểm tra | Một constructor body có nhiều nhất một explicit invocation; không nhét `super(...)` vào `if` / `try` |
| **Epilogue** | Sau explicit invocation thành công | Gán field, chạy logic hoàn thiện trạng thái của lớp | Có thể ném lỗi; side effect của các bước trước vẫn tồn tại |

Nếu không có explicit `super(...)` hay `this(...)`, Java thường chèn **implicit `super()` tại đầu**, không tự động coi các câu lệnh đầu constructor thành prologue. Muốn thực thi validation trước superclass constructor, hãy viết explicit invocation đúng vị trí.

~~~mermaid
flowchart TD
    A["new Child(args)"] --> B["Phân bổ object,\nthiết lập giá trị mặc định"]
    B --> C["Prologue của Child"]
    C --> D{"Hoàn thành bình thường?"}
    D -->|Không| X["Lỗi thoát ra\nkhông gọi constructor tiếp theo"]
    D -->|Có| E["Gọi this(...) hoặc super(...)"]
    E --> F{"Invocation hoàn thành?"}
    F -->|Không| X
    F -->|Có| G["Instance/field initializers\nkhi đến lượt của lớp"]
    G --> H["Epilogue"]
    H --> I{"Hoàn thành bình thường?"}
    I -->|Không| X
    I -->|Có| J["new trả instance"]
~~~

Sơ đồ tóm tắt ý nghĩa. Thứ tự chi tiết khi có chuỗi `this(...)` thuộc quy tắc khởi tạo đối tượng của **JLS `12.5**: mỗi constructor có thể có prologue riêng; nếu gọi `this(...)`, constructor được ủy quyền tiếp tục chuỗi tới superclass và phần khởi tạo của lớp chỉ chạy theo một trình tự thích hợp, không được chạy lại tùy tiện. Xem JLS cho trường hợp phức tạp.

**Một điểm dễ hiểu sai:** bộ nhớ cho object có thể đã được cấp phát và các class có thể đã được khởi tạo tĩnh trước khi prologue chạy. "Fail fast trước `super`" nghĩa là tránh **thực thi phần constructor sau đó**, không có nghĩa không hề cấp phát bộ nhớ hay chưa xảy ra bất kỳ class initialization nào.

## 3. Ví dụ 1 — Chặn input lỗi trước side effect của superclass

Lưu thành `ValidateFirst.java`:

~~~java
public class ValidateFirst {

    static class Account {
        static int createdAttempts;

        Account(String customerId) {
            createdAttempts++;
            System.out.println("Account constructor: " + customerId);
        }
    }

    static final class Subscription extends Account {
        final int months;

        Subscription(String customerId, int months) {
            if (customerId == null || customerId.isBlank()) {
                throw new IllegalArgumentException("customerId required");
            }
            if (months <= 0) {
                throw new IllegalArgumentException("months must be positive");
            }

            String normalized = customerId.strip();
            super(normalized);
            this.months = months;
        }
    }

    public static void main(String[] args) {
        try {
            new Subscription("CUS-01", -3);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        System.out.println("Account calls: " + Account.createdAttempts);

        var active = new Subscription(" CUS-02 ", 12);
        System.out.println("Months: " + active.months);
        System.out.println("Account calls: " + Account.createdAttempts);
    }
}
~~~

Chạy trên JDK 25:

~~~bash
java --version
javac --version
javac ValidateFirst.java
java ValidateFirst
~~~

Kết quả mong đợi:

~~~text
Rejected: months must be positive
Account calls: 0
Account constructor: CUS-02
Months: 12
Account calls: 1
~~~

**Giải thích:** Với `months = -3`, prologue ném `IllegalArgumentException`. `Account` constructor chưa được gọi nên counter không tăng. Với input hợp lệ, chuỗi chuẩn hóa được truyền vào `super(normalized)`, rồi epilogue gán `months`.

Đây là điều **Java 25 giải quyết tốt**: chặn những đầu vào không hợp lệ đã biết **trước một superclass constructor có side effect**. Nó không khẳng định superclass an toàn trong mọi lỗi (chẳng hạn superclass có thể ghi log rồi ném exception).

## 4. So sánh: validation sau super không bảo đảm tránh side effect

Lưu thành `LateValidation.java`:

~~~java
public class LateValidation {

    static class Account {
        static int calls;

        Account(String customerId) {
            calls++;
            System.out.println("Account constructor called");
        }
    }

    static final class BadSubscription extends Account {
        BadSubscription(String customerId, int months) {
            super(customerId);  // Đã chạy trước khi kiểm tra months.
            if (months <= 0) {
                throw new IllegalArgumentException("invalid months");
            }
        }
    }

    static final class GoodSubscription extends Account {
        GoodSubscription(String customerId, int months) {
            if (months <= 0) {
                throw new IllegalArgumentException("invalid months");
            }
            super(customerId);
        }
    }

    public static void main(String[] args) {
        try {
            new BadSubscription("A", -1);
        } catch (IllegalArgumentException ignored) {
            System.out.println("BadSubscription failed");
        }
        System.out.println("calls after bad: " + Account.calls);

        try {
            new GoodSubscription("B", -1);
        } catch (IllegalArgumentException ignored) {
            System.out.println("GoodSubscription failed");
        }
        System.out.println("calls after good: " + Account.calls);
    }
}
~~~

Kết quả:

~~~text
Account constructor called
BadSubscription failed
calls after bad: 1
GoodSubscription failed
calls after good: 1
~~~

Bài học từ con số `1` ở cuối: lỗi tạo object **không hoàn tác** lần tăng counter từ `BadSubscription`. `GoodSubscription` chặn input lỗi trước khi tăng counter, nhưng counter lịch sử không tự trở về `0`. Nếu side effect là ghi database, gửi email hoặc message, hậu quả còn lớn hơn.

## 5. Kiểm soát ngoại lệ trong prologue

Prologue Java 25 được phép chứa câu lệnh như `if`, `try/catch` và phép tính local hợp lệ trong **early construction context**. Đây là nơi tốt để xử lý dữ liệu nhập trước khi chuyển tới `super(...)` hoặc `this(...)`.

### 5.1. Phân biệt lỗi cú pháp với lỗi quy tắc nghiệp vụ

Ví dụ muốn constructor cha nhận một `URI` hợp lệ, chỉ chấp nhận HTTPS. Lưu `UriEndpointDemo.java`:

~~~java
import java.net.URI;
import java.net.URISyntaxException;

public class UriEndpointDemo {

    static class EndpointBase {
        final URI uri;

        EndpointBase(URI uri) {
            this.uri = uri;
            System.out.println("EndpointBase initialized");
        }
    }

    static final class SecureEndpoint extends EndpointBase {

        SecureEndpoint(String address) {
            URI parsed;

            try {
                parsed = new URI(address);
            } catch (URISyntaxException ex) {
                throw new IllegalArgumentException("Malformed URI", ex);
            }

            if (!"https".equalsIgnoreCase(parsed.getScheme())
                    || parsed.getHost() == null) {
                throw new IllegalArgumentException("Expected absolute HTTPS URI");
            }

            super(parsed);
        }
    }

    public static void main(String[] args) {
        try {
            new SecureEndpoint("not a valid URI %%%");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
            System.out.println(ex.getCause() instanceof URISyntaxException);
        }

        try {
            new SecureEndpoint("http://example.org");
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        var valid = new SecureEndpoint("https://example.org/api");
        System.out.println(valid.uri.getHost());
    }
}
~~~

Kết quả dự kiến:

~~~text
Malformed URI
true
Expected absolute HTTPS URI
EndpointBase initialized
example.org
~~~

Trên luồng lỗi, `EndpointBase` không được khởi tạo vì cả hai tình huống đều bị từ chối trong prologue.

**Lựa chọn exception:**

- `IllegalArgumentException` phù hợp với tham số sai hợp đồng của API; `Objects.requireNonNull(...)` cho một `NullPointerException` có thông điệp rõ.
- Checked exception như `URISyntaxException` có thể được khai báo ở `throws` để caller xử lý, hoặc được bọc trong một exception ở tầng API **với cause được bảo toàn**.
- Tránh `catch (Exception ex)` rồi ném một exception mới không giữ cause; sẽ làm mất dữ kiện điều tra lỗi.
- Nếu validation là quy tắc thuần, ưu tiên một biểu thức hoặc helper **không có side effect**, giúp test dễ hơn.

### 5.2. Vẫn có thể khai báo checked exception từ prologue

Ví dụ minh họa:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

class FileConfig extends BaseConfig {
    FileConfig(Path file) throws IOException {
        String content = Files.readString(file); // Có thể ném IOException.
        if (content.isBlank()) {
            throw new IllegalArgumentException("Empty config");
        }
        super(content);
    }
}

class BaseConfig {
    BaseConfig(String text) {}
}
~~~

Đoạn mã trên hợp lệ trong Java 25: `throws IOException` mô tả lỗi từ prologue. Tuy nhiên, nó **chưa hẳn là thiết kế tối ưu**: đọc file là I/O; dù là tác vụ đọc, nó vẫn tốn thời gian, có thể gặp sự cố và có thể làm constructor khó test. Trong nhiều ứng dụng thực tế, nên đọc/parse/validate cấu hình **bên ngoài constructor** rồi truyền dữ liệu đã chuẩn bị vào object. Ví dụ chỉ chứng minh khả năng ngôn ngữ, không khuyến khích mọi constructor thực hiện I/O.

## 6. Giới hạn quan trọng: không đặt super(...) trong try/catch

Lời gọi `super(...)` hoặc `this(...)` là **constructor invocation đặc biệt**, không phải một method call có thể di chuyển tùy ý vào block.

Đoạn **cố ý sai, không biên dịch**:

~~~java
class Parent {
    Parent(int value) {}
}

class InvalidChild extends Parent {
    InvalidChild(int value) {
        try {
            super(value);   // Sai: invocation không nằm trực tiếp ở body.
        } catch (RuntimeException ex) {
            System.out.println("Cannot catch super here");
        }
    }
}
~~~

Tương tự, không thể đặt `super(value)` vào `if`:

~~~java
class AnotherInvalidChild extends Parent {
    AnotherInvalidChild(int value) {
        if (value > 0) {
            super(value); // Sai: không đặt invocation trong nhánh if.
        } else {
            super(0);     // Sai: không có hai invocation thay thế trong if.
        }
    }
}
~~~

**Cách đúng:** kiểm tra/rẽ nhánh để **tạo tham số**, sau đó viết **một lời gọi top-level**:

~~~java
class ValidChild extends Parent {
    ValidChild(int value) {
        int normalized = Math.max(value, 0);
        super(normalized);
    }
}
~~~

Nếu superclass constructor thật sự ném exception sau khi bắt đầu chạy, constructor con **không có cơ chế cục bộ để catch riêng invocation `super(...)`**. Lỗi lan tới caller hoặc một factory bao ngoài `new Child(...)`; xử lý, cleanup hoặc bù trừ cho side effect nên được bố trí ở đó hoặc ngay trong lớp sở hữu side effect.

## 7. Thứ tự ném lỗi và tác dụng phụ: bốn tình huống

| Vị trí lỗi xảy ra | Bước nào chắc chắn đã qua? | Tác dụng phụ có thể còn? | Hướng thiết kế |
|---|---|---|---|
| Trong prologue trước invocation | Chưa chạy constructor được gọi tiếp | **Có**, nếu chính prologue đã làm I/O/cập nhật shared state | Đưa validation thuần lên trước; tránh side effect ở prologue |
| Khi đánh giá đối số `super(...)` / `this(...)` | Prologue đã chạy; constructor đích có thể chưa bắt đầu | Có từ prologue hoặc đánh giá đối số | Tránh hàm tạo side effect trong đối số |
| Bên trong superclass constructor hoặc constructor được ủy quyền | Có thể đã chạy một phần logic ở chuỗi constructor | Có từ các bước đã chạy | Superclass tự bảo toàn invariant; factory/caller xử lý cleanup bên ngoài |
| Ở instance initializer/epilogue sau invocation | Superclass đã hoàn thành; initializer trước đó có thể đã chạy | **Có** từ superclass và các initializer đã hoàn tất | Trì hoãn công bố/đăng ký resource; kích hoạt sau khi object hoàn thiện |

Theo **JLS `12.5**, nếu prologue kết thúc bất thường thì việc xử lý constructor kết thúc bất thường ngay; nếu invocation không hoàn thành thì các initializer/epilogue kế tiếp bị bỏ qua. Nếu initializer/epilogue lỗi, phần đã chạy trước đó không tự được hoàn tác.

### Vấn đề còn xảy ra dù validation đã đặt sớm

~~~java
class ParentService {
    ParentService(String key) {
        ExternalAudit.record("constructing " + key);
        throw new IllegalStateException("remote setup failed");
    }
}

class ChildService extends ParentService {
    ChildService(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("key required");
        }
        super(key);
    }
}
~~~

Dù `ChildService` kiểm tra input trước `super(key)`, nếu `ParentService` tự ghi audit rồi ném lỗi, việc ghi audit vẫn có thể tồn tại. Không nên hiểu “flexible constructor bodies” là cơ chế rollback cho side effect ở **bất kỳ tầng nào**.

Trong ví dụ này, `ExternalAudit` là một dịch vụ giả định nhằm minh họa side effect, không phải lớp thuộc JDK có sẵn.

## 8. Bẫy: gây side effect ngay trong prologue

Cú pháp sau **được phép** về mặt trình tự nhưng thường là thiết kế không an toàn:

~~~java
class Parent {
    Parent(String id) {
        System.out.println("Parent constructed: " + id);
    }
}

class RiskyChild extends Parent {
    RiskyChild(String id, int amount) {
        System.out.println("Sending notification for " + id); // Side effect!
        if (amount <= 0) {
            throw new IllegalArgumentException("invalid amount");
        }
        super(id);
    }
}
~~~

Với `new RiskyChild("CUS-3", -1)`, dòng notification đã được in/ghi trước khi `IllegalArgumentException` xảy ra. Nếu thay `println` bằng gửi email, lập lệnh thanh toán hay xuất message, side effect có thể không thu hồi được.

### Nguyên tắc thực hành

- **Validate first:** kiểm tra input và invariant càng sớm càng tốt.
- **Pure computation:** chuẩn hóa string, tính giá trị đơn vị, parse dữ liệu trong memory khi có thể; không đụng external state.
- **Không công bố instance:** không đưa `this` vào callback, registry, listener hoặc thread đang chạy trước khi constructor thành công.
- **Không cấp phát resource sở hữu lâu dài quá sớm:** nếu cần mở socket/file/connection, dùng lifecycle có cleanup rõ ràng.
- **Commit last:** ghi database/gửi message sau khi object đã đạt trạng thái hợp lệ; nếu có nhiều bước liên quan, dùng transaction/outbox/compensating action theo nhu cầu nghiệp vụ.

“Pure validation” giúp giảm side effect, **không** làm cho constructor trở thành transaction xuyên nhiều hệ thống.

## 9. Tổ chức constructor chain this(...) để tránh lặp validation

Java 25 cũng cho phép prologue trước `this(...)`. Ví dụ muốn nhận timeout bằng số giây nhưng constructor nội bộ dùng `Duration`.

Lưu thành `DelegatingConstructor.java`:

~~~java
import java.time.Duration;
import java.util.Objects;

public class DelegatingConstructor {

    static final class ClientPolicy {
        final String name;
        final Duration timeout;

        ClientPolicy(String rawName, long timeoutSeconds) {
            String normalized = Objects.requireNonNull(rawName).strip();

            if (normalized.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            if (timeoutSeconds <= 0 || timeoutSeconds > 300) {
                throw new IllegalArgumentException("timeout out of range");
            }

            this(normalized, Duration.ofSeconds(timeoutSeconds));
        }

        private ClientPolicy(String name, Duration timeout) {
            this.name = name;
            this.timeout = timeout;
            System.out.println("Policy initialized");
        }
    }

    public static void main(String[] args) {
        try {
            new ClientPolicy(" service ", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        var p = new ClientPolicy(" service ", 30);
        System.out.println(p.name + ": " + p.timeout.getSeconds());
    }
}
~~~

Kết quả:

~~~text
timeout out of range
Policy initialized
service: 30
~~~

**Điểm cần nhớ:**

1. Constructor ngoài chuẩn hóa và kiểm tra giá trị trong prologue.
2. Khi dữ liệu hợp lệ, nó gọi đúng một `this(normalized, Duration.ofSeconds(timeoutSeconds))`.
3. Constructor đích thực hiện phần gán field; nếu prologue ném lỗi thì constructor đích không được gọi.
4. `this(...)` không phải phương thức có thể đưa vào `try` hoặc `if`; nó vẫn là một constructor invocation ở vị trí top-level.

Lưu ý: ngay cả constructor được ủy quyền cũng nên giữ invariant của mình. Nếu constructor nội bộ có đường gọi khác (cùng package, reflection hoặc mở rộng mã về sau), không nên dựa hoàn toàn vào assumption rằng mọi caller đã validation trước.

## 10. Khởi tạo field sớm: tính năng mới và giới hạn an toàn

Java 25 còn cho phép **gán trực tiếp một số instance field của chính lớp đang xây dựng** trong prologue, dù nhìn chung vẫn cấm đọc/dùng instance trước `super(...)`.

Một tình huống là superclass constructor gọi method có thể bị override:

~~~java
public class EarlyFieldAssignment {

    static class Parent {
        Parent() {
            display(); // Dispatch tới override, dù Child chưa hoàn thiện!
        }

        void display() {}
    }

    static class Child extends Parent {
        final int code;

        Child(int code) {
            if (code < 0) {
                throw new IllegalArgumentException("invalid code");
            }
            this.code = code; // Được phép gán trực tiếp trong prologue.
            super();
        }

        @Override
        void display() {
            System.out.println("code=" + code);
        }
    }

    public static void main(String[] args) {
        new Child(42);
    }
}
~~~

Dự kiến:

~~~text
code=42
~~~

**Vì sao được phép?** JLS/Oracle Java 25 cho phép **simple assignment** vào field instance của lớp hiện tại trong early construction context. Tuy nhiên:

- Không được **đọc** field như `int x = this.code;` hoặc `code++` trước invocation.
- Không được gọi instance method như `this.display()`, `display()` hoặc để tham chiếu `this` thoát ra ngoài theo cách thường.
- Không được truy cập field instance thuộc superclass như thể đối tượng đã khởi tạo.
- Các instance variable initializer của lớp con (nếu có) được xử lý **sau** superclass constructor khi đến lượt; cần xét thứ tự để tránh ghi đè ngoài ý muốn, đặc biệt với field không `final`.

**Khuyến nghị an toàn:** việc cho phép gán field sớm không có nghĩa constructor cha gọi method override là một mô hình tốt. Cách thiết kế ít rủi ro hơn vẫn là **không gọi method có thể bị override trong constructor**; nếu cần hook, ưu tiên method `final`/`private` hoặc thiết kế hoạt động sau khi object đã hoàn thiện.

## 11. Nếu constructor cần resource: factory tạo object và cleanup

Một constructor Java không thể bắt ngoại lệ bằng cách bao `super(...)` trong `try/catch`. Nếu cần cấp phát resource rồi thực hiện chuỗi constructor có thể ném lỗi, nên có một điểm sở hữu cleanup **ở bên ngoài lời gọi `new`**, chẳng hạn static factory.

Ví dụ sau minh họa cleanup khi constructor cha không hoàn thành. Lưu thành `FactoryCleanupDemo.java`:

~~~java
import java.util.Objects;

public class FactoryCleanupDemo {

    static final class Lease implements AutoCloseable {
        private boolean closed;

        Lease() {
            System.out.println("lease opened");
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                System.out.println("lease closed");
            }
        }
    }

    static class Base {
        Base(String name) {
            if ("reject".equals(name)) {
                throw new IllegalStateException("base rejected");
            }
        }
    }

    static final class ManagedClient extends Base implements AutoCloseable {
        private final Lease lease;

        private ManagedClient(String name, Lease lease) {
            super(name);
            this.lease = lease;
        }

        static ManagedClient open(String name) {
            Objects.requireNonNull(name, "name");

            // Validate trước khi mở tài nguyên khi có thể.
            if (name.isBlank()) {
                throw new IllegalArgumentException("blank name");
            }

            Lease lease = new Lease(); // Tạo resource có thể có side effect.
            try {
                // Nếu super(name) ném lỗi, catch bên ngoài "new" sẽ chạy.
                return new ManagedClient(name, lease);
            } catch (RuntimeException | Error failure) {
                try {
                    lease.close();
                } catch (RuntimeException closeFailure) {
                    failure.addSuppressed(closeFailure);
                }
                throw failure;
            }
        }

        @Override
        public void close() {
            lease.close();
        }
    }

    public static void main(String[] args) {
        try {
            ManagedClient.open("reject");
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }

        try (var client = ManagedClient.open("ok")) {
            System.out.println("client ready");
        }
    }
}
~~~

Kết quả:

~~~text
lease opened
lease closed
base rejected
lease opened
client ready
lease closed
~~~

**Cơ chế:**

- Input có thể kiểm tra trước khi mở `Lease` được từ chối sớm ở factory.
- Factory mở `Lease`, sau đó gọi `new ManagedClient(...)`.
- Nếu `Base` ném exception, `ManagedClient` không hoàn thành; factory bắt lỗi và đóng resource **mà chính factory vừa tạo**.
- Nếu constructor thành công, quyền sở hữu `Lease` được chuyển sang `ManagedClient`, và caller đóng `ManagedClient` bằng `try-with-resources`.

Nếu `Lease.close()` có thể ném **checked exception**, cần catch/suppress phù hợp với chữ ký thực tế; ví dụ trên sử dụng một `close()` không khai báo checked exception để tập trung vào mô hình sở hữu. Trong hệ thống thật, phải quản lý cả lỗi cleanup, idempotency và việc close có thể thành công một phần.

**Đừng nhầm:** factory không tự rollback database hoặc email từ superclass. Nó chỉ kiểm soát được những resource và hành động mà factory **thật sự sở hữu**.

### Một lựa chọn khác: two-phase activation

Thay vì constructor thực hiện kết nối mạng, đăng ký event listener hoặc bắt đầu thread:

~~~text
validate input
  → new đối tượng với trạng thái trong bộ nhớ
  → start()/connect()/register()
  → khi thành công mới publish object ra ngoài
~~~

Khi giai đoạn `start()` thất bại, component chịu trách nhiệm cleanup và đưa hệ thống về trạng thái xác định. Cách này thường hợp lý hơn với service, database client hoặc thành phần hạ tầng có vòng đời. Nó cũng phù hợp với dependency injection framework, nơi công cụ quản lý lifecycle thực sự được quy định rõ.

## 12. Thiết kế an toàn khi ngoại lệ đến từ superclass

Không phải lúc nào subclass cũng kiểm soát được hành vi constructor cha, đặc biệt khi kế thừa lớp thư viện.

Giả sử superclass thực hiện:

~~~java
class RemoteSession {
    RemoteSession(String endpoint) {
        registry.add(endpoint);       // Đã thay đổi shared state.
        connect(endpoint);            // Có thể ném ngoại lệ.
    }
}
~~~

Đây là **mã minh họa khái niệm** (`registry` và `connect` không phải Java API có sẵn). Nếu `connect(...)` ném lỗi, việc `registry.add(...)` vẫn đã xảy ra. Một subclass dùng Java 25 validation trước `super(endpoint)` chỉ chặn những lỗi **có thể dự đoán từ input**; nó không sửa được transaction boundary bên trong `RemoteSession`.

Khi có quyền thiết kế lớp cha, nên:

1. Kiểm tra tham số trước khi làm side effect.
2. Trì hoãn đăng ký resource/đối tượng cho đến khi cấu hình và khởi tạo logic đã đạt trạng thái hợp lệ.
3. Dùng `try/finally` hoặc `try-with-resources` tại **nơi sở hữu resource** để dọn dẹp khi có lỗi.
4. Đảm bảo lỗi cleanup không che lấp lỗi gốc; thêm lỗi dọn dẹp dưới dạng `suppressed` nếu thích hợp.
5. Dùng transaction cho thao tác database có thể giao dịch, và dùng outbox/compensation cho các side effect ngoài transaction (message/email/network).
6. Không gọi method có thể override từ constructor nếu điều đó phơi bày trạng thái chưa sẵn sàng.

**Không giả định mọi side effect đều rollback được.** Email đã gửi hoặc event đã xuất ra một hệ thống khác có thể cần cơ chế bù trừ/thông báo điều chỉnh chứ không thể “undo” bằng `catch`.

## 13. Giới hạn của early construction context

JEP 513 nới quy tắc “`super(...)` phải là statement đầu tiên” nhưng không hủy các quy tắc bảo vệ instance chưa khởi tạo.

| Việc định làm trong prologue | Tình trạng trong Java 25 | Lý do / hướng xử lý |
|---|---|---|
| Kiểm tra tham số bằng `if` | Hợp lệ | Không cần đọc instance |
| Chuẩn hóa tham số vào biến local | Hợp lệ | Thao tác trên input/local |
| `try/catch` quanh phép parse | Hợp lệ | Invocation vẫn nằm top-level |
| Gọi helper `static` không dùng instance | Hợp lệ | Không tham chiếu đối tượng đang xây |
| `this.code = input` | Có thể hợp lệ | Simple assignment vào field trực tiếp của lớp đang xây; tuân thủ definite assignment |
| `int old = this.code` | Không hợp lệ trước invocation | Đọc instance quá sớm |
| `this.code++` | Không hợp lệ trước invocation | Có thao tác đọc rồi ghi |
| `this.validate()` | Không hợp lệ trước invocation | Gọi instance method quá sớm |
| `registry.add(this)` | Không hợp lệ trước invocation | Để `this` thoát ra ngoài khi chưa hoàn tất |
| `super.toString()` | Không hợp lệ trước invocation | Truy cập instance superclass |
| `try { super(...); } catch (...) {}` | Không hợp lệ | Explicit constructor invocation phải nằm trực tiếp trong constructor body |
| `if (...) super(...); else super(...);` | Không hợp lệ | Không đặt invocation trong nhánh |
| Hai invocation `super(...)` và `this(...)` | Không hợp lệ | Constructor body có tối đa một explicit invocation |

Dấu hiệu compile lỗi ở JDK 25 có thể được diễn đạt như “cannot reference this before supertype constructor has been called” hoặc dạng khác tùy context. Không biến một thông báo lỗi cụ thể thành quy tắc ngôn ngữ; tham chiếu JLS `8.8.7 và `8.8.7.1 để xác định chính xác giới hạn.

## 14. Kiểm thử hồi quy: không chạy constructor cha khi input lỗi

Để kiểm tra tính chất “fail before superclass”, có thể viết **JUnit 5** test với counter test-local. Giả sử dự án sử dụng cùng kiểu `ValidateFirst.Subscription` đã định nghĩa ở mục 3, tạo `ValidateFirstTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class ValidateFirstTest {

    @BeforeEach
    void resetCounter() {
        ValidateFirst.Account.createdAttempts = 0;
    }

    @Test
    void invalidDurationNeverRunsSuperclassConstructor() {
        assertThrows(IllegalArgumentException.class,
                () -> new ValidateFirst.Subscription("CUS-1", -5));

        assertEquals(0, ValidateFirst.Account.createdAttempts);
    }

    @Test
    void validInputRunsSuperclassExactlyOnce() {
        new ValidateFirst.Subscription(" CUS-2 ", 12);

        assertEquals(1, ValidateFirst.Account.createdAttempts);
    }
}
~~~

Với JUnit 5 trên test classpath và JDK 25, test này xác nhận một **bất biến quan sát được**: input lỗi không chạy side effect được mô phỏng ở superclass.

Trong hệ thống thật:

- Không dùng **counter static toàn cục** cho test có chạy song song mà không cô lập/reset; ở đây là ví dụ ngắn, có trạng thái dùng chung nên không thích hợp cho parallel test.
- Kiểm tra side effect qua fake/in-memory repository, adapter giả hoặc mock ở nơi phù hợp.
- Bổ sung test exception đến từ superclass: factory có đóng resource không? Cause và suppressed exceptions có được giữ không?
- Nếu side effect là external call, tránh test integration gửi message/email thật khi không có môi trường sandbox.

### Ma trận test tối thiểu

| Kịch bản | Input / lỗi | Kết quả cần chứng minh |
|---|---|---|
| Validation fail trước `super` | `months = -5` | Exception đúng loại, superclass không được gọi |
| Tất cả input hợp lệ | `months = 12` | Constructor chain hoàn thành, field đúng |
| Parse lỗi trong prologue | URI không hợp lệ | Exception bảo toàn cause, superclass chưa được gọi |
| Superclass tự ném lỗi | Parent constructor throw | Constructor con không hoàn thành; side effect trước throw có thể còn |
| Resource đã mở trước khi `new` thất bại | Factory đã mở `Lease` | Factory đóng resource, giữ exception gốc |
| Initializer/epilogue ném lỗi | Logic sau `super` throw | Không có object hợp lệ được trả; cần xem lại side effect đã xảy ra |
| `this(...)` delegation lỗi sớm | Timeout không hợp lệ | Constructor đích không chạy |

## 15. Lỗi thường gặp khi chuyển dự án sang Java 25

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Compiler báo `call to super must be first statement` | Dùng `javac` cũ hoặc cấu hình `--release` thấp hơn 25 | Kiểm tra `java --version`, `javac --version`, compiler plugin/toolchain |
| Dùng Java 25 mà IDE vẫn báo lỗi | Language level / compiler của IDE chưa hỗ trợ | Cập nhật SDK và language level thành 25 |
| `this`/instance method không dùng được trước `super` | Early construction context giới hạn thao tác | Chỉ dùng input/local/static helper; hoặc simple field assignment hợp lệ |
| Đặt `super(...)` trong `try` báo lỗi | Sai vị trí explicit constructor invocation | Đưa invocation ra top-level, bắt lỗi từ bên ngoài `new` |
| Hai nhánh `if` đều gọi `super(...)` | Constructor body không cho invocation trong branch | Tính tham số bằng nhánh/conditional rồi gọi một `super(...)` |
| Input sai nhưng counter/log vẫn thay đổi | Side effect được thực hiện **trước** validation | Chuyển validation thuần lên đầu prologue |
| Prologue kiểm tra đúng nhưng vẫn có side effect khi thất bại | Superclass/initializer/epilogue có side effect trước lỗi | Đặt cleanup ở chủ sở hữu, factory/transaction và dời external side effect |
| Resource bị rò rỉ khi superclass ném lỗi | Mở resource rồi gọi `new` nhưng không cleanup | Dùng factory sở hữu resource; cleanup trong catch/finally |
| Test đôi khi fail vì counter | Shared mutable state của test | Reset/cô lập fixture, tránh test song song trên counter static |
| Dữ liệu field bất ngờ sau `super` | Instance initializer chạy sau prologue và có thể ghi giá trị mới | Xem thứ tự JLS `12.5; tránh gán chồng field không cần thiết |
| Constructor cha gọi override khi subclass chưa sẵn | Dynamic dispatch xảy ra khi tạo instance | Không gọi overridable method trong constructor; nếu bắt buộc, kiểm soát field init thật chặt |
| Exception mới che mất nguyên nhân gốc | Catch và throw không giữ cause hoặc cleanup ném lỗi mới | Dùng exception chaining / suppressed exception đúng cách |

## 16. Bài tập áp dụng

### Bài tập A — Đổi từ validation muộn sang fail fast

Cho hai lớp:

~~~java
class PaymentBase {
    PaymentBase(String accountId) {
        System.out.println("registered " + accountId);
    }
}

class PaymentRequest extends PaymentBase {
    PaymentRequest(String accountId, long cents) {
        super(accountId);
        if (cents <= 0) {
            throw new IllegalArgumentException("cents");
        }
    }
}
~~~

**Yêu cầu:** chuyển validation `cents > 0` và `accountId` không blank lên trước `super(...)`. Giải thích điều gì không còn xảy ra khi input sai. Khi test, không gửi thanh toán thật; thay side effect bằng counter/log test-local.

### Bài tập B — Bảo toàn cause của checked exception

Cho một constructor nhận đường dẫn hoặc URI dạng chuỗi. Viết prologue có `try/catch` để parse; nếu parse lỗi, ném `IllegalArgumentException` với cause gốc, **trước khi** gọi superclass constructor. Hãy chứng minh bằng `assertSame`/`assertInstanceOf` hoặc `getCause()` rằng cause không bị mất.

### Bài tập C — Thiết kế cleanup khi constructor cha thất bại

Mô phỏng resource bằng `AutoCloseable` có counter `opened`/`closed`, superclass đôi khi ném `IllegalStateException`. Viết factory gọi `new` trong `try` và đảm bảo resource được đóng trong `catch`; sau khi object thành công, caller dùng `try-with-resources` để đóng bình thường.

### Bài tập D — Phân biệt lỗi và rollback

Giả sử constructor cha tăng counter trong bộ nhớ rồi ném lỗi. Hãy dự đoán counter sau lần khởi tạo thất bại. Vì sao chuyển validation của lớp con lên prologue **không thể** hoàn tác side effect này nếu lỗi xảy ra bên trong lớp cha?

### Câu hỏi tự đánh giá

1. Prologue và epilogue nằm ở đâu khi constructor có `super(...)`?
2. Ngoại lệ trong prologue có ngăn constructor cha chạy không? Khi nào câu trả lời là “có”?
3. Vì sao không thể viết `try { super(...); } catch (...)` trong constructor?
4. Có thể gán `this.code = code` trước `super(...)` không? Có thể đọc `this.code` ở thời điểm đó không?
5. Nếu `super(...)` gọi method override của subclass, rủi ro chính là gì?
6. Nếu factory mở connection rồi constructor ném lỗi, ai có trách nhiệm đóng connection?
7. Vì sao “object không được trả về” không đồng nghĩa “không có side effect”?
8. Khi nào nên dùng static factory/two-phase activation thay cho constructor làm nhiều I/O?

## 17. Checklist thiết kế an toàn

- [ ] Dự án đang dùng **JDK 25** cho compiler và runtime; không dựa vào hướng dẫn preview cũ.
- [ ] Validation đầu vào không cần instance state được thực thi trước `super(...)` / `this(...)`.
- [ ] Prologue ưu tiên thao tác thuần, không gửi email/message, không tạo transaction ngoài ý muốn.
- [ ] Một constructor body có tối đa một explicit constructor invocation tại top-level.
- [ ] Không đọc/công bố `this` hoặc gọi instance method trong early construction context.
- [ ] Nếu gán field sớm, đã xét definite assignment và thứ tự initializer sau `super(...)`.
- [ ] Constructor cha không gọi method override nếu có thể tránh.
- [ ] Exception giữ cause; nếu cleanup lỗi, cân nhắc suppressed exception.
- [ ] Resource mở trước bước có thể thất bại có chủ sở hữu cleanup rõ ràng.
- [ ] Các side effect khó hoàn tác được kích hoạt **sau khi object đạt trạng thái hợp lệ** hoặc được bọc bởi transaction/compensation phù hợp.
- [ ] Có test input lỗi không chạy superclass constructor, test lỗi giữa chừng và test cleanup.
- [ ] Nếu dùng Maven/Gradle/IDE, toolchain và source level đều hỗ trợ Java 25.

## 18. Tài liệu chính thức

- [OpenJDK JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513): đề xuất đã được hoàn thiện trong JDK 25, mục tiêu validation/khởi tạo sớm và giới hạn.
- [Oracle JDK 25 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html): ví dụ prologue trước `super(...)`, early construction context, gán field trực tiếp và record constructor.
- [Java SE 25 JLS `8.8.7 — Constructor Body](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7): cú pháp prologue/epilogue và giới hạn constructor invocation.
- [Java SE 25 JLS `8.8.7.1 — Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7.1): luật explicit `this(...)` / `super(...)` và early construction context.
- [Java SE 25 JLS `12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.5): thứ tự xử lý prologue, invocation, instance initializers và epilogue khi có ngoại lệ.
- [Java SE 25 JLS `16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se25/html/jls-16.html): quy tắc gán field/local variable trong constructor.

> **Ghi nhớ:** Java 25 giúp constructor **kiểm tra và từ chối sớm** trước `super(...)` / `this(...)`, nhưng **không tự rollback** I/O, resource hay thay đổi trạng thái đã xảy ra. Đặt validation thuần ở prologue; giao quyền sở hữu cleanup cho nơi tạo resource và hoãn side effect cho đến khi trạng thái được xác nhận.
