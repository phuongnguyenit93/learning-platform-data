# Câu hỏi phỏng vấn thường gặp về Spring Framework Application Events

## 1. Mục tiêu ôn tập và cách trả lời phỏng vấn

Spring Framework Application Events là một cơ chế publish–subscribe **nội bộ trong application context**, thường được dùng để tách một nghiệp vụ phát sự kiện khỏi các thành phần phản ứng với sự kiện đó. Khi phỏng vấn, người hỏi không chỉ muốn nghe tên annotation `@EventListener`, mà thường đánh giá khả năng giải thích **đường thực thi**, **transaction**, **async**, **lỗi**, **tính nhất quán** và **lựa chọn kiến trúc**.

Bài học này tổng hợp câu hỏi từ cơ bản đến nâng cao, kèm câu trả lời có lý do, ví dụ và bẫy thường gặp. Cách trả lời tốt nhất cho câu hỏi thiết kế thường theo bốn phần:

1. **Nêu cơ chế mặc định:** cùng JVM/context, listener thường đồng bộ.
2. **Chỉ ra giới hạn:** không tự có queue bền vững, retry, transaction giữa các service hoặc exactly-once delivery.
3. **Chọn công cụ phù hợp:** `@EventListener`, `@TransactionalEventListener`, `@Async`, outbox, broker hoặc application service.
4. **Nêu cách kiểm chứng:** integration test, logging/tracing, transaction boundary, kiểm thử retry/idempotency và đo hiệu năng.

Đừng lặp lại khẩu quyết “event luôn bất đồng bộ” hoặc “publish thành công là xử lý xong”. Cả hai đều **sai trong mô hình mặc định**.

### Bản đồ kiến thức nhanh

| Nhóm câu hỏi | Khả năng cần thể hiện |
| --- | --- |
| Cơ bản | Publisher, listener, payload object, `ApplicationEvent`, `ApplicationContext`. |
| Cơ chế | Multicaster, matching theo type, thứ tự, condition, return-value publication. |
| Async | `@Async`, executor, exception, thread context, thứ tự và shutdown. |
| Transaction | `@TransactionalEventListener`, các phase, rollback, no-transaction. |
| Spring Boot | Các sự kiện lifecycle, đăng ký listener từ giai đoạn sớm. |
| Thiết kế | Immutability, metadata, versioning, idempotency, outbox/broker. |
| Vận hành | Security, observability, testing, performance, troubleshooting. |

## 2. Câu hỏi cơ bản: khái niệm và API

### Câu 1. Spring Application Events là gì?

**Trả lời:** Cơ chế giao tiếp theo sự kiện trong Spring container: một component gọi `ApplicationEventPublisher.publishEvent(...)` để báo một sự thật hoặc trạng thái; những listener phù hợp được framework gọi mà publisher không cần biết trực tiếp từng listener.

Ví dụ: khi đặt đơn hoàn tất, `OrderService` phát `OrderPlaced`; `AuditListener` ghi audit, `StatisticsListener` cập nhật số liệu. Sự phụ thuộc trực tiếp từ OrderService tới hai listener được thay bằng hợp đồng event.

**Cần nói thêm:** đây là **in-process event dispatch**, không đồng nghĩa Kafka/RabbitMQ, không tự bảo đảm event còn tồn tại sau khi tiến trình chết.

### Câu 2. Có những thành phần nào trong đường đi của một event?

**Trả lời ngắn:** `ApplicationEventPublisher` (API công bố), `ApplicationContext` (đường phát thông thường), `ApplicationEventMulticaster` (quản lý và phân phối listener), `ApplicationListener` hoặc method `@EventListener` (người xử lý).

~~~text
Service -> ApplicationEventPublisher.publishEvent(event)
                   |
                   v
          ApplicationContext
                   |
                   v
       ApplicationEventMulticaster
                   |
            +------+------+
            |             |
      @EventListener A  ApplicationListener B
~~~

`SimpleApplicationEventMulticaster` là triển khai phổ biến. Ứng dụng có thể thay/customize bean tên `applicationEventMulticaster` để điều chỉnh executor và xử lý exception.

### Câu 3. Khác nhau giữa ApplicationEvent và payload object?

**Trả lời:** Lớp sự kiện kiểu cũ có thể kế thừa `ApplicationEvent`; từ Spring 4.2, ta cũng có thể publish **đối tượng Java bất kỳ**. Nếu payload không kế thừa `ApplicationEvent`, Spring bọc nó thành `PayloadApplicationEvent` khi đưa qua cơ chế multicast.

~~~java
public record OrderPlaced(String orderId) {}

publisher.publishEvent(new OrderPlaced("ORD-1"));
~~~

*Snippet minh họa trong Spring bean có publisher; cần định nghĩa/import `ApplicationEventPublisher`.*

Không cần tự viết `extends ApplicationEvent` chỉ vì muốn một domain event. Java record phù hợp cho payload bất biến nông, nhưng **record không tự bất biến sâu** nếu có field chứa list/map mutable.

### Câu 4. ApplicationEventPublisher có phải là message broker không?

**Không.** Nó là API phát event trong ứng dụng Spring. Không có mặc định các chức năng lưu message bền vững, acknowledgement, consumer offsets, dead-letter queue, retry trên broker hay giao giữa hai JVM.

Nếu yêu cầu giao qua nhiều service hoặc phải xử lý sau khi ứng dụng restart, cần thiết kế broker/event store/outbox thích hợp. Có thể dùng Spring Application Events để tách các module trong một service **và** dùng broker cho ranh giới liên dịch vụ; không cần coi chúng là lựa chọn loại trừ nhau.

### Câu 5. ApplicationListener khác @EventListener như thế nào?

| `ApplicationListener<E>` | `@EventListener` |
| --- | --- |
| Triển khai một interface, thường viết `onApplicationEvent(E)`. | Annotation trên phương thức của Spring bean. |
| Rõ ràng kiểu listener ở interface, thuận tiện cho startup/registration trong một số use case. | Gọn, có `condition` SpEL, có thể khai báo nhiều event types. |
| Có thể đăng ký object listener theo API. | Được Spring phát hiện trong quá trình xử lý bean. |
| Có thể kết hợp `GenericApplicationListener` để lọc type/source. | Có thể return event để publish tiếp khi chạy đồng bộ. |

**Chọn theo bài toán:** trong code nghiệp vụ thông thường, `@EventListener` dễ đọc; khi cần listener ở giai đoạn chưa có bean, điều khiển registration rõ ràng hoặc type/source matching đặc biệt, `ApplicationListener` phù hợp hơn.

### Câu 6. @EventListener có bắt buộc method trả void không?

**Không.** Method có thể trả một object; Spring sẽ publish nó thành event tiếp theo. Nếu method trả `Collection` hoặc array, **từng phần tử** được publish như các event độc lập.

~~~java
@EventListener
public List<Object> afterOrderPlaced(OrderPlaced e) {
    return List.of(
        new AuditRequested(e.orderId()),
        new MetricsRequested(e.orderId()));
}
~~~

*Snippet minh họa trong bean; các record `OrderPlaced`, `AuditRequested`, `MetricsRequested` phải được định nghĩa. Tính năng return-value publication **không hỗ trợ cho asynchronous listener**.*

Nếu muốn một event duy nhất chứa một danh sách, cần wrapper như `BatchReady(List<String> ids)` thay vì return thẳng `List<String>`.

### Câu 7. Một listener có thể nhận nhiều loại event không?

Có. Có thể dùng `@EventListener({ContextStartedEvent.class, ContextRefreshedEvent.class})` khi method không cần một tham số cố định cho từng type, hoặc tạo các method typed riêng cho từng loại. Nếu dùng một method với nhiều loại không liên hệ, cẩn thận signature và đọc metadata phù hợp.

Đối với domain events, tách method `onOrderPlaced(OrderPlaced)` và `onPaymentCaptured(PaymentCaptured)` thường rõ hơn một method tổng quát phải tự `instanceof` nhiều kiểu.

### Câu 8. Listener có cần là Spring bean không?

Với `@EventListener`, **có**: method phải nằm trong bean được container quản lý và được event listener processor phát hiện. Tự tạo object bằng `new MyListener()` bên ngoài context sẽ không được đăng ký tự động.

Với `ApplicationListener`, có thể đăng ký listener object bằng `SpringApplication.addListeners(...)` (trong Boot) hoặc API của multicaster theo vòng đời phù hợp. Listener quá sớm, listener thuộc context khác, hoặc bean bị profile loại bỏ là nguyên nhân phổ biến khiến event không được nhận.

### Câu 9. Có thể publish event từ bất kỳ service nào không?

Có thể inject `ApplicationEventPublisher` vào Spring-managed component và gọi `publishEvent(event)`, miễn code có publisher/context phù hợp.

~~~java
@Service
class OrderService {
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    void place(String orderId) {
        // Thực hiện thao tác nghiệp vụ...
        publisher.publishEvent(new OrderPlaced(orderId));
    }
}
~~~

*Đoạn tích hợp minh họa; `OrderPlaced` là record nghiệp vụ. Các import cần thiết gồm `@Service` và `ApplicationEventPublisher`.*

Nên phát event mô tả **sự thật nghiệp vụ có ý nghĩa**, không dùng event để thay tất cả lời gọi method hoặc che một workflow bắt buộc đồng bộ.

### Câu 10. Vì sao nên ưu tiên event bất biến?

Listener có thể chạy vào thời điểm khác, ở thread khác hoặc đọc event khi producer đã thay đổi object gốc. Payload bất biến giúp truyền dữ liệu ổn định, giảm race condition và dễ kiểm thử. Tránh mang cả JPA entity/lazy proxy làm event public contract; nên dùng ID và snapshot tối thiểu.

Nếu chứa collection trong record, có thể dùng `List.copyOf(...)` trong canonical constructor để sao chép phòng vệ. Dữ liệu nhạy cảm cần được giới hạn theo người nhận, không phải “publish cả entity vì tiện”.

## 3. Câu hỏi về cơ chế dispatch, filter và thứ tự

### Câu 11. Spring tìm listener phù hợp bằng cách nào?

Multicaster chọn listener theo event type; với generic events có thể dùng `ResolvableType`. Các loại listener chuyên biệt như `GenericApplicationListener` có thể xem cả `supportsEventType(...)` và `supportsSourceType(...)`. Spring cache kết quả tiền lọc ứng viên cho các event/source types thích hợp để giảm lặp lại matching.

**Cache matching không phải cache kết quả xử lý.** Cùng event type vẫn được xử lý ở mỗi lần publish; `@EventListener(condition=...)` vẫn đánh giá theo dữ liệu từng event.

### Câu 12. @EventListener(condition) là gì?

`condition` là SpEL expression để quyết định method có được gọi cho **event cụ thể** không:

~~~java
@EventListener(condition = "#p0.totalMinorUnits() >= 10000")
public void onLargeOrder(OrderPlaced event) { }
~~~

*Snippet minh họa; `OrderPlaced` cần có method `totalMinorUnits()`.*

`#p0` hoặc `#a0` là tham số đầu tiên; `#root.args[0]` là argument của listener. Tên `#event` chỉ sử dụng an toàn khi tên tham số tồn tại qua Java compiler metadata (`-parameters`). `#root.event` là **ApplicationEvent thực tế**; khi publish arbitrary payload, nó thường là `PayloadApplicationEvent`, không phải payload trực tiếp.

### Câu 13. Condition luôn false thì debug theo thứ tự nào?

1. Đảm bảo publisher phát **đúng object/type/value**, không chỉ dựa vào trạng thái database lúc debug.
2. Thêm listener probe không condition trong cùng context để xác minh event đến.
3. Thử `condition="true"` để phân biệt routing/registration với logic filter.
4. Thay tên tham số bằng `#p0`; kiểm tra compiler `-parameters` nếu muốn dùng `#namedParameter`.
5. Kiểm tra case của String, enum, null, đơn vị tiền và dấu `>` so với `>=`.
6. Phân biệt Boolean false với `SpelEvaluationException`: lỗi property/method có thể ném exception, không phải im lặng false.
7. Nếu là `@TransactionalEventListener`, kiểm tra có transaction và phase phù hợp không.

Điểm phỏng vấn: hãy nêu **cách chứng minh nguyên nhân**, không sửa ngẫu nhiên expression.

### Câu 14. @Order có bảo đảm thứ tự xử lý không?

`@Order` giúp xếp thứ tự các listener phù hợp trong đường dispatch **đồng bộ**. Giá trị nhỏ hơn thường có mức ưu tiên cao hơn. Không suy diễn rằng event đi qua executor bất đồng bộ sẽ hoàn tất theo đúng thứ tự; không thể dùng `@Order` làm giao thức ordering bền vững giữa service.

Nếu nghiệp vụ phải bảo đảm bước A thành công rồi mới chạy B, thường application service hoặc workflow orchestration rõ hơn một chuỗi listener phụ thuộc ngầm vào order.

### Câu 15. Nếu một listener ném exception, các listener khác có chạy tiếp không?

Trong `SimpleApplicationEventMulticaster` mặc định đồng bộ **không có ErrorHandler tùy biến**, exception từ listener có thể làm multicast dừng và truyền ngược tới publisher, khiến listener sau chưa được chạy. Khi cấu hình `setErrorHandler(...)` hoặc executor, behavior có thể khác.

Vì vậy không nên khẳng định “một listener lỗi không ảnh hưởng ai”. Với side effect độc lập, hãy thiết kế xử lý lỗi/queue riêng; với transaction đồng bộ, đánh giá rollback và các side effect đã xảy ra.

### Câu 16. @EventListener có tự chạy trong thread riêng không?

**Không.** Theo mặc định `SimpleApplicationEventMulticaster` gọi listener trên thread phát event. Một listener chạy 300 ms có thể làm lời gọi `publishEvent(...)` bị chặn tương ứng nếu chạy đồng bộ.

Muốn async, dùng `@Async` với `@EnableAsync` và executor thích hợp, hoặc cung cấp `TaskExecutor` cho bean `applicationEventMulticaster`. Hai phương án có điểm cấu hình, error handling và phạm vi tác động khác nhau.

### Câu 17. @Async trên listener khác async multicaster thế nào?

- `@Async`: áp dụng ở phương thức listener khi đi qua Spring proxy, thường chọn executor theo tên/qualifier hoặc executor mặc định.
- Async multicaster: cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)`, ảnh hưởng đến các listener mà multicaster có thể chạy bất đồng bộ.
- Từ Spring Framework 6.1, listener báo `supportsAsyncExecution() == false` vẫn cần được gọi ở publishing thread ở mức multicaster, ví dụ listener có ràng buộc transaction.
- Dùng cả hai có thể tạo **nhiều thread hop** và làm tracing/transaction/order khó suy luận hơn.

Trong mọi trường hợp, không mặc định có durable queue hay retry.

### Câu 18. Vì sao @Async listener không nên return event?

Spring tài liệu hóa rằng **asynchronous event listener không hỗ trợ publish event thông qua return value**. Nếu muốn phát event sau khi xử lý async thành công, cần inject `ApplicationEventPublisher` và gọi `publishEvent(...)` tường minh tại thời điểm thích hợp.

~~~java
@Async
@EventListener
public void handle(PaymentCaptured event) {
    // Xử lý...
    publisher.publishEvent(new ReceiptPrepared(event.paymentId()));
}
~~~

*Snippet tích hợp cần bean publisher, `@EnableAsync`/executor và các event types tương ứng.*

Đừng trả `List<Object>` từ method `@Async` rồi kỳ vọng Spring tự phát từng phần tử; đó là một giả định sai về cơ chế xử lý kết quả async.

### Câu 19. ThreadLocal/SecurityContext/MDC có theo listener async không?

**Không tự động.** Khi listener chạy ở thread pool, `ThreadLocal`/MDC/Spring Security `SecurityContextHolder` của publisher thường không được kế thừa như trong cùng thread. Dùng propagation phù hợp, chẳng hạn `ContextPropagatingTaskDecorator` (Micrometer) cho logging/observation và `DelegatingSecurityContextAsyncTaskExecutor` khi thật sự cần truyền security context.

Không sao chép JDBC transaction/EntityManager sang worker bằng `ThreadLocal`. Thread-bound transaction có vòng đời độc lập; nếu listener async cần DB transaction, hãy chủ động mở transaction mới đúng boundary.

### Câu 20. Publish event có đồng nghĩa tất cả listener đã hoàn tất không?

Chỉ có thể suy luận theo cấu hình thực tế. Với multicast mặc định **đồng bộ** và mọi listener bình thường hoàn tất, `publishEvent(...)` thường trở lại sau khi các listener đó đã chạy. Với `@Async` hoặc async multicaster, publisher có thể trả ngay khi listener mới được lên lịch, không đợi side effect hoàn tất.

Thậm chí với đồng bộ, “listener đã chạy” không nghĩa email gửi thành công vĩnh viễn, DB transaction đã commit, hay event được lưu bền vững.

## 4. Câu hỏi về transaction và dữ liệu nhất quán

### Câu 21. @EventListener khác @TransactionalEventListener thế nào?

`@EventListener` thông thường nhận event tại thời điểm phát trong context và không tự chờ commit của transaction hiện hành.

`@TransactionalEventListener` đăng ký xử lý gắn với **một phase của transaction**; mặc định là `TransactionPhase.AFTER_COMMIT`. Nó phù hợp khi chỉ muốn phản ứng sau commit thành công, tránh dựa vào dữ liệu sẽ bị rollback.

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Xử lý sau khi transaction phát event đã commit.
}
~~~

*Snippet tích hợp cần transaction manager, transaction thật và import `@TransactionalEventListener`/`TransactionPhase`.*

### Câu 22. Những transaction phase nào được hỗ trợ?

| Phase | Khi nào listener được kích hoạt? | Tình huống |
| --- | --- | --- |
| `BEFORE_COMMIT` | Trước khi commit transaction. | Kiểm tra/tổng hợp bổ sung trong workflow commit khi thật sự cần. |
| `AFTER_COMMIT` (mặc định) | Khi transaction hoàn tất bằng commit thành công. | Side effect chỉ nên xảy ra nếu business fact đã commit. |
| `AFTER_ROLLBACK` | Khi transaction kết thúc bằng rollback. | Thu thập trạng thái lỗi/compensation được thiết kế rõ. |
| `AFTER_COMPLETION` | Sau khi transaction hoàn thành, dù commit hoặc rollback. | Cleanup/telemetry. |

Nếu không có transaction phù hợp, `@TransactionalEventListener` mặc định **không chạy**, trừ khi chọn `fallbackExecution=true`. Không nên bật fallback chỉ để “chữa listener im lặng” mà không xem lại nghiệp vụ.

### Câu 23. Nếu publish trong @Transactional rồi rollback, listener nào đã chạy?

Giả sử `service.placeOrder()` đang trong transaction:

- Listener `@EventListener` **đồng bộ** có thể đã chạy ngay lúc publish, trước khi có kết quả commit/rollback.
- Listener `@TransactionalEventListener(AFTER_COMMIT)` không chạy nếu transaction rollback.
- Listener `AFTER_ROLLBACK` sẽ được gọi theo phase rollback.
- Listener có `@Async` hoặc executor riêng không tự được phối hợp với DB transaction gốc.

Không nên phát email/HTTP không thể rollback ngay trong listener đồng bộ nếu nghiệp vụ yêu cầu chỉ sau commit.

### Câu 24. Có thể ghi DB trong AFTER_COMMIT callback không?

Được, nhưng phải hiểu ranh giới: transaction gốc đã commit; tài nguyên giao dịch có thể vẫn đang bound trong thời điểm callback, nhưng các ghi mới không được hiểu là tự có một lần commit tiếp theo trên transaction cũ. Nếu cần DB update riêng, nên mở **transaction mới**, ví dụ qua một service có `@Transactional(propagation = Propagation.REQUIRES_NEW)` được gọi qua proxy đúng.

Đừng tạo một method `private` hoặc self-invocation rồi kỳ vọng annotation transaction tự hoạt động nếu AOP proxy không được đi qua.

### Câu 25. @TransactionalEventListener có hoạt động với reactive transactions không?

Có, kể từ Spring Framework 6.1 có hỗ trợ ngữ cảnh giao dịch reactive theo cách riêng. Giao dịch imperative thường gắn với `ThreadLocal` của `PlatformTransactionManager`; reactive transaction dựa vào **Reactor Context**. Trong trường hợp reactive, transaction context cần được chuyển qua **event source** theo cơ chế được Spring hướng dẫn; `TransactionalEventPublisher` là API hỗ trợ phát event có transaction context phù hợp.

Không áp dụng máy móc kiểu “trong thread đang có transaction” cho pipeline Reactor. Luôn xác định stack transaction (JDBC/JPA hay R2DBC/reactive) trước khi chọn listener.

### Câu 26. AFTER_COMMIT có bảo đảm sự kiện không bao giờ mất sau DB commit không?

**Không.** Một callback sau commit vẫn chạy trong tiến trình ứng dụng và có thể bị mất nếu JVM chết đúng thời điểm, không có nơi lưu sự kiện. Nó giải quyết **thời điểm xử lý đối với transaction** chứ không tự cung cấp **durable delivery**.

Khi yêu cầu “đã commit là phải có bản tin để xử lý lại”, cân nhắc **transactional outbox**: ghi bản ghi outbox trong cùng transaction với domain data, relay chuyển bản tin sang broker, consumer có retry và idempotency.

### Câu 27. Transactional outbox giải quyết vấn đề gì?

Nó tránh tình trạng DB commit thành công nhưng một lời gọi publish ra broker thất bại và không có dấu vết để retry.

~~~text
@Transactional
  UPDATE orders
  INSERT outbox(eventId, type, payload, ...)
  COMMIT
        |
        v
Outbox relay -> broker -> consumer
                    |
                    +-- xử lý idempotent theo eventId
~~~

Outbox không tự biến toàn bộ hệ thống thành exactly-once. Relay có thể gửi trùng; consumer vẫn cần chống trùng side effect, quản lý ordering theo aggregate khi cần, và theo dõi bản ghi pending/failure.

### Câu 28. Event-driven có thay thế transaction management không?

**Không.** Event là phương thức liên lạc/điều phối; transaction là cơ chế nhất quán của tài nguyên. Hai khái niệm liên quan nhưng không đồng nhất. Với thay đổi phải nguyên tử trong một database, nên dùng transaction rõ ràng. Với workflow liên dịch vụ, cần event + idempotency + retry/compensation/saga/outbox tùy mô hình, không suy từ `publishEvent` rằng đã có atomicity toàn cục.

## 5. Câu hỏi Spring Boot lifecycle và đăng ký listener sớm

### Câu 29. SpringApplication phát những lifecycle events chính nào?

Một chuỗi thường gặp khi startup thành công theo Spring Boot 3.5:

1. `ApplicationStartingEvent`: đầu quá trình `run`, trước phần lớn xử lý.
2. `ApplicationEnvironmentPreparedEvent`: `Environment` đã chuẩn bị, context chưa tạo.
3. `ApplicationContextInitializedEvent`: context đã chuẩn bị và initializers đã được áp dụng, trước khi nạp các bean definitions của ứng dụng.
4. `ApplicationPreparedEvent`: trước refresh, sau khi bean definitions được nạp.
5. `ApplicationStartedEvent`: context đã refresh, trước khi chạy application/command-line runners.
6. `ApplicationReadyEvent`: sau các runners; báo ứng dụng đã sẵn sàng phục vụ.
7. `ApplicationFailedEvent`: phát khi startup gặp lỗi.

Ngoài các `SpringApplicationEvent` còn có `ContextRefreshedEvent` và những event khác như `WebServerInitializedEvent` tùy loại ứng dụng. Không đưa mọi event vào một thứ tự cứng cho mọi môi trường; hãy phân biệt nguồn và vòng đời.

### Câu 30. Vì sao @EventListener bean không nhận ApplicationStartingEvent?

Vì một số Boot events được phát **trước khi ApplicationContext và bean listener của ứng dụng tồn tại**. Annotated method trong bean chưa được đăng ký nên không thể nhận.

Giải pháp cho very-early Boot events: đăng ký `ApplicationListener` trước `SpringApplication.run(...)` bằng `SpringApplication.addListeners(...)`, `SpringApplicationBuilder.listeners(...)` hoặc cấu hình `META-INF/spring.factories` khi đóng gói thư viện.

`@EventListener` phù hợp hơn cho các event xảy ra sau khi bean listener được quản lý và đăng ký.

### Câu 31. ApplicationStartedEvent khác ApplicationReadyEvent?

`ApplicationStartedEvent` xảy ra **sau context refresh nhưng trước application/command-line runners**. `ApplicationReadyEvent` xảy ra **sau khi các runner hoàn tất**, biểu thị ứng dụng đã sẵn sàng ở phạm vi lifecycle của Boot.

Nếu cần thực thi tác vụ chuẩn bị có thể làm startup chậm, cân nhắc cách dùng `ApplicationRunner`/`CommandLineRunner`, background initialization hoặc lifecycle mechanism phù hợp, thay vì luôn dùng một listener đồng bộ rất nặng ở `ApplicationReadyEvent`.

### Câu 32. ApplicationFailedEvent là gì, và có luôn đến listener bean không?

`ApplicationFailedEvent` được Boot gửi khi startup thất bại, nhưng context có thể chưa hoàn chỉnh hoặc đã gặp lỗi trước khi listener bean được đăng ký. Do đó nếu muốn bắt lỗi **từ giai đoạn sớm**, nên dùng listener được đăng ký từ `SpringApplication`/`spring.factories` thay vì chỉ đặt một bean `@EventListener`.

Không dùng nó thay cho monitoring lỗi runtime hoặc cơ chế restart của process manager; nó nói về thất bại ở **startup**.

### Câu 33. Vì sao cùng event lifecycle có thể được nhận hai lần trong một ứng dụng?

Khi Spring Boot dùng **parent-child context hierarchy**, event phát từ child context có thể được chuyển lên ancestor context. Listener ở hierarchy có thể quan sát nhiều instance cùng kiểu. Cần xem `event.getApplicationContext()` (đối với lifecycle event có API này) và so với context mà bean/listener thuộc về.

Đừng kết luận ngay rằng cache multicaster hoặc `@EventListener` tự gửi trùng. Trước tiên hãy kiểm tra context hierarchy, bean duplication và cách đăng ký listener.

## 6. Câu hỏi nâng cao: hợp đồng, event chain, observability và security

### Câu 34. Sự khác nhau giữa domain event và command?

**Domain event** khẳng định một sự thật đã xảy ra, ví dụ `OrderPlaced` hay `PaymentCaptured`. **Command** yêu cầu thực hiện thao tác, ví dụ `CapturePayment` hoặc `SendReceipt`. Event nên có tên ở thì đã xảy ra và contract ngữ nghĩa ổn định.

Nếu event dùng để ép một listener duy nhất làm hành động bắt buộc rồi publisher ngầm chờ kết quả, kiến trúc có thể đang che một command hoặc một lời gọi service trực tiếp.

### Câu 35. Một listener tạo nhiều event liên tiếp có rủi ro gì?

Có thể return một `Collection`/array để Spring publish từng phần tử, tạo **fan-out** hoặc **event chaining**. Rủi ro:

- Vòng lặp `A -> B -> A` khi listener trả về event kích hoạt chính nó.
- Một listener downstream lỗi làm dừng phần còn lại của chuỗi đồng bộ.
- Sự phụ thuộc thứ tự ẩn giữa các listener.
- Replay input event sinh lại các side effect.
- Dùng async nhưng vẫn mong return-value publication hoạt động.

Nếu cần workflow có thứ tự bắt buộc, hãy xem xét application service hoặc workflow engine rõ ràng.

### Câu 36. Event contract nên chứa những gì?

Tối thiểu: event type/tên nghiệp vụ, version, event ID, aggregate ID, occurrence time, payload snapshot tối thiểu, field types/unit/nullability, provenance và semantics phát. Khi workflow nhiều bước, có thể thêm `correlationId` và `causationId`.

**Không** đưa nguyên `@Entity` mutable, toàn bộ graph hoặc credentials vào public event contract. Với tiền, ghi rõ đơn vị và currency; với timestamp, ghi chuẩn UTC/`Instant`.

Một thay đổi thêm field không tự tương thích trong mọi trường hợp: Java constructor, strict JSON deserializer, consumer cũ, enum mở rộng và thay đổi ngữ nghĩa đều có thể phá vỡ contract.

### Câu 37. Làm sao chuyển từ event V1 sang V2 không làm hỏng consumer?

Một chiến lược phổ biến là **expand → migrate → contract**:

1. Định nghĩa V2, mapping và các quy tắc backward/forward compatibility.
2. Nâng consumer/adapter để đọc cả V1 và V2 trước khi đổi producer.
3. Kiểm thử các fixture event lịch sử và version mới.
4. Chuyển producer, quan sát lỗi decode và độ phủ consumer.
5. Ngừng V1 khi hết phụ thuộc và có giải pháp đọc/replay dữ liệu cũ.

Nếu dual-publish V1 và V2 cho **cùng occurrence**, cần route và idempotency; không phát hai version rồi vô tình chạy side effect hai lần. `eventId` của occurrence và `schemaVersion` phải có quy ước rõ ràng.

### Câu 38. Event ID và correlation ID khác nhau?

`eventId` định danh **một occurrence**; `correlationId` nối **nhiều occurrence** trong cùng nghiệp vụ. `orderId` là aggregate ID, không thay thế hai ID trên. Một workflow có thể có `OrderPlaced`, `PaymentCaptured`, `OrderShipped` chung correlation ID nhưng event ID riêng.

Khi retry cùng occurrence, nên giữ event ID gốc để dedup; khi phát một fact mới, cấp event ID mới. Trace ID/span ID phục vụ tracing kỹ thuật và có thể thay đổi qua retry, không nên làm khóa nghiệp vụ duy nhất.

### Câu 39. Spring có tự cung cấp distributed tracing cho mỗi @EventListener không?

Spring Framework **không tự tạo một Observation cho từng lời gọi `@EventListener`** chỉ vì có annotation. Với listener đồng bộ, logging/tracing thread context có thể còn hiệu lực; khi chuyển executor, cần propagation có chủ đích (ví dụ `ContextPropagatingTaskDecorator` và Micrometer Context Propagation).

Để đo riêng latency/error của handler, instrument bằng Micrometer Observation/Tracing theo nhu cầu. Không dùng event ID hoặc correlation ID làm **low-cardinality metrics tags** vì cardinality cao; đặt ID vào logs/span attributes khi an toàn.

### Câu 40. Spring Application Events có bảo mật sẵn cho listener không?

**Không có một cơ chế authorization tự động chỉ vì listener nhận event.** Event routing theo type không giống kiểm tra actor có quyền xem/sửa bản ghi. Với side effect nhạy cảm:

- Xác thực nguồn event và actor ở trust boundary.
- Đặt `@PreAuthorize`/`AuthorizationManager` ở service thực hiện thao tác (bật `@EnableMethodSecurity` khi cần).
- Kiểm tra object/tenant permissions bằng dữ liệu đáng tin.
- Với async, xử lý đúng `SecurityContext` hoặc service principal.
- Không coi `claimedRole="ADMIN"` trong payload là authority thật.

Đừng truyền JWT hoặc `Authentication` đang sống vào event lưu lâu chỉ để “giữ quyền” qua replay.

### Câu 41. Listener cache trong multicaster hoạt động thế nào?

`AbstractApplicationEventMulticaster` có cơ chế cache danh sách ứng viên theo **`ResolvableType` của event và source type** khi có thể cache an toàn. Nó giảm chi phí matching khi nhiều event cùng type/source. Khi đăng ký/gỡ listener qua API chính thức, cache tiền lọc được invalidated.

**Cache không giảm số lần xử lý event có listener phù hợp**. Bộ lọc `@EventListener(condition)` vẫn cần đánh giá theo payload từng lần; không đặt feature flag thay đổi liên tục vào `supportsEventType(...)` rồi kỳ vọng Spring gọi predicate này trên mỗi event.

### Câu 42. Có thể dùng @EventListener cho event sourcing không?

`@EventListener` có thể dùng để **phản ứng** khi một event được publish, nhưng bản thân nó không phải event store. Event sourcing đòi hỏi dữ liệu event được lưu bền vững như nguồn sự thật, có thứ tự, version, replay, snapshot, migration và khả năng tái dựng trạng thái.

Nếu chỉ phát event trong JVM rồi mất khi restart, đó **không phải một triển khai event sourcing đầy đủ**. Cần thiết kế storage/schema/idempotency/replay riêng.

### Câu 43. Khi nào nên dùng Application Events, khi nào dùng Kafka/RabbitMQ?

| Nhu cầu | Application Events | Broker / outbox |
| --- | --- | --- |
| Tách module nội bộ cùng JVM | Phù hợp, setup nhẹ. | Có thể quá nặng nếu không cần boundary. |
| Chạy logic phụ ngắn ngay trong process | Phù hợp, chú ý đồng bộ/lỗi. | Không luôn cần thiết. |
| Giao message qua service/process | Không tự làm được. | Phù hợp. |
| Phải replay sau restart | Không mặc định hỗ trợ. | Cần storage/log/retention và consumer phù hợp. |
| Retry có kiểm soát, DLQ | Không có sẵn như broker. | Thiết kế dựa vào broker/outbox/inbox. |
| Yêu cầu transaction atomic với DB rồi giao message | Không tự bảo đảm. | Transactional outbox và relay là lựa chọn phổ biến. |

Kafka và RabbitMQ có đặc điểm khác nhau; đừng gộp “broker” thành một bộ bảo đảm duy nhất. Cần nói rõ delivery semantics, partition/ordering, duplicate và consumer failure theo công nghệ cụ thể.

### Câu 44. Spring có đảm bảo exactly-once event processing không?

**Không mặc định.** Ngay cả broker có một số tính năng exactly-once trong phạm vi nhất định, side effect bên ngoài như gửi email hoặc ghi sang một DB khác vẫn cần thiết kế chống trùng.

Ví dụ consumer ghi `(consumerName, eventId)` với unique constraint trong transaction phù hợp để hỗ trợ idempotency. Khi có side effect qua HTTP hoặc email, cân nhắc idempotency key ở đối tác, outbox/inbox, retry và reconciliation.

### Câu 45. Khi nào không nên dùng @EventListener?

Tránh dùng event như một lớp trừu tượng che đi:

- Một bước bắt buộc phải thực thi theo thứ tự và phải trả lỗi trực tiếp.
- Một thao tác cần kết quả đồng bộ để caller quyết định tiếp.
- Một workflow nhiều service yêu cầu retry/replay bền vững.
- Một chức năng nhạy cảm mà quyền/trust boundary chưa được định nghĩa.
- Một đường nóng hiệu năng cao khi số listener/coupling ẩn làm debug khó hơn lợi ích tách module.

Một lời gọi service trực tiếp, application orchestrator hoặc broker/event store có thể minh bạch hơn. Giá trị của event là **loose coupling có kiểm soát**, không phải tách mọi lời gọi bất kể ngữ cảnh.

## 7. Bài thực hành Java 17+ có thể chạy để giải thích khi phỏng vấn

Ví dụ dùng **Spring Framework 6.2.9**, Maven và Java 17 trở lên, không dùng Spring Boot để tránh lifecycle events làm nhiễu stdout. Chúng ta sẽ minh họa bốn ý chính:

1. Publisher phát một **payload record** không kế thừa `ApplicationEvent`.
2. `@EventListener` đồng bộ, có thể sắp xếp bằng `@Order`.
3. `condition` SpEL lọc mỗi event theo một giá trị nghiệp vụ.
4. Listener trả `List<Object>` để Spring phát tiếp **hai event độc lập**.

### 7.1. Cấu trúc project

~~~text
spring-event-interview/
├── pom.xml
└── src/main/java/InterviewEventsDemo.java
~~~

Tệp `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>spring-event-interview</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/java/InterviewEventsDemo.java`:

~~~java
import java.util.List;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class InterviewEventsDemo {

    public record OrderPlaced(String orderId, long amountMinorUnits) {}

    public record AuditRequested(String orderId) {}

    public record MetricsRequested(String orderId) {}

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Handlers handlers() {
            return new Handlers();
        }
    }

    public static class Handlers {

        @Order(0)
        @EventListener
        public void observe(OrderPlaced event) {
            System.out.println("SEEN " + event.orderId()
                    + " " + event.amountMinorUnits());
        }

        @Order(10)
        @EventListener(condition = "#p0.amountMinorUnits() >= 10000")
        public List<Object> routeLargeOrder(OrderPlaced event) {
            System.out.println("ROUTE " + event.orderId());

            // Mỗi phần tử List trở thành một event riêng.
            return List.of(
                    new AuditRequested(event.orderId()),
                    new MetricsRequested(event.orderId()));
        }

        @EventListener
        public void audit(AuditRequested event) {
            System.out.println("AUDIT " + event.orderId());
        }

        @EventListener
        public void metrics(MetricsRequested event) {
            System.out.println("METRICS " + event.orderId());
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            System.out.println("BEGIN");
            context.publishEvent(new OrderPlaced("ORD-1", 15000));
            context.publishEvent(new OrderPlaced("ORD-2", 5000));
            System.out.println("END");
        }
    }
}
~~~

### 7.2. Chạy

Trong thư mục có `pom.xml`, dùng Maven và Java 17+:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=InterviewEventsDemo
~~~

**Stdout do chương trình in ra** (không tính log build/Maven hoặc môi trường):

~~~text
BEGIN
SEEN ORD-1 15000
ROUTE ORD-1
AUDIT ORD-1
METRICS ORD-1
SEEN ORD-2 5000
END
~~~

### 7.3. Phân tích từng dòng

- `BEGIN` xuất hiện trước khi publish.
- Với `ORD-1`, listener `observe` có `@Order(0)` nên in `SEEN` trước listener `routeLargeOrder` có `@Order(10)`.
- Vì `amountMinorUnits = 15000` đạt ngưỡng, SpEL cho kết quả true, method in `ROUTE` và trả `List.of(AuditRequested, MetricsRequested)`.
- Spring phát từng event con: `audit` in `AUDIT ORD-1`, rồi `metrics` in `METRICS ORD-1`. Các call đang đồng bộ nên diễn ra trước khi event gốc hoàn tất.
- Với `ORD-2`, `observe` vẫn được gọi, nhưng `routeLargeOrder` có condition false vì `5000 < 10000`, không tạo audit/metrics event.
- `END` chỉ xuất hiện sau khi hai lần `publishEvent(...)` đồng bộ kết thúc.

**Không tự suy ra** điều kiện của `routeLargeOrder` được cache theo amount: Spring có thể cache **tập ứng viên theo type**, nhưng SpEL vẫn phải kiểm tra giá trị từng event. Nếu thêm `@Async` hoặc executor, thứ tự thời gian của các dòng log không còn được bảo đảm giống ví dụ.

### 7.4. Hai thay đổi để tự luyện

**Bài A:** đổi `ORD-2` từ `5000` thành `10000`. Vì điều kiện dùng `>=`, kết quả dự kiến phải thêm ba dòng `ROUTE ORD-2`, `AUDIT ORD-2` và `METRICS ORD-2` trước `END`.

**Bài B:** giả sử method `audit` ném `IllegalStateException` và không có ErrorHandler. Trong cấu hình mặc định đồng bộ, hãy dự đoán liệu `METRICS ORD-1` và `END` có được in không. Câu trả lời: **không bảo đảm sẽ được in**; exception có thể ngắt luồng xử lý trước khi phát phần tử tiếp theo và có thể truyền ngược về `publishEvent(...)`.

**Bài C:** muốn việc audit chỉ chạy sau khi transaction lưu đơn đã commit, phải thêm transaction thật và dùng `@TransactionalEventListener(AFTER_COMMIT)` theo boundary thích hợp. Không chỉ thêm annotation vào demo vốn **không có transaction** rồi kỳ vọng listener vẫn được gọi.

## 8. Câu hỏi tình huống cho vòng phỏng vấn senior

### Tình huống 1. Đặt hàng thành công nhưng đôi lúc khách nhận email dù DB rollback

**Giả thiết:** `@Transactional OrderService.placeOrder()` publish `OrderPlaced`; listener đồng bộ gửi email; sau đó transaction rollback vì một bước kiểm tra thất bại.

**Hướng trả lời:**

- Listener `@EventListener` đồng bộ có thể đã chạy **trước commit**.
- Email là external side effect, không thể rollback cùng DB.
- Nếu chỉ cần xử lý sau commit trong cùng JVM, dùng `@TransactionalEventListener(AFTER_COMMIT)`.
- Nếu email **không được phép mất** khi process crash, ghi outbox cùng transaction và dùng relay/queue có retry.
- Consumer gửi email idempotently hoặc dùng idempotency key khi nhà cung cấp hỗ trợ.
- Kiểm thử tình huống rollback trước khi gửi, crash sau commit và duplicate delivery.

**Câu hỏi gợi mở:** Có cần một email chính xác một lần không? Nếu có, giải thích rõ giới hạn của API email và reconciliation thay vì hứa “exactly once” tuyệt đối.

### Tình huống 2. Sau khi thêm @Async, log listener không còn traceId

**Hướng trả lời:** `@Async` đẩy method sang executor; MDC/ThreadLocal tracing của publisher không tự truyền. Kiểm tra executor thực tế, `@EnableAsync` và Micrometer Context Propagation; có thể dùng `ContextPropagatingTaskDecorator` nếu accessor phù hợp. Giữ business `correlationId` trong payload/envelope để truy vết xuyên retry/traces mới.

Đừng dùng `InheritableThreadLocal` như giải pháp tổng quát cho pool. Không copy JDBC transaction chỉ để “giữ context”.

### Tình huống 3. Có hai event handlers, khi một handler lỗi thì handler thứ hai không được chạy

**Hướng trả lời:** kiểm tra multicast đồng bộ và exception; nếu một listener ném exception chưa được xử lý, dispatch có thể dừng. Lựa chọn dựa vào yêu cầu: xử lý lỗi từng handler, cấu hình ErrorHandler, tách thành các work items độc lập, hoặc broker/outbox với retry riêng. Đừng chỉ bắt exception rồi im lặng: phải có logging, metric và outcome chính xác.

### Tình huống 4. @TransactionalEventListener không chạy trong unit test

**Hướng trả lời:** kiểm tra test có transaction thật được Spring quản lý không, phase, `fallbackExecution` mặc định false và cách gọi qua proxy. Một method test tự tạo object bằng `new` hoặc publish khi không có transaction phù hợp có thể không kích hoạt after-commit listener. Không bật fallback vô điều kiện; nên tạo integration test với transaction manager và xác minh cả commit/rollback.

### Tình huống 5. Sau khi nâng cấp producer, consumer cũ không đọc được event

**Hướng trả lời:** phân biệt **Java API compatibility** với **wire schema compatibility**. Đổi constructor record, xóa field, đổi tên, đổi đơn vị tiền và thêm enum value đều có thể gây đứt gãy. Version hóa hợp đồng, adapter/upcaster, schema registry nếu thích hợp; nâng consumer trước producer; giữ fixture event lịch sử; kiểm thử replay và event type routing.

### Tình huống 6. Người phỏng vấn yêu cầu thiết kế hệ thống order/inventory/payment bằng events

**Hướng trả lời:** làm rõ domain boundaries và tính nhất quán trước: trong **một database/một service** thì application service/transaction và application events phù hợp cho việc tách side effects phụ; giữa **nhiều service** thì cần broker/outbox và idempotent consumers. Inventory reservation hoặc payment capture có kết quả bắt buộc và timeout, nên thường cần workflow orchestration/saga, compensation và trạng thái rõ ràng; không chỉ bắn ba event rồi kỳ vọng tất cả thành công.

### Tình huống 7. Listener chạy trùng hai lần trong Spring Boot

**Hướng trả lời:** trước tiên kiểm tra nhiều bean registrations, parent-child context hierarchy, trùng publisher calls, code tự replay, application restarts và broker duplicate. Không đổ lỗi ngay cho cache listener. Theo dõi `eventId`/`correlationId`, context ID, listener bean identity và thread để tìm nguồn.

### Tình huống 8. Listener phải có quyền truy cập đơn hàng nhưng event chứa userId

**Hướng trả lời:** `userId` hay `claimedRole` trong payload không phải bằng chứng Authentication. Dùng Spring Security/`@PreAuthorize` tại service side effect, kiểm tra owner/tenant bằng nguồn đáng tin, dùng service identity least-privilege cho background jobs. Nếu async, SecurityContext cần propagation phù hợp hoặc revalidation; không tái dùng token người dùng hết hạn qua event store.

## 9. Năm câu hỏi phản biện để chứng minh hiểu sâu

### “@TransactionalEventListener(AFTER_COMMIT) chắc chắn gửi Kafka message sau commit, đúng không?”

**Sai về chữ chắc chắn.** Callback được gắn với phase commit, nhưng message gửi tới broker vẫn có thể thất bại hoặc process có thể chết. Nếu cần không mất message, dùng outbox và relay; consumer chịu duplicate.

### “@Order(1) listener A và @Order(2) listener B thì A luôn hoàn thành trước B?”

Chỉ trong phạm vi dispatch đồng bộ phù hợp. Nếu có `@Async`/executor hoặc tác vụ downstream, việc hoàn thành không còn được bảo đảm bởi thứ tự gọi ban đầu. Nếu đây là invariant nghiệp vụ, điều phối rõ ràng.

### “@EventListener(condition) có thể dùng làm cơ chế authorization không?”

Không. SpEL condition lọc event value, còn phân quyền cần actor/source trust, object/tenant permissions và policy ở service/data boundary. Event payload có thể mang dữ liệu tự khai, không phải quyền đã xác minh.

### “Spring publishEvent() bảo đảm exactly-once processing trong cùng JVM?”

Không nên phát biểu như vậy. Một lời gọi có thể dispatch cho listener phù hợp, nhưng exception/registration/context hierarchy, event chaining, retry do application và side effects làm semantics phức tạp. Nó không phải một transaction exactly-once delivery API.

### “Một record event có List là Spring sẽ tự tách thành nhiều events?”

Không đúng nếu `List` là **một field bên trong record payload**. Spring chỉ tự phát nhiều event khi một **`@EventListener` trả về Collection/array** theo cơ chế return-value publication. Phải phân biệt wrapper event chứa list với method return list.

## 10. Mini mock interview: tự trả lời trong 10 phút

Có thể dùng bộ thử dưới đây trong phỏng vấn thử. Mỗi câu nên trả lời thành tiếng khoảng 30–60 giây, rồi tự đối chiếu với các phần trên.

| Vòng | Câu hỏi | Một dấu hiệu của câu trả lời đạt |
| --- | --- | --- |
| Junior | Publish arbitrary object được không? | Có, Spring dùng `PayloadApplicationEvent` cho object không kế thừa `ApplicationEvent`. |
| Junior | Listener có đồng bộ không? | Mặc định đồng bộ; cấu hình `@Async`/executor mới đổi. |
| Junior | Condition lấy tham số đầu tiên thế nào? | `#p0` hoặc `#a0`. |
| Mid | Listener ném exception thì sao? | Có thể dừng multicast đồng bộ, lan về publisher. |
| Mid | Tại sao AFTER_COMMIT không chạy? | Không có transaction hoặc phase không phù hợp; fallback mặc định false. |
| Mid | Return List từ listener thì sao? | Phát từng phần tử thành event mới nếu listener đồng bộ. |
| Mid | Listener event Boot quá sớm đăng ký thế nào? | `SpringApplication.addListeners(...)` hoặc `spring.factories`. |
| Senior | Gửi email đúng sau DB commit nhưng không mất? | Outbox + relay + idempotency; không chỉ AFTER_COMMIT. |
| Senior | Trace context mất khi @Async? | Xem executor/context propagation và correlation ID trong event. |
| Senior | Event versioning khi schema đổi? | Compatibility policy, migration, adapters, fixture/replay tests. |
| Senior | Security của listener được bảo vệ ở đâu? | Trusted identity + method/object authorization tại service boundary. |
| Senior | Khi nào không dùng events? | Logic tuần tự bắt buộc, kết quả đồng bộ, tác vụ bền vững xuyên service. |

### Tiêu chí tự chấm

- **Đạt nền tảng:** giải thích đúng publisher → multicaster → listener, payload object và sync mặc định.
- **Đạt mức trung cấp:** mô tả chính xác condition, return value, error handling, transaction phases và async.
- **Đạt mức nâng cao:** phân biệt consistency/delivery semantics với event dispatch; biết outbox, idempotency, security, schema evolution và observability.
- **Thuyết phục ở cấp thiết kế:** đề xuất trade-off có điều kiện, làm rõ failure scenarios và nêu integration/chaos tests để chứng minh các cam kết.

## 11. Checklist những bẫy sai hay gặp trước buổi phỏng vấn

1. **“Spring event mặc định async”** → sai: mặc định đồng bộ, cùng thread publisher.
2. **“ApplicationEventPublisher là Kafka thu nhỏ”** → sai: không có durable log/offset/retry.
3. **“Đã return Collection thì một List là một event”** → sai: Spring publish **từng phần tử** của kết quả.
4. **“@Async listener có thể return event để publish tiếp”** → sai: phải gọi publisher thủ công.
5. **“@Order luôn bảo đảm hoàn thành theo thứ tự”** → sai khi có concurrency/async.
6. **“@TransactionalEventListener luôn chạy dù không có transaction”** → sai nếu `fallbackExecution=false` mặc định.
7. **“AFTER_COMMIT đủ để gửi email/broker chắc chắn”** → sai: vẫn có crash window.
8. **“Giao dịch JDBC tự đi theo thread pool”** → sai: transaction context thường gắn thread.
9. **“Bất kỳ @EventListener bean nào cũng nghe ApplicationStartingEvent”** → sai vì event quá sớm.
10. **“Thêm field/enum value luôn backward compatible”** → sai: tùy Java/wire/parser/semantic contract.
11. **“Mỗi event chỉ có đúng một listener”** → sai: nhiều listener phù hợp có thể cùng nhận.
12. **“Listener nhận được event tức có quyền thao tác”** → sai: routing khác authorization.
13. **“EventId là traceId”** → sai: business occurrence khác tracing execution.
14. **“Cache listener làm handler chỉ chạy lần đầu”** → sai: chỉ cache matching candidates.
15. **“Event sourcing chỉ cần @EventListener”** → sai: còn thiếu lưu bền, replay, versioning.
16. **“Thấy listener chạy hai lần nghĩa là cache hỏng”** → chưa đủ chứng cứ; xem context hierarchy/registration/retry.
17. **“Biết tên method là biết event type”** → sai: dispatch dựa type/signature hoặc annotation.
18. **“Một unit test gọi thẳng listener sẽ kiểm tra @EventListener(condition)”** → sai: phải publish qua Spring context.
19. **“Một listener bị lỗi thì tất cả side effects đều rollback”** → sai nếu đã gọi email/HTTP hoặc không chung DB transaction.
20. **“Dùng @Async là được retry khi thread lỗi”** → sai: cần cơ chế retry/idempotency và quan sát lỗi riêng.

## 12. Câu hỏi thực hành cuối bài

**Bài 1.** Tạo event `OrderPlaced` và hai listener, một có `@Order(1)`, một có `@Order(10)`. Quan sát stdout ở chế độ sync, sau đó thêm `@Async`. Giải thích tại sao không nên dùng thứ tự log async để suy ra thứ tự hoàn thành.

**Bài 2.** Tạo `@EventListener(condition = "#p0.totalMinorUnits() >= 10000")` và publish ba giá trị `9999`, `10000`, `10001`. Xác minh đúng ranh giới bằng integration test. Sau đó cố ý đổi `>=` thành `>` và giải thích test nào phát hiện lỗi.

**Bài 3.** Trong một project có transaction manager, tạo `@EventListener` và `@TransactionalEventListener(AFTER_COMMIT)`. Publish từ một method `@Transactional` rồi lần lượt commit và rollback. Ghi rõ listener nào chạy, thời điểm và tại sao.

**Bài 4.** Thử tạo `@Async @EventListener` trả một `List<Object>`. Tại sao kỳ vọng Spring publish tiếp danh sách là không hợp lệ? Sửa bằng `ApplicationEventPublisher.publishEvent(...)` thủ công và test completion bằng `CountDownLatch`.

**Bài 5.** Thiết kế event `PaymentCapturedV2` có `eventId`, `correlationId`, `amountMinorUnits`, `currency`. Viết một adapter đọc V1 với **quy tắc tiền tệ legacy đã được hợp đồng bảo đảm**, không tự bịa currency. Nêu cách chống xử lý trùng khi V1/V2 cùng đại diện một occurrence.

**Bài 6.** Thiết kế một outbox nhỏ (chỉ mô tả contract và transaction boundary): khi đơn commit, record outbox cũng commit. Nếu relay publish hai lần, consumer dedup theo khóa nào? Cần quan sát những metric nào để phát hiện backlog và lỗi?

**Bài 7.** Viết test xác minh listener có authority toàn cục nhưng không có quyền với `orderId` của tenant khác bị từ chối; nhấn mạnh `actorId` trong payload là metadata, không thay cho authentication.

**Bài 8.** Trả lời trong tối đa 90 giây: “Vì sao chúng ta nên dùng Spring Application Events cho module metrics trong một monolith, nhưng dùng broker/outbox cho thông báo quan trọng ở dịch vụ khác?” Câu trả lời phải nêu giới hạn **process boundary**, **durable delivery**, **failure semantics** và chi phí vận hành.

## Tài liệu tham khảo

- [Spring Framework Reference 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`, SpEL, return value, async, ordering và generic event.
- [Spring Framework 6.2.9 Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html): `publishEvent(Object)` và giới hạn của publication.
- [Spring Framework 6.2.9 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): synchronous mặc định, executor và error handler.
- [Spring Framework Reference 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html): `@TransactionalEventListener`, các phase, fallback, reactive context.
- [Spring Boot 3.5 — SpringApplication Events](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): lifecycle events và đăng ký early listeners.
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): tracing context trong event handlers, `ContextPropagatingTaskDecorator`.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity` và `@PreAuthorize` cho service nghiệp vụ.
