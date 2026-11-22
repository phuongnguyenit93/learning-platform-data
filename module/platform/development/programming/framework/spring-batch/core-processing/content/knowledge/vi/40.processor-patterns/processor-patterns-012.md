# Kiểm thử processor chain

Trong Spring Batch, một processor chain gồm nhiều `ItemProcessor` được nối theo thứ tự: output của processor trước trở thành input của processor sau. `CompositeItemProcessor` cung cấp cách ghép các delegate đó thành một processor duy nhất để Step sử dụng. Khi kiểm thử chain, cần xác nhận từng delegate nhận đúng dữ liệu, thứ tự xử lý chính xác, kết quả cuối đúng hợp đồng, và các nhánh dừng như `null` hoặc exception có hành vi như mong đợi.

Một test chỉ gọi processor cuối hoặc chỉ chạy Job đến trạng thái `COMPLETED` chưa đủ để chứng minh chain được cấu hình đúng. Chain có thể trả kết quả tình cờ đúng dù một delegate không được gọi, thứ tự bị đảo, một bước mapping bị bỏ qua hoặc lỗi bị xử lý sai. Nên chia kiểm thử thành ba lớp: unit test cho từng delegate, unit test cho `CompositeItemProcessor` để xác nhận composition, và integration test qua Step để kiểm tra wiring, filtering, retry/skip cùng output thực tế.

## 1. Processor chain là gì?

Một `ItemProcessor<I, O>` nhận một item và trả về item đã xử lý. Chain kết hợp nhiều processor với các kiểu trung gian khác nhau:

```text
OrderInput
    |
    v
NormalizeOrderProcessor
    |  OrderInput -> NormalizedOrder
    v
ValidateOrderProcessor
    |  NormalizedOrder -> ValidatedOrder
    v
EnrichOrderProcessor
    |  ValidatedOrder -> EnrichedOrder
    v
MapExportProcessor
    |  EnrichedOrder -> OrderExport
    v
OrderExport
```

Mỗi delegate có một trách nhiệm rõ. Processor normalize chuẩn hóa input; processor validate kiểm tra quy tắc nghiệp vụ; processor enrich bổ sung dữ liệu; processor cuối chuyển sang model mà writer cần.

`CompositeItemProcessor<I, O>` triển khai `ItemProcessor<I, O>` và lần lượt gọi các delegate đã cấu hình. Step chỉ cần khai báo composite như processor của mình. Nhờ vậy, logic ghép chuỗi được kiểm tra riêng với logic đọc/ghi dữ liệu.

## 2. Phân biệt test delegate và test composite

Hai loại test trả lời hai câu hỏi khác nhau:

| Loại test | Câu hỏi chính | Ví dụ assertion |
|---|---|---|
| Delegate unit test | Một processor riêng có xử lý đúng input không? | Chuẩn hóa mã đơn hàng, từ chối amount âm, map đúng field. |
| Composite unit test | Các processor có được gọi đúng thứ tự và truyền output đúng cách không? | Delegate B nhận chính xác output của A; kết quả cuối là output của C. |
| Step integration test | Spring Batch có wiring và điều phối chain đúng trong chunk không? | Writer nhận đúng item, filter/skip/retry counters đúng. |

Nếu chỉ kiểm thử delegate, chain có thể wiring nhầm thứ tự hoặc bỏ sót một bước. Nếu chỉ kiểm thử composite bằng mock, nghiệp vụ bên trong delegate chưa được kiểm tra. Nếu chỉ kiểm thử Job end-to-end, test có thể khó chỉ ra lỗi nằm ở mapping, chain hay reader/writer.

## 3. Xây dựng ví dụ domain cho chain

Giả sử một Step xuất dữ liệu đơn hàng. Các kiểu trung gian thể hiện rõ input/output của từng bước:

```java
public record OrderInput(
        String orderId,
        String customerCode,
        String amountText) {
}

public record NormalizedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record ValidatedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record EnrichedOrder(
        String orderId,
        String customerName,
        BigDecimal amount) {
}

public record OrderExport(
        String orderId,
        String customerName,
        BigDecimal amount) {
}
```

Mỗi record là một dạng dữ liệu tại một ranh giới cụ thể của chain. Dùng kiểu trung gian riêng giúp compiler phát hiện khi output của delegate này không tương thích input của delegate kế tiếp.

## 4. Các delegate trong ví dụ

Processor đầu tiên chuẩn hóa dữ liệu:

```java
public class NormalizeOrderProcessor
        implements ItemProcessor<OrderInput, NormalizedOrder> {

    @Override
    public NormalizedOrder process(OrderInput input) {
        return new NormalizedOrder(
                input.orderId().trim(),
                input.customerCode().trim().toUpperCase(Locale.ROOT),
                new BigDecimal(input.amountText().trim()));
    }
}
```

Processor tiếp theo kiểm tra nghiệp vụ:

```java
public class ValidateOrderProcessor
        implements ItemProcessor<NormalizedOrder, ValidatedOrder> {

    @Override
    public ValidatedOrder process(NormalizedOrder order) {
        if (order.amount().signum() <= 0) {
            throw new InvalidOrderException(order.orderId());
        }

        return new ValidatedOrder(
                order.orderId(),
                order.customerCode(),
                order.amount());
    }
}
```

Processor enrichment tra cứu tên khách hàng:

```java
public class EnrichOrderProcessor
        implements ItemProcessor<ValidatedOrder, EnrichedOrder> {

    private final CustomerService customerService;

    public EnrichOrderProcessor(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Override
    public EnrichedOrder process(ValidatedOrder order) {
        String name = customerService.findName(order.customerCode());
        return new EnrichedOrder(order.orderId(), name, order.amount());
    }
}
```

Processor cuối map sang output:

```java
public class MapOrderExportProcessor
        implements ItemProcessor<EnrichedOrder, OrderExport> {

    @Override
    public OrderExport process(EnrichedOrder order) {
        return new OrderExport(
                order.orderId(),
                order.customerName(),
                order.amount());
    }
}
```

Các class được viết ngắn để minh họa hợp đồng. Trong ứng dụng thật, mỗi delegate có thể inject validator, repository hoặc API client riêng; unit test của delegate nên mock các collaborator đó.

## 5. Cấu hình CompositeItemProcessor

Có thể ghép các delegate bằng builder:

```java
@Bean
ItemProcessor<OrderInput, OrderExport> orderProcessor(
        NormalizeOrderProcessor normalize,
        ValidateOrderProcessor validate,
        EnrichOrderProcessor enrich,
        MapOrderExportProcessor map) throws Exception {

    return new CompositeItemProcessorBuilder<OrderInput, OrderExport>()
            .delegates(List.of(normalize, validate, enrich, map))
            .build();
}
```

Danh sách `delegates` chính là thứ tự thực thi. Builder kiểm tra một số điều kiện cấu hình và tạo composite. Trong ví dụ, output type của `normalize` tương thích input type của `validate`, rồi tiếp tục qua các bước sau.

Nếu khai báo các delegate trực tiếp trong cấu hình Step, test cấu hình có thể khó đọc hơn. Một bean composite riêng cho phép unit test lấy đúng chain production và Step chỉ cần inject một `ItemProcessor<OrderInput, OrderExport>`.

## 6. Test đơn vị cho từng delegate

Delegate nên được kiểm thử độc lập với composite. Ví dụ test normalize:

```java
class NormalizeOrderProcessorTest {

    private final NormalizeOrderProcessor processor =
            new NormalizeOrderProcessor();

    @Test
    void trimsFieldsAndNormalizesCustomerCode() throws Exception {
        OrderInput input = new OrderInput(
                " O-100 ", " cust-7 ", " 125.50 ");

        NormalizedOrder result = processor.process(input);

        assertThat(result).isEqualTo(new NormalizedOrder(
                "O-100",
                "CUST-7",
                new BigDecimal("125.50")));
    }
}
```

Test này xác nhận behavior của normalize mà không cần tạo Step hoặc JobRepository. Với processor có dependency, mock collaborator và xác nhận input gửi đến dependency cùng output được trả về.

Ví dụ test enrichment:

```java
@Test
void enrichesOrderWithCustomerName() throws Exception {
    CustomerService customerService = mock(CustomerService.class);
    EnrichOrderProcessor processor =
            new EnrichOrderProcessor(customerService);

    ValidatedOrder input = new ValidatedOrder(
            "O-100", "CUST-7", new BigDecimal("125.50"));
    when(customerService.findName("CUST-7")).thenReturn("Lan Nguyen");

    EnrichedOrder result = processor.process(input);

    assertThat(result).isEqualTo(new EnrichedOrder(
            "O-100", "Lan Nguyen", new BigDecimal("125.50")));
    verify(customerService).findName("CUST-7");
    verifyNoMoreInteractions(customerService);
}
```

Test delegate nên bao gồm input hợp lệ, input biên, dữ liệu không hợp lệ và lỗi từ dependency nếu những trường hợp đó thuộc trách nhiệm của processor.

## 7. Test composite với delegate mock

Để kiểm tra composition, có thể mock từng `ItemProcessor` và thiết lập output cho từng bước:

```java
@Test
void passesOutputOfEachDelegateToTheNextDelegate() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<OrderInput, NormalizedOrder> normalize =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<NormalizedOrder, ValidatedOrder> validate =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<ValidatedOrder, EnrichedOrder> enrich =
            mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<EnrichedOrder, OrderExport> map =
            mock(ItemProcessor.class);

    OrderInput input = new OrderInput(" O-100 ", " cust-7 ", "125.50");
    NormalizedOrder normalized = new NormalizedOrder(
            "O-100", "CUST-7", new BigDecimal("125.50"));
    ValidatedOrder validated = new ValidatedOrder(
            "O-100", "CUST-7", new BigDecimal("125.50"));
    EnrichedOrder enriched = new EnrichedOrder(
            "O-100", "Lan Nguyen", new BigDecimal("125.50"));
    OrderExport expected = new OrderExport(
            "O-100", "Lan Nguyen", new BigDecimal("125.50"));

    when(normalize.process(input)).thenReturn(normalized);
    when(validate.process(normalized)).thenReturn(validated);
    when(enrich.process(validated)).thenReturn(enriched);
    when(map.process(enriched)).thenReturn(expected);

    CompositeItemProcessor<OrderInput, OrderExport> composite =
            new CompositeItemProcessorBuilder<OrderInput, OrderExport>()
                    .delegates(List.of(normalize, validate, enrich, map))
                    .build();

    assertThat(composite.process(input)).isEqualTo(expected);

    InOrder order = inOrder(normalize, validate, enrich, map);
    order.verify(normalize).process(input);
    order.verify(validate).process(normalized);
    order.verify(enrich).process(validated);
    order.verify(map).process(enriched);
    verifyNoMoreInteractions(normalize, validate, enrich, map);
}
```

Test xác nhận composite truyền đúng object output của từng delegate sang delegate kế tiếp và gọi các delegate theo thứ tự. `InOrder` làm rõ thứ tự invocation; assertion kết quả cuối xác nhận output chain được trả về cho caller.

Nếu project dùng Java version không hỗ trợ `record`, có thể thay các record bằng immutable class/POJO; ý nghĩa test không thay đổi.

## 8. Xác nhận delegate không bị bỏ qua hoặc gọi thừa

Một lỗi wiring có thể khiến chain chỉ gọi ba trong bốn delegate hoặc vô tình thêm một delegate hai lần. `InOrder` kết hợp `verifyNoMoreInteractions` giúp phát hiện những trường hợp này.

Nếu một delegate là optional theo cấu hình, test cần thể hiện rõ chain variant nào đang được kiểm tra. Không nên viết một assertion chung chỉ kiểm tra output cuối mà không xác nhận các bước quan trọng đã chạy.

Khi delegate có side effect, verify collaborator của delegate được gọi đúng số lần. Ví dụ `EnrichOrderProcessor` gọi `CustomerService` một lần cho mỗi item. Nếu chain xử lý một item mà service bị gọi hai lần, test có thể phát hiện regression làm tăng query/API traffic.

## 9. Kiểm thử thứ tự chain bằng giá trị biến đổi

Ngoài mock, có thể dùng processor thật với các phép biến đổi đơn giản để chứng minh thứ tự có ý nghĩa:

```java
@Test
void executesProcessorsInConfiguredOrder() throws Exception {
    ItemProcessor<String, String> trim = String::trim;
    ItemProcessor<String, String> uppercase = String::toUpperCase;
    ItemProcessor<String, String> addPrefix = value -> "ORDER-" + value;

    CompositeItemProcessor<String, String> composite =
            new CompositeItemProcessorBuilder<String, String>()
                    .delegates(List.of(trim, uppercase, addPrefix))
                    .build();

    assertThat(composite.process("  ab-10  "))
            .isEqualTo("ORDER-AB-10");
}
```

Nếu đảo `trim` và `uppercase`, kết quả ví dụ này vẫn có thể giống nhau; vì vậy, hãy chọn transformation mà thứ tự thực sự ảnh hưởng đến kết quả hoặc dùng mock `InOrder`. Không dùng một input không phân biệt được thứ tự rồi kết luận chain đúng.

## 10. Kiểu input/output giữa các delegate

Chain có thể gồm các kiểu trung gian khác nhau. Compiler kiểm tra generic ở thời điểm compile nếu khai báo type rõ:

```java
ItemProcessor<OrderInput, NormalizedOrder> normalize = ...;
ItemProcessor<NormalizedOrder, ValidatedOrder> validate = ...;
ItemProcessor<ValidatedOrder, OrderExport> map = ...;
```

Một lỗi cấu hình phổ biến là delegate thứ hai mong đợi `String` nhưng delegate đầu trả `NormalizedOrder`, hoặc delegate cuối trả một kiểu writer không chấp nhận. Hãy tránh raw type và cast không cần thiết trong cấu hình production.

Compile-time type safety không chứng minh runtime mapping đúng. Một processor có thể tạo object hợp lệ về kiểu nhưng gán sai field. Vì vậy, unit test từng delegate vẫn cần assert toàn bộ dữ liệu có ý nghĩa.

## 11. Kiểm thử khi delegate trả null

Theo contract của Spring Batch, processor trả `null` có nghĩa item bị filter và không được chuyển tiếp đến writer. Trong `CompositeItemProcessor`, khi một delegate trả `null`, chain dừng ở đó; các delegate còn lại không được gọi.

Ví dụ test:

```java
@Test
void nullFromDelegateStopsTheRemainingChain() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> normalize = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> filter = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> map = mock(ItemProcessor.class);

    when(normalize.process("input")).thenReturn("normalized");
    when(filter.process("normalized")).thenReturn(null);

    CompositeItemProcessor<String, String> composite =
            new CompositeItemProcessorBuilder<String, String>()
                    .delegates(List.of(normalize, filter, map))
                    .build();

    assertThat(composite.process("input")).isNull();

    InOrder order = inOrder(normalize, filter);
    order.verify(normalize).process("input");
    order.verify(filter).process("normalized");
    verifyNoInteractions(map);
}
```

Test này quan trọng vì một delegate sau có thể tạo side effect hoặc gọi service bên ngoài. Nếu item đã bị filter, delegate đó không được chạy.

## 12. Phân biệt null filter với exception

`null` là tín hiệu filter theo contract processor. Exception là lỗi xử lý và được Spring Batch xử lý theo fault-tolerance policy của Step.

| Kết quả delegate | Hành vi chain | Hành vi thường thấy ở Step |
|---|---|---|
| Trả object | Truyền object sang delegate tiếp theo | Tiếp tục đến writer. |
| Trả `null` | Dừng chain cho item hiện tại | Tăng filter count; writer không nhận item đó. |
| Ném exception | Chain dừng do lỗi | Rollback/retry/skip/fail theo cấu hình. |

Không dùng `null` để biểu diễn lỗi hệ thống như database unavailable hoặc API timeout. Làm vậy sẽ biến lỗi thành filter âm thầm và khiến dữ liệu bị mất khỏi output mà không có skip record rõ ràng.

## 13. Kiểm thử exception từ một delegate

Nếu delegate ở giữa chain ném exception, các delegate sau không được gọi và exception phải được truyền ra ngoài:

```java
@Test
void exceptionStopsTheChainAndPropagates() throws Exception {
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> first = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> second = mock(ItemProcessor.class);
    @SuppressWarnings("unchecked")
    ItemProcessor<String, String> third = mock(ItemProcessor.class);

    RuntimeException failure = new IllegalStateException("validation failed");
    when(first.process("input")).thenReturn("normalized");
    when(second.process("normalized")).thenThrow(failure);

    CompositeItemProcessor<String, String> composite =
            new CompositeItemProcessorBuilder<String, String>()
                    .delegates(List.of(first, second, third))
                    .build();

    assertThatThrownBy(() -> composite.process("input"))
            .isSameAs(failure);

    verify(first).process("input");
    verify(second).process("normalized");
    verifyNoInteractions(third);
}
```

Test nên đặt exception ở đầu, giữa và cuối chain nếu các vị trí đó có semantics hoặc side effect khác nhau. Thường chỉ cần một test đại diện cho cơ chế propagation của composite và các test riêng cho business exception của delegate, nhưng phải bảo đảm các bước sau không chạy sau lỗi.

## 14. Kiểm thử chain rỗng và cấu hình thiếu

Một chain rỗng hoặc thiếu delegate bắt buộc thường là lỗi cấu hình ứng dụng, không phải tình huống nghiệp vụ bình thường. Hãy quyết định rõ chain có được phép không có delegate không.

Với một chain bắt buộc có normalize, validate và map, nên kiểm tra cấu hình tạo composite nhận đủ delegate. Có thể kiểm tra application context khởi tạo thành công và bean composite tồn tại.

Không nên tạo một test phức tạp chỉ để xác nhận behavior implementation nội bộ của builder đối với danh sách rỗng nếu ứng dụng không hỗ trợ cấu hình đó. Thay vào đó, bảo đảm factory/configuration của ứng dụng không tạo danh sách rỗng ngoài ý muốn và fail sớm với thông báo rõ.

## 15. Test cấu hình bean production

Unit test tự dựng composite giúp kiểm tra semantics nhưng có thể không phát hiện bean production đã cấu hình sai thứ tự hoặc inject nhầm delegate. Một test Spring context nhỏ có thể lấy đúng bean composite:

```java
@SpringJUnitConfig(BatchProcessorConfiguration.class)
class OrderProcessorConfigurationTest {

    @Autowired
    ItemProcessor<OrderInput, OrderExport> orderProcessor;

    @Test
    void configuredChainProducesExpectedExport() throws Exception {
        OrderInput input = new OrderInput(
                " O-100 ", " cust-7 ", "125.50");

        OrderExport result = orderProcessor.process(input);

        assertThat(result.orderId()).isEqualTo("O-100");
        assertThat(result.customerName()).isEqualTo("Lan Nguyen");
        assertThat(result.amount()).isEqualByComparingTo("125.50");
    }
}
```

Test cần cung cấp fixture/customer service phù hợp, chẳng hạn bean test hoặc database test. Mục tiêu là lấy bean production để xác nhận danh sách delegate được wiring đúng, không phải tạo một composite khác trong test.

Nếu chain phụ thuộc `@StepScope`, bean có thể cần StepScope context khi gọi. Trong trường hợp đó, dùng `StepScopeTestExecutionListener` hoặc `StepScopeTestUtils` để tạo StepExecution context cho test, hoặc kiểm tra chain ở cấp Step integration.

## 16. Kiểm thử processor có @StepScope

Một delegate có thể đọc JobParameters hoặc StepExecutionContext qua `@Value`. Unit test gọi bean ngoài StepScope có thể gặp lỗi scope chưa active.

Ví dụ:

```java
@Bean
@StepScope
ItemProcessor<OrderInput, NormalizedOrder> normalizeProcessor(
        @Value("#{jobParameters['tenant.id']}") Long tenantId,
        TenantConfigurationService configurationService) {

    return input -> normalize(input, tenantId, configurationService);
}
```

Khi test, cần tạo StepExecution có JobParameters chứa `tenant.id` và đăng ký scope test. Không mock toàn bộ scope rồi bỏ qua việc kiểm tra parameter nếu logic phụ thuộc tenant.

Với Spring Batch Test, `StepScopeTestExecutionListener` có thể cung cấp StepExecution cho test method theo quy ước framework. `StepScopeTestUtils.doInStepScope(...)` cho phép chạy một đoạn code trong StepScope context được cung cấp. Chọn cách phù hợp với phiên bản Spring Batch của dự án.

## 17. Integration test qua Step

Sau unit test, cần một integration test xác nhận Step sử dụng composite đúng cách. Có thể dùng `@SpringBatchTest`, `JobLauncherTestUtils` và fixture reader/writer nhỏ.

Ví dụ cấu trúc test:

```java
@SpringBatchTest
@SpringJUnitConfig(OrderBatchTestConfiguration.class)
class OrderExportStepTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void stepRunsConfiguredProcessorChain() throws Exception {
        JobExecution execution = jobLauncherTestUtils.launchStep(
                "exportOrdersStep",
                new JobParametersBuilder()
                        .addString("test.run", UUID.randomUUID().toString())
                        .toJobParameters());

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

        StepExecution stepExecution = execution.getStepExecutions()
                .iterator().next();
        assertThat(stepExecution.getReadCount()).isEqualTo(2);
        assertThat(stepExecution.getWriteCount()).isEqualTo(2);
    }
}
```

Đây là khung minh họa. Test configuration cần tạo Step có tên `exportOrdersStep`, reader trả hai item và writer quan sát output. Nếu dùng `launchStep`, `JobLauncherTestUtils` phải được cấu hình với Job/Step tương ứng theo version. Nếu muốn kiểm tra cả flow Job, dùng `launchJob`.

Không chỉ assert `BatchStatus.COMPLETED`. Hãy xác nhận output writer nhận đúng record và dữ liệu cuối phản ánh từng bước trong chain.

## 18. Kiểm tra output writer

Một writer test có thể lưu item nhận được để assertion:

```java
class CollectingOrderWriter implements ItemWriter<OrderExport> {

    private final List<OrderExport> written = new ArrayList<>();

    @Override
    public void write(Chunk<? extends OrderExport> chunk) {
        written.addAll(chunk.getItems());
    }

    List<OrderExport> writtenItems() {
        return List.copyOf(written);
    }
}
```

Trong integration test, inject writer test hoặc dùng repository/output file thật tùy mục tiêu. Assertion nên so sánh business key, field đã normalize/enrich và thứ tự output nếu thứ tự là một phần hợp đồng.

Nếu writer được gọi nhiều chunk, `write` có thể được gọi nhiều lần; không giả định một invocation duy nhất cho toàn Step. Test phải gom item qua các chunk hoặc xác nhận từng chunk đúng cách.

## 19. Kiểm thử filter count

Một delegate có thể trả `null` để loại item. Integration test nên xác nhận item đó không tới writer và `filterCount` phản ánh đúng:

```java
assertThat(stepExecution.getReadCount()).isEqualTo(3);
assertThat(stepExecution.getFilterCount()).isEqualTo(1);
assertThat(stepExecution.getWriteCount()).isEqualTo(2);
```

Các con số trên giả định cả ba item đều được đọc, một item bị filter và hai item còn lại được ghi thành công, không có skip hoặc retry làm thay đổi counters.

Hãy kiểm tra writer không nhận item bị filter. Chỉ nhìn `filterCount` có thể chưa phát hiện writer hoặc side effect ngoài ý muốn ở một delegate đã chạy trước điểm filter.

## 20. Kiểm thử retry khi delegate ném exception

Nếu exception từ delegate được cấu hình retry, Step có thể gọi lại processing cho item theo fault-tolerance behavior. Test cần xác nhận:

- Exception thuộc loại được retry.
- Retry limit được áp dụng đúng.
- Lần thử lại có thể thành công hoặc cuối cùng thất bại theo fixture.
- Các delegate trước điểm lỗi có thể được gọi lại; không giả định chỉ delegate lỗi chạy lại.
- Side effect của các delegate trước đó an toàn khi xử lý lại.

Ví dụ processor đầu gọi API và processor sau thất bại: retry cả chain có thể gọi API đầu nhiều lần. Nếu API có side effect, hãy dùng idempotency key hoặc tách side effect sang bước phù hợp.

Không chỉ kiểm tra số lần gọi delegate ném exception. Hãy kiểm tra số lần gọi các delegate trước nó và xác nhận chain không để lại trạng thái mutable sai giữa các attempt.

## 21. Kiểm thử skip policy

Nếu Step skip một loại exception phát sinh từ chain, item bị lỗi sẽ không được ghi và Step tiếp tục theo policy. Có thể dùng `SkipListener` để xác nhận item và exception được ghi nhận:

```java
@Bean
SkipListener<OrderInput, OrderExport> orderSkipListener(
        RejectedOrderRepository rejectedOrders) {

    return new SkipListener<>() {
        @Override
        public void onSkipInProcess(
                OrderInput item,
                Throwable failure) {
            rejectedOrders.record(item.orderId(), failure.getClass().getSimpleName());
        }
    };
}
```

Trong test, xác nhận `processSkipCount`, item reject được lưu đúng và các item hợp lệ khác vẫn tới writer. Không nên skip mọi exception chung chung; cấu hình loại exception theo nghiệp vụ và phân biệt lỗi dữ liệu với lỗi hệ thống tạm thời.

## 22. Listener quan sát processor chain

`ItemProcessListener<I, O>` được gắn với processor mà Step sử dụng. Nếu Step sử dụng `CompositeItemProcessor`, listener ở cấp Step quan sát composite như một processor; nó không tự tạo callback riêng cho từng delegate bên trong.

Nếu cần đo thời gian hoặc log theo từng delegate, có thể:

- Bọc từng delegate bằng decorator đo thời gian.
- Ghi metric trong từng processor.
- Dùng collaborator quan sát được trong unit test.
- Gắn branch/step name vào structured log.

Ví dụ decorator:

```java
public class TimingProcessor<I, O> implements ItemProcessor<I, O> {

    private final String name;
    private final ItemProcessor<I, O> delegate;
    private final Timer timer;

    public TimingProcessor(
            String name,
            ItemProcessor<I, O> delegate,
            MeterRegistry registry) {
        this.name = name;
        this.delegate = delegate;
        this.timer = Timer.builder("batch.processor.duration")
                .tag("processor", name)
                .register(registry);
    }

    @Override
    public O process(I item) throws Exception {
        return timer.recordCallable(() -> delegate.process(item));
    }
}
```

Decorator cần giữ nguyên semantics của delegate, bao gồm trả `null` và propagate exception. Khi bọc delegate bằng wrapper, bảo đảm các stream/listener lifecycle khác (nếu delegate có triển khai `ItemStream`) được chuyển tiếp hoặc đăng ký riêng.

## 23. Test side effect và idempotency trong chain

Một processor lý tưởng thường biến đổi item và trả output. Nhưng thực tế có thể có delegate gọi API, ghi audit hoặc cập nhật database. Nếu Step retry, processor có thể chạy lại và lặp side effect.

Test cần xác nhận:

- Cùng business item được retry không tạo giao dịch/API trùng ngoài ý muốn.
- Idempotency key ổn định giữa các attempt.
- Audit không ghi thành công trước khi chunk commit nếu nghiệp vụ yêu cầu atomicity.
- Delegate không giữ mutable state theo item trong field singleton.
- Nếu delegate được gọi lại, output vẫn xác định hoặc lỗi được xử lý rõ.

Ví dụ test service nhận idempotency key:

```java
verify(paymentGateway, times(1)).submit(
        eq("order-O-100"),
        any(PaymentRequest.class));
```

Trong integration test có retry, assertion nên kiểm tra số operation thực sự được commit/accept, không chỉ số lần processor method được gọi.

## 24. Test null input và validation boundary

Nếu reader có thể trả `null`, cần xác định contract của reader/processor. Trong Spring Batch, `ItemReader.read()` trả `null` để báo hết dữ liệu; `ItemProcessor` thông thường không được gọi với một item null như một record hợp lệ.

Nếu một field bên trong item null, test riêng cách delegate xử lý field đó. Đừng nhầm `read() == null` (EOF) với `process(item) == null` (filter item).

Ví dụ:

```java
@Test
void missingCustomerCodeIsRejected() {
    OrderInput input = new OrderInput("O-100", null, "125.50");

    assertThatThrownBy(() -> normalizeProcessor.process(input))
            .isInstanceOf(InvalidOrderException.class);
}
```

Nếu policy nghiệp vụ yêu cầu filter thay vì reject, processor có thể trả null; integration test cần xác nhận filter count và không có output.

## 25. Test dữ liệu thay đổi giữa các delegate

Processor chain chạy tuần tự trên cùng item reference/value. Nếu delegate dùng object mutable, bước trước có thể thay đổi object mà bước sau nhận. Điều này đôi khi là chủ đích, nhưng có thể tạo coupling khó thấy.

Ưu tiên immutable DTO/record làm kiểu trung gian. Nếu dùng mutable object, test cần xác nhận field nào được thay đổi và delegate sau quan sát giá trị nào.

Ví dụ lỗi có thể xảy ra khi processor normalize sửa object input dùng chung trong cache hoặc field singleton. Test với hai item liên tiếp giúp phát hiện dữ liệu của item trước rò sang item sau.

Không lưu `currentItem`, `currentCustomer` hoặc accumulator của một item vào field mutable của processor singleton nếu không có lifecycle/reset và concurrency contract rõ.

## 26. Test concurrency khi Step chạy nhiều thread

`CompositeItemProcessor` gọi delegate tuần tự cho từng item; bản thân chain không làm các delegate của một item chạy song song. Tuy nhiên, multi-threaded Step có thể gọi cùng composite/delegate instance từ nhiều thread tùy cấu hình.

Kiểm thử concurrency khi:

- Step dùng task executor cho chunk/item processing.
- Nhiều Job/Step dùng chung bean singleton.
- Delegate có cache hoặc state mutable.
- Collaborator không thread-safe.
- Có side effect hoặc thứ tự nghiệp vụ phụ thuộc item.

Test nên gửi nhiều item khác nhau đồng thời và xác nhận output không trộn field/correlation ID. Nếu delegate không thread-safe, dùng scope phù hợp, stateless design, thread-safe collaborator hoặc điều chỉnh concurrency.

Không giả định vì chain chạy tuần tự trong một item nên toàn bộ bean chỉ được một thread truy cập tại một thời điểm.

## 27. Kiểm thử chain có nhiều bước lọc

Nếu nhiều delegate có thể trả null, hãy test vị trí filter khác nhau:

```text
Input -> Normalize -> Validate -> Enrich -> Map
              |          |         |
              |          |         +--> null: không gọi Map
              |          +------------> null: không gọi Enrich/Map
              +-----------------------> null: không gọi Validate/Enrich/Map
```

Không nhất thiết phải nhân bản mọi test nếu semantics composite giống nhau, nhưng mỗi delegate có logic filter cần có unit test riêng. Một composite test đại diện xác nhận short-circuit; Step integration test xác nhận filter count tổng hợp đúng.

Nếu chain có side effect trước bước filter, hãy xem xét di chuyển filter/validation lên trước side effect để tránh gọi API hoặc ghi audit cho item cuối cùng bị loại.

## 28. Kiểm thử lỗi mapping giữa các kiểu trung gian

Một chain có thể compile nhưng mapping field sai. Ví dụ processor enrich nhận customer code đúng nhưng tạo `EnrichedOrder` với `orderId` của item trước do dùng mutable cache.

Unit test nên kiểm tra:

- Mỗi field output lấy từ đúng input field.
- BigDecimal không bị chuyển qua `double` gây sai precision.
- Date/time giữ timezone và format được yêu cầu.
- Null/blank có semantics rõ.
- Identifier không bị thay đổi ngoài ý muốn.
- Mapping không làm mất field cần thiết cho delegate kế tiếp.

Với mapping phức tạp, dùng fixture có giá trị khác nhau ở mọi field để phát hiện gán nhầm. Tránh test chỉ dùng cùng một giá trị cho nhiều field vì mapping sai vẫn có thể pass.

## 29. Kiểm thử thứ tự side effect và thứ tự output

Thứ tự delegate trong một item là cố định theo danh sách cấu hình. Thứ tự giữa các item phụ thuộc reader, chunking và concurrency của Step.

Nếu nghiệp vụ yêu cầu thứ tự xử lý item toàn cục, cần cấu hình Step/partition phù hợp và kiểm thử ở cấp Step. `CompositeItemProcessor` không bảo đảm item 1 hoàn tất toàn bộ chain trước khi item 2 bắt đầu trong mọi cấu hình concurrent.

Nếu chỉ cần thứ tự output theo sort key, hãy bảo đảm reader có sort ổn định và writer không reorder. Test output bằng danh sách business key, không chỉ so sánh tổng số item.

## 30. Test chain với Spring Batch Test

Spring Batch Test cung cấp tiện ích để chạy Job/Step trong integration test. Một cấu hình thường gồm:

- `@SpringBatchTest` để đăng ký test utilities/listeners.
- `@SpringJUnitConfig` hoặc Spring test context tương ứng.
- `JobLauncherTestUtils` để launch Job hoặc Step.
- `JobRepositoryTestUtils` để dọn metadata giữa test nếu phù hợp.
- StepScope test support nếu reader/processor/writer dùng `@StepScope`.

Ví dụ kiểm tra cả flow:

```java
@SpringBatchTest
@SpringJUnitConfig(OrderJobTestConfiguration.class)
class OrderJobProcessorChainTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    OrderExportRepository exportRepository;

    @Test
    void jobWritesExpectedResultsFromProcessorChain() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("test.run.id", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(exportRepository.findAllForTestRun(parameters))
                .containsExactly(
                        new OrderExport("O-100", "Lan Nguyen",
                                new BigDecimal("125.50")));
    }
}
```

Tên repository/helper trong ví dụ là thành phần test của ứng dụng. Nếu writer ghi file, thay assertion repository bằng đọc và parse file staging. JobParameters cần bảo đảm JobInstance riêng cho từng test để metadata không xung đột.

## 31. Test restart khi chain đã xử lý một phần

Restart test hữu ích nếu delegate có state, side effect hoặc processor chain có lỗi có thể retry/skip. Kịch bản:

1. Seed input có nhiều item với business ID xác định.
2. Launch Job lần đầu và làm Step fail sau một số chunk đã commit.
3. Xác nhận các item đã commit có output đúng.
4. Restart cùng JobInstance với cùng identifying parameters.
5. Xác nhận reader tiếp tục đúng checkpoint.
6. Xác nhận chain xử lý các item còn lại theo đúng thứ tự delegate.
7. Xác nhận không có output trùng hoặc thiếu.
8. Xác nhận side effect của delegate trước/sau failure tuân thủ idempotency policy.

Nếu processor chain stateless và không có side effect, restart test có thể tập trung vào Step wiring/output. Nếu delegate có cache/state hoặc gọi hệ thống ngoài, cần kiểm tra cả lifecycle và recovery.

## 32. Ma trận test đề xuất

Một bộ test thực tế có thể dùng ma trận sau:

| Lớp | Trường hợp | Điều cần xác nhận |
|---|---|---|
| Delegate unit | Input hợp lệ | Output và field mapping chính xác. |
| Delegate unit | Input biên/không hợp lệ | Validation, exception hoặc filter đúng contract. |
| Delegate unit | Collaborator lỗi | Exception được propagate hoặc chuyển đổi có chủ đích. |
| Composite unit | Chain thành công | Đúng thứ tự và đúng object được truyền giữa các bước. |
| Composite unit | Delegate trả null | Dừng chain, delegate sau không chạy. |
| Composite unit | Delegate ném exception | Dừng chain, exception được truyền ra. |
| Composite unit | Delegate gọi side effect | Số lần và thứ tự collaborator call đúng. |
| Context test | Bean production | Đúng delegate và thứ tự được wiring. |
| Step integration | Chunk thành công | Writer nhận output đúng. |
| Step integration | Filter | `filterCount`, `writeCount` và output đúng. |
| Step integration | Retry/skip | Counters, listener và trạng thái Step đúng. |
| Restart integration | Fail giữa Job | Không thiếu/trùng output và side effect an toàn. |
| Concurrency test | Nhiều item đồng thời | Không rò state giữa item. |

Không phải dự án nào cũng cần mọi dòng. Chọn test dựa trên rủi ro và trách nhiệm thực tế của delegate, nhưng luôn có ít nhất một test cho từng delegate quan trọng và một test xác nhận composition.

## 33. Những lỗi thường gặp khi kiểm thử processor chain

### Chỉ test kết quả cuối

Output tình cờ đúng dù một delegate bị bỏ qua hoặc chain sai thứ tự. Verify invocation và giá trị truyền giữa từng bước.

### Chỉ test mock composite

Composition đúng nhưng business logic delegate có thể sai. Viết unit test riêng cho từng delegate.

### Không xác nhận delegate sau không chạy khi filter

Side effect ở bước sau có thể vẫn xảy ra. Dùng `verifyNoInteractions` hoặc verify không có invocation.

### Coi null là exception

Null là filter theo contract processor. Exception là lỗi xử lý và đi qua fault-tolerance policy.

### Retry chỉ test số lần gọi processor bị lỗi

Các delegate trước điểm lỗi có thể chạy lại. Kiểm tra side effect và idempotency của cả chain.

### Dùng raw generic type

Compiler mất khả năng phát hiện type mismatch giữa delegate. Khai báo input/output type cụ thể.

### Tự dựng chain khác production trong test

Test pass nhưng bean thật có thể inject nhầm thứ tự. Thêm test lấy bean composite production từ Spring context.

### Bỏ qua StepScope

Test bean `@StepScope` ngoài context có thể không phản ánh JobParameters/ExecutionContext. Tạo StepExecution test context.

### Chỉ assert BatchStatus

Job `COMPLETED` chưa chứng minh output đúng. Assert writer output, counters và business key.

### Dùng processor mutable state trong singleton

Item trước có thể ảnh hưởng item sau hoặc thread khác. Ưu tiên processor stateless và immutable intermediate data.

### Không test concurrency khi dùng multi-threaded Step

Chain tuần tự theo delegate nhưng cùng instance có thể được gọi đồng thời cho nhiều item. Kiểm tra thread safety của mọi delegate/collaborator.

## 34. Quy trình kiểm thử processor chain

Khi xây dựng hoặc thay đổi một chain, có thể đi theo trình tự:

1. Liệt kê delegate, input type, output type và thứ tự dự kiến.
2. Unit test từng delegate với input hợp lệ, biên và lỗi.
3. Dùng mock để test composite truyền đúng output của bước trước sang bước sau.
4. Dùng `InOrder` để xác nhận invocation theo thứ tự.
5. Test delegate trả `null` và xác nhận chain short-circuit.
6. Test exception và xác nhận delegate sau không chạy.
7. Test side effect, retry và idempotency nếu delegate gọi hệ thống ngoài.
8. Load bean composite production để kiểm tra wiring và StepScope.
9. Integration test Step/Job với writer quan sát được.
10. Kiểm tra filter/skip/retry counters và listener.
11. Test restart nếu Job cần phục hồi sau failure.
12. Test concurrency nếu nhiều item có thể được xử lý đồng thời.

| Câu hỏi | Bằng chứng |
|---|---|
| Mỗi delegate có đúng nghiệp vụ? | Unit test riêng cho delegate. |
| Thứ tự chain có đúng? | `InOrder` và output trung gian cụ thể. |
| Output được truyền đúng? | Verify delegate kế tiếp nhận đúng object. |
| Filter có dừng chain? | Delegate sau không được gọi; Step filter count tăng. |
| Exception có dừng chain? | Exception propagate; delegate sau không chạy. |
| Production wiring có đúng? | Test lấy composite bean từ Spring context. |
| Step ghi đúng kết quả? | Integration test kiểm tra output và counters. |
| Retry có an toàn? | Test side effect, reload/idempotency và retry exhaustion. |

## Kết luận

Kiểm thử processor chain cần xác nhận cả behavior của từng delegate lẫn cách `CompositeItemProcessor` ghép chúng. Hãy kiểm thử delegate độc lập, dùng mock và `InOrder` để chứng minh đúng thứ tự cùng dữ liệu truyền giữa các bước, đồng thời xác nhận `null` dừng chain và exception được propagate. Test bean production và integration test qua Step giúp phát hiện lỗi wiring, StepScope, filter/skip/retry counters và output. Nếu delegate có side effect hoặc Step chạy nhiều thread, cần kiểm tra idempotency, state isolation và thread safety. Một chain chỉ đáng tin khi từng bước đúng, composition đúng và Step sử dụng chain đúng như hợp đồng nghiệp vụ.
