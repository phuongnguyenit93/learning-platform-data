# Kiểm soát mass assignment và dữ liệu đầu vào ngoài dự kiến trong Spring Data REST

## Mục tiêu

Spring Data REST có thể nhận JSON từ client và dùng Jackson để ánh xạ các thuộc tính trong request body vào domain object của repository. Cơ chế này thuận tiện cho CRUD, nhưng cũng tạo ra rủi ro **mass assignment** nếu API cho phép client ghi những thuộc tính mà giao diện người dùng bình thường không gửi.

Mass assignment xảy ra khi server tự động bind nhiều thuộc tính từ request vào object, trong khi ứng dụng chỉ định cho client thay đổi một tập nhỏ thuộc tính. Một client có thể tự thêm các trường như \`role\`, \`admin\`, \`ownerId\`, \`tenantId\`, \`approved\`, \`createdAt\` hoặc \`internalStatus\` vào JSON dù các trường đó không xuất hiện trên form.

Ví dụ, màn hình chỉ cho phép đổi tên Person, nhưng request có thể được gửi thủ công:

~~~json
{
  "displayName": "Ada",
  "role": "ADMIN",
  "tenantId": "tenant-other",
  "approved": true
}
~~~

Nếu các thuộc tính này được Jackson bind vào entity và không có kiểm soát ở server, client có thể thay đổi dữ liệu ngoài ý muốn.

Để kiểm soát rủi ro này, cần kết hợp:

- Giới hạn các thuộc tính được phép ghi vào từng API.
- Đánh dấu các thuộc tính do server quản lý là read-only hoặc không được serialize/bind.
- Dùng DTO có allowlist khi endpoint cần nhận một tập input rõ ràng.
- Kiểm tra dữ liệu bằng Bean Validation và domain rules.
- Áp dụng authorization ở server cho từng hành động nhạy cảm.
- Kiểm thử bằng request có chủ ý gửi các trường ngoài hợp đồng API.

## 1. Mass assignment trong quá trình JSON mapping

Giả sử repository Person được export:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Một request tạo Person có thể gửi JSON:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "displayName": "Ada Lovelace",
  "email": "ada@example.com"
}
~~~

Spring Data REST nhận request body và dùng cơ chế message conversion của Spring MVC/Jackson để tạo hoặc cập nhật domain object. Những thuộc tính JSON tương ứng với property có thể được Jackson bind theo cấu hình mapper, constructor, setter và visibility của model.

Rủi ro xuất hiện khi entity chứa các thuộc tính nội bộ có thể bind:

~~~java
@Entity
class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String displayName;
    private String email;

    private String role;
    private UUID tenantId;
    private boolean approved;
    private Instant createdAt;

    // getters/setters
}
~~~

Nếu API nhận entity trực tiếp và các property nhạy cảm có thể ghi, client có thể gửi thêm các key đó. Việc UI không hiển thị trường không có nghĩa request HTTP không thể chứa trường đó.

### Những thuộc tính cần xem xét

| Nhóm thuộc tính | Ví dụ | Rủi ro nếu client tự ghi |
|---|---|---|
| Quyền và vai trò | \`role\`, \`admin\`, \`permissions\` | Nâng quyền hoặc tự cấp quyền. |
| Chủ sở hữu và tenant | \`ownerId\`, \`tenantId\`, \`organizationId\` | Gán dữ liệu sang người dùng hoặc tenant khác. |
| Trạng thái phê duyệt | \`approved\`, \`verified\`, \`reviewedBy\` | Bỏ qua quy trình duyệt. |
| Trường audit | \`createdAt\`, \`createdBy\`, \`updatedBy\` | Làm sai nguồn gốc và lịch sử dữ liệu. |
| Trường tính toán nội bộ | \`balance\`, \`priceAfterDiscount\`, \`riskScore\` | Ghi đè giá trị phải do server tính. |
| Quan hệ nhạy cảm | \`manager\`, \`account\`, \`organization\` | Gắn entity vào đối tượng mà client không được phép quản lý. |

Không phải mọi thuộc tính trong bảng đều luôn nhạy cảm. Quyết định dựa trên nghiệp vụ, quyền của principal và hợp đồng API.

## 2. Phân biệt dữ liệu đầu vào hợp lệ và dữ liệu ngoài dự kiến

Có ba trường hợp khác nhau khi server nhận JSON:

1. **Thuộc tính được phép ghi:** client được quyền gửi và server có thể bind vào domain object.
2. **Thuộc tính hợp lệ khi đọc nhưng không được client sửa:** server có thể trả trong response nhưng phải bỏ qua hoặc từ chối khi xuất hiện trong request.
3. **Thuộc tính không thuộc hợp đồng API:** client không nên gửi; cách Jackson xử lý key lạ phụ thuộc cấu hình ObjectMapper và message converter.

Không nên dựa vào việc Jackson bỏ qua unknown property như một cơ chế bảo vệ. Một key như \`role\` có thể không phải unknown property nếu entity thực sự có property đó. Khi ấy Jackson có thể bind nó như các thuộc tính bình thường khác.

Cũng không nên nhầm việc ẩn một thuộc tính khỏi response với việc bảo đảm client không thể ghi thuộc tính đó. Cần cấu hình rõ cả hướng serialize và deserialize.

## 3. Dùng @JsonProperty(access = READ_ONLY) cho thuộc tính do server quản lý

Jackson hỗ trợ \`@JsonProperty(access = JsonProperty.Access.READ_ONLY)\`. Thuộc tính read-only có thể được serialize ra response nhưng không nhận giá trị từ JSON input.

Ví dụ:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

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

Khi client gửi:

~~~json
{
  "displayName": "Ada",
  "role": "ADMIN",
  "tenantId": "tenant-other",
  "createdAt": "2026-01-01T00:00:00Z"
}
~~~

Jackson không dùng các giá trị input của các property được đánh dấu READ_ONLY để cập nhật object. Khi serialize, các giá trị đó vẫn có thể xuất hiện trong response.

### Khi nào dùng READ_ONLY?

Dùng cho thuộc tính:

- Do server tự tạo hoặc tự cập nhật.
- Được phép hiển thị cho client nhưng không được client điều khiển.
- Là kết quả tính toán hoặc trạng thái nội bộ chỉ server có quyền thay đổi.
- Cần xuất hiện trong response để client đọc, nhưng không thuộc hợp đồng ghi.

Ví dụ thường gặp là ID do database sinh, timestamp audit, trạng thái phê duyệt hoặc tenant được suy ra từ principal.

### READ_ONLY không thay thế authorization

READ_ONLY chặn việc bind từ JSON theo Jackson. Nó không quyết định người dùng nào được đọc thuộc tính đó, không kiểm soát mọi đường ghi trong ứng dụng và không thay thế quyền ở service/domain layer.

Nếu một user không được phép đọc \`tenantId\` hoặc \`role\`, cần kiểm soát representation hoặc authorization riêng. Nếu một thao tác quản trị được phép thay đổi role, hãy cung cấp use case có authorization rõ ràng thay vì mở property đó trong endpoint CRUD chung.

## 4. Dùng WRITE_ONLY cho dữ liệu chỉ nhận từ client

Jackson cũng có:

~~~java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String password;
~~~

WRITE_ONLY cho phép property được bind từ JSON input nhưng không được serialize trong response.

Cách này phù hợp với một số input như secret cần nhận từ client, nhưng cần xử lý cẩn thận:

- Không lưu mật khẩu dạng plain text.
- Chỉ truyền qua HTTPS.
- Hash/encode tại service chuyên trách trước khi lưu.
- Không trả lại secret trong response hoặc log.
- Không để một endpoint repository chung vô tình cho phép đổi credential mà không chạy quy trình nghiệp vụ tương ứng.

Với credential, token hoặc secret, DTO và service chuyên biệt thường rõ ràng hơn việc đưa trực tiếp property đó vào entity được export.

## 5. Dùng @JsonIgnore khi thuộc tính không được đọc hoặc ghi qua JSON

Nếu một property hoàn toàn không nên xuất hiện trong JSON representation và cũng không được bind từ JSON, có thể dùng:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnore;

@Entity
class Person {

    private String displayName;

    @JsonIgnore
    private String internalRiskFlag;

    // getters/setters
}
~~~

\`@JsonIgnore\` áp dụng cho cả quá trình serialize và deserialize theo cách Jackson xử lý property. Vì vậy, response sẽ không công bố property và request JSON cũng không dùng property đó để bind.

So sánh:

| Cấu hình | Serialize response | Deserialize request |
|---|---|---|
| \`@JsonProperty(access = READ_ONLY)\` | Có thể xuất hiện | Không nhận giá trị input |
| \`@JsonProperty(access = WRITE_ONLY)\` | Không xuất hiện | Có thể nhận giá trị input |
| \`@JsonIgnore\` | Bị bỏ qua | Bị bỏ qua |

Hãy kiểm tra cách annotation được đặt trên field/getter/setter và cấu hình Jackson của ứng dụng. Jackson có thể hợp nhất field và accessor thành cùng một logical property; đặt annotation không nhất quán ở nhiều accessor có thể gây hành vi khó hiểu.

Nếu cần property được đọc ở API nhưng chỉ một số role được phép xem, \`@JsonIgnore\` là quá rộng. Khi đó cần thiết kế representation hoặc endpoint theo quyền truy cập.

## 6. Ẩn association không đồng nghĩa bảo vệ mọi đường ghi

Spring Data REST có thể export association dưới dạng link và association resource. Có thể ẩn association khỏi REST exporter bằng \`@RestResource(exported = false)\`:

~~~java
@ManyToOne
@RestResource(exported = false)
private Organization organization;
~~~

Cấu hình này điều khiển việc công bố association resource/link của Spring Data REST. Nó không nên được xem là cơ chế allowlist tổng quát cho toàn bộ JSON binding hoặc authorization của ứng dụng.

Nếu entity vẫn có property \`organization\` và JSON mapper vẫn nhận property đó, cần kiểm soát binding riêng. Hãy dùng annotation Jackson, DTO input hoặc custom endpoint với quyền kiểm tra rõ ràng.

Đối với association nhạy cảm, cần xác minh cả hai đường:

- Gọi association resource trực tiếp bằng HTTP method phù hợp.
- Gửi JSON chứa thuộc tính association trong POST/PUT/PATCH của item hoặc collection.

Kiểm thử cả hai trường hợp để tránh chỉ ẩn link nhưng vẫn cho phép một đường ghi khác.

## 7. DTO allowlist là lựa chọn rõ ràng cho input có giới hạn

Khi endpoint chỉ cần một số trường nhất định, cách chắc chắn và dễ kiểm soát là nhận một request DTO thay vì bind trực tiếp entity.

Ví dụ:

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

Controller gọi service:

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

        PersonResponse response =
                personService.updateProfile(id, request);

        return ResponseEntity.ok(response);
    }
}
~~~

Service chỉ sao chép những thuộc tính được cho phép:

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

DTO đóng vai trò allowlist: chỉ các component được khai báo mới thuộc hợp đồng input. Các trường như \`role\`, \`tenantId\`, \`approved\` hoặc \`createdAt\` không có trong DTO nên không được service sao chép vào entity.

### Nếu cần từ chối key ngoài hợp đồng

Tùy cấu hình Jackson, property lạ trong JSON có thể bị bỏ qua hoặc làm request thất bại. Nếu yêu cầu API là phải từ chối mọi key ngoài DTO, cấu hình deserialization nghiêm ngặt và kiểm thử hành vi đó trong đúng ObjectMapper/message converter của ứng dụng.

Không giả định mọi phiên bản Spring Boot đều có cùng giá trị mặc định của \`FAIL_ON_UNKNOWN_PROPERTIES\`. Hãy kiểm tra cấu hình thực tế.

### DTO và Spring Data REST

Spring Data REST mặc định export repository domain resource; nó không tự biến mọi repository endpoint thành endpoint nhận DTO. Nếu cần input allowlist, có thể:

- Tạo custom controller và service cho use case đó.
- Đặt custom endpoint ở URI không xung đột với repository resource.
- Hoặc ẩn repository resource bằng \`@RepositoryRestResource(exported = false)\` nếu endpoint DTO thay thế toàn bộ API CRUD tương ứng.

Không tạo controller trùng URI với collection/item resource đã export rồi kỳ vọng route sẽ được chọn theo ý muốn. Hãy thiết kế path rõ ràng và kiểm tra mapping thực tế.

## 8. Validation và domain invariant

Giới hạn property được bind mới giải quyết một phần vấn đề. Dữ liệu được phép ghi vẫn phải hợp lệ.

### Bean Validation

Ví dụ:

~~~java
@Entity
class Person {

    @NotBlank
    @Size(max = 120)
    private String displayName;

    @Email
    @Size(max = 254)
    private String email;
}
~~~

Bean Validation kiểm tra giá trị theo constraint đã khai báo. Với Spring Data REST, validation có thể được kết nối qua repository event listener. Cần bảo đảm validator được đăng ký và chạy ở các lifecycle event phù hợp với thao tác create/update.

### Repository event handler

Spring Data REST hỗ trợ event handler cho lifecycle repository:

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

Các handler này phù hợp cho kiểm tra hoặc xử lý trước/sau thao tác repository. Tuy nhiên, chúng không phải allowlist JSON: nếu một field nhạy cảm đã được bind, event handler phải chủ động phát hiện và từ chối hoặc khôi phục giá trị không được phép.

Đối với quy tắc phụ thuộc người dùng hiện tại, tenant, quyền quản trị hoặc trạng thái workflow, service/domain layer có thể là nơi phù hợp hơn để thực hiện quyết định nghiệp vụ.

## 9. Bảo vệ các thuộc tính server-managed

Một mẫu thiết kế thường dùng là gán các thuộc tính do server quản lý từ security context hoặc service:

~~~java
@Transactional
public Person createPerson(CreatePersonRequest request, CurrentUser user) {
    Person person = new Person();

    person.setDisplayName(request.displayName());
    person.setEmail(request.email());

    person.setTenantId(user.tenantId());
    person.setRole(Role.USER);
    person.setApproved(false);
    person.setCreatedAt(Instant.now());

    return repository.save(person);
}
~~~

Client không gửi \`tenantId\`, \`role\`, \`approved\` hoặc \`createdAt\`. Server tự thiết lập những giá trị đó dựa trên principal và quy tắc nghiệp vụ.

Với update, không gán lại toàn bộ object từ input một cách mù quáng. Hãy lấy entity hiện có, kiểm tra quyền của principal, rồi cập nhật từng field được phép. Cách này tránh vô tình ghi đè giá trị nội bộ khi request chỉ muốn đổi một vài thuộc tính.

### Không tin identifier do client gửi để xác định quyền

Nếu client gửi \`ownerId\` hoặc \`tenantId\`, không được coi đó là bằng chứng người dùng có quyền thao tác trên đối tượng tương ứng. Hãy suy ra tenant/owner từ authentication context hoặc kiểm tra quyền trên entity hiện tại ở server.

Đặc biệt với multi-tenant application, truy vấn lấy entity và kiểm tra tenant cần được thực hiện nhất quán. Chỉ kiểm tra tenant ở UI hoặc lọc dữ liệu sau khi đã tải entity là không đủ.

## 10. PUT, PATCH và POST đều cần kiểm soát input

Mass assignment không chỉ xảy ra ở POST tạo mới. Cần xem xét mọi method nhận JSON:

| Method | Mục đích thường gặp | Rủi ro |
|---|---|---|
| POST collection | Tạo entity mới | Client thêm role, owner, tenant hoặc trạng thái nội bộ vào object mới. |
| PUT item | Thay thế/cập nhật representation của item theo semantics endpoint | Client gửi thêm property ngoài các field được phép. |
| PATCH item | Cập nhật một phần representation | Client chỉ cần gửi một field nhạy cảm để thay đổi trạng thái. |
| PATCH association | Cập nhật quan hệ hoặc một phần resource liên quan | Client có thể gán liên kết tới entity mà họ không được phép truy cập. |

Không nên coi PATCH an toàn hơn PUT chỉ vì request body nhỏ. Nếu property nhạy cảm được bind, một JSON PATCH nhỏ vẫn có thể thay đổi property đó.

Đối với mỗi endpoint ghi, hãy xác định:

- Những property nào client được phép tạo.
- Những property nào client được phép sửa.
- Property nào chỉ server được thay đổi.
- Association nào client được phép gán hoặc bỏ liên kết.
- Quyền nào cần thiết cho thao tác cụ thể.

## 11. Authorization và kiểm soát theo nghiệp vụ

Spring Security bảo vệ endpoint theo authentication và authorization. Việc cho phép POST hoặc PATCH ở mức URL không có nghĩa mọi property trong entity đều được phép thay đổi.

Một số quy tắc cần đặt ở tầng nghiệp vụ:

- Chỉ quản trị viên mới có thể thay đổi role.
- User chỉ được sửa hồ sơ của chính mình.
- Tenant A không được gán entity thuộc tenant B.
- Chỉ người duyệt mới được chuyển trạng thái từ PENDING sang APPROVED.
- Giá hoặc số dư phải được tính bởi server.
- Quan hệ manager phải tuân thủ quy tắc tổ chức.

Nếu một endpoint CRUD chung không thể biểu diễn rõ các quyền này, hãy tạo command/service endpoint riêng cho use case. Phương thức service có thể được bảo vệ bằng authorization phù hợp, sau đó kiểm tra dữ liệu hiện tại trước khi thay đổi.

Ẩn property khỏi JSON hoặc đánh dấu READ_ONLY không thay thế authorization. Ngược lại, chỉ có authorization ở URL mà không kiểm soát field cũng có thể để lại lỗ hổng mass assignment.

## 12. Unknown JSON properties và cấu hình Jackson

Một request có thể chứa key không tồn tại trên entity:

~~~json
{
  "displayName": "Ada",
  "unexpectedFlag": true
}
~~~

Jackson có thể:

- Bỏ qua property không biết nếu cấu hình cho phép.
- Từ chối request nếu cấu hình bật lỗi unknown property.
- Xử lý qua custom deserializer hoặc mixin nếu ứng dụng có cấu hình riêng.

Hành vi cụ thể phụ thuộc ObjectMapper mà Spring MVC/Spring Data REST đang dùng và phiên bản framework. Không nên dựa vào mặc định mà không kiểm tra.

Điểm quan trọng hơn: **unknown property và sensitive known property là hai trường hợp khác nhau**.

- \`unexpectedFlag\` không tồn tại trên model nên có thể là unknown.
- \`role\` tồn tại trên entity và có setter nên có thể được bind, dù UI không bao giờ gửi nó.

Bật \`FAIL_ON_UNKNOWN_PROPERTIES\` chỉ xử lý nhóm key lạ. Nó không tự ngăn client ghi các property hợp lệ nhưng nhạy cảm.

## 13. Kiểm thử chống mass assignment

Integration test cần gửi request chứa cả field hợp lệ và field không được phép ghi. Sau request, kiểm tra trạng thái lưu trong database, không chỉ kiểm tra response.

Ví dụ minh họa:

~~~java
@Test
void patchMustNotChangeServerManagedFields() throws Exception {
    Person person = new Person();
    person.setDisplayName("Ada");
    person.setRole("USER");
    person.setTenantId(UUID.fromString(
            "11111111-1111-1111-1111-111111111111"));
    person = repository.save(person);

    mockMvc.perform(patch("/api/people/{id}", person.getId())
            .contentType(MediaType.APPLICATION_JSON)
            .accept("application/hal+json")
            .content("""
                {
                  "displayName": "Ada Lovelace",
                  "role": "ADMIN",
                  "tenantId": "22222222-2222-2222-2222-222222222222"
                }
                """))
            .andExpect(status().is2xxSuccessful());

    Person saved = repository.findById(person.getId()).orElseThrow();

    assertThat(saved.getDisplayName()).isEqualTo("Ada Lovelace");
    assertThat(saved.getRole()).isEqualTo("USER");
    assertThat(saved.getTenantId()).isEqualTo(
            UUID.fromString(
                "11111111-1111-1111-1111-111111111111"));
}
~~~

Đây là ví dụ kiểm thử với property READ_ONLY và một endpoint Spring Data REST đã được cấu hình phù hợp. Trong dự án thực tế, dùng đúng media type, authentication và fixture của phiên bản đang chạy. Nếu API chọn từ chối request thay vì bỏ qua field, điều chỉnh assertion cho status lỗi và vẫn xác nhận database không đổi.

Các trường hợp nên có trong integration test:

1. POST chỉ chứa field được phép: tạo thành công.
2. POST thêm role/tenant/owner: server không chấp nhận thay đổi trái phép.
3. PATCH một field hợp lệ: chỉ field đó thay đổi.
4. PATCH chỉ chứa field read-only: trạng thái server-managed không thay đổi.
5. PUT có property ngoài allowlist: server xử lý theo hợp đồng đã chọn.
6. Gán association tới entity thuộc tenant khác: bị từ chối.
7. User không có quyền quản trị thử đổi role: bị từ chối.
8. Request có unknown JSON key: hành vi đúng với chính sách API.
9. Response không lộ secret hoặc field nội bộ.
10. Kiểm tra cả trạng thái entity sau request, không chỉ status code.

## 14. Quy trình xử lý khi phát hiện field bị ghi ngoài ý muốn

Khi một client có thể thay đổi field ngoài dự kiến, kiểm tra theo thứ tự:

1. Xác định endpoint và HTTP method đã nhận request.
2. Lưu request body thực tế và content type.
3. Xác định entity property nào đã thay đổi sau binding.
4. Kiểm tra getter/setter, constructor, field visibility và Jackson annotation.
5. Kiểm tra ObjectMapper/message converter của ứng dụng.
6. Đánh dấu property server-managed bằng READ_ONLY hoặc ẩn hoàn toàn nếu phù hợp.
7. Nếu input cần allowlist rõ ràng, chuyển sang request DTO và service mapping.
8. Kiểm tra association endpoint và JSON association binding riêng.
9. Đặt validation và authorization ở server.
10. Viết integration test gửi trực tiếp field nhạy cảm trong request.
11. Xem lại dữ liệu đã bị thay đổi và áp dụng quy trình khôi phục phù hợp nếu có.

Không chỉ sửa giao diện để ẩn field. Client có thể gửi request trực tiếp mà không đi qua UI.

## 15. Những nhầm lẫn thường gặp

1. **Cho rằng field không có trên form thì client không thể gửi.** Request HTTP có thể được tạo thủ công.
2. **Cho rằng Jackson chỉ bind các field có trong DTO của UI.** Khi endpoint nhận entity, Jackson dựa trên property mapping của model và cấu hình.
3. **Dùng \`@JsonIgnore\` trong khi vẫn cần trả field cho client.** Dùng READ_ONLY nếu cần đọc nhưng không nhận input.
4. **Dùng \`@JsonProperty(READ_ONLY)\` như cơ chế phân quyền.** Annotation kiểm soát JSON binding, không xác định user nào được phép đọc hoặc thay đổi qua các đường khác.
5. **Bật FAIL_ON_UNKNOWN_PROPERTIES rồi cho rằng đã chặn mass assignment.** Cấu hình đó không chặn property nhạy cảm đã tồn tại trên entity.
6. **Chỉ kiểm tra POST.** PUT, PATCH và association update cũng cần kiểm soát.
7. **Ẩn association link rồi cho rằng không thể ghi quan hệ.** Kiểm tra trực tiếp association URI và JSON binding.
8. **Dùng \`exported = false\` thay cho field allowlist.** Annotation đó điều khiển việc export resource/method/association, không phải quy tắc tổng quát cho mọi property input.
9. **Tin ownerId hoặc tenantId từ client.** Các giá trị này cần được xác định hoặc xác minh ở server.
10. **Chỉ kiểm tra response.** Field có thể đã được ghi vào database dù response không hiển thị nó.
11. **Cho rằng validation tự chặn field không được phép.** Validation kiểm tra giá trị; allowlist quyết định property nào được phép nhận input.
12. **Dùng projection để chống mass assignment.** Projection chủ yếu điều khiển representation đọc, không phải allowlist ghi.

## 16. Checklist triển khai an toàn

- Xác định rõ property nào được phép ghi cho từng use case.
- Đánh dấu property server-managed bằng \`@JsonProperty(access = READ_ONLY)\` nếu vẫn cần serialize.
- Dùng \`@JsonIgnore\` nếu property không nên được đọc/ghi qua JSON.
- Chỉ dùng WRITE_ONLY cho input thật sự cần thiết và xử lý secret an toàn.
- Dùng DTO allowlist cho endpoint có input giới hạn hoặc quy tắc nghiệp vụ phức tạp.
- Map từng field được phép trong service.
- Xác định tenant, owner, role, audit và trạng thái workflow ở server.
- Kiểm soát association bằng cả export configuration và authorization.
- Dùng Bean Validation và domain invariant.
- Bảo vệ thao tác nhạy cảm bằng Spring Security/service authorization.
- Không dựa vào UI, hidden link hoặc unknown-property behavior làm ranh giới bảo mật.
- Integration test POST, PUT, PATCH và association update với payload có field ngoài dự kiến.
- Kiểm tra database state sau mỗi request thử nghiệm.
- Đảm bảo response không tiết lộ secret và dữ liệu nội bộ.

## Tóm tắt

Mass assignment xuất hiện khi JSON được bind trực tiếp vào domain object và client có thể gửi thêm những property mà use case không cho phép thay đổi. Trong Spring Data REST, cần xem xét mọi endpoint nhận JSON, đặc biệt POST, PUT và PATCH, cùng với các association resource.

Dùng \`@JsonProperty(access = READ_ONLY)\` cho property cần đọc nhưng không nhận input; dùng \`@JsonIgnore\` nếu property không được trao đổi qua JSON; dùng WRITE_ONLY cho input không được trả lại. Khi cần allowlist rõ ràng, nhận request DTO và chỉ map các field được phép trong service.

Validation, authorization và domain invariant vẫn phải được thực thi ở server. Hãy kiểm thử bằng request trực tiếp chứa role, tenant, owner, trạng thái và association ngoài dự kiến, rồi xác nhận database không bị thay đổi trái phép.

## Tài liệu tham khảo

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Customizing JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Jackson — JsonProperty.Access](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html)
- [Jackson — JsonIgnore](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
