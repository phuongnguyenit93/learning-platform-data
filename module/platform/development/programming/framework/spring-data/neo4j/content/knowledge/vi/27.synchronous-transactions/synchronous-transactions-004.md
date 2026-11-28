# Phối hợp nhiều repository, template và client trong cùng giao dịch

Một nghiệp vụ thường cần nhiều thao tác dữ liệu liên tiếp. Ví dụ, khi đặt hàng, ứng dụng phải đọc khách hàng, kiểm tra và trừ tồn kho, lưu đơn hàng, sau đó ghi lại sự kiện nghiệp vụ. Nếu mỗi thao tác tự mở một transaction riêng, lỗi xảy ra ở bước cuối có thể để lại dữ liệu đã cập nhật ở các bước trước.

Spring Data Neo4j (SDN) tích hợp transaction của Neo4j với cơ chế quản lý giao dịch của Spring. Bạn có thể đặt ranh giới giao dịch ở tầng service bằng **@Transactional**, sau đó gọi nhiều repository, **Neo4jTemplate** và **Neo4jClient** trong cùng một giao dịch đồng bộ. Khi một lỗi phù hợp với quy tắc rollback thoát khỏi phương thức service, các thay đổi trong transaction Neo4j sẽ được hoàn tác cùng nhau.

Sau bài học, bạn có thể:

- Giải thích vai trò của **Neo4jTransactionManager** trong giao dịch đồng bộ.
- Đặt ranh giới giao dịch ở service để phối hợp nhiều repository.
- Dùng repository, **Neo4jTemplate** và **Neo4jClient** trong cùng transaction.
- Chọn **@Transactional** hoặc **TransactionTemplate** theo cách tổ chức mã.
- Kiểm soát rollback, propagation và read-only transaction.
- Nhận biết các thao tác không tham gia transaction Spring, đặc biệt là truy cập trực tiếp Neo4j Java Driver.
- Kiểm tra hành vi commit và rollback trong kiểm thử tích hợp.

## 1. Vì sao cần một ranh giới giao dịch ở service?

Giả sử nghiệp vụ đặt hàng có bốn bước:

1. Tìm khách hàng và sản phẩm.
2. Trừ số lượng tồn kho.
3. Lưu đơn hàng.
4. Ghi sự kiện xác nhận đơn hàng.

Nếu bước 2, 3 và 4 được thực hiện trong các transaction độc lập, lỗi ở bước 4 không tự động hoàn tác việc trừ kho và lưu đơn. Dữ liệu có thể ở trạng thái không nhất quán: tồn kho đã giảm nhưng đơn hàng không có sự kiện xác nhận.

Khi đặt một ranh giới transaction bao quanh toàn bộ nghiệp vụ, các thao tác trên cùng cơ sở dữ liệu Neo4j được commit hoặc rollback như một đơn vị. Ranh giới này không tự làm cho thao tác HTTP, gửi email, ghi file hoặc cập nhật một cơ sở dữ liệu khác trở thành một phần atomic của transaction Neo4j:

~~~mermaid
flowchart TD
    A["Bắt đầu transaction"] --> B["Đọc CustomerRepository"]
    B --> C["Đọc ProductRepository"]
    C --> D["Cập nhật tồn kho qua Neo4jClient"]
    D --> E["Lưu đơn qua OrderRepository"]
    E --> F["Đọc entity qua Neo4jTemplate"]
    F --> G["Ghi OrderEvent qua Neo4jClient"]
    G --> H{"Có lỗi?"}
    H -->|Không| I["COMMIT"]
    H -->|Có| J["ROLLBACK"]
~~~

**@Transactional** thường được đặt ở phương thức service vì service điều phối một use case hoàn chỉnh. Repository vẫn có thể có transaction mặc định riêng, nhưng khi được gọi bên trong một transaction đang tồn tại với propagation mặc định **REQUIRED**, các lời gọi tham gia transaction hiện tại.

## 2. Neo4jTransactionManager và Spring transaction

**Neo4jTransactionManager** là implementation của **PlatformTransactionManager** dành cho transaction gốc của Neo4j. Nó đồng bộ một cặp session/transaction của Neo4j Java Driver với transaction do Spring quản lý.

Với ứng dụng imperative, luồng xử lý thường là:

1. Spring nhận lời gọi tới phương thức service có **@Transactional** qua proxy.
2. Transaction manager bắt đầu transaction Neo4j và gắn tài nguyên giao dịch với ngữ cảnh thực thi hiện tại.
3. Repository, **Neo4jTemplate** và **Neo4jClient** sử dụng transaction đã được quản lý khi thực thi thao tác.
4. Khi phương thức hoàn tất bình thường, Spring yêu cầu commit.
5. Khi exception kích hoạt rollback, Spring yêu cầu Neo4j rollback và kết thúc transaction.

Neo4j là cơ sở dữ liệu transactional. Các thao tác ghi phải nằm trong transaction. Với SDN, transaction manager giúp ứng dụng điều phối transaction bằng annotation hoặc API lập trình thay vì tự mở và đóng transaction cho từng câu lệnh.

### Cấu hình trong Spring Boot

Khi dùng **spring-boot-starter-data-neo4j** trong ứng dụng imperative, Spring Boot tự cấu hình hạ tầng repository và transaction management. Thông thường bạn chỉ cần inject các bean được cấu hình sẵn và đặt **@Transactional** ở service.

### Cấu hình khi không dùng Spring Boot

Trong cấu hình Spring thuần, khai báo transaction manager và bật annotation-driven transaction management:

~~~java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.data.neo4j.core.transaction.Neo4jTransactionManager;

@Configuration
@EnableTransactionManagement
public class Neo4jTransactionConfiguration {

    @Bean
    PlatformTransactionManager transactionManager(Driver driver) {
        return new Neo4jTransactionManager(driver);
    }
}
~~~

Constructor nhận **Driver** tạo transaction manager cho database mặc định. Nếu ứng dụng chọn database động, có thể dùng overload nhận **DatabaseSelectionProvider** để transaction manager sử dụng cùng chính sách chọn database.

Không khai báo thêm transaction manager nếu Spring Boot đã cung cấp đúng bean cho ứng dụng. Khi có nhiều transaction manager trong cùng application context, hãy chỉ rõ manager mà phương thức cần dùng qua thuộc tính **transactionManager** của **@Transactional**.

## 3. Phối hợp nhiều repository trong một transaction

Ví dụ, ba repository cùng tham gia nghiệp vụ đặt hàng:

~~~java
public interface CustomerRepository
        extends Neo4jRepository<Customer, Long> {

    Optional<Customer> findByCustomerCode(String customerCode);
}

public interface ProductRepository
        extends Neo4jRepository<Product, Long> {

    Optional<Product> findBySku(String sku);
}

public interface PurchaseOrderRepository
        extends Neo4jRepository<PurchaseOrder, Long> {
}
~~~

Service điều phối các repository:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final CustomerRepository customerRepository;
    private final ProductRepository productRepository;
    private final PurchaseOrderRepository orderRepository;

    public OrderService(
            CustomerRepository customerRepository,
            ProductRepository productRepository,
            PurchaseOrderRepository orderRepository) {
        this.customerRepository = customerRepository;
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
    }

    @Transactional
    public PurchaseOrder createOrder(
            String customerCode,
            String sku,
            int quantity) {

        Customer customer = customerRepository
            .findByCustomerCode(customerCode)
            .orElseThrow(() -> new CustomerNotFoundException(customerCode));

        Product product = productRepository
            .findBySku(sku)
            .orElseThrow(() -> new ProductNotFoundException(sku));

        if (quantity <= 0 || product.getStock() < quantity) {
            throw new InsufficientStockException(sku);
        }

        product.setStock(product.getStock() - quantity);
        productRepository.save(product);

        PurchaseOrder order = new PurchaseOrder(
            createOrderCode(),
            customer,
            product,
            quantity
        );

        return orderRepository.save(order);
    }
}
~~~

Các phương thức repository có thể tự tạo transaction nếu được gọi độc lập. Khi được gọi trong **createOrder()**, propagation mặc định **REQUIRED** khiến chúng tham gia transaction do service mở. Nếu việc lưu đơn hàng thất bại và exception làm transaction rollback, thay đổi tồn kho được lưu trước đó cũng bị rollback.

Trong ví dụ này, kiểm tra tồn kho và trừ kho được thực hiện qua đọc rồi ghi entity để minh họa transaction orchestration. Với hệ thống có nhiều request cập nhật cùng sản phẩm đồng thời, hãy cân nhắc cập nhật có điều kiện bằng một câu Cypher nguyên tử để tránh lost update hoặc bán vượt tồn kho.

## 4. Kết hợp repository, Neo4jTemplate và Neo4jClient

Repository phù hợp với CRUD và query method theo entity. **Neo4jTemplate** hỗ trợ các thao tác có mapping entity rõ ràng. **Neo4jClient** cung cấp API truy vấn trực tiếp và ánh xạ kết quả tùy chỉnh. Cả ba có thể tham gia cùng transaction Spring nếu dùng chung hạ tầng Driver và transaction manager.

Ví dụ mở rộng use case đặt hàng:

- **CustomerRepository** đọc khách hàng.
- **ProductRepository** đọc sản phẩm.
- **PurchaseOrderRepository** lưu đơn hàng.
- **Neo4jTemplate** đọc lại entity theo Cypher tùy chỉnh.
- **Neo4jClient** cập nhật tồn kho có điều kiện và ghi sự kiện.

~~~java
import java.util.Map;

import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final CustomerRepository customerRepository;
    private final ProductRepository productRepository;
    private final PurchaseOrderRepository orderRepository;
    private final Neo4jTemplate neo4jTemplate;
    private final Neo4jClient neo4jClient;

    public OrderApplicationService(
            CustomerRepository customerRepository,
            ProductRepository productRepository,
            PurchaseOrderRepository orderRepository,
            Neo4jTemplate neo4jTemplate,
            Neo4jClient neo4jClient) {
        this.customerRepository = customerRepository;
        this.productRepository = productRepository;
        this.orderRepository = orderRepository;
        this.neo4jTemplate = neo4jTemplate;
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public PurchaseOrder placeOrder(
            String customerCode,
            String sku,
            int quantity) {

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải lớn hơn 0");
        }

        Customer customer = customerRepository
            .findByCustomerCode(customerCode)
            .orElseThrow(() -> new CustomerNotFoundException(customerCode));

        productRepository.findBySku(sku)
            .orElseThrow(() -> new ProductNotFoundException(sku));

        neo4jClient.query("""
            MATCH (p:Product {sku: $sku})
            WHERE p.stock >= $quantity
            SET p.stock = p.stock - $quantity
            RETURN p.stock AS remainingStock
            """)
            .bind(sku).to("sku")
            .bind(quantity).to("quantity")
            .fetchAs(Long.class)
            .mappedBy((types, record) ->
                record.get("remainingStock").asLong()
            )
            .one()
            .orElseThrow(() -> new InsufficientStockException(sku));

        PurchaseOrder order = new PurchaseOrder(
            createOrderCode(),
            customer,
            sku,
            quantity
        );
        PurchaseOrder saved = orderRepository.save(order);

        PurchaseOrder reloaded = neo4jTemplate.findOne(
            """
            MATCH (o:PurchaseOrder {orderCode: $orderCode})
            RETURN o
            """,
            Map.of("orderCode", saved.getOrderCode()),
            PurchaseOrder.class
        ).orElseThrow();

        neo4jClient.query("""
            MATCH (o:PurchaseOrder {orderCode: $orderCode})
            CREATE (o)-[:HAS_EVENT]->(
                :OrderEvent {
                    eventType: $eventType,
                    occurredAt: datetime()
                }
            )
            """)
            .bind(saved.getOrderCode()).to("orderCode")
            .bind("PLACED").to("eventType")
            .run();

        return reloaded;
    }
}
~~~

Ví dụ trên minh họa việc dùng chung transaction, không phải mẫu triển khai đầy đủ cho mọi hệ thống đặt hàng. Những lớp entity, exception và phương thức tạo mã đơn là thành phần miền của ứng dụng. Câu lệnh cập nhật kho kiểm tra số lượng trong cùng một lệnh Cypher để thao tác trừ kho có điều kiện.

Nếu một thao tác sau khi trừ kho thất bại, chẳng hạn lưu đơn hàng hoặc ghi **OrderEvent** ném runtime exception, transaction Neo4j sẽ rollback cả phần giảm tồn kho, node đơn hàng và node sự kiện. Việc đọc lại bằng **Neo4jTemplate** cũng sử dụng transaction hiện tại nên nhìn thấy dữ liệu vừa ghi trong cùng transaction.

### Điều kiện để Neo4jClient tham gia transaction

**Neo4jClient** được SDN thiết kế để tích hợp với transaction management của Spring. Nếu tự tạo client bằng **Neo4jClient.create(driver)**, phải dùng đúng instance **Driver** đã được dùng để tạo **Neo4jTransactionManager**. Nếu dùng một Driver khác, client không thể đồng bộ transaction với manager đó.

Trong ứng dụng Spring Boot, nên inject bean **Neo4jClient** được cấu hình sẵn. Không tự tạo thêm Driver hoặc client riêng nếu không có nhu cầu cấu hình đặc biệt.

### Vì sao không dùng trực tiếp Driver trong service?

Neo4j Java Driver là API cấp thấp và các transaction tự mở qua **driver.session()** không tự tích hợp với transaction Spring đang chạy. Ví dụ, nếu service có **@Transactional** nhưng một đoạn mã tự mở session rồi gọi **executeWrite()**, thao tác đó có transaction riêng và không được rollback cùng transaction Spring.

Khi cần truy vấn Cypher tùy chỉnh trong transaction Spring, hãy ưu tiên **Neo4jClient**. Chỉ dùng session/transaction Driver độc lập khi bạn chủ động thiết kế một ranh giới giao dịch riêng và hiểu rõ hệ quả.

## 5. Dùng TransactionTemplate khi cần điều khiển bằng mã

**@Transactional** phù hợp với ranh giới giao dịch khai báo ở public method của Spring bean. Khi cần tạo transaction bên trong một phương thức private, một helper nội bộ hoặc một đoạn mã có ranh giới động, dùng **TransactionTemplate**.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ManualOrderService {

    private final TransactionTemplate transactionTemplate;
    private final PurchaseOrderRepository orderRepository;
    private final Neo4jClient neo4jClient;

    public ManualOrderService(
            PlatformTransactionManager transactionManager,
            PurchaseOrderRepository orderRepository,
            Neo4jClient neo4jClient) {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.orderRepository = orderRepository;
        this.neo4jClient = neo4jClient;
    }

    public PurchaseOrder saveOrderAndEvent(PurchaseOrder order) {
        return transactionTemplate.execute(status -> {
            PurchaseOrder saved = orderRepository.save(order);

            neo4jClient.query("""
                MATCH (o:PurchaseOrder {orderCode: $orderCode})
                CREATE (o)-[:HAS_EVENT]->(
                    :OrderEvent {eventType: $eventType}
                )
                """)
                .bind(saved.getOrderCode()).to("orderCode")
                .bind("CREATED").to("eventType")
                .run();

            return saved;
        });
    }
}
~~~

**TransactionTemplate.execute()** bắt đầu transaction theo cấu hình của template, thực thi callback rồi commit khi callback hoàn tất bình thường. Nếu callback ném exception, transaction bị rollback theo quy tắc của transaction manager. Bạn cũng có thể gọi **status.setRollbackOnly()** khi muốn đánh dấu rollback mà không ném exception ra ngoài.

TransactionTemplate mặc định dùng propagation **REQUIRED**. Có thể cấu hình các thuộc tính như read-only, timeout hoặc propagation trước khi gọi **execute()**:

~~~java
TransactionTemplate readOnlyTemplate =
    new TransactionTemplate(transactionManager);

readOnlyTemplate.setReadOnly(true);
~~~

Dùng template khi ranh giới giao dịch không thuận tiện thể hiện bằng annotation. Với service method công khai thông thường, **@Transactional** thường dễ đọc và ít mã hơn.

## 6. Propagation: lời gọi bên trong tham gia transaction nào?

Propagation xác định Spring xử lý transaction khi một phương thức được gọi trong lúc đã có transaction hay chưa.

| Propagation | Hành vi | Tình huống |
|---|---|---|
| **REQUIRED** | Tham gia transaction hiện tại; nếu chưa có thì tạo mới | Mặc định, phù hợp cho các repository/service cùng use case |
| **REQUIRES_NEW** | Tạm ngưng transaction hiện tại và mở transaction mới | Một thao tác cần commit độc lập với use case bên ngoài |
| **SUPPORTS** | Tham gia nếu có transaction; nếu không thì chạy không transaction | Thao tác có thể đọc độc lập, nhưng cần cân nhắc nếu có ghi |
| **MANDATORY** | Yêu cầu phải có transaction hiện tại; nếu không thì báo lỗi | Hàm nội bộ chỉ được gọi trong một use case có transaction |
| **NOT_SUPPORTED** | Tạm ngưng transaction hiện tại và chạy không transaction | Công việc không nên nằm trong transaction đang có |
| **NEVER** | Báo lỗi nếu đang có transaction | Chặn rõ ràng việc gọi trong transaction |

Ví dụ:

~~~java
@Transactional
public void placeOrder() {
    inventoryService.reserve();       // REQUIRED: tham gia transaction hiện tại
    auditService.recordSeparately();  // REQUIRES_NEW: transaction độc lập
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordSeparately() {
    // Thao tác được commit hoặc rollback độc lập.
}
~~~

Nếu **recordSeparately()** commit thành công rồi transaction bên ngoài rollback, bản ghi audit vẫn tồn tại. Đây là hành vi có chủ đích của **REQUIRES_NEW**; đừng dùng nó cho dữ liệu cần rollback đồng bộ với đơn hàng.

## 7. Rollback và xử lý exception

Theo mặc định của Spring, transaction rollback khi phương thức thoát ra với **RuntimeException** hoặc **Error**. Checked exception không làm rollback theo mặc định.

Ví dụ cấu hình rollback cả checked exception:

~~~java
@Transactional(rollbackFor = OrderValidationException.class)
public PurchaseOrder placeOrder() throws OrderValidationException {
    // Các thao tác ghi graph.
    throw new OrderValidationException("Đơn hàng không hợp lệ");
}
~~~

Một số nguyên tắc:

- Để exception thoát khỏi phương thức transaction nếu muốn Spring áp dụng rollback rule.
- Nếu bắt exception bên trong và không ném lại, Spring có thể coi callback hoàn tất bình thường và commit.
- Nếu cần bắt lỗi để chuyển thành kết quả nghiệp vụ, hãy đánh dấu transaction rollback-only trước khi trả kết quả.
- Đừng dùng **noRollbackFor** cho exception mà dữ liệu graph cần được hoàn tác.

Nếu exception được bắt và xử lý, hãy quyết định rõ liệu nghiệp vụ có thể tiếp tục hay toàn bộ transaction phải rollback. Không nuốt exception sau một phần thao tác ghi rồi giả định Spring tự rollback.

Nếu cần thực hiện công việc bên ngoài Neo4j như gửi email hoặc phát thông điệp, hãy cân nhắc ghi một outbox event trong cùng transaction Neo4j rồi xử lý việc gửi sau khi commit. Điều này tránh giữ một transaction graph mở trong lúc chờ hệ thống bên ngoài và giúp xử lý retry rõ ràng hơn.

## 8. Read-only transaction và Neo4j cluster

Với Neo4j Causal Cluster, transaction read-only giúp hệ thống định tuyến các thao tác đọc tới read replica khi phù hợp, giảm tải cho primary. Hãy đánh dấu rõ các use case chỉ đọc:

~~~java
@Transactional(readOnly = true)
public Optional<CustomerSummary> getCustomer(String customerCode) {
    return customerRepository.findByCustomerCode(customerCode)
        .map(this::toSummary);
}
~~~

Các phương thức tìm kiếm dựng sẵn như **findById**, **findAllById**, **findAll** và các phương thức tồn tại được định nghĩa sẵn của repository được SDN đánh dấu read-only. Tuy nhiên, SDN và Neo4j Java Driver không phân tích nội dung Cypher để tự biết một custom query có ghi hay không. Vì vậy, custom query hoặc repository method có thể thực thi lệnh ghi cần được đánh dấu read-only chỉ khi chắc chắn nó không sửa dữ liệu.

Không đặt **readOnly = true** trên một service có thao tác **save**, **MERGE**, **CREATE**, **DELETE** hoặc cập nhật property. Một transaction read-only không phù hợp cho use case vừa đọc vừa ghi.

## 9. Ranh giới của giao dịch đồng bộ

Giao dịch imperative của Spring được gắn với luồng thực thi đồng bộ hiện tại. Điều này dẫn đến một số giới hạn:

- Gọi repository, template và client tuần tự trong cùng phương thức **@Transactional** sẽ tham gia transaction hiện tại.
- Gọi một phương thức **@Transactional** khác thông qua Spring proxy có thể tham gia transaction theo propagation đã khai báo.
- Tự gọi một phương thức khác trong cùng instance (self-invocation) không đi qua proxy, nên annotation trên phương thức được gọi không tạo ranh giới mới.
- Gọi thao tác qua **@Async**, thread mới, parallel stream hoặc callback bất đồng bộ không tự động tham gia transaction đồng bộ của thread ban đầu.
- Gọi transaction trực tiếp qua Neo4j Driver tạo transaction độc lập, không được Spring quản lý tự động.

Nếu cần xử lý bất đồng bộ hoặc reactive, hãy dùng **ReactiveNeo4jClient**, **ReactiveNeo4jTemplate**, reactive repository và **ReactiveNeo4jTransactionManager** theo mô hình Reactor. Reactive transaction được truyền qua Reactor Context, không phải transaction đồng bộ gắn với thread.

## 10. Kiểm thử rollback

Một kiểm thử tích hợp nên xác minh thay đổi ở nhiều thành phần cùng rollback khi có lỗi. Với Spring Boot, **@DataNeo4jTest** hỗ trợ hạ tầng kiểm thử SDN và các test imperative mặc định chạy trong transaction rồi rollback khi kết thúc test.

Ví dụ kiểm tra trạng thái tồn kho sau một nghiệp vụ thất bại:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class OrderTransactionTests {

    @Autowired
    private ProductRepository productRepository;

    @Autowired
    private OrderApplicationService orderService;

    @Test
    void shouldRollbackStockAndOrderWhenAuditFails() {
        // Chuẩn bị product có stock = 10 và customer hợp lệ.

        assertThatThrownBy(() ->
            orderService.placeOrder("C-100", "SKU-01", 3)
        ).isInstanceOf(RuntimeException.class);

        Product product = productRepository.findBySku("SKU-01")
            .orElseThrow();

        assertThat(product.getStock()).isEqualTo(10);
        // Xác minh không có PurchaseOrder hoặc OrderEvent được commit.
    }
}
~~~

Để kiểm thử rollback do lỗi ở bước cuối, có thể dùng test double cho thành phần ghi sự kiện hoặc cấu hình lỗi truy vấn có chủ đích. Khi dùng **@DataNeo4jTest**, lưu ý test mặc định đã có transaction riêng và rollback khi kết thúc. Nếu muốn kiểm tra transaction của service độc lập, hãy tắt transaction bao ngoài của test bằng **@Transactional(propagation = Propagation.NOT_SUPPORTED)**. Khi đó lời gọi service sẽ mở transaction riêng; sau khi exception thoát ra, test có thể đọc lại dữ liệu đã commit trước use case để xác minh các thay đổi trong use case đã rollback.

Các test cần kiểm tra nhiều ranh giới khác nhau:

- Thành công: tồn kho giảm, đơn hàng và sự kiện đều tồn tại.
- Thất bại trước khi lưu đơn: không có thay đổi tồn kho được commit.
- Thất bại sau khi lưu đơn: tồn kho, đơn hàng và sự kiện cùng rollback.
- Lời gọi có **REQUIRES_NEW**: xác minh dữ liệu độc lập vẫn được commit nếu transaction ngoài rollback.

Không dùng kiểm thử chỉ gọi từng repository riêng lẻ để kết luận service orchestration đã atomic. Hãy gọi đúng public service method qua Spring proxy trong kiểm thử tích hợp.

## 11. Những lỗi thường gặp

**Đặt @Transactional ở từng repository thay vì service boundary.** Mỗi repository có thể tự chạy transaction khi gọi riêng, nhưng các lời gọi độc lập không mặc nhiên thuộc cùng một transaction. Đặt annotation ở service để gom cả use case.

**Tạo Neo4jClient bằng một Driver khác.** Client không thể đồng bộ transaction với manager dùng Driver khác. Hãy inject bean được cấu hình sẵn hoặc dùng cùng Driver instance.

**Dùng raw Driver bên trong @Transactional.** Transaction mở trực tiếp qua session/executeWrite là transaction riêng. Dùng Neo4jClient khi cần tham gia transaction Spring.

**Bắt exception rồi tiếp tục như thể chưa có lỗi.** Nếu exception bị nuốt, transaction có thể commit. Hãy ném lại hoặc đánh dấu rollback-only.

**Cho rằng checked exception luôn rollback.** Theo mặc định, Spring rollback RuntimeException và Error. Dùng rollbackFor cho checked exception cần rollback.

**Dùng REQUIRES_NEW cho mọi lời gọi.** Mỗi lần dùng propagation này tạo transaction độc lập. Dữ liệu có thể được commit dù use case bên ngoài thất bại.

**Đặt readOnly trên use case có ghi.** Read-only phù hợp cho luồng chỉ đọc, đặc biệt khi dùng cluster có read replica.

**Gọi phương thức transaction qua self-invocation.** Lời gọi nội bộ cùng instance không đi qua proxy. Đặt ranh giới ở public service method được gọi từ bean khác hoặc dùng TransactionTemplate.

**Chuyển sang thread khác giữa transaction.** Transaction đồng bộ không tự truyền sang thread mới hoặc tác vụ bất đồng bộ. Thiết kế riêng ranh giới giao dịch cho công việc đó.

## 12. Tự kiểm tra

1. **Neo4jTransactionManager** đồng bộ những tài nguyên nào với Spring transaction?
2. Vì sao nên đặt **@Transactional** ở service khi use case gọi nhiều repository?
3. Điều kiện nào giúp **Neo4jClient** tham gia transaction do Spring quản lý?
4. Vì sao transaction mở trực tiếp bằng Neo4j Java Driver không tự rollback cùng transaction Spring?
5. Propagation **REQUIRED** và **REQUIRES_NEW** khác nhau như thế nào?
6. Spring rollback theo mặc định với những loại exception nào?
7. Khi nào cần dùng **TransactionTemplate** thay cho annotation?
8. Vì sao phải đánh dấu rõ read-only cho một custom query chỉ đọc khi chạy trên Neo4j cluster?

**Bài tập thực hành:** Xây dựng use case đặt hàng có ba repository để đọc khách hàng, đọc sản phẩm và lưu đơn. Dùng **Neo4jClient** để cập nhật tồn kho có điều kiện và tạo node sự kiện; dùng **Neo4jTemplate** để đọc lại đơn hàng theo mã. Đặt **@Transactional** ở public service method. Viết kiểm thử cho trường hợp thành công và trường hợp cố ý ném exception sau khi đã lưu đơn để chứng minh tồn kho, đơn hàng và sự kiện cùng rollback. Sau đó thay một thao tác phụ bằng **REQUIRES_NEW**, quan sát dữ liệu nào còn tồn tại khi transaction ngoài thất bại.

## Tài liệu tham khảo

- [Spring Data Neo4j — FAQ: Transaction orchestration, TransactionTemplate and read-only transactions](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j API — Neo4jTransactionManager](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
- [Spring Data Neo4j — Neo4jClient and transaction integration](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Spring Boot — Working with Neo4j](https://docs.spring.io/spring-boot/reference/data/nosql.html)
- [Spring Framework — @Transactional settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling back a declarative transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
