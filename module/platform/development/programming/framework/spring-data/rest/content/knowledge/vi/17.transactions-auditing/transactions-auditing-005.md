# Rollback, lỗi listener và tác động đến dữ liệu đã thay đổi

## Mục tiêu

Spring Data REST phát repository event trong quá trình tạo, cập nhật, thay đổi association và xóa tài nguyên. Listener có thể chuẩn hóa entity, ghi audit hoặc kích hoạt xử lý tiếp theo. Tuy nhiên, listener ném exception không đồng nghĩa mọi thay đổi trước đó trong request đều tự động được rollback.

Để xử lý đúng lỗi, cần xác định ba điều:

- Event được phát ở thời điểm nào so với lời gọi repository.
- Transaction database nào đang hoạt động khi listener chạy.
- Thay đổi đã thực hiện là thay đổi trong database, trong entity đang nằm trong bộ nhớ hay side effect ở hệ thống bên ngoài.

Bài này tập trung vào rollback và lỗi listener trong Spring Data REST, đặc biệt là khác biệt giữa `Before*` và `After*` event. Quy tắc chính là: transaction chỉ rollback những thao tác tham gia transaction đó; exception không thể tự hoàn tác email đã gửi, HTTP call đã thực hiện hoặc một transaction khác đã commit.

## 1. Luồng event và vị trí có thể phát sinh lỗi

Với repository Person được export:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Một request tạo mới đi theo luồng khái quát:

~~~text
POST /people
      |
      v
Deserialize request body thành Person
      |
      v
BeforeCreateEvent
      |
      v
repository.save(person)
      |
      v
AfterCreateEvent
      |
      v
Tạo HTTP response
~~~

Với cập nhật item, Spring Data REST dùng cặp `BeforeSaveEvent` và `AfterSaveEvent`. Với xóa, framework phát `BeforeDeleteEvent` và `AfterDeleteEvent`. Thay đổi association có các event link save tương ứng.

Vị trí của exception rất quan trọng:

- Exception trong `BeforeCreateEvent` xảy ra trước lời gọi lưu entity mới. Luồng xử lý dừng và repository save của thao tác POST chưa được gọi.
- Exception trong lời gọi `repository.save(...)` có thể làm transaction của thao tác lưu rollback.
- Exception trong `AfterCreateEvent` xảy ra sau khi lời gọi repository save trả về. Nếu repository save đã chạy trong transaction riêng và transaction đó đã commit, exception ở listener không thể rollback transaction đã kết thúc.
- Nếu có một transaction bên ngoài bao trùm toàn bộ request và repository save tham gia transaction đó, exception ở After event vẫn có thể làm transaction bên ngoài rollback.

Vì vậy, không thể chỉ nhìn tên event hoặc HTTP status để kết luận dữ liệu đã được commit hay chưa. Phải kiểm tra transaction boundary thực tế của ứng dụng.

## 2. Before event: lỗi trước khi repository lưu

Các event như `BeforeCreateEvent`, `BeforeSaveEvent` và `BeforeDeleteEvent` được phát trước thao tác repository tương ứng.

Ví dụ handler từ chối tạo Person:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonCreateHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        if (person.getEmail() == null
                || person.getEmail().isBlank()) {
            throw new IllegalArgumentException("Email is required");
        }
    }
}
~~~

Khi handler ném exception:

1. Việc publish event truyền lỗi trở lại luồng xử lý request theo cơ chế event đồng bộ mặc định.
2. Spring Data REST không tiếp tục đến repository save trong luồng tạo tài nguyên đó.
3. Entity đang được dựng từ request không được lưu bởi thao tác POST này.
4. Request kết thúc bằng lỗi được exception handling của ứng dụng ánh xạ thành HTTP response.

Với cấu hình mặc định, một runtime exception không được xử lý có thể trở thành HTTP 500. Nếu ứng dụng có exception resolver, `@ControllerAdvice` hoặc Spring Data REST exception mapping riêng, status và response body có thể khác. Hãy định nghĩa mapping cho lỗi nghiệp vụ nếu client cần nhận 400, 409 hoặc status cụ thể.

### 2.1. Thay đổi trong bộ nhớ không phải là thay đổi đã commit

Handler có thể sửa entity trước khi ném exception:

~~~java
@HandleBeforeCreate
public void beforeCreate(Person person) {
    person.setEmail(person.getEmail().trim().toLowerCase(Locale.ROOT));

    if (person.getEmail().endsWith("@blocked.example")) {
        throw new IllegalArgumentException("Email domain is not allowed");
    }
}
~~~

Sau khi exception thoát ra, entity trong bộ nhớ đã có email chuẩn hóa, nhưng repository save chưa được gọi. Nếu không có một thao tác ghi khác, thay đổi đó không trở thành dữ liệu database.

Không nên dùng lại object vừa tham gia một request thất bại như thể nó có trạng thái persistence bình thường. Hãy tải lại dữ liệu từ repository khi cần trạng thái đáng tin cậy.

### 2.2. Before listener vẫn có thể tạo side effect riêng

Việc repository save chưa xảy ra không có nghĩa mọi tác động trong listener đều tự biến mất. Ví dụ listener có thể:

- Ghi một audit record bằng repository khác.
- Gọi dịch vụ bên ngoài.
- Gửi email hoặc message.
- Ghi file hoặc cập nhật cache.

Nếu những thao tác này dùng transaction riêng hoặc không tham gia transaction của entity đang tạo, chúng có thể tồn tại dù thao tác tạo Person bị dừng. Vì vậy, không nên thực hiện side effect không thể đảo ngược trong Before listener trước khi biết thao tác chính có thể commit hay không.

## 3. Lỗi trong repository save: transaction có thể rollback

Các phương thức CRUD ghi dữ liệu của Spring Data JPA thường chạy trong transaction do repository implementation quản lý. Khi thao tác lưu gặp runtime exception hoặc lỗi ở bước flush/commit, transaction tương ứng được rollback.

Ví dụ:

~~~java
@Transactional
public Person createPerson(Person person) {
    return personRepository.save(person);
}
~~~

Nếu lỗi constraint hoặc lỗi persistence xảy ra trong transaction này, các thay đổi database thuộc transaction sẽ không được commit. Một số lỗi chỉ xuất hiện lúc flush hoặc commit, dù lời gọi `save()` đã được thực hiện trước đó.

Mặc định của Spring transaction là rollback với `RuntimeException` và `Error`; checked exception không tự động kích hoạt rollback nếu không cấu hình `rollbackFor` phù hợp:

~~~java
@Transactional(rollbackFor = Exception.class)
public Person createPerson(Person person) throws Exception {
    // các thao tác database cần cùng thành công hoặc cùng rollback
}
~~~

Quy tắc rollback chỉ áp dụng khi exception đi qua transaction interceptor và transaction chưa commit. Nếu code bắt exception rồi không ném lại, transaction có thể tiếp tục commit, trừ khi đã được đánh dấu rollback-only hoặc có lỗi persistence khiến transaction không thể commit.

Với JPA, sau một lỗi persistence, transaction có thể đã bị đánh dấu rollback-only. Không nên bắt exception rồi tiếp tục ghi thêm trong cùng transaction với giả định persistence context vẫn an toàn.

## 4. After event: lỗi listener có thể xảy ra sau commit

Ví dụ handler:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonAfterCreateHandler {

    @HandleAfterCreate
    public void afterCreate(Person person) {
        auditService.recordCreated(person.getId());
        throw new IllegalStateException("Audit processing failed");
    }
}
~~~

Trong luồng Spring Data REST thông thường, event After được phát sau khi lời gọi repository save trả về. Với repository JPA dùng transaction của chính phương thức save và không có transaction bên ngoài, transaction save có thể đã commit trước khi After handler được gọi.

Khi đó có thể xảy ra tình huống:

1. Person được insert và transaction save commit thành công.
2. Spring Data REST phát `AfterCreateEvent`.
3. Listener ném exception.
4. Client nhận HTTP error thay vì response tạo mới dự kiến.
5. Bản ghi Person vẫn tồn tại trong database.

Đây là lý do HTTP 500 không phải bằng chứng rằng POST đã rollback. Client có thể retry request sau khi thấy lỗi và vô tình tạo bản ghi trùng.

Tình huống trên phụ thuộc transaction boundary thực tế. Nếu controller/service hoặc cấu hình ứng dụng đã mở một transaction bên ngoài bao trùm cả repository save và event dispatch, After listener vẫn chạy bên trong transaction đó; exception có thể làm transaction bên ngoài rollback. Không nên giả định có transaction bao trùm request nếu ứng dụng chưa cấu hình rõ.

### 4.1. After event không phải transaction after-commit event

Tên `AfterCreateEvent` có nghĩa là event được phát sau thao tác create/save của repository trong luồng Spring Data REST. Nó không đồng nghĩa với Spring transaction phase `AFTER_COMMIT`.

Hai khái niệm cần tách biệt:

- `AfterCreateEvent`: repository lifecycle event do Spring Data REST phát sau lời gọi lưu entity.
- `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`: listener của application event được gọi sau khi transaction đang chứa event publish commit thành công.

Nếu event được publish khi không có transaction đang hoạt động, transactional event listener mặc định không được gọi vì không có transaction phase để gắn vào. Do đó, không chỉ đổi tên hoặc thêm `@TransactionalEventListener` lên một listener mà không xác định nơi event được publish và transaction nào đang hoạt động.

## 5. Bảng tác động theo vị trí lỗi

| Vị trí lỗi | Repository save đã được gọi? | Dữ liệu entity có thể đã commit? | Điều cần kiểm tra |
|---|---|---|---|
| `BeforeCreateEvent` ném lỗi | Chưa | Không từ thao tác POST đó | Listener có ghi dữ liệu hoặc tạo side effect riêng không |
| `BeforeSaveEvent` ném lỗi | Chưa gọi save cho lần cập nhật đó | Không từ lần save đó | Có transaction ngoài hoặc thao tác phụ trước đó không |
| Trong `repository.save()` | Có | Thường không nếu transaction rollback thành công | Runtime/checked exception, flush, commit và rollback rule |
| `AfterCreateEvent` ném lỗi | Đã gọi và trả về | Có thể đã commit nếu save transaction kết thúc độc lập | Có transaction ngoài bao trùm request không |
| `AfterSaveEvent` ném lỗi | Đã gọi và trả về | Có thể đã commit nếu save transaction kết thúc độc lập | Transaction boundary và side effect của listener |
| `AfterDeleteEvent` ném lỗi | Lệnh xóa đã chạy | Bản ghi có thể đã bị xóa và commit | Kiểm tra lại bằng repository/database |
| External API/email/message lỗi | Tùy thời điểm | Database có thể đã commit hoặc chưa | Hệ thống ngoài có hỗ trợ retry/idempotency không |

Bảng này mô tả luồng repository CRUD thông thường. Custom transaction ở controller/service, propagation, transaction manager và loại datastore có thể thay đổi kết quả. Khi cần bảo đảm nguyên tử, phải thiết kế transaction boundary rõ ràng thay vì dựa vào tên event.

## 6. Nhiều listener và lỗi đồng bộ

Spring application event được phát đồng bộ theo mặc định nếu ứng dụng không cấu hình một event multicaster bất đồng bộ. Vì vậy, handler thường chạy trong luồng xử lý request.

Nếu một listener ném exception không được xử lý:

- Exception có thể truyền ngược đến nơi publish event và làm request thất bại.
- Các listener được gọi sau listener lỗi có thể không được thực thi với multicaster mặc định không có ErrorHandler.
- Những listener đã chạy trước đó có thể đã ghi dữ liệu hoặc tạo side effect.
- Không có cơ chế tự động undo các listener đã chạy.

Nếu ứng dụng cấu hình event multicaster với ErrorHandler hoặc xử lý lỗi riêng, hành vi tiếp tục/gửi lỗi có thể khác. Hãy kiểm tra cấu hình thực tế nếu có nhiều listener phụ thuộc thứ tự.

Không nên dựa vào thứ tự ngẫu nhiên giữa các listener để thực hiện chuỗi nghiệp vụ quan trọng. Nếu bước B chỉ được chạy sau khi bước A thành công, hãy gọi chúng từ một service điều phối có transaction và quy tắc lỗi rõ ràng, hoặc dùng workflow/message processing có trạng thái.

## 7. @Transactional trên listener không tự bao trùm toàn bộ request

Thêm `@Transactional` vào event handler chỉ tạo hoặc tham gia transaction cho lời gọi handler theo propagation được cấu hình. Nó không tự động kéo repository save trước đó vào cùng một transaction.

Ví dụ:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonAfterCreateHandler {

    private final AuditRepository auditRepository;

    public PersonAfterCreateHandler(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional
    @HandleAfterCreate
    public void afterCreate(Person person) {
        auditRepository.save(
            new AuditRecord("PERSON_CREATED", person.getId())
        );
    }
}
~~~

Nếu không có transaction bên ngoài, transaction của handler có thể bắt đầu sau khi transaction save Person đã kết thúc. Khi audit insert lỗi, audit transaction rollback nhưng Person đã commit vẫn còn.

Nếu dùng `Propagation.REQUIRES_NEW`, transaction listener được tách riêng một cách chủ ý. Nó có thể commit độc lập và không bị rollback cùng transaction bên ngoài. Điều này hữu ích cho một số loại audit độc lập, nhưng không phù hợp nếu yêu cầu là audit và entity phải cùng thành công hoặc cùng thất bại.

Ngược lại, `Propagation.REQUIRED` chỉ tham gia transaction hiện có nếu có; nếu không có thì nó mở transaction mới. Cần xác định transaction nào đang hoạt động tại thời điểm event được phát.

## 8. Cách thiết kế để dữ liệu và audit cùng nhất quán

Nếu yêu cầu nghiệp vụ là tạo entity và ghi audit record phải cùng commit hoặc cùng rollback, hãy đặt cả hai thao tác trong một service method có transaction bao trùm:

~~~java
@Service
public class PersonCreationService {

    private final PersonRepository personRepository;
    private final AuditRepository auditRepository;

    public PersonCreationService(
            PersonRepository personRepository,
            AuditRepository auditRepository) {
        this.personRepository = personRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Person create(Person person) {
        Person saved = personRepository.save(person);

        auditRepository.save(
            new AuditRecord("PERSON_CREATED", saved.getId())
        );

        return saved;
    }
}
~~~

Trong cùng transaction manager và cùng transaction, nếu lưu audit record thất bại với lỗi làm rollback, thao tác tạo Person cũng rollback. Để bảo đảm endpoint sử dụng service này, cần cho request đi qua service method đó, ví dụ bằng custom controller hoặc luồng nghiệp vụ được ứng dụng điều phối. Chỉ khai báo service không làm cho POST mặc định của Spring Data REST tự động gọi nó.

Nếu muốn tiếp tục dùng repository event handler, cần hiểu rằng một handler chạy trước hoặc sau lời gọi repository không mặc nhiên tạo transaction bao trùm cả hai phía. Đừng giả định một `@Transactional` đặt riêng trên listener sẽ bảo đảm tính nguyên tử giữa entity và audit.

## 9. Side effect bên ngoài và transactional outbox

Database rollback không thể hoàn tác các hành động đã xảy ra ở hệ thống ngoài transaction:

- Email đã được gửi.
- HTTP request đã đến dịch vụ khác.
- Message đã được broker xác nhận.
- File đã được ghi.
- Cache ở hệ thống khác đã được cập nhật.

Ví dụ, BeforeCreate listener gửi email rồi repository save gặp lỗi constraint. Database không có Person mới, nhưng email đã rời khỏi hệ thống. Tương tự, AfterCreate listener có thể gửi webhook thành công rồi một bước khác làm transaction bên ngoài rollback.

Với tích hợp cần độ tin cậy cao, transactional outbox là lựa chọn phổ biến:

1. Trong cùng transaction tạo entity, ghi thêm một outbox record mô tả sự kiện cần phát.
2. Commit entity và outbox record cùng nhau.
3. Một worker đọc các outbox record chưa xử lý và gửi message/webhook.
4. Sau khi gửi thành công, worker đánh dấu record đã xử lý.
5. Nếu worker lỗi, retry theo chính sách; consumer cần xử lý idempotent để tránh tác động trùng.

Ví dụ cấu trúc đơn giản:

~~~java
@Transactional
public Person create(Person person) {
    Person saved = personRepository.save(person);

    outboxRepository.save(
        OutboxMessage.personCreated(saved.getId())
    );

    return saved;
}
~~~

Nếu transaction rollback, cả Person và outbox record đều không được commit. Nếu transaction commit, worker có thể tiếp tục phát message kể cả khi ứng dụng dừng ngay sau đó.

Outbox không tự bảo đảm message chỉ được gửi đúng một lần. Worker có thể gửi thành công nhưng chết trước khi đánh dấu đã xử lý, nên consumer và thao tác gửi cần có idempotency key hoặc cơ chế chống trùng phù hợp.

## 10. Cách xử lý lỗi và trả HTTP response

Không nên nuốt exception trong listener chỉ để request luôn trả thành công:

~~~java
@HandleAfterCreate
public void afterCreate(Person person) {
    try {
        notificationService.send(person);
    } catch (Exception ex) {
        log.error("Notification failed", ex);
        // Không âm thầm coi side effect quan trọng là đã thành công.
    }
}
~~~

Nếu thông báo là tác vụ phụ có thể retry, hãy ghi nhận trạng thái lỗi và chuyển sang worker/outbox. Nếu thông báo là điều kiện bắt buộc để nghiệp vụ được xem là thành công, hãy đưa nó vào một workflow có trạng thái và compensation rõ ràng; không dựa vào việc ném exception từ After listener để rollback một insert đã commit.

Đối với lỗi nghiệp vụ trước lưu, dùng exception có ý nghĩa và ánh xạ sang response phù hợp. Ví dụ:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(InvalidPersonException.class)
    ResponseEntity<ProblemDetail> handleInvalidPerson(
            InvalidPersonException ex) {

        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);

        problem.setDetail(ex.getMessage());

        return ResponseEntity.badRequest().body(problem);
    }
}
~~~

Đây là ví dụ cho Controller advice của ứng dụng; phạm vi áp dụng và định dạng response cần kiểm tra khi dùng chung với Spring Data REST. Không phải mọi exception từ listener đều nên trả 400. Phân loại lỗi validation, conflict, lỗi hệ thống và lỗi tích hợp theo hợp đồng API.

## 11. Kiểm thử rollback và dữ liệu còn lại sau lỗi

Cần kiểm thử bằng integration test với database phù hợp và xác nhận trạng thái repository sau request. Hai trường hợp quan trọng là Before listener lỗi và After listener lỗi.

Ví dụ kiểm tra BeforeCreate thất bại:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonCreateRollbackTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    PersonRepository repository;

    @Test
    void beforeCreateFailureDoesNotSavePerson() throws Exception {
        mvc.perform(post("/people")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "firstName": "An",
                      "email": "blocked@example.com"
                    }
                    """))
            .andExpect(status().is5xxServerError());

        assertThat(repository.findByEmail("blocked@example.com"))
            .isEmpty();
    }
}
~~~

Status ở ví dụ cần điều chỉnh theo exception mapping thực tế. Điều cần kiểm tra là entity không được lưu bởi POST đã bị chặn trước repository save.

Với After listener, nếu không có transaction ngoài bao trùm request, cần kiểm tra khả năng dữ liệu đã commit dù response là lỗi:

~~~java
@Test
void afterCreateFailureMayLeaveCommittedPerson() throws Exception {
    mvc.perform(post("/people")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "firstName": "An",
                  "email": "after-error@example.com"
                }
                """))
        .andExpect(status().is5xxServerError());

    assertThat(repository.findByEmail("after-error@example.com"))
        .isPresent();
}
~~~

Test này chỉ đúng với cấu hình transaction mà repository save commit trước khi After listener lỗi. Nếu ứng dụng có outer transaction bao trùm event dispatch, kỳ vọng có thể là rollback và cần test theo cấu hình đó.

**Tránh đặt `@Transactional` trên test method khi đang kiểm tra ranh giới transaction thực tế của request.** Transaction test có thể được gắn vào cùng thread và làm repository save tham gia transaction của test. Khi đó After listener chạy trước lúc test transaction kết thúc; kết quả có thể khác request production không có transaction bên ngoài. Nếu test cần transaction riêng, dùng transaction template hoặc một request chạy qua server/thread độc lập và xác minh dữ liệu sau khi request hoàn tất.

Các test nên bao gồm:

- Before listener ném lỗi: xác nhận repository save chưa tạo entity.
- Repository save gặp lỗi constraint: xác nhận thay đổi trong transaction được rollback.
- After listener ném lỗi: xác nhận status HTTP và kiểm tra database có thể đã giữ entity.
- Listener ghi audit trong transaction riêng: xác nhận audit có thể tồn tại độc lập.
- Side effect được chuyển qua outbox: xác nhận entity và outbox record cùng commit/rollback.
- Retry request sau response lỗi: xác nhận có cơ chế idempotency hoặc chống tạo trùng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| POST trả 500 nhưng entity vẫn tồn tại | AfterCreate listener lỗi sau khi repository save đã commit | Kiểm tra database; không kết luận rollback từ HTTP status |
| BeforeCreate lỗi nhưng có audit record | Listener ghi audit bằng transaction độc lập trước khi từ chối tạo | Đưa audit vào transaction chung hoặc xác định rõ audit thất bại |
| Bắt exception rồi dữ liệu vẫn commit | Exception bị nuốt hoặc không đánh dấu transaction rollback-only | Ném lại lỗi hoặc cấu hình rollback rule phù hợp |
| Checked exception không rollback | Spring mặc định rollback RuntimeException/Error | Dùng rollbackFor khi transaction cần rollback với checked exception |
| Email/webhook vẫn được gửi dù database rollback | Side effect bên ngoài không tham gia transaction database | Dùng outbox hoặc after-commit workflow |
| Audit lỗi nhưng entity đã lưu | Audit chạy trong transaction riêng sau repository save | Dùng service transaction bao trùm entity và audit nếu cần atomicity |
| Test cho thấy After listener rollback nhưng production không rollback | Test method có transaction bao trùm MockMvc request | Kiểm thử không có transaction ngoài hoặc dùng server/thread độc lập |
| Listener sau không được chạy | Listener trước ném exception trong event multicaster đồng bộ | Xử lý lỗi có chủ đích và không dựa vào thứ tự listener ngầm |
| Entity trong bộ nhớ có giá trị mới dù DB rollback | Object Java không tự được khôi phục về trạng thái trước transaction | Reload entity; không tái sử dụng persistence state sau rollback |
| Retry POST tạo bản ghi trùng | Response lỗi sau khi insert đã commit khiến client gửi lại | Dùng idempotency key hoặc unique business key |

## 13. Checklist xử lý rollback và lỗi listener

- Xác định event là Before hay After và vị trí publish so với repository invocation.
- Kiểm tra transaction nào đang hoạt động khi handler được gọi.
- Phân biệt thay đổi trong object Java, thay đổi database và side effect bên ngoài.
- Không suy luận rollback chỉ từ HTTP 4xx/5xx.
- Kiểm tra exception có đi qua transaction interceptor hay đã bị bắt và nuốt.
- Dùng rollbackFor khi cần rollback với checked exception.
- Không dùng After event như một callback mặc định bảo đảm transaction đã commit.
- Không đặt audit cần atomicity trong transaction riêng sau thao tác save.
- Dùng service method có @Transactional để gom các ghi database cần cùng commit.
- Dùng transactional outbox cho message/webhook cần độ tin cậy.
- Làm cho consumer và thao tác retry có tính idempotent.
- Kiểm thử cả dữ liệu đã commit và dữ liệu chưa commit; tránh transaction test làm sai lệch boundary production.
- Ánh xạ exception nghiệp vụ sang HTTP status phù hợp và ghi log có correlation ID.

## Kết luận

Rollback phụ thuộc transaction boundary, không phụ thuộc đơn thuần vào việc listener ném exception. Lỗi trong Before event thường ngăn repository save của thao tác đó được gọi. Lỗi trong chính transaction save có thể rollback các thay đổi database thuộc transaction. Lỗi trong After event có thể làm request trả lỗi trong khi entity đã commit, nếu transaction save đã kết thúc và không có transaction ngoài bao trùm. Các side effect như email, webhook hoặc message không tự rollback cùng database. Khi entity và audit cần nguyên tử, hãy điều phối chúng trong một service transaction; khi cần phát sự kiện ra ngoài một cách tin cậy, dùng transactional outbox và xử lý idempotent.

## Tài liệu tham khảo

- Spring Data REST – Events and repository event handlers: https://docs.spring.io/spring-data/rest/reference/events.html
- Spring Data JPA – Transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- Spring Framework – Declarative transaction management and rollback rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework – Transaction-bound events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
