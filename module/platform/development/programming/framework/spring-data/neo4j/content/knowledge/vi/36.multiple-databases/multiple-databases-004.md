# Thiết kế tenant theo database hoặc theo mô hình dữ liệu

Khi xây dựng ứng dụng nhiều tenant với Spring Data Neo4j (SDN), có hai hướng phổ biến để phân vùng dữ liệu: cấp một Neo4j database riêng cho mỗi tenant, hoặc dùng chung một database và gắn khóa tenant vào dữ liệu graph. Lựa chọn này ảnh hưởng đến mức độ cô lập dữ liệu, cách định tuyến truy vấn, transaction, schema migration, backup, chi phí vận hành và khả năng mở rộng.

SDN hỗ trợ chọn database tĩnh hoặc động, nhưng không tự cung cấp một cơ chế multi-tenancy hoàn chỉnh. Ứng dụng vẫn phải xác định tenant đáng tin cậy, ánh xạ tenant sang database hoặc tenant key, bảo đảm mọi truy vấn tuân theo phạm vi đó và quản lý vòng đời database/schema.

## 1. Hai cách phân vùng dữ liệu chính

Giả sử nền tảng quản lý dự án có nhiều khách hàng. Mỗi tenant sở hữu Person, Team, Project và các relationship giữa chúng.

**Database-per-tenant** tạo một standard database riêng cho từng tenant:

~~~text
Neo4j DBMS
  +-- tenant_alpha
  |     +-- Person, Team, Project
  +-- tenant_beta
  |     +-- Person, Team, Project
  +-- tenant_gamma
        +-- Person, Team, Project
~~~

Mỗi database chứa graph riêng. Cùng một label hoặc relationship type có thể được dùng lại trong nhiều database mà không trộn dữ liệu.

**Shared database với tenant key** đặt dữ liệu của nhiều tenant trong cùng một graph, đồng thời gắn tenantId lên node và relationship thuộc tenant:

~~~text
Neo4j database: application
  +-- Person {tenantId: "alpha", ...}
  +-- Team   {tenantId: "alpha", ...}
  +-- Person {tenantId: "beta", ...}
  +-- Team   {tenantId: "beta", ...}
~~~

Các truy vấn phải lọc theo tenantId để chỉ đọc hoặc thay đổi phần graph thuộc tenant hiện tại.

Hai hướng này không phải lựa chọn về cách đặt tên database đơn thuần. Chúng xác định ranh giới dữ liệu và cách ứng dụng chứng minh một truy vấn chỉ được phép truy cập đúng tenant.

## 2. So sánh database-per-tenant và shared database

| Tiêu chí | Database-per-tenant | Shared database + tenant key |
| --- | --- | --- |
| Cô lập dữ liệu | Ranh giới database rõ ràng | Phụ thuộc tenant key và mọi truy vấn |
| Định tuyến trong SDN | Chọn database theo tenant | Chọn tenantId cho query |
| Schema/index/constraint | Quản lý trên từng database | Quản lý một schema chung |
| Backup/restore một tenant | Có thể thao tác theo database | Thường cần quy trình trích xuất hoặc phục hồi theo tenant |
| Truy vấn xuyên tenant | Phải truy vấn từng database hoặc có kiến trúc tổng hợp riêng | Có thể truy vấn một graph, nhưng phải được cấp quyền rõ ràng |
| Transaction | Mỗi transaction thuộc một database | Một transaction có thể cập nhật nhiều tenant trong cùng database nếu nghiệp vụ cho phép |
| Chi phí vận hành | Tăng theo số database và vòng đời tenant | Ít database hơn, schema chung dễ quản lý hơn |
| Nguy cơ truy vấn sai tenant | Định tuyến nhầm database | Quên tenant predicate hoặc tạo relationship sai tenant |
| Tenant có tải rất khác nhau | Dễ tách tenant lớn sang database riêng | Có thể xuất hiện noisy neighbor trong cùng database |
| Tùy biến schema theo tenant | Có thể nhưng làm tăng độ phức tạp migration | Khó duy trì nếu mỗi tenant cần schema khác nhau |

Database riêng tạo ranh giới graph ở cấp database. Shared database tận dụng chung tài nguyên và schema nhưng yêu cầu kỷ luật tenant filtering ở mọi đường truy cập dữ liệu.

Không có lựa chọn tốt nhất cho mọi ứng dụng. Hãy dựa trên yêu cầu cô lập, quy mô tenant, workload và khả năng vận hành database.

## 3. Khi nào nên chọn database-per-tenant?

Database riêng phù hợp khi tenant cần mức cô lập dữ liệu cao, có chính sách lưu trữ hoặc backup riêng, có workload lớn hoặc có yêu cầu vận hành khác biệt.

Các trường hợp thường phù hợp:

- Tenant có yêu cầu hợp đồng hoặc quy định về vị trí và vòng đời dữ liệu.
- Cần backup, restore, export hoặc xóa dữ liệu của một tenant theo ranh giới rõ.
- Một số tenant có dữ liệu hoặc lưu lượng lớn hơn nhiều tenant còn lại.
- Cần triển khai migration hoặc bảo trì theo từng tenant.
- Cần giới hạn quyền truy cập ở cấp database bằng vai trò và quyền Neo4j.

Tách database không tự động bảo đảm an toàn nếu ứng dụng dùng một tài khoản Neo4j có quyền truy cập mọi database và định tuyến tenant không được kiểm soát. Hãy kết hợp database boundary với xác thực, phân quyền và nguyên tắc least privilege.

Mô hình này cũng có chi phí: provisioning database, chạy migration cho từng database, theo dõi trạng thái, backup, restore, giới hạn số database và xử lý tenant bị ngừng hoạt động. Khi số tenant tăng nhanh, công việc vận hành có thể trở thành phần khó nhất.

## 4. Khi nào nên chọn shared database với tenant key?

Shared database phù hợp khi số tenant lớn, mỗi tenant có dữ liệu vừa phải, phần lớn tenant dùng chung một mô hình domain và ứng dụng cần tận dụng chung schema/index.

Các trường hợp thường phù hợp:

- Có nhiều tenant nhỏ hoặc vừa với workload tương đối đồng đều.
- Không cần backup/restore độc lập ở cấp database cho từng tenant.
- Các tenant dùng chung entity model và quy tắc truy vấn.
- Muốn giảm số lượng database cần provision và migrate.
- Có thể áp dụng tenant scoping nhất quán ở service, repository và custom Cypher.

Điểm khó nhất là bảo đảm mọi truy vấn đều có tenant predicate. SDN không tự thêm tenantId vào tất cả repository query hoặc Cypher tùy chỉnh chỉ vì ứng dụng có khái niệm tenant. Một method quên điều kiện tenant có thể đọc hoặc sửa dữ liệu của tenant khác.

Tenant key là cơ chế phân vùng dữ liệu ở tầng mô hình và ứng dụng. Nó không tương đương với database-level access control. Cần kiểm thử tenant isolation như một yêu cầu bảo mật.

## 5. Thiết kế tenant key trong graph dùng chung

Với shared database, mọi node thuộc tenant nên có tenantId. Các property định danh nghiệp vụ thường cần kết hợp tenantId để tạo khóa duy nhất trong phạm vi tenant.

Ví dụ:

~~~cypher
CREATE CONSTRAINT person_tenant_business_id_unique IF NOT EXISTS
FOR (person:Person)
REQUIRE (person.tenantId, person.businessId) IS UNIQUE;

CREATE CONSTRAINT team_tenant_business_id_unique IF NOT EXISTS
FOR (team:Team)
REQUIRE (team.tenantId, team.businessId) IS UNIQUE;
~~~

Constraint bảo đảm tổ hợp tenantId và businessId là duy nhất. Nó không có nghĩa businessId phải duy nhất trên toàn database. Trong SDN, property được ánh xạ bằng @Id vẫn cần định danh entity duy nhất trong database; đừng mặc định composite constraint trên tenantId/businessId tự trở thành composite @Id. Một cách rõ ràng là giữ id kỹ thuật duy nhất cho @Id và dùng businessId làm khóa nghiệp vụ trong phạm vi tenant. Lưu ý uniqueness constraint không tự buộc mọi node phải có đủ cả hai property; ứng dụng cần validate dữ liệu và cân nhắc key/existence constraint nếu edition và phiên bản Neo4j hỗ trợ.

Ví dụ entity có ID kỹ thuật và business ID theo tenant:

~~~java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Person")
public class Person {
    @Id
    private String id; // ID duy nhất trong database

    private String tenantId;
    private String businessId;
}
~~~

Relationship thuộc tenant cũng nên được tạo theo quy tắc tenant nhất quán. Có thể lưu tenantId trên relationship để dễ kiểm tra và lọc:

~~~cypher
MATCH (person:Person {
    tenantId: $tenantId,
    businessId: $personId
})
MATCH (team:Team {
    tenantId: $tenantId,
    businessId: $teamId
})
MERGE (person)-[membership:MEMBER_OF {
    tenantId: $tenantId
}]->(team)
ON CREATE SET membership.joinedAt = datetime()
RETURN person, membership, team
~~~

Cả hai đầu relationship và relationship property đều được ràng buộc với tenant hiện tại. Điều này giảm nguy cơ tạo edge nối node thuộc hai tenant khác nhau.

Nếu graph có node dùng chung toàn hệ thống như danh mục tham chiếu, hãy mô hình hóa chúng thành nhóm dữ liệu global rõ ràng. Đừng coi một node global là node của tenant đầu tiên tạo ra nó rồi cho các tenant khác liên kết tùy ý.

## 6. Tenant predicate phải có mặt trong truy vấn

Mỗi truy vấn đọc hoặc ghi dữ liệu tenant cần lấy tenantId từ ngữ cảnh đã xác thực và đưa nó vào điều kiện Cypher.

Ví dụ truy vấn một Person và các Team liên quan:

~~~cypher
MATCH (person:Person {
    tenantId: $tenantId,
    businessId: $personId
})
MATCH (person)-[membership:MEMBER_OF {
    tenantId: $tenantId
}]->(team:Team {
    tenantId: $tenantId
})
RETURN person, membership, team
~~~

Với repository method:

~~~java
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends Neo4jRepository<Person, String> {

    @Query("""
        MATCH (person:Person {
            tenantId: $tenantId,
            businessId: $businessId
        })
        RETURN person
        """)
    Optional<Person> findForTenant(
        @Param("tenantId") String tenantId,
        @Param("businessId") String businessId
    );
}
~~~

TenantId phải được lấy từ principal hoặc tenant context đã được server xác minh. Không tin một tenantId do client gửi trong query string hoặc request body nếu chưa kiểm tra người dùng có quyền truy cập tenant đó.

Các quy tắc cần áp dụng nhất quán:

1. Lọc tenant trên node bắt đầu và mọi node tenant-owned được trả về.
2. Lọc tenant trên relationship nếu relationship mang tenant key.
3. Khi tạo edge, xác nhận hai đầu thuộc cùng tenant hoặc thuộc một quan hệ global được cho phép.
4. Dùng tenant key trong MERGE để tránh ghép nhầm node có cùng business ID ở tenant khác.
5. Kiểm tra mọi custom @Query, Cypher-DSL và Neo4jClient query; không chỉ derived repository method.
6. Không cho phép client tự chọn tenant bằng cách thay đổi một tham số không được authorization kiểm tra.

Một base service hoặc repository fragment có thể giúp chuẩn hóa cách truyền tenantId, nhưng không thay thế việc review và kiểm thử từng truy vấn.

## 7. Index và constraint cho shared database

Trong shared database, truy vấn thường lọc tenantId cùng business key hoặc trạng thái. Hãy thiết kế index theo đúng query pattern.

Ví dụ:

~~~cypher
CREATE RANGE INDEX person_tenant_status IF NOT EXISTS
FOR (person:Person)
ON (person.tenantId, person.status);

CREATE RANGE INDEX team_tenant_slug IF NOT EXISTS
FOR (team:Team)
ON (team.tenantId, team.slug);
~~~

Composite uniqueness constraint trên tenantId và businessId đã có backing index để bảo vệ uniqueness và hỗ trợ lookup theo tổ hợp đó. Không tạo thêm một index trùng mục đích mà chưa kiểm tra execution plan.

Trong database-per-tenant, mỗi database có schema/index riêng. Các constraint và index phải được tạo trong từng database; tạo schema ở database tenant_alpha không tự áp dụng sang tenant_beta.

## 8. Chọn database tĩnh trong Spring Data Neo4j

Nếu toàn bộ ứng dụng chỉ dùng một database, cấu hình tĩnh là cách đơn giản nhất:

~~~yaml
spring:
  data:
    neo4j:
      database: application
~~~

Với cấu hình này, repository, Neo4jTemplate và Neo4jClient được SDN cấu hình để dùng database application.

Cấu hình tĩnh phù hợp với ứng dụng đơn tenant hoặc một deployment chỉ phục vụ một tenant/database. Nó không tự định tuyến các request của nhiều tenant tới các database khác nhau.

SDN không tạo database cho ứng dụng. Database phải được provision trước bằng lệnh quản trị, migration tool hoặc quy trình vận hành phù hợp.

## 9. Định tuyến database động bằng DatabaseSelectionProvider

Với database-per-tenant, SDN cho phép cung cấp bean DatabaseSelectionProvider. Provider được hỏi trước mỗi lần repository hoặc template tương tác với Neo4j và trả về DatabaseSelection cho database cần dùng.

Ứng dụng cần một tenant context và một registry server-side ánh xạ tenant ID sang database name:

~~~java
public interface TenantContext {
    String requireTenantId();
}

public interface TenantDatabaseRegistry {
    String requireDatabaseName(String tenantId);
}
~~~

Hai interface trên là thành phần do ứng dụng định nghĩa. Registry nên lấy từ cấu hình hoặc metadata quản trị được kiểm soát, không ghép tên database trực tiếp từ chuỗi tenant do client gửi.

Bean provider imperative:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;

@Configuration
public class TenantDatabaseConfiguration {

    @Bean
    DatabaseSelectionProvider databaseSelectionProvider(
            TenantContext tenantContext,
            TenantDatabaseRegistry registry) {

        return () -> {
            String tenantId = tenantContext.requireTenantId();
            String databaseName = registry.requireDatabaseName(tenantId);
            return DatabaseSelection.byName(databaseName);
        };
    }
}
~~~

Provider trả về database name đã được registry xác nhận. Nếu tenant không tồn tại hoặc không có database mapping, hãy ném lỗi và từ chối request. Không trả DatabaseSelection.undecided() như một fallback cho request tenant-specific, vì giá trị này có nghĩa là để server chọn default database và có thể khiến dữ liệu đi nhầm nơi.

Khi dùng Spring Boot, bean DatabaseSelectionProvider được SDN sử dụng cho hạ tầng repository/client/transaction tương ứng. Nếu tự cấu hình Neo4jClient và Neo4jTransactionManager, truyền cùng một provider instance cho cả hai để chúng chọn cùng database.

## 10. Định tuyến trong ứng dụng reactive

Reactive application cần ReactiveDatabaseSelectionProvider. Không dựa vào ThreadLocal để tìm tenant vì một reactive request có thể chuyển thread trong quá trình xử lý.

Ví dụ định nghĩa một abstraction đọc tenant từ Reactor Context hoặc reactive security context:

~~~java
import reactor.core.publisher.Mono;

public interface ReactiveTenantContext {
    Mono<String> currentTenantId();
}
~~~

Provider reactive:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.ReactiveDatabaseSelectionProvider;

@Configuration
public class ReactiveTenantDatabaseConfiguration {

    @Bean
    ReactiveDatabaseSelectionProvider reactiveDatabaseSelectionProvider(
            ReactiveTenantContext tenantContext,
            TenantDatabaseRegistry registry) {

        return () -> tenantContext.currentTenantId()
            .map(registry::requireDatabaseName)
            .map(DatabaseSelection::byName);
    }
}
~~~

ReactiveTenantContext là abstraction của ứng dụng; implementation có thể đọc tenant đã xác thực từ ReactiveSecurityContextHolder hoặc Reactor Context. Nếu không có tenant context, publisher nên phát lỗi thay vì trả empty Mono để chọn default database.

Trong cấu hình reactive thủ công, dùng cùng ReactiveDatabaseSelectionProvider instance cho ReactiveNeo4jClient và ReactiveNeo4jTransactionManager. Điều này giữ database selection nhất quán trong managed transaction.

## 11. Giữ tenant ổn định trong một transaction

DatabaseSelectionProvider được hỏi trước các lần tương tác repository/template. Vì vậy, provider có thể trả database khác nhau ở các interaction khác nhau nếu tenant context thay đổi. SDN kiểm tra database được chọn trong managed transaction và có thể báo lỗi nếu một thao tác cố dùng database khác trong transaction hiện tại.

Không thay đổi tenant context giữa một transaction. Một service method không nên đọc entity từ database tenant_alpha rồi ghi entity đó vào tenant_beta chỉ bằng cách thay đổi tenant context trước lệnh save.

Một request tenant-specific nên có tenant identity bất biến từ lúc xác thực đến khi kết thúc nghiệp vụ. Nếu một tác vụ quản trị cần thao tác nhiều tenant, hãy tách thành các đơn vị công việc rõ ràng, mỗi đơn vị dùng một transaction/database tương ứng.

Entity được tải từ database này không nên được giữ lại rồi tái sử dụng trong một thao tác persistence ở database khác. Hai database có thể chứa node cùng label và cùng business ID nhưng chúng là hai graph khác nhau.

## 12. Chọn database tường minh với Neo4jClient

Neo4jClient cho phép chỉ định database trực tiếp trên query:

~~~java
var result = neo4jClient
    .query("MATCH (person:Person) RETURN person")
    .in(databaseName)
    .fetch()
    .all();
~~~

Đây là lựa chọn cho một thao tác có database đích đã được xác định rõ. databaseName vẫn phải được lấy từ registry/authorization phía server, không lấy trực tiếp từ input tùy ý.

Nếu query chạy trong Spring-managed transaction, database được chỉ định phải khớp database mà transaction manager đã chọn. Không dùng .in(...) để chuyển database giữa chừng trong cùng transaction. Với các truy vấn thuộc tenant hiện tại, dynamic provider thường giúp repository, template và client dùng cùng quy tắc định tuyến.

Nếu dùng Neo4j Java Driver trực tiếp, session không tự động biết tenant mapping của SDN. Ứng dụng phải chọn database rõ ràng khi tạo session, đồng thời tự xử lý transaction và resource lifecycle phù hợp.

## 13. Giới hạn transaction khi dùng nhiều database

Một transaction Neo4j thuộc về một database. Không thể dùng một transaction thông thường để cập nhật nguyên tử hai standard database khác nhau.

Ví dụ, nếu chuyển dữ liệu từ tenant_alpha sang tenant_beta, không thể giả định một method @Transactional duy nhất sẽ commit hoặc rollback cả hai database như một graph duy nhất.

Các cách xử lý thường gặp:

- Chia thao tác thành hai transaction độc lập và thiết kế trạng thái trung gian.
- Dùng saga hoặc workflow có bước bù trừ nếu một phía thất bại.
- Ghi outbox/event trong database nguồn rồi xử lý database đích theo cơ chế retry.
- Nếu dữ liệu cần truy vấn và cập nhật nguyên tử thường xuyên, xem lại liệu chúng có nên nằm trong cùng database hoặc cùng mô hình tenant key hay không.

Đừng thiết kế một nghiệp vụ thường xuyên cần transaction xuyên tenant rồi mới phát hiện database-per-tenant không đáp ứng được ranh giới nguyên tử đó.

## 14. Provisioning, migration và vòng đời tenant database

SDN không tự tạo hoặc xóa database khi tenant được đăng ký. Một quy trình provisioning cần có bước quản trị database và bước chuẩn bị schema.

Ví dụ lệnh quản trị tạo database:

~~~cypher
CREATE DATABASE tenant_alpha IF NOT EXISTS
~~~

Lệnh này là lệnh quản trị DBMS và cần quyền phù hợp; không phải repository query thông thường. Việc tạo database cần được thực hiện bởi provisioning service hoặc migration/operations pipeline có kiểm soát.

Một vòng đời tenant có thể gồm:

1. Tạo tenant record trong hệ thống quản trị.
2. Cấp database name từ registry nội bộ.
3. Tạo database bằng tài khoản có quyền quản trị.
4. Chạy schema migration để tạo constraint, index và dữ liệu khởi tạo.
5. Xác minh database online và schema ở đúng version.
6. Đánh dấu tenant sẵn sàng để nhận request.
7. Khi ngừng tenant, khóa truy cập, backup/export theo chính sách rồi mới xóa database nếu được phép.

Với database-per-tenant, migration phải chạy cho tất cả database đang hoạt động. Theo dõi schema version từng tenant để phát hiện tenant bị bỏ sót hoặc migration thất bại giữa chừng.

Với shared database, schema migration chạy một lần cho graph chung, nhưng thay đổi property hoặc tenant data có thể cần backfill trên toàn bộ tenant. Cần đo quy mô dữ liệu và lập kế hoạch migration theo batch.

## 15. Backup, restore và vận hành

Database-per-tenant giúp chọn một database làm đơn vị backup/restore hoặc export. Điều này hữu ích khi tenant yêu cầu khôi phục riêng, nhưng vận hành phải theo dõi nhiều database và xác minh từng database có backup hợp lệ.

Shared database thường đơn giản hơn ở cấp DBMS, nhưng phục hồi một tenant riêng khó hơn vì dữ liệu nằm chung graph. Có thể cần export theo tenant key, phục hồi sang database tạm rồi trích xuất graph, hoặc dùng quy trình application-level restore đã được kiểm thử.

Theo dõi các chỉ số:

- Số database đang hoạt động và giới hạn theo edition/cấu hình.
- Trạng thái online/offline và schema version của từng tenant database.
- Dung lượng, transaction rate, query latency và lỗi theo tenant.
- Tỷ lệ query shared database thiếu tenant predicate qua review/test hoặc instrumentation.
- Thời gian provisioning, migration, backup và restore.
- Tenant có workload lớn gây noisy neighbor.

Đối với shared database, log và metric cần gắn tenant ID đã được làm sạch để tìm tenant gây tải cao. Không ghi dữ liệu cá nhân hoặc toàn bộ graph payload vào log chỉ để theo dõi tenant.

## 16. Hybrid model: tenant lớn có database riêng

Một hệ thống có thể dùng shared database cho phần lớn tenant nhỏ và cấp database riêng cho tenant lớn hoặc có yêu cầu cô lập cao.

Ví dụ:

~~~text
Tenant registry
  +-- alpha -> shared_tenants
  +-- beta  -> shared_tenants
  +-- gamma -> tenant_gamma
  +-- delta -> tenant_delta
~~~

Ứng dụng vẫn dùng một TenantDatabaseRegistry để ánh xạ tenant sang database. Tuy nhiên, truy vấn và schema cần tương thích với cả hai chế độ. Với tenant trong shared database, mọi query cần tenantId; với tenant database riêng, database đã là partition nhưng entity mapping có thể vẫn dùng cùng model.

Hybrid giúp tách tenant lớn mà không cần tạo database riêng cho tất cả. Đổi lại, migration, backup, routing và kiểm thử phải hiểu cả hai chế độ. Chỉ chọn hybrid nếu có quy tắc rõ ràng để phân loại tenant và quy trình chuyển tenant từ shared sang dedicated.

## 17. Chuyển tenant giữa hai mô hình

Chuyển một tenant từ shared database sang database riêng cần giữ tính nhất quán trong thời gian cutover.

Một quy trình tổng quát:

1. Tạo database đích và chạy schema migration.
2. Trích xuất toàn bộ node, relationship và property thuộc tenant từ shared graph.
3. Import vào database đích, bảo toàn ID và cấu trúc relationship cần thiết.
4. Đối chiếu số lượng node/relationship, constraint và các truy vấn quan trọng.
5. Tạm dừng hoặc đồng bộ write trong thời điểm cutover để không mất thay đổi phát sinh.
6. Cập nhật tenant registry để request mới được định tuyến sang database đích.
7. Xác minh đọc/ghi trên database mới và theo dõi lỗi.
8. Chỉ xóa dữ liệu tenant khỏi shared database sau khi hoàn tất đối soát và thời hạn rollback vận hành.

Nếu tenant được chuyển theo chiều ngược lại, cần loại bỏ xung đột khóa bằng tenantId và kiểm tra relationship không nối sang dữ liệu tenant khác. Không chỉ copy node rồi bỏ qua các edge; graph có thể mất ý nghĩa nếu relationship không được chuyển đúng.

## 18. Ma trận quyết định

| Yêu cầu chính | Hướng thường phù hợp |
| --- | --- |
| Cô lập database, backup/restore riêng | Database-per-tenant |
| Nhiều tenant nhỏ, schema giống nhau | Shared database + tenant key |
| Một số tenant lớn, số còn lại nhỏ | Hybrid |
| Nghiệp vụ cần transaction xuyên nhiều tenant thường xuyên | Xem xét shared database hoặc thay đổi ranh giới nghiệp vụ |
| Tenant cần schema thay đổi độc lập | Database-per-tenant, nếu chấp nhận chi phí migration |
| Muốn giảm số database và công việc provisioning | Shared database |
| Yêu cầu cô lập hạ tầng rất cao | Cân nhắc DBMS/cluster riêng cho tenant đặc biệt |

Với dữ liệu nhạy cảm hoặc yêu cầu pháp lý nghiêm ngặt, có thể cần database hoặc cluster riêng cùng credential và quyền truy cập riêng. Một database riêng trong cùng DBMS vẫn dùng chung hạ tầng server/cluster.

## 19. Kiểm thử tenant isolation

Dù chọn mô hình nào, tenant isolation cần được kiểm thử qua đường truy cập thực tế.

Với database-per-tenant:

1. Tạo hai database test cho hai tenant.
2. Ghi cùng business ID vào cả hai database.
3. Xác thực request tenant alpha chỉ đọc/ghi database alpha.
4. Xác thực tenant beta không thể đọc hoặc sửa graph của alpha.
5. Kiểm tra provider từ chối tenant không có mapping.
6. Kiểm tra mọi thao tác trong cùng transaction dùng một database nhất quán.
7. Kiểm tra custom Neo4jClient query và thao tác Driver không vô tình dùng default database.

Với shared database:

1. Tạo node và relationship cho hai tenant có cùng business ID.
2. Xác nhận repository query luôn giới hạn tenantId.
3. Xác nhận traversal không trả node hoặc relationship thuộc tenant khác.
4. Kiểm tra create/update/delete và MERGE đều dùng tenant key.
5. Thử tenantId giả mạo trong request và xác nhận server không chấp nhận.
6. Kiểm tra custom Cypher, Cypher-DSL và Neo4jClient đều tuân thủ tenant scoping.

Integration test cần chạy với Neo4j thật hoặc môi trường tương thích. Unit test mock repository không thể chứng minh Cypher thực tế đã lọc đúng tenant.

## 20. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Dùng tenantId từ request làm database name | Client có thể yêu cầu database ngoài phạm vi được phép | Dùng registry server-side và authorization |
| Không có tenant context nhưng fallback default DB | Dữ liệu có thể bị đọc/ghi nhầm database | Fail closed với request tenant-specific |
| Thay tenant giữa transaction | Entity và query có thể trỏ tới database khác nhau | Giữ tenant identity bất biến trong một transaction |
| Quên tenant predicate trong một custom query | Có thể rò rỉ dữ liệu giữa tenant | Review mọi query và test isolation |
| MERGE chỉ theo business ID trong shared DB | Có thể ghép node của tenant khác | MERGE theo tenantId và business key |
| Cho rằng SDN tự tạo database | Tenant mới không có database hoặc schema | Provisioning và migration riêng |
| Cho rằng transaction bao phủ nhiều database | Một phần nghiệp vụ có thể commit độc lập | Thiết kế saga/outbox hoặc thay đổi data boundary |
| Dùng ThreadLocal trong reactive provider | Mất tenant context khi đổi thread | Dùng Reactor Context/reactive security |
| Không migrate mọi tenant database | Tenant có schema version khác nhau | Theo dõi migration status theo tenant |

## 21. Quy trình chọn mô hình cho hệ thống

1. Xác định số lượng tenant hiện tại và dự kiến trong vài năm.
2. Ước lượng kích thước graph, read/write rate và độ lệch workload giữa tenant.
3. Xác định yêu cầu isolation, quyền truy cập, backup, restore và lưu trữ dữ liệu.
4. Kiểm tra edition, giới hạn database và topology Neo4j có thể triển khai.
5. Xác định nghiệp vụ có cần transaction hoặc truy vấn xuyên tenant không.
6. Chọn database-per-tenant, shared database hoặc hybrid.
7. Thiết kế tenant registry và tenant context từ danh tính đã xác thực.
8. Cấu hình DatabaseSelectionProvider hoặc ReactiveDatabaseSelectionProvider nếu định tuyến database động.
9. Nếu dùng shared database, áp dụng tenantId trên node/relationship và tenant predicate cho mọi query.
10. Thiết kế provisioning, schema migration, backup, restore và offboarding.
11. Kiểm thử isolation, transaction boundary và các đường truy vấn tùy chỉnh.
12. Theo dõi workload để quyết định khi nào cần tách tenant lớn hoặc chuyển mô hình.

## 22. Lưu ý về edition và giới hạn database

Khả năng quản lý nhiều standard database phụ thuộc edition và phiên bản Neo4j. Theo Operations Manual hiện hành, Community Edition hỗ trợ đúng một standard database; Enterprise Edition hỗ trợ nhiều standard database và chịu giới hạn cấu hình như dbms.max_databases. Hãy xác nhận điều kiện này với phiên bản và hình thức triển khai thực tế trước khi chọn database-per-tenant.

Neo4j hỗ trợ quản trị nhiều database từ phiên bản 4.0, nhưng giới hạn, cú pháp và tính năng quản trị thay đổi theo phiên bản. SDN hỗ trợ chọn database; nó không tự tạo database, không tự provision tenant và không thay thế cơ chế authorization của ứng dụng.

## 23. Bài tập tự kiểm tra

1. Database-per-tenant khác shared database với tenantId ở ranh giới cô lập nào?
2. Vì sao tenant key cần xuất hiện trên node và relationship trong graph dùng chung?
3. Tại sao uniqueness constraint nên kết hợp tenantId với business ID?
4. DatabaseSelectionProvider được SDN hỏi vào thời điểm nào?
5. Vì sao không nên trả DatabaseSelection.undecided() khi request tenant-specific thiếu tenant context?
6. ReactiveDatabaseSelectionProvider khác provider imperative ở kiểu trả về và cách lấy tenant context như thế nào?
7. Vì sao phải dùng cùng provider instance cho Neo4jClient và Neo4jTransactionManager khi tự cấu hình?
8. Một transaction Neo4j có thể cập nhật hai standard database khác nhau không?
9. Vì sao SDN không tự tạo database hoặc schema khi tenant mới được đăng ký?
10. Khi nào hybrid model có lợi và chi phí vận hành của nó là gì?

Khi hoàn thành bài học, bạn cần chọn được ranh giới tenant phù hợp, thiết kế tenant key hoặc database routing an toàn, hiểu giới hạn transaction và chuẩn bị được provisioning/migration/backup cho từng mô hình. Đây là nền tảng để triển khai multi-tenancy trong ứng dụng Spring Data Neo4j mà không nhầm lẫn giữa phân vùng dữ liệu, cô lập database và authorization.

## Tài liệu tham khảo

- [Spring Data Neo4j – FAQ: Multiple databases](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
- [Spring Data Neo4j – DatabaseSelectionProvider API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/DatabaseSelectionProvider.html)
- [Spring Data Neo4j – ReactiveDatabaseSelectionProvider API](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/ReactiveDatabaseSelectionProvider.html)
- [Spring Data Neo4j – Neo4jClient and database selection](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Neo4j Operations Manual – Database administration](https://neo4j.com/docs/operations-manual/current/database-administration/)
- [Neo4j Operations Manual – Configuration settings](https://neo4j.com/docs/operations-manual/current/configuration/configuration-settings/)

