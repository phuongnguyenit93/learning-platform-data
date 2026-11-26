# Ranh giới giao dịch khi tiêu thụ stream

Trong chương **Luồng và wrapper** của Spring Data Commons (`SPRING_DATA_COMMONS`), một repository có thể biểu diễn nhiều kết quả bằng `Stream<T>`. Khi stream còn phụ thuộc tài nguyên của kho dữ liệu, thao tác đọc chưa kết thúc chỉ vì repository đã trả về một đối tượng Java.

Ranh giới cần thiết kế là **đơn vị công việc bao trùm việc mở stream, tiêu thụ dữ liệu và đóng stream**. Với kho dữ liệu yêu cầu giao dịch trong lúc đọc, cả ba việc phải diễn ra khi giao dịch phù hợp vẫn còn hiệu lực.

Bài học dùng luồng xử lý mệnh lệnh, đồng bộ, trên cùng thread. Ví dụ giao dịch sử dụng Spring Data JPA; chúng không phải cam kết rằng mọi module Spring Data có cùng cách giữ connection, cursor hoặc session.

## 1. Phân biệt giao dịch, stream và dữ liệu đã lấy xong

Ba đối tượng sau có vòng đời khác nhau:

| Đối tượng | Vai trò | Điểm cần xác định |
| --- | --- | --- |
| Giao dịch | Định nghĩa phạm vi đọc hoặc ghi và cách hoàn tất công việc. | Ai mở, ai kết thúc, có tham gia giao dịch bên ngoài không? |
| Stream kết quả truy vấn | Cho phép ứng dụng duyệt kết quả theo pipeline. | Nguồn có còn cần tài nguyên của store trong khi duyệt không? |
| Kết quả đã tính xong | Ví dụ tổng tiền hoặc danh sách DTO có trường giá trị. | Có còn truy cập entity hoặc thuộc tính lazy sau khi trả về không? |

Trong Spring Data, hỗ trợ kiểu trả về `Stream<T>` phụ thuộc module. Stream truy vấn có thể giữ tài nguyên riêng của store và cần được đóng sau khi dùng. Không suy diễn quy tắc quản lý tài nguyên của một stream truy vấn từ `List.of(...).stream()`. Xem [Spring Data Commons: Streaming Query Results](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.query-streaming).

Ví dụ nghiệp vụ xuyên suốt: tính tổng tiền hóa đơn có trạng thái `READY` của một tenant. Caller cần nhận một `BigDecimal` đã tính xong; caller không cần giữ quyền điều khiển một nguồn đọc cơ sở dữ liệu.

## 2. Trì hoãn tiêu thụ không có nghĩa trì hoãn mọi hoạt động của truy vấn

Các phép toán trung gian của Java Stream như `map` và `filter` tạo pipeline. Phép toán kết thúc như `reduce`, `forEach` hoặc `findFirst` kích hoạt việc tiêu thụ nguồn. Đây là ngữ nghĩa của [Java Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).

Tuy nhiên, lời gọi repository vẫn có thể chuẩn bị hoặc thực thi truy vấn, mở tài nguyên và kiểm tra giao dịch ngay lúc tạo stream. Việc lấy thêm hàng cũng có thể tiếp tục trong khi duyệt. Không dùng quy tắc “Java Stream là lazy” để kết luận rằng chưa có truy cập store trước terminal operation.

Có thể hình dung một lượt đọc như sau:

```text
Caller
  -> đi qua proxy giao dịch của service
  -> bắt đầu hoặc tham gia giao dịch phù hợp
  -> gọi repository, nhận stream
  -> duyệt và tính kết quả
  -> đóng stream
  -> service hoàn tất
  -> phạm vi giao dịch kết thúc hoặc quay về giao dịch ngoài
  -> caller nhận kết quả đã tính xong
```

Nếu service tham gia một giao dịch bên ngoài, việc service trả về chưa đồng nghĩa giao dịch vật lý đã commit. Điều quan trọng tại đây là stream đã được tiêu thụ và đóng trước khi rời phạm vi mà service kiểm soát.

## 3. Repository khai báo query chưa đủ xác định ranh giới tiêu thụ

Giả sử ứng dụng có entity JPA `Invoice` với các thuộc tính sau:

| Thuộc tính | Kiểu Java | Giả định của ví dụ |
| --- | --- | --- |
| `id` | `Long` | Định danh không null, có thứ tự ổn định. |
| `tenantId` | `String` | Định danh tenant cần lọc. |
| `state` | `String` | Một giá trị có thể là `READY`. |
| `amount` | `BigDecimal` | Không null; các hóa đơn trong báo cáo dùng cùng đơn vị tiền. |

Entity đã được mapping, có getter tương ứng và repository scanning đã được cấu hình cho JPA. Repository chỉ cần khai báo khả năng truy vấn:

```java
import java.util.stream.Stream;

import org.springframework.data.repository.Repository;

public interface InvoiceRepository extends Repository<Invoice, Long> {

    Stream<Invoice> findByTenantIdAndStateOrderByIdAsc(
        String tenantId,
        String state
    );
}
```

`Repository` là abstraction chung; implementation thực tế do Spring Data JPA cung cấp trong ví dụ này. Tên method diễn đạt bộ lọc và thứ tự, còn kiểu trả về diễn đạt cách tiêu thụ.

Theo [Spring Data JPA: Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html), query method tự khai báo không tự nhận cấu hình giao dịch mặc định giống mọi method CRUD được kế thừa. Service có thể định nghĩa giao dịch bao trùm query và việc sử dụng kết quả.

Không lấy việc một method đọc CRUD có giao dịch để suy ra rằng mọi derived query trả stream đều có giao dịch phù hợp ở caller.

## 4. Service tính xong kết quả trước khi trả về

Một service cho đơn vị công việc trên:

```java
import java.math.BigDecimal;
import java.util.Objects;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceReportService {

    private final InvoiceRepository repository;

    public InvoiceReportService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public BigDecimal totalReadyAmount(String tenantId) {
        Objects.requireNonNull(tenantId, "tenantId");

        try (Stream<Invoice> invoices =
                 repository.findByTenantIdAndStateOrderByIdAsc(
                     tenantId,
                     "READY"
                 )) {

            return invoices
                .map(Invoice::getAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        }
    }
}
```

Caller gọi `totalReadyAmount` qua bean do Spring quản lý. Cấu hình giao dịch phải được kích hoạt và sử dụng transaction manager tương ứng với persistence unit của repository.

Các bước trong method có cùng phạm vi:

1. Repository nhận lời gọi khi giao dịch đang có hiệu lực.
2. `reduce` tính tổng ngay trong thân method.
3. `try-with-resources` đóng stream khi rời khối.
4. Giá trị tiền đã tính xong được trả về qua proxy giao dịch.

Nếu không có hóa đơn phù hợp, phép cộng với identity `BigDecimal.ZERO` trả về số không. Nếu một bước đọc ném lỗi, method không trả một tổng tiền từng phần như thể báo cáo đã hoàn thành.

Dòng `return` bên trong `try` không bỏ qua việc đóng tài nguyên: Java tính giá trị trả về rồi thực hiện phần đóng trước khi method thực sự hoàn tất.

Ví dụ dùng stream để minh họa vòng đời giao dịch. Nếu nhu cầu chỉ là một phép tổng hợp có thể biểu diễn trực tiếp ở store, một query tổng hợp cũng là lựa chọn cần đánh giá theo use case.

## 5. Vì sao trả stream ra khỏi service dễ làm mất phạm vi cần thiết?

Xét thiết kế sau:

```java
@Transactional(readOnly = true)
public Stream<Invoice> openReadyInvoices(String tenantId) {
    return repository.findByTenantIdAndStateOrderByIdAsc(
        tenantId,
        "READY"
    );
}
```

Caller mới thực hiện phần tiêu thụ:

```java
try (Stream<Invoice> invoices = service.openReadyInvoices("ACME")) {
    BigDecimal total = invoices
        .map(Invoice::getAmount)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
}
```

Giả sử caller không có giao dịch bao trùm và service vừa tạo một giao dịch mới. Giao dịch của service kết thúc khi method trả về. Phần `reduce` ở caller diễn ra sau đó, trong khi nguồn vẫn có thể cần tài nguyên gắn với giao dịch vừa kết thúc.

Trong triển khai Spring Data JPA, đường thực thi stream còn có thể phát hiện việc thiếu giao dịch bao quanh trước khi trả stream. Có thể xem cơ chế này trong [JpaQueryExecution.StreamExecution, Spring Data JPA 3.5.0](https://github.com/spring-projects/spring-data-jpa/blob/3.5.0/spring-data-jpa/src/main/java/org/springframework/data/jpa/repository/query/JpaQueryExecution.java). Đây là minh họa theo một implementation, không phải thông báo lỗi chung cho mọi store.

Các thiết kế cần được phân biệt:

| Cách tổ chức | Điều cần kết luận |
| --- | --- |
| Service mở giao dịch, tiêu thụ và đóng stream trước khi trả kết quả | Vòng đời đọc nằm trong phạm vi service kiểm soát. |
| Service mở giao dịch mới rồi trả một stream chưa tiêu thụ | Annotation trên service không tự kéo dài giao dịch đến lúc caller duyệt. |
| Caller có giao dịch bao trùm cả lời gọi service và việc tiêu thụ | Có thể phù hợp nếu cùng tài nguyên, cùng thread và stream được đóng trong phạm vi đó. |
| Service trả DTO đã được tạo đầy đủ | Caller không cần tiếp tục đọc từ stream truy vấn đó. |

Đặt `@Transactional` chỉ tại repository cũng không thay thế việc thiết kế phạm vi của caller. Cần biết giao dịch nào còn tồn tại khi terminal operation chạy.

## 6. Đóng stream và kết thúc giao dịch là hai trách nhiệm

Một terminal operation hoàn tất việc tính toán, nhưng không thay cho lời gọi `close()` của stream. `BaseStream.close()` gọi các close handler của pipeline; xem [Java BaseStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html).

Vì vậy, vẫn cần `try-with-resources` ngay cả khi chỉ lấy một phần tử:

```java
import java.math.BigDecimal;
import java.util.Optional;

public record InvoiceLine(Long id, BigDecimal amount) {}
```

Đoạn method sau đặt trong service có repository ở trên:

```java
@Transactional(readOnly = true)
public Optional<InvoiceLine> firstReadyInvoice(String tenantId) {
    try (Stream<Invoice> invoices =
             repository.findByTenantIdAndStateOrderByIdAsc(
                 tenantId,
                 "READY"
             )) {

        return invoices
            .map(invoice -> new InvoiceLine(
                invoice.getId(),
                invoice.getAmount()
            ))
            .findFirst();
    }
}
```

`findFirst` có thể kết thúc mà chưa duyệt hết nguồn. Khối `try` vẫn đóng stream. Kết quả trả về chứa `Long` và `BigDecimal`, không chứa entity hoặc hàm đọc lazy cần gọi sau này.

Hai nhận định cần giữ riêng:

- Đóng stream giải phóng những tài nguyên mà stream sở hữu theo implementation.
- Đóng stream không phải lệnh commit giao dịch nghiệp vụ.

Tương tự, không dùng việc giao dịch cuối cùng sẽ kết thúc làm lý do để bỏ qua trách nhiệm đóng stream.

## 7. readOnly và propagation không tạo thêm thời gian sống cho stream

`@Transactional(readOnly = true)` mô tả một giao dịch phục vụ đọc. Đây là hint cho hạ tầng, không phải cơ chế bảo đảm rằng mọi thao tác ghi đều bị chặn. Cấu hình rollback mặc định và ý nghĩa các thuộc tính được mô tả trong [API Transactional](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/annotation/Transactional.html).

Trong ví dụ, `readOnly` phù hợp vì service chỉ đọc giá trị và tính tổng. Nếu consumer thay đổi entity hoặc gọi nghiệp vụ ghi, cần xác định một đơn vị công việc khác và cấu hình tương ứng.

Với propagation mặc định `REQUIRED`, method có thể tạo giao dịch mới hoặc tham gia giao dịch đang tồn tại. Khi tham gia, các đặc tính giao dịch ngoài thường chi phối giao dịch thực tế. Không mặc định annotation của method con tạo một giao dịch đọc độc lập. Xem [Spring Framework: Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html).

Ví dụ suy luận:

```text
Outer service đã có giao dịch
    -> gọi report service dùng REQUIRED
    -> đọc và đóng stream
    -> report service trả kết quả
    -> outer service tiếp tục công việc
    -> outer service mới kết thúc giao dịch của nó
```

Đổi sang `REQUIRES_NEW` không sửa thiết kế trả stream chưa tiêu thụ: nếu method sở hữu giao dịch mới kết thúc trước lúc caller đọc, vấn đề thời gian sống vẫn còn.

## 8. Dùng callback để giữ quyền sở hữu stream tại service

Khi cần xử lý từng dòng thay vì trả tổng tiền, service có thể nhận một callback đồng bộ. Service giữ quyền mở và đóng nguồn; callback chỉ nhận dữ liệu giá trị.

Đoạn method sau cũng thuộc service sử dụng `InvoiceRepository`:

```java
import java.util.Objects;
import java.util.function.Consumer;
import java.util.stream.Stream;

@Transactional(readOnly = true)
public void visitReadyInvoices(
    String tenantId,
    Consumer<InvoiceLine> consumer
) {
    Objects.requireNonNull(consumer, "consumer");

    try (Stream<Invoice> invoices =
             repository.findByTenantIdAndStateOrderByIdAsc(
                 tenantId,
                 "READY"
             )) {

        invoices
            .map(invoice -> new InvoiceLine(
                invoice.getId(),
                invoice.getAmount()
            ))
            .forEach(consumer);
    }
}
```

Hợp đồng của method là callback chạy đồng bộ trong lúc service đang duyệt. Caller không nhận `Stream` hoặc `Iterator` để giữ lại.

Giả sử callback định dạng mỗi dòng rồi ghi vào một bộ đệm có giới hạn. Tốc độ callback quyết định tốc độ service hoàn thành lượt đọc. Nếu callback chờ một hệ thống bên ngoài lâu, giao dịch đọc cũng phải chờ theo.

Nếu callback đẩy `InvoiceLine` sang một hàng đợi để xử lý sau, công việc sau đó nằm ngoài phạm vi giao dịch của lượt duyệt. Chỉ dữ liệu giá trị đã được tạo là thứ chuyển sang; giao dịch không đi cùng DTO.

Thiết kế callback giúp nhìn rõ ownership tài nguyên, nhưng không tự tạo chính sách retry, checkpoint hoặc hoàn tất đồng thời với hệ thống nhận dữ liệu.

## 9. TransactionTemplate: đặt toàn bộ việc tiêu thụ trong callback giao dịch

Có thể định nghĩa phạm vi bằng lập trình khi ranh giới công việc dễ diễn đạt bằng callback. Với luồng mệnh lệnh, Spring cung cấp `TransactionTemplate`; xem [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).

Một phiên bản khác của service tính tổng:

```java
import java.math.BigDecimal;
import java.util.Objects;
import java.util.stream.Stream;

import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ProgrammaticInvoiceReport {

    private final InvoiceRepository repository;
    private final TransactionTemplate readTransaction;

    public ProgrammaticInvoiceReport(
        InvoiceRepository repository,
        PlatformTransactionManager transactionManager
    ) {
        this.repository = repository;
        this.readTransaction =
            new TransactionTemplate(transactionManager);
        this.readTransaction.setReadOnly(true);
    }

    public BigDecimal totalReadyAmount(String tenantId) {
        BigDecimal result = readTransaction.execute(status -> {
            try (Stream<Invoice> invoices =
                     repository.findByTenantIdAndStateOrderByIdAsc(
                         tenantId,
                         "READY"
                     )) {

                return invoices
                    .map(Invoice::getAmount)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
            }
        });

        return Objects.requireNonNull(result);
    }
}
```

Transaction manager được inject phải quản lý đúng tài nguyên JPA đang dùng. Nếu ứng dụng có nhiều manager, cần chọn bean đúng theo cấu hình của ứng dụng.

Callback phải trả kết quả đã tính xong. Không viết:

```java
Stream<Invoice> invoices = readTransaction.execute(status ->
    repository.findByTenantIdAndStateOrderByIdAsc("ACME", "READY")
);
```

Đoạn trên lại đưa công việc đọc ra ngoài callback. `TransactionTemplate` quản lý thời gian chạy callback; nó không theo dõi lần tiêu thụ tương lai của một Java Stream được callback trả về. Xem hợp đồng [TransactionTemplate.execute](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html).

Cũng không mở stream trước rồi mới bao terminal operation trong một giao dịch khác. Việc tạo nguồn có thể đã yêu cầu giao dịch, và tài nguyên nguồn không tự chuyển sang giao dịch mới.

## 10. Lời gọi phải đi qua cơ chế giao dịch thực tế

Trong chế độ proxy thông thường, annotation chỉ có tác dụng khi lời gọi đi qua proxy phù hợp. Một lời gọi nội bộ như sau không tự tạo giao dịch mới cho helper:

```java
public BigDecimal runReport(String tenantId) {
    return this.totalReadyAmount(tenantId);
}

@Transactional(readOnly = true)
public BigDecimal totalReadyAmount(String tenantId) {
    // Mở, tiêu thụ và đóng stream ở đây.
    // Nếu runReport chưa có giao dịch thì annotation của lời gọi
    // this.totalReadyAmount không tự bổ sung giao dịch trong proxy mode.
    return calculateInsideCurrentScope(tenantId);
}
```

Đây là sơ đồ minh họa lời gọi; `calculateInsideCurrentScope` đại diện cho thân xử lý stream đã trình bày, không phải API Spring Data.

Có thể đặt ranh giới tại method public được caller bên ngoài gọi qua bean, tách sang một bean khác, hoặc dùng `TransactionTemplate` để biểu diễn phạm vi rõ ràng. Quy tắc self-invocation được giải thích trong [Spring Framework: Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).

Một instance tạo bằng `new InvoiceReportService(...)` cũng không tự có proxy giao dịch. Cần phân biệt việc Java gọi được một method với việc hạ tầng Spring đã áp dụng giao dịch cho lời gọi đó.

## 11. Không chuyển stream đang mở sang thread khác để “tiếp tục giao dịch”

Với transaction manager mệnh lệnh thông thường, tài nguyên giao dịch gắn với thread. Các callback chạy bởi `parallel()`, executor hoặc tác vụ async không tự thừa hưởng giao dịch của thread mở stream. Cơ chế quản lý tài nguyên theo thread được mô tả trong [TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html).

Những dạng tổ chức sau cần tránh khi vẫn phụ thuộc nguồn đang mở:

```java
// Không dùng đây làm cách chia sẻ giao dịch đọc hiện tại.
invoices.parallel().forEach(this::processInvoice);

// Không để tác vụ tiếp tục tiêu thụ nguồn sau khi service đóng nguồn.
executor.submit(() -> invoices.forEach(this::processInvoice));
```

Nếu công việc cần song song, một cách tổ chức là đọc một batch có giới hạn thành DTO giá trị, đóng stream và hoàn tất phạm vi đọc, rồi giao batch cho các tác vụ xử lý độc lập. Mỗi tác vụ cần ghi store sẽ thiết lập giao dịch riêng phù hợp.

Điều đó thay đổi đơn vị công việc: batch đã đọc và việc xử lý về sau không mặc nhiên thuộc cùng một giao dịch.

Java `Stream<T>` cũng không phải reactive publisher. Không chuyển nguyên mô hình thread và `try-with-resources` ở bài này sang `Flux<T>` rồi coi hai vòng đời giao dịch là tương đương.

## 12. Lỗi đọc, lỗi xử lý và kết quả bên ngoài giao dịch

Một lượt báo cáo có thể thất bại tại nhiều điểm:

| Thời điểm | Ví dụ | Hệ quả đối với hợp đồng method |
| --- | --- | --- |
| Mở nguồn | Store từ chối tạo truy vấn hoặc thiếu giao dịch cần thiết. | Chưa có kết quả báo cáo hoàn chỉnh. |
| Duyệt nguồn | Không lấy được hàng tiếp theo. | Kết quả đã cộng dồn mới là kết quả từng phần. |
| Chạy callback | Bộ nhận dữ liệu ném lỗi khi xử lý một dòng. | Một phần tác động bên ngoài có thể đã xảy ra. |
| Đóng nguồn | Close handler ném lỗi. | Không được mặc định lượt đọc đã kết thúc bình thường. |
| Hoàn tất giao dịch | Hạ tầng không hoàn tất được giao dịch. | Caller có thể nhận lỗi sau khi thân method đã tính xong. |

`try-with-resources` vẫn thực hiện đóng khi thân khối ném lỗi. Nếu phần thân và phần đóng cùng thất bại, cần xem cả suppressed exceptions khi chẩn đoán.

Theo cấu hình Spring mặc định không có quy tắc rollback tùy chỉnh, `RuntimeException` và `Error` dẫn đến rollback; checked exception không mặc nhiên có cùng quy tắc. Với một callback có nghiệp vụ ghi, phải thiết kế cách truyền lỗi và rollback tương ứng, không chỉ thêm `try/catch` rồi trả bình thường.

Ví dụ gốc chỉ đọc và cộng tiền trong bộ nhớ. Nếu đổi callback thành gửi email cho từng hóa đơn, rollback cơ sở dữ liệu không tự thu hồi các email đã gửi. Nếu cần retry toàn lượt, người thiết kế phải xác định cách tránh lặp các tác động đã thành công.

Stream không tự lưu vị trí nghiệp vụ để chạy tiếp. Một terminal operation bị lỗi cũng không biến stream thành nguồn có thể đọc lại từ đầu.

## 13. Giao dịch dài và giả định về kho dữ liệu

Giả sử có 200.000 hóa đơn. Mỗi callback đợi 50 ms ở một dịch vụ ngoài. Chỉ riêng thời gian chờ tuần tự đã khoảng 10.000 giây, tức khoảng 2 giờ 47 phút.

Nếu giữ stream và giao dịch đọc xuyên suốt lượt đó, chi phí không chỉ là số lượng phần tử đang có trong biến Java. Connection, cursor, session và phiên bản dữ liệu được giữ ra sao còn phụ thuộc store và cấu hình.

Các lựa chọn cần cân nhắc theo yêu cầu công việc:

| Yêu cầu | Cách tổ chức có thể phù hợp | Điều phải xác định thêm |
| --- | --- | --- |
| Tính một báo cáo nhỏ trong thời gian ngắn | Tiêu thụ stream trong một giao dịch đọc. | Thời lượng và khả năng của store. |
| Xử lý dữ liệu rất lớn, cần tiếp tục sau lỗi | Chia theo batch hoặc vị trí duyệt có checkpoint. | Thứ tự ổn định, tác động của dữ liệu thay đổi, chính sách retry. |
| Sau khi đọc phải chờ hệ thống ngoài | Tạo dữ liệu giá trị trong phạm vi đọc, xử lý tiếp theo hợp đồng riêng. | Ranh giới hoàn tất và khả năng lặp tác động. |
| Cần một ảnh chụp dữ liệu nhất quán | Thiết kế theo isolation và cơ chế snapshot của store. | Không suy ra bảo đảm snapshot chỉ từ kiểu Stream. |

Với JPA, entity đã đọc còn có thể được persistence context giữ lại. Việc tiêu thụ bằng stream không tự bảo đảm tổng bộ nhớ của ứng dụng là hằng số. Độ lớn bộ đệm của driver, cách provider lấy dữ liệu và việc consumer tích lũy kết quả đều cần được xem xét trong môi trường thực tế.

Projection có thể giúp biểu diễn đúng các trường cần dùng, nhưng một projection vẫn lấy dữ liệu từ stream truy vấn không làm mất nhu cầu quản lý vòng đời nguồn.

Ngoài ra, Open EntityManager in View giữ EntityManager cho xử lý request, không phải lời hứa kéo dài giao dịch service đến cuối request. Mục đích và phạm vi của cơ chế này được nêu tại [OpenEntityManagerInViewFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/support/OpenEntityManagerInViewFilter.html).

## 14. Bài thực hành: xác định ranh giới trước khi thay đổi code

Với repository hóa đơn ở trên, hãy phân tích từng tình huống:

1. Controller gọi service tính tổng; service mở, tiêu thụ và đóng stream.
2. Service trả stream, controller gọi `findFirst` sau khi service đã trả về và caller không có giao dịch ngoài.
3. Service trả một `List<InvoiceLine>` đã tạo đầy đủ; controller duyệt list đó sau khi service trả về.
4. Service chạy `forEach`, callback ném lỗi ở hóa đơn thứ tư.
5. Service nhận stream rồi chuyển nó sang executor.
6. Một test đang có sẵn giao dịch gọi service trả stream, khiến thiết kế ở tình huống 2 có vẻ chạy được.

Kết quả phân tích cần thể hiện:

| Tình huống | Điểm mấu chốt |
| --- | --- |
| 1 | Caller chỉ nhận kết quả đã tính; stream nằm trọn trong phạm vi service. |
| 2 | Cần sửa ranh giới mở và tiêu thụ; annotation trên method trả stream chưa đủ. |
| 3 | Việc duyệt list giá trị không còn đọc từ nguồn truy vấn đó; vẫn phải xét kích thước list. |
| 4 | Nguồn cần được đóng; phải phân biệt tác động đã thực hiện với báo cáo hoàn tất. |
| 5 | Giao dịch và quyền sở hữu tài nguyên không tự chuyển sang executor. |
| 6 | Giao dịch do test tạo có thể che mất việc caller thực tế không có giao dịch bao trùm. |

Khi thực hành tích hợp trong một môi trường có store thật, quan sát thời điểm service được gọi qua proxy, lúc lấy phần tử đầu tiên, lúc đóng nguồn và lúc caller nhận kết quả. Đừng dùng một stream tạo từ collection trong bộ nhớ làm bằng chứng rằng vòng đời tài nguyên của repository đã đúng.

Mục tiêu thiết kế là chỉ rõ ai sở hữu nguồn, ai tiêu thụ nó và phạm vi nào còn có hiệu lực trong suốt lượt đọc. Khi caller nhận một kết quả đã hoàn chỉnh và tài nguyên đã được đóng trong phạm vi phù hợp, hợp đồng của service trở nên dễ sử dụng và kiểm chứng hơn.
