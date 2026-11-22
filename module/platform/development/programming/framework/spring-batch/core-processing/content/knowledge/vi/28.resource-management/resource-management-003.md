# Đóng resource khi Job thất bại trong Spring Batch

Một Job Spring Batch thường làm việc với nhiều tài nguyên bên ngoài: file, cursor database, stream, kết nối, message consumer, temporary file, lock hoặc client gọi dịch vụ từ xa. Những tài nguyên này cần được giải phóng đúng lúc, kể cả khi Step gặp exception và Job kết thúc ở trạng thái FAILED.

Đóng resource là một phần của quản lý vòng đời thực thi. Spring Batch hỗ trợ giao diện **ItemStream** với các callback open, update và close để quản lý reader, writer và các thành phần có trạng thái. Với tài nguyên chỉ tồn tại trong một lần gọi, Java cung cấp try-with-resources. Với tài nguyên ở phạm vi Step hoặc Job, có thể dùng listener hoặc cơ chế lifecycle phù hợp.

Cần phân biệt ba việc: **rollback transaction**, **đóng resource** và **dọn dữ liệu tạm**. Rollback hoàn tác thay đổi của transaction hiện tại; close giải phóng handle hoặc kết nối; cleanup xóa, cách ly hoặc thu hồi tài nguyên đã tạo. Một thao tác không tự động thay thế hai thao tác còn lại.

Bài học này trình bày vòng đời resource khi Step thành công hoặc thất bại, cách dùng ItemStream và listener, cách đóng tài nguyên khi khởi tạo dở dang, cách xử lý file đầu ra chưa hoàn chỉnh, và cách bảo vệ ứng dụng khi tiến trình bị dừng đột ngột.

## 1. Vì sao phải đóng resource khi Job thất bại?

Một resource thường chiếm tài nguyên của JVM, operating system hoặc hệ thống bên ngoài. Nếu không đóng đúng lúc, ứng dụng có thể gặp:

- File bị giữ handle nên không thể đổi tên, xóa hoặc đọc từ tiến trình khác.
- JDBC cursor, statement hoặc connection bị giữ lâu hơn cần thiết.
- HTTP response body hoặc stream không được đóng khiến connection pool cạn.
- Message consumer hoặc subscription vẫn giữ tài nguyên sau khi Step kết thúc.
- Temporary file, lock hoặc lease bị bỏ lại.
- Buffer chưa flush làm file đầu ra thiếu dữ liệu.
- Worker giữ tài nguyên trong lúc Job đã FAILED, khiến lần chạy sau không thể tiếp tục.

Ví dụ, một reader mở file CSV ở đầu Step. Trong lúc đọc, processor ném exception không thể phục hồi. Spring Batch đánh dấu Step thất bại. Nếu reader không được đóng, file handle có thể tiếp tục tồn tại cho đến khi garbage collection hoặc process kết thúc; thời điểm này không đủ tin cậy cho quy trình batch.

Quản lý resource tốt giúp:

1. Giải phóng tài nguyên ngay khi phạm vi sử dụng kết thúc.
2. Tránh rò rỉ file descriptor, connection và buffer.
3. Giúp restart hoặc rerun không bị khóa bởi tài nguyên cũ.
4. Giữ trạng thái file tạm và file chính thức rõ ràng.
5. Làm cho failure path có thể dự đoán và kiểm thử.

## 2. Phân biệt close, rollback và cleanup

Ba thao tác thường cùng xuất hiện khi Job thất bại nhưng có ý nghĩa khác nhau.

| Thao tác | Mục đích | Ví dụ |
|---|---|---|
| Rollback | Hoàn tác thay đổi trong transaction hiện tại | Hoàn tác các insert của chunk chưa commit |
| Close | Giải phóng resource đang mở | Đóng BufferedReader, cursor hoặc response body |
| Cleanup | Xử lý tài nguyên hoặc dữ liệu tạm đã tạo | Xóa file tạm hoặc chuyển file lỗi vào thư mục quarantine |

Ví dụ một Step đọc file, ghi database và tạo file báo cáo:

- Khi writer thất bại, transaction database có thể rollback.
- Reader và writer phải đóng file hoặc cursor đang mở.
- File báo cáo chưa hoàn chỉnh cần được xóa hoặc cách ly theo chính sách.
- Nếu Step trước đã commit dữ liệu, rollback của Step hiện tại không xóa dữ liệu đó.

Rollback không tự đóng mọi file handle. Close không tự rollback database. Close file cũng không tự xóa file đó.

~~~mermaid
flowchart TD
    A["Job hoặc Step gặp lỗi"] --> B["Rollback transaction hiện tại"]
    A --> C["Đóng resource đang mở"]
    A --> D["Xử lý file tạm, lock và lease"]
    B --> E["Dữ liệu transaction được hoàn tác"]
    C --> F["Handle và connection được giải phóng"]
    D --> G["Xóa, quarantine hoặc thu hồi"]
~~~

Thiết kế failure handling cần quyết định riêng cả ba nhánh.

## 3. Vòng đời ItemStream

Spring Batch cung cấp giao diện ItemStream cho thành phần cần quản lý trạng thái và resource trong Step:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

Trong thực tế, các phương thức có thể khai báo ném ItemStreamException.

Ý nghĩa:

- **open:** mở resource và khôi phục trạng thái từ ExecutionContext nếu đây là lần restart.
- **update:** lưu checkpoint hoặc trạng thái cần khôi phục.
- **close:** giải phóng resource khi Step kết thúc.

Reader và writer có state thường triển khai các interface kết hợp như ItemStreamReader hoặc ItemStreamWriter.

~~~java
public interface ItemStreamReader<T>
        extends ItemReader<T>, ItemStream {
}
~~~

Một số reader/writer có sẵn của Spring Batch, chẳng hạn FlatFileItemReader và JdbcCursorItemReader, đã quản lý vòng đời resource. Khi được cấu hình và đăng ký đúng với Step, framework gọi các callback tương ứng.

### Close được gọi khi Step thất bại?

Trong vòng đời thực thi bình thường của Step, Spring Batch đóng các ItemStream đã được đăng ký khi Step hoàn tất, bao gồm đường đi kết thúc do exception. Điều này cho phép reader/writer giải phóng resource sau khi Step thất bại.

Tuy vậy, không được hiểu đây là bảo đảm cho mọi kiểu sự cố. Nếu JVM bị kill -9, máy bị mất điện, container bị terminate cưỡng bức hoặc process crash trước khi lifecycle hoàn tất, callback close có thể không được chạy. Resource bên ngoài cần thêm lease, timeout hoặc cơ chế recovery.

Ngoài ra, nếu một resource được mở ngoài lifecycle của Step, framework không tự biết để đóng nó. Hãy quản lý rõ resource đó bằng try-with-resources, ItemStream hoặc listener phù hợp.

## 4. Reader tự quản lý resource bằng ItemStreamReader

Khi tự viết reader mở file hoặc stream, nên triển khai ItemStreamReader để Spring Batch quản lý open, update và close.

Ví dụ reader đọc file văn bản và lưu số dòng đã đọc:

~~~java
public class ManagedLineReader implements ItemStreamReader<String> {

    private final Path path;
    private BufferedReader reader;
    private long lineNumber;

    public ManagedLineReader(Path path) {
        this.path = path;
    }

    @Override
    public void open(ExecutionContext context) {
        try {
            reader = Files.newBufferedReader(
                path,
                StandardCharsets.UTF_8
            );

            lineNumber = context.getLong("managedLineReader.line", 0L);

            for (long i = 0; i < lineNumber; i++) {
                if (reader.readLine() == null) {
                    break;
                }
            }
        } catch (IOException ex) {
            closeAfterOpenFailure();
            throw new ItemStreamException(
                "Không thể mở hoặc khôi phục reader",
                ex
            );
        }
    }

    @Override
    public String read() throws Exception {
        if (reader == null) {
            throw new IllegalStateException("Reader chưa được mở");
        }

        String line = reader.readLine();
        if (line != null) {
            lineNumber++;
        }
        return line;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("managedLineReader.line", lineNumber);
    }

    @Override
    public void close() {
        BufferedReader current = reader;
        reader = null;

        if (current != null) {
            try {
                current.close();
            } catch (IOException ex) {
                throw new ItemStreamException(
                    "Không thể đóng reader",
                    ex
                );
            }
        }
    }

    private void closeAfterOpenFailure() {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException ignored) {
                // Giữ nguyên exception khởi tạo ban đầu.
            } finally {
                reader = null;
            }
        }
    }
}
~~~

Ví dụ minh họa cách lưu checkpoint theo số dòng. Với file lớn, việc đọc bỏ qua từ đầu đến checkpoint có thể tốn thời gian; reader thực tế có thể dùng offset, index hoặc cơ chế seek phù hợp.

### Vì sao close đặt reader về null trước khi đóng?

Đặt field về null trước khi gọi close giúp phương thức có tính idempotent hơn: nếu cleanup được gọi lần nữa, reader không còn được xem là resource đang mở. Đây là một mẫu hữu ích cho resource lifecycle.

Tùy yêu cầu, ứng dụng có thể lưu exception đóng resource vào log hoặc gắn nó với lỗi chính. Không nên làm mất exception ban đầu chỉ vì close cũng thất bại.

## 5. Khởi tạo resource dở dang phải tự cleanup

Một lỗi dễ bỏ sót xảy ra khi open() mở nhiều resource nhưng thất bại giữa chừng.

Ví dụ:

1. Mở file input thành công.
2. Tạo buffer hoặc temporary output.
3. Mở thêm một stream phụ.
4. Bước thứ ba thất bại.

Nếu open() ném exception ngay mà không đóng các resource đã mở ở bước trước, framework có thể không có đủ thông tin để cleanup một đối tượng chưa hoàn tất quá trình khởi tạo.

Hãy bảo đảm chính phương thức open() dọn các resource đã tạo nếu quá trình mở không hoàn tất.

~~~java
@Override
public void open(ExecutionContext context) {
    try {
        input = Files.newInputStream(inputPath);
        output = Files.newOutputStream(
            temporaryOutput,
            StandardOpenOption.CREATE,
            StandardOpenOption.TRUNCATE_EXISTING
        );
        writer = new BufferedWriter(
            new OutputStreamWriter(output, StandardCharsets.UTF_8)
        );
    } catch (IOException ex) {
        closeQuietly();
        throw new ItemStreamException(
            "Không thể khởi tạo resource cho Step",
            ex
        );
    }
}
~~~

Helper closeQuietly cần đóng từng resource còn tồn tại và đặt field về null trong finally. Nếu có nhiều resource phụ thuộc nhau, đóng theo thứ tự ngược với thứ tự mở.

Nguyên tắc này tương tự try-with-resources: resource đã mở phải được giải phóng ngay cả khi việc khởi tạo phần còn lại thất bại.

## 6. Đăng ký ItemStream với Step

Spring Batch tự quản lý reader hoặc writer được cấu hình trực tiếp nếu đối tượng đó triển khai ItemStream. Tuy nhiên, một resource phụ hoặc delegate lồng bên trong custom component có thể không được framework nhìn thấy.

Ví dụ Step có reader, writer và một stream phụ:

~~~java
@Bean
Step exportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemWriter<Customer> customerWriter,
        ItemStream auditStream) {

    return new StepBuilder("exportStep", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .writer(customerWriter)
        .stream(auditStream)
        .build();
}
~~~

Phương thức stream(...) đăng ký thêm ItemStream để Step gọi lifecycle của nó.

### Composite reader hoặc writer

Nếu một custom composite chứa delegate mở resource, composite cần chuyển tiếp open, update và close đến delegate, hoặc đăng ký delegate riêng với Step bằng stream(...).

Nếu quên đăng ký:

- Step có thể đọc/ghi được nhưng delegate không được close đúng lifecycle.
- Checkpoint có thể không được lưu.
- Restart có thể mở resource từ đầu hoặc không khôi phục đúng vị trí.
- Resource có thể còn mở sau khi Step kết thúc.

Hãy kiểm tra hợp đồng của composite đang dùng. Một số composite có sẵn đã quản lý ItemStream delegate; custom composite cần tự triển khai hoặc đăng ký các stream phù hợp.

## 7. Close resource của writer

Writer có thể giữ file handle hoặc buffer trong suốt Step. Nếu writer tự triển khai ItemStreamWriter, close() là nơi flush và đóng stream.

Ví dụ writer file:

~~~java
public class ManagedCsvWriter implements ItemStreamWriter<Customer> {

    private final Path outputPath;
    private BufferedWriter writer;

    public ManagedCsvWriter(Path outputPath) {
        this.outputPath = outputPath;
    }

    @Override
    public void open(ExecutionContext context) {
        try {
            writer = Files.newBufferedWriter(
                outputPath,
                StandardCharsets.UTF_8,
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND
            );
        } catch (IOException ex) {
            throw new ItemStreamException(
                "Không thể mở file output",
                ex
            );
        }
    }

    @Override
    public void write(Chunk<? extends Customer> chunk)
            throws Exception {
        if (writer == null) {
            throw new IllegalStateException("Writer chưa được mở");
        }

        for (Customer customer : chunk.getItems()) {
            writer.write(customer.customerId());
            writer.write(",");
            writer.write(customer.fullName());
            writer.newLine();
        }
    }

    @Override
    public void update(ExecutionContext context) {
        // Có thể lưu vị trí hoặc trạng thái cần khôi phục.
    }

    @Override
    public void close() {
        BufferedWriter current = writer;
        writer = null;

        if (current != null) {
            try {
                current.flush();
                current.close();
            } catch (IOException ex) {
                throw new ItemStreamException(
                    "Không thể flush hoặc đóng file output",
                    ex
                );
            }
        }
    }
}
~~~

Đây là ví dụ tối giản về lifecycle. Writer production cần cân nhắc checkpoint, append/truncate khi restart, header, encoding, atomic publish và hành vi khi close thất bại.

### Close có thể flush dữ liệu chưa commit

File writer không tham gia transaction database theo mặc định. Khi close gọi flush, nội dung buffer có thể được ghi xuống file dù chunk database bị rollback. Vì vậy, file output không tự đồng bộ transaction với database.

Nếu file chỉ được công bố khi Job thành công, hãy ghi vào file tạm riêng và chỉ publish sau khi toàn bộ bước tạo file đã hoàn tất. Không dựa vào close để quyết định file có hợp lệ hay không.

## 8. Dùng try-with-resources trong Tasklet

Với resource chỉ cần trong một lần gọi Tasklet, try-with-resources thường đơn giản và an toàn hơn giữ field để đóng ở listener.

Ví dụ đọc file trong Tasklet:

~~~java
@Bean
Tasklet validateFileTasklet() {
    return (contribution, chunkContext) -> {
        Path input = Path.of("/data/in/customers.csv");

        try (BufferedReader reader = Files.newBufferedReader(
                input,
                StandardCharsets.UTF_8)) {

            String line;
            while ((line = reader.readLine()) != null) {
                validate(line);
            }
        }

        return RepeatStatus.FINISHED;
    };
}
~~~

Dù validate() ném exception, Java vẫn đóng BufferedReader trước khi exception thoát khỏi Tasklet. Spring Batch sau đó xử lý transaction và trạng thái Step theo exception.

### Không giữ resource cục bộ qua nhiều lần execute

Tasklet có thể được gọi lặp lại nếu trả RepeatStatus.CONTINUABLE. Nếu mỗi lần execute mở resource, hãy đóng resource trong chính lần gọi đó. Không mở file ở lần đầu rồi giả định nó chỉ được gọi một lần, trừ khi lifecycle được thiết kế rõ.

Nếu resource cần tồn tại trong toàn bộ Step và cần checkpoint, dùng ItemStream hoặc một cơ chế lifecycle phù hợp thay vì giữ file handle trong biến cục bộ không thể khôi phục.

## 9. Dùng StepExecutionListener cho cleanup riêng của Step

StepExecutionListener cung cấp callback trước và sau Step:

~~~java
public interface StepExecutionListener extends StepListener {
    void beforeStep(StepExecution stepExecution);
    ExitStatus afterStep(StepExecution stepExecution);
}
~~~

afterStep được gọi khi Step kết thúc theo lifecycle thông thường. Có thể dùng nó để ghi thống kê, giải phóng một resource phụ không được mô hình hóa thành ItemStream hoặc thực hiện cleanup nhẹ.

Ví dụ:

~~~java
@Bean
StepExecutionListener temporaryDirectoryListener() {
    return new StepExecutionListener() {

        @Override
        public void beforeStep(StepExecution stepExecution) {
            // Tạo hoặc xác định thư mục làm việc của Step.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            Path workDirectory = resolveWorkDirectory(stepExecution);

            try {
                cleanupEmptyTemporaryFiles(workDirectory);
            } catch (IOException ex) {
                log.error(
                    "Không thể cleanup thư mục Step {}",
                    stepExecution.getStepName(),
                    ex
                );
            }

            return null;
        }
    };
}
~~~

Gắn listener:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .listener(temporaryDirectoryListener)
    .build();
~~~

### Khi nào nên dùng ItemStream thay vì listener?

Nếu resource là reader/writer có open, checkpoint và close, ItemStream thường phù hợp hơn vì lifecycle của resource được gắn trực tiếp với Step.

Listener phù hợp với hành động phụ thuộc trạng thái Step hoặc công việc cleanup không cần checkpoint. Tránh dùng listener để thay thế lifecycle của reader/writer khi framework đã có ItemStream.

afterStep không nên trở thành nơi thực hiện công việc nghiệp vụ quan trọng mà Job cần restart. Nếu bước publish hoặc cleanup là một phần bắt buộc của quy trình, hãy biểu diễn nó thành Step riêng để JobRepository theo dõi.

## 10. Cleanup ở cấp Job bằng JobExecutionListener

Một Job có thể tạo tài nguyên dùng chung qua nhiều Step, chẳng hạn thư mục tạm hoặc một lease điều phối. JobExecutionListener cung cấp callback trước và sau Job:

~~~java
public interface JobExecutionListener extends JobListener {
    void beforeJob(JobExecution jobExecution);
    void afterJob(JobExecution jobExecution);
}
~~~

Ví dụ cleanup theo trạng thái cuối:

~~~java
@Bean
JobExecutionListener jobResourceListener() {
    return new JobExecutionListener() {

        @Override
        public void beforeJob(JobExecution jobExecution) {
            // Chuẩn bị metadata hoặc resource cấp Job.
        }

        @Override
        public void afterJob(JobExecution jobExecution) {
            if (jobExecution.getStatus() == BatchStatus.COMPLETED) {
                finalizeSuccessfulRun(jobExecution);
            } else {
                quarantineFailedRun(jobExecution);
            }
        }
    };
}
~~~

Đăng ký listener vào Job:

~~~java
return new JobBuilder("customerImportJob", jobRepository)
    .listener(jobResourceListener)
    .start(validateStep)
    .next(importStep)
    .next(publishStep)
    .build();
~~~

afterJob phù hợp với cleanup hoặc housekeeping cấp Job sau khi các Step đã kết thúc. Hành động trong listener cần idempotent vì vận hành có thể phải chạy lại cleanup sau sự cố.

### Không đặt toàn bộ business publish trong afterJob

Nếu publish là bước bắt buộc quyết định Job có thành công hay không, nên tạo một publish Step cuối cùng. Khi publish Step thất bại, JobRepository ghi nhận trạng thái thất bại và có thể restart theo quy tắc.

afterJob là callback lifecycle, không phải một Step có checkpoint riêng. Nếu listener chỉ chạy sau khi Job đã được đánh dấu kết thúc, exception trong listener không tương đương với một Step thất bại có thể restart. Dùng listener cho cleanup phụ; dùng Step cho công việc nghiệp vụ bắt buộc.

## 11. Thứ tự cleanup và giữ lại exception gốc

Một failure path có thể gặp hai lỗi:

1. Reader hoặc writer ném exception chính.
2. close() cũng ném exception khi cố giải phóng resource.

Cần bảo toàn thông tin lỗi chính để vận hành biết nguyên nhân Job thất bại. Exception đóng resource vẫn cần được ghi nhận vì có thể chỉ ra leak hoặc resource bị hỏng.

Với code tự quản lý resource, try-with-resources giúp Java gắn exception xảy ra khi close như suppressed exception nếu thân khối đã ném exception.

Ví dụ:

~~~java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
~~~

Nếu process() ném IOException và close() cũng thất bại, exception chính vẫn được giữ và lỗi close có thể được truy cập qua getSuppressed().

Với ItemStream do Spring Batch quản lý, hãy ném ItemStreamException có nguyên nhân gốc và ghi log có đủ context. Không bắt rồi bỏ qua mọi exception close vì điều đó che giấu resource leak.

### Đóng theo thứ tự ngược

Nếu resource B phụ thuộc resource A, thường mở A trước rồi B, sau đó đóng B trước A.

Ví dụ:

1. Mở connection.
2. Tạo statement.
3. Mở result set.
4. Khi cleanup: đóng result set, statement, rồi connection nếu ứng dụng sở hữu connection đó.

Với JDBC do Spring quản lý, hãy để JdbcTemplate hoặc transaction manager quản lý connection. Không tự đóng connection được bind với transaction hiện tại.

## 12. Resource database khi Step thất bại

Database resource cần phân biệt resource do ứng dụng sở hữu và resource do Spring transaction quản lý.

Các đối tượng thường gặp:

- Connection.
- PreparedStatement.
- ResultSet.
- Cursor reader.
- EntityManager.

Nếu dùng JdbcTemplate, NamedParameterJdbcTemplate hoặc Spring Data repository, framework quản lý phần lớn vòng đời statement/result set và tham gia transaction phù hợp.

Nếu tự mở JDBC resource, dùng try-with-resources:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql);
     ResultSet resultSet = statement.executeQuery()) {

    while (resultSet.next()) {
        processRow(resultSet);
    }
}
~~~

Đoạn code này phù hợp khi ứng dụng thực sự sở hữu connection được mở độc lập. Nếu connection được lấy từ transaction-aware Spring API và thuộc transaction của Step, không tự đóng nó theo cách phá vỡ transaction.

### JdbcCursorItemReader

JdbcCursorItemReader là một reader có state và quản lý cursor/statement/connection theo lifecycle của nó. Khi dùng trực tiếp trong Step, hãy để Spring Batch gọi open, update và close. Không lấy cursor nội bộ rồi đóng từ listener khác.

Nếu Step thất bại, transaction chunk có thể rollback nhưng reader vẫn cần close cursor. Hai hành động này có vai trò riêng.

## 13. Resource HTTP và client bên ngoài

Khi gọi HTTP, cần đóng response body hoặc stream ngay sau khi đọc xong. Connection pool thường được tái sử dụng; không phải mỗi request đều cần đóng toàn bộ HTTP client.

Ví dụ dùng một client có response resource:

~~~java
try (InputStream body = responseBodyStream) {
    return parseResponse(body);
}
~~~

Trong thực tế, API cụ thể của WebClient, RestClient, HttpClient hoặc thư viện khác có quy tắc riêng. Hãy dùng cơ chế release/close của thư viện đó.

### Phân biệt vòng đời client và response

- HTTP client có thể là singleton dùng chung toàn ứng dụng và được đóng khi application shutdown.
- Response body hoặc stream thuộc một request và cần được giải phóng sau khi đọc.
- Một request timeout không chứng minh server chưa thực hiện thao tác.
- Retry request cần idempotency nếu thao tác có side effect.

Không đóng singleton HTTP client sau mỗi item hoặc sau mỗi Step nếu client được chia sẻ cho các Job khác. Chỉ đóng resource có ownership thuộc phạm vi hiện tại.

## 14. File output chưa hoàn chỉnh khi Job thất bại

Đóng file không có nghĩa file đã hợp lệ. Nếu writer ghi file rồi Step thất bại ở giữa, file có thể chứa một phần output.

Một thiết kế an toàn là ghi vào file tạm và publish sau khi toàn bộ quy trình thành công:

~~~mermaid
flowchart TD
    A["Writer mở file staging"] --> B["Ghi từng chunk"]
    B --> C["Step kết thúc và close file"]
    C --> D{"Job xử lý thành công?"}
    D -- "Có" --> E["Publish / atomic move"]
    D -- "Không" --> F["Quarantine hoặc xóa file staging"]
    E --> G["Output chính thức"]
    F --> H["Không công bố output dở dang"]
~~~

Ví dụ đặt tên:

~~~java
Path staging = outputDirectory.resolve(
    "customer-summary-" + runId + ".part"
);

Path published = outputDirectory.resolve(
    "customer-summary-" + runId + ".csv"
);
~~~

Sau khi writer đóng file và publish Step xác nhận dữ liệu đầy đủ, có thể dùng Files.move với ATOMIC_MOVE nếu filesystem hỗ trợ. Nếu atomic move không được hỗ trợ, cần fallback có kiểm soát và bảo đảm không công bố file dở dang.

### Vì sao không xóa file ngay trong close()?

close() thường được gọi cả khi Step thành công lẫn thất bại. Nó chỉ nên đóng handle và hoàn tất lifecycle của writer. Nếu close luôn xóa file, output hợp lệ cũng bị xóa.

Quyết định giữ, publish, quarantine hay xóa file cần dựa trên trạng thái Step/Job và được đặt ở Step publish hoặc cleanup lifecycle phù hợp.

### Không ghi trực tiếp file chính thức

Nếu writer mở file chính thức rồi Job thất bại, downstream có thể đọc file dở dang. Dùng staging path riêng và chỉ chuyển sang vị trí chính thức sau khi hoàn tất.

## 15. Cleanup temporary file và thư mục làm việc

Temporary file có thể được tạo bởi reader, writer, sort, merge hoặc bước chuyển đổi. Cần quy định ownership:

- Step nào tạo file?
- Step nào sử dụng file?
- Khi nào file được xem là không còn cần?
- Khi Job thất bại thì giữ để debug hay quarantine?
- Khi nào có thể xóa an toàn?
- Có thể có Job khác đang sử dụng cùng thư mục không?

Không dùng một tên file tạm cố định cho nhiều JobExecution đồng thời. Hãy tạo đường dẫn theo JobExecution ID, run ID hoặc batch ID ổn định.

Ví dụ:

~~~java
Path workDirectory = rootDirectory.resolve(
    "job-" + jobExecution.getId()
);
Files.createDirectories(workDirectory);
~~~

Dùng một thư mục riêng giúp cleanup theo đúng execution. Không xóa thư mục chung hoặc wildcard rộng có thể chứa file của Job đang chạy khác.

### Cleanup idempotent

Cleanup có thể được gọi lại sau một lần thất bại. Hãy viết theo hướng idempotent:

~~~java
Files.deleteIfExists(temporaryFile);
~~~

Nếu file đã bị xóa, thao tác vẫn đạt trạng thái mong muốn. Với thư mục, chỉ xóa những file mà JobExecution sở hữu và đã được xác định không còn được sử dụng.

## 16. Lock, lease và resource bên ngoài

Một Job có thể lấy distributed lock, database advisory lock, file lock hoặc lease để bảo đảm chỉ một execution xử lý một lô.

Nếu Job thất bại, cần giải phóng lock hoặc để lease hết hạn. Không chỉ dựa vào callback close vì process có thể bị kill trước khi callback chạy.

Một thiết kế lease thường có:

- Owner ID gắn với JobExecution.
- Thời điểm hết hạn.
- Heartbeat hoặc gia hạn khi Job còn hoạt động.
- Cơ chế takeover sau khi lease hết hạn.
- Kiểm tra owner trước khi release để tránh xóa lock của Job khác.

Ví dụ release theo owner:

~~~java
lockService.release(
    resourceKey,
    jobExecution.getId().toString()
);
~~~

Release phải xác nhận lock hiện tại thuộc đúng JobExecution. Nếu Job cũ kết thúc muộn và release lock đã được Job mới nhận, không được xóa lock của owner mới.

### Không dùng file lock làm cơ chế restart duy nhất

File lock có thể được hệ điều hành giải phóng khi process kết thúc, nhưng nó không thay thế metadata của JobRepository. Restart vẫn cần kiểm tra JobExecution, checkpoint và trạng thái nghiệp vụ.

## 17. Message consumer và acknowledgment

Với message queue, việc đóng consumer khác với việc xác nhận message đã xử lý.

- Close consumer giải phóng kết nối hoặc subscription.
- Acknowledge xác nhận message đã được nhận và xử lý theo giao thức.
- Transaction rollback có thể làm message được redeliver nếu broker và transaction được phối hợp đúng.
- Nếu acknowledge quá sớm, message có thể mất dù database transaction rollback.

Không acknowledge message trước khi chunk hoặc transaction nghiệp vụ đạt trạng thái an toàn. Với transactional queue reader, cần cấu hình và kiểm thử cơ chế redelivery/rollback đúng với broker.

Khi Job thất bại, đóng consumer giúp giải phóng tài nguyên kết nối. Nó không tự quyết định message đang xử lý sẽ được redeliver hay không; điều đó phụ thuộc acknowledgment mode, visibility timeout và transaction integration.

## 18. Executor và thread

TaskExecutor thường là bean do Spring quản lý và có thể được chia sẻ giữa nhiều Step hoặc Job. Không nên shutdown executor từ afterStep nếu executor không thuộc ownership riêng của Step đó.

Quy tắc:

- Executor singleton được đóng theo vòng đời application context.
- Executor tạo riêng cho một JobExecution phải có ownership và shutdown rõ ràng.
- Không shutdown thread pool dùng chung khi một Step thất bại.
- Chờ worker kết thúc trong giới hạn thời gian phù hợp.
- Xử lý interrupt đúng cách và không nuốt cờ interrupt.
- Không giữ resource trong ThreadLocal mà không clear ở finally.

Nếu worker thread sở hữu file hoặc connection, worker phải đóng resource trong lifecycle của chính nó. Listener của thread manager không thể tự đóng an toàn resource cục bộ mà không có tham chiếu và ownership rõ ràng.

## 19. JobExecutionListener và sự cố process bị kill

Lifecycle callback hoạt động khi Spring Batch có cơ hội kết thúc Job/Step theo đường thực thi thông thường. Callback không thể được bảo đảm nếu process bị dừng cưỡng bức.

Các tình huống:

| Tình huống | Callback close/listener có cơ hội chạy? | Cách bảo vệ |
|---|---|---|
| Exception trong processor/writer | Thông thường có trong lifecycle Step | ItemStream và try-with-resources |
| Step bị fail có kiểm soát | Thông thường có | Step listener và Job listener |
| Job bị stop theo cơ chế Spring Batch | Lifecycle có cơ hội kết thúc | Stop/interrupt handling và close |
| JVM crash hoặc kill -9 | Không bảo đảm | Lease, TTL, recovery scan |
| Máy mất điện | Không bảo đảm | Durable metadata và cleanup khi khởi động lại |
| Container bị terminate cưỡng bức | Không bảo đảm nếu không đủ thời gian shutdown | Graceful shutdown và lease expiry |

### Graceful shutdown

Khi triển khai trên server hoặc container, cấu hình thời gian shutdown đủ để Job dừng có kiểm soát, transaction kết thúc và resource được đóng. Tuy nhiên, graceful shutdown chỉ giảm rủi ro; không loại bỏ khả năng process chết đột ngột.

### Recovery khi ứng dụng khởi động lại

Một cơ chế recovery có thể quét các thư mục staging hoặc lease đã hết hạn:

1. Tìm resource gắn với JobExecution không còn hoạt động.
2. Đối chiếu JobRepository và owner ID.
3. Xác định file hoặc lease có thể được thu hồi an toàn.
4. Quarantine hoặc xóa theo retention policy.
5. Ghi audit kết quả cleanup.

Không xóa file chỉ vì tuổi file lớn. Job chạy lâu có thể vẫn đang sử dụng nó. Cần xác minh owner và trạng thái trước khi cleanup.

## 20. Đóng resource trong listener mà không tạo lỗi thứ cấp

Listener có thể gặp lỗi trong quá trình cleanup. Nếu cleanup là công việc phụ, lỗi cần được ghi nhận nhưng không nên che mất nguyên nhân Job thất bại.

Ví dụ:

~~~java
@Override
public void afterJob(JobExecution execution) {
    try {
        releaseJobLease(execution);
    } catch (Exception cleanupException) {
        log.error(
            "Cleanup lease thất bại cho execution {}",
            execution.getId(),
            cleanupException
        );
    }
}
~~~

Nếu không thể release lease, TTL hoặc recovery process cần thu hồi sau. Không bỏ qua lỗi hoàn toàn; ghi lại owner, resource key và thời điểm.

Nếu cleanup là điều kiện bắt buộc để Job được coi là thành công, hãy thực hiện nó trong một Step riêng trước terminal transition. Step có thể thất bại, được theo dõi và restart bằng JobRepository.

### Không thay đổi trạng thái Job tùy tiện trong listener

afterJob và afterStep là callback lifecycle. Không nên tự sửa BatchStatus hoặc ExitStatus để che giấu lỗi cleanup. Nếu cleanup ảnh hưởng kết quả nghiệp vụ, hãy đưa nó vào flow bằng Step và quy định rõ terminal state.

## 21. Đóng resource khi retry và skip

Retry, skip và close có thể tương tác trong một Step:

- Retry có thể gọi lại processor hoặc writer trước khi Step kết thúc.
- Skip có thể làm framework rollback và cô lập item lỗi.
- ItemStream vẫn cần giữ resource trong suốt lifecycle Step và đóng khi Step kết thúc.
- Không đóng reader hoặc writer trong mỗi lần retry nếu framework cần dùng lại ở lần tiếp theo.
- Không xóa file staging ngay khi một item bị skip nếu các item khác còn cần ghi vào cùng file.

Nếu một request HTTP tạo response body riêng cho mỗi lần retry, hãy đóng response body của lần thử đó trong chính lần gọi. Nếu một reader giữ cursor cho toàn Step, hãy để ItemStream quản lý cursor đến khi Step kết thúc.

Phân biệt resource có phạm vi một attempt với resource có phạm vi Step:

| Phạm vi | Ví dụ | Nơi đóng |
|---|---|---|
| Một method call | HTTP response body | try-with-resources/finally trong method |
| Một item attempt | InputStream mở riêng cho item | finally của lần xử lý |
| Một Step | Cursor reader, file writer | ItemStream.close |
| Một Job | Lease hoặc thư mục staging dùng chung | Job lifecycle/cleanup Step |
| Toàn ứng dụng | Shared HTTP client, executor singleton | Application shutdown |

## 22. Resource trong partitioning

Trong partitioned Step, mỗi worker có StepExecution riêng và có thể mở resource riêng.

Ví dụ:

- Worker partition0 mở cursor theo range ID 1–250.
- Worker partition1 mở cursor theo range ID 251–500.
- Worker partition2 mở cursor theo range ID 501–750.

Mỗi reader nên là Step-scoped và quản lý lifecycle riêng. Khi một worker thất bại, resource của worker đó cần đóng; các worker khác có thể đang chạy hoặc cũng kết thúc theo chính sách manager.

Không dùng chung một mutable reader hoặc một file handle giữa các partition nếu implementation không thread-safe.

### File output theo partition

Mỗi worker nên ghi file riêng:

~~~text
staging/
  run-42/
    partition0.part
    partition1.part
    partition2.part
~~~

Sau khi manager xác nhận mọi worker hoàn tất, một Step tiếp theo có thể ghép hoặc publish output. Nếu một worker thất bại, không publish toàn bộ tập file như thể Job đã hoàn thành.

Cleanup cần biết partition nào đã hoàn tất và file nào đang được worker sử dụng. Không xóa file của worker còn hoạt động.

## 23. Resource trong multi-threaded Step

Trong multi-threaded Step, nhiều thread có thể cùng sử dụng thành phần Step. Một resource được chia sẻ cần có cơ chế đồng bộ hoặc thread safety.

Cần xem xét:

- Reader có thread-safe không?
- Writer có thể ghi đồng thời không?
- Mỗi thread có resource riêng hay dùng chung?
- Ai sở hữu resource và ai được phép close?
- Có thể một thread đóng resource trong khi thread khác đang sử dụng không?
- Khi Step bị interrupt, các thread còn lại được dừng và cleanup thế nào?

Không đóng một shared resource ngay khi một thread gặp lỗi nếu các thread khác vẫn đang dùng nó. Hãy để cơ chế điều phối kết thúc worker, sau đó đóng resource ở đúng owner.

Với resource cần riêng cho từng thread, tạo và đóng trong phạm vi task của thread. Với resource chung, quản lý ở cấp Step hoặc application và chỉ close sau khi tất cả consumer đã kết thúc.

## 24. Theo dõi resource và phát hiện leak

Không chỉ dựa vào việc Job có kết thúc hay không. Nên theo dõi các dấu hiệu resource bị rò rỉ:

- Số connection đang active và thời gian giữ connection.
- Số file descriptor hoặc file handle.
- Connection pool pending/timeout count.
- HTTP connection pool leased/available.
- Số consumer/subscription đang hoạt động.
- Số file staging cũ chưa được cleanup.
- Số lease hết hạn nhưng chưa thu hồi.
- Thời gian từ Step kết thúc đến khi cleanup hoàn tất.

Log nên chứa:

- Job name và JobExecution ID.
- Step name và StepExecution ID.
- Tên resource hoặc resource key.
- Hành động open/close/release/cleanup.
- Kết quả và exception nếu thất bại.
- Owner ID nếu resource được chia sẻ.

Không ghi token, credential hoặc nội dung dữ liệu nhạy cảm trong log resource.

### Metric hữu ích

Có thể tạo metric như:

- batch.resource.open.count
- batch.resource.close.count
- batch.resource.cleanup.failure
- batch.staging.file.count
- batch.lease.expired.count

Tên metric thực tế nên theo quy ước của hệ thống. Mục tiêu là phát hiện số resource mở tăng liên tục hoặc cleanup thất bại kéo dài.

## 25. Kiểm thử đóng resource khi Job thất bại

Kiểm thử cần chứng minh close được gọi và tài nguyên thực sự được giải phóng, không chỉ chứng minh Job có trạng thái FAILED.

### Test ItemStream.close khi processor thất bại

Tạo reader test triển khai ItemStreamReader và ghi nhận callback close:

~~~java
class TrackingReader implements ItemStreamReader<InputRecord> {

    boolean opened;
    boolean closed;

    @Override
    public void open(ExecutionContext context) {
        opened = true;
    }

    @Override
    public InputRecord read() {
        return new InputRecord("A");
    }

    @Override
    public void update(ExecutionContext context) {
    }

    @Override
    public void close() {
        closed = true;
    }
}
~~~

Cấu hình processor ném exception không skipable. Chạy Step và xác nhận:

- StepExecution kết thúc FAILED.
- Reader đã được mở.
- close() được gọi trong lifecycle kết thúc Step.
- Không còn resource test đang mở.

Trong test, reader nên có cơ chế kết thúc sau một số lần đọc hoặc ném lỗi có chủ đích để tránh lặp vô hạn.

### Test close khi writer thất bại

Tạo writer triển khai ItemStreamWriter, cho write() ném exception. Xác nhận:

- Transaction chunk rollback theo policy.
- Step thất bại.
- Writer close() được gọi.
- File hoặc handle được đóng.
- Dữ liệu tạm được xử lý theo cleanup policy riêng.

### Test open thất bại giữa chừng

Tạo ItemStream mở resource A thành công nhưng mở resource B thất bại. Xác nhận code open() tự đóng A trước khi ném ItemStreamException.

Đây là kiểm thử quan trọng vì framework không thể đóng một resource mà object chưa hoàn tất khởi tạo và chưa được đăng ký đầy đủ.

### Test try-with-resources

Cho xử lý bên trong Tasklet ném exception và xác nhận resource mock hoặc file stream đã được đóng. Java try-with-resources cần được kiểm thử ở cả đường thành công và đường exception.

### Test cleanup idempotent

Gọi cleanup hai lần và xác nhận không gây lỗi ngoài dự kiến. Với file tạm, lần thứ hai có thể không còn file. Với lease, lần thứ hai phải không giải phóng nhầm lease của owner khác.

### Test process crash

Không thể chứng minh callback close được chạy khi process bị kill bằng một unit test thông thường. Thay vào đó, kiểm thử recovery logic:

1. Tạo metadata giả lập một execution không còn hoạt động.
2. Tạo lease hoặc file staging cũ gắn với execution đó.
3. Chạy recovery scanner.
4. Xác nhận scanner kiểm tra owner và trạng thái.
5. Xác nhận chỉ resource đã hết hạn và không còn được sử dụng mới bị thu hồi.

## 26. Những lỗi thiết kế thường gặp

### Chỉ đóng resource khi Step thành công

Nếu close chỉ nằm trong nhánh thành công, exception có thể làm resource bị bỏ lại. Dùng ItemStream lifecycle, finally hoặc try-with-resources.

### Cho rằng rollback tự đóng file và cursor

Rollback quản lý transaction, không thay thế close của file handle, stream hoặc consumer.

### Cho rằng close sẽ xóa file tạm

Close giải phóng handle và có thể flush buffer. Xóa hoặc quarantine là cleanup riêng.

### Mở resource trong singleton constructor

Resource có thể tồn tại lâu hơn JobExecution và bị chia sẻ ngoài ý muốn. Mở trong ItemStream.open, Tasklet method hoặc lifecycle phù hợp.

### Quên đăng ký custom ItemStream delegate

Framework chỉ quản lý những stream mà Step biết. Đăng ký delegate bằng stream(...) hoặc chuyển tiếp lifecycle từ composite.

### Đóng shared client trong afterStep

Một HTTP client hoặc executor singleton có thể được nhiều Job dùng chung. Đóng nó sau một Step có thể làm các Job khác lỗi.

### Cleanup file chính thức khi close

close chạy cả khi Step thành công. Không xóa output hợp lệ ở callback này. Dùng staging và publish/cleanup theo trạng thái Job.

### Cleanup mọi file trong thư mục chung

Có thể xóa file của Job khác đang chạy. Dùng thư mục riêng theo execution và xác minh ownership.

### Dựa vào listener để xử lý process crash

Callback không thể chạy nếu process bị kill hoặc máy mất điện. Dùng lease TTL, startup recovery và retention policy.

### Nuốt exception close

Resource leak có thể bị che giấu. Ghi nhận lỗi cleanup cùng resource key và execution ID.

### Tự đóng connection do transaction manager sở hữu

Đóng connection transaction-bound có thể phá transaction của Step. Để Spring quản lý resource đó.

### Acknowledge message trước commit

Message có thể mất nếu database rollback. Phối hợp acknowledgment, broker transaction và chunk commit.

## 27. Quy trình thiết kế resource cleanup cho Job

Khi một Job sử dụng resource bên ngoài, có thể làm theo trình tự:

1. **Liệt kê resource:** file, cursor, connection, response body, consumer, lock, lease, executor và temporary output.
2. **Xác định ownership:** resource thuộc một method, item attempt, Step, Job hay toàn ứng dụng.
3. **Chọn lifecycle:** try-with-resources cho method; ItemStream cho reader/writer; listener hoặc cleanup Step cho phạm vi Step/Job.
4. **Đăng ký stream:** bảo đảm custom ItemStream và delegate được Step quản lý.
5. **Xử lý open thất bại:** tự đóng các resource đã mở dở dang.
6. **Tách transaction:** hiểu resource nào tham gia rollback và resource nào phải cleanup riêng.
7. **Bảo vệ output:** dùng staging, quarantine và publish sau khi hoàn tất.
8. **Thiết kế cleanup idempotent:** thao tác lặp không gây hỏng dữ liệu hoặc giải phóng nhầm owner.
9. **Bảo vệ sự cố đột ngột:** dùng lease TTL, graceful shutdown và recovery scanner.
10. **Theo dõi:** ghi nhận open/close/cleanup và metric resource.
11. **Kiểm thử:** exception ở reader, processor, writer, open failure, cleanup failure và process recovery.

## 28. Những điểm cần nhớ

- Resource cần được giải phóng khi Step hoặc Job thất bại theo lifecycle thông thường.
- ItemStream cung cấp open, update và close cho reader/writer có trạng thái.
- Spring Batch quản lý stream được đăng ký với Step; custom delegate cần chuyển tiếp hoặc đăng ký rõ ràng.
- close giải phóng handle, không đồng nghĩa với rollback transaction hoặc xóa file.
- Transaction rollback chỉ hoàn tác resource tham gia transaction.
- Dùng try-with-resources cho resource có phạm vi một method hoặc một lần execute.
- Dùng ItemStream cho resource tồn tại trong lifecycle Step và cần checkpoint.
- Dùng listener hoặc cleanup Step cho công việc phụ thuộc trạng thái Step/Job.
- Nếu open() thất bại giữa chừng, code khởi tạo phải tự đóng những resource đã mở.
- Không đặt business publish bắt buộc trong afterJob; dùng Step riêng để JobRepository theo dõi và restart.
- File output chưa hoàn chỉnh nên được giữ ở staging và chỉ publish sau khi quy trình thành công.
- Lock và lease cần owner ID, TTL và recovery vì process crash có thể bỏ qua callback close.
- Không đóng shared client, executor hoặc connection thuộc ownership của thành phần khác.
- Message acknowledgment phải phối hợp với transaction và commit.
- Kiểm thử cả callback close lẫn trạng thái resource thực tế sau exception.

Đóng resource đúng cách giúp Job thất bại mà không để lại file handle, cursor, connection hoặc lease bị giữ vô thời hạn. Khi phân biệt rõ rollback, close và cleanup, đồng thời thiết kế recovery cho trường hợp process chết đột ngột, Spring Batch có thể giải phóng tài nguyên an toàn và hỗ trợ lần chạy tiếp theo một cách đáng tin cậy.

