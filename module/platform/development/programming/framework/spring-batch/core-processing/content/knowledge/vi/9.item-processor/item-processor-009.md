# Processor idempotent

Trong Spring Batch, `ItemProcessor<I, O>` nhận một item đầu vào, áp dụng quy tắc xử lý và trả về item đầu ra. Một processor tốt nên có khả năng xử lý lại cùng một item mà không tạo ra kết quả sai hoặc tác dụng phụ ngoài ý muốn. Đó là ý nghĩa thực tế của việc thiết kế **processor idempotent**.

Trong batch processing, một item có thể được xử lý lại do retry, rollback, restart hoặc do ứng dụng gửi lại cùng yêu cầu. Nếu processor phụ thuộc vào số lần được gọi, thời điểm hiện tại hoặc thay đổi trạng thái bên ngoài mỗi lần chạy, kết quả có thể khác nhau. Thiết kế processor có tính lặp an toàn giúp job dễ phục hồi và dễ dự đoán hơn.

## 1. Idempotent là gì?

Trong xử lý phần mềm, một thao tác được gọi là idempotent khi thực hiện một lần hay nhiều lần với cùng điều kiện đều dẫn đến cùng kết quả cuối cùng. Với processor, điều quan trọng là cùng một item và cùng dữ liệu tham chiếu phải tạo ra cùng kết quả xử lý, đồng thời việc gọi lại không tạo thêm tác dụng phụ.

Ví dụ chuẩn hóa mã đơn hàng:

```java
String normalize(String value) {
    return value.trim().toUpperCase(Locale.ROOT);
}
```

Gọi hàm với `"  ab-123 "` luôn trả về `"AB-123"`. Nếu áp dụng lại trên kết quả `"AB-123"`, kết quả vẫn không thay đổi:

```text
normalize("  ab-123 ")  -> "AB-123"
normalize("AB-123")    -> "AB-123"
```

Đây là một phép biến đổi có tính idempotent theo nghĩa toán học: áp dụng lại không làm thay đổi kết quả đã chuẩn hóa.

Trong `ItemProcessor`, thường cần hai thuộc tính liên quan:

- **Deterministic:** cùng đầu vào và cùng các dữ liệu tham chiếu sẽ cho cùng đầu ra.
- **Không tạo tác dụng phụ khi xử lý:** việc gọi lại không ghi thêm dữ liệu, gửi thêm thông báo hoặc thay đổi trạng thái bên ngoài.

Hai thuộc tính này giúp processor có thể được gọi lại an toàn. Một processor thuần túy (pure function) thường dễ đạt được mục tiêu này: nó chỉ tính đầu ra từ đầu vào và không thay đổi trạng thái bên ngoài.

## 2. Vì sao processor có thể được gọi lại?

Không nên giả định một item chỉ đi qua processor đúng một lần trong toàn bộ vòng đời job. Tùy cấu hình fault tolerance và đường đi thực thi, cùng một item có thể được xử lý lại.

Một số tình huống thường gặp:

- **Retry:** processor hoặc một thao tác trong chunk gặp lỗi tạm thời và framework thử lại theo retry policy.
- **Rollback:** chunk chưa commit bị rollback; quá trình xử lý có thể phải thực hiện lại với các item liên quan.
- **Restart:** step được chạy lại sau khi execution trước thất bại. Reader có thể khôi phục checkpoint, còn các item chưa được commit có thể xuất hiện lại.
- **Yêu cầu chạy lại từ bên ngoài:** người vận hành hoặc hệ thống gọi lại một đơn vị công việc sau khi không nhận được kết quả xác nhận.
- **Xử lý song song:** nhiều worker hoặc partition xử lý các phạm vi dữ liệu khác nhau; nếu phạm vi bị giao nhau hoặc yêu cầu được gửi lặp, cùng một bản ghi có thể được xử lý nhiều lần.

Ví dụ một chunk có 100 item. Processor đã chuyển đổi các item, nhưng writer thất bại trước khi chunk commit. Khi framework áp dụng retry hoặc step được restart, một phần hoặc toàn bộ item có thể được xử lý lại tùy chính sách và trạng thái đã lưu.

```text
Đọc item
   |
   v
ItemProcessor
   |
   v
ItemWriter
   |
   +---- lỗi trước commit
             |
             v
          rollback
             |
             v
       retry / restart
             |
             v
       xử lý lại item
```

Việc một processor có thể được gọi lại là đặc điểm cần tính đến khi thiết kế. Không nên dựa vào bộ đếm trong bộ nhớ hoặc giả định thứ tự gọi để quyết định kết quả nghiệp vụ.

## 3. Processor thuần túy và dễ lặp lại

Một processor đơn giản thường nhận DTO đầu vào, kiểm tra và tạo đối tượng đầu ra mới. Ví dụ:

```java
public record OrderInput(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

public record Order(
        String orderId,
        String customerCode,
        BigDecimal amount) {
}

@Bean
ItemProcessor<OrderInput, Order> normalizeOrderProcessor() {
    return input -> {
        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException(
                    "Invalid amount for order " + input.orderId());
        }

        return new Order(
                input.orderId().trim(),
                input.customerCode().trim().toUpperCase(Locale.ROOT),
                input.amount().setScale(2, RoundingMode.HALF_UP));
    };
}
```

Với cùng một `OrderInput`, processor tạo ra cùng một `Order`, miễn là các quy tắc chuẩn hóa không thay đổi. Processor không ghi database, không gửi message và không cập nhật bộ đếm toàn cục.

Một vài nguyên tắc giúp giữ processor dễ lặp lại:

- Tạo object đầu ra mới thay vì sửa trực tiếp object đầu vào nếu object có thể được dùng lại hoặc chia sẻ.
- Dùng các phép biến đổi ổn định như trim, chuẩn hóa mã, kiểm tra định dạng và tính toán từ các trường đầu vào.
- Truyền dữ liệu cần thiết vào item hoặc JobParameters thay vì đọc giá trị thay đổi theo thời gian trong lúc xử lý.
- Tránh sinh kết quả dựa trên số thứ tự gọi processor.
- Không ghi dữ liệu nghiệp vụ hoặc phát thông báo trong processor nếu không có cơ chế chống lặp riêng.

## 4. Tránh phụ thuộc vào thời gian hiện tại và dữ liệu ngẫu nhiên

Một processor có thể trở nên không deterministic nếu tự đọc đồng hồ hệ thống hoặc tạo giá trị ngẫu nhiên mỗi lần được gọi.

Ví dụ không ổn định:

```java
public record OrderWithMetadata(
        String orderId,
        String customerCode,
        BigDecimal amount,
        LocalDateTime processedAt,
        String requestId) {
}

@Bean
ItemProcessor<OrderInput, OrderWithMetadata> processor() {
    return input -> new OrderWithMetadata(
            input.orderId(),
            input.customerCode(),
            input.amount(),
            LocalDateTime.now(),
            UUID.randomUUID().toString());
}
```

Khi cùng một item được xử lý lại, `processedAt` và UUID sẽ khác nhau. Nếu các giá trị này ảnh hưởng đến kết quả nghiệp vụ hoặc được ghi lại, việc retry có thể tạo ra kết quả khác lần đầu.

Nếu cần ngày nghiệp vụ, hãy truyền ngày đó qua JobParameters:

```java
public record BusinessDatedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount,
        LocalDate businessDate) {
}

@Bean
@StepScope
ItemProcessor<OrderInput, BusinessDatedOrder> processor(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    LocalDate processingDate = LocalDate.parse(businessDate);

    return input -> new BusinessDatedOrder(
            input.orderId(),
            input.customerCode().trim().toUpperCase(Locale.ROOT),
            input.amount(),
            processingDate);
}
```

Với cùng JobInstance, `businessDate` giữ nguyên nên việc xử lý lại item dùng cùng ngày nghiệp vụ. Nếu cần timestamp tiếp nhận hoặc mã correlation, có thể tạo ở cấp yêu cầu/job và lưu trong tham số hoặc metadata phù hợp, thay vì sinh một giá trị mới mỗi lần `process` được gọi.

UUID không phải lúc nào cũng sai. Nếu UUID đại diện cho một đơn vị nghiệp vụ mới, hãy tạo và lưu nó ở ranh giới tiếp nhận yêu cầu, sau đó dùng lại khi retry. Tránh tạo UUID mới bên trong processor cho mỗi lần gọi nếu nó được dùng làm khóa chống trùng.

## 5. Tách tính toán khỏi tác dụng phụ

Processor nên tập trung chuyển đổi item. Các thao tác thay đổi trạng thái bên ngoài như ghi database, gửi email, publish message hoặc gọi API để tạo giao dịch thường nên được đặt ở writer hoặc một bước riêng có cơ chế phục hồi phù hợp.

Ví dụ, processor không nên gửi email mỗi lần nó xử lý một đơn hàng:

```java
// Không nên: mỗi lần process được gọi có thể gửi thêm một email.
@Bean
ItemProcessor<OrderInput, Order> processor(NotificationService notifications) {
    return input -> {
        notifications.sendOrderReceived(input.orderId());
        return mapToOrder(input);
    };
}
```

Nếu chunk rollback hoặc processor được gọi lại, email có thể được gửi nhiều lần. Giao dịch database không thể tự thu hồi email đã gửi.

Thiết kế tốt hơn là để processor chỉ tạo dữ liệu đầu ra, còn việc gửi thông báo được xử lý ở một bước riêng sau khi dữ liệu đã được ghi nhận. Bước thông báo cần có khóa idempotency hoặc bảng outbox để xác định một thông báo đã được phát hay chưa.

```text
ItemReader
    |
    v
ItemProcessor (chỉ biến đổi dữ liệu)
    |
    v
ItemWriter (ghi dữ liệu / outbox)
    |
    v
Commit database
    |
    v
Notification step / Outbox publisher
    |
    v
Gửi thông báo với khóa chống lặp
```

Nếu processor cần tra cứu dữ liệu từ dịch vụ khác để làm giàu item, thao tác đọc thường có thể chấp nhận được, nhưng cần cân nhắc tính ổn định của dữ liệu trả về. Nếu dữ liệu tham chiếu thay đổi giữa lần xử lý đầu và lần retry, cùng item có thể tạo đầu ra khác nhau. Có thể giải quyết bằng snapshot, phiên bản dữ liệu tham chiếu hoặc lưu giá trị cần thiết cùng batch.

## 6. Đọc dữ liệu bên ngoài trong processor

Không phải mọi lời gọi service trong processor đều là tác dụng phụ. Ví dụ, tra cứu hạng khách hàng hoặc tỷ giá có thể là thao tác đọc. Tuy nhiên, tính idempotent của kết quả còn phụ thuộc dịch vụ đó có trả dữ liệu ổn định hay không.

Giả sử processor lấy tỷ giá hiện tại từ một API. Nếu lần đầu trả về 25.000 và lần retry trả về 25.100, cùng một giao dịch đầu vào có thể tạo ra số tiền quy đổi khác nhau. Vấn đề không nằm ở việc API chỉ đọc, mà ở việc dữ liệu tham chiếu thay đổi theo thời gian.

Một số cách xử lý:

- Chốt tỷ giá hoặc phiên bản dữ liệu tham chiếu tại thời điểm bắt đầu batch.
- Lưu snapshot dữ liệu cần thiết trong database hoặc một resource bất biến.
- Truyền mã phiên bản/snapshot qua JobParameters để mọi lần thực thi của cùng JobInstance dùng cùng dữ liệu.
- Cache kết quả tra cứu trong phạm vi phù hợp nếu dữ liệu được bảo đảm bất biến trong batch.
- Nếu dữ liệu tham chiếu thay đổi là yêu cầu nghiệp vụ, ghi nhận rõ phiên bản được sử dụng để có thể giải thích kết quả.

Không nên cache tùy tiện trong một singleton processor nếu cache làm kết quả phụ thuộc lịch sử xử lý của thread hoặc instance ứng dụng. Cần xác định phạm vi và vòng đời cache rõ ràng.

## 7. Phân biệt idempotent, deterministic và exactly-once

Ba khái niệm này liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Câu hỏi cần trả lời |
|---|---|---|
| Idempotent | Lặp lại thao tác không làm kết quả cuối cùng thay đổi thêm. | Gọi lại có tạo thêm tác dụng phụ hoặc thay đổi kết quả không? |
| Deterministic | Cùng đầu vào và cùng trạng thái tham chiếu tạo ra cùng đầu ra. | Cùng dữ liệu có luôn cho cùng kết quả không? |
| Exactly-once | Một tác dụng nghiệp vụ được áp dụng đúng một lần trong phạm vi hệ thống được bảo đảm. | Hệ thống có bảo đảm không mất và không áp dụng lặp không? |

Một processor thuần túy, deterministic thường dễ làm cho việc xử lý lại an toàn. Nhưng điều đó không tự bảo đảm toàn bộ job exactly-once. Writer vẫn có thể ghi trùng, một API ngoài vẫn có thể nhận yêu cầu lặp hoặc metadata có thể không đồng bộ với tác dụng phụ bên ngoài.

Ngược lại, một thao tác ghi có idempotency key ở hệ thống nhận có thể giúp nhiều lần gửi cùng yêu cầu chỉ tạo một kết quả nghiệp vụ. Đây là cơ chế ở ranh giới tác dụng phụ, không phải thuộc tính tự động có được chỉ vì processor trả cùng output.

## 8. Idempotency key cho tác dụng phụ bên ngoài

Khi một quy trình cần gửi yêu cầu đến hệ thống khác, có thể dùng khóa idempotency ổn định để hệ thống nhận nhận diện yêu cầu lặp. Khóa nên được tạo từ định danh nghiệp vụ ổn định, chẳng hạn batch ID và order ID.

Ví dụ:

```java
String idempotencyKey = batchId + ":" + input.orderId();
```

Nếu yêu cầu gửi cho cùng đơn hàng trong cùng batch được retry, khóa vẫn giữ nguyên. Hệ thống nhận có thể lưu khóa đã xử lý và trả lại kết quả cũ khi nhận yêu cầu trùng.

Không nên tạo khóa bằng `UUID.randomUUID()` trong mỗi lần gọi processor hoặc writer, vì mỗi lần retry sẽ tạo khóa mới và hệ thống nhận không thể nhận ra đó là cùng một yêu cầu logic.

Nếu API bên ngoài hỗ trợ idempotency key, cần hiểu chính sách lưu khóa của API: thời gian lưu, phạm vi khóa, phản hồi khi gửi trùng và cách xử lý cùng khóa nhưng payload khác nhau. Nếu API không hỗ trợ, ứng dụng có thể cần một bảng trạng thái gửi, outbox hoặc bước đối soát riêng.

## 9. Thiết kế writer cũng phải chịu được việc ghi lặp

Processor idempotent không đủ nếu writer không idempotent. Ví dụ, processor tạo cùng một `Order` mỗi lần, nhưng writer luôn thực hiện `INSERT` một dòng mới. Nếu chunk bị xử lý lại, database có thể chứa hai bản ghi cho cùng đơn hàng.

Một số cách làm writer an toàn hơn:

- Dùng khóa nghiệp vụ duy nhất như `order_id` và xử lý duplicate có chủ đích.
- Dùng câu lệnh upsert hoặc merge theo khả năng của database.
- Ghi nhận trạng thái xử lý theo batch ID và item ID.
- Dùng outbox có unique key cho sự kiện cần phát.
- Phân biệt rõ insert mới với update bản ghi đã tồn tại.

Ví dụ, bảng đích có thể có unique constraint trên `(batch_id, order_id)`. Writer dùng câu lệnh phù hợp để cập nhật hoặc bỏ qua bản ghi đã được ghi nhận. Cách thực hiện cụ thể tùy database và quy tắc nghiệp vụ.

Không nên chỉ bắt lỗi duplicate key rồi bỏ qua một cách mù quáng. Bản ghi trùng có thể có payload khác nhau; cần xác định đó là cùng một kết quả được gửi lại hay là xung đột dữ liệu cần xử lý.

## 10. Retry và processor

Trong chunk-oriented step, có thể cấu hình retry cho các exception tạm thời. Ví dụ, một processor gọi dịch vụ đọc có thể gặp timeout. Spring Batch có thể thử lại theo retry policy của step.

```java
return new StepBuilder("processOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Retry policy cần được giới hạn theo loại lỗi có khả năng phục hồi. Không nên retry vô hạn hoặc retry lỗi dữ liệu không thể tự khắc phục. Với lời gọi service, nên có timeout rõ ràng, backoff và giới hạn tổng thời gian chờ.

Khi retry, processor có thể được gọi lại tùy đường đi thực thi và cấu hình fault tolerance. Vì vậy, hãy thiết kế processor không phụ thuộc số lần gọi. Nếu dùng `processorNonTransactional` hoặc các tùy chọn liên quan đến cache kết quả processor, cần hiểu rõ semantics của phiên bản Spring Batch đang dùng; không dùng chúng để thay thế thiết kế idempotency cho tác dụng phụ.

## 11. Filter và skip không thay thế idempotency

Processor có thể trả về `null` để filter item. Nó cũng có thể ném exception để step áp dụng skip policy nếu exception được cho phép.

```java
@Bean
ItemProcessor<OrderInput, Order> processor() {
    return input -> {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("Missing order ID");
        }

        if (input.amount().signum() == 0) {
            return null; // filter theo quy tắc nghiệp vụ
        }

        return mapToOrder(input);
    };
}
```

Filter quyết định item có được chuyển đến writer hay không. Skip quyết định exception thuộc loại nào có thể được bỏ qua. Idempotency giải quyết việc xử lý lại có tạo kết quả hoặc tác dụng phụ lặp hay không. Đây là ba vấn đề khác nhau.

Nếu processor ghi log lỗi hoặc lưu bản ghi rejected vào một hệ thống riêng, thao tác ghi nhận đó cũng cần được xem xét khi retry. Tránh tạo nhiều bản ghi lỗi giống nhau cho cùng item nếu điều đó gây khó khăn cho đối soát.

## 12. Tránh sửa object đầu vào và dùng trạng thái mutable

Processor thường được thiết kế như một phép chuyển đổi từ input sang output. Nếu processor sửa trực tiếp object đầu vào, việc gọi lại có thể nhận object đã bị thay đổi trong một số cách tổ chức xử lý hoặc test, dẫn đến kết quả khó dự đoán.

Ví dụ không nên sửa trực tiếp:

```java
@Bean
ItemProcessor<OrderInputMutable, OrderInputMutable> processor() {
    return input -> {
        input.setCustomerCode(input.getCustomerCode().trim());
        input.setAmount(input.getAmount().setScale(2, RoundingMode.HALF_UP));
        return input;
    };
}
```

Nếu có thể, hãy dùng object bất biến hoặc tạo object đầu ra mới:

```java
@Bean
ItemProcessor<OrderInput, NormalizedOrder> processor() {
    return input -> new NormalizedOrder(
            input.orderId().trim(),
            input.customerCode().trim().toUpperCase(Locale.ROOT),
            input.amount().setScale(2, RoundingMode.HALF_UP));
}
```

Object bất biến giúp dễ suy luận, dễ test và tránh việc processor làm thay đổi dữ liệu được các thành phần khác chia sẻ.

## 13. Stateful processor và xử lý song song

Một processor có thể giữ state như bộ đếm, cache hoặc tập hợp các mã đã thấy. Tuy nhiên, state mutable làm cho kết quả có thể phụ thuộc thứ tự item, thread hoặc lịch sử của lần thực thi trước.

Ví dụ, processor tăng bộ đếm toàn cục và gán số thứ tự cho từng item. Nếu một item được xử lý lại, số thứ tự mới có thể khác. Nếu step chạy nhiều thread, nhiều thread có thể cập nhật bộ đếm đồng thời và tạo race condition.

Khi cần state, hãy cân nhắc:

- State có phải là dữ liệu nghiệp vụ cần được lưu bền vững hay chỉ là cache tạm thời?
- Có thể tính lại từ input thay vì duy trì bộ đếm mutable không?
- State có cần lưu trong `ExecutionContext` để restart không?
- Mỗi partition hoặc step execution có state riêng không?
- Processor có được nhiều thread gọi đồng thời không?
- Kết quả có phụ thuộc thứ tự item không?

Nếu xử lý song song, processor nên thread-safe hoặc được tạo theo scope phù hợp để mỗi execution/partition có instance riêng. Không nên dựa vào một singleton processor có state mutable nếu chưa thiết kế đồng bộ và khôi phục rõ ràng.

## 14. Kiểm thử tính lặp lại của processor

Processor thường có thể được unit test mà không cần khởi động toàn bộ Spring Batch. Một cách kiểm thử hữu ích là gọi processor nhiều lần với cùng input và xác nhận output tương đương.

Ví dụ:

```java
@Test
void processingSameInputProducesSameOutput() throws Exception {
    ItemProcessor<OrderInput, Order> processor = normalizeOrderProcessor();

    OrderInput input = new OrderInput(
            " O-001 ", " customer-a ", new BigDecimal("125.5"));

    Order first = processor.process(input);
    Order second = processor.process(input);

    assertThat(second).isEqualTo(first);
}
```

Với processor có side effect hoặc phụ thuộc service, cần kiểm tra thêm:

- Cùng input có tạo cùng số lần gọi ghi hoặc gửi request không? Tốt nhất processor không thực hiện các thao tác này.
- Khi service trả cùng snapshot dữ liệu, output có giống nhau không?
- Khi service timeout rồi retry, processor có thể tiếp tục mà không tạo thay đổi ngoài ý muốn không?
- Tham số thời gian và phiên bản dữ liệu tham chiếu có cố định trong cùng JobInstance không?
- Processor có thay đổi object input hoặc state dùng chung không?

Ở cấp integration test, có thể mô phỏng writer thất bại trước commit rồi chạy lại step để xác nhận kết quả nghiệp vụ không bị nhân đôi. Unit test xác nhận phép biến đổi; integration test xác nhận tương tác giữa reader, processor, writer, transaction và metadata.

## 15. Ví dụ: processor gọi dịch vụ tra cứu nhưng vẫn giữ đầu ra ổn định

Giả sử đơn hàng cần được bổ sung nhóm khách hàng. Processor có thể gọi một service chỉ đọc để lấy nhóm khách hàng. Để đầu ra ổn định, service cần trả dữ liệu theo một phiên bản/snapshot được xác định cho batch.

```java
public record CustomerSnapshot(
        String customerId,
        String segment,
        String version) {
}

public record EnrichedOrder(
        String orderId,
        String customerCode,
        BigDecimal amount,
        String customerSegment) {
}

@Bean
@StepScope
ItemProcessor<OrderInput, EnrichedOrder> enrichOrderProcessor(
        CustomerLookupService customerLookupService,
        @Value("#{jobParameters['customerSnapshotVersion']}") String snapshotVersion) {

    return input -> {
        CustomerSnapshot customer = customerLookupService.find(
                input.customerCode(), snapshotVersion);

        return new EnrichedOrder(
                input.orderId(),
                input.customerCode(),
                input.amount(),
                customer.segment());
    };
}
```

Ở ví dụ này, processor không cập nhật hồ sơ khách hàng. Nó chỉ tra cứu snapshot theo một version cố định rồi tạo output. Khi cùng item được xử lý lại trong cùng JobInstance, cùng phiên bản snapshot được sử dụng.

Nếu service lookup trả về dữ liệu thay đổi liên tục mà không hỗ trợ snapshot, processor có thể tạo kết quả khác nhau ở lần retry. Khi đó cần lưu dữ liệu tham chiếu, chốt version hoặc thay đổi thiết kế để kết quả batch có thể tái lập.

## 16. Checklist thiết kế processor idempotent

Khi triển khai một `ItemProcessor`, hãy cân nhắc các câu hỏi sau:

1. Cùng một input có luôn tạo cùng output khi các tham số và dữ liệu tham chiếu không đổi không?
2. Processor có đọc đồng hồ hệ thống, sinh UUID hoặc số ngẫu nhiên trong mỗi lần gọi không?
3. Processor có ghi database, gửi email, publish message hoặc gọi API làm thay đổi trạng thái không?
4. Nếu có tra cứu bên ngoài, dữ liệu trả về có ổn định trong suốt JobInstance không?
5. Processor có sửa trực tiếp object input hoặc state dùng chung không?
6. Nếu item được xử lý lại sau rollback/restart, kết quả có còn hợp lệ không?
7. Nếu processor chạy song song, các dependency và state có thread-safe không?
8. Writer có thể ghi lại cùng output mà không tạo dữ liệu nghiệp vụ trùng không?
9. Các tác dụng phụ bên ngoài có idempotency key hoặc cơ chế đối soát không?
10. Có test chứng minh việc gọi lại cùng input cho kết quả như mong đợi không?

Không phải processor nào cũng cần một cơ chế phức tạp. Với phép chuẩn hóa hoặc chuyển đổi thuần túy, giữ input rõ ràng và tạo output mới thường đã đủ. Những processor gọi dịch vụ bên ngoài hoặc phụ thuộc dữ liệu thay đổi cần thiết kế snapshot, version và xử lý lỗi cẩn thận hơn.

## 17. Những điểm cần ghi nhớ

- Processor có thể được gọi lại do retry, rollback, restart hoặc yêu cầu chạy lặp; không dựa vào giả định mỗi item chỉ được xử lý đúng một lần.
- Cùng input và cùng dữ liệu tham chiếu nên tạo cùng output.
- Ưu tiên processor thuần túy: tính toán và chuyển đổi dữ liệu, không tạo tác dụng phụ.
- Tránh phụ thuộc `now()`, UUID hoặc số ngẫu nhiên được sinh mới trong mỗi lần gọi nếu chúng ảnh hưởng kết quả.
- Dùng JobParameters hoặc snapshot cố định cho ngày nghiệp vụ và dữ liệu tham chiếu cần ổn định.
- Nếu cần gọi hệ thống ngoài, dùng idempotency key ổn định hoặc tách tác dụng phụ sang writer/bước riêng có cơ chế chống lặp.
- Processor idempotent không tự bảo đảm writer idempotent hay toàn bộ job exactly-once.
- Tránh sửa object đầu vào và tránh state mutable dùng chung khi xử lý song song.
- Phân biệt filter bằng `null`, skip do exception và idempotency; chúng giải quyết các vấn đề khác nhau.
- Kiểm thử bằng cách gọi lại cùng input và kiểm tra cả output lẫn tác dụng phụ.

Thiết kế processor idempotent giúp Spring Batch có thể retry hoặc restart một cách dễ dự đoán hơn. Hãy giữ phép xử lý item ổn định, quản lý dữ liệu tham chiếu có phiên bản và đặt các tác dụng phụ ở ranh giới có thể kiểm soát việc lặp. Khi đó, việc framework xử lý lại item sẽ ít có nguy cơ làm thay đổi sai kết quả nghiệp vụ.
