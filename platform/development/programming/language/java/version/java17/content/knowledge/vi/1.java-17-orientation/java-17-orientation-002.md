# Java 17 trong lộ trình học sau Java 8 và Java 11

## 1. Vì sao học Java 17 sau Java 8 và Java 11?

Java 17 là một phiên bản **Long-Term Support (LTS)** được phát hành vào tháng 9/2021. Trong lộ trình học Java, Java 17 đóng vai trò là cột mốc chuyển từ nền tảng Java đã quen thuộc ở Java 8/11 sang cách viết mã hiện đại hơn: mô hình dữ liệu gọn hơn, phân loại trạng thái bằng kiểu dữ liệu chặt chẽ hơn, xử lý nhánh dễ đọc hơn, và môi trường chạy có cơ chế đóng gói nội bộ JDK nghiêm ngặt hơn.

Đây là một **mốc học tập và triển khai có giá trị thực tế**, không phải phiên bản Java mới nhất ở mọi thời điểm. Sau Java 17 còn có các phiên bản LTS mới hơn, trong đó có Java 21 và Java 25. Việc chọn JDK để chạy một hệ thống phải dựa trên yêu cầu sản phẩm, framework, thư viện, chính sách hỗ trợ của nhà cung cấp và hạ tầng, thay vì mặc định rằng bản có số lớn nhất luôn phù hợp nhất.

Có thể hình dung ba mốc kiến thức như sau:

| Mốc học tập | Trọng tâm | Kết quả cần đạt |
|---|---|---|
| **Java 8** | Lambda, Stream API, Optional, `java.time`, `CompletableFuture`, nền tảng OOP và Collections | Viết được ứng dụng Java hiện đại ở mức nền tảng, hiểu cú pháp hàm và xử lý dữ liệu |
| **Java 9–11** | Module system, suy luận kiểu cục bộ `var`, API HTTP Client chuẩn, cải tiến Collections/Files/String; làm quen thay đổi trong JDK | Hiểu Java đã thay đổi như một nền tảng, không chỉ ở cú pháp |
| **Java 12–17** | Switch expression, text block, record, pattern matching cho `instanceof`, sealed class/interface, tính đóng gói mạnh của JDK | Viết mã rõ ý định hơn, thiết kế mô hình dữ liệu tốt hơn và vận hành/nâng cấp ứng dụng an toàn hơn |

**Mục tiêu của bài:** Sau khi học, bạn phải chỉ ra được vì sao một tính năng xuất hiện ở một giai đoạn cụ thể, khi nào nên dùng nó, khi nào không nên dùng, và cách đưa dự án Java 8/11 lên Java 17 có kiểm soát.

## 2. Hành trang cần có trước Java 17

### 2.1. Kiến thức Java 8 cần thật sự sử dụng thành thạo

Trước khi học cú pháp mới ở Java 17, hãy bảo đảm bạn đã áp dụng được:

- **Nền tảng ngôn ngữ:** class/interface, kế thừa và đa hình, generic, exception, immutable object, phạm vi truy cập và nguyên tắc đóng gói.
- **Collections:** phân biệt `List`, `Set`, `Map`; hiểu hợp đồng `equals()` và `hashCode()`; biết khi nào cấu trúc dữ liệu có thể bị thay đổi.
- **Lambda và method reference:** diễn đạt hành vi ngắn gọn với functional interface mà vẫn giữ mã dễ đọc.
- **Stream API:** `filter`, `map`, `flatMap`, `reduce`, `collect`; hiểu phép biến đổi trung gian, phép kết thúc, side effect và tính lazy.
- **Optional:** biểu diễn kết quả có thể vắng mặt ở ranh giới phù hợp; không lạm dụng Optional cho mọi field hoặc mọi tham số.
- **Date and Time API:** `Instant`, `LocalDate`, `LocalDateTime`, `ZonedDateTime`, `Duration`; hiểu khác biệt giữa mốc thời gian và ngày giờ theo múi giờ.
- **Concurrency cơ bản:** `Thread`, `ExecutorService`, `CompletableFuture`, thread safety và quản lý tài nguyên.

Ví dụ kỹ năng Java 8 vẫn là nền tảng trong Java 17:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

class Java8Foundation {
    static Map<String, Long> countByDepartment(List<Employee> employees) {
        return employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.counting()
                ));
    }

    interface Employee {
        boolean active();
        String department();
    }
}
~~~

Đoạn mã dùng Stream và method reference đã quen thuộc từ Java 8. Java 17 **bổ sung công cụ diễn đạt**, chứ không thay thế toàn bộ kỹ thuật này.

### 2.2. Kiến thức Java 9–11 giúp hiểu nền tảng

**Java Platform Module System (JPMS)** xuất hiện ở Java 9, khai báo module bằng `module-info.java`. Bạn nên hiểu `requires`, `exports` và sự khác nhau giữa *classpath* với *module path*. Tuy nhiên, **không bắt buộc phải module hóa mọi dự án** khi dùng Java 17; nhiều ứng dụng vẫn hoạt động tốt với classpath.

Java 10 đưa vào `var` cho **biến cục bộ** có thể suy ra kiểu khi khởi tạo. Nó không biến Java thành ngôn ngữ có kiểu động và không thay thế khai báo kiểu cho field hoặc kiểu trả về của phương thức.

~~~java
var names = List.of("An", "Binh", "Chi"); // Kiểu được suy ra: List<String>
// var value; // Không hợp lệ: không có biểu thức khởi tạo để suy ra kiểu
~~~

Java 11 hoàn thiện HTTP Client chuẩn trong gói `java.net.http` và có những API tiện dụng như `String.isBlank()`, `String.lines()`, `Files.readString()`. Bạn nên biết dùng API chuẩn trong trường hợp phù hợp, đồng thời hiểu thư viện HTTP chuyên dụng vẫn hữu ích khi cần những khả năng hoặc tích hợp đặc thù.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

class Java11HttpExample {
    static String getExamplePage() throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .GET()
                .build();
        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        ).body();
    }
}
~~~

Trong lộ trình, hãy phân biệt **kiến thức Java 8**, **thay đổi từ Java 9–11**, **thay đổi từ Java 12–17**. Điều này giúp đọc codebase cũ chính xác và tránh nhầm một tính năng là “tính năng mới của Java 17” dù thực tế đã được chuẩn hóa ở phiên bản trước.

## 3. Các cải tiến ngôn ngữ quan trọng cần học khi đến Java 17

### 3.1. Switch expression — trả về giá trị từ nhánh lựa chọn

Switch expression được chuẩn hóa ở **Java 14** và có sẵn trong Java 17. Khác với cách dùng `switch` statement truyền thống có thể cần `break`, switch expression có thể tính ra một giá trị và cú pháp mũi tên tránh lỗi rơi qua nhánh (*fall-through*) ngoài ý muốn.

~~~java
enum Priority { LOW, MEDIUM, HIGH }

class PriorityExample {
    static int responseHours(Priority priority) {
        return switch (priority) {
            case HIGH -> 2;
            case MEDIUM -> 8;
            case LOW -> 24;
        };
    }
}
~~~

Với nhánh chứa nhiều lệnh, dùng `yield` để cung cấp giá trị cho biểu thức:

~~~java
int fee = switch (customerType) {
    case "VIP" -> 0;
    case "STANDARD" -> 10;
    default -> {
        System.out.println("Áp dụng mức phí mặc định");
        yield 20;
    }
};
~~~

**Khi dùng:** ánh xạ enum/trạng thái sang một kết quả rõ ràng. **Cần nhớ:** các nhánh phải bao phủ những đầu vào có thể có; dùng `default` khi thực sự phù hợp, nhưng với enum, việc liệt kê đầy đủ các hằng đôi khi giúp trình biên dịch phát hiện trường hợp mới chưa xử lý. Tránh biến switch expression thành khối nghiệp vụ quá dài.

### 3.2. Text block — chuỗi nhiều dòng dễ đọc hơn

Text block được chuẩn hóa ở **Java 15**. Nó hữu ích với JSON mẫu, SQL nhiều dòng, nội dung HTML hoặc thông báo có bố cục. Dấu mở và đóng là ba dấu ngoặc kép.

~~~java
String query = """
        SELECT id, full_name, email
        FROM students
        WHERE active = true
        ORDER BY full_name
        """;
~~~

Text block xử lý xuống dòng và thụt lề theo các quy tắc của Java; hãy quan sát kết quả thực tế khi khoảng trắng có ý nghĩa. **Không ghép trực tiếp dữ liệu người dùng vào câu SQL**: dù viết SQL bằng text block, vẫn phải dùng prepared statement và tham số ràng buộc. Với JSON động, dùng thư viện serialize thay vì tự nối chuỗi.

### 3.3. Record — biểu diễn dữ liệu với ít mã lặp

Record được chuẩn hóa ở **Java 16** và rất phù hợp để mô tả dữ liệu truyền qua các lớp, kết quả truy vấn, message hoặc DTO.

~~~java
import java.util.Objects;

public record StudentResponse(long id, String fullName) {
    public StudentResponse {
        if (id <= 0) {
            throw new IllegalArgumentException("id phải dương");
        }
        Objects.requireNonNull(fullName, "fullName");
        if (fullName.isBlank()) {
            throw new IllegalArgumentException("Tên không được trống");
        }
    }
}
~~~

Trình biên dịch cung cấp constructor, accessor `id()` và `fullName()`, `equals()`, `hashCode()`, `toString()`. Record là kiểu dữ liệu có trạng thái cố định qua các component: không có setter để thay đổi field sau khi tạo.

Tuy nhiên **record không bảo đảm bất biến sâu**. Nếu một component tham chiếu đến danh sách hoặc đối tượng có thể thay đổi, bên ngoài vẫn có thể sửa nội dung đối tượng đó. Hãy sao chép phòng vệ khi cần:

~~~java
import java.util.List;

public record ClassRoom(String name, List<String> students) {
    public ClassRoom {
        students = List.copyOf(students);
    }
}
~~~

Ở đây `List.copyOf` tạo danh sách không sửa được qua tham chiếu được lưu trong record (đồng thời từ chối phần tử `null`). Nếu phần tử bên trong là đối tượng mutable, cần thêm giải pháp phù hợp để bảo vệ chính các phần tử.

**Không dùng record một cách máy móc** cho entity JPA vốn có yêu cầu đặc thù về định danh, vòng đời và khả năng thay đổi trạng thái. Trong các dự án ORM, record thường thích hợp hơn ở DTO/projection khi framework và phiên bản thư viện đang dùng hỗ trợ.

### 3.4. Pattern matching cho instanceof — kiểm tra và lấy kiểu trong một bước

Được chuẩn hóa ở **Java 16**, pattern matching cho `instanceof` tránh ép kiểu lặp lại.

~~~java
static String describe(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return "Chuỗi hợp lệ: " + text;
    }
    if (value instanceof Integer count && count > 0) {
        return "Số dương: " + count;
    }
    return "Giá trị khác";
}
~~~

Biến `text` chỉ có thể được sử dụng tại vị trí mà trình biên dịch biết phép kiểm tra kiểu đã thành công. Đây là *flow scoping*; không nên nghĩ biến pattern luôn có phạm vi giống biến khai báo đầu khối.

**Phân biệt rõ:** pattern matching trong `switch` ở JDK 17 vẫn là tính năng **preview**, chưa phải cú pháp ổn định của Java 17. Bài học chuẩn Java 17 nên dùng `instanceof` pattern như trên và switch expression với case thông thường. Pattern matching for switch chỉ được chuẩn hóa về sau, ở Java 21.

### 3.5. Sealed class và sealed interface — kiểm soát tập kiểu con

Sealed types được chuẩn hóa ở **Java 17**. Chúng thể hiện rằng một interface hoặc class chỉ cho phép một tập kiểu con đã xác định. Đây là công cụ phù hợp để biểu diễn kết quả xử lý và các trạng thái nghiệp vụ có số trường hợp hữu hạn.

~~~java
public sealed interface PaymentResult
        permits PaymentAccepted, PaymentRejected {
}

record PaymentAccepted(String transactionId) implements PaymentResult {
}

record PaymentRejected(String reason) implements PaymentResult {
}
~~~

Kiểu kế thừa trực tiếp một sealed type phải chọn định hướng thích hợp: `final`, `sealed` hoặc `non-sealed` (record ngầm định là `final`). Các kiểu con được cho phép phải nằm trong cùng named module; nếu sử dụng unnamed module thì phải cùng package.

Sealed types phát huy tác dụng khi kết hợp với record để biểu diễn các phương án của một kết quả:

~~~java
static String message(PaymentResult result) {
    if (result instanceof PaymentAccepted accepted) {
        return "Đã thanh toán: " + accepted.transactionId();
    }
    if (result instanceof PaymentRejected rejected) {
        return "Từ chối: " + rejected.reason();
    }
    throw new IllegalStateException("Trường hợp chưa hỗ trợ");
}
~~~

**Khi dùng:** tập kết quả, lệnh hoặc trạng thái được thiết kế có giới hạn rõ. **Không nên dùng:** hierarchy là API mở cho plugin hoặc bên thứ ba kế thừa tùy ý. Sealed type làm thay đổi hợp đồng mở rộng API, vì thế cần cân nhắc khi thiết kế thư viện công khai.

### 3.6. Một số API mới đáng chú ý trong giai đoạn này

| Tính năng/API | Xuất hiện | Ý nghĩa thực hành |
|---|---|---|
| `List.of`, `Set.of`, `Map.of` | Java 9 | Khởi tạo collection không sửa được qua API |
| `List.copyOf`, `Set.copyOf`, `Map.copyOf` | Java 10 | Sao chép thành collection không sửa được |
| `String.isBlank()`, `String.strip()` | Java 11 | Xử lý chuỗi theo ký tự khoảng trắng Unicode phù hợp hơn nhiều trường hợp |
| `Files.readString()`, `Files.writeString()` | Java 11 | Đọc và ghi file văn bản thuận tiện |
| `Stream.toList()` | Java 16 | Thu kết quả stream thành danh sách không sửa được |
| `RandomGenerator` và các API liên quan | Java 17 | Giao diện thống nhất hơn cho nhiều bộ sinh số giả ngẫu nhiên |

Ví dụ:

~~~java
List<String> activeNames = names.stream()
        .filter(name -> !name.isBlank())
        .map(String::strip)
        .toList();
~~~

Danh sách do `Stream.toList()` trả về **không cho phép thao tác sửa đổi**. Đừng mặc định kết quả `Collectors.toList()` có cùng hợp đồng; đặc tả của collector này không cam kết một kiểu cụ thể hoặc tính mutable. Khi cần danh sách có thể sửa, hãy thể hiện rõ:

~~~java
List<String> editable = names.stream()
        .filter(name -> !name.isBlank())
        .collect(java.util.stream.Collectors.toCollection(java.util.ArrayList::new));
~~~

## 4. Ví dụ tổng hợp có thể chạy trên Java 17

Ví dụ sau kết hợp Stream từ Java 8, `var` từ Java 10, switch expression, record, sealed interface và pattern matching. Lưu toàn bộ thành file **LearningPathDemo.java**:

~~~java
import java.util.List;

public class LearningPathDemo {
    sealed interface EnrollmentResult permits Accepted, Rejected {}

    record Accepted(String student, String course) implements EnrollmentResult {}

    record Rejected(String reason) implements EnrollmentResult {}

    static EnrollmentResult enroll(String student, String course) {
        if (student == null || student.isBlank()) {
            return new Rejected("Tên học viên không hợp lệ");
        }
        return new Accepted(student.strip(), course);
    }

    static String describe(EnrollmentResult result) {
        if (result instanceof Accepted accepted) {
            return "Đăng ký thành công: " + accepted.student()
                    + " -> " + accepted.course();
        }
        if (result instanceof Rejected rejected) {
            return "Đăng ký thất bại: " + rejected.reason();
        }
        throw new IllegalStateException("Kết quả không xác định");
    }

    public static void main(String[] args) {
        var students = List.of("An", " ", "Binh", "Chi");

        List<String> validStudents = students.stream()
                .filter(name -> !name.isBlank())
                .toList();

        String course = switch (validStudents.size()) {
            case 0 -> "Chưa có học viên";
            case 1 -> "Java 8";
            default -> "Java 17";
        };

        for (String student : validStudents) {
            System.out.println(describe(enroll(student, course)));
        }
        System.out.println(describe(enroll(" ", course)));
    }
}
~~~

Chạy trong thư mục chứa file bằng JDK 17:

~~~shell
java -version
javac --release 17 LearningPathDemo.java
java LearningPathDemo
~~~

Kết quả dự kiến:

~~~text
Đăng ký thành công: An -> Java 17
Đăng ký thành công: Binh -> Java 17
Đăng ký thành công: Chi -> Java 17
Đăng ký thất bại: Tên học viên không hợp lệ
~~~

Trong ví dụ này, các biểu thức mới giảm mã lặp và giúp thể hiện ý định rõ ràng. Dù vậy, các quy tắc xử lý đầu vào, phân chia trách nhiệm giữa các hàm và kiểm thử vẫn quan trọng như trước.

## 5. Java 17 thay đổi gì ở cách chạy và triển khai ứng dụng?

Học Java 17 không dừng ở cú pháp. Nhiều vấn đề khi nâng cấp dự án đến từ **JDK runtime, thư viện phụ thuộc và công cụ build**.

### 5.1. Tính đóng gói mạnh hơn với JDK internals

Java 17 đưa vào **strong encapsulation** cho các thành phần nội bộ của JDK (JEP 403). Ứng dụng và thư viện không nên phụ thuộc vào các class nội bộ như `sun.*` hoặc truy cập phản chiếu trái phép vào thành viên không mở của module JDK.

- Code sử dụng API Java công khai thường dễ nâng cấp hơn code dựa vào API nội bộ.
- Framework hoặc thư viện reflection cũ có thể gặp lỗi `InaccessibleObjectException`; cần ưu tiên cập nhật dependency lên bản hỗ trợ Java 17.
- Tham số `--add-opens` có thể hỗ trợ chuyển tiếp cho một số trường hợp, nhưng cần giới hạn phạm vi và có kế hoạch loại bỏ. Tùy chọn `--illegal-access` của các bản JDK trước không còn là giải pháp kích hoạt lại kiểu truy cập này trên Java 17.

Ví dụ dạng tham số chuyển tiếp khi đã xác định chính xác thư viện cần quyền truy cập:

~~~shell
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Không thêm tham số này vào mọi ứng dụng theo thói quen. Chỉ dùng sau khi đã đọc lỗi, biết module/package nào cần mở, và xác định thư viện nào cần cập nhật.

### 5.2. Thư viện từng đi kèm JDK có thể không còn sẵn

Một số thành phần phổ biến trong ứng dụng Java 8 đã bị tách hoặc loại khỏi JDK ở các mốc trước Java 17:

- Các module Java EE/CORBA thuộc JDK bị loại khỏi Java SE từ Java 11; ví dụ ứng dụng cũ dùng JAXB có thể phải khai báo dependency độc lập.
- JavaFX không còn được đóng gói trong JDK tiêu chuẩn từ Java 11; ứng dụng desktop cần cấu hình OpenJFX hoặc runtime phù hợp.
- Nashorn JavaScript engine bị loại khỏi JDK từ Java 15; nếu phụ thuộc vào nó, cần giải pháp thay thế đã được đánh giá.

Đây là **vấn đề tương thích thực tế khi nâng cấp từ 8/11**, không phải lý do để tiếp tục dùng API đã bị loại.

### 5.3. Class file version và tương thích nhị phân

| Java dùng để biên dịch | Major class file version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |

JVM Java 8 hoặc 11 không thể chạy trực tiếp class file được biên dịch cho Java 17. Lỗi thường gặp là `UnsupportedClassVersionError`. Trong nhiều trường hợp, JDK mới có thể chạy bytecode được biên dịch cho JDK cũ, nhưng ứng dụng vẫn có thể lỗi do API đã bị loại, thay đổi hành vi hoặc dependency không tương thích. **Tương thích bytecode không đồng nghĩa với tương thích toàn bộ ứng dụng.**

Để quy định đích biên dịch bằng JDK hỗ trợ, dùng:

~~~shell
javac --release 17 MyClass.java
~~~

`--release` đồng bộ mức ngôn ngữ, class file và tập API Java SE có sẵn cho bản đích; cách này rõ nghĩa hơn việc chỉ chỉnh `-source` và `-target` khi xây dựng cho một Java release cũ hơn JDK đang dùng. Lưu ý: `--release` không kiểm tra tương thích của mọi thư viện ngoài JDK hoặc cấu hình runtime.

### 5.4. Công cụ build, framework và runtime

Trong dự án thực tế, cần phân biệt:

1. **JDK chạy build** (Maven/Gradle daemon, plugin).
2. **JDK hoặc release đích để biên dịch**.
3. **JDK trên môi trường chạy** (server, container, CI).

Chúng có thể khác nhau và phải được cấu hình có chủ đích. Ví dụ với Maven Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

Với Gradle có thể mô tả JDK biên dịch qua Java toolchain:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Mỗi công cụ build, plugin, annotation processor và framework đều có ma trận tương thích riêng. Trước khi nâng cấp, phải xác nhận **phiên bản thực tế** đang dùng tương thích Java 17. Ví dụ, Spring Boot 3 lấy Java 17 làm baseline và chuyển sang các API Jakarta EE; việc đổi `javax.*` sang `jakarta.*` trong trường hợp này gắn với thế hệ framework/Jakarta EE, **không phải cú pháp Java 17 tự động yêu cầu**.

### 5.5. Quan sát và hiệu năng

Java 17 tiếp tục có các công cụ và cơ chế quan sát hiện đại của JVM. Bạn nên biết:

- G1 là garbage collector mặc định trong các cấu hình HotSpot phổ biến của JDK 17; các GC khác có thể phù hợp theo workload và bản phân phối.
- Unified JVM logging dùng tùy chọn `-Xlog`, ví dụ `-Xlog:gc*` để phân tích GC.
- Java Flight Recorder (JFR) và Java Mission Control là những công cụ hữu ích để điều tra hiệu năng, độ trễ, cấp phát bộ nhớ và hoạt động ứng dụng.
- Không tối ưu GC dựa trên lời khuyên chung chung. Cần đo latency, throughput, heap, pause và tải thực tế trước khi điều chỉnh.

Java 17 cũng không bảo đảm mã tự động nhanh hơn chỉ vì nâng cấp số phiên bản. Hiệu năng phụ thuộc ứng dụng, thư viện, cài đặt JVM và điều kiện đo.

## 6. Lộ trình thực hành: từ người đã biết Java 8/11 đến làm việc tốt với Java 17

Đây là lộ trình dựa trên **năng lực cần đạt**, không gắn cứng số ngày học.

### Chặng 1 — Củng cố phần kiến thức không đổi

Tự xây dựng một ứng dụng nhỏ có collection, stream, exception, thời gian, API HTTP hoặc thao tác file. Mục tiêu là bảo đảm bạn hiểu bản chất dữ liệu, hợp đồng API và quản lý lỗi trước khi áp dụng cú pháp mới.

**Bài tập:** Xử lý danh sách đơn hàng có thời điểm tạo, trạng thái, số tiền; dùng Stream để tính doanh thu theo tháng và nhóm theo trạng thái. Kiểm tra trường hợp danh sách rỗng, ngày giờ khác múi giờ và giá trị không hợp lệ.

### Chặng 2 — Viết lại những đoạn mã thích hợp với Java 17

Lần lượt luyện:

1. Đổi switch statement thuần ánh xạ thành switch expression.
2. Đổi những lớp dữ liệu DTO đơn giản thành record khi thỏa hợp đồng dữ liệu.
3. Đổi kiểm tra `instanceof` và ép kiểu thủ công thành pattern matching.
4. Dùng sealed interface để thể hiện những kết quả xử lý có tập trường hợp hữu hạn.
5. Dùng text block cho chuỗi nhiều dòng thực sự cần định dạng.
6. So sánh `Stream.toList()` với việc thu thập vào danh sách mutable để chọn đúng hợp đồng.

**Bài tập:** Thiết kế API trả kết quả nhập học: `Accepted`, `Rejected`, `PendingReview`. Sử dụng sealed interface và các record, kiểm tra đầu vào, chuyển kết quả thành thông báo. Mở rộng thêm trạng thái để quan sát những vị trí phải cập nhật logic xử lý.

### Chặng 3 — Hiểu migration từ Java 8/11

Tập phân tích một dự án cũ (hoặc tạo dự án mẫu đại diện) với quy trình:

1. **Chụp đường cơ sở:** ghi nhận JDK và phiên bản framework/dependency, trạng thái build, test, số lỗi hiện tại và yêu cầu triển khai.
2. **Kiểm tra phụ thuộc:** thư viện sử dụng JDK internals, reflection, annotation processing, API JAXB/JavaFX/Nashorn hoặc phiên bản framework quá cũ.
3. **Nâng JDK và build plugin theo ma trận hỗ trợ:** thống nhất compiler release và runtime; tránh để CI dùng JDK khác local.
4. **Biên dịch, chạy kiểm thử và rà lỗi runtime:** chú ý `ClassNotFoundException`, `NoClassDefFoundError`, `InaccessibleObjectException`, `UnsupportedClassVersionError`.
5. **Kiểm thử tích hợp:** database driver, HTTP/TLS, serialization, timezone, locale, message broker và các chức năng thực tế.
6. **Đo lại hiệu năng, đóng gói và triển khai:** kiểm thử container image, startup, memory, throughput và log; duy trì cách quay lại phiên bản cũ nếu phát sinh vấn đề.

Để tìm phụ thuộc vào API nội bộ JDK, có thể tham khảo công cụ `jdeps`:

~~~shell
jdeps --jdk-internals app.jar
~~~

Kết quả là tín hiệu để điều tra thêm; không thể thay thế kiểm thử runtime hoặc quét toàn bộ hành vi reflection động.

### Chặng 4 — Đưa kiến thức vào mã nghiệp vụ

Viết một module nhỏ gồm lớp nhận request, xử lý, trả response và kiểm thử. Nên dùng:

- Record cho request/response khi hợp đồng dữ liệu phù hợp.
- Sealed type cho kết quả có số trạng thái được kiểm soát.
- Switch expression cho phép ánh xạ đơn giản.
- Stream API khi cần biến đổi tập dữ liệu; vòng lặp thường vẫn hợp lý cho logic phức tạp có side effect.
- API chuẩn Java 11+ (HTTP Client, Files, String) khi đáp ứng yêu cầu.

Đừng refactor toàn bộ codebase chỉ để “sử dụng tính năng Java 17”. Việc chuyển đổi nên cải thiện tên gọi, giảm mã lặp, làm rõ hợp đồng dữ liệu hoặc giảm nguy cơ lỗi cụ thể.

## 7. Những nhầm lẫn cần tránh trong quá trình học

| Nhầm lẫn | Hiểu đúng |
|---|---|
| “Mọi tính năng hiện đại đều xuất hiện lần đầu ở Java 17.” | Java 17 là mốc LTS tích lũy nhiều thay đổi từ Java 9 đến 17; cần biết phiên bản chuẩn hóa của từng tính năng. |
| “Dùng Java 17 là phải chuyển tất cả class sang record.” | Record thích hợp cho mô hình dữ liệu cố định; domain entity có vòng đời hoặc state thay đổi có thể vẫn cần class thường. |
| “Record bất biến tuyệt đối.” | Record bảo vệ tham chiếu component khỏi bị gán lại, nhưng object tham chiếu vẫn có thể mutable. |
| “`var` làm Java thành ngôn ngữ kiểu động.” | Java vẫn kiểm tra kiểu tĩnh ở compile time. |
| “Sealed interface luôn thay thế được interface thường.” | Sealed phù hợp hierarchy đóng; interface mở vẫn đúng khi cần bên thứ ba mở rộng. |
| “`switch` pattern matching là tính năng ổn định của Java 17.” | Trong Java 17 nó là preview; chỉ `instanceof` pattern matching đã được chuẩn hóa. |
| “`Stream.toList()` cho kết quả có thể thêm/xóa phần tử.” | Danh sách trả về không thể sửa qua API. |
| “Biên dịch được thì ứng dụng đã tương thích Java 17.” | Cần kiểm tra runtime, reflection, thư viện, tích hợp và hiệu năng. |
| “Bất cứ dự án Java 17 nào cũng cần `module-info.java`.” | Dự án classpath vẫn được hỗ trợ; module hóa là quyết định kiến trúc riêng. |
| “Nâng lên Java 17 tự động yêu cầu đổi mọi `javax` thành `jakarta`.” | Phụ thuộc framework và phiên bản Jakarta EE được sử dụng, không phải thay đổi ngôn ngữ tự thân. |
| “Java 17 có virtual thread ổn định.” | Virtual thread được chuẩn hóa ở Java 21; không dùng như API ổn định sẵn có của Java 17. |

Các ví dụ Java 17 nên tránh dựa vào tính năng preview chỉ để làm code ngắn hơn. Preview có thể cần cờ biên dịch/chạy riêng và hợp đồng ngôn ngữ còn có thể thay đổi.

## 8. Khi nào nên tiếp tục từ Java 17 sang Java 21/25?

Java 17 là điểm học rất tốt để hiểu một bước chuyển quan trọng của ngôn ngữ và ecosystem. Khi đã nắm vững, bạn có thể tiếp tục đến các phiên bản LTS mới hơn theo yêu cầu công việc:

- **Java 21:** tìm hiểu virtual threads, pattern matching for switch ở dạng ổn định, record patterns và sequenced collections.
- **Java 25:** tìm hiểu các thay đổi ổn định mới có trong JDK 25 theo tài liệu chính thức và kiểm tra ma trận tương thích của dự án trước khi nâng cấp.

Đừng mang cú pháp hoặc API chỉ có từ Java 21/25 vào ví dụ được yêu cầu chạy trên Java 17. Đồng thời, **LTS là chính sách hỗ trợ gắn với từng nhà cung cấp/bản phân phối**, nên hãy kiểm tra thời hạn cập nhật bảo mật và hỗ trợ thực tế thay vì suy luận chỉ từ nhãn LTS.

Khi lập lộ trình trong đội nhóm, cần trả lời ba câu: **hệ thống cần chạy trên phiên bản nào, người học cần thành thạo tập tính năng nào, và bản phân phối JDK nào đang được hỗ trợ?** Ba câu trả lời có thể khác nhau.

## 9. Tự đánh giá sau bài học

Bạn đã đạt mục tiêu của bài khi có thể:

1. Nói rõ những kiến thức Java 8 vẫn là nền tảng của Java 17 và những cải tiến đáng học trong Java 9–11.
2. Chỉ đúng phiên bản chuẩn hóa của switch expression, text block, record, `instanceof` pattern matching và sealed types.
3. Viết được code Java 17 dùng các tính năng trên, biên dịch và chạy bằng JDK 17 mà không cần bật preview.
4. Giải thích sự khác nhau giữa DTO dạng record, entity có state thay đổi, hierarchy mở và sealed hierarchy.
5. Nhận biết giới hạn của `var`, record và `Stream.toList()` mà không dựa vào phỏng đoán.
6. Nhận diện các rủi ro nâng cấp từ Java 8/11: internal JDK APIs, thư viện đã tách khỏi JDK, compiler release, dependency, reflection và runtime.
7. Lập được một kế hoạch nâng cấp có build, test, kiểm thử tích hợp, đo vận hành và phương án quay lại phiên bản cũ.
8. Biết tính năng nào thuộc Java 21 trở lên, để không đưa nhầm vào dự án Java 17.

### Câu hỏi kiểm tra tư duy

**Câu 1.** Một API trả về một bộ dữ liệu gồm ID và tên người dùng, không yêu cầu sửa từng field sau khi tạo. Nên cân nhắc record hay class thường?

**Gợi ý:** Record thường phù hợp cho DTO dữ liệu cố định, nhưng phải xem xét validation, cấu trúc dữ liệu lồng nhau và yêu cầu framework.

**Câu 2.** Vì sao ứng dụng compile được trên Java 17 nhưng lỗi khi khởi động với `InaccessibleObjectException`?

**Gợi ý:** Dependency có thể dùng reflection truy cập thành viên nội bộ JDK; ưu tiên nâng cấp thư viện và kiểm tra yêu cầu mở module.

**Câu 3.** Vì sao không thể sử dụng `Stream.toList()` trong source code bắt buộc biên dịch cho Java 11?

**Gợi ý:** API này có từ Java 16. Biên dịch với `--release 11` bảo vệ bạn khỏi việc vô tình dùng API Java SE mới hơn release đích.

**Câu 4.** Khi nào sealed interface là lựa chọn kém phù hợp?

**Gợi ý:** Khi cần cho phép hệ thống plugin hoặc người dùng thư viện tự triển khai các kiểu con mới ngoài danh sách bạn kiểm soát.

**Câu 5.** Có thể dùng record patterns, virtual threads hoặc pattern matching for switch ổn định ngay trong Java 17 không?

**Gợi ý:** Không. Những khả năng này thuộc mốc phiên bản sau; đặc biệt pattern matching for switch ở Java 17 chỉ là preview.

## 10. Tài liệu tham khảo để học tiếp

- [dev.java — Learn Java](https://dev.java/learn/): tài liệu thực hành về ngôn ngữ, API và công cụ Java.
- [OpenJDK — JDK 17](https://openjdk.org/projects/jdk/17/): danh sách tính năng/JEP của Java 17, có thể theo liên kết đến JEP gốc.
- [Oracle — JDK 17 Migration Guide](https://docs.oracle.com/en/java/javase/17/migrate/): hướng dẫn các vấn đề tương thích khi nâng cấp sang JDK 17.
- [Oracle — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/): xác minh API thực sự có trong Java 17 trước khi viết code.

**Định hướng tiếp theo:** Hãy xem Java 17 là nền tảng để học cách lựa chọn công cụ ngôn ngữ đúng mục đích và nâng cấp hệ thống có kiểm chứng. Nền tảng Java 8/11 vẫn được dùng thường xuyên; Java 17 giúp bạn biểu đạt mô hình dữ liệu rõ ràng hơn và hiểu sâu hơn các ràng buộc của JVM hiện đại.
