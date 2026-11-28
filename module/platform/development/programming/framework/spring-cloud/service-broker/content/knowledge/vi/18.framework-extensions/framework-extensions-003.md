# Lập lịch lời gọi hạ tầng chặn luồng trong ứng dụng WebFlux

## Mục tiêu và bối cảnh

Spring Cloud Service Broker thường kết hợp các API reactive của Spring WebFlux và Reactor với SDK của nhà cung cấp hạ tầng. Một số SDK vẫn dùng I/O blocking: gọi JDBC, đọc file, truy vấn thư viện quản lý cloud, chạy lệnh đồng bộ hoặc gọi HTTP client cũ. Nếu gọi trực tiếp các API đó trên Reactor event loop, một thao tác chậm có thể giữ thread xử lý nhiều request khác và làm giảm khả năng phục vụ của toàn broker.

Bài học này trình bày cách lập lịch lời gọi blocking vào scheduler phù hợp trong ứng dụng WebFlux. Mục tiêu là giữ luồng reactive không bị chặn, giới hạn số tác vụ đồng thời và xử lý đúng timeout, lỗi, cancellation cùng context của request.

Sau bài học, bạn có thể:

- Nhận diện lời gọi blocking trong service broker.
- Giải thích vai trò của event loop, subscribeOn và publishOn.
- Bao bọc SDK blocking bằng Mono hoặc Flux và chuyển sang bounded elastic scheduler.
- Tạo scheduler riêng với giới hạn thread và hàng đợi khi cần.
- Kết hợp reactive API với adapter blocking mà không chặn event loop.
- Giới hạn concurrency, đặt timeout và xử lý retry an toàn.
- Kiểm thử để phát hiện blocking call chạy sai thread.
- Quyết định khi nào nên dùng scheduler và khi nào nên chuyển công việc sang worker bền vững.

## 1. Vì sao WebFlux cần tránh blocking?

WebFlux được xây dựng trên mô hình non-blocking. Reactor Netty thường dùng một nhóm nhỏ event loop để nhận kết nối, đọc dữ liệu, điều phối callback và ghi response. Một event loop có thể phục vụ nhiều request theo kiểu asynchronous.

Nếu một handler gọi phương thức blocking, thread hiện tại phải chờ cho đến khi I/O hoàn tất. Trong thời gian đó, event loop không thể xử lý các callback khác được giao cho nó.

Ví dụ không an toàn:

~~~java
public Mono<ServiceInstance> getInstance(String id) {
    ServiceInstance instance = blockingCloudClient.findInstance(id);
    return Mono.just(instance);
}
~~~

Phương thức findInstance được gọi ngay khi getInstance chạy. Nếu controller hoặc service gọi nó trên event loop, event loop bị chặn trước cả khi Mono được trả về.

Một request có thể chỉ chậm vài trăm mili giây, nhưng khi nhiều request cùng chờ backend, các event loop có thể bị chiếm hết. Người dùng sẽ thấy latency tăng, request timeout và throughput giảm dù CPU chưa chắc đã bận.

### 1.1. Các nguồn blocking thường gặp

| Nguồn | Ví dụ | Hướng xử lý |
|---|---|---|
| JDBC | JDBC Template, JPA repository đồng bộ | Chuyển phần gọi JDBC sang scheduler blocking hoặc dùng R2DBC |
| HTTP client đồng bộ | RestTemplate, Apache client blocking | Dùng WebClient hoặc bao bọc client trong bounded elastic |
| SDK cloud | SDK quản lý database, bucket, network theo kiểu đồng bộ | Dùng SDK async nếu phù hợp hoặc adapter blocking |
| File I/O | Đọc chứng thư, cấu hình hoặc file lớn | Dùng API async hoặc scheduler dành cho I/O |
| Process I/O | Chờ lệnh hệ điều hành, đọc stdout đồng bộ | Chuyển sang worker có giới hạn và quản lý timeout |
| Sleep/wait | Thread.sleep, Future.get, CountDownLatch.await | Tránh trong reactive path; dùng delay hoặc coordination reactive |

Không phải mọi phương thức có vẻ đồng bộ đều chắc chắn blocking. Cần kiểm tra hợp đồng thư viện và cách triển khai. Một method trả về Mono nhưng bên trong lại gọi blocking API ngay lập tức vẫn có thể chặn event loop.

### 1.2. CPU-bound và I/O-bound khác nhau

Tác vụ CPU-bound như tính toán mã hóa hoặc nén dữ liệu cần scheduler dành cho tính toán, thường là parallel scheduler với concurrency phù hợp số CPU. Tác vụ I/O-bound blocking như chờ JDBC hoặc SDK cloud phù hợp với bounded elastic scheduler.

Không chuyển tất cả công việc sang cùng một scheduler mà không phân loại. Nếu dùng scheduler CPU-bound cho lời gọi blocking, các thread tính toán có thể bị giữ trong lúc chờ I/O. Nếu dùng bounded elastic cho tính toán CPU nặng không giới hạn, số thread có thể tăng không cần thiết và làm hệ thống khó dự đoán.

## 2. Reactor event loop và scheduler

Reactor tách việc mô tả pipeline khỏi nơi pipeline được thực thi. Scheduler quyết định thread hoặc nhóm thread thực hiện các callback được lập lịch.

Một số scheduler thường gặp:

| Scheduler | Mục đích | Ví dụ sử dụng |
|---|---|---|
| immediate | Thực thi ngay trên thread hiện tại | Tình huống đặc biệt cần thực thi trực tiếp |
| single | Một thread tuần tự | Tác vụ cần tuần tự hóa trên một scheduler |
| parallel | Tác vụ CPU-bound | Tính toán độc lập, không blocking |
| boundedElastic | Tác vụ I/O blocking | JDBC hoặc SDK đồng bộ |
| Scheduler riêng | Nhóm thread với giới hạn do ứng dụng định nghĩa | Cô lập một backend hoặc nhóm tác vụ |

WebFlux không yêu cầu mọi đoạn code phải chạy trên một thread duy nhất. Pipeline có thể chuyển thread tại các ranh giới được lập lịch. Điều cần tránh là thực hiện thao tác blocking trên event loop hoặc trên scheduler không được thiết kế cho việc chờ I/O.

## 3. Dùng subscribeOn để chuyển blocking source

Cách phổ biến để bao bọc một lời gọi blocking là dùng Mono.fromCallable hoặc Mono.fromRunnable rồi áp dụng subscribeOn với Schedulers.boundedElastic().

Ví dụ:

~~~java
public Mono<CloudDatabase> findDatabase(String databaseId) {
    return Mono.fromCallable(
                    () -> blockingCloudClient.findDatabase(databaseId)
            )
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Mono.fromCallable trì hoãn việc gọi hàm cho đến khi có subscription. subscribeOn yêu cầu source và phần xử lý upstream chạy trên scheduler được chỉ định. Vì vậy lời gọi blocking được thực hiện trên bounded elastic thay vì event loop.

Đây là điểm khác biệt quan trọng so với ví dụ gọi client trước khi tạo Mono. Không gọi SDK blocking ở ngoài fromCallable rồi mới bọc kết quả vào Mono.just.

### 3.1. Bao bọc một chuỗi thao tác blocking

Nếu một nghiệp vụ gồm nhiều lời gọi đồng bộ có quan hệ phụ thuộc, có thể gom phần blocking vào một callable:

~~~java
public Mono<ProvisionResult> provisionDatabase(ProvisionCommand command) {
    return Mono.fromCallable(() -> {
                CloudDatabase database =
                        blockingCloudClient.createDatabase(command);

                blockingCloudClient.configureBackup(
                        database.id(),
                        command.backupPolicy()
                );

                return new ProvisionResult(
                        database.id(),
                        database.endpoint()
                );
            })
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Trong ví dụ này, cả chuỗi gọi blocking chạy trên bounded elastic. Không cần tạo một scheduler switch cho từng dòng lệnh. Tuy nhiên, nếu từng bước cần retry, timeout, compensation hoặc lưu operation riêng, nên tách chúng thành các bước workflow có trạng thái thay vì gom tất cả vào một callable dài.

### 3.2. Bao bọc một thao tác không trả kết quả

Với method blocking trả void, dùng Mono.fromRunnable:

~~~java
public Mono<Void> revokeCredential(String principalId) {
    return Mono.fromRunnable(
                    () -> blockingIdentityClient.revoke(principalId)
            )
            .subscribeOn(Schedulers.boundedElastic())
            .then();
}
~~~

Mono chỉ hoàn tất sau khi lệnh revoke kết thúc. Nếu lệnh ném exception, lỗi được chuyển thành tín hiệu onError của reactive pipeline.

Không dùng Mono.just để bao bọc một method void đã được gọi trước đó. Ví dụ Mono.just(blockingClient.delete(id)) vẫn gọi delete ngay khi biểu thức được đánh giá.

## 4. subscribeOn và publishOn khác nhau thế nào?

Hai toán tử đều có thể thay đổi thread thực thi, nhưng phạm vi tác động khác nhau.

- subscribeOn ảnh hưởng quá trình subscribe vào source và các thao tác upstream.
- publishOn chuyển việc xử lý các operator phía downstream sang scheduler được chỉ định tại vị trí đó.

Ví dụ:

~~~java
Mono.fromCallable(() -> blockingClient.fetchConfiguration())
        .subscribeOn(Schedulers.boundedElastic())
        .map(this::toDomainModel)
        .publishOn(Schedulers.parallel())
        .map(this::calculateSummary);
~~~

Trong pipeline này:

1. fetchConfiguration chạy trên bounded elastic.
2. toDomainModel nằm upstream của publishOn và thường tiếp tục trên thread phát tín hiệu từ source.
3. calculateSummary chạy trên parallel scheduler sau ranh giới publishOn.

Nếu chỉ đặt publishOn sau một lời gọi blocking đã được thực hiện trước khi tạo Mono, nó không thể chuyển lời gọi đó sang thread khác.

Một mẫu dễ gây nhầm:

~~~java
CloudConfiguration config = blockingClient.fetchConfiguration();

return Mono.just(config)
        .publishOn(Schedulers.boundedElastic());
~~~

Lời gọi fetchConfiguration đã hoàn tất trước khi publishOn có cơ hội tác động. Hãy bọc lời gọi trong fromCallable và đặt subscribeOn ở source.

### 4.1. Chọn đúng vị trí subscribeOn

Thông thường, đặt subscribeOn gần source blocking để ý định rõ ràng:

~~~java
Mono.fromCallable(() -> legacySdk.describeResource(resourceId))
        .subscribeOn(blockingScheduler)
        .map(this::toResourceView);
~~~

Không cần thêm nhiều subscribeOn giống nhau nếu không có lý do cụ thể. Nhiều lần chuyển scheduler không tự làm pipeline nhanh hơn; chúng có thể làm tăng chi phí điều phối và khiến việc theo dõi thread khó hơn.

## 5. Dùng boundedElastic mặc định hay scheduler riêng?

Reactor cung cấp Schedulers.boundedElastic() cho tác vụ blocking. Đây là lựa chọn phù hợp khi ứng dụng cần một cách đơn giản để cô lập các lời gọi blocking có thời gian chờ I/O.

~~~java
return Mono.fromCallable(() -> legacyClient.loadResource(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Scheduler mặc định được quản lý bởi Reactor. Ứng dụng không nên dispose scheduler toàn cục này trong vòng đời của một request hoặc service bean.

### 5.1. Khi nào nên tạo scheduler riêng?

Nếu broker có nhiều nhóm backend với đặc tính khác nhau, scheduler riêng giúp cô lập tải. Ví dụ, SDK quản lý database có thể chậm hơn SDK quản lý secret. Nếu dùng chung một pool và database API bị nghẽn, các tác vụ secret cũng có thể phải chờ.

Có thể tạo scheduler riêng với giới hạn thread và hàng đợi:

~~~java
@Configuration
public class BlockingSchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    public Scheduler cloudSdkScheduler() {
        return Schedulers.newBoundedElastic(
                16,
                500,
                "broker-cloud-sdk"
        );
    }
}
~~~

Các con số 16 thread và 500 task đang chờ chỉ là giá trị minh họa. Cần chọn theo giới hạn kết nối backend, quota API, thời gian xử lý và tài nguyên của container.

Spring quản lý bean scheduler và gọi dispose khi application context đóng. Không tạo scheduler mới cho từng request; việc đó gây rò rỉ thread và làm mất khả năng kiểm soát concurrency.

### 5.2. Giới hạn queue cũng quan trọng như giới hạn thread

Bounded elastic có thể xếp hàng tác vụ khi thread đang bận. Nếu hàng đợi quá lớn, request có thể nằm chờ lâu trước khi lời gọi backend bắt đầu. Khi đó timeout ở tầng HTTP có thể xảy ra dù backend chưa nhận request.

Cần đặt giới hạn queue phù hợp và theo dõi:

- Số thread đang hoạt động.
- Số tác vụ đang chờ.
- Thời gian chờ trước khi bắt đầu.
- Số lần scheduler từ chối nhận task.
- Thời gian thực hiện blocking call.

Nếu scheduler quá tải, broker nên phản hồi bằng lỗi quá tải có kiểm soát hoặc điều tiết request ở tầng application, thay vì để hàng đợi tăng vô hạn.

## 6. Thiết kế adapter cho SDK blocking

Không nên để chi tiết SDK blocking lan ra controller và domain service. Hãy cô lập chúng trong adapter hoặc gateway có hợp đồng reactive.

Ví dụ:

~~~java
public interface CloudResourceGateway {
    Mono<CloudResource> find(String resourceId);

    Mono<CloudResource> create(CreateResourceCommand command);

    Mono<Void> delete(String resourceId);
}
~~~

Implementation bọc SDK blocking:

~~~java
@Component
public class BlockingCloudResourceGateway
        implements CloudResourceGateway {

    private final LegacyCloudClient client;
    private final Scheduler cloudSdkScheduler;

    public BlockingCloudResourceGateway(
            LegacyCloudClient client,
            Scheduler cloudSdkScheduler) {
        this.client = client;
        this.cloudSdkScheduler = cloudSdkScheduler;
    }

    @Override
    public Mono<CloudResource> find(String resourceId) {
        return Mono.fromCallable(
                        () -> client.find(resourceId)
                )
                .subscribeOn(cloudSdkScheduler);
    }

    @Override
    public Mono<CloudResource> create(
            CreateResourceCommand command) {
        return Mono.fromCallable(
                        () -> client.create(command)
                )
                .subscribeOn(cloudSdkScheduler);
    }

    @Override
    public Mono<Void> delete(String resourceId) {
        return Mono.fromRunnable(
                        () -> client.delete(resourceId)
                )
                .subscribeOn(cloudSdkScheduler)
                .then();
    }
}
~~~

Domain service có thể compose gateway mà không cần biết SDK dùng blocking:

~~~java
public Mono<ProvisionResult> provision(
        ProvisionCommand command) {
    return cloudResourceGateway.create(
                    command.toCreateResourceCommand()
            )
            .map(resource ->
                    new ProvisionResult(
                            resource.id(),
                            resource.endpoint()
                    )
            );
}
~~~

Cách tách này giúp thay SDK blocking bằng SDK reactive hoặc WebClient trong tương lai mà không thay đổi logic nghiệp vụ.

## 7. Kết hợp reactive và blocking trong một workflow

Một service broker có thể dùng WebClient để gọi một backend, R2DBC để lưu operation và SDK blocking để cấu hình tài nguyên. Không phải toàn bộ workflow cần chạy trên bounded elastic; chỉ đoạn blocking phải được cô lập.

Ví dụ:

~~~java
public Mono<ProvisionResult> provision(
        ProvisionCommand command) {

    return operationRepository.save(
                    OperationRecord.pending(command)
            )
            .flatMap(operation ->
                    cloudGateway.create(command)
                            .flatMap(resource ->
                                    operationRepository
                                            .markResourceCreated(
                                                    operation.id(),
                                                    resource.id()
                                            )
                                            .thenReturn(
                                                    new ProvisionResult(
                                                            operation.id(),
                                                            resource.id()
                                                    )
                                            )
                            )
            );
}
~~~

Nếu cloudGateway là adapter blocking đã dùng subscribeOn, các thao tác R2DBC vẫn chạy trên scheduler reactive phù hợp. Không chuyển toàn bộ pipeline sang bounded elastic chỉ vì một adapter có blocking I/O.

Nếu dùng JDBC đồng bộ thay vì R2DBC, các thao tác database cũng phải được cô lập khỏi event loop. Có thể dùng một JDBC repository adapter riêng chạy trên bounded elastic hoặc cân nhắc chuyển persistence sang R2DBC nếu kiến trúc yêu cầu reactive end-to-end.

### 7.1. Không trộn transaction reactive và transaction JDBC tùy tiện

Reactive transaction manager thường quản lý transaction qua Reactor Context. JDBC transaction manager dùng thread-bound transaction context. Không giả định một transaction reactive tự động bao trùm một lời gọi JDBC blocking được chuyển sang thread khác.

Nếu cần transaction JDBC, thực hiện phần JDBC trong ranh giới transaction đồng bộ được quản lý phù hợp trên blocking scheduler. Không giữ transaction database mở trong khi gọi API cloud hoặc HTTP bên ngoài. Dùng operation record và outbox để điều phối side effect giữa các hệ thống.

## 8. Giới hạn concurrency và bảo vệ backend

Chuyển blocking call sang bounded elastic ngăn event loop bị chặn, nhưng không có nghĩa broker có thể gửi số lượng request không giới hạn tới backend.

Ví dụ, backend chỉ cho phép 20 kết nối đồng thời. Nếu scheduler có 100 thread và mọi thread đều gọi backend, broker có thể vượt quota hoặc làm backend quá tải.

Cần áp dụng bulkhead hoặc semaphore theo backend:

~~~java
public Mono<CloudResource> find(String id) {
    return Mono.fromCallable(() -> client.find(id))
            .subscribeOn(cloudSdkScheduler)
            .transformDeferred(
                    BulkheadOperator.of(cloudBulkhead)
            );
}
~~~

Đoạn code minh họa với Resilience4j Reactor integration; dependency và cách cấu hình cần khớp phiên bản thư viện trong ứng dụng. Có thể dùng Semaphore hoặc giới hạn concurrency ở tầng service nếu không dùng Resilience4j.

Một pipeline xử lý nhiều tài nguyên có thể giới hạn số tác vụ đồng thời bằng flatMap:

~~~java
Flux.fromIterable(resourceIds)
        .flatMap(
                cloudGateway::find,
                8
        );
~~~

Ở đây tối đa tám lời gọi reactive đang được subscribe đồng thời qua gateway. Concurrency phải phù hợp với scheduler, connection pool và quota backend. Không dùng parallel() như một cách thay thế cho giới hạn I/O blocking.

### 8.1. Backpressure không tự giới hạn mọi lời gọi blocking

Reactive Streams có cơ chế backpressure, nhưng khi ứng dụng chuyển dữ liệu sang các API imperative hoặc tạo nhiều task nóng ngoài pipeline, backpressure có thể không bảo vệ được backend.

Hãy giữ công việc ở dạng lazy Publisher, tránh tạo Future hoặc submit task thủ công trước khi có demand. Kết hợp giới hạn concurrency, queue capacity và rate limit ở ranh giới adapter.

## 9. Timeout và cancellation

Có ít nhất hai loại timeout cần phân biệt:

- Timeout ở Reactor pipeline: giới hạn thời gian chờ của subscriber.
- Timeout ở client/backend: giới hạn thời gian kết nối, đọc hoặc thực thi tại thư viện bên dưới.

Ví dụ:

~~~java
public Mono<CloudResource> find(String id) {
    return Mono.fromCallable(() -> client.find(id))
            .subscribeOn(cloudSdkScheduler)
            .timeout(Duration.ofSeconds(5));
}
~~~

Timeout Reactor phát tín hiệu lỗi khi thời gian vượt quá giới hạn. Tuy nhiên, điều đó không bảo đảm một lời gọi blocking đang chạy sẽ lập tức dừng. Một số thư viện không hỗ trợ interrupt hoặc cancellation. Vì vậy cần cấu hình connect/read/request timeout ngay trong SDK nếu có.

Nếu timeout xảy ra sau khi backend đã thực hiện side effect, kết quả có thể không xác định. Với create/delete, broker cần dùng idempotency key hoặc lookup backend trước khi retry. Không coi timeout là bằng chứng thao tác chưa xảy ra.

### 9.1. Cancellation không phải rollback

Platform hoặc client có thể đóng kết nối sau khi request đã được chấp nhận. Cancellation của reactive subscription không tự động thu hồi tài nguyên đã tạo ở backend.

Đối với thao tác ngắn đồng bộ, cancellation có thể ngăn các bước tiếp theo nếu chúng chưa bắt đầu. Đối với workflow provision/deprovision dài, broker nên lưu operation bền vững và điều phối bằng worker. Không gắn toàn bộ vòng đời tài nguyên vào sự tồn tại của HTTP subscription.

Nếu cần hỗ trợ hủy nghiệp vụ, hãy xây dựng một lệnh cancel riêng với state machine, kiểm tra bước hiện tại và compensation. Không dùng việc client ngắt kết nối như một lệnh hủy ngầm.

## 10. Retry và lỗi khi gọi SDK blocking

Retry một lời gọi blocking thường được thực hiện ở mức Publisher:

~~~java
return Mono.fromCallable(() -> client.describe(resourceId))
        .subscribeOn(cloudSdkScheduler)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(200))
                        .filter(this::isTransientFailure)
        );
~~~

Khi retry, callable được subscribe lại và SDK được gọi lại. Điều này chỉ an toàn nếu thao tác là read-only hoặc backend hỗ trợ idempotency. Không tự động retry create, charge, revoke hoặc delete chỉ vì lỗi có vẻ tạm thời.

Phân loại lỗi:

| Lỗi | Xử lý gợi ý |
|---|---|
| Connect timeout trước khi gửi request | Có thể retry theo chính sách |
| HTTP 429 hoặc rate limit | Tôn trọng Retry-After, giảm concurrency |
| HTTP 5xx | Retry có giới hạn nếu thao tác an toàn |
| Authentication/authorization | Không retry mù quáng; sửa credentials hoặc quyền |
| Validation error | Không retry; sửa input |
| Timeout sau khi gửi create | Tra cứu resource hoặc dùng idempotency key |
| Cancellation | Không tự coi là lỗi backend hay rollback |

Không retry mọi exception. Cần giới hạn số lần thử, dùng backoff có jitter và ghi metric. Với tác vụ dài, retry nên được lưu bền vững trong operation/queue thay vì giữ HTTP request mở.

## 11. Context propagation và logging

Khi pipeline chuyển từ event loop sang bounded elastic, thread thay đổi. Các giá trị lưu trong ThreadLocal như MDC, security context hoặc request-scoped data có thể không tự xuất hiện trên thread mới.

Trong Reactor, dữ liệu theo subscription nên được truyền bằng Reactor Context thay vì giả định một thread cố định. Ví dụ:

~~~java
Mono.deferContextual(context -> {
    String correlationId =
            context.get("correlationId");

    return Mono.fromCallable(
                    () -> client.describe(resourceId, correlationId)
            )
            .subscribeOn(cloudSdkScheduler);
});
~~~

Ví dụ này đọc correlation ID từ Reactor Context rồi truyền tường minh vào SDK. Nếu cần tích hợp MDC hoặc tracing, dùng cơ chế context propagation tương thích với phiên bản Reactor, Micrometer Tracing và Spring đang triển khai.

Không lưu tenant identity hoặc quyền truy cập chỉ trong ThreadLocal rồi kỳ vọng chúng tự truyền qua scheduler. Dữ liệu authorization quan trọng nên được truyền rõ qua command hoặc security context đã được xác thực.

Log nên có:

- operation_id và instance_id.
- backend/provider.
- loại thao tác.
- thời gian chờ scheduler và thời gian gọi SDK.
- kết quả hoặc mã lỗi đã chuẩn hóa.
- correlation/trace ID.

Không ghi password, access token hoặc toàn bộ parameters nhạy cảm.

## 12. Phân biệt blocking call ngắn với operation dài

Bounded elastic là cơ chế cô lập blocking call, không phải hệ thống quản lý workflow bền vững.

Có thể dùng scheduler cho thao tác blocking ngắn trong request path, ví dụ đọc metadata hoặc gọi SDK để xác minh trạng thái. Nhưng nếu provision database mất vài phút, có nhiều bước, cần retry sau restart hoặc cần platform polling tiến độ, nên ghi operation và chuyển sang worker bền vững.

| Đặc điểm | Bounded elastic trong request | Queue/worker bền vững |
|---|---|---|
| Thời gian | Ngắn, có giới hạn | Dài hoặc nhiều bước |
| Sống sót khi restart | Subscription bị mất; không tự phục hồi | Operation và message được lưu bền vững |
| Retry | Trong thời gian subscription | Có lịch retry và trạng thái lưu |
| Theo dõi | Response HTTP | Operation/last_operation |
| Phù hợp | I/O blocking nhỏ, có timeout | Provision, update, deprovision kéo dài |

Một worker nền vẫn có thể gọi SDK blocking. Khi đó worker cần executor hoặc scheduler có giới hạn riêng, đồng thời dùng operation record, lease, idempotency và retry bền vững.

## 13. Kiểm thử để phát hiện blocking trên event loop

Một test hữu ích là kiểm tra tên thread trong lời gọi blocking adapter:

~~~java
@Test
void blockingClientRunsOutsideReactorEventLoop() {
    AtomicReference<String> threadName = new AtomicReference<>();

    Mono<String> result = Mono.fromCallable(() -> {
                threadName.set(Thread.currentThread().getName());
                return "ok";
            })
            .subscribeOn(Schedulers.boundedElastic());

    StepVerifier.create(result)
            .expectNext("ok")
            .verifyComplete();

    assertThat(threadName.get())
            .doesNotContain("reactor-http");
}
~~~

Tên thread cụ thể phụ thuộc runtime và cấu hình, vì vậy test thực tế nên kiểm tra scheduler hoặc thread prefix đã cấu hình thay vì dựa duy nhất vào một tên mặc định.

Các kịch bản nên kiểm thử:

- Callable chỉ chạy khi có subscription.
- Blocking call chạy trên scheduler được chọn.
- Event loop vẫn phục vụ request khác khi SDK chậm.
- Timeout được phát đúng thời hạn.
- Lỗi SDK được chuyển thành onError và được ánh xạ đúng.
- Retry chỉ xảy ra với lỗi được cho phép.
- Concurrency không vượt giới hạn bulkhead.
- Cancellation không làm broker đánh dấu operation thành công giả.
- Context/correlation ID vẫn được truyền đúng.
- Scheduler được dispose khi application context đóng.

Có thể dùng BlockHound trong môi trường test để phát hiện một số lời gọi blocking trên thread được đánh dấu non-blocking. Cần cấu hình tương thích với phiên bản Reactor và thư viện đang dùng, đồng thời xử lý các trường hợp blocking được cho phép có chủ đích.

## 14. Quan sát scheduler và chẩn đoán nghẽn

Khi latency tăng, cần phân biệt:

- Event loop bị block.
- Bounded elastic thread đã bão hòa.
- Hàng đợi scheduler tăng.
- Backend chậm hoặc giới hạn quota.
- Connection pool cạn.
- CPU-bound computation chiếm scheduler parallel.

Các chỉ số nên theo dõi:

| Chỉ số | Ý nghĩa |
|---|---|
| Blocking task duration | Thời gian thực thi SDK/JDBC |
| Scheduler queue delay | Thời gian task chờ trước khi chạy |
| Active blocking threads | Số thread đang thực thi blocking call |
| Rejected task count | Số task không được scheduler nhận |
| Backend timeout rate | Tỷ lệ timeout từ SDK |
| Bulkhead rejected count | Số lời gọi bị từ chối do giới hạn concurrency |
| Event loop latency | Độ trễ xử lý event loop |
| Request latency | Độ trễ endpoint broker |

Không dùng instance ID hoặc tenant ID làm metric label có cardinality cao. Dùng label có tập giá trị giới hạn như provider, operation type và result.

Khi điều tra, hãy so sánh thời gian chờ scheduler với thời gian backend. Nếu queue delay cao nhưng backend latency bình thường, scheduler có thể thiếu capacity hoặc nhận quá nhiều task. Nếu queue delay thấp nhưng backend latency cao, cần kiểm tra provider, network và timeout.

## 15. Những lỗi triển khai thường gặp

- **Gọi SDK trước khi tạo Mono:** blocking đã xảy ra trên thread hiện tại.
- **Chỉ dùng publishOn sau Mono.just:** không chuyển lời gọi đã chạy sang scheduler khác.
- **Dùng parallel cho I/O blocking:** chiếm thread dành cho CPU-bound work.
- **Dùng @Async tùy tiện:** tạo thêm executor nhưng không có giới hạn hoặc quản lý lifecycle rõ ràng.
- **Tạo scheduler cho từng request:** gây rò rỉ thread và khó kiểm soát tải.
- **Không giới hạn queue:** tác vụ chờ quá lâu, làm tăng latency và bộ nhớ.
- **Chỉ đặt timeout Reactor:** SDK blocking có thể tiếp tục chạy sau khi subscriber timeout.
- **Retry create không idempotent:** tạo tài nguyên trùng sau timeout.
- **Dùng block() trong WebFlux handler:** chặn event loop và phá vỡ pipeline reactive.
- **Gọi subscribe() thủ công trong service:** tách side effect khỏi lifecycle và error handling của caller.
- **Giữ transaction trong lúc gọi cloud API:** giữ connection/lock quá lâu và tạo rủi ro nhất quán.
- **Coi scheduler là durable queue:** công việc đang chạy không tự phục hồi sau process restart.

## 16. Quy trình áp dụng trong Spring Cloud Service Broker

Khi tích hợp một thư viện hạ tầng vào broker, hãy thực hiện:

1. Kiểm tra API có thực sự non-blocking hay không.
2. Nếu có API reactive/async ổn định, ưu tiên dùng API đó.
3. Nếu buộc dùng SDK blocking, cô lập trong adapter.
4. Bao bọc lời gọi bằng Mono.fromCallable, fromRunnable hoặc cơ chế Publisher phù hợp.
5. Đặt subscribeOn trên boundedElastic hoặc scheduler riêng.
6. Đặt giới hạn thread, queue và concurrency theo quota backend.
7. Cấu hình timeout tại SDK và timeout tổng ở reactive pipeline.
8. Chỉ retry thao tác an toàn hoặc có idempotency key.
9. Truyền correlation và security context một cách tường minh.
10. Không gọi block hoặc subscribe thủ công trong handler.
11. Dùng operation/queue bền vững cho workflow dài.
12. Kiểm thử thread, timeout, cancellation, retry và quá tải.
13. Theo dõi scheduler queue delay, backend latency và event loop responsiveness.

## Kết luận

Trong WebFlux, lời gọi blocking phải được cô lập khỏi Reactor event loop. Với thao tác I/O ngắn, hãy bọc SDK bằng Mono.fromCallable hoặc fromRunnable và dùng subscribeOn với boundedElastic hoặc scheduler riêng có giới hạn. publishOn chỉ chuyển các operator phía sau nó; nó không thể sửa một lời gọi blocking đã chạy trước khi Publisher được tạo.

Trong Spring Cloud Service Broker, hãy đặt ranh giới blocking tại adapter, giới hạn concurrency theo khả năng backend, cấu hình timeout ở cả Reactor và SDK, đồng thời chỉ retry khi thao tác an toàn. Scheduler giúp chạy lời gọi blocking mà không chiếm event loop; nó không thay thế operation record và worker bền vững cho provision, update hoặc deprovision kéo dài.
