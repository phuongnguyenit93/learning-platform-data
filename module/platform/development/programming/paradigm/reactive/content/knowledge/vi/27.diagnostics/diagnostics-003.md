# checkpoint và thông tin lắp ráp phục vụ tìm lỗi

Trong **REACTIVE_PROGRAMMING**, `Mono` và `Flux` mô tả pipeline bất đồng bộ theo hợp đồng `Publisher–Subscriber`, có demand, cancellation, scheduler và các tín hiệu lỗi. Khi một pipeline dài phát sinh lỗi, stack trace thông thường đôi khi chỉ cho thấy nơi lỗi được quan sát hoặc nơi callback được thực thi. Nó có thể không chỉ ra đoạn code đã lắp ráp operator gây ra lỗi.

Reactor cung cấp **assembly tracing** để bổ sung thông tin về nơi Publisher được tạo và các operator được ghép. `checkpoint` đánh dấu những vị trí quan trọng trong pipeline; `Hooks.onOperatorDebug()` bật chế độ ghi nhận assembly trace trên diện rộng. Kết hợp các dấu mốc này với tên pipeline, metadata và kiểm thử giúp xác định lỗi nằm ở bước biến đổi, ghép luồng, scheduler hay ranh giới I/O.

## 1. Phân biệt assembly, subscription và execution

Để hiểu checkpoint, trước hết cần phân biệt ba thời điểm trong vòng đời Publisher:

1. **Assembly:** ứng dụng gọi các operator như `map`, `filter`, `flatMap`, `publishOn` để tạo một Publisher mới. Chưa có Subscriber nhận dữ liệu chỉ vì pipeline được lắp ráp.
2. **Subscription:** một Subscriber đăng ký vào Publisher. Reactive Streams thiết lập `Subscription`, sau đó Subscriber có thể yêu cầu demand hoặc cancel.
3. **Execution:** các tín hiệu `onNext`, `onError`, `onComplete` và các callback thực tế chạy theo lịch thực thi của nguồn và scheduler.

```text
Assembly                         Subscription / Execution
---------                        -------------------------
source                            subscribe()
  .map(...)                            |
  .flatMap(...)                        v
  .publishOn(...)                 onSubscribe
  .checkpoint(...)                    |
       |                              request(n)
       |                              |
       v                              v
 Publisher được tạo              onNext / onError / onComplete
```

Assembly trace trả lời câu hỏi “Publisher/operator này được tạo ở đâu?”. Stack trace thực thi trả lời câu hỏi “lỗi đang được ném hoặc quan sát ở đâu?”. Hai vị trí có thể khác nhau, nhất là khi callback chạy trên thread khác hoặc pipeline được tạo trong một service rồi subscribe ở tầng web.

Ví dụ, một service lắp ráp pipeline:

```java
Mono<Invoice> loadInvoice(String id) {
    return invoiceClient.fetch(id)
        .map(this::normalize)
        .flatMap(this::enrich)
        .checkpoint("invoice-service: load and enrich");
}
```

Publisher được lắp ráp khi `loadInvoice` được gọi. Khi một controller subscribe, quá trình thực thi mới bắt đầu. Nếu lỗi phát sinh trong phần upstream của checkpoint, assembly information có thể giúp truy ngược vị trí tạo chuỗi operator này.

## 2. Stack trace thông thường có thể thiếu ngữ cảnh lắp ráp

Một pipeline reactive có thể chạy qua nhiều operator và chuyển thread bằng `publishOn` hoặc `subscribeOn`. Khi callback ném exception, stack trace thường phản ánh đường gọi tại thời điểm thực thi. Các frame của framework và scheduler có thể chiếm phần lớn stack, trong khi dòng code tạo pipeline ban đầu không còn xuất hiện rõ.

Ví dụ:

```java
Flux<Integer> parsed = Flux.just("12", "not-a-number", "30")
    .map(Integer::parseInt)
    .publishOn(Schedulers.parallel())
    .map(value -> 100 / value);
```

`Integer.parseInt` có thể ném `NumberFormatException`. Nếu chỉ xem stack trace thực thi, ta có thể thấy frame của `FluxMap`, operator fuseable hoặc scheduler. Assembly tracing bổ sung dấu vết về nơi `map` và các operator liên quan được lắp ráp.

Assembly trace không thay thế stack trace gốc. Nó bổ sung thông tin để liên hệ lỗi runtime với đoạn code tạo Publisher.

## 3. Dùng checkpoint để đánh dấu ranh giới nghiệp vụ

`checkpoint` là operator được đặt trong pipeline để thêm thông tin assembly khi lỗi đi qua vị trí đó. Có thể đặt mô tả dễ tìm:

```java
Flux<Integer> parsed = Flux.just("12", "not-a-number", "30")
    .map(Integer::parseInt)
    .checkpoint("invoice-import: parse amount");
```

Khi lỗi `NumberFormatException` đi qua checkpoint, Reactor có thể gắn thông tin checkpoint vào exception dưới dạng thông tin suppressed/assembly. Khi log lỗi đầy đủ, mô tả `invoice-import: parse amount` giúp xác định pipeline và bước nghiệp vụ liên quan.

Nên dùng tên có ý nghĩa và ổn định, ví dụ:

- `orders: validate incoming event`
- `payments: call authorization provider`
- `inventory: reserve stock`
- `reporting: aggregate daily totals`

Tránh mô tả quá chung như `checkpoint-1`, vì nó không giúp người đọc nhận ra ranh giới nghiệp vụ.

## 4. Checkpoint nhẹ và checkpoint có stack trace

Reactor cung cấp các overload với chi phí khác nhau:

| Cách gọi | Thông tin bổ sung | Chi phí tương đối |
|---|---|---|
| `checkpoint()` | Ghi nhận assembly trace kèm stack trace tại vị trí lắp ráp | Cao hơn do thu thập stack trace |
| `checkpoint("description")` | Đánh dấu checkpoint bằng mô tả, không thu thập stack trace đầy đủ | Nhẹ hơn |
| `checkpoint("description", true)` | Có mô tả và buộc thu thập stack trace | Cao hơn |

Ví dụ dùng checkpoint nhẹ tại các ranh giới nghiệp vụ:

```java
Mono<PaymentResult> payment = paymentRequest(command)
    .checkpoint("payment: build request")
    .flatMap(paymentClient::authorize)
    .checkpoint("payment: authorize with provider")
    .flatMap(this::persistResult)
    .checkpoint("payment: persist authorization result");
```

Các checkpoint có mô tả giúp nhận diện nơi lỗi đi qua. Nếu cần biết chính xác call site trong code, có thể bật stack trace ở một vị trí nghi vấn:

```java
Mono<PaymentResult> payment = paymentRequest(command)
    .flatMap(paymentClient::authorize)
    .checkpoint("payment: provider authorization", true);
```

Không nên mặc định buộc stack trace ở mọi checkpoint trong luồng có lưu lượng lớn. Thu thập stack trace có chi phí CPU và bộ nhớ, nên ưu tiên mô tả nhẹ hoặc bật stack trace có chọn lọc trong quá trình điều tra.

## 5. Vị trí đặt checkpoint quyết định lỗi nào được đánh dấu

Checkpoint quan sát lỗi đi qua vị trí của nó. Do đó, vị trí đặt checkpoint ảnh hưởng đến phạm vi operator mà nó có thể giúp chẩn đoán.

```java
Flux<Order> orders = source
    .map(this::normalize)
    .checkpoint("orders: after normalization")
    .flatMap(this::loadCustomer)
    .checkpoint("orders: after customer lookup")
    .map(this::toView);
```

Checkpoint thứ nhất có thể đánh dấu lỗi phát sinh ở `source` hoặc `normalize` khi lỗi đi qua nó. Checkpoint thứ hai bao phủ đoạn upstream gồm cả bước tra cứu khách hàng. Lỗi phát sinh ở `toView`, là operator phía downstream sau checkpoint thứ hai, không đi ngược qua checkpoint đó; nếu muốn đánh dấu lỗi của toàn chuỗi, có thể đặt thêm checkpoint ở cuối:

```java
Flux<OrderView> views = source
    .map(this::normalize)
    .flatMap(this::loadCustomer)
    .map(this::toView)
    .checkpoint("orders: complete view pipeline");
```

Một checkpoint cuối pipeline thường hữu ích để xác định call site lắp ráp của cả chuỗi. Các checkpoint trung gian hữu ích hơn khi muốn thu hẹp phạm vi theo từng bước. Không cần đặt checkpoint sau mọi operator; chọn ranh giới có ý nghĩa để thông tin lỗi dễ đọc.

## 6. Bật assembly tracing toàn cục với Hooks.onOperatorDebug

Khi chưa biết lỗi nằm trong pipeline nào, có thể bật chế độ debug toàn cục:

```java
Hooks.onOperatorDebug();

// Sau đó mới lắp ráp các Mono/Flux cần theo dõi.
Mono<Result> result = service.loadData()
    .map(this::transform);
```

`Hooks.onOperatorDebug()` yêu cầu Reactor ghi nhận thông tin assembly cho các operator được lắp ráp sau khi hook được bật. Vì vậy, cần kích hoạt nó sớm trước khi ứng dụng tạo các Publisher cần chẩn đoán. Bật hook sau khi pipeline đã được tạo không bổ sung ngược assembly trace cho những Publisher cũ.

Chế độ toàn cục có thể làm tăng chi phí lắp ráp và sử dụng bộ nhớ vì stack trace được thu thập trên diện rộng. Nên dùng trong môi trường phát triển, kiểm thử hoặc một phiên điều tra có kiểm soát; không bật vô điều kiện cho mọi request production có throughput cao.

Khi cần tắt hook trong test hoặc môi trường dùng chung:

```java
Hooks.resetOnOperatorDebug();
```

Đặt việc bật/tắt hook trong lifecycle rõ ràng. Tránh để test này bật hook toàn cục rồi ảnh hưởng đến test khác.

## 7. Đọc thông tin assembly trong exception

Khi một lỗi đi qua checkpoint hoặc assembly-debug hook, Reactor có thể gắn `OnAssemblyException` vào exception dưới dạng suppressed exception. Thông tin này thường chứa:

- Operator hoặc Publisher đã được lắp ráp.
- Vị trí assembly trace trong source code nếu có stack trace.
- Danh sách checkpoint có mô tả đã đi qua.
- Đường liên kết giữa lỗi runtime và chuỗi operator.

Định dạng hiển thị cụ thể có thể thay đổi theo phiên bản Reactor và cách logger in exception. Khi điều tra, hãy log exception đầy đủ, gồm cả suppressed exceptions, thay vì chỉ log `error.getMessage()`:

```java
Mono<Result> result = service.loadData()
    .checkpoint("reporting: load source data");

result.doOnError(error ->
    log.error("Reactive reporting pipeline failed", error)
);
```

Logger nhận cả throwable để có thể in stack trace và thông tin suppressed. Nếu chỉ ghi message, assembly trace có thể không xuất hiện trong log.

Không nên parse nội dung stack trace để điều khiển nghiệp vụ. Assembly information dành cho chẩn đoán; logic retry, fallback hoặc mapping lỗi cần dựa trên loại exception và hợp đồng nghiệp vụ.

## 8. Kết hợp checkpoint với name và tag

Checkpoint giúp truy nguyên assembly khi có lỗi. `name` và `tag` cung cấp metadata để nhận diện một Publisher trong công cụ introspection hoặc instrumentation:

```java
Flux<Event> events = eventSource()
    .name("order-event-stream")
    .tag("component", "order-service")
    .tag("stream", "incoming-events")
    .checkpoint("order-service: consume incoming events");
```

Có thể đọc metadata bằng `Scannable`:

```java
Scannable scan = Scannable.from(events);

String pipelineName = scan.name();
scan.tags().forEach(tag ->
    log.debug("Pipeline tag {}={}", tag.getT1(), tag.getT2())
);
```

`name` và `tag` không tự tạo stack trace và không thay thế checkpoint. Chúng giúp đặt nhãn cho pipeline; checkpoint bổ sung assembly information khi lỗi đi qua vị trí đánh dấu.

Không đưa token, thông tin xác thực, dữ liệu cá nhân hoặc payload nhạy cảm vào tag hay description. Metadata chẩn đoán có thể xuất hiện trong log, metrics hoặc công cụ quan sát.

## 9. Assembly trace không tự chỉ ra nguyên nhân gốc

Checkpoint giúp tìm nơi Publisher được lắp ráp, nhưng không tự giải thích tại sao lỗi xảy ra. Ví dụ, checkpoint có thể cho biết lỗi đi qua `payments: authorize with provider`; nguyên nhân gốc vẫn có thể là timeout, dữ liệu đầu vào sai, dịch vụ từ xa trả lỗi hoặc một bug trong mapper.

Khi đọc lỗi, nên kết hợp nhiều lớp thông tin:

1. **Exception gốc:** loại lỗi, message, cause và suppressed exceptions.
2. **Assembly trace:** pipeline được lắp ráp ở đâu và checkpoint nào đã đi qua.
3. **Signal context:** lỗi xuất hiện ở bước nào, sau bao nhiêu phần tử hoặc sau bao lâu.
4. **Correlation/trace ID:** request hoặc event nào đã kích hoạt subscription.
5. **Metrics:** timeout, retry, cancellation, queue và latency tại thời điểm xảy ra lỗi.

Ví dụ, một `TimeoutException` đi qua checkpoint của HTTP client chỉ cho biết request không hoàn tất trong deadline. Cần thêm metrics connection pool, connect latency, response latency và trace phân tán để xác định request chờ ở pool, mạng hay service từ xa.

## 10. Kiểm thử lỗi và checkpoint bằng StepVerifier

`StepVerifier` giúp xác minh tín hiệu lỗi của pipeline. Không nên khóa test vào toàn bộ nội dung stack trace vì định dạng assembly trace có thể thay đổi giữa các phiên bản Reactor.

```java
Flux<Integer> parsed = Flux.just("10", "invalid", "30")
    .map(Integer::parseInt)
    .checkpoint("import: parse integer values");

StepVerifier.create(parsed)
    .expectNext(10)
    .expectError(NumberFormatException.class)
    .verify();
```

Test xác minh phần tử đầu được phát rồi pipeline kết thúc bằng `NumberFormatException`. Checkpoint bổ sung assembly context để người phát triển xem khi test thất bại hoặc log exception đầy đủ.

Nếu muốn kiểm tra thông tin chẩn đoán cụ thể, có thể dùng `expectErrorSatisfies` để kiểm tra loại lỗi, cause hoặc các thuộc tính ổn định mà ứng dụng kiểm soát. Tránh khẳng định chính xác số dòng hoặc toàn bộ chuỗi stack trace vì chúng phụ thuộc compiler, phiên bản thư viện và cấu trúc build.

## 11. Kiểm thử chế độ debug toàn cục an toàn

`Hooks.onOperatorDebug()` là hook toàn cục, nên test phải khôi phục trạng thái sau khi chạy. Có thể bật trước khi lắp ráp Publisher và reset trong `finally`:

```java
try {
    Hooks.onOperatorDebug();

    Flux<Integer> pipeline = Flux.just("1", "x")
        .map(Integer::parseInt);

    StepVerifier.create(pipeline)
        .expectNext(1)
        .expectError(NumberFormatException.class)
        .verify();
} finally {
    Hooks.resetOnOperatorDebug();
}
```

Trong bộ test chạy song song, hook toàn cục có thể ảnh hưởng test khác. Nên cô lập nhóm test này, tránh thay đổi hook trong khi các test khác đang lắp ráp Publisher hoặc dùng checkpoint cục bộ nếu chỉ cần đánh dấu một pipeline.

## 12. Phân biệt checkpoint với log và doOnError

Ba cơ chế có mục đích khác nhau:

| Cơ chế | Trả lời câu hỏi | Tác động lên pipeline |
|---|---|---|
| `checkpoint` | Publisher/operator được lắp ráp ở đâu? | Bổ sung assembly information cho lỗi đi qua checkpoint |
| `doOnError` | Lỗi nào vừa đi qua vị trí này? | Quan sát lỗi; không tự phục hồi |
| Logging/metrics | Lỗi xảy ra bao nhiêu lần, trong ngữ cảnh nào? | Ghi nhận thông tin quan sát; callback cần ngắn và an toàn |

Có thể kết hợp chúng:

```java
Mono<Receipt> receipt = createReceipt(command)
    .checkpoint("orders: create receipt")
    .doOnError(error ->
        log.error("Create receipt failed, orderId={}", command.orderId(), error)
    );
```

Checkpoint cung cấp vị trí lắp ráp; `doOnError` ghi nhận lỗi và metadata nghiệp vụ. Nếu cần fallback, dùng `onErrorResume` ở vị trí phù hợp. Không nhầm việc ghi log hoặc thêm checkpoint với việc xử lý lỗi.

## 13. Khi nào nên dùng từng mức chẩn đoán?

| Tình huống | Cách tiếp cận |
|---|---|
| Pipeline dài, cần biết lỗi đi qua ranh giới nghiệp vụ nào | Thêm `checkpoint("description")` tại các ranh giới chính |
| Một đoạn cụ thể nghi có lỗi assembly | Dùng `checkpoint("description", true)` hoặc `checkpoint()` tại đoạn đó |
| Chưa biết pipeline nào gây lỗi trong môi trường dev/test | Bật `Hooks.onOperatorDebug()` trước khi lắp ráp Publisher |
| Cần định danh pipeline cho introspection/metrics | Dùng `name` và `tag` |
| Cần biết số lỗi, correlation ID hoặc trạng thái request | Kết hợp logging, metrics và tracing |
| Cần xác minh tín hiệu lỗi trong test | Dùng `StepVerifier.expectError...` và chỉ kiểm tra thuộc tính ổn định |

Một chiến lược thực tế là giữ checkpoint nhẹ tại ranh giới quan trọng trong code, sau đó bật full assembly trace có chọn lọc khi cần điều tra sâu. Như vậy, thông tin chẩn đoán vẫn hữu ích mà không phải thu thập stack trace cho mọi operator trong mọi request.

## 14. Các lỗi thường gặp khi dùng checkpoint

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Bật `Hooks.onOperatorDebug()` sau khi pipeline đã được lắp ráp | Publisher cũ không có assembly trace được tạo bởi hook đó | Bật hook trước khi tạo Publisher cần theo dõi |
| Chỉ log `error.getMessage()` | Mất stack trace và suppressed assembly information | Log đầy đủ throwable |
| Đặt checkpoint trước đoạn đang nghi ngờ | Lỗi ở operator phía downstream không đi qua checkpoint đó | Đặt checkpoint sau đoạn cần đánh dấu hoặc ở cuối chuỗi |
| Dùng mô tả checkpoint chung chung | Khó xác định pipeline trong log | Dùng tên domain, thao tác và thành phần |
| Buộc stack trace ở mọi checkpoint | Tăng chi phí CPU và bộ nhớ | Dùng checkpoint nhẹ, force trace có chọn lọc |
| Coi checkpoint là cơ chế retry/fallback | Lỗi vẫn truyền xuống downstream | Dùng `retryWhen`, `onErrorResume` khi nghiệp vụ yêu cầu |
| Test khẳng định toàn bộ stack trace | Test dễ vỡ khi đổi phiên bản hoặc build | Kiểm tra loại lỗi và thông tin ổn định |
| Để hook toàn cục ảnh hưởng test khác | Kết quả test không độc lập | Reset hook trong `finally` và cô lập test |

## 15. Checklist chẩn đoán một pipeline lỗi

Khi một `Mono` hoặc `Flux` phát lỗi khó truy nguyên, hãy kiểm tra:

1. Publisher được lắp ráp ở service, controller hay factory nào?
2. Lỗi xuất hiện trong assembly, subscription hay execution?
3. Stack trace đầy đủ có cause và suppressed exceptions không?
4. Có checkpoint mô tả tại các ranh giới nghiệp vụ quan trọng không?
5. Checkpoint có nằm sau đoạn operator cần quan sát để lỗi đi qua nó không?
6. Có cần force stack trace cục bộ hay bật `Hooks.onOperatorDebug()` trong môi trường điều tra không?
7. `name`/`tag`, correlation ID và trace ID có giúp định danh pipeline không?
8. Lỗi là lỗi dữ liệu, lỗi scheduler, timeout, cancellation hay lỗi dependency từ xa?
9. Metrics có cho biết demand, queue, retry, latency và số lần cancellation không?
10. Test có xác minh tín hiệu lỗi bằng `StepVerifier` mà không phụ thuộc định dạng stack trace không?
11. Hook debug toàn cục có được reset sau test hoặc phiên điều tra không?

`checkpoint` và assembly tracing giúp nối lỗi runtime với vị trí tạo Publisher trong code. Dùng checkpoint nhẹ có mô tả tại ranh giới nghiệp vụ, bật stack trace hoặc `Hooks.onOperatorDebug()` có chọn lọc, và log đầy đủ throwable để giữ cả cause lẫn suppressed information. Kết hợp assembly trace với `StepVerifier`, metrics và correlation context giúp việc chẩn đoán pipeline `Mono`/`Flux` có căn cứ hơn mà vẫn kiểm soát được chi phí quan sát.
