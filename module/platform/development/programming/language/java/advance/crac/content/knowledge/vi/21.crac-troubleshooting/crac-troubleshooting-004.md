# Thu thập vị trí tạo file descriptor bằng jdk.crac.collect-fd-stacktraces

Khi tạo checkpoint, CRaC cần đưa tiến trình về trạng thái có thể được khôi phục an toàn. Một phần của công việc đó là kiểm tra các file descriptor (FD) còn mở. File descriptor là handle cấp hệ điều hành mà process dùng để truy cập file, socket, pipe và nhiều loại tài nguyên khác. Nếu ứng dụng vẫn giữ một FD không thể được mang qua checkpoint, thao tác checkpoint có thể thất bại với CheckpointException.

Một lỗi thường cho biết FD nào còn mở và đường dẫn hoặc loại tài nguyên của nó. Nhưng thông tin đó chưa trả lời câu hỏi quan trọng nhất: đoạn mã nào đã mở FD này? Thuộc tính CRaC system property jdk.crac.collect-fd-stacktraces được thiết kế để hỗ trợ chẩn đoán trường hợp file descriptor được tạo thông qua Java FileDescriptor. Khi bật thuộc tính này, runtime ghi lại stack trace tại thời điểm FileDescriptor được tạo và đưa thông tin đó vào exception khi checkpoint phát hiện FD còn mở.

Thuộc tính này giúp lần ngược từ một FD bị bỏ quên đến constructor hoặc thư viện đã tạo ra nó. Nó không tự đóng FD, không sửa lifecycle của ứng dụng và không thu thập được stack trace cho mọi FD được mở trực tiếp từ native code. Bài học này giải thích cách bật thuộc tính, đọc kết quả, tìm nguồn gốc FD trong Java và chuyển sang công cụ hệ điều hành khi nguồn mở nằm trong native code.

## 1. File descriptor là gì?

Trên Unix/Linux, file descriptor là một số nguyên không âm được process dùng làm chỉ mục đến một entry trong bảng file descriptor của process. Kernel dùng entry đó để theo dõi một open file description hoặc tài nguyên liên quan.

FD có thể đại diện cho nhiều loại tài nguyên:

- File thông thường được mở để đọc hoặc ghi.
- Socket TCP/UDP.
- Pipe hoặc FIFO.
- Event descriptor và các handle kernel khác.
- Listening socket của web server.
- File lock hoặc channel đang giữ file.
- Một số tài nguyên được thư viện native tạo ra.

Trong Java, các lớp như FileInputStream, FileOutputStream, RandomAccessFile và một số channel hoặc stream có thể sử dụng FileDescriptor để đại diện cho FD ở tầng native. Nhiều API khác có thể mở tài nguyên trực tiếp thông qua native code hoặc thư viện hệ thống, không nhất thiết có một đối tượng FileDescriptor Java tương ứng.

Ví dụ, khi gọi:

~~~java
FileInputStream input = new FileInputStream("/var/app/config.json");
~~~

JVM mở file ở hệ điều hành và gắn FD vào đối tượng Java liên quan. Nếu input không được đóng, FD có thể vẫn còn mở khi ứng dụng yêu cầu checkpoint.

Các FD 0, 1 và 2 thường tương ứng với standard input, standard output và standard error. CRaC thường giữ các stream chuẩn này và một số FD cần thiết cho runtime hoặc classpath. Những FD ứng dụng khác cần được xử lý theo quy tắc của CRaC và engine đang dùng.

## 2. Vì sao FD còn mở có thể làm checkpoint thất bại?

Checkpoint lưu trạng thái tiến trình để restore sau này. Một file descriptor đang mở có thể gắn với trạng thái kernel bên ngoài tiến trình: socket kết nối đến server, file đang bị khóa, pipe nối với process khác hoặc file được mount từ một môi trường cụ thể.

Nếu FD đó không thể được lưu và khôi phục đúng cách, tiến trình sau restore có thể tham chiếu đến tài nguyên không còn tồn tại hoặc không còn thuộc cùng môi trường. Vì vậy, CRaC yêu cầu ứng dụng phối hợp để đóng hoặc xử lý các FD không phù hợp trước checkpoint.

Một lỗi thường có dạng:

~~~text
Exception in thread "main" jdk.crac.CheckpointException
    at ... application code ...
    Suppressed: jdk.crac.impl.CheckpointOpenFileException:
        FileDescriptor 4 left open: /var/app/data/input.csv (regular)
        at java.base/java.io.FileDescriptor.beforeCheckpoint(...)
        at java.base/java.io.FileDescriptor$Resource.beforeCheckpoint(...)
        ...
~~~

Thông tin này cho biết:

- CheckpointException là lỗi tổng hợp ở cấp checkpoint.
- CheckpointOpenFileException là một vấn đề cụ thể được phát hiện trong quá trình kiểm tra resource.
- FileDescriptor 4 là số FD trong process ở thời điểm kiểm tra.
- Đường dẫn cho biết file đang mở nếu runtime xác định được.
- regular cho biết loại tài nguyên được nhận diện.

CheckpointException có thể chứa nhiều suppressed exception, mỗi exception mô tả một FD hoặc resource không đáp ứng điều kiện checkpoint. Vì vậy, cần đọc toàn bộ stack trace thay vì chỉ nhìn dòng exception đầu tiên.

Thông báo cho biết FD còn mở tại thời điểm checkpoint; nó không tự xác định đoạn mã đã tạo FD đó. Thuộc tính jdk.crac.collect-fd-stacktraces giúp bổ sung thông tin nguồn gốc cho các FD được tạo qua Java FileDescriptor.

## 3. jdk.crac.collect-fd-stacktraces làm gì?

jdk.crac.collect-fd-stacktraces là một Java system property dành cho CRaC. Khi được bật, runtime ghi nhận stack trace tại thời điểm một Java FileDescriptor được tạo. Nếu FD tương ứng vẫn còn mở và bị CRaC phát hiện khi checkpoint, exception có thể chứa cause chỉ ra thread và call stack đã tạo descriptor.

Ví dụ, thay vì chỉ thấy:

~~~text
Suppressed: jdk.crac.impl.CheckpointOpenFileException:
    FileDescriptor 4 left open: /etc/passwd (regular)
~~~

kết quả có thể thêm phần nguyên nhân:

~~~text
Caused by: java.lang.Exception:
    This file descriptor was created by main at epoch:1684328308663
    at java.base/java.io.FileDescriptor$Resource.<init>(...)
    at java.base/java.io.FileDescriptor.<init>(...)
    at java.base/java.io.FileInputStream.<init>(...)
    at java.base/java.io.FileReader.<init>(...)
    at ... application code ...
~~~

Stack trace này giúp xác định constructor hoặc call path đã mở file. Tên thread cũng giúp biết FD được tạo từ luồng nào. Thời điểm epoch là timestamp được ghi nhận lúc tạo descriptor; một số FD được tạo rất sớm trong quá trình khởi tạo VM có thể không được định dạng thành thời gian dễ đọc.

Cần hiểu đúng phạm vi:

- Property ghi lại vị trí tạo Java FileDescriptor.
- Nó không ghi lại mọi lần FD được sử dụng.
- Nó không tự xác định component nào hiện đang sở hữu FD nếu FD đã được chuyển giao.
- Nó không tự đóng FD hoặc thay đổi cách checkpoint xử lý FD.
- Nó không bảo đảm có stack trace cho FD được mở trực tiếp từ native code mà không thông qua Java FileDescriptor.
- Nó là công cụ chẩn đoán; cách hỗ trợ và tên property cần được xác nhận trên đúng CRaC JDK distribution.

## 4. Bật property khi khởi động JVM

Đặt property bằng tùy chọn -D ngay trên lệnh khởi động Java:

~~~bash
java \
  -Djdk.crac.collect-fd-stacktraces=true \
  -XX:CRaCCheckpointTo=./checkpoint \
  -jar app.jar
~~~

Trong ví dụ này:

- -Djdk.crac.collect-fd-stacktraces=true bật việc thu thập stack trace.
- -XX:CRaCCheckpointTo chỉ định nơi lưu checkpoint theo runtime hỗ trợ.
- -jar app.jar khởi chạy ứng dụng.

Nếu ứng dụng tự gọi Core.checkpointRestore(), property vẫn cần được đặt khi JVM khởi động:

~~~bash
java -Djdk.crac.collect-fd-stacktraces=true -jar app.jar
~~~

Không nên đợi đến lúc bắt đầu checkpoint mới gọi System.setProperty(). Stack trace cần được ghi lại tại thời điểm FD được tạo. Nếu FD đã mở từ trước khi property được bật, runtime không thể tái tạo call stack tạo FD đó một cách đáng tin cậy.

Có thể đặt property qua biến môi trường JAVA_TOOL_OPTIONS trong môi trường chẩn đoán:

~~~bash
export JAVA_TOOL_OPTIONS="-Djdk.crac.collect-fd-stacktraces=true"
java -XX:CRaCCheckpointTo=./checkpoint -jar app.jar
~~~

Cần bảo đảm biến môi trường chỉ áp dụng cho đúng tiến trình cần điều tra. Khi chạy trong container, có thể truyền JVM option qua cấu hình entrypoint hoặc JAVA_TOOL_OPTIONS của container.

## 5. Property mặc định và tính tương thích theo JDK

jdk.crac.collect-fd-stacktraces là property thuộc triển khai CRaC, không phải thuộc tính chuẩn của Java SE. Không nên giả định mọi JDK vendor hoặc mọi bản build CRaC đều hỗ trợ giống nhau.

Tài liệu CRaC của Azul liệt kê property này trong nhóm system properties của Community Availability builds, dùng ở giai đoạn checkpoint và có giá trị mặc định false cho các bản được liệt kê. Hãy kiểm tra tài liệu của đúng vendor, JDK version và build đang triển khai trước khi dựa vào nó.

Một số lưu ý:

- Nếu property không được runtime hỗ trợ, truyền -D có thể chỉ tạo một system property thông thường mà không bật chức năng chẩn đoán.
- Việc System.getProperty() trả về true chỉ chứng minh property đã được đặt trong Java system properties, không chứng minh runtime đã sử dụng nó.
- Bản build khác nhau có thể có hành vi hoặc output khác nhau.
- Không phụ thuộc vào class nội bộ như jdk.crac.impl.CheckpointOpenFileException trong code ứng dụng.
- Dùng stack trace của exception để chẩn đoán, không dùng internal implementation class làm API ổn định.

Kiểm tra java.vendor, java.version, java.vm.name và java.home để ghi nhận runtime. Sau đó đối chiếu với tài liệu CRaC của nhà cung cấp.

## 6. Vì sao cần bật từ đầu thay vì bật ngay trước checkpoint?

Stack trace được thu thập khi Java FileDescriptor được tạo. Thời điểm tạo thường nằm trong constructor hoặc native call được gọi từ constructor. Ví dụ:

1. Ứng dụng tạo FileReader.
2. FileReader tạo FileInputStream hoặc đối tượng liên quan.
3. FileDescriptor được khởi tạo và gắn với FD của hệ điều hành.
4. Runtime ghi nhận stack trace nếu chế độ thu thập đã bật.
5. Sau đó ứng dụng quên đóng reader.
6. Khi checkpoint, CRaC phát hiện FD còn mở và có thể đính kèm stack trace đã ghi nhận.

Nếu chỉ bật property ngay trước bước 6, các FD được tạo ở bước 1-3 đã tồn tại mà không có stack trace nguồn. Đó là lý do cần bật từ lúc JVM khởi động trong lần chạy dùng để tái hiện lỗi.

Property có thể làm tăng chi phí tạo FileDescriptor vì runtime cần lưu thêm thông tin stack. Chỉ nên bật khi điều tra hoặc trong môi trường thử nghiệm có chủ đích. Sau khi xác định được nguồn lỗi và sửa lifecycle, hãy chạy lại với cấu hình production thông thường.

## 7. Đọc stack trace để tìm đoạn mã tạo FD

Khi checkpoint thất bại, hãy tìm phần suppressed exception có nội dung FileDescriptor left open. Sau đó đọc phần Caused by nằm bên dưới exception đó.

Một stack trace có thể gồm các lớp JDK trước khi đến code ứng dụng:

~~~text
Caused by: java.lang.Exception:
    This file descriptor was created by main at epoch:...
    at java.base/java.io.FileDescriptor$Resource.<init>(...)
    at java.base/java.io.FileDescriptor.<init>(...)
    at java.base/java.io.FileInputStream.<init>(...)
    at java.base/java.io.FileReader.<init>(...)
    at com.example.config.ConfigLoader.load(ConfigLoader.java:42)
    at com.example.Application.start(Application.java:27)
~~~

Cách đọc:

1. Các frame thuộc java.base thường là implementation của JDK đang tạo FD.
2. Tìm frame đầu tiên thuộc package của ứng dụng hoặc thư viện bên thứ ba.
3. Mở đúng source line nếu có source code hoặc debug symbols.
4. Xác định đối tượng stream/channel nào được tạo tại vị trí đó.
5. Theo dõi nơi đối tượng được đóng và kiểm tra mọi nhánh exception.
6. Nếu đối tượng được giữ lâu dài, xác định owner lifecycle và cách đóng trước checkpoint.

Trong ví dụ trên, ConfigLoader.load() tại dòng 42 là điểm bắt đầu điều tra. Không nhất thiết dòng đó là nơi FD bị bỏ quên; nó là nơi tạo descriptor. Cần kiểm tra toàn bộ vòng đời của stream được tạo ở đó.

Nếu stack chỉ có frame JDK, có thể descriptor được tạo trong quá trình khởi tạo runtime hoặc một thư viện. Hãy kết hợp thread name, timestamp, path và các log khởi tạo để khoanh vùng.

## 8. Ví dụ lỗi: mở file nhưng không đóng

Đoạn code sau tạo một FD nhưng không đảm bảo đóng nó:

~~~java
public final class ConfigLoader {
    public Properties load(Path path) throws IOException {
        FileInputStream input =
                new FileInputStream(path.toFile());

        Properties properties = new Properties();
        properties.load(input);
        return properties;
    }
}
~~~

Nếu load() thành công, input vẫn không được đóng. Nếu load() ném IOException, FD cũng có thể bị bỏ lại. Khi checkpoint diễn ra sau đó, CRaC có thể phát hiện FD còn mở.

Khi bật jdk.crac.collect-fd-stacktraces, stack trace có thể chỉ đến constructor FileInputStream bên trong ConfigLoader.load(). Sau khi thấy vị trí này, sửa code để đóng stream ở mọi nhánh.

## 9. Sửa bằng try-with-resources

Với resource có thời gian sống gắn với một thao tác, try-with-resources là cách đơn giản nhất:

~~~java
public final class ConfigLoader {
    public Properties load(Path path) throws IOException {
        Properties properties = new Properties();

        try (InputStream input = Files.newInputStream(path)) {
            properties.load(input);
        }

        return properties;
    }
}
~~~

Khi rời khỏi khối try, Java gọi close() ngay cả khi có exception. Nhờ đó, FD không còn bị giữ sau khi thao tác đọc kết thúc.

Áp dụng nguyên tắc tương tự cho:

- FileInputStream và FileOutputStream.
- FileReader và FileWriter.
- RandomAccessFile.
- InputStream và OutputStream từ thư viện.
- JDBC Connection, Statement và ResultSet theo ownership/transaction.
- Socket và channel do ứng dụng tạo.
- ZipFile, JarFile và các resource có close().

Không đóng một resource mà code hiện tại không sở hữu. Nếu một method nhận InputStream từ caller, hợp đồng API cần nói rõ ai chịu trách nhiệm đóng stream.

## 10. FD được giữ lâu dài cần lifecycle riêng

Không phải mọi FD đều nên đóng ngay sau một thao tác. Một web server, message consumer, file watcher hoặc client có thể cần giữ socket/channel trong suốt thời gian hoạt động. Với loại resource này, try-with-resources không phù hợp nếu resource cần tồn tại lâu dài.

Cần có owner rõ ràng và lifecycle trước/sau checkpoint:

- Dừng nhận công việc mới.
- Drain request hoặc message đang xử lý.
- Đóng socket/channel/selector theo API của thư viện.
- Xác nhận FD đã được giải phóng.
- Sau restore, tạo lại resource hoặc reconnect.
- Chỉ mở ingress/worker khi resource mới sẵn sàng.

Ví dụ Resource minh họa:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class FileWatcherCracResource implements Resource {
    private final FileWatcherLifecycle watcher;

    public FileWatcherCracResource(FileWatcherLifecycle watcher) {
        this.watcher = watcher;
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context)
            throws Exception {
        watcher.stopWatching();
        watcher.awaitCallbacksToFinish();
        watcher.closeWatchService();
    }

    @Override
    public void afterRestore(Context<? extends Resource> context)
            throws Exception {
        watcher.recreateWatchService();
        watcher.startWatching();
    }

    public interface FileWatcherLifecycle {
        void stopWatching() throws Exception;
        void awaitCallbacksToFinish() throws Exception;
        void closeWatchService() throws Exception;
        void recreateWatchService() throws Exception;
        void startWatching() throws Exception;
    }
}
~~~

FileWatcherLifecycle là interface minh họa do ứng dụng định nghĩa, không phải API CRaC hoặc JDK. Với thư viện thực tế, hãy dùng API lifecycle được hỗ trợ và kiểm tra xem thư viện đã có CRaC integration hay chưa. Không đăng ký thêm Resource để đóng một FD mà một integration khác đã quản lý.

## 11. Một FD có thể được chuyển giao giữa các đối tượng

Stack trace của property chỉ ra nơi FileDescriptor được tạo. Nó không phải bằng chứng rằng đối tượng tạo ra FD vẫn là owner ở thời điểm checkpoint.

Ví dụ:

1. Một factory tạo FileInputStream.
2. Factory chuyển stream cho một component khác.
3. Component nhận stream nhưng quên đóng.
4. Factory đã kết thúc và không còn giữ reference.
5. Checkpoint phát hiện FD vẫn mở.

Stack trace vẫn trỏ đến factory, nhưng lỗi lifecycle nằm ở component nhận stream. Vì vậy, sau khi tìm thấy điểm tạo FD, hãy theo dõi luồng ownership, không chỉ sửa ngay dòng constructor.

Thiết kế API nên làm rõ:

- Ai tạo resource?
- Ai sở hữu resource sau khi trả về?
- Ai phải gọi close()?
- Resource có được chia sẻ giữa nhiều component không?
- Có thể đóng trong khi một thread khác đang dùng không?
- Ai điều phối việc đóng trước checkpoint và mở lại sau restore?

Các abstraction như AutoCloseable, try-with-resources và một lifecycle manager rõ ràng giúp giảm tình trạng ownership không xác định.

## 12. Khi property không cung cấp stack trace

Nếu checkpoint exception cho biết FD còn mở nhưng không có phần Caused by chỉ vị trí tạo, có một số khả năng:

- Property chưa được bật khi FD được tạo.
- JDK build không hỗ trợ property.
- FD được tạo trước khi runtime có thể thu thập stack trace.
- FD được mở từ native code mà không đi qua Java FileDescriptor.
- Thư viện hoặc native component tạo FD theo một đường đi không có Java creation stack tương ứng.

Đừng kết luận ngay rằng runtime không phát hiện FD. Exception vẫn có thể cho biết descriptor number, type và path dù không có stack trace nguồn.

Kiểm tra lần lượt:

1. Xác nhận property nằm trong JVM command line lúc process khởi động.
2. Xác nhận đúng JDK vendor, version và build.
3. Restart ứng dụng với property bật từ đầu.
4. Tái hiện cùng workload tạo FD.
5. Yêu cầu checkpoint và đọc toàn bộ suppressed exceptions.
6. Nếu vẫn không có stack trace, xác định liệu FD đến từ native code.

Không nên dùng System.setProperty() sau khi ứng dụng đã chạy để thay thế tùy chọn JVM startup.

## 13. Phân biệt FD mở từ Java và FD mở từ native code

Tài liệu CRaC phân biệt trường hợp FD được tạo thông qua Java FileDescriptor với trường hợp native code mở FD trực tiếp.

### FD qua Java FileDescriptor

Một exception thường có dạng:

~~~text
Suppressed: jdk.crac.impl.CheckpointOpenFileException:
    FileDescriptor 4 left open: /etc/passwd (regular)
Caused by: java.lang.Exception:
    This file descriptor was created by main at epoch:...
    at java.base/java.io.FileDescriptor...
    at java.base/java.io.FileInputStream...
    at ... application code ...
~~~

Trong trường hợp này, jdk.crac.collect-fd-stacktraces có thể chỉ ra Java call path đã tạo descriptor.

### FD từ native code

Một exception có thể có dạng:

~~~text
Suppressed: jdk.crac.impl.CheckpointOpenResourceException:
    FD fd=4 type=fifo path=pipe:[8953321]
~~~

Runtime vẫn phát hiện FD, nhưng không có Java FileDescriptor creation stack. Cần điều tra syscall tạo descriptor trong native code.

Các syscall thường liên quan gồm open/openat, socket/socketpair, pipe/pipe2, dup/dup2, accept/accept4 và các API tương tự. Không phải mọi FD đều bắt nguồn từ file open; pipe hoặc socket cũng là FD.

## 14. Dùng strace khi nguồn FD nằm trong native code

Trên Linux, strace có thể ghi lại syscall của process và các thread. Tùy chọn -f theo dõi fork/thread, còn -o ghi kết quả ra file:

~~~bash
strace -f -o /tmp/crac-strace.log java -jar app.jar
~~~

Nếu cần tập trung vào syscall tạo FD, có thể lọc syscall và yêu cầu stack trace native nếu strace build hỗ trợ:

~~~bash
strace -f -o /tmp/crac-open-fd.log \
  -e trace=openat,open,dup,dup2,pipe2,socket,socketpair,accept,accept4 \
  -k java -jar app.jar
~~~

Cú pháp syscall filter và khả năng in stack phụ thuộc phiên bản strace. Tài liệu CRaC cũng minh họa cách lọc một syscall cụ thể, ví dụ pipe2:

~~~bash
strace -f -o /tmp/crac-pipe.log -e pipe2 -k java -jar app.jar
~~~

Trong log, tìm FD number tương ứng với lỗi checkpoint. Ví dụ, nếu exception báo fd=4 và log có:

~~~text
1204483 pipe2([4, 5], 0) = 0
~~~

thì syscall pipe2 đã tạo cặp FD 4 và 5. Tiếp tục đọc các dòng sau để xem chúng được cấu hình, duplicate hoặc đóng ở đâu.

Nếu strace in được native stack, nó có thể chỉ đến thư viện như libnio hoặc một thư viện bên thứ ba. Nếu binary bị strip symbol, stack có thể chỉ hiện địa chỉ. Khi đó cần debug symbols hoặc build có symbol để ánh xạ địa chỉ đến function.

Không chạy strace như một giải pháp production thường trực. Tracing syscall có overhead đáng kể và log có thể rất lớn. Dùng trong môi trường kiểm thử hoặc một lần tái hiện có kiểm soát.

## 15. Quy trình điều tra từng bước

Một quy trình thực tế có thể thực hiện như sau.

### Bước 1: Tái hiện lỗi ban đầu

Chạy ứng dụng với đúng workload và cấu hình checkpoint gây lỗi. Lưu toàn bộ stdout, stderr và checkpoint log. Ghi nhận FD number, path hoặc resource type từ suppressed exception.

### Bước 2: Bật thu thập stack trace

Khởi động lại JVM với:

~~~bash
-Djdk.crac.collect-fd-stacktraces=true
~~~

Đảm bảo thuộc tính có mặt từ khi process khởi động, trước khi workload tạo các FD cần điều tra.

### Bước 3: Tái hiện cùng workload

Chạy lại cùng luồng khởi tạo hoặc request. Không thay đổi đồng thời nhiều yếu tố vì sẽ khó so sánh kết quả. Khi checkpoint thất bại, lưu toàn bộ stack trace.

### Bước 4: Tìm suppressed exception

Tìm chuỗi FileDescriptor left open hoặc CheckpointOpenFileException. Đọc phần Caused by để tìm thread, timestamp và call path.

### Bước 5: Xác định owner và lifecycle

Từ frame ứng dụng hoặc thư viện, tìm nơi resource được tạo, chuyển giao, sử dụng và đóng. Kiểm tra các nhánh exception, timeout, cancel và shutdown.

### Bước 6: Sửa lifecycle

Với resource ngắn hạn, dùng try-with-resources hoặc close trong finally. Với resource sống lâu, thêm lifecycle trước checkpoint và phục hồi sau restore bằng API được hỗ trợ.

### Bước 7: Nếu không có Java stack, chuyển sang native tracing

Dùng strace để ghi syscall tạo FD. Lọc theo FD number và syscall phù hợp, rồi ánh xạ về thư viện hoặc native function.

### Bước 8: Chạy lại checkpoint

Sau khi sửa, chạy lại workload và checkpoint. Thành công của checkpoint là bằng chứng quan trọng, nhưng vẫn cần kiểm tra restore và chức năng ứng dụng sau restore.

## 16. Ví dụ bắt và in CheckpointException

Nếu ứng dụng gọi checkpoint trực tiếp, có thể ghi toàn bộ exception để không làm mất suppressed exceptions:

~~~java
import org.crac.Core;
import org.crac.CheckpointException;

public final class CheckpointRunner {
    public static void checkpoint() throws CheckpointException {
        try {
            Core.checkpointRestore();
        } catch (CheckpointException exception) {
            exception.printStackTrace(System.err);

            for (Throwable suppressed : exception.getSuppressed()) {
                System.err.println("Suppressed problem:");
                suppressed.printStackTrace(System.err);
            }

            throw exception;
        }
    }
}
~~~

Tên package và chữ ký method cần khớp với CRaC API được dự án sử dụng. Ví dụ minh họa việc giữ nguyên exception và in suppressed errors; không nên phụ thuộc vào implementation class nằm trong package nội bộ jdk.crac.impl.

Trong nhiều trường hợp runtime hoặc framework đã in exception ra stderr. Điều quan trọng là log collector phải giữ toàn bộ multiline stack trace, bao gồm các phần Suppressed và Caused by. Nếu hệ thống chỉ giữ dòng đầu tiên, thông tin nguồn gốc FD có thể bị mất.

## 17. Đừng nhầm property này với file descriptor policy

CRaC có thể cung cấp cơ chế policy để xử lý một số file descriptor hoặc file được phép tồn tại theo quy tắc riêng. Những policy đó có mục đích khác với jdk.crac.collect-fd-stacktraces.

- collect-fd-stacktraces: ghi lại stack trace tạo Java FileDescriptor để hỗ trợ tìm nguồn lỗi.
- resource policies: mô tả cách CRaC xử lý một số resource/FD theo policy được hỗ trợ.
- CRaCAllowedOpenFilePrefixes: trong một số bản triển khai, dùng cho prefix file mở từ native code theo phạm vi được tài liệu quy định.

Không dùng policy để che lỗi trước khi biết FD thuộc về thành phần nào. Nếu một file descriptor cần được giữ hoặc được xử lý đặc biệt, hãy hiểu tác động tới checkpoint/restore và xác nhận policy được hỗ trợ trong đúng JDK build.

Đối với FD ứng dụng có thể đóng bình thường, sửa lifecycle thường rõ ràng và an toàn hơn việc thêm ngoại lệ vào policy. Property thu thập stack trace giúp tìm nguồn; nó không phải cách cho phép FD còn mở.

## 18. Những giới hạn và lưu ý khi sử dụng

Khi bật thu thập stack trace, cần nhớ:

- **Có chi phí lúc tạo FD:** Runtime cần thu thập và giữ thông tin stack. Có thể làm tăng thời gian mở resource và memory usage.
- **Không phải profiler tổng quát:** Nó không ghi lại mọi thao tác đọc/ghi, cũng không đo thời gian FD được sử dụng.
- **Không chỉ ra nơi quên close một cách trực tiếp:** Nó chỉ ra nơi tạo descriptor; cần theo ownership để tìm nơi lifecycle bị thiếu.
- **Không bao phủ native FD:** FD mở trực tiếp từ native code cần công cụ như strace hoặc native debugger.
- **Phụ thuộc bản CRaC:** Property không phải API chuẩn Java SE; kiểm tra đúng vendor/build.
- **Cần bật trước khi tạo FD:** Bật sau khi ứng dụng đã chạy không tái tạo được stack lịch sử.
- **Output có thể chứa thông tin nội bộ:** Path, package name và stack trace có thể tiết lộ cấu trúc ứng dụng; bảo vệ log theo chính sách.

Chỉ bật trong lần chạy điều tra hoặc môi trường kiểm thử có chủ đích, sau đó bỏ property khi không còn cần thiết.

## 19. Những lỗi thường gặp

**Bật property sau khi FD đã được mở.** Runtime không có stack trace lịch sử để đính kèm. Khởi động lại JVM với property ngay từ đầu.

**Chỉ đọc exception ngoài cùng.** Các vấn đề FD thường nằm trong suppressed exceptions. In và lưu toàn bộ stack trace.

**Cho rằng property tự đóng FD.** Property chỉ thu thập thông tin nguồn. Ứng dụng vẫn phải đóng hoặc quản lý resource đúng lifecycle.

**Chỉ tìm số FD mà không kiểm tra path và call stack.** Số FD có thể được tái sử dụng sau khi đóng. Đọc đầy đủ descriptor type, path, thread và creation stack.

**Sửa dòng tạo resource mà không kiểm tra ownership.** Resource có thể được chuyển cho component khác. Xác định ai chịu trách nhiệm close trước khi thay đổi code.

**Dùng property để chẩn đoán FD native.** Native code có thể không tạo Java FileDescriptor. Dùng strace hoặc công cụ native tracing.

**Nuốt CheckpointException.** Log chỉ còn thông báo chung và mất suppressed details. Giữ nguyên exception hoặc in đầy đủ stack trace.

**Thêm FD vào allowlist quá sớm.** Có thể che lỗi lifecycle và làm checkpoint phụ thuộc vào tài nguyên ngoài. Chỉ dùng policy khi đã hiểu và xác nhận hành vi restore.

**Giữ property trong production mà không đánh giá overhead.** Thu thập stack ở mọi lần tạo FD có thể làm tăng chi phí. Tắt sau khi điều tra.

## 20. Checklist chẩn đoán FD với CRaC

- [ ] Đã ghi nhận JDK vendor, version, build và CRaC engine chưa?
- [ ] CheckpointException và toàn bộ suppressed exceptions đã được lưu chưa?
- [ ] Đã xác định FD number, path và loại resource chưa?
- [ ] jdk.crac.collect-fd-stacktraces=true có được truyền từ lúc JVM khởi động không?
- [ ] Runtime đang dùng có hỗ trợ property này không?
- [ ] Đã tái hiện cùng workload sau khi bật property chưa?
- [ ] Đã đọc phần Caused by để tìm Java creation stack chưa?
- [ ] Đã xác định owner của stream/channel/socket hoặc resource tương ứng chưa?
- [ ] Đã kiểm tra mọi nhánh exception, cancellation và shutdown có đóng resource không?
- [ ] Resource ngắn hạn đã dùng try-with-resources hoặc finally phù hợp chưa?
- [ ] Resource dài hạn đã có beforeCheckpoint/afterRestore lifecycle chưa?
- [ ] Nếu không có Java stack, đã xác định khả năng FD được mở từ native code chưa?
- [ ] Đã dùng strace hoặc native tracing để tìm syscall tạo FD khi cần chưa?
- [ ] Đã tránh phụ thuộc vào class nội bộ jdk.crac.impl trong code ứng dụng chưa?
- [ ] Đã chạy lại checkpoint và restore sau khi sửa lifecycle chưa?
- [ ] Đã tắt property chẩn đoán sau khi hoàn tất điều tra chưa?

## Kết luận

jdk.crac.collect-fd-stacktraces giúp tìm nguồn gốc của những Java FileDescriptor còn mở khiến checkpoint thất bại. Bằng cách bật property từ lúc JVM khởi động, CRaC có thể ghi lại stack trace khi descriptor được tạo và đưa thông tin thread/call path vào suppressed exception khi phát hiện FD còn mở.

Thông tin này giúp lần từ FD number và path đến constructor hoặc thư viện đã mở tài nguyên. Sau đó cần kiểm tra ownership và sửa lifecycle: đóng resource ngắn hạn bằng try-with-resources, hoặc dừng và phục hồi resource dài hạn qua CRaC lifecycle. Nếu FD được tạo trực tiếp từ native code và không có Java creation stack, dùng strace để tìm syscall như openat, pipe2, dup hoặc socket. Property là công cụ chẩn đoán có phạm vi cụ thể; nó không tự giải quyết FD còn mở và không thay thế kiểm thử checkpoint/restore sau khi sửa lỗi.

## Tài liệu tham khảo

- Azul CRaC, CRaC Command-Line Options and System Properties: https://docs.azul.com/crac/usage/vm-options
- Azul CRaC, Debugging CRaC Failures — File Descriptors in Java Code và File Descriptors in Native Code: https://docs.azul.com/crac/usage/debugging.html
