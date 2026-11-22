# Kiểm thử resource leak trong Spring Batch

Spring Batch thường chạy job trong thời gian dài, xử lý nhiều chunk và có thể retry hoặc restart sau lỗi. Mỗi step có thể mở database cursor, connection, file stream, socket, HTTP response, temporary file hoặc thread. Nếu tài nguyên không được giải phóng đúng lúc, một lần chạy có thể vẫn thành công nhưng các lần chạy tiếp theo dần cạn connection pool, file descriptor, thread hoặc bộ nhớ.

Kiểm thử resource leak cần xác nhận tài nguyên được đóng trên cả đường chạy thành công và đường chạy lỗi. Chỉ kiểm tra JobExecution có COMPLETED chưa đủ; cần quan sát vòng đời ItemStream, quyền sở hữu tài nguyên, số tài nguyên đang hoạt động và khả năng chạy lặp lại mà không tăng dần lượng tài nguyên bị giữ.

## 1. Resource leak là gì?

Resource leak xảy ra khi ứng dụng lấy hoặc tạo một tài nguyên nhưng không giải phóng nó sau khi không còn sử dụng. Trong batch processing, lỗi này thường không xuất hiện ngay ở một lần chạy ngắn. Nó có thể tích lũy qua nhiều chunk, nhiều partition hoặc nhiều lần chạy job.

| Tài nguyên | Dấu hiệu rò rỉ | Tác động có thể xảy ra |
| --- | --- | --- |
| JDBC connection | Số connection đang mượn tăng và không trở về mức nền | Hết connection pool, job chờ hoặc timeout |
| Statement/ResultSet/cursor | Cursor hoặc statement còn mở sau khi step kết thúc | Giữ connection, lock hoặc server-side resource |
| File stream/channel | File không thể đổi tên/xóa hoặc descriptor tăng | Hết file descriptor, file bị khóa |
| HTTP response/body/socket | Response body không được đóng | Cạn connection của HTTP client, socket tồn đọng |
| Temporary file | File trung gian còn sót sau khi job kết thúc | Tốn disk, lộ dữ liệu tạm, đầy filesystem |
| Thread/executor | Thread worker vẫn sống sau khi chủ sở hữu đã kết thúc | Tốn stack/CPU, giữ classloader và bean |
| Lock/buffer | Lock hoặc object lớn được giữ lâu hơn cần thiết | Deadlock, heap tăng hoặc dữ liệu giữa execution bị lẫn |

Không phải mọi tài nguyên còn tồn tại sau step đều là leak. Một file staging có thể được giữ có chủ đích để restart; một thread pool có thể là singleton dùng chung và chỉ được shutdown khi ApplicationContext đóng. Kiểm thử phải dựa trên quyền sở hữu và lifecycle đã thiết kế.

## 2. Xác định ai sở hữu tài nguyên

Trước khi viết test, xác định thành phần nào mở tài nguyên và thành phần nào phải đóng nó. Quy tắc cơ bản là thành phần mở resource phải có trách nhiệm giải phóng resource, trừ khi ownership được chuyển giao rõ ràng.

| Nơi mở resource | Cách quản lý thường phù hợp |
| --- | --- |
| Reader/writer Spring Batch | ItemStream.open() và ItemStream.close() |
| Một method Java | try-with-resources hoặc finally |
| JDBC qua JdbcTemplate/repository | Để Spring quản lý statement, result set và connection theo transaction |
| Connection lấy qua DataSourceUtils | Trả lại bằng DataSourceUtils.releaseConnection() |
| HTTP response/body | Đóng response/body bằng try-with-resources hoặc API tương ứng của client |
| Executor dùng chung | Đăng ký bean với lifecycle của Spring; shutdown khi application context đóng |
| File staging | Quản lý theo execution ID và retention/restart policy |

Không đóng một connection đang được transaction manager quản lý bằng cách gọi connection.close() tùy tiện. Nếu lấy connection qua DataSourceUtils, hãy dùng API release tương ứng. Nếu dùng JdbcTemplate hoặc Spring Data repository, để framework quản lý vòng đời JDBC resource.

Một resource có thể được giữ xuyên nhiều chunk, ví dụ cursor reader. Khi đó không đóng sau mỗi chunk; đóng khi step kết thúc theo hợp đồng lifecycle của reader.

## 3. Vòng đời ItemStream: open, update và close

Spring Batch dùng ItemStream để quản lý resource và trạng thái của reader/writer:

- open(ExecutionContext): mở resource và khôi phục trạng thái cần thiết trước khi xử lý.
- update(ExecutionContext): lưu checkpoint hoặc state cần thiết tại ranh giới chunk.
- close(): giải phóng resource khi step kết thúc.

Một reader tự quản lý file có thể triển khai ItemStreamReader:

~~~java
public class TrackingFileReader implements ItemStreamReader<String> {

    private final Path input;
    private final ResourceProbe probe;
    private BufferedReader reader;

    public TrackingFileReader(Path input, ResourceProbe probe) {
        this.input = input;
        this.probe = probe;
    }

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        try {
            reader = Files.newBufferedReader(input);
            probe.opened();
        } catch (IOException ex) {
            closeAfterOpenFailure();
            throw new ItemStreamException("Cannot open " + input, ex);
        }
    }

    @Override
    public String read() throws Exception {
        return reader == null ? null : reader.readLine();
    }

    @Override
    public void update(ExecutionContext context) {
        // Lưu vị trí đọc/checkpoint ở đây nếu reader hỗ trợ restart.
    }

    @Override
    public void close() throws ItemStreamException {
        if (reader == null) {
            return;
        }

        try {
            reader.close();
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot close " + input, ex);
        } finally {
            reader = null;
            probe.closed();
        }
    }

    private void closeAfterOpenFailure() {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException ignored) {
                // Giữ exception mở resource làm nguyên nhân chính.
            } finally {
                reader = null;
            }
        }
    }
}
~~~

Ví dụ tập trung vào lifecycle; reader production cần lưu và khôi phục vị trí đọc nếu cần restart. close() nên idempotent: gọi nhiều lần cũng không đóng lặp hoặc ném lỗi vì resource đã được giải phóng. Nếu open() mở được một phần tài nguyên rồi thất bại, chính open() cần dọn phần đã mở; không nên giả định framework luôn gọi close() sau một lần open() thất bại giữa chừng.

Spring Batch quản lý lifecycle của ItemStream đã được đăng ký với step. Khi step kết thúc theo lifecycle bình thường, framework gọi đóng các stream đã mở. Không có callback Java nào bảo đảm chạy khi process bị kill -9, JVM crash hoặc máy mất điện; với tình huống đó cần thiết kế tài nguyên có thể được hệ điều hành thu hồi và tác vụ dọn artifact tồn đọng.

## 4. Đảm bảo ItemStream được đăng ký với step

Khi reader hoặc writer trực tiếp được cấu hình cho step và triển khai ItemStream, Spring Batch có thể đăng ký lifecycle của nó thông qua builder. Nhưng nếu một custom wrapper chỉ triển khai ItemReader/ItemWriter và giữ một delegate ItemStream bên trong, framework có thể không nhìn thấy delegate.

Ví dụ wrapper không tự expose ItemStream:

~~~java
public class LoggingReader<T> implements ItemReader<T> {

    private final ItemStreamReader<T> delegate;

    public LoggingReader(ItemStreamReader<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public T read() throws Exception {
        return delegate.read();
    }
}
~~~

Trong trường hợp wrapper không chuyển tiếp open, update, close, đăng ký delegate như một stream của step:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<Order, Order>chunk(100, transactionManager)
    .reader(loggingReader)
    .stream(delegateReader)
    .writer(writer)
    .build();
~~~

Một lựa chọn khác là để wrapper tự triển khai ItemStreamReader và chuyển tiếp cả ba callback tới delegate. Điều quan trọng là mọi resource-owning delegate phải nằm trong lifecycle của step. Thiếu đăng ký stream là nguyên nhân phổ biến khiến close() không được gọi như mong đợi.

## 5. Kiểm thử reader/writer đóng resource sau khi step thành công

Một test hữu ích không chỉ xác nhận reader trả đúng dữ liệu, mà còn quan sát open() và close(). Có thể dùng probe nhỏ trong test để đếm số lần mở/đóng và số resource đang hoạt động:

~~~java
public class ResourceProbe {

    private final AtomicInteger opened = new AtomicInteger();
    private final AtomicInteger closed = new AtomicInteger();

    public void opened() {
        opened.incrementAndGet();
    }

    public void closed() {
        closed.incrementAndGet();
    }

    public int openCount() {
        return opened.get();
    }

    public int closeCount() {
        return closed.get();
    }

    public int activeCount() {
        return openCount() - closeCount();
    }
}
~~~

Sau khi chạy job thành công:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(probe.openCount()).isEqualTo(1);
assertThat(probe.closeCount()).isEqualTo(1);
assertThat(probe.activeCount()).isZero();
~~~

Fixture cần bảo đảm reader được tạo cho đúng step execution và probe là đối tượng test dùng chung để quan sát. Nếu reader chạy qua nhiều execution hoặc nhiều partition, số lần open/close sẽ khác một; khi đó assertion nên kiểm tra số resource đang hoạt động bằng 0 và số lần đóng khớp số lần mở thành công.

## 6. Kiểm thử cleanup khi step thất bại

Leak thường xuất hiện ở error path vì code thoát sớm trước khi đóng resource. Hãy tạo một integration test có reader mở stream, sau đó writer cố ý ném exception:

~~~java
public class FailingOrderWriter implements ItemWriter<Order> {

    @Override
    public void write(Chunk<? extends Order> chunk) {
        throw new IllegalStateException("Simulated writer failure");
    }
}
~~~

Test:

~~~java
JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.FAILED);
assertThat(probe.openCount()).isEqualTo(probe.closeCount());
assertThat(probe.activeCount()).isZero();
~~~

Với fixture mở thành công một stream trước khi writer thất bại, test xác nhận resource được đóng dù step kết thúc FAILED. Không chỉ test exception ở processor; reader/writer có thể có lifecycle khác nhau và lỗi có thể xuất hiện ở các thời điểm khác nhau.

Nên có test riêng cho:

- Lỗi trong processor sau khi reader đã mở.
- Lỗi trong writer sau khi reader đã mở.
- Lỗi khi mở resource.
- Lỗi trong chính close().
- Step bị dừng hoặc bị yêu cầu stop.

Đối với lỗi xảy ra giữa open(), kiểm tra logic cleanup nội bộ của open() vì framework không thể đóng một stream mà nó chưa nhận được trạng thái mở thành công.

## 7. Kiểm thử reader/writer đóng đúng một lần và idempotent

Không chỉ kiểm tra active count bằng 0. Một implementation có thể đóng cùng resource hai lần, hoặc callback bị gọi lại khi code cleanup được thiết kế không idempotent.

Với reader custom, kiểm tra:

- close() sau khi mở thành công giải phóng resource.
- Gọi close() lần thứ hai không làm phát sinh lỗi ngoài dự kiến.
- Field giữ resource được reset về null.
- close() không xóa checkpoint cần cho restart.
- Exception trong lúc đóng không làm resource reference bị giữ mãi trong bean.

Ví dụ unit test:

~~~java
@Test
void closeIsSafeWhenCalledMoreThanOnce() throws Exception {
    TrackingFileReader reader = new TrackingFileReader(input, probe);
    reader.open(new ExecutionContext());

    reader.close();
    reader.close();

    assertThat(probe.activeCount()).isZero();
}
~~~

Test unit này bổ sung cho integration test lifecycle. Nó không thay thế kiểm thử rằng Spring Batch thực sự gọi close() cho stream được cấu hình trong step.

## 8. Kiểm thử JDBC connection leak

JDBC resource thường gồm connection, statement và result set. Nếu dùng JdbcTemplate, Spring Data repository hoặc reader/writer có sẵn của Spring Batch, framework quản lý phần lớn việc acquire/release. Leak dễ xảy ra hơn trong code tự gọi DataSource.getConnection() hoặc giữ cursor thủ công.

Code không an toàn:

~~~java
public List<Order> loadOrders(DataSource dataSource) throws SQLException {
    Connection connection = dataSource.getConnection();
    PreparedStatement statement =
        connection.prepareStatement("select id from orders");
    ResultSet resultSet = statement.executeQuery();
    return map(resultSet);
}
~~~

Ví dụ trên không đóng result set, statement hoặc connection. Dùng try-with-resources nếu method sở hữu các resource đó:

~~~java
public List<Order> loadOrders(DataSource dataSource) throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement("select id from orders");
         ResultSet resultSet = statement.executeQuery()) {
        return map(resultSet);
    }
}
~~~

Nếu connection được lấy từ DataSourceUtils trong transaction Spring, hãy release bằng DataSourceUtils.releaseConnection() thay vì tự đóng connection đang được transaction manager quản lý. Với JdbcTemplate, không cần tự quản lý connection.

## 9. Đo connection đang active bằng connection pool

Một integration test có thể quan sát connection pool trước và sau job. Với HikariCP, HikariPoolMXBean cung cấp số connection active, idle và tổng:

~~~java
HikariPoolMXBean pool = hikariDataSource.getHikariPoolMXBean();

int activeBefore = pool.getActiveConnections();

JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(pool.getActiveConnections()).isEqualTo(activeBefore);
~~~

Đây là cách minh họa; trong test thực tế, cần lấy baseline sau khi application context và test fixture đã ổn định. Các thao tác metadata repository, health check hoặc background task có thể mượn connection đồng thời, vì vậy một assertion tức thời bằng đúng baseline có thể chập chờn. Có thể đợi trong một khoảng timeout ngắn cho pool trở về baseline và xác nhận xu hướng ổn định.

Không đặt activeConnections == 0 một cách máy móc nếu pool có connection đang được sử dụng hợp lệ bởi test hoặc transaction ngoài. Hãy cô lập datasource, tắt background traffic trong test hoặc so sánh với baseline đã đo.

Hikari leakDetectionThreshold là công cụ chẩn đoán connection bị giữ lâu hơn ngưỡng. Nó ghi cảnh báo và stack trace nơi connection được mượn; nó không tự đóng connection bị leak và không thay thế assertion trong test.

## 10. Dùng proxy DataSource để đếm acquire/release

Nếu cần kiểm tra chính xác code của ứng dụng đã trả connection hay chưa, có thể bọc datasource bằng một proxy/decorator trong test. Proxy ghi nhận mỗi lần getConnection() và mỗi lần connection được đóng/release.

Một cách triển khai test có thể dùng thư viện datasource-proxy hoặc wrapper Java DataSource/Connection. Điều quan trọng là:

- Theo dõi connection được mượn thành công.
- Ghi nhận việc close()/release xảy ra đúng một lần.
- Không nhầm Connection.close() của connection pool với đóng socket vật lý; pool thường trả connection về pool.
- Kiểm tra cả connection lấy qua getConnection(username, password).
- Không để wrapper thay đổi transaction semantics của datasource.

Proxy hữu ích để phát hiện code tự quản lý JDBC sai. Nhưng nếu proxy chỉ đếm số lần close() mà không hiểu transaction-bound connection, test có thể báo sai. Nên kiểm tra cùng với pool metrics và kết quả transaction.

## 11. Kiểm thử ResultSet, Statement và cursor

Một connection có thể đã được trả về pool trong khi statement hoặc cursor vẫn còn mở, tùy driver và cách sử dụng. Với custom JDBC code, cần đóng resource theo thứ tự ngược với thứ tự mở:

~~~text
Connection
  └── PreparedStatement
        └── ResultSet
~~~

Try-with-resources đóng result set, statement rồi connection. Nếu dùng JdbcCursorItemReader, để reader quản lý cursor theo lifecycle ItemStream; không tự đóng connection/statement bên trong processor hoặc listener khi reader còn đang dùng.

Các test hữu ích:

- Xác nhận custom mapper/reader đóng result set khi hết dữ liệu.
- Xác nhận lỗi khi map row vẫn đóng statement và connection.
- Xác nhận cursor reader đóng resource sau step success và failure.
- Chạy nhiều lần để phát hiện số cursor/connection đang mở tăng dần.

Nếu driver/database cung cấp metric session/cursor, có thể dùng metric đó để kiểm tra leak ở integration environment. Tránh phụ thuộc vào tên session hoặc counter đặc thù của một driver trong unit test chung.

## 12. Kiểm thử file stream và file descriptor

Reader/writer file thường giữ file handle trong toàn bộ step. Dùng ItemStream.close() để đóng handle. Test có thể dùng probe đếm open/close, sau đó thử thao tác filesystem trên file:

~~~java
Path moved = tempDirectory.resolve("input-after-step.txt");

Files.move(inputFile, moved);

assertThat(Files.exists(moved)).isTrue();
~~~

Trên Windows, file đang mở thường có thể khiến move/delete thất bại tùy cách handle được mở và sharing flags. Vì vậy thao tác move/delete là một tín hiệu bổ sung; probe lifecycle vẫn là assertion chính và ít phụ thuộc hệ điều hành hơn.

Với FlatFileItemReader hoặc FlatFileItemWriter, kiểm tra:

- File được đóng sau khi step kết thúc.
- Step failure cũng giải phóng stream.
- File đầu vào cần restart không bị xóa.
- File output staging được giữ hoặc xóa theo chính sách.
- Chạy lặp không tạo thêm handle/file tạm không giới hạn.

Không nhầm file còn tồn tại với resource leak. Output file được giữ lại có thể là kết quả nghiệp vụ hợp lệ; leak là handle/descriptor còn mở hoặc artifact tạm không còn chủ sở hữu.

## 13. Kiểm thử temporary file và cleanup theo execution

Temporary file nên có tên gắn với job/step execution hoặc batch ID để không đè lên nhau khi hai job chạy đồng thời. Test nên chạy cả success và failure, rồi kiểm tra file tạm theo chính sách đã thiết kế.

Ví dụ:

~~~java
Path staging = tempDirectory.resolve(
    "orders-" + jobExecutionId + ".tmp"
);

// Step ghi staging file.
// Listener chỉ publish khi thành công.
// Cleanup job xử lý file thất bại theo retention policy.
~~~

Các assertion có thể gồm:

- Sau success, staging được publish thành artifact cuối hoặc được xóa nếu không cần giữ.
- Sau failure có thể giữ staging để restart/diagnostics theo thiết kế.
- Sau khi execution đã hết thời hạn restart, cleanup job xóa artifact cũ.
- Cleanup chạy hai lần không gây lỗi hoặc xóa artifact của execution khác.
- Hai execution song song không dùng chung path tạm.

Không xóa file ngay khi step có trạng thái FAILED nếu job có thể restart từ checkpoint và cần file đó. Resource handle phải được đóng ngay; dữ liệu tạm bền vững được xóa theo chính sách retention khác.

## 14. Kiểm thử HTTP response và network resource

Khi processor hoặc writer gọi HTTP API, response body có thể giữ socket/connection từ HTTP client. Đọc response rồi bỏ qua việc đóng body có thể làm pool của client cạn dần.

Ví dụ với Java HTTP client trả về InputStream:

~~~java
HttpResponse<InputStream> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofInputStream()
);

try (InputStream body = response.body()) {
    return parse(body);
}
~~~

Với client khác, dùng API close/dispose tương ứng cho response/body. Không chỉ đóng khi status code là 2xx; error response cũng có body và cần được giải phóng.

Trong test, dùng mock server hoặc fake client để đếm response/body đã đóng. Kiểm tra cả success, non-2xx, timeout và lỗi parse body. Nếu client dùng connection pool, theo dõi leased/available connection qua metric của client nếu API hỗ trợ.

Không giữ response object trong field singleton sau khi xử lý item. Trả dữ liệu cần thiết ra khỏi method rồi đóng response ngay khi hoàn tất.

## 15. Kiểm thử thread và executor lifecycle

Một step có thể dùng TaskExecutor để chạy worker hoặc partition. Cần phân biệt executor thuộc step hay được chia sẻ ở cấp application:

- Executor được quản lý như Spring bean dùng chung thường sống cùng ApplicationContext và được shutdown khi context đóng.
- Executor được tạo thủ công trong method hoặc trong từng execution phải được shutdown bởi thành phần sở hữu nó.
- Không shutdown một executor singleton sau mỗi step nếu các step khác còn dùng nó.
- Không tạo thread mới cho từng item mà không có giới hạn hoặc cơ chế kết thúc.

Với ThreadPoolTaskExecutor do Spring quản lý:

~~~java
@Bean
ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setThreadNamePrefix("batch-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    return executor;
}
~~~

Test có thể kiểm tra sau khi step hoàn tất không còn task worker của execution đó đang chạy. Khi đóng ApplicationContext, xác nhận executor được shutdown và worker thread kết thúc trong thời gian cho phép. Không đòi hỏi thread pool dùng chung phải shutdown ngay sau mỗi job.

## 16. Kiểm thử với partitioning và multi-threaded step

Resource leak dễ bị che giấu khi chỉ chạy một worker. Partitioning có thể mở nhiều reader, cursor, file hoặc connection cùng lúc. Test nên xác nhận resource được đóng cho từng partition, kể cả khi chỉ một partition thất bại.

Ví dụ, nếu có bốn partition và mỗi partition mở một file reader:

~~~text
Manager
  |
  +-- Partition 0 -> open reader 0 -> close reader 0
  +-- Partition 1 -> open reader 1 -> close reader 1
  +-- Partition 2 -> open reader 2 -> exception -> close reader 2
  +-- Partition 3 -> open reader 3 -> close reader 3
~~~

Test cần theo dõi số resource đang hoạt động theo partition hoặc tổng cộng. Sau khi manager step kết thúc, số resource do các worker mở phải trở về 0. Nếu worker remote chạy ở process khác, đo resource tại worker process; manager không thể trực tiếp quan sát file handle hoặc connection của node khác chỉ qua local probe.

Khi dùng multi-threaded step, probe phải thread-safe (AtomicInteger, LongAdder hoặc collector đồng bộ). Không dùng ArrayList mutable không đồng bộ để ghi nhận event lifecycle từ nhiều worker.

## 17. Kiểm thử restart và resource lifecycle

Restart là một luồng riêng cần được kiểm thử. Sau khi step thất bại, resource của execution cũ phải được đóng; khi restart, reader/writer mở resource mới và khôi phục checkpoint.

Một test restart có thể:

1. Chạy job và làm writer thất bại sau một chunk đã commit.
2. Xác nhận reader/file/database resource của lần chạy đầu đã được đóng.
3. Khởi chạy lại cùng JobInstance với parameters phù hợp.
4. Xác nhận reader mở lại resource và đọc từ checkpoint.
5. Xác nhận sau lần chạy thứ hai, resource mới cũng được đóng.

Không dùng lại một stream đã đóng cho execution restart. open() cần tạo resource mới và dùng ExecutionContext để khôi phục vị trí. Nếu reader lưu state vào field nhưng không ghi vào context, restart có thể đọc sai vị trí dù resource không bị leak.

Với file output, kiểm tra FlatFileItemWriter hoặc custom writer dùng state/restart policy đúng. File còn tồn tại không đồng nghĩa với handle còn mở; cần test cả nội dung, checkpoint và close count.

## 18. Chạy lặp để phát hiện leak tích lũy

Một test đơn lẻ có thể bỏ sót leak nhỏ. Với một step ngắn, chạy lặp nhiều lần trong cùng test ApplicationContext và quan sát tài nguyên sau mỗi lần:

~~~text
Run 1: active connections = 0
Run 2: active connections = 0
Run 3: active connections = 0
...
Run N: active connections = 0
~~~

Nếu active connection, open file count, worker thread hoặc số temporary file tăng dần sau mỗi lần chạy, có thể có leak hoặc cleanup policy chưa hoàn tất.

Không cần chạy số vòng quá lớn trong unit test. Chọn số lần đủ để lộ xu hướng, giữ fixture cô lập và tránh biến test thành benchmark. Với leak phụ thuộc thời gian, dùng stress/integration test riêng và ghi nhận metric theo từng vòng.

Nên so sánh với baseline sau khi framework, connection pool và background thread đã khởi tạo xong. Một số pool giữ idle connection hoặc worker thread theo thiết kế; số resource tổng không nhất thiết trở về 0. Điều cần ổn định là số resource đang được mượn/giữ ngoài phạm vi dự kiến.

## 19. Dùng metric và công cụ chẩn đoán

Test assertion là lớp bảo vệ chính; metric và profiler giúp tìm nguyên nhân khi test hoặc production phát hiện leak.

Các nguồn quan sát hữu ích:

- HikariCP/JMX: active, idle, total connection và pending thread.
- HTTP client metrics: leased, available connection, pending acquire.
- JVM: live thread count, heap usage, direct buffer và classloader.
- OS: số file descriptor/handle và socket đang mở.
- Database: session, cursor, lock và connection theo application name.
- Java Flight Recorder: socket, file I/O, thread và allocation event.
- Log: stack trace từ leak detection của connection pool hoặc client.

Hãy đặt ngưỡng theo workload thực tế. Một số resource được pool cố ý giữ lại để tái sử dụng; đó không phải leak. Leak thường biểu hiện bằng resource active/leased tăng không giảm, số thread tăng qua từng execution hoặc artifact không còn chủ sở hữu.

Hikari leakDetectionThreshold là cảnh báo khi connection được giữ lâu, không phải cơ chế tự sửa. Dùng stack trace của cảnh báo để tìm nơi acquire và xác định nhánh code nào không release.

## 20. Test không nên phụ thuộc vào GC để chứng minh cleanup

Không nên dùng System.gc() rồi kiểm tra số object hoặc file descriptor để kết luận resource đã đóng. Garbage collection không bảo đảm chạy ngay và finalizer/cleaner không thay thế lifecycle rõ ràng.

Resource như file stream, JDBC connection và HTTP response cần được đóng tường minh. Kiểm tra bằng probe, proxy, pool metric hoặc thao tác trên resource sau khi step kết thúc. Heap assertion chỉ hữu ích cho loại memory leak cần phân tích bằng profiler và thường thuộc stress test riêng.

Nếu một class dựa vào Cleaner để phòng vệ cuối cùng, test vẫn phải xác nhận code gọi close/dispose đúng lúc. Cleaner không phải đường cleanup chính của step.

## 21. Những lỗi thường gặp khi kiểm thử resource leak

**Chỉ test đường thành công:** lỗi trong processor/writer có thể bỏ qua cleanup. Tạo test failure sau khi resource đã mở.

**Chỉ assert job status:** job COMPLETED không chứng minh connection/file/socket đã đóng. Theo dõi active resource hoặc close callback.

**Reader delegate không được đăng ký ItemStream:** wrapper không expose lifecycle nên delegate có thể không nhận close(). Đăng ký .stream(delegate) hoặc forward toàn bộ ItemStream contract.

**Đóng connection transaction-bound thủ công:** có thể phá transaction. Dùng JdbcTemplate, repository hoặc DataSourceUtils đúng cách.

**Giả định close() chạy sau JVM crash:** callback chỉ được gọi trong lifecycle mà process còn có thể thực thi. Thiết kế recovery và cleanup tồn đọng.

**Đếm pool connection rồi yêu cầu bằng 0:** pool có thể giữ connection idle hoặc test khác đang dùng. So sánh active count với baseline và cô lập test.

**Xóa file staging ngay khi FAILED:** job có thể restart và cần file/checkpoint đó. Đóng handle ngay nhưng giữ artifact theo retention policy.

**Shutdown executor dùng chung sau mỗi step:** các step khác có thể còn cần executor. Quản lý lifecycle ở ApplicationContext.

**Dùng probe không thread-safe:** nhiều partition cập nhật đồng thời có thể làm số liệu test sai. Dùng atomic/concurrent collector.

**Dùng GC/finalizer làm cleanup:** thời điểm không xác định và không bảo đảm. Gọi close/dispose tường minh.

## 22. Ma trận kiểm thử resource lifecycle

Một bộ integration test thực tế nên bao phủ các tình huống chính:

| Kịch bản | Resource cần theo dõi | Kết quả mong đợi |
| --- | --- | --- |
| Step thành công | Reader, writer, connection, file | Resource được đóng; active count trở về baseline |
| Processor ném exception | Reader và resource đã mở | Step kết thúc theo policy; resource được giải phóng |
| Writer ném exception | Reader, writer, JDBC | Không còn resource mượn sau khi step kết thúc |
| Reader open thất bại giữa chừng | File/channel/connection đã mở một phần | open() tự dọn phần đã tạo |
| Reader delegate nằm trong wrapper | Delegate stream | Delegate nhận lifecycle close |
| Step restart | Resource cũ và resource mới | Resource cũ đóng; resource mới mở và đóng; checkpoint được khôi phục |
| Nhiều partition | Mỗi worker resource | Tất cả resource của worker kết thúc đều được giải phóng |
| Job chạy lặp | Pool, thread, temp file | Không tăng dần active resource/artifact ngoài chính sách |
| ApplicationContext đóng | Executor và singleton resource | Executor được shutdown theo lifecycle ứng dụng |

Không phải mọi test đều cần mock tất cả resource. Chọn integration test cho transaction/lifecycle thật và unit test cho code tự quản lý resource. Test càng gần resource thực tế càng hữu ích trong việc phát hiện lỗi ownership.

## 23. Quy trình xây dựng test cho custom ItemStream

Khi viết reader/writer tùy chỉnh, hãy thiết kế khả năng quan sát lifecycle ngay từ đầu:

1. Tách việc mở resource khỏi constructor và đặt trong open().
2. Đảm bảo open() tự dọn resource nếu quá trình mở thất bại giữa chừng.
3. Lưu checkpoint trong update() nếu component cần restart.
4. Đóng resource trong close() và reset reference trong finally.
5. Làm close() idempotent.
6. Đăng ký mọi delegate ItemStream với step.
7. Dùng probe hoặc wrapper trong test để quan sát số lần mở/đóng.
8. Kiểm tra success, failure, stop, restart và nhiều execution đồng thời.

Một custom stream không nên giữ tài nguyên trong static field hoặc truyền resource qua các execution. Mỗi step execution cần sở hữu đúng resource của nó; resource dùng chung cấp application phải có lifecycle riêng.

## 24. Cách kiểm thử resource leak trong production

Trước tiên, lập danh sách tài nguyên step mở và xác định rõ owner cùng thời điểm đóng. Với reader/writer Spring Batch, dùng ItemStream.open/update/close; với JDBC, dùng JdbcTemplate/repository hoặc quản lý connection theo transaction; với HTTP response, file stream và socket, đóng tường minh; với executor, để Spring quản lý lifecycle nếu dùng chung.

Tiếp theo, viết integration test cho cả success và failure. Dùng probe cho custom ItemStream, pool metrics hoặc datasource proxy cho JDBC, mock server cho HTTP body, và kiểm tra thread/executor ở đúng phạm vi lifecycle. Bao gồm delegate stream, partitioning và restart nếu step dùng các cơ chế đó.

Cuối cùng, chạy lặp nhiều lần để phát hiện xu hướng resource tăng dần. So sánh active resource với baseline, phân biệt tài nguyên idle được pool giữ hợp lệ với tài nguyên đang bị leak. Trong production, theo dõi connection pool, HTTP pool, thread, file descriptor và artifact tạm; dùng JFR/JMX/log để truy vết nơi acquire mà không release.

Kiểm thử resource leak trong Spring Batch là kiểm chứng ownership và lifecycle trên mọi đường chạy. Một step chỉ được xem là giải phóng tài nguyên đúng khi các stream, connection, response, file handle và worker do execution sở hữu được đóng sau success hoặc failure, đồng thời state cần restart vẫn được giữ đúng. Probe, pool metrics, test lặp và kiểm thử restart giúp phát hiện rò rỉ trước khi chúng tích lũy thành lỗi vận hành.
