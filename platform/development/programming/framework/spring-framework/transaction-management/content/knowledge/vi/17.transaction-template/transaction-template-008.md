# Dùng lại TransactionTemplate và tránh sửa cấu hình dùng chung đồng thời

## 1. Mục tiêu và bài toán

`TransactionTemplate` là công cụ lập trình transaction theo callback của Spring Framework. Một instance có thể được sử dụng lặp lại qua nhiều lời gọi, nhiều service và nhiều thread. **Điều kiện quan trọng:** cấu hình transaction của instance đã được thiết lập ổn định trước khi chia sẻ và **không bị thay đổi trong lúc các thread đang sử dụng**.

Đây là nội dung dễ bị hiểu sai: tài liệu Spring nói `TransactionTemplate` **thread-safe** bởi nó không giữ *conversational state* của từng giao dịch; tuy nhiên nó **có configuration state** có thể thay đổi bằng các setter như `setPropagationBehavior(...)`, `setIsolationLevel(...)`, `setTimeout(...)` và `setReadOnly(...)`. Nếu một thread thay đổi cùng instance để phục vụ request của nó, thread khác có thể vô tình dùng cấu hình không mong muốn.

Bài học giúp bạn:

1. Phân biệt **trạng thái cấu hình của template** và **trạng thái transaction của từng lần gọi `execute(...)`**.
2. Biết vì sao một `TransactionTemplate` được cấu hình một lần có thể làm Spring singleton bean, inject vào nhiều service và dùng đồng thời.
3. Tránh anti-pattern `setTimeout`/`setPropagationBehavior`/`setIsolationLevel` ngay trước mỗi `execute` trên instance dùng chung.
4. Tạo **các template riêng, có tên và policy ổn định** cho `REQUIRED`, `REQUIRES_NEW`, read-only hoặc các nhu cầu khác.
5. Nếu một request thật sự cần cấu hình động, tạo **template cục bộ mới cho request/operation**, không ghi đè cấu hình của singleton.
6. Hiểu rằng `TransactionStatus`, JDBC connection và dữ liệu callback thuộc **mỗi transaction/thread**, không phải trạng thái nên lưu trên template hay singleton field dùng chung.
7. Kiểm chứng bằng dự án **Java 17+ / Spring Boot / Spring JDBC / H2 / Maven**, nhiều thread ghi qua một template, rollback-only trong một lời gọi, và hai transaction policy khác nhau.
8. Viết integration test xác nhận policy, isolation/timeout, dữ liệu committed, rollback và cách tái sử dụng an toàn.

**Ví dụ tình huống:** API nhận hai loại yêu cầu: ghi nghiệp vụ bình thường (`REQUIRED`) và ghi một sự kiện cần transaction độc lập (`REQUIRES_NEW`). Hai request chạy đồng thời. Nếu code dùng **một singleton template** và đổi propagation theo từng request, khả năng một request vô tình dùng propagation của request khác là lỗi correctness, không chỉ lỗi performance.

## 2. TransactionTemplate thực sự lưu gì?

`TransactionTemplate` thuộc package `org.springframework.transaction.support` và triển khai `TransactionOperations`. Nó kết hợp:

- Một tham chiếu tới `PlatformTransactionManager`.
- **Transaction definition / cấu hình**: propagation, isolation, timeout, read-only, name.
- Phương thức `execute(TransactionCallback<T>)` hoặc `executeWithoutResult(Consumer<TransactionStatus>)` để thực thi callback trong transaction scope.

Nó **không phải** đối tượng chứa duy nhất một `TransactionStatus` được dùng chung cho mọi lời gọi. Mỗi lần execute, manager sẽ quyết định tạo mới hay tham gia transaction tùy context và propagation, rồi callback nhận status phù hợp.

```text
                TransactionTemplate singleton
               [manager + stable configuration]
                   /            |             \
                  /             |              \
Thread A: execute(...)   Thread B: execute(...)   Thread C: execute(...)
        |                        |                        |
Transaction scope A      Transaction scope B      Transaction scope C
JDBC resource A          JDBC resource B          JDBC resource C
        |                        |                        |
commit/rollback A       commit/rollback B       commit/rollback C
```

Trong ví dụ, mỗi thread gọi từ ngoài transaction nên mỗi lời gọi `REQUIRED` có transaction riêng. **Không suy luận** các scope luôn độc lập: nếu callback được gọi bên trong một transaction hiện hữu thì `REQUIRED` tham gia transaction đó. Transaction context JDBC đồng bộ thường gắn với thread; nó không tự lan sang thread khác do ExecutorService tạo ra.

### Thread-safe không đồng nghĩa "mọi setter đều an toàn khi gọi đồng thời"

Spring mô tả rõ hai thuộc tính cùng tồn tại:

- **Không có conversational state của mỗi invocation:** có thể dùng chung một template để gọi `execute` song song.
- **Có configuration state:** những thuộc tính như `timeout`, `propagation`, `isolation` là thông tin mà các invocation đọc để tạo scope. Nếu một thread sửa chúng trong lúc các thread khác bắt đầu transaction, hành vi không được bảo đảm theo policy từng request.

Vì vậy, câu "TransactionTemplate thread-safe" phải được hiểu đúng là **an toàn để thực thi nhiều transaction song song với cấu hình không thay đổi trong thời gian sử dụng**, không phải lời hứa rằng thay đổi setters cùng lúc là phương pháp lập trình an toàn.

## 3. Cách an toàn: cấu hình một lần rồi tái sử dụng

Mẫu đơn giản trong một service:

```java
@Service
public class PaymentCommandService {
    private final TransactionTemplate transactionTemplate;
    private final JdbcTemplate jdbcTemplate;

    public PaymentCommandService(
            PlatformTransactionManager transactionManager,
            JdbcTemplate jdbcTemplate) {
        this.transactionTemplate = new TransactionTemplate(transactionManager);
        this.transactionTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        this.transactionTemplate.setTimeout(20);
        this.jdbcTemplate = jdbcTemplate;
    }

    public void record(long id) {
        transactionTemplate.executeWithoutResult(status -> {
            jdbcTemplate.update(
                    "INSERT INTO payment_command(id) VALUES (?)",
                    id);
        });
    }
}
```

**Đây là fragment minh họa**, chưa bao gồm import, schema và class main. Điểm cần quan sát: chỉ gọi các setter **trong constructor trước khi instance được sử dụng/chia sẻ**; `record(...)` chỉ gọi `executeWithoutResult` và không thay đổi cấu hình.

Các giá trị cụ thể có thể được đặt một lần khi tạo Spring `@Bean`, một lần trong constructor service, hoặc trong file XML bean configuration. Spring bean singleton thường thích hợp khi chính template có policy thống nhất.

**Lợi ích:** Service không cần lặp thao tác tạo template/mapping configuration ở mỗi request. Nhưng không nên phóng đại thành "TransactionTemplate singleton dùng cùng connection". Việc lấy/trả connection và transaction lifecycle thuộc `PlatformTransactionManager`/`DataSource`/pool. Reuse template **không** biến nhiều invocation thành một physical transaction.

### Phân biệt `final` và bất biến

`private final TransactionTemplate template` ngăn gán lại **tham chiếu** template, nhưng `TransactionTemplate` vẫn có setter. `final` **không biến đối tượng bên trong thành immutable**. Điều bảo đảm an toàn ở đây là **quy ước không chỉnh sửa cấu hình sau khi khởi tạo**, bảo đảm publication/wiring phù hợp và không để các thread khác có quyền gọi setter trong luồng request.

Một Spring singleton service cũng không tự thread-safe chỉ vì field là `final`: những field mutable khác (như `ArrayList`, counters, `TransactionStatus` hoặc `Connection`) vẫn cần thiết kế đồng thời riêng.

## 4. Anti-pattern: sửa một singleton template ngay trước mỗi execute

### 4.1. Đoạn code sai

```java
// SAI nếu sharedTemplate được nhiều thread sử dụng.
public void process(boolean urgent, long id) {
    if (urgent) {
        sharedTemplate.setTimeout(1);
        sharedTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    } else {
        sharedTemplate.setTimeout(30);
        sharedTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
    }

    sharedTemplate.executeWithoutResult(status -> {
        jdbcTemplate.update(
                "INSERT INTO job_event(id) VALUES (?)", id);
    });
}
```

Đây là fragment **minh họa lỗi thiết kế**, không nên triển khai. Cả hai method set là các thao tác thay đổi **cùng configuration object**.

### 4.2. Interleaving gây sai policy

```text
Thread A: request urgent=true
  A1: sharedTemplate.setTimeout(1)
  A2: sharedTemplate.setPropagationBehavior(REQUIRES_NEW)
                    |
                    v (context switch)
Thread B: request urgent=false
  B1: sharedTemplate.setTimeout(30)
  B2: sharedTemplate.setPropagationBehavior(REQUIRED)
  B3: sharedTemplate.execute(callback B)
                    |
                    v (A chạy tiếp)
Thread A:
  A3: sharedTemplate.execute(callback A)
       -> A có thể nhận timeout=30, propagation=REQUIRED
          thay vì timeout=1, REQUIRES_NEW
```

Sai sót có thể nghiêm trọng:

- Transaction cần độc lập lại tham gia outer transaction, rồi bị rollback theo outer.
- Transaction cần ngắn lại nhận timeout dài, giữ lock lâu hơn.
- Một request ghi dữ liệu nhưng template vừa bị đổi `readOnly=true` vì request khác.
- Một request tưởng đọc mức `SERIALIZABLE` nhưng isolation bị request khác hạ xuống mức yếu hơn.

**Ngay cả khi gọi hai setter liên tiếp**, không có một giao dịch cấu hình nguyên tử; thread khác có thể quan sát một tập thuộc tính bị pha trộn. Mã có thể chạy "đúng" trong test tuần tự, nhưng lỗi chỉ xuất hiện khi tải đồng thời.

### 4.3. Vì sao thêm synchronized quanh setter chưa đủ?

Nếu khóa chỉ bảo vệ đoạn setter nhưng **không bảo vệ toàn bộ khoảng từ cấu hình đến manager tạo transaction**, thread khác vẫn có thể đổi cấu hình trước lúc `execute` đọc nó. Khóa quanh cả `execute` có thể buộc xử lý tuần tự, làm mất concurrency và tạo các vấn đề mới (đặc biệt khi callback chờ I/O). Đây là cách chữa không cần thiết cho một thiết kế vốn có lựa chọn tốt hơn.

**Khuyến nghị:** không dùng một template có policy thay đổi theo request; hãy chọn một trong hai:

- **Các template bất biến về mặt sử dụng**, một instance cho mỗi policy đã xác định trước.
- **Template cục bộ mới** trong từng lời gọi khi giá trị thật sự phụ thuộc input và không thể định nghĩa trước thành các profile.

Không giữ "currentRequestTimeout" hay "currentTransactionStatus" thành mutable field trên singleton service để tránh cùng loại race.

## 5. Nhiều policy: tạo nhiều TransactionTemplate rõ tên

### 5.1. Tạo bean theo profile

```java
@Configuration
public class TransactionProfiles {

    @Bean("standardTemplate")
    TransactionTemplate standardTemplate(
            PlatformTransactionManager manager) {

        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(30);
        template.setName("standard");
        return template;
    }

    @Bean("independentTemplate")
    TransactionTemplate independentTemplate(
            PlatformTransactionManager manager) {

        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(10);
        template.setName("independent");
        return template;
    }
}
```

Đây là fragment đã có cấu trúc Spring configuration, nhưng cần imports và phần ứng dụng hoàn chỉnh ở mục 9. Hai templates là **hai instance khác nhau**; cấu hình hoàn tất trước khi chúng được trao cho các consumer.

- `standardTemplate`: tham gia transaction hiện tại nếu có, nếu không có thì tạo mới; timeout 30 giây khi tạo transaction mới.
- `independentTemplate`: luôn tạo transaction mới (suspend outer khi cần), timeout 10 giây cho transaction mới của nó.
- Cả hai dùng cùng `PlatformTransactionManager` nhưng có **transaction definitions khác nhau**.
- Không gọi setters trên hai bean này sau khởi tạo.

### 5.2. Inject chính xác khi có nhiều bean cùng type

```java
public EventWriter(
        @Qualifier("standardTemplate") TransactionTemplate standard,
        @Qualifier("independentTemplate") TransactionTemplate independent,
        JdbcTemplate jdbc) {
    this.standard = standard;
    this.independent = independent;
    this.jdbc = jdbc;
}
```

Đây là fragment constructor; phần code đầy đủ ở mục 9. Dùng `@Qualifier` hoặc một cơ chế định danh minh bạch vì hai bean cùng kiểu `TransactionTemplate`.

Đừng phụ thuộc tên parameter/field để suy ra một cách mơ hồ khi có nhiều beans. Khi ứng dụng có nhiều `PlatformTransactionManager`, cần chỉ rõ đúng manager theo DataSource/tenant/resource, không chỉ chọn template theo tên nghiệp vụ mà bỏ qua tài nguyên của transaction.

### 5.3. Một template chia sẻ cho cả ghi và đọc có ổn không?

Nếu reader và writer cùng chấp nhận một policy, **có thể inject cùng instance**. `TransactionTemplate` không lưu dữ liệu request trong chính nó. Nhưng nếu reader thực sự cần `readOnly=true` hoặc timeout khác, **không sửa standardTemplate trong reader**; tạo một `readOnlyTemplate` cấu hình riêng.

Ví dụ:

```java
@Bean("readOnlyTemplate")
TransactionTemplate readOnlyTemplate(PlatformTransactionManager manager) {
    TransactionTemplate template = new TransactionTemplate(manager);
    template.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED);
    template.setReadOnly(true);
    template.setTimeout(5);
    return template;
}
```

`readOnly` thường là hint của transaction manager/driver/database; không phải bảo đảm không thể INSERT ở mọi backend. Nếu muốn ràng buộc cứng quyền ghi, dùng DB grants/transaction manager features phù hợp, không dựa chỉ vào setter.

## 6. Dynamic configuration: template cục bộ thay vì sửa bean dùng chung

Một số ứng dụng có timeout khác nhau theo tenant, SLA hoặc loại job. Khi không thể gom thành vài profile cố định, hãy tạo template **trong phạm vi lời gọi**:

```java
public void performWithCustomTimeout(int timeoutSeconds, long id) {
    if (timeoutSeconds <= 0 || timeoutSeconds > 120) {
        throw new IllegalArgumentException("Timeout ngoài phạm vi cho phép");
    }

    TransactionTemplate local = new TransactionTemplate(transactionManager);
    local.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED);
    local.setTimeout(timeoutSeconds);

    local.executeWithoutResult(status -> {
        jdbcTemplate.update(
                "INSERT INTO job_event(id) VALUES (?)", id);
    });
}
```

Đây là fragment cần các field/bean `transactionManager`, `jdbcTemplate` và schema. Vì `local` là **instance mới không chia sẻ**, request A không thể làm thay đổi timeout của request B bằng cách gọi setter trên object đó.

**Giải thích đúng:**

- `PlatformTransactionManager` được **dùng chung**; mỗi lời gọi không tạo manager hay DataSource mới.
- Template là object cấu hình mỏng, việc tạo mới trong một số luồng động thường hợp lý hơn đánh đổi correctness.
- Chỉ cấu hình **trước `local.execute(...)`**, không sửa template đang được thực thi.
- Nếu `PROPAGATION_REQUIRED` tham gia transaction ngoài, timeout mới trên template cục bộ **không tự override deadline** của physical transaction ngoài; muốn transaction độc lập cần policy `REQUIRES_NEW` nhưng phải đánh giá tính nhất quán.
- Tốt nhất validate timeout từ input và đặt hard cap thay vì cho khách hàng gửi một số tùy ý cực lớn.

### Khi cần lựa chọn hai policy từ request

Nếu có đúng hai profile, chọn **hai instance đã cấu hình sẵn**:

```java
TransactionTemplate template = urgent
        ? independentTemplate
        : standardTemplate;

template.executeWithoutResult(status -> {
    saveBusinessData();
});
```

Chọn **tham chiếu** không thay đổi configuration state. Fragment minh họa; cần khai báo hai templates cùng helper.

## 7. TransactionStatus, callback và tài nguyên không được chia sẻ bừa bãi

Một template dùng chung nhưng **mỗi lời gọi** nhận `TransactionStatus` riêng:

```java
sharedTemplate.executeWithoutResult(status -> {
    // status dành cho lần execute này.
    jdbcTemplate.update(
            "INSERT INTO job_event(id) VALUES (?)", uniqueId);
});
```

Không viết:

```java
// SAI: singleton service có mutable state của request đang chạy.
private TransactionStatus currentStatus;

public void process(long id) {
    sharedTemplate.executeWithoutResult(status -> {
        currentStatus = status; // Thread khác sẽ ghi đè field này.
        save(id);
    });
}
```

Trong transaction đồng bộ, thread-bound JDBC connection và synchronization được Spring quản lý. Không đưa `TransactionStatus`, `Connection`, `EntityManager` hoặc object chứa transaction-bound state ra shared field rồi dùng từ thread khác. Sau khi callback kết thúc, status không còn là context mở để tái sử dụng.

### Một status không phải transaction manager

`TransactionStatus` chứa thông tin của **một scope** như `isNewTransaction()`, `setRollbackOnly()` và trạng thái hoàn tất. Nó không phải pool connection để chuyển qua thread. Callback nên kết thúc đầy đủ tại boundary `execute(...)`.

Trong `execute(...)`:

- Nếu callback return bình thường và scope được phép commit, template gọi transaction manager hoàn tất scope/commit.
- Nếu callback ném unchecked exception hoặc error, Spring template rollback theo contract phù hợp rồi truyền lỗi cho caller.
- Nếu business error bị catch bên trong callback mà vẫn cần rollback, dùng `status.setRollbackOnly()`.
- `setRollbackOnly()` chỉ ảnh hưởng đến transaction/scope hiện tại và **không ghi cờ vĩnh viễn lên shared TransactionTemplate**. Một lời gọi sau qua cùng template có thể commit bình thường.

**Đó là khác biệt quan trọng giữa shared configuration và per-call transaction state.**

### Khi dùng ExecutorService, @Async hoặc CompletableFuture

Thread khác không tự nhận transaction JDBC của thread gốc. Nếu muốn mỗi job có transaction của chính nó, gọi `sharedTemplate.execute(...)` **bên trong chính thread của job**. Đừng tạo transaction ở thread A rồi chuyển `status`/`Connection` sang thread B. Nếu nhiệm vụ gồm nhiều ghi phải atomically commit cùng nhau, chạy tất cả chúng trong một transaction trên một execution context phù hợp hoặc thiết kế distributed coordination; đừng trông chờ một template singleton tự tạo transaction chung giữa threads.

## 8. Propagation, timeout, isolation: cấu hình vẫn có giới hạn ngữ nghĩa

### 8.1. REQUIRED không có nghĩa transaction riêng mỗi lần

```text
Caller không có transaction
  -> standardTemplate.execute(...)
     -> tạo physical transaction mới, commit/rollback cuối callback

Caller đã có outer transaction T
  -> standardTemplate.execute(...)
     -> tham gia T, không commit vật lý độc lập
```

Nếu muốn một audit entry tồn tại ngay cả khi outer rollback, `REQUIRED` không đủ. Có thể dùng `REQUIRES_NEW` trong một template riêng — nhưng commit độc lập có hệ quả kinh doanh và tài nguyên.

### 8.2. REQUIRES_NEW là transaction vật lý khác

`REQUIRES_NEW` suspend outer transaction nếu cần và mở transaction mới. Inner có thể commit còn outer rollback về sau. Điều đó minh họa rõ tại sao **không được đổi propagation ngẫu nhiên ở runtime trên shared template**: một lựa chọn sai có thể làm dữ liệu audit/side-effect mất hoặc tồn tại ngoài dự kiến.

Với JDBC, inner transaction mới có thể cần thêm một connection trong pool **trong khi outer đang giữ connection**. Hãy cân nhắc capacity pool, concurrency và lock ordering để tránh tình huống nhiều threads giữ outer connection rồi cùng chờ connection cho REQUIRES_NEW.

### 8.3. Isolation và timeout không tự override outer transaction

Giả sử outer đang ở `READ_COMMITTED` với timeout 30 giây; inner gọi một template `REQUIRED` đặt `SERIALIZABLE` và timeout 1 giây. Nếu inner chỉ tham gia transaction đã mở, isolation/timeout mới của template **thường không thay đổi physical transaction đang chạy**. Có thể cấu hình manager `validateExistingTransaction=true` để từ chối isolation mismatch trong một số trường hợp, nhưng không biến inner thành transaction mới.

Vì thế, việc có hai templates không tự giải quyết mâu thuẫn policy nếu cách gọi và propagation không đúng. Hãy viết integration test trên **transaction boundary thực** của ứng dụng.

### 8.4. Read-only và name

`setReadOnly(true)` được xem như hint/metadata cho manager và resource. `setName("...")` đặt tên transaction definition cho logging/monitoring theo nơi hỗ trợ. Cả hai là **configuration state**, nên cũng phải đặt **trước khi chia sẻ**, không gắn lại theo từng request.

Không nên đặt request ID hoặc thông tin cá nhân bằng `template.setName(requestId)` trên shared singleton. Nếu cần tracing per-request, dùng MDC/trace context của thread hoặc cách instrumentation phù hợp, không mutate transaction definition.

## 9. Dự án Java 17+ hoàn chỉnh: hai template cố định, dùng chung giữa nhiều thread

Ứng dụng thực hành dùng **Spring Boot 3.5.6**, **Java 17+**, **Spring JDBC**, **H2** và **Maven**. Đã chọn phiên bản release cố định để việc copy code có thể tái hiện; khi đưa vào production nên cập nhật dependency theo chính sách bảo mật và compatibility của dự án.

Mục tiêu kiểm chứng:

1. Bean `standardTemplate` được inject vào **hai service** và dùng cho nhiều lời gọi.
2. Một callback đánh dấu rollback-only không "làm bẩn" template cho những callback tiếp theo.
3. Template thứ hai `independentTemplate` có policy `REQUIRES_NEW` rõ ràng, không cần đổi policy của `standardTemplate`.
4. Bốn job chạy đồng thời qua shared template, mỗi job commit row ID riêng; không có race do cấu hình.
5. Một outer transaction rollback trong khi inner `REQUIRES_NEW` đã commit; phân biệt hai transaction profile.
6. Test xác minh object bean, giá trị configuration và data outcomes.

### 9.1. Cấu trúc file

```text
shared-transaction-template-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── SharedTemplateApplication.java
    │   │   ├── TemplateConfig.java
    │   │   ├── RecordWriter.java
    │   │   └── RecordReader.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/demo/
        └── SharedTemplateIntegrationTest.java
```

Không cần tạo bảng thủ công trong runner/test: Spring Boot chạy `schema.sql` trên embedded H2 khi application context khởi tạo, trước các callback `CommandLineRunner` và test method.

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>shared-transaction-template-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Các dependency JDBC, H2, JUnit 5 và Spring TestContext được quản lý bởi Spring Boot BOM. `TransactionTemplate` có sẵn từ Spring transaction dependency do JDBC starter cung cấp.

### 9.3. application.properties và schema.sql

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:shared_templates;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=8
spring.sql.init.mode=always
spring.main.banner-mode=off
app.demo.enabled=true
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE tx_record (
    id BIGINT PRIMARY KEY,
    origin VARCHAR(80) NOT NULL
);
```

H2 in-memory database có tên `shared_templates` cho phép nhiều connection trong cùng JVM thấy một database. Pool 8 connection phục vụ bốn jobs đồng thời và transaction `REQUIRES_NEW` khi outer đang giữ connection. Không đồng nhất template singleton với JDBC connection singleton: mỗi transaction mới nhận connection theo manager/pool.

### 9.4. TemplateConfig.java — cấu hình trước khi share

**`src/main/java/demo/TemplateConfig.java`**

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class TemplateConfig {

    @Bean("standardTemplate")
    public TransactionTemplate standardTemplate(
            PlatformTransactionManager manager) {
        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(30);
        template.setName("standard");
        return template;
    }

    @Bean("independentTemplate")
    public TransactionTemplate independentTemplate(
            PlatformTransactionManager manager) {
        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(10);
        template.setName("independent");
        return template;
    }
}
```

Hai Spring beans mặc định là **singleton**, nhưng là hai objects khác nhau. Không có setter nào được gọi trên chúng trong runtime request code. Đây là ranh giới cấu hình mà bạn có thể kiểm soát để tránh race condition.

Cả hai có `Isolation.READ_COMMITTED` để minh họa sự khác nhau chủ yếu ở **propagation** và **timeout**. Nếu production yêu cầu `SERIALIZABLE` hoặc isolation khác, hãy xác nhận backend/driver hỗ trợ và cấu hình thành một profile mới; không mutate profile đang phục vụ concurrent traffic.

### 9.5. RecordWriter.java — reuse template, rollback-only per-call và REQUIRES_NEW

**`src/main/java/demo/RecordWriter.java`**

```java
package demo;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class RecordWriter {
    private final TransactionTemplate standard;
    private final TransactionTemplate independent;
    private final JdbcTemplate jdbc;

    public RecordWriter(
            @Qualifier("standardTemplate") TransactionTemplate standard,
            @Qualifier("independentTemplate") TransactionTemplate independent,
            JdbcTemplate jdbc) {
        this.standard = standard;
        this.independent = independent;
        this.jdbc = jdbc;
    }

    public void save(long id, String origin) {
        standard.executeWithoutResult(status ->
                insert(id, origin));
    }

    public void rejectAndRollback(long id) {
        standard.executeWithoutResult(status -> {
            insert(id, "rejected");
            status.setRollbackOnly();
        });
    }

    public void saveIndependent(long id) {
        independent.executeWithoutResult(status ->
                insert(id, "independent"));
    }

    public void outerFailsAfterIndependentWrite(
            long outerId, long independentId) {
        standard.executeWithoutResult(status -> {
            insert(outerId, "outer");

            // Method trong cùng bean, nhưng transaction được tạo
            // bởi independent.execute(...) — không dựa vào AOP.
            saveIndependent(independentId);

            throw new IllegalStateException("outer failed");
        });
    }

    private void insert(long id, String origin) {
        jdbc.update(
                "INSERT INTO tx_record(id, origin) VALUES (?, ?)",
                id, origin);
    }
}
```

Các tình huống:

- `save(...)` dùng shared standard template với `REQUIRED`. Khi caller không có transaction, mỗi lần execute tạo transaction riêng; một số thread có thể gọi đồng thời.
- `rejectAndRollback(...)` gọi `status.setRollbackOnly()` **trên status của callback này**. Nó không thay đổi configuration của `standard`, nên những lời gọi `save(...)` khác không bị rollback theo.
- `saveIndependent(...)` dùng một template **khác** để tạo `REQUIRES_NEW` physical transaction.
- `outerFailsAfterIndependentWrite(...)` mở outer transaction qua `standard`, ghi outer row, sau đó gọi `saveIndependent`. Inner commit độc lập; outer ném `IllegalStateException` và rollback. `standard` không cần bị mutate sang `REQUIRES_NEW`.

**Ghi chú về self-invocation:** Lời gọi `saveIndependent(...)` trong cùng class không bị vấn đề `this.method()` làm mất annotation `@Transactional` vì transaction boundary ở đây là **lời gọi explicit `independent.execute(...)`**, không phải annotation AOP trên method được gọi. Nếu chuyển code sang declarative `@Transactional`, phải xét proxy/self-invocation theo cách khác.

## 9.6. RecordReader.java — một template được inject vào bean thứ hai

**`src/main/java/demo/RecordReader.java`**

```java
package demo;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class RecordReader {
    private final TransactionTemplate standard;
    private final JdbcTemplate jdbc;

    public RecordReader(
            @Qualifier("standardTemplate") TransactionTemplate standard,
            JdbcTemplate jdbc) {
        this.standard = standard;
        this.jdbc = jdbc;
    }

    public List<Long> ids(long fromInclusive, long toInclusive) {
        return standard.execute(status ->
                jdbc.queryForList(
                        "SELECT id FROM tx_record "
                                + "WHERE id BETWEEN ? AND ? ORDER BY id",
                        Long.class,
                        fromInclusive, toInclusive));
    }
}
```

`RecordReader` và `RecordWriter` cùng inject **bean tên `standardTemplate`**. Theo scope singleton mặc định, đó là **cùng object**; người dùng không cần tạo bản sao cho từng service nếu policy đồng nhất.

Ở bản demo, template chuẩn không đánh dấu `readOnly=true` vì phục vụ cả reader/writer. Trong ứng dụng thật, nếu đọc có transaction policy riêng (read-only, timeout ngắn, v.v.), nên tạo `readOnlyTemplate` thứ ba, thay vì `standard.setReadOnly(true)` trước truy vấn rồi đặt lại sau đó.

### 9.7. SharedTemplateApplication.java — chạy tuần tự và đồng thời

**`src/main/java/demo/SharedTemplateApplication.java`**

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SharedTemplateApplication {
    public static void main(String[] args) {
        SpringApplication.run(SharedTemplateApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            name = "app.demo.enabled",
            havingValue = "true",
            matchIfMissing = true)
    CommandLineRunner demonstrate(
            RecordWriter writer,
            RecordReader reader) {
        return args -> {
            writer.save(1L, "single");
            writer.rejectAndRollback(2L);
            writer.saveIndependent(3L);

            try {
                writer.outerFailsAfterIndependentWrite(4L, 5L);
            } catch (IllegalStateException ex) {
                System.out.println("outer failure: " + ex.getMessage());
            }

            ExecutorService pool = Executors.newFixedThreadPool(4);
            try {
                List<Future<?>> tasks = new ArrayList<>();
                for (long id = 10L; id <= 13L; id++) {
                    long recordId = id;
                    tasks.add(pool.submit(
                            () -> writer.save(recordId, "parallel")));
                }
                for (Future<?> task : tasks) {
                    task.get(10, TimeUnit.SECONDS);
                }
            } finally {
                pool.shutdownNow();
            }

            System.out.println("standard rows: " + reader.ids(1L, 1L));
            System.out.println("rollback rows: " + reader.ids(2L, 2L));
            System.out.println("independent rows: " + reader.ids(3L, 3L));
            System.out.println("outer rows: " + reader.ids(4L, 4L));
            System.out.println("inner rows: " + reader.ids(5L, 5L));
            System.out.println("parallel rows: " + reader.ids(10L, 13L));
        };
    }
}
```

Ở `CommandLineRunner` không có outer transaction, nên mỗi `writer.save(...)` có một scope `REQUIRED` riêng. `ExecutorService` tạo bốn threads; mỗi thread đi vào **cùng instance `RecordWriter` và cùng `standardTemplate`** nhưng transaction manager cấp per-thread transaction resources phù hợp.

**Tại sao `pool.submit(...)` không làm bốn job dùng một transaction chung?** Spring JDBC transaction context được gắn với thread. Một template singleton **không** truyền transaction context từ main thread sang worker threads. Bởi vậy chúng là bốn transaction độc lập trong lab này, dù configuration được dùng lại.

Code chờ `Future.get(...)` tất cả jobs, để kết quả SELECT chỉ chạy **sau khi các callback và transaction đã hoàn tất**. Không lấy số lượng hàng khi một job còn đang chạy, vì bạn có thể quan sát trạng thái giữa chừng hoặc race về thời điểm commit.

### 9.8. Chạy chương trình

Trong thư mục `shared-transaction-template-demo` đã có `pom.xml`, với JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

Dòng output do **chính chương trình** in (bỏ qua Spring/Maven logs):

```text
outer failure: outer failed
standard rows: [1]
rollback rows: []
independent rows: [3]
outer rows: []
inner rows: [5]
parallel rows: [10, 11, 12, 13]
```

Giải thích:

| Phép thử | Policy | Kết quả |
| --- | --- | --- |
| `save(1)` | Shared `REQUIRED` | Commit row `1` |
| `rejectAndRollback(2)` | Shared `REQUIRED` + per-call `setRollbackOnly` | Không còn row `2` |
| `saveIndependent(3)` | Template `REQUIRES_NEW` | Commit row `3` |
| `outerFailsAfterIndependentWrite(4,5)` | Outer `REQUIRED` + inner `REQUIRES_NEW` | Row `4` rollback, row `5` vẫn tồn tại |
| Bốn jobs `save(10..13)` | **Cùng standard template**, per-thread transactions | Commit tất cả rows `[10,11,12,13]` |

Kết quả này minh họa hai nguyên tắc: **cùng cấu hình có thể tái sử dụng đồng thời**, và **mỗi transaction callback có state riêng**. Nó không phải test chứng minh việc mutate setters là an toàn; ngược lại, demo **không có setter nào trong request path**.

## 10. Integration test: bean identity, policy và concurrency

Tạo file **`src/test/java/demo/SharedTemplateIntegrationTest.java`**:

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(properties = "app.demo.enabled=false")
class SharedTemplateIntegrationTest {
    @Autowired
    @Qualifier("standardTemplate")
    private TransactionTemplate standard;

    @Autowired
    @Qualifier("independentTemplate")
    private TransactionTemplate independent;

    @Autowired
    private RecordWriter writer;

    @Autowired
    private RecordReader reader;

    @Test
    void policyBeansAreDistinctAndConfiguredOnce() {
        assertNotSame(standard, independent);

        assertEquals(
                TransactionDefinition.PROPAGATION_REQUIRED,
                standard.getPropagationBehavior());
        assertEquals(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW,
                independent.getPropagationBehavior());

        assertEquals(
                TransactionDefinition.ISOLATION_READ_COMMITTED,
                standard.getIsolationLevel());
        assertEquals(
                TransactionDefinition.ISOLATION_READ_COMMITTED,
                independent.getIsolationLevel());

        assertEquals(30, standard.getTimeout());
        assertEquals(10, independent.getTimeout());
    }

    @Test
    void rollbackMarkerIsPerInvocationNotOnTemplate() {
        writer.rejectAndRollback(101L);
        writer.save(102L, "after-rollback");

        assertEquals(List.of(), reader.ids(101L, 101L));
        assertEquals(List.of(102L), reader.ids(102L, 102L));
        assertEquals(
                TransactionDefinition.PROPAGATION_REQUIRED,
                standard.getPropagationBehavior());
    }

    @Test
    void requiresNewCommitsIndependentlyOfOuterRollback() {
        assertThrows(IllegalStateException.class,
                () -> writer.outerFailsAfterIndependentWrite(201L, 202L));

        assertEquals(List.of(), reader.ids(201L, 201L));
        assertEquals(List.of(202L), reader.ids(202L, 202L));
    }

    @Test
    void manyThreadsCanReuseOneStableTemplate() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(4);

        try {
            List<Future<?>> tasks = new ArrayList<>();
            for (long id = 301L; id <= 308L; id++) {
                long recordId = id;
                tasks.add(pool.submit(
                        () -> writer.save(recordId, "parallel-test")));
            }
            for (Future<?> task : tasks) {
                task.get(10, TimeUnit.SECONDS);
            }
        } finally {
            pool.shutdownNow();
        }

        assertEquals(
                List.of(301L, 302L, 303L, 304L,
                        305L, 306L, 307L, 308L),
                reader.ids(301L, 308L));

        assertEquals(30, standard.getTimeout());
        assertEquals(
                TransactionDefinition.PROPAGATION_REQUIRED,
                standard.getPropagationBehavior());
    }
}
```

Chạy:

```bash
mvn test
```

**Kỳ vọng:** bốn tests pass khi dependencies được tải và dự án tạo đúng cấu trúc.

### Vì sao tắt runner trong test?

`@SpringBootTest(properties = "app.demo.enabled=false")` ngăn `CommandLineRunner` demo ghi các ID 1–13 khi khởi động context cho test. Bảng `tx_record` vẫn được tạo bởi `schema.sql`. Tests dùng ID riêng (101–308) để tránh va chạm với demo, và không thêm transaction ngoài không cần thiết.

### Vì sao không gắn @Transactional lên toàn test?

Spring TestContext có thể mở test-managed transaction cho test mang `@Transactional`. Khi đó `standardTemplate` `REQUIRED` có thể tham gia transaction của test, làm thay đổi thời điểm commit và ranh giới rollback. Đặc biệt, test `REQUIRES_NEW` cần nhìn rõ outer transaction do `writer` tạo, không bị transaction test vô tình bao quanh. Các test trên **không có `@Transactional`** ở class/method.

### Tại sao không viết test mutate template cùng lúc?

Vì bài học là **không được làm thế**, không nên cố viết một test mong muốn race chắc chắn tái hiện. Race theo scheduler thường không deterministic: test có thể pass hàng nghìn lần nhưng lỗi xảy ra khi có tải. Thay vào đó, kiểm chứng cấu hình template **không đổi** sau các invocation và không có setter trong đường xử lý request. Nếu cần chứng minh lỗi, dùng code review/static analysis hoặc kiểm tra thiết kế bean và điều kiện sharing.

## 11. Một số pattern Spring cho dự án lớn

### 11.1. Singleton @Bean là lựa chọn mặc định phù hợp

`@Bean` do `@Configuration` tạo mặc định là singleton trong Spring container. Điều đó giúp một policy rõ ràng được tái sử dụng ở nhiều service mà không lặp cấu hình. Trong dependency injection, các consumer nhận cùng instance nếu inject cùng bean name.

**Không nhất thiết bắt buộc singleton:** mỗi service có thể tự khởi tạo một `TransactionTemplate` cố định trong constructor với cùng manager. Điều quan trọng không phải singleton bằng mọi giá, mà là **không mutate cấu hình đang được share bởi concurrent calls**.

### 11.2. Khi có nhiều transaction manager

Trong hệ thống có nhiều DataSource, cần cố định cả manager lẫn policy của từng template:

```java
@Bean("billingTemplate")
TransactionTemplate billingTemplate(
        @Qualifier("billingTransactionManager")
        PlatformTransactionManager manager) {

    TransactionTemplate template = new TransactionTemplate(manager);
    template.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED);
    template.setTimeout(15);
    return template;
}
```

Đây là fragment cấu hình; bean `billingTransactionManager` phải được khai báo từ trước. Đừng đổi `template.setTransactionManager(...)` trên một shared instance giữa các tenants/requests. Một save/rollback trên DataSource A không tự điều khiển SQL đã ghi ở DataSource B.

### 11.3. Khi policy phụ thuộc tenant hoặc job type

Có ba chiến lược có thể cân nhắc:

| Nhu cầu | Lựa chọn | Cần tránh |
| --- | --- | --- |
| Một policy chung | Một shared template cấu hình một lần | Mỗi request đổi setter |
| Vài policy cố định | Một named bean mỗi policy; chọn theo yêu cầu | Đổi propagation/timeout trên bean duy nhất |
| Rất nhiều giá trị động | Tạo local TransactionTemplate per operation | Đưa `TransactionStatus` vào singleton field |
| Nhiều transaction managers | Tạo template gắn manager phù hợp | Thay manager trên shared object |
| Nhiều threads | Mỗi thread gọi `execute` trên template ổn định | Truyền cùng `Connection`/`TransactionStatus` giữa threads |
| Reactive programming | Dùng `TransactionalOperator`/`ReactiveTransactionManager` | Dùng JDBC thread-bound assumptions để suy luận reactive semantics |

Nếu cần cache template theo policy, hãy cân nhắc key bao gồm manager, propagation, isolation, timeout, read-only, transaction name; mọi instance trong cache vẫn phải có cấu hình ổn định sau khi publish. Đừng biến cache thành nơi mutate một object dùng chung để tiết kiệm vài allocation.

### 11.4. Cách thể hiện policy trong cấu trúc code

Nên đặt tên bean và wrapper service theo **mục đích nghiệp vụ** hơn là các tên chung như `template1` và `template2`. Ví dụ:

- `orderWriteTemplate` cho transaction đơn hàng thông thường.
- `auditIndependentTemplate` cho audit độc lập được thiết kế có chủ ý.
- `reportReadOnlyTemplate` cho truy vấn reporting với timeout được kiểm soát.

Dùng các kiểu/hằng `TransactionDefinition.PROPAGATION_REQUIRED`, `PROPAGATION_REQUIRES_NEW` thay vì tự nhớ các giá trị số 0, 3. Bất kỳ thay đổi policy nào nên đi kèm regression tests xác minh transactional outcomes, vì propagation khác nhau có thể ảnh hưởng dữ liệu được commit.

## 12. Những hiểu lầm thường gặp

### 12.1. "Thread-safe" nghĩa là cứ gọi setTimeout từ nhiều thread

**Sai.** Thread safety theo tài liệu Spring nói tới khả năng reuse template khi thực thi callbacks, không cấp quyền mutate configuration state tùy ý trong luồng concurrent. Setter chạy từ thread A có thể thay policy của thread B.

### 12.2. Cùng template nghĩa là cùng JDBC Connection

**Sai.** Template giữ manager và transaction definition. Connection được transaction manager và DataSource quản lý theo transaction/thread. Sharing template không tự share connection/transaction state.

### 12.3. private final đã làm config bất biến

**Sai.** `final` chỉ cố định tham chiếu, không cấm `template.setTimeout(...)`. Cần quy ước cấu hình xong trước khi publish/tiếp nhận request và không lộ API mutate qua service.

### 12.4. Tạo template mới mỗi lần sẽ tạo DataSource mới

**Sai.** `new TransactionTemplate(existingManager)` chỉ tạo wrapper/definition object mới, vẫn dùng manager đã được inject. Không được tạo một `DataSourceTransactionManager` mới cho mỗi request chỉ để đổi timeout.

### 12.5. Đổi REQUIRES_NEW trên shared template ở "riêng request này" là vô hại

**Sai.** Setter đổi một object chung, có thể ảnh hưởng request khác và thay commit/rollback boundary của nó. Tạo profile cố định hoặc local instance.

### 12.6. Mỗi callback có TransactionStatus riêng, nên thay cấu hình vẫn an toàn

**Sai.** Per-callback status và shared configuration là hai loại state khác nhau. Dù status độc lập, manager vẫn lấy definition từ template khi bắt đầu scope; definition bị sửa đồng thời có thể dẫn tới behavior sai.

### 12.7. Template dùng trong @Async sẽ tiếp tục transaction của caller

**Sai trong mô hình JDBC thread-bound thông thường.** Worker thread thường không mang context của caller. Một `execute` trong worker tạo/tham gia transaction *của worker*, không tự gia nhập transaction của thread gọi.

### 12.8. Muốn read-only thì setReadOnly(true), query xong setReadOnly(false)

**Sai nếu template shared.** Đây là mutate configuration trong concurrent runtime. Dùng một read-only template riêng. Ngoài ra read-only không luôn chặn tuyệt đối SQL ghi trên mọi database.

### 12.9. Callback đánh dấu rollback-only sẽ khiến template vĩnh viễn rollback

**Sai.** `status.setRollbackOnly()` tác động lên scope hiện tại, không thay đổi template. Callback sau trong transaction độc lập có thể commit; integration test ở trên xác minh điều đó.

### 12.10. REQUIRES_NEW luôn tốt hơn REQUIRED để tránh bị ảnh hưởng từ ngoài

**Không đúng.** REQUIRES_NEW tạo transaction vật lý riêng, có thể commit dữ liệu không đồng bộ với outer và tăng nhu cầu connection pool. Chọn propagation theo tính nguyên tử nghiệp vụ, không chỉ để tránh lỗi rollback.

### 12.11. Timeout ngắn trên inner REQUIRED luôn được áp dụng

**Sai nếu inner tham gia existing outer transaction.** Timeout của transaction definition thường áp dụng khi tạo physical transaction mới; inner REQUIRED không tự reset deadline outer.

### 12.12. Test concurrent pass là đủ chứng minh code không race

**Không.** Scheduler có thể không tạo đúng interleaving trong test. Thiết kế đúng là không mutate shared configuration, cộng với tests kiểm tra dữ liệu và giám sát vận hành khi tải lớn.

## 13. Checklist review trước khi đưa vào production

- [ ] Các `TransactionTemplate` dùng chung được **khởi tạo và cấu hình một lần**, trước khi phục vụ concurrent requests.
- [ ] Không có setter `setTimeout`, `setIsolationLevel`, `setPropagationBehavior`, `setReadOnly`, `setName`, `setTransactionManager` trên singleton template trong runtime request methods.
- [ ] Các transaction profile khác nhau dùng **các template instance riêng**; `@Qualifier` chỉ ra bean cần dùng.
- [ ] Các template dùng đúng `PlatformTransactionManager`/`DataSource`.
- [ ] Những giá trị động được validate và chỉ cấu hình trên **local instance** chưa publish.
- [ ] Không lưu `TransactionStatus`, JDBC `Connection`, mutable request state vào field dùng chung.
- [ ] Callback rollback-only chỉ đánh dấu chính status được truyền vào invocation đó.
- [ ] Có tests riêng cho `REQUIRED` join outer và `REQUIRES_NEW` commit độc lập nếu nghiệp vụ dùng cả hai.
- [ ] Hiểu timeout/isolation của inner participating transaction không tự override outer physical transaction.
- [ ] Thread pool, connection pool, timeout và lock contention được sizing/monitor phù hợp.
- [ ] Có integration tests chạy đồng thời và kiểm tra dữ liệu **sau khi transaction kết thúc**, không chỉ đếm số lần callback gọi.
- [ ] Không giả định Java thread interruption tự hủy JDBC transaction/SQL.
- [ ] Với nhiều tenants/managers, policy và resource được xác định trước khi dùng; không đổi manager trên shared template.
- [ ] Với reactive code, không áp dụng thread-local JDBC model cho `TransactionalOperator`.
- [ ] Chỉ dùng `REQUIRES_NEW` khi chấp nhận được commit độc lập và hậu quả nếu outer rollback.

## 14. Câu hỏi và bài tập

**Bài 1.** Hai requests cùng gọi `sharedTemplate.execute(...)` trong hai thread. Template đã được cấu hình một lần ở constructor, không có setter nào chạy sau đó. Có nhất thiết phải tạo một template cho mỗi request?

**Đáp án:** Không. Theo contract Spring, template có thể được reuse đồng thời khi configuration ổn định. Mỗi execute nhận transaction status/resource phù hợp với context của nó.

**Bài 2.** Thread A gọi `shared.setTimeout(1)`; thread B gọi `shared.setTimeout(30)` ngay trước execute. Tại sao chương trình vẫn có thể sai dù cả hai thread đều dùng `try/catch` đúng?

**Đáp án:** Cả hai đang sửa **cùng cấu hình**. Transaction definition được manager sử dụng có thể mang timeout của thread còn lại. `try/catch` không cô lập shared mutable configuration.

**Bài 3.** `private final TransactionTemplate template` có đủ khiến các setters bất khả dụng không?

**Đáp án:** Không. `final` chỉ khóa việc gán lại tham chiếu; bản thân object vẫn mutable. Cần hoàn tất cấu hình trước khi chia sẻ và không mutate sau đó.

**Bài 4.** Một callback gọi `status.setRollbackOnly()`, sau đó request khác dùng cùng template và commit thành công. Có trái với thread safety không?

**Đáp án:** Không. `TransactionStatus` là trạng thái của invocation; rollback-only không được ghi thành cấu hình trên template, nên request khác không tự bị rollback theo.

**Bài 5.** Cần `REQUIRED` cho thao tác thông thường và `REQUIRES_NEW` cho audit độc lập. Cách nào an toàn hơn: đổi `setPropagationBehavior` mỗi lần hay tạo hai template cố định?

**Đáp án:** Tạo **hai instance**, cấu hình một lần, chọn theo mục đích. Không mutate một shared object trong đường xử lý đồng thời.

**Bài 6.** Khi caller đang mở transaction outer, một `REQUIRED` template có timeout 1 giây được gọi. Timeout đó có bảo đảm thay đổi deadline của outer không?

**Đáp án:** Không. Khi tham gia physical transaction đã tồn tại, definition mới thường không thay timeout/isolation của outer. Phải thiết kế policy ở đúng transaction boundary.

**Bài 7.** Muốn timeout thay đổi từ 1 tới 120 giây tùy job. Nên làm thế nào?

**Đáp án:** Có thể validate input rồi tạo `new TransactionTemplate(existingManager)` cục bộ, set timeout trước execute, không publish instance ra shared state. Nếu số policy hữu hạn, có thể tạo các named templates sẵn.

**Bài 8.** Tại sao không đưa `TransactionStatus` vào singleton service field để tiện theo dõi transaction đang chạy?

**Đáp án:** Các requests đồng thời sẽ ghi đè/đọc nhầm status nhau. Đối tượng status và context thuộc một transaction scope; giữ trong callback hoặc một scope thích hợp, không share cross-thread.

**Bài 9.** Hai service cùng inject `@Qualifier("standardTemplate")`. Vì sao điều này không tự làm chúng dùng một transaction vật lý?

**Đáp án:** Bean template chỉ là object cấu hình/điều phối. Physical transaction được manager tạo/tham gia theo context tại từng lần execute. Singleton template không đồng nghĩa singleton transaction.

**Bài 10.** Trong project, outer `REQUIRED` ghi row 4, inner `REQUIRES_NEW` ghi row 5, outer ném lỗi. Kết quả nào đúng và vì sao?

**Đáp án:** Row 4 rollback, row 5 đã commit độc lập nên còn. Hai profile khác nhau làm thay transaction boundary; đó là lý do phải chọn policy rõ ràng thay vì đổi setter trên một shared template.

**Bài 11.** Có nên gọi `template.setName(requestId)` trên singleton để log ID từng request không?

**Đáp án:** Không. Đó là mutate configuration state. Dùng tracing/MDC hoặc một cơ chế per-request không can thiệp vào policy của shared template.

**Bài 12.** Nếu test đồng thời chạy 1.000 lần đều pass, có thể bỏ code review cho mutation trên template không?

**Đáp án:** Không. Concurrency bugs phụ thuộc interleaving; test pass không chứng minh không có race. Duy trì invariant: **không thay đổi shared template configuration trong runtime concurrent**.

## 15. Tài liệu chính thức

- Spring Framework — **Programmatic Transaction Management**: phần `Using the TransactionTemplate` và `Specifying Transaction Settings` nêu rõ instance có thể dùng chung, thread-safe với execution, nhưng có configuration state nên policy khác nhau cần template khác: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework Javadoc — `TransactionTemplate`: constructor, `execute`, transaction manager và callback lifecycle: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Framework Javadoc — `TransactionOperations` / `executeWithoutResult`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionOperations.html
- Spring Framework Javadoc — `DefaultTransactionDefinition` và các setter: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/DefaultTransactionDefinition.html
- Spring Framework — **Transaction Propagation** và `REQUIRED` / `REQUIRES_NEW`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **JDBC Connections / DataSourceTransactionManager**: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Boot 3.5.6 release (phiên bản dùng trong lab): https://spring.io/blog/2025/09/18/spring-boot-3-5-6-available-now

**Ghi nhớ:** Dùng một `TransactionTemplate` cố định cho nhiều lời gọi hay nhiều thread là hợp lệ vì nó không giữ transaction state của mỗi callback. Nhưng **đừng đổi các setters trên một instance đang được chia sẻ**. Configuration là shared mutable state; còn `TransactionStatus`, transaction-bound connection và kết quả rollback/commit là per-scope. Nếu policy khác nhau, tạo **templates riêng**; nếu cấu hình thực sự động, tạo **local template** cho operation đó. Kiểm chứng behavior ở đúng transaction boundary thay vì suy đoán từ tên bean hay từ việc code chạy tuần tự.