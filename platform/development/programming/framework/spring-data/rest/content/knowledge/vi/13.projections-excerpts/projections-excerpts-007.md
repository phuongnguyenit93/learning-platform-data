# Excerpt projection và cấu hình excerptProjection trên repository trong Spring Data REST

## Mục tiêu

Spring Data REST mặc định biểu diễn domain object theo các thuộc tính mà framework có thể xuất. Khi một client đọc collection lớn, việc nhúng toàn bộ thông tin của mỗi entity có thể làm response nặng; nhưng chỉ trả các link association cũng có thể buộc client gửi thêm nhiều request để lấy dữ liệu thường xuyên sử dụng.

**Projection** cho phép định nghĩa một góc nhìn (view) của entity. **Excerpt** là một projection được áp dụng tự động khi Spring Data REST nhúng item resources vào collection hoặc related resources. Có thể chọn excerpt mặc định cho một repository bằng thuộc tính `excerptProjection` của `@RepositoryRestResource`.

Bài này trình bày cách định nghĩa projection interface, cách đăng ký và gọi projection tường minh, cách cấu hình excerpt mặc định, sự khác nhau giữa collection và item resource, cách nhúng dữ liệu quan hệ, và các lưu ý về tương thích API cũng như bảo mật.

## 1. Projection là gì?

Giả sử ứng dụng có entity Person:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    @OneToOne
    private Address address;

    // constructors, getters and setters
}
~~~

Khi xuất qua Spring Data REST, representation mặc định có thể chứa các thuộc tính firstName, lastName và liên kết tới address. Nếu Address cũng có repository riêng, association thường được biểu diễn bằng một link:

~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/1"
    },
    "address": {
      "href": "http://localhost:8080/api/people/1/address"
    }
  }
}
~~~

Nếu client chỉ cần tên, có thể định nghĩa projection chỉ chứa hai getter:

~~~java
@Projection(name = "nameOnly", types = Person.class)
public interface PersonNameOnly {

    String getFirstName();

    String getLastName();
}
~~~

Projection là Java interface được đánh dấu bằng `@Projection`. Thuộc tính `name` là tên công khai client dùng trong query parameter `projection`; nó không phải tên interface. Thuộc tính `types` chỉ định domain type mà projection áp dụng.

Với projection trên, response chỉ hiển thị các thuộc tính được khai báo trong interface cùng các link do Spring Data REST cung cấp. Entity và schema database không bị thay đổi.

## 2. Đăng ký projection để client lựa chọn

Spring Data REST tự phát hiện projection interface nếu nó được đánh dấu `@Projection` và đặt trong cùng package với domain type hoặc một sub-package của package đó.

Ví dụ cấu trúc package:

~~~text
com.example.people
  Person.java
  Address.java
  PersonRepository.java
  projection
    PersonNameOnly.java
    PersonWithAddress.java
~~~

Nếu projection nằm ngoài phạm vi package được phát hiện, có thể đăng ký thủ công qua `RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)`:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getProjectionConfiguration()
                .addProjection(PersonNameOnly.class);
    }
}
~~~

Các import chính:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
~~~

Projection phải được đăng ký để Spring Data REST công bố nó cho client. Nếu interface không có `@Projection` hoặc không được scan/đăng ký, tên projection có thể không xuất hiện trong metadata và request với tên đó không được áp dụng như mong đợi.

## 3. Gọi projection tường minh bằng query parameter

Sau khi projection được phát hiện, client có thể chọn projection bằng query parameter `projection`.

Ví dụ:

~~~http
GET /api/people/1?projection=nameOnly
Accept: application/hal+json
~~~

Tên `nameOnly` lấy từ `@Projection(name = "nameOnly", ...)`. Client không dùng tên `PersonNameOnly` trừ khi đó cũng chính là giá trị annotation.

Một response rút gọn có thể như sau:

~~~json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/1{?projection}",
      "templated": true
    },
    "address": {
      "href": "http://localhost:8080/api/people/1/address"
    }
  }
}
~~~

Link self có thể là URI template để client tiếp tục lựa chọn projection. Projection chỉ ảnh hưởng cách dữ liệu được trình bày; các link điều hướng vẫn có thể được giữ lại để client truy cập tài nguyên liên quan.

Có thể khai báo nhiều projection cho cùng một domain type, ví dụ `nameOnly`, `withAddress` và `details`. Client chọn góc nhìn phù hợp theo mục đích của màn hình hoặc use case.

## 4. Excerpt là projection mặc định cho item được nhúng

Một excerpt là projection được Spring Data REST tự động áp dụng khi item resource được nhúng vào collection resource hoặc related resource.

Ví dụ, repository có thể cấu hình excerpt:

~~~java
@RepositoryRestResource(
        path = "people",
        excerptProjection = PersonNameOnly.class
)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

Khi client gọi collection:

~~~http
GET /api/people
Accept: application/hal+json
~~~

các item trong `_embedded.people` được biểu diễn theo `PersonNameOnly`. Response minh họa:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "Frodo",
        "lastName": "Baggins",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people"
    }
  }
}
~~~

Thuộc tính `excerptProjection` nhận class của projection interface. Nó chỉ định góc nhìn mặc định dùng khi Spring Data REST nhúng item resources của repository vào collection và related resources. Nó không đổi entity hay cách repository truy vấn dữ liệu.

## 5. Excerpt không tự động áp dụng cho item resource đơn

Đây là khác biệt quan trọng nhất giữa excerpt và projection được chọn tường minh.

| Request | Cách áp dụng |
| --- | --- |
| `GET /api/people` | Excerpt được áp dụng cho các Person được nhúng trong collection. |
| `GET /api/people/1` | Item resource đơn dùng representation mặc định, không tự động dùng excerpt. |
| `GET /api/people/1?projection=nameOnly` | Projection được chọn tường minh cho item. |
| Related collection có nhúng Person | Excerpt của repository Person được dùng cho các item Person được nhúng. |

Excerpt được thiết kế làm preview mặc định cho collection, không phải representation mặc định của một item khi client đọc trực tiếp item đó. Item resource thường cần representation đầy đủ hơn để client có đủ thông tin khi đọc hoặc cập nhật.

Nếu muốn item resource dùng projection, client phải yêu cầu bằng query parameter `projection`. Đừng kỳ vọng cấu hình `excerptProjection` tự động làm thay đổi mọi request GET item.

## 6. Nhúng dữ liệu quan hệ bằng excerpt projection

Một trường hợp thường gặp là Person có Address. Nếu Address được xuất thành repository riêng, representation mặc định có thể chỉ cung cấp association link. Nếu collection Person thường xuyên cần hiển thị địa chỉ, excerpt có thể đưa dữ liệu Address vào ngay trong item được nhúng.

Định nghĩa projection:

~~~java
@Projection(name = "inlineAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    String getLastName();

    Address getAddress();
}
~~~

Cấu hình repository:

~~~java
@RepositoryRestResource(
        path = "people",
        excerptProjection = PersonWithAddress.class
)
public interface PersonRepository
        extends CrudRepository<Person, Long> {
}
~~~

Khi gọi collection, response có thể chứa address inline:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "Frodo",
        "lastName": "Baggins",
        "address": {
          "street": "Bag End",
          "state": "The Shire",
          "country": "Middle Earth"
        },
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/1"
          },
          "address": {
            "href": "http://localhost:8080/api/people/1/address"
          }
        }
      }
    ]
  }
}
~~~

Dữ liệu Address được nhúng để client đọc thuận tiện, nhưng link association vẫn có thể được cung cấp để client điều hướng tới tài nguyên Address riêng. Excerpt không biến association thành một entity khác và không loại bỏ endpoint association.

Việc nhúng object quan hệ có thể làm response lớn hơn. Chỉ nên đưa vào excerpt những dữ liệu thường xuyên cần ở màn hình danh sách; tránh tạo một đồ thị object sâu hoặc tải nhiều collection lồng nhau.

## 7. Projection có thể tạo thuộc tính tính toán

Projection interface không chỉ chọn getter có sẵn. Có thể tạo một thuộc tính chỉ đọc bằng Spring `@Value` và SpEL:

~~~java
@Projection(name = "personCard", types = Person.class)
public interface PersonCard {

    String getFirstName();

    String getLastName();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
~~~

Trong ví dụ, `getFullName()` không cần field `fullName` trong entity. Spring đánh giá biểu thức trên target object và trả về giá trị tổng hợp trong representation.

Projection cũng có thể khai báo getter trả về một nested projection interface để giới hạn góc nhìn của object quan hệ:

~~~java
@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {

    String getCity();

    String getCountry();
}

@Projection(name = "personCardWithAddress", types = Person.class)
public interface PersonCardWithAddress {

    String getFirstName();

    String getLastName();

    AddressSummary getAddress();
}
~~~

Nested projection giúp kiểm soát mức dữ liệu được nhúng thay vì xuất toàn bộ thuộc tính của object liên quan. Các projection nested cũng phải được phát hiện hoặc đăng ký phù hợp.

## 8. Projection có thể làm lộ dữ liệu bị ẩn

Projection là một ranh giới serialization, không phải cơ chế phân quyền hay bộ lọc bảo mật tự động.

Spring Data REST mặc định tôn trọng Jackson `@JsonIgnore` khi serialize entity. Tuy nhiên, một projection có thể khai báo getter cho thuộc tính mà entity đã đánh dấu `@JsonIgnore`, khiến thuộc tính đó vẫn xuất hiện khi projection được dùng.

Ví dụ không an toàn:

~~~java
@Entity
public class User {

    @Id
    private Long id;

    private String username;

    @JsonIgnore
    private String password;
}
~~~

Một projection vô tình thêm getter:

~~~java
@Projection(name = "userDetails", types = User.class)
public interface UserDetailsProjection {

    String getUsername();

    String getPassword();
}
~~~

Nếu client có thể chọn projection này, trường password có nguy cơ bị đưa vào response. Spring Data REST không thể tự biết thuộc tính nào nhạy cảm về nghiệp vụ; nhóm phát triển phải kiểm soát các projection được công bố.

Nguyên tắc an toàn:

1. Không tạo projection công khai có getter cho password, token, secret, credential hoặc dữ liệu nội bộ.
2. Kiểm tra từng getter và nested projection trước khi đăng ký.
3. Không dùng projection thay cho authorization; quyền đọc vẫn phải được kiểm tra ở tầng security/service.
4. Không cho rằng `@JsonIgnore` bảo vệ tuyệt đối nếu một projection khác chủ động expose thuộc tính đó.
5. Dùng DTO/controller riêng nếu cần một response có allowlist rõ ràng cho dữ liệu nhạy cảm.

## 9. Excerpt và thay đổi hợp đồng API

Cấu hình `@RepositoryRestResource(excerptProjection = ...)` thay đổi representation mặc định của các item khi chúng được nhúng trong collection hoặc related resources. Nếu API đã được client sử dụng, việc thêm excerpt có thể là thay đổi breaking đối với client đang dựa vào các field trước đây xuất hiện trong embedded item.

Ví dụ trước khi cấu hình, embedded Person có thể chứa `firstName`, `lastName`, `birthDate` và `address`. Sau khi cấu hình excerpt chỉ có firstName và lastName, client đọc `birthDate` từ collection response có thể không còn thấy field đó.

Trước khi phát hành:

- Liệt kê các client đang tiêu thụ collection và related resources.
- So sánh response HAL trước và sau excerpt.
- Xác nhận các field bị loại khỏi preview vẫn có thể đọc từ item resource nếu client cần.
- Cân nhắc versioning hoặc lộ trình chuyển đổi nếu contract đã được công bố.
- Kiểm tra cả projection parameter và các link association.

Projection/excerpt chủ yếu phục vụ representation đọc. Không nên thiết kế form cập nhật dựa trên excerpt vì nó có thể không chứa đầy đủ thuộc tính cần thiết cho một thao tác thay thế hoặc cập nhật.

## 10. Kiểm tra projection đã được phát hiện

Spring Data REST công bố metadata ALPS thông qua link `profile` ở API root. Theo link profile của domain resource, client có thể xem các projection khả dụng và mô tả các thuộc tính mà projection cung cấp.

Quy trình kiểm tra:

1. Gọi API root và lấy link `profile`.
2. Theo link ALPS cho domain resource, ví dụ `/api/alps/people`.
3. Tìm descriptor `projection` và các projection name được công bố.
4. Xác nhận tên trong descriptor khớp với `@Projection(name = "...")`.
5. Gọi item resource với query parameter projection để xác nhận representation.

Nếu projection được đăng ký thủ công, kiểm tra cấu hình Spring context và đảm bảo configurer bean thực sự được nạp.

## 11. Kiểm thử bằng MockMvc

Có thể kiểm thử excerpt trên collection và projection tường minh trên item riêng biệt.

Kiểm tra collection dùng excerpt:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonProjectionTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void collectionUsesConfiguredExcerpt() throws Exception {
        mockMvc.perform(get("/api/people")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._embedded.people[0].firstName")
                    .exists())
            .andExpect(jsonPath("$._embedded.people[0].lastName")
                    .exists());
    }
}
~~~

Kiểm tra item resource với projection tường minh:

~~~java
mockMvc.perform(get("/api/people/{id}", 1)
        .param("projection", "nameOnly")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.firstName").exists())
    .andExpect(jsonPath("$.lastName").exists());
~~~

Kiểm tra item không tự động nhận excerpt bằng cách xác nhận một field chỉ có trong representation mặc định vẫn xuất hiện (nếu entity và test fixture có field đó). Không nên chỉ kiểm tra status 200; hãy kiểm tra chính xác các field và link trong JSON.

Với excerpt có nested Address, kiểm tra cả object inline và association link:

~~~java
mockMvc.perform(get("/api/people")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.people[0].address.city")
            .exists())
    .andExpect(jsonPath("$._embedded.people[0]._links.address.href")
            .exists());
~~~

Các test cần fixture có dữ liệu ổn định và chạy trên phiên bản Spring Data REST thực tế của dự án. Điều chỉnh tên collection relation, base path và projection name theo cấu hình ứng dụng.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Projection không xuất hiện trong ALPS | Interface thiếu @Projection hoặc nằm ngoài package được scan | Đặt trong package domain/sub-package hoặc đăng ký thủ công |
| Query projection không có tác dụng | Dùng tên interface thay vì annotation name hoặc projection chưa được đăng ký | Kiểm tra giá trị @Projection(name = ...) và ALPS descriptor |
| Collection vẫn trả representation mặc định | Repository chưa cấu hình excerptProjection hoặc cấu hình nhầm class | Kiểm tra @RepositoryRestResource trên đúng repository |
| GET item không dùng excerpt | Excerpt không tự áp dụng cho single resource | Gửi ?projection=tenProjection |
| Address vẫn chỉ là link | Projection không khai báo getter Address hoặc nested projection chưa được áp dụng | Thêm getter quan hệ vào excerpt và kiểm tra serialization |
| Collection response quá lớn | Excerpt nhúng quá nhiều dữ liệu quan hệ | Giảm số getter/nested projection hoặc chỉ nhúng field cần thiết |
| Dữ liệu bị lộ dù có @JsonIgnore | Projection khai báo getter cho thuộc tính bị ẩn | Loại bỏ getter nhạy cảm và kiểm tra toàn bộ projection |
| Client cũ lỗi sau khi thêm excerpt | Embedded representation đã thay đổi | Đánh giá compatibility và cập nhật contract/client |

## 13. Khi nào nên dùng projection, excerpt hay DTO?

| Giải pháp | Dùng khi | Đặc điểm |
| --- | --- | --- |
| Projection tường minh | Client cần chọn nhiều góc nhìn trên cùng entity | Chọn qua query parameter projection |
| Excerpt projection | Collection cần một preview mặc định nhất quán | Tự áp dụng khi item được nhúng |
| Nested projection | Cần giới hạn dữ liệu của object liên quan | Điều khiển representation sâu hơn |
| DTO/custom controller | Cần contract độc lập, logic nghiệp vụ hoặc allowlist dữ liệu rõ ràng | Chủ động kiểm soát response và authorization |

Nếu chỉ muốn giảm payload collection và vẫn giữ item endpoint đầy đủ, excerpt là lựa chọn tự nhiên. Nếu client cần nhiều representation tùy ngữ cảnh, dùng projection tường minh. Nếu response cần tính toán nghiệp vụ phức tạp hoặc kiểm soát field nhạy cảm chặt chẽ, DTO/custom controller thường dễ quản lý hơn.

## Tài liệu tham khảo

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): cách định nghĩa projection, đăng ký, gọi projection, excerpt mặc định và nhúng dữ liệu quan hệ.
- [Spring Data REST 5.1.2 API — RepositoryRestResource](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html): thuộc tính excerptProjection dùng khi nhúng item resources vào collection và related resources.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): cấu trúc collection/item resources và hypermedia links.
