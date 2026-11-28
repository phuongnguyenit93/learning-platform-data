# Phân biệt Mono bất đồng bộ trong ứng dụng với bất đồng bộ của OSB API

Trong Spring Cloud Open Service Broker, các handler thường sử dụng Reactor Mono để biểu diễn kết quả xử lý theo kiểu reactive. Mono cho phép ứng dụng thực hiện I/O không chặn và trả về một kết quả sẽ có sẵn khi tác vụ hoàn tất. Tuy nhiên, việc một handler trả về Mono không có nghĩa platform đã nhận được phản hồi bất đồng bộ theo Open Service Broker API (OSB API).

Đây là hai lớp khác nhau:

- **Bất đồng bộ ở cấp ứng dụng:** Mono mô tả cách một tác vụ trong ứng dụng Spring tạo ra một kết quả hoặc hoàn tất mà không nhất thiết chặn thread đang xử lý.
- **Bất đồng bộ ở cấp giao thức OSB:** Broker trả lời platform rằng thao tác vòng đời chưa hoàn tất, cung cấp mã operation và cho phép platform truy vấn trạng thái qua endpoint last_operation.

Một Mono có thể hoàn tất sau vài mili giây hoặc vài phút. Nếu broker chỉ gửi HTTP response sau khi Mono phát ra kết quả cuối cùng, platform vẫn đang chờ request đó. Để dùng cơ chế bất đồng bộ của OSB API, broker phải trả phản hồi chấp nhận thao tác khi công việc còn đang chạy, lưu trạng thái bền vững và cho platform một cách theo dõi tiến trình.

Bài học này giải thích ngữ nghĩa của Mono, cơ chế reactive trong Spring, hợp đồng asynchronous operation của OSB API, cách kết hợp hai lớp trong service broker, cùng các lỗi thường gặp khi triển khai provision, update và deprovision kéo dài.

## 1. Hai lớp bất đồng bộ giải quyết hai vấn đề khác nhau

Giả sử platform yêu cầu tạo một PostgreSQL database. Việc tạo database có thể mất 90 giây. Trong khi đó, broker được viết bằng Spring WebFlux và handler có chữ ký trả về Mono.

Có hai cách xử lý:

**Cách A — Mono chờ tới khi provider tạo xong tài nguyên**

Handler gọi API provider bằng WebClient. Request HTTP tới provider không chặn thread, nhưng Mono chỉ phát ra response khi database đã sẵn sàng. Trong suốt thời gian đó, request OSB ban đầu vẫn chưa có response cuối cùng. Đây là reactive I/O ở cấp ứng dụng; chưa phải asynchronous operation ở cấp OSB.

**Cách B — Broker chấp nhận thao tác rồi xử lý nền**

Handler ghi nhận yêu cầu, lưu operation ở trạng thái đang chạy, gửi công việc vào queue hoặc transactional outbox rồi trả HTTP 202 Accepted. Platform nhận mã operation và có thể gọi last_operation để hỏi trạng thái. Worker xử lý việc tạo database độc lập với request HTTP ban đầu.

Cách B sử dụng cả hai lớp: Mono giúp handler thực hiện việc ghi trạng thái và phát lệnh nhanh theo kiểu reactive; OSB API định nghĩa cách platform theo dõi công việc dài.

~~~mermaid
flowchart TD
    A[Platform gửi provision request] --> B[OSB HTTP handler]
    B --> C[Mono reactive pipeline]
    C --> D{Provider đã hoàn tất ngay?}
    D -->|Có| E[Trả kết quả hoàn tất]
    D -->|Chưa, nhưng client cho phép async| F[Lưu operation và enqueue job]
    F --> G[Trả HTTP 202 Accepted]
    G --> H[Platform gọi last_operation]
    F --> I[Background worker]
    I --> J[Provider API]
    J --> K[Cập nhật trạng thái operation]
    K --> H
~~~

Điểm cần nhớ: Mono mô tả cách một đoạn code tạo ra kết quả; OSB asynchronous operation mô tả một quy trình nhiều bước có trạng thái được platform quan sát qua giao thức.

## 2. Mono là gì trong Reactor?

Mono là một kiểu Publisher trong Project Reactor, biểu diễn một luồng có thể phát ra tối đa một phần tử rồi kết thúc. Một Mono có thể:

- Phát ra một giá trị và hoàn tất.
- Hoàn tất mà không phát ra giá trị, thường dùng cho thao tác không cần kết quả.
- Phát ra lỗi.

Ví dụ:

~~~java
Mono<String> completed = Mono.just("database-ready");

Mono<Void> noValue = Mono.empty();

Mono<String> failed =
        Mono.error(new IllegalStateException("provider unavailable"));
~~~

Mono thường được dùng trong Spring WebFlux và các API reactive của Spring Cloud Open Service Broker. Handler có thể trả Mono chứa response, Mono chứa model nghiệp vụ hoặc Mono<Void> khi chỉ cần biểu diễn việc hoàn tất.

Mono không phải một thread và cũng không mặc định tạo thread mới. Nó là một mô tả cho quá trình phát tín hiệu. Việc chạy trên thread nào phụ thuộc nguồn dữ liệu, scheduler và cách pipeline được subscribe.

### 2.1. Mono thường là lazy

Nhiều operator của Reactor tạo pipeline mà chưa thực thi công việc ngay. Công việc bắt đầu khi có subscriber. Trong ứng dụng WebFlux, framework web thường đảm nhiệm việc subscribe publisher để lấy response và ghi dữ liệu ra HTTP.

Ví dụ:

~~~java
Mono<String> result = Mono.fromSupplier(() -> {
    System.out.println("Đang tạo giá trị");
    return "ready";
});
~~~

Khai báo biến result chưa nhất thiết chạy supplier. Khi pipeline được subscribe, supplier mới được gọi.

Điều này quan trọng khi thiết kế handler: hãy trả publisher cho framework để framework quản lý vòng đời request. Không tự gọi subscribe bên trong handler để khởi chạy công việc rồi trả response rỗng, vì như vậy framework không còn quản lý đúng lỗi, cancellation và tín hiệu hoàn tất của công việc đó.

### 2.2. Mono có thể biểu diễn I/O không chặn

Với WebClient, broker có thể gọi provider API mà không giữ một thread chờ response:

~~~java
Mono<ProviderResource> createDatabase(
        CreateDatabaseRequest request) {

    return webClient.post()
            .uri("/databases")
            .bodyValue(request)
            .retrieve()
            .bodyToMono(ProviderResource.class);
}
~~~

Mono ở đây hoàn tất khi provider trả response và body được giải mã. Nếu provider trả về một operation ID ngay sau khi tiếp nhận công việc, Mono có thể hoàn tất nhanh với operation ID đó dù database vẫn đang được tạo ở phía provider.

Nếu provider chỉ trả response khi database sẵn sàng, Mono sẽ hoàn tất muộn hơn. Cả hai trường hợp đều có thể dùng reactive I/O; chỉ trường hợp broker trả response OSB 202 trước khi database sẵn sàng mới thể hiện asynchronous operation ở cấp giao thức.

## 3. Mono hoàn tất không đồng nghĩa OSB operation hoàn tất

Một handler có thể trả Mono của response OSB. Khi Mono phát ra response, framework có dữ liệu để hoàn tất HTTP request. Thời điểm đó mới quyết định platform nhận được response gì.

Ví dụ, pipeline sau đợi provider tạo xong database:

~~~java
Mono<ProvisionResult> provision(ProvisionCommand command) {
    return providerClient.createAndWaitUntilReady(command)
            .map(resource -> ProvisionResult.completed(
                    resource.id()));
}
~~~

Dù providerClient sử dụng WebClient và không chặn thread, platform vẫn phải đợi Mono phát ra ProvisionResult. Nếu tác vụ kéo dài 90 giây, HTTP request có thể tồn tại trong 90 giây, phụ thuộc timeout của platform, gateway và server.

Reactive giúp sử dụng tài nguyên thread hiệu quả hơn trong khi chờ I/O. Nó không tự thay đổi hợp đồng HTTP thành mô hình chấp nhận rồi polling.

Một ví dụ khác:

~~~java
Mono<ProvisionAccepted> acceptProvision(ProvisionCommand command) {
    return operationService.createAndEnqueue(command)
            .map(operation -> new ProvisionAccepted(operation.id()));
}
~~~

Nếu endpoint adapter chuyển ProvisionAccepted thành response OSB 202, platform nhận được mã operation ngay sau khi broker lưu trạng thái và xếp công việc. Việc tạo database tiếp tục trong worker. Đây mới là cách kết hợp Mono với asynchronous operation ở cấp OSB.

## 4. Cơ chế asynchronous operation của OSB API

OSB API cho phép broker xử lý một số thao tác vòng đời theo kiểu bất đồng bộ, đặc biệt là:

- Provision service instance.
- Update service instance.
- Deprovision service instance.

Platform cho biết nó có chấp nhận thao tác bất đồng bộ hay không thông qua query parameter accepts_incomplete=true trên request tương ứng.

Ví dụ provision:

~~~http
PUT /v2/service_instances/instance-123?accepts_incomplete=true
Content-Type: application/json
X-Broker-API-Version: <phiên-bản-OSB-API-được-hỗ-trợ>
~~~

Nếu broker không thể hoàn tất thao tác trong request hiện tại và platform đã cho phép asynchronous operation, broker có thể chấp nhận xử lý và trả HTTP 202 Accepted theo hợp đồng OSB. Response có thể chứa operation để platform truy vấn tiến trình.

Ví dụ response rút gọn:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
~~~

~~~json
{
  "operation": "provision-op-789"
}
~~~

Mã operation là định danh do broker quản lý. Broker phải giữ được mối quan hệ giữa operation, service instance và công việc thực tế đang chạy.

Nếu client không cho phép asynchronous operation mà broker không thể hoàn tất đồng bộ, broker phải phản hồi theo quy tắc lỗi của OSB API, thường là lỗi AsyncRequired với HTTP 422. Không được trả 202 khi client chưa chấp nhận xử lý bất đồng bộ, cũng không được trả thành công hoàn tất khi tài nguyên vẫn đang được tạo.

### 4.1. Endpoint last_operation

Sau khi nhận 202, platform truy vấn endpoint last_operation để biết trạng thái thao tác.

Ví dụ:

~~~http
GET /v2/service_instances/instance-123/last_operation?service_id=postgres-service-id&plan_id=postgres-plan-id&operation=provision-op-789
X-Broker-API-Version: <phiên-bản-OSB-API-được-hỗ-trợ>
~~~

Broker trả trạng thái theo hợp đồng OSB. Các trạng thái thường dùng gồm:

- in progress: thao tác vẫn đang chạy.
- succeeded: thao tác đã hoàn tất thành công.
- failed: thao tác đã thất bại.

Ví dụ response khi đang xử lý:

~~~json
{
  "state": "in progress",
  "description": "Đang tạo database trên provider"
}
~~~

Ví dụ response khi hoàn tất:

~~~json
{
  "state": "succeeded",
  "description": "Database đã sẵn sàng"
}
~~~

Platform có thể tiếp tục polling theo chính sách của nó cho tới khi nhận trạng thái kết thúc. Broker nên trả mô tả ngắn, có ích cho vận hành và không chứa secret hoặc thông tin nội bộ nhạy cảm.

### 4.2. Phân biệt operation ID của broker và provider

Provider cũng có thể có operation ID riêng. Ví dụ broker gửi lệnh tạo database và provider trả task-456. Broker có thể trả operation ID cho OSB là provision-op-789.

Hai ID có vai trò khác nhau:

| Định danh | Ai sử dụng | Mục đích |
|---|---|---|
| service_instance_id | Platform và broker | Nhận diện service instance |
| OSB operation ID | Platform và broker | Theo dõi một thao tác vòng đời |
| provider operation ID | Broker và provider | Tra cứu công việc tại nhà cung cấp |
| provider_resource_id | Broker và provider | Quản lý tài nguyên thực tế |

Broker cần lưu mapping giữa các ID này. Không nên trả provider operation ID trực tiếp cho platform nếu điều đó làm lộ chi tiết nội bộ hoặc khiến hợp đồng platform phụ thuộc vào nhà cung cấp.

## 5. Bảng so sánh Mono và OSB asynchronous operation

| Tiêu chí | Mono / Reactor | OSB asynchronous operation |
|---|---|---|
| Phạm vi | Trong ứng dụng Spring | Giữa platform và broker |
| Mục đích | Biểu diễn kết quả reactive, hỗ trợ I/O không chặn | Cho phép request được chấp nhận trước khi công việc hoàn tất |
| Cơ chế | Publisher, operator, subscriber, scheduler | accepts_incomplete, HTTP 202, operation ID, last_operation |
| Thời điểm HTTP response | Khi handler phát ra response hoặc hoàn tất | Có thể trả 202 ngay khi đã lưu nhận thao tác |
| Theo dõi tiến trình | Qua pipeline, log, metric hoặc trạng thái nội bộ | Platform polling last_operation |
| Lưu trạng thái | Mono không tự lưu trạng thái bền vững | Broker phải lưu operation bền vững để truy vấn lại |
| Sau khi process restart | Pipeline đang chạy trong memory có thể mất | Operation phải có thể tiếp tục hoặc được phục hồi từ kho trạng thái |
| Có tự tạo background job không? | Không | Không tự tạo; broker phải triển khai worker hoặc cơ chế xử lý nền |

Mono có thể được dùng để triển khai cả handler phản hồi đồng bộ lẫn handler chấp nhận thao tác bất đồng bộ. OSB async có thể được triển khai bằng reactive hoặc imperative code. Hai khái niệm độc lập về mặt thiết kế.

## 6. Kiến trúc kết hợp Mono với OSB asynchronous operation

Một kiến trúc phổ biến có các thành phần:

- OSB HTTP handler: nhận request và kiểm tra điều kiện giao thức.
- Application service: xác thực instance, plan, tenant và quy tắc nghiệp vụ.
- Operation repository: lưu trạng thái thao tác.
- Transactional outbox hoặc message queue: chuyển công việc tới worker một cách tin cậy.
- Background worker: thực hiện công việc dài.
- Provider adapter: gọi API nhà cung cấp.
- Last operation service: đọc trạng thái để trả cho platform.

~~~mermaid
flowchart LR
    P[Platform] --> H[OSB Handler]
    H --> A[Application Service]
    A --> R[(Operation Repository)]
    A --> O[(Transactional Outbox)]
    O --> Q[Queue]
    Q --> W[Background Worker]
    W --> V[Provider Adapter]
    V --> S[Backing Service]
    W --> R
    P --> L[Last Operation Handler]
    L --> R
~~~

Mono có thể xuất hiện ở handler, repository reactive, outbox publisher và provider adapter. Tuy nhiên, queue và kho trạng thái mới là nơi bảo đảm công việc có thể tiếp tục sau khi HTTP request kết thúc hoặc ứng dụng restart.

Nếu dùng một queue bên ngoài, broker cần quản lý việc gửi message và ghi operation nhất quán. Transactional outbox là một lựa chọn: trong cùng transaction database, broker lưu operation và outbox event. Một publisher riêng đọc outbox rồi gửi message. Cách này tránh tình huống lưu operation thành công nhưng gửi queue thất bại, hoặc gửi queue thành công nhưng transaction lưu operation rollback.

## 7. Triển khai handler reactive cho request đồng bộ

Không phải mọi thao tác đều cần asynchronous operation. Nếu broker có thể hoàn tất nhanh trong giới hạn timeout của platform, handler có thể trả kết quả sau khi Mono hoàn tất.

Ví dụ khái niệm:

~~~java
public Mono<ProvisionServiceInstanceResponse> provision(
        ProvisionServiceInstanceRequest request) {

    return providerClient.createDatabase(request)
            .flatMap(resource ->
                    instanceRepository.saveActive(
                            request.getServiceInstanceId(),
                            resource.id()))
            .map(saved -> ProvisionServiceInstanceResponse.builder()
                    .build());
}
~~~

Pipeline thực hiện lần lượt:

1. Gọi provider API theo kiểu reactive.
2. Khi có resource, lưu mapping và trạng thái ACTIVE.
3. Tạo response cho framework.
4. Framework ghi HTTP response về platform khi Mono phát ra giá trị.

Ví dụ này phù hợp khi provider hoàn tất đủ nhanh hoặc API provider trả kết quả đồng bộ về mặt nghiệp vụ. Nếu thao tác thực tế kéo dài, broker cần cân nhắc timeout, cancellation và khả năng retry của platform.

Một Mono có thể hoàn tất nhanh dù có dùng I/O bất đồng bộ. Điều quan trọng là thời điểm handler phát ra response và ý nghĩa của response đó, không phải chỉ nhìn kiểu trả về Mono.

## 8. Triển khai handler chấp nhận thao tác OSB bất đồng bộ

Với thao tác dài, handler nên tập trung vào việc nhận và lưu yêu cầu một cách tin cậy. Ví dụ mã giả:

~~~java
public Mono<AsyncProvisionAccepted> acceptProvision(
        ProvisionCommand command) {

    return operationService.createPendingOperation(command)
            .flatMap(operation ->
                    outboxRepository.enqueueProvision(operation)
                            .thenReturn(operation))
            .map(operation ->
                    new AsyncProvisionAccepted(operation.id()));
}
~~~

Đây là ví dụ ở tầng ứng dụng, không phải chữ ký handler cụ thể của mọi phiên bản framework. Adapter OSB phải chuyển kết quả accepted thành HTTP 202 và body theo đúng hợp đồng mà phiên bản Spring Cloud Open Service Broker đang dùng hỗ trợ.

Một operation chỉ nên được coi là đã chấp nhận khi:

- Broker đã xác thực request.
- Service instance và plan đã được kiểm tra.
- Operation record đã được lưu bền vững.
- Công việc đã được ghi vào transactional outbox hoặc một cơ chế enqueue tin cậy.
- Operation ID có thể được dùng để tra cứu trạng thái.

Không trả 202 chỉ vì đã đưa một Runnable vào executor trong memory. Nếu tiến trình dừng ngay sau response, công việc có thể biến mất và platform sẽ polling mãi mà không có kết quả.

## 9. Worker xử lý công việc dài

Sau khi request OSB ban đầu kết thúc, worker thực hiện công việc tạo tài nguyên. Worker có thể sử dụng reactive pipeline hoặc code imperative tùy công nghệ queue và provider adapter.

Một luồng worker khái niệm:

~~~java
Mono<Void> executeProvision(String operationId) {
    return operationRepository.markRunning(operationId)
            .then(operationRepository.load(operationId))
            .flatMap(operation ->
                    providerClient.createResource(operation.command())
                            .flatMap(providerResult ->
                                    operationRepository
                                            .saveProviderOperation(
                                                    operationId,
                                                    providerResult.operationId(),
                                                    providerResult.resourceId())))
            .then(operationRepository.markSucceeded(operationId))
            .onErrorResume(error ->
                    operationRepository.markFailed(
                            operationId,
                            sanitize(error)));
}
~~~

Đây là mã minh họa, cần điều chỉnh theo transaction boundary và trạng thái provider thực tế. Nếu provider trả operation ID trước khi tài nguyên sẵn sàng, worker không được đánh dấu SUCCEEDED ngay. Nó phải tiếp tục polling provider hoặc nhận callback cho đến khi tài nguyên đạt trạng thái sẵn sàng theo tiêu chí của broker.

Nếu worker xử lý nhiều message, cần bảo đảm mỗi message có thể được giao lại mà không tạo tác dụng phụ trùng lặp. Queue thường cung cấp ít nhất một lần giao nhận; do đó worker phải idempotent và operation state phải kiểm soát việc xử lý lặp.

## 10. Không dùng Mono như một bộ lập lịch nền

Một hiểu lầm phổ biến là gọi provider bằng Mono, tự subscribe rồi trả HTTP 202:

~~~java
public Mono<Response> provision(Request request) {
    providerClient.createDatabase(request)
            .subscribe();

    return Mono.just(Response.accepted());
}
~~~

Cách làm này có nhiều vấn đề:

- Lỗi trong pipeline có thể không được chuyển tới luồng xử lý lỗi của HTTP request.
- Không có operation record bền vững để last_operation truy vấn.
- Công việc có thể mất khi process restart.
- Không có cơ chế retry có kiểm soát.
- Không có cách phối hợp nhiều replica hoặc ngăn thao tác trùng.
- Không có mapping đáng tin cậy giữa operation ID và provider resource.

Tương tự, Mono.delay hoặc một scheduler trong memory không thay thế queue bền vững cho công việc dài. Scheduler hữu ích cho timer hoặc tác vụ cục bộ có vòng đời phù hợp, nhưng không nên là nguồn sự thật duy nhất cho operation mà platform đang theo dõi.

Hãy trả publisher để framework quản lý request. Nếu cần xử lý sau khi trả 202, hãy ghi công việc vào queue hoặc outbox và để worker có vòng đời độc lập thực hiện.

## 11. Tránh chặn event loop trong reactive pipeline

Reactive I/O chỉ phát huy tác dụng khi các thành phần trong pipeline không chặn thread xử lý. Một đoạn code gọi JDBC đồng bộ, SDK blocking hoặc Thread.sleep bên trong handler có thể làm nghẽn event loop.

Ví dụ không nên làm:

~~~java
Mono<ProviderResource> createResource(Command command) {
    return Mono.fromCallable(() -> blockingProviderSdk.create(command));
}
~~~

Mono.fromCallable không tự biến lời gọi blocking thành non-blocking. Callable mặc định chạy trên thread subscribe nếu không chuyển scheduler phù hợp.

Nếu buộc phải dùng SDK blocking, có thể cô lập lời gọi trên boundedElastic:

~~~java
Mono<ProviderResource> createResource(Command command) {
    return Mono.fromCallable(
                    () -> blockingProviderSdk.create(command))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Cách này giảm nguy cơ chặn event loop nhưng vẫn tiêu thụ thread trong lúc chờ. Khi có thể, ưu tiên client reactive như WebClient. Với CPU-bound work, cần chọn chiến lược thực thi phù hợp thay vì mặc định đưa mọi công việc sang boundedElastic.

Cũng không nên dùng block() trong handler WebFlux để chờ Mono khác. Làm như vậy biến pipeline reactive thành chờ đồng bộ và có thể gây lỗi hoặc deadlock trong một số ngữ cảnh.

## 12. Xử lý lỗi và cancellation

Trong reactive pipeline, lỗi được truyền như một tín hiệu onError. Có thể dùng onErrorMap, onErrorResume hoặc retryWhen để chuyển đổi và phục hồi lỗi theo chính sách.

Ví dụ:

~~~java
return providerClient.createResource(command)
        .onErrorMap(
                ProviderUnavailableException.class,
                error -> new BrokerDependencyException(
                        "Provider is temporarily unavailable",
                        error));
~~~

Tuy nhiên, không phải lỗi nào cũng có nghĩa provider không thực hiện thao tác. Nếu request timeout sau khi provider đã nhận lệnh, trạng thái có thể không xác định. Broker cần lưu operation và kiểm tra provider trước khi gửi lại lệnh có tác dụng phụ.

Cancellation cũng cần được hiểu đúng. Khi platform, gateway hoặc client đóng kết nối, subscription của request Mono có thể bị cancel. Việc cancel HTTP request không nhất thiết có nghĩa phải hủy thao tác tạo tài nguyên ở provider. Nếu broker đã chấp nhận operation bền vững và trả 202, worker phải tiếp tục theo chính sách độc lập với subscription ban đầu.

Nếu broker đang xử lý đồng bộ và client hủy request, cần xác định provider call có thể bị cancel an toàn hay không. Không được giả định hủy subscription sẽ hoàn tác tài nguyên đã tạo ở hệ thống bên ngoài.

## 13. Quản lý trạng thái operation bền vững

Để hỗ trợ last_operation, broker cần lưu trạng thái trong database hoặc một kho bền vững dùng chung. Một bảng operation có thể có các trường:

| Trường | Mục đích |
|---|---|
| operation_id | ID công khai cho OSB operation |
| service_instance_id | Instance liên quan |
| operation_type | PROVISION, UPDATE hoặc DEPROVISION |
| state | Trạng thái xử lý hiện tại |
| description | Mô tả an toàn để trả cho platform |
| provider_operation_id | ID thao tác của provider |
| attempt_count | Số lần worker đã thử |
| created_at | Thời điểm nhận yêu cầu |
| started_at | Thời điểm worker bắt đầu |
| completed_at | Thời điểm kết thúc |
| last_error_code | Mã lỗi đã chuẩn hóa |

Ví dụ SQL:

~~~sql
CREATE TABLE broker_operation (
    operation_id VARCHAR(255) PRIMARY KEY,
    service_instance_id VARCHAR(255) NOT NULL,
    operation_type VARCHAR(40) NOT NULL,
    state VARCHAR(40) NOT NULL,
    description VARCHAR(500),
    provider_operation_id VARCHAR(512),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    last_error_code VARCHAR(100)
);
~~~

Cần có index theo service_instance_id và created_at hoặc theo trạng thái để worker và last_operation truy vấn hiệu quả. Nếu một instance chỉ được phép có một operation thay đổi tài nguyên tại một thời điểm, có thể bổ sung ràng buộc hoặc cơ chế khóa để bảo đảm điều đó.

Không nên chỉ lưu operation trong một Map hoặc biến static. Cách đó chỉ tồn tại trong một process, không hoạt động ổn định khi chạy nhiều replica và mất trạng thái khi restart.

## 14. Triển khai last_operation bằng Mono

Endpoint last_operation thường cần đọc trạng thái operation và trả response nhanh. Nếu repository hỗ trợ reactive, handler có thể trả Mono của trạng thái:

~~~java
public Mono<OperationStatus> getLastOperation(
        String instanceId,
        String operationId) {

    return operationRepository
            .findByIdAndInstanceId(operationId, instanceId)
            .switchIfEmpty(Mono.error(
                    new OperationNotFoundException(operationId)))
            .map(operation -> new OperationStatus(
                    operation.state(),
                    operation.description()));
}
~~~

Mono ở đây chỉ mô tả việc đọc trạng thái. Nó không có nghĩa operation đang chạy là một Mono được giữ sống từ request provision ban đầu. Mỗi lần platform gọi last_operation, broker thực hiện một lần tra cứu mới từ kho trạng thái.

Nếu operation vẫn đang chạy, response có state in progress. Khi worker cập nhật database thành succeeded hoặc failed, lần polling tiếp theo trả trạng thái mới.

Không nên giữ một Mono trong memory rồi cố chia sẻ kết quả cho mọi request last_operation. Trạng thái operation cần là dữ liệu có thể truy vấn độc lập qua nhiều request và nhiều instance broker.

## 15. Idempotency trong cả hai lớp

Idempotency cần được áp dụng cho request OSB và công việc worker. Platform có thể retry request provision nếu không nhận được response; queue cũng có thể giao lại message nếu worker không ack.

Một khóa xử lý có thể dựa trên service_instance_id và operation type, kết hợp operation ID hoặc request fingerprint. Khi nhận request lặp:

- Nếu operation tương ứng đang chạy, trả cùng operation ID và tiếp tục theo dõi.
- Nếu operation đã thành công, trả kết quả phù hợp với trạng thái đã lưu.
- Nếu request có nội dung không tương thích với instance đã tồn tại, trả lỗi theo hợp đồng.
- Không tạo operation thứ hai chỉ vì platform gửi lại cùng request.

Ở worker:

- Kiểm tra operation có đang ở trạng thái có thể xử lý hay không.
- Lưu trạng thái RUNNING theo cơ chế atomic.
- Dùng provider idempotency key nếu API hỗ trợ.
- Trước khi tạo lại tài nguyên sau timeout, tra cứu provider operation hoặc resource tag.
- Commit trạng thái cuối cùng một cách idempotent.

Một pipeline Mono có thể bị subscribe nhiều lần nếu được dùng sai cách hoặc được chia sẻ không đúng. Không nên dựa vào việc một Mono chỉ chạy một lần để bảo đảm idempotency. Ràng buộc phải nằm trong database, operation registry và provider integration.

## 16. Xử lý đồng thời và state transition

Một instance có thể nhận nhiều request update hoặc deprovision gần nhau. Broker cần ngăn các thao tác thay đổi tài nguyên chạy đồng thời nếu chúng xung đột.

Ví dụ state transition:

~~~text
REQUESTED
    |
    v
ACCEPTED
    |
    v
IN_PROGRESS
   / \
  v   v
SUCCEEDED  FAILED
~~~

Đây là trạng thái operation nội bộ minh họa. Instance có state riêng, ví dụ PROVISIONING, ACTIVE, UPDATING, DEPROVISIONING hoặc FAILED.

Mỗi transition cần có điều kiện. Ví dụ chỉ cho phép bắt đầu update khi instance ACTIVE và không có operation thay đổi tài nguyên khác. Khi worker hoàn tất, cần kiểm tra operation vẫn là operation đang sở hữu instance trước khi ghi trạng thái cuối cùng.

Có thể dùng optimistic locking với version, row-level lock hoặc conditional update. Việc chỉ kiểm tra state ở Java rồi ghi sau bằng hai câu lệnh rời rạc có thể tạo race condition khi nhiều replica xử lý cùng instance.

## 17. Timeout và polling

Platform có thể polling last_operation theo khoảng thời gian do nó quyết định. Broker cần bảo đảm endpoint này đủ nhẹ để chịu được nhiều request lặp, đồng thời không gọi provider quá mức cho mỗi lần polling nếu không cần thiết.

Một số nguyên tắc:

- Lưu trạng thái tiến trình trong broker database.
- Worker cập nhật trạng thái khi có thay đổi hoặc theo chu kỳ.
- Last operation ưu tiên đọc trạng thái đã lưu.
- Chỉ gọi provider để refresh khi cần và có giới hạn tốc độ.
- Không trả succeeded khi chưa xác minh tiêu chí hoàn tất.
- Không giữ operation in progress vô thời hạn; cần timeout, reconciliation và cảnh báo.
- Description nên phản ánh trạng thái thực tế, không tiết lộ dữ liệu nhạy cảm.

Timeout HTTP của request provision ban đầu và timeout nghiệp vụ của operation là hai khái niệm khác nhau. Request có thể hoàn tất sau vài trăm mili giây với 202, trong khi operation có thể mất vài phút. Broker cần quản lý cả timeout xử lý request lẫn deadline của operation.

## 18. Khi nào nên dùng Mono đồng bộ, khi nào nên dùng OSB async?

Có thể chọn theo đặc điểm của thao tác:

| Tình huống | Cách phù hợp |
|---|---|
| Đọc catalog từ cấu hình hoặc database | Mono trả kết quả sau khi đọc |
| Kiểm tra tham số nhanh | Mono đồng bộ về mặt giao thức |
| Tạo tài nguyên provider hoàn tất rất nhanh và ổn định | Có thể chờ Mono hoàn tất rồi trả kết quả |
| Gọi provider bằng WebClient nhưng provider phản hồi sau khi tài nguyên sẵn sàng | Reactive I/O; cân nhắc timeout và khả năng client chờ |
| Tạo database hoặc cluster mất nhiều phút | OSB asynchronous operation nếu platform chấp nhận |
| Update engine hoặc chạy migration dài | OSB asynchronous operation nếu được hỗ trợ |
| Deprovision cần chờ provider xóa tài nguyên | OSB asynchronous operation nếu được hỗ trợ |
| Tác vụ cần tiếp tục sau khi broker restart | Lưu operation bền vững và xử lý bằng worker |
| Tác vụ ngắn trong pipeline nội bộ | Mono thường đủ, không cần tạo OSB operation |

Không nên chọn asynchronous operation chỉ vì handler có kiểu trả về Mono. Hãy chọn dựa trên thời gian, timeout, khả năng retry, trải nghiệm platform và nhu cầu theo dõi trạng thái.

## 19. Lỗi thường gặp khi nhầm hai lớp bất đồng bộ

| Hiện tượng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Handler trả Mono nhưng platform vẫn timeout | Mono chỉ phát response sau khi provider hoàn tất | Trả 202 sớm nếu client chấp nhận async và lưu operation |
| Broker trả 202 nhưng last_operation không tìm thấy | Operation chỉ lưu trong memory hoặc chưa commit | Lưu operation bền vững trước khi response |
| Provider call không chặn nhưng HTTP vẫn mở lâu | Reactive I/O không thay đổi thời điểm response | Thiết kế protocol-level async |
| Công việc mất sau khi broker restart | Dùng scheduler hoặc subscribe trong process | Dùng queue/outbox và worker có thể phục hồi |
| Lỗi worker không được ghi nhận | Tách subscription khỏi request nhưng không quản lý error | Lưu trạng thái failed và metric/audit |
| Một message tạo nhiều tài nguyên | Worker không idempotent | Dùng operation state, unique key và provider idempotency |
| Event loop bị nghẽn | Gọi JDBC hoặc SDK blocking trực tiếp | Dùng client reactive hoặc cô lập blocking call |
| Platform polling mãi | Worker không cập nhật trạng thái kết thúc | Có deadline, reconciliation và cảnh báo operation treo |
| Cancel request làm dừng nhầm công việc nền | Gắn vòng đời worker với subscription HTTP | Tách worker khỏi request sau khi đã accept operation |
| Trạng thái last_operation không nhất quán giữa replica | Dữ liệu nằm trong memory hoặc cache không đồng bộ | Dùng kho trạng thái chung và cập nhật có kiểm soát |

## 20. Quy trình triển khai end-to-end

Khi triển khai một thao tác provision bất đồng bộ trong Spring Cloud service broker, có thể thực hiện theo trình tự:

1. Xác nhận thao tác OSB được phép chạy bất đồng bộ và platform hỗ trợ accepts_incomplete.
2. Xác định điều kiện hoàn tất đồng bộ và ngưỡng thời gian phù hợp.
3. Thiết kế operation ID và state machine nội bộ.
4. Lưu operation và instance state trong database bền vững.
5. Dùng transaction hoặc outbox để ghi nhận công việc cần xử lý.
6. Trả HTTP 202 theo hợp đồng OSB khi thao tác đã được chấp nhận.
7. Worker nhận job và gọi provider adapter.
8. Lưu provider operation ID và provider resource ID.
9. Poll hoặc nhận callback từ provider để cập nhật trạng thái.
10. Dùng last_operation trả trạng thái cho platform.
11. Khi hoàn tất, cập nhật instance state và operation state trong transaction phù hợp.
12. Kiểm thử retry, message redelivery, broker restart, provider timeout và nhiều request đồng thời.

Cần kiểm thử với đúng phiên bản Spring Cloud Open Service Broker và platform thực tế. Tên interface, kiểu response và cách framework biểu diễn asynchronous operation có thể khác theo release. Không nên sao chép chữ ký handler từ một phiên bản thư viện khác mà chưa xác nhận.

## 21. Checklist đánh giá

- [ ] Đã phân biệt Mono reactive với asynchronous operation của OSB API.
- [ ] Đã hiểu Mono phát tối đa một phần tử hoặc hoàn tất không có giá trị.
- [ ] Không dùng subscribe thủ công để chạy tác vụ nền trong handler.
- [ ] Không dùng block hoặc lời gọi blocking trực tiếp trên event loop.
- [ ] Đã xác nhận platform gửi accepts_incomplete khi cần async.
- [ ] Broker trả 202 chỉ sau khi operation được lưu bền vững và được xếp hàng tin cậy.
- [ ] Có operation ID riêng theo hợp đồng OSB.
- [ ] Đã lưu mapping tới provider operation ID và resource ID.
- [ ] Endpoint last_operation đọc trạng thái từ kho bền vững.
- [ ] Worker có thể tiếp tục sau restart và xử lý message redelivery.
- [ ] Retry không tạo tài nguyên hoặc operation trùng lặp.
- [ ] Có state transition và kiểm soát thao tác đồng thời.
- [ ] Timeout và cancellation của HTTP request không làm mất operation đã được chấp nhận.
- [ ] Có deadline, reconciliation và cảnh báo operation treo.
- [ ] Đã kiểm thử với đúng phiên bản framework và platform mục tiêu.

Mono và OSB asynchronous operation bổ sung cho nhau ở hai lớp khác nhau. Mono giúp Spring xử lý pipeline reactive, giảm việc giữ thread trong lúc chờ I/O và biểu diễn kết quả của handler. OSB asynchronous operation cho phép broker kết thúc request HTTP sớm bằng phản hồi chấp nhận, sau đó theo dõi công việc qua operation ID và last_operation. Một service broker đáng tin cậy cần kết hợp reactive pipeline với trạng thái bền vững, queue hoặc outbox, worker idempotent và endpoint theo dõi; chỉ trả về Mono không đủ để tạo ra quy trình bất đồng bộ mà platform có thể quan sát.

