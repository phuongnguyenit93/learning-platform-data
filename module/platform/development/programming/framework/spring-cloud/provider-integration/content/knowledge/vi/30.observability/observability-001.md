# Health indicator, readiness và liveness cho phụ thuộc đám mây

## 1. Bối cảnh và mục tiêu

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, chúng ta thực hành tích hợp Spring Boot với các dịch vụ managed của **AWS, Azure và Google Cloud** qua thư viện Spring Cloud và SDK tương ứng. Ngoài việc cấu hình danh tính, quyền truy cập, storage, messaging và bảo vệ secret, một ứng dụng production còn cần cho nền tảng biết **nó có đang chạy được hay có thể nhận traffic hay không**.

Hãy xét một API Spring Boot lưu tài liệu vào object storage và gửi job sang message queue. Ứng dụng có thể vẫn chạy khi dịch vụ cloud bị gián đoạn, nhưng một số request sẽ không thực hiện được. Nếu nền tảng chỉ kiểm tra process còn sống, nó vẫn chuyển traffic vào một instance chưa thể phục vụ. Ngược lại, nếu cứ thấy một lần gọi cloud thất bại là khởi động lại process, cả cụm có thể cùng restart và làm sự cố nghiêm trọng hơn.

Spring Boot Actuator cung cấp **HealthIndicator**, **health groups**, trạng thái **liveness/readiness** và endpoint để nền tảng như Kubernetes kiểm tra. Bài học tập trung vào cách phân loại phụ thuộc cloud đúng mục đích, triển khai health indicator có timeout và lựa chọn điều kiện readiness phù hợp.

Sau bài này, bạn có thể:

- Phân biệt **health**, **liveness**, **readiness** và **startup probe**.
- Cấu hình Spring Boot Actuator để cung cấp endpoint kiểm tra cho Kubernetes.
- Viết HealthIndicator kiểm tra một tài nguyên cloud quan trọng bằng thao tác nhẹ và có giới hạn thời gian.
- Chọn phụ thuộc AWS, Azure hoặc Google Cloud nào nên đưa vào readiness.
- Tránh restart storm, health check gây tải và rò rỉ thông tin nhạy cảm.
- Kiểm thử health endpoint, mô phỏng dependency lỗi và xác minh hành vi của Kubernetes.

## 2. Bốn khái niệm cần phân biệt

Các từ “healthy”, “live” và “ready” thường bị dùng thay thế cho nhau, nhưng chúng dẫn đến hành động vận hành khác nhau.

| Khái niệm | Câu hỏi | Khi thất bại, nền tảng nên làm gì? |
|---|---|---|
| **Health** | Các thành phần mà ứng dụng báo cáo đang ở trạng thái nào? | Hiển thị trạng thái, hỗ trợ giám sát và chẩn đoán |
| **Liveness** | Process còn ở trạng thái có thể tiếp tục chạy hoặc tự phục hồi không? | Khởi động lại instance nếu trạng thái hỏng không thể tự phục hồi |
| **Readiness** | Instance hiện có thể nhận và xử lý traffic không? | Tạm ngừng gửi traffic đến instance |
| **Startup** | Ứng dụng đã hoàn tất giai đoạn khởi động cần thiết chưa? | Chưa chạy liveness/readiness cho đến khi startup thành công; nếu thất bại quá ngưỡng thì restart |

Ví dụ:

- Ứng dụng bị deadlock trong một luồng quan trọng và không thể xử lý request: **liveness có thể DOWN**.
- Ứng dụng vừa khởi động, đang nạp cấu hình hoặc warm cache: **readiness chưa ACCEPTING_TRAFFIC**.
- Azure Blob Storage đang gặp sự cố nhưng JVM, thread pool và Spring context vẫn hoạt động: **liveness vẫn UP**; readiness phụ thuộc việc Blob có phải dependency bắt buộc của mọi request hay không.
- Một cache không khả dụng nhưng ứng dụng có fallback sang database: cache có thể **DOWN trong health tổng thể**, nhưng không nhất thiết làm readiness DOWN.

**Health không tự quyết định hành động của Kubernetes.** Chính cấu hình probe sẽ ánh xạ kết quả HTTP sang hành động restart container hoặc ngừng gửi traffic.

## 3. Liveness: kiểm tra khả năng sống của chính ứng dụng

Liveness trả lời câu hỏi: **instance có thể tiếp tục chạy không?** Đây là tín hiệu để Kubernetes quyết định có cần restart container.

Những tình huống có thể khiến liveness thất bại:

- Ứng dụng rơi vào trạng thái nội bộ không thể phục hồi, ví dụ một thành phần thiết yếu bị hỏng vĩnh viễn.
- Deadlock hoặc lỗi nghiêm trọng khiến process không còn tiến triển.
- Trạng thái nội bộ đã được ứng dụng xác định rõ là BROKEN và không có cách phục hồi tại chỗ.

Những tình huống không nên tự động làm liveness thất bại:

- AWS S3, Azure Blob Storage, Google Cloud Storage hoặc message broker tạm thời không truy cập được.
- DNS, mạng ngoài cụm hoặc một API bên thứ ba gặp lỗi.
- Database dùng chung bị gián đoạn trong khi process vẫn hoạt động bình thường.
- Một request riêng lẻ timeout hoặc circuit breaker mở.

Nếu phụ thuộc cloud bị lỗi mà liveness của mọi instance cùng DOWN, Kubernetes có thể restart toàn bộ workload. Các instance mới lại gọi tới cùng dependency đang lỗi, tạo thêm tải và kéo dài sự cố. Đây là **restart storm/cascading failure**.

Spring Boot mô tả liveness dựa trên trạng thái nội bộ của ứng dụng. Khi ApplicationContext đã khởi tạo thành công, Spring Boot mặc định coi ứng dụng đã live; thành phần ứng dụng có thể cập nhật LivenessState khi phát hiện lỗi nội bộ không thể phục hồi.

## 4. Readiness: kiểm tra khả năng nhận traffic

Readiness trả lời câu hỏi: **instance này có nên nhận request mới ngay lúc này không?**

Khi readiness thất bại, Kubernetes đánh dấu Pod không sẵn sàng và loại địa chỉ Pod khỏi EndpointSlice của Service tương ứng. Container vẫn chạy; kubelet tiếp tục thực hiện readiness probe để nhận biết khi nào instance có thể phục vụ trở lại.

Readiness thường chuyển sang REFUSING_TRAFFIC trong các trường hợp:

- Ứng dụng đang khởi động và chưa hoàn tất tác vụ bắt buộc.
- Kết nối tới một dependency riêng của instance chưa sẵn sàng.
- Instance đang bảo trì hoặc chủ động drain traffic.
- Ứng dụng quá tải và có chính sách tạm thời từ chối request mới.
- Một dependency cloud thiết yếu cho **mọi request được định tuyến vào instance** đang không thể sử dụng.

Readiness là quyết định ở **cấp instance**, không phải một quy tắc chung cho toàn bộ hệ thống. Nếu chỉ một API endpoint cần một dịch vụ cloud, đưa dịch vụ đó vào readiness toàn ứng dụng có thể loại bỏ cả instance khỏi traffic dù những endpoint khác vẫn hoạt động bình thường.

Ví dụ:

| Dependency | Vai trò trong ứng dụng | Đưa vào readiness? |
|---|---|---|
| Blob chứa mọi tài liệu mà API phải đọc để xử lý request chính | Bắt buộc với mọi request thuộc workload này | Có thể, nếu lỗi khiến instance không phục vụ được traffic đó |
| Cache có fallback sang database | Không bắt buộc | Thường không |
| Queue chỉ dùng cho một endpoint tạo job | Chỉ ảnh hưởng một nhóm request | Cân nhắc tách workload/route hoặc trả lỗi có kiểm soát ở endpoint đó |
| Dịch vụ gửi email thông báo phụ | Có thể retry bất đồng bộ | Không |
| Secret/config bắt buộc chưa nạp khi khởi động | Không thể phục vụ đúng nếu thiếu | Giữ readiness ở trạng thái chưa sẵn sàng đến khi khởi tạo xong |

Nếu dependency dùng chung bị hỏng trên tất cả replica, tất cả Pod có thể trở thành NotReady. Khi đó Kubernetes Service có thể không còn endpoint và kết nối tới Service thất bại thay vì trả một HTTP 503 từ ứng dụng. Vì vậy, hãy cân nhắc readiness cùng circuit breaker, fallback, giới hạn retry và khả năng degraded service.

## 5. Startup probe: bảo vệ giai đoạn khởi động dài

Một ứng dụng có thể cần thời gian để:

- Khởi tạo Spring context và connection pool.
- Nạp cấu hình hoặc dữ liệu cần thiết.
- Chạy migration/kiểm tra schema theo quy trình đã thiết kế.
- Warm cache hoặc tải model/dữ liệu lớn.
- Xác minh các tài nguyên bắt buộc trước khi nhận traffic.

Nếu liveness bắt đầu kiểm tra quá sớm, Kubernetes có thể restart ứng dụng liên tục trước khi ứng dụng kịp khởi động. **Startup probe** giải quyết việc này: trong khi startup probe chưa thành công, Kubernetes chưa chạy liveness và readiness probe của container đó.

Khi startup probe vượt quá failureThreshold lần thất bại liên tiếp, kubelet dừng container theo restart policy. Startup probe phù hợp với thời gian khởi động dài hoặc khó dự đoán; không nên tăng liveness initialDelaySeconds vô hạn để che giấu startup không ổn định.

~~~mermaid
flowchart TD
    A[Container khởi động] --> B[Startup probe]
    B -->|Chưa thành công| C[Chờ và kiểm tra lại]
    C --> B
    B -->|Thành công| D[Bắt đầu liveness và readiness]
    D --> E{Liveness}
    E -->|Thất bại quá ngưỡng| F[Restart container]
    E -->|Thành công| G{Readiness}
    G -->|Thất bại| H[Không gửi traffic vào Pod]
    G -->|Thành công| I[Pod nhận traffic]
    H -->|Kiểm tra lại| G
~~~

Startup, liveness và readiness có mục tiêu khác nhau. Startup bảo vệ giai đoạn khởi động; liveness phát hiện lỗi nội bộ cần restart; readiness điều phối traffic trong toàn bộ vòng đời container.

## 6. Spring Boot Actuator Health endpoint

Thêm dependency Actuator vào ứng dụng Spring Boot:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Chọn phiên bản Spring Boot tương thích với Spring Cloud release train và các starter AWS/Azure/GCP của dự án. Không nâng riêng Actuator lên một major version khác với Spring Boot.

Endpoint health mặc định:

~~~text
GET /actuator/health
~~~

Khi chạy trong Kubernetes, Spring Boot Actuator cung cấp hai health group:

~~~text
GET /actuator/health/liveness
GET /actuator/health/readiness
~~~

Trong Spring Boot 3.x, các health group probe được tự động bật khi ứng dụng được nhận diện đang chạy trong Kubernetes. Có thể bật tường minh ở mọi môi trường bằng `management.endpoint.health.probes.enabled=true`, hữu ích khi kiểm thử local hoặc dùng nền tảng triển khai khác.

Ví dụ response đơn giản:

~~~json
{
  "status": "UP"
}
~~~

Nếu được phép hiển thị component/details, response có thể có thêm thông tin:

~~~json
{
  "status": "UP",
  "components": {
    "livenessState": {
      "status": "UP"
    }
  }
}
~~~

Không nên công khai chi tiết endpoint, account name, bucket/container, lỗi IAM hoặc exception message cho người dùng không có quyền. Probe của Kubernetes chỉ cần mã HTTP thành công/thất bại; đội vận hành có thể xem chi tiết qua kênh giám sát được bảo vệ.

## 7. Cấu hình health group cho Kubernetes

Một cấu hình Spring Boot 3.x cơ bản:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      show-components: never
      probes:
        enabled: true
        add-additional-paths: true
      group:
        readiness:
          include: "readinessState,requiredBlobContainer"
~~~

Ý nghĩa:

- Chỉ expose endpoint health qua HTTP.
- show-details và show-components không công khai dữ liệu nội bộ.
- probes.enabled bật health group liveness/readiness một cách tường minh.
- add-additional-paths tạo endpoint /livez và /readyz trên **cổng HTTP chính của ứng dụng**.
- Readiness group chứa trạng thái readinessState và health indicator requiredBlobContainer.

Spring Boot không tự đưa mọi dependency bên ngoài vào liveness/readiness. Mặc định hai group này tập trung vào availability state của ứng dụng. Việc thêm requiredBlobContainer là quyết định có chủ ý vì ví dụ này giả định Blob container bắt buộc cho workload.

Nếu không muốn dùng additional path, Kubernetes có thể gọi /actuator/health/liveness và /actuator/health/readiness trên management port. Tuy nhiên, nếu Actuator chạy ở port/context riêng, health endpoint có thể vẫn trả lời thành công trong khi web server chính không nhận được kết nối. Đưa probe path lên main port giúp kiểm tra gần hơn với đường phục vụ traffic thực tế.

## 8. Viết HealthIndicator kiểm tra Azure Blob Storage

Spring Boot có các health indicator dựng sẵn cho một số thành phần như DataSource, MongoDB, Redis, RabbitMQ và Elasticsearch. Không nên giả định mọi Azure/AWS/GCP SDK client đều tự có indicator phù hợp. Khi cần kiểm tra một resource cloud cụ thể, có thể viết bean thực thi HealthIndicator.

Ví dụ dưới đây dùng Spring Boot 3.x và Azure Blob SDK. Nó kiểm tra **một container đã cấu hình sẵn** bằng thao tác existence có timeout:

~~~java
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.BlobStorageException;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component
public class RequiredBlobContainerHealthIndicator
        implements HealthIndicator {

    private final BlobContainerClient container;

    public RequiredBlobContainerHealthIndicator(
            BlobServiceClient blobServiceClient,
            @Value("${app.storage.required-container}") String containerName) {
        this.container =
                blobServiceClient.getBlobContainerClient(containerName);
    }

    @Override
    public Health health() {
        try {
boolean exists = container
                    .existsWithResponse(Duration.ofMillis(800), Context.NONE)
                    .getValue();

            if (!exists) {
                return Health.down()
                        .withDetail("dependency", "azure-blob")
                        .withDetail("reason", "required_container_missing")
                        .build();
            }

            return Health.up()
                    .withDetail("dependency", "azure-blob")
                    .build();
        } catch (BlobStorageException ex) {
            return Health.down()
                    .withDetail("dependency", "azure-blob")
                    .withDetail("reason", classify(ex.getStatusCode()))
                    .build();
        } catch (RuntimeException ex) {
            return Health.down()
                    .withDetail("dependency", "azure-blob")
                    .withDetail("reason", "request_failed")
                    .build();
        }
    }

    private String classify(int statusCode) {
        if (statusCode == 403) {
            return "authorization_failed";
        }
        if (statusCode == 404) {
            return "resource_not_found";
        }
        if (statusCode == 408 || statusCode == 429 || statusCode >= 500) {
            return "temporarily_unavailable";
        }
        return "storage_request_rejected";
    }
}
~~~

Tên bean mặc định là RequiredBlobContainerHealthIndicator. Spring Boot loại hậu tố HealthIndicator để tạo ID requiredBlobContainer, vì vậy YAML readiness group có thể include đúng ID này.

Ví dụ giả định:

- BlobServiceClient đã được cấu hình bằng Spring Cloud Azure và Microsoft Entra ID/managed identity.
- Container đã được provision trước bằng IaC.
- Workload cần truy cập container này để phục vụ chức năng chính.
- Identity có quyền data-plane đủ để đọc trạng thái container.

Nếu ứng dụng dùng một phiên bản Azure SDK khác, kiểm tra overload timeout của SDK tương ứng. Không đưa exception message, SAS URL, account key hoặc endpoint nội bộ vào Health details.

Các import trong ví dụ nhắm tới **Spring Boot 3.x**. Spring Boot 4 chuyển các kiểu health contributor sang package mới `org.springframework.boot.health.contributor`; khi nâng major version, cập nhật import và kiểm tra compatibility của Spring Cloud release train trước khi sửa code.

**Giới hạn của phép kiểm tra:** existence/read-properties thành công chứng minh ứng dụng có thể thực hiện thao tác đọc metadata với identity hiện tại. Nó không chứng minh thao tác upload, download mọi blob hoặc mọi quyền nghiệp vụ đều hoạt động. Không thực hiện write/delete thử trong mỗi lần probe chỉ để chứng minh quyền ghi.

## 9. Cấu hình tài nguyên cho ví dụ Azure

Đặt tên container trong cấu hình ứng dụng:

~~~yaml
app:
  storage:
    required-container: documents
~~~

Với môi trường Azure:

- Dùng managed identity thay cho account key nếu dịch vụ và operation hỗ trợ.
- Gán role data-plane tối thiểu cần thiết cho principal của ứng dụng.
- Provision container trước khi deploy.
- Kiểm tra firewall, private endpoint và DNS từ network của workload.
- Đặt timeout/retry của Azure SDK sao cho tổng thời gian health check nhỏ hơn timeout Kubernetes.

Health indicator không tạo container nếu thiếu. Nếu container bắt buộc nhưng chưa tồn tại, trả DOWN giúp readiness giữ instance khỏi nhận traffic cho đến khi hạ tầng được sửa. Tạo resource trong health check sẽ làm probe có side effect, có thể gây race giữa nhiều replica và che giấu lỗi triển khai.

## 10. Mẫu kiểm tra cho AWS và Google Cloud

Nguyên tắc giống nhau giữa các provider: **kiểm tra một tài nguyên đã biết bằng một thao tác nhẹ, có quyền tối thiểu và có timeout**. Tránh gọi API liệt kê toàn bộ tài nguyên chỉ để chứng minh credential còn hoạt động.

| Provider | Storage check minh họa | Điều cần kiểm tra |
|---|---|---|
| **AWS S3** | HeadBucket với bucket đã cấu hình | Bucket tồn tại/được truy cập theo quyền hiện tại; lỗi IAM, region hoặc network |
| **Azure Blob** | BlobContainerClient.existsWithResponse | Container có tồn tại và identity có thể đọc metadata |
| **Google Cloud Storage** | Storage.get(bucketName) | Bucket metadata có thể được đọc bằng credential hiện tại |
| **AWS SQS** | GetQueueAttributes trên queue đã cấu hình | Queue tồn tại và identity có quyền đọc attributes |
| **Azure Queue Storage** | QueueClient.getProperties() | Queue tồn tại và client có thể đọc properties |
| **Google Pub/Sub** | Đọc metadata subscription qua client quản trị | Subscription tồn tại và identity có quyền truy cập metadata |

Ví dụ thao tác metadata với AWS SDK for Java 2.x:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadBucketRequest;

public void checkBucket(S3Client s3, String bucketName) {
    s3.headBucket(HeadBucketRequest.builder()
            .bucket(bucketName)
            .build());
}
~~~

Client cần được cấu hình timeout cho cả một API call và từng attempt, ví dụ bằng `apiCallTimeout` và `apiCallAttemptTimeout` trong ClientOverrideConfiguration. Nếu chỉ gọi API mà không giới hạn thời gian, probe có thể kéo dài hơn timeout của kubelet.

Ví dụ đọc bucket metadata với Google Cloud Storage Java client:

~~~java
import com.google.cloud.storage.Bucket;
import com.google.cloud.storage.Storage;

public void checkBucket(Storage storage, String bucketName) {
    Bucket bucket = storage.get(bucketName);
    if (bucket == null) {
        throw new IllegalStateException("Required bucket is missing");
    }
}
~~~

Các ví dụ trên là **operation của SDK**, chưa phải toàn bộ HealthIndicator production. Hãy đặt chúng trong indicator hoặc adapter có timeout, phân loại lỗi và chỉ đưa vào readiness nếu bucket/queue đó thực sự bắt buộc cho workload.

## 11. Thiết kế health check cho nhiều phụ thuộc cloud

Một ứng dụng có thể kết nối nhiều dịch vụ: object storage, queue, database, secret manager và API bên thứ ba. Không nên gộp tất cả vào một phép kiểm tra duy nhất rồi để bất kỳ lỗi nào cũng làm toàn bộ instance NotReady.

| Nhóm dependency | Ví dụ | Vị trí phù hợp |
|---|---|---|
| Bắt buộc để mọi request chính hoạt động | Database giao dịch hoặc object store cốt lõi | Readiness, nếu không có fallback khả dụng |
| Bắt buộc cho một route/nhóm công việc | Queue chỉ phục vụ endpoint tạo job | Health riêng hoặc readiness riêng cho workload; cân nhắc route-level failure |
| Có fallback/circuit breaker | Cache, API phụ trợ | Health tổng thể/metrics/alert; thường không đưa vào readiness |
| Không ảnh hưởng request hiện tại | Email, báo cáo nền, analytics | Worker health và giám sát riêng |
| Nội bộ process | Thread pool bị kẹt, local state hỏng | Liveness nếu không thể tự phục hồi |

Nếu ứng dụng có nhiều workload khác nhau, cân nhắc tách deployment:

- API đọc tài liệu phụ thuộc Blob.
- Worker xử lý nền phụ thuộc Queue và Blob.
- Notification worker phụ thuộc email provider.

Mỗi workload có readiness riêng, phản ánh đúng dependency cần cho công việc của nó. Cách này tránh việc email provider lỗi làm API đọc tài liệu ngừng nhận toàn bộ traffic.

### 11.1. Không kiểm tra toàn bộ cloud account

Một health check tốt không nên:

- Gọi ListBuckets, list mọi container hoặc list mọi queue mỗi vài giây.
- Download một blob lớn hoặc đọc toàn bộ message.
- Gửi một message giả vào queue rồi xóa ngay.
- Tạo/xóa resource để thử quyền.
- Gọi nhiều API liên tiếp không giới hạn timeout.

Hãy kiểm tra một resource cụ thể mà workload thật sự cần. Health check nên **đọc, nhẹ, ít side effect và có thể lặp lại an toàn**.

### 11.2. Readiness không phải phép thử mọi quyền

Một thao tác đọc metadata thành công không chứng minh identity có quyền ghi hoặc xóa. Nếu workload cần upload blob, thao tác ghi thực tế sẽ kiểm tra quyền ghi và trả lỗi khi quyền sai. Không tạo file test rồi xóa ở mỗi lần probe vì việc đó gây side effect và cần thêm quyền.

Quyền cần được xác minh riêng qua:

- Integration test dùng principal/role giống production.
- Kiểm tra role assignment và scope trong quy trình triển khai.
- Metrics/log từ các operation thật.
- Synthetic test có lịch chạy riêng nếu cần xác minh end-to-end.

## 12. Timeout, retry, cache và tải do probe tạo ra

Kubernetes thường gọi readiness/liveness theo chu kỳ. Nếu mỗi probe đều gọi nhiều API cloud, tổng request sẽ tăng theo số replica và tần suất kiểm tra.

Ví dụ có 40 replica, mỗi replica probe readiness 5 giây một lần, mỗi lần kiểm tra 3 dependency: hệ thống có thể phát sinh khoảng **24 lần gọi dependency mỗi giây**, chưa tính retry và liveness. Khi cloud chậm, retry có thể làm tải tăng đúng lúc dịch vụ đang gặp sự cố.

Các nguyên tắc:

1. **Timeout ngắn và rõ ràng:** SDK operation phải kết thúc trước timeoutSeconds của probe, chừa thời gian cho Spring xử lý response.
2. **Giới hạn retry:** health check không nên retry dài; một phép kiểm tra có thể dùng ít attempt hơn operation nghiệp vụ.
3. **Cache kết quả ngắn hạn khi cần:** có thể dùng background sampler cập nhật trạng thái mỗi vài giây; probe chỉ đọc trạng thái gần nhất. Ghi rõ thời điểm kiểm tra cuối và tránh dùng cache quá cũ.
4. **Jitter:** tránh tất cả replica gọi dependency cùng một thời điểm sau deploy.
5. **Giới hạn số dependency:** chỉ kiểm tra những dịch vụ ảnh hưởng trực tiếp tới khả năng phục vụ của workload.
6. **Tách alert khỏi probe:** một lỗi dependency cần cảnh báo/quan sát, nhưng không nhất thiết phải restart hoặc loại bỏ instance.

Nếu health indicator được gọi trực tiếp, hãy cấu hình timeout ở SDK client. Ví dụ AWS SDK Java 2.x hỗ trợ timeout toàn bộ API call và timeout cho từng attempt; Azure SDK có overload timeout cho nhiều operation; Google Cloud client dùng cấu hình timeout/retry theo client/API tương ứng. Không dùng một giá trị timeout chung mà bỏ qua timeout của HTTP client và retry pipeline.

## 13. Cập nhật trạng thái readiness từ bên trong ứng dụng

Ngoài health indicator, Spring Boot có ApplicationAvailability và AvailabilityChangeEvent để ứng dụng chủ động cập nhật trạng thái.

Ví dụ khi bắt đầu bảo trì một instance:

~~~java
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

@Component
public class MaintenanceReadiness {
    private final ApplicationEventPublisher publisher;

    public MaintenanceReadiness(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void stopAcceptingTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.REFUSING_TRAFFIC);
    }

    public void resumeTraffic() {
        AvailabilityChangeEvent.publish(
                publisher, this, ReadinessState.ACCEPTING_TRAFFIC);
    }
}
~~~

Khi readiness chuyển sang REFUSING_TRAFFIC, readiness health group phản ánh trạng thái đó; Kubernetes ngừng định tuyến traffic tới Pod. Sau khi bảo trì hoàn tất và instance có thể nhận request, phát ACCEPTING_TRAFFIC.

Chỉ cập nhật readiness cho tình trạng ứng dụng thực sự không nên nhận request. Nếu một API cloud tạm timeout, thường nên xử lý ở tầng gọi bằng timeout/circuit breaker và phản hồi có kiểm soát; không cần chuyển toàn bộ ứng dụng sang NotReady.

Liveness state cũng có thể được cập nhật bằng AvailabilityChangeEvent với LivenessState.BROKEN, nhưng chỉ dùng khi phát hiện lỗi nội bộ không thể tự phục hồi. Không đặt liveness BROKEN vì một lần gọi S3, Blob Storage hoặc Pub/Sub thất bại.

## 14. Cấu hình Kubernetes probes

Ví dụ Deployment dùng các path do Spring Boot Actuator cung cấp trên cổng ứng dụng chính:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: document-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: document-api
  template:
    metadata:
      labels:
        app: document-api
    spec:
      containers:
        - name: app
          image: example/document-api:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1
~~~

Diễn giải:

- Startup probe cho ứng dụng tối đa khoảng 5 phút theo ví dụ (30 lần × 10 giây, chưa tính thời gian mỗi request) để hoàn tất khởi động.
- Liveness probe kiểm tra /livez; ba lần liên tiếp thất bại sẽ khiến kubelet restart container.
- Readiness probe kiểm tra /readyz; hai lần liên tiếp thất bại sẽ đánh dấu Pod NotReady, không restart container.
- Khi readiness phục hồi và probe thành công, Pod có thể nhận traffic trở lại.

Các con số là ví dụ khởi đầu, cần điều chỉnh theo thời gian startup, latency và SLA thực tế. timeoutSeconds mặc định của Kubernetes là 1 giây; nên đặt rõ nếu health endpoint có độ trễ cao hơn. Đảm bảo tổng thời gian xử lý health group nhỏ hơn ngân sách timeout probe.

### 14.1. Nếu Actuator chạy trên management port riêng

Nếu cấu hình `management.server.port`, có thể cho probe gọi port đó. Tuy nhiên, health endpoint trên management server có thể thành công dù main server không nhận kết nối hoặc thread pool phục vụ traffic bị hỏng. Với ứng dụng web, nên cân nhắc `management.endpoint.health.probes.add-additional-paths=true` để có /livez và /readyz trên cổng chính.

### 14.2. Bảo vệ endpoint

Probe phải truy cập được từ kubelet. Nếu Spring Security bảo vệ mọi endpoint, hãy cho phép các path probe trong phạm vi mạng phù hợp, nhưng không mở rộng toàn bộ Actuator ra Internet. Chỉ expose health, không expose env, beans, configprops hoặc endpoint quản trị không cần thiết.

Không trả thông tin account, subscription, bucket/container, IAM principal hoặc exception chi tiết trong body health endpoint công khai.

## 15. Kiểm thử health indicator và probe

Kiểm thử nên bao gồm cả trạng thái bình thường lẫn sự cố dependency.

| Kịch bản | Kết quả mong đợi |
|---|---|
| Spring context khởi động thành công | Liveness UP; readiness chuyển UP sau khi startup task hoàn tất |
| Blob container bắt buộc tồn tại và đọc metadata thành công | Indicator requiredBlobContainer UP |
| Container bắt buộc không tồn tại | Indicator DOWN; readiness DOWN nếu được include |
| Identity không có quyền đọc metadata | Indicator DOWN với reason đã phân loại; không lộ exception/credential |
| Azure/AWS/GCP endpoint timeout | Health check kết thúc trong timeout; không treo probe |
| Cache tùy chọn bị lỗi nhưng có fallback | Readiness vẫn UP nếu cache không phải dependency bắt buộc |
| Dependency ngoài cụm ngừng hoạt động | Liveness vẫn UP |
| Ứng dụng chuyển sang bảo trì | Readiness chuyển REFUSING_TRAFFIC |
| Ứng dụng kết thúc graceful shutdown | Readiness ngừng nhận traffic trước khi process dừng |
| Health group chạy trên management port riêng | Kiểm tra thêm main server path để tránh probe thành công giả |

### 15.1. Unit test cho indicator

Có thể mock BlobContainerClient để kiểm tra mapping từ kết quả SDK sang Health:

~~~java
import com.azure.core.http.rest.Response;
import com.azure.core.util.Context;
import com.azure.storage.blob.BlobContainerClient;
import com.azure.storage.blob.BlobServiceClient;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.health.Status;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class RequiredBlobContainerHealthIndicatorTest {
    @Test
    void reportsDownWhenContainerIsMissing() {
        BlobServiceClient service = mock(BlobServiceClient.class);
        BlobContainerClient container = mock(BlobContainerClient.class);
        @SuppressWarnings("unchecked")
        Response<Boolean> response = mock(Response.class);

        when(service.getBlobContainerClient("documents"))
                .thenReturn(container);
        when(container.existsWithResponse(any(Duration.class), any(Context.class)))
                .thenReturn(response);
        when(response.getValue()).thenReturn(false);

        RequiredBlobContainerHealthIndicator indicator =
                new RequiredBlobContainerHealthIndicator(service, "documents");

        assertEquals(Status.DOWN, indicator.health().getStatus());
    }
}
~~~

Để test gọi được constructor trực tiếp như trên, constructor của indicator nhận BlobServiceClient và tên container; annotation Value chỉ phục vụ Spring injection. Trong test đầy đủ, kiểm tra thêm detail required_container_missing, trạng thái UP khi container tồn tại và DOWN khi SDK ném exception.

### 15.2. Integration test trên cloud thật

Azurite không kiểm chứng đầy đủ managed identity, RBAC, private endpoint, DNS, throttling hoặc behavior cloud production. Đối với các yêu cầu này, dùng account test và principal riêng:

- Chạy test với managed identity hoặc workload identity có role tương tự production.
- Xác minh một operation metadata/read đúng resource.
- Thu hồi hoặc giảm role trong môi trường test để xác nhận indicator trả lỗi phù hợp.
- Kiểm tra endpoint probe từ trong Pod/container qua main server port.
- Kiểm tra readiness khi dependency bị chặn tạm thời, sau đó khôi phục.

Với AWS và Google Cloud, thực hiện kiểm thử tương ứng trên account/project test bằng IAM role/service account thật. Không dùng emulator để kết luận authorization cloud đã đúng.

## 16. Lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách điều chỉnh |
|---|---|---|
| Đưa mọi cloud dependency vào liveness | Dependency dùng chung lỗi làm toàn bộ Pod restart | Liveness chỉ phản ánh lỗi nội bộ không thể phục hồi |
| Đưa mọi indicator vào readiness | Một dịch vụ phụ lỗi khiến API không nhận bất kỳ traffic nào | Chỉ include dependency thật sự bắt buộc cho workload |
| Health check gọi list toàn bộ bucket/container | Tăng quyền IAM, chi phí và latency | Kiểm tra một resource đã biết bằng API metadata nhẹ |
| Không cấu hình timeout SDK | Probe treo hoặc vượt timeout kubelet | Đặt timeout toàn operation và attempt phù hợp |
| Retry quá nhiều trong health indicator | Tăng tải khi cloud đang lỗi | Retry rất hạn chế; xử lý retry nghiệp vụ ở tầng service |
| show-details: always trên endpoint công khai | Rò rỉ endpoint, resource name và lỗi bảo mật | Chỉ hiển thị chi tiết cho người được ủy quyền |
| Dùng management port riêng mà không kiểm tra main server | Probe UP dù cổng ứng dụng chính không phục vụ request | Dùng additional path trên main port khi phù hợp |
| Dùng readiness thay alert | Đội vận hành không biết dependency đang suy giảm | Tạo metrics/log/alert riêng cho dependency |
| Đưa dependency riêng của một route vào readiness toàn Pod | Các route không liên quan cũng ngừng nhận traffic | Tách workload hoặc xử lý lỗi ở route/circuit breaker |
| Không test khi tất cả replica NotReady | Service có thể không còn endpoint và client không nhận HTTP response | Thiết kế degraded mode và kiểm thử sự cố toàn cụm |

## 17. Bài tập thực hành và câu hỏi tự kiểm tra

**Tình huống A — Blob Storage lỗi:** API có ba replica, tất cả cùng đọc Azure Blob Storage. Azure tạm trả timeout trong 2 phút. Hãy xác định liveness/readiness nào nên thất bại, đặt timeout cho SDK và giải thích cách tránh restart storm.

**Tình huống B — Cache có fallback:** Redis/ElastiCache/Memorystore bị lỗi nhưng ứng dụng có thể đọc từ database. Hãy quyết định có include cache trong readiness không và thiết kế alert/circuit breaker.

**Tình huống C — Worker và API:** API chỉ gửi message vào queue; worker mới là thành phần tiêu thụ queue. Hãy xác định dependency nào cần nằm trong readiness của API và worker, tránh kiểm tra thừa.

**Tình huống D — Startup chậm:** Ứng dụng cần 150 giây để warm cache và nạp cấu hình. Hãy cấu hình startup probe để liveness không restart container quá sớm, đồng thời giữ readiness ở trạng thái từ chối traffic cho đến khi hoàn tất.

**Tình huống E — Phân quyền sai:** Indicator Azure Blob trả 403 trong production nhưng local chạy được bằng account key. Hãy xác minh managed identity, role data-plane, scope và network; giải thích vì sao local test không chứng minh RBAC production.

**Tình huống F — Một dependency dùng chung bị lỗi:** Tất cả replica cùng phụ thuộc một dịch vụ cloud đang outage. Hãy đánh giá hậu quả khi readiness loại toàn bộ Pod khỏi Service, và đề xuất degraded response/circuit breaker hoặc tách workload.

### Câu hỏi tự kiểm tra

1. **Liveness trả lời điều gì?** Instance còn ở trạng thái có thể tiếp tục chạy hoặc tự phục hồi không.
2. **Readiness trả lời điều gì?** Instance hiện có nên nhận traffic mới không.
3. **Startup probe bảo vệ điều gì?** Giai đoạn khởi động dài trước khi liveness/readiness bắt đầu.
4. **Vì sao dependency cloud không nên mặc định nằm trong liveness?** Lỗi dependency có thể khiến Kubernetes restart mọi replica và tạo cascading failure.
5. **Có phải mọi dependency phải nằm trong readiness không?** Không; chỉ dependency bắt buộc cho workload và không có fallback phù hợp.
6. **HealthIndicator nên kiểm tra gì?** Một thao tác nhẹ trên resource đã biết, với timeout và quyền tối thiểu.
7. **HealthIndicator có chứng minh mọi quyền upload/download không?** Không; nó chỉ chứng minh operation cụ thể đã kiểm tra hoạt động.
8. **Readiness thất bại thì Kubernetes làm gì?** Đánh dấu Pod NotReady và ngừng gửi traffic qua Service; container vẫn chạy.
9. **Liveness thất bại quá ngưỡng thì sao?** Kubelet restart container theo restart policy.
10. **Vì sao cần alert riêng?** Probe điều phối instance; alert giúp con người biết dependency hoặc hệ thống đang suy giảm.

## 18. Tổng kết

Spring Boot Actuator cung cấp HealthIndicator, health groups và các trạng thái application availability để nền tảng điều phối instance. **Liveness** phải phản ánh lỗi nội bộ không thể phục hồi; **readiness** phản ánh khả năng nhận traffic; **startup probe** bảo vệ ứng dụng trong giai đoạn khởi động dài.

Khi tích hợp AWS, Azure và Google Cloud, hãy chỉ kiểm tra những dependency thực sự cần thiết cho workload, dùng một thao tác metadata nhẹ, timeout ngắn và quyền tối thiểu. Không để lỗi của một dịch vụ cloud kéo theo restart toàn bộ ứng dụng. Kết hợp readiness với circuit breaker, fallback, metrics, alert và integration test trên cloud thật để hệ thống vừa phục hồi đúng cách vừa cung cấp thông tin vận hành đáng tin cậy.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Actuator Endpoints and Kubernetes Probes](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html)
- [Spring Boot 3.5 — Application Availability](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html)
- [Spring Boot 3.5 — HealthIndicator API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/health/HealthIndicator.html)
- [Kubernetes — Liveness, Readiness, and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Microsoft Learn — BlobContainerClient Java API](https://learn.microsoft.com/java/api/com.azure.storage.blob.blobcontainerclient)
- [AWS SDK for Java 2.x — Configure client timeouts](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/timeouts.html)
- [Google Cloud Storage Java — Storage API](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/com.google.cloud.storage.Storage)
