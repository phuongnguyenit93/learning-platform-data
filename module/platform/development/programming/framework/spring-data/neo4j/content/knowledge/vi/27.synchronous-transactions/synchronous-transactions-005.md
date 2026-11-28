# Neo4jTransactionManager và tài nguyên gắn với luồng thực thi

Bài học này thuộc chương **Giao dịch đồng bộ** của module **SPRING_DATA_NEO4J**. Trong ứng dụng Spring Data Neo4j chạy theo kiểu imperative (đồng bộ), một service có thể gọi nhiều repository, `Neo4jTemplate` hoặc `Neo4jClient` trong cùng một nghiệp vụ. Để các lời gọi này cùng đọc và ghi trên một giao dịch Neo4j, Spring cần quản lý và chia sẻ đúng session cùng transaction đang hoạt động.

`Neo4jTransactionManager` là implementation của Spring `PlatformTransactionManager` dành cho native transaction của Neo4j. Nó đồng bộ một cặp session/transaction của Neo4j Java Driver với transaction Spring. Với mô hình imperative, Spring giữ tài nguyên giao dịch trong ngữ cảnh gắn với luồng thực thi hiện tại. Các thành phần SDN sử dụng cùng `Driver` có thể tìm thấy và tham gia transaction đó.

Điểm cần nhớ là **Driver có thể được chia sẻ giữa nhiều luồng, còn Session và Transaction thuộc về một giao dịch cụ thể**. Không lưu session vào singleton service, không chuyển session sang luồng khác và không giả định một lời gọi trực tiếp Java Driver tự động tham gia transaction do Spring quản lý.

## 1. Vai trò của Neo4jTransactionManager

`Neo4jTransactionManager` triển khai `PlatformTransactionManager` và quản lý native transaction thông qua Neo4j Java Driver. Khi Spring bắt đầu một transaction, manager tạo hoặc lấy session phù hợp, bắt đầu transaction native và đồng bộ vòng đời của chúng với transaction Spring.

Trong một transaction imperative, có thể hình dung các tài nguyên chính như sau:

| Tài nguyên | Vai trò | Vòng đời |
|---|---|---|
| `Driver` | Kết nối tới Neo4j, quản lý connection pool và tạo session | Thường là bean dùng chung trong application context |
| `Session` | Kênh làm việc với database và quản lý transaction native | Gắn với một transaction; được đóng khi hoàn tất |
| Native `Transaction` | Nhóm các câu Cypher phải commit hoặc rollback cùng nhau | Được bắt đầu, commit hoặc rollback bởi transaction manager |
| Spring transaction context | Lưu trạng thái và tài nguyên giao dịch cho luồng hiện tại | Tồn tại trong ranh giới Spring transaction |

Class `Neo4jTransactionManager` đồng bộ một cặp native session/transaction với transaction Spring. Khi có transaction hiện hành, `Neo4jClient` có thể lấy native transaction tương ứng từ hạ tầng SDN. Nếu không có transaction Spring đang chạy, không có native transaction được quản lý để tái sử dụng theo cơ chế này.

## 2. Tài nguyên gắn với luồng thực thi là gì?

Trong mô hình transaction imperative của Spring, tài nguyên giao dịch được lưu trong `TransactionSynchronizationManager` theo ngữ cảnh của thread hiện tại. Cơ chế này thường được gọi là **thread-bound resource**.

Với SDN, `Driver` là đối tượng đồng bộ quan trọng để xác định tài nguyên Neo4j tương ứng. Khi `Neo4jTransactionManager` mở transaction, nó đăng ký tài nguyên liên quan với Spring. Các lời gọi SDN sử dụng đúng `Driver` trong cùng thread và cùng transaction context có thể tham gia transaction hiện hành.

Có thể hình dung luồng xử lý như sau:

```text
Thread T1
  |
  +-- Spring @Transactional bắt đầu
  |      |
  |      +-- Neo4jTransactionManager mở Session S1
  |      +-- Bắt đầu native Transaction TX1
  |      +-- Gắn tài nguyên Neo4j vào transaction context của T1
  |
  +-- PersonRepository.save(...)
  |      +-- Sử dụng TX1
  |
  +-- Neo4jTemplate.findAll(...)
  |      +-- Sử dụng TX1
  |
  +-- Neo4jClient.query(...)
  |      +-- Sử dụng TX1
  |
  +-- Spring commit hoặc rollback
         +-- Kết thúc TX1
         +-- Đóng Session S1 và giải phóng tài nguyên
```

Đây là mô hình khái niệm về việc chia sẻ transaction. Ứng dụng không cần tự lấy `Session` hoặc `Transaction` từ thread context. Repository, template và client được cấu hình cùng hạ tầng SDN sẽ xử lý việc tham gia transaction.

## 3. Vì sao cùng thread và cùng Driver lại quan trọng?

Việc tái sử dụng transaction dựa trên ngữ cảnh hiện hành. Các yếu tố quan trọng gồm:

- Lời gọi đang chạy trong cùng thread imperative có transaction Spring.
- Các thành phần SDN dùng cùng instance `Driver` mà transaction manager quản lý.
- Database selection và user selection của client phù hợp với transaction đã mở.
- Lời gọi đi qua hạ tầng Spring/SDN tích hợp transaction.

Nếu service gọi repository rồi gọi `Neo4jClient` được cấu hình với cùng Driver và database, hai thao tác có thể tham gia cùng native transaction. Nếu tạo một `Driver` khác hoặc tự mở session bằng Driver độc lập, thao tác đó không tự động dùng transaction đang được Spring quản lý.

Với cấu hình nhiều database hoặc impersonation, `DatabaseSelectionProvider` và `UserSelectionProvider` cần được chia sẻ nhất quán giữa `Neo4jClient` và `Neo4jTransactionManager`. Một transaction đã bắt đầu cho database/user cụ thể không thể được xem như transaction dùng chung cho mọi database hoặc mọi user.

## 4. Cấu hình transaction manager

### Với Spring Boot

Khi dùng `spring-boot-starter-data-neo4j`, Spring Boot tự cấu hình `Driver`, `Neo4jClient`, `Neo4jTemplate` và transaction manager theo cấu hình kết nối. Trong trường hợp thông thường, không cần tự tạo một `Neo4jTransactionManager` thứ hai.

Ví dụ cấu hình kết nối:

```yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: secret
  data:
    neo4j:
      database: graphdb
```

Ứng dụng có thể dùng `@Transactional` ở service để mở ranh giới giao dịch. Spring Boot quản lý transaction infrastructure và sử dụng driver đã cấu hình.

### Cấu hình tường minh khi không dùng Boot auto-configuration

Với cấu hình thủ công, khai báo transaction manager dựa trên đúng `Driver` và `DatabaseSelectionProvider` được dùng cho client:

```java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.Neo4jTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class Neo4jTransactionConfiguration {

    @Bean
    PlatformTransactionManager transactionManager(
            Driver driver,
            DatabaseSelectionProvider databaseSelectionProvider) {
        return new Neo4jTransactionManager(driver, databaseSelectionProvider);
    }
}
```

Ví dụ này giả định `Driver` và `DatabaseSelectionProvider` đã được khai báo trong application context. Nếu kế thừa `AbstractNeo4jConfig`, lớp cấu hình nền đã cung cấp các bean SDN cần thiết; không khai báo trùng bean transaction manager trừ khi đang chủ động thay thế cấu hình.

## 5. Repository, Template và Client cùng tham gia một transaction

Một service có thể phối hợp nhiều abstraction SDN trong một phương thức:

```java
import com.example.graph.domain.Order;
import com.example.graph.repository.OrderRepository;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.neo4j.core.Neo4jTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final Neo4jTemplate neo4jTemplate;
    private final Neo4jClient neo4jClient;

    public OrderService(
            OrderRepository orderRepository,
            Neo4jTemplate neo4jTemplate,
            Neo4jClient neo4jClient) {
        this.orderRepository = orderRepository;
        this.neo4jTemplate = neo4jTemplate;
        this.neo4jClient = neo4jClient;
    }

    @Transactional
    public void placeOrder(Order order) {
        orderRepository.save(order);

        neo4jTemplate.save(order.getCustomer());

        neo4jClient.query("""
                MATCH (c:Customer {id: $customerId})
                SET c.lastOrderAt = datetime()
                """)
            .bind(order.getCustomer().getId()).to("customerId")
            .run();
    }
}
```

Vì cả ba abstraction dùng cùng hạ tầng SDN trong một lời gọi service có `@Transactional`, các thao tác có thể tham gia cùng transaction Neo4j. Nếu câu lệnh cuối thất bại và exception làm transaction rollback, các thay đổi trước đó trong transaction cũng được rollback.

`Neo4jClient` là điểm tích hợp giữa SDN và transaction Spring. Nó cho phép chạy Cypher tùy biến mà vẫn tham gia transaction hiện hành. Không cần tự gọi `Neo4jTransactionManager.retrieveTransaction(...)`; phương thức này là cơ chế nội bộ mà SDN dùng để cung cấp native transaction cho client.

## 6. TransactionTemplate cho thao tác đồng bộ lập trình thủ công

Khi không muốn dùng annotation, hoặc cần mở transaction bên trong một private method, có thể sử dụng `TransactionTemplate`:

```java
import com.example.graph.repository.InventoryRepository;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class InventoryService {

    private final TransactionTemplate transactionTemplate;
    private final InventoryRepository inventoryRepository;
    private final Neo4jClient neo4jClient;

    public InventoryService(
            PlatformTransactionManager transactionManager,
            InventoryRepository inventoryRepository,
            Neo4jClient neo4jClient) {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.inventoryRepository = inventoryRepository;
        this.neo4jClient = neo4jClient;
    }

    public void reserve(String sku, int quantity) {
        transactionTemplate.executeWithoutResult(status -> {
            inventoryRepository.decreaseAvailable(sku, quantity);

            neo4jClient.query("""
                    MATCH (p:Product {sku: $sku})
                    SET p.reserved = coalesce(p.reserved, 0) + $quantity
                    """)
                .bind(sku).to("sku")
                .bind(quantity).to("quantity")
                .run();
        });
    }
}
```

`TransactionTemplate` sử dụng cùng `PlatformTransactionManager` như `@Transactional`. Các thao tác repository và client bên trong callback tham gia transaction được mở bởi template. Nếu callback ném exception, transaction được rollback theo quy tắc của Spring.

Nếu ứng dụng có nhiều transaction manager, hãy inject đúng manager bằng `@Qualifier` khi tạo `TransactionTemplate`; nếu không, Spring có thể chọn manager mặc định không quản lý Neo4j.

## 7. Vòng đời của tài nguyên transaction

Một transaction imperative thường đi qua các giai đoạn:

1. **Bắt đầu:** Spring gọi `Neo4jTransactionManager` khi phương thức transactional được gọi.
2. **Mở tài nguyên:** manager tạo session và native transaction phù hợp với Driver, database và user selection.
3. **Gắn tài nguyên:** tài nguyên được đăng ký trong transaction context của thread hiện tại để các thao tác SDN có thể tái sử dụng.
4. **Thực thi:** repository, template và client sử dụng native transaction hiện hành.
5. **Hoàn tất:** Spring yêu cầu commit hoặc rollback native transaction.
6. **Dọn dẹp:** session được đóng và tài nguyên được giải phóng khỏi transaction context.

Ứng dụng không tự đóng session do `Neo4jTransactionManager` quản lý. Nếu tự mở session, ứng dụng chịu trách nhiệm đóng session bằng try-with-resources và quản lý transaction độc lập.

## 8. Tài nguyên thread-bound không truyền sang thread khác

Transaction imperative được gắn với thread hiện tại. Nếu code chuyển sang thread khác, thread mới không tự nhận transaction resource của thread ban đầu.

Ví dụ không chia sẻ transaction như mong đợi:

Giả sử service đã inject hai repository và có các biến `person`, `movie` cần lưu:

```java
import java.util.concurrent.CompletableFuture;

import com.example.graph.domain.Movie;
import com.example.graph.domain.Person;
import com.example.graph.repository.MovieRepository;
import com.example.graph.repository.PersonRepository;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void updateGraph() {
    personRepository.save(person);

    CompletableFuture.runAsync(() -> {
        movieRepository.save(movie);
    });
}
```

Lời gọi trong `CompletableFuture` chạy trên một thread khác. Nó không tự tham gia transaction đang mở ở thread gọi `updateGraph()`. Việc method ngoài commit hoặc rollback không điều khiển transaction độc lập được tạo ra trong thread mới.

Các tình huống tương tự gồm:

- `@Async` hoặc executor service.
- `CompletableFuture` và callback chạy trên thread pool.
- `parallelStream()` hoặc xử lý song song.
- Tự tạo `Thread`.
- Gửi công việc sang scheduler hoặc worker khác.

Nếu công việc ở thread khác cần transaction, hãy gọi một service method công khai có `@Transactional` qua Spring proxy trong worker đó. Transaction mới được mở trên thread worker. Nếu cần một đơn vị nghiệp vụ nguyên tử duy nhất, không tách các thao tác database thành các thread độc lập; hãy thực hiện tuần tự trong cùng transaction hoặc thiết kế cơ chế điều phối phù hợp.

Ví dụ worker mở transaction riêng:

```java
import com.example.graph.domain.Movie;
import com.example.graph.repository.MovieRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MovieWorker {

    private final MovieRepository movieRepository;

    public MovieWorker(MovieRepository movieRepository) {
        this.movieRepository = movieRepository;
    }

    @Transactional
    public void saveMovie(Movie movie) {
        movieRepository.save(movie);
    }
}
```

Worker phải được gọi thông qua bean Spring được proxy. `@Transactional` dựa trên proxy; gọi một method transactional khác bằng `this.saveMovie(...)` trong cùng object không tạo transaction mới hoặc áp dụng propagation riêng cho method đó.

### Phân biệt với transaction reactive

Thread-bound resource là mô hình của transaction imperative. Với `ReactiveNeo4jTransactionManager`, Spring quản lý transaction trong Reactor Context của publisher thay vì gắn nó vào một thread cố định. Một reactive chain có thể chuyển thread mà transaction context vẫn được truyền theo reactive subscription. Vì vậy, không áp dụng quy tắc `ThreadLocal` của imperative cho reactive flow và không trộn imperative repository với reactive client nếu kỳ vọng chúng cùng tham gia một transaction.

## 9. Driver có thể chia sẻ, Session không thể chia sẻ tùy ý

Neo4j Java Driver được thiết kế để dùng chung giữa các thread. `Session` không thread-safe; mỗi thread cần session riêng. `Transaction` cũng gắn với session và không nên được truyền qua các thread để dùng đồng thời.

Trong ứng dụng SDN:

- Inject và dùng chung bean `Driver` do Spring quản lý.
- Để `Neo4jTransactionManager` quản lý session/transaction của Spring transaction.
- Không lưu `Session` hoặc `Transaction` vào field của singleton service.
- Không truyền native transaction đang được Spring quản lý sang executor hoặc callback chạy thread khác.
- Nếu dùng Driver trực tiếp ngoài Spring transaction, mở session trong phạm vi method và đóng bằng try-with-resources.

Ví dụ sử dụng Driver độc lập:

```java
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

try (Session session = driver.session()) {
    session.executeWrite(tx -> {
        tx.run("CREATE (:AuditEvent {name: $name})", Map.of("name", "import"));
        return null;
    });
}
```

Đoạn mã này tự mở session và transaction do Driver quản lý. Nó không tự tham gia transaction Spring đang hoạt động trong cùng method. Nếu cần cùng một transaction Spring, hãy dùng `Neo4jClient`, repository hoặc template; các abstraction này đã tích hợp transaction management.

## 10. Propagation và việc tham gia transaction hiện hành

`@Transactional` mặc định dùng `Propagation.REQUIRED`. Nếu thread hiện tại đã có transaction được quản lý bởi cùng transaction manager, lời gọi tiếp theo tham gia transaction đó. Nếu chưa có, Spring mở transaction mới.

```java
import com.example.graph.domain.Customer;
import com.example.graph.domain.Order;
import com.example.graph.repository.CustomerRepository;
import com.example.graph.repository.OrderRepository;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void createCustomerAndOrder(Customer customer, Order order) {
    customerRepository.save(customer);
    orderRepository.save(order);
}
```

Hai repository call cùng nằm trong transaction do service mở. Nếu `createOrder()` ở service khác cũng dùng `REQUIRED` và được gọi qua Spring proxy, method đó tham gia transaction hiện hành.

`REQUIRES_NEW` yêu cầu một transaction độc lập. Spring tạm ngưng transaction hiện hành, mở transaction mới, rồi khôi phục transaction ngoài sau khi transaction trong hoàn tất:

Method này nên nằm trên một Spring bean riêng và được gọi qua proxy để propagation `REQUIRES_NEW` có hiệu lực:

```java
import com.example.graph.domain.AuditEvent;
import com.example.graph.repository.AuditRepository;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeAuditEvent(AuditEvent event) {
    auditRepository.save(event);
}
```

Nếu transaction ngoài rollback sau khi transaction audit đã commit, bản ghi audit trong transaction độc lập vẫn có thể được giữ lại. Chỉ dùng propagation này khi đó là hành vi nghiệp vụ mong muốn.

`NESTED` không có nghĩa Neo4j tạo một native transaction lồng nhau hoặc savepoint trong cùng transaction. Hãy kiểm tra khả năng hỗ trợ của transaction manager và không dùng `NESTED` như một cách rollback riêng một phần graph nếu không có cơ chế được hỗ trợ rõ ràng.

## 11. Chọn đúng transaction manager khi có nhiều nguồn dữ liệu

Một ứng dụng có thể đồng thời dùng Neo4j và một database quan hệ. Mỗi tài nguyên cần transaction manager tương ứng, ví dụ `neo4jTransactionManager` và `transactionManager` cho database quan hệ.

Khi có nhiều transaction manager, chỉ rõ manager cho method:

Ví dụ giả định bean `PersonRepository` được inject vào service và transaction manager Neo4j được đăng ký với tên chỉ định:

```java
import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import org.springframework.transaction.annotation.Transactional;

@Transactional(transactionManager = "neo4jTransactionManager")
public void updateGraph() {
    personRepository.save(person);
}
```

Bean `PlatformTransactionManager` của Neo4j phải được đăng ký với tên `neo4jTransactionManager` để qualifier trong annotation khớp. Nếu cấu hình dùng tên bean khác, hãy chỉ đúng tên thực tế.

Một method dùng `@Transactional` với một transaction manager không tự động tạo distributed transaction bao trùm mọi database khác. Nếu method gọi cả repository Neo4j lẫn repository quan hệ, mỗi manager có thể quản lý transaction riêng. Rollback của một manager không tự rollback tài nguyên do manager khác điều khiển.

Nếu cần phối hợp nhiều hệ thống, hãy lựa chọn giải pháp phù hợp với khả năng resource và hạ tầng, hoặc dùng outbox/saga với retry và hành động bù. Không giả định một thread-bound resource của Neo4j bao trùm các tài nguyên ngoài Neo4j.

## 12. Read-only transaction và bookmark

`@Transactional(readOnly = true)` mô tả một transaction chỉ đọc. Trong Neo4j cluster, đánh dấu read-only giúp hạ tầng SDN và Driver định tuyến truy vấn đọc phù hợp với kiến trúc primary/secondary. Đây là metadata về mục đích giao dịch, không phải cơ chế phân quyền bảo mật; custom query có thao tác ghi vẫn phải được khai báo và kiểm soát đúng.

```java
import java.util.List;

import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import org.springframework.transaction.annotation.Transactional;

@Transactional(readOnly = true)
public List<Person> findPeople() {
    return personRepository.findAll();
}
```

Bookmark là một cơ chế khác với thread-bound resource. Transaction manager/SDN sử dụng bookmark để duy trì causal consistency giữa các transaction, đặc biệt trong cluster. Transaction tiếp theo có thể dùng bookmark từ transaction đã commit để quan sát các thay đổi trước đó. Bookmark không phải session và không giữ transaction đang mở.

Trong các thao tác cùng thread, SDN quản lý transaction và bookmark để các lời gọi tiếp theo đọc được dữ liệu đã ghi theo kỳ vọng. Khi chuyển sang một thread hoặc transaction mới, transaction cũ không được truyền sang; causal consistency giữa các transaction được xử lý qua bookmark manager.

## 13. Sử dụng trực tiếp Driver bên trong Spring transaction

Đây là lỗi dễ gây dữ liệu lệch nhất. Ví dụ:

Giả sử service đã inject `Driver` và `PersonRepository`:

```java
import java.util.Map;

import com.example.graph.domain.Person;
import com.example.graph.repository.PersonRepository;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void updatePerson(Person person) {
    personRepository.save(person);

    try (Session session = driver.session()) {
        session.executeWrite(tx -> {
            tx.run("CREATE (:Log {message: 'person updated'})");
            return null;
        });
    }

    throw new IllegalStateException("force rollback");
}
```

Repository save tham gia transaction Spring. Nhưng session/transaction được mở trực tiếp bằng Driver là transaction độc lập. Khi method ném exception, Spring rollback phần repository; thao tác tạo `Log` đã commit bởi Driver có thể vẫn tồn tại.

Nếu mục tiêu là rollback cả hai thao tác, hãy chuyển truy vấn `CREATE (:Log ...)` sang `Neo4jClient` trong cùng service transaction. Chỉ dùng Driver trực tiếp khi chủ động muốn tự quản lý một transaction riêng và hiểu rõ ranh giới commit.

## 14. Kiểm thử transaction và tài nguyên thread-bound

Nên kiểm tra cả kết quả dữ liệu và cách các abstraction tham gia transaction. Các tình huống quan trọng:

1. Gọi repository, template và client trong cùng service method `@Transactional`; sau khi commit, xác nhận tất cả thay đổi đều tồn tại.
2. Tạo exception sau nhiều thao tác; xác nhận mọi thay đổi thuộc cùng transaction đều rollback.
3. Dùng `TransactionTemplate` để xác nhận các thao tác trong callback tham gia transaction được mở bởi template.
4. Gọi method `REQUIRES_NEW`; xác nhận transaction trong có thể commit độc lập với transaction ngoài.
5. Thực thi công việc trong executor; xác nhận thread worker không kế thừa transaction imperative của thread gọi.
6. So sánh truy vấn qua `Neo4jClient` với truy vấn qua Driver session độc lập để nhận biết hai transaction boundary.
7. Kiểm tra cấu hình nhiều database hoặc nhiều Driver để bảo đảm client và transaction manager dùng cùng provider/Driver tương ứng.
8. Với cluster, xác nhận bookmark/causal consistency giữa các transaction kế tiếp nếu use case phụ thuộc read-your-writes.

Trong integration test, có thể kiểm tra dữ liệu sau khi transaction kết thúc bằng một transaction đọc mới. Không nên kiểm tra bằng một session độc lập vẫn đang mở hoặc giả định rằng một truy vấn chạy trên thread khác sẽ nhìn thấy transaction chưa commit.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Repository và `Neo4jClient` không rollback cùng nhau | Client dùng Driver hoặc transaction manager khác | Dùng cùng Driver/provider và abstraction SDN tích hợp transaction |
| Truy vấn trong async worker không tham gia transaction ngoài | Transaction imperative gắn với thread hiện tại | Mở transaction mới trong worker hoặc giữ thao tác tuần tự |
| Dữ liệu Driver trực tiếp vẫn tồn tại sau rollback Spring | Driver mở transaction độc lập | Dùng `Neo4jClient` nếu cần cùng transaction |
| Session bị lỗi khi chia sẻ giữa thread | Session không thread-safe | Mỗi thread dùng session riêng; để SDN quản lý session |
| Gọi `REQUIRES_NEW` nhưng kết quả vẫn rollback theo outer | Lời gọi không đi qua proxy hoặc propagation không được áp dụng | Gọi qua bean proxy và kiểm tra transaction manager |
| Client và transaction manager chọn database khác nhau | Provider/database selection không đồng nhất | Dùng cùng `DatabaseSelectionProvider` |
| Transaction của Neo4j không rollback database quan hệ | Hai local transaction manager độc lập | Dùng cơ chế phối hợp nhiều tài nguyên hoặc saga/outbox |
| Dữ liệu mới chưa đọc được ngay trong cluster | Causal bookmark không được truyền/giữ đúng | Dùng bookmark manager tích hợp SDN; không vô hiệu hóa bookmark tùy tiện |

## 16. Nguyên tắc cần nhớ

- `Neo4jTransactionManager` là `PlatformTransactionManager` cho native Neo4j transaction.
- Manager đồng bộ session/transaction của Driver với transaction Spring.
- Trong ứng dụng imperative, tài nguyên giao dịch gắn với thread hiện tại và được chia sẻ qua hạ tầng Spring.
- Repository, `Neo4jTemplate` và `Neo4jClient` dùng cùng hạ tầng có thể tham gia một transaction.
- Dùng cùng instance Driver, database selection và user selection tương ứng.
- Driver dùng chung được giữa thread; Session không thread-safe và không được truyền qua thread tùy ý.
- Thread-bound transaction không tự truyền qua `@Async`, executor, `CompletableFuture` hoặc parallel stream.
- Gọi Driver trực tiếp tạo transaction riêng; nó không tự tham gia transaction Spring.
- Dùng `TransactionTemplate` khi cần mở transaction imperative bằng code.
- Bookmark duy trì causal consistency giữa transaction; nó không phải tài nguyên session/transaction đang mở.
- Với nhiều transaction manager, chỉ rõ manager và không giả định có distributed transaction tự động.

Trong Spring Data Neo4j đồng bộ, thread-bound resource là cơ chế giúp nhiều thao tác SDN trên cùng luồng thực thi chia sẻ đúng native transaction. Khi giữ nhất quán Driver, transaction manager và ranh giới thread, repository, template và client có thể phối hợp như một đơn vị công việc ACID. Khi chuyển thread hoặc gọi Driver trực tiếp, cần xác định lại transaction boundary để tránh thao tác ngoài transaction dự kiến.

## Tài liệu tham khảo

- [Spring Data Neo4j 8.1.2 – Neo4jTransactionManager API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
- [Spring Data Neo4j 8.1.2 – Building blocks](https://docs.spring.io/spring-data/neo4j/reference/introduction-and-preface/building-blocks.html)
- [Spring Data Neo4j 8.1.2 – FAQ: transactions, TransactionTemplate and Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Neo4j Java Driver Manual – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
