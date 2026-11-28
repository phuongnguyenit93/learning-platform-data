# Ranh giới transaction cho một lệnh hoặc một nhóm bản ghi

Một command CLI có thể cập nhật nhiều bảng, nhập hàng trăm bản ghi hoặc tạo dữ liệu liên quan trong cùng một thao tác. Nếu chương trình dừng giữa chừng, dữ liệu có thể chỉ được ghi một phần. Spring transaction management giúp xác định phần công việc nào phải commit cùng nhau và phần nào có thể được commit độc lập.

Với Spring Shell, command là điểm tiếp nhận input và trả kết quả cho terminal. Ranh giới transaction nên được thiết kế quanh một đơn vị nghiệp vụ có thể xác định rõ: toàn bộ một lần chạy command, một nhóm bản ghi (chunk), hoặc từng bản ghi. Bài viết trình bày cách chọn ranh giới, dùng `@Transactional` và `TransactionTemplate`, xử lý rollback, cũng như kiểm thử để xác nhận dữ liệu thực sự được commit hoặc rollback.

## 1. Transaction bảo vệ điều gì?

Transaction gom nhiều thao tác dữ liệu thành một đơn vị. Với transaction cơ sở dữ liệu quan hệ, mục tiêu thường được mô tả bằng bốn thuộc tính ACID:

- **Atomicity:** hoặc tất cả thao tác trong transaction được commit, hoặc tất cả bị rollback.
- **Consistency:** các ràng buộc dữ liệu được giữ sau khi transaction kết thúc.
- **Isolation:** các transaction đồng thời không nhìn thấy trạng thái trung gian theo cách vi phạm mức cô lập đã chọn.
- **Durability:** dữ liệu đã commit được lưu bền vững theo bảo đảm của hệ quản trị cơ sở dữ liệu.

Ví dụ command `account-transfer` cần ghi nợ tài khoản nguồn và ghi có tài khoản đích. Nếu chỉ một thao tác được lưu, tổng số dư sẽ sai. Hai thao tác phải nằm trong cùng một transaction:

```text
account-transfer
       |
       v
  BEGIN TRANSACTION
       |
       +---- trừ tiền tài khoản nguồn
       |
       +---- cộng tiền tài khoản đích
       |
       v
  COMMIT nếu tất cả thành công
  ROLLBACK nếu có lỗi cần rollback
```

Transaction không tự bảo đảm tính đúng đắn của nghiệp vụ. Nó chỉ quản lý việc commit/rollback các tài nguyên có tham gia transaction. Command vẫn phải xác thực số tiền, quyền truy cập, tài khoản tồn tại và các quy tắc khác.

## 2. Spring Shell command và service transaction

Trong Spring Shell 4, command khai báo bằng `@Command` trên method của một Spring bean, thường là class có `@Component`. Command method nhận argument/option, gọi service và trả nội dung cho shell.

Nên phân chia trách nhiệm như sau:

```text
Người dùng / script
        |
        v
Spring Shell command bean
  - đọc option và argument
  - đọc/parse file đầu vào
  - gọi service
  - trình bày kết quả hoặc lỗi
        |
        v
Application service (@Transactional)
  - kiểm tra quy tắc nghiệp vụ
  - ghi nhiều repository
  - trả kết quả nghiệp vụ
        |
        v
TransactionManager
  - BEGIN / COMMIT / ROLLBACK
```

Command là adapter của terminal. Service định nghĩa đơn vị nghiệp vụ cần nhất quán. Đặt `@Transactional` trên public method của service giúp cùng logic có thể được gọi từ Spring Shell, REST API, scheduler hoặc test mà không phụ thuộc vào giao diện gọi.

Về kỹ thuật, một command class cũng là Spring bean nên có thể tham gia proxy transaction nếu method được gọi qua proxy. Tuy nhiên, không nên để ranh giới dữ liệu phụ thuộc vào cách Spring Shell gọi method. Tách transaction vào service làm rõ phạm vi nghiệp vụ và tránh để việc parse input hoặc in output kéo dài transaction.

## 3. Chọn phạm vi: một command, một chunk hay một record

Không có một ranh giới duy nhất phù hợp cho mọi command. Hãy chọn theo yêu cầu nhất quán và kích thước dữ liệu.

| Ranh giới | Cách hoạt động | Khi phù hợp | Đánh đổi |
|---|---|---|---|
| Toàn bộ command | Tất cả thay đổi của một lần gọi commit cùng nhau | Một thao tác nghiệp vụ nhỏ, cần all-or-nothing | Transaction có thể dài nếu xử lý nhiều dữ liệu |
| Một chunk gồm N records | Mỗi nhóm được commit độc lập | Import lớn, chấp nhận các nhóm trước đã lưu khi nhóm sau lỗi | Cần báo cáo tiến độ và hỗ trợ chạy lại an toàn |
| Từng record | Mỗi bản ghi có transaction riêng | Bản ghi độc lập, muốn cô lập lỗi từng mục | Nhiều lần begin/commit, chi phí cao |

Ví dụ import 1.000 dòng:

- Một transaction cho cả 1.000 dòng: nếu dòng 999 lỗi, toàn bộ 1.000 dòng rollback.
- Chunk 100 dòng: 10 transaction; nếu chunk thứ 7 lỗi, 6 chunk đầu đã commit, chunk thứ 7 rollback.
- Một transaction mỗi dòng: tối đa 1.000 transaction; dòng lỗi không ảnh hưởng các dòng đã commit trước đó.

Hãy thống nhất chính sách này với người dùng command. Thông báo “import thất bại” cần nói rõ liệu các nhóm trước đã được lưu hay toàn bộ lần chạy đã rollback.

## 4. Ranh giới cho toàn bộ một command

Với command có lượng dữ liệu vừa phải và yêu cầu tất cả hoặc không gì cả, tạo một public service method có `@Transactional`.

Ví dụ ứng dụng quản lý hóa đơn. Command đọc file và parse dữ liệu trước; service kiểm tra toàn bộ lô và ghi các hóa đơn trong một transaction.

```java
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

import org.springframework.shell.core.command.annotation.Command;
import org.springframework.shell.core.command.annotation.Option;
import org.springframework.stereotype.Component;

@Component
public class InvoiceCommands {

    private final InvoiceCsvReader csvReader;
    private final InvoiceImportService importService;

    public InvoiceCommands(
            InvoiceCsvReader csvReader,
            InvoiceImportService importService) {
        this.csvReader = csvReader;
        this.importService = importService;
    }

    @Command(name = "invoice-import", description = "Import invoices from a CSV file")
    public String importInvoices(@Option(longName = "file") String file) {
        try {
            List<InvoiceInput> rows = csvReader.read(Path.of(file));
            ImportSummary summary = importService.importAll(rows);
            return "Imported " + summary.importedCount() + " invoices.";
        }
        catch (IOException ex) {
            throw new IllegalArgumentException("Cannot read input file: " + file, ex);
        }
        catch (ImportRejectedException ex) {
            return "Import rejected: " + ex.getMessage();
        }
    }
}
```

Exception type:

```java
public class ImportRejectedException extends Exception {
    public ImportRejectedException(String message) {
        super(message);
    }
}
```

Service:

```java
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceImportService {

    private final InvoiceRepository invoiceRepository;
    private final InvoiceValidator validator;

    public InvoiceImportService(
            InvoiceRepository invoiceRepository,
            InvoiceValidator validator) {
        this.invoiceRepository = invoiceRepository;
        this.validator = validator;
    }

    @Transactional(rollbackFor = ImportRejectedException.class)
    public ImportSummary importAll(List<InvoiceInput> rows)
            throws ImportRejectedException {

        validator.validateAll(rows);
        List<Invoice> invoices = rows.stream()
                .map(Invoice::from)
                .toList();

        invoiceRepository.saveAll(invoices);
        invoiceRepository.flush();

        return new ImportSummary(invoices.size());
    }
}
```

`InvoiceRepository` trong ví dụ có thể là Spring Data `JpaRepository<Invoice, Long>`. `flush()` đẩy các thay đổi đang được ORM giữ lại xuống database để một số lỗi constraint xuất hiện sớm hơn; commit vẫn do transaction interceptor thực hiện sau khi method hoàn tất.

Điểm cần chú ý:

1. Đọc file và parse CSV diễn ra trước khi mở transaction, giảm thời gian giữ connection và lock.
2. `importAll()` là một public method trên Spring bean và được gọi từ bean khác qua proxy.
3. Tất cả thao tác repository trong method tham gia cùng transaction mặc định.
4. Nếu validation ném `ImportRejectedException`, cấu hình `rollbackFor` yêu cầu rollback dù đây là checked exception.
5. Khi service trả về thành công qua proxy, transaction đã được commit; nếu commit thất bại, lỗi có thể được ném ra tại điểm gọi service.

Với dữ liệu nhỏ và cần tính nguyên tử của toàn bộ lệnh, đây thường là lựa chọn dễ hiểu nhất.

## 5. Bật transaction management và transaction manager

`@Transactional` là metadata. Nó chỉ có hiệu lực khi ứng dụng có transaction infrastructure và một transaction manager phù hợp.

Trong ứng dụng Spring Boot dùng JDBC hoặc Spring Data JPA, starter và datasource thường cho phép Boot auto-configure transaction manager tương ứng. Nếu tự cấu hình Spring Framework, có thể bật annotation-driven transaction management và khai báo `PlatformTransactionManager`:

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionConfiguration {

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Với JPA, dùng `JpaTransactionManager` gắn với `EntityManagerFactory`; không dùng `DataSourceTransactionManager` thay thế một cách tùy tiện cho transaction JPA. Nếu ứng dụng có nhiều datasource hoặc nhiều transaction manager, cần chọn đúng manager bằng qualifier/name trên `@Transactional`.

Không khai báo transaction manager giả hoặc chỉ thêm annotation mà thiếu cấu hình. Hãy kiểm tra bean `PlatformTransactionManager`/`TransactionManager` thực tế trong application context.

## 6. Mặc định của `@Transactional` và rollback rules

Các mặc định quan trọng của Spring `@Transactional`:

| Thuộc tính | Mặc định |
|---|---|
| `propagation` | `REQUIRED` |
| `isolation` | `DEFAULT` của transaction manager/database |
| `readOnly` | `false` |
| `timeout` | Theo mặc định của transaction system hoặc không giới hạn |
| Rollback | `RuntimeException` và `Error` |
| Checked exception | Không rollback theo mặc định |

Nếu muốn checked exception cũng rollback, khai báo:

```java
@Transactional(rollbackFor = ImportRejectedException.class)
public ImportSummary importAll(List<InvoiceInput> rows)
        throws ImportRejectedException {
    // ...
}
```

Có thể dùng `noRollbackFor` cho loại exception mà nghiệp vụ chủ ý vẫn commit. Hãy hạn chế cấu hình này vì nó dễ khiến người đọc hiểu nhầm một lần chạy đã thất bại nhưng dữ liệu vẫn được lưu.

Đối với lỗi nghiệp vụ cần rollback, cách rõ ràng thường là ném một exception phù hợp để nó đi qua transaction proxy. Không bắt exception rồi trả về chuỗi lỗi bên trong method transactional mà không đánh dấu rollback.

## 7. Vì sao catch exception bên trong transaction có thể làm dữ liệu commit?

Transaction interceptor quyết định commit hay rollback dựa trên kết quả method và rollback rules. Nếu code bắt exception rồi trả về bình thường, interceptor có thể xem method đã hoàn thành thành công.

Ví dụ dễ gây lỗi:

```java
@Transactional
public ImportSummary importAll(List<InvoiceInput> rows) {
    try {
        invoiceRepository.saveAll(map(rows));
        riskyUpdate();
        return new ImportSummary(rows.size());
    }
    catch (RuntimeException ex) {
        return new ImportSummary(0); // Method trả bình thường
    }
}
```

Trong trường hợp exception chưa đánh dấu transaction rollback-only, method trả bình thường có thể dẫn tới commit các thay đổi đã thực hiện. Một số lỗi persistence có thể tự đánh dấu rollback-only; không nên dựa vào hành vi đó như một chính sách chung.

Cách xử lý rõ hơn là để exception đi ra khỏi service, sau đó chuyển thành thông báo CLI ở command layer:

```java
@Command(name = "invoice-import")
public String importInvoices(@Option(longName = "file") String file) {
    try {
        return importService.importAll(csvReader.read(Path.of(file))).message();
    }
    catch (ImportRejectedException ex) {
        // Service proxy đã xử lý rollback trước khi exception tới đây.
        return "Import rejected: " + ex.getMessage();
    }
}
```

Nếu cần ghi nhận lỗi trong transaction và tiếp tục xử lý có chủ đích, phải thiết kế rollback policy rõ ràng, ví dụ dùng `TransactionStatus.setRollbackOnly()` với `TransactionTemplate`, hoặc tách từng đơn vị lỗi sang transaction riêng.

## 8. Hiểu proxy và lỗi self-invocation

Ở chế độ mặc định, Spring áp dụng `@Transactional` bằng AOP proxy. Chỉ lời gọi đi qua proxy mới được transaction interceptor xử lý. Một method gọi method khác trong cùng object (`this.otherMethod()`) không đi qua proxy.

Ví dụ không tạo transaction mới như kỳ vọng:

```java
@Service
public class ImportService {

    public void importCommand() {
        saveAll(); // self-invocation
    }

    @Transactional
    public void saveAll() {
        // Không được proxy chặn khi gọi từ importCommand() trong cùng object.
    }
}
```

Tách method transactional sang bean riêng:

```java
@Service
public class ImportCommandService {

    private final InvoiceWriter invoiceWriter;

    public ImportCommandService(InvoiceWriter invoiceWriter) {
        this.invoiceWriter = invoiceWriter;
    }

    public void runImport(List<InvoiceInput> rows) {
        invoiceWriter.saveAll(rows); // Lời gọi qua Spring proxy
    }
}

@Service
public class InvoiceWriter {

    @Transactional
    public void saveAll(List<InvoiceInput> rows) {
        // Ghi dữ liệu trong transaction.
    }
}
```

Ưu tiên method public trên concrete Spring bean và constructor injection. Không tự tạo service bằng `new`, vì object đó nằm ngoài Spring container và không có transactional proxy.

## 9. Ranh giới transaction cho một chunk bản ghi

Với file lớn, giữ một transaction cho toàn bộ file có thể làm transaction kéo dài, giữ lock/connection lâu và tăng bộ nhớ của persistence context. Nếu nghiệp vụ cho phép một phần dữ liệu đã commit trước khi phần sau lỗi, có thể chia file thành các chunk.

Ví dụ orchestrator không có `@Transactional`, còn writer là bean riêng và mỗi lần gọi ghi một chunk:

```java
@Component
public class CustomerImportCommands {

    private final CsvCustomerReader reader;
    private final CustomerChunkWriter chunkWriter;

    public CustomerImportCommands(
            CsvCustomerReader reader,
            CustomerChunkWriter chunkWriter) {
        this.reader = reader;
        this.chunkWriter = chunkWriter;
    }

    @Command(name = "customer-import")
    public String importCustomers(
            @Option(longName = "file") String file,
            @Option(longName = "chunk-size") int chunkSize) {

        int committed = 0;

        for (List<CustomerInput> chunk : reader.readChunks(Path.of(file), chunkSize)) {
            chunkWriter.writeChunk(chunk);
            committed += chunk.size();
        }

        return "Committed " + committed + " records.";
    }
}
```

Writer:

```java
@Service
public class CustomerChunkWriter {

    private final CustomerRepository repository;

    public CustomerChunkWriter(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void writeChunk(List<CustomerInput> chunk) {
        repository.saveAll(chunk.stream()
                .map(Customer::from)
                .toList());
        repository.flush();
    }
}
```

Trong ví dụ, mỗi lần gọi `writeChunk()` đi qua proxy và tạo transaction riêng vì không có transaction bên ngoài. `REQUIRED` mặc định sẽ bắt đầu transaction nếu chưa có transaction hiện hành, commit khi chunk thành công và rollback chunk hiện tại khi exception cần rollback thoát khỏi method.

Chính sách khi chunk lỗi cần được xác định:

- **Dừng ngay:** các chunk trước vẫn đã commit; chunk lỗi rollback; các chunk sau chưa chạy.
- **Ghi nhận và tiếp tục:** chỉ tiếp tục nếu lỗi có thể cô lập an toàn và mỗi chunk có transaction độc lập. Ghi rõ số bản ghi thành công/thất bại.
- **Retry:** chỉ retry khi thao tác có thể chạy lặp an toàn hoặc có idempotency key.

Đừng khai báo `@Transactional` ở orchestrator nếu mục tiêu là commit từng chunk; nếu orchestrator mở transaction ngoài, các lời gọi `REQUIRED` bên trong sẽ tham gia transaction đó và không commit độc lập.

## 10. `REQUIRES_NEW` và khi nào cần dùng

`Propagation.REQUIRED` là mặc định: tham gia transaction hiện có hoặc tạo transaction mới nếu chưa có.

`Propagation.REQUIRES_NEW` luôn tạo transaction vật lý mới. Nếu đã có transaction bên ngoài, Spring tạm suspend transaction đó trong lúc transaction mới chạy.

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditEntry(AuditEntry entry) {
    auditRepository.save(entry);
}
```

Một số trường hợp có thể dùng `REQUIRES_NEW`:

- Ghi audit cần commit độc lập với transaction nghiệp vụ.
- Mỗi chunk phải commit độc lập ngay cả khi caller có transaction.
- Ghi trạng thái lỗi hoặc tiến độ theo chính sách riêng.

Đổi lại, transaction ngoài có thể vẫn giữ connection hoặc lock trong khi transaction mới chạy. Dùng quá nhiều `REQUIRES_NEW` có thể tăng tải connection pool và tạo tình trạng chờ tài nguyên. Với import theo chunk, thường nên để orchestrator không có transaction và dùng `REQUIRED` trên writer; chỉ dùng `REQUIRES_NEW` khi thật sự cần tách khỏi transaction đang tồn tại.

`NESTED` thường dựa trên savepoint và chỉ hoạt động nếu transaction manager/tài nguyên hỗ trợ. Không giả định `NESTED` luôn có thể dùng với mọi JPA provider hoặc mọi database.

## 11. TransactionTemplate cho ranh giới động

Khi ranh giới transaction phụ thuộc vào vòng lặp hoặc cấu hình runtime, `TransactionTemplate` là lựa chọn lập trình tường minh. Spring khuyến nghị cách này cho imperative transaction management thay vì tự gọi trực tiếp `PlatformTransactionManager` trong phần lớn trường hợp.

```java
import java.util.List;

import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class CustomerChunkTransaction {

    private final TransactionTemplate transactionTemplate;
    private final CustomerRepository repository;

    public CustomerChunkTransaction(
            PlatformTransactionManager transactionManager,
            CustomerRepository repository) {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.transactionTemplate.setTimeout(30);
        this.repository = repository;
    }

    public void writeChunk(List<Customer> customers) {
        transactionTemplate.executeWithoutResult(status -> {
            repository.saveAll(customers);
            repository.flush();
        });
    }
}
```

Mỗi lần gọi `executeWithoutResult(...)` chạy callback trong transaction do template quản lý. Nếu callback ném runtime exception, template rollback rồi ném lỗi cho caller.

Có thể chủ động đánh dấu rollback-only:

```java
transactionTemplate.executeWithoutResult(status -> {
    repository.saveAll(customers);
    if (businessRuleFailed(customers)) {
        status.setRollbackOnly();
    }
});
```

Khi dùng `TransactionTemplate`, hãy giữ cấu hình timeout/isolation cố định cho instance được chia sẻ. Nếu các luồng cần transaction settings khác nhau, tạo template riêng thay vì thay đổi cấu hình của một instance đang được dùng đồng thời.

Chọn `@Transactional` khi ranh giới gắn tự nhiên với một method nghiệp vụ. Chọn `TransactionTemplate` khi cần bao một đoạn code động, nhiều lần lặp hoặc chính sách transaction thay đổi theo từng chunk.

## 12. Khi nào nên dùng Spring Batch?

Một vòng lặp chunk tự viết có thể đủ cho file vừa phải. Khi quy trình import lớn cần restart, retry, skip, checkpoint, theo dõi tiến độ và thống kê, hãy cân nhắc Spring Batch.

Spring Batch dùng chunk-oriented processing: đọc và xử lý từng item, gom đủ `commit-interval`, ghi cả chunk bằng `ItemWriter`, sau đó commit transaction. Ví dụ:

```java
@Bean
Step importCustomers(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomers", jobRepository)
            .<CustomerInput, Customer>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Trong ví dụ, mỗi chunk 100 item là một transaction step. `commit-interval` bằng 1 sẽ commit sau mỗi item; cách này có thể tốn chi phí begin/commit hơn so với xử lý một nhóm hợp lý.

Chọn Spring Batch khi command thực chất khởi chạy một batch job cần quản lý vòng đời. Spring Shell có thể đóng vai trò giao diện khởi chạy job và hiển thị `JobExecution`/`ExitStatus`, còn Spring Batch quản lý đọc, xử lý, ghi và commit theo chunk.

## 13. Kiểm tra và xác thực dữ liệu trước transaction

Không phải công việc nào cũng cần nằm trong transaction. Các thao tác sau thường nên diễn ra trước khi mở transaction ghi dữ liệu:

- Kiểm tra file tồn tại và có quyền đọc.
- Parse CSV/JSON và xác định encoding.
- Kiểm tra cú pháp, định dạng, trường bắt buộc.
- Tính số dòng và checksum của file.
- Chuyển đổi dữ liệu thuần không phụ thuộc database.

Các kiểm tra cần đọc dữ liệu hiện tại từ database hoặc bảo đảm ràng buộc khi ghi có thể cần nằm trong transaction. Tuy nhiên, kiểm tra trước khi ghi không thay thế constraint ở database: hai command chạy đồng thời vẫn có thể cùng vượt qua bước kiểm tra rồi cạnh tranh ghi dữ liệu.

Hãy dùng unique constraint, foreign key, optimistic locking hoặc cơ chế concurrency phù hợp làm lớp bảo vệ cuối cùng. Khi constraint vi phạm, transaction phải rollback theo chính sách đã chọn.

## 14. Side effect bên ngoài transaction database

`@Transactional` với `PlatformTransactionManager` thường quản lý tài nguyên database tham gia cùng transaction. Nó không tự hoàn tác:

- HTTP request đã gửi tới hệ thống khác.
- Email đã gửi.
- File đã ghi hoặc đã đổi tên.
- Message đã publish tới broker không tham gia transaction.
- Tác vụ đã chạy ở thread khác.

Ví dụ, command cập nhật database rồi gửi email ngay trong transaction. Nếu email gửi thành công nhưng commit database thất bại, người nhận vẫn nhận email về một thay đổi chưa được lưu.

Với sự kiện cần phát sau khi dữ liệu commit, có thể dùng transaction-bound event listener hoặc pattern transactional outbox. Outbox ghi sự kiện vào cùng database transaction với dữ liệu nghiệp vụ; một worker riêng đọc outbox và gửi message, có retry và idempotency.

Không gọi dịch vụ từ xa lâu trong transaction nếu có thể tránh. Việc giữ connection và lock trong khi chờ mạng làm tăng contention và rủi ro timeout.

## 15. Idempotency và chạy lại command

Với chunk commit độc lập, tiến trình có thể dừng sau khi một chunk đã commit nhưng trước khi ghi nhận tiến độ ở nơi khác. Khi chạy lại, cùng chunk có thể được xử lý lần nữa.

Để command an toàn khi retry:

- Nhận `run-id` ổn định cho một lần import.
- Xác định khóa nghiệp vụ của từng bản ghi, ví dụ `externalId`.
- Dùng unique constraint hoặc upsert theo chính sách rõ ràng.
- Ghi checkpoint/progress trong cùng transaction với dữ liệu chunk nếu cần bảo đảm không lệch trạng thái.
- Lưu trạng thái chunk: pending, committed, failed.
- Không tạo side effect lặp khi retry; dùng idempotency key ở hệ thống ngoài nếu API hỗ trợ.

Ví dụ một bảng tiến độ import có thể lưu `(run_id, chunk_number)` với unique constraint. Trong cùng transaction ghi chunk, cập nhật chunk tương ứng thành `COMMITTED`. Nếu transaction rollback, cả dữ liệu và trạng thái chunk cùng rollback.

Idempotency không thay thế transaction. Transaction bảo vệ tính nguyên tử của một đơn vị; idempotency giúp xử lý an toàn khi cùng đơn vị được gửi lại.

## 16. Kiểm thử ranh giới transaction

Không chỉ kiểm tra command in ra thông báo thành công. Cần xác nhận trạng thái database sau cả trường hợp thành công và thất bại.

Ví dụ integration test cho transaction toàn command. Test này không tự đánh dấu `@Transactional`, để kết quả commit/rollback của service được quan sát trực tiếp:

```java
@SpringBootTest
class InvoiceImportServiceTests {

    @Autowired
    InvoiceImportService importService;

    @Autowired
    InvoiceRepository invoiceRepository;

    @Test
    void rejectsInvalidBatchBeforeWriting() {
        List<InvoiceInput> rows = List.of(
                new InvoiceInput("INV-001", 100),
                new InvoiceInput("INV-INVALID", -10));

        assertThrows(ImportRejectedException.class,
                () -> importService.importAll(rows));

        assertEquals(0, invoiceRepository.count());
    }
}
```

Test thực tế cần khởi tạo dữ liệu sạch và chọn database test phù hợp. Nếu test method tự mang `@Transactional`, test framework có thể rollback transaction của test ở cuối; điều đó đôi khi che khuất việc service có commit transaction độc lập đúng như mong muốn hay không.

Test trên xác nhận lô không hợp lệ bị từ chối trước khi ghi. Để chứng minh rollback cả những thay đổi đã thực hiện trước khi lỗi xảy ra, bổ sung một test dùng test double/failure hook để ném exception sau `saveAll()` hoặc sau một thao tác repository thứ nhất; sau khi service proxy ném lỗi, xác nhận dữ liệu của thao tác trước cũng không còn trong database.

Ma trận kiểm thử nên bao gồm:

| Trường hợp | Ranh giới toàn command | Ranh giới chunk |
|---|---|---|
| Tất cả dữ liệu hợp lệ | Tất cả commit | Tất cả chunk commit |
| Lỗi giữa quá trình ghi | Toàn bộ command rollback | Chunk hiện tại rollback; chunk trước giữ nguyên |
| Checked exception | Kiểm tra `rollbackFor` | Kiểm tra rollback policy của writer |
| Runtime exception | Rollback theo mặc định | Rollback chunk hiện tại |
| Retry cùng run ID | Không tạo dữ liệu trùng | Không ghi lại chunk đã commit |
| Hai command đồng thời | Constraint/isolation bảo vệ dữ liệu | Constraint/isolation bảo vệ từng chunk |
| Lỗi sau DB commit khi gửi event | Kiểm tra outbox/retry | Kiểm tra outbox trong transaction của chunk |

Ngoài integration test, có thể dùng `TransactionSynchronizationManager.isActualTransactionActive()` trong test hoặc log chẩn đoán để xác nhận đoạn code đang ở trong transaction. Không giữ kiểm tra nội bộ này trong logic nghiệp vụ thông thường.

## 17. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `@Transactional` không rollback | Chưa có transaction manager/infrastructure hoặc method không đi qua proxy | Kiểm tra transaction configuration và Spring bean |
| Một method được đánh dấu transaction nhưng không có transaction | Self-invocation hoặc object được tạo bằng `new` | Tách sang bean khác và gọi qua proxy |
| Checked exception nhưng dữ liệu vẫn commit | Mặc định chỉ rollback RuntimeException/Error | Khai báo `rollbackFor` hoặc dùng exception runtime phù hợp |
| Bắt exception rồi dữ liệu vẫn commit | Method transactional trả về bình thường | Để exception đi qua proxy hoặc đánh dấu rollback-only |
| Chunk trước đã lưu dù command báo lỗi | Mỗi chunk là transaction độc lập | Báo rõ partial progress và hỗ trợ resume/idempotency |
| `REQUIRES_NEW` làm cạn connection pool | Transaction ngoài bị suspend nhưng vẫn giữ tài nguyên | Tránh transaction ngoài dài; chỉ dùng khi cần độc lập |
| Import lớn chậm hoặc giữ lock lâu | Một transaction cho toàn file | Chia chunk hoặc dùng Spring Batch |
| `saveAll()` tưởng như đã commit | `saveAll` không đồng nghĩa commit; flush và commit là bước riêng | Hiểu transaction proxy và kiểm tra trạng thái sau commit |
| Email đã gửi nhưng DB rollback | Email không tham gia transaction database | Dùng outbox hoặc xử lý sau commit với retry |
| Retry tạo bản ghi trùng | Không có idempotency key/unique constraint | Dùng run ID, khóa nghiệp vụ và upsert có quy tắc |
| Transaction không bao phủ thread mới | Imperative transaction thường gắn với execution thread | Truyền công việc qua cơ chế quản lý transaction phù hợp; không tự tách thread trong transaction |

## 18. Checklist thiết kế transaction cho command

- [ ] Đã xác định đơn vị nghiệp vụ cần commit cùng nhau.
- [ ] Đã chọn transaction cho toàn command, từng chunk hoặc từng record.
- [ ] Command chỉ xử lý input/output; service sở hữu transaction nghiệp vụ.
- [ ] Transaction method là public method trên Spring-managed bean và được gọi qua proxy.
- [ ] Đã có `PlatformTransactionManager` phù hợp với JDBC/JPA resource.
- [ ] Đã xác định rollback rules cho checked và unchecked exception.
- [ ] Không bắt/swallow exception bên trong transaction nếu cần rollback.
- [ ] File parsing và kiểm tra cú pháp diễn ra trước transaction ghi khi có thể.
- [ ] Đã chọn chunk size dựa trên kích thước dữ liệu, thời gian và lock contention.
- [ ] Nếu chunk commit riêng, đã xác định chính sách partial success, resume và retry.
- [ ] Đã có unique constraint/idempotency key để chống ghi trùng.
- [ ] Side effect ngoài database được xử lý bằng outbox hoặc cơ chế nhất quán phù hợp.
- [ ] Đã kiểm thử dữ liệu database sau commit và rollback.
- [ ] Đã kiểm tra command behavior khi transaction commit thất bại.
- [ ] Với batch lớn cần restart/retry/skip/checkpoint, đã cân nhắc Spring Batch.

## Tài liệu tham khảo

1. [Spring Shell 4 – Command Registration](https://docs.spring.io/spring-shell/reference/commands/registration.html) – command method được khai báo trong Spring bean.
2. [Spring Shell 4 – `@Command` API](https://docs.spring.io/spring-shell/reference/api/org/springframework/shell/core/command/annotation/Command.html) – annotation đánh dấu method command và yêu cầu declaring class là Spring bean.
3. [Spring Framework – Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) – transaction proxy, propagation, isolation, timeout và rollback defaults.
4. [Spring Framework – Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html) – rollback rules cho checked/unchecked exception.
5. [Spring Framework – Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html) – `TransactionTemplate` và `PlatformTransactionManager`.
6. [Spring Framework – Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html) – `PlatformTransactionManager` và `ReactiveTransactionManager`.
7. [Spring Batch – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html) – đọc, xử lý, ghi chunk trong transaction.
8. [Spring Batch – Commit Interval](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html) – chọn số item trước mỗi lần commit.

Ranh giới transaction quyết định command có thể khôi phục đến đâu khi lỗi xảy ra. Với thao tác nhỏ cần tính nguyên tử, dùng một service method transactional cho toàn bộ nghiệp vụ. Với import lớn chấp nhận tiến độ từng phần, commit theo chunk và thiết kế idempotency, checkpoint cùng thông báo partial success. Hãy để Spring transaction proxy quản lý begin/commit/rollback, kiểm thử trạng thái database thực tế và xử lý riêng các side effect nằm ngoài database.
