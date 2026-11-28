# Health check và quyền truy cập khi database mặc định khác database ứng dụng

Một ứng dụng Spring Data Neo4j (SDN) có thể sử dụng database `appdb` trong khi tài khoản Neo4j có database mặc định là `neo4j`. Đây là cấu hình hợp lệ, nhưng có thể tạo ra khác biệt giữa health check và thao tác nghiệp vụ: một health check mở session mà không chỉ định database có thể kiểm tra database mặc định, trong khi repository của ứng dụng lại truy cập `appdb`.

Khi đó, health endpoint có thể báo DOWN dù ứng dụng vẫn đọc ghi được database đích; hoặc health check báo UP vì database mặc định truy cập được trong khi database ứng dụng thiếu quyền hay đang không khả dụng. Để chẩn đoán chính xác, cần xác định database mà từng session đang sử dụng, kiểm tra quyền trên đúng database và thiết kế readiness probe theo dependency thực tế của ứng dụng.

## 1. Database mặc định và database ứng dụng là hai khái niệm riêng

Neo4j có thể chứa nhiều database trong cùng một DBMS. Mỗi user có database mặc định được cấu hình ở phía Neo4j; driver có thể mở session tới database khác nếu session chỉ định rõ database và user có quyền truy cập.

Trong ứng dụng Spring Boot, database SDN sử dụng được cấu hình bằng `spring.data.neo4j.database`:

~~~yaml
spring:
  neo4j:
    uri: neo4j://neo4j-router.internal:7687
    authentication:
      username: app_user
      password: ${NEO4J_PASSWORD}
  data:
    neo4j:
      database: appdb
~~~

`spring.data.neo4j.database` cho biết database mà các thành phần Spring Data Neo4j được cấu hình sẽ chọn khi tạo session. Giá trị này không thay đổi database mặc định của user ở Neo4j. Một công cụ quản trị, health check hoặc đoạn code tự mở Driver session mà không chỉ định database vẫn có thể sử dụng database mặc định của user.

| Khái niệm | Được quyết định bởi | Ảnh hưởng |
|---|---|---|
| Database mặc định của user | Cấu hình user trong Neo4j | Database được chọn khi session không chỉ định database |
| Database của ứng dụng SDN | `spring.data.neo4j.database` hoặc database selection configuration | Database mà repository/template SDN nhắm tới |
| Database của một Driver session | `SessionConfig.withDatabase(...)` | Database cụ thể cho session đó |
| Database trong Cypher `USE` | Câu lệnh Cypher và quyền tương ứng | Chuyển ngữ cảnh query trong phạm vi được phép |

Không suy ra database ứng dụng chỉ từ database mặc định của tài khoản. Hãy cấu hình và kiểm tra database đích một cách tường minh.

## 2. Vì sao health check có thể kiểm tra nhầm database?

Spring Boot Actuator tự cấu hình Neo4j health contributor khi các dependency và điều kiện auto-configuration phù hợp. Theo FAQ hiện hành của Spring Data Neo4j, health indicator Neo4j mặc định của Spring Boot nhắm tới database mặc định của user. Driver được cấu hình độc lập với SDN nên health indicator mặc định không tự nhận database selection mà SDN đang dùng.

Nếu health check chỉ gọi `driver.session()` mà không truyền `SessionConfig` có database, Neo4j sẽ chọn database mặc định của user. Điều này khác với repository SDN đang dùng `spring.data.neo4j.database`.

Ví dụ:

- User `app_user` có default database là `neo4j`.
- Ứng dụng được cấu hình `spring.data.neo4j.database: appdb`.
- `appdb` đang hoạt động và `app_user` có quyền truy cập.
- Database `neo4j` không được cấp quyền cho `app_user`.
- Repository truy cập `appdb` thành công, nhưng một health check mở session mặc định có thể thất bại.

Chiều ngược lại cũng có thể xảy ra: health check truy cập `neo4j` thành công nhưng `appdb` bị offline, chưa được cấp quyền hoặc thiếu quyền đọc cần thiết. Vì vậy, một phép kiểm tra kết nối chung chưa chắc phản ánh sức khỏe của dependency mà nghiệp vụ thực sự sử dụng.

Khi database mặc định khác database SDN đang chọn, health check mặc định có thể thất bại nếu user không có ít nhất quyền ACCESS trên database mặc định, dù repository vẫn truy cập database ứng dụng được. Hãy dùng custom health contributor có nhận `DatabaseSelectionProvider` để probe đúng database SDN đang chọn. Tham khảo [Spring Data Neo4j FAQ – The Spring Boot Neo4j health indicator targets the default database](https://docs.spring.io/spring-data/neo4j/reference/faq.html).

## 3. Kiểm tra đúng database bằng Neo4j Java Driver

Neo4j Java Driver cho phép chọn database cho từng session bằng `SessionConfig.Builder.withDatabase(...)`. Một probe đơn giản có thể mở session tới đúng database ứng dụng và chạy câu lệnh nhẹ:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;

public class Neo4jDatabaseProbe {

    private final Driver driver;
    private final DatabaseSelectionProvider databaseSelectionProvider;

    public Neo4jDatabaseProbe(
            Driver driver, DatabaseSelectionProvider databaseSelectionProvider) {
        this.driver = driver;
        this.databaseSelectionProvider = databaseSelectionProvider;
    }

    public void check() {
        var selection = databaseSelectionProvider.getDatabaseSelection();
        var sessionConfig = selection == null
                || selection == DatabaseSelection.undecided()
            ? SessionConfig.defaultConfig()
            : SessionConfig.builder()
                .withDatabase(selection.getValue())
                .build();

        try (var session = driver.session(sessionConfig)) {
            session.run("RETURN 1 AS probe").single();
        }
    }
}
~~~

Lệnh `RETURN 1` xác nhận driver có thể mở session và thực thi query trên database được chọn. Nó không kiểm tra mọi quyền đọc/ghi của ứng dụng, cũng không chứng minh các label, property hoặc constraint cần cho nghiệp vụ đều có sẵn.

Trong cấu hình thực tế, lấy database selection từ cùng provider mà ứng dụng dùng cho SDN. Cách này cũng hoạt động với cấu hình database động. Nếu probe độc lập không nằm trong Spring context, có thể truyền tên database tường minh và dùng `withDatabase(database)`.

## 4. Tạo health indicator kiểm tra database ứng dụng

Nếu health indicator mặc định không kiểm tra đúng database đích hoặc không thể tùy chỉnh theo nhu cầu, có thể tạo `HealthIndicator` riêng. Ví dụ imperative:

~~~java
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.data.neo4j.core.DatabaseSelection;
import org.springframework.data.neo4j.core.DatabaseSelectionProvider;
import org.springframework.stereotype.Component;

@Component("applicationNeo4j")
public class ApplicationNeo4jHealthIndicator implements HealthIndicator {

    private final Driver driver;
    private final DatabaseSelectionProvider databaseSelectionProvider;

    public ApplicationNeo4jHealthIndicator(
            Driver driver,
            DatabaseSelectionProvider databaseSelectionProvider) {
        this.driver = driver;
        this.databaseSelectionProvider = databaseSelectionProvider;
    }

    @Override
    public Health health() {
        var selection = databaseSelectionProvider.getDatabaseSelection();
        var sessionConfig = selection == null
                || selection == DatabaseSelection.undecided()
            ? SessionConfig.defaultConfig()
            : SessionConfig.builder()
                .withDatabase(selection.getValue())
                .build();

        String database = selection == null
                || selection == DatabaseSelection.undecided()
            ? "default"
            : selection.getValue();

        try (var session = driver.session(sessionConfig)) {
            int probe = session.run("RETURN 1 AS probe")
                .single()
                .get("probe")
                .asInt();

            return Health.up()
                .withDetail("database", database)
                .withDetail("probe", probe)
                .build();
        } catch (Exception exception) {
            return Health.down(exception)
                .withDetail("database", database)
                .build();
        }
    }
}
~~~

Bean trên dùng đúng database selection provider của SDN. Với cấu hình tĩnh, provider lấy giá trị từ `spring.data.neo4j.database`; với cấu hình động, provider có thể chọn database theo request hoặc tenant. Nếu provider trả `DatabaseSelection.undecided()`, session dùng database mặc định của user.

Tên health contributor `applicationNeo4j` là ID của bean trong ví dụ. Khi cấu hình health group, dùng đúng ID mà Actuator hiển thị. Nếu vẫn giữ health indicator Neo4j mặc định, có thể expose cả hai contributor để phân biệt kiểm tra kết nối chung và kiểm tra database ứng dụng.

Với ứng dụng reactive, hãy triển khai `ReactiveHealthIndicator` và dùng reactive Driver/session API để trả `Mono<Health>`. Không gọi `block()` trên reactive health check để tái sử dụng implementation imperative; việc đó có thể chặn event-loop thread.

## 5. Health check cần kiểm tra điều gì?

Một health check nên có phạm vi rõ ràng:

| Loại probe | Điều xác nhận | Không chứng minh |
|---|---|---|
| Driver connectivity | Có thể kết nối tới Neo4j endpoint | Database ứng dụng có quyền truy cập |
| Database availability | Session tới database đích có thể thực thi query nhẹ | User có đủ quyền cho mọi query nghiệp vụ |
| Read permission | Có thể chạy một truy vấn đọc đại diện trên graph đích | Các quyền ghi đã được cấp |
| Schema readiness | Index, constraint hoặc dữ liệu cần thiết đã sẵn sàng | Mọi use case đều hoạt động |
| Write permission | Có thể thực hiện thao tác ghi đại diện | Nên kiểm tra liên tục bằng cách ghi dữ liệu thật |

Không nên thực hiện một transaction ghi dữ liệu thật trong health endpoint. Health endpoint có thể được gọi thường xuyên bởi orchestrator; ghi liên tục sẽ tạo side effect và làm tăng tải. Nếu cần kiểm tra quyền ghi, hãy xác minh bằng migration/deployment preflight hoặc một kiểm thử riêng dùng dữ liệu probe có thể rollback an toàn.

Một probe `RETURN 1` phù hợp để xác nhận database được chọn có thể nhận query. Nếu readiness cần xác nhận quyền đọc của ứng dụng, có thể chạy một query nhẹ trên label hoặc dữ liệu health riêng mà role được phép truy cập. Không dùng query quét toàn bộ graph trong health endpoint.

## 6. Cấp quyền truy cập trên đúng database

Neo4j RBAC phân biệt quyền truy cập database với quyền thao tác trên graph. Một user cần được phép truy cập database đích và có các privilege cần thiết cho query.

Ví dụ, tạo role ứng dụng và cấp quyền truy cập database:

~~~cypher
CREATE ROLE app_role IF NOT EXISTS;
GRANT ACCESS ON DATABASE appdb TO app_role;
~~~

Nếu ứng dụng chỉ đọc node và relationship trên graph, có thể cấp quyền đọc phù hợp:

~~~cypher
GRANT MATCH {*} ON GRAPH appdb NODE * TO app_role;
GRANT MATCH {*} ON GRAPH appdb RELATIONSHIP * TO app_role;
~~~

Nếu ứng dụng cần ghi, cấp thêm đúng các privilege cần thiết theo label, relationship type và property mà ứng dụng quản lý. Ví dụ:

~~~cypher
GRANT CREATE ON GRAPH appdb NODE Person TO app_role;
GRANT CREATE ON GRAPH appdb RELATIONSHIP * TO app_role;
GRANT SET PROPERTY {*} ON GRAPH appdb NODE Person TO app_role;
GRANT SET PROPERTY {*} ON GRAPH appdb RELATIONSHIP * TO app_role;
~~~

Đây là ví dụ minh họa cho Neo4j 5 privilege model; cú pháp và các privilege khả dụng cần đối chiếu với phiên bản Neo4j đang triển khai. Các lệnh quản trị `CREATE ROLE` và `GRANT` được thực thi trong database `system` bằng tài khoản có quyền quản trị phù hợp. Hãy giới hạn quyền theo graph, label, relationship type và property cần thiết thay vì cấp quyền quản trị hoặc quyền toàn bộ DBMS cho tài khoản runtime.

Sau khi role được cấp quyền, gán role cho user ứng dụng bằng tài khoản quản trị:

~~~cypher
GRANT ROLE app_role TO app_user;
~~~

Không dùng user quản trị Neo4j cho ứng dụng chỉ vì health check đang thất bại. Trước hết, xác định query nào cần quyền gì và cấp privilege tối thiểu trên đúng database.

## 7. Phân biệt quyền ACCESS, MATCH và quyền ghi

Các nhóm quyền thường cần được xem xét riêng:

- `ACCESS ON DATABASE`: cho phép user truy cập database.
- `MATCH`: cho phép tìm pattern, duyệt và đọc các property được chỉ định trên node/relationship trong phạm vi privilege.
- `TRAVERSE`: cho phép duyệt qua node/relationship trong phạm vi được cấp.
- `READ`: cho phép đọc property được chỉ định.
- `CREATE`: cho phép tạo node hoặc relationship trong phạm vi được cấp.
- `SET PROPERTY`: cho phép đặt hoặc cập nhật property.
- `DELETE`: cho phép xóa node/relationship theo phạm vi privilege.

Một query `RETURN 1` không cần đọc graph entity, nên có thể thành công trong khi query `MATCH (p:Person) RETURN p.name` bị từ chối do thiếu quyền graph. Ngược lại, user có thể có quyền đọc graph nhưng không có quyền `CREATE` hoặc `SET PROPERTY`, khiến thao tác ghi của repository thất bại.

Vì vậy, hãy tách health probe cơ bản khỏi kiểm thử quyền theo nghiệp vụ. Một health probe đơn giản không thể đại diện cho toàn bộ privilege mà ứng dụng cần.

## 8. Kiểm tra database, user và privilege khi chẩn đoán

Tài khoản quản trị có thể kiểm tra database đang tồn tại và trạng thái:

~~~cypher
SHOW DATABASES;
~~~

Kiểm tra role của user:

~~~cypher
SHOW USERS;
SHOW ROLES WITH USERS;
~~~

Kiểm tra privilege được cấp cho role:

~~~cypher
SHOW ROLE app_role PRIVILEGES AS COMMANDS;
~~~

Các lệnh quản trị như `SHOW DATABASES`, `SHOW USERS` và `SHOW ROLE ... PRIVILEGES` có thể yêu cầu privilege quản trị tương ứng. Không cấp những quyền này cho user runtime chỉ để health check chạy được. Hãy thực hiện bằng tài khoản vận hành có quyền phù hợp.

Khi kiểm tra trực tiếp database ứng dụng, hãy dùng session chỉ định `appdb` hoặc Cypher `USE appdb` nếu phiên bản và ngữ cảnh query hỗ trợ. Cách chỉ định database ở `SessionConfig` thường rõ ràng hơn cho một health probe chuyên biệt.

## 9. Tách quyền runtime và quyền migration

Ứng dụng runtime và công cụ migration có nhu cầu quyền khác nhau:

| Tài khoản | Mục đích | Quyền thường cần |
|---|---|---|
| Runtime user | Đọc/ghi graph khi xử lý request | ACCESS và quyền MATCH/CREATE/SET PROPERTY/DELETE đúng phạm vi nghiệp vụ |
| Migration user | Tạo constraint, index, thay đổi schema hoặc backfill | Quyền quản trị database/schema và quyền dữ liệu cần cho migration |
| Monitoring user | Kiểm tra kết nối/database hoặc đọc số liệu quan sát | ACCESS và quyền đọc tối thiểu cần cho probe |
| Admin user | Quản lý user, role, database và privilege | Quyền quản trị; chỉ dùng cho vận hành có kiểm soát |

Không cấp quyền tạo index, quản lý user hoặc thay đổi database cho runtime user nếu ứng dụng không thực hiện các công việc đó. Migration job nên dùng credential riêng và chỉ chạy trong pipeline triển khai được kiểm soát.

Nếu dùng cùng một tài khoản cho runtime và migration, sự cố lộ credential ứng dụng có thể cho phép thay đổi schema hoặc quản lý dữ liệu vượt quá nhu cầu runtime.

## 10. Readiness và liveness không có cùng mục tiêu

Khi Neo4j là dependency bắt buộc để phục vụ request, trạng thái database nên ảnh hưởng đến readiness: instance chỉ nhận traffic khi có thể truy cập database ứng dụng. Tuy nhiên, một lỗi Neo4j tạm thời không nhất thiết có nghĩa tiến trình ứng dụng cần bị restart.

- **Liveness** trả lời tiến trình có còn hoạt động hay không. Không nên gắn mọi lỗi database vào liveness vì orchestrator có thể restart liên tục trong khi database vẫn đang phục hồi.
- **Readiness** trả lời instance có đủ điều kiện nhận request hay không. Có thể đưa health contributor kiểm tra `appdb` vào readiness group.
- **Startup probe** dành cho giai đoạn ứng dụng khởi động chậm và chưa sẵn sàng nhận traffic.

Ví dụ cấu hình Actuator health probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      show-details: when_authorized
      group:
        readiness:
          include: readinessState,applicationNeo4j
~~~

`applicationNeo4j` là tên bean trong ví dụ health indicator ở phần trước. Nếu dùng contributor khác, thay bằng ID thực tế. Hãy xác nhận endpoint và group bằng cấu hình Actuator của đúng phiên bản Spring Boot.

Nếu ứng dụng có thể phục vụ một số chức năng khi Neo4j tạm thời không khả dụng, readiness policy có thể cần phân loại dependency bắt buộc và tùy chọn thay vì đánh dấu toàn bộ instance DOWN.

## 11. Bảo vệ thông tin health endpoint

Health endpoint có thể tiết lộ tên database, lỗi xác thực, hostname, trạng thái cụm hoặc thông tin hạ tầng. Không expose chi tiết này công khai nếu không cần thiết.

Một số nguyên tắc:

- Chỉ expose health endpoint cần thiết cho load balancer hoặc orchestrator.
- Đặt `show-details` thành `when_authorized` hoặc `never` tùy chính sách.
- Không trả password, URI chứa credential hoặc query nhạy cảm trong health details.
- Dùng security rule để giới hạn ai có thể xem chi tiết.
- Tách probe nội bộ khỏi endpoint quan sát công khai nếu môi trường yêu cầu.

Ví dụ `Health.down(exception)` có thể chứa thông tin lỗi; hãy kiểm tra cách Actuator serialize chi tiết theo cấu hình hiện tại và tránh đưa thông tin xác thực vào exception message.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Health check mở session không chỉ định database | Kiểm tra database mặc định của user thay vì database SDN dùng | Chỉ định `SessionConfig.withDatabase(appdb)` |
| Nghĩ `spring.data.neo4j.database` thay đổi default database của user | Driver session độc lập vẫn có thể chọn database mặc định khác | Phân biệt cấu hình SDN và cấu hình user trong Neo4j |
| Health check `RETURN 1` báo UP nên cho rằng ứng dụng đủ quyền | Query nghiệp vụ có thể vẫn thiếu MATCH/CREATE/SET PROPERTY | Kiểm tra quyền trên đúng database bằng query đại diện hoặc preflight |
| Cấp quyền quản trị để sửa health DOWN | Runtime user có quyền vượt quá nhu cầu | Cấp ACCESS và privilege tối thiểu trên graph đích |
| Dùng database mặc định `neo4j` làm fallback tùy tiện | Probe có thể kiểm tra sai database | Lấy database từ cấu hình triển khai rõ ràng |
| Đưa database vào liveness | Orchestrator restart loop khi DB tạm thời lỗi | Đưa dependency vào readiness nếu phù hợp |
| Dùng cùng credential cho runtime và migration | Tăng phạm vi ảnh hưởng khi credential bị lộ | Tách tài khoản và quyền theo mục đích |
| Health endpoint chạy query nặng hoặc ghi dữ liệu | Tăng tải và tạo side effect khi probe lặp lại | Dùng query nhẹ, read-only và timeout hữu hạn |
| Không kiểm tra health indicator mặc định theo phiên bản | Hiểu nhầm database mà contributor đang kiểm tra | Kiểm tra implementation và quan sát session database thực tế |

## 13. Quy trình chẩn đoán khi health và repository cho kết quả khác nhau

1. Xác nhận giá trị `spring.data.neo4j.database` hoặc database selection provider trong môi trường đang chạy.
2. Xác định database mặc định của user ứng dụng trong Neo4j.
3. Kiểm tra health contributor đang dùng và database mà session của nó chọn.
4. Mở session với `SessionConfig.withDatabase(appdb)` để probe đúng database ứng dụng.
5. Dùng tài khoản quản trị kiểm tra `SHOW DATABASES` và trạng thái database.
6. Kiểm tra role của runtime user và privilege `ACCESS` trên database đích.
7. Kiểm tra quyền graph cần cho query đọc/ghi của repository.
8. Tách quyền runtime, monitoring và migration nếu chúng có nhu cầu khác nhau.
9. Đưa probe database ứng dụng vào readiness nếu database là dependency bắt buộc.
10. Giới hạn health details và xác nhận endpoint không tiết lộ credential hoặc thông tin nội bộ.

## 14. Tự kiểm tra

1. Database mặc định của user khác gì database được cấu hình bằng `spring.data.neo4j.database`?
2. Vì sao health check có thể báo DOWN trong khi repository vẫn hoạt động?
3. `SessionConfig.withDatabase(...)` giải quyết vấn đề chọn database như thế nào?
4. Một probe `RETURN 1` xác nhận điều gì và không xác nhận điều gì?
5. `ACCESS ON DATABASE` khác quyền `MATCH` hoặc `CREATE` trên graph ra sao?
6. Vì sao không nên cấp quyền quản trị cho runtime user để làm health check thành công?
7. Khi nào nên đưa Neo4j health contributor vào readiness thay vì liveness?
8. Vì sao nên tách runtime user và migration user?
9. Tại sao cần kiểm tra health indicator mặc định theo phiên bản Spring Boot?

Khi database mặc định của user khác database ứng dụng, health check phải kiểm tra đúng dependency mà repository sử dụng. Hãy chỉ định database tường minh cho probe, cấp `ACCESS` và graph privileges tối thiểu trên database đó, đồng thời phân biệt readiness với liveness. Một health check kết nối thành công chỉ là bước đầu; quyền đọc/ghi và schema cần thiết phải được xác minh riêng bằng các kiểm tra phù hợp.

Tài liệu tham khảo:

- [Spring Boot Actuator – Health Information](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Neo4j Java Driver – Sessions and database selection](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Operations Manual – Manage privileges](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-privileges/)
- [Spring Data Neo4j FAQ – Multiple databases and database-aware health checks](https://docs.spring.io/spring-data/neo4j/reference/faq.html)
