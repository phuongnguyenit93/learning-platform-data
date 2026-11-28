# Reactor Mono trong các giao diện dịch vụ của framework

Spring Cloud Open Service Broker sử dụng Reactor để biểu diễn kết quả của các thao tác service broker dưới dạng publisher. Nhiều service interface của framework nhận request model rồi trả về một kiểu như Mono chứa response model. Điều này cho phép ứng dụng kết hợp việc đọc state store, kiểm tra quyền, gọi cloud provider và xử lý operation bất đồng bộ mà không phải giữ một HTTP request thread trong suốt thời gian chờ I/O.

Với module SPRING_CLOUD_SERVICE_BROKER, Mono là hợp đồng giữa phần xử lý nghiệp vụ của broker và framework OSB. Handler nên trả publisher mô tả toàn bộ công việc cần thực hiện; framework sẽ subscribe để thực thi và chuyển kết quả thành HTTP response. Hiểu đúng cách Mono phát giá trị, hoàn tất rỗng, phát lỗi, retry và cancellation giúp tránh tạo tài nguyên hai lần, trả response thiếu dữ liệu hoặc để tác vụ tiếp tục chạy ngoài kiểm soát.

## 1. Mono là gì trong service interface

Mono là một Reactor Publisher phát tối đa một phần tử rồi kết thúc. Một publisher Mono có thể:

- Phát đúng một response rồi complete.
- Complete mà không phát response.
- Phát một error rồi kết thúc.
- Không phát gì trong một khoảng thời gian cho đến khi nguồn dữ liệu hoàn tất.

Một service interface có thể biểu diễn kết quả bằng kiểu:

~~~java
public interface ExampleService {
    Mono<ExampleResponse> handle(ExampleRequest request);
}
~~~

Trong Spring Cloud Open Service Broker, các extension point cho service instance, service binding và last operation dùng kiểu trả về reactive tương ứng với model của framework. Tên method, tham số và response type cụ thể cần theo phiên bản dependency mà ứng dụng đang sử dụng; nguyên tắc chung là trả Mono của response thay vì tự tạo HTTP response trong service implementation.

Mono không phải một thread, cũng không tự tạo thread mới. Nó là mô tả một pipeline xử lý. Việc thực thi thường bắt đầu khi có subscriber. Scheduler chỉ tham gia khi pipeline yêu cầu chuyển execution sang scheduler đó, chẳng hạn để gọi API blocking trên bounded elastic.

## 2. Ba kết quả cần phân biệt: value, empty và error

Ba kết quả của Mono có ý nghĩa khác nhau:

| Kết quả | Ý nghĩa trong ứng dụng | Cách dùng thường gặp |
|---|---|---|
| Một value | Thao tác tạo được response hợp lệ | Trả CreateServiceInstanceResponse hoặc binding response |
| Empty completion | Không có phần tử để trả | Trường hợp tùy chọn hoặc luồng được thiết kế rõ ràng là không có body |
| Error | Thao tác không thể hoàn tất theo hợp đồng | Instance không tồn tại, validation thất bại, backend lỗi hoặc conflict |

Không được xem Mono.empty() là cách chung để báo “không tìm thấy”. Với thao tác cần response, empty có thể khiến framework nhận được kết thúc không có body trong khi caller mong đợi response model. Khi instance hoặc binding không tồn tại, hãy phát domain/framework exception phù hợp để OSB adapter ánh xạ thành HTTP response đúng hợp đồng.

Ngược lại, không phát exception chỉ vì một trường tùy chọn không có giá trị. Ví dụ, dashboard URL có thể không được cấu hình; response mapper có thể bỏ trường tùy chọn trong khi vẫn trả response đầy đủ.

## 3. Mono thường lazy và thực thi khi subscribe

Các operator của Reactor thường tạo pipeline mà chưa chạy công việc ngay. Ví dụ:

~~~java
Mono<String> result = Mono.fromSupplier(() -> {
    System.out.println("Đọc cấu hình");
    return "ready";
});
~~~

Khi tạo biến result, supplier chưa được gọi. Khi có subscriber, supplier mới được thực thi. Đặc tính này cho phép framework kiểm soát thời điểm thực thi và kết hợp nhiều bước trong một pipeline.

Operator defer giúp trì hoãn cả việc tạo publisher:

~~~java
Mono<ProvisionCommand> command =
        Mono.defer(() -> Mono.just(requestMapper.toCommand(request)));
~~~

Defer hữu ích khi việc tạo publisher hoặc đọc context phải xảy ra tại thời điểm subscription. Nó cũng bảo đảm mỗi subscription gọi lại supplier. Vì vậy, nếu pipeline chứa tác dụng phụ như provision resource, nhiều subscription có thể thực hiện công việc nhiều lần. Cần kết hợp idempotency và state transition bền vững; không dựa vào giả định rằng Mono chỉ được subscribe đúng một lần.

Không dùng cache một cách tùy tiện để “chống chạy hai lần”. Cache có thể giữ lại kết quả và thay đổi semantics của lỗi, thời gian sống hoặc dữ liệu theo caller. Với thao tác thay đổi tài nguyên, cơ chế chống trùng phải nằm trong application service và state store.

## 4. map và flatMap

Hai operator được dùng thường xuyên trong service implementation:

- map chuyển một giá trị sang một giá trị khác bằng phép biến đổi đồng bộ.
- flatMap chuyển một giá trị thành một publisher khác rồi nối publisher đó vào pipeline.

Ví dụ map để chuyển domain result thành response:

~~~java
Mono<CreateServiceInstanceResponse> response =
        provisionService.provision(command)
                .map(responseMapper::toResponse);
~~~

Ví dụ flatMap khi bước tiếp theo cần gọi repository hoặc backend client trả Mono:

~~~java
Mono<ServiceInstance> instance =
        instanceRepository.findById(instanceId)
                .flatMap(record ->
                        backendClient.inspect(record.resourceId())
                                .map(snapshot -> mapper.merge(record, snapshot)));
~~~

Nếu dùng map với một hàm trả Mono, kết quả sẽ là Mono<Mono<T>>. Khi muốn nối công việc bất đồng bộ, dùng flatMap để tránh publisher lồng nhau.

Không đưa tác dụng phụ blocking hoặc thao tác dài vào map chỉ vì cú pháp ngắn. map nên dành cho phép biến đổi nhanh, không chờ mạng và không chiếm event loop.

## 5. Ghép nhiều bước xử lý tuần tự

Một yêu cầu provision thường cần:

1. Chuyển request OSB thành command nội bộ.
2. Xác thực caller và xác định tenant.
3. Tìm service definition/plan.
4. Kiểm tra parameters và entitlement.
5. Reserve quota và ghi operation.
6. Gọi backend hoặc gửi công việc cho worker.
7. Chuyển kết quả thành response.

Các bước có phụ thuộc dữ liệu nên được nối bằng flatMap hoặc then:

~~~java
public Mono<CreateServiceInstanceResponse> create(
        CreateServiceInstanceRequest request) {

    return Mono.defer(() -> {
        ProvisionCommand command = requestMapper.toCommand(request);

        return tenantResolver.resolve(request)
                .flatMap(tenant -> catalogService.findPlan(
                        command.serviceId(), command.planId())
                        .flatMap(plan -> validator.validate(
                                command, tenant, plan)
                                .then(provisionService.provision(
                                        command, tenant, plan))))
                .map(responseMapper::toResponse);
    });
}
~~~

Đây là ví dụ kiến trúc; tên model và method là của ứng dụng minh họa. Điểm quan trọng là mỗi bước chỉ chạy sau khi publisher của bước trước phát kết quả hoặc complete theo semantics đã định nghĩa.

then dùng khi chỉ cần chờ một publisher hoàn tất và bỏ qua giá trị của nó. Ví dụ validator có thể trả Mono<Void>; sau khi validation complete, pipeline tiếp tục sang provision. Nếu validator phát error, bước provision sẽ không chạy.

~~~java
validator.validate(command)
        .then(quotaService.reserve(command))
        .flatMap(reservation -> operationService.start(reservation));
~~~

Nếu publisher trước complete rỗng, then vẫn tiếp tục publisher sau. Đây là hành vi hữu ích với Mono<Void>, nhưng cần cẩn thận nếu publisher trước đáng lẽ phải có value; trong trường hợp đó, dùng switchIfEmpty để biến missing value thành lỗi có ý nghĩa.

## 6. Ghép các công việc độc lập

Một số kiểm tra độc lập có thể chạy song song. Ví dụ broker cần đọc feature policy và quota snapshot, cả hai đều không phụ thuộc kết quả của nhau:

~~~java
Mono<FeaturePolicy> policy = policyClient.loadPolicy(tenantId);
Mono<QuotaSnapshot> quota = quotaClient.loadQuota(tenantId);

return Mono.zip(policy, quota)
        .flatMap(tuple -> validator.validate(
                command, tuple.getT1(), tuple.getT2()));
~~~

Chỉ chạy song song khi các thao tác thực sự độc lập và backend chịu được tải đồng thời. Không dùng zip để chạy hai lệnh thay đổi cùng resource nếu thứ tự của chúng có ý nghĩa.

Mono.zip cần mỗi nguồn cung cấp value. Nếu một nguồn complete rỗng, zip có thể complete mà không tạo tuple và các bước tiếp theo sẽ không chạy. Nếu một nguồn là Mono<Void>, dùng Mono.when cho các side effect độc lập hoặc chuyển kết quả thành một marker có giá trị trước khi zip.

~~~java
return Mono.when(auditService.recordRequest(command),
                 metricsService.recordAccepted(command))
        .then(operationService.start(command));
~~~

Audit/metrics không nên làm hỏng thao tác nghiệp vụ nếu chúng được thiết kế là best-effort; khi đó cần xử lý lỗi riêng và không được âm thầm nuốt lỗi của bước bắt buộc như reservation hoặc authorization.

## 7. Triển khai service interface theo kiểu reactive

Một service instance handler nên điều phối use case và trả publisher cho framework:

~~~java
@Override
public Mono<CreateServiceInstanceResponse> createServiceInstance(
        CreateServiceInstanceRequest request) {

    return Mono.defer(() -> {
        ProvisionCommand command = requestMapper.toCommand(request);

        return provisionApplicationService.execute(command)
                .map(responseMapper::toCreateResponse);
    });
}
~~~

Đối với binding, cấu trúc tương tự:

~~~java
@Override
public Mono<CreateServiceInstanceBindingResponse>
createServiceInstanceBinding(CreateServiceInstanceBindingRequest request) {

    return Mono.defer(() -> {
        CreateBindingCommand command = bindingRequestMapper.toCommand(request);

        return bindingApplicationService.create(command)
                .map(bindingResponseMapper::toResponse);
    });
}
~~~

Các chữ ký trên minh họa kiểu extension point thường gặp. Cần xác nhận đúng interface và generic response type trong phiên bản Spring Cloud Open Service Broker của dự án. Handler không nên chứa toàn bộ policy, SQL hoặc SDK call; application service điều phối nghiệp vụ, repository quản lý state, adapter giao tiếp hạ tầng và mapper tạo response.

## 8. Mono cho thao tác bất đồng bộ của OSB

Mono trả response HTTP và OSB asynchronous operation là hai lớp khác nhau:

- Mono biểu diễn việc xử lý request handler và tạo HTTP response.
- OSB operation biểu diễn công việc nghiệp vụ có thể tiếp tục sau khi HTTP request đã kết thúc.

Nếu provision hoàn tất nhanh, handler có thể trả Mono chứa response thành công sau khi resource được xác nhận.

Nếu provision cần thời gian dài và nền tảng gửi accepts_incomplete=true, broker thường ghi operation bền vững, chuyển trạng thái instance sang provisioning và trả response accepted chứa operation key. Worker độc lập tiếp tục công việc. Mono của HTTP request có thể complete ngay sau khi response accepted được tạo; nó không cần tồn tại suốt thời gian provision.

~~~java
public Mono<CreateServiceInstanceResponse> create(
        ProvisionCommand command) {

    return operationService.accept(command)
            .map(accepted -> responseMapper.toAcceptedResponse(accepted));
}
~~~

Worker xử lý operation qua một pipeline riêng, đọc operation từ state store, thực hiện checkpoint, gọi backend và ghi terminal result. Không gắn toàn bộ provisioning vào subscription HTTP rồi mong công việc tự sống sót khi client ngắt kết nối hoặc gateway timeout.

## 9. Xử lý lỗi bằng onErrorMap và onErrorResume

Reactor truyền lỗi trong pipeline dưới dạng terminal signal. Khi một bước phát error, các bước tiếp theo không chạy cho đến khi có operator phục hồi hoặc thay thế lỗi.

onErrorMap chuyển loại exception:

~~~java
return backendClient.createDatabase(command)
        .onErrorMap(BackendQuotaException.class,
                error -> new ServiceQuotaExceededException());
~~~

onErrorResume chọn một publisher thay thế:

~~~java
return catalogRepository.findPlan(serviceId, planId)
        .switchIfEmpty(Mono.error(new UnknownPlanException()))
        .onErrorResume(CatalogTemporarilyUnavailableException.class,
                error -> Mono.error(new DependencyUnavailableException()));
~~~

Không dùng onErrorResume với Exception chung để trả một response thành công mặc định. Cách đó có thể biến lỗi authorization, validation hoặc backend thành success giả. Chỉ phục hồi các loại lỗi đã xác định và có hành vi thay thế an toàn.

Không để raw exception hoặc stack trace đi vào response OSB. Hãy giữ cause cho log nội bộ có kiểm soát và ánh xạ sang domain/framework exception với thông điệp công khai đã chuẩn hóa.

## 10. switchIfEmpty và trường hợp không tìm thấy

Repository có thể trả Mono.empty() khi không có record:

~~~java
return instanceRepository.findById(instanceId)
        .switchIfEmpty(Mono.error(new ServiceInstanceNotFoundException()))
        .flatMap(instance -> operationService.inspect(instance));
~~~

switchIfEmpty chỉ chạy publisher thay thế khi nguồn complete mà không có value. Nó không bắt lỗi database; lỗi kết nối vẫn đi theo error channel.

Điều này giúp phân biệt ba tình huống:

- Không có instance: domain not found.
- Không đọc được state store: dependency error.
- Có instance nhưng không có trường tùy chọn: trả response với trường đó bị lược bỏ hoặc null theo schema.

Nếu repository trả Mono<Void>, không thể dùng sự có mặt của value để kết luận record tồn tại; cần API kiểm tra riêng hoặc trả một kiểu kết quả có ý nghĩa.

## 11. Không tự subscribe trong service handler

Một lỗi nghiêm trọng là tự gọi subscribe() bên trong method của service interface:

~~~java
// Không làm như thế này
public Mono<CreateServiceInstanceResponse> create(
        ProvisionCommand command) {

    backendClient.createDatabase(command).subscribe();
    return Mono.just(responseMapper.accepted());
}
~~~

Đoạn code trên tách tác dụng phụ khỏi pipeline do framework quản lý. Framework có thể nhận response accepted trước khi backend hoàn tất; lỗi của backend không còn được nối với request; cancellation và tracing không còn theo dõi được công việc đó. Nếu cần xử lý bất đồng bộ, hãy lưu operation/outbox rồi để worker độc lập thực hiện.

Tương tự, không gọi block(), toFuture().join() hoặc sleep trong handler reactive. Những thao tác đó chặn thread và có thể làm cạn event loop, giảm throughput của toàn broker.

Hãy trả publisher:

~~~java
return backendClient.createDatabase(command)
        .map(responseMapper::toCreateResponse);
~~~

Framework sẽ subscribe theo vòng đời request. Ứng dụng không cần tự tạo subscription để kích hoạt pipeline.

## 12. Tích hợp thư viện blocking

Không phải mọi thư viện mà broker sử dụng đều reactive. JPA/JDBC, một số cloud SDK và file I/O có thể blocking. Không gọi trực tiếp chúng trên event-loop.

Với một tác vụ blocking độc lập:

~~~java
return Mono.fromCallable(() -> jdbcRepository.loadInstance(instanceId))
        .subscribeOn(Schedulers.boundedElastic())
        .flatMap(instance -> backendClient.inspect(instance.resourceId()));
~~~

fromCallable trì hoãn lời gọi cho đến khi subscription; subscribeOn chuyển việc thực thi nguồn blocking sang boundedElastic. Không dùng parallel scheduler cho I/O blocking.

Nếu nhiều câu lệnh JDBC/JPA phải cùng một transaction, hãy giữ toàn bộ transaction blocking trong một boundary được offload như một đơn vị. Không tách từng repository call sang các scheduler khác nhau rồi kỳ vọng transaction thread-bound tiếp tục tồn tại.

Với R2DBC và ReactiveTransactionManager, có thể dùng TransactionalOperator để bao quanh publisher:

~~~java
return transactionalOperator.transactional(
        instanceRepository.save(instance)
                .then(operationRepository.save(operation))
                .then(outboxRepository.save(event)));
~~~

Không giả định @Transactional kiểu imperative tự động cung cấp transaction reactive cho mọi publisher. Chọn transaction manager phù hợp với công nghệ persistence và giữ ranh giới transaction rõ ràng.

## 13. Timeout và retry

Gọi backend có thể bị treo hoặc trả lỗi tạm thời. timeout đặt giới hạn cho một publisher:

~~~java
return backendClient.inspect(resourceId)
        .timeout(Duration.ofSeconds(5));
~~~

Timeout không chứng minh backend chưa thực hiện tác dụng phụ. Ví dụ, lệnh tạo database có thể đã thành công ở provider nhưng response bị mất. Trước khi retry, broker phải dùng idempotency key hoặc tra cứu resource theo ownership metadata để xác định kết quả thực tế.

Retry chỉ áp dụng cho lỗi tạm thời đã phân loại:

~~~java
return backendClient.inspect(resourceId)
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
                .filter(this::isTransientFailure));
~~~

Không retry tự động lỗi validation, authorization hoặc quota exceeded. Không retry thao tác tạo/xóa resource nếu adapter chưa idempotent. Cần giới hạn số lần thử, dùng backoff và jitter, đồng thời ghi nhận attempt trong operation state nếu workflow kéo dài.

## 14. Cancellation và tác vụ có tác dụng phụ

Reactive stream có thể bị cancel khi HTTP client ngắt kết nối, timeout xảy ra ở gateway hoặc downstream không còn cần kết quả. Cancellation là tín hiệu dừng subscription; nó không bảo đảm một lệnh đã gửi đến cloud provider được hủy.

Vì vậy:

- Với thao tác đọc thuần túy, cancellation thường có thể dừng công việc không cần thiết.
- Với thao tác ghi, phải xác định thời điểm tác dụng phụ đã được gửi và trạng thái cần reconcile.
- Với OSB async operation, lưu operation bền vững rồi giao cho worker; việc HTTP subscription kết thúc không được xóa operation.
- Không dùng doFinally để giả định mọi cancellation đều đồng nghĩa backend đã rollback.

Nếu pipeline tạo tài nguyên trực tiếp trong request, cần có compensation/reconciliation cho trường hợp client disconnect sau khi backend đã nhận lệnh nhưng trước khi broker ghi state.

## 15. Reactor Context và thông tin theo request

Trong ứng dụng reactive, không nên phụ thuộc ThreadLocal để truyền thông tin theo request qua các bước có thể chạy trên nhiều thread. Reactor Context là nơi phù hợp để mang metadata như correlation ID hoặc security context trong pipeline.

Ví dụ minh họa:

~~~java
return provisionService.provision(command)
        .contextWrite(context -> context.put("correlationId", correlationId));
~~~

Các operator có thể chuyển execution giữa scheduler; ThreadLocal hoặc MDC không tự động luôn giữ giá trị như mong đợi nếu chưa cấu hình context propagation. Không lưu credentials hoặc dữ liệu nhạy cảm trong Context chỉ vì nó tiện truy cập.

Với Spring Security reactive, dùng cơ chế Reactor Context của framework để đọc Authentication. Không lấy SecurityContext từ imperative ThreadLocal bên trong pipeline reactive.

Correlation ID nên được dùng trong log và trace để nối request handler với operation/worker. Khi chuyển sang background worker, ghi correlation ID vào operation record hoặc event vì Reactor Context của HTTP request không tự tồn tại trong subscription mới của worker.

## 16. Thiết kế response mapper và domain service

Không để domain service phụ thuộc trực tiếp vào response model HTTP nếu có thể tránh. Một cấu trúc phân lớp:

| Thành phần | Trách nhiệm |
|---|---|
| OSB service interface implementation | Nhận request model và trả Mono response |
| Request mapper | Chuyển framework request thành command nội bộ |
| Application service | Điều phối validation, authorization, state và operation |
| Domain service | Áp dụng quy tắc plan, binding, quota và lifecycle |
| Repository/client port | Khai báo nhu cầu đọc/ghi state hoặc gọi provider |
| Infrastructure adapter | Thực hiện persistence và API cloud |
| Response mapper | Chuyển application result thành model Spring Cloud OSB |

Ví dụ:

~~~java
@Override
public Mono<DeleteServiceInstanceResponse> deleteServiceInstance(
        DeleteServiceInstanceRequest request) {

    return Mono.defer(() -> {
        DeprovisionCommand command = requestMapper.toCommand(request);

        return deprovisionApplicationService.execute(command)
                .map(responseMapper::toDeleteResponse);
    });
}
~~~

Nếu deprovision được chấp nhận bất đồng bộ, application service trả một kết quả accepted có operation ID. Response mapper chuyển kết quả đó thành response model của framework. Worker tiếp tục workflow bên ngoài subscription của handler.

## 17. Kiểm thử Mono bằng StepVerifier

Không cần subscribe thủ công để kiểm tra pipeline. Reactor Test cung cấp StepVerifier để xác nhận signal theo thứ tự:

~~~java
StepVerifier.create(service.createServiceInstance(request))
        .assertNext(response -> {
            assertThat(response).isNotNull();
        })
        .verifyComplete();
~~~

Kiểm thử trường hợp lỗi:

~~~java
StepVerifier.create(service.createServiceInstance(invalidRequest))
        .expectErrorMatches(error ->
                error instanceof InvalidServiceParametersException)
        .verify();
~~~

Kiểm thử trường hợp empty:

~~~java
StepVerifier.create(optionalLookup.findDashboardUrl(instanceId))
        .verifyComplete();
~~~

Chỉ dùng empty khi hợp đồng của use case cho phép không có value. Với service interface cần response, test nên xác nhận publisher phát đúng response hoặc lỗi rõ ràng.

Các trường hợp cần kiểm thử:

- Publisher phát đúng một response và complete.
- Validation error không gọi backend.
- Repository empty được chuyển thành not-found error ở use case bắt buộc.
- Backend error được ánh xạ đúng loại domain/framework exception.
- Retry chỉ xảy ra với lỗi transient và số lần thử bị giới hạn.
- Timeout sau side effect dẫn đến reconcile, không tạo resource trùng.
- Cancellation không làm mất operation đã được lưu bền vững.
- Hai subscription hoặc hai request retry không tạo hai logical resources.
- Blocking adapter chạy trên boundedElastic, không chặn event loop.

Với timeout/retry cần kiểm tra thời gian, có thể dùng virtual time của Reactor Test để tránh test phải chờ thật. Với HTTP boundary, dùng WebTestClient để xác nhận framework ánh xạ response model và exception thành status/body OSB như mong đợi.

## 18. Quan sát và vận hành reactive pipeline

Các metric nên theo dõi:

- Số request đang xử lý và thời gian handler hoàn tất.
- Tỷ lệ Mono empty, success và error theo use case.
- Số timeout, retry và backend dependency failure.
- Độ trễ của repository và provider client.
- Số operation được accepted, đang chạy và terminal.
- Số cancellation và tác vụ cần reconcile sau cancellation.
- Mức sử dụng boundedElastic và số tác vụ blocking đang chờ.
- Số lỗi transaction hoặc optimistic locking conflict.

Không dùng instance ID, binding ID, tenant ID hoặc operation ID làm metric label có cardinality không giới hạn. Dùng metric tag có tập giá trị giới hạn như operation type, outcome và dependency name; định danh cụ thể có thể ghi trong log/tracing có kiểm soát.

Khi log lỗi, không ghi request body đầy đủ nếu parameters có thể chứa password, token hoặc thông tin riêng tư. Ghi correlation ID, operation ID, mã lỗi đã chuẩn hóa và tên dependency để hỗ trợ điều tra.

## 19. Những sai lầm thường gặp

- Gọi subscribe trong service interface rồi trả Mono khác cho framework.
- Gọi block hoặc join trong event-loop.
- Dùng map cho một hàm trả Mono khiến publisher bị lồng.
- Dùng Mono.empty để báo instance không tồn tại.
- Nuốt mọi exception bằng onErrorResume rồi trả response thành công.
- Dùng retry cho lệnh tạo resource không có idempotency.
- Cho rằng timeout nghĩa là backend chưa thực hiện tác dụng phụ.
- Giữ provisioning lâu dài trong subscription HTTP thay vì operation/worker bền vững.
- Chạy JPA/JDBC blocking trực tiếp trên event-loop.
- Tách các câu lệnh trong cùng transaction blocking sang nhiều scheduler.
- Dùng ThreadLocal để truyền context qua mọi scheduler.
- Giả định cancellation tự động rollback tác dụng phụ ở cloud provider.
- Viết test bằng subscribe thủ công mà không kiểm tra signal và completion.

## Kết luận

Mono là hợp đồng reactive cho một kết quả đơn lẻ trong các service interface của Spring Cloud Open Service Broker. Handler nên tạo một pipeline có thể compose, trả publisher cho framework và để application service điều phối validation, state transition, operation và adapter. map dành cho phép biến đổi đồng bộ; flatMap nối các bước bất đồng bộ; switchIfEmpty phân biệt dữ liệu thiếu; error operators ánh xạ lỗi có chủ đích. Không tự subscribe hoặc block trong handler, không chạy thư viện blocking trên event-loop và không coi cancellation/timeout là rollback. Với công việc dài, hãy lưu OSB operation bền vững rồi giao cho worker. Kết hợp StepVerifier, idempotency và observability giúp broker giữ đúng semantics của Mono ngay cả khi backend lỗi, request retry hoặc client ngắt kết nối.
