# Kiểm thử ca sử dụng với các cổng hạ tầng được thay thế

Trong Domain-Driven Design (DDD), ca sử dụng (use case) điều phối hành vi của mô hình miền và các cộng tác viên cần thiết để hoàn thành một mục tiêu của người dùng. Những cộng tác viên này thường bao gồm repository, cổng gọi dịch vụ bên ngoài, đồng hồ hệ thống, message publisher hoặc đơn vị công việc (Unit of Work).

Nếu kiểm thử ca sử dụng bằng database thật, message broker thật và HTTP service thật trong mọi trường hợp, test sẽ chậm, khó tái lập và dễ thất bại vì môi trường. Một cách tiếp cận hiệu quả là **thay thế các cổng hạ tầng bằng test double**: fake, stub hoặc spy có hành vi được kiểm soát trong bộ nhớ. Nhờ vậy, test tập trung vào quyết định và kết quả của use case, trong khi adapter thật được kiểm thử riêng ở tầng tích hợp.

Bài học này giải thích cách thiết kế port để thay thế được, cách tạo test double có ý nghĩa, cách kiểm thử nhánh thành công và thất bại, cách kiểm soát thời gian và cách xác định phần nào vẫn cần integration test.

Sau bài học, người học có thể:

- Giải thích vì sao use case nên phụ thuộc vào port thay vì lớp hạ tầng cụ thể.
- Phân biệt fake, stub, spy, mock và dummy.
- Viết test cho application service bằng repository và gateway giả lập.
- Kiểm soát thời gian bằng Clock cố định để test ổn định.
- Kiểm tra kết quả nghiệp vụ, trạng thái aggregate và các yêu cầu gửi ra port.
- Tránh mock quá mức và tránh test phụ thuộc vào chi tiết triển khai.
- Phân biệt use case test với domain unit test, adapter integration test và end-to-end test.
- Xác định giới hạn của fake và phần cần xác minh với database, broker hoặc hệ thống bên ngoài thật.

## 1. Vì sao cần thay thế cổng hạ tầng khi kiểm thử use case?

Một use case thường phối hợp nhiều thành phần. Ví dụ, khi nhân viên xem các hóa đơn quá hạn, application service có thể:

1. Tải hóa đơn của khách hàng từ Invoice Repository.
2. Xác định ngày nghiệp vụ hiện tại.
3. Hỏi Payment Context những hóa đơn nào đã được thanh toán.
4. Loại các hóa đơn đã thanh toán.
5. Trả về danh sách hóa đơn quá hạn cho màn hình.

Nếu test gọi database và Payment API thật, nó đang kiểm tra đồng thời logic use case, câu SQL, mapping ORM, network, authentication và trạng thái của hệ thống bên ngoài. Khi test thất bại, khó biết lỗi nằm ở đâu.

Thay các cổng bằng implementation trong bộ nhớ giúp test cô lập phần điều phối:

~~~text
             Use Case Test
                  |
                  v
       FindOverdueInvoicesHandler
          /          |          \
         /           |           \
        v            v            v
  Fake Invoice   Fake Payment   Fixed Clock
  Repository     Status Port
        |            |
        v            v
   In-memory     Canned payment
   invoices      status result
~~~

Use case vẫn chạy qua các interface mà production sử dụng. Chỉ các implementation ở phía ngoài được thay bằng test double. Đây là cách kiểm tra application layer mà không cần khởi động toàn bộ hệ thống.

### Test cần chứng minh điều gì?

Một use case test nên trả lời được:

- Với dữ liệu đầu vào và trạng thái ban đầu này, kết quả có đúng không?
- Quy tắc nghiệp vụ nào được áp dụng?
- Khi port trả về kết quả khác hoặc lỗi, use case phản ứng thế nào?
- Dữ liệu có được lưu hoặc yêu cầu bên ngoài có được gửi đúng theo hợp đồng không?
- Những nhánh quan trọng có được xử lý an toàn không?

Test không cần chứng minh rằng một câu SQL cụ thể đã chạy hoặc một HTTP client đã gọi đúng thư viện. Đó là trách nhiệm của adapter test.

## 2. Port là ranh giới giúp thay thế hạ tầng

### Use case phụ thuộc vào interface có ý nghĩa

Trong kiến trúc hướng cổng và bộ chuyển đổi (Ports and Adapters), application layer định nghĩa những khả năng mà use case cần. Adapter ở infrastructure layer triển khai các interface đó.

Ví dụ:

~~~java
public interface InvoiceRepository {
    List<Invoice> findByCustomer(CustomerId customerId);
}

public interface PaymentStatusPort {
    Set<InvoiceId> findSettledInvoiceIds(Set<InvoiceId> invoiceIds);
}
~~~

Use case biết rằng nó có thể tìm hóa đơn và hỏi trạng thái thanh toán. Nó không cần biết dữ liệu đến từ PostgreSQL, REST API, message projection hay một fake trong test.

Một adapter production có thể là JpaInvoiceRepository và HttpPaymentStatusAdapter. Trong test, có thể dùng InMemoryInvoiceRepository và FakePaymentStatusPort.

### Đặt port ở phía sở hữu nhu cầu

Tên và kiểu dữ liệu của port nên phản ánh ngôn ngữ của use case hoặc domain. Tránh để application layer phụ thuộc vào kiểu của framework như EntityManager, JpaRepository, RestTemplate hoặc KafkaTemplate.

Không nên để use case nhận trực tiếp:

~~~java
public class FindOverdueInvoicesHandler {
    private final EntityManager entityManager;
    private final RestTemplate restTemplate;
}
~~~

Thay vào đó, use case nhận các interface có ý nghĩa:

~~~java
public class FindOverdueInvoicesHandler {
    private final InvoiceRepository invoices;
    private final PaymentStatusPort payments;
}
~~~

Adapter chịu trách nhiệm chuyển đổi giữa hợp đồng của port và giao thức kỹ thuật. Cách này giúp domain/application code có thể được kiểm thử độc lập với framework.

### Không tạo port chỉ để bọc một thư viện

Port hữu ích khi nó thể hiện một nhu cầu của use case hoặc một ranh giới cần thay thế. Không cần tạo interface cho mọi class hoặc mọi hàm nội bộ. Quá nhiều abstraction không có ý nghĩa làm code khó điều hướng mà không tăng khả năng kiểm thử.

## 3. Phân biệt các loại Test Double

Test double là một đối tượng thay thế cộng tác viên thật trong test. Các loại phổ biến có mục đích khác nhau:

| Loại | Mục đích | Ví dụ |
|---|---|---|
| Dummy | Được truyền vào nhưng không được sử dụng | Một actor ID không liên quan đến nhánh đang test |
| Stub | Trả về kết quả đã định trước | Payment port trả về tập invoice đã thanh toán |
| Fake | Implementation đơn giản nhưng có hành vi thực | Repository lưu entity trong Map |
| Spy | Ghi nhận lời gọi để test có thể quan sát | Publisher lưu các event đã nhận |
| Mock | Thiết lập kỳ vọng và xác minh tương tác | Xác nhận port được gọi với đúng command |

### Fake thường hữu ích cho use case test

Fake có logic đủ để hoạt động giống một phiên bản nhỏ của port, nhưng không có hạ tầng thật. Ví dụ, repository trong bộ nhớ có thể lưu Invoice theo ID, tìm theo CustomerId và trả về bản sao danh sách.

Fake giúp test dễ đọc vì dữ liệu đầu vào và trạng thái sau xử lý có thể được quan sát trực tiếp.

### Stub phù hợp khi chỉ cần kiểm soát câu trả lời

Nếu use case chỉ cần biết Payment Context trả về những invoice nào đã thanh toán, một stub đơn giản có thể trả về tập ID đã cấu hình. Không cần xây một mô hình Payment đầy đủ.

### Spy dùng khi kết quả không đủ để xác nhận hành vi

Ví dụ use case phải yêu cầu lưu một aggregate hoặc phát một thông báo. Recording spy có thể lưu các lệnh đã nhận để test kiểm tra payload. Tuy nhiên, nếu trạng thái lưu có thể quan sát qua fake repository thì không cần thêm spy cho cùng mục đích.

### Mock không nên trở thành bản sao của implementation

Mock hữu ích khi cần xác nhận một tương tác là một phần hợp đồng, ví dụ không được gửi lệnh thu tiền nếu đơn chưa hợp lệ. Nhưng test chỉ xác minh chuỗi gọi hàm nội bộ sẽ dễ vỡ khi refactor.

Ưu tiên kiểm tra kết quả quan sát được và trạng thái có ý nghĩa. Chỉ xác minh tương tác khi tương tác đó có ý nghĩa nghiệp vụ hoặc là cam kết của port.

## 4. Ví dụ xuyên suốt: tìm hóa đơn quá hạn

Ta xây dựng use case cho Accounts Receivable Context. Mục tiêu là liệt kê các hóa đơn đang mở, đã quá hạn theo ngày nghiệp vụ hiện tại và chưa được Payment Context xác nhận thanh toán.

Use case cần ba cộng tác viên:

- InvoiceRepository: tải hóa đơn của khách hàng.
- PaymentStatusPort: hỏi Payment Context về các hóa đơn đã quyết toán.
- Clock: cung cấp thời điểm hiện tại có thể kiểm soát trong test.

Ngày nghiệp vụ được tính theo ZoneId của tổ chức. Ví dụ dùng Asia/Ho_Chi_Minh để thể hiện rằng ngày ở Việt Nam có thể khác ngày UTC tại cùng một Instant.

### Các kiểu miền tối thiểu

~~~java
import java.time.LocalDate;
import java.util.UUID;

public record CustomerId(UUID value) {
}

public record InvoiceId(UUID value) {
}

public enum InvoiceStatus {
    OPEN,
    PAID,
    VOID
}

public record Invoice(
        InvoiceId id,
        CustomerId customerId,
        LocalDate dueDate,
        InvoiceStatus status
) {
    public boolean isOverdueOn(LocalDate businessDate) {
        return status == InvoiceStatus.OPEN
                && dueDate.isBefore(businessDate);
    }
}
~~~

Trong ví dụ, dueDate là LocalDate vì hạn thanh toán được quy định theo ngày lịch nghiệp vụ, không phải một thời điểm UTC. Hóa đơn đến hạn đúng ngày hôm nay chưa được xem là quá hạn; điều kiện dùng isBefore thay vì isBefore hoặc isEqual.

### Các port của use case

~~~java
import java.util.List;

public interface InvoiceRepository {
    List<Invoice> findByCustomer(CustomerId customerId);
}
~~~

~~~java
import java.util.Set;

public interface PaymentStatusPort {
    Set<InvoiceId> findSettledInvoiceIds(Set<InvoiceId> invoiceIds);
}
~~~

PaymentStatusPort chỉ trả về những ID đã được xác nhận quyết toán trong phạm vi các ID được yêu cầu. Nó không trả về Payment entity hoặc kiểu của HTTP client. Nếu Payment Context không sẵn sàng, adapter có thể ném một exception có ý nghĩa như PaymentStatusUnavailable; use case không nên tự giả định rằng không có khoản thanh toán.

### Query và kết quả

~~~java
import java.util.UUID;

public record FindOverdueInvoices(CustomerId customerId) {
}

public record OverdueInvoiceSummary(
        InvoiceId invoiceId,
        LocalDate dueDate,
        long daysOverdue
) {
}
~~~

Kết quả chỉ chứa dữ liệu màn hình cần. Không trả toàn bộ aggregate nếu use case chỉ cần mã hóa đơn, ngày đến hạn và số ngày quá hạn.

### Application service

~~~java
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.temporal.ChronoUnit;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public final class FindOverdueInvoicesHandler {
    private final InvoiceRepository invoices;
    private final PaymentStatusPort payments;
    private final Clock clock;
    private final ZoneId businessZone;

    public FindOverdueInvoicesHandler(
            InvoiceRepository invoices,
            PaymentStatusPort payments,
            Clock clock,
            ZoneId businessZone
    ) {
        this.invoices = invoices;
        this.payments = payments;
        this.clock = clock;
        this.businessZone = businessZone;
    }

    public List<OverdueInvoiceSummary> handle(
            FindOverdueInvoices query
    ) {
        LocalDate businessDate =
                LocalDate.now(clock.withZone(businessZone));

        List<Invoice> overdueCandidates =
                invoices.findByCustomer(query.customerId()).stream()
                        .filter(invoice -> invoice.isOverdueOn(businessDate))
                        .sorted(Comparator.comparing(Invoice::dueDate))
                        .toList();

        if (overdueCandidates.isEmpty()) {
            return List.of();
        }

        Set<InvoiceId> candidateIds = overdueCandidates.stream()
                .map(Invoice::id)
                .collect(Collectors.toSet());

        Set<InvoiceId> settledIds =
                payments.findSettledInvoiceIds(candidateIds);

        return overdueCandidates.stream()
                .filter(invoice -> !settledIds.contains(invoice.id()))
                .map(invoice -> new OverdueInvoiceSummary(
                        invoice.id(),
                        invoice.dueDate(),
                        ChronoUnit.DAYS.between(
                                invoice.dueDate(), businessDate
                        )
                ))
                .toList();
    }
}
~~~

Handler phối hợp hai port và dùng Clock để tính ngày nghiệp vụ. Nó lọc các hóa đơn quá hạn trước khi hỏi Payment Context, do đó chỉ gửi những ID thực sự cần kiểm tra. Nếu không có ứng viên, nó trả danh sách rỗng mà không gọi Payment port.

Nếu Payment port thất bại, exception được truyền lên để caller xử lý như lỗi phụ thuộc. Handler không được trả danh sách “chưa thanh toán” bằng cách giả định tất cả invoice đều chưa được trả tiền; làm vậy có thể đưa ra thông tin sai.

Đây là ví dụ minh họa một query use case. Một hệ thống thực tế có thể dùng read model đã đồng bộ trạng thái thanh toán thay vì gọi Payment Context mỗi lần. Lựa chọn đó phụ thuộc freshness requirement; logic use case và test double vẫn có thể được tổ chức tương tự.

## 5. Tạo Fake Repository trong bộ nhớ

Fake repository nên đủ đơn giản để người đọc hiểu ngay cách nó hoạt động. Không cần mô phỏng transaction engine hoặc tối ưu truy vấn như database thật.

~~~java
import java.util.ArrayList;
import java.util.List;

final class InMemoryInvoiceRepository implements InvoiceRepository {
    private final List<Invoice> data = new ArrayList<>();
    private int findCalls;

    void add(Invoice invoice) {
        data.add(invoice);
    }

    @Override
    public List<Invoice> findByCustomer(CustomerId customerId) {
        findCalls++;

        return data.stream()
                .filter(invoice -> invoice.customerId().equals(customerId))
                .toList();
    }

    int findCalls() {
        return findCalls;
    }
}
~~~

Fake này cho phép test thêm dữ liệu bằng add, gọi use case và kiểm tra kết quả. findCalls chỉ cần thiết nếu test có một yêu cầu hợp đồng cụ thể về việc không truy vấn khi không cần. Nếu không có yêu cầu đó, có thể bỏ bộ đếm để fake đơn giản hơn.

## 6. Tạo Fake Payment Port

Payment port cần trả về tập ID đã thanh toán. Fake có thể cấu hình trước kết quả và ghi lại tập ID nhận được:

~~~java
import java.util.HashSet;
import java.util.Set;

final class FakePaymentStatusPort implements PaymentStatusPort {
    private final Set<InvoiceId> settledIds = new HashSet<>();
    private Set<InvoiceId> lastRequestedIds = Set.of();
    private RuntimeException failure;

    void markSettled(InvoiceId invoiceId) {
        settledIds.add(invoiceId);
    }

    void failWith(RuntimeException exception) {
        failure = exception;
    }

    Set<InvoiceId> lastRequestedIds() {
        return lastRequestedIds;
    }

    @Override
    public Set<InvoiceId> findSettledInvoiceIds(
            Set<InvoiceId> invoiceIds
    ) {
        lastRequestedIds = Set.copyOf(invoiceIds);

        if (failure != null) {
            throw failure;
        }

        Set<InvoiceId> result = new HashSet<>(invoiceIds);
        result.retainAll(settledIds);
        return Set.copyOf(result);
    }
}
~~~

Fake mô phỏng đúng phần hợp đồng mà use case cần: nhận danh sách ID, trả về tập con đã quyết toán hoặc phát sinh lỗi đã cấu hình. Nó không mô phỏng HTTP status, JSON serialization hay retry của client. Những chi tiết đó thuộc adapter integration test.

## 7. Dùng Clock cố định để test thời gian

Test thời gian không nên phụ thuộc ngày thật lúc chạy. Không dùng Thread.sleep để đợi qua ngày hoặc sửa system clock của máy.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;

Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-18T00:30:00Z"),
        ZoneId.of("UTC")
);

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
~~~

Instant trên tương ứng 07:30 ngày 18/11/2026 tại TP. Hồ Chí Minh, trong khi ngày UTC vẫn là 18/11 ở thời điểm này. Để thể hiện khác biệt ngày, hãy chọn một Instant gần ranh giới UTC:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-17T18:00:00Z"),
        ZoneId.of("UTC")
);

// Tại Asia/Ho_Chi_Minh, thời điểm này là 2026-11-18 01:00.
~~~

Test có thể khẳng định một hóa đơn đến hạn ngày 17/11 đã quá hạn theo ngày nghiệp vụ 18/11, dù ngày UTC của cùng Instant vẫn là 17/11. Điều này giúp phát hiện lỗi dùng LocalDate.now() theo múi giờ mặc định của máy.

## 8. Viết test cho use case

Ví dụ dùng JUnit 5. Mỗi test tạo fake mới để trạng thái không rò rỉ sang test khác.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class FindOverdueInvoicesHandlerTest {
    private static final ZoneId BUSINESS_ZONE =
            ZoneId.of("Asia/Ho_Chi_Minh");

    private static final Clock FIXED_CLOCK = Clock.fixed(
            Instant.parse("2026-11-17T18:00:00Z"),
            ZoneId.of("UTC")
    );

    private CustomerId customerId;
    private InMemoryInvoiceRepository invoices;
    private FakePaymentStatusPort payments;
    private FindOverdueInvoicesHandler handler;

    @BeforeEach
    void setUp() {
        customerId = new CustomerId(UUID.randomUUID());
        invoices = new InMemoryInvoiceRepository();
        payments = new FakePaymentStatusPort();

        handler = new FindOverdueInvoicesHandler(
                invoices,
                payments,
                FIXED_CLOCK,
                BUSINESS_ZONE
        );
    }

    @Test
    void returnsOnlyOverdueInvoicesThatAreNotSettled() {
        Invoice overdueUnpaid = invoice("2026-11-15");
        Invoice overduePaid = invoice("2026-11-10");
        Invoice dueToday = invoice("2026-11-18");
        Invoice dueLater = invoice("2026-11-20");

        invoices.add(overdueUnpaid);
        invoices.add(overduePaid);
        invoices.add(dueToday);
        invoices.add(dueLater);

        payments.markSettled(overduePaid.id());

        List<OverdueInvoiceSummary> result =
                handler.handle(new FindOverdueInvoices(customerId));

        assertEquals(1, result.size());
        assertEquals(overdueUnpaid.id(), result.get(0).invoiceId());
        assertEquals(LocalDate.parse("2026-11-15"), result.get(0).dueDate());
        assertEquals(3, result.get(0).daysOverdue());

        assertEquals(
                Set.of(overdueUnpaid.id(), overduePaid.id()),
                payments.lastRequestedIds()
        );
    }

    @Test
    void usesBusinessZoneRatherThanUtcDate() {
        Invoice dueYesterdayInBusinessZone = invoice("2026-11-17");
        invoices.add(dueYesterdayInBusinessZone);

        List<OverdueInvoiceSummary> result =
                handler.handle(new FindOverdueInvoices(customerId));

        assertEquals(1, result.size());
        assertEquals(1, result.get(0).daysOverdue());
    }

    @Test
    void doesNotCallPaymentPortWhenThereAreNoOverdueCandidates() {
        invoices.add(invoice("2026-11-18"));
        invoices.add(invoice("2026-11-20"));

        List<OverdueInvoiceSummary> result =
                handler.handle(new FindOverdueInvoices(customerId));

        assertTrue(result.isEmpty());
        assertTrue(payments.lastRequestedIds().isEmpty());
    }

    @Test
    void returnsOverdueInvoicesInDueDateOrder() {
        Invoice later = invoice("2026-11-16");
        Invoice earlier = invoice("2026-11-12");

        invoices.add(later);
        invoices.add(earlier);

        List<OverdueInvoiceSummary> result =
                handler.handle(new FindOverdueInvoices(customerId));

        assertEquals(
                List.of(earlier.id(), later.id()),
                result.stream()
                        .map(OverdueInvoiceSummary::invoiceId)
                        .toList()
        );
    }

    @Test
    void propagatesPaymentStatusFailureInsteadOfAssumingUnpaid() {
        invoices.add(invoice("2026-11-15"));
        payments.failWith(new PaymentStatusUnavailable());

        assertThrows(
                PaymentStatusUnavailable.class,
                () -> handler.handle(new FindOverdueInvoices(customerId))
        );
    }

    private Invoice invoice(String dueDate) {
        return new Invoice(
                new InvoiceId(UUID.randomUUID()),
                customerId,
                LocalDate.parse(dueDate),
                InvoiceStatus.OPEN
        );
    }
}
~~~

Exception dùng trong test:

~~~java
public final class PaymentStatusUnavailable extends RuntimeException {
    public PaymentStatusUnavailable() {
        super("Payment status is temporarily unavailable");
    }
}
~~~

Test đầu tiên xác nhận cả kết quả lẫn dữ liệu gửi qua Payment port. Nó chứng minh hóa đơn đến hạn hôm nay và hóa đơn tương lai không được coi là quá hạn; hóa đơn đã thanh toán bị loại dù bản ghi Invoice vẫn ở trạng thái OPEN do dữ liệu giữa context có thể cập nhật trễ.

Test thứ hai xác nhận ngày nghiệp vụ được tính theo ZoneId được cấu hình. Test thứ ba kiểm tra tối ưu điều phối: không cần gọi Payment khi không có ứng viên. Test cuối xác nhận lỗi từ context thanh toán không bị biến thành kết quả sai.

## 9. Kiểm tra kết quả trước, tương tác sau

Một test thường tốt hơn khi diễn đạt theo Given–When–Then:

- **Given:** các hóa đơn ban đầu, trạng thái thanh toán giả lập và thời điểm cố định.
- **When:** gọi use case với customer ID.
- **Then:** nhận danh sách đúng, theo thứ tự đúng và không chứa hóa đơn đã thanh toán.

Có thể kiểm tra tương tác với port khi nó là một phần hợp đồng. Ví dụ PaymentStatusPort chỉ nên nhận các invoice ID đã quá hạn; không cần kiểm tra use case gọi một private helper bao nhiêu lần.

Một số câu hỏi để đánh giá assertion:

- Nếu đổi tên một method nội bộ nhưng kết quả và hành vi công khai không đổi, test có còn pass không?
- Assertion đang kiểm tra yêu cầu nghiệp vụ hay đang khóa chặt cấu trúc code?
- Có thể quan sát trạng thái qua fake repository thay vì verify từng lệnh mock không?
- Việc gọi port có side effect hoặc chi phí quan trọng cần được bảo vệ không?

Test càng phụ thuộc vào chi tiết nội bộ, refactor càng dễ tạo ra lỗi giả.

## 10. Thay thế từng loại cổng hạ tầng

Không phải mọi port đều cần cùng loại test double.

| Port | Test double thường phù hợp | Điều cần xác minh |
|---|---|---|
| Repository | Fake trong bộ nhớ | Dữ liệu được truy xuất/lưu theo hợp đồng |
| External query API | Stub hoặc fake | Kết quả, lỗi và timeout được use case xử lý đúng |
| Command gateway | Spy/fake | Command gửi đúng dữ liệu và chỉ gửi ở nhánh hợp lệ |
| Clock | Clock.fixed | Boundary thời gian và ngày nghiệp vụ |
| ID generator | Generator xác định | ID không làm test ngẫu nhiên khó đọc |
| Event publisher | Recording fake | Event đúng loại, payload và correlation |
| Unit of Work | Fake hoặc transaction test | Điều phối use case; atomicity cần kiểm tra với adapter thật |
| File/object storage | Fake storage | Key, metadata và nội dung được yêu cầu đúng |
| Email/SMS sender | Recording fake | Recipient, template và nội dung yêu cầu |

### Repository fake

Fake repository phù hợp khi cần chuẩn bị dữ liệu và quan sát trạng thái sau use case. Với repository phức tạp có nhiều query, fake có thể nhanh chóng trở thành một database giả khó duy trì. Khi đó, hãy giữ fake ở mức tối thiểu cho hợp đồng use case và kiểm thử adapter thật riêng.

### Event publisher fake

Một recording fake có thể ghi event:

~~~java
import java.util.ArrayList;
import java.util.List;

final class RecordingEventPublisher implements EventPublisher {
    private final List<DomainEvent> published = new ArrayList<>();

    @Override
    public void publish(List<DomainEvent> events) {
        published.addAll(events);
    }

    List<DomainEvent> publishedEvents() {
        return List.copyOf(published);
    }
}
~~~

Test có thể kiểm tra event được phát sau hành vi thành công và không phát khi aggregate từ chối thao tác. Nếu production dùng Transactional Outbox, fake này chỉ kiểm tra use case tạo yêu cầu ghi event; nó không chứng minh outbox và aggregate commit nguyên tử. Cần integration test cho transaction đó.

### Unit of Work fake

Nếu use case phụ thuộc UnitOfWork, một fake đơn giản có thể thực thi callback ngay lập tức. Điều này kiểm tra điều phối nhưng không mô phỏng rollback thật:

~~~java
import java.util.function.Supplier;

final class DirectUnitOfWork implements UnitOfWork {
    @Override
    public <T> T execute(Supplier<T> work) {
        return work.get();
    }
}
~~~

Không dùng fake này để kết luận transaction production bảo đảm atomicity. Nó chỉ thay thế ranh giới để test logic use case.

## 11. Kiểm thử command use case và thay đổi Aggregate

Ví dụ trên là query use case. Với command use case, test thường cần kiểm tra cả trạng thái aggregate sau hành vi và các yêu cầu ghi ra port.

Giả sử CancelOrderHandler tải Order, gọi hành vi order.cancel(reason, actor, now), rồi lưu aggregate và ghi domain event qua OutboxPort.

Một test tốt có thể xác nhận:

- Đơn ở trạng thái cho phép hủy được chuyển sang CANCELLED.
- Lý do và actor được ghi đúng theo mô hình.
- Repository nhận aggregate đã thay đổi.
- Domain event OrderCancelled được đưa vào outbox.
- Đơn đã giao không bị hủy.
- Khi hành vi miền từ chối, không có yêu cầu lưu hoặc phát event.

Không nên test bằng cách gọi trực tiếp setter của Order để chuẩn bị trạng thái nếu setter đó không thuộc API miền. Hãy dùng factory hoặc hành vi công khai để tạo fixture hợp lệ.

Nếu command gọi một dịch vụ ngoài có side effect, cần làm rõ transaction boundary và idempotency. Fake có thể xác minh command được gửi đúng; integration/contract test phải xác minh adapter gửi request đúng giao thức và xử lý retry an toàn.

## 12. Test fixture và dữ liệu dễ đọc

Fixture tốt làm nổi bật điều kiện nghiệp vụ. Có thể dùng factory:

~~~java
final class InvoiceFixtures {
    static Invoice openInvoice(
            CustomerId customerId,
            LocalDate dueDate
    ) {
        return new Invoice(
                new InvoiceId(UUID.randomUUID()),
                customerId,
                dueDate,
                InvoiceStatus.OPEN
        );
    }
}
~~~

Hoặc builder khi đối tượng có nhiều thuộc tính:

~~~java
Invoice invoice = anInvoice()
        .forCustomer(customerId)
        .dueOn(LocalDate.parse("2026-11-15"))
        .withStatus(InvoiceStatus.OPEN)
        .build();
~~~

Không cần tạo một builder tổng quát cho mọi entity. Nếu factory khiến test khó hiểu hơn việc gọi constructor, hãy dùng constructor.

Dữ liệu nên thể hiện ý nghĩa: dueToday, overduePaid, overdueUnpaid dễ đọc hơn invoice1, invoice2. Dùng ID cố định trong test khi cần so sánh chính xác; dùng UUID ngẫu nhiên vẫn ổn nếu ID không ảnh hưởng kết quả và test không phụ thuộc thứ tự ngẫu nhiên.

## 13. Kiểm thử lỗi của port và hành vi fail-safe

Cổng hạ tầng có thể thất bại vì timeout, mất kết nối, từ chối quyền hoặc phản hồi không hợp lệ. Use case cần quyết định cách phản ứng dựa trên mức độ quan trọng của dữ liệu.

Một số lựa chọn:

- Truyền lỗi có ý nghĩa lên application boundary để API trả lỗi phù hợp.
- Trả trạng thái PENDING khi nghiệp vụ cho phép xử lý tiếp sau.
- Dùng dữ liệu cache nếu freshness budget còn hợp lệ.
- Từ chối quyết định nếu không thể xác nhận điều kiện bắt buộc.
- Chuyển sang manual review khi rủi ro cao.

Không nên mặc định mọi lỗi đều trả danh sách rỗng hoặc dùng giá trị mặc định. Ví dụ Payment Context không trả lời không có nghĩa invoice chưa thanh toán. Đây là khác biệt giữa “không có dữ liệu” và “không thể xác minh dữ liệu”.

Test nên có ít nhất:

- Kết quả thành công.
- Kết quả rỗng hoặc không tìm thấy.
- Dữ liệu biên.
- Port trả kết quả nghiệp vụ từ chối.
- Port không sẵn sàng hoặc timeout.
- Dữ liệu trả về không hợp lệ theo hợp đồng.
- Retry hoặc xử lý lặp nếu use case có chính sách đó.

Không cần viết mọi tổ hợp có thể có. Ưu tiên các nhánh ảnh hưởng đến quyết định và dữ liệu.

## 14. Contract test cho adapter và fake

Fake được viết bởi nhóm phát triển có thể vô tình không giống adapter production. Ví dụ fake repository trả về mọi bản ghi đúng như mong đợi nhưng SQL adapter lọc sai trạng thái hoặc xử lý null khác.

Khi port có semantics đáng kể, có thể dùng một contract test suite chạy trên nhiều implementation:

~~~text
InvoiceRepositoryContract
    |
    +-- InMemoryInvoiceRepository
    |
    +-- JpaInvoiceRepository
~~~

Các test hợp đồng có thể xác nhận:

- Tìm theo customer không trả bản ghi của customer khác.
- Kết quả tuân theo quy tắc status.
- Thứ tự và pagination nhất quán nếu là một phần hợp đồng.
- Save rồi load lại giữ được các giá trị miền.
- Xử lý ID không tồn tại đúng quy định.

Fake có thể chạy suite nhanh trong unit test; JPA adapter chạy cùng suite trên database kiểm thử. Không phải port nào cũng cần contract suite, nhưng nó hữu ích khi nhiều adapter phải tuân thủ một hợp đồng chung.

## 15. Phần nào vẫn cần Integration Test?

Thay thế port trong use case test không chứng minh adapter thật hoạt động đúng. Cần các test riêng:

| Lớp kiểm thử | Thành phần thật | Mục tiêu |
|---|---|---|
| Domain unit test | Entity/Value Object thật | Invariant và hành vi miền |
| Use case test | Handler thật, test double cho port | Điều phối và kết quả use case |
| Adapter integration test | Repository/HTTP/broker adapter thật cùng môi trường test | SQL, mapping, serialization, protocol |
| Contract test | Provider/consumer contract hoặc port adapter | Tương thích schema và semantics |
| End-to-end test | Một luồng hệ thống thật hoặc gần thật | Xác nhận các thành phần phối hợp |

Ví dụ, use case test không thể chứng minh:

- JPA mapping lưu đúng enum và Value Object.
- Database transaction rollback khi outbox insert thất bại.
- SQL query dùng đúng index hoặc xử lý null chính xác.
- HTTP adapter gửi đúng header, timeout và deserialize lỗi.
- Broker giữ đúng partition key hoặc consumer ack message đúng thời điểm.
- Schema event tương thích với consumer đang chạy.

Các nội dung đó cần integration hoặc contract test có môi trường phù hợp. Không cần biến mọi test thành end-to-end; hãy chọn lớp test theo rủi ro cần xác minh.

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách điều chỉnh |
|---|---|---|
| Dùng database thật cho mọi use case test | Test chậm và phụ thuộc môi trường | Fake repository cho logic điều phối; integration test cho adapter |
| Mock mọi method của mọi dependency | Test khóa chặt implementation và khó đọc | Ưu tiên fake/stub, mock khi tương tác là hợp đồng |
| Fake mô phỏng cả database engine | Fake phức tạp và khác hành vi production | Chỉ mô phỏng phần semantics mà use case cần |
| Dùng Clock.systemDefaultZone trong test | Kết quả phụ thuộc máy và ngày chạy | Dùng Clock.fixed và ZoneId tường minh |
| Dùng sleep để kiểm tra thời gian | Test chậm, không ổn định | Điều khiển Clock |
| Verify mọi lời gọi private/helper | Refactor tạo lỗi test giả | Assert kết quả và side effect có ý nghĩa |
| Coi fake pass là adapter production đúng | SQL, mapping hoặc protocol vẫn có thể lỗi | Integration/contract test adapter |
| Bỏ qua lỗi của port | Use case có thể giả định dữ liệu chưa xác minh | Test timeout, unavailable và fail-safe |
| Test chỉ happy path | Không thấy lỗi ở boundary và trạng thái bất hợp lệ | Bao phủ nhánh quan trọng và biên |
| Dùng fixture không hợp lệ | Test không phản ánh trạng thái miền thật | Tạo dữ liệu qua factory/hành vi hợp lệ |
| Fake có state dùng chung giữa test | Test phụ thuộc thứ tự chạy | Tạo fake mới cho mỗi test |
| Kiểm tra transaction bằng DirectUnitOfWork | Nhầm điều phối với atomicity thật | Test transaction trên adapter thật |

## 17. Quy trình viết use case test

1. **Đọc hợp đồng use case:** xác định input, output, lỗi và side effect có ý nghĩa.
2. **Liệt kê port được sử dụng:** repository, gateway, clock, publisher, unit of work.
3. **Chọn test double tối thiểu:** fake cho state, stub cho kết quả, spy cho output cần quan sát.
4. **Tạo fixture hợp lệ:** dùng factory hoặc builder có tên theo ngữ nghĩa.
5. **Cố định thời gian và ID khi cần:** tránh phụ thuộc môi trường.
6. **Viết Given–When–Then:** mỗi test tập trung vào một quyết định hoặc một nhánh.
7. **Kiểm tra kết quả và trạng thái:** xác nhận dữ liệu trả về, aggregate được lưu hoặc event được yêu cầu.
8. **Kiểm tra lỗi và boundary:** không tìm thấy, từ chối, timeout, stale data hoặc dữ liệu không hợp lệ.
9. **Rà soát assertion:** loại bỏ verify chi tiết nội bộ không thuộc hợp đồng.
10. **Bổ sung adapter test:** xác minh SQL, mapping, protocol và transaction bằng implementation thật.

## 18. Checklist rà soát

- [ ] Use case phụ thuộc vào port có ý nghĩa, không phụ thuộc framework hạ tầng.
- [ ] Port được đặt ở phía application/domain cần khả năng đó.
- [ ] Test double chỉ mô phỏng phần hợp đồng mà use case cần.
- [ ] Fake repository có trạng thái riêng cho từng test.
- [ ] Stub/fake external gateway có thể cấu hình cả kết quả và lỗi.
- [ ] Clock được cố định; ZoneId nghiệp vụ được chỉ định rõ.
- [ ] Test có happy path, empty/not-found, boundary và lỗi quan trọng.
- [ ] Assertion tập trung vào kết quả và side effect có ý nghĩa.
- [ ] Không verify private method hoặc thứ tự gọi không phải hợp đồng.
- [ ] Aggregate được chuẩn bị qua factory/hành vi hợp lệ.
- [ ] Event hoặc command được ghi nhận đúng khi use case thành công.
- [ ] Không phát side effect khi domain từ chối thao tác.
- [ ] Lỗi port không bị diễn giải thành dữ liệu hợp lệ mặc định.
- [ ] Fake không bị dùng để kết luận SQL, mapping, protocol hoặc atomicity thật.
- [ ] Adapter có integration/contract test phù hợp với rủi ro.
- [ ] Transactional Outbox và rollback được kiểm thử với hạ tầng thật khi cần.

## Kết luận

Kiểm thử ca sử dụng với các cổng hạ tầng được thay thế giúp xác minh logic điều phối của application layer nhanh và ổn định. Use case phụ thuộc vào port có ý nghĩa; test cung cấp fake repository, stub gateway, recording spy và Clock cố định để điều khiển đầu vào, thời gian và kết quả bên ngoài. Test nên tập trung vào quyết định, trạng thái và side effect thuộc hợp đồng. Fake không thay thế integration test: SQL, ORM mapping, HTTP, broker, transaction và outbox vẫn cần được kiểm tra với adapter thật. Khi phân chia rõ hai trách nhiệm, test use case vừa dễ đọc, vừa hỗ trợ refactor mà vẫn giữ được bằng chứng cho các ranh giới hạ tầng.

