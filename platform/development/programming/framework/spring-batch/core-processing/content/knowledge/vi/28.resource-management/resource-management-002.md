# ItemStream open và close

Trong Spring Batch, nhiều thành phần batch cần mở và giải phóng resource trong suốt vòng đời của một Step. Reader có thể cần mở file hoặc cursor; writer có thể cần mở file đầu ra; một thành phần tùy chỉnh có thể cần khôi phục vị trí đọc sau khi Job restart. Interface **ItemStream** cung cấp hợp đồng lifecycle để Spring Batch quản lý những thao tác này.

ItemStream có ba callback: **open**, **update** và **close**. open nhận ExecutionContext để khôi phục trạng thái đã lưu; update ghi checkpoint hiện tại vào context tại các mốc quản lý của Step; close giải phóng resource khi Step kết thúc. Trong đó, open và close thường được nhắc cùng nhau khi nói về quản lý resource, nhưng update là phần quan trọng giúp reader hoặc writer hỗ trợ restart.

## 1. ItemStream là gì?

ItemStream là interface lifecycle trong Spring Batch:

~~~java
public interface ItemStream {

    void open(ExecutionContext executionContext) throws ItemStreamException;

    void update(ExecutionContext executionContext) throws ItemStreamException;

    void close() throws ItemStreamException;
}
~~~

Các thành phần đọc hoặc ghi có thể kết hợp hợp đồng này với interface xử lý item:

- **ItemStreamReader<T>** kết hợp **ItemReader<T>** và **ItemStream**.
- **ItemStreamWriter<T>** kết hợp **ItemWriter<T>** và **ItemStream**.
- Một reader hoặc writer tùy chỉnh có thể triển khai trực tiếp các interface này để vừa xử lý item vừa quản lý resource.

ItemReader chỉ định nghĩa cách lấy item; ItemWriter chỉ định nghĩa cách ghi item. ItemStream bổ sung vòng đời mở resource, khôi phục trạng thái, cập nhật checkpoint và đóng resource. Điều này giúp framework quản lý lifecycle thống nhất thay vì ứng dụng tự gọi open/close thủ công ở nhiều nơi.

## 2. Ba callback trong vòng đời ItemStream

| Callback | Khi nào được gọi? | Trách nhiệm |
|---|---|---|
| open(ExecutionContext) | Khi Step bắt đầu và trước khi xử lý item | Mở resource, đọc trạng thái đã lưu và khôi phục vị trí |
| update(ExecutionContext) | Tại các mốc cập nhật trạng thái của Step, thường gắn với ranh giới commit của chunk | Ghi checkpoint hoặc trạng thái cần khôi phục |
| close() | Khi Step kết thúc, kể cả khi xử lý có lỗi và framework thực hiện cleanup | Flush phần cần thiết và giải phóng resource |

Luồng khái quát của một chunk-oriented Step:

~~~text
Step bắt đầu
    |
    v
ItemStream.open(executionContext)
    |
    v
Đọc / xử lý / ghi chunk
    |
    v
ItemStream.update(executionContext)
    |
    v
Commit chunk và metadata theo transaction
    |
    v
Lặp lại cho các chunk tiếp theo
    |
    v
Step kết thúc hoặc thất bại
    |
    v
ItemStream.close()
~~~

Đây là mô tả lifecycle ở mức khái quát. Thứ tự chi tiết giữa các stream, listener và transaction phụ thuộc loại Step và cách đăng ký thành phần. Điểm quan trọng là ứng dụng giao việc quản lý stream cho Spring Batch bằng cách đăng ký đúng các ItemStream cần thiết.

## 3. open() — mở resource và khôi phục trạng thái

Spring Batch gọi open() khi Step chuẩn bị thực thi. Phương thức nhận ExecutionContext của StepExecution hiện tại. Context này có thể chứa checkpoint đã lưu từ lần chạy trước.

Một triển khai open thường thực hiện:

1. Kiểm tra tham số hoặc resource cần thiết.
2. Mở file, stream, cursor hoặc resource phù hợp.
3. Đọc checkpoint từ ExecutionContext nếu có.
4. Đưa reader/writer về trạng thái tương ứng với checkpoint.
5. Ném ItemStreamException nếu không thể khởi tạo an toàn.

Ví dụ, reader đọc file có thể mở file rồi bỏ qua số dòng đã xử lý trước đó. Khi Job restart, open() nhận lại context đã persist và khôi phục vị trí đọc.

~~~java
@Override
public void open(ExecutionContext executionContext) {
    try {
        reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);

        long linesAlreadyRead = executionContext.getLong(READ_COUNT_KEY, 0L);
        for (long i = 0; i < linesAlreadyRead; i++) {
            if (reader.readLine() == null) {
                throw new ItemStreamException(
                        "Checkpoint is beyond the end of the input file");
            }
        }

        currentLine = linesAlreadyRead;
    } catch (IOException ex) {
        throw new ItemStreamException("Cannot open input file: " + path, ex);
    }
}
~~~

Đây là ý tưởng khôi phục checkpoint bằng số dòng. Trong ứng dụng thực tế, cần xác nhận file đầu vào vẫn là đúng file/version đã dùng trước đó. Nếu file bị thay thế hoặc nội dung thay đổi, cùng một số dòng có thể trỏ tới dữ liệu khác. Có thể lưu thêm checksum, file size, version hoặc batch ID để xác minh resource.

Không nên mở resource ở constructor của reader. Constructor của bean có thể chạy khi application context khởi động, trước khi StepExecution tồn tại. open() là nơi phù hợp để mở resource theo lifecycle của Step.

## 4. update() — lưu checkpoint

update() cho phép ItemStream ghi trạng thái hiện tại vào ExecutionContext. Với chunk-oriented Step, Spring Batch gọi callback này tại các mốc checkpoint, thường trước khi transaction của chunk commit. Metadata và dữ liệu chunk được quản lý theo transaction/repository configuration để hỗ trợ khôi phục nhất quán.

Ví dụ reader đã đọc đến dòng thứ 250:

~~~java
@Override
public void update(ExecutionContext executionContext) {
    executionContext.putLong(READ_COUNT_KEY, currentLine);
}
~~~

Khi Job restart, open() lấy lại giá trị đã lưu để tiếp tục từ checkpoint. Nếu ứng dụng không ghi trạng thái cần thiết vào context, reader tùy chỉnh có thể bắt đầu lại từ đầu hoặc không thể khôi phục chính xác.

Không phải mọi giá trị runtime đều cần đưa vào context. Chỉ lưu những thông tin nhỏ cần thiết để khôi phục, ví dụ:

- Số dòng đã đọc.
- Khóa duy nhất cuối cùng đã xử lý.
- Trang hoặc offset hiện tại.
- Version hoặc định danh snapshot.
- Trạng thái writer cần thiết để tiếp tục ghi.

Không lưu cả danh sách item đã đọc hoặc toàn bộ nội dung file vào ExecutionContext. Context được persist trong metadata repository và cần giữ kích thước nhỏ, có thể serialize.

## 5. close() — giải phóng resource

close() được Spring Batch gọi khi Step kết thúc để thành phần stream giải phóng tài nguyên đã mở. Các thao tác thường thực hiện:

- Flush buffer nếu hợp đồng của writer yêu cầu.
- Đóng reader hoặc writer đang mở.
- Đóng cursor hoặc stream do thành phần sở hữu.
- Giải phóng handle, temporary resource hoặc file descriptor.
- Xóa tham chiếu runtime để tránh giữ resource sau khi Step kết thúc.

Ví dụ:

~~~java
@Override
public void close() {
    if (reader != null) {
        try {
            reader.close();
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot close input reader", ex);
        } finally {
            reader = null;
        }
    }
}
~~~

close() cần an toàn khi resource chưa được mở hoàn chỉnh. Một lỗi trong open() có thể khiến chỉ một phần resource được khởi tạo; cleanup không nên tạo thêm lỗi khó hiểu hoặc che mất exception gốc. Nên kiểm tra null và giải phóng từng resource đã được mở.

Không nên nuốt mọi exception trong close() một cách âm thầm. Nếu không đóng hoặc flush được resource quan trọng, Step có thể cần phản ánh lỗi đó. Cần quyết định rõ lỗi cleanup có làm Step thất bại hay được ghi nhận như lỗi phụ, tùy mức độ quan trọng của dữ liệu.

## 6. Ví dụ reader tùy chỉnh triển khai ItemStream

Ví dụ dưới đây tạo một reader đọc file văn bản từng dòng, lưu số dòng đã đọc và khôi phục vị trí khi restart:

~~~java
public class CheckpointFileReader
        implements ItemStreamReader<String> {

    private static final String READ_COUNT_KEY =
            "checkpointFileReader.readCount";

    private final Path path;
    private BufferedReader reader;
    private long currentLine;

    public CheckpointFileReader(Path path) {
        this.path = path;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        try {
            reader = Files.newBufferedReader(path, StandardCharsets.UTF_8);
            long savedLine = executionContext.getLong(READ_COUNT_KEY, 0L);

            for (long i = 0; i < savedLine; i++) {
                if (reader.readLine() == null) {
                    throw new ItemStreamException(
                            "Saved position exceeds input length");
                }
            }

            currentLine = savedLine;
        } catch (IOException ex) {
            closeQuietly();
            throw new ItemStreamException("Unable to open " + path, ex);
        }
    }

    @Override
    public String read() throws Exception {
        if (reader == null) {
            throw new IllegalStateException("Reader has not been opened");
        }

        String line = reader.readLine();
        if (line != null) {
            currentLine++;
        }
        return line;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        executionContext.putLong(READ_COUNT_KEY, currentLine);
    }

    @Override
    public void close() {
        try {
            closeQuietly();
        } catch (RuntimeException ex) {
            throw new ItemStreamException("Unable to close reader", ex);
        }
    }

    private void closeQuietly() {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException ex) {
                throw new ItemStreamException("Unable to close file " + path, ex);
            } finally {
                reader = null;
            }
        }
    }
}
~~~

Reader này minh họa các trách nhiệm chính:

- open() mở file và khôi phục số dòng từ context.
- read() lấy một dòng và tăng bộ đếm khi có dữ liệu.
- update() ghi bộ đếm vào context.
- close() đóng file.

Đây là ví dụ nền tảng, chưa xử lý mọi trường hợp production. Nếu file lớn, bỏ qua từng dòng trong open() có thể tốn thời gian khi restart xa checkpoint; có thể dùng byte offset, indexed file hoặc nguồn dữ liệu hỗ trợ seek. Cần kiểm tra file identity trước khi khôi phục và xử lý rõ lỗi đọc/đóng. Nếu reader cần được dùng trong Step scope, khai báo bean với @StepScope khi nó phụ thuộc JobParameters hoặc context.

## 7. Đăng ký ItemStream với Step

Spring Batch chỉ quản lý lifecycle của các stream mà Step nhận diện và đăng ký. Nếu reader hoặc writer được cấu hình trực tiếp trong Step và triển khai ItemStream, framework thường tự đăng ký lifecycle của thành phần đó.

Ví dụ:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemStreamReader<String> reader,
        ItemWriter<String> writer) {

    return new StepBuilder("importStep", jobRepository)
            .<String, String>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
~~~

Reader được đưa trực tiếp vào cấu hình Step và triển khai ItemStream, nên Spring Batch có thể gọi open/update/close trong lifecycle của Step.

### Delegate bị ẩn bên trong composite

Một số reader/writer được bọc trong composite hoặc adapter. Nếu wrapper không triển khai ItemStream hoặc không chuyển tiếp lifecycle tới delegate, Spring Batch không tự biết delegate cần open/update/close.

Khi đó, cần đăng ký delegate như một stream của Step:

~~~java
return new StepBuilder("compositeWriteStep", jobRepository)
        .<InputRecord, OutputRecord>chunk(100, transactionManager)
        .reader(reader)
        .writer(compositeWriter)
        .stream(delegateWriter)
        .build();
~~~

Phương thức stream(...) đăng ký một ItemStream bổ sung để Step gọi lifecycle callback. Chỉ cần đăng ký riêng khi wrapper không tự quản lý delegate. Nếu composite đã triển khai ItemStream và chuyển tiếp callback tới delegate, tránh đăng ký lặp làm open/update/close được gọi hai lần.

Hãy kiểm tra hợp đồng của composite/adapter đang dùng trong phiên bản Spring Batch của ứng dụng. Đừng giả định mọi wrapper đều tự động chuyển tiếp lifecycle.

## 8. ItemStream và reader/writer built-in

Nhiều thành phần có sẵn của Spring Batch đã triển khai ItemStream để quản lý resource và checkpoint:

- **FlatFileItemReader:** mở file, theo dõi vị trí đọc và hỗ trợ khôi phục trạng thái.
- **MultiResourceItemReader:** quản lý tập resource và vị trí hiện tại trong danh sách file.
- **JdbcCursorItemReader:** quản lý cursor/result set và trạng thái cần thiết theo implementation.
- **JdbcPagingItemReader:** lưu thông tin trang hoặc khóa để tiếp tục đọc.
- **FlatFileItemWriter:** quản lý file output, header/footer, append và trạng thái ghi.
- **StaxEventItemReader** và các reader XML: quản lý resource và vị trí xử lý theo khả năng hỗ trợ.

Khi dùng thành phần built-in, ưu tiên cấu hình các thuộc tính restart/resource của nó thay vì tự mở cùng resource bên ngoài. Kiểm tra tài liệu phiên bản cụ thể để biết reader/writer có hỗ trợ restart hay không và những điều kiện cần thiết.

Một reader/writer có thể triển khai ItemStream nhưng không nhất thiết lưu mọi trạng thái nếu cấu hình tắt việc lưu state. Ví dụ, một số builder có tùy chọn saveState(false). Khi tắt, thành phần có thể không ghi checkpoint để khôi phục sau restart; chỉ dùng khi Step không cần restart hoặc trạng thái được quản lý bằng cơ chế khác.

## 9. Tên stream và key trong ExecutionContext

Reader/writer built-in thường dùng tên thành phần để tạo key lưu trạng thái trong ExecutionContext. Tên này cần ổn định giữa các lần chạy và restart.

Với reader tùy chỉnh, nên dùng key có namespace để tránh trùng với key của thành phần khác:

~~~java
private static final String READ_COUNT_KEY =
        "customerFileReader.readCount";
~~~

Không nên dùng key quá chung như count, index hoặc position nếu Step có nhiều stream. Hai stream cùng ghi một key có thể ghi đè trạng thái của nhau và làm restart sai vị trí.

Nếu đổi tên reader hoặc key checkpoint trong phiên bản ứng dụng mới, cần xem xét khả năng tương thích với JobExecution cũ còn cần restart. Một thay đổi key có thể khiến reader không đọc được checkpoint đã lưu. Có thể hỗ trợ đọc key cũ trong giai đoạn chuyển đổi hoặc quyết định rõ rằng execution cũ không còn được restart bằng code mới.

## 10. open() khi restart

Khi Job restart cùng JobInstance, Spring Batch khôi phục metadata đã lưu từ JobRepository. open() nhận ExecutionContext của StepExecution đang được thực thi lại, bao gồm checkpoint đã persist trước đó.

Ví dụ:

~~~text
Lần chạy đầu:
  open(context: readCount=0)
  đọc 100 item
  update(context: readCount=100)
  commit chunk
  đọc tiếp 100 item
  update(context: readCount=200)
  commit chunk
  lỗi ở chunk tiếp theo
  close()

Restart:
  open(context: readCount=200)
  khôi phục reader sau item 200
  tiếp tục đọc phần còn lại
~~~

Checkpoint thường đại diện cho trạng thái đã được lưu tại ranh giới commit gần nhất. Nếu ứng dụng dừng đột ngột trước khi checkpoint mới được commit, reader có thể khôi phục checkpoint cũ và đọc lại một phần dữ liệu. Đây là lý do writer cần tham gia transaction hoặc có idempotency phù hợp.

Restart chỉ an toàn khi resource đầu vào vẫn tương ứng với checkpoint. Nếu file bị thay đổi, bảng nguồn thay đổi hoặc paging sort key không ổn định, việc khôi phục vị trí có thể dẫn tới bỏ sót hoặc xử lý trùng. Nên dùng batch ID, snapshot ID, version hoặc checksum để xác minh nguồn.

## 11. close() và xử lý lỗi

close() là nơi giải phóng tài nguyên bất kể Step kết thúc bình thường hay do lỗi. Không nên chỉ gọi close trong nhánh thành công của reader/writer.

Một số nguyên tắc:

- Đóng resource chỉ khi đã mở.
- Đặt field resource về null sau khi đóng để tránh dùng lại handle cũ.
- Nếu có nhiều resource, cố gắng đóng tất cả ngay cả khi một thao tác close lỗi.
- Không để lỗi cleanup che mất exception gốc của quá trình đọc/ghi nếu framework đã có lỗi chính.
- Không đóng resource do Spring transaction manager hoặc container quản lý thay cho ứng dụng.
- Không giữ resource mở trong singleton field qua nhiều StepExecution.

Ví dụ cleanup nhiều resource:

~~~java
@Override
public void close() {
    ItemStreamException failure = null;

    if (reader != null) {
        try {
            reader.close();
        } catch (IOException ex) {
            failure = new ItemStreamException("Cannot close reader", ex);
        } finally {
            reader = null;
        }
    }

    if (output != null) {
        try {
            output.close();
        } catch (IOException ex) {
            if (failure == null) {
                failure = new ItemStreamException("Cannot close output", ex);
            } else {
                failure.addSuppressed(ex);
            }
        } finally {
            output = null;
        }
    }

    if (failure != null) {
        throw failure;
    }
}
~~~

Ví dụ cho thấy cần tiếp tục đóng resource còn lại ngay cả khi resource đầu tiên đóng lỗi. Trong code thực tế, có thể dùng helper hoặc cấu trúc try/finally để giảm lặp, nhưng vẫn phải bảo đảm mọi resource đã mở đều được giải phóng.

## 12. ItemStream không thay thế transaction management

ItemStream quản lý lifecycle và checkpoint. Nó không tự tạo transaction, không tự commit dữ liệu nghiệp vụ và không bảo đảm các tác dụng phụ bên ngoài được rollback.

Ví dụ, một writer mở file và ghi dữ liệu. Database transaction rollback không thể tự xóa những byte đã ghi vào file. Nếu cần file output nhất quán khi restart, có thể:

- Ghi file tạm theo batch ID rồi publish/rename sau khi Step hoàn tất.
- Lưu offset/checkpoint và truncate file về vị trí đã commit trước khi tiếp tục, nếu định dạng và hệ thống file hỗ trợ.
- Ghi dữ liệu vào database trước, sau đó tạo file từ dữ liệu đã commit.
- Dùng output version riêng và chỉ công bố version hoàn chỉnh.

Tương tự, close() đóng file không có nghĩa nội dung file đã được commit cùng transaction database. Cần thiết kế resource và transaction boundary theo loại hệ thống.

## 13. ItemStream với Tasklet

Tasklet thường được gọi trong transaction theo cấu hình của TaskletStep. Nếu Tasklet cần quản lý resource có lifecycle riêng, có thể triển khai ItemStream cùng với Tasklet hoặc đăng ký stream riêng cho Step.

Ví dụ cấu trúc:

~~~java
public class FileProcessingTasklet implements Tasklet, ItemStream {

    private BufferedReader reader;

    @Override
    public void open(ExecutionContext executionContext) {
        // Mở file và khôi phục trạng thái nếu cần.
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {
        // Thực hiện công việc của Tasklet.
        return RepeatStatus.FINISHED;
    }

    @Override
    public void update(ExecutionContext executionContext) {
        // Lưu checkpoint nếu Tasklet có thể chạy nhiều lượt.
    }

    @Override
    public void close() {
        // Đóng resource.
    }
}
~~~

Nếu Tasklet chỉ mở resource trong một lần gọi và có thể dùng try-with-resources bên trong execute, cách đó thường đơn giản hơn. ItemStream hữu ích khi resource cần tồn tại xuyên suốt vòng đời Step hoặc trạng thái cần được lưu để restart.

Khi dùng Tasklet tùy chỉnh, hãy xác nhận stream được đăng ký với Step để lifecycle callback được gọi. Nếu Tasklet hoặc wrapper không tự được nhận diện như ItemStream, đăng ký bằng API stream của Step.

## 14. ItemStream và @StepScope

@StepScope điều khiển vòng đời bean theo StepExecution; ItemStream điều khiển lifecycle resource của thành phần stream. Hai cơ chế bổ trợ nhau:

- @StepScope giúp tạo bean với JobParameters hoặc StepExecutionContext của lần thực thi hiện tại.
- ItemStream mở resource khi Step bắt đầu, cập nhật checkpoint và đóng resource khi Step kết thúc.

Ví dụ reader vừa cần đường dẫn từ context vừa cần restart:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
~~~

Spring tạo reader theo StepExecution hiện tại. Khi Step chạy, Spring Batch gọi lifecycle của reader để mở file, lưu checkpoint và đóng resource. @StepScope không thay thế open/close; ItemStream cũng không thay thế việc late-bind inputFile.

## 15. Quản lý resource theo loại thành phần

Không phải mọi resource đều được mở và đóng theo cùng cách. Cần phân biệt resource do ItemStream sở hữu với resource được quản lý bởi framework hoặc transaction manager.

| Resource | Cách quản lý thường phù hợp |
|---|---|
| File input | Reader mở trong open, đóng trong close |
| File output | Writer mở trong open, flush/checkpoint trong update theo implementation, đóng trong close |
| JDBC cursor/result set | Dùng reader built-in hoặc đảm bảo cursor được đóng đúng lifecycle |
| JDBC connection lấy từ DataSource | Thường để Spring transaction manager/JdbcTemplate quản lý; không tự đóng connection đang tham gia transaction |
| HTTP client dùng chung | Thường là bean ứng dụng quản lý; không tạo/đóng client cho từng item nếu không cần |
| Temporary file | Tạo và xóa theo lifecycle, nhưng chỉ xóa khi chắc chắn không còn cần cho restart hoặc audit |
| Socket/stream tùy chỉnh | Thành phần sở hữu phải đóng trong close và xử lý lỗi cleanup |

Nguyên tắc là thành phần chỉ đóng resource mà nó sở hữu. Đóng nhầm connection do transaction manager quản lý có thể làm hỏng transaction của chunk.

## 16. Xử lý lỗi trong open, update và close

Ba callback đều có thể phát sinh lỗi:

- **Lỗi open:** resource không tồn tại, không có quyền đọc, không kết nối được hoặc checkpoint không hợp lệ. Step không thể bắt đầu xử lý an toàn.
- **Lỗi update:** không thể serialize hoặc lưu trạng thái. Checkpoint không đáng tin cậy; chunk có thể không commit theo transaction/repository configuration.
- **Lỗi close:** resource không đóng hoặc flush được. Step có thể ghi nhận lỗi cleanup dù phần xử lý trước đó đã commit.

Không nên chuyển các lỗi này thành trạng thái thành công bằng cách bắt exception rồi bỏ qua. Nếu lỗi làm mất khả năng restart hoặc dữ liệu đầu ra không hoàn chỉnh, cần để Step phản ánh trạng thái lỗi hoặc ghi nhận rõ ràng theo chính sách vận hành.

ItemStreamException là exception chuyên biệt dùng để báo lỗi lifecycle stream. Nên giữ exception gốc làm cause để log và điều tra được nguyên nhân thực tế.

## 17. Kiểm thử lifecycle ItemStream

Nên kiểm tra lifecycle bằng Step integration test hoặc test thành phần kết hợp với Spring Batch Test. Các tình huống quan trọng:

1. open được gọi trước khi reader bắt đầu đọc.
2. Resource được mở đúng một lần cho StepExecution theo lifecycle mong đợi.
3. update ghi checkpoint hiện tại vào ExecutionContext.
4. Restart truyền checkpoint đã lưu vào open.
5. close giải phóng resource sau khi Step hoàn tất.
6. close vẫn được thực hiện trong đường cleanup khi Step gặp lỗi.
7. open thất bại thì không có item nào được xử lý từ resource chưa sẵn sàng.
8. update thất bại không làm Step báo thành công với checkpoint không đáng tin cậy.
9. Delegate stream được đăng ký và nhận đủ lifecycle callback.
10. Không có file descriptor, cursor hoặc resource bị rò rỉ sau nhiều lần chạy.

Ví dụ kiểm tra callback với một stream giả:

~~~java
class RecordingItemStream implements ItemStream {

    boolean opened;
    boolean updated;
    boolean closed;
    long savedPosition;

    @Override
    public void open(ExecutionContext executionContext) {
        opened = true;
        savedPosition = executionContext.getLong("position", 0L);
    }

    @Override
    public void update(ExecutionContext executionContext) {
        updated = true;
        executionContext.putLong("position", savedPosition + 10L);
    }

    @Override
    public void close() {
        closed = true;
    }
}
~~~

Test có thể đăng ký stream này với Step và xác nhận các cờ sau khi launch. Để kiểm tra restart thật, cần dùng JobRepository bền vững qua hai lần JobExecution và xác nhận giá trị context được khôi phục, thay vì chỉ kiểm tra một lần gọi open trong unit test.

## 18. Các lỗi thường gặp

**Chỉ triển khai ItemReader mà quên ItemStream:** reader tùy chỉnh không có lifecycle để mở/đóng resource và lưu checkpoint. Triển khai ItemStreamReader khi cần những khả năng đó.

**Mở file trong constructor:** constructor có thể chạy trước khi StepExecution hoặc JobParameters tồn tại. Mở resource trong open.

**Không khôi phục state trong open:** Job restart có thể đọc lại từ đầu hoặc sai vị trí. Đọc checkpoint từ ExecutionContext.

**Không ghi checkpoint trong update:** reader không lưu được tiến độ cần thiết. Ghi các key nhỏ, ổn định vào context.

**Quên đăng ký delegate stream:** wrapper không chuyển tiếp lifecycle khiến delegate không được mở, cập nhật hoặc đóng.

**Đăng ký stream hai lần:** composite đã quản lý delegate nhưng Step cũng đăng ký riêng có thể khiến callback bị gọi lặp. Xác nhận hợp đồng wrapper.

**Không đóng resource khi có lỗi:** file descriptor, cursor hoặc stream có thể bị rò rỉ. Cleanup phải xử lý cả đường thành công và thất bại.

**Đóng resource không thuộc quyền sở hữu:** tự đóng connection do transaction manager quản lý có thể phá hỏng transaction.

**Lưu checkpoint không ổn định:** đổi key, reader name hoặc input giữa các lần restart có thể làm checkpoint cũ không còn dùng được.

**Nhầm close với commit:** đóng file hoặc stream không thay thế commit của transaction database và không bảo đảm output ngoài transaction được khôi phục.

## Kết luận

ItemStream định nghĩa lifecycle cho thành phần batch cần quản lý resource và trạng thái. open() mở resource và khôi phục checkpoint từ ExecutionContext; update() lưu trạng thái tại các mốc checkpoint của Step; close() giải phóng resource khi Step kết thúc. Reader/writer triển khai ItemStream cần được đăng ký với Step để Spring Batch quản lý callback. Khi dùng composite hoặc delegate, phải bảo đảm lifecycle được chuyển tiếp hoặc đăng ký stream bổ sung đúng một lần. Hãy mở resource trong open, lưu checkpoint nhỏ và ổn định trong update, đóng mọi resource thuộc quyền sở hữu trong close, đồng thời kiểm thử restart và các đường lỗi để tránh rò rỉ resource hoặc khôi phục sai dữ liệu.
