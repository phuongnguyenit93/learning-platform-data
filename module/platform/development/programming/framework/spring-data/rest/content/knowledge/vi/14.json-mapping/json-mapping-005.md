# Chủ động công bố ID bằng exposeIdsFor khi cần

## Mục tiêu

Spring Data REST mặc định biểu diễn tài nguyên theo hướng hypermedia. Một entity thường được nhận diện qua liên kết HAL như `_links.self.href`; ID của entity không nhất thiết xuất hiện như một thuộc tính thông thường trong JSON.

Khi client cần giá trị ID trực tiếp để lưu trạng thái, ghép dữ liệu với hệ thống khác, hiển thị mã tham chiếu hoặc thực hiện một quy trình tích hợp, có thể cấu hình Spring Data REST công bố ID bằng phương thức `RepositoryRestConfiguration.exposeIdsFor(...)`.

Cấu hình này cho phép ID của các domain type được chọn xuất hiện như một property trong representation. Nó không thay đổi khóa chính, cách sinh ID, URI của item resource hay quyền truy cập dữ liệu. Chỉ bật cho những loại tài nguyên mà hợp đồng API thực sự cần ID trong body.

## 1. ID trong entity và representation REST

Giả sử có entity Person:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;

    // constructors, getters, setters
}
~~~

Repository được Spring Data REST export:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Với cấu hình mặc định, response item thường có representation tương tự:

~~~http
GET /people/42
Accept: application/hal+json
~~~

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Client vẫn có thể nhận diện và điều hướng đến item thông qua liên kết self. Tuy nhiên, nếu ứng dụng phía client cần trường ID riêng để lưu vào state hoặc dùng trong một bảng dữ liệu, việc chỉ có ID nằm trong URL của link có thể không thuận tiện.

Khi bật exposeIdsFor cho Person, representation có thể chứa thêm thuộc tính ID:

~~~json
{
  "id": 42,
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Thứ tự property trong JSON không được bảo đảm. Ví dụ chỉ minh họa việc ID xuất hiện như một thuộc tính dữ liệu thông thường bên cạnh các liên kết HAL.

## 2. Cấu hình exposeIdsFor bằng RepositoryRestConfigurer

Cách phổ biến là triển khai RepositoryRestConfigurer và gọi exposeIdsFor trong configureRepositoryRestConfiguration:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.exposeIdsFor(Person.class);
    }
}
~~~

Trong ví dụ, Spring Data REST được yêu cầu công bố ID của domain type Person. Sau khi ứng dụng khởi động với cấu hình này, response cho tài nguyên Person có thể chứa thuộc tính id.

Có thể truyền nhiều domain type trong cùng một lần gọi:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.exposeIdsFor(
            Person.class,
            Order.class,
            Product.class
        );
    }
}
~~~

Phương thức nhận danh sách kiểu domain qua varargs Class<?>. Hãy truyền class entity/domain được repository quản lý, ví dụ Person.class; không truyền repository interface hoặc kiểu Java của ID như Long.class.

Nếu ứng dụng đã có một RepositoryRestConfigurer, bổ sung cấu hình vào implementation hiện tại hoặc tổ chức các configurer theo cách dự án đang dùng. Tránh tạo nhiều cấu hình trùng lặp khiến người bảo trì khó xác định nơi quản lý REST behavior.

## 3. Chỉ bật ID cho domain type cần thiết

exposeIdsFor được cấu hình theo domain type. Ví dụ, nếu chỉ client của Person cần ID trong JSON, có thể chỉ bật Person:

~~~java
config.exposeIdsFor(Person.class);
~~~

Khi đó, không cần bật ID cho tất cả domain type của ứng dụng. Với Order và Product, representation tiếp tục theo cấu hình hiện tại nếu chúng không nằm trong danh sách được expose.

Bảng lựa chọn:

| Nhu cầu | Cấu hình phù hợp |
|---|---|
| Client cần ID của Person trong JSON | exposeIdsFor(Person.class) |
| Client cần ID của nhiều loại entity | exposeIdsFor(Person.class, Order.class, Product.class) |
| Client chỉ cần điều hướng đến tài nguyên | Dùng HAL self link, không cần expose ID riêng |
| Client cần business code thay cho database ID | Thiết kế thuộc tính business code hoặc entity lookup phù hợp; exposeIdsFor không đổi khóa định danh |
| Không muốn một loại entity lộ ID trong body | Không thêm domain type đó vào exposeIdsFor |

Nên quản lý danh sách ID được công bố như một phần của API contract. Khi thêm domain type mới, hãy xác định client nào thực sự cần ID trước khi đưa class đó vào cấu hình.

## 4. Phân biệt thuộc tính ID và liên kết HAL

ID trong JSON và liên kết HAL giải quyết hai nhu cầu khác nhau:

- Thuộc tính id cung cấp giá trị định danh ở dạng dữ liệu. Client có thể lưu giá trị này, hiển thị nó hoặc dùng để đối chiếu với hệ thống khác.
- Liên kết _links.self.href cung cấp URI chuẩn để client truy cập tài nguyên. Đây là cơ chế hypermedia để điều hướng và thao tác REST.

Ví dụ response có cả hai:

~~~json
{
  "id": 42,
  "firstName": "An",
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42"
    }
  }
}
~~~

Nếu client cần đọc tài nguyên, hãy ưu tiên dùng URI trong self link. Không nên phân tích chuỗi URL để lấy ID khi API đã có thể cung cấp property ID hoặc link có cấu trúc.

Ngược lại, nếu client cần một giá trị ID để lưu trong dữ liệu nghiệp vụ, exposeIdsFor có thể giúp client đọc trực tiếp giá trị đó. Việc có ID trong body không làm mất vai trò của self link và không biến link thành một field ID.

## 5. exposeIdsFor không thay đổi định danh của endpoint

Với repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Item resource vẫn có URI dạng:

~~~http
GET /people/42
~~~

Sau khi gọi exposeIdsFor(Person.class):

- ID xuất hiện trong representation theo cấu hình.
- URI item vẫn được xác định theo entity lookup strategy đang dùng.
- Kiểu ID trong repository vẫn là Long.
- @Id trong entity vẫn xác định persistent identifier.
- Phương thức findById vẫn tìm theo identifier của repository.
- Không có thay đổi schema database hoặc chiến lược sinh ID chỉ vì bật exposeIdsFor.

Nếu mục tiêu là đổi URI item để dùng mã nghiệp vụ thay cho khóa chính, exposeIdsFor không giải quyết việc đó. Spring Data REST có cơ chế entity lookup riêng để ánh xạ URI identifier sang entity. Hãy phân biệt việc công bố ID trong JSON với việc thay đổi cách server tìm entity từ path.

## 6. Khi nào client nên yêu cầu ID?

Một số tình huống ID trong body có ích:

- Bảng dữ liệu phía frontend cần giữ ID để cập nhật hoặc xóa một item sau này.
- Ứng dụng cần đối chiếu entity với một hệ thống tích hợp sử dụng cùng identifier.
- Log hoặc màn hình vận hành cần hiển thị ID để tra cứu.
- Một quy trình xử lý theo lô cần lưu danh sách ID nhận từ response.
- Client cần liên kết dữ liệu response với một bản ghi local đã lưu trước đó.

Nếu client chỉ cần điều hướng hoặc thao tác REST, HAL link thường đã đủ. Tránh công bố ID chỉ vì muốn JSON có thêm trường; mỗi property được trả về đều trở thành một phần của hợp đồng API mà client có thể phụ thuộc.

## 7. Ảnh hưởng đến bảo mật và quyền truy cập

Công bố ID trong JSON không tự cấp quyền đọc, cập nhật hoặc xóa entity. Việc gọi GET, PUT, PATCH hoặc DELETE vẫn phải tuân theo security configuration, authorization rule và exposure của repository.

Tuy vậy, ID có thể tiết lộ thông tin về hệ thống:

- ID tuần tự có thể giúp người dùng suy đoán số lượng bản ghi hoặc thứ tự tạo dữ liệu.
- ID nội bộ có thể được dùng để đối chiếu dữ liệu giữa các hệ thống.
- ID trong response giúp client dễ lưu lại và gửi lại trong request tiếp theo.

Vì vậy:

- Chỉ expose ID cho domain type có nhu cầu rõ ràng.
- Không dùng ID khó đoán như một cơ chế authorization.
- Kiểm tra quyền ở cấp tài nguyên và thao tác, kể cả khi client biết ID.
- Nếu cần định danh công khai khó đoán, cân nhắc public identifier/UUID hoặc business key phù hợp với domain.
- Không đưa thông tin nhạy cảm vào chính giá trị ID.
- Xem việc expose ID là thay đổi representation có thể ảnh hưởng client và tài liệu API.

ID tuần tự không nhất thiết là lỗ hổng nếu authorization được triển khai đúng. Nguy cơ xuất hiện khi ứng dụng dựa vào việc người dùng không biết ID để bảo vệ tài nguyên.

## 8. Kết hợp với projection và Jackson

Spring Data REST có thể dùng projection để tạo representation theo nhu cầu của client. Projection quyết định tập property được đưa vào một dạng representation; exposeIdsFor điều khiển việc Spring Data REST công bố identifier như property thông thường cho domain type.

Ví dụ projection:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Client yêu cầu:

~~~http
GET /people/42?projection=personSummary
Accept: application/hal+json
~~~

Không nên giả định mọi projection đều tự động hiển thị ID chỉ vì domain type đã được cấu hình exposeIdsFor. Nếu client cần ID trong một projection cụ thể, hãy kiểm tra representation thực tế và điều chỉnh projection/API phù hợp với phiên bản Spring Data REST đang dùng.

Jackson annotations, mixins, custom serializers và cấu hình serialization của ứng dụng cũng có thể ảnh hưởng property visibility. Nếu ID bị gắn @JsonIgnore hoặc bị xử lý bởi custom serializer, hãy kiểm thử kết quả thực tế thay vì giả định exposeIdsFor luôn ghi đè mọi quy tắc Jackson.

Không dùng exposeIdsFor để giải quyết một field JSON thông thường bị ẩn vì lý do serialization. Phương thức này dành riêng cho việc công bố identifier mà Spring Data REST quản lý.

## 9. Kiểm tra response sau khi bật exposeIdsFor

Sau khi thêm cấu hình, chạy ứng dụng và gửi GET tới một item có dữ liệu:

~~~http
GET /people/42
Accept: application/hal+json
~~~

Kiểm tra:

1. Response thành công có status phù hợp, thường là 200 OK.
2. Body có property id với giá trị đúng kiểu và đúng identifier của entity.
3. _links.self.href vẫn trỏ đến đúng item.
4. Các field nghiệp vụ khác vẫn được serialize theo cấu hình.
5. Các domain type không được chọn không tự động công bố ID ngoài dự định.
6. Projection và các custom Jackson serializer cho kết quả đúng với hợp đồng API.

Có thể kiểm tra thủ công bằng curl:

~~~bash
curl -i http://localhost:8080/people/42 \
  -H "Accept: application/hal+json"
~~~

Hoặc dùng MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ExposedIdTests {

    @Autowired
    MockMvc mvc;

    @Test
    void personRepresentationContainsItsId() throws Exception {
        mvc.perform(get("/people/42")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(42))
            .andExpect(jsonPath("$._links.self.href")
                .value(org.hamcrest.Matchers.endsWith("/people/42")));
    }
}
~~~

Đây là khung kiểm thử tích hợp. Cần tạo fixture Person có ID xác định hoặc lấy URI từ response POST; không phụ thuộc vào ID tự sinh nếu thứ tự test không cố định.

Nên có thêm test cho một domain type không nằm trong danh sách expose để xác nhận cấu hình chỉ tác động đến các type được chọn. Nếu ứng dụng có projection hoặc custom serializer, test representation của những trường hợp đó riêng.

## 10. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| ID không xuất hiện trong JSON | Chưa gọi exposeIdsFor cho domain type | Thêm đúng entity class vào cấu hình |
| Đã expose Person nhưng Order vẫn không có ID | Chỉ đăng ký Person.class | Thêm Order.class nếu client thực sự cần |
| ID xuất hiện nhưng URL không đổi | exposeIdsFor chỉ thay đổi representation | Dùng entity lookup strategy nếu cần đổi URI identifier |
| Client có ID nhưng vẫn nhận 403 | Biết ID không đồng nghĩa có quyền truy cập | Kiểm tra Spring Security và authorization |
| Projection không có ID | Projection chỉ hiển thị các accessor được định nghĩa | Kiểm tra projection và representation thực tế |
| ID vẫn bị ẩn sau cấu hình | Jackson annotation, mixin hoặc custom serializer ảnh hưởng serialization | Kiểm tra cấu hình Jackson và viết test response |
| Client phụ thuộc vào ID nội bộ | Hợp đồng API đang công bố database identifier | Cân nhắc public ID hoặc business key ổn định |
| Tất cả entity đều lộ ID ngoài dự định | Cấu hình expose quá rộng hoặc dùng danh sách domain type không phù hợp | Chỉ đăng ký các domain type cần thiết |

## 11. Checklist trước khi công bố ID

- Xác định client hoặc use case thực sự cần ID trong JSON.
- Kiểm tra đúng domain type được repository export.
- Dùng config.exposeIdsFor(Entity.class) trong RepositoryRestConfigurer.
- Truyền nhiều entity class khi cần, không truyền repository interface hoặc ID class.
- Giữ self link làm URI chuẩn để điều hướng đến resource.
- Phân biệt ID trong body với identifier dùng trong URI.
- Kiểm tra projection, Jackson annotations và custom serializer.
- Kiểm thử cả domain type được expose và domain type không được expose.
- Xem xét khả năng lộ ID nội bộ và bảo đảm authorization không dựa vào tính khó đoán của ID.
- Cập nhật tài liệu API và client contract nếu representation thay đổi.

## Kết luận

RepositoryRestConfiguration.exposeIdsFor(...) cho phép Spring Data REST công bố ID như một property thông thường trong representation của các domain type được chọn. Cấu hình này hữu ích khi client cần lưu hoặc đối chiếu identifier trực tiếp từ JSON. ID trong body bổ sung cho liên kết HAL self; nó không thay đổi khóa chính, URI item, entity lookup hay quyền truy cập. Hãy chỉ bật cho các loại tài nguyên cần thiết, kiểm tra projection/Jackson và bảo đảm security được thực thi độc lập với việc client có biết ID hay không.

## Tài liệu tham khảo

- Spring Data REST – RepositoryRestConfiguration API, exposeIdsFor(Class<?>...): https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html
- Spring Data REST – Working with Spring Data Repositories and resource representations: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST – Projections and excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
