# Đánh giá tích hợp Sentinel hoặc hiện thực bên ngoài theo artifact thực tế

Spring Cloud CircuitBreaker cung cấp API chung để ứng dụng gọi circuit breaker thông qua một thư viện hiện thực. Khi cân nhắc Sentinel hoặc một thư viện bảo vệ dịch vụ khác, cần xác định rõ artifact nào thực sự có trong dependency của dự án và artifact đó cung cấp loại tích hợp nào. Một thư viện có khả năng mở mạch không đồng nghĩa nó đã có provider tương thích với `CircuitBreakerFactory` hoặc `ReactiveCircuitBreakerFactory`.

Với module **SPRING_CLOUD_CIRCUIT_BREAKER**, mục tiêu là đánh giá một lựa chọn thay thế dựa trên dependency tree, BOM, auto-configuration và API thực tế. Sau khi xác minh, nhóm phát triển có thể dùng tích hợp có sẵn, gọi trực tiếp API của thư viện hoặc xây adapter riêng cho Spring Cloud CircuitBreaker. Không nên chọn giải pháp chỉ dựa trên tên dependency hoặc một ví dụ thuộc phiên bản khác.

## 1. Phân biệt thư viện bảo vệ và provider Spring Cloud CircuitBreaker

Có ba lớp cần phân biệt:

1. **Engine bảo vệ:** thư viện thực hiện thuật toán circuit breaker, rate limiting, flow control hoặc bulkhead. Ví dụ Sentinel core cung cấp các API và rule để kiểm soát tài nguyên.
2. **Tích hợp framework:** artifact kết nối engine với một thành phần Spring cụ thể, chẳng hạn annotation AOP, Spring Web, WebFlux, Gateway hoặc Feign.
3. **Provider Spring Cloud CircuitBreaker:** adapter triển khai hợp đồng factory của Spring Cloud CircuitBreaker, cho phép ứng dụng tạo breaker qua API chung như `CircuitBreakerFactory` hoặc `ReactiveCircuitBreakerFactory`.

Ba lớp này có thể nằm trong cùng một starter hoặc ở các artifact khác nhau. Một starter Sentinel có thể tự động cấu hình filter hoặc annotation interceptor nhưng chưa chắc cung cấp một bean `CircuitBreakerFactory`. Ngược lại, một provider Spring Cloud CircuitBreaker có thể cung cấp factory nhưng không bao gồm mọi tính năng đặc thù của engine.

| Điều tìm thấy trong dependency | Có thể kết luận | Chưa thể kết luận |
|---|---|---|
| Chỉ có core artifact của Sentinel | Engine Sentinel đã có trên classpath. | Chưa chứng minh có Spring integration hoặc provider Spring Cloud CircuitBreaker. |
| Có Spring Cloud Alibaba Sentinel starter | Dự án có một lớp tích hợp Sentinel với Spring Cloud Alibaba theo phiên bản starter. | Chưa chứng minh starter triển khai `CircuitBreakerFactory` của Spring Cloud CircuitBreaker. |
| Có tích hợp Sentinel cho Feign, Gateway hoặc WebFlux | Có thể bảo vệ một ranh giới framework cụ thể. | Chưa chứng minh mọi lời gọi qua `CircuitBreakerFactory` đều dùng Sentinel. |
| Có artifact provider và auto-configuration tạo factory tương thích | Có cơ sở để dùng API chung nếu phiên bản tương thích. | Vẫn cần xác minh bean, cấu hình, fallback, reactive và metrics tại runtime. |
| Có thư viện nội bộ hoặc adapter riêng | Có thể tồn tại tích hợp ngoài dự án Spring Cloud chính. | Cần kiểm tra hợp đồng API, phiên bản và vòng đời bảo trì của adapter đó. |

Vì vậy, câu hỏi đầu tiên không phải “Sentinel có circuit breaker không?” mà là “artifact nào đang cung cấp cơ chế bảo vệ, artifact nào nối nó với Spring, và có provider nào thực sự thực hiện API factory mà ứng dụng định sử dụng không?”.

## 2. Kiểm tra artifact thực tế trong dự án

Trước khi thêm dependency mới, hãy kiểm tra phiên bản Spring Boot, Spring Cloud release train và dependency management hiện tại. Các thành phần cần được quản lý theo BOM tương thích; không tự ghép một phiên bản Spring Cloud Alibaba, Spring Cloud CircuitBreaker và Spring Boot chỉ vì chúng có thể tải xuống cùng lúc.

Với Maven, xem dependency tree của các nhóm liên quan:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud,com.alibaba.cloud,com.alibaba.csp,io.github.resilience4j
```

Kiểm tra dependency management đã áp dụng:

```bash
mvn help:effective-pom
```

Với Gradle, có thể xem runtime classpath:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm chính xác các thành phần như:

| Nhóm artifact | Điều cần xác minh |
|---|---|
| `org.springframework.cloud` | Có starter Spring Cloud CircuitBreaker và provider nào được kéo vào? |
| `com.alibaba.cloud` | Có starter Spring Cloud Alibaba Sentinel hoặc adapter Spring Cloud Alibaba nào? |
| `com.alibaba.csp` | Có Sentinel core và các module tích hợp cần thiết không? |
| `io.github.resilience4j` | Có Resilience4j modules nào được kéo vào trực tiếp hoặc transitively? |
| Artifact nội bộ/nhà cung cấp khác | Có module adapter, phiên bản, nguồn phát hành và tài liệu tương ứng không? |

Đừng chỉ kiểm tra tên artifact trong `pom.xml`. Dependency có thể được kéo vào gián tiếp, bị loại trừ, bị đổi phiên bản bởi BOM hoặc không có mặt ở runtime do scope. Hãy kiểm tra cả version thực tế và đường dẫn dependency dẫn đến artifact đó.

## 3. Xác minh có provider factory hay không

Nếu mục tiêu là dùng Spring Cloud CircuitBreaker API chung, hãy kiểm tra provider có cung cấp và đăng ký bean phù hợp không. Các dấu hiệu cần tìm:

- Có implementation của `CircuitBreakerFactory` hoặc lớp factory mở rộng abstraction tương ứng của release train đang dùng.
- Nếu cần reactive, có implementation của `ReactiveCircuitBreakerFactory` và tích hợp với Reactor phù hợp.
- Có auto-configuration hoặc cấu hình Spring tạo bean factory khi starter được bật.
- Factory có thể tạo breaker theo ID và, nếu hợp đồng phiên bản hỗ trợ, theo group name.
- Có cách cấu hình mặc định và cấu hình riêng theo ID tương thích với cơ chế `Customizer`.
- Fallback nhận và truyền nguyên nhân lỗi đúng hợp đồng.
- Có cách quan sát trạng thái, events và metrics của engine bên dưới.

Có thể kiểm tra classpath và auto-configuration bằng IDE, dependency analyzer hoặc xem nội dung JAR của đúng artifact. Với Spring Boot hiện đại, metadata auto-configuration thường được khai báo trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; một số thư viện cũ dùng cơ chế đăng ký khác. Việc một JAR chứa lớp có tên `CircuitBreaker` không đủ chứng minh nó là provider cho Spring Cloud CircuitBreaker.

Khi ứng dụng khởi động, kiểm tra bean thực tế bằng Spring Boot Actuator `/actuator/beans` nếu endpoint được expose và bảo vệ phù hợp, hoặc dùng một integration test kiểm tra bean factory có thể inject. Nếu factory không tồn tại, không giả định Spring sẽ tự chuyển sang Sentinel chỉ vì Sentinel starter có trên classpath.

## 4. Sentinel cung cấp những khả năng nào?

Sentinel là một hệ thống bảo vệ và điều khiển traffic. Tùy artifact và phiên bản được sử dụng, các khả năng thường được quan tâm gồm:

- **Flow control:** giới hạn lưu lượng theo resource, số request hoặc các chiến lược điều khiển được hỗ trợ.
- **Circuit breaking/degradation:** đánh giá tỷ lệ lỗi, số lỗi hoặc tỷ lệ request chậm trong cửa sổ thống kê để ngăn tiếp tục gọi một resource đang suy giảm.
- **System protection:** bảo vệ ứng dụng theo một số tín hiệu tải hệ thống nếu cấu hình và runtime hỗ trợ.
- **Resource definition:** đặt tên resource để áp dụng rule cho một điểm gọi hoặc một nhóm thao tác.
- **Block handling:** xử lý trường hợp request bị Sentinel chặn, thường qua `BlockException` hoặc handler tương ứng của integration.

Sentinel dùng khái niệm resource và rule. Tên resource cần ổn định để rule được áp dụng đúng nơi. Một resource có thể được bảo vệ bởi nhiều loại rule, chẳng hạn flow control và degradation. Do đó, khi chuyển từ Resilience4j sang Sentinel, không nên chỉ đổi tên thư viện mà cần ánh xạ lại ý nghĩa của từng rule.

Các loại degradation rule và tham số hỗ trợ có thể thay đổi theo phiên bản Sentinel. Hãy kiểm tra artifact thực tế để biết có hỗ trợ chiến lược slow request ratio, exception ratio hoặc exception count hay không, cùng các giá trị như thời gian thống kê, ngưỡng tối thiểu và thời gian mở mạch. Không giả định cửa sổ, thuật toán và cách chuyển trạng thái hoàn toàn giống Resilience4j.

## 5. Spring Cloud Alibaba Sentinel không tự động đồng nghĩa provider Spring Cloud CircuitBreaker

Trong hệ sinh thái Spring Cloud Alibaba, starter Sentinel có thể tích hợp Sentinel với các thành phần Spring Cloud theo release train tương ứng. Một ứng dụng có thể dùng annotation `@SentinelResource`, filter hoặc tích hợp cho Feign/Gateway nếu artifact và phiên bản đó cung cấp.

Ví dụ sử dụng annotation để bảo vệ một resource:

```java
import com.alibaba.csp.sentinel.annotation.SentinelResource;
import com.alibaba.csp.sentinel.slots.block.BlockException;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    @SentinelResource(
        value = "inventory:read",
        blockHandler = "handleBlocked",
        fallback = "handleFailure"
    )
    public Stock getStock(String sku) {
        return inventoryClient.getStock(sku);
    }

    public Stock handleBlocked(String sku, BlockException error) {
        return Stock.temporarilyUnavailable(sku);
    }

    public Stock handleFailure(String sku, Throwable error) {
        return Stock.unavailable(sku);
    }
}
```

Trong ví dụ, `inventory:read` là tên resource. `blockHandler` xử lý trường hợp Sentinel chặn request theo rule; `fallback` xử lý exception phát sinh trong phương thức được bảo vệ theo cơ chế annotation. Chữ ký handler phải tuân thủ quy tắc của phiên bản Sentinel đang dùng, thường nhận các tham số gốc và thêm `BlockException` cho block handler. Cần có dependency AOP/integration tương ứng để annotation được thực thi; chỉ thêm annotation vào mã không bảo đảm interceptor đã hoạt động.

Ví dụ này chứng minh một điểm gọi có thể được bảo vệ trực tiếp bằng Sentinel integration. Nó **không chứng minh** ứng dụng có thể inject `CircuitBreakerFactory` và dùng Sentinel như một provider Spring Cloud CircuitBreaker. Hai cách tích hợp có API và vòng đời khác nhau.

## 6. Đánh giá Sentinel cho Feign, Gateway và reactive

Tích hợp ở từng ranh giới cần được xác minh riêng. Ví dụ, một release của Spring Cloud Alibaba có thể cung cấp tích hợp Sentinel cho Feign hoặc Gateway, nhưng điều đó không đồng nghĩa các lời gọi service nội bộ, `WebClient` và Reactor publisher đều được bảo vệ theo cùng cách.

| Ranh giới | Điều cần xác minh trong artifact/version |
|---|---|
| `@SentinelResource` | AOP aspect có được cấu hình và resource được tạo đúng không? |
| OpenFeign | Có tích hợp Feign/Sentinel trong starter không; thuộc tính bật tính năng và fallback factory là gì? |
| Spring Cloud Gateway | Có filter hoặc adapter tương thích với phiên bản Gateway đang dùng không; rule áp dụng theo route hay resource nào? |
| Spring WebFlux | Có filter hoặc reactive integration không; cancellation và tín hiệu lỗi được xử lý thế nào? |
| Reactor `Mono`/`Flux` | Có operator reactive bảo vệ subscription đúng vòng đời không; có chặn event loop không? |
| HTTP client trực tiếp | Có interceptor hoặc decorator tương thích với client thực tế không? |

Đặc biệt với reactive, không giả định annotation đồng bộ sẽ tự động bao phủ toàn bộ vòng đời publisher. Nếu integration chỉ bao quanh lúc tạo publisher thay vì lúc subscribe và kết thúc, thời điểm giữ permit, ghi nhận lỗi và giải phóng tài nguyên có thể sai. Cần dùng adapter/operator reactive được tài liệu của artifact hỗ trợ và kiểm thử `onError`, `onComplete`, cancellation cùng nhiều subscription.

Không gọi API Sentinel đồng bộ có khả năng chờ hoặc block trực tiếp trên Reactor event loop. Nếu cần bảo vệ tác vụ blocking, hãy chuyển tác vụ sang scheduler phù hợp và giới hạn concurrency; nếu cần bảo vệ luồng reactive, dùng tích hợp reactive thực sự.

## 7. Ánh xạ khái niệm giữa Resilience4j và Sentinel

Hai thư viện có thể cùng giải quyết một số vấn đề nhưng mô hình cấu hình không giống nhau hoàn toàn.

| Nhu cầu | Resilience4j | Sentinel |
|---|---|---|
| Nhận diện điểm được bảo vệ | Circuit breaker ID | Resource name |
| Giới hạn số lời gọi đồng thời | Bulkhead module | Có thể cần cơ chế flow/concurrency hoặc giới hạn ở tầng khác tùy integration; không xem flow rule là tương đương hoàn toàn với bulkhead. |
| Ngăn gọi khi phụ thuộc suy giảm | CircuitBreaker state và sliding window | Degrade/circuit-breaking rule và state machine của Sentinel. |
| Giới hạn tốc độ request | RateLimiter | Flow control rule. |
| Xử lý request bị chặn | `CallNotPermittedException` hoặc exception của policy khác | `BlockException` hoặc handler của integration. |
| Retry | Resilience4j Retry | Thường cần phối hợp retry ở client/framework hoặc chính sách riêng; không mặc định coi retry là một phần của degradation rule. |
| Timeout | TimeLimiter và timeout ở client | Cần xác minh integration và timeout của client; Sentinel degradation theo slow request không tự thay thế timeout mạng. |
| Metrics/events | Micrometer integration và event publisher | Sentinel metrics, dashboard, datasource hoặc integration tương ứng. |

Không nên ánh xạ máy móc `failureRateThreshold` thành một tham số Sentinel chỉ vì cả hai đều là phần trăm. Cần xem chiến lược rule, số mẫu tối thiểu, thời gian thống kê, thời gian mở mạch và cách đánh giá request chậm của phiên bản thực tế.

## 8. Khi nào nên dùng Sentinel trực tiếp?

Tích hợp Sentinel trực tiếp có thể phù hợp khi ứng dụng đã chuẩn hóa resource name và rule của Sentinel, cần flow control cùng degradation trên một resource, hoặc đã sử dụng dashboard/dynamic rule datasource của Sentinel trong hệ thống.

Trong trường hợp đó, có thể giữ API Sentinel ở ranh giới service hoặc framework được hỗ trợ. Hãy tổ chức resource name ổn định, phân biệt block handler với fallback nghiệp vụ, và ghi nhận metrics riêng cho request bị chặn với exception từ dependency.

Không cần ép Sentinel vào `CircuitBreakerFactory` nếu ứng dụng không có nhu cầu dùng abstraction đó. Dùng trực tiếp API của engine có thể rõ ràng hơn khi tính năng Sentinel-specific là yêu cầu chính. Tuy nhiên, mã nghiệp vụ sẽ phụ thuộc nhiều hơn vào Sentinel và việc thay engine sau này có thể cần thay đổi adapter hoặc service boundary.

## 9. Khi nào cần viết adapter cho Spring Cloud CircuitBreaker?

Nếu ứng dụng muốn giữ API chung của Spring Cloud CircuitBreaker nhưng provider cần dùng Sentinel hoặc một engine bên ngoài, có thể viết adapter. Adapter phải chuyển đổi hợp đồng của Spring sang API của engine và ngược lại.

Một adapter cần xử lý ít nhất các phần sau:

1. **Factory:** triển khai factory imperative; nếu ứng dụng reactive, triển khai factory reactive riêng với semantics không blocking.
2. **Định danh:** ánh xạ `id` và `groupName` sang resource/rule key của engine; tránh tạo ID không ổn định theo request.
3. **Cấu hình:** hỗ trợ cấu hình mặc định và cấu hình riêng theo ID theo hợp đồng của release train Spring Cloud đang dùng.
4. **Supplier:** chỉ thực thi supplier khi engine cấp quyền; giải phóng entry/permit đúng vòng đời khi supplier hoàn tất, lỗi hoặc bị hủy.
5. **Exception mapping:** phân biệt lời gọi bị chặn với exception phát sinh từ supplier; không chuyển mọi exception thành cùng một loại lỗi.
6. **Fallback:** chuyển đúng nguyên nhân đến fallback và không làm mất lỗi gốc nếu fallback tiếp tục thất bại.
7. **Reactive lifecycle:** gắn quyền bảo vệ với subscription, terminal signal và cancellation; không block event loop.
8. **Observability:** cung cấp trạng thái, metrics và events đủ để vận hành; xác định cách ánh xạ các trạng thái đặc thù của engine.
9. **Lifecycle:** quản lý registry, listener, rule refresh và shutdown; tránh tạo listener hoặc engine instance mới mỗi request.

Các kiểu generic, lớp base và hook mở rộng của Spring Cloud CircuitBreaker có thể thay đổi theo release train. Khi triển khai adapter, hãy đọc API của đúng dependency đang dùng và implement interface/abstract class tương ứng; không sao chép skeleton từ một phiên bản khác mà chưa kiểm tra chữ ký.

## 10. Exception mapping là ranh giới quan trọng

Adapter phải giữ được sự khác biệt giữa:

- **Rejection:** engine từ chối trước khi supplier chạy vì circuit breaker đang mở, flow rule vượt ngưỡng hoặc không còn sức chứa.
- **Execution failure:** supplier đã chạy và phát sinh timeout, lỗi kết nối hoặc exception từ dependency.
- **Ignored/business outcome:** exception được phân loại là không ảnh hưởng trạng thái sức khỏe của dependency.

Nếu adapter chuyển mọi `BlockException` thành một exception chung rồi tính nó như lỗi thực thi của dependency, failure rate có thể tăng do chính sách chặn của Sentinel. Ngược lại, nếu chuyển timeout từ supplier thành rejection, nhóm vận hành sẽ không biết dependency đã nhận request và thất bại.

Khi ánh xạ rejection sang `CallNotPermittedException`, chỉ làm vậy nếu ngữ nghĩa tương ứng với lời gọi bị circuit breaker từ chối và phù hợp với hợp đồng Spring Cloud CircuitBreaker. Flow control rejection và bulkhead full có thể có ý nghĩa khác nhau; nếu gộp chúng, hãy giữ nguyên nguyên nhân gốc trong cause hoặc metadata để fallback và metrics có thể phân biệt.

Fallback nhận `Throwable` nên cần kiểm tra loại nguyên nhân. Không retry nóng một rejection; không báo thành công giả cho thao tác ghi; và nếu fallback thất bại, giữ cả lỗi ban đầu lẫn lỗi fallback theo một quy ước exception nhất quán.

## 11. Không chạy hai circuit breaker cho cùng một lời gọi nếu không có chủ đích

Một lỗi cấu hình thường gặp là cùng một lời gọi Feign hoặc HTTP client vừa bị Sentinel bảo vệ, vừa bị Spring Cloud CircuitBreaker/Resilience4j bọc. Khi đó hai engine có thể có hai cửa sổ, hai ngưỡng và hai trạng thái độc lập.

Hệ quả có thể gồm:

- Một engine từ chối request trước khi engine còn lại có cơ hội ghi nhận kết quả.
- Fallback bị gọi nhiều tầng hoặc nguyên nhân lỗi bị thay đổi.
- Metrics báo số lần gọi, lỗi và rejection không khớp nhau.
- Retry của một lớp liên tục đụng vào circuit breaker đang mở ở lớp khác.
- Khó xác định engine nào đang quyết định ngừng traffic.

Nếu thực sự cần nhiều lớp bảo vệ, hãy xác định vai trò riêng: ví dụ Sentinel flow control ở ingress để giới hạn lưu lượng toàn route và circuit breaker ở service client để theo dõi sức khỏe một dependency. Đặt ranh giới khác nhau, định nghĩa rõ thứ tự và kiểm thử số request thực tế đến dependency. Tránh đặt hai circuit breaker tương đương quanh cùng một supplier chỉ vì cả hai starter đã có trong classpath.

## 12. Đánh giá một artifact ngoài Sentinel

Các thư viện khác có thể cung cấp circuit breaker hoặc bulkhead riêng. Trước khi dùng một artifact bên ngoài, đánh giá theo các câu hỏi:

| Tiêu chí | Câu hỏi kiểm tra |
|---|---|
| Nguồn và bảo trì | Artifact do ai phát hành, còn được bảo trì và có chính sách phát hành rõ ràng không? |
| Tương thích | Phiên bản có tương thích với Java, Spring Boot, Spring Cloud và Jakarta/Servlet stack của dự án không? |
| API | Có API imperative, reactive hoặc cả hai? Có hỗ trợ cancellation không? |
| Spring integration | Có starter/auto-configuration hay chỉ có core library? |
| Factory provider | Có triển khai `CircuitBreakerFactory` hoặc cần adapter nội bộ? |
| Rule semantics | Ngưỡng, sliding window, minimum calls, slow call và HALF_OPEN được định nghĩa thế nào? |
| Failure classification | Có phân biệt exception được ghi nhận, ignored và request bị từ chối không? |
| Fallback | Có hỗ trợ fallback hoặc cho phép tích hợp fallback theo hợp đồng ứng dụng không? |
| Timeout/bulkhead/retry | Có module tương ứng hay cần phối hợp client và thư viện khác? |
| Observability | Có metrics, events, health indicator, dashboard và khả năng gắn resource ID không? |
| Configuration | Có hỗ trợ cấu hình bên ngoài, refresh rule và nhiều môi trường không? |
| Testing | Có thể kiểm thử trạng thái, thời gian, concurrency và hành vi khi shutdown không? |

Không chọn thư viện chỉ vì có một annotation dễ dùng. Cần tính cả khả năng vận hành, quan sát, cập nhật rule, tương thích phiên bản và chi phí bảo trì adapter.

## 13. Quy trình xác minh trước khi quyết định

Có thể thực hiện theo trình tự:

1. Ghi nhận Spring Boot, Spring Cloud release train và Java version đang dùng.
2. Xuất dependency tree và effective POM/runtime classpath để xác định artifact cùng phiên bản thực tế.
3. Kiểm tra artifact có phải core engine, Spring integration hay provider factory.
4. Kiểm tra auto-configuration và bean được tạo khi ứng dụng khởi động.
5. Nếu dùng Sentinel trực tiếp, xác minh resource, rule, block handler và integration cho đúng ranh giới cần bảo vệ.
6. Nếu dùng Spring Cloud CircuitBreaker API, xác minh có provider tương thích hoặc ước lượng phạm vi adapter cần viết.
7. Kiểm tra exception mapping, fallback, timeout, reactive lifecycle và metrics.
8. Kiểm thử lỗi từ supplier, rejection, ignored exception, phục hồi và shutdown.
9. Ghi rõ engine nào là nguồn quyết định duy nhất cho mỗi ranh giới bảo vệ.

## 14. Kịch bản kiểm thử chấp nhận tích hợp

Một tích hợp chỉ nên được xem là sẵn sàng khi kiểm thử chứng minh đúng hành vi ở runtime, không chỉ vì ứng dụng khởi động thành công.

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Dependency hoạt động bình thường | Supplier chạy, kết quả thành công được ghi nhận đúng một lần. |
| Dependency timeout hoặc ném lỗi | Supplier đã chạy; lỗi được phân loại và ghi nhận theo rule. |
| Circuit breaker mở hoặc Sentinel chặn resource | Supplier không chạy; rejection được phân biệt với lỗi thực thi. |
| Fallback thành công | Caller nhận kết quả dự phòng có ý nghĩa nghiệp vụ. |
| Fallback thất bại | Lỗi chính và lỗi fallback đều có thể truy vết. |
| Đủ điều kiện phục hồi | Engine cho phép thăm dò hoặc đóng lại theo state machine của nó. |
| Lưu lượng vượt giới hạn | Flow control/bulkhead từ chối theo chính sách và không làm cạn tài nguyên caller. |
| Nhiều request đồng thời | Concurrency, queue và số request đến dependency nằm trong giới hạn. |
| Reactive cancellation | Tài nguyên/permit được giải phóng đúng và event loop không bị block. |
| Rule refresh hoặc shutdown | Listener, registry và kết nối quản trị được cập nhật/đóng đúng vòng đời. |

## 15. Cách đưa ra quyết định

Chọn **Sentinel trực tiếp** khi artifact thực tế cung cấp đúng integration cho resource và ranh giới cần bảo vệ, đồng thời nhóm phát triển chấp nhận dùng API/rule của Sentinel. Chọn **provider Spring Cloud CircuitBreaker có sẵn** khi dependency tree và auto-configuration chứng minh provider tương thích với release train của dự án. Chọn **adapter ngoài** khi cần giữ API factory chung nhưng artifact engine chỉ cung cấp core hoặc integration ở tầng khác.

Nếu không tìm thấy provider factory trong artifact, hãy ghi nhận rõ rằng Sentinel đang được tích hợp qua annotation, filter, Feign hoặc API trực tiếp; không mô tả nó như provider Spring Cloud CircuitBreaker. Nếu cần adapter, bắt đầu bằng một ranh giới nhỏ, giữ nguyên semantics rejection và execution failure, rồi mở rộng sang reactive và metrics sau khi có kiểm thử.

Với mọi lựa chọn, chỉ một chính sách circuit breaker nên chịu trách nhiệm cho mỗi lời gọi phụ thuộc cụ thể, trừ khi các lớp bảo vệ có vai trò tách biệt được thiết kế rõ. Kiểm tra artifact và phiên bản thực tế, xác minh bean cùng hành vi runtime, rồi mới quyết định cách tích hợp. Cách đánh giá này giúp ứng dụng Spring Cloud CircuitBreaker dùng Sentinel hoặc một hiện thực bên ngoài mà không dựa vào giả định sai về starter, factory hay khả năng reactive.
