# Làm nóng ứng dụng trước khi công bố trạng thái phục vụ

## 1. Vì sao cần làm nóng ứng dụng?

Một tiến trình Spring Boot có thể đã khởi động web server nhưng chưa sẵn sàng xử lý tải thực tế. Ứng dụng có thể còn phải tạo connection pool, tải cấu hình, nạp cache, biên dịch đường chạy nóng của JVM, tải mô hình hoặc kiểm tra các dependency bắt buộc.

Nếu service được công bố là sẵn sàng ngay khi cổng HTTP mở, registry hoặc Kubernetes có thể đưa request đến instance trong lúc nó còn khởi tạo. Người dùng sẽ thấy lỗi timeout, latency cao hoặc lỗi phụ thuộc dù ứng dụng cuối cùng vẫn khởi động thành công.

**Warm-up** là giai đoạn chuẩn bị trước khi instance nhận traffic nghiệp vụ. Trong Spring Cloud Service Discovery, warm-up cần phối hợp với trạng thái readiness và trạng thái instance trong registry:

- Ứng dụng đã mở cổng nhưng vẫn từ chối traffic mới.
- Các tác vụ chuẩn bị được thực hiện và kiểm tra trong giới hạn thời gian.
- Chỉ sau khi warm-up thành công, instance mới được công bố là sẵn sàng.
- Nếu warm-up thất bại, instance tiếp tục ở trạng thái chưa sẵn sàng hoặc quá trình khởi động bị đánh dấu thất bại.

Mục tiêu không phải trì hoãn mọi lần khởi động. Chỉ thực hiện những bước cần thiết để request đầu tiên có thể được xử lý an toàn và với chất lượng chấp nhận được.

## 2. Phân biệt khởi động, warm-up và readiness

Các mốc trong vòng đời có quan hệ nhưng không đồng nghĩa:

| Mốc | Ý nghĩa | Có nên nhận traffic nghiệp vụ? |
|---|---|---|
| Process started | JVM và tiến trình đã chạy | Chưa |
| Application context refreshed | Bean đã được tạo và cấu hình context | Chưa chắc |
| Web server started | HTTP server đã mở cổng | Chưa chắc |
| Warm-up running | Đang tạo cache, kết nối hoặc chuẩn bị tài nguyên | Chưa |
| Warm-up completed | Các bước chuẩn bị bắt buộc đã hoàn tất | Có thể, sau khi readiness được bật |
| Ready / Accepting traffic | Ứng dụng cho phép nhận request mới | Có |

Một ứng dụng có thể trả lời được endpoint health cơ bản nhưng chưa sẵn sàng xử lý nghiệp vụ. Vì vậy, không nên dùng việc cổng TCP mở hoặc process còn sống làm điều kiện duy nhất để đưa instance vào registry.

~~~mermaid
flowchart TD
    START[Process bắt đầu] --> CONTEXT[Spring context khởi tạo]
    CONTEXT --> SERVER[Web server mở cổng]
    SERVER --> REFUSE[Readiness: REFUSING_TRAFFIC]
    REFUSE --> WARM[Warm-up và kiểm tra dependency]
    WARM --> RESULT{Warm-up thành công?}
    RESULT -->|Không| HOLD[Giữ trạng thái chưa sẵn sàng hoặc fail startup]
    RESULT -->|Có| READY[Readiness: ACCEPTING_TRAFFIC]
    READY --> PUBLISH[Công bố instance phục vụ]
    PUBLISH --> TRAFFIC[Nhận traffic nghiệp vụ]
~~~

Thứ tự đăng ký service có thể khác theo discovery provider. Ví dụ, auto-registration có thể chạy khi web server khởi tạo, trước khi các ApplicationRunner hoàn tất. Vì vậy, cần giữ instance ở trạng thái không phục vụ trong giai đoạn warm-up, thay vì chỉ giả định rằng đăng ký sẽ luôn xảy ra sau ApplicationReadyEvent.

## 3. Chọn những việc cần làm trong warm-up

Warm-up nên ngắn, có giới hạn và gắn trực tiếp với khả năng phục vụ request. Một số công việc thường gặp:

| Công việc | Mục đích | Lưu ý |
|---|---|---|
| Tạo connection pool | Chuẩn bị kết nối database hoặc hệ thống lưu trữ | Dùng timeout và giới hạn số kết nối |
| Kiểm tra cấu hình bắt buộc | Phát hiện thiếu secret, endpoint hoặc feature flag | Không in secret ra log |
| Tải dữ liệu tham chiếu | Tránh request đầu tiên phải tải dữ liệu nền | Chỉ tải phần cần thiết |
| Nạp cache quan trọng | Giảm latency của request đầu tiên | Có giới hạn dung lượng và chính sách stale |
| Nạp mô hình hoặc rule | Chuẩn bị tài nguyên phục vụ xử lý | Xác minh checksum/version nếu cần |
| Khởi tạo client tới dependency | Phát hiện lỗi DNS, TLS hoặc authentication sớm | Không retry vô hạn |
| Chạy một số đường xử lý đại diện | Làm nóng JIT hoặc cache nội bộ | Không tạo side effect nghiệp vụ |

Không nên thực hiện trong warm-up:

- Gửi giao dịch thật hoặc tạo dữ liệu nghiệp vụ không thể hoàn tác.
- Quét toàn bộ dữ liệu lớn chỉ để làm nóng cache.
- Chờ vô hạn một dependency không thiết yếu.
- Tạo tải đồng thời quá lớn lên database hoặc service khác khi nhiều replica khởi động cùng lúc.
- Đưa dữ liệu nhạy cảm vào log để chẩn đoán.

Với nhiều replica khởi động cùng lúc, hãy giới hạn concurrency, dùng jitter hoặc điều phối rollout để tránh warm-up tạo ra một đợt tải đột biến lên dependency.

## 4. Điều khiển readiness bằng Spring Boot

Spring Boot cung cấp trạng thái availability để biểu thị ứng dụng có nên nhận traffic hay không. Hai trạng thái readiness chính:

- **REFUSING_TRAFFIC:** ứng dụng chưa sẵn sàng nhận request.
- **ACCEPTING_TRAFFIC:** ứng dụng đã sẵn sàng nhận request.

Spring Boot có thể công bố trạng thái readiness qua AvailabilityChangeEvent và health group của Actuator. Trong quá trình khởi động thông thường, ứng dụng ở trạng thái từ chối traffic cho đến khi ApplicationReadyEvent được phát. Sau khi các ApplicationRunner và CommandLineRunner hoàn tất, Spring Boot chuyển sang trạng thái chấp nhận traffic.

Điều này phù hợp khi warm-up được thực hiện đồng bộ trong runner: ứng dụng chưa trở thành ready cho đến khi runner kết thúc.

### 4.1. Bật readiness health endpoint

Ví dụ cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

Endpoint readiness thường có đường dẫn:

~~~text
/actuator/health/readiness
~~~

Kubernetes có thể gọi endpoint này trong readinessProbe. Khi trạng thái readiness là REFUSING_TRAFFIC, health group readiness phản ánh trạng thái chưa sẵn sàng; sau khi chuyển sang ACCEPTING_TRAFFIC, endpoint có thể trả trạng thái UP nếu các contributor khác cũng đạt.

Không dùng liveness endpoint thay cho readiness. Liveness trả lời tiến trình có cần khởi động lại hay không; readiness trả lời instance có nên nhận traffic hay không.

### 4.2. Thực hiện warm-up đồng bộ bằng ApplicationRunner

ApplicationRunner chạy sau khi ApplicationContext được khởi tạo và trước khi Spring Boot phát ApplicationReadyEvent. Đây là vị trí phù hợp cho warm-up đồng bộ có thời gian hữu hạn:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ApplicationWarmupRunner implements ApplicationRunner {

    private final WarmupService warmupService;

    public ApplicationWarmupRunner(WarmupService warmupService) {
        this.warmupService = warmupService;
    }

    @Override
    public void run(ApplicationArguments args) {
        warmupService.prepareRequiredResources();
        warmupService.loadCriticalReferenceData();
        warmupService.exerciseRepresentativePath();
    }
}
~~~

Trong ví dụ này, runner chỉ hoàn tất khi các bước warm-up bắt buộc kết thúc. Nếu một bước ném exception, quá trình khởi động có thể thất bại và ứng dụng không chuyển sang readiness ACCEPTING_TRAFFIC.

Các thao tác warm-up phải có timeout và retry hữu hạn. Nếu warm-up có thể kéo dài nhiều phút hoặc cần chạy nền, hãy dùng readiness gate riêng để giữ ứng dụng ở trạng thái chưa sẵn sàng cho đến khi tác vụ nền báo hoàn tất.

## 5. Readiness gate cho warm-up bất đồng bộ

Một số tác vụ không phù hợp để chặn ApplicationRunner, chẳng hạn tải một tập dữ liệu lớn hoặc khởi tạo tài nguyên nền. Có thể tạo trạng thái warm-up riêng và đưa health indicator đó vào readiness group.

Ví dụ coordinator giữ trạng thái:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.stereotype.Component;

@Component
public class WarmupState {
    private final AtomicBoolean completed = new AtomicBoolean(false);

    public boolean isCompleted() {
        return completed.get();
    }

    public void markCompleted() {
        completed.set(true);
    }
}
~~~

Health indicator phản ánh trạng thái warm-up:

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("warmup")
public class WarmupHealthIndicator implements HealthIndicator {

    private final WarmupState warmupState;

    public WarmupHealthIndicator(WarmupState warmupState) {
        this.warmupState = warmupState;
    }

    @Override
    public Health health() {
        if (warmupState.isCompleted()) {
            return Health.up().build();
        }
        return Health.outOfService()
                .withDetail("phase", "warming-up")
                .build();
    }
}
~~~

Thêm contributor warmup vào readiness group:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,warmup
  endpoints:
    web:
      exposure:
        include: health
~~~

Tác vụ nền chỉ gọi markCompleted sau khi mọi bước bắt buộc thành công. Nếu tác vụ thất bại, trạng thái vẫn chưa hoàn tất và Pod tiếp tục NotReady.

Với cách làm bất đồng bộ, cần bảo đảm warm-up thực sự được khởi chạy và có chính sách timeout, retry, logging và xử lý lỗi. Nếu readiness indicator mặc định không bao gồm warmup, Pod có thể trở thành Ready quá sớm.

## 6. Giữ instance chưa phục vụ trong Eureka

Kubernetes readiness và Eureka instance status là hai cơ chế riêng. Readiness probe của Kubernetes không tự động thay đổi trạng thái instance trong Eureka nếu ứng dụng không tích hợp hai cơ chế này.

Eureka có các trạng thái như UP, DOWN, STARTING, OUT_OF_SERVICE và UNKNOWN. Trong giai đoạn warm-up, có thể giữ instance ở trạng thái OUT_OF_SERVICE hoặc STARTING, sau đó chuyển sang UP khi đã sẵn sàng.

Một cấu hình thường dùng là đặt trạng thái ban đầu:

~~~yaml
eureka:
  instance:
    initial-status: OUT_OF_SERVICE
~~~

Sau khi warm-up hoàn tất, Spring Boot chuyển readiness sang ACCEPTING_TRAFFIC. Có thể lắng nghe chính sự kiện availability này để đồng bộ trạng thái Eureka:

~~~java
import com.netflix.appinfo.InstanceInfo;
import com.netflix.discovery.EurekaClient;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class EurekaReadinessListener {

    private final EurekaClient eurekaClient;

    public EurekaReadinessListener(EurekaClient eurekaClient) {
        this.eurekaClient = eurekaClient;
    }

    @EventListener
    public void onReadinessChange(
            AvailabilityChangeEvent<ReadinessState> event) {
        if (event.getState() == ReadinessState.ACCEPTING_TRAFFIC) {
            eurekaClient.setStatus(InstanceInfo.InstanceStatus.UP);
        } else if (event.getState() == ReadinessState.REFUSING_TRAFFIC) {
            eurekaClient.setStatus(InstanceInfo.InstanceStatus.OUT_OF_SERVICE);
        }
    }
}
~~~

Warm-up đồng bộ vẫn chạy trong ApplicationRunner ở phần trước. Listener này chỉ chuyển Eureka sang UP khi Spring Boot công bố readiness ACCEPTING_TRAFFIC; nếu readiness quay lại REFUSING_TRAFFIC, instance được đưa về OUT_OF_SERVICE. Ví dụ minh họa tích hợp riêng với Eureka. Cần xác nhận property initial-status và API client phù hợp với phiên bản Spring Cloud Netflix đang dùng. Nếu auto-registration bị tắt hoặc provider đăng ký theo cách khác, phải điều chỉnh trình tự register/status tương ứng.

Nếu warm-up thất bại, không chuyển instance sang UP. Có thể để startup thất bại để nền tảng khởi động lại, hoặc giữ trạng thái OUT_OF_SERVICE và thực hiện retry có giới hạn theo chính sách vận hành.

### 6.1. Dùng health check integration của Eureka

Spring Cloud Netflix Eureka Client có thể tích hợp health state của ứng dụng vào trạng thái được công bố:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

Khi bật health check integration, trạng thái health của ứng dụng có thể được sử dụng để cập nhật trạng thái instance trong Eureka. Có thể xây dựng một HealthIndicator dành riêng cho warm-up và bảo đảm nó phản ánh đúng trạng thái hoàn tất. Nếu đồng thời dùng listener cập nhật status thủ công, hãy bảo đảm hai nguồn trạng thái không mâu thuẫn; health indicator cần báo trạng thái chưa sẵn sàng cho đến khi warm-up hoàn tất.

Không nên giả định health check integration tự hiểu mọi readiness state hoặc tự bao gồm mọi health group của Actuator trong mọi phiên bản. Hãy kiểm tra cách phiên bản đang dùng ánh xạ Health status sang Eureka status và xác minh bằng cách truy vấn registry trong khi warm-up.

Nếu cần kiểm soát thời điểm công bố một cách chặt chẽ, trạng thái ban đầu OUT_OF_SERVICE kết hợp cập nhật UP sau khi Spring Boot chuyển sang ACCEPTING_TRAFFIC là một cách rõ ràng. Health check integration có thể bổ sung việc phản ánh suy giảm sức khỏe sau khi đã phục vụ, miễn là trạng thái health và thao tác setStatus được phối hợp nhất quán.

## 7. Kết hợp warm-up với Consul

Với Spring Cloud Consul Discovery, service thường được đăng ký cùng health check. Consul có thể đánh dấu service là passing, warning hoặc critical dựa trên kết quả check.

Một cấu hình HTTP health check minh họa:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        health-check-path: /actuator/health/readiness
        health-check-interval: 10s
        register-health-check: true
~~~

Nếu readiness endpoint vẫn báo chưa sẵn sàng trong lúc warm-up, health check của Consul có thể đánh dấu instance chưa passing. Khi warm-up hoàn tất và readiness endpoint chuyển UP, lần kiểm tra tiếp theo có thể cập nhật trạng thái service.

Cần phân biệt đăng ký service trong catalog với trạng thái health check. Instance có thể đã xuất hiện trong catalog nhưng vẫn ở trạng thái critical; client cần truy vấn các service passing nếu chỉ muốn nhận instance khỏe mạnh.

Chu kỳ health check tạo thêm độ trễ từ lúc warm-up hoàn tất đến lúc Consul đánh dấu passing. Nếu cần thời gian chuyển trạng thái nhanh hơn, hãy điều chỉnh interval trong giới hạn tải và khả năng đáp ứng của health endpoint.

## 8. Warm-up và Kubernetes readiness

Trong Kubernetes, readiness probe là cơ chế trực tiếp để điều khiển Pod có được đưa vào endpoint thông thường của Service hay không. Một Pod có thể Running trong suốt warm-up nhưng vẫn NotReady.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: payment-service
  template:
    metadata:
      labels:
        app: payment-service
    spec:
      containers:
        - name: payment-service
          image: example/payment-service:2.5.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
~~~

Startup probe cho phép ứng dụng có thời gian khởi động ban đầu. Readiness probe tiếp tục giữ Pod khỏi endpoint cho đến khi warm-up hoàn tất. Liveness probe chỉ nên phản ánh tiến trình có cần restart hay không.

Khi readiness chuyển thành công:

1. Pod condition Ready được cập nhật.
2. EndpointSlice controller cập nhật điều kiện endpoint.
3. Service networking có thể đưa Pod vào tập đích nhận traffic mới.
4. Ingress, gateway hoặc client discovery cập nhật danh sách theo cơ chế của chúng.

Các thành phần có cache riêng nên thay đổi không nhất thiết đến mọi client ngay cùng một thời điểm.

## 9. Thứ tự warm-up và đăng ký theo từng mô hình

Không có một thứ tự duy nhất cho mọi provider. Hãy xác định thời điểm auto-registration diễn ra và cách giữ instance không phục vụ trước khi triển khai.

| Mô hình | Cách giữ instance chưa phục vụ | Khi nào cho nhận traffic? |
|---|---|---|
| Kubernetes Service | Readiness probe trả NotReady | Khi warm-up hoàn tất và readiness trả UP |
| Eureka auto-registration | Initial status OUT_OF_SERVICE/STARTING hoặc health integration | Chuyển status sang UP sau warm-up |
| Consul Discovery | Health check readiness chưa passing | Khi health check chuyển sang passing |
| Tự quản lý ServiceRegistry | Chưa register hoặc register với status không phục vụ | Gọi register/setStatus sau khi chuẩn bị xong |

Nếu một ứng dụng vừa chạy Kubernetes vừa đăng ký Eureka, cần giữ cả hai trạng thái đồng nhất. Ví dụ, Pod NotReady nhưng Eureka status UP vẫn có thể bị client ngoài Kubernetes tìm thấy và gọi trực tiếp.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Warm as Warmup Coordinator
    participant K8s as Kubernetes
    participant Reg as Eureka / Consul
    App->>K8s: Pod bắt đầu, readiness chưa đạt
    App->>Reg: Instance chưa phục vụ (OOS / health critical)
    App->>Warm: Bắt đầu warm-up
    Warm->>Warm: Kết nối, nạp cache, kiểm tra tài nguyên
    Warm-->>App: Warm-up hoàn tất
    App->>K8s: Readiness chuyển UP
    App->>Reg: Trạng thái instance chuyển phục vụ
    K8s-->>App: Endpoint được cập nhật dần
    Reg-->>App: Registry/client nhận thay đổi dần
~~~

## 10. Thiết kế retry, timeout và lỗi warm-up

Warm-up là một phần của khởi động nên lỗi cần được xử lý có chủ đích:

- Đặt timeout riêng cho từng dependency.
- Dùng retry có giới hạn và backoff, tránh retry liên tục.
- Phân biệt dependency bắt buộc với dependency tùy chọn.
- Ghi log tên bước, thời gian và nguyên nhân thất bại, không ghi secret.
- Đặt tổng thời gian warm-up tối đa để rollout không bị treo vô hạn.
- Nếu warm-up chạy nền, giữ readiness ở trạng thái từ chối traffic cho đến khi có kết quả cuối.
- Nếu warm-up không thể phục hồi, để startup thất bại hoặc giữ instance ngoài phục vụ và phát cảnh báo.

Khi nhiều replica khởi động đồng thời, có thể tạo một đợt tải lớn lên database, cache hoặc API cấu hình. Dùng concurrency limit, jitter và rollout strategy phù hợp để phân tán tải.

Không dùng readiness thất bại như một cách che giấu lỗi khởi động vĩnh viễn. Cần có cảnh báo khi Pod hoặc instance ở trạng thái warming-up quá lâu.

## 11. Quan sát thời gian warm-up

Nên đo thời gian từng bước thay vì chỉ ghi một dòng “application ready”. Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| **application_warmup_duration_seconds** | Tổng thời gian warm-up |
| **application_warmup_step_duration_seconds** | Thời gian từng bước chuẩn bị |
| **application_warmup_success_total** | Số lần warm-up hoàn tất |
| **application_warmup_failure_total** | Số lần warm-up thất bại |
| **application_readiness_state** | Trạng thái readiness hiện tại |
| **service_registry_status** | Trạng thái instance được công bố |

Tên metric là ví dụ quy ước; cần dùng naming convention và instrumentation của hệ thống giám sát hiện tại. Nên gắn nhãn theo service và phiên bản, tránh dùng instance ID có cardinality quá cao nếu hệ thống metrics không phù hợp.

Để điều tra rollout chậm, so sánh:

- Thời gian từ process start đến web server start.
- Thời gian từ server start đến warm-up complete.
- Thời gian từ warm-up complete đến readiness UP.
- Thời gian từ readiness UP đến endpoint xuất hiện trong Kubernetes hoặc registry chuyển sang passing/UP.

Những mốc này cho biết độ trễ nằm trong ứng dụng, probe, registry hay cache phía client.

## 12. Kiểm thử hành vi warm-up

Một bài kiểm thử thực tế nên bao gồm cả trường hợp thành công và thất bại:

1. Khởi động ứng dụng với dependency khỏe mạnh; xác nhận readiness ban đầu chưa đạt.
2. Quan sát registry để xác nhận instance chưa được đánh dấu phục vụ trong warm-up.
3. Chờ warm-up hoàn tất; xác nhận readiness chuyển ACCEPTING_TRAFFIC hoặc health endpoint trả UP.
4. Kiểm tra Eureka status, Consul passing hoặc EndpointSlice ready tương ứng.
5. Gửi request nghiệp vụ và xác nhận request đến instance sau khi warm-up.
6. Làm dependency bắt buộc thất bại; xác nhận ứng dụng không chuyển sang trạng thái phục vụ.
7. Kiểm tra timeout và retry có giới hạn; bảo đảm ứng dụng không bị treo vô hạn.
8. Nếu warm-up bất đồng bộ, xác nhận health indicator vẫn giữ trạng thái NotReady cho đến khi tác vụ hoàn tất.

| Tình huống | Kết quả mong đợi |
|---|---|
| Warm-up hoàn tất | Instance chuyển sang trạng thái sẵn sàng |
| Dependency bắt buộc không truy cập được | Instance không nhận traffic mới |
| Dependency tùy chọn gặp lỗi | Ứng dụng vẫn ready nếu nghiệp vụ cho phép |
| Warm-up vượt thời gian tối đa | Có cảnh báo hoặc startup thất bại theo chính sách |
| Pod bị xóa trong khi đang warm-up | Pod không được xem là endpoint ready |
| Instance Eureka chưa warm-up | Status không phải UP |
| Consul health check trong warm-up | Service chưa ở trạng thái passing |

## 13. Những lỗi thiết kế thường gặp

### 13.1. Dùng ApplicationReadyEvent để bắt đầu warm-up

ApplicationReadyEvent có nghĩa các runner đã hoàn tất và ứng dụng chuẩn bị chuyển sang trạng thái ready. Nếu chỉ bắt đầu warm-up tại event này, readiness có thể đã chuyển sang ACCEPTING_TRAFFIC. Hãy thực hiện warm-up đồng bộ trong ApplicationRunner/CommandLineRunner hoặc giữ một readiness gate riêng cho tác vụ nền.

### 13.2. Chỉ dùng readiness của Kubernetes nhưng quên Eureka

Nếu ứng dụng vừa có Kubernetes Service vừa đăng ký Eureka, Pod có thể NotReady nhưng Eureka vẫn công bố UP. Các client truy cập Eureka bên ngoài cluster vẫn có thể gọi instance. Cần đồng bộ trạng thái ở cả hai nơi.

### 13.3. Nhầm liveness với readiness

Warm-up chưa hoàn tất thường không có nghĩa tiến trình cần restart. Nếu liveness phụ thuộc vào trạng thái warm-up, kubelet có thể restart lặp lại và không bao giờ cho ứng dụng đủ thời gian chuẩn bị.

### 13.4. Warm-up không có timeout

Một dependency bị treo có thể khiến ứng dụng không bao giờ ready. Đặt timeout, retry hữu hạn và cảnh báo thời gian warm-up vượt ngưỡng.

### 13.5. Warm-up tạo side effect nghiệp vụ

Gửi thanh toán, tạo đơn hàng hoặc phát message thật để “làm nóng” có thể gây dữ liệu sai. Chỉ chạy thao tác đại diện an toàn, có thể lặp và không tạo side effect ngoài ý muốn.

### 13.6. Cho rằng status UP có nghĩa mọi client đã cập nhật

Sau khi registry đổi trạng thái, peer replication, health check interval và client cache vẫn cần thời gian cập nhật. Hãy quan sát endpoint ở nhiều lớp thay vì chỉ kiểm tra một dashboard.

## 14. Quy trình triển khai khuyến nghị

1. Xác định các bước warm-up bắt buộc và tùy chọn.
2. Đặt timeout, retry và tổng thời gian tối đa cho từng bước.
3. Chọn warm-up đồng bộ trong ApplicationRunner hoặc bất đồng bộ với readiness gate.
4. Bật Spring Boot readiness health endpoint và cấu hình probe phù hợp.
5. Nếu dùng Eureka, giữ initial status ngoài UP và chỉ chuyển UP sau warm-up; xác minh hành vi với phiên bản đang dùng.
6. Nếu dùng Consul, để health check readiness phản ánh trạng thái warm-up và chỉ truy vấn service passing khi cần instance khỏe.
7. Nếu chạy trên Kubernetes, kiểm tra EndpointSlice và bảo đảm Pod chưa Ready không nhận traffic mới.
8. Đo thời gian warm-up và độ trễ từ warm-up đến lúc endpoint được công bố.
9. Kiểm thử lỗi dependency, restart, rolling update và nhiều replica khởi động đồng thời.

## 15. Tổng kết

Warm-up chuẩn bị tài nguyên và đường xử lý quan trọng trước khi service nhận traffic. Spring Boot có thể giữ readiness ở REFUSING_TRAFFIC trong quá trình ApplicationRunner chạy; với tác vụ nền, một health indicator riêng cần giữ readiness chưa đạt cho đến khi warm-up hoàn tất.

Kubernetes dùng readiness probe để quyết định Pod có nằm trong tập endpoint phục vụ hay không. Eureka và Consul có trạng thái registry/health riêng, vì vậy cần giữ instance ở trạng thái chưa phục vụ trong lúc warm-up và chỉ chuyển sang UP hoặc passing sau khi hoàn tất. Khi ứng dụng chạy qua nhiều cơ chế discovery, hãy đồng bộ các trạng thái, đặt timeout và retry hữu hạn, đồng thời đo độ trễ ở từng bước để tránh công bố instance quá sớm.
