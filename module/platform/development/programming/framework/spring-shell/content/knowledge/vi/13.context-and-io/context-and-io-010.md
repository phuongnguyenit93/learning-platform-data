# Dọn tài nguyên nhập xuất mà lệnh thực sự sở hữu

Một command Spring Shell có thể đọc file, ghi báo cáo, mở kết nối hoặc ghi nội dung lên terminal. Mỗi tài nguyên cần có một chủ sở hữu rõ ràng để biết ai chịu trách nhiệm đóng nó và đóng vào thời điểm nào.

Quy tắc cốt lõi:

- Command mở file hoặc stream cho riêng lần gọi của nó thì command phải đóng.
- Command nhận một stream do nơi khác mở thì mặc định chỉ mượn stream đó; không tự ý đóng.
- Terminal, writer, reader và các bean do Spring Shell/Spring quản lý là tài nguyên dùng chung theo vòng đời ứng dụng; command chỉ sử dụng, flush khi cần và không đóng.
- Khi quyền sở hữu được chuyển cho một tác vụ bất đồng bộ hoặc một thành phần khác, hợp đồng chuyển giao phải nói rõ ai sẽ đóng tài nguyên.

Bài học dùng Java 17 và Spring Shell 3.3.x. Phần I/O của shell dựa trên JLine `Terminal`, `CommandContext` và cơ chế command registration của Spring Shell 3.3.

## 1. Vì sao phải xác định quyền sở hữu?

Tài nguyên I/O thường đại diện cho một handle bên ngoài bộ nhớ Java: file descriptor, socket, kết nối, pipe hoặc terminal. Garbage Collector quản lý bộ nhớ heap, nhưng không thay thế việc giải phóng các handle này.

Nếu không đóng tài nguyên do command mở, ứng dụng có thể gặp:

- File bị giữ mở, không thể đổi tên hoặc xóa trên một số hệ điều hành.
- Socket và kết nối bị chiếm dụng, làm cạn connection pool hoặc giới hạn file descriptor.
- File tạm tích tụ sau nhiều lần chạy.
- Buffer chưa được flush khiến dữ liệu đầu ra bị thiếu.
- Tác vụ chạy nền tiếp tục giữ stream sau khi command đã kết thúc.

Nếu command đóng tài nguyên dùng chung, lỗi xảy ra theo chiều ngược lại:

- Terminal của shell bị đóng và những command sau không thể ghi output.
- Reader dùng cho vòng lặp shell không thể tiếp tục đọc input.
- `System.in`, `System.out` hoặc `System.err` bị đóng cho toàn bộ tiến trình.
- Bean dùng chung bị đưa vào trạng thái không thể tái sử dụng.

Do đó, câu hỏi đầu tiên không phải là “đối tượng này có phương thức `close()` không?”, mà là “ai đã mở nó và ai đang chịu trách nhiệm cho vòng đời của nó?”.

## 2. Phân loại tài nguyên theo quyền sở hữu

Có thể phân loại tài nguyên mà command sử dụng thành ba nhóm:

| Nhóm | Ví dụ | Trách nhiệm của command |
|---|---|---|
| Owned — command sở hữu | `Files.newInputStream(path)`, `Files.newBufferedWriter(path)`, `Socket` do command tạo, `Connection` lấy trực tiếp từ `DataSource` | Đóng khi hoàn tất |
| Borrowed — command mượn | `CommandContext.getTerminal()`, `Terminal.writer()`, `System.in`, `System.out`, stream được truyền vào từ caller | Không đóng; chỉ sử dụng theo hợp đồng |
| Transferred — đã chuyển quyền | Stream được giao cho một worker hoặc object khác chịu trách nhiệm kết thúc | Bên nhận phải đóng; bên chuyển không tiếp tục dùng hoặc đóng |

Một số API trả về object không phải tài nguyên dù nó mô tả tài nguyên. Ví dụ `Path` chỉ là đường dẫn, `ResourceLoader` là dịch vụ dùng chung và `DataSource` là factory quản lý connection. Gọi `close()` trên stream được mở từ `Resource` hoặc connection được lấy từ `DataSource` là việc khác với đóng chính `Resource` hay `DataSource`.

Hãy ghi rõ hợp đồng trong tên biến, JavaDoc hoặc chữ ký method:

~~~java
// Caller mở và đóng stream; method này chỉ mượn để đọc.
long countRows(InputStream borrowedInput) throws IOException;

// Method tự mở file và chịu trách nhiệm đóng stream.
long countRows(Path inputFile) throws IOException;
~~~

Hợp đồng này giúp người gọi biết mình phải giữ stream mở đến khi nào và tránh hai nơi cùng đóng một tài nguyên.

## 3. Dùng try-with-resources cho tài nguyên command mở

Các lớp như `InputStream`, `OutputStream`, `Reader`, `Writer`, `Connection`, `Statement` và nhiều stream khác triển khai `AutoCloseable` hoặc `Closeable`. Java cung cấp `try-with-resources` để tự gọi `close()` khi rời khỏi khối lệnh, dù khối lệnh kết thúc bình thường hay ném exception.

Ví dụ đọc file:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public long countRows(Path file) throws IOException {
    try (BufferedReader reader =
            Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
        return reader.lines().count();
    }
}
~~~

Command mở `BufferedReader` từ file nên command sở hữu reader. Khi `count()` hoàn tất hoặc ném lỗi, reader được đóng và file handle được giải phóng.

Không cần viết `reader.close()` trong `finally` nếu đã dùng `try-with-resources`. Cấu trúc này cũng xử lý đúng trường hợp thân `try` và `close()` cùng phát sinh exception: lỗi trong thân `try` được giữ làm lỗi chính, lỗi khi đóng được ghi thành suppressed exception.

### 3.1. Đóng theo thứ tự ngược

Khi khai báo nhiều tài nguyên, Java đóng chúng theo thứ tự ngược với thứ tự khai báo:

~~~java
try (DataInputStream data = new DataInputStream(
        new BufferedInputStream(Files.newInputStream(file)))) {

    return data.readInt();
}
~~~

Ở ví dụ này, chỉ khai báo wrapper ngoài cùng. `data.close()` đóng `buffered`, rồi `buffered.close()` đóng stream file. Nếu có nhiều tài nguyên độc lập, Java đóng chúng theo thứ tự ngược với thứ tự khai báo:

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {
    input.transferTo(output);
}
~~~

Trong ví dụ thứ hai, `output` được đóng trước `input`. Hãy tránh khai báo riêng cả wrapper lẫn stream bên dưới nếu wrapper đã chịu trách nhiệm đóng stream đó.

### 3.2. Không dựa vào garbage collection

Để một stream ra khỏi scope hoặc gán biến thành `null` không bảo đảm file/socket được giải phóng đúng lúc. Garbage Collector có thể chạy muộn hoặc không chạy trong khoảng thời gian ứng dụng cần tài nguyên. Hãy đóng tài nguyên ngay khi không còn sử dụng.

## 4. Đọc file và stream theo cách đúng

Các API `Files` có hành vi vòng đời khác nhau:

| API | Giá trị trả về | Có cần command đóng? |
|---|---|---|
| `Files.readString(path)` | `String` | Không; API tự đóng file |
| `Files.readAllBytes(path)` | `byte[]` | Không; API tự đóng file |
| `Files.readAllLines(path)` | `List<String>` | Không; API tự đóng file |
| `Files.newInputStream(path)` | `InputStream` | Có |
| `Files.newBufferedReader(path)` | `BufferedReader` | Có |
| `Files.newOutputStream(path)` | `OutputStream` | Có |
| `Files.newBufferedWriter(path)` | `BufferedWriter` | Có |
| `Files.lines(path)` | `Stream<String>` giữ file đang mở | Có |
| `Files.list(path)` / `Files.walk(path)` | `Stream<Path>` giữ directory handle | Có |

Với file nhỏ, `readString` hoặc `readAllLines` thuận tiện vì API tự đóng file. Với file lớn, nên xử lý theo luồng và đóng stream:

~~~java
public long countMatchingLines(Path file, String keyword)
        throws IOException {
    try (var lines = Files.lines(file, StandardCharsets.UTF_8)) {
        return lines.filter(line -> line.contains(keyword)).count();
    }
}
~~~

`Files.lines()` đọc lazy và giữ file mở trong suốt thời gian stream được tiêu thụ. Gọi `count()` xong nhưng không đóng stream vẫn có thể giữ file handle. `Files.walk()` và `Files.list()` cũng cần được đặt trong `try-with-resources`.

Đừng trả một stream dựa trên file đã đóng ra khỏi method:

~~~java
// Sai: stream được trả ra nhưng file đã đóng khi method kết thúc.
public Stream<String> lines(Path file) throws IOException {
    try (var lines = Files.lines(file)) {
        return lines.filter(line -> !line.isBlank());
    }
}
~~~

Nếu muốn trả stream cho caller, phải chuyển giao quyền sở hữu và để caller đóng:

~~~java
// Hợp đồng: caller phải đóng Stream được trả về.
public Stream<String> openLines(Path file) throws IOException {
    return Files.lines(file, StandardCharsets.UTF_8)
            .filter(line -> !line.isBlank());
}
~~~

Caller sử dụng:

~~~java
try (Stream<String> lines = openLines(file)) {
    lines.forEach(System.out::println);
}
~~~

Trong command Spring Shell, thường đơn giản và an toàn hơn khi tiêu thụ stream hoàn toàn bên trong method rồi trả về một kết quả đã tính.

## 5. Wrapper có thể đóng cả tài nguyên bên dưới

Các wrapper thường chuyển tiếp thao tác `close()` xuống stream/reader/writer được bọc:

- `BufferedReader.close()` đóng reader bên dưới.
- `InputStreamReader.close()` đóng input stream bên dưới.
- `BufferedOutputStream.close()` flush và đóng output stream bên dưới.
- `PrintWriter.close()` đóng writer bên dưới.
- `ZipInputStream.close()` đóng stream nguồn.

Vì vậy, đừng tạo wrapper rồi đưa vào `try-with-resources` nếu stream gốc thuộc caller:

~~~java
// Không an toàn nếu borrowedInput thuộc caller.
try (BufferedReader reader = new BufferedReader(
        new InputStreamReader(borrowedInput, StandardCharsets.UTF_8))) {
    return reader.readLine();
}
~~~

Khi khối `try` kết thúc, reader đóng `InputStreamReader`, rồi đóng luôn `borrowedInput`. Caller có thể không đọc tiếp được.

Nếu method chỉ mượn stream, hãy quy định rõ rằng method không đóng stream và không đóng wrapper. Nếu một thư viện bắt buộc tự đóng wrapper, có thể cung cấp wrapper không đóng stream gốc:

~~~java
import java.io.FilterInputStream;
import java.io.InputStream;

final class NonClosingInputStream extends FilterInputStream {

    NonClosingInputStream(InputStream delegate) {
        super(delegate);
    }

    @Override
    public void close() {
        // Caller vẫn sở hữu delegate.
    }
}
~~~

Chỉ dùng kiểu wrapper này khi hợp đồng mượn stream đã rõ. Không dùng nó để che một rò rỉ tài nguyên mà command thực sự sở hữu.

## 6. Không đóng Terminal và writer do Spring Shell cung cấp

Spring Shell 3.3.4 cho phép command ghi output thông qua `CommandContext` và JLine `Terminal`. `Terminal` là terminal của shell đang chạy; writer lấy từ nó là kênh output dùng chung.

Ví dụ với command registration dạng consumer:

~~~java
import org.springframework.shell.command.CommandRegistration;

CommandRegistration registration = CommandRegistration.builder()
        .command("report status")
        .withTarget()
            .consumer(context -> {
                var writer = context.getTerminal().writer();
                writer.println("Báo cáo đã sẵn sàng.");
                writer.flush();
            })
            .and()
        .build();
~~~

Ở đây command mượn `Terminal` và `PrintWriter`. Có thể gọi `flush()` để đẩy dữ liệu đang đệm ra terminal, nhưng không gọi `close()`:

~~~java
// Đúng: flush writer dùng chung.
writer.flush();

// Sai: có thể đóng output của toàn bộ shell.
writer.close();
~~~

Tương tự, không đóng `Terminal` lấy từ `CommandContext`, không đóng bean `Terminal` được inject và không đóng `System.out`/`System.err`. Vòng đời các đối tượng này thuộc shell hoặc tiến trình ứng dụng.

Nếu command chỉ cần trả một kết quả văn bản, ưu tiên trả về `String` để Spring Shell result handler hiển thị:

~~~java
@ShellMethod(key = "report status")
public String status() {
    return "Báo cáo đã sẵn sàng.";
}
~~~

Cách này tránh quản lý writer thủ công. Chỉ lấy writer trực tiếp khi cần ghi từng phần, hiển thị tiến trình hoặc xử lý output đặc biệt.

### 6.1. PrintWriter không ném IOException khi ghi

JDK `PrintWriter` ghi nhận lỗi nội bộ thay vì ném `IOException` từ các phương thức `print`, `println` hoặc `write`. Nếu cần phát hiện lỗi output:

~~~java
var writer = context.getTerminal().writer();
writer.println("Đang xuất báo cáo...");
writer.flush();

if (writer.checkError()) {
    throw new IllegalStateException("Không thể ghi output ra terminal.");
}
~~~

Không đóng writer sau khi kiểm tra lỗi. `checkError()` có thể flush và kiểm tra trạng thái lỗi; nó không chuyển quyền sở hữu writer sang command.

## 7. Input của shell cũng là tài nguyên dùng chung

Trong Spring Shell, vòng lặp shell nhận từng dòng input qua runner và các thành phần JLine. `CommandContext` 3.3.x cung cấp terminal của lần thực thi; shell và runner quản lý vòng đời terminal/input của ứng dụng.

Command không nên:

- Gọi `System.in.close()` hoặc đóng reader bọc quanh `System.in`.
- Đóng `LineReader` do cấu hình shell tạo và chia sẻ.
- Tạo một reader thứ hai đọc đồng thời từ cùng terminal trong khi shell vẫn quản lý input.
- Tự thay `System.in`, `System.out` hoặc `System.err` trong một command.

Đối với dữ liệu người dùng, ưu tiên khai báo argument/option của command để parser của Spring Shell nhận input. Với luồng tương tác nhiều bước, dùng component hoặc flow của Spring Shell để framework điều phối prompt và terminal.

Nếu ứng dụng tự tích hợp JLine `LineReader`, hãy xác định reader được tạo bởi command hay được Spring cấu hình dùng chung. Reader dùng chung là borrowed resource: command gọi API đọc nhưng không đóng reader hoặc terminal bên dưới.

Không nhầm `CommandContext` với một resource handle cần đóng. Context cung cấp dữ liệu của lần gọi command; việc nhận context không trao quyền sở hữu terminal hoặc input của shell.

## 8. Tách service xử lý dữ liệu khỏi service quản lý vòng đời stream

Một cách thiết kế dễ kiểm soát là để command mở file, còn service nhận reader/writer đã mở và chỉ thực hiện nghiệp vụ.

~~~java
@Service
public class CsvImportService {

    public int importRows(BufferedReader reader) throws IOException {
        int imported = 0;
        String line;

        while ((line = reader.readLine()) != null) {
            if (line.isBlank()) {
                continue;
            }
            // Parse và lưu bản ghi.
            imported++;
        }

        return imported;
    }
}
~~~

Command sở hữu reader vì command mở file:

~~~java
@ShellComponent
public class ImportCommands {

    private final CsvImportService importService;

    public ImportCommands(CsvImportService importService) {
        this.importService = importService;
    }

    @ShellMethod(key = "inventory import")
    public String importFile(Path file) throws IOException {
        try (BufferedReader reader =
                Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            int imported = importService.importRows(reader);
            return "Đã nhập " + imported + " dòng.";
        }
    }
}
~~~

Service không đóng reader. Hợp đồng của `importRows` là mượn reader trong thời gian method chạy. Command đóng reader khi service trả về hoặc ném exception.

Lợi ích của cách chia này:

- Service dễ unit test bằng `StringReader` hoặc reader giả.
- Command chịu trách nhiệm mở/đóng tài nguyên ở đúng ranh giới.
- Service không phụ thuộc vào đường dẫn file hoặc vòng đời shell.
- Một service có thể được gọi từ command, batch job hoặc test với các nguồn dữ liệu khác nhau.

Nếu service cần tự mở file, chuyển tham số thành `Path` và để service sở hữu stream. Đừng vừa truyền stream vừa yêu cầu service đóng khi command cũng nghĩ mình sở hữu stream.

## 9. Ghi file output và hoàn tất dữ liệu

Command mở writer để tạo báo cáo phải đóng writer sau khi ghi xong. `close()` sẽ flush dữ liệu còn trong buffer rồi giải phóng file handle:

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.List;

public void writeReport(Path output, List<String> rows)
        throws IOException {
    try (BufferedWriter writer = Files.newBufferedWriter(
            output,
            StandardCharsets.UTF_8,
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING,
            StandardOpenOption.WRITE)) {

        for (String row : rows) {
            writer.write(row);
            writer.newLine();
        }
    }
}
~~~

Các tùy chọn ở ví dụ có nghĩa:

- `CREATE`: tạo file nếu chưa có.
- `TRUNCATE_EXISTING`: xóa nội dung cũ trước khi ghi.
- `WRITE`: mở file để ghi.

Nếu không muốn ghi đè file cũ, dùng `CREATE_NEW` để thất bại khi file đã tồn tại. Việc chọn open option là một phần của hợp đồng command, không phải chi tiết có thể bỏ qua.

Với output lớn, không gom toàn bộ dữ liệu vào một `String` hoặc `byte[]` nếu có thể ghi theo từng bản ghi. Stream và buffer giúp kiểm soát bộ nhớ, còn `try-with-resources` bảo đảm file được đóng.

## 10. Dọn file tạm mà command tạo ra

Nếu command tạo file tạm để chuẩn bị kết quả, command phải xóa file đó khi không còn cần. Đặt file tạm trong cùng thư mục đích nếu cần di chuyển nguyên tử trên cùng filesystem.

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.List;

public void exportAtomically(Path target, List<String> rows)
        throws IOException {

    Path absoluteTarget = target.toAbsolutePath();
    Path directory = absoluteTarget.getParent();
    Files.createDirectories(directory);
    Path temporary = Files.createTempFile(
            directory, "report-", ".tmp");

    try {
        try (BufferedWriter writer = Files.newBufferedWriter(
                temporary, StandardCharsets.UTF_8)) {
            for (String row : rows) {
                writer.write(row);
                writer.newLine();
            }
        }

        try {
            Files.move(
                    temporary,
                    absoluteTarget,
                    StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
        }
        catch (AtomicMoveNotSupportedException ex) {
            Files.move(
                    temporary,
                    absoluteTarget,
                    StandardCopyOption.REPLACE_EXISTING);
        }
    }
    finally {
        Files.deleteIfExists(temporary);
    }
}
~~~

Writer được đóng trước khi file tạm được di chuyển. `finally` xóa file tạm nếu việc ghi hoặc di chuyển thất bại. Nếu di chuyển thành công, file tạm không còn ở đường dẫn cũ nên `deleteIfExists` không làm gì. Hỗ trợ thay thế file đích trong một thao tác `ATOMIC_MOVE` phụ thuộc filesystem provider; nếu cần bảo đảm hành vi khi file đích đã tồn tại, hãy kiểm thử trên filesystem triển khai.

Command chỉ xóa file tạm mà nó tạo ra. Không xóa file đầu vào do người dùng cung cấp, file dùng chung hoặc file output đã được bàn giao cho người dùng.

Nếu command trả về đường dẫn file tạm để một tác vụ khác sử dụng, quyền sở hữu file đã được chuyển giao. Bên nhận phải chịu trách nhiệm xóa nó sau khi dùng xong; command không được xóa ngay trong `finally`.

## 11. Kết nối do Spring quản lý và tài nguyên lấy từ factory

Một số object là factory hoặc client dùng chung; object được tạo ra từ chúng mới là tài nguyên của một thao tác.

| Đối tượng | Quyền sở hữu thông thường | Hành động |
|---|---|---|
| Spring `DataSource` bean | Application context | Không đóng trong command |
| `Connection` lấy từ `DataSource.getConnection()` | Command nếu tự lấy trực tiếp | Đóng để trả về pool |
| `PreparedStatement` | Command | Đóng |
| `ResultSet` | Command | Đóng |
| `JdbcTemplate` | Application context | Không đóng trong command; để template quản lý connection |
| `RestClient`/HTTP client bean | Application context | Không đóng sau mỗi command |
| `InputStream` của response body | Command nếu command lấy và đọc trực tiếp | Đóng sau khi xử lý |
| `ResourceLoader` hoặc `Resource` | Bean/descriptor | Không đóng `Resource`; đóng stream được mở từ `getInputStream()` |

Ví dụ JDBC khi command tự quản lý connection:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public int countActiveItems(DataSource dataSource) throws SQLException {
    String sql = "select count(*) from inventory where active = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setBoolean(1, true);

        try (ResultSet resultSet = statement.executeQuery()) {
            resultSet.next();
            return resultSet.getInt(1);
        }
    }
}
~~~

Đóng `Connection` lấy từ pool thường trả connection về pool, không nhất thiết đóng socket vật lý. Không gọi `dataSource.close()` trong command vì DataSource thuộc application context.

Nếu dùng `JdbcTemplate`, Spring quản lý việc lấy/đóng connection và statement. Không tự lấy thêm connection chỉ để đóng một tài nguyên mà framework đã quản lý.

## 12. Đóng response body và stream từ hệ thống bên ngoài

Khi HTTP client trả body dưới dạng `InputStream`, stream đó cần được đóng sau khi đọc. Client/factory có thể dùng chung, còn body stream gắn với một response cụ thể.

Ví dụ với JDK `HttpClient` và `BodyHandlers.ofInputStream()`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

HttpResponse<InputStream> response = httpClient.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    if (response.statusCode() >= 400) {
        throw new IOException("HTTP status " + response.statusCode());
    }

    Files.copy(body, target, StandardCopyOption.REPLACE_EXISTING);
}
~~~

Không giữ body stream mở sau khi command đã xử lý response. Với API HTTP khác, đọc tài liệu của body handler để biết body có được buffer tự động hay phải đóng thủ công.

Tương tự, stream lấy từ `Resource.getInputStream()` phải được đóng:

~~~java
try (InputStream input = resource.getInputStream()) {
    return new String(input.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

`Resource` mô tả vị trí tài nguyên; `InputStream` là handle được mở ra để đọc. Đóng stream, không đóng `ResourceLoader` hoặc bean quản lý tài nguyên.

## 13. Tài nguyên được truyền vào command hoặc service là borrowed

Một method nhận `InputStream` hoặc `OutputStream` từ caller nên mặc định không đóng chúng. Caller biết stream được mở từ đâu và còn cần dùng sau method hay không.

~~~java
public long copy(InputStream input, OutputStream output)
        throws IOException {
    return input.transferTo(output);
}
~~~

Method này không đóng `input` hoặc `output`. Caller sở hữu cả hai và quyết định vòng đời:

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(target)) {
    copyService.copy(input, output);
}
~~~

Nếu `copyService.copy` đóng output, caller có thể không ghi tiếp được. Nếu caller đóng stream trước khi service xử lý xong, service sẽ đọc/ghi trên tài nguyên đã đóng. Cần thống nhất rõ thời điểm bắt đầu và kết thúc quyền mượn.

Khi API cần nhận quyền sở hữu, hãy thể hiện rõ bằng tên hoặc tài liệu, ví dụ `consumeAndClose(InputStream ownedInput)`. Chỉ dùng kiểu này khi người gọi đồng ý chuyển giao quyền đóng.

## 14. Tác vụ bất đồng bộ và vòng đời tài nguyên

Không mở stream trong command rồi đóng nó trước khi worker bất đồng bộ hoàn tất:

~~~java
// Sai: stream bị đóng khi command method thoát, trong khi task vẫn đang đọc.
CompletableFuture<Void> startImport(Path file) throws IOException {
    try (InputStream input = Files.newInputStream(file)) {
        return CompletableFuture.runAsync(() -> importService.read(input));
    }
}
~~~

Mở tài nguyên bên trong tác vụ để tác vụ sở hữu và đóng nó:

~~~java
CompletableFuture<Integer> startImport(Path file) {
    return CompletableFuture.supplyAsync(() -> {
        try (BufferedReader reader = Files.newBufferedReader(
                file, StandardCharsets.UTF_8)) {
            return importService.importRows(reader);
        }
        catch (IOException ex) {
            throw new CompletionException(ex);
        }
    }, taskExecutor);
}
~~~

Trong ví dụ, worker mở reader, sử dụng và đóng reader trong cùng scope. Command không giữ một file handle sống lâu hơn method.

Nếu caller truyền một stream vào tác vụ bất đồng bộ, cần chọn một trong hai hợp đồng:

- Caller giữ stream mở và chờ future hoàn tất trước khi đóng.
- Caller chuyển quyền sở hữu stream cho worker; worker đóng stream trong `try-with-resources`.

Không để cả caller và worker cùng nghĩ mình sở hữu stream. Với tác vụ dài, bổ sung cơ chế hủy và timeout. Khi tác vụ kết thúc do exception hoặc cancellation, đảm bảo khối `try-with-resources` được thoát để giải phóng tài nguyên.

## 15. Hủy command và xử lý lỗi khi đang I/O

`try-with-resources` đóng tài nguyên khi luồng điều khiển rời khỏi khối `try`, kể cả khi có exception. Tuy nhiên, nó không tự tạo cơ chế hủy cho một thao tác I/O đang bị chặn vô thời hạn.

Với tác vụ dài:

- Dùng timeout cho network/database operation.
- Kiểm tra trạng thái interrupt hoặc cancellation token trong vòng lặp xử lý.
- Không nuốt `InterruptedException`; khôi phục interrupt status nếu chuyển exception.
- Giữ scope tài nguyên ngắn nhất có thể.
- Đảm bảo nhánh lỗi cũng đi qua `close()`.

Ví dụ:

~~~java
try (InputStream input = Files.newInputStream(file)) {
    byte[] buffer = new byte[8192];
    int count;

    while ((count = input.read(buffer)) != -1) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedIOException("Tác vụ đã bị hủy.");
        }
        processChunk(buffer, count);
    }
}
~~~

Khi phát hiện interrupt, exception làm thoát khối `try` và stream được đóng. Với một số loại I/O đang chặn, việc interrupt thread có thể không đủ để dừng ngay; cần dùng API hỗ trợ timeout hoặc cơ chế đóng socket/handle theo đúng chủ sở hữu.

## 16. Những việc command không nên làm

| Thao tác | Vì sao không nên | Cách làm đúng |
|---|---|---|
| `System.in.close()` | Đóng input của toàn tiến trình | Dùng option hoặc input API do shell quản lý |
| `System.out.close()` | Làm hỏng output của shell và các thành phần khác | Ghi qua result handler hoặc terminal writer |
| `context.getTerminal().close()` | Đóng terminal dùng chung | Chỉ dùng terminal và flush writer |
| `terminal.writer().close()` | Đóng writer dùng chung | Gọi `flush()` khi cần |
| Đóng `DataSource` bean | Làm hỏng connection pool cho command khác | Đóng connection lấy từ DataSource |
| Đóng `RestClient` dùng chung | Phá vòng đời client của application context | Đóng response body/stream theo API |
| Trả stream đã đóng | Caller không thể tiêu thụ kết quả | Chuyển giao stream còn mở và quy định caller phải đóng |
| Đóng stream borrowed | Caller mất quyền tiếp tục đọc/ghi | Không đóng hoặc dùng wrapper không đóng khi cần |
| Giữ stream trong singleton service | Tài nguyên sống lâu, khó quản lý và dễ xung đột | Mở/đóng trong scope của một lần thực thi |
| Xóa file do người dùng cung cấp | Vượt quyền sở hữu của command | Chỉ xóa file tạm do command tạo |

## 17. Kiểm thử việc đóng và không đóng tài nguyên

Kiểm thử I/O không chỉ xác nhận nội dung đúng. Cần xác nhận vòng đời tài nguyên đúng trong cả đường thành công và đường lỗi.

### 17.1. Dùng temporary directory

JUnit 5 cung cấp `@TempDir` để tạo thư mục tạm cho test:

~~~java
@Test
void commandReadsFileAndReleasesIt(@TempDir Path directory)
        throws Exception {
    Path file = directory.resolve("items.txt");
    Files.writeString(file, "A\nB\n", StandardCharsets.UTF_8);

    String result = commands.importFile(file);

    assertThat(result).contains("2");
    Files.delete(file);
    assertThat(Files.exists(file)).isFalse();
}
~~~

Test này kiểm tra kết quả và việc file có thể được xóa sau khi command kết thúc. Trên hệ điều hành có thể xóa file đang mở, nên bổ sung kiểm tra stream trực tiếp khi cần xác nhận hành vi close.

### 17.2. Theo dõi stream có được đóng hay không

Tạo stream giả có cờ ghi nhận `close()`:

~~~java
import java.io.ByteArrayInputStream;

final class TrackingInputStream extends ByteArrayInputStream {

    private boolean closed;

    TrackingInputStream(byte[] bytes) {
        super(bytes);
    }

    @Override
    public void close() {
        closed = true;
        super.close();
    }

    boolean isClosed() {
        return closed;
    }
}
~~~

Nếu method chỉ mượn stream, test phải xác nhận stream vẫn mở:

~~~java
@Test
void serviceDoesNotCloseBorrowedInput() throws Exception {
    TrackingInputStream input = new TrackingInputStream(
            "A\nB\n".getBytes(StandardCharsets.UTF_8));

    service.countRows(input);

    assertThat(input.isClosed()).isFalse();
}
~~~

Nếu command tự mở stream qua factory hoặc adapter, kiểm tra stream được đóng cả khi service ném exception. Có thể mock factory để trả `TrackingInputStream`, sau đó gọi command và xác nhận `isClosed()` là `true`.

### 17.3. Kiểm tra writer của terminal vẫn dùng được

Với command ghi qua terminal, dùng terminal test hoặc mock để xác nhận command gọi `flush()` nhưng không gọi `close()`. Một command không được làm cho command kế tiếp mất khả năng ghi output.

### 17.4. Kiểm tra đường lỗi

Tạo input stream ném `IOException` sau một số byte, rồi xác nhận:

- Exception được chuyển thành kết quả lỗi phù hợp.
- Stream đã mở được đóng.
- File tạm được xóa nếu command tạo file tạm.
- Không có output dở dang được công bố như một báo cáo hoàn chỉnh.

## 18. Các lỗi thường gặp khi quản lý vòng đời

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| File không thể xóa sau command | Reader hoặc stream chưa được đóng | Dùng `try-with-resources` quanh stream mở từ file |
| Các command sau không ghi được output | Command đã đóng terminal writer | Chỉ flush writer dùng chung |
| Shell không đọc được dòng tiếp theo | Command đóng input/LineReader dùng chung | Để shell runner quản lý input |
| Connection pool cạn | Connection lấy từ DataSource không được đóng | Đóng `Connection`, `Statement`, `ResultSet` |
| Service dùng stream đã đóng | Command đóng stream trước khi service hoàn tất | Giữ scope bao trùm toàn bộ thao tác |
| Worker nền báo stream closed | Command trả về và đóng stream trước khi worker xong | Mở tài nguyên trong worker hoặc chuyển giao quyền sở hữu |
| File tạm còn sau lỗi | Cleanup chỉ nằm ở nhánh thành công | Xóa trong `finally` |
| Output thiếu phần cuối | Writer do command mở chưa được flush/close | Đóng writer thuộc command; flush writer mượn |
| Lỗi đóng che mất lỗi xử lý | Tự đóng trong `finally` và ghi đè exception gốc | Dùng `try-with-resources` |
| File stream bị giữ dù đã gọi `count()` | `Files.lines()` hoặc `Files.walk()` chưa được đóng | Đặt stream trong `try-with-resources` |

## 19. Quy trình quyết định ai phải đóng

Trước khi thêm `close()`, trả lời lần lượt:

1. Ai đã tạo hoặc mở tài nguyên?
2. API có tài liệu nói quyền sở hữu được chuyển cho caller không?
3. Tài nguyên có được Spring Shell/Spring quản lý theo vòng đời ứng dụng không?
4. Có wrapper nào sẽ đóng tài nguyên bên dưới không?
5. Tài nguyên được dùng đồng bộ hay còn được worker khác sử dụng?
6. Khi command trả về hoặc ném exception, ai sẽ đóng?
7. Nếu file tạm hoặc stream được trả ra ngoài, bên nhận có nhận trách nhiệm đóng/xóa không?

Sau đó áp dụng:

- Tài nguyên do command mở: đặt trong `try-with-resources`.
- Tài nguyên mượn: không đóng; flush nếu đó là output cần đẩy ra.
- Tài nguyên chuyển giao: ghi rõ bên nhận phải đóng và không dùng tiếp ở bên chuyển.
- Tài nguyên Spring-managed: để application context quản lý; chỉ đóng handle riêng được cấp từ factory.
- File tạm do command tạo: xóa trong `finally`, trừ khi đã chuyển giao quyền sở hữu.

## 20. Tổng kết

Quản lý I/O trong Spring Shell bắt đầu từ quyền sở hữu. Command phải đóng file, stream, response body, JDBC handle và file tạm mà nó tự mở hoặc tạo. Command chỉ mượn terminal, writer, input và các bean dùng chung; không đóng những tài nguyên đó.

`try-with-resources` là cách mặc định cho tài nguyên `AutoCloseable` thuộc command vì nó đóng cả khi method trả về hoặc gặp exception. Hãy chú ý wrapper có thể đóng stream bên dưới, `Files.lines()`/`Files.walk()` giữ handle trong stream lazy, và tác vụ bất đồng bộ có vòng đời tài nguyên riêng.

Với Spring Shell 3.3.x, `CommandContext.getTerminal()` cung cấp terminal của shell. Ghi output qua writer, gọi `flush()` khi cần và để shell quản lý vòng đời terminal. Khi command tách rõ tài nguyên sở hữu và tài nguyên mượn, các lần chạy liên tiếp ổn định hơn, file/socket không bị rò rỉ và service dễ kiểm thử hơn.

## Tài liệu tham khảo

- [Spring Shell 3.3.4 — Writing](https://docs.spring.io/spring-shell/reference/3.3/commands/writing.html) — ghi output qua `CommandContext` và JLine `Terminal`.
- [Spring Shell 3.3.0 — CommandContext API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/command/CommandContext.html) — thông tin lần thực thi command và truy cập terminal.
- [Spring Shell 3.3.0 — Shell API](https://docs.spring.io/spring-shell/docs/3.3.0/api/org/springframework/shell/Shell.html) — vòng lặp nhận input và đánh giá command.
- [Java 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html) — hợp đồng đóng tài nguyên và `try-with-resources`.
- [The Java Tutorials — The try-with-resources Statement](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html) — đóng tự động, thứ tự đóng và suppressed exceptions.
- [Java 17 — Files API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — stream file, directory stream và API tự đóng file.
- [Java 17 — Stream API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html) — stream từ I/O channel cần được đóng.
- [Java 17 — PrintWriter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html) — `flush()`, `close()` và `checkError()`.
