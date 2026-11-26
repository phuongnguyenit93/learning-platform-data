# Cô lập database

Trong module **SPRING_MODULITH_APPLICATION_EVENTS**, application events giúp các module Spring Modulith giao tiếp qua sự kiện nghiệp vụ, giảm phụ thuộc trực tiếp và bảo vệ ranh giới nghiệp vụ. Khi kiểm thử module, database là một phần của trạng thái dùng chung: dữ liệu, sequence, transaction, inbox, outbox và Event Publication Registry đều có thể ảnh hưởng đến kết quả của test khác. **Cô lập database** giúp mỗi test hoặc nhóm test có trạng thái dữ liệu xác định, tránh phụ thuộc vào thứ tự chạy và phát hiện đúng hành vi persistence của module.

Một test có thể pass khi chạy riêng nhưng fail khi chạy cùng suite vì dữ liệu còn sót, listener bất đồng bộ chưa xử lý xong hoặc hai test cùng sửa một bản ghi. Ngược lại, test có thể pass với database nhúng nhưng fail trên database production do khác biệt về SQL, constraint, locking hoặc transaction. Cần chọn chiến lược cô lập phù hợp với mục tiêu kiểm thử và ranh giới module.

## 1. Cô lập database trong kiểm thử module là gì?

Trong bài này, cô lập database nghĩa là kiểm soát trạng thái lưu trữ mà test sử dụng để test không đọc hoặc ghi nhầm dữ liệu của test khác. Nó bao gồm:

- Cơ sở dữ liệu hoặc schema được tạo riêng cho test hoặc suite.
- Dữ liệu fixture được khởi tạo có chủ đích và có thể tái tạo.
- Transaction và cleanup không để lại trạng thái ngoài dự kiến.
- Listener bất đồng bộ không tiếp tục ghi vào dữ liệu sau khi test đã kết thúc.
- Các test chạy song song không tranh chấp cùng một bản ghi hoặc cùng thao tác cleanup.
- Migration, sequence, index, constraint và kiểu dữ liệu tương thích với môi trường cần mô phỏng.

Không nên nhầm **cô lập database giữa các test** với **transaction isolation level**. Cô lập giữa các test ngăn test A làm thay đổi dữ liệu mà test B nhìn thấy. Transaction isolation level như READ COMMITTED, REPEATABLE READ hoặc SERIALIZABLE quy định một transaction nhìn thấy thay đổi của transaction khác như thế nào. Hai khái niệm liên quan nhưng giải quyết hai vấn đề khác nhau.

## 2. Vì sao test module cần database riêng?

Giả sử module Order nhận OrderConfirmed, cập nhật read model và ghi nhận eventId vào inbox. Nếu test A tạo order ORD-1 rồi không dọn dữ liệu, test B có thể gặp lỗi unique constraint hoặc đọc phải trạng thái từ lần chạy trước. Nếu listener chạy bất đồng bộ và hoàn tất sau khi test A đã xóa dữ liệu, nó có thể tạo lại bản ghi trong lúc test B đang chạy.

Các nguyên nhân gây nhiễm trạng thái thường gặp:

| Nguồn trạng thái | Rủi ro nếu dùng chung |
| --- | --- |
| Bảng nghiệp vụ | Test đọc nhầm hoặc cập nhật dữ liệu do test khác tạo. |
| Sequence/identity | Giá trị sinh tự động thay đổi theo thứ tự chạy; không nên giả định ID luôn bắt đầu từ một số cố định. |
| Inbox/deduplication | EventId đã được test trước đánh dấu xử lý, khiến test sau bỏ qua event. |
| Outbox | Publisher nền gửi lại message cũ từ test khác. |
| Event Publication Registry | Publication chưa hoàn tất có thể được recovery trong lúc test khác đang chạy. |
| Read model/projection | Listener bất đồng bộ cập nhật dữ liệu sau khi assertion hoặc cleanup đã kết thúc. |
| Database migration | Schema hoặc dữ liệu khởi tạo thay đổi giữa các test. |

Database cô lập làm cho test có thể lặp lại, chạy độc lập và chạy song song với ít phụ thuộc hơn. Nó cũng giúp xác định rõ module đang sở hữu dữ liệu nào và module nào chỉ tương tác qua event hoặc API công khai.

## 3. Các mức độ cô lập

Không phải test nào cũng cần một database container riêng. Có thể chọn một trong các mức sau:

| Chiến lược | Phạm vi chia sẻ | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Database dùng chung, transaction rollback | Các test dùng cùng database; mỗi test mở transaction riêng. | Nhanh, ít cấu hình. | Không cô lập được side effect chạy ở thread/transaction khác; sequence và tác vụ nền có thể còn trạng thái. |
| Database dùng chung, schema riêng | Mỗi test hoặc class có schema riêng. | Tách bảng và migration theo schema. | Cần cấu hình schema/search path; connection pool và tool migration phải dùng đúng schema. |
| Database riêng cho mỗi test class | Mỗi class có database hoặc container riêng. | Cô lập mạnh giữa class, dễ kiểm soát fixture. | Tốn thời gian khởi tạo và tài nguyên. |
| Database riêng cho từng test | Mỗi test có database riêng hoàn toàn. | Cô lập mạnh nhất, dễ chạy song song. | Chi phí tạo database/migration cao. |
| Container dùng chung cho suite, schema/database riêng theo test | Container engine dùng chung nhưng namespace dữ liệu tách biệt. | Cân bằng tốc độ và cô lập. | Cần quản lý vòng đời schema/database và cleanup chính xác. |

Chọn mức nhỏ nhất đáp ứng yêu cầu correctness. Unit test không cần database thật; integration test kiểm tra repository, transaction hoặc event publication nên dùng database tương thích với production khi có thể.

## 4. Cô lập bằng transaction rollback

Spring Test hỗ trợ @Transactional trên test method hoặc test class. Transaction được rollback sau test theo mặc định, giúp dữ liệu đồng bộ được ghi trong transaction đó không tồn tại sau khi test kết thúc:

~~~java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    OrderRepository orders;

    @Test
    void persistsOrderWithinTestTransaction() {
        orders.save(new Order("ORD-TEST-1"));

        assertThat(orders.findByBusinessId("ORD-TEST-1"))
            .isPresent();
    }
}
~~~

Chiến lược này phù hợp với thao tác đồng bộ tham gia cùng transaction test. Nó không phải cơ chế cô lập toàn diện:

- REQUIRES_NEW có thể mở transaction riêng và commit ngoài transaction test.
- Listener @Async hoặc @ApplicationModuleListener chạy trên thread khác, không tham gia transaction test.
- @TransactionalEventListener(AFTER_COMMIT) không chạy khi transaction test bị rollback.
- Dữ liệu ghi qua HTTP, broker hoặc service ngoài database không bị rollback cùng transaction test.
- Sequence/identity có thể tăng dù transaction rollback, tùy database.

Vì vậy, rollback transaction test không bảo đảm mọi side effect đã được dọn. Với test event-driven, cần xác định transaction boundary của publisher và listener, chờ xử lý bất đồng bộ hoàn tất và có cleanup cho dữ liệu nằm ngoài transaction test.

## 5. Cô lập bằng Testcontainers

Testcontainers cung cấp database thật trong container để integration test sử dụng đúng engine gần với production. Ví dụ với PostgreSQL và Spring Boot:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class DatabaseTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
~~~

~~~java
@ApplicationModuleTest
@Import(DatabaseTestConfiguration.class)
class OrderModuleDatabaseTest {

    @Autowired
    OrderRepository orders;

    @Test
    void savesOrderUsingIsolatedPostgresContainer() {
        orders.save(new Order("ORD-TEST-2"));

        assertThat(orders.findByBusinessId("ORD-TEST-2"))
            .isPresent();
    }
}
~~~

Ví dụ minh họa dùng Spring Boot có hỗ trợ @ServiceConnection (Spring Boot 3.1 trở lên), module Testcontainers cho PostgreSQL và Spring Modulith test. @ApplicationModuleTest khởi tạo context theo phạm vi module; database container được cung cấp cho datasource của context. Tên class, entity và repository cần được thay bằng thành phần thực tế của module đang kiểm thử.

Khai báo container như bean do Spring quản lý giúp vòng đời container gắn với ApplicationContext. Điều này hữu ích khi Spring Test cache context giữa các class; tránh trường hợp container static của một class đã dừng trong khi context được cache vẫn giữ connection details trỏ đến container đó.

Nếu phiên bản Spring Boot chưa hỗ trợ @ServiceConnection, có thể dùng @DynamicPropertySource để đăng ký JDBC URL, username và password từ container. Dù dùng cách nào, hãy bảo đảm container còn hoạt động trong toàn bộ thời gian context sử dụng nó.

## 6. Database/schema riêng cho từng test

Nếu test chạy song song hoặc cần dữ liệu hoàn toàn độc lập, có thể tạo database hoặc schema riêng theo test. Một cách phổ biến là dùng một PostgreSQL container cho suite nhưng tạo schema riêng cho từng test class hoặc test case.

Quy trình tổng quát:

1. Sinh tên schema duy nhất, ví dụ test_order_8f31.
2. Tạo schema bằng connection quản trị.
3. Cấu hình datasource hoặc connection pool của test dùng schema đó.
4. Chạy Flyway/Liquibase migration vào schema mới.
5. Tạo fixture, chạy test và chờ listener hoàn tất.
6. Đóng connection pool trước khi drop schema.
7. Xóa schema và dữ liệu liên quan sau test.

Tên schema phải được tạo từ giá trị nội bộ an toàn, không nối trực tiếp dữ liệu người dùng vào SQL identifier. Một số database không hỗ trợ bind parameter cho tên schema/table; khi đó cần validate và quote identifier đúng theo database.

Database riêng từng test class thường dễ triển khai hơn database riêng từng method. Nếu tạo schema theo method, cần bảo đảm tất cả connection trong pool đều dùng đúng schema; nếu không, một số truy vấn có thể vô tình ghi vào schema mặc định.

## 7. Chạy migration trong database test

Database test cần có schema giống ứng dụng thực tế. Nếu production dùng Flyway hoặc Liquibase, nên chạy cùng migration trên database test thay vì tự tạo vài bảng tối giản bằng script riêng.

Điều này giúp phát hiện:

- Migration thiếu hoặc sai thứ tự.
- Kiểu dữ liệu, index và unique constraint không tương thích.
- Foreign key hoặc check constraint bị thiếu.
- Thay đổi schema làm hỏng repository hoặc event inbox/outbox.
- Dữ liệu seed không còn tương thích với schema mới.

Ví dụ cấu hình Flyway:

~~~yaml
spring:
  flyway:
    enabled: true
    locations: classpath:db/migration
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Với database test mới và rỗng, migration chạy khi context khởi tạo. ddl-auto: validate giúp Hibernate kiểm tra mapping với schema đã được tạo. Không nên dùng ddl-auto: create-drop trong mọi integration test nếu production dùng migration; cách đó có thể bỏ qua lỗi migration và khác biệt schema.

Nếu cần seed dữ liệu, dùng fixture hoặc script test có phiên bản và phạm vi rõ ràng. Tránh phụ thuộc vào dữ liệu còn lại từ lần chạy trước hoặc vào thứ tự migration của một module khác không nằm trong phạm vi test.

## 8. Cô lập database trong Spring Modulith module test

@ApplicationModuleTest giúp khởi tạo Spring context theo module được kiểm thử và các dependency được cho phép theo bootstrap mode. Database test nên phục vụ đúng module đó, để test tập trung vào public API, repository và event contract của module.

Một bài test module có thể kiểm tra:

- Module sở hữu dữ liệu và migration của mình.
- Repository chỉ thao tác trên schema test được cấp.
- Event được phát khi transaction module commit.
- Listener cập nhật inbox/read model trong transaction riêng.
- Không truy cập trực tiếp bảng nội bộ của module khác chỉ để dựng fixture.

Nếu test cần dữ liệu từ module khác, ưu tiên dùng public API hoặc event contract được công khai. Nếu cần tích hợp nhiều module trong cùng test, dùng bootstrap mode phù hợp và vẫn giữ quyền sở hữu dữ liệu rõ ràng. Không dùng một database test dùng chung làm lý do để module truy cập bảng nội bộ của nhau.

## 9. Cô lập transaction và listener bất đồng bộ

Với application events, publisher và listener có thể chạy trong các transaction khác nhau. Ví dụ @ApplicationModuleListener xử lý bất đồng bộ sau commit; transaction của listener không phải transaction của test method.

Luồng kiểm thử cần được điều khiển rõ:

~~~mermaid
sequenceDiagram
    participant T as Test
    participant P as Publisher transaction
    participant R as Publication Registry
    participant L as Async listener transaction
    participant D as Test database

    T->>P: Gọi module public API
    P->>D: Ghi dữ liệu nghiệp vụ
    P->>R: Đăng ký publication
    P->>P: Commit
    P-->>L: Giao event sau commit
    L->>D: Cập nhật projection/inbox
    L->>L: Commit
    L-->>R: Đánh dấu publication hoàn tất
    T->>D: Chờ và assert kết quả
~~~

Test cần chờ điều kiện cuối cùng, ví dụ projection xuất hiện hoặc publication được đánh dấu completed, với timeout hữu hạn. Sau khi assertion xong, chờ mọi listener liên quan kết thúc trước khi xóa schema hoặc database.

Không dựa vào rollback của test method để dọn dữ liệu do listener async đã commit. Có thể dùng unique test ID để giới hạn dữ liệu, sau đó cleanup trong transaction riêng sau khi chắc chắn listener đã hoàn tất.

## 10. Cô lập Event Publication Registry, inbox và outbox

Database của event-driven module có thể chứa thêm các bảng vận hành:

| Thành phần | Dữ liệu cần cô lập |
| --- | --- |
| Event Publication Registry | Publication record và trạng thái completed/incomplete của listener. |
| Inbox/deduplication | Event ID đã xử lý và kết quả áp dụng. |
| Outbox | Event chờ gửi đến broker hoặc adapter bên ngoài. |
| Projection/read model | Dữ liệu tổng hợp do listener cập nhật. |
| Saga/process manager | Trạng thái quy trình và các bước đang chờ. |

Nếu các bảng này dùng chung giữa test, một publication incomplete có thể được recovery ngoài ý muốn trong lúc test khác chạy. Một outbox publisher nền có thể gửi event của test cũ. Một eventId trong inbox có thể khiến test sau coi event mới là duplicate.

Ưu tiên database/schema riêng. Nếu dùng chung database, phải gắn dữ liệu test với namespace hoặc ID duy nhất và tắt/kiểm soát background scheduler trong test. Không xóa toàn bộ registry hoặc outbox khi các test khác còn đang chạy.

## 11. Fixture và cleanup có thể lặp lại

Fixture nên tạo dữ liệu tối thiểu cần thiết cho use case. Mỗi test nên có business key và eventId riêng, dễ nhận diện và không trùng với dữ liệu test khác.

Ví dụ:

~~~java
UUID testRunId = UUID.randomUUID();
String orderId = "ORD-" + testRunId;
UUID eventId = UUID.randomUUID();
~~~

Không nên giả định ID sequence luôn bắt đầu từ 1. Hãy truy vấn theo business key hoặc ID đã lưu trong fixture. Nếu cần kiểm tra sequence, viết test riêng cho behavior đó thay vì buộc mọi test phụ thuộc vào giá trị sequence.

Các chiến lược cleanup:

- Rollback transaction cho thay đổi đồng bộ nằm trong cùng transaction.
- Xóa dữ liệu theo testRunId sau khi listener và background task hoàn tất.
- Drop schema/database riêng khi kết thúc test class hoặc suite.
- Dùng container mới cho test cần trạng thái hoàn toàn sạch.

Cleanup phải theo thứ tự phụ thuộc: dừng hoặc chờ worker, xóa bảng con trước bảng cha khi cần, xóa inbox/outbox/registry liên quan và chỉ sau đó đóng database. Không chạy TRUNCATE toàn bộ bảng dùng chung khi test song song.

## 12. Chạy test song song mà không nhiễm dữ liệu

Test song song giúp giảm thời gian suite nhưng có thể làm lộ lỗi cô lập. Hai test có thể cùng dùng business key cố định, cùng xóa bảng hoặc cùng khởi tạo một singleton container.

Để hỗ trợ chạy song song:

- Mỗi test tạo ID duy nhất cho order, event, saga và tenant.
- Tách database/schema theo class hoặc worker khi cần.
- Không dùng chung mutable static fixture.
- Không để scheduler nền xử lý dữ liệu thuộc test khác.
- Tránh cleanup toàn cục trên database dùng chung.
- Dùng locking/constraint trong test concurrency để xác minh invariant thay vì dựa vào thứ tự thread.
- Cấu hình pool size và số container phù hợp với tài nguyên CI.

Nếu một test chưa thể chạy song song an toàn, đánh dấu giới hạn đó rõ ràng và chạy tuần tự trong phạm vi hẹp. Không tắt toàn bộ parallel execution chỉ để che một test phụ thuộc trạng thái dùng chung mà không tìm nguyên nhân.

## 13. H2 hay database production-like?

H2 hữu ích cho test nhanh và có thể phù hợp với repository đơn giản. Tuy nhiên, H2 không phải bản sao của PostgreSQL, MySQL hoặc SQL Server. Khác biệt có thể xuất hiện ở:

- Kiểu dữ liệu, JSON, UUID, enum và timestamp.
- Cú pháp SQL đặc thù, function và collation.
- Unique constraint, foreign key và index.
- Locking, deadlock, isolation và concurrent update.
- Sequence/identity và hành vi rollback.
- Migration và extension của database.

Nếu module phụ thuộc vào đặc tính database cụ thể, integration test nên chạy trên engine tương thích production bằng Testcontainers hoặc môi trường test tương đương. Có thể giữ H2 cho test repository nhanh, nhưng không dùng kết quả H2 làm bằng chứng duy nhất cho correctness của transaction hoặc migration production.

## 14. Phân biệt test isolation với SQL transaction isolation

SQL transaction isolation level quy định cách một transaction nhìn thấy thay đổi từ transaction khác. Những mức thường gặp:

| Isolation level | Đặc điểm khái quát |
| --- | --- |
| READ UNCOMMITTED | Có thể đọc dữ liệu chưa commit nếu database hỗ trợ mức này. |
| READ COMMITTED | Chỉ đọc dữ liệu đã commit; mỗi statement có thể thấy snapshot mới. |
| REPEATABLE READ | Dữ liệu đã đọc trong transaction thường ổn định theo snapshot; chi tiết phụ thuộc database. |
| SERIALIZABLE | Database cố bảo đảm kết quả tương đương thực hiện tuần tự; có thể phát sinh serialization failure cần retry. |

Mặc định của database có thể khác nhau. Nếu logic module phụ thuộc vào isolation level, hãy kiểm thử với engine production-like và cấu hình transaction thực tế. Test chạy tuần tự trên database sạch không thay thế được test concurrency để phát hiện lost update hoặc write skew.

## 15. Kiểm thử lỗi và phục hồi với database cô lập

Database cô lập cho phép kiểm tra những tình huống mà dữ liệu dùng chung khó tái tạo:

| Tình huống | Điều cần xác minh |
| --- | --- |
| Publisher transaction commit | Dữ liệu nghiệp vụ và publication record được commit đúng. |
| Publisher rollback | Không còn dữ liệu hoặc publication thuộc transaction rollback. |
| Listener rollback | Side effect listener không được commit; publication còn trạng thái cần recovery. |
| Listener async hoàn tất | Projection/inbox được ghi trong database và test chờ đúng điều kiện. |
| Event duplicate | Unique constraint/inbox ngăn side effect lặp. |
| Outbox gửi thất bại | Bản ghi chờ gửi còn tồn tại để retry theo policy. |
| Migration từ database rỗng | Schema được tạo đầy đủ và mapping hợp lệ. |
| Hai test song song | Không đọc/xóa dữ liệu của nhau. |
| Database restart | Ứng dụng có thể kết nối lại và trạng thái bền vững còn nguyên. |
| SQL/locking đặc thù | Hành vi trên database test khớp engine production-like. |

Khi test failure/recovery, dùng database mới hoặc namespace riêng cho từng scenario. Nhờ vậy, publication incomplete hoặc inbox record từ test trước không làm sai kết quả của scenario hiện tại.

## 16. Quản lý vòng đời container và Spring context

Spring Test cache ApplicationContext để tăng tốc suite. Database container phải có vòng đời tương thích với context đang được cache. Nếu container dừng trước khi context bị hủy, test class sau có thể dùng datasource trỏ đến cổng không còn hoạt động.

Các nguyên tắc:

- Chọn vòng đời container theo suite/context thay vì vô tình trộn static container với cached context.
- Dùng bean container do Spring quản lý khi cần gắn lifecycle với context.
- Không tạo một container mới cho mỗi method nếu chi phí khởi tạo quá lớn và không cần mức cô lập đó.
- Nếu container dùng chung, tách schema/database hoặc cleanup theo namespace.
- Đóng pool và context trước khi xóa database/schema.
- Đảm bảo CI có thể tải image và khởi động container; ghi rõ điều kiện môi trường cho test.

Nếu dùng reusable container trong môi trường local, không mặc định rằng dữ liệu bên trong luôn sạch. Reuse chỉ tái sử dụng hạ tầng; test vẫn phải tạo namespace và fixture xác định.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Test pass riêng, fail trong suite | Dữ liệu hoặc sequence còn sót. | Dùng database/schema riêng hoặc fixture ID duy nhất. |
| Listener ghi dữ liệu sau cleanup | Async listener chưa hoàn tất. | Chờ completion trước cleanup; giới hạn thời gian chờ. |
| Test rollback nhưng dữ liệu vẫn tồn tại | Listener hoặc REQUIRES_NEW commit transaction riêng. | Cleanup riêng hoặc dùng database namespace cô lập. |
| Publication cũ được resubmit | Registry dùng chung và có scheduler recovery. | Tách registry/database hoặc kiểm soát recovery trong test. |
| Test H2 pass nhưng production fail | SQL/locking/migration khác engine. | Chạy integration test với database production-like. |
| Test song song lỗi unique constraint | Business key cố định hoặc cleanup đụng nhau. | Dùng ID duy nhất và namespace theo worker/test. |
| Context dùng datasource đã dừng | Container lifecycle không khớp context cache. | Gắn container với Spring context hoặc điều chỉnh cache/lifecycle. |
| Migration chạy lặp hoặc sai schema | Datasource/search path không đồng nhất. | Cấu hình schema rõ ràng và chạy migration trên đúng database. |

## 18. Checklist cô lập database

- Chọn rõ database, schema hoặc transaction scope cho từng loại test.
- Không nhầm cô lập giữa test với SQL transaction isolation level.
- Dùng database production-like cho test migration, locking và SQL đặc thù.
- Chạy Flyway/Liquibase migration thật trên database test.
- Không dựa vào rollback của test để dọn side effect async hoặc REQUIRES_NEW.
- Chờ listener và background task hoàn tất trước cleanup.
- Cô lập Event Publication Registry, inbox, outbox, projection và saga state.
- Dùng business key/eventId duy nhất; không giả định sequence cố định.
- Cleanup theo namespace và đúng thứ tự phụ thuộc.
- Hỗ trợ test song song bằng database/schema riêng hoặc dữ liệu không xung đột.
- Quản lý container lifecycle tương thích với Spring ApplicationContext cache.
- Kiểm tra transaction, constraint và migration trên engine phù hợp production.
- Có test commit, rollback, duplicate, retry, listener failure và recovery.
- Không dùng database dùng chung làm lý do để module truy cập bảng nội bộ của module khác.

Cô lập database giúp module test có trạng thái đầu vào xác định và kết quả có thể lặp lại. Khi database/schema, transaction, event registry và dữ liệu nền được quản lý theo vòng đời test, các kiểm thử Spring Modulith có thể xác minh đúng ranh giới module, hành vi commit/rollback và xử lý event bất đồng bộ mà không bị nhiễm dữ liệu từ lần chạy khác.
