# Giữ kiểm thử ổn định trước độ trễ đồng bộ của Kubernetes

Trong chương **Kiểm thử tự động** của **SPRING_CLOUD_KUBERNETES**, bài học này giải quyết tình huống cùng một ca cập nhật ConfigMap hoặc thay đổi số Pod thành công trên máy cá nhân nhưng thỉnh thoảng thất bại trên CI. Phép kiểm tra có thể chạy trước khi các thành phần liên quan quan sát và áp dụng thay đổi.

Mục tiêu là viết kiểm thử có điều kiện thành công rõ ràng, thời hạn hữu hạn và thông tin lỗi đủ để biết hệ thống đang dừng ở đâu. Phạm vi gồm cấu hình Spring, Configuration Watcher, DiscoveryClient, Spring Cloud LoadBalancer, sức khỏe Pod và RBAC. Chỉ đưa những thành phần ứng dụng thực sự sử dụng vào đường kiểm thử.

## 1. Hiểu đúng điều cần chờ

Giả sử kiểm thử cập nhật một ConfigMap chứa thông điệp chào:

~~~java
updateConfigMap("demo.message", "Xin chào từ phiên bản mới");
assertThat(callGreetingApi()).isEqualTo("Xin chào từ phiên bản mới");
~~~

Hai lệnh đứng cạnh nhau trong mã kiểm thử, nhưng thay đổi phải đi qua một chuỗi xử lý khác:

~~~mermaid
sequenceDiagram
    participant T as Kiểm thử
    participant K as Kubernetes API
    participant W as Configuration Watcher
    participant A as Ứng dụng Spring
    T->>K: Cập nhật ConfigMap
    K-->>T: Trả đối tượng đã cập nhật
    K-->>W: Sự kiện thay đổi
    W->>A: Thông báo refresh qua HTTP hoặc Bus
    A->>K: Nạp lại nguồn cấu hình trong kịch bản đọc API
    A->>A: Tạo lại bean hỗ trợ refresh
    T->>A: Đọc kết quả đến khi đạt điều kiện
~~~

Sơ đồ minh họa kịch bản đọc cấu hình qua API. Nếu cấu hình đến từ volume, đường đi còn có bước đồng bộ file. Phản hồi cập nhật của API server xác nhận thay đổi tại đối tượng Kubernetes; nó chưa chứng minh bean hay kết quả nghiệp vụ đã thay đổi.

Đây là vấn đề **hội tụ**: những bên quan sát khác nhau cần thời gian để phản ánh trạng thái mong muốn. Không nên suy ra rằng Kubernetes API luôn trả dữ liệu cũ, cũng không dùng tính bất đồng bộ để giải thích mọi lỗi.

Một ca kiểm thử tốt mô tả bốn yếu tố:

1. **Thay đổi đầu vào:** thao tác nào đã hoàn tất?
2. **Bên quan sát:** API Kubernetes, một Pod cụ thể hay ứng dụng gọi qua load balancer?
3. **Điều kiện đích:** dữ liệu nào chứng minh tác động cần kiểm thử đã xảy ra?
4. **Giới hạn:** sau bao lâu chưa đạt thì phải thất bại?

Ví dụ: “Sau khi ghi ConfigMap chứa revision R, trong 90 giây, Pod có UID U phải trả revision R và thông điệp M từ bean nghiệp vụ; Pod đó không được bị thay thế”. Mốc 90 giây là ngân sách minh họa của fixture, không phải cam kết của Kubernetes.

## 2. Chọn bằng chứng ở đúng tầng

Chờ điều kiện yếu có thể khiến kiểm thử báo xanh trước khi hành vi cần kiểm tra hoạt động.

| Tín hiệu quan sát | Điều có thể kết luận | Điều cần kiểm tra thêm |
| --- | --- | --- |
| Cập nhật ConfigMap thành công | API đã tiếp nhận dữ liệu mới | Ứng dụng đã áp dụng hay chưa |
| Pod ở pha `Running` | Pod đã qua một phần vòng đời khởi động | Readiness và khả năng phục vụ nghiệp vụ |
| Pod có `Ready=True` | Readiness đạt tại thời điểm quan sát | DiscoveryClient và đường gọi từ bên tiêu thụ |
| Danh sách endpoint phù hợp | Control plane có các địa chỉ và điều kiện tương ứng | Cache của client và lưu lượng thực tế |
| DiscoveryClient có instance mới | Client đó nhìn thấy instance | Load balancer đang dùng danh sách nào |
| HTTP 200 | Request cụ thể thành công về giao thức | Đúng Pod, đúng revision và đúng nội dung hay chưa |
| Một Pod trả revision mới | Pod đó phản ánh thay đổi | Những replica còn lại đã áp dụng hay chưa |

Với EndpointSlice, xem các điều kiện `ready`, `serving`, `terminating` và cấu hình Service. `publishNotReadyAddresses` có thể làm thay đổi ý nghĩa mong đợi của `ready`. Hãy tổng hợp tất cả slice của Service và loại trùng theo danh tính endpoint; không giả định một Service luôn chỉ có một slice. Xem [EndpointSlices của Kubernetes](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/).

Không áp đặt EndpointSlice vào mọi cấu hình Spring Cloud Kubernetes. Kiểm thử phải biết implementation DiscoveryClient đang dùng API nào và đọc bằng chứng tương ứng. EndpointSlice có thể hữu ích để chẩn đoán Service nhưng không thay thế phép quan sát ngay tại client.

## 3. Chờ điều kiện thay cho thời gian ngủ cố định

Mẫu sau vừa chậm vừa dễ thất bại:

~~~java
updateConfigMap();
Thread.sleep(10_000);
assertNewBusinessValue();
~~~

Nếu thay đổi hoàn tất sau 300 ms, kiểm thử vẫn mất 10 giây. Nếu CI cần 12 giây, kiểm thử thất bại dù hành vi cuối cùng đúng. Tăng thời gian ngủ chỉ dịch chuyển ranh giới.

Dùng Awaitility để diễn đạt điều kiện:

~~~java
await("ứng dụng áp dụng revision của lần chạy này")
    .pollDelay(Duration.ZERO)
    .pollInterval(Duration.ofMillis(500))
    .atMost(Duration.ofSeconds(90))
    .untilAsserted(() -> {
        var snapshot = readFreshSnapshot();
        assertThat(snapshot.revision()).isEqualTo(expectedRevision);
        assertThat(snapshot.message()).isEqualTo(expectedMessage);
    });
~~~

`readFreshSnapshot()` phải thực hiện quan sát mới mỗi vòng. Đọc một lần trước `await` rồi lặp assertion trên cùng đối tượng không phát hiện được tiến triển.

Assertion chưa đạt trong `untilAsserted` sẽ được đánh giá lại. Ngoại lệ khác không mặc nhiên nên bỏ qua. Chỉ cấu hình bỏ qua các lỗi tạm thời đã biết; không dùng `ignoreExceptions()` cho mọi lỗi. Tài liệu [Awaitility Usage](https://github.com/awaitility/awaitility/wiki/Usage) mô tả polling, xử lý ngoại lệ và kiểm tra điều kiện được duy trì.

**Thao tác gây thay đổi nằm ngoài vòng chờ.** Nếu mỗi vòng lại patch ConfigMap, kiểm thử có thể liên tục tạo sự kiện mới và làm dịch chuyển mốc hội tụ. Vòng chờ chỉ nên quan sát.

## 4. Xác định đường cập nhật cấu hình

Trước khi chọn timeout, xác định ứng dụng lấy cấu hình theo đường nào:

| Đường cấu hình | Hợp đồng kiểm thử phù hợp |
| --- | --- |
| Biến môi trường của container | Đổi nguồn rồi triển khai lại workload; kiểm tra Pod mới |
| File chiếu qua volume | Chờ file thay đổi, sau đó chờ cơ chế nạp lại của ứng dụng |
| ConfigMap/Secret đọc qua Kubernetes API | Chờ cơ chế refresh nạp nguồn và bean nghiệp vụ phản ánh giá trị mới |
| Cấu hình chỉ đọc khi khởi động | Kiểm thử restart/rollout |
| Nguồn cấu hình bất biến | Tạo đối tượng phiên bản mới và cập nhật tham chiếu theo thiết kế |

Với ConfigMap, Kubernetes cập nhật volume theo cơ chế đồng bộ riêng; ứng dụng vẫn phải đọc lại file để dùng giá trị mới. Biến môi trường của container đang chạy không tự đổi theo ConfigMap. Mount bằng `subPath` cũng không nhận cập nhật ConfigMap như mount volume thông thường. Xem [Configure a Pod to Use a ConfigMap](https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/).

Configuration Watcher thông báo refresh qua HTTP hoặc Spring Cloud Bus. Với nguồn đọc file, thời điểm thông báo cần phù hợp thời gian đồng bộ file; refresh quá sớm có thể đọc lại giá trị cũ. Phân biệt **độ trễ refresh của Watcher** với **timeout kiểm thử**. Xem [Configuration Watcher](https://docs.spring.io/spring-cloud-kubernetes/reference/spring-cloud-kubernetes-configuration-watcher.html).

Nếu thông báo đến quá sớm và không có lần refresh tiếp theo, tăng timeout kiểm thử không sửa được luồng đó. Khi kiểm thử Watcher, cũng không gọi `/actuator/refresh` thủ công trong vòng chờ vì có thể che lỗi thông báo.

Với Secret, điều kiện thành công nên là hành vi như kết nối bằng credential thử nghiệm mới hoặc báo mã phiên bản không nhạy cảm. Không đưa mật khẩu, token, nội dung Secret hay hash của bí mật có miền giá trị nhỏ vào chẩn đoán.

## 5. Chuẩn bị fixture và dấu vết cho từng lần chạy

Ví dụ Java dưới đây giả định fixture tích hợp đã được chuẩn bị:

- Mỗi lần chạy có namespace riêng hoặc mức cô lập tương đương.
- Workload có **một replica** cho ca hot refresh; không có rollout tự động khi ConfigMap đổi.
- ConfigMap có `demo.revision` và `demo.message`, là dữ liệu không nhạy cảm.
- Ứng dụng đọc ConfigMap qua API bằng Spring Cloud Kubernetes; Watcher gửi refresh đến đúng ứng dụng.
- Ứng dụng, Watcher và test runner có ServiceAccount/quyền riêng theo chức năng.
- Endpoint quan sát chỉ có trong profile tích hợp và được truy cập trực tiếp ở Pod cần kiểm tra.
- Test runner biết trước UID của Pod, lấy từ Kubernetes API, và có đường truy cập ổn định tới Pod ấy.

Dùng marker `it-<UUID>` để chứng minh kết quả thuộc lần thay đổi hiện tại. Chỉ kiểm tra giá trị thông dụng như `enabled=true` có thể vô tình chấp nhận trạng thái cũ.

Truyền UID vào ứng dụng bằng Downward API:

~~~yaml
env:
  - name: POD_UID
    valueFrom:
      fieldRef:
        fieldPath: metadata.uid
~~~

Đoạn trên nằm trong cấu hình container của Deployment. Test runner chọn Pod thuộc fixture rồi đọc UID từ Kubernetes API. Không lấy UID mong đợi từ chính response cần kiểm chứng.

Cấu hình ứng dụng minh họa:

~~~yaml
spring:
  application:
    name: greeting
  profiles:
    active: it
  config:
    import: "kubernetes:"

management:
  endpoints:
    web:
      exposure:
        include: health,refresh
~~~

ConfigMap do fixture tạo trong cùng namespace:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: greeting
  labels:
    spring.cloud.kubernetes.config: "true"
data:
  demo.revision: baseline
  demo.message: "Xin chào ban đầu"
~~~

Fixture cần starter Config của implementation đã chọn, Actuator, Spring Cloud Context, Service và cấu hình Watcher hoàn chỉnh. Mở endpoint `refresh` chưa đủ để Watcher tìm và gọi đúng Pod. Chỉ cho phép thành phần cần thiết truy cập endpoint quản trị trong môi trường thử nghiệm.

Ví dụ dùng Config Data import; không trộn thêm bootstrap cũ. Tên nguồn và ưu tiên property phải phù hợp dự án. Biến môi trường ghi đè `demo.message` có thể khiến kiểm thử chờ mãi dù ConfigMap đổi đúng. Tham khảo [Kubernetes PropertySource implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html).

## 6. Quan sát bean thực sự dùng cấu hình

Ví dụ dùng Java 17 trở lên. Các lớp dưới đây đặt trong package của ứng dụng; mỗi lớp công khai nằm trong tệp tương ứng khi triển khai.

Snapshot chỉ chứa dữ liệu không nhạy cảm:

~~~java
public record GreetingSnapshot(
    String podUid,
    String revision,
    String message
) {
}
~~~

Bean nghiệp vụ hỗ trợ refresh:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Service;

@Service
@RefreshScope
public class GreetingService {
    private final String revision;
    private final String message;

    public GreetingService(
        @Value("${demo.revision}") String revision,
        @Value("${demo.message}") String message
    ) {
        this.revision = revision;
        this.message = message;
    }

    public GreetingSnapshot snapshot(String podUid) {
        return new GreetingSnapshot(podUid, revision, message);
    }
}
~~~

Endpoint quan sát gọi chính bean nghiệp vụ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("it")
public class ConfigObservationController {
    private final GreetingService greetingService;
    private final String podUid;

    public ConfigObservationController(
        GreetingService greetingService,
        @Value("${POD_UID}") String podUid
    ) {
        this.greetingService = greetingService;
        this.podUid = podUid;
    }

    @GetMapping("/internal/test/config")
    public GreetingSnapshot config() {
        return greetingService.snapshot(podUid);
    }
}
~~~

Revision và message nằm trong cùng một bean đích và được trả trong một lần gọi `snapshot`. Không ghép revision của response này với message của response khác.

Nếu chỉ đọc `Environment`, kiểm thử chưa chứng minh bean nghiệp vụ đã được refresh: nguồn property có thể đổi trong khi bean còn giữ giá trị cũ. Với ứng dụng thật, chọn dữ liệu quan sát tối thiểu và không bật endpoint thử nghiệm trong profile phục vụ người dùng.

## 7. Kiểm thử tích hợp: ghi một lần, chờ đúng kết quả

Ví dụ cần JUnit Jupiter, AssertJ, Awaitility 4.x, Jackson Databind và Fabric8 Kubernetes Client trong test classpath. Dùng phiên bản tương thích BOM và Spring Boot của dự án.

Test runner nhận bốn biến môi trường:

| Biến | Ý nghĩa |
| --- | --- |
| `TEST_NAMESPACE` | Namespace fixture |
| `TEST_CONFIGMAP` | ConfigMap ứng dụng thực sự đọc |
| `TEST_POD_UID` | UID Pod chọn từ Kubernetes API |
| `APP_DIAGNOSTIC_URL` | URL đầy đủ đến `/internal/test/config` của chính Pod đó |

URL có thể dùng kết nối port-forward dành riêng cho Pod. Nếu test runner chạy trong cluster, có thể dùng địa chỉ Pod theo cấu hình mạng cho phép. Không trỏ URL này tới Service cân bằng nhiều replica trong ca kiểm thử một Pod.

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import io.fabric8.kubernetes.api.model.ConfigMap;
import io.fabric8.kubernetes.api.model.ConfigMapBuilder;
import io.fabric8.kubernetes.client.KubernetesClient;
import io.fabric8.kubernetes.client.KubernetesClientBuilder;
import org.awaitility.core.ConditionTimeoutException;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

class ConfigRefreshIT {
    private final String namespace = requiredEnv("TEST_NAMESPACE");
    private final String configMapName = requiredEnv("TEST_CONFIGMAP");
    private final String expectedPodUid = requiredEnv("TEST_POD_UID");
    private final URI endpoint = URI.create(requiredEnv("APP_DIAGNOSTIC_URL"));

    private final HttpClient http = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

    private final ObjectMapper json = new ObjectMapper();
    private final AtomicReference<String> lastObservation =
        new AtomicReference<>("chưa quan sát");

    public record Snapshot(
        String podUid,
        String revision,
        String message
    ) {
    }

    @Test
    void configMapChangeReachesBusinessBeanWithoutReplacingPod() {
        try (KubernetesClient client = new KubernetesClientBuilder().build()) {
            ConfigMap before = client.configMaps()
                .inNamespace(namespace)
                .withName(configMapName)
                .get();

            assertThat(before).as("ConfigMap của fixture").isNotNull();
            assertThat(before.getData()).isNotNull();
            assertThat(before.getData().get("demo.revision")).isNotBlank();
            assertThat(before.getData().get("demo.message")).isNotNull();

            waitFor(
                before.getData().get("demo.revision"),
                before.getData().get("demo.message"),
                Duration.ofSeconds(45)
            );

            String revision = "it-" + UUID.randomUUID();
            String message = "Xin chào " + revision;

            // Gây thay đổi một lần, ngoài vòng polling.
            ConfigMap updated = client.configMaps()
                .inNamespace(namespace)
                .withName(configMapName)
                .edit(current -> new ConfigMapBuilder(current)
                    .addToData("demo.revision", revision)
                    .addToData("demo.message", message)
                    .build());

            assertThat(updated.getMetadata().getUid())
                .isEqualTo(before.getMetadata().getUid());
            assertThat(updated.getData().get("demo.revision"))
                .isEqualTo(revision);

            waitFor(revision, message, Duration.ofSeconds(90));
        }
    }

    private void waitFor(
        String expectedRevision,
        String expectedMessage,
        Duration budget
    ) {
        lastObservation.set("chưa quan sát trong giai đoạn này");

        try {
            await("ConfigMap tới bean nghiệp vụ của Pod " + expectedPodUid)
                .pollDelay(Duration.ZERO)
                .pollInterval(Duration.ofMillis(500))
                .atMost(budget)
                .ignoreExceptionsMatching(error ->
                    error instanceof ConnectException
                        || error instanceof HttpTimeoutException
                        || error instanceof ProbeNotReadyException)
                .untilAsserted(() -> {
                    Snapshot snapshot = readFreshSnapshot();

                    if (!expectedPodUid.equals(snapshot.podUid())) {
                        throw new IllegalStateException(
                            "Endpoint trả Pod khác với fixture");
                    }

                    assertThat(snapshot.revision()).isEqualTo(expectedRevision);
                    assertThat(snapshot.message()).isEqualTo(expectedMessage);
                });
        } catch (ConditionTimeoutException timeout) {
            throw new AssertionError(
                "Hết hạn; namespace=" + namespace
                    + ", configMap=" + configMapName
                    + ", expectedPodUid=" + expectedPodUid
                    + ", expectedRevision=" + expectedRevision
                    + ", last=" + lastObservation.get(),
                timeout);
        }
    }

    private Snapshot readFreshSnapshot()
        throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(endpoint)
            .timeout(Duration.ofSeconds(2))
            .header("Accept", "application/json")
            .GET()
            .build();

        HttpResponse<String> response;
        try {
            response = http.send(
                request, HttpResponse.BodyHandlers.ofString());
        } catch (IOException error) {
            lastObservation.set(error.getClass().getSimpleName());
            throw error;
        }

        int status = response.statusCode();
        lastObservation.set("HTTP " + status);

        if (status == 503) {
            throw new ProbeNotReadyException();
        }
        if (status != 200) {
            throw new IllegalStateException(
                "HTTP ngoài hợp đồng fixture: " + status);
        }

        Snapshot snapshot = json.readValue(response.body(), Snapshot.class);
        if (snapshot.podUid() == null
            || snapshot.revision() == null
            || snapshot.message() == null) {
            throw new IllegalStateException("Response thiếu trường bắt buộc");
        }

        // Không lưu toàn bộ response hoặc giá trị cấu hình.
        lastObservation.set(
            "podUid=" + snapshot.podUid()
                + ", revision=" + snapshot.revision());
        return snapshot;
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Thiếu biến " + name);
        }
        return value;
    }

    private static final class ProbeNotReadyException
        extends RuntimeException {
    }
}
~~~

Mẫu cập nhật ConfigMap dùng DSL `edit` của [Fabric8 Kubernetes Client](https://github.com/fabric8io/kubernetes-client/blob/main/doc/CHEATSHEET.md). Cần đặt timeout hữu hạn cho Kubernetes Client theo API của phiên bản đang dùng; Awaitility không bao trùm lệnh `get` và `edit` nằm bên ngoài nó.

Các điểm quyết định độ tin cậy:

- Chờ baseline trước khi patch để biết ứng dụng ban đầu đã đọc đúng nguồn.
- Mỗi vòng có HTTP GET mới và kiểm tra hai trường trong cùng snapshot.
- Mỗi request HTTP có timeout riêng.
- UID khác là lỗi ngay vì mục tiêu là hot refresh trên cùng Pod.
- Chỉ lỗi kết nối, timeout HTTP và HTTP 503 được coi là tạm thời theo hợp đồng fixture.
- HTTP 401/403, 404, JSON sai và response thiếu trường không bị che bằng retry.
- Test không gọi refresh thủ công: thay đổi phải đi qua Watcher đã cấu hình.

Chỉ bỏ qua HTTP 503 nếu fixture cho phép nó trong giai đoạn chuyển tiếp. Nếu sản phẩm cam kết không gián đoạn, cần test khác ghi nhận 503 là vi phạm. Phép chờ hội tụ này không tự chứng minh tính sẵn sàng liên tục.

Lớp `ConfigRefreshIT` thực hiện phần kiểm chứng; fixture sở hữu việc tạo và dọn tài nguyên. Kết thúc test, fixture xóa namespace riêng kể cả khi assertion thất bại. Không khôi phục hay xóa tài nguyên dùng chung mà ca kiểm thử không sở hữu.

## 8. Chờ discovery và load balancer theo đường gọi thực tế

Spring Cloud Kubernetes LoadBalancer có chế độ chọn Pod và chế độ gọi qua Service. Hai chế độ dẫn tới cách xác minh khác nhau; xem [LoadBalancer for Kubernetes](https://docs.spring.io/spring-cloud-kubernetes/reference/load-balancer.html).

Kiểm thử scale từ một lên hai Pod có thể tách thành ba mốc:

1. **Workload:** controller quan sát thế hệ mong muốn; số replica sẵn sàng và cập nhật phù hợp kịch bản.
2. **Discovery:** instance client nhìn thấy tương ứng tập đích.
3. **Lưu lượng:** lời gọi nghiệp vụ qua đường thực tế thành công và trả danh tính backend hợp lệ.

Không dùng riêng `availableReplicas == 2` để kết luận rollout hoàn tất. Đối chiếu `observedGeneration`, `updatedReplicas`, condition và UID các Pod thuộc controller mong đợi khi mục tiêu có liên quan bản triển khai mới.

Trong chế độ chọn Pod, có thể chuẩn hóa danh sách `ServiceInstance` thành tập `(host, port, namespace)` hoặc UID khi metadata cung cấp. Không giả định mọi implementation dùng Pod UID làm `instanceId`. Trong chế độ Service, một instance có thể đại diện Service; kỳ vọng “hai Pod thì discovery phải có hai instance” có thể sai với hợp đồng đó.

Giả mã cho adapter discovery của bộ kiểm thử:

~~~text
scale workload lên 2 một lần
chờ workload của thế hệ cần kiểm tra sẵn sàng
lấy tập backend mong đợi thuộc fixture

chờ snapshot DiscoveryClient mới khớp tập đích theo chế độ sử dụng
gửi request mới qua client nghiệp vụ
kiểm tra backend trả lời thuộc tập hợp lệ và nội dung đúng
~~~

DiscoveryClient đạt đích chưa chắc danh sách LoadBalancer dùng đã đạt đích. Cache trong chuỗi `ServiceInstanceListSupplier` có thể thêm độ trễ. Tài liệu [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html) mô tả cache và TTL; đừng đưa mặc định của phiên bản khác vào ngân sách của dự án.

Có thể tắt cache trong ca chỉ kiểm tra discovery để giảm số thành phần tham gia. Ca tích hợp cache phải giữ cấu hình đại diện triển khai thực tế và quan sát qua đúng load balancer. Không dùng kết quả cấu hình tắt cache để kết luận độ trễ của cấu hình có cache.

## 9. Kiểm tra loại bỏ Pod và điều kiện phủ định

Sau khi xóa Pod, kiểm tra ngay “không còn instance” thường quá sớm. Ngược lại, một snapshot rỗng có thể quá yếu: nó có thể là kết quả lỗi tạm thời của bên quan sát.

Một quy trình kiểm thử loại bỏ backend:

1. Ghi UID Pod bị loại và UID các Pod được phép phục vụ.
2. Gây thay đổi một lần; nếu mục tiêu là scale xuống, đổi desired replicas thay vì chỉ xóa Pod để Deployment tạo lại.
3. Chờ bên quan sát không còn chọn UID bị loại.
4. Kiểm tra tập còn lại hợp lệ và lời gọi mới đi tới backend được phép.
5. Nếu hợp đồng yêu cầu, quan sát điều kiện giữ được trong một cửa sổ hữu hạn.

Ví dụ Awaitility với adapter của bộ kiểm thử:

~~~java
await("backend cũ không xuất hiện lại trong cửa sổ quan sát")
    .pollInterval(Duration.ofMillis(500))
    .during(Duration.ofSeconds(3))
    .atMost(Duration.ofSeconds(30))
    .untilAsserted(() -> {
        var snapshot = readFreshRoutingSnapshot();
        assertThat(snapshot.backendUids()).isNotEmpty();
        assertThat(snapshot.backendUids()).doesNotContain(removedPodUid);
    });
~~~

Đây là quan sát theo mẫu, không chứng minh mọi request ở mọi thời điểm đều an toàn. Ba giây chỉ minh họa cú pháp; chọn cửa sổ theo hợp đồng sản phẩm.

Nói rõ đang xét request mới, kết nối mới hay request đang xử lý. HTTP keep-alive và phiên kết nối kéo dài có thể giữ đường đi tới backend cũ. Một request thành công tới Pod còn lại không chứng minh Pod bị loại đã biến mất khỏi mọi danh sách định tuyến.

Không kiểm tra phân phối tải bằng “hai request phải thấy đủ hai Pod” trừ khi đã kiểm soát thuật toán, trạng thái client và các cơ chế ảnh hưởng. Kiểm tra thành viên discovery và kiểm tra phân phối lưu lượng là hai mục tiêu riêng.

## 10. Đặt ngân sách thời gian và nhịp polling

Ghi ngân sách theo từng giai đoạn:

| Giai đoạn | Điều cần tính vào ngân sách |
| --- | --- |
| Khởi động fixture | Scheduling, kéo image, container start, startup/readiness probe |
| Cấu hình qua API | Watcher nhận sự kiện, thông báo, nạp nguồn, refresh bean |
| Cấu hình qua file | Đồng bộ volume, thời điểm thông báo, cơ chế đọc lại file |
| Discovery/load balancer | Controller, cập nhật client, cache và kết nối |
| Dọn tài nguyên | Grace period, finalizer, thời gian quan sát việc xóa |

Cách ước lượng phục vụ thiết kế:

~~~text
Ngân sách hội tụ
    = các độ trễ được cấu hình trên đường đi
    + độ trễ quan sát từ những lần chạy thành công
    + biên dự phòng đã giải thích
~~~

Đây là mô hình chọn timeout, không phải giới hạn cứng của Kubernetes. Đo riêng các giai đoạn giúp phân biệt kéo image chậm với thông báo refresh bị thất lạc.

Phân biệt ba đại lượng:

- **Timeout request:** giới hạn một lần gọi API/HTTP.
- **Timeout hội tụ:** tổng thời gian chờ điều kiện đích.
- **Timeout job:** giới hạn toàn ca chạy, gồm setup và cleanup.

Dùng deadline tổng nếu ca có giới hạn chung; mỗi giai đoạn chỉ nhận thời gian còn lại. Năm lần `atMost(90 giây)` độc lập không tạo thành giới hạn tổng 90 giây.

Nhịp polling vài trăm mili giây có thể hợp lý cho fixture nhỏ, không phải mặc định bắt buộc. Với N test đồng thời, mỗi vòng đọc M tài nguyên, chu kỳ P giây tạo xấp xỉ `N × M / P` lượt đọc mỗi giây, chưa tính retry và request nghiệp vụ. Dùng selector hẹp, nhịp phù hợp; test dồn request có thể tự làm cluster chậm.

Khi tự viết deadline, dùng đồng hồ đơn điệu như `System.nanoTime()` để đo khoảng thời gian, tránh phụ thuộc thời gian lịch có thể được điều chỉnh.

## 11. Retry có chọn lọc và fail fast

| Hiện tượng | Cách xử lý đề xuất |
| --- | --- |
| Chưa thấy revision mới trong snapshot hợp lệ | Quan sát tiếp đến deadline |
| Chưa đủ endpoint trong khi workload đang tiến triển | Chờ trong ngân sách đã chọn |
| Lỗi kết nối ở bước được phép gián đoạn | Retry hữu hạn và ghi lỗi gần nhất |
| Kubernetes API trả 401/403 | Dừng để sửa thông tin xác thực hoặc RBAC |
| Endpoint quan sát trả 404 | Kiểm tra fixture/profile/path |
| Kubernetes API trả 404 | Phân biệt đang chờ tạo, chờ xóa hay đọc nhầm tên |
| Response sai schema | Dừng để sửa hợp đồng hoặc phiên bản |
| Revision đúng nhưng message sai | Assertion chưa đạt; nếu kéo dài, điều tra binding và ưu tiên nguồn |
| Container lỗi cấu hình không thể khởi động | Báo lỗi triển khai; tăng timeout không giải quyết được |

Tách retry của **quan sát** khỏi retry của **thao tác ghi**. Với lỗi ghi chưa rõ kết quả, đọc lại trạng thái và dùng idempotency hoặc optimistic concurrency phù hợp, không cứ gửi lại thao tác.

`resourceVersion` hữu ích cho watch và kiểm soát cập nhật đồng thời. Nó không phải revision nghiệp vụ chứng minh ứng dụng đã áp dụng cấu hình. Kiểm thử không cần ép nó thành số để so lớn nhỏ hoặc so giữa các loại tài nguyên. Dùng revision riêng để nối thay đổi nguồn với kết quả ứng dụng. Xem [Kubernetes API Concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/).

## 12. Thu thập thông tin khi hết hạn

Timeout cần trả lời được “kỳ vọng gì, đã quan sát gì, đang thiếu bước nào?”. Fixture có thể thu thập snapshot chẩn đoán có giới hạn:

- Namespace, run ID, tên tài nguyên, UID và revision kỳ vọng.
- Thời gian đã dùng, số vòng polling, lỗi tạm thời gần nhất.
- Thế hệ Deployment, số replica và condition liên quan.
- UID Pod, deletion timestamp, readiness, restart count, trạng thái container.
- Endpoint/EndpointSlice phù hợp và danh sách discovery tại client.
- Backend của response nghiệp vụ gần nhất.
- Đoạn log ứng dụng và Watcher trong cửa sổ ca chạy, đã loại dữ liệu nhạy cảm.

Ví dụ:

~~~text
Giai đoạn: refresh ConfigMap tới bean nghiệp vụ
Namespace: it-greeting-a8d1
ConfigMap: greeting
Expected revision: it-9b72
Expected Pod UID: 6375...
Last observed revision: baseline
Pod Ready: true
Watcher observation: yêu cầu refresh bị HTTP 403
Elapsed: 90s
~~~

Thông tin này gợi ý kiểm tra quyền gọi endpoint quản trị, thay vì sửa lịch polling.

Giới hạn riêng thời gian thu thập chẩn đoán để một lệnh đọc log không làm mất lỗi gốc. Cleanup có deadline và báo lỗi riêng. Nếu test chính đã thất bại, giữ lỗi chính và đính kèm lỗi cleanup.

Không xuất toàn bộ Secret, biến môi trường hay response cấu hình vào CI. Revision của bài được thiết kế không nhạy cảm nên có thể dùng làm dấu vết.

## 13. Cô lập kiểm thử song song và dọn tài nguyên

Hai test cùng sửa một ConfigMap có thể lần lượt đổi revision của nhau; tăng timeout không giải quyết tranh chấp fixture.

Ưu tiên namespace riêng cho mỗi lần chạy hoặc nhóm test cần cô lập. Nếu chỉ khác tên, bảo đảm watcher selector, nguồn cấu hình, Service selector và phạm vi discovery không lẫn nhau. Discovery tìm trên nhiều namespace có thể ghép Service cùng tên ngoài dự kiến.

Phân tách quyền của ba bên:

| Chủ thể | Quyền cần xem xét |
| --- | --- |
| Ứng dụng | Đọc nguồn cấu hình và discovery thực sự sử dụng |
| Configuration Watcher | Quan sát nguồn trong phạm vi cho phép, tìm đích và gửi thông báo |
| Test runner/fixture | Tạo, sửa, xóa tài nguyên thử nghiệm thuộc quyền sở hữu |

Chỉ cấp quyền trên tài nguyên và phạm vi cần thiết, gồm `list/watch` khi implementation thực sự dùng chúng. Không cấp quyền quản trị cluster cho ứng dụng chỉ để test vượt qua. Test RBAC riêng có thể kiểm tra cả trường hợp được phép và bị từ chối.

Dọn tài nguyên trong cơ chế bảo đảm chạy khi thành công hoặc thất bại, như extension/fixture teardown. Với namespace riêng, xóa namespace rồi chờ tài nguyên biến mất trong deadline. Namespace ở trạng thái `Terminating` chưa phải đã xóa xong; thu thập thông tin finalizer nếu quá hạn, không tự gỡ finalizer trên tài nguyên không thuộc test.

Không phụ thuộc thứ tự chạy test. Nếu chia sẻ fixture để tiết kiệm thời gian, cần quy tắc sở hữu và cơ chế tuần tự hóa phần thay đổi.

## 14. Đặt mỗi hành vi ở đúng tầng kiểm thử

| Tầng | Nên kiểm tra |
| --- | --- |
| Unit test | Logic chọn giá trị, so revision, phân loại lỗi, xây điều kiện đích |
| Test với API giả lập | Request/response, lỗi RBAC mô phỏng, nhánh retry của adapter |
| Tích hợp trên cluster thử nghiệm | Probe, đồng bộ endpoint, Watcher, refresh, đường gọi thực |
| Môi trường đại diện | Cache, mạng, nhiều replica, ngân sách hội tụ sát triển khai |

API giả lập không có đầy đủ controller, kubelet, DNS hay mạng Kubernetes. Nó hữu ích để kiểm tra client, nhưng không chứng minh ConfigMap chiếu vào volume hoặc Service định tuyến sau rollout.

Chọn phạm vi theo nhu cầu triển khai:

- Chỉ gọi Service qua DNS: kiểm tra đường DNS/Service đang dùng.
- Dùng Spring Cloud LoadBalancer chọn Pod: kiểm tra discovery và đường chọn backend của client.
- Dùng cấu hình lúc khởi động: kiểm tra rollout và Pod mới.
- Dùng hot refresh: kiểm tra Watcher, RBAC, nguồn cấu hình và bean trên cùng Pod.
- Dùng nhiều replica: kiểm tra từng UID thuộc tập đích; một response qua Service không xác nhận toàn bộ replica.

Với nhiều replica, cố định tập đích phù hợp hoặc giải thích cách xử lý Pod bị thay thế giữa lúc quan sát. Snapshot phải gắn với UID; chỉ đếm số response thành công có thể đếm nhiều lần cùng một Pod.

## 15. Bài tập thực hành

1. Chạy ca ConfigMap với marker duy nhất; ghi thời gian từ khi API trả cập nhật đến khi bean phản ánh revision.
2. Cho một nguồn ưu tiên cao hơn ghi đè message. Giải thích vì sao ConfigMap đúng nhưng assertion nghiệp vụ thất bại.
3. Làm Watcher không gọi được refresh trong fixture. Kiểm tra báo lỗi phân biệt được nhận sự kiện và gửi thông báo hay chưa.
4. Chuyển cấu hình sang biến môi trường. Viết hợp đồng rollout và kiểm tra Pod UID mới.
5. Với fixture LoadBalancer, scale lên rồi xuống; ghi riêng mốc workload, discovery và request nghiệp vụ.
6. Chạy song song hai fixture cô lập, sau đó chủ động cho dùng chung ConfigMap để quan sát tranh chấp.

Tiêu chí hoàn thành: không dùng thời gian ngủ cố định làm bằng chứng đồng bộ; mỗi phép chờ đọc dữ liệu mới, có deadline và điều kiện rõ ràng; lỗi cố định không bị retry vô hạn; timeout chỉ ra bên quan sát cuối cùng; tài nguyên được dọn theo quyền sở hữu.

Kiểm thử ổn định vẫn phải thất bại nếu hệ thống không đạt hợp đồng trong thời hạn. Chờ điều kiện giúp kiểm tra đúng thời điểm và đúng tác động, đồng thời giữ khả năng phát hiện lỗi triển khai thực sự.
