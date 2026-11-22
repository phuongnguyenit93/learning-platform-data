# @RepositoryEventHandler và các annotation @HandleBefore*, @HandleAfter*

## 1. Repository events trong Spring Data REST là gì?

Spring Data REST xuất bản Spring Data repository thành HTTP resources. Trong quá trình xử lý request tạo, cập nhật, thay đổi association hoặc xóa một entity, REST exporter phát ra các application event tương ứng.

Repository event handler cho phép ứng dụng chạy logic tại những thời điểm đó mà không phải tự viết lại toàn bộ controller CRUD. Ví dụ:

- Chuẩn hóa dữ liệu trước khi entity được tạo hoặc lưu.
- Ghi nhận thông tin audit.
- Kiểm tra hoặc điều chỉnh trạng thái trước thao tác.
- Phản ứng sau khi entity được tạo, cập nhật hoặc xóa.
- Theo dõi việc thêm, thay đổi hoặc gỡ liên kết giữa các resource.

Cơ chế này thuộc lifecycle của **Spring Data REST exporter**. Không nên hiểu nó là interceptor tự động chạy mỗi khi bất kỳ service nào gọi repository. Một lời gọi trực tiếp từ service hoặc một controller MVC tùy chỉnh không mặc nhiên phát ra các REST repository events này.

Có hai cách tiếp cận chính:

1. Viết một handler POJO được đánh dấu bằng \`@RepositoryEventHandler\`, rồi gắn các method với event bằng annotation \`@HandleBefore...\` hoặc \`@HandleAfter...\`.
2. Lắng nghe các application event bằng \`ApplicationListener\` hoặc kế thừa \`AbstractRepositoryEventListener\` khi cần kiểm soát dispatch ở mức tổng quát hơn.

Với phần lớn xử lý theo từng domain type, annotated handler thường ngắn gọn và dễ đọc.

## 2. Các event trong vòng đời resource

Spring Data REST có tám event cốt lõi cho thao tác entity:

| Event | Annotation handler | Thời điểm |
|---|---|---|
| BeforeCreateEvent | \`@HandleBeforeCreate\` | Trước khi tạo entity mới |
| AfterCreateEvent | \`@HandleAfterCreate\` | Sau khi entity mới được tạo |
| BeforeSaveEvent | \`@HandleBeforeSave\` | Trước khi lưu thay đổi của entity hiện có |
| AfterSaveEvent | \`@HandleAfterSave\` | Sau khi entity được lưu |
| BeforeLinkSaveEvent | \`@HandleBeforeLinkSave\` | Trước khi lưu thay đổi liên kết giữa các resource |
| AfterLinkSaveEvent | \`@HandleAfterLinkSave\` | Sau khi lưu thay đổi liên kết |
| BeforeDeleteEvent | \`@HandleBeforeDelete\` | Trước khi xóa entity |
| AfterDeleteEvent | \`@HandleAfterDelete\` | Sau khi xóa entity |

Một số phiên bản Spring Data REST hiện hành còn có event cho thao tác xóa association:

| Event bổ sung | Annotation | Ý nghĩa |
|---|---|---|
| BeforeLinkDeleteEvent | \`@HandleBeforeLinkDelete\` | Trước khi gỡ một liên kết khỏi entity cha |
| AfterLinkDeleteEvent | \`@HandleAfterLinkDelete\` | Sau khi gỡ liên kết |

Hai event link-delete không có mặt trong mọi phiên bản cũ. Hãy kiểm tra package \`org.springframework.data.rest.core.annotation\` và API của release train đang dùng trước khi sử dụng chúng.

### Phân biệt create và save

- **Create** dùng khi REST exporter tạo entity mới, thường qua POST collection resource.
- **Save** dùng khi exporter lưu thay đổi cho entity đã tồn tại, thường qua PUT hoặc PATCH item resource.
- **Link save/delete** áp dụng cho association resource hoặc thao tác thay đổi liên kết giữa các entity.
- **Delete** áp dụng cho việc xóa entity resource.

Không nên chỉ dựa vào HTTP method để tự suy ra mọi event sẽ chạy. Hãy kiểm tra resource mapping và luồng repository thực tế của phiên bản đang dùng, đặc biệt với association và custom controller.

## 3. Vai trò của @RepositoryEventHandler

\`@RepositoryEventHandler\` đánh dấu một class là nơi chứa các method xử lý repository events. Spring Data REST dùng BeanPostProcessor để tìm bean có annotation này, quét các method mang annotation event và đăng ký chúng với event tương ứng.

Một handler đơn giản:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        if (person.getDisplayName() != null) {
            person.setDisplayName(
                    person.getDisplayName().trim()
            );
        }
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        person.setUpdatedAt(Instant.now());
    }

    @HandleAfterCreate
    public void afterCreate(Person person) {
        // Ghi log hoặc phát tín hiệu nội bộ sau khi tạo.
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        // Phản ứng sau khi entity bị xóa.
    }
}
~~~~

Các điểm cần nhớ:

- Class phải là Spring bean. Có thể dùng \`@Component\` hoặc khai báo bean qua \`@Bean\` trong cấu hình.
- Class phải được đánh dấu \`@RepositoryEventHandler\`.
- Method xử lý event cần annotation tương ứng.
- Kiểu domain ở tham số đầu tiên của method xác định loại entity mà handler nhận.
- Có thể viết nhiều method cùng annotation nhưng nhận các domain type khác nhau.
- Handler chỉ được gọi khi event tương ứng được REST exporter phát ra.

Trong các phiên bản API hiện hành, kiểu domain được suy ra từ tham số đầu tiên của method handler. Thuộc tính class-level \`value\` trên \`@RepositoryEventHandler\` và thuộc tính kiểu trên một số annotation handler đã bị đánh dấu deprecated ở API mới; nên ưu tiên khai báo tham số có kiểu cụ thể và kiểm tra Javadoc của phiên bản dự án.

## 4. Đăng ký handler trong ApplicationContext

Cách thông dụng trong Spring Boot là đặt handler trong package được component scan:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {
    // Các method @HandleBefore... và @HandleAfter...
}
~~~~

Nếu class nằm ngoài package scan, có thể khai báo thủ công:

~~~~java
@Configuration
public class RepositoryEventConfiguration {

    @Bean
    PersonEventHandler personEventHandler() {
        return new PersonEventHandler();
    }
}
~~~~

Không cần vừa khai báo \`@Component\` vừa tạo thêm một bean \`@Bean\` cho cùng một class. Chọn một cách đăng ký để tránh hai instance handler và việc xử lý event lặp ngoài ý muốn.

Nếu handler cần service, repository hoặc clock, hãy dùng constructor injection như các Spring bean bình thường:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {

    private final PersonPolicy personPolicy;
    private final Clock clock;

    public PersonEventHandler(
            PersonPolicy personPolicy,
            Clock clock) {
        this.personPolicy = personPolicy;
        this.clock = clock;
    }

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        personPolicy.prepareForCreation(person);
        person.setCreatedAt(Instant.now(clock));
    }
}
~~~~

Tránh tự tạo dependency bằng \`new\` trong handler vì cách đó bỏ qua dependency injection, proxy và các cấu hình Spring liên quan.

## 5. Phạm vi domain type của handler

Có thể để một class xử lý nhiều domain type bằng cách khai báo kiểu cụ thể ở từng method:

~~~~java
@Component
@RepositoryEventHandler
public class AccountEventHandler {

    @HandleBeforeSave
    public void beforeSaveAccount(Account account) {
        // Xử lý Account.
    }

    @HandleBeforeSave
    public void beforeSaveProfile(Profile profile) {
        // Xử lý Profile.
    }
}
~~~~

BeanPostProcessor xác định domain type quan tâm từ tham số đầu tiên của từng method có annotation. Vì vậy, nên dùng kiểu domain cụ thể thay cho \`Object\` để handler chỉ nhận event phù hợp và compiler kiểm tra được API domain.

Tài liệu của các phiên bản trước thường minh họa cách giới hạn type bằng \`@RepositoryEventHandler(Person.class)\` hoặc truyền type vào annotation method. API mới đánh dấu một số thuộc tính type này deprecated và khuyến nghị suy ra từ tham số method. Khi nâng cấp Spring Data REST, hãy đối chiếu đúng Javadoc thay vì sao chép nguyên ví dụ cũ.

## 6. Dùng @HandleBefore* để xử lý trước thao tác

Các annotation Before được gọi trước hành động repository tương ứng. Đây là thời điểm phù hợp để chuẩn hóa entity, bổ sung metadata đơn giản hoặc thực hiện kiểm tra trước khi tiếp tục.

Ví dụ chuẩn hóa dữ liệu trước khi tạo:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
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
~~~~

Ví dụ cập nhật audit timestamp trước khi lưu:

~~~~java
@HandleBeforeSave
public void beforeSave(Person person) {
    person.setUpdatedAt(Instant.now());
}
~~~~

Ví dụ kiểm tra trạng thái trước khi xóa:

~~~~java
@HandleBeforeDelete
public void beforeDelete(Person person) {
    if (person.isProtectedAccount()) {
        throw new IllegalStateException(
                "Không thể xóa tài khoản được bảo vệ"
        );
    }
}
~~~~

Ví dụ cuối minh họa việc dừng thao tác bằng exception. Trong ứng dụng thực tế, nên dùng exception nghiệp vụ riêng và ánh xạ nó thành HTTP response phù hợp. Nếu kiểm tra là constraint đầu vào thông thường, Spring Data REST có cơ chế Validator riêng; dùng validator thường giúp trả lỗi field rõ ràng hơn là ném exception chung.

Không nên đưa truy vấn nặng, lời gọi mạng hoặc một use case nhiều bước vào Before handler. Nếu logic cần phối hợp nhiều aggregate, quyền truy cập hoặc transaction phức tạp, hãy chuyển sang application service và custom controller.

## 7. Dùng @HandleAfter* để phản ứng sau thao tác

Các annotation After được gọi sau khi REST exporter thực hiện thao tác tương ứng. Chúng hữu ích cho log, audit event hoặc phát tín hiệu nội bộ:

~~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {

    private static final Logger log =
            LoggerFactory.getLogger(PersonEventHandler.class);

    @HandleAfterCreate
    public void afterCreate(Person person) {
        log.info("Created person with id {}", person.getId());
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        log.info("Saved person with id {}", person.getId());
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        log.info("Deleted person with id {}", person.getId());
    }
}
~~~~

After event giúp tách phản ứng khỏi controller, nhưng không nên hiểu tên “After” là bảo đảm transaction database đã commit. Spring Data REST events là Spring application events và mặc định được phát đồng bộ; vị trí phát event so với transaction commit phụ thuộc transaction boundary của ứng dụng.

Nếu cần gửi email, gọi dịch vụ bên ngoài hoặc phát message phải phản ánh một thay đổi đã commit, hãy dùng cơ chế after-commit phù hợp như \`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)\` với application event của ứng dụng, hoặc transactional outbox. Không để một lời gọi mạng dễ lỗi quyết định thành công của request lưu dữ liệu.

## 8. Xử lý thay đổi association

Một resource có thể liên kết đến resource khác qua association. Ví dụ Person có nhiều Role hoặc Order. Spring Data REST có các association resource và phát event riêng khi liên kết được thay đổi.

Các handler chính:

- \`@HandleBeforeLinkSave\`: trước khi lưu liên kết.
- \`@HandleAfterLinkSave\`: sau khi lưu liên kết.
- \`@HandleBeforeLinkDelete\`: trước khi gỡ liên kết, nếu phiên bản hỗ trợ.
- \`@HandleAfterLinkDelete\`: sau khi gỡ liên kết, nếu phiên bản hỗ trợ.

Ví dụ:

~~~~java
@Component
@RepositoryEventHandler
public class PersonAssociationEventHandler {

    @HandleBeforeLinkSave
    public void beforeLinkSave(Person person) {
        // Kiểm tra hoặc chuẩn bị dữ liệu trước khi liên kết được lưu.
    }

    @HandleAfterLinkSave
    public void afterLinkSave(Person person) {
        // Ghi nhận việc liên kết đã thay đổi.
    }

    @HandleBeforeLinkDelete
    public void beforeLinkDelete(Person person) {
        // Kiểm tra trước khi gỡ association.
    }

    @HandleAfterLinkDelete
    public void afterLinkDelete(Person person) {
        // Phản ứng sau khi association được gỡ.
    }
}
~~~~

Hai annotation link-delete chỉ dùng được khi có trong phiên bản Spring Data REST của dự án. Cần kiểm tra package annotation trước khi thêm method để tránh lỗi compile khi ứng dụng dùng release train cũ.

Handler link event nhận domain object theo contract của annotation. Nếu nghiệp vụ cần biết chính xác association/property nào thay đổi, hãy kiểm tra API event cụ thể của phiên bản hoặc dùng custom controller/service có tham số association rõ ràng; đừng giả định mọi handler method đều tự nhận tên property hoặc URI liên quan.

## 9. Các annotation Before/After tương ứng

Các annotation thường gặp được nhóm như sau:

| Nhóm | Annotation |
|---|---|
| Tạo entity | \`@HandleBeforeCreate\`, \`@HandleAfterCreate\` |
| Lưu entity | \`@HandleBeforeSave\`, \`@HandleAfterSave\` |
| Lưu association | \`@HandleBeforeLinkSave\`, \`@HandleAfterLinkSave\` |
| Xóa entity | \`@HandleBeforeDelete\`, \`@HandleAfterDelete\` |
| Xóa association ở phiên bản hỗ trợ | \`@HandleBeforeLinkDelete\`, \`@HandleAfterLinkDelete\` |

Tên annotation gắn trực tiếp với event name. Mỗi method nên thực hiện một trách nhiệm rõ ràng và tránh gom toàn bộ lifecycle vào một method duy nhất.

Một class có thể có nhiều handler method. Nếu nhiều bean cùng đăng ký cho một event/domain type, có thể có nhiều handler được gọi; thứ tự thực thi không nên được dùng làm cơ chế phối hợp nghiệp vụ trừ khi ứng dụng cấu hình và kiểm soát rõ ràng thứ tự đó.

## 10. So sánh annotated handler và ApplicationListener

Spring Data REST cũng cho phép lắng nghe event theo kiểu Spring application event.

| Cách | Đặc điểm | Khi phù hợp |
|---|---|---|
| \`@RepositoryEventHandler\` + \`@Handle...\` | Khai báo theo annotation, method nhận domain type cụ thể | Xử lý theo entity và lifecycle event rõ ràng |
| \`ApplicationListener<BeforeSaveEvent>\` | Lắng nghe một event type Spring cụ thể | Cần tích hợp với hệ thống application event |
| \`AbstractRepositoryEventListener<T>\` | Override hook như onBeforeSave hoặc onAfterDelete | Muốn tổ chức handler theo lớp kế thừa và các hook lifecycle |

Annotated handler tự suy ra domain type từ tham số method. Với listener tổng quát, ứng dụng có thể phải tự kiểm tra loại entity nếu listener nhận Object hoặc xử lý nhiều domain type.

Ví dụ khái niệm với abstract listener:

~~~~java
@Component
public class PersonRepositoryListener
        extends AbstractRepositoryEventListener<Person> {

    @Override
    protected void onBeforeSave(Person person) {
        // Xử lý trước khi lưu.
    }

    @Override
    protected void onAfterDelete(Person person) {
        // Xử lý sau khi xóa.
    }
}
~~~~

Kiểm tra visibility và generic signature của các hook theo phiên bản API đang dùng. Không đăng ký cùng một nghiệp vụ ở cả annotated handler và listener khác nếu không muốn xử lý hai lần.

## 11. Event handler không thay thế Validator hoặc service layer

Mặc dù Before handler có thể kiểm tra entity, không phải mọi kiểm tra đều nên đặt trong event handler.

- **Bean Validation:** phù hợp cho nullability, độ dài, định dạng và giới hạn field.
- **ValidatingRepositoryEventListener / Spring Validator:** phù hợp để gắn validator vào repository lifecycle và trả lỗi validation.
- **Domain/application service:** phù hợp cho quy tắc phụ thuộc trạng thái hiện tại, quyền người dùng, dữ liệu liên quan hoặc nhiều bước nghiệp vụ.
- **Database constraint:** bảo vệ tính toàn vẹn dữ liệu tại thời điểm ghi.
- **Repository event handler:** phù hợp cho logic gắn với lifecycle của REST exporter như chuẩn hóa nhẹ, audit hoặc phát tín hiệu.

Không nên xem \`@HandleBeforeSave\` là nơi duy nhất bảo vệ một quy tắc nghiệp vụ quan trọng. Service hoặc batch job gọi repository trực tiếp có thể không phát REST event, vì vậy business invariant cần được đặt ở domain/service hoặc database tùy tính chất.

## 12. Transaction, đồng bộ và side effect

Spring Data REST events là application events của Spring. Mặc định Spring application events được phát đồng bộ trong cùng luồng xử lý, trừ khi listener chủ động chuyển sang async hoặc phát tiếp qua ranh giới thread/hệ thống khác.

Điều đó dẫn đến một số lưu ý:

- Handler Before chạy trong request path; xử lý chậm sẽ làm request chậm.
- Handler After đồng bộ cũng có thể kéo dài thời gian phản hồi.
- Exception trong handler có thể ảnh hưởng đến quá trình xử lý request; cách transaction rollback phụ thuộc vị trí phát event và transaction boundary.
- Side effect bên ngoài database không tự rollback khi transaction database rollback.
- Retry một request có thể khiến side effect bị lặp nếu handler không idempotent.

Với thông báo cần bảo đảm chỉ gửi sau khi commit, nên ghi outbox record trong cùng transaction rồi worker riêng gửi message. Nếu dùng \`@TransactionalEventListener\`, kiểm tra transaction thực tế và cấu hình fallback khi không có transaction.

Không dùng event handler như một message broker bền vững. Application event trong bộ nhớ không tự bảo đảm delivery sau khi process bị dừng.

## 13. Xử lý lỗi và mapping response

Before handler có thể từ chối thao tác bằng exception, nhưng exception cần được thiết kế rõ:

- Dùng exception nghiệp vụ riêng để phân biệt lỗi trạng thái, xung đột hoặc quyền.
- Dùng Validator cho các lỗi field để client nhận được tên field và mã lỗi.
- Dùng \`@RestControllerAdvice\` cho controller MVC tùy chỉnh.
- Với Spring Data REST, kiểm tra exception handling mặc định và cấu hình response tương ứng.
- Không trả stack trace, SQL, token hoặc thông tin nội bộ trong response.

Status code phụ thuộc loại lỗi và exception mapping. Không nên mặc định mọi exception trong handler đều trở thành 400; nếu không được ánh xạ, lỗi có thể thành 500. Viết integration test để xác nhận response mà client thực sự nhận.

## 14. Kiểm thử repository event handler

Nên kiểm thử qua HTTP request thực tế vì mục tiêu là xác nhận REST exporter phát event và handler đã được đăng ký.

Ví dụ với MockMvc:

~~~~java
mockMvc.perform(post("/people")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_HAL_JSON)
        .content("""
            {
              "displayName": "  Alice  "
            }
            """))
    .andExpect(status().isCreated());
~~~~

Sau request, kiểm tra entity đã được chuẩn hóa hoặc audit field đã được đặt theo logic handler.

Các trường hợp nên kiểm tra:

1. POST kích hoạt \`@HandleBeforeCreate\` và \`@HandleAfterCreate\`.
2. PUT/PATCH item kích hoạt các handler save phù hợp.
3. DELETE item kích hoạt BeforeDelete và AfterDelete.
4. Thao tác association kích hoạt LinkSave; link-delete chỉ test khi phiên bản có hỗ trợ.
5. Handler không nhận event của domain type khác.
6. Bean handler được component scan hoặc đăng ký qua ApplicationContext.
7. Exception ở Before handler chặn thao tác và response được ánh xạ đúng.
8. After handler không gây side effect trùng khi request được retry.
9. Các đường gọi repository trực tiếp không bị giả định là sẽ phát REST events.
10. Transaction và rollback được kiểm tra trong integration test phù hợp.

Có thể dùng Mockito để unit test logic thuần của handler, nhưng unit test đó không chứng minh Spring Data REST đã phát event hoặc phát hiện bean. Cần ít nhất một integration test để xác nhận wiring.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Handler không được gọi | Class không phải Spring bean hoặc thiếu \`@RepositoryEventHandler\` | Kiểm tra component scan và ApplicationContext |
| Handler nhận sai domain type | Tham số method quá tổng quát hoặc cấu hình type cũ không khớp | Dùng tham số đầu tiên có kiểu entity cụ thể |
| BeforeCreate không chạy khi cập nhật | Create và save là hai event khác nhau | Dùng annotation đúng lifecycle |
| BeforeSave không chạy khi tạo mới | Tạo mới phát BeforeCreate | Đăng ký cả hai nếu cần logic cho cả create và update |
| Handler chạy hai lần | Cùng nghiệp vụ được đăng ký ở nhiều handler/listener hoặc bean trùng | Kiểm tra bean definitions và event registrations |
| Annotation link-delete không compile | Phiên bản Spring Data REST không có annotation đó | Kiểm tra Javadoc của dependency thực tế |
| Exception trả 500 | Chưa ánh xạ exception theo API contract | Dùng exception riêng và integration test |
| Gọi repository từ service không kích hoạt handler | REST events thuộc REST exporter lifecycle | Đưa invariant vào service/domain hoặc phát application event riêng |
| Gửi message trước commit | Dùng After event như thể đó là after-commit | Dùng transactional event/outbox |
| Handler làm request chậm | Chạy truy vấn hoặc gọi mạng đồng bộ | Giữ handler nhẹ, chuyển side effect sang xử lý phù hợp |

## 16. Kết luận

\`@RepositoryEventHandler\` đánh dấu một Spring bean chứa các method xử lý lifecycle event do Spring Data REST phát ra. Các annotation \`@HandleBeforeCreate\`, \`@HandleAfterCreate\`, \`@HandleBeforeSave\`, \`@HandleAfterSave\`, \`@HandleBeforeDelete\`, \`@HandleAfterDelete\` và các annotation link tương ứng giúp gắn logic vào đúng thời điểm của quá trình xử lý resource.

Handler cần được đăng ký trong ApplicationContext, có kiểu domain rõ ràng ở tham số method và chỉ chạy trong luồng REST exporter tương ứng. Dùng Before event cho chuẩn hóa hoặc kiểm tra nhẹ, After event cho phản ứng sau thao tác, còn business invariant, validation field, authorization và side effect cần bảo đảm sau commit nên đặt ở lớp phù hợp. Cuối cùng, kiểm tra API theo phiên bản và dùng integration test để xác nhận event thực sự được phát và xử lý như mong đợi.

## Tài liệu tham khảo

- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — RepositoryEventHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryEventHandler.html)
- [Spring Data REST — HandleBeforeSave API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/HandleBeforeSave.html)
- [Spring Data REST — HandleBeforeLinkDelete API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/HandleBeforeLinkDelete.html)
- [Spring Data REST — Repository event package](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/package-summary.html)
- [Spring Framework — Transaction-bound events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
