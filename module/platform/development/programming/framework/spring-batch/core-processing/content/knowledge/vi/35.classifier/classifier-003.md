# Phân loại theo field hoặc business state trong Spring Batch

Trong một chunk-oriented Step, đôi khi mỗi item cần đi theo một nhánh xử lý khác nhau. Ví dụ, đơn hàng đã thanh toán được ghi vào file paid, đơn bị hủy được ghi vào file cancelled, còn đơn cần kiểm tra được đưa vào hàng review. Một trường hợp khác là cùng một loại input nhưng mỗi trạng thái nghiệp vụ cần một processor riêng.

Spring Batch hỗ trợ cách định tuyến này bằng **Classifier** và các thành phần composite dựa trên classifier. **ClassifierCompositeItemWriter** chọn writer cho từng item; **ClassifierCompositeItemProcessor** chọn processor tương ứng. Classifier có thể dựa trên một field trực tiếp như type, status hoặc category, hoặc dựa trên business state được suy ra từ nhiều thuộc tính.

Điểm quan trọng là classifier chỉ quyết định item đi theo nhánh nào. Nó không tự tạo thêm Step, không thay đổi transaction boundary và không bảo đảm side effect của mọi delegate được rollback cùng nhau. Khi định tuyến tới nhiều file, database hoặc hệ thống ngoài, cần thiết kế resource lifecycle, tính idempotent và cách publish output phù hợp.

Bài học này giải thích Classifier, cách phân loại theo field và business state, cách cấu hình writer/processor routing, cách xử lý giá trị không hợp lệ, vai trò của ItemStream delegate, ảnh hưởng đến chunk và transaction, cùng chiến lược kiểm thử.

Ví dụ cấu hình sử dụng API chunk-based của Spring Batch 5. Với Spring Batch 4, một số API writer sử dụng List thay cho Chunk; cần điều chỉnh theo version của dự án.

## 1. Bài toán định tuyến item

Giả sử Job nhập các đơn hàng từ một nguồn chung. Mỗi Order có trạng thái:

~~~text
orderId,status,total
O-1001,PAID,120.00
O-1002,CANCELLED,75.00
O-1003,REVIEW,980.00
O-1004,PAID,45.00
~~~

Yêu cầu đầu ra:

- PAID được ghi vào paid-orders.csv.
- CANCELLED được ghi vào cancelled-orders.csv.
- REVIEW được ghi vào review-orders.csv.

Nếu dùng một writer thông thường, writer phải tự kiểm tra status rồi ghi vào đúng resource. Có thể làm vậy bằng custom ItemWriter, nhưng khi số nhánh tăng hoặc cần thay đổi logic định tuyến, code sẽ nhanh chóng trở nên khó quản lý.

Classifier tách quyết định phân loại ra khỏi writer. Mỗi item được đưa cho classifier; classifier trả về delegate phù hợp; composite writer chuyển item cho delegate đó.

~~~mermaid
flowchart TD
    A["ItemReader"] --> B["ItemProcessor (optional)"]
    B --> C["ClassifierCompositeItemWriter"]
    C --> D{"Classifier"}
    D -->|PAID| E["Paid writer"]
    D -->|CANCELLED| F["Cancelled writer"]
    D -->|REVIEW| G["Review writer"]
~~~

Mỗi item vẫn thuộc cùng Step và cùng luồng chunk. Việc định tuyến không tự tạo một JobExecution hoặc StepExecution mới.

## 2. Classifier là gì?

Spring Framework cung cấp interface Classifier để ánh xạ một đối tượng đầu vào sang một kết quả:

~~~java
public interface Classifier<C, T> extends Serializable {
    T classify(C classifiable);
}
~~~

Trong đó:

- C là kiểu đối tượng cần phân loại.
- T là kết quả phân loại, thường là một delegate như ItemWriter hoặc ItemProcessor.
- classify() nhận một đối tượng và trả về nhánh được chọn.

Classifier có thể được viết bằng lambda:

~~~java
Classifier<Order, String> classifier =
    order -> order.status().name();
~~~

Hoặc triển khai thành class riêng:

~~~java
public class OrderStatusClassifier
        implements Classifier<Order, String> {

    @Override
    public String classify(Order order) {
        return order.status().name();
    }
}
~~~

Classifier không bắt buộc trả về String hoặc enum. Nó có thể trả về bất kỳ kiểu nào phù hợp với mục đích sử dụng. Với composite writer, kết quả thường là một ItemWriter; với composite processor, kết quả là một ItemProcessor.

### Classifier nên là logic quyết định thuần

Một classifier tốt thường:

- Đọc field hoặc trạng thái đã có trên item.
- Trả cùng kết quả khi nhận cùng input.
- Không sửa đổi item.
- Không ghi database hoặc gọi API.
- Không giữ state phụ thuộc thứ tự item.
- Xử lý rõ null và giá trị không nhận diện được.

Nếu cần gọi dịch vụ để xác định risk level, hãy thực hiện việc enrichment trong processor trước, sau đó classifier đọc risk level đã được gắn vào item. Gọi API bên trong classifier khiến việc định tuyến có side effect và khó dự đoán khi retry.

## 3. Phân loại theo field trực tiếp

Cách đơn giản nhất là định tuyến theo một field có sẵn.

Ví dụ model:

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED,
    REVIEW
}

public record Order(
    String orderId,
    OrderStatus status,
    BigDecimal total
) {
}
~~~

Classifier theo status:

~~~java
Classifier<Order, OrderStatus> statusClassifier =
    Order::status;
~~~

Có thể dùng kết quả enum để chọn writer:

~~~java
ItemWriter<Order> selectWriter(Order order) {
    return switch (order.status()) {
        case PAID -> paidWriter;
        case CANCELLED -> cancelledWriter;
        case REVIEW -> reviewWriter;
        case NEW -> newOrderWriter;
    };
}
~~~

Enum giúp giới hạn tập giá trị hợp lệ và làm rõ các nhánh cần xử lý. Nếu dữ liệu đầu vào đến từ chuỗi như "paid", "Paid" hoặc "PAID", nên chuẩn hóa và parse thành enum trước khi định tuyến.

### Phân loại theo type hoặc category

Cùng cách này có thể áp dụng cho customer type (INDIVIDUAL, BUSINESS), payment method (CARD, BANK_TRANSFER, CASH), record category (HEADER, DETAIL, TRAILER), source system (CRM, ERP, PARTNER) hoặc priority (HIGH, NORMAL, LOW).

Không nên dùng chuỗi tùy ý xuyên suốt pipeline nếu tập giá trị có thể được biểu diễn bằng enum hoặc kiểu miền rõ ràng. Kiểu dữ liệu rõ giúp compiler và test phát hiện nhánh thiếu.

## 4. Phân loại theo nhiều field

Một quyết định định tuyến có thể phụ thuộc nhiều field. Ví dụ đơn hàng chỉ vào nhánh HIGH_VALUE khi status là PAID và total đạt ngưỡng.

~~~java
Classifier<Order, String> routeClassifier = order -> {
    if (order.status() == OrderStatus.CANCELLED) {
        return "CANCELLED";
    }

    if (order.status() == OrderStatus.PAID
            && order.total().compareTo(
                new BigDecimal("1000.00")
            ) >= 0) {
        return "HIGH_VALUE";
    }

    if (order.status() == OrderStatus.PAID) {
        return "PAID";
    }

    return "PENDING";
};
~~~

Thứ tự điều kiện có ý nghĩa. Nếu kiểm tra PAID trước điều kiện HIGH_VALUE, mọi đơn đã thanh toán sẽ bị định tuyến vào PAID và nhánh HIGH_VALUE không bao giờ được chọn.

Khi có nhiều điều kiện, hãy thể hiện rõ thứ tự ưu tiên và kiểm thử các boundary value.

### Dùng method riêng cho business rule

Không nên để lambda dài chứa nhiều quy tắc nghiệp vụ. Có thể tách thành method:

~~~java
public OrderRoute classifyOrder(Order order) {
    if (order.status() == OrderStatus.CANCELLED) {
        return OrderRoute.CANCELLED;
    }

    if (order.status() == OrderStatus.PAID
            && order.total().compareTo(highValueLimit) >= 0) {
        return OrderRoute.HIGH_VALUE;
    }

    if (order.status() == OrderStatus.PAID) {
        return OrderRoute.PAID;
    }

    return OrderRoute.PENDING;
}
~~~

Sau đó classifier chỉ gọi method này. Business rule có thể được unit test độc lập với Spring Batch.

## 5. Field và business state khác nhau thế nào?

Field là dữ liệu trực tiếp có trên object, ví dụ status, type, region hoặc total. Business state có thể được suy ra từ nhiều field và ngữ cảnh.

Ví dụ:

- Một đơn có status PAID, nhưng bị đánh dấu fraudHold.
- Một khách hàng có status ACTIVE, nhưng đã vượt hạn mức tín dụng.
- Một payment có trạng thái RECEIVED, nhưng chưa được đối soát.
- Một record có type STANDARD, nhưng thuộc batch đang chạy chế độ correction.

Business state có thể được mô hình hóa bằng enum riêng:

~~~java
public enum OrderRoute {
    NORMAL,
    HIGH_VALUE,
    MANUAL_REVIEW,
    CANCELLED
}
~~~

Processor hoặc domain service xác định route:

~~~java
public OrderRoute determineRoute(Order order) {
    if (order.isFraudHold()) {
        return OrderRoute.MANUAL_REVIEW;
    }

    if (order.status() == OrderStatus.CANCELLED) {
        return OrderRoute.CANCELLED;
    }

    if (order.status() == OrderStatus.PAID
            && order.total().compareTo(highValueLimit) >= 0) {
        return OrderRoute.HIGH_VALUE;
    }

    return OrderRoute.NORMAL;
}
~~~

Classifier sau đó chỉ dựa vào route đã được tính:

~~~java
Classifier<Order, OrderRoute> classifier =
    Order::route;
~~~

Cách tách này làm cho quyết định nghiệp vụ dễ test, trong khi classifier vẫn đơn giản và không thực hiện enrichment.

## 6. Dùng ClassifierCompositeItemWriter

ClassifierCompositeItemWriter định tuyến từng item tới ItemWriter mà classifier chọn.

Ví dụ cấu hình:

~~~java
@Bean
ClassifierCompositeItemWriter<Order> orderRouterWriter(
        @Qualifier("paidOrdersWriter")
        ItemWriter<Order> paidOrdersWriter,
        @Qualifier("cancelledOrdersWriter")
        ItemWriter<Order> cancelledOrdersWriter,
        @Qualifier("reviewOrdersWriter")
        ItemWriter<Order> reviewOrdersWriter,
        @Qualifier("pendingOrdersWriter")
        ItemWriter<Order> pendingOrdersWriter) {

    return new ClassifierCompositeItemWriterBuilder<Order>()
        .classifier(order -> switch (order.status()) {
            case PAID -> paidOrdersWriter;
            case CANCELLED -> cancelledOrdersWriter;
            case REVIEW -> reviewOrdersWriter;
            case NEW -> pendingOrdersWriter;
        })
        .build();
}
~~~

Builder nhận classifier trả về writer phù hợp. Mỗi item được gửi tới writer tương ứng với trạng thái của chính item đó.

Nếu classifier không thể tìm được delegate, đừng trả null. Hãy định nghĩa nhánh fallback hoặc ném exception rõ ràng để Step xử lý theo policy.

### Writer được chọn cho từng item

Ví dụ chunk có bốn đơn:

~~~text
[O-1001 PAID, O-1002 CANCELLED, O-1003 REVIEW, O-1004 PAID]
~~~

Kết quả định tuyến:

~~~text
paidOrdersWriter:
  O-1001
  O-1004

cancelledOrdersWriter:
  O-1002

reviewOrdersWriter:
  O-1003
~~~

Mỗi item chỉ được chuyển tới writer mà classifier trả về. Nếu cần ghi cùng item vào nhiều đích, ClassifierCompositeItemWriter không phải công cụ fan-out; hãy dùng CompositeItemWriter hoặc một custom writer thực hiện nhiều lần ghi.

## 7. Cấu hình delegate writer

Các delegate có thể là FlatFileItemWriter, JdbcBatchItemWriter hoặc custom ItemWriter.

Ví dụ các file writer:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> paidOrdersWriter(
        @Value("#{jobParameters['paid.output']}") String output) {

    return new FlatFileItemWriterBuilder<Order>()
        .name("paidOrdersWriter")
        .resource(new FileSystemResource(output))
        .lineAggregator(orderLineAggregator())
        .encoding(StandardCharsets.UTF_8.name())
        .saveState(true)
        .build();
}

@Bean
@StepScope
FlatFileItemWriter<Order> cancelledOrdersWriter(
        @Value("#{jobParameters['cancelled.output']}") String output) {

    return new FlatFileItemWriterBuilder<Order>()
        .name("cancelledOrdersWriter")
        .resource(new FileSystemResource(output))
        .lineAggregator(orderLineAggregator())
        .encoding(StandardCharsets.UTF_8.name())
        .saveState(true)
        .build();
}
~~~

Mỗi writer có tên riêng và ổn định, output resource riêng, state riêng để restart, cùng kiểu item Order và cấu hình encoding/line aggregator phù hợp.

Các output path cần khác nhau và phải được xác định ổn định cho cùng JobInstance. Không để hai delegate vô tình ghi vào cùng một file.

## 8. Đăng ký ItemStream delegate với Step

Đây là chi tiết quan trọng khi dùng composite writer.

ClassifierCompositeItemWriter chịu trách nhiệm định tuyến nhưng bản thân nó không quản lý lifecycle ItemStream của mọi delegate. Nếu các delegate như FlatFileItemWriter cần open(), update() và close(), hãy đăng ký chúng với Step.

Ví dụ:

~~~java
@Bean
Step routeOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ClassifierCompositeItemWriter<Order> orderRouterWriter,
        FlatFileItemWriter<Order> paidOrdersWriter,
        FlatFileItemWriter<Order> cancelledOrdersWriter,
        FlatFileItemWriter<Order> reviewOrdersWriter,
        FlatFileItemWriter<Order> pendingOrdersWriter) {

    return new StepBuilder("routeOrdersStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(orderRouterWriter)
        .stream(paidOrdersWriter)
        .stream(cancelledOrdersWriter)
        .stream(reviewOrdersWriter)
        .stream(pendingOrdersWriter)
        .build();
}
~~~

Việc đăng ký stream giúp Spring Batch gọi lifecycle của các delegate và lưu state cần thiết. Nếu bỏ sót một delegate, writer đó có thể vẫn nhận write() nhưng không được mở, cập nhật checkpoint hoặc đóng đúng cách.

### Vì sao không chỉ đăng ký composite?

Composite writer định tuyến đến một delegate tại runtime. Step không nhất thiết tự khám phá mọi ItemStream được giữ bên trong classifier. Vì vậy, hãy đăng ký rõ các stream delegate hoặc dùng một composite tự triển khai ItemStream và chuyển tiếp lifecycle đúng cách.

Nếu delegate không triển khai ItemStream và không giữ resource, không cần đăng ký stream cho nó.

## 9. Phân loại theo business state đã chuẩn hóa

Trong hệ thống thực tế, field đầu vào có thể chưa đủ để quyết định nhánh. Ví dụ trạng thái trong nguồn là chuỗi không chuẩn hóa hoặc phải kết hợp với thông tin từ một service.

Có thể tạo một processor enrichment:

~~~java
@Bean
ItemProcessor<RawOrder, Order> orderEnrichmentProcessor(
        OrderPolicyService policyService) {

    return raw -> {
        Order order = map(raw);
        OrderRoute route = policyService.determineRoute(order);

        return order.withRoute(route);
    };
}
~~~

Sau đó classifier chỉ đọc route:

~~~java
.classifier(order -> switch (order.route()) {
    case NORMAL -> normalWriter;
    case HIGH_VALUE -> highValueWriter;
    case MANUAL_REVIEW -> reviewWriter;
    case CANCELLED -> cancelledWriter;
})
~~~

Lợi ích:

- Business rule nằm trong service hoặc processor có thể test riêng.
- Classifier không gọi API hoặc database.
- Một lần phân loại có kết quả nhất quán.
- Có thể log route đã được xác định trên item.
- Writer chỉ chịu trách nhiệm ghi dữ liệu.

Nếu business state thay đổi theo thời gian, hãy quyết định thời điểm snapshot state. Không để cùng một item được phân loại khác nhau giữa retry chỉ vì classifier đọc một nguồn dữ liệu mutable.

## 10. Dùng ClassifierCompositeItemProcessor

Không phải mọi nhánh định tuyến đều cần writer khác nhau. Đôi khi cùng một loại input cần processor khác nhau theo field hoặc state.

ClassifierCompositeItemProcessor chọn một ItemProcessor cho mỗi input:

~~~java
@Bean
ClassifierCompositeItemProcessor<RawOrder, Order> routedOrderProcessor(
        ItemProcessor<RawOrder, Order> retailProcessor,
        ItemProcessor<RawOrder, Order> wholesaleProcessor,
        ItemProcessor<RawOrder, Order> correctionProcessor) {

    return new ClassifierCompositeItemProcessorBuilder<RawOrder, Order>()
        .classifier(raw -> switch (raw.type()) {
            case "RETAIL" -> retailProcessor;
            case "WHOLESALE" -> wholesaleProcessor;
            case "CORRECTION" -> correctionProcessor;
            default -> throw new IllegalArgumentException(
                "Order type không được hỗ trợ: " + raw.type()
            );
        })
        .build();
}
~~~

Cấu hình Step:

~~~java
return new StepBuilder("processOrdersStep", jobRepository)
    .<RawOrder, Order>chunk(100, transactionManager)
    .reader(rawOrderReader)
    .processor(routedOrderProcessor)
    .writer(orderWriter)
    .build();
~~~

Mỗi processor delegate nhận input item và trả output cùng kiểu Order. Nếu một processor trả null, đó là hành vi filter chuẩn của ItemProcessor: item không được chuyển tới writer.

### Khi nào phân loại ở processor, khi nào ở writer?

| Nhu cầu | Vị trí phù hợp |
|---|---|
| Cùng input nhưng cần quy tắc transform khác | ClassifierCompositeItemProcessor |
| Item đã hoàn chỉnh, chỉ cần chọn đích ghi | ClassifierCompositeItemWriter |
| Cần vừa transform khác nhau vừa ghi khác nhau | Có thể dùng cả hai |
| Cùng item phải ghi vào tất cả đích | CompositeItemWriter |
| Nhánh có quy trình nhiều Step khác nhau | Flow/Job hoặc Step riêng |

Đừng chuyển logic nghiệp vụ sang writer chỉ vì classifier writer thuận tiện. Hãy đặt transformation ở processor và routing output ở writer.

## 11. Phân loại theo field đã parse

Nếu nguồn có status dạng String, hãy chuẩn hóa trước:

~~~java
public OrderStatus parseStatus(String rawStatus) {
    if (rawStatus == null || rawStatus.isBlank()) {
        throw new InvalidOrderStatusException(
            "Thiếu order status"
        );
    }

    try {
        return OrderStatus.valueOf(
            rawStatus.trim().toUpperCase(Locale.ROOT)
        );
    } catch (IllegalArgumentException ex) {
        throw new InvalidOrderStatusException(
            "Order status không hợp lệ: " + rawStatus,
            ex
        );
    }
}
~~~

Không nên để classifier phải xử lý nhiều biến thể chuỗi trong mọi lần gọi. Việc parse và validate thuộc boundary của input hoặc processor.

Với dữ liệu không hợp lệ, có thể skip item theo policy và ghi reject record, route sang quarantine writer nếu muốn giữ raw input, hoặc fail Step nếu giá trị cho thấy cả file/batch sai contract.

Chính sách phải rõ ràng. Không tự chuyển một status không nhận diện thành PAID hoặc một nhánh mặc định có thể gây side effect nghiệp vụ.

## 12. Nhánh fallback và dữ liệu không phân loại được

Classifier cần có cách xử lý cho mọi trạng thái có thể gặp.

Một cách là dùng fallback writer:

~~~java
.classifier(order -> {
    if (order.status() == null) {
        return rejectedOrdersWriter;
    }

    return switch (order.status()) {
        case PAID -> paidOrdersWriter;
        case CANCELLED -> cancelledOrdersWriter;
        case REVIEW -> reviewOrdersWriter;
        case NEW -> pendingOrdersWriter;
    };
})
~~~

Nếu trạng thái null không thể xuất hiện sau validation, có thể fail rõ ràng:

~~~java
.classifier(order -> {
    if (order.status() == null) {
        throw new InvalidOrderStatusException(
            "Không thể định tuyến đơn hàng thiếu status"
        );
    }

    return writerFor(order.status());
})
~~~

Lựa chọn phụ thuộc nghiệp vụ:

- **Reject/quarantine:** cần lưu dữ liệu lỗi để điều tra.
- **Fail:** dữ liệu không hợp lệ khiến toàn bộ batch không thể tiếp tục.
- **Fallback:** trạng thái chưa hỗ trợ vẫn có thể xử lý an toàn ở một nhánh riêng.

Không trả null như một fallback. Composite writer không có delegate hợp lệ để ghi item và có thể gây NullPointerException khó hiểu.

## 13. Phân loại theo ngưỡng và boundary

Một classifier có thể dùng số tiền, số lượng hoặc điểm rủi ro:

~~~java
private OrderRoute classifyByAmount(Order order) {
    BigDecimal amount = order.total();

    if (amount == null || amount.signum() < 0) {
        return OrderRoute.MANUAL_REVIEW;
    }

    if (amount.compareTo(new BigDecimal("10000.00")) >= 0) {
        return OrderRoute.HIGH_VALUE;
    }

    return OrderRoute.NORMAL;
}
~~~

Khi dùng ngưỡng, hãy xác định:

- Ngưỡng có inclusive hay exclusive không?
- Giá trị null được xử lý ra sao?
- Scale và rounding của BigDecimal.
- Currency có giống nhau không?
- Có cần chuyển đổi tỷ giá trước khi phân loại không?
- Ngưỡng lấy từ JobParameters hay cấu hình được snapshot theo JobInstance?

Dùng BigDecimal.compareTo() cho so sánh số tiền thay vì so sánh bằng equals(), vì equals() còn xét scale. Ví dụ 10.0 và 10.00 có cùng giá trị số nhưng không bằng nhau theo equals().

### Test ngay tại boundary

Nếu ngưỡng là 10,000:

| Giá trị | Nhánh mong đợi |
|---:|---|
| 9,999.99 | NORMAL |
| 10,000.00 | HIGH_VALUE |
| 10,000.01 | HIGH_VALUE |
| null | MANUAL_REVIEW hoặc exception |
| -1.00 | MANUAL_REVIEW hoặc exception |

Boundary test ngăn lỗi do dùng nhầm > thay vì >=.

## 14. Phân loại theo business state nhiều bước

Một business state có thể được suy ra từ trạng thái payment, fraud check và thời hạn:

~~~java
public OrderRoute determineRoute(Order order) {
    if (order.isCancelled()) {
        return OrderRoute.CANCELLED;
    }

    if (order.isFraudHold()) {
        return OrderRoute.MANUAL_REVIEW;
    }

    if (!order.isPaid()) {
        return OrderRoute.PENDING_PAYMENT;
    }

    if (order.isPastDue()) {
        return OrderRoute.OVERDUE;
    }

    return OrderRoute.NORMAL;
}
~~~

Thứ tự ưu tiên là một phần của business rule. Đơn vừa cancelled vừa fraudHold sẽ đi nhánh nào? Đoạn code trên quyết định CANCELLED ưu tiên trước. Nếu yêu cầu nghiệp vụ khác, phải đổi rule và test tương ứng.

Nên mô hình hóa rule trong một class có tên rõ như OrderRoutingPolicy thay vì viết nhiều điều kiện rải rác trong cấu hình Spring.

## 15. Phân loại theo field và theo trạng thái đã lưu

Một số ứng dụng có thể lưu cả field gốc và trạng thái xử lý:

~~~java
public record Payment(
    String paymentType,
    PaymentStatus status,
    ReconciliationState reconciliationState
) {
}
~~~

Ví dụ route:

- BANK_TRANSFER và PENDING_RECONCILIATION -> reconciliation writer.
- CARD và SETTLED -> settled card writer.
- FAILED -> failed payment writer.
- REFUNDED -> refund writer.

Không nên suy ra trạng thái chỉ từ paymentType nếu trạng thái đối soát mới quyết định hành động. Hãy dùng field thể hiện state có thẩm quyền hoặc một policy kết hợp nhiều field.

Nếu trạng thái được tính từ nhiều bảng, nên snapshot nó vào item trước khi routing. Điều này giúp classifier thuần và làm kết quả ổn định trong suốt chunk.

## 16. ClassifierCompositeItemWriter và CompositeItemWriter khác nhau

Hai thành phần có mục tiêu khác nhau.

| Thành phần | Hành vi |
|---|---|
| ClassifierCompositeItemWriter | Chọn một writer cho mỗi item |
| CompositeItemWriter | Gửi cùng chunk tới các delegate đã cấu hình |
| Custom routing writer | Có thể nhóm item theo route rồi gọi mỗi delegate một lần |
| FlatFileItemWriter | Ghi item thành dòng trong một file |
| JdbcBatchItemWriter | Ghi item vào database theo batch |

Ví dụ:

- Một Order cần ghi vào đúng một file theo status: ClassifierCompositeItemWriter.
- Một Order cần ghi đồng thời vào audit table và file: CompositeItemWriter hoặc custom fan-out writer.
- Một chunk có nhiều route và cần bulk insert riêng từng nhóm: custom grouping writer có thể hiệu quả hơn.

Không dùng ClassifierCompositeItemWriter khi ý định là broadcast một item đến mọi delegate. Nó là routing, không phải fan-out.

## 17. Ảnh hưởng của routing đến chunk và hiệu năng

ClassifierCompositeItemWriter nhận một chunk từ Step và phân loại từng item. Delegate được chọn nhận item tương ứng; implementation tiêu chuẩn gọi writer theo từng item, nên delegate có thể nhận các lần write với chunk rất nhỏ.

Ví dụ chunk có 100 item, 70 item vào writer A và 30 item vào writer B. Composite có thể gọi delegate nhiều lần, thay vì gọi A một lần với chunk 70 item và B một lần với chunk 30 item.

Điều này có thể ảnh hưởng hiệu năng nếu delegate tối ưu theo batch, ví dụ JdbcBatchItemWriter hoặc writer gọi API.

Nếu cần gom item theo route, có thể triển khai một writer nhóm chunk:

~~~java
public class GroupingRoutingWriter<T> implements ItemWriter<T> {

    private final Classifier<T, ItemWriter<? super T>> classifier;

    public GroupingRoutingWriter(
            Classifier<T, ItemWriter<? super T>> classifier) {
        this.classifier = classifier;
    }

    @Override
    public void write(Chunk<? extends T> items) throws Exception {
        Map<ItemWriter<? super T>, List<T>> groups =
            new LinkedHashMap<>();

        for (T item : items) {
            ItemWriter<? super T> delegate = classifier.classify(item);

            if (delegate == null) {
                throw new IllegalStateException(
                    "Classifier không trả về writer"
                );
            }

            groups.computeIfAbsent(
                delegate,
                ignored -> new ArrayList<>()
            ).add(item);
        }

        for (Map.Entry<ItemWriter<? super T>, List<T>> entry
                : groups.entrySet()) {
            entry.getKey().write(new Chunk<>(entry.getValue()));
        }
    }
}
~~~

Ví dụ này nhóm item theo delegate và gọi mỗi writer một lần cho chunk con. Khi dùng custom writer như vậy, vẫn phải đăng ký các ItemStream delegate với Step và kiểm tra thứ tự ghi, transaction, restart cũng như resource lifecycle.

Không tối ưu grouping trước khi đo hiệu năng. Với file writer hoặc số item nhỏ, ClassifierCompositeItemWriter tiêu chuẩn có thể đơn giản và đủ nhanh.

## 18. Transaction khi nhiều delegate ghi trong một chunk

Classifier không tạo transaction riêng cho từng nhánh. Các lần gọi delegate xảy ra trong quá trình Step xử lý chunk.

Nếu các delegate ghi vào cùng database và tham gia cùng transaction manager, transaction rollback có thể hoàn tác các thay đổi database của chunk.

Nhưng nếu một delegate ghi file rồi delegate tiếp theo ghi database và database thất bại, file đã ghi không tự động được rollback như database transaction.

~~~mermaid
flowchart TD
    A["Chunk bắt đầu transaction"] --> B["Route item 1 đến file writer"]
    B --> C["Route item 2 đến database writer"]
    C --> D{"Database write thành công?"}
    D -->|Có| E["Commit chunk"]
    D -->|Không| F["Rollback transaction database"]
    F --> G["File output có thể đã có dữ liệu"]
~~~

Với output file quan trọng, nên ghi vào staging resource riêng theo JobInstance hoặc run ID. Chỉ publish sau khi toàn bộ Step/Job thành công và file được xác nhận đầy đủ.

Nếu nhiều database hoặc hệ thống ngoài không cùng transaction manager, không giả định một transaction cục bộ có thể rollback mọi side effect. Dùng outbox, idempotency key, staging hoặc workflow bù trừ tùy kiến trúc.

## 19. Restart và state của nhiều delegate

Nếu mỗi delegate là một ItemStreamWriter, mỗi writer cần tên và ExecutionContext key riêng. Ví dụ:

- paidOrdersWriter.
- cancelledOrdersWriter.
- reviewOrdersWriter.

Đăng ký tất cả stream delegate với Step để Spring Batch mở, cập nhật và đóng chúng.

Khi restart:

- Cùng JobInstance phải dùng cùng identifying JobParameters.
- Output resource cần trỏ về đúng file của lần chạy đó.
- Writer name và state key cần ổn định.
- Các delegate phải khôi phục vị trí tương ứng.
- Không để hai JobExecution đồng thời ghi cùng file.
- Nếu classifier rule thay đổi giữa hai lần chạy, phải đánh giá tác động tới item đã ghi và item còn lại.

### Thay đổi classifier giữa restart

Giả sử lần đầu status PAID được ghi vào file A, sau khi deploy phiên bản mới rule PAID được chuyển sang file B. Khi restart JobInstance cũ, phần item chưa xử lý có thể đi vào file B trong khi phần đã commit vẫn nằm ở file A.

Kết quả có thể chia cùng một batch vào hai output theo hai quy tắc khác nhau. Vì vậy, business routing policy cần ổn định trong suốt JobInstance hoặc được version hóa/snapshot theo JobParameters.

Nếu policy thay đổi, có thể cần tạo một JobInstance mới và chạy lại theo quy trình nghiệp vụ có kiểm soát.

## 20. Phân loại và skip/retry

Classifier có thể ném exception khi dữ liệu không hợp lệ hoặc không xác định được route. Exception xảy ra trong processor hoặc writer sẽ được Step xử lý theo fault-tolerance policy tương ứng.

Ví dụ:

~~~java
return new StepBuilder("routeOrdersStep", jobRepository)
    .<OrderInput, Order>chunk(100, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderRouterWriter)
    .faultTolerant()
    .skip(UnknownOrderStatusException.class)
    .skipLimit(20)
    .build();
~~~

Tuy nhiên, cần phân biệt lỗi parse field, business state không hợp lệ, không có writer cho route, lỗi tạm thời của delegate và lỗi ghi file. Nếu classifier nằm trong writer và ném exception, framework có thể xem đó là lỗi write. Đừng chuyển lỗi cấu hình route thành lỗi dữ liệu có thể skip nếu việc skip làm mất item mà không có reject record.

## 21. Không dùng Classifier để chia Job thành nhiều quy trình độc lập

ClassifierCompositeItemWriter phù hợp khi các nhánh chỉ khác đích ghi nhưng vẫn thuộc cùng một Step và cùng chunk lifecycle.

Nếu mỗi trạng thái cần transaction manager riêng, chính sách retry/skip riêng, commit interval riêng, listener/checkpoint riêng, Step flow riêng hoặc lịch chạy độc lập, hãy cân nhắc phân loại trước rồi chạy các Step riêng, hoặc dùng flow/Job có quyết định điều hướng.

Một writer classifier không tạo ra những ranh giới vận hành đó.

## 22. Phân loại trong partitioning

Classifier và partitioning giải quyết hai vấn đề khác nhau.

- Classifier chọn delegate cho từng item.
- Partitioner chia nguồn dữ liệu thành nhiều StepExecution/worker.

Có thể kết hợp cả hai: mỗi worker xử lý một range, rồi writer classifier định tuyến item trong range tới output phù hợp.

Nhưng phải chú ý:

- Mỗi worker cần resource riêng nếu writer có state.
- Không để nhiều partition ghi cùng file mà không có cơ chế đồng bộ.
- Output path nên có partition ID hoặc dùng writer an toàn với concurrency.
- Mỗi worker phải có ExecutionContext riêng.
- Tổng hợp output sau khi manager xác nhận tất cả worker thành công.

Nếu chỉ cần tách file theo trạng thái, không cần partitioning chỉ để tạo các nhánh. Nếu cần tăng throughput bằng parallelism, partitioning cần được thiết kế riêng.

## 23. Kiểm thử classifier độc lập

Business policy nên có unit test riêng. Ví dụ:

~~~java
@Test
void routesPaidHighValueOrderToHighValueRoute() {
    Order order = new Order(
        "O-2001",
        OrderStatus.PAID,
        new BigDecimal("1500.00")
    );

    assertEquals(
        OrderRoute.HIGH_VALUE,
        routingPolicy.classifyOrder(order)
    );
}
~~~

Test các nhánh:

- Mỗi enum value.
- Null status nếu có thể xuất hiện.
- Field rỗng hoặc không hợp lệ.
- Ngưỡng ngay dưới, đúng bằng và ngay trên.
- Nhiều điều kiện đồng thời.
- Trạng thái ưu tiên khi hai rule cùng đúng.
- Giá trị tiền null hoặc âm.

Unit test classifier không cần Spring context nếu policy là class thuần Java.

## 24. Kiểm thử ClassifierCompositeItemWriter

Có thể dùng writer giả ghi item vào các List để xác nhận định tuyến:

~~~java
@Test
void routesItemsToMatchingWriters() throws Exception {
    List<Order> paid = new ArrayList<>();
    List<Order> cancelled = new ArrayList<>();

    ItemWriter<Order> paidWriter =
        chunk -> paid.addAll(chunk.getItems());

    ItemWriter<Order> cancelledWriter =
        chunk -> cancelled.addAll(chunk.getItems());

    ClassifierCompositeItemWriter<Order> router =
        new ClassifierCompositeItemWriterBuilder<Order>()
            .classifier(order -> order.status() == OrderStatus.PAID
                ? paidWriter
                : cancelledWriter)
            .build();

    Chunk<Order> items = new Chunk<>();
    items.add(new Order(
        "O-1", OrderStatus.PAID, new BigDecimal("10.00")
    ));
    items.add(new Order(
        "O-2", OrderStatus.CANCELLED, new BigDecimal("20.00")
    ));
    items.add(new Order(
        "O-3", OrderStatus.PAID, new BigDecimal("30.00")
    ));

    router.write(items);

    assertEquals(List.of("O-1", "O-3"),
        paid.stream().map(Order::orderId).toList());

    assertEquals(List.of("O-2"),
        cancelled.stream().map(Order::orderId).toList());
}
~~~

Test này xác nhận từng item được chuyển tới đúng delegate. Có thể bổ sung writer spy để xác nhận số lần delegate được gọi và kích thước chunk mà nó nhận.

Với ClassifierCompositeItemWriter tiêu chuẩn, không nên giả định delegate nhận một chunk đã gom tất cả item cùng route. Nếu hiệu năng phụ thuộc bulk write, hãy test grouping behavior của custom writer riêng.

## 25. Kiểm thử ClassifierCompositeItemProcessor

Processor composite cũng nên được kiểm tra theo từng nhánh:

~~~java
@Test
void selectsProcessorByInputType() throws Exception {
    ItemProcessor<RawOrder, Order> retail =
        raw -> new Order(raw.id(), OrderStatus.NEW, raw.total());

    ItemProcessor<RawOrder, Order> wholesale =
        raw -> new Order(raw.id(), OrderStatus.REVIEW, raw.total());

    ClassifierCompositeItemProcessor<RawOrder, Order> processor =
        new ClassifierCompositeItemProcessorBuilder<RawOrder, Order>()
            .classifier(raw -> "WHOLESALE".equals(raw.type())
                ? wholesale
                : retail)
            .build();

    Order result = processor.process(
        new RawOrder("O-10", "WHOLESALE", new BigDecimal("50.00"))
    );

    assertEquals(OrderStatus.REVIEW, result.status());
}
~~~

Kiểm tra cả trường hợp processor delegate trả null để xác nhận item được filter theo đúng ý định. Kiểm tra unknown type để bảo đảm fallback hoặc exception rõ ràng.

## 26. Kiểm thử Step integration và output thật

Unit test classifier chưa kiểm tra Spring Batch có mở delegate writer không, ItemStream delegate có được đăng ký đúng không, JobParameters có được bind vào output path không, transaction và StepExecution counters có đúng không, file output có nội dung hợp lệ không, hay restart có khôi phục state của từng writer không.

Dùng **spring-batch-test** và JobLauncherTestUtils để chạy Step thật. Sau khi chạy, kiểm tra:

1. BatchStatus và ExitStatus.
2. Read, write, filter và skip counts.
3. Số item trong từng output.
4. Không có item nằm ở nhiều nhánh nếu yêu cầu exclusive routing.
5. Không có item bị mất.
6. File được đóng và có thể đọc lại.
7. Các delegate stream được mở/đóng đúng lifecycle.

Không chỉ kiểm tra file tồn tại. Parse hoặc đọc lại nội dung để xác nhận đúng item theo từng route.

## 27. Kiểm thử failure và restart của nhiều output

Tạo test có nhiều chunk và cho một delegate thất bại có chủ đích:

1. Chunk đầu ghi một số item vào các output.
2. Chunk tiếp theo gặp lỗi tại một delegate.
3. Xác nhận Step FAILED và transaction rollback theo cấu hình.
4. Kiểm tra file nào đã nhận dữ liệu và có staging/publish policy phù hợp.
5. Restart cùng JobInstance và identifying JobParameters.
6. Xác nhận từng delegate khôi phục checkpoint đúng.
7. Xác nhận không mất hoặc ghi trùng item theo semantics đã thiết kế.
8. Chỉ publish output sau khi toàn bộ Step/Job thành công.

Với database writer trong cùng transaction, kiểm tra rollback bằng dữ liệu trong database. Với file writer, kiểm tra riêng vì filesystem không tự tham gia transaction database.

## 28. Quan sát và audit routing

Trong batch production, cần biết item được route theo quyết định nào khi điều tra dữ liệu.

Có thể ghi log có cấu trúc gồm JobExecution ID, StepExecution ID, business key của item, route đã chọn, routing policy version, delegate/output resource, kết quả ghi và exception.

Tránh log toàn bộ item nếu chứa dữ liệu nhạy cảm. Dùng business key hoặc correlation ID phù hợp.

Nếu cần audit bền vững cho mỗi route, cân nhắc lưu route trong một cột hoặc audit table. Đừng phụ thuộc duy nhất vào log text để tái dựng quyết định nghiệp vụ.

### Snapshot policy version

Nếu routing policy có thể thay đổi, truyền policy version bằng JobParameters hoặc lưu trong JobExecutionContext. Khi restart, kiểm tra version và bảo đảm JobInstance dùng cùng rule.

Ví dụ tham số:

~~~java
.addString("routingPolicyVersion", "v3", true)
~~~

Nếu policy version là identifying parameter, nó tham gia xác định JobInstance. Nếu mục đích chỉ là metadata, có thể đánh dấu non-identifying nhưng vẫn phải bảo đảm lần restart khôi phục cùng giá trị theo thiết kế. Quyết định này cần phù hợp với business identity của batch.

## 29. Các lỗi triển khai thường gặp

### Trả null khi không tìm thấy delegate

Composite không thể ghi item qua null writer. Dùng fallback writer hoặc ném exception có ý nghĩa.

### Chỉ xử lý các trạng thái phổ biến

Một enum hoặc field mới có thể làm classifier thiếu nhánh. Dùng switch exhaustiveness khi có thể và test mọi trạng thái.

### Phân loại bằng chuỗi chưa chuẩn hóa

"paid", "PAID" và "Paid" có thể đi các nhánh khác nhau. Parse và normalize trước khi routing.

### Gọi API trong classifier

Mỗi lần classify có thể gọi lại API khi retry, làm tăng latency và tạo kết quả không ổn định. Enrich trước trong processor.

### Dùng ClassifierCompositeItemWriter để broadcast

Classifier chọn một delegate cho mỗi item. Muốn ghi vào nhiều đích, dùng CompositeItemWriter hoặc custom fan-out.

### Quên đăng ký ItemStream delegate

Delegate vẫn có thể nhận write nhưng không được open/update/close đúng lifecycle. Đăng ký stream với Step.

### Dùng chung output resource

Hai writer có thể ghi đè hoặc xen kẽ dữ liệu. Mỗi delegate cần resource riêng hoặc một cơ chế ghi đồng bộ rõ ràng.

### Nghĩ routing tạo transaction riêng

Mọi delegate vẫn chạy trong chunk lifecycle của Step. Classifier không tạo transaction boundary riêng.

### Giả định file rollback cùng database

File có thể đã được flush dù transaction database rollback. Dùng staging và publish.

### Thay routing rule giữa restart

Item trước và sau restart có thể đi nhánh khác nhau. Version hóa hoặc snapshot policy.

### Dùng writer classifier cho quy trình có lifecycle độc lập

Nếu mỗi route cần retry, transaction hoặc Step flow riêng, hãy mô hình hóa thành Step/flow thay vì chỉ đổi delegate writer.

### Bỏ qua hiệu năng khi delegate nhận từng item

Một writer tối ưu theo batch có thể bị gọi nhiều lần với chunk nhỏ. Đo hiệu năng và cân nhắc grouping writer khi cần.

## 30. Quy trình thiết kế routing theo field hoặc business state

Khi xây dựng định tuyến, có thể thực hiện theo trình tự:

1. **Xác định item:** field nào có thể dùng để phân loại?
2. **Xác định state:** route là field trực tiếp hay business state được suy ra?
3. **Chuẩn hóa dữ liệu:** parse enum, normalize chuỗi và kiểm tra null.
4. **Viết policy:** đưa thứ tự ưu tiên và boundary rule vào method/class có thể test.
5. **Chọn điểm routing:** processor nếu cần transform khác nhau; writer nếu chỉ cần chọn đích ghi.
6. **Khai báo delegate:** mỗi writer/processor có cấu hình và ownership rõ ràng.
7. **Đăng ký stream:** mọi ItemStream delegate cần được Step quản lý.
8. **Thiết kế fallback:** reject, quarantine hoặc fail cho route không hợp lệ.
9. **Kiểm tra transaction:** xác định delegate nào tham gia cùng transaction và output nào cần staging.
10. **Thiết kế restart:** giữ resource, checkpoint và policy version ổn định.
11. **Kiểm thử:** mọi nhánh, boundary, unknown state, failure, restart và output thực tế.
12. **Theo dõi:** log route, execution ID và policy version phù hợp.

## 31. Những điểm cần nhớ

- Classifier ánh xạ một item sang kết quả phân loại, thường là delegate writer hoặc processor.
- Phân loại theo field dùng trực tiếp status, type, category hoặc source.
- Phân loại theo business state có thể kết hợp nhiều field và cần quy tắc ưu tiên rõ ràng.
- Nên normalize và validate dữ liệu trước khi classifier chạy.
- Classifier nên thuần, deterministic và không gọi API/database hoặc tạo side effect.
- ClassifierCompositeItemWriter chọn một writer cho mỗi item.
- ClassifierCompositeItemProcessor chọn processor cho mỗi input item.
- CompositeItemWriter có semantics fan-out, khác với routing.
- ClassifierCompositeItemWriter không tự quản lý lifecycle của mọi ItemStream delegate; đăng ký các stream với Step.
- Routing không tạo Step hoặc transaction boundary riêng.
- File output không tự rollback cùng database transaction; dùng staging và publish.
- Unknown state cần fallback hoặc exception rõ ràng, không trả null.
- Routing policy cần ổn định qua restart hoặc được version hóa.
- Classifier writer tiêu chuẩn có thể gọi delegate theo từng item; cân nhắc grouping nếu cần bulk write.
- Kiểm thử mọi nhánh, boundary, delegate lifecycle, output thật và restart.

Classifier giúp tách quyết định định tuyến khỏi logic đọc và ghi dữ liệu. Khi field được chuẩn hóa, business state được tính nhất quán, delegate có lifecycle rõ ràng và output được kiểm soát theo transaction/restart, một Step có thể xử lý nhiều loại item mà vẫn giữ được luồng batch dễ hiểu và dễ kiểm thử.

