# Không để processor thực hiện side effect khó retry trong Spring Batch

`ItemProcessor` nằm giữa reader và writer trong chunk-oriented processing. Nhiệm vụ chính của nó là nhận một item đầu vào, kiểm tra hoặc biến đổi item đó rồi trả về kết quả để writer ghi. Vì processor được gọi trong quá trình xử lý chunk, cách thiết kế của nó ảnh hưởng trực tiếp đến khả năng retry, rollback và restart của job.

Một processor dễ retry nên thực hiện phép biến đổi có thể lặp lại mà không gây thêm tác động bên ngoài. Nếu processor gửi email, trừ tiền, gọi API tạo dữ liệu, ghi file hoặc phát message, lần xử lý lại có thể tạo tác dụng phụ trùng lặp. **Không nên đặt side effect khó hoàn tác hoặc khó lặp an toàn trong `process()`**. Hãy giữ processor tập trung vào việc tạo kết quả và đưa các thao tác ghi bền vững vào nơi có transaction hoặc cơ chế chống trùng phù hợp.

## 1. Vai trò của ItemProcessor

Trong chunk processing, Spring Batch đọc các item, chuyển từng item qua processor nếu có cấu hình, rồi đưa các output còn lại cho writer:

```text
ItemReader
    |
    v
Input item
    |
    v
ItemProcessor
    |
    +---- trả về object -> đưa vào output chunk
    |
    +---- trả về null   -> filter item khỏi output
    |
    v
ItemWriter
    |
    v
Commit chunk transaction
```

Interface cơ bản:

```java
public interface ItemProcessor<I, O> {
    O process(I item) throws Exception;
}
```

Processor nhận một item kiểu `I` và trả về item kiểu `O`. Hai kiểu có thể giống nhau nếu chỉ chuẩn hóa hoặc cập nhật dữ liệu, hoặc khác nhau nếu chuyển từ dữ liệu nguồn sang command/DTO phục vụ bước tiếp theo.

Các công việc phù hợp với processor gồm:

- Chuẩn hóa chuỗi, ngày tháng hoặc mã nghiệp vụ.
- Tính toán giá trị dựa trên dữ liệu đầu vào.
- Ánh xạ entity nguồn sang DTO hoặc command.
- Kiểm tra điều kiện nghiệp vụ và trả về kết quả đã được phân loại.
- Filter item không cần xử lý bằng cách trả về `null`, khi đó là quy tắc nghiệp vụ hợp lệ.

Processor có thể ném exception nếu item không thể xử lý. Step sẽ áp dụng transaction và fault-tolerance policy đã cấu hình để quyết định retry, skip hoặc fail.

## 2. Side effect là gì?

Side effect là thay đổi có thể quan sát được bên ngoài kết quả trả về của hàm. Trong một processor, các hành động sau là side effect:

- Gửi email hoặc SMS.
- Gọi API `POST`, `PUT`, `PATCH` để tạo hoặc cập nhật dữ liệu ở hệ thống khác.
- Trừ tiền, tạo giao dịch thanh toán hoặc đặt hàng ở dịch vụ bên ngoài.
- Gửi message vào Kafka, RabbitMQ hoặc một queue khác.
- Ghi file, upload object hoặc cập nhật một database không tham gia transaction của chunk.
- Cập nhật cache dùng chung, biến static, bộ đếm toàn cục hoặc trạng thái của một service bên ngoài.
- Gọi một thao tác có tính phí hoặc tạo tài nguyên mới mỗi lần được gọi.

Không phải mọi thao tác I/O đều là side effect. Một truy vấn chỉ đọc dữ liệu tham chiếu có thể phù hợp trong processor, nhưng kết quả cần ổn định nếu cùng item được xử lý lại. Ví dụ, tra cứu tỷ giá hiện tại hai lần có thể cho kết quả khác nhau; nếu kết quả đó ảnh hưởng đến số tiền ghi ra, nên gắn với một thời điểm hoặc phiên bản dữ liệu rõ ràng.

Điểm cần quan tâm là tác động có được rollback cùng chunk hay không, và có thể nhận diện một lần thực hiện lặp lại hay không. Gọi một hệ thống bên ngoài thường không tham gia transaction database của Spring Batch, vì vậy rollback chunk không thể tự hoàn tác lời gọi đó.

## 3. Vì sao processor có thể được gọi lại?

Một job batch không bảo đảm mỗi lời gọi `process()` chỉ xảy ra đúng một lần trong toàn bộ vòng đời nghiệp vụ. Việc xử lý có thể được thử lại khi có lỗi, chunk rollback hoặc job restart. Hành vi chính xác phụ thuộc cấu hình step, fault-tolerance và thời điểm lỗi.

Các tình huống có thể dẫn đến xử lý lại gồm:

- Chunk thất bại và được rollback; một phần item của chunk có thể phải được xử lý lại.
- Lỗi trong writer khiến chunk không commit; step có thể thử lại chunk theo chính sách đã cấu hình.
- Job thất bại rồi được restart từ checkpoint đã commit; item chưa được commit có thể xuất hiện lại.
- Một test hoặc thao tác vận hành chạy lại cùng đơn vị công việc theo cấu hình phù hợp.
- Với fault-tolerant step, cấu hình `processorNonTransactional()` có thể yêu cầu processor được gọi lại khi item được xử lý lại sau rollback.

Spring Batch có cơ chế buffering/caching kết quả processor trong một số đường xử lý fault-tolerant để tránh tính toán lại khi rollback. Tuy nhiên, không nên dựa vào cache nội bộ đó như một bảo đảm exactly-once. Cache không thay thế tính bền vững qua restart hoặc khả năng chống trùng ở hệ thống bên ngoài; cấu hình và tình huống thực thi cũng có thể làm processor được gọi lại.

Ví dụ, processor gọi dịch vụ thanh toán:

```text
Đọc Order-42
    |
    v
Processor gọi payment API -> thanh toán thành công
    |
    v
Writer ghi kết quả -> lỗi database
    |
    v
Chunk rollback
    |
    v
Item được xử lý lại
    |
    v
Processor gọi payment API lần nữa
```

Nếu API không có idempotency key, đơn hàng có thể bị tính tiền hai lần. Transaction rollback của database không thể hoàn tác khoản thanh toán đã hoàn tất ở hệ thống thanh toán.

## 4. Ví dụ processor có side effect khó retry

Đoạn code sau minh họa một thiết kế rủi ro:

```java
public class ChargeOrderProcessor
        implements ItemProcessor<Order, PaymentReceipt> {

    private final PaymentClient paymentClient;

    public ChargeOrderProcessor(PaymentClient paymentClient) {
        this.paymentClient = paymentClient;
    }

    @Override
    public PaymentReceipt process(Order order) {
        // Side effect: mỗi lần gọi có thể tạo một lần charge mới.
        return paymentClient.charge(order.getId(), order.getTotal());
    }
}
```

Vấn đề nằm ở chỗ `process()` vừa quyết định dữ liệu đầu ra vừa thực hiện giao dịch thanh toán. Nếu cùng order được xử lý lại, API có thể tạo thêm một khoản charge. Processor cũng khó được kiểm thử độc lập vì mỗi lần gọi đều phụ thuộc vào dịch vụ thanh toán và có thể làm thay đổi dữ liệu thật.

Những cách viết tương tự cũng có rủi ro:

```java
@Override
public Notification process(Order order) {
    emailClient.sendReceipt(order);       // gửi email ngay
    messageBroker.publish(order);         // phát message ngay
    auditRepository.save(new Audit(...)); // ghi DB khác transaction
    return toNotification(order);
}
```

Khi một thao tác trong chunk thất bại, các tác động đã xảy ra ở hệ thống ngoài vẫn có thể còn nguyên. Lần retry hoặc restart sau đó có thể lặp lại chúng.

## 5. Thiết kế processor như một phép biến đổi có thể lặp lại

Processor nên tập trung vào tính toán và ánh xạ dữ liệu. Với cùng một input và cùng dữ liệu tham chiếu/version, kết quả nên ổn định và không tạo thay đổi bên ngoài.

Ví dụ, thay vì charge ngay trong processor, hãy tạo một command mô tả yêu cầu thanh toán:

```java
public record PaymentCommand(
    String eventId,
    String orderId,
    BigDecimal amount
) {}

public class PaymentCommandProcessor
        implements ItemProcessor<Order, PaymentCommand> {

    @Override
    public PaymentCommand process(Order order) {
        if (order.isCancelled()) {
            return null; // filter theo quy tắc nghiệp vụ
        }

        String eventId = "payment:v1:" + order.getId();
        return new PaymentCommand(
            eventId,
            order.getId(),
            order.getTotal()
        );
    }
}
```

Processor chỉ tạo một object mô tả công việc. `eventId` được tạo từ định danh ổn định của nghiệp vụ và phiên bản thao tác; nó sẽ được dùng làm khóa chống trùng ở bước ghi hoặc ở consumer. Nếu một order có thể thanh toán nhiều lần hợp lệ, khóa cần chứa thêm định danh lần thanh toán hoặc mã yêu cầu để không gộp nhầm hai giao dịch khác nhau.

Một phép biến đổi có thể lặp lại còn cần tránh phụ thuộc vào trạng thái thay đổi không được kiểm soát. Nếu processor cần thông tin tỷ giá, chính sách hoặc bảng giá, hãy truyền phiên bản/thời điểm cần dùng qua input hoặc `JobParameters`, hoặc đọc một snapshot nhất quán. Không nên gọi một dịch vụ thay đổi theo thời gian rồi giả định lần retry sẽ nhận đúng kết quả như lần đầu.

## 6. Đưa thao tác ghi vào ItemWriter

`ItemWriter` là thành phần chịu trách nhiệm ghi một nhóm output của chunk. Các thao tác ghi vào database tham gia cùng transaction của step có thể được commit hoặc rollback cùng chunk nếu dùng đúng transaction manager và cùng tài nguyên transaction.

Ví dụ writer lưu yêu cầu thanh toán vào bảng outbox:

```java
@Bean
ItemWriter<PaymentCommand> paymentOutboxWriter(
        PaymentOutboxRepository outboxRepository) {
    return chunk -> {
        List<PaymentOutboxEvent> events = chunk.getItems().stream()
            .map(command -> new PaymentOutboxEvent(
                command.eventId(),
                command.orderId(),
                command.amount(),
                "PENDING"
            ))
            .toList();

        outboxRepository.saveAll(events);
    };
}
```

Trong cấu hình thực tế, `PaymentOutboxEvent` và repository là model của ứng dụng. Bảng outbox cần có unique constraint trên `event_id` để một yêu cầu logic không được tạo thành nhiều hàng. Nếu writer có thể được gọi lại, cách ghi nên dùng insert-if-absent/upsert hoặc xử lý duplicate key theo quy tắc đã định, thay vì để một lần ghi lặp tạo thêm sự kiện.

Writer cũng có thể được gọi lại khi chunk rollback hoặc retry. Vì vậy, chuyển side effect từ processor sang writer chưa tự động tạo ra exactly-once. Lợi ích của writer là nó là ranh giới ghi chunk rõ ràng và có thể tham gia transaction; tính an toàn vẫn cần transaction phù hợp và idempotency.

## 7. Transactional outbox cho tác động đến hệ thống bên ngoài

Nếu job cần gửi message, gọi API hoặc tạo giao dịch ở một dịch vụ khác, một mẫu phổ biến là **transactional outbox**. Thay vì thực hiện side effect ngay trong processor, job ghi một bản ghi sự kiện vào outbox cùng transaction với dữ liệu nghiệp vụ liên quan.

Luồng tổng quát:

```text
ItemReader
    |
    v
ItemProcessor
  tạo PaymentCommand (không charge)
    |
    v
ItemWriter
  ghi business data + outbox event
    |
    v
Một local database transaction commit
    |
    v
Outbox dispatcher đọc event PENDING
    |
    v
Gọi payment API / publish message
    |
    v
Đánh dấu event đã gửi
```

Nếu ghi dữ liệu nghiệp vụ và outbox cùng một transaction database, cả hai cùng commit hoặc rollback. Sau commit, một dispatcher riêng đọc outbox và gửi yêu cầu ra ngoài. Nếu dispatcher dừng giữa lúc gửi và đánh dấu đã gửi, event có thể được gửi lại; do đó hệ thống nhận vẫn cần idempotency theo `eventId`.

Outbox giúp tránh mất yêu cầu giữa thời điểm commit dữ liệu và thời điểm publish. Nó thường cung cấp mô hình at-least-once delivery, không phải bảo đảm một thông điệp chỉ đến consumer đúng một lần. Consumer hoặc API đích cần lưu idempotency key để phát hiện lần gửi trùng.

Ví dụ, consumer có thể lưu `eventId` đã xử lý trong bảng có unique constraint. Khi nhận lại cùng event, consumer nhận biết sự kiện đã được áp dụng và trả về kết quả phù hợp mà không thực hiện side effect lần nữa.

## 8. Idempotency khi không thể tránh side effect

Một thao tác là idempotent nếu thực hiện nhiều lần với cùng định danh yêu cầu vẫn tạo ra cùng kết quả nghiệp vụ như thực hiện một lần. Idempotency là lớp bảo vệ quan trọng khi hệ thống phải retry hoặc xử lý lại.

Các cách thường dùng:

- Gửi một `Idempotency-Key` ổn định đến API đích, ví dụ `payment:v1:ORDER-42`.
- Tạo unique constraint trên khóa nghiệp vụ hoặc event ID ở database đích.
- Dùng upsert thay vì insert mù khi thao tác ghi có thể lặp lại.
- Lưu trạng thái xử lý của event và kiểm tra trạng thái trước khi áp dụng tác động.
- Dùng mã giao dịch do hệ thống nguồn tạo và truyền xuyên suốt các lần retry.

Không dùng UUID mới được tạo trong mỗi lần gọi `process()` làm idempotency key. Nếu retry tạo UUID khác, hệ thống đích sẽ coi đó là hai yêu cầu độc lập. Khóa phải được tạo từ định danh ổn định của đơn vị nghiệp vụ hoặc được lưu bền vững trước khi thực hiện side effect.

Idempotency cũng cần định nghĩa phạm vi. Một order có thể có nhiều lần thanh toán hợp lệ; khóa chỉ dựa vào `orderId` có thể ngăn cả giao dịch mới. Hãy kết hợp order ID với payment attempt ID hoặc operation version theo đúng mô hình nghiệp vụ.

## 9. Có nên gọi service chỉ đọc trong processor?

Processor đôi khi cần tra cứu dữ liệu để tính kết quả. Ví dụ, lấy thông tin khách hàng, quy tắc phân loại hoặc hạn mức. Những thao tác chỉ đọc có thể phù hợp, nhưng vẫn cần xem xét tính lặp lại và độ ổn định.

Một lần gọi API đọc có thể trả về kết quả khác ở lần retry nếu dữ liệu thay đổi giữa hai thời điểm. Điều này không phải side effect trực tiếp, nhưng có thể làm cùng item tạo ra kết quả khác nhau. Nếu tính đúng đắn yêu cầu cùng một snapshot, hãy:

- Truyền thời điểm hoặc phiên bản dữ liệu cần dùng vào job.
- Đọc dữ liệu tham chiếu từ snapshot bất biến.
- Lưu giá trị đã tra cứu vào input hoặc một vùng lưu bền vững phù hợp.
- Dùng cache có phạm vi và thời hạn rõ ràng khi chấp nhận được.
- Xử lý lỗi timeout bằng retry có giới hạn, không chuyển lỗi thành kết quả rỗng tùy tiện.

Không nên gọi service có tác dụng phụ dưới tên một hàm “lookup” hoặc “validate”. Hãy làm rõ hợp đồng của service: chỉ đọc, có thay đổi trạng thái, có tính phí hay có thể tạo tài nguyên mới.

## 10. Listener không phải cơ chế exactly-once

Spring Batch có các listener như `ItemProcessListener`, `ChunkListener`, `StepExecutionListener` để quan sát vòng đời xử lý. Chúng phù hợp cho log, metric, tracing hoặc ghi nhận thông tin chẩn đoán. Tuy nhiên, callback listener không tự bảo đảm một thao tác bên ngoài chỉ được thực hiện đúng một lần.

Ví dụ, gửi email trong `afterProcess()` vẫn có nguy cơ gửi lại nếu item được xử lý lại. Gửi message trong `afterChunk()` có thể tránh một số trường hợp trước commit, nhưng tiến trình vẫn có thể dừng sau khi database commit và trước khi message được gửi; nếu callback được thực hiện lại trong tình huống khác, cũng có thể phát sinh trùng. Gửi email trong `afterStep()` cũng có thể gặp vấn đề tương tự khi step hoàn tất nhưng ứng dụng dừng trước khi ghi nhận hoặc gửi xong.

Hãy dùng listener cho quan sát và hook vòng đời có kiểm soát. Với tác động nghiệp vụ cần bảo đảm không bị mất, hãy ghi ý định bền vững trong transaction (chẳng hạn outbox), sau đó dispatch bằng một thành phần có retry và idempotency.

## 11. Phân biệt processor, writer và dịch vụ nghiệp vụ

Một cách tổ chức rõ ràng là để processor tạo kết quả hoặc command, writer lưu kết quả/ý định, còn service chuyên trách thực hiện giao tiếp với hệ thống ngoài theo cơ chế bền vững.

| Thành phần | Trách nhiệm phù hợp | Điều cần tránh |
| --- | --- | --- |
| `ItemReader` | Lấy item từ nguồn và duy trì trạng thái đọc có thể phục hồi. | Tiêu thụ dữ liệu không thể đọc lại mà không có checkpoint phù hợp. |
| `ItemProcessor` | Validate, tính toán, chuẩn hóa, ánh xạ và filter. | Gửi email, charge, publish hoặc ghi tài nguyên ngoài transaction. |
| `ItemWriter` | Ghi output của chunk trong transaction hoặc qua thao tác idempotent. | Giả định writer chỉ được gọi một lần. |
| Outbox dispatcher | Gửi sự kiện đã lưu và cập nhật trạng thái dispatch. | Gửi mà không có idempotency hoặc không lưu tiến độ. |
| Consumer/API đích | Áp dụng tác động nghiệp vụ với khóa chống trùng. | Coi mỗi lần nhận request là một thao tác hoàn toàn mới. |

Việc phân tách này giúp kiểm thử processor bằng input/output đơn giản, kiểm thử writer với transaction test và kiểm thử dispatcher riêng cho retry, timeout, duplicate delivery.

## 12. Xử lý lỗi khi side effect đã xảy ra

Một tình huống khó là hệ thống bên ngoài đã thực hiện thao tác nhưng ứng dụng không nhận được phản hồi. Ví dụ, payment API đã charge thành công nhưng kết nối timeout trước khi trả kết quả. Ứng dụng không biết giao dịch đã thành công hay chưa.

Không nên lập tức gửi một yêu cầu mới với ID khác. Hãy dùng cùng idempotency key để truy vấn hoặc gửi lại yêu cầu. Nếu API đích hỗ trợ tra cứu trạng thái theo request ID, hãy xác minh trước khi quyết định tạo giao dịch khác.

Với hệ thống không hỗ trợ idempotency, có thể cần bước đối soát theo mã nghiệp vụ, trạng thái giao dịch hoặc quy trình bù trừ. Không có cách tổng quát để rollback một side effect đã commit ở hệ thống ngoài chỉ bằng cách rollback transaction của Spring Batch.

## 13. Kiểm thử processor và khả năng retry

Processor thuần biến đổi dễ kiểm thử vì không cần database hoặc dịch vụ bên ngoài. Test có thể kiểm tra input hợp lệ, input bị filter và input không hợp lệ:

```java
class PaymentCommandProcessorTest {

    private final PaymentCommandProcessor processor =
        new PaymentCommandProcessor();

    @Test
    void mapsOrderToStablePaymentCommand() throws Exception {
        Order order = new Order("ORDER-42", new BigDecimal("125.00"));

        PaymentCommand first = processor.process(order);
        PaymentCommand second = processor.process(order);

        assertThat(first).isEqualTo(second);
        assertThat(first.eventId()).isEqualTo("payment:v1:ORDER-42");
        assertThat(first.amount()).isEqualByComparingTo("125.00");
    }
}
```

Test gọi processor hai lần với cùng input để xác nhận phép biến đổi không tạo tác động bên ngoài và cho kết quả ổn định. Nếu processor cần dependency chỉ đọc, có thể mock dependency đó để xác nhận cách tra cứu; không nên mock một side effect rồi xem như đã chứng minh khả năng chống trùng ở production.

Với writer/outbox, nên kiểm thử rằng:

- Output được ghi trong transaction phù hợp.
- Hai lần ghi cùng `eventId` không tạo hai sự kiện nghiệp vụ.
- Rollback chunk không để lại outbox event chưa có dữ liệu nghiệp vụ tương ứng.
- Dispatcher có thể gửi lại sau timeout mà không tạo tác động trùng ở consumer.
- Một sự kiện đã gửi nhưng chưa đánh dấu hoàn tất có thể được gửi lại một cách an toàn.

Với job tích hợp, mô phỏng lỗi writer sau khi processor đã chạy để xác nhận processor không gửi side effect trực tiếp. Kiểm tra restart sau chunk rollback và đối chiếu số event trong outbox với số đơn vị nghiệp vụ đã commit.

## 14. Những sai lầm thường gặp

**Gọi API tạo dữ liệu trong `process()`:** lần xử lý lại có thể tạo nhiều tài nguyên. Hãy tạo command và lưu ý định trong outbox hoặc dùng API idempotent.

**Gửi email trực tiếp trong processor:** email không rollback cùng transaction chunk. Hãy ghi yêu cầu gửi vào outbox và để dispatcher gửi sau commit.

**Nghĩ rằng chuyển side effect sang writer là đủ:** writer cũng có thể được gọi lại sau rollback/retry. Cần transaction và idempotency.

**Dùng UUID mới cho mỗi lần retry:** hệ thống đích không nhận ra các yêu cầu là cùng một thao tác. Tạo khóa từ định danh nghiệp vụ ổn định.

**Dựa vào cache processor để bảo đảm một lần:** cache là chi tiết xử lý trong một số tình huống fault-tolerant, không phải cơ chế bền vững hoặc bảo đảm exactly-once.

**Gửi message trong listener:** listener không tự cung cấp transaction phân tán hoặc exactly-once. Dùng outbox cho sự kiện cần được phát đáng tin cậy.

**Dùng dữ liệu tham chiếu thay đổi theo thời gian:** retry có thể tạo kết quả khác cho cùng input. Dùng snapshot, version hoặc thời điểm nghiệp vụ rõ ràng.

**Nuốt lỗi side effect:** nếu API thất bại mà processor vẫn trả về kết quả thành công, job có thể đánh dấu item đã xử lý dù tác động nghiệp vụ chưa xảy ra. Hãy biểu diễn lỗi và retry/đối soát theo hợp đồng rõ ràng.

## 15. Cách thiết kế một chunk job có thể retry an toàn

Khi xây dựng job, hãy bắt đầu bằng việc xác định tác động nào là tính toán và tác động nào làm thay đổi trạng thái bên ngoài. Đưa các phép validate, normalize, calculate và map vào processor. Giữ input/output ổn định, tránh thay đổi object dùng chung và tránh phụ thuộc vào dữ liệu không có phiên bản.

Tiếp theo, xác định nơi ghi dữ liệu. Những thay đổi database cần commit cùng chunk nên được thực hiện trong writer và tham gia đúng transaction manager. Nếu cần gửi message, email hoặc gọi API sau khi dữ liệu được lưu, ghi một outbox event trong cùng transaction rồi dispatch riêng. Nếu phải gọi hệ thống đích trực tiếp, dùng idempotency key ổn định và có khả năng tra cứu kết quả sau timeout.

Cuối cùng, thử các tình huống rollback, retry, skip và restart. Đặc biệt, kiểm tra trường hợp side effect bên ngoài đã thành công nhưng ứng dụng mất phản hồi, writer thất bại sau khi processor chạy, hoặc dispatcher dừng sau khi publish nhưng trước khi đánh dấu event hoàn tất. Theo dõi số lần retry, số event pending, duplicate key và kết quả đối soát.

Processor nên tập trung tạo ra output có thể tính toán lại. Khi side effect được quản lý bằng transaction, outbox và idempotency ở đúng ranh giới, job Spring Batch có thể retry hoặc restart mà không vô tình lặp lại các tác động nghiệp vụ khó hoàn tác.
