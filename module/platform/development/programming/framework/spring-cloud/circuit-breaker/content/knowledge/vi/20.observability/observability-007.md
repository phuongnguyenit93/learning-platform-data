# Tránh dùng lỗi một phụ thuộc tùy chọn để làm hỏng liveness

Trong ứng dụng Spring Cloud chạy trên Kubernetes, liveness probe cho biết tiến trình ứng dụng còn hoạt động và có thể tiếp tục chạy hay không. Readiness probe cho biết instance đã sẵn sàng nhận traffic hay chưa. Hai tín hiệu này có mục đích khác nhau. Nếu một dịch vụ phụ thuộc tùy chọn như gợi ý sản phẩm, gửi email hoặc tra cứu nội dung gặp sự cố, ứng dụng vẫn có thể xử lý phần lớn request nhờ fallback. Không nên để lỗi của phụ thuộc tùy chọn làm liveness thất bại, khiến Kubernetes khởi động lại container đang hoạt động bình thường.

Khi mọi replica cùng kiểm tra một phụ thuộc bên ngoài trong liveness, một sự cố ở phụ thuộc có thể khiến tất cả replica bị đánh dấu không khỏe và khởi động lại liên tục. Việc restart không sửa được dịch vụ bên ngoài; nó còn làm giảm năng lực xử lý và có thể khuếch đại sự cố. Cần thiết kế health check theo khả năng sống của tiến trình và khả năng nhận traffic của ứng dụng, đồng thời theo dõi phụ thuộc bằng tín hiệu riêng.

## Phân biệt liveness, readiness và startup probe

Ba loại probe trong Kubernetes trả lời ba câu hỏi khác nhau:

| Probe | Câu hỏi | Khi thất bại |
|---|---|---|
| **Liveness** | Tiến trình có còn hoạt động và có thể tiếp tục chạy không? | Kubelet có thể khởi động lại container sau khi đạt ngưỡng thất bại. |
| **Readiness** | Instance có thể nhận và xử lý traffic hiện tại không? | Pod bị loại khỏi các endpoint nhận traffic cho đến khi readiness thành công trở lại. |
| **Startup** | Ứng dụng đã hoàn tất giai đoạn khởi động chưa? | Kubelet tiếp tục kiểm tra startup và chưa thực hiện liveness/readiness cho đến khi startup thành công. |

Liveness nên phản ánh tình trạng nội bộ của tiến trình: ứng dụng đã khởi tạo, event loop hoặc thread chính không bị treo nghiêm trọng và có thể tiếp tục hoạt động. Nó không nên phụ thuộc vào việc mọi dịch vụ từ xa đều khỏe.

Readiness có thể xét những điều kiện thật sự cần để instance nhận request. Nếu cơ sở dữ liệu là điều kiện bắt buộc để mọi endpoint hoạt động an toàn, readiness có thể phản ánh tình trạng kết nối hoặc trạng thái ứng dụng liên quan. Nếu một phụ thuộc chỉ phục vụ chức năng phụ và có fallback, sự cố của nó thường không nên làm toàn bộ instance unready.

Startup probe hữu ích khi ứng dụng khởi động lâu, chẳng hạn cần nạp cấu hình hoặc khởi tạo dữ liệu cục bộ. Nó giúp Kubernetes không đánh giá liveness quá sớm trong giai đoạn ứng dụng chưa hoàn tất khởi động.

## Vì sao phụ thuộc tùy chọn không nên quyết định liveness?

Giả sử một API tổng hợp trang sản phẩm gọi ba dịch vụ: danh mục, tồn kho và gợi ý sản phẩm. Danh mục và tồn kho là dữ liệu cốt lõi; gợi ý sản phẩm là chức năng tùy chọn. Khi dịch vụ gợi ý ngừng hoạt động, ứng dụng vẫn có thể trả trang sản phẩm với dữ liệu danh mục và tồn kho, đồng thời bỏ qua phần gợi ý hoặc dùng cache.

Nếu liveness kiểm tra cả ba dịch vụ, lỗi của dịch vụ gợi ý có thể khiến toàn bộ pod bị restart. Một chuỗi sự kiện nguy hiểm có thể xảy ra:

~~~mermaid
flowchart TD
    A[Dịch vụ gợi ý gặp sự cố] --> B[Liveness gọi hoặc phụ thuộc vào dịch vụ gợi ý]
    B --> C[Liveness probe thất bại]
    C --> D[Kubernetes restart các pod]
    D --> E[Năng lực xử lý giảm và kết nối bị tạo lại]
    E --> F[Tải lên các dịch vụ còn lại tăng]
    F --> G[Sự cố lan rộng]
~~~

Circuit breaker giúp ngăn request tiếp tục gọi phụ thuộc đang lỗi. Fallback giúp ứng dụng duy trì chức năng cốt lõi. Liveness nên tiếp tục thành công khi tiến trình còn hoạt động, kể cả khi circuit breaker của phụ thuộc tùy chọn đang OPEN.

Không nên dùng liveness để buộc ứng dụng restart nhằm thử khôi phục một dịch vụ từ xa. Kubernetes restart container của ứng dụng, không restart dịch vụ phụ thuộc. Việc khởi động lại hàng loạt client còn có thể tạo ra một đợt kết nối và request mới đúng lúc hệ thống đang quá tải.

## Cấu hình health probe với Spring Boot Actuator

Spring Boot Actuator cung cấp các health group dành cho liveness và readiness. Khi bật probe support, ứng dụng có thể công bố endpoint riêng:

- /actuator/health/liveness
- /actuator/health/readiness

Có thể bật probe và công bố thêm các đường dẫn ngắn trên cổng HTTP chính:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState
~~~

Với cấu hình này, Spring Boot cung cấp các nhóm health dựa trên trạng thái availability của ứng dụng. Khi add-additional-paths được bật, có thể dùng /livez và /readyz trên cổng server chính để Kubernetes kiểm tra cùng tiến trình phục vụ request.

Không đưa health indicator của phụ thuộc tùy chọn vào nhóm liveness. Ví dụ, một indicator kiểm tra dịch vụ gợi ý, Redis dùng cho cache không bắt buộc hoặc dịch vụ gửi email không nên làm tiến trình bị restart khi các dịch vụ đó không sẵn sàng.

Readiness cũng cần được chọn có chủ đích. Nếu một phụ thuộc tùy chọn hỏng nhưng ứng dụng có fallback và vẫn phục vụ các endpoint cốt lõi, không nên tự động đưa indicator đó vào readiness group chung. Có thể công bố trạng thái phụ thuộc trong một health group riêng để chẩn đoán.

## Cấu hình probe trong Kubernetes

Ví dụ Deployment sử dụng endpoint probe của Spring Boot:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: product-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: product-api
  template:
    metadata:
      labels:
        app: product-api
    spec:
      containers:
        - name: product-api
          image: example/product-api:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
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
~~~

Các giá trị thời gian chỉ là ví dụ. Hãy điều chỉnh theo thời gian khởi động, độ trễ bình thường và yêu cầu triển khai. Startup probe cho phép ứng dụng có thời gian khởi động; liveness chỉ được bắt đầu sau khi startup probe thành công. Readiness tiếp tục kiểm tra khả năng nhận traffic trong suốt vòng đời pod.

Endpoint probe nên nhẹ, nội bộ và trả kết quả nhanh. Tránh thực hiện một loạt lời gọi HTTP đồng bộ đến mọi dịch vụ phụ thuộc mỗi khi kubelet gọi probe. Những kiểm tra mạng đó có thể làm probe chậm, phụ thuộc vào timeout của nhiều dịch vụ và biến một sự cố ngoài ứng dụng thành lỗi sức khỏe của chính tiến trình.

## Chọn phụ thuộc nào ảnh hưởng đến readiness?

Không phải mọi phụ thuộc đều tùy chọn. Hãy phân loại theo khả năng ứng dụng tiếp tục phục vụ khi phụ thuộc không sẵn sàng:

| Loại phụ thuộc | Ví dụ | Ảnh hưởng đến liveness | Ảnh hưởng đến readiness |
|---|---|---|---|
| Phụ thuộc tùy chọn | Gợi ý sản phẩm, gửi email, nội dung bổ sung | Không | Thường không, nếu có fallback hoặc có thể bỏ qua chức năng. |
| Phụ thuộc quan trọng cho một nhóm endpoint | Dịch vụ tồn kho cho thao tác giữ chỗ | Không | Có thể ảnh hưởng đến readiness của ứng dụng nếu phần lớn traffic không thể xử lý an toàn; cân nhắc tách service hoặc route nếu phạm vi hẹp. |
| Phụ thuộc bắt buộc cho mọi request | Cơ sở dữ liệu chính trong ứng dụng không có chế độ suy giảm | Không nên dùng để quyết định restart tiến trình | Có thể làm readiness thất bại nếu không thể phục vụ bất kỳ request nào một cách đúng đắn. |
| Tài nguyên nội bộ thiết yếu | Thread pool bị kẹt hoàn toàn, ứng dụng không thể xử lý request | Có thể ảnh hưởng nếu tiến trình thực sự không thể phục hồi | Có thể ảnh hưởng. |

Một điểm quan trọng: readiness thất bại không có nghĩa pod bị restart. Nó chủ yếu ngăn pod nhận traffic qua Service. Nếu một ứng dụng có nhiều chức năng với mức phụ thuộc khác nhau, việc đánh dấu cả pod unready vì một endpoint phụ bị lỗi có thể làm giảm khả năng phục vụ những endpoint còn hoạt động. Khi đó, cân nhắc tách chức năng thành service riêng hoặc xử lý suy giảm ở từng request bằng circuit breaker và fallback.

## Tách trạng thái phụ thuộc thành health group riêng

Có thể tạo một health group riêng để theo dõi các phụ thuộc hoặc circuit breaker mà không gắn chúng vào probe của Kubernetes:

~~~yaml
management:
  endpoint:
    health:
      group:
        dependencies:
          include: inventoryCircuitBreaker,recommendationService
          show-details: when-authorized
~~~

Tên inventoryCircuitBreaker và recommendationService ở đây là tên các health contributor bean do ứng dụng cung cấp. Endpoint nhóm có thể được truy cập qua /actuator/health/dependencies, tùy cấu hình Actuator và chính sách bảo mật.

Health group riêng giúp nhóm vận hành xem trạng thái phụ thuộc mà không biến chúng thành điều kiện sống của tiến trình. Cần giới hạn quyền truy cập chi tiết health endpoint và không để lộ thông tin nhạy cảm như URL nội bộ, thông tin xác thực hoặc exception chứa dữ liệu request.

Nếu dùng Resilience4j, có thể theo dõi trạng thái circuit breaker qua metrics và event listener. Khi cần hiển thị trong health group riêng, ứng dụng có thể cung cấp HealthIndicator đọc trạng thái registry. Indicator nên đọc trạng thái cục bộ nhanh, không gọi mạng đồng bộ đến phụ thuộc trong mỗi lần kiểm tra.

Ví dụ minh họa một health indicator chỉ quan sát trạng thái circuit breaker:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("inventoryCircuitBreaker")
public class InventoryCircuitBreakerHealthIndicator
        implements HealthIndicator {

    private final CircuitBreakerRegistry registry;

    public InventoryCircuitBreakerHealthIndicator(
            CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    @Override
    public Health health() {
        CircuitBreaker breaker =
                registry.circuitBreaker("inventory-read");

        CircuitBreaker.State state = breaker.getState();

        if (state == CircuitBreaker.State.OPEN) {
            return Health.status("DEGRADED")
                    .withDetail("circuitBreaker", state.name())
                    .build();
        }

        return Health.up()
                .withDetail("circuitBreaker", state.name())
                .build();
    }
}
~~~

Đây là indicator phục vụ chẩn đoán. Nếu dùng nó trong health group riêng, trạng thái DEGRADED có thể cho biết phụ thuộc đang bị ngắt mạch. Không đưa indicator này vào liveness group. Nếu hệ thống tùy chỉnh status mapping của Actuator, hãy xác định rõ HTTP status của DEGRADED và bảo vệ endpoint theo quyền truy cập.

## Kết hợp circuit breaker và fallback cho phụ thuộc tùy chọn

Health probe không thay thế cơ chế bảo vệ từng lời gọi. Với một phụ thuộc tùy chọn, ứng dụng nên đặt circuit breaker ở đúng client hoặc luồng gọi, sau đó cung cấp fallback phù hợp.

~~~java
@Service
public class ProductPageService {

    private final RecommendationClient recommendationClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ProductPageService(
            RecommendationClient recommendationClient,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.recommendationClient = recommendationClient;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductPage load(String productId) {
        Product product = loadCoreProduct(productId);

        List<Recommendation> recommendations =
                circuitBreakerFactory.create("recommendations").run(
                        () -> recommendationClient.findFor(productId),
                        error -> List.of()
                );

        return new ProductPage(product, recommendations);
    }
}
~~~

Các kiểu dữ liệu và phương thức trong ví dụ là minh họa. Trong ứng dụng thực tế, fallback có thể trả danh sách gợi ý cache gần nhất, hoặc danh sách rỗng nếu giao diện cho phép bỏ phần gợi ý. Phần dữ liệu cốt lõi vẫn được tải và trả về.

Khi circuit breaker chuyển OPEN, lời gọi gợi ý bị từ chối nhanh và fallback xử lý. Liveness vẫn phản ánh tiến trình product-api đang hoạt động. Readiness vẫn có thể thành công vì ứng dụng còn xử lý được trang sản phẩm mà không có gợi ý.

Fallback phải phù hợp với ngữ nghĩa của chức năng. Không dùng danh sách rỗng nếu danh sách rỗng có nghĩa nghiệp vụ là “không có sản phẩm phù hợp” và người dùng có thể hiểu nhầm đó là kết quả đã được xác nhận. Có thể bổ sung metadata cho biết phần gợi ý tạm thời không khả dụng.

## Không để health check tạo thêm tải lên phụ thuộc

Một lỗi thiết kế phổ biến là health indicator gọi trực tiếp dịch vụ bên ngoài mỗi lần Actuator nhận request health. Kubernetes có thể gọi probe liên tục trên mọi replica. Nếu mỗi probe gọi nhiều dịch vụ, số request kiểm tra có thể trở thành tải đáng kể, đặc biệt khi hệ thống đang suy giảm.

Nên áp dụng các nguyên tắc:

- Liveness chỉ kiểm tra trạng thái nội bộ, không gọi database, broker, Redis hoặc HTTP service tùy chọn.
- Readiness chỉ kiểm tra điều kiện thật sự cần để nhận traffic.
- Indicator phụ thuộc nên dùng dữ liệu trạng thái đã có, timeout ngắn và giới hạn tần suất nếu cần kiểm tra mạng.
- Không thực hiện retry dài trong health indicator.
- Không để health check chờ circuit breaker ở trạng thái HALF_OPEN hoặc chờ một request phụ thuộc hoàn tất.
- Giữ endpoint probe đơn giản, nhanh và có thể truy cập trên cổng phục vụ phù hợp.

Nếu cần kiểm tra phụ thuộc từ xa, nên thực hiện qua metrics, giám sát chủ động hoặc health group riêng. Một lần health check chậm không nên chiếm thread và làm chậm endpoint liveness.

## Theo dõi suy giảm mà không restart ứng dụng

Khi phụ thuộc tùy chọn gặp sự cố, nhóm vận hành cần nhận được tín hiệu rõ ràng dù liveness và readiness vẫn xanh. Có thể theo dõi:

- Số circuit breaker đang OPEN hoặc HALF_OPEN theo từng dependency.
- Failure rate, slow call rate và độ trễ lời gọi phụ thuộc.
- Số lời gọi bị từ chối nhanh.
- Tỷ lệ fallback và tỷ lệ request trả dữ liệu suy giảm.
- Số lần health group phụ thuộc báo DEGRADED.
- Tỷ lệ lỗi của endpoint cốt lõi so với endpoint phụ thuộc tùy chọn.

Không nên chỉ dựa vào màu xanh của liveness để kết luận toàn bộ chức năng đang khỏe. Liveness trả lời câu hỏi tiến trình có thể tiếp tục chạy hay không; metrics và health group phụ thuộc cung cấp góc nhìn về các tích hợp bên ngoài.

Cảnh báo nên phân biệt:
- **Process unhealthy:** liveness thất bại, cần điều tra tiến trình hoặc tài nguyên nội bộ.
- **Instance not ready:** ứng dụng chưa thể nhận traffic an toàn.
- **Dependency degraded:** một phụ thuộc lỗi hoặc circuit breaker OPEN, nhưng ứng dụng vẫn có thể phục vụ chức năng khác.
- **Fallback elevated:** ứng dụng tiếp tục phục vụ nhưng nhiều request đang nhận kết quả suy giảm.

## Kiểm thử hành vi probe khi phụ thuộc tùy chọn lỗi

Cần kiểm tra cả trạng thái probe lẫn hành vi nghiệp vụ. Có thể giả lập dịch vụ gợi ý trả 503, timeout hoặc không kết nối được, sau đó quan sát circuit breaker, fallback và health endpoint.

| Kịch bản | Liveness | Readiness | Hành vi mong đợi |
|---|---|---|---|
| Dịch vụ gợi ý hoạt động bình thường | UP | ACCEPTING_TRAFFIC | Trang sản phẩm có dữ liệu gợi ý. |
| Dịch vụ gợi ý trả 503 và circuit breaker OPEN | UP | ACCEPTING_TRAFFIC nếu chức năng cốt lõi vẫn phục vụ được | Fallback bỏ phần gợi ý hoặc dùng cache. |
| Dịch vụ email tùy chọn không khả dụng | UP | ACCEPTING_TRAFFIC | Request không cần email vẫn được xử lý; tác vụ email có chính sách riêng. |
| Cơ sở dữ liệu cốt lõi không khả dụng và app không thể phục vụ request | UP nếu tiến trình vẫn sống | REFUSING_TRAFFIC | Pod không nhận traffic; không restart chỉ vì database lỗi. |
| Tiến trình bị deadlock hoặc không thể phục vụ health endpoint | Có thể thất bại | Có thể thất bại | Kubelet có thể restart container khi liveness vượt ngưỡng. |
| Ứng dụng đang khởi động | Startup chưa thành công | Chưa được đánh giá | Startup probe trì hoãn liveness/readiness. |
| Circuit breaker phụ thuộc chuyển HALF_OPEN rồi CLOSED | UP | ACCEPTING_TRAFFIC | Các lời gọi thử phục hồi thành công; chức năng tùy chọn hoạt động trở lại. |

Trong kiểm thử tích hợp, xác nhận rằng lỗi của phụ thuộc không làm /livez thất bại. Đồng thời xác nhận /readyz chỉ thất bại khi ứng dụng thực sự không thể nhận traffic an toàn theo chính sách. Đừng chỉ kiểm tra status code của probe; hãy kiểm tra request nghiệp vụ vẫn phục vụ phần cốt lõi và fallback được gọi đúng.

## Quy trình thiết kế

1. Xác định chức năng cốt lõi và các phụ thuộc tùy chọn của từng luồng request.
2. Thiết kế liveness chỉ dựa trên khả năng hoạt động nội bộ của tiến trình.
3. Thiết kế readiness theo khả năng phục vụ traffic an toàn, chỉ xét phụ thuộc bắt buộc.
4. Dùng startup probe cho ứng dụng có thời gian khởi động dài.
5. Bật health groups của Spring Boot Actuator và công bố endpoint probe phù hợp.
6. Tách trạng thái phụ thuộc hoặc circuit breaker thành health group/metrics riêng.
7. Dùng circuit breaker và fallback tại client gọi phụ thuộc tùy chọn.
8. Không thực hiện lời gọi mạng chậm hoặc retry trong liveness/readiness handler.
9. Kiểm thử lỗi phụ thuộc, circuit breaker OPEN, fallback, readiness và liveness độc lập.
10. Thiết lập cảnh báo riêng cho process health, readiness, dependency degradation và fallback.

Liveness là tín hiệu về khả năng tiếp tục chạy của tiến trình; readiness là tín hiệu về khả năng nhận traffic; trạng thái của phụ thuộc là một tín hiệu vận hành riêng. Khi một dịch vụ tùy chọn lỗi, circuit breaker và fallback nên giới hạn tác động đến chức năng đó, còn probe tiếp tục phản ánh đúng tình trạng của ứng dụng. Cách tách biệt này tránh restart không cần thiết và giảm nguy cơ một sự cố bên ngoài lan thành gián đoạn toàn hệ thống.

