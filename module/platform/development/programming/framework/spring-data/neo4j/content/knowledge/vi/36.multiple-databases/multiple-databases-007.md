# Không trộn entity đã tải từ các database hoặc tenant khác nhau

Spring Data Neo4j (SDN) có thể làm việc với nhiều database trên cùng Neo4j DBMS và hỗ trợ chọn database theo tenant. Nhưng một object Java không tự mang theo database mà nó được đọc từ đó. `@Id` chỉ định danh entity trong phạm vi graph mà SDN đang truy cập; cùng một giá trị ID có thể tồn tại ở nhiều database hoặc nhiều tenant.

Vì vậy, entity đã tải từ tenant A không được dùng như entity của tenant B. Khi ngữ cảnh tenant thay đổi giữa hai lần gọi repository, SDN có thể gửi thao tác tiếp theo tới database khác. Nếu tiếp tục lưu object cũ, ứng dụng có thể tạo node sai nơi, cập nhật nhầm node trùng ID hoặc tạo quan hệ tới dữ liệu không thuộc tenant dự kiến.

Bài học này giải thích ranh giới giữa database và tenant, cách SDN chọn database, vì sao transaction phải giữ nguyên tenant context, cách thiết kế tham chiếu entity và cache an toàn, cùng các biện pháp kiểm thử để phát hiện việc trộn dữ liệu.

## Database, graph và tenant là những phạm vi khác nhau

Một Neo4j DBMS có thể quản lý nhiều database. Mỗi standard database là một miền dữ liệu và transaction riêng. Trong ứng dụng, cần phân biệt:

- **DBMS:** máy Neo4j hoặc cụm máy chủ quản lý các database.
- **Database:** miền graph được chọn cho session hoặc transaction.
- **Tenant:** khách hàng, tổ chức hoặc không gian dữ liệu mà ứng dụng đang phục vụ.
- **Entity:** object Java ánh xạ tới node hoặc graph được đọc từ một database trong một ngữ cảnh cụ thể.

Có hai cách phổ biến để phân vùng tenant:

| Chiến lược | Cách tổ chức | Ranh giới dữ liệu |
|---|---|---|
| Database-per-tenant | Mỗi tenant dùng một database riêng | Database name xác định tenant |
| Shared database | Nhiều tenant cùng dùng một database | Property như `tenantId` phân biệt dữ liệu |

Trong mô hình database-per-tenant, hai database có thể cùng chứa `Person` với `employeeCode = "E-01"`. Hai node đó là hai entity khác nhau dù ID có cùng giá trị.

Trong mô hình shared database, các node nằm chung một graph. Mọi truy vấn cần giới hạn theo `tenantId`; chỉ chọn database không thể thay thế điều kiện tenant trong query.

Sơ đồ hai chiến lược:

~~~text
Database-per-tenant

Neo4j DBMS
  |
  +-- tenant_acme
  |     +-- Person E-01
  |     +-- Department D-01
  |
  +-- tenant_zen
        +-- Person E-01
        +-- Department D-01


Shared database

Neo4j DBMS
  |
  +-- application
        +-- Person {tenantId: "acme", employeeCode: "E-01"}
        +-- Department {tenantId: "acme", code: "D-01"}
        +-- Person {tenantId: "zen", employeeCode: "E-01"}
        +-- Department {tenantId: "zen", code: "D-01"}
~~~

Không được coi hai object có cùng `@Id` là cùng một entity nếu chúng đến từ hai database khác nhau. Khi cần truyền một tham chiếu giữa các tầng hoặc qua message queue, phải mang theo cả phạm vi dữ liệu và ID.

## Vì sao entity đã tải không tự nhận biết database nguồn?

Giả sử hai database có dữ liệu:

~~~text
tenant_acme:
  Person { employeeCode: "E-01", fullName: "Lan Nguyen" }

tenant_zen:
  Person { employeeCode: "E-01", fullName: "Minh Tran" }
~~~

Cả hai node đều có thể được ánh xạ thành cùng kiểu Java:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String employeeCode;

    private String fullName;

    protected Person() {
    }

    public String getEmployeeCode() {
        return employeeCode;
    }

    public String getFullName() {
        return fullName;
    }

    public void rename(String newName) {
        this.fullName = newName;
    }
}
~~~

Object `Person` chỉ chứa `employeeCode` và `fullName`. Nó không tự giữ `tenant_acme` hay `tenant_zen` như một phần của identity. Nếu object được tải khi tenant hiện tại là `acme`, sau đó ngữ cảnh đổi sang `zen`, một lời gọi repository mới có thể dùng database `tenant_zen`.

Ví dụ luồng nguy hiểm:

~~~text
1. Tenant context = acme
2. people.findById("E-01")
   -> đọc Lan từ tenant_acme

3. Tenant context đổi thành zen

4. people.save(personAcme)
   -> database selection được lấy lại cho transaction mới
   -> thao tác có thể chạy trên tenant_zen
~~~

Khi đó object được tạo từ graph A nhưng lại được dùng trong graph B. Nếu B đã có node cùng ID, thao tác ghi có thể tác động tới node của B theo mapping và trạng thái object; nếu chưa có, nó có thể tạo node không đúng nghiệp vụ. Nếu object còn chứa relationship, việc ghi có thể tạo liên kết với node cùng ID trong database B thay vì node mà object ban đầu tham chiếu ở database A.

Tài liệu SDN cảnh báo rằng database name được yêu cầu cho mỗi transaction mới. Khi đổi database giữa các lời gọi, ứng dụng có thể nhận thiếu hoặc thừa entity, hoặc lưu entity vào database sai. Do đó, database/tenant context phải ổn định trong toàn bộ use case.

## Chọn database tĩnh và động trong SDN

SDN hỗ trợ chọn database tĩnh hoặc động thông qua `DatabaseSelectionProvider`. Provider được hỏi trước khi repository hoặc template tương tác với Neo4j.

### Chọn một database cố định

Nếu ứng dụng luôn dùng một database, có thể tạo provider tĩnh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;

@Configuration
public class Neo4jDatabaseConfig {

    @Bean
    DatabaseSelectionProvider databaseSelectionProvider() {
        return DatabaseSelectionProvider
            .createStaticDatabaseSelectionProvider("application");
    }
}
~~~

Tất cả repository và `Neo4jTemplate` dùng provider này sẽ làm việc với database `application`. Trong Spring Boot, SDN cũng có cấu hình database tĩnh; tên property và cách bind cần được đối chiếu theo phiên bản Spring Boot/SDN đang dùng.

SDN không tự tạo database. Database và quyền truy cập phải được provision trước bằng công cụ quản trị hoặc migration phù hợp.

### Chọn database theo tenant đã xác thực

Với database-per-tenant, provider có thể tra database từ tenant context do ứng dụng quản lý:

~~~java
import java.util.Optional;

public interface TenantDatabaseResolver {

    Optional<String> currentDatabaseName();
}
~~~

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;

@Configuration
public class TenantNeo4jConfig {

    @Bean
    DatabaseSelectionProvider databaseSelectionProvider(
            TenantDatabaseResolver resolver) {

        return () -> resolver.currentDatabaseName()
            .map(DatabaseSelection::byName)
            .orElseThrow(() ->
                new IllegalStateException("No authenticated tenant database")
            );
    }
}
~~~

`TenantDatabaseResolver` là thành phần của ứng dụng. Nó phải lấy tenant từ danh tính đã xác thực và ánh xạ tenant sang database name trong registry được kiểm soát. Không lấy trực tiếp database name từ request body, query string hoặc header do client tự đặt rồi dùng làm tên database.

Nếu tenant bắt buộc phải có, hãy fail closed khi không tìm được tenant. Trả về `DatabaseSelection.undecided()` trong tình huống thiếu tenant có thể khiến truy vấn chạy vào database mặc định và làm rò rỉ dữ liệu.

### Database scope của Neo4j Driver Session

Một Driver có thể dùng chung cho nhiều database trên cùng DBMS, nhưng mỗi Session được gắn với một database cụ thể. Khi dùng Java Driver trực tiếp, hãy chọn database ngay lúc tạo session:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

try (Session session = driver.session(
        SessionConfig.builder()
            .withDatabase("tenant_acme")
            .build())) {

    long count = session.executeRead(tx ->
        tx.run("MATCH (p:Person) RETURN count(p) AS total")
            .single()
            .get("total")
            .asLong()
    );
}
~~~

Session và transaction của ví dụ này hoạt động trong `tenant_acme`. Tạo session riêng cho từng database/work unit và đóng sau khi dùng. Nếu bỏ qua database, Driver dùng database mặc định của server; điều này có thể làm một query chạy vào nơi không mong muốn. Với SDN, `DatabaseSelectionProvider` thực hiện việc chọn database cho repository/template thay cho việc tự tạo session thủ công.

### Dùng cùng provider cho client và transaction manager

Khi tự cấu hình hạ tầng SDN, `Neo4jClient` và `Neo4jTransactionManager` phải dùng cùng một `DatabaseSelectionProvider` instance. SDN kiểm tra database được chọn trong lời gọi client có khớp database của managed transaction hay không.

Ví dụ cấu hình client:

~~~java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;
import org.springframework.data.neo4j.core.Neo4jClient;

@Bean
Neo4jClient neo4jClient(
        Driver driver,
        DatabaseSelectionProvider databaseSelectionProvider) {

    return Neo4jClient.create(driver)
        .withDatabaseSelectionProvider(databaseSelectionProvider)
        .build();
}
~~~

Nếu ứng dụng cần tự khai báo transaction manager, dùng cùng provider:

~~~java
import org.neo4j.driver.Driver;
import org.springframework.context.annotation.Bean;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;
import org.springframework.data.neo4j.core.transaction.Neo4jTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
PlatformTransactionManager transactionManager(
        Driver driver,
        DatabaseSelectionProvider databaseSelectionProvider) {

    return new Neo4jTransactionManager(driver, databaseSelectionProvider);
}
~~~

Đây là ví dụ cho cấu hình hạ tầng tự quản lý. Nếu Spring Boot đã auto-configure repository, client và transaction manager, hãy cung cấp provider bean theo hướng dẫn của phiên bản đó và để auto-configuration sử dụng nó; không tạo thêm một manager/client riêng không đồng bộ với hạ tầng đang chạy.

## Giữ nguyên tenant context trong một transaction

Một transaction nghiệp vụ nên làm việc với một database/tenant duy nhất. Hãy đọc, kiểm tra và lưu entity trong cùng ranh giới transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository people;
    private final TenantContext tenantContext;

    public PersonService(
            PersonRepository people,
            TenantContext tenantContext) {
        this.people = people;
        this.tenantContext = tenantContext;
    }

    @Transactional
    public Person renamePerson(String employeeCode, String newName) {
        String tenantId = tenantContext.requireTenantId();

        Person person = people.findById(employeeCode)
            .orElseThrow(() -> new IllegalArgumentException("Person not found"));

        if (!tenantContext.isCurrentTenant(tenantId)) {
            throw new IllegalStateException("Tenant context changed");
        }

        person.rename(newName);
        return people.save(person);
    }
}
~~~

Ví dụ minh họa việc cố định và kiểm tra tenant context trong use case. Trong database-per-tenant, repository đã được định tuyến tới database của tenant. Nếu ứng dụng dùng shared database, repository query vẫn cần điều kiện `tenantId`; không thể chỉ dựa vào `DatabaseSelectionProvider`.

Không đổi tenant context ở giữa một transaction. Cũng không mở transaction cho tenant A rồi gọi một client có provider trả về tenant B. SDN có thể phát hiện việc database selection không khớp trong managed transaction và báo lỗi; hãy coi đây là lỗi ranh giới dữ liệu cần sửa, không phải lỗi để bỏ qua.

Tránh giữ entity đã tải qua ranh giới request hoặc đưa entity vào cache dùng chung rồi dùng lại dưới tenant context khác. Nếu cần xử lý sau, hãy truyền một tham chiếu rõ ràng và tải lại entity trong ngữ cảnh tenant đích.

## Truyền tham chiếu thay vì truyền entity qua tenant boundary

Một entity không phải là một định danh toàn cục. Khi cần gửi công việc qua message queue, lưu reference trong cache hoặc gọi một service khác, hãy tạo value object có chứa scope:

~~~java
public record PersonReference(
    String tenantId,
    String employeeCode
) {
}
~~~

Trong nhiều hệ thống, chỉ cần `tenantId` là đủ vì ứng dụng có registry để ánh xạ tenant sang database. Nếu một tác vụ nội bộ thực sự cần mang database name, giá trị đó phải do resolver đáng tin cậy tạo ra; không chấp nhận tên database do client bên ngoài tự cung cấp.

Consumer nhận reference sẽ xác thực tenant, thiết lập context phù hợp rồi tải entity lại. Pseudocode:

~~~java
public Person loadForProcessing(PersonReference reference) {
    tenantAuthorizer.requireAccess(reference.tenantId());

    return tenantContext.callAs(
        reference.tenantId(),
        () -> people.findById(reference.employeeCode())
            .orElseThrow(() ->
                new IllegalArgumentException("Person not found")
            )
    );
}
~~~

`tenantContext.callAs` là API minh họa của ứng dụng; implementation phải giữ context xuyên suốt lời gọi repository và transaction. Với reactive pipeline, context cần tồn tại tới khi publisher hoàn tất hoặc bị hủy.

Không dùng cách này:

~~~java
// Không an toàn: object không chứa database provenance.
Person person = event.getPerson();
people.save(person);
~~~

Dùng reference giúp service đích tải đúng entity từ đúng database và áp dụng authorization tại nơi dữ liệu được truy cập.

## Relationship không thể nối node thuộc hai database khác nhau

Một relationship Neo4j luôn nối hai node trong cùng graph. Không thể tạo relationship `WORKS_IN` từ `Person` trong database `tenant_acme` tới `Department` trong database `tenant_zen`.

Ví dụ mô hình trong một database:

~~~text
tenant_acme

(Person E-01) -[:WORKS_IN]-> (Department D-01)
~~~

Nếu `Person` và `Department` được tải từ hai database khác nhau, property `@Relationship` không biến chúng thành một quan hệ liên database. Việc lưu graph có thể tạo node/relationship sai trong database đang được chọn hoặc thất bại do mapping và dữ liệu không phù hợp.

Nếu nghiệp vụ cần tham chiếu sang tenant khác, lưu một tham chiếu nghiệp vụ có scope thay vì khai báo relationship SDN trực tiếp:

~~~java
public record DepartmentReference(
    String tenantId,
    String departmentCode
) {
}
~~~

Service nhận tham chiếu sẽ xác thực quyền truy cập tenant đích và đọc Department trong database tương ứng. Nếu cần hiển thị dữ liệu từ hai tenant, ứng dụng tổng hợp hai kết quả thành DTO ở tầng service.

Không dùng `@Relationship` như một cơ chế nối graph giữa các database. Cũng không dùng Neo4j `elementId` như khóa toàn cục để tra node trong database khác; ID nội bộ không thay thế cặp định danh gồm scope và business ID.

## Shared database: tenantId phải có mặt trong truy vấn

Nếu nhiều tenant dùng chung một database, `DatabaseSelectionProvider` không phân biệt được các dòng dữ liệu. Nó chỉ chọn database; nó không tự thêm bộ lọc `tenantId` vào mọi query.

Entity có thể chứa tenant key:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {

    @Id
    private String id;

    private String tenantId;
    private String employeeCode;
    private String fullName;

    protected Person() {
    }

    public Person(
            String id,
            String tenantId,
            String employeeCode,
            String fullName) {
        this.id = id;
        this.tenantId = tenantId;
        this.employeeCode = employeeCode;
        this.fullName = fullName;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getEmployeeCode() {
        return employeeCode;
    }
}
~~~

Trong shared database, property được đánh dấu `@Id` phải phân biệt được các node trong chính database đó. Nếu `employeeCode` chỉ duy nhất trong từng tenant, đừng dùng riêng giá trị này làm ID chung cho mọi tenant. Hãy dùng ID toàn cục như UUID hoặc ID có namespace tenant (ví dụ `acme:E-01`), đồng thời giữ `tenantId` để lọc và kiểm tra quyền. Composite uniqueness trên `(tenantId, employeeCode)` bảo vệ business key; nó không biến `@Id` thành khóa ghép.

Repository cần method có tenant scope:

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    Optional<Person> findPersonByIdAndTenantId(String id, String tenantId);

    Optional<Person> findByTenantIdAndEmployeeCode(
        String tenantId,
        String employeeCode
    );
}
~~~

Service lấy tenant từ context đã xác thực:

~~~java
public Person findPerson(String id) {
    String tenantId = tenantContext.requireTenantId();

    return people.findPersonByIdAndTenantId(id, tenantId)
        .orElseThrow(() -> new IllegalArgumentException("Person not found"));
}
~~~

Không cung cấp method chỉ tìm theo ID cho đường truy cập tenant nếu ID không được bảo đảm là global và authorization chưa được áp dụng ở lớp khác. Các custom `@Query`, `Neo4jClient` và query dùng trong batch cũng phải chứa điều kiện tenant.

Ví dụ Cypher có tenant predicate:

~~~cypher
MATCH (p:Person {
    id: $id,
    tenantId: $tenantId
})
RETURN p;
~~~

Với business key chỉ duy nhất trong tenant, có thể tạo composite uniqueness constraint:

~~~cypher
CREATE CONSTRAINT person_tenant_employee_unique
IF NOT EXISTS
FOR (p:Person)
REQUIRE (p.tenantId, p.employeeCode) IS UNIQUE;
~~~

Nếu quy tắc yêu cầu hai property luôn phải có, cần thêm constraint tồn tại phù hợp hoặc node key constraint trên phiên bản/edition hỗ trợ. Composite uniqueness không tự bắt buộc các property phải xuất hiện.

## Cache, batch và background job cũng phải có tenant scope

Lỗi trộn entity không chỉ xảy ra trong repository. Bất kỳ nơi nào lưu object hoặc ID đều phải giữ đúng phạm vi:

| Thành phần | Khóa hoặc payload an toàn |
|---|---|
| Cache database-per-tenant | `(databaseName, entityId)` hoặc `(tenantId, entityId)` |
| Cache shared database | `(tenantId, entityId)` |
| Message queue | `tenantId` + business ID; database name được resolver xác định |
| Batch import/export | Một tenant/database cho mỗi batch hoặc partition |
| Pagination/cursor | Ràng buộc với tenant và query filter ban đầu |
| Bookmark | Chỉ dùng trong cùng database scope |
| Audit log | Ghi rõ tenant/database đã xử lý |
| In-memory map | Dùng key gồm scope và ID, không chỉ ID |

Ví dụ cache chỉ dùng `employeeCode` có thể trả dữ liệu của tenant A cho tenant B nếu cả hai tenant có cùng mã. Key nên chứa scope:

~~~java
String cacheKey = tenantId + ":" + employeeCode;
~~~

Với database-per-tenant, cache key có thể dùng database name đã được resolver xác thực. Với shared database, phải dùng tenant ID vì mọi entity cùng nằm trong một database.

Batch nên gom các công việc cùng tenant/database. Nếu một batch chứa entity từ nhiều database, chia thành từng nhóm và chạy transaction riêng cho từng nhóm. Không thay tenant context liên tục trong khi một transaction hoặc một lần lưu graph còn đang thực thi.

## Reactive application: tenant context nằm trong Reactor Context

Trong ứng dụng reactive, không dựa vào `ThreadLocal` hoặc `SecurityContextHolder` imperative để chọn tenant. Một pipeline có thể đổi thread giữa các operator; tenant context cần được truyền trong Reactor Context hoặc thông qua cơ chế reactive security context.

SDN cung cấp `ReactiveDatabaseSelectionProvider` trả về `Mono<DatabaseSelection>`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;

import reactor.core.publisher.Mono;

@Configuration
public class ReactiveTenantNeo4jConfig {

    static final String TENANT_DATABASE = "tenantDatabase";

    @Bean
    ReactiveDatabaseSelectionProvider reactiveDatabaseSelectionProvider() {
        return () -> Mono.deferContextual(context ->
            Mono.justOrEmpty(context.<String>getOrEmpty(TENANT_DATABASE))
                .map(DatabaseSelection::byName)
                .switchIfEmpty(Mono.error(
                    new IllegalStateException("Missing tenant database context")
                ))
        );
    }
}
~~~

Tầng web hoặc security thiết lập context sau khi xác thực tenant:

~~~java
public Mono<Person> findPersonForTenant(
        String tenantDatabase,
        String employeeCode) {

    return people.findById(employeeCode)
        .contextWrite(context ->
            context.put(
                ReactiveTenantNeo4jConfig.TENANT_DATABASE,
                tenantDatabase
            )
        );
}
~~~

Ví dụ dùng `tenantDatabase` đã được server resolver ánh xạ từ danh tính đã xác thực. Không lấy trực tiếp giá trị này từ payload của client. Trong ứng dụng thực tế, provider và các thành phần reactive security nên cùng đọc một nguồn tenant context đáng tin cậy.

`ReactiveDatabaseSelectionProvider` phải được dùng nhất quán với `ReactiveNeo4jTransactionManager` và `ReactiveNeo4jClient`. Khi một transaction reactive đang chạy, các thao tác trong pipeline phải tiếp tục dùng cùng database selection. Không chuyển sang tenant khác giữa pipeline bằng cách ghi đè Reactor Context ở một đoạn con.

## Bookmark và transaction không được dùng lẫn giữa database

Bookmark biểu diễn trạng thái đã commit trong một database để transaction sau có thể chờ dữ liệu được đồng bộ trong cluster. Bookmark không phải ID entity và không phải token có thể dùng chung cho mọi tenant.

Trong môi trường nhiều database:

- Dùng bookmark với session của cùng database.
- Không lấy bookmark từ `tenant_acme` rồi gắn vào session của `tenant_zen`.
- Bookmark của database `system` có vai trò đặc biệt trong một số thao tác quản trị tạo database; ngoại lệ đó không áp dụng cho luồng dữ liệu entity giữa các tenant.
- Giữ các thao tác cần causal consistency trong cùng session hoặc dùng bookmark manager đúng scope.
- Không dùng bookmark để cố nối hai transaction của hai database thành một transaction.
- Khi một thao tác nghiệp vụ cần ghi hai database, thiết kế điều phối ở tầng ứng dụng.

Neo4j định nghĩa mỗi standard database là một transaction domain; một transaction không thể span qua nhiều database. Vì vậy, không thể mong đợi một `@Transactional` SDN duy nhất bảo đảm atomicity cho hai database tenant độc lập.

Nếu cần cập nhật nhiều database, hãy xác định rõ thứ tự, khả năng retry và cách bù trừ. Có thể dùng saga/outbox hoặc workflow điều phối: mỗi database commit trong transaction riêng, còn trạng thái toàn cục được quản lý bởi ứng dụng. Đừng giả định rollback của database thứ nhất sẽ tự rollback một transaction đã commit ở database thứ hai.

## Kiểm thử để phát hiện trộn entity

Một bộ integration test cho database-per-tenant nên tạo hai database hoặc hai graph cô lập có cùng business ID:

~~~text
tenant_acme: Person E-01, fullName = "Lan"
tenant_zen:  Person E-01, fullName = "Minh"
~~~

Các tình huống cần kiểm tra:

1. Đọc `E-01` trong tenant A trả về Lan.
2. Đọc `E-01` trong tenant B trả về Minh.
3. Entity tải từ A không được chuyển thẳng sang service ghi của B.
4. Transaction đang chạy trong A không được gọi client được cấu hình sang B.
5. Relationship của entity A chỉ được ghi trong graph A.
6. Cache không trả entity A khi truy cập bằng tenant B.
7. Background job tải lại entity từ reference chứa tenant scope.
8. Bookmark của A không được dùng cho session B.
9. Khi thiếu tenant context, provider từ chối truy cập thay vì chọn database mặc định.
10. Với shared database, query thiếu tenant predicate phải được phát hiện qua test hoặc kiểm tra code.

Ví dụ kiểm tra cùng một ID trả dữ liệu khác nhau theo tenant context:

~~~java
@Test
void sameBusinessIdIsResolvedWithinCurrentTenant() {
    tenantContext.runAs("acme", () -> {
        Person person = people.findById("E-01").orElseThrow();
        assertThat(person.getFullName()).isEqualTo("Lan");
    });

    tenantContext.runAs("zen", () -> {
        Person person = people.findById("E-01").orElseThrow();
        assertThat(person.getFullName()).isEqualTo("Minh");
    });
}
~~~

Đây là pseudocode minh họa `tenantContext.runAs`. Implementation thật phải giữ context xuyên suốt cả transaction và subscription. Nếu dùng reactive, dùng `StepVerifier` với `contextWrite` và test hai subscription có tenant context riêng.

Một test quan trọng khác là bảo đảm provider không đổi database giữa transaction:

~~~java
@Transactional
public void updatePersonAndDepartment(String employeeCode) {
    Person person = people.findById(employeeCode).orElseThrow();

    // Mọi thao tác trong method phải tiếp tục dùng cùng tenant/database.
    departmentRepository.findByCode(person.getDepartmentCode());
    people.save(person);
}
~~~

Trong test, thử làm thay đổi tenant context ở giữa method và xác nhận ứng dụng từ chối hoặc SDN phát hiện database selection không khớp. Không bắt lỗi này rồi tiếp tục lưu.

## Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Coi `@Id` là định danh toàn cục | ID giống nhau ở hai database bị nhầm thành một entity | Ghép database/tenant scope với entity ID |
| Lưu entity đã tải từ tenant A trong context B | Ghi nhầm node hoặc tạo relationship sai graph | Tải lại entity bằng reference trong tenant đích |
| Thay tenant giữa các lời gọi trong một use case | Các lần đọc/ghi đi tới database khác nhau | Giữ tenant context cố định trong transaction |
| Dùng provider riêng cho Neo4jClient và transaction manager | Query có thể chọn database khác transaction | Dùng cùng provider instance |
| Thiếu tenant context rồi fallback về default database | Có thể đọc/ghi nhầm tenant | Fail closed khi không xác định được tenant |
| Lấy database name từ request không tin cậy | Người gọi có thể chọn database ngoài quyền của mình | Resolve tenant từ authentication và allowlist |
| Cho rằng provider tự lọc tenant trong shared database | Query có thể đọc dữ liệu của tenant khác | Bổ sung `tenantId` vào mọi query |
| Cache chỉ bằng entity ID | Cache hit có thể trả object của tenant khác | Thêm tenant/database vào cache key |
| Tạo `@Relationship` giữa entity của hai database | Không có quan hệ graph liên database hợp lệ | Dùng reference DTO và resolve riêng |
| Dùng bookmark giữa hai database | Causal context không hợp lệ hoặc không được bảo đảm | Giữ bookmark trong cùng database |
| Mong một transaction commit nhiều database | Atomicity không được bảo đảm | Dùng transaction riêng và workflow điều phối |
| Truyền entity qua queue/background job | Consumer có thể xử lý object dưới tenant context khác | Truyền tenant scope và business ID, rồi tải lại |

## Bài tập thực hành

Với ứng dụng quản lý `Person`, `Department` và relationship `WORKS_IN`, hãy thực hiện:

1. Tạo hai database `tenant_acme` và `tenant_zen`, mỗi database có Person cùng `employeeCode = "E-01"` nhưng tên khác nhau.
2. Viết `DatabaseSelectionProvider` chọn database từ tenant context đã xác thực.
3. Kiểm tra repository trả đúng Person khi tenant context là Acme và Zen.
4. Tải entity ở Acme, chuyển sang Zen rồi thử lưu; xác định rủi ro và sửa thiết kế để tải lại bằng reference.
5. Tạo relationship `WORKS_IN` trong từng database và xác minh endpoint thuộc cùng graph.
6. Thử tham chiếu Department từ database khác; thay bằng `DepartmentReference` và resolve qua service.
7. Viết test provider từ chối khi không có tenant context.
8. Cấu hình `Neo4jClient` và `Neo4jTransactionManager` dùng cùng provider.
9. Với ứng dụng reactive, dùng `ReactiveDatabaseSelectionProvider` và Reactor Context để chọn database.
10. Với shared database, thêm `tenantId` vào Person và viết repository method có tenant predicate.
11. Tạo cache key gồm tenant/database scope và kiểm tra hai tenant có cùng ID không bị trộn.
12. Thiết kế workflow ghi hai database bằng hai transaction riêng và mô tả cách retry/compensation khi một bước thất bại.

Khi làm việc với nhiều database hoặc tenant trong SDN, hãy xem database/tenant là một phần của identity và ranh giới transaction. Giữ tenant context ổn định, dùng provider thống nhất, truyền reference có scope thay vì entity đã tải từ nơi khác, lọc `tenantId` trong shared database và không dùng chung cache/bookmark giữa các database. Cách này ngăn việc đọc, ghi hoặc nối graph của tenant này sang tenant khác.

Tài liệu tham khảo chính thức:

- [Spring Data Neo4j FAQ - Multiple databases and tenant selection](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [DatabaseSelectionProvider API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/DatabaseSelectionProvider.html)
- [ReactiveDatabaseSelectionProvider API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveDatabaseSelectionProvider.html)
- [Neo4j Operations Manual - Database administration and transaction domains](https://neo4j.com/docs/operations-manual/current/database-administration/)
- [Neo4j Java Driver Manual - Session and database selection](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual - Bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/)

