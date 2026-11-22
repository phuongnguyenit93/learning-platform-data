# File lock và file đang được sử dụng

Trong Spring Batch, job thường đọc file đầu vào, ghi file kết quả hoặc di chuyển file qua các thư mục `incoming`, `processing`, `archive` và `error`. Khi nhiều job, nhiều worker hoặc một tiến trình bên ngoài cùng truy cập một file, có thể xảy ra xung đột: file đang được ghi nhưng batch đã đọc, hai job cùng xử lý một file, writer không mở được output vì chương trình khác đang giữ file, hoặc một job restart ghi vào resource đã bị thay thế.

**File lock** là cơ chế phối hợp để xác định tiến trình nào được quyền sử dụng một resource trong một khoảng thời gian. Tuy nhiên, file lock chỉ có tác dụng khi các bên cùng tuân thủ giao thức khóa; hành vi còn phụ thuộc hệ điều hành và filesystem. Spring Batch không tự động khóa mọi file mà reader hoặc writer sử dụng. Ứng dụng cần thiết kế cách claim file, giữ lock, giải phóng lock và phục hồi khi tiến trình chết.

Một quy trình batch an toàn thường có ba phần: producer công bố file chỉ sau khi ghi xong; consumer claim file để chỉ một execution xử lý; writer tạo output riêng rồi publish khi kết quả đã hoàn tất. Nếu job chạy trên nhiều node, cần dùng cơ chế đồng bộ có tính phân tán phù hợp thay vì chỉ dựa vào `synchronized` trong JVM.

## Những tình huống file contention thường gặp

Các lỗi liên quan tới file đang được sử dụng thường xuất hiện ở những thời điểm sau:

- Producer đang ghi file CSV nhưng job đã bắt đầu đọc.
- Hai `JobExecution` khác nhau cùng đọc và xử lý một file đầu vào.
- Hai step hoặc hai job cùng ghi vào một output path.
- Một tiến trình đang mở file nên Windows từ chối thao tác xóa, đổi tên hoặc ghi đè.
- Job restart cần mở lại file nhưng file đã bị di chuyển, xóa hoặc thay thế.
- Một node giữ lock trong khi node khác không biết owner đã chết hay chưa.
- File được đặt trên NFS, SMB hoặc object storage với semantics khác filesystem local.

Ví dụ, hai job được khởi chạy với `JobParameters` khác nhau nên tạo ra hai `JobInstance` hợp lệ, nhưng cả hai lại nhận cùng `inputFile`. Batch metadata không tự ngăn chúng đọc cùng một resource. Nếu cả hai cùng ghi output vào `orders-result.csv`, dữ liệu có thể bị trộn, ghi đè hoặc một job thất bại với lỗi file đang được sử dụng.

## File lock là gì?

File lock là một cơ chế đồng bộ hóa gắn với file hoặc một vùng byte của file. Một tiến trình yêu cầu lock trước khi thực hiện thao tác cần độc quyền; tiến trình khác tuân thủ cùng giao thức sẽ không được cấp lock xung đột cho tới khi lock được giải phóng.

Trong Java NIO, `FileChannel.lock()` yêu cầu lock và có thể chờ tới khi lấy được; `tryLock()` thử lấy lock ngay và trả về `null` nếu vùng cần khóa đang bị tiến trình khác giữ. `FileLock` có thể là shared hoặc exclusive:

- **Exclusive lock:** một bên giữ quyền khóa vùng file; thường dùng cho thao tác ghi hoặc claim xử lý độc quyền.
- **Shared lock:** nhiều bên có thể giữ lock đọc tương thích nếu hệ điều hành/filesystem hỗ trợ và không có exclusive lock xung đột.

Không nên mặc định shared lock được hỗ trợ giống nhau trên mọi nền tảng. Một số filesystem hoặc hệ điều hành có thể chỉ hỗ trợ exclusive lock hoặc chuyển đổi shared lock theo cách khác.

### File lock có thể là advisory

Trên nhiều hệ thống, file lock mang tính *advisory*: nó chỉ ngăn các tiến trình khác lấy lock tương ứng nếu những tiến trình đó cũng yêu cầu lock theo cùng cơ chế. Một chương trình khác vẫn có thể mở và ghi file mà không kiểm tra lock. Vì vậy, file lock không phải một bức tường bảo vệ tuyệt đối trước mọi ứng dụng.

Trên một số nền tảng, lock có semantics gần mandatory hơn hoặc ảnh hưởng trực tiếp tới cách mở file, nhưng không nên dựa vào hành vi đó để xây dựng ứng dụng đa nền tảng. Cần kiểm tra hệ điều hành, filesystem, mount option và Java runtime của môi trường triển khai.

### Lock không đồng nghĩa file handle đang mở

Một file có thể đang được mở mà không có lock. Ngược lại, một lock có thể được giữ trên channel trong khi ứng dụng khác vẫn đọc được file nếu không tuân thủ lock hoặc nền tảng cho phép. Vì vậy, lỗi “file is being used by another process” và trạng thái “file đang có lock” có liên quan nhưng không phải lúc nào cũng là một khái niệm.

## Java NIO FileLock

`FileChannel` cung cấp API lock cấp hệ điều hành. Ví dụ sau yêu cầu exclusive lock trên một file lock riêng:

```java
Path lockPath = Path.of("/batch/locks/orders.lock");

try (FileChannel channel = FileChannel.open(
        lockPath,
        StandardOpenOption.CREATE,
        StandardOpenOption.WRITE)) {

    FileLock lock = channel.tryLock();
    if (lock == null) {
        throw new FileBusyException("Another process owns the lock");
    }

    try (lock) {
        processOrdersFile();
    }
}
```

Đoạn code minh họa việc mở channel, thử lấy lock và giữ lock trong phạm vi xử lý. `FileBusyException` và `processOrdersFile()` là thành phần do ứng dụng định nghĩa. Trong code production, cần xử lý thêm lỗi I/O, lock overlap trong cùng JVM và chính sách chờ.

Một cách viết phổ biến khác là khóa toàn bộ vùng file:

```java
FileLock lock = channel.tryLock(0L, Long.MAX_VALUE, false);
```

Tham số cuối `false` yêu cầu exclusive lock. Không phải filesystem nào cũng hỗ trợ mọi kiểu vùng lock giống nhau; chọn phạm vi và loại lock phù hợp với giao thức ứng dụng.

### tryLock và các kết quả có thể gặp

| Kết quả | Ý nghĩa | Xử lý gợi ý |
| --- | --- | --- |
| Trả về `FileLock` | Đã lấy được lock | Thực hiện công việc trong phạm vi lock |
| Trả về `null` | Lock xung đột đang được giữ | Chờ có giới hạn, báo file bận hoặc đưa vào hàng đợi |
| `OverlappingFileLockException` | JVM hiện tại đã có lock chồng lấn trên vùng đó | Kiểm tra việc nhiều thread trong cùng JVM cùng claim file |
| `IOException` | Lỗi mở channel/lock hoặc lỗi filesystem | Phân loại lỗi I/O, quyền truy cập và filesystem |

`FileLock` được gắn với `FileChannel`. Đóng channel sẽ giải phóng lock; có thể gọi `release()` tường minh. Dùng try-with-resources giúp tránh giữ lock khi code ném exception.

### Lock trong cùng JVM

Java quản lý các file lock trong phạm vi JVM. Hai thread trong cùng JVM yêu cầu lock chồng lấn có thể gặp `OverlappingFileLockException` thay vì chờ nhau như hai process độc lập. Nếu ứng dụng cần phối hợp nhiều thread cùng JVM, có thể kết hợp `ConcurrentHashMap`, `ReentrantLock` hoặc một cơ chế đồng bộ nội bộ với file lock.

`synchronized` hoặc `ReentrantLock` chỉ phối hợp thread trong cùng JVM. Chúng không ngăn một process khác hoặc một node khác truy cập file. Khi có nhiều instance ứng dụng, cần một cơ chế liên tiến trình hoặc phân tán.

## Lock file và file dữ liệu

Một mẫu thường dùng là tạo file lock riêng bên cạnh file dữ liệu:

```text
incoming/
  orders-2026-11-15.csv
  orders-2026-11-15.csv.lock
```

Các consumer thống nhất rằng muốn xử lý `orders-2026-11-15.csv` thì phải lấy exclusive lock trên file `.lock`. Lock riêng giúp tránh thay đổi nội dung file dữ liệu chỉ để phối hợp truy cập.

Có hai cách dễ bị nhầm:

1. **Giữ OS lock trên lock file:** file lock tồn tại ổn định; tiến trình giữ `FileLock` trong channel. Khi process chết hoặc channel đóng, OS/JVM giải phóng lock.
2. **Dùng sự tồn tại của file marker làm khóa:** ứng dụng tạo `orders.lock` và coi việc file tồn tại là có owner. Nếu process chết, marker có thể còn lại dù không ai giữ lock.

Hai cách này có semantics khác nhau. Một file marker tồn tại không chứng minh OS lock đang được giữ.

### Không xóa lock file đang dùng một cách tùy tiện

Với mẫu OS lock, nên giữ một lock file ổn định và chỉ release lock; không xóa file lock sau mỗi lần xử lý. Nếu process A đang giữ lock trên file, process B đã mở cùng file và đang chờ, rồi A xóa file và process C tạo lại file cùng tên, B và C có thể đang thao tác trên hai file object khác nhau. Trên filesystem hỗ trợ inode, điều này có thể làm hai bên cùng nghĩ mình có lock hợp lệ.

Giữ lock file tồn tại ổn định giúp các process luôn khóa cùng một resource. Quyền truy cập thư mục lock cần được quản lý để tránh tiến trình tùy tiện thay thế hoặc xóa file.

### Tạo marker bằng CREATE_NEW

Nếu dùng marker file làm cơ chế claim, thao tác tạo phải nguyên tử đối với việc file đã tồn tại. Trong Java có thể dùng `Files.createFile(path)` hoặc `CREATE_NEW` để chỉ một process tạo thành công khi path chưa có.

```java
try {
    Files.createFile(claimPath);
    // Process này đã tạo marker và được xem là owner theo giao thức.
} catch (FileAlreadyExistsException busy) {
    // Một consumer khác đã claim resource.
}
```

Marker file vẫn có thể còn lại sau crash. Cần có owner metadata, lease/TTL hoặc quy trình reconciliation để thu hồi claim cũ an toàn. Không chỉ kiểm tra marker tồn tại rồi xóa nếu không xác định owner còn hoạt động hay không.

## Claim file bằng atomic move

Một cách phối hợp phổ biến cho pipeline file là chuyển file từ thư mục `incoming` sang `processing`. Nhiều consumer có thể cùng thử claim, nhưng chỉ một consumer thành công nếu filesystem cung cấp rename/move nguyên tử cho thao tác đó.

```text
incoming/orders.csv
       |
       | atomic move / claim
       v
processing/orders.csv
       |
       | batch xử lý
       +------------------+
       |                  |
       v                  v
archive/orders.csv   error/orders.csv
```

Ví dụ:

```java
Path source = incoming.resolve(fileName);
Path claimed = processing.resolve(fileName);

try {
    Files.move(source, claimed, StandardCopyOption.ATOMIC_MOVE);
} catch (FileAlreadyExistsException alreadyClaimed) {
    // Consumer khác đã claim file này.
}
```

`ATOMIC_MOVE` chỉ được hỗ trợ khi filesystem/provider đáp ứng điều kiện. Move trong cùng filesystem thường là lựa chọn phù hợp hơn; move qua filesystem khác có thể không nguyên tử hoặc không được hỗ trợ. Nếu không thể dùng atomic move, cần một giao thức khác thay vì giả định thao tác copy rồi delete là một claim nguyên tử.

Atomic move cũng không tự giải quyết mọi tình huống crash. Ví dụ process có thể claim file rồi chết trước khi ghi metadata batch. Cần có quy trình khôi phục file nằm trong `processing`, đối chiếu JobRepository và owner metadata để quyết định restart hay đưa về hàng đợi.

## Producer phải công bố file sau khi ghi xong

Một lỗi phổ biến là consumer bắt đầu đọc file trong khi producer vẫn đang ghi. Kiểm tra file tồn tại hoặc kích thước không đổi trong một khoảng thời gian ngắn không phải bằng chứng tuyệt đối rằng producer đã hoàn tất.

Một giao thức an toàn hơn:

1. Producer ghi vào tên tạm, ví dụ `orders.csv.part`.
2. Producer flush và đóng file.
3. Producer đổi tên thành `orders.csv` trong cùng filesystem bằng atomic move nếu có thể.
4. Consumer chỉ đọc file có tên hoàn chỉnh hoặc manifest/ready marker đã công bố.

```java
Path temporary = incoming.resolve("orders.csv.part");
Path ready = incoming.resolve("orders.csv");

writeAndClose(temporary);
Files.move(temporary, ready, StandardCopyOption.ATOMIC_MOVE);
```

`writeAndClose` là logic producer. Sau khi rename, consumer có thể xem file là đã sẵn sàng theo giao thức. Nếu filesystem không hỗ trợ atomic move, dùng manifest/ready marker được tạo sau khi đóng file hoặc một hàng đợi/metadata store có cơ chế publish rõ ràng.

Với file lớn hoặc nhiều file thuộc cùng một lô, có thể tạo manifest chứa tên file, kích thước, checksum và batch ID; publish manifest sau khi mọi file đã sẵn sàng. Consumer chỉ bắt đầu khi manifest hoàn chỉnh và checksum phù hợp.

## Tránh hai JobExecution cùng xử lý một input

Spring Batch phân biệt `JobInstance` bằng job name và identifying parameters. Cơ chế này ngăn khởi chạy trùng cùng một logical instance theo quy tắc repository, nhưng không tự ngăn hai instance khác nhau dùng chung file input.

Ví dụ:

```text
JobInstance A: importJob, businessDate=2026-11-15
JobInstance B: importJob, businessDate=2026-11-16

Cả hai cùng nhận inputFile=/data/incoming/orders.csv
```

Hai instance khác nhau có thể cùng tồn tại và cùng đọc một file. Nếu file phải được xử lý đúng một lần, cần một lớp claim/lock theo file key hoặc batch ID. Key claim nên ổn định, ví dụ normalized path + source version/checksum hoặc producer batch ID.

Không nên dùng tên file đơn thuần nếu producer có thể tái sử dụng tên đó cho nội dung khác. Cùng path nhưng version khác nhau là hai input logical khác nhau; checksum hoặc immutable object version giúp phân biệt.

## Lock trong Spring Batch lifecycle

Có thể quản lý lock ở phạm vi job hoặc step tùy resource được chia sẻ.

### Lock ở cấp job

Nếu toàn bộ job sở hữu một file trong suốt vòng đời, có thể lấy lock trong `JobExecutionListener.beforeJob` và giải phóng trong `afterJob`. Cách này dễ hiểu nhưng cần nhớ callback `afterJob` không được bảo đảm chạy khi JVM bị kill hoặc máy chủ mất điện. OS lock thường được giải phóng khi process/channel kết thúc; marker/lease cần recovery riêng.

### Lock ở cấp step

Nếu chỉ một step sử dụng file, có thể acquire lock trước khi mở reader/writer và release sau khi step hoàn tất. Một component triển khai `ItemStream` hoặc một tasklet/step listener có thể quản lý lifecycle, nhưng cần bảo đảm lock được giữ xuyên suốt phần đọc/ghi cần bảo vệ.

Không nên release lock trong `afterWrite` hoặc callback giữa chunk nếu step còn tiếp tục truy cập file. Lock phải bao phủ toàn bộ khoảng thời gian resource cần được bảo vệ.

### Lock trong wrapper service

Có thể tách logic lock thành `FileLockService` để các step dùng chung giao thức:

```java
public interface FileLockService {
    FileLockHandle acquire(Path resource, Duration timeout);
}
```

`FileLockHandle` là abstraction do ứng dụng định nghĩa, cung cấp `close()` để release. Dùng try-with-resources ở nơi thực thi để lock được giải phóng ngay cả khi reader, processor hoặc writer ném exception.

## Ví dụ FileLockService có timeout

Một service đơn giản có thể thử lock trong khoảng thời gian hữu hạn. Ví dụ sau là skeleton; production cần bổ sung logging, phân loại lỗi filesystem và chính sách backoff phù hợp.

```java
public final class FileLockService {

    public FileLockHandle acquire(Path lockPath, Duration timeout)
            throws IOException, InterruptedException {

        Files.createDirectories(lockPath.getParent());
        FileChannel channel = FileChannel.open(
                lockPath,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE);

        long deadline = System.nanoTime() + timeout.toNanos();
        try {
            while (System.nanoTime() < deadline) {
                try {
                    FileLock lock = channel.tryLock();
                    if (lock != null) {
                        return new FileLockHandle(channel, lock);
                    }
                } catch (OverlappingFileLockException busyInThisJvm) {
                    // Thread khác trong JVM đang giữ vùng lock chồng lấn.
                }

                Thread.sleep(100);
            }

            throw new FileLockTimeoutException(lockPath.toString());
        } catch (IOException | InterruptedException | RuntimeException ex) {
            channel.close();
            throw ex;
        }
    }
}
```

`FileLockHandle` có thể triển khai `AutoCloseable` và đóng lock/channel:

```java
public final class FileLockHandle implements AutoCloseable {

    private final FileChannel channel;
    private final FileLock lock;

    public FileLockHandle(FileChannel channel, FileLock lock) {
        this.channel = channel;
        this.lock = lock;
    }

    @Override
    public void close() throws IOException {
        try {
            if (lock.isValid()) {
                lock.release();
            }
        } finally {
            channel.close();
        }
    }
}
```

Đoạn code minh họa một cách chờ có timeout. Trong triển khai thực tế, cần dùng deadline an toàn, bảo đảm không làm mất interrupt, xử lý lỗi khi đóng channel và tránh polling quá dày. `Thread.sleep` chỉ là ví dụ; có thể dùng backoff tăng dần và jitter để nhiều consumer không cùng retry một nhịp.

Không giữ lock trong lúc chờ vô hạn. Nếu timeout hết, ứng dụng có thể đánh dấu file chưa sẵn sàng và thử lại ở lần poll tiếp theo, hoặc đưa ra cảnh báo để operator xử lý.

## File đang được sử dụng trên Windows và Linux

Hành vi xóa, đổi tên hoặc ghi đè file đang mở có thể khác giữa hệ điều hành.

| Thao tác | Windows (thường gặp) | Linux/Unix (thường gặp) |
| --- | --- | --- |
| Mở file để đọc trong khi process khác đọc | Thường được phép nếu sharing mode tương thích | Thường được phép |
| Mở file để ghi trong khi process khác giữ handle | Có thể bị từ chối tùy sharing flags/lock | Có thể mở được nhưng vẫn có race/ghi đè nếu không phối hợp |
| Xóa file đang mở | Thường bị từ chối nếu handle không cho phép delete sharing | Có thể unlink tên file trong khi process đang giữ file descriptor |
| Rename file đang mở | Có thể bị từ chối tùy handle/share mode | Thường có thể đổi tên; process đang mở vẫn truy cập inode cũ |
| File lock | Phụ thuộc FileChannel và filesystem | Thường advisory; phụ thuộc filesystem/mount |

Đây là hành vi phổ biến, không phải hợp đồng tuyệt đối cho mọi filesystem hoặc API. Antivirus, indexing service, backup agent, editor, preview pane hoặc process khác cũng có thể giữ handle trên Windows và làm thao tác rename/delete thất bại.

Nếu cần xử lý đa nền tảng, tránh dựa vào việc có thể xóa/rename file đang mở. Thiết kế producer đóng file trước khi publish; consumer chỉ mở resource đã sẵn sàng; output được ghi vào path riêng rồi publish sau khi đóng.

## Lỗi file đang được sử dụng và cách phân loại

Một số exception Java có thể xuất hiện:

- `AccessDeniedException`: không đủ quyền hoặc thao tác bị hệ điều hành từ chối.
- `FileSystemException`: lỗi filesystem tổng quát; message có thể mô tả file đang được sử dụng.
- `FileAlreadyExistsException`: path đích đã tồn tại khi tạo marker hoặc move.
- `NoSuchFileException`: file hoặc thư mục không còn tồn tại.
- `OverlappingFileLockException`: lock vùng chồng lấn trong cùng JVM.
- `IOException`: lỗi mở, đọc, ghi, lock hoặc đóng resource.

Không nên phân loại mọi `IOException` thành lỗi file bận. Quyền truy cập sai, path không tồn tại, disk full, filesystem read-only và file lock conflict cần cách xử lý khác nhau.

Một chính sách xử lý có thể gồm:

1. Nếu lock đang được owner khác giữ, chờ có giới hạn hoặc đưa file về hàng đợi.
2. Nếu lỗi là transient do antivirus hoặc process ngắn hạn giữ handle, retry có backoff hữu hạn.
3. Nếu quyền hoặc path sai, fail sớm và báo cấu hình.
4. Nếu disk full hoặc filesystem read-only, không retry liên tục; báo lỗi vận hành.
5. Nếu file bị mất sau claim, đối chiếu metadata/manifest và báo lỗi nguồn.

Chỉ retry lỗi có khả năng tự phục hồi. Không dùng skip policy để bỏ qua lỗi file bận nếu việc bỏ file làm mất dữ liệu nghiệp vụ.

## Retry khi file bận

Nếu một thao tác rename hoặc mở file thất bại vì lock tạm thời, có thể retry với giới hạn. Retry cần có timeout tổng, khoảng nghỉ tăng dần và thông tin chẩn đoán.

```java
int maxAttempts = 5;
long delayMillis = 200;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        openAndProcessFile(path);
        break;
    } catch (AccessDeniedException | FileSystemException ex) {
        if (attempt == maxAttempts) {
            throw ex;
        }
        Thread.sleep(delayMillis);
        delayMillis = Math.min(delayMillis * 2, 2_000);
    }
}
```

Đây chỉ là minh họa ý tưởng. Trong Java, `AccessDeniedException` là subclass của `FileSystemException`, nên không thể đặt cả hai trong cùng multi-catch; code thực tế cần catch `FileSystemException` một lần rồi phân loại subtype/message phù hợp. Không nên phân loại bằng message string nếu có thể dùng exception type hoặc OS error code rõ ràng.

Trong Spring Batch, có thể đưa retry vào fault-tolerant step nếu exception phát sinh từ reader/writer và loại exception được xác định phù hợp. Tuy nhiên, nếu lỗi xảy ra trước khi step có thể mở resource, có thể cần retry ở tasklet/service orchestration hoặc để scheduler thử lại job theo chính sách. Không nên retry vô hạn một file bị giữ lâu.

## Lock file và stale lock

Nếu dùng marker file, process có thể chết sau khi tạo marker mà chưa xóa nó. Marker còn lại được gọi là stale lock theo giao thức marker. Không nên xóa chỉ vì file đã cũ; owner có thể đang chạy lâu hoặc node bị mất kết nối tạm thời.

Metadata marker nên có:

- Logical resource key hoặc file identity.
- Owner ID duy nhất cho execution.
- Host/node name và process ID để hỗ trợ chẩn đoán.
- Thời điểm acquire và thời điểm lease hết hạn.
- Fencing token hoặc generation nếu cần ngăn owner cũ tiếp tục ghi.
- Job name, `JobExecution` ID và correlation ID nếu có.

PID và host name chỉ là thông tin chẩn đoán, không đủ để chứng minh owner còn sống. PID có thể được tái sử dụng và node có thể không truy cập được. Muốn thu hồi stale lock an toàn, cần lease có thời hạn, heartbeat và một quy tắc fencing.

## Lease và fencing token cho nhiều node

Khi nhiều node cùng xử lý một file trên shared storage, OS file lock không phải lúc nào cũng là lựa chọn đáng tin cậy. Có thể dùng database lock/lease table hoặc distributed coordination service.

Một bảng claim có thể lưu:

```text
batch_file_claim
----------------
file_key          PRIMARY KEY
owner_id
lease_until
fencing_token
updated_at
```

Quy trình khái quát:

1. Consumer thử insert hoặc cập nhật claim theo điều kiện lease đã hết hạn.
2. Database đảm bảo chỉ một transaction giành quyền tại một thời điểm thông qua unique constraint/conditional update.
3. Owner nhận `fencing_token` tăng đơn điệu.
4. Owner gia hạn lease định kỳ khi vẫn làm việc.
5. Khi hoàn tất, owner release claim bằng điều kiện đúng `owner_id` và token.
6. Nếu lease hết hạn, consumer khác có thể claim với token mới.

Lease giải quyết tình huống owner chết mà không release. Tuy nhiên, chỉ có TTL vẫn chưa đủ: owner cũ có thể bị pause lâu, lease hết hạn và owner mới nhận file; sau đó owner cũ tỉnh lại và tiếp tục ghi. Fencing token giúp resource đích từ chối thao tác của owner cũ nếu token của nó thấp hơn token mới nhất.

Không giữ một database transaction mở suốt thời gian job chỉ để giữ `SELECT ... FOR UPDATE`; transaction dài có thể giữ connection và lock lâu, gây contention. Lease row được commit riêng, có thời hạn và heartbeat thường phù hợp hơn cho công việc kéo dài.

## File lock trên NFS, SMB và shared storage

Khi file nằm trên NFS hoặc SMB, semantics lock và cache có thể khác local disk. Hành vi còn phụ thuộc phiên bản giao thức, mount option, server configuration và client implementation. Một lock hoạt động tốt trên máy developer không chứng minh nó phối hợp đúng giữa các container hoặc node production.

Trước khi chọn file lock trên shared storage, cần kiểm tra:

- Filesystem có hỗ trợ lock giữa các client hay chỉ trong một node?
- Lock có được duy trì qua network partition hoặc server restart không?
- Rename/create có atomic trong phạm vi thư mục đang dùng không?
- Client có cache directory entry hoặc file attribute làm chậm nhận biết thay đổi không?
- Khi node chết, lock được giải phóng như thế nào?
- Có thể quan sát owner và thu hồi lock an toàn không?

Nếu không có semantics đáng tin cậy, dùng database lease, distributed lock service hoặc một queue/metadata store có atomic claim. Không dựa vào một file marker trên shared mount mà không kiểm thử tình huống nhiều node và network failure.

## Object storage không có file lock kiểu filesystem

Object storage như S3-compatible storage thường không cung cấp `FileChannel` hoặc lock byte-range theo semantics filesystem local. Thay vào đó, ứng dụng dùng object key/version, conditional create/update, metadata/manifest và cơ chế claim bên ngoài.

Một quy trình có thể:

- Producer upload object với key/version immutable.
- Producer publish manifest hoặc trạng thái `READY` sau khi upload hoàn tất.
- Consumer claim batch ID trong database bằng conditional update.
- Job lưu object key và version ID trong `JobParameters` hoặc `ExecutionContext`.
- Writer xuất object tạm, sau đó cập nhật manifest/pointer khi publish thành công.

Không nên giả định rename object là thao tác atomic như rename file local; trên nhiều object store, rename được mô phỏng bằng copy rồi delete. Hãy dùng API conditional write/versioning và một metadata store phù hợp.

## Phối hợp file lock với FlatFileItemReader

`FlatFileItemReader` đọc file theo cơ chế stream và có thể lưu vị trí đọc để restart. Nó không tự động thiết lập một lock hệ điều hành để ngăn producer hoặc job khác ghi cùng file.

Nếu input có thể bị thay đổi trong khi đọc, nên bảo đảm file đã được producer đóng và publish trước khi reader mở. Có thể claim file bằng atomic move hoặc lock service rồi cấu hình reader đọc path trong thư mục `processing`.

Ví dụ reader nhận resource qua step scope:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['claimedFile']}") String claimedFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(claimedFile))
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

`claimedFile` cần ổn định qua restart. Nếu lần chạy đầu đã move file sang `processing`, restart phải dùng lại path đó hoặc một resource identity được lưu bền vững. Không claim lại file bằng cách tạo identifying parameter mới nếu muốn restart cùng `JobInstance`.

## Phối hợp file lock với FlatFileItemWriter

`FlatFileItemWriter` hỗ trợ state và restart, nhưng điều đó không có nghĩa nhiều job có thể cùng ghi một file an toàn. Mỗi logical execution nên có output resource riêng hoặc có giao thức khóa độc quyền rõ ràng.

Ví dụ output path có thể gắn với business date và execution identity ổn định:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .lineAggregator(order ->
                    order.orderId() + "," + order.amount())
            .saveState(true)
            .build();
}
```

Giữ `outputFile` và writer name ổn định cho cùng logical execution để restart khôi phục state. Hai execution khác nhau không nên dùng cùng output path trừ khi writer được thiết kế để phối hợp đồng thời.

### Ghi file tạm rồi publish

Nếu consumer chỉ được phép nhìn thấy file hoàn chỉnh, writer có thể ghi vào `orders.csv.part`. Sau khi step/job hoàn tất và file được đóng, một step finalize đổi tên sang `orders.csv` hoặc publish manifest. Nếu job thất bại, file `.part` được giữ để restart hoặc đưa vào quarantine theo quy trình.

Rename cần cùng filesystem nếu muốn có khả năng atomic. Nếu phải copy sang filesystem khác, consumer cần chờ marker/manifest xác nhận hoàn tất và kiểm tra checksum.

## Lock lifecycle với Spring Batch

Một cách triển khai là tạo `ItemStream`/service giữ handle lock và release khi step đóng:

```java
public class LockedFileResource implements ItemStream {

    private final FileLockService lockService;
    private final Path lockPath;
    private FileLockHandle handle;

    public LockedFileResource(FileLockService lockService, Path lockPath) {
        this.lockService = lockService;
        this.lockPath = lockPath;
    }

    @Override
    public void open(ExecutionContext context) {
        handle = lockService.acquire(lockPath, Duration.ofSeconds(30));
    }

    @Override
    public void update(ExecutionContext context) {
        // Lock ownership không cần checkpoint như reader position.
    }

    @Override
    public void close() throws ItemStreamException {
        if (handle != null) {
            try {
                handle.close();
            } catch (IOException ex) {
                throw new ItemStreamException("Cannot release file lock", ex);
            }
        }
    }
}
```

Đây là skeleton minh họa lifecycle. Cần bảo đảm stream được đăng ký với step và được mở trước khi reader/writer truy cập file. Trong ứng dụng thực tế, lock handle có thể được quản lý bởi một wrapper resource hoặc listener phù hợp. Nếu `open` thất bại, step phải không tiếp tục đọc/ghi resource.

Không lưu đối tượng `FileLock`, `FileChannel` hoặc handle đang mở vào `ExecutionContext`; đây là resource runtime không serialize/restart được. Chỉ lưu định danh file/claim và lấy lock mới ở lần execution/restart tương ứng.

## Khi nào release lock?

Lock cần được giữ đúng trong khoảng thời gian resource cần độc quyền:

- Input file: từ trước khi reader mở file cho tới khi step không còn đọc file.
- Output file: từ trước khi writer mở file cho tới khi writer đóng và output được finalize.
- Claim file: từ khi consumer nhận quyền xử lý tới khi file được chuyển archive/error hoặc trạng thái xử lý được commit.

Release quá sớm có thể cho phép job khác mở file trong khi step hiện tại vẫn đang dùng. Giữ lock quá lâu làm giảm throughput và có thể chặn consumer khác không cần thiết.

Với OS lock, đóng channel thường giải phóng lock ngay cả khi code không gọi `release()` do exception. Với marker/lease, cần release có điều kiện theo owner ID/token; không xóa claim của một owner khác.

## Job restart và file lock

Khi job dừng hoặc thất bại, lock runtime cần được giải phóng. Khi restart, job phải lấy lock lại trước khi mở file. Không thể serialize lock handle trong context rồi mong nó vẫn có hiệu lực sau khi process mới khởi động.

Một flow restart điển hình:

```text
Lần chạy đầu
  claim input
  acquire lock
  đọc/ghi một số chunk
  chunk lỗi -> rollback
  release lock khi step kết thúc
  JobExecution FAILED

Restart
  dùng cùng identifying JobParameters
  xác nhận input resource còn tồn tại
  acquire lock mới
  khôi phục reader/writer checkpoint
  tiếp tục xử lý
  hoàn tất -> archive input / publish output
  release lock
```

Nếu file đã được move khỏi `processing` hoặc archive trước khi metadata job commit, restart có thể không tìm thấy resource. Thứ tự cập nhật file và batch metadata cần được thiết kế để phục hồi khi crash giữa hai thao tác. Có thể dùng trạng thái claim/manifest trong database để đối chiếu với `JobExecution` và chỉ archive sau khi job hoàn tất.

## Idempotency và duplicate processing

File lock giảm khả năng hai consumer cùng xử lý một file đồng thời, nhưng không tự bảo đảm file chỉ được xử lý đúng một lần trong mọi tình huống crash.

Ví dụ job ghi business data thành công nhưng process chết trước khi cập nhật manifest file sang `PROCESSED`. Lần poll tiếp theo có thể claim lại file. Nếu writer không idempotent, dữ liệu sẽ bị ghi trùng.

Các cơ chế bổ sung:

- Batch ID hoặc file identity duy nhất trong database.
- Unique constraint cho business key hoặc processing ledger.
- Output path gắn với logical execution và version nguồn.
- Manifest ghi trạng thái `CLAIMED`, `PROCESSING`, `COMPLETED` hoặc `FAILED`.
- Transactional outbox cho event phát sinh sau khi ghi business data.
- Đối soát input/output count và checksum.

Lock giúp phối hợp truy cập đồng thời; idempotency giúp xử lý an toàn khi một công việc bị replay. Hai cơ chế bổ trợ nhau.

## Monitoring và vận hành

Để điều tra file contention, log nên có đủ thông tin nhưng tránh ghi payload nhạy cảm:

- File key/path đã chuẩn hóa.
- Source version, checksum hoặc batch ID.
- Job name và `JobExecution` ID.
- Step name và `StepExecution` ID.
- Owner ID, host/node và fencing token nếu có.
- Thời điểm acquire, thời gian giữ lock và thời điểm release.
- Số lần retry và thời gian chờ lock.
- Kết quả claim, archive, quarantine hoặc publish.
- Exception type và nguyên nhân I/O đã được phân loại.

Các metric hữu ích:

- Số file đang chờ, đang claim và đang xử lý.
- Số lock acquisition thành công/thất bại.
- Thời gian chờ lock trung bình và percentile cao.
- Số lease hết hạn/stale claim được thu hồi.
- Số file xử lý lại và số duplicate được phát hiện.
- Số lỗi rename/delete/open và dung lượng disk còn lại.

Không log token/secret hoặc toàn bộ nội dung file. Nếu path chứa thông tin khách hàng, có thể log file ID hoặc hash thay cho full path theo chính sách bảo mật.

## Kiểm thử file lock

Kiểm thử lock nên bao phủ cả thread trong cùng JVM và process độc lập nếu production chạy nhiều process/node.

### Hai thread tranh cùng lock

Mở cùng lock path từ hai thread. Thread thứ nhất lấy lock và giữ tới khi test release; thread thứ hai phải không được cấp lock xung đột. Dùng `CountDownLatch` để kiểm soát thời điểm, không dùng `Thread.sleep` để phỏng đoán thứ tự.

### Hai process tranh cùng lock

Khởi chạy hai JVM test process cùng yêu cầu lock trên một filesystem được hỗ trợ. Xác nhận chỉ một process lấy được exclusive lock tại một thời điểm. Test này quan trọng vì `synchronized` không kiểm tra được phối hợp liên process.

### Process chết khi đang giữ OS lock

Cho process test lấy lock rồi kết thúc bất thường. Xác nhận OS giải phóng lock khi channel/process đóng theo semantics của môi trường. Nếu dùng marker file, xác nhận marker còn lại và quy trình lease/reconciliation xử lý nó; không nhầm marker tồn tại với OS lock đang hoạt động.

### Producer ghi file chưa xong

Mô phỏng producer giữ file `.part` mở, consumer chỉ nhìn file `ready`. Xác nhận consumer không đọc file trước khi producer đóng và publish marker/rename.

### Hai consumer claim cùng file

Cho hai worker cùng thử atomic move từ `incoming` sang `processing`. Xác nhận chỉ một consumer claim thành công trên filesystem hỗ trợ atomic move. Kiểm thử riêng trên loại storage production sẽ sử dụng.

### File bận và retry timeout

Giữ lock từ test thread, cho consumer thử acquire với timeout hữu hạn. Xác nhận consumer kết thúc đúng thời gian, ghi nhận file bận và không tạo vòng lặp vô hạn.

### Restart sau khi claim

Cho job claim file, commit một số chunk rồi thất bại. Restart cùng identifying parameters và xác nhận file vẫn ở vị trí đã lưu, lock được acquire lại, reader/writer khôi phục checkpoint và output không trùng.

### Stale lease và fencing

Trong test database lease, cho owner A hết lease, owner B claim với fencing token mới, rồi mô phỏng owner A quay lại. Resource đích phải từ chối thao tác mang token cũ nếu yêu cầu fencing được triển khai.

## Các lỗi thường gặp

### Chỉ kiểm tra file tồn tại rồi bắt đầu đọc

Producer có thể vẫn đang ghi. Dùng giao thức publish sau khi đóng file, manifest hoặc ready marker.

### Dùng `synchronized` để khóa file giữa nhiều node

`synchronized` chỉ có hiệu lực trong một JVM. Dùng OS lock được filesystem hỗ trợ, atomic claim hoặc distributed lease.

### Nghĩ mọi chương trình đều tôn trọng FileLock

Nhiều file lock là advisory. Các process không tham gia giao thức vẫn có thể đọc/ghi file.

### Xóa lock file sau khi release

Có thể tạo race khi các process đã mở những file object khác nhau cùng tên. Với OS lock trên sidecar file, giữ file ổn định và chỉ release lock.

### Dùng marker không có TTL/owner

Process crash có thể để lại marker vĩnh viễn. Ghi owner metadata, lease và quy trình thu hồi an toàn.

### Xóa stale lock chỉ vì đã cũ

Owner có thể vẫn hoạt động hoặc đang bị pause/network partition. Dùng lease/heartbeat và fencing thay vì chỉ so sánh timestamp.

### Dùng FileLock trên shared filesystem mà chưa kiểm thử

NFS/SMB có semantics khác local disk. Xác nhận lock, rename, cache và crash recovery trên môi trường thực tế.

### Hai job dùng cùng output path

JobRepository không tự khóa file output. Dùng output path riêng theo logical execution hoặc claim lock độc quyền.

### Giữ lock qua I/O không có timeout

Một API hoặc database call bị treo có thể giữ file lock vô thời hạn. Đặt timeout ở từng resource và có cơ chế dừng/recovery.

### Cho rằng restart tự lấy lại lock cũ

Lock handle không được serialize. Restart phải acquire lock mới và xác minh file/resource vẫn đúng version.

### Cho rằng lock bảo đảm exactly-once

Crash có thể xảy ra giữa business commit và cập nhật trạng thái file. Cần idempotency, ledger, manifest hoặc outbox để xử lý replay.

## Nguyên tắc thiết kế

Khi xây dựng batch pipeline sử dụng file, hãy xác định:

1. Producer công bố file bằng cách nào để consumer biết file đã hoàn tất?
2. File identity gồm path, batch ID, version hoặc checksum nào?
3. Nhiều consumer claim file bằng OS lock, atomic move hay database lease?
4. Cơ chế khóa có hoạt động giữa các process/node và trên filesystem production không?
5. Lock được giữ trong khoảng thời gian nào và được release ở lifecycle nào?
6. Khi process chết, OS lock tự giải phóng hay marker/lease cần recovery?
7. Có fencing token để ngăn owner cũ tiếp tục ghi sau khi lease hết hạn không?
8. Input/output path có ổn định qua restart không?
9. Writer có state, transaction hoặc idempotency để tránh output trùng không?
10. File chỉ được archive/publish sau khi batch metadata và business output đạt trạng thái phù hợp không?
11. Monitoring có thể xác định owner, thời gian lock và file bị kẹt không?
12. Integration test đã mô phỏng contention, crash, stale lock và restart chưa?

Với pipeline local hoặc một host, `FileChannel`/`FileLock` có thể phù hợp nếu mọi consumer tuân thủ cùng giao thức và filesystem hỗ trợ. Với nhiều node, shared storage hoặc object storage, hãy chọn cơ chế claim/lease có semantics rõ ràng và kiểm thử failure mode. Kết hợp lock với checkpoint, idempotency và quy trình publish file hoàn chỉnh để job có thể dừng, restart và phục hồi an toàn.

## Ghi nhớ

File lock giúp phối hợp quyền truy cập giữa các tiến trình cùng tuân thủ giao thức; Java NIO cung cấp `FileChannel.lock()` và `tryLock()`, nhưng lock có thể mang tính advisory và phụ thuộc filesystem. `synchronized` chỉ khóa trong một JVM; nhiều node cần atomic claim, database lease hoặc distributed coordination phù hợp. Producer nên ghi file tạm rồi đóng và publish bằng atomic move/manifest; consumer claim file trước khi xử lý. Giữ lock xuyên suốt thời gian resource cần được bảo vệ, release bằng lifecycle rõ ràng và không serialize `FileLock` vào `ExecutionContext`. Khi crash, OS lock có thể được giải phóng nhưng marker có thể còn lại; lease, heartbeat và fencing giúp thu hồi an toàn. Spring Batch không tự khóa file cho reader/writer; cần phối hợp lock với `ItemStream`, checkpoint, output path ổn định, restart và idempotency để tránh xử lý trùng hoặc mất dữ liệu.
