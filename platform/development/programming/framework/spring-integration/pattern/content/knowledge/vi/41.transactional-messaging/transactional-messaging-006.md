# Transaction propagation qua Service Activator trong Spring Integration

## 1. Bài toán: một message đi qua nhiều service, transaction thuộc về ai?

Trong Spring Integration, **Service Activator** là một Enterprise Integration Pattern (EIP) chuyển thông điệp thành lời gọi tới một phương thức xử lý nghiệp vụ. Một flow có thể nhận message từ Gateway, đưa qua Filter/Transformer/Router rồi gọi nhiều Service Activator liên tiếp hoặc ở các nhánh khác nhau.

Ví dụ, hệ thống tiếp nhận đơn hàng thực hiện:

1. Application service mở transaction và ghi `orders`.
2. Gateway gửi `ReserveCommand` vào `DirectChannel`.
3. Service Activator A ghi `reserved_inventory`.
4. Service Activator B ghi nhật ký nghiệp vụ `audit_log`.
5. Application service phát hiện lỗi và yêu cầu rollback.

Câu hỏi: **Dữ liệu ở A và B có bị rollback cùng đơn hàng không?** Câu trả lời phụ thuộc vào *transaction propagation* của từng phương thức, transaction đang tồn tại tại thời điểm gọi và cách channel chuyển thông điệp.

**Transaction propagation** là quy tắc mà Spring dùng khi một phương thức có transaction advice được gọi **trong hoặc ngoài transaction hiện có**. Nó quyết định phương thức **tham gia transaction đang chạy**, **mở transaction độc lập**, **dùng savepoint**, **chạy không có transaction** hay **từ chối lời gọi**. Việc một method là Service Activator không tự thay đổi các quy tắc đó.

Trong module `SPRING_INTEGRATION_PATTERN`, hiểu đúng propagation giúp xây dựng các luồng Router, Filter, Transformer, Splitter, Aggregator và Gateway ít phụ thuộc, đồng thời dự đoán chính xác commit/rollback, retry, error channel và correlation khi flow có nhiều nhánh.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Chỉ ra transaction bắt đầu ở application service, poller, listener hay chính Service Activator.
- Giải thích đủ bảy chế độ `Propagation` thường dùng của `@Transactional`, đặc biệt `REQUIRED`, `REQUIRES_NEW` và `NESTED`.
- Thiết kế hai Service Activator hoạt động với transaction khác nhau trong cùng một luồng `DirectChannel`.
- Phân tích `UnexpectedRollbackException`, rollback-only, checked exception, lời gọi không đi qua proxy và lỗi sau commit.
- Xác định vì sao `ExecutorChannel` hoặc broker cắt đứt transaction theo thread.
- Kiểm thử trường hợp outer rollback, inner commit, savepoint rollback và xử lý lặp qua retry/redelivery.

## 2. Điều kiện để propagation có hiệu lực

Một phương thức có `@Transactional` không có nghĩa mọi lời gọi đến nó đều tự động đi qua transaction interceptor. Trong mô hình Spring proxy phổ biến, phương thức phải được gọi qua **Spring-managed proxy** phù hợp; annotation được áp dụng khi advice thực sự chặn lời gọi.

~~~mermaid
flowchart LR
    A["Application service @Transactional"] --> B["Messaging Gateway"]
    B --> C["DirectChannel"]
    C --> D["Service Activator bean/proxy"]
    D --> E["Transaction interceptor"]
    E --> F["Business method + JDBC"]
~~~

Để kết quả giống sơ đồ:

1. Caller thực sự đã đi qua proxy của application service có `@Transactional`.
2. Service Activator trỏ đến **bean được Spring quản lý**, và lời gọi handler đi qua proxy/interceptor tương ứng.
3. Flow còn chạy **đồng bộ trên cùng thread** nếu muốn dùng transaction của caller.
4. `PlatformTransactionManager` được chọn quản lý đúng database hoặc tài nguyên mà handler sử dụng.
5. Exception và rollback rules cho phép transaction interceptor nhìn thấy lỗi cần rollback.

Với `DirectChannel`, handler được gọi đồng bộ trên thread phát message. Đây là điều kiện thuận lợi để handler tham gia transaction đang có, **nhưng DirectChannel không tự mở transaction**.

Với `ExecutorChannel`, worker thường chạy trên thread khác: transaction kiểu thread-bound của caller **không tự truyền qua**. `@Transactional(REQUIRED)` ở worker có thể mở transaction mới vì tại đó không tồn tại transaction của caller.

### “Cùng message” không có nghĩa “cùng transaction”

`MessageHeaders.ID`, `correlationId`, `sequenceNumber` và `orderId` phục vụ nhận diện, routing, aggregation và tracing. Các header này không phải transaction context. Khi message đi vào queue, executor hoặc broker, cần xác định transaction ở **consumer**, chứ không suy từ transaction của producer.

## 3. Bảy chế độ propagation

`Propagation` thuộc `org.springframework.transaction.annotation.Propagation`.

| Chế độ | Khi **đã có** transaction ở caller | Khi **chưa có** transaction | Trường hợp sử dụng |
| --- | --- | --- | --- |
| `REQUIRED` *(mặc định)* | Tham gia transaction hiện tại. | Mở transaction mới. | Handler JDBC thuộc cùng đơn vị nghiệp vụ. |
| `REQUIRES_NEW` | Tạm đình chỉ transaction ngoài và mở transaction độc lập. | Mở transaction mới. | Ghi một kết quả bắt buộc độc lập, với rủi ro commit trước outer. |
| `NESTED` | Dùng transaction lồng với savepoint nếu manager/resource hỗ trợ. | Thường hành xử giống `REQUIRED` và mở transaction mới. | Cho phép rollback một phần JDBC mà outer vẫn có thể tiếp tục. |
| `SUPPORTS` | Tham gia transaction đang có. | Chạy không có transaction thực sự. | Truy vấn hoặc logic có thể dùng transaction nếu caller cung cấp. |
| `MANDATORY` | Tham gia transaction hiện tại. | Báo lỗi do không có transaction hiện hành. | Buộc caller sở hữu transaction cho thao tác phải nhất quán. |
| `NOT_SUPPORTED` | Tạm đình chỉ transaction hiện tại, chạy không có transaction. | Chạy không có transaction. | Công việc không cần transaction; phải hiểu tác dụng phụ ngoài rollback. |
| `NEVER` | Báo lỗi vì có transaction hiện hành. | Chạy không có transaction. | Chặn lời gọi trong bối cảnh transaction. |

`REQUIRED`, `REQUIRES_NEW` và `NESTED` là ba chế độ cần phân biệt kỹ nhất. Những chế độ khác quan trọng khi một Service Activator được tái sử dụng từ nhiều endpoint hoặc được gọi qua các nhánh có transaction boundary khác nhau.

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Service Activator được gọi qua transaction interceptor"] --> B{"Thread hiện tại đã có transaction?"}
    B -->|"Có"| C{"Propagation?"}
    B -->|"Không"| D{"Propagation?"}
    C -->|"REQUIRED / SUPPORTS / MANDATORY"| E["Tham gia transaction hiện tại"]
    C -->|"REQUIRES_NEW"| F["Suspend outer, mở transaction độc lập"]
    C -->|"NESTED"| G["Savepoint nếu hỗ trợ"]
    C -->|"NOT_SUPPORTED"| H["Suspend outer, chạy không transaction"]
    C -->|"NEVER"| I["Lỗi"]
    D -->|"REQUIRED / REQUIRES_NEW / NESTED"| J["Mở transaction mới"]
    D -->|"SUPPORTS / NOT_SUPPORTED / NEVER"| K["Chạy không transaction"]
    D -->|"MANDATORY"| L["Lỗi"]
~~~

Khi một method `REQUIRED` **tham gia transaction đang tồn tại**, các thuộc tính `isolation`, `timeout` và `readOnly` khai báo ở method đó **không mặc định thay thế** những thuộc tính của physical transaction đã được outer tạo. Có thể cấu hình transaction manager để xác nhận tính tương thích của thuộc tính khi tham gia. Hãy xem **boundary nào thực sự mở physical transaction**.

## 4. Phân biệt logical transaction và physical transaction

Trong Spring, mỗi lời gọi `@Transactional` có thể tạo **phạm vi transaction logic** của riêng interceptor. Nhưng nhiều phạm vi `REQUIRED` có thể cùng dùng **một physical transaction** trên database.

~~~mermaid
flowchart LR
    subgraph P["Physical TX-A: một lần commit/rollback"]
        O["Outer @Transactional(REQUIRED)"] --> I["Activator A @Transactional(REQUIRED)"]
        I --> DB[("Same JDBC connection / DB resource")]
    end
    O --> R["Activator B @Transactional(REQUIRES_NEW)"]
    subgraph Q["Physical TX-B: độc lập"]
        R --> DB2[("DB connection cho TX-B")]
    end
~~~

**REQUIRED:** handler A và caller có thể dùng chung TX-A. Handler A trả về thành công **chưa commit** nếu caller vẫn giữ TX-A mở. Caller ném lỗi sau đó có thể rollback cả dữ liệu ở A.

**REQUIRES_NEW:** handler B tạo TX-B trong khi TX-A bị suspend. TX-B commit/rollback độc lập. Nếu TX-B commit và sau đó TX-A rollback, dữ liệu TX-B **vẫn được giữ**. Ngược lại, nếu TX-B ném lỗi lên caller và caller không bắt lỗi, TX-A cũng có thể rollback theo rollback rules — không có nghĩa hai transaction đã trở thành một.

**NESTED:** với manager hỗ trợ savepoint, inner có thể rollback về savepoint còn outer tiếp tục; tuy nhiên inner **không có independent commit** như `REQUIRES_NEW`. Nếu outer rollback, phần thay đổi đã đi qua savepoint vẫn bị rollback theo outer.

### Tại sao chuyện này quan trọng với message?

Một message có thể lần lượt đi qua Service Activator A rồi B trong cùng `DirectChannel`, nhưng **A và B có thể có kết quả commit khác nhau**. Tên channel, payload và correlation không nói lên loại transaction; phải xem entrypoint của proxy, propagation và transaction manager.

## 5. Ví dụ thực hành: REQUIRED và REQUIRES_NEW trong cùng flow

Ví dụ dùng Spring Boot, Spring Integration Java DSL, Spring JDBC và một transaction manager được cấu hình cho cùng `DataSource`. Các đoạn code lược bỏ import để tập trung vào ý nghĩa propagation.

**Kịch bản:** application service ghi đơn, gửi lệnh ghi thông tin giữ hàng qua một Service Activator `REQUIRED`, rồi gửi lệnh ghi audit qua một Service Activator `REQUIRES_NEW`. Cuối cùng outer ném lỗi.

### 5.1. Schema

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(64) PRIMARY KEY,
    state VARCHAR(24) NOT NULL
);

CREATE TABLE reserved_inventory (
    order_id VARCHAR(64) PRIMARY KEY,
    quantity INTEGER NOT NULL
);

CREATE TABLE audit_log (
    event_id VARCHAR(96) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL,
    action VARCHAR(40) NOT NULL
);
~~~

Trong bài thực hành, bảng `audit_log` cố ý **không có foreign key** tham chiếu `orders`, vì `REQUIRES_NEW` có thể ghi audit **trước khi** transaction tạo đơn của outer commit. Với dữ liệu thực tế, nếu audit bắt buộc phụ thuộc vào đơn đã commit, không nên thiết kế kiểu commit độc lập này; cân nhắc outbox hoặc ghi trong cùng transaction.

### 5.2. Payload và Gateway

~~~java
record ReserveCommand(String orderId, int quantity) {}
record AuditCommand(String eventId, String orderId, String action) {}

@MessagingGateway
interface ReservationGateway {
    @Gateway(requestChannel = "reserveInput")
    void reserve(ReserveCommand command);

    @Gateway(requestChannel = "auditInput")
    void audit(AuditCommand command);
}
~~~

`@MessagingGateway` tạo lối vào typed API. Hai phương thức gửi message đến hai channel riêng, giúp xác định handler nào chịu trách nhiệm. Gateway không tự làm transaction của những thread/broker khác trở thành transaction hiện tại.

### 5.3. IntegrationFlow và các DirectChannel

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
class ReservationFlowConfig {

    @Bean("reserveInput")
    MessageChannel reserveInput() {
        return new DirectChannel();
    }

    @Bean("auditInput")
    MessageChannel auditInput() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow reserveFlow(ReservationWriter writer) {
        return IntegrationFlow.from("reserveInput")
                .handle(writer, "write")
                .get();
    }

    @Bean
    IntegrationFlow auditFlow(AuditWriter writer) {
        return IntegrationFlow.from("auditInput")
                .handle(writer, "write")
                .get();
    }
}
~~~

`.handle(writer, "write")` là một Service Activator theo Java DSL. Để `@Transactional` được áp dụng đúng, `writer` phải là Spring bean với method có thể được gọi qua transaction proxy. Nếu sử dụng JDK dynamic proxy, method cần được công khai qua interface thích hợp; nếu dùng proxy theo class, phương thức phải tương thích với cơ chế proxy đó. Kiểm tra bằng integration test khi thay đổi cách tạo bean/proxy.

### 5.4. Handler A — REQUIRED

~~~java
@Service
class ReservationWriter {
    private final JdbcTemplate jdbc;

    ReservationWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void write(ReserveCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        jdbc.update("""
                INSERT INTO reserved_inventory(order_id, quantity)
                VALUES (?, ?)
                """, command.orderId(), command.quantity());
    }
}
~~~

Nếu method được gọi khi TX-A đang hoạt động, `REQUIRED` **tham gia TX-A**. Câu `INSERT` chưa độc lập commit khi `write()` return.

Nếu gọi cùng handler từ một endpoint khác **không có** transaction, `REQUIRED` **tự mở transaction mới** rồi commit/rollback quanh phương thức `write()`. Vì vậy handler không thể dựa vào `REQUIRED` để xác nhận rằng caller *bắt buộc* phải sở hữu transaction; muốn ép caller cung cấp transaction, cân nhắc `MANDATORY`.

### 5.5. Handler B — REQUIRES_NEW

~~~java
@Service
class AuditWriter {
    private final JdbcTemplate jdbc;

    AuditWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void write(AuditCommand command) {
        jdbc.update("""
                INSERT INTO audit_log(event_id, order_id, action)
                VALUES (?, ?, ?)
                """,
                command.eventId(), command.orderId(), command.action());
    }
}
~~~

Khi outer đã có transaction, Spring tạm đình chỉ TX-A và mở TX-B cho `AuditWriter.write()`. TX-B kết thúc khi handler return hoặc ném lỗi. **Commit của TX-B xảy ra trước khi outer TX-A hoàn tất.**

### 5.6. Application service — chủ động tạo kết quả khác nhau

~~~java
@Service
class ReservationApplicationService {
    private final JdbcTemplate jdbc;
    private final ReservationGateway gateway;

    ReservationApplicationService(
            JdbcTemplate jdbc,
            ReservationGateway gateway) {
        this.jdbc = jdbc;
        this.gateway = gateway;
    }

    @Transactional
    public void reserveNormally(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "PENDING");

        gateway.reserve(new ReserveCommand(orderId, 2));
        gateway.audit(new AuditCommand(
                "audit-" + orderId, orderId, "RESERVATION_REQUESTED"));
    }

    @Transactional
    public void reserveThenFail(String orderId) {
        jdbc.update(
                "INSERT INTO orders(order_id, state) VALUES (?, ?)",
                orderId, "PENDING");

        gateway.reserve(new ReserveCommand(orderId, 2));
        gateway.audit(new AuditCommand(
                "audit-" + orderId, orderId, "RESERVATION_REQUESTED"));

        throw new IllegalStateException("Simulated outer failure");
    }
}
~~~

**Điều gì sẽ còn trong database sau khi `reserveThenFail(...)` kết thúc?**

| Dữ liệu | Transaction | Kết quả dự kiến |
| --- | --- | --- |
| `orders` | TX-A của application service | **Rollback**, không còn row. |
| `reserved_inventory` | Handler `REQUIRED` tham gia TX-A | **Rollback**, không còn row. |
| `audit_log` | Handler `REQUIRES_NEW` tạo TX-B | **Commit**, row còn tồn tại nếu TX-B thành công. |

Với `reserveNormally(...)`, cả TX-B và TX-A có thể commit, nên cả ba bảng có row. Trong cả hai phương thức, lúc `gateway.audit(...)` return, TX-B đã hoàn tất, nhưng TX-A **chưa chắc đã commit**.

~~~mermaid
sequenceDiagram
    participant Facade as Application Service
    participant DB as Orders / Inventory DB
    participant Audit as Audit Service Activator
    Facade->>DB: BEGIN TX-A
    Facade->>DB: INSERT orders (TX-A)
    Facade->>DB: INSERT reserved_inventory via REQUIRED (TX-A)
    Facade->>Audit: Gateway -> DirectChannel -> write()
    Note over Facade,Audit: Suspend TX-A, begin TX-B
    Audit->>DB: INSERT audit_log (TX-B)
    Audit->>DB: COMMIT TX-B
    Audit-->>Facade: Return; resume TX-A
    Facade->>DB: Throw exception -> ROLLBACK TX-A
    Note over DB: audit_log vẫn tồn tại
~~~

**Lưu ý về hiệu năng:** `REQUIRES_NEW` có thể phải dùng **connection DB khác** trong khi connection của outer vẫn đang được giữ. Một connection pool quá nhỏ, nhất là khi nhiều thread cùng mở outer rồi đợi inner, có thể gây cạn pool hoặc bế tắc chờ connection. Cấu hình pool phải tính cả các transaction lồng độc lập, concurrency và timeout.

## 6. Vì sao REQUIRES_NEW không phải giải pháp mặc định cho audit và event?

Việc một audit row được commit trước outer có thể là **yêu cầu thật** (lưu dấu vết một lần thử thất bại), nhưng cũng có thể là **lỗi nhất quán**: audit nói “đã đặt hàng” trong khi đơn cuối cùng rollback.

| Mục tiêu | Thiết kế thường hợp lý hơn |
| --- | --- |
| Audit rằng *một lần thử đã xảy ra* dù đơn cuối cùng thất bại | `REQUIRES_NEW`, với mô tả action là attempt/decision, ID duy nhất và khả năng chấp nhận orphan reference. |
| Audit rằng *đơn hàng đã commit thành công* | Ghi audit cùng TX-A, hoặc ghi outbox/audit record cùng transaction nguồn. |
| Phát `OrderCreated` tới broker sau khi đơn commit | Transactional outbox và relay; không chỉ dùng `REQUIRES_NEW` để publish. |
| Ghi log/metric kỹ thuật độc lập | Có thể dùng logging/telemetry ngoài DB transaction, với quy tắc lỗi rõ ràng. |

**Transaction độc lập không đồng nghĩa với dữ liệu đúng về mặt nghiệp vụ.** Ví dụ, nếu TX-B tham chiếu row `orders` mới được insert trong TX-A chưa commit, TX-B có thể không đọc thấy row đó hoặc gặp khóa/constraint. Nên thiết kế phụ thuộc và thứ tự commit theo domain, tránh dựa vào dữ liệu chưa commit từ transaction bị suspend.

### Retry và duplicate của REQUIRES_NEW

Nếu outer rollback rồi nhận redelivery và chạy lại toàn bộ flow, TX-B có thể cố ghi lại `audit-" + orderId`. Với `event_id` là khóa chính, lần ghi lặp có thể ném duplicate-key exception. Phải chọn chiến lược:

- Một event nghiệp vụ nên có **ID ổn định** qua retry và dùng upsert/idempotent insert.
- Một log *attempt* mới được phép có ID khác, nhưng phải phân biệt attempt với kết quả nghiệp vụ đã commit.
- Không để lỗi ghi audit phụ bị lặp khiến một nghiệp vụ chính bị từ chối ngoài ý muốn nếu domain yêu cầu độc lập.

Nếu audit sử dụng `REQUIRES_NEW` để giữ log thất bại, cần đảm bảo lời gọi ghi audit không ném lỗi làm rollback outer một cách vô tình; điều này phụ thuộc cách bạn xử lý exception tại caller và chính sách business.

## 7. NESTED — savepoint khác gì transaction độc lập?

`Propagation.NESTED` sử dụng khái niệm **savepoint** bên trong một physical transaction khi transaction manager và resource hỗ trợ. Trong JDBC với `DataSourceTransactionManager`/`JdbcTransactionManager` có cấu hình phù hợp, nó thường cho phép rollback phần thay đổi của inner mà outer tiếp tục chạy.

~~~mermaid
flowchart TD
    A["Begin outer TX-A"] --> B["INSERT order"]
    B --> C["Savepoint S1 trước NESTED activator"]
    C --> D["Inner INSERT / UPDATE"]
    D --> E{"Inner thành công?"}
    E -->|"Không"| F["Rollback tới S1"]
    E -->|"Có"| G["Giữ thay đổi trong TX-A"]
    F --> H["Outer tiếp tục"]
    G --> H
    H --> I{"Outer commit?"}
    I -->|"Có"| J["Commit TX-A"]
    I -->|"Không"| K["Rollback toàn bộ TX-A"]
~~~

Ví dụ riêng cho một handler:

~~~java
@Service
class OptionalEnrichmentWriter {
    private final JdbcTemplate jdbc;

    OptionalEnrichmentWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void enrich(String orderId) {
        jdbc.update(
                "INSERT INTO optional_enrichment(order_id) VALUES (?)",
                orderId);

        // Minh họa lỗi để transaction interceptor rollback về savepoint.
        throw new IllegalStateException("Cannot enrich order");
    }
}
~~~

Caller đã có TX-A có thể gọi method qua proxy rồi **bắt lỗi một cách chủ đích** để outer tiếp tục:

~~~java
@Transactional
public void process(String orderId) {
    ordersRepository.insert(orderId);
    try {
        optionalEnrichmentWriter.enrich(orderId);
    } catch (IllegalStateException expected) {
        // Inner rollback về savepoint nếu NESTED được hỗ trợ.
        // Caller chấp nhận thiếu enrichment và tiếp tục nghiệp vụ.
    }
}
~~~

Hai đoạn code trên minh họa propagation khi **gọi Spring bean thông thường**. Trong IntegrationFlow, `OptionalEnrichmentWriter` cũng có thể là Service Activator được gọi qua `DirectChannel`; nguyên tắc vẫn là transaction interceptor phải thật sự được áp dụng.

**Giới hạn quan trọng:**

- Không phải mọi transaction manager hỗ trợ `NESTED`; một số sẽ báo lỗi ngay khi cố bắt đầu nested transaction.
- `NESTED` dùng savepoint trong **physical transaction hiện có**, không phải độc lập commit như `REQUIRES_NEW`.
- Sau inner thành công, nếu outer rollback, phần inner **vẫn rollback theo outer**.
- Một số side effect ngoài JDBC như publish broker hoặc gọi HTTP không được đảo ngược chỉ bởi rollback savepoint.
- Nếu inner method được gọi bằng `this.enrich(...)` và không đi qua proxy, không có bảo đảm savepoint thực sự được tạo.

Khi không chắc resource hỗ trợ savepoint, nên xác minh bằng integration test với đúng database/transaction manager; không giả định `NESTED` là giải pháp portable cho JMS, Kafka, JPA hoặc distributed transaction.

## 8. SUPPORTS, MANDATORY, NOT_SUPPORTED và NEVER tại Service Activator

Các chế độ này thường dùng để diễn tả **hợp đồng gọi**:

### MANDATORY — handler yêu cầu caller đã mở transaction

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public void updateBalance(AccountMessage message) {
    jdbc.update("UPDATE accounts SET balance = ? WHERE id = ?",
            message.balance(), message.accountId());
}
~~~

Khi handler chạy đồng bộ qua `DirectChannel` từ một service đang giữ transaction, nó có thể tham gia transaction đó. Nếu gọi từ một nguồn không có transaction, Spring báo lỗi thay vì âm thầm mở transaction mới. Điều này hữu ích khi muốn enforce ranh giới transaction **ở orchestration layer**.

**Cảnh báo:** nếu sau đó đổi input sang `ExecutorChannel` và worker không có transaction hiện hành, `MANDATORY` sẽ lỗi. Annotation này không thể đưa transaction của caller sang worker.

### SUPPORTS — dùng transaction hiện có nếu có

~~~java
@Transactional(propagation = Propagation.SUPPORTS, readOnly = true)
public CustomerInfo lookup(String customerId) {
    return repository.find(customerId);
}
~~~

Nếu caller có transaction, method tham gia; nếu không, method có thể chạy không có physical transaction. `readOnly = true` là một **hint/thuộc tính transaction**, không phải cơ chế chặn mọi thao tác ghi. Khi tham gia physical transaction đã mở, method không tự đổi transaction đó thành read-only.

### NOT_SUPPORTED — suspend transaction và chạy không có transaction

~~~java
@Transactional(propagation = Propagation.NOT_SUPPORTED)
public void invokeLegacyReport(String reportId) {
    legacyClient.generate(reportId);
}
~~~

Nếu caller có transaction, Spring tạm đình chỉ nó trong lúc chạy method. Side effect ở legacy API không được rollback cùng transaction của caller. Đừng dùng `NOT_SUPPORTED` để “giảm khóa” rồi kỳ vọng thao tác của method vẫn atomic với JDBC transaction trước đó.

### NEVER — chặn lời gọi trong transaction

~~~java
@Transactional(propagation = Propagation.NEVER)
public void performNonTransactionalTask(String taskId) {
    taskRunner.run(taskId);
}
~~~

Nếu method được gọi trong bối cảnh có transaction, Spring báo lỗi. Nó phù hợp khi code không được chạy trong transaction do yêu cầu kỹ thuật/nghiệp vụ rõ ràng. Chế độ này **không** có tác dụng tự suspend transaction như `NOT_SUPPORTED`.

### Bảng quyết định theo yêu cầu nghiệp vụ

| Muốn handler... | Chế độ nên cân nhắc | Điều cần nhớ |
| --- | --- | --- |
| Cùng commit/rollback với caller | `REQUIRED` | Cùng thread/tài nguyên; mặc định khi đã có transaction. |
| Từ chối nếu caller không có transaction | `MANDATORY` | Phù hợp contract ở điểm vào đồng bộ; async cần transaction tại worker. |
| Commit độc lập dù outer rollback | `REQUIRES_NEW` | Cần connection phù hợp, nghiệp vụ chấp nhận trạng thái độc lập. |
| Có thể rollback một phần, outer vẫn tiếp tục | `NESTED` | Chỉ khi manager hỗ trợ savepoint; outer rollback vẫn ảnh hưởng inner. |
| Tùy chọn tham gia transaction | `SUPPORTS` | Không đảm bảo có transaction khi được gọi trực tiếp. |
| Chủ đích không dùng transaction của caller | `NOT_SUPPORTED` | Side effect không thuộc rollback outer. |
| Bị cấm chạy khi có transaction | `NEVER` | Lỗi nếu caller có transaction. |

## 9. Rollback-only và UnexpectedRollbackException

Một tình huống dễ gây hiểu nhầm: Service Activator `REQUIRED` ném exception, caller **bắt lỗi** rồi tiếp tục:

~~~java
@Service
class RequiredPricingWriter {
    @Transactional(propagation = Propagation.REQUIRED)
    public void updatePrice(PricingCommand command) {
        // Ví dụ gây lỗi sau một số thao tác DB.
        throw new IllegalStateException("Pricing rule failed");
    }
}
~~~

~~~java
@Transactional
public void recalculate(String orderId) {
    ordersRepository.markProcessing(orderId);

    try {
        pricingGateway.apply(new PricingCommand(orderId));
    } catch (IllegalStateException ex) {
        // Bắt exception không đảm bảo outer còn có thể commit.
        log.warn("Pricing step failed", ex);
    }

    ordersRepository.markDone(orderId);
    // Khi outer kết thúc có thể nhận UnexpectedRollbackException.
}
~~~

Vì handler `REQUIRED` tham gia **cùng physical transaction** nhưng có một logical transaction scope riêng, transaction interceptor của handler có thể đánh dấu physical transaction là **rollback-only** khi exception thoát khỏi method. Caller bắt exception sau đó **không xóa được rollback-only**. Khi outer cố commit, Spring thường phát sinh `UnexpectedRollbackException` để báo rằng rollback đã xảy ra ngoài kỳ vọng của caller.

**Cách xử lý đúng phụ thuộc nghiệp vụ:**

- Nếu lỗi làm cả đơn hàng không hợp lệ: để exception truyền ngược và rollback toàn bộ.
- Nếu bước thất bại thực sự **độc lập**: cân nhắc `REQUIRES_NEW`, nhưng phải chấp nhận commit/rollback riêng và thiết kế idempotency.
- Nếu chỉ cần rollback phần JDBC của bước phụ: cân nhắc `NESTED` và savepoint khi được hỗ trợ.
- Nếu lỗi là trạng thái hợp lệ của nghiệp vụ: thiết kế handler trả về kết quả rõ ràng, tránh ném exception với rollback rules không mong muốn.

Không “sửa” bằng cách bắt rồi bỏ qua mọi lỗi trong error channel: điều đó có thể khiến poller/listener **ACK message** trong khi nghiệp vụ chưa được xử lý đúng.

### Checked exception và setRollbackOnly

Mặc định Spring rollback cho `RuntimeException` và `Error`; checked exception không mặc định yêu cầu rollback. Khi nghiệp vụ cần, khai báo:

~~~java
@Transactional(
        propagation = Propagation.REQUIRED,
        rollbackFor = Exception.class)
public void handle(OrderCommand command) throws Exception {
    // ...
}
~~~

`TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` có thể đánh dấu transaction để rollback nhưng cần dùng có chủ đích: caller có thể nhận `UnexpectedRollbackException` khi nghĩ rằng mọi method đã return bình thường. Cấu hình exception policy rõ ràng thường dễ đọc và kiểm thử hơn.

## 10. Khi propagation gặp polling endpoint và listener

Transaction của Service Activator cần xem cùng **transaction khởi đầu tại consumer**.

### Poller mở transaction trước khi gọi handler

~~~java
@Bean
IntegrationFlow pollingFlow(
        PlatformTransactionManager transactionManager,
        ReservationWriter writer) {
    return IntegrationFlow.from(
                    "workQueue",
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1_000)
                                    .maxMessagesPerPoll(1)
                                    .transactional(transactionManager)))
            .handle(writer, "write")
            .get();
}
~~~

Giả sử đã có `PollableChannel` tên `workQueue` và payload `ReserveCommand`:

1. Poller có transaction advice, mở TX-P cho tác vụ poll/dispatch theo cấu hình.
2. Handler `@Transactional(REQUIRED)` chạy đồng bộ, thường tham gia TX-P.
3. Nếu handler ném exception khiến TX-P rollback, các thao tác JDBC tham gia TX-P bị rollback.
4. Nếu handler dùng `REQUIRES_NEW`, nó tạm đình chỉ TX-P và mở TX-H riêng; TX-H có thể commit trước khi TX-P kết thúc.

**Nguồn message vẫn là một vấn đề riêng.** Nếu `workQueue` là `QueueChannel` in-memory, JDBC rollback **không tự đưa message đã dequeue trở lại queue**. Với persistent message store hoặc broker, khả năng redelivery phụ thuộc cơ chế nhận/ACK/transaction thực tế.

### Listener message-driven

~~~text
JMS / RabbitMQ / Kafka inbound
  -> inbound adapter / listener container
  -> DirectChannel
  -> Service Activator @Transactional(REQUIRED)
  -> DB business operation
  -> return / exception
  -> source ACK / offset / redelivery theo adapter
~~~

Nếu listener không mở JDBC transaction từ trước, `REQUIRED` trên handler sẽ **mở transaction JDBC mới**; nó không mặc định tham gia JMS/Kafka/RabbitMQ transaction. Khi DB đã commit nhưng nguồn chưa ACK, message có thể được giao lại; cần **idempotent consumer**.

Nếu listener đã cấu hình transaction JDBC phù hợp và dispatch đồng bộ, handler `REQUIRED` có thể tham gia. Nhưng **broker transaction** và **DB transaction** là các phạm vi riêng trừ khi hạ tầng thật sự hỗ trợ cơ chế phối hợp đã cấu hình. Đừng suy rằng propagation JDBC thay thế ACK/redelivery.

## 11. Async boundary: khi transaction của caller không còn

Giữ nguyên application service nhưng thay channel đầu vào thành:

~~~java
@Bean("reserveInput")
MessageChannel reserveInput(TaskExecutor taskExecutor) {
    return new ExecutorChannel(taskExecutor);
}
~~~

Với executor bất đồng bộ thông thường:

~~~mermaid
flowchart LR
    subgraph Outer["Thread A — physical TX-A"]
      A["Outer @Transactional"] --> B["Gateway sends"]
      B --> C["ExecutorChannel"]
      C --> D["Outer có thể commit/rollback"]
    end
    C -. "dispatch ở thread khác" .-> E["Worker nhận message"]
    subgraph Worker["Thread B — transaction do handler mở"]
      E --> F["Service Activator REQUIRED"]
      F --> G["TX-B riêng + JDBC"]
    end
~~~

Khi worker không có transaction trước đó, `REQUIRED` **mở transaction mới**. `REQUIRES_NEW` cũng mở transaction mới. Điều đó có nghĩa:

- Outer rollback **không tự rollback** dữ liệu worker đã commit.
- Worker lỗi **không tự làm outer rollback** nếu outer đã return/commit.
- `MANDATORY` có thể thất bại tại worker vì không có transaction hiện hành.
- Callback `afterCommit` của outer không mặc định chờ worker xong.
- Với input nhận từ broker, listener có thể hoàn tất ACK sau khi chỉ bàn giao cho executor; khi worker lỗi, nguồn ban đầu có thể không redeliver.

Một số `TaskExecutor` có thể chạy inline; cần xác minh cấu hình thực tế. Không dùng `ExecutorChannel` như cách truyền transaction hoặc làm message bền vững. Nếu cần xử lý nền có thể phục hồi, dùng **durable queue/inbox**, transaction ở consumer và idempotency.

## 12. Propagation với Router, Filter, Splitter, Aggregator và Gateway

Giả sử flow đặt hàng:

~~~mermaid
flowchart LR
    A["Gateway"] --> B["Transformer"]
    B --> C{"Router"}
    C --> D["Filter: validate"]
    C --> E["Splitter: từng sản phẩm"]
    D --> F["Service Activator REQUIRED"]
    E --> G["ExecutorChannel"]
    G --> H["Worker REQUIRES_NEW / REQUIRED"]
    F --> I["Aggregator"]
    H --> I
~~~

Phân tích theo từng pattern:

| Pattern | Tác động tới propagation |
| --- | --- |
| **Gateway** | Một Gateway đồng bộ có thể gọi flow trên thread caller, nên Service Activator phía sau `DirectChannel` có thể tham gia transaction caller. Gateway không tự tạo transaction xuyên broker. |
| **Filter** | Loại message có thể là kết thúc hợp lệ của nhánh, không tự ném exception/rollback. Nếu lọc là lỗi cần rollback, thiết kế error path rõ ràng. |
| **Transformer** | Thực thi đồng bộ có thể nằm trong cùng transaction; exception có thể tác động rollback nếu đi đến interceptor. |
| **Router** | Đường đến `DirectChannel` có thể giữ thread; đường đến `ExecutorChannel` hoặc broker thường tạo boundary khác. |
| **Splitter** | Tách nhiều message con. Nếu xử lý nối tiếp cùng thread, có thể ở chung transaction; nếu song song, mỗi nhánh cần boundary của mình. |
| **Aggregator** | Correlation/release strategy và message store quyết định khi nào phát kết quả; không thể tự rollback các commit đã hoàn thành ở nhánh khác. |
| **Error channel** | Việc error flow tiêu thụ exception có thể làm transaction/consumer thấy thành công; cần xem handler ném lại hay return. |

### REQUIRES_NEW trong từng nhánh không tạo “all-or-nothing”

Nếu Splitter tạo ba message con và mỗi worker dùng `REQUIRES_NEW`, ba transaction có thể commit riêng. Khi nhánh thứ ba thất bại, hai nhánh đầu đã commit **không tự rollback**. Nếu nghiệp vụ yêu cầu hoàn tác tác dụng đã commit, cần **compensating actions/Saga**, lưu trạng thái từng bước và có khả năng retry, chứ không thể dựa vào một transaction JDBC ở Gateway.

### Correlation và idempotency

`correlationId` giúp nhóm message thuộc cùng đơn hàng; `sequenceNumber` giúp xác định thứ tự message con. Nhưng khóa chống xử lý lặp thường là `eventId`/`commandId` được định nghĩa **ổn định qua retry và redelivery**. Với Service Activator `REQUIRES_NEW`, duplicate có thể commit ở lần xử lý trước rồi xuất hiện lại khi outer retry; nên dùng unique constraint và logic idempotent phù hợp.

## 13. Retry và thứ tự transaction advice

Trong các flow transactional, hai cấu hình có thể trông giống nhau nhưng không tương đương:

~~~text
Mô hình A — retry bao ngoài transaction:
  retry attempt #1
      -> begin TX-1
      -> Service Activator
      -> rollback TX-1
  backoff
  retry attempt #2
      -> begin TX-2
      -> Service Activator
      -> commit TX-2
~~~

~~~text
Mô hình B — transaction bao ngoài retry:
  begin TX-A
      -> attempt #1: handler gặp lỗi
      -> attempt #2: handler chạy lại
  commit/rollback TX-A
~~~

Nếu TX-A đã bị đánh dấu `rollback-only` ở attempt đầu, attempt tiếp theo có thể thành công về mặt code nhưng outer vẫn rollback. Với JDBC và lỗi cần retry toàn đơn vị công việc, thường nên **mở transaction mới cho mỗi attempt**; cấu hình advice chain/caller boundary để đạt điều đó thật sự.

Với `REQUIRES_NEW`, mỗi lần retry handler có thể tạo một physical transaction độc lập; khi một attempt đã commit nhưng caller không biết kết quả do timeout, attempt sau có thể tạo side effect **trùng**. Dùng khóa idempotency, unique constraint hoặc trạng thái bền vững để tránh lặp.

Với `NESTED`, rollback về savepoint có thể cho phép outer tiếp tục xử lý một nhánh phụ; nhưng nếu outbound broker/API đã nhận event trong attempt đầu, savepoint rollback không thể thu hồi event đó.

### Error channel và rollback rule

Giả sử một endpoint bất đồng bộ chuyển exception thành `ErrorMessage` cho error channel. Nếu error handler chỉ ghi log rồi return, transaction interceptor có thể nhìn thấy một lời gọi hoàn tất thành công và commit theo cấu hình. Nếu muốn broker redeliver hoặc database rollback, lỗi phải được truyền đúng đến nơi quyết định transaction/ACK. Không nên mặc định một bản ghi log lỗi tương đương với rollback.

## 14. Transaction synchronization theo từng propagation

Một handler có thể đăng ký `TransactionSynchronization` để chạy hành động sau commit. Nhưng **“sau commit của transaction nào”** mới là câu hỏi cốt lõi:

| Handler | Callback sau commit sẽ gắn với |
| --- | --- |
| `REQUIRED` tham gia TX-A | **TX-A của caller**; callback chưa chạy khi handler return. |
| `REQUIRES_NEW` mở TX-B | **TX-B độc lập**; callback có thể chạy trước khi TX-A commit/rollback. |
| `NESTED` tham gia TX-A qua savepoint | **Physical transaction TX-A**; không có commit riêng sau khi inner return. |
| `SUPPORTS` khi không có actual transaction | Có thể không có physical commit để đồng bộ; phải kiểm tra thực tế trước khi đăng ký hook. |
| `NOT_SUPPORTED` / `NEVER` | Chạy không có transaction thực; không kỳ vọng callback sau DB commit của caller. |

Ví dụ logic đăng ký hook:

~~~java
if (!TransactionSynchronizationManager.isActualTransactionActive()
        || !TransactionSynchronizationManager.isSynchronizationActive()) {
    throw new IllegalStateException("Transaction required");
}

TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Hành động này chạy sau COMMIT của physical transaction
                // mà synchronization tham gia.
            }
        });
~~~

**Đặc biệt nguy hiểm:** một callback phát `OrderCreated` được đăng ký trong `REQUIRES_NEW` có thể gửi event khi TX-B commit, dù outer TX-A chứa đơn hàng **chưa commit** và cuối cùng rollback. Nếu event mô tả thành công của outer, nên ghi **transactional outbox** cùng TX-A và chỉ phát sau khi TX-A commit.

Việc gửi trong `afterCommit` vẫn có thể thất bại hoặc không chạy khi process sập ngay sau commit. Callback điều phối thời điểm; outbox lưu bền vững **ý định gửi**. Consumer nhận event cần idempotency khi relay publish trùng.

## 15. Kiểm thử REQUIRED và REQUIRES_NEW bằng database thật

Với schema và các bean ở phần 5, kiểm thử tích hợp nên quan sát trạng thái **sau khi application service trả về**:

~~~java
@SpringBootTest
class ServiceActivatorPropagationIT {
    @Autowired ReservationApplicationService service;
    @Autowired JdbcTemplate jdbc;

    @Test
    void outerRollbackAlsoRollsBackRequiredButKeepsRequiresNew() {
        String orderId = UUID.randomUUID().toString();

        assertThrows(IllegalStateException.class,
                () -> service.reserveThenFail(orderId));

        assertEquals(0, countByOrderId("orders", orderId));
        assertEquals(0, countByOrderId("reserved_inventory", orderId));
        assertEquals(1, countByOrderId("audit_log", orderId));
    }

    @Test
    void successfulOuterTransactionCommitsAll() {
        String orderId = UUID.randomUUID().toString();

        service.reserveNormally(orderId);

        assertEquals(1, countByOrderId("orders", orderId));
        assertEquals(1, countByOrderId("reserved_inventory", orderId));
        assertEquals(1, countByOrderId("audit_log", orderId));
    }

    private int countByOrderId(String table, String orderId) {
        String sql = switch (table) {
            case "orders" ->
                    "SELECT COUNT(*) FROM orders WHERE order_id = ?";
            case "reserved_inventory" ->
                    "SELECT COUNT(*) FROM reserved_inventory WHERE order_id = ?";
            case "audit_log" ->
                    "SELECT COUNT(*) FROM audit_log WHERE order_id = ?";
            default -> throw new IllegalArgumentException(table);
        };
        return jdbc.queryForObject(sql, Integer.class, orderId);
    }
}
~~~

**Cách đọc kết quả:** Nếu `audit_log` vẫn có row sau khi outer rollback, đó là bằng chứng TX-B của `REQUIRES_NEW` đã commit độc lập trong môi trường test. Nếu cả ba bảng rollback, cần kiểm tra handler thực tế có đi qua transaction proxy, dữ liệu có bị ràng buộc ngoài ý muốn, hay bean/flow đã bị cấu hình khác.

Để kết luận đáng tin cậy:

- Không đặt `@Transactional` trên **chính test** nếu nó che mất hành vi commit/rollback của service được kiểm thử.
- Sử dụng ID riêng cho từng test và cô lập/cleanup dữ liệu.
- Dùng database, datasource, transaction manager và connection pool sát cấu hình cần kiểm chứng.
- Ghi nhận exception thực tế nếu kết quả khác mong đợi; không chỉ assert số lần handler được gọi.
- Không dùng external API hay broker làm bằng chứng về atomicity của JDBC; kiểm thử delivery/ACK ở cấp riêng.

### Kiểm thử thêm NESTED và rollback-only

Với `NESTED`, một ca có ích là outer insert order, inner tạo row sau savepoint rồi ném lỗi, outer bắt lỗi và commit. Kết quả mong muốn trên manager hỗ trợ savepoint: outer row **còn**, inner row **không còn**. Chạy thêm ca outer rollback để thấy toàn bộ row thuộc TX-A bị rollback.

Với `REQUIRED`, cố tình cho inner ném `RuntimeException` và caller bắt lỗi rồi return. Nếu inner interceptor đánh dấu global rollback-only, outer commit có thể ném `UnexpectedRollbackException`; khẳng định không có commit một phần. Đây là phép thử bảo vệ bạn trước lỗi “đã catch exception nên chắc commit được”.

## 16. Ma trận failure injection cho Service Activator

| Tình huống | Kết quả cần kiểm tra | Điều rút ra |
| --- | --- | --- |
| Outer rollback sau khi handler `REQUIRED` ghi DB | Dữ liệu ở outer và handler cùng rollback. | Hai logical scope có thể dùng chung physical transaction. |
| Outer rollback sau khi handler `REQUIRES_NEW` commit | Row của inner vẫn tồn tại. | Inner commit độc lập, không được outer hoàn tác. |
| Handler `REQUIRES_NEW` ném lỗi và caller không catch | Inner rollback; outer cũng có thể rollback do exception lan lên. | Độc lập transaction không có nghĩa độc lập error handling. |
| `NESTED` gặp lỗi, outer bắt và tiếp tục | Inner rollback tới savepoint, outer commit nếu resource hỗ trợ. | Savepoint khác physical transaction mới. |
| `MANDATORY` được gọi từ worker không có transaction | Ném exception tại boundary handler. | Transaction của caller không tự theo ExecutorChannel. |
| Handler `REQUIRED` ném lỗi, outer catch | Có thể gặp `UnexpectedRollbackException` khi outer cố commit. | Catch exception không hủy rollback-only. |
| Poller dùng `QueueChannel` in-memory và handler rollback | DB rollback nhưng message có thể mất khỏi queue. | Propagation không thay thế source transaction. |
| Outer rollback nhưng inner đã publish external event | Event bên ngoài có thể vẫn tồn tại. | Transaction JDBC không rollback broker/API. |
| Broker redeliver sau inner commit | Duplicate key hoặc side effect lặp nếu không idempotent. | REQUIRES_NEW cần deduplication và policy retry. |
| Splitter tạo nhiều async nhánh, một nhánh lỗi | Các nhánh đã commit giữ dữ liệu; aggregator có thể thiếu kết quả. | Cần durable state, timeout và compensation. |

Quan sát log/trace với `messageId`, `correlationId`, `orderId`, `eventId`, thread, channel, propagation, điểm commit/rollback, số lần retry và kết quả ACK khi có thể. Không log payload nhạy cảm. Với lỗi concurrency, theo dõi connection pool, lock wait, deadlock và các transaction mở lâu.

## 17. Lựa chọn thiết kế theo yêu cầu thực tế

| Bài toán | Thiết kế phù hợp | Rủi ro cần chú ý |
| --- | --- | --- |
| Một use case ghi nhiều bảng cùng database, muốn all-or-nothing | `@Transactional` tại application service + `DirectChannel` + Service Activator `REQUIRED`. | Cùng datasource/manager, exception propagation, proxy có hiệu lực. |
| Handler phải luôn nằm trong transaction do tầng orchestration tạo | `MANDATORY` tại handler đồng bộ. | Lỗi nếu gọi từ nguồn không có transaction hoặc qua executor. |
| Ghi attempt/audit độc lập với thành bại của nghiệp vụ chính | `REQUIRES_NEW`, với semantics audit rõ và idempotency. | Có thể commit audit trước khi outer hoàn tất; connection pool và orphan row. |
| Bước phụ có thể thất bại nhưng outer vẫn commit | `NESTED` nếu JDBC savepoint được hỗ trợ; hoặc tách bước sang cơ chế khác. | NESTED không độc lập commit, không rollback remote side effect. |
| Consumer từ broker ghi DB | Transaction của consumer/handler + idempotency + ACK/redelivery đúng adapter. | DB commit trước ACK có thể gây redelivery. |
| Xử lý nền nhiều nhánh/worker | Durable messaging + mỗi worker có transaction riêng + correlation. | Partial commit, duplicate, timeout, Saga/compensation. |
| Phát event chỉ sau khi business DB commit và không được bỏ quên | Ghi outbox cùng transaction business rồi relay publish. | Relay có thể publish trùng; downstream phải idempotent. |

**Nguyên tắc chọn propagation:** bắt đầu với `REQUIRED` khi tất cả thao tác **thật sự thuộc một đơn vị nghiệp vụ**. Chỉ dùng `REQUIRES_NEW` hoặc `NESTED` khi có lý do cụ thể và đã mô tả được kết quả khi outer rollback. Propagation chỉ giải quyết ranh giới transaction cục bộ, còn độ tin cậy end-to-end phụ thuộc vào message source, ACK, retry và idempotency.

## 18. Bài tập vận dụng

**Bài 1 — vẽ boundary thực tế.** Dùng `Gateway → DirectChannel → Service Activator REQUIRED → Service Activator REQUIRES_NEW` với một outer `@Transactional`. Vẽ TX-A, TX-B, thời điểm suspend/resume và các row còn lại khi outer ném exception.

**Bài 2 — thử MANDATORY.** Đổi handler viết DB sang `Propagation.MANDATORY`. Gọi từ một application service đang có transaction và từ một message-driven endpoint không mở transaction. Giải thích hai kết quả; thử chuyển channel sang `ExecutorChannel`.

**Bài 3 — NESTED với savepoint.** Tạo handler `NESTED` ghi bảng phụ rồi cố tình ném lỗi. Outer bắt lỗi và commit. Kiểm tra trạng thái hai bảng, rồi đổi propagation thành `REQUIRED` để quan sát khác biệt trong rollback-only. Nêu rõ transaction manager/database bạn dùng.

**Bài 4 — audit có nghĩa gì?** Đặt `REQUIRES_NEW` để lưu `OrderAttempted` trước khi outer commit. Hãy chỉ ra vì sao không nên gọi event đó là `OrderCreated`; thiết kế lại bằng outbox nếu cần chỉ phát sự kiện của đơn đã commit.

**Bài 5 — redelivery và idempotency.** Mô phỏng broker giao lại cùng `ReserveCommand(eventId)` sau khi một handler độc lập đã commit. Dùng unique constraint và khóa idempotency cố định để không trừ tồn kho hai lần.

**Bài 6 — flow nhiều nhánh.** Splitter tạo ba message và gửi qua ba `ExecutorChannel`; mỗi worker có `@Transactional(REQUIRED)`. Khi một worker rollback, xác định trạng thái hai worker còn lại, cách Aggregator giải quyết timeout và lúc nào cần compensation.

### Câu hỏi tự đánh giá

**1. Service Activator dùng `REQUIRED` có tự tạo transaction mới khi caller đang có transaction không?** Không. Nó tham gia transaction hiện tại nếu tương thích; chỉ mở mới khi không có transaction.

**2. Outer rollback có xóa được row đã commit bởi handler `REQUIRES_NEW` không?** Không. Inner commit là physical transaction độc lập.

**3. `NESTED` có giống `REQUIRES_NEW` không?** Không. `NESTED` thường dùng savepoint trong transaction outer; outer rollback vẫn rollback thay đổi nested.

**4. Vì sao `MANDATORY` có thể lỗi sau khi thêm `ExecutorChannel`?** Vì worker không tự nhận transaction context từ thread caller.

**5. Catch exception từ handler `REQUIRED` có chắc outer sẽ commit được không?** Không. Inner interceptor có thể đã đánh dấu transaction rollback-only, dẫn đến rollback/`UnexpectedRollbackException` ở outer.

**6. Khi nào cần outbox thay vì `REQUIRES_NEW` để phát event?** Khi event phải phản ánh dữ liệu nghiệp vụ **đã commit** và phải có khả năng phục hồi/phát lại sau crash; một transaction độc lập tại handler không cung cấp bảo đảm đó.

## 19. Checklist trước khi đưa flow vào vận hành

- [ ] Xác định Service Activator được gọi qua Spring bean/proxy thật và transaction advice có hiệu lực.
- [ ] Vẽ outer transaction, inner logical scope, physical transaction và thời điểm commit/rollback.
- [ ] Chọn propagation cho từng handler dựa trên yêu cầu nghiệp vụ, không dựa vào tên pattern.
- [ ] Dùng `REQUIRED` khi muốn cùng transaction; `MANDATORY` nếu caller bắt buộc phải sở hữu transaction.
- [ ] Với `REQUIRES_NEW`, mô tả được kết quả khi outer rollback, connection pool và rủi ro duplicate.
- [ ] Với `NESTED`, xác minh savepoint được transaction manager và database hỗ trợ.
- [ ] Kiểm tra error propagation, rollback rules, rollback-only và `UnexpectedRollbackException`.
- [ ] Không để `this.method()` hoặc proxy JDK không phơi bày method làm mất transaction interceptor.
- [ ] Xác định channel nào có thread handoff; không giả định `ExecutorChannel` chuyển transaction context.
- [ ] Với polling/listener, kiểm tra source transaction, ACK/offset/redelivery và độ bền của message store.
- [ ] Kiểm tra thứ tự retry advice và transaction advice; mỗi attempt có transaction phù hợp.
- [ ] Dùng business event ID ổn định, unique constraint và idempotent consumer khi có redelivery.
- [ ] Với Router/Splitter/Aggregator, theo dõi correlation, partial commit, timeout và compensation.
- [ ] Phát event quan trọng bằng transactional outbox, kiểm thử crash giữa DB commit và broker publish.
- [ ] Kiểm thử outer rollback, inner commit, nested savepoint, catch lỗi và các nhánh bất đồng bộ.

**Ghi nhớ:** **Transaction propagation quyết định cách một Service Activator tham gia hoặc tạo transaction tại thời điểm được gọi.** `DirectChannel` thường giữ cùng thread để `REQUIRED` tham gia transaction caller; `REQUIRES_NEW` commit độc lập; `NESTED` dùng savepoint nếu hỗ trợ; executor và broker tạo ra boundary mới. Hãy kết hợp propagation với error handling, retry, idempotency và ACK/redelivery để flow Spring Integration đúng cả khi thành công lẫn khi gặp lỗi.
