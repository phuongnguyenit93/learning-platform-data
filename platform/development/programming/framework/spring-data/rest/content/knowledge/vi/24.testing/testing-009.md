# Kiểm tra projection, excerpt và dữ liệu nhạy cảm

## Mục tiêu

Spring Data REST có thể biểu diễn cùng một entity theo nhiều dạng JSON thông qua projection. Projection cho phép chọn các thuộc tính cần xuất hiện trong representation, tạo tên hiển thị hoặc lồng projection cho association. Excerpt projection là một projection được cấu hình làm dạng tóm tắt mặc định khi entity xuất hiện trong collection representation.

Những cơ chế này hữu ích khi API cần trả ít dữ liệu hơn cho danh sách, cung cấp nhiều góc nhìn cho từng loại client hoặc tránh gửi các thuộc tính không cần thiết. Tuy nhiên, projection và excerpt là cơ chế định hình representation; chúng không tự tạo authorization rule và không bảo vệ dữ liệu nhạy cảm khỏi mọi endpoint.

Bài này hướng dẫn cách khai báo và chọn projection, cấu hình excerpt, kiểm tra các response thực tế và thiết lập ranh giới an toàn cho dữ liệu nhạy cảm.

## 1. Projection là gì?

Projection là một interface mô tả tập thuộc tính mà Spring Data REST sẽ dùng để tạo representation. Thay vì serialize toàn bộ domain object theo representation mặc định, Spring Data REST tạo một view theo các accessor được khai báo trong projection.

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
    private String phoneNumber;

    // getters and setters
}
~~~

Projection chỉ hiển thị tên:

~~~java
@Projection(name = "personName", types = Person.class)
public interface PersonName {

    String getFirstName();

    String getLastName();
}
~~~

Khi client chọn projection, representation tập trung vào các thuộc tính đã khai báo. Spring Data REST vẫn có thể bổ sung các HAL link cần thiết để điều hướng đến tài nguyên.

Projection thường được dùng khi:

- Danh sách chỉ cần vài field ngắn gọn.
- Màn hình chi tiết cần một tập field khác màn hình danh sách.
- Client cần một property tổng hợp hoặc tên hiển thị.
- Association cần biểu diễn theo dạng rút gọn.
- API cần tránh truyền các field không cần thiết trong một response cụ thể.

Projection không thay đổi cấu trúc entity hoặc schema database. Nó định nghĩa một cách nhìn vào entity khi tạo representation.

## 2. Khai báo và phát hiện projection

Projection được khai báo bằng annotation `@Projection`:

~~~java
@Projection(name = "personName", types = Person.class)
public interface PersonName {

    String getFirstName();

    String getLastName();
}
~~~

Các điểm cần nhớ:

- `name` là tên công khai dùng trong query parameter `projection`.
- `types` xác định domain type mà projection áp dụng.
- Projection là interface; Spring Data tạo proxy để cung cấp các accessor.
- Các getter xác định thuộc tính hoặc nested view cần xuất hiện.

Spring Data REST phát hiện projection theo package convention. Đặt projection trong cùng package với domain type hoặc một subpackage của package đó để repository exporter có thể tìm thấy.

Ví dụ cấu trúc:

~~~text
com.example.people
├── Person.java
├── PersonRepository.java
└── projection
    ├── PersonName.java
    └── PersonDetail.java
~~~

Nếu projection không xuất hiện trong API, kiểm tra package của interface, tên projection và domain type trong `@Projection`. Không nhầm tên interface Java với giá trị `name`: client dùng giá trị `name` trong URL.

## 3. Chọn projection bằng query parameter

Một projection có thể được yêu cầu bằng query parameter `projection`.

Ví dụ lấy collection:

~~~http
GET /people?projection=personName
Accept: application/hal+json
~~~

Ví dụ lấy một item:

~~~http
GET /people/42?projection=personName
Accept: application/hal+json
~~~

Spring Data REST dùng tên projection đã đăng ký để tạo representation tương ứng. HAL links vẫn có thể xuất hiện cùng các field của projection.

Nếu không truyền `projection`, endpoint sử dụng representation mặc định của resource, trừ trường hợp collection resource có excerpt projection được cấu hình.

Tên projection trong URL phân biệt với tên repository path và tên Java interface. Ví dụ `PersonName` là tên interface, còn `personName` là tên công khai trong `@Projection`.

Client chỉ nên phụ thuộc vào projection name đã được xem như một phần của API contract. Khi đổi tên projection, cần cập nhật client và tài liệu API tương ứng.

## 4. Cấu hình excerpt projection cho collection

Excerpt projection là projection được Spring Data REST tự động dùng làm dạng tóm tắt cho entity trong collection representation khi repository khai báo nó.

Ví dụ:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();
}
~~~

Cấu hình repository:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Khi client gọi:

~~~http
GET /people
Accept: application/hal+json
~~~

các Person trong collection representation sẽ dùng excerpt projection đã cấu hình. Điều này giúp danh sách chỉ chứa các field tóm tắt, thay vì toàn bộ dữ liệu chi tiết.

Excerpt projection thường không tự động thay representation của item resource. Ví dụ `GET /people/42` vẫn sử dụng representation mặc định nếu client không chọn projection. Nếu cần item dùng một view cụ thể, yêu cầu projection rõ ràng:

~~~http
GET /people/42?projection=personExcerpt
~~~

Đây là khác biệt quan trọng khi kiểm tra dữ liệu nhạy cảm: cấu hình excerpt cho collection không có nghĩa mọi cách truy cập entity đều dùng cùng một tập field.

## 5. Projection mặc định và excerpt projection khác nhau

| Cơ chế | Cách chọn | Phạm vi thường dùng |
|---|---|---|
| Representation mặc định | Không truyền query parameter | Item resource và collection nếu không có excerpt |
| Projection tường minh | `?projection=personName` | Client chọn view đã đăng ký |
| Excerpt projection | `excerptProjection = PersonExcerpt.class` trên repository | Tự động rút gọn entity trong collection representation |

Một repository có thể khai báo excerpt projection và vẫn cho client chọn projection khác bằng query parameter. Excerpt là lựa chọn mặc định cho collection; projection tường minh cho phép client yêu cầu một view khác đã được công bố.

Hãy kiểm tra riêng:

- Collection resource.
- Item resource.
- Collection trả về từ search resource.
- Entity xuất hiện trong association.
- Projection được chọn tường minh.

Không giả định mọi loại response đều áp dụng excerpt theo cùng cách. Cách biểu diễn còn phụ thuộc resource và phiên bản Spring Data REST; integration test sẽ xác nhận hợp đồng API thực tế.

## 6. Nhiều projection cho các nhu cầu khác nhau

Một domain type có thể có nhiều projection:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

~~~java
@Projection(name = "personContact", types = Person.class)
public interface PersonContact {

    String getFirstName();

    String getLastName();

    String getEmail();

    String getPhoneNumber();
}
~~~

Client có thể chọn:

~~~http
GET /people/42?projection=personSummary
GET /people/42?projection=personContact
~~~

View summary phù hợp cho màn hình danh sách hoặc lựa chọn người dùng. View contact phù hợp với chức năng cần email và số điện thoại.

Không nên tạo một projection chứa tất cả thuộc tính rồi dùng nó ở mọi nơi chỉ để giảm số interface. Các view riêng giúp hợp đồng API thể hiện rõ dữ liệu cần thiết của từng use case.

Cũng cần xem projection là một API công khai: khi thêm getter vào projection đang dùng, dữ liệu mới có thể bắt đầu xuất hiện trong response và được client tiêu thụ.

## 7. Nested projection và association

Projection có thể khai báo một view cho association thay vì serialize toàn bộ object liên quan.

Ví dụ domain:

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String city;
    private String district;
    private String street;
}
~~~

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;

    @ManyToOne
    private Address address;
}
~~~

Projection cho địa chỉ:

~~~java
@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {

    String getCity();

    String getDistrict();
}
~~~

Projection cho Person có thể khai báo accessor trả về projection của association:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    AddressSummary getAddress();
}
~~~

Representation khi chọn `personWithAddress` có thể chứa city và district của address theo nested view. Những field khác như street không được yêu cầu bởi projection này.

Nested projection hữu ích khi API cần một cấu trúc representation thống nhất và không muốn client phải gọi thêm nhiều association endpoint chỉ để hiển thị vài field. Tuy nhiên, nếu association lớn hoặc lazy-loaded, hãy cân nhắc số truy vấn và cách tải dữ liệu. Projection định hình JSON nhưng không đảm bảo mọi trường hợp đều tối ưu số SQL query.

Không đưa association nhạy cảm vào projection chỉ vì accessor có sẵn. Mỗi nested projection cũng là một phần của API contract và cần được kiểm tra như projection cấp cao nhất.

## 8. Property tổng hợp trong projection

Projection có thể định nghĩa property tính toán thông qua Spring Expression Language với `@Value`.

Ví dụ:

~~~java
@Projection(name = "personDisplay", types = Person.class)
public interface PersonDisplay {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();

    String getEmail();
}
~~~

Client nhận `displayName` được tạo từ firstName và lastName. Property tổng hợp phù hợp cho giá trị trình bày không cần lưu riêng trong database.

Với biểu thức phức tạp, nhiều phép gọi service hoặc logic nghiệp vụ có thể thay đổi, nên chuyển logic sang DTO assembler hoặc custom controller/service. Giữ SpEL đơn giản để projection dễ hiểu và tránh biến representation thành nơi thực thi logic nghiệp vụ khó kiểm soát.

Hãy kiểm tra null handling trong biểu thức. Ví dụ nối chuỗi với field null có thể tạo kết quả không như mong muốn; viết biểu thức phù hợp hoặc dùng method tạo display value trong một thành phần chuyên trách.

## 9. Projection không phải là authorization

Projection quyết định field nào xuất hiện trong một representation cụ thể. Nó không quyết định người dùng có quyền đọc entity hay thực hiện thao tác nào.

Ví dụ:

- Người dùng có thể chọn một projection khác nếu projection đó được công bố.
- Item resource có thể dùng representation mặc định thay vì excerpt.
- Search resource hoặc association có thể có cách biểu diễn riêng.
- Một custom endpoint có thể trả dữ liệu qua đường khác.
- Projection không tự ngăn repository method trả về entity hoặc field nhạy cảm.

Vì vậy, không dùng projection như ranh giới bảo mật duy nhất. Hãy dùng Spring Security để xác thực và authorization ở request, method hoặc object level. Với dữ liệu chỉ một số nhóm người dùng được phép đọc, cần áp dụng access control ở server trước khi trả dữ liệu.

Nếu hai nhóm người dùng cần hai mức dữ liệu khác nhau, có thể tạo các endpoint hoặc service method có authorization rõ ràng và trả DTO theo quyền. Không nên cho rằng chỉ cần đặt tên projection khó đoán là đã bảo vệ được dữ liệu.

## 10. Bảo vệ field nhạy cảm trong entity

Ví dụ Person có password hash và token nội bộ:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String email;

    @JsonIgnore
    private String passwordHash;

    @JsonIgnore
    private String internalAccessToken;
}
~~~

`@JsonIgnore` yêu cầu Jackson bỏ qua property trong quá trình serialization và deserialization theo cấu hình mặc định của annotation. Đây là cách phù hợp khi field hoàn toàn không thuộc hợp đồng JSON công khai.

Nếu client được phép gửi giá trị khi tạo hoặc cập nhật nhưng server không bao giờ được trả giá trị đó, có thể cân nhắc:

~~~java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String password;
~~~

`WRITE_ONLY` cho phép Jackson nhận property khi deserialize request nhưng không serialize property ra response. Cần xử lý và hash password ở service trước khi lưu; không lưu plaintext password.

Không dùng password hash, reset token, API key, refresh token hoặc secret nội bộ làm field hiển thị trong projection. Nếu field cần có trong request nhưng không được trả về, kiểm thử cả chiều đọc lẫn chiều ghi.

## 11. Kiểm tra projection không làm lộ dữ liệu nhạy cảm

Một projection có thể vô tình thêm getter cho field nhạy cảm:

~~~java
// Không dùng cho API công khai nếu passwordHash là dữ liệu nhạy cảm.
@Projection(name = "personUnsafe", types = Person.class)
public interface PersonUnsafe {

    String getEmail();

    String getPasswordHash();
}
~~~

Hãy xem mọi projection như một danh sách field được công bố. Khi review một thay đổi projection, kiểm tra:

- Getter trực tiếp có trả field nhạy cảm không.
- Nested projection có mở rộng sang association nhạy cảm không.
- SpEL có truy cập property hoặc bean trả dữ liệu nhạy cảm không.
- Excerpt projection có thêm field ngoài nhu cầu tóm tắt không.
- Representation mặc định có vô tình trả field nhạy cảm không.
- Search resource và custom controller có serialize cùng entity theo đường khác không.

Nếu yêu cầu bảo mật nghiêm ngặt, dùng DTO với danh sách field cho phép rõ ràng hoặc custom response model. Không phụ thuộc vào việc một projection hiện tại tình cờ không khai báo field nhạy cảm; một projection mới có thể vô tình đưa field đó trở lại.

## 12. Projection không thay thế request model cho dữ liệu ghi

Projection chủ yếu định hình representation khi đọc. Nó không phải một request schema đầy đủ để quyết định client được phép thay đổi field nào.

Ví dụ, nếu client gửi JSON có `role`, `accountStatus` hoặc `isAdmin`, việc các field này không có trong projection đọc không tự động ngăn chúng được deserialize hoặc cập nhật bởi endpoint ghi.

Với field server-managed:

- Dùng DTO/request model riêng nếu cần allow-list dữ liệu đầu vào.
- Không cho client tự đặt role, owner, trạng thái duyệt hoặc audit timestamp.
- Thiết lập field do server quản lý ở service/event handler.
- Dùng validation và authorization cho thao tác cập nhật.
- Kiểm thử request body chứa field ngoài hợp đồng.

Nếu cần kiểm soát chặt cả read model lẫn write model, custom controller/service với DTO tách biệt thường rõ ràng hơn việc chỉ dựa vào projection trên entity.

## 13. Kiểm thử representation bằng MockMvc

Nên kiểm thử JSON thực tế cho collection, item, projection tường minh và excerpt projection.

Ví dụ repository:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Test collection sử dụng excerpt:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonProjectionTests {

    @Autowired
    MockMvc mvc;

    @Test
    void collectionUsesConfiguredExcerpt() throws Exception {
        mvc.perform(get("/people")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._embedded.people[0].firstName")
                .exists())
            .andExpect(jsonPath("$._embedded.people[0].passwordHash")
                .doesNotExist());
    }
}
~~~

Test projection tường minh:

~~~java
@Test
void explicitProjectionReturnsSelectedFields() throws Exception {
    mvc.perform(get("/people/42")
            .param("projection", "personName")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.firstName").exists())
        .andExpect(jsonPath("$.lastName").exists())
        .andExpect(jsonPath("$.passwordHash").doesNotExist());
}
~~~

Test representation mặc định của item:

~~~java
@Test
void defaultItemRepresentationDoesNotExposeSecrets() throws Exception {
    mvc.perform(get("/people/42")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.passwordHash").doesNotExist())
        .andExpect(jsonPath("$.internalAccessToken").doesNotExist());
}
~~~

Đây là khung kiểm thử; cần tạo fixture Person có ID phù hợp, đảm bảo collection có ít nhất một phần tử và điều chỉnh JSON path theo tên collection resource thực tế.

Nên bổ sung test cho:

- Projection được phát hiện và chọn đúng bằng tên.
- Excerpt chỉ áp dụng ở những representation dự kiến.
- Item resource không có projection không vô tình lộ secret.
- Search result và association representation không lộ field nhạy cảm.
- Nested projection chỉ trả các field đã chọn.
- Projection mới không thêm password, token hoặc internal property.
- Request ghi không thể sửa các field server-managed.
- Người dùng không có quyền không thể truy cập endpoint dù biết projection name.

## 14. Kiểm tra dữ liệu nhạy cảm ngoài JSON body

Kiểm tra JSON response là cần thiết nhưng chưa đủ. Một số field có thể xuất hiện ở các vị trí khác:

- HAL link hoặc URI có thể chứa identifier nội bộ.
- Error response có thể đưa exception message hoặc input value ra ngoài.
- Log có thể ghi password, token hoặc request body.
- Search endpoint có thể trả entity bằng projection khác.
- Export endpoint hoặc custom controller có thể serialize cùng entity theo cấu hình khác.
- Association endpoint có thể hiển thị nested object ngoài dự kiến.

Không đưa secret vào URI, link, exception message hoặc log. Dùng log có kiểm soát và mask dữ liệu nhạy cảm. Nếu response cần chứa một public identifier, hãy tách nó khỏi secret hoặc internal token.

Khi kiểm tra API, tìm các field nhạy cảm trong toàn bộ response JSON và header, không chỉ ở root object.

## 15. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Projection không được nhận diện | Interface nằm ngoài package domain hoặc sai types/name | Đặt projection cùng package hoặc subpackage và kiểm tra @Projection |
| Query parameter projection không hoạt động | Dùng tên interface thay vì projection name | Dùng đúng giá trị name trong @Projection |
| Collection vẫn trả nhiều field | Repository chưa cấu hình excerptProjection | Khai báo excerptProjection trên @RepositoryRestResource |
| Item resource vẫn dùng representation mặc định | Excerpt không tự động áp dụng cho item | Truyền projection tường minh khi cần |
| Projection làm lộ passwordHash | Getter nhạy cảm được khai báo trong projection | Loại getter và bảo vệ field ở serialization boundary |
| @JsonIgnore không được kiểm tra ở mọi đường response | Search/custom endpoint dùng representation khác | Kiểm thử item, collection, search, association và custom controller |
| Nested projection trả quá nhiều dữ liệu | Association getter dùng domain type đầy đủ | Dùng nested projection với tập field tối thiểu |
| Projection được xem như quyền truy cập | Nhầm representation với authorization | Bảo vệ resource/method/object bằng Spring Security |
| Client sửa được field không được hiển thị | Projection đọc không phải request allow-list | Dùng DTO/request model, validation và server-managed fields |
| JSON body không lộ secret nhưng log vẫn có | Request/exception được ghi nguyên văn | Mask hoặc loại dữ liệu nhạy cảm khỏi log |
| Response list có quá nhiều query | Nested association lazy-loading hoặc projection truy cập nhiều relation | Kiểm tra SQL, fetch plan và query strategy |

## 16. Checklist kiểm tra projection, excerpt và secret

- Khai báo projection bằng `@Projection(name, types)`.
- Đặt interface trong package của domain type hoặc subpackage.
- Dùng đúng projection name trong query parameter.
- Cấu hình `excerptProjection` cho collection cần dạng tóm tắt mặc định.
- Kiểm tra riêng collection, item, search result và association representation.
- Không giả định excerpt tự động áp dụng cho item resource.
- Kiểm tra getter, nested projection và SpEL có thể truy cập field nhạy cảm.
- Dùng `@JsonIgnore` cho field không thuộc JSON contract và `WRITE_ONLY` khi chỉ cần nhận input.
- Không trả password hash, token, API key hoặc secret qua projection.
- Dùng DTO/request model và server-side validation để giới hạn field được ghi.
- Dùng Spring Security để kiểm soát ai được đọc tài nguyên; projection không phải authorization.
- Kiểm thử JSON body, response headers, error response và log.
- Kiểm tra số truy vấn khi projection truy cập nested association.

## Kết luận

Projection cho phép Spring Data REST tạo nhiều representation từ cùng một entity; excerpt projection cung cấp dạng tóm tắt mặc định cho entity trong collection resource. Có thể chọn projection bằng query parameter hoặc cấu hình excerpt trên repository. Cần phân biệt collection với item vì excerpt không tự động thay representation mặc định của item. Quan trọng hơn, projection chỉ kiểm soát cách dữ liệu được trình bày trong một response; nó không thay thế authentication, authorization hoặc request validation. Hãy bảo vệ secret ở serialization boundary, tách read projection khỏi write DTO khi cần allow-list chặt và kiểm thử mọi đường response có thể đưa entity ra ngoài.

## Tài liệu tham khảo

- Spring Data REST – Projections and Excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
- Spring Data REST – Projection API: https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/ProjectionDefinitionConfiguration.html
- Spring Data Commons – Projection and interface-based projection concepts: https://docs.spring.io/spring-data/commons/reference/repositories/projections.html
- Jackson – JsonProperty.Access and JsonIgnore annotations: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html
