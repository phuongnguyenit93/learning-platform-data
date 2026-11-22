# Trình tự học Java 17: kiến thức nền và tiêu chí hoàn thành

Java 17 là một phiên bản Java LTS (Long-Term Support) được nhiều dự án sử dụng làm mốc tương thích. Để học hiệu quả, cần phân biệt **học ngôn ngữ Java**, **hiểu thư viện chuẩn Java SE**, **sử dụng công cụ phát triển**, rồi mới **xây dựng và kiểm thử ứng dụng**. Tài liệu này đưa ra thứ tự học từ nền tảng đến khả năng tự triển khai một chương trình Java 17 hoàn chỉnh.

Nội dung tập trung vào những kiến thức vẫn hữu ích khi phát triển phần mềm hiện nay. Các tính năng xuất hiện ở phiên bản Java mới hơn có thể được học sau, nhưng không được nhầm là tính năng sẵn có trong Java 17.

## 1. Đích đến của lộ trình

Sau khi hoàn thành, người học cần tự mình:

1. Chuẩn bị môi trường JDK 17, biên dịch, chạy và gỡ lỗi chương trình; hiểu quan hệ giữa mã nguồn, bytecode và JVM.
2. Viết chương trình có cấu trúc rõ ràng bằng lớp, đối tượng, interface, kiểu tổng quát (generics), ngoại lệ và các API chuẩn thiết yếu.
3. Chọn cấu trúc dữ liệu phù hợp; sử dụng collection, lambda và Stream khi chúng làm mã dễ đọc và dễ kiểm tra hơn.
4. Xử lý dữ liệu nhập, ngày giờ, tệp và tài nguyên bên ngoài một cách có kiểm soát; không làm mất lỗi hoặc bỏ quên tài nguyên.
5. Dùng đúng những tính năng ổn định có trong Java 17, đặc biệt là record, sealed class/interface, switch expression, text block và pattern matching cho `instanceof`.
6. Viết unit test, đọc thông báo lỗi, dùng Git và một công cụ build như Maven hoặc Gradle; bàn giao được chương trình người khác có thể chạy lại.

**Sản phẩm đầu ra:** một ứng dụng Java 17 quy mô nhỏ, có mã nguồn, cách chạy, kiểm thử tự động và danh sách các tình huống đã xử lý. Không cần học framework web trước khi đạt các nền tảng này.

## 2. Kiến thức nền cần có

### 2.1. Nền tảng tối thiểu trước khi bắt đầu

| Nhóm kiến thức | Cần hiểu được gì? | Cách tự kiểm tra |
|---|---|---|
| Tư duy lập trình | Biến, kiểu dữ liệu, điều kiện, vòng lặp, hàm và giá trị trả về | Diễn đạt được thuật toán tìm số lớn nhất trong danh sách; tự viết mã giả |
| Dữ liệu | Số, chuỗi, boolean, mảng/danh sách; khác biệt giữa giá trị và tham chiếu | Dự đoán được kết quả khi sửa một đối tượng qua hai biến cùng tham chiếu |
| Logic cơ bản | AND, OR, NOT, so sánh, điều kiện biên | Đặt được các trường hợp thử cho một hàm kiểm tra đầu vào |
| Máy tính và terminal | Thư mục, đường dẫn, tệp, lệnh chạy chương trình | Di chuyển đến thư mục dự án, liệt kê tệp và thực thi lệnh biên dịch |
| Kỹ năng đọc tài liệu | Phân biệt ví dụ, API contract, tham số, kiểu trả về và ngoại lệ | Tra cứu được một phương thức trong Java 17 API Documentation |

Người hoàn toàn mới có thể học các khái niệm lập trình song song với chặng đầu. Người đã biết một ngôn ngữ khác có thể bắt đầu trực tiếp từ cú pháp và mô hình đối tượng của Java.

### 2.2. Chuẩn bị môi trường Java 17

- Cài **JDK 17** từ một bản phân phối còn được nhà cung cấp hỗ trợ, chẳng hạn Eclipse Temurin, Oracle JDK hoặc một OpenJDK distribution phù hợp với dự án.
- Kiểm tra cả `java -version` và `javac -version`; hai lệnh phải trỏ đến JDK/JVM dự định dùng. Nếu máy cài nhiều JDK, kiểm tra `JAVA_HOME`, `PATH` và cấu hình JDK trong IDE.
- Chọn một IDE có hỗ trợ Java (IntelliJ IDEA, Eclipse hoặc VS Code với Java extensions). Tập dùng breakpoint, step into, xem biến và call stack.
- Cài Git và làm quen với `status`, `add`, `commit`, `diff`. Chọn **một** công cụ build cho dự án thực hành: Maven **hoặc** Gradle.
- Đặt mức ngôn ngữ/API mục tiêu thành **17**. Khi dùng `javac`, tùy chọn `--release 17` giúp kiểm soát cả cú pháp lẫn API có sẵn ở bản phát hành mục tiêu. Với Maven/Gradle, cấu hình mức release hoặc toolchain tương ứng và kiểm tra lại JDK chạy chương trình.

Thử chương trình đầu tiên trong tệp `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Java 17 ready");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 Hello.java
java Hello
```

Kết quả cần xuất hiện: `Java 17 ready`. Nếu không chạy được, xử lý vấn đề JDK, tên lớp, tên tệp hoặc thư mục chạy trước khi học tiếp.

## 3. Trình tự học đề xuất

Đây là **thứ tự phụ thuộc kiến thức**, không phải lịch cố định theo số ngày. Có thể rút ngắn chặng đã thành thạo, nhưng cần thực hiện bài chứng minh đầu ra trước khi chuyển tiếp.

| Chặng | Nội dung trọng tâm | Bài thực hành để qua chặng |
|---|---|---|
| **0. Môi trường và cách Java chạy** | JDK, JVM, bytecode, `javac`, `java`, classpath, cấu trúc dự án, Git | Biên dịch và chạy một lớp bằng terminal, gỡ lỗi một lỗi đơn giản trong IDE |
| **1. Cú pháp và luồng điều khiển** | Primitive/reference type, biến, toán tử, ép kiểu, `String`, toán tử so sánh, `if`, `switch`, vòng lặp, phương thức, mảng | Viết ứng dụng nhập/kiểm tra dữ liệu; xử lý trường hợp thiếu, rỗng, không hợp lệ |
| **2. Mô hình đối tượng** | Class, object, constructor, access modifier, encapsulation, `static`, kế thừa, interface, polymorphism, `enum`, `record` | Xây dựng các lớp mô tả một miền nghiệp vụ nhỏ và phân chia trách nhiệm |
| **3. Collections và generics** | `List`, `Set`, `Map`, duyệt, sắp xếp, `Comparator`, `equals`/`hashCode`, generics, tính bất biến | Quản lý tập đối tượng, tìm kiếm, lọc, thống kê và xử lý dữ liệu trùng |
| **4. Lập trình hàm vừa đủ** | Lambda, method reference, functional interface, Stream, `Optional`, cách chọn vòng lặp hay Stream | Xây dựng thao tác lọc, nhóm, đếm, sắp xếp với dữ liệu thật; giải thích được pipeline |
| **5. Làm việc với môi trường** | Exception, `try-with-resources`, `Path`/`Files`, UTF-8, `java.time`, HTTP client cơ bản | Đọc/ghi tệp, xử lý lỗi I/O, thao tác ngày hạn và phân biệt lỗi người dùng với lỗi hệ thống |
| **6. Chất lượng mã và công cụ** | Unit test, JUnit 5, debugger, logging, Maven/Gradle, dependency, package, Git, đọc stack trace | Có bài kiểm thử cho nghiệp vụ và ca biên; chạy build/test được từ terminal |
| **7. JVM và đồng thời căn bản** | Heap/stack ở mức khái niệm, garbage collection, thread, `ExecutorService`, race condition, đồng bộ và đóng tài nguyên | Giải thích một lỗi dữ liệu dùng chung; triển khai tác vụ độc lập với executor khi có nhu cầu |
| **8. Tính năng ổn định của Java 17 và tích hợp** | Record, sealed types, switch expression, text block, `instanceof` pattern matching; phối hợp tất cả kiến thức trên | Hoàn thành ứng dụng cuối khóa và giải thích vì sao dùng từng cấu trúc |

### Chặng 1: Cú pháp trước, mẹo viết ngắn sau

Học cách khai báo giá trị, gọi phương thức và phân nhánh trước khi tối ưu câu lệnh. Cần phân biệt:

- `int`, `long`, `double`, `boolean` là primitive; `String`, mảng và các đối tượng khác được truy cập thông qua tham chiếu.
- `==` trên object so sánh tham chiếu; dùng `equals()` khi cần so sánh bằng nhau theo nội dung/giá trị mà kiểu dữ liệu định nghĩa.
- `String` bất biến. Khi nối chuỗi nhiều lần trong vòng lặp, cân nhắc `StringBuilder`.
- `null` biểu thị không có tham chiếu; cần xác định hợp đồng đầu vào thay vì để `NullPointerException` xuất hiện ngẫu nhiên.
- `var` hỗ trợ suy luận kiểu cho biến cục bộ có giá trị khởi tạo; kiểu vẫn tĩnh và không biến thành kiểu động.

Ví dụ bài luyện: viết phương thức tính tổng các giá trị hợp lệ trong một mảng, tự quyết định hành vi với mảng rỗng, giá trị âm và nguy cơ tràn số.

### Chặng 2: Thiết kế đối tượng có trách nhiệm rõ ràng

Tạo lớp để mô tả **trạng thái và hành vi gắn với nhau**, không đơn thuần gom mọi thao tác vào một lớp tiện ích. Một lớp quản lý công việc có thể kiểm tra tên, ngày hạn và trạng thái; lớp phụ trách lưu tệp sẽ xử lý I/O. Các thao tác không cùng trách nhiệm không cần đặt chung một nơi.

Học interface để tách hợp đồng khỏi cách triển khai, enum cho một tập trạng thái hữu hạn, record cho dữ liệu có các thành phần được công bố rõ ràng và sealed type khi muốn kiểm soát tập kiểu con. Kế thừa chỉ nên sử dụng khi thực sự có quan hệ **is-a** và có thể thay thế được theo hợp đồng của kiểu cha; nhiều bài toán phù hợp hơn với composition.

### Chặng 3: Chọn cấu trúc dữ liệu theo hành vi

| Nhu cầu | Lựa chọn thường gặp | Cần chú ý |
|---|---|---|
| Danh sách có thứ tự, cho phép phần tử trùng | `List<T>` | Chi phí tìm kiếm, chèn/xóa thay đổi theo implementation |
| Tập phần tử không trùng | `Set<T>` | Tính đúng đắn của `equals()` và `hashCode()` |
| Ánh xạ khóa → giá trị | `Map<K,V>` | Khóa phải ổn định khi đang nằm trong map |
| Sắp xếp theo tiêu chí | `Comparator<T>` | Phải xác định thứ tự và cách xử lý giá trị bằng nhau |
| Dữ liệu không được sửa qua API trả về | `List.copyOf(...)`, `List.of(...)` | Phân biệt collection không sửa được với đối tượng phần tử có thể thay đổi |

Biết dùng generics (`List<Task>` thay vì raw `List`), duyệt collection an toàn và tính toán độ phức tạp ở mức cơ bản. Không cần học thuộc từng implementation; cần giải thích vì sao cấu trúc được chọn phù hợp với truy vấn của bài.

### Chặng 4: Stream là công cụ biến đổi dữ liệu

Trình tự hợp lý là: viết được vòng lặp → viết được lambda → hiểu `filter`, `map`, `sorted`, `collect` và phép kết thúc như `count` → mới học `groupingBy` hoặc kỹ thuật nâng cao. Stream thường chỉ chạy khi có terminal operation và không nên sử dụng để giấu side effect.

`Optional<T>` thích hợp khi **API có thể không trả về kết quả**; không cần thay mọi field hay tham số có thể null bằng Optional. Khi dữ liệu có thể thiếu, quy định rõ cách trả về, báo lỗi hoặc dùng giá trị mặc định.

### Chặng 5: Tệp, ngày giờ và ngoại lệ

Sử dụng `Path` và `Files` cho thao tác tệp thông thường, `try-with-resources` cho tài nguyên cần đóng, và xác định encoding (thường là UTF-8). Đọc API contract để biết ngoại lệ nào có thể xảy ra; chỉ bắt lỗi ở nơi có thể phục hồi hoặc cung cấp thông tin có ích. Không nên `catch (Exception e)` rồi bỏ qua.

Ưu tiên `java.time`: `LocalDate` cho ngày, `LocalDateTime` cho ngày-giờ không mang múi giờ, `Instant` cho thời điểm trên trục thời gian và `ZonedDateTime` khi cần múi giờ. Tránh nhầm `LocalDateTime` là thời điểm toàn cầu. Với tiền tệ, học `BigDecimal` và quy tắc làm tròn phù hợp, thay vì dùng `double` để biểu diễn số tiền chính xác.

Khi học HTTP, `java.net.http.HttpClient` là API chuẩn có trong Java 17; cần nắm status code, timeout, lỗi mạng và cách đóng luồng khi có. Tự triển khai giao thức HTTP hoặc parser JSON/CSV đầy đủ không phải mục tiêu của chặng này; thư viện ngoài phải được khai báo dependency rõ ràng.

### Chặng 6–7: Test trước khi mở rộng, đồng thời sau khi hiểu trạng thái

Unit test nên kiểm tra kết quả quan sát được theo đầu vào, nhất là ranh giới: danh sách rỗng, ID trùng, chuỗi trắng, ngày vừa đến hạn, ngày quá hạn và lỗi đọc/ghi. Dùng debugger để tìm nguyên nhân, không chỉ sửa đến khi ví dụ mẫu chạy được.

Hiểu thread, task và executor trước khi chia sẻ dữ liệu giữa nhiều luồng. Biết rằng thay đổi trạng thái chung có thể gây race condition; học cách giảm shared mutable state, dùng công cụ đồng bộ khi thật sự cần và đóng `ExecutorService`/tài nguyên thích hợp. **Virtual threads là tính năng được hoàn thiện ở Java 21, không phải tính năng chuẩn của Java 17.** Phần nâng cao về concurrent programming chỉ nên triển khai trong dự án khi bài toán có yêu cầu tương ứng.

## 4. Những tính năng Java hiện đại cần nhận diện đúng phiên bản

Không phải tính năng nào được giới thiệu trong các bài viết về “Modern Java” cũng thuộc Java 17. Bảng sau nêu các tính năng đã ổn định **và sử dụng được khi đặt mục tiêu Java 17**:

| Tính năng | Có sẵn ổn định từ | Khi nào sử dụng |
|---|---|---|
| `var` cho biến cục bộ | Java 10 | Kiểu suy ra rõ ràng, giảm phần khai báo lặp |
| HTTP Client (`java.net.http`) | Java 11 | Thực hiện yêu cầu HTTP với API chuẩn |
| Switch expression | Java 14 | Chọn một giá trị theo các nhánh rõ ràng |
| Text block (`"""..."""`) | Java 15 | Chuỗi nhiều dòng như mẫu văn bản, SQL, JSON |
| Record | Java 16 | Kiểu mang dữ liệu, có accessor, `equals`, `hashCode`, `toString` theo thành phần |
| Pattern matching cho `instanceof` | Java 16 | Kiểm tra kiểu và lấy biến đã ép kiểu trong nhánh hợp lệ |
| `Stream.toList()` | Java 16 | Thu kết quả Stream thành danh sách không hỗ trợ sửa |
| Sealed class/interface | Java 17 | Giới hạn những lớp/interface được phép kế thừa, triển khai trực tiếp |

Ví dụ độc lập về pattern matching cho `instanceof`:

```java
static String describe(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        return "Chuoi dai " + text.length() + " ky tu";
    }
    return "Khong co chuoi hop le";
}
```

**Ranh giới phiên bản:** pattern matching cho `switch` ở Java 17 còn là *preview*, không nên đưa vào chương trình Java 17 chuẩn nếu chưa chủ động chọn và hiểu cơ chế preview. Virtual threads, sequenced collections và những cú pháp hoàn thiện ở Java sau 17 cũng nằm ngoài yêu cầu đầu ra. Mục tiêu là viết đúng chương trình chạy bằng Java 17, đồng thời giữ được cách tiếp cận có ích khi nâng cấp JDK.

## 5. Ví dụ tích hợp: danh sách công việc quá hạn

Ví dụ dưới đây kết hợp record, enum, switch expression, `java.time`, collection và Stream. Mã chạy được trên JDK 17 mà không cần thư viện bên ngoài.

Lưu vào `Main.java`:

```java
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;

public class Main {
    enum Status {
        TODO, IN_PROGRESS, DONE
    }

    record Task(long id, String title, LocalDate due, Status status) {
        Task {
            if (id <= 0) {
                throw new IllegalArgumentException("id must be positive");
            }
            title = Objects.requireNonNull(title, "title").trim();
            if (title.isBlank()) {
                throw new IllegalArgumentException("title must not be blank");
            }
            Objects.requireNonNull(due, "due");
            Objects.requireNonNull(status, "status");
        }

        boolean isOverdue(LocalDate today) {
            return status != Status.DONE && due.isBefore(today);
        }
    }

    static String statusLabel(Status status) {
        return switch (status) {
            case TODO -> "Chưa làm";
            case IN_PROGRESS -> "Đang làm";
            case DONE -> "Hoàn thành";
        };
    }

    public static void main(String[] args) {
        var today = LocalDate.of(2030, 6, 10);
        var tasks = List.of(
                new Task(1, "Học Stream",
                        LocalDate.of(2030, 6, 9), Status.IN_PROGRESS),
                new Task(2, "Viết unit test",
                        LocalDate.of(2030, 6, 11), Status.TODO),
                new Task(3, "Cài JDK",
                        LocalDate.of(2030, 6, 1), Status.DONE)
        );

        tasks.stream()
                .filter(task -> task.isOverdue(today))
                .forEach(task -> System.out.println(
                        task.title() + ": " + statusLabel(task.status())));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Kết quả:

```text
Học Stream: Đang làm
```

Điểm cần giải thích được: `record` tự cung cấp accessor như `title()`; compact constructor kiểm tra dữ liệu ngay lúc khởi tạo; `List.of` tạo danh sách không sửa được; Stream lọc công việc quá hạn; switch expression trả về nhãn theo từng trạng thái. `LocalDate.of(...)` được dùng thay vì đồng hồ hệ thống để ví dụ có kết quả lặp lại.

Trong ứng dụng thực tế, hãy tách các kiểu dữ liệu và nghiệp vụ vào package có tên, tránh giữ tất cả trong lớp `Main`. Nếu dữ liệu cần cập nhật trạng thái, có thể tạo bản ghi `Task` mới với trạng thái mới thay vì sửa nội bộ record.

### Minh họa cách kiểm thử nghiệp vụ

Khi dự án đã khai báo **JUnit Jupiter (JUnit 5)** làm test dependency, một lớp kiểm thử có thể viết như sau; đây là đoạn minh họa dành cho cấu trúc `Main` ở trên và nên đặt dưới `src/test/java`:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class TaskTest {
    @Test
    void openTaskPastDeadlineIsOverdue() {
        var task = new Main.Task(1, "Ôn Java",
                LocalDate.of(2030, 6, 9), Main.Status.TODO);
        assertTrue(task.isOverdue(LocalDate.of(2030, 6, 10)));
    }

    @Test
    void completedTaskIsNotOverdue() {
        var task = new Main.Task(2, "Đã xong",
                LocalDate.of(2030, 6, 1), Main.Status.DONE);
        assertFalse(task.isOverdue(LocalDate.of(2030, 6, 10)));
    }

    @Test
    void blankTitleIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new Main.Task(3, "   ",
                        LocalDate.of(2030, 6, 10), Main.Status.TODO));
    }
}
```

JUnit **không nằm sẵn trong JDK**; muốn chạy bằng Maven hoặc Gradle phải thêm dependency và cấu hình bộ chạy test thích hợp. Bài học ở đây là đưa các quy tắc nhỏ thành phép thử tự động, dễ lặp lại.

## 6. Đồ án cuối lộ trình

**Đề xuất: ứng dụng CLI quản lý công việc cá nhân**, chạy bằng JDK 17 và không phụ thuộc máy của người viết. Người học có thể chọn miền dữ liệu tương đương (quản lý sách, đơn hàng giả lập, lịch học) nhưng nên giữ độ khó tương tự.

### Yêu cầu chức năng

1. Thêm công việc với ID, tiêu đề, trạng thái và ngày hạn; kiểm tra ID hợp lệ, tên không trắng, trạng thái được hỗ trợ và định dạng ngày.
2. Liệt kê, tìm theo ID, lọc theo trạng thái, sắp xếp theo hạn và đánh dấu công việc hoàn thành.
3. Thống kê tổng số, số hoàn thành và số quá hạn; định nghĩa rõ “quá hạn” là **trước** ngày đang xét và **chưa** hoàn thành.
4. Lưu/đọc dữ liệu bền vững từ tệp bằng `Path`/`Files` và UTF-8; báo lỗi rõ ràng khi tệp không tồn tại, dữ liệu hỏng hoặc không có quyền đọc.
5. Cung cấp menu/lệnh dễ hiểu, cho phép thoát bình thường, không làm chương trình sập vì nhập sai định dạng thông thường.

Để lưu dữ liệu có cấu trúc, có thể chọn một định dạng đã định nghĩa rõ. Nếu dùng JSON hoặc CSV với trường hợp phức tạp, chọn thư viện phù hợp và khai báo dependency; **Java 17 không có bộ JSON binding tổng quát tích hợp sẵn**. Không nên tự viết parser chỉ tách theo dấu phẩy rồi giả định mọi trường dữ liệu đều đơn giản.

### Yêu cầu thiết kế và kỹ thuật

- Tách tối thiểu các phần **model/domain**, **nghiệp vụ**, **lưu trữ** và **giao diện CLI**. Đặt tên lớp/phương thức phản ánh ý nghĩa, không tạo một lớp chứa toàn bộ chương trình.
- Dùng `enum` cho trạng thái, `LocalDate` cho ngày và collection/generics đúng kiểu; cân nhắc record cho dữ liệu bất biến. Tránh sử dụng `null` làm phương tiện điều khiển ở nhiều tầng.
- Không bỏ qua exception; dùng thông báo phù hợp cho lỗi người nhập và giữ nguyên nguyên nhân lỗi hệ thống khi cần điều tra.
- Tạo unit test cho các quy tắc nghiệp vụ, gồm trường hợp bình thường, trường hợp biên và đầu vào không hợp lệ. Phần lưu/đọc tệp nên có integration test dùng thư mục tạm, tránh phụ thuộc dữ liệu có sẵn trên máy.
- Dùng Git lưu lịch sử thay đổi; khai báo JDK target 17 và dependency trong dự án; tài liệu chạy không phụ thuộc vào đường dẫn cá nhân.

### Bộ tình huống phải tự chứng minh

| Tình huống | Hành vi mong đợi |
|---|---|
| Thêm công việc hợp lệ | Lưu được, tìm lại đúng ID, tên, trạng thái, ngày hạn |
| Tiêu đề chỉ gồm khoảng trắng | Từ chối với lý do rõ ràng |
| ID trùng | Không tạo bản ghi thứ hai với cùng ID |
| Ngày hạn là hôm qua, chưa xong | Được tính là quá hạn |
| Ngày hạn là hôm nay | Không tính là quá hạn theo định nghĩa trên |
| Công việc đã hoàn thành nhưng ngày hạn trong quá khứ | Không tính là quá hạn |
| Danh sách trống | Hiển thị kết quả rỗng, không phát sinh lỗi |
| Đọc tệp hỏng hoặc dữ liệu sai cấu trúc | Xử lý có kiểm soát; không âm thầm coi dữ liệu hỏng là hợp lệ |
| Ghi rồi khởi động lại ứng dụng | Có thể đọc lại dữ liệu đã lưu, không mất thông tin |

## 7. Tiêu chí hoàn thành có thể kiểm chứng

Một chặng được xem là hoàn thành khi người học **tự giải thích được khái niệm, tự viết bài thực hành và xử lý được tình huống biên**. Việc xem hết video hoặc chép lại ví dụ chưa chứng minh được khả năng sử dụng Java.

Đối với toàn bộ lộ trình, kiểm tra các nhóm sau:

| Nhóm năng lực | Bằng chứng đạt yêu cầu |
|---|---|
| **Môi trường** | Có thể checkout dự án và chạy build/test/app từ terminal; cấu hình target Java 17 rõ ràng |
| **Ngôn ngữ và OOP** | Giải thích được primitive/reference, `equals`, encapsulation, interface, record, enum; áp dụng đúng vào mã |
| **API và dữ liệu** | Chọn được `List`/`Set`/`Map`, dùng generics, Stream, `java.time`, `Files` theo nhu cầu; xử lý lỗi đúng |
| **Tính năng Java 17** | Sử dụng được những tính năng ổn định phù hợp và nhận diện được tính năng chỉ xuất hiện hoặc ổn định ở các JDK mới hơn |
| **Kiểm thử** | Test tự động chạy thành công; có ca đúng, ca sai, ca biên; có thể tái hiện và sửa lỗi được phát hiện |
| **Bàn giao** | Có mã nguồn, `README` hướng dẫn chạy, ví dụ thao tác, quyết định thiết kế chính và danh sách hạn chế còn lại |
| **Giải thích kỹ thuật** | Có thể trình bày luồng dữ liệu từ nhập → xử lý → lưu → hiển thị, đồng thời giải thích ít nhất một lựa chọn thiết kế hoặc cấu trúc dữ liệu |

**Điều kiện qua môn đề xuất:**

- Toàn bộ tính năng bắt buộc của đồ án thực hiện được; không có lỗi làm mất dữ liệu trong các tình huống thử đã nêu.
- Biên dịch/chạy được ở mức Java 17; không cần bật preview hoặc cài JDK cao hơn để chạy ứng dụng.
- Test nghiệp vụ và kiểm tra tích hợp quan trọng đều chạy thành công trên môi trường sạch có đủ dependency.
- Người học tự sửa được ít nhất một lỗi mới được đưa ra (ví dụ ID trùng, ngày hạn bằng hôm nay, dữ liệu tệp sai) bằng cách tái hiện, xác định nguyên nhân, sửa và thêm test ngăn tái phát.
- Khi nhìn vào một đoạn code của chính mình, người học giải thích được **tại sao** chọn cách làm đó, thay vì chỉ mô tả từng dòng.

Nếu chưa đạt một nhóm, quay lại đúng chặng tương ứng và bổ sung bài thực hành; không cần học lại từ đầu. Nếu đã thành thạo các nhóm cốt lõi, có thể tiếp tục chủ đề kế tiếp như SQL/JDBC, API web, Spring, tối ưu hiệu năng, bảo mật hoặc nâng cấp lên JDK LTS mới hơn, tùy yêu cầu dự án.

## 8. Cách tự học để tránh học trước quên sau

Mỗi chặng nên đi theo chu trình: **hiểu khái niệm → viết ví dụ nhỏ không nhìn đáp án → thử trường hợp biên → đọc tài liệu API → thêm vào đồ án**. Giữ một nhật ký ngắn gồm điều học được, lỗi từng gặp và cách tự chứng minh đã hiểu.

Một số nguyên tắc giúp giữ chất lượng kiến thức:

- **Học một cách chạy chuẩn trước:** terminal + một IDE + một build tool. Chỉ thêm công cụ khi có mục đích rõ ràng.
- **Tách API chuẩn khỏi thư viện ngoài:** JUnit, Jackson hoặc framework không tự xuất hiện chỉ vì đã cài JDK.
- **Đọc thông báo lỗi đầy đủ:** tìm loại exception, vị trí, call stack và dữ liệu gây lỗi trước khi sửa.
- **Không lạm dụng tính năng mới:** dùng vòng lặp khi dễ hiểu hơn Stream; dùng class thường khi record không phù hợp; dùng inheritance/sealed type theo mô hình thật.
- **Dành thời gian cho kiểm thử:** bài toán chạy với một ví dụ chưa đủ chứng minh đáp ứng các tình huống thực tế.
- **Giữ mã tương thích Java 17:** khi xem hướng dẫn dành cho Java 21/25 hoặc bản mới hơn, kiểm tra tính năng và API trước khi áp dụng.

Nguồn tra cứu nên ưu tiên tài liệu gốc: [dev.java — Learn Java](https://dev.java/learn/), [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/index.html) và [OpenJDK JEP Index](https://openjdk.org/jeps/0). Dùng tài liệu API để xác định hành vi thực tế của phương thức; dùng JEP để kiểm tra phiên bản tính năng được giới thiệu và trạng thái preview/final.
