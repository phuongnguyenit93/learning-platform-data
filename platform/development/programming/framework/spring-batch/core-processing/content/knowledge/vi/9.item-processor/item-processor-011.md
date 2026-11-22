# Kiểm thử processor với item hợp lệ và không hợp lệ

Trong Spring Batch, `ItemProcessor` nhận một item từ `ItemReader`, thực hiện kiểm tra hoặc biến đổi dữ liệu rồi trả về item cho `ItemWriter`. Khi xây dựng processor, cần xác định rõ cách xử lý ba trường hợp: item hợp lệ, item cần loại khỏi luồng và item không hợp lệ đến mức phải báo lỗi.

Kiểm thử processor nên xác nhận được cả kết quả trả về lẫn hành vi khi dữ liệu sai. Unit test giúp kiểm tra nhanh logic xử lý của từng item; kiểm thử Step hoặc Job giúp xác nhận Spring Batch áp dụng đúng transaction, filter, skip và trạng thái thực thi.

## 1. Xác định hành vi của processor

`ItemProcessor<I, O>` nhận một đối tượng kiểu `I` và trả về một đối tượng kiểu `O`. Processor có thể giữ nguyên kiểu dữ liệu hoặc chuyển sang kiểu khác.

Có ba kết quả quan trọng:

| Tình huống | Hành vi của processor | Ý nghĩa trong Spring Batch |
|---|---|---|
| Item hợp lệ | Trả về đối tượng đã kiểm tra hoặc biến đổi | Item được chuyển đến Writer. |
| Item cần lọc | Trả về `null` | Item bị filter và không được chuyển đến Writer. |
| Item không hợp lệ | Ném exception | Step có thể thất bại, retry hoặc skip tùy cấu hình fault tolerance. |

Không nên dùng `null` và exception thay thế cho nhau một cách tùy tiện. Filter thường dành cho bản ghi hợp lệ về mặt cấu trúc nhưng không thuộc tập dữ liệu cần xử lý, ví dụ đơn hàng đã bị hủy. Exception phù hợp khi dữ liệu sai hoặc không thể xử lý, ví dụ thiếu mã khách hàng bắt buộc hoặc số tiền âm.

## 2. Ví dụ processor cần kiểm tra

Giả sử ứng dụng nhập đơn hàng. Một đơn hàng hợp lệ phải có mã khách hàng và số tiền lớn hơn 0. Đơn hàng có trạng thái `CANCELLED` được loại khỏi luồng; dữ liệu vi phạm quy tắc bắt buộc sẽ làm processor ném `InvalidOrderException`.

```java
import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;

public class OrderProcessor
        implements ItemProcessor<Order, ProcessedOrder> {

    @Override
    public ProcessedOrder process(Order order) {
        if ("CANCELLED".equals(order.status())) {
            return null;
        }

        if (order.customerId() == null || order.customerId().isBlank()) {
            throw new InvalidOrderException("Customer ID is required");
        }

        if (order.amount() == null
                || order.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new InvalidOrderException("Amount must be greater than zero");
        }

        return new ProcessedOrder(
                order.id(),
                order.customerId(),
                order.amount());
    }
}
```

Trong ví dụ, `Order` và `ProcessedOrder` là các kiểu dữ liệu domain của ứng dụng; có thể định nghĩa chúng bằng Java record hoặc class thông thường. `InvalidOrderException` là exception nghiệp vụ riêng, thường kế thừa `RuntimeException`:

```java
public class InvalidOrderException extends RuntimeException {
    public InvalidOrderException(String message) {
        super(message);
    }
}
```

Processor không thay đổi đối tượng đầu vào mà tạo `ProcessedOrder` mới sau khi dữ liệu vượt qua các điều kiện. Cách viết này giúp kiểm thử kết quả rõ ràng và giảm tác dụng phụ khi Spring Batch retry hoặc xử lý lại item.

## 3. Unit test cho item hợp lệ

Unit test có thể gọi trực tiếp `process()` mà không cần khởi tạo Spring context, JobRepository hoặc JobLauncher. Mục tiêu là xác nhận item hợp lệ được chuyển đổi đúng.

Ví dụ dùng JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderProcessorTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void convertsValidOrder() throws Exception {
        Order input = new Order(
                "ORD-100",
                "CUS-10",
                new BigDecimal("125.50"),
                "NEW");

        ProcessedOrder result = processor.process(input);

        assertNotNull(result);
        assertEquals("ORD-100", result.id());
        assertEquals("CUS-10", result.customerId());
        assertEquals(new BigDecimal("125.50"), result.amount());
    }
}
```

Test này kiểm tra các thuộc tính đầu ra quan trọng thay vì chỉ xác nhận kết quả khác `null`. Nếu processor có quy tắc tính toán hoặc chuẩn hóa dữ liệu, nên kiểm tra cả giá trị sau biến đổi và các trường được giữ nguyên.

## 4. Unit test cho item không hợp lệ

Với item vi phạm quy tắc nghiệp vụ, kiểm thử cần xác nhận đúng loại exception và thông tin lỗi. Ví dụ, mã khách hàng bị thiếu:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderProcessorInvalidItemTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void rejectsOrderWithoutCustomerId() {
        Order input = new Order(
                "ORD-101",
                " ",
                new BigDecimal("50.00"),
                "NEW");

        InvalidOrderException exception = assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));

        assertEquals("Customer ID is required", exception.getMessage());
    }

    @Test
    void rejectsZeroOrNegativeAmount() {
        Order input = new Order(
                "ORD-102",
                "CUS-10",
                BigDecimal.ZERO,
                "NEW");

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
```

Nên kiểm tra các trường hợp biên như `null`, chuỗi rỗng, chuỗi chỉ có khoảng trắng, số 0, số âm và giá trị lớn bất thường nếu chúng có ý nghĩa với nghiệp vụ. Mỗi test nên tập trung vào một điều kiện để khi thất bại có thể xác định quy tắc nào đang sai.

## 5. Kiểm thử item được filter

Nếu processor trả về `null`, Spring Batch xem item đó là bị filter. Item không được gửi đến Writer, nhưng đây không phải là skip do exception.

```java
import static org.junit.jupiter.api.Assertions.assertNull;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class OrderProcessorFilterTest {

    private final OrderProcessor processor = new OrderProcessor();

    @Test
    void filtersCancelledOrder() throws Exception {
        Order cancelled = new Order(
                "ORD-103",
                "CUS-10",
                new BigDecimal("75.00"),
                "CANCELLED");

        assertNull(processor.process(cancelled));
    }
}
```

Phân biệt filter và skip rất quan trọng khi đọc số liệu vận hành:

- `filterCount` tăng khi processor trả về `null`.
- `processSkipCount` tăng khi processor ném exception và exception đó được cấu hình cho phép skip.

Nếu một bản ghi không hợp lệ phải được ghi vào bảng lỗi hoặc gửi sang quy trình sửa dữ liệu, không nên chỉ trả về `null` vì như vậy bản ghi sẽ bị loại khỏi luồng mà không tự động được lưu ở đâu. Có thể dùng listener, cơ chế skip hoặc một nhánh xử lý riêng tùy yêu cầu nghiệp vụ.

## 6. Dùng parameterized test cho nhiều trường hợp dữ liệu

Khi nhiều giá trị đầu vào phải tuân theo cùng một quy tắc, JUnit 5 hỗ trợ `@ParameterizedTest`. Cách này giảm lặp lại test nhưng vẫn thể hiện rõ các trường hợp biên.

Ví dụ kiểm tra nhiều giá trị số tiền không hợp lệ:

```java
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.math.BigDecimal;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class OrderProcessorAmountTest {

    private final OrderProcessor processor = new OrderProcessor();

    @ParameterizedTest
    @ValueSource(strings = {"0", "-0.01", "-100"})
    void rejectsNonPositiveAmounts(String amount) {
        Order input = new Order(
                "ORD-104",
                "CUS-10",
                new BigDecimal(amount),
                "NEW");

        assertThrows(
                InvalidOrderException.class,
                () -> processor.process(input));
    }
}
```

Có thể dùng `@CsvSource` hoặc `@MethodSource` khi một test cần nhiều trường dữ liệu cùng lúc, chẳng hạn mã khách hàng, số tiền, trạng thái và kết quả mong đợi. Nên đặt tên test thể hiện quy tắc đang được kiểm tra để báo cáo test dễ đọc.

## 7. Mock dependency khi processor gọi service bên ngoài

Processor thực tế có thể phụ thuộc vào service tra cứu khách hàng, quy đổi tiền tệ hoặc kiểm tra hạn mức. Unit test nên cô lập processor bằng Mockito để chủ động kiểm soát kết quả của dependency.

Ví dụ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CustomerEnrichmentProcessorTest {

    @Mock
    private CustomerService customerService;

    @InjectMocks
    private CustomerEnrichmentProcessor processor;

    @Test
    void enrichesOrderForKnownCustomer() throws Exception {
        Order input = new Order(
                "ORD-105", "CUS-10", new BigDecimal("80.00"), "NEW");
        when(customerService.findName("CUS-10"))
                .thenReturn("Lan Nguyen");

        EnrichedOrder result = processor.process(input);

        assertEquals("Lan Nguyen", result.customerName());
    }
}
```

Mock giúp kiểm tra processor phản ứng thế nào khi service trả về dữ liệu, không tìm thấy khách hàng hoặc ném exception. Không nên mock chính logic đang cần kiểm thử; chỉ mock ranh giới phụ thuộc bên ngoài để test tập trung vào hành vi của processor.

## 8. Kiểm thử tích hợp Step với Spring Batch Test

Unit test xác nhận logic của processor, nhưng chưa chứng minh Step áp dụng đúng skip, filter, transaction và ghi dữ liệu. Khi cần kiểm tra sự phối hợp giữa các thành phần, có thể dùng module `spring-batch-test`.

Với Spring Boot, `@SpringBatchTest` cung cấp các tiện ích như `JobLauncherTestUtils`. `launchStep` cho phép chạy một Step cụ thể với JobParameters kiểm thử.

Ví dụ dưới đây giả định ứng dụng có một Job được cấu hình cho test, Step tên `processOrdersStep`, reader đọc fixture có một đơn hàng không hợp lệ và Step cho phép skip `InvalidOrderException`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@SpringBatchTest
class ProcessOrdersStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void skipsInvalidOrderAndCompletesStep() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRun", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchStep(
                "processOrdersStep", parameters);

        StepExecution stepExecution = execution.getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(1, stepExecution.getProcessSkipCount());
    }
}
```

Để test chạy được, cần có dependency `spring-batch-test`, cấu hình test context chứa Job/Step và fixture đầu vào xác định. Nếu ứng dụng có nhiều Job, hãy cấu hình `JobLauncherTestUtils` trỏ đúng Job cần kiểm thử. Tham số `testRun` duy nhất giúp các lần test không vô tình dùng lại JobInstance đã hoàn tất.

Trong một Step không cho phép skip, có thể kiểm tra JobExecution hoặc StepExecution kết thúc `FAILED` khi processor ném exception. Với Step cho phép skip, hãy xác nhận `processSkipCount`, `filterCount`, `writeCount` và dữ liệu writer nhận được phù hợp với chính sách.

## 9. Kiểm thử sự khác nhau giữa filter và skip

Một test tích hợp hữu ích là chuẩn bị tập input có ba loại item:

1. Một item hợp lệ được ghi ra.
2. Một item bị filter vì không thuộc phạm vi xử lý.
3. Một item không hợp lệ, processor ném exception và Step được cấu hình skip loại exception đó.

Giả sử mỗi loại xuất hiện một lần, kết quả mong đợi có thể được biểu diễn như sau:

| Chỉ số | Giá trị mong đợi | Giải thích |
|---|---:|---|
| `readCount` | 3 | Reader đã đọc ba item. |
| `filterCount` | 1 | Một item bị processor loại bằng cách trả về `null`. |
| `processSkipCount` | 1 | Một item gây exception và được skip. |
| `writeCount` | 1 | Chỉ item hợp lệ được chuyển tới Writer. |

Các bộ đếm thực tế phụ thuộc vào cấu hình Step, retry, transaction và thời điểm lỗi. Khi test, nên xác nhận thêm nội dung mà Writer đã ghi thay vì chỉ dựa vào tổng số lượng. Nếu dùng database test, có thể truy vấn bảng đích sau khi Step hoàn tất để xác nhận bản ghi đúng và không có bản ghi bị filter/skip.

## 10. Kiểm thử khi processor dùng StepScope hoặc JobParameters

Một processor có thể được khai báo `@StepScope` để nhận JobParameters hoặc giá trị trong `ExecutionContext`. Khi gọi trực tiếp processor trong unit test, các giá trị scope chưa được khởi tạo nếu không có Step context.

Ví dụ processor lấy ngày nghiệp vụ từ JobParameters:

```java
import java.time.LocalDate;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
@StepScope
public class BusinessDateProcessor
        implements ItemProcessor<Order, DatedOrder> {

    private final LocalDate businessDate;

    public BusinessDateProcessor(
            @Value("#{jobParameters['businessDate']}") String businessDate) {
        this.businessDate = LocalDate.parse(businessDate);
    }

    @Override
    public DatedOrder process(Order order) {
        return new DatedOrder(order.id(), businessDate);
    }
}
```

Với processor phụ thuộc StepScope, có thể dùng `StepScopeTestUtils` và một `StepExecution` giả lập để mở scope trong test:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@SpringBatchTest
class BusinessDateProcessorTest {

    @Autowired
    private BusinessDateProcessor processor;

    @Test
    void readsBusinessDateFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15")
                .toJobParameters();
        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution(parameters);

        DatedOrder result = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> processor.process(new Order("ORD-106", "CUS-10",
                        new BigDecimal("40.00"), "NEW")));

        assertEquals(LocalDate.of(2026, 11, 15), result.businessDate());
    }
}
```

Trong ví dụ, `DatedOrder` là kiểu output có trường `businessDate`; `Order` là domain input đã dùng ở các phần trên. Test context cần đăng ký bean `BusinessDateProcessor` và bật Spring Batch test support. Nếu processor không phụ thuộc scope, unit test trực tiếp đơn giản hơn và không cần Spring context.

## 11. Những trường hợp cần kiểm thử thêm

Ngoài item hợp lệ và không hợp lệ cơ bản, processor thường cần được kiểm thử với các tình huống sau:

- **Giá trị biên:** số tiền bằng 0, giá trị âm, ngày ở đầu/cuối kỳ, chuỗi có độ dài tối đa.
- **Dữ liệu thiếu:** trường bắt buộc `null`, rỗng hoặc chỉ chứa khoảng trắng.
- **Dữ liệu sai định dạng:** ngày không hợp lệ, số không parse được, mã trạng thái không được hỗ trợ.
- **Dữ liệu trùng:** hai item có cùng khóa nghiệp vụ và cách processor xử lý từng item.
- **Dependency lỗi:** service timeout, trả về `null` hoặc ném exception.
- **Tính lặp lại:** cùng một input được xử lý nhiều lần có tạo kết quả nhất quán không, đặc biệt khi Step có retry.
- **Không làm thay đổi input ngoài ý muốn:** nếu processor tạo output mới, xác nhận đối tượng đầu vào vẫn giữ nguyên khi đó là yêu cầu thiết kế.

## 12. Lỗi kiểm thử thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| Chỉ assert kết quả không `null` | Không phát hiện sai trường dữ liệu hoặc sai phép biến đổi. | Kiểm tra các trường quan trọng của output. |
| Dùng `assertNull` cho mọi item lỗi | Nhầm item cần filter với item phải báo lỗi. | Xác định rõ quy tắc: filter trả `null`, lỗi nghiệp vụ ném exception. |
| Unit test cần khởi động toàn bộ Spring context | Processor bị phụ thuộc quá nhiều vào container hoặc scope. | Tách logic thuần để kiểm thử trực tiếp; chỉ dùng Spring context cho integration test. |
| Test Step nhưng không kiểm tra dữ liệu ghi | Step có thể COMPLETED nhưng output sai. | Kiểm tra writer output hoặc truy vấn dữ liệu đích. |
| Không kiểm tra skip/filter counts | Không biết item bị loại theo cơ chế nào. | Assert `filterCount`, `processSkipCount` và `writeCount`. |
| Test phụ thuộc JobInstance cũ | Các test dùng lại identifying JobParameters và bị từ chối launch. | Dùng tham số test duy nhất hoặc làm sạch metadata theo cấu hình test. |
| Mock toàn bộ processor | Test không thực thi logic cần kiểm tra. | Chỉ mock dependency bên ngoài, giữ processor thật trong unit test. |

## Kết luận

Kiểm thử `ItemProcessor` cần xác nhận rõ ba hành vi: item hợp lệ được biến đổi đúng, item cần loại được trả về `null`, và item vi phạm quy tắc phải ném exception phù hợp. JUnit unit test giúp kiểm tra nhanh từng quy tắc và các giá trị biên; Mockito cô lập dependency bên ngoài. Kiểm thử Step hoặc Job bằng Spring Batch Test xác nhận cách framework xử lý filter, skip, transaction và dữ liệu ghi ra. Khi phân biệt đúng filter với skip và kiểm tra cả output lẫn metadata, bài test sẽ phản ánh sát hành vi batch trong môi trường thực tế.
