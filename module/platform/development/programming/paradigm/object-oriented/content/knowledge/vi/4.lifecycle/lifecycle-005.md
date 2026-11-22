# Hàm tạo tĩnh (Static Factory Method), Factory và Builder trong Java

Khi viết OOP, câu lệnh `new` không phải cách duy nhất để **lấy một đối tượng**. Ta có thể che constructor sau một phương thức tĩnh, giao việc chọn lớp cụ thể cho một Factory, hoặc thu thập tham số bằng Builder rồi mới tạo đối tượng. Ba cách này cùng liên quan tới **quá trình khởi tạo và vòng đời đối tượng**, nhưng giải quyết những vấn đề khác nhau.

> **Phân biệt ngay từ đầu:** Constructor là cú pháp khởi tạo đối tượng của Java; *static factory method* là phương thức `static` trả về một đối tượng; *Factory* thường là đối tượng/lớp chịu trách nhiệm chọn và cung cấp đối tượng; *Builder* là đối tượng hỗ trợ cấu hình từng bước rồi gọi `build()`. Không có nghĩa cứ gọi một factory là chắc chắn tạo một instance mới.

## 1. Bắt đầu từ constructor và vòng đời đối tượng

Đoạn Java cơ bản:

~~~java
public class User {
    private final String email;

    public User(String email) {
        if (email == null || email.isBlank()) {
            throw new IllegalArgumentException("Email không được rỗng");
        }
        this.email = email.trim();
    }

    public String getEmail() {
        return email;
    }
}
~~~

~~~java
User user = new User("hello@example.com");
System.out.println(user.getEmail());
~~~

Ở biểu thức `new User(...)`, JVM cấp phát/khởi tạo một instance theo quy tắc ngôn ngữ Java và chạy constructor sau bước khởi tạo thích hợp. Constructor có cùng tên lớp, **không có kiểu trả về**, có thể có nhiều phiên bản (overloading), và có thể kiểm tra tính hợp lệ của trạng thái ban đầu.

Tuy nhiên, khi có nhiều cách tạo dữ liệu, constructor bắt đầu bộc lộ nhược điểm về cách đặt tên:

~~~java
// Cùng nhận một double nên không thể khai báo cả hai constructor này:
// Temperature(double celsius)
// Temperature(double fahrenheit)
~~~

Hai constructor phía trên có **cùng chữ ký** `Temperature(double)`; Java không thể phân biệt chúng chỉ bằng tên tham số. Static factory method xử lý được trường hợp đó.

Trong mọi cách tạo đối tượng ở bài này, nhớ phân biệt:

- **Tạo instance:** constructor thực sự chạy cho một đối tượng mới (trực tiếp hoặc bên trong factory/builder).
- **Nhận instance:** phương thức trả về một đối tượng đã tồn tại, đối tượng cache, instance dùng chung, hoặc một implementation cụ thể.
- **Sử dụng và kết thúc sử dụng:** khi không còn tham chiếu mạnh có thể truy cập đến object, object có thể đủ điều kiện cho garbage collection. Factory/Builder không thay đổi nguyên tắc này; tài nguyên bên ngoài như file/socket vẫn phải được đóng đúng cách khi cần.

## 2. Static Factory Method: đặt tên cho các cách tạo

**Static factory method** là phương thức `static` trả về một đối tượng. Nó có thể gọi một constructor, xử lý/chuyển đổi dữ liệu trước khi tạo, hoặc quyết định trả về đối tượng có sẵn.

Ví dụ thực tế: một nhiệt độ có thể được cung cấp theo °C hoặc °F. Ta chỉ lưu **Celsius** làm dạng nội bộ chuẩn:

`Temperature.java` (Java 11+):

~~~java
public final class Temperature {
    private final double celsius;

    // Ẩn cách khởi tạo: bên ngoài phải chọn đơn vị rõ ràng.
    private Temperature(double celsius) {
        if (!Double.isFinite(celsius)) {
            throw new IllegalArgumentException("Nhiệt độ phải là số hữu hạn");
        }
        this.celsius = celsius;
    }

    public static Temperature celsius(double value) {
        return new Temperature(value);
    }

    public static Temperature fahrenheit(double value) {
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("Nhiệt độ phải là số hữu hạn");
        }
        return new Temperature((value - 32.0) * 5.0 / 9.0);
    }

    public double inCelsius() {
        return celsius;
    }

    public double inFahrenheit() {
        return celsius * 9.0 / 5.0 + 32.0;
    }
}
~~~

~~~java
public class Main {
    public static void main(String[] args) {
        Temperature a = Temperature.celsius(30);
        Temperature b = Temperature.fahrenheit(86);

        System.out.println(a.inCelsius()); // 30.0
        System.out.println(b.inCelsius()); // 30.0

        // new Temperature(30); // Không biên dịch: constructor private
    }
}
~~~

Nhờ tên `celsius` và `fahrenheit`, chỗ gọi thể hiện **ý nghĩa** của tham số. Class chỉ công khai các cách tạo hợp lệ; instance không có setter nên không thể cập nhật trường `celsius` sau khi tạo. Dù vậy, hai lời gọi ở ví dụ trên tạo **hai đối tượng riêng**, vì mỗi factory đều gọi `new Temperature(...)`.

### Khi nào static factory hữu ích?

1. **Tên mô tả ý nghĩa:** `of(...)`, `from(...)`, `parse(...)`, `forGuest(...)`, `fromCsv(...)` giúp người đọc hiểu nguồn dữ liệu.
2. **Kiểm tra và chuẩn hóa đầu vào:** factory áp đặt quy tắc hợp lệ trước khi trả đối tượng.
3. **Ẩn implementation:** kiểu trả về có thể là interface/superclass, còn instance là một implementation cụ thể.
4. **Tái sử dụng/caching khi phù hợp:** factory có thể trả instance cũ, singleton hoặc object đã được cache thay vì tạo mới.
5. **Giữ API gọn:** có thể giấu constructor bằng `private`/package-private và tập trung các con đường tạo hợp lệ.

Một số tên thường gặp (chủ yếu là **quy ước**, không phải cú pháp đặc biệt của Java):

| Tên phương thức | Ý nghĩa hay được dùng | Ví dụ gần gũi |
| --- | --- | --- |
| `of(...)` | Tạo/nhận instance từ các tham số | `List.of("a", "b")` |
| `from(...)` | Chuyển dữ liệu/kiểu khác sang kiểu đích | `Instant.from(temporal)` |
| `valueOf(...)` | Lấy object từ giá trị tương ứng | `Integer.valueOf(42)` |
| `parse(...)` | Phân tích chuỗi để có giá trị kiểu đích | `LocalDate.parse("2026-10-15")` |
| `getInstance(...)` | Lấy một instance, có thể dùng chung | Tên do thư viện tự định nghĩa |
| `newInstance(...)` | Tên gợi ý tạo mới | Tên do thư viện tự định nghĩa |

Không suy ra hành vi cache/chắc chắn tạo mới **chỉ từ tên**. Luôn xem hợp đồng của API: chẳng hạn `Integer.valueOf` có thể trả object cache cho một số giá trị, còn `List.of` tạo/nhận một danh sách không sửa được và không bảo đảm danh tính instance.

### Static factory không phải “constructor static”

Java **không có static constructor** theo nghĩa khai báo `static User(...)` hoặc thêm `static` vào constructor. Một khối khởi tạo tĩnh `static { ... }` chạy khi lớp được khởi tạo theo quy tắc JVM; nó dùng để khởi tạo trạng thái tĩnh, **không phải** factory trả về object. Static factory method là phương thức bình thường có từ khóa `static` và có kiểu trả về.

~~~java
public class Config {
    private static final String DEFAULT_REGION;

    static {
        DEFAULT_REGION = "VN"; // Static initializer, không trả về object
    }

    private final String region;

    private Config(String region) {
        this.region = region;
    }

    public static Config defaultConfig() { // Static factory method
        return new Config(DEFAULT_REGION);
    }

    public String region() {
        return region;
    }
}
~~~

## 3. Factory: giao việc lựa chọn loại đối tượng cho một nơi riêng

Static factory ở ví dụ `Temperature` nằm **ngay trong lớp trả về**. Nhưng có hệ thống cần quyết định **loại implementation** dựa trên cấu hình, trường hợp nghiệp vụ hoặc môi trường chạy. Khi đó, một lớp/đối tượng Factory riêng giúp mã gọi không phải rải `new ConcreteType(...)` khắp nơi.

Ví dụ: chọn hình thức gửi thông báo. Để minh họa OOP, hai implementation chỉ in thông báo ra console, **không gửi email/SMS thật**.

`NotificationDemo.java` (Java 11+):

~~~java
interface Notifier {
    void send(String message);
}

final class EmailNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("[EMAIL] " + message);
    }
}

final class SmsNotifier implements Notifier {
    @Override
    public void send(String message) {
        System.out.println("[SMS] " + message);
    }
}

enum Channel {
    EMAIL, SMS
}

final class NotifierFactory {
    private NotifierFactory() {
        // Không cho tạo instance của lớp tiện ích này.
    }

    public static Notifier create(Channel channel) {
        if (channel == null) {
            throw new IllegalArgumentException("Channel không được null");
        }

        switch (channel) {
            case EMAIL:
                return new EmailNotifier();
            case SMS:
                return new SmsNotifier();
            default:
                throw new IllegalArgumentException("Channel không hỗ trợ");
        }
    }
}

public class NotificationDemo {
    public static void main(String[] args) {
        Notifier notifier = NotifierFactory.create(Channel.EMAIL);
        notifier.send("Đơn hàng đã được xác nhận");
        // [EMAIL] Đơn hàng đã được xác nhận

        Notifier sms = NotifierFactory.create(Channel.SMS);
        sms.send("Mã OTP thử nghiệm");
        // [SMS] Mã OTP thử nghiệm
    }
}
~~~

Người gọi chỉ biết `Notifier` và lựa chọn `Channel`. Factory chịu trách nhiệm khởi tạo class thực tế; mã sử dụng interface để gọi `send`. Khi cần thay cách tạo `EmailNotifier` (ví dụ bổ sung các dependency hoặc cấu hình), phần thay đổi có thể được tập trung trong vùng xây dựng đối tượng.

~~~mermaid
flowchart LR
    Client["Client"] --> Factory["NotifierFactory.create(channel)"]
    Factory --> Decision{"Channel"}
    Decision -->|EMAIL| Email["new EmailNotifier()"]
    Decision -->|SMS| SMS["new SmsNotifier()"]
    Email --> Interface["Notifier"]
    SMS --> Interface
    Interface --> Use["Client gọi send(...)"]
~~~

### “Factory” và “Factory Method pattern” có giống nhau?

Không hoàn toàn. Các thuật ngữ dễ bị gọi lẫn nhau:

| Thuật ngữ | Đặc điểm | Ví dụ |
| --- | --- | --- |
| **Static factory method** | Phương thức `static` trả về object; thường nằm ở lớp sản phẩm | `Temperature.fahrenheit(86)` |
| **Simple Factory** | Một hàm/lớp tập trung logic lựa chọn và tạo implementation; không phải một trong 23 mẫu GoF được đặt tên riêng | `NotifierFactory.create(Channel)` ở trên |
| **Factory Method (GoF)** | Lớp cha định nghĩa điểm mở rộng tạo đối tượng, lớp con ghi đè phương thức tạo | `Creator.createProduct()` được subclass cài đặt |
| **Abstract Factory (GoF)** | Cung cấp interface tạo một **họ đối tượng liên quan** mà không buộc client gọi lớp cụ thể | `UiFactory.createButton()` và `createDialog()` cho từng giao diện |

Một ví dụ **Factory Method pattern** tối giản:

~~~java
interface Report {
    String render();
}

final class CsvReport implements Report {
    public String render() {
        return "name,quantity\nBook,2";
    }
}

final class JsonReport implements Report {
    public String render() {
        return "{\"name\":\"Book\",\"quantity\":2}";
    }
}

abstract class ReportService {
    // Thuật toán chung gọi điểm mở rộng do subclass cung cấp.
    public final void printReport() {
        Report report = createReport();
        System.out.println(report.render());
    }

    protected abstract Report createReport(); // Factory Method
}

final class CsvReportService extends ReportService {
    @Override
    protected Report createReport() {
        return new CsvReport();
    }
}

final class JsonReportService extends ReportService {
    @Override
    protected Report createReport() {
        return new JsonReport();
    }
}

// Cách dùng:
ReportService service = new CsvReportService();
service.printReport();
~~~

Ở đây `createReport()` là **instance method** được subclass ghi đè, không cần là `static`. Vì thế, “static factory method” và “Factory Method design pattern” là hai khái niệm khác nhau.

**Điểm cần cân nhắc:** Một factory dùng `switch` tập trung chỗ lựa chọn nhưng khi thêm kênh mới vẫn phải sửa `switch`, nên không tự động đạt nguyên tắc Open/Closed tuyệt đối. Với dự án lớn, có thể dùng đăng ký implementation qua `Map<Channel, Supplier<Notifier>>`, dependency injection hoặc chiến lược cấu hình phù hợp. Không nên áp dụng quá nhiều tầng Factory nếu chỉ có một loại đối tượng đơn giản.

## 4. Builder: cấu hình từng bước trước khi tạo đối tượng

Constructor với nhiều tham số dễ gây nhầm và khó thêm tùy chọn:

~~~java
// Người đọc khó biết 0, 20 và true tương ứng tham số nào:
SearchRequest request = new SearchRequest("java", 0, 20, true);
~~~

Nếu có thêm nhiều tham số không bắt buộc, cách tạo một “rừng constructor” (telescoping constructors) càng khó bảo trì. **Builder pattern** giải quyết bằng đối tượng trung gian có các phương thức đặt tên rõ ràng; chỉ khi gọi `build()` mới tạo đối tượng kết quả.

Ví dụ `SearchRequest` có từ khóa bắt buộc, các tùy chọn `page`, `pageSize` và nhãn lọc.

`SearchRequest.java` (Java 11+):

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class SearchRequest {
    private final String keyword;
    private final int page;
    private final int pageSize;
    private final List<String> tags;

    private SearchRequest(Builder builder) {
        this.keyword = builder.keyword;
        this.page = builder.page;
        this.pageSize = builder.pageSize;
        this.tags = List.copyOf(builder.tags); // Snapshot, không lộ List mutable
    }

    public static Builder builder(String keyword) {
        return new Builder(keyword);
    }

    public String getKeyword() { return keyword; }
    public int getPage() { return page; }
    public int getPageSize() { return pageSize; }
    public List<String> getTags() { return tags; }

    public static final class Builder {
        private final String keyword;
        private int page = 0;          // Giá trị mặc định
        private int pageSize = 20;     // Giá trị mặc định
        private final List<String> tags = new ArrayList<>();

        private Builder(String keyword) {
            String clean = Objects.requireNonNull(keyword, "keyword").trim();
            if (clean.isEmpty()) {
                throw new IllegalArgumentException("Keyword không được rỗng");
            }
            this.keyword = clean;
        }

        public Builder page(int page) {
            if (page < 0) {
                throw new IllegalArgumentException("Page phải >= 0");
            }
            this.page = page;
            return this;
        }

        public Builder pageSize(int pageSize) {
            if (pageSize < 1 || pageSize > 100) {
                throw new IllegalArgumentException("Page size phải trong [1, 100]");
            }
            this.pageSize = pageSize;
            return this;
        }

        public Builder addTag(String tag) {
            String clean = Objects.requireNonNull(tag, "tag").trim();
            if (clean.isEmpty()) {
                throw new IllegalArgumentException("Tag không được rỗng");
            }
            this.tags.add(clean);
            return this;
        }

        public SearchRequest build() {
            return new SearchRequest(this);
        }
    }
}
~~~

`SearchDemo.java`:

~~~java
public class SearchDemo {
    public static void main(String[] args) {
        SearchRequest request = SearchRequest.builder("  java oop  ")
                .page(2)
                .pageSize(25)
                .addTag("core")
                .addTag("interview")
                .build();

        System.out.println(request.getKeyword()); // java oop
        System.out.println(request.getPage());    // 2
        System.out.println(request.getPageSize()); // 25
        System.out.println(request.getTags());    // [core, interview]

        // Khi chỉ có tham số bắt buộc, dùng được giá trị mặc định:
        SearchRequest defaults = SearchRequest.builder("spring").build();
        System.out.println(defaults.getPageSize()); // 20
    }
}
~~~

Phân tích luồng:

~~~mermaid
flowchart TD
    A["SearchRequest.builder(keyword)"] --> B["Tạo Builder, kiểm tra keyword"]
    B --> C["page(), pageSize(), addTag()"]
    C --> D["Builder lưu cấu hình và trả this"]
    D --> E["build()"]
    E --> F["new SearchRequest(builder)"]
    F --> G["Sao chép List; đối tượng kết quả bất biến"]
~~~

- `builder(...)` là **static factory tạo Builder**, chưa tạo `SearchRequest`.
- `page(...), pageSize(...), addTag(...)` cập nhật trạng thái **mutable** của Builder và trả `this` để viết theo chuỗi (fluent API).
- `build()` gọi constructor `private SearchRequest(Builder)` và trả đối tượng đã cấu hình.
- `List.copyOf(builder.tags)` bảo vệ danh sách của `SearchRequest` khỏi các thay đổi sau đó trên Builder. Vì `String` bất biến, các phần tử cũng không bị cập nhật tại chỗ.

Kiểm chứng việc tái sử dụng Builder:

~~~java
SearchRequest.Builder builder = SearchRequest.builder("oop");
builder.addTag("basic");

SearchRequest first = builder.build();

builder.addTag("advanced");
SearchRequest second = builder.build();

System.out.println(first.getTags());  // [basic]
System.out.println(second.getTags()); // [basic, advanced]
System.out.println(first == second);  // false
~~~

**Chú ý:** Builder trong ví dụ là đối tượng mutable và **không được thiết kế thread-safe**; không nên chia sẻ Builder cho nhiều luồng sửa đồng thời. `build()` cũng **không bắt buộc phải tạo mới** theo mọi API Builder trên thế giới, nhưng trong implementation mẫu của chúng ta, mỗi lần gọi đều thực hiện `new SearchRequest(...)`.

## 5. Chọn cách tạo phù hợp với bài toán

| Tiêu chí | Constructor | Static Factory Method | Factory riêng | Builder |
| --- | --- | --- | --- | --- |
| Cú pháp điển hình | `new Order(...)` | `Order.from(...)` | `factory.create(...)` | `Order.builder().build()` |
| Mục tiêu chính | Khởi tạo trực tiếp | Đặt tên/chọn quy tắc trả object | Tập trung logic chọn implementation/tạo phụ thuộc | Cấu hình nhiều tham số rõ nghĩa |
| Có cần tạo instance mới mỗi lần? | Có, khi dùng `new` | Không nhất thiết | Không nhất thiết | Tùy hợp đồng của `build()` |
| Tham số tùy chọn | Dùng overload, đôi khi rối | Có thể có overload | Tùy API | Thuận tiện cho nhiều tùy chọn |
| Ẩn lớp triển khai cụ thể | Không khi gọi trực tiếp | Có thể | Thường có | Có thể |
| Chi phí thiết kế | Thấp | Thấp đến vừa | Vừa | Vừa đến cao |

Một số tình huống chọn nhanh:

- **`Point(int x, int y)`**: dữ liệu đơn giản, ít tham số, tạo rõ ràng → constructor thường đủ.
- **`Temperature.celsius(30)` / `fahrenheit(86)`**: cùng loại tham số nhưng khác ý nghĩa → static factory.
- **Chọn bộ mã hóa/gửi thông báo theo cấu hình** → Factory cung cấp interface thích hợp.
- **Cấu hình nhiều trường bắt buộc/tùy chọn, cần giá trị mặc định và validation** → Builder.
- **Tạo object rất phức tạp, cần cả chọn implementation và cấu hình từng bước** → có thể kết hợp Factory cung cấp một Builder, rồi gọi `build()`.

Các phương pháp **không loại trừ nhau**: class có thể dùng constructor `private`, static factory trả `Builder`, Factory khác quyết định triển khai, còn Builder gọi constructor để tạo kết quả.

## 6. Liên quan đến dependency injection và Spring

Trong ứng dụng Spring, container thường là bên chịu trách nhiệm khởi tạo/quản lý bean và tiêm dependency. Vì vậy, Factory trong dự án thật có thể cần **các dependency được inject**, thay vì tự `new` mọi dịch vụ.

Ví dụ tối giản:

~~~java
import org.springframework.stereotype.Component;

@Component
public class NotifierSelector {
    private final EmailService emailService;
    private final SmsService smsService;

    public NotifierSelector(EmailService emailService, SmsService smsService) {
        this.emailService = emailService;
        this.smsService = smsService;
    }

    public MessageSender select(Channel channel) {
        return switch (channel) {
            case EMAIL -> emailService;
            case SMS -> smsService;
        };
    }
}
~~~

Ở đây giả định `EmailService` và `SmsService` là bean đã tồn tại, cùng implement `MessageSender`, còn `Channel` là enum có `EMAIL`, `SMS`. Đoạn code mang tính minh họa **tích hợp Spring**; không phải chương trình Java độc lập như các ví dụ phía trên. Với selector này, `select` **trả về bean được quản lý sẵn**, không tạo service mới. Tránh `new EmailService()` trong logic nếu service cần Spring inject dependency, interceptor, transaction proxy hoặc lifecycle callback.

Trong Spring, annotation `@Bean` trên phương thức cấu hình có thể trả object để container quản lý, nhưng không đồng nghĩa mọi `@Bean` method đều là static factory method. Cần phân biệt **cơ chế quản lý bean của framework** và **mẫu tạo đối tượng trong Java thuần**.

## 7. Những lỗi và hiểu nhầm phổ biến

**1. Tưởng static factory luôn tạo mới**

~~~java
Integer a = Integer.valueOf(42);
Integer b = Integer.valueOf(42);

System.out.println(a.equals(b)); // true
// a == b không nên dùng để kiểm tra bằng nhau về giá trị.
~~~

`valueOf` có thể dùng cache; ứng dụng nên dựa vào **hợp đồng dữ liệu** (`equals` khi muốn so sánh giá trị), không phụ thuộc việc factory cấp phát instance nào. Với object mutable, dùng chung instance có thể gây sửa trạng thái ngoài ý muốn, nên chỉ cache/chia sẻ khi có chủ đích.

**2. Đưa logic nghiệp vụ hoặc I/O nặng vào mọi constructor/factory**

Constructor/factory nên đảm bảo trạng thái hợp lệ; các công việc I/O có thể cần thiết theo thiết kế nhưng phải minh bạch về lỗi, tài nguyên, thời gian và side effect. Không biến mỗi `new` hoặc `of` thành lời gọi mạng bất ngờ.

**3. Cho rằng Builder tự động đảm bảo immutable**

Builder thường mutable; object được xây dựng có thể vẫn mutable nếu field/setter/collection bị lộ. Muốn immutable, nên dùng field `private final`, validate đầu vào, defensive copy cho trạng thái mutable, tránh setter công khai và thận trọng với phần tử lồng nhau.

**4. Chỉ kiểm tra từng setter mà bỏ qua ràng buộc giữa các trường**

Nếu `startDate` phải trước `endDate`, riêng `startDate(...)` và `endDate(...)` có thể chưa đủ để xác thực. Kiểm tra ràng buộc chung ở `build()` hoặc constructor cuối:

~~~java
public TimeRange build() {
    if (start == null || end == null || !start.isBefore(end)) {
        throw new IllegalStateException("Khoảng thời gian không hợp lệ");
    }
    return new TimeRange(start, end);
}
~~~

Mã trên là phác thảo phần `build()` khi lớp Builder có các trường `start`, `end` kiểu `LocalDateTime` (hoặc kiểu thời gian so sánh tương đương); nó nhấn mạnh **thời điểm kiểm tra bất biến tổng thể**.

**5. Overengineering**

Một class hai tham số rõ ràng không cần Builder hàng trăm dòng. Không cần tạo `FactoryFactory` chỉ để bọc một câu lệnh `new`. Chọn abstraction khi nó thực sự cải thiện ý nghĩa lời gọi, mở rộng implementation hoặc kiểm soát khởi tạo.

**6. Hiểu sai khi kết hợp với kế thừa**

Constructor không được override. Static method trong Java có thể bị **method hiding**, không phải overriding đa hình theo instance; nó không đóng vai trò điểm mở rộng giống phương thức `protected createProduct()` trong GoF Factory Method. Với các hệ thống cần polymorphism ở bước tạo, cân nhắc Factory Method, Abstract Factory, hoặc injection.

## 8. Câu hỏi luyện tập

**Câu 1:** Tại sao hai constructor `Temperature(double celsius)` và `Temperature(double fahrenheit)` không thể cùng tồn tại?

**Đáp án:** Chúng có cùng chữ ký kiểu tham số. Tên biến tham số không tham gia phân biệt overload; các static factory được đặt tên `celsius` và `fahrenheit` giải quyết được.

**Câu 2:** Lời gọi `Temperature.fahrenheit(86)` có nhất thiết tạo object mới không?

**Đáp án:** Trong implementation mẫu, có vì nó gọi `new Temperature(...)`. Nhưng về khái niệm static factory method nói chung, không bắt buộc; factory có thể trả object đã tồn tại.

**Câu 3:** `NotifierFactory.create(Channel.EMAIL)` và `ReportService.createReport()` khác nhau điểm nào?

**Đáp án:** Ví dụ đầu là **Simple Factory**, dùng một static method với `switch` để chọn implementation; ví dụ sau là **Factory Method pattern**, để subclass override phương thức tạo `Report`.

**Câu 4:** Vì sao Builder hay dùng `return this`?

**Đáp án:** Để gọi nối tiếp `builder.page(1).pageSize(30).build()`. Đây là fluent API; các bước trước `build()` thay đổi **Builder**, chưa nhất thiết tạo object kết quả.

**Câu 5:** Vì sao `List.copyOf(builder.tags)` xuất hiện trong constructor của `SearchRequest`?

**Đáp án:** Để chụp trạng thái danh sách tại thời điểm tạo. Nếu Builder tiếp tục thêm tag, `SearchRequest` đã tạo không bị thay đổi theo; người dùng cũng không chỉnh sửa List trả từ getter bằng `add/remove`.

**Câu 6:** Nên chọn gì cho một immutable class chỉ có `id` và `name` bắt buộc?

**Đáp án:** Một constructor đơn giản có validation thường đã đủ; thêm static factory nếu cần tên mô tả một cách tạo đặc biệt. Không có lý do mặc định phải dùng Builder.

**Ghi nhớ:** Constructor tạo instance trực tiếp; static factory **đặt tên và kiểm soát cách lấy object**; Factory **chịu trách nhiệm chọn/cung cấp implementation**; Builder **tập hợp cấu hình rồi hoàn tất đối tượng**. Chọn đúng kỹ thuật từ nhu cầu tạo object và quy tắc bất biến của lớp, thay vì áp một mẫu thiết kế cho mọi tình huống.