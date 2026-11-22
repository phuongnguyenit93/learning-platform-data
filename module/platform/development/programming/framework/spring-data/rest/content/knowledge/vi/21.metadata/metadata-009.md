# Khả năng và giới hạn của metadata đối với validation, phân quyền và nghiệp vụ

## Mục tiêu

Metadata giúp client khám phá API và hiểu hình dạng dữ liệu mà Spring Data REST công bố. Nó có thể mô tả resource, thuộc tính, các chuyển tiếp REST, projection và cấu trúc JSON. Nhờ vậy, frontend, công cụ khám phá API hoặc tài liệu có thể biết nên gọi endpoint nào và chuẩn bị dữ liệu ra sao.

Tuy nhiên, metadata là thông tin mô tả được công bố cho client. Nó không tự thực thi quy tắc trên server. Cần phân biệt ba trách nhiệm:

- **Validation:** dữ liệu gửi lên có đúng cấu trúc, định dạng và ràng buộc hay không?
- **Authorization:** principal hiện tại có được phép đọc hoặc thực hiện thao tác trên resource cụ thể hay không?
- **Business rules:** thao tác có hợp lệ theo trạng thái, quan hệ và invariant của domain hay không?

ALPS và JSON Schema hỗ trợ mô tả contract. Spring Validator/Bean Validation kiểm tra dữ liệu. Spring Security quyết định quyền. Application service và domain model bảo vệ quy tắc nghiệp vụ.

## 1. Metadata trong Spring Data REST là gì?

Spring Data REST phân tích repository và domain model để công bố hypermedia-driven REST API. Bên cạnh các resource và link, ứng dụng có thể cung cấp metadata để client khám phá ngữ nghĩa và cấu trúc của API.

Hai dạng metadata quan trọng là:

- **ALPS (Application-Level Profile Semantics):** mô tả ngữ nghĩa của representation và các chuyển tiếp REST được công bố.
- **JSON Schema:** mô tả cấu trúc dữ liệu, kiểu thuộc tính và một số đặc tính của representation.

Một root resource thường có link `profile`:

~~~json
{
  "_links": {
    "people": {
      "href": "https://api.example.com/people"
    },
    "profile": {
      "href": "https://api.example.com/profile"
    }
  }
}
~~~

Client theo link `profile` để khám phá metadata. Từ đó, nó có thể tìm profile dành cho repository, ví dụ `/profile/people`. URI thực tế phải lấy từ hypermedia link của server; ví dụ trên chỉ minh họa.

## 2. ALPS mô tả thuộc tính và chuyển tiếp REST

Spring Data REST cung cấp ALPS document cho mỗi repository được export. ALPS có thể mô tả các thuộc tính của resource và những chuyển tiếp REST như GET collection, GET item, POST, PUT, PATCH hoặc DELETE.

Ví dụ rút gọn về ALPS descriptor:

~~~json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person-representation",
      "descriptors": [
        {
          "name": "firstName",
          "type": "SEMANTIC"
        },
        {
          "name": "lastName",
          "type": "SEMANTIC"
        }
      ]
    },
    {
      "id": "create-people",
      "name": "people",
      "type": "UNSAFE",
      "rt": "#person-representation"
    },
    {
      "id": "get-people",
      "name": "people",
      "type": "SAFE",
      "rt": "#person-representation"
    }
  ]
}
~~~

Các descriptor giúp client hiểu một số thông tin:

- `person-representation` mô tả các thuộc tính của representation Person.
- `firstName` và `lastName` là các semantic descriptor của dữ liệu.
- `get-people` mô tả một chuyển tiếp đọc collection.
- `create-people` mô tả một chuyển tiếp tạo resource và representation liên quan.

ALPS phân loại hypermedia control bằng các type phổ biến:

| Type | Ý nghĩa khái quát |
|---|---|
| `SEMANTIC` | Thuộc tính hoặc dữ liệu mang ngữ nghĩa trong representation |
| `SAFE` | Chuyển tiếp an toàn, không làm thay đổi trạng thái server, thường là GET/HEAD |
| `IDEMPOTENT` | Chuyển tiếp có thể thay đổi trạng thái nhưng lặp lại cùng request có semantics idempotent, thường là PUT/DELETE |
| `UNSAFE` | Chuyển tiếp có thể làm thay đổi trạng thái và không có semantics idempotent, thường là POST |

Các type này mô tả semantics của thao tác HTTP. `UNSAFE` không có nghĩa thao tác bị cấm hoặc người gọi có quyền cao; `SAFE` cũng không có nghĩa mọi người đều được phép đọc. Chúng không phải role, permission hay policy.

## 3. JSON Schema mô tả cấu trúc dữ liệu

Spring Data REST hỗ trợ JSON Schema như một dạng metadata khác. Client có thể yêu cầu schema từ profile link của repository bằng media type `application/schema+json`.

Ví dụ request:

~~~http
GET /profile/people
Accept: application/schema+json
~~~

URI cần được lấy từ profile link tương ứng trong API đang chạy. Một schema minh họa có thể có dạng:

~~~json
{
  "title": "Person",
  "type": "object",
  "properties": {
    "firstName": {
      "type": "string",
      "readOnly": false
    },
    "lastName": {
      "type": "string",
      "readOnly": false
    },
    "createdAt": {
      "type": "string",
      "format": "date-time",
      "readOnly": true
    }
  }
}
~~~

Schema có thể giúp client:

- Hiển thị danh sách thuộc tính và kiểu dữ liệu.
- Chọn input phù hợp, ví dụ text, number, date-time hoặc URI.
- Phân biệt một số field chỉ đọc với field có thể nhập.
- Tạo tài liệu, form hoặc kiểm tra cấu trúc JSON ở phía client.
- Viết contract test dựa trên hình dạng dữ liệu được công bố.

Ví dụ chỉ minh họa cấu trúc. Schema thực tế được tạo từ domain model và cấu hình của ứng dụng; tập thuộc tính, format, descriptor và khả năng diễn đạt ràng buộc có thể khác nhau theo version.

### Schema không phải bản sao đầy đủ của validation logic

JSON Schema có thể biểu diễn nhiều ràng buộc cấu trúc, nhưng schema do API công bố không nhất thiết thể hiện mọi quy tắc đang chạy trên server.

Các quy tắc sau thường cần logic bổ sung:

- Email phải duy nhất trong database.
- Ngày kết thúc phải sau ngày bắt đầu.
- Một Order chỉ được xác nhận khi còn ở trạng thái DRAFT.
- Người dùng chỉ được sửa dữ liệu thuộc tenant của mình.
- Số lượng đặt hàng không được vượt lượng tồn kho tại thời điểm commit.
- Giá trị chỉ hợp lệ khi kết hợp với vai trò hoặc trạng thái hiện tại.

Một schema có thể giúp client phát hiện lỗi đơn giản trước khi gửi request, nhưng không thể thay thế kiểm tra trên dữ liệu và trạng thái hiện tại ở server.

## 4. ALPS và JSON Schema có thể hỗ trợ client đến đâu?

Metadata hữu ích nhất khi được xem là một phần của API discovery và contract documentation.

Ví dụ frontend có thể:

1. GET root resource.
2. Theo link `profile` để tìm metadata của repository.
3. Đọc ALPS để biết resource có những thuộc tính và chuyển tiếp nào.
4. Yêu cầu JSON Schema để biết kiểu dữ liệu và cấu trúc field.
5. Dùng thông tin đó để tạo form hoặc hiển thị hướng dẫn.
6. Gửi request đến link resource/transition do server công bố.
7. Xử lý response thành công hoặc lỗi validation/authorization từ server.

Client có thể dùng metadata để cải thiện trải nghiệm và giảm request sai định dạng. Nhưng client không được tự coi metadata là bằng chứng rằng một thao tác chắc chắn được phép hoặc chắc chắn hợp lệ tại thời điểm ghi.

## 5. Metadata không thực thi validation phía server

Giả sử JSON Schema mô tả `firstName` là string. Client có thể tạo text input và từ chối giá trị rỗng trước khi gửi. Nhưng một client khác có thể bỏ qua form, tự tạo HTTP request hoặc gọi API bằng curl.

Vì vậy, server phải tự kiểm tra request.

### Bean Validation

Có thể khai báo constraint trên entity hoặc DTO:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public class CreatePersonRequest {

    @NotBlank
    private String firstName;

    @NotBlank
    private String lastName;

    @Email
    private String email;

    // getters and setters
}
~~~

Các annotation diễn tả những constraint đơn giản:

- `@NotBlank`: chuỗi phải có nội dung sau khi xét khoảng trắng.
- `@Email`: kiểm tra định dạng email theo validator đang dùng.

Đối với custom Spring MVC controller, có thể kích hoạt validation trên request DTO bằng `@Valid`:

~~~java
@PostMapping("/people")
public ResponseEntity<PersonResponse> create(
        @Valid @RequestBody CreatePersonRequest request) {

    PersonResponse response = personService.create(request);
    return ResponseEntity.status(HttpStatus.CREATED).body(response);
}
~~~

Với repository REST endpoint, có thể đăng ký Spring `Validator` theo repository event:

~~~java
@Configuration
public class RepositoryValidationConfig
        implements RepositoryRestConfigurer {

    private final PersonValidator personValidator;

    public RepositoryValidationConfig(PersonValidator personValidator) {
        this.personValidator = personValidator;
    }

    @Override
    public void configureValidatingRepositoryEventListener(
            ValidatingRepositoryEventListener listener) {
        listener.addValidator("beforeCreate", personValidator);
        listener.addValidator("beforeSave", personValidator);
    }
}
~~~

Validator kiểm tra target và ghi lỗi vào `Errors`:

~~~java
@Component
public class PersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Person.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getFirstName() == null
                || person.getFirstName().isBlank()) {
            errors.rejectValue(
                "firstName",
                "person.firstName.required",
                "First name is required"
            );
        }
    }
}
~~~

Đăng ký validator theo đúng lifecycle event và domain type. Validation lỗi cần được chuyển thành response lỗi theo cơ chế Spring Data REST/Spring MVC đang dùng. Không giả định JSON Schema tự gọi validator hoặc request sẽ bị từ chối chỉ vì client đã nhận schema.

## 6. Validation cấu trúc khác business validation

Nên phân biệt ít nhất hai lớp:

| Loại kiểm tra | Ví dụ | Nơi phù hợp |
|---|---|---|
| Cấu trúc/format | Field bắt buộc, email đúng định dạng, số nằm trong khoảng | Bean Validation hoặc request validator |
| Quy tắc nghiệp vụ | Order chỉ được xác nhận khi đủ điều kiện, số lượng không vượt tồn kho | Application service/domain model, có transaction khi cần |

Một số constraint đơn giản có thể xuất hiện trong schema hoặc được client kiểm tra trước. Nhưng các quy tắc phụ thuộc database, thời gian, trạng thái hoặc dữ liệu của người dùng khác phải được kiểm tra lại ở server tại thời điểm xử lý.

Ví dụ, client đọc tồn kho là 5 và gửi yêu cầu đặt 4 sản phẩm. Một client khác có thể đặt 3 sản phẩm trước đó. Kiểm tra phía client dựa trên số tồn kho cũ không đủ để bảo đảm thao tác còn hợp lệ. Server phải kiểm tra và cập nhật tồn kho một cách nhất quán, thường trong transaction và với concurrency control phù hợp.

## 7. Metadata và phân quyền là hai việc khác nhau

Authorization xác định principal hiện tại được phép làm gì. Metadata mô tả API và các chuyển tiếp mà client có thể khám phá.

ALPS có thể mô tả một thao tác là `UNSAFE`, hoặc HAL response có thể chứa link đến một thao tác. Những thông tin đó không tự chứng minh người dùng hiện tại được phép thực hiện thao tác.

Ví dụ client nhìn thấy collection link:

~~~json
{
  "_links": {
    "people": {
      "href": "https://api.example.com/people"
    }
  }
}
~~~

Client có thể thử POST đến collection, nhưng server vẫn phải xác thực và kiểm tra quyền. Việc ẩn link trong response có thể giúp giao diện không hiển thị nút không phù hợp; nó không phải lớp bảo vệ duy nhất.

### Thực thi quyền ở Spring Security

Có thể bảo vệ HTTP request theo method và path:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/people/**")
                .hasAuthority("people:read")
            .requestMatchers(HttpMethod.POST, "/people")
                .hasAuthority("people:create")
            .requestMatchers(HttpMethod.PUT, "/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.PATCH, "/people/**")
                .hasAuthority("people:update")
            .requestMatchers(HttpMethod.DELETE, "/people/**")
                .hasAuthority("people:delete")
            .anyRequest().authenticated()
        )
        .build();
}
~~~

Đây là ví dụ minh họa URL-level authorization. Ứng dụng cần cấu hình authentication, CSRF, CORS và các matcher còn lại theo kiến trúc thực tế.

### Quyền trên từng resource

Quyền có thể phụ thuộc vào bản ghi, không chỉ method và URL:

- User chỉ được sửa Person thuộc tenant của mình.
- Chỉ người tạo hoặc quản lý mới được sửa một bản ghi.
- Chỉ HR mới được xem trường salary.
- Chỉ người có quyền phù hợp mới được chuyển Order sang trạng thái APPROVED.

Có thể dùng method security ở service:

~~~java
@Service
public class PersonService {

    @PreAuthorize("hasAuthority('people:update')")
    public PersonResponse update(Long id, UpdatePersonRequest request) {
        // Load entity and verify ownership/tenant policy.
        // Apply allowed changes and save.
        return null;
    }
}
~~~

`@PreAuthorize` kiểm tra authority trước khi gọi method. Kiểm tra ownership/tenant của chính entity vẫn cần được thực hiện bằng logic phù hợp. Một URL rule tổng quát không thể tự biết người dùng có quyền sửa đúng bản ghi này hay không.

## 8. Metadata không thực thi business rules

Business rule là điều kiện quyết định một hành động có hợp lệ trong domain hay không. Ví dụ:

- Không thể thanh toán một Order đã bị hủy.
- Không thể chuyển trạng thái từ DELIVERED về DRAFT.
- Không thể đặt số lượng lớn hơn lượng tồn khả dụng.
- Không thể duyệt một yêu cầu do chính người duyệt tạo.
- Ngày bắt đầu phải trước ngày kết thúc.
- Tổng chiết khấu không được vượt giới hạn hợp đồng.

Metadata có thể mô tả field `status` là string hoặc liệt kê một số trạng thái tĩnh. Nhưng việc một chuyển đổi trạng thái có hợp lệ hay không phụ thuộc trạng thái hiện tại, principal, dữ liệu liên quan và thời điểm xử lý.

Nên bảo vệ invariant trong application service/domain model:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Order approve(Long id, User currentUser) {
        Order order = repository.findById(id)
            .orElseThrow(() -> new EntityNotFoundException());

        if (order.getStatus() != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only draft orders can be approved"
            );
        }

        if (order.getCreatedBy().equals(currentUser.getId())) {
            throw new AccessDeniedException(
                "The creator cannot approve this order"
            );
        }

        order.setStatus(OrderStatus.APPROVED);
        return repository.save(order);
    }
}
~~~

Đây là ví dụ rút gọn. Trong ứng dụng thật, lấy principal từ security context, xử lý lỗi bằng exception mapping phù hợp và đặt kiểm tra concurrency/transaction theo yêu cầu domain.

Điểm quan trọng là request không được phép tự quyết định trạng thái cuối cùng chỉ bằng cách gửi `"status": "APPROVED"`. Service/domain phải kiểm tra transition và actor có hợp lệ hay không.

## 9. Metadata có thể bị tùy chỉnh hoặc không đầy đủ

Metadata phản ánh những gì ứng dụng công bố tại thời điểm request. Nó có thể chịu ảnh hưởng bởi:

- Repository nào được export.
- Domain model và association.
- Projection được đăng ký.
- Cấu hình Spring Data REST.
- Customization của representation hoặc controller.
- Version thư viện và media type được yêu cầu.

ALPS có thể bổ sung mô tả bằng các message properties như `rest.description.*`. Những mô tả này giúp giải thích resource và field bằng ngôn ngữ dễ hiểu. Chúng vẫn chỉ là documentation.

Ví dụ:

~~~properties
rest.description.person=A collection of people
rest.description.person.firstName=Person's first name
rest.description.person.lastName=Person's last name
~~~

Các mô tả trên giúp client hiểu ý nghĩa field. Đổi `rest.description.person.firstName` không tự thêm `@NotBlank`, không tạo unique constraint và không cấp quyền truy cập field.

Nếu API có custom endpoint hoặc rule không được thể hiện trong metadata, hãy công bố contract/documentation bổ sung. Client nên xử lý response thực tế và lỗi HTTP thay vì suy luận rằng metadata đã mô tả mọi hành vi có thể xảy ra.

## 10. Bảng phân biệt trách nhiệm

| Câu hỏi | Metadata | Validation | Authorization | Business rules |
|---|---|---|---|---|
| Resource có field nào? | Mô tả qua ALPS/Schema | Không phải mục đích chính | Không phải mục đích chính | Không phải mục đích chính |
| Field có kiểu gì? | JSON Schema mô tả | Kiểm tra kiểu/format đầu vào | Không quyết định | Có thể dùng kiểu trong domain |
| Field có bắt buộc không? | Có thể mô tả nếu schema thể hiện | Server phải xác thực | Không quyết định | Có thể là invariant |
| Ai được đọc/sửa? | Không tự quyết định | Không quyết định | Spring Security/policy | Có thể kiểm tra actor trong use case |
| Thao tác có hợp lệ ở trạng thái hiện tại? | Không bảo đảm mô tả hết | Chỉ một phần | Có thể kiểm tra quyền | Service/domain quyết định |
| Client có thể tạo form? | Có, hỗ trợ discovery | Có thể hỗ trợ UX | Có thể ẩn affordance | Có thể hiển thị hướng dẫn |

## 11. Quy trình thiết kế và sử dụng metadata an toàn

Khi xây dựng client hoặc API Spring Data REST:

1. Khám phá root resource và theo link `profile` mà server công bố.
2. Đọc ALPS để hiểu resource, field và các transition được mô tả.
3. Yêu cầu JSON Schema bằng `Accept: application/schema+json` nếu API hỗ trợ.
4. Dùng schema để tạo form, kiểm tra cấu trúc và đưa ra lỗi sớm cho người dùng.
5. Thực thi validation trên server bằng Bean Validation, Spring Validator hoặc request DTO phù hợp.
6. Bảo vệ endpoint bằng Spring Security; kiểm tra cả quyền trên từng resource/tenant khi cần.
7. Đặt invariant và state transition trong application service/domain model.
8. Xử lý lỗi validation, 401/403 và lỗi nghiệp vụ theo response contract.
9. Kiểm thử trực tiếp HTTP request, kể cả request giả mạo bỏ qua giao diện client.
10. Cập nhật metadata và tài liệu khi contract API thay đổi.

## 12. Kiểm thử các giới hạn của metadata

Nên có các nhóm test độc lập:

- **Metadata test:** root resource có profile link; ALPS và JSON Schema trả đúng media type và mô tả đúng các field dự kiến.
- **Validation test:** request thiếu field bắt buộc hoặc sai format bị từ chối kể cả khi gọi trực tiếp endpoint.
- **Authorization test:** user không có quyền nhận 403 khi gọi URL trực tiếp, kể cả khi tự tạo request mà giao diện không cung cấp link.
- **Resource policy test:** user của tenant A không thể sửa resource thuộc tenant B.
- **Business rule test:** thao tác sai trạng thái hoặc vi phạm invariant bị từ chối dù payload đúng JSON Schema.
- **Concurrency test:** nếu rule phụ thuộc số tồn hoặc trạng thái có thể thay đổi đồng thời, kiểm tra transaction và optimistic/pessimistic locking thích hợp.

Không chỉ kiểm tra rằng frontend ẩn nút hoặc JSON Schema hiển thị `readOnly`. Hãy gửi request trực tiếp đến server để chứng minh enforcement thực sự hoạt động.

## 13. Những nhầm lẫn thường gặp

- **ALPS ghi thao tác UNSAFE nên người dùng không được gọi.** UNSAFE mô tả semantics của transition, không phải quyền truy cập.
- **Có link trong HAL nghĩa là mọi người đều được phép dùng.** Server vẫn phải kiểm tra authorization trên mỗi request.
- **Không có link nghĩa là dữ liệu được bảo vệ.** Client có thể thử gọi URI trực tiếp; security phải được thực thi ở server.
- **JSON Schema mô tả field nên server tự validate mọi rule.** Schema chỉ là metadata; request phải được validate trong server pipeline.
- **Field readOnly trong schema là hàng rào bảo mật.** Client có thể bỏ qua schema và tự gửi payload; server phải kiểm soát binding và quyền ghi.
- **Metadata mô tả status nên client có thể tự đổi status.** State transition phải được kiểm tra trong domain/service.
- **Validation thay thế authorization.** Dữ liệu hợp lệ không đồng nghĩa người gửi có quyền thao tác.
- **Authorization thay thế business rules.** Người có quyền vẫn có thể gửi thao tác vi phạm trạng thái hoặc invariant.
- **Documentation properties thay đổi hành vi API.** `rest.description.*` bổ sung mô tả, không tự thêm constraint hoặc permission.

## 14. Ghi nhớ

- Spring Data REST cung cấp ALPS và JSON Schema để khám phá semantics và cấu trúc resource.
- ALPS mô tả thuộc tính và loại chuyển tiếp; JSON Schema mô tả hình dạng dữ liệu.
- Metadata giúp tạo form, documentation và client discovery, nhưng không phải cơ chế enforcement.
- Validation phải chạy ở server; schema/client-side validation chỉ giúp phát hiện sớm lỗi đơn giản.
- Authorization phải được kiểm tra bằng Spring Security và policy theo resource khi cần.
- Business rules và state transitions phải được bảo vệ ở application service/domain model.
- Link hoặc descriptor được công bố không chứng minh principal hiện tại có quyền thực hiện thao tác.
- Hãy kiểm thử bằng request HTTP trực tiếp để chứng minh validation, authorization và business rules vẫn hoạt động khi client bỏ qua metadata.

## Tài liệu tham khảo

- [Spring Data REST Reference — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST Reference — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST Reference — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring Security Reference — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [JSON Schema Specification](https://json-schema.org/specification)
