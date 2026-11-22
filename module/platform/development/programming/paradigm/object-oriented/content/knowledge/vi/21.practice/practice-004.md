# Bài tập: Chọn kế thừa hay kết hợp trong Java OOP

## Mục tiêu

Khi thiết kế hướng đối tượng, hai cách rất phổ biến để các lớp phối hợp và tái sử dụng hành vi là **kế thừa (inheritance)** và **kết hợp (composition)**. Bài thực hành này yêu cầu bạn lựa chọn dựa trên bản chất quan hệ nghiệp vụ, sau đó chứng minh lựa chọn bằng chương trình Java và kiểm thử.

Hoàn thành bài học, bạn cần:
- Phân biệt quan hệ **is-a** (là một loại của) và **has-a/uses-a** (có hoặc sử dụng một thành phần).
- Biết khi nào một lớp con có thể **thay thế** lớp cha mà không phá hợp đồng hành vi.
- Dùng interface và constructor injection để lắp ghép các thành phần có thể thay thế.
- Nhận diện kế thừa chỉ để mượn code, phân cấp lớp phình to và sự phụ thuộc quá chặt vào lớp cha.
- Đưa ra lời giải thiết kế, viết Java chạy được và kiểm thử cả hợp đồng chung lẫn khả năng thay thế thành phần.

**Điểm cần nhớ:** Không có công thức "luôn dùng composition" hoặc "cứ có điểm chung thì dùng extends". Hãy dựa trên trách nhiệm, hợp đồng public, mức phụ thuộc và khả năng thay đổi của hệ thống.

## 1. Phân biệt bản chất hai lựa chọn

Kế thừa một lớp trong Java dùng cú pháp **extends**. Lớp con nhận hành vi có thể kế thừa từ lớp cha, có thể định nghĩa thêm hoặc ghi đè phương thức được phép override.

Kết hợp là việc một đối tượng **giữ tham chiếu tới đối tượng khác** và gọi các phương thức của đối tượng đó để thực hiện công việc. Tham chiếu có thể mang kiểu interface, nhờ vậy implementation cụ thể có thể thay đổi mà lớp sử dụng không cần biết chi tiết.

| Câu hỏi thiết kế | Kế thừa | Kết hợp |
| --- | --- | --- |
| Quan hệ mô hình | A **là một loại B** | A **có/dùng một B** |
| Biểu hiện trong Java | class A extends B | private final B b; |
| Mục tiêu thường gặp | Chuyên biệt hóa một hợp đồng chung ổn định | Ghép các năng lực hoặc cộng tác viên |
| Đổi cách thực hiện | Thay bằng một lớp con khác, phải theo hợp đồng lớp cha | Tiêm một implementation khác |
| Ràng buộc | Dễ phụ thuộc vào thiết kế của lớp cha | Có thể giảm coupling nếu dựa vào interface nhỏ |
| Kiểm thử | Chạy hợp đồng chung trên mọi lớp con | Thay collaborator bằng fake hoặc stub |
| Rủi ro | Lớp con làm yếu hợp đồng, kéo theo API không phù hợp | Quá nhiều lớp ủy quyền hoặc abstraction không cần thiết |

**Interface không phải composition.** Khi một lớp viết implements ReportFormatter, nó công bố rằng đối tượng đó thỏa hợp đồng ReportFormatter. Composition xuất hiện khi ReportPublisher **chứa** một trường kiểu ReportFormatter và **ủy quyền** tác vụ định dạng cho trường ấy. Hai kỹ thuật thường được dùng cùng nhau.

## 2. Bài tập phân loại trước khi xem đáp án

Với từng tình huống sau, hãy chọn **K (kế thừa), H (kết hợp)** hoặc **C (cần làm rõ thêm)**, rồi trả lời vì sao. Bạn nên thử tự làm trước khi đọc lời giải.

| Tình huống | Câu hỏi cần giải thích |
| --- | --- |
| A. Circle và Rectangle đều là Shape, mỗi loại có công thức area() khác nhau | Có hợp đồng Shape chung mà tất cả lớp con tuân thủ được không? |
| B. ReportPublisher cần xuất dữ liệu thành CSV, văn bản hoặc JSON | ReportPublisher có thật sự là một CSV formatter không? |
| C. Car có Engine và có thể dùng loại động cơ khác | Một chiếc ô tô có phải là một loại động cơ không? |
| D. SavingsAccount kế thừa BankAccount nhưng cấm hầu hết hành vi rút tiền vốn được lớp cha cho phép | Lớp con có còn thay được lớp cha không? |
| E. Một AlertService cần gửi qua EmailSender hoặc SmsSender | Hành vi gửi có thể cấu hình độc lập với quy tắc cảnh báo không? |
| F. Một framework cung cấp AbstractTask với hợp đồng execute() rõ ràng và các hook được thiết kế cho việc mở rộng | Lớp con được framework kỳ vọng tuân thủ điều gì? |

Trong phần mã, ta giải hai tình huống A và B thành một dự án chạy được. Những trường hợp còn lại được phân tích ở phần lời giải và bài tập mở rộng.

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Bạn muốn tạo quan hệ giữa A và B"] --> B{"A thực sự là một loại B?"}
    B -->|Không| C["Ưu tiên kết hợp / ủy quyền"]
    B -->|Có| D{"A thay được B theo hợp đồng?"}
    D -->|Không| E["Thiết kế lại hợp đồng hoặc tách vai trò"]
    D -->|Có| F{"Hợp đồng ổn định và cần chuyên biệt hóa?"}
    F -->|Có| G["Có thể dùng kế thừa"]
    F -->|Không| H["Xem xét interface + kết hợp"]
    C --> I["Kiểm tra trách nhiệm và coupling"]
    G --> I
    H --> I
    E --> I
~~~

Đây là câu hỏi gợi ý, không phải thuật toán đưa ra đáp án tuyệt đối. Ví dụ, dù có quan hệ is-a, một interface cùng các implementation độc lập có thể gọn hơn một abstract class mang nhiều state.

## 3. Bài A — Mô hình các hình học bằng kế thừa

**Yêu cầu:** Xây dựng một loại Shape có hợp đồng tính diện tích; Circle và Rectangle là các loại Shape cụ thể. Chương trình nhận một danh sách Shape mà không cần dùng if/else theo từng lớp để tính diện tích.

Ta chọn **abstract class Shape** vì các hình đều có hợp đồng area(), cùng có tên hiển thị và cùng được dùng như Shape. Hai lớp con phải trả diện tích không âm cho kích thước đã được kiểm tra.

~~~mermaid
classDiagram
    class Shape {
        <<abstract>>
        -String name
        +name() String
        +area() double*
    }
    class Circle {
        -double radius
        +area() double
    }
    class Rectangle {
        -double width
        -double height
        +area() double
    }
    Shape <|-- Circle
    Shape <|-- Rectangle
~~~

### 3.1. Shape.java

~~~java
package vn.example;

public abstract class Shape {
    private final String name;

    protected Shape(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name;
    }

    public final String name() {
        return name;
    }

    /** Diện tích theo đơn vị bình phương; lớp con phải hiện thực. */
    public abstract double area();
}
~~~

Shape thiết lập một phần trạng thái dùng chung (name), bảo đảm tên không trống và quy định thao tác area(). Nếu các lớp không cần chia sẻ state hay implementation, dùng interface Shape với area() cũng là một phương án hợp lệ.

### 3.2. Circle.java

~~~java
package vn.example;

public final class Circle extends Shape {
    private final double radius;

    public Circle(double radius) {
        super("Circle");
        requirePositiveFinite(radius, "radius");
        this.radius = radius;
    }

    @Override
    public double area() {
        return Math.PI * radius * radius;
    }

    private static void requirePositiveFinite(double value, String field) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new IllegalArgumentException(
                    field + " must be finite and positive");
        }
    }
}
~~~

### 3.3. Rectangle.java

~~~java
package vn.example;

public final class Rectangle extends Shape {
    private final double width;
    private final double height;

    public Rectangle(double width, double height) {
        super("Rectangle");
        requirePositiveFinite(width, "width");
        requirePositiveFinite(height, "height");
        this.width = width;
        this.height = height;
    }

    @Override
    public double area() {
        return width * height;
    }

    private static void requirePositiveFinite(double value, String field) {
        if (!Double.isFinite(value) || value <= 0) {
            throw new IllegalArgumentException(
                    field + " must be finite and positive");
        }
    }
}
~~~

**Vì sao kế thừa hợp lý ở đây?** Đối tượng Circle hay Rectangle được sử dụng ở bất kỳ vị trí nào cần Shape.area(), không buộc caller quan tâm công thức bên trong. Cả hai đều áp dụng cùng ý nghĩa của area(): diện tích hình. Điều này thể hiện **đa hình** và khả năng thay thế theo hợp đồng.

Với giá trị double rất lớn, phép nhân có thể trả Infinity dù các kích thước đầu vào hữu hạn. Bài tập chưa cam kết diện tích luôn hữu hạn; nếu hệ thống yêu cầu điều đó, phải bổ sung quy tắc kiểm soát tràn/sai số và test tương ứng.

## 4. Bài B — Xuất báo cáo bằng kết hợp

**Yêu cầu:** ReportPublisher nhận một báo cáo doanh thu, định dạng theo CSV hoặc văn bản rồi lưu nội dung qua một kênh xuất. Sau này có thể thêm JSON formatter và thay phương thức lưu sang file/database mà không thay đổi nghiệp vụ điều phối.

Thiết kế **không phù hợp**:

~~~java
// Mã gợi ý về mùi thiết kế; KHÔNG đưa vào dự án chạy bên dưới.
class CsvExporter {
    String toCsv(/* dữ liệu */) { return "..."; }
}

class ReportPublisher extends CsvExporter {
    // Kế thừa chỉ để dùng toCsv().
}
~~~

Một report publisher **không phải** là một loại CSV exporter. Khi hệ thống cần định dạng khác, mô hình kế thừa này ép thay đổi quan hệ lớp hoặc thêm nhánh điều kiện.

Thiết kế **hợp lý hơn**: ReportPublisher có một ReportFormatter và một ReportSink.

~~~mermaid
classDiagram
    class ReportPublisher {
        -ReportFormatter formatter
        -ReportSink sink
        +publish(SalesSummary) void
    }
    class ReportFormatter {
        <<interface>>
        +format(SalesSummary) String
    }
    class CsvFormatter {
        +format(SalesSummary) String
    }
    class TextFormatter {
        +format(SalesSummary) String
    }
    class ReportSink {
        <<interface>>
        +save(String) void
    }
    class SalesSummary {
        +period() String
        +revenueVnd() long
    }
    ReportPublisher --> ReportFormatter : sử dụng
    ReportPublisher --> ReportSink : sử dụng
    ReportPublisher --> SalesSummary : nhận đầu vào
    ReportFormatter <|.. CsvFormatter
    ReportFormatter <|.. TextFormatter
~~~

### 4.1. SalesSummary.java

~~~java
package vn.example;

/** Bản tóm tắt doanh thu cho một tháng, đơn vị tiền nguyên VND. */
public record SalesSummary(String period, long revenueVnd) {
    public SalesSummary {
        // Ví dụ chấp nhận dạng YYYY-MM với tháng từ 01 đến 12.
        if (period == null
                || !period.matches("[0-9]{4}-(0[1-9]|1[0-2])")) {
            throw new IllegalArgumentException("Invalid period");
        }
        if (revenueVnd < 0) {
            throw new IllegalArgumentException(
                    "revenueVnd must not be negative");
        }
    }
}
~~~

SalesSummary là một record bất biến giúp dễ truyền dữ liệu đầu vào. Quy tắc hợp lệ của kỳ báo cáo nằm ngay tại lớp mô hình, tránh việc formatter phải đoán dữ liệu đã đúng hay chưa.

### 4.2. ReportFormatter.java

~~~java
package vn.example;

@FunctionalInterface
public interface ReportFormatter {
    String format(SalesSummary summary);
}
~~~

### 4.3. CsvFormatter.java

~~~java
package vn.example;

public final class CsvFormatter implements ReportFormatter {
    @Override
    public String format(SalesSummary summary) {
        return summary.period() + "," + summary.revenueVnd();
    }
}
~~~

Dữ liệu period chỉ chứa chữ số và dấu gạch nối, revenueVnd chỉ chứa chữ số nên ví dụ không cần escape dấu phẩy. Một CSV formatter tổng quát phải xử lý dấu phẩy, dấu nháy kép và xuống dòng đúng chuẩn.

### 4.4. TextFormatter.java

~~~java
package vn.example;

public final class TextFormatter implements ReportFormatter {
    @Override
    public String format(SalesSummary summary) {
        return "Thang " + summary.period() + ": "
                + summary.revenueVnd() + " VND";
    }
}
~~~

CsvFormatter và TextFormatter cùng **implements ReportFormatter** để thay thế được cho nhau. Chúng không cần kế thừa một formatter cụ thể.

### 4.5. ReportSink.java

~~~java
package vn.example;

@FunctionalInterface
public interface ReportSink {
    void save(String content);
}
~~~

### 4.6. ReportPublisher.java

~~~java
package vn.example;

import java.util.Objects;

public final class ReportPublisher {
    private final ReportFormatter formatter;
    private final ReportSink sink;

    public ReportPublisher(ReportFormatter formatter, ReportSink sink) {
        this.formatter = Objects.requireNonNull(
                formatter, "formatter");
        this.sink = Objects.requireNonNull(sink, "sink");
    }

    public void publish(SalesSummary summary) {
        Objects.requireNonNull(summary, "summary");
        String content = formatter.format(summary);
        sink.save(content);
    }
}
~~~

ReportPublisher quyết định **trình tự công việc**: định dạng trước, lưu sau. Nó không chứa công thức CSV, không tự mở file và không tạo formatter bằng new. Những khả năng này được cung cấp từ ngoài thông qua constructor.

Nhờ vậy:
- Muốn thêm JSON thì tạo JsonFormatter implements ReportFormatter.
- Muốn lưu ra cơ sở dữ liệu thì tạo DatabaseReportSink implements ReportSink.
- Muốn kiểm thử mà không ghi ra hệ thống thật thì cung cấp một sink ghi nhận dữ liệu trong bộ nhớ.
- Không phải sửa ReportPublisher mỗi lần thêm format hay sink mới, miễn các collaborator tuân thủ hợp đồng đã định.

## 5. Ghép hai bài vào một chương trình Java chạy được

Cấu trúc dự án:

~~~text
oop-inheritance-or-composition/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── Shape.java
    │   ├── Circle.java
    │   ├── Rectangle.java
    │   ├── SalesSummary.java
    │   ├── ReportFormatter.java
    │   ├── CsvFormatter.java
    │   ├── TextFormatter.java
    │   ├── ReportSink.java
    │   ├── ReportPublisher.java
    │   └── Main.java
    └── test/java/vn/example/
        └── DesignChoiceTest.java
~~~

Tạo pom.xml cho Java 17 + JUnit Jupiter:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>oop-inheritance-or-composition</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/vn/example/Main.java**

~~~java
package vn.example;

import java.util.List;

public final class Main {
    public static void main(String[] args) {
        // Bài A: cùng kiểu Shape, hai lớp con có cách tính riêng.
        List<Shape> shapes = List.of(
                new Circle(2),
                new Rectangle(3, 4));

        double totalArea = shapes.stream()
                .mapToDouble(Shape::area)
                .sum();

        System.out.println("Tong dien tich = " + totalArea);

        // Bài B: thay formatter và sink bằng cách lắp ghép object.
        SalesSummary report = new SalesSummary("2026-10", 1_500_000);
        ReportSink console = System.out::println;

        ReportPublisher csv = new ReportPublisher(
                new CsvFormatter(), console);
        ReportPublisher text = new ReportPublisher(
                new TextFormatter(), console);

        csv.publish(report);
        text.publish(report);
    }
}
~~~

Khi chạy Main, chương trình cộng diện tích của Circle và Rectangle qua cùng kiểu Shape, sau đó xuất cùng một báo cáo theo hai định dạng. Các lớp nghiệp vụ không phải sửa khi composition root đổi lựa chọn formatter.

Chạy từ thư mục gốc dự án:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes vn.example.Main
~~~

Kết quả ví dụ:

~~~text
Tong dien tich = 24.566370614359172
2026-10,1500000
Thang 2026-10: 1500000 VND
~~~

Với số thực double, phần hiển thị có thể có sai biệt chữ số cuối theo môi trường tính toán hoặc thay đổi cách định dạng; trong test nên so sánh với sai số chấp nhận được.

## 6. Kiểm thử để kiểm chứng lựa chọn thiết kế

**src/test/java/vn/example/DesignChoiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class DesignChoiceTest {

    @Test
    void circleAndRectangleWorkThroughShapeContract() {
        Shape circle = new Circle(2);
        Shape rectangle = new Rectangle(3, 4);

        assertEquals(Math.PI * 4, circle.area(), 1e-9);
        assertEquals(12.0, rectangle.area(), 1e-9);

        List<Shape> mixed = List.of(circle, rectangle);
        double sum = mixed.stream().mapToDouble(Shape::area).sum();

        assertEquals(Math.PI * 4 + 12, sum, 1e-9);
        assertEquals("Circle", circle.name());
        assertEquals("Rectangle", rectangle.name());
    }

    @Test
    void shapeDimensionsMustBePositiveAndFinite() {
        assertThrows(IllegalArgumentException.class,
                () -> new Circle(0));
        assertThrows(IllegalArgumentException.class,
                () -> new Circle(Double.NaN));
        assertThrows(IllegalArgumentException.class,
                () -> new Rectangle(-1, 2));
        assertThrows(IllegalArgumentException.class,
                () -> new Rectangle(2, Double.POSITIVE_INFINITY));
    }

    @Test
    void publisherCanReplaceFormatterWithoutSubclassing() {
        List<String> saved = new ArrayList<>();
        ReportSink sink = saved::add;
        SalesSummary summary = new SalesSummary("2026-10", 1_500_000);

        new ReportPublisher(new CsvFormatter(), sink).publish(summary);
        new ReportPublisher(new TextFormatter(), sink).publish(summary);

        assertEquals(List.of(
                "2026-10,1500000",
                "Thang 2026-10: 1500000 VND"), saved);
    }

    @Test
    void publisherAllowsNewFormatterWithoutChangingItsCode() {
        List<String> saved = new ArrayList<>();
        ReportFormatter custom = summary ->
                "REPORT=" + summary.period();

        ReportPublisher publisher = new ReportPublisher(
                custom, saved::add);

        publisher.publish(new SalesSummary("2026-11", 500));

        assertEquals(List.of("REPORT=2026-11"), saved);
    }

    @Test
    void nullReportDoesNotCallCollaborators() {
        AtomicInteger saves = new AtomicInteger();
        ReportSink sink = ignored -> saves.incrementAndGet();
        ReportPublisher publisher = new ReportPublisher(
                new CsvFormatter(), sink);

        assertThrows(NullPointerException.class,
                () -> publisher.publish(null));
        assertEquals(0, saves.get());
    }

    @Test
    void publisherDoesNotSwallowStorageFailure() {
        ReportSink failing = content -> {
            throw new IllegalStateException("Storage unavailable");
        };

        ReportPublisher publisher = new ReportPublisher(
                new CsvFormatter(), failing);

        assertThrows(IllegalStateException.class,
                () -> publisher.publish(
                        new SalesSummary("2026-10", 10)));
    }

    @Test
    void constructorsValidateTheirContracts() {
        assertThrows(IllegalArgumentException.class,
                () -> new SalesSummary(" ", 20));
        assertThrows(IllegalArgumentException.class,
                () -> new SalesSummary("2026-13", 20));
        assertThrows(IllegalArgumentException.class,
                () -> new SalesSummary("2026-10", -1));

        assertThrows(NullPointerException.class,
                () -> new ReportPublisher(null, text -> {}));
        assertThrows(NullPointerException.class,
                () -> new ReportPublisher(new CsvFormatter(), null));
    }
}
~~~

Có **7 phương thức @Test** trong bộ test trên. Khi mã được chép đúng cấu trúc tệp và có JDK 17 + Maven, dự kiến các test chạy thành công với 0 failures và 0 errors.

Các phép assert thể hiện hai khía cạnh:

| Kiểm thử | Quyết định OOP đang được bảo vệ |
| --- | --- |
| circleAndRectangleWorkThroughShapeContract | Các lớp con thay thế được kiểu Shape và tuân thủ ý nghĩa chung của area() |
| shapeDimensionsMustBePositiveAndFinite | Lớp con tự bảo vệ bất biến riêng |
| publisherCanReplaceFormatterWithoutSubclassing | ReportPublisher sử dụng nhiều implementation cùng interface |
| publisherAllowsNewFormatterWithoutChangingItsCode | Bổ sung formatter mới mà không cần sửa lớp điều phối |
| nullReportDoesNotCallCollaborators | Không gọi phụ thuộc khi input không hợp lệ |
| publisherDoesNotSwallowStorageFailure | Kết quả lỗi từ phụ thuộc không bị che giấu |
| constructorsValidateTheirContracts | Đối tượng được tạo ở trạng thái hợp lệ |

Test cho thấy một lớp con thỏa một số ca của hợp đồng; không thể từ vài test kết luận mọi lớp con luôn thay thế được nhau trong tất cả tình huống. Khi thiết kế hierarchy lớn, cần viết thêm contract test dùng chung cho các lớp con và xác định rõ mọi điều kiện tiền/hậu.

## 7. Lời giải cho các tình huống ở đầu bài

| Tình huống | Lựa chọn gợi ý | Lập luận |
| --- | --- | --- |
| A. Circle / Rectangle / Shape | **K** (hoặc interface chung) | Cả hai thực sự là Shape và thực hiện hợp đồng diện tích chung |
| B. ReportPublisher và các formatter | **H** | Publisher sử dụng khả năng định dạng, không phải một formatter |
| C. Car và Engine | **H** | Car có engine; thay loại động cơ không biến car thành subclass của engine |
| D. SavingsAccount cấm rút trái hợp đồng BankAccount | **C: xem lại mô hình** | Lớp con có thể vi phạm nguyên tắc thay thế Liskov; cần điều chỉnh contract hoặc tách chính sách |
| E. AlertService gửi email/SMS | **H** | Tách nghiệp vụ cảnh báo khỏi phương tiện gửi; có thể tiêm interface MessageSender |
| F. AbstractTask và các task tuân thủ hook framework | **K khi hợp đồng rõ** | Abstract base class được thiết kế để subclass chuyên biệt hóa trong khuôn khổ đã định |

### Trường hợp D: đừng lạm dụng "is-a"

Một SavingsAccount ngoài đời có thể được gọi là một loại tài khoản ngân hàng, nhưng tên gọi **không đủ** để quyết định dùng kế thừa trong code. Nếu BankAccount cam kết rút một số tiền hợp lệ trong phạm vi số dư còn lại, mà SavingsAccount lại luôn ném UnsupportedOperationException, mã đang dựa vào hợp đồng lớp cha có thể bị phá.

Một số hướng thiết kế:
- Thu hẹp hợp đồng chung thành Account chỉ bảo đảm những hành vi mọi loại tài khoản đều thực sự hỗ trợ.
- Dùng các interface thể hiện năng lực như Withdrawable, nếu người dùng cần biết liệu một tài khoản có thể rút.
- Đưa chính sách rút tiền vào một WithdrawPolicy được **kết hợp** trong tài khoản, nếu sự khác biệt là quy tắc có thể thay đổi mà không làm mất hợp đồng chung.
- Với hierarchy hiện hữu, rà soát các method override xem có làm chặt hơn tiền điều kiện hoặc làm yếu hậu điều kiện của lớp cha không.

Chọn phương án cụ thể còn phụ thuộc yêu cầu nghiệp vụ. Không nên tự động giải bằng cách thêm nhiều lớp con hơn.

## 8. Tình huống lỗi thiết kế hay gặp

### Chỉ kế thừa để tiết kiệm vài dòng code

Ví dụ một lớp gửi hóa đơn kế thừa HttpClient chỉ để dùng post(). Quan hệ nghiệp vụ không đúng, đồng thời cả API kỹ thuật của HttpClient bị đưa vào lớp gửi hóa đơn. Kết hợp một HttpTransport interface sẽ thể hiện sự phụ thuộc tốt hơn.

### Quá nhiều tổ hợp lớp con

Nếu một hệ thống có 3 loại báo cáo, 4 định dạng và 2 cách lưu, mô hình một subclass cho mỗi tổ hợp có thể dẫn tới 3 × 4 × 2 = **24 lớp** chỉ để ghép tính năng. Khi các yếu tố thực sự độc lập, cấu hình ReportType, ReportFormatter và ReportSink bằng kết hợp giúp tránh tổ hợp kế thừa.

### Kế thừa nhưng lớp con phá bất biến lớp cha

Trong mô hình Rectangle có setter đổi width và height độc lập, Square extends Rectangle có thể phải sửa cả hai khi một setter được gọi. Nếu caller kỳ vọng setWidth không đổi height, Square không còn phù hợp với hợp đồng MutableRectangle. Lựa chọn tốt là mô hình bất biến hoặc hợp đồng Shape chung không có những setter mâu thuẫn.

### Composition nhưng quá nhiều abstraction

Một phép tính tổng thuần túy có thể chỉ cần phương thức trong lớp sở hữu dữ liệu. Không cần trích interface, factory và delegate chỉ để thực hiện phép cộng đơn giản. Composition có ích khi có trách nhiệm độc lập, sự thay thế có giá trị hoặc ranh giới với hệ thống bên ngoài.

### Nhầm đa hình với kế thừa lớp

Trong Java, đa hình có thể thể hiện qua **abstract class** hoặc **interface**. ReportFormatter là interface cho nhiều implementation; việc ReportPublisher dùng ReportFormatter qua một field mới tạo ra quan hệ composition. Bạn không cần extends một concrete formatter để có đa hình.

## 9. Bài tập nâng cao

### Bài 1 — Thay các định dạng mà không đổi code điều phối

Viết JsonFormatter implements ReportFormatter để xuất nội dung:

~~~json
{"period":"2026-10","revenueVnd":1500000}
~~~

Với chuỗi period bị giới hạn dạng YYYY-MM và số tiền là long không âm, ví dụ có thể tạo JSON tương đối đơn giản. Trong hệ thống thật, hãy dùng thư viện JSON để escape dữ liệu và kiểm tra tính hợp lệ. Thêm test kiểm chứng chuỗi JSON và bảo đảm không sửa ReportPublisher.

### Bài 2 — Thêm một sink khác

Viết InMemoryReportSink lưu danh sách String đã nhận. Truyền nó vào ReportPublisher và kiểm tra lần lượt hai báo cáo. Giải thích vì sao sink là collaborator phù hợp để thay thế, không phải lớp cha của publisher.

### Bài 3 — Phát hiện vi phạm hợp đồng

Thiết kế MutableRectangle với setWidth, setHeight và giả định hai kích thước thay đổi độc lập. Thử viết Square extends MutableRectangle, rồi xây một test dùng tham chiếu kiểu MutableRectangle. Xác định kỳ vọng nào bị phá và đề xuất thay đổi mô hình.

### Bài 4 — Kết hợp các chính sách

Một ứng dụng tính phí vận chuyển theo phương thức Standard, Express và International. Hãy quyết định nên:
- Tạo Shipment là base class cùng ba subclass; hay
- Để Shipment có ShippingPolicy, chọn chính sách qua constructor.

Nêu ít nhất hai yêu cầu nghiệp vụ khiến lựa chọn của bạn hợp lý. Ví dụ nếu một kiện hàng có thể đổi phương thức giao trong quá trình xử lý, chính sách là thành phần có thể thay đổi độc lập; nếu đó là các loại đối tượng có vòng đời và bất biến hoàn toàn khác, cần cân nhắc ranh giới các lớp.

### Bài 5 — Tự chấm lựa chọn

Với từng phương án mà bạn đã chọn, hãy viết ngắn:
1. Quan hệ chính xác giữa hai đối tượng là is-a hay has-a?
2. Có thể sử dụng A tại nơi kỳ vọng B mà không phá hợp đồng không?
3. Một yêu cầu mới sẽ buộc sửa những lớp nào?
4. Làm sao kiểm thử một implementation khác?
5. Điều gì trở nên phức tạp hơn khi dùng phương án đã chọn?

## 10. Tiêu chí hoàn thành

- [ ] Phân loại được 6 tình huống và giải thích từng quyết định.
- [ ] Có chương trình Java minh họa một trường hợp kế thừa **đúng ngữ nghĩa**, một trường hợp kết hợp **đúng trách nhiệm**.
- [ ] Chạy được chương trình với hai Shape khác nhau mà không rẽ nhánh theo kiểu cụ thể.
- [ ] Thay CsvFormatter bằng TextFormatter hoặc formatter mới mà không sửa ReportPublisher.
- [ ] Hiểu khác biệt giữa extends, implements và việc giữ tham chiếu tới collaborator.
- [ ] Có test cho hợp đồng, lỗi đầu vào và khả năng thay thành phần.
- [ ] Nhận ra trường hợp Liskov Substitution Principle bị ảnh hưởng bởi subclass hạn chế hành vi của lớp cha.
- [ ] Không lựa chọn inheritance chỉ vì muốn dùng lại một phương thức.

**Kết quả kỳ vọng:** Bạn có thể giải thích vì sao Shape được chuyên biệt hóa thành Circle/Rectangle, trong khi ReportPublisher sử dụng ReportFormatter/ReportSink như các thành phần độc lập. Chọn đúng quan hệ giúp code phản ánh nghiệp vụ, giữ hợp đồng rõ ràng và giảm chi phí sửa đổi về sau.