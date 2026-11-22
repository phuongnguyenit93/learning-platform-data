# Chain nhiều processor

Trong Spring Batch, một `ItemProcessor` nhận một item đầu vào, thực hiện chuyển đổi hoặc kiểm tra rồi trả về item đầu ra. Khi một bước xử lý cần nhiều công đoạn liên tiếp, có thể ghép nhiều processor thành một chuỗi. Mỗi processor đảm nhiệm một việc nhỏ, còn output của processor trước trở thành input của processor tiếp theo.

Ví dụ, khi nhập đơn hàng, một chuỗi processor có thể chuẩn hóa dữ liệu, bổ sung thông tin khách hàng, kiểm tra quy tắc nghiệp vụ và tạo đối tượng sẵn sàng ghi xuống database. Cách tổ chức này giúp tách logic thành các thành phần có trách nhiệm rõ ràng và có thể kiểm thử riêng.

Spring Batch cung cấp `CompositeItemProcessor` và `CompositeItemProcessorBuilder` để thực hiện chuỗi này. Các delegate được gọi theo thứ tự khai báo cho từng item. Chuỗi chạy bên trong cùng một step và cùng quy trình chunk; nó không tự tạo thêm step, transaction hoặc checkpoint riêng cho từng processor.

## 1. Vì sao cần chain nhiều processor?

Một processor lớn thường nhanh chóng tích tụ nhiều trách nhiệm: chuẩn hóa chuỗi, tra cứu dữ liệu tham chiếu, tính toán, kiểm tra điều kiện và ánh xạ sang mô hình ghi. Khi mọi logic nằm trong một phương thức, việc đọc, kiểm thử và thay đổi quy tắc trở nên khó khăn.

Có thể tách các công đoạn như sau:

1. **Normalize:** làm sạch và chuẩn hóa dữ liệu đầu vào.
2. **Enrich:** bổ sung thông tin từ hệ thống hoặc repository khác.
3. **Validate:** kiểm tra điều kiện nghiệp vụ.
4. **Transform:** tạo kiểu dữ liệu cuối cùng mà writer cần.

Ví dụ với đơn hàng:

```mermaid
flowchart LR
    A[OrderInput] --> B[Normalize]
    B --> C[Enrich customer]
    C --> D[Validate]
    D --> E[ApprovedOrder]
    E --> F[ItemWriter]
```

Mỗi delegate tập trung vào một bước biến đổi. Nếu quy tắc chuẩn hóa thay đổi, chỉ cần thay đổi processor tương ứng. Nếu cần kiểm tra processor riêng, có thể viết unit test cho delegate đó mà không phải khởi chạy toàn bộ job.

Chain phù hợp khi các công đoạn là một pipeline xử lý item liên tục, có quan hệ input/output rõ ràng. Nếu các giai đoạn có ranh giới transaction, checkpoint, điều kiện điều khiển hoặc cách restart riêng, hãy cân nhắc tách thành nhiều step thay vì chỉ ghép processor.

## 2. Cách CompositeItemProcessor hoạt động

`CompositeItemProcessor<I, O>` là một `ItemProcessor` bao bọc nhiều processor khác. Khi nhận một item, nó gọi từng delegate theo thứ tự:

1. Delegate đầu tiên nhận item gốc.
2. Output của delegate đầu tiên được chuyển cho delegate thứ hai.
3. Output tiếp tục đi qua các delegate kế tiếp.
4. Output của delegate cuối cùng trở thành kết quả của composite processor.

Giả sử có ba processor:

```java
ItemProcessor<OrderInput, NormalizedOrder> normalize;
ItemProcessor<NormalizedOrder, EnrichedOrder> enrich;
ItemProcessor<EnrichedOrder, ApprovedOrder> validate;
```

Luồng kiểu dữ liệu sẽ là:

```text
OrderInput
    -> NormalizedOrder
    -> EnrichedOrder
    -> ApprovedOrder
```

Các kiểu generic thể hiện hợp đồng giữa các bước. Output của một delegate phải tương thích với input của delegate tiếp theo. Khi khai báo kiểu cụ thể, compiler giúp phát hiện nhiều lỗi nối sai kiểu ngay từ lúc biên dịch.

Điểm quan trọng là chain chạy cho từng item. Với 3 delegate và 100 item trong một chunk, Spring Batch thực hiện chuỗi xử lý cho từng item theo thứ tự delegate, sau đó writer nhận các kết quả còn lại của chunk. Nó không chạy delegate thứ nhất cho toàn bộ 100 item rồi mới chạy delegate thứ hai cho toàn bộ chunk.

## 3. Tạo chain bằng CompositeItemProcessorBuilder

Trong Spring Batch 5+, có thể dùng `CompositeItemProcessorBuilder` để khai báo danh sách delegate. Ví dụ dưới đây dùng ba processor có kiểu đầu vào/đầu ra nối tiếp nhau:

```java
@Bean
ItemProcessor<OrderInput, ApprovedOrder> orderProcessor(
        ItemProcessor<OrderInput, NormalizedOrder> normalizeOrder,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichOrder,
        ItemProcessor<EnrichedOrder, ApprovedOrder> validateOrder) {

    return new CompositeItemProcessorBuilder<OrderInput, ApprovedOrder>()
            .delegates(List.of(
                    normalizeOrder,
                    enrichOrder,
                    validateOrder))
            .build();
}
```

Các delegate được gọi theo đúng thứ tự trong `List.of(...)`. Không nên dựa vào thứ tự lấy bean từ application context hoặc thứ tự alphabet của tên bean; hãy khai báo thứ tự xử lý một cách tường minh.

`CompositeItemProcessorBuilder` kiểm tra cấu hình khi build composite. Kiểu generic đầu vào `OrderInput` và đầu ra `ApprovedOrder` mô tả hợp đồng ngoài của cả chuỗi; từng delegate vẫn cần có input/output tương thích với delegate đứng cạnh nó.

Nếu đang dùng phiên bản Spring Batch cũ hoặc muốn cấu hình trực tiếp, có thể tạo `CompositeItemProcessor` và gọi `setDelegates(...)`. Với ứng dụng mới, builder giúp cấu hình rõ ràng và kiểm tra cấu hình khi khởi tạo bean.

## 4. Ví dụ các delegate trong pipeline đơn hàng

Để thấy rõ vai trò từng processor, giả sử dữ liệu đầu vào có các trường `orderId`, `customerId` và `amount`.

Các kiểu dữ liệu minh họa:

```java
public record OrderInput(
        String orderId,
        String customerId,
        BigDecimal amount) {}

public record NormalizedOrder(
        String orderId,
        String customerId,
        BigDecimal amount) {}

public record EnrichedOrder(
        NormalizedOrder order,
        String customerTier) {}

public record ApprovedOrder(
        String orderId,
        String customerId,
        BigDecimal amount,
        String customerTier) {}
```

### 4.1. Processor chuẩn hóa dữ liệu

Processor đầu tiên làm sạch chuỗi và chuẩn hóa mã khách hàng:

```java
@Bean
ItemProcessor<OrderInput, NormalizedOrder> normalizeOrder() {
    return input -> new NormalizedOrder(
            input.orderId().trim(),
            input.customerId().trim().toUpperCase(Locale.ROOT),
            input.amount());
}
```

Processor này chỉ chuyển đổi dữ liệu đã có. Nó không cần biết thông tin khách hàng hoặc cách writer lưu đơn hàng.

### 4.2. Processor bổ sung dữ liệu

Processor thứ hai tra cứu phân hạng khách hàng để làm giàu dữ liệu:

```java
@Bean
ItemProcessor<NormalizedOrder, EnrichedOrder> enrichOrder(
        CustomerService customerService) {

    return order -> {
        Customer customer =
                customerService.findRequired(order.customerId());

        return new EnrichedOrder(order, customer.tier());
    };
}
```

Processor này phụ thuộc `CustomerService`, nhưng không cần biết file đầu vào được đọc thế nào hoặc kết quả được ghi vào bảng nào. Nếu dịch vụ khách hàng gặp lỗi tạm thời, chính sách retry ở step có thể quyết định có thử lại hay không.

### 4.3. Processor kiểm tra và tạo kết quả cuối

Processor cuối kiểm tra quy tắc nghiệp vụ rồi chuyển sang kiểu writer cần:

```java
@Bean
ItemProcessor<EnrichedOrder, ApprovedOrder> validateOrder() {
    return enriched -> {
        if (enriched.order().amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return new ApprovedOrder(
                enriched.order().orderId(),
                enriched.order().customerId(),
                enriched.order().amount(),
                enriched.customerTier());
    };
}
```

Ở đây, dữ liệu không hợp lệ làm processor ném `InvalidOrderException`. Step có thể được cấu hình để skip loại lỗi này nếu nghiệp vụ cho phép, hoặc để job thất bại nếu dữ liệu cần được xử lý thủ công. Không nên biến mọi lỗi validation thành `null` vì `null` có ý nghĩa filter item, không phải báo lỗi.

### 4.4. Ghép các processor

Sau khi có ba bean delegate, ghép chúng thành một processor duy nhất:

```java
@Bean
ItemProcessor<OrderInput, ApprovedOrder> orderProcessor(
        ItemProcessor<OrderInput, NormalizedOrder> normalizeOrder,
        ItemProcessor<NormalizedOrder, EnrichedOrder> enrichOrder,
        ItemProcessor<EnrichedOrder, ApprovedOrder> validateOrder) {

    return new CompositeItemProcessorBuilder<OrderInput, ApprovedOrder>()
            .delegates(List.of(
                    normalizeOrder,
                    enrichOrder,
                    validateOrder))
            .build();
}
```

Kết quả cuối cùng là một `ItemProcessor<OrderInput, ApprovedOrder>`. Step không cần biết bên trong có bao nhiêu delegate; nó chỉ cần biết kiểu input và output của composite.

## 5. Đưa chain vào chunk-oriented step

Composite processor được cấu hình cho step giống như một processor thông thường:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, ApprovedOrder> orderProcessor,
        ItemWriter<ApprovedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, ApprovedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(orderProcessor)
            .writer(writer)
            .build();
}
```

Reader cung cấp `OrderInput`; composite xử lý qua các delegate và trả `ApprovedOrder`; writer nhận các `ApprovedOrder` còn lại trong chunk. Transaction vẫn do step quản lý. Composite không tạo transaction riêng cho từng delegate.

Nếu một delegate ném exception, exception truyền ra khỏi composite và step áp dụng chính sách lỗi đã cấu hình. Nếu delegate trả `null`, composite dừng chuỗi cho item đó và item bị filter; các delegate đứng sau không được gọi cho item này.

## 6. Ý nghĩa của kết quả null trong processor chain

Theo hợp đồng `ItemProcessor`, trả về `null` có nghĩa item được filter và không được chuyển tiếp tới writer. `CompositeItemProcessor` giữ nguyên ý nghĩa này: khi một delegate trả về `null`, composite không gọi các delegate tiếp theo cho item đó.

Ví dụ:

```java
ItemProcessor<NormalizedOrder, EnrichedOrder> filterTestOrders = order -> {
    if (order.orderId().startsWith("TEST-")) {
        return null;
    }
    return enrich(order);
};
```

Nếu delegate này nằm ở giữa chain, đơn hàng có mã `TEST-` sẽ không được đưa qua bước validation hoặc mapping phía sau và không đến writer.

Chỉ dùng `null` khi chủ đích là bỏ item khỏi luồng xử lý. Nếu dữ liệu không hợp lệ cần được ghi nhận, điều tra hoặc xử lý lại, hãy ném exception phù hợp, tạo một kiểu kết quả biểu diễn trạng thái từ chối, hoặc ghi thông tin lỗi theo một cơ chế nghiệp vụ rõ ràng.

Phân biệt ba trường hợp:

| Kết quả của delegate | Ý nghĩa trong chain |
|---|---|
| Trả về object | Object trở thành input của delegate tiếp theo |
| Trả về `null` | Filter item; dừng chain cho item đó; writer không nhận item |
| Ném exception | Chain dừng do lỗi; step áp dụng retry, skip hoặc fail theo cấu hình |

## 7. Thứ tự delegate ảnh hưởng đến kết quả

Thứ tự các processor là một phần của quy tắc nghiệp vụ. Chẳng hạn, chuẩn hóa mã khách hàng cần xảy ra trước khi tra cứu khách hàng nếu repository yêu cầu mã ở dạng uppercase. Validation số tiền có thể thực hiện trước khi gọi dịch vụ bên ngoài để tránh tra cứu không cần thiết cho item chắc chắn bị từ chối.

Ví dụ hai thứ tự khác nhau:

```text
Normalize -> Enrich -> Validate
```

và

```text
Enrich -> Normalize -> Validate
```

Hai chain này có thể cho kết quả khác nhau nếu `Enrich` phụ thuộc vào định dạng mã khách hàng. Vì vậy, hãy sắp xếp theo phụ thuộc dữ liệu và mục tiêu nghiệp vụ, không chỉ theo tên processor.

Một số gợi ý tổ chức:

- Chuẩn hóa định dạng và loại bỏ khoảng trắng trước khi tra cứu.
- Kiểm tra cấu trúc hoặc trường bắt buộc trước các thao tác tốn chi phí.
- Làm giàu dữ liệu sau khi có khóa tham chiếu hợp lệ.
- Kiểm tra quy tắc nghiệp vụ sau khi đã có đủ dữ liệu cần thiết.
- Ánh xạ sang kiểu writer cần ở cuối chuỗi.

Không phải mọi pipeline đều cần đúng thứ tự trên. Hãy xác định rõ input/output và phụ thuộc của từng delegate trong miền nghiệp vụ cụ thể.

## 8. Chain processor và xử lý lỗi

`CompositeItemProcessor` không tự định nghĩa retry hoặc skip. Nó chỉ điều phối các delegate. Khi delegate ném exception, step nhận exception đó và áp dụng chính sách fault tolerance nếu được cấu hình.

Ví dụ:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, ApprovedOrder> orderProcessor,
        ItemWriter<ApprovedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, ApprovedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(orderProcessor)
            .writer(writer)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

Trong ví dụ, lỗi validation được phép skip trong giới hạn 50 item; lỗi truy cập dữ liệu tạm thời có thể được retry tối đa theo giới hạn đã cấu hình. Cần xác minh exception thực tế được ném ra từ delegate và cân nhắc backoff cho lỗi tạm thời.

Một số nguyên tắc:

- Chỉ skip exception đại diện cho dữ liệu có thể từ chối theo quy tắc nghiệp vụ.
- Chỉ retry lỗi có khả năng tự hết, ví dụ deadlock hoặc lỗi kết nối tạm thời.
- Không retry vô hạn lỗi validation không thể tự sửa.
- Nếu một delegate gọi API hoặc ghi side effect, phải tính đến việc delegate có thể được gọi lại khi chunk rollback hoặc retry.
- Không cấu hình skip mọi `Exception` nếu chưa hiểu rõ hậu quả; có thể che giấu lỗi lập trình và lỗi hạ tầng.

## 9. Giữ processor đơn giản, ít side effect

Processor thường nên tập trung vào chuyển đổi, làm giàu và kiểm tra dữ liệu. Nếu có thể, hãy thiết kế processor theo hướng stateless và deterministic: cùng input cùng dữ liệu tham chiếu sẽ tạo cùng output.

Tránh thực hiện side effect khó lặp lại trong processor, chẳng hạn trừ tiền, gửi email hoặc phát thông điệp trực tiếp. Processor có thể được gọi lại khi retry hoặc khi chunk rollback. Nếu cần tích hợp hệ thống ngoài, hãy cân nhắc lưu ý định gửi vào outbox trong transaction nghiệp vụ, rồi phát thông điệp bằng một thành phần chuyên trách.

Nếu processor cần tra cứu database hoặc service, hãy cân nhắc chi phí gọi cho từng item. Ví dụ, 100 item có thể tạo 100 truy vấn bổ sung. Có thể dùng cache có giới hạn, bulk lookup theo thiết kế phù hợp hoặc đưa dữ liệu tham chiếu vào bước chuẩn bị riêng. Cần bảo đảm cache không làm sai tính nhất quán hoặc giữ dữ liệu lỗi thời ngoài mong muốn.

Không nên để processor phụ thuộc vào `HttpServletRequest`, request-scoped bean hoặc thread-local của request. Job có thể chạy nền lâu sau khi HTTP request kết thúc. Hãy truyền các tham số cần thiết qua `JobParameters`, context phù hợp hoặc kho dữ liệu nghiệp vụ.

## 10. Thread safety và scope của delegate

Trong step tuần tự, các delegate thường được gọi tuần tự trên cùng luồng xử lý của step. Tuy nhiên, nếu step dùng multi-threading hoặc cấu hình xử lý song song, cùng một processor bean có thể được nhiều thread gọi đồng thời tùy cấu trúc step.

Do đó:

- Ưu tiên processor stateless, không giữ dữ liệu riêng của từng item trong field mutable.
- Nếu cần cache, dùng cấu trúc an toàn luồng và giới hạn dung lượng.
- Không lưu biến tạm của một item vào field của singleton processor.
- Nếu delegate có state gắn với step, xem xét `@StepScope` và lifecycle phù hợp.
- Nếu delegate tự triển khai `ItemStream`, bảo đảm Spring Batch biết và quản lý lifecycle của stream đó.

Một lưu ý khi dùng composite: bản thân `CompositeItemProcessor` chủ yếu điều phối danh sách delegate; không nên giả định nó tự động chuyển tiếp mọi lifecycle tùy chỉnh của các delegate. Nếu delegate cần được Spring Batch gọi `open()`, `update()` hoặc `close()`, cần đăng ký stream đó với step bằng `.stream(delegate)` hoặc dùng wrapper chuyển tiếp `ItemStream` đầy đủ. Tránh đăng ký trùng khiến callback bị gọi nhiều lần.

## 11. Khi nào nên dùng nhiều processor và khi nào nên tách nhiều step?

Chain nhiều processor và job nhiều step giải quyết hai nhu cầu khác nhau.

| Tiêu chí | Chain nhiều processor | Nhiều step |
|---|---|---|
| Mục đích | Tách các phép biến đổi/kiểm tra trên một item | Tách các giai đoạn của quy trình batch |
| Luồng dữ liệu | Output delegate trước sang input delegate sau | Step sau bắt đầu khi flow cho phép |
| Transaction | Vẫn thuộc transaction của chunk step | Mỗi step/chunk có ranh giới transaction riêng |
| Checkpoint | Checkpoint do step quản lý, không có checkpoint riêng cho mỗi delegate | Có metadata và trạng thái riêng cho từng step |
| Restart | Restart step theo checkpoint của reader/step | Có thể tiếp tục ở step chưa hoàn thành theo flow và cấu hình restart |
| Điều kiện chuyển | Logic trong processor hoặc filter/exception | Transition, decider hoặc flow của job |

Hãy dùng chain khi các công đoạn chỉ là các phép biến đổi liên tiếp trên cùng item và cần cùng vòng đời step. Hãy tách step khi giai đoạn cần commit riêng, checkpoint riêng, điều kiện chuyển tiếp, tài nguyên hoặc quy trình phục hồi độc lập.

Ví dụ, chuẩn hóa địa chỉ, tra cứu phân hạng khách hàng và kiểm tra hạn mức cho một đơn hàng có thể là một chain. Nhưng tải file, nhập dữ liệu, đối soát tổng tiền và gửi kết quả cho hệ thống khác thường là những giai đoạn nghiệp vụ phù hợp với nhiều step.

## 12. Kiểm thử chain nhiều processor

Nên kiểm thử từng delegate và cả composite:

1. **Unit test delegate:** xác nhận chuẩn hóa, làm giàu và validation hoạt động độc lập.
2. **Kiểm tra thứ tự:** xác nhận output của delegate trước được truyền đúng cho delegate sau.
3. **Kiểm tra kiểu dữ liệu:** bảo đảm input/output generic của các delegate tương thích.
4. **Kiểm tra filter:** một delegate trả `null` thì các delegate sau không được gọi và writer không nhận item đó.
5. **Kiểm tra exception:** exception được truyền ra ngoài composite và step áp dụng skip/retry đúng cấu hình.
6. **Kiểm tra dữ liệu biên:** chuỗi rỗng, mã không tồn tại, số tiền bằng 0/âm, dữ liệu lớn hoặc thiếu trường.
7. **Kiểm tra hiệu năng:** đo số lần gọi service/database trong mỗi chunk và chi phí của từng delegate.
8. **Kiểm tra song song:** nếu step chạy đa luồng, xác nhận delegate không bị race condition hoặc chia sẻ state sai cách.
9. **Kiểm tra restart:** xác nhận processor có thể được gọi lại mà không tạo side effect trùng.

Ví dụ unit test cho composite có thể dùng các processor nhỏ với output xác định, sau đó kiểm tra kết quả cuối. Với test tích hợp, dùng `JobLauncherTestUtils` hoặc cơ chế khởi chạy job phù hợp để xác nhận toàn bộ reader → composite processor → writer hoạt động đúng trong transaction của step.

## 13. Những lỗi thường gặp

**Đảo thứ tự delegate.** Processor làm giàu dữ liệu có thể tra cứu bằng mã chưa chuẩn hóa. Khai báo thứ tự rõ ràng theo phụ thuộc dữ liệu.

**Nối sai kiểu input/output.** Dùng raw type hoặc ép kiểu không an toàn có thể che giấu lỗi nối chuỗi. Khai báo generic cụ thể cho từng delegate.

**Trả `null` khi validation thất bại.** `null` có nghĩa filter item, không tự ghi nhận lý do từ chối. Dùng exception hoặc mô hình kết quả nghiệp vụ nếu cần truy vết.

**Nhồi nhiều trách nhiệm vào một delegate.** Delegate lớn làm mất lợi ích của việc tách pipeline. Mỗi processor nên có một trách nhiệm rõ ràng.

**Cho rằng mỗi processor là một step.** Composite chạy bên trong một step và dùng cùng ranh giới transaction/checkpoint. Muốn ranh giới thực thi riêng, hãy tạo step riêng.

**Thực hiện side effect không idempotent.** Retry hoặc rollback có thể làm delegate được gọi lại. Dùng transaction, unique key, outbox hoặc idempotency key phù hợp.

**Dùng mutable singleton trong step đa luồng.** Field dùng chung có thể làm dữ liệu item này ghi đè item khác. Ưu tiên stateless hoặc quản lý scope/thread safety đúng cách.

**Quên đăng ký delegate triển khai ItemStream.** Composite có thể che khuất lifecycle của delegate. Đăng ký stream riêng hoặc chuyển tiếp đầy đủ callback.

## Kết luận

Chain nhiều processor giúp chia một pipeline xử lý item thành các công đoạn nhỏ, có kiểu input/output rõ ràng và có thể kiểm thử độc lập. `CompositeItemProcessorBuilder` cho phép ghép các delegate theo thứ tự; output của mỗi delegate trở thành input của delegate tiếp theo. Nếu một delegate trả `null`, item bị filter và chain dừng cho item đó; nếu ném exception, step áp dụng chính sách retry, skip hoặc fail.

Hãy giữ processor tập trung vào chuyển đổi, làm giàu và validation; hạn chế side effect; bảo đảm thứ tự và kiểu dữ liệu của delegate; đồng thời chú ý thread safety và lifecycle khi dùng step đa luồng hoặc delegate triển khai `ItemStream`. Dùng chain cho các phép biến đổi liên tiếp trên item, còn dùng nhiều step khi cần ranh giới transaction, checkpoint, điều khiển luồng hoặc phục hồi độc lập.
