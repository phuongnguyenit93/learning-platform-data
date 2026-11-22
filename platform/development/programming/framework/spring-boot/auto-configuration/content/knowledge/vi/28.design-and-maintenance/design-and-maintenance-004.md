# Không dùng thứ tự cấu hình để che giấu vòng phụ thuộc trong thiết kế Spring Boot

## 1. Vấn đề cần giải quyết

Khi một ứng dụng Spring Boot có hai bean phụ thuộc lẫn nhau, việc thay đổi thứ tự auto-configuration thường chỉ làm thay đổi thời điểm Spring đăng ký bean definitions. Nó không loại bỏ quan hệ phụ thuộc giữa hai object.

Ví dụ:
- `OrderService` cần `PaymentService` để thanh toán đơn hàng.
- `PaymentService` lại cần `OrderService` để cập nhật trạng thái đơn hàng.

Đây là một vòng phụ thuộc trong thiết kế. Nếu cả hai dùng constructor injection, Spring không thể tạo bean nào trước vì mỗi constructor cần bean còn lại. Ứng dụng có thể thất bại với `BeanCurrentlyInCreationException` hoặc một `UnsatisfiedDependencyException` có nguyên nhân gốc là circular reference.

Một cách xử lý sai thường gặp là thử đổi `@AutoConfigureBefore`, `@AutoConfigureAfter`, `@AutoConfigureOrder` hoặc `@DependsOn` cho đến khi ứng dụng khởi động. Các API này có mục đích riêng về thứ tự xử lý và khởi tạo; chúng không thay thế việc thiết kế lại dependency graph.

Mục tiêu của bài là phân biệt rõ thứ tự xử lý cấu hình, thứ tự tạo bean và quan hệ phụ thuộc nghiệp vụ; sau đó chọn cách refactor để các thành phần có trách nhiệm rõ ràng và đồ thị phụ thuộc không còn chu trình.

## 2. Phân biệt ba loại thứ tự trong Spring

Có ba khái niệm thường bị gộp làm một:

| Khái niệm | Spring đang sắp xếp điều gì? | Cơ chế tiêu biểu |
| --- | --- | --- |
| Khám phá cấu hình | Auto-configuration nào được tìm thấy và đưa vào quy trình import | `AutoConfiguration.imports`, `@EnableAutoConfiguration` |
| Đăng ký bean definitions | Cấu hình nào được xử lý trước để đăng ký metadata/bean definitions | `@AutoConfigureBefore`, `@AutoConfigureAfter`, `@AutoConfigureOrder` |
| Tạo và khởi tạo bean | Bean nào phải được tạo trước vì bean khác cần nó | Constructor/method injection, dependency graph, `@DependsOn` |

Hai lớp đầu liên quan đến quá trình xử lý cấu hình. Lớp thứ ba liên quan đến việc container thực sự tạo object.

Ví dụ, Spring có thể xử lý `PaymentAutoConfiguration` trước `OrderAutoConfiguration` để đăng ký các bean definitions. Nhưng nếu constructor của `PaymentService` cần `OrderService` và constructor của `OrderService` cần `PaymentService`, dependency graph vẫn có chu trình.

## 3. @AutoConfigureBefore, @AutoConfigureAfter và @AutoConfigureOrder làm gì?

Spring Boot cung cấp các annotation để điều khiển thứ tự áp dụng auto-configuration:

- `@AutoConfigureBefore(OtherAutoConfiguration.class)` yêu cầu auto-configuration hiện tại được áp dụng trước cấu hình được chỉ định.
- `@AutoConfigureAfter(OtherAutoConfiguration.class)` yêu cầu cấu hình hiện tại được áp dụng sau cấu hình được chỉ định.
- `@AutoConfigureOrder(100)` đặt thứ tự tương đối giữa các auto-configuration không cần tham chiếu trực tiếp đến nhau.
- `@AutoConfiguration(before = ..., after = ...)` cung cấp các thuộc tính tương ứng ngay trên annotation `@AutoConfiguration`.

Điểm quan trọng trong tài liệu Spring Boot 3.3: thứ tự áp dụng auto-configuration chỉ ảnh hưởng đến thứ tự các bean definitions được đăng ký. Thứ tự tạo bean sau đó vẫn do dependencies của từng bean và các quan hệ `@DependsOn` quyết định.

Ví dụ một cấu hình tích hợp web cần được áp dụng sau cấu hình Spring MVC:

~~~java
@AutoConfiguration(after = WebMvcAutoConfiguration.class)
public class WidgetWebAutoConfiguration {
    // Các bean tích hợp với Spring MVC
}
~~~

Đây là lý do hợp lệ để dùng ordering: cấu hình cần được xử lý sau một auto-configuration khác. Nó không phải cách sửa vòng phụ thuộc giữa các service.

Không dùng các annotation ordering như một thủ thuật để buộc bean A khởi tạo trước bean B khi A và B lại cần nhau trong constructor.

## 4. Mô hình hóa dependency graph

Hãy biểu diễn mỗi bean như một đỉnh và mỗi dependency như một cạnh có hướng. Nếu bean A cần bean B, vẽ cạnh A → B.

Một thiết kế không có circular dependency có thể biểu diễn bằng đồ thị có hướng không chu trình (DAG):

~~~mermaid
flowchart TD
    A["OrderService"] --> B["PaymentProcessor"]
    A --> C["OrderRepository"]
    B --> D["PaymentGateway"]
~~~

Một thiết kế có vòng phụ thuộc:

~~~mermaid
flowchart LR
    A["OrderService"] --> B["PaymentService"]
    B --> A
~~~

Thay đổi thứ tự đăng ký configuration không xóa được cạnh A → B hoặc B → A. Muốn giải quyết vòng lặp, phải thay đổi quan hệ trách nhiệm hoặc cách các thành phần giao tiếp.

Cách nhìn này cũng hữu ích ngoài Spring: vòng phụ thuộc thường là dấu hiệu hai module biết quá nhiều về nhau, hoặc một use case đang bị chia trách nhiệm sai chỗ.

## 5. Ví dụ thiết kế có circular dependency

Hai service sau phụ thuộc constructor vào nhau:

~~~java
@Service
public class OrderService {

    private final PaymentService paymentService;

    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void markPaid(String orderId) {
        // Cập nhật trạng thái đơn hàng
    }
}
~~~

~~~java
@Service
public class PaymentService {

    private final OrderService orderService;

    public PaymentService(OrderService orderService) {
        this.orderService = orderService;
    }

    public void charge(String orderId) {
        // Thực hiện thanh toán
        orderService.markPaid(orderId);
    }
}
~~~

Đồ thị phụ thuộc:

- Tạo `OrderService` cần có `PaymentService`.
- Tạo `PaymentService` cần có `OrderService`.
- Không có điểm bắt đầu hợp lệ cho chuỗi khởi tạo constructor.

Đây không phải vấn đề thiếu thứ tự giữa hai class cấu hình. Nó phản ánh việc `PaymentService` đang vừa xử lý thanh toán, vừa điều khiển trạng thái đơn hàng thông qua một service khác.

Một dấu hiệu thiết kế cần xem lại là service A gọi service B để thực hiện công việc, rồi B gọi ngược A để hoàn thành cùng một use case. Thường nên có một thành phần điều phối use case đó.

## 6. Vì sao đổi thứ tự cấu hình không sửa được vòng lặp?

Giả sử ta thử:

~~~java
@AutoConfiguration
@AutoConfigureBefore(OrderAutoConfiguration.class)
public class PaymentAutoConfiguration {
}
~~~

Hoặc đổi thành `@AutoConfigureAfter`. Spring có thể thay đổi thứ tự xử lý các configuration class, nhưng khi tạo singleton, container vẫn phải giải quyết dependencies được khai báo trong constructor, field, setter hoặc tham số method `@Bean`.

Với vòng A → B → A:

1. Spring cần tạo A.
2. Constructor A yêu cầu B.
3. Spring bắt đầu tạo B.
4. Constructor B yêu cầu A.
5. A vẫn đang trong trạng thái tạo và chưa thể hoàn tất constructor.
6. Container phát hiện circular reference không thể giải quyết theo constructor injection.

Không có thứ tự configuration nào biến chuỗi này thành một chuỗi tạo object hợp lệ. Đổi ordering có thể làm điều kiện đăng ký bean được đánh giá ở thời điểm khác, nhưng không thay đổi yêu cầu runtime của hai constructor.

## 7. @DependsOn không phải công cụ phá circular dependency

`@DependsOn` khai báo bean hiện tại phụ thuộc vào việc khởi tạo một hoặc nhiều bean khác trước nó. Nó hữu ích khi cần bảo đảm một side effect khởi tạo đã xảy ra, chẳng hạn một bean đăng ký driver hoặc chuẩn bị tài nguyên toàn cục trước bean khác.

Ví dụ:

~~~java
@Component
@DependsOn("databaseDriverRegistrar")
public class DatabaseHealthProbe {
    // Cần driver registrar được khởi tạo trước
}
~~~

`@DependsOn` không truyền collaborator vào constructor và không loại bỏ dependency nghiệp vụ giữa hai service. Nếu A phụ thuộc B và B phụ thuộc A, thêm `@DependsOn` vào hai phía chỉ tạo thêm ràng buộc thứ tự, không sửa vòng lặp.

Chỉ dùng `@DependsOn` khi có một yêu cầu khởi tạo rõ ràng mà dependency injection thông thường không thể diễn đạt, thường là thứ tự side effect. Nếu bean cần gọi method của bean khác trong hoạt động bình thường, hãy khai báo collaborator đó qua constructor hoặc tham số factory method.

## 8. Refactor bằng cách chọn một use-case orchestrator

Một cách sửa thường hiệu quả là xác định service nào sở hữu use case và để service đó điều phối các bước.

Trong ví dụ thanh toán:
- `OrderService` sở hữu use case thanh toán cho đơn hàng.
- `OrderService` gọi `PaymentProcessor` để xử lý khoản thanh toán.
- `PaymentProcessor` trả kết quả thanh toán.
- `OrderService` cập nhật đơn hàng dựa trên kết quả đó.
- `PaymentProcessor` không cần gọi ngược `OrderService`.

Dependency graph mới:

~~~mermaid
flowchart TD
    A["OrderService"] --> B["PaymentProcessor"]
    A --> C["OrderRepository"]
    B --> D["PaymentGateway"]
~~~

Ví dụ các contract:

~~~java
public interface PaymentProcessor {
    PaymentReceipt charge(Order order);
}
~~~

~~~java
public record PaymentReceipt(String transactionId, boolean successful) {
}
~~~

Service điều phối:

~~~java
@Service
public class OrderService {

    private final PaymentProcessor paymentProcessor;
    private final OrderRepository orderRepository;

    public OrderService(
            PaymentProcessor paymentProcessor,
            OrderRepository orderRepository) {
        this.paymentProcessor = paymentProcessor;
        this.orderRepository = orderRepository;
    }

    public void pay(String orderId) {
        Order order = orderRepository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found: " + orderId));

        PaymentReceipt receipt = paymentProcessor.charge(order);

        if (receipt.successful()) {
            order.markPaid(receipt.transactionId());
            orderRepository.save(order);
        }
    }
}
~~~

Implementation thanh toán chỉ thực hiện phần việc của nó:

~~~java
@Service
public class DefaultPaymentProcessor implements PaymentProcessor {

    private final PaymentGateway paymentGateway;

    public DefaultPaymentProcessor(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    @Override
    public PaymentReceipt charge(Order order) {
        return paymentGateway.charge(order.id(), order.total());
    }
}
~~~

Sau refactor:
- `OrderService` có thể điều phối nhiều bước của use case.
- `PaymentProcessor` chỉ cần biết order data và payment gateway.
- Kết quả thanh toán được trả về bằng một value object.
- Không còn dependency ngược từ payment về order service.

Đây thường là giải pháp dễ kiểm thử nhất khi thao tác thanh toán là một phần đồng bộ của use case đặt hàng.

## 9. Ví dụ Java 17+ chạy độc lập sau refactor

Chương trình dưới đây mô phỏng cùng ý tưởng mà không cần Spring, database hoặc thư viện bên ngoài. Nó thể hiện dependency một chiều: `OrderService` phụ thuộc vào interface `PaymentProcessor`.

Tệp `OrderPaymentDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class OrderPaymentDemo {

    record Order(String id, BigDecimal total) {
    }

    record PaymentReceipt(String transactionId, boolean successful) {
    }

    interface PaymentProcessor {
        PaymentReceipt charge(Order order);
    }

    static final class FakePaymentProcessor implements PaymentProcessor {

        @Override
        public PaymentReceipt charge(Order order) {
            return new PaymentReceipt("TX-42", true);
        }
    }

    static final class OrderService {

        private final PaymentProcessor paymentProcessor;

        OrderService(PaymentProcessor paymentProcessor) {
            this.paymentProcessor = Objects.requireNonNull(paymentProcessor);
        }

        String pay(Order order) {
            PaymentReceipt receipt = paymentProcessor.charge(order);
            if (!receipt.successful()) {
                return "Payment failed for " + order.id();
            }
            return "Order " + order.id() + " paid: " + receipt.transactionId();
        }
    }

    public static void main(String[] args) {
        PaymentProcessor processor = new FakePaymentProcessor();
        OrderService orderService = new OrderService(processor);

        Order order = new Order("ORD-42", new BigDecimal("125.00"));
        System.out.println(orderService.pay(order));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac OrderPaymentDemo.java
java OrderPaymentDemo
~~~

Stdout chính xác:

~~~text
Order ORD-42 paid: TX-42
~~~

Ví dụ không tạo Spring bean. Nó chứng minh phần thiết kế cốt lõi có thể tồn tại độc lập với container: một use-case service nhận collaborator qua constructor và điều phối công việc theo một chiều.

## 10. Dùng interface và dependency inversion đúng cách

Interface có thể giúp đảo chiều phụ thuộc giữa module, nhưng chỉ thêm interface chưa chắc phá được cycle.

Ví dụ:
- Module order định nghĩa `PaymentProcessor` như một port mà use case cần.
- Adapter thanh toán triển khai `PaymentProcessor`.
- `OrderService` phụ thuộc vào port.
- Adapter phụ thuộc vào gateway bên ngoài.

Đồ thị module trở nên rõ hơn:

~~~mermaid
flowchart LR
    A["Order application"] --> B["PaymentProcessor port"]
    C["Payment adapter"] -. "implements" .-> B
    C --> D["External payment gateway"]
~~~

Nếu adapter vẫn inject ngược `OrderService` để cập nhật order, vòng lặp chỉ bị chuyển qua interface hoặc module khác. Dependency inversion có tác dụng khi hướng phụ thuộc thực sự được thay đổi và contract không kéo ngược toàn bộ module cấp cao vào module cấp thấp.

Khi review, hãy xem các import, constructor, factory method và module dependency. Tên interface đẹp không đủ; đồ thị phụ thuộc thực tế mới quyết định kiến trúc có acyclic hay không.

## 11. Khi nào nên dùng event để tách hai phía?

Nếu một service cần thông báo kết quả cho phần khác nhưng không cần gọi trực tiếp và nhận kết quả ngay, application/domain event có thể tách hai phía.

Ví dụ payment service phát sự kiện:

~~~java
public record PaymentCompleted(String orderId, String transactionId) {
}
~~~

~~~java
@Service
public class PaymentService {

    private final ApplicationEventPublisher events;

    public PaymentService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void charge(String orderId) {
        String transactionId = "TX-42";
        events.publishEvent(
                new PaymentCompleted(orderId, transactionId));
    }
}
~~~

Một listener thuộc phần order xử lý sự kiện:

~~~java
@Component
public class PaymentCompletedHandler {

    private final OrderRepository orders;

    public PaymentCompletedHandler(OrderRepository orders) {
        this.orders = orders;
    }

    @EventListener
    public void on(PaymentCompleted event) {
        Order order = orders.findById(event.orderId())
                .orElseThrow();
        order.markPaid(event.transactionId());
        orders.save(order);
    }
}
~~~

Dependency graph:
- Payment service phụ thuộc vào `ApplicationEventPublisher`.
- Handler phụ thuộc vào `OrderRepository`.
- Payment service không cần biết `OrderService` hoặc handler cụ thể.

Trong Spring, `ApplicationEventPublisher` mặc định phát event trong cùng process; listener đồng bộ nếu không cấu hình async. Nếu cần chỉ xử lý sau khi transaction commit, xem `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` và bảo đảm event được phát trong transaction phù hợp.

Event hữu ích khi quan hệ là thông báo một chiều. Không nên dùng event cho mọi lời gọi service đơn giản vì nó làm luồng xử lý và lỗi khó theo dõi hơn nếu không cần sự tách rời đó.

## 12. @Lazy và ObjectProvider chỉ nên dùng cho nhu cầu trì hoãn thực sự

Spring có một số cơ chế trì hoãn việc phân giải dependency:

- `@Lazy` tại injection point tạo proxy để dependency được phân giải khi sử dụng.
- `ObjectProvider<T>` cho phép lấy bean theo yêu cầu, kiểm tra optional bean hoặc trì hoãn việc gọi `getObject()`.
- `ObjectFactory<T>` cũng cung cấp cách lấy object khi cần.

Ví dụ:

~~~java
@Service
public class ReportService {

    private final ObjectProvider<ExportClient> exportClientProvider;

    public ReportService(
            ObjectProvider<ExportClient> exportClientProvider) {
        this.exportClientProvider = exportClientProvider;
    }

    public void exportWhenEnabled(Report report) {
        ExportClient client = exportClientProvider.getIfAvailable();
        if (client != null) {
            client.export(report);
        }
    }
}
~~~

Đây là trường hợp hợp lý nếu export là dependency tùy chọn hoặc chỉ cần trong một nhánh xử lý hiếm khi chạy.

Nếu dùng `@Lazy` hoặc `ObjectProvider` chỉ để che giấu việc A gọi B và B gọi A, dependency vòng vẫn tồn tại về mặt thiết kế. Khi method được gọi, lỗi có thể xuất hiện muộn hơn; luồng gọi qua lại cũng có thể gây recursion hoặc trạng thái object chưa sẵn sàng.

Quy tắc thực tế:
- Dùng trì hoãn khi dependency thực sự optional, nặng hoặc chỉ cần tại một thời điểm sau.
- Dùng interface/event/orchestrator khi cần sửa hướng phụ thuộc.
- Không dùng proxy lazy như cách thay thế việc phân chia trách nhiệm.

## 13. Setter injection không phải giải pháp kiến trúc mặc định

Spring có thể giải quyết một số circular reference giữa singleton bean dùng setter hoặc field injection bằng cơ chế early reference. Tuy nhiên:
- Một bean có thể được đưa vào bean khác trước khi hoàn tất khởi tạo.
- Trạng thái chưa hoàn chỉnh có thể bị quan sát.
- Constructor không còn thể hiện đầy đủ các dependency bắt buộc.
- Test unit khó dựng object ở trạng thái hợp lệ nếu dependency chỉ được gán sau.
- Một số đường khởi tạo, proxy hoặc lifecycle có thể không tương thích với cách giải quyết vòng lặp đó.

Spring khuyến nghị constructor injection cho dependency bắt buộc. Setter/configuration method phù hợp hơn cho dependency tùy chọn có default hợp lý.

Spring Boot mặc định không cho phép tự động giải quyết circular references. Thuộc tính `spring.main.allow-circular-references` có default `false`. Bật nó có thể làm một số vòng lặp setter/field chạy được, nhưng không làm đồ thị thiết kế trở nên tốt hơn và không giải quyết được vòng constructor không thể khởi tạo.

Không đổi toàn ứng dụng sang setter injection chỉ để vượt qua lỗi startup. Hãy xác định cạnh phụ thuộc ngược và refactor.

## 14. Dùng thứ tự auto-configuration đúng trường hợp

Ordering vẫn rất quan trọng trong thư viện auto-configuration, đặc biệt khi condition phụ thuộc bean definitions đã được đăng ký.

Ví dụ cấu hình metrics cần quan sát bean `DataSource` do Spring Boot JDBC auto-configuration tạo:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class JdbcMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(DataSource.class)
    JdbcMetricsReporter jdbcMetricsReporter(DataSource dataSource) {
        return new JdbcMetricsReporter(dataSource);
    }
}
~~~

Ở đây `after` có mục đích rõ:
1. Spring xử lý auto-configuration datasource trước.
2. Bean definition `DataSource` được đăng ký.
3. Condition `@ConditionalOnBean(DataSource.class)` có thể kiểm tra bean definition đã có.
4. Nếu condition khớp, reporter được đăng ký.

Ordering phù hợp vì nó giúp condition nhìn thấy bean definition từ cấu hình khác. Khi reporter được tạo, dependency `DataSource` vẫn được giải quyết bằng tham số method `@Bean`.

Không dùng ordering để khiến hai auto-configuration chứa các service constructor phụ thuộc lẫn nhau. Nếu một configuration chỉ hoạt động khi configuration kia đã đăng ký bean, dùng ordering cho condition; nếu hai bean phụ thuộc vòng, refactor bean graph.

## 15. @Bean method parameters diễn đạt dependency rõ ràng hơn gọi method trực tiếp

Trong Java configuration, tham số của method `@Bean` là dependency mà container cần cung cấp:

~~~java
@Configuration(proxyBeanMethods = false)
public class OrderConfiguration {

    @Bean
    PaymentProcessor paymentProcessor(PaymentGateway paymentGateway) {
        return new DefaultPaymentProcessor(paymentGateway);
    }

    @Bean
    OrderService orderService(
            PaymentProcessor paymentProcessor,
            OrderRepository orderRepository) {
        return new OrderService(paymentProcessor, orderRepository);
    }
}
~~~

Cách này để Spring quản lý việc phân giải dependency và tạo bean theo đúng bean definitions.

Tránh gọi trực tiếp method `@Bean` khác như một cách tìm instance:

~~~java
@Bean
OrderService orderService() {
    return new OrderService(paymentProcessor(null));
}
~~~

Đây là ví dụ sai vì tự truyền giá trị không phù hợp và bỏ qua dependency resolution của container. Trong cấu hình `proxyBeanMethods = false`, lời gọi method là lời gọi Java thông thường, không được intercept để lấy bean từ container. Dùng method parameters để diễn đạt quan hệ.

Khi configuration class bắt đầu gọi chéo nhiều factory method, hãy xem lại xem các dependency có thể được biểu diễn tường minh qua tham số hay không.

## 16. Kiểm thử để phát hiện circular dependency sớm

Một test context cần xác minh ứng dụng có thể tạo các bean sau refactor. Với auto-configuration, `ApplicationContextRunner` giúp dựng context nhỏ:

~~~java
class OrderPaymentAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    OrderPaymentAutoConfiguration.class));

    @Test
    void createsOrderAndPaymentBeansWithoutCircularDependency() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(OrderService.class);
            assertThat(context).hasSingleBean(PaymentProcessor.class);
        });
    }
}
~~~

Test này phù hợp khi `OrderPaymentAutoConfiguration` là auto-configuration thực sự và có đăng ký các bean cần thiết. Nếu cấu hình dùng prerequisite bean, thêm đúng user configuration/property tương ứng vào runner.

Ngoài test context:
- Unit test `OrderService` bằng fake `PaymentProcessor` để xác minh orchestration.
- Integration test xác minh giao dịch hoặc event listener cập nhật trạng thái đúng.
- Test khởi động ứng dụng bằng `@SpringBootTest` để kiểm tra các configuration cùng hoạt động.
- Khi thay đổi module boundary, cân nhắc ArchUnit hoặc kiểm tra dependency graph để phát hiện dependency ngược.

Đừng chỉ assert context khởi động. Hãy test hành vi quan trọng và xác nhận dependency không quay ngược qua một service khác.

## 17. Anti-pattern và cách xử lý

| Anti-pattern | Vì sao không giải quyết gốc rễ | Hướng xử lý |
| --- | --- | --- |
| Đổi `@AutoConfigureBefore` thành `@AutoConfigureAfter` để chữa constructor cycle | Chỉ đổi thứ tự đăng ký bean definitions | Refactor dependency graph |
| Thêm `@DependsOn` ở hai bean | Thêm ràng buộc khởi tạo, không bỏ dependency ngược | Chọn orchestrator hoặc tách trách nhiệm |
| Bật `spring.main.allow-circular-references=true` | Cho phép một số vòng setter/field chạy bằng early references | Giữ dependency bắt buộc qua constructor và sửa thiết kế |
| Chuyển tất cả constructor sang setter | Che giấu dependency bắt buộc và có thể để lộ bean chưa hoàn chỉnh | Dùng constructor injection; tách collaborator |
| Thêm `@Lazy` vào mọi dependency vòng | Trì hoãn lỗi hoặc việc khởi tạo, không xóa quan hệ vòng | Chỉ dùng lazy khi có nhu cầu trì hoãn thực sự |
| Bọc service bằng interface nhưng implementation vẫn gọi ngược | Đổi kiểu tham chiếu nhưng giữ chu trình | Đảo chiều module dependency và loại callback ngược |
| Tạo thêm configuration class để gọi chéo bean | Tăng số lớp nhưng không đổi dependency graph | Đưa dependency vào tham số `@Bean` hoặc service owner |
| Dùng event cho mọi lời gọi đồng bộ | Làm luồng xử lý khó theo dõi mà không có lợi ích tách rời | Chỉ dùng event cho thông báo một chiều phù hợp |

## 18. Checklist review thiết kế

Trước khi thêm hoặc thay đổi ordering, hãy tự hỏi:

1. Tôi đang sắp xếp auto-configuration để condition thấy bean definition, hay đang cố điều khiển thời điểm tạo service?
2. Bean A có cần bean B trong constructor, và B có cần A không?
3. Có service nào vừa điều phối use case vừa bị service cấp thấp gọi ngược?
4. Có thể chọn một orchestrator duy nhất để điều phối luồng không?
5. Có thể chuyển kết quả qua return value/value object thay vì callback ngược không?
6. Nếu quan hệ là thông báo một chiều, event có phù hợp hơn gọi service trực tiếp không?
7. Interface mới có thực sự đổi hướng phụ thuộc giữa module không?
8. Dependency có thực sự optional/lazy, hay `@Lazy`/`ObjectProvider` chỉ đang che giấu cycle?
9. `@DependsOn` có đang diễn đạt side effect initialization thật sự hay chỉ chữa lỗi injection?
10. Test context có kiểm tra cả startup lẫn hành vi nghiệp vụ sau refactor không?
11. Có cấu hình `spring.main.allow-circular-references=true` nào đang vô tình che lỗi không?
12. Ordering được ghi chú rõ condition hoặc auto-configuration nào cần được xử lý trước/sau chưa?

## 19. Tự kiểm tra kiến thức

1. `@AutoConfigureAfter` điều khiển thứ tự nào? **Thứ tự áp dụng auto-configuration và đăng ký bean definitions.**
2. Bean được tạo theo thứ tự nào? **Theo dependency graph và các quan hệ khởi tạo tường minh như `@DependsOn`.**
3. Đổi `@AutoConfigureBefore` có phá được constructor cycle không? **Không; quan hệ constructor dependency vẫn còn.**
4. Vòng constructor A → B → A thường dẫn đến lỗi gì? **`BeanCurrentlyInCreationException` hoặc lỗi dependency có nguyên nhân circular reference.**
5. `@DependsOn` phù hợp với trường hợp nào? **Bảo đảm một bean có side effect khởi tạo được chạy trước bean khác.**
6. Vì sao constructor injection hữu ích khi review? **Nó thể hiện dependency bắt buộc và tạo object ở trạng thái đầy đủ.**
7. `@Lazy` có xóa dependency cycle không? **Không; nó trì hoãn việc phân giải dependency.**
8. `ObjectProvider<T>` hữu ích khi nào? **Khi dependency optional hoặc cần lấy theo yêu cầu tại một thời điểm sau.**
9. Khi nào event phù hợp? **Khi một thành phần cần phát thông báo một chiều và không cần gọi trực tiếp service nhận thông báo.**
10. Vì sao ordering hữu ích với `@ConditionalOnBean`? **Bean definition của prerequisite cần được đăng ký trước lúc condition được đánh giá.**
11. `spring.main.allow-circular-references` mặc định là gì trong Spring Boot 3.3? **`false`.**
12. Bước đầu tiên khi phát hiện hai service gọi ngược nhau là gì? **Xác định service sở hữu use case và thiết kế lại hướng điều phối/phụ thuộc.**

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): thứ tự áp dụng auto-configuration, bean definition ordering, conditions và lưu ý về dependencies.
- [Spring Boot 3.3.13 — `@AutoConfigureBefore` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html): mục đích và giới hạn của ordering.
- [Spring Boot 3.3.13 — `@AutoConfigureAfter` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html): thứ tự áp dụng auto-configuration.
- [Spring Boot 3.3.13 — `@AutoConfigureOrder` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureOrder.html): thứ tự tương đối giữa các auto-configuration.
- [Spring Boot 3.3.13 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): default của `spring.main.allow-circular-references`.
- [Spring Framework — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): constructor/setter injection, dependency resolution và circular dependencies.
