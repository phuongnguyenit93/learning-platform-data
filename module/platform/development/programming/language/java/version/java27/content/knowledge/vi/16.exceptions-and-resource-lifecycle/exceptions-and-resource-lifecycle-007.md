# Quản lý vòng đời tài nguyên tường minh và phát hiện rò rỉ trong Java 27

Trong chương **Ngoại lệ và vòng đời tài nguyên**, việc xử lý đúng `Exception` chỉ là một phần của lập trình an toàn. Ứng dụng còn phải trả lại những tài nguyên hữu hạn đã mượn từ hệ điều hành, runtime hoặc dịch vụ bên ngoài: file descriptor, socket, kết nối cơ sở dữ liệu, luồng I/O, thread pool và vùng bộ nhớ native.

**Java quản lý bộ nhớ đối tượng bằng garbage collector (GC), nhưng GC không thay thế giao thức đóng tài nguyên.** Một đối tượng không còn tham chiếu vẫn có thể chưa được thu gom; trong thời gian đó file hoặc socket gắn với nó có thể còn chiếm tài nguyên. Java 27 cung cấp một mô hình tường minh và ổn định: xác định **ai sở hữu tài nguyên**, khoanh vùng **thời gian sử dụng**, và đóng nó bằng `try-with-resources` hoặc một cơ chế dọn dẹp có kiểm soát tương ứng.

Bài học tập trung vào API Java SE 27 còn áp dụng hiện nay. Những cách dựa vào `finalize()`, gọi `System.gc()` để mong đóng file, hay giả định JVM tự giải phóng tài nguyên ngay khi một biến ra khỏi scope **không phải chiến lược quản lý vòng đời đáng tin cậy**.

## 1. Tài nguyên khác đối tượng Java thông thường ở điểm nào?

Không phải mọi đối tượng Java đều cần `close()`. Một `String`, một record dữ liệu hoặc một `ArrayList` chỉ chứa giá trị thường không đòi hỏi thao tác dọn dẹp tường minh. Nhưng một đối tượng quản lý tài nguyên *ngoài heap* hoặc một hệ thống có vòng đời độc lập có thể cần hành động đóng:

| Loại tài nguyên | Ví dụ API Java hiện hành | Nếu không đóng |
| --- | --- | --- |
| File / luồng I/O | `Files.newInputStream`, `Files.newBufferedReader`, `FileChannel` | Tăng số handle, giữ file chưa được giải phóng hoặc khóa liên quan |
| Stream đọc thư mục / file | `Files.lines`, `Files.list`, `Files.walk` | Giữ các tài nguyên đọc file/thư mục cho đến khi được đóng |
| Socket | `Socket`, `ServerSocket`, kênh NIO | Chiếm kết nối/descriptor; có thể không giải phóng kịp khi tải lớn |
| JDBC | `Connection`, `Statement`, `ResultSet` | Giữ kết nối hoặc cursor; cạn connection pool |
| Executor | `ExecutorService` | Tác vụ/thread hoặc hàng đợi tiếp tục tồn tại ngoài nhu cầu |
| Native memory có scope | `Arena.ofConfined()`, `Arena.ofShared()` | Bộ nhớ native không được giải phóng đúng thời điểm |
| Tài nguyên ứng dụng tự định nghĩa | Class triển khai `AutoCloseable` | Không chạy quy trình flush, release hoặc cleanup của class |

*Lưu ý:* Cụm từ “rò rỉ” không chỉ có nghĩa một vùng heap tăng mãi. Nó còn bao gồm **resource leak**: tài nguyên được cấp phát/mượn nhưng không được trả lại trong thời gian hợp lý, dẫn đến cạn quota, giảm thông lượng hoặc khóa hệ thống.

### 1.1. Một mô hình vòng đời đơn giản

```text
acquire/open
    |
    v
use (phạm vi được phép sử dụng)
    |
    +---- thành công ------+
    |                     |
    +---- ném exception ---+--> close/release --> đóng xong hoặc báo lỗi đóng
    |                     |
    +---- return sớm -----+
```

Mục tiêu là bảo đảm đường đi nào sau khi **mở thành công** cũng có đường dọn dẹp phù hợp. Nếu việc mở tài nguyên thứ hai thất bại, tài nguyên thứ nhất cũng phải được đóng; không chỉ xử lý nhánh thành công của nghiệp vụ.

### 1.2. Cần phân biệt ba kiểu sự cố

- **Heap memory leak:** Đối tượng vẫn còn reachable không cần thiết, ví dụ collection cache tăng mãi.
- **Resource leak:** Quên đóng file, cursor, connection, executor hoặc native arena đúng thời điểm.
- **Tắc nghẽn nhưng không phải leak:** Một connection vẫn đang được sử dụng bởi truy vấn lâu, tác vụ bị kẹt hoặc pool có cấu hình quá nhỏ. Các triệu chứng có thể giống leak nhưng nguyên nhân khác.

Chẩn đoán đúng loại sự cố sẽ quyết định nên xem heap dump, thread dump, bộ đếm pool, file descriptor hay native-memory metrics.

## 2. Quy tắc ownership: ai mở, ai đóng?

Một contract tốt cần chỉ rõ **đối tượng nào chịu trách nhiệm đóng tài nguyên**. Quy tắc thực hành thường dùng là: **thành phần tạo/mượn tài nguyên đóng nó khi công việc kết thúc**, trừ khi tài liệu API có quy định chuyển giao ownership.

Ví dụ hàm tự mở file và xử lý trọn vẹn:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static long countLines(Path path) throws IOException {
    try (var lines = Files.lines(path)) {
        return lines.count();
    }
}
```

Ở đây `countLines` tạo stream gắn với file và sở hữu nó. Phương thức trả về `long`, không để tài nguyên thoát khỏi scope nên có thể đóng ngay.

Ngược lại, nếu một factory **trả tài nguyên còn mở**:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static BufferedReader openReader(Path path) throws IOException {
    return Files.newBufferedReader(path);
}
```

Caller nhận ownership và phải đóng:

```java
try (BufferedReader reader = openReader(path)) {
    System.out.println(reader.readLine());
}
```

**Không được đóng reader trong `openReader` trước khi trả về**, vì đối tượng trả về sẽ không còn dùng được. Hợp đồng nên ghi rõ: “caller owns the returned reader and must close it”.

### 2.1. Borrowed resource và owned resource

Có phương thức chỉ **mượn** tài nguyên đang do caller quản lý:

```java
static String firstLine(BufferedReader borrowed) throws IOException {
    return borrowed.readLine();
    // Không gọi borrowed.close(): owner ở bên ngoài.
}
```

Gọi `close()` ngay trong `firstLine` có thể phá công việc phía caller vẫn cần thực hiện với reader. Tên tham số `borrowed` chỉ nhằm diễn đạt contract; Java không tự có type system phân biệt owned/borrowed reference.

Bảng tư duy:

| Tình huống | Ai đóng? |
| --- | --- |
| Phương thức mở file, đọc hết rồi trả dữ liệu | Phương thức |
| Factory trả một stream/reader còn mở | Caller, trừ khi API nói khác |
| Phương thức chỉ sử dụng connection do caller truyền vào | Caller hoặc transaction scope bên ngoài |
| Connection được lấy từ pool | Bên sở hữu lượt mượn gọi `close()` để trả về pool theo contract implementation |
| Lớp lưu tài nguyên để dùng nhiều lần | Lớp đó triển khai `AutoCloseable`, và owner của lớp đóng lớp khi không dùng nữa |

Không nên áp dụng “hễ có `AutoCloseable` thì đóng ngay” khi đối tượng được *mượn* và còn người khác sử dụng.

## 3. `AutoCloseable` và `Closeable`: hợp đồng đóng tài nguyên

`java.lang.AutoCloseable` là interface nền tảng cho đối tượng cần giải phóng tài nguyên. Nó có phương thức:

```java
public interface AutoCloseable {
    void close() throws Exception;
}
```

Khi đối tượng được khai báo trong phần resource của `try-with-resources`, Java sẽ tự gọi `close()` khi rời khối `try` theo quy tắc ngôn ngữ.

`java.io.Closeable` mở rộng `AutoCloseable` nhưng `close()` thu hẹp exception thành `IOException`:

```java
public interface Closeable extends AutoCloseable {
    void close() throws IOException;
}
```

Một số khác biệt đáng nhớ:

- `AutoCloseable.close()` có thể khai báo ném `Exception`; class cụ thể nên thu hẹp loại exception hoặc không ném checked exception nếu có thể.
- Contract chung của `AutoCloseable` **không bắt buộc `close()` phải idempotent**. Đóng hai lần có thể có hành vi tùy implementation.
- `Closeable` có contract đóng lặp lại không gây tác động sau lần đầu, nhưng vẫn phải đọc tài liệu loại tài nguyên cụ thể khi thiết kế wrapper.
- Không nên để `AutoCloseable.close()` tự ném `InterruptedException` vì nó tương tác khó với trạng thái interrupted và suppressed exceptions.
- Đóng tài nguyên **không đồng nghĩa** xóa object khỏi heap ngay lập tức; sau khi đóng, object vẫn có thể còn referenced nhưng tài nguyên bên dưới phải được quản lý theo contract.

### 3.1. Không phải stream nào cũng cần close

Các stream thuần trong bộ nhớ không thường có tài nguyên bên ngoài:

```java
var result = java.util.List.of(1, 2, 3)
    .stream()
    .map(n -> n * 2)
    .toList();
```

Với trường hợp này, không cần mở một `try-with-resources` chỉ để đóng `List.stream()`. Tuy nhiên `Files.lines`, `Files.list` hoặc `Files.walk` trả stream **có resource cần đóng**. Quy tắc là **xem nguồn stream và tài liệu API**, không chỉ nhìn kiểu `Stream<T>`.

## 4. `try-with-resources`: mặc định nên dùng

Cú pháp hiện đại nhất để đóng tài nguyên trong Java là `try-with-resources`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static String readFirstLine(Path path) throws IOException {
    try (var reader = Files.newBufferedReader(path)) {
        return reader.readLine();
    }
}
```

Nếu `readLine()` chạy xong, ném exception hoặc method `return` sớm, Java vẫn gọi `reader.close()` khi rời scope. Nếu reader mở thất bại, chưa có resource nào được khởi tạo thành công nên không có reader đó để đóng.

Đóng diễn ra **trước khi control flow rời statement**, kể cả khi có `return` bên trong `try`. Exception từ `close()` vẫn có thể ảnh hưởng việc thoát khối, vì vậy không nên xem `close()` là thao tác luôn thành công.

### 4.1. Nhiều resource và thứ tự đóng

Có thể khai báo nhiều tài nguyên trong cùng resource specification:

```java
try (var first = Files.newBufferedReader(firstPath);
     var second = Files.newBufferedReader(secondPath)) {
    System.out.println(first.readLine());
    System.out.println(second.readLine());
}
```

Thứ tự là:

1. Mở `first`.
2. Mở `second`.
3. Chạy phần thân `try`.
4. Đóng `second`.
5. Đóng `first`.

**Đóng theo thứ tự ngược với thứ tự khởi tạo thành công.** Nếu mở `second` thất bại, Java vẫn đóng `first`. Đây là ưu điểm lớn so với tự viết nhiều `finally` lồng nhau.

### 4.2. Dùng biến đã có từ Java 9

Nếu resource là biến cục bộ `final` hoặc effectively final, có thể đưa chính biến đó vào resource specification:

```java
var reader = Files.newBufferedReader(path);

try (reader) {
    System.out.println(reader.readLine());
}
// reader đã được close
```

Điều kiện quan trọng: biến được dùng phải đáp ứng quy tắc final/effectively final và thuộc scope hợp lệ. Không nên hiểu cú pháp này là resource được “clone” hoặc ownership trở nên tự động rõ ràng; chính khối `try` vẫn chịu trách nhiệm gọi `close()` trên object đó.

**Tránh sử dụng lại resource sau khi đã đóng**, trừ khi API cụ thể nói rõ những thao tác nào còn được phép.

## 5. Ngoại lệ khi đóng: primary và suppressed exceptions

Giải phóng tài nguyên cũng có thể thất bại: flush output không thành công, socket báo lỗi, kết nối mất trong khi close. Nếu phần thân `try` đã ném exception, Java cần giữ lại **nguyên nhân chính** đồng thời không đánh mất lỗi đóng tài nguyên.

Với `try-with-resources`:
- Exception phát sinh trong thân `try` là **primary exception**.
- Exception từ `close()` trong quá trình xử lý primary được lưu dưới dạng **suppressed exception** trên primary.
- Nếu phần thân không ném exception nhưng nhiều `close()` cùng thất bại, lỗi từ resource được đóng **trước** (theo thứ tự đảo) là primary, các lỗi đóng tiếp theo bị suppressed.

### 5.1. Ví dụ có thể chạy độc lập

```java
import java.io.IOException;

public class SuppressedExceptionDemo {
    static final class FailingResource implements AutoCloseable {
        private final String name;

        FailingResource(String name) {
            this.name = name;
        }

        @Override
        public void close() throws IOException {
            System.out.println("Closing " + name);
            throw new IOException("Close failure: " + name);
        }
    }

    public static void main(String[] args) {
        try (var first = new FailingResource("first");
             var second = new FailingResource("second")) {
            throw new IllegalStateException("Business failure");
        } catch (Exception primary) {
            System.out.println("Primary: " + primary.getMessage());

            for (Throwable suppressed : primary.getSuppressed()) {
                System.out.println("Suppressed: " + suppressed.getMessage());
            }
        }
    }
}
```

Kết quả:

```text
Closing second
Closing first
Primary: Business failure
Suppressed: Close failure: second
Suppressed: Close failure: first
```

Thông tin suppressed quan trọng khi debug: chỉ nhìn message của primary có thể bỏ sót bằng chứng tài nguyên đóng thất bại. Ghi stack trace đầy đủ thường hiển thị suppressed exceptions; khi log thủ công cần bảo đảm không loại bỏ thông tin đó.

### 5.2. Vì sao không nên dùng `finally` một cách sơ suất?

Ví dụ truyền thống:

```java
Resource resource = acquire();

try {
    use(resource);
} finally {
    resource.close();
}
```

Nếu `use()` ném exception rồi `close()` lại ném exception khác, exception từ `close()` có thể **ghi đè** lỗi nghiệp vụ ban đầu. Ngoài ra, nếu có nhiều tài nguyên, việc tự điều phối đóng theo thứ tự và giữ suppressed exceptions khá dễ sai.

Vì vậy `try-with-resources` là lựa chọn mặc định khi kiểu triển khai `AutoCloseable`. Dùng `finally` khi tài nguyên không hỗ trợ `AutoCloseable` hoặc khi phải xử lý protocol đặc biệt không biểu diễn được bằng một `close()` đơn giản.

## 6. Xử lý lỗi đóng có trách nhiệm

Đừng âm thầm bỏ qua lỗi `close()` của tài nguyên có khả năng flush dữ liệu hoặc commit một thao tác quan trọng.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static void export(Path path, String data) throws IOException {
    try (var writer = Files.newBufferedWriter(path)) {
        writer.write(data);
    }
}
```

Với nhiều writer, việc đóng có thể bao gồm flush các buffer; nếu có lỗi I/O thì method vẫn có thể ném `IOException`. Caller phải quyết định có thể retry, báo thất bại hoặc làm sạch file đầu ra chưa hoàn chỉnh.

**Đóng không phải commit giao dịch.** JDBC transaction cần commit/rollback theo ranh giới nghiệp vụ. Tương tự, ghi file quan trọng cần có chiến lược file tạm và thay thế atomic khi hệ thống hỗ trợ, chứ không nên cho rằng `close()` đủ để bảo đảm ghi bền vững hoặc cập nhật nguyên tử.

### 6.1. Một wrapper `AutoCloseable` tự định nghĩa

Nếu một class sở hữu resource, nên làm quyền sở hữu và trạng thái đóng trở nên rõ ràng:

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ManagedInput implements AutoCloseable {
    private final InputStream input;
    private boolean closed;

    public ManagedInput(Path path) throws IOException {
        input = Files.newInputStream(path);
    }

    public int read() throws IOException {
        if (closed) {
            throw new IllegalStateException("Input already closed");
        }
        return input.read();
    }

    @Override
    public void close() throws IOException {
        if (closed) {
            return;
        }
        closed = true;
        input.close();
    }
}
```

Dùng như sau:

```java
try (var input = new ManagedInput(path)) {
    System.out.println(input.read());
}
```

Ví dụ cố tình đơn giản và giả định **không có truy cập đồng thời**. Nếu nhiều thread có thể đọc/đóng cùng lúc, cần thiết kế đồng bộ hóa phù hợp, không chỉ một biến boolean. Việc đặt `closed = true` trước khi gọi `input.close()` ngăn gọi lại theo thiết kế ví dụ, nhưng **không bảo đảm tầng I/O đã giải phóng thành công nếu `close()` ném lỗi**; xử lý sự cố này phụ thuộc contract tài nguyên cụ thể.

Không tự thêm `finalize()` vào lớp này. Trong Java hiện đại, finalization đã bị đánh dấu deprecated for removal và không còn là giải pháp đáng tin cậy cho deterministic cleanup.

## 7. Tránh lỗi ownership khi bọc nhiều tầng

Nhiều API có lớp bọc như `BufferedInputStream`, `BufferedReader`, `GZIPInputStream` hoặc một reader giải mã. Khi wrapper sở hữu resource bên dưới, thường **đóng wrapper là đóng tài nguyên bên dưới**.

```java
import java.io.BufferedInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

static int readFirstByte(Path path) throws Exception {
    try (InputStream input =
             new BufferedInputStream(Files.newInputStream(path))) {
        return input.read();
    }
}
```

Ở đây `BufferedInputStream` là owner của `InputStream` phía dưới. Không cần đưa cả inner stream và outer stream vào hai resource declaration chỉ để gọi `close()` hai lần. Thiết kế nên xác định rõ điểm ownership chuyển sang wrapper.

**Rủi ro khi tự tạo wrapper:** nếu constructor của wrapper thực hiện nhiều bước cấp phát rồi thất bại giữa chừng, wrapper phải tự dọn các resource đã cấp phát trước khi ném exception. `try-with-resources` chỉ đóng được những resource đã khởi tạo và được đưa thành công vào resource specification.

### 7.1. Nếu bắt buộc có nhiều phần tử mở liên tiếp

Khi tài nguyên B phụ thuộc A, dùng:

```java
try (var a = acquireA();
     var b = acquireB(a)) {
    use(a, b);
}
```

Nếu `acquireB(a)` ném exception, `a.close()` vẫn chạy. Nếu cả A và B đã được tạo, B đóng trước A. Hãy bảo đảm `b.close()` không đóng lại A nếu cả hai được khai báo là resource độc lập và contract của B đã chuyển ownership của A.

## 8. Stream gắn với file hoặc thư mục: chỗ rò rỉ dễ bị bỏ qua

Stream API có thể che khuất tài nguyên I/O đằng sau một pipeline trông như code biến đổi collection thông thường.

**Sai:**

```java
import java.nio.file.Files;
import java.nio.file.Path;

// Đừng lặp kiểu này trên máy chủ:
// long count = Files.lines(Path.of("app.log")).count();
```

`Files.lines(path)` trả về stream gắn với file đang mở. Terminal operation `count()` chỉ **tiêu thụ stream**, không tự thực hiện nghĩa vụ `close()` của nguồn.

**Đúng:**

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static long nonBlankLines(Path path) throws IOException {
    try (var lines = Files.lines(path)) {
        return lines.filter(line -> !line.isBlank()).count();
    }
}
```

Với thư mục:

```java
static long countRegularFiles(Path root) throws IOException {
    try (var paths = Files.walk(root, 2)) {
        return paths
            .filter(Files::isRegularFile)
            .count();
    }
}
```

`Files.list` và `Files.walk` cũng phải được đóng. Việc duyệt có thể phát sinh I/O exception muộn trong pipeline; một số API Stream bọc lỗi này bằng `UncheckedIOException`. Đừng chỉ đặt `try` quanh lệnh tạo stream rồi giả định các bước duyệt sau đó không thể thất bại.

### 8.1. Xử lý trả dữ liệu chứ không trả stream đang giữ file mở

Một phương thức có thể đọc rồi materialize thành collection:

```java
static java.util.List<String> readAllNonBlank(Path path)
        throws IOException {
    try (var lines = Files.lines(path)) {
        return lines
            .filter(line -> !line.isBlank())
            .toList();
    }
}
```

Sau khi `toList()` hoàn tất, stream được đóng trước khi method trả collection. Nhưng cách này đưa toàn bộ kết quả vào heap; với file rất lớn, nên xử lý từng phần hoặc thiết kế API streaming có ownership rõ ràng thay vì luôn gom thành list.

Nếu một API **trả về `Stream<String>`** đọc file cho caller, phải ghi rõ caller chịu trách nhiệm gọi `close()` và không dùng stream sau khi đóng.

## 9. JDBC: trả lại connection và đóng cursor

JDBC là một nguồn resource leak thực tế trong server. `Connection`, `PreparedStatement` và `ResultSet` đều có thể dùng với `try-with-resources`.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

static void printOpenOrders(DataSource dataSource) throws SQLException {
    String sql = "SELECT id FROM orders WHERE status = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setString(1, "OPEN");

        try (ResultSet rows = statement.executeQuery()) {
            while (rows.next()) {
                System.out.println(rows.getLong("id"));
            }
        }
    }
}
```

Ở đây, `ResultSet` đóng trước; sau đó `PreparedStatement`, cuối cùng `Connection`. Với connection pool, `connection.close()` thường **trả connection về pool** thay vì đóng socket vật lý ngay lập tức — nhưng phải dựa vào contract của implementation/pool đang dùng.

**Không đóng connection đang được framework/transaction manager quản lý** nếu bạn chỉ mượn nó trong một transaction scope. Trong trường hợp đó, code quản lý transaction chính là owner, và method nghiệp vụ chỉ sử dụng connection được cung cấp.

### 9.1. Transaction cần chính sách riêng

Khi tắt auto-commit, ứng dụng phải xác định rõ lúc commit, rollback và xử lý exception. Đừng coi `close()` thay thế cho commit/rollback. Các pool/framework có thể can thiệp vào trạng thái transaction khi trả connection; chính sách này phải được xác minh từ tài liệu của công cụ sử dụng.

### 9.2. Dấu hiệu rò rỉ connection

- Thời gian chờ `getConnection()` tăng dần.
- Pool báo “connection timeout” hoặc cạn số connection available.
- Tổng connection đang được mượn không trở về mức bình thường sau khi request hoàn tất.
- Một số truy vấn thực ra vẫn đang chạy rất lâu, khiến connection bị giữ hợp lệ nhưng quá thời gian kỳ vọng.

Theo dõi metrics **active / idle / pending / acquisition timeout**, cùng log điểm acquire và release theo request correlation ID; tránh ghi mật khẩu hay thông tin truy cập bí mật vào log.

## 10. ExecutorService và vòng đời tác vụ

Từ Java SE 19, `ExecutorService` triển khai `AutoCloseable`. Trong Java 27 có thể dùng `try-with-resources` để gắn vòng đời executor vào scope:

```java
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutorLifecycleDemo {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Integer> answer = executor.submit(() -> 6 * 7);
            System.out.println(answer.get()); // 42
        }
    }
}
```

`executor.close()` khởi động shutdown có trật tự, không nhận thêm nhiệm vụ, và **chờ tác vụ đã nhận hoàn tất** theo contract. Nếu thread đóng executor bị interrupt trong khi chờ, default close thực hiện shutdownNow, tiếp tục chờ những tác vụ đang chạy kết thúc rồi khôi phục interrupted status trước khi trả về.

**Cảnh báo quan trọng:** `close()` có thể chờ lâu hoặc không hoàn tất nếu tác vụ không kết thúc hoặc không hợp tác với interruption. Với hệ thống sản xuất cần deadline, hãy chủ động lập chính sách timeout, cancellation và giám sát task; `try-with-resources` không tự đặt timeout cho logic nghiệp vụ.

### 10.1. Phân biệt scope ngắn và service dùng chung

- Executor tạo riêng cho một lô công việc trong method: đóng ở cuối lô.
- Executor là thành phần dùng chung suốt vòng đời service: để service/application lifecycle quản lý và đóng khi shutdown, **không** đóng sau từng request.
- Một task có thể tạo/tận dụng tài nguyên con; task phải đóng tài nguyên con của mình, chứ việc đóng executor không tự đóng mọi file hoặc connection mà task đã mở.

Đừng thiết kế “mỗi request tạo một executor rồi quên shutdown” chỉ vì executor không trực tiếp chiếm file descriptor. Thread và hàng đợi cũng là nguồn tài nguyên hữu hạn cần quản lý.

## 11. Native memory: sử dụng Arena cho scope có kiểm soát

Foreign Function & Memory API là API chính thức trong Java hiện đại (ổn định từ Java 22). `java.lang.foreign.Arena` quản lý vòng đời một hoặc nhiều `MemorySegment` native. Arena kiểu confined hoặc shared có thể được đóng tường minh:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class NativeMemoryScopeDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment memory = arena.allocate(16);
            memory.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);

            System.out.println(
                memory.get(ValueLayout.JAVA_BYTE, 0)
            ); // 42
        } // Native memory do arena quản lý được giải phóng
    }
}
```

Sau khi arena đóng, những memory segment gắn với scope đó không còn được phép truy cập theo contract. `Arena.ofConfined()` cho phép truy cập từ thread sở hữu; `Arena.ofShared()` cho phép truy cập đa luồng theo điều kiện API.

**Không dùng `Arena.ofAuto()` làm lựa chọn mặc định cho bộ nhớ cần giải phóng đúng deadline** vì lifetime của arena tự động phụ thuộc reachability/GC. `Arena.global()` có lifetime toàn cục và không thể đóng bằng `close()`; chỉ dùng khi chủ động chấp nhận lifetime dài đó.

Không phải mọi native allocation hoặc bộ nhớ từ thư viện bên thứ ba đều tự được Native Memory Tracking (NMT) ghi nhận. Việc dùng FFM hoặc thư viện JNI vẫn cần theo dõi hợp đồng ownership cụ thể của từng tài nguyên.

## 12. Cleaner và GC: lớp dự phòng, không phải cam kết thời điểm

`java.lang.ref.Cleaner` có thể hỗ trợ cleanup sau khi một object không còn reachable, nhưng **không bảo đảm cleanup xảy ra ngay hoặc trước khi process kết thúc**. Đây không phải lựa chọn thay cho `close()` ở những resource có lifetime rõ ràng.

Một số API có cơ chế cleanup nội bộ để giảm hậu quả của việc quên đóng. Tuy vậy, ứng dụng vẫn phải dùng explicit resource lifecycle theo contract API. Đừng trông chờ:
- `System.gc()` sẽ đóng tài nguyên ngay.
- `finalize()` sẽ được gọi đúng lúc hoặc được hỗ trợ lâu dài.
- Đối tượng ra khỏi block sẽ tự khiến file descriptor/socket biến mất.
- Heap usage ổn định có nghĩa không có native/resource leak.

Java đã deprecated finalization for removal; tránh viết code mới dựa vào finalizer để giải phóng tài nguyên.

## 13. Phát hiện resource leak theo tín hiệu nào?

Rò rỉ thường thể hiện bằng **độ lệch tăng theo thời gian sau khi workload kết thúc**, không phải một snapshot đơn lẻ.

| Triệu chứng | Khả năng cần kiểm tra | Tín hiệu hoặc công cụ |
| --- | --- | --- |
| “Too many open files”, không mở được socket mới | File descriptor / socket leak | Số descriptor, metrics I/O, `lsof`, `/proc/<pid>/fd` trên Linux |
| Không lấy được JDBC connection | Quên trả pool, transaction dài, truy vấn kẹt | Pool active/idle/pending, checkout duration |
| Thread tăng, shutdown không thoát | Executor chưa shutdown, task kẹt | Thread dump, executor metrics, JFR |
| Process RSS tăng nhưng heap ổn định | Native memory, direct buffer, thread stack | NMT nếu bật, metrics OS, native profiler |
| Heap sau GC tăng qua các chu kỳ | Object vẫn reachable, cache tăng | JFR OldObjectSample, heap histogram/dump, GC metrics |
| Windows báo file đang được ứng dụng sử dụng | Handle chưa đóng hoặc lock còn giữ | Handle inspection, monitoring, ứng dụng tự log open/close |
| Test đơn vị chạy ổn, tải nhiều request thì lỗi | Leak tích lũy theo request | Load test có so sánh resource count trước/sau |

**Đừng kết luận leak từ một cảnh báo đơn lẻ.** Pool có thể chủ động giữ tài nguyên để tái sử dụng; thread có thể xử lý lâu; heap có thể dao động do GC. Phải đối chiếu trạng thái sau khi tải ngừng và sau các mốc xử lý tương đương.

### 13.1. Quy trình điều tra 6 bước

1. **Xác định loại tài nguyên**: descriptor, connection, thread, heap, native memory hay file lock.
2. **Ghi baseline** trước khi tăng tải: số handle, active connections, threads, heap used sau GC, RSS, throughput.
3. **Chạy workload có khả năng tái hiện**, theo dõi số lượt acquire và release.
4. **Cho workload kết thúc**, chờ thời gian hợp lý cho tác vụ đang hoàn tất; đo lại các chỉ số.
5. **Khoanh vùng đường code** mở nhưng không đóng, gồm exception path, early return, timeout và cancellation.
6. **Sửa bằng ownership và close có cấu trúc**, thêm test lặp nhiều lần, rồi so sánh metric trước/sau thay vì chỉ kiểm tra hết exception.

Ghi log theo resource ID và trace ID có thể hỗ trợ tìm cặp acquire/release mất cân bằng. Không ghi đường dẫn nhạy cảm, token truy cập hoặc nội dung file bí mật vào log chẩn đoán một cách không kiểm soát.

## 14. Công cụ JDK hiện hành: `jcmd`, JFR và NMT

Java 27 có các công cụ chẩn đoán tiêu chuẩn. Lệnh dưới đây là **ví dụ chạy trong môi trường được cấp phép**, không nên thử trên production nếu chưa đánh giá overhead và chính sách truy cập dữ liệu.

### 14.1. Tìm process và liệt kê lệnh hỗ trợ

```text
jcmd -l
jcmd <pid> help
```

`jcmd -l` liệt kê JVM process có thể khám phá được; việc attach có thể cần cùng user và quyền truy cập phù hợp. Không phải mọi launcher/process/container đều được hiển thị bằng cùng một cách.

### 14.2. Thu JDK Flight Recorder

```text
jcmd <pid> JFR.start name=ResourceTrace settings=profile duration=60s filename=resource-trace.jfr
jcmd <pid> JFR.check
```

JFR ghi các sự kiện runtime phục vụ điều tra CPU, allocation, thread và một số hoạt động I/O tùy cấu hình. Dữ liệu có thể được phân tích bằng Java Mission Control hoặc công cụ tương thích.

Điểm quan trọng: **JFR không tự cung cấp một danh sách “mọi file đã mở mà chưa đóng” trong mọi trường hợp**. Cần kết hợp dữ liệu sự kiện với số lượng descriptor/connection của hệ điều hành hoặc pool, log ownership và call path. Những recording có thể chứa thông tin nhạy cảm từ ứng dụng; bảo vệ và giới hạn thời gian lưu file `.jfr`.

### 14.3. Native Memory Tracking (NMT)

Nếu cần phân tích bộ nhớ native do JVM quản lý, khởi động JVM với:

```text
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Sau đó:

```text
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline
# Sau khi tái hiện vấn đề:
jcmd <pid> VM.native_memory summary.diff
```

NMT phải được bật khi khởi động JVM bằng cấu hình phù hợp; nó có overhead. Thông tin `reserved` và `committed` khác nhau và không nên coi `reserved` là lượng RAM thực đang dùng. NMT theo dõi những phạm vi allocation của JVM, **không phải mọi cấp phát native của thư viện bên thứ ba** và **không thay thế metric file descriptor**.

### 14.4. Heap dump và thread dump

Heap histogram hoặc heap dump hữu ích nếu có đối tượng vẫn reachable, chẳng hạn pool/cache vô tình giữ tham chiếu đến resource wrapper. Thread dump giúp tìm task chờ I/O, thread bị kẹt hoặc executor chưa shutdown.

Heap dump có thể rất lớn, gây pause và chứa dữ liệu nhạy cảm. Thu thập có kiểm soát, theo hướng dẫn vận hành và chính sách bảo mật. Không dùng heap dump làm công cụ đầu tiên khi dấu hiệu rõ ràng là cạn file descriptor nhưng heap vẫn ổn định.

### 14.5. OS-level inspection

Trên Linux, có thể xem số file descriptor của process bằng thư mục `/proc/<pid>/fd` hoặc các công cụ như `lsof -p <pid>`; trên Windows có thể dùng công cụ xem process handles như Process Explorer, tùy quyền. Các chỉ số này không đồng nhất giữa hệ điều hành và container; hãy đo đúng process/container cần điều tra.

## 15. Kiểm thử đóng tài nguyên trên nhánh thành công và lỗi

Một test tốt kiểm tra **close được gọi ngay cả khi code giữa chừng ném lỗi**. Có thể dùng resource giả thay vì mở file thật:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class ResourceCloseTestDemo {
    static final class TrackingResource implements AutoCloseable {
        private final AtomicInteger closeCount;

        TrackingResource(AtomicInteger closeCount) {
            this.closeCount = closeCount;
        }

        @Override
        public void close() {
            closeCount.incrementAndGet();
        }
    }

    static void run(boolean fail, AtomicInteger closeCount) {
        try (var resource = new TrackingResource(closeCount)) {
            if (fail) {
                throw new IllegalStateException("Simulated failure");
            }
        }
    }

    public static void main(String[] args) {
        AtomicInteger closes = new AtomicInteger();

        run(false, closes);
        if (closes.get() != 1) {
            throw new AssertionError("Expected close after success");
        }

        try {
            run(true, closes);
            throw new AssertionError("Expected failure");
        } catch (IllegalStateException expected) {
            // Chứng minh exception đi ra ngoài mà close vẫn xảy ra.
        }

        if (closes.get() != 2) {
            throw new AssertionError("Close missing on failure path");
        }

        System.out.println("Close checks passed");
    }
}
```

Đây là kiểm thử mức đơn vị cho logic scope, không đủ thay thế integration test của JDBC pool hay file descriptor. Trong integration/load test, nên theo dõi số tài nguyên **đang được sử dụng** trước và sau nhiều lượt gọi, nhất là khi có timeout, interruption, exception và hủy request.

### 15.1. Các ca biên nên kiểm tra

| Ca kiểm thử | Điều mong đợi |
| --- | --- |
| Mở resource, xử lý bình thường | Đóng đúng thời điểm |
| `return` sớm từ thân `try` | Resource vẫn được đóng |
| Thân `try` ném `IOException`/runtime exception | Resource vẫn được đóng |
| Mở resource thứ hai thất bại | Resource thứ nhất được đóng |
| Cả business operation và `close()` cùng lỗi | Primary giữ nguyên, lỗi đóng ở `getSuppressed()` |
| Nhiều resource cùng đóng lỗi | Thứ tự đóng đảo, suppressed đúng |
| Caller chỉ mượn resource | Method không đóng resource của caller |
| Callback/tác vụ dùng resource sau khi scope đóng | Thiết kế phải từ chối hoặc kéo dài scope có chủ đích |
| Executor chứa task không chịu dừng | Có timeout/cancellation/giám sát thay vì treo vô hạn |
| Lặp lại operation hàng nghìn lượt | Số resource in-use trở về baseline phù hợp |

## 16. Thiết kế scope tài nguyên trong code bất đồng bộ

Một trong những sai lầm khó phát hiện là **đóng resource trước khi tác vụ nền dùng xong**:

```java
// SAI nếu task chạy sau khi try đã đóng reader:
// try (var reader = Files.newBufferedReader(path)) {
//     executor.submit(() -> consume(reader));
// }
```

Đây không phải vấn đề `try-with-resources` hoạt động sai; **scope sở hữu resource quá ngắn** so với vòng đời task. Có hai hướng chính:

1. **Chờ task kết thúc trước khi đóng** resource (khi tài nguyên được thiết kế an toàn cho thread/task đó).
2. **Để task tự tạo và sở hữu resource của mình**, sau đó tự đóng trong chính task.

Ví dụ cách thứ hai:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class AsyncResourceDemo {
    static long count(Path path) throws IOException {
        try (var lines = Files.lines(path)) {
            return lines.count();
        }
    }

    public static void main(String[] args) throws Exception {
        Path path = Path.of("input.txt");

        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Long> task = executor.submit(() -> count(path));
            System.out.println(task.get());
        }
    }
}
```

Task sở hữu `Files.lines` do chính nó mở; reader/stream luôn đóng khi task thoát, kể cả trường hợp có exception. Executor chỉ được đóng khi tác vụ đã hoặc đang hoàn tất theo contract của `ExecutorService.close()`. Với code async phức tạp, quản lý thêm cancellation, deadline và cleanup rõ ràng cho từng task.

## 17. Ví dụ tổng hợp: đọc file, lọc dữ liệu và đóng mọi scope

Chương trình dưới đây dùng một stream gắn với file, xử lý từng dòng và trả kết quả materialized. Nó thể hiện *mở — dùng — đóng* mà không giữ stream thoát khỏi method.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Objects;

public class ResourceLifecycleExample {
    static List<String> loadNonBlankLines(Path path) throws IOException {
        Objects.requireNonNull(path, "path");

        try (var lines = Files.lines(path)) {
            return lines
                .map(String::strip)
                .filter(line -> !line.isEmpty())
                .toList();
        }
    }

    public static void main(String[] args) throws IOException {
        Path path = Path.of("app.log");
        List<String> data = loadNonBlankLines(path);

        System.out.println("Loaded lines: " + data.size());
    }
}
```

**Đường chạy:** `Files.lines` mở resource → stream pipeline đọc dữ liệu → `toList()` hoàn tất → `lines.close()` được gọi → method trả một list không lệ thuộc reader/stream.

**Giới hạn:** Nếu `app.log` rất lớn, `toList()` có thể tốn nhiều heap. Với dữ liệu lớn, hãy xử lý theo batch hoặc đọc dần trong scope `try` mà không gom tất cả vào bộ nhớ. Muốn viết output, hãy tách trách nhiệm xử lý thành phương thức nhận `BufferedWriter` mượn từ scope phía trên hoặc có một scope writer cùng với reader, tránh mở và đóng output mới cho từng dòng.

## 18. Bảng lỗi thường gặp

| Sai lầm | Hậu quả | Thay thế đúng |
| --- | --- | --- |
| Không đóng `Files.lines()` sau terminal operation | Descriptor có thể còn mở | `try (var lines = Files.lines(path)) { ... }` |
| Trông chờ GC đóng connection | Pool có thể cạn trước khi GC diễn ra | Đóng tại scope mượn từ pool |
| Dùng `finalize()` để cleanup | Không có bảo đảm thời điểm; API lỗi thời | `AutoCloseable` và `try-with-resources` |
| Tự viết `finally` để đóng nhiều resource nhưng bỏ qua suppressed | Mất thông tin nguyên nhân gốc | Dùng `try-with-resources` |
| Đóng resource caller còn sử dụng | Gây lỗi “closed” về sau | Quy định ownership rõ |
| Trả stream gắn với file nhưng không ghi rõ ai đóng | Người gọi có thể bỏ quên resource | Trả dữ liệu hoặc tài liệu hóa owner |
| Executor được tạo trên mỗi request nhưng không shutdown | Tăng thread/queue và giữ các tác vụ | Gắn lifecycle với scope phù hợp |
| Đóng resource trước khi task async kết thúc | Task đọc vào resource đã đóng | Task sở hữu resource hoặc await trước close |
| Lấy heap ổn định làm bằng chứng không leak | Bỏ qua native/descriptor leak | Theo dõi metric đúng loại tài nguyên |
| Dùng NMT để đếm mọi file descriptor | NMT không đo loại tài nguyên đó | Dùng OS-level handles/FD metrics |
| Quên xử lý lỗi `close()` của writer | Có thể bỏ sót lỗi flush/output | Báo/truyền `IOException`; quản lý output transaction |
| Dùng try-with-resources với resource dùng chung toàn app ở scope request | Đóng tài nguyên sớm | Chuyển việc đóng sang application shutdown |

## 19. Checklist áp dụng cho một API mới

Trước khi coi một luồng xử lý tài nguyên là an toàn, hãy kiểm tra:

1. **Tài nguyên đang được mở ở đâu?** Có đường cấp phát/mượn được kiểm soát không?
2. **Ai là owner?** Resource được mượn hay ownership đã được chuyển giao?
3. **Scope sử dụng dài bao lâu?** Có callback, task hoặc coroutine/virtual thread dùng sau khi method trả về không?
4. **Mọi nhánh thành công, exception và early return đều đóng đúng không?**
5. **Nếu có nhiều resource, thứ tự đóng có phù hợp dependency không?**
6. **Exception khi close được quan sát hay lưu dưới suppressed exception không?**
7. **Transaction, flush và commit có yêu cầu riêng với close không?**
8. **Có resource pool không?** Metric active/idle/pending có trở về mức bình thường không?
9. **Có file/network/native memory không?** Đã chọn bộ đếm và công cụ chẩn đoán đúng chưa?
10. **Có test lặp, test exception, test async/cancellation không?**
11. **Tài nguyên chứa dữ liệu nhạy cảm không?** Log, JFR recording và heap dump đã được bảo vệ chưa?
12. **Có dựa vào finalizer/GC để đóng không?** Nếu có, cần thiết kế lại bằng lifecycle tường minh.

**Nguyên tắc kết luận:** *Tạo ở đâu chưa đủ; phải biết ai sở hữu, được sử dụng đến khi nào, đóng ra sao khi có lỗi và làm thế nào đo được rằng tài nguyên đã được trả lại.* Java 27 cung cấp `AutoCloseable` và `try-with-resources` để biến trách nhiệm đó thành một phần rõ ràng của cấu trúc chương trình.

## Tài liệu tham khảo chính thức

- [Java SE 27 API — AutoCloseable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/AutoCloseable.html): contract đóng tài nguyên, ngoại lệ và `try-with-resources`.
- [Java SE 27 API — Closeable](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/io/Closeable.html): hợp đồng đóng tài nguyên I/O.
- [Java Language Specification 27 — §14.20.3 try-with-resources](https://docs.oracle.com/javase/specs/jls/se27/html/jls-14.html#jls-14.20.3): thứ tự đóng, primary và suppressed exceptions.
- [Java SE 27 API — Files](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/file/Files.html): `lines`, `list`, `walk`, các API mở stream từ filesystem.
- [Java SE 27 API — ExecutorService](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ExecutorService.html): `close`, shutdown, termination.
- [Java SE 27 API — Arena](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/Arena.html): scope và lifetime native memory.
- [Java SE 27 API — Cleaner](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ref/Cleaner.html): cleanup không mang bảo đảm thời gian.
- [Java SE 27 — The jcmd Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html): Flight Recorder và Native Memory Tracking.
- [Java SE 27 — The java Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): tùy chọn `-XX:NativeMemoryTracking`.
- [Oracle Java SE 27 Troubleshooting — Diagnostic Tools](https://docs.oracle.com/en/java/javase/27/troubleshoot/diagnostic-tools.html): JFR, JMC và chẩn đoán native memory.
