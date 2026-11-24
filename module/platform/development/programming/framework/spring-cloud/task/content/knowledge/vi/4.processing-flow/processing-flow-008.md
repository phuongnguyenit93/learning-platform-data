# Đóng tệp, kết nối và tài nguyên sau xử lý

Trong **Spring Cloud Task**, một ứng dụng được khởi chạy để thực hiện công việc **có thời gian chạy hữu hạn** rồi kết thúc: nhập tệp, tạo báo cáo, làm sạch dữ liệu hoặc đồng bộ với hệ thống khác. Điểm kết thúc đúng nghĩa không chỉ là “xử lý xong bản ghi cuối cùng”. Ứng dụng còn phải giải phóng tệp, kết nối, luồng thực thi và các tài nguyên tạm; ghi nhận kết quả thực thi; sau đó trả trạng thái đủ tin cậy cho bộ điều phối.

Bài học thuộc chương **Luồng xử lý**, tập trung vào **đóng tệp, kết nối và tài nguyên sau xử lý**. Đây là nền tảng để một Spring Cloud Task có thể chạy theo lịch hoặc theo yêu cầu nhiều lần mà không làm cạn kết nối, rò rỉ file descriptor, tạo kết quả dở dang hay bị treo do tiến trình chưa kết thúc. Các ví dụ dùng Java, Spring Boot, Spring JDBC và một số cấu hình vận hành điển hình; chi tiết triển khai có thể khác tùy phiên bản Spring Boot và Spring Cloud Task.

## 1. Vì sao kết thúc tác vụ phải đi kèm giải phóng tài nguyên?

Giả sử một tác vụ nhập dữ liệu chạy mỗi 15 phút. Mỗi lượt đọc một tệp, dùng kết nối cơ sở dữ liệu và tạo vài luồng xử lý. Nếu ứng dụng chỉ hoàn tất logic nghiệp vụ mà **không đóng tài nguyên**, có thể xảy ra:

- **Tệp chưa được đóng:** hệ điều hành giữ file descriptor; tệp tạm không xóa hoặc di chuyển được, đặc biệt dễ thấy trên Windows.
- **Kết nối CSDL chưa được trả về pool:** những lượt chạy song song thiếu kết nối, chờ timeout hoặc thất bại dù database vẫn hoạt động.
- **HTTP response chưa tiêu thụ/đóng:** kết nối mạng không thể tái sử dụng, số socket tăng và các lời gọi tiếp theo chậm dần.
- **Executor còn luồng không phải daemon:** phần nghiệp vụ đã xong nhưng JVM vẫn sống, khiến launcher tưởng tác vụ đang chạy.
- **Tệp kết quả mới ghi một phần:** người tiêu thụ đọc phải bản báo cáo thiếu dòng dù tiến trình tạo báo cáo thất bại.
- **Tác vụ bị dừng đột ngột:** trạng thái bên ngoài và metadata có thể chưa phản ánh cùng một thời điểm.

**TaskRepository** của Spring Cloud Task giúp theo dõi **TaskExecution** (ví dụ thời gian bắt đầu, thời gian kết thúc, mã thoát và thông báo lỗi), nhưng không tự đóng mọi tài nguyên do mã ứng dụng tạo. Quản lý vòng đời tài nguyên là trách nhiệm phối hợp giữa mã Java, Spring Framework, thư viện truy cập dữ liệu và môi trường chạy.

### Luồng tổng thể

~~~mermaid
flowchart TD
    A["Bộ điều phối khởi chạy ứng dụng"] --> B["Khởi tạo Spring Context và TaskExecution"]
    B --> C["Nhận và kiểm tra tham số"]
    C --> D["Mở tài nguyên trong phạm vi cần dùng"]
    D --> E["Đọc / xử lý / ghi kết quả"]
    E --> F{"Kết quả xử lý?"}
    F -- "Thành công" --> G["Commit dữ liệu và xuất bản đầu ra"]
    F -- "Lỗi" --> H["Rollback trong phạm vi giao dịch, giữ thông tin lỗi"]
    G --> I["Đóng tài nguyên theo quyền sở hữu"]
    H --> I
    I --> J["Hoàn tất vòng đời Task và đóng ApplicationContext"]
    J --> K["Tiến trình kết thúc; launcher nhận trạng thái"]
~~~

Sơ đồ mô tả **trách nhiệm logic**, không áp đặt thứ tự nội bộ tuyệt đối của mọi callback Spring. Một số tài nguyên đóng khi ra khỏi khối xử lý; một số bean đóng khi ApplicationContext dừng. Điều quan trọng là tài nguyên còn cần thiết để ghi trạng thái cuối cùng của TaskRepository phải được Spring quản lý đến hết vòng đời phù hợp.

## 2. Phân loại tài nguyên và xác định ai có trách nhiệm đóng

Không có một lệnh đóng chung cho tất cả tài nguyên. Trước khi viết tác vụ, hãy xác định **tài nguyên được tạo ở đâu, ai sở hữu và khi nào nó không còn cần thiết**.

| Tài nguyên | Cách tạo thường gặp | Cách kết thúc phù hợp | Lỗi hay gặp |
| --- | --- | --- | --- |
| Tệp đầu vào | **Files.newBufferedReader**, **Files.newInputStream**, **ZipFile** | **try-with-resources** ngay tại phạm vi đọc | Quên đóng khi phát sinh exception |
| Tệp đầu ra | **Files.newBufferedWriter**, **Files.newOutputStream** | Đóng/flush rồi mới công bố tệp hoàn chỉnh | Công bố tệp trước khi ghi xong |
| Luồng thư mục | **Files.lines**, **Files.list**, **Files.walk** | Đóng **Stream** sau khi duyệt | Nghĩ terminal operation sẽ tự đóng tệp |
| JDBC thao tác trực tiếp | **DataSource.getConnection** ngoài giao dịch Spring | **try-with-resources** cho Connection, Statement, ResultSet | Không trả Connection vào pool |
| JDBC qua Spring | **JdbcTemplate**, **@Transactional** | Để **JdbcTemplate** và transaction manager quản lý Connection | Tự đóng Connection đang thuộc transaction |
| HTTP request/response | Client dùng kết nối tái sử dụng | Đóng **response body/response handle** theo API thư viện | Không giải phóng response khi gặp lỗi HTTP |
| Pool, client dùng chung | Bean cấu hình bởi Spring | Để Spring thực thi lifecycle/destroy khi đóng context | Đóng singleton ngay giữa một tác vụ |
| Executor, thread pool | Bean hoặc mã ứng dụng tạo | Chờ công việc hoàn tất; dừng executor do mình sở hữu | Chạy “fire-and-forget” rồi kết thúc Task |
| Tệp tạm, thư mục làm việc | **Files.createTempFile** hoặc work directory | Xóa tệp chưa xuất bản sau lỗi; có chính sách dọn bản cũ | Tệp hỏng tích tụ sau mỗi lần retry |
| Khóa/lease phân tán | Bảng khóa, Redis, hệ điều phối | Nhả lease khi có thể; bắt buộc TTL và cơ chế khôi phục | Tin rằng khối finally luôn được chạy |

Có hai khái niệm phải tách rõ:

1. **Tài nguyên cục bộ trong một thao tác:** ví dụ BufferedReader đọc một tệp. Mã mở nó nên đóng nó, thường bằng try-with-resources.
2. **Tài nguyên dài hạn do Spring quản lý:** ví dụ HikariDataSource, client HTTP cấu hình thành bean và executor dùng chung. Spring chịu trách nhiệm đóng khi ApplicationContext ngừng; mã nghiệp vụ không nên đóng sớm.

Một đối tượng **Connection.close()** lấy từ pool thường có nghĩa là **trả kết nối về pool**, không nhất thiết đóng socket vật lý. Vì thế vẫn phải gọi đúng thao tác giải phóng, nhưng không tự đóng toàn bộ DataSource đang được các thành phần khác sử dụng.

## 3. Quản lý tệp đầu vào bằng try-with-resources

Java có **try-with-resources** để tự gọi **close()** trên các đối tượng **AutoCloseable** khi rời khối, bất kể thành công hay có exception. Đây là lựa chọn mặc định cho BufferedReader, InputStream, OutputStream, ZipFile và nhiều tài nguyên tương tự.

### Ví dụ: đọc tệp chứa mã đơn hàng

Giả sử đầu vào là tệp UTF-8, **mỗi dòng chỉ chứa một mã đơn hàng**. Tác vụ đọc 250 mã mỗi lô và ghi vào CSDL. Tệp này được cố ý giữ định dạng đơn giản để tập trung vào quản lý tài nguyên; với CSV có dấu phẩy, dấu nháy hoặc xuống dòng trong trường dữ liệu, cần parser CSV đúng chuẩn.

~~~java
@Component
public class ImportRunner implements ApplicationRunner {

    private static final int CHUNK_SIZE = 250;
    private final ImportBatchService importService;

    public ImportRunner(ImportBatchService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        List<String> options = args.getOptionValues("input");
        if (options == null || options.size() != 1
                || options.get(0).isBlank()) {
            throw new IllegalArgumentException(
                "Expected exactly one --input=/path/to/file");
        }

        Path input = Path.of(options.get(0));
        List<String> chunk = new ArrayList<>(CHUNK_SIZE);

        try (BufferedReader reader =
                 Files.newBufferedReader(input, StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                if (line.isBlank()) {
                    continue;
                }

                chunk.add(line.trim());
                if (chunk.size() == CHUNK_SIZE) {
                    importService.upsertChunk(List.copyOf(chunk));
                    chunk.clear();
                }
            }

            if (!chunk.isEmpty()) {
                importService.upsertChunk(List.copyOf(chunk));
            }
        }
    }
}
~~~

**Điểm cần quan sát:**

- BufferedReader chỉ tồn tại trong phạm vi đọc một tệp; mã không phải nhớ đóng trong từng nhánh if hay catch.
- Nếu **upsertChunk** ném exception, BufferedReader vẫn được đóng và exception tiếp tục đi ra ngoài để Spring Boot nhận biết lỗi.
- Mỗi lô được giao cho một service khác, giúp đặt **ranh giới giao dịch** hợp lý thay vì giữ một transaction lớn trong suốt thời gian đọc.
- Khi không có dữ liệu, tác vụ vẫn đóng tệp đúng cách. Việc tệp rỗng được coi là thành công hay lỗi là **quy tắc nghiệp vụ riêng**, cần định nghĩa trước.

Đối với **Files.lines(path)**, **Files.list(dir)** hoặc **Files.walk(dir)**, đối tượng Stream cũng cần được đóng vì nó có thể giữ tài nguyên hệ điều hành:

~~~java
try (Stream<String> lines =
         Files.lines(inputPath, StandardCharsets.UTF_8)) {

    long validCount = lines
            .filter(line -> !line.isBlank())
            .count();

    System.out.println("Valid records: " + validCount);
}
~~~

Lời gọi **count()** chỉ kết thúc phép duyệt; không thay thế **close()**. Không trả Stream gắn với tệp ra ngoài phạm vi mà tài nguyên đã bị đóng.

### Nếu lỗi xảy ra ngay trong lúc đóng tệp?

try-with-resources giữ exception chính từ phần xử lý và thường đưa exception phát sinh ở **close()** vào danh sách **suppressed exceptions**. Khi chẩn đoán lỗi I/O phức tạp, đừng chỉ đọc thông điệp cấp cao: kiểm tra cả nguyên nhân và suppressed exceptions trong log. Nếu thao tác close thất bại khi phần xử lý trước đó thành công, exception từ close có thể khiến cả lượt chạy thất bại; đây là tín hiệu cần được xem xét, nhất là khi đầu ra chưa chắc đã flush thành công.

## 4. Tệp đầu ra: đóng hoàn tất rồi mới xuất bản

Nhập tệp và xuất báo cáo có yêu cầu khác nhau. Tệp đầu vào chỉ cần đọc; **tệp đầu ra cần tránh lộ nội dung ghi dở**.

Ví dụ báo cáo phải được tạo tại **report-2026-11-24.csv**. Nếu ghi thẳng vào đường dẫn mà người dùng có thể tải xuống, ứng dụng khác có thể đọc một tệp mới chỉ có vài dòng. Mẫu phổ biến là:

1. Tạo **tệp tạm trong cùng thư mục/filesystem** với tệp kết quả.
2. Ghi nội dung vào tệp tạm bằng try-with-resources; khi rời khối, writer được đóng.
3. Kiểm tra các điều kiện cần thiết (số dòng, checksum, định dạng).
4. Chuyển từ tệp tạm sang tên chính thức bằng thao tác thích hợp với hệ lưu trữ.
5. Nếu lỗi trước khi công bố, xóa tệp tạm hoặc ghi nhận để cơ chế dọn dẹp xử lý.

Ví dụ dùng filesystem có hỗ trợ atomic move:

~~~java
public void publishReport(Path outputDir, String reportText)
        throws IOException {

    Path destination = outputDir.resolve("report-2026-11-24.csv");
    Path temporary = Files.createTempFile(
            outputDir, ".report-", ".partial");

    try {
        try (BufferedWriter writer = Files.newBufferedWriter(
                temporary, StandardCharsets.UTF_8)) {
            writer.write(reportText);
        }

        // Chỉ chuyển tên sau khi writer đã đóng thành công.
        Files.move(temporary, destination,
                   StandardCopyOption.ATOMIC_MOVE);

    } catch (IOException | RuntimeException error) {
        try {
            Files.deleteIfExists(temporary);
        } catch (IOException cleanupError) {
            error.addSuppressed(cleanupError);
        }
        throw error;
    }
}
~~~

**Giới hạn của ví dụ:** ATOMIC_MOVE không được mọi filesystem hỗ trợ; khi không hỗ trợ, có thể phát sinh **AtomicMoveNotSupportedException**. Đường dẫn trong mã chỉ là minh họa và cần được xác định theo **report key/version** thực tế. Không được chỉ dựa vào thao tác rename để chống hai tiến trình cùng công bố báo cáo; cơ chế chống trùng phải dựa trên khóa nghiệp vụ, quy ước tên, kiểm soát phiên bản hoặc ràng buộc ở cơ sở dữ liệu. Atomic move cũng không đồng nghĩa bảo đảm dữ liệu đã được đồng bộ bền vững xuống thiết bị lưu trữ; yêu cầu độ bền cao cần quy trình fsync và đặc điểm filesystem phù hợp.

Đối với **object storage**, không thể giả định thao tác rename như filesystem cục bộ. Thường cần upload đầy đủ đối tượng, kiểm tra checksum/etag theo quy ước, sau đó cập nhật bản ghi trạng thái **READY** hoặc con trỏ tới object đã hoàn chỉnh. Nếu upload hoặc cập nhật trạng thái thất bại, lần chạy lại phải có cách phát hiện và xử lý object mồ côi.

## 5. Kết nối CSDL: phân biệt JDBC trực tiếp và Spring quản lý

Spring Cloud Task dùng **TaskRepository** để lưu metadata thực thi trong CSDL; cùng ứng dụng có thể dùng CSDL khác hoặc cùng CSDL để ghi dữ liệu nghiệp vụ. Hai nhu cầu này có thể dùng các DataSource được cấu hình tương ứng. Tránh đóng tài nguyên phục vụ metadata trước khi lifecycle của Task hoàn tất.

### 5.1. Khi tự lấy Connection bằng JDBC

Nếu mã **không nằm trong transaction do Spring quản lý** và trực tiếp gọi **DataSource.getConnection()**, hãy trả Connection về pool bằng try-with-resources:

~~~java
public long countPending(DataSource dataSource) throws SQLException {
    String sql = "SELECT COUNT(*) FROM import_queue WHERE status = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement = connection.prepareStatement(sql)) {

        statement.setString(1, "PENDING");

        try (ResultSet resultSet = statement.executeQuery()) {
            resultSet.next();
            return resultSet.getLong(1);
        }
    }
}
~~~

Đối tượng được đóng theo thứ tự ngược với lúc mở: ResultSet, PreparedStatement rồi Connection. Nếu phát sinh lỗi ở bất kỳ bước nào, tài nguyên đã mở vẫn được giải phóng.

Nếu bạn lấy Connection thông qua cơ chế **DataSourceUtils.getConnection(...)** có tham gia transaction do Spring quản lý, phải dùng cơ chế release phù hợp của Spring, **không tự gọi close() theo thói quen**. Tốt hơn, khi logic không có yêu cầu đặc biệt, dùng **JdbcTemplate** hoặc một lớp truy cập dữ liệu của Spring.

### 5.2. Khi dùng JdbcTemplate và @Transactional

Phần ghi một lô ở mục trước có thể triển khai như sau:

~~~java
@Service
public class ImportBatchService {

    private final JdbcTemplate jdbcTemplate;

    public ImportBatchService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void upsertChunk(List<String> externalIds) {
        jdbcTemplate.batchUpdate(
            "INSERT INTO imported_key (external_id) VALUES (?) "
            + "ON CONFLICT (external_id) DO NOTHING",
            externalIds,
            externalIds.size(),
            (statement, id) -> statement.setString(1, id)
        );
    }
}
~~~

Trong ví dụ này:

- **JdbcTemplate** quản lý việc mượn và giải phóng tài nguyên JDBC trong phạm vi gọi.
- **Transaction manager** quản lý transaction của **upsertChunk**; commit khi phương thức hoàn tất hoặc rollback khi lỗi được xem là nguyên nhân rollback theo cấu hình.
- Vì runner gọi **một service Spring khác** qua proxy, annotation **@Transactional** có hiệu lực theo cơ chế proxy thông thường. Gọi một phương thức @Transactional khác trên **this** trong cùng bean có thể không đi qua proxy.
- Câu **ON CONFLICT** trong ví dụ dành cho PostgreSQL; các hệ CSDL khác dùng cú pháp upsert tương ứng.

**Không đóng Connection bên trong phương thức @Transactional** nếu Connection thuộc sự quản lý của transaction manager. Đóng thủ công có thể phá giao dịch đang hoạt động hoặc gây lỗi khó theo dõi.

### 5.3. Ranh giới transaction và thời điểm đóng

Không mở một transaction lớn rồi vừa giữ kết nối vừa gọi API chậm, đọc hàng GB tệp và chờ các luồng xử lý. Tác vụ dễ làm nghẽn pool, giữ lock lâu và rollback quá nhiều dữ liệu khi gặp lỗi. Với nhập dữ liệu theo lô, thường nên:

- Đọc một nhóm bản ghi từ tệp.
- Chuyển nhóm đó tới service thực hiện transaction ngắn.
- Commit nhóm thành công rồi tiếp tục nhóm kế tiếp.
- Ghi checkpoint, khóa nghiệp vụ hoặc trạng thái nguồn để hỗ trợ chạy lại sau lỗi.

**Commit transaction** và **close Connection** không nhất thiết là cùng một thao tác. Với pool, Connection thường được trả về pool sau khi transaction hoặc truy vấn hoàn tất; bản thân pool vẫn sống để phục vụ các thành phần khác trong ApplicationContext.

## 6. Các tài nguyên dài hạn thuộc ApplicationContext

Một ứng dụng Spring Boot có thể tạo các bean như **DataSource**, **WebClient/HTTP client**, **Executor**, message producer, object-storage client hoặc cache client. Khi chúng dùng chung giữa nhiều service, nên đăng ký chúng thành **Spring bean** với cơ chế hủy phù hợp.

Ví dụ một client riêng có phương thức **close()**:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    public ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

Đây là ví dụ về **kiểu client giả định**: ExternalClient phải thật sự có phương thức close() phù hợp. Với thư viện cụ thể, xem hợp đồng lifecycle của client đó, đặc biệt khi thư viện tự quản connection pool. Spring cũng hỗ trợ các callback hủy bean như **@PreDestroy**, **DisposableBean** hoặc cơ chế **destroyMethod**.

Tài nguyên do Spring Boot tự cấu hình, chẳng hạn pool kết nối của một DataSource chuẩn, thường đã có lifecycle tương ứng. **Không tự đóng DataSource ở cuối ApplicationRunner**: Spring Cloud Task vẫn có thể cần truy cập TaskRepository để ghi nhận kết quả cuối cùng và đóng ApplicationContext đúng quy trình.

### Một mẫu main cho tác vụ chạy dạng tiến trình

~~~java
@SpringBootApplication
@EnableTask
public class FileImportTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(FileImportTaskApplication.class, args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
~~~

Ở đây **SpringApplication.exit(context)** kích hoạt quy trình đóng ApplicationContext và tính exit code dựa trên cơ chế **ExitCodeGenerator** được cấu hình; **System.exit** kết thúc JVM với mã đó. Với CLI/batch app, điều này giúp không để context và các luồng còn sống vô hạn. Nếu lỗi xảy ra ngay trong quá trình **SpringApplication.run(...)**, lời gọi sau đó không nhất thiết được thực thi; cơ chế báo lỗi lúc khởi động của Spring Boot phải được xử lý phù hợp. Trong bài kiểm thử, có thể kiểm tra runner/service riêng thay vì gọi **System.exit**.

**Lưu ý:** không gọi SpringApplication.exit() **trong từng service xử lý**; chỉ kết thúc context sau khi mọi công việc cần thiết đã được chờ và xác nhận. Nếu một bean có callback @PreDestroy cần tài nguyên của bean khác, tránh dựa vào thứ tự ngẫu nhiên; khai báo quan hệ phụ thuộc và thiết kế shutdown theo lifecycle của Spring.

## 7. Không để tác vụ kết thúc khi công việc bất đồng bộ còn chạy

Một lỗi khó phát hiện là runner khởi chạy xử lý nền nhưng không chờ:

~~~java
// Ví dụ sai về vòng đời tác vụ
@Override
public void run(ApplicationArguments args) {
    executor.execute(() -> importService.importAll());
    // run() kết thúc trước khi importAll() hoàn thành.
}
~~~

Khi runner trả về, Spring Cloud Task có thể ghi nhận phần thực thi chính là đã kết thúc trong khi tác dụng phụ còn xảy ra hoặc bị ngắt bởi shutdown. Log thành công và trạng thái TaskExecution không còn đáng tin.

### Chờ mọi tác vụ con và phát hiện lỗi

~~~java
@Override
public void run(ApplicationArguments args) {
    CompletableFuture<Void> first =
        CompletableFuture.runAsync(
            () -> importService.importPartition("A"), executor);

    CompletableFuture<Void> second =
        CompletableFuture.runAsync(
            () -> importService.importPartition("B"), executor);

    // Nếu một nhánh lỗi, join() ném CompletionException.
    CompletableFuture.allOf(first, second).join();
}
~~~

Có thể đăng ký executor do Spring quản lý:

~~~java
@Bean
public ThreadPoolTaskExecutor processingExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("task-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(60);
    return executor;
}
~~~

Hai lớp bảo vệ có mục đích khác nhau: **allOf(...).join()** giữ runner chờ công việc thực sự hoàn thành và truyền lỗi; **chính sách shutdown của executor** là phương án dự phòng khi context phải đóng. Không coi việc chờ tối đa 60 giây là đủ để xác nhận kết quả nghiệp vụ thành công.

Các transaction gắn với luồng thường **không tự truyền** sang luồng do executor chạy. Mỗi nhánh xử lý cần ranh giới transaction tại service được gọi trong chính luồng đó. Tương tự, ngữ cảnh log/MDC hoặc security context cần cơ chế truyền ngữ cảnh rõ ràng nếu nghiệp vụ yêu cầu.

Nếu tự tạo **ExecutorService** ngoài Spring, mã tạo nó phải có đường shutdown thích hợp (shutdown, awaitTermination có giới hạn, sau đó xử lý phần chưa hoàn tất). Không giả định JVM tự giải phóng worker thread tại thời điểm runner trả về.

## 8. HTTP, messaging, khóa và tài nguyên ngoài tiến trình

### 8.1. HTTP client và response

Trong một tác vụ đồng bộ dữ liệu, HTTP client có thể dùng connection pool tái sử dụng. Quy tắc thực hành:

- Đặt **connect timeout**, **response/read timeout** và giới hạn retry để tác vụ không chờ vô hạn.
- Đóng hoặc tiêu thụ response theo đúng hợp đồng thư viện, **kể cả HTTP 4xx/5xx**; tránh giữ socket vì bỏ qua error body.
- Nếu client được cấu hình thành bean dùng chung, giữ nó sống đến khi context shutdown.
- Kiểm soát retry bằng khóa nghiệp vụ/idempotency key vì việc đóng kết nối mạng không cho biết máy chủ bên kia đã xử lý yêu cầu hay chưa.

Ví dụ một request có thể timeout **sau khi** dịch vụ đối tác đã ghi dữ liệu. Chạy lại chỉ dựa vào TaskExecution ID có thể tạo bản ghi trùng ở đối tác. Đây là lý do cần khóa yêu cầu riêng và chính sách truy vấn trạng thái trước khi retry.

### 8.2. Message broker và acknowledgment

Một tác vụ đọc message và ghi database cần xác định thứ tự **xử lý → commit → acknowledgment** theo hợp đồng của broker và client. Nếu ack quá sớm, tác vụ chết có thể làm mất message; nếu ack sau commit, message có thể được phát lại, vì vậy bên tiêu thụ phải xử lý trùng an toàn. Sử dụng cơ chế transaction, outbox hoặc idempotent consumer theo yêu cầu thay vì chỉ dựa vào lệnh close().

Trước khi đóng producer, có thể cần **flush** các bản tin đã gửi bất đồng bộ và chờ xác nhận gửi thành công. Flush chỉ bảo đảm theo semantics của thư viện và broker, không thay thế đối soát kết quả nghiệp vụ.

### 8.3. Khóa phân tán và lease

Một tác vụ bảo trì thường dùng khóa để tránh hai instance dọn cùng dữ liệu. Đường đi bình thường là **nhả khóa trong finally**; tuy nhiên khi tiến trình bị kill hoặc máy chủ mất điện, finally không chạy. Vì vậy khóa cần có **TTL/lease**, gia hạn nếu tác vụ lâu, và quy tắc ownership khi nhả. Tác vụ tiếp quản phải kiểm tra dữ liệu đã xử lý và checkpoint, không tin rằng lần chạy trước luôn rollback hoàn toàn.

## 9. Xử lý lỗi khi giải phóng tài nguyên

Một tác vụ cần bảo toàn **nguyên nhân thất bại ban đầu**. Nếu phần xử lý chính lỗi, sau đó thao tác cleanup cũng lỗi, không nên vô tình thay exception chính bằng exception cleanup.

Với AutoCloseable, ưu tiên **try-with-resources** vì Java tự quản suppressed exceptions. Với tài nguyên phụ không áp dụng được, có thể dùng finally và ghi nhận lỗi bổ sung:

~~~java
Exception primary = null;

try {
    performWork();
} catch (Exception error) {
    primary = error;
    throw error;
} finally {
    try {
        deleteTemporaryScratchFiles();
    } catch (Exception cleanupError) {
        if (primary != null) {
            primary.addSuppressed(cleanupError);
        } else {
            throw cleanupError;
        }
    }
}
~~~

Đoạn này minh họa nguyên tắc với **Exception** thông thường; ở mã thật cần xem xét cả quy tắc cleanup khi có **Error**, interruption, và việc thao tác cleanup có đáng làm tác vụ thất bại hay không. Nếu cleanup là điều kiện bắt buộc (ví dụ phải đóng/ghi đầy đủ đầu ra để đảm bảo tính toàn vẹn), lỗi cleanup phải phản ánh vào trạng thái thất bại. Nếu chỉ là dọn tệp tạm có thể chạy lại, có thể ghi log và đưa vào hàng đợi dọn bù, nhưng phải tránh âm thầm che khuất rác tồn đọng.

Nên có **quy tắc phân loại rõ ràng**:

| Trạng thái | Ví dụ | Ứng xử |
| --- | --- | --- |
| Hoàn tất toàn bộ | Đã commit kết quả, đóng output và đối soát thành công | Báo thành công cho launcher |
| Lỗi nghiệp vụ | Dữ liệu sai định dạng, thiếu khóa bắt buộc | Không đánh dấu thành công; cung cấp nguyên nhân để sửa đầu vào |
| Lỗi tạm thời | Mất kết nối CSDL hoặc dịch vụ ngoài | Rollback phần chưa commit, trả lỗi để retry có giới hạn |
| Lỗi lúc đóng tài nguyên | Writer flush lỗi, HTTP response không thể đóng | Không mặc định bỏ qua; xác định tác động tới tính đúng đắn |
| Chết bất thường | SIGKILL, mất điện, container bị OOM | Không trông chờ finally/@PreDestroy; khôi phục dựa vào metadata, khóa và idempotency |

**Không** bắt mọi exception rồi chỉ log và return bình thường. Cách đó có thể khiến tiến trình và metadata biểu thị thành công dù công việc bị dở dang. Với lỗi được coi là thất bại của task, để exception đi tới cơ chế báo lỗi phù hợp hoặc cung cấp exit code thất bại qua quy trình chuẩn của ứng dụng.

## 10. Shutdown có kiểm soát trong container và khi chạy theo lịch

Khi tác vụ được chạy trong Kubernetes Job/CronJob hoặc một hệ điều phối khác, tiến trình có thể nhận tín hiệu dừng do hết hạn, triển khai lại hoặc người vận hành yêu cầu. Các giai đoạn điển hình gồm:

1. **SIGTERM** yêu cầu tiến trình kết thúc; nếu JVM và launcher nhận tín hiệu đúng cách, shutdown hook có cơ hội chạy.
2. Ứng dụng ngừng nhận công việc mới, chờ những thao tác đang xử lý trong giới hạn hợp lý, đóng bean và tài nguyên.
3. Nếu vượt quá thời gian chờ hoặc bị **SIGKILL**, tiến trình dừng tức thì; Java không được bảo đảm gọi finally, @PreDestroy hay listener nào.

Ví dụ cấu hình pod trong Job:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: one-off-import
spec:
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 90
      containers:
        - name: import-task
          image: registry.example/import-task:1.0.0
          args:
            - "--input=/data/orders.txt"
~~~

**terminationGracePeriodSeconds** là khoảng thời gian Kubernetes dành cho kết thúc bình thường trước khi cưỡng chế dừng; giá trị thực tế cần dựa trên transaction, batch size và thời gian đóng tài nguyên của tác vụ. Đặt quá ngắn sẽ làm tăng lượt xử lý dở dang; đặt quá dài có thể khiến quá trình thu hồi tài nguyên của cụm bị kéo dài. Đây chỉ là cấu hình minh họa: volume, secrets, giới hạn tài nguyên, chế độ chạy và quyền truy cập cần được bổ sung theo môi trường.

Đối với tác vụ chạy lâu, cần thêm:

- **Timeout** cấp tiến trình và cấp từng lời gọi I/O.
- **Checkpoint** hoặc khóa nghiệp vụ để chạy tiếp khi bị gián đoạn.
- **Giới hạn retry** và backoff để không gây bão kết nối hoặc ghi trùng.
- **Tệp tạm có tên riêng** theo mỗi lần thực thi; cơ chế dọn những tệp mồ côi dựa vào tuổi và ownership.
- **Quan sát trạng thái** ở cả TaskRepository và bộ điều phối; nếu START_TIME có mà END_TIME chưa có, cần xác minh tiến trình còn sống hay đã chết bất thường.

### Không dừng nguồn metadata quá sớm

Spring Cloud Task cần truy cập **TaskRepository** để ghi nhận lifecycle. Nếu code gọi đóng pool CSDL metadata ngay sau khi xử lý business data, quá trình ghi nhận kết thúc có thể thất bại. Hãy để Spring đóng DataSource ở giai đoạn destruction của ApplicationContext. Các callback kết thúc Task hoặc shutdown hook dùng để thông báo và cleanup bổ sung, không nên dùng thay cho cơ chế quản lý tài nguyên chính.

## 11. Mẫu thiết kế cho ba loại tác vụ phổ biến

| Loại tác vụ | Tài nguyên chính | Điểm đóng quan trọng | Quy tắc khi chạy lại |
| --- | --- | --- | --- |
| **Nhập dữ liệu** | Reader, parser, JDBC connection, file tạm | Đóng reader dù một batch lỗi; transaction hoàn tất từng chunk | Khóa nguồn và khóa bản ghi tránh nhập trùng |
| **Báo cáo** | ResultSet/stream dữ liệu, BufferedWriter, object-storage client | Đóng writer trước khi công bố; không để người dùng thấy tệp dở | Report key, version, checksum; không gửi thông báo trùng |
| **Bảo trì** | JDBC connection, cursor, lock/lease | Transaction ngắn, cursor được đóng, nhả lease theo ownership | Chỉ xử lý bản ghi còn thỏa cutoff hoặc checkpoint |

### Tình huống lỗi thực tế: nhập 10.000 bản ghi, chết ở lô thứ 31

Giả sử mỗi transaction ghi 250 bản ghi. Sau khi 30 lô hoàn tất, tiến trình chết khi đang xử lý lô thứ 31. Những lô đã commit vẫn nằm trong CSDL, lô chưa commit có thể rollback, còn metadata TaskExecution có thể chưa kịp cập nhật END_TIME. Để vận hành an toàn:

- Tệp gốc hoặc nguồn dữ liệu phải còn truy cập được khi chạy lại.
- Mỗi bản ghi có khóa nghiệp vụ duy nhất hoặc cơ chế upsert phù hợp.
- Dữ liệu được đối soát theo số bản ghi và mã nguồn; không coi “đã đọc hết tệp” là tương đương “đã ghi thành công”.
- Reader, transaction và executor có phạm vi ownership rõ ràng để lần chạy tiếp theo không phụ thuộc tài nguyên của tiến trình cũ.
- Nếu sử dụng Spring Batch, checkpoint/JobRepository hỗ trợ restart theo step/chunk; vẫn cần thiết kế idempotency cho tác dụng phụ bên ngoài transaction.

Ở đây **đóng tài nguyên** hỗ trợ vận hành đúng, nhưng **khôi phục an toàn** còn phụ thuộc transaction và thiết kế trạng thái nghiệp vụ. Không một khối finally nào tự đảm bảo khôi phục sau SIGKILL.

## 12. Quan sát và chẩn đoán rò rỉ tài nguyên

Một lượt chạy thành công về nghiệp vụ vẫn có thể để lại vấn đề tài nguyên cho lần chạy sau. Để tìm nguyên nhân, nên ghi nhận tối thiểu **task execution ID, business key, loại thao tác, số bản ghi, thời lượng, trạng thái và lỗi**; tránh đưa mật khẩu, token hoặc dữ liệu nhạy cảm vào log.

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Task chạy xong nhưng JVM không thoát | Thread pool tự tạo chưa shutdown, còn non-daemon thread | Dump luồng, danh sách bean/executor, nơi tạo luồng |
| Tác vụ chờ kết nối CSDL quá lâu | Connection leak, transaction dài, pool quá nhỏ | Active/idle/waiting của pool, timeout, lịch sử transaction |
| Không đổi tên/xóa được tệp | Reader, writer hoặc file stream còn mở | Kiểm tra mọi nhánh lỗi và try-with-resources |
| Báo cáo tải về bị thiếu | Công bố trước khi đóng writer hoặc đang ghi đè tệp | Thứ tự close → validate → publish, cơ chế version |
| TaskExecution thiếu END_TIME | Tiến trình còn chạy hoặc bị kill trước khi ghi cuối | Đối chiếu trạng thái pod/process và log, áp dụng chính sách timeout |
| Nhiều tệp .partial tồn đọng | Cleanup không chạy khi tiến trình chết | Quy trình dọn tệp tạm theo tuổi, kiểm tra tác vụ đang sở hữu |
| Log nói thành công nhưng dữ liệu thiếu | Bắt exception rồi bỏ qua, không chờ async future | Kiểm tra nhánh xử lý lỗi, join future và đối soát nghiệp vụ |

Với một tác vụ định kỳ, theo dõi xu hướng số connection, số thread, file descriptor và dung lượng thư mục tạm qua nhiều lượt chạy. Đặc biệt khi nhiều instance cùng dùng một pool hoặc hệ thống lưu trữ, cần quan sát theo instance và theo lần chạy để phân biệt rò rỉ thực sự với tăng tải hợp lệ.

## 13. Bài thực hành kiểm chứng

Xây dựng một Spring Cloud Task nhập tệp gồm 1.000 mã đơn hàng, ghi theo chunk vào PostgreSQL. Dùng **ApplicationRunner**, **try-with-resources**, **JdbcTemplate**, **@Transactional** trên service riêng và TaskRepository để quan sát lượt chạy.

Thực hiện các kịch bản theo thứ tự:

1. **Chạy bình thường:** tệp được đọc và đóng; tiến trình kết thúc; số bản ghi đúng; có bản ghi thực thi tương ứng.
2. **Tệp không tồn tại:** mở BufferedReader thất bại; tác vụ trả lỗi rõ ràng và không tạo kết quả thành công giả.
3. **Lỗi giữa chừng:** cố ý làm hỏng một dòng giữa các chunk; kiểm tra transaction của chunk lỗi rollback và chunk trước vẫn nhất quán; lần chạy lại không ghi trùng.
4. **Tệp đang được giữ mở:** mô phỏng một đường code quên đóng stream, so sánh với try-with-resources qua trạng thái file descriptor hoặc khả năng đổi tên/xóa tệp trên hệ điều hành.
5. **Xử lý bất đồng bộ:** thử không chờ Future, sau đó bổ sung **CompletableFuture.allOf(...).join()**; đối chiếu thời điểm trạng thái tác vụ với thời điểm dữ liệu được ghi xong.
6. **Dừng giữa chừng:** gửi tín hiệu kết thúc bình thường, rồi so sánh với cưỡng chế dừng; kiểm tra TaskRepository, log, dữ liệu đã commit và kế hoạch chạy lại.

**Tiêu chí đạt:** mỗi lượt có kết quả thành công/thất bại đúng với dữ liệu thực tế; tài nguyên cục bộ được đóng trên đường thành công và đường lỗi; ứng dụng không treo sau khi xử lý; lần chạy lại không tạo bản ghi trùng hoặc xuất bản tệp chưa hoàn chỉnh.

## 14. Checklist trước khi vận hành

| Câu hỏi | Tiêu chí hoàn tất |
| --- | --- |
| Có liệt kê mọi tài nguyên do tác vụ mở? | Biết rõ owner và thời điểm đóng của từng tài nguyên |
| Mọi InputStream, Reader, Writer, ResultSet/cursor có được giải phóng? | try-with-resources hoặc lifecycle tương đương |
| Connection có được trả về pool đúng cách? | Spring quản transaction/connection hoặc code JDBC dùng close đúng phạm vi |
| Tệp đầu ra có được công bố sau khi đóng? | Tệp tạm, kiểm tra kết quả và publish có kiểm soát |
| Tác vụ có chờ mọi xử lý async? | Không còn future chưa kiểm tra khi runner kết thúc |
| Có timeout và shutdown phù hợp? | Tác vụ có thể dừng trong cửa sổ vận hành bình thường |
| Có xử lý trường hợp bị kill mà không có finally? | Checkpoint, idempotency, TTL/lease, cleanup bù |
| Metadata TaskRepository có được ghi đến cuối lifecycle? | Pool/bean metadata không bị đóng thủ công quá sớm |
| Có thể chẩn đoán lỗi đóng tài nguyên? | Ghi nguyên nhân chính, suppressed exception, metric và log cần thiết |

### Ghi nhớ

Trong Spring Cloud Task, **kết thúc công việc** và **kết thúc tiến trình** phải được thiết kế cùng nhau. Tài nguyên cục bộ nên được đóng ở phạm vi nhỏ nhất bằng try-with-resources; kết nối/bean do Spring quản lý cần được để Spring đóng đúng vòng đời; các bước bất đồng bộ phải hoàn tất hoặc thất bại rõ ràng trước khi task báo kết quả. Khi kết hợp **TaskRepository, tham số chạy, xử lý lỗi, lịch chạy và Spring Batch**, việc giải phóng tài nguyên đúng cách giúp mỗi lần thực thi hữu hạn thực sự đáng tin cậy và có thể chạy lại an toàn.
