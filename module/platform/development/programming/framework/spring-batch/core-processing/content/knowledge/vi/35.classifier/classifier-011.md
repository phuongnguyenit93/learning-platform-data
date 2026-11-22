# Kiểm thử mọi nhánh classifier

Trong Spring Batch, classifier chọn một xử lý tiếp theo dựa trên đặc điểm của item hoặc kết quả thực thi. Ví dụ, đơn hàng nội địa đi qua processor tính thuế nội địa, đơn hàng quốc tế đi qua processor tính phí xuất khẩu, còn đơn hàng có dữ liệu thiếu được chuyển đến nhánh kiểm tra thủ công.

Một classifier có thể có nhiều nhánh, điều kiện biên và nhánh mặc định. Nếu chỉ kiểm thử một trường hợp thành công, các lỗi như phân loại sai giá trị sát ngưỡng, bỏ quên enum mới, trả về delegate null hoặc chuyển item đến nhầm writer có thể chỉ xuất hiện khi chạy batch thật.

Kiểm thử đầy đủ cần bao phủ hai lớp:

- **Classifier:** với mỗi input, kết quả phân loại có đúng theo quy tắc không?
- **Component được phân nhánh:** processor hoặc writer được chọn có thực sự nhận đúng item và thực hiện đúng hành vi không?

Trong Spring Batch, classifier thường được dùng cùng ClassifierCompositeItemProcessor hoặc ClassifierCompositeItemWriter. Bài này tập trung vào cách kiểm thử từng nhánh, các giá trị biên, fallback, lỗi và hành vi của Step khi nhánh được chọn thất bại.

## 1. Classifier làm gì?

Classifier là một hàm phân loại: nhận một đối tượng đầu vào và trả về một kết quả được chọn dựa trên các điều kiện.

Trong Spring Batch, interface tổng quát có dạng:

~~~java
public interface Classifier<C, T> {
    T classify(C classifiable);
}
~~~

Trong đó:

- C là kiểu dữ liệu đầu vào cần phân loại.
- T là kết quả phân loại, thường là processor, writer hoặc một loại handler.

Ví dụ, phân loại đơn hàng theo giá trị và khu vực:

~~~text
Order
  |
  v
OrderClassifier
  |
  +--> HIGH_VALUE
  |
  +--> INTERNATIONAL
  |
  +--> DOMESTIC
  |
  +--> REVIEW
~~~

Classifier nên chứa quy tắc chọn nhánh rõ ràng và có thể kiểm thử độc lập. Không nên đặt truy vấn database, gọi API hoặc side effect trong hàm classify nếu có thể tránh được. Một classifier thuần, xác định và không có side effect sẽ dễ kiểm thử và ít gây bất ngờ khi Spring Batch gọi lại component.

## 2. Xác định toàn bộ nhánh trước khi viết test

Trước khi tạo test, hãy liệt kê mọi kết quả có thể trả về và điều kiện dẫn đến từng kết quả.

Ví dụ:

| Nhánh | Điều kiện | Xử lý |
| --- | --- | --- |
| HIGH_VALUE | Tổng tiền lớn hơn hoặc bằng ngưỡng | Processor/writer ưu tiên |
| INTERNATIONAL | Không thuộc HIGH_VALUE và loại khách hàng là quốc tế | Xử lý ngoại tệ |
| DOMESTIC | Không thuộc hai nhánh trên và khách hàng nội địa | Xử lý nội địa |
| REVIEW | Dữ liệu thiếu hoặc cần xác minh | Đưa vào hàng chờ kiểm tra |

Bảng này làm rõ thứ tự ưu tiên. Nếu một đơn hàng vừa có giá trị cao vừa là đơn quốc tế, classifier phải chọn nhánh nào? Nếu không quy định thứ tự, hai người có thể viết hai cách phân loại khác nhau và đều nghĩ rằng đúng.

Nên ghi rõ:

- Điều kiện của từng nhánh.
- Thứ tự ưu tiên khi nhiều điều kiện cùng đúng.
- Cách xử lý null và dữ liệu thiếu.
- Nhánh mặc định cho giá trị chưa nhận diện.
- Trường hợp nào phải ném exception thay vì chọn fallback.
- Có nhánh nào không được phép nhận item không?

Không dùng một nhánh mặc định chung cho mọi dữ liệu lỗi nếu việc đó làm che giấu lỗi schema hoặc lỗi nghiệp vụ.

## 3. Viết classifier có kết quả rõ ràng

Ví dụ mô hình dữ liệu:

~~~java
public record Order(
        long orderId,
        String region,
        BigDecimal totalAmount) {
}

public enum OrderRoute {
    HIGH_VALUE,
    INTERNATIONAL,
    DOMESTIC,
    REVIEW
}
~~~

Classifier:

~~~java
public class OrderRouteClassifier
        implements Classifier<Order, OrderRoute> {

    private static final BigDecimal HIGH_VALUE_LIMIT =
            new BigDecimal("1000000.00");

    @Override
    public OrderRoute classify(Order order) {
        if (order == null || order.region() == null
                || order.totalAmount() == null) {
            return OrderRoute.REVIEW;
        }

        if (order.totalAmount().compareTo(HIGH_VALUE_LIMIT) >= 0) {
            return OrderRoute.HIGH_VALUE;
        }

        if ("INTERNATIONAL".equals(order.region())) {
            return OrderRoute.INTERNATIONAL;
        }

        if ("DOMESTIC".equals(order.region())) {
            return OrderRoute.DOMESTIC;
        }

        return OrderRoute.REVIEW;
    }
}
~~~

Ở đây, HIGH_VALUE được xét trước region. Vì vậy một đơn hàng quốc tế có tổng tiền bằng hoặc lớn hơn ngưỡng sẽ được phân loại HIGH_VALUE. Test phải xác nhận chính sách ưu tiên này.

Nếu nghiệp vụ muốn mọi đơn quốc tế đi vào INTERNATIONAL bất kể số tiền, hãy đổi thứ tự điều kiện và sửa ma trận test tương ứng. Điều quan trọng là quy tắc phải có chủ đích và được test.

## 4. Kiểm thử classifier trực tiếp

Unit test nên gọi classify() trực tiếp với từng loại input. Không cần JobLauncher hoặc Spring ApplicationContext nếu chỉ kiểm tra quy tắc phân loại.

Ví dụ:

~~~java
class OrderRouteClassifierTest {

    private final OrderRouteClassifier classifier =
            new OrderRouteClassifier();

    @Test
    void classifiesHighValueOrder() {
        Order order = new Order(
                1L,
                "DOMESTIC",
                new BigDecimal("1500000.00"));

        assertEquals(
                OrderRoute.HIGH_VALUE,
                classifier.classify(order));
    }

    @Test
    void classifiesInternationalOrderBelowThreshold() {
        Order order = new Order(
                2L,
                "INTERNATIONAL",
                new BigDecimal("500000.00"));

        assertEquals(
                OrderRoute.INTERNATIONAL,
                classifier.classify(order));
    }

    @Test
    void classifiesDomesticOrderBelowThreshold() {
        Order order = new Order(
                3L,
                "DOMESTIC",
                new BigDecimal("500000.00"));

        assertEquals(
                OrderRoute.DOMESTIC,
                classifier.classify(order));
    }

    @Test
    void sendsUnknownRegionToReview() {
        Order order = new Order(
                4L,
                "UNKNOWN",
                new BigDecimal("500000.00"));

        assertEquals(
                OrderRoute.REVIEW,
                classifier.classify(order));
    }
}
~~~

Các test này xác nhận từng kết quả chính. Tuy nhiên, vẫn cần kiểm tra giá trị biên và trường hợp nhiều điều kiện cùng đúng.

## 5. Kiểm thử giá trị biên

Nếu classifier dùng ngưỡng số tiền, cần kiểm tra giá trị ngay dưới ngưỡng, đúng bằng ngưỡng và ngay trên ngưỡng.

Với ngưỡng 1.000.000:

| Input | Kết quả mong đợi |
| ---: | --- |
| 999.999,99 | INTERNATIONAL hoặc DOMESTIC theo region |
| 1.000.000,00 | HIGH_VALUE |
| 1.000.000,01 | HIGH_VALUE |

Ví dụ:

~~~java
@ParameterizedTest
@CsvSource({
        "999999.99, DOMESTIC",
        "1000000.00, HIGH_VALUE",
        "1000000.01, HIGH_VALUE"
})
void classifiesAmountAtThreshold(
        String amount,
        OrderRoute expected) {

    Order order = new Order(
            10L,
            "DOMESTIC",
            new BigDecimal(amount));

    assertEquals(expected, classifier.classify(order));
}
~~~

Không dùng double cho giá trị tiền trong test ngưỡng. BigDecimal giúp so sánh chính xác theo decimal mà nghiệp vụ quy định.

Ngoài ngưỡng tiền, cần kiểm tra:

- Chuỗi rỗng và chuỗi chỉ có khoảng trắng.
- Giá trị enum mới hoặc không nhận diện.
- Ngày ngay trước, đúng ngày và sau cutoff.
- Số lượng bằng 0, âm và giới hạn tối đa.
- Region có chữ hoa/chữ thường khác nhau nếu input không được chuẩn hóa.
- Null ở từng field mà classifier đọc.

Nếu input được normalize trước khi phân loại, hãy kiểm thử cả bước normalize hoặc xác nhận classifier có nhận dữ liệu đã chuẩn hóa theo hợp đồng.

## 6. Kiểm thử thứ tự ưu tiên giữa các điều kiện

Một classifier có thể chứa nhiều điều kiện cùng đúng. Test riêng các trường hợp chồng lấn để xác nhận nhánh ưu tiên.

Ví dụ:

~~~java
@Test
void highValueTakesPriorityOverInternationalRegion() {
    Order order = new Order(
            20L,
            "INTERNATIONAL",
            new BigDecimal("1500000.00"));

    assertEquals(
            OrderRoute.HIGH_VALUE,
            classifier.classify(order));
}
~~~

Nếu chỉ test một đơn HIGH_VALUE nội địa và một đơn INTERNATIONAL giá trị thấp, test suite chưa xác nhận thứ tự ưu tiên.

Với các điều kiện Boolean phức tạp, nên tạo bảng tổ hợp để bảo đảm mỗi điều kiện có cả giá trị true và false trong những tình huống quan trọng. Không cần liệt kê mọi tổ hợp nếu có quá nhiều điều kiện, nhưng phải bao phủ các tổ hợp làm thay đổi nhánh.

## 7. Kiểm thử null và dữ liệu không hợp lệ

Null có thể xuất hiện ở object hoặc ở property mà classifier đọc. Cần xác định hành vi mong muốn:

- Trả về nhánh REVIEW.
- Ném exception dữ liệu đầu vào.
- Từ chối input ở validation trước khi classifier chạy.

Ví dụ classifier hiện tại chuyển dữ liệu thiếu sang REVIEW:

~~~java
@Test
void sendsNullOrderToReview() {
    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(null));
}

@Test
void sendsMissingRegionToReview() {
    Order order = new Order(
            21L,
            null,
            new BigDecimal("100.00"));

    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(order));
}

@Test
void sendsMissingAmountToReview() {
    Order order = new Order(22L, "DOMESTIC", null);

    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(order));
}
~~~

Nếu null là lỗi lập trình và không được phép xuất hiện, có thể dùng Objects.requireNonNull và test exception. Không để hành vi null phụ thuộc tình cờ vào NullPointerException ở một dòng so sánh.

### Phân biệt fallback với exception

Fallback phù hợp khi có một nhánh nghiệp vụ có chủ đích, ví dụ REVIEW. Exception phù hợp khi input vi phạm contract mà không thể phân loại an toàn.

Không chuyển mọi giá trị lạ vào nhánh DOMESTIC chỉ vì đó là nhánh phổ biến nhất. Một region mới có thể là INTERNATIONAL hoặc một loại đặc biệt; fallback sai có thể tạo dữ liệu sai nhưng Job vẫn COMPLETED.

## 8. Kiểm thử classifier bằng parameterized test

Khi có nhiều loại input, có thể dùng MethodSource để tạo test case có tên và dữ liệu rõ ràng:

~~~java
static Stream<Arguments> routeCases() {
    return Stream.of(
            Arguments.of(
                    new Order(1L, "DOMESTIC", new BigDecimal("1500000")),
                    OrderRoute.HIGH_VALUE),
            Arguments.of(
                    new Order(2L, "INTERNATIONAL", new BigDecimal("500000")),
                    OrderRoute.INTERNATIONAL),
            Arguments.of(
                    new Order(3L, "DOMESTIC", new BigDecimal("500000")),
                    OrderRoute.DOMESTIC),
            Arguments.of(
                    new Order(4L, "OTHER", new BigDecimal("500000")),
                    OrderRoute.REVIEW)
    );
}

@ParameterizedTest(name = "case {index} returns {1}")
@MethodSource("routeCases")
void classifiesEveryRoute(Order input, OrderRoute expected) {
    assertEquals(expected, classifier.classify(input));
}
~~~

Parameterized test giảm lặp code nhưng mỗi case vẫn phải dễ đọc. Nếu test thất bại, tên case hoặc tham số cần giúp xác định điều kiện nào sai.

Không đưa quá nhiều trường hợp không liên quan vào một danh sách dài không có mô tả. Có thể tách nhóm test theo high value, region, null và fallback để báo cáo dễ hiểu hơn.

## 9. Kiểm thử mọi nhánh của ClassifierCompositeItemWriter

ClassifierCompositeItemWriter chọn writer dựa trên từng item. Một writer có thể nhận các item được phân loại vào cùng nhánh.

Ví dụ:

~~~java
@Bean
public ClassifierCompositeItemWriter<Order> orderWriter(
        ItemWriter<Order> highValueWriter,
        ItemWriter<Order> internationalWriter,
        ItemWriter<Order> domesticWriter,
        ItemWriter<Order> reviewWriter) {

    return new ClassifierCompositeItemWriterBuilder<Order>()
            .classifier(order -> {
                OrderRoute route = orderRouteClassifier.classify(order);
                return switch (route) {
                    case HIGH_VALUE -> highValueWriter;
                    case INTERNATIONAL -> internationalWriter;
                    case DOMESTIC -> domesticWriter;
                    case REVIEW -> reviewWriter;
                };
            })
            .build();
}
~~~

Đây là ví dụ cấu hình theo Spring Batch 5. Nếu dự án dùng version khác, hãy đối chiếu builder và generic signature tương ứng. Có thể cấu hình trực tiếp ClassifierCompositeItemWriter bằng setter classifier nếu không dùng builder.

### Kiểm thử routing của writer

Tạo mock cho từng delegate, gửi một chunk chứa item thuộc tất cả nhánh:

~~~java
@ExtendWith(MockitoExtension.class)
class OrderWriterRoutingTest {

    @Mock
    private ItemWriter<Order> highValueWriter;

    @Mock
    private ItemWriter<Order> internationalWriter;

    @Mock
    private ItemWriter<Order> domesticWriter;

    @Mock
    private ItemWriter<Order> reviewWriter;

    private ClassifierCompositeItemWriter<Order> writer;

    @BeforeEach
    void setUp() {
        OrderRouteClassifier routeClassifier =
                new OrderRouteClassifier();

        writer = new ClassifierCompositeItemWriter<>();
        writer.setClassifier(order -> switch (routeClassifier.classify(order)) {
            case HIGH_VALUE -> highValueWriter;
            case INTERNATIONAL -> internationalWriter;
            case DOMESTIC -> domesticWriter;
            case REVIEW -> reviewWriter;
        });
    }

    @Test
    void routesItemsToEveryExpectedWriter() throws Exception {
        Order high = new Order(
                1L, "DOMESTIC", new BigDecimal("1500000"));
        Order international = new Order(
                2L, "INTERNATIONAL", new BigDecimal("500000"));
        Order domestic = new Order(
                3L, "DOMESTIC", new BigDecimal("500000"));
        Order review = new Order(
                4L, "OTHER", new BigDecimal("500000"));

        writer.write(new Chunk<>(
                List.of(high, international, domestic, review)));

        verify(highValueWriter).write(any());
        verify(internationalWriter).write(any());
        verify(domesticWriter).write(any());
        verify(reviewWriter).write(any());
    }
}
~~~

Test trên xác nhận mỗi nhánh có delegate được gọi. Để kiểm tra chính xác hơn, hãy capture chunk của từng delegate và xác nhận chỉ item đúng nhánh xuất hiện trong chunk đó.

### Kiểm tra nội dung từng chunk

Ví dụ dùng ArgumentCaptor:

~~~java
@Captor
private ArgumentCaptor<Chunk<Order>> highValueChunk;

@Test
void sendsOnlyHighValueItemsToHighValueWriter() throws Exception {
    Order high1 = new Order(
            1L, "DOMESTIC", new BigDecimal("1500000"));
    Order high2 = new Order(
            2L, "INTERNATIONAL", new BigDecimal("2000000"));
    Order normal = new Order(
            3L, "DOMESTIC", new BigDecimal("100000"));

    writer.write(new Chunk<>(List.of(high1, high2, normal)));

    verify(highValueWriter).write(highValueChunk.capture());

    assertEquals(
            List.of(1L, 2L),
            highValueChunk.getValue().getItems().stream()
                    .map(Order::orderId)
                    .toList());
}
~~~

Trong test thực tế, khởi tạo Mockito annotation bằng MockitoExtension hoặc MockitoAnnotations.openMocks. Tùy generic signature của ItemWriter.write, có thể cần khai báo ArgumentCaptor với wildcard hoặc dùng argThat để tránh lỗi kiểu.

ClassifierCompositeItemWriter có thể gom item theo delegate trước khi gọi writer. Vì vậy, không nên giả định mỗi item tạo ra một lời gọi write riêng. Cũng không nên assert thứ tự gọi giữa các delegate nếu implementation không cam kết thứ tự đó; hãy kiểm tra tập delegate được gọi và nội dung chunk của từng delegate.

## 10. Kiểm thử nhánh không có item

Một chunk có thể không chứa item cho một nhánh cụ thể. Delegate của nhánh đó không nên được gọi trong lần ghi này.

Ví dụ chunk chỉ có đơn nội địa:

~~~java
@Test
void doesNotCallInternationalWriterWhenChunkHasNoInternationalOrders()
        throws Exception {

    Order domestic = new Order(
            10L, "DOMESTIC", new BigDecimal("100.00"));

    writer.write(new Chunk<>(List.of(domestic)));

    verify(domesticWriter).write(any());
    verifyNoInteractions(internationalWriter);
    verifyNoInteractions(highValueWriter);
    verifyNoInteractions(reviewWriter);
}
~~~

Test này giúp phát hiện classifier hoặc cấu hình composite gửi nhầm item đến nhiều delegate.

Với chunk rỗng, hãy xác định hành vi mong muốn theo component và version. Thông thường không có item để phân loại nên các delegate không cần nhận chunk. Test có thể xác nhận không delegate nào được gọi nếu đó là contract của ứng dụng.

## 11. Kiểm thử classifier trả về delegate mặc định

Nếu classifier hỗ trợ fallback, test phải xác nhận fallback được chọn cho mọi giá trị chưa nhận diện:

~~~java
@Test
void routesUnknownRegionToReviewWriter() throws Exception {
    Order unknown = new Order(
            30L, "NEW_REGION", new BigDecimal("100.00"));

    writer.write(new Chunk<>(List.of(unknown)));

    verify(reviewWriter).write(any());
    verifyNoInteractions(domesticWriter);
    verifyNoInteractions(internationalWriter);
    verifyNoInteractions(highValueWriter);
}
~~~

Không chỉ assert classifier trả REVIEW; cần kiểm tra REVIEW được map sang đúng reviewWriter. Hai tầng này có thể bị cấu hình sai độc lập.

### Không trả delegate null

Nếu classifier trả null, composite không có writer hợp lệ để xử lý item. Tùy implementation, lỗi có thể xuất hiện khi gom nhóm hoặc lúc gọi write. Hãy kiểm tra null ngay trong classifier hoặc cấu hình fallback rõ ràng.

Ví dụ:

~~~java
private ItemWriter<Order> writerFor(OrderRoute route) {
    ItemWriter<Order> selected = writers.get(route);
    if (selected == null) {
        throw new IllegalArgumentException(
                "No writer configured for route " + route);
    }
    return selected;
}
~~~

Test cần xác nhận giá trị route chưa được cấu hình tạo exception rõ ràng thay vì NullPointerException khó chẩn đoán.

## 12. Kiểm thử ClassifierCompositeItemProcessor

ClassifierCompositeItemProcessor chọn processor theo input. Đây là cách dùng khi các loại item cần logic biến đổi khác nhau:

~~~text
OrderInput
    |
    v
Classifier
    |
    +--> DomesticProcessor
    |
    +--> InternationalProcessor
    |
    +--> ReviewProcessor
~~~

Ví dụ cấu hình:

~~~java
@Bean
public ClassifierCompositeItemProcessor<Order, OrderResult>
        orderProcessor(
                ItemProcessor<Order, OrderResult> domesticProcessor,
                ItemProcessor<Order, OrderResult> internationalProcessor,
                ItemProcessor<Order, OrderResult> reviewProcessor) {

    ClassifierCompositeItemProcessor<Order, OrderResult> composite =
            new ClassifierCompositeItemProcessor<>();

    composite.setClassifier(order -> switch (orderRouteClassifier.classify(order)) {
        case HIGH_VALUE, DOMESTIC -> domesticProcessor;
        case INTERNATIONAL -> internationalProcessor;
        case REVIEW -> reviewProcessor;
    });

    return composite;
}
~~~

Ví dụ gộp HIGH_VALUE vào domestic chỉ để minh họa cách chọn processor; trong ứng dụng thực tế có thể dùng processor riêng cho HIGH_VALUE. Hãy giữ quy tắc nghiệp vụ nhất quán giữa processor và writer nếu cả hai đều phân nhánh.

### Test từng processor được chọn

Có thể mock processor delegate:

~~~java
@Test
void delegatesInternationalOrderToInternationalProcessor()
        throws Exception {

    Order input = new Order(
            40L, "INTERNATIONAL", new BigDecimal("500.00"));
    OrderResult expected = new OrderResult(40L, "CROSS_BORDER");

    when(internationalProcessor.process(input)).thenReturn(expected);

    OrderResult result = composite.process(input);

    assertEquals(expected, result);
    verify(internationalProcessor).process(input);
    verifyNoInteractions(domesticProcessor, reviewProcessor);
}
~~~

Lặp lại kiểm tra cho mỗi nhánh. Với processor trả null để filter item, test phải xác nhận null được truyền ra đúng theo contract; không nhầm null output với lỗi classifier.

### Test exception từ processor được chọn

~~~java
@Test
void propagatesFailureFromSelectedProcessor() throws Exception {
    Order input = new Order(
            41L, "INTERNATIONAL", new BigDecimal("500.00"));

    when(internationalProcessor.process(input))
            .thenThrow(new IllegalStateException("pricing unavailable"));

    assertThrows(
            IllegalStateException.class,
            () -> composite.process(input));

    verify(internationalProcessor).process(input);
    verifyNoInteractions(domesticProcessor, reviewProcessor);
}
~~~

ClassifierCompositeItemProcessor không tự retry processor. Retry là hành vi của Step fault-tolerant configuration. Unit test xác nhận exception được truyền ra; integration test mới xác nhận Step retry/skip theo policy.

## 13. Kiểm thử classifier độc lập với component routing

Một thiết kế dễ kiểm thử là tách classifier thành bean riêng:

~~~java
@Bean
public Classifier<Order, OrderRoute> orderRouteClassifier() {
    return new OrderRouteClassifier();
}
~~~

Sau đó writer/processor mapping chỉ chuyển OrderRoute sang delegate:

~~~java
@Bean
public Classifier<Order, ItemWriter<? super Order>> orderWriterClassifier(
        Classifier<Order, OrderRoute> routeClassifier,
        ItemWriter<Order> highWriter,
        ItemWriter<Order> internationalWriter,
        ItemWriter<Order> domesticWriter,
        ItemWriter<Order> reviewWriter) {

    return order -> switch (routeClassifier.classify(order)) {
        case HIGH_VALUE -> highWriter;
        case INTERNATIONAL -> internationalWriter;
        case DOMESTIC -> domesticWriter;
        case REVIEW -> reviewWriter;
    };
}
~~~

Cách tách này tạo hai tập test:

- Test OrderRouteClassifier để xác nhận điều kiện nghiệp vụ.
- Test mapping route-to-delegate để xác nhận từng route chọn đúng bean.

Khi thêm một route mới, compiler có thể giúp phát hiện switch expression chưa xử lý enum mới nếu không có default. Test mapping cũng cần thêm case cho route đó.

Nếu classifier và mapping được viết chung một lambda, vẫn có thể test trực tiếp nhưng khó xác định lỗi nằm ở điều kiện hay ở cấu hình delegate. Tách lớp khi quy tắc phân loại có nhiều nhánh hoặc được dùng ở nhiều nơi.

## 14. Kiểm thử nhánh default khi enum được mở rộng

Khi thêm enum value mới, có hai lựa chọn:

**Exhaustive switch:** không có default, compiler yêu cầu xử lý mọi enum constant khi biên dịch lại.

**Default branch:** mọi giá trị chưa xử lý đi vào nhánh dự phòng.

Ví dụ:

~~~java
return switch (route) {
    case HIGH_VALUE -> highWriter;
    case INTERNATIONAL -> internationalWriter;
    case DOMESTIC -> domesticWriter;
    case REVIEW -> reviewWriter;
};
~~~

Exhaustive switch giúp phát hiện route mới chưa được cấu hình. Với dữ liệu đến từ hệ thống ngoài, vẫn cần xử lý giá trị không nhận diện trước khi chuyển thành enum.

Nếu dùng default:

~~~java
return switch (route) {
    case HIGH_VALUE -> highWriter;
    case INTERNATIONAL -> internationalWriter;
    case DOMESTIC -> domesticWriter;
    default -> reviewWriter;
};
~~~

Test phải xác nhận các giá trị ngoài danh sách được chuyển đúng vào reviewWriter. Tuy nhiên, default có thể che giấu việc thêm enum mới mà chưa đánh giá nghiệp vụ. Có thể ghi metric hoặc log cảnh báo khi fallback được sử dụng.

## 15. Kiểm thử tính thuần và tính xác định

Classifier thường được gọi nhiều lần và có thể được gọi lại khi chunk retry. Kết quả nên phụ thuộc vào input và cấu hình cố định, không phụ thuộc trạng thái ngẫu nhiên.

Một classifier khó kiểm thử:

~~~java
public OrderRoute classify(Order order) {
    if (repository.isPriorityCustomer(order.customerCode())) {
        return random.nextBoolean()
                ? OrderRoute.HIGH_VALUE
                : OrderRoute.REVIEW;
    }
    return OrderRoute.DOMESTIC;
}
~~~

Nếu nghiệp vụ thực sự cần tra cứu khách hàng, hãy tách enrichment/lookup thành processor hoặc inject một dependency có hợp đồng rõ ràng. Nếu classifier buộc phải dùng dependency, test cần kiểm soát dependency và xác nhận hành vi khi dependency timeout, không tìm thấy dữ liệu hoặc trả kết quả khác nhau.

Không gọi API bên ngoài trong classify() nếu kết quả có thể được tính hoặc nạp trước. Retry có thể gọi lại classifier; side effect trong classifier dễ bị lặp và khó quan sát.

## 16. Kiểm thử exception classifier và retry policy

Spring Batch có thể dùng classifier trong các chính sách phân loại exception, ví dụ chọn retry policy hoặc rollback behavior theo loại exception. Khi ứng dụng tự cấu hình các policy này, cần kiểm tra mọi exception type quan trọng.

Một ma trận ví dụ:

| Exception | Hành vi mong muốn |
| --- | --- |
| TransientDataAccessException | Retry có giới hạn |
| DeadlockLoserDataAccessException | Retry có giới hạn nếu thao tác idempotent |
| InvalidOrderException | Skip/reject theo giới hạn |
| IllegalStateException do cấu hình | Fail nhanh |
| AuthenticationException | Fail và yêu cầu sửa cấu hình |

Test classifier/policy nên xác nhận:

- Exception cụ thể được phân vào nhóm mong muốn.
- Subclass có được xử lý như superclass hay không.
- Exception không biết có đi vào default policy không.
- Retry limit được áp dụng.
- Exception không retry được không bị retry ngoài ý muốn.
- Lỗi dữ liệu không bị phân loại nhầm thành lỗi transient.

Đừng dùng một retry policy rộng cho mọi RuntimeException. Lỗi lập trình hoặc lỗi dữ liệu không tự biến mất sau khi thử lại.

Phần classifier exception nên được kiểm tra riêng khỏi item routing. Một OrderRouteClassifier và một RetryPolicy classifier có input/output khác nhau, dù cùng dùng ý tưởng phân loại.

## 17. Kiểm thử toàn Step với nhiều nhánh

Unit test xác nhận classifier và delegate riêng lẻ, nhưng chưa chứng minh Step wiring đúng. Integration test nên chạy Step với dữ liệu chứa ít nhất một item thuộc mỗi nhánh.

Ví dụ kịch bản:

~~~text
Input:
  Order 1 -> HIGH_VALUE
  Order 2 -> INTERNATIONAL
  Order 3 -> DOMESTIC
  Order 4 -> REVIEW

Expected:
  high_value_output       = [1]
  international_output   = [2]
  domestic_output         = [3]
  review_output           = [4]
~~~

Sau khi chạy Step:

- Xác nhận BatchStatus và ExitStatus.
- Đếm item ở từng output.
- Kiểm tra business ID trong từng output.
- Xác nhận không item nào xuất hiện ở hai nhánh.
- Xác nhận không item nào bị bỏ sót.
- Kiểm tra các nhánh không có item không tạo side effect ngoài ý muốn.

Không chỉ assert tổng số item bằng số input. Ví dụ bốn item có thể được ghi đủ nhưng hai item bị đảo nhánh; tổng count vẫn đúng.

### Kiểm tra nhánh lỗi

Tạo một delegate có chủ đích ném exception:

~~~text
Chunk có item thuộc HIGH_VALUE và DOMESTIC
  |
  v
HIGH_VALUE writer ghi thành công trong transaction
  |
  v
DOMESTIC writer ném exception
  |
  v
Chunk rollback theo transaction manager
~~~

Nếu cả hai delegate ghi cùng database và tham gia cùng transaction, integration test cần xác nhận dữ liệu của chunk được rollback. Nếu delegate ghi file hoặc gọi API, test phải phản ánh side effect không tự rollback.

## 18. Kiểm thử ItemStream của delegate

Một số writer được chọn bởi classifier là ItemStream, ví dụ FlatFileItemWriter. Cần bảo đảm Step quản lý lifecycle của từng delegate:

- open(ExecutionContext).
- update(ExecutionContext).
- close().

ClassifierCompositeItemWriter không nên được giả định là tự chuyển tiếp lifecycle của mọi delegate trong mọi version. Kiểm tra interface và tài liệu của version Spring Batch đang dùng; nếu delegate cần ItemStream, đăng ký stream với Step theo cách phù hợp.

Ví dụ:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(classifierCompositeWriter)
        .stream(highValueFileWriter)
        .stream(internationalFileWriter)
        .stream(domesticFileWriter)
        .stream(reviewFileWriter)
        .build();
~~~

Nếu dùng builder hoặc delegate wrapper có hỗ trợ stream propagation, xác nhận hành vi cụ thể thay vì đăng ký lặp. Test restart với file output để kiểm tra từng writer khôi phục đúng checkpoint và không ghi đè file của nhánh khác.

## 19. Kiểm thử nhiều nhánh trong chunk và grouping

Một chunk có thể chứa nhiều item thuộc cùng một nhánh hoặc nhiều nhánh khác nhau:

~~~text
Chunk:
  HIGH_VALUE
  DOMESTIC
  HIGH_VALUE
  REVIEW
  INTERNATIONAL
  DOMESTIC

Nhóm gửi tới delegate:
  highValueWriter      -> 2 items
  domesticWriter       -> 2 items
  reviewWriter         -> 1 item
  internationalWriter  -> 1 item
~~~

Test nên kiểm tra:

- Mỗi item chỉ được đưa vào một delegate.
- Mọi item được phân loại đều được gửi đến delegate tương ứng.
- Chunk của delegate chỉ chứa item thuộc nhánh đó.
- Thứ tự item trong cùng một nhánh được giữ nếu contract yêu cầu.
- Không giả định thứ tự gọi giữa các delegate nếu implementation dùng map hoặc grouping không cam kết thứ tự.

Nếu downstream phụ thuộc thứ tự giữa các nhánh, ClassifierCompositeItemWriter có thể không phải abstraction phù hợp. Hãy dùng một writer điều phối tùy chỉnh với thứ tự rõ ràng hoặc tách thành Step/flow phù hợp.

## 20. Kiểm thử khi một nhánh không được cấu hình

Nếu classifier trả một route nhưng mapping không có delegate, đó là lỗi cấu hình. Có thể xử lý bằng:

- Exhaustive switch trên enum.
- Map được kiểm tra đầy đủ khi khởi tạo application context.
- Throw exception rõ ràng nếu không tìm thấy delegate.
- Default reject writer nếu nghiệp vụ cho phép.

Ví dụ kiểm tra cấu hình:

~~~java
EnumMap<OrderRoute, ItemWriter<Order>> writers =
        new EnumMap<>(OrderRoute.class);

writers.put(OrderRoute.HIGH_VALUE, highValueWriter);
writers.put(OrderRoute.INTERNATIONAL, internationalWriter);
writers.put(OrderRoute.DOMESTIC, domesticWriter);
writers.put(OrderRoute.REVIEW, reviewWriter);

for (OrderRoute route : OrderRoute.values()) {
    if (!writers.containsKey(route) || writers.get(route) == null) {
        throw new IllegalStateException(
                "Missing writer for route " + route);
    }
}
~~~

Test cấu hình thiếu delegate nên thất bại sớm khi khởi tạo, thay vì chờ một item hiếm gặp chạy đến nhánh đó trong production.

## 21. Kiểm thử retry và side effect theo nhánh

Nếu một delegate thất bại, retry của chunk có thể gọi lại writer composite và phân loại lại item. Mỗi lần retry, cùng một input nên đi đến cùng một nhánh nếu classifier là deterministic.

Test cần xác nhận:

- Classifier không thay đổi route giữa các lần gọi cùng input.
- Delegate được gọi lại theo policy.
- Writer database có thể rollback trước khi retry.
- API/message/file delegate có idempotency hoặc cơ chế phục hồi riêng.
- Không có item bị chuyển sang nhánh khác do state mutable bị thay đổi.

Không để classifier phụ thuộc vào biến toàn cục hoặc trạng thái thay đổi theo lần gọi. Nếu route thay đổi theo thời gian, hãy xác định route tại một thời điểm và lưu vào item/context để retry dùng cùng quyết định.

Ví dụ có thể thêm route vào DTO sau bước classification:

~~~java
public record RoutedOrder(
        Order order,
        OrderRoute route) {
}
~~~

Sau đó processor/writer dùng route đã xác định thay vì tính lại dựa trên dữ liệu có thể thay đổi. Chỉ làm vậy khi route phải được cố định qua chunk/restart theo yêu cầu nghiệp vụ.

## 22. Kiểm thử classifier khi có dữ liệu mới

Classifier thường cần cập nhật khi thêm region, product type, customer tier hoặc event type. Test nên làm lộ các giá trị chưa được hỗ trợ.

Ví dụ:

~~~java
@Test
void unknownRegionUsesReviewRoute() {
    Order order = new Order(
            70L, "NEW_REGION", new BigDecimal("200.00"));

    assertEquals(
            OrderRoute.REVIEW,
            classifier.classify(order));
}
~~~

Nếu nghiệp vụ muốn fail thay vì fallback:

~~~java
@Test
void rejectsUnsupportedRegion() {
    Order order = new Order(
            71L, "NEW_REGION", new BigDecimal("200.00"));

    assertThrows(
            UnsupportedRegionException.class,
            () -> strictClassifier.classify(order));
}
~~~

Hãy quyết định giữa fallback và fail dựa trên khả năng xử lý an toàn. Fallback tốt khi có queue review rõ ràng; fail phù hợp khi mọi nhánh đều phải được cấu hình trước và xử lý ngoài danh sách có thể gây sai dữ liệu.

## 23. Coverage: không chỉ đo số dòng

Line coverage cao không đồng nghĩa mọi nhánh đã được kiểm thử. Một classifier có thể có đủ dòng được chạy nhưng điều kiện phức tạp chưa được kiểm tra cả hai phía.

Ví dụ:

~~~java
if (amount >= limit && approved) {
    return HIGH_VALUE;
}
return STANDARD;
~~~

Ít nhất cần các test:

| amount >= limit | approved | Kết quả |
| --- | --- | --- |
| true | true | HIGH_VALUE |
| false | true | STANDARD |
| true | false | STANDARD |

Các case này giúp chứng minh mỗi điều kiện có thể thay đổi kết quả. Nếu có null, unknown hoặc short-circuit, bổ sung test tương ứng.

Có thể dùng JaCoCo hoặc công cụ coverage của dự án để xem branch coverage. Tuy nhiên, coverage chỉ là chỉ số hỗ trợ; assertion phải xác nhận kết quả nghiệp vụ đúng.

Không viết test chỉ để đạt 100% branch coverage bằng cách gọi mọi dòng mà không kiểm tra output, delegate hoặc side effect.

## 24. Những lỗi thường gặp

### Chỉ test nhánh phổ biến

Các nhánh hiếm như REVIEW hoặc INTERNATIONAL có thể bị cấu hình sai. Tạo test cho mọi kết quả phân loại.

### Không test giá trị sát ngưỡng

Lỗi dùng lớn hơn thay vì lớn hơn hoặc bằng thường chỉ xuất hiện ở boundary. Test dưới, bằng và trên ngưỡng.

### Không test điều kiện chồng lấn

Một item có thể thỏa nhiều điều kiện. Xác nhận thứ tự ưu tiên.

### Chỉ test classifier, không test routing

Classifier có thể trả đúng enum nhưng mapping enum sang writer sai. Test riêng cả mapping và composite behavior.

### Chỉ verify delegate được gọi

Item vẫn có thể bị gửi nhầm. Capture chunk và assert business ID của từng item.

### Assert thứ tự gọi delegate không được cam kết

Composite có thể gom item theo writer và dùng collection không bảo đảm iteration order. Assert nội dung và membership thay vì thứ tự không thuộc contract.

### Trả null khi không có delegate

Lỗi xuất hiện muộn dưới dạng NullPointerException. Reject route không hợp lệ hoặc dùng fallback tường minh.

### Dùng fallback che giấu route mới

Enum mới có thể bị chuyển vào nhánh cũ mà không ai biết. Cân nhắc exhaustive switch hoặc cảnh báo fallback.

### Bỏ qua null và field thiếu

Classifier có thể ném NullPointerException hoặc chọn sai nhánh. Quy định rõ null policy và test từng trường hợp.

### Classifier có side effect

Retry có thể gọi lại classifier và lặp API/database operation. Giữ classifier thuần hoặc làm dependency idempotent.

### Không đăng ký ItemStream delegate

File writer có thể không lưu checkpoint hoặc không đóng đúng cách. Kiểm tra lifecycle và restart của từng delegate.

### Chỉ test unit mà không chạy Step

Unit test không xác nhận wiring, stream registration, transaction, retry và skip. Bổ sung integration test cho hành vi framework.

## 25. Ma trận kiểm thử classifier

Một ma trận thực tế có thể bao gồm:

| Nhóm | Trường hợp | Kỳ vọng |
| --- | --- | --- |
| Mỗi nhánh | Một input đại diện cho từng route | Đúng route |
| Boundary | Dưới, bằng và trên ngưỡng | Đúng toán tử và nhánh |
| Ưu tiên | Input thỏa nhiều điều kiện | Chọn route ưu tiên |
| Null | Object hoặc field null | REVIEW hoặc exception theo contract |
| Unknown | Enum/region/type không hỗ trợ | Fallback hoặc exception rõ ràng |
| Mapping | Route sang processor/writer | Đúng delegate |
| Grouping | Chunk có nhiều route | Item nằm đúng chunk của delegate |
| Empty branch | Chunk không có item của route | Delegate tương ứng không được gọi |
| Failure | Delegate được chọn ném exception | Exception truyền ra đúng |
| Retry | Cùng item được xử lý lại | Route ổn định, side effect idempotent |
| Stream | Delegate có ItemStream | open/update/close và restart đúng |
| Step | Chạy dữ liệu chứa mọi route | Output đúng, không mất/trùng item |

Ma trận này là khung để thiết kế test. Không phải mọi classifier đều cần tất cả trường hợp; hãy chọn dựa trên các điều kiện và component thực tế.

## 26. Quy trình kiểm thử mọi nhánh classifier

Khi xây dựng test suite, hãy thực hiện:

1. Liệt kê mọi route và điều kiện chọn route.
2. Ghi rõ thứ tự ưu tiên khi điều kiện chồng lấn.
3. Xác định null, unknown và fallback policy.
4. Viết unit test gọi classifier trực tiếp cho từng route.
5. Kiểm tra giá trị ngay dưới, bằng và trên mọi ngưỡng.
6. Dùng parameterized test cho các trường hợp có cấu trúc tương tự.
7. Test mapping từ route sang processor hoặc writer.
8. Với composite writer, capture chunk của từng delegate và xác nhận item membership.
9. Xác nhận delegate không có item không bị gọi.
10. Test exception từ classifier và delegate được chọn.
11. Kiểm tra ItemStream lifecycle nếu delegate quản lý resource/checkpoint.
12. Chạy integration test với Step để xác nhận wiring, transaction, retry và output.
13. Dùng branch coverage để tìm nhánh chưa chạy, sau đó bổ sung assertion có ý nghĩa.

Classifier nên là thành phần xác định, dễ kiểm thử và không chứa side effect. Khi quy tắc thay đổi, cập nhật bảng route và test case cùng lúc để tránh mapping giữa nghiệp vụ và delegate bị lệch.

## Kết luận

Kiểm thử mọi nhánh classifier cần xác nhận cả quy tắc phân loại và component được chọn. Bắt đầu bằng ma trận route, kiểm tra từng nhánh, giá trị biên, điều kiện chồng lấn, null và unknown; sau đó kiểm thử ClassifierCompositeItemProcessor hoặc ClassifierCompositeItemWriter để chắc chắn item đến đúng delegate. Với writer, hãy xác nhận nội dung từng chunk và tránh phụ thuộc thứ tự gọi delegate nếu implementation không cam kết. Kiểm tra exception, retry, idempotency và ItemStream lifecycle; cuối cùng chạy integration test để xác nhận Step wiring và output thực tế. Branch coverage giúp phát hiện nhánh chưa chạy, nhưng assertion về kết quả nghiệp vụ mới chứng minh classifier hoạt động đúng.
