# Tính toán giá trị trung gian để truyền vào super hoặc this

## 1. Mục tiêu bài học và vấn đề cần giải quyết

Trong Java, constructor của lớp con thường chuyển dữ liệu cho constructor của lớp cha bằng **super(...)**; một constructor cũng có thể chuyển việc khởi tạo sang constructor khác cùng lớp bằng **this(...)**. Đầu vào thực tế không phải lúc nào cũng ở dạng sẵn sàng sử dụng. Ví dụ: cần chuẩn hóa tên, chuyển tiền từ đơn vị thập phân sang số cent, phân tích một địa chỉ URI, kiểm tra kích thước hoặc ngăn số nguyên tràn trước khi chuyển tham số sang constructor đích.

**Java 25** hoàn thiện **Flexible Constructor Bodies (JEP 513)**: có thể đặt các câu lệnh phù hợp **trước** lời gọi constructor tường minh **super(...)** hoặc **this(...)**. Nhờ đó, các phép tính trung gian, kiểm tra hợp lệ và lựa chọn tham số có thể nằm ngay trong constructor thay vì bị ép vào một biểu thức dài hoặc một hàm static chỉ dùng để lách cú pháp. Tính năng đã **final** trong Java 25, không cần **--enable-preview**.

Bài **Tính toán giá trị trung gian để truyền vào super hoặc this**, thuộc chương **Hàm khởi tạo linh hoạt** của lộ trình **JAVA_VERSION_JAVA25**, tập trung vào kỹ thuật Java hiện đại vẫn được hỗ trợ. Đây là một phần của việc khai thác Java 25 cùng các chủ đề chương trình nguồn gọn, module import, ScopedValue, API dẫn xuất khóa, AOT cache và JFR trong lộ trình, nhưng **không yêu cầu** các chủ đề đó để hiểu constructor.

Sau bài học, bạn có thể:

1. Phân biệt **prologue**, **explicit constructor invocation** và **epilogue**.
2. Tính một hoặc nhiều biến cục bộ, kiểm tra dữ liệu và truyền kết quả vào **super(...)**.
3. Chuẩn bị dữ liệu rồi ủy quyền vào **this(...)**, tránh tính trùng và giữ bất biến của đối tượng.
4. Hiểu các giới hạn **early construction context**: không đọc trạng thái instance đang xây dựng, không gọi instance method, nhưng có ngoại lệ gán sớm cho một số field.
5. Kiểm chứng thứ tự thực thi, ngoại lệ, hiện tượng tràn số và luồng constructor chaining.
6. Thiết lập Java 25 cho biên dịch/CI và nhận diện lỗi do dùng compiler release cũ.

## 2. Cấu trúc constructor mới trong Java 25

Một constructor có lời gọi tường minh được hình dung như sau:

~~~java
class Parent {
    Parent(String value) {
        System.out.println("Parent: " + value);
    }
}

class Child extends Parent {
    Child(String raw) {
        // (1) Prologue: kiểm tra, tính toán trên tham số và biến cục bộ.
        String normalized = java.util.Objects.requireNonNull(raw).strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Tên không được rỗng");
        }

        // (2) Chuyển dữ liệu tới constructor lớp cha.
        super(normalized);

        // (3) Epilogue: được phép thao tác với instance đã qua super().
        System.out.println("Child created");
    }
}
~~~

| Pha | Nội dung | Điều cần nhớ |
| --- | --- | --- |
| **Prologue** | Các câu lệnh đứng trước **super(...)** hoặc **this(...)**. | Được dùng tham số, local variables, static members; bị hạn chế sử dụng instance đang xây dựng. |
| **Constructor invocation** | Một lệnh **super(...)** hoặc **this(...)** ở cấp thân constructor. | Chỉ có tối đa một lời gọi constructor tường minh trong thân; phải có đường khởi tạo hợp lệ. |
| **Epilogue** | Các câu lệnh đứng sau lời gọi constructor. | Sau khi chuỗi constructor tương ứng hoàn tất, có thể dùng **this** và instance members theo quy tắc bình thường. |

~~~mermaid
flowchart TD
    A["new Child(raw)"] --> B["Prologue: kiểm tra + chuẩn hóa raw"]
    B --> C{"Dữ liệu hợp lệ?"}
    C -->|Không| E["Throw exception; không gọi super"]
    C -->|Có| D["super(normalized)"]
    D --> F["Constructor lớp cha"]
    F --> G["Khởi tạo instance của Child theo thứ tự Java"]
    G --> H["Epilogue của Child"]
    H --> I["Đối tượng sẵn sàng trả về"]
~~~

**Quan trọng:** quyền viết câu lệnh ở prologue **không** có nghĩa đối tượng đã được khởi tạo đầy đủ. Java duy trì ràng buộc an toàn đối với việc dùng **this/super** quá sớm. Việc khai báo local variables trước super **không** khiến các field của lớp cha sẵn sàng để đọc.

Nếu constructor **không** chứa lời gọi tường minh và lớp không phải **Object**, compiler vẫn xem như có một **super()** ngầm tại đầu; các câu lệnh đang viết thuộc epilogue. Để có prologue rõ ràng, ta cần viết **super(...)** hoặc **this(...)** tường minh.

## 3. Mẫu cơ bản: tính giá trị trước super(...)

Giả sử một lớp cha nhận kích thước đã kiểm tra, nhưng lớp con nhận chiều dài cạnh thô. Trước khi gọi lớp cha, ta muốn xác minh tính hợp lệ và tính diện tích có kiểm tra tràn số:

~~~java
class Area {
    private final long squareUnits;

    Area(long squareUnits) {
        if (squareUnits <= 0) {
            throw new IllegalArgumentException("Diện tích phải dương");
        }
        this.squareUnits = squareUnits;
    }

    long squareUnits() {
        return squareUnits;
    }
}

final class SquareArea extends Area {
    SquareArea(long side) {
        if (side <= 0) {
            throw new IllegalArgumentException("Cạnh phải dương");
        }

        // Math.multiplyExact báo lỗi nếu phép nhân long bị tràn.
        long computedArea = Math.multiplyExact(side, side);
        super(computedArea);
    }
}
~~~

**Cách dùng:** **new SquareArea(12).squareUnits()** trả về **144**. Giá trị **side = 0** bị từ chối **trước khi** constructor của Area chạy. Giá trị **side** cực lớn có thể làm **Math.multiplyExact** ném **ArithmeticException** thay vì âm thầm tràn rồi chuyển một kết quả sai cho super.

Nếu tính toán nằm ngay trong lời gọi **super(Math.multiplyExact(side, side))**, code vẫn có thể hợp lệ. Điểm mới của Java 25 là ta có thể chia công việc thành **nhiều bước rõ ràng**: kiểm tra, tính biến cục bộ, kiểm tra tiếp, rồi gọi super với biến đã chuẩn bị.

### Khi nào nên dùng prologue?

Prologue đặc biệt có ích nếu cần **nhiều câu lệnh**, **nhiều giá trị trung gian** hoặc **fail fast trước tác dụng phụ của constructor lớp cha**. Với một biểu thức đơn giản, không cần cố kéo logic ra trước super chỉ để sử dụng tính năng mới.

## 4. Ví dụ hoàn chỉnh: chuẩn hóa chuỗi và đổi tiền sang cent

Trong hệ thống hóa đơn, constructor lớp cha lưu **tên khách hàng chuẩn hóa** và **tổng tiền dạng số nguyên cent**. Lớp con nhận một chuỗi thô cùng **BigDecimal**. Ta muốn tránh xử lý tiền bằng **double** và muốn báo lỗi rõ ràng trước khi gọi lớp cha.

Lưu toàn bộ mã dưới đây vào **InvoiceDemo.java** rồi chạy bằng JDK 25:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class InvoiceDemo {

    static class InvoiceBase {
        private final String customer;
        private final long totalCents;

        InvoiceBase(String customer, long totalCents) {
            this.customer = customer;
            this.totalCents = totalCents;
        }

        String customer() {
            return customer;
        }

        long totalCents() {
            return totalCents;
        }
    }

    static final class Invoice extends InvoiceBase {
        private final BigDecimal sourceAmount;

        Invoice(String rawCustomer, BigDecimal amount) {
            // Prologue: chưa đọc hay gọi member của instance Invoice.
            String customer = Objects.requireNonNull(rawCustomer, "customer")
                    .strip();
            if (customer.isEmpty()) {
                throw new IllegalArgumentException("customer không được rỗng");
            }

            Objects.requireNonNull(amount, "amount");
            if (amount.signum() < 0) {
                throw new IllegalArgumentException("amount không được âm");
            }

            BigDecimal scaled = amount.movePointRight(2);
            long cents = scaled.longValueExact();

            // Giá trị đã được tính một lần và kiểm tra xong.
            super(customer, cents);

            // Epilogue: mới thao tác với instance.
            this.sourceAmount = amount;
        }

        BigDecimal sourceAmount() {
            return sourceAmount;
        }
    }

    public static void main(String[] args) {
        Invoice invoice = new Invoice("  Lan  ", new BigDecimal("125.30"));
        System.out.println(invoice.customer());    // Lan
        System.out.println(invoice.totalCents());  // 12530
        System.out.println(invoice.sourceAmount()); // 125.30
    }
}
~~~

Ở đây có ba giá trị trung gian:

- **customer** được lấy bằng **strip()**, không phụ thuộc instance.
- **scaled** là BigDecimal sau khi chuyển từ đơn vị tiền sang cent theo giả định **hai chữ số thập phân**.
- **cents** dùng **longValueExact()** để không làm tròn lặng lẽ và không chấp nhận số ngoài phạm vi long.

Nếu đầu vào là **new BigDecimal("1.234")**, phép đổi ra **123.4 cent** không phải số nguyên, nên **longValueExact()** ném **ArithmeticException**. Nếu ứng dụng muốn làm tròn, cần định nghĩa **RoundingMode** theo nghiệp vụ thay vì để thư viện chọn tùy ý. Nếu loại tiền có số chữ số thập phân khác 2, phải thiết kế lại quy tắc scale, không copy nguyên ví dụ.

**Lợi ích:** lớp cha chỉ nhận dữ liệu đã chuẩn hóa, còn trường hợp sai được từ chối trước khi đối tượng lớp cha bị khởi tạo. Đây là ví dụ tính toán trung gian, không phải hướng dẫn đầy đủ về kế toán hoặc mô hình tiền tệ.

## 5. Chuẩn bị nhiều đối số và tránh tính toán trùng

Prologue có thể chứa nhiều câu lệnh độc lập trên **tham số**, **local variables** và các hàm **static**. Ví dụ xây dựng một báo cáo từ danh sách tác vụ:

~~~java
import java.util.List;
import java.util.Objects;

class ReportBase {
    final String title;
    final int rowCount;

    ReportBase(String title, int rowCount) {
        this.title = title;
        this.rowCount = rowCount;
    }
}

final class TaskReport extends ReportBase {
    private final List<String> tasks;

    TaskReport(String rawTitle, List<String> inputTasks) {
        String title = Objects.requireNonNull(rawTitle, "title").strip();
        if (title.isEmpty()) {
            throw new IllegalArgumentException("title rỗng");
        }

        List<String> safeTasks =
                List.copyOf(Objects.requireNonNull(inputTasks, "tasks"));
        if (safeTasks.isEmpty()) {
            throw new IllegalArgumentException("Cần ít nhất một task");
        }
        int count = safeTasks.size();

        super(title, count);
        this.tasks = safeTasks;
    }

    List<String> tasks() {
        return tasks;
    }
}
~~~

**List.copyOf(...)** tạo danh sách không thể chỉnh sửa qua API List và từ chối phần tử null; đây là lựa chọn phù hợp khi muốn tách dữ liệu nội bộ khỏi danh sách mutable do caller đưa vào. Cả **count** lẫn danh sách được tạo **một lần**, tránh lặp phép biến đổi trong hai hoặc ba argument của super.

Không nên đưa mọi phép xử lý nghiệp vụ phức tạp vào constructor. Nếu việc chuẩn bị cần **network I/O, transaction, tài nguyên phải đóng** hoặc nhiều nhánh bất đồng bộ, một **factory/service** thường rõ ràng và dễ kiểm thử hơn. Prologue là chỗ tốt để **kiểm tra và tính toán giá trị thuần túy**, không phải nơi thay thế orchestration nghiệp vụ.

## 6. Tính giá trị trước this(...): ủy quyền constructor cùng lớp

**this(...)** giúp các constructor overload cùng dùng một constructor trung tâm để gán field và thực thi invariant. Trong Java 25, một overload có thể **parse, chuẩn hóa, kiểm tra dữ liệu** trước khi gọi overload khác.

Ví dụ lớp **ConnectionOptions** nhận hai dạng đầu vào: cặp **host/port** hoặc một **URI**:

~~~java
import java.net.URI;
import java.util.Locale;
import java.util.Objects;

public final class ConnectionOptions {
    private final String host;
    private final int port;

    public ConnectionOptions(String host, int port) {
        String validatedHost = Objects.requireNonNull(host, "host").strip();
        if (validatedHost.isEmpty()) {
            throw new IllegalArgumentException("host rỗng");
        }
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("port ngoài khoảng hợp lệ");
        }
        this.host = validatedHost.toLowerCase(Locale.ROOT);
        this.port = port;
    }

    public ConnectionOptions(URI uri) {
        // Prologue của overload: chỉ dùng tham số/local/static.
        Objects.requireNonNull(uri, "uri");
        String scheme = uri.getScheme();
        boolean https = "https".equalsIgnoreCase(scheme);
        boolean http = "http".equalsIgnoreCase(scheme);
        if (!https && !http) {
            throw new IllegalArgumentException("Chỉ hỗ trợ HTTP hoặc HTTPS");
        }

        String parsedHost = uri.getHost();
        if (parsedHost == null || parsedHost.isBlank()) {
            throw new IllegalArgumentException("URI thiếu host");
        }
        int parsedPort = uri.getPort();
        int effectivePort = parsedPort == -1 ? (https ? 443 : 80) : parsedPort;

        // Các biến cục bộ đã tính được truyền tới constructor trung tâm.
        this(parsedHost, effectivePort);
    }

    public String host() {
        return host;
    }

    public int port() {
        return port;
    }
}
~~~

Khi gọi **new ConnectionOptions(URI.create("https://Example.COM/path"))**, constructor URI tính được **parsedHost** và **effectivePort = 443**, sau đó **this(parsedHost, effectivePort)** chạy constructor trung tâm. Kết quả **host()** là **example.com**, **port()** là **443**.

**Chú ý về thiết kế:** ví dụ trên xác minh scheme, host và port để minh họa constructor chaining, nhưng chưa triển khai toàn bộ chính sách URL/IDN, user-info, security hoặc kết nối mạng. Không diễn giải nó như một bộ phân tích URL đầy đủ cho môi trường production.

### Trình tự constructor chaining

~~~mermaid
sequenceDiagram
    participant U as Caller
    participant A as ConnectionOptions(URI)
    participant B as ConnectionOptions(String,int)
    participant O as Object()
    U->>A: new ConnectionOptions(uri)
    A->>A: kiểm tra scheme/host; tính port
    A->>B: this(parsedHost, effectivePort)
    B->>O: super() ngầm
    O-->>B: hoàn tất
    B->>B: kiểm tra và gán host, port
    B-->>A: hoàn tất
    A-->>U: instance
~~~

Prologue trước **this(...)** chạy **trước** constructor được ủy quyền. Phần epilogue của constructor URI, nếu có, chỉ chạy **sau khi** constructor trung tâm đã hoàn thành. Các lời gọi **this(...)** không được tạo chu trình trực tiếp hoặc gián tiếp.

## 7. Trường hợp đặc biệt: record constructor dùng this(...)

**Record** vẫn có quy tắc khởi tạo riêng. Constructor **không canonical** của record phải ủy quyền về constructor canonical bằng **this(...)**; Java 25 cho phép xử lý dữ liệu trước lời gọi đó.

~~~java
import java.math.BigDecimal;
import java.util.Locale;
import java.util.Objects;

record Price(String currency, long cents) {
    Price {
        Objects.requireNonNull(currency, "currency");
        if (currency.length() != 3) {
            throw new IllegalArgumentException("Cần mã tiền ba ký tự");
        }
        if (cents < 0) {
            throw new IllegalArgumentException("cents âm");
        }
    }

    Price(String input) {
        Objects.requireNonNull(input, "input");
        String[] parts = input.strip().split(":", 2);
        if (parts.length != 2) {
            throw new IllegalArgumentException("Định dạng: CUR:amount");
        }

        String code = parts[0].strip().toUpperCase(Locale.ROOT);
        BigDecimal amount = new BigDecimal(parts[1].strip());
        long normalizedCents = amount.movePointRight(2).longValueExact();

        this(code, normalizedCents);
    }
}
~~~

**new Price("usd:12.50")** gọi overload **Price(String)** rồi ủy quyền vào constructor canonical của record, cho ra **Price("USD", 1250)**. Validation canonical tiếp tục là nơi bảo vệ mọi đường khởi tạo record; overload không được bỏ qua invariant.

**Không nhầm hai trường hợp:** phần **Price { ... }** là **compact canonical constructor** của record, **không phải** compact source file. Record canonical constructor không được tự gọi **super(...)** hoặc **this(...)** giống noncanonical constructor; tính toán trước **this(...)** ở đây nằm trong **overload không canonical**.

## 8. Bảng quy tắc: prologue được phép làm gì?

Trong **early construction context** (prologue và các biểu thức trong lời gọi constructor), code bị cấm dùng trực tiếp hoặc gián tiếp **instance đang được khởi tạo**, ngoài ngoại lệ gán sớm field được quy định cụ thể.

| Thao tác trong prologue | Hợp lệ? | Lý do |
| --- | --- | --- |
| Đọc tham số constructor, khai báo biến cục bộ, tính biểu thức. | **Có** | Không đụng vào trạng thái instance hiện tại. |
| Dùng **Objects.requireNonNull**, **Math.multiplyExact**, phương thức static. | **Có** | Không cần current instance. |
| **if** rồi throw khi input không hợp lệ. | **Có** | Có thể fail fast trước super/this. |
| Vòng lặp tính tổng từ dữ liệu tham số. | **Có**, nếu không dùng instance hiện tại. | Dùng local variables để tạo argument. |
| Gọi **this.instanceMethod()**, **instanceMethod()** hoặc dùng **this** như một object. | **Không** | Chưa được phép truy cập instance đang xây dựng. |
| Đọc **this.field**, **field** hoặc **super.field** của instance hiện tại. | **Không** | Không đọc trạng thái instance trước khi constructor tương ứng hoàn tất. |
| Gọi **super.method()** hoặc lấy method reference từ instance. | **Không** | Phụ thuộc current instance/superclass state. |
| Gán sớm một field do chính lớp khai báo, chưa có initializer, bằng phép gán đơn. | **Có điều kiện** | Ngoại lệ của Java 25; xem mục 9. |
| **return;** trong constructor. | **Không** | Constructor body không cho phép return statement. |
| Đặt **super(...)** bên trong **if**, vòng lặp hoặc **try**. | **Không** | Constructor invocation là cấu trúc riêng ở cấp constructor body. |
| Có cả **super(...)** và **this(...)** trong cùng một constructor. | **Không** | Mỗi constructor chỉ có tối đa một invocation tường minh. |

### Ví dụ cố ý sai để đọc thông báo compiler

Đoạn sau **không biên dịch**; hãy lưu riêng khỏi các ví dụ hợp lệ:

~~~java
class Base {
    Base(int code) {}
}

class BadChild extends Base {
    private int cached;

    BadChild(int code) {
        // Sai: đọc một instance field quá sớm.
        int x = cached;

        // Sai: không thể gọi instance method trước super.
        logInput();

        super(code);
    }

    void logInput() {
        System.out.println("Starting");
    }
}
~~~

**Sửa:** dùng **code** hoặc local variable, hoặc một static helper thay cho **cached/logInput()** ở prologue. Những thao tác thật sự cần đọc instance phải dời sang epilogue. **Đừng sửa bằng cách gọi this.logInput()**, vì thêm **this.** không làm instance sẵn sàng sớm hơn.

Một lỗi cú pháp khác:

~~~java
class InvalidShape extends Base {
    InvalidShape(int code) {
        if (code > 0) {
            // Sai: super(...) không được lồng trong if.
            super(code);
        }
    }
}
~~~

Thay bằng **if** chỉ để kiểm tra/throw, sau đó đặt **super(code)** ở cấp thân constructor:

~~~java
class ValidShape extends Base {
    ValidShape(int code) {
        if (code <= 0) {
            throw new IllegalArgumentException("code phải dương");
        }
        super(code);
    }
}
~~~

## 9. Ngoại lệ gán field sớm: hiểu đúng, không lạm dụng

Java 25 còn cho phép **một số phép gán đơn** tới field của chính lớp đang xây dựng **trước super(...)**. Cơ chế này bảo vệ trường hợp constructor cha gọi một phương thức overridable, khiến implementation lớp con bị gọi khi field lớp con chưa được khởi tạo.

Ví dụ sau minh họa trường hợp được Java 25 hỗ trợ:

~~~java
class ParentService {
    ParentService() {
        report();
    }

    void report() {
        System.out.println("ParentService");
    }
}

final class NamedService extends ParentService {
    private final String safeName; // Không khai báo initializer ở field.

    NamedService(String rawName) {
        String normalized =
                java.util.Objects.requireNonNull(rawName, "name").strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Tên rỗng");
        }

        // Ngoại lệ hợp lệ: phép gán đơn vào field do NamedService khai báo.
        this.safeName = normalized;
        super();
    }

    @Override
    void report() {
        System.out.println(safeName);
    }
}
~~~

Khi tạo **new NamedService(" Lan ")**, constructor cha gọi **report()**; giá trị **safeName** đã được gán nên in **Lan**, không phải giá trị mặc định **null**.

**Không hiểu sai rằng có thể dùng mọi field như bình thường trước super:**

- Chỉ một số **assignment tới field của chính lớp** được phép; không được đọc giá trị trước đó.
- Field được gán sớm **không được có initializer ngay trong khai báo field** hoặc cơ chế khởi tạo xung đột theo quy tắc ngôn ngữ.
- **this.field = value** ở đây là ngoại lệ cụ thể đối với cách dùng **this**, không cho phép **this.method()**, truyền **this** làm argument, **this.field++**, **this.field += ...** hoặc truy cập field của super.
- Với **final field** và constructor chaining, phải thỏa mọi quy tắc definite assignment; không gán lại cùng field sau khi gọi constructor khác.

Mục tiêu của bài này vẫn là **tính giá trị trung gian để truyền vào super/this**; gán field sớm chỉ là khả năng có liên quan. **Constructor cha gọi phương thức overridable vẫn là một thiết kế nhiều rủi ro**; nếu kiểm soát được mã nguồn cha, hãy ưu tiên không gọi method overridable trong constructor thay vì dựa hoàn toàn vào workaround.

## 10. Thứ tự đánh giá và tác dụng phụ

Prologue chạy theo thứ tự câu lệnh Java bình thường. Với **super(a, b)** hoặc **this(a, b)**, các đối số được đánh giá **từ trái sang phải** trước khi constructor đích bắt đầu. Nếu prologue hoặc việc đánh giá một argument ném exception, lời gọi constructor đích **không** diễn ra.

Ví dụ:

~~~java
class ParentCall {
    ParentCall(String name, int size) {
        System.out.println("PARENT: " + name + "/" + size);
    }
}

class DerivedCall extends ParentCall {
    DerivedCall(String name, int size) {
        System.out.println("VALIDATING");
        String clean = java.util.Objects.requireNonNull(name).strip();
        if (clean.isEmpty() || size < 0) {
            throw new IllegalArgumentException("Tham số không hợp lệ");
        }
        int adjusted = Math.addExact(size, 1);
        super(clean, adjusted);
        System.out.println("CHILD");
    }
}
~~~

Với **new DerivedCall("Lan", 2)**, thứ tự log là **VALIDATING → PARENT: Lan/3 → CHILD**. Với **new DerivedCall(" ", 2)**, chỉ có **VALIDATING**, tiếp theo là exception; constructor cha không được gọi. Với **size = Integer.MAX_VALUE**, **Math.addExact** ném **ArithmeticException** trước super.

Tuy nhiên, **prologue có thể tự gây tác dụng phụ** (log, thay đổi static counter, mở tài nguyên). Nếu xảy ra exception, các tác dụng phụ đó không tự rollback. Nguyên tắc tốt là giữ prologue **ngắn, dễ dự đoán**, ưu tiên biến đổi thuần túy; không mở file, tạo thread hoặc kết nối mạng chỉ để tính constructor arguments.

**Không có bảo đảm tự động về atomicity hay rollback.** Kiểm tra input trước super giúp tránh những tác dụng phụ **bên trong constructor cha**, nhưng không phục hồi dữ liệu bên ngoài đã bị thay đổi bởi chính prologue.

## 11. Biên dịch bằng Java 25 và kiểm tra tương thích

Tính năng **Flexible Constructor Bodies** đã **final từ JDK 25**, không cần **--enable-preview**. Nếu file có câu lệnh trước super/this mà bị báo lỗi ở mức ngôn ngữ thấp, trước tiên kiểm tra phiên bản compiler và target release.

Ví dụ trong terminal:

~~~bash
java --version
javac --version

# Nếu đang đứng ở thư mục chứa InvoiceDemo.java:
javac --release 25 InvoiceDemo.java
java InvoiceDemo
~~~

**--release 25** đòi hỏi compiler hỗ trợ Java 25 và quy định tập API/bytecode của Java 25. Nếu dùng **--release 21**, code có prologue trước super sẽ không được chấp nhận theo ngôn ngữ Java 21. **JDK chạy ứng dụng** phải tương thích với bytecode được biên dịch; class file Java 25 có **major version 69**.

Nếu Gradle là công cụ build, nên dùng **Java Toolchains** và release 25, với Gradle wrapper phiên bản hỗ trợ Java 25 (Gradle **9.1+** cho Java 25 theo compatibility matrix):

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(25)
}
~~~

Nếu dùng Maven, thiết lập compiler release trong **pom.xml** và bảo đảm compiler JDK 25 được chọn bằng Maven launcher hoặc Maven Toolchains:

~~~xml
<properties>
    <maven.compiler.release>25</maven.compiler.release>
</properties>
~~~

**maven.compiler.release** không tự cài JDK 25. Với CI hoặc IDE, kiểm tra compiler thực được gọi, SDK/language level, Maven/Gradle JVM, toolchain, Run JDK và plugin hỗ trợ cú pháp Java 25. **Build chạy được bằng JDK 25** và **build có compiler release 25** là hai điều cần xác nhận riêng.

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Compiler báo phải đặt super/this đầu tiên | Compiler hoặc **--release** đang ở Java trước 25. | **javac --version**, toolchain, language level. |
| Không thể tham chiếu **this/super** trước constructor | Code đọc hoặc gọi member của current instance. | Đưa thao tác sang epilogue, hoặc dùng local/static. |
| **cannot assign initialized field** | Gán sớm field đã có initializer. | Xem quy tắc field assignment, dời sau super. |
| **recursive constructor invocation** | **this(...)** tạo vòng lặp. | Kiểm tra toàn bộ chuỗi overload. |
| Không có constructor cha thích hợp | Lời gọi super sai chữ ký hoặc constructor không truy cập được. | Kiểm tra overload/accessibility. |
| **UnsupportedClassVersionError** | Runtime cũ hơn class file Java 25. | Dùng JVM hỗ trợ Java 25 hoặc compile target thấp hơn nếu mã tương thích. |
| Terminal compile được, IDE gạch lỗi | IDE/parser/plugin chưa hỗ trợ Java 25. | Cập nhật IDE, SDK, compiler và reimport build. |

### Không dùng preview flags của các JEP cũ

Những bài viết lịch sử từng gọi tính năng này là **Statements before super(...)** hoặc **Flexible Constructor Bodies (Preview)**. Đó là các giai đoạn đề xuất trước khi JEP 513 hoàn thiện. Trong tài liệu Java 25, dùng cú pháp chính thức và **không** bật **--enable-preview** chỉ vì muốn đặt validation trước super/this.

## 12. Kiểm thử các bất biến thay vì chỉ kiểm tra compile

Một constructor hợp lệ về cú pháp vẫn có thể gây lỗi logic. Với Java 25, nên kiểm thử:

1. **Happy path:** chuẩn hóa tham số và các giá trị truyền vào super/this chính xác.
2. **Null/blank/negative:** exception đúng loại và thông điệp hữu ích trước khi tác dụng phụ của constructor đích xảy ra.
3. **Overflow/precision:** dùng **Math.addExact**, **Math.multiplyExact**, **BigDecimal.longValueExact** khi cần tính chính xác.
4. **Constructor chaining:** mọi overload bảo toàn invariant và không tạo chu trình.
5. **Thứ tự initialization:** nếu có field assignment sớm, giá trị không bị initializer khác ghi đè.
6. **Tương thích công cụ:** javac, test runner, IDE và CI đều dùng Java 25.

Ví dụ JUnit 5 kiểm chứng **SquareArea** (từ mục 3):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SquareAreaTest {
    @Test
    void computesAreaBeforeCallingParent() {
        assertEquals(144L, new SquareArea(12).squareUnits());
    }

    @Test
    void rejectsInvalidSide() {
        assertThrows(IllegalArgumentException.class,
                () -> new SquareArea(0));
    }

    @Test
    void rejectsLongOverflow() {
        assertThrows(ArithmeticException.class,
                () -> new SquareArea(Long.MAX_VALUE));
    }
}
~~~

Ví dụ trên không phụ thuộc JUnit hỗ trợ reflection trên constructor private: các constructor và lớp trong cùng package được truy cập theo package-level trong test. Khi chuyển code vào production, điều chỉnh visibility theo API thực tế.

### Đo thứ tự với phép thử có kiểm soát

Nếu cần chứng minh **constructor lớp cha không chạy khi prologue fail**, thiết kế một constructor cha ghi vào danh sách sự kiện hoặc bộ đếm do test kiểm soát. Tránh chỉ dựa vào stdout hoặc snapshot đồ thị đối tượng sau khi constructor ném exception. Ngoài ra cần kiểm tra tác dụng phụ thực sự của cả prologue nếu nó có thao tác ngoài bộ nhớ.

### Kiểm tra thủ công không được coi là QA tự động

Các đoạn mã trong bài là ví dụ hướng dẫn để chạy bằng JDK 25; khi đưa vào dự án thật, hãy chạy build/test của môi trường và kiểm tra kết quả thực. Bài học tập trung vào cách viết và cách suy luận; nó không đồng nghĩa mọi cấu hình IDE, plugin hoặc build cụ thể đã được thực thi trong môi trường học.

## 13. Các lựa chọn thiết kế thay thế: khi nào không nên dùng prologue?

**Flexible Constructor Bodies** không làm mọi static helper hoặc factory trở nên lỗi thời. Chọn công cụ theo yêu cầu:

| Tình huống | Gợi ý | Lý do |
| --- | --- | --- |
| Kiểm tra vài tham số và tính 1–3 local values trước super. | **Constructor prologue** | Ngắn gọn, dễ hiểu, fail fast. |
| Nhiều overload cần một bộ quy tắc invariant. | **this(...)** vào constructor trung tâm | Tránh logic bị nhân bản. |
| Quy tắc chuẩn hóa được nhiều nơi tái dùng. | Hàm **static** hoặc utility riêng | Tách trách nhiệm và kiểm thử độc lập. |
| Xử lý có I/O, HTTP, database, transaction. | **Factory/service** ngoài constructor | Quản lý lỗi, timeout, tài nguyên và side effects rõ ràng. |
| Cần hỗ trợ Java 21 cùng một source tree. | Giữ cú pháp Java 21 hoặc build/source riêng | Prologue Java 25 không compile với release 21. |
| Dữ liệu là value bất biến, không cần kế thừa. | **Record** hoặc class bất biến | Không tạo hierarchy chỉ để dùng super. |

### Tránh những anti-pattern mới

- **Giấu công việc nặng** trong prologue: ví dụ gọi mạng để lấy dữ liệu rồi mới super, khiến constructor khó đoán và khó retry.
- **Dùng biến static mutable** để truyền trạng thái giữa constructor overload thay vì local variables, gây race condition.
- **Đọc instance trước khi hoàn tất khởi tạo** thông qua instance method, lambda capture this hoặc nested inner object.
- **Tính lại giá trị** trong nhiều đối số super/this, đặc biệt nếu hàm có side effect hoặc tạo số ngẫu nhiên.
- **Bắt Exception chung rồi tiếp tục khởi tạo** với giá trị mặc định không an toàn, che lỗi input.
- **Lẫn lộn validation và side effects:** gọi constructor cha có thể kích hoạt I/O hoặc logic khác; nên đảm bảo input đúng trước khi vào đó nếu có thể.

## 14. Bài tập thực hành có tiêu chí đánh giá

### Bài tập A — chuẩn hóa tham số trước super

Tạo **NormalizedAccount extends BaseAccount**, lớp cha nhận **String accountId** và **long limit**. Lớp con nhận **rawId**, **baseLimit**, **bonusLimit**. Trong prologue:

1. **strip()** accountId và từ chối chuỗi rỗng;
2. dùng **Math.addExact** để tính total limit;
3. kiểm tra total limit không âm;
4. gọi **super(normalizedId, totalLimit)**.

**Đạt:** các input hợp lệ cho giá trị đúng; chuỗi rỗng/overflow bị từ chối **trước khi** constructor cha được chạy.

### Bài tập B — hai constructor và this(...)

Tạo **ServiceEndpoint** nhận **String host, int port** hoặc **URI uri**. Constructor URI phải kiểm tra scheme, lấy host, suy ra port mặc định, rồi **this(host, port)**. Constructor trung tâm gán hai field sau khi tự kiểm tra invariant.

**Đạt:** URL HTTP và HTTPS đi đúng port; thiếu host hoặc port không hợp lệ bị từ chối; không có logic gán field bị nhân bản trong hai overload.

### Bài tập C — record với constructor phụ

Tạo **record Quantity(String unit, long amount)**, thêm constructor nhận **String input** có dạng **UNIT:COUNT**. Trong prologue, tách chuỗi, chuẩn hóa unit và parse số, rồi **this(unit, count)**. Canonical constructor phải kiểm tra invariant.

**Đạt:** mọi đường khởi tạo record đều qua validation canonical; input sai định dạng ném exception.

### Bài tập D — tìm và sửa lỗi early construction context

Viết một constructor cố ý chứa **this.print()** hoặc đọc **this.cached** trước super. Ghi thông báo lỗi javac 25 rồi sửa bằng tính toán từ tham số/local variables. Không sửa bằng cách thay **this.method()** thành **method()** vì vẫn gọi instance method.

**Đạt:** hiểu lý do compile error, biết vị trí nào có thể dời sang epilogue.

### Bài tập E — gán sớm field một cách an toàn

Dựa trên ví dụ **NamedService** ở mục 9, thử gán **final safeName** trước super và quan sát phương thức overridden được gọi bởi lớp cha. Sau đó thử thêm initializer ngay ở khai báo field để thấy compiler không cho phép gán sớm theo cùng cách. Cuối cùng đề xuất cách sửa kiến trúc **không gọi overridable method trong constructor cha**.

**Đạt:** phân biệt được ngoại lệ field assignment với quyền đọc/call instance và hiểu vì sao ngoại lệ không nên bị lạm dụng.

### Câu hỏi tự kiểm tra

1. Prologue khác epilogue ở điểm nào? Khi nào constructor có super() ngầm?
2. Vì sao **long area = Math.multiplyExact(side, side)** trước super có ích hơn phép nhân **side * side**?
3. Trong constructor có **this(...)**, khi nào constructor được ủy quyền bắt đầu chạy?
4. Có được đưa **super(...)** vào nhánh if khi điều kiện đúng không? Vì sao?
5. Vì sao **this.field = value** có thể hợp lệ trước super trong trường hợp chặt chẽ, còn **this.field++** không hợp lệ?
6. Nếu prologue ném exception, constructor cha đã chạy chưa? Những tác dụng phụ nào có thể đã xảy ra?
7. Có cần **--enable-preview** khi compile Flexible Constructor Bodies bằng JDK 25?
8. Tại sao một file Java 25 compile được trên máy cá nhân nhưng Gradle/IDE/CI báo lỗi cú pháp cũ?
9. Trong record, constructor phụ cần làm gì để gọi canonical constructor đúng?
10. Khi nào nên chọn static helper hoặc factory thay vì kéo quá nhiều logic vào constructor prologue?

## 15. Tài liệu chính thức và cách cập nhật kiến thức

Các nguồn phù hợp để đối chiếu với Java 25:

- [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513): tài liệu đề xuất đã được hoàn thiện trong Java 25.
- [Oracle Java 25 — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html): ví dụ prologue, early construction context, gán field và record.
- [Java Language Specification SE 25 §8.8.7 — Constructor Body](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7): ngữ pháp thân constructor, prologue/epilogue và giới hạn.
- [JLS SE 25 §8.8.7.1 — Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7.1): quy tắc super/this và constructor chaining.
- [JLS SE 25 §16 — Definite Assignment](https://docs.oracle.com/javase/specs/jls/se25/html/jls-16.html): ràng buộc gán biến và field.
- [Gradle Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): phiên bản Gradle hỗ trợ JDK 25.

**Không sử dụng tài liệu preview của Java 22–24 làm quy tắc cuối cùng**; chỉ coi chúng là lịch sử phát triển. Khi công cụ hoặc IDE báo lỗi, so với **JLS SE 25** và **JEP 513** thay vì tự gắn preview flags hay hạ mục tiêu ngôn ngữ. Khi phát triển dự án yêu cầu hỗ trợ runtime trước Java 25, phải chọn source/API tương thích phù hợp.

**Kết quả cần nộp:** hai ví dụ có thể chạy dùng **super(...)** và **this(...)** với nhiều biến trung gian; ít nhất một phép kiểm tra fail fast và một test overflow; bảng quy tắc early construction context; một bài test constructor chaining; và checklist compiler/IDE/CI Java 25. Mục tiêu là tính toán đúng, chuẩn hóa rõ ràng, giữ invariant và hiểu thứ tự khởi tạo, chứ không chỉ đưa **super(...)** xuống vài dòng mà không có giá trị thiết kế.
