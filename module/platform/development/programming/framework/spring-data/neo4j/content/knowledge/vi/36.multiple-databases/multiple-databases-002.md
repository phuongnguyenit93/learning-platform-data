# DatabaseSelectionProvider và lựa chọn database theo giao dịch

Neo4j 4 trở lên hỗ trợ nhiều database trong cùng một DBMS hoặc cluster. Spring Data Neo4j (SDN) có thể gửi repository, `Neo4jTemplate` và `Neo4jClient` tới một database được chỉ định. Khi ứng dụng chỉ dùng một database, có thể cấu hình tên database cố định. Với hệ thống nhiều tenant, có thể chọn database theo tenant hiện hành bằng `DatabaseSelectionProvider` ở imperative application hoặc `ReactiveDatabaseSelectionProvider` ở reactive application.

Điểm cần thiết kế cẩn thận là database được chọn phải nhất quán trong suốt một đơn vị nghiệp vụ. Một transaction Spring của Neo4j làm việc với một database đích. Nếu tenant context thay đổi giữa các thao tác, ứng dụng có thể đọc một entity từ database này rồi ghi nhầm sang database khác. SDN có cơ chế kiểm tra lựa chọn database giữa client và transaction manager, nhưng ứng dụng vẫn phải giữ tenant context ổn định và xác thực tenant trước khi truy cập dữ liệu.

## 1. Nhiều database trong Neo4j có nghĩa gì?

Một Neo4j DBMS có thể chứa nhiều database logic. Chẳng hạn một cụm Neo4j có thể quản lý:

```text
Neo4j DBMS / Cluster
├── system
├── catalog
├── tenant_acme
├── tenant_globex
└── tenant_initech
```

Mỗi database có graph, node, relationship, constraint và index riêng. Cùng một label và ID có thể xuất hiện trong hai database khác nhau mà không đại diện cho cùng một entity.

Ví dụ, `(:Person {id: 42})` trong `tenant_acme` và `(:Person {id: 42})` trong `tenant_globex` là hai node thuộc hai graph khác nhau. ID chỉ có ý nghĩa trong phạm vi database nếu ứng dụng không tự xây dựng một khóa toàn cục.

SDN chọn database đích cho các thao tác repository và template. Việc chọn database không tạo database mới. Database phải được provision trước, user kết nối phải có quyền truy cập và Neo4j server/edition cần hỗ trợ mô hình nhiều database mà ứng dụng sử dụng.

## 2. Phân biệt database selection với Driver selection

`DatabaseSelectionProvider` chọn một database logic bên trong DBMS mà `Driver` đang kết nối tới. Nó không thay đổi địa chỉ server hoặc chuyển kết nối sang một Neo4j cluster khác.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Chọn `catalog` hoặc `tenant_acme` trên cùng DBMS/cluster | `DatabaseSelectionProvider` |
| Chọn database theo tenant cho imperative SDN | `DatabaseSelectionProvider` |
| Chọn database theo tenant cho reactive SDN | `ReactiveDatabaseSelectionProvider` |
| Kết nối tới hai Neo4j cluster hoặc hai server độc lập | Nhiều `Driver` và bộ client/transaction manager tương ứng |
| Tạo database hoặc cấp quyền cho database | Công cụ quản trị Neo4j, migration hoặc quy trình provisioning |

Không dùng một provider để giả lập routing giữa các server vật lý. Nếu các database nằm trên những cluster khác nhau, phải định tuyến tới `Driver` phù hợp và quản lý riêng client, template cùng transaction manager của mỗi Driver.

## 3. Chọn database tĩnh trong Spring Boot

Nếu toàn bộ ứng dụng chỉ làm việc với một database cụ thể, cấu hình `spring.data.neo4j.database` là đủ:

```yaml
spring:
  neo4j:
    uri: ${NEO4J_URI:bolt://localhost:7687}
    authentication:
      username: ${NEO4J_USERNAME:neo4j}
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: catalog
```

Với cấu hình này, các query do repository imperative/reactive và `Neo4jTemplate`/`ReactiveNeo4jTemplate` tạo ra sẽ sử dụng database `catalog`.

Đây là cách phù hợp khi một application instance luôn làm việc với cùng database, ví dụ service catalog, service identity hoặc một deployment riêng cho từng tenant. Không cần tự viết provider nếu database không thay đổi theo request.

## 4. DatabaseSelection và DatabaseSelectionProvider

SDN cung cấp hai API chính:

- `DatabaseSelection`: đối tượng mô tả database được chọn.
- `DatabaseSelectionProvider`: thành phần trả về lựa chọn database cho imperative access.

`DatabaseSelection.byName("catalog")` chọn database có tên cụ thể. `DatabaseSelection.undecided()` có nghĩa là không chỉ định tên, để Neo4j server chọn database mặc định theo cấu hình của server/user.

`DatabaseSelectionProvider` là functional interface, có thể triển khai bằng lambda:

```java
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;

DatabaseSelectionProvider provider =
    () -> DatabaseSelection.byName("catalog");
```

Nếu luôn dùng database mặc định, có thể dùng:

```java
DatabaseSelectionProvider provider =
    DatabaseSelectionProvider.getDefaultSelectionProvider();
```

Hoặc tạo provider tĩnh:

```java
DatabaseSelectionProvider provider =
    DatabaseSelectionProvider.createStaticDatabaseSelectionProvider("catalog");
```

Các API `DatabaseSelectionProvider` và `DatabaseSelection` có từ SDN 6.0. Provider được hỏi trước khi repository hoặc template tương tác với server. Vì vậy, về mặt kỹ thuật có thể trả về database khác nhau ở những lần tương tác khác nhau; trong ứng dụng nghiệp vụ, chỉ nên làm vậy khi ranh giới tenant và transaction đã được kiểm soát.

## 5. Cấu hình imperative provider theo tenant

Một mô hình multi-tenant phổ biến là ánh xạ tenant đã xác thực sang tên database. Không lấy thẳng database name từ query parameter hoặc HTTP header rồi đưa vào `DatabaseSelection.byName`. Ứng dụng nên có một resolver phía server kiểm tra tenant và ánh xạ sang danh sách database được phép.

Trước tiên, định nghĩa abstraction lấy tenant hiện tại và resolver:

```java
public interface CurrentTenant {
    String requireTenantId();
}
```

```java
import java.util.Map;

public final class TenantDatabaseResolver {
    private final Map<String, String> tenantDatabases;

    public TenantDatabaseResolver(Map<String, String> tenantDatabases) {
        this.tenantDatabases = Map.copyOf(tenantDatabases);
    }

    public String databaseFor(String tenantId) {
        String databaseName = tenantDatabases.get(tenantId);
        if (databaseName == null || databaseName.isBlank()) {
            throw new IllegalArgumentException(
                "No database is configured for tenant " + tenantId
            );
        }
        return databaseName;
    }
}
```

`CurrentTenant` nên lấy tenant ID từ security principal hoặc một context đã được xác thực. Resolver chỉ trả về database name nằm trong cấu hình được quản lý bởi server.

Đăng ký provider:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;

@Configuration
public class TenantNeo4jConfiguration {

    @Bean
    DatabaseSelectionProvider databaseSelectionProvider(
            CurrentTenant currentTenant,
            TenantDatabaseResolver databaseResolver) {

        return () -> DatabaseSelection.byName(
            databaseResolver.databaseFor(currentTenant.requireTenantId())
        );
    }
}
```

Ví dụ giả định `CurrentTenant` và `TenantDatabaseResolver` đã được đăng ký thành bean. Khi repository hoặc template cần truy cập Neo4j, provider lấy tenant hiện tại, phân giải tên database rồi trả `DatabaseSelection` tương ứng.

Trong Spring Boot, chỉ cần cung cấp bean `DatabaseSelectionProvider` phù hợp; SDN auto-configuration sử dụng provider đó cho infrastructure Neo4j. Nếu cấu hình SDN thủ công, phải truyền cùng provider vào client và transaction manager như phần tiếp theo.

## 6. Dùng cùng provider cho Neo4jClient và transaction manager

Với cấu hình thủ công, `Neo4jClient` và `Neo4jTransactionManager` phải dùng cùng một instance `DatabaseSelectionProvider`:

```java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.data.neo4j.core.transaction.Neo4jTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class ManualNeo4jConfiguration {

    @Bean
    Neo4jClient neo4jClient(
            Driver driver,
            DatabaseSelectionProvider databaseSelectionProvider) {
        return Neo4jClient.with(driver)
            .withDatabaseSelectionProvider(databaseSelectionProvider)
            .build();
    }

    @Bean
    PlatformTransactionManager transactionManager(
            Driver driver,
            DatabaseSelectionProvider databaseSelectionProvider) {
        return Neo4jTransactionManager.with(driver)
            .withDatabaseSelectionProvider(databaseSelectionProvider)
            .build();
    }
}
```

Trong ví dụ, Spring inject cùng bean singleton `DatabaseSelectionProvider` vào hai thành phần. Khi một query của `Neo4jClient` chạy bên trong managed transaction, SDN kiểm tra lựa chọn database của client có khớp với database mà transaction manager đã mở hay không. Nếu khác, lời gọi bị từ chối thay vì âm thầm chạy trên một database khác.

Nếu dùng Spring Boot auto-configuration, không cần tự khai báo lại hai bean chỉ để thêm provider. Hãy để Boot cấu hình chúng từ provider bean. Đoạn code trên dành cho trường hợp tự quản lý client và transaction manager.

## 7. Database selection gắn với ranh giới transaction

Khi một service mở transaction bằng `@Transactional`, transaction manager cần chọn database đích để tạo transaction Neo4j. Những repository/template/client operation tham gia transaction đó phải dùng cùng database.

Ví dụ:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {
    private final PersonRepository personRepository;
    private final AuditRepository auditRepository;

    public PersonService(
            PersonRepository personRepository,
            AuditRepository auditRepository) {
        this.personRepository = personRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public void register(Person person) {
        personRepository.save(person);
        auditRepository.recordCreated(person.getCode());
    }
}
```

Nếu provider chọn `tenant_acme` khi transaction bắt đầu, cả hai repository operation phải tham gia transaction trên `tenant_acme`. Không được đổi tenant context giữa hai lời gọi rồi kỳ vọng lời gọi thứ hai chuyển sang `tenant_globex` trong cùng transaction.

Một transaction Neo4j nhắm tới một database. Nếu nghiệp vụ cần cập nhật hai tenant database khác nhau, đó là hai transaction riêng. Không giả định `@Transactional` trên một method sẽ tạo atomic commit xuyên nhiều database. Nếu cần phối hợp nhiều database, phải thiết kế workflow, retry, idempotency và cơ chế bù trừ phù hợp.

## 8. Rủi ro khi tenant context thay đổi giữa các lần gọi

Tài liệu SDN cảnh báo database name được yêu cầu khi bắt đầu transaction hoặc trước tương tác của repository/template. Nếu provider trả về database khác ở lần gọi sau, ứng dụng có thể gặp các tình huống:

- Đọc một `Person` từ database A nhưng ghi object đó vào database B.
- Tìm thấy ít hoặc nhiều entity hơn mong đợi vì mỗi truy vấn đi tới graph khác nhau.
- Ghi dữ liệu vào sai tenant database.
- Dùng ID của một tenant để cập nhật node có cùng ID ở tenant khác.

Ví dụ luồng nguy hiểm:

```text
Request bắt đầu với tenant = acme
        |
        v
findById("P-100") -> tenant_acme
        |
        v
Tenant context bị đổi thành globex
        |
        v
save(person) -> tenant_globex
```

Đây là lỗi cô lập tenant. Một entity được đọc từ database A không tự mang theo thông tin để SDN bắt buộc ghi lại vào A; việc chọn database vẫn phụ thuộc provider tại thời điểm thao tác.

Để tránh:

1. Xác định tenant trước khi vào service nghiệp vụ.
2. Giữ tenant context bất biến trong suốt request và transaction.
3. Không cho phép service tự thay tenant context giữa các repository call.
4. Không truyền entity giữa các tenant mà không có bước kiểm tra ownership.
5. Đặt transaction ở ranh giới nghiệp vụ cần đọc/ghi nhất quán.
6. Kiểm thử việc provider bị gọi nhiều lần và xác nhận mọi lần trong cùng transaction trả về cùng database.

## 9. ReactiveDatabaseSelectionProvider

Ứng dụng reactive sử dụng `ReactiveDatabaseSelectionProvider` thay cho imperative provider. Interface này trả về `Mono<DatabaseSelection>`:

```java
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import reactor.core.publisher.Mono;

ReactiveDatabaseSelectionProvider provider =
    () -> Mono.just(DatabaseSelection.byName("catalog"));
```

Provider tĩnh có thể tạo bằng:

```java
ReactiveDatabaseSelectionProvider provider =
    ReactiveDatabaseSelectionProvider
        .createStaticDatabaseSelectionProvider("catalog");
```

Hoặc dùng database mặc định:

```java
ReactiveDatabaseSelectionProvider provider =
    ReactiveDatabaseSelectionProvider.getDefaultSelectionProvider();
```

`ReactiveDatabaseSelectionProvider` cũng có từ SDN 6.0. Khác biệt quan trọng là provider có thể cần đọc tenant từ Reactor Context để giữ đúng ngữ cảnh khi pipeline chuyển thread. Không dùng `ThreadLocal` hoặc `SecurityContextHolder` imperative làm nguồn duy nhất cho reactive tenant routing.

## 10. Đọc tenant từ Reactor Context

Với WebFlux, tenant có thể được xác định từ security context đã xác thực ở biên request, sau đó truyền vào Reactor Context. Provider đọc giá trị này bằng `deferContextual`:

```java
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import reactor.core.publisher.Mono;

public final class TenantContextKeys {
    public static final String TENANT_ID = "tenantId";

    private TenantContextKeys() {
    }
}
```

```java
@Bean
ReactiveDatabaseSelectionProvider reactiveDatabaseSelectionProvider(
        TenantDatabaseResolver databaseResolver) {

    return () -> Mono.deferContextual(context -> {
        String tenantId = context.get(TenantContextKeys.TENANT_ID);
        String databaseName = databaseResolver.databaseFor(tenantId);
        return Mono.just(DatabaseSelection.byName(databaseName));
    });
}
```

Provider chỉ trả `Mono` khi tenant context có mặt và tenant được resolver chấp nhận. Nếu thiếu tenant, `context.get(...)` phát lỗi; với hệ thống multi-tenant, đây thường là hành vi an toàn hơn việc âm thầm dùng database mặc định.

Ở biên ứng dụng, đặt tenant ID đã xác thực vào context của subscription:

```java
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Flux;

public class ReactivePersonService {
    private final ReactivePersonRepository personRepository;

    public ReactivePersonService(ReactivePersonRepository personRepository) {
        this.personRepository = personRepository;
    }

    @Transactional(readOnly = true)
    public Flux<Person> findAll() {
        return personRepository.findAll();
    }
}
```

Caller đặt tenant context bên ngoài publisher transactional:

```java
public Flux<Person> findPeople(String authenticatedTenantId) {
    return personService.findAll()
        .contextWrite(context -> context.put(
            TenantContextKeys.TENANT_ID,
            authenticatedTenantId
        ));
}
```

`authenticatedTenantId` ở đây phải đến từ security principal hoặc tenant resolver đáng tin cậy, không phải giá trị do client tự khai báo mà chưa được kiểm tra.

Với service có `@Transactional`, hãy đặt `contextWrite` ở phía caller bên ngoài publisher được proxy transaction quản lý để tenant context có mặt ngay khi transaction manager bắt đầu xử lý subscription. Không đặt tenant context muộn bên trong một publisher đã mở transaction.

## 11. Cấu hình reactive client và transaction manager

Khi cấu hình reactive SDN thủ công, truyền cùng một `ReactiveDatabaseSelectionProvider` vào reactive client và reactive transaction manager:

```java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;
import org.springframework.data.neo4j.core.ReactiveNeo4jClient;
import org.springframework.data.neo4j.core.transaction.ReactiveNeo4jTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class ManualReactiveNeo4jConfiguration {

    @Bean
    ReactiveNeo4jClient reactiveNeo4jClient(
            Driver driver,
            ReactiveDatabaseSelectionProvider databaseSelectionProvider) {
        return ReactiveNeo4jClient.with(driver)
            .withDatabaseSelectionProvider(databaseSelectionProvider)
            .build();
    }

    @Bean
    ReactiveTransactionManager reactiveTransactionManager(
            Driver driver,
            ReactiveDatabaseSelectionProvider databaseSelectionProvider) {
        return ReactiveNeo4jTransactionManager.with(driver)
            .withDatabaseSelectionProvider(databaseSelectionProvider)
            .build();
    }
}
```

Runtime check giữa reactive client và transaction manager cũng xác nhận database được chọn có khớp với transaction đang quản lý hay không. Trong Spring Boot, chỉ cần cung cấp provider bean để auto-configuration sử dụng; không khai báo lại client/manager nếu không có nhu cầu thay thế infrastructure mặc định.

## 12. Database selection không thay thế authorization

Provider chỉ quyết định database nào được dùng. Nó không tự xác thực user có quyền truy cập tenant đó hay không. Trách nhiệm bảo mật nằm ở authentication, authorization, tenant resolver và quyền database của user kết nối Neo4j.

Các quy tắc nên áp dụng:

- Tenant ID phải được lấy từ danh tính đã xác thực hoặc membership đã kiểm tra.
- Mapping tenant → database phải được quản lý phía server.
- Tenant không tồn tại hoặc không được cấp database phải bị từ chối.
- Không cho phép client truyền database name tùy ý.
- Neo4j user chỉ có quyền cần thiết đối với các database được phép.
- Không trả dữ liệu hoặc thông báo lỗi có thể tiết lộ tenant khác.

Trong mô hình dùng chung một technical Neo4j user có quyền truy cập nhiều database, provider là một phần của ranh giới cô lập ở ứng dụng. Cần kiểm thử kỹ vì một lỗi định tuyến có thể trở thành lỗi rò rỉ dữ liệu giữa tenant.

## 13. Database selection và health indicator

Spring Boot Actuator Neo4j health indicator mặc định kiểm tra kết nối tới database mặc định vì `Driver` kết nối tới DBMS, còn database selection thuộc SDN. Nếu user cấu hình chỉ có quyền trên `tenant_acme` nhưng không có quyền truy cập database mặc định, health indicator mặc định có thể báo DOWN dù repository truy cập database tenant thành công.

Trong hệ thống multi-database, cần kiểm tra health theo đúng database selection hoặc cung cấp custom health contributor dùng cùng provider. Health check cũng phải xác định tenant/database mục tiêu; một lần kiểm tra database mặc định không chứng minh mọi tenant database đều sẵn sàng.

## 14. Kiểm thử database selection

Nên kiểm thử ít nhất các tình huống sau:

| Tình huống | Kỳ vọng |
|---|---|
| Provider tĩnh chọn `catalog` | Repository và template truy cập `catalog` |
| Tenant `acme` đã đăng ký | Provider chọn `tenant_acme` |
| Tenant không có trong resolver | Request bị từ chối; không fallback sang database mặc định |
| Thiếu tenant context trong reactive flow | Publisher phát lỗi trước khi truy vấn graph |
| Hai repository call trong cùng transaction | Cùng dùng một database đã chọn |
| Provider/client và transaction manager khác database | Runtime check báo lỗi |
| Cùng ID tồn tại ở hai tenant database | Đọc/ghi đúng graph theo tenant hiện hành |
| Tenant context bị đổi trong transaction | Bị ngăn chặn hoặc kiểm thử phát hiện mismatch |
| Health indicator | Kiểm tra đúng database mà ứng dụng cần xác nhận |

Một integration test có thể tạo hai database test với cùng label và ID nhưng dữ liệu khác nhau:

```text
tenant_acme:   (:Person {code: "P-1", name: "An"})
tenant_globex: (:Person {code: "P-1", name: "Binh"})
```

Gọi cùng một repository method dưới hai tenant context và xác nhận kết quả khác nhau theo database. Sau đó kiểm tra một lần ghi dưới tenant `acme` không làm thay đổi node của `globex`.

Với reactive provider, dùng `StepVerifier` và `contextWrite` để xác nhận subscription mang đúng tenant ID. Không chỉ gọi trực tiếp `getDatabaseSelection()` ngoài Reactor Context vì khi đó không mô phỏng đúng luồng ứng dụng.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Repository luôn truy cập database mặc định | Chưa cấu hình database tĩnh hoặc provider bean | Kiểm tra `spring.data.neo4j.database` hoặc provider |
| Không tìm thấy database | Database chưa được tạo hoặc tên sai | Provision database và kiểm tra tên được resolver trả về |
| Lỗi quyền truy cập | Neo4j user không có quyền trên database được chọn | Cấp quyền tối thiểu cần thiết cho user |
| Entity được đọc ở tenant này nhưng ghi sang tenant khác | Tenant context thay đổi giữa các lần tương tác | Giữ tenant ổn định và dùng transaction bao quanh nghiệp vụ |
| Runtime báo database mismatch trong transaction | Client và transaction manager dùng provider khác nhau hoặc provider trả kết quả khác | Dùng cùng provider instance và giữ context bất biến |
| Reactive provider không tìm thấy tenant | Tenant chưa có trong Reactor Context | Đặt context ở biên subscription trước khi transaction bắt đầu |
| Reactive routing sai sau khi đổi scheduler | Dựa vào `ThreadLocal`/imperative security context | Dùng Reactor Context và reactive security context |
| Một provider không route tới server khác | Nhầm database selection với cluster routing | Dùng Driver/client riêng cho từng server hoặc cluster |
| Actuator báo Neo4j DOWN | Health indicator kiểm tra database mặc định | Tạo health contributor aware database selection |
| Hai tenant thấy cùng dữ liệu | Resolver trả cùng database hoặc code bỏ qua tenant context | Kiểm tra mapping tenant-database và integration test isolation |

## 16. Quy trình triển khai nhiều database

1. Xác định các database nằm trong cùng DBMS/cluster hay trên nhiều server độc lập.
2. Provision database, constraint, index và quyền truy cập trước khi ứng dụng dùng chúng.
3. Nếu toàn bộ application dùng một database, cấu hình `spring.data.neo4j.database`.
4. Nếu imperative multi-tenant, cung cấp `DatabaseSelectionProvider` dựa trên tenant đã xác thực.
5. Nếu reactive multi-tenant, cung cấp `ReactiveDatabaseSelectionProvider` đọc tenant từ Reactor Context.
6. Dùng cùng provider instance cho Neo4j client và transaction manager.
7. Đặt transaction ở ranh giới nghiệp vụ và giữ tenant/database ổn định trong suốt transaction.
8. Không dùng một entity được nạp từ database này như thể nó thuộc database khác.
9. Nếu cần truy cập nhiều cluster, cấu hình nhiều Driver và bộ infrastructure riêng.
10. Kiểm thử isolation, authorization, database mismatch và health check cho từng tenant.

## 17. Tự kiểm tra

1. `DatabaseSelectionProvider` và `DatabaseSelection` có vai trò gì?
2. Khi nào nên dùng `spring.data.neo4j.database` thay vì dynamic provider?
3. Vì sao `DatabaseSelection.undecided()` có thể nguy hiểm trong hệ thống multi-tenant?
4. Vì sao không nên lấy database name trực tiếp từ request parameter?
5. Tại sao `Neo4jClient` và `Neo4jTransactionManager` cần dùng cùng provider instance?
6. Điều gì xảy ra nếu tenant context thay đổi giữa hai repository call trong cùng transaction?
7. `ReactiveDatabaseSelectionProvider` khác imperative provider ở kiểu trả về và cách lấy tenant context như thế nào?
8. Vì sao reactive tenant context nên được truyền bằng Reactor Context?
9. Database selection khác Driver/cluster routing ở điểm nào?
10. Một `@Transactional` có thể bảo đảm atomic commit trên hai tenant database khác nhau không?
11. Vì sao SDN không tự tạo database khi provider trả về tên database mới?
12. Cần kiểm thử những gì để chứng minh dữ liệu giữa các tenant được cô lập?

## Tài liệu tham khảo

- [Spring Data Neo4j — FAQ: Multiple databases](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j — DatabaseSelection API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/DatabaseSelection.html)
- [Spring Data Neo4j — DatabaseSelectionProvider API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/DatabaseSelectionProvider.html)
- [Spring Data Neo4j — ReactiveDatabaseSelectionProvider API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveDatabaseSelectionProvider.html)
- [Spring Data Neo4j — Neo4jClient.Builder API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/Neo4jClient.Builder.html)
- [Spring Data Neo4j — Neo4jTransactionManager.Builder API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.Builder.html)
