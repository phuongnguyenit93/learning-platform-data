# Processor composite chọn theo classifier

Trong Spring Batch, một Job có thể nhận nhiều loại item trong cùng một luồng dữ liệu. Mỗi loại item có thể cần quy tắc xử lý khác nhau: giao dịch BUY cần kiểm tra hạn mức, giao dịch SELL cần tính phí, còn giao dịch TRANSFER cần kiểm tra tài khoản nguồn và tài khoản đích. Nếu gom tất cả logic vào một ItemProcessor lớn với nhiều nhánh if/else, component sẽ khó mở rộng và khó kiểm thử.

**ClassifierCompositeItemProcessor** giải quyết bài toán định tuyến này. Nó nhận một item, dùng một **Classifier** để chọn processor phù hợp, rồi chuyển item đến đúng delegate processor. Mỗi item được định tuyến theo kết quả phân loại của chính nó.

Điểm cần nhớ là processor composite theo classifier chọn **một nhánh xử lý cho mỗi item**. Nó không lần lượt chạy tất cả processor như CompositeItemProcessor. Nếu một nhánh cần thực hiện nhiều bước chuyển đổi nối tiếp, có thể đặt một CompositeItemProcessor làm delegate của nhánh đó.

## 1. Bài toán cần nhiều processor

Giả sử một Job nhập giao dịch từ nhiều nguồn. Mỗi item có loại giao dịch và các trường dữ liệu chung:

~~~java
public class Trade {

    private String tradeId;
    private String type;
    private BigDecimal amount;
    private String sourceAccount;
    private String targetAccount;

    // Getters and setters
}
~~~

Các loại giao dịch cần xử lý khác nhau:

| Loại | Quy tắc xử lý |
|---|---|
| BUY | Kiểm tra số tiền và hạn mức mua, chuẩn hóa thông tin lệnh |
| SELL | Kiểm tra số lượng bán, tính phí giao dịch |
| TRANSFER | Xác thực tài khoản nguồn/đích và kiểm tra quy tắc chuyển tiền |

Một processor duy nhất có thể viết như sau:

~~~java
public class TradeProcessor implements ItemProcessor<Trade, TradeResult> {

    @Override
    public TradeResult process(Trade trade) {
        if ("BUY".equals(trade.getType())) {
            // Logic BUY
        } else if ("SELL".equals(trade.getType())) {
            // Logic SELL
        } else if ("TRANSFER".equals(trade.getType())) {
            // Logic TRANSFER
        } else {
            throw new IllegalArgumentException(
                    "Unsupported trade type: " + trade.getType());
        }

        // ...
    }
}
~~~

Khi số loại tăng lên, processor này phải biết mọi quy tắc, mọi dependency và mọi thay đổi của từng nhánh. Việc thêm loại mới có thể làm thay đổi một class đã lớn, khiến test và bảo trì khó khăn.

Với ClassifierCompositeItemProcessor, có thể tách từng quy tắc thành một ItemProcessor riêng rồi định tuyến item đến processor phù hợp.

## 2. ClassifierCompositeItemProcessor hoạt động thế nào?

ClassifierCompositeItemProcessor là một ItemProcessor đặc biệt. Nó giữ một Classifier có nhiệm vụ chọn delegate processor dựa trên input hiện tại.

Luồng xử lý:

~~~text
ItemReader
    |
    v
Trade item
    |
    v
ClassifierCompositeItemProcessor
    |
    v
Classifier.classify(item)
    |
    +---- BUY ------> BuyTradeProcessor
    |
    +---- SELL -----> SellTradeProcessor
    |
    +---- TRANSFER -> TransferTradeProcessor
    |
    v
TradeResult
    |
    v
ItemWriter
~~~

Các bước:

1. Spring Batch gọi process(item) trên ClassifierCompositeItemProcessor.
2. Composite chuyển item cho Classifier.
3. Classifier quyết định delegate nào phù hợp.
4. Composite gọi process(item) trên delegate được chọn.
5. Kết quả từ delegate được trả về cho Step.

Với mỗi item, classifier có thể chọn một processor khác nhau. Hai item liên tiếp trong cùng chunk không bắt buộc phải đi qua cùng một delegate.

## 3. Phân biệt ClassifierCompositeItemProcessor và CompositeItemProcessor

Hai loại composite có mục đích khác nhau:

- **CompositeItemProcessor** nối nhiều processor thành một chuỗi. Output của processor trước trở thành input của processor tiếp theo.
- **ClassifierCompositeItemProcessor** chọn một processor theo kết quả phân loại của item. Chỉ delegate được chọn được gọi cho item đó.

| Tiêu chí | CompositeItemProcessor | ClassifierCompositeItemProcessor |
|---|---|---|
| Mục tiêu | Chạy một chuỗi processor | Định tuyến đến một processor |
| Số delegate được gọi cho một item | Thường là tất cả delegate trong chuỗi | Một delegate được classifier chọn |
| Quan hệ giữa các bước | Output bước trước chuyển sang bước sau | Các nhánh thường độc lập |
| Quy tắc lựa chọn | Thứ tự cấu hình | Classifier |
| Trường hợp phù hợp | Normalize → validate → enrich | BUY → processor mua, SELL → processor bán |

Ví dụ chuỗi:

~~~text
Input
  |
  v
NormalizeProcessor
  |
  v
ValidateProcessor
  |
  v
EnrichProcessor
  |
  v
Output
~~~

Ví dụ định tuyến:

~~~text
Input
  |
  v
Classifier
  |
  +---- Type A --> Processor A
  |
  +---- Type B --> Processor B
  |
  +---- Type C --> Processor C
~~~

Nếu mỗi loại giao dịch có một chuỗi riêng, có thể kết hợp hai cơ chế: classifier chọn một CompositeItemProcessor cho nhánh đó.

## 4. Tạo các delegate ItemProcessor

Mỗi delegate nên tập trung vào một loại nghiệp vụ. Ví dụ, tất cả nhánh nhận Trade và trả TradeResult:

~~~java
@Component
public class BuyTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    private final TradingPolicy tradingPolicy;

    public BuyTradeProcessor(TradingPolicy tradingPolicy) {
        this.tradingPolicy = tradingPolicy;
    }

    @Override
    public TradeResult process(Trade trade) {
        tradingPolicy.validateBuy(trade);

        return new TradeResult(
                trade.getTradeId(),
                "BUY",
                trade.getAmount(),
                BigDecimal.ZERO);
    }
}
~~~

Processor cho SELL:

~~~java
@Component
public class SellTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    private final TradingPolicy tradingPolicy;
    private final FeeCalculator feeCalculator;

    public SellTradeProcessor(
            TradingPolicy tradingPolicy,
            FeeCalculator feeCalculator) {
        this.tradingPolicy = tradingPolicy;
        this.feeCalculator = feeCalculator;
    }

    @Override
    public TradeResult process(Trade trade) {
        tradingPolicy.validateSell(trade);
        BigDecimal fee = feeCalculator.calculate(trade.getAmount());

        return new TradeResult(
                trade.getTradeId(),
                "SELL",
                trade.getAmount(),
                fee);
    }
}
~~~

Processor cho TRANSFER:

~~~java
@Component
public class TransferTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    private final AccountService accountService;

    public TransferTradeProcessor(AccountService accountService) {
        this.accountService = accountService;
    }

    @Override
    public TradeResult process(Trade trade) {
        accountService.validateTransfer(
                trade.getSourceAccount(),
                trade.getTargetAccount(),
                trade.getAmount());

        return new TradeResult(
                trade.getTradeId(),
                "TRANSFER",
                trade.getAmount(),
                BigDecimal.ZERO);
    }
}
~~~

Các delegate có cùng kiểu input và output nên có thể lắp vào một ClassifierCompositeItemProcessor<Trade, TradeResult>. Nếu mỗi nhánh tạo ra các kiểu output khác nhau, nên chuẩn hóa về một kiểu output chung hoặc dùng một interface/sealed hierarchy để writer nhận diện kết quả.

## 5. Cấu hình ClassifierCompositeItemProcessor

Trong Spring Batch, ClassifierCompositeItemProcessor nằm trong package org.springframework.batch.item.support. Nó được cấu hình bằng cách cung cấp một Classifier trả về delegate processor.

Ví dụ Java configuration:

~~~java
@Bean
ClassifierCompositeItemProcessor<Trade, TradeResult> tradeProcessor(
        BuyTradeProcessor buyProcessor,
        SellTradeProcessor sellProcessor,
        TransferTradeProcessor transferProcessor) {

    ClassifierCompositeItemProcessor<Trade, TradeResult> composite =
            new ClassifierCompositeItemProcessor<>();

    composite.setClassifier(trade -> {
        return switch (trade.getType()) {
            case "BUY" -> buyProcessor;
            case "SELL" -> sellProcessor;
            case "TRANSFER" -> transferProcessor;
            default -> throw new IllegalArgumentException(
                    "Unsupported trade type: " + trade.getType());
        };
    });

    return composite;
}
~~~

Classifier nhận một Trade và trả về ItemProcessor được chọn. Composite sau đó gọi delegate đó với cùng item.

Trong một số phiên bản, chữ ký generic của setClassifier biểu diễn delegate bằng wildcard như ItemProcessor<?, ? extends O>. Lambda thường suy luận được kiểu khi các delegate có cùng input/output. Nếu compiler báo lỗi generic, khai báo kiểu Classifier tường minh theo chữ ký API của Spring Batch đang dùng và giữ các delegate tương thích với kiểu input/output chung.

Nên inject các delegate từ Spring container thay vì tạo new BuyTradeProcessor() bên trong classifier. Dependency injection giúp delegate dùng chung cấu hình, transaction-aware service, metrics và các dependency đã được quản lý.

## 6. Classifier là thành phần quyết định nhánh

Classifier có nhiệm vụ phân loại item và trả về delegate. Nó không nên thực hiện toàn bộ nghiệp vụ của nhánh. Nên giữ logic classify đơn giản, xác định và dễ kiểm thử.

Có thể tách classifier thành một class riêng:

~~~java
public class TradeTypeClassifier
        implements Classifier<Trade, ItemProcessor<?, ? extends TradeResult>> {

    private final ItemProcessor<Trade, TradeResult> buyProcessor;
    private final ItemProcessor<Trade, TradeResult> sellProcessor;
    private final ItemProcessor<Trade, TradeResult> transferProcessor;

    public TradeTypeClassifier(
            ItemProcessor<Trade, TradeResult> buyProcessor,
            ItemProcessor<Trade, TradeResult> sellProcessor,
            ItemProcessor<Trade, TradeResult> transferProcessor) {
        this.buyProcessor = buyProcessor;
        this.sellProcessor = sellProcessor;
        this.transferProcessor = transferProcessor;
    }

    @Override
    public ItemProcessor<?, ? extends TradeResult> classify(Trade trade) {
        return switch (trade.getType()) {
            case "BUY" -> buyProcessor;
            case "SELL" -> sellProcessor;
            case "TRANSFER" -> transferProcessor;
            default -> throw new IllegalArgumentException(
                    "Unsupported trade type: " + trade.getType());
        };
    }
}
~~~

Khai báo classifier bean:

~~~java
@Bean
Classifier<Trade, ItemProcessor<?, ? extends TradeResult>> tradeClassifier(
        BuyTradeProcessor buyProcessor,
        SellTradeProcessor sellProcessor,
        TransferTradeProcessor transferProcessor) {

    return new TradeTypeClassifier(
            buyProcessor, sellProcessor, transferProcessor);
}
~~~

Sau đó cấu hình composite:

~~~java
@Bean
ClassifierCompositeItemProcessor<Trade, TradeResult> tradeProcessor(
        Classifier<Trade, ItemProcessor<?, ? extends TradeResult>> tradeClassifier) {

    ClassifierCompositeItemProcessor<Trade, TradeResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(tradeClassifier);
    return composite;
}
~~~

Chữ ký generic cụ thể của Classifier và setter cần khớp phiên bản Spring Batch/Spring Core. Ví dụ trên minh họa cách tách trách nhiệm: classifier chỉ chọn processor; delegate thực hiện xử lý.

## 7. Xử lý loại không được hỗ trợ

Classifier cần có hành vi rõ ràng khi không nhận diện được loại item. Có ba cách phổ biến:

1. Ném exception để Step thất bại hoặc áp dụng skip policy.
2. Chuyển đến một processor fallback chuyên ghi nhận item không hỗ trợ.
3. Trả về null từ delegate processor nếu nghiệp vụ muốn filter item đó.

Không nên trả về null từ classifier nếu API yêu cầu một delegate processor. Null delegate có thể dẫn tới NullPointerException khi composite cố gọi process().

Ví dụ fallback:

~~~java
@Component
public class UnsupportedTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    @Override
    public TradeResult process(Trade trade) {
        return TradeResult.rejected(
                trade.getTradeId(),
                "UNSUPPORTED_TYPE");
    }
}
~~~

Classifier có thể trả về fallback cho mọi loại chưa biết:

~~~java
default -> unsupportedTradeProcessor;
~~~

Chọn fallback hay fail phụ thuộc hợp đồng dữ liệu. Nếu loại mới có thể làm thay đổi ý nghĩa tiền hoặc trạng thái giao dịch, dừng Job thường an toàn hơn việc âm thầm tạo kết quả rejected. Nếu hệ thống yêu cầu tiếp tục và audit mọi record, fallback cần ghi nhận rõ nguyên nhân và đảm bảo writer xử lý đúng trạng thái.

## 8. Filter item trong delegate processor

Một delegate ItemProcessor có thể trả về null để filter item. Khi đó, item không được chuyển đến writer và Spring Batch tăng filter count.

Ví dụ:

~~~java
@Component
public class BuyTradeProcessor
        implements ItemProcessor<Trade, TradeResult> {

    @Override
    public TradeResult process(Trade trade) {
        if (trade.getAmount().signum() <= 0) {
            return null;
        }
        return mapBuyTrade(trade);
    }
}
~~~

Việc trả null là quyết định filter có chủ đích, không phải skip exception. Nếu delegate ném exception, Step chỉ bỏ qua item khi exception được cấu hình là skippable và skip limit chưa bị vượt.

| Kết quả delegate | Hành vi |
|---|---|
| Trả object | Item tiếp tục tới writer |
| Trả null | Item được filter, không tới writer |
| Ném exception được skip | Item bị skip theo fault-tolerance policy |
| Ném exception không được skip | Step thất bại, trừ khi có policy khác xử lý |

Không dùng null để biểu thị lỗi không hỗ trợ nếu cần audit hoặc xử lý lại; filter không tự cung cấp lý do loại item.

## 9. Kết hợp classifier với CompositeItemProcessor theo từng nhánh

Đôi khi mỗi loại item cần nhiều bước xử lý nối tiếp. Ví dụ BUY cần normalize, validate và enrich; SELL cần normalize, validate và calculate fee.

Có thể tạo một CompositeItemProcessor cho mỗi nhánh rồi để classifier chọn composite tương ứng:

~~~text
                    Classifier
                   /          \
                BUY            SELL
                 |               |
                 v               v
          Composite BUY    Composite SELL
             |   |   |        |   |   |
             v   v   v        v   v   v
          Normalize       Normalize
          Validate        Validate
          Enrich          Fee calculation
~~~

Ví dụ khai báo nhánh BUY:

~~~java
@Bean
CompositeItemProcessor<Trade, TradeResult> buyPipeline(
        NormalizeBuyProcessor normalize,
        ValidateBuyProcessor validate,
        EnrichBuyProcessor enrich) throws Exception {

    CompositeItemProcessor<Trade, TradeResult> composite =
            new CompositeItemProcessor<>();
    composite.setDelegates(List.of(normalize, validate, enrich));
    composite.afterPropertiesSet();
    return composite;
}
~~~

Ví dụ trên giả định các processor có kiểu trung gian tương thích. Nếu NormalizeBuyProcessor trả NormalizedBuy thay vì Trade, các delegate sau phải nhận đúng kiểu trung gian; generic của CompositeItemProcessor không phải lúc nào cũng phát hiện đầy đủ mismatch ở compile time do danh sách delegate dùng wildcard. Hãy cấu hình chuỗi type rõ ràng và kiểm thử.

Classifier có thể trả về ItemProcessor<Trade, TradeResult> mà delegate thực tế là CompositeItemProcessor<Trade, TradeResult>. Nhờ đó, từng nhánh có pipeline riêng nhưng Step vẫn chỉ nhìn thấy một processor tổng hợp.

## 10. Dùng map để định tuyến theo loại

Khi có nhiều loại item, có thể lưu delegate trong Map thay vì viết switch dài:

~~~java
@Bean
Classifier<Trade, ItemProcessor<?, ? extends TradeResult>> tradeClassifier(
        BuyTradeProcessor buy,
        SellTradeProcessor sell,
        TransferTradeProcessor transfer,
        UnsupportedTradeProcessor fallback) {

    Map<String, ItemProcessor<Trade, TradeResult>> processors = Map.of(
            "BUY", buy,
            "SELL", sell,
            "TRANSFER", transfer);

    return trade -> processors.getOrDefault(trade.getType(), fallback);
}
~~~

Map giúp thêm loại mới bằng cấu hình rõ ràng. Cần kiểm soát key null và chuẩn hóa type nếu dữ liệu nguồn không bảo đảm chữ hoa/chữ thường.

Ví dụ chuẩn hóa:

~~~java
String type = trade.getType() == null
        ? ""
        : trade.getType().trim().toUpperCase(Locale.ROOT);

return processors.getOrDefault(type, fallback);
~~~

Không dùng locale mặc định của máy để chuẩn hóa mã loại kỹ thuật. Locale.ROOT giúp kết quả không thay đổi theo cấu hình ngôn ngữ của server.

Nếu loại item được xác định bằng enum, nên dùng enum làm key hoặc parse chuỗi thành enum ở bước validation trước khi phân loại. Điều này giảm lỗi do typo và giúp compiler hỗ trợ kiểm tra.

## 11. Phân loại theo nhiều thuộc tính

Classifier không bắt buộc chỉ dựa vào một field. Nó có thể kết hợp type, source system, region hoặc trạng thái:

~~~java
return trade -> {
    if ("ERP".equals(trade.getSourceSystem())
            && "BUY".equals(trade.getType())) {
        return erpBuyProcessor;
    }

    if ("MOBILE".equals(trade.getSourceSystem())
            && "BUY".equals(trade.getType())) {
        return mobileBuyProcessor;
    }

    if ("SELL".equals(trade.getType())) {
        return sellProcessor;
    }

    return unsupportedProcessor;
};
~~~

Khi điều kiện tăng lên, nên tạo một routing key bất biến:

~~~java
public record TradeRoute(String sourceSystem, TradeType type) {
}
~~~

Classifier có thể tạo key từ item rồi tra Map<TradeRoute, ItemProcessor<...>>. Cách này tách logic chuẩn hóa key khỏi logic xử lý nghiệp vụ và giúp kiểm thử từng route.

Nếu các điều kiện có thứ tự ưu tiên, cần ghi rõ thứ tự đó. Một điều kiện tổng quát đặt trước điều kiện cụ thể có thể bắt mất item của nhánh cụ thể.

## 12. Phân loại theo class type

Không phải lúc nào item cũng có một field type. Nếu reader tạo ra nhiều subclass khác nhau, classifier có thể chọn processor theo class:

~~~java
public sealed interface Payment
        permits CardPayment, BankTransfer {
}

public record CardPayment(
        String paymentId,
        BigDecimal amount) implements Payment {
}

public record BankTransfer(
        String paymentId,
        BigDecimal amount,
        String destinationAccount) implements Payment {
}
~~~

Classifier có thể kiểm tra kiểu:

~~~java
return payment -> {
    if (payment instanceof CardPayment) {
        return cardPaymentProcessor;
    }
    if (payment instanceof BankTransfer) {
        return bankTransferProcessor;
    }
    throw new IllegalArgumentException(
            "Unsupported payment class: " + payment.getClass().getName());
};
~~~

Nếu hệ thống có nhiều subclass, có thể dùng một classifier theo hierarchy hoặc registry theo class. Cần xác định hành vi với subclass mới và class không được đăng ký. Không nên dùng getClass().getSimpleName() làm routing key nếu tên class có thể đổi khi refactor.

## 13. Classifier nên nhẹ và không có side effect

Classifier được gọi cho mỗi item cần định tuyến. Vì vậy, nên giữ nó nhanh, xác định và không tạo tác dụng phụ.

Tránh:

- Gọi REST API để quyết định processor cho từng item nếu có thể lấy route từ dữ liệu hoặc cache.
- Truy vấn database lặp lại cho mọi item chỉ để chọn nhánh.
- Thay đổi state dùng chung trong classify().
- Tạo một delegate processor mới cho mỗi item.
- Ghi dữ liệu nghiệp vụ trong classifier.

Classifier nên dựa vào thuộc tính đã có trong item hoặc một registry bất biến được cấu hình từ trước. Nếu việc chọn nhánh cần tra cứu dữ liệu ngoài, cân nhắc enrich item ở một bước riêng hoặc dùng cache có TTL và thread-safety phù hợp.

Việc tạo delegate mới cho mỗi item có thể làm mất lợi ích dependency injection, tăng allocation và khiến lifecycle khó quản lý. Hãy inject các delegate đã được Spring quản lý.

## 14. Thread safety của classifier và delegate

Trong multi-threaded Step hoặc khi nhiều JobExecution chạy đồng thời, cùng một classifier/delegate singleton có thể nhận nhiều lời gọi song song. Classifier và mọi delegate phải thread-safe.

Các nguyên tắc:

- Classifier stateless hoặc chỉ đọc cấu hình bất biến.
- Không giữ currentTrade trong field.
- Không thay đổi Map route sau khi Step bắt đầu.
- Delegate processor tránh mutable shared state.
- Service được delegate sử dụng phải thread-safe.
- Nếu delegate có state theo StepExecution, dùng scope phù hợp nhưng vẫn đánh giá nhiều thread trong cùng StepExecution.

Ví dụ map route bất biến:

~~~java
private final Map<String, ItemProcessor<Trade, TradeResult>> routes;

public TradeTypeClassifier(
        Map<String, ItemProcessor<Trade, TradeResult>> routes) {
    this.routes = Map.copyOf(routes);
}
~~~

Map.copyOf bảo vệ cấu trúc map khỏi thay đổi qua tham chiếu trả về. Nó không làm các processor được lưu trong map thread-safe; mỗi delegate vẫn cần được thiết kế riêng.

Nếu delegate giữ file handle, cursor hoặc checkpoint, không chia sẻ cùng instance giữa nhiều worker nếu implementation không hỗ trợ. Dùng processor riêng theo StepScope/partition khi state cần gắn với từng worker.

## 15. Skip và retry trong các nhánh

ClassifierCompositeItemProcessor nằm trong pipeline processor của Step. Vì vậy, exception từ delegate được xem là lỗi trong giai đoạn process và chịu ảnh hưởng của fault-tolerance policy ở Step.

Ví dụ:

~~~java
return new StepBuilder("processTradesStep", jobRepository)
        .<Trade, TradeResult>chunk(100, transactionManager)
        .reader(tradeReader)
        .processor(classifierCompositeItemProcessor)
        .writer(tradeWriter)
        .faultTolerant()
        .skip(InvalidTradeException.class)
        .skipLimit(50)
        .retry(TemporaryPricingException.class)
        .retryLimit(3)
        .build();
~~~

Nếu BuyTradeProcessor ném InvalidTradeException, item được xử lý theo skip policy. Nếu SellTradeProcessor ném TemporaryPricingException, Step có thể retry theo policy đã cấu hình.

Không nên dùng cùng một exception type cho lỗi nghiệp vụ vĩnh viễn và lỗi hạ tầng tạm thời nếu chúng cần policy khác nhau. Định nghĩa exception rõ nghĩa giúp chọn skip/retry chính xác.

Retry có thể gọi lại delegate hoặc toàn bộ xử lý liên quan tùy cơ chế fault tolerance. Classifier cần cho cùng một item và cùng dữ liệu route kết quả nhất quán trong suốt lần xử lý. Không thay route dựa vào mutable global state giữa các lần retry.

## 16. Filter, skip và route fallback

Ba hành vi này khác nhau:

- **Route fallback:** classifier chọn một processor chuyên xử lý loại chưa hỗ trợ.
- **Filter:** delegate trả null, item bị loại có chủ đích và không tới writer.
- **Skip:** delegate ném exception được cấu hình skippable; Spring Batch ghi nhận skip count và gọi listener phù hợp.

Không nên dùng fallback để che giấu lỗi phân loại nếu loại item mới cần dừng Job. Không nên dùng filter cho dữ liệu bị lỗi nếu cần audit. Không nên dùng skip chỉ vì một loại item không có processor; đó là vấn đề routing/configuration, không nhất thiết là lỗi của item.

## 17. Tích hợp với Step

ClassifierCompositeItemProcessor được cấu hình như một ItemProcessor bình thường:

~~~java
@Bean
Step processTradesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Trade> tradeReader,
        ClassifierCompositeItemProcessor<Trade, TradeResult> tradeProcessor,
        ItemWriter<TradeResult> tradeWriter) {

    return new StepBuilder("processTradesStep", jobRepository)
            .<Trade, TradeResult>chunk(200, transactionManager)
            .reader(tradeReader)
            .processor(tradeProcessor)
            .writer(tradeWriter)
            .build();
}
~~~

Step không cần biết có bao nhiêu delegate hoặc classifier chọn theo field nào. Nó chỉ thấy một ItemProcessor<Trade, TradeResult>.

Điều này giữ cấu hình Step gọn và tách routing khỏi transaction/write behavior. Nếu một loại giao dịch cần một writer khác hẳn, classifier processor không tự chọn writer. Khi đó có thể:

- Chuẩn hóa tất cả nhánh về một output type và dùng một writer.
- Gắn discriminator vào output để writer quyết định cách lưu.
- Dùng classifier writer riêng nếu bài toán thực sự cần định tuyến ở giai đoạn ghi.
- Tách thành các Step/flow khác nhau nếu mỗi loại có lifecycle hoặc transaction riêng.

Không đưa logic lựa chọn writer vào processor chỉ để tạo side effect ghi dữ liệu. Processor nên tạo output; writer chịu trách nhiệm persistence.

## 18. Khi nào nên tách thành nhiều Step?

ClassifierCompositeItemProcessor phù hợp khi các nhánh vẫn thuộc cùng một Step và có chung reader/writer/transaction boundary. Nếu mỗi loại item có yêu cầu vận hành khác nhau đáng kể, tách Step có thể rõ ràng hơn.

Nên cân nhắc nhiều Step hoặc nhiều flow khi:

- Mỗi loại có transaction manager hoặc database khác nhau.
- Mỗi loại cần retry/skip policy khác nhau.
- Một nhánh cần resource hoặc chunk size riêng.
- Cần chạy song song độc lập hoặc theo lịch khác nhau.
- Cần restart từng loại dữ liệu độc lập.
- Cần báo cáo trạng thái riêng theo loại.

Classifier trong processor không tạo một StepExecution riêng cho mỗi nhánh. Tất cả delegate vẫn chạy trong cùng StepExecution, cùng chunk lifecycle và cùng fault-tolerance configuration của Step.

Nếu các nhánh cần chính sách lỗi khác nhau, có thể dùng exception type riêng và policy phân loại theo exception, hoặc tách thành Step để có cấu hình độc lập và dễ vận hành hơn.

## 19. Logging và metrics theo nhánh

Khi định tuyến nhiều loại item, cần biết mỗi delegate xử lý bao nhiêu item và lỗi nào xảy ra ở nhánh nào.

Có thể ghi:

- Route key hoặc loại item.
- Số item được delegate nhận.
- Số item filter theo nhánh.
- Số lỗi và skip theo exception type.
- Thời gian xử lý theo delegate.
- Số item writer ghi thành công theo output type.

Metrics collector phải thread-safe nếu Step chạy song song. Không dùng một HashMap mutable chung để tăng counter từ nhiều thread. Có thể dùng Micrometer Counter/Timer hoặc collector concurrent phù hợp.

Không chỉ dựa vào log của classifier để kết luận item đã được ghi thành công. Delegate có thể trả kết quả nhưng writer hoặc transaction sau đó thất bại. Phân biệt processor invocation, writer invocation và commit.

## 20. Kiểm thử classifier độc lập

Classifier là logic routing nên có thể unit test mà không cần khởi chạy Job.

Ví dụ:

~~~java
@Test
void selectsProcessorByTradeType() {
    ItemProcessor<Trade, TradeResult> buy = trade -> buyResult(trade);
    ItemProcessor<Trade, TradeResult> sell = trade -> sellResult(trade);
    ItemProcessor<Trade, TradeResult> transfer = trade -> transferResult(trade);

    TradeTypeClassifier classifier =
            new TradeTypeClassifier(buy, sell, transfer);

    assertSame(buy, classifier.classify(tradeOfType("BUY")));
    assertSame(sell, classifier.classify(tradeOfType("SELL")));
    assertSame(transfer, classifier.classify(tradeOfType("TRANSFER")));
}
~~~

Nên kiểm tra:

- Mỗi loại đã hỗ trợ chọn đúng delegate.
- Loại không hỗ trợ ném exception hoặc chọn fallback đúng policy.
- Giá trị type null/blank được xử lý rõ.
- Chuẩn hóa chữ hoa/chữ thường đúng.
- Điều kiện nhiều thuộc tính có thứ tự ưu tiên đúng.
- Classifier không tạo delegate mới mỗi lần classify.

## 21. Kiểm thử ClassifierCompositeItemProcessor

Unit test composite xác nhận delegate được chọn thực sự được gọi và output được trả về:

~~~java
@Test
void delegatesItemToSelectedProcessor() throws Exception {
    ItemProcessor<Trade, TradeResult> buy = mock(ItemProcessor.class);
    ItemProcessor<Trade, TradeResult> sell = mock(ItemProcessor.class);

    Trade trade = tradeOfType("BUY");
    TradeResult expected = new TradeResult(
            trade.getTradeId(), "BUY", trade.getAmount(), BigDecimal.ZERO);

    when(buy.process(trade)).thenReturn(expected);

    ClassifierCompositeItemProcessor<Trade, TradeResult> composite =
            new ClassifierCompositeItemProcessor<>();
    composite.setClassifier(item ->
            "BUY".equals(item.getType()) ? buy : sell);

    assertSame(expected, composite.process(trade));
    verify(buy).process(trade);
    verifyNoInteractions(sell);
}
~~~

Test này kiểm tra một item BUY chỉ đi qua buy processor. Nên thêm test cho các nhánh còn lại và trường hợp classifier trả fallback hoặc ném exception.

## 22. Kiểm thử tích hợp Step

Unit test routing chưa chứng minh chunk, transaction, skip, retry và writer hoạt động đúng khi chạy Job. Nên có Step integration test với fixture gồm nhiều loại item:

~~~text
Input:
  T-001 BUY
  T-002 SELL
  T-003 TRANSFER
  T-004 BUY

Routing:
  T-001 -> BuyTradeProcessor
  T-002 -> SellTradeProcessor
  T-003 -> TransferTradeProcessor
  T-004 -> BuyTradeProcessor

Expected output:
  4 TradeResult với route/type đúng
~~~

Với Spring Batch Test, có thể chạy Step hoặc Job rồi xác nhận:

- Job/Step hoàn tất theo trạng thái mong đợi.
- readCount và writeCount phù hợp.
- Output của từng loại được tạo bởi delegate đúng.
- Item filter không xuất hiện trong output.
- Exception ở một delegate được skip/retry đúng policy.
- Writer không tạo duplicate khi retry/restart.

Nếu các delegate có dependency ngoài như pricing API hoặc account service, dùng mock hoặc stub để tạo kết quả xác định. Không phụ thuộc service production trong unit test.

## 23. Các lỗi thường gặp

**Nhầm classifier composite với processor chain:** ClassifierCompositeItemProcessor chỉ chọn một delegate cho item; nó không chạy tất cả delegate nối tiếp.

**Không có nhánh default:** loại item mới có thể làm composite nhận null delegate và gây lỗi khó hiểu. Chọn fail-fast hoặc fallback rõ ràng.

**Trả null từ classifier:** null không phải cách filter item; hãy trả delegate hợp lệ hoặc ném exception.

**Tạo processor mới trong classify():** làm mất dependency injection, tăng allocation và khiến lifecycle khó kiểm soát. Inject delegate đã được quản lý.

**Generic input/output không tương thích:** các delegate phải chấp nhận input phù hợp và trả output tương thích với O của composite. Chuỗi processor nội bộ cũng phải khớp kiểu trung gian.

**Classifier chứa nghiệp vụ quá nhiều:** routing khó kiểm thử và khó bảo trì. Chỉ phân loại ở classifier, chuyển nghiệp vụ sang delegate.

**Dùng một fallback để che mọi loại mới:** có thể làm dữ liệu quan trọng bị xử lý sai. Chọn policy theo contract.

**Cho rằng mỗi nhánh có transaction hoặc Step riêng:** mọi delegate của composite vẫn nằm trong cùng StepExecution và chunk lifecycle.

**Bỏ qua thread safety:** classifier và delegate singleton có thể được gọi đồng thời. Giữ state bất biến hoặc bảo vệ state chia sẻ.

**Không kiểm thử retry:** classifier cần chọn route nhất quán khi cùng item được xử lý lại.

**Định tuyến theo chuỗi không chuẩn hóa:** BUY, buy và chuỗi có khoảng trắng có thể đi vào nhánh khác nhau nếu không chuẩn hóa input.

## Kết luận

ClassifierCompositeItemProcessor cho phép chọn một ItemProcessor phù hợp cho từng item dựa trên kết quả của Classifier. Nó phù hợp khi một Step xử lý nhiều loại dữ liệu nhưng mỗi loại cần logic nghiệp vụ riêng. Tách delegate theo trách nhiệm, inject chúng từ Spring container và giữ classifier nhẹ, xác định, không có side effect. Phân biệt rõ cơ chế định tuyến này với CompositeItemProcessor nối nhiều processor thành chuỗi; nếu một nhánh cần nhiều bước, có thể đặt một composite làm delegate của nhánh. Hãy định nghĩa hành vi cho loại không hỗ trợ, kiểm soát filter/skip/retry, bảo đảm thread safety và kiểm thử cả routing độc lập lẫn Step integration để xác nhận đúng delegate, output, transaction và restart behavior.
