# Open và close resource

Trong Spring Batch, custom reader, writer hoặc tasklet thường phải mở và giải phóng resource như file, JDBC cursor, socket, stream hoặc kết nối tới dịch vụ bên ngoài. Việc mở resource đúng thời điểm giúp component có thể sử dụng dữ liệu trong Step; việc đóng resource đúng thời điểm giúp tránh rò rỉ file descriptor, connection pool exhaustion và dữ liệu chưa được flush.

Với component tham gia chunk processing, Spring Batch cung cấp lifecycle contract ItemStream gồm ba phương thức open, update và close. Component dùng open để mở resource và khôi phục state, update để lưu checkpoint vào ExecutionContext, còn close để giải phóng tài nguyên. Hiểu contract này là nền tảng khi viết custom reader/writer có state hoặc cần restart.

## 1. Vì sao resource lifecycle quan trọng?

Một resource thường có vòng đời dài hơn một lần gọi read hoặc write. Ví dụ, reader có thể mở một file ở đầu Step, đọc hàng nghìn dòng qua nhiều chunk rồi mới đóng file. Writer có thể giữ một output stream mở để tránh mở/đóng file liên tục cho từng item.

Nếu mở resource trong mỗi lần read/write, ứng dụng có thể tạo nhiều connection hoặc file handle không cần thiết. Nếu quên đóng resource khi Step kết thúc hoặc thất bại, tài nguyên có thể bị giữ lại cho đến khi process kết thúc.

Các loại resource thường gặp:

- File input/output và BufferedReader/BufferedWriter.
- JDBC Connection, Statement, ResultSet hoặc cursor.
- HTTP response body, stream hoặc socket.
- Reader/writer tới object storage hoặc hệ thống file từ xa.
- Native resource hoặc handle do thư viện bên thứ ba quản lý.

Resource lifecycle cần xử lý cả đường chạy thành công và các tình huống lỗi như exception giữa lúc mở, lỗi khi đọc/ghi, rollback, stop và restart.

## 2. Ba phương thức của ItemStream

ItemStream là contract của Spring Batch cho các component cần lifecycle và có thể lưu state:

~~~java
public interface ItemStream {

    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
~~~

Mỗi phương thức có một trách nhiệm riêng:

| Phương thức | Thời điểm và mục đích |
|---|---|
| open | Khi Step bắt đầu sử dụng stream; mở resource và khôi phục state đã lưu |
| update | Tại checkpoint; ghi state hiện tại vào ExecutionContext |
| close | Khi stream kết thúc; flush và giải phóng resource |

ItemStream không thay thế ItemReader hoặc ItemWriter. Nó bổ sung lifecycle cho component. Vì vậy, một custom reader có state thường triển khai ItemStreamReader, còn custom writer có state thường triển khai ItemStreamWriter.

~~~java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}

public interface ItemStreamWriter<T>
        extends ItemWriter<T>, ItemStream {
}
~~~

Nếu component không cần giữ resource qua nhiều lần gọi và không có state cần khôi phục, có thể dùng try-with-resources trong một phương thức xử lý ngắn. Không cần triển khai ItemStream cho mọi class chỉ vì class đó có sử dụng file hoặc connection.

## 3. Vòng đời của resource trong một Step

Trong chunk-oriented Step, Spring Batch quản lý lifecycle của các stream được đăng ký với Step. Một luồng khái quát:

~~~text
Step bắt đầu
    |
    v
ItemStream.open(ExecutionContext)
    |
    v
Đọc và xử lý chunk
    |
    +--> ItemStream.update(ExecutionContext)
    |          |
    |          v
    |      Commit chunk/checkpoint
    |
    +--> chunk tiếp theo
    |
    v
Step kết thúc hoặc thất bại
    |
    v
ItemStream.close()
~~~

Reader/writer có thể giữ file hoặc cursor mở trong nhiều chunk. Phương thức update được gọi để component ghi thông tin cần thiết cho lần restart tiếp theo. close được gọi khi lifecycle của Step kết thúc.

Thứ tự chi tiết và transaction synchronization phụ thuộc Step implementation và phiên bản Spring Batch. Điểm quan trọng là update thuộc lifecycle checkpoint của Step, còn close thuộc lifecycle giải phóng resource. Không dùng close để lưu checkpoint cuối cùng thay cho update.

## 4. Khi nào dùng ItemStream, khi nào dùng try-with-resources?

Chọn cơ chế theo thời gian sống của resource:

| Tình huống | Cách quản lý phù hợp |
|---|---|
| Reader mở file và đọc qua nhiều chunk | ItemStreamReader |
| Writer giữ output stream trong cả Step | ItemStreamWriter |
| JDBC cursor cần tồn tại xuyên suốt Step | Reader triển khai ItemStream |
| Tasklet mở file, đọc/ghi rồi đóng trong một lần execute | try-with-resources |
| Một service mở HTTP response và xử lý ngay trong một method | try-with-resources |
| Component cần lưu vị trí đọc để restart | ItemStream và ExecutionContext |
| Resource chỉ dùng trong một câu lệnh ngắn | API quản lý resource như JdbcTemplate |

Ví dụ tasklet xử lý file trong một lần gọi:

~~~java
public class ImportManifestTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        Path path = Path.of("/data/input/manifest.txt");

        try (BufferedReader reader =
                     Files.newBufferedReader(path, StandardCharsets.UTF_8)) {

            String firstLine = reader.readLine();
            // Xử lý nội dung manifest trong lần gọi này.
        }

        return RepeatStatus.FINISHED;
    }
}
~~~

Resource được đóng ngay cả khi xử lý ném exception. Nếu tasklet cần giữ resource qua nhiều lần gọi execute hoặc cần checkpoint giữa các lần gọi, hãy thiết kế lifecycle rõ ràng bằng ItemStream thay vì giữ một handle mở mà không có cơ chế khôi phục.

## 5. Custom reader triển khai ItemStreamReader

Một custom reader có thể mở file trong open, trả từng dòng trong read, lưu số dòng đã đọc trong update và đóng file trong close.

Ví dụ minh họa:

~~~java
public class LineItemReader
        implements ItemStreamReader<String> {

    private static final String LINE_COUNT_KEY =
            "lineItemReader.lineCount";

    private final Path inputPath;

    private BufferedReader reader;
    private long lineCount;

    public LineItemReader(Path inputPath) {
        this.inputPath = inputPath;
    }

    @Override
    public void open(ExecutionContext context) {
        try {
            reader = Files.newBufferedReader(
                    inputPath, StandardCharsets.UTF_8);

            lineCount = context.containsKey(LINE_COUNT_KEY)
                    ? context.getLong(LINE_COUNT_KEY)
                    : 0L;

            for (long skipped = 0; skipped < lineCount; skipped++) {
                if (reader.readLine() == null) {
                    throw new ItemStreamException(
                            "Checkpoint exceeds input file length");
                }
            }
        } catch (Exception exception) {
            try {
                closeQuietly();
            } catch (Exception closeException) {
                exception.addSuppressed(closeException);
            }
            throw new ItemStreamException(
                    "Cannot open input file: " + inputPath,
                    exception);
        }
    }

    @Override
    public String read() throws Exception {
        if (reader == null) {
            throw new IllegalStateException(
                    "Reader has not been opened");
        }

        String line = reader.readLine();
        if (line != null) {
            lineCount++;
        }
        return line;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LINE_COUNT_KEY, lineCount);
    }

    @Override
    public void close() {
        closeQuietly();
    }

    private void closeQuietly() {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException exception) {
                throw new ItemStreamException(
                        "Cannot close input file: " + inputPath,
                        exception);
            } finally {
                reader = null;
            }
        }
    }
}
~~~

Đây là ví dụ đơn giản để minh họa lifecycle. Với file rất lớn, việc bỏ qua lại từ đầu đến checkpoint có thể tốn thời gian. Có thể dùng byte offset, index, record key hoặc định dạng nguồn hỗ trợ seek để phục hồi nhanh hơn.

Tên key trong ExecutionContext phải ổn định qua các lần restart. Nếu reader có thể xuất hiện nhiều lần trong cùng Step hoặc nhiều instance cùng loại, hãy thêm định danh riêng để tránh các key bị ghi đè.

## 6. open phải khôi phục state và xử lý mở dở dang

open nhận ExecutionContext chứa state đã lưu ở checkpoint trước. Khi chạy lần đầu, context thường chưa có key của component. Khi restart, context có thể chứa vị trí đọc, last processed ID hoặc thông tin cần để mở resource đúng chỗ.

Trong open nên thực hiện theo thứ tự:

1. Kiểm tra cấu hình và resource path.
2. Đọc state cần khôi phục từ ExecutionContext.
3. Mở resource.
4. Đặt resource về vị trí đã lưu hoặc khôi phục cursor.
5. Kiểm tra resource có tương thích với checkpoint không.
6. Chỉ đánh dấu component sẵn sàng sau khi mọi bước thành công.

Nếu component mở nhiều resource và resource thứ hai lỗi, cần đóng resource thứ nhất trước khi ném exception. Không để một phần tài nguyên bị bỏ lại vì open chưa hoàn thành.

Ví dụ:

~~~java
@Override
public void open(ExecutionContext context) {
    try {
        input = Files.newInputStream(inputPath);
        index = Files.newBufferedReader(indexPath);
        restorePosition(context);
    } catch (Exception exception) {
        closeResourcesAfterOpenFailure();
        throw new ItemStreamException(
                "Cannot initialize reader resources", exception);
    }
}
~~~

Phương thức cleanup trong ví dụ phải an toàn khi một hoặc nhiều field vẫn null. Việc đóng resource nên có thể gọi nhiều lần mà không gây lỗi thứ cấp.

Không lưu một InputStream, Connection hoặc ResultSet trực tiếp trong ExecutionContext. Context dành cho state có thể serialize như số dòng, byte offset, last key hoặc tên file; resource handle phải được mở lại trong open.

## 7. update lưu checkpoint, không lưu resource handle

update nhận ExecutionContext để component lưu trạng thái cần thiết cho restart.

Ví dụ state có thể lưu:

- Số dòng đã đọc.
- Byte offset đã xử lý.
- ID cuối cùng đã đọc hoặc ghi.
- Trang hiện tại và sort key.
- Tên file, version hoặc checksum của input.
- Số record đã ghi và vị trí output.

Không lưu các đối tượng sau trong ExecutionContext:

- BufferedReader hoặc BufferedWriter.
- FileInputStream hoặc FileOutputStream.
- JDBC Connection, Statement hoặc ResultSet.
- Socket, HTTP response hoặc thread.
- Các object không serializable hoặc phụ thuộc process hiện tại.

ExecutionContext là metadata bền vững, không phải container giữ tài nguyên đang mở. Khi process dừng, handle cũ không còn dùng được; restart cần mở resource mới và khôi phục bằng state.

## 8. update và ranh giới commit của chunk

Trong chunk-oriented processing, update được gọi tại checkpoint của Step để lưu state của reader/writer. State này được persist cùng metadata StepExecution theo transaction semantics của JobRepository.

Ví dụ:

~~~text
Đã commit chunk 1:
  checkpoint = item 100

Đang xử lý chunk 2:
  đọc item 101..200
  ghi item 101..200
  update checkpoint = item 200
  commit

Nếu chunk 2 rollback:
  metadata checkpoint vẫn phải phản ánh điểm commit trước đó
  restart sẽ khôi phục từ checkpoint đã persist
~~~

Không cập nhật checkpoint bền vững cho item chưa được commit như thể item đó đã hoàn tất. Nếu checkpoint tiến xa hơn dữ liệu đích, restart có thể bỏ qua item chưa được ghi. Nếu checkpoint lùi quá xa, item đã commit có thể được xử lý lại; writer cần idempotency hoặc cơ chế chống trùng.

Đối với custom writer ghi ra filesystem, file và JobRepository không mặc nhiên tham gia cùng một transaction. Cần thiết kế thứ tự flush, lưu offset và phục hồi file để giảm nguy cơ checkpoint và file lệch nhau.

## 9. close giải phóng resource

close được gọi khi Step kết thúc lifecycle. Component nên:

- Flush dữ liệu còn trong buffer nếu contract yêu cầu.
- Đóng stream, reader, writer, cursor và statement do component sở hữu.
- Giải phóng lock hoặc handle.
- Xóa reference tới resource đã đóng.
- Đưa component về trạng thái không còn mở.
- Báo lỗi cleanup theo cơ chế exception của ItemStream.

close cần idempotent: gọi lần thứ hai không làm phát sinh lỗi vì resource đã được đóng hoặc field đã null. Đây là điều quan trọng vì cleanup có thể được gọi sau khi open chỉ thành công một phần.

Ví dụ:

~~~java
@Override
public void close() {
    if (reader == null) {
        return;
    }

    try {
        reader.close();
    } catch (IOException exception) {
        throw new ItemStreamException(
                "Failed to close reader", exception);
    } finally {
        reader = null;
    }
}
~~~

Nếu component sở hữu nhiều resource, hãy cố gắng đóng tất cả kể cả khi một thao tác close thất bại. Có thể lưu exception đầu tiên, tiếp tục đóng các resource còn lại, rồi ném exception tổng hợp hoặc gắn các lỗi sau làm suppressed exceptions.

Không nuốt mọi lỗi close. Một lỗi flush hoặc close có thể báo rằng dữ liệu chưa được ghi hoàn chỉnh. Cần log và để Step/Job phản ánh cleanup failure theo cách phù hợp.

## 10. Đóng resource theo thứ tự ngược

Khi mở nhiều resource phụ thuộc nhau, nên đóng theo thứ tự ngược với thứ tự mở.

Ví dụ:
1. Mở DataSource connection.
2. Tạo PreparedStatement.
3. Thực thi query và nhận ResultSet.

Khi đóng:
1. Đóng ResultSet.
2. Đóng Statement.
3. Trả Connection về pool hoặc giải phóng theo cơ chế sở hữu.

Với JDBC, nếu dùng JdbcTemplate hoặc API Spring quản lý connection, không tự đóng connection được transaction manager quản lý. Hãy dùng JdbcTemplate hoặc DataSourceUtils đúng cách để connection được release theo transaction synchronization.

Nếu custom component tự mở một connection độc lập để giữ cursor, component chịu trách nhiệm đóng statement/result set/connection của chính nó. Đừng nhầm connection độc lập với connection đang được transaction manager quản lý.

## 11. Custom writer triển khai ItemStreamWriter

Writer có thể giữ output resource mở trong suốt Step và lưu vị trí đã ghi để restart.

Ví dụ ghi từng dòng UTF-8 với byte offset:

~~~java
public class CheckpointLineWriter
        implements ItemStreamWriter<String> {

    private static final String OFFSET_KEY =
            "checkpointLineWriter.byteOffset";

    private final Path outputPath;

    private RandomAccessFile file;

    public CheckpointLineWriter(Path outputPath) {
        this.outputPath = outputPath;
    }

    @Override
    public void open(ExecutionContext context) {
        try {
            file = new RandomAccessFile(
                    outputPath.toFile(), "rw");

            long offset = context.containsKey(OFFSET_KEY)
                    ? context.getLong(OFFSET_KEY)
                    : 0L;

            if (offset > file.length()) {
                throw new ItemStreamException(
                        "Output file is shorter than saved checkpoint");
            }

            // Loại bỏ byte chưa được checkpoint ở lần chạy trước.
            file.setLength(offset);
            file.seek(offset);
        } catch (Exception exception) {
            try {
                closeQuietly();
            } catch (Exception closeException) {
                exception.addSuppressed(closeException);
            }
            throw new ItemStreamException(
                    "Cannot open output file: " + outputPath,
                    exception);
        }
    }

    @Override
    public void write(Chunk<? extends String> chunk)
            throws Exception {
        for (String item : chunk) {
            file.write(item.getBytes(StandardCharsets.UTF_8));
            file.write('\n');
        }
    }

    @Override
    public void update(ExecutionContext context) {
        try {
            file.getFD().sync();
            context.putLong(OFFSET_KEY, file.getFilePointer());
        } catch (IOException exception) {
            throw new ItemStreamException(
                    "Cannot save output checkpoint", exception);
        }
    }

    @Override
    public void close() {
        closeQuietly();
    }

    private void closeQuietly() {
        if (file != null) {
            try {
                file.close();
            } catch (IOException exception) {
                throw new ItemStreamException(
                        "Cannot close output file", exception);
            } finally {
                file = null;
            }
        }
    }
}
~~~

Ví dụ này dùng Spring Batch 5 với chữ ký write nhận Chunk. Ở các phiên bản cũ, ItemWriter có thể nhận List thay vì Chunk; hãy điều chỉnh method signature theo API của phiên bản dự án.

Ý tưởng checkpoint là lưu byte offset sau khi nội dung chunk đã được ghi và đồng bộ file. Khi restart, writer cắt bỏ phần byte vượt quá offset đã lưu rồi seek về đúng vị trí. Điều này giúp xử lý trường hợp file có dữ liệu ghi dở nhưng checkpoint database chưa commit.

Đây vẫn là ví dụ tối giản. Ứng dụng thật cần xử lý thư mục chưa tồn tại, header/footer, encoding newline, giới hạn kích thước, file locking, I/O exception và tính tương thích của output format.

## 12. Transaction của database không tự rollback filesystem

Một writer ghi file và một writer ghi database có thể cùng được gọi trong một chunk, nhưng file system không tự tham gia transaction JDBC.

Có thể xảy ra:

- File đã ghi chunk nhưng transaction database rollback.
- Database commit thành công nhưng process dừng trước khi hoàn tất file.
- File được flush nhưng metadata checkpoint không commit.
- Metadata đã commit nhưng dữ liệu file chưa được đồng bộ xuống storage bền vững.

Vì vậy, custom writer cần một chiến lược phục hồi phù hợp:
- Ghi file theo staging path ổn định.
- Lưu byte offset hoặc record key trong ExecutionContext.
- Flush/sync dữ liệu trước khi lưu checkpoint khi yêu cầu durability.
- Khi restart, truncate hoặc reconcile phần output chưa được checkpoint.
- Publish file sau khi Job hoàn tất và xác nhận kết quả.
- Dùng manifest, checksum và record count để đối soát.

Không tuyên bố file writer có transaction nguyên tử với database nếu ứng dụng không sử dụng một cơ chế distributed transaction thực sự hỗ trợ resource đó.

## 13. Đăng ký custom stream với Step

Spring Batch cần biết component nào có ItemStream lifecycle để gọi open, update và close.

Nếu custom reader được cấu hình trực tiếp qua reader(...) và triển khai ItemStreamReader, Step có thể nhận diện lifecycle của nó qua kiểu stream-aware.

Ví dụ:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        LineItemReader lineItemReader,
        ItemWriter<String> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<String, String>chunk(100, transactionManager)
            .reader(lineItemReader)
            .writer(writer)
            .build();
}
~~~

Nếu một stream không được nhận diện qua reader/writer chính, đăng ký rõ ràng bằng stream(...):

~~~java
return new StepBuilder("exportStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeWriter)
        .stream(auditFileWriter)
        .build();
~~~

Đây là trường hợp thường gặp với delegate hoặc resource phụ. Nếu stream không được đăng ký, framework có thể không gọi open/update/close cho nó. Job lần đầu có thể vẫn chạy nhưng restart không khôi phục state hoặc resource không được đóng đúng cách.

Không đăng ký cùng một stream lặp lại qua nhiều đường nếu không có chủ đích. Tránh việc cùng một instance nhận callback lifecycle nhiều lần ngoài mong đợi.

## 14. Delegate reader/writer và ItemStream

Một custom reader/writer có thể bọc một component khác. Ví dụ, CompositeItemWriter gọi nhiều writer con, hoặc reader lọc dữ liệu từ một delegate reader.

Nếu delegate triển khai ItemStream, wrapper cần chuyển tiếp lifecycle:

~~~java
public class AuditingReader<T>
        implements ItemStreamReader<T> {

    private final ItemStreamReader<T> delegate;

    public AuditingReader(ItemStreamReader<T> delegate) {
        this.delegate = delegate;
    }

    @Override
    public T read() throws Exception {
        T item = delegate.read();
        if (item != null) {
            // Ghi nhận audit metadata phù hợp.
        }
        return item;
    }

    @Override
    public void open(ExecutionContext context) {
        delegate.open(context);
    }

    @Override
    public void update(ExecutionContext context) {
        delegate.update(context);
    }

    @Override
    public void close() {
        delegate.close();
    }
}
~~~

Wrapper phải đảm bảo delegate nhận đúng ExecutionContext và lifecycle callback. Nếu wrapper chỉ triển khai ItemReader mà không chuyển tiếp ItemStream, Step có thể không biết delegate cần mở, lưu state hoặc đóng.

Với nhiều delegate, mỗi stream cần key state riêng. Tránh dùng chung key như currentPosition cho tất cả reader; key nên có prefix ổn định theo tên component.

## 15. Custom Tasklet và resource lifecycle

Tasklet thường phù hợp với một thao tác không cần reader/writer theo item. Nếu resource chỉ dùng trong một lần execute, dùng try-with-resources để đóng ngay trong phạm vi method.

~~~java
public class ArchiveTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        Path source = Path.of("/data/source.txt");
        Path archive = Path.of("/data/archive.txt");

        try (InputStream in = Files.newInputStream(source);
             OutputStream out = Files.newOutputStream(archive)) {
            in.transferTo(out);
        }

        return RepeatStatus.FINISHED;
    }
}
~~~

Nếu tasklet cần resource tồn tại qua nhiều lần gọi execute hoặc cần checkpoint, có thể triển khai ItemStream cùng Tasklet và bảo đảm stream được đăng ký với Step. Khi đó open/close quản lý resource, còn execute thực hiện từng đơn vị công việc.

Không giữ file handle hoặc connection trong static field hay singleton tasklet mà không có lifecycle rõ ràng. Một StepExecution khác có thể dùng cùng bean instance và truy cập nhầm resource.

## 16. Listener không thay thế ItemStream lifecycle

StepExecutionListener có beforeStep và afterStep; JobExecutionListener có beforeJob và afterJob. Các listener phù hợp cho logging, metrics, kiểm tra điều kiện hoặc thông báo nghiệp vụ.

Không nên dùng afterStep làm cơ chế chính để đóng reader/writer có state nếu component đã có ItemStream. ItemStream được thiết kế cho lifecycle của resource và checkpoint; listener có mục tiêu rộng hơn.

Ví dụ phân biệt:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Mở file reader trước khi đọc | ItemStream.open |
| Lưu vị trí đọc tại checkpoint | ItemStream.update |
| Đóng file reader sau Step | ItemStream.close |
| Ghi log thời gian Step | StepExecutionListener |
| Gửi notification sau Job | JobExecutionListener |
| Tạo metadata output dùng trong Step | Job listener hoặc Step listener tùy phạm vi |
| Resource chỉ sống trong một lần Tasklet.execute | try-with-resources |

Nếu listener mở resource, phải tự đảm bảo resource được đóng cả khi Step khởi chạy một phần rồi lỗi. Thông thường ItemStream rõ ràng và ít dễ bỏ sót hơn cho custom reader/writer.

## 17. JDBC resource và transaction-aware connection

Với JDBC, resource lifecycle phức tạp hơn file vì connection có thể do transaction manager quản lý.

Nếu dùng JdbcTemplate, Spring quản lý connection, statement và ResultSet theo phạm vi operation. Đây thường là lựa chọn đơn giản cho query ngắn.

Nếu custom component cần lấy connection trực tiếp và muốn tham gia transaction hiện tại, dùng DataSourceUtils:

~~~java
Connection connection =
        DataSourceUtils.getConnection(dataSource);

try {
    // Thực hiện JDBC work trên connection gắn với transaction hiện tại.
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

Không gọi connection.close() tùy tiện nếu connection được transaction manager bind vào thread. DataSourceUtils.releaseConnection sẽ tôn trọng transaction-bound connection và chỉ trả/đóng khi phù hợp.

Nếu reader cần cursor mở qua nhiều chunk và phải giữ connection lâu, hãy thiết kế rõ connection thuộc reader hay transaction. Có thể cần connection riêng và lifecycle ItemStream. Không giữ một transaction database mở trong suốt toàn bộ Job chỉ để giữ cursor nếu yêu cầu không đòi hỏi điều đó.

Đối với ResultSet và Statement do custom component tạo, luôn đóng chúng trong close theo thứ tự ngược với thứ tự mở. Nếu dùng JdbcTemplate, không đóng resource do JdbcTemplate quản lý.

## 18. Exception safety khi mở và đóng nhiều resource

Một component có thể mở nhiều tài nguyên liên tiếp. Nếu một bước giữa chừng thất bại, các tài nguyên đã mở cần được đóng.

Ví dụ:
- Mở file input.
- Mở file output.
- Khởi tạo parser.
- Kết nối dịch vụ ngoài.

Nếu khởi tạo parser lỗi, file input/output đã mở phải được giải phóng. Hãy viết cleanup chịu được trạng thái khởi tạo một phần.

Khi close nhiều resource, không dừng ngay ở lỗi đầu tiên nếu còn tài nguyên khác cần đóng. Mẫu xử lý:

~~~java
@Override
public void close() {
    RuntimeException failure = null;

    try {
        closeInput();
    } catch (RuntimeException exception) {
        failure = exception;
    }

    try {
        closeOutput();
    } catch (RuntimeException exception) {
        if (failure == null) {
            failure = exception;
        } else {
            failure.addSuppressed(exception);
        }
    }

    if (failure != null) {
        throw failure;
    }
}
~~~

Mẫu trên minh họa việc cố gắng đóng cả hai resource. Trong ItemStream implementation, có thể chuyển lỗi cuối thành ItemStreamException. Hãy giữ exception gốc để log và chẩn đoán.

Không bỏ qua exception trong close chỉ để Job hiển thị COMPLETED. Nếu flush/close thất bại, output có thể chưa hoàn chỉnh.

## 19. Resource cleanup khi Step thất bại hoặc bị stop

Step có thể kết thúc bằng COMPLETED, FAILED hoặc STOPPED. Resource phải được giải phóng trong mọi trường hợp mà framework kết thúc lifecycle của Step.

Một số tình huống cần chú ý:
- Reader mở thành công nhưng processor ném exception.
- Writer ném IOException giữa chunk.
- Database deadlock làm transaction rollback.
- Người vận hành yêu cầu stop.
- Job bị restart sau một execution thất bại.
- Một resource mở thành công nhưng resource tiếp theo không mở được.

close không nên giả định mọi field đã được khởi tạo đầy đủ. open có thể thất bại ở giữa; close cần kiểm tra null hoặc trạng thái resource trước khi đóng.

Process bị kill -9, mất điện hoặc JVM crash không bảo đảm callback close sẽ chạy. Vì vậy, cần thêm timeout, connection leak detection, file staging và cơ chế phục hồi khi process khởi động lại. Không dựa vào close như cách duy nhất bảo vệ dữ liệu bền vững.

## 20. Không giữ resource trong ExecutionContext

ExecutionContext được lưu trong JobRepository và có thể được serialize. Chỉ lưu state cần thiết để mở lại resource, không lưu chính resource.

Ví dụ phù hợp:

~~~java
context.putString("input.path", inputPath.toString());
context.putLong("input.lastLine", lastLine);
context.putLong("output.byteOffset", outputOffset);
context.putString("input.version", checksum);
~~~

Ví dụ không phù hợp:
- context.put("reader", bufferedReader)
- context.put("connection", jdbcConnection)
- context.put("resultSet", resultSet)
- context.put("socket", socket)

Các object này gắn với process, thread hoặc session hiện tại. Chúng không thể được tái sử dụng sau restart và thường không serialize được.

Nếu đường dẫn hoặc version input ảnh hưởng tới kết quả, hãy lưu hoặc xác minh chúng để tránh restart với một resource khác nội dung.

## 21. Thread safety và nhiều StepExecution

Step-scoped component thường có target riêng cho từng StepExecution, nhưng điều đó không có nghĩa mọi truy cập đều đơn luồng. Multi-threaded Step có thể gọi cùng một reader/writer instance từ nhiều thread trong một StepExecution, tùy cấu hình.

Khi resource không thread-safe:
- Không chia sẻ BufferedReader hoặc ResultSet giữa nhiều thread nếu implementation không hỗ trợ.
- Dùng partitioning với resource và checkpoint riêng cho mỗi worker khi phù hợp.
- Đồng bộ các thao tác chỉ khi có lý do và đo được tác động.
- Không dùng static resource handle.
- Không cho hai writer cùng ghi một file nếu không có coordination rõ ràng.

Nếu component được dùng bởi nhiều StepExecution đồng thời, cần bảo đảm mỗi execution có resource độc lập hoặc cơ chế pool/thread-safe phù hợp.

## 22. Kiểm thử lifecycle của custom component

Nên kiểm thử riêng ba callback và cả hành vi tích hợp trong Step.

Unit test có thể xác nhận:
- open mở resource và khôi phục state.
- read/write sử dụng resource đang mở.
- update ghi đúng checkpoint.
- close giải phóng resource.
- close gọi nhiều lần không gây lỗi.
- open lỗi giữa chừng vẫn cleanup resource đã mở.
- read/write sau close hoặc trước open được xử lý rõ ràng.

Integration test với Spring Batch nên xác nhận framework gọi đúng lifecycle:

| Kịch bản | Điều cần xác nhận |
|---|---|
| Step thành công | open, update tại checkpoint và close được gọi |
| Step thất bại | Resource được đóng khi framework kết thúc Step |
| Restart | open nhận ExecutionContext đã lưu và khôi phục vị trí |
| Chunk rollback | Checkpoint không vượt quá dữ liệu đã commit |
| Stream delegate | Delegate nhận đủ open/update/close |
| Resource thứ hai lỗi khi open | Resource thứ nhất được đóng |
| close ném exception | Lỗi cleanup được quan sát |
| Stop Step | Resource được giải phóng theo lifecycle |
| Nhiều StepExecution | Không chia sẻ nhầm resource hoặc state |
| Process crash | Restart phục hồi từ metadata và resource bền vững |

Có thể dùng mock hoặc fake resource để kiểm tra thứ tự callback. Với JDBC, cần integration test trên database/driver phù hợp để xác nhận connection được trả về pool và cursor được đóng.

## 23. Quan sát resource trong vận hành

Resource leak có thể không xuất hiện ngay trong một lần chạy nhỏ. Nên theo dõi:

- Số connection active/idle/pending trong pool.
- Thời gian connection được giữ.
- Số file descriptor hoặc handle đang mở.
- Thời gian mở cursor và số cursor hoạt động.
- Số lần open/close của custom stream.
- Số lỗi I/O, flush hoặc cleanup.
- JobExecution/StepExecution kết thúc nhưng resource vẫn còn được giữ.

Log nên bao gồm JobExecution ID, Step name, component name và loại resource. Không ghi credential, token hoặc nội dung dữ liệu nhạy cảm.

Với custom stream, có thể thêm log debug ở open/close và metric đếm resource đang mở. Metric cần tránh tag có cardinality cao như từng item ID hoặc đường dẫn đầy đủ của mỗi lần chạy.

## 24. Lỗi thường gặp

**Mở resource trong mỗi lần read/write.** Gây overhead và có thể tạo quá nhiều connection hoặc file handle.

**Quên triển khai ItemStream cho component có state.** Không có lifecycle checkpoint rõ ràng và restart khó tin cậy.

**Không đăng ký delegate stream.** Spring Batch không gọi open/update/close cho resource ẩn bên trong wrapper.

**Chỉ đóng resource trong nhánh thành công.** Exception có thể làm rò rỉ connection hoặc file handle.

**close không idempotent.** Cleanup lần hai có thể ném exception không cần thiết.

**Lưu Connection hoặc stream vào ExecutionContext.** Resource handle không thể phục hồi sau process restart.

**Lưu checkpoint quá sớm.** Metadata có thể vượt trước dữ liệu đã commit và làm mất item khi restart.

**Không flush trước khi lưu byte offset.** Checkpoint có thể trỏ tới byte chưa được ghi bền vững.

**Tự đóng connection do transaction manager quản lý.** Có thể làm transaction hiện tại hỏng hoặc connection bị trả pool quá sớm.

**Dùng listener thay cho ItemStream.** Resource lifecycle và checkpoint bị tách khỏi component thực sự sở hữu resource.

**Giả định close chạy sau JVM crash.** Process bị kill đột ngột có thể không gọi callback.

**Chia sẻ resource mutable giữa các thread.** Có thể gây race condition, dữ liệu sai hoặc lỗi driver.

## 25. Quy trình triển khai open và close resource

Khi xây dựng custom reader/writer, hãy thực hiện theo trình tự:

1. Xác định resource sống trong một method, một chunk hay toàn Step.
2. Dùng try-with-resources cho resource chỉ cần trong một method.
3. Dùng ItemStreamReader/ItemStreamWriter nếu component giữ resource hoặc checkpoint qua nhiều chunk.
4. Mở resource trong open và khôi phục state từ ExecutionContext.
5. Lưu state nhỏ, ổn định trong update tại checkpoint.
6. Đóng mọi resource do component sở hữu trong close.
7. Làm close idempotent và cleanup được cả khi open thất bại một phần.
8. Đăng ký các delegate stream với Step để framework gọi lifecycle.
9. Dùng API Spring transaction-aware cho JDBC connection; không tự đóng connection đang được transaction manager quản lý.
10. Giữ file/resource ổn định qua restart và thiết kế cách reconcile dữ liệu ngoài transaction.
11. Kiểm thử success, failure, rollback, stop, restart và process interruption.
12. Theo dõi resource pool, handle, cursor và cleanup error trong production.

open, update và close tạo nên hợp đồng lifecycle cho custom component có state trong Spring Batch. open chuẩn bị resource và khôi phục checkpoint; update lưu tiến độ ở ranh giới checkpoint; close giải phóng tài nguyên. Khi component sở hữu resource được đăng ký đúng với Step, cleanup an toàn và state được lưu nhất quán, Job có thể xử lý dữ liệu qua nhiều chunk, phục hồi sau lỗi và tránh rò rỉ tài nguyên.

