# Vòng đời tài nguyên và dọn dẹp trên mọi đường đi

Một chương trình có thể chạy đúng hàng nghìn lần nhưng dần chậm đi rồi ngừng phục vụ vì mỗi yêu cầu để sót một kết nối cơ sở dữ liệu, một tệp đang mở hoặc một giấy phép của semaphore. Ngược lại, đóng tài nguyên quá sớm có thể khiến công việc bất đồng bộ thất bại dù luồng gọi ban đầu đã trả về bình thường. Để xây dựng mã nguồn đáng tin cậy, cần quản lý **toàn bộ vòng đời tài nguyên**, từ lúc tạo hoặc mượn cho tới khi giải phóng đúng cách.

Trong chương **Độ tin cậy** của module **CODE_QUALITY_FUNDAMENTALS**, chủ đề này giúp hiểu những thuộc tính làm cho mã nguồn **đáng tin cậy, dễ hiểu và dễ thay đổi**. Trọng tâm là bảo đảm tài nguyên được dọn dẹp trên mọi đường đi: thành công, trả về sớm, ngoại lệ, hủy tác vụ và lỗi khi khởi tạo một phần.

## 1. Tài nguyên và vòng đời tài nguyên

**Tài nguyên** (*resource*) là đối tượng hoặc năng lực hữu hạn mà chương trình phải quản lý trong quá trình hoạt động. Nhiều tài nguyên cần thao tác giải phóng rõ ràng, vì việc một đối tượng Java không còn được tham chiếu không đồng nghĩa tài nguyên bên ngoài được trả lại ngay lập tức.

| Loại tài nguyên | Khi được sử dụng | Cách giải phóng thường gặp | Hậu quả nếu giữ quá lâu |
| --- | --- | --- | --- |
| Tệp, stream | Đọc/ghi dữ liệu | Đóng stream hoặc reader/writer | Cạn file descriptor, dữ liệu ghi chưa được flush |
| Kết nối cơ sở dữ liệu | Truy vấn, giao dịch | Đóng kết nối hoặc trả về pool theo hợp đồng | Cạn connection pool, yêu cầu sau phải chờ |
| Socket, kết nối mạng | Giao tiếp qua mạng | Đóng socket/stream theo giao thức | Rò rỉ socket, giữ bộ đệm và kết nối |
| Khóa (*lock*) | Bảo vệ vùng dữ liệu chung | Mở khóa tương ứng | Deadlock hoặc các luồng khác chờ mãi |
| Giấy phép semaphore | Giới hạn số công việc đồng thời | Trả giấy phép đã lấy | Công việc mới không thể được phép chạy |
| Executor hoặc thread pool do thành phần sở hữu | Thực thi công việc nền | Dừng nhận việc và kết thúc các tác vụ theo chính sách | Giữ thread hoạt động, tiến trình khó dừng |
| Tệp tạm | Lưu dữ liệu trung gian | Xóa sau khi sử dụng hoặc theo chính sách lưu giữ | Đầy đĩa, để lại dữ liệu nhạy cảm |
| Ngữ cảnh gắn với thread | Truyền thông tin trong một tác vụ | Xóa hoặc khôi phục ngữ cảnh | Dữ liệu của yêu cầu cũ ảnh hưởng yêu cầu mới |

Cần phân biệt **đối tượng Java** với **tài nguyên hữu hạn bên dưới**. Garbage collector chủ yếu quản lý bộ nhớ của các đối tượng có thể thu hồi; không nên dựa vào thời điểm GC hoặc finalizer để bảo đảm đóng tệp, trả kết nối hay mở khóa. Những hoạt động này cần ranh giới vòng đời rõ ràng.

### 1.1. Bốn giai đoạn

~~~text
Chưa sở hữu
     |
     | acquire / open
     v
Đã sở hữu và đang sử dụng
     |
     | hoàn tất, lỗi, return sớm, bị hủy
     v
Đang dọn dẹp
     |
     | close / release / delete
     v
Đã giải phóng
~~~

Khi thực hiện **acquire**, chương trình phải biết ai có trách nhiệm **release**. Ranh giới đó quyết định tài nguyên có được giải phóng đúng thời điểm và đúng một lần theo hợp đồng hay không.

Ba lỗi điển hình là:

- **Rò rỉ:** đã cấp phát nhưng không giải phóng trên một đường thực thi.
- **Giải phóng quá sớm:** tài nguyên bị đóng trước khi người dùng cuối cùng hoàn tất công việc.
- **Sử dụng sau giải phóng hoặc giải phóng sai chủ sở hữu:** mã tiếp tục đọc stream đã đóng, trả giấy phép chưa lấy hoặc một hàm phụ đóng đối tượng dùng chung.

## 2. “Mọi đường đi” bao gồm những gì?

Đường đi bình thường chỉ là một phần của chương trình. Ví dụ:

~~~java
InputStream input = Files.newInputStream(path);
String header = readHeader(input);

if (header.isBlank()) {
    return; // input chưa được đóng.
}

process(input); // Có thể ném IOException.
input.close();
~~~

Đoạn mã có thể rò rỉ tài nguyên khi **return** sớm hoặc khi **readHeader/process** ném ngoại lệ. Ngoài ra, việc mở stream có thể thành công nhưng một bước khởi tạo tiếp theo thất bại; không được quên đóng những tài nguyên đã mở trước đó.

Khi review mã quản lý tài nguyên, cần xét những đường đi sau:

| Tình huống | Câu hỏi |
| --- | --- |
| Hoàn thành bình thường | Tài nguyên có được đóng sau lần sử dụng cuối cùng? |
| Return sớm | Có nhánh nào bỏ qua dọn dẹp? |
| Ngoại lệ trong xử lý | Có cơ chế dọn dẹp ngay cả khi không đi tới dòng cuối? |
| Ngoại lệ trong lúc đóng | Lỗi xử lý gốc có được bảo toàn? |
| Mở nhiều tài nguyên | Nếu mở tài nguyên thứ hai thất bại, tài nguyên thứ nhất có được đóng? |
| Hủy hoặc ngắt tác vụ | Có đóng tài nguyên và xử lý tín hiệu ngắt đúng chính sách? |
| Công việc bất đồng bộ | Có đóng trước khi tác vụ thực sự hoàn thành không? |
| Tài nguyên dùng chung | Có thành phần nào đóng nhầm tài nguyên mà nó không sở hữu? |

Không thể bảo đảm mọi tình huống như tiến trình bị hệ điều hành buộc dừng bằng một khối **finally** trong Java. Khi cần phục hồi sau crash, phải kết hợp cơ chế của hệ điều hành, lưu trữ bền vững, giao dịch hoặc quy trình dọn dẹp khi khởi động lại.

## 3. Try-with-resources: cách chuẩn với AutoCloseable

Java cung cấp cú pháp **try-with-resources** cho đối tượng triển khai **AutoCloseable** hoặc **Closeable**. Tài nguyên được đóng tự động khi thoát khỏi khối try, kể cả khi có return sớm hoặc ngoại lệ.

### 3.1. Ví dụ đọc tệp an toàn

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class LineCounter {
    public long countNonEmptyLines(Path path) throws IOException {
        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
            long count = 0;
            String line;

            while ((line = reader.readLine()) != null) {
                if (!line.isBlank()) {
                    count++;
                }
            }

            return count;
        }
    }
}
~~~

Khi chạy hết tệp, phương thức trả về số dòng không rỗng; **reader.close()** vẫn được thực hiện. Nếu **readLine()** ném **IOException**, Java cũng cố gắng đóng reader trước khi ngoại lệ được truyền cho bên gọi.

Đặt tài nguyên ngay trong phần khai báo của try làm **vòng đời của nó hiển thị rõ cho người đọc**: tài nguyên thuộc phạm vi khối này và sẽ được giải phóng khi ra khỏi khối.

### 3.2. Nhiều tài nguyên được đóng theo thứ tự ngược

~~~java
try (InputStream input = Files.newInputStream(source);
     OutputStream output = Files.newOutputStream(destination)) {
    input.transferTo(output);
}
~~~

Trong ví dụ trên:

1. **input** được mở trước.
2. **output** được mở sau.
3. Khi thoát khối, Java đóng **output** trước, sau đó đóng **input**.
4. Nếu mở **output** thất bại, **input** đã mở vẫn được Java đóng.

Đây là lợi thế lớn so với nhiều lệnh đóng thủ công ở cuối phương thức. Lưu ý: đối với ghi tệp, **close()** có thể phát hiện lỗi flush/ghi muộn. Không nên báo thành công cho một thao tác lưu quan trọng trước khi việc đóng và kiểm tra lỗi hoàn tất.

### 3.3. Ngoại lệ chính và ngoại lệ khi đóng

Giả sử xử lý tệp ném **IOException A**, rồi quá trình đóng tệp cũng ném **IOException B**. Với try-with-resources, **A** được giữ làm ngoại lệ chính, còn **B** thường được gắn vào danh sách **suppressed exceptions** của A.

~~~java
try (AutoCloseable resource = openResource()) {
    process(resource);
} catch (Exception error) {
    log(error);
    for (Throwable suppressed : error.getSuppressed()) {
        log(suppressed);
    }
    throw error;
}
~~~

**openResource**, **process** và **log** ở đây là các hàm minh họa. Điểm cần nhớ là **error.getSuppressed()** giúp chẩn đoán cả lỗi làm tác vụ thất bại lẫn lỗi phát sinh khi dọn dẹp; đây không phải danh sách nguyên nhân từ **getCause()**.

Nếu không có ngoại lệ nào trong thân try nhưng **close()** thất bại, ngoại lệ từ close trở thành lỗi cần xử lý. Vì vậy “đã đi hết thân try” chưa đủ để tuyên bố thao tác thành công.

## 4. Finally: dành cho tài nguyên không dùng AutoCloseable

Không phải tài nguyên nào cũng có phương thức close. Với một số tài nguyên như **Lock** hoặc **Semaphore**, cần cặp **acquire/release** rõ ràng. **finally** là công cụ phù hợp vì nó chạy khi khối try thoát bình thường hoặc bằng ngoại lệ trong điều kiện JVM vẫn tiếp tục thực thi.

### 4.1. Khóa phải được mở trên mọi đường đi

~~~java
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantLock;

public final class Counter {
    private final Lock lock = new ReentrantLock();
    private long value;

    public void increment() {
        lock.lock();
        try {
            value = Math.addExact(value, 1L);
        } finally {
            lock.unlock();
        }
    }
}
~~~

Nếu **Math.addExact** phát hiện tràn số và ném ngoại lệ, khóa vẫn được mở. Nếu chỉ gọi **unlock()** sau thân try, đường đi ngoại lệ sẽ làm các luồng khác có thể bị chặn vô hạn.

Thứ tự chính xác là **chiếm khóa thành công rồi mới vào try/finally**. Với **lockInterruptibly()**, ngoại lệ **InterruptedException** có thể xảy ra trước khi chiếm khóa; nếu đặt lời gọi này bên trong khối mà finally luôn mở khóa, chương trình có thể mở một khóa mà nó chưa nắm giữ.

### 4.2. Chỉ trả giấy phép semaphore đã lấy được

~~~java
import java.util.concurrent.Semaphore;

public final class LimitedOperation {
    private final Semaphore permits = new Semaphore(5);

    public void execute() throws InterruptedException {
        permits.acquire(); // Có thể bị ngắt trước khi lấy giấy phép.
        try {
            performWork();
        } finally {
            permits.release();
        }
    }

    private void performWork() {
        // Công việc cần giới hạn số lần thực hiện đồng thời.
    }
}
~~~

Nếu **acquire()** ném **InterruptedException**, khối try chưa bắt đầu và không có lời gọi **release()**. Nếu đã lấy giấy phép, dù **performWork()** ném lỗi thì giấy phép vẫn được trả. Trả giấy phép khi chưa lấy có thể vô tình tăng giới hạn đồng thời vượt mức thiết kế.

Với các lời gọi như **tryAcquire()** có thể trả về **false**, phải kiểm tra kết quả và chỉ giải phóng khi việc chiếm giữ thành công.

### 4.3. Tránh return hoặc ném lỗi từ finally

~~~java
public int dangerousExample() {
    try {
        throw new IllegalStateException("Processing failed");
    } finally {
        return 0; // Che mất ngoại lệ gốc: cách viết nên tránh.
    }
}
~~~

Trả về trong finally có thể làm bên gọi không nhận được lỗi thực sự. Ngoài ra, nếu **finally** ném ngoại lệ mới, ngoại lệ đó có thể che lỗi đang truyền ra. Đây là lý do nên ưu tiên try-with-resources khi có thể, và xử lý rõ ràng lỗi phát sinh trong quá trình dọn dẹp.

## 5. Quyền sở hữu quyết định ai được đóng

Nguyên tắc thực dụng: **thành phần tạo hoặc mượn tài nguyên để sử dụng riêng thường chịu trách nhiệm kết thúc lần sử dụng đó, trừ khi hợp đồng quy định rõ việc chuyển quyền sở hữu**.

Tuy nhiên, “ai gọi phương thức tạo” chưa phải quy tắc tuyệt đối: một factory có thể trả đối tượng dùng chung, một thư viện có thể quản lý tài nguyên thay người gọi, hoặc một API có thể chuyển hẳn quyền sở hữu cho bên nhận. Luôn đọc hợp đồng thực tế.

### 5.1. Sở hữu, mượn và chuyển giao

| Quan hệ | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| **Sở hữu trong một phạm vi** | Hàm mở tệp để đọc | Hàm đóng reader/stream trước khi trả kết quả |
| **Mượn theo hợp đồng** | Lấy Connection từ DataSource pool | Đóng Connection để trả về pool; không tự đóng cả pool |
| **Chia sẻ ở cấp ứng dụng** | ExecutorService dùng cho nhiều request | Thành phần quản lý vòng đời ứng dụng chịu trách nhiệm shutdown |
| **Bên gọi sở hữu** | Hàm nhận InputStream từ tham số và chỉ đọc | Không tự đóng nếu API không chuyển quyền sở hữu |
| **Chuyển giao sở hữu** | Hàm tạo và trả về một InputStream mới | Tài liệu API phải nói rõ bên nhận cần đóng |

Ví dụ **không nên** đóng stream do bên gọi sở hữu nếu hợp đồng không cho phép:

~~~java
public long countBytes(InputStream borrowedInput) throws IOException {
    long count = 0;
    byte[] buffer = new byte[8192];
    int read;
    while ((read = borrowedInput.read(buffer)) != -1) {
        count += read;
    }
    return count; // Không đóng borrowedInput ở đây.
}
~~~

Ở đây, phương thức đọc từ một stream được truyền vào và giả định **bên gọi vẫn sở hữu** nó. Nếu phương thức tự ý đóng stream, bên gọi có thể không sử dụng lại được. Ngược lại, nếu phương thức **tự mở** stream, hãy đóng tài nguyên tại phạm vi đó hoặc ghi rõ rằng quyền sở hữu được chuyển cho bên nhận.

### 5.2. Vòng đời tài nguyên có thể dài hơn một lời gọi

Một **Connection** lấy từ pool thường chỉ thuộc một lần xử lý và được trả sớm sau khi xong. Trong khi đó, **DataSource** hoặc **ExecutorService** dùng chung có thể sống suốt vòng đời ứng dụng.

Đóng tài nguyên dùng chung ở cuối mỗi request có thể gây lỗi cho các request khác. Nhưng không bao giờ dừng resource dùng chung khi ứng dụng kết thúc cũng có thể giữ luồng và kết nối ngoài ý muốn. Tìm đúng **ranh giới sở hữu** là điều kiện để dọn dẹp đúng.

## 6. Tài nguyên gắn với giao dịch: JDBC

Tài nguyên JDBC thường gồm **Connection**, **PreparedStatement** và **ResultSet**. Mỗi tài nguyên có vòng đời riêng. Khi dùng connection pool, **Connection.close()** thường trả kết nối về pool theo hợp đồng của pool thay vì đóng socket vật lý ngay lập tức; vẫn phải gọi close khi xong lần mượn.

### 6.1. Đọc dữ liệu với ba tầng tài nguyên

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class UserRepository {
    private final DataSource dataSource;

    public UserRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public String findDisplayName(long userId) throws SQLException {
        String sql = "SELECT display_name FROM users WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, userId);

            try (ResultSet resultSet = statement.executeQuery()) {
                return resultSet.next()
                        ? resultSet.getString("display_name")
                        : null;
            }
        }
    }
}
~~~

Dù tìm thấy dữ liệu và **return** sớm, không tìm thấy hàng nào, hoặc **executeQuery()** ném lỗi, các tài nguyên đã mở đều được đóng theo phạm vi. Việc đóng **ResultSet**, **PreparedStatement** và **Connection** không nên phụ thuộc vào người gọi phải nhớ dọn dẹp các đối tượng nội bộ.

### 6.2. Đóng kết nối không thay thế quyết định commit/rollback

Nếu tắt **auto-commit** để thực hiện nhiều câu lệnh trong một giao dịch, phải quyết định **commit** khi thành công hoặc **rollback** khi thất bại. Không nên chỉ trông chờ vào **Connection.close()** để xử lý trạng thái giao dịch: hành vi khi đóng kết nối còn giao dịch chưa hoàn thành phụ thuộc hệ quản trị và cấu hình.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class BatchFlagUpdater {
    private final DataSource dataSource;

    public BatchFlagUpdater(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void markBoth(long firstId, long secondId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                String sql = "UPDATE tasks SET processed = TRUE WHERE id = ?";
                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {
                    statement.setLong(1, firstId);
                    if (statement.executeUpdate() != 1) {
                        throw new IllegalStateException("First row missing");
                    }

                    statement.setLong(1, secondId);
                    if (statement.executeUpdate() != 1) {
                        throw new IllegalStateException("Second row missing");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Ví dụ giả định **firstId** và **secondId** khác nhau, hai bản ghi tồn tại trong cùng cơ sở dữ liệu hỗ trợ giao dịch, và phạm vi gọi quản lý kết nối theo hợp đồng của DataSource. Nếu ghi bản ghi thứ hai thất bại, chương trình **thử rollback**, ghi nhận lỗi rollback nếu có, rồi try-with-resources **đóng/hoàn trả connection**. Đoạn mã minh họa không giải quyết mọi tình huống như mất kết nối trong lúc commit khiến kết quả cam kết chưa xác định; những trường hợp đó cần cơ chế đối soát ở cấp nghiệp vụ.

Việc dọn dẹp tài nguyên và việc giữ **tính nhất quán dữ liệu** là hai trách nhiệm liên quan nhưng khác nhau. Đóng kết nối không tự bảo đảm logic giao dịch đúng.

## 7. Tệp tạm, stream lười và các tài nguyên khó nhìn thấy

### 7.1. Tệp tạm không tự biến mất chỉ vì chương trình xong việc

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class TemporaryReport {
    public String renderReport() throws IOException {
        Path tempFile = Files.createTempFile("report-", ".txt");
        try {
            Files.writeString(tempFile, "Temporary report");
            return Files.readString(tempFile);
        } finally {
            Files.deleteIfExists(tempFile);
        }
    }
}
~~~

Trong ví dụ này, tệp sẽ được **thử xóa** dù có return hoặc IOException. Nếu việc xóa cũng thất bại, lỗi xóa có thể che lỗi xử lý trước đó vì mã dùng finally trực tiếp. Với dữ liệu quan trọng, cần chính sách ghi nhận cả hai lỗi (chẳng hạn gắn lỗi dọn dẹp dưới dạng suppressed), có cơ chế dọn dẹp lại và bảo đảm các tệp cũ không tồn tại vô thời hạn.

Khi tệp phải được giữ lại để người dùng tải về hoặc phục vụ tác vụ khác, không được xóa ngay trong phạm vi tạo tệp. Hãy chuyển giao quyền sở hữu hoặc quản lý theo thời hạn lưu giữ đã định.

### 7.2. Một số Stream có tài nguyên nền

Không phải mọi **Stream** của Java đều cần đóng. Stream từ danh sách trong bộ nhớ thường không giữ tài nguyên bên ngoài, nhưng Stream do **Files.lines()** mở có thể giữ kênh đọc tệp.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

public long countWarnings(Path logFile) throws IOException {
    try (Stream<String> lines =
                 Files.lines(logFile, StandardCharsets.UTF_8)) {
        return lines.filter(line -> line.contains("WARN")).count();
    }
}
~~~

Lời gọi terminal **count()** thực hiện xử lý Stream, nhưng không thay cho **close()** của Stream có tài nguyên nền. Cần đặt Stream trong try-with-resources khi API cung cấp hợp đồng yêu cầu đóng.

### 7.3. Ngữ cảnh ThreadLocal trong thread pool

Thread pool tái sử dụng thread giữa các yêu cầu. Nếu một yêu cầu gán **ThreadLocal** rồi quên xóa, dữ liệu có thể tồn tại khi cùng thread xử lý yêu cầu khác.

~~~java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

public void handle(String requestId) {
    REQUEST_ID.set(requestId);
    try {
        processRequest();
    } finally {
        REQUEST_ID.remove();
    }
}
~~~

Đây là ví dụ về vòng đời **ngữ cảnh gắn với thread**, không phải đóng một file descriptor. Nếu mã là thành phần tạm thời ghi đè ngữ cảnh do bên khác sở hữu, thay vì xóa vô điều kiện phải khôi phục giá trị trước đó theo hợp đồng. Cũng cần nhớ **ThreadLocal không tự lan truyền chính xác qua mọi cơ chế bất đồng bộ**.

## 8. Bất đồng bộ: đóng tài nguyên khi công việc thật sự kết thúc

Xét trường hợp mở InputStream ở thread nhận yêu cầu, gửi công việc sử dụng nó sang thread khác, rồi thoát khỏi try-with-resources. Khi thread xử lý bắt đầu đọc, stream có thể **đã bị đóng**.

**Nguyên tắc:** tài nguyên cần tồn tại cho tới khi **tác vụ cuối cùng dùng nó đã hoàn thành**. Ranh giới thực thi của tác vụ bất đồng bộ có thể khác ranh giới phương thức gọi.

### 8.1. Đặt việc mở và đóng bên trong tác vụ

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

public CompletableFuture<byte[]> loadSmallFile(
        Path path, Executor executor) {
    return CompletableFuture.supplyAsync(() -> {
        try (var input = Files.newInputStream(path)) {
            return input.readAllBytes();
        } catch (IOException error) {
            throw new UncheckedIOException(error);
        }
    }, executor);
}
~~~

Đoạn mã minh họa dùng cho **tệp nhỏ** có thể đọc toàn bộ vào bộ nhớ; tệp lớn cần thiết kế xử lý theo luồng. Bằng cách mở stream **bên trong tác vụ**, quyền sở hữu và việc đóng stream cùng nằm trên một đường thực thi. Nếu tác vụ không được gửi đi hoặc bị hủy trước khi bắt đầu, không có stream nào được mở để rồi bị bỏ quên.

Việc gọi **CompletableFuture.cancel()** không mặc nhiên bảo đảm tác vụ đang chạy bị ngắt và tài nguyên được đóng ngay. Cơ chế hủy, timeout và dừng executor phải được thiết kế cho dạng công việc thực tế.

### 8.2. Kết thúc executor do mình sở hữu

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public void runOwnedExecutor() throws InterruptedException {
    ExecutorService executor = Executors.newFixedThreadPool(2);
    try {
        submitTasks(executor);
    } finally {
        executor.shutdown();
        if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
            executor.shutdownNow();
        }
    }
}
~~~

Ví dụ giả định phương thức **sở hữu executor**, các tác vụ có chính sách dừng phù hợp và bên gọi chấp nhận ngoại lệ ngắt. **shutdown()** ngừng nhận việc mới nhưng không bảo đảm các tác vụ đang chạy đã hoàn tất; **awaitTermination()** đợi trong giới hạn; **shutdownNow()** chỉ yêu cầu dừng, không thể ép mọi tác vụ tự kết thúc.

Trong ứng dụng thực tế, nếu **awaitTermination()** bị ngắt, cần thực hiện chính sách hủy phù hợp và thường khôi phục trạng thái ngắt khi bắt và xử lý **InterruptedException**. Với executor dùng chung của toàn ứng dụng, phương thức xử lý một request **không được tự shutdown**.

## 9. Cách kiểm thử dọn dẹp trên các đường lỗi

Kiểm thử nghiệp vụ chỉ kiểm tra giá trị trả về có thể bỏ sót rò rỉ tài nguyên. Cần chủ động kiểm tra tài nguyên được đóng khi xử lý bình thường và khi có lỗi.

### 9.1. Đối tượng giả theo dõi lần đóng

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.Test;

final class TrackingResource implements AutoCloseable {
    boolean closed;

    String read() {
        throw new IllegalStateException("Read failed");
    }

    @Override
    public void close() {
        closed = true;
    }
}

class ResourceCleanupTest {
    @Test
    void closesResourceEvenWhenReadingFails() {
        TrackingResource resource = new TrackingResource();

        assertThrows(IllegalStateException.class, () -> {
            try (TrackingResource owned = resource) {
                owned.read();
            }
        });

        assertTrue(resource.closed);
    }
}
~~~

Ví dụ kiểm tra rằng lỗi đọc **không bỏ qua close()**. Có thể mở rộng đối tượng giả để đếm số lần đóng, chủ động ném ngoại lệ trong close và xác minh **suppressed exceptions**.

Tuy nhiên, kiểm thử với đối tượng giả chỉ chứng minh điều khiển luồng trong phạm vi kiểm thử. Rò rỉ kết nối thật, lỗi shutdown thread hoặc việc giải phóng khóa trong hệ thống đồng thời còn cần kiểm thử tích hợp, kiểm thử tải và các quan sát thực tế.

### 9.2. Ma trận đường đi và trách nhiệm dọn dẹp

| Điểm thất bại | Cần xác minh |
| --- | --- |
| Thao tác mở tài nguyên đầu tiên thất bại | Không gọi close lên một tài nguyên chưa cấp phát |
| Mở tài nguyên thứ hai thất bại | Tài nguyên thứ nhất đã mở được đóng |
| Xử lý ném ngoại lệ | Tài nguyên sở hữu được đóng; ngoại lệ gốc không bị che |
| Đóng tài nguyên ném ngoại lệ | Lỗi được truyền hoặc ghi nhận theo hợp đồng |
| Có return trong lúc xử lý | Đường return vẫn thực hiện dọn dẹp |
| Lấy khóa hoặc giấy phép bị ngắt | Không unlock/release nếu chưa lấy được |
| Giao dịch SQL thất bại | Thử rollback và đóng statement/connection |
| Tác vụ bất đồng bộ chưa hoàn tất | Tài nguyên không bị đóng trước khi tác vụ dùng xong |
| Có timeout hoặc hủy | Có chính sách dừng và thu hồi tài nguyên |

### 9.3. Những tín hiệu vận hành có thể theo dõi

- Số kết nối đang dùng, thời gian chờ connection pool và số lần yêu cầu chờ quá hạn.
- Số file descriptor, socket và tệp tạm tăng liên tục theo thời gian.
- Số thread hoạt động sau khi hủy hoặc kết thúc một nhóm công việc.
- Số giấy phép semaphore hoặc khóa được giữ bất thường.
- Các lỗi **close**, **rollback**, **shutdown** và **suppressed exceptions** trong log và trace.

Một phép đo không đủ để kết luận có rò rỉ. Hãy quan sát xu hướng qua nhiều chu kỳ tải, đối chiếu số tác vụ còn hoạt động và xem lại quyền sở hữu tài nguyên ở những đường xử lý liên quan.

## 10. Những hiểu nhầm dễ dẫn tới lỗi

**“GC sẽ đóng tài nguyên giúp tôi.”** GC không bảo đảm thời điểm đóng tài nguyên bên ngoài. Hãy đóng hoặc trả tài nguyên theo hợp đồng ngay khi hết sử dụng.

**“Chỉ cần gọi close ở dòng cuối phương thức.”** Return sớm và ngoại lệ có thể bỏ qua dòng đó. Dùng try-with-resources hoặc finally đúng chỗ.

**“Đóng càng sớm càng tốt.”** Đóng trước khi tác vụ bất đồng bộ sử dụng xong có thể khiến công việc thất bại. Thời điểm đóng phải dựa trên lần sử dụng cuối và quyền sở hữu.

**“Tôi không tạo DataSource nên không cần đóng Connection.”** Khi mượn kết nối từ pool, thường phải đóng **Connection** để hoàn trả lượt mượn, dù không sở hữu toàn bộ pool.

**“finally luôn chạy trong mọi tình huống.”** Mất điện, tiến trình bị dừng đột ngột hoặc JVM kết thúc bất thường có thể ngăn Java thực hiện khối dọn dẹp. Những tài nguyên bền vững cần cơ chế thu hồi hoặc phục hồi phù hợp.

**“close() không thể thất bại.”** Close hoặc flush có thể ném lỗi; phải quyết định cách báo lỗi và bảo toàn lỗi gốc.

**“Rollback là đủ, không cần close.”** Rollback xử lý thay đổi giao dịch; close xử lý quyền sử dụng tài nguyên. Cần quan tâm cả hai.

## 11. Quy trình review vòng đời tài nguyên

1. **Liệt kê tài nguyên:** Tệp, stream, connection, statement, lock, permit, executor, tệp tạm và ngữ cảnh có vòng đời.
2. **Chỉ ra chủ sở hữu:** Ai tạo/mượn, ai được dùng và ai chịu trách nhiệm đóng hoặc trả?
3. **Xác định phạm vi sống:** Tài nguyên cần tồn tại tới thời điểm nào, nhất là khi có xử lý bất đồng bộ?
4. **Liệt kê mọi điểm thoát:** Thành công, return sớm, ngoại lệ khi khởi tạo, lỗi xử lý, ngắt/hủy và lỗi khi dọn dẹp.
5. **Chọn cơ chế giải phóng:** Try-with-resources với AutoCloseable; finally với lock/permit; cơ chế lifecycle riêng cho executor và tài nguyên sống lâu.
6. **Bảo toàn thông tin lỗi:** Không che ngoại lệ gốc, ghi nhận lỗi close/rollback và suppressed exceptions.
7. **Kiểm tra tác động nghiệp vụ:** Đóng kết nối không thay thế commit/rollback; xóa tệp tạm không được làm mất dữ liệu người khác đang sử dụng.
8. **Kiểm chứng:** Bổ sung kiểm thử đường lỗi, kiểm thử tích hợp và theo dõi chỉ số tài nguyên khi vận hành.

Mục đích là biến trách nhiệm dọn dẹp thành **cấu trúc rõ ràng ngay trong mã**, để một thay đổi về luồng xử lý không vô tình thêm đường rò rỉ mới.

## 12. Tình huống luyện tập

Một dịch vụ tạo báo cáo làm các bước sau:

~~~text
1. Mượn Connection từ pool
2. Tạo tệp PDF tạm
3. Truy vấn dữ liệu và ghi nội dung tệp
4. Gửi tác vụ upload tệp sang executor dùng chung
5. Đóng Connection và xóa tệp tạm
6. Trả HTTP 202
~~~

Một số lần, tác vụ upload báo **file not found**. Trong vài tuần sau, hệ thống đồng thời bắt đầu báo hết kết nối DB khi truy vấn bị lỗi.

Hãy trả lời:

1. Vì sao tác vụ upload đôi khi không tìm thấy tệp dù phương thức tạo báo cáo đã chạy thành công?
2. Vòng đời tệp tạm nên thuộc về bước nào để phù hợp với xử lý bất đồng bộ?
3. Cần đặt try-with-resources ở đâu để Connection được trả về pool trên cả đường truy vấn lỗi?
4. Nếu việc đóng tệp thất bại đồng thời thao tác ghi tệp cũng lỗi, phải giữ thông tin lỗi như thế nào?
5. Đâu là khác biệt giữa dừng một executor do thành phần tạo riêng và một executor được dùng chung cho cả ứng dụng?

**Gợi ý đối chiếu:** Tệp tạm đã bị xóa trước khi công việc upload hoàn tất. Nên chuyển giao quyền sở hữu tệp cho tác vụ upload, chỉ dọn dẹp sau khi upload hoàn thành hoặc được xác định thất bại, và có chính sách thu hồi tệp còn sót. Kết nối DB cần nằm trong try-with-resources ở phạm vi truy vấn, được đóng cả khi đọc/ghi phát sinh ngoại lệ. Lỗi xử lý chính nên được bảo toàn cùng với lỗi đóng tài nguyên, chẳng hạn thông qua suppressed exceptions. Executor dùng chung chỉ nên được dừng bởi thành phần quản lý vòng đời của nó.

## 13. Ghi nhớ

- **Mỗi tài nguyên cần chủ sở hữu và ranh giới vòng đời rõ ràng**: mở hoặc mượn, sử dụng, đóng hoặc trả.
- **Mọi đường đi** gồm thành công, return sớm, ngoại lệ, lỗi khởi tạo một phần, hủy và lỗi trong quá trình dọn dẹp.
- Ưu tiên **try-with-resources** với AutoCloseable; dùng **finally** với khóa, giấy phép và tài nguyên có cơ chế release riêng.
- **Đóng đúng thời điểm** quan trọng ngang với việc có đóng: tránh rò rỉ, đóng quá sớm và đóng tài nguyên thuộc sở hữu của thành phần khác.
- **Rollback, close, shutdown và xóa tệp tạm** giải quyết những trách nhiệm khác nhau; cần thiết kế theo hợp đồng và kiểm thử cả đường lỗi.
