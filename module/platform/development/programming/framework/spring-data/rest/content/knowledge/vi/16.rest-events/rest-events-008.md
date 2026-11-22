# Đăng ký handler thành Spring bean và giới hạn kiểu miền

## Mục tiêu

Spring Data REST phát ra repository lifecycle events khi client tạo, lưu, xóa resource hoặc thay đổi association qua các endpoint repository REST. Ứng dụng có thể lắng nghe các event này bằng một lớp handler được đăng ký thành Spring bean.

Hai việc cần làm rõ:

- **Đăng ký bean:** để Spring Data REST tìm thấy handler trong ApplicationContext.
- **Giới hạn kiểu miền:** dùng `@RepositoryEventHandler(Person.class)` để chỉ định domain type mà handler phục vụ.

Các method trong handler được gắn annotation như `@HandleBeforeCreate`, `@HandleAfterCreate`, `@HandleBeforeSave` hoặc `@HandleAfterSave`. Nhờ vậy, logic chạy đúng thời điểm trong vòng đời resource mà không cần viết controller riêng cho từng thao tác CRUD.

## 1. Repository event handler là gì?

Repository event handler là một Spring bean nhận các sự kiện do Spring Data REST phát ra trong quá trình xử lý repository resource.

Ví dụ, khi client gửi:

~~~http
POST /api/people
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Nguyen"
}
~~~

Spring Data REST nhận diện collection resource, chuyển request body thành đối tượng Person và phát các event phù hợp trong quá trình tạo/lưu. Handler đăng ký cho event trước khi tạo có thể chuẩn hóa hoặc bổ sung dữ liệu; handler sau khi tạo có thể thực hiện công việc hậu xử lý.

Handler không phải REST controller:

- Không khai báo URL bằng `@RequestMapping`.
- Không trực tiếp nhận `HttpServletRequest` như controller.
- Được gọi khi Spring Data REST phát event tương ứng.
- Có thể dùng dependency được inject từ Spring như service, clock hoặc publisher.

## 2. Đăng ký handler thành Spring bean

Spring Data REST chỉ có thể phát hiện handler nếu đối tượng đó nằm trong Spring ApplicationContext và được đánh dấu là repository event handler.

Cách phổ biến là dùng `@Component` cùng `@RepositoryEventHandler`:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;

@Component
@RepositoryEventHandler
public class PersonEventHandler {
    // Event handler methods go here.
}
~~~

- `@Component` đăng ký class thành Spring bean thông qua component scanning.
- `@RepositoryEventHandler` đánh dấu bean là nơi chứa các method xử lý repository events.
- Spring Data REST tìm các bean handler trong ApplicationContext và kết nối method có annotation lifecycle tương ứng.

Package chứa class phải nằm trong phạm vi component scan của ứng dụng. Nếu class không được scan, annotation trên class không đủ để tạo bean.

### Đăng ký bằng @Bean

Nếu không dùng `@Component`, có thể khai báo bean tường minh trong configuration:

~~~java
@Configuration
public class RepositoryEventConfiguration {

    @Bean
    PersonEventHandler personEventHandler(
            PersonService personService) {
        return new PersonEventHandler(personService);
    }
}
~~~

Class vẫn cần được đánh dấu bằng `@RepositoryEventHandler` để Spring Data REST nhận diện vai trò của nó. Chọn một cách đăng ký bean phù hợp; tránh tạo nhiều instance của cùng handler ngoài ý muốn.

## 3. Giới hạn handler theo domain type

Một ứng dụng có thể export nhiều repository, ví dụ Person, Department và Order. Nếu một handler chỉ xử lý Person, hãy chỉ rõ domain type trên `@RepositoryEventHandler`:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void handlePersonCreate(Person person) {
        // Logic chỉ dành cho Person.
    }
}
~~~

`Person.class` là domain type mà handler được đăng ký để nhận event. Điều này giúp Spring Data REST phân phối event tới đúng handler, tránh để một lớp xử lý nhầm loại entity khác.

Không có giới hạn type tường minh, handler có thể được đăng ký rộng hơn dự định. Với ứng dụng có nhiều aggregate, nên tạo handler riêng cho từng domain type hoặc nhóm type có cùng trách nhiệm.

### Domain type scope không phải authorization

`@RepositoryEventHandler(Person.class)` chỉ giới hạn loại domain object mà handler nhận. Nó không:

- Cấp quyền cho người dùng sửa Person.
- Giới hạn field nào được phép ghi.
- Ẩn dữ liệu trong response.
- Thay thế Spring Security hoặc kiểm tra quyền sở hữu resource.

Authorization vẫn phải được cấu hình riêng ở tầng security và application/domain service.

## 4. Gắn method với lifecycle event

Các annotation lifecycle được đặt trên method của handler:

| Annotation | Thời điểm | Ví dụ mục đích |
|---|---|---|
| `@HandleBeforeCreate` | Trước khi tạo resource mới | Gán giá trị mặc định, chuẩn hóa dữ liệu đầu vào |
| `@HandleAfterCreate` | Sau khi tạo resource | Ghi nhận hoạt động sau tạo |
| `@HandleBeforeSave` | Trước khi lưu resource | Chuẩn hóa hoặc kiểm tra trạng thái trước khi lưu |
| `@HandleAfterSave` | Sau khi lưu resource | Phát tín hiệu hậu xử lý |
| `@HandleBeforeDelete` | Trước khi xóa resource | Kiểm tra điều kiện trước khi xóa |
| `@HandleAfterDelete` | Sau khi xóa resource | Ghi nhận hoặc phát thông báo sau xóa |
| `@HandleBeforeLinkSave` | Trước khi lưu thay đổi association | Kiểm tra thay đổi liên kết |
| `@HandleAfterLinkSave` | Sau khi lưu thay đổi association | Xử lý hậu kỳ cho liên kết |

Các annotation tương ứng với event mà Spring Data REST phát ra. Hãy chọn event theo thời điểm logic cần chạy; không dùng event sau thao tác nếu cần thay đổi object trước khi lưu.

## 5. Ví dụ handler hoàn chỉnh cho Person

Ví dụ dưới đây chuẩn hóa dữ liệu trước khi tạo và cập nhật:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.util.StringUtils;

@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    private final PersonService personService;

    public PersonEventHandler(PersonService personService) {
        this.personService = personService;
    }

    @HandleBeforeCreate
    public void handleBeforeCreate(Person person) {
        normalize(person);
        personService.applyCreationDefaults(person);
    }

    @HandleBeforeSave
    public void handleBeforeSave(Person person) {
        normalize(person);
    }

    private void normalize(Person person) {
        if (StringUtils.hasText(person.getFirstName())) {
            person.setFirstName(person.getFirstName().trim());
        }

        if (StringUtils.hasText(person.getLastName())) {
            person.setLastName(person.getLastName().trim());
        }
    }
}
~~~

Trong ví dụ:

- `@Component` tạo bean.
- `@RepositoryEventHandler(Person.class)` giới hạn handler vào Person.
- `@HandleBeforeCreate` chạy trước thao tác tạo.
- `@HandleBeforeSave` chạy trước thao tác lưu.
- Constructor injection cung cấp PersonService từ Spring.
- Logic chuẩn hóa được tách thành method riêng để tránh lặp.

Các method handler nhận domain object phù hợp với event. Giữ tham số method có kiểu rõ ràng, chẳng hạn Person, để tránh ép kiểu không cần thiết.

Nếu cùng một quy tắc chuẩn hóa được dùng từ nhiều entry point (REST, batch hoặc message consumer), hãy đặt quy tắc cốt lõi trong domain/service và gọi lại từ handler. Không để hành vi nghiệp vụ quan trọng chỉ tồn tại trong một callback REST.

## 6. Phân biệt Before và After

Sự khác biệt chính là thời điểm event được phát:

- **Before:** thao tác repository chưa hoàn tất. Handler có thể chuẩn hóa hoặc thay đổi object trước khi Spring Data REST tiếp tục xử lý.
- **After:** thao tác tương ứng đã được thực hiện. Handler phù hợp cho công việc hậu xử lý dựa trên kết quả vừa xảy ra.

Ví dụ:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonAuditHandler {

    private final AuditService auditService;

    public PersonAuditHandler(AuditService auditService) {
        this.auditService = auditService;
    }

    @HandleAfterCreate
    public void afterCreate(Person person) {
        auditService.recordCreated(person.getId());
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        auditService.recordSaved(person.getId());
    }

    @HandleAfterDelete
    public void afterDelete(Person person) {
        auditService.recordDeleted(person.getId());
    }
}
~~~

Đây là ví dụ minh họa vị trí gọi audit service. Cần xác định transaction boundary và yêu cầu nhất quán của hệ thống trước khi thực hiện side effect bên ngoài.

Nếu phải gửi email, gọi HTTP service hoặc phát message tới hệ thống khác, hãy cân nhắc transactional outbox hoặc cơ chế đảm bảo giao nhận phù hợp. Không giả định một external side effect trong handler sẽ tự động exactly-once hoặc luôn đồng bộ với transaction database.

## 7. Giới hạn type ở cấp class và kiểu tham số method

Hai phần bổ trợ nhau:

~~~java
@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        // Xử lý Person trước khi tạo.
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // Xử lý Person sau khi lưu.
    }
}
~~~

- Annotation ở cấp class giới hạn domain type mà handler đăng ký.
- Kiểu tham số method thể hiện object mà method xử lý.
- Lifecycle annotation xác định event nào gọi method.

Giữ ba phần này nhất quán. Nếu handler được giới hạn cho Person nhưng method lại khai báo kiểu domain không phù hợp, method có thể không được gọi như mong đợi hoặc cấu hình handler trở nên khó hiểu.

Nếu cần xử lý Department, có thể tạo `DepartmentEventHandler` riêng:

~~~java
@Component
@RepositoryEventHandler(Department.class)
public class DepartmentEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Department department) {
        department.setName(department.getName().trim());
    }
}
~~~

Tách handler theo domain type giúp giới hạn trách nhiệm và làm cho dependency dễ kiểm soát hơn.

## 8. Handler khác gì ValidatingRepositoryEventListener?

Spring Data REST có cả repository event handler và validating repository event listener, nhưng chúng phục vụ những mục đích khác nhau:

| Cơ chế | Mục đích chính | Cách khai báo |
|---|---|---|
| Repository event handler | Chạy logic tùy chỉnh tại lifecycle event | Spring bean với `@RepositoryEventHandler` và `@Handle...` |
| ValidatingRepositoryEventListener | Chạy Spring Validator và ghi lỗi validation | Đăng ký validator theo event trong `RepositoryRestConfigurer` |

Ví dụ:

- Chuẩn hóa tên trước khi lưu có thể đặt trong handler hoặc domain/service.
- Kiểm tra dữ liệu không hợp lệ bằng `Errors` phù hợp với Spring Validator.
- Quyết định user có được sửa Person hay không thuộc authorization.
- Quy tắc nghiệp vụ phải luôn được bảo vệ nên nằm ở application/domain service, không chỉ trong handler REST.

Không dùng repository event handler như một cơ chế validation ngầm nếu mục tiêu là trả lỗi field một cách chuẩn hóa. Hãy chọn abstraction phù hợp với trách nhiệm.

## 9. Handler có được gọi khi nào?

Handler được gọi khi Spring Data REST phát repository event trong quá trình xử lý repository REST resource. Ví dụ các request thường liên quan:

| HTTP request | Event thường liên quan |
|---|---|
| `POST /api/people` | BeforeCreate / AfterCreate và các event save liên quan theo lifecycle |
| `PUT /api/people/42` | BeforeSave / AfterSave |
| `PATCH /api/people/42` | BeforeSave / AfterSave |
| `DELETE /api/people/42` | BeforeDelete / AfterDelete |
| Thay đổi association | BeforeLinkSave / AfterLinkSave hoặc event liên kết tương ứng |

Trình tự chính xác và event phát ra phụ thuộc loại thao tác, loại resource và phiên bản Spring Data REST. Khi cần phụ thuộc vào thứ tự event cụ thể, hãy xác nhận bằng integration test trên version đang chạy.

Một lời gọi `repository.save(...)` từ service hoặc batch job không nên mặc định được xem là đi qua cùng Spring Data REST event pipeline. Nếu logic phải chạy cho mọi cách ghi dữ liệu, hãy gọi service/domain logic chung ở mọi entry point hoặc dùng cơ chế persistence event phù hợp.

## 10. Những lỗi thường gặp khi handler không chạy

Nếu request đi qua Spring Data REST nhưng handler không được gọi, kiểm tra:

1. Handler có thực sự là Spring bean không?
2. Package chứa handler có nằm trong component scan không?
3. Class có `@RepositoryEventHandler` không?
4. Domain type trong `@RepositoryEventHandler(Person.class)` có đúng với entity được export không?
5. Method có annotation lifecycle đúng, ví dụ `@HandleBeforeCreate` không?
6. Tham số method có kiểu domain tương ứng không?
7. Method có visibility/signature phù hợp với API của Spring Data REST version đang dùng không?
8. Request có thực sự đi qua Spring Data REST repository resource không?
9. Có nhiều bean handler cùng nhận một event và gây nhầm lẫn không?
10. Handler có được đăng ký trùng qua cả `@Component` và `@Bean` không?

Để debug, có thể đặt breakpoint trong constructor để xác nhận bean được tạo và trong method handler để xác nhận event được dispatch. Log tên event, domain type và ID của entity; tránh log toàn bộ dữ liệu nhạy cảm.

## 11. Kiểm thử handler

Có thể kiểm tra logic handler bằng unit test trực tiếp:

~~~java
@Test
void trimsPersonNamesBeforeCreate() {
    PersonEventHandler handler =
            new PersonEventHandler(personService);

    Person person = new Person();
    person.setFirstName(" An ");
    person.setLastName(" Nguyen ");

    handler.handleBeforeCreate(person);

    assertThat(person.getFirstName()).isEqualTo("An");
    assertThat(person.getLastName()).isEqualTo("Nguyen");
}
~~~

Unit test xác nhận logic method. Để xác nhận Spring Data REST phát event và tìm thấy bean, cần integration test khởi động application context và gọi repository REST endpoint:

~~~java
mockMvc.perform(
        post("/api/people")
            .contentType("application/json")
            .accept("application/hal+json")
            .content("""
                {
                  "firstName": " An ",
                  "lastName": " Nguyen "
                }
                """)
    )
    .andExpect(status().isCreated());
~~~

Sau request, kiểm tra dữ liệu đã lưu hoặc representation trả về để xác nhận handler thực sự chạy. Test nên dùng repository/database test fixture phù hợp với ứng dụng.

## 12. Ghi nhớ

- Handler phải là Spring bean để Spring Data REST phát hiện.
- `@Component` là cách phổ biến để đăng ký bean qua component scanning; `@Bean` cũng có thể dùng.
- `@RepositoryEventHandler(Person.class)` giới hạn handler vào domain type Person.
- `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleAfterSave`, `@HandleBeforeDelete` và các annotation liên quan chọn lifecycle event.
- Kiểu tham số method nên khớp domain object mà handler xử lý.
- Before event phù hợp với logic cần chạy trước thao tác; After event phù hợp với hậu xử lý.
- Domain type scope không phải authorization và không giới hạn field request.
- Event handler phục vụ Spring Data REST lifecycle; không giả định mọi lệnh repository từ bất kỳ nơi nào cũng đi qua pipeline này.
- Side effect ngoài transaction cần thiết kế retry/idempotency và tính nhất quán rõ ràng.

## Tài liệu tham khảo

- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST API — RepositoryEventHandler](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/annotation/RepositoryEventHandler.html)
- [Spring Data REST API — HandleBeforeCreate](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/annotation/HandleBeforeCreate.html)
- [Spring Framework — Bean definition and component scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html)
