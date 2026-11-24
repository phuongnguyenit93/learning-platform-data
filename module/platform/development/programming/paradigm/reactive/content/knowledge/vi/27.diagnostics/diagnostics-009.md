# Kiểm soát chi phí chẩn đoán và bảo vệ dữ liệu khi ghi log

Chẩn đoán giúp đội phát triển hiểu pipeline reactive đang chạy ra sao, nhưng mỗi lần ghi log, tạo stack trace, serialize payload hoặc gắn metric đều tiêu tốn tài nguyên. Một `Flux` có thể phát hàng nghìn phần tử mỗi giây; nếu ghi log toàn bộ từng phần tử, chi phí quan sát có thể làm thay đổi chính hành vi mà ta muốn quan sát. Log còn có thể chứa token, dữ liệu cá nhân, thông tin thanh toán hoặc nội dung nghiệp vụ không nên xuất hiện trong hệ thống lưu trữ tập trung.

Trong ứng dụng Java dùng Reactor, cần thiết kế chẩn đoán theo hai mục tiêu cùng lúc: thu thập đủ tín hiệu để tìm nguyên nhân và giữ chi phí ở mức có thể dự đoán; ghi lại thông tin cần thiết nhưng chỉ đưa dữ liệu đã được cho phép vào log. Các lựa chọn như `log()`, `doOnEach`, `checkpoint`, Micrometer Observation, sampling và structured logging nên được đặt đúng vị trí trong pipeline.

## 1. Chi phí chẩn đoán đến từ đâu?

Chẩn đoán không chỉ là thời gian gọi logger. Một event log có thể cần tạo object, lấy Context, định dạng chuỗi, serialize payload, ghi vào queue, truyền qua network và lưu trữ. Stack trace cũng cần thu thập thông tin call stack và giữ thêm dữ liệu trong bộ nhớ.

Các nhóm chi phí thường gặp:

| Thành phần | Chi phí có thể phát sinh | Khi nào đáng chú ý |
| --- | --- | --- |
| Ghi log từng tín hiệu | CPU, allocation, I/O, queue contention | `Flux` có throughput cao hoặc phát tín hiệu liên tục |
| Serialize payload | CPU, cấp phát bộ nhớ, tạo bản sao dữ liệu | Payload lớn, nested object hoặc log JSON |
| Stack trace | Thu thập call stack, giữ object và chuỗi dài | Bật operator debug toàn cục hoặc tạo exception thường xuyên |
| Metrics | CPU, cập nhật meter, số lượng time series | Gắn tag có cardinality cao |
| Tracing | Tạo span, truyền context, export telemetry | Nhiều span nhỏ hoặc tỷ lệ lấy mẫu quá cao |
| Logging bất đồng bộ | Queue, bộ nhớ đệm, thread xử lý và network | Log producer nhanh hơn appender hoặc collector |
| Log lỗi lặp lại | Dung lượng lưu trữ và thời gian tìm kiếm | Cùng một lỗi được ghi ở nhiều tầng |

Chi phí phụ thuộc throughput, kích thước dữ liệu, cấu hình logger, exporter và tải hệ thống. Không nên giả định một lời gọi `debug` là miễn phí chỉ vì log level hiện tại đang tắt: biểu thức dùng để tạo đối số vẫn được tính trước khi logger nhận lời gọi.

## 2. log() hữu ích khi phát triển, nhưng có thể quá ồn trong production

Reactor cung cấp toán tử `log()` để quan sát các tín hiệu như subscription, request, `onNext`, `onError`, `onComplete` và cancellation:

~~~java
Flux<Order> orders = orderRepository.findAll()
    .log("orders-pipeline");
~~~

Toán tử này rất hữu ích khi học hoặc điều tra một pipeline nhỏ. Nó giúp thấy subscriber yêu cầu bao nhiêu phần tử, nguồn phát gì và kết thúc bằng tín hiệu nào.

Trong production, `log()` có thể ghi quá nhiều dòng, đặc biệt khi đặt trên `Flux` dài hạn hoặc luồng có throughput cao. Nó cũng có thể in biểu diễn phần tử và exception mà không phù hợp với chính sách bảo vệ dữ liệu. Hãy giới hạn việc dùng `log()` vào test, môi trường phát triển hoặc một đoạn pipeline có lưu lượng thấp và thời gian quan sát ngắn.

Nếu chỉ cần biết một số mốc, dùng hook có mục tiêu rõ ràng:

~~~java
Flux<Order> orders = orderRepository.findAll()
    .doOnSubscribe(subscription -> log.debug("Bắt đầu đọc orders"))
    .doOnComplete(() -> log.debug("Đã đọc xong orders"))
    .doOnCancel(() -> log.debug("Consumer đã hủy đọc orders"))
    .doOnError(error -> log.warn("Đọc orders thất bại: {}", safeErrorCode(error)));
~~~

Các hook trên không biến lỗi thành kết quả khác; chúng chỉ quan sát lifecycle. Tuy vậy, mỗi hook vẫn có chi phí. Chỉ giữ những sự kiện giúp trả lời một câu hỏi vận hành cụ thể.

## 3. Tránh ghi log toàn bộ payload

Một lỗi phổ biến là đưa cả object vào logger:

~~~java
// Không nên: toString() có thể chứa nhiều trường không cần thiết.
log.debug("Received request: {}", request);
~~~

`toString()` có thể in email, số điện thoại, địa chỉ, token, cookie, nội dung biểu mẫu hoặc dữ liệu thanh toán. Nếu object thay đổi theo thời gian, một lần thêm field mới cũng có thể vô tình làm log lộ thêm dữ liệu.

Thay vào đó, hãy chọn trường theo allowlist và tạo event log nhỏ:

~~~java
log.debug(
    "Order accepted: orderId={}, itemCount={}, channel={}",
    safeOrderId(order.id()),
    order.items().size(),
    safeChannel(order.channel())
);
~~~

Chỉ ghi các trường cần để chẩn đoán. Ví dụ, `orderId` có thể được thay bằng mã tham chiếu nội bộ đã được phê duyệt; không cần ghi tên khách hàng, địa chỉ giao hàng hoặc nội dung thanh toán nếu chúng không giúp giải quyết sự cố.

### Allowlist tốt hơn blacklist

Blacklist cố gắng xóa các trường nhạy cảm đã biết. Khi DTO có thêm field mới, field đó có thể lọt vào log nếu bộ lọc không được cập nhật. Allowlist chỉ chọn những trường được phép ghi nên có hành vi an toàn hơn khi schema thay đổi.

Một DTO dành riêng cho log giúp giới hạn dữ liệu:

~~~java
record OrderLogEvent(
    String orderReference,
    String status,
    int itemCount
) {}

OrderLogEvent toLogEvent(Order order) {
    return new OrderLogEvent(
        safeOrderReference(order.id()),
        safeStatus(order.status()),
        order.items().size()
    );
}
~~~

Không dùng DTO nghiệp vụ đầy đủ làm DTO log. Tách riêng hai kiểu dữ liệu giúp reviewer nhìn thấy chính xác trường nào được phép rời khỏi tiến trình ứng dụng.

## 4. Redaction phải xảy ra trước khi dữ liệu được serialize

Redaction là quá trình che hoặc loại bỏ thông tin nhạy cảm trước khi ghi. Không nên ghi payload nguyên bản rồi trông chờ một hệ thống downstream xóa dữ liệu sau đó: log có thể đã đi qua queue, file tạm, collector hoặc bản sao lưu.

Ví dụ, nếu bắt buộc ghi một phần mã tham chiếu, hãy dùng hàm che có hợp đồng rõ ràng:

~~~java
String maskReference(String value) {
    if (value == null || value.length() < 4) {
        return "[redacted]";
    }
    return "..." + value.substring(value.length() - 4);
}
~~~

Hàm minh họa này chỉ phù hợp với một mã tham chiếu mà chính sách cho phép lộ bốn ký tự cuối. Không áp dụng cùng cách che cho mọi loại dữ liệu. Token, mật khẩu, session cookie và khóa bí mật nên bị loại hoàn toàn khỏi log.

Các loại dữ liệu thường phải loại bỏ hoặc xử lý đặc biệt:

- Password, API key, access token, refresh token, private key và secret.
- Header Authorization, cookie và session identifier.
- Số thẻ, mã bảo mật thanh toán và dữ liệu tài khoản.
- Thông tin định danh cá nhân, địa chỉ, email, số điện thoại.
- Nội dung request/response có thể chứa dữ liệu người dùng.
- Dữ liệu thuộc tenant hoặc khách hàng khác với phạm vi đang điều tra.

Không ghi dữ liệu nhạy cảm vào message exception, trace baggage hoặc tag metric với suy nghĩ rằng chỉ log mới cần bảo vệ. Metadata có thể được truyền sang nhiều hệ thống quan sát khác nhau.

## 5. Không dùng hash đơn giản để ẩn mọi định danh

Hash không tự động làm dữ liệu trở nên vô danh. Email, số điện thoại hoặc mã có không gian giá trị nhỏ có thể bị dò bằng cách hash danh sách giá trị phổ biến rồi so sánh. Nếu cần liên kết cùng một định danh qua nhiều log mà không lưu giá trị gốc, hãy dùng tokenization hoặc HMAC với khóa bí mật được quản lý an toàn, theo chính sách của tổ chức.

Không tự tạo thuật toán mã hóa hoặc HMAC trong logger. Nên dùng một dịch vụ/tiện ích bảo vệ dữ liệu đã được phê duyệt và chỉ phát ra mã tham chiếu không thể đảo ngược bởi người đọc log thông thường. Hãy cân nhắc rằng mã giả danh vẫn có thể là dữ liệu cá nhân nếu có khả năng liên kết trở lại một người.

## 6. Ghi lỗi có chọn lọc và tránh log lặp

Một lỗi có thể đi qua repository, service, controller và error handler toàn cục. Nếu mọi tầng đều ghi stack trace, một sự cố có thể tạo nhiều bản log giống nhau. Điều này làm tăng chi phí và che khuất log hữu ích.

Một nguyên tắc thực tế:

- Tầng thấp thêm ngữ cảnh vào exception hoặc ánh xạ sang lỗi miền nghiệp vụ, nhưng không nhất thiết ghi stack trace.
- Tầng xử lý lỗi sở hữu request hoặc operation ghi một log đầy đủ ở mức phù hợp.
- Tầng trả response không ghi lại cùng lỗi lần nữa nếu đã được ghi tại error boundary.
- Lỗi dự kiến của nghiệp vụ có thể được ghi ở mức info hoặc warn với error code; lỗi bất ngờ cần stack trace ở một nơi có kiểm soát.

Ví dụ ánh xạ lỗi và ghi tại ranh giới:

~~~java
Mono<Order> loadOrder(String id) {
    return orderRepository.findById(id)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
        .onErrorMap(DatabaseException.class,
            error -> new OrderLookupException("ORDER_LOOKUP_FAILED", error));
}

Mono<ServerResponse> handleError(Throwable error) {
    log.error(
        "Request xử lý thất bại: code={}, cause={}",
        safeErrorCode(error),
        safeCauseSummary(error)
    );
    return ServerResponse.status(statusFor(error)).build();
}
~~~

Đây là phác thảo; cách lấy cause và ghi stack trace cần theo cấu hình logger của ứng dụng. Không đưa raw SQL, bind parameter hoặc toàn bộ response body vào exception message. Một lỗi database có thể chứa câu truy vấn, tên schema hoặc dữ liệu đầu vào.

`doOnError` chỉ quan sát lỗi, không phục hồi nó. Hãy để lỗi tiếp tục đi đến error handler phù hợp và tránh vừa log stack trace vừa nuốt lỗi thành `Mono.empty()` khiến vận hành tưởng rằng request thành công.

## 7. Kiểm tra log level trước khi tạo dữ liệu đắt tiền

Logger có API tham số thường tránh format chuỗi khi level bị tắt:

~~~java
log.debug("Order {} changed to {}", orderId, status);
~~~

Nhưng biểu thức đối số vẫn được tính trước khi gọi logger. Nếu `expensiveSnapshot(order)` serialize một object lớn, công việc đó vẫn chạy dù DEBUG bị tắt.

~~~java
if (log.isDebugEnabled()) {
    log.debug("Order snapshot: {}", safeSnapshot(order));
}
~~~

Guard này tránh tạo snapshot khi DEBUG không bật. Tuy nhiên, `safeSnapshot` vẫn phải áp dụng allowlist và redaction; bật DEBUG trong production không phải lý do để ghi toàn bộ payload.

Không tính hash, serialize JSON hoặc dựng stack trace chỉ để truyền vào một log statement có thể đang bị tắt. Hãy đo chi phí của các hàm hỗ trợ logging nếu chúng xử lý object lớn hoặc chạy thường xuyên.

## 8. Tránh công việc blocking trong callback chẩn đoán

Các callback như `doOnNext`, `doOnEach`, `doOnError` thường chạy trên thread phát tín hiệu. Với WebFlux, thread đó có thể là event-loop. Nếu callback thực hiện serialize lớn, gọi dịch vụ log từ xa đồng bộ, ghi file blocking hoặc chờ lock lâu, nó có thể làm chậm nhiều request khác.

~~~java
Flux<Event> events = eventSource.events()
    .doOnNext(event -> {
        // Chỉ trích xuất một số trường nhỏ, đã được cho phép.
        log.debug("Event received: type={}", safeEventType(event));
    });
~~~

Không thực hiện các thao tác sau ngay trong callback trên event-loop:

- Gọi HTTP đồng bộ đến log collector.
- Ghi file bằng API blocking.
- Serialize toàn bộ object graph.
- Chờ Future.get() hoặc gọi block().
- Lấy lock có thể bị giữ lâu.

Dùng logging framework có appender bất đồng bộ được cấu hình phù hợp hoặc gửi event nhỏ đến một pipeline quan sát riêng. Logging bất đồng bộ vẫn có chi phí queue và thread; nếu producer nhanh hơn consumer, queue cần giới hạn và có chính sách khi đầy. Không để queue không giới hạn biến log thành một nguồn tăng bộ nhớ.

## 9. Sampling log cho luồng có throughput cao

Với một `Flux` phát nhiều sự kiện tương tự, ghi từng phần tử có thể không tạo thêm thông tin chẩn đoán tương xứng. Sampling giảm số log bằng cách chỉ ghi một phần sự kiện, ví dụ một trong mỗi N phần tử hoặc một tỷ lệ nhỏ theo request.

Ví dụ lấy một log cho mỗi 1.000 phần tử trong từng subscription:

~~~java
Flux<Event> sampledLogs = Flux.defer(() -> {
    AtomicLong count = new AtomicLong();

    return eventSource.events()
        .doOnNext(event -> {
            long current = count.incrementAndGet();
            if (current % 1_000 == 0) {
                log.debug(
                    "Processed event sample: count={}, type={}",
                    current,
                    safeEventType(event)
                );
            }
        });
});
~~~

`defer` tạo bộ đếm riêng cho mỗi subscription. Ví dụ này vẫn kiểm tra một bộ đếm trên mỗi phần tử, nhưng tránh serialize và ghi log cho phần lớn event. Với hệ thống nhiều subscription, hãy cân nhắc cách tổng hợp counter bằng metric thay vì tạo log định kỳ từ từng stream.

Sampling không phù hợp với audit log, sự kiện bảo mật bắt buộc ghi nhận hoặc giao dịch cần bằng chứng đầy đủ. Cũng không nên lấy mẫu lỗi nghiêm trọng một cách tùy tiện. Một chính sách thường hữu ích là:

- Giữ lại tất cả lỗi nghiêm trọng và sự kiện bảo mật bắt buộc.
- Sampling các sự kiện thành công có tần suất cao.
- Ghi metric tổng số, số lỗi và số bị lấy mẫu để thấy quy mô thực tế.
- Gắn sampling rate vào metadata của log để người phân tích hiểu dữ liệu không đầy đủ.

Nếu chọn mẫu theo tỷ lệ, dùng một quyết định ổn định theo request/trace khi cần các log của cùng một request được giữ cùng nhau. Tránh lấy mẫu ngẫu nhiên độc lập từng dòng nếu điều đó làm mất mối liên hệ giữa các bước.

## 10. Dùng checkpoint có mục tiêu thay vì bật debug toàn cục

Khi pipeline phát lỗi, stack trace thông thường có thể chỉ ra vị trí exception được tạo mà không cho thấy đầy đủ nơi pipeline được lắp ráp. Reactor cung cấp `checkpoint` để bổ sung dấu mốc chẩn đoán:

~~~java
Mono<Order> order = orderRepository.findById(orderId)
    .checkpoint("order-service.find-order");
~~~

`checkpoint(String)` thêm mô tả giúp nhận diện vị trí trong assembly traceback mà không chủ động thu thập stack trace đầy đủ như chế độ force stack trace. Khi cần stack trace tại checkpoint, có overload `checkpoint(description, true)`, nhưng nó tốn chi phí hơn.

`Hooks.onOperatorDebug()` bật chế độ ghi nhận assembly stack trace rộng hơn cho các operator được lắp ráp sau khi hook được bật. Cách này có thể rất hữu ích khi điều tra một lỗi khó tái hiện trong môi trường phát triển, nhưng overhead có thể đáng kể vì stack trace được thu thập ở nhiều điểm.

Khuyến nghị:

- Dùng `checkpoint("mô tả ổn định")` tại ranh giới service hoặc đoạn pipeline khó chẩn đoán.
- Chỉ dùng checkpoint force stack trace cho khu vực thật sự cần thiết.
- Bật `Hooks.onOperatorDebug()` có giới hạn trong môi trường phát triển hoặc một phiên điều tra có kiểm soát.
- Nếu bật hook toàn cục, bảo đảm cấu hình được áp dụng trước khi các pipeline cần chẩn đoán được lắp ráp.
- Không bật operator debug toàn cục mặc định cho workload production có throughput cao nếu chưa đo overhead.

Không thêm checkpoint ở mọi toán tử theo thói quen. Một vài mốc có tên rõ ràng thường hữu ích hơn một stack trace dài khó đọc.

## 11. Metrics và tracing thay thế log từng phần tử

Log trả lời “điều gì đã xảy ra ở request này?”. Metric trả lời “hệ thống đang hoạt động thế nào qua thời gian?”. Tracing trả lời “một request đi qua những thành phần nào và mất bao lâu ở mỗi bước?”.

Với pipeline reactive, nên dùng:

- **Metrics** cho throughput, error rate, latency, số subscription, số cancellation và kích thước hàng đợi.
- **Tracing/Observation** cho hành trình qua HTTP client, service, database và message broker.
- **Logs** cho sự kiện quan trọng, lỗi cần điều tra và thông tin ngữ cảnh đã được cho phép.

Không cần log mọi `onNext` để biết throughput. Một counter hoặc timer có thể cung cấp số liệu tổng hợp với chi phí thấp hơn nhiều so với hàng nghìn dòng log.

### Tránh cardinality cao trong metric tag

Không dùng các giá trị thay đổi theo request làm tag metric:

- request ID, trace ID hoặc span ID.
- user ID, email hoặc tenant ID tùy biến.
- URL đầy đủ có path variable hoặc query string.
- exception message hoặc SQL text.

Mỗi tổ hợp tag có thể tạo một time series riêng, làm tăng bộ nhớ và chi phí của metrics backend. Dùng nhãn có tập giá trị giới hạn như `operation`, `outcome`, `client`, `error_code` đã chuẩn hóa hoặc `status_class`.

Trace ID và request ID có thể hữu ích trong log đã kiểm soát quyền truy cập, nhưng không nên đưa chúng vào metric labels. Không đưa secret hoặc dữ liệu cá nhân vào trace baggage chỉ để tiện tìm kiếm.

## 12. Đặt tên và cấu trúc log nhất quán

Structured logging giúp truy vấn theo trường mà không cần phân tích chuỗi message. Một log event nên có các trường có ý nghĩa và kiểu dữ liệu ổn định:

~~~java
log.atInfo()
    .addKeyValue("event", "order.created")
    .addKeyValue("orderRef", safeOrderReference(order.id()))
    .addKeyValue("itemCount", order.items().size())
    .addKeyValue("outcome", "success")
    .log("Order created");
~~~

API fluent như trên phụ thuộc logging backend và phiên bản SLF4J. Nếu ứng dụng không hỗ trợ key-value logging, dùng DTO log an toàn hoặc message có cấu trúc thống nhất.

Một schema log hữu ích thường có:

- timestamp, level, service và environment.
- event hoặc operation với tên ổn định.
- outcome hoặc error_code chuẩn hóa.
- trace_id/request_id nếu chính sách cho phép.
- Mã tham chiếu nghiệp vụ đã được che hoặc giả danh.

Không đưa toàn bộ HTTP headers, query parameters hoặc exception object vào structured field một cách tự động. Structured logging không tự làm dữ liệu an toàn; nó chỉ khiến dữ liệu dễ truy vấn hơn.

## 13. Bảo vệ log ở toàn bộ vòng đời

Chính sách bảo vệ dữ liệu không kết thúc ở logger. Log có thể được lưu trong container, file, queue, collector, kho tìm kiếm, bản sao lưu và hệ thống cảnh báo.

Hãy xác định:

1. **Thu thập:** trường nào được phép ghi và ai chịu trách nhiệm redaction?
2. **Truyền tải:** log có được mã hóa khi truyền tới collector không?
3. **Lưu trữ:** retention phù hợp với mục đích và yêu cầu tổ chức là bao lâu?
4. **Truy cập:** ai được tìm kiếm, tải xuống hoặc chia sẻ log?
5. **Xuất dữ liệu:** dashboard, ticket và bản chụp log có thể làm lộ dữ liệu không?
6. **Xóa:** log hết hạn và bản sao lưu được xử lý theo chính sách nào?

Không ghi secret rồi chỉ dựa vào retention ngắn. Nếu secret đã xuất hiện trong log, cần đánh giá phạm vi truy cập và khả năng phải rotate credential. Không dùng log production có dữ liệu thật để chia sẻ trong issue công khai hoặc ví dụ tài liệu.

## 14. Kiểm thử redaction và giới hạn dữ liệu log

Logic tạo log event an toàn nên là một thành phần có thể kiểm thử độc lập. Ví dụ:

~~~java
record SafePaymentLog(String paymentRef, String outcome) {}

SafePaymentLog toSafeLog(Payment payment) {
    return new SafePaymentLog(
        maskReference(payment.reference()),
        safeOutcome(payment.status())
    );
}
~~~

Test xác minh trường nhạy cảm không xuất hiện:

~~~java
@Test
void safeLogDoesNotContainPaymentSecret() {
    Payment payment = new Payment(
        "PAY-12345678",
        "4111111111111111",
        "secret-token",
        "APPROVED"
    );

    SafePaymentLog safe = toSafeLog(payment);
    String serialized = serializeForTest(safe);

    assertFalse(serialized.contains("4111111111111111"));
    assertFalse(serialized.contains("secret-token"));
    assertTrue(serialized.contains("APPROVED"));
}
~~~

`serializeForTest` đại diện cho serializer được ứng dụng dùng. Test nên dùng dữ liệu giả, không dùng secret production. Nếu chính sách yêu cầu loại bỏ một trường hoàn toàn, kiểm tra rằng field không tồn tại trong output thay vì chỉ kiểm tra nó đã được che.

Ngoài unit test cho redactor, có thể thêm test tích hợp cho appender hoặc log encoder để bảo đảm dữ liệu không bị thêm lại ở bước serialize. Kiểm tra cả exception message, MDC và structured fields vì thông tin nhạy cảm có thể lọt qua những đường khác nhau.

## 15. Những lỗi thường gặp

- **Ghi toàn bộ object bằng toString():** schema thay đổi có thể làm lộ field mới; dùng allowlist và DTO log riêng.
- **Serialize trước khi kiểm tra log level:** tốn CPU và bộ nhớ dù log không được ghi.
- **Ghi mọi tín hiệu bằng log():** tạo log volume lớn, tăng I/O và có thể lộ payload.
- **Dùng blacklist làm cơ chế duy nhất:** field mới có thể lọt qua; ưu tiên allowlist.
- **Che dữ liệu sau khi ghi:** bản gốc có thể đã được chuyển tới queue, file hoặc collector.
- **Dùng hash thường cho email hoặc số điện thoại:** dữ liệu có miền giá trị nhỏ có thể bị dò; dùng tokenization/HMAC được phê duyệt khi cần liên kết giả danh.
- **Ghi stack trace ở mọi tầng:** cùng lỗi xuất hiện nhiều lần và làm tăng chi phí lưu trữ.
- **Gọi dịch vụ log đồng bộ trong doOnNext:** có thể chặn event-loop và làm giảm throughput.
- **Dùng queue log không giới hạn:** log producer nhanh hơn consumer có thể làm heap tăng.
- **Sampling audit/security event:** có thể mất bằng chứng bắt buộc; chỉ sampling dữ liệu được phép lấy mẫu.
- **Bật Hooks.onOperatorDebug() toàn cục không đo trước:** stack trace assembly có thể tạo overhead lớn.
- **Gắn request ID hoặc user ID vào metric tag:** cardinality tăng nhanh và làm backend metrics quá tải.
- **Đưa secret vào trace baggage hoặc exception message:** dữ liệu có thể lan sang nhiều hệ thống quan sát.
- **Chỉ test redactor mà không test encoder:** serializer hoặc MDC vẫn có thể thêm trường nhạy cảm vào log cuối cùng.

## 16. Quy trình chọn tín hiệu chẩn đoán

Trước khi thêm log, metric hoặc checkpoint, hãy trả lời:

1. Câu hỏi vận hành nào cần được trả lời bằng tín hiệu này?
2. Có thể dùng metric hoặc trace thay cho log từng phần tử không?
3. Log có ghi payload hay chỉ ghi mã tham chiếu và trạng thái cần thiết?
4. Trường nào được allowlist, trường nào phải loại bỏ hoặc che?
5. Việc tạo đối số, serialize hoặc stack trace có chi phí đáng kể không?
6. Callback có chạy trên event-loop hoặc thread xử lý tín hiệu quan trọng không?
7. Có thể sampling sự kiện thành công mà vẫn giữ lỗi và audit event không?
8. Metric tag có cardinality thấp và ổn định không?
9. Lỗi có đang bị ghi lặp ở nhiều tầng không?
10. Log được bảo vệ, lưu giữ và cấp quyền truy cập theo chính sách nào?
11. Test có xác minh redaction ở cả DTO và output serializer không?

Chẩn đoán tốt cần đủ thông tin nhưng không làm pipeline trở nên chậm, ồn hoặc rò rỉ dữ liệu. Dùng `log()` cho điều tra có phạm vi; dùng hook có mục tiêu cho lifecycle; dùng `checkpoint` tại các ranh giới quan trọng thay vì bật stack trace toàn cục; dùng metrics và tracing để quan sát xu hướng thay cho log từng phần tử. Với nội dung log, ưu tiên allowlist, DTO riêng, redaction trước serialize và một điểm ghi lỗi có trách nhiệm rõ ràng. Kết hợp sampling phù hợp, metric tag cardinality thấp, queue có giới hạn và kiểm thử encoder sẽ giúp hệ thống quan sát được pipeline reactive mà vẫn kiểm soát chi phí và bảo vệ dữ liệu.
