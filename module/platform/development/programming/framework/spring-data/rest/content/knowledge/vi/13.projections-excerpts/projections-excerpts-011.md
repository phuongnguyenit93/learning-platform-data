# Giới hạn của projection đối với đầu vào ghi, phân quyền và hợp đồng DTO

## Mục tiêu

Trong Spring Data REST, projection và excerpt giúp định hình representation mà client nhìn thấy khi đọc dữ liệu. Tuy nhiên, chúng không tự trở thành cơ chế kiểm soát dữ liệu được phép ghi, không thay thế phân quyền và cũng không định nghĩa đầy đủ một hợp đồng DTO cho các thao tác tạo/cập nhật.

Cần tách biệt ba trách nhiệm:

- **Projection/Excerpt:** quyết định representation đọc được serialize như thế nào.
- **Authorization:** quyết định ai được phép thực hiện thao tác nào trên resource/dữ liệu nào.
- **DTO và write model:** xác định chính xác dữ liệu đầu vào/đầu ra của một use case và cách dữ liệu đó được chuyển thành thay đổi domain.

Nếu dùng projection như một hàng rào bảo mật hoặc như whitelist cho request body, ứng dụng có thể vô tình cho phép ghi những field mà client không nên điều khiển.

## 1. Projection và Excerpt phục vụ representation đọc

Projection trong Spring Data REST thường được khai báo bằng `@Projection`. Nó mô tả một view của domain object để serialize ra response.

Ví dụ domain type:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private boolean active;

    private BigDecimal salary;

    // getters and setters
}
~~~

Projection công khai một số thuộc tính:

~~~java
@Projection(name = "summary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();

    boolean isActive();
}
~~~

Client có thể yêu cầu projection qua query parameter:

~~~http
GET /api/people/42?projection=summary
Accept: application/hal+json
~~~

Representation trả về có thể chỉ chứa các thuộc tính được projection công bố cùng hypermedia links:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "active": true,
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people/42"
    }
  }
}
~~~

Các field không nằm trong projection, ví dụ `email` hoặc `salary`, không xuất hiện trong view này. Điều đó chỉ nói về representation được tạo cho response; nó không có nghĩa các field đã bị xóa khỏi entity hay bị khóa ở tầng ghi.

### Projection không tạo một entity mới

Projection không phải một bản ghi database riêng và cũng không phải một bản sao domain object mà client có thể ghi ngược lại. Nó là một cách trình bày dữ liệu từ domain object.

Một projection có thể:

- Chọn một tập getter được đưa vào response.
- Kết hợp các thuộc tính từ object hiện tại và association được expose.
- Đổi hình dạng representation cho một use case đọc cụ thể.
- Cung cấp view gọn hơn cho client.

Projection không tự:

- Tạo một bảng hoặc entity riêng.
- Thay đổi quyền đọc/ghi trên field.
- Xác thực request body.
- Ngăn client gửi một field ngoài projection trong POST/PUT/PATCH.
- Thực hiện mapping một request DTO thành command nghiệp vụ.

## 2. Excerpt là projection mặc định cho collection

Excerpt projection là projection được Spring Data REST áp dụng mặc định cho các item khi chúng được render bên trong collection resource, nếu có excerpt projection được cấu hình/đăng ký cho domain type.

Ví dụ:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Khi client gọi:

~~~http
GET /api/people
Accept: application/hal+json
~~~

các phần tử trong `_embedded.people` có thể dùng representation `PersonSummary`. Khi gọi trực tiếp item URI, client có thể nhận representation mặc định của item hoặc yêu cầu projection cụ thể theo cấu hình.

Excerpt giúp collection list nhẹ hơn và nhất quán hơn với nhu cầu hiển thị danh sách. Nó không phải whitelist của các field mà POST hoặc PUT được phép nhận.

## 3. Projection không giới hạn request body khi ghi

Một nhầm lẫn nguy hiểm là: “Nếu projection chỉ expose ba field thì client chỉ có thể ghi ba field đó.” Đây không phải cam kết của Spring Data REST.

Ví dụ projection chỉ expose:

~~~java
@Projection(name = "publicView", types = Person.class)
public interface PersonPublicView {

    String getFirstName();

    String getLastName();
}
~~~

Nhưng entity còn có:

~~~java
private String email;
private BigDecimal salary;
private boolean admin;
~~~

Projection không tự ngăn request POST/PUT gửi các field này. Request body khi ghi được deserialize theo mapping và cấu hình Jackson/domain type của ứng dụng, sau đó đi vào luồng lưu repository. Projection được chọn để serialize response không phải bộ lọc đầu vào.

Ví dụ, client có thể cố gửi:

~~~http
POST /api/people
Content-Type: application/json

{
  "firstName": "An",
  "lastName": "Nguyen",
  "salary": 999999,
  "admin": true
}
~~~

Nếu các thuộc tính được bind và không có cơ chế bảo vệ phù hợp, việc chúng vắng mặt trong projection đọc không bảo đảm chúng bị từ chối trong request body. Tùy cấu hình Jackson, visibility, setter, mapping và security, các field có thể được bind, bị bỏ qua hoặc gây lỗi. Không dựa vào projection để quyết định kết quả đó.

Đặc biệt, các field nhạy cảm như `role`, `admin`, `ownerId`, `approved`, `balance` hoặc `salary` cần được bảo vệ rõ ràng ở write boundary và domain/service layer.

## 4. Phân quyền là trách nhiệm riêng

Authorization quyết định principal hiện tại được phép thực hiện thao tác nào. Projection chỉ điều chỉnh representation; việc ẩn một field khỏi response không làm field đó an toàn trước request ghi hoặc truy cập trực tiếp khác.

Ví dụ, một API có thể cho mọi người dùng đã đăng nhập đọc danh sách Person nhưng chỉ HR được sửa salary. Quy tắc này cần được thực thi bằng Spring Security, service authorization hoặc policy phù hợp.

Một cấu hình URL-level minh họa:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/people/**")
                .hasAuthority("people:read")
            .requestMatchers(HttpMethod.POST, "/api/people")
                .hasAuthority("people:create")
            .requestMatchers(HttpMethod.PUT, "/api/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.PATCH, "/api/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.DELETE, "/api/people/**")
                .hasAuthority("people:delete")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Đây là ví dụ minh họa cho việc tách quyền theo HTTP method và resource path. Ứng dụng thực tế cần cấu hình authentication, CSRF, CORS và các rule còn lại phù hợp với kiểu client/API đang sử dụng.

### URL-level authorization chưa đủ cho mọi trường hợp

Quyền thao tác có thể phụ thuộc vào dữ liệu cụ thể:

- Người dùng chỉ được sửa Person thuộc phòng ban của mình.
- Người tạo được sửa bản ghi khi bản ghi còn ở trạng thái DRAFT.
- Chỉ quản lý mới được thay đổi trạng thái phê duyệt.
- Người dùng chỉ được xem dữ liệu của chính mình.

Các rule này cần kiểm tra ở service/domain boundary hoặc method security, không chỉ dựa trên URL.

Ví dụ method security:

~~~java
@Service
public class PersonService {

    @PreAuthorize("hasAuthority('people:update')")
    public Person updatePerson(Long id, UpdatePersonCommand command) {
        // Load entity, enforce ownership/business rules, apply allowed changes.
        // Save through repository.
        return null;
    }
}
~~~

Phần thân ở trên chỉ minh họa vị trí đặt authorization; ứng dụng cần triển khai việc tải entity, kiểm tra quyền trên bản ghi và áp dụng thay đổi thực tế.

### Ẩn field trong response không phải authorization

Nếu `salary` không xuất hiện trong `PersonPublicView`, client không thấy salary trong representation đó. Nhưng điều này không chứng minh client không thể:

- Gửi `salary` trong request body.
- Gọi một endpoint khác trả salary.
- Theo association/link tới một resource có dữ liệu nhạy cảm.
- Sử dụng một projection khác expose salary.

Hãy bảo vệ dữ liệu nhạy cảm ở mọi đường đọc và ghi bằng policy nhất quán. Projection có thể hỗ trợ giảm dữ liệu trả về, nhưng không thay thế access control.

## 5. DTO xác định hợp đồng đầu vào rõ ràng

DTO (Data Transfer Object) là kiểu dữ liệu được thiết kế cho một ranh giới giao tiếp cụ thể. Với thao tác ghi, DTO giúp chỉ rõ client được phép gửi những field nào.

Ví dụ:

~~~java
public record CreatePersonRequest(
        @NotBlank String firstName,
        @NotBlank String lastName,
        @Email String email
) {
}
~~~

DTO này chỉ có ba field đầu vào. Client không có field `salary`, `admin` hoặc `approved` trong contract tạo Person.

Một custom controller có thể nhận DTO:

~~~java
@RestController
@RequestMapping("/api/person-commands")
public class PersonCommandController {

    private final PersonService personService;

    public PersonCommandController(PersonService personService) {
        this.personService = personService;
    }

    @PostMapping
    public ResponseEntity<PersonResponse> create(
            @Valid @RequestBody CreatePersonRequest request) {

        PersonResponse response = personService.create(request);

        return ResponseEntity
                .created(URI.create("/api/people/" + response.id()))
                .body(response);
    }
}
~~~

Ví dụ này minh họa ranh giới API riêng cho command tạo Person. Trong ứng dụng thực tế, URI Location nên lấy từ URI resource do ứng dụng tạo hoặc từ link/resource mapping phù hợp, không hard-code nếu path có thể thay đổi.

Service ánh xạ DTO sang domain:

~~~java
@Service
public class PersonService {

    private final PersonRepository repository;

    public PersonService(PersonRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("hasAuthority('people:create')")
    public PersonResponse create(CreatePersonRequest request) {
        Person person = new Person();
        person.setFirstName(request.firstName());
        person.setLastName(request.lastName());
        person.setEmail(request.email());

        // Sensitive or server-owned values are assigned by trusted logic.
        person.setActive(true);
        person.setAdmin(false);

        Person saved = repository.save(person);

        return new PersonResponse(
                saved.getId(),
                saved.getFirstName(),
                saved.getLastName(),
                saved.getEmail()
        );
    }
}
~~~

Ví dụ trên cho thấy chỉ các field được phép từ DTO mới được copy sang entity. Giá trị do server quản lý được gán bằng logic tin cậy. DTO không tự cấp quyền; service vẫn cần authorization và kiểm tra nghiệp vụ.

## 6. Tách Create, Update và Response DTO khi contract khác nhau

Một DTO dùng chung cho mọi thao tác có thể khiến API khó kiểm soát. Tạo mới và cập nhật thường có yêu cầu khác nhau:

| DTO | Mục đích | Ví dụ field |
|---|---|---|
| `CreatePersonRequest` | Tạo Person | firstName, lastName, email |
| `UpdatePersonRequest` | Cập nhật các field được phép | firstName, lastName, email |
| `PersonResponse` | Dữ liệu trả về cho client | id, firstName, lastName, status |
| `PersonAdminResponse` | View riêng cho người có quyền | Thêm field quản trị được phép đọc |

Ví dụ response DTO:

~~~java
public record PersonResponse(
        Long id,
        String firstName,
        String lastName,
        String email
) {
}
~~~

Không đưa các field nội bộ như password hash, access token hoặc cờ quản trị vào response DTO công khai. Nếu một vai trò được phép xem thêm dữ liệu, có thể định nghĩa response contract riêng hoặc policy serialization có kiểm soát.

DTO nên phản ánh use case và quyền sở hữu field:

- Field do client nhập.
- Field do server tạo, ví dụ ID, timestamp.
- Field do workflow quản lý, ví dụ approved/status.
- Field chỉ một vai trò được đọc.
- Field nội bộ không được expose.

## 7. DTO và projection có thể cùng tồn tại

Projection và DTO không loại trừ nhau. Chúng phục vụ các hướng dữ liệu khác nhau:

~~~text
READ
Repository / Domain
       |
       v
Projection / Excerpt
       |
       v
HAL representation
       |
       v
Client

WRITE
Client request
       |
       v
Create/Update DTO
       |
       v
Validation + Authorization
       |
       v
Application Service
       |
       v
Domain changes + Repository save
       |
       v
Response DTO / HAL resource
~~~

Ví dụ:

- Collection GET dùng excerpt projection để trả danh sách gọn.
- Item GET cho phép client chọn projection phù hợp.
- POST nhận CreatePersonRequest qua custom controller.
- PUT/PATCH nhận UpdatePersonRequest hoặc command chuyên biệt.
- Service xác thực, kiểm tra quyền trên entity và chỉ áp dụng field được phép.
- Response trả DTO hoặc resource representation phù hợp.

Khi dùng Spring Data REST repository endpoint trực tiếp cho write, request body thường được deserialize thành domain representation theo cấu hình của ứng dụng. Nếu cần một input contract nghiêm ngặt theo từng use case, custom controller/application service với DTO thường rõ ràng và dễ kiểm soát hơn.

## 8. Các công cụ Jackson không thay thế DTO/policy

Jackson có annotation điều khiển serialization/deserialization, ví dụ:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private String systemCode;

@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String internalNote;
~~~

- `READ_ONLY`: field có thể xuất hiện khi serialize nhưng bị bỏ qua khi deserialize theo cấu hình Jackson.
- `WRITE_ONLY`: field được nhận khi deserialize nhưng không xuất hiện khi serialize.

Các annotation này có thể hữu ích cho một số contract đơn giản, nhưng không phải authorization. Chúng không tự kiểm tra người dùng có quyền ghi field hay không và không thay thế validation/business rules. Cũng cần xem xét mọi serializer/deserializer, projection, controller và endpoint khác đang dùng cùng entity.

Đừng dùng `@JsonIgnore` hoặc visibility tùy tiện như một biện pháp bảo vệ duy nhất cho field nhạy cảm. Hãy kiểm tra toàn bộ các đường đọc/ghi và thực thi quyền ở tầng thích hợp.

## 9. Những nhầm lẫn thường gặp

- **Projection chỉ có ba field nên request ghi chỉ nhận ba field.** Sai: projection định hình representation đọc; request binding là một luồng riêng.
- **Field bị ẩn trong response thì người dùng không thể sửa field đó.** Sai: cần write validation, DTO allowlist và authorization.
- **Excerpt là DTO tạo mới.** Sai: excerpt là projection mặc định cho item trong collection representation.
- **Projection kiểm soát ai được đọc field.** Không tự động; phải có access control hoặc representation policy phù hợp.
- **DTO tự bảo vệ endpoint.** DTO định nghĩa shape dữ liệu, nhưng vẫn cần validation, authorization và kiểm tra nghiệp vụ.
- **Chỉ kiểm tra quyền theo URL là đủ.** Một số quyền phụ thuộc owner, tenant, trạng thái hoặc quan hệ của bản ghi.
- **Dùng chung entity cho mọi request là an toàn.** Entity có thể chứa field nội bộ mà client không nên điều khiển; dùng DTO/command giúp giới hạn rõ đầu vào.
- **Jackson annotation là phân quyền.** Annotation điều khiển serialization/binding; nó không quyết định principal có quyền thao tác hay không.

## 10. Checklist thiết kế API

Khi thiết kế Spring Data REST có projection và thao tác ghi, hãy trả lời riêng từng câu hỏi:

1. **Read representation:** Client nào cần xem field nào? Projection/excerpt nào phù hợp?
2. **Write input:** Client được phép gửi chính xác những field nào cho từng use case?
3. **Validation:** Field bắt buộc, format, giới hạn và invariant nào phải được kiểm tra?
4. **Authorization:** Ai được tạo, đọc, sửa, xóa? Quyền có phụ thuộc bản ghi/tenant/trạng thái không?
5. **Server-owned fields:** Field nào phải do server hoặc workflow gán?
6. **DTO contract:** Create, update và response có cần kiểu riêng không?
7. **Mapping:** Field nào được copy từ DTO vào domain? Có field nào phải bỏ qua hoặc tính lại?
8. **Response exposure:** Projection/response DTO có vô tình lộ dữ liệu nhạy cảm không?
9. **Endpoint coverage:** Có đường đọc/ghi khác nào bypass policy đã thiết kế không?
10. **Tests:** Có test payload chứa field không được phép, user thiếu quyền, owner khác và response không lộ field nhạy cảm không?

## 11. Ghi nhớ

- Projection và excerpt điều khiển cách domain data được trình bày trong response đọc.
- Projection không phải whitelist của POST/PUT/PATCH và không tự giới hạn field được ghi.
- Ẩn field trong representation không đồng nghĩa đã bảo vệ field đó.
- Authorization phải được thực thi độc lập ở HTTP security và/hoặc service/domain boundary.
- DTO/command xác định input contract cho từng use case; service ánh xạ các field được phép sang domain object.
- Create, update và response có thể cần DTO riêng.
- Jackson annotation hỗ trợ serialization/binding nhưng không thay thế phân quyền.
- Với write contract nghiêm ngặt, custom controller + DTO + application service thường tạo ranh giới rõ ràng hơn việc nhận trực tiếp entity qua repository REST endpoint.

## Tài liệu tham khảo

- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Jackson Annotations — JsonProperty.Access](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
