# Cleanup sau rollback trong Spring Batch

Trong chunk-oriented processing, Spring Batch thực hiện một nhóm item trong transaction. Nếu lỗi xảy ra và transaction rollback, các thay đổi thuộc resource được transaction manager quản lý sẽ được hoàn tác. Tuy nhiên, rollback không tự xóa mọi trạng thái trong bộ nhớ, không đóng mọi tài nguyên do ứng dụng tự mở và cũng không thu hồi email, HTTP request hay message đã gửi ra hệ thống bên ngoài.

Vì vậy, sau rollback cần phân biệt ba việc: **hoàn tác dữ liệu transactional**, **giải phóng tài nguyên tạm thời** và **xử lý tác động bên ngoài transaction**. Mỗi việc có cơ chế riêng. Cleanup đúng cách giúp step có thể retry hoặc restart mà không để lại file tạm, buffer cũ, kết nối bị rò rỉ hoặc side effect trùng lặp.

## 1. Rollback thực sự hoàn tác điều gì?

Một chunk thường có transaction boundary riêng. Khi transaction rollback, database sẽ hoàn tác các thao tác đã tham gia cùng transaction đó, chẳng hạn insert/update qua JdbcTemplate hoặc JPA repository dùng cùng datasource và transaction manager với step.

Ví dụ:

```text
Chunk 1: BEGIN -> ghi A, B -> COMMIT
Chunk 2: BEGIN -> ghi C, D -> exception -> ROLLBACK

Kết quả trong cùng database transaction:
  A, B: vẫn tồn tại vì chunk 1 đã commit
  C, D: thay đổi của chunk 2 bị hoàn tác
```

Rollback chỉ tác động đến resource được enlist vào transaction tương ứng. Nó không tự động:

- Đưa object Java hoặc biến trong singleton bean về giá trị trước chunk.
- Xóa file mà ứng dụng đã tạo hoặc khôi phục nội dung file đã ghi.
- Thu hồi HTTP request đã được dịch vụ khác xử lý.
- Hoàn tác email hoặc SMS đã gửi.
- Xóa message đã publish đến broker.
- Khôi phục offset hoặc trạng thái tiêu thụ của một nguồn queue không tham gia transaction.

Do đó, trước khi viết cleanup, cần xác định trạng thái nào đã được database rollback và trạng thái nào nằm ngoài transaction.

## 2. Phân biệt rollback, cleanup và compensation

Ba khái niệm thường bị nhầm lẫn:

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Rollback | Hoàn tác thay đổi thuộc transaction chưa commit. | Database hủy các câu lệnh ghi của chunk lỗi. |
| Cleanup | Giải phóng tài nguyên hoặc xóa dữ liệu tạm không còn cần thiết. | Đóng stream, xóa file staging sau khi job kết thúc. |
| Compensation | Thực hiện một nghiệp vụ bù để xử lý tác động đã xảy ra ngoài transaction. | Gửi yêu cầu hoàn tiền sau khi một giao dịch thanh toán không thể tiếp tục. |

Cleanup không phải là cách thủ công để đảo ngược mọi thứ mà rollback chưa xử lý. Nếu một API bên ngoài đã tạo giao dịch, xóa một file log hoặc reset một field trong bộ nhớ không thể hoàn tác giao dịch đó. Cần một thao tác compensation có ý nghĩa nghiệp vụ hoặc một thiết kế idempotent/outbox để kiểm soát tác động.

## 3. Vòng đời tài nguyên của ItemStream

Các reader và writer cần mở, lưu trạng thái và đóng tài nguyên có thể triển khai ItemStream. Interface này có ba callback chính:

- open(ExecutionContext): mở hoặc khôi phục trạng thái tài nguyên khi step bắt đầu.
- update(ExecutionContext): ghi trạng thái cần thiết để checkpoint.
- close(): giải phóng tài nguyên khi step kết thúc.

Một thành phần triển khai ItemStreamReader hoặc ItemStreamWriter có thể dùng các callback đó để quản lý file, cursor, buffer hoặc vị trí đọc/ghi.

```java
public class ResourceAwareReader implements ItemStreamReader<String> {

    private BufferedReader reader;

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        try {
            reader = Files.newBufferedReader(Path.of("input.txt"));
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot open input", ex);
        }
    }

    @Override
    public String read() throws Exception {
        return reader.readLine();
    }

    @Override
    public void update(ExecutionContext context) {
        // Lưu checkpoint nếu reader cần hỗ trợ restart.
    }

    @Override
    public void close() throws ItemStreamException {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException ex) {
                throw new ItemStreamException("Cannot close input", ex);
            } finally {
                reader = null;
            }
        }
    }
}
```

Ví dụ trên chỉ minh họa vòng đời resource; reader production cần lưu và khôi phục vị trí đọc trong ExecutionContext nếu cần restart. Spring Batch gọi lifecycle của ItemStream trong vòng đời step, bao gồm lúc step kết thúc sau lỗi thông thường. Nhưng không có callback Java nào được bảo đảm chạy nếu process bị kill đột ngột, máy mất điện hoặc JVM crash. Tài nguyên hệ điều hành cần được đóng an toàn khi process kết thúc, còn file tạm cần có cơ chế dọn tồn đọng riêng.

Không mở file hoặc connection trong constructor của singleton bean. Dùng open() để khởi tạo tài nguyên theo execution và close() để giải phóng nó.

## 4. close() không phải callback sau mỗi lần rollback

ItemStream.close() thuộc vòng đời step, không phải callback được gọi sau từng chunk rollback. Một step có thể rollback một chunk, retry và tiếp tục xử lý các chunk sau trước khi kết thúc. Nếu đóng reader hoặc writer trong close() sau lần rollback đầu tiên, step sẽ không thể tiếp tục bình thường.

Hãy chọn callback theo phạm vi cần cleanup:

| Phạm vi | Cơ chế phù hợp |
| --- | --- |
| Từng chunk thành công | ChunkListener.afterChunk() để ghi nhận sau khi chunk hoàn tất. |
| Một chunk gặp lỗi/rollback | ChunkListener.afterChunkError() để quan sát lỗi và dọn state tạm gắn với lần xử lý chunk đó. |
| Toàn bộ step kết thúc | ItemStream.close() để đóng resource; StepExecutionListener.afterStep() để xử lý hậu kỳ theo trạng thái step. |
| Job kết thúc | JobExecutionListener.afterJob() để thực hiện hậu kỳ ở phạm vi job. |
| Tác động ngoài transaction cần bù | Quy trình compensation/outbox riêng, có trạng thái và idempotency. |

Không dùng close() để xóa checkpoint hoặc file đầu vào cần cho restart. close() chỉ nên giải phóng resource đang mở; quyết định giữ/xóa dữ liệu tạm phải dựa trên trạng thái execution và chính sách restart.

## 5. Dùng ChunkListener để quan sát rollback

ChunkListener cung cấp callback ở cấp chunk. afterChunkError() được gọi khi chunk gặp lỗi và transaction của chunk đã rollback theo cơ chế xử lý của step. Callback này hữu ích để ghi log, metric hoặc dọn buffer tạm được tạo riêng cho lần chunk đó.

```java
public class ImportChunkListener implements ChunkListener {

    private static final Logger log =
        LoggerFactory.getLogger(ImportChunkListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        log.debug("Starting chunk");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.debug("Chunk committed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("Chunk rolled back; inspect transient state");
    }
}
```

Đăng ký listener với step:

```java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .listener(new ImportChunkListener())
    .build();
```

afterChunkError() phù hợp cho cleanup state tạm trong phạm vi chunk nếu ứng dụng quản lý state đó một cách rõ ràng. Không nên dùng callback này để xóa dữ liệu nghiệp vụ đã commit, gửi email, gọi API bù trừ một cách mù quáng hoặc xóa checkpoint. Một chunk có thể được retry; callback lỗi có thể xuất hiện trong một lần thử chưa phải lỗi cuối cùng của toàn step.

Nếu listener ghi metric ngoài transaction, metric có thể đã tăng dù một lần thử sau đó được retry thành công. Hãy phân biệt metric số lần rollback với số item cuối cùng bị skip hoặc step thất bại.

## 6. Cleanup state trong bộ nhớ sau rollback

Database rollback không hoàn tác các field trong object Java. Nếu processor, writer hoặc listener giữ buffer trong singleton bean, nội dung buffer có thể còn sau rollback và bị dùng lại ở lần thử tiếp theo.

Ví dụ không an toàn:

```java
public class BufferedWriter implements ItemWriter<Record> {

    private final List<Record> pending = new ArrayList<>();

    @Override
    public void write(Chunk<? extends Record> chunk) {
        pending.addAll(chunk.getItems());
        repository.saveAll(pending);
        pending.clear();
    }
}
```

Nếu saveAll() hoặc phần xử lý sau đó thất bại trước khi pending.clear() chạy, buffer có thể giữ các item của chunk lỗi. Khi writer được gọi lại, item cũ có thể bị ghi trùng cùng item mới.

Ưu tiên cách viết không giữ state theo chunk:

```java
public class StatelessWriter implements ItemWriter<Record> {

    private final RecordRepository repository;

    @Override
    public void write(Chunk<? extends Record> chunk) {
        repository.saveAll(chunk.getItems());
    }
}
```

Nếu thực sự cần buffer riêng, hãy tạo buffer theo execution/chunk, xóa trong finally hoặc trong cơ chế rollback được thiết kế rõ ràng, và không chia sẻ mutable state giữa các worker. finally giúp dọn bộ nhớ của lần gọi hiện tại nhưng không tự đảo ngược side effect ngoài transaction.

Với step chạy đa luồng hoặc partitioning, singleton bean có thể được nhiều thread sử dụng đồng thời. State mutable theo chunk nên nằm trong object có scope phù hợp hoặc được đồng bộ hóa có chủ đích; tránh dùng một danh sách global để tích lũy item.

## 7. Cleanup file tạm và file đầu ra

Ghi file không tự động tham gia transaction database. Nếu ứng dụng ghi trực tiếp vào file cuối cùng rồi chunk rollback, dữ liệu đã ghi có thể vẫn nằm trong file. Với file output quan trọng, nên dùng một quy trình staging:

1. Tạo file tạm riêng cho job/step execution.
2. Ghi dữ liệu vào file staging.
3. Lưu checkpoint hoặc trạng thái ghi nếu cần restart.
4. Chỉ công bố file cuối cùng sau khi step/job hoàn tất thành công.
5. Nếu execution thất bại và không còn được restart, xóa file staging theo retention policy.

Ví dụ hậu kỳ ở phạm vi step:

```java
public class StagingFileListener implements StepExecutionListener {

    private final Path stagingFile;

    public StagingFileListener(Path stagingFile) {
        this.stagingFile = stagingFile;
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED) {
            publishStagingFile(stagingFile);
        }
        // Khi FAILED, có thể giữ file để restart hoặc xóa theo chính sách.
        return null;
    }
}
```

publishStagingFile() là thao tác ứng dụng, ví dụ rename file trong cùng filesystem. Cần kiểm tra điều kiện atomic move mà filesystem hỗ trợ. Nếu file là đầu vào cho restart, không xóa nó chỉ vì step hiện tại thất bại. Với output cần giữ để chẩn đoán, có thể chuyển sang thư mục quarantine thay vì xóa.

Với FlatFileItemWriter, ưu tiên dùng writer có sẵn và cấu hình name ổn định, saveState phù hợp để tận dụng cơ chế transaction-aware writing và restart state của Spring Batch. Nếu viết writer file tùy chỉnh, phải tự xác định cách rollback nội dung, khôi phục vị trí ghi và chống ghi trùng.

## 8. Cleanup tài nguyên database và connection

Khi dùng JdbcCursorItemReader, JdbcPagingItemReader, JPA reader hoặc writer, hãy để Spring Batch và Spring transaction infrastructure quản lý resource theo lifecycle của component. Không tự đóng connection được lấy từ transaction-bound datasource trong lúc chunk còn đang chạy.

Những nguyên tắc cần nhớ:

- Dùng JdbcTemplate hoặc repository được cấu hình với datasource/transaction manager phù hợp.
- Không giữ Connection, ResultSet hoặc EntityManager trong static field.
- Nếu tự mở resource, đóng trong ItemStream.close() hoặc try-with-resources khi phạm vi sử dụng đã kết thúc.
- Không đóng resource do transaction manager quản lý trước khi transaction hoàn tất.
- Nếu writer dùng datasource khác, hiểu rõ nó có transaction riêng hay không; rollback của step không tự rollback datasource đó.

Không cần tự xóa các hàng database đã được rollback. Transaction manager thực hiện việc đó cho resource transactional. Nếu thấy dữ liệu vẫn còn, hãy kiểm tra xem thao tác ghi có dùng cùng transaction manager và cùng datasource hay không trước khi viết một cleanup delete thủ công.

## 9. Message queue và acknowledgement sau rollback

Với reader lấy message từ queue, việc rollback database không nhất thiết trả message về queue. Điều đó phụ thuộc broker, session/acknowledgement mode và việc transaction của broker có được phối hợp với transaction database hay không.

Trong một số cấu hình transactional queue, message được giữ trong transaction của broker và có thể được redeliver khi transaction rollback. Spring Batch có tùy chọn readerIsTransactionalQueue() trong cấu hình fault-tolerant step cho trường hợp reader lấy item từ transactional queue; tùy chọn này điều chỉnh việc framework buffer item đọc được, vì bản thân queue transaction có thể quản lý việc phát lại message.

Ví dụ minh họa cấu hình:

```java
return new StepBuilder("consumeEventsStep", jobRepository)
    .<Event, EventResult>chunk(50, transactionManager)
    .reader(eventReader)
    .processor(eventProcessor)
    .writer(eventWriter)
    .faultTolerant()
    .readerIsTransactionalQueue()
    .build();
```

Chỉ dùng tùy chọn này khi reader thực sự đọc từ transactional queue với semantics rollback/redelivery phù hợp. Nó không tự tạo transaction phân tán giữa mọi broker và database. Nếu message đã được ack/commit ở broker nhưng database transaction rollback, message có thể không được gửi lại; nếu message được redeliver, consumer có thể nhận lại cùng event. Dùng inbox/idempotency key và cơ chế đối soát để bảo đảm xử lý lặp an toàn.

## 10. Side effect ngoài transaction không thể cleanup bằng rollback

Một processor hoặc writer có thể gọi API, gửi email hoặc publish message. Nếu thao tác đó thành công rồi chunk transaction rollback, hệ thống bên ngoài không biết database đã rollback và không tự thu hồi tác động.

Ví dụ:

```text
Processor gọi payment API -> charge thành công
          |
          v
Writer ghi database -> lỗi
          |
          v
Chunk rollback
          |
          v
Payment vẫn đã được thực hiện
```

Không nên gọi API charge trực tiếp trong processor rồi hy vọng afterChunkError() có thể hoàn tác. Nếu dịch vụ thanh toán hỗ trợ idempotency key, hãy dùng khóa ổn định theo nghiệp vụ để lần retry không tạo charge thứ hai. Nếu cần hủy giao dịch đã tạo, gọi API compensation riêng và lưu trạng thái của quá trình bù.

Với email hoặc message, một cách an toàn hơn là ghi ý định gửi vào outbox cùng transaction với dữ liệu nghiệp vụ. Sau khi transaction commit, dispatcher riêng gửi event và cập nhật trạng thái. Consumer cũng cần idempotency vì message có thể được gửi lại nếu dispatcher dừng giữa publish và ghi nhận hoàn tất.

## 11. Transactional outbox để tránh cleanup thủ công

Outbox giúp tách việc lưu ý định nghiệp vụ khỏi việc thực hiện side effect:

```text
Chunk transaction
    |
    +-- Ghi dữ liệu nghiệp vụ
    |
    +-- Ghi outbox event (PENDING)
    |
    +-- COMMIT
             |
             v
      Outbox dispatcher
             |
             +-- Gửi API/message
             |
             +-- Đánh dấu SENT
```

Nếu chunk rollback, cả dữ liệu nghiệp vụ và outbox event cùng rollback khi chúng nằm trong cùng database transaction. Không cần một cleanup job xóa event chưa gửi của chunk thất bại vì event đó chưa được commit.

Nếu dispatcher gửi thành công nhưng dừng trước khi đánh dấu SENT, event có thể được gửi lại. Consumer/API đích phải nhận diện eventId để không lặp tác động. Outbox cung cấp mô hình delivery ít nhất một lần trong nhiều triển khai, không phải cam kết exactly-once trên toàn hệ thống.

## 12. Dùng afterStep để xử lý hậu kỳ

StepExecutionListener.afterStep() được gọi khi step kết thúc. Đây là nơi phù hợp để thực hiện một số việc hậu kỳ dựa trên trạng thái cuối, ví dụ publish file staging khi thành công hoặc ghi metric tổng kết.

```java
public class StepFinalizationListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED) {
            // Công bố artifact đã hoàn tất.
        } else if (stepExecution.getStatus() == BatchStatus.FAILED) {
            // Ghi nhận trạng thái thất bại; giữ artifact nếu cần restart.
        }
        return null;
    }
}
```

Không nên xem afterStep() là nơi đảm bảo compensation cho mọi side effect. Callback có thể thực hiện khi step kết thúc bình thường theo lifecycle của Spring Batch, nhưng không thể chạy nếu JVM bị kill đột ngột. Ngoài ra, step FAILED vẫn có thể được restart; xóa toàn bộ file hoặc checkpoint ngay trong afterStep() có thể phá hỏng khả năng tiếp tục.

Hãy phân biệt cleanup tài nguyên đang mở với cleanup artifact bền vững. Đóng stream trong ItemStream.close(); quyết định xóa staging file dựa trên trạng thái terminal, chính sách restart và retention.

## 13. Cleanup khi step bị restart

Sau rollback, job có thể retry chunk trong cùng execution hoặc thất bại rồi được restart thành một JobExecution mới. Cleanup không được xóa trạng thái mà lần restart cần dùng.

Với reader triển khai ItemStream, update(ExecutionContext) lưu checkpoint tại ranh giới chunk. Khi chunk rollback, checkpoint bền vững gần nhất vẫn là mốc phục hồi. Reader được mở lại với context đã lưu để tiếp tục từ vị trí phù hợp.

Các nguyên tắc:

- Giữ nguyên checkpoint cuối cùng đã commit.
- Không xóa file đầu vào, token hoặc dữ liệu nguồn mà reader cần để restart.
- Dọn buffer trong bộ nhớ của lần xử lý thất bại, nhưng không xóa dữ liệu bền vững đã commit.
- Dùng tên staging file gắn với JobInstance/JobExecution để phân biệt lần chạy.
- Nếu file nguồn thay đổi, xác minh checksum hoặc định danh nguồn trước khi tiếp tục từ checkpoint cũ.
- Bảo đảm writer idempotent nếu item chưa commit có thể được xử lý lại.

Nếu execution đã được đánh dấu terminal và không còn được restart, một tác vụ cleanup riêng có thể xóa artifact tạm sau thời gian retention. Cách làm này an toàn hơn xóa ngay mọi thứ khi afterStep() nhìn thấy FAILED.

## 14. Compensation cho nghiệp vụ đã thực hiện bên ngoài

Khi một side effect đã xảy ra và không thể rollback, cần xác định có thể bù bằng nghiệp vụ hay không. Ví dụ:

- Một payment đã capture có thể được refund.
- Một reservation có thể được cancel.
- Một message đã được consumer áp dụng có thể cần một event điều chỉnh.
- Một file đã publish có thể cần đánh dấu invalid và phát hành phiên bản thay thế.

Compensation không nhất thiết khôi phục hệ thống về đúng trạng thái trước đó. Nó thường tạo một hành động nghiệp vụ mới để cân bằng tác động trước đó. Vì vậy, cần lưu định danh giao dịch gốc, trạng thái compensation, số lần thử và kết quả cuối.

Một quy trình compensation nên:

1. Có định danh ổn định liên kết với tác động gốc.
2. Có thể retry mà không tạo bù trùng.
3. Lưu trạng thái PENDING, COMPLETED hoặc FAILED ở nơi bền vững.
4. Có cảnh báo khi compensation vượt số lần thử hoặc cần can thiệp thủ công.
5. Không chạy compensation chỉ vì một chunk rollback nếu side effect thực tế chưa được xác nhận.

Không thể viết một finally chung để hoàn tác mọi API. Mỗi dịch vụ bên ngoài cần một hợp đồng bù trừ và quy tắc idempotency riêng.

## 15. Kiểm thử cleanup sau rollback

Nên có integration test với database test thật để xác nhận transaction rollback, cùng test riêng cho resource ngoài transaction.

Một kịch bản cơ bản:

1. Chunk đầu ghi dữ liệu và commit thành công.
2. Chunk tiếp theo ghi một số item rồi writer ném exception.
3. Step kết thúc FAILED nếu không có retry/skip phù hợp.
4. Database chỉ còn dữ liệu của chunk đã commit trước đó.
5. Resource mở được đóng theo lifecycle khi step kết thúc.
6. Buffer tạm không mang item cũ sang lần thử tiếp theo.

Ví dụ writer cố ý lỗi ở lần gọi thứ hai:

```java
public class FailingWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;
    private int calls;

    public FailingWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        calls++;
        for (Order order : chunk) {
            jdbcTemplate.update(
                "insert into imported_order(order_id) values (?)",
                order.getId()
            );
        }

        if (calls == 2) {
            throw new IllegalStateException("Simulated failure");
        }
    }
}
```

Để test chứng minh rollback, JdbcTemplate phải dùng cùng datasource và transaction manager với step. Không bọc toàn bộ test method trong một transaction ngoài khiến các chunk đã commit của step bị rollback khi test kết thúc. Sau khi job thất bại, truy vấn database để xác nhận dữ liệu của chunk đầu vẫn còn và dữ liệu chunk thứ hai đã được hoàn tác.

Các test bổ sung nên xác nhận:

- afterChunkError() được gọi khi chunk rollback.
- ItemStream.close() giải phóng stream/connection sau khi step kết thúc theo lifecycle.
- Reader khôi phục checkpoint sau restart.
- File staging được giữ hoặc xóa theo đúng chính sách.
- API/message đã thực hiện bên ngoài transaction không bị giả định là đã rollback.
- Idempotency ngăn side effect bị lặp khi chunk hoặc job chạy lại.

## 16. Những lỗi thường gặp khi cleanup sau rollback

**Xóa dữ liệu đã commit để “dọn chunk”:** rollback chỉ hoàn tác transaction chưa commit. Xóa thêm có thể làm mất dữ liệu của chunk thành công trước đó.

**Đóng reader trong afterChunkError():** step có thể retry và tiếp tục dùng reader. Đóng resource ở đây làm hỏng lifecycle; dùng close() khi step kết thúc.

**Dựa vào finally để đảo ngược API call:** finally chỉ chạy code trong process hiện tại, không thể rollback dịch vụ bên ngoài. Dùng idempotency hoặc compensation.

**Xóa checkpoint khi step FAILED:** job có thể được restart. Giữ context và dữ liệu nguồn cần thiết cho checkpoint cuối đã commit.

**Giữ buffer mutable trong singleton:** item của chunk rollback có thể còn trong buffer và bị ghi lại. Tránh state theo chunk hoặc dọn đúng phạm vi, có kiểm soát thread.

**Giả định file tự rollback cùng database:** file là resource riêng. Dùng staging, transaction-aware writer hoặc cơ chế publish/cleanup riêng.

**Dùng afterStep như cơ chế đảm bảo chạy mọi lúc:** JVM có thể bị kill trước callback. Tác vụ cleanup tồn đọng nên có thể chạy lại và quét theo execution state.

**Cho rằng queue message luôn redeliver:** acknowledgement và transaction phụ thuộc broker. Kiểm tra cấu hình transactional queue, ack mode và cơ chế idempotency.

**Cleanup ngay khi thấy FAILED:** FAILED có thể là trạng thái có thể restart. Chỉ xóa artifact khi đã xác định execution không còn cần phục hồi.

## 17. Quy trình thiết kế cleanup trong production

Trước tiên, liệt kê resource mà step sử dụng: database, file, stream, cache, queue, API và buffer trong bộ nhớ. Với từng resource, xác định nó có tham gia transaction chunk hay không, ai sở hữu lifecycle và cách phục hồi sau rollback.

Tiếp theo, để transaction manager hoàn tác các thao tác database transactional. Dùng ItemStream.open/update/close để quản lý resource và checkpoint. Dùng ChunkListener.afterChunkError() cho quan sát hoặc cleanup tạm theo chunk; dùng afterStep()/afterJob() cho hậu kỳ dựa trên trạng thái terminal. Không xóa dữ liệu cần cho restart.

Với file và object storage, dùng staging và chỉ công bố artifact khi step/job thành công. Với queue, xác định ack/redelivery semantics. Với API, email và message, dùng outbox, idempotency hoặc compensation thay vì giả định rollback database sẽ thu hồi tác động.

Cuối cùng, kiểm thử lỗi giữa chunk, rollback, retry, restart và process interruption. Cleanup nên idempotent để có thể chạy lại khi ứng dụng dừng giữa chừng. Theo dõi artifact staging tồn đọng, resource leak, message redelivery và compensation pending để vận hành có thể phát hiện và xử lý các trường hợp không được dọn hoàn tất.

Cleanup sau rollback là việc quản lý đúng từng loại trạng thái sau khi một chunk thất bại. Database transaction tự hoàn tác dữ liệu thuộc nó; ItemStream đóng tài nguyên theo lifecycle; listener hỗ trợ quan sát lỗi; còn side effect bên ngoài cần outbox, idempotency hoặc compensation. Khi tách rõ các ranh giới này, step có thể retry và restart mà không làm mất checkpoint, rò rỉ tài nguyên hoặc tạo tác động nghiệp vụ trùng lặp.
