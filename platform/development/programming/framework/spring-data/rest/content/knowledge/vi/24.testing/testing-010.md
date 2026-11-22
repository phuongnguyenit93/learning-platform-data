# Kiểm tra validation, sự kiện và rollback khi xử lý thất bại

## Mục tiêu

Spring Data REST xuất các Spring Data repository thành tài nguyên HTTP. Khi kiểm thử một luồng ghi dữ liệu, cần xác minh đồng thời ba lớp hành vi:

1. **Validation:** dữ liệu không hợp lệ bị từ chối trước khi được lưu.
2. **Lifecycle events:** các hook tương ứng với thao tác tạo, cập nhật, liên kết hoặc xóa được phát và xử lý đúng.
3. **Transaction rollback:** nếu một nghiệp vụ gồm nhiều lần ghi thất bại giữa chừng, tất cả thay đổi thuộc cùng transaction phải được hoàn tác.

Nên có cả kiểm thử qua HTTP endpoint Spring Data REST và kiểm thử transaction ở service. Gọi trực tiếp repository chỉ kiểm tra tầng persistence; nó không đi qua toàn bộ pipeline validation và event của REST exporter.

Ví dụ dưới đây dùng Java, JUnit Jupiter, Spring Boot, Spring Data REST và Spring Data JPA. Hãy dùng dependency versions do Spring Boot BOM của dự án quản lý; tên package của một số annotation kiểm thử có thể khác giữa các thế hệ Spring Boot.

## 1. Chuẩn bị endpoint và domain model

Giả sử ứng dụng có entity **Person** với các trường **id**, **name**, **email**, constructor và getter tương ứng:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
    private String email;

    protected Person() {
    }

    public Person(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository được Spring Data REST xuất thành endpoint **/people**:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    boolean existsByEmail(String email);
}
~~~

Các URL thực tế còn phụ thuộc **spring.data.rest.base-path**, cấu hình repository và quyền truy cập. Trong ví dụ này, **POST /people** tạo mới một **Person**, còn **PUT** hoặc **PATCH /people/{id}** cập nhật tài nguyên.

## 2. Kiểm thử validation

Spring Data REST hỗ trợ đăng ký **org.springframework.validation.Validator** theo hai cách:

- Đặt tên bean theo quy ước **<event><DomainType>Validator**. Ví dụ **beforeCreatePersonValidator** chạy ở hook **beforeCreate** cho domain type **Person**.
- Đăng ký thủ công bằng **RepositoryRestConfigurer.configureValidatingRepositoryEventListener(...)** và **ValidatingRepositoryEventListener.addValidator(...)**.

Cách đặt tên bean thường ngắn gọn nhất. Ví dụ validator yêu cầu email không được để trống:

~~~java
@Component("beforeCreatePersonValidator")
public class BeforeCreatePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (!StringUtils.hasText(person.getEmail())) {
            errors.rejectValue(
                "email",
                "email.required",
                "Email is required"
            );
        }
    }
}
~~~

Các import chính:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;
~~~

Đối với cập nhật, đăng ký validator ở hook **beforeSave**, chẳng hạn bean **beforeSavePersonValidator**. Tạo và cập nhật là hai thời điểm khác nhau; đừng giả định validator **beforeCreate** tự chạy khi **PUT** hoặc **PATCH**. Nếu muốn tái sử dụng logic, tách phần kiểm tra thành một lớp dùng chung rồi đăng ký ở cả hai hook.

Có thể đăng ký thủ công thay cho quy ước tên bean:

~~~java
@Configuration
public class RestValidationConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeSave", new PersonValidator());
    }
}
~~~

Không nên đăng ký cùng một validator bằng cả hai cách nếu không chủ ý chạy nó hai lần.

Khi validator thêm lỗi vào **Errors**, Spring Data REST ném **RepositoryConstraintViolationException**. Đây là ngoại lệ validation riêng của Spring Data REST, kế thừa **DataIntegrityViolationException**; REST exception handling chuyển lỗi thành phản hồi HTTP cho client. Với cấu hình mặc định, kiểm thử thường xác nhận phản hồi **400 Bad Request**. Nếu ứng dụng có **@ControllerAdvice** tùy chỉnh, hãy kiểm tra status và cấu trúc lỗi theo hợp đồng API thực tế.

Ví dụ gọi endpoint:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan",
  "email": ""
}
~~~

Kết quả cần xác minh: request bị từ chối, phản hồi là lỗi client (thường là **400**), và không có bản ghi **Person** mang email vừa gửi trong repository.

## 3. Kiểm thử lifecycle events

Spring Data REST phát tám event trong quá trình xử lý entity:

| Thao tác | Trước thao tác lưu/xóa | Sau thao tác lưu/xóa |
|---|---|---|
| Tạo entity | **BeforeCreateEvent** | **AfterCreateEvent** |
| Lưu entity hiện có | **BeforeSaveEvent** | **AfterSaveEvent** |
| Lưu liên kết | **BeforeLinkSaveEvent** | **AfterLinkSaveEvent** |
| Xóa entity | **BeforeDeleteEvent** | **AfterDeleteEvent** |

Có hai cách xử lý event:

- Kế thừa **AbstractRepositoryEventListener** rồi override các callback như **onBeforeSave** hoặc **onAfterDelete**. Cách này nhận nhiều loại domain object; listener phải tự kiểm tra kiểu entity.
- Dùng **@RepositoryEventHandler** cùng annotation như **@HandleBeforeSave**, **@HandleAfterSave**. Kiểu tham số đầu tiên của method xác định domain type, giúp handler có kiểu dữ liệu cụ thể.

Ví dụ handler cho **Person**:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeSave
    public void beforeSave(Person person) {
        if (!StringUtils.hasText(person.getName())) {
            throw new IllegalArgumentException("name must not be blank");
        }
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // Ghi log hoặc cập nhật xử lý nội bộ nhẹ sau khi repository save.
    }
}
~~~

Các annotation handler thuộc package **org.springframework.data.rest.core.annotation**. Handler phải là Spring bean: đánh dấu bằng **@Component** để component scan tìm thấy, hoặc khai báo bằng **@Bean**. **@RepositoryEventHandler(Person.class)** giới hạn handler vào **Person**; nếu bỏ tham số class, kiểu của tham số đầu tiên trên từng method vẫn được dùng để xác định domain type.

Các event Spring Data REST là Spring application events và mặc định được phát đồng bộ. Điều đó có nghĩa là listener đồng bộ được gọi trong luồng xử lý phát event. Tuy vậy, **AfterSaveEvent** chỉ nói repository đã thực hiện thao tác save; không nên coi tên event này là bằng chứng transaction đã commit. Cũng cần nhớ các REST lifecycle events thuộc pipeline của Spring Data REST: gọi repository trực tiếp trong unit test không tương đương gửi request qua REST exporter.

### Gắn xử lý phụ vào transaction

Nếu cần chỉ gửi thông báo hoặc thực hiện side effect sau khi transaction commit thành công, dùng event nghiệp vụ riêng và **@TransactionalEventListener**:

~~~java
@Component
public class PersonCreatedListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PersonCreated event) {
        // Gửi thông báo sau khi transaction đã commit.
    }
}
~~~

**@TransactionalEventListener** mặc định chạy ở **AFTER_COMMIT**. Có thể chọn **BEFORE_COMMIT**, **AFTER_ROLLBACK** hoặc **AFTER_COMPLETION**. Nếu không có transaction đang chạy, listener mặc định không được gọi; chỉ bật **fallbackExecution = true** khi thật sự muốn xử lý cả trường hợp đó. Listener ở **AFTER_COMMIT** không thể làm transaction đã commit quay lại trạng thái rollback. Với side effect cần bảo đảm giao nhận bền vững, cân nhắc transactional outbox thay vì phụ thuộc vào một lời gọi mạng trong callback.

## 4. Kiểm thử rollback khi nghiệp vụ thất bại

Theo mặc định, Spring transaction đánh dấu rollback khi method transactional ném **RuntimeException** hoặc **Error** ra ngoài. Checked exception không tự động rollback theo quy tắc mặc định. Có thể khai báo rõ loại checked exception cần rollback:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public void performBusinessOperation() throws BusinessRuleException {
    // Các thao tác ghi dữ liệu.
    throw new BusinessRuleException("Business rule failed");
}
~~~

Ví dụ service ghi vào hai repository rồi cố ý ném runtime exception:

~~~java
@Service
public class PersonWorkflowService {

    private final PersonRepository people;
    private final AuditRepository audits;

    public PersonWorkflowService(
            PersonRepository people,
            AuditRepository audits) {
        this.people = people;
        this.audits = audits;
    }

    @Transactional
    public void createAndFail(String email) {
        people.save(new Person("Lan", email));
        audits.save(new AuditEntry(email, "CREATED"));

        // Mô phỏng lỗi xảy ra sau khi đã có các lệnh ghi.
        throw new IllegalStateException("Simulated workflow failure");
    }
}
~~~

**AuditEntry** là entity audit có trường **email** và **action**; repository tương ứng có thể khai báo như sau:

~~~java
public interface AuditRepository extends JpaRepository<AuditEntry, Long> {

    boolean existsByEmail(String email);
}
~~~

Khi method **createAndFail** kết thúc bằng exception, cả hai lần ghi chỉ được rollback nếu chúng tham gia cùng transaction manager và cùng transaction. Kiểm thử nên gọi service thông qua Spring bean đã được inject để transaction proxy thực sự được áp dụng. Không tự gọi method transactional từ một method khác trong cùng object rồi kỳ vọng proxy chặn lời gọi nội bộ đó.

Ví dụ kiểm thử độc lập cho rollback:

~~~java
@SpringBootTest
class PersonWorkflowRollbackTest {

    @Autowired
    private PersonWorkflowService workflow;

    @Autowired
    private PersonRepository people;

    @Autowired
    private AuditRepository audits;

    @Test
    void rollsBackAllWritesWhenWorkflowFails() {
        String email = "rollback-" + UUID.randomUUID() + "@example.test";

        assertThatThrownBy(() -> workflow.createAndFail(email))
            .isInstanceOf(IllegalStateException.class);

        assertThat(people.existsByEmail(email)).isFalse();
        assertThat(audits.existsByEmail(email)).isFalse();
    }
}
~~~

Không đặt **@Transactional** lên test rollback này. Khi service transaction kết thúc do exception, các truy vấn assertion chạy sau đó và kiểm tra trạng thái đã được rollback. Dùng email duy nhất để các lần chạy test không ảnh hưởng nhau.

### Ranh giới transaction với Spring Data REST

Validation ở **beforeCreate** hoặc **beforeSave** phù hợp để chặn dữ liệu trước khi repository lưu. Với nghiệp vụ nhiều bước, ví dụ vừa lưu **Person**, vừa lưu audit, vừa cập nhật một aggregate khác, hãy đặt toàn bộ chuỗi thao tác trong một service method **@Transactional** và để exception thoát khỏi method đó.

Nếu một REST lifecycle handler chỉ gọi một service transactional sau khi repository đã save, transaction mới có thể bắt đầu quá muộn để bao trùm lần save ban đầu. Để bảo đảm tính nguyên tử của toàn bộ request, hãy thiết kế custom controller/workflow gọi service làm transaction boundary, hoặc xác minh rõ rằng có transaction bên ngoài bao trùm toàn bộ chuỗi thao tác. Không suy luận rollback chỉ từ việc handler được gọi đồng bộ.

Các trường hợp thường khiến rollback không xảy ra:

- Exception là checked exception nhưng không có **rollbackFor** phù hợp.
- Code bắt exception rồi không ném lại, khiến transaction interceptor thấy method kết thúc bình thường.
- Lời gọi transactional là self-invocation, không đi qua proxy.
- Một phần thao tác dùng transaction manager hoặc resource khác.
- Công việc đã chạy bất đồng bộ hoặc trong listener **AFTER_COMMIT**, tức là sau transaction cần kiểm tra.

## 5. Kiểm thử HTTP và event bằng MockMvc

**MockMvc** thực hiện đầy đủ quá trình xử lý Spring MVC bằng request/response giả lập, không cần khởi động HTTP server. Đây là lựa chọn phù hợp để kiểm tra endpoint Spring Data REST trong cùng application context.

**@RecordApplicationEvents** của Spring TestContext (có từ Spring Framework 5.3.3) ghi lại application events phát ra trong từng test method. Có thể nhận **ApplicationEvents** làm tham số test và đếm event theo kiểu.

Ví dụ hai kiểm thử: request sai bị từ chối và request hợp lệ phát đúng event tạo mới:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@RecordApplicationEvents
@Transactional
class PersonRestIntegrationTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private PersonRepository people;

    @Test
    void rejectsInvalidEmail() throws Exception {
        String email = "invalid-" + UUID.randomUUID() + "@example.test";

        mvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Lan",
                      "email": ""
                    }
                    """))
            .andExpect(status().isBadRequest());

        assertThat(people.existsByEmail(email)).isFalse();
    }

    @Test
    void publishesCreateEvents(ApplicationEvents events) throws Exception {
        mvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Lan",
                      "email": "lan@example.test"
                    }
                    """))
            .andExpect(status().isCreated());

        assertThat(events.stream(BeforeCreateEvent.class).count()).isEqualTo(1);
        assertThat(events.stream(AfterCreateEvent.class).count()).isEqualTo(1);
    }
}
~~~

Trong ví dụ trên, **@Transactional** ở lớp kiểm thử giúp rollback dữ liệu của từng test method sau khi test kết thúc; request MockMvc chạy trong mock environment. Nếu dùng **@SpringBootTest(webEnvironment = RANDOM_PORT)** hoặc **DEFINED_PORT**, HTTP client và server chạy ở các thread khác nhau, với transaction riêng. Transaction của test khi đó không rollback transaction đã chạy ở server. Hãy dọn dữ liệu bằng fixture/test database hoặc xác minh kết quả bằng transaction độc lập.

Khi cần kiểm tra update, tạo sẵn một **Person**, gửi **PUT** hoặc **PATCH** đến **/people/{id}**, rồi xác nhận **BeforeSaveEvent**/**AfterSaveEvent** và giá trị cuối cùng. Khi kiểm tra delete, xác nhận cặp **BeforeDeleteEvent**/**AfterDeleteEvent** và bản ghi không còn tồn tại. Đừng chỉ kiểm tra số event: hãy kiểm tra đúng domain object và trạng thái dữ liệu sau request.

## 6. Ma trận kiểm thử đề xuất

| Tình huống | Cách kích hoạt | Điều cần khẳng định |
|---|---|---|
| Tạo hợp lệ | **POST /people** với email hợp lệ | HTTP **201**; bản ghi tồn tại; có **BeforeCreateEvent** và **AfterCreateEvent** |
| Tạo không hợp lệ | **POST /people** thiếu email | HTTP lỗi client, thường **400**; không có bản ghi |
| Cập nhật hợp lệ | **PUT** hoặc **PATCH /people/{id}** | Dữ liệu đổi đúng; có **BeforeSaveEvent** và **AfterSaveEvent** |
| Cập nhật không hợp lệ | **PUT** hoặc **PATCH** với dữ liệu sai | Request bị từ chối; dữ liệu cũ vẫn nguyên vẹn |
| Lưu liên kết | Gửi request cập nhật association | Có cặp **BeforeLinkSaveEvent**/**AfterLinkSaveEvent** |
| Xóa | **DELETE /people/{id}** | Có cặp delete event; entity bị xóa |
| Runtime exception giữa workflow | Service ghi nhiều repository rồi ném exception | Mọi thay đổi trong cùng transaction đều biến mất |
| Checked exception | Service ném checked exception | Rollback khi cấu hình **rollbackFor** hoặc quy tắc mặc định toàn exception phù hợp |
| Listener sau commit | Commit hoặc rollback transaction chứa event | **AFTER_COMMIT** chỉ chạy sau commit thành công |

## 7. Khắc phục lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Validator không chạy khi POST | Sai tên bean, bean chưa được scan, **supports()** trả về **false** | Kiểm tra chính tả **beforeCreatePersonValidator**, component scan và kiểu **Person** |
| Validator chạy khi POST nhưng không chạy khi PUT/PATCH | Chỉ đăng ký hook **beforeCreate** | Đăng ký thêm validator ở **beforeSave** |
| REST trả lỗi nhưng dữ liệu vẫn tồn tại | Lỗi phát sinh sau khi transaction đã commit, hoặc exception bị bắt và nuốt | Xác định transaction boundary; để exception thoát khỏi transaction cần rollback |
| Event handler không được gọi | Handler chưa là Spring bean, annotation hoặc kiểu tham số sai | Đăng ký **@Component**/**@Bean**, kiểm tra **@RepositoryEventHandler** và tham số đầu tiên |
| Gọi repository trong unit test nhưng không thấy REST event | Đường gọi không đi qua Spring Data REST exporter | Dùng MockMvc gọi endpoint để kiểm tra REST lifecycle events |
| Runtime exception nhưng dữ liệu vẫn còn | Ghi dữ liệu nằm ngoài transaction, self-invocation, transaction manager khác hoặc exception bị nuốt | Gọi service qua proxy, kiểm tra manager/resource và đường đi của exception |
| Checked exception không rollback | Quy tắc mặc định không rollback checked exception | Dùng **@Transactional(rollbackFor = ...)** hoặc cấu hình rollback toàn exception nếu phù hợp |
| Test rollback vẫn thấy dữ liệu ở server | Test dùng **RANDOM_PORT**/**DEFINED_PORT**; request ở thread và transaction khác | Dọn dữ liệu rõ ràng hoặc xác minh qua transaction độc lập ở server |
| **AFTER_COMMIT** listener không chạy | Không có transaction đang hoạt động khi event được publish | Publish event bên trong transaction; chỉ bật **fallbackExecution** khi chấp nhận chạy ngoài transaction |

## 8. Checklist trước khi hoàn tất

- [ ] Validator hỗ trợ đúng domain type và được đăng ký đúng event (**beforeCreate**, **beforeSave**).
- [ ] Request không hợp lệ trả status lỗi client và không ghi dữ liệu.
- [ ] Request hợp lệ tạo/cập nhật/xóa đúng entity.
- [ ] Test ghi nhận đúng Spring Data REST lifecycle events cho từng thao tác.
- [ ] Handler là Spring bean và chỉ xử lý domain type dự kiến.
- [ ] Nghiệp vụ nhiều bước có transaction boundary rõ ràng.
- [ ] Runtime exception được ném ra khỏi transaction; checked exception có rollback rule nếu cần.
- [ ] Test rollback kiểm tra dữ liệu sau khi transaction kết thúc, tốt nhất từ test method không có transaction bao ngoài.
- [ ] Side effect chỉ chạy sau commit được gắn với **@TransactionalEventListener** hoặc cơ chế outbox phù hợp.
- [ ] Test HTTP dùng MockMvc hoặc test server đúng với mục tiêu; không nhầm rollback của test transaction với transaction ở server.

## 9. Tài liệu chính thức

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): đăng ký validator bằng tên bean hoặc **RepositoryRestConfigurer**.
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html): danh sách lifecycle events, **AbstractRepositoryEventListener** và **@RepositoryEventHandler**.
- [RepositoryConstraintViolationException API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/RepositoryConstraintViolationException.html): ngoại lệ được tạo khi Spring **Validator** báo lỗi.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules cho runtime, checked exception, **rollbackFor** và **noRollbackFor**.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): các phase **BEFORE_COMMIT**, **AFTER_COMMIT**, **AFTER_ROLLBACK** và **AFTER_COMPLETION**.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): kiểm thử Spring MVC qua request/response giả lập.
- [Spring Framework — Application Events in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/application-events.html): **@RecordApplicationEvents** và API **ApplicationEvents**.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): **@SpringBootTest**, mock web environment và lưu ý transaction khi dùng server port.
