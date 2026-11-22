# Kiểm thử tích hợp giao dịch và lớp lưu trữ

Trong ứng dụng MVC, Controller tiếp nhận request, application service điều phối use case, Model bảo vệ quy tắc nghiệp vụ và repository/DAO làm việc với database. Unit test có thể kiểm tra từng thành phần bằng mock, nhưng không chứng minh được câu truy vấn thực thi đúng, mapping entity phù hợp schema, transaction commit hoặc rollback như mong đợi, hay database thực sự bảo vệ các ràng buộc khi nhiều request chạy đồng thời.

**Kiểm thử tích hợp giao dịch và lớp lưu trữ** xác minh cách các thành phần phối hợp với database thật hoặc môi trường database tương đương production. Bài kiểm thử cần đi qua ranh giới persistence, quan sát dữ liệu sau flush/commit/rollback, xác minh constraint, transaction propagation, isolation và hành vi đồng thời. Với ứng dụng web MVC, có thể bổ sung kiểm thử từ HTTP request qua Controller và application service đến database để xác nhận toàn bộ use case.

Bài học thuộc module **MODEL_VIEW_CONTROLLER**: tổ chức ứng dụng theo Model–View–Controller để phân tách trạng thái/nghiệp vụ, trình bày và tiếp nhận tương tác. Trọng tâm ở đây là kiểm chứng ranh giới transaction và lớp lưu trữ, nơi dữ liệu của nhiều request cần được giữ nhất quán.

## 1. Vì sao cần kiểm thử tích hợp?

Một repository có thể vượt qua unit test dùng mock nhưng vẫn có lỗi khi chạy với database:

- JPQL hoặc native SQL sai cú pháp theo dialect thực tế.
- Mapping kiểu dữ liệu, enum, quan hệ hoặc tên cột không khớp schema.
- Truy vấn thiếu điều kiện tenant hoặc lọc sai trạng thái.
- Lazy relationship bị truy cập sau khi persistence context đóng.
- Unique constraint chỉ phát hiện khi flush hoặc commit.
- Database default không được áp dụng vì ứng dụng gửi NULL tường minh.
- Hai transaction đồng thời ghi đè dữ liệu của nhau.
- Service gọi nhiều repository nhưng một phần dữ liệu đã commit trước khi bước khác thất bại.
- Migration tạo schema khác với schema mà test đang sử dụng.

Mock repository chỉ xác nhận rằng service gọi đúng phương thức mock và xử lý giá trị trả về theo kịch bản test. Nó không thực thi SQL, không chạy constraint, không tạo transaction database và không tái hiện hành vi locking.

Kiểm thử tích hợp bổ sung bằng chứng rằng cấu hình persistence, truy vấn, mapping và transaction hoạt động cùng nhau.

### 1.1. Các cấp độ kiểm thử liên quan

| Loại kiểm thử | Thành phần thật | Điều có thể xác minh |
|---|---|---|
| Unit test Model/service | Logic nghiệp vụ; repository thường được mock | Quy tắc, nhánh xử lý và kết quả độc lập database |
| Repository integration test | Repository, ORM/JDBC và database | SQL/JPQL, mapping, query, constraint |
| Transaction integration test | Application service, transaction manager, repository và database | Commit, rollback, propagation, isolation |
| MVC integration test | HTTP pipeline, Controller, service, persistence và database | Hợp đồng HTTP cùng tác động dữ liệu thực |
| System/end-to-end test | Nhiều thành phần và hạ tầng gần production | Luồng nghiệp vụ xuyên hệ thống |

Không cần biến mọi unit test thành test tích hợp. Unit test nhanh giúp kiểm tra nhiều trường hợp quy tắc; integration test tập trung vào những ranh giới mà mock không thể chứng minh.

## 2. Xác định điều cần chứng minh trước khi viết test

Một test tích hợp tốt bắt đầu từ một giả thuyết cụ thể. Ví dụ:

- Lưu một Task rồi tải lại phải nhận đúng title, status và owner.
- Hai task cùng tenant không được trùng mã theo unique constraint.
- Nếu ghi task thành công nhưng ghi lịch sử thất bại trong cùng use case, cả hai thay đổi phải rollback.
- Khi hai request cập nhật cùng version, một request phải nhận xung đột thay vì âm thầm ghi đè.
- Người dùng tenant A không thể truy vấn dữ liệu tenant B.
- Database migration mới tạo đủ index, foreign key và default cần thiết.

Mỗi test nên có dữ liệu đầu vào, hành động và kết quả quan sát rõ. Tránh viết test chỉ kiểm tra phương thức không ném exception; một thao tác có thể không ném lỗi nhưng vẫn lưu sai trạng thái.

Một mẫu suy nghĩ hữu ích:

1. Thiết lập dữ liệu ban đầu trong database.
2. Gọi repository hoặc use case qua ranh giới cần kiểm tra.
3. Buộc ORM đồng bộ thay đổi nếu cần.
4. Đọc lại từ database theo cách không dùng lại trạng thái cache cũ.
5. Kiểm tra dữ liệu, ràng buộc và trạng thái transaction.

## 3. Chọn database cho integration test

Lựa chọn database ảnh hưởng trực tiếp đến giá trị của test. Một embedded database như H2 có thể khởi động nhanh, nhưng cú pháp SQL, kiểu dữ liệu, collation, locking, isolation và hành vi constraint có thể khác PostgreSQL, MySQL hoặc SQL Server đang chạy production.

Nếu ứng dụng dùng một hệ quản trị cụ thể, nên ưu tiên test trên cùng loại engine và phiên bản tương thích.

### 3.1. Embedded database

Embedded database phù hợp khi:
- Truy vấn dùng tính năng SQL phổ thông.
- Mapping đơn giản.
- Test tập trung vào luồng ORM cơ bản.
- Tốc độ khởi động là ưu tiên và khác biệt dialect không ảnh hưởng mục tiêu test.

Giới hạn:
- Có thể chấp nhận cú pháp mà production từ chối hoặc ngược lại.
- Kiểu dữ liệu, JSON, sequence, collation và function có thể khác.
- Locking và isolation không đại diện chính xác cho production.
- Migration có thể có nhánh riêng cho từng database.

Không nên chỉ dựa vào H2 để kết luận rằng native query, migration hoặc concurrency behavior sẽ chạy đúng trên database thật.

### 3.2. Testcontainers

Testcontainers khởi chạy database trong container phục vụ test và tự quản lý vòng đời container. Cách này cho phép kiểm tra với engine gần production mà không cần cài database thủ công trên máy của mỗi lập trình viên.

Ví dụ dùng PostgreSQL:

~~~java
@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class TaskRepositoryIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("mvc_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void configureDatasource(
        DynamicPropertyRegistry registry
    ) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name",
            postgres::getDriverClassName);
    }

    @Autowired
    TaskRepository tasks;

    @Autowired
    TestEntityManager entityManager;

    // Các test đặt tại đây
}
~~~

Ví dụ minh họa cấu hình JUnit 5, Testcontainers và Spring Boot. Dự án cần khai báo dependency tương ứng và chọn image/version phù hợp với môi trường production. Annotation **@AutoConfigureTestDatabase(replace = NONE)** giúp Spring không thay datasource container bằng embedded database.

Một số phiên bản Spring Boot mới hỗ trợ service connection cho Testcontainers; dự án có thể dùng cơ chế đó thay cho DynamicPropertySource. Điều quan trọng là test thực sự kết nối container mong muốn.

### 3.3. Không dùng database container như một mock

Container vẫn là database thật trong phạm vi test. Nó thực thi SQL, transaction và constraint. Tuy vậy, cấu hình container cần tương đồng với production ở những yếu tố có ảnh hưởng: phiên bản engine, extension, collation, timezone, isolation, schema và migration.

Testcontainers không tự làm dữ liệu test độc lập. Vẫn cần chiến lược tạo dữ liệu, dọn dẹp và tránh phụ thuộc thứ tự chạy.

## 4. Kiểm thử repository với Spring Data JPA

Spring Boot cung cấp **@DataJpaTest** cho các test tập trung vào JPA. Annotation này thường cấu hình entity scan, repository và các thành phần persistence liên quan; test được chạy trong transaction và mặc định rollback sau mỗi test method.

Ví dụ:

~~~java
@DataJpaTest
class TaskRepositoryTest {

    @Autowired
    TaskRepository tasks;

    @Autowired
    TestEntityManager entityManager;

    @Test
    void savesAndFindsTask() {
        Task task = Task.create(
            "Chuẩn bị báo cáo",
            tenantId
        );

        tasks.save(task);
        entityManager.flush();
        entityManager.clear();

        Task loaded = tasks.findById(task.getId())
            .orElseThrow();

        assertThat(loaded.getTitle())
            .isEqualTo("Chuẩn bị báo cáo");
        assertThat(loaded.getTenantId())
            .isEqualTo(tenantId);
    }
}
~~~

Test xác minh entity được lưu và tải lại từ database. **flush()** yêu cầu persistence context đồng bộ thay đổi xuống database; **clear()** xóa entity đang được quản lý khỏi persistence context. Khi truy vấn sau đó, ORM phải tải lại dữ liệu thay vì chỉ trả object đang nằm trong first-level cache.

### 4.1. Vì sao cần flush và clear?

JPA có persistence context theo dõi entity. Sau khi gọi save, dữ liệu có thể chỉ nằm trong bộ nhớ của persistence context và chưa được gửi SQL xuống database. Nếu test chỉ đọc lại object trong cùng context, test có thể vượt qua dù mapping hoặc SQL thực tế có lỗi.

- **flush():** buộc ORM đồng bộ các thay đổi đang chờ xuống database trong transaction hiện tại.
- **clear():** detach các entity đang quản lý để lần đọc tiếp theo không dùng lại instance đã có trong context.
- **find lại:** kiểm tra dữ liệu được đọc từ database qua mapping.

Flush không phải commit. Transaction vẫn có thể rollback sau flush. Test cần hiểu chính xác nó đang xác minh SQL được thực thi hay dữ liệu đã được commit và nhìn thấy từ transaction khác.

### 4.2. Dùng TestEntityManager hoặc EntityManager

TestEntityManager là tiện ích trong Spring Boot JPA test slice, hỗ trợ persist, flush, clear và thao tác entity trong test. Có thể dùng EntityManager trực tiếp nếu cần kiểm soát chi tiết hơn.

Không nên phụ thuộc vào helper riêng nếu test cần chạy ngoài @DataJpaTest. Khi đó, EntityManager, JdbcTemplate hoặc repository có thể được inject trong cấu hình integration phù hợp.

## 5. Kiểm thử truy vấn và mapping

Một repository test nên xác minh kết quả theo ngữ nghĩa truy vấn, không chỉ kiểm tra số lượng tổng quát.

Ví dụ tìm công việc theo tenant và trạng thái:

~~~java
@Test
void filtersTasksByTenantAndStatus() {
    Task openA = tasks.save(
        Task.create("Task A", tenantA, TaskStatus.OPEN)
    );
    tasks.save(
        Task.create("Task B", tenantA, TaskStatus.DONE)
    );
    tasks.save(
        Task.create("Task C", tenantB, TaskStatus.OPEN)
    );

    entityManager.flush();
    entityManager.clear();

    List<Task> result = tasks.findByTenantIdAndStatus(
        tenantA,
        TaskStatus.OPEN
    );

    assertThat(result)
        .extracting(Task::getId)
        .containsExactly(openA.getId());
}
~~~

Test này kiểm tra cả điều kiện tenant và status. Nếu bỏ sót tenant filter, task C có thể xuất hiện. Nếu test chỉ kiểm tra kết quả không rỗng, lỗi truy cập chéo tenant có thể không bị phát hiện.

### 5.1. Kiểm thử quan hệ entity

Với quan hệ one-to-many hoặc many-to-one, nên kiểm tra:
- Foreign key được ghi đúng.
- Cascade được áp dụng theo thiết kế.
- Orphan removal có hành vi đúng nếu được cấu hình.
- Quan hệ lazy/eager hoạt động trong phạm vi persistence context dự kiến.
- Xóa entity cha tuân thủ constraint và quy tắc nghiệp vụ.
- Không xuất hiện truy vấn N+1 trong use case quan trọng.

Ví dụ:

~~~java
@Test
void loadsTaskWithAssignedUser() {
    User user = users.save(User.create("An"));
    Task task = tasks.save(
        Task.create("Chuẩn bị báo cáo", tenantId, user)
    );

    entityManager.flush();
    entityManager.clear();

    Task loaded = tasks.findWithAssigneeById(task.getId())
        .orElseThrow();

    assertThat(loaded.getAssignee().getDisplayName())
        .isEqualTo("An");
}
~~~

Tên repository method và model là minh họa. Nếu use case cần assignee, nên viết truy vấn fetch phù hợp hoặc projection; không nên để View vô tình kích hoạt lazy query sau khi transaction đã đóng.

### 5.2. Kiểm thử projection và DTO

Nếu repository trả projection cho trang danh sách, hãy kiểm tra đúng trường được chọn và kiểu dữ liệu. Projection giúp tránh tải entity graph lớn và giảm nguy cơ đưa trường nội bộ vào ViewModel.

Không nên chỉ assert số phần tử. Hãy kiểm tra các trường quan trọng và điều kiện lọc, đặc biệt với tenant, owner, trạng thái và quyền.

## 6. Kiểm thử constraint của database

Một số quy tắc cần được bảo vệ ngay tại database để chống race condition và dữ liệu không hợp lệ. Integration test nên xác minh constraint thực sự tồn tại và được thực thi.

Các loại thường gặp:

| Constraint | Điều cần xác minh |
|---|---|
| NOT NULL | Không thể lưu giá trị null ở cột bắt buộc |
| UNIQUE | Không thể tạo hai hàng trùng khóa duy nhất |
| FOREIGN KEY | Không thể tham chiếu hàng không tồn tại |
| CHECK | Giá trị phải thỏa điều kiện ở database |
| DEFAULT | Giá trị mặc định được áp dụng đúng khi cột được bỏ qua |
| INDEX | Truy vấn quan trọng có index theo schema; hiệu năng cần test riêng |

Ví dụ kiểm tra unique constraint:

~~~java
@Test
void rejectsDuplicateTaskCode() {
    tasks.saveAndFlush(
        Task.createWithCode("TASK-100", tenantId)
    );

    assertThatThrownBy(() ->
        tasks.saveAndFlush(
            Task.createWithCode("TASK-100", tenantId)
        )
    ).isInstanceOf(DataIntegrityViolationException.class);
}
~~~

Tên exception cụ thể có thể khác theo tầng và thời điểm flush; Spring thường chuyển lỗi persistence thành DataAccessException. Không nên assert message SQL cụ thể vì message phụ thuộc database và driver.

Sau khi một constraint violation xảy ra, transaction có thể bị đánh dấu rollback-only và persistence context không còn phù hợp để tiếp tục dùng. Hãy để test transaction kết thúc hoặc rollback, thay vì tiếp tục thao tác tùy tiện trên cùng context.

### 6.1. Kiểm thử default và null

Cần phân biệt:
- Cột bị bỏ khỏi câu INSERT.
- Cột được INSERT với NULL.
- Cột được INSERT với giá trị cụ thể.

Database default thường chỉ áp dụng khi cột được bỏ qua hoặc dùng từ khóa DEFAULT. Nếu ORM gửi NULL tường minh, default có thể không được áp dụng.

Có thể dùng JdbcTemplate trong integration test để kiểm tra trực tiếp câu lệnh bỏ cột và câu lệnh gửi NULL. Với ORM, cần kiểm tra SQL thực tế hoặc mapping như insertable/updatable/default theo cấu hình entity. Không suy luận rằng annotation hoặc giá trị khởi tạo Java chứng minh database default đang hoạt động.

## 7. Kiểm thử migration và schema

Ứng dụng thường dùng Flyway hoặc Liquibase để quản lý schema theo phiên bản. Test tích hợp nên khởi tạo database rỗng rồi chạy migration thực tế, sau đó thực thi repository và use case.

Điều này phát hiện:
- Migration thiếu cột hoặc index.
- Kiểu dữ liệu khác với mapping entity.
- Foreign key hoặc unique constraint bị thiếu.
- Migration mới không chạy được trên phiên bản database mục tiêu.
- Dữ liệu cũ không được chuyển đổi đúng.
- Native query không tương thích schema sau migration.

Không nên tạo schema test bằng cách Hibernate tự generate nếu mục tiêu là xác minh migration. Nếu test chỉ dùng create-drop, migration có thể chưa từng chạy và lỗi deploy vẫn bị bỏ sót.

Một cấu hình integration có thể đặt Hibernate ở chế độ validate hoặc không tự tạo schema, rồi để Flyway/Liquibase tạo cấu trúc. Cách cấu hình cụ thể phụ thuộc Spring Boot và chiến lược migration của dự án.

### 7.1. Test migration từ phiên bản cũ

Với thay đổi schema có chuyển đổi dữ liệu, nên kiểm thử nâng cấp từ schema phiên bản trước:
1. Tạo database với migration cũ.
2. Seed dữ liệu đại diện cho phiên bản cũ.
3. Chạy migration mới.
4. Đọc lại dữ liệu và xác minh mapping/chuyển đổi.
5. Xác minh constraint và index sau migration.

Test tạo database mới từ đầu chỉ chứng minh chuỗi migration đầy đủ có thể chạy trên database rỗng; nó chưa chứng minh nâng cấp dữ liệu đang tồn tại an toàn.

## 8. Kiểm thử transaction commit và rollback

Một use case có thể cập nhật nhiều repository trong cùng một transaction. Cần kiểm tra rằng nếu bước sau thất bại, thay đổi trước đó không bị commit một phần.

Ví dụ service:

~~~java
@Service
class RegisterTaskService {
    private final TaskRepository tasks;
    private final AuditRepository audits;

    RegisterTaskService(
        TaskRepository tasks,
        AuditRepository audits
    ) {
        this.tasks = tasks;
        this.audits = audits;
    }

    @Transactional
    public UUID register(RegisterTaskCommand command) {
        Task task = tasks.save(
            Task.create(command.title(), command.tenantId())
        );

        audits.save(
            AuditEntry.forTask(task.getId(), "TASK_CREATED")
        );

        return task.getId();
    }
}
~~~

Nếu ghi audit thất bại do lỗi runtime và cả hai repository tham gia cùng transaction manager, task cũng phải rollback theo chính sách mặc định. Test cần xác minh bằng một transaction độc lập sau khi phương thức service kết thúc.

### 8.1. Bẫy transaction của chính test

**@DataJpaTest** mặc định chạy test method trong một transaction và rollback sau test. Điều này rất hữu ích để cô lập dữ liệu, nhưng có thể che khuất hành vi commit của application service.

Nếu test method đã mở transaction, service có propagation REQUIRED thường tham gia transaction đó. Khi service trả về, transaction chưa commit vì transaction ngoài cùng thuộc test vẫn đang mở. Do đó, test không thể kết luận rằng service đã commit chỉ vì phương thức đã kết thúc.

Để kiểm tra transaction boundary của service:
- Dùng test không có transaction bao ngoài.
- Gọi service để transaction do service mở tự commit hoặc rollback khi phương thức kết thúc.
- Đọc lại bằng một transaction độc lập hoặc JdbcTemplate sau lời gọi.
- Nếu cần kiểm tra chính xác visibility giữa hai transaction, dùng hai connection/transaction riêng.

Có thể dùng TransactionTemplate để điều khiển ranh giới rõ ràng. **@Commit** hoặc **@Rollback(false)** có thể hữu ích trong một số test, nhưng cần dọn dữ liệu chắc chắn; không dùng chúng như giải pháp mặc định vì dễ làm test phụ thuộc nhau.

### 8.2. Test rollback khi bước sau thất bại

Có thể dùng một collaborator test cố ý ném exception hoặc cấu hình repository để tạo lỗi constraint. Ví dụ:

~~~java
@Test
void rollsBackTaskWhenAuditWriteFails() {
    assertThatThrownBy(() ->
        registerTaskService.register(command)
    ).isInstanceOf(AuditWriteException.class);

    assertThat(taskRepository.countByTenantId(command.tenantId()))
        .isZero();
}
~~~

Test này phải chạy mà không có transaction bao ngoài test method. Nếu service transaction đã rollback khi exception thoát khỏi proxy, truy vấn sau đó từ transaction mới phải không thấy task vừa tạo.

Khi dùng mock để làm audit service ném exception, test vẫn xác minh transaction của database đối với task repository, nhưng chưa xác minh persistence thật của audit repository. Có thể bổ sung một integration test với constraint thật để kiểm tra cả hai repository.

### 8.3. Kiểm thử checked exception và rollback rule

Spring transaction mặc định thường rollback với RuntimeException và Error; checked exception không tự động rollback trừ khi cấu hình rollbackFor hoặc transaction rule tương ứng.

Nếu use case ném checked exception sau khi lưu dữ liệu, test nên xác minh chính sách đã chọn:
- Nếu checked exception phải rollback, cấu hình rollbackFor và kiểm tra dữ liệu không tồn tại.
- Nếu checked exception được phép commit, xác minh hành vi đó có chủ đích và được tài liệu hóa.

Không nên chỉ kiểm tra loại exception; phải kiểm tra trạng thái database sau khi transaction kết thúc.

## 9. Kiểm thử propagation

Propagation xác định service con tham gia transaction hiện tại hay tạo transaction riêng. Cần test theo hành vi dữ liệu quan sát được, không chỉ kiểm tra annotation có tồn tại.

| Propagation | Hành vi cần kiểm tra |
|---|---|
| REQUIRED | Service con tham gia transaction hiện tại; lỗi có thể rollback toàn bộ |
| REQUIRES_NEW | Transaction con commit/rollback độc lập với transaction ngoài |
| MANDATORY | Gọi khi không có transaction phải thất bại |
| SUPPORTS | Chạy có hoặc không có transaction tùy caller |
| NOT_SUPPORTED | Tạm ngưng transaction hiện tại trong phạm vi phương thức |
| NESTED | Savepoint/rollback một phần nếu transaction manager hỗ trợ |

Ví dụ với REQUIRES_NEW: service ngoài cập nhật một bản ghi rồi gọi service con ghi audit độc lập. Nếu service ngoài rollback nhưng transaction con đã commit, audit vẫn tồn tại. Đây có thể là hành vi đúng khi audit ghi nhận nỗ lực thao tác; nhưng nếu audit mang ý nghĩa “nghiệp vụ đã thành công”, nó có thể tạo dữ liệu gây hiểu nhầm.

Test cần kiểm tra chính xác semantics mong muốn và sử dụng transaction manager/database hỗ trợ propagation tương ứng. Không mặc định NESTED hoạt động như một transaction phân tán; nó thường dựa trên savepoint và phụ thuộc transaction manager.

## 10. Kiểm thử isolation và truy cập đồng thời

Một test chạy tuần tự không thể chứng minh hai request đồng thời không ghi đè nhau. Với use case quan trọng, cần tạo hai transaction riêng, thường trên hai thread và hai connection, rồi điều phối thời điểm đọc/ghi.

Các tình huống có thể kiểm tra:
- Hai transaction cùng đọc một version rồi cập nhật.
- Hai request tạo cùng khóa unique.
- Hai giao dịch cùng trừ số lượng tồn kho.
- Một transaction giữ lock trong khi transaction khác cố đọc hoặc ghi.
- Isolation level ngăn hoặc cho phép hiện tượng đọc theo đặc tính database.

### 10.1. Optimistic locking

Với JPA, entity có trường @Version. Khi hai transaction cùng sửa version cũ, một transaction có thể thất bại do optimistic lock.

~~~java
@Entity
class InventoryItem {
    @Id
    private UUID id;

    @Version
    private long version;

    private int available;
}
~~~

Test cần:
1. Tạo entity với version ban đầu.
2. Mở hai transaction độc lập.
3. Cả hai đọc cùng version.
4. Điều phối để transaction A cập nhật và commit.
5. Transaction B cập nhật theo version cũ.
6. Xác minh B nhận optimistic locking failure hoặc lỗi đã được chuyển đổi theo hợp đồng.
7. Đọc lại database để xác minh số lượng cuối không bị cập nhật mất.

Cần kiểm soát đồng bộ bằng CountDownLatch, CyclicBarrier hoặc công cụ tương đương; tránh dùng sleep ngẫu nhiên vì không bảo đảm thứ tự.

### 10.2. Unique constraint dưới tải đồng thời

Một kiểm tra “chưa tồn tại” trong Java không ngăn hai request đồng thời cùng tạo một giá trị. Unique constraint ở database là lớp bảo vệ cuối.

Test có thể chạy hai transaction cùng insert một email hoặc mã đơn. Kết quả mong đợi là chỉ một transaction commit; transaction còn lại nhận lỗi constraint và application service chuyển thành kết quả xung đột phù hợp.

Không nên giả định thread nào luôn thắng. Test chỉ nên kiểm tra bất biến cuối: có đúng một hàng, và kết quả của hai thao tác phản ánh một thành công cùng một thất bại.

### 10.3. Isolation phụ thuộc database

READ_COMMITTED, REPEATABLE_READ và SERIALIZABLE có hành vi cụ thể khác nhau giữa hệ quản trị. Test concurrency nên chạy trên engine gần production. Không nên viết một test H2 rồi kết luận PostgreSQL hoặc MySQL sẽ có cùng locking behavior.

Test cần giới hạn thời gian chờ và cleanup transaction/thread trong finally để tránh làm treo suite khi có deadlock hoặc lỗi đồng bộ.

## 11. Kiểm thử lớp lưu trữ qua luồng MVC

Repository test xác minh persistence; MVC integration test xác minh request thực sự đi qua binding, security, Controller, service và database.

Với Spring Boot, có thể dùng @SpringBootTest và @AutoConfigureMockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class TaskFlowIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    TaskRepository tasks;

    @Test
    void createsTaskThroughHttpRequest() throws Exception {
        mockMvc.perform(post("/api/tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "title": "Chuẩn bị báo cáo"
                    }
                    """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title")
                .value("Chuẩn bị báo cáo"));

        assertThat(tasks.findAll())
            .extracting(Task::getTitle)
            .contains("Chuẩn bị báo cáo");
    }
}
~~~

Ví dụ cần bổ sung authentication, tenant context và request DTO theo ứng dụng thật. Nếu endpoint trả 202 cho background job, test nên xác minh job record được tạo và status URL truy vấn được; không nên đợi worker chạy thật trong mọi test Controller.

### 11.1. Test transaction ở HTTP boundary

Nếu test method có @Transactional, request MockMvc có thể được xử lý trong thread/request transaction khác với transaction của test. Không nên giả định transaction test bao bọc transaction của server như một lời gọi phương thức thông thường.

Để xác minh dữ liệu được commit qua endpoint:
- Không gắn @Transactional lên test method nếu mục tiêu là quan sát commit.
- Gửi HTTP request.
- Sau response, truy vấn bằng repository hoặc JDBC trong transaction độc lập.
- Kiểm tra cả dữ liệu đã lưu và các side effect bền vững.

Nếu dùng rollback test để dọn dữ liệu, hãy hiểu transaction nào đang rollback. Request HTTP qua MockMvc thường đi qua pipeline server và có thể mở transaction riêng ở application service.

## 12. Kiểm thử tenant isolation và phân quyền dữ liệu

Một repository method có thể bind tham số an toàn nhưng vẫn trả sai dữ liệu nếu thiếu tenant condition. Test cần tạo ít nhất hai tenant và xác minh truy vấn không vượt phạm vi.

Ví dụ:
- Tạo task A thuộc tenant A.
- Tạo task B thuộc tenant B.
- Gọi use case với principal thuộc tenant A.
- Xác minh chỉ task A xuất hiện.
- Thử thay ID sang task B và xác minh bị từ chối hoặc không tìm thấy theo chính sách.

Không chỉ kiểm tra status code. Cần xác minh response không chứa title, ID hoặc trường nào của tenant B. Kiểm tra cả endpoint list, detail, update, delete và download nếu chúng truy cập cùng tài nguyên.

Nếu database dùng Row-Level Security, test cần chạy bằng role tương ứng với ứng dụng, thiết lập tenant context trên connection và xác minh context được reset đúng khi connection pool tái sử dụng connection.

## 13. Kiểm thử outbox và tác dụng phụ sau commit

Nếu use case ghi dữ liệu nghiệp vụ và outbox event trong cùng transaction, integration test cần xác minh:

- Khi transaction commit, cả business row và outbox row cùng tồn tại.
- Khi transaction rollback, cả hai đều không tồn tại.
- Dispatcher chỉ publish event đã commit.
- Nếu publish thất bại, event vẫn có thể được retry.
- Consumer xử lý message trùng lặp mà không tạo tác dụng phụ lặp ngoài ý muốn.

Không nên kiểm thử outbox bằng cách chỉ mock publisher và xác minh phương thức được gọi. Cần test database để chứng minh job/event record cùng nằm trong transaction với dữ liệu nghiệp vụ.

Với listener AFTER_COMMIT, kiểm tra event chỉ được xử lý sau commit. Cần lưu ý listener chạy trong bộ nhớ không tự bảo đảm giao sự kiện bền vững nếu process dừng sau commit; test outbox sẽ xác minh cơ chế bền vững phù hợp hơn cho tác vụ quan trọng.

## 14. Kiểm thử query performance và N+1

Integration test chủ yếu xác minh tính đúng đắn, nhưng có thể bổ sung kiểm tra truy vấn cho các use case quan trọng:
- Đếm số SQL statement trong một luồng đọc.
- Xác minh fetch join hoặc entity graph giảm N+1.
- Kiểm tra pagination và thứ tự ổn định.
- Kiểm tra index bằng execution plan ở bộ test hiệu năng riêng.
- Dùng dataset đủ đại diện để phát hiện truy vấn tăng theo số bản ghi.

Không nên khẳng định truy vấn nhanh chỉ vì test chạy dưới một số mili giây trên máy phát triển. Thời gian phụ thuộc phần cứng, cache, container và dữ liệu. Test hiệu năng nên có môi trường, dataset, warm-up và ngưỡng được kiểm soát riêng.

Có thể dùng Hibernate statistics hoặc datasource proxy để đếm query trong test. Nhưng không nên buộc mọi test vào số lượng SQL quá chi tiết nếu thay đổi ORM không làm thay đổi hợp đồng; hãy tập trung vào dấu hiệu N+1 hoặc tải dữ liệu ngoài ý muốn.

## 15. Dọn dữ liệu và cô lập test

Integration test cần chạy độc lập và có thể chạy song song. Một số chiến lược:

| Cách dọn dữ liệu | Phù hợp | Lưu ý |
|---|---|---|
| Rollback transaction test | Repository test đơn giản | Không dùng để chứng minh commit thực |
| Xóa dữ liệu theo test ID | Test không chạy trong transaction bao ngoài | Cần cleanup kể cả khi test thất bại |
| Schema/database riêng | Suite song song hoặc nhiều module | Tốn tài nguyên hơn nhưng cô lập tốt |
| Truncate bảng | Dataset lớn, cần reset nhanh | Cẩn thận foreign key và transaction |
| Tạo container/schema mới | Test migration hoặc test độc lập mạnh | Chậm hơn, cần quản lý vòng đời |

Tránh để test phụ thuộc vào thứ tự chạy hoặc ID tự tăng bắt đầu từ một giá trị cố định. Dùng UUID hoặc tạo dữ liệu riêng theo test khi phù hợp. Không chia sẻ mutable fixture giữa các test method.

Nếu dùng @DirtiesContext, chỉ dùng khi test thực sự làm thay đổi context không thể khôi phục; không thêm vào mọi test vì sẽ làm suite chậm.

## 16. Kiểm thử transaction timeout, deadlock và retry

Các tình huống vận hành như lock timeout, deadlock hoặc serialization failure cần được xử lý có chủ đích.

Test có thể:
- Tạo hai transaction lấy lock theo thứ tự khác nhau để xác minh deadlock được database phát hiện.
- Kiểm tra ứng dụng chuyển lỗi sang mã lỗi phù hợp.
- Xác minh retry chỉ áp dụng với lỗi có thể thử lại.
- Giới hạn thời gian chờ để suite không bị treo.
- Kiểm tra transaction sau lỗi được rollback và connection được trả về pool.

Không nên phụ thuộc vào timing quá mong manh để tái hiện deadlock trong mọi lần chạy. Có thể dành một nhóm integration test chuyên biệt cho concurrency, chạy trên database thật và có cơ chế đồng bộ rõ. Test thường xuyên nên tập trung vào bất biến và đường lỗi ổn định.

## 17. Những lỗi thường gặp khi viết integration test

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ mock repository rồi gọi đó là test tích hợp | Không thực thi SQL hoặc transaction thật | Dùng database test thật |
| Chỉ dùng H2 cho hệ thống phụ thuộc dialect cụ thể | Bỏ sót lỗi schema, query và locking production | Dùng Testcontainers với engine tương thích |
| Không flush trước khi kiểm tra constraint | Lỗi SQL chưa được thực thi nên test vượt qua giả | Gọi flush hoặc saveAndFlush |
| Đọc lại entity trong cùng persistence context | Có thể chỉ đọc object trong cache | Flush, clear rồi tải lại |
| Test có @Transactional khi cần chứng minh service commit | Service tham gia transaction test và chưa commit | Bỏ transaction bao ngoài hoặc điều khiển transaction rõ |
| Kiểm tra exception nhưng không kiểm tra database | Không biết dữ liệu đã rollback chưa | Đọc lại bằng transaction độc lập |
| Dùng sleep để test concurrency | Test không ổn định | Dùng barrier/latch và timeout |
| Chỉ kiểm tra truy vấn trả dữ liệu không rỗng | Bỏ sót lọc tenant hoặc quyền | Seed nhiều tenant và assert chính xác ID |
| Tạo schema bằng Hibernate thay vì migration | Migration lỗi không bị phát hiện | Chạy Flyway/Liquibase trong test |
| Chia sẻ dữ liệu test giữa các method | Test phụ thuộc thứ tự và chạy song song lỗi | Fixture riêng, rollback hoặc cleanup |
| Assert nguyên văn lỗi SQL | Test phụ thuộc driver/dialect | Assert exception type, error code ứng dụng và dữ liệu cuối |

## 18. Quy trình xây dựng bộ kiểm thử tích hợp

Khi thêm một use case có persistence, hãy thực hiện theo thứ tự:

1. Xác định bất biến và ranh giới transaction của use case.
2. Liệt kê truy vấn, quan hệ entity, constraint và migration liên quan.
3. Chọn database test tương thích production.
4. Viết repository integration test cho truy vấn và mapping quan trọng.
5. Kiểm tra constraint bằng flush và đọc lại dữ liệu.
6. Viết service integration test cho commit, rollback và propagation.
7. Viết concurrency test cho unique, version hoặc lock quan trọng.
8. Kiểm thử tenant scope và quyền truy cập ở các endpoint.
9. Kiểm thử migration trên database rỗng và nâng cấp từ schema cũ khi cần.
10. Bổ sung MVC integration test cho những luồng HTTP có rủi ro cao.
11. Kiểm tra outbox, retry và tác dụng phụ nếu use case phát sự kiện.
12. Bảo đảm dữ liệu được cô lập, test có timeout và chạy độc lập.

Không phải use case nào cũng cần đủ mọi loại test. Hãy chọn theo rủi ro: một CRUD đơn giản có thể cần repository test và một vài MVC test; chuyển tiền, đặt chỗ hoặc cập nhật nhiều bảng cần kiểm tra transaction, concurrency và constraint kỹ hơn.

## 19. Những điểm cần ghi nhớ

Unit test với mock kiểm tra logic của từng thành phần, nhưng không chứng minh database thực thi truy vấn, mapping và transaction đúng. Repository integration test nên chạy với database tương thích production, dùng dữ liệu rõ ràng và xác minh kết quả sau flush/clear.

Để kiểm tra commit/rollback, cần hiểu transaction của test. @DataJpaTest thường tự mở transaction và rollback sau mỗi test; điều này tiện cho cô lập dữ liệu nhưng có thể che khuất ranh giới commit của service. Khi cần chứng minh commit hoặc rollback của use case, hãy gọi service trong điều kiện không có transaction bao ngoài và quan sát database từ transaction độc lập.

Dùng Testcontainers khi cần xác minh dialect, constraint, migration, isolation và locking trên engine thật. Kiểm thử các bất biến bằng constraint, optimistic locking, tenant scope, outbox và concurrency; không dựa vào sleep hoặc assert message SQL. Kết hợp repository, service và MVC integration test giúp xác nhận dữ liệu đi xuyên qua các tầng MVC mà vẫn nhất quán khi thành công, thất bại hoặc có request đồng thời.
