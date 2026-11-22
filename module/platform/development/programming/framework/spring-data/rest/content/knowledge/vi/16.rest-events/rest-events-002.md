# BeforeCreateEvent và AfterCreateEvent khi tạo tài nguyên

## Mục tiêu

Khi client gửi HTTP POST đến collection resource của Spring Data REST, framework tạo một entity từ request body rồi lưu entity qua repository. Trong quá trình đó, Spring Data REST phát hai repository event dành riêng cho thao tác tạo mới:

- `BeforeCreateEvent`: phát trước khi entity mới được lưu lần đầu.
- `AfterCreateEvent`: phát sau khi entity mới được lưu vào repository.

Hai event cho phép ứng dụng thực hiện logic theo vòng đời tạo tài nguyên mà không cần viết lại endpoint POST. Ví dụ, `BeforeCreateEvent` có thể chuẩn hóa dữ liệu hoặc thiết lập giá trị mặc định; `AfterCreateEvent` có thể ghi log nghiệp vụ, phát application event hoặc khởi tạo công việc tiếp theo.

Bài này trình bày cách đăng ký event handler, phân biệt create event với save event, tổ chức logic trước/sau khi lưu và kiểm thử hành vi.

## 1. Vị trí của create event trong luồng POST

Giả sử repository quản lý Person được export:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Client tạo một tài nguyên:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": " An ",
  "lastName": "Nguyen",
  "email": " AN@EXAMPLE.COM "
}
~~~

Luồng xử lý khái quát:

1. Spring MVC nhận POST và Spring Data REST chọn collection resource của repository people.
2. HTTP message converter đọc JSON body và tạo entity Person.
3. Spring Data REST phát `BeforeCreateEvent` để các handler có thể xử lý entity trước khi lưu.
4. Repository thực hiện thao tác lưu entity mới.
5. Sau khi thao tác lưu hoàn tất, Spring Data REST phát `AfterCreateEvent`.
6. Spring Data REST tạo HTTP response, thường là `201 Created` và header `Location` trỏ đến URI của item mới.

Có thể hình dung:

~~~text
POST /people
      |
      v
Deserialize JSON -> Person
      |
      v
BeforeCreateEvent
      |
      v
Repository save(new entity)
      |
      v
AfterCreateEvent
      |
      v
Build HTTP response (201 Created, Location, optional body)
~~~

Create event được dùng cho entity đang được tạo lần đầu qua REST exporter. Khi cập nhật một item đã tồn tại bằng PUT hoặc PATCH, Spring Data REST dùng cặp event lưu thông thường `BeforeSaveEvent` và `AfterSaveEvent`.

## 2. BeforeCreateEvent: xử lý trước khi lưu

`BeforeCreateEvent` được phát trước lần lưu đầu tiên của entity. Handler nhận entity đã được deserialize từ request body và có thể điều chỉnh dữ liệu trước khi repository lưu.

Các việc phù hợp với giai đoạn này:

- Chuẩn hóa dữ liệu đầu vào, ví dụ trim khoảng trắng hoặc chuẩn hóa email.
- Thiết lập giá trị mặc định mà client không được tự quyết định.
- Tạo mã nghiệp vụ nếu quy tắc đó thuộc vòng đời tạo entity.
- Kiểm tra invariant đơn giản trước khi ghi.
- Gắn thông tin audit như thời điểm tạo hoặc nguồn tạo nếu ứng dụng có quy tắc rõ ràng.

Ví dụ entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private Instant createdAt;

    // constructors, getters, setters
}
~~~

Handler cho Person:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonCreateEventHandler {

    @HandleBeforeCreate
    public void handleBeforeCreate(Person person) {
        if (person.getFirstName() != null) {
            person.setFirstName(person.getFirstName().trim());
        }

        if (person.getLastName() != null) {
            person.setLastName(person.getLastName().trim());
        }

        if (person.getEmail() != null) {
            person.setEmail(
                person.getEmail().trim().toLowerCase(Locale.ROOT)
            );
        }

        if (person.getCreatedAt() == null) {
            person.setCreatedAt(Instant.now());
        }
    }
}
~~~

Trong ví dụ, dữ liệu được chuẩn hóa ngay trước khi lưu. Vì thao tác thay đổi diễn ra trước repository save, entity được lưu với giá trị đã chuẩn hóa.

Không nên dùng handler này để gọi một chuỗi dịch vụ bên ngoài kéo dài hoặc thực hiện tác vụ không liên quan đến việc chuẩn bị entity. Logic trong giai đoạn trước lưu nên ngắn, xác định và có thể kiểm soát lỗi.

## 3. AfterCreateEvent: xử lý sau khi lưu

`AfterCreateEvent` được phát sau khi entity mới đã được lưu vào repository. Đây là thời điểm phù hợp để đọc identifier do persistence provider tạo ra và khởi tạo các bước tiếp theo phụ thuộc vào entity vừa tạo.

Các trường hợp sử dụng thường gặp:

- Ghi log/audit về việc tạo tài nguyên.
- Phát application event để các thành phần khác trong ứng dụng phản ứng.
- Tạo bản ghi phụ trợ hoặc yêu cầu một tác vụ nền.
- Cập nhật cache hoặc chỉ mục tìm kiếm theo chiến lược nhất quán của ứng dụng.
- Ghi nhận ID và thông tin tài nguyên vừa được tạo.

Ví dụ mở rộng handler:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonCreateEventHandler {

    private static final Logger log =
        LoggerFactory.getLogger(PersonCreateEventHandler.class);

    private final ApplicationEventPublisher eventPublisher;

    public PersonCreateEventHandler(
            ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @HandleBeforeCreate
    public void handleBeforeCreate(Person person) {
        if (person.getEmail() != null) {
            person.setEmail(
                person.getEmail().trim().toLowerCase(Locale.ROOT)
            );
        }

        if (person.getCreatedAt() == null) {
            person.setCreatedAt(Instant.now());
        }
    }

    @HandleAfterCreate
    public void handleAfterCreate(Person person) {
        log.info("Created Person with id={}", person.getId());

        eventPublisher.publishEvent(
            new PersonCreatedEvent(person.getId(), person.getEmail())
        );
    }
}
~~~

Application event của ứng dụng:

~~~java
public record PersonCreatedEvent(Long personId, String email) {
}
~~~

Event handler của Spring Data REST nhận entity Person; sau khi lưu, ID được sinh có thể đã có trên entity. Application event riêng giúp tách phần tích hợp tiếp theo khỏi handler REST.

Nếu ứng dụng chỉ cần ghi log hoặc cập nhật một trạng thái nội bộ nhỏ, có thể thực hiện trực tiếp trong handler. Nếu cần gửi email, gọi HTTP service, đẩy message broker hoặc chạy tác vụ lâu, nên chuyển công việc sang cơ chế xử lý nền phù hợp thay vì giữ request POST chờ toàn bộ công việc hoàn tất.

## 4. Đăng ký @RepositoryEventHandler

`@RepositoryEventHandler` đánh dấu một bean có các method xử lý repository event. Có hai cách phổ biến để đăng ký bean.

### 4.1. Dùng @Component

Cách đơn giản:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonCreateEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        // chuẩn hóa dữ liệu trước khi lưu
    }

    @HandleAfterCreate
    public void afterCreate(Person person) {
        // xử lý sau khi lưu
    }
}
~~~

Spring Boot component scanning phát hiện bean và Spring Data REST đăng ký các method handler tương ứng.

### 4.2. Khai báo bean bằng @Bean

Nếu muốn quản lý handler trong configuration:

~~~java
@Configuration
public class RepositoryEventConfiguration {

    @Bean
    PersonCreateEventHandler personCreateEventHandler(
            ApplicationEventPublisher publisher) {
        return new PersonCreateEventHandler(publisher);
    }
}
~~~

Không cần khai báo đồng thời cả `@Component` và một `@Bean` thứ hai cho cùng handler, vì có thể tạo hai bean và khiến cùng logic được gọi nhiều lần.

Điều quan trọng là handler phải thực sự tồn tại trong Spring ApplicationContext. Chỉ thêm annotation vào một class không được component scan hoặc không được khai báo thành bean thì chưa đủ để Spring Data REST gọi method.

## 5. Phân biệt handler theo domain type

Spring Data REST xác định domain type cần xử lý từ kiểu tham số đầu tiên của method có annotation event handler. Có thể giới hạn ngay ở cấp class:

~~~java
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        // chỉ xử lý Person
    }

    @HandleAfterCreate
    public void afterCreate(Person person) {
        // chỉ xử lý Person
    }
}
~~~

Hoặc dùng một handler cho nhiều domain type:

~~~java
@RepositoryEventHandler
public class CreateEventHandler {

    @HandleBeforeCreate
    public void beforeCreatePerson(Person person) {
        // xử lý Person
    }

    @HandleBeforeCreate
    public void beforeCreateOrder(Order order) {
        // xử lý Order
    }

    @HandleAfterCreate
    public void afterCreatePerson(Person person) {
        // xử lý Person sau khi lưu
    }
}
~~~

Với handler không giới hạn ở class level, kiểu tham số của từng method cho biết domain type tương ứng. Cách này hữu ích khi nhiều entity dùng chung một nhóm quy tắc. Nếu logic của các entity khác nhau đáng kể, nên tách handler để mỗi class có phạm vi và trách nhiệm rõ ràng.

## 6. Annotation create event và các event khác

Spring Data REST REST exporter phát nhiều event trong vòng đời entity:

| Event | Thời điểm | Mục đích |
|---|---|---|
| `BeforeCreateEvent` | Trước lần lưu đầu tiên | Chuẩn bị entity mới |
| `AfterCreateEvent` | Sau khi entity mới được lưu | Phản ứng sau thao tác tạo |
| `BeforeSaveEvent` | Trước khi lưu entity đã tồn tại | Chuẩn bị dữ liệu cập nhật |
| `AfterSaveEvent` | Sau thao tác lưu entity | Phản ứng sau cập nhật/lưu |
| `BeforeLinkSaveEvent` | Trước khi lưu liên kết association | Xử lý thay đổi quan hệ |
| `AfterLinkSaveEvent` | Sau khi lưu liên kết association | Phản ứng sau thay đổi quan hệ |
| `BeforeDeleteEvent` | Trước khi xóa entity | Kiểm tra hoặc chuẩn bị xóa |
| `AfterDeleteEvent` | Sau khi xóa entity | Ghi nhận hoặc xử lý sau xóa |

Các annotation handler tương ứng gồm `@HandleBeforeCreate`, `@HandleAfterCreate`, `@HandleBeforeSave`, `@HandleAfterSave`, `@HandleBeforeLinkSave`, `@HandleAfterLinkSave`, `@HandleBeforeDelete` và `@HandleAfterDelete`.

Phân biệt create và save rất quan trọng:

- POST đến collection tạo một entity mới, nên dùng cặp BeforeCreate/AfterCreate.
- PUT hoặc PATCH đến item hiện có cập nhật entity, nên dùng cặp BeforeSave/AfterSave.
- Thay đổi association có thể phát link save event riêng.

Không nên dùng `@HandleBeforeSave` để thay thế mọi logic tạo mới nếu nghiệp vụ chỉ áp dụng lúc tạo. Tách đúng event giúp tránh chạy lại logic tạo mã, thiết lập thời gian tạo hoặc gửi thông báo tạo mới khi entity chỉ được cập nhật.

## 7. Cách khác: AbstractRepositoryEventListener

Ngoài annotation handler, Spring Data REST cung cấp `AbstractRepositoryEventListener<T>`. Có thể kế thừa class này và override các callback cần thiết:

~~~java
@Component
public class PersonRepositoryEventListener
        extends AbstractRepositoryEventListener<Person> {

    @Override
    protected void onBeforeCreate(Person person) {
        if (person.getEmail() != null) {
            person.setEmail(
                person.getEmail().trim().toLowerCase(Locale.ROOT)
            );
        }
    }

    @Override
    protected void onAfterCreate(Person person) {
        // xử lý sau khi tạo
    }
}
~~~

Cách này phù hợp khi muốn xử lý event thông qua một listener class và override callback theo vòng đời repository. Listener generic có thể giới hạn domain type qua tham số kiểu.

Một listener tổng quát không phân biệt domain type ở từng callback nếu dùng kiểu Object hoặc listener không được giới hạn phù hợp; khi đó cần tự kiểm tra kiểu entity. Annotation handler thường dễ đọc hơn khi cần xử lý nhiều domain type bằng các method type-safe riêng.

Không cần dùng đồng thời cả annotation handler và AbstractRepositoryEventListener cho cùng một nghiệp vụ. Chọn một cách triển khai để tránh xử lý trùng.

## 8. Event handler và transaction boundary

Tên `AfterCreateEvent` có nghĩa là repository save operation đã hoàn tất và Spring Data REST phát event sau thao tác đó. Nó không nên được hiểu mặc định là một cam kết rằng transaction database đã commit thành công trong mọi cấu hình.

Spring Data REST event là Spring application event và mặc định được phát đồng bộ. Vì vậy, handler thường chạy trong luồng xử lý request. Nếu handler thực hiện công việc chậm, thời gian phản hồi POST cũng tăng theo.

Với tác vụ cần chỉ chạy sau khi transaction commit, hãy thiết kế transaction boundary rõ ràng. Có thể phát application event trong transaction rồi dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` khi event được phát trong một transaction đang hoạt động. Cơ chế này chỉ có ý nghĩa khi có transaction phù hợp; nếu event được phát sau khi transaction repository đã kết thúc, không thể giả định listener sẽ tự có một transaction trước đó để chờ commit.

Với tích hợp quan trọng cần bảo đảm không mất message khi ứng dụng dừng giữa lúc ghi database và gửi message, cân nhắc transactional outbox: ghi dữ liệu nghiệp vụ và outbox record trong cùng transaction, sau đó một worker phát message từ outbox. Đây là quyết định kiến trúc ở tầng ứng dụng, không phải bảo đảm tự động của `AfterCreateEvent`.

Đối với tác vụ nền không yêu cầu ràng buộc commit, có thể publish application event và xử lý bất đồng bộ bằng listener được cấu hình `@Async` cùng executor phù hợp. Cần xác định rõ cách xử lý lỗi, retry và quan sát tác vụ vì lỗi trong worker không còn được trả trực tiếp cho request POST.

## 9. Validation và xử lý lỗi trước khi tạo

Nếu entity không hợp lệ, nên chặn thao tác trước khi repository lưu dữ liệu. Có thể thực hiện kiểm tra invariant trong `@HandleBeforeCreate` hoặc dùng cơ chế validation của Spring Data REST/Spring Validation.

Ví dụ chuẩn hóa và kiểm tra điều kiện nghiệp vụ:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonCreateEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        if (person.getEmail() == null || person.getEmail().isBlank()) {
            throw new InvalidPersonException("Email is required");
        }

        person.setEmail(
            person.getEmail().trim().toLowerCase(Locale.ROOT)
        );
    }
}
~~~

Ví dụ exception:

~~~java
public class InvalidPersonException extends RuntimeException {
    public InvalidPersonException(String message) {
        super(message);
    }
}
~~~

Ứng dụng cần cấu hình exception handling phù hợp để chuyển lỗi nghiệp vụ thành HTTP response nhất quán. Không nên để handler tự bắt rồi bỏ qua exception, vì request có thể tiếp tục lưu entity không hợp lệ.

Với validation theo annotation như `@NotBlank`, `@Email` hoặc custom constraint, hãy cấu hình Bean Validation và Spring Data REST validator đúng cách. Event handler có thể bổ sung kiểm tra phụ thuộc ngữ cảnh tạo, nhưng không nên nhân bản toàn bộ validation framework trong từng handler.

## 10. Kiểm thử BeforeCreateEvent và AfterCreateEvent

Nên kiểm tra qua HTTP POST thật trong integration test để xác nhận Spring Data REST đã nhận request, gọi đúng event và lưu entity.

Ví dụ kiểm thử kết quả chuẩn hóa trước khi lưu:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonCreateEventTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    PersonRepository repository;

    @BeforeEach
    void cleanDatabase() {
        repository.deleteAll();
    }

    @Test
    void beforeCreateNormalizesEmailBeforeSaving() throws Exception {
        mvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaTypes.HAL_JSON)
                .content("""
                    {
                      "firstName": " An ",
                      "lastName": " Nguyen ",
                      "email": " AN@EXAMPLE.COM "
                    }
                    """))
            .andExpect(status().isCreated());

        Person saved = repository.findAll().iterator().next();

        assertThat(saved.getFirstName()).isEqualTo("An");
        assertThat(saved.getLastName()).isEqualTo("Nguyen");
        assertThat(saved.getEmail()).isEqualTo("an@example.com");
        assertThat(saved.getCreatedAt()).isNotNull();
    }
}
~~~

Để kiểm tra AfterCreateEvent, có thể spy handler hoặc đăng ký một test listener nhận application event. Ví dụ dùng Mockito spy trong test context:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class AfterCreateEventTests {

    @Autowired
    MockMvc mvc;

    @SpyBean
    PersonCreateEventHandler handler;

    @Test
    void postInvokesAfterCreateHandler() throws Exception {
        mvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaTypes.HAL_JSON)
                .content("""
                    {
                      "firstName": "An",
                      "lastName": "Nguyen",
                      "email": "an@example.com"
                    }
                    """))
            .andExpect(status().isCreated());

        verify(handler).handleAfterCreate(any(Person.class));
    }
}
~~~

Tên method spy phải khớp với method thực tế trong handler. Tùy phiên bản Spring Boot, `@SpyBean` có thể được thay bằng cơ chế Mockito bean override tương ứng. Mỗi test cần dữ liệu riêng hoặc cleanup để không phụ thuộc thứ tự chạy.

Các điểm nên xác nhận:

- POST tạo đúng một entity mới.
- BeforeCreate handler chạy trước khi dữ liệu được lưu.
- Giá trị đã chuẩn hóa xuất hiện trong repository sau POST.
- AfterCreate handler nhận entity có ID đã được lưu.
- PUT/PATCH không vô tình gọi create handler.
- Nếu handler phát application event, listener tiếp theo nhận đúng payload.
- Lỗi validation trước lưu không tạo entity mới.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Handler không được gọi | Bean không nằm trong ApplicationContext | Dùng @Component hoặc khai báo @Bean và kiểm tra component scan |
| Handler chạy cho sai entity | Thiếu domain type restriction hoặc kiểu tham số không đúng | Dùng @RepositoryEventHandler(Person.class) và tham số Person |
| Logic tạo mới chạy khi PUT/PATCH | Đặt logic vào BeforeSave/AfterSave hoặc service dùng chung | Chuyển logic chỉ dành cho tạo sang BeforeCreate/AfterCreate |
| Email vẫn lưu chữ hoa/khoảng trắng | Chuẩn hóa sau repository save hoặc handler không được đăng ký | Đặt thay đổi trong BeforeCreate và kiểm thử dữ liệu đã lưu |
| ID chưa có trong BeforeCreate | Entity chưa được lưu nên ID do database sinh chưa có | Dùng AfterCreate cho logic cần ID đã sinh |
| Gửi message nhưng database rollback | Nhầm AfterCreate với transaction after-commit | Xác định transaction boundary; dùng after-commit hoặc outbox khi cần |
| POST chậm bất thường | AfterCreate handler thực hiện tác vụ đồng bộ kéo dài | Chuyển tác vụ phù hợp sang xử lý nền |
| Một nghiệp vụ chạy hai lần | Cùng logic được đăng ký qua nhiều handler/listener | Chỉ đăng ký một cơ chế cho mỗi nghiệp vụ và kiểm tra số bean |
| Handler nuốt exception | Bắt lỗi nhưng không xử lý hoặc báo lại | Để lỗi được chuyển đến exception handling phù hợp |
| Test không ổn định | Phụ thuộc ID tự sinh hoặc dữ liệu còn từ test trước | Tạo fixture riêng, cleanup và lấy URI từ response |

## 12. Checklist triển khai create event

- Xác định thao tác nào thực sự là tạo mới qua POST collection resource.
- Dùng `@HandleBeforeCreate` cho logic cần chạy trước lần lưu đầu tiên.
- Dùng `@HandleAfterCreate` cho logic cần entity sau khi save hoàn tất.
- Đăng ký handler thành Spring bean bằng `@Component` hoặc `@Bean`.
- Giới hạn domain type bằng `@RepositoryEventHandler(Entity.class)` khi phù hợp.
- Giữ handler ngắn và tránh gọi dịch vụ bên ngoài đồng bộ nếu không cần.
- Phân biệt create event với before/after save event của PUT/PATCH.
- Không coi AfterCreateEvent là cam kết transaction đã commit.
- Dùng after-commit hoặc transactional outbox khi tác vụ phụ thuộc vào commit bền vững.
- Kiểm thử cả dữ liệu trước lưu, dữ liệu sau lưu và trường hợp lỗi.
- Tránh đăng ký đồng thời nhiều handler thực hiện cùng một nghiệp vụ.

## Kết luận

`BeforeCreateEvent` và `AfterCreateEvent` cho phép mở rộng vòng đời POST của Spring Data REST. BeforeCreate chạy trước khi entity mới được lưu, phù hợp để chuẩn hóa dữ liệu, thiết lập mặc định và kiểm tra invariant. AfterCreate chạy sau thao tác lưu, phù hợp để ghi nhận entity đã tạo và phát application event cho bước tiếp theo. Đăng ký handler bằng `@RepositoryEventHandler` cùng `@HandleBeforeCreate`/`@HandleAfterCreate` giúp logic được giới hạn theo domain type. Hãy phân biệt create event với save event của cập nhật, quản lý transaction boundary rõ ràng và kiểm thử qua HTTP POST để xác nhận đúng vòng đời.

## Tài liệu tham khảo

- Spring Data REST – Events: https://docs.spring.io/spring-data/rest/reference/events.html
- Spring Data REST – Event package API (BeforeCreateEvent, AfterCreateEvent, AbstractRepositoryEventListener): https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/event/package-summary.html
- Spring Framework – Transaction-bound events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
