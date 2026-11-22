# Throw exception on rejection

## 1. Vấn đề: Filter từ chối message thì hệ thống biết bằng cách nào?

Trong một luồng xử lý đơn hàng, một message đến từ HTTP, broker hoặc Gateway. **Filter** phải quyết định một đơn hàng có được chuyển tiếp hay không. Chẳng hạn, đơn phải có mã định danh và số lượng dương. Với một đơn không hợp lệ, có nhiều hành vi rất khác nhau:

- Không chuyển tiếp message và **im lặng loại bỏ**.
- Không chuyển tiếp message nhưng gửi tới **discard channel** để ghi nhận và xử lý.
- **Ném ngoại lệ** để bên gọi hoặc error handling của hệ thống biết việc từ chối.

Trong Spring Integration, lựa chọn thứ ba được điều khiển bởi cấu hình `throwExceptionOnRejection` của `MessageFilter`. Khi selector trả về `false` và cờ này là `true`, Filter phát sinh `MessageRejectedException`. Đây là một tín hiệu lỗi **có chủ đích** tại ranh giới message, không phải một exception ngẫu nhiên do mã kiểm tra bị lỗi.

**Câu hỏi quan trọng:** từ chối một message là hành vi bình thường của nghiệp vụ hay là lỗi khiến producer/poller phải được thông báo? Không có câu trả lời chung. Bật exception sai chỗ có thể dẫn tới **retry liên tục cùng một message không hợp lệ**, rollback transaction không cần thiết hoặc Gateway trả lỗi thay vì kết quả từ chối có cấu trúc.

Bài thuộc chương **Filter** của module **SPRING_INTEGRATION_PATTERN**. Nội dung hỗ trợ việc học triển khai Enterprise Integration Patterns với Spring Integration: xây dựng luồng thông điệp ít phụ thuộc, kết hợp **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel và correlation**, đồng thời kiểm thử và quan sát các nhánh xử lý.

Sau bài này, bạn sẽ hiểu hành vi mặc định và khi bật exception, cách cấu hình Java DSL/annotation/XML, cách xử lý trong flow đồng bộ và bất đồng bộ, tương tác với transaction, advice và discard channel, cũng như cách kiểm thử message bị từ chối mà không tạo side effect ngoài ý muốn.

## 2. Filter hoạt động theo hợp đồng nào?

**Message Filter** triển khai mẫu **Selective Consumer** trong Enterprise Integration Patterns. Nó đọc một message và hỏi **selector** xem message có được chấp nhận không. Một selector tiêu biểu có dạng hàm thuần:

~~~java
record OrderRequest(
    String eventId,
    String orderId,
    Integer quantity
) {}

final class OrderGuard {
    public boolean accepted(OrderRequest order) {
        return order.eventId() != null
            && !order.eventId().isBlank()
            && order.orderId() != null
            && !order.orderId().isBlank()
            && order.quantity() != null
            && order.quantity() > 0;
    }
}
~~~

Tại Filter:

| Kết quả selector | Hành vi Filter |
|---|---|
| `true` | Chuyển message đến output channel; các handler sau có thể tiếp tục xử lý |
| `false`, chế độ mặc định | Không chuyển sang output; đưa tới discard channel nếu đã cấu hình, nếu không thì loại |
| `false` và `throwExceptionOnRejection=true` | Không chuyển sang output; phát sinh `MessageRejectedException` |
| Selector tự ném exception | Lỗi runtime từ việc đánh giá predicate, cần xử lý theo exception/error policy |

Một điểm cần phân biệt: **selector trả `false`** là kết luận hợp lệ của thuật toán, còn **selector ném exception** có thể do dữ liệu sai kiểu, bug, timeout hoặc logic bên ngoài. Cả hai có thể khiến flow thất bại, nhưng chúng không cùng một nguyên nhân, không nhất thiết nên có cùng mã lỗi hoặc cùng chiến lược retry.

Filter không phải Router. Filter trả lời “message có được đi tiếp không?”, còn Router trả lời “message đi theo nhánh nào?”. Nếu bạn cần phân biệt nhiều loại lỗi như `MISSING_FIELD`, `UNSUPPORTED_VERSION`, `BUSINESS_REJECTED`, đôi khi **classifier + Router** hữu ích hơn một predicate boolean duy nhất.

## 3. Ba cách xử lý rejection

~~~mermaid
flowchart TD
    IN["orders.in"] --> F{"Filter selector"}
    F -->|"true"| OK["orders.accepted"]
    F -->|"false"| R{"Rejection policy"}
    R -->|"Mặc định"| DROP["Loại message / không output"]
    R -->|"discardChannel"| DC["orders.rejected"]
    R -->|"throwExceptionOnRejection"| EX["MessageRejectedException"]
    EX --> ERR["Caller / error handler / transaction boundary"]
~~~

| Cấu hình | Có message ở output? | Có discard message? | Có exception khi predicate=false? |
|---|---:|---:|---:|
| Mặc định, không discard | Không | Không | Không |
| `discardChannel("orders.rejected")` | Không | Có | Không |
| `throwExceptionOnRejection(true)` | Không | Không, trừ khi cấu hình riêng | Có |
| **Cả discard và throw** | Không | **Có** | **Có, sau thao tác discard** |

Điểm cuối rất dễ gây hiểu nhầm. Theo hành vi của `MessageFilter`, nếu đồng thời cấu hình `discardChannel` và `throwExceptionOnRejection=true`, **message vẫn được gửi sang discard channel, sau đó exception vẫn được ném**. Đây không phải cơ chế chọn *một trong hai*. Nếu discard handler đã lưu một bản ghi hoặc gửi sang broker, rồi transaction upstream rollback và retry, bạn có thể thấy **nhiều lần ghi nhận cùng một rejection**.

Không nên bật cả hai chỉ vì “muốn chắc chắn message lỗi không mất”. Hãy xác định hành vi thực sự cần: phản hồi lỗi trực tiếp, phân luồng xử lý rejection, hay cả hai theo hợp đồng đã có idempotency.

**Ghi chú về log:** từ Spring Integration 6.1, Filter mặc định không có discard channel và không bật exception có thể ghi cảnh báo về message bị loại. Vì thế “silently dropped” là mô tả semantics định tuyến, **không đảm bảo log luôn hoàn toàn im lặng**.

## 4. Java DSL: bật `throwExceptionOnRejection(true)`

Giữ ví dụ ngắn, có contract cụ thể. Lưu ý các đoạn cấu hình tiếp theo **là các phương án thay thế**, không đăng ký đồng thời nhiều flow với cùng input để tránh tranh chấp subscriber.

~~~java
@Configuration
@EnableIntegration
public class RejectingOrderFlow {

    @Bean
    OrderGuard orderGuard() {
        return new OrderGuard();
    }

    @Bean
    IntegrationFlow rejectInvalidOrders(OrderGuard guard) {
        return IntegrationFlow.from("orders.in")
            .filter(OrderRequest.class, guard::accepted,
                spec -> spec.throwExceptionOnRejection(true))
            .channel("orders.accepted")
            .get();
    }
}
~~~

Ở đây:

1. `orders.in` nhận `OrderRequest`.
2. Filter gọi `OrderGuard.accepted(order)`.
3. Nếu kết quả là `true`, message đi tới `orders.accepted`.
4. Nếu kết quả là `false`, Filter ném `MessageRejectedException`; **không có message** được phát đến `orders.accepted` từ nhánh đó.
5. Channel `orders.accepted` cần consumer thật, ví dụ một Service Activator hoặc một test channel; chỉ khai báo tên channel mà không có người xử lý không tạo ra quy trình nghiệp vụ hoàn chỉnh.

Ví dụ sử dụng Java record (Java 17+) và Spring Integration Java DSL. Các import được lược bỏ. Khi tích hợp, bảo đảm cấu hình ứng dụng quét các bean và tải dependency Spring Integration phù hợp.

**Tuyệt đối không** dùng đoạn Filter trên như giải pháp đầy đủ cho input có payload bất kỳ. Overload typed filter giả định payload của message có thể được chuyển sang `OrderRequest`. Khi giao thức đầu vào có thể gửi JSON lỗi, `String` hoặc `byte[]`, cần decode, validate type/schema ở adapter hoặc dựng một type gate riêng **trước** khi predicate này được gọi.

## 5. So sánh với discard channel trong Java DSL

Nếu business muốn nhận message lỗi để báo trạng thái `REJECTED` mà **không làm producer gặp exception**, cấu hình discard:

~~~java
@Bean
IntegrationFlow routeInvalidOrdersToDiscard(OrderGuard guard) {
    return IntegrationFlow.from("orders.in")
        .filter(OrderRequest.class, guard::accepted,
            spec -> spec.discardChannel("orders.rejected"))
        .channel("orders.accepted")
        .get();
}

@Bean
IntegrationFlow processRejections() {
    return IntegrationFlow.from("orders.rejected")
        .handle(message ->
            System.out.println("Rejected order: "
                + message.getHeaders().getId()))
        .get();
}
~~~

Đoạn `processRejections()` chỉ minh họa logging. Trong ứng dụng production, handler nên ghi nhận **reason code** và event ID, dùng dữ liệu đã được kiểm tra, không log nguyên payload nhạy cảm và không giả định `MessageHeaders.ID` là mã sự kiện ổn định qua redelivery.

**Quan trọng:** nếu chỉ dùng `discardChannel`, mọi thứ có thể trông giống một lần `send()` thành công với upstream. Vì vậy, không được dùng kết quả Boolean của `send()` để suy ra **đơn đã qua Filter** hay handler nghiệp vụ đã commit. Đối với Gateway request–reply, Filter không sinh reply sau khi từ chối có thể khiến caller chờ đến timeout nếu không có quy trình gửi phản hồi phù hợp.

## 6. Nếu vừa discard vừa throw thì thứ tự nào được áp dụng?

Cấu hình dưới **có chủ đích bật đồng thời cả hai**:

~~~java
.filter(OrderRequest.class, guard::accepted,
    spec -> spec
        .discardChannel("orders.rejected")
        .throwExceptionOnRejection(true))
~~~

Khi predicate trả `false`, Filter có thể chuyển message đến discard channel rồi **ném ngoại lệ**. Do đó:

- Message không đi vào output thành công.
- Discard consumer có thể thực hiện side effect trước khi upstream thấy exception.
- Nếu transaction bao trùm cả discard consumer và rollback được, side effect trong cùng transaction có thể bị rollback; **không áp dụng cho mọi hệ thống ngoài**.
- Nếu discard consumer lưu file, gọi HTTP hoặc ghi sang một storage khác không cùng transaction, retry từ upstream có thể ghi nhiều bản.
- Nếu discard consumer tự ném exception, đường lỗi quan sát được có thể là lỗi của discard handling, không chỉ lỗi rejection ban đầu.

Để tránh nhầm, hãy chọn một trong hai mẫu:

**Mẫu A – Rejection là dữ liệu nghiệp vụ:** route message sang reject flow, lưu outcome `REJECTED`, tạo response/event phù hợp mà không ném exception để kích hoạt retry upstream.

**Mẫu B – Rejection là điều kiện lỗi:** bật `throwExceptionOnRejection`, cho error boundary chuyển sang HTTP error, rollback hoặc flow xử lý thất bại có kiểm soát.

Chỉ kết hợp cả hai khi bạn thực sự cần **vừa lưu message bị loại vừa báo lỗi** và đã thiết kế idempotency, transaction, monitoring cho tình huống gửi lặp.

## 7. Cấu hình bằng annotation và XML

Ngoài Java DSL, Spring Integration có annotation cho Filter:

~~~java
@Component
class AnnotatedOrderGuard {

    @Filter(
        inputChannel = "orders.in",
        outputChannel = "orders.accepted",
        throwExceptionOnRejection = "true")
    public boolean accept(OrderRequest order) {
        return order.quantity() != null && order.quantity() > 0;
    }
}
~~~

Ví dụ annotation sử dụng chuỗi `"true"` theo thuộc tính annotation của Spring Integration. **Đây là một lựa chọn thay thế** cho flow Java DSL ở mục 4. Không khai báo cả hai trong cùng test context, trừ khi bạn chủ ý tạo nhiều selective consumer và đã thiết kế dispatcher.

Trong cấu hình XML namespace:

~~~xml
<int:filter input-channel="orders.in"
            output-channel="orders.accepted"
            ref="orderSelector"
            method="accept"
            throw-exception-on-rejection="true"/>
~~~

Bean `orderSelector` cần có phương thức tương ứng trả boolean; cần khai báo namespace XML và bean trong Spring context. Mặc định của thuộc tính này là `false`. Nếu dùng Spring Boot/Java DSL, không nhất thiết phải dùng XML; đoạn này giúp đọc các cấu hình dự án cũ.

## 8. Exception cụ thể là gì?

Khi selector trả `false` và `throwExceptionOnRejection=true`, `MessageFilter` ném **`MessageRejectedException`**. Nó là một ngoại lệ dạng messaging của Spring Integration, mang ngữ cảnh message bị từ chối để chẩn đoán.

Phân biệt với các lỗi khác:

| Tình huống | Kết quả | Hướng xử lý |
|---|---|---|
| Selector trả `false` | `MessageRejectedException` nếu bật cờ | Rejection policy |
| Selector gọi method trên `null` | Có thể phát sinh runtime exception/wrapper | Sửa dữ liệu/validator/predicate |
| Payload sai kiểu trước selector | Type conversion hoặc handler error | Type gate/contract validation |
| Không có consumer trên output channel | Lỗi gửi/dispatch tùy channel | Kiểm tra topology |
| Discard handler lỗi | Exception khi gửi hoặc xử lý discard | Error path của discard flow |
| Consumer downstream lỗi | Lỗi sau khi Filter đã chấp nhận | Retry/error policy của consumer |

**Không khẳng định exception cụ thể luôn xuất hiện trực tiếp ở đầu caller.** Một Gateway, poller hoặc adapter có thể bọc nó bằng messaging exception khác hoặc xử lý qua error channel. Khi kiểm thử, hãy xác minh `MessageRejectedException` trong **cause chain** nếu framework/proxy có lớp bọc.

Nội dung và message text của exception có thể thay đổi theo phiên bản; nghiệp vụ không nên phân loại lỗi bằng cách so nguyên chuỗi thông báo. Dùng exception type/reason code do adapter chuyển đổi rõ ràng.

## 9. Đồng bộ: ai sẽ thấy rejection?

Với `DirectChannel`, các handler thường được dispatch **đồng bộ trên thread gửi**. Nếu Filter ném ngoại lệ, nó có thể lan ngược tới nơi gọi `send()` hoặc Gateway.

~~~mermaid
sequenceDiagram
    participant C as Caller / Gateway
    participant IN as DirectChannel
    participant F as MessageFilter
    participant OUT as Accepted consumer
    C->>IN: send(OrderRequest)
    IN->>F: handleMessage
    F->>F: selector trả false
    F-->>IN: MessageRejectedException
    IN-->>C: exception (có thể được bọc)
    Note over OUT: Không có message từ nhánh bị loại
~~~

Ví dụ một ứng dụng có boundary nhận command qua HTTP:

~~~text
HTTP request
    -> adapter / Gateway
    -> DirectChannel
    -> Filter(throwExceptionOnRejection=true)
    -> exception về boundary
    -> map thành response lỗi phù hợp
~~~

HTTP adapter/controller **không tự động biến mọi MessageRejectedException thành 400 Bad Request** theo một hợp đồng bất biến. Bạn phải cấu hình mapping exception → HTTP response phù hợp, ví dụ response `422 Unprocessable Entity` cho validation nghiệp vụ, `403 Forbidden` cho kiểm tra quyền ở tầng authorization, hoặc một mã khác theo API contract.

Một Filter rejection không nên tự được gán thành HTTP 500 nếu ứng dụng đã dự kiến điều kiện loại. Nhưng việc lựa chọn mã HTTP phụ thuộc ý nghĩa lỗi và hợp đồng public API, không phụ thuộc duy nhất class exception.

## 10. Bất đồng bộ: publisher có thể không thấy lỗi của Filter

Khi message đi qua `ExecutorChannel`, `QueueChannel` và polling consumer hoặc broker listener, exception có thể xảy ra **sau khi publisher đã hoàn tất gửi**. Vì thế:

~~~mermaid
flowchart LR
    P["Publisher"] --> CH["Queue / Executor"]
    CH --> F{"Filter"}
    F -->|"true"| OK["Business handler"]
    F -->|"false, throw"| E["Exception"]
    E --> EH["Error handler / error channel"]
    EH --> DEC{"Recovery policy"}
    DEC -->|"Non-retryable"| DLQ["Quarantine / reject status"]
    DEC -->|"Transient"| R["Bounded retry + backoff"]
~~~

Lời gọi `send()` thành công vào queue/executor **chỉ chứng minh công việc được nhận tại ranh giới đó**, không chứng minh Filter đã chấp nhận hoặc mọi consumer đã xử lý xong.

**Phụ thuộc ngữ cảnh:**

- Một poller có thể dùng error handler phù hợp hoặc phát `ErrorMessage` vào error channel nếu đã cấu hình.
- Một executor có thể báo lỗi qua error path của task bất đồng bộ.
- Một inbound broker adapter quyết định ack/nack/redelivery theo listener container, error handler và transaction boundary.
- Không phải mọi loại channel đều tự động đưa lỗi đến một channel tên `errorChannel` chỉ vì channel đó tồn tại.

Đối với input không hợp lệ **vĩnh viễn**, cần cơ chế phân loại “không retry” để tránh một poison message bị phát lại liên tục làm tắc consumer. Hãy nêu rõ chính sách tại **đúng adapter/poller** thay vì chỉ cấu hình Filter.

## 11. Rejection và transaction rollback

Một lý do hợp lệ để bật `throwExceptionOnRejection` là **ép một đơn vị xử lý giao dịch thất bại khi Filter từ chối**.

Ví dụ message được lấy từ transactional broker session hoặc poller có transaction:

~~~text
transaction begin
  → receive message
  → Filter selector = false
  → MessageRejectedException
transaction rollback (nếu exception thoát khỏi boundary và policy yêu cầu)
  → message có thể được redeliver
~~~

Tuy nhiên, **ném exception không tự động bảo đảm rollback**. Transaction chỉ rollback khi:

1. Bước Filter nằm **bên trong transaction boundary** liên quan.
2. Exception được truyền tới thành phần điều khiển transaction và được phân loại rollback.
3. Adapter hoặc message store hỗ trợ rollback/ack semantics tương ứng.
4. Không có advice/error handler trung gian bắt exception rồi coi là thành công trước boundary.

Một lần rollback có thể khiến message **được giao lại**, tùy nguồn và cấu hình. Nếu không có đường xử lý poison message, Filter sẽ tiếp tục từ chối cùng message vô hạn. Một chiến lược hợp lý là: giới hạn retry, đưa vào DLQ/quarantine hoặc chuyển thành lỗi nghiệp vụ có thể quan sát được.

**Không rollback chỉ để báo cho caller rằng dữ liệu sai** nếu sự cố là validation vĩnh viễn và workflow đã có cách từ chối rõ ràng. Transaction rollback hữu ích khi bảo toàn tính nguyên tử của đơn vị nhận/xử lý, nhưng không thay thế chính sách nghiệp vụ.

## 12. Filter kết hợp với Retry Advice: cẩn thận lặp vô hạn

Spring Integration có cơ chế advice xung quanh handler, ví dụ retry advice. Khi `throwExceptionOnRejection=true`, Filter chủ động ném exception; nếu advice được cấu hình retry **mọi exception**, message có thể bị đánh giá lại nhiều lần dù dữ liệu không thay đổi.

~~~mermaid
flowchart TD
    M["Message sai hợp đồng"] --> F["Filter: predicate false"]
    F --> E["MessageRejectedException"]
    E --> RETRY{"Retry advice có coi là retryable?"}
    RETRY -->|"Có, cấu hình rộng"| F
    RETRY -->|"Không"| REJECT["Reject / DLQ / error response"]
~~~

Thực hành nên làm:

- Xem `MessageRejectedException` do **validation vĩnh viễn** là **non-retryable**, trừ khi nghiệp vụ xác định có một điều kiện ngoài dự kiến sẽ thay đổi.
- Retry lỗi tạm thời, chẳng hạn mất kết nối dependency ở handler downstream, với backoff và giới hạn.
- Đưa metadata reason code/event ID vào error record có kiểm soát, không dùng raw exception message làm key nghiệp vụ.
- Nếu RetryAdvice nằm quanh Filter và discard flow, cần hiểu rõ khi nào discard và exception được thực hiện trong phạm vi advice.

**Đặc điểm quan trọng của Filter advice:** theo cấu hình mặc định, các thao tác discard và exception do rejection được thực hiện **bên trong advice chain**. Vì vậy nếu advice retry bắt lỗi rejection, **mỗi lần thử có thể lại chạy discard side effect**.

Spring Integration cung cấp tùy chọn `discardWithinAdvice(false)` để đưa thao tác discard/exception ra **sau** phạm vi advice. Đây không phải “tự động sửa mọi retry”; bạn vẫn cần thiết kế policy retry và hiểu hệ quả khi Filter không cho message đi tiếp.

## 13. Dùng `discardWithinAdvice` khi nào?

Đây là cấu hình minh họa cho Filter có cả discard và throw:

~~~java
.filter(OrderRequest.class, guard::accepted,
    spec -> spec
        .discardChannel("orders.rejected")
        .throwExceptionOnRejection(true)
        .discardWithinAdvice(false))
~~~

**Ý nghĩa:** `discardWithinAdvice(false)` thay đổi ranh giới của hành động discard và exception so với advice chain **được áp dụng cho chính Filter**. Nếu có retry advice, thao tác rejection nằm sau phần được advise, nên không diễn ra như một exception retryable bên trong lời gọi advised handler thông thường.

Đây là một quyết định kỹ thuật về **vị trí phát sinh lỗi**; không sử dụng nó để che giấu lỗi hoặc giả định transaction luôn commit/rollback theo một cách cố định. Test thực tế phải bao gồm:

1. Bao nhiêu lần selector được đánh giá?
2. Bao nhiêu lần discard handler nhận cùng event?
3. Khi nào caller/poller nhận exception?
4. Transaction có bao trùm discard handler không?
5. Error message có bao gồm rejected message và correlation phù hợp không?

**Không cấu hình cả hai một cách phản xạ.** Phần lớn use case nên chọn hoặc discard có chủ đích, hoặc exception có chủ đích. `discardWithinAdvice` dành cho trường hợp cụ thể có advice và yêu cầu kiểm soát ranh giới side effect.

## 14. Point-to-point channel có nhiều Selective Consumer

Một trường hợp nâng cao: nhiều Filter được đăng ký làm **competing selective consumers** trên cùng một point-to-point channel, chẳng hạn `DirectChannel`. Mỗi Filter chỉ chấp nhận một nhóm message.

~~~text
orders.in (point-to-point)
    ├── Filter A: chỉ nhận market=VN
    └── Filter B: chỉ nhận market=US
~~~

Nếu dispatcher chọn Filter A cho message US:

- Khi A **âm thầm drop**, dispatcher có thể coi lần dispatch đó là **đã được xử lý**, nên Filter B không có cơ hội nhận US.
- Khi A **ném `MessageRejectedException`**, dispatcher **có thể** thử subscriber khác theo chiến lược failover được cấu hình.

Tài liệu Spring Integration nêu đây là một lý do sử dụng `throwExceptionOnRejection=true` với nhiều Selective Consumer. Tuy nhiên, **không bảo đảm** rằng luôn thử được subscriber B: cần xét cách dispatcher chọn handler, cấu hình failover, số subscriber và những exception được coi là đủ điều kiện retry/failover.

Nếu thực tế cần chọn **một nhánh theo `market`**, một **Content-Based Router** với mapping `VN → orders.vn` và `US → orders.us` thường rõ ràng, dễ kiểm thử và dễ quan sát hơn việc dựa vào dispatcher failover để thử nhiều Filter.

**Phân biệt:** nhiều subscriber của `PublishSubscribeChannel` là mô hình fan-out, còn nhiều subscriber của `DirectChannel` là point-to-point; không mang giả định “Filter nào cũng được gọi” từ pub/sub sang point-to-point.

## 15. Xử lý input thiếu/sai kiểu trước Filter

Nếu message đến từ HTTP, Kafka hoặc AMQP, không thể giả định mọi payload đã là `OrderRequest` hợp lệ.

Ví dụ lỗi thường gặp:

| Đầu vào | Có chắc predicate đã chạy? | Cách xử lý |
|---|---|---|
| JSON sai cú pháp | Không, lỗi có thể ở adapter/deserializer | Ingress decode error |
| Payload là `String` thay vì `OrderRequest` | Không chắc, có thể lỗi type conversion | Type gate/reject schema |
| `orderId=null` | Có nếu DTO vẫn parse được | Predicate false |
| `quantity=null` | Có nếu trường nullable | Predicate false |
| `quantity=-3` | Có | Predicate false |
| Bản tin hợp lệ nhưng thiếu quyền truy cập | Không nên chỉ dựa vào Filter thường | Authorization boundary |
| Broker redelivery cùng event | Predicate có thể chạy nhiều lần | Idempotency + recovery policy |

**Thiết kế khuyến nghị:** decode → schema/type validation → Filter nghiệp vụ → Transformer/Router → handler downstream. Nếu muốn áp dụng exception policy riêng cho decode và validation, hãy phân loại lỗi tại từng bước, không mong mọi lỗi đầu vào đều biến thành `MessageRejectedException`.

Một predicate **không nên truy vấn database hoặc gọi HTTP để kiểm tra mọi message** nếu có thể giữ thuần Java và nhanh. Nếu cần dữ liệu ngoài, tách thành service/handler độc lập có timeout và retry rõ ràng; Filter chỉ đọc kết quả đã được xác định.

## 16. Gateway request–reply và kết quả từ chối

Xét một Gateway gửi đơn tới Filter rồi đợi kết quả:

~~~java
@MessagingGateway(defaultRequestChannel = "orders.in")
public interface OrderGateway {
    OrderReceipt submit(OrderRequest order);
}
~~~

Nếu Filter **âm thầm drop**, Gateway không tự nhận `OrderReceipt(REJECTED)`. Tùy timeout và cấu hình, caller có thể chờ hoặc nhận kết quả null/error khi không có reply. Nếu Filter **throw**, caller có thể nhận messaging exception trực tiếp hoặc qua wrapper.

Nếu API yêu cầu **trả kết quả nghiệp vụ có cấu trúc**, có hai hướng:

- **Exception boundary:** bật throw, map `MessageRejectedException` thành API error, không trực tiếp lộ stack trace/message nội bộ cho client.
- **Business outcome:** trước khi reply, phân loại `ACCEPTED/REJECTED` thành đối tượng `OrderReceipt` riêng; chỉ dùng Filter nếu việc drop một nhánh không làm mất phản hồi mong đợi.

Ví dụ một result kiểu nghiệp vụ:

~~~java
public record OrderReceipt(
    String orderId,
    String status,        // ACCEPTED / REJECTED
    String reasonCode
) {}
~~~

Nếu business yêu cầu receipt cho **mọi input hợp lệ về giao thức**, dùng một classifier hoặc Router phát hai loại reply có thể tự nhiên hơn so với Filter ném exception. Không thiết kế API chỉ dựa vào “HTTP request không timeout” để nhận biết Filter chấp nhận message.

## 17. Error channel và ErrorMessage nên chứa gì?

Khi Filter ném exception trong một ngữ cảnh có error handler, framework có thể tạo `ErrorMessage` chứa exception gốc. Đường xử lý lỗi nên bảo toàn thông tin để chẩn đoán nhưng không làm lộ dữ liệu:

~~~text
ErrorMessage
    ├─ exception type: MessageRejectedException
    ├─ failedMessage / eventId (nếu được giữ)
    ├─ input channel, endpoint name
    ├─ trace / correlation context
    └─ reason code do ứng dụng phân loại
~~~

Có thể có khác biệt về failed message/cause chain do wrapper và adapter; test không nên dựa vào một cấu trúc exception bất biến cho mọi nguồn.

**Không retry tự động** mọi `ErrorMessage`. Nhóm rejection do validation vĩnh viễn khác với lỗi mạng tạm thời. Với AMQP/Kafka, quyết định nack, commit offset, requeue, DLQ hoặc skip phụ thuộc adapter/container và policy đã cấu hình; việc ném exception tại Filter chỉ là **một tín hiệu**, không tự xác định mọi semantics delivery.

## 18. Correlation, Splitter và Aggregator khi Filter từ chối

Giả sử một order được **Splitter** chia thành ba dòng sản phẩm, rồi Filter loại một dòng không hợp lệ trước **Aggregator**:

~~~mermaid
flowchart LR
    ORD["Order O-101"] --> SPLIT["Splitter"]
    SPLIT --> L1["Line 1"]
    SPLIT --> L2["Line 2: invalid"]
    SPLIT --> L3["Line 3"]
    L1 --> FIL{"Filter"}
    L2 --> FIL
    L3 --> FIL
    FIL -->|"Accepted"| AG["Aggregator"]
    FIL -->|"Rejected + throw"| ER["Error handling"]
    AG --> RES["OrderResult?"]
~~~

Nếu sequence size ban đầu là 3 nhưng một dòng không tới Aggregator, group có thể **chờ thiếu thành viên**. Khi Filter ném exception:

- Trong flow đồng bộ, exception có thể chặn quá trình phát các dòng tiếp theo.
- Trong flow bất đồng bộ, các dòng khác có thể đang được xử lý và Aggregator nhận một nhóm không đầy đủ.
- Nếu toàn bộ order phải thất bại khi bất kỳ dòng nào invalid, dùng một quy tắc fail-fast trước khi Splitter hoặc một coordinator xử lý kết quả lỗi.
- Nếu cho phép kết quả từng dòng, chuyển rejection thành **failure result** có correlation ID để Aggregator có thể tổng hợp cả accepted và rejected.

**Không tự sửa `sequenceSize` bằng tay** chỉ để tránh timeout nếu nghiệp vụ chưa xác định cách release. Cần thiết kế release strategy, group timeout, expired-message handling và chống trùng.

Hãy giữ `correlationId`, event ID và số thứ tự qua các Transformer/adapter có chủ đích; không lấy message ID mới được tạo khi redelivery làm khóa nghiệp vụ duy nhất.

## 19. Kiểm thử trực tiếp việc ném exception

Với integration test chạy trong Spring context có `RejectingOrderFlow` và consumer test cho `orders.accepted`, có thể kiểm tra message bị từ chối như sau:

~~~java
@SpringJUnitConfig(classes = RejectingOrderFlow.class)
class FilterRejectionTest {

    @Autowired
    ApplicationContext context;

    @Test
    void rejectsInvalidQuantityWithMessagingException() {
        MessageChannel input = context.getBean(
            "orders.in", MessageChannel.class);

        Message<OrderRequest> invalid = MessageBuilder
            .withPayload(new OrderRequest("E-1", "O-1", -1))
            .build();

        assertThrows(MessagingException.class,
            () -> input.send(invalid));
    }
}
~~~

Lưu ý lớp test minh họa **chỉ kiểm tra exception thuộc họ MessagingException** để chịu được một số lớp bọc; nên bổ sung assertion tìm `MessageRejectedException` trong cause chain ở phiên bản framework của dự án. Với luồng đồng bộ, `orders.in` cần được kết nối vào handler Filter qua cấu hình. Để test happy path, cung cấp consumer cho `orders.accepted` bằng `QueueChannel` trong **test-only configuration**, tránh gửi message accepted vào output channel không có subscriber.

Test giá trị:

| Case | Input | Kết quả mong đợi |
|---|---|---|
| Hợp lệ | `quantity=2`, ID đầy đủ | Accepted channel nhận message |
| Quantity âm | `quantity=-1` | `MessageRejectedException` hoặc wrapper chứa nó |
| Quantity null | `quantity=null` | Rejection, không `NullPointerException` |
| Thiếu orderId | `orderId=null` | Rejection |
| Thiếu eventId | `eventId=""` | Rejection |
| Không bật throw | Predicate false | Không exception; default/discard theo config |
| Chỉ discard | Predicate false | Rejected channel nhận, accepted không nhận |
| Cả discard + throw | Predicate false | Discard nhận và caller thấy exception |
| Predicate tự ném exception | Bug/type error | Không nhầm với rejection hợp lệ |
| Consumer downstream lỗi | Predicate true, handler lỗi | Phân loại là downstream error |

Tránh viết test chỉ assert `send() == true`. Một Filter mặc định có thể loại message mà không báo exception, nên thông số này **không chứng minh** bước nghiệp vụ đã được xử lý.

## 20. Kiểm thử retry, transaction và error path

Các integration test cần mô phỏng đường đi phù hợp với production:

1. **Synchronous DirectChannel:** kiểm tra exception lan về producer/Gateway và accepted handler không bị gọi.
2. **Async executor/queue:** kiểm tra `ErrorMessage` hoặc error handler nhận rejection, không đòi publisher trực tiếp thấy exception.
3. **Discard + throw:** đếm số lần discard consumer chạy; nếu có retry advice, xác minh hành vi `discardWithinAdvice`.
4. **Transaction:** dùng một resource có transaction thật để kiểm chứng rollback; không tuyên bố rollback chỉ vì test thấy exception.
5. **Broker redelivery:** xác minh policy non-retryable cho validation, DLQ/quarantine và không gây retry vô hạn.
6. **Idempotency:** cùng `eventId` đến nhiều lần chỉ ghi business result/rejection record theo chính sách.
7. **Splitter/Aggregator:** một phần tử bị reject không để nhóm chờ vô hạn mà không có timeout hoặc failure result.

Đối với thử nghiệm concurrency, dùng latch, test channel và timeout hữu hạn. Không phụ thuộc vào `Thread.sleep` cố định hoặc thứ tự thread ngẫu nhiên.

## 21. Quan sát và chẩn đoán rejection

Một đội vận hành cần phân biệt rõ Filter từ chối có chủ đích và exception do lỗi:

| Tín hiệu nên có | Giải thích |
|---|---|
| `filter.accepted.count` | Số message đi qua predicate thành công |
| `filter.rejected.count` | Số message bị Filter loại |
| `filter.rejection.exception.count` | Số trường hợp ném `MessageRejectedException` |
| `filter.discard.count` | Số message gửi sang discard channel |
| `filter.predicate.error.count` | Số lỗi khi đánh giá selector |
| `filter.downstream.error.count` | Lỗi sau khi Filter đã chấp nhận |
| `consumer.retry.count` | Retry theo loại lỗi |
| `dlq.count` và backlog | Message cần điều tra/khắc phục |

Đây là **tên metric đề xuất**, không khẳng định là các meter mặc định của Spring Integration. Nếu dùng Micrometer/observation, bổ sung nhãn endpoint và reason code có tập giá trị hữu hạn; tránh dùng `orderId`/`eventId` làm metric tag vì gây high cardinality. ID cụ thể nên nằm trong tracing/log có kiểm soát.

Khi một message “mất” sau Filter, kiểm tra theo thứ tự:

~~~text
Ingress decode/type
   → Filter selector result
   → throwExceptionOnRejection?
   → discardChannel?
   → channel/caller error handling
   → transaction/retry decision
   → DLQ/quarantine hoặc business result
~~~

Tại mỗi điểm, xác định thời điểm xảy ra và chủ sở hữu quyết định. Một producer nhìn thấy lỗi không chứng minh message chưa tạo side effect; một producer thấy `send()` thành công không chứng minh Filter đã chấp nhận.

## 22. Khi nào nên bật và khi nào không?

| Mục tiêu | Khuyến nghị | Lý do |
|---|---|---|
| Request–reply cần lỗi rõ khi dữ liệu không hợp lệ | Cân nhắc **throw** và map thành API error | Caller nhận tín hiệu lỗi thay vì chờ |
| Muốn ghi nhận rejected message để điều tra | **discard channel** có owner | Không nhất thiết làm upstream rollback |
| Muốn bỏ telemetry không phù hợp | Không throw; có thể discard/null channel | Drop là hành vi dự kiến |
| Transaction phải rollback khi selector từ chối | **throw**, kèm rollback policy | Exception cho transaction boundary thấy lỗi |
| Poison message trên broker | Không retry vô hạn; kết hợp non-retryable recovery | Validation thường không tự phục hồi |
| Nhiều Selective Consumer trên point-to-point channel | Cân nhắc throw + dispatcher failover được kiểm thử | Có thể cho handler khác cơ hội nhận |
| Đơn cần kết quả `ACCEPTED/REJECTED` trong mọi trường hợp | Classifier/Router tạo business result | Boolean Filter + drop có thể mất reply |
| Một nhánh của Aggregator bị loại | Failure result hoặc group failure policy | Không để chờ thiếu thành viên |

**Nguyên tắc:** rejection **có dự kiến** không nhất thiết phải là exception. Chỉ bật `throwExceptionOnRejection` khi có thành phần ở phía trên **cần nhận tín hiệu lỗi**, và bạn biết tín hiệu đó sẽ kích hoạt hành vi gì.

## 23. Những sai lầm phổ biến

**“Predicate trả false nghĩa là exception.”** Sai. Mặc định Filter có thể drop hoặc discard; chỉ khi bật cờ mới phát sinh `MessageRejectedException` cho rejection.

**“Có discard channel thì sẽ không throw.”** Sai. Nếu cấu hình cả hai, message có thể được discard **và** exception vẫn được ném sau đó.

**“Bật throw tự động gửi message vào errorChannel.”** Sai. Đường lỗi phụ thuộc kiểu channel, caller, adapter, poller và error handler.

**“Bật throw tự động rollback transaction.”** Sai. Exception phải xảy ra và truyền qua transaction boundary có chính sách rollback phù hợp.

**“Mọi exception đều nên retry.”** Sai. Predicate false do dữ liệu không hợp lệ thường là lỗi vĩnh viễn; retry có thể gây poison message.

**“Filter false và bug trong predicate là như nhau.”** Sai. Rejection có chủ đích khác lỗi đánh giá/thiếu schema.

**“Gateway nhận được `send()==true` tức đơn được chấp nhận.”** Sai. Sự chấp nhận ở ranh giới channel khác với chấp nhận nghiệp vụ.

**“Discard + throw chắc chắn không gây side effect trùng.”** Sai. Nếu discard đã ghi ngoài transaction trước khi exception làm retry, bản ghi có thể bị nhân đôi.

**“Filter là cách tốt nhất để trả nhiều reason code.”** Không nhất thiết. Dùng classifier/Router hoặc result type khi cần lý do từ chối có cấu trúc.

## 24. Bài thực hành

Hãy xây dựng flow **OrderAdmission** gồm:

1. **Gateway/producer** gửi `OrderRequest(eventId, orderId, quantity)`.
2. **Filter** dùng `OrderGuard.accepted()` để xác minh trường bắt buộc.
3. **Case A:** dùng Filter mặc định, thử một đơn bị từ chối, quan sát có reply hay không.
4. **Case B:** dùng `discardChannel("orders.rejected")` với consumer đếm rejection.
5. **Case C:** bật `throwExceptionOnRejection(true)` và xác minh exception.
6. **Case D:** bật cả discard và throw để quan sát discard chạy trước exception; thử lại khi có retry advice.
7. **Error handling:** tách `MessageRejectedException` khỏi lỗi timeout từ handler downstream; cài chính sách non-retryable cho dữ liệu sai.
8. **Transaction:** thử một poller/adapter với transaction; xác định lúc nào exception khiến rollback và message được giao lại.
9. **Splitter/Aggregator:** một dòng hàng bị reject; thiết kế failure result hoặc group timeout.
10. **Observability:** đo accepted, rejected, discard, exception, retry và DLQ; nối bằng event ID/correlation.

**Tiêu chí hoàn thành:** có bảng chứng minh ba chế độ default/discard/throw khác nhau; kiểm thử cả case false và selector exception; xác định rõ thread/boundary nhận exception, chính sách retry, idempotency và trạng thái cuối mà caller có thể quan sát.

## 25. Ghi nhớ

**`throwExceptionOnRejection=true`** biến việc **Filter selector trả `false`** thành **`MessageRejectedException`**. Nó cho phép upstream biết message đã bị từ chối, có thể ảnh hưởng dispatch failover, rollback hoặc error handling **nếu các ranh giới đó được cấu hình phù hợp**. Cờ này **không** tự cấp HTTP error mapping, error channel, retry policy hay transaction rollback.

Hãy phân biệt **silent drop**, **discard channel** và **exception**, đặc biệt vì discard và throw **có thể cùng xảy ra**. Chọn một hợp đồng nhất quán với Gateway, broker, Filter/Router/Transformer, Splitter/Aggregator, retry, error channel và correlation để message lỗi được xử lý có chủ đích, không bị retry vô hạn hoặc làm mất kết quả nghiệp vụ.

### Tài liệu tham khảo

- Spring Integration Reference, **Filter**: https://docs.spring.io/spring-integration/reference/filter.html
- Spring Integration API, **MessageFilter**: https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/filter/MessageFilter.html
- Spring Integration API, **FilterEndpointSpec**: https://docs.spring.io/spring-integration/docs/current/api/org/springframework/integration/dsl/FilterEndpointSpec.html
- Spring Integration Reference, **Advising Filters**: https://docs.spring.io/spring-integration/reference/handler-advice/advising-filters.html
