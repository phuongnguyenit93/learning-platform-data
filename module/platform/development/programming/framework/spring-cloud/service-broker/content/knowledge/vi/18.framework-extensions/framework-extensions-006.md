# Đăng ký luồng bằng registry hoặc các bean event flow

Spring Cloud Open Service Broker cho phép mở rộng quy trình xử lý service instance và service binding bằng các event flow. Thay vì đặt mọi logic phụ trợ vào ServiceInstanceService hoặc ServiceInstanceBindingService, ứng dụng có thể đăng ký các luồng chạy ở những giai đoạn xác định: trước khi xử lý request, sau khi xử lý thành công hoặc khi xảy ra lỗi.

Có hai cách đăng ký chính: lấy registry do framework cấu hình sẵn rồi thêm flow trực tiếp, hoặc khai báo từng flow thành Spring bean. Framework tự nhận diện các bean này và đưa chúng vào registry tương ứng. Cách thứ hai thường dễ đọc, dễ kiểm thử và phù hợp với Spring Boot configuration; cách thứ nhất hữu ích khi cần đăng ký có điều kiện hoặc điều chỉnh registry bằng code.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, event flow có thể dùng để kiểm tra policy, ghi audit, gắn correlation metadata, phát metric, đồng bộ trạng thái phụ hoặc thực hiện tác vụ hậu xử lý. Bài học này giải thích cấu trúc registry, các loại flow, cách cấu hình bằng hai phương thức, cách mở rộng service instance và binding, cùng các lưu ý về reactive execution, lỗi, thứ tự chạy và kiểm thử.

## 1. Event flow là điểm mở rộng của framework

Một service broker nhận request OSB API rồi chuyển đến service implementation. Ví dụ, request provision đi vào createServiceInstance(), còn request bind đi vào createServiceInstanceBinding(). Các method này vẫn là nơi triển khai nghiệp vụ chính: kiểm tra request, gọi provider, lưu trạng thái và tạo response.

Event flow bổ sung các bước phụ quanh quá trình đó. Framework cung cấp registry và wrapper để chạy các flow đã đăng ký ở từng giai đoạn của request.

Một event flow không thay thế ServiceInstanceService hoặc ServiceInstanceBindingService. Nếu broker cần tạo database, cấp user hoặc thu hồi tài nguyên, nghiệp vụ đó vẫn phải được thực hiện trong service implementation hoặc một coordinator mà service gọi đến. Event flow phù hợp với logic mở rộng có ranh giới rõ, chẳng hạn:

- Kiểm tra chính sách trước khi bắt đầu một thao tác.
- Ghi nhận audit event khi thao tác thành công hoặc thất bại.
- Gửi metric hoặc trace annotation.
- Ghi nhận correlation ID và metadata vận hành.
- Cập nhật hệ thống theo dõi hoặc notification.
- Thực hiện kiểm tra bổ sung có thể ghép vào reactive pipeline.

Không nên biến các flow thành nơi chứa toàn bộ provisioning workflow. Khi logic phụ thuộc nhiều bước, có transaction riêng hoặc cần phục hồi sau restart, hãy đặt nó trong service/coordinator chuyên trách rồi để flow gọi một API rõ ràng.

## 2. Ba giai đoạn của một event flow

Mỗi loại operation có thể có ba nhóm flow:

| Nhóm flow | Thời điểm | Tham số chính | Mục đích thường gặp |
|---|---|---|---|
| Initialization flow | Trước khi service xử lý request | Request | Kiểm tra policy, chuẩn bị context, ghi nhận bắt đầu |
| Completion flow | Sau khi service xử lý thành công | Request và response | Audit thành công, metric, đồng bộ metadata |
| Error flow | Khi xử lý gặp lỗi | Request và Throwable | Ghi lỗi, phát cảnh báo, lưu thông tin phục hồi |

Các interface flow trả về Reactor Mono<Void>. Điều đó cho phép framework ghép chúng vào reactive pipeline và chờ tác vụ của flow hoàn tất theo cơ chế xử lý của framework.

Luồng khái quát:

~~~mermaid
flowchart TD
    Request["OSB API request"] --> Init["Initialization flows"]
    Init --> Service["Service implementation"]
    Service -->|Success| Completion["Completion flows"]
    Service -->|Error| Error["Error flows"]
    Completion --> Response["Return response"]
    Error --> Failure["Propagate operation failure"]
~~~

Initialization flow phù hợp với các kiểm tra trước nghiệp vụ. Completion flow nhận cả request và response để có thể ghi nhận kết quả. Error flow nhận Throwable để phân loại lỗi và lưu thông tin cần thiết.

Flow không nên tự tạo response OSB thay cho service implementation. Completion flow chủ yếu xử lý hậu kỳ; nếu cần thay đổi nghiệp vụ hoặc response, hãy thực hiện trong service implementation theo API mà framework hỗ trợ.

## 3. Các registry có sẵn

Framework cung cấp registry riêng theo loại operation. Mỗi registry quản lý các flow initialization, completion và error tương ứng.

| Operation | Registry |
|---|---|
| Tạo service instance | CreateServiceInstanceEventFlowRegistry |
| Cập nhật service instance | UpdateServiceInstanceEventFlowRegistry |
| Xóa service instance | DeleteServiceInstanceEventFlowRegistry |
| Truy vấn last operation của instance | AsyncOperationServiceInstanceEventFlowRegistry |
| Tạo service binding | CreateServiceInstanceBindingEventFlowRegistry |
| Xóa service binding | DeleteServiceInstanceBindingEventFlowRegistry |
| Truy vấn last operation của binding | AsyncOperationServiceInstanceBindingEventFlowRegistry |

Ví dụ, CreateServiceInstanceEventFlowRegistry chỉ nhận các flow dành cho create instance. Không đăng ký CreateServiceInstanceBindingInitializationFlow vào registry tạo instance; hai nhóm interface có request type và lifecycle khác nhau.

Một registry cung cấp các phương thức:

- addInitializationFlow(...)
- addCompletionFlow(...)
- addErrorFlow(...)

Các phương thức thêm flow trả về Mono<Void>. Registry cũng cung cấp các phương thức lấy các flow phù hợp với request và response dưới dạng Flux<Void> để framework thực thi.

Framework tự cấu hình các registry mặc định khi ứng dụng sử dụng Spring Cloud Open Service Broker starter và cấu hình Spring Boot phù hợp. Vì vậy, thông thường chỉ cần inject registry hoặc khai báo flow bean; không cần tự tạo registry mới.

## 4. Cách 1: Inject registry và đăng ký flow trực tiếp

Cách này phù hợp khi muốn đăng ký flow bằng code, ví dụ khi lựa chọn flow dựa trên cấu hình hoặc khi cần tập trung việc đăng ký trong một lớp cấu hình.

Ví dụ đăng ký ba flow cho thao tác tạo service instance:

~~~java
@Configuration
public class InstanceFlowRegistryConfiguration {

    @Bean
    ApplicationRunner registerCreateInstanceFlows(
            CreateServiceInstanceEventFlowRegistry registry,
            ProvisionPolicy provisionPolicy,
            BrokerAuditService auditService) {

        return args -> registry
            .addInitializationFlow(
                new CreateServiceInstanceInitializationFlow() {
                    @Override
                    public Mono<Void> initialize(
                            CreateServiceInstanceRequest request) {
                        return provisionPolicy.validate(request);
                    }
                })
            .then(registry.addCompletionFlow(
                new CreateServiceInstanceCompletionFlow() {
                    @Override
                    public Mono<Void> complete(
                            CreateServiceInstanceRequest request,
                            CreateServiceInstanceResponse response) {
                        return auditService.recordProvisionAccepted(
                            request, response);
                    }
                }))
            .then(registry.addErrorFlow(
                new CreateServiceInstanceErrorFlow() {
                    @Override
                    public Mono<Void> error(
                            CreateServiceInstanceRequest request,
                            Throwable error) {
                        return auditService.recordProvisionFailure(
                            request, error);
                    }
                }))
            .subscribe();
    }
}
~~~

Các class ProvisionPolicy và BrokerAuditService là thành phần do ứng dụng định nghĩa. Ví dụ sử dụng ApplicationRunner để thực hiện đăng ký một lần khi ứng dụng khởi động. Chuỗi Mono được subscribe để các thao tác add flow thực sự được thực hiện; không gọi đăng ký lặp lại trong mỗi request.

Có thể đăng ký riêng từng nhóm flow nếu chỉ cần một hoặc hai giai đoạn. Không bắt buộc phải khai báo đủ initialization, completion và error.

### Lưu ý về thời điểm đăng ký

Đăng ký flow là cấu hình lúc khởi động ứng dụng, không phải side effect của mỗi request. Không thêm flow vào registry mỗi lần createServiceInstance() chạy, vì registry có thể tích lũy nhiều bản đăng ký giống nhau và một request sẽ kích hoạt flow nhiều lần.

Không nên tạo registry bằng new trong service hoặc controller. Hãy inject registry được Spring quản lý để flow được gắn vào đúng pipeline của framework.

## 5. Cách 2: Khai báo event flow thành Spring bean

Cách thứ hai là tạo bean có kiểu interface flow cụ thể. Spring Cloud Open Service Broker tự nhận diện các bean này và thêm chúng vào registry tương ứng.

Đây thường là cách cấu hình đơn giản nhất vì:

- Mỗi flow có thể được đặt trong một bean riêng.
- Dependency được inject trực tiếp qua constructor hoặc method parameter.
- Có thể dùng profile hoặc conditional configuration.
- Dễ viết unit test cho từng flow.
- Không cần tự gọi add...Flow().

Ví dụ:

~~~java
@Configuration
public class ProvisionEventFlowBeans {

    @Bean
    CreateServiceInstanceInitializationFlow validateProvisionPolicy(
            ProvisionPolicy policy) {

        return new CreateServiceInstanceInitializationFlow() {
            @Override
            public Mono<Void> initialize(
                    CreateServiceInstanceRequest request) {
                return policy.validate(request);
            }
        };
    }

    @Bean
    CreateServiceInstanceCompletionFlow auditProvisionSuccess(
            BrokerAuditService auditService) {

        return new CreateServiceInstanceCompletionFlow() {
            @Override
            public Mono<Void> complete(
                    CreateServiceInstanceRequest request,
                    CreateServiceInstanceResponse response) {
                return auditService.recordProvisionAccepted(
                    request, response);
            }
        };
    }

    @Bean
    CreateServiceInstanceErrorFlow auditProvisionFailure(
            BrokerAuditService auditService) {

        return new CreateServiceInstanceErrorFlow() {
            @Override
            public Mono<Void> error(
                    CreateServiceInstanceRequest request,
                    Throwable error) {
                return auditService.recordProvisionFailure(
                    request, error);
            }
        };
    }
}
~~~

Điểm quan trọng là kiểu trả về của từng method @Bean. Framework dựa trên interface để nhận diện flow và đưa nó vào registry thích hợp. Tên bean chỉ giúp người đọc hiểu mục đích; tên method không thay thế kiểu interface.

Nếu có nhiều bean cùng triển khai một loại flow, chúng có thể cùng được đưa vào registry đó. Với các flow có quan hệ phụ thuộc thứ tự, không nên giả định thứ tự chỉ dựa trên thứ tự khai báo method trong file. Hãy gom các bước cần chạy tuần tự vào một flow/coordinator duy nhất hoặc sử dụng cơ chế ordering được phiên bản Spring hỗ trợ và kiểm thử rõ ràng.

## 6. So sánh hai cách đăng ký

| Tiêu chí | Đăng ký trực tiếp qua registry | Khai báo event flow bean |
|---|---|---|
| Cách cấu hình | Inject registry và gọi add...Flow() | Khai báo bean có interface flow |
| Tự động nhận diện | Không; ứng dụng chủ động đăng ký | Có; framework nhận diện bean theo kiểu |
| Điều kiện runtime | Linh hoạt khi cần lựa chọn flow bằng code | Có thể dùng profile/conditional bean |
| Dependency injection | Có thể truyền dependency khi tạo flow | Spring inject dependency tự nhiên |
| Độ rõ ràng | Registry và đăng ký tập trung trong một lớp | Mỗi flow thể hiện thành một bean |
| Rủi ro phổ biến | Quên subscribe Mono đăng ký hoặc đăng ký nhiều lần | Nhiều flow cùng loại nhưng không kiểm soát phụ thuộc |

Nên ưu tiên event flow bean cho cấu hình tĩnh của ứng dụng Spring Boot. Dùng registry trực tiếp khi thật sự cần đăng ký động hoặc muốn điều phối đăng ký bằng code. Không cần sử dụng cả hai cách cho cùng một flow nếu điều đó khiến một tác vụ bị thực thi hai lần.

## 7. Ví dụ flow cho update và delete instance

Registry của update và delete sử dụng interface riêng. Ví dụ flow kiểm tra trước khi cập nhật plan:

~~~java
@Bean
UpdateServiceInstanceInitializationFlow validatePlanChange(
        PlanChangePolicy policy) {

    return new UpdateServiceInstanceInitializationFlow() {
        @Override
        public Mono<Void> initialize(
                UpdateServiceInstanceRequest request) {
            return policy.validate(
                request.getServiceInstanceId(),
                request.getPlanId(),
                request.getPreviousValues());
        }
    };
}
~~~

Flow hoàn tất có thể ghi audit:

~~~java
@Bean
UpdateServiceInstanceCompletionFlow recordPlanChange(
        BrokerAuditService auditService) {

    return new UpdateServiceInstanceCompletionFlow() {
        @Override
        public Mono<Void> complete(
                UpdateServiceInstanceRequest request,
                UpdateServiceInstanceResponse response) {
            return auditService.recordPlanChange(
                request, response);
        }
    };
}
~~~

Với delete instance, initialization flow có thể kiểm tra legal hold hoặc trạng thái binding; completion flow ghi nhận việc thu hồi; error flow tạo thông tin phục hồi nếu provider từ chối xóa.

~~~java
@Bean
DeleteServiceInstanceErrorFlow recordDeleteFailure(
        BrokerAuditService auditService) {

    return new DeleteServiceInstanceErrorFlow() {
        @Override
        public Mono<Void> error(
                DeleteServiceInstanceRequest request,
                Throwable error) {
            return auditService.recordDeprovisionFailure(
                request.getServiceInstanceId(), error);
        }
    };
}
~~~

Các flow này không thay thế logic update hoặc deprovision. Service implementation vẫn chịu trách nhiệm thay đổi tài nguyên provider và cập nhật trạng thái nghiệp vụ.

## 8. Đăng ký flow cho service binding

Service binding có các registry riêng vì request và response chứa dữ liệu consumer, binding ID và credentials.

Ví dụ completion flow sau khi tạo binding:

~~~java
@Bean
CreateServiceInstanceBindingCompletionFlow auditBindingCreated(
        BindingAuditService auditService) {

    return new CreateServiceInstanceBindingCompletionFlow() {
        @Override
        public Mono<Void> complete(
                CreateServiceInstanceBindingRequest request,
                CreateServiceInstanceBindingResponse response) {
            return auditService.recordBindingCreated(
                request.getServiceInstanceId(),
                request.getBindingId());
        }
    };
}
~~~

Initialization flow có thể xác minh policy của tenant trước khi tạo binding. Error flow có thể ghi mã lỗi và binding ID để hỗ trợ đối soát.

Đối với delete binding, flow có thể ghi nhận yêu cầu revoke và kết quả thu hồi. Tuy nhiên, việc xóa credential hoặc thu hồi user ở provider vẫn phải được thực hiện trong deleteServiceInstanceBinding() hoặc coordinator mà service gọi đến.

Không ghi credentials, password, token hoặc private key vào audit event. Event flow chỉ nên ghi định danh và kết quả cần thiết; secret được quản lý qua secret manager với quyền truy cập riêng.

## 9. Event flow cho truy vấn last operation

Khi provision, update hoặc deprovision chạy bất đồng bộ, nền tảng có thể gọi getLastOperation() nhiều lần để truy vấn trạng thái. Framework cung cấp AsyncOperationServiceInstanceEventFlowRegistry cho các event flow của thao tác truy vấn này.

Ví dụ initialization flow:

~~~java
@Bean
AsyncOperationServiceInstanceInitializationFlow auditLastOperationPoll(
        OperationAuditService auditService) {

    return new AsyncOperationServiceInstanceInitializationFlow() {
        @Override
        public Mono<Void> initialize(
                GetLastServiceOperationRequest request) {
            return auditService.recordPoll(
                request.getServiceInstanceId());
        }
    };
}
~~~

Completion flow có thể ghi nhận trạng thái operation đã trả về; error flow có thể ghi lại lỗi khi truy vấn trạng thái.

Không dùng last-operation flow để thực hiện lại provision hoặc xóa tài nguyên. Nền tảng có thể poll nhiều lần, nên các flow ở đây cần nhẹ, idempotent và không tạo side effect lặp. Trạng thái operation phải được đọc từ kho dữ liệu bền vững hoặc nguồn có thẩm quyền.

Với thao tác binding bất đồng bộ, framework có registry riêng là AsyncOperationServiceInstanceBindingEventFlowRegistry và các interface AsyncOperationServiceInstanceBindingInitializationFlow, AsyncOperationServiceInstanceBindingCompletionFlow, AsyncOperationServiceInstanceBindingErrorFlow.

## 10. Phân biệt registry mặc định và custom registry bean

Spring Cloud Open Service Broker tự cấu hình registry và các thành phần event service cần thiết. Khi ứng dụng khai báo một bean registry cùng loại, cấu hình tùy chỉnh đó có thể thay thế registry auto-configured.

Điều này quan trọng vì registry không chỉ là một object rỗng. Constructor của registry nhận các danh sách initialization, completion và error flow. Nếu tự khai báo registry mà không đưa các flow bean hiện có vào các danh sách tương ứng, những flow đó có thể không còn được đăng ký.

Chỉ tạo custom registry bean khi cần thay đổi cách xây dựng registry hoặc kiểm soát tập flow ở mức thấp. Nếu mục tiêu chỉ là thêm một hook, hãy inject registry mặc định và gọi add...Flow(), hoặc khai báo flow bean.

Trước khi override registry, cần kiểm tra:

- Registry nào đang được auto-configure.
- Danh sách flow nào phải được giữ lại.
- Các flow bean hiện tại có được đưa vào registry mới không.
- Các service event wrapper đang sử dụng registry nào.
- Integration test có xác nhận tất cả flow cần thiết được gọi không.

Không khai báo bean registry chỉ để tiện inject một object. Điều đó có thể vô tình thay đổi cấu hình mặc định của framework.

## 11. Reactive execution và cách xử lý lỗi

Các event flow trả Mono<Void>, do đó logic bên trong cần tạo và trả về publisher thay vì tự chạy công việc ngoài pipeline.

Đúng:

~~~java
@Override
public Mono<Void> initialize(CreateServiceInstanceRequest request) {
    return policyService.validate(request)
        .then(auditService.recordStart(request));
}
~~~

Không nên gọi subscribe() bên trong flow:

~~~java
@Override
public Mono<Void> initialize(CreateServiceInstanceRequest request) {
    auditService.recordStart(request).subscribe();
    return Mono.empty();
}
~~~

Cách thứ hai khiến framework không chờ audit hoàn tất và không quan sát được lỗi của tác vụ đó. Hãy trả Mono để framework quản lý quá trình thực thi và lỗi.

Nếu dependency dùng API blocking, hãy cô lập blocking I/O trên scheduler phù hợp thay vì chặn event-loop thread. Không gọi block() trong reactive request path.

### Lỗi trong từng loại flow

- Initialization flow thất bại có thể ngăn service operation tiếp tục; dùng nó cho validation hoặc điều kiện thật sự phải đạt.
- Completion flow thất bại có thể khiến pipeline báo lỗi dù nghiệp vụ chính đã thành công. Hãy quyết định rõ tác vụ hậu kỳ nào là bắt buộc.
- Error flow cần tránh che mất nguyên nhân ban đầu. Với telemetry không bắt buộc, có thể ghi nhận lỗi phụ và hoàn tất flow an toàn. Với cleanup hoặc audit bắt buộc, hãy lưu công việc bền vững và có cơ chế retry.

Ví dụ, nếu gửi metric thất bại, broker thường không nên biến một lần provision thành lỗi chỉ vì hệ thống metrics tạm thời không khả dụng. Ngược lại, nếu initialization flow kiểm tra tenant bị khóa và trả lỗi, broker phải dừng request trước khi tạo tài nguyên.

Không dùng error flow làm nơi duy nhất để bù trừ side effect quan trọng. Nếu cleanup có thể kéo dài hoặc cần phục hồi sau restart, hãy tạo operation hoặc task bền vững trong coordinator.

## 12. Thiết kế flow idempotent và không tạo side effect lặp

Một số event có thể được gọi trong các request retry. Last-operation event đặc biệt có thể chạy nhiều lần vì platform polling.

Vì vậy:

- Ghi audit có khóa deduplication hoặc event ID ổn định khi cần.
- Không tạo tài nguyên provider trong completion flow nếu service đã làm việc đó.
- Không gửi notification lặp mà không có idempotency key.
- Không dùng initialization flow để thay đổi state không thể đảo ngược nếu request có thể bị retry.
- Không giả định completion flow chỉ chạy đúng một lần trên toàn hệ thống.
- Không dựa vào biến static hoặc bộ nhớ cục bộ để chống trùng giữa nhiều replica.

Nếu một flow cần tạo side effect, lưu operation/reference bền vững và dùng idempotency key. Event flow là điểm nối vào pipeline, không tự cung cấp bảo đảm exactly-once cho hệ thống bên ngoài.

## 13. Quản lý thứ tự khi có nhiều flow

Một registry có thể chứa nhiều initialization, completion hoặc error flow. Tuy nhiên, không nên dựa vào thứ tự khai báo bean trong file cấu hình để biểu diễn dependency nghiệp vụ.

Ví dụ, nếu flow B cần dữ liệu do flow A tạo, có hai hướng:

1. Gom A và B thành một flow điều phối, trả về một reactive chain tuần tự.
2. Dùng cơ chế ordering được phiên bản framework/Spring hỗ trợ và kiểm thử thứ tự thực tế trong ứng dụng.

Không dùng nhiều flow độc lập như một workflow engine nếu chúng phụ thuộc chặt chẽ vào nhau. Khi có nhiều bước cần retry, checkpoint, transaction hoặc compensation, hãy dùng service coordinator/Saga và để event flow gọi coordinator ở đúng lifecycle stage.

## 14. Bật flow theo profile hoặc điều kiện cấu hình

Spring bean cho phép đăng ký flow theo môi trường. Ví dụ chỉ bật flow ghi metric khi cấu hình metrics được bật:

~~~java
@Configuration
public class OptionalFlowConfiguration {

    @Bean
    @ConditionalOnProperty(
        name = "broker.events.metrics-enabled",
        havingValue = "true")
    CreateServiceInstanceCompletionFlow provisionMetricsFlow(
            BrokerMetrics metrics) {

        return new CreateServiceInstanceCompletionFlow() {
            @Override
            public Mono<Void> complete(
                    CreateServiceInstanceRequest request,
                    CreateServiceInstanceResponse response) {
                return metrics.recordProvisionSuccess(request);
            }
        };
    }
}
~~~

Trong ví dụ, bean chỉ được tạo khi property có giá trị true. Nếu property không bật, registry không nhận flow này. Đây là cách thuận tiện để bật/tắt tích hợp phụ trợ theo môi trường mà không cần tự quản lý registry.

Có thể dùng @Profile cho flow chỉ dành cho development hoặc test. Không nên để một flow test-only được component scan trong production.

## 15. Kiểm thử event flow

Nên kiểm thử hai lớp: hành vi của flow riêng lẻ và việc framework thực sự gọi flow trong request lifecycle.

### Unit test

Kiểm tra flow nhận đúng request, gọi service phụ trợ đúng dữ liệu và trả Mono hoàn tất hoặc lỗi như mong đợi.

Ví dụ với initialization flow:

~~~java
@Test
void validateProvisionRequest() {
    CreateServiceInstanceInitializationFlow flow =
        new CreateServiceInstanceInitializationFlow() {
            @Override
            public Mono<Void> initialize(
                    CreateServiceInstanceRequest request) {
                return policyService.validate(request);
            }
        };

    StepVerifier.create(flow.initialize(validRequest))
        .verifyComplete();
}
~~~

Ví dụ minh họa cần được đặt trong test class có các dependency và fixture tương ứng. Với lỗi policy, kiểm tra publisher phát đúng exception và không gọi provider.

### Integration test

Khởi động Spring application context với cấu hình event flow thực tế, gửi request qua broker endpoint hoặc gọi service event wrapper, rồi xác nhận:

- Flow bean được phát hiện và đăng ký.
- Initialization flow chạy trước nghiệp vụ chính.
- Completion flow chỉ chạy sau response thành công.
- Error flow nhận lỗi phù hợp.
- Flow không bị đăng ký trùng khi context khởi động.
- Flow không được bật khi profile/property không phù hợp.
- Registry mặc định vẫn tồn tại khi ứng dụng chỉ thêm flow bean.
- Các flow binding không bị đăng ký nhầm vào registry instance.

Nếu tự khai báo registry bean, integration test cần xác nhận đầy đủ flow mặc định hoặc flow bean cần thiết vẫn được giữ lại.

### Kiểm thử lỗi và reactive lifecycle

Dùng StepVerifier hoặc công cụ test Reactor phù hợp để kiểm tra completion, error và cancellation. Mô phỏng dependency chậm hoặc lỗi để xác nhận flow không chặn event-loop và không làm mất lỗi gốc.

Với last-operation flow, gửi nhiều lần request poll và xác nhận audit/metric không tạo side effect nghiệp vụ lặp.

## 16. Những lỗi triển khai thường gặp

**Đăng ký flow trong mỗi request.** Registry tích lũy flow và một request sau có thể chạy hook nhiều lần. Đăng ký một lần trong cấu hình khởi động.

**Quên subscribe Mono trả về từ add...Flow().** Việc thêm flow không được thực thi nếu publisher không được subscribe. Trong cấu hình trực tiếp, hãy thực thi chuỗi đăng ký lúc startup; hoặc dùng bean flow để framework tự nhận diện.

**Tạo registry mới không cần thiết.** Custom registry có thể thay thế auto-configuration và làm mất flow khác. Dùng registry mặc định trừ khi thực sự cần thay thế.

**Đưa toàn bộ nghiệp vụ vào event flow.** Flow trở nên khó kiểm thử và khó theo dõi. Giữ nghiệp vụ trong service/coordinator, flow chỉ gọi đúng extension point.

**Gọi subscribe() trong flow.** Framework không chờ công việc hoàn tất và khó nhận lỗi. Trả Mono<Void> cho framework.

**Ghi credentials vào audit.** Event có thể được chuyển đến log hoặc hệ thống tập trung. Chỉ ghi định danh, trạng thái và mã lỗi đã làm sạch.

**Không xử lý flow lỗi.** Một lỗi telemetry có thể làm request thất bại ngoài ý muốn; một lỗi policy lại cần chặn request. Phân biệt rõ lỗi bắt buộc và lỗi phụ trợ.

**Giả định thứ tự nhiều bean.** Thứ tự khai báo không phải hợp đồng nghiệp vụ. Gom các bước phụ thuộc vào một flow hoặc coordinator.

**Dùng last-operation flow để chạy lại provisioning.** Nền tảng có thể poll nhiều lần. Last-operation flow chỉ nên xử lý việc truy vấn và quan sát trạng thái.

## 17. Nguyên tắc lựa chọn cho Spring Cloud Service Broker

Đối với cấu hình thông thường, hãy khai báo event flow thành Spring bean theo interface cụ thể. Framework tự nhận diện và thêm chúng vào registry tương ứng. Cách này giữ cấu hình gần với dependency, profile và điều kiện của Spring Boot.

Dùng registry trực tiếp khi cần đăng ký bằng code hoặc khi tập flow phụ thuộc vào cấu hình được xác định lúc khởi động. Inject registry do framework cung cấp và thực hiện đăng ký đúng một lần. Chỉ tự khai báo registry bean khi thực sự cần thay đổi cấu trúc auto-configuration và đã bảo đảm các flow cần thiết vẫn được đăng ký.

Dùng initialization flow cho kiểm tra trước nghiệp vụ, completion flow cho hậu xử lý thành công và error flow cho ghi nhận/điều phối xử lý lỗi. Giữ các flow reactive, idempotent và không làm lộ credentials. Với workflow nhiều bước, retry hoặc compensation, hãy giao cho coordinator bền vững thay vì phân tán logic vào nhiều hook độc lập.

Cách đăng ký rõ ràng giúp service broker mở rộng lifecycle của instance và binding mà vẫn giữ được trách nhiệm của ServiceInstanceService, ServiceInstanceBindingService và provider adapter. Nhờ đó, các chính sách dùng chung như audit, metrics và validation có thể được tích hợp nhất quán trên nhiều operation.

## Tài liệu tham khảo

- [Spring Cloud Open Service Broker Reference – Event Flow Configuration](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/reference/#example-event-flow-configuration)
- [CreateServiceInstanceEventFlowRegistry API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/service/events/CreateServiceInstanceEventFlowRegistry.html)
- [EventFlowRegistry API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/service/events/EventFlowRegistry.html)

