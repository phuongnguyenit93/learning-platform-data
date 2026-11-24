# Đọc yêu cầu thực tế và giải thích lựa chọn toán tử, vòng đời, giới hạn tải

Một pipeline reactive tốt bắt đầu từ yêu cầu nghiệp vụ và vận hành. Cùng một nguồn `Flux`, ta có thể chọn `concatMap`, `flatMap` hoặc `flatMapSequential`; mỗi lựa chọn tạo ra hành vi khác nhau về thứ tự, concurrency, bộ nhớ và cancellation. Nếu chỉ chọn operator theo thói quen, hệ thống có thể xử lý sai thứ tự, giữ quá nhiều request đồng thời hoặc tiếp tục công việc sau khi client đã ngắt kết nối.

Bài thực hành này đặt bạn vào vai trò thiết kế một dịch vụ nhập dữ liệu đơn hàng. Bạn sẽ đọc yêu cầu, chuyển chúng thành hợp đồng có thể kiểm tra, chọn operator, xác định ranh giới transaction, mô tả lifecycle của subscription và đặt giới hạn tải. Sau đó, bạn dùng `StepVerifier` để kiểm chứng các quyết định đó.

## 1. Đề bài: dịch vụ nhập đơn hàng dạng streaming

Một đối tác gửi một luồng bản ghi đơn hàng đến WebFlux endpoint. Mỗi bản ghi cần được kiểm tra, tra cứu thông tin sản phẩm từ một dịch vụ HTTP và lưu vào database bằng R2DBC. Endpoint trả về một luồng `ImportResult` tương ứng với từng bản ghi.

Đội sản phẩm và vận hành đưa ra các yêu cầu sau:

| Nhóm | Yêu cầu |
| --- | --- |
| Đầu vào | Đọc bản ghi theo luồng; một job tối đa 20.000 bản ghi và request body tối đa 10 MB |
| Cardinality | Mỗi bản ghi tạo đúng một kết quả: `SAVED`, `REJECTED` hoặc `LOOKUP_TIMEOUT` |
| Thứ tự | Kết quả trả về phải theo thứ tự bản ghi đầu vào |
| I/O đồng thời | Tối đa 8 lần tra cứu sản phẩm đang hoạt động trong một job |
| Thời gian | Mỗi lần tra cứu sản phẩm có timeout 2 giây |
| Validation | Bản ghi sai dữ liệu bị từ chối và không gọi dịch vụ sản phẩm |
| Database | Mỗi bản ghi hợp lệ được lưu trong transaction reactive riêng |
| Lỗi hạ tầng | Lỗi database hoặc lỗi dịch vụ không được phân loại là timeout phải kết thúc job và truyền lỗi cho caller |
| Consumer chậm | Không gom toàn bộ 20.000 kết quả vào một List; tôn trọng demand của downstream |
| Cancellation | Khi client hủy subscription, ngừng nhận bản ghi mới, hủy I/O còn hoạt động nếu adapter hỗ trợ và giải phóng tài nguyên |
| Khả năng chạy lại | Job có thể được tiếp tục hoặc gửi lại an toàn; không tạo bản ghi trùng khi một request trước có kết quả không rõ ràng |

Đây là hợp đồng trực tiếp của bài. Không được tự bỏ yêu cầu giữ thứ tự hoặc đổi lỗi hạ tầng thành kết quả thành công chỉ để pipeline tiếp tục.

Mỗi bản ghi có một kết quả khi được xử lý đến một nhánh nghiệp vụ. Nếu lỗi hạ tầng làm job kết thúc, stream có thể chỉ phát kết quả của phần đã xử lý rồi kết thúc bằng `onError`; không tạo kết quả giả cho các bản ghi chưa chạy.

## 2. Chuyển yêu cầu thành quyết định kỹ thuật

Trước khi viết code, điền bảng quyết định sau. Cột cuối là lý do cần giải thích trong phần nộp bài:

| Câu hỏi | Quyết định cần đưa ra |
| --- | --- |
| Một bản ghi tạo bao nhiêu kết quả? | Chọn `Mono<ImportResult>` hay `Flux<ImportResult>` cho hàm xử lý một bản ghi |
| Một job tạo bao nhiêu kết quả? | Chọn kiểu trả về của pipeline tổng |
| Làm sao giữ thứ tự khi I/O hoàn tất không cùng tốc độ? | Chọn giữa `concatMap`, `flatMap` và `flatMapSequential` |
| Giới hạn số lần gọi HTTP đồng thời ở đâu? | Chọn concurrency và prefetch phù hợp |
| Timeout được áp dụng cho phần nào? | Chỉ tra cứu HTTP hay cả toàn bộ job |
| Lỗi nào trở thành kết quả nghiệp vụ? | Phân biệt validation, timeout và lỗi hạ tầng |
| Transaction bao quanh phần nào? | Chọn ranh giới bắt đầu/kết thúc transaction |
| Client hủy thì điều gì xảy ra? | Mô tả cancellation, I/O đang chạy và bản ghi đã commit |
| Giới hạn tải toàn hệ thống ra sao? | Phân biệt giới hạn mỗi job với bulkhead/rate limit toàn ứng dụng |

Ghi rõ giả định của bạn. Ví dụ, `ImportResult` là một giá trị cho mỗi bản ghi, kể cả khi bản ghi bị từ chối; do đó publisher xử lý một bản ghi phải phát đúng một kết quả trong các trường hợp nghiệp vụ dự kiến.

## 3. Xác định cardinality và kiểu trả về

Một bản ghi đầu vào được xử lý thành một kết quả:

~~~java
Mono<ImportResult> processOne(ImportRow row);
~~~

Toàn bộ job có thể chứa nhiều bản ghi nên trả về:

~~~java
Flux<ImportResult> importRows(Flux<ImportRow> rows);
~~~

`Mono` phù hợp với một lần xử lý bản ghi vì nó phát tối đa một kết quả. `Flux` phù hợp với toàn bộ job vì nó phát lần lượt nhiều kết quả. Không dùng `collectList()` ở cuối pipeline để chuyển toàn bộ job thành `Mono<List<ImportResult>>`: cách đó buộc ứng dụng giữ mọi kết quả đến khi job hoàn tất và không phù hợp với consumer chậm.

Một bản ghi sai validation vẫn cần một `ImportResult` có trạng thái `REJECTED`, thay vì `Mono.empty()`. Nếu trả empty, consumer không thể phân biệt bản ghi bị từ chối với bản ghi không tồn tại trong luồng.

## 4. Chọn operator cho thứ tự và concurrency

Ba lựa chọn phổ biến có semantics khác nhau:

| Operator | Concurrency | Thứ tự đầu ra | Phù hợp khi |
| --- | --- | --- | --- |
| `concatMap` | Một publisher con tại một thời điểm | Giữ thứ tự nguồn | Cần xử lý tuần tự hoặc thao tác phụ thuộc nhau |
| `flatMap` | Có thể xử lý đồng thời theo giới hạn cấu hình | Theo thứ tự publisher con phát kết quả | Thứ tự không quan trọng và cần throughput |
| `flatMapSequential` | Subscribe publisher con đồng thời theo giới hạn | Giữ thứ tự nguồn | Cần concurrency nhưng response phải theo thứ tự đầu vào |

Với đề bài này, mỗi bản ghi được xử lý độc lập, nhưng kết quả phải theo thứ tự nguồn. Chỉ dùng `flatMapSequential` cho toàn bộ job có thể giữ nhiều kết quả đã hoàn tất phía sau một bản ghi chậm. Để giới hạn cả lượng dữ liệu chờ, chia nguồn thành các trang tối đa 64 bản ghi, xử lý một trang tại một thời điểm, rồi chạy tối đa 8 bản ghi đồng thời bên trong trang:

~~~java
import java.time.Duration;

private static final int PAGE_SIZE = 64;
private static final int MAX_IN_FLIGHT_LOOKUPS = 8;
private static final int INNER_PREFETCH = 1;
private static final Duration MAX_PAGE_WAIT =
    Duration.ofMillis(100);

Flux<ImportResult> importRows(Flux<ImportRow> rows) {
    return rows
        .bufferTimeout(PAGE_SIZE, MAX_PAGE_WAIT)
        .concatMap(page ->
            Flux.fromIterable(page)
                .flatMapSequential(
                    this::processOne,
                    MAX_IN_FLIGHT_LOOKUPS,
                    INNER_PREFETCH
                ),
            1
        );
}
~~~

`bufferTimeout` tạo trang có tối đa 64 bản ghi và flush sau 100 ms nếu trang chưa đầy. `concatMap(..., 1)` chỉ xử lý một trang tại một thời điểm và đặt prefetch của trang ở mức 1. Bên trong trang, `flatMapSequential` chạy tối đa 8 bản ghi đồng thời, giữ thứ tự và dùng prefetch 1 cho mỗi inner publisher. Mỗi `processOne` trả về `Mono` có tối đa một kết quả.

`flatMapSequential` có thể phải đệm kết quả của bản ghi hoàn tất sớm nếu một bản ghi trước đó còn chậm. Ví dụ, bản ghi thứ 2 đến thứ 8 đã xử lý xong nhưng bản ghi đầu tiên vẫn đang tra cứu; các kết quả sau phải chờ để giữ thứ tự. Trang tối đa 64 bản ghi đặt giới hạn cho lượng kết quả có thể chờ trong trang hiện tại; `concatMap` không chuyển sang trang tiếp theo cho đến khi trang hiện tại hoàn tất.

Nếu sản phẩm bỏ yêu cầu giữ thứ tự, có thể cân nhắc `flatMap(processOne, 8, 1)` trong từng trang để phát kết quả ngay khi hoàn tất. Nếu các thao tác phải chạy lần lượt, thay inner operator bằng `concatMap`. Hãy giải thích sự đánh đổi, không chỉ ghi tên operator.

## 5. Mô hình dữ liệu và dependency

Các kiểu dữ liệu dưới đây đủ để xây dựng service:

~~~java
import java.math.BigDecimal;

record ImportRow(
    long rowNumber,
    String sku,
    int quantity
) {}

record Product(String sku, BigDecimal unitPrice) {}

record EnrichedImport(
    long rowNumber,
    String sku,
    int quantity,
    BigDecimal unitPrice
) {}

enum ImportStatus {
    SAVED,
    REJECTED,
    LOOKUP_TIMEOUT
}

record ImportResult(
    long rowNumber,
    ImportStatus status,
    String detail
) {}

interface CatalogClient {
    // Emits one Product or an error; it must not silently complete empty.
    Mono<Product> findProduct(String sku);
}

interface ImportRepository {
    Mono<Void> save(EnrichedImport value);
}

interface ImportValidator {
    ValidationResult validate(ImportRow row);
}

record ValidationResult(boolean valid, String reason) {}
~~~

`ImportValidator` cần thực hiện validation thuần và nhanh. Không đặt thao tác blocking hoặc truy cập mạng trong hàm này. `CatalogClient` và `ImportRepository` phải trả về publisher reactive, không gọi `block()` bên trong adapter.

## 6. Xây dựng processOne với lỗi được phân loại

Quy tắc nghiệp vụ của đề:

- Validation không đạt: phát `REJECTED`, không gọi HTTP hoặc database.
- Tra cứu sản phẩm timeout: phát `LOOKUP_TIMEOUT`.
- Tra cứu thành công: lưu database trong transaction riêng rồi phát `SAVED`.
- Lỗi HTTP khác timeout hoặc lỗi database: truyền lỗi ra ngoài để job thất bại.

Có thể biểu diễn kết quả tra cứu bằng một kiểu riêng:

~~~java
sealed interface LookupOutcome
    permits ProductFound, ProductLookupTimedOut {}

record ProductFound(Product product) implements LookupOutcome {}

record ProductLookupTimedOut() implements LookupOutcome {}
~~~

Service xử lý một bản ghi:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

class ImportService {
    private static final Duration LOOKUP_TIMEOUT =
        Duration.ofSeconds(2);

    private final ImportValidator validator;
    private final CatalogClient catalogClient;
    private final ImportRepository repository;
    private final TransactionalOperator transactionalOperator;

    ImportService(
            ImportValidator validator,
            CatalogClient catalogClient,
            ImportRepository repository,
            TransactionalOperator transactionalOperator) {
        this.validator = validator;
        this.catalogClient = catalogClient;
        this.repository = repository;
        this.transactionalOperator = transactionalOperator;
    }

    Mono<ImportResult> processOne(ImportRow row) {
        ValidationResult validation = validator.validate(row);

        if (!validation.valid()) {
            return Mono.just(new ImportResult(
                row.rowNumber(),
                ImportStatus.REJECTED,
                validation.reason()
            ));
        }

        Mono<LookupOutcome> lookup = catalogClient
            .findProduct(row.sku())
            .timeout(LOOKUP_TIMEOUT)
            .<LookupOutcome>map(ProductFound::new)
            .onErrorResume(
                TimeoutException.class,
                error -> Mono.just(new ProductLookupTimedOut())
            );

        return lookup.flatMap(outcome -> {
            if (outcome instanceof ProductLookupTimedOut) {
                return Mono.just(new ImportResult(
                    row.rowNumber(),
                    ImportStatus.LOOKUP_TIMEOUT,
                    "Product lookup exceeded 2 seconds"
                ));
            }

            Product product = ((ProductFound) outcome).product();
            EnrichedImport value = new EnrichedImport(
                row.rowNumber(),
                row.sku(),
                row.quantity(),
                product.unitPrice()
            );

            return repository.save(value)
                .thenReturn(new ImportResult(
                    row.rowNumber(),
                    ImportStatus.SAVED,
                    "Stored"
                ))
                .as(transactionalOperator::transactional);
        });
    }
}
~~~

Điểm cần chú ý là `timeout` và phục hồi timeout chỉ bao quanh publisher tra cứu sản phẩm. Lỗi database không bị biến thành `LOOKUP_TIMEOUT`. Transaction chỉ bao quanh thao tác lưu database; ứng dụng không giữ connection hoặc transaction database trong lúc chờ HTTP.

Trong đề này, `CatalogClient` phải phát đúng một `Product` hoặc một lỗi có kiểu rõ ràng; không complete rỗng. Nếu adapter thực tế có thể trả empty khi không tìm thấy SKU, hãy bổ sung nhánh nghiệp vụ như `PRODUCT_NOT_FOUND` (hoặc ánh xạ sang `REJECTED`) trước khi đưa vào pipeline, để không làm mất kết quả của bản ghi đó. Không được âm thầm xem empty là `SAVED`.

Trong code thực tế, nếu `validator.validate` có thể ném exception, hãy quyết định rõ đó là lỗi dữ liệu cần chuyển thành `REJECTED` hay lỗi lập trình cần làm job thất bại. Không dùng một `onErrorResume` chung cho mọi exception.

## 7. Xây dựng pipeline của job

Thêm pipeline tổng:

~~~java
import java.time.Duration;

private static final int MAX_IN_FLIGHT_LOOKUPS = 8;
private static final int INNER_PREFETCH = 1;
private static final int PAGE_SIZE = 64;
private static final Duration MAX_PAGE_WAIT =
    Duration.ofMillis(100);

Flux<ImportResult> importRows(Flux<ImportRow> rows) {
    return rows
        .bufferTimeout(PAGE_SIZE, MAX_PAGE_WAIT)
        .concatMap(page ->
            Flux.fromIterable(page)
                .flatMapSequential(
                    this::processOne,
                    MAX_IN_FLIGHT_LOOKUPS,
                    INNER_PREFETCH
                ),
            1
        )
        .checkpoint("partner-import.process-rows");
}
~~~

Pipeline không subscribe nội bộ. Controller hoặc thành phần điều phối sở hữu subscription và trả `Flux<ImportResult>` cho WebFlux. Nhờ vậy, lifecycle của công việc gắn với consumer thực tế; cancellation có thể truyền ngược vào nguồn và các inner publisher.

Không gọi `subscribe()` trong `importRows`. Nếu service tự subscribe rồi trả về một publisher khác, ứng dụng sẽ có hai lifecycle độc lập: caller có thể nhận response trước khi xử lý xong, lỗi bị tách khỏi request và cancellation từ client không còn kiểm soát được công việc.

## 8. Đặt giới hạn tải ở đúng tầng

Một giới hạn concurrency cho mỗi job không đồng nghĩa giới hạn toàn ứng dụng. Nếu có 50 job cùng lúc và mỗi job cho phép 8 lookup, hệ thống có thể tạo đến 400 request HTTP đồng thời.

| Tầng | Giới hạn đề xuất | Mục đích |
| --- | --- | --- |
| Ingress | Body tối đa 10 MB | Ngăn request quá lớn trước khi parse |
| Parser | Tối đa 20.000 dòng mỗi job | Bảo vệ CPU, bộ nhớ và thời gian xử lý |
| Pipeline mỗi job | Trang 64 bản ghi; `concatMap(..., 1)` và `flatMapSequential(..., 8, 1)` bên trong trang | Tối đa 8 bản ghi đang xử lý đồng thời; kết quả chờ bị giới hạn trong trang hiện tại |
| HTTP client | Connection pool có giới hạn | Giới hạn socket và connection đang mở |
| Toàn ứng dụng | Bulkhead/semaphore hoặc admission control | Giới hạn tổng job và request đồng thời |
| Downstream service | Rate limiter theo quota | Giới hạn request mỗi giây, khác với concurrency |
| Database | Connection pool và transaction ngắn | Tránh giữ connection quá lâu |

Không dùng `take(20_000)` như cách xác thực giới hạn đầu vào: `take` sẽ complete sau 20.000 phần tử và có thể âm thầm bỏ phần dư. Parser hoặc tầng ingress phải phát lỗi rõ ràng nếu request vượt giới hạn. Với file lớn, parser cần phát từng dòng theo demand và không giữ toàn bộ file trong bộ nhớ.

`limitRate(n)` có thể điều tiết request được truyền lên upstream theo từng đợt, nhưng không phải giới hạn tổng số bản ghi, không thay thế parser limit, không thay connection pool và không thay rate limiter. Chỉ thêm nó khi cần kiểm soát request window của nguồn và đã hiểu tương tác với operator kế tiếp. Trong thiết kế trang ở trên, kích thước trang, prefetch của `concatMap` và concurrency nội trang đã thể hiện các giới hạn chính; không thêm `limitRate` chỉ để lặp lại cùng một giới hạn.

## 9. Transaction và vòng đời của từng bản ghi

Đề bài chọn transaction riêng cho mỗi bản ghi hợp lệ. Kết quả là:

- Bản ghi đã lưu thành công có transaction đã commit.
- Bản ghi tiếp theo có transaction riêng.
- Nếu một bản ghi sau đó thất bại, các bản ghi đã commit trước đó vẫn tồn tại.
- Nếu cancellation xảy ra trong khi đang lưu, reactive transaction manager xử lý cancellation theo semantics rollback và cleanup.

Không bọc toàn bộ `Flux<ImportRow>` trong một transaction kéo dài hàng phút. Cách đó có thể giữ connection, lock và snapshot lâu, đồng thời làm rollback toàn bộ job trở nên tốn kém.

Nếu nghiệp vụ yêu cầu all-or-nothing cho toàn bộ file, cần đánh giá lại kiến trúc: giới hạn kích thước file, staging table, trạng thái job và bước publish/commit cuối. Đừng giả định một transaction database lớn là lựa chọn phù hợp cho một stream không giới hạn.

Cancellation cũng không thể hoàn tác những transaction đã commit. Nếu job cần tiếp tục sau khi client ngắt kết nối, hãy chuyển ownership của job sang một worker bền vững, lưu tiến độ và cung cấp API truy vấn trạng thái. Một request streaming thông thường không tự trở thành durable background job.

## 10. Phân biệt lỗi nghiệp vụ, timeout và lỗi hạ tầng

Chọn đúng nơi phục hồi lỗi:

| Trường hợp | Hành vi mong đợi | Lý do |
| --- | --- | --- |
| Dòng thiếu SKU hoặc quantity không hợp lệ | Phát `REJECTED` | Lỗi dữ liệu thuộc riêng bản ghi |
| Product lookup quá 2 giây | Phát `LOOKUP_TIMEOUT` | Có trạng thái kết quả được định nghĩa trong hợp đồng |
| HTTP 5xx hoặc lỗi kết nối không phải timeout | Kết thúc job bằng lỗi | Hạ tầng đang không đáng tin cậy; không giả vờ là kết quả nghiệp vụ |
| Database save thất bại | Rollback transaction của bản ghi và kết thúc job | Không phát `SAVED` khi chưa commit |
| Client hủy | Propagate cancellation và cleanup | Caller không còn nhận kết quả |

Không đặt `onErrorResume(error -> Mono.empty())` ở cuối toàn bộ pipeline. Điều đó có thể biến lỗi database hoặc lỗi lập trình thành completion bình thường, khiến caller không biết job đã dừng giữa chừng.

Nếu cần retry lookup hoặc save, chỉ retry lỗi tạm thời đã phân loại, giới hạn số lần và dùng backoff. Lệnh save phải idempotent theo `jobId + rowNumber` hoặc khóa nghiệp vụ tương đương. Khi timeout xảy ra, client có thể đã hoàn tất thao tác ở server nhưng response chưa về; retry không có idempotency có thể tạo bản ghi trùng.

## 11. Cancellation và cleanup

Vòng đời một job streaming:

~~~mermaid
stateDiagram-v2
    [*] --> NotSubscribed
    NotSubscribed --> Running: subscribe
    Running --> Running: onNext / request
    Running --> Completed: onComplete
    Running --> Failed: onError
    Running --> Cancelled: cancel
    Completed --> [*]
    Failed --> [*]
    Cancelled --> Cleanup
    Cleanup --> [*]
~~~

Khi downstream hủy:

1. Cancellation được truyền ngược qua các operator.
2. Nguồn được yêu cầu dừng phát dữ liệu.
3. Các inner publisher đang hoạt động nhận cancellation.
4. HTTP client hoặc database driver cố gắng hủy I/O nếu hỗ trợ.
5. Transaction đang hoạt động được reactive transaction manager xử lý rollback/cleanup theo cấu hình.
6. Các transaction đã commit trước đó vẫn giữ dữ liệu.

Có thể quan sát tín hiệu kết thúc để ghi metric:

~~~java
return rows
    .bufferTimeout(PAGE_SIZE, MAX_PAGE_WAIT)
    .concatMap(page ->
        Flux.fromIterable(page)
            .flatMapSequential(this::processOne, 8, 1),
        1
    )
    .doFinally(signalType ->
        jobMetrics.recordTermination(signalType)
    );
~~~

Callback `doFinally` chạy cho complete, error hoặc cancel. Callback này nên ngắn và không blocking; nó không phải nơi để thực hiện cleanup bất đồng bộ cần chờ hoàn tất. Nếu cần quản lý tài nguyên bất đồng bộ có cleanup publisher, xem xét `usingWhen`.

Không giả định `cancel()` bảo đảm server HTTP từ xa đã ngừng xử lý. Với request đã gửi, server có thể đã ghi dữ liệu. Idempotency và khả năng đối soát vẫn cần thiết.

## 12. Kiểm thử thứ tự và concurrency bằng StepVerifier

Test thứ tự phải tạo các publisher con hoàn tất khác thời điểm. Ví dụ, bản ghi đầu chậm 300 ms, các bản ghi sau chỉ mất 50 ms:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OrderingTest {
    @Test
    void keepsInputOrderWhileProcessingConcurrently() {
        StepVerifier.withVirtualTime(() ->
            Flux.just(1, 2, 3)
                .buffer(3)
                .concatMap(page ->
                    Flux.fromIterable(page)
                        .flatMapSequential(
                            row -> Mono.delay(
                                    Duration.ofMillis(row == 1 ? 300 : 50)
                                )
                                .thenReturn(row),
                            3,
                            1
                        ),
                    1
                )
        )
            .thenAwait(Duration.ofMillis(300))
            .expectNext(1, 2, 3)
            .verifyComplete();
    }
}
~~~

Nếu đổi sang `flatMap`, kết quả có thể là `2, 3, 1`, vì các publisher con được phát theo thứ tự hoàn tất. Test phải phản ánh hợp đồng đã chọn, không dựa vào một thứ tự ngẫu nhiên của scheduler thật.

Test concurrency:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertTrue;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ConcurrencyTest {
    @Test
    void neverExceedsConfiguredConcurrency() {
        AtomicInteger inFlight = new AtomicInteger();
        AtomicInteger maxInFlight = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
            Flux.range(1, 20)
                .buffer(8)
                .concatMap(page ->
                    Flux.fromIterable(page)
                        .flatMapSequential(
                            value -> Mono.defer(() -> {
                                int active = inFlight.incrementAndGet();
                                maxInFlight.accumulateAndGet(active, Math::max);

                                return Mono.delay(Duration.ofMillis(100))
                                    .thenReturn(value)
                                    .doFinally(signal ->
                                        inFlight.decrementAndGet()
                                    );
                            }),
                            4,
                            1
                        ),
                    1
                )
        )
            .thenAwait(Duration.ofMillis(500))
            .expectNextCount(20)
            .verifyComplete();

        assertTrue(maxInFlight.get() <= 4);
        assertTrue(maxInFlight.get() > 1);
        assertTrue(inFlight.get() == 0);
    }
}
~~~

Test này xác minh giới hạn concurrency bằng bộ đếm đang hoạt động. Với virtual time, các timer hoàn tất mà không cần `Thread.sleep`. Khi kiểm thử service thật, thay các client bằng stub trả publisher có thời gian điều khiển được; integration test riêng xác minh connection pool và driver.

### Kiểm tra nhánh timeout

Lookup timeout phải được chuyển thành một kết quả nghiệp vụ, trong khi các lỗi khác vẫn đi ra ngoài:

~~~java
import java.util.concurrent.TimeoutException;

StepVerifier.withVirtualTime(() ->
        Mono.<Product>never()
            .timeout(Duration.ofSeconds(2))
            .<LookupOutcome>map(ProductFound::new)
            .onErrorResume(
                TimeoutException.class,
                error -> Mono.just(new ProductLookupTimedOut())
            )
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(new ProductLookupTimedOut())
    .verifyComplete();
~~~

Đây là phần lookup trong `processOne` được tách ra để kiểm thử. Bổ sung một test khác với `Mono.error(new IllegalStateException("catalog unavailable"))` để xác minh lỗi hạ tầng không bị chuyển thành `ProductLookupTimedOut`.

### Kiểm tra validation không gọi I/O

Với một dòng có quantity không hợp lệ, xác minh service phát `REJECTED` và không gọi catalog hoặc repository. Nếu dùng Mockito, thiết lập validator trả về `new ValidationResult(false, "quantity must be positive")`, sau đó:

~~~java
StepVerifier.create(service.processOne(invalidRow))
    .expectNextMatches(result ->
        result.status() == ImportStatus.REJECTED
            && result.rowNumber() == invalidRow.rowNumber()
    )
    .verifyComplete();

verifyNoInteractions(catalogClient, repository);
~~~

Test này bảo đảm validation dừng nhánh xử lý trước mọi I/O.

## 13. Kiểm thử demand và cancellation

Một consumer chậm có thể chỉ request một kết quả mỗi lần. `StepVerifier` cho phép điều khiển demand:

~~~java
StepVerifier.create(importService.importRows(rows), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNextMatches(result -> result.rowNumber() == 1)
    .thenRequest(1)
    .expectNextMatches(result -> result.rowNumber() == 2)
    .thenCancel()
    .verify();
~~~

Test trên xác minh consumer nhận kết quả theo từng request và chủ động hủy sau hai kết quả. Nếu muốn xác minh cancellation đến client, dùng fake client có `doOnCancel` hoặc publisher kiểm soát được:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger cancelledLookups = new AtomicInteger();

Mono<Product> lookup = Mono.<Product>never()
    .doOnCancel(cancelledLookups::incrementAndGet);
~~~

Sau khi hủy subscription chứa lookup, kiểm tra counter tăng. Với HTTP client hoặc R2DBC driver thật, cần integration test để xác minh adapter chuyển cancellation đến I/O như mong đợi.

## 14. Bài nộp và tiêu chí đánh giá

Hoàn thành các đầu việc sau:

1. **Requirement map:** điền bảng ở mục 2 với lựa chọn và lý do cho từng yêu cầu.
2. **Operator decision:** giải thích vì sao chọn `flatMapSequential` với concurrency 8 và prefetch 1; nêu điều gì thay đổi nếu dùng `concatMap` hoặc `flatMap`.
3. **Pipeline:** triển khai `processOne` và `importRows` theo hợp đồng cardinality và lỗi.
4. **Lifecycle:** mô tả complete, error và cancellation; chỉ rõ transaction nào commit, transaction nào rollback.
5. **Load limits:** nêu giới hạn ở ingress, parser, mỗi job, toàn ứng dụng, HTTP client và database.
6. **Tests:** viết test cho thứ tự, concurrency, timeout, validation rejection, demand và cancellation.
7. **Recovery:** giải thích cách tiếp tục job sau lỗi hoặc client disconnect mà không tạo dữ liệu trùng.

Tiêu chí đạt:

- Mỗi bản ghi tạo đúng một `ImportResult` cho các kết quả nghiệp vụ đã định nghĩa.
- Kết quả phát theo thứ tự đầu vào.
- Không vượt quá 8 lookup đồng thời trong một job.
- Validation rejection không gọi HTTP hoặc database.
- Timeout lookup tạo `LOOKUP_TIMEOUT`; lỗi hạ tầng vẫn được truyền ra ngoài.
- Transaction chỉ bao quanh thao tác database của một bản ghi hợp lệ.
- Không gom toàn bộ job vào một collection trong bộ nhớ.
- Cancellation truyền đến publisher nguồn và inner publisher; giới hạn của adapter được nêu rõ.
- Các giới hạn per-job và global được phân biệt.
- Test dùng `StepVerifier` và virtual time cho timer; không dùng `Thread.sleep`.

## 15. Các lỗi thiết kế cần tránh

- **Chọn `flatMap` dù yêu cầu giữ thứ tự:** kết quả có thể phát theo thứ tự hoàn tất.
- **Chọn `concatMap` cho mọi trường hợp:** có thể giảm throughput không cần thiết khi các thao tác độc lập.
- **Dùng `flatMapSequential` không giới hạn:** concurrency lớn có thể gây áp lực lên HTTP client và database.
- **Gom toàn bộ job bằng `collectList()`:** bộ nhớ tăng theo kích thước đầu vào.
- **Dùng `take(20_000)` để kiểm tra giới hạn:** dữ liệu vượt mức có thể bị cắt mà không báo lỗi.
- **Bọc HTTP lookup trong transaction database:** giữ connection và transaction trong lúc chờ network.
- **Nuốt mọi lỗi bằng `onErrorResume`:** caller không biết job đã thất bại giữa chừng.
- **Retry thao tác ghi không idempotent:** có thể tạo bản ghi trùng khi response trước bị mất.
- **Cho rằng cancellation rollback mọi dữ liệu:** các transaction đã commit không thể tự động bị hoàn tác.
- **Chỉ giới hạn concurrency mỗi job:** nhiều job đồng thời vẫn có thể vượt năng lực toàn hệ thống.
- **Nhầm concurrency với rate limit:** giới hạn số request đang chạy không đồng nghĩa giới hạn số request mỗi giây.
- **Giả định cancel luôn dừng remote server:** adapter và hệ thống đích có thể đã tiếp nhận thao tác.

## 16. Kết luận thực hành

Hãy đọc yêu cầu trước khi chọn operator. Cardinality quyết định `Mono` hay `Flux`; thứ tự và concurrency quyết định `concatMap`, `flatMap` hay `flatMapSequential`; timeout và error recovery phải đặt đúng ranh giới; transaction cần ngắn và gắn với thao tác database; cancellation phải được truyền qua subscription; load limit phải tồn tại ở cả cấp job lẫn cấp toàn ứng dụng. Khi mỗi quyết định được viết thành một hợp đồng có thể kiểm thử, pipeline reactive sẽ dễ giải thích, dễ vận hành và ít bất ngờ khi nguồn nhanh hơn consumer hoặc khi request kết thúc giữa chừng.
