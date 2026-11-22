# Vòng đời sự kiện của REST exporter và điểm mở rộng xử lý trong Spring Data REST

Spring Data REST tự động công bố Spring Data repository thành REST resource. Khi client tạo, cập nhật, thay đổi association hoặc xóa entity qua các endpoint này, REST exporter phát các sự kiện tương ứng trong quá trình xử lý. Ứng dụng có thể lắng nghe những sự kiện đó để chuẩn hóa dữ liệu, kiểm tra quy tắc nghiệp vụ, ghi nhận hoạt động hoặc khởi động xử lý bổ sung.

Các điểm mở rộng thường dùng gồm:

- **Annotated event handler** với @RepositoryEventHandler và các annotation @HandleBefore... / @HandleAfter... để xử lý theo kiểu domain cụ thể.
- **AbstractRepositoryEventListener** để nhận các callback lifecycle tập trung và tự phân loại entity.
- **ValidatingRepositoryEventListener** để gắn Spring Validator vào những thời điểm cụ thể của request.

Các event này thuộc luồng xử lý của Spring Data REST exporter. Chúng không phải callback persistence tổng quát và không tự chạy mỗi khi bất kỳ service hoặc batch job nào gọi repository trực tiếp.

## 1. Tổng quan vòng đời event

Khi client gửi request tới một repository resource, Spring Data REST xác định repository, tải hoặc tạo entity, bind dữ liệu request và phát event phù hợp quanh thao tác repository.

Luồng khái quát:

~~~text
HTTP request
    |
    v
Spring Data REST exporter
    |
    v
Resolve repository và entity
    |
    v
Bind dữ liệu request
    |
    v
Before event / validation
    |
    v
Repository operation
    |
    v
After event
    |
    v
HTTP response và HAL representation
~~~

Event cụ thể phụ thuộc thao tác:

- POST tới collection resource tạo entity mới và đi qua nhóm Create.
- PUT hoặc PATCH tới item resource lưu thay đổi và đi qua nhóm Save.
- Thêm hoặc thay thế association đi qua nhóm Link Save.
- Gỡ association có callback Link Delete trong các phiên bản API hỗ trợ.
- DELETE item resource đi qua nhóm Delete.

Callback Before chạy trước thao tác repository tương ứng. Callback After chạy sau thao tác đó. Từ After không có nghĩa transaction database đã commit hoặc HTTP response đã được gửi thành công.

## 2. Các event của REST exporter

Các event entity lifecycle chính gồm:

| Event | Thời điểm | Đối tượng | Mục đích thường gặp |
|---|---|---|---|
| BeforeCreateEvent | Trước lần lưu đầu tiên của entity mới | Entity mới | Chuẩn hóa dữ liệu, gán giá trị mặc định |
| AfterCreateEvent | Sau khi entity mới được lưu | Entity vừa tạo | Ghi nhận hoạt động tạo, khởi tạo xử lý tiếp |
| BeforeSaveEvent | Trước khi lưu entity | Entity sắp lưu | Kiểm tra hoặc chuẩn hóa dữ liệu cập nhật |
| AfterSaveEvent | Sau khi entity được lưu | Entity vừa lưu | Ghi nhận thay đổi, tạo thông tin đồng bộ |
| BeforeLinkSaveEvent | Trước khi lưu association | Entity cha và entity được liên kết | Kiểm tra quan hệ trước khi gắn |
| AfterLinkSaveEvent | Sau khi lưu association | Entity cha và entity được liên kết | Ghi nhận association vừa thay đổi |
| BeforeDeleteEvent | Trước khi xóa entity | Entity sắp xóa | Kiểm tra điều kiện xóa |
| AfterDeleteEvent | Sau khi xóa entity | Entity đã xóa | Ghi nhận việc xóa, thông báo hệ thống khác |

API của Spring Data REST còn có callback và annotation dành cho link deletion, chẳng hạn onBeforeLinkDelete, onAfterLinkDelete, @HandleBeforeLinkDelete và @HandleAfterLinkDelete ở các phiên bản hỗ trợ. Hãy kiểm tra Javadoc đúng phiên bản dependency của ứng dụng trước khi dùng các hook này.

## 3. Phân biệt Create, Save, Link và Delete

### Create: tạo entity mới

Khi client POST lên collection resource, REST exporter tạo domain object và lưu qua repository.

~~~http
POST /people
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Nguyen"
}
~~~

BeforeCreate phù hợp để chuẩn hóa dữ liệu hoặc gán thuộc tính do server quản lý trước lần lưu đầu tiên. AfterCreate phù hợp để ghi nhận entity mới đã được tạo.

### Save: lưu entity hiện có

Khi client cập nhật item resource bằng PUT hoặc PATCH, REST exporter xử lý entity hiện tại và lưu thay đổi.

~~~http
PATCH /people/42
Content-Type: application/json

{
  "lastName": "Tran"
}
~~~

BeforeSave có thể kiểm tra dữ liệu hoặc tính lại thuộc tính dẫn xuất trước khi lưu. AfterSave có thể ghi nhận thay đổi sau khi repository đã thực hiện thao tác lưu.

Create và Save không nên bị coi là một event duy nhất. Nếu logic phụ thuộc việc entity mới được tạo hay entity cũ được cập nhật, hãy đặt nó vào đúng callback.

### Link Save: thêm hoặc thay thế association

Giả sử Person có association tới Address. Client có thể gán địa chỉ qua association resource:

~~~http
PUT /people/42/address
Content-Type: text/uri-list

http://localhost:8080/addresses/7
~~~

BeforeLinkSave và AfterLinkSave nhận entity cha cùng entity được liên kết. Nhờ đó handler có thể kiểm tra quan hệ cụ thể, ví dụ địa chỉ có được phép gán cho người này hay không.

### Link Delete: gỡ association

Khi API và phiên bản Spring Data REST hỗ trợ link-delete event, handler có thể quan sát thao tác gỡ quan hệ:

~~~http
DELETE /people/42/address
~~~

Gỡ association không đồng nghĩa với xóa entity Address. Callback link-delete giúp ứng dụng kiểm tra hoặc ghi nhận quan hệ vừa bị gỡ. Hãy xác nhận endpoint association và callback thực tế được công bố trong phiên bản đang chạy.

### Delete: xóa entity

Khi client DELETE item resource:

~~~http
DELETE /people/42
~~~

BeforeDelete phù hợp để kiểm tra điều kiện nghiệp vụ trước khi xóa. AfterDelete phù hợp để ghi nhận thao tác sau khi repository đã xóa entity.

Nếu cần từ chối thao tác xóa, thực hiện kiểm tra ở BeforeDelete, Validator hoặc service/domain logic. AfterDelete đã ở sau thao tác repository nên không phải nơi thích hợp để ngăn việc xóa.

## 4. Annotated handler với @RepositoryEventHandler

Đây là cách trực tiếp khi logic gắn với một domain type. Tạo Spring bean, đánh dấu bằng @RepositoryEventHandler và đặt annotation event lên method.

~~~java
import java.time.Instant;

import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.annotation.HandleAfterCreate;
import org.springframework.data.rest.core.annotation.HandleAfterSave;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.HandleBeforeDelete;
import org.springframework.data.rest.core.annotation.HandleAfterDelete;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;

@Component
@RepositoryEventHandler
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        person.setCreatedAt(Instant.now());
    }

    @HandleAfterCreate
    public void afterCreate(Person person) {
        // Ghi nhận Person vừa được tạo.
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        person.setDisplayName(
            person.getFirstName() + " " + person.getLastName()
        );
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // Ghi nhận Person vừa được lưu.
    }

    @HandleBeforeDelete
    public void beforeDelete(Person person) {
        // Kiểm tra điều kiện nghiệp vụ trước khi xóa.
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        // Ghi nhận Person đã bị xóa.
    }
}
~~~

Các method nhận trực tiếp Person nên có thể truy cập thuộc tính domain mà không cần ép kiểu từ Object.

### Xử lý association trong annotated handler

Với link event, tham số đầu tiên là entity cha và tham số thứ hai là entity được liên kết:

~~~java
@HandleBeforeLinkSave
public void beforeAddressLink(Person person, Address address) {
    // Kiểm tra địa chỉ có được phép gắn cho người này không.
}

@HandleAfterLinkSave
public void afterAddressLink(Person person, Address address) {
    // Ghi nhận association vừa được cập nhật.
}
~~~

Nếu phiên bản hỗ trợ link-delete annotation:

~~~java
@HandleBeforeLinkDelete
public void beforeAddressUnlink(Person person, Address address) {
    // Kiểm tra trước khi gỡ association.
}

@HandleAfterLinkDelete
public void afterAddressUnlink(Person person, Address address) {
    // Ghi nhận association đã được gỡ.
}
~~~

Không nhầm thứ tự hai tham số: parent là entity sở hữu association, linked entity là đối tượng ở đầu bên kia của quan hệ.

## 5. Cách Spring Data REST phát hiện handler

Handler phải là bean trong ApplicationContext. Có thể đăng ký bằng component scan:

~~~java
@Component
@RepositoryEventHandler
public class PersonEventHandler {
    // Event methods
}
~~~

Hoặc khai báo bean trong cấu hình:

~~~java
@Configuration
public class RestEventConfiguration {

    @Bean
    PersonEventHandler personEventHandler() {
        return new PersonEventHandler();
    }
}
~~~

Spring Data REST sử dụng cấu hình event handler và bean post-processing để tìm các method có annotation @Handle... trên bean @RepositoryEventHandler.

Loại domain được xác định từ kiểu tham số đầu tiên của method. Với link event, tham số đầu tiên là parent và tham số thứ hai là linked entity. Nên khai báo kiểu cụ thể để handler chỉ nhận event phù hợp.

Nếu class có nhiều method cho nhiều domain type, hãy giữ mỗi method tập trung vào một loại event và một domain rõ ràng. Tránh đặt quá nhiều xử lý không liên quan trong một handler.

## 6. Dùng AbstractRepositoryEventListener

Khi muốn tập trung nhiều callback lifecycle trong một listener tổng quát, có thể kế thừa AbstractRepositoryEventListener.

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.event.AbstractRepositoryEventListener;

@Component
public class RepositoryLifecycleListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeCreate(Object entity) {
        if (entity instanceof Person person) {
            // Chuẩn bị Person trước khi tạo.
        }
    }

    @Override
    protected void onAfterSave(Object entity) {
        if (entity instanceof Person person) {
            // Xử lý sau khi Person được lưu.
        }
    }

    @Override
    protected void onBeforeDelete(Object entity) {
        if (entity instanceof Person person) {
            // Kiểm tra trước khi xóa Person.
        }
    }

    @Override
    protected void onBeforeLinkSave(Object parent, Object linked) {
        if (parent instanceof Person person
                && linked instanceof Address address) {
            // Kiểm tra association Person - Address.
        }
    }

    @Override
    protected void onAfterLinkDelete(Object parent, Object linked) {
        if (parent instanceof Person person
                && linked instanceof Address address) {
            // Ghi nhận association đã được gỡ.
        }
    }
}
~~~

Listener tổng quát nhận Object và tự kiểm tra kiểu. Với entity event, callback nhận entity. Với link event, callback nhận parent và linked object.

Cách này phù hợp khi cần tập trung callback của nhiều domain type. Nếu logic chỉ thuộc một domain cụ thể, annotated handler thường dễ đọc và có kiểu tham số rõ ràng hơn.

## 7. Chọn handler hay listener

| Tiêu chí | @RepositoryEventHandler | AbstractRepositoryEventListener |
|---|---|---|
| Kiểu tham số | Có thể khai báo domain type cụ thể | Thường nhận Object hoặc kiểu tổng quát |
| Lọc domain | Dựa vào kiểu tham số method | Tự kiểm tra trong callback |
| Cách tổ chức | Method riêng theo event và entity | Một class tập trung nhiều callback |
| Phù hợp | Logic cụ thể theo domain | Listener tổng quát cho nhiều domain |

Không cần triển khai đồng thời cả hai cách cho cùng một nghiệp vụ. Nếu cùng một logic được đăng ký ở cả hai nơi, nó có thể chạy hai lần và tạo side effect lặp.

## 8. Validation bằng ValidatingRepositoryEventListener

Khi mục tiêu là kiểm tra dữ liệu và từ chối request nếu không hợp lệ, dùng Spring Validator gắn với event.

Ví dụ validator cho Person khi tạo mới:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component("beforeCreatePersonValidator")
public class PersonCreateValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getEmail() == null
                || person.getEmail().isBlank()) {
            errors.rejectValue(
                "email",
                "email.required",
                "Email is required"
            );
        }
    }
}
~~~

Tên bean theo quy ước beforeCreatePersonValidator gắn validator với event beforeCreate của Person. Có thể dùng các tên event tương ứng như beforeSave hoặc beforeDelete nếu cần validation ở các giai đoạn đó.

Cũng có thể đăng ký validator thủ công qua RepositoryRestConfigurer:

~~~java
@Configuration
public class RestRepositoryConfiguration
        implements RepositoryRestConfigurer {

    private final PersonCreateValidator validator;

    public RestRepositoryConfiguration(
            PersonCreateValidator validator) {
        this.validator = validator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeCreate", validator);
    }
}
~~~

ValidatingRepositoryEventListener kết nối validator với event. Khi validation phát hiện lỗi, request có thể bị từ chối trước thao tác repository và trả lỗi theo cơ chế xử lý validation của ứng dụng.

Dùng Validator cho quy tắc kiểm tra dữ liệu. Dùng event handler cho xử lý domain hoặc side effect. Có thể kết hợp hai cơ chế nếu mỗi cơ chế có trách nhiệm riêng.

## 9. Chọn đúng extension point

Không phải logic nào cũng nên đặt trong REST event handler.

| Nhu cầu | Extension point phù hợp |
|---|---|
| Chuẩn hóa dữ liệu khi REST tạo entity | BeforeCreate handler |
| Kiểm tra dữ liệu khi REST cập nhật | Validator hoặc BeforeSave handler |
| Ghi nhận thao tác sau REST create/update/delete | After event handler |
| Kiểm tra hoặc ghi nhận thay đổi association | Link event handler |
| Logic nghiệp vụ phải chạy từ REST, batch và service | Service hoặc domain layer |
| Audit created/modified date và user | Spring Data auditing |
| Thay đổi representation GET | Projection, serializer hoặc custom controller |
| Endpoint có request/response riêng | Custom controller hoặc custom repository implementation |

REST event chỉ được REST exporter phát trong luồng REST. Nếu một quy tắc nghiệp vụ phải được áp dụng bất kể entity được thay đổi qua REST, service, batch job hoặc message consumer, hãy đặt quy tắc cốt lõi trong service/domain layer.

JPA lifecycle callback như @PrePersist, @PostPersist, @PreUpdate và @PreRemove thuộc persistence provider. Chúng khác với event của Spring Data REST và có phạm vi kích hoạt riêng. Spring Data auditing cũng là cơ chế riêng để ghi metadata như created date và modified date.

## 10. Transaction và side effect

Spring application event được xử lý đồng bộ theo mặc định nếu ứng dụng không cấu hình event multicaster hoặc cơ chế chuyển tiếp bất đồng bộ. Vì vậy:

- Handler chạy lâu có thể kéo dài thời gian phản hồi HTTP.
- Exception trong handler có thể ảnh hưởng request tùy vị trí phát event và transaction.
- After event cho biết thao tác repository tương ứng đã chạy; không tự bảo đảm transaction đã commit.
- Gửi email hoặc gọi dịch vụ bên ngoài trực tiếp trong callback có thể tạo side effect dù transaction database sau đó rollback.

Với side effect cần thực hiện sau khi dữ liệu đã commit, hãy xem xét TransactionalEventListener ở pha AFTER_COMMIT hoặc transactional outbox. Kiểm tra transaction boundary thực tế trước khi chọn cơ chế.

Với message hoặc tác vụ có thể retry, thiết kế consumer và side effect theo hướng idempotent. Không xem callback After là cơ chế bảo đảm exactly-once.

## 11. Các giới hạn cần nhớ

- REST event không tự chạy khi code Java gọi repository trực tiếp.
- Event lifecycle chính không cung cấp một callback read tổng quát cho mọi GET.
- After không đồng nghĩa với after commit.
- Link event có hai đối tượng: parent và linked entity.
- Handler không thay thế Spring Security hoặc authorization trong service.
- Before event hoặc Validator phù hợp để từ chối thao tác; After event chạy sau thao tác repository.
- Thứ tự nhiều handler không nên được giả định nếu ứng dụng không cấu hình rõ.
- Nếu nhiều handler cùng sửa một entity, cần xác định trách nhiệm và tránh ghi đè lẫn nhau.
- API link-delete callback có thể khác theo phiên bản Spring Data REST; kiểm tra dependency và Javadoc thực tế.

## 12. Kiểm thử event lifecycle

Nên kiểm thử qua HTTP integration test để xác nhận REST exporter phát đúng event và handler đã được đăng ký.

Các trường hợp nên kiểm tra:

1. POST Person và xác nhận BeforeCreate/AfterCreate được gọi.
2. PUT hoặc PATCH Person và xác nhận BeforeSave/AfterSave được gọi.
3. Gắn Address vào Person và xác nhận LinkSave nhận đúng parent cùng linked entity.
4. Gỡ association và xác nhận LinkDelete callback nếu phiên bản đang dùng hỗ trợ.
5. DELETE Person và xác nhận BeforeDelete/AfterDelete.
6. Gửi dữ liệu không hợp lệ và xác nhận Validator từ chối trước khi lưu.
7. Gọi repository trực tiếp từ service và xác nhận logic nghiệp vụ cốt lõi vẫn chạy mà không phụ thuộc REST event.
8. Kiểm tra transaction rollback khi callback phát sinh exception.
9. Kiểm tra side effect ngoài hệ thống không được gửi trước commit nếu nghiệp vụ yêu cầu after-commit.
10. Kiểm tra handler không chạy hai lần do đăng ký trùng.

Có thể dùng Mockito để xác nhận service được gọi từ handler. Integration test với database giúp kiểm tra trạng thái entity và association sau request. Nếu có xử lý bất đồng bộ, kiểm tra cả message được ghi nhận và cách consumer xử lý retry.

## 13. Quy trình triển khai

1. Xác định thao tác REST cần mở rộng: create, save, link save/delete hay delete.
2. Chọn Before hoặc After theo thời điểm cần xử lý.
3. Chọn annotated handler cho logic theo domain type hoặc AbstractRepositoryEventListener cho callback tổng quát.
4. Đăng ký handler trong ApplicationContext bằng component scan hoặc bean configuration.
5. Dùng Validator gắn với event nếu mục tiêu là kiểm tra dữ liệu.
6. Đặt quy tắc nghiệp vụ dùng chung trong service/domain layer.
7. Xác định transaction boundary trước khi gọi hệ thống ngoài hoặc phát message.
8. Dùng after-commit hoặc outbox nếu side effect phải gắn với commit database.
9. Viết integration test qua HTTP cho từng event và xác nhận dữ liệu sau thao tác.

## 14. Những điểm cần ghi nhớ

- Spring Data REST phát event quanh thao tác create, save, link và delete trong REST exporter.
- Tám event entity lifecycle chính là Before/After Create, Before/After Save, Before/After Link Save và Before/After Delete.
- Các phiên bản hỗ trợ link deletion có thêm callback và annotation Before/After Link Delete.
- @RepositoryEventHandler cùng @Handle... là cách khai báo handler theo domain type; với link event, hai tham số lần lượt là parent và linked entity.
- AbstractRepositoryEventListener cung cấp callback tổng quát và phù hợp khi cần xử lý nhiều domain type trong một listener.
- ValidatingRepositoryEventListener cho phép gắn Spring Validator vào event bằng tên bean hoặc đăng ký thủ công.
- REST event không thay thế service/domain logic, JPA lifecycle callback hoặc Spring Data auditing.
- Event mặc định chạy đồng bộ; callback After không tự bảo đảm transaction đã commit.
- Kiểm thử qua HTTP để xác nhận handler được kích hoạt đúng và dữ liệu được lưu như mong đợi.

## Nguồn tham khảo

- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — AbstractRepositoryEventListener API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/AbstractRepositoryEventListener.html)
- [Spring Data REST — RepositoryEventHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryEventHandler.html)
- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — ValidatingRepositoryEventListener API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/ValidatingRepositoryEventListener.html)
