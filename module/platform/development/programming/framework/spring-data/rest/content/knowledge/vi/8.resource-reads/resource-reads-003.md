# GET tài nguyên đơn và phương thức findById

## Mục tiêu

Trong Spring Data REST, request `GET` đến URI item dùng để đọc một tài nguyên đơn theo identifier của repository. Ví dụ `GET /people/42` yêu cầu server tìm entity có ID là `42` và trả về representation của entity đó.

Ở tầng repository, thao tác này dựa trên phương thức `findById(ID id)` kế thừa từ `CrudRepository` hoặc `JpaRepository`. Spring Data REST nhận ID từ path, chuyển nó sang kiểu ID Java rồi gọi cơ chế truy vấn item của repository. Hiểu mối liên hệ giữa URI, kiểu ID và `findById` giúp xử lý đúng trường hợp tìm thấy, không tìm thấy hoặc gửi ID sai định dạng.

## 1. Collection resource và item resource

Giả sử có entity Person và repository:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    // constructors, getters, setters
}
~~~

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST export repository thành một collection resource và các item resource:

| URI | Ý nghĩa |
|---|---|
| `GET /people` | Đọc collection people |
| `GET /people/42` | Đọc item có ID là 42 |
| `GET /people/57` | Đọc item có ID là 57 |

Nếu ứng dụng đặt base path bằng `spring.data.rest.base-path=/api`, URI tương ứng sẽ là `/api/people`, `/api/people/42` và `/api/people/57`.

Collection request thường đi qua thao tác đọc danh sách của repository, chẳng hạn `findAll(Pageable)` hoặc biến thể phù hợp với repository. Item request cần một identifier cụ thể và đi qua thao tác tìm entity theo ID.

## 2. Luồng xử lý GET một tài nguyên

Với request:

~~~http
GET /people/42
Accept: application/hal+json
~~~

Luồng xử lý khái quát:

1. `RepositoryRestHandlerMapping` nhận diện path `/people/42` thuộc repository đã export là `people`.
2. Spring Data REST xác định kiểu ID của repository. Trong ví dụ, kiểu ID là `Long`.
3. Giá trị `42` lấy từ path được chuyển từ chuỗi sang `Long` bằng cơ chế conversion của Spring.
4. Spring Data REST gọi thao tác tìm item qua repository invoker. Với repository CRUD thông thường, thao tác này sử dụng `findById(42L)`.
5. Nếu tìm thấy entity, Spring Data REST tạo resource representation và trả về HTTP response. Nếu không có entity, request được xử lý như tài nguyên không tồn tại.

Đường đi này là thao tác đọc. Nó không gọi `save()` và không tạo entity mới.

## 3. findById() trong repository

`CrudRepository` khai báo phương thức:

~~~java
Optional<T> findById(ID id);
~~~

Trong đó:

- `T` là kiểu entity, ví dụ `Person`.
- `ID` là kiểu identifier được khai báo ở generic thứ hai của repository, ví dụ `Long`.
- Kết quả là `Optional<T>` để biểu diễn việc có hoặc không có entity với ID đó.

Ví dụ:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Có thể gọi từ service hoặc code Java thông thường:

~~~java
Optional<Person> result = personRepository.findById(42L);

result.ifPresent(person -> {
    System.out.println(person.getFirstName());
});
~~~

Hoặc xử lý trường hợp không tìm thấy:

~~~java
Person person = personRepository.findById(42L)
    .orElseThrow(() -> new PersonNotFoundException(42L));
~~~

Spring Data REST thực hiện việc tra cứu item cho HTTP GET. Không cần tự viết một Controller chỉ để gọi `findById` nếu endpoint item mặc định của repository đã đáp ứng nhu cầu.

### 3.1. findById là phương thức dành riêng cho identifier

Tên `findById` là một phương thức CRUD dành riêng của repository: tham số của nó là identifier thật sự của entity, theo khai báo `@Id`. Nó không đơn thuần là một query method được suy ra từ tên thuộc tính bất kỳ có tên `id`.

Ví dụ entity có khóa chính tên `personKey` nhưng đồng thời có một thuộc tính nghiệp vụ tên `id`:

~~~java
@Entity
public class Person {

    @Id
    private Long personKey;

    private String id;
    private String name;
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    Optional<Person> findPersonById(String id);
}
~~~

Hai phương thức có ý nghĩa khác nhau:

- `findById(Long id)` là phương thức CRUD dành riêng, tìm theo khóa chính `personKey`.
- `findPersonById(String id)` là query method được phân tích theo tên thuộc tính, tìm theo thuộc tính nghiệp vụ `id`.

Phần tên mô tả `Person` nằm giữa `find` và `By` giúp tránh đụng tên với phương thức CRUD dành riêng. Khi đọc hoặc thiết kế repository, hãy kiểm tra trường được gắn `@Id` thay vì suy luận khóa chính chỉ từ tên field.

### 3.2. Kiểu ID phải khớp với repository

Kiểu ID được khai báo ở generic repository:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {
}
~~~

Với repository này, Spring Data REST cần chuyển segment ID trên URL sang `UUID`. Một request có thể có dạng:

~~~http
GET /orders/9f7c2a8e-3d2a-4a6c-9f1e-7c9b6a1d1234
~~~

Không nên khai báo repository với ID là `Long` nếu entity thực tế dùng `UUID`, hoặc viết service gọi `findById` bằng một kiểu không tương thích. Nếu dùng kiểu ID tùy chỉnh, cần có converter phù hợp để Spring chuyển giá trị URL sang kiểu Java đó.

## 4. Request và response khi tìm thấy tài nguyên

Giả sử database có Person với ID 42:

~~~http
GET /people/42
Accept: application/hal+json
~~~

Response thành công thường có status `200 OK` và representation HAL JSON, ví dụ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
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

Các trường thực tế phụ thuộc entity, Jackson configuration, projection và các association được export. Phần `_links.self` cho client biết URI chuẩn của item. Representation HAL có thể cung cấp thêm các liên kết association để client điều hướng đến tài nguyên liên quan.

Client có thể gửi `Accept: application/hal+json` để yêu cầu định dạng HAL JSON. Nếu client yêu cầu media type không được endpoint hỗ trợ, server có thể trả lỗi không hỗ trợ định dạng.

## 5. Khi ID không tồn tại hoặc sai định dạng

Hai tình huống cần phân biệt:

### 5.1. ID hợp lệ nhưng không có entity

Ví dụ ID là một số hợp lệ nhưng database không có Person tương ứng:

~~~http
GET /people/999999
Accept: application/hal+json
~~~

Repository trả về `Optional.empty()`. Spring Data REST xử lý item không tồn tại và thường trả về:

~~~http
HTTP/1.1 404 Not Found
~~~

Đây là kết quả bình thường của truy vấn không tìm thấy. Không nên trả về HTTP 200 với một object rỗng nếu URI được yêu cầu đại diện cho một item cụ thể không tồn tại.

### 5.2. ID không chuyển đổi được sang kiểu identifier

Với repository có ID kiểu `Long`, request sau không chứa ID hợp lệ:

~~~http
GET /people/abc
~~~

Spring không thể chuyển chuỗi `abc` thành `Long`. Lỗi xảy ra trước khi repository có thể tra cứu entity; request thường trả về HTTP 400 Bad Request.

Nếu ID là `UUID`, một chuỗi không đúng định dạng UUID cũng gặp lỗi conversion tương tự. Khi debug, hãy xác định lỗi xảy ra ở bước chuyển đổi path hay ở bước truy vấn repository.

## 6. Phân biệt findById với các thao tác đọc khác

| Phương thức hoặc request | Mục đích | Kết quả |
|---|---|---|
| `GET /people` | Đọc collection | Nhiều entity, có thể phân trang |
| `GET /people/42` | Đọc một item theo ID | Một resource hoặc 404 |
| `findById(42L)` | Repository lookup theo identifier | `Optional<Person>` |
| `findAll()` | Repository lookup toàn bộ entity | `Iterable<Person>` |
| `findByLastName("Nguyen")` | Query method theo thuộc tính | Các entity phù hợp điều kiện |

`findById` là lookup theo khóa chính. Nếu cần tìm theo email, tên, mã nghiệp vụ hoặc điều kiện kết hợp, hãy khai báo query method hoặc custom query phù hợp thay vì cố dùng `findById`.

Ví dụ:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    Optional<Person> findByEmail(String email);

    List<Person> findByLastNameOrderByFirstNameAsc(String lastName);
}
~~~

Nếu query method được Spring Data REST export, nó thường xuất hiện dưới đường dẫn `/people/search/**`. Đó là search resource riêng, không phải item resource `/people/{id}`.

## 7. Projection và representation của item

Entity được tìm thấy có thể được biểu diễn qua projection nếu ứng dụng đã khai báo projection và đăng ký nó cho repository. Client có thể yêu cầu projection bằng query parameter:

~~~http
GET /people/42?projection=personSummary
Accept: application/hal+json
~~~

Ví dụ projection:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Projection thay đổi các thuộc tính được đưa vào representation; nó không thay đổi ý nghĩa của lookup theo ID. Server vẫn tìm cùng item 42, sau đó tạo representation theo projection được yêu cầu. Nếu projection không được đăng ký hoặc tên projection không hợp lệ, client không nên giả định response sẽ chứa đúng tập trường mong muốn.

## 8. Tùy chỉnh cách tìm item

Thông thường, hãy giữ `findById` mặc định cho item resource. Nếu domain cần một URI khác để tra cứu bằng business key, có thể tạo query method riêng và export nó thành search resource:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-employee-code", rel = "by-employee-code")
    Optional<Person> findByEmployeeCode(
        @Param("code") String employeeCode);
}
~~~

Client gọi:

~~~http
GET /people/search/by-employee-code?code=EMP-0042
~~~

Cách này giữ ý nghĩa rõ ràng:

- `/people/42` tra cứu theo identifier của resource.
- `/people/search/by-employee-code?code=EMP-0042` tra cứu theo business key.

Nếu muốn URI item chính nó dùng business key thay cho khóa chính, cần cấu hình entity lookup strategy phù hợp với phiên bản Spring Data REST và bảo đảm định danh, link HAL, converter cùng repository lookup nhất quán. Đây là thay đổi ở chiến lược định tuyến/lookup; không nên chỉ đổi tên biến path hoặc viết một query method `findById` rồi kỳ vọng endpoint mặc định tự hiểu business key.

## 9. Kiểm thử GET item

Có thể dùng MockMvc để kiểm tra endpoint item. Ví dụ dưới đây là khung kiểm thử tích hợp; cần bổ sung cấu hình repository và dữ liệu test theo ứng dụng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonItemResourceTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getExistingPersonReturnsHalResource() throws Exception {
        mvc.perform(get("/people/42")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.firstName").value("An"))
            .andExpect(jsonPath("$._links.self.href")
                .value(org.hamcrest.Matchers.endsWith("/people/42")));
    }

    @Test
    void getUnknownPersonReturnsNotFound() throws Exception {
        mvc.perform(get("/people/999999")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isNotFound());
    }

    @Test
    void invalidLongIdentifierReturnsBadRequest() throws Exception {
        mvc.perform(get("/people/abc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isBadRequest());
    }
}
~~~

Trong test thực tế:

- Tạo fixture có ID xác định hoặc lấy URI từ response POST thay vì phụ thuộc ID tự sinh.
- Dùng database test hoặc repository mock phù hợp với loại test.
- Kiểm tra cả status và nội dung/link cần thiết.
- Xác nhận request với ID sai định dạng và ID không tồn tại đi qua hai nhánh lỗi khác nhau.
- Nếu bật projection, kiểm thử representation với và không có query parameter projection.

## 10. Lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể gặp | Cách kiểm tra |
|---|---|---|
| GET item trả 404 | ID không có trong repository hoặc path không đúng | Kiểm tra ID, collection path và base path |
| GET item trả 400 | Path ID không chuyển đổi được sang kiểu ID | Kiểm tra generic ID và định dạng URL |
| findById tìm nhầm field | Nhầm identifier với thuộc tính có tên `id` | Kiểm tra `@Id` và reserved method semantics |
| Repository khai báo sai generic ID | Kiểu ID không khớp entity | Kiểm tra `JpaRepository<Person, Long>` và kiểu `@Id` |
| Response thiếu field mong đợi | Projection, Jackson visibility hoặc cấu hình serialization | Kiểm tra projection và representation |
| Client không điều hướng được đến item | URI self hoặc base path không đúng | Kiểm tra `_links.self.href` và base path |
| Muốn tìm theo mã nghiệp vụ nhưng dùng findById | Business key không phải identifier | Tạo query method riêng hoặc cấu hình entity lookup phù hợp |

## 11. Checklist khi dùng GET tài nguyên đơn

- Xác định đúng collection path mà repository export.
- Kiểm tra base path của Spring Data REST.
- Kiểm tra kiểu ID ở generic của repository và thuộc tính `@Id`.
- Gửi identifier đúng định dạng trong path.
- Dùng `findById` cho khóa chính; dùng query method riêng cho business key.
- Xử lý `Optional.empty()` như trường hợp không tìm thấy khi viết service.
- Kiểm tra status 200, 404 và 400 theo từng tình huống.
- Đọc `_links.self` để dùng URI tài nguyên do server cung cấp.
- Nếu dùng projection, kiểm tra tên projection và representation trả về.

## Kết luận

`GET /people/{id}` đọc một item theo identifier của repository. Spring Data REST lấy ID từ path, chuyển sang kiểu Java và gọi thao tác lookup tương ứng, thường là `findById(ID)`. `findById` là phương thức CRUD dành riêng cho khóa chính; nếu cần tìm theo thuộc tính nghiệp vụ có tên `id` hoặc theo mã khác, hãy dùng query method có tên tránh xung đột. ID hợp lệ nhưng không tồn tại thường trả 404, còn ID sai định dạng thường trả 400. Representation cuối cùng có thể là HAL JSON và chịu ảnh hưởng của projection cùng cấu hình serialization.

## Tài liệu tham khảo

- Spring Data Commons – CrudRepository API: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html
- Spring Data REST – Repository resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST – Projections and excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
- Spring Data JPA – Query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
