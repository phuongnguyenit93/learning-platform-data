# EventFlowRegistry và các giai đoạn initialization, completion, error

Spring Cloud Open Service Broker cho phép mở rộng quá trình xử lý request OSB bằng các event flow. Thay vì viết mọi thao tác phụ vào service xử lý provision, update, deprovision hoặc binding, ứng dụng có thể đăng ký các flow chạy trước khi xử lý, sau khi tạo response thành công hoặc khi có lỗi. Các điểm mở rộng này được quản lý bởi **EventFlowRegistry** và những registry chuyên biệt cho từng loại request.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, event flow hữu ích cho audit, metrics, kiểm tra điều kiện chung, ghi nhận kết quả và xử lý tác vụ phụ trợ. Ba giai đoạn **initialization**, **completion** và **error** có đầu vào cùng thời điểm chạy khác nhau. Hiểu đúng ranh giới đó giúp ứng dụng không nhầm hook của request HTTP với vòng đời thật của tác vụ bất đồng bộ, không lặp lại side effect và không vô tình che mất lỗi nghiệp vụ.

## 1. EventFlowRegistry là gì?

**EventFlowRegistry** là lớp cơ sở trừu tượng trong package:

~~~java
org.springframework.cloud.servicebroker.service.events
~~~

Nó quản lý các nhóm flow có kiểu cụ thể cho một loại request. Trong Javadoc, lớp có dạng generic:

~~~java
EventFlowRegistry<I, C, E, R, S>
~~~

Trong đó:

| Tham số | Ý nghĩa |
|---|---|
| I | Kiểu initialization flow |
| C | Kiểu completion flow |
| E | Kiểu error flow |
| R | Kiểu request mà flow nhận |
| S | Kiểu response tương ứng |

Registry cung cấp các phương thức đăng ký:

- `addInitializationFlow(...)`
- `addCompletionFlow(...)`
- `addErrorFlow(...)`

Và các phương thức lấy danh sách flow để framework thực thi theo request:

- `getInitializationFlows(request)`
- `getCompletionFlows(request, response)`
- `getErrorFlows(request, throwable)`

Các phương thức đăng ký trả về kiểu reactive `Mono<Void>`; các phương thức lấy flow được biểu diễn bằng `Flux<Void>` trong API của thư viện. Chi tiết chữ ký và generic type phụ thuộc phiên bản Spring Cloud Open Service Broker mà ứng dụng sử dụng.

**EventFlowRegistry là lớp cơ sở**, không phải một registry duy nhất để ứng dụng tự tạo cho tất cả thao tác. Framework cung cấp các lớp con có kiểu request/response cụ thể. Ứng dụng thường inject registry chuyên biệt tương ứng với thao tác cần mở rộng.

## 2. Những registry chuyên biệt

Các registry phổ biến được chia theo vòng đời service instance và service binding:

| Registry | Request được theo dõi | Mục đích |
|---|---|---|
| `CreateServiceInstanceEventFlowRegistry` | Tạo service instance | Hook quanh provision |
| `UpdateServiceInstanceEventFlowRegistry` | Cập nhật service instance | Hook quanh update |
| `DeleteServiceInstanceEventFlowRegistry` | Xóa service instance | Hook quanh deprovision |
| `AsyncOperationServiceInstanceEventFlowRegistry` | Lấy trạng thái last operation của instance | Hook quanh request polling |
| `CreateServiceInstanceBindingEventFlowRegistry` | Tạo binding | Hook quanh bind |
| `DeleteServiceInstanceBindingEventFlowRegistry` | Xóa binding | Hook quanh unbind |
| `AsyncOperationServiceInstanceBindingEventFlowRegistry` | Lấy trạng thái last operation của binding | Hook quanh polling binding operation |

Một số phiên bản còn cung cấp **EventFlowRegistries**, là đối tượng tập hợp các registry chuyên biệt và cung cấp accessor để lấy từng registry. Nó giúp cấu hình tập trung khi ứng dụng muốn quản lý nhiều nhóm flow.

Không phải broker nào cũng cần đăng ký cả bảy registry. Nếu broker không hỗ trợ binding hoặc không có thao tác bất đồng bộ, không cần tạo flow cho các giai đoạn đó. Hãy chọn registry theo các endpoint và capability mà broker thực sự triển khai.

## 3. Ba giai đoạn trong vòng đời request

Một request được framework chuyển qua các giai đoạn tổng quát:

~~~mermaid
flowchart TD
    A["Platform gửi request OSB"] --> B["Initialization flows"]
    B --> C["ServiceInstanceService / BindingService"]
    C --> D{"Xử lý thành công?"}
    D -->|Có| E["Completion flows"]
    E --> F["Trả response cho platform"]
    D -->|Không| G["Error flows"]
    G --> H["Chuyển lỗi sang exception handler"]
~~~

Ba giai đoạn có mục đích khác nhau:

- **Initialization:** chạy trước service method để thực hiện công việc chuẩn bị hoặc kiểm tra chung.
- **Completion:** chạy sau khi service method tạo được response thành công, nhận cả request và response.
- **Error:** chạy khi quá trình xử lý request phát sinh lỗi, nhận request và đối tượng `Throwable`.

Mỗi flow là một thành phần reactive riêng. Flow thường trả về `Mono<Void>`, vì nó thực hiện side effect hoặc kiểm tra mà không thay response nghiệp vụ. Response vẫn do implementation của `ServiceInstanceService` hoặc `ServiceInstanceBindingService` tạo ra.

Không coi ba giai đoạn là ba trạng thái của service instance. Chúng là các điểm hook trong pipeline xử lý request. Trạng thái `PROVISIONING`, `ACTIVE`, `DEPROVISIONING` hoặc `FAILED` vẫn phải được quản lý bởi domain service và state store của broker.

## 4. Initialization flow

Initialization flow chạy trước khi framework gọi service method chính của thao tác tương ứng. Interface có tên theo loại request, ví dụ:

- `CreateServiceInstanceInitializationFlow`
- `UpdateServiceInstanceInitializationFlow`
- `DeleteServiceInstanceInitializationFlow`
- `CreateServiceInstanceBindingInitializationFlow`
- `DeleteServiceInstanceBindingInitializationFlow`
- `AsyncOperationServiceInstanceInitializationFlow`

Phương thức xử lý thường có tên `initialize(...)`, nhận request tương ứng và trả `Mono<Void>`.

### Việc phù hợp với initialization

Initialization flow có thể đảm nhận:

- Ghi nhận request ID hoặc correlation ID vào audit context.
- Ghi metric request đến theo loại operation.
- Kiểm tra một điều kiện vận hành chung trước khi gọi service.
- Gắn trace/log context từ thông tin request đã được framework xác thực.
- Kiểm tra policy chung mà nhiều service method cùng sử dụng.
- Tạo dấu mốc bắt đầu xử lý để đối chiếu với completion/error.

Ví dụ, một broker muốn ghi nhận thời điểm platform yêu cầu provision để đo thời gian xử lý:

~~~java
@Bean
CreateServiceInstanceInitializationFlow provisionStartAudit(
        BrokerAuditService auditService) {

    return request -> auditService.recordStarted(
        "PROVISION",
        request.getServiceInstanceId()
    );
}
~~~

Đây là ví dụ minh họa. `BrokerAuditService` là service do ứng dụng xây dựng và trả về `Mono<Void>`.

### Initialization không thay thế domain validation

Initialization flow không nên trở thành nơi duy nhất kiểm tra parameters, quota hoặc ownership. Những điều kiện quyết định việc có được tạo tài nguyên hay không phải được kiểm tra trong domain service ngay trước thao tác có tác động.

Lý do là domain service có thể được gọi từ worker, tác vụ nội bộ hoặc luồng khác không đi qua endpoint OSB. Nếu chỉ đặt validation ở initialization flow, các đường gọi khác có thể bỏ qua kiểm tra.

Request model được truyền cho initialization flow là đầu vào để đọc. Nếu cần tạo một command đã chuẩn hóa hoặc thay đổi dữ liệu nghiệp vụ, hãy thực hiện trong application/domain service; không dùng event flow như một cơ chế sửa request ngầm.

## 5. Completion flow

Completion flow chạy sau khi service method xử lý thành công và tạo response. Interface nhận cả request lẫn response:

~~~java
Mono<Void> complete(Request request, Response response);
~~~

Các interface cụ thể có kiểu dữ liệu tương ứng, ví dụ:

- `CreateServiceInstanceCompletionFlow`
- `UpdateServiceInstanceCompletionFlow`
- `DeleteServiceInstanceCompletionFlow`
- `AsyncOperationServiceInstanceCompletionFlow`
- `CreateServiceInstanceBindingCompletionFlow`
- `DeleteServiceInstanceBindingCompletionFlow`

### Việc phù hợp với completion

Completion flow phù hợp với các công việc phụ trợ sau khi có kết quả xử lý:

- Ghi audit event thành công.
- Ghi metric theo response hoặc trạng thái operation.
- Phát notification cho hệ thống quan sát.
- Ghi nhận correlation ID và thời điểm kết thúc request.
- Cập nhật một chỉ số tổng hợp không quyết định tính đúng đắn của tài nguyên.
- Gửi thông tin đến hệ thống báo cáo hoặc analytics.

Ví dụ:

~~~java
@Bean
CreateServiceInstanceCompletionFlow provisionCompleted(
        BrokerAuditService auditService) {

    return (request, response) -> auditService.recordCompleted(
        "PROVISION",
        request.getServiceInstanceId()
    );
}
~~~

Ví dụ không cần đọc toàn bộ response để ghi audit. Khi cần dùng một field response cụ thể, hãy đối chiếu getter với phiên bản model đang dùng; điểm chính là completion flow có thể quan sát cả request và response đã được tạo.

### Completion không có nghĩa backend đã hoàn tất

Đây là điểm dễ nhầm khi broker hỗ trợ asynchronous operation.

Nếu `createServiceInstance()` trả response có `async=true`, completion flow của thao tác create chạy sau khi broker đã tạo response chấp nhận công việc bất đồng bộ. Nó **không** có nghĩa database hoặc cluster phía backend đã sẵn sàng.

Ví dụ:

1. Platform gửi PUT provision.
2. Broker lưu instance ở `PROVISIONING`, tạo operation và enqueue worker.
3. Service method trả response `async=true`.
4. Completion flow của request provision chạy sau khi response đó được tạo.
5. Worker tiếp tục gọi provider và có thể hoàn tất sau vài phút.

Sự kiện hoàn tất thật của worker cần được ghi nhận bởi worker/domain workflow, operation store hoặc event nội bộ của ứng dụng. Không dùng completion flow của HTTP request để thay thế callback hoàn thành backend.

Tương tự, completion flow của `getLastOperation()` chạy sau khi broker xử lý một request polling và tạo response trạng thái. Nó không phải callback thông báo operation nền vừa chuyển từ IN_PROGRESS sang SUCCEEDED.

## 6. Error flow

Error flow được gọi khi quá trình xử lý request phát sinh lỗi. Interface nhận request và lỗi:

~~~java
Mono<Void> error(Request request, Throwable error);
~~~

Các interface chuyên biệt gồm:

- `CreateServiceInstanceErrorFlow`
- `UpdateServiceInstanceErrorFlow`
- `DeleteServiceInstanceErrorFlow`
- `AsyncOperationServiceInstanceErrorFlow`
- `CreateServiceInstanceBindingErrorFlow`
- `DeleteServiceInstanceBindingErrorFlow`
- `AsyncOperationServiceInstanceBindingErrorFlow`

### Việc phù hợp với error flow

Error flow có thể:

- Ghi audit thất bại với operation và resource ID.
- Ghi metric lỗi theo loại request hoặc exception category.
- Gửi cảnh báo vận hành đã lọc thông tin nhạy cảm.
- Ghi trace ID để tìm log chi tiết.
- Ghi nhận bước chuẩn bị thất bại để hỗ trợ đối soát.
- Thực hiện cleanup phụ trợ an toàn khi cleanup đó độc lập và idempotent.

Ví dụ:

~~~java
@Bean
CreateServiceInstanceErrorFlow provisionFailed(
        BrokerAuditService auditService) {

    return (request, error) -> auditService.recordFailed(
        "PROVISION",
        request.getServiceInstanceId(),
        error.getClass().getSimpleName()
    ).onErrorResume(auditFailure -> {
        // Không để lỗi ghi audit che mất lỗi provision ban đầu.
        return Mono.empty();
    });
}
~~~

Ví dụ dùng tên exception thay cho log toàn bộ message để hạn chế rò rỉ thông tin provider hoặc dữ liệu nhạy cảm. Cách ghi log cụ thể cần tuân theo policy bảo mật của broker.

### Không biến lỗi thành thành công

Error flow là hook xử lý lỗi, không phải cơ chế tự động retry hoặc biến exception thành response thành công. Nếu flow chỉ ghi audit rồi hoàn tất, lỗi gốc của service method vẫn cần được framework xử lý theo exception mapping của OSB API.

Nếu error flow tự phát sinh lỗi và không xử lý, lỗi phụ có thể làm phức tạp kết quả xử lý hoặc che khuất nguyên nhân ban đầu. Hãy giữ error flow đơn giản, có fallback phù hợp và không để việc ghi log/notification làm thay đổi kết quả nghiệp vụ.

### Lỗi của worker nền là một phạm vi khác

Khi request đã trả `202 Accepted` và worker chạy độc lập, lỗi xảy ra vài phút sau đó không còn nằm trong pipeline HTTP ban đầu. Error flow gắn với request event registry không tự động bắt mọi exception của worker hoặc message consumer.

Worker phải tự ghi trạng thái operation, phân loại lỗi backend, áp dụng retry/compensation và cập nhật instance. Platform sẽ nhận kết quả qua endpoint last operation khi polling. Nếu cần hook cho worker, hãy dùng cơ chế event/job của ứng dụng hoặc message processing pipeline riêng.

## 7. Registry chuyên biệt cho service instance

Bốn nhóm registry thường dùng cho instance:

### Create service instance

`CreateServiceInstanceEventFlowRegistry` điều phối:

- `CreateServiceInstanceInitializationFlow`
- `CreateServiceInstanceCompletionFlow`
- `CreateServiceInstanceErrorFlow`

Các flow có thể ghi nhận request bắt đầu, audit response accepted/succeeded và ghi lỗi khi quá trình xử lý request create thất bại.

### Update service instance

`UpdateServiceInstanceEventFlowRegistry` dùng ba interface tương ứng:

- `UpdateServiceInstanceInitializationFlow`
- `UpdateServiceInstanceCompletionFlow`
- `UpdateServiceInstanceErrorFlow`

Update có thể thay đổi plan hoặc parameters. Flow có thể ghi nhận old/new plan ID và kết quả, nhưng kiểm tra tính hợp lệ của thay đổi và cập nhật resource vẫn thuộc domain service.

### Delete service instance

`DeleteServiceInstanceEventFlowRegistry` cung cấp các hook quanh deprovision:

- `DeleteServiceInstanceInitializationFlow`
- `DeleteServiceInstanceCompletionFlow`
- `DeleteServiceInstanceErrorFlow`

Initialization có thể ghi nhận yêu cầu thu hồi; completion ghi nhận response; error flow ghi nhận lỗi. Việc xóa backend resource, xác nhận đã xóa và giữ tombstone vẫn thuộc logic deprovision.

### Get last operation

`AsyncOperationServiceInstanceEventFlowRegistry` áp dụng cho request lấy trạng thái operation bất đồng bộ. Các interface:

- `AsyncOperationServiceInstanceInitializationFlow`
- `AsyncOperationServiceInstanceCompletionFlow`
- `AsyncOperationServiceInstanceErrorFlow`

Initialization có thể ghi metric polling; completion ghi nhận response state; error flow ghi nhận lỗi khi đọc trạng thái. Không gọi provider API dài hoặc thực hiện lại provision trong hook polling. Endpoint này nên trả trạng thái từ operation store một cách nhanh, nhất quán và có thể lặp lại.

## 8. Registry chuyên biệt cho service binding

Binding có vòng đời riêng với service instance nên có registry riêng.

### Create binding

`CreateServiceInstanceBindingEventFlowRegistry` dùng:

- `CreateServiceInstanceBindingInitializationFlow`
- `CreateServiceInstanceBindingCompletionFlow`
- `CreateServiceInstanceBindingErrorFlow`

Các hook có thể ghi nhận binding ID, instance ID và kết quả bind. Không ghi password, token hoặc toàn bộ credentials vào audit.

### Delete binding

`DeleteServiceInstanceBindingEventFlowRegistry` dùng:

- `DeleteServiceInstanceBindingInitializationFlow`
- `DeleteServiceInstanceBindingCompletionFlow`
- `DeleteServiceInstanceBindingErrorFlow`

Các hook ghi nhận yêu cầu unbind và kết quả thu hồi. Việc revoke user/token thực tế phải do binding service thực hiện; error flow không nên xóa record binding trong khi credential vẫn còn hiệu lực.

### Last binding operation

`AsyncOperationServiceInstanceBindingEventFlowRegistry` bao quanh request lấy trạng thái của thao tác bind/unbind bất đồng bộ. Nó có cùng ba giai đoạn, nhưng request/response type riêng của binding.

Các interface flow tương ứng là:

- `AsyncOperationServiceInstanceBindingInitializationFlow`
- `AsyncOperationServiceInstanceBindingCompletionFlow`
- `AsyncOperationServiceInstanceBindingErrorFlow`

Không dùng registry last operation của service instance cho service binding chỉ vì tên hai thao tác gần giống nhau. Inject đúng concrete registry để compiler giúp phát hiện sai loại request.

## 9. Đăng ký flow bằng Spring beans

Cách cấu hình đơn giản là khai báo bean có kiểu interface flow. Auto-configuration của Spring Cloud Open Service Broker nhận diện các bean flow và đưa chúng vào registry tương ứng.

Ví dụ:

~~~java
@Configuration
public class BrokerEventFlowsConfiguration {

    @Bean
    CreateServiceInstanceInitializationFlow createAuditStart(
            BrokerAuditService auditService) {
        return request -> auditService.recordStarted(
            "PROVISION",
            request.getServiceInstanceId()
        );
    }

    @Bean
    CreateServiceInstanceCompletionFlow createAuditSuccess(
            BrokerAuditService auditService) {
        return (request, response) -> auditService.recordCompleted(
            "PROVISION",
            request.getServiceInstanceId()
        );
    }

    @Bean
    CreateServiceInstanceErrorFlow createAuditFailure(
            BrokerAuditService auditService) {
        return (request, error) -> auditService.recordFailed(
            "PROVISION",
            request.getServiceInstanceId(),
            error.getClass().getSimpleName()
        );
    }
}
~~~

Các interface flow là functional interface trong những API tương ứng, nên có thể dùng lambda nếu chữ ký của dependency cho phép. Nếu method signature khác ở version đang dùng, triển khai anonymous class để thể hiện đúng method `initialize`, `complete` hoặc `error`.

Ưu điểm của cách dùng bean:

- Cấu hình flow tách khỏi service nghiệp vụ.
- Dependency được inject bằng constructor hoặc method parameter.
- Spring quản lý lifecycle và dependency.
- Auto-configuration tự ghép flow bean vào registry tương ứng.
- Dễ kiểm thử từng flow độc lập.

Tên bean nên mô tả rõ thao tác và giai đoạn. Tránh khai báo hai flow giống hệt nhau do import configuration trùng, vì cùng một audit có thể bị ghi hai lần.

## 10. Đăng ký flow trực tiếp qua EventFlowRegistry

Nếu cần đăng ký động hoặc muốn cấu hình tập trung theo registry, có thể inject registry chuyên biệt rồi gọi các phương thức add.

Ví dụ khái niệm:

~~~java
@Configuration
public class DirectRegistryConfiguration {

    public DirectRegistryConfiguration(
            CreateServiceInstanceEventFlowRegistry registry,
            BrokerAuditService auditService) {

        registry.addInitializationFlow(request ->
            auditService.recordStarted(
                "PROVISION",
                request.getServiceInstanceId()
            )
        ).subscribe();
    }
}
~~~

Trong API, `addInitializationFlow`, `addCompletionFlow` và `addErrorFlow` trả về `Mono<Void>`. Ví dụ trên minh họa việc đăng ký một lần khi ứng dụng khởi tạo; hãy theo đúng cách khởi tạo và quản lý subscription phù hợp với phiên bản thư viện.

Không gọi `add...Flow()` trong mỗi request handler. Registry thường là thành phần dùng chung trong application context; thêm flow mỗi lần request sẽ làm số hook tăng dần và một thao tác có thể bị thực thi lặp nhiều lần.

Nếu cần đăng ký nhiều flow, có thể kết hợp các publisher add bằng reactive composition và subscribe một lần ở bước cấu hình. Không dùng `block()` hoặc `subscribe()` bên trong chính flow để chờ tác vụ; flow phải trả publisher cho framework quản lý.

## 11. Không vô tình thay thế auto-configuration

Spring Cloud Open Service Broker cung cấp auto-configuration cho các registry. Reference documentation nêu rõ có thể:

1. Inject registry và thêm flow trực tiếp.
2. Khai báo bean cho từng flow để framework tự nhận diện.
3. Khai báo registry bean mới, nhưng thao tác này sẽ override registry auto-configured tương ứng.

Lựa chọn thứ ba cần thận trọng. Nếu khai báo một custom registry bean, ứng dụng phải tự cung cấp đầy đủ các flow list và cấu hình cần thiết. Một registry mới chỉ chứa một flow có thể làm mất các flow bean khác hoặc hành vi auto-configuration mà ứng dụng mong đợi.

Trong hầu hết trường hợp, hãy dùng typed flow beans hoặc inject registry mặc định. Chỉ thay registry khi có nhu cầu rõ ràng về cách tập hợp, lưu trữ hoặc phân phối flow và đã kiểm thử toàn bộ pipeline.

## 12. Reactive flow và cách xử lý lỗi

Các flow của framework dùng Project Reactor. Method trả `Mono<Void>` nên công việc chỉ được thực thi khi publisher được subscribe trong pipeline của framework hoặc được subscribe đúng cách ở bước đăng ký.

Ví dụ một flow gọi dịch vụ audit reactive:

~~~java
@Bean
DeleteServiceInstanceCompletionFlow deleteAudit(
        BrokerAuditService auditService) {

    return (request, response) ->
        auditService.recordCompleted(
            "DEPROVISION",
            request.getServiceInstanceId()
        );
}
~~~

Một số nguyên tắc:

- Trả publisher từ method, không gọi `block()` trong flow.
- Tránh tự gọi `subscribe()` trong `initialize`, `complete` hoặc `error`; điều đó tách tác vụ khỏi pipeline và làm framework không chờ kết quả.
- Không thực hiện I/O blocking trên event loop của WebFlux.
- Giới hạn thời gian cho hệ thống audit/notification bên ngoài.
- Dùng retry có giới hạn khi lỗi tạm thời và chỉ với side effect an toàn.
- Dùng idempotency key cho event phụ trợ có thể bị lặp.
- Nếu flow không thiết yếu và hệ thống phụ trợ gặp lỗi, quyết định rõ có cho phép request tiếp tục hay không.

Nếu một initialization flow là điều kiện bắt buộc, lỗi của nó có thể ngăn service method được gọi. Nếu audit chỉ mang tính best-effort, hãy xử lý lỗi audit theo policy thay vì để hệ thống audit ngừng hoạt động làm gián đoạn provision.

Completion flow cũng nằm trong pipeline xử lý response. Một lỗi từ notification hoặc analytics không nên làm mất kết quả provisioning đã hoàn tất. Với tác vụ không được phép làm request thất bại, ưu tiên ghi outbox trong transaction nghiệp vụ rồi xử lý notification ở worker riêng.

## 13. Phân chia trách nhiệm giữa flow và domain service

Không phải mọi logic đều nên đưa vào event flow.

| Công việc | Nơi phù hợp | Lý do |
|---|---|---|
| Kiểm tra parameters theo plan | Domain/application service | Là điều kiện nghiệp vụ của provision/update |
| Kiểm tra tenant ownership | Security/domain service | Phải áp dụng cho mọi đường gọi |
| Tạo resource backend | Provider adapter/domain workflow | Là thao tác cốt lõi của service |
| Lưu operation và state | State store/domain service | Cần transaction và tính bền vững |
| Ghi audit request đến | Initialization flow | Là hook chung trước xử lý |
| Ghi audit response | Completion flow | Có cả request và response |
| Ghi lỗi pipeline | Error flow | Nhận request và Throwable |
| Retry job nền | Worker/job processor | Nằm ngoài vòng đời HTTP ban đầu |
| Reconcile backend sau timeout | Domain workflow/worker | Cần state và idempotency |
| Notification không quan trọng | Completion flow hoặc outbox worker | Chọn theo yêu cầu độ tin cậy |

Một nguyên tắc hữu ích: nếu broker cần bảo đảm một hành động để tài nguyên và state store nhất quán, hành động đó phải nằm trong domain workflow có transaction/idempotency/reconciliation. Event flow thích hợp cho cross-cutting concern và side effect phụ trợ.

## 14. Ví dụ pipeline provision có cả ba giai đoạn

Giả sử platform gửi yêu cầu provision PostgreSQL:

1. Controller nhận request OSB và framework tạo request model.
2. Initialization flow ghi nhận request bắt đầu và trace ID.
3. `ServiceInstanceService.createServiceInstance()` xác thực parameters, lưu instance/operation và bắt đầu công việc provision.
4. Service method trả response đồng bộ hoặc `async=true`.
5. Completion flow ghi nhận response được tạo.
6. Controller trả response cho platform.
7. Nếu bước xử lý request phát sinh lỗi, error flow ghi nhận lỗi và framework ánh xạ exception sang response OSB.
8. Nếu provision bất đồng bộ, worker tiếp tục độc lập; worker tự cập nhật operation khi backend thành công hoặc thất bại.
9. Platform gọi last operation; initialization/completion/error flow của `AsyncOperationServiceInstanceEventFlowRegistry` bao quanh request polling.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant C as OSB Controller
    participant R as EventFlowRegistry
    participant S as ServiceInstanceService
    participant DB as State Store
    participant W as Worker

    P->>C: PUT service_instances/{id}
    C->>R: Initialization flows
    R-->>C: Mono<Void> completed
    C->>S: createServiceInstance(request)
    S->>DB: Save instance + operation
    S-->>C: Response async=true
    C->>R: Completion flows(request, response)
    R-->>C: Mono<Void> completed
    C-->>P: 202 Accepted
    W->>DB: Load pending operation
    W->>W: Provision backend
    W->>DB: Persist success/failure
    P->>C: GET last_operation
    C->>R: Async initialization flows
    C->>S: getLastOperation(request)
    S->>DB: Read operation state
    S-->>C: Operation response
    C->>R: Async completion flows
    C-->>P: Operation state
~~~

Nếu lỗi xảy ra trong service method, pipeline đi qua error flow tương ứng. Nếu worker lỗi sau khi response 202 đã được trả, worker cập nhật operation và platform nhận trạng thái đó khi polling; error flow của request PUT ban đầu không tự chạy lại.

## 15. Quản lý side effect và tính idempotent

Event flow có thể được gọi trong những request mà platform retry sau timeout hoặc do người dùng thực hiện lại thao tác. Vì vậy, không giả định mỗi flow chỉ chạy một lần trong toàn bộ vòng đời nghiệp vụ.

Ví dụ, nếu completion flow gửi email mỗi lần create request trả response, retry cùng instance có thể gửi email trùng. Nếu error flow tạo ticket mỗi lần lỗi được quan sát, cùng một request có thể tạo nhiều ticket.

Nên thiết kế side effect với:

- Correlation ID hoặc request identity.
- Operation ID và resource ID.
- Idempotency key cho notification hoặc audit event.
- Unique constraint cho event đã ghi.
- Outbox khi event phải được phát bền vững.
- Retry policy rõ ràng và có giới hạn.
- Log đủ để đối soát mà không chứa secret.

Với audit quan trọng, nên ghi audit event trong transaction hoặc outbox cùng state transition. Completion flow có thể ghi metric hoặc notification bổ sung, nhưng không nên là nơi duy nhất lưu bằng chứng của một thay đổi tài nguyên quan trọng.

## 16. Bảo mật khi triển khai event flow

Flow nhận request model và đôi khi cả response hoặc exception. Các đối tượng này có thể chứa parameters, context, credentials hoặc thông tin backend nhạy cảm.

Hãy áp dụng các quy tắc:

- Không serialize toàn bộ request/response vào log.
- Không ghi password, token, private key, connection URI có credential hoặc secret reference nhạy cảm.
- Chỉ log field cần cho correlation: operation type, platform scope đã xác minh, instance/binding ID và trace ID.
- Redact exception message đến từ provider nếu có thể chứa endpoint, account hoặc request payload.
- Không để event flow bỏ qua xác thực/authorization của service method.
- Giới hạn quyền của audit/notification client.
- Không gửi raw parameters đến hệ thống analytics nếu chưa lọc dữ liệu.
- Kiểm soát retention và quyền đọc audit record.

Error flow cần đặc biệt cẩn trọng: `Throwable` có thể chứa cause chain, request URL, provider response body hoặc token. Log tên loại lỗi và correlation ID thường an toàn hơn ghi toàn bộ stack trace vào hệ thống ngoài.

## 17. Kiểm thử từng giai đoạn

Nên kiểm thử flow độc lập và kiểm thử integration qua endpoint OSB.

| Trường hợp | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Initialization thành công | Gửi request hợp lệ | Hook chạy trước service method |
| Initialization thất bại | Cho hook trả lỗi | Service method không được coi là đã xử lý thành công |
| Completion thành công | Service method trả response | Hook nhận đúng request và response |
| Error trong service method | Mock service ném exception | Error flow nhận đúng request và lỗi |
| Completion lỗi | Audit/notification client lỗi | Hành vi theo policy; không làm mất kết quả nghiệp vụ nếu hook best-effort |
| Error flow lỗi | Audit backend không hoạt động | Lỗi phụ không che nguyên nhân gốc theo thiết kế |
| Nhiều flow | Đăng ký nhiều hook cùng loại | Tất cả hook dự kiến được thực thi |
| Bean được phát hiện | Khai báo typed flow bean | Auto-configuration thêm vào registry tương ứng |
| Registry custom | Khai báo registry bean riêng | Xác minh không làm mất các flow cần thiết |
| Request retry | Gửi lại cùng OSB request | Audit/notification không nhân đôi ngoài policy |
| Async create | Response accepted, worker chạy sau | Completion flow chạy sau response accepted; worker quản lý kết quả riêng |
| Worker thất bại sau 202 | Làm provider lỗi sau khi trả accepted | Operation store chuyển failed; không kỳ vọng error flow HTTP ban đầu chạy |
| Last operation polling | Gửi GET polling | Async registry chạy quanh request đọc trạng thái |
| Binding create/delete | Gửi bind và unbind | Đúng registry binding được sử dụng |
| Secret redaction | Dùng request có secret | Không có secret trong log/audit |
| Reactive execution | Dùng StepVerifier hoặc WebTestClient | Publisher hoàn tất đúng, không có tác vụ bị bỏ quên |

Trong unit test, có thể dùng mock audit service để xác minh thứ tự gọi và tham số. Với integration test, kiểm tra response OSB, invocation count của từng flow và exception mapping. Đừng chỉ test rằng Spring context khởi động; cần xác minh flow thực sự được registry nhận và được gọi.

## 18. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nhầm EventFlowRegistry là event bus tổng quát | Đăng ký sai abstraction và khó hiểu vòng đời | Dùng registry chuyên biệt theo request type |
| Dùng nhầm registry instance và binding | Flow không được gọi hoặc nhận sai kiểu | Inject đúng concrete registry |
| Đưa toàn bộ nghiệp vụ provision vào initialization | Đường gọi khác có thể bỏ qua logic | Giữ nghiệp vụ trong domain service |
| Nghĩ completion nghĩa là backend đã sẵn sàng | Đánh dấu sai trạng thái async | Phân biệt response accepted với worker completion |
| Nghĩ error flow bắt lỗi worker nền | Operation có thể không được cập nhật | Worker tự quản lý lỗi và operation state |
| Gọi subscribe trong mỗi flow | Tác vụ tách khỏi pipeline, lỗi khó theo dõi | Trả Mono cho framework |
| Gọi block trên WebFlux event loop | Chặn request và giảm throughput | Dùng reactive client hoặc scheduler phù hợp |
| Đăng ký flow mỗi request | Một hook bị thêm nhiều lần | Đăng ký một lần khi khởi tạo application |
| Khai báo registry bean mới vô tình | Override auto-configuration và mất flow khác | Dùng typed flow beans hoặc registry mặc định |
| Error flow ghi log raw Throwable | Lộ secret hoặc dữ liệu provider | Redaction và log theo correlation |
| Completion flow thực hiện transaction nghiệp vụ chính | Khó bảo đảm tính nhất quán | Đưa thay đổi state vào domain transaction/outbox |
| Flow phụ trợ lỗi làm request thất bại | Audit/analytics outage ảnh hưởng provision | Chọn rõ critical hay best-effort và xử lý lỗi |

## 19. Nguyên tắc cần ghi nhớ

**EventFlowRegistry** là extension point của Spring Cloud Open Service Broker để gắn các reactive flow vào pipeline xử lý request OSB. Lớp cơ sở quản lý ba nhóm flow có kiểu: initialization, completion và error. Các registry con xác định request/response cụ thể cho provision, update, deprovision, bind, unbind và last operation.

Khi triển khai trong **SPRING_CLOUD_SERVICE_BROKER**, hãy nhớ:

- Initialization chạy trước service method và nhận request.
- Completion chạy sau khi service method tạo response và nhận cả request lẫn response.
- Error chạy khi pipeline request phát sinh lỗi và nhận request cùng Throwable.
- Completion của response async chỉ có nghĩa broker đã tạo response accepted; nó không xác nhận backend job đã hoàn tất.
- Lỗi của worker sau HTTP 202 phải được worker ghi vào operation store; error flow HTTP không tự theo dõi worker.
- Dùng registry chuyên biệt đúng với loại request.
- Có thể đăng ký flow bằng typed Spring bean hoặc gọi add flow trên registry.
- Không tạo registry bean mới nếu không chủ động thay thế auto-configuration.
- Giữ flow reactive, tránh block và side effect trùng lặp.
- Để domain service quản lý validation, tài nguyên, transaction và lifecycle state.
- Bảo vệ request, response và Throwable khỏi việc lộ secret trong log/audit.

Khi phân chia đúng trách nhiệm, event flow giúp thêm audit, metrics và các xử lý chung mà không làm rối service method. Broker vẫn giữ được quy trình provision, update, deprovision và binding rõ ràng, có thể kiểm thử, phục hồi và vận hành nhất quán.

## Tài liệu tham khảo

- [Spring Cloud Open Service Broker Reference — Event Registry](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/reference/)
- [EventFlowRegistry Javadoc](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/service/events/EventFlowRegistry.html)
- [CreateServiceInstanceEventFlowRegistry Javadoc](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/service/events/CreateServiceInstanceEventFlowRegistry.html)

