# Nhập dữ liệu theo nhóm với giới hạn đồng thời và chính sách lỗi

Một luồng nhập dữ liệu lớn thường phải đọc hàng nghìn hoặc hàng triệu bản ghi, kiểm tra dữ liệu, chuyển thành entity rồi ghi xuống database qua Spring Data Relational R2DBC. Nếu xử lý tuần tự, thời gian hoàn tất có thể quá dài. Nếu tạo quá nhiều thao tác đồng thời, ứng dụng có thể làm cạn connection pool, tăng lock contention hoặc khiến database quá tải.

Giải pháp là chia luồng thành các nhóm có kích thước hữu hạn, giới hạn số nhóm hoặc bản ghi được xử lý cùng lúc, và xác định rõ lỗi nào được bỏ qua, lỗi nào cần retry, lỗi nào phải dừng import. Reactive Streams và Reactor cung cấp các operator như `buffer`, `bufferTimeout`, `flatMap`, `concatMap` và `retryWhen` để xây dựng pipeline có kiểm soát.

Batch size, concurrency, transaction boundary và error policy là bốn quyết định khác nhau. Một batch có thể chứa 500 dòng nhưng chỉ cho phép 3 batch ghi đồng thời. Một lỗi validation có thể chỉ làm từ chối một dòng, trong khi lỗi mất kết nối có thể phải dừng cả job. Nếu transaction theo nhóm bị lỗi, các dòng khác trong cùng nhóm có thể cũng bị rollback.

Bài học này trình bày cách thiết kế pipeline import bằng Flux, chia nhóm có giới hạn, kiểm soát concurrency theo khả năng database, chọn transaction theo dòng hoặc theo nhóm, phân loại lỗi, retry an toàn, bảo đảm idempotency, lưu tiến độ và kiểm thử trên database thật.

## 1. Bức tranh tổng thể của một pipeline import

Một pipeline import thường có các bước:

1. Đọc dữ liệu từ file, message stream hoặc nguồn HTTP.
2. Gán số dòng/khóa nguồn để truy vết.
3. Parse và chuẩn hóa dữ liệu.
4. Validate dữ liệu theo quy tắc nghiệp vụ.
5. Chia các bản ghi thành nhóm hữu hạn.
6. Ghi database với giới hạn concurrency.
7. Phân loại thành công, lỗi dữ liệu và lỗi hạ tầng.
8. Ghi kết quả, tiến độ và checkpoint.
9. Tổng hợp báo cáo import.

~~~text
Nguồn dữ liệu
   |
   v
Flux<ImportRow>
   |
   v
Gán row number / source key
   |
   v
Parse + normalize + validate
   |
   v
Buffer thành batch hữu hạn
   |
   v
flatMap với concurrency giới hạn
   |
   +-------------------------------+
   |                               |
   v                               v
Transaction theo dòng        Transaction theo batch
   |                               |
   v                               v
R2DBC repository / DatabaseClient
   |                               |
   +---------------+---------------+
                   |
                   v
        Kết quả + lỗi + checkpoint
                   |
                   v
             Import report
~~~

Không nhất thiết triển khai mọi bước trong một class. Nên tách parser, validator, writer, error classifier và job coordinator để có thể kiểm thử riêng.

## 2. Vì sao cần chia batch?

Một nguồn dữ liệu lớn không nên được tải toàn bộ vào bộ nhớ trước khi ghi.

Ví dụ cách làm dễ gây vấn đề:

~~~java
List<ImportRow> rows = Files.readAllLines(path)
        .stream()
        .map(this::parse)
        .toList();

return Flux.fromIterable(rows)
        .flatMap(repository::save);
~~~

Cách này có thể:

- Đọc toàn bộ file vào heap.
- Tạo thêm object cho mỗi dòng.
- Phát quá nhiều thao tác ghi cùng lúc.
- Không có giới hạn rõ ràng về số transaction đang chạy.
- Khó resume từ checkpoint nếu process dừng giữa chừng.

Thay vào đó, đọc theo stream và chỉ giữ một lượng dữ liệu hữu hạn:

~~~java
Flux<ImportRow> rows = importFileReader.read(path);

return rows
        .buffer(250)
        .concatMap(this::writeBatch);
~~~

`buffer(250)` gom tối đa 250 phần tử thành một List rồi phát List đó. `concatMap` chờ batch hiện tại hoàn tất trước khi xử lý batch tiếp theo, vì vậy chỉ có một batch đang được xử lý tại một thời điểm trong pipeline này.

Đây là thiết kế đơn giản, dễ kiểm soát và có thứ tự. Nếu cần throughput cao hơn, có thể cho phép nhiều batch chạy đồng thời bằng `flatMap` với concurrency hữu hạn.

## 3. Phân biệt batch size và concurrency

Hai tham số này không giống nhau:

- **Batch size:** số bản ghi trong một nhóm.
- **Concurrency:** số nhóm hoặc thao tác được phép thực thi đồng thời.

Ví dụ batch size 200 và chunk concurrency 4 có thể có tối đa khoảng 800 bản ghi nằm trong các batch đang hoạt động, chưa tính buffer/prefetch và kết quả phụ trợ.

| Batch size | Chunk concurrency | Ý nghĩa |
|---:|---:|---|
| 100 | 1 | Mỗi lần một batch 100 dòng |
| 100 | 4 | Tối đa 4 batch đang xử lý |
| 500 | 2 | Tối đa khoảng 1.000 dòng thuộc các batch đang hoạt động |
| 1.000 | 8 | Có thể tạo áp lực bộ nhớ và database rất lớn |

Không có con số tối ưu cho mọi hệ thống. Cần đo bằng dữ liệu và database gần production.

### 3.1. Batch nhỏ

Ưu điểm:

- Transaction ngắn hơn nếu mỗi batch là một transaction.
- Ít bộ nhớ hơn.
- Lỗi trong một batch ảnh hưởng ít dòng hơn.
- Checkpoint thường xuyên hơn.

Nhược điểm:

- Tăng số lần gọi database.
- Tăng chi phí mở/commit transaction nếu mỗi batch có transaction riêng.
- Có thể giảm hiệu suất nếu mỗi insert quá nhỏ.

### 3.2. Batch lớn

Ưu điểm:

- Có thể giảm số lần round-trip hoặc số transaction.
- Có thể tận dụng bulk insert nếu driver/database hỗ trợ.
- Tăng throughput khi overhead mỗi lần ghi lớn.

Nhược điểm:

- Giữ nhiều object trong memory.
- Transaction dài và lock lâu hơn.
- Rollback có thể làm mất nhiều công việc hơn.
- Một lỗi có thể ảnh hưởng nhiều dòng.
- Có thể chạm giới hạn parameter hoặc statement của database.

Batch size cần được chọn cùng với transaction policy và cách driver thực hiện batch.

## 4. Đọc dữ liệu theo stream và tránh nạp toàn bộ file

Nếu nguồn là file lớn, parser nên phát từng bản ghi thay vì trả một List chứa toàn bộ file.

~~~java
public interface ImportFileReader {
    Flux<ImportRow> read(Path path);
}
~~~

Parser có thể dùng thư viện CSV streaming hoặc đọc từng dòng bằng API phù hợp. Nếu dùng API file blocking, cần cô lập việc đọc file trên scheduler phù hợp hoặc dùng thư viện hỗ trợ non-blocking. R2DBC non-blocking không tự làm parser file blocking trở thành non-blocking.

Gán số dòng ngay khi đọc:

~~~java
Flux<IndexedImportRow> indexedRows =
        reader.read(path)
                .index()
                .map(tuple ->
                        new IndexedImportRow(
                                tuple.getT1() + 1,
                                tuple.getT2()));
~~~

`index()` phát chỉ số bắt đầu từ 0; cộng 1 nếu muốn số dòng hiển thị bắt đầu từ 1. Nếu file có header, parser cần xác định số dòng nguồn thực tế hoặc lưu source offset riêng.

Không chỉ dùng index trong bộ nhớ nếu cần resume sau restart. Với import có thể tiếp tục, hãy lưu source row number hoặc một source key ổn định trong checkpoint.

## 5. Chia batch bằng buffer

Reactor cung cấp nhiều operator gom phần tử.

### 5.1. buffer(size)

~~~java
source.buffer(200)
~~~

Gom tối đa 200 phần tử thành một List. Khi upstream hoàn tất, batch cuối có thể ít hơn 200 phần tử.

### 5.2. bufferTimeout(size, duration)

~~~java
source.bufferTimeout(
        200,
        Duration.ofMillis(300))
~~~

Phát batch khi đạt 200 phần tử hoặc khi hết khoảng thời gian 300 ms. Cách này hữu ích cho luồng liên tục, nơi có thể phải chờ lâu mới đủ batch.

### 5.3. bufferUntil và bufferWhile

Các operator này gom theo điều kiện của dữ liệu, chẳng hạn nhóm theo tenant hoặc loại record. Chúng không thay thế giới hạn batch size nếu một nhóm có thể phát triển không giới hạn. Hãy kiểm soát kích thước tối đa khi nhóm dữ liệu theo key.

### 5.4. Không tạo buffer vô hạn

Tránh tự gom mọi record vào một collection rồi chỉ ghi khi nguồn complete. Nếu nguồn không bao giờ hoàn tất, import sẽ không ghi gì và bộ nhớ tiếp tục tăng.

Một pipeline streaming nên có giới hạn rõ ràng về:

- Số bản ghi trong mỗi batch.
- Số batch đang hoạt động.
- Số phần tử được prefetch.
- Số kết quả/lỗi giữ trong memory.
- Số transaction đang mở.

## 6. Giới hạn concurrency bằng flatMap

Ví dụ cho phép tối đa 4 batch chạy đồng thời:

~~~java
return source
        .buffer(200)
        .flatMap(
                this::writeBatch,
                4,
                1);
~~~

Các tham số của `flatMap(mapper, concurrency, prefetch)`:

- `mapper`: chuyển mỗi batch thành một Publisher.
- `concurrency`: số inner Publisher tối đa được subscribe đồng thời.
- `prefetch`: số phần tử được yêu cầu trước từ mỗi inner publisher.

Trong ví dụ này, tối đa 4 batch được xử lý đồng thời; prefetch là 1 phần tử cho mỗi inner publisher. Chọn prefetch phù hợp với operator và driver, không coi nó là batch size.

### 6.1. flatMap không giữ thứ tự kết quả

Các batch có thể hoàn tất theo thứ tự khác với thứ tự nguồn. Nếu batch thứ hai nhanh hơn batch thứ nhất, kết quả của batch thứ hai có thể được phát trước.

Nếu cần chạy đồng thời nhưng phát kết quả theo thứ tự nguồn:

~~~java
return source
        .buffer(200)
        .flatMapSequential(
                this::writeBatch,
                4,
                1);
~~~

`flatMapSequential` có thể buffer kết quả của batch hoàn tất sớm để chờ batch trước đó. Vì vậy, giữ thứ tự có thể tăng bộ nhớ và độ trễ phát kết quả.

Nếu bắt buộc xử lý tuần tự cả execution lẫn output, dùng:

~~~java
return source
        .buffer(200)
        .concatMap(this::writeBatch);
~~~

### 6.2. flatMap với concurrency trên từng dòng

Không nhất thiết phải gom batch nếu mỗi record có transaction độc lập:

~~~java
return source.flatMap(
        this::importOne,
        8,
        1);
~~~

Ở đây tối đa 8 bản ghi đang được xử lý đồng thời. Cách này phù hợp khi cần partial success theo từng dòng và mỗi dòng có transaction riêng.

### 6.3. Concurrency không đồng nghĩa tạo thread

R2DBC driver thường thực hiện I/O bất đồng bộ. `flatMap` điều khiển số publisher được subscribe cùng lúc; nó không nhất thiết tạo một thread riêng cho mỗi record.

Không dùng `parallel()` hoặc tăng scheduler thread count chỉ để tăng số query. Hãy điều chỉnh concurrency, pool và khả năng chịu tải của database trước.

## 7. Chọn concurrency theo connection pool và database

Nếu R2DBC pool có max size 20, không nên mặc định cho import dùng hết cả 20 connection. API request, health check, background job và tác vụ khác cũng cần connection.

Ví dụ ngân sách:

- Pool max size: 20.
- Dự trữ cho API traffic: 8.
- Dự trữ cho job khác/maintenance: 2.
- Ngân sách tối đa dành cho import: khoảng 10 connection.

Đây chỉ là ví dụ tính toán. Nếu mỗi batch mở một transaction/connection, chunk concurrency cần nằm trong ngân sách đó. Nếu một batch tạo nhiều query song song, số connection/operation thực tế có thể khác.

Công thức tham khảo:

\[
C_{\text{import}}
\leq
P_{\text{pool}}
-
R_{\text{API}}
-
R_{\text{other}}
\]

Trong môi trường nhiều replica, cần tính tổng pool của tất cả instance:

\[
P_{\text{total}}
=
P_{\text{per instance}}
\times
N_{\text{instances}}
\]

Database có giới hạn session, CPU, IOPS, lock và transaction log. Tăng concurrency có thể làm throughput giảm nếu database đã bão hòa.

### 7.1. Bắt đầu thấp rồi tăng dần

Một cách thực tế:

1. Bắt đầu concurrency 1 hoặc 2.
2. Đo thời gian import, query latency và pool pending.
3. Tăng từng bước.
4. Theo dõi lỗi timeout, deadlock, lock wait và database CPU.
5. Dừng tăng khi throughput không cải thiện hoặc tail latency tăng mạnh.

Đo bằng dữ liệu có kích thước và phân bố gần production. Một test chỉ có vài chục dòng không đủ để chọn concurrency cho file hàng triệu dòng.

## 8. Hai chiến lược transaction chính

Batch processing cần quyết định transaction boundary.

| Chiến lược | Transaction bao phủ | Khi phù hợp |
|---|---|---|
| Một transaction toàn file | Toàn bộ import | File nhỏ, yêu cầu all-or-nothing và thời gian ngắn |
| Một transaction mỗi batch | Tất cả record trong một batch | Cần commit theo nhóm và chấp nhận rollback cả batch |
| Một transaction mỗi record | Một record | Cần partial success và lỗi một dòng không ảnh hưởng dòng khác |

Không có chiến lược nào luôn đúng. Chọn theo yêu cầu nghiệp vụ, database và khả năng resume.

### 8.1. Một transaction toàn file

Ưu điểm: nếu lỗi xảy ra trước commit, toàn bộ thay đổi có thể rollback.

Nhược điểm:

- Transaction có thể kéo dài rất lâu.
- Giữ connection trong suốt import.
- Lock và transaction log/undo có thể tăng.
- Khó retry một phần.
- Một lỗi ở cuối có thể rollback toàn bộ công việc.

Không nên bọc một file hàng triệu dòng trong một transaction duy nhất chỉ vì muốn “an toàn”.

### 8.2. Một transaction mỗi batch

Mỗi batch commit hoặc rollback độc lập. Đây thường là lựa chọn cân bằng cho import dữ liệu lớn.

Nếu batch 4 thất bại, batch 1-3 có thể đã commit. Job cần checkpoint để tiếp tục từ vị trí phù hợp và idempotency để chạy lại an toàn.

Nếu một record lỗi database trong transaction batch, nhiều database như PostgreSQL đánh dấu transaction thất bại. Không thể bắt lỗi constraint rồi tiếp tục insert các dòng khác trong cùng transaction như thể không có gì xảy ra. Cần rollback transaction batch hoặc dùng savepoint nếu driver/database hỗ trợ và được kiểm thử.

### 8.3. Một transaction mỗi record

Mỗi record có transaction riêng. Khi một record vi phạm unique constraint, transaction của record đó rollback, nhưng record khác vẫn có thể tiếp tục.

Ưu điểm:

- Dễ phân loại lỗi theo dòng.
- Partial success tự nhiên.
- Retry riêng một record.
- Một lỗi constraint không làm hỏng transaction của record kế tiếp.

Nhược điểm:

- Nhiều transaction hơn.
- Chi phí transaction/round-trip tăng.
- Cần giới hạn concurrency để không mở quá nhiều transaction.

## 9. Cấu hình TransactionalOperator cho R2DBC

Khi cần transaction tường minh, dùng reactive transaction manager và `TransactionalOperator`.

Ví dụ cấu hình:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Spring Boot có thể đã cung cấp reactive transaction manager theo ConnectionFactory. Kiểm tra application context trước khi tự khai báo bean trùng.

Tất cả repository/database operation trong transaction phải tham gia cùng reactive transaction context và cùng cấu hình ConnectionFactory phù hợp. Không tạo một ConnectionFactory độc lập trong một repository rồi mong transaction manager hiện tại quản lý nó.

### 9.1. Transaction theo từng record

~~~java
private Mono<ImportedCustomer> saveOne(ImportRow row) {
    Mono<ImportedCustomer> write =
            customerRepository.save(toEntity(row));

    return transactionalOperator.transactional(write);
}
~~~

Nếu pipeline chạy lại publisher transaction, transaction mới được tạo cho lần subscribe đó. Khi dùng retry, hãy đặt retry bên ngoài publisher được bọc transaction để mỗi lần thử có transaction mới.

### 9.2. Transaction theo batch

~~~java
private Mono<List<ImportedCustomer>> saveBatch(
        List<ImportRow> batch) {

    Mono<List<ImportedCustomer>> work =
            Flux.fromIterable(batch)
                    .concatMap(row ->
                            customerRepository.save(toEntity(row)))
                    .collectList();

    return transactionalOperator.transactional(work);
}
~~~

Các thao tác trong một batch được thực hiện tuần tự bằng `concatMap` trong cùng transaction. Khi một thao tác lỗi, transaction có thể rollback toàn bộ batch.

Không đổi `concatMap` thành `flatMap` trong cùng transaction một cách tùy tiện. Một reactive transaction thường gắn với một connection; driver có thể không hỗ trợ nhiều statement đồng thời trên cùng connection hoặc trong cùng transaction. Kiểm tra khả năng driver và transaction manager trước khi chạy song song bên trong transaction.

## 10. Chính sách lỗi phải được định nghĩa trước

Không phải mọi lỗi đều nên được xử lý giống nhau. Phân loại trước khi viết operator.

| Loại lỗi | Ví dụ | Chính sách thường dùng |
|---|---|---|
| Lỗi định dạng/validation | Thiếu email, ngày không hợp lệ | Từ chối dòng, tiếp tục |
| Lỗi nghiệp vụ | Trạng thái không cho phép, customer không tồn tại | Từ chối hoặc đưa vào danh sách review |
| Duplicate/conflict | Unique constraint, import key đã tồn tại | Skip, reject hoặc upsert theo contract |
| Lỗi transient database | Mất kết nối tạm thời, deadlock có thể retry | Retry có giới hạn |
| Lỗi cấu hình/schema | Sai tên cột, thiếu table, SQL grammar | Dừng job |
| Lỗi hạ tầng kéo dài | Database unavailable, pool timeout liên tục | Dừng job và resume sau |
| Lỗi không xác định | Exception chưa phân loại | Fail job và lưu chẩn đoán an toàn |

Một chính sách rõ ràng cần trả lời:

- Record lỗi có làm dừng cả file không?
- Có tiếp tục sau duplicate không?
- Bao nhiêu lần retry?
- Lỗi hạ tầng có làm job chuyển sang FAILED hay PAUSED?
- Batch đã commit có được chạy lại không?
- Báo cáo lỗi chứa row number và error code nào?
- Có giới hạn số lỗi được lưu hay không?

Không để operator mặc định quyết định semantics nghiệp vụ thay cho thiết kế.

## 11. Mô hình kết quả import theo dòng

Thay vì phát exception cho mọi lỗi dữ liệu, có thể biểu diễn kết quả của một record:

~~~java
public record ImportOutcome(
        long rowNumber,
        ImportStatus status,
        Long generatedId,
        String errorCode,
        String safeMessage) {

    public static ImportOutcome success(
            long rowNumber,
            Long id) {
        return new ImportOutcome(
                rowNumber, ImportStatus.SUCCESS, id, null, null);
    }

    public static ImportOutcome rejected(
            long rowNumber,
            String code,
            String message) {
        return new ImportOutcome(
                rowNumber, ImportStatus.REJECTED, null, code, message);
    }
}
~~~

Enum:

~~~java
public enum ImportStatus {
    SUCCESS,
    REJECTED,
    SKIPPED,
    FAILED
}
~~~

Dùng error code ổn định như `EMAIL_REQUIRED`, `DUPLICATE_EXTERNAL_ID` hoặc `UNKNOWN_CUSTOMER`. Không trả raw SQL, stack trace, password hoặc dữ liệu cá nhân trong báo cáo cho người dùng.

Với file rất lớn, không giữ mọi ImportOutcome trong một List. Có thể lưu outcome vào bảng import_error/import_row_status hoặc ghi báo cáo theo stream.

## 12. Mẫu import từng record với transaction riêng và concurrency giới hạn

Chiến lược này phù hợp khi muốn tiếp tục sau lỗi dữ liệu của từng dòng.

~~~java
@Service
public class CustomerImportService {

    private final CustomerRepository repository;
    private final TransactionalOperator transactionalOperator;

    public CustomerImportService(
            CustomerRepository repository,
            TransactionalOperator transactionalOperator) {
        this.repository = repository;
        this.transactionalOperator = transactionalOperator;
    }

    public Flux<ImportOutcome> importRows(
            Flux<IndexedImportRow> rows) {

        return rows.flatMap(
                this::importOne,
                8,
                1);
    }

    private Mono<ImportOutcome> importOne(IndexedImportRow item) {
        Mono<Customer> write = Mono.defer(() -> {
            validate(item.row());

            return repository.save(toEntity(item.row()));
        });

        return transactionalOperator.transactional(write)
                .map(saved ->
                        ImportOutcome.success(
                                item.rowNumber(),
                                saved.getId()))
                .onErrorResume(
                        InvalidImportRowException.class,
                        error -> Mono.just(
                                ImportOutcome.rejected(
                                        item.rowNumber(),
                                        error.code(),
                                        error.safeMessage())))
                .onErrorResume(
                        DataIntegrityViolationException.class,
                        error -> Mono.just(
                                ImportOutcome.rejected(
                                        item.rowNumber(),
                                        "DATA_CONFLICT",
                                        "Record conflicts with stored data")));
    }
}
~~~

Ví dụ minh họa cần bổ sung retry và job-level failure handling cho môi trường thật. Các điểm quan trọng:

- `flatMap(..., 8, 1)` giới hạn tối đa 8 record đang được xử lý.
- Mỗi record có transaction riêng.
- Validation error và constraint error được chuyển thành outcome sau khi transaction của record đã kết thúc/rollback.
- Lỗi hạ tầng chưa được phân loại vẫn truyền ra ngoài và có thể dừng pipeline.
- Thứ tự outcome không được bảo đảm vì flatMap cho phép hoàn tất không theo thứ tự nguồn.

Không bắt mọi Throwable rồi chuyển thành REJECTED. Nếu database mất kết nối, báo cáo một triệu dòng rejected sẽ che giấu lỗi hạ tầng.

### 12.1. Thêm retry có giới hạn

Có thể tạo publisher transaction cho từng lần thử rồi retry ở bên ngoài:

~~~java
private Mono<ImportOutcome> importOne(IndexedImportRow item) {
    Mono<Customer> oneAttempt = Mono.defer(() -> {
        validate(item.row());

        Mono<Customer> write =
                repository.save(toEntity(item.row()));

        return transactionalOperator.transactional(write);
    });

    return oneAttempt
            .retryWhen(
                    Retry.backoff(3, Duration.ofMillis(100))
                            .maxBackoff(Duration.ofSeconds(2))
                            .jitter(0.5)
                            .filter(this::isTransientDatabaseFailure)
                            .onRetryExhaustedThrow(
                                    (spec, signal) -> signal.failure()))
            .map(saved ->
                    ImportOutcome.success(
                            item.rowNumber(),
                            saved.getId()))
            .onErrorResume(
                    InvalidImportRowException.class,
                    error -> Mono.just(
                            ImportOutcome.rejected(
                                    item.rowNumber(),
                                    error.code(),
                                    error.safeMessage())))
            .onErrorResume(
                    DataIntegrityViolationException.class,
                    error -> Mono.just(
                            ImportOutcome.rejected(
                                    item.rowNumber(),
                                    "DATA_CONFLICT",
                                    "Record conflicts with stored data")));
}
~~~

`Mono.defer` bảo đảm mỗi subscription/retry tạo lại publisher ghi và transaction. Retry chỉ áp dụng với lỗi được `isTransientDatabaseFailure` nhận diện. Không retry validation hoặc unique conflict.

Một predicate có thể kiểm tra cause chain:

~~~java
private boolean isTransientDatabaseFailure(Throwable error) {
    for (Throwable cause = error;
            cause != null;
            cause = cause.getCause()) {

        if (cause instanceof R2dbcTransientException
                || cause instanceof TransientDataAccessException) {
            return true;
        }
    }

    return false;
}
~~~

Các driver có thể phân loại exception khác nhau. Hãy kiểm tra exception thực tế của driver đang dùng và chỉ retry các lỗi được xác định là transient. Deadlock/serialization conflict có thể retry trong một số trường hợp, nhưng cần bảo đảm toàn bộ transaction được chạy lại và thao tác có thể lặp an toàn.

## 13. Mẫu transaction theo batch với concurrency giới hạn

Nếu muốn mỗi batch atomic, có thể chạy nhiều batch độc lập đồng thời:

~~~java
public Flux<BatchOutcome> importInBatches(
        Flux<IndexedImportRow> source) {

    return source
            .buffer(200)
            .flatMap(
                    this::writeBatchAtomically,
                    3,
                    1);
}

private Mono<BatchOutcome> writeBatchAtomically(
        List<IndexedImportRow> batch) {

    Mono<List<Customer>> work =
            Flux.fromIterable(batch)
                    .concatMap(item ->
                            Mono.fromRunnable(() ->
                                            validate(item.row()))
                                    .then(Mono.defer(() ->
                                            repository.save(
                                                    toEntity(item.row())))))
                    .collectList();

    return transactionalOperator.transactional(work)
            .map(saved ->
                    BatchOutcome.success(
                            batch.size(),
                            saved.size()));
}
~~~

Trong ví dụ:

- Mỗi batch tối đa 200 dòng.
- Tối đa 3 batch chạy đồng thời.
- Bên trong một batch, record được ghi tuần tự.
- Mỗi batch có transaction riêng.
- Nếu một row làm write lỗi, transaction của batch có thể rollback toàn bộ.

Đây là semantics all-or-nothing theo batch. Không dùng nó nếu yêu cầu nghiệp vụ là một dòng lỗi vẫn phải giữ các dòng khác trong cùng batch.

### 13.1. Báo lỗi batch sau khi transaction rollback

Nếu muốn pipeline tiếp tục với batch kế tiếp, xử lý lỗi ở bên ngoài transaction:

~~~java
private Mono<BatchOutcome> writeBatchAtomically(
        List<IndexedImportRow> batch) {

    Mono<List<Customer>> work =
            Flux.fromIterable(batch)
                    .concatMap(item ->
                            Mono.fromRunnable(() ->
                                            validate(item.row()))
                                    .then(Mono.defer(() ->
                                            repository.save(
                                                    toEntity(item.row())))))
                    .collectList();

    return transactionalOperator.transactional(work)
            .map(saved -> BatchOutcome.success(batch, saved))
            .onErrorResume(error -> {
                if (isFatalInfrastructureFailure(error)) {
                    return Mono.error(error);
                }

                return Mono.just(
                        BatchOutcome.rolledBack(
                                batch,
                                classifyBatchFailure(error)));
            });
}
~~~

`onErrorResume` ở đây nằm sau transaction publisher. Khi nó chạy, transaction đã kết thúc theo đường lỗi và rollback nếu database/transaction manager hỗ trợ rollback cho lỗi đó.

Nếu connection bị mất đúng lúc commit, kết quả commit có thể không xác định. Không khẳng định batch đã rollback nếu chưa có bằng chứng. Dùng idempotency key/checkpoint để reconcile trạng thái.

### 13.2. Validation trước transaction để giảm rollback không cần thiết

Nếu validation chỉ dùng dữ liệu của record và không cần đọc database, có thể phân loại validation trước khi mở transaction. Giữ row number và kết quả reject để báo cáo đầy đủ.

Validation phụ thuộc database như kiểm tra tham chiếu vẫn có race condition; constraint database mới là hàng rào cuối cùng.

## 14. Không tiếp tục ghi trong transaction đã bị lỗi

Đây là lỗi thiết kế dễ gặp khi xử lý partial success.

Ví dụ một batch chạy trong transaction PostgreSQL. Một INSERT vi phạm unique constraint. PostgreSQL đánh dấu transaction ở trạng thái aborted; các statement tiếp theo trong transaction sẽ thất bại cho đến khi rollback.

Đoạn logic kiểu:

~~~java
Flux.fromIterable(batch)
        .concatMap(row ->
                repository.save(toEntity(row))
                        .onErrorResume(
                                DataIntegrityViolationException.class,
                                error -> Mono.empty()))
~~~

có thể nuốt lỗi ở cấp publisher, nhưng không phục hồi trạng thái transaction database. Các insert sau vẫn có thể thất bại vì transaction đã bị đánh dấu lỗi.

Các lựa chọn an toàn hơn:

- Transaction riêng cho mỗi row nếu cần tiếp tục từng row sau lỗi constraint.
- Transaction toàn batch và rollback cả batch khi có lỗi.
- Dùng savepoint nếu driver/database/transaction manager hỗ trợ và đã kiểm thử.
- Validate/deduplicate trước khi vào transaction, nhưng vẫn xử lý constraint race ở database.

Không dựa vào việc `onErrorResume` đã thay thế error signal để kết luận database transaction còn sử dụng được.

## 15. Dùng savepoint khi thực sự cần partial success trong batch

Savepoint cho phép rollback một phần transaction trong một số database. Nhưng hỗ trợ R2DBC savepoint và cách transaction manager phơi bày API phụ thuộc driver/database/version.

Trước khi dùng, xác nhận:

- Driver hỗ trợ create/rollback/release savepoint.
- Transaction manager hỗ trợ các thao tác đó.
- Database cho phép tiếp tục transaction sau rollback về savepoint.
- Constraint violation có thể được phục hồi theo semantics database.
- Savepoint hoạt động đúng với connection pool và transaction context.

Nếu cần portability, transaction riêng theo row thường dễ hiểu hơn. Savepoint có thể giảm chi phí transaction nhưng tăng độ phức tạp và phụ thuộc database.

## 16. Phân biệt fail-fast, continue-on-error và delay-error

### 16.1. Fail-fast

Mặc định các operator kết hợp publisher như `flatMap` sẽ kết thúc khi inner publisher phát lỗi, hủy subscription còn lại theo semantics của operator. Đây là lựa chọn phù hợp khi lỗi cho thấy job không thể tiếp tục.

Tuy nhiên, các thao tác đã gửi tới database có thể đã thực thi hoặc commit trước khi cancellation đến. Fail-fast không phải rollback toàn bộ các transaction độc lập đã commit.

### 16.2. Continue-on-error theo từng record

Dùng `onErrorResume` bên trong publisher xử lý một record, nhưng chỉ chuyển các lỗi dữ liệu đã xác định thành outcome. Lỗi hạ tầng/fatal phải thoát ra ngoài.

Đây là cách phù hợp cho import cần chấp nhận partial success.

### 16.3. Delay error

Reactor có các operator delay-error như `flatMapDelayError` cho phép chờ các inner publisher khác hoàn tất trước khi phát lỗi tổng hợp. Nó hữu ích trong một số pipeline cần thu thập thêm kết quả.

Tuy nhiên, delay-error không tự phân loại lỗi nghiệp vụ, không rollback các transaction đã commit và không tạo báo cáo lỗi theo từng dòng. Dùng nó có chủ đích, không thay thế error policy.

### 16.4. Tránh onErrorContinue cho import quan trọng

`onErrorContinue` có semantics phụ thuộc operator và vị trí lỗi, dễ làm code khó dự đoán. Nó có thể bỏ qua một phần tử nhưng không tự bảo đảm transaction database đã phục hồi.

Ưu tiên `onErrorResume` ở ranh giới xử lý một record hoặc một batch, nơi biết rõ record nào bị ảnh hưởng và transaction nào đã kết thúc.

## 17. Retry: khi nào được phép và khi nào không?

Retry hữu ích khi lỗi có tính tạm thời:

- Connection bị ngắt tạm thời.
- Deadlock có thể giải quyết bằng cách thử lại transaction.
- Serialization conflict theo database isolation.
- Service phụ thuộc trả lỗi transient.

Không retry mù các lỗi:

- Dữ liệu sai định dạng.
- Vi phạm unique/business constraint không có chiến lược xử lý.
- SQL grammar sai.
- Thiếu table/column.
- Mapping/conversion lỗi.
- Permission bị từ chối.

### 17.1. Retry phải có giới hạn

~~~java
Retry.backoff(3, Duration.ofMillis(100))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isTransientDatabaseFailure);
~~~

Backoff giúp tránh gửi lại liên tục khi database đang quá tải. Jitter giúp nhiều worker không retry cùng thời điểm.

Cần giới hạn tổng thời gian job và ghi nhận số lần retry. Retry vô hạn có thể giữ tài nguyên và làm backlog tăng mãi.

### 17.2. Retry toàn bộ đơn vị transaction

Nếu một batch gồm nhiều insert và một insert lỗi transient, cần retry toàn bộ batch transaction sau rollback, không chỉ retry statement cuối cùng trong transaction đã hỏng.

Với transaction theo row, retry row đó. Với transaction theo batch, retry batch đó. Đặt retry ngoài publisher transaction để mỗi lần thử mở transaction mới.

### 17.3. Idempotency là điều kiện quan trọng

Nếu request timeout hoặc connection mất sau khi database commit nhưng trước khi ứng dụng nhận response, ứng dụng không biết chắc record đã được ghi hay chưa. Retry có thể tạo duplicate nếu không có idempotency.

Một khóa idempotency có thể gồm:

- Import job ID.
- Source row number hoặc source record key.
- Tenant/business key nếu phù hợp.

Tạo unique constraint cho khóa này hoặc bảng import ledger. Khi chạy lại, ứng dụng có thể xác định record đã được xử lý và trả kết quả tương ứng.

Không dùng sequence ID sinh tự động làm khóa idempotency. Sequence có thể tăng dù transaction rollback.

## 18. Duplicate, upsert và dữ liệu đã tồn tại

Khi import, duplicate có thể có nhiều ý nghĩa:

- Record đã được import trong cùng job.
- Record đã tồn tại từ job trước.
- Business key đã được sử dụng.
- Nhiều dòng trong chính file bị trùng.

Chính sách có thể là:

| Chính sách | Hành vi |
|---|---|
| Reject | Ghi nhận lỗi duplicate |
| Skip | Không thay đổi record hiện có |
| Update | Cập nhật record theo business key |
| Upsert | Insert nếu chưa có, update nếu đã có |
| Merge | Cập nhật một số field theo quy tắc domain |

Upsert là cú pháp và semantics riêng của từng database. Spring Data R2DBC không tạo một câu upsert portable cho mọi dialect. Có thể cần custom SQL và integration test trên database mục tiêu.

Nếu import có nhiều dòng cùng business key, cần quyết định dòng nào thắng: dòng đầu, dòng cuối, hoặc tất cả đều bị từ chối. Deduplicate trước khi ghi nếu chính sách yêu cầu.

Không dựa vào câu SELECT kiểm tra tồn tại rồi INSERT để bảo đảm uniqueness dưới concurrency. Hai worker có thể cùng thấy “chưa tồn tại”. Unique constraint hoặc upsert atomic ở database mới giải quyết race condition.

## 19. Checkpoint và khả năng resume

Import lớn có thể bị dừng do deploy, mất kết nối, timeout hoặc process crash. Nếu không có checkpoint, phải đọc lại từ đầu.

Một bảng job có thể lưu:

- Job ID.
- File/source identity và checksum.
- Trạng thái: PENDING, RUNNING, PAUSED, COMPLETED, FAILED.
- Tổng số record nếu biết.
- Số thành công, reject, skipped.
- Vị trí/row number đã xử lý.
- Thời điểm bắt đầu/cập nhật/kết thúc.
- Error code tổng thể.

Bảng chi tiết có thể lưu trạng thái theo source key hoặc batch ID.

### 19.1. Checkpoint phải nhất quán với commit

Nếu ghi dữ liệu thành công nhưng checkpoint chưa được ghi, restart có thể xử lý lại record. Nếu checkpoint được ghi trước khi dữ liệu commit, restart có thể bỏ qua record chưa được lưu.

Cách an toàn là cập nhật business row và import ledger/checkpoint trong cùng transaction khi chúng nằm cùng database:

~~~text
BEGIN
  INSERT/UPDATE business row
  INSERT import_row_ledger
  UPDATE import_job progress
COMMIT
~~~

Nếu dữ liệu và checkpoint ở hai hệ thống khác nhau, không có atomicity tự động; cần thiết kế reconciliation/idempotency.

### 19.2. Không chỉ checkpoint theo số dòng khi nguồn có thể thay đổi

Nếu file được thay thế hoặc nội dung thay đổi, row 1000 trong file mới có thể khác row 1000 cũ. Lưu checksum, version hoặc source identity để bảo đảm resume đúng nguồn.

Với nguồn message, dùng message offset/partition hoặc source event ID theo semantics của broker.

## 20. Cancellation và vòng đời import job

Nếu một HTTP request gửi toàn bộ file và client ngắt kết nối, publisher có thể bị cancel. Cancellation có thể dừng pipeline đang chạy, nhưng các transaction đã commit vẫn tồn tại. Một write đang thực thi cũng có thể đã được database xử lý trước khi cancel tới nơi.

Cần quyết định import có thuộc vòng đời HTTP request hay là một job độc lập.

### 20.1. Import đồng bộ theo request

Phù hợp với file nhỏ và thời gian ngắn. Client chờ kết quả hoàn tất. Khi client hủy request, pipeline có thể bị cancel.

### 20.2. Import job bất đồng bộ

Với file lớn, thường nên:

1. Upload file và lưu vào storage.
2. Tạo import job record.
3. Trả HTTP 202 Accepted cùng job ID.
4. Một worker/job coordinator quản lý publisher import.
5. Lưu tiến độ và kết quả.
6. Client truy vấn trạng thái job.

Không gọi `subscribe()` tùy tiện trong controller để “chạy nền”. Nếu cần background execution, phải có thành phần job coordinator quản lý subscription, lỗi, shutdown, retry và checkpoint, hoặc đưa job vào durable queue.

Nếu process restart, job phải có khả năng resume từ trạng thái đã lưu.

## 21. Lưu báo cáo lỗi mà không làm tăng memory

Với import nhỏ, có thể thu kết quả:

~~~java
return importRows(rows)
        .collectList()
        .map(ImportReport::from);
~~~

Nhưng `collectList()` giữ mọi outcome trong heap. Với file lớn, dùng một trong các cách:

- Lưu lỗi vào bảng import_error theo từng record.
- Ghi CSV lỗi ra file theo stream.
- Dùng Counter cho tổng số success/rejected/skipped.
- Lưu mẫu lỗi có giới hạn và tổng số lỗi theo code.
- Phân trang kết quả khi client tải báo cáo.

Không giữ toàn bộ exception object. Lưu row number, error code, thông báo an toàn và source key đủ để người dùng tìm lại dòng.

## 22. Bulk insert và Statement.add()

Batch logic ở ứng dụng không đồng nghĩa driver thực hiện một bulk insert duy nhất.

Có thể ghi từng entity bằng repository.save, dùng saveAll, tạo một câu INSERT nhiều hàng hoặc dùng R2DBC SPI Statement batch binding. Những cách này có khác biệt về hiệu năng và khả năng trả generated values.

R2DBC SPI có cơ chế `Statement.add()` để thêm một bộ binding khác vào statement ở các driver hỗ trợ. Nhưng khả năng batch, row count, generated values và giới hạn parameter khác nhau giữa driver/database.

Trước khi chọn bulk statement, kiểm tra:

- Driver có hỗ trợ Statement.add cho câu SQL đang dùng không?
- Có thể bind lại mọi parameter không?
- Result có một count hay nhiều count?
- Generated ID có được trả cho từng hàng không?
- Một lỗi giữa batch ảnh hưởng các binding khác thế nào?
- Kích thước batch và parameter limit của database là bao nhiêu?

Không giả định `repository.saveAll(Publisher)` luôn được biến thành một lệnh bulk insert ở database. Nó là API reactive để lưu nhiều entity; implementation và cách driver thực thi phụ thuộc Spring Data version, dialect và driver.

### 22.1. Bulk SQL và giới hạn parameter

Nếu tạo một câu INSERT nhiều hàng, số bind parameter tăng theo:

\[
N_{\text{parameters}}
=
N_{\text{rows}}
\times
N_{\text{columns per row}}
\]

Database có giới hạn số parameter, độ dài statement hoặc packet size. Chia batch theo giới hạn thực tế của driver/database.

### 22.2. Tách API batch khỏi transaction policy

Một câu lệnh batch có thể thực thi nhiều binding nhưng không tự đảm bảo toàn bộ import atomic. Nếu cần atomicity, vẫn phải xác định transaction. Nếu driver trả lỗi một phần, cần biết database đã thực thi những binding nào.

Test trên driver mục tiêu trước khi dùng bulk path trong production.

## 23. Validation, normalization và staging table

Import có thể cần parse nhiều loại dữ liệu: ngày, tiền, mã quốc gia, enum, email hoặc foreign key.

Nên tách:

- Parse: chuyển chuỗi nguồn thành kiểu có cấu trúc.
- Normalize: trim, chuẩn hóa case, định dạng và timezone theo quy tắc.
- Validate: kiểm tra required field, range, format và domain rule.
- Resolve: tìm tham chiếu database nếu cần.
- Persist: ghi vào bảng đích.

Với file lớn hoặc quy tắc phức tạp, staging table có thể hữu ích:

1. Nạp dữ liệu thô vào staging theo job ID và row number.
2. Validate bằng SQL hoặc service.
3. Ghi các row lỗi vào bảng reject.
4. Merge dữ liệu hợp lệ sang bảng đích.
5. Đánh dấu job hoàn tất.

Staging giúp resume và audit tốt hơn, nhưng cần quản lý cleanup, index, partition và quyền truy cập. Đừng giữ dữ liệu nhạy cảm thô lâu hơn thời hạn cần thiết.

## 24. Thứ tự xử lý và tính nhất quán

Nếu nhiều batch chạy đồng thời, thứ tự commit có thể khác thứ tự nguồn. Điều này quan trọng khi:

- Một record phụ thuộc record trước.
- Hai record cập nhật cùng aggregate.
- Một file có sequence number nghiệp vụ.
- Import phải áp dụng phiên bản mới nhất.

Các lựa chọn:

- `concatMap` để xử lý tuần tự.
- `flatMapSequential` để xử lý đồng thời nhưng phát kết quả theo thứ tự nguồn.
- Partition theo business key để các record cùng key đi tuần tự, còn các key khác chạy song song.
- Thiết kế upsert/version check để xử lý xung đột.
- Tách dependency thành nhiều phase: import master data trước, detail sau.

Giữ thứ tự output không có nghĩa giữ thứ tự commit. `flatMapSequential` vẫn cho phép inner publisher chạy đồng thời; nó chỉ sắp thứ tự phát kết quả.

## 25. Kiểm soát concurrency theo tenant hoặc partition

Nếu dữ liệu có tenant, có thể giới hạn concurrency toàn job và đồng thời giữ thứ tự theo tenant.

~~~text
Nguồn record
   |
   +--> tenant A --> concatMap tuần tự
   |
   +--> tenant B --> concatMap tuần tự
   |
   +--> tenant C --> concatMap tuần tự
             |
             v
       giới hạn số tenant active
~~~

Reactor có thể dùng `groupBy` rồi xử lý từng group, nhưng groupBy có thể giữ group và buffer nếu upstream không được tiêu thụ đúng cách. Không dùng nó cho cardinality không giới hạn mà chưa đánh giá memory/lifecycle.

Một giải pháp khác là partition key từ nguồn hoặc đưa record vào queue theo tenant. Mục tiêu là tránh hai update cùng aggregate chạy cạnh tranh trong khi vẫn tận dụng concurrency giữa các aggregate độc lập.

## 26. Observability cho import job

Một import job nên phát ra metrics có cardinality hữu hạn:

- `import.records.read`
- `import.records.succeeded`
- `import.records.rejected`
- `import.records.skipped`
- `import.records.retried`
- `import.batch.duration`
- `import.batch.size`
- `import.job.duration`
- `import.database.errors`

Tag phù hợp có thể là `sourceType`, `outcome`, `errorCategory` hoặc `operation` với tập giá trị giới hạn.

Không dùng importJobId, file name, customer ID hoặc row number làm metric tag. Những giá trị đó có thể được lưu trong log/trace/job table nếu được bảo vệ, nhưng không phù hợp cho metric dimension có cardinality cao.

Theo dõi thêm R2DBC pool:

- Acquired/allocated/idle.
- Pending acquire.
- Acquire timeout.
- Query latency.
- Database error rate.

Nếu concurrency tăng mà throughput không tăng, pool pending và query duration sẽ giúp xác định bottleneck.

## 27. Kiểm thử pipeline import

Unit test có thể kiểm tra parser, validator, error classifier và mapping outcome. Integration test cần dùng database thật để xác nhận transaction, constraint, retry và driver behavior.

### 27.1. Test giới hạn concurrency

Có thể tạo publisher giả với bộ đếm active:

~~~java
AtomicInteger active = new AtomicInteger();
AtomicInteger maximum = new AtomicInteger();

Flux<Integer> work =
        Flux.range(1, 100)
                .flatMap(value ->
                                Mono.defer(() -> {
                                    int current =
                                            active.incrementAndGet();

                                    maximum.accumulateAndGet(
                                            current,
                                            Math::max);

                                    return Mono.delay(
                                                    Duration.ofMillis(20))
                                            .thenReturn(value)
                                            .doFinally(signal ->
                                                    active.decrementAndGet());
                                }),
                        4,
                        1);
~~~

Sau khi verify publisher hoàn tất, xác nhận maximum không vượt 4. Đây là test operator concurrency; integration test vẫn cần kiểm tra pool/database thật.

### 27.2. Test partial success theo record

Chuẩn bị ba dòng:

- Dòng 1 hợp lệ.
- Dòng 2 vi phạm validation hoặc unique constraint.
- Dòng 3 hợp lệ.

Kỳ vọng:

- Dòng 1 commit.
- Dòng 2 có outcome REJECTED.
- Dòng 3 vẫn commit.
- Báo cáo có đủ ba row number.
- Không có lỗi database bị chuyển nhầm thành validation error.

Với transaction riêng từng row, đây là semantics có thể kiểm chứng rõ ràng.

### 27.3. Test atomicity theo batch

Tạo một batch có một record vi phạm constraint. Xác nhận:

- Transaction batch rollback.
- Không có business row nào của batch đó được commit.
- Batch khác vẫn có thể hoàn tất nếu policy cho phép.
- Outcome phản ánh cả batch bị rollback, không báo thành công cho các dòng đã chạy trước lỗi.

### 27.4. Test retry và idempotency

Giả lập hoặc tạo lỗi transient có kiểm soát. Xác nhận số lần retry không vượt giới hạn và mỗi lần thử dùng transaction mới.

Chạy lại cùng job/source key sau khi một phần record đã commit. Xác nhận unique import ledger/upsert không tạo duplicate.

### 27.5. Test cancellation và restart

Hủy subscription giữa import và xác nhận:

- Các transaction chưa commit được rollback nếu cancellation được xử lý kịp.
- Các transaction đã commit vẫn tồn tại.
- Job state cho biết import bị pause/cancel/fail theo thiết kế.
- Restart có thể resume mà không tạo duplicate.

Không giả định cancellation đồng nghĩa không có dữ liệu nào được ghi.

### 27.6. Test với database thật

Dùng Testcontainers hoặc database test riêng đúng engine/version với production. H2 không thay thế được semantics về transaction abort, savepoint, upsert, lock và batch behavior của database mục tiêu.

## 28. Ví dụ tổng hợp: import theo nhóm với transaction riêng từng record

Ví dụ này minh họa streaming, gán row number, giới hạn concurrency, transaction theo record, retry transient và tiếp tục sau lỗi dữ liệu đã phân loại.

~~~java
@Service
public class CustomerImportService {

    private static final int ROW_CONCURRENCY = 8;

    private final CustomerRepository repository;
    private final TransactionalOperator tx;

    public CustomerImportService(
            CustomerRepository repository,
            TransactionalOperator tx) {
        this.repository = repository;
        this.tx = tx;
    }

    public Flux<ImportOutcome> importRows(Flux<ImportRow> source) {
        return source
                .index()
                .map(tuple ->
                        new IndexedImportRow(
                                tuple.getT1() + 1,
                                tuple.getT2()))
                .flatMap(
                        this::importOne,
                        ROW_CONCURRENCY,
                        1);
    }

    private Mono<ImportOutcome> importOne(
            IndexedImportRow item) {

        Mono<Customer> oneAttempt = Mono.defer(() -> {
            validate(item.row());

            return tx.transactional(
                    repository.save(toEntity(item.row())));
        });

        return oneAttempt
                .retryWhen(
                        Retry.backoff(
                                        3,
                                        Duration.ofMillis(100))
                                .maxBackoff(Duration.ofSeconds(2))
                                .jitter(0.5)
                                .filter(this::isTransientDatabaseFailure)
                                .onRetryExhaustedThrow(
                                        (spec, signal) ->
                                                signal.failure()))
                .map(saved ->
                        ImportOutcome.success(
                                item.rowNumber(),
                                saved.getId()))
                .onErrorResume(
                        InvalidImportRowException.class,
                        error -> Mono.just(
                                ImportOutcome.rejected(
                                        item.rowNumber(),
                                        error.code(),
                                        error.safeMessage())))
                .onErrorResume(
                        DataIntegrityViolationException.class,
                        error -> Mono.just(
                                ImportOutcome.rejected(
                                        item.rowNumber(),
                                        "DATA_CONFLICT",
                                        "Record conflicts with stored data")));
    }

    private void validate(ImportRow row) {
        if (row.email() == null || row.email().isBlank()) {
            throw new InvalidImportRowException(
                    "EMAIL_REQUIRED",
                    "Email is required");
        }
    }

    private Customer toEntity(ImportRow row) {
        return new Customer(row.email(), row.fullName());
    }

    private boolean isTransientDatabaseFailure(Throwable error) {
        for (Throwable cause = error;
                cause != null;
                cause = cause.getCause()) {

            if (cause instanceof R2dbcTransientException
                    || cause instanceof TransientDataAccessException) {
                return true;
            }
        }

        return false;
    }
}
~~~

Đây là khung minh họa; cần bổ sung import ledger/idempotency, job state, metrics và cách phân loại exception phù hợp driver thật. `flatMap` có thể phát outcome không theo thứ tự row number. Nếu cần kết quả theo thứ tự nguồn, cân nhắc `flatMapSequential` và chi phí buffer của nó.

Với một file rất lớn, không gọi `collectList()` trên toàn bộ outcome. Hãy ghi outcome theo stream hoặc tổng hợp bằng bộ đếm có giới hạn.

## 29. Những lỗi thường gặp khi nhập dữ liệu theo nhóm

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Đọc toàn bộ file vào List | Tốn heap, khó xử lý file lớn | Dùng parser streaming và Flux |
| buffer không có giới hạn | Memory tăng không kiểm soát | Dùng buffer(size) hoặc bufferTimeout có size |
| flatMap không chỉ rõ concurrency | Có thể mở quá nhiều operation | Chọn concurrency/prefetch tường minh |
| Chọn concurrency bằng max pool size | API traffic không còn connection | Dự trữ connection và tính tổng replica |
| Tăng batch size và concurrency cùng lúc | Không xác định được nguồn quá tải | Điều chỉnh từng tham số và đo |
| Dùng flatMap nhưng giả định giữ thứ tự | Outcome/commit có thể đảo thứ tự | concatMap hoặc flatMapSequential khi cần |
| Nuốt lỗi trong transaction đã hỏng | Các statement sau vẫn thất bại | Rollback batch hoặc transaction theo row |
| Bọc toàn file trong một transaction dài | Giữ connection/lock lâu, rollback lớn | Transaction theo batch hoặc row |
| Retry mọi exception | Lặp lỗi dữ liệu và SQL không thể sửa | Retry chỉ transient, có giới hạn |
| Retry statement trong transaction đã abort | Transaction vẫn hỏng | Retry toàn bộ transaction |
| Không có idempotency | Retry/restart tạo duplicate | Unique import key/ledger |
| Checkpoint ghi trước commit dữ liệu | Có thể bỏ sót record khi resume | Cập nhật checkpoint cùng transaction |
| Checkpoint sau commit nhưng không idempotent | Có thể xử lý lại record | Reconcile bằng source key |
| Gọi subscribe() trong controller để chạy nền | Mất quản lý lỗi và lifecycle | Job coordinator/durable queue |
| Collect mọi error vào memory | Tốn heap với file lớn | Stream error report hoặc lưu database |
| Dùng onErrorContinue | Semantics khó dự đoán, không bảo đảm transaction phục hồi | onErrorResume ở ranh giới record/batch |
| Tin rằng saveAll luôn là bulk SQL | Hiệu năng và generated key không như mong đợi | Kiểm tra implementation/driver và đo thực tế |
| Không test trên database production | Sai khác transaction/batch/upsert | Integration test với đúng engine |
| Không theo dõi pool pending | Chỉ thấy import chậm mà không biết nguyên nhân | Metrics pool, query duration và retry |

## 30. Quy trình triển khai thực tế

Một trình tự triển khai có kiểm soát:

1. Xác định nguồn dữ liệu và cách đọc streaming.
2. Gán source key/row number ổn định.
3. Định nghĩa validation, normalization và error code.
4. Chọn batch size theo memory, transaction và database limits.
5. Chọn transaction theo row hoặc batch theo yêu cầu partial success.
6. Chọn concurrency theo connection pool và database capacity.
7. Giới hạn prefetch và không tạo buffer vô hạn.
8. Xác định fail-fast, reject-row, skip, upsert và retry policy.
9. Chỉ retry lỗi transient; retry toàn bộ transaction unit.
10. Thiết kế idempotency key và checkpoint cho resume.
11. Ghi kết quả theo stream, tránh collect toàn bộ file.
12. Xác định cancellation và vòng đời job.
13. Thêm metrics cho throughput, error, retry, batch duration và pool.
14. Kiểm thử concurrency, rollback, partial success, retry, resume và cancellation.
15. Đo tải trên đúng database/driver/version gần production.

## 31. Ghi nhớ

- Batch size là số record trong nhóm; concurrency là số nhóm/record được xử lý đồng thời.
- Dùng Flux streaming và buffer có giới hạn để tránh nạp toàn bộ file vào heap.
- flatMap giới hạn concurrency; concatMap xử lý tuần tự; flatMapSequential giữ thứ tự phát kết quả nhưng có thể buffer.
- Tính concurrency theo connection pool, API traffic, số replica và khả năng database.
- Chọn transaction toàn file, mỗi batch hoặc mỗi record theo yêu cầu atomicity/partial success.
- Với transaction batch, một lỗi database có thể làm transaction thất bại; không tiếp tục ghi chỉ bằng cách nuốt error signal.
- Transaction riêng từng record phù hợp khi cần tiếp tục sau lỗi constraint của một dòng.
- Phân loại validation/business error, conflict, transient infrastructure và fatal configuration error.
- Chỉ chuyển lỗi dữ liệu đã xác định thành outcome; để lỗi hạ tầng/fatal thoát ra job coordinator.
- Retry có giới hạn, backoff và jitter; đặt retry bên ngoài transaction để mỗi lần thử dùng transaction mới.
- Retry và resume cần idempotency key/unique import ledger.
- Ghi checkpoint nhất quán với commit dữ liệu; không giả định cancellation rollback những transaction đã commit.
- R2DBC Statement.add và bulk insert phụ thuộc driver/database; saveAll không mặc nhiên là một câu bulk SQL.
- Không dùng onErrorContinue như cơ chế partial success chung.
- Không gọi subscribe() tùy tiện để tạo job nền; quản lý vòng đời qua job coordinator hoặc durable queue.
- Với import lớn, stream kết quả/lỗi thay vì collectList toàn bộ.
- Kiểm thử trên database thật các tình huống concurrency, transaction abort, retry, duplicate, restart và cancellation.

