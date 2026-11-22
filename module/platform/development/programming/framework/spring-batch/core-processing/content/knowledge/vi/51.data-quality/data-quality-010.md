# Business rule trong processor — kiểm soát chất lượng dữ liệu với Spring Batch

## 1. Vì sao business rule nên được thiết kế rõ trong processor?

Một batch import đơn hàng thường gồm ba giai đoạn:

```text
Nguồn CSV / JDBC / API
        |
        v
  ItemReader<I>
  đọc và tạo input item
        |
        v
  ItemProcessor<I, O>
  chuẩn hóa + đánh giá business rules
        |
        +-- hợp lệ ----------------------> output item O
        |
        +-- không thuộc phạm vi --------> null (lọc có chủ đích)
        |
        +-- vi phạm cần xử lý ----------> exception hoặc kết quả REJECTED
        |
        v
  ItemWriter<O>
  ghi kết quả của một chunk
```

Ví dụ, một đơn hàng chỉ được ghi vào hệ thống nếu:

- Có mã đơn hàng bên ngoài (external order ID) hợp lệ.
- Trạng thái đơn hàng thuộc loại được xử lý.
- Số tiền lớn hơn 0, có định dạng và đơn vị tiền hợp lệ.
- Ngày nghiệp vụ khớp kỳ import.
- Tổng tiền không vượt ngưỡng được phê duyệt tự động.
- Những đơn phải duyệt thủ công được đưa vào luồng riêng, không biến mất âm thầm.

Các yêu cầu trên là **business rules**. Chúng biểu diễn chính sách nghiệp vụ, không chỉ kiểm tra dữ liệu có đúng kiểu Java hay không.

Trong Spring Batch, **`ItemProcessor<I, O>`** là nơi rất phù hợp để triển khai quy tắc áp dụng cho từng item vì nó đứng giữa reader và writer, có thể chuyển đổi input sang output, lọc item hoặc báo lỗi theo chính sách của step.

Tuy nhiên, đặt business rule trong processor **không có nghĩa mọi vấn đề đều nên được giải quyết bằng một if/else lớn**. Quyết định lọc, từ chối, ghi quarantine, abort cả job, truy vấn dữ liệu tham chiếu hay kiểm tra tính nhất quán liên bản ghi đều cần một hợp đồng rõ ràng.

Bài học thuộc nhóm **Data quality** trong **Spring Batch Core Processing**, dùng **Java 17+, Spring Batch 5.x, Spring Boot 3.x và JUnit 5** làm ngữ cảnh. Các chi tiết API nên được đối chiếu khi ứng dụng sử dụng phiên bản Spring Batch khác, đặc biệt Spring Batch 6.x.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt schema validation, business rule, transform, filter, reject và quarantine.
2. Dùng `ItemProcessor<I,O>` để đánh giá quy tắc theo từng item một cách có thể kiểm thử.
3. Chọn đúng kết quả `return item`, `return null`, `throw exception` hoặc trả về một decision object.
4. Kết hợp nhiều processor hoặc validator mà vẫn giữ được thứ tự và hợp đồng dữ liệu.
5. Kết nối rule violation với `skip`, `skipLimit`, `SkipListener` và hệ thống ghi lỗi.
6. Thiết kế rule ổn định qua retry/restart, không tạo side effect lặp, có version và audit.
7. Đo, kiểm thử và cải thiện chất lượng dữ liệu bằng các chỉ số phù hợp.

---

## 2. Business rule khác kiểm tra schema hoặc kiểm tra kỹ thuật thế nào?

Một input có thể parse thành Java object thành công nhưng vẫn không được phép ghi.

| Loại kiểm tra | Ví dụ | Tầng xử lý thường phù hợp |
| --- | --- | --- |
| Định dạng / parsing | Ngày `2026-13-55` không parse được thành `LocalDate` | Reader/tokenizer/field mapper |
| Validation thuộc tính | `externalOrderId` rỗng, độ dài mã vượt 50 | Bean Validation hoặc processor |
| Business rule từng item | Đơn có `amount <= 0`, tiền tệ không cho phép | Processor / domain rule service |
| Eligibility | Đơn `CANCELLED` không nằm trong phạm vi báo cáo | Processor filter hoặc upstream query |
| Rule liên item | Mỗi kỳ chỉ được có một order ID, tổng chi phí không vượt ngân sách | Unique constraint, staging/aggregation, writer hoặc bước đối soát |
| Constraint dữ liệu đích | Unique key, foreign key, check constraint | Database/writer là lớp bảo vệ cuối |
| Tính toàn vẹn toàn batch | Tất cả record phải đủ sequence, tổng tiền nguồn khớp output | Step tổng hợp/đối soát sau xử lý |
| Hạ tầng | Mất DB connection, HTTP timeout | Retry/recovery, không gắn nhãn lỗi nghiệp vụ |

**Một processor xử lý từng item không phải nguồn chân lý duy nhất cho tính đúng đắn toàn tập dữ liệu.** Ví dụ hai item cùng external order ID có thể được các thread khác nhau xử lý. Nếu chỉ dùng `HashSet` trong processor để phát hiện trùng, kết quả dễ sai khi partition, retry, restart hoặc chạy nhiều instance. Unique constraint hoặc một bước staging/dedup có kiểm soát mới phù hợp để bảo vệ tính duy nhất toàn cục.

### 2.1. Chất lượng dữ liệu có nhiều chiều

Trong ứng dụng batch, một rule thường nhằm bảo vệ một hoặc nhiều chiều chất lượng:

- **Completeness:** thiếu trường bắt buộc.
- **Validity:** giá trị không thỏa điều kiện nghiệp vụ.
- **Consistency:** trạng thái/giá trị mâu thuẫn nhau.
- **Uniqueness:** một business key chỉ được xuất hiện theo số lần cho phép.
- **Timeliness:** dữ liệu phải thuộc kỳ được phép xử lý.
- **Accuracy:** giá trị phải khớp nguồn hoặc công thức được phê duyệt.

Không nên đơn giản đồng nhất tất cả giá trị không mong muốn với “dữ liệu bẩn”: một đơn `CANCELLED` có thể là dữ liệu hoàn toàn hợp lệ nhưng **không thuộc phạm vi batch**.

### 2.2. Rule có thể là chính sách, không chỉ validation

Ví dụ:

```text
Đơn A: status = CANCELLED
  -> hợp lệ về mặt dữ liệu
  -> không được nhập vào bảng đơn đã hoàn tất
  -> FILTERED

Đơn B: amount = -500
  -> vi phạm điều kiện amount > 0
  -> REJECTED hoặc FAIL theo chính sách

Đơn C: amount = 900_000_000
  -> dữ liệu hợp lệ
  -> cần MANUAL_REVIEW theo ngưỡng phê duyệt

Đơn D: amount = 200_000
  -> hợp lệ và đủ điều kiện
  -> ACCEPTED
```

Nếu trả `null` cho cả A, B và C thì số liệu `filterCount` có thể tăng nhưng không còn cách phân biệt item bị bỏ qua hợp lệ với item bị từ chối hoặc cần phê duyệt. Thiết kế này mất khả năng audit.

---

## 3. Hợp đồng quan trọng của `ItemProcessor<I, O>`

Trong Spring Batch 5.x:

```java
@FunctionalInterface
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

Ba trường hợp chính:

| Giá trị `process` | Spring Batch hiểu thế nào? | Ý nghĩa cần định nghĩa ở ứng dụng |
| --- | --- | --- |
| Trả một object `O` | Item tiếp tục đến writer của chunk | ACCEPTED hoặc kết quả cần ghi |
| Trả `null` | Item được **filter**; không đưa vào chunk output | Chỉ dùng khi bỏ item là hành vi mong muốn |
| Ném exception | Step xử lý exception theo fault-tolerant policy hoặc thất bại | Validation/recoverable failure cần phân loại |

Điểm đáng chú ý:

- Trả `null` **không phải exception**, không dùng `skipLimit` và không biến `processSkipCount` tăng; đó là **filtering**.
- Exception ở processor có thể khiến step `FAILED`, hoặc được **skip** nếu `.faultTolerant().skip(...)` được cấu hình phù hợp.
- Nếu chọn skip, item bị bỏ đi trong phạm vi execution theo chính sách; không có nghĩa item đã được đưa vào một bảng lỗi bền vững.
- Việc process item có thể bị **gọi lại** khi transaction rollback/retry. Processor nên deterministic và không có side effect ngoài transaction.

### 3.1. Filter khác skip

```text
ItemProcessor returns null
    |
    v
filtered item
    |
    +-- tăng filterCount theo execution
    +-- không đi vào writer
    +-- không tính là process skip

ItemProcessor throws BusinessRuleViolationException
    |
    +-- cấu hình không cho skip:
    |       step FAILS
    |
    +-- cấu hình cho skip trong hạn mức:
            item bị SKIPPED
            processSkipCount tăng
            SkipListener có thể được gọi
```

Filter phù hợp với lựa chọn “không cần output”; skip phù hợp với “bản ghi bị lỗi có thể bỏ qua có kiểm soát”. Nếu nghiệp vụ bắt buộc có **hồ sơ từ chối** cho từng item, cần một chiến lược quarantine/reject bền vững thay vì chỉ dựa vào hai counter.

### 3.2. Xác định chính sách trước khi viết code

Một bảng quyết định giúp thống nhất với Product Owner, Data Steward và vận hành:

| Rule code | Điều kiện | Quyết định | Lý do |
| --- | --- | --- | --- |
| `ORDER_ID_REQUIRED` | ID rỗng | REJECT | Không thể định danh đơn |
| `STATUS_NOT_IN_SCOPE` | Status là CANCELLED | FILTER | Không thuộc tập đầu ra |
| `AMOUNT_NON_POSITIVE` | Amount null hoặc ≤ 0 | REJECT | Giá trị tiền không hợp lệ |
| `CURRENCY_UNSUPPORTED` | Currency không trong whitelist | REJECT | Không có nghiệp vụ xử lý |
| `AMOUNT_SCALE` | Amount nhiều hơn 2 chữ số thập phân có ý nghĩa | REJECT | Không làm tròn ngầm |
| `DATE_OUT_OF_SCOPE` | Ngày đơn khác business date của job | FILTER hoặc REJECT theo contract | Cần quy định rõ |
| `AMOUNT_REVIEW_REQUIRED` | Amount vượt ngưỡng tự động | MANUAL_REVIEW | Không được biến thành mất dữ liệu |
| `CUSTOMER_BLOCKED` | Khách hàng bị hạn chế | REJECT hoặc MANUAL_REVIEW | Phụ thuộc chính sách tuân thủ |

Bảng trên là **một ví dụ chính sách**, không phải quy tắc mặc định của Spring Batch. Ứng dụng thực phải thống nhất giới hạn và hậu quả của từng rule.

---

## 4. Thiết kế domain model và rule context

Hãy bắt đầu với kiểu dữ liệu rõ ràng thay vì truyền `Map<String,Object>` qua mọi tầng.

### 4.1. Model input và output bất biến

Java 17 hỗ trợ `record`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;

public record OrderRow(
    String externalOrderId,
    BigDecimal amount,
    String currency,
    String status,
    LocalDate businessDate
) {}

public record ApprovedOrder(
    String externalOrderId,
    BigDecimal amount,
    String currency,
    LocalDate businessDate
) {}
```

Input có thể chưa chuẩn hóa; output đại diện cho dữ liệu đã đạt hợp đồng của writer. Không nên sửa object input ngay trong processor nếu cùng object còn được retry, ghi log, dùng cho skip listener hoặc các delegate khác. Trả về một object mới giúp luồng dữ liệu dễ kiểm tra hơn.

### 4.2. Snapshot quy tắc cho một lần chạy

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Set;

public record OrderRuleContext(
    LocalDate businessDate,
    BigDecimal maxAutoApprovedAmount,
    Set<String> allowedCurrencies,
    String ruleVersion
) {
    public OrderRuleContext {
        allowedCurrencies = Set.copyOf(allowedCurrencies);
    }
}
```

Context chứa **giá trị của quy tắc được chọn cho lần chạy**, không phải một connection hay repository sống. Bằng cách chụp snapshot của cấu hình, cùng một item trong một execution sẽ được xử lý theo policy nhất quán hơn.

Nếu hệ thống cần restart sau deploy mà quy tắc đã đổi, `ruleVersion` là một phần quan trọng của hợp đồng. Cần quyết định từ trước **restart dùng rule snapshot cũ hay áp dụng rule mới**, vì đổi kết quả đánh giá giữa hai lần có thể làm dữ liệu không nhất quán.

---

## 5. Ví dụ processor đánh giá business rule

### 5.1. Exception có rule code ổn định

Thay vì ném `IllegalArgumentException("bad data")` cho mọi lỗi, dùng exception chứa một **mã rule ổn định**:

```java
public final class BusinessRuleViolationException
        extends RuntimeException {

    private final String ruleCode;
    private final String externalOrderId;

    public BusinessRuleViolationException(
            String ruleCode,
            String externalOrderId,
            String message) {

        super(message);
        this.ruleCode = ruleCode;
        this.externalOrderId = externalOrderId;
    }

    public String getRuleCode() {
        return ruleCode;
    }

    public String getExternalOrderId() {
        return externalOrderId;
    }
}
```

`ruleCode` là contract với dashboard, log, bảng reject và test. Không đưa dữ liệu nhạy cảm hoặc toàn bộ raw payload vào thông điệp exception.

### 5.2. Processor đầy đủ

Ví dụ này đưa đơn `CANCELLED` ra khỏi tập import, từ chối đơn vi phạm quy tắc và chuẩn hóa currency trước khi ghi.

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

import org.springframework.batch.item.ItemProcessor;

public final class OrderBusinessRuleProcessor
        implements ItemProcessor<OrderRow, ApprovedOrder> {

    private final OrderRuleContext rules;

    public OrderBusinessRuleProcessor(OrderRuleContext rules) {
        this.rules = rules;
    }

    @Override
    public ApprovedOrder process(OrderRow item) {

        if (item == null) {
            throw violation(
                "INPUT_NULL", null, "Input order is null");
        }

        String id = item.externalOrderId();
        if (id == null || id.isBlank()) {
            throw violation(
                "ORDER_ID_REQUIRED", id, "Order ID is required");
        }
        id = id.trim();

        String status = item.status() == null
            ? ""
            : item.status().trim().toUpperCase(Locale.ROOT);

        // Chỉ lọc trạng thái đã được business contract định nghĩa.
        if ("CANCELLED".equals(status)) {
            return null;
        }

        if (!"READY".equals(status)) {
            throw violation(
                "STATUS_UNSUPPORTED", id,
                "Status is not eligible for import");
        }

        if (item.amount() == null ||
                item.amount().signum() <= 0) {
            throw violation(
                "AMOUNT_NON_POSITIVE", id,
                "Order amount must be positive");
        }

        String currency = item.currency() == null
            ? ""
            : item.currency().trim().toUpperCase(Locale.ROOT);

        if (!rules.allowedCurrencies().contains(currency)) {
            throw violation(
                "CURRENCY_UNSUPPORTED", id,
                "Currency is not supported");
        }

        if (item.businessDate() == null ||
            !rules.businessDate().equals(item.businessDate())) {
            throw violation(
                "DATE_OUT_OF_SCOPE", id,
                "Business date does not match this job");
        }

        // Không làm tròn ngầm một giá trị tiền sai độ chính xác.
        BigDecimal amount;
        try {
            amount = item.amount().setScale(
                2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw violation(
                "AMOUNT_SCALE", id,
                "Amount has unsupported decimal precision");
        }

        if (amount.compareTo(
                rules.maxAutoApprovedAmount()) > 0) {
            throw violation(
                "AMOUNT_REVIEW_REQUIRED", id,
                "Order must be reviewed before import");
        }

        return new ApprovedOrder(
            id, amount, currency, item.businessDate());
    }

    private static BusinessRuleViolationException violation(
            String code,
            String id,
            String message) {
        return new BusinessRuleViolationException(
            code, id, message);
    }
}
```

Đây là ví dụ processor “**accepted / filtered / exception**”. Đơn cần duyệt thủ công đang được biểu diễn bằng exception; nếu nghiệp vụ cần ghi bản ghi manual-review bền vững, không thể chỉ skip rồi kết luận đã có hồ sơ. Mục 9 giới thiệu biến thể **decision object + routing writer** phù hợp hơn.

### 5.3. Vì sao kiểm tra rule theo thứ tự đó?

Thứ tự là một phần của contract:

1. Xác định ID để các lỗi phía sau có thể gắn với record.
2. Nhận diện status hợp lệ nằm ngoài phạm vi và filter có chủ đích.
3. Từ chối status không hỗ trợ.
4. Kiểm tra amount, currency, date.
5. Chuẩn hóa tiền với rule không cho làm tròn ngầm.
6. Áp dụng ngưỡng phê duyệt.
7. Tạo output mới.

Một item có thể vi phạm nhiều rule cùng lúc. Cách **fail fast** ở trên báo rule đầu tiên. Nếu cần báo tất cả lỗi của một record, nên dùng một kết quả validation chứa danh sách violations, thay vì ném ngay ở điều kiện đầu tiên. Cách chọn ảnh hưởng trực tiếp trải nghiệm sửa dữ liệu nguồn và số liệu rule violations.

### 5.4. Điều chỉnh thứ tự lọc và validate

Ví dụ `CANCELLED` được filter **trước** khi kiểm tra amount. Nghĩa là một đơn bị hủy với amount âm không xuất hiện trong thống kê `AMOUNT_NON_POSITIVE`. Điều này có thể đúng nếu canceled orders không thuộc tập cần kiểm toán amount; nhưng cũng có thể sai với một chương trình đánh giá chất lượng dữ liệu của **toàn bộ feed**.

Nếu yêu cầu báo mọi lỗi input, cần validate trước khi filter hoặc ghi luồng kiểm toán độc lập. Phải định nghĩa rõ đối tượng mà KPI data quality áp dụng: toàn bộ source hay chỉ các record đủ điều kiện nghiệp vụ.

---

## 6. Kiểm thử unit cho processor

Các business rules thuần Java nên được test trước khi dựng cả Spring context. Điều này giảm thời gian chạy và làm rõ nguyên nhân khi luật thay đổi.

### 6.1. Fixture

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Set;

final class OrderFixtures {

    static OrderRuleContext rules() {
        return new OrderRuleContext(
            LocalDate.of(2026, 11, 16),
            new BigDecimal("1000000.00"),
            Set.of("VND", "USD"),
            "rules-2026-11"
        );
    }

    static OrderRow valid() {
        return new OrderRow(
            "  ORDER-001  ",
            new BigDecimal("125.50"),
            " usd ",
            "READY",
            LocalDate.of(2026, 11, 16)
        );
    }
}
```

### 6.2. JUnit 5 với các nhánh quyết định

```java
import java.math.BigDecimal;
import java.time.LocalDate;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderBusinessRuleProcessorTest {

    private final OrderBusinessRuleProcessor processor =
        new OrderBusinessRuleProcessor(OrderFixtures.rules());

    @Test
    void normalizesAndApprovesValidOrder() {
        ApprovedOrder actual =
            processor.process(OrderFixtures.valid());

        assertNotNull(actual);
        assertEquals("ORDER-001", actual.externalOrderId());
        assertEquals("USD", actual.currency());
        assertEquals(
            new BigDecimal("125.50"),
            actual.amount());
    }

    @Test
    void filtersCancelledOrder() {
        OrderRow cancelled = new OrderRow(
            "ORDER-C",
            new BigDecimal("50.00"),
            "USD",
            "CANCELLED",
            LocalDate.of(2026, 11, 16));

        assertNull(processor.process(cancelled));
    }

    @Test
    void rejectsZeroAmountWithStableCode() {
        OrderRow invalid = new OrderRow(
            "ORDER-Z",
            BigDecimal.ZERO,
            "USD",
            "READY",
            LocalDate.of(2026, 11, 16));

        BusinessRuleViolationException exception =
            assertThrows(
                BusinessRuleViolationException.class,
                () -> processor.process(invalid));

        assertEquals(
            "AMOUNT_NON_POSITIVE",
            exception.getRuleCode());
    }

    @Test
    void requiresReviewAboveThreshold() {
        OrderRow large = new OrderRow(
            "ORDER-L",
            new BigDecimal("1000000.01"),
            "USD",
            "READY",
            LocalDate.of(2026, 11, 16));

        BusinessRuleViolationException exception =
            assertThrows(
                BusinessRuleViolationException.class,
                () -> processor.process(large));

        assertEquals(
            "AMOUNT_REVIEW_REQUIRED",
            exception.getRuleCode());
    }

    @Test
    void neverSilentlyRoundsAmount() {
        OrderRow extraPrecision = new OrderRow(
            "ORDER-P",
            new BigDecimal("10.005"),
            "USD",
            "READY",
            LocalDate.of(2026, 11, 16));

        BusinessRuleViolationException exception =
            assertThrows(
                BusinessRuleViolationException.class,
                () -> processor.process(extraPrecision));

        assertEquals(
            "AMOUNT_SCALE",
            exception.getRuleCode());
    }
}
```

Những test này xác nhận contract của business rules ở mức từng item: biến đổi, lọc, mã lỗi và ngưỡng. Chúng chưa chứng minh skip policy, transaction, ghi quarantine hay rollback đúng ở toàn step; những yêu cầu đó cần integration test.

### 6.3. Test boundary quan trọng hơn test một giá trị giữa khoảng

Với rule `amount > 0` và `amount <= max`, nên có các ca:

- Null.
- `0` và số âm.
- Giá trị dương rất nhỏ.
- Bằng ngưỡng tối đa.
- Lớn hơn ngưỡng một đơn vị nhỏ nhất được phép.
- Có scale nhiều hơn mức cho phép.
- Giá trị lớn bất thường hoặc precision vượt giới hạn database.

Với business date, thử trước kỳ, đúng kỳ và sau kỳ. Với currency/status, thử chữ thường, whitespace, null, mã không trong whitelist. Khi input có encoding/Unicode, tránh giả định `trim()` giải quyết được mọi ký tự trắng hoặc normalization nghiệp vụ.

---

## 7. Kết hợp nhiều rule qua một pipeline có cấu trúc

Một processor hàng trăm dòng có nhiều trách nhiệm sẽ khó theo dõi. Một hướng phổ biến là chia logic thành nhiều stage:

```text
RawOrder
   |
   v
BasicValidationProcessor
   |
   v
CanonicalizationProcessor
   |
   v
BusinessEligibilityProcessor
   |
   v
RiskClassificationProcessor
   |
   v
ApprovedOrder / Decision
```

Spring Batch có `CompositeItemProcessor` để nối nhiều `ItemProcessor` theo thứ tự. Output type của delegate trước phải phù hợp input type của delegate sau.

### 7.1. Ví dụ composite processor

```java
import java.util.List;

import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.support.CompositeItemProcessor;

ItemProcessor<OrderRow, OrderRow> normalize = item ->
    new OrderRow(
        item.externalOrderId() == null
            ? null : item.externalOrderId().trim(),
        item.amount(),
        item.currency() == null
            ? null : item.currency().trim(),
        item.status() == null
            ? null : item.status().trim(),
        item.businessDate());

ItemProcessor<OrderRow, ApprovedOrder> business =
    new OrderBusinessRuleProcessor(rules);

CompositeItemProcessor<OrderRow, ApprovedOrder> pipeline =
    new CompositeItemProcessor<>();

pipeline.setDelegates(List.of(normalize, business));
```

`rules` trong ví dụ là `OrderRuleContext` đã được tạo cho job. Các delegate được chạy theo thứ tự danh sách. Nếu một delegate trả `null` để filter, composite dừng chuyển item đó sang các delegate tiếp theo.

**Lưu ý state:** nếu một delegate implement `ItemStream`, cần bảo đảm lifecycle `open/update/close` được gọi đúng theo cấu hình phiên bản và wrapper/composite đang dùng. Một số composite/delegate có thể không tự động đăng ký stream dưới mọi kiểu wiring; thiếu checkpoint thường chỉ lộ ra khi restart.

### 7.2. Khi nào cần class rule riêng?

Nếu quy tắc có nhiều biến thể, cần metadata và version, có thể dùng contract:

```java
public interface BusinessRule<T> {
    String code();
    RuleOutcome evaluate(T item, RuleContext context);
}
```

`RuleOutcome` và `RuleContext` là kiểu domain do dự án định nghĩa. Một `RuleEngine` chạy danh sách rules theo thứ tự, trả kết quả hoặc tập violations. Cách này giúp:

- Thêm/bớt rule có kiểm soát.
- Viết unit test độc lập cho mỗi rule.
- Bật/tắt rule theo phiên bản chính sách hoặc tenant.
- Gắn mã/độ nghiêm trọng và quan sát kết quả.
- Tránh đưa validation, persistence và quyết định retry vào cùng một class.

Tuy nhiên, đừng tạo một rule engine quá tổng quát chỉ để thay vài điều kiện đơn giản. Kiến trúc nên tương xứng số lượng, độ thay đổi và yêu cầu kiểm toán của rules.

---

## 8. Bean Validation và `ValidatingItemProcessor`

Spring Batch có các công cụ validation có thể dùng trước hoặc trong business processor.

### 8.1. `ValidatingItemProcessor`

Một `Validator<T>` của Spring Batch nhận item và ném `ValidationException` khi không hợp lệ:

```java
import org.springframework.batch.item.validator.ValidationException;
import org.springframework.batch.item.validator.Validator;

Validator<OrderRow> basicValidator = row -> {
    if (row == null ||
        row.externalOrderId() == null ||
        row.externalOrderId().isBlank()) {

        throw new ValidationException(
            "externalOrderId is required");
    }
};
```

Dùng với `ValidatingItemProcessor`:

```java
import org.springframework.batch.item.validator.ValidatingItemProcessor;

ValidatingItemProcessor<OrderRow> basicValidation =
    new ValidatingItemProcessor<>(basicValidator);

// Mặc định không filter; ValidationException được truyền lên.
basicValidation.setFilter(false);
```

Sau đó có thể đưa `basicValidation` vào `CompositeItemProcessor` trước business stage.

Nếu `setFilter(true)`, những item validation fail được trả `null` và tính là **filtered**, không phải skipped. Chỉ bật khi việc loại bỏ âm thầm đúng với nghiệp vụ; nếu mục tiêu là audit record sai, nên giữ violation và routing đến quarantine.

### 8.2. Bean Validation (Jakarta Validation)

Với Spring Boot 3.x, có thể dùng:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Model:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

import java.math.BigDecimal;

public record ImportDto(
    @NotBlank String externalOrderId,
    @NotNull @Positive BigDecimal amount,
    @NotBlank String currency
) {}
```

Spring Batch cung cấp `BeanValidatingItemProcessor<T>` để kiểm tra các constraint Jakarta Bean Validation trên item, nếu hạ tầng validation phù hợp được cấu hình. Những constraint như `@NotBlank` hay `@Positive` hữu ích cho kiểm tra thuộc tính phổ biến, còn rule nghiệp vụ liên quan nhiều trường, tenant, business date hoặc policy version thường cần processor/domain service riêng.

**Không đồng nhất annotation với một hợp đồng data quality hoàn chỉnh.** `@Positive` không nói được amount này có vượt hạn mức phê duyệt của tenant hay không.

### 8.3. Thứ tự validator và business rule

Một pipeline hợp lý có thể là:

```text
Input parse
   -> validate các trường bắt buộc và kiểu cơ bản
   -> normalize giá trị
   -> business rules/eligibility
   -> classify accepted/rejected/review
   -> writer
```

Nếu rule yêu cầu giá trị đã chuẩn hóa (ví dụ currency uppercase), normalize phải xảy ra trước rule đó. Nếu cần ghi lại dữ liệu gốc để audit, giữ cả raw và canonical value trong decision hoặc audit record; không overwrite raw payload mất dấu vết.

---

## 9. Khi nào không nên dùng `null`: decision object và quarantine

Giả sử batch phải lưu tất cả item có quyết định rõ ràng:

- Hợp lệ: ghi bảng `approved_orders`.
- Vi phạm rule: ghi bảng `rejected_orders` với rule code.
- Vượt hạn mức: ghi bảng `manual_review_queue`.

Nếu processor chỉ trả `null` cho item lỗi, writer sẽ không nhìn thấy chúng. `SkipListener` có thể ghi log, nhưng không tự bảo đảm một record audit bền vững đúng transaction.

### 9.1. Model quyết định

Java 17 dùng `sealed interface` và `record`:

```java
public sealed interface OrderDecision
        permits AcceptedDecision,
                RejectedDecision,
                ReviewDecision {
}

public record AcceptedDecision(
    ApprovedOrder order) implements OrderDecision {
}

public record RejectedDecision(
    String externalOrderId,
    String ruleCode,
    String ruleVersion) implements OrderDecision {
}

public record ReviewDecision(
    String externalOrderId,
    String reasonCode,
    String ruleVersion) implements OrderDecision {
}
```

Một processor thay vì ném exception cho những vi phạm được phép lưu quarantine có thể trả về decision:

```java
public final class ClassifyingOrderProcessor
        implements ItemProcessor<OrderRow, OrderDecision> {

    private final OrderRuleContext rules;

    public ClassifyingOrderProcessor(OrderRuleContext rules) {
        this.rules = rules;
    }

    @Override
    public OrderDecision process(OrderRow row) {

        if (row == null ||
            row.externalOrderId() == null ||
            row.externalOrderId().isBlank()) {
            return new RejectedDecision(
                null, "ORDER_ID_REQUIRED", rules.ruleVersion());
        }

        if (row.amount() == null ||
            row.amount().signum() <= 0) {
            return new RejectedDecision(
                row.externalOrderId(),
                "AMOUNT_NON_POSITIVE",
                rules.ruleVersion());
        }

        if (row.amount().compareTo(
                rules.maxAutoApprovedAmount()) > 0) {
            return new ReviewDecision(
                row.externalOrderId(),
                "AMOUNT_REVIEW_REQUIRED",
                rules.ruleVersion());
        }

        if (!rules.businessDate().equals(
                row.businessDate())) {
            return new RejectedDecision(
                row.externalOrderId(),
                "DATE_OUT_OF_SCOPE", rules.ruleVersion());
        }

        return new AcceptedDecision(new ApprovedOrder(
            row.externalOrderId(),
            row.amount(),
            row.currency(),
            row.businessDate()));
    }
}
```

Ví dụ này minh họa **cách phân loại** chứ không dùng chung toàn bộ rules với `OrderBusinessRuleProcessor` ở mục 5. Khi áp dụng thật, nên tái sử dụng các rule/domain validation chung và định nghĩa rõ trạng thái CANCELLED/unsupported currency; không vận hành hai policy khác nhau một cách vô tình.

### 9.2. Routing writer cho nhiều kết quả

Một `ItemWriter<OrderDecision>` có thể chia item thành các nhóm và ủy quyền cho từng writer:

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ItemWriter;

public final class OrderDecisionWriter
        implements ItemWriter<OrderDecision> {

    private final ItemWriter<ApprovedOrder> approvedWriter;
    private final ItemWriter<RejectedDecision> rejectedWriter;
    private final ItemWriter<ReviewDecision> reviewWriter;

    public OrderDecisionWriter(
            ItemWriter<ApprovedOrder> approvedWriter,
            ItemWriter<RejectedDecision> rejectedWriter,
            ItemWriter<ReviewDecision> reviewWriter) {
        this.approvedWriter = approvedWriter;
        this.rejectedWriter = rejectedWriter;
        this.reviewWriter = reviewWriter;
    }

    @Override
    public void write(Chunk<? extends OrderDecision> chunk)
            throws Exception {

        List<ApprovedOrder> approved = new ArrayList<>();
        List<RejectedDecision> rejected = new ArrayList<>();
        List<ReviewDecision> review = new ArrayList<>();

        for (OrderDecision decision : chunk.getItems()) {

            if (decision instanceof AcceptedDecision accepted) {
                approved.add(accepted.order());

            } else if (
                decision instanceof RejectedDecision invalid) {
                rejected.add(invalid);

            } else if (
                decision instanceof ReviewDecision pendingReview) {
                review.add(pendingReview);
            }
        }

        if (!approved.isEmpty()) {
            approvedWriter.write(new Chunk<>(approved));
        }

        if (!rejected.isEmpty()) {
            rejectedWriter.write(new Chunk<>(rejected));
        }

        if (!review.isEmpty()) {
            reviewWriter.write(new Chunk<>(review));
        }
    }
}
```

Nếu cả ba delegate writer là JDBC writers dùng **cùng transaction manager và datasource** của chunk step, chúng có thể cùng tham gia transaction để dữ liệu accepted/rejected/review nhất quán khi rollback. Nếu chúng ghi vào ba database hoặc gọi HTTP, **không có atomicity tự động**; phải thiết kế idempotency, outbox hoặc reconciliation riêng.

**Metadata counts:** Spring Batch `writeCount` của một step ghi `OrderDecision` thường đếm **decision items đã ghi qua writer**, không trực tiếp là số đơn approved. Muốn biết accepted/rejected/review counts, cần metric/bảng kết quả chuyên biệt. Đừng lấy `writeCount` làm số đơn hợp lệ trong thiết kế routing này.

### 9.3. Quarantine cần lưu gì?

Một record bị reject có thể cần:

| Trường | Vai trò |
| --- | --- |
| Source system / file / batch ID | Truy xuất nguồn |
| Business key hoặc source line ID | Định danh record |
| Rule code | Phân loại lỗi ổn định |
| Rule version | Biết chính sách áp dụng |
| Original value / sanitized payload | Phục vụ sửa lỗi và reprocess có kiểm soát |
| JobInstance/Execution ID | Liên kết execution và audit |
| First seen / last seen | Theo dõi lịch sử |
| Resolution status | `NEW`, `FIXED`, `WAIVED`, `REPROCESSED` ... |

Chỉ lưu dữ liệu cần thiết, có quy định bảo mật và retention; tránh đưa PII/secrets vào logs, metrics tag hoặc exception string không kiểm soát.

---

## 10. Cấu hình fault-tolerant step: skip có hạn mức

Nếu chính sách cho phép bỏ qua một số record lỗi thay vì ghi chúng vào quarantine ngay trong writer, có thể dùng Spring Batch fault tolerance.

### 10.1. Ví dụ Spring Batch 5.x

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, ApprovedOrder> processor,
        ItemWriter<ApprovedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderRow, ApprovedOrder>chunk(
            100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(BusinessRuleViolationException.class)
        .skipLimit(50)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
}
```

Semantics đáng nhớ:

- `.skip(BusinessRuleViolationException.class)` cho phép step skip loại exception đó theo hạn mức.
- `.skipLimit(50)` giới hạn tổng skip của step theo chính sách Spring Batch, không phải 50 cho mỗi loại lỗi riêng.
- Khi exception từ processor được skip, `processSkipCount` ghi nhận theo framework.
- Nếu số lỗi vượt hạn mức, step có thể thất bại.
- `.retry(TransientDataAccessException.class)` hướng đến lỗi tài nguyên tạm thời; phải điều chỉnh classifier với JDBC driver và nghiệp vụ.
- Không đưa `BusinessRuleViolationException` vào retry mặc định: cùng input và rule snapshot sẽ thường tiếp tục thất bại.

**Cần cân nhắc kỹ:** Trong ví dụ ở mục 5, lỗi `AMOUNT_REVIEW_REQUIRED` cũng là `BusinessRuleViolationException`. Nếu cấu hình skip chung, những đơn cần review sẽ **bị bỏ qua**, không tự xuất hiện trong manual review queue. Nếu đây là điều không được phép, cần dùng các exception subclass riêng và skip policy phân loại, hoặc chuyển sang decision routing như mục 9.

### 10.2. Skip limit có phải KPI chất lượng dữ liệu không?

Không. `skipLimit` là **ngưỡng chặn của step**, giúp tránh một feed quá lỗi bị bỏ qua quá nhiều. Một hệ thống có thể cần threshold theo tỷ lệ, ví dụ không quá 0,1% record invalid, thay vì một con số cố định.

Để quản lý tỷ lệ, tính số lỗi trên một mẫu số được định nghĩa rõ (raw records, parsed records hay eligible records), sau đó áp dụng rule ở một bước tổng kết hoặc gate chuyên dụng. Một bộ đếm trong processor không đủ tin cậy khi có rollback, retry hoặc parallel processing.

### 10.3. `SkipListener` và việc ghi nhận lỗi

Spring Batch cung cấp `SkipListener<I,O>` với các callback như:

```java
import org.springframework.batch.core.SkipListener;

public final class OrderSkipObserver
        implements SkipListener<OrderRow, ApprovedOrder> {

    @Override
    public void onSkipInProcess(
            OrderRow item, Throwable throwable) {

        if (throwable
                instanceof BusinessRuleViolationException violation) {
            // Quan sát rule code để audit/metrics.
            // Không tự gọi API bên ngoài một cách mù quáng.
            String code = violation.getRuleCode();
        }
    }
}
```

Có thể đăng ký với builder qua `.listener(new OrderSkipObserver())` ở bước cấu hình fault-tolerant step. `SkipListener` hữu ích để biết item bị skip, nhưng **không phải cơ chế exactly-once tự động cho mọi side effect**. Nếu callback ghi vào một database/queue ngoài transaction hiện tại và step rollback/restart, dữ liệu audit có thể trùng hoặc lệch.

Nếu mỗi record sai bắt buộc có một bằng chứng persisted nhất quán với kết quả chunk, dùng routing writer trong cùng transaction hoặc cơ chế outbox có khóa idempotency rõ ràng.

### 10.4. Những lỗi không nên skip

- Mất kết nối database.
- Lỗi mapping output khiến toàn bộ writer không ghi được.
- Metadata repository không persist được.
- Lỗi cấu hình rule version.
- Bug `NullPointerException` do code.
- Vi phạm critical data quality gate đòi dừng batch để sửa nguồn.

Cấu hình `.skip(Exception.class)` có thể khiến job báo `COMPLETED` dù bỏ đi lượng lớn dữ liệu và che lỗi hạ tầng. Chỉ skip những loại lỗi có contract nghiệp vụ cho phép, với threshold và audit phù hợp.

---

## 11. Nên viết rule thuần hàm và deterministic

### 11.1. Retry và restart có thể gọi processor nhiều lần

Trong chunk processing, một item có thể được xử lý lại khi transaction rollback, fault-tolerant retry hoặc job restart:

```text
Chunk:
  read item 101
  process item 101 -> approved
  write(chunk)     -> database error
  transaction      -> ROLLBACK

Restart/retry:
  read item 101 (hoặc reprocess cached item)
  process item 101 -> phải cho kết quả tương thích
  write(chunk)     -> retry / commit
```

Nếu processor có side effect như gửi email, gọi API thu tiền, ghi log audit riêng không transactional hoặc tăng counter có ảnh hưởng nghiệp vụ, retry có thể nhân đôi hành động.

**Thiết kế ưu tiên:**

```text
Business processor:
  result = f(input item, immutable rule context)
  không ghi dữ liệu ngoài
  không gửi thông báo
  không tạo identifying UUID cho mỗi lần process
  không phụ thuộc vào trạng thái mutable toàn cục
```

I/O thực sự cần thiết nên được đặt tại bước được quản lý transaction phù hợp hoặc ở một service có semantics retry/idempotency được kiểm soát.

### 11.2. Tránh dùng `LocalDate.now()` trực tiếp trong rule

Giả sử import job chạy ngày 16 rồi restart ngày 17. Nếu business rule so sánh input date với `LocalDate.now()`, cùng item có thể được chấp nhận ngày 16 nhưng bị từ chối ngày 17.

Thay vì:

```java
if (!item.businessDate().equals(LocalDate.now())) {
    return null;
}
```

Hãy truyền **business date của `JobInstance`** như một tham số ổn định:

```java
new OrderRuleContext(
    LocalDate.parse(jobBusinessDate),
    maxAmount,
    allowedCurrencies,
    ruleVersion
);
```

Nếu rule thực sự phụ thuộc giờ hiện tại, hãy xác định một `Clock` hoặc cut-off instant snapshot theo hợp đồng, ghi vào metadata/JobParameters phù hợp để restart không thay đổi quyết định ngoài ý muốn.

### 11.3. External reference data cần snapshot hoặc version

Ví dụ rule “customer có active account” phải truy vấn một service khác. Nếu trạng thái customer thay đổi giữa lần xử lý đầu và restart, kết quả có thể đổi dù input giống nhau.

Chiến lược:

- Prefetch/reference snapshot ở đầu job theo kỳ dữ liệu.
- Dùng version hoặc effective-at timestamp khi query.
- Cache có key/TTL phù hợp và invalidation rõ.
- Với rule thật sự phải đánh giá theo trạng thái mới nhất, định nghĩa rõ việc re-evaluation khi restart.
- Thêm test cho consistency khi rule config hoặc reference data đổi giữa executions.

Một processor chỉ đọc tham chiếu một lần và giữ trong mutable singleton cũng có thể bị chia sẻ giữa nhiều jobs hoặc tenants. Cần thiết kế bean scope và context isolation phù hợp.

---

## 12. JobParameters, rule version và `@StepScope`

### 12.1. Truyền business date vào processor

Với Spring Boot 3 và Spring Batch 5, có thể tạo processor theo step scope:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Set;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderProcessorConfiguration {

    @Bean
    @StepScope
    ItemProcessor<OrderRow, ApprovedOrder> orderProcessor(
            @Value("#{jobParameters['businessDate']}")
            String businessDate,
            @Value("#{jobParameters['ruleVersion']}")
            String ruleVersion) {

        OrderRuleContext context = new OrderRuleContext(
            LocalDate.parse(businessDate),
            new BigDecimal("1000000.00"),
            Set.of("USD", "VND"),
            ruleVersion
        );

        return new OrderBusinessRuleProcessor(context);
    }
}
```

`@StepScope` tạo proxy bean để lấy `jobParameters` khi step execution thực sự hoạt động, không phải lúc ứng dụng mới startup. Ví dụ giả định cả hai tham số đều có mặt và đúng định dạng; production nên validate JobParameters trước khi job chạy.

### 12.2. Identifying và non-identifying parameters

Spring Batch dùng tên job và **identifying JobParameters** để xác định `JobInstance`. Các lựa chọn:

- `businessDate` thường là identifying vì ngày khác tạo một đợt xử lý logic mới.
- `tenantId` có thể identifying nếu job được chạy theo tenant.
- `ruleVersion` có nên identifying không phụ thuộc contract: nếu đổi version đồng nghĩa một run mới, cần ghi rõ; nếu restart phải giữ rule cũ, không được âm thầm đổi version hoặc đọc config “mới nhất”.
- `traceId` thường non-identifying; thay trace ID không nên tạo JobInstance khác.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("tenantId", "TENANT-A", true)
    .addString("ruleVersion", "rules-2026-11", false)
    .addString("traceId", "trace-63829", false)
    .toJobParameters();
```

**Lưu ý quan trọng:** `non-identifying` không có nghĩa được tự do thay đổi khi restart qua `JobOperator`; Spring Batch restart phải dựa vào parameters và metadata của instance/execution cũ. Tính ổn định của rule configuration cần được đảm bảo bằng chính sách deploy/version và snapshot, không chỉ bằng flag `identifying=false`.

### 12.3. Khi rule thay đổi giữa các lần chạy

Một job thất bại khi rule version A đang áp dụng, hôm sau production deploy version B. Hệ thống cần chính sách:

| Chính sách | Cách làm | Đánh đổi |
| --- | --- | --- |
| Freeze rule snapshot | Lưu version và dùng logic tương ứng khi restart | Cần lưu/duy trì version cũ |
| Re-evaluate theo policy mới | Cho phép processor dùng version B | Cần reconciliation, có nguy cơ kết quả khác với chunk cũ |
| Không cho restart qua breaking rule change | Từ chối restart, yêu cầu migration/reprocess | An toàn hơn trong trường hợp hợp đồng thay đổi mạnh |

Không giả định thay JAR là có thể restart mọi job đang thất bại mà không kiểm tra tương thích rule code, input/output schema và `ExecutionContext`.

---

## 13. Rules phụ thuộc nhiều item: vì sao không nên dùng state của một processor?

Một số quy tắc vượt phạm vi từng item:

- Không có hai đơn trùng business key trong cùng file.
- Tổng tiền toàn bộ batch phải khớp header/trailer.
- Một customer không được có hơn N giao dịch trong ngày.
- Mỗi file phải có đầy đủ sequence numbers.
- Hai record từ các nguồn khác nhau phải khớp trước khi xuất báo cáo.

Một processor có `Map`/`Set` mutable để đếm hoặc đánh dấu seen IDs dễ gặp vấn đề:

1. Khi rollback/retry, cùng item có thể được xử lý lại và bị xem là trùng.
2. Khi restart JVM, state trong bộ nhớ biến mất.
3. Với multi-threaded step, mutable map có race condition.
4. Với partitioning, mỗi partition không thấy dữ liệu của partition khác.
5. Tập dữ liệu lớn có thể làm tràn bộ nhớ.

### 13.1. Những giải pháp thay thế

| Rule | Cách tiếp cận thường phù hợp |
| --- | --- |
| Business key phải duy nhất toàn bộ dữ liệu đích | Unique constraint + idempotent upsert / reject policy |
| Trùng trong một file nhập | Staging table với unique key theo source file; SQL query/aggregation |
| Tổng amount phải khớp trailer | Aggregation step hoặc bước reconciliation sau load |
| Giới hạn giao dịch theo khách hàng/ngày | Query/aggregation transactionally trên dữ liệu có snapshot |
| Quan hệ giữa nhiều loại entity | Validate trong staging hoặc bước join/match riêng |
| Risk score cần lịch sử | Domain rule service truy cập snapshot/versioned reference data |

Processor từng item vẫn có thể gọi một domain service xác định eligibility, nhưng tính đúng của rule liên item phải xét consistency, concurrency và transaction semantics của nơi service đọc trạng thái.

### 13.2. Vì sao database constraint vẫn cần tồn tại?

Ngay cả khi processor kiểm tra external order ID chưa có trong database, hai Batch executions song song đều có thể kiểm tra “chưa tồn tại” rồi cùng insert. Database unique constraint mới là guard cuối có thể phân xử concurrency. Processor validation bổ sung thông điệp lỗi tốt hơn, **không thay thế** constraint.

---

## 14. Data quality gates: lỗi từng record và lỗi cả đợt

Có nghiệp vụ cho phép loại tối đa 0,5% item sai; có nghiệp vụ buộc **dừng cả job nếu bất kỳ record nào vi phạm**.

### 14.1. Ba chính sách tổng thể

1. **Strict:** bất kỳ critical violation nào cũng làm step `FAILED`; dùng khi output không được phép thiếu.
2. **Tolerant with threshold:** cho skip/reject trong hạn mức và vẫn hoàn thành với tập kết quả có thể dùng.
3. **Quarantine + gate:** lưu quyết định rejected/review, rồi ở bước sau kiểm tra tổng số lượng/tỷ lệ/quy tắc nghiêm trọng để xác định có được công bố kết quả hay không.

### 14.2. Gate theo tỷ lệ

Ví dụ:

```text
Raw rows parsed:             100,000
Eligible rows:                95,000
Rejected eligible rows:          250
Allowed invalid ratio:          0.2%

Observed ratio:
  250 / 95,000 = 0.2632%
  -> FAIL DATA QUALITY GATE
```

Phải định nghĩa mẫu số. Nếu 5.000 canceled orders được filter hợp lệ, tỷ lệ reject trên 100.000 raw records sẽ khác tỷ lệ trên 95.000 eligible records. Không chọn mẫu số theo hướng làm KPI đẹp hơn.

### 14.3. Thời điểm gate ảnh hưởng nghiệp vụ

Nếu Batch đã ghi accepted records vào bảng production, sau đó quality gate thất bại, **job `FAILED` không tự rollback những chunk đã commit trước đó**. Với những quy trình cần all-or-nothing ở cấp toàn batch:

```text
Reader -> Processor -> staging tables
                  |
                  v
          Quality reconciliation
                  |
          +-------+--------+
          |                |
        PASS             FAIL
          |                |
          v                v
     Publish/merge     Keep quarantine,
     from staging      do not publish
```

Staging/merge giúp tách việc **nạp và kiểm tra dữ liệu** khỏi việc **công bố dữ liệu hợp lệ**. Tùy yêu cầu, bước publish có thể dùng transaction ở mức phù hợp hoặc một cơ chế version/pointer swap, chứ không chỉ hy vọng toàn job có một transaction xuyên nhiều chunk.

---

## 15. Business rule và transaction/restart

### 15.1. Điều gì xảy ra khi lỗi ở writer?

Một chunk gồm 100 input items, processor đã chấp nhận 96 và filter 4. Writer gặp lỗi database, transaction rollback. Sau retry/restart, processor có thể chạy lại trên một số item tùy reader/step policy.

Nếu processor thuần hàm với rule context ổn định, kết quả vẫn là 96 accepted, 4 filtered. Nếu processor cập nhật một bộ đếm mutable làm nguồn chân lý, số đếm có thể tăng hai lần và không đúng với output đã commit.

### 15.2. Counter trong memory không phải kết quả chính thức

Một đoạn như:

```java
private long rejectedCount = 0;

public ApprovedOrder process(OrderRow row) {
    if (isInvalid(row)) {
        rejectedCount++; // Có thể tăng lại khi rollback/retry.
        return null;
    }
    return map(row);
}
```

không phải cách đáng tin cậy để đo số unique rejected records ở batch có retry/restart. Ngoài ra, nếu processor bean singleton được dùng chung nhiều execution, state còn có thể bị trộn giữa các jobs.

Ưu tiên:

- `StepExecution` counters cho quan sát cơ bản.
- Bảng rejected/decision có **unique business key** cho số liệu audit bền vững.
- Aggregation/query sau execution để tính KPI chính thức.
- Micrometer counters cho quan sát thời gian thực với hiểu biết rằng đó là **số lời gọi/attempts**, không nhất thiết là unique records.
- Nếu cần stateful processor, thiết kế `ItemStream`, checkpoint, thread safety và rollback semantics rất rõ.

### 15.3. Rule processor phải idempotent theo contract

Idempotency ở processor nghĩa là cùng input và cùng immutable rule context cho cùng kết quả, không tạo side effect mới. **Idempotency của writer** là vấn đề khác: cùng approved item được ghi lặp lại không tạo output trùng ngoài yêu cầu.

Một hệ thống cần cả hai khi metadata checkpoint và business transaction không được commit nguyên tử, đặc biệt khi tách metadata database khỏi business database.

---

## 16. Audit trail và observability cho business rules

### 16.1. Dùng rule code, không chỉ message tự do

Một exception message có thể thay đổi khi sửa câu chữ, nhưng `ruleCode` nên có semantics ổn định:

```text
ruleCode=AMOUNT_NON_POSITIVE
ruleVersion=rules-2026-11
jobName=importOrdersJob
stepName=importOrdersStep
jobExecutionId=9221
sourceRecordId=ORDER-148
decision=REJECTED
```

Ví dụ log trên không chứa thông tin nhạy cảm; ID thật vẫn cần xử lý theo chính sách dữ liệu của tổ chức.

Một rule được tách thành hai logic riêng hoặc đổi nghĩa cần cân nhắc **version/code mới**, thay vì làm dashboard lịch sử diễn giải cùng code theo hai nghĩa.

### 16.2. Metrics có cardinality hữu hạn

Gợi ý metric (tên minh họa, không phải built-in):

| Metric | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| `batch.rule.evaluations` | attempts | Số lần đánh giá rule |
| `batch.rule.violations` | attempts | Số lần rule bị vi phạm |
| `batch.rule.duration` | seconds | Latency của rule/service |
| `batch.dataquality.rejected` | decisions | Số decision rejected |
| `batch.dataquality.review` | decisions | Số decision cần review |
| `batch.dataquality.gate_failed` | gates | Số đợt không đạt ngưỡng |
| `batch.dataquality.quarantine_backlog` | records | Số record chưa giải quyết |

Tag nên giới hạn vào `job.name`, `step.name`, `rule.code`, `rule.version` và `decision` khi số giá trị nhỏ/có quản lý. **Không dùng `externalOrderId`, raw amount, customer email hay `jobExecutionId` làm metric tag** vì cardinality cao và rủi ro lộ dữ liệu.

### 16.3. Thời gian xử lý rule

Một business rule chỉ so sánh BigDecimal thường rất nhanh. Một rule gọi HTTP/DB theo từng item có thể là bottleneck lớn:

```text
100,000 items
  * 1 remote check per item
  * 20 ms trung bình/check
  = ~2,000 giây chờ tuần tự
```

Đây là ước lượng tuyến tính cho xử lý tuần tự, chưa tính network variance, caching, concurrency và retry. Để cải thiện:

- Preload bảng tham chiếu nhỏ theo rule version.
- Batch lookup thay vì N+1 query.
- Cache có key/TTL/invalidation phù hợp.
- Dùng snapshot dữ liệu theo business date.
- Kiểm soát timeout và retry của remote rule service.
- Nếu song song, bảo đảm service chịu được rate và rule không phụ thuộc mutable state.

Không nên hy sinh tính đúng của rule chỉ để tăng throughput; đặc biệt cache stale có thể chấp nhận cho rule hiển thị nhưng không phù hợp cho một số rule compliance.

---

## 17. Dữ liệu lỗi, bảo mật và quyền thay đổi rule

### 17.1. Lưu dữ liệu reject có kiểm soát

Bảng quarantine có thể chứa raw payload phục vụ sửa lỗi. Nhưng raw payload có thể gồm số định danh khách hàng, thông tin tài chính, địa chỉ hoặc token không nên lưu vô hạn.

Nên có:

- Data classification và retention.
- Access control để người sửa lỗi chỉ xem dữ liệu thuộc phạm vi.
- Audit log của thao tác sửa/waive/reprocess.
- Masking/encryption nếu dữ liệu nhạy cảm.
- Không đưa full payload vào exception message và metric labels.
- Quy tắc chọn lọc những trường thật sự cần cho remediation.

### 17.2. Quản lý thay đổi rule

Một rule do cấu hình ngoài điều khiển cần lifecycle:

```text
DRAFT
  -> REVIEWED
  -> APPROVED
  -> EFFECTIVE(version, timestamp)
  -> RETIRED
```

Khi batch chạy, log `ruleVersion`/effective instant phù hợp. Không nên để người dùng sửa cấu hình ngưỡng giữa chừng mà một nửa file chạy rule A, nửa còn lại chạy rule B, trừ khi đó là yêu cầu đã được thiết kế tường minh.

### 17.3. Reprocess record bị reject

Khi nguồn dữ liệu đã sửa, thường cần:

1. Xác định record/slot đã bị reject và rule version cũ.
2. Chọn input mới hoặc dữ liệu đã được sửa, với audit sửa đổi.
3. Quyết định chạy lại cả `JobInstance`, một job remediation riêng hay một ingestion mới.
4. Sử dụng business key/unique constraints để tránh viết lại record accepted.
5. Đối soát output và cập nhật trạng thái quarantine.

**Không mặc định rằng restart một `JobInstance COMPLETED` sẽ xử lý lại các item đã filter/skip**. Job đã completed không được restart theo cơ chế thông thường. Một quy trình remediation có thể cần job mới hoặc thiết kế tách luồng.

---

## 18. Integration test cho business rules trong chunk step

Unit test đã chứng minh logic của processor, nhưng toàn step còn phải xác nhận filter/skip/writer semantics.

### 18.1. Fixture dự kiến

Giả sử file test có 6 items:

| ID | Trạng thái | Amount | Kết quả |
| --- | --- | ---: | --- |
| A | READY | 100 | Accepted |
| B | CANCELLED | 50 | Filtered |
| C | READY | 0 | Rejected/Skipped theo policy |
| D | READY | 200 | Accepted |
| E | READY | 10.005 | Rejected/Skipped |
| F | READY | 300 | Accepted |

Với step có `skip(BusinessRuleViolationException.class)`, `skipLimit(2)`, và writer chỉ nhận `ApprovedOrder`:

- `readCount` dự kiến 6 nếu input fixture không có read failure.
- `filterCount` dự kiến 1 cho B.
- `processSkipCount` dự kiến 2 cho C và E.
- `writeCount` dự kiến 3 cho A, D, F nếu writer thành công.
- `JobExecution` `COMPLETED` nếu không có lỗi khác.

Những giá trị là kỳ vọng của fixture này trong một step đồng bộ, không retry/rollback đặc biệt. Test nên đọc `StepExecution` đã persist từ repository, chứ không chỉ nhìn counter trên object processor trong bộ nhớ.

### 18.2. Khung assertion

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;

import static org.junit.jupiter.api.Assertions.*;

JobExecution execution =
    jobLauncherTestUtils.launchJob(uniqueParameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution step = execution.getStepExecutions().stream()
    .filter(s -> "importOrdersStep".equals(s.getStepName()))
    .findFirst()
    .orElseThrow();

assertEquals(6L, step.getReadCount());
assertEquals(1L, step.getFilterCount());
assertEquals(2L, step.getProcessSkipCount());
assertEquals(3L, step.getWriteCount());
```

Đây là **khung assertion** nằm trong một integration test có `@SpringBatchTest`, `@SpringBootTest`, JobRepository, JobLauncher và các bean reader/processor/writer đã thiết lập. `uniqueParameters` là `JobParameters` của test fixture, không phải biến Spring Batch tự cung cấp.

Nếu dùng decision-routing writer thay vì skip/filter, expected counters **khác** vì các decision bị rejected/review vẫn đi đến writer. Test phải dựa trên hợp đồng đã chọn, không sao chép nguyên bộ assert của chiến lược khác.

### 18.3. Kiểm thử khi vượt skip limit

Thêm item G lỗi nghiệp vụ trong khi `skipLimit(2)` đã đạt. Bước xử lý cần phản ánh chính sách vượt ngưỡng: step thất bại thay vì tiếp tục bỏ vô hạn.

Cần kiểm tra status cuối, exception/cause và các chunk đã commit trước khi lỗi. Vì chunk processing có transaction boundaries, `FAILED` của job không có nghĩa tất cả output trước đó được rollback. Nếu yêu cầu không công bố partial output, hãy dùng staging + quality gate + publish step.

### 18.4. Kiểm thử retry/restart

Cho writer thất bại sau khi một số chunk đã commit, rồi restart job với cùng identifying parameters. Assert:

- Processor không tạo duplicate external side effect.
- Các rule decisions cho item đã xử lý lại vẫn nhất quán khi dùng cùng rule snapshot.
- Reader khôi phục checkpoint thích hợp.
- Output accepted không trùng, dữ liệu quarantine có unique key.
- Tổng chất lượng dữ liệu cuối dựa trên **unique records**, không dựa vào attempts.

### 18.5. Multi-threaded step

Nếu processor dùng `AtomicInteger` để đếm violations hoặc mutable `HashSet` để dedup, unit test single-thread thường không phát hiện race. Với multi-thread/partitioned step:

- Rule context nên immutable và thread-safe.
- Metrics registry phải thread-safe.
- Không giữ state riêng theo thứ tự item trừ khi có thiết kế đồng bộ và checkpoint.
- Bảo vệ uniqueness ở database hoặc tầng staging.
- Test thêm concurrency và partition boundaries với dataset đại diện.

---

## 19. Mẫu thiết kế và lỗi thường gặp

| Mẫu/lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `return null` cho mọi invalid data | Mất dấu reject, chỉ thấy filter count | Chỉ filter item thực sự ngoài phạm vi; dùng skip/quarantine cho lỗi |
| `throw RuntimeException` chung | Khó phân loại; dễ retry/skip nhầm | Dùng exception/rule code có contract |
| `skip(Exception.class)` | Che lỗi hạ tầng, output thiếu | Skip loại lỗi đã được phép với threshold |
| Gửi email/gọi payment API trong processor | Retry có thể tạo side effect trùng | Đưa sang writer/outbox/idempotent service |
| `LocalDate.now()` cho business date | Restart ngày khác ra quyết định khác | JobParameters/Clock snapshot |
| Lấy ngưỡng “latest” theo từng item | Một job chạy nhiều policy | Freeze rule version/context |
| Đếm lỗi bằng field mutable trên singleton | Sai khi retry, parallel, nhiều jobs | Step counters, unique decision ledger, aggregation |
| Dedup bằng local `HashSet` | Sai khi restart/partition | Unique key/staging |
| Làm tròn số tiền ngầm | Sai amount và khó audit | Explicit scale/rounding contract |
| Rule code thay ý nghĩa không version | Dashboard lịch sử khó giải thích | Versioned rules và audit |
| Filter xong rồi kiểm tra dữ liệu nguồn toàn diện | KPI data quality thấp giả | Định nghĩa eligible population/mẫu số |
| Quarantine qua HTTP trong `SkipListener` | Audit có thể ghi lặp/không nhất quán | Routing writer cùng transaction/outbox |
| Chỉ test processor unit | Không thấy lỗi skip/rollback/wiring | Integration test chunk + JobRepository |
| Chỉ assert `JobExecution COMPLETED` | Có thể thiếu item nếu skip quá thoáng | Assert accepted/rejected counts và business output |
| Không bảo vệ writer bằng unique constraint | Two workers cùng insert một business key | Constraint + idempotent write |
| Rule gọi database mỗi item | N+1 queries, throughput thấp | Batch lookup/preload/cache snapshot |

### 19.1. Một flow quyết định khi viết rule mới

```text
Input item
    |
    v
Có parse/shape hợp lệ?
    | không
    +------> Reader mapping error / validation violation
    |
    v
Có thuộc phạm vi business?
    | không
    +------> FILTER (nếu đã được hợp đồng cho phép)
    |
    v
Rule có thể quyết định độc lập cho item?
    | không
    +------> Staging/aggregate/cross-record validation
    |
    v
Vi phạm có cần record audit?
    | có
    +------> Decision REJECTED / REVIEW -> routing writer
    |
    v
Vi phạm có được phép skip với ngưỡng?
    | có
    +------> BusinessRuleViolationException -> fault tolerant skip
    |
    v
Có critical violation?
    | có
    +------> Fail step / quality gate
    |
    v
Accepted -> ItemWriter
```

Sơ đồ thể hiện các lựa chọn nghiệp vụ, không phải thứ tự cố định Spring Batch áp dụng. Một rule cũng có thể yêu cầu cả audit **và** chặn publish; khi đó kết hợp staging/decision routing và quality gate.

---

## 20. Bài thực hành

### Bài 1 — Processor cho bộ quy tắc đơn hàng

Viết `ItemProcessor<OrderRow, ApprovedOrder>` với điều kiện:

- ID không rỗng.
- Status `CANCELLED` được filter.
- Status khác `READY` là violation.
- Amount > 0.
- Currency thuộc whitelist đã cấu hình.
- Business date bằng kỳ import.
- Amount vượt ngưỡng phải có rule code cần duyệt.

Viết unit test cho từng nhánh và các boundary của amount.

### Bài 2 — Composite processor

Tách pipeline thành normalize, validate và business eligibility. Dùng `CompositeItemProcessor` để nối các stage.

Yêu cầu: chứng minh stage sau không được gọi khi stage trước filter item, và biến đổi đầu ra phù hợp kiểu dữ liệu của delegate tiếp theo.

### Bài 3 — Skip và filter khác nhau

Dùng fixture có 6 item như mục 18. Đặt skip limit 2. Chạy integration test và khẳng định `readCount`, `filterCount`, `processSkipCount` và `writeCount`.

Thêm item vi phạm thứ ba. Xác định status của step và dữ liệu đã commit, giải thích vì sao `filterCount` không tính vào `skipLimit`.

### Bài 4 — Quarantine bền vững

Đổi processor để trả `AcceptedDecision`, `RejectedDecision` hoặc `ReviewDecision`. Viết routing writer ghi vào ba bảng có unique keys.

Yêu cầu: khi writer ném exception và chunk rollback, không có bản ghi accepted/rejected/review bị lưu một phần nếu cả ba table cùng transaction. Restart rồi chứng minh không có duplicate decisions.

### Bài 5 — Thay đổi rule version giữa restart

Một job ngày 16 chạy với rule version A, thất bại ở chunk thứ hai. Sau đó cấu hình ngưỡng thay đổi thành version B.

Hãy thiết kế chính sách freeze snapshot hoặc migration; test chứng minh cùng input được xử lý nhất quán theo contract restart đã chọn.

### Bài 6 — Data quality gate

Một feed có 100.000 rows, 5.000 item out of scope và 250 eligible items bị reject. Cho phép tỷ lệ invalid tối đa 0,2% trong eligible population.

Tính tỷ lệ thực tế, thiết kế một step gate và đề xuất cách ngăn output chưa đạt chất lượng được publish ra bảng production.

### Bài 7 — Rule liên record

Hai order có cùng external ID xuất hiện ở hai partition. Chứng minh local `HashSet` trong processor không bảo đảm phát hiện trùng. Đề xuất staging unique constraint và integration test concurrency.

### Bài 8 — Observability và báo cáo

Thiết kế dashboard gồm tổng source records, eligible, accepted, filtered, skipped, rejected, manual-review, KPI theo `ruleCode` và rule version. Nêu rõ mẫu số, quy tắc đếm unique records và cách tránh metric tags có cardinality cao.

---

## 21. Checklist thiết kế business rule trong processor

Trước khi đưa một processor vào luồng dữ liệu thật, cần trả lời:

- Rule được định nghĩa bằng tài liệu/decision table nào và ai có quyền phê duyệt?
- Input shape, dữ liệu reference và business date có ổn định theo lần chạy không?
- Kết quả của item là accepted, filter, reject, review hay fail job?
- Filter có đúng nghĩa “item không thuộc phạm vi” không?
- Vi phạm nào có thể skip, hạn mức bao nhiêu, ai xử lý các record bị bỏ qua?
- Có yêu cầu quarantine persisted trong cùng transaction không?
- Rule có phụ thuộc record khác, uniqueness hoặc tổng toàn batch không?
- Processor có tránh side effect ngoài transaction và giữ tính deterministic khi retry/restart không?
- Rule version/cấu hình có được freeze và audit không?
- Các metric phản ánh unique decisions hay chỉ attempts?
- Unit test, integration test, restart test và reconciliation đã kiểm tra đúng contract chưa?

Một processor đáng tin cậy không chỉ trả ra dữ liệu “đẹp”, mà còn làm rõ **vì sao item được chấp nhận, bị loại hay phải được xử lý thủ công**, và giữ quyết định đó nhất quán trong vòng đời của một Spring Batch job.

## 22. Tài liệu tham khảo

- [Spring Batch Reference — Item Processing](https://docs.spring.io/spring-batch/reference/processor.html): `ItemProcessor`, filtering và transformation.
- [Spring Batch Reference — Validating Input](https://docs.spring.io/spring-batch/reference/processor.html): validation trong processing pipeline.
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): chunk và transaction boundaries.
- [Spring Batch Reference — Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): fault-tolerant skip configuration.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry và backoff.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): lưu/khôi phục state.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest` và hỗ trợ test job/step.
- [Spring Batch API — CompositeItemProcessor](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/item/support/CompositeItemProcessor.html): nối các processors theo thứ tự.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraint validation.
