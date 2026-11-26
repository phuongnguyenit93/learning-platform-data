# Chọn đồng bộ hay async

Khi một module Spring Modulith phát application event, các listener có thể xử lý ngay trong luồng gọi hoặc xử lý bất đồng bộ sau đó. Chọn cách nào ảnh hưởng trực tiếp đến thời gian phản hồi, transaction boundary, mức độ nhất quán, khả năng phục hồi và cách vận hành production.

Không có một chế độ đúng cho mọi event. Nếu người gọi cần kết quả của module khác ngay để quyết định tiếp, một lời gọi service có kiểu trả về thường phù hợp hơn event. Nếu module chỉ thông báo một sự kiện nghiệp vụ đã xảy ra và các module khác có thể hoàn tất công việc sau, event bất đồng bộ thường giúp giảm phụ thuộc thời gian và cô lập lỗi tốt hơn. Với một số trường hợp cần phản ứng ngay trong transaction, listener đồng bộ có thể là lựa chọn hợp lý.

Bài này đưa ra cách ra quyết định theo từng listener, giải thích semantics của synchronous listener, transactional event listener và @ApplicationModuleListener, rồi hướng dẫn đánh giá latency, consistency, failure, ordering, capacity và testing.

## 1. Phân biệt đồng bộ và bất đồng bộ

**Đồng bộ (synchronous)** nghĩa là listener được gọi trong cùng luồng thực thi với nơi publish event. publishEvent() chỉ trả về sau khi các listener đồng bộ đã chạy xong hoặc một listener ném exception làm luồng gọi thất bại.

**Bất đồng bộ (asynchronous)** nghĩa là listener được thực thi ở một thread/executor khác hoặc được chuyển qua broker. Luồng publish không phải chờ listener hoàn tất. Kết quả xử lý đến sau và cần được quan sát, retry hoặc xử lý lỗi theo cơ chế riêng.

Với Spring Modulith, cần phân biệt ba cách thường gặp:

| Cách đăng ký | Thời điểm chạy | Thread | Quan hệ với transaction |
|---|---|---|---|
| @EventListener | Ngay khi event được publish | Mặc định cùng thread | Có thể tham gia transaction hiện tại nếu listener gọi trong transaction đó |
| @TransactionalEventListener | Theo transaction phase; mặc định AFTER_COMMIT | Mặc định cùng thread ở phase tương ứng | Gắn với transaction phát event |
| @ApplicationModuleListener | Sau commit | Bất đồng bộ | Chạy trong transaction mới theo cấu hình annotation |

@ApplicationModuleListener là annotation tiện ích của Spring Modulith dành cho listener giữa các module. Nó kết hợp xử lý bất đồng bộ, transactional event listener và transaction riêng cho listener. Hãy đối chiếu API của phiên bản Spring Modulith mà dự án sử dụng khi cấu hình hoặc nâng cấp.

Một điểm quan trọng: AFTER_COMMIT không đồng nghĩa với asynchronous. @TransactionalEventListener mặc định chạy sau commit nhưng vẫn có thể chạy đồng bộ trên thread hoàn tất transaction. Ngược lại, @Async không tự động có nghĩa event chỉ được xử lý sau khi transaction nguồn commit.

## 2. Quyết định theo nhu cầu của người gọi

Câu hỏi đầu tiên không phải là hệ thống có thể chạy async hay không, mà là người gọi cần biết điều gì trước khi trả kết quả.

| Nhu cầu | Hướng phù hợp |
|---|---|
| Cần kết quả ngay để quyết định hoặc trả response | Gọi application service trực tiếp và nhận kết quả |
| Cần thay đổi dữ liệu cùng transaction hiện tại | Gọi service trong transaction hoặc dùng xử lý đồng bộ phù hợp |
| Chỉ cần thông báo sự kiện đã xảy ra | Publish event; chọn sync/async theo yêu cầu listener |
| Công việc có thể hoàn tất sau response | Listener async |
| Công việc chậm, có thể retry độc lập | Listener async với registry/persistence phù hợp |
| Lỗi listener không được làm request ban đầu thất bại | Async, kèm cơ chế theo dõi và phục hồi |
| Cần xác nhận nhiều hệ thống đã xử lý xong | Workflow có trạng thái, saga/process manager hoặc API truy vấn trạng thái |

Ví dụ, khi đặt hàng, API cần biết đơn hàng đã được tạo hợp lệ hay chưa. Việc ghi đơn hàng và xác nhận các quy tắc bắt buộc phải hoàn tất trước khi trả response. Nhưng gửi email, cập nhật analytics hoặc đồng bộ một read model có thể hoàn tất sau.

Nếu caller cần một giá trị trả về từ module Inventory để quyết định có chấp nhận đơn hàng hay không, một event fire-and-forget không đáp ứng được nhu cầu đó. Hãy gọi API/service phù hợp hoặc thiết kế quy trình bất đồng bộ có trạng thái chờ và kết quả riêng.

## 3. Dùng đồng bộ khi kết quả phải có ngay

Synchronous listener phù hợp khi xử lý ngắn, có chi phí dự đoán được và kết quả cần nằm trong cùng luồng quyết định.

Các trường hợp có thể cân nhắc:

- Cập nhật một phần dữ liệu cần thiết trước khi transaction commit.
- Thực hiện một phản ứng nội bộ rất nhẹ và không phụ thuộc mạng.
- Kiểm tra hoặc tính toán cục bộ cần hoàn tất trước khi publisher tiếp tục.
- Giữ một invariant trong cùng transaction boundary, nếu thiết kế event và transaction thực sự bảo đảm điều đó.

Ví dụ listener đồng bộ:

~~~java
@Component
class UpdateOrderSummaryOnOrderPlaced {

    private final OrderSummaryRepository summaries;

    UpdateOrderSummaryOnOrderPlaced(
            OrderSummaryRepository summaries
    ) {
        this.summaries = summaries;
    }

    @EventListener
    void on(OrderPlaced event) {
        summaries.createInitialSummary(event.orderId());
    }
}
~~~

Nếu event được publish bên trong transaction và repository tham gia cùng transaction manager, thao tác này có thể commit hoặc rollback cùng transaction nguồn. Điều đó phải được xác minh qua cấu hình transaction thực tế; chỉ dùng annotation listener không tự bảo đảm mọi datasource hoặc transaction manager đều nguyên tử.

Đồng bộ cũng phù hợp khi lỗi listener cần làm thao tác nguồn thất bại. Ví dụ, nếu một bước kiểm tra nội bộ là điều kiện bắt buộc để chấp nhận nghiệp vụ, việc ném exception có thể khiến transaction nguồn rollback.

Tuy nhiên, nếu đây thực chất là yêu cầu lấy kết quả từ module khác, gọi service trực tiếp thường diễn đạt ý định rõ hơn publish event rồi chờ listener cập nhật một biến dùng chung.

## 4. Chi phí của synchronous listener

Mỗi listener đồng bộ kéo dài thời gian của luồng publish. Nếu một event có bốn listener lần lượt mất 30 ms, 50 ms, 100 ms và 200 ms, thời gian chờ có thể tăng ít nhất khoảng 380 ms, chưa tính overhead và truy cập database.

Các rủi ro:

- Response API chậm theo tổng thời gian listener.
- Transaction giữ connection và lock lâu hơn.
- Một listener chậm làm các listener sau phải chờ.
- Exception listener có thể lan ngược về publisher.
- Dependency bên ngoài không sẵn sàng có thể làm request thất bại.
- Tải tăng ở một module ảnh hưởng trực tiếp module phát event.

Không gọi HTTP, gửi email hoặc chờ broker confirm bên trong transaction đồng bộ dài nếu nghiệp vụ không yêu cầu điều đó. Một transaction giữ lock trong khi chờ network có thể làm tăng contention và tạo chuỗi timeout.

Nếu có nhiều listener đồng bộ, xác định rõ listener nào là phần bắt buộc của use case và listener nào chỉ là side effect có thể xử lý sau. Không biến mọi subscriber thành một phần của critical path chỉ vì mặc định event multicaster chạy đồng bộ.

## 5. Chọn asynchronous khi công việc có thể hoàn tất sau

Async phù hợp khi publisher chỉ cần công bố sự kiện và không cần đợi từng listener hoàn tất.

Các trường hợp thường gặp:

- Gửi email, push notification hoặc webhook.
- Cập nhật projection/read model.
- Ghi analytics hoặc audit phụ trợ.
- Đồng bộ dữ liệu sang hệ thống khác.
- Tạo tài liệu hoặc xử lý file.
- Chạy các bước downstream có thời gian xử lý biến động.
- Thực hiện công việc có thể retry độc lập.

Ví dụ listener theo kiểu Spring Modulith:

~~~java
@Component
class SendOrderConfirmation {

    private final EmailService emailService;

    SendOrderConfirmation(EmailService emailService) {
        this.emailService = emailService;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        emailService.sendOrderConfirmation(event.orderId());
    }
}
~~~

Publisher không phải chờ email được gửi. Listener được kích hoạt sau khi transaction nguồn commit và chạy trong transaction riêng theo semantics của @ApplicationModuleListener.

Async giúp tách thời gian xử lý giữa các module, nhưng không làm công việc biến mất. Hệ thống vẫn cần capacity, backpressure, retry, idempotency, timeout, quan sát và chính sách xử lý message lỗi.

## 6. Transaction phase và tính nhất quán

Chọn sync/async phải đi cùng câu hỏi event được phát ở thời điểm nào.

### 6.1. @EventListener

@EventListener được gọi ngay khi publishEvent() chạy. Nếu publisher đang ở trong transaction, listener đồng bộ có thể tham gia luồng transaction hiện tại khi các thao tác dùng cùng transaction resource và propagation phù hợp.

Nếu listener ném exception, exception có thể truyền về publisher và làm transaction nguồn rollback. Đây là hành vi cần thiết trong một số trường hợp, nhưng có thể không mong muốn với side effect phụ trợ.

### 6.2. @TransactionalEventListener

@TransactionalEventListener gắn việc xử lý với transaction phase. Mặc định là AFTER_COMMIT; có thể chọn các phase như BEFORE_COMMIT, AFTER_ROLLBACK hoặc AFTER_COMPLETION khi phù hợp.

~~~java
@Component
class AuditOrderPlacement {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    void on(OrderPlaced event) {
        // Ghi nhận hành động sau khi transaction nguồn commit
    }
}
~~~

Listener AFTER_COMMIT mặc định vẫn chạy đồng bộ nếu không kết hợp cơ chế async. Vì transaction đã commit, exception tại listener không thể rollback dữ liệu nguồn. Nếu listener cần ghi dữ liệu mới, hãy thiết kế transaction riêng phù hợp; không giả định thao tác ghi sau commit sẽ được commit cùng transaction cũ.

Nếu event được publish ngoài transaction, transactional listener thường không chạy trừ khi bật fallbackExecution. Chỉ bật fallback khi xử lý event không có transaction là hành vi được nghiệp vụ cho phép.

### 6.3. @ApplicationModuleListener

@ApplicationModuleListener được thiết kế cho giao tiếp event giữa các module theo hướng async và transaction riêng. Event được xử lý sau commit; listener có transaction độc lập để thực hiện công việc của module nhận.

~~~java
@Component
class UpdateInventoryOnOrderPlaced {

    private final InventoryService inventory;

    UpdateInventoryOnOrderPlaced(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        inventory.reserve(event.orderId());
    }
}
~~~

Nếu listener thất bại, transaction riêng của listener có thể rollback. Với Event Publication Registry được cấu hình bền vững, publication chưa hoàn tất có thể được quan sát và resubmit theo API của phiên bản Spring Modulith đang dùng.

Không hiểu registry là bảo đảm exactly-once. Listener có thể thực hiện side effect rồi thất bại trước khi publication được đánh dấu hoàn tất; khi resubmit, side effect có thể được gọi lại. Thiết kế listener idempotent.

## 7. Độ nhất quán và trải nghiệm người dùng

Async thường tạo eventual consistency: dữ liệu của module phát đã commit, trong khi projection hoặc module nhận chưa cập nhật ngay.

Điều này cần được phản ánh trong hợp đồng API và giao diện người dùng.

Ví dụ:

- API trả 201 Created khi đơn hàng đã được tạo.
- Response có orderId và trạng thái PROCESSING hoặc PENDING_FULFILLMENT.
- Inventory và Shipping xử lý sau.
- Client truy vấn trạng thái đơn hàng hoặc nhận notification khi hoàn tất.

Không trả trạng thái COMPLETED chỉ vì event đã được publish. Publish event là bắt đầu giao việc; trạng thái hoàn tất chỉ được ghi khi bước nghiệp vụ cuối cùng xác nhận thành công.

Nếu người dùng cần kết quả ngay, cân nhắc synchronous service call cho phần quyết định và async event cho side effect phụ trợ. Một use case có thể kết hợp cả hai cách thay vì chọn một chế độ duy nhất cho toàn bộ event.

## 8. Độ tin cậy và khả năng phục hồi

Async tạo ra một khoảng thời gian giữa commit nguồn và xử lý listener. Khoảng thời gian này cần được quản lý.

Với Spring Modulith, Event Publication Registry theo dõi publication tới các transactional listener. Khi dùng persistence implementation phù hợp, ứng dụng có thể tìm publication chưa hoàn tất và resubmit sau khi sửa nguyên nhân lỗi.

Cần xác định:

- Registry đang dùng persistence nào và schema đã được triển khai chưa?
- Publication nào được theo dõi và retention ra sao?
- Cách phát hiện listener lỗi hoặc publication bị kẹt?
- Ai được phép resubmit và bằng công cụ/runbook nào?
- Listener có idempotent khi nhận event lại không?
- Exception nào được retry và exception nào cần quarantine?

Nếu event cần được chuyển ra broker, registry nội bộ không tự thay thế transactional outbox, publisher confirm hoặc broker acknowledgement. Chọn cơ chế đảm bảo delivery phù hợp với ranh giới vận chuyển.

Với side effect quan trọng, không dùng async fire-and-forget không có persistence hoặc giám sát. Nếu process dừng sau commit nhưng trước khi listener xử lý, cần một cơ chế bền vững để công việc không bị mất.

## 9. Ordering và concurrency

Synchronous listener trong cùng luồng thường có thứ tự gọi xác định theo cấu hình listener và order, nhưng không nên dựa vào thứ tự ngẫu nhiên nếu nghiệp vụ cần một trình tự cụ thể. Có thể dùng @Order khi thứ tự listener thực sự là hợp đồng và được kiểm thử.

Async listener có thể chạy đồng thời hoặc hoàn tất theo thứ tự khác thứ tự publish. Nhiều event của cùng aggregate có thể được xử lý song song nếu executor cho phép.

Nếu thứ tự là bắt buộc:

- Đưa aggregateId và aggregateVersion/sequence vào event.
- Phân vùng theo aggregate key khi dùng broker hỗ trợ ordering theo partition.
- Dùng optimistic locking hoặc cơ chế serialize cập nhật projection.
- Phát hiện sequence gap và có quy trình chờ/reconcile.
- Không giả định một executor thread duy nhất là giải pháp ordering bền vững khi scale nhiều instance.

Có thể xử lý song song giữa các aggregate độc lập nhưng tuần tự trong cùng aggregate. Chọn mức concurrency theo invariant nghiệp vụ, không chỉ theo throughput tối đa.

## 10. Latency, throughput và backpressure

Async không tự động nhanh hơn. Nó chuyển thời gian xử lý ra khỏi request thread, nhưng tổng công việc và tải database vẫn tồn tại.

Khi đánh giá capacity, đo:

- Event arrival rate.
- Listener completion rate.
- Processing latency P50/P95/P99.
- Số publication chưa hoàn tất và oldest age.
- Executor active threads, queue depth và task rejection.
- Database connection pool, CPU, I/O và lock wait.
- Retry, redelivery và DLQ rate.

Nếu arrival rate liên tục cao hơn completion rate, backlog sẽ tăng. Tăng thread có thể làm database hoặc external API quá tải. Dùng bounded queue, giới hạn concurrency, rate limit và backpressure phù hợp.

Với synchronous path, giới hạn độ dài critical path và tránh thực hiện công việc không bắt buộc trước response. Với async path, xác định SLA hoàn tất và cảnh báo khi tuổi publication vượt ngưỡng.

## 11. Failure semantics và xử lý exception

Đồng bộ và async có hành vi lỗi khác nhau.

| Tình huống | Đồng bộ | Bất đồng bộ |
|---|---|---|
| Listener ném exception trước commit | Có thể lan về publisher và làm rollback transaction | Không lan về request đã trả; listener transaction có thể rollback |
| Dependency ngoài timeout | Có thể kéo dài request/transaction | Tăng retry/backlog; cần timeout và retry policy |
| Process dừng | Công việc chưa commit có thể rollback cùng transaction | Cần registry/outbox/broker bền vững để phục hồi |
| Retry | Thường do caller/use case điều khiển | Có thể do registry, listener retry hoặc broker policy |
| Quan sát | Log trong request path | Cần metric backlog, publication age và listener outcome |

Không bắt exception rồi bỏ qua trong listener đồng bộ nếu điều đó khiến publisher tưởng mọi việc đã thành công. Với async, cũng không catch rồi return bình thường khi side effect chưa hoàn tất; framework có thể xem listener đã xử lý thành công và đánh dấu publication hoàn tất.

Phân loại lỗi tạm thời và lỗi cố định. Timeout database có thể retry; payload schema không hỗ trợ thường cần quarantine hoặc cập nhật consumer, không retry vô hạn.

## 12. Không dùng event để thay lời gọi cần kết quả

Event mô tả một sự kiện đã xảy ra; command yêu cầu một hành động; query yêu cầu dữ liệu. Ba loại giao tiếp này không nên bị trộn lẫn.

Ví dụ không phù hợp:

- Publish CheckCreditLimit rồi chờ listener cập nhật một biến dùng chung.
- Publish FindCustomerAddress rồi đợi event phản hồi trong cùng request.
- Dùng async event cho bước bắt buộc phải biết kết quả trước khi commit đơn hàng.

Nếu caller cần kết quả ngay, gọi application service/query API và nhận kết quả rõ ràng. Nếu quy trình cần nhiều bước và có thể kéo dài, dùng saga/process manager với trạng thái bền vững và kết quả truy vấn được.

Event phù hợp hơn khi module thông báo OrderPlaced, PaymentCaptured hoặc InventoryReserved để các module khác phản ứng độc lập.

## 13. Có thể kết hợp sync và async trong cùng một event flow

Một event có thể có nhiều listener với yêu cầu khác nhau. Ví dụ sau khi Order được tạo:

- Một listener đồng bộ, nhẹ, cập nhật dữ liệu cần thiết trong cùng transaction nếu invariant yêu cầu.
- Một listener transactional AFTER_COMMIT ghi audit phụ trợ.
- Một @ApplicationModuleListener bất đồng bộ yêu cầu Inventory xử lý.
- Một adapter outbox gửi integration event sang broker.

Mỗi listener cần có lý do rõ ràng cho chế độ thực thi. Tránh để tất cả listener dùng chung một chế độ chỉ vì tiện cấu hình.

~~~text
Order service
    |
    | publish OrderPlaced trong transaction
    |
    +--> synchronous listener
    |      cập nhật dữ liệu bắt buộc
    |
    +--> AFTER_COMMIT listener
    |      ghi nhận sau commit
    |
    +--> @ApplicationModuleListener
    |      async, transaction riêng
    |
    +--> outbox adapter
           gửi integration message theo cơ chế bền vững
~~~

Sơ đồ minh họa các lựa chọn kiến trúc, không có nghĩa mọi ứng dụng cần cả bốn nhánh. Chỉ giữ các nhánh đáp ứng yêu cầu nghiệp vụ và reliability đã xác định.

## 14. Ví dụ quyết định cho use case đặt hàng

Giả sử use case đặt hàng cần kiểm tra dữ liệu đầu vào, tạo Order và sau đó thực hiện fulfillment.

| Công việc | Chọn | Lý do |
|---|---|---|
| Validate command và quy tắc tạo Order | Đồng bộ trong use case | Phải quyết định trước khi trả response |
| Lưu Order | Đồng bộ trong transaction | Là kết quả chính của request |
| Tính dữ liệu bắt buộc để chấp nhận đơn | Đồng bộ hoặc gọi service trực tiếp | Cần kết quả ngay |
| Gửi email xác nhận | Async | Có thể gửi sau và retry độc lập |
| Cập nhật read model | Async nếu chấp nhận eventual consistency | Không cần giữ request chờ projection |
| Giữ hàng | Tùy nghiệp vụ; thường async nếu là quy trình riêng có trạng thái | Có thể cần retry/compensation và không giữ transaction Order |
| Gửi event sang hệ thống đối tác | Outbox/async transport | Cần delivery bền vững và theo dõi confirm |
| Trả trạng thái fulfillment | Truy vấn trạng thái hoặc notification | Kết quả đến sau khi downstream hoàn tất |

Nếu hệ thống yêu cầu không chấp nhận đơn hàng khi không giữ được tồn kho, có hai hướng khác nhau: gọi Inventory đồng bộ để lấy quyết định ngay, hoặc chấp nhận Order ở trạng thái pending và xử lý saga bất đồng bộ. Không dùng async rồi vẫn trả response như thể reservation đã thành công.

## 15. Kiểm thử synchronous và asynchronous listener

Test phải phản ánh đúng transaction và thời điểm xử lý.

### 15.1. Kiểm thử đồng bộ

Với @EventListener, có thể publish event rồi assert kết quả ngay sau khi publishEvent() trả về, nếu listener thực sự chạy đồng bộ và không có cơ chế async khác.

Kiểm tra:

- Listener được gọi đúng một lần theo expectation.
- Side effect tham gia transaction như thiết kế.
- Exception có lan về publisher hay không.
- Rollback có hoàn tác side effect cùng transaction không.
- Thứ tự listener nếu đó là hợp đồng bắt buộc.

### 15.2. Kiểm thử transactional listener

Với @TransactionalEventListener, cần tạo transaction và xác minh phase tương ứng. Test method có transaction mặc định rollback có thể không kích hoạt AFTER_COMMIT như mong muốn.

Dùng transaction commit thực sự trong test hoặc công cụ điều khiển transaction phù hợp. Kiểm tra cả trường hợp rollback và trường hợp publish ngoài transaction nếu ứng dụng có hỗ trợ.

### 15.3. Kiểm thử async

Với @ApplicationModuleListener, không assert ngay sau khi publisher trả về. Dùng Scenario của Spring Modulith, Awaitility hoặc latch có timeout để chờ event/state kết quả.

Kiểm tra:

- Listener được gọi sau commit.
- Listener dùng transaction riêng theo cấu hình.
- Listener exception để lại publication chưa hoàn tất khi registry bền vững được cấu hình.
- Resubmit sau khi sửa lỗi hoạt động.
- Duplicate không tạo side effect lặp.
- Context/MDC được truyền và dọn đúng nếu log cần correlation ID.

Không dùng Thread.sleep() cố định. Test nên đợi điều kiện thực tế với timeout hữu hạn.

## 16. Quy trình ra quyết định

Khi thiết kế một listener, trả lời theo thứ tự:

1. Người gọi có cần kết quả của listener trước khi trả response không?
2. Side effect có bắt buộc commit cùng transaction nguồn không?
3. Nếu listener lỗi, nghiệp vụ nguồn có phải thất bại không?
4. Công việc có thể hoàn tất sau và người dùng có chấp nhận trạng thái pending không?
5. Listener có thể retry độc lập và idempotent không?
6. Có yêu cầu ordering theo aggregate không?
7. Có registry/outbox/broker persistence phù hợp không?
8. Arrival rate và downstream capacity có đáp ứng được không?
9. Có metric, alert và runbook cho listener không?
10. Test có xác minh đúng transaction phase và failure semantics không?

Sau khi trả lời, ghi lại quyết định theo từng listener: chế độ, transaction phase, timeout, retry policy, idempotency key, ordering requirement, SLA và owner.

## 17. Lỗi thiết kế thường gặp

**Chọn async chỉ để làm request nhanh hơn.** Nếu caller vẫn cần kết quả, trạng thái pending phải được thiết kế rõ hoặc cần gọi service trực tiếp.

**Cho mọi listener chạy đồng bộ.** Critical path dài và một listener chậm ảnh hưởng tất cả module.

**Nhầm AFTER_COMMIT với async.** Transaction phase và execution thread là hai khái niệm khác nhau.

**Dùng @Async mà không nghĩ về transaction.** Thread khác không tự kế thừa transaction nguồn. Chọn transactional listener và transaction riêng khi phù hợp.

**Fire-and-forget cho side effect quan trọng.** Process có thể dừng và công việc không được phục hồi nếu không có persistence.

**Không làm listener idempotent.** Resubmit hoặc redelivery có thể lặp side effect.

**Tăng concurrency mà không đo downstream.** Database hoặc external API có thể trở thành bottleneck mới.

**Giả định async giữ thứ tự.** Event của cùng aggregate có thể hoàn tất sai thứ tự nếu không có sequence/serialization.

**Dùng event request-response.** Caller phải chờ event phản hồi và tạo coupling thời gian. Dùng service/query API hoặc workflow có trạng thái.

**Không có SLA cho eventual consistency.** Người dùng không biết khi nào trạng thái downstream phải hoàn tất và đội vận hành không có ngưỡng cảnh báo.

## 18. Checklist trước khi chọn chế độ

- [ ] Đã xác định người gọi cần kết quả ngay hay chỉ cần công bố sự kiện.
- [ ] Đã phân biệt event, command và query.
- [ ] Đã xác định transaction phase và transaction manager.
- [ ] Đã đánh giá ảnh hưởng của listener lên response latency.
- [ ] Đã xác định hành vi khi listener ném exception.
- [ ] Async listener có persistence/registry hoặc transport bền vững phù hợp.
- [ ] Listener có idempotency và xử lý duplicate.
- [ ] Ordering và aggregate sequence được bảo vệ nếu cần.
- [ ] Có timeout, retry, backpressure và DLQ/quarantine phù hợp.
- [ ] Có metric backlog, processing latency và oldest age.
- [ ] API/UI thể hiện trạng thái pending nếu eventual consistency.
- [ ] Test bao phủ commit, rollback, async completion và failure.

## 19. Kết luận quyết định

Chọn synchronous khi công việc là một phần của quyết định hiện tại, cần kết quả ngay hoặc phải tham gia transaction nguồn. Chọn asynchronous khi event thông báo một sự kiện đã xảy ra, listener có thể hoàn tất sau, cần cô lập lỗi hoặc có thể retry độc lập. Khi caller cần phản hồi tức thời từ module khác, hãy dùng service/query API thay vì biến event thành request-response.

Trong Spring Modulith, @EventListener, @TransactionalEventListener và @ApplicationModuleListener có semantics khác nhau về thời điểm, thread và transaction. Quyết định đúng cần được đưa ra cho từng listener, dựa trên consistency, failure handling, ordering, capacity và SLA. Một thiết kế tốt không chỉ làm request nhanh hoặc listener chạy song song; nó giúp các module phối hợp với mức độ nhất quán và độ tin cậy mà nghiệp vụ thực sự yêu cầu.
