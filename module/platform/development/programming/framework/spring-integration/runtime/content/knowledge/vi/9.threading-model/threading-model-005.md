# Thread context, MDC và propagation

Trong Spring Integration, một message có thể đi qua nhiều channel và endpoint, nhưng không phải mọi bước đều chạy trên cùng một thread. Khi flow chuyển từ `DirectChannel` sang `ExecutorChannel`, từ producer sang poller hoặc qua một executor khác, các dữ liệu gắn với thread hiện tại như MDC, `ThreadLocal`, security context hay request context có thể không còn xuất hiện ở bước tiếp theo.

Message header đi cùng message; thread context đi cùng thread. Đây là khác biệt quan trọng khi cần nối log, trace và thông tin nghiệp vụ qua các ranh giới bất đồng bộ. Muốn propagation đáng tin cậy, hãy xác định dữ liệu nào thuộc message, dữ liệu nào thuộc thread, rồi chọn cơ chế truyền phù hợp cho từng loại.

## 1. Thread context là gì?

Thread context là trạng thái được lưu gắn với thread đang thực thi. Trong Java, nhiều framework dùng `ThreadLocal` để giữ trạng thái này mà không phải truyền tham số qua mọi method.

Một số ví dụ thường gặp:

| Context | Mục đích | Cơ chế thường dùng |
|---|---|---|
| SLF4J MDC | Gắn correlation ID, tenant ID hoặc thông tin request vào log | `MDC` dựa trên thread-local state |
| Spring Security | Giữ `SecurityContext` và principal của request | `SecurityContextHolder` mặc định dùng thread-local strategy |
| Spring transaction | Giữ transaction/resource đang tham gia trên thread hiện tại | Transaction synchronization và resource binding theo thread |
| Locale/request context | Giữ locale hoặc thông tin request trong quá trình xử lý đồng bộ | `LocaleContextHolder`, `RequestContextHolder` |
| Tracing context | Liên kết span hiện tại với log và các lời gọi tiếp theo | Micrometer Tracing/OpenTelemetry context và propagation |

Thread-local giúp code đồng bộ dễ sử dụng, nhưng không tự trở thành dữ liệu của message. Khi một task chạy trên worker thread khác, worker có thread-local riêng. Java không tự sao chép toàn bộ context từ thread gửi sang thread nhận.

Không nên coi mọi thread context là cùng một loại dữ liệu. Correlation ID nghiệp vụ có thể nằm trong message header; MDC là cách đưa một số giá trị vào log; transaction là trạng thái quản lý tài nguyên; security context là danh tính và quyền hạn. Chúng có yêu cầu vòng đời và bảo mật khác nhau.

## 2. Những ranh giới thread trong Spring Integration

Loại channel và cách endpoint được kích hoạt quyết định nơi thread thay đổi.

| Thành phần | Hành vi thread điển hình | Hệ quả với context |
|---|---|---|
| `DirectChannel` | Gọi subscriber trên thread gửi message | MDC và ThreadLocal hiện tại thường còn thấy được trong lời gọi đồng bộ |
| `ExecutorChannel` | Giao xử lý cho `TaskExecutor` | Worker thread khác; context cần propagation rõ ràng |
| `QueueChannel` | Producer enqueue, polling consumer nhận message sau | Consumer chạy trên thread của poller; context từ producer không tự đi theo queue |
| `PublishSubscribeChannel` không có executor | Subscriber thường chạy đồng bộ trên thread gửi | Context còn trong cùng call path, tùy subscriber |
| `PublishSubscribeChannel` có executor | Subscriber được dispatch bất đồng bộ | Mỗi worker cần context propagation |
| Polling endpoint | Poller nhận message trên thread scheduler hoặc executor của poller | Context của thread gửi vào queue không tự có ở poller |

Sơ đồ minh họa:

~~~mermaid
flowchart LR
    A[HTTP request thread<br/>MDC + SecurityContext] --> B[DirectChannel]
    B --> C[Transformer]
    C --> D[ExecutorChannel]
    D --> E[Worker thread<br/>context mới]
    E --> F[Service Activator]
    F --> G[Remote service]
~~~

Ở đoạn từ A tới C, code thường chạy trên cùng thread. Khi message đi qua `ExecutorChannel`, task được thực thi trên worker thread E. Header của message vẫn đi theo message nếu được giữ lại, nhưng MDC, `SecurityContextHolder` hoặc `LocaleContextHolder` của thread A không tự xuất hiện ở E.

`QueueChannel` tạo một ranh giới tương tự về mặt thời gian: producer gửi message vào queue rồi kết thúc; poller lấy message sau đó. Message header có thể được giữ trong queue, nhưng thread context của producer đã kết thúc hoặc được dùng cho request khác.

Không phải cứ dùng channel là bất đồng bộ. `DirectChannel` thường đồng bộ; `ExecutorChannel` mới chủ động chuyển việc xử lý sang executor. Cũng không phải cứ cùng một `IntegrationFlow` thì các endpoint dùng chung một thread. Hãy xác định channel, poller, executor và adapter thực tế giữa hai bước.

## 3. Message header và MDC có vai trò khác nhau

Thông tin cần theo message qua nhiều channel nên được đặt trong message header hoặc payload theo hợp đồng nghiệp vụ. MDC chỉ là cách làm cho log của thread hiện tại có thêm trường để truy vấn.

Ví dụ producer đặt correlation ID vào message header:

~~~java
Message<Order> message = MessageBuilder.withPayload(order)
        .setHeader("correlationId", correlationId)
        .build();

ordersInputChannel.send(message);
~~~

Ở endpoint phía sau, lấy correlation ID từ message và đưa vào log context trong phạm vi xử lý:

~~~java
public void handle(Message<Order> message) {
    String correlationId = message.getHeaders()
            .get("correlationId", String.class);

    try (MDC.MDCCloseable ignored =
                 MDC.putCloseable("correlationId", correlationId)) {
        log.info("Processing order messageId={}",
                message.getHeaders().getId());
        orderService.process(message.getPayload());
    }
}
~~~

`MDC.putCloseable` giúp xóa giá trị sau block. Nếu dùng API MDC thông thường, hãy đặt `MDC.remove(...)` trong `finally`. Đừng để correlation ID của message trước tồn tại trên worker thread để message tiếp theo vô tình ghi log với ID sai.

Nếu transformer tạo một message mới, hãy kiểm tra các header cần thiết có được giữ lại hay không. Với `MessageBuilder`, có thể dùng `copyHeadersIfAbsent(...)` để giữ metadata từ message nguồn và bổ sung header mới. Một số adapter hoặc protocol chỉ truyền những header được cấu hình trong header mapper; không mặc định mọi header nội bộ đều qua được broker hoặc HTTP.

Message header là nguồn dữ liệu để liên kết message và nghiệp vụ. MDC là bản chiếu tạm thời của một số trường vào log. Không đọc MDC để quyết định nghiệp vụ nếu message header hoặc dữ liệu domain mới là nguồn sự thật.

## 4. Vì sao MDC bị mất hoặc rò rỉ?

MDC thường được triển khai dựa trên thread-local map. Khi request bắt đầu trên thread A, ứng dụng đặt `correlationId` vào MDC. Nếu xử lý tiếp tục đồng bộ, các log sau đó trên thread A nhìn thấy giá trị này. Khi task được submit sang thread B, thread B không tự nhận map của A.

Thread pool còn tạo ra một vấn đề khác: worker thread được tái sử dụng. Nếu một task đặt MDC nhưng không xóa, task tiếp theo có thể thấy giá trị cũ. Lỗi này nguy hiểm vì log vẫn hợp lệ về cú pháp nhưng gắn sai request hoặc tenant.

Ví dụ không an toàn:

~~~java
public void process(Message<?> message) {
    MDC.put("correlationId", correlationId(message));
    service.process(message);
    // Nếu không remove trong finally, worker có thể giữ lại giá trị.
}
~~~

Ví dụ an toàn trong xử lý đồng bộ:

~~~java
public void process(Message<?> message) {
    String correlationId = correlationId(message);
    try {
        MDC.put("correlationId", correlationId);
        service.process(message);
    }
    finally {
        MDC.remove("correlationId");
    }
}
~~~

Nếu block có thể lồng nhau hoặc cần giữ context trước đó, lưu map cũ rồi khôi phục trong `finally`, hoặc dùng `MDC.putCloseable` khi phù hợp. Không gọi `MDC.clear()` một cách tùy tiện nếu cùng thread có context khác do framework quản lý; hãy xác định rõ phạm vi sở hữu các key.

## 5. Propagate MDC qua TaskExecutor bằng TaskDecorator

Spring Framework cung cấp `TaskDecorator` để bọc `Runnable` trước khi executor thực thi. Đây là điểm phù hợp để chụp context trên thread submit và cài lại trên worker thread.

Ví dụ decorator chỉ sao chép MDC:

~~~java
public class MdcTaskDecorator implements TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> callerContext = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previousContext = MDC.getCopyOfContextMap();
            try {
                if (callerContext == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(callerContext);
                }

                task.run();
            }
            finally {
                if (previousContext == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(previousContext);
                }
            }
        };
    }
}
~~~

Gắn decorator vào executor:

~~~java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("integration-worker-");
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(30);
    return executor;
}

@Bean
MessageChannel asyncOrdersChannel(TaskExecutor integrationExecutor) {
    return new ExecutorChannel(integrationExecutor);
}
~~~

Decorator chụp map lúc task được submit, cài map đó trên worker rồi khôi phục context worker trước đó sau khi task kết thúc. Bước khôi phục rất quan trọng vì worker được tái sử dụng. Ví dụ này chỉ propagation MDC; nó không sao chép transaction, security context hay mọi `ThreadLocal` khác.

Nếu executor nhận task từ nhiều nguồn, chỉ các key thực sự cần thiết nên được đưa vào MDC. Tránh sao chép dữ liệu lớn, token hoặc thông tin nhạy cảm. Khi xử lý nested task, cần hiểu context nào được kế thừa và context nào phải được thay thế.

## 6. Micrometer Context Propagation

Khi ứng dụng cần propagation nhiều loại context, tự viết decorator cho từng `ThreadLocal` dễ thiếu sót. Micrometer Context Propagation cung cấp abstraction để capture context ở nơi submit và restore context trong phạm vi task.

Trong Spring Framework 6.1+, có thể dùng `ContextPropagatingTaskDecorator`:

~~~java
@Bean
ThreadPoolTaskExecutor integrationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(8);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("integration-worker-");
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    return executor;
}
~~~

Decorator này sử dụng `ContextSnapshot` và các `ThreadLocalAccessor` đã đăng ký trong `ContextRegistry` để capture/restore context. Cần có Micrometer Context Propagation trên classpath và accessor tương ứng cho loại context muốn truyền. Chỉ cài decorator không có nghĩa mọi `ThreadLocal` tùy chỉnh trong ứng dụng tự động được nhận diện.

Với một `ThreadLocal` do ứng dụng tự tạo, đăng ký accessor để mô tả cách đọc, cài đặt và reset giá trị. Cần bảo đảm thao tác reset xóa giá trị khi snapshot không chứa key đó. Nếu không, giá trị từ task trước có thể còn lại trên worker.

Context propagation có chi phí capture và restore. Chỉ bật cho executor và context cần thiết. Với rất nhiều task nhỏ, đo overhead trước khi áp dụng toàn cục.

## 7. Tracing context khác MDC

MDC thường phục vụ log. Distributed tracing cần nhiều hơn một chuỗi `traceId`: nó quản lý trace/span hiện tại, quan hệ parent-child, sampling và propagation qua ranh giới process.

Trong hệ sinh thái Spring hiện đại, Micrometer Observation và Micrometer Tracing cung cấp instrumentation và propagation cho các context được hỗ trợ. Khi đi qua executor, dùng cơ chế context propagation tích hợp với observation/tracing để span hiện tại được tiếp tục đúng cách. Khi đi qua HTTP hoặc broker, dùng propagator theo chuẩn như W3C Trace Context và cấu hình header mapper/protocol tương ứng.

Không tự tạo một header `traceId` rồi xem đó là distributed tracing đầy đủ. Cũng không dùng Correlation ID nghiệp vụ thay thế Trace ID. Một đơn hàng có thể có cùng Correlation ID qua nhiều request, trong khi mỗi lần xử lý có thể tạo trace khác nhau.

| Giá trị | Phạm vi | Dùng để |
|---|---|---|
| Message ID | Một message | Tìm một lần chuyển giao message cụ thể |
| Correlation ID | Một nghiệp vụ hoặc nhóm message | Gom message con, reply hoặc các bước cùng nghiệp vụ |
| Trace ID | Một distributed trace | Nối các span qua thread và service |
| Span ID | Một operation trong trace | Xác định đoạn xử lý và quan hệ cha-con |

Khi log, có thể đưa trace/span ID vào MDC để truy vấn dễ hơn, nhưng hãy để tracing library quản lý context và lifecycle. Tránh tự đặt/xóa các key mà tracing instrumentation đang sở hữu.

## 8. SecurityContext và transaction không thể sao chép như MDC

### SecurityContext

Spring Security mặc định lưu `SecurityContext` trong `SecurityContextHolder` theo thread. Khi cần chạy task bất đồng bộ với danh tính người gọi, dùng cơ chế của Spring Security như `DelegatingSecurityContextAsyncTaskExecutor` hoặc wrapper tương ứng thay vì chỉ sao chép MDC.

Ví dụ:

~~~java
@Bean
AsyncTaskExecutor securedExecutor(ThreadPoolTaskExecutor delegate) {
    return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
}
~~~

Việc truyền security context cần theo nguyên tắc least privilege. Không giữ context của request lâu hơn cần thiết; nếu task được lưu queue và xử lý sau, hãy cân nhắc truyền một định danh người dùng/actor đã được xác thực trong message theo chính sách bảo mật, rồi kiểm tra quyền tại thời điểm xử lý.

### Transaction context

Transaction của Spring thường gắn với thread và resource hiện tại. Khi message chuyển qua `ExecutorChannel` hoặc poller executor, transaction của thread gửi không tự chuyển sang worker. Không copy `EntityManager`, JDBC connection hay transaction resource vào MDC/ThreadLocal của worker.

Nếu worker cần transaction, hãy mở transaction mới tại service được gọi trên worker bằng `@Transactional` qua Spring proxy, hoặc cấu hình transaction advice/poller phù hợp. Với message broker và database, cần thiết kế transaction/acknowledgment theo khả năng thực tế của từng resource. Context propagation không biến hai transaction thành một transaction phân tán.

### Request và locale context

`RequestContextHolder` và các object request thường gắn với vòng đời HTTP request. Không giữ `HttpServletRequest` hoặc session object để xử lý sau khi request đã kết thúc. Chỉ truyền các giá trị cần thiết, bất biến và đã được kiểm soát vào message header hoặc command object. Locale có thể được propagate nếu nghiệp vụ cần định dạng theo locale của người dùng, nhưng phải xác định rõ locale được lấy từ request hay từ cấu hình tenant.

## 9. Propagation qua Spring Integration channel và adapter

Để propagation hoạt động đúng, phải xem cả hai phía của ranh giới:

1. **Channel có đổi thread không?** Nếu có, executor cần decorator hoặc context propagation tương ứng.
2. **Message header có được giữ không?** Transformer, filter, router và adapter có thể tạo message mới hoặc lọc header.
3. **Có ranh giới process không?** ThreadLocal không đi qua broker/HTTP; cần serialize metadata vào header và khôi phục context ở phía nhận.
4. **Context có được xóa không?** Worker phải trả về trạng thái sạch sau mỗi task.

Ví dụ một flow có ranh giới executor:

~~~java
@Bean
IntegrationFlow orderFlow(MessageChannel asyncOrdersChannel,
                          OrderService orderService) {
    return IntegrationFlow.from("orders.input")
            .channel(asyncOrdersChannel)
            .handle(orderService, "process")
            .get();
}
~~~

Nếu `asyncOrdersChannel` là `ExecutorChannel`, endpoint xử lý sau channel chạy trên worker. Correlation ID vẫn nên có trong message header. Decorator của executor giúp context log/tracing cần thiết có mặt trong worker khi task được thực thi.

Với broker adapter, kiểm tra `DefaultHeaderMapper` hoặc header mapper tương ứng để biết header nào được gửi và nhận. Không truyền mọi header nội bộ một cách vô điều kiện: một số header chứa object không serialize được hoặc dữ liệu nhạy cảm. Chỉ whitelist metadata cần thiết, như correlation ID nghiệp vụ hoặc trace context theo chuẩn.

## 10. Kiểm thử context propagation

Kiểm thử propagation nên chứng minh cả hai điều: task nhận đúng context được submit và worker không giữ lại context sau khi task hoàn tất.

Một test có thể dùng executor một worker để buộc hai task dùng lại cùng thread:

~~~java
@Test
void propagatesMdcAndDoesNotLeakBetweenTasks() throws Exception {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(1);
    executor.setMaxPoolSize(1);
    executor.setQueueCapacity(10);
    executor.setTaskDecorator(new MdcTaskDecorator());
    executor.initialize();

    try {
        MDC.put("correlationId", "request-A");
        Future<String> first = executor.submit(
                () -> MDC.get("correlationId"));
        MDC.clear();

        assertEquals("request-A", first.get());

        Future<String> second = executor.submit(
                () -> MDC.get("correlationId"));
        assertNull(second.get());
    }
    finally {
        executor.shutdown();
        MDC.clear();
    }
}
~~~

Test minh họa kiểm tra snapshot ở thời điểm submit và xác nhận task tiếp theo không nhận nhầm context của task trước. Trong test thực tế, nên dùng `try/finally` để dọn MDC cả trên thread test, đặt timeout cho `Future.get(...)` và đảm bảo executor shutdown ngay cả khi assertion thất bại.

Các trường hợp nên kiểm thử thêm:

- Task chạy đồng bộ và bất đồng bộ cho cùng một message.
- Exception xảy ra trong worker nhưng MDC vẫn được dọn.
- Hai message có correlation ID khác nhau chạy liên tiếp trên cùng worker.
- Message đi qua transformer có tạo message mới và giữ header cần thiết.
- Context được truyền qua broker/HTTP theo header mapper và trace propagator.
- Security context được truyền bằng executor wrapper phù hợp và không rò rỉ principal sang task sau.
- Transaction trên worker là transaction đúng dự kiến, không phụ thuộc thread gửi.

## 11. Chẩn đoán khi context bị mất hoặc sai

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Log sau `ExecutorChannel` không có correlation ID | MDC không được propagate | Kiểm tra TaskDecorator trên đúng executor của channel |
| Log có correlation ID của request khác | Worker thread bị rò rỉ MDC hoặc decorator không restore/clear | Kiểm tra `finally`, task reuse và context snapshot |
| Message header có ID nhưng MDC trống | Header còn nhưng không có bước đưa header vào MDC | Đặt MDC tại handler/interceptor hoặc dùng accessor phù hợp |
| Trace bị tách thành root span mới | Trace context không được capture/propagate | Kiểm tra Micrometer Observation/Tracing, executor decorator và propagator |
| Principal mất sau async boundary | SecurityContext không được truyền | Dùng `DelegatingSecurityContextAsyncTaskExecutor` hoặc cơ chế tương ứng |
| Worker không tham gia transaction của producer | Transaction thread-bound | Mở transaction mới ở worker hoặc thiết kế ranh giới transaction khác |
| Context cũ còn sau khi message lỗi | Cleanup không nằm trong `finally` | Khôi phục/xóa context kể cả khi exception xảy ra |

Khi điều tra, log cả thread name, channel/endpoint name, message ID và Correlation ID. So sánh log trước và sau điểm chuyển thread để xác định context bị mất tại ranh giới nào. Đừng thêm propagation toàn cục trước khi biết context nào bị thiếu và executor nào thực sự được sử dụng.

## 12. Checklist thiết kế context propagation

- [ ] Đánh dấu các ranh giới đổi thread trong IntegrationFlow.
- [ ] Lưu dữ liệu nghiệp vụ cần theo message trong header hoặc payload.
- [ ] Dùng MDC chỉ như context phục vụ log và luôn cleanup/restore.
- [ ] Gắn `TaskDecorator` vào đúng executor dùng bởi `ExecutorChannel` hoặc poller.
- [ ] Dùng Micrometer Context Propagation khi cần nhiều loại context được hỗ trợ.
- [ ] Dùng cơ chế riêng của Spring Security cho `SecurityContext`.
- [ ] Mở transaction phù hợp trên worker; không cố copy transaction resource.
- [ ] Kiểm tra header mapper khi qua broker hoặc HTTP.
- [ ] Không truyền token, request object hoặc payload nhạy cảm chỉ để tiện logging.
- [ ] Test context bị mất, context bị rò rỉ và task thất bại trên thread pool tái sử dụng.

Thread context giúp code đồng bộ truy cập thông tin thuận tiện, nhưng nó không thay thế message metadata và không tự đi qua executor. Khi dùng message header cho dữ liệu nghiệp vụ, decorator hoặc context propagation cho dữ liệu gắn thread, và lifecycle cleanup rõ ràng, log và trace sẽ giữ được liên kết chính xác qua các ranh giới bất đồng bộ của Spring Integration.

## Tài liệu tham khảo

- [Spring Framework Reference: Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework API: TaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/TaskDecorator.html)
- [Spring Framework API: ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Spring Security Reference: Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
