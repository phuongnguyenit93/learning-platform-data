# Giảm phụ thuộc giữa cấu trúc entity và hợp đồng HTTP trong Spring Data REST

## Mục tiêu

Spring Data REST có thể xuất bản trực tiếp repository và biểu diễn entity thành JSON/HAL. Cách này giúp tạo API nhanh, nhưng cũng khiến cấu trúc domain hoặc persistence dễ trở thành một phần của hợp đồng HTTP mà client đang sử dụng.

Khi đổi tên thuộc tính, tách entity, thay quan hệ hoặc bổ sung trường nội bộ, response API có thể thay đổi theo. Để giảm phụ thuộc, cần chọn đúng mức trừu tượng cho từng endpoint: projection khi chỉ cần điều chỉnh cách đọc, cấu hình resource khi cần ổn định đường dẫn và relation, hoặc DTO cùng controller/service riêng khi cần hợp đồng HTTP độc lập với entity.

Sau bài này, bạn có thể:

- Nhận biết rủi ro khi xuất bản entity trực tiếp.
- Dùng projection để kiểm soát representation đọc.
- Ổn định path và relation name của Spring Data REST.
- Tách request/response DTO khỏi entity cho API cần hợp đồng riêng.
- Lựa chọn cách xuất bản repository và kiểm thử khả năng tương thích.

## 1. Vì sao entity và hợp đồng HTTP dễ bị gắn chặt?

Giả sử domain model có entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;

    private String internalNote;

    // constructors, getters và setters
}
~~~

Khi repository được Spring Data REST xuất bản, client có thể đọc trực tiếp representation của Person. Những thuộc tính được serializer đưa ra có thể trở thành điều mà frontend, mobile app hoặc hệ thống tích hợp phụ thuộc vào.

Điều đó tạo ra một số rủi ro:

- Đổi **firstName** thành **givenName** có thể làm client không đọc được trường cũ.
- Gộp **firstName** và **lastName** thành một thuộc tính **fullName** có thể làm thay đổi JSON schema.
- Tách một entity thành nhiều entity hoặc thay quan hệ JPA có thể làm thay đổi cách biểu diễn association.
- Thêm trường nội bộ có thể vô tình đưa dữ liệu không dành cho client ra response.
- Đổi tên repository path hoặc finder relation có thể làm các URL client đang gọi không còn hợp lệ.

Cần phân biệt hai mô hình:

- **Domain/persistence model:** phản ánh nghiệp vụ, quan hệ và cách ứng dụng lưu trữ dữ liệu.
- **HTTP contract:** phản ánh dữ liệu, thao tác, URL, status và media type mà client được phép dựa vào.

Hai mô hình có thể giống nhau ở một ứng dụng nhỏ, nhưng không nên mặc định chúng phải luôn giống nhau. Hợp đồng HTTP cần được quản lý như một giao diện công khai có vòng đời riêng.

## 2. Dùng projection để kiểm soát representation đọc

Spring Data REST hỗ trợ projection để giới hạn hoặc định hình các thuộc tính được hiển thị trong representation. Đây là lựa chọn phù hợp khi bạn vẫn muốn dùng repository resource nhưng chỉ cần một góc nhìn đọc cụ thể.

Ví dụ tạo projection cho Person:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(
    name = "personSummary",
    types = Person.class
)
public interface PersonSummary {

    Long getId();

    String getFirstName();

    String getLastName();
}
~~~

Projection trên chỉ công bố các thuộc tính cần cho màn hình danh sách. Trường **email** và **internalNote** không nằm trong representation này.

Đăng ký projection làm excerpt mặc định cho collection resource:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Client cũng có thể yêu cầu projection theo tên, nếu projection được Spring Data REST phát hiện:

~~~http
GET /people/42?projection=personSummary
Accept: application/hal+json
~~~

Các điểm cần hiểu:

- **Projection** định hình representation trả về; nó không thay đổi entity hoặc schema database.
- **excerptProjection** chọn projection mặc định cho các phần tử trong collection representation.
- Query parameter **projection** cho phép client chọn projection đã được xuất bản.
- Tên projection là một phần của API nếu client gọi nó trực tiếp, nên cần giữ ổn định hoặc có kế hoạch chuyển đổi.

Projection giúp giảm việc client phụ thuộc vào toàn bộ entity, nhưng chưa tách hoàn toàn hợp đồng HTTP khỏi domain model. Interface vẫn tham chiếu tới kiểu Person và tên thuộc tính của nó. Khi entity đổi cấu trúc, projection có thể cần được cập nhật.

Projection cũng không phải ranh giới phân quyền. Không dựa vào việc một projection không hiển thị trường nào đó để thay thế authorization ở server. Những dữ liệu nhạy cảm phải được bảo vệ bằng policy truy cập phù hợp và kiểm thử trên tất cả endpoint có thể trả dữ liệu đó.

## 3. Ổn định path, relation và tên endpoint

Ngoài JSON representation, URL và relation name cũng là một phần của hợp đồng HTTP.

Spring Data REST cho phép tùy chỉnh đường dẫn và collection relation trên repository:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Có thể tùy chỉnh path và relation của finder method:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    @RestResource(
        path = "by-email",
        rel = "byEmail"
    )
    Optional<Person> findByEmail(String email);
}
~~~

Finder có thể được truy cập qua search resource tương ứng, ví dụ:

~~~http
GET /people/search/by-email?email=person@example.com
Accept: application/hal+json
~~~

Dùng relation name ổn định giúp client khám phá liên kết qua HAL thay vì tự ghép URL từ tên class hoặc tên method Java.

Tuy nhiên, tùy chỉnh path và relation chỉ ổn định cách định danh resource. Nó không tự tách representation của entity khỏi hợp đồng JSON. Nếu thuộc tính domain được xuất bản trực tiếp, thay đổi thuộc tính vẫn có thể ảnh hưởng response.

Khi thay đổi path hoặc relation đang được client sử dụng, hãy coi đó là thay đổi API cần có lộ trình tương thích. Nếu có thể, duy trì link cũ trong giai đoạn chuyển đổi hoặc xuất bản endpoint mới trước khi loại bỏ endpoint cũ.

## 4. Dùng DTO và controller riêng khi cần hợp đồng độc lập

Nếu API cần tên trường, cấu trúc lồng nhau, validation hoặc quy tắc ghi riêng, hãy tạo request/response DTO. Controller nhận DTO, gọi service và ánh xạ sang domain model. Client không cần biết entity được lưu như thế nào.

Ví dụ response DTO:

~~~java
public record PersonResponse(
        Long id,
        String fullName
) {
}
~~~

Request DTO:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record CreatePersonRequest(
        @NotBlank String firstName,
        @NotBlank String lastName,
        @Email String email
) {
}
~~~

Controller minh họa:

~~~java
@RestController
@RequestMapping("/api/v1/people")
public class PersonApiController {

    private final PersonService personService;

    public PersonApiController(PersonService personService) {
        this.personService = personService;
    }

    @GetMapping("/{id}")
    public PersonResponse getById(@PathVariable Long id) {
        return personService.getResponse(id);
    }

    @PostMapping
    public ResponseEntity<PersonResponse> create(
            @Valid @RequestBody CreatePersonRequest request) {

        PersonResponse created = personService.create(request);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(created);
    }
}
~~~

Service chịu trách nhiệm phối hợp nghiệp vụ, truy cập repository và ánh xạ entity sang DTO. Controller không cần công bố trực tiếp entity:

~~~text
HTTP request
    |
    v
CreatePersonRequest
    |
    v
Controller
    |
    v
Application service
    |
    +--> Validate nghiệp vụ
    +--> Repository / domain model
    +--> Mapping
    |
    v
PersonResponse
    |
    v
HTTP response
~~~

Trong ví dụ, client nhận **fullName** dù entity vẫn lưu **firstName** và **lastName** riêng. Sau này domain có thể thay đổi cách lưu tên mà response DTO vẫn giữ nguyên nếu ý nghĩa nghiệp vụ không đổi.

Để tránh Spring Data REST đồng thời tự xuất bản repository theo entity representation, có thể ẩn repository khỏi REST export:

~~~java
@RepositoryRestResource(exported = false)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Repository vẫn là Spring bean để service inject và sử dụng; thiết lập **exported = false** ngăn Spring Data REST xuất bản repository resource tương ứng. Hãy kiểm tra các endpoint và association liên quan để chắc chắn không còn đường truy cập ngoài ý muốn.

Nếu vẫn cần Spring Data REST cho một số resource khác, có thể giữ chúng và chỉ xây controller riêng cho phần hợp đồng cần độc lập. Không cần chuyển toàn bộ ứng dụng sang một kiểu API duy nhất.

## 5. Kiểm soát dữ liệu ghi và association

Đưa entity trực tiếp vào request body có thể khiến client phụ thuộc vào các thuộc tính persistence và vô tình cho phép cập nhật trường mà nghiệp vụ không muốn công khai.

Request DTO tạo mới chỉ nên chứa dữ liệu client được phép gửi. Khi cập nhật, có thể dùng một DTO riêng với các trường được phép thay đổi. Service xác định entity nào được sửa, kiểm tra quyền, áp dụng quy tắc nghiệp vụ và lưu thay đổi.

Ví dụ, client được phép gửi **firstName**, **lastName** và **email**, nhưng không được gửi **internalNote**, **createdAt** hoặc trạng thái kiểm duyệt nội bộ. DTO allowlist giúp giới hạn rõ input contract.

Tương tự, không nên mặc định mọi quan hệ JPA đều cần xuất bản thành association resource. Một association có thể là chi tiết triển khai của domain. Có thể ẩn quan hệ không dành cho client bằng cấu hình export phù hợp, ví dụ:

~~~java
@ManyToOne
@RestResource(exported = false)
private InternalProfile internalProfile;
~~~

Khi API cần thao tác với quan hệ, hãy quyết định rõ client cần liên kết một resource có sẵn, gửi một định danh, hay thực hiện một use case nghiệp vụ. DTO và service riêng cho phép thiết kế thao tác theo ngôn ngữ nghiệp vụ thay vì buộc client thao tác trực tiếp trên graph entity.

Không dùng DTO để bỏ qua kiểm tra quyền. Service vẫn phải xác minh người gọi có quyền đọc hoặc thay đổi đúng entity và association.

## 6. Chọn giải pháp theo nhu cầu

| Nhu cầu | Cách tiếp cận phù hợp | Giới hạn cần nhớ |
|---|---|---|
| Chỉ muốn ẩn bớt trường khi đọc | Projection | Vẫn gắn với domain type và tên thuộc tính |
| Muốn collection có representation mặc định | excerptProjection | Chủ yếu định hình collection excerpt |
| Muốn URL và relation ổn định | @RepositoryRestResource, @RestResource | Không tự tách JSON schema khỏi entity |
| Muốn input có allowlist và validation riêng | Request DTO + controller/service | Cần tự quản lý mapping và HTTP behavior |
| Muốn response giữ nguyên khi entity tái cấu trúc | Response DTO + controller/service | Cần kiểm thử contract và duy trì phiên bản |
| Muốn ngừng xuất bản repository trực tiếp | exported = false | Client phải dùng API khác đã được công bố |

Có thể áp dụng theo từng bước. Bắt đầu với projection nếu mục tiêu chỉ là representation đọc. Khi cần kiểm soát write contract, quy tắc nghiệp vụ hoặc cấu trúc response độc lập, chuyển phần use case đó sang DTO và controller/service riêng.

## 7. Quản lý thay đổi hợp đồng HTTP

Một hợp đồng ổn định không có nghĩa API không bao giờ thay đổi. Điều quan trọng là thay đổi có chủ đích và có khả năng tương thích.

Một số nguyên tắc thực tế:

- **Ưu tiên thay đổi bổ sung:** thêm trường optional hoặc thêm link thường ít ảnh hưởng hơn đổi tên hay xóa trường đang dùng.
- **Không tái sử dụng tên cũ cho ý nghĩa mới:** client cũ có thể hiểu sai dữ liệu.
- **Có giai đoạn deprecation:** khi cần thay field hoặc endpoint, công bố cách thay thế và duy trì đường cũ trong thời gian chuyển đổi phù hợp.
- **Version khi có breaking change:** dùng version URI hoặc chiến lược versioning nhất quán của hệ thống, ví dụ **/api/v1/** và **/api/v2/**.
- **Giữ semantics HTTP:** xác định rõ status code, media type, validation error và hành vi khi resource không tồn tại.
- **Ưu tiên link HAL:** client nên theo link do server cung cấp thay vì ghép URL từ cấu trúc class hoặc tên repository.
- **Không để lộ dữ liệu nội bộ:** kiểm tra cả item, collection, projection, association và custom endpoint.

Không nên tăng version chỉ vì entity nội bộ được refactor. Nếu DTO và contract bên ngoài không thay đổi, client không cần biết chi tiết persistence đã thay đổi.

## 8. Kiểm thử contract thay vì chỉ kiểm tra entity

Khi entity và HTTP contract được tách ra, cần kiểm tra trực tiếp response mà client nhận được. Unit test service vẫn hữu ích, nhưng không thay thế integration test cho HTTP endpoint.

Ví dụ kiểm tra response DTO:

~~~java
@Test
void getPersonReturnsStableResponseContract() throws Exception {
    mockMvc.perform(get("/api/v1/people/42")
            .accept(MediaType.APPLICATION_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.id").value(42))
        .andExpect(jsonPath("$.fullName").value("An Nguyen"))
        .andExpect(jsonPath("$.internalNote").doesNotExist());
}
~~~

Ví dụ kiểm tra input contract không nhận thiếu trường bắt buộc:

~~~java
@Test
void createPersonRejectsBlankFirstName() throws Exception {
    mockMvc.perform(post("/api/v1/people")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "firstName": " ",
                  "lastName": "Nguyen",
                  "email": "an@example.com"
                }
                """))
        .andExpect(status().isBadRequest());
}
~~~

Đây là ví dụ định hướng; test cần chuẩn bị dữ liệu và cấu hình MockMvc theo ứng dụng thực tế.

Ngoài ra, nên xác nhận:

1. Projection trả đúng tập trường đã công bố.
2. Collection resource sử dụng excerpt projection mong muốn.
3. Repository được đánh dấu **exported = false** không còn endpoint Spring Data REST công khai.
4. Custom endpoint giữ nguyên JSON field, status và validation behavior sau khi entity thay đổi.
5. Client có thể theo các HAL links mà không cần suy đoán đường dẫn.
6. Các trường nội bộ không xuất hiện qua item, collection hoặc association endpoint khác.

## Ghi nhớ

Xuất bản entity trực tiếp giúp tạo API nhanh nhưng khiến cấu trúc domain dễ trở thành hợp đồng HTTP. Dùng projection để kiểm soát representation đọc, dùng annotation để ổn định path và relation, và dùng DTO cùng controller/service khi cần input, output hoặc vòng đời API độc lập. Giữ contract test để việc tái cấu trúc entity không vô tình làm hỏng client đang sử dụng API.