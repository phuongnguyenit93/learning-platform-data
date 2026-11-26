# Lắp ráp thành phần tại composition root và quản lý vòng đời

Trong chương **Tổ chức phụ thuộc và lắp ráp ứng dụng**, bài học này giải thích nơi các thành phần được kết nối thành một ứng dụng chạy được và cách quản lý vòng đời của những đối tượng đó. Với module **SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED**, mục tiêu là tổ chức phần mềm theo kiến trúc phân tầng: tầng trình bày, ứng dụng, nghiệp vụ và truy cập dữ liệu có trách nhiệm riêng, đồng thời cần được lắp ráp theo một đồ thị phụ thuộc nhất quán.

Một lớp có thể được thiết kế tốt nhưng ứng dụng vẫn khó thay đổi nếu nó tự tạo các dependency bằng `new`, tự tìm đối tượng qua một service locator hoặc tự quản lý kết nối và thread. Khi cách tạo đối tượng bị phân tán khắp mã nguồn, việc thay triển khai, cấu hình theo môi trường và kiểm thử trở nên khó khăn. **Composition root** là điểm có trách nhiệm lắp ráp đồ thị đối tượng của ứng dụng. Tại đó, các triển khai cụ thể được chọn, dependency được truyền vào consumer và vòng đời được giao cho cơ chế quản lý phù hợp.

Sau bài học, bạn có thể:

- Giải thích composition root và vai trò của nó trong kiến trúc phân tầng.
- Nhận biết đồ thị dependency và xác định nơi nên tạo, cấu hình, kết nối các thành phần.
- Dùng constructor injection và cấu hình Spring để lắp ráp ứng dụng.
- Chọn scope và vòng đời phù hợp cho service, adapter và tài nguyên dùng chung.
- Quản lý khởi tạo, đóng tài nguyên và tránh các lỗi do singleton mutable hoặc dependency vòng.
- Kiểm thử cấu hình lắp ráp mà không buộc unit test phải khởi động toàn bộ ứng dụng.

## 1. Từ các lớp riêng lẻ đến một ứng dụng được lắp ráp

Một ứng dụng phân tầng thường có nhiều thành phần hợp tác với nhau. Ví dụ, request tạo đơn hàng đi từ controller đến dịch vụ ứng dụng, qua hợp đồng lưu trữ rồi đến adapter JPA:

~~~mermaid
flowchart TD
    C[OrderController] --> U[PlaceOrderService]
    U --> P[OrderRepository port]
    P --> A[JpaOrderRepository adapter]
    A --> D[(Database)]
~~~

Sơ đồ thể hiện các quan hệ sử dụng. Nhưng khi chương trình khởi động, ai tạo `OrderController`, ai cung cấp `PlaceOrderService`, triển khai nào đáp ứng `OrderRepository` và cấu hình database lấy từ đâu? Những quyết định tạo và nối các đối tượng này thuộc hoạt động **composition** – lắp ráp thành phần.

Đồ thị dependency là tập các đối tượng và quan hệ mà một đối tượng cần để thực hiện trách nhiệm. Nếu `OrderController` cần `PlaceOrder`, và `PlaceOrderService` cần `OrderRepository`, thì đồ thị có dạng:

~~~text
OrderController
    -> PlaceOrder
        -> OrderRepository
            -> JpaOrderRepository
                -> DataSource
~~~

Một ứng dụng có thể có hàng trăm hoặc hàng nghìn bean, nhưng các lớp nghiệp vụ không nên tự quyết định cách tạo toàn bộ những dependency mà chúng sử dụng. Chúng khai báo nhu cầu qua constructor hoặc một hợp đồng phù hợp; cơ chế lắp ráp chịu trách nhiệm cung cấp đối tượng thực tế.

## 2. Composition root là gì?

Composition root là điểm hoặc vùng mã nguồn ở ranh giới khởi động ứng dụng, nơi các thành phần được tạo và kết nối thành đồ thị dependency hoàn chỉnh. Nó là nơi phù hợp để quyết định:

- Dùng triển khai cụ thể nào cho một interface hoặc port.
- Cung cấp cấu hình, endpoint, thông tin kết nối và các giá trị môi trường.
- Tạo các đối tượng dùng chung và chọn scope/vòng đời của chúng.
- Bật hoặc thay thế adapter theo môi trường hay kiểu triển khai.
- Kết nối framework, logging, metrics, scheduler và các tài nguyên cấp ứng dụng.

Trong một chương trình Java thuần, composition root có thể là `main` hoặc một lớp bootstrap tạo đối tượng bằng constructor. Với Spring Boot, composition root được hình thành từ lớp khởi động, các lớp `@Configuration`, các phương thức `@Bean`, component scanning và cơ chế auto-configuration. Không nhất thiết chỉ có một file cấu hình; điều cần có là một vùng dễ nhận diện chịu trách nhiệm lắp ráp ứng dụng.

Ví dụ Java thuần:

~~~java
public final class Application {
    public static void main(String[] args) {
        var dataSource = createDataSourceFromEnvironment();
        var orderRepository = new JdbcOrderRepository(dataSource);
        var placeOrder = new PlaceOrderService(orderRepository);
        var controller = new OrderController(placeOrder);

        var server = new HttpServerAdapter(controller);
        server.start();
    }
}
~~~

Đây là mã minh họa, trong đó các hàm và kiểu adapter được rút gọn. Điểm quan trọng là `Application` biết các lớp triển khai cụ thể và kết nối chúng. `PlaceOrderService` không tự tạo `JdbcOrderRepository`; `OrderController` không tự tạo `PlaceOrderService`. Nhờ vậy, quyết định lắp ráp tập trung ở biên ứng dụng.

Composition root thường phụ thuộc vào nhiều chi tiết cụ thể hơn các module nghiệp vụ. Điều này là bình thường: nó có nhiệm vụ kết nối các chi tiết đó. Các tầng bên trong vẫn giữ hợp đồng và hướng phụ thuộc phù hợp để không bị kéo theo framework hoặc cơ chế lưu trữ.

## 3. Constructor injection làm rõ dependency

Một đối tượng nên khai báo dependency bắt buộc qua constructor. Cách này làm rõ điều kiện để đối tượng hoạt động, giúp đối tượng được tạo ở trạng thái hợp lệ và dễ thay thế dependency trong kiểm thử.

~~~java
public interface OrderRepository {
    void save(Order order);
}

public interface PlaceOrder {
    OrderReceipt execute(PlaceOrderCommand command);
}

public final class PlaceOrderService implements PlaceOrder {
    private final OrderRepository orders;

    public PlaceOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Override
    public OrderReceipt execute(PlaceOrderCommand command) {
        var order = Order.create(command);
        orders.save(order);
        return new OrderReceipt(order.id());
    }
}
~~~

Trong ví dụ, `PlaceOrderService` khai báo nó cần `OrderRepository`. Nó không biết repository được triển khai bằng JDBC, JPA hay một fake trong test. Dependency là `final`, do đó không thể bị thay thế tùy tiện sau khi đối tượng đã được tạo.

Các kiểu `Order`, `PlaceOrderCommand` và `OrderReceipt` đại diện cho mô hình của ứng dụng. Ví dụ tập trung vào cách tiêm dependency, không nhằm mô tả đầy đủ quy tắc đặt hàng.

### Vì sao constructor injection thường là lựa chọn mặc định?

- **Dependency rõ ràng:** nhìn vào constructor là biết đối tượng cần gì.
- **Trạng thái hợp lệ:** không thể tạo đối tượng thiếu dependency bắt buộc mà không chủ động cung cấp giá trị.
- **Dễ kiểm thử:** test có thể truyền fake hoặc mock trực tiếp.
- **Bất biến:** dependency có thể được giữ trong trường `final`.
- **Phát hiện thiết kế quá tải:** constructor có quá nhiều tham số thường là dấu hiệu lớp đang nhận quá nhiều trách nhiệm hoặc cần gom nhóm dependency có ý nghĩa.

Field injection làm dependency khó nhìn thấy và khiến việc tạo đối tượng ngoài container trở nên bất tiện. Setter injection phù hợp hơn với dependency thật sự tùy chọn hoặc cần thay đổi sau khi tạo, nhưng không nên dùng cho những dependency bắt buộc chỉ để tránh khai báo constructor.

## 4. Lắp ráp bằng Spring Boot

Spring IoC container quản lý bean và giải quyết dependency dựa trên các bean definition. Một lớp khởi động thường có `@SpringBootApplication`, bao gồm cấu hình, auto-configuration và component scanning trong phạm vi package được chọn.

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Spring tìm các thành phần được đăng ký và tạo bean theo dependency graph. Có thể dùng stereotype như `@Service`, `@Repository`, `@Component`, `@RestController` cho các lớp phù hợp. Các lớp cấu hình dùng `@Configuration` và `@Bean` để đăng ký thành phần cần tạo tường minh, đặc biệt khi lớp triển khai nằm trong thư viện ngoài hoặc cần cách khởi tạo có tham số.

Ví dụ cấu hình một port lưu trữ:

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderConfiguration {

    @Bean
    OrderRepository orderRepository(DataSource dataSource) {
        return new JdbcOrderRepository(dataSource);
    }

    @Bean
    PlaceOrder placeOrder(OrderRepository orderRepository) {
        return new PlaceOrderService(orderRepository);
    }
}
~~~

Ở đây, `OrderConfiguration` là một phần composition root. Nó chọn `JdbcOrderRepository` để triển khai `OrderRepository` và tạo `PlaceOrderService`. Spring cũng có thể tự tạo `DataSource` từ cấu hình nếu dependency và thuộc tính tương ứng đã có.

Trong một dự án dùng component scanning, `PlaceOrderService` có thể được đánh dấu `@Service` và `JdbcOrderRepository` có thể được đánh dấu `@Repository`; khi đó không cần khai báo lại chúng bằng `@Bean`. Hãy chọn một cách đăng ký nhất quán cho từng bean để tránh tạo hai bean cùng vai trò hoặc gây mơ hồ khi inject.

### Khi có nhiều triển khai

Nếu có cả `JdbcOrderRepository` và `JpaOrderRepository`, Spring cần biết triển khai nào được chọn cho một injection point. Có thể dùng `@Primary`, `@Qualifier`, profile hoặc cấu hình có điều kiện. Ví dụ:

~~~java
@Configuration
class PersistenceConfiguration {

    @Bean
    @Primary
    OrderRepository orderRepository(JpaOrderRepository repository) {
        return repository;
    }
}
~~~

`@Primary` chọn bean ưu tiên khi có nhiều candidate phù hợp. `@Qualifier` hữu ích khi một consumer cần chỉ rõ bean theo tên hoặc qualifier. Profiles và conditional configuration phù hợp để thay adapter theo môi trường, nhưng lựa chọn đó nên được thể hiện tại composition root. Không đưa các nhánh `if (environment == "production")` vào service nghiệp vụ để tự chọn repository.

## 5. Cấu hình môi trường và dependency graph

Composition root cũng là nơi kết hợp cấu hình bên ngoài với thành phần. URL database, kích thước pool, thời gian timeout, endpoint của dịch vụ ngoài và cờ bật adapter nên đến từ cấu hình môi trường hoặc secret manager theo chính sách vận hành.

Với Spring Boot, có thể gom cấu hình liên quan vào một kiểu `@ConfigurationProperties` thay vì đọc biến môi trường rải rác trong service:

~~~java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "orders.client")
public record OrdersClientProperties(
        String baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {}
~~~

~~~yaml
orders:
  client:
    base-url: https://orders.internal
    connect-timeout: 2s
    read-timeout: 5s
~~~

Ứng dụng cần đăng ký properties bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` phù hợp. Ví dụ này minh họa cấu trúc cấu hình; giá trị production cần được cung cấp qua hệ thống cấu hình an toàn và không nên commit mật khẩu hay token vào repository.

Hãy kiểm tra cấu hình bắt buộc ngay lúc khởi động. Nếu endpoint hoặc credential thiếu, ứng dụng nên thất bại sớm với thông báo đủ rõ để vận hành sửa cấu hình. Tránh để một service khởi động thành công nhưng chỉ phát hiện thiếu cấu hình khi request đầu tiên đến.

Profiles như `dev`, `test` hoặc `prod` có thể chọn cấu hình và adapter khác nhau. Tuy nhiên, profile không nên trở thành cơ chế để che giấu nhiều kiến trúc khác nhau mà không ai hiểu. Nên giới hạn khác biệt ở những quyết định triển khai hợp lý, như database local so với database dùng chung, hoặc adapter gửi email thật so với adapter giả lập.

## 6. Scope và vòng đời bean trong Spring

Tạo đối tượng đúng chưa đủ; cần xác định đối tượng sống trong bao lâu và ai chịu trách nhiệm hủy nó. Scope quyết định container tạo và chia sẻ instance như thế nào.

| Scope | Cách sống | Ví dụ sử dụng và lưu ý |
|---|---|---|
| `singleton` | Một instance cho mỗi bean definition trong một Spring container | Service stateless, repository, adapter dùng chung. Phải an toàn khi nhiều thread cùng gọi. |
| `prototype` | Container tạo instance mới mỗi lần bean được yêu cầu | Đối tượng có trạng thái riêng theo một lần xử lý; container không tự quản lý đầy đủ bước hủy sau khi giao instance cho consumer. |
| `request` | Một instance trong vòng đời HTTP request | Context hoặc thành phần thực sự gắn với một request web. Không phù hợp để mặc định dùng trong scheduler hoặc batch. |
| `session` | Một instance theo HTTP session | Dữ liệu có vòng đời phiên người dùng; cần cân nhắc bộ nhớ, phân tán và tính phù hợp của trạng thái. |

Spring dùng singleton scope làm mặc định. Điều này không có nghĩa đối tượng là singleton toàn JVM; nó là một instance theo bean definition trong từng container. Khi ứng dụng có nhiều tiến trình hoặc container, mỗi container có instance riêng.

### Singleton phải an toàn với nhiều request

Một service singleton thường nên stateless: dữ liệu của một lần gọi nằm trong biến cục bộ hoặc đối tượng đầu vào bất biến, không lưu vào trường mutable dùng chung.

~~~java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
class TaxCalculator {
    BigDecimal calculate(Order order) {
        var rate = resolveRate(order.region());
        return order.subtotal().multiply(rate);
    }
}
~~~

Trong ví dụ này, `rate` là biến cục bộ nên mỗi lần gọi có giá trị riêng. Trái lại, nếu service lưu `currentOrder` vào một trường instance rồi thay đổi nó ở mỗi request, hai thread có thể ghi đè dữ liệu của nhau. Không nên lưu dữ liệu request, actor hiện tại hoặc kết quả tạm vào field của bean singleton.

### Prototype được inject vào singleton

Nếu một bean prototype được inject trực tiếp vào singleton, dependency đó thường được phân giải tại thời điểm singleton được tạo và cùng instance sẽ được giữ lại. Muốn lấy một instance mới theo từng lần cần dùng, hãy dùng `ObjectProvider`, `Provider` hoặc một factory được tiêm vào:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
class ReportCoordinator {
    private final ObjectProvider<ReportJob> jobs;

    ReportCoordinator(ObjectProvider<ReportJob> jobs) {
        this.jobs = jobs;
    }

    void createReport() {
        var job = jobs.getObject();
        job.run();
    }
}

@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class ReportJob {
    void run() {
        // Thực hiện một lần tạo báo cáo.
    }
}
~~~

Container tạo một `ReportJob` mới cho mỗi lần `getObject()`. Tuy nhiên, với prototype, Spring không tự gọi đầy đủ callback hủy sau khi đã bàn giao instance cho consumer. Nếu đối tượng cần đóng tài nguyên, consumer hoặc factory phải có quy tắc sở hữu và giải phóng rõ ràng. Không dùng prototype chỉ vì muốn tránh quản lý trạng thái; thiết kế stateless thường đơn giản hơn.

### Request scope và tác vụ nền

Request-scoped bean chỉ có ngữ cảnh hợp lệ khi xử lý web request. Nếu một singleton hoặc scheduled job cần dữ liệu gắn với request, hãy chuyển các giá trị cần thiết thành command/context rõ ràng. Không để job nền phụ thuộc ngầm vào `HttpServletRequest`, session hoặc request-scoped bean.

## 7. Khởi tạo và giải phóng tài nguyên

Một số bean chỉ chứa logic thuần, nhưng adapter dữ liệu, client HTTP, scheduler, executor hoặc consumer message có thể sở hữu tài nguyên cần đóng đúng lúc. Vòng đời thường có các giai đoạn:

1. Tạo đối tượng và inject dependency.
2. Thực hiện bước khởi tạo sau khi dependency đã sẵn sàng.
3. Bean phục vụ ứng dụng trong scope đã chọn.
4. Khi container đóng, thực hiện callback hủy và giải phóng tài nguyên do bean sở hữu.

Với bean Spring, có thể dùng `@PostConstruct` cho khởi tạo và `@PreDestroy` cho bước dọn dẹp:

~~~java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
class MessageConsumer {
    private final BrokerClient client;

    MessageConsumer(BrokerClient client) {
        this.client = client;
    }

    @PostConstruct
    void start() {
        client.connectAndSubscribe();
    }

    @PreDestroy
    void stop() {
        client.close();
    }
}
~~~

Ví dụ giả định `BrokerClient` có các phương thức tương ứng và bean này sở hữu vòng đời kết nối. Nếu client được chia sẻ và quản lý bởi một bean khác, không nên đóng nó từ consumer. Mỗi tài nguyên cần có một chủ sở hữu rõ ràng để tránh đóng hai lần hoặc đóng khi thành phần khác vẫn đang sử dụng.

Với đối tượng được tạo bằng `@Bean`, có thể khai báo `destroyMethod` hoặc để Spring suy luận phương thức đóng như `close`/`shutdown` trong các trường hợp được hỗ trợ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ClientConfiguration {
    @Bean(destroyMethod = "close")
    ExternalClient externalClient(ClientProperties properties) {
        return new ExternalClient(properties.endpoint());
    }
}
~~~

Đối với tài nguyên ngắn hạn như `InputStream`, `ResultSet` hoặc file handle trong một phương thức, dùng `try-with-resources` thường phù hợp hơn callback vòng đời bean. Không giữ một tài nguyên ngắn hạn trong singleton nếu mỗi lần gọi có thể tự mở và đóng nó.

### Không làm khởi động ứng dụng phụ thuộc vào tác vụ dài không cần thiết

`@PostConstruct` nên dành cho khởi tạo nhanh và cần thiết để bean sẵn sàng. Không nên đặt một quá trình import hàng triệu dòng hoặc tác vụ đồng bộ kéo dài trong callback này, vì nó làm chậm startup và khó retry/quan sát. Tác vụ nền dài nên được điều phối bởi job hoặc runner có trạng thái, logging, checkpoint và chính sách lỗi riêng.

Nếu một service phải xác minh dependency ngoài khi khởi động, hãy cân nhắc health check và chính sách readiness phù hợp. Không nên âm thầm bỏ qua lỗi kết nối bắt buộc rồi để ứng dụng nhận traffic trong trạng thái không thể phục vụ.

## 8. Những lỗi thiết kế thường gặp khi lắp ráp dependency

### Tự tạo dependency bên trong service

~~~java
class PlaceOrderService {
    private final OrderRepository orders = new JdbcOrderRepository(
            DataSourceFactory.fromEnvironment());
}
~~~

Service tự chọn công nghệ lưu trữ và tự mở kết nối. Điều này trộn logic ứng dụng với cấu hình hạ tầng, khó thay thế và khiến việc quản lý tài nguyên không rõ ràng. Hãy đưa `OrderRepository` vào constructor và tạo adapter tại composition root.

### Service locator ẩn dependency

~~~java
class PlaceOrderService {
    OrderRepository repository() {
        return ApplicationContextHolder.getBean(OrderRepository.class);
    }
}
~~~

Mã nguồn không thể hiện rõ service cần gì; dependency được lấy ngầm trong lúc chạy. Cách này làm test phải thiết lập container và khiến việc đọc constructor không còn cho biết điều kiện hoạt động. Hãy dùng injection trực tiếp hoặc một factory rõ ràng nếu việc tạo dependency thật sự là một phần của use case.

### Dependency vòng

Nếu `OrderService` cần `CustomerService` và `CustomerService` lại cần `OrderService`, đồ thị có chu trình. Spring có thể báo lỗi khởi tạo hoặc một số cơ chế lazy/proxy có thể che giấu vấn đề. Chu trình thường chỉ ra trách nhiệm đang đặt sai hoặc hai thành phần đang phụ thuộc quá chặt. Hãy tách hợp đồng nhỏ hơn, chuyển điều phối lên một service ứng dụng hoặc đặt quy tắc chung vào mô hình phù hợp.

Không nên xử lý dependency vòng bằng cách thêm `@Lazy` một cách máy móc. Lazy có thể hữu ích cho một số ranh giới khởi tạo có chủ đích, nhưng nó không sửa được quan hệ trách nhiệm sai.

### Một lớp cấu hình trở thành nơi chứa logic nghiệp vụ

Configuration nên tạo và kết nối bean, không nên tính giá đơn hàng, quyết định quyền phê duyệt hoặc thực hiện quy tắc miền. Nếu logic nghiệp vụ nằm trong phương thức `@Bean`, nó khó kiểm thử qua hợp đồng đúng và bị gắn với thời điểm khởi tạo ứng dụng.

### Scope không phù hợp

Đưa dữ liệu mutable của một request vào singleton có thể gây race condition. Dùng request scope cho thành phần được scheduler gọi có thể khiến không có scope hoạt động. Dùng prototype mà không đóng tài nguyên có thể gây rò rỉ. Hãy chọn scope theo vòng đời thực của dữ liệu và trách nhiệm sở hữu tài nguyên.

## 9. Kiểm thử composition root và dependency graph

Nên tách kiểm thử hành vi của lớp khỏi kiểm thử lắp ráp ứng dụng:

| Phạm vi | Điều cần xác nhận | Cách kiểm thử |
|---|---|---|
| Unit test service | Logic ứng dụng hoạt động với hợp đồng dependency | Tạo service trực tiếp, truyền fake repository và kiểm tra kết quả. |
| Test cấu hình | Bean đúng được đăng ký và dependency được giải quyết | Dùng Spring test context nhỏ để kiểm tra bean của cấu hình cần thiết. |
| Context smoke test | Ứng dụng khởi động được với tập cấu hình mục tiêu | Dùng `@SpringBootTest` hoặc context runner phù hợp, cung cấp cấu hình test. |
| Profile/conditional test | Môi trường chọn đúng adapter | Kiểm tra bean được tạo cho profile hoặc property tương ứng. |
| Lifecycle test | Tài nguyên được khởi tạo và đóng đúng | Dùng fake client ghi nhận callback khởi tạo/hủy khi context đóng. |
| Architecture test | Hướng phụ thuộc không bị vi phạm | Kiểm tra controller không phụ thuộc adapter persistence hoặc module nghiệp vụ không import Spring web. |

Không cần khởi động toàn bộ Spring context cho mọi unit test. Test service thuần thường nhanh hơn và chỉ cần fake dependency. Ngược lại, một số lỗi chỉ xuất hiện ở composition root như thiếu bean, nhiều bean cùng loại không có qualifier, component scan sai package hoặc profile cấu hình nhầm; chúng cần context test để phát hiện.

Với tài nguyên được quản lý bởi Spring, nên kiểm tra context đóng sẽ gọi callback hủy khi phù hợp. Với prototype, hãy kiểm tra chính sách giải phóng do consumer sở hữu vì container không tự hoàn tất vòng đời hủy của instance đã bàn giao.

## 10. Quy trình thiết kế composition root

Khi lắp ráp một ứng dụng phân tầng, có thể đi theo trình tự:

1. Xác định các điểm khởi động: HTTP server, worker, CLI, batch hoặc test harness.
2. Xác định hợp đồng mà từng adapter cần gọi và các dependency mà ca sử dụng yêu cầu.
3. Chọn triển khai cho từng port, chẳng hạn JPA repository, JDBC adapter hoặc fake trong test.
4. Gom cấu hình theo trách nhiệm và lấy giá trị từ nguồn cấu hình phù hợp.
5. Chọn scope và xác định ai sở hữu, ai đóng từng tài nguyên.
6. Đăng ký bean tại bootstrap/configuration, ưu tiên constructor injection.
7. Kiểm tra dependency graph không có chu trình ngoài ý muốn và không làm lộ chi tiết tầng dưới.
8. Viết unit test cho hành vi và context test cho việc lắp ráp, profile, lifecycle.

Composition root có thể khác nhau giữa ứng dụng web và worker. Một hệ thống Spring Boot có thể có một context chứa cả controller lẫn scheduler; một triển khai khác có thể dùng hai entry point hoặc hai profile để chỉ đăng ký những adapter cần thiết. Hãy chọn cách tổ chức theo cách triển khai thực tế, không cần ép mọi ứng dụng vào một mẫu bootstrap duy nhất.

## 11. Tự rà soát thiết kế

Khi review một thay đổi về dependency hoặc vòng đời, hãy tự hỏi:

1. Dependency bắt buộc có được khai báo rõ trong constructor không?
2. Đâu là composition root chịu trách nhiệm chọn và tạo triển khai cụ thể?
3. Có lớp nghiệp vụ nào tự tạo JDBC/JPA client, đọc biến môi trường hoặc truy cập service locator không?
4. Bean có scope phù hợp với vòng đời dữ liệu và số thread sử dụng không?
5. Singleton có giữ trạng thái mutable theo request không?
6. Tài nguyên được tạo ở đâu, ai sở hữu và ai chịu trách nhiệm đóng nó?
7. Có dependency vòng hoặc cấu hình profile khiến bean không được đăng ký đúng không?
8. Đã có unit test cho hành vi và context test cho việc lắp ráp quan trọng chưa?

Nếu một thành phần phải biết cách tạo hoặc tìm các thành phần khác để làm việc, hãy xem liệu việc lắp ráp có thể chuyển về composition root. Nếu một bean giữ tài nguyên, hãy xác định vòng đời và chủ sở hữu trước khi chọn callback. Nếu đồ thị có chu trình, hãy xem lại trách nhiệm và hướng phụ thuộc trước khi thêm cơ chế lazy.

## Kết luận

Composition root là nơi ứng dụng chọn triển khai, cung cấp cấu hình và kết nối dependency thành một đồ thị có thể chạy. Trong Spring, vùng này thường gồm bootstrap và các cấu hình bean; các lớp nghiệp vụ khai báo nhu cầu qua constructor và không tự tìm hoặc tạo dependency hạ tầng. Scope phải phù hợp với vòng đời dữ liệu, singleton cần an toàn khi dùng đồng thời và tài nguyên phải có chủ sở hữu chịu trách nhiệm khởi tạo, đóng. Kết hợp composition root rõ ràng, constructor injection và kiểm thử cấu hình giúp ứng dụng phân tầng dễ thay thế, dễ kiểm thử và vận hành ổn định.
