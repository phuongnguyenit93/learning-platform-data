# Xác minh thay đổi mặc định của danh tính, retry và listener

Khi nâng Spring Boot, Spring Cloud OCI hoặc OCI Java SDK, ứng dụng có thể thay đổi hành vi dù file cấu hình không đổi. Một property không được khai báo sẽ lấy giá trị mặc định từ thư viện đang chạy. Nếu version mới bổ sung authentication provider, cập nhật retry policy hoặc thay dependency Spring Messaging, hành vi thực tế có thể khác với môi trường cũ.

Việc nâng cấp cần xác minh ba nhóm hành vi độc lập:

- **Danh tính (identity):** ứng dụng đang xác thực bằng profile API key, Instance Principal, Resource Principal, Session Token hay Workload Identity?
- **Retry:** tầng nào đang retry, operation nào được bật retry mặc định, số lần và backoff là bao nhiêu?
- **Listener:** consumer có tự khởi động không, có bao nhiêu consumer, listener chờ message bao lâu, xử lý lỗi và transaction/acknowledgement ra sao?

Không thể kết luận default đã thay đổi chỉ vì version tăng. Cần so sánh release notes, tài liệu đúng version, dependency graph và hành vi quan sát được trong runtime. Bài này xây dựng quy trình kiểm tra để phát hiện thay đổi có thật, nhận diện default được giữ nguyên và khóa các giá trị quan trọng trước khi rollout.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao một upgrade có thể đổi hành vi dù application configuration không đổi.
2. Phân biệt default của Spring Cloud OCI, OCI Java SDK, Spring Cloud Stream và Spring JMS.
3. So sánh authentication defaults giữa Spring Cloud Oracle 1.x và 2.x.
4. Xác minh kiểu authentication, profile và region thực tế.
5. Phân biệt retry ở SDK operation, message listener và broker redelivery.
6. Đọc retry policy của OCI Java SDK theo từng operation.
7. Kiểm tra số lần retry, điều kiện retry, backoff và precedence.
8. Xác minh listener auto-startup, concurrency, timeout và transaction mode.
9. Phân biệt OCI Queue/Streaming API consumer với Spring Cloud Stream listener.
10. Xác định những default nào được tài liệu công bố và những giá trị nào phải kiểm tra từ runtime.
11. Tạo cấu hình tường minh cho production sau khi nâng cấp.
12. Thiết kế regression test cho identity, retry và listener.
13. Rollout/rollback an toàn khi hành vi runtime thay đổi.
14. Lưu bằng chứng trước/sau để lần nâng cấp tiếp theo có thể lặp lại.

## 2. Vì sao cần kiểm tra default khi nâng cấp?

Spring Boot và Spring Cloud sử dụng auto-configuration. Nếu không khai báo một property, framework sẽ lấy default từ thư viện hoặc module đang có trên classpath.

Ví dụ, một service có thể không khai báo:

- spring.cloud.oci.config.type
- spring.cloud.oci.config.profile
- spring.cloud.stream.bindings.orders-in-0.consumer.concurrency
- spring.cloud.stream.bindings.orders-in-0.consumer.max-attempts
- spring.jms.listener.auto-startup
- spring.jms.listener.session.transacted

Khi nâng version, dependency mới có thể:

- Thêm một authentication mode.
- Cập nhật OCI SDK và retry behavior.
- Đổi phiên bản Spring Cloud Stream hoặc Spring Framework.
- Cập nhật auto-configuration condition.
- Thay cách listener container được tạo.
- Thay default của một property hoặc cách property được bind.
- Giữ nguyên default nhưng thay implementation bên dưới.

~~~mermaid
flowchart TD
    A[Upgrade Spring Boot / Spring Cloud / OCI SDK] --> B[Resolved dependency graph thay đổi?]
    B --> C[Auto-configuration và default thay đổi?]
    C --> D[Identity / Retry / Listener behavior]
    D --> E[Quan sát runtime]
    E --> F{Có khác baseline?}
    F -->|Không| G[Ghi nhận default được giữ nguyên]
    F -->|Có| H[Đánh giá ảnh hưởng và cấu hình tường minh]
    H --> I[Regression test]
    I --> J[Canary / rollout]
~~~

Một release note không nhắc tới authentication hoặc listener không phải bằng chứng tuyệt đối rằng không có thay đổi. Nó chỉ cho biết project không công bố thay đổi đó trong phần release notes. Cần kiểm tra dependency graph, configuration metadata và runtime behavior.

## 3. Xác định chính xác những version đang được nâng

Trước khi so sánh default, ghi nhận version của từng lớp:

| Lớp | Ví dụ cần ghi lại |
| --- | --- |
| Java runtime | Java 17, 21 hoặc version đang dùng |
| Spring Boot | Parent/plugin và resolved Boot artifacts |
| Spring Framework | spring-core, spring-context, spring-jms |
| Spring Cloud release train | BOM nếu ứng dụng có dùng |
| Spring Cloud OCI | spring-cloud-oci-starter và module service |
| OCI Java SDK | OCI SDK module/version được resolve |
| Spring Cloud Stream | Version của core và binder |
| Oracle TxEventQ binder | Version độc lập với OCI starter |
| Spring JMS/AQ-JMS | Spring Integration JMS và AQ API |

Spring Cloud OCI 2.0.4 là một release line độc lập. Release notes 2.0.4 ghi nâng Spring Boot lên 4.1.1 và refresh third-party dependencies. Release notes 2.0.0 ghi hỗ trợ Spring Boot 4 và Spring Framework 7. Những thay đổi này yêu cầu kiểm tra dependency graph và integration behavior, kể cả khi không có dòng release note riêng về retry/listener.

Không giả định OCI SDK version chỉ từ tên starter. Đọc dependency tree để biết chính xác version được kéo vào runtime.

### 3.1. Maven

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.boot,org.springframework,org.springframework.cloud,com.oracle.cloud.spring,com.oracle.oci.sdk
~~~

Lưu output của version cũ và version mới. Tập trung vào:

- Spring Boot parent/BOM.
- Spring Framework modules.
- Spring Cloud Stream.
- spring-cloud-oci-core và service modules.
- OCI Java SDK common và service-specific modules.
- Spring Integration JMS.
- Oracle AQ-JMS API nếu dùng TxEventQ qua JMS.

### 3.2. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-oci-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency oci-java-sdk-common --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-stream --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-jms --configuration runtimeClasspath
~~~

Ghi cả dependency constraints, forced version và platform/BOM đang tác động tới resolution.

### 3.3. Tạo bảng so sánh trước/sau

| Hạng mục | Trước nâng cấp | Sau nâng cấp | Bằng chứng |
| --- | --- | --- | --- |
| Spring Boot | Version đã khóa | Version đích | Effective POM/Gradle graph |
| OCI starter | Version cũ | Version mới | Dependency tree |
| OCI SDK | Version cũ | Version mới | Resolved runtime graph |
| Auth type | Giá trị hiệu lực | Giá trị hiệu lực | Property + audit principal |
| Retry | Policy hiệu lực | Policy hiệu lực | SDK Javadoc + test |
| Listener | Auto-start/concurrency | Auto-start/concurrency | Runtime config + metrics |
| Error handling | Retry/DLQ/transaction | Retry/DLQ/transaction | Integration test |

Không ghi same nếu chỉ kiểm tra file application.yaml. Cần kiểm tra giá trị đã bind và behavior thực tế.

## 4. Xác minh default của danh tính OCI

### 4.1. FILE vẫn là default của Spring Cloud OCI

Tài liệu Spring Cloud Oracle 1.0.0 và tài liệu 2.0.4 đều ghi configuration-file authentication là default. Property:

| Property | Default hiện hành | Ý nghĩa |
| --- | --- | --- |
| spring.cloud.oci.config.type | FILE | Kiểu authentication |
| spring.cloud.oci.config.profile | DEFAULT | Profile trong OCI config file |
| spring.cloud.oci.config.file | Không có giá trị mặc định cố định | Đường dẫn config file |
| spring.cloud.oci.config.region | Không có giá trị mặc định cố định | Region trong auth configuration |
| spring.cloud.oci.region.static | Không có giá trị mặc định cố định | Region dùng cho API call |
| spring.cloud.oci.compartment.static | Không có giá trị mặc định cố định | Compartment mặc định |

Điều quan trọng khi so sánh 1.x và 2.x:

- Default authentication type FILE được giữ nguyên trong tài liệu 1.0.0 và 2.0.4.
- Profile DEFAULT vẫn là profile mặc định.
- Các auth mode hiện hành gồm FILE, SIMPLE, INSTANCE_PRINCIPAL, RESOURCE_PRINCIPAL, SESSION_TOKEN và WORKLOAD_IDENTITY.
- Tài liệu 1.0.0 liệt kê ít lựa chọn hơn; các auth mode bổ sung ở release line mới không tự động được chọn nếu property không thay đổi.

Vì vậy, không kết luận nâng 2.x tự chuyển ứng dụng sang Instance Principal hoặc Workload Identity. Nếu không cấu hình spring.cloud.oci.config.type, Spring Cloud OCI vẫn chọn FILE theo default đã công bố.

### 4.2. FILE default có thể gây lỗi khi chuyển runtime

Một ứng dụng chạy local có ~/.oci/config sẽ hoạt động với FILE. Khi đưa cùng image lên Compute hoặc OKE, file đó có thể không tồn tại. Ứng dụng có thể:

- Không khởi động do không tìm được config file.
- Đọc nhầm profile mặc định.
- Dùng API key của user không đúng môi trường.
- Chạy được nhưng nhận 403 do policy của user không phù hợp.

Production nên cấu hình rõ identity theo runtime.

Local:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
~~~

OCI Compute:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
~~~

OCI Functions:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: RESOURCE_PRINCIPAL
~~~

OKE đã cấu hình federation:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: WORKLOAD_IDENTITY
~~~

Đây là cấu hình theo môi trường. Không bật nhiều auth profile cùng lúc theo cách khiến identity được chọn không rõ ràng.

### 4.3. Kiểm tra region precedence

spring.cloud.oci.region.static có độ ưu tiên cao hơn spring.cloud.oci.config.region và region trong OCI auth configuration file.

Khi nâng cấp, một environment variable hoặc profile mới có thể làm region static xuất hiện mà trước đó không có. Client có thể chuyển sang endpoint khác dù OCI profile vẫn giữ nguyên.

Kiểm tra:

1. spring.cloud.oci.region.static.
2. spring.cloud.oci.config.region.
3. Region trong OCI config file.
4. Region của resource thực tế.
5. Region được ghi nhận trong audit/request.

Không chỉ xác minh authentication thành công; phải xác minh request đang đi đúng region.

### 4.4. Kiểm tra principal thực tế

Cấu hình cho biết ứng dụng định chọn provider nào. OCI Audit cho biết principal nào thực sự gọi API.

Kiểm tra:

- Local: OCI user OCID dự kiến.
- Compute: Instance Principal của đúng instance/dynamic group.
- Functions: Resource Principal của function.
- OKE: Workload Identity gắn với cluster, namespace và service account.
- IAM policy: principal có đúng quyền và scope không.

Nếu audit principal không khớp cấu hình dự kiến, dừng rollout và điều tra profile/environment override trước khi tiếp tục.

### 4.5. Cấu hình tường minh để tránh phụ thuộc default

Sau khi xác minh, có thể đặt rõ các property quan trọng:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: OCI_REGION
      compartment:
        static: OCI_COMPARTMENT_OCID
~~~

Trong ví dụ trên, các giá trị in hoa là placeholder cần được thay bằng giá trị deployment. Không ghi OCID hoặc credential thật vào source nếu policy yêu cầu externalize cấu hình.

## 5. Phân biệt ba tầng retry

Một lỗi có thể bị retry bởi nhiều lớp:

1. OCI Java SDK retry request tới OCI service.
2. Spring Cloud Stream retry khi function/consumer listener ném exception.
3. Broker hoặc message system redeliver message sau khi listener thất bại, session rollback hoặc visibility/ack deadline hết hạn.

Ba tầng này có mục tiêu và counter khác nhau. Nếu không phân biệt, một message có thể được xử lý nhiều lần hơn dự kiến.

~~~mermaid
flowchart TD
    A[Message đến consumer] --> B[Listener xử lý]
    B --> C{Gọi OCI API?}
    C -->|Có| D[OCI SDK retry operation]
    C -->|Không| E[Business handler]
    D --> E
    E --> F{Handler thành công?}
    F -->|Có| G[Commit / ack / checkpoint]
    F -->|Không| H[Spring listener retry]
    H --> I{Còn attempts?}
    I -->|Có| B
    I -->|Không| J[Broker redelivery / DLQ / error flow]
~~~

Sơ đồ là mô hình tổng quát. Thứ tự chính xác phụ thuộc binder, listener container và transaction mode. Không phải mọi service đều hỗ trợ redelivery hoặc DLQ theo cùng cách.

### 5.1. OCI SDK retry

OCI Java SDK có retry configuration ở cấp SDK/global, client và request. Tài liệu SDK cho biết retry mặc định được hỗ trợ từ SDK 2.10.0, nhưng không có nghĩa mọi operation đều tự retry. Mỗi service operation phải được kiểm tra trong Javadoc để biết operation đó có bật retry mặc định hay không.

Các nhóm lỗi SDK retry mặc định có thể gồm:

- HTTP 409 với service code IncorrectState.
- HTTP 429 throttling.
- HTTP 500, 502, 503 và 504.
- Connection/read timeout.
- Request connection errors.
- Request exceptions.
- Circuit breaker exceptions.

Không retry tất cả lỗi 4xx. Authentication 401, authorization 403 và validation 400 thường cần sửa credential, policy hoặc request thay vì gửi lại liên tục.

### 5.2. Default strategy của OCI Java SDK

Tài liệu OCI Java SDK mô tả default retry strategy như sau:

| Thành phần | Default được công bố |
| --- | --- |
| Termination strategy | MaxAttemptsTerminationStrategy với giá trị 8 |
| Delay strategy | Exponential backoff |
| Jitter | Ngẫu nhiên trong khoảng 0–1000 ms |
| Maximum delay giữa các lần gọi | 30 giây |
| Retryable errors | Theo DefaultRetryCondition và mô tả từng operation |
| Async client | Không hỗ trợ retry mặc định theo tài liệu SDK |

8 là giá trị max-attempts của termination strategy. Khi nâng SDK, hãy kiểm tra Javadoc đúng version và cách implementation tính attempt cho operation đang dùng; không tự quy đổi thành 8 lần retry cộng thêm lần gọi đầu nếu tài liệu của version đó không xác nhận.

### 5.3. Retry được bật theo operation

Mỗi service operation có thể ghi một trong các mô tả:

- Operation dùng RetryConfiguration.SDK_DEFAULT_RETRY_CONFIGURATION nếu request không cung cấp retry strategy.
- Operation không retry mặc định; caller có thể bật retry bằng SDK default.
- Operation có retry behavior riêng.

Do đó, hai method trong cùng một client có thể có hành vi khác nhau. Khi nâng SDK, kiểm tra operation quan trọng trong Javadoc của version đang resolve thay vì chỉ đọc retry configuration chung.

### 5.4. Retry precedence

OCI SDK cho phép cấu hình ở nhiều cấp. Thứ tự ưu tiên:

1. Request-level retry configuration.
2. Client-level retry configuration.
3. Global/default retry configuration và environment override.

Request-level có thể override policy của client cho request đó. Client-level có thể override global/default cho client tương ứng.

Biến môi trường OCI_SDK_DEFAULT_RETRY_ENABLED=false dùng để tắt default retry toàn cục. Nếu code đặt retry configuration tường minh ở client hoặc request, cấu hình tường minh đó có thể ghi đè environment default.

### 5.5. Async client là trường hợp riêng

Tài liệu OCI Java SDK hiện hành ghi rõ retry mặc định không được hỗ trợ cho asynchronous clients. Nếu upgrade làm một integration chuyển từ synchronous sang asynchronous client, không được giả định retry behavior giống trước.

Với async client, cần:

- Xác định retry owner.
- Phân loại lỗi transient.
- Đặt tổng retry budget.
- Kiểm tra request body có thể gửi lại không.
- Có idempotency key hoặc reconciliation.
- Không retry vô hạn trong callback/executor.

## 6. Spring Cloud Stream consumer retry

Spring Cloud Stream có retry policy riêng cho input binding. Các giá trị mặc định hiện hành trong binding properties reference:

| Property | Default | Ý nghĩa |
| --- | --- | --- |
| autoStartup | true | Consumer binding tự khởi động |
| concurrency | 1 | Số consumer song song |
| maxAttempts | 3 | Tổng số lần xử lý, gồm lần đầu |
| backOffInitialInterval | 1000 ms | Backoff ban đầu |
| backOffMaxInterval | 10000 ms | Backoff tối đa |
| backOffMultiplier | 2.0 | Hệ số tăng backoff |
| defaultRetryable | true | Exception chưa khai báo mặc định được retry |
| retryableExceptions | Rỗng | Map exception class tới true/false |

Với maxAttempts=3, listener có tối đa ba lần xử lý trong retry cycle của Spring Cloud Stream: lần đầu và hai lần retry. Đây là retry của listener, không phải retry của OCI SDK.

Các con số này thuộc Spring Cloud Stream ConsumerProperties. Trang tham chiếu 5.1.0 công bố các giá trị trên; nếu dependency graph của ứng dụng resolve một version khác, hãy dùng binding properties reference tương ứng với version đó.

### 6.1. Retry listener khác redelivery của broker

Nếu listener ném exception:

1. Spring Cloud Stream có thể gọi lại listener theo maxAttempts.
2. Nếu retry cycle thất bại, binder/error handler quyết định bước tiếp.
3. Tùy binder, message có thể bị reject, requeue, redeliver hoặc gửi DLQ.
4. Nếu transaction rollback, broker có thể giao lại message theo semantics của broker.

Không cộng maxAttempts=3 với một số redelivery broker cố định nếu chưa biết binder behavior. Ghi nhận cả listener attempts và broker delivery count.

### 6.2. Ví dụ khóa retry theo binding

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        invoiceConsumer-in-0:
          destination: invoice-events
          group: invoice-workers
          consumer:
            auto-startup: true
            concurrency: 1
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
            default-retryable: true
~~~

Các giá trị trên lặp lại default để cấu hình trở nên tường minh. Nếu production cần khác, thay theo latency budget và khả năng chịu lỗi của workload.

### 6.3. Chỉ retry lỗi có khả năng hồi phục

Ví dụ phân loại:

| Exception/condition | Retry? | Lý do |
| --- | --- | --- |
| Temporary network timeout | Có, giới hạn | Có thể hồi phục |
| HTTP 429 | Có, theo backoff | Throttling |
| HTTP 503 | Có, giới hạn | Service tạm unavailable |
| Invalid payload/schema | Không | Retry không sửa được dữ liệu |
| HTTP 401/403 | Không | Cần sửa identity/policy |
| Business rule violation | Thường không | Không phải lỗi transient |
| Database deadlock | Có thể | Tùy transaction/idempotency |
| Duplicate business event | Không xử lý lại side effect | Deduplicate theo event ID |

Có thể khai báo exception cụ thể qua retryable-exceptions. Trước khi bật retry mặc định cho mọi exception, kiểm tra listener có ném exception nghiệp vụ không thể hồi phục hay không.

## 7. Xác minh listener mặc định theo từng programming model

Không có một listener default dùng chung cho tất cả OCI messaging integrations. Cần xác định ứng dụng đang dùng API nào.

| Integration | Consumer model | Default listener cần kiểm tra |
| --- | --- | --- |
| OCI Queue starter | Queue service bean và Queue API | Không có Spring @QueueListener mặc định trong starter docs |
| OCI Streaming starter | Streaming service bean và getMessages/cursor API | Không có Spring listener/container auto-start default trong starter docs |
| Oracle TxEventQ Stream Binder | Spring Cloud Stream function binding | autoStartup, concurrency, retry properties của Spring Cloud Stream |
| Oracle TxEventQ qua Spring JMS | @JmsListener và listener container | Spring Boot/JMS container defaults |

Điểm này quan trọng khi nâng cấp. Nếu ứng dụng dùng OCI Queue bean để tự poll, không thể lấy default concurrency của Spring Cloud Stream để suy ra số Queue consumers. Nếu ứng dụng dùng TxEventQ binder, không lấy Queue starter API để suy ra listener lifecycle.

### 7.1. OCI Queue và OCI Streaming

Spring Cloud OCI Queue starter auto-configure bean Queue để thao tác queue/message. Streaming starter auto-configure bean Streaming để tạo stream, gửi và nhận record.

Tài liệu starter mô tả API bean và operation, không công bố một Spring listener annotation hoặc listener container với auto-startup/concurrency default.

Nếu ứng dụng tự triển khai polling loop:

- Xác định số worker thread do ứng dụng tạo.
- Xác định poll interval và request timeout.
- Xác định message visibility/lease/settlement behavior theo Queue API.
- Xác định cursor và checkpoint theo Streaming API.
- Đảm bảo shutdown dừng poll loop.
- Giới hạn số message in-flight.
- Kiểm tra idempotency khi process restart.

Những giá trị này thuộc application implementation và OCI service API, không phải default listener của Spring Cloud OCI starter.

### 7.2. TxEventQ với Spring Cloud Stream binder

TxEventQ binder hỗ trợ functional Consumer, Function và Supplier. Consumer binding có thể được cấu hình như sau:

~~~yaml
spring:
  cloud:
    function:
      definition: invoiceConsumer
    stream:
      bindings:
        invoiceConsumer-in-0:
          destination: INVOICE_EVENTS
          group: INVOICE_WORKERS
          consumer:
            concurrency: 1
~~~

Tài liệu Oracle có ví dụ concurrency: 2; đó là giá trị cấu hình trong sample, không phải default. Default chung của Spring Cloud Stream consumer là 1.

Các property binder-specific:

- spring.cloud.stream.txeventq.bindings.<bindingName>.consumer.timeout
- spring.cloud.stream.txeventq.bindings.<bindingName>.consumer.batchSize

Binder timeout có default 1000 ms. Đây là thời gian tối đa consumer thread chờ trong mỗi lần consume operation, không phải timeout của business handler, không phải message retention và không phải listener shutdown timeout.

batchSize xác định số message tối đa trong một callback khi batch mode được bật. Property này bị bỏ qua nếu batch-mode=false.

### 7.3. TxEventQ với Spring JMS

Oracle TxEventQ cũng có thể được dùng qua Spring JMS:

~~~java
@Component
public class InvoiceJmsListener {

    @JmsListener(destination = "INVOICE_QUEUE")
    public void receive(String payload) {
        // Validate và xử lý message
    }
}
~~~

Oracle documentation xác nhận @JmsListener mặc định tạo DefaultMessageListenerContainer nếu không có factory khác. Với Spring Boot auto-configuration, các giá trị đáng kiểm tra gồm:

| Property | Default Boot/JMS được công bố |
| --- | --- |
| spring.jms.listener.auto-startup | true |
| spring.jms.listener.receive-timeout | 1s |
| spring.jms.listener.session.acknowledge-mode | auto |
| spring.jms.listener.min-concurrency | Không đặt mặc định; underlying container bắt đầu với 1 consumer |
| spring.jms.listener.max-concurrency | Không đặt mặc định |
| spring.jms.listener.session.transacted | true nếu không có JTA transaction manager; khi có JTA, container dùng transaction manager đó |

Spring Framework DefaultMessageListenerContainer có concurrentConsumers=1 và maxConcurrentConsumers=1 mặc định. Khi tăng concurrency, thứ tự xử lý có thể thay đổi và nhiều consumer có thể xử lý đồng thời.

Nếu ứng dụng khai báo custom DefaultJmsListenerContainerFactory, giá trị của factory có thể thay thế các default Boot. Vì vậy cần kiểm tra factory thực tế được @JmsListener sử dụng.

### 7.4. Transaction và acknowledgement của TxEventQ

TxEventQ có thể phối hợp database DML với send/consume trong một local transaction khi sử dụng transaction feature được hỗ trợ.

Với Spring JMS:

- Cần transacted JMS Session.
- AQjmsSession.getDBConnection() cung cấp JDBC connection gắn với session.
- DML và JMS operation được commit/rollback cùng nhau khi container commit session.

Với TxEventQ Stream Binder:

- Functional callback cần làm việc trực tiếp với Spring Message.
- TxEventQUtils.getDBConnection(message) lấy JDBC connection gắn với consume operation.
- DML và message consume/produce có thể cùng một local transaction theo binder feature.

Không suy rộng transaction semantics này sang OCI Queue hoặc OCI Streaming. Với những service đó, dùng inbox/outbox, idempotency hoặc reconciliation phù hợp.

## 8. Những thay đổi có thể xuất hiện sau upgrade

Khi version tăng, một số thay đổi có thể ảnh hưởng runtime dù file config không đổi:

| Nguồn thay đổi | Ảnh hưởng có thể gặp |
| --- | --- |
| OCI SDK patch | Operation được bật retry hoặc retry condition thay đổi |
| Spring Cloud Stream patch/minor | Binding defaults, retry integration hoặc lifecycle thay đổi |
| Spring Boot/Spring Framework | Listener factory auto-configuration, transaction defaults hoặc property binding thay đổi |
| TxEventQ binder | Consumer polling, batch behavior, transaction integration hoặc compatibility thay đổi |
| OCI authentication module | Auth mode mới, provider implementation hoặc token handling thay đổi |
| Environment/profile | Property override làm đổi identity, region, retry hoặc listener |

Đừng đánh giá upgrade chỉ bằng release note. Hãy so sánh runtime effective configuration và test cùng một workload trên hai version.

### 8.1. Kết luận có thể rút ra từ tài liệu công khai

| Hạng mục | Bằng chứng so sánh | Kết luận an toàn |
| --- | --- | --- |
| OCI authentication default | Tài liệu 1.0.0 và 2.0.4 đều ghi FILE; profile DEFAULT vẫn được giữ | Không có bằng chứng default FILE đổi trong hai mốc tài liệu này |
| Auth modes | Tài liệu 1.0.0 liệt kê FILE, SIMPLE, INSTANCE_PRINCIPAL và RESOURCE_PRINCIPAL; tài liệu hiện hành liệt kê thêm SESSION_TOKEN và WORKLOAD_IDENTITY | Tập lựa chọn được mở rộng; không đồng nghĩa ứng dụng tự chuyển sang mode mới |
| OCI SDK retry | SDK docs mô tả operation-specific default retry; OCI release notes 2.0.4 chỉ ghi refresh third-party dependencies | Phải kiểm tra SDK version và Javadoc của từng operation; release note không xác nhận retry policy giữ nguyên |
| Spring Cloud Stream listener | Default autoStartup/concurrency/retry thuộc Spring Cloud Stream ConsumerProperties | So sánh version Spring Cloud Stream thực tế mà binder resolve; không gán mọi khác biệt cho OCI starter |
| TxEventQ binder | Oracle docs công bố consumer timeout 1000 ms và các thuộc tính batch riêng | Kiểm tra binder version, batch-mode và transaction configuration riêng |
| Spring JMS listener | Default do Spring Boot auto-configuration và listener factory quyết định | Kiểm tra Boot version, custom factory, JTA và session transaction mode |

Release notes Spring Cloud Oracle 2.0.4 nêu nâng Spring Boot lên 4.1.1 và refresh third-party dependencies, nhưng không công bố một thay đổi cụ thể cho default identity, SDK retry hoặc listener concurrency. Điều đó không đủ để kết luận runtime không đổi; nó xác định các điểm cần kiểm tra bằng dependency graph và regression test.

## 9. Cấu hình tường minh cho production

Một cách giảm phụ thuộc vào default là đặt rõ những giá trị ảnh hưởng đến bảo mật và delivery.

### 9.1. Identity

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: OCI_REGION
~~~

### 9.2. Spring Cloud Stream listener

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        invoiceConsumer-in-0:
          destination: INVOICE_EVENTS
          group: INVOICE_WORKERS
          consumer:
            auto-startup: true
            concurrency: 2
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
            default-retryable: true
~~~

Chỉ tăng concurrency sau khi đo throughput, DB pool, downstream capacity và ordering requirements. Giá trị 2 là ví dụ cấu hình, không phải default.

### 9.3. Spring JMS listener

~~~yaml
spring:
  jms:
    listener:
      auto-startup: true
      min-concurrency: 1
      max-concurrency: 1
      receive-timeout: 1s
      session:
        acknowledge-mode: auto
        transacted: true
~~~

Nếu dùng JTA hoặc custom listener factory, xác minh transaction manager và factory thực tế. Không đặt session.transacted=true một cách máy móc nếu ứng dụng đang dùng JTA hoặc transaction semantics khác.

### 9.4. OCI SDK retry

Retry SDK nên được cấu hình theo client/request và operation. Ví dụ request-level có thể giới hạn số attempts:

~~~java
RetryConfiguration noRetry =
        RetryConfiguration.builder()
                .terminationStrategy(new MaxAttemptsTerminationStrategy(1))
                .build();

GetObjectRequest request = GetObjectRequest.builder()
        .namespaceName(namespace)
        .bucketName(bucketName)
        .objectName(objectName)
        .retryConfiguration(noRetry)
        .build();
~~~

Ví dụ trên minh họa request override. Trong ứng dụng thật, chọn retry policy theo operation idempotency, request body replayability và timeout budget. Không tắt retry toàn cục nếu chỉ một operation cần xử lý đặc biệt.

## 10. Quy trình xác minh trước và sau upgrade

### Bước 1 — Chụp baseline

Lưu:

- Dependency tree/runtimeClasspath.
- Effective application properties đã được bind.
- Principal xuất hiện trong OCI Audit.
- Retry behavior của operation quan trọng.
- Listener auto-startup/concurrency.
- Message attempts/redelivery/DLQ.
- Consumer lag/queue depth.
- Database transaction/acknowledgement behavior.

### Bước 2 — So sánh tài liệu đúng version

Đọc:

- Spring Cloud Oracle release notes.
- OCI Core và Configuration Properties docs.
- OCI Java SDK Javadoc cho operation đang dùng.
- Spring Cloud Stream binding properties đúng version.
- Spring Boot JMS application properties đúng version.
- Oracle TxEventQ binder docs và binder-specific properties.

Không dùng tài liệu latest để kết luận cho một runtime version cũ nếu API/default đã đổi. Ghi lại URL/version và ngày kiểm tra.

### Bước 3 — Kiểm tra effective configuration

Dùng Spring Boot Actuator configprops hoặc configuration metadata trong môi trường kiểm thử để kiểm tra property đã bind. Có thể dùng auto-configuration report (--debug) để xác định bean/container nào được tạo.

Không expose env, configprops, beans hoặc endpoint nhạy cảm ra public. Các endpoint này có thể tiết lộ cấu hình và thông tin nội bộ. Nếu cần dùng Actuator trong production, giới hạn bằng authentication, network policy và endpoint exposure.

### Bước 4 — Kiểm tra identity

- Khởi động bằng identity của môi trường test.
- Gọi operation read-only trước.
- Xác minh principal trong OCI Audit.
- Kiểm tra region và compartment.
- Kiểm tra IAM positive/negative.
- Xác nhận không có profile/API key cũ bị nạp ngầm.

### Bước 5 — Kiểm tra retry

Tạo các tình huống có kiểm soát:

- Một request thành công ngay lần đầu.
- Một lỗi transient như 429/503.
- Một lỗi không retry như 400/401/403.
- Timeout sau khi server có thể đã nhận request.
- Một operation không idempotent.
- Một async SDK client nếu ứng dụng có dùng.

Ghi số request thực tế, thời gian giữa các lần retry, request ID và kết quả cuối. Không chỉ đếm exception trong application log.

### Bước 6 — Kiểm tra listener

- Container/binding có tự start không?
- Có đúng số consumer không?
- Consumer có thể stop/start qua lifecycle không?
- Exception được retry bao nhiêu lần?
- Message sau khi hết retry được xử lý ra sao?
- Ack/commit có xảy ra sau business transaction không?
- Shutdown có chờ xử lý message đang chạy không?
- Có duplicate khi process restart không?
- Ordering có thay đổi khi concurrency tăng không?

### Bước 7 — So sánh và phê duyệt rollout

Chỉ rollout khi:

- Identity đúng và quyền tối thiểu.
- Retry nằm trong latency budget.
- Listener concurrency phù hợp capacity.
- Không có duplicate side effect ngoài dự kiến.
- Transaction/ack semantics đã kiểm chứng.
- DLQ/replay/reconciliation hoạt động.
- Metrics và alert có thể phát hiện lỗi mới.

## 11. Regression test matrix

| Nhóm | Test | Kết quả mong đợi |
| --- | --- | --- |
| Identity | FILE profile local | Principal là user test |
| Identity | Instance Principal trên Compute | Principal là đúng instance |
| Identity | Resource/Workload Identity | Principal khớp resource/workload |
| Identity | Thiếu IAM policy | Request bị từ chối, không fallback admin |
| SDK retry | 429/503 | Retry theo policy của operation |
| SDK retry | 401/403 | Không retry vô hạn |
| SDK retry | Async client | Xử lý lỗi theo retry logic của ứng dụng |
| Stream listener | Binding startup | Theo autoStartup đã khóa |
| Stream listener | Handler throws | Số attempts đúng maxAttempts |
| Stream listener | Concurrency | Số consumer đúng cấu hình |
| JMS listener | Container startup | Đúng lifecycle và receive timeout |
| JMS listener | Transaction rollback | Message không bị mất trước commit |
| TxEventQ | DML + consume | Cùng transaction theo binder/JMS mode được hỗ trợ |
| Recovery | App restart | Message chưa commit được xử lý lại an toàn |
| Duplicate | Redelivery | Side effect idempotent |
| DLQ | Hết retry | Message đi theo error/DLQ flow đã cấu hình |

## 12. Các lỗi thường gặp sau upgrade

### 12.1. Ứng dụng vẫn dùng FILE trong production

Nguyên nhân: spring.cloud.oci.config.type không được khai báo và default FILE vẫn hoạt động.

Xử lý:

- Đặt auth type rõ ràng theo runtime.
- Kiểm tra environment variable/profile.
- Xác minh principal qua OCI Audit.
- Không đưa API key cá nhân vào image để chữa lỗi.

### 12.2. Retry tăng bất ngờ

Nguyên nhân có thể:

- OCI SDK mới bật retry cho operation trước đây không retry.
- Request-level/client-level retry override bị xóa.
- Listener retry và broker redelivery cùng xảy ra.
- Một error mới được xếp vào nhóm retryable.

Xử lý:

- Xác định request ID và operation.
- Kiểm tra Javadoc operation của SDK version đang chạy.
- Kiểm tra retry config ở cả ba tầng.
- Kiểm tra event/message có duplicate không.
- Đặt idempotency và retry budget.

### 12.3. Listener xử lý chậm hoặc backlog tăng

Nguyên nhân có thể:

- concurrency vẫn là 1 sau khi workload tăng.
- Listener retry giữ consumer thread trong backoff.
- receive-timeout hoặc binder timeout không phù hợp.
- Connection pool không đủ.
- Database transaction kéo dài.

Xử lý:

- Đo consumer throughput và processing duration.
- Kiểm tra DB pool và downstream capacity.
- Tăng concurrency có kiểm soát.
- Tách retry chậm sang DLQ/retry queue nếu binder hỗ trợ.
- Tránh giữ transaction mở trong thời gian gọi external API.

### 12.4. Message được xử lý nhiều lần

Nguyên nhân:

- Business commit xong nhưng ack/settlement thất bại.
- Process chết trước checkpoint.
- Listener retry và broker redelivery bị cộng dồn.
- Timeout khiến client không biết operation đã hoàn thành chưa.

Xử lý:

- Dùng business event ID/inbox table.
- Commit business effect và marker idempotency cùng transaction khi có thể.
- Với TxEventQ, tận dụng transaction integration được hỗ trợ.
- Với OCI Queue/Streaming, thiết kế reconciliation và deduplication riêng.

### 12.5. Listener không khởi động

Kiểm tra:

- auto-startup có bị set false không?
- Có custom listener factory không?
- Binding function definition có đúng tên bean không?
- Binder/destination có resolve được không?
- Database/Queue connectivity có thành công không?
- Auto-configuration condition có match không?

Không mặc định lỗi là do service unavailable; có thể binding bị tắt bởi property hoặc profile.

## 13. Rollout và rollback

### Trước rollout

- Pin version của Boot, Spring Cloud, OCI SDK và binder.
- Khóa auth type và listener settings.
- Lưu dependency tree và effective config.
- Chạy regression test.
- Chuẩn bị rollback image và cấu hình cũ.
- Xác định message có thể được xử lý bởi cả version cũ và mới hay không.

### Canary

Triển khai một nhóm nhỏ consumer:

1. Xác minh principal và policy.
2. Quan sát retry count và error code.
3. Quan sát queue depth/stream lag.
4. Kiểm tra duplicate và ordering.
5. Kiểm tra transaction/ack.
6. Tăng replica sau khi hành vi ổn định.

### Rollback

Nếu cần rollback:

- Dừng consumer mới theo lifecycle đã kiểm chứng.
- Đảm bảo message chưa commit vẫn có thể được xử lý bởi version cũ.
- Không xóa queue, stream cursor hoặc checkpoint.
- Tránh downgrade schema/payload mà consumer cũ không hiểu.
- Khôi phục dependency graph và config baseline.
- Reconcile operation timeout/unknown outcome trước khi phát lại message.

## 14. Bài thực hành: xác minh upgrade Invoice Worker

**Bối cảnh:** Invoice Worker nâng Spring Boot và Spring Cloud OCI. Ứng dụng dùng Instance Principal để đọc secret từ Vault, nhận message từ Oracle TxEventQ qua Spring Cloud Stream binder và gọi Object Storage SDK để đọc PDF.

Nhiệm vụ là chứng minh identity, SDK retry và listener behavior không đổi ngoài chủ đích.

### Phần A — Identity

1. Ghi version Spring Cloud OCI trước/sau.
2. Ghi effective spring.cloud.oci.config.type.
3. Xác nhận production dùng INSTANCE_PRINCIPAL.
4. Kiểm tra principal trong OCI Audit.
5. Kiểm tra IAM policy chỉ cho phép đọc secret/object cần thiết.
6. Xác nhận không có FILE profile bị nạp ngoài ý muốn.

### Phần B — Retry

1. Ghi OCI SDK version thực tế.
2. Kiểm tra Javadoc của GetObject operation.
3. Kiểm tra request/client/global retry config.
4. Kiểm tra Spring Cloud Stream maxAttempts và backoff.
5. Tạo test 503 và 403.
6. Đếm số lần gọi OCI API và số lần listener chạy.
7. Xác minh không tạo duplicate business effect.

### Phần C — Listener

1. Ghi autoStartup, concurrency, maxAttempts.
2. Kiểm tra TxEventQ binder timeout và batch mode.
3. Chạy consumer với concurrency 1.
4. Tăng concurrency lên 2 trong môi trường test.
5. Gây lỗi sau khi consume trước business commit.
6. Xác minh rollback/redelivery.
7. Kiểm tra shutdown và restart.
8. Kiểm tra message được xử lý đúng một lần về mặt business.

### Phần D — Báo cáo

Tạo bảng:

| Hạng mục | Trước upgrade | Sau upgrade | Kết luận |
| --- | --- | --- | --- |
| Auth type |  |  |  |
| Audit principal |  |  |  |
| OCI SDK retry |  |  |  |
| Stream maxAttempts |  |  |  |
| Listener auto-start |  |  |  |
| Listener concurrency |  |  |  |
| TxEventQ timeout |  |  |  |
| Transaction/ack |  |  |  |
| Duplicate test |  |  |  |

### Sản phẩm cần nộp

- Dependency tree/effective POM trước và sau.
- Bảng authentication defaults và principal audit.
- Bảng retry policy theo OCI operation.
- Bảng Spring Cloud Stream/JMS listener settings.
- Integration test 429/503/403 và timeout.
- Test concurrency, rollback, redelivery và duplicate.
- Metrics retry count, listener duration, consumer lag và DLQ.
- Quyết định giữ/đổi từng default cùng lý do.
- Rollout và rollback runbook.

## 15. Câu hỏi tự kiểm tra

1. Vì sao nâng version có thể đổi hành vi dù application.yaml không đổi?
2. FILE và DEFAULT có còn là default trong Spring Cloud OCI 2.0.4 không?
3. SESSION_TOKEN và WORKLOAD_IDENTITY có tự được chọn sau upgrade không?
4. Region static có precedence như thế nào?
5. Vì sao phải kiểm tra principal qua OCI Audit?
6. OCI SDK retry có bật cho mọi operation không?
7. Những HTTP status/error nào có thể được retry theo SDK default condition?
8. Default max-attempts của OCI SDK khác maxAttempts của Spring Cloud Stream như thế nào?
9. Vì sao request-level retry config có thể ghi đè client-level config?
10. Async OCI SDK client có dùng default retry không?
11. maxAttempts=3 của Spring Cloud Stream gồm bao nhiêu lần retry?
12. autoStartup=true và concurrency=1 có ý nghĩa gì?
13. Vì sao Queue/Streaming starter không có listener default giống Spring Cloud Stream?
14. TxEventQ binder timeout 1000 ms là loại timeout nào?
15. Spring JMS @JmsListener mặc định tạo container nào?
16. Khi nào Spring Boot bật transacted JMS session?
17. Vì sao listener concurrency tăng có thể ảnh hưởng ordering?
18. Retry của listener khác broker redelivery ở điểm nào?
19. Làm sao xác minh business effect không bị duplicate?
20. Cần lưu những bằng chứng nào trước khi rollout upgrade?

## 16. Ghi nhớ

- Không suy ra default thay đổi chỉ từ version tăng; so sánh release notes, dependency graph, configuration metadata và runtime.
- Spring Cloud OCI 1.0.0 và 2.0.4 đều công bố FILE là authentication default; profile mặc định là DEFAULT.
- Các auth mode mới hơn như SESSION_TOKEN và WORKLOAD_IDENTITY mở rộng lựa chọn nhưng không tự thay identity đang được cấu hình.
- spring.cloud.oci.region.static ưu tiên hơn region trong auth configuration.
- OCI SDK retry và Spring Cloud Stream listener retry là hai cơ chế độc lập.
- OCI SDK retry được bật theo từng operation; không giả định mọi request đều retry.
- OCI SDK default retry strategy có max-attempts 8, exponential backoff, jitter và maximum delay 30 giây theo tài liệu SDK; xác minh Javadoc của version thực tế.
- Spring Cloud Stream consumer default có autoStartup=true, concurrency=1, maxAttempts=3, backoff 1s/10s/multiplier 2 và defaultRetryable=true.
- OCI Queue/Streaming starter expose service API beans; không có listener auto-start default trong tài liệu starter.
- TxEventQ binder dùng Spring Cloud Stream consumer defaults; binder-specific consume timeout mặc định 1000 ms.
- Spring JMS @JmsListener dùng DefaultMessageListenerContainer theo cấu hình; kiểm tra auto-startup, concurrency, receive timeout và transaction mode.
- Listener retry, broker redelivery và SDK retry có thể cộng dồn; cần idempotency và retry budget.
- Khóa identity/retry/listener settings sau khi đã kiểm chứng và lưu bằng chứng trước/sau upgrade.

## Tài liệu tham khảo

- [Spring Cloud Oracle 1.0.0 — OCI authentication defaults](https://oracle.github.io/spring-cloud-oracle/1.0.0/reference/html/appendix.html)
- [Spring Cloud Oracle 1.4.5 — Reference documentation](https://oracle.github.io/spring-cloud-oracle/latest/reference/html/index.html)
- [Spring Cloud OCI 2.0.4 — Core authentication](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI 2.0.4 — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/)
- [Spring Cloud Oracle — Release notes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/)
- [OCI Java SDK — Concepts and retry behavior](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm)
- [OCI Java SDK — DefaultRetryCondition Javadoc](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/retrier/DefaultRetryCondition.html)
- [Spring Cloud Stream 5.1 — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Error handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Oracle TxEventQ — Spring Framework integration](https://docs.oracle.com/en/database/oracle/oracle-database/26/adque/txeventq-with-springframework.html)
- [Spring Boot 4.1 — JMS application properties](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html)
- [Spring Boot 4.1 — JMS integration](https://docs.spring.io/spring-boot/4.1/reference/messaging/jms.html)
- [Spring Framework 7 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
