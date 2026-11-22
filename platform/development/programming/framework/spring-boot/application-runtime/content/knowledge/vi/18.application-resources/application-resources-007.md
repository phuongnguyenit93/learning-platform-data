# Phát hiện rò rỉ luồng, kết nối, tệp và classloader trong Spring Boot

Một ứng dụng Spring Boot có thể vẫn trả HTTP 200 trong thời gian dài dù đang **giữ lại những tài nguyên không còn cần thiết**. Khi số lượng thread, connection đang được mượn, file descriptor hoặc classloader cũ tiếp tục tăng theo tải và không quay về mức ổn định sau khi công việc kết thúc, hệ thống có thể gặp timeout, `OutOfMemoryError`, hết file descriptor, cạn connection pool hoặc dừng được rất chậm.

Điểm khó là **tài nguyên tăng không đồng nghĩa chắc chắn có leak**. Thread pool thường giữ worker sau khi tác vụ xong; HikariCP giữ kết nối **idle** để tái sử dụng; JVM có thể giữ class metadata/cache; hệ điều hành cấp nhiều file descriptor cho socket và thư viện. Muốn kết luận chính xác, phải hiểu **ai sở hữu tài nguyên, tài nguyên cần tồn tại bao lâu, khi nào phải được trả lại và nó có thực sự được giải phóng không**.

Bài học tập trung vào bốn nhóm trong Spring Boot Application Runtime:

1. **Thread leak:** luồng hoặc tác vụ nền không được dừng, executor hoặc scheduler không được shutdown.
2. **Connection leak:** JDBC/HTTP/message connection bị giữ quá lâu hoặc không được trả về pool.
3. **File/descriptor leak:** stream, channel, socket hoặc file handle không được đóng.
4. **Classloader leak:** classloader đáng ra đã hết vòng đời nhưng còn bị tham chiếu; thường thấy khi restart/redeploy, plugin hoặc module được nạp động.

Các ví dụ chính dùng **Java 17+ và Spring Boot 3.3.x**. Phần công cụ chẩn đoán sử dụng lệnh JDK HotSpot thông dụng; khả năng hỗ trợ và chi phí chẩn đoán tùy JVM/OS.

## 1. Phân biệt tài nguyên đang được dùng, được cache và bị rò rỉ

Trong thực tế có ba trường hợp khác nhau:

| Quan sát | Có nhất thiết là leak? | Vì sao? |
|---|---|---|
| Một pool giữ 10 thread dù hiện không có job | Không | Worker có thể được giữ để tránh chi phí tạo lại. |
| HikariCP có 8 kết nối idle | Không | Idle connection được trả **vào pool**, chứ không nhất thiết đóng socket vật lý ngay. |
| Một servlet request giữ connection trong lúc query đang chạy | Không | Connection có chủ sở hữu hợp lệ trong thời gian xử lý. |
| Sau hàng trăm request, active connections liên tục tăng và không giảm | **Đáng nghi** | Có thể có checkout không được trả hoặc query bị treo. |
| Số file descriptor tăng, không trở về baseline sau khi batch xong | **Đáng nghi** | Có thể stream/socket/channel không đóng. |
| Metaspace tăng trong startup rồi ổn định | Không | Classloading và JIT/caching có thể tạo tăng trưởng hợp lệ. |
| Sau nhiều lần reload, classloader cũ vẫn bị giữ cùng toàn bộ class của nó | **Đáng nghi** | Có thể thread, static reference, listener hoặc ThreadLocal giữ classloader cũ. |

**Định nghĩa thực dụng:** rò rỉ tài nguyên xảy ra khi thứ đáng lẽ phải được giải phóng sau một vòng đời lại vẫn còn **bị giữ hoặc không được đóng**, khiến việc dùng tài nguyên có xu hướng tích lũy qua những vòng đời tương tự.

Với Java heap, leak thường là **object vẫn reachable từ GC roots dù nghiệp vụ không còn cần**, nên garbage collector không thể thu hồi. Với connection, file descriptor và native handle, chỉ dựa vào heap histogram **không đủ**, vì chúng còn có trạng thái ở OS, pool và hệ thống bên ngoài.

## 2. Chiến lược chẩn đoán: xem xu hướng trước khi xem stack trace

Một thời điểm đo có thể đánh lừa. Nên tiến hành có đối chứng:

~~~text
Baseline sau startup
       |
       v
Chạy tải nhỏ, xác định và lặp lại
       |
       v
Đợi tác vụ kết thúc, pool ổn định, hệ thống hết backlog
       |
       v
Đo lại cùng một bộ tín hiệu
       |
       +-- Trở về mức ổn định: có thể là sử dụng bình thường
       |
       +-- Tăng tích lũy mỗi vòng: cần điều tra ownership
       |
       v
Lấy bằng chứng chi tiết: dump / stack / allocation / handle
       |
       v
Xác định code tạo tài nguyên và code phải đóng nó
       |
       v
Sửa và chạy lại thí nghiệm đối chứng
~~~

Những thứ cần ghi cho từng phép đo:

- Thời gian uptime, phiên bản code, Java/Boot, cấu hình JVM, số replica.
- Lưu lượng, concurrency, số job đang xử lý, timeout/retry.
- Số thread live và thread name; queue length; active tasks.
- Pool connections active/idle/pending/max, thời gian checkout.
- Số file descriptors/handles và loại chúng trỏ đến.
- Loaded classes, Metaspace và số classloader còn sống sau những vòng reload/redeploy.
- GC/heap pressure, native memory, lỗi `too many open files` hoặc connection timeout.

Quan sát phải **so sánh với khối lượng công việc**. Một executor có 20 thread và 20 job hoạt động không giống một executor có 20 thread do request nào cũng tạo pool mới rồi không đóng.

## 3. Tín hiệu sẵn có của Spring Boot Actuator

Thêm `spring-boot-starter-actuator` để dùng những metrics theo Micrometer mà Spring Boot tự cấu hình khi điều kiện phù hợp. Không phải metric nào cũng có trên mọi OS hoặc mọi loại bean.

Những tên metric thường hữu ích:

| Metric hoặc nhóm | Điều cần theo dõi | Lưu ý |
|---|---|---|
| `jvm.threads.live` | Số thread đang sống | Tăng theo tải/khởi tạo pool có thể hợp lệ. |
| `jvm.threads.states` | Phân bố trạng thái thread | WAITING/BLOCKED không tự kết luận leak. |
| `jvm.memory.used` | Heap/non-heap, bao gồm Metaspace theo tags | Memory tăng cần xem GC và điểm ổn định. |
| `jvm.classes.loaded` | Số class đang được nạp | Không trực tiếp cho biết classloader cũ có bị giữ hay không. |
| `process.files.open` | Số file descriptors đang mở, nếu OS/JVM hỗ trợ | Có thể bao gồm socket/pipe, không chỉ file dữ liệu. |
| `jdbc.connections.active` | Connection đang được mượn/active | Tùy DataSource metadata và pool. |
| `jdbc.connections.idle` | Connection idle sẵn sàng tái sử dụng | Idle > 0 không tự là leak. |
| `hikaricp.connections.active` | Hikari checked-out connections | Cần đối chiếu tải, thời gian giữ và pool max. |
| `hikaricp.connections.pending` | Threads đang chờ lấy connection | Tăng kéo dài có thể báo bão hòa hoặc bị giữ connection. |
| `executor.active` / `executor.queued` | Tác vụ hoạt động/hàng đợi của executor được instrument | Không phải executor nào cũng tự được instrument. |

Để xem danh sách metric **thực sự đang có**:

~~~properties
management.endpoints.web.exposure.include=health,metrics
~~~

Sau đó truy cập trong môi trường thử nghiệm:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/jvm.classes.loaded
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.pending
~~~

**Quan trọng:** endpoint metrics chỉ trả về những meter **đã được đăng ký**. Nếu một tên chưa hiện diện, không vội kết luận tính năng hỏng hoặc tài nguyên bằng 0. Hãy kiểm tra classpath, thời điểm khởi tạo pool, cấu hình Micrometer, OS, custom bean và tags. Ví dụ Hikari pool có thể chưa được khởi tạo ở thời điểm đo đầu tiên.

**Bảo mật:** không phơi các Actuator endpoints nhạy cảm trực tiếp ra Internet. Endpoint `heapdump` và `threaddump` có thể làm lộ dữ liệu, tên hệ thống, call stacks hoặc thông tin xác thực; chỉ mở theo kiểm soát truy cập cần thiết. Không bật `management.endpoints.web.exposure.include=*` ở production chỉ vì muốn điều tra một lần.

## 4. Rò rỉ thread: biểu hiện, nguồn gốc và cách tìm

### 4.1 Các nguyên nhân thường gặp

- Mỗi request tạo `new Thread(...)` nhưng không có cơ chế dừng hoặc `join()`.
- Mỗi lần gọi service tạo `Executors.newFixedThreadPool(...)` rồi không `shutdown()`.
- `ScheduledExecutorService` hoặc timer được tạo lại qua nhiều lần refresh/context restart.
- Consumer hoặc polling loop bỏ qua interrupt flag, vẫn chạy sau khi shutdown.
- Task blocking vô hạn trên socket/lock/queue nên không kết thúc.
- Thư viện tạo background threads nhưng lifecycle của bean không đóng thư viện.
- Một thread nền giữ `contextClassLoader` hoặc `ThreadLocal` tham chiếu tới classloader của deployment cũ.

Một **thread pool có kích thước ổn định** không nhất thiết là leak. Dấu hiệu mạnh hơn là **số thread thuộc cùng nhóm tăng thêm sau mỗi vòng thao tác** hoặc thread sống sót sau khi component/context sở hữu nó đã bị đóng.

### 4.2 Thread dump

Với HotSpot JDK có quyền attach phù hợp:

~~~bash
jcmd -l
jcmd <PID> Thread.print -l
~~~

`<PID>` là placeholder cho process ID thật. `Thread.print -l` in danh sách thread, stack trace và thông tin lock; có thể có chi phí và output lớn. Không tự động chạy vòng lặp dump dày đặc lên production.

Khi đọc dump, cần xem:

1. Tên thread có prefix của executor/scheduler nào?
2. Stack có lặp tại `Thread.sleep`, `SocketInputStream`, `LockSupport.park`, `BlockingQueue.take` hay code ứng dụng nào?
3. Thread thuộc pool **nào** và pool đó có owner/destroy callback hay không?
4. Có bao nhiêu thread cùng kiểu sau vòng tải thứ nhất, thứ hai, thứ ba?
5. Khi đóng ApplicationContext, nhóm thread đó có biến mất không?

**Không đánh đồng `WAITING` với “rò rỉ”.** Worker của thread pool có thể chờ công việc một cách hoàn toàn hợp lệ. Một deadlock hay quên shutdown thường cần thêm thông tin vòng đời và bằng chứng stack qua nhiều thời điểm.

Các công cụ hỗ trợ: Java Flight Recorder (JFR), Java Mission Control (JMC), VisualVM, thread dump trong IDE hoặc `/actuator/threaddump` được bảo vệ nếu bạn cố ý cho phép endpoint này.

### 4.3 Sai và đúng với executor

Một anti-pattern:

~~~java
public void processRequest() {
    ExecutorService pool = Executors.newFixedThreadPool(4);
    pool.submit(() -> doWork());
    // Không shutdown, pool và thread có thể tồn tại lâu ngoài request.
}
~~~

Đoạn trên là **mã minh họa lỗi**, các hàm/import chưa đầy đủ. Nếu code chạy mỗi request, nó tạo nhiều executor có vòng đời vượt request.

Cách sửa thường gặp: **một executor có owner và lifecycle rõ**:

~~~java
@Component
public class BackgroundWorker {

    private final ExecutorService pool =
            Executors.newFixedThreadPool(4);

    public Future<?> submit(Runnable task) {
        return pool.submit(task);
    }

    @PreDestroy
    public void shutdown() {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        } catch (InterruptedException ex) {
            pool.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Đây là class minh họa, cần import `Component`, `jakarta.annotation.PreDestroy` và những lớp `java.util.concurrent` tương ứng. Trong ứng dụng thực tế, thường ưu tiên `ThreadPoolTaskExecutor` được Spring quản lý, có cấu hình queue, pool, shutdown và instrumentation rõ ràng hơn.

Phải phân biệt **dừng nhận task**, **hoàn tất task đang chạy** và **thu hồi executor**. Một lệnh `shutdown()` không tự biến tất cả task đang chờ thành kết quả đã hoàn tất; deadline và chính sách hủy cần được thiết kế.

## 5. Rò rỉ JDBC connection: nhìn theo pool, không chỉ theo socket

### 5.1 Connection từ pool hoạt động ra sao?

Trong ứng dụng dùng `HikariDataSource`:

~~~text
HTTP request
     |
     v
dataSource.getConnection()  -> mượn logical connection từ Hikari pool
     |
     v
Thực hiện SQL
     |
     v
connection.close()          -> trả logical connection về pool
     |
     v
Hikari giữ physical connection idle để tái sử dụng nếu phù hợp
~~~

Với **pooled connection**, gọi `Connection.close()` thường có ý nghĩa **trả connection về pool**, không nhất thiết đóng TCP connection vật lý ngay. Vì vậy quan sát `idle connections > 0` là điều bình thường. Ngược lại, **active gần maximumPoolSize và pending tăng dai dẳng sau khi tải đã ngừng** là dấu hiệu cần điều tra.

Một số nguyên nhân:

- Code gọi `getConnection()` nhưng bỏ qua `close()` khi có exception.
- Truy vấn hoặc transaction giữ connection quá lâu.
- Streaming JDBC `ResultSet` không được đọc/đóng theo hợp đồng.
- Async task giữ connection trong khi chờ tác vụ khác không liên quan.
- Leak trong thư viện hoặc custom DataSource wrapper.
- Số lượng request tăng vượt capacity, gây pool exhaustion **dù không có leak**.

### 5.2 Hikari leakDetectionThreshold không chứng minh có leak

HikariCP có property:

~~~properties
spring.datasource.hikari.leak-detection-threshold=2000
~~~

Đơn vị là **millisecond**. Nếu connection được mượn quá ngưỡng mà chưa trả, Hikari log cảnh báo **possible/apparent connection leak**. Ngưỡng tối thiểu có hiệu lực thông thường là 2000 ms; giá trị `0` tắt cảnh báo.

**Cảnh báo này là manh mối, không phải phán quyết.** Một transaction hợp lệ kéo dài 5 giây cũng có thể kích hoạt cảnh báo tại giây thứ 2, rồi connection được trả về khi transaction kết thúc. Nếu Hikari ghi thêm thông điệp “previously reported leaked connection ... was returned to the pool”, đó chính là một ví dụ connection **đã được trả**, không phải leak vĩnh viễn.

Để điều tra:

1. Bật threshold phù hợp ở môi trường cần kiểm tra, có kiểm soát noise.
2. Xem stack trace lúc checkout hoặc khi cảnh báo.
3. Quan sát `hikaricp.connections.active`, `idle`, `pending` và pool max theo thời gian.
4. Đo độ dài transaction/query và thời gian chờ network.
5. Xác minh code trả connection ở **mọi nhánh**, kể cả lỗi, timeout và cancellation.
6. Chạy tải nhỏ lặp lại và kiểm tra active có trở về baseline không.

Đừng chọn threshold quá thấp so với thời gian xử lý bình thường: bạn sẽ tạo nhiều false positives, che lấp sự cố thật.

### 5.3 try-with-resources

Mã JDBC tốt có thể theo mẫu:

~~~java
String sql = "select count(*) from orders";

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql);
     ResultSet results = statement.executeQuery()) {

    if (results.next()) {
        long total = results.getLong(1);
        // Dùng total...
    }
}
~~~

Đây là đoạn minh họa trong class có `DataSource dataSource` và bảng `orders` tương ứng, không phải chương trình độc lập. `try-with-resources` đóng `ResultSet`, `PreparedStatement` và `Connection` theo thứ tự ngược khi khối kết thúc, kể cả trường hợp có exception.

Nếu code dùng Spring `JdbcTemplate`/Spring Data, nên để framework quản lý connection và transaction theo API, tránh tự gọi `getConnection()` ngoài những nơi thật sự cần thao tác JDBC cấp thấp. Với `@Transactional`, connection có thể được giữ tới khi transaction kết thúc; **transaction kéo dài** vẫn gây pool starvation dù framework không bị “quên close”.

## 6. Rò rỉ file descriptor, file handle và socket

### 6.1 Triệu chứng

- Exception `Too many open files` trên Linux/Unix.
- Không mở thêm tệp hoặc socket được dù heap chưa đầy.
- Ứng dụng không xóa/rename tệp được trong một số môi trường, đặc biệt Windows.
- Số file handle tăng sau mỗi batch import/export.
- Nhiều socket ở trạng thái không mong muốn hoặc I/O timeout.

Một descriptor có thể đại diện cho **file, socket, pipe, eventfd hoặc tài nguyên OS khác**, nên `process.files.open` tăng chưa đủ để kết luận file CSV bị quên đóng.

### 6.2 Công cụ quan sát

Trên Linux:

~~~bash
ls -l /proc/<PID>/fd
lsof -p <PID>
~~~

Thay `<PID>` bằng PID thật. `/proc/<PID>/fd` liệt kê các descriptor; `lsof -p` giúp xem chúng trỏ tới tệp/socket nào, nếu có lệnh và quyền phù hợp. Đếm descriptor **nhiều lần dưới cùng một tải** để tránh nhiễu do log rotation, socket mới, JAR files và các tài nguyên JVM.

Trên Windows, có thể dùng **Process Explorer/Handle của Microsoft Sysinternals** hoặc các công cụ đo handle được cho phép để xem handle count và đối tượng đang được giữ. Cách mở/chia sẻ file và hành vi lock khác Linux; không dùng số FD của Linux làm một ngưỡng chung cho mọi nền tảng.

Trong Actuator, metric `process.files.open`/`process.files.max` có thể có tùy OS/JVM. Nếu metric không xuất hiện trên Windows hoặc trong container tối giản, đó có thể là hạn chế cung cấp tín hiệu, không phải số lượng handle bằng 0.

### 6.3 Đóng stream/channel đúng cách

Mẫu nên dùng:

~~~java
Path input = Path.of("data", "orders.csv");

try (BufferedReader reader =
             Files.newBufferedReader(input, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        // Xử lý từng dòng.
    }
}
~~~

Đây là đoạn Java minh họa, cần import `Path`, `Files`, `BufferedReader`, `StandardCharsets` và cần có tệp `data/orders.csv`. Không bắt buộc tệp phải tồn tại khi đọc bài.

Các đối tượng có thể cần đóng: `InputStream`, `OutputStream`, `Reader`, `Writer`, `FileChannel`, `ZipFile`, `JarFile`, socket/client, result cursor. Với `Files.lines(path)`, `Stream<String>` trả về cũng cần được đóng sau khi duyệt.

Anti-pattern:

~~~java
Stream<String> lines = Files.lines(path);
long total = lines.count();
// Không gọi close() lên Stream.
~~~

Mẫu đúng:

~~~java
try (Stream<String> lines = Files.lines(path)) {
    long total = lines.count();
}
~~~

Hai đoạn là minh họa, cần `Path path`, `Stream` và các import thích hợp. Đừng dựa vào finalizer hoặc GC để đóng tài nguyên OS đúng lúc.

## 7. Classloader leak: tại sao khác với heap leak thông thường?

### 7.1 Classloader sở hữu những gì?

Một `ClassLoader` được dùng để nạp classes và liên quan tới class metadata, object instances, static fields, reflection caches, thread context classloader (TCCL) và các tài nguyên của module/deployment. Khi một classloader có vòng đời **ngắn** (plugin, DevTools restart, application redeploy) đáng ra được giải phóng, những reference còn sót có thể giữ nó cùng nhiều class/object liên quan.

Ví dụ:

~~~text
Một thread do ứng dụng tạo (vẫn còn sống)
           |
           v
Thread.contextClassLoader
           |
           v
OldRestartClassLoader
           |
           +-- classes của deployment cũ
           +-- static fields / reflection metadata
           +-- các object còn reachable
~~~

Một object reference có thể đi qua nhiều đường: thread, `ThreadLocal`, static registry, callback/listener của thư viện ở parent classloader, executor, MBean, driver registration hoặc global cache.

Không phải “mọi static field đều gây classloader leak”. Static fields thuộc về class do **classloader nào** nạp và liệu có reference từ một GC root sống lâu hơn loader cũ hay không. Vấn đề phát sinh khi một thành phần **có vòng đời dài hơn** giữ reference vào classloader/objects **có vòng đời ngắn hơn**.

### 7.2 DevTools và nhiều lần restart

Spring Boot DevTools restart thường dùng **hai classloaders**:

- **Base classloader:** chứa nhiều dependency ít đổi.
- **Restart classloader:** chứa các classes của ứng dụng đang phát triển; bị thay khi restart.

Sau restart, restart classloader cũ **nên có thể được GC** khi không còn reference cần thiết. Nếu một thread/plugin/cache cũ vẫn giữ TCCL hoặc callback của loader đó, loader cũ có thể tiếp tục sống, khiến **Metaspace** và heap tăng qua nhiều lần restart.

Không nên coi một lần Metaspace tăng sau startup là leak. Hãy đo **sau nhiều chu kỳ restart/deploy tương đồng** và kiểm tra loader cũ có còn reachable sau GC thích hợp hay không.

### 7.3 Các lệnh chẩn đoán classloader

Với HotSpot JDK hỗ trợ các lệnh tương ứng:

~~~bash
jcmd <PID> VM.classloader_stats
jcmd <PID> VM.classloaders
jcmd <PID> VM.metaspace
~~~

Những lệnh này cho biết thống kê/hierarchy của loaders hoặc usage của Metaspace; chúng là **bằng chứng tổng hợp**, chưa tự cung cấp toàn bộ đường giữ reference.

Có thể xem thêm qua Actuator:

~~~bash
curl "http://localhost:8080/actuator/metrics/jvm.classes.loaded"
curl "http://localhost:8080/actuator/metrics/jvm.memory.used?tag=id:Metaspace"
~~~

Các chỉ số này giúp phát hiện xu hướng nhưng **không chỉ ra loader cụ thể** đang bị giữ. Để tìm nguyên nhân, phân tích heap dump có kiểm soát trong Eclipse Memory Analyzer (MAT), VisualVM hoặc công cụ hỗ trợ, tìm **GC roots / paths to GC roots** đi tới classloader cũ.

**Cẩn trọng:** heap dump có thể rất lớn, dừng ứng dụng tạm thời tùy cách lấy và chứa secrets/dữ liệu cá nhân trong heap. Chỉ lưu trong khu vực an toàn, đặt retention/xóa theo quy định và không mở endpoint `/actuator/heapdump` công khai.

### 7.4 Sửa TCCL và listener ownership

Một đoạn thay đổi context classloader nên phục hồi đúng giá trị trước đó:

~~~java
ClassLoader before =
        Thread.currentThread().getContextClassLoader();

try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    // Thực hiện công việc dùng plugin.
} finally {
    Thread.currentThread().setContextClassLoader(before);
}
~~~

Đây là đoạn **minh họa**, trong đó `pluginLoader` do hệ thống plugin sở hữu và đã được tạo. Phải luôn restore ở `finally`; không lưu TCCL của loader ngắn hạn mãi trên thread dùng chung.

Nếu tự dùng `URLClassLoader` hoặc thư viện load module, đóng loader khi hợp đồng yêu cầu chỉ là **một bước**. `close()` giải phóng những resource loader quản lý nhưng **không bảo đảm class được unload** nếu thread/static cache/listener vẫn còn reference.

Khi unload một plugin, cần:

1. Dừng executor, scheduler, listener và task của plugin.
2. Đăng ký/huỷ đăng ký callback với owner đúng vòng đời.
3. Dọn `ThreadLocal` và restore TCCL nơi cần thiết.
4. Bỏ entries trong global/static registries sống lâu hơn plugin.
5. Đóng connection pool, files, JarFile/URLClassLoader nếu plugin thực sự sở hữu.
6. Bỏ reference tới plugin object/class/classloader.
7. Quan sát loader cũ có còn tồn tại sau GC và những vòng chạy tiếp theo.

## 8. Ví dụ Spring Boot 3.3 chạy được: giữ tài nguyên có kiểm soát rồi trả lại

Ví dụ này cố ý **giữ JDBC connection và file channel trong vài giây** trong lúc một task dùng executor hoạt động. Nó giúp học cách quan sát ba nhóm tài nguyên **mà không tạo leak vĩnh viễn**. Sau khi request hoàn tất, connection, file channel và file tạm đều được trả/đóng/xóa; executor là một bean do Spring quản lý và được shutdown khi context đóng.

Classloader leak cần thí nghiệm **redeploy/restart** riêng ở mục sau, không nên cố tạo classloader bị giữ vĩnh viễn trong demo web này.

### 8.1 Cấu trúc và dependencies

~~~text
resource-diagnostics/
├── build.gradle
└── src/
    └── main/
        ├── java/com/example/resources/ResourceDiagnosticsApplication.java
        └── resources/application.properties
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'com.h2database:h2'
}

springBoot {
    mainClass = 'com.example.resources.ResourceDiagnosticsApplication'
}
~~~

Chọn **H2 in-memory** để quan sát HikariCP mà không cần database ngoài. Trong production, cần đo cả tín hiệu từ database thực và connection pool trên client.

### 8.2 File cấu hình

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=resource-diagnostics
server.port=8080

spring.datasource.url=jdbc:h2:mem:resource_lab;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.pool-name=lab-pool
spring.datasource.hikari.maximum-pool-size=3
spring.datasource.hikari.minimum-idle=1
spring.datasource.hikari.connection-timeout=3000

# Chỉ bật ngưỡng thấp trong lab; cảnh báo không chứng minh leak thật.
spring.datasource.hikari.leak-detection-threshold=2000

management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=never
~~~

Giải thích:

- Hikari pool tối đa 3 connections để dễ quan sát `active`, `idle`, `pending`.
- `leak-detection-threshold=2000` tạo cảnh báo **possible leak** khi một request giữ connection hơn 2 giây. Vì bài lab cố ý giữ 4 giây, cảnh báo **được kỳ vọng dù code đóng đúng**.
- `connection-timeout=3000` giới hạn thời gian chờ lấy connection, không phải thời gian tối đa transaction có thể giữ connection.
- Chỉ expose health/metrics trong môi trường lab. Endpoint tác động tài nguyên `/lab/hold` phải được loại bỏ hoặc bảo vệ trước khi đưa vào production.

### 8.3 File Java hoàn chỉnh

Tạo `src/main/java/com/example/resources/ResourceDiagnosticsApplication.java`:

~~~java
package com.example.resources;

import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.sql.Connection;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class ResourceDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(ResourceDiagnosticsApplication.class, args);
    }

    @Bean("labExecutor")
    ThreadPoolTaskExecutor labExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("lab-worker-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(5);
        return executor;
    }

    @RestController
    public static class LabController {

        private final DataSource dataSource;
        private final ThreadPoolTaskExecutor executor;

        public LabController(
                DataSource dataSource,
                @Qualifier("labExecutor")
                ThreadPoolTaskExecutor executor) {
            this.dataSource = dataSource;
            this.executor = executor;
        }

        @PostMapping("/lab/hold")
        public String hold(
                @RequestParam(defaultValue = "4000") long millis)
                throws Exception {

            if (millis < 0 || millis > 10000) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "millis must be between 0 and 10000");
            }

            // File tạm có owner rõ và luôn được xóa khi kết thúc.
            Path temp = Files.createTempFile(
                    "spring-resource-lab-", ".txt");

            try {
                // Connection mượn từ Hikari; FileChannel giữ FD.
                try (Connection connection = dataSource.getConnection();
                     FileChannel channel = FileChannel.open(
                             temp, StandardOpenOption.WRITE)) {

                    channel.write(
                            StandardCharsets.UTF_8.encode("lab\n"));

                    // Worker thread do executor bean sở hữu.
                    Future<String> worker = executor.submit(() -> {
                        TimeUnit.MILLISECONDS.sleep(millis);
                        return Thread.currentThread().getName();
                    });

                    try {
                        String name = worker.get(
                                15, TimeUnit.SECONDS);
                        return "completed on " + name;
                    } finally {
                        if (!worker.isDone()) {
                            worker.cancel(true);
                        }
                    }
                }
                // Hai resource của try đã đóng trước finally ngoài.
            } finally {
                Files.deleteIfExists(temp);
            }
        }
    }
}
~~~

**Vì sao mã này không làm rò rỉ?**

- `Connection` được khai báo trong `try-with-resources`; khi hoàn tất dù thành công hay exception, `close()` trả connection về Hikari pool.
- `FileChannel` cũng được đóng tự động, sau đó tệp tạm được xóa trong `finally`.
- `labExecutor` là bean quản lý bởi Spring, không tạo thêm một pool sau mỗi request. Nó có lifecycle/shutdown rõ.
- `Future` được chờ có timeout; nếu chưa hoàn thành thì gửi yêu cầu cancel. Task trong demo chỉ ngủ và đáp ứng interruption; production task phải thiết kế timeout/cancel cho I/O thực.
- `@PostMapping` tránh dùng GET cho thao tác tạo file/giữ tài nguyên trong lab.
- Giới hạn `millis` từ 0 đến 10.000 để tránh request vô hạn từ ví dụ. Dù vậy endpoint lab vẫn không được expose công khai.

**Điều mà mã không hứa:** request có thể nhận HTTP 500 nếu executor/pool bị quá tải hoặc file system gặp lỗi, và không có transaction nghiệp vụ nào được thực hiện với H2. Mục tiêu là quan sát vòng đời tài nguyên, không phải thiết kế endpoint production.

### 8.4 Chạy và đo

Với project có Gradle wrapper và JDK 17+:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper, tạo/cấu hình Gradle tương thích trước. Đây là ứng dụng Spring Boot có dependencies, không thể chạy riêng file Java bằng một lệnh `javac` trần thiếu classpath.

Trong terminal khác, chạy:

~~~bash
curl -X POST "http://localhost:8080/lab/hold?millis=4000"
~~~

Kết quả HTTP body có dạng:

~~~text
completed on lab-worker-1
~~~

**Hậu tố thread name có thể khác** khi có nhiều request; đây là output ví dụ, không phải chuỗi bảo đảm. Chương trình có thể ghi cảnh báo Hikari kiểu “apparent connection leak” sau 2 giây do connection được giữ 4 giây, rồi ghi thông tin connection đã trở về pool.

Trong khi request còn chạy, quan sát:

~~~bash
curl http://localhost:8080/actuator/metrics/hikaricp.connections.active
curl http://localhost:8080/actuator/metrics/hikaricp.connections.pending
curl http://localhost:8080/actuator/metrics/jvm.threads.live
curl http://localhost:8080/actuator/metrics/process.files.open
~~~

Kết quả là JSON meter với số đo và tags nếu metric tồn tại; **không có một stdout cố định** vì phụ thuộc thời điểm lấy mẫu và số request đồng thời.

Thử một vài request liên tiếp rồi dừng. Sau khi công việc đã kết thúc:

- `hikaricp.connections.active` thường quay về gần 0, connection có thể chuyển sang idle.
- Hikari pool có thể giữ physical connection mở đúng thiết kế.
- `lab-worker-*` có thể vẫn tồn tại do thread pool giữ worker để tái sử dụng; **không kết luận leak** chỉ vì thread chưa biến mất ngay.
- File tạm được xóa; số FD có thể dao động do socket/log khác, cần so baseline theo tải.
- Khi dừng ứng dụng một cách có kiểm soát, Spring đóng executor bean và datasource theo lifecycle.

**Thí nghiệm đối chứng quan trọng:** đổi `millis=1000` để không vượt 2000ms trong điều kiện bình thường; không có cảnh báo Hikari về thời gian checkout dài. Giữ `millis=4000` để tạo cảnh báo, nhưng connection vẫn được trả. Bài học: cảnh báo ngưỡng thời gian **không** chứng minh lỗi `close()`.

## 9. Thí nghiệm leak có kiểm soát và cách sửa

Không nên cố ý tạo leak vô hạn trên production. Nếu cần tái hiện lỗi để hiểu, làm trên **máy lab**, giới hạn số vòng và có khả năng dừng process.

### 9.1 Thread

**Đối chứng lỗi:** trong một test cô lập, mỗi vòng tạo một `ScheduledExecutorService` và không đóng. Quan sát tên thread tăng cùng số vòng. Chỉ chạy một số vòng nhỏ rồi kết thúc toàn bộ process lab, không đưa pattern này vào mã thực tế.

**Sửa:** đưa executor vào bean có chủ sở hữu, gọi `shutdown/awaitTermination` ở `@PreDestroy` hoặc dùng Spring-managed `ThreadPoolTaskExecutor`.

**Bằng chứng sau sửa:** số thread thuộc executor ổn định theo pool size và các thread biến mất sau khi context đóng.

### 9.2 Connection

**Đối chứng lỗi:** tạo một path test cố ý không trả `Connection` sau `getConnection()`, với giới hạn tối đa vài requests trong môi trường tách biệt. Chờ tới khi `active=max` và `pending` tăng, rồi dừng test. Không đưa mã này vào endpoint chạy public.

**Sửa:** `try-with-resources` hoặc để Spring data access/transaction framework quản lý kết nối đúng cách.

**Bằng chứng sau sửa:** active giảm sau khi request/transaction kết thúc, không có xu hướng tích lũy qua các vòng tương tự.

### 9.3 File handle

**Đối chứng lỗi:** trong test riêng, mở vài `FileInputStream` và quên đóng, đo số FD. Tránh chạy đến mức hết FD của máy dùng chung.

**Sửa:** đóng stream/channel bằng `try-with-resources`, kể cả khi exception.

**Bằng chứng sau sửa:** số FD trỏ tới tập tệp test trở về baseline; không chỉ nhìn tổng FD của JVM vì tổng còn nhiều nguồn dao động.

### 9.4 Classloader

**Đối chứng lỗi:** trong môi trường DevTools/plugin test, tạo và tháo một module nhiều lần; cố ý giữ reference vào object từ loader cũ trong một registry sống lâu hơn, rồi theo dõi `VM.classloader_stats` hoặc heap dump.

**Sửa:** huỷ đăng ký registry/listener, dừng threads, xóa TCCL/ThreadLocal, đóng loader và bỏ reference về plugin.

**Bằng chứng sau sửa:** loader cũ **không còn reachable** theo đường GC roots sau các vòng unload/GC phù hợp. Chỉ thấy Metaspace giảm không đủ chứng minh mọi đường giữ đã được sửa, và ngược lại Metaspace chưa giảm ngay không tự chứng minh còn leak.

## 10. Quan sát native memory và heap khi triệu chứng không rõ

Một số lỗi không thể suy ra chỉ từ heap usage. JVM dùng nhiều vùng:

~~~text
Java process memory
 +-- Java heap
 +-- Metaspace / class metadata
 +-- Code cache
 +-- Thread stacks
 +-- Direct buffers
 +-- GC/JIT/native allocations
 +-- Memory do native libraries/OS quản lý
~~~

Khi container RSS tăng mà `jvm.memory.used` heap không tăng tương ứng, có thể liên quan **native memory, thread stacks, direct buffers, class metadata hoặc memory mapping**.

JDK HotSpot có Native Memory Tracking (NMT). Nếu khởi động JVM với:

~~~text
-XX:NativeMemoryTracking=summary
~~~

thì có thể chạy:

~~~bash
jcmd <PID> VM.native_memory summary
~~~

NMT cần được bật từ lúc JVM khởi động theo cấu hình phù hợp. Nó có overhead và chủ yếu phân tích **bộ nhớ do JVM theo dõi**, không bảo đảm bao quát mọi allocation của thư viện native bên thứ ba. Dùng cùng với OS-level RSS, thread, FD và pool metrics.

Nếu cần phân tích heap:

~~~bash
jcmd <PID> GC.class_histogram
~~~

Lệnh này có thể tốn tài nguyên và gây pause đáng kể tùy heap; chỉ dùng khi được phép. Nó giúp thấy số lượng classes/objects trong heap, nhưng không tự chỉ ra **đường giữ**. Khi nghi classloader leak, một heap dump và phân tích dominator/GC roots thường giàu thông tin hơn histogram đơn lẻ.

Java Flight Recorder có thể dùng để thu thập bằng chứng theo thời gian:

~~~bash
jcmd <PID> JFR.start name=resource-lab settings=profile duration=60s filename=resource-lab.jfr
~~~

Đây là ví dụ lệnh cho HotSpot/JDK hỗ trợ JFR. Kiểm tra quyền, filesystem, cấu hình recording và overhead trước khi chạy. Tệp recording có thể chứa thông tin nhạy cảm, cần được kiểm soát lưu trữ tương tự heap dump.

## 11. Rò rỉ ở ranh giới Spring ApplicationContext

Spring quản lý vòng đời **những bean đã đăng ký**, nhưng một tài nguyên do bạn tự tạo ngoài container có thể vượt qua cơ chế destroy:

~~~java
class ExternalClientHolder {

    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    // Nếu object này bị tạo bằng new ngoài Spring và không close,
    // Spring không tự biết để shutdown executor.
}
~~~

Đây là ví dụ rút gọn minh họa lỗi ownership, không phải chương trình độc lập.

Một số nguyên tắc:

- Mỗi resource phải có **owner cụ thể**.
- Nếu owner là Spring bean, đăng ký `@PreDestroy`, `DisposableBean` hoặc `@Bean(destroyMethod=...)` khi phù hợp.
- Nếu owner là method, dùng `try-with-resources`.
- Nếu owner là job/stream, đảm bảo close khi complete, error và cancel.
- Nếu owner là ApplicationContext, dừng component con **trước** những shared dependencies mà chúng dùng.
- Nếu resource thuộc một thư viện, dùng API `close()/shutdown()` của thư viện, không chỉ xoá reference Java.
- Khi chạy **nhiều ApplicationContext trong một JVM**, đóng từng context đã tạo; chỉ đóng context cuối không tự đảm bảo toàn bộ tài nguyên context khác được xử lý đúng.

### @PreDestroy và shutdown không đủ nếu task không hợp tác

Ngay cả khi có:

~~~java
@PreDestroy
public void shutdown() {
    executor.shutdownNow();
}
~~~

đoạn này vẫn chỉ phát yêu cầu ngừng. Nếu một task không phản ứng với interruption hoặc đang block ở một API không có timeout, nó có thể tiếp tục sống. Vì vậy cần timeout I/O, cancellation contract, graceful shutdown và xác minh thread thực tế đã kết thúc.

Không dùng `System.exit(...)` như cách xử lý bình thường một component bị leak: nó kết thúc cả JVM, che giấu vấn đề ownership và làm mất khả năng đóng tài nguyên có kiểm soát.

## 12. Quy trình xử lý sự cố thực tế

Giả sử production báo timeout tăng dần sau vài giờ. Một quy trình hiệu quả:

**Bước 1 — Khoanh vùng hiện tượng.** Tỷ lệ lỗi bắt đầu ở thời điểm nào? CPU, heap, GC, thread count, FD hay pool pending biến đổi? Có deploy hoặc cấu hình mới không?

**Bước 2 — Xác định loại tài nguyên.** Nếu `hikaricp.connections.pending` tăng, xem JDBC pool và transaction. Nếu `process.files.open` tăng, xem descriptor. Nếu số thread tên `custom-worker-*` tăng, xem executor owner. Nếu sau mỗi redeploy Metaspace/classloader tăng, tập trung loader retention.

**Bước 3 — Lấy mẫu theo thời gian.** Ít nhất đo trước tải, trong tải, sau khi idle và sau nhiều vòng tải giống nhau. Một ảnh chụp ngay khi tải cao chưa chứng minh leak.

**Bước 4 — Thu bằng chứng cụ thể.** Thread dump/JFR, Hikari checkout stack, lsof/Handle, classloader stats/heap dump. Chỉ dùng những công cụ được phép trên môi trường đó.

**Bước 5 — Tìm owner bị thất lạc.** Tìm nơi gọi `new Thread`, `Executors.new...`, `DataSource.getConnection`, `Files.new...`, `URLClassLoader`, đăng ký listener hoặc ThreadLocal. So với nơi phải đóng/hủy đăng ký.

**Bước 6 — Sửa nguyên nhân và viết regression test.** Mọi nhánh thành công, exception, timeout, cancel và context close cần có chính sách dọn dẹp.

**Bước 7 — Kiểm chứng sau sửa.** Chạy cùng kịch bản, cùng mức tải, đo lại. Chỉ tuyên bố hết leak khi tài nguyên đạt baseline/plateau phù hợp và không còn tăng tích lũy qua nhiều vòng.

**Bước 8 — Đặt cảnh báo phù hợp.** Không đặt alert chỉ dựa vào tổng thread/FD tuyệt đối. Ưu tiên tốc độ tăng, ngưỡng pool pending, tỷ lệ lỗi, timeout, active/max và tác động người dùng.

## 13. Checklist thực hành cho từng tài nguyên

| Loại | Bằng chứng ban đầu | Công cụ sâu hơn | Cách sửa thường gặp |
|---|---|---|---|
| Thread | `jvm.threads.live`, executor active/queue, thread prefix | Thread dump/JFR, lifecycle logs | Shutdown executor/scheduler, cancel task, timeout I/O. |
| JDBC connection | Hikari active/idle/pending/max, timeout | LeakDetectionThreshold + stack, transaction traces | try-with-resources, ngắn transaction, đúng owner. |
| File descriptor | `process.files.open`, “too many open files” | `/proc/PID/fd`, `lsof`, Process Explorer/Handle | Close stream/channel/socket, quản lý client lifecycle. |
| Classloader | Class count, Metaspace, số loader sau reload | `VM.classloader_stats`, heap dump, paths to GC roots | Dừng threads, huỷ registry/listener, dọn TCCL/ThreadLocal và loader references. |

Không dùng một công cụ để chẩn đoán thay cho tất cả. Ví dụ **heap dump có thể giúp tìm object giữ FileInputStream**, nhưng hệ thống OS mới xác nhận file descriptor nào còn mở; **Hikari warning giúp tìm call stack**, nhưng pool metrics và lịch sử checkout mới giúp đánh giá liệu có phải connection không được trả.

## 14. Sai lầm phổ biến

**Sai lầm 1 — “Heap không tăng thì không thể có leak”.** Sai. Thread stacks, native memory, socket/file descriptors và connections có thể cạn trước khi heap tăng nhiều.

**Sai lầm 2 — “Thread ở trạng thái WAITING là bị leak”.** Sai. Worker chờ task có thể bình thường. Cần xét owner, số lượng, vòng đời và việc shutdown.

**Sai lầm 3 — “Hikari idle connections là connection leak”.** Sai. Idle là connection đã về pool và sẵn sàng tái sử dụng theo cấu hình.

**Sai lầm 4 — “Hikari leakDetectionThreshold báo lỗi là chắc chắn quên close”.** Không. Nó cảnh báo checkout lâu; một query/transaction hợp lệ cũng có thể vượt ngưỡng.

**Sai lầm 5 — “Connection.close() luôn đóng TCP socket vật lý”.** Không nhất thiết với pool; nó thường trả connection logic về pool.

**Sai lầm 6 — “GC sẽ tự đóng file hoặc socket kịp lúc”.** Không thể dựa vào đó. Phải đóng một cách tường minh theo hợp đồng.

**Sai lầm 7 — “Metaspace tăng nghĩa là classloader leak”.** Chưa đủ. Classloading/caching có thể hợp lệ; cần chứng minh loader cũ không thể được GC do reference giữ lại.

**Sai lầm 8 — “Chỉ cần URLClassLoader.close() là chắc chắn unload class”.** Không. Reference từ thread/static registry vẫn có thể giữ loader và class metadata.

**Sai lầm 9 — “Bật Spring DevTools restart thì mọi tài nguyên của lần chạy cũ tự biến mất”.** Không chắc, đặc biệt với tài nguyên unmanaged, TCCL và listener/ThreadLocal sống lâu hơn context.

**Sai lầm 10 — “Tăng maximumPoolSize sẽ sửa leak”.** Có thể chỉ làm hệ thống chịu đựng lâu hơn trước khi cạn; nếu code quên trả connection, cuối cùng pool lớn cũng cạn.

**Sai lầm 11 — “Chỉ cần gọi shutdownNow() là mọi thread chắc chắn dừng”.** Không. Task phải hợp tác với interruption và timeout; I/O không phản hồi có thể vẫn giữ tài nguyên.

**Sai lầm 12 — “Mở mọi Actuator endpoint cho dễ debug”.** Rủi ro bảo mật nghiêm trọng. Chỉ expose endpoint cần thiết qua đường được bảo vệ và kiểm soát dữ liệu chẩn đoán.

## 15. Bài thực hành kiểm chứng

1. **Chạy ứng dụng lab** ở mục 8, đo `hikaricp.connections.active` trước/trong/sau một request `millis=4000`.
2. **Giải thích cảnh báo Hikari** ở ngưỡng 2000ms: vì sao request 4 giây có thể tạo warning dù connection được trả đúng?
3. **Quan sát executor** qua `jvm.threads.live` và thread name `lab-worker-*` sau nhiều request. Vì sao worker còn sống không tự chứng minh leak?
4. **Quan sát descriptor** bằng `/proc/<PID>/fd` hoặc `lsof` trong lúc request giữ `FileChannel`. Tại sao số tổng có thể thay đổi do socket hoặc logger?
5. **Tăng concurrent requests có giới hạn** để chạm Hikari pool max=3. Quan sát active/pending/timeout và phân biệt saturation với leak.
6. **Dừng app đúng cách**; xác minh executor và Hikari pool đóng, process không bị thread unmanaged giữ sống.
7. **Tạo regression test có kiểm soát** cho nhánh exception/timeout của file và JDBC operations. Xác minh `finally`/`try-with-resources` vẫn trả lại tài nguyên.
8. **Thử DevTools restart trong môi trường riêng** rồi dùng `VM.classloader_stats`; đừng suy ra leak chỉ từ một lần class count tăng.
9. **Phân tích một heap dump được phép** bằng MAT, tìm classloader cũ và đường giữ từ GC roots; lưu trữ tệp chẩn đoán theo chính sách bảo mật.
10. **Chạy lại sau khi sửa** với cùng tải và thời gian quan sát; ghi bằng chứng resource usage đạt plateau ổn định.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Actuator Metrics: https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html
- Spring Boot — Actuator Endpoints và bảo mật exposure: https://docs.spring.io/spring-boot/reference/actuator/endpoints.html
- Spring Boot — Developer Tools, restart vs reload và hai classloaders: https://docs.spring.io/spring-boot/reference/using/devtools.html
- Oracle JDK 21 — `jcmd` diagnostic commands: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — Diagnostic Tools/JFR: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- HikariCP — Configuration, `leakDetectionThreshold`: https://github.com/brettwooldridge/HikariCP/wiki/Configuration

**Ghi nhớ:** phát hiện leak không phải tìm một con số lớn mà là chứng minh **tài nguyên không quay về vòng đời đúng**. Với Spring Boot hãy phối hợp Actuator metrics, thread dumps/JFR, Hikari statistics, file-handle inspection và classloader/heap analysis. Mọi resource phải có owner, đường close/shutdown/unregister ở cả nhánh thành công lẫn thất bại, và một phép thử đối chứng xác nhận tài nguyên được giải phóng sau khi công việc kết thúc.
