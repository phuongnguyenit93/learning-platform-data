# File descriptor và tài nguyên do hệ điều hành quản lý

Một JVM đang chạy không chỉ giữ trạng thái trong heap. Nó còn sử dụng các tài nguyên do kernel và môi trường vận hành cung cấp: file đang mở, socket, pipe, khóa file, timer, thiết bị, kết nối cơ sở dữ liệu và nhiều handle native khác. Đây là phần cần xử lý cẩn thận khi dùng **CRaC (Coordinated Restore at Checkpoint)**.

CRaC chụp trạng thái của một tiến trình Java đã khởi động và khôi phục tiến trình từ ảnh checkpoint. Sau restore, chương trình tiếp tục từ trạng thái đã chụp. Tuy nhiên, một số tài nguyên bên ngoài tiến trình không thể được xem như dữ liệu Java thông thường. Một số handle có thể không được checkpoint engine lưu lại an toàn; một số khác có thể trỏ tới môi trường đã thay đổi. Vì vậy, ứng dụng cần chủ động giải phóng chúng trước checkpoint và tạo lại chúng sau restore.

Bài này tập trung vào cách hiểu file descriptor, nhận diện các tài nguyên hệ điều hành có thể ảnh hưởng đến CRaC, và tổ chức vòng đời của chúng bằng API Resource.

## 1. File descriptor là gì?

Trên Unix và Linux, **file descriptor (FD)** là một số nguyên không âm mà tiến trình dùng để tham chiếu tới một đối tượng I/O do kernel quản lý. FD thường được tạo ra khi chương trình mở file, tạo socket, tạo pipe hoặc gọi một system call cần handle I/O.

Trong Java, lập trình viên thường thao tác với các lớp cấp cao như:

- **FileInputStream**, **FileOutputStream**, **RandomAccessFile**.
- **FileChannel** và các lớp trong Java NIO.
- **Socket**, **ServerSocket**, **DatagramSocket**.
- **SocketChannel**, **ServerSocketChannel**, **Pipe**.
- Các thư viện JDBC, HTTP hoặc thư viện native có thể tạo handle ở bên dưới.

Các lớp Java này che giấu phần lớn chi tiết của FD. Một **FileInputStream** có thể giữ một **FileDescriptor**, còn **Socket** hoặc NIO channel giữ trạng thái native tương ứng.

### 1.1 Từ đối tượng Java tới kernel

Có thể hình dung đường đi của một thao tác đọc file như sau:

~~~mermaid
flowchart LR
    A["FileInputStream trong Java"] --> B["FileDescriptor / native handle"]
    B --> C["Bảng FD của tiến trình<br/>ví dụ: số 7"]
    C --> D["Open file description trong kernel"]
    D --> E["File, socket, pipe hoặc device"]
~~~

Số FD chỉ là chỉ mục trong bảng descriptor của một tiến trình. Nó không phải là bản thân file hay socket. Kernel dùng descriptor đó để tìm tới trạng thái mở tương ứng.

Với file thông thường, trạng thái mở ở kernel có thể chứa vị trí đọc/ghi hiện tại, các cờ trạng thái và tham chiếu tới file. Với socket, kernel còn quản lý trạng thái giao thức, hàng đợi dữ liệu nhận/gửi và thông tin kết nối. Những phần này nằm ngoài heap Java.

Hai FD khác nhau có thể cùng tham chiếu tới một open file description, chẳng hạn sau thao tác **dup**. Vì vậy, đóng một FD chưa chắc đã giải phóng đối tượng kernel nếu vẫn còn descriptor khác tham chiếu tới nó.

### 1.2 Vì sao chỉ lưu số FD là không đủ?

Giả sử một tiến trình đang có FD số 7 trỏ tới một file. Sau khi file được đóng, kernel có thể tái sử dụng số 7 cho một socket mới. Do đó, số 7 không mang ý nghĩa định danh bền vững.

Một checkpoint image có thể lưu trạng thái bộ nhớ của tiến trình, bao gồm các số nguyên và đối tượng Java đang giữ chúng. Nhưng việc giữ nguyên một số FD trong bộ nhớ không tự bảo đảm rằng đối tượng kernel phía sau vẫn còn đúng, vẫn thuộc cùng tài nguyên, hoặc có thể sử dụng an toàn trong môi trường restore.

Đối với socket, vấn đề còn rõ hơn: kết nối TCP có trạng thái ở cả hai đầu. Giữ lại một tham chiếu Java không thể bảo đảm peer vẫn còn kết nối, đường mạng vẫn giống trước checkpoint, hay trạng thái phiên đăng nhập vẫn hợp lệ sau restore.

## 2. Vì sao file descriptor và tài nguyên OS quan trọng với CRaC?

Trong một lần checkpoint, CRaC phối hợp với checkpoint engine để lưu trạng thái của tiến trình. Trước khi tạo ảnh, ứng dụng nhận callback **beforeCheckpoint**. Sau khi ảnh được khôi phục, ứng dụng nhận callback **afterRestore**.

Cần phân biệt hai nhóm trạng thái:

- **Trạng thái nội bộ của ứng dụng:** object Java, dữ liệu heap, trạng thái logic, cấu trúc dữ liệu và các biến trong tiến trình.
- **Tài nguyên bên ngoài tiến trình:** trạng thái kernel, kết nối tới dịch vụ khác, file trên filesystem, thiết bị, tài nguyên container và các dịch vụ từ xa.

Nhóm thứ hai có thể thay đổi trong khoảng thời gian giữa checkpoint và restore. Ngay cả khi checkpoint engine có thể giữ một số tài nguyên trong một môi trường cụ thể, ứng dụng vẫn phải xem xét liệu tài nguyên đó có còn đúng về mặt nghiệp vụ sau restore hay không.

Ví dụ:

- File cấu hình có thể được cập nhật trong lúc ứng dụng đang ở trạng thái checkpoint.
- Server từ xa có thể đã đóng kết nối TCP.
- Database có thể đã hết phiên hoặc thu hồi connection.
- Container có thể được khởi động trên host khác, với địa chỉ IP, route hoặc mount khác.
- File lock có thể không còn được giữ.
- Timer và deadline có thể đã quá hạn do thời gian thực đã trôi qua.

CRaC vì vậy yêu cầu ứng dụng chuẩn bị các tài nguyên không thể khôi phục an toàn. Một số runtime có thể phát hiện FD còn mở và từ chối checkpoint với lỗi. Danh sách descriptor được phép giữ lại có thể bao gồm một số FD chuẩn hoặc FD nội bộ của runtime; chi tiết phụ thuộc bản JDK, CRaC runtime và checkpoint engine.

## 3. Những tài nguyên cần kiểm kê

Không phải mọi tài nguyên OS đều được quản lý bằng cùng một loại FD. Khi chuẩn bị ứng dụng cho CRaC, hãy kiểm kê cả tài nguyên Java, native và tài nguyên từ xa.

| Tài nguyên | Rủi ro khi restore | Xử lý thường dùng |
|---|---|---|
| File input/output | File có thể thay đổi, descriptor có thể không còn hợp lệ, buffer chưa được ghi hết | Flush dữ liệu cần giữ, lưu vị trí logic, đóng trước checkpoint và mở lại sau restore |
| File channel | Channel giữ FD và trạng thái vị trí đọc/ghi | Lưu vị trí cần thiết, đóng channel, tạo channel mới |
| TCP/UDP socket | Peer hoặc trạng thái kết nối có thể đã thay đổi | Đóng socket, kết nối lại, xác thực và khôi phục subscription |
| Server socket | Port hoặc môi trường mạng có thể thay đổi; listener có thể còn hoạt động ở trạng thái cũ | Dừng nhận kết nối, đóng listener, bind và listen lại sau restore |
| Database connection | Session, transaction hoặc connection pool có thể hết hiệu lực | Kết thúc transaction đúng cách, đóng hoặc invalidate pool, tạo pool/connection mới |
| Pipe và process handle | Tiến trình con hoặc đầu pipe có thể không được khôi phục cùng ứng dụng | Đồng bộ tiến trình con, đóng pipe và tạo lại quan hệ IPC khi cần |
| File lock | Lock thuộc kernel và có thể được giải phóng khi channel đóng | Lưu trạng thái nghiệp vụ, đóng channel, xin lock lại và xử lý trường hợp lock đã bị tiến trình khác lấy |
| Memory mapping | Mapping phụ thuộc file và filesystem; file có thể bị thay thế hoặc thay đổi | Kiểm tra hỗ trợ của runtime, giải phóng hoặc tạo mapping lại theo thiết kế |
| epoll, eventfd, io_uring | Đây là trạng thái I/O ở kernel, không chỉ là object Java | Dừng event loop, giải phóng native handle, dựng lại selector/event loop |
| Timer, device handle | Trạng thái timer hoặc thiết bị có thể phụ thuộc host và thời gian thực | Hủy timer cũ, tính lại deadline và mở thiết bị lại |
| JNI/native library handle | Native code có thể mở FD mà Java không biết | Bổ sung hook quản lý native resource hoặc sửa thư viện để đóng và tạo lại handle |

Bảng này là điểm khởi đầu cho việc kiểm kê. Cách xử lý cụ thể phụ thuộc vào semantics của tài nguyên: có tài nguyên cần khôi phục đúng vị trí, có tài nguyên phải kết nối lại, và có tài nguyên nên được tạo mới hoàn toàn.

## 4. Vòng đời Resource trong CRaC

CRaC cung cấp API để ứng dụng đăng ký các đối tượng quan tâm tới hai thời điểm trong vòng đời checkpoint/restore.

Một resource triển khai interface **Resource** và được đăng ký với một **Context**. Context toàn cục lấy từ **Core.getGlobalContext()** thường là lựa chọn đơn giản nhất.

Hai callback chính:

- **beforeCheckpoint(Context)**: chạy trước khi checkpoint được tạo. Resource dừng hoạt động liên quan, flush dữ liệu cần thiết, lưu trạng thái logic và đóng tài nguyên OS.
- **afterRestore(Context)**: chạy sau khi tiến trình được khôi phục. Resource tạo lại file channel, socket, pool hoặc handle cần thiết để ứng dụng tiếp tục hoạt động.

Ví dụ cấu trúc:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ManagedResource implements Resource {

    public ManagedResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Dừng sử dụng và giải phóng tài nguyên OS.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Tạo lại tài nguyên để ứng dụng tiếp tục hoạt động.
    }
}
~~~

Ví dụ dùng package **org.crac**, là API tương thích được dự án CRaC cung cấp cho ứng dụng. Một số bản JDK tích hợp CRaC cung cấp API trong package **jdk.crac**. Hãy dùng package và phiên bản phù hợp với JDK/runtime của dự án.

### 4.1 Thứ tự callback

Với global context trong tài liệu CRaC, callback **beforeCheckpoint** được gọi theo thứ tự đăng ký resource; callback **afterRestore** được gọi theo thứ tự ngược lại.

Điều này hữu ích khi các resource phụ thuộc nhau. Ví dụ, một HTTP server phụ thuộc vào connection pool:

- Trước checkpoint, server nên ngừng nhận request và hoàn tất request đang xử lý trước khi pool bị đóng.
- Sau restore, pool cần sẵn sàng trước khi server nhận request mới.

Nếu đăng ký resource theo thứ tự phù hợp, thứ tự callback ngược nhau có thể hỗ trợ quá trình đóng và mở tài nguyên theo đúng quan hệ phụ thuộc. Với custom context hoặc framework quản lý resource riêng, cần kiểm tra chính sách thứ tự của context đó.

### 4.2 Lỗi trong callback

Nếu resource không thể chuẩn bị an toàn, callback **beforeCheckpoint** nên ném exception để checkpoint bị từ chối. Không nên bắt lỗi rồi bỏ qua, vì checkpoint có thể tạo ra ảnh không nhất quán.

Tương tự, nếu **afterRestore** không thể tạo lại tài nguyên thiết yếu, ứng dụng không nên báo trạng thái sẵn sàng. Hãy để lỗi được truyền lên cơ chế restore hoặc readiness của ứng dụng xử lý. Với tài nguyên có thể khôi phục bằng retry, hãy xác định rõ thời hạn retry và thời điểm cho phép nhận traffic.

## 5. Ví dụ: đóng và mở lại FileChannel

Một file channel giữ handle tới file do kernel quản lý. Khi checkpoint, ta có thể lưu vị trí đọc hiện tại, đóng channel và mở channel mới sau restore.

Ví dụ sau giả định một đối tượng reader là nơi duy nhất quản lý channel. Các thao tác đọc và callback được đồng bộ bằng cùng monitor để không lưu vị trí giữa lúc một thread khác đang đọc.

~~~java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ResumableFileReader
        implements Resource, AutoCloseable {

    private final Path path;
    private FileChannel channel;
    private long savedPosition;

    public ResumableFileReader(Path path) throws IOException {
        this.path = path;
        openAtSavedPosition();
        Core.getGlobalContext().register(this);
    }

    public synchronized int read(ByteBuffer destination)
            throws IOException {
        if (channel == null) {
            throw new IllegalStateException("File channel is not open");
        }

        int count = channel.read(destination);
        if (count > 0) {
            savedPosition = channel.position();
        }
        return count;
    }

    private void openAtSavedPosition() throws IOException {
        FileChannel reopened = FileChannel.open(
                path, StandardOpenOption.READ);
        try {
            reopened.position(savedPosition);
            channel = reopened;
        } catch (IOException e) {
            try {
                reopened.close();
            } catch (IOException closeError) {
                e.addSuppressed(closeError);
            }
            throw e;
        }
    }

    @Override
    public synchronized void beforeCheckpoint(
            Context<? extends Resource> context) throws IOException {
        if (channel != null) {
            savedPosition = channel.position();
            channel.close();
            channel = null;
        }
    }

    @Override
    public synchronized void afterRestore(
            Context<? extends Resource> context) throws IOException {
        openAtSavedPosition();
    }

    @Override
    public synchronized void close() throws IOException {
        if (channel != null) {
            channel.close();
            channel = null;
        }
    }
}
~~~

Điểm cần chú ý:

1. **Lưu trạng thái logic.** Ví dụ lưu vị trí đọc, thay vì cố giữ lại số FD.
2. **Đóng handle trước checkpoint.** Khi channel đóng thành công, FD tương ứng được giải phóng.
3. **Tạo handle mới sau restore.** Channel mới được mở từ đường dẫn và đưa về vị trí đã lưu.
4. **Đồng bộ truy cập.** Cùng một monitor bảo vệ thao tác đọc và hai callback, tránh việc lưu vị trí khi một thao tác đọc chưa hoàn tất.
5. **Xử lý thay đổi file.** Nếu file có thể bị thay thế hoặc sửa trong thời gian checkpoint, chỉ lưu vị trí byte có thể chưa đủ. Ứng dụng có thể cần lưu file key, version, checksum hoặc một cursor nghiệp vụ, rồi xác minh file trước khi tiếp tục.

Trong ứng dụng thực tế, hãy quyết định rõ semantics khi file thay đổi: đọc tiếp từ file mới, bắt đầu lại, hoặc từ chối restore. Không nên mặc định rằng đường dẫn sau restore luôn trỏ tới cùng nội dung như trước checkpoint.

## 6. Ví dụ: kết nối mạng và database

### 6.1 Socket

Một socket đang mở đại diện cho trạng thái kết nối do kernel và peer cùng duy trì. Sau checkpoint, peer có thể đã đóng kết nối hoặc phiên xác thực đã hết hạn. Vì vậy, cách phổ biến là đóng socket trước checkpoint và tạo kết nối mới sau restore.

~~~java
@Override
public synchronized void beforeCheckpoint(
        Context<? extends Resource> context) throws IOException {
    if (socket != null) {
        socket.close();
        socket = null;
    }
}

@Override
public synchronized void afterRestore(
        Context<? extends Resource> context) throws IOException {
    socket = openNewSocket();
}
~~~

**openNewSocket()** cần thực hiện đầy đủ các bước cần thiết: tạo socket, connect với timeout, TLS handshake nếu có, xác thực, và đăng ký lại subscription hoặc listener ở tầng ứng dụng.

Không thể tiếp tục một transaction hoặc message exchange đang dở chỉ bằng cách mở lại socket. Hãy thiết kế giao thức để ứng dụng có thể xác định message nào đã được xử lý, message nào cần gửi lại, và thao tác nào phải idempotent. Nếu kết nối mới thất bại, ứng dụng cần giữ trạng thái chưa sẵn sàng cho tới khi kết nối được khôi phục.

### 6.2 Database connection và connection pool

Một JDBC connection thường đại diện cho một session ở database server. Session đó có thể bị timeout hoặc bị server đóng trong thời gian ứng dụng ở trạng thái checkpoint.

Quy trình phù hợp thường là:

1. Ngừng nhận công việc mới và chờ các request đang chạy hoàn tất.
2. Commit hoặc rollback transaction theo quy tắc nghiệp vụ.
3. Đóng connection đang mượn và đóng hoặc invalidate connection pool trước checkpoint.
4. Sau restore, tạo pool mới hoặc yêu cầu framework khởi tạo lại pool.
5. Kiểm tra kết nối và chỉ mở readiness khi pool hoạt động.

Không nên checkpoint giữa một transaction đang mở nếu ứng dụng không có cơ chế phục hồi transaction rõ ràng. Cũng không nên trả một connection cũ về pool sau restore chỉ vì object Java của nó vẫn tồn tại trong heap.

Nếu framework như Spring Boot, Quarkus hoặc Micronaut đã tích hợp CRaC, hãy ưu tiên cơ chế lifecycle do framework cung cấp. Tránh đăng ký một resource riêng có thể đóng cùng connection pool lần thứ hai hoặc xung đột với thứ tự shutdown của framework.

## 7. Phối hợp thread và luồng xử lý

Đóng file và socket chỉ là một phần của quá trình chuẩn bị. Ứng dụng còn cần bảo đảm không có thread đang sử dụng tài nguyên trong lúc callback đóng nó.

Một trình tự chuẩn bị thường gặp:

1. **Ngừng nhận công việc mới:** tạm dừng HTTP listener, consumer hoặc scheduler.
2. **Drain công việc đang chạy:** chờ request, message handler và transaction hoàn tất trong giới hạn thời gian.
3. **Dừng hoặc tạm dừng worker:** bảo đảm thread không tiếp tục truy cập tài nguyên sắp đóng.
4. **Flush dữ liệu:** ghi các buffer quan trọng và lưu trạng thái logic cần thiết.
5. **Đóng tài nguyên:** đóng file, channel, socket, pool và native handle.
6. **Tạo checkpoint.**
7. **Sau restore, dựng lại dependency:** mở file, tạo pool, kết nối dịch vụ và khởi động worker.
8. **Mở lại traffic:** chỉ cho phép nhận request khi các thành phần thiết yếu đã sẵn sàng.

Cần thiết kế timeout cho bước drain. Nếu một request không thể hoàn tất trong thời gian cho phép, hãy quyết định rõ việc hủy request, lưu checkpoint thất bại hay trì hoãn checkpoint. Không nên đóng cưỡng bức một tài nguyên trong khi thread khác vẫn có thể ghi vào nó.

Với hệ thống có nhiều tầng phụ thuộc, thứ tự đóng và mở rất quan trọng. Thành phần nhận traffic nên dừng trước các dependency mà nó sử dụng; khi restore, dependency nên sẵn sàng trước khi thành phần nhận traffic khởi động lại.

## 8. Tài nguyên native và FD không được Java quản lý trực tiếp

Không phải mọi FD đều xuất phát từ **FileInputStream** hoặc **Socket**. JNI, JNA, thư viện C/C++ và một số framework có thể gọi trực tiếp system call để tạo descriptor.

Ví dụ:

- Native library mở file bằng **open()** hoặc socket bằng **socket()**.
- Thư viện logging hoặc metrics tự quản lý file handle.
- Event loop tạo epoll descriptor, eventfd hoặc timerfd.
- Thư viện IPC tạo pipe hoặc Unix domain socket.
- Driver hoặc SDK tạo handle tới thiết bị.

Nếu native library không cung cấp API đóng và mở lại tài nguyên, Java code khó có thể quản lý đúng vòng đời của chúng. Cần làm việc với thư viện để bổ sung lifecycle hook, hoặc thay đổi cách tích hợp để ứng dụng có thể dừng, giải phóng và khởi tạo lại thành phần đó.

Các tài nguyên như memory mapping, direct memory và handle native cần được đánh giá theo runtime và checkpoint engine đang dùng. Không nên suy luận rằng vì một object Java vẫn tồn tại sau restore nên mọi tài nguyên native phía dưới nó cũng hợp lệ.

## 9. Phát hiện file descriptor còn mở

Trên Linux, có thể kiểm tra descriptor của một tiến trình qua filesystem ảo **/proc** hoặc công cụ hệ thống.

### 9.1 Dùng lsof

~~~bash
lsof -p <PID>
~~~

Lệnh này liệt kê file, socket, pipe và các đối tượng đang được tiến trình giữ mở. Có thể lọc theo loại tài nguyên hoặc đường dẫn để tìm thành phần đáng chú ý.

### 9.2 Xem /proc

~~~bash
ls -l /proc/<PID>/fd
~~~

Mỗi mục trong thư mục là một descriptor của tiến trình. Đường dẫn đích thường cho biết descriptor đang trỏ tới file, socket, pipe hoặc đối tượng nào. Đây là cách nhanh để kiểm tra FD còn mở khi không có lsof.

### 9.3 Dùng lỗi checkpoint và stack trace

Nếu checkpoint thất bại vì FD còn mở, hãy đọc toàn bộ exception và các suppressed exception. Một lỗi cấp cao như **CheckpointException** có thể chứa chi tiết về descriptor cụ thể, loại tài nguyên và đường dẫn.

Với một số bản CRaC JDK, có thể bật:

~~~bash
-Djdk.crac.collect-fd-stacktraces=true
~~~

Tùy runtime, tùy chọn này giúp ghi lại stack trace tại thời điểm FD được tạo qua API Java, nhờ đó dễ tìm lớp đã mở file nhưng quên đóng.

Nếu FD được tạo trực tiếp từ native code, stack trace Java có thể không có. Khi đó, **strace** có thể giúp tìm system call tạo descriptor:

~~~bash
strace -f -o /tmp/strace.log java -jar app.jar
~~~

Sau đó tìm các system call như **openat**, **socket**, **accept**, **pipe**, **dup** và đối chiếu với thời điểm checkpoint. Cần lưu ý rằng tracing có thể tạo nhiều log và làm thay đổi timing của ứng dụng.

### 9.4 Resource policy của JDK

Một số CRaC runtime có cơ chế cấu hình policy cho một số FD được mở thông qua JDK API. Policy có thể quy định hành động như báo lỗi, đóng hoặc mở lại một số loại tài nguyên.

Đây là công cụ hỗ trợ trong trường hợp khó sửa thư viện, nhưng có giới hạn:

- Policy không thay thế việc quản lý lifecycle của ứng dụng.
- FD được tạo trực tiếp từ native code có thể nằm ngoài phạm vi policy.
- Đóng tự động có thể khiến object Java còn tham chiếu tới handle đã đóng.
- Mở lại socket hoặc tài nguyên đặc biệt có thể không được hỗ trợ hoặc không giữ được semantics cũ.

Chỉ dùng policy sau khi đã hiểu tài nguyên nào được khớp, hành động nào được thực hiện và object Java sẽ hoạt động ra sao sau restore. Với tài nguyên quan trọng, callback **Resource** tường minh thường dễ kiểm soát hơn.

## 10. Những lỗi thiết kế thường gặp

### Giữ object Java nhưng quên đóng tài nguyên bên dưới

Một biến instance còn tồn tại sau restore không chứng minh rằng FD hoặc socket mà nó tham chiếu còn hợp lệ. Object có thể giữ trạng thái cũ trong khi kernel resource đã bị đóng hoặc thay đổi.

### Chỉ đóng một wrapper trong khi còn descriptor khác

Nếu native code hoặc thư viện khác đã duplicate FD, đóng một wrapper có thể chưa giải phóng open file description. Cần xác định toàn bộ nơi sở hữu handle và quy ước ownership rõ ràng.

### Đóng stream nhưng chưa flush dữ liệu

Đóng tài nguyên có thể flush buffer tùy lớp và cách sử dụng. Với dữ liệu quan trọng, hãy flush tường minh và kiểm tra lỗi trước khi checkpoint. Đừng giả định rằng mọi buffer của thư viện đều được ghi an toàn khi callback kết thúc.

### Giữ transaction hoặc request đang xử lý

Checkpoint giữa một thao tác nghiệp vụ có thể để lại trạng thái khó xác định: phía ứng dụng nghĩ rằng thao tác chưa hoàn thành nhưng dịch vụ từ xa đã xử lý. Hãy xác định điểm an toàn để checkpoint, dùng idempotency key hoặc cơ chế xác nhận phù hợp.

### Nuốt exception trong callback

Nếu đóng file hoặc kết nối thất bại mà callback vẫn trả về bình thường, checkpoint có thể tiếp tục trong trạng thái chưa an toàn. Hãy truyền lỗi lên CRaC để checkpoint bị từ chối.

### Giả định môi trường restore giống hệt môi trường checkpoint

Địa chỉ IP, DNS, mount, credentials, certificate, filesystem hoặc phiên dịch vụ có thể thay đổi. Hãy phân giải lại và xác thực lại các phụ thuộc môi trường sau restore khi cần.

### Mở lại tài nguyên nhưng không khôi phục trạng thái nghiệp vụ

Tạo socket mới không tự khôi phục subscription; mở file mới không tự khôi phục cursor đúng nghĩa; tạo connection pool mới không tự khôi phục transaction. Hãy lưu và khôi phục trạng thái nghiệp vụ ở mức phù hợp.

## 11. Quy trình triển khai cho một ứng dụng CRaC

Có thể áp dụng quy trình sau khi đưa CRaC vào một dịch vụ Java hiện có:

**Bước 1 — Lập danh sách tài nguyên.** Tìm các lớp I/O, JDBC, HTTP client, message consumer, scheduler, thư viện native, file lock và tài nguyên thiết bị. Kiểm tra cả tài nguyên được framework tạo tự động.

**Bước 2 — Xác định owner.** Mỗi tài nguyên cần có một thành phần chịu trách nhiệm mở, đóng và mở lại. Tránh để nhiều lớp cùng đóng một handle mà không có quy ước ownership.

**Bước 3 — Chọn trạng thái cần lưu.** Lưu dữ liệu logic như vị trí đọc, offset message, cấu hình hoặc trạng thái subscription. Tránh lưu số FD như một cách khôi phục tài nguyên.

**Bước 4 — Viết callback có thể kiểm soát.** **beforeCheckpoint** dừng hoạt động liên quan, lưu trạng thái và giải phóng tài nguyên. **afterRestore** tạo lại tài nguyên và xác minh chúng trước khi ứng dụng hoạt động.

**Bước 5 — Kiểm tra thứ tự phụ thuộc.** Đảm bảo consumer dừng trước dependency và dependency sẵn sàng trước consumer. Kiểm tra thứ tự callback của context hoặc framework thực tế.

**Bước 6 — Thử checkpoint khi tải đã ổn định.** Quan sát exception, suppressed exception, FD còn mở và log của checkpoint engine. Lặp lại với các loại request hoặc workload có sử dụng tài nguyên khác nhau.

**Bước 7 — Thử restore trong môi trường mục tiêu.** Xác minh file, socket, database, DNS, certificate, timer và readiness. Nếu môi trường restore có thể khác host, hãy kiểm thử cả trường hợp đó.

**Bước 8 — Theo dõi sau restore.** Đo thời gian khởi tạo lại dependency, tỷ lệ kết nối lại thất bại, số FD, lỗi request và độ trễ trước khi mở traffic.

Một ứng dụng chỉ nên được xem là sẵn sàng sau restore khi các dependency cần thiết đã được khởi tạo và kiểm tra thành công. Đây là trách nhiệm của lifecycle ứng dụng hoặc framework, không chỉ của checkpoint engine.

## Tài liệu tham khảo

- [CRaC — What CRaC is](https://crac.org/about/about-crac/): mô hình checkpoint/restore và lý do cần phối hợp tài nguyên.
- [CRaC — Integrating CRaC in your Application](https://docs.azul.com/crac/usage/integrating-crac): đăng ký Resource và triển khai **beforeCheckpoint** / **afterRestore**.
- [CRaC — Debugging](https://crac.org/reference/debugging/): lỗi do FD còn mở, stack trace và cách điều tra descriptor native.
- [CRaC — File descriptor policies](https://crac.org/reference/fd-policies/): giới hạn và cấu hình policy cho một số file descriptor.
- [CRaC Resource API](https://crac.org/openjdk-builds/javadoc/api/java.base/jdk/crac/Resource.html): hợp đồng callback của interface Resource.

