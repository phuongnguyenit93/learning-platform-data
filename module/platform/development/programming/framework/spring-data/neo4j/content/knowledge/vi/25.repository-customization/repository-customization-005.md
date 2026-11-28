# Truyền ranh giới giao dịch qua các phương thức tùy chỉnh

Một phương thức repository tùy chỉnh có thể thực hiện nhiều thao tác Neo4j trong cùng một use case: cập nhật node, thay đổi relationship properties và ghi thêm một node audit. Nếu mỗi thao tác chạy trong transaction riêng, lỗi ở bước sau có thể để lại graph ở trạng thái chỉ được cập nhật một phần. Spring Data Neo4j (SDN) phối hợp với transaction management của Spring để gom các thao tác này vào một ranh giới giao dịch rõ ràng.

Khi tùy chỉnh repository, cần xác định lớp nào sở hữu ranh giới transaction, phương thức nào tham gia transaction hiện tại và phương thức nào cần một transaction độc lập. `@Transactional` cùng thuộc tính `propagation` điều khiển cách lời gọi đi qua các lớp service, repository fragment, `Neo4jTemplate` và `Neo4jClient` tham gia vào transaction.

## 1. Ranh giới transaction nằm ở đâu?

Transaction là đơn vị công việc cần được thực thi nhất quán. Với SDN, một transaction Neo4j có thể bao gồm nhiều câu Cypher và nhiều thao tác repository. Nếu một bước thất bại và lỗi được rollback theo quy tắc Spring, các thay đổi trong transaction đó được rollback cùng nhau.

~~~mermaid
flowchart TD
    A[Controller] --> B[Service use case]
    B -->|@Transactional| C[Repository proxy]
    C --> D[Custom repository fragment]
    C --> E[Neo4jRepository / Template]
    D --> F[Neo4jClient]
    E --> G[Neo4j transaction manager]
    F --> G
    G --> H[(Neo4j transaction)]
~~~

Service thường là nơi phù hợp để đặt ranh giới transaction vì service biết toàn bộ bước nghiệp vụ cần được thực hiện nguyên tử. Repository tập trung vào thao tác dữ liệu. Một phương thức custom repository vẫn có thể khai báo transaction riêng nếu nó được gọi độc lập hoặc có yêu cầu propagation cụ thể.

## 2. Cấu hình transaction manager của Neo4j

Trong ứng dụng Spring Boot dùng `spring-boot-starter-data-neo4j`, auto-configuration tạo các thành phần kết nối và transaction manager cho Neo4j dựa trên `Driver` đã cấu hình. Các thao tác SDN thông qua repository, template và client được Spring quản lý có thể tham gia transaction này.

Một cấu hình kết nối thường nằm trong `application.yml`:

~~~yaml
spring:
  neo4j:
    uri: bolt://localhost:7687
    authentication:
      username: neo4j
      password: secret-from-environment
    database: neo4j
~~~

Nếu ứng dụng có nhiều transaction manager, chẳng hạn một manager cho cơ sở dữ liệu quan hệ và một manager cho Neo4j, hãy chỉ rõ manager phù hợp trong `@Transactional`. Giá trị `transactionManager` phải khớp với tên bean transaction manager thực tế trong application context.

Ví dụ khi bean Neo4j transaction manager được đặt tên `neo4jTransactionManager`:

~~~java
@Transactional(transactionManager = "neo4jTransactionManager")
public void updateGraph() {
    // Các thao tác SDN thuộc transaction Neo4j.
}
~~~

Nếu chỉ có một transaction manager phù hợp, có thể dùng `@Transactional` mà không chỉ định tên. Không giả định một transaction Neo4j tự động bao trùm các thao tác trên database khác; transaction cục bộ của từng hệ thống không tự tạo thành distributed transaction.

## 3. Khai báo custom repository fragment

Spring Data cho phép mở rộng repository bằng fragment interface và lớp triển khai tương ứng. Ví dụ, một thao tác đổi tên người và ghi audit có thể được đặt trong fragment riêng:

~~~java
import org.springframework.transaction.annotation.Transactional;

public interface PersonWriteOperations {

    @Transactional
    void renameAndRecord(String personKey, String newName, String message);
}
~~~

Repository chính kết hợp fragment với `Neo4jRepository`:

~~~java
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, Long>, PersonWriteOperations {
}
~~~

Lớp triển khai fragment dùng hậu tố `Impl` theo quy ước mặc định của Spring Data:

~~~java
import org.springframework.data.neo4j.core.Neo4jClient;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class PersonWriteOperationsImpl implements PersonWriteOperations {

    private final Neo4jClient neo4jClient;

    public PersonWriteOperationsImpl(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Override
    @Transactional
    public void renameAndRecord(
            String personKey, String newName, String message) {

        neo4jClient.query("""
                MATCH (p:Person {personKey: $personKey})
                SET p.name = $newName
                """)
            .bind(personKey).to("personKey")
            .bind(newName).to("newName")
            .run();

        neo4jClient.query("""
                MATCH (p:Person {personKey: $personKey})
                CREATE (p)-[:HAS_AUDIT {
                    action: 'RENAMED',
                    recordedAt: datetime()
                }]->(:Audit {message: $message})
                """)
            .bind(personKey).to("personKey")
            .bind(message).to("message")
            .run();
    }
}
~~~

Trong ví dụ, `personKey` là property định danh do ứng dụng quản lý trên node `Person`; nó không phải internal ID của Neo4j. Hai câu lệnh Cypher dùng `Neo4jClient` được cấu hình bởi Spring. Annotation `@Transactional` trên hợp đồng fragment và phương thức triển khai làm rõ rằng thao tác tùy chỉnh cần transaction.

Nếu câu lệnh thứ hai thất bại do lỗi runtime, transaction bao quanh phương thức sẽ rollback thay đổi tên ở câu lệnh đầu. Không mở một driver session hoặc transaction độc lập bên trong fragment nếu muốn các câu lệnh tham gia transaction Spring đang hoạt động.

## 4. Gọi phương thức custom bên trong transaction của service

Một use case có thể gọi nhiều repository method. Đặt transaction ở service giúp tất cả thao tác Neo4j thuộc cùng một đơn vị công việc:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PersonService {

    private final PersonRepository people;

    public PersonService(PersonRepository people) {
        this.people = people;
    }

    @Transactional
    public void changeName(
            String personKey, String newName, String auditMessage) {

        people.renameAndRecord(personKey, newName, auditMessage);
    }
}
~~~

Mặc định, `@Transactional` dùng propagation `REQUIRED`. Khi service đã mở transaction, lời gọi `renameAndRecord` với `REQUIRED` tham gia transaction hiện tại thay vì mở một transaction độc lập. Hai câu Cypher trong fragment và các thao tác repository khác được gọi trong cùng use case có thể cùng commit hoặc rollback.

Nếu phương thức custom được gọi độc lập mà không có transaction bên ngoài, `REQUIRED` tạo một transaction mới cho phương thức đó. Vì vậy, cùng một phương thức có thể tham gia transaction của caller hoặc tự tạo ranh giới khi được gọi riêng.

## 5. Các chế độ propagation thường dùng

`Propagation` quy định cách một phương thức xử lý khi đã có transaction đang hoạt động:

| Propagation | Hành vi | Khi phù hợp |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện tại; nếu chưa có thì tạo mới | Mặc định cho phần lớn use case cần tính nguyên tử |
| `REQUIRES_NEW` | Tạm ngưng transaction hiện tại và tạo transaction độc lập | Một thao tác cần commit/rollback riêng với use case bên ngoài |
| `MANDATORY` | Bắt buộc phải có transaction hiện tại; nếu không có thì báo lỗi | Phương thức chỉ hợp lệ khi được gọi trong một use case đã mở transaction |
| `SUPPORTS` | Tham gia nếu có transaction; nếu không thì chạy không có transaction mới | Thao tác có thể chạy trong hoặc ngoài transaction theo ngữ cảnh |
| `NOT_SUPPORTED` | Tạm ngưng transaction hiện tại và chạy ngoài transaction | Công việc được chủ đích thực hiện ngoài transaction |
| `NEVER` | Yêu cầu không có transaction; nếu đang có thì báo lỗi | Phương thức không được phép chạy trong transaction |

Với phần lớn thao tác cập nhật graph cần tính nguyên tử, hãy bắt đầu bằng `REQUIRED`. Các propagation khác làm thay đổi ranh giới commit và rollback, vì vậy cần chọn dựa trên yêu cầu nghiệp vụ.

## 6. Khi nào dùng `REQUIRES_NEW`?

`REQUIRES_NEW` tạo transaction độc lập với transaction bên ngoài. Ví dụ, một bản ghi audit được yêu cầu lưu ngay cả khi use case chính rollback:

~~~java
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class AuditRepository {

    private final Neo4jClient neo4jClient;

    public AuditRepository(Neo4jClient neo4jClient) {
        this.neo4jClient = neo4jClient;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordAttempt(String personKey, String message) {
        neo4jClient.query("""
                CREATE (:Audit {
                    personKey: $personKey,
                    message: $message,
                    recordedAt: datetime()
                })
                """)
            .bind(personKey).to("personKey")
            .bind(message).to("message")
            .run();
    }
}
~~~

Nếu transaction ngoài rollback nhưng transaction audit độc lập đã commit, bản ghi audit vẫn còn. Đây là hành vi có chủ đích và khác với việc ghi audit trong cùng transaction.

Không dùng `REQUIRES_NEW` cho một bước phải thành công hoặc thất bại cùng thao tác chính. Ví dụ đổi tên và tạo relationship bắt buộc phải cùng commit thì nên để cả hai dùng `REQUIRED`. Nếu ghi relationship bằng transaction riêng rồi thao tác chính rollback, graph có thể lưu trạng thái không đúng nghiệp vụ.

`REQUIRES_NEW` cũng cần thêm tài nguyên transaction trong khi transaction ngoài bị tạm ngưng. Dùng quá nhiều transaction lồng theo kiểu độc lập có thể làm tăng tải kết nối và làm luồng commit khó hiểu.

## 7. `MANDATORY` để bảo vệ hợp đồng của phương thức

Một phương thức custom có thể được thiết kế để chỉ chạy trong transaction do service mở:

~~~java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public interface PersonGraphOperations {

    @Transactional(propagation = Propagation.MANDATORY)
    void replaceMemberships(String personKey);
}
~~~

Nếu caller không có transaction đang hoạt động, Spring báo lỗi thay vì âm thầm chạy thao tác độc lập. Cách này hữu ích khi phương thức là một bước bên trong quy trình lớn và không nên được gọi riêng.

Hãy cân nhắc khả năng tái sử dụng trước khi chọn `MANDATORY`. Nếu một phương thức cần được gọi độc lập trong nhiều use case, `REQUIRED` thường linh hoạt hơn.

## 8. Rollback khi có lỗi

Theo mặc định của Spring, transaction rollback khi phương thức kết thúc bằng unchecked exception (`RuntimeException`) hoặc `Error`. Checked exception không tự động kích hoạt rollback theo quy tắc mặc định.

Nếu nghiệp vụ yêu cầu rollback cả checked exception, khai báo `rollbackFor`:

~~~java
@Transactional(rollbackFor = Exception.class)
public void renameAndPublish(String personKey, String newName)
        throws Exception {

    people.renameAndRecord(personKey, newName, "Name changed");
    publishChange(personKey);
}
~~~

Chỉ khai báo `rollbackFor` khi quy tắc nghiệp vụ yêu cầu. Nếu một exception bị bắt rồi không được ném ra khỏi phương thức transactional, Spring có thể không nhận biết rằng use case đã thất bại. Khi cần rollback sau khi xử lý lỗi, hãy ném lại exception hoặc đánh dấu transaction rollback-only theo cơ chế Spring.

Không nuốt exception chỉ để trả về một kết quả thành công giả. Điều đó có thể khiến transaction commit dù một phần nghiệp vụ không hoàn tất.

## 9. `readOnly` và transaction cho truy vấn đọc

Với phương thức chỉ đọc, có thể khai báo:

~~~java
@Transactional(readOnly = true)
public Optional<Person> findPerson(String personKey) {
    return people.findByPersonKey(personKey);
}
~~~

`readOnly = true` biểu thị ý định chỉ đọc và có thể được transaction manager hoặc tầng truy cập dữ liệu dùng như một hint tối ưu. Không coi thuộc tính này là cơ chế phân quyền hay bảo đảm database sẽ từ chối mọi lệnh ghi. Nếu cần ngăn ghi, hãy dùng quyền database và kiểm soát API phù hợp.

Các phương thức CRUD kế thừa và các query method tự khai báo có thể có quy tắc transaction khác nhau tùy cấu hình repository và phiên bản Spring Data. Khi một custom query hoặc fragment cần transaction, khai báo rõ ràng trên service hoặc method thay vì dựa vào giả định rằng mọi method repository đều có cùng cấu hình.

## 10. Proxy, self-invocation và vị trí đặt annotation

Spring thường áp dụng `@Transactional` thông qua proxy. Lời gọi từ bean khác đi qua proxy có thể kích hoạt transaction interceptor. Lời gọi nội bộ từ một method sang method khác trên cùng object (ví dụ `this.someMethod()`) không đi qua proxy trong chế độ proxy thông thường, nên annotation trên method được gọi có thể không được áp dụng như mong đợi.

Ví dụ dễ gây nhầm:

~~~java
public void process() {
    updateGraphInNewTransaction(); // self-invocation
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void updateGraphInNewTransaction() {
    // Không nên giả định REQUIRES_NEW được kích hoạt qua lời gọi nội bộ.
}
~~~

Nếu cần một ranh giới propagation riêng, hãy đặt thao tác đó trong một bean khác và gọi qua dependency được Spring inject. Giữ method transactional ở phạm vi phù hợp, thường là public method được gọi qua proxy.

Với custom repository fragment, khai báo transaction trên method của fragment interface hoặc method triển khai theo cách nhất quán với cấu hình repository. Quan trọng là lời gọi thực tế phải đi qua proxy có transaction interceptor và sử dụng đúng transaction manager.

## 11. Những giới hạn cần lưu ý với Neo4j

- Neo4j transaction có phạm vi trên một database transaction. Không giả định transaction Spring của Neo4j tự bao trùm database quan hệ hoặc dịch vụ bên ngoài.
- Không trộn một `Driver` hoặc `Session` tự tạo độc lập với transaction do SDN quản lý nếu mong muốn chúng cùng commit/rollback.
- Không giả định `Propagation.NESTED` tạo savepoint như trong một số hệ quản trị quan hệ; Neo4j không cung cấp nested transaction/savepoint theo cách đó trong SDN. Nếu cần transaction độc lập, đánh giá `REQUIRES_NEW` và hệ quả commit riêng.
- Với API reactive, transaction context được truyền qua Reactor context và cần reactive transaction manager. Không gọi imperative `Neo4jClient` bên trong reactive pipeline rồi mặc định nó tham gia reactive transaction.
- Transaction dài giữ tài nguyên và có thể làm tăng contention. Giữ ranh giới đủ rộng để bảo đảm nghiệp vụ nhưng tránh thực hiện tác vụ mạng hoặc chờ người dùng bên trong transaction.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Không đặt transaction cho custom method gồm nhiều câu Cypher | Mỗi thao tác có thể chạy độc lập và graph bị ghi dở dang | Đặt `@Transactional` ở service hoặc method custom |
| Dùng `REQUIRES_NEW` cho bước phải cùng commit với nghiệp vụ chính | Transaction con có thể commit dù transaction ngoài rollback | Dùng `REQUIRED` cho các bước cùng một đơn vị công việc |
| Cho rằng `REQUIRED` luôn tạo transaction mới | Lời gọi có thể tham gia transaction của caller | Hiểu propagation mặc định là tham gia nếu đã có transaction |
| Gọi method `REQUIRES_NEW` qua self-invocation | Proxy không được kích hoạt nên propagation không áp dụng | Tách method sang bean khác hoặc gọi qua proxy |
| Bắt và nuốt exception sau khi một bước ghi thất bại | Transaction có thể commit nếu không được đánh dấu rollback-only | Ném lại lỗi hoặc đánh dấu rollback theo quy tắc rõ ràng |
| Dùng `readOnly = true` như cơ chế bảo mật | Không bảo đảm database từ chối mọi lệnh ghi | Dùng quyền database và kiểm soát truy cập |
| Mở driver session riêng bên trong transaction SDN | Thao tác có thể chạy ngoài transaction dự kiến | Dùng `Neo4jClient`/template được Spring quản lý hoặc tích hợp driver tường minh |
| Kỳ vọng một transaction bao trùm nhiều database độc lập | Không có atomic commit tự động giữa các hệ thống | Thiết kế outbox, saga hoặc cơ chế phối hợp phù hợp |

## 13. Quy trình thiết kế transaction cho phương thức tùy chỉnh

1. Xác định các node, relationship và thao tác nào phải cùng thành công hoặc cùng rollback.
2. Đặt ranh giới ở service nếu use case phối hợp nhiều repository hoặc nhiều bước nghiệp vụ.
3. Dùng `REQUIRED` làm lựa chọn mặc định cho các method cần tham gia cùng transaction.
4. Chỉ chọn `REQUIRES_NEW`, `MANDATORY`, `SUPPORTS` hoặc propagation khác khi có lý do nghiệp vụ rõ ràng.
5. Bảo đảm custom fragment, repository, template và client sử dụng transaction manager Neo4j phù hợp.
6. Kiểm tra lời gọi có đi qua Spring proxy; tránh self-invocation khi cần propagation riêng.
7. Xác định exception nào phải rollback; cấu hình `rollbackFor` nếu checked exception cũng cần rollback.
8. Kiểm thử cả trường hợp thành công và lỗi giữa chừng, sau đó đọc graph để xác nhận dữ liệu đã commit hoặc rollback đúng.

## 14. Tự kiểm tra

1. Vì sao service thường là nơi phù hợp để đặt ranh giới transaction cho một use case?
2. `REQUIRED` xử lý thế nào khi caller đã có transaction?
3. Khác biệt giữa `REQUIRED` và `REQUIRES_NEW` là gì khi transaction ngoài rollback?
4. Khi nào `MANDATORY` giúp bảo vệ hợp đồng của custom repository method?
5. Mặc định Spring rollback với loại exception nào?
6. Vì sao self-invocation có thể làm `@Transactional` không hoạt động như mong đợi?
7. Vì sao không nên giả định transaction Neo4j tự bao trùm một database quan hệ?

Khi thiết kế custom repository, hãy để các thao tác cần tính nguyên tử tham gia cùng transaction `REQUIRED` và đặt ranh giới ở service theo use case. Chỉ tạo transaction độc lập khi muốn commit riêng một cách có chủ đích; đồng thời kiểm tra proxy, transaction manager và quy tắc rollback để graph luôn phản ánh đúng kết quả nghiệp vụ.
