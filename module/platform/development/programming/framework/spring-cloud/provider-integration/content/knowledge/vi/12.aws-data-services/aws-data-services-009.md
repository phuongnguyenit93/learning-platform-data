# Tích hợp dịch vụ AWS chưa có starter bằng SDK trong adapter riêng

## 1. Bối cảnh và mục tiêu

Trong module **Spring Cloud Provider Integration**, ứng dụng Spring Boot thực hành tích hợp dịch vụ managed của AWS, Azure và Google Cloud thông qua thư viện Spring Cloud hoặc SDK tương ứng. Spring Cloud AWS (AWSpring) cung cấp starter và abstraction cho một số dịch vụ AWS phổ biến. Tuy nhiên, hệ sinh thái AWS có hàng trăm dịch vụ và không phải dịch vụ nào cũng có starter Spring Cloud phù hợp với phiên bản dự án.

Khi cần tích hợp dịch vụ chưa có starter phù hợp, ứng dụng vẫn có thể dùng **AWS SDK for Java 2.x** trực tiếp. Hãy đặt SDK trong một **adapter riêng**: tầng nghiệp vụ gọi interface do ứng dụng định nghĩa, adapter chuyển lời gọi thành request SDK, cấu hình Region/credentials/retry, rồi chuyển response hoặc lỗi về contract nội bộ. Nhờ vậy, mã nghiệp vụ không phụ thuộc package AWS SDK và không biết chi tiết AWS.

Bài dùng **Amazon EventBridge** làm ví dụ: khi reservation được xác nhận, ứng dụng phát event ReservationConfirmed lên event bus để các hệ thống khác xử lý. EventBridge được gọi qua SDK v2 EventBridgeClient. Mô hình tương tự áp dụng cho dịch vụ khác bằng service client/module SDK tương ứng, chẳng hạn SES v2, AWS KMS, Amazon Bedrock Runtime hoặc API AWS chưa có starter phù hợp.

Sau bài học, bạn có thể:

1. Quyết định khi nào dùng AWSpring starter và khi nào gọi AWS SDK trực tiếp.
2. Quản lý AWS SDK BOM, service module, client lifecycle, Region và credential provider trong Spring Boot.
3. Tách business port khỏi AWS adapter để tránh rò rỉ SDK model vào domain/application.
4. Tạo EventBridge publisher bằng PutEvents, xử lý partial failure và ánh xạ lỗi có chủ đích.
5. Cấp IAM least privilege, cấu hình endpoint local và phân biệt local/staging/production.
6. Thiết kế idempotency, outbox và retry để tránh mất hoặc nhân đôi event.
7. Kiểm thử adapter bằng mock/fake, LocalStack và AWS staging; quan sát metric và vận hành an toàn.

> **Phạm vi:** Bài minh họa tích hợp dịch vụ AWS qua AWS SDK for Java 2.x, với EventBridge là ví dụ chính. Không có một starter chung cho mọi dịch vụ AWS. Trước khi tự viết adapter, hãy kiểm tra danh sách dịch vụ và version mà AWSpring hiện tại hỗ trợ; nếu starter phù hợp đã có và đáp ứng nhu cầu, ưu tiên abstraction đó.

## 2. Chọn starter hay gọi SDK trực tiếp?

### 2.1. Không phải mọi dịch vụ đều cần adapter tự viết

Một số tích hợp thường gặp có starter/abstraction trong AWSpring, tùy phiên bản: S3, SQS, SNS, Secrets Manager, Parameter Store và một số dịch vụ khác. Danh sách cụ thể thay đổi theo release train. Với dịch vụ chưa có starter, hoặc khi cần API SDK chưa được abstraction bao phủ, dùng SDK v2 là cách tích hợp chính thức của AWS.

| Tình huống | Hướng tiếp cận | Lý do |
| --- | --- | --- |
| Starter AWSpring hỗ trợ đúng service và API cần dùng | Dùng starter/abstraction tương ứng | Ít cấu hình lặp lại, tích hợp tốt với Spring Boot |
| Có starter nhưng chưa hỗ trợ API/option cần thiết | Dùng SDK client trực tiếp trong adapter nhỏ | Giữ quyền truy cập API đầy đủ mà vẫn giữ ranh giới ứng dụng |
| Không có starter phù hợp | Dùng service module AWS SDK v2 trong adapter | SDK cung cấp API client chính thức |
| Chỉ gọi một API AWS ở một nơi | Adapter mỏng với client được inject | Tránh tạo abstraction tổng quát không cần thiết |
| Nhiều provider hoặc có khả năng thay dịch vụ | Port nghiệp vụ ổn định, adapter theo provider | Cô lập khác biệt credential, payload, retry và semantics |

Không nên tự viết một framework "AWS generic client" bọc mọi service chỉ để tránh dùng SDK trực tiếp. Mỗi AWS service có API, lỗi, quota và semantics riêng. Tạo adapter theo **use case của ứng dụng**, không theo từng method SDK một cách máy móc.

### 2.2. Kiến trúc port-and-adapter

~~~mermaid
flowchart LR
    A["Reservation application service"] --> B["ReservationEventPublisher<br/>application port"]
    B --> C["EventBridge adapter"]
    C --> D["AWS SDK v2<br/>EventBridgeClient"]
    D --> E["Amazon EventBridge"]
    F["AWS SDK configuration"] --> D
    G["IAM role / credential provider"] --> D
    H["Region / endpoint / retry"] --> D
~~~

Tách trách nhiệm:

- **Domain/application:** định nghĩa event hoặc command và interface cần thiết, ví dụ ReservationEventPublisher.
- **AWS adapter:** ánh xạ event nội bộ sang PutEventsRequestEntry, gọi SDK và diễn giải response.
- **Configuration:** tạo SDK client, Region, credential provider, endpoint override và retry strategy.
- **Infrastructure/IAM:** cấp quyền cho workload role và tạo event bus/rule/target bằng IaC.
- **Observability:** ghi log/metric ở ranh giới adapter mà không đưa credential hoặc dữ liệu nhạy cảm vào log.

Application service không cần biết event bus tên gì, SDK client dùng Region nào, credentials lấy từ đâu hoặc AWS response class có tên gì. Những chi tiết đó thuộc adapter/configuration.

## 3. Chuẩn bị AWS SDK for Java 2.x

### 3.1. Quản lý version bằng BOM

Không tự đặt version khác nhau cho từng module SDK. Dùng AWS SDK BOM để tất cả service modules cùng một release:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>software.amazon.awssdk</groupId>
            <artifactId>bom</artifactId>
            <version>${aws.sdk.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Chọn aws.sdk.version tương thích với Java runtime và dependency policy của dự án; BOM ở ví dụ là property do dự án quản lý, không phải literal cần giữ nguyên.

### 3.2. Chỉ thêm service module cần thiết

Ví dụ tích hợp EventBridge:

~~~xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>eventbridge</artifactId>
    </dependency>
</dependencies>
~~~

Một số module SDK thường gặp:

| AWS service/API | SDK v2 artifact |
| --- | --- |
| Amazon EventBridge | eventbridge |
| Amazon SES v2 | sesv2 |
| AWS Key Management Service | kms |
| Amazon Bedrock Runtime | bedrockruntime |
| Amazon S3 | s3 |
| AWS Secrets Manager | secretsmanager |
| Amazon SQS | sqs |

Artifact trên là module SDK, không có nghĩa service đó nhất thiết thiếu starter. Kiểm tra AWSpring release đang dùng trước khi quyết định tự quản lý integration. Không thêm toàn bộ SDK modules vào mọi service chỉ vì có thể sẽ dùng sau này.

### 3.3. SDK client là tài nguyên dùng chung

EventBridgeClient là client thread-safe, có thể dùng chung giữa các request trong một ứng dụng. Không tạo client mới trong mỗi controller call hoặc mỗi lần publish event. Client giữ HTTP connection pool, retry configuration và các tài nguyên nội bộ; cần đóng khi Spring context dừng.

Với Spring Boot, khai báo client bằng bean:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.eventbridge.EventBridgeClient;

@Configuration
public class EventBridgeSdkConfiguration {

    @Bean(destroyMethod = "close")
    DefaultCredentialsProvider awsCredentialsProvider() {
        return DefaultCredentialsProvider.create();
    }

    @Bean
    EventBridgeClient eventBridgeClient(
            DefaultCredentialsProvider credentialsProvider,
            @Value("${app.aws.region}") String region) {
        return EventBridgeClient.builder()
                .region(Region.of(region))
                .credentialsProvider(credentialsProvider)
                .build();
    }
}
~~~

Spring đóng EventBridgeClient khi context dừng; bean credential provider cũng được đóng theo destroyMethod. Không tự đóng client sau mỗi lần gọi. Nếu dùng async client, quản lý lifecycle tương tự và bảo đảm executor/HTTP client được đóng đúng cách.

### 3.4. Region và credential provider chain

DefaultCredentialsProvider tìm credentials theo chuỗi provider của AWS SDK, có thể lấy từ environment, Java system properties, web identity, profile, container credentials hoặc instance profile tùy môi trường và SDK version. Với workload production, ưu tiên IAM role:

- ECS: task role.
- EKS: EKS Pod Identity hoặc IRSA.
- EC2: instance profile.
- Local development: AWS IAM Identity Center/profile được tổ chức cho phép.

Không ghi access key/secret key vào source, YAML commit Git, Dockerfile hoặc log. Không tự dựng provider bằng credentials tĩnh trong production nếu workload role đã có thể cấp credentials tạm thời. Credential provider chain có thể làm mới credentials tạm thời theo cơ chế provider; ứng dụng không nên cache AWS session credentials thủ công.

Region là cấu hình rõ ràng của ứng dụng. Không suy luận Region từ endpoint, hostname hoặc vị trí người dùng cuối. EventBridge bus là tài nguyên theo Region; Region sai có thể khiến ứng dụng gọi nhầm bus hoặc gặp ResourceNotFoundException.

## 4. Cấu hình theo môi trường

### 4.1. application.yml

Đưa tên event bus và source vào cấu hình ứng dụng:

~~~yaml
app:
  aws:
    region: ap-southeast-1
    eventbridge:
      event-bus-name: rental-app-events
      source: com.rentalapp.reservations
~~~

Source là tên hệ thống phát event theo quy ước ứng dụng, không phải AWS credential. Detail type mô tả loại event, ví dụ ReservationConfirmed. Tránh nhúng tenant ID, email, token hoặc dữ liệu cá nhân vào source/detail type; dữ liệu nghiệp vụ cần thiết nằm trong detail theo schema đã quản lý.

### 4.2. Local endpoint và credentials giả

Khi test bằng LocalStack hoặc một endpoint giả lập tương thích, dùng profile riêng:

~~~yaml
# application-local.yml
app:
  aws:
    region: ap-southeast-1
    eventbridge:
      event-bus-name: rental-app-events
      source: com.rentalapp.reservations

aws:
  endpoint: http://localhost:4566
~~~

Có thể tạo client local bằng endpointOverride và credentials giả:

~~~java
import java.net.URI;

import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;

EventBridgeClient localClient = EventBridgeClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .endpointOverride(URI.create("http://localhost:4566"))
        .credentialsProvider(
                StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
        .build();
~~~

Đây chỉ là cấu hình test local. Không để endpointOverride hoặc credentials giả lọt vào profile production. Không dùng static test credentials như một cách thay thế IAM role trên AWS.

### 4.3. Đóng gói cấu hình có kiểu

Trong dự án lớn, dùng ConfigurationProperties thay vì rải Value khắp adapter:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.aws")
public record AwsIntegrationProperties(
        String region,
        EventBridge eventbridge) {

    public record EventBridge(
            String eventBusName,
            String source) {
    }
}
~~~

Đăng ký record bằng EnableConfigurationProperties(AwsIntegrationProperties.class) hoặc cơ chế scan cấu hình của dự án. Có thể bổ sung validation để phát hiện thiếu Region, bus name hoặc source khi ứng dụng khởi động. Không đưa credential vào record này; credential do AWS SDK provider chain quản lý.

## 5. Định nghĩa contract ở tầng ứng dụng

### 5.1. Event nghiệp vụ không phụ thuộc AWS

Ví dụ event được phát khi đặt chỗ xác nhận:

~~~java
import java.time.Instant;

public record ReservationConfirmed(
        String eventId,
        String tenantId,
        String reservationId,
        String propertyId,
        Instant occurredAt) {
}
~~~

Event ID cần ổn định theo một lần phát sinh nghiệp vụ. Nếu publisher retry hoặc outbox gửi lại cùng event, consumer có thể nhận lại cùng ID để thực hiện idempotency.

### 5.2. Application port

~~~java
public interface ReservationEventPublisher {
    void publish(ReservationConfirmed event);
}
~~~

Application service chỉ phụ thuộc port:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReservationApplicationService {
    private final ReservationRepository reservations;
    private final ReservationEventPublisher eventPublisher;

    public ReservationApplicationService(
            ReservationRepository reservations,
            ReservationEventPublisher eventPublisher) {
        this.reservations = reservations;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public void confirm(String reservationId) {
        Reservation reservation = reservations.confirm(reservationId);

        eventPublisher.publish(new ReservationConfirmed(
                reservation.eventId(),
                reservation.tenantId(),
                reservation.id(),
                reservation.propertyId(),
                reservation.confirmedAt()));
    }
}
~~~

Đoạn trên chỉ minh họa dependency direction. **Không nên mặc định publish EventBridge trực tiếp bên trong transaction database** như code này trong production. Nếu database commit nhưng publish thất bại, hoặc publish thành công rồi transaction rollback, hai hệ thống sẽ lệch trạng thái. Mục 9 trình bày transactional outbox để xử lý dual-write. Có thể dùng port này ở worker đọc outbox sau khi database transaction đã commit.

### 5.3. Vì sao không trả AWS SDK model từ port?

Không nên để application port trả PutEventsResponse, nhận PutEventsRequestEntry hoặc ném EventBridgeException. Khi đó domain/application phụ thuộc SDK và mọi provider khác phải giả lập các kiểu dữ liệu AWS.

Port nên dùng kiểu nghiệp vụ của ứng dụng. Adapter chịu trách nhiệm:

- Serialize event sang JSON.
- Gán EventBridge source, detailType, eventBusName, time.
- Gọi SDK.
- Đọc eventId, errorCode, errorMessage, failedEntryCount.
- Chuyển lỗi sang exception/result nội bộ có ý nghĩa với use case.

## 6. Viết EventBridge adapter bằng SDK v2

### 6.1. Serialize detail và tạo request

EventBridge PutEvents nhận một danh sách entry. Mỗi entry có thể chứa event bus name, source, detail type, thời điểm và detail dạng JSON string.

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import software.amazon.awssdk.services.eventbridge.EventBridgeClient;
import software.amazon.awssdk.services.eventbridge.model.PutEventsRequest;
import software.amazon.awssdk.services.eventbridge.model.PutEventsRequestEntry;
import software.amazon.awssdk.services.eventbridge.model.PutEventsResponse;
import software.amazon.awssdk.services.eventbridge.model.PutEventsResultEntry;
import software.amazon.awssdk.services.eventbridge.model.EventBridgeException;
import software.amazon.awssdk.core.exception.SdkClientException;

@Component
public class EventBridgeReservationEventPublisher
        implements ReservationEventPublisher {

    private final EventBridgeClient client;
    private final ObjectMapper objectMapper;
    private final String eventBusName;
    private final String source;

    public EventBridgeReservationEventPublisher(
            EventBridgeClient client,
            ObjectMapper objectMapper,
            @Value("${app.aws.eventbridge.event-bus-name}") String eventBusName,
            @Value("${app.aws.eventbridge.source}") String source) {
        this.client = client;
        this.objectMapper = objectMapper;
        this.eventBusName = eventBusName;
        this.source = source;
    }

    @Override
    public void publish(ReservationConfirmed event) {
        final String detail;
        try {
            detail = objectMapper.writeValueAsString(event);
        } catch (JsonProcessingException ex) {
            throw new IllegalArgumentException(
                    "Cannot serialize ReservationConfirmed event", ex);
        }

        PutEventsRequestEntry entry = PutEventsRequestEntry.builder()
                .eventBusName(eventBusName)
                .source(source)
                .detailType("ReservationConfirmed")
                .time(event.occurredAt())
                .detail(detail)
                .build();

        final PutEventsResponse response;
        try {
            response = client.putEvents(
                    PutEventsRequest.builder()
                            .entries(entry)
                            .build());
        } catch (EventBridgeException ex) {
            String code = ex.awsErrorDetails() == null
                    ? "EVENTBRIDGE_SERVICE_ERROR"
                    : ex.awsErrorDetails().errorCode();
            throw new EventPublicationException(event.eventId(), code, ex);
        } catch (SdkClientException ex) {
            throw new EventPublicationException(
                    event.eventId(), "AWS_SDK_CLIENT_ERROR", ex);
        }

        if (response.failedEntryCount() != null
                && response.failedEntryCount() > 0) {
            PutEventsResultEntry result = response.entries().get(0);
            throw new EventPublicationException(
                    event.eventId(),
                    result.errorCode());
        }
    }
}
~~~

Với request một entry, nếu failedEntryCount lớn hơn 0, entry result tương ứng chứa lỗi. Exception nội bộ có thể lưu event ID và mã lỗi để retry worker hoặc đưa vào trạng thái cần xử lý. Không ghi toàn bộ JSON detail hoặc token vào exception/log.

### 6.2. Exception nội bộ

~~~java
public class EventPublicationException extends RuntimeException {
    private final String eventId;
    private final String errorCode;

    public EventPublicationException(String eventId, String errorCode) {
        super("Event publication failed: " + errorCode + " for " + eventId);
        this.eventId = eventId;
        this.errorCode = errorCode;
    }

    public EventPublicationException(
            String eventId, String errorCode, Throwable cause) {
        super("Event publication failed: " + errorCode + " for " + eventId, cause);
        this.eventId = eventId;
        this.errorCode = errorCode;
    }

    public String eventId() {
        return eventId;
    }

    public String errorCode() {
        return errorCode;
    }
}
~~~

Trong ví dụ, message từ AWS không được đưa thẳng vào response HTTP cho client. Nếu cần giữ thông tin chẩn đoán, ghi log đã lọc ở adapter và liên kết bằng correlation ID. Error message có thể thay đổi theo service/version; code nghiệp vụ không nên parse chuỗi message để quyết định flow.

### 6.3. Đừng coi HTTP 200 là mọi entry đã thành công

Một PutEvents request có thể trả HTTP 200 nhưng một số entry thất bại. Phải đọc FailedEntryCount và từng PutEventsResultEntry:

- EventId có giá trị: entry đã được EventBridge chấp nhận.
- ErrorCode/ErrorMessage có giá trị: entry đó thất bại.
- Khi gửi nhiều entry, response entries giữ thứ tự tương ứng với request entries.
- SDK retry strategy xử lý một số lỗi HTTP/retryable ở request level; partial failures nằm trong response thành công cần logic ứng dụng xử lý riêng.

Nếu gửi nhiều entry trong một batch, **chỉ retry những entry thất bại có mã lỗi retryable**, không gửi lại cả batch gồm entry đã được chấp nhận. Nếu không thể xác định chắc request đã được chấp nhận do timeout/mất response, downstream vẫn cần idempotency vì retry có thể tạo duplicate event.

### 6.4. Giới hạn request và event size

EventBridge PutEvents nhận tối đa **10 entries trong một request**. Mỗi event có giới hạn kích thước **256 KB**; kích thước được tính trên các trường event theo quy tắc dịch vụ, không chỉ riêng detail. Hãy kiểm soát payload trước khi gửi:

- Chỉ đưa dữ liệu consumer cần để xử lý.
- Không nhúng file, ảnh hoặc document lớn; lưu object ở S3 rồi gửi object key và metadata.
- Không gửi secret, access token hoặc thông tin thanh toán nhạy cảm.
- Phiên bản hóa schema event và giữ tương thích ngược cho consumer.
- Với batch, tính giới hạn tổng request và xử lý từng entry result.

## 7. Retry, idempotency và lỗi phân tán

### 7.1. Phân loại lỗi

| Loại lỗi | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Lỗi cấu hình/quyền | AccessDeniedException, bus/Region sai | Không retry vô hạn; sửa IAM, resource policy hoặc cấu hình |
| Lỗi payload | JSON không hợp lệ, event vượt giới hạn, source/detail type không hợp lệ | Sửa schema/payload; retry nguyên request không giúp |
| Throttling | ThrottlingException | Backoff + jitter, giới hạn attempts và kiểm soát tốc độ |
| Lỗi nội bộ dịch vụ | InternalFailure | Retry có giới hạn theo chính sách |
| Lỗi mạng/timeout | SdkClientException, socket timeout | Kết quả có thể không rõ; retry có kiểm soát và dựa trên event ID idempotent |
| Partial failure | HTTP 200 nhưng một số entry có ErrorCode | Chỉ retry các entry thất bại có thể retry |

Không gom tất cả lỗi thành "AWS unavailable". Lỗi permission và validation thường cần can thiệp cấu hình; throttling và lỗi tạm thời có thể retry. Khi SDK client đã có retry strategy, tránh thêm vòng retry service không giới hạn khiến số request bị nhân lên.

### 7.2. Backoff có jitter và giới hạn thời gian

Với lỗi retryable, dùng exponential backoff có jitter, ví dụ:

\[
delay_k \sim U(0,\min(delay_{max},baseDelay \times 2^k))
\]

Đặt giới hạn attempts và tổng deadline theo SLO. Nếu request đã qua deadline HTTP, không giữ request thread chờ nhiều lần retry; chuyển sang worker/queue/outbox để xử lý bất đồng bộ. SDK retry strategy có thể cấu hình ở client level; ứng dụng chỉ thêm retry riêng khi có lý do rõ ràng, nhất là xử lý partial failure trong response HTTP 200.

### 7.3. Idempotency ở consumer

EventBridge không phải cơ chế exactly-once delivery end-to-end. Consumer cần chấp nhận duplicate delivery và thiết kế idempotent:

1. Mỗi event có eventId ổn định được tạo từ nghiệp vụ/outbox.
2. Consumer ghi nhận event ID đã xử lý trong bảng inbox/deduplication có unique key.
3. Trong cùng transaction với cập nhật business state, consumer đánh dấu event ID đã xử lý.
4. Nếu nhận lại cùng event ID, bỏ qua side effect đã hoàn thành và trả kết quả phù hợp.
5. Với side effect tới hệ thống ngoài, truyền idempotency key nếu API đích hỗ trợ hoặc dùng workflow/compensation.

Không dùng EventId do EventBridge trả về làm business event ID duy nhất nếu ứng dụng cần chống duplicate giữa nhiều lần publish. EventBridge event ID đại diện cho lần EventBridge chấp nhận event; retry sau timeout có thể tạo event ID mới.

### 7.4. Bus tồn tại và response thành công

Cấu hình sai event bus là lỗi cần kiểm tra ở deployment. Với một số tình huống gửi tới event bus không tồn tại, PutEvents có thể trả response thành công mà event không được ingest như mong đợi. Vì vậy:

- Tạo event bus/rule/target bằng IaC trước khi deploy ứng dụng.
- Xác nhận bus name, account và Region trong pipeline hoặc smoke test.
- Có thể dùng DescribeEventBus trong health/deployment validation nếu role được cấp quyền cần thiết.
- Kiểm tra metric ingestion và target invocation sau khi phát event thử nghiệm.

Không dựa riêng vào HTTP 200 hoặc FailedEntryCount=0 để kết luận cấu hình toàn tuyến đã đúng.

## 8. Transactional outbox: tránh dual-write

### 8.1. Vì sao gọi EventBridge trong database transaction có rủi ro?

Giả sử reservation lưu trong RDS và event phát sang EventBridge:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant DB as RDS
    participant EB as EventBridge
    App->>DB: UPDATE reservation = CONFIRMED
    App->>EB: PutEvents ReservationConfirmed
    EB-->>App: Accepted
    DB-->>App: COMMIT thất bại
    Note over DB,EB: Event đã phát nhưng reservation rollback
~~~

Chiều ngược lại cũng có thể xảy ra: DB commit thành công, ứng dụng chết trước khi gọi EventBridge. Khi đó reservation đã xác nhận nhưng event không được phát. Không có một transaction ACID mặc định bao trùm RDS và EventBridge.

### 8.2. Ghi outbox cùng transaction

Tạo bảng outbox trong cùng database với reservation:

~~~sql
CREATE TABLE outbox_event (
    event_id        VARCHAR(100) PRIMARY KEY,
    aggregate_id    VARCHAR(100) NOT NULL,
    event_type      VARCHAR(150) NOT NULL,
    payload         JSONB NOT NULL,
    occurred_at     TIMESTAMPTZ NOT NULL,
    published_at    TIMESTAMPTZ NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      VARCHAR(500) NULL
);

CREATE INDEX idx_outbox_pending
    ON outbox_event (occurred_at)
    WHERE published_at IS NULL;
~~~

Trong cùng @Transactional method:

~~~java
@Transactional
public void confirm(String reservationId) {
    Reservation reservation = reservations.confirm(reservationId);

    ReservationConfirmed event = new ReservationConfirmed(
            reservation.eventId(),
            reservation.tenantId(),
            reservation.id(),
            reservation.propertyId(),
            reservation.confirmedAt());

    final String payload;
    try {
        payload = objectMapper.writeValueAsString(event);
    } catch (JsonProcessingException ex) {
        throw new IllegalArgumentException("Cannot serialize outbox event", ex);
    }

    outboxRepository.insert(
            event.eventId(),
            reservation.id(),
            "ReservationConfirmed",
            payload,
            event.occurredAt());
}
~~~

Nếu transaction commit, cả reservation và outbox record cùng tồn tại. Nếu rollback, cả hai cùng rollback. Trong ví dụ PostgreSQL, repository cần bind chuỗi payload vào cột JSONB bằng kiểu PGobject hoặc CAST(? AS jsonb), không lưu payload như VARCHAR thuần. Worker độc lập đọc outbox và gửi event qua ReservationEventPublisher.

### 8.3. Worker phát outbox

Luồng cơ bản:

~~~text
SELECT pending outbox rows
  -> publish EventBridge
  -> nếu entry được chấp nhận: đánh dấu published_at
  -> nếu retryable: tăng attempts, ghi last_error, lên lịch retry
  -> nếu permanent failure: đưa trạng thái vào dead-letter/review queue
~~~

Khi nhiều worker chạy đồng thời, claim row bằng cơ chế lock phù hợp, ví dụ SELECT ... FOR UPDATE SKIP LOCKED trong transaction ngắn, hoặc dùng cột claimed_by/lease_until. Không giữ transaction/row lock trong lúc chờ gọi AWS lâu; claim record, commit, publish, rồi cập nhật trạng thái riêng với lease và cơ chế recovery khi worker chết.

Có cửa sổ crash sau khi EventBridge nhận event nhưng trước khi outbox được đánh dấu published. Worker có thể gửi lại event. Vì vậy outbox bảo đảm **không mất ý định phát event sau DB commit**, nhưng delivery vẫn có thể at-least-once; consumer cần deduplication theo event ID.

### 8.4. Không đánh dấu published khi partial failure

Nếu một batch có nhiều entry, phải map từng response result về event ID tương ứng:

- Entry có EventId và không có error: đánh dấu accepted/published.
- Entry có lỗi retryable: giữ pending và lên lịch retry.
- Entry có lỗi permanent: chuyển dead-letter/review, cảnh báo và giữ payload phục vụ điều tra.
- Timeout không rõ kết quả: retry cùng event ID, consumer dedupe.

Không đánh dấu toàn bộ batch published chỉ vì PutEvents trả HTTP 200.

## 9. IAM least privilege và tài nguyên EventBridge

### 9.1. Quyền gửi event

Role của producer thường cần events:PutEvents trên đúng event bus ARN:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "events:PutEvents"
      ],
      "Resource": "arn:aws:events:ap-southeast-1:123456789012:event-bus/rental-app-events"
    }
  ]
}
~~~

Nếu adapter/health check cần DescribeEventBus, cấp riêng action đó theo resource support và nhu cầu thực tế. Ứng dụng không cần events:PutRule, events:PutTargets, events:CreateEventBus hoặc quyền quản trị EventBridge khi bus/rule/target đã được provision bằng IaC.

### 9.2. Cross-account event bus

Khi gửi event sang account khác:

- Producer role cần quyền events:PutEvents tới bus đích theo IAM policy.
- Event bus đích cần resource-based policy cho phép principal/account gửi event.
- Kiểm tra Region, account, bus ARN và yêu cầu organization policy/SCP.
- Không cấp events:* toàn tài khoản để giải quyết lỗi cross-account.

Tách role producer khỏi role triển khai hạ tầng. Ứng dụng runtime chỉ gửi event; pipeline/IaC chịu trách nhiệm tạo bus, rule, target, archive, replay và DLQ.

### 9.3. Quyền của target khác quyền của producer

Producer gửi event vào bus; EventBridge rule match event và gọi target như Lambda, SQS hoặc Step Functions. Role/resource policy cho EventBridge invoke target là cấu hình riêng. events:PutEvents thành công chỉ chứng minh EventBridge chấp nhận entry theo API, không chứng minh rule match hoặc target đã xử lý thành công.

## 10. SDK retry, timeout và client configuration

### 10.1. Dùng retry mặc định trước khi tùy chỉnh

AWS SDK v2 có retry strategy theo mode. Cấu hình client mặc định thường là điểm khởi đầu phù hợp; quan sát lỗi/throttling trước khi thay đổi. Nếu cần tùy chỉnh, cấu hình trên client:

~~~java
EventBridgeClient client = EventBridgeClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .overrideConfiguration(config -> config
                .apiCallAttemptTimeout(java.time.Duration.ofSeconds(2))
                .apiCallTimeout(java.time.Duration.ofSeconds(5)))
        .build();
~~~

Đoạn này minh họa timeout ở SDK level; cần chọn theo latency/SLO thực tế. apiCallAttemptTimeout giới hạn một lần thử, còn apiCallTimeout giới hạn toàn bộ API call gồm retry. Nếu toàn bộ call timeout, kết quả phía server có thể chưa rõ; idempotency downstream vẫn cần thiết.

Không chồng nhiều retry policy ở HTTP client, SDK và application mà không tính tổng số attempts. Ví dụ SDK có 3 attempts và service layer cũng thử 3 lần có thể tạo tới 9 request. Partial failure response HTTP 200 cần được xử lý riêng vì SDK không thể biết entry nào ứng dụng muốn retry.

### 10.2. Khi nào dùng AsyncClient?

EventBridgeAsyncClient trả CompletableFuture, phù hợp khi ứng dụng có luồng non-blocking và quản lý backpressure rõ. Không chuyển sang async chỉ để "nhanh hơn" nếu controller/repository vẫn block. Nếu dùng async:

- Quản lý executor/HTTP client và shutdown.
- Xử lý exception trong completion stage.
- Giới hạn số future đang in-flight.
- Propagate correlation/tracing context đúng cách.
- Đảm bảo outbox worker chỉ đánh dấu accepted sau khi future hoàn tất và response entry không có lỗi.

Với ứng dụng Spring MVC/JDBC blocking, EventBridgeClient đồng bộ thường đơn giản và dễ quản lý. Chọn một mô hình nhất quán theo stack của ứng dụng.

## 11. Kiểm thử adapter và tích hợp AWS

### 11.1. Unit test bằng mock SDK client

Mock EventBridgeClient để xác minh adapter ánh xạ event đúng và xử lý partial failure:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import software.amazon.awssdk.services.eventbridge.EventBridgeClient;
import software.amazon.awssdk.services.eventbridge.model.PutEventsRequest;
import software.amazon.awssdk.services.eventbridge.model.PutEventsResponse;
import software.amazon.awssdk.services.eventbridge.model.PutEventsResultEntry;

class EventBridgeReservationEventPublisherTest {

    @Test
    void publishesReservationConfirmed() {
        EventBridgeClient client = org.mockito.Mockito.mock(
                EventBridgeClient.class);
        when(client.putEvents(any(PutEventsRequest.class)))
                .thenReturn(PutEventsResponse.builder()
                        .failedEntryCount(0)
                        .entries(PutEventsResultEntry.builder()
                                .eventId("aws-event-1")
                                .build())
                        .build());

        var publisher = new EventBridgeReservationEventPublisher(
                client, new ObjectMapper(),
                "rental-app-events", "com.rentalapp.reservations");

        publisher.publish(new ReservationConfirmed(
                "evt-1", "tenant-a", "res-1", "house-1",
                java.time.Instant.parse("2026-11-24T10:00:00Z")));

        ArgumentCaptor<PutEventsRequest> captor =
                ArgumentCaptor.forClass(PutEventsRequest.class);
        verify(client).putEvents(captor.capture());

        var entry = captor.getValue().entries().get(0);
        org.junit.jupiter.api.Assertions.assertEquals(
                "rental-app-events", entry.eventBusName());
        org.junit.jupiter.api.Assertions.assertEquals(
                "ReservationConfirmed", entry.detailType());
        org.junit.jupiter.api.Assertions.assertTrue(
                entry.detail().contains("res-1"));
    }

    @Test
    void failsWhenEntryHasPartialFailure() {
        EventBridgeClient client = org.mockito.Mockito.mock(
                EventBridgeClient.class);
        when(client.putEvents(any(PutEventsRequest.class)))
                .thenReturn(PutEventsResponse.builder()
                        .failedEntryCount(1)
                        .entries(PutEventsResultEntry.builder()
                                .errorCode("ThrottlingException")
                                .errorMessage("Rate exceeded")
                                .build())
                        .build());

        var publisher = new EventBridgeReservationEventPublisher(
                client, new ObjectMapper(),
                "rental-app-events", "com.rentalapp.reservations");

        assertThrows(EventPublicationException.class, () ->
                publisher.publish(new ReservationConfirmed(
                        "evt-2", "tenant-a", "res-2", "house-1",
                        java.time.Instant.now())));
    }
}
~~~

Test đầu xác nhận request mapping; test sau chứng minh HTTP-level success không bị hiểu nhầm là entry-level success. Trong project thật, thêm assertion cho eventId/errorCode trong exception, JSON schema và các trường bắt buộc. Đoạn test là mẫu cần gắn với dependency/test setup thực tế; chưa có kết quả chạy test trong bài này.

### 11.2. LocalStack cho vòng lặp phát triển local

LocalStack hỗ trợ nhiều API AWS, trong đó có EventBridge. Có thể dùng Testcontainers/Compose để khởi động LocalStack, tạo event bus và gọi SDK với endpointOverride. Ví dụ tạo bus bằng AWS CLI:

~~~bash
aws --endpoint-url http://localhost:4566 events create-event-bus \
  --name rental-app-events \
  --region ap-southeast-1
~~~

LocalStack giúp kiểm tra wiring, serialization và API request trong môi trường local. Không giả định mọi IAM authorization, throttling, cross-account policy, archive/replay, target retry hoặc metric của AWS được mô phỏng đầy đủ.

### 11.3. AWS staging để kiểm tra semantics thật

Staging nên xác minh:

1. Workload role thực sự có events:PutEvents đúng event bus ARN.
2. Event bus tồn tại trong account/Region cấu hình.
3. PutEvents trả accepted event ID và event xuất hiện trong rule/target.
4. Event pattern match đúng source/detail-type/version.
5. Target permission, retry policy và DLQ hoạt động như dự kiến.
6. Throttling/partial failure được xử lý có giới hạn.
7. Cross-account resource policy đúng nếu dùng bus account khác.
8. Consumer dedupe khi gửi lại cùng event ID.

Không test throttling bằng cách tạo tải vô hạn. Đặt ngân sách request/chi phí, giới hạn concurrency và có cách dừng bài test.

## 12. Quan sát và xử lý sự cố

### 12.1. Log có cấu trúc

Log nên chứa thông tin đủ để điều tra:

- eventId nghiệp vụ, correlation ID và reservation ID (nếu được phép).
- Event bus name, source, detail type và AWS Region.
- SDK operation, latency, retry attempts và mã lỗi.
- EventId do EventBridge trả về sau khi entry được chấp nhận.
- Kết quả outbox: pending, published, retry scheduled hoặc dead-letter.

Không log token, AWS credentials, full payload chứa dữ liệu cá nhân, payment details hoặc secret. Dùng event ID để truy vết xuyên producer/consumer thay vì in toàn bộ detail.

### 12.2. CloudWatch metrics

Theo dõi metric EventBridge trong namespace AWS/Events, ví dụ:

| Metric | Ý nghĩa |
| --- | --- |
| PutEventsApproximateCallCount | Lượng PutEvents request |
| PutEventsApproximateFailedCount | Entry thất bại gần đúng |
| PutEventsApproximateThrottledCount | Entry/request bị throttled gần đúng |
| MatchedEvents | Event match rule |
| Invocations | Số lần EventBridge gọi target |
| FailedInvocations | Target invocation thất bại |

Tên metric/khả năng dimension phụ thuộc loại bus và tính năng; xác minh trong CloudWatch console cho tài nguyên đang dùng. Theo dõi thêm outbox backlog/oldest age, retry count, DLQ depth và consumer processing latency. Nếu PutEvents accepted nhưng MatchedEvents không tăng, kiểm tra event pattern, bus, source và detail type. Nếu Invocations tăng nhưng FailedInvocations tăng, kiểm tra target permission, target health và retry/DLQ.

### 12.3. Bảng chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| AccessDeniedException | IAM policy hoặc bus resource policy thiếu quyền | Kiểm tra principal, action, ARN, SCP và cross-account policy |
| ResourceNotFoundException | Bus/Region/account sai | So sánh cấu hình với IaC; kiểm tra bus tồn tại |
| PutEvents 200 nhưng không thấy event | Bus sai/tồn tại không đúng, rule không match hoặc metric/target trễ | Kiểm tra event bus, source, detail type, event pattern và ingestion metrics |
| FailedEntryCount > 0 | Partial failure trong batch | Đọc từng result entry, chỉ retry entry lỗi retryable |
| ThrottlingException | Tốc độ gửi vượt giới hạn | Backoff + jitter, giảm concurrency và xem quota |
| Event được nhận nhưng target lỗi | Target permission, timeout, service unavailable | Xem FailedInvocations, retry policy, DLQ và target logs |
| Consumer xử lý trùng | At-least-once delivery hoặc producer retry sau timeout | Deduplicate bằng business event ID/inbox |
| Outbox backlog tăng | Publisher lỗi, worker thiếu capacity hoặc event bus unavailable | Xem oldest age, lỗi theo loại, worker concurrency và DLQ |

## 13. Mở rộng adapter cho dịch vụ AWS khác

Mỗi service SDK có model, retry và semantics riêng; vẫn có thể giữ cùng nguyên tắc:

| Use case | Adapter/SDK | Port nghiệp vụ gợi ý |
| --- | --- | --- |
| Gửi email giao dịch | SES v2 (sesv2) | TransactionalEmailSender |
| Mã hóa/giải mã envelope key | KMS (kms) | DataKeyProvider |
| Gọi model foundation | Bedrock Runtime (bedrockruntime) | TextGenerationGateway |
| Upload/download object | S3 (s3) | DocumentStorage |
| Publish domain event | EventBridge (eventbridge) | DomainEventPublisher |

Không nên tạo interface chung như AwsService.call(Map<String,Object>). Port nên diễn tả hành vi nghiệp vụ, ví dụ sendReservationConfirmation, encryptDataKey, storeDocument, không lộ API shape của provider.

Nếu cần chuyển provider, adapter Azure/Google triển khai cùng port nhưng semantics có thể khác: retry, consistency, authentication, quota, message ordering, delivery guarantees và payload limits. Hãy định nghĩa rõ contract mà ứng dụng yêu cầu, rồi kiểm tra mỗi provider có đáp ứng hay cần workflow bổ sung.

## 14. Checklist production

1. **Service support:** đã kiểm tra AWSpring starter có hỗ trợ đúng service/API/version chưa; chỉ dùng SDK trực tiếp khi có lý do.
2. **Dependency:** AWS SDK BOM thống nhất version; chỉ thêm service modules cần thiết.
3. **Client lifecycle:** client được tạo một lần qua Spring bean, thread-safe và được đóng khi context dừng.
4. **Identity:** production dùng workload IAM role/credential provider; không hardcode access key.
5. **Region/endpoint:** Region và tài nguyên được cấu hình theo môi trường; endpoint override chỉ ở local/test.
6. **Adapter boundary:** domain/application không import AWS SDK request/response/exception.
7. **Payload:** schema có version, event ID ổn định, không gửi secret/PII không cần thiết và nằm trong size limit.
8. **Failure handling:** đọc partial failure, retry có jitter/deadline, không retry lỗi permission/validation vô hạn.
9. **Delivery:** dùng outbox khi database commit và publish event cần nhất quán; consumer idempotent.
10. **IAM:** quyền runtime chỉ cho phép action/resource cần thiết; bus/rule/target được provision bằng IaC.
11. **Testing:** unit test adapter, local emulator cho feedback nhanh, staging cho IAM/network/target semantics thật.
12. **Operations:** dashboard CloudWatch, log an toàn, backlog/age/DLQ alert và quy trình replay/recovery.

## 15. Bài tập tự luyện

1. Kiểm tra một service AWS bạn cần dùng có AWSpring starter phù hợp không. Nếu không, chọn SDK module và giải thích vì sao cần adapter riêng.
2. Viết port DomainEventPublisher và adapter EventBridgeDomainEventPublisher; domain không được import bất kỳ class AWS SDK nào.
3. Cấu hình AWS SDK BOM và EventBridgeClient dùng Region từ configuration, credentials từ workload role và lifecycle do Spring quản lý.
4. Tạo event ReservationConfirmed có event ID ổn định, serialize thành JSON và gửi bằng PutEvents.
5. Mô phỏng response HTTP 200 có FailedEntryCount=1; chỉ ra entry lỗi và thiết kế retry có giới hạn.
6. Tạo IAM policy chỉ có events:PutEvents trên một event bus; kiểm tra lỗi khi gọi bus khác hoặc Region khác.
7. Dùng LocalStack tạo event bus, publish event và xác minh rule/target trong môi trường local.
8. Thiết kế outbox worker để không mất event sau DB commit và xử lý crash sau khi EventBridge nhận event nhưng trước khi đánh dấu published.
9. Thiết kế inbox/deduplication ở consumer để cùng event ID không tạo side effect hai lần.
10. So sánh EventBridge adapter với SES v2 hoặc KMS adapter; xác định phần dùng chung ở cấu hình client và phần riêng ở port/error/payload semantics.

**Tiêu chí hoàn thành:** người học có thể tích hợp một dịch vụ AWS chưa có starter phù hợp bằng SDK v2 trong adapter riêng, quản lý client/Region/credentials an toàn, xử lý response partial failure và retry, bảo vệ tính nhất quán bằng outbox/idempotency, và kiểm thử được adapter ở local lẫn AWS staging.

## Tài liệu tham khảo

- [Spring Cloud AWS — Reference documentation](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html): danh sách module, starter và cấu hình theo phiên bản.
- [AWS SDK for Java 2.x — Developer guide](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/home.html): service clients, credentials, Region và retry.
- [AWS SDK for Java 2.x — Set the AWS Region](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/region-selection.html): cấu hình Region.
- [AWS SDK for Java 2.x — Credentials providers](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html): default provider chain và IAM role.
- [AWS SDK for Java 2.x — Retry strategy](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/retry-strategy.html): retry mode và attempts.
- [Amazon EventBridge — PutEvents API](https://docs.aws.amazon.com/eventbridge/latest/APIReference/API_PutEvents.html): request/response, entry errors và giới hạn.
- [Amazon EventBridge — Permissions](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-event-bus-perms.html): event bus resource policy và cross-account.
- [Amazon EventBridge — Monitoring](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-monitoring.html): CloudWatch metrics.
- [Amazon EventBridge — Quotas](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-quota.html): quota, event size và PutEvents limits.
- [AWS Prescriptive Guidance — Transactional outbox pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html): dual-write, outbox và duplicate delivery.
