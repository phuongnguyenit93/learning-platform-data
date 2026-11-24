# Ngăn phép đo trùng khi framework đã tự động quan sát thao tác

Spring Boot và Micrometer có thể tự động quan sát nhiều hoạt động như HTTP request phía máy chủ. Ứng dụng cũng có thể bổ sung instrumentation bằng annotation như @Timed, @Counted hoặc @Observed và các aspect AOP tương ứng. Nếu cả hai lớp cùng đo một sự kiện với cùng mục đích, dữ liệu có thể bị ghi nhận hai lần hoặc dashboard có thể cộng hai meter đang mô tả cùng một tập sự kiện.

Để tránh trùng, trước khi thêm annotation cần xác định framework đã quan sát thao tác nào, ranh giới bắt đầu/kết thúc ở đâu và metric mới sẽ trả lời câu hỏi nào. Một HTTP request và một thao tác thanh toán bên trong request có thể được đo riêng vì chúng có ranh giới khác nhau. Nhưng nếu mục tiêu chỉ là đếm tổng số HTTP request, không nên vừa dùng meter tự động của framework vừa thêm một Counter annotation hoặc lời gọi increment cho chính request đó.

## Hai kiểu trùng cần phân biệt

Trùng instrumentation có thể xảy ra theo hai cách:

1. **Ghi cùng sự kiện nhiều lần:** một lần request hoàn tất làm tăng hai counter cùng ý nghĩa, ví dụ built-in HTTP observation đã đếm request nhưng controller lại gọi Counter.increment() cho cùng request.
2. **Đo chồng lấn cùng ranh giới:** hai meter khác tên cùng đo toàn bộ thời gian HTTP request, ví dụ http.server.requests và một @Timed đặt trên controller. Cả hai meter vẫn có thể hợp lệ về mặt kỹ thuật, nhưng nếu dashboard cộng số lượng hoặc so sánh như hai nhóm request độc lập thì kết quả bị hiểu sai.

Không phải mọi meter trên cùng một luồng đều là trùng. HTTP observation có thể đo toàn bộ request, trong khi một Timer riêng đo thời gian gọi payment provider. Hai phép đo này bổ sung góc nhìn nếu được đặt tên, gắn tag và giải thích theo đúng phạm vi.

| Tình huống | Đánh giá | Hướng xử lý |
|---|---|---|
| Built-in HTTP timer và @Timed cùng đặt trên controller để đo toàn bộ request | Chồng lấn ranh giới | Giữ built-in HTTP timer; bỏ annotation dư thừa |
| Built-in HTTP observation và @Counted trên controller cùng đếm request | Cùng sự kiện được đếm ở hai meter | Chọn một nguồn cho request count |
| @Observed và @Timed cùng bọc một service method với cùng mục tiêu latency | Hai instrumentation cùng quan sát một method | Chọn một cơ chế hoặc tách rõ mục tiêu và tên metric |
| HTTP timer và Timer cho riêng thao tác gọi payment provider | Ranh giới khác nhau | Giữ cả hai, đặt tên và diễn giải riêng |
| @Counted và Counter.increment() cùng chạy trong một method cho cùng event | Có thể tăng hai lần | Chỉ giữ annotation hoặc cập nhật thủ công |

## Framework đã tự động quan sát HTTP request

Khi ứng dụng Spring Boot dùng Actuator và web stack được hỗ trợ, Spring Boot tích hợp Observation để đo request phía máy chủ. Với Micrometer metrics registry, observation thường tạo meter http.server.requests dạng Timer.

Meter này đã ghi nhận thời lượng và số request hoàn tất cùng các chiều như method, URI template, status và outcome. Tập tag cụ thể phụ thuộc phiên bản Spring Boot và web stack. Có thể kiểm tra tại /actuator/metrics/http.server.requests hoặc endpoint exposition của backend.

Vì vậy, đoạn controller sau thường không cần thêm một @Timed chỉ để đo thời gian HTTP:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService orders;

    public OrderController(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    public OrderResponse get(@PathVariable String id) {
        return orders.find(id);
    }
}
~~~

Built-in observation bao quanh request ở tầng web. Nếu thêm @Timed vào get(...), một aspect có thể tạo thêm timer cho method controller. Hai timer có thể có tên khác nhau và không nhất thiết gây xung đột Meter.Id, nhưng chúng đo các khoảng thời gian gần như trùng nhau. Khi dashboard cộng count của cả hai hoặc coi chúng là hai loại request, số liệu bị nhân đôi về mặt diễn giải.

Nếu mục tiêu là đo riêng thời gian xử lý nghiệp vụ của OrderService, đặt instrumentation ở service method với tên riêng và diễn giải là thời gian nội bộ. Không cộng timer nghiệp vụ này với HTTP timer để tính tổng số request.

## Phân biệt Observation, Timed và Counted

Các cơ chế annotation có vai trò khác nhau:

| Cơ chế | Mục đích | Điều cần lưu ý |
|---|---|---|
| Built-in HTTP Observation | Tự động quan sát vòng đời request phía máy chủ | Đã có timer và tag HTTP khi web stack được hỗ trợ |
| @Observed | Tạo Observation quanh method hoặc operation | Có thể cung cấp metrics và tracing qua ObservationHandler |
| @Timed | Ghi nhận thời lượng method | Cần TimedAspect được đăng ký nếu dùng annotation AOP |
| @Counted | Đếm số lần method được gọi | Cần CountedAspect; tránh đếm lại cùng event bằng Counter thủ công |
| Timer/Counter API | Ghi nhận thủ công tại điểm nghiệp vụ | Phù hợp khi cần chọn chính xác ranh giới và điều kiện ghi nhận |

@Observed không đơn thuần là một Timer khác. Nó tạo Observation, có thể được xử lý bởi nhiều handler như metrics và tracing. Khi ObservationRegistry được cấu hình với metrics handler, Observation có thể tạo meter cho operation. Nếu @Observed và @Timed cùng bọc một method, TimedAspect tạo thêm một timer riêng cho gần như cùng khoảng thời gian. Với cùng mục tiêu latency, chọn một cơ chế. Nếu cần đo một đoạn con, giữ @Observed ở method ngoài và dùng Timer.record(...) quanh đoạn con bên trong.

Annotation không tự hoạt động chỉ vì có mặt trên method. Các aspect tương ứng phải được cấu hình và method phải được gọi qua proxy AOP. Kiểm tra cấu hình ứng dụng và phiên bản Micrometer/Spring Boot trước khi giả định annotation đang được xử lý.

## Chọn một nguồn đo cho HTTP request

Nếu built-in HTTP observation đã cung cấp request count, latency, status và URI template, dashboard HTTP nên dùng nguồn này làm số liệu chuẩn. Không cần thêm @Counted trên controller để đếm lại request.

Ví dụ không nên thêm:

~~~java
import java.util.List;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrderController {
    private final Counter requests;
    private final OrderService orderService;

    public OrderController(MeterRegistry registry, OrderService orderService) {
        this.requests = registry.counter("http.requests");
        this.orderService = orderService;
    }

    @GetMapping("/orders")
    public List<OrderResponse> list() {
        requests.increment();
        return orderService.findAll();
    }
}
~~~

Đoạn code trên chỉ đếm request đi qua method list(), trong khi built-in HTTP timer đã đếm request ở tầng web. Nếu dashboard cộng http.server.requests với http.requests, cùng một request xuất hiện trong cả hai nhóm. Ngoài ra, nếu method ném exception trước khi trả về, Counter vẫn đã tăng dù request có thể được phân loại là lỗi; điều này có thể đúng với metric attempt nhưng không phải metric success.

Thay vào đó, dùng http.server.requests cho số request tổng thể. Nếu cần đo số lần nghiệp vụ tìm danh sách được thực thi, hãy đặt tên thể hiện rõ nghiệp vụ như orders.search.executions và xác định đó là số lần gọi use case, có thể khác số request do retry nội bộ hoặc nhiều caller.

## Đo phần nghiệp vụ con bằng metric riêng

Một HTTP request có thể gọi nhiều thành phần. Đo riêng thao tác thanh toán có thể giúp xác định latency đến từ logic ứng dụng hay dependency:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {
    private final Timer paymentTimer;
    private final PaymentGateway gateway;

    public PaymentService(MeterRegistry registry, PaymentGateway gateway) {
        this.gateway = gateway;
        this.paymentTimer = Timer.builder("checkout.payment.duration")
                .description("Thời gian gọi cổng thanh toán")
                .tag("operation", "authorize")
                .register(registry);
    }

    public PaymentResult authorize(PaymentRequest request) {
        return paymentTimer.record(() -> gateway.authorize(request));
    }
}
~~~

Trong trường hợp này, http.server.requests đo toàn bộ request, còn checkout.payment.duration chỉ đo lời gọi gateway.authorize(...). Hai timer có thể được giữ cùng lúc vì chúng có phạm vi khác nhau. Dashboard nên đặt chúng cạnh nhau để so sánh, không cộng count hay duration như thể chúng là hai request độc lập.

Tag operation trong ví dụ có tập giá trị cố định. Không dùng orderId, customerId, requestId hoặc URL gateway có tham số làm tag.

## Tránh đếm trùng giữa @Counted và Counter.increment()

Nếu dùng @Counted, CountedAspect sẽ ghi nhận lần gọi method theo cấu hình annotation. Không thêm một Counter.increment() trong cùng method cho đúng sự kiện đó.

Ví dụ annotation:

~~~java
import io.micrometer.core.annotation.Counted;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    @Counted(value = "inventory.reservation.calls",
             description = "Số lần gọi use case giữ hàng")
    public Reservation reserve(ReservationCommand command) {
        return reservationRepository.reserve(command);
    }
}
~~~

Nếu aspect CountedAspect đã được đăng ký, mỗi lần lời gọi đi qua proxy sẽ được đếm. Đừng đồng thời viết:

~~~java
public Reservation reserve(ReservationCommand command) {
    reservationCalls.increment();
    return reservationRepository.reserve(command);
}
~~~

với cùng ý nghĩa và cùng đường thực thi. Chọn annotation khi muốn áp dụng chính sách đếm ở ranh giới method; chọn API Counter khi cần điều khiển chính xác nhánh nào được tính, chẳng hạn chỉ đếm sau commit hoặc chỉ đếm kết quả thành công.

Đặc biệt, xác định annotation đếm attempt hay success. @Counted trên method thường phản ánh lời gọi được aspect quan sát, không tự hiểu rằng giao dịch nghiệp vụ đã commit. Nếu cần đếm thành công sau commit, đặt increment tại event/listener AFTER_COMMIT hoặc cập nhật counter theo logic nghiệp vụ có kiểm soát.

## Tránh bọc cùng method bằng @Observed và @Timed

Ví dụ sau có thể tạo hai phép đo thời gian bao quanh cùng method:

~~~java
import io.micrometer.core.annotation.Timed;
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @Observed(name = "reports.generate")
    @Timed(value = "reports.generate.duration")
    public Report generate(ReportRequest request) {
        return reportGenerator.generate(request);
    }
}
~~~

Nếu cả ObservedAspect và TimedAspect đều hoạt động, method có thể được quan sát bởi hai aspect. Tên meter khác nhau nên registry có thể lưu cả hai, nhưng cả hai duration đều phản ánh gần như toàn bộ generate(...). Nếu mục tiêu là metrics latency và trace cho cùng operation, thường chỉ cần @Observed cùng ObservationRegistry được cấu hình metrics/tracing handlers; không cần thêm @Timed cho cùng phạm vi.

Nếu muốn Timer cho một đoạn con trong method, đặt nó ở method con hoặc dùng Timer.record(...) quanh đúng đoạn đó với tên thể hiện ranh giới. Đừng đặt annotation trên cùng method chỉ để tạo thêm một bản sao của latency.

## Cấu hình các aspect một cách có chủ đích

Micrometer cung cấp aspect cho một số annotation. Trong ứng dụng Spring AOP, cần đăng ký bean tương ứng; không tạo nhiều bean aspect cho cùng annotation:

Nếu dự án chưa có Spring AOP infrastructure, thêm starter:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-aop")
}
~~~

~~~java
import io.micrometer.core.aop.CountedAspect;
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsAopConfiguration {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }

    @Bean
    CountedAspect countedAspect(MeterRegistry registry) {
        return new CountedAspect(registry);
    }

    @Bean
    ObservedAspect observedAspect(ObservationRegistry observationRegistry) {
        return new ObservedAspect(observationRegistry);
    }
}
~~~

Đoạn cấu hình trên chỉ là ví dụ khi ứng dụng thực sự dùng cả ba annotation. Nếu chỉ dùng @Observed, không cần tạo TimedAspect và CountedAspect. Nếu chỉ dùng @Timed, chỉ đăng ký TimedAspect. Spring Boot có thể auto-configure một số thành phần tùy phiên bản và dependency; kiểm tra ApplicationContext để tránh tự khai báo thêm một aspect đã có.

Với Spring AOP proxy, thêm spring-boot-starter-aop nếu dự án chưa có AOP infrastructure. Proxy-based AOP thường chỉ chặn lời gọi đi qua proxy. Gọi một method được annotate từ method khác trong cùng object (self-invocation) có thể bỏ qua aspect. Method private hoặc final cũng có giới hạn proxy tùy loại proxy. Đây thường là nguyên nhân annotation không ghi nhận; không nên chữa bằng cách thêm một annotation hoặc aspect thứ hai.

## Đặt annotation ở đúng ranh giới

Một quy tắc thực tế là chọn một lớp sở hữu cho từng loại phép đo:

| Ranh giới | Nguồn đo ưu tiên | Ví dụ |
|---|---|---|
| Toàn bộ HTTP request | Built-in server Observation | http.server.requests |
| Thao tác nghiệp vụ độc lập | @Observed hoặc Timer API | checkout.payment |
| Số lần use case được gọi | @Counted hoặc Counter API | inventory.reservation.calls |
| Thời lượng dependency call | Timer API hoặc annotation trên method gateway chuyên biệt | payment.gateway.duration |
| Số tác vụ đang chạy | LongTaskTimer | reports.generation.active |
| Kết quả thành công sau transaction commit | Counter API tại điểm commit | orders.created |

Không đặt annotation một cách máy móc ở controller, service, repository và client cho cùng một metric. Mỗi tầng có thể có phép đo riêng, nhưng tên và mô tả phải cho biết tầng đó đang đo điều gì.

Với annotation trên interface và implementation, hãy xác minh aspect/proxy đọc annotation theo quy tắc của phiên bản đang dùng. Cách an toàn là đặt annotation tại method implementation được Spring proxy và viết integration test xác nhận meter thực sự được tạo.

## Kiểm thử số lần đo để phát hiện trùng

Unit test với SimpleMeterRegistry giúp xác minh Counter API hoặc Timer API thủ công. Để kiểm tra annotation AOP, cần khởi tạo Spring context có aspect và gọi bean qua proxy. Ví dụ với @Counted:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class CountedServiceTest {
    @Autowired
    InventoryService inventoryService;

    @Autowired
    MeterRegistry registry;

    @Test
    void oneInvocationCreatesOneCountObservation() {
        Counter before = registry.find("inventory.reservation.calls").counter();
        double initialCount = before == null ? 0.0 : before.count();

        inventoryService.reserve(new ReservationCommand("sku-1", 1));

        Counter counter = registry.find("inventory.reservation.calls")
                .counter();

        assertThat(counter).isNotNull();
        assertThat(counter.count()).isEqualTo(initialCount + 1.0);
    }
}
~~~

Test này giả định không có invocation nền hoặc lời gọi đồng thời khác trong lúc đo. Vì Spring test context có thể được dùng lại giữa các test, việc lấy count ban đầu rồi so sánh delta giúp tránh phụ thuộc vào giá trị tuyệt đối của counter.

Để phát hiện trùng giữa built-in HTTP observation và annotation, gọi endpoint qua HTTP thật rồi kiểm tra:

1. Count của http.server.requests tăng đúng một lần cho request.
2. Không xuất hiện meter phụ có cùng ý nghĩa do annotation thừa, hoặc nếu có thì được xác định rõ là metric của một ranh giới khác.
3. Dashboard không cộng meter tổng request với meter method-level thành một tổng giả.

Test AOP cũng nên kiểm tra self-invocation nếu code có gọi nội bộ method annotate. Kiểm tra cả success và exception để xác định annotation đếm mọi invocation hay chỉ các kết quả thành công theo cấu hình aspect.

## Chẩn đoán khi metric tăng gấp đôi

Khi dashboard hiển thị count hoặc latency cao gấp đôi, đi theo thứ tự:

1. Tìm tên meter và toàn bộ tag để xác định có một series hay nhiều series.
2. Tìm các điểm ghi nhận thủ công như increment(), record(...) và các annotation trên cùng đường gọi.
3. Kiểm tra framework đã tự tạo Observation hoặc meter built-in nào.
4. Kiểm tra TimedAspect, CountedAspect, ObservedAspect có bị đăng ký trùng bean hay không.
5. Kiểm tra một method có bị bọc bởi nhiều aspect hoặc decorator.
6. So sánh ranh giới thời gian: HTTP request, service method, repository call hay dependency call.
7. Kiểm tra dashboard có đang cộng các meter khác tên nhưng cùng tập sự kiện không.
8. Viết test xác nhận một sự kiện nghiệp vụ tạo đúng số observation dự kiến.

Nếu meter cùng tên và tag được đăng ký nhiều lần, Micrometer thường trả về meter tương ứng đã có trong registry; việc đăng ký lại không có nghĩa là mỗi lần tạo builder sẽ tạo một chuỗi độc lập. Vấn đề đếm trùng thường nằm ở việc nhiều đường code cùng cập nhật meter hoặc nhiều meter khác tên cùng mô tả một sự kiện.

## Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| HTTP request count lớn hơn lưu lượng thực | Built-in HTTP metric và @Counted/Counter thủ công cùng đếm request | Dùng built-in HTTP meter làm nguồn chuẩn |
| Latency controller gần giống HTTP latency nhưng có hai series | @Timed chồng lên server Observation | Bỏ @Timed nếu không có mục tiêu riêng |
| @Timed không tạo meter | Thiếu TimedAspect hoặc method không đi qua proxy | Kiểm tra bean aspect và đường gọi qua proxy |
| @Counted tăng hai lần | CountedAspect và increment() cùng ghi một sự kiện | Chọn một cơ chế ghi nhận |
| @Observed và @Timed xuất hai duration tương tự | Hai aspect cùng bọc method | Chọn Observation hoặc Timer cho cùng ranh giới |
| Annotation không hoạt động khi gọi nội bộ cùng class | Self-invocation bỏ qua Spring proxy | Tách bean hoặc gọi qua proxy phù hợp |
| Metric đếm attempt nhưng dashboard gọi là success | Annotation đếm lời gọi method, không gắn với commit | Đổi tên/ý nghĩa hoặc ghi Counter sau commit |
| Hai meter khác tên bị cộng vào một panel | Dashboard gộp các phạm vi khác nhau | Phân nhóm theo ranh giới và chỉ cộng metric tương thích |

## Checklist triển khai

- [ ] Đã kiểm tra framework có tự động tạo Observation hoặc meter cho thao tác đó chưa.
- [ ] Mỗi sự kiện có một nguồn sở hữu cho phép đếm tổng thể.
- [ ] Không dùng @Counted và Counter.increment() cùng đếm một event.
- [ ] Không dùng @Timed chồng lên built-in HTTP timer nếu cùng mục tiêu.
- [ ] Không bọc cùng method bằng @Observed và @Timed nếu hai phép đo không có mục tiêu riêng.
- [ ] Metric cho thao tác con có tên và ranh giới khác metric của request tổng thể.
- [ ] Aspect cần thiết được đăng ký đúng một lần và AOP proxy thực sự chặn lời gọi.
- [ ] Đã xem xét self-invocation, method visibility và proxy type.
- [ ] Tag của annotation có cardinality thấp và không chứa ID từng request.
- [ ] Integration test xác nhận một invocation tạo đúng số observation mong đợi.
- [ ] Dashboard không cộng các meter khác phạm vi như cùng một tập sự kiện.

Ngăn phép đo trùng bắt đầu bằng việc lập bản đồ các ranh giới đã được framework quan sát. Giữ built-in instrumentation cho hoạt động tổng thể, chỉ thêm annotation hoặc API thủ công khi cần đo một operation riêng, và kiểm thử số observation cho mỗi sự kiện. Khi tên metric phản ánh đúng ranh giới, dữ liệu có thể được so sánh mà không bị đếm lặp hoặc hiểu nhầm.
