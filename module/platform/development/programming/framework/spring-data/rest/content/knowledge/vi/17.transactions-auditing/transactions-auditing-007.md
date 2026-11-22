# Kiểm soát mass assignment và dữ liệu đầu vào ngoài dự kiến trong Spring Data REST

## Mục tiêu

Khi Spring Data REST nhận request ghi, JSON body thường được ánh xạ vào domain object rồi chuyển tới repository. Nếu client có thể gửi mọi thuộc tính mà entity hỗ trợ, một request được thiết kế để đổi vài trường có thể vô tình hoặc cố ý thay đổi cả dữ liệu nội bộ. Đây là rủi ro **mass assignment**.

Ví dụ, use case chỉ cho phép cập nhật tên hiển thị và email:

~~~http
PATCH /api/people/42
Content-Type: application/merge-patch+json

{
  "displayName": "Ada Lovelace",
  "email": "ada@example.com"
}
~~~

Một client có thể tự gửi thêm các thuộc tính không nằm trong màn hình hoặc hợp đồng ghi:

~~~json
{
  "displayName": "Ada Lovelace",
  "email": "ada@example.com",
  "role": "ADMIN",
  "tenantId": "tenant-other",
  "approved": true,
  "createdBy": "attacker"
}
~~~

Nếu các trường đó tồn tại trên entity và có thể được bind, server có nguy cơ lưu thay đổi ngoài quyền của người gọi.

Mục tiêu của việc kiểm soát mass assignment là xác định chính xác **ai được ghi trường nào, qua endpoint nào và trong điều kiện nào**. Cần kết hợp kiểm soát JSON binding, allowlist input, validation, authorization và quy tắc domain. Việc ẩn trường trên UI hoặc ẩn link HAL không bảo vệ được request được gửi trực tiếp.

## 1. Mass assignment xảy ra ở đâu trong luồng ghi?

Một request ghi điển hình của Spring Data REST có thể được hình dung như sau:

~~~text
HTTP request
    |
    v
Spring Security authentication / authorization
    |
    v
Spring MVC message converter (Jackson)
    |
    v
Domain object / association binding
    |
    v
Repository event handlers and validation
    |
    v
Repository save / database
    |
    v
HTTP response representation
~~~

Rủi ro xuất hiện ở giai đoạn binding: dữ liệu JSON được ánh xạ vào các property mà object cho phép nhận. Sau đó, repository có thể lưu object đã bị thay đổi.

Cần kiểm soát nhiều điểm:

- **Trước binding:** xác định endpoint và request contract cho phép những trường nào.
- **Trong binding:** ngăn các property server-managed nhận giá trị từ JSON.
- **Trước khi lưu:** kiểm tra giá trị, quyền và domain invariant.
- **Khi truy cập quan hệ:** xác minh entity đích và quyền liên kết.
- **Sau thao tác:** kiểm tra trạng thái lưu thực tế, không chỉ response body.

Spring Data REST tự động cung cấp endpoint CRUD cho repository được export. Vì vậy, khi entity có property nhạy cảm, cần xem xét cách endpoint POST, PUT, PATCH và association resource xử lý request body.

## 2. Phân loại property trước khi mở endpoint ghi

Không phải mọi property của entity đều nên do client điều khiển. Hãy phân loại trước khi export repository:

| Nhóm property | Ví dụ | Quy tắc ghi thường phù hợp |
|---|---|---|
| Dữ liệu người dùng quản lý | \`displayName\`, \`description\` | Cho phép theo use case và validation. |
| Dữ liệu liên hệ | \`email\`, \`phoneNumber\` | Cho phép có điều kiện, kiểm tra định dạng và quyền sửa. |
| Định danh | \`id\`, mã sinh tự động | Server/database quản lý. |
| Quyền và vai trò | \`role\`, \`admin\`, \`permissions\` | Chỉ luồng quản trị có authorization riêng. |
| Tenant và chủ sở hữu | \`tenantId\`, \`ownerId\`, \`organizationId\` | Lấy từ principal hoặc kiểm tra ở server. |
| Trạng thái workflow | \`approved\`, \`verified\`, \`reviewedBy\` | Chỉ chuyển qua command hợp lệ. |
| Trường audit | \`createdAt\`, \`createdBy\`, \`updatedBy\` | Server tự ghi. |
| Giá trị tính toán | \`balance\`, \`totalPrice\`, \`riskScore\` | Server tính từ dữ liệu nguồn. |
| Association nhạy cảm | \`account\`, \`manager\`, \`organization\` | Kiểm tra quyền trên cả entity nguồn và đích. |

Bảng này là cách phân loại theo nghiệp vụ. Một trường có thể được ghi bởi một nhóm người dùng trong một use case, nhưng read-only trong một use case khác. Khi quyền ghi khác nhau theo vai trò hoặc trạng thái, một endpoint CRUD chung có thể không thể hiện rõ hợp đồng đó.

## 3. Vì sao chỉ ẩn field trên giao diện không đủ?

UI thường gửi một JSON object gồm các trường đang hiển thị. Nhưng người gọi API có thể:

- Dùng curl hoặc Postman để tự tạo request.
- Sửa payload trong browser developer tools.
- Gọi endpoint trực tiếp từ script.
- Gửi property không có trong form nhưng có trong entity.
- Gửi association URI tới một entity mà họ không được phép liên kết.

Ví dụ, form không có trường role nhưng entity có property role:

~~~java
@Entity
class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;
    private String role;

    // getters/setters
}
~~~

Nếu endpoint nhận entity và Jackson cho phép bind \`role\`, request sau vẫn có thể được gửi:

~~~http
POST /api/people
Content-Type: application/json

{
  "displayName": "Ada",
  "role": "ADMIN"
}
~~~

Hợp đồng ghi phải được thực thi tại server. Không dùng việc field vắng mặt trên form làm ranh giới bảo mật.

## 4. Chặn ghi property server-managed bằng Jackson

Nếu một property được phép trả về trong response nhưng không được nhận từ JSON request, Jackson cung cấp:

~~~java
@JsonProperty(access = JsonProperty.Access.READ_ONLY)
private String role;
~~~

Ví dụ entity:

~~~java
@Entity
class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;
    private String email;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String role;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private UUID tenantId;

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Instant createdAt;

    // getters/setters
}
~~~

Các property READ_ONLY có thể được serialize trong response, nhưng Jackson không lấy giá trị từ JSON input để ghi vào các property đó.

Dùng cách này cho các trường do server quản lý nhưng client vẫn cần đọc, ví dụ ID, timestamp, tenant hiện tại hoặc trạng thái được tính từ workflow.

### READ_ONLY không phải là authorization

READ_ONLY điều khiển JSON deserialization. Nó không quyết định user nào được phép đọc giá trị, không bảo vệ các đường ghi khác như service nội bộ, batch job hoặc database access, và không thay thế authorization.

Nếu chỉ quản trị viên được phép thay đổi role, hãy tạo thao tác quản trị riêng, kiểm tra quyền ở server và thực hiện thay đổi qua service. Không mở role cho endpoint CRUD chung chỉ để phục vụ một use case đặc biệt.

### Dùng WRITE_ONLY và JsonIgnore đúng mục đích

Jackson có ba cách thường gặp:

| Annotation | Serialize response | Deserialize request |
|---|---|---|
| \`@JsonProperty(access = READ_ONLY)\` | Có thể xuất hiện | Không nhận giá trị input |
| \`@JsonProperty(access = WRITE_ONLY)\` | Không xuất hiện | Có thể nhận giá trị input |
| \`@JsonIgnore\` | Bị bỏ qua | Bị bỏ qua |

WRITE_ONLY phù hợp với input cần nhận nhưng không được trả lại, như một secret. Credential cần được xử lý trong service chuyên biệt, hash trước khi lưu và không ghi vào log.

JsonIgnore phù hợp khi property không nên trao đổi qua JSON theo cả hai chiều. Nếu client cần đọc property nhưng không được ghi, READ_ONLY thường phù hợp hơn.

Kiểm tra annotation trên field, getter và setter. Jackson có thể hợp nhất chúng thành một logical property; cấu hình không nhất quán có thể tạo ra hành vi khác với mong đợi.

## 5. Allowlist input bằng request DTO

Khi một use case chỉ cho phép một số trường, request DTO là cách rõ ràng để mô tả hợp đồng input. Ví dụ:

~~~java
public record UpdatePersonRequest(
    @NotBlank
    @Size(max = 120)
    String displayName,

    @Email
    @Size(max = 254)
    String email
) {
}
~~~

Custom controller nhận DTO và gọi service:

~~~java
@RestController
@RequestMapping("/api/person-commands")
class PersonCommandController {

    private final PersonService personService;

    PersonCommandController(PersonService personService) {
        this.personService = personService;
    }

    @PatchMapping("/{id}")
    ResponseEntity<PersonResponse> update(
            @PathVariable Long id,
            @Valid @RequestBody UpdatePersonRequest request) {

        return ResponseEntity.ok(
            personService.updateProfile(id, request)
        );
    }
}
~~~

Service lấy entity hiện có và chỉ cập nhật các trường được allowlist:

~~~java
@Transactional
public PersonResponse updateProfile(
        Long id,
        UpdatePersonRequest request) {

    Person person = repository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException());

    person.setDisplayName(request.displayName());
    person.setEmail(request.email());

    return PersonResponse.from(person);
}
~~~

Các trường role, tenantId, approved và createdAt không có trong DTO, do đó không được service sao chép từ request vào entity.

Spring Data REST mặc định xuất bản repository domain resource; nó không tự biến endpoint repository thành endpoint nhận DTO. Khi cần input allowlist theo use case, hãy tạo custom controller/service ở URI riêng. Nếu custom endpoint thay thế hoàn toàn repository API, có thể cân nhắc ẩn repository bằng \`@RepositoryRestResource(exported = false)\`.

Nếu chính sách yêu cầu từ chối mọi JSON key ngoài DTO, hãy cấu hình unknown-property handling rõ ràng và kiểm thử ObjectMapper thực tế. Giá trị mặc định của \`FAIL_ON_UNKNOWN_PROPERTIES\` có thể thay đổi theo cấu hình và phiên bản. Dù key lạ bị bỏ qua hay bị từ chối, điều đó vẫn không thay thế allowlist cho property đã tồn tại trên entity.

## 6. Kiểm soát POST, PUT và PATCH

Mass assignment có thể xảy ra ở mọi request ghi nhận JSON:

| Method | Resource | Rủi ro chính |
|---|---|---|
| POST | Collection, ví dụ \`/api/people\` | Tạo entity với role, owner hoặc tenant do client tự chọn. |
| PUT | Item, ví dụ \`/api/people/42\` | Gửi các property không thuộc hợp đồng cập nhật. |
| PATCH | Item, ví dụ \`/api/people/42\` | Thay đổi một property nhạy cảm bằng payload rất nhỏ. |
| PATCH/PUT | Association resource | Gắn hoặc thay thế quan hệ tới entity không được phép truy cập. |

Không mặc định PATCH an toàn hơn PUT. Nếu property nhạy cảm được bind, một payload PATCH ngắn vẫn có thể thay đổi property đó.

Với mỗi method, xác định:

1. Các property được phép tạo hoặc sửa.
2. Property chỉ server được thay đổi.
3. Hành vi khi client gửi property read-only.
4. Hành vi với JSON key không thuộc hợp đồng.
5. Quyền cần thiết cho principal.
6. Quy tắc kiểm tra trạng thái hiện tại trước khi lưu.

Với PUT, cần hiểu semantics thay thế representation của endpoint và các giá trị bị bỏ qua theo cấu hình. Với PATCH, kiểm tra media type và cơ chế patch đang dùng. Không giả định mọi kiểu PATCH có cùng hành vi binding.

## 7. Kiểm soát association và URI reference

Spring Data REST có thể cho phép client cập nhật association bằng URI của entity đích. Ví dụ:

~~~http
PUT /api/people/42/address
Content-Type: text/uri-list

http://localhost:8080/api/addresses/7
~~~

Ngay cả khi JSON body không có property \`address\`, client vẫn có thể thay đổi quan hệ qua association resource nếu endpoint được export và method được phép.

Vì vậy, cần kiểm tra:

- Person 42 thuộc user hoặc tenant nào.
- User có quyền sửa association của Person 42 không.
- Address 7 có tồn tại không.
- Address 7 có thuộc tenant hoặc phạm vi mà Person 42 được phép tham chiếu không.
- Association có được phép thay đổi ở trạng thái hiện tại không.
- Cascade và orphan removal có thể ảnh hưởng dữ liệu nào.

Ẩn association bằng \`@RestResource(exported = false)\` điều khiển việc công bố link/resource của Spring Data REST. Nó không phải allowlist tổng quát cho mọi đường JSON binding và không thay thế authorization.

Đối với quan hệ nhạy cảm, kiểm thử cả request tới association URI và request JSON tới item/collection resource. Đừng chỉ kiểm tra link có xuất hiện hay không.

## 8. Xác định tenant, owner và trạng thái ở server

Các trường như tenantId, ownerId, role, approved và audit fields thường phải được thiết lập từ security context hoặc quy tắc domain.

Ví dụ tạo entity:

~~~java
@Transactional
public Person createPerson(
        CreatePersonRequest request,
        CurrentUser currentUser) {

    Person person = new Person();
    person.setDisplayName(request.displayName());
    person.setEmail(request.email());

    person.setTenantId(currentUser.tenantId());
    person.setRole(Role.USER);
    person.setApproved(false);
    person.setCreatedAt(Instant.now());

    return repository.save(person);
}
~~~

Client chỉ gửi dữ liệu nghiệp vụ được phép. Server lấy tenant từ principal, đặt role mặc định và tạo audit timestamp.

Với update, lấy entity hiện có trong phạm vi tenant phù hợp, kiểm tra quyền của principal, rồi cập nhật từng property được phép. Không lấy ownerId hoặc tenantId từ client làm bằng chứng quyền truy cập.

Trong hệ thống multi-tenant, truy vấn và kiểm tra tenant phải được thực hiện nhất quán ở server. Việc kiểm tra tenant ở UI hoặc chỉ lọc kết quả sau khi đã tải entity là không đủ.

## 9. Validation và domain invariant

Allowlist quyết định property nào được nhận; validation quyết định giá trị nhận được có hợp lệ hay không. Hai lớp này cần hoạt động cùng nhau.

### Bean Validation

~~~java
public record CreatePersonRequest(
    @NotBlank
    @Size(max = 120)
    String displayName,

    @NotBlank
    @Email
    @Size(max = 254)
    String email
) {
}
~~~

Dùng \`@Valid\` tại boundary nhận request để kích hoạt validation cho DTO. Với Spring Data REST repository event validation, bảo đảm validator được đăng ký cho các lifecycle event phù hợp với create/update.

### Repository event handlers

Spring Data REST cung cấp các sự kiện như before-create, before-save và before-link-save. Ví dụ:

~~~java
@Component
@RepositoryEventHandler
class PersonEventHandler {

    @HandleBeforeCreate
    void beforeCreate(Person person) {
        validatePerson(person);
    }

    @HandleBeforeSave
    void beforeSave(Person person) {
        validatePerson(person);
    }

    private void validatePerson(Person person) {
        if (person.getDisplayName() == null
                || person.getDisplayName().isBlank()) {
            throw new IllegalArgumentException(
                "displayName is required");
        }
    }
}
~~~

Event handler có thể kiểm tra trạng thái và từ chối thao tác trước khi repository lưu. Tuy nhiên, event handler không tự tạo allowlist JSON. Nếu property nhạy cảm đã được bind, code phải phát hiện và từ chối thay đổi đó.

Các quy tắc phụ thuộc principal, tenant, quyền quản trị hoặc workflow thường nên được đặt ở service/domain layer để có thể kiểm tra đầy đủ ngữ cảnh. Không dựa riêng vào validation annotation để thực thi authorization.

## 10. Cấu hình JSON key không được biết

Một request có thể gửi key không tồn tại trên entity:

~~~json
{
  "displayName": "Ada",
  "unexpectedFlag": true
}
~~~

Jackson có thể bỏ qua key này hoặc từ chối request tùy cấu hình ObjectMapper. Ứng dụng có thể tùy chỉnh qua Spring Boot properties, ObjectMapper bean, module, mixin hoặc message converter.

Cần phân biệt:

- **Unknown property:** key không tồn tại trên model, ví dụ unexpectedFlag.
- **Known but forbidden property:** key tồn tại trên entity nhưng client không được phép ghi, ví dụ role.

Bật \`FAIL_ON_UNKNOWN_PROPERTIES\` có thể giúp phát hiện payload sai hợp đồng, nhưng không chặn property nhạy cảm đã tồn tại trên entity. Để ngăn mass assignment, cần kiểm soát known property bằng READ_ONLY, DTO allowlist hoặc logic ghi chuyên biệt.

Hãy kiểm thử với đúng ObjectMapper mà endpoint Spring Data REST đang sử dụng. Không suy luận hành vi chỉ từ một ObjectMapper được tạo riêng trong unit test.

## 11. Authorization cho thao tác ghi

Cho phép HTTP POST hoặc PATCH ở mức URL không có nghĩa mọi user đều có quyền thay đổi mọi field. Authorization cần gắn với hành động và tài nguyên cụ thể.

Ví dụ quy tắc nghiệp vụ:

- User chỉ sửa profile của chính mình.
- Chỉ admin mới thay đổi role.
- Tenant A không được gán association tới entity thuộc tenant B.
- Chỉ người duyệt mới chuyển trạng thái PENDING sang APPROVED.
- Giá, số dư và điểm rủi ro do server tính.
- Manager chỉ được thay đổi theo quy tắc tổ chức.

Có thể dùng Spring Security request authorization và method security để bảo vệ endpoint/service. Với các thao tác nhạy cảm, kiểm tra quyền trên entity hiện tại và trạng thái workflow ngay trong luồng nghiệp vụ.

Ẩn link HAL không phải bảo vệ endpoint. Một client có thể gọi URI trực tiếp. Server phải kiểm tra quyền trên request thực tế.

## 12. Kiểm thử mass assignment bằng integration test

Kiểm thử nên gửi payload chứa cả property hợp lệ và property không được phép ghi, sau đó đọc lại database để xác nhận trạng thái.

Ví dụ với property READ_ONLY:

~~~java
@Test
void patchCannotChangeServerManagedFields() throws Exception {
    Person person = new Person();
    person.setDisplayName("Ada");
    person.setRole("USER");
    person = repository.save(person);

    mockMvc.perform(patch("/api/people/{id}", person.getId())
            .contentType(MediaType.APPLICATION_JSON)
            .accept("application/hal+json")
            .content("""
                {
                  "displayName": "Ada Lovelace",
                  "role": "ADMIN"
                }
                """))
        .andExpect(status().is2xxSuccessful());

    Person saved = repository.findById(person.getId())
        .orElseThrow();

    assertThat(saved.getDisplayName())
        .isEqualTo("Ada Lovelace");
    assertThat(saved.getRole()).isEqualTo("USER");
}
~~~

Ví dụ cần được điều chỉnh theo media type PATCH và cấu hình thực tế của dự án. Nếu chính sách API là từ chối payload có property bị cấm, kiểm tra status lỗi và xác nhận database vẫn giữ nguyên.

Các test nên bao gồm:

1. POST với field được phép tạo entity thành công.
2. POST cố gửi role, tenant hoặc owner không làm thay đổi các giá trị server-managed.
3. PUT chỉ cập nhật những field được hợp đồng cho phép.
4. PATCH một field hợp lệ không làm thay đổi field khác.
5. PATCH chỉ gửi property READ_ONLY không thay đổi trạng thái server-managed.
6. Payload có unknown key tuân theo chính sách từ chối/bỏ qua đã công bố.
7. Association update tới entity ngoài tenant bị từ chối.
8. User không có quyền không thể đổi role hoặc trạng thái duyệt.
9. Response không chứa secret.
10. Database state được kiểm tra sau mỗi request, không chỉ kiểm tra HTTP status.

## 13. Ví dụ kiểm tra bằng curl

Tạo Person chỉ với dữ liệu được phép:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"displayName":"Ada Lovelace","email":"ada@example.com"}' \
  http://localhost:8080/api/people
~~~

Thử gửi thêm field server-managed trong môi trường kiểm thử:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"displayName":"Ada","role":"ADMIN","approved":true}' \
  http://localhost:8080/api/people
~~~

Cập nhật profile bằng endpoint DTO riêng:

~~~bash
curl -i -X PATCH \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"displayName":"Ada Lovelace","email":"ada@example.com"}' \
  http://localhost:8080/api/person-commands/42
~~~

Thử gán association trong môi trường test:

~~~bash
curl -i -X PUT \
  -H "Content-Type: text/uri-list" \
  --data-binary "http://localhost:8080/api/addresses/7" \
  http://localhost:8080/api/people/42/address
~~~

Các request có field trái phép chỉ nên được thử trên dữ liệu/môi trường kiểm thử phù hợp. Sau mỗi request, đọc lại entity để xác nhận server không lưu thay đổi ngoài hợp đồng.

## 14. Quy trình xử lý khi phát hiện mass assignment

Khi một property bị thay đổi ngoài dự kiến:

1. Xác định URI, HTTP method, principal và request body thực tế.
2. Xác định property nào thay đổi trong entity/database.
3. Kiểm tra entity field, getter/setter, constructor và Jackson annotations.
4. Kiểm tra ObjectMapper/message converter mà Spring Data REST đang dùng.
5. Xác định endpoint có bind trực tiếp domain object hay dùng DTO.
6. Phân loại property theo quyền ghi và use case.
7. Đánh dấu server-managed property bằng READ_ONLY hoặc ẩn khỏi JSON nếu phù hợp.
8. Chuyển endpoint có input giới hạn sang DTO allowlist nếu cần.
9. Kiểm tra association resource và URI reference binding.
10. Đặt validation và authorization tại server.
11. Thêm integration test gửi payload có field nhạy cảm.
12. Xem xét các bản ghi đã bị ghi sai và xử lý khôi phục theo quy trình dữ liệu của ứng dụng.

Không chỉ sửa UI để ẩn field. Cần sửa hợp đồng và cơ chế thực thi tại server.

## 15. Những nhầm lẫn thường gặp

1. **Field không có trên form nên client không thể gửi.** Client có thể tạo request HTTP thủ công.
2. **Unknown-property handling chặn mass assignment.** Nó chỉ xử lý key không có trên model; property nhạy cảm đã tồn tại vẫn có thể bind.
3. **READ_ONLY là cơ chế phân quyền.** Nó kiểm soát JSON binding, không thay thế authorization.
4. **JsonIgnore luôn là lựa chọn tốt nhất.** Nếu cần đọc nhưng không cho ghi, READ_ONLY thể hiện đúng ý định hơn.
5. **PATCH không có rủi ro vì chỉ cập nhật một phần.** Một property nhạy cảm trong payload vẫn có thể bị thay đổi.
6. **Ẩn association link đồng nghĩa không thể cập nhật quan hệ.** Phải kiểm soát association URI và JSON binding.
7. **exported=false là allowlist cho property.** Nó điều khiển export resource/method/association, không phải quy tắc tổng quát cho mọi property.
8. **Validation tự ngăn property không được phép.** Validation kiểm tra giá trị; allowlist xác định property nào được nhận.
9. **Tenant/owner do client gửi là đáng tin.** Server phải suy ra hoặc xác minh quyền trên entity.
10. **Chỉ cần kiểm tra response.** Dữ liệu có thể đã được ghi dù response không hiển thị field đó.
11. **Event handler tự động loại bỏ mọi field ngoài ý muốn.** Handler chỉ thực hiện logic được lập trình; nó không thay thế binding policy.
12. **Projection bảo vệ endpoint ghi.** Projection chủ yếu điều khiển representation đọc, không phải allowlist ghi.

## 16. Checklist triển khai

- Xác định allowlist property cho từng thao tác create/update.
- Đánh dấu ID, tenant, owner, audit và trạng thái server-managed phù hợp.
- Dùng READ_ONLY khi property cần đọc nhưng không nhận JSON input.
- Dùng WRITE_ONLY cho input secret cần thiết và xử lý an toàn.
- Dùng JsonIgnore khi property không nên trao đổi qua JSON.
- Dùng request DTO cho use case có input giới hạn.
- Map rõ từng property được phép trong service.
- Không tin tenantId, ownerId hoặc role do client gửi.
- Kiểm tra quyền trên entity nguồn và entity đích khi cập nhật association.
- Dùng Bean Validation và domain invariant.
- Bảo vệ thao tác nhạy cảm bằng Spring Security/service authorization.
- Kiểm tra cả POST, PUT, PATCH và association update.
- Xác định rõ chính sách unknown JSON property.
- Kiểm tra database state sau request thử nghiệm.
- Không dựa vào UI hoặc link HAL làm ranh giới bảo mật.
- Không trả secret hoặc dữ liệu nội bộ trong response/log.

## Tóm tắt

Mass assignment trong Spring Data REST xảy ra khi request body được bind vào domain object và client có thể ghi các property vượt quá quyền của use case. Rủi ro xuất hiện ở POST, PUT, PATCH và cả association resource.

Hãy phân loại property theo quyền ghi, dùng Jackson READ_ONLY cho trường server-managed cần đọc, JsonIgnore cho trường không trao đổi qua JSON và DTO allowlist khi cần hợp đồng input chặt chẽ. Service phải thiết lập tenant, owner, role và audit data từ server context; association update phải kiểm tra cả quyền trên entity nguồn lẫn entity đích.

Validation kiểm tra giá trị, authorization kiểm tra quyền và allowlist giới hạn trường được nhận. Cần kiểm thử request trực tiếp có thêm property nhạy cảm và xác nhận database không thay đổi ngoài dự kiến.

## Tài liệu tham khảo

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Repository Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Jackson — JsonProperty.Access](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
- [Jackson — JsonIgnore](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
