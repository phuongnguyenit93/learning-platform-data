# Tệp log, xoay vòng log và việc mở lại đích ghi

Ứng dụng Java thường ghi log ra tệp để lưu lại hoạt động, lỗi và thông tin vận hành. Trong thời gian ứng dụng chạy, một logger hoặc appender có thể giữ file descriptor và tiếp tục ghi qua cùng một đối tượng tệp. Khi CRaC tạo checkpoint, tiến trình tạm ngừng hoạt động; trong khoảng thời gian đó, hệ thống vận hành vẫn có thể xoay vòng log, đổi tên tệp, tạo tệp mới, thay symlink hoặc mount lại volume.

Vì vậy, sau khi restore, một file descriptor được giữ trong heap hoặc được khôi phục ở cấp tiến trình chưa chắc còn trỏ tới tệp log hiện hành. Trên hệ thống Unix, khi một tệp đang mở bị đổi tên, file descriptor cũ vẫn tham chiếu tới inode cũ. Những lần ghi tiếp theo có thể tiếp tục đi vào tệp đã được đổi tên, trong khi đường dẫn cấu hình của ứng dụng đã trỏ tới tệp mới. Nếu ứng dụng cần ghi vào đích hiện hành, nó phải đóng handle cũ và mở lại đường dẫn sau restore.

Trong CRaC, việc này thường được tổ chức bằng resource callback: flush và đóng đích ghi trước checkpoint, rồi mở lại đích ghi sau restore. Cách làm cụ thể phụ thuộc vào logger đang dùng, hệ điều hành, loại filesystem và cách môi trường triển khai quản lý log.

## 1. Vì sao file log cần được quản lý qua checkpoint?

Khi ứng dụng mở một tệp để ghi, hệ điều hành cấp một file descriptor (trên Windows thường được biểu diễn qua handle). Java có thể giữ đối tượng như FileOutputStream, FileWriter, BufferedWriter, FileChannel hoặc appender của logging framework. Đối tượng Java này thường giữ tham chiếu tới tài nguyên hệ điều hành tương ứng.

Đường dẫn và file descriptor là hai khái niệm khác nhau:

- Đường dẫn như /var/log/orders/app.log là tên được filesystem phân giải khi ứng dụng mở tệp.
- File descriptor là tham chiếu tới tệp đã được mở. Nó không tự động chuyển sang một tệp khác chỉ vì một tiến trình đổi tên hoặc tạo lại đường dẫn ban đầu.
- Inode trên filesystem Unix đại diện cho đối tượng tệp. Nhiều đường dẫn có thể lần lượt tham chiếu tới các inode khác nhau theo thời gian.
- Bộ đệm trong Java hoặc logging framework có thể giữ dữ liệu chưa được ghi xuống filesystem. Chỉ đóng hoặc flush đúng cách mới giúp đẩy phần dữ liệu đó theo hợp đồng của API.

Ví dụ, ứng dụng mở /var/log/orders/app.log. Sau đó logrotate đổi tên tệp này thành app.log.1 và tạo một app.log mới. File descriptor cũ vẫn trỏ tới đối tượng tệp đã đổi tên. Nếu ứng dụng tiếp tục ghi bằng descriptor cũ, nội dung mới có thể xuất hiện trong app.log.1 thay vì app.log.

Điều này có thể xảy ra nếu thao tác xoay vòng log diễn ra khi ứng dụng đang checkpoint và ứng dụng restore lại với handle cũ. JVM có thể tiếp tục chạy, logger có thể vẫn hoạt động và thao tác ghi có thể không báo lỗi, nhưng log đã đi vào tệp không còn là đích ghi hiện hành.

Do đó, việc khôi phục tiến trình không đồng nghĩa với việc logging framework tự mở lại đường dẫn. Ứng dụng cần có chính sách vòng đời rõ ràng cho các đích ghi dựa trên tệp.

## 2. Điều gì xảy ra khi log được xoay vòng?

Xoay vòng log (log rotation) giới hạn kích thước hoặc thời gian tồn tại của tệp log. Khi tới ngưỡng, hệ thống đổi tên tệp hiện tại, nén hoặc lưu trữ nó, rồi tạo một tệp mới để nhận log tiếp theo.

Có hai cách xoay vòng phổ biến khi ứng dụng đang ghi.

### 2.1. Rename và create

Trong cách này, công cụ xoay vòng đổi tên tệp đang ghi, sau đó tạo một tệp mới tại đường dẫn ban đầu.

Ví dụ:

~~~text
Trước khi rotate:
  /var/log/orders/app.log       -> inode A (ứng dụng đang mở)

Sau khi rotate:
  /var/log/orders/app.log.1     -> inode A
  /var/log/orders/app.log       -> inode B (tệp mới)
~~~

File descriptor của ứng dụng vẫn tham chiếu inode A. Đổi tên đường dẫn không tự thay đổi đối tượng mà descriptor đang trỏ tới. Muốn ghi vào inode B, ứng dụng phải đóng descriptor cũ rồi mở lại /var/log/orders/app.log.

Đây là lý do nhiều logging framework hỗ trợ thao tác reopen hoặc nhận tín hiệu để đóng và mở lại tệp. Với CRaC, có thể phối hợp bằng cách đóng tệp trong callback trước checkpoint và mở lại đường dẫn hiện hành trong callback sau restore. Nếu rotation diễn ra trong thời gian JVM đang dừng, lần mở lại sau restore sẽ phân giải đường dẫn tới tệp mới.

### 2.2. Copy và truncate

Một số cấu hình logrotate sao chép nội dung tệp hiện tại sang tệp lưu trữ rồi truncate tệp gốc mà không đổi inode. Đây thường được gọi là copytruncate.

~~~text
Trước khi rotate:
  /var/log/orders/app.log       -> inode A (ứng dụng đang mở)

Sau khi copytruncate:
  /var/log/orders/app.log.1     -> bản sao nội dung tại thời điểm copy
  /var/log/orders/app.log       -> inode A đã bị truncate
~~~

Vì inode không thay đổi, file descriptor đang mở vẫn có thể ghi vào tệp app.log sau khi truncate. Tuy nhiên, copytruncate có một cửa sổ đua: log được ghi trong khoảng giữa thao tác copy và truncate có thể bị mất hoặc xuất hiện không đúng như mong đợi trong bản lưu trữ. Việc truncate cũng không làm cho bộ đệm ở mọi tầng tự động được đồng bộ.

Nếu ứng dụng chủ động đóng tệp trước checkpoint và mở lại sau restore, nó vẫn có thể làm việc với đường dẫn hiện hành. Nhưng copytruncate không giải quyết được các vấn đề về dữ liệu log bị mất trong cửa sổ copy/truncate khi ứng dụng vẫn ghi. Khi cần độ tin cậy cao, nên chọn chiến lược rotation có phối hợp reopen rõ ràng hoặc dùng cơ chế rolling do logging framework quản lý.

### 2.3. Rotation khi ứng dụng đang dừng

Một lợi ích của việc đóng đích ghi trước checkpoint là công cụ rotation có thể đổi tên, nén và tạo tệp mới trong khi JVM đang dừng mà không còn descriptor của ứng dụng giữ tệp cũ mở. Sau restore, callback mở lại đường dẫn active sẽ trỏ tới tệp hiện tại.

Trình tự minh họa:

~~~text
Ứng dụng đang chạy
    |
    v
beforeCheckpoint(): flush và đóng app.log
    |
    v
CRaC tạo checkpoint; JVM dừng
    |
    v
Log rotation: lưu app.log cũ, tạo app.log mới
    |
    v
CRaC restore
    |
    v
afterRestore(): mở lại đường dẫn app.log
    |
    v
Ứng dụng ghi vào tệp log hiện hành
~~~

Nếu hệ thống không xoay vòng log trong lúc ứng dụng dừng, callback sau restore vẫn có thể mở lại cùng đường dẫn. Việc mở mới giúp ứng dụng bắt đầu với một handle mới và xác minh được đích ghi ở thời điểm phục hồi.

## 3. Vai trò của callback CRaC

Một resource quản lý tệp log có thể triển khai interface org.crac.Resource và đăng ký với global context. Hai callback có trách nhiệm khác nhau:

- beforeCheckpoint(): dừng hoặc drain luồng ghi, flush dữ liệu còn trong bộ đệm, đóng writer hoặc appender đang giữ file descriptor.
- afterRestore(): đọc lại cấu hình đường dẫn nếu cần, tạo thư mục nếu cần, mở lại tệp theo đường dẫn hiện hành và chỉ cho phép ghi log khi đích ghi đã sẵn sàng.

Ví dụ đăng ký:

~~~java
Core.getGlobalContext().register(logFileResource);
~~~

Việc đăng ký chỉ giúp runtime gọi callback. Nó không tự động phát hiện logrotate, không tự đóng mọi FileOutputStream trong ứng dụng và không tự chọn đường dẫn mới. Resource cần quản lý đúng đối tượng đang sở hữu writer hoặc appender.

Đối với ứng dụng có nhiều tệp log, cần xác định rõ logger nào sở hữu từng appender, appender nào dùng chung và thành phần nào có quyền đóng hoặc mở lại chúng. Tránh để hai resource cùng đóng một writer hoặc một resource đóng appender mà logging framework vẫn tiếp tục gửi sự kiện vào đó.

## 4. Ví dụ: quản lý một file log bằng Resource

Ví dụ dưới đây minh họa một writer đơn giản ghi vào một đường dẫn cố định. Resource đóng writer trước checkpoint và mở lại cùng đường dẫn sau restore. Đường dẫn được chuyển thành absolute path ngay khi khởi tạo để tránh phụ thuộc vào working directory có thể thay đổi khi môi trường chạy ứng dụng được dựng lại.

~~~java
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class LogFileResource implements Resource {
    private final Path logPath;
    private BufferedWriter writer;

    public LogFileResource(Path configuredPath) throws IOException {
        this.logPath = configuredPath.toAbsolutePath().normalize();
        openWriter();
        Core.getGlobalContext().register(this);
    }

    public synchronized void writeLine(String message)
            throws IOException {
        if (writer == null) {
            throw new IllegalStateException(
                    "Log writer is not available");
        }

        writer.write(message);
        writer.newLine();
    }

    public synchronized void flush() throws IOException {
        if (writer != null) {
            writer.flush();
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws IOException {
        closeWriter();
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws IOException {
        openWriter();
    }

    private void openWriter() throws IOException {
        Path parent = logPath.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        writer = Files.newBufferedWriter(
                logPath,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
                StandardOpenOption.APPEND
        );
    }

    private void closeWriter() throws IOException {
        BufferedWriter current = writer;
        writer = null;

        if (current != null) {
            current.flush();
            current.close();
        }
    }
}
~~~

Khởi tạo resource trong giai đoạn bootstrap:

~~~java
Path logPath = Path.of("/var/log/orders/app.log");
LogFileResource logResource = new LogFileResource(logPath);
~~~

Khi checkpoint:

1. Ứng dụng ngừng nhận các thao tác cần ghi log mới hoặc chờ các thao tác hiện tại hoàn tất.
2. beforeCheckpoint() lấy writer hiện tại, đặt trường writer về null, flush và đóng writer.
3. Sau khi checkpoint, tiến trình không còn giữ writer đang mở cho tệp log này.

Khi restore:

1. afterRestore() gọi openWriter().
2. Files.newBufferedWriter() phân giải đường dẫn hiện hành và mở tệp với chế độ APPEND.
3. Nếu rotation đã đổi tên tệp cũ và tạo tệp mới, writer mới ghi vào tệp mới tại đường dẫn active.

Đây là ví dụ minh họa cơ chế, không phải một logging framework đầy đủ. Phương thức writeLine() và callback được đồng bộ để tránh đóng writer trong lúc một lần ghi thông qua chính đối tượng này đang thực hiện. Tuy nhiên, ứng dụng vẫn phải dừng hoặc drain các thread gửi log trước checkpoint. Nếu một thread gọi writeLine() sau khi writer đã đóng, phương thức sẽ báo lỗi để ứng dụng xử lý rõ ràng.

Trong môi trường production, không nên dùng một writer tự xây dựng thay cho logging framework nếu ứng dụng cần level, structured logging, async queue, MDC, rolling policy hoặc nhiều appender. Hãy áp dụng cùng nguyên tắc vòng đời lên appender thực tế thông qua API được framework hỗ trợ.

## 5. Tích hợp với logging framework

Các framework như java.util.logging, Logback và Log4j2 quản lý handler hoặc appender thay cho ứng dụng. Đích ghi tệp có thể được giữ bên trong đối tượng framework, nên việc chỉ đóng một FileOutputStream khác không ảnh hưởng đến appender đang ghi log.

Khi tích hợp CRaC, hãy xác định:

- Đối tượng nào đang sở hữu file appender hoặc handler?
- Có bộ đệm hoặc hàng đợi bất đồng bộ nào cần drain không?
- Framework có API chính thức để flush, stop, close, reopen hoặc reconfigure appender không?
- Sau khi mở lại, appender có sử dụng đúng đường dẫn active và giữ nguyên formatter, filter, encoder, level cùng cấu hình rollover không?
- Framework hoặc phiên bản đang dùng có hỗ trợ CRaC sẵn hay có integration module phù hợp không?

Không nên tùy tiện đóng file descriptor nằm bên dưới framework trong khi appender vẫn còn hoạt động. Framework có thể tiếp tục giữ tham chiếu tới writer đã đóng, làm log bị lỗi hoặc bị loại bỏ. Cũng không nên khởi tạo thêm appender mới sau mỗi restore mà quên gỡ appender cũ, vì điều đó có thể khiến mỗi sự kiện được ghi nhiều lần.

Một resource tích hợp với framework thường thực hiện các công việc theo khái niệm sau:

~~~java
public void beforeCheckpoint(Context<? extends Resource> context) {
    stopAcceptingLogEvents();
    drainAsyncLoggingQueue();
    flushAndCloseFileAppenders();
}

public void afterRestore(Context<? extends Resource> context) {
    reopenOrReconfigureFileAppenders();
    verifyActiveLogTargets();
    resumeLogEvents();
}
~~~

Đây là pseudocode mô tả trình tự, không phải API có sẵn của một framework cụ thể. Tên phương thức và cách quản lý lifecycle cần theo tài liệu của phiên bản framework mà ứng dụng sử dụng. Nếu framework có CRaC integration chính thức, nên ưu tiên integration đó thay vì tự điều khiển nội bộ appender.

### 5.1. Log bất đồng bộ

Một số logger ghi log qua hàng đợi và worker thread. Khi ứng dụng chuẩn bị checkpoint, việc đóng appender ngay có thể làm mất các sự kiện vẫn còn trong queue hoặc khiến worker thread truy cập writer đã đóng.

Trình tự cần có:

1. Ngừng nhận sự kiện log mới từ các luồng nghiệp vụ theo cách phù hợp với ứng dụng.
2. Yêu cầu logging framework drain hàng đợi bất đồng bộ.
3. Chờ worker hoàn tất ghi trong giới hạn thời gian.
4. Flush và đóng appender.
5. Sau restore, mở lại appender, khởi động lại worker hoặc logging context theo hướng dẫn của framework.

Nếu không thể drain queue trong thời hạn, cần xác định chính sách rõ ràng: chờ thêm, báo lỗi checkpoint hay chấp nhận bỏ một số log theo yêu cầu vận hành. Không nên âm thầm bỏ qua lỗi vì log có thể là dữ liệu cần thiết để điều tra sự cố.

### 5.2. Nhiều appender và nhiều đích ghi

Một logger có thể gửi sự kiện tới console, file, socket hoặc dịch vụ tập trung cùng lúc. Resource chỉ cần đóng những đích ghi mà ứng dụng sở hữu và cần tái tạo. Ví dụ, file appender có thể cần đóng và mở lại, trong khi console appender vẫn được quản lý bởi runtime container.

Nếu nhiều logger dùng chung một appender, chỉ một thành phần nên sở hữu lifecycle của appender đó. Đăng ký resource cho từng logger rồi cùng đóng một appender có thể tạo ra callback trùng lặp và lỗi thứ tự.

## 6. Đường dẫn log và nơi lưu trữ

Việc mở lại tệp chỉ có ý nghĩa nếu đường dẫn sau restore trỏ tới đúng filesystem và đúng đích mong muốn.

### 6.1. Đường dẫn tuyệt đối và working directory

Đường dẫn tương đối được phân giải dựa trên working directory của tiến trình. Nếu môi trường restore sử dụng working directory khác, cùng một chuỗi đường dẫn có thể trỏ tới nơi khác. Với đích ghi quan trọng, nên lưu đường dẫn tuyệt đối hoặc xây dựng đường dẫn từ cấu hình rõ ràng.

Không nên chỉ lưu một đối tượng Path rồi giả định filesystem phía sau vẫn như cũ. Sau restore, volume có thể được mount lại hoặc cấu hình đường dẫn có thể thay đổi. Nếu đích ghi có thể đổi theo môi trường, hãy đọc lại cấu hình từ nguồn phù hợp trong callback sau restore.

### 6.2. Persistent volume và container

Trong container, filesystem của lớp ghi tạm có thể bị thay thế khi container được tạo lại. Persistent volume có thể giữ dữ liệu qua lần tạo lại container, nhưng mount point, quyền truy cập và trạng thái volume vẫn cần được xác minh.

Trước khi mở lại log sau restore, ứng dụng cần bảo đảm:

- Thư mục đích đã tồn tại hoặc có thể được tạo.
- Volume đã mount đúng vị trí.
- Tài khoản chạy JVM có quyền ghi.
- Đích ghi còn đủ dung lượng và không ở trạng thái chỉ đọc.
- Đường dẫn không vô tình trỏ vào filesystem tạm khi cần lưu log lâu dài.

Nếu volume chưa sẵn sàng, callback phục hồi nên báo lỗi hoặc để ứng dụng ở trạng thái chưa sẵn sàng. Không nên tự động chuyển sang một thư mục khác mà không có chính sách rõ ràng, vì log có thể bị phân tán hoặc mất khỏi nơi vận hành đang theo dõi.

### 6.3. Symlink làm đích ghi

Một số hệ thống sử dụng symlink như current.log để trỏ tới tệp đang hoạt động. Khi rotation thay đổi symlink, descriptor đã mở vẫn trỏ tới đối tượng tệp mà nó đã mở trước đó. Mở lại đường dẫn symlink sau restore sẽ phân giải liên kết tại thời điểm mở và có thể đi tới tệp mới.

Hãy kiểm tra quyền truy cập, mục tiêu symlink và chính sách rotation. Không lưu một file descriptor cũ rồi mong nó tự theo symlink mới.

## 7. Ghi log ra stdout và stderr trong container

Không phải ứng dụng Java nào cũng nên quản lý tệp log trực tiếp. Trong Kubernetes và nhiều nền tảng container, ứng dụng thường ghi log ra stdout hoặc stderr. Runtime container hoặc agent thu thập log sẽ nhận các luồng này rồi chuyển tiếp, lưu trữ và xoay vòng theo cấu hình nền tảng.

Với mô hình đó:

- Ứng dụng không tự đóng System.out hoặc System.err trong beforeCheckpoint().
- Ứng dụng nên flush các luồng nếu phù hợp với cách logging framework quản lý console appender.
- Không tự mở một file app.log khác chỉ để thay thế luồng stdout do container runtime cấp.
- Rotation và retention thường do nền tảng hoặc log collector quản lý.
- Sau restore, cần kiểm tra cách runtime và môi trường triển khai cung cấp lại standard streams; không giả định một pipe hoặc sink bên ngoài có cùng vòng đời với một file thường.

Nếu framework ghi console qua appender, hãy kiểm tra cách framework flush và xử lý callback. Việc quản lý stdout/stderr khác với việc đóng và mở lại một tệp theo đường dẫn. Không đóng standard stream chỉ để mô phỏng lifecycle của file appender.

## 8. Các lỗi thường gặp khi khôi phục đích ghi

| Tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Log tiếp tục xuất hiện trong app.log.1 | Descriptor cũ vẫn tham chiếu inode đã đổi tên | Đóng descriptor trước checkpoint và mở lại đường dẫn active sau restore |
| Log không xuất hiện sau restore | Writer đã đóng nhưng appender chưa được tạo lại | Khôi phục appender theo API của logging framework |
| Mỗi dòng log xuất hiện hai lần | Resource tạo appender mới nhưng appender cũ vẫn được đăng ký | Quản lý duy nhất một chủ sở hữu và loại bỏ appender cũ đúng cách |
| Mất các log cuối trước checkpoint | Bộ đệm hoặc async queue chưa được drain | Drain queue, flush và chờ thao tác ghi hoàn tất |
| Callback sau restore báo lỗi quyền truy cập | Volume, owner hoặc permission thay đổi | Kiểm tra mount và quyền ghi trước khi mở tệp |
| Log ghi vào thư mục không mong muốn | Đường dẫn tương đối được phân giải từ working directory khác | Dùng đường dẫn tuyệt đối hoặc đọc lại cấu hình |
| Tệp log mới không được tạo | Thư mục chưa tồn tại hoặc filesystem read-only | Tạo thư mục có kiểm soát và kiểm tra trạng thái filesystem |
| Log bị thiếu quanh thời điểm copytruncate | Rotation có cửa sổ đua giữa copy và truncate | Dùng chiến lược rotation có reopen rõ ràng hoặc rolling appender phù hợp |
| Async logger mất sự kiện | Queue chưa drain khi appender bị đóng | Dừng nhận log mới, drain queue rồi mới đóng appender |

## 9. Quy trình vận hành đề xuất

Một quy trình có thể áp dụng cho file appender như sau.

### Trước checkpoint

1. Chuyển ứng dụng sang trạng thái quiescing để ngừng nhận công việc mới nếu việc đó cần thiết cho tính nhất quán của log.
2. Drain các request hoặc tác vụ đang ghi log theo chính sách của ứng dụng.
3. Drain queue của async logger và chờ worker hoàn tất trong thời hạn đã định.
4. Flush các appender và writer đang ghi vào tệp.
5. Đóng các đích ghi tệp và giải phóng handle.
6. Xác nhận resource đã ở trạng thái sẵn sàng cho checkpoint.

### Trong thời gian JVM dừng

Hệ thống vận hành có thể xoay vòng log, đổi tên tệp, tạo tệp mới, nén tệp cũ hoặc thay đổi mount. Quy trình rotation phải biết rằng ứng dụng đã đóng tệp và không còn ghi vào đích cũ. Nếu một công cụ rotation khác vẫn quản lý cùng tệp, cần bảo đảm không có hai cơ chế rotation cạnh tranh.

### Sau restore

1. Đọc lại cấu hình đích ghi nếu đường dẫn hoặc mount có thể thay đổi.
2. Xác minh thư mục, volume, quyền ghi và dung lượng.
3. Mở lại đường dẫn active thay vì tái sử dụng descriptor cũ.
4. Khôi phục appender, formatter, filter và rolling policy của logging framework.
5. Khởi động lại worker của async logger và cho phép nhận sự kiện mới.
6. Kiểm tra rằng log mới xuất hiện tại đích ghi dự kiến trước khi mở readiness nếu logging là phụ thuộc bắt buộc của vận hành.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Ứng dụng ghi log] --> B[Ngừng hoặc drain luồng ghi]
    B --> C[Drain async queue và flush]
    C --> D[Đóng file appender hoặc writer]
    D --> E[CRaC checkpoint]
    E --> F[Log rotation khi JVM dừng]
    F --> G[CRaC restore]
    G --> H[Xác minh mount, path và permission]
    H --> I[Mở lại đích ghi hiện hành]
    I --> J[Khởi động logger và worker]
    J --> K[Tiếp tục ghi log]
~~~

Không phải mọi ứng dụng đều cần dừng toàn bộ xử lý nghiệp vụ chỉ để đóng file log. Nếu logging framework hỗ trợ một quy trình đóng/mở appender an toàn khi còn lưu lượng, có thể dùng cơ chế đó. Tuy nhiên, cần bảo đảm không có thread ghi vào appender đã đóng và có chính sách rõ ràng cho sự kiện log phát sinh trong khoảng thời gian appender tạm ngừng.

## 10. Kiểm thử log rotation với CRaC

Kiểm thử nên mô phỏng việc tệp thay đổi trong lúc JVM đang dừng, thay vì chỉ xác nhận rằng callback đã được gọi.

Một kịch bản cơ bản:

1. Khởi chạy ứng dụng và ghi một số dòng log có thể nhận diện.
2. Tạo checkpoint để callback đóng file appender.
3. Trong khi JVM dừng, đổi tên tệp hiện tại thành app.log.1 và tạo app.log mới.
4. Restore ứng dụng.
5. Ghi thêm một dòng log có nội dung nhận diện khác.
6. Kiểm tra dòng mới nằm trong app.log, còn các dòng trước rotation nằm trong tệp lưu trữ theo chính sách.

Các trường hợp khác nên thử:

- Rotation không xảy ra trong thời gian checkpoint.
- Rotation xảy ra nhiều lần trong lúc JVM dừng.
- Thư mục log bị thay symlink.
- Persistent volume được mount lại.
- Quyền ghi bị thay đổi hoặc filesystem chuyển sang read-only.
- Appender dùng buffer hoặc async queue còn sự kiện khi checkpoint bắt đầu.
- Callback mở lại tệp thất bại vì thư mục chưa sẵn sàng.
- Ứng dụng có nhiều appender, trong đó chỉ một số appender ghi ra tệp.
- Nhiều replica restore từ cùng checkpoint và ghi vào các tệp log riêng.

Kiểm tra cả nội dung và đích ghi. Một ứng dụng có thể không báo lỗi nhưng vẫn ghi vào tệp đã đổi tên. Hãy kiểm tra inode hoặc đường dẫn thực tế trên nền tảng hỗ trợ, thời điểm sửa đổi của tệp, số dòng và vị trí của các dòng đánh dấu trước/sau restore.

## 11. Chọn chiến lược ghi log phù hợp

| Mô hình | Cách quản lý rotation | Công việc CRaC cần quan tâm |
|---|---|---|
| Ứng dụng ghi trực tiếp ra file | Ứng dụng hoặc công cụ ngoài đổi tên và tạo file | Đóng writer trước checkpoint, mở lại active path sau restore |
| Logging framework có rolling appender | Framework tự quản lý theo kích thước hoặc thời gian | Dùng lifecycle API hoặc CRaC integration được framework hỗ trợ |
| File appender kết hợp logrotate | Công cụ hệ điều hành xoay vòng file | Phối hợp close/reopen; tránh tiếp tục ghi vào descriptor cũ |
| Console logging trong container | Runtime hoặc log collector quản lý lưu trữ và rotation | Flush theo cơ chế framework; không đóng stdout/stderr |
| Log gửi tới dịch vụ tập trung | Client gửi qua socket hoặc HTTP | Đóng hoặc tạm dừng client phù hợp, tạo lại kết nối và xác thực sau restore |

Với hệ thống cần vận hành đơn giản trong container, ghi log có cấu trúc ra stdout/stderr thường giúp tách trách nhiệm lưu trữ khỏi ứng dụng. Với ứng dụng cần ghi file trực tiếp, cần thiết kế resource quản lý appender và phối hợp với công cụ rotation.

## 12. Những nguyên tắc cần nhớ

- File descriptor tham chiếu tới tệp đã mở; đổi tên đường dẫn không tự chuyển descriptor sang tệp mới.
- Log rotation có thể xảy ra trong lúc JVM đang checkpoint và dừng.
- Trước checkpoint, cần drain luồng ghi, flush bộ đệm và đóng appender hoặc writer có sở hữu file.
- Sau restore, mở lại đường dẫn active để phân giải đích ghi hiện hành.
- Với async logger, phải xử lý queue và worker trước khi đóng appender.
- Với logging framework, dùng API lifecycle được hỗ trợ và tránh tạo appender trùng lặp.
- Với stdout/stderr trong container, để runtime và log collector quản lý vòng đời stream và rotation.
- Xác minh filesystem, volume, permission và đường dẫn trước khi cho ứng dụng tiếp tục ghi.

CRaC giữ lại trạng thái tiến trình để giảm thời gian khởi động, nhưng không làm cho đường dẫn log và file descriptor tự đồng bộ với các thay đổi bên ngoài. Quản lý đúng vòng đời tệp log đòi hỏi ứng dụng chuẩn bị đích ghi trước checkpoint, mở lại đường dẫn hiện hành sau restore và kiểm thử với chính sách rotation thực tế của môi trường triển khai.
