# Tái sử dụng bằng kết hợp và bằng kế thừa trong Java OOP

Trong một ứng dụng Java, nhiều chức năng có thể dùng chung mã nguồn: cùng định dạng báo cáo, gửi thông báo, kiểm tra dữ liệu, ghi log hoặc lưu kết quả. Có hai hướng OOP thường gặp để tái sử dụng:

- **Kế thừa (inheritance):** tạo một *lớp con* dựa trên *lớp cha*, dùng lại phần hành vi/trạng thái được kế thừa và có thể ghi đè những điểm được phép mở rộng. Quan hệ cần có ý nghĩa **is-a**: “đối tượng con là một loại đối tượng cha”.
- **Kết hợp (composition):** một đối tượng **có hoặc sử dụng** các đối tượng khác để làm việc và **ủy quyền (delegation)** một phần hành vi cho chúng. Quan hệ thường được diễn đạt **has-a / uses-a**. Tái sử dụng đến từ việc lắp ghép những thành phần có trách nhiệm rõ ràng, không bắt buộc các thành phần cùng cây kế thừa.

Câu hỏi quan trọng không phải “cách nào ít dòng code hơn”, mà là: **quan hệ giữa các đối tượng có đúng về mặt nghiệp vụ không, phần nào cần thay đổi độc lập, và code sử dụng sẽ chịu ảnh hưởng gì khi yêu cầu phát triển?**

## 1. Nhìn từ ví dụ đời thường: is-a và has-a

Một `ElectricCar` là một loại `Car`. Nếu tất cả những hành vi mà `Car` cam kết đều có nghĩa với `ElectricCar`, quan hệ kế thừa có thể phù hợp:

~~~java
class Car {
    void drive() {
        System.out.println("Xe đang chạy");
    }
}

class ElectricCar extends Car {
    void charge() {
        System.out.println("Đang sạc");
    }
}
~~~

Nhưng một chiếc xe **có pin**; xe **không phải là pin**. Viết `class ElectricCar extends Battery` chỉ để dùng phương thức `charge` là sai về mô hình.

Cách kết hợp đúng hơn:

~~~java
class Battery {
    void charge() {
        System.out.println("Pin đang sạc");
    }
}

class ElectricCar {
    private final Battery battery;

    ElectricCar(Battery battery) {
        this.battery = battery;
    }

    void chargeCar() {
        battery.charge(); // Ủy quyền cho thành phần.
    }
}
~~~

Ở đây `ElectricCar` có một `Battery`. Việc dùng `battery.charge()` là **delegation**, một kỹ thuật rất phổ biến khi tái sử dụng bằng kết hợp.

| Câu hỏi | Kế thừa | Kết hợp |
| --- | --- | --- |
| Quan hệ cốt lõi | “A **là một loại** B” | “A **có/dùng** B” |
| Java thường viết | `class A extends B` | Field tham chiếu `B b`, gọi `b.doWork()` |
| Nguồn hành vi được dùng lại | Phương thức/trạng thái được kế thừa | Phương thức của đối tượng cộng tác |
| Có cần chung superclass? | Có quan hệ lớp cha–lớp con | Không |
| Thay đổi hành vi | Override các điểm mở rộng đã thiết kế | Thay đối tượng cộng tác hoặc cấu hình |
| Mức độ ràng buộc | Lớp con gắn với hợp đồng và một phần chi tiết lớp cha | Bên sử dụng có thể chỉ phụ thuộc interface của thành phần |
| Rủi ro điển hình | Quan hệ is-a giả tạo, lớp cha dễ ảnh hưởng lớp con | Quá nhiều đối tượng trung gian hoặc ủy quyền vô nghĩa |

**Lưu ý thuật ngữ:** trong lập trình, “ưu tiên composition” đôi khi được dùng rộng để chỉ *thiết kế ghép các đối tượng qua field và delegation*. Trong UML chặt chẽ, **composition** với hình thoi đặc còn thể hiện quan hệ sở hữu vòng đời mạnh (*whole–part*). Một dependency được **truyền từ ngoài vào constructor** có thể là association/aggregation thay vì composition sở hữu vòng đời theo nghĩa UML. Bài này sử dụng “kết hợp” theo nghĩa thiết kế OOP rộng, và sẽ không gán hình thoi đặc cho mọi tham chiếu đối tượng.

## 2. Tình huống: xuất và phân phối báo cáo

Giả sử hệ thống cần:

1. Tạo nội dung báo cáo doanh thu.
2. Định dạng báo cáo thành **văn bản thuần** hoặc **Markdown**.
3. Xuất báo cáo ra **console** hoặc **kho lưu trữ trong bộ nhớ**.

Có hai cách tái sử dụng hợp lý nhưng giải quyết các mức độ thay đổi khác nhau.

### Cách A: kế thừa để chia sẻ khung tạo báo cáo

Một `AbstractReport` chứa tiêu đề và khung `render()`. Từng lớp báo cáo cụ thể chỉ viết phần thân:

~~~java
abstract class AbstractReport {
    private final String title;

    protected AbstractReport(String title) {
        this.title = title;
    }

    public final String render() {
        return title + "\n" + buildBody();
    }

    protected abstract String buildBody();
}

class SalesReport extends AbstractReport {
    SalesReport(String title) {
        super(title);
    }

    @Override
    protected String buildBody() {
        return "Tổng doanh thu: 1500000 VND";
    }
}
~~~

`SalesReport extends AbstractReport` hợp lý vì **báo cáo bán hàng là một loại báo cáo**. Phần khung kết xuất được tái sử dụng. `render()` là `final` để lớp con không tự bỏ qua khung chung; điểm mở rộng có chủ đích là `buildBody()`.

Hạn chế xuất hiện nếu mỗi lớp con lại phải quyết định **cả loại nội dung, cách định dạng và kênh xuất**. Một cây lớp `SalesMarkdownConsoleReport`, `SalesPlainTextConsoleReport`, `SalesMarkdownArchiveReport`... dễ phình to khi những lựa chọn này thay đổi độc lập.

### Cách B: kết hợp để lắp ghép những trách nhiệm độc lập

Tách ba vai trò:

- `ReportData`: dữ liệu báo cáo cần trình bày.
- `Formatter`: biến báo cáo thành chuỗi hiển thị.
- `Destination`: nhận chuỗi và đưa tới nơi cần xuất.
- `ReportPublisher`: **sở hữu quy trình phối hợp**, gọi các thành phần đúng thứ tự.

~~~mermaid
flowchart LR
    R["ReportData"] --> P["ReportPublisher"]
    F["Formatter\nPlainText hoặc Markdown"] --> P
    P --> D["Destination\nConsole hoặc Archive"]
~~~

`ReportPublisher` không phải **một loại** formatter, cũng không phải **một loại** destination. Nó **sử dụng** cả hai để hoàn thành mục tiêu. Đây là ví dụ tự nhiên của kết hợp.

## 3. Mã Java hoàn chỉnh: so sánh hai cách trong cùng chương trình

Lưu thành **`ReuseComparisonDemo.java`**, chạy với Java **11 trở lên**, không cần thư viện bên ngoài.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ReuseComparisonDemo {

    private static String requireText(String value, String field) {
        String checked = Objects.requireNonNull(value, field).trim();
        if (checked.isEmpty()) {
            throw new IllegalArgumentException(field + " không được rỗng");
        }
        return checked;
    }

    // ----- PHẦN 1: TÁI SỬ DỤNG BẰNG KẾ THỪA -----

    static abstract class AbstractReport {
        private final String title;

        protected AbstractReport(String title) {
            this.title = requireText(title, "title");
        }

        public final String render() {
            return title + "\n" + buildBody();
        }

        // Điểm mở rộng: lớp con cung cấp phần thân báo cáo.
        protected abstract String buildBody();
    }

    static final class SalesReport extends AbstractReport {
        private final BigDecimal revenue;

        SalesReport(String title, BigDecimal revenue) {
            super(title);
            this.revenue = Objects.requireNonNull(revenue, "revenue");
            if (revenue.signum() < 0) {
                throw new IllegalArgumentException(
                        "Doanh thu không được âm");
            }
        }

        @Override
        protected String buildBody() {
            return "Tổng doanh thu: "
                    + revenue.toPlainString() + " VND";
        }
    }

    // ----- PHẦN 2: TÁI SỬ DỤNG BẰNG KẾT HỢP -----

    static final class ReportData {
        private final String title;
        private final String body;

        ReportData(String title, String body) {
            this.title = requireText(title, "title");
            this.body = requireText(body, "body");
        }

        String getTitle() {
            return title;
        }

        String getBody() {
            return body;
        }
    }

    interface Formatter {
        String format(ReportData report);
    }

    static final class PlainTextFormatter implements Formatter {
        @Override
        public String format(ReportData report) {
            Objects.requireNonNull(report, "report");
            return report.getTitle() + "\n" + report.getBody();
        }
    }

    static final class MarkdownFormatter implements Formatter {
        @Override
        public String format(ReportData report) {
            Objects.requireNonNull(report, "report");
            return "# " + report.getTitle() + "\n\n"
                    + report.getBody();
        }
    }

    interface Destination {
        void deliver(String formattedReport);
    }

    static final class ConsoleDestination implements Destination {
        @Override
        public void deliver(String formattedReport) {
            System.out.println(formattedReport);
        }
    }

    static final class MemoryArchive implements Destination {
        private final List<String> stored = new ArrayList<>();

        @Override
        public void deliver(String formattedReport) {
            stored.add(Objects.requireNonNull(
                    formattedReport, "formattedReport"));
        }

        List<String> readAll() {
            return List.copyOf(stored);
        }
    }

    // Quy trình chung chỉ biết các vai trò, không biết lớp cụ thể.
    static final class ReportPublisher {
        private final Formatter formatter;
        private final Destination destination;

        ReportPublisher(Formatter formatter, Destination destination) {
            this.formatter = Objects.requireNonNull(
                    formatter, "formatter");
            this.destination = Objects.requireNonNull(
                    destination, "destination");
        }

        void publish(ReportData report) {
            Objects.requireNonNull(report, "report");
            String rendered = Objects.requireNonNull(
                    formatter.format(report), "rendered");
            destination.deliver(rendered);
        }
    }

    public static void main(String[] args) {
        // Kế thừa: dùng một lớp con thay cho lớp cha trừu tượng.
        AbstractReport inherited = new SalesReport(
                "Doanh thu tháng", new BigDecimal("1500000"));

        System.out.println("KẾ THỪA:");
        System.out.println(inherited.render());

        // Kết hợp: lắp Formatter và Destination khác nhau.
        ReportData report = new ReportData(
                "Doanh thu tháng",
                "Tổng doanh thu: 1500000 VND");

        ReportPublisher consolePublisher = new ReportPublisher(
                new MarkdownFormatter(), new ConsoleDestination());

        System.out.println("KẾT HỢP:");
        consolePublisher.publish(report);

        MemoryArchive archive = new MemoryArchive();
        ReportPublisher archivePublisher = new ReportPublisher(
                new PlainTextFormatter(), archive);

        archivePublisher.publish(report);
        System.out.println("Đã lưu: " + archive.readAll().size()
                + " báo cáo");
        System.out.println("Nội dung lưu:");
        System.out.println(archive.readAll().get(0));
    }
}
~~~

Chạy:

~~~bash
javac ReuseComparisonDemo.java
java ReuseComparisonDemo
~~~

Kết quả:

~~~text
KẾ THỪA:
Doanh thu tháng
Tổng doanh thu: 1500000 VND
KẾT HỢP:
# Doanh thu tháng

Tổng doanh thu: 1500000 VND
Đã lưu: 1 báo cáo
Nội dung lưu:
Doanh thu tháng
Tổng doanh thu: 1500000 VND
~~~

Trong ví dụ này, `MemoryArchive` **chỉ lưu trong RAM**; không phải lưu trữ bền vững. `ConsoleDestination` chỉ in ra console; chưa gửi mạng hay tạo file. Chúng đủ để làm rõ **phần mã nào được dùng lại** mà không đưa vào các phụ thuộc ngoài bài học.

### Chính xác thì mã được tái sử dụng ở đâu?

**Phương án kế thừa:**

~~~java
AbstractReport report = new SalesReport(...);
String output = report.render();
~~~

`SalesReport` **kế thừa** implementation `render()` từ `AbstractReport`. Nó chỉ override `buildBody()`, và lời gọi từ `render()` được dispatch tới subclass đang chạy.

**Phương án kết hợp:**

~~~java
ReportPublisher publisher =
        new ReportPublisher(new MarkdownFormatter(),
                            new ConsoleDestination());
publisher.publish(reportData);
~~~

`ReportPublisher` **không kế thừa** `MarkdownFormatter` hoặc `ConsoleDestination`. Nó giữ **tham chiếu** tới các đối tượng cộng tác. Code trong `publish()` được tái sử dụng cho mọi cặp formatter/destination tuân thủ hai interface.

Đổi mục tiêu sử dụng mà không sửa `ReportPublisher`:

~~~java
new ReportPublisher(
        new PlainTextFormatter(), new ConsoleDestination());

new ReportPublisher(
        new MarkdownFormatter(), new MemoryArchive());
~~~

`ReportPublisher` chạy cùng thuật toán “định dạng rồi xuất”, còn những phần phụ trách chi tiết có thể được thay độc lập.

## 4. Sơ đồ UML: nhìn rõ loại quan hệ

### Kế thừa: quan hệ giữa các kiểu

~~~mermaid
classDiagram
    class AbstractReport {
        <<abstract>>
        -title String
        +render() String
        #buildBody() String
    }
    class SalesReport {
        -revenue BigDecimal
        #buildBody() String
    }
    AbstractReport <|-- SalesReport
~~~

Tam giác rỗng hướng tới lớp cha biểu thị **`extends`**. Lớp con trở thành một kiểu con của lớp cha; `AbstractReport report = new SalesReport(...)` là phép gán an toàn.

### Kết hợp: quan hệ sử dụng các đối tượng cộng tác

~~~mermaid
classDiagram
    class ReportPublisher {
        -formatter Formatter
        -destination Destination
        +publish(ReportData) void
    }
    class Formatter {
        <<interface>>
        +format(ReportData) String
    }
    class Destination {
        <<interface>>
        +deliver(String) void
    }
    class PlainTextFormatter
    class MarkdownFormatter
    class ConsoleDestination
    class MemoryArchive
    ReportPublisher --> Formatter : uses
    ReportPublisher --> Destination : uses
    Formatter <|.. PlainTextFormatter
    Formatter <|.. MarkdownFormatter
    Destination <|.. ConsoleDestination
    Destination <|.. MemoryArchive
~~~

`ReportPublisher` không phải subtype của `Formatter` hoặc `Destination`. Vì các đối tượng được **truyền vào từ bên ngoài** và có thể được chia sẻ, sơ đồ dùng quan hệ tham chiếu/dependency, **không tự giả định** vòng đời thành phần hoàn toàn thuộc về `ReportPublisher`.

Nếu `ReportPublisher` thật sự tạo và sở hữu một thành phần riêng, quản lý vòng đời của nó theo quy tắc “whole–part”, có thể cân nhắc dùng quan hệ composition mạnh hơn ở mức mô hình UML. Việc một class có field tham chiếu **chưa đủ** để kết luận quan hệ vòng đời đó.

## 5. Khác biệt quan trọng: dùng lại implementation hay lắp ghép hành vi

**Kế thừa để dùng lại implementation** có lợi khi các loại đối tượng thực sự cùng bản chất và chia sẻ được một cách triển khai ổn định.

Trong ví dụ, mọi `AbstractReport` đều có tiêu đề và hành vi `render()`. Nếu cần thêm kiểm tra chung ở `render()`, lớp cha có thể thay đổi một chỗ cho các subclass.

Nhưng sự phụ thuộc cũng sâu hơn:

- Subclass phải tuân theo cấu trúc và hợp đồng của superclass.
- Khi lớp cha thay đổi protected API hoặc giả định nội bộ, các lớp con có thể bị ảnh hưởng.
- Java không cho một class `extends` nhiều class trực tiếp, nên không thể kế thừa độc lập nhiều “nhánh chức năng” qua nhiều superclass.
- Việc subclass override một hook có thể phá invariant hoặc tiền/hậu điều kiện mà superclass kỳ vọng.

**Kết hợp để dùng lại hành vi** phù hợp khi các khả năng có thể thay độc lập.

Ví dụ, phần định dạng và nơi lưu trữ **không phải cùng một loại** và thay đổi ở hai chiều khác nhau:

| | ConsoleDestination | MemoryArchive |
| --- | --- | --- |
| PlainTextFormatter | Văn bản thuần ra console | Văn bản thuần vào archive |
| MarkdownFormatter | Markdown ra console | Markdown vào archive |

Ta chỉ cần **hai formatter, hai destination và một publisher** để lắp bốn kết hợp. Nếu ép “format + destination” vào mỗi subclass cụ thể, số biến thể lớp có thể tăng nhanh khi bổ sung lựa chọn mới.

Tuy nhiên, **không phải cứ kết hợp là ít lớp hơn**. Nó có thể tạo nhiều interface/adapter và các lời gọi ủy quyền. Lợi ích là tách đúng **những chiều thay đổi độc lập** để tránh gắn chúng vào một cây kế thừa cứng nhắc.

## 6. “Composition over inheritance” có phải lúc nào cũng đúng?

Câu “**ưu tiên kết hợp hơn kế thừa**” là một **nguyên tắc định hướng thiết kế**, không phải lệnh cấm `extends`.

Nên cân nhắc **kế thừa** khi:

- Quan hệ *is-a* thực sự đúng: `SalesReport` là một `AbstractReport`.
- Lớp cha cung cấp một hợp đồng nhất quán và các điểm mở rộng được thiết kế rõ.
- Có phần hành vi/trạng thái chung **ổn định** và được chuyên biệt hóa hợp lệ.
- Một object lớp con có thể **thay thế** object lớp cha trong mọi tình huống phù hợp mà không gây ngạc nhiên về hành vi.

Nên cân nhắc **kết hợp** khi:

- Các khả năng cần phối hợp nhưng không phải “một loại của nhau”.
- Có nhiều chiều thay đổi độc lập: định dạng, nguồn dữ liệu, nơi xuất, cách retry.
- Cần dễ thay thành phần, dễ test bằng fake, dễ inject phụ thuộc.
- Muốn tránh subclass phải biết quá nhiều chi tiết protected/internal của superclass.
- Một nhu cầu chỉ là **dùng chức năng** từ đối tượng khác, không có quan hệ is-a hợp lý.

Một câu tự kiểm tra rất hiệu quả:

> **“Nếu xóa mọi dòng code trùng nhau, liệu A vẫn thực sự là một loại B không?”**

Nếu câu trả lời là không, chỉ có ý định tái sử dụng vài phương thức, **kết hợp/ủy quyền** thường phù hợp hơn kế thừa.

## 7. Quan hệ is-a và nguyên tắc thay thế Liskov

Một lớp con không được phép chỉ “trông giống” lớp cha về mặt cú pháp. Nó phải giữ những cam kết mà phần mã sử dụng lớp cha dựa vào.

Ví dụ thiết kế có vấn đề:

~~~java
class Bird {
    void fly() {
        System.out.println("Bay");
    }
}

class Penguin extends Bird {
    @Override
    void fly() {
        throw new UnsupportedOperationException("Không biết bay");
    }
}
~~~

Một hàm nhận `Bird` và tin rằng `fly()` thực hiện được sẽ gặp lỗi với `Penguin`. Quan hệ danh từ “chim cánh cụt là chim” đúng, nhưng **hợp đồng lớp Bird ở đây sai với các loại chim không bay**.

Thiết kế tốt hơn:

~~~java
interface Flyable {
    void fly();
}

abstract class Bird {
    abstract void move();
}

class Sparrow extends Bird implements Flyable {
    @Override
    void move() {
        System.out.println("Chim sẻ di chuyển");
    }

    @Override
    public void fly() {
        System.out.println("Chim sẻ bay");
    }
}

class Penguin extends Bird {
    @Override
    void move() {
        System.out.println("Chim cánh cụt đi hoặc bơi");
    }
}
~~~

Tách **bản chất chung** và **năng lực tùy chọn** giúp tránh biến một phương thức thành lỗi runtime trong subtype. Đây là tinh thần của **Liskov Substitution Principle (LSP)**: code dùng lớp cha không bị phá vỡ kỳ vọng hợp lệ khi nhận đối tượng lớp con.

Đối với thiết kế kết hợp, LSP cũng có ý nghĩa: một `Destination` thay thế khác phải đáp ứng hợp đồng `deliver(...)` đã được client kỳ vọng, chẳng hạn không tự ý sửa báo cáo hay nói thành công khi chưa thực hiện nếu hợp đồng cấm.

## 8. Đổi hành vi tại lúc chạy bằng kết hợp

Ví dụ ban đầu dùng **constructor injection**: `ReportPublisher` nhận phụ thuộc từ bên ngoài:

~~~java
ReportPublisher publisher =
        new ReportPublisher(formatter, destination);
~~~

Việc khởi tạo các instance khác nhau giúp chọn tổ hợp tại runtime:

~~~java
Formatter formatter =
        useMarkdown ? new MarkdownFormatter() : new PlainTextFormatter();

Destination destination =
        keepArchive ? new MemoryArchive() : new ConsoleDestination();

ReportPublisher publisher =
        new ReportPublisher(formatter, destination);
~~~

Ở đây các biến `useMarkdown` và `keepArchive` chỉ là cấu hình lựa chọn. Thuật toán **`ReportPublisher.publish` không thay đổi**.

Một cách khác là dùng setter để thay strategy của một publisher đang tồn tại, nhưng phải cân nhắc đồng thời, vòng đời và invariant. Với ví dụ, field `final` và constructor injection giúp mỗi `ReportPublisher` có bộ phụ thuộc rõ ràng, **không bị thay tham chiếu sau khởi tạo**.

**Quan trọng:** `final Formatter formatter` chỉ ngăn gán lại field, không bảo đảm object formatter tự bất biến hoặc thread-safe. Nếu các thành phần giữ trạng thái mutable và được chia sẻ giữa nhiều thread, cần thiết kế đồng bộ/thực thi phù hợp.

### Kết hợp và dependency inversion

`ReportPublisher` phụ thuộc vào **`Formatter` và `Destination` là abstraction**, chứ không phụ thuộc trực tiếp `MarkdownFormatter` hoặc `MemoryArchive`. Đây là một cách áp dụng Dependency Inversion: logic cấp cao không gắn với một cách triển khai cụ thể.

Tuy nhiên, **composition không bắt buộc phải có interface**. Nếu một thành phần chỉ có một cách dùng và không cần thay thế, field kiểu class cụ thể cũng có thể là thiết kế hợp lý. Không nên sinh hàng loạt interface khi chúng chưa giải quyết một yêu cầu rõ ràng.

## 9. Tái sử dụng qua kết hợp và Strategy/Decorator

Hai mô hình hay gặp khi kết hợp đối tượng:

### Strategy: thay thuật toán

Ví dụ `Formatter` ở trên là một **hợp đồng chiến lược**. `PlainTextFormatter` và `MarkdownFormatter` là các thuật toán định dạng khác nhau. `ReportPublisher` có thể sử dụng bất kỳ implementation phù hợp nào.

~~~java
Formatter formatter = new MarkdownFormatter();
String content = formatter.format(reportData);
~~~

### Decorator: bọc thêm hành vi

Giả sử mọi destination đều cần ghi log trước khi xuất. Thay vì kế thừa từng destination, có thể **bọc** một destination:

~~~java
class LoggingDestination implements Destination {
    private final Destination target;

    LoggingDestination(Destination target) {
        this.target = java.util.Objects.requireNonNull(target);
    }

    @Override
    public void deliver(String formattedReport) {
        System.out.println("[LOG] Đang xuất báo cáo");
        target.deliver(formattedReport);
    }
}
~~~

~~~java
Destination wrapped =
        new LoggingDestination(new ConsoleDestination());

new ReportPublisher(new MarkdownFormatter(), wrapped).publish(reportData);
~~~

`LoggingDestination` **implements cùng interface** nhưng tái sử dụng hành vi bằng cách **ủy quyền** cho `target`. Nó có thể được lắp quanh một destination khác, không cần các lớp con kiểu `LoggedConsoleDestination`, `LoggedMemoryArchive`, v.v.

**Lưu ý:** đoạn bọc log chạy trước bước `deliver`, nhưng không chứng minh bước xuất chắc chắn thành công. Đối với yêu cầu audit thực tế, phải xác định rõ thời điểm log, lỗi và nghĩa vụ lưu vết.

## 10. Kiểm thử khi tái sử dụng bằng kết hợp

Một điểm mạnh của kết hợp là **có thể thay đối tượng phụ thuộc bằng fake**. Ta kiểm tra riêng `ReportPublisher` mà không ghi file hay gọi hệ thống ngoài.

Ví dụ JUnit 5 (cần dependency JUnit Jupiter; file demo chính không cần JUnit):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ReportPublisherTest {

    @Test
    void publisherFormatsBeforeDelivering() {
        final String[] delivered = new String[1];

        ReuseComparisonDemo.Formatter formatter =
                report -> "[" + report.getTitle() + "]";

        ReuseComparisonDemo.Destination fakeDestination =
                text -> delivered[0] = text;

        ReuseComparisonDemo.ReportPublisher publisher =
                new ReuseComparisonDemo.ReportPublisher(
                        formatter, fakeDestination);

        publisher.publish(new ReuseComparisonDemo.ReportData(
                "Doanh thu", "Nội dung"));

        assertEquals("[Doanh thu]", delivered[0]);
    }

    @Test
    void archiveDoesNotExposeMutableList() {
        ReuseComparisonDemo.MemoryArchive archive =
                new ReuseComparisonDemo.MemoryArchive();
        archive.deliver("Một báo cáo");

        assertThrows(UnsupportedOperationException.class,
                () -> archive.readAll().clear());

        assertEquals(1, archive.readAll().size());
    }
}
~~~

`Formatter` và `Destination` đều là **functional interface** (một phương thức trừu tượng), nên có thể dùng lambda làm fake; đây là lợi ích của cách phụ thuộc vào abstraction.

Khi dùng kế thừa, vẫn hoàn toàn có thể test được subclass, nhưng nhiều hành vi kiểm thử có thể phụ thuộc vào quy trình được kế thừa hoặc các protected hook. Nếu lớp cha có trạng thái phức tạp, việc dựng fixture và kiểm chứng hiệu ứng phụ đôi khi khó hơn so với lắp ráp những thành phần nhỏ độc lập.

## 11. Chú ý về vòng đời, trạng thái và ngoại lệ

Tái sử dụng mã nguồn **không tự bảo đảm** cập nhật trạng thái đúng hoặc xử lý lỗi đúng.

### Thành phần mutable có thể được chia sẻ

~~~java
MemoryArchive shared = new MemoryArchive();

ReportPublisher a = new ReportPublisher(
        new MarkdownFormatter(), shared);

ReportPublisher b = new ReportPublisher(
        new PlainTextFormatter(), shared);
~~~

Hai publisher **cùng tham chiếu một `MemoryArchive`**. Khi mỗi bên `publish`, cả hai báo cáo đi vào **cùng danh sách `stored`** của archive. Nếu muốn kho riêng, hãy truyền hai instance `MemoryArchive` khác nhau.

### Ngoại lệ không tự hoàn tác

Trong `ReportPublisher.publish`, formatter chạy trước destination:

~~~java
String text = formatter.format(report);
destination.deliver(text);
~~~

Nếu formatter ném ngoại lệ, destination không được gọi. Nếu destination ghi một phần rồi ném ngoại lệ, không có gì trong composition tự động rollback thao tác đã ghi. Với file, database, queue hay mạng cần quy tắc transaction/retry/idempotency phù hợp.

### An toàn luồng không đến từ `final` hoặc `private`

`MemoryArchive` sử dụng `ArrayList`, **không thread-safe** khi bị nhiều thread cập nhật đồng thời. `ReportPublisher` giữ hai field `final` nhưng điều đó không làm các thành phần mutable mà chúng tham chiếu tự an toàn luồng. Hệ thống đa luồng cần đồng bộ hoặc chuyển sang cấu trúc/kiến trúc phù hợp.

Những vấn đề này có thể xuất hiện cả với kế thừa lẫn kết hợp; đừng nhầm quyết định tái sử dụng code với bảo đảm về vòng đời, dữ liệu và concurrency.

## 12. Khi kế thừa vẫn tốt hơn nhiều lớp ủy quyền

Dùng kết hợp “mọi nơi, mọi lúc” có thể tạo một hệ thống quá phức tạp: mỗi thao tác phải đi qua vài lớp wrapper không thêm ý nghĩa, mỗi hợp đồng chỉ có một implementation và không có chiều thay đổi độc lập.

Trong ví dụ kế thừa, `SalesReport` thực sự là một báo cáo và chia sẻ khung `render()` ổn định với các report khác. Nếu yêu cầu chỉ có **chuyên biệt hóa phần thân báo cáo**, không có formatter/destination thay đổi độc lập, `AbstractReport` là một abstraction có thể rất hợp lý.

Ngược lại, nếu ngày mai cần xuất nội dung **của mọi loại báo cáo** qua PDF, email, console hoặc lưu kho, gắn logic xuất vào từng subclass khiến sự mở rộng khó hơn. Tách `Formatter` và `Destination` là hợp lý khi chúng thành các chiều biến thể riêng.

Có thể **kết hợp cả hai cách**: một `SalesReport extends AbstractReport` để sinh nội dung, rồi đưa nội dung đó tới một `ReportPublisher` được lắp ghép formatter và destination. “Ưu tiên composition” không phải chọn một và vứt bỏ hoàn toàn cách còn lại.

## 13. Quy trình lựa chọn trong dự án

~~~mermaid
flowchart TD
    A["Muốn tái sử dụng chức năng"] --> B{"Có quan hệ is-a đúng<br/>và hợp đồng cha ổn định?"}
    B -->|Không| C["Ưu tiên kết hợp/delegation"]
    B -->|Có| D{"Subclass chỉ thay vài<br/>điểm mở rộng được thiết kế?"}
    D -->|Có| E["Cân nhắc kế thừa"]
    D -->|Không| F["Tách các chiều thay đổi<br/>thành thành phần"]
    F --> C
    E --> G["Kiểm tra LSP, invariant,<br/>quyền truy cập, coupling"]
    C --> H["Định nghĩa interface khi hữu ích,<br/>inject và test thành phần"]
~~~

Các câu hỏi thực hành:

1. **Is-a hay has-a?** “Bộ xuất báo cáo có một formatter” tự nhiên hơn “bộ xuất báo cáo là một formatter”.
2. **Phần nào có lý do thay đổi riêng?** Formatter có thể thay độc lập với destination.
3. **Code sử dụng cần biết bao nhiêu?** `ReportPublisher` chỉ cần `Formatter` và `Destination`.
4. **Có ràng buộc vòng đời không?** Thành phần được tạo sở hữu riêng hay truyền vào để có thể chia sẻ?
5. **Có cần thay thế hoặc fake khi test?** Đưa hành vi thay đổi vào interface khi việc này đem lại giá trị.
6. **Có phá hợp đồng của lớp cha không?** Subclass có phải override rồi ném `UnsupportedOperationException` cho thao tác lẽ ra hợp lệ?
7. **Chi phí cấu trúc có đáng không?** Một lớp đơn giản không cần bị phân rã thành mười interface nếu không có nhu cầu thật.

## 14. Lỗi phổ biến

| Lỗi | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Kế thừa chỉ để lấy lại vài phương thức | `Car extends Engine` | Đặt `Engine` làm thành phần rồi delegation |
| Subclass phá cam kết của superclass | Override thao tác bằng lỗi “không hỗ trợ” | Xem lại quan hệ is-a, tách năng lực thành interface |
| Dùng subclass cho từng cặp lựa chọn | `CsvEmail`, `CsvFile`, `PdfEmail`... | Tách `Formatter` và `Destination` |
| Kết hợp nhưng phụ thuộc quá cứng | `new EmailClient()` nằm sâu trong `ReportPublisher` | Cân nhắc constructor injection theo vai trò |
| Mọi lớp đều được bọc qua interface không cần thiết | Nhiều wrapper không thêm hành vi/khả năng thay thế | Giữ thiết kế tối giản có cơ sở |
| Nhầm có field với sở hữu vòng đời UML | Tự vẽ hình thoi đặc cho dependency được inject | Phân biệt association/aggregation với composition chặt |
| Đổi component rồi nghĩ toàn bộ trạng thái độc lập | Hai publisher dùng chung một archive | Xác định rõ chia sẻ hay sở hữu instance |
| Nghĩ composition tự bảo đảm atomic/thread-safe | List mutable bị ghi song song | Thiết kế transaction/đồng bộ riêng |
| Nhầm hợp đồng kiểu với hợp đồng nghiệp vụ | Hai strategy cùng interface nhưng một bên trả kết quả sai | Viết contract test và điều kiện hậu hợp lệ |

## 15. Bài tập tự kiểm tra

**Câu 1.** `class PaymentService extends EmailClient` chỉ để gọi `sendMail()` có hợp lý không?

**Đáp án:** Thường không. `PaymentService` **sử dụng** chức năng gửi email, không phải **một loại EmailClient**. Nên nhận một đối tượng phụ thuộc qua constructor hoặc composition thích hợp.

**Câu 2.** Một `ReportPublisher` đang dùng `MarkdownFormatter`. Làm sao đổi sang `PlainTextFormatter` mà không sửa nội dung `publish`?

**Đáp án:** Tạo/cấu hình `ReportPublisher` với `new PlainTextFormatter()` qua constructor. `publish` vẫn gọi `formatter.format(report)` theo interface.

**Câu 3.** `SalesReport extends AbstractReport` có lợi gì?

**Đáp án:** `SalesReport` dùng lại việc kiểm tra tiêu đề và khung `render()` của lớp cha; nó chỉ cung cấp `buildBody()`. Điều kiện là quan hệ loại báo cáo và hợp đồng của lớp cha có ý nghĩa.

**Câu 4.** Nếu hai publisher nhận cùng `MemoryArchive`, có bao nhiêu kho lưu trữ được tạo?

**Đáp án:** Một `MemoryArchive` được tạo từ lệnh `new` tương ứng rồi được chia sẻ qua hai field tham chiếu; kết hợp không tự sao chép đối tượng. Mỗi publisher có đối tượng riêng nhưng cùng dùng chung archive.

**Câu 5.** Vì sao không nên tạo `SalesMarkdownConsoleReport`, `SalesPlainTextArchiveReport` cho mọi tổ hợp?

**Đáp án:** Nội dung báo cáo, định dạng và nơi xuất là các chiều thay đổi độc lập. Kế thừa cho mọi tổ hợp tạo nhiều lớp phụ thuộc lẫn nhau; lắp ghép formatter/destination giúp tái sử dụng độc lập.

**Câu 6.** `ReportPublisher` giữ field `final Destination destination`. `MemoryArchive` có thread-safe hoặc immutable ngay không?

**Đáp án:** Không. `final` ngăn gán lại tham chiếu của field, không khóa trạng thái bên trong đối tượng `Destination`. Phải thiết kế synchronization/immutable/concurrency riêng khi cần.

**Câu 7.** Có nên dùng interface cho một lớp duy nhất không bao giờ thay đổi?

**Đáp án:** Không bắt buộc. Interface hữu ích khi làm rõ hợp đồng độc lập, dễ fake/test hoặc muốn thay implementation. Nếu không có những nhu cầu đó, kiểu class cụ thể có thể đơn giản hơn.

**Câu 8.** Một lớp con được tạo ra để kế thừa mã tiện ích nhưng hoàn toàn không đáp ứng được các kỳ vọng về hành vi của lớp cha. Điều gì sai?

**Đáp án:** Quan hệ *is-a* và nguyên tắc thay thế có thể bị vi phạm. Cần xem lại mô hình; thường phù hợp hơn khi sử dụng một đối tượng helper/collaborator bằng kết hợp.

## Kết luận

**Kế thừa** tái sử dụng theo quan hệ “một loại của”: subclass nhận phần chung của superclass và chỉ chuyên biệt hóa những điểm hợp lệ. **Kết hợp** tái sử dụng theo quan hệ “có hoặc dùng”: đối tượng phối hợp những thành phần có trách nhiệm riêng rồi ủy quyền công việc cho chúng.

Không có công thức “mọi nơi dùng composition” hoặc “mọi nơi dùng inheritance”. Chọn **kế thừa khi quan hệ is-a và hợp đồng cha thật sự vững**, chọn **kết hợp khi các khả năng cần lắp ghép hoặc thay đổi độc lập**. Một thiết kế Java tốt thường sử dụng cả hai đúng vị trí để tránh cây kế thừa gượng ép và giữ code dễ kiểm thử, dễ phát triển.