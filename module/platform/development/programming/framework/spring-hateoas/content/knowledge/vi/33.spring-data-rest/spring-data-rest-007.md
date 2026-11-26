# Excerpt projection

Spring Data REST có thể xuất một entity thành representation chứa nhiều thuộc tính hơn mức client cần trong một màn hình danh sách. Ví dụ, entity `Person` có tên, email, số điện thoại, địa chỉ và thông tin nội bộ; collection endpoint chỉ cần tên cùng thành phố để hiển thị danh sách. **Projection** cho phép định nghĩa một góc nhìn của entity bằng interface, còn **excerpt projection** là projection được áp dụng mặc định cho các item nhúng trong collection resource.

Spring Data REST dùng `@Projection` để đặt tên cho góc nhìn và `excerptProjection` trên `@RepositoryRestResource` để chọn projection mặc định cho collection của repository. Client vẫn có thể yêu cầu một projection cụ thể bằng query parameter `projection` nếu projection đó đã được đăng ký và được công bố.

Bài học này thuộc chương **Spring Data REST** trong module **SPRING_HATEOAS**, tập trung vào cách định nghĩa excerpt projection, áp dụng cho collection resource, yêu cầu projection cho item resource, lồng projection, tạo thuộc tính tính toán và hiểu giới hạn về hiệu năng, ghi dữ liệu và bảo mật.

Sau bài học, bạn có thể:

- Giải thích projection và excerpt projection trong Spring Data REST.
- Tạo interface projection bằng `@Projection`.
- Cấu hình `excerptProjection` trên repository.
- Phân biệt hành vi của collection resource và item resource.
- Yêu cầu projection tường minh bằng query parameter `projection`.
- Tạo nested projection và thuộc tính tính toán bằng SpEL.
- Đăng ký projection để Spring Data REST phát hiện.
- Đánh giá tác động của projection tới payload, truy vấn, bảo mật và hợp đồng API.
- Kiểm thử projection bằng MockMvc.

## 1. Projection giải quyết vấn đề gì?

Một entity thường chứa dữ liệu phục vụ nhiều use case. Nếu collection endpoint trả toàn bộ thuộc tính của entity, response có thể lớn và làm lộ dữ liệu mà màn hình danh sách không cần. Ngược lại, nếu tạo DTO riêng cho mọi màn hình, ứng dụng phải duy trì nhiều kiểu dữ liệu và endpoint mapping.

Projection định nghĩa một tập thuộc tính mà client cần nhìn thấy. Spring Data REST tạo projection từ interface getter, rồi dùng projection đó để biểu diễn entity trong response.

Ví dụ entity `Person`:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phoneNumber;
    private String city;
    private String internalNote;

    protected Person() {
    }

    // Constructors, getters and setters.
}
```

Màn hình danh sách chỉ cần `firstName`, `lastName` và `city`. Projection giúp công bố đúng góc nhìn đó mà không cần thay đổi entity gốc:

```java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();

    String getCity();
}
```

Projection là interface, không phải entity mới và không tạo bảng database mới. Spring Data REST tạo projection proxy để đọc các thuộc tính từ entity nguồn.

## 2. Khai báo excerptProjection trên repository

Để áp dụng projection làm mặc định cho các item trong collection resource, khai báo `excerptProjection` trên `@RepositoryRestResource`:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
```

Với cấu hình này, collection resource được xuất tại `/people`. Khi client gọi collection endpoint, các item nhúng trong `_embedded.people` sử dụng `PersonExcerpt` làm representation mặc định.

Ví dụ request:

```http
GET /people
Accept: application/hal+json
```

Response rút gọn có dạng:

```json
{
  "_embedded": {
    "people": [
      {
        "firstName": "Lan",
        "lastName": "Nguyen",
        "city": "Ho Chi Minh City",
        "_links": {
          "self": { "href": "http://localhost:8080/people/1" }
        }
      }
    ]
  },
  "_links": {
    "self": { "href": "http://localhost:8080/people" },
    "profile": { "href": "http://localhost:8080/profile/people" }
  }
}
```

Response minh họa phần content của item chỉ có các thuộc tính do projection khai báo. Các link hypermedia vẫn được Spring Data REST tạo theo repository và resource mapping.

## 3. Excerpt projection chỉ là mặc định cho collection resource

Một điểm quan trọng là `excerptProjection` không tự động thay representation của item resource. Collection resource và item resource là hai dạng tài nguyên khác nhau:

| Request | Hành vi mặc định |
|---|---|
| `GET /people` | Các item trong `_embedded.people` dùng excerpt projection đã cấu hình. |
| `GET /people/1` | Item resource dùng representation mặc định của entity, trừ khi client yêu cầu projection cụ thể. |
| `GET /people/1?projection=personExcerpt` | Item resource dùng projection có tên `personExcerpt`, nếu projection được phát hiện/đăng ký. |

Sự khác biệt này cho phép collection trả representation gọn để hiển thị danh sách, trong khi item resource vẫn có thể cung cấp góc nhìn chi tiết hơn. Nếu muốn item resource cũng dùng một projection, client phải yêu cầu projection tương ứng hoặc ứng dụng phải thiết kế hợp đồng riêng.

Không nên cho rằng `excerptProjection` là cấu hình che giấu thuộc tính trên toàn bộ API. Nó không tự động thay đổi mọi representation, association resource hay endpoint tùy chỉnh.

## 4. Yêu cầu projection tường minh bằng query parameter

Spring Data REST cho phép client chọn projection đã đăng ký bằng query parameter `projection`:

```http
GET /people/1?projection=personExcerpt
Accept: application/hal+json
```

Giá trị của query parameter là `name` trong `@Projection`, không phải tên interface Java. Ví dụ:

```java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {
    String getFirstName();
    String getLastName();
    String getCity();
}
```

Client phải gửi `projection=personExcerpt`. Gửi `projection=PersonExcerpt` sẽ không đúng nếu tên projection đã khai báo là `personExcerpt`.

Có thể định nghĩa nhiều projection cho cùng entity để phục vụ các nhu cầu khác nhau:

```java
@Projection(name = "personContact", types = Person.class)
public interface PersonContact {

    String getFirstName();

    String getLastName();

    String getEmail();

    String getPhoneNumber();
}
```

Khi đó client có thể yêu cầu `?projection=personContact` cho một góc nhìn liên hệ. Các projection cần có tên duy nhất trong phạm vi được phát hiện để client không phải đoán projection nào sẽ được chọn.

## 5. Spring Data REST phát hiện projection ở đâu?

Spring Data REST tự phát hiện các interface projection có `@Projection` trong package của repository và các package con. Để cách phát hiện mặc định hoạt động dễ dự đoán, đặt projection gần repository quản lý entity tương ứng.

Ví dụ cấu trúc package:

```text
com.example.people
├── Person.java
├── PersonRepository.java
├── PersonExcerpt.java
└── PersonContact.java
```

Nếu projection nằm ngoài package được quét, nó có thể không xuất hiện trong danh sách projection được hỗ trợ và query parameter `projection` không phân giải được tên đó. Khi cần tổ chức projection ở package riêng, hãy đăng ký rõ ràng bằng `RepositoryRestConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
class RestRepositoryConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getProjectionConfiguration()
                .addProjection(PersonExcerpt.class);
        config.getProjectionConfiguration()
                .addProjection(PersonContact.class);
    }
}
```

Ví dụ đăng ký tường minh hữu ích khi projection không nằm trong package mặc định được phát hiện. Nếu projection đã được tự động phát hiện, không cần đăng ký lại chỉ để làm cho nó hoạt động.

## 6. Thêm thuộc tính tính toán bằng SpEL

Projection không chỉ expose trực tiếp getter của entity. Có thể dùng `@Value` với SpEL để tạo một thuộc tính tính toán:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();

    String getCity();

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

`target` đại diện cho đối tượng nguồn. Getter `getDisplayName()` không yêu cầu entity có field `displayName`; giá trị được tính từ `firstName` và `lastName`.

Đây là phiên bản mở rộng của `PersonExcerpt` ở mục 1: thêm getter `getDisplayName()` vào cùng interface, không tạo thêm một interface trùng tên trong dự án.

Ví dụ JSON:

```json
{
  "firstName": "Lan",
  "lastName": "Nguyen",
  "city": "Ho Chi Minh City",
  "displayName": "Lan Nguyen"
}
```

SpEL phù hợp cho phép tính đơn giản phục vụ representation. Không nên đặt truy vấn nặng, gọi dịch vụ từ xa hoặc quy tắc nghiệp vụ phức tạp trong biểu thức projection. Những logic đó nên nằm trong service hoặc một lớp trình bày riêng có thể kiểm thử rõ ràng.

## 7. Nested projection cho thuộc tính liên kết

Entity có thể chứa association tới entity khác. Projection có thể khai báo getter trả về một projection khác để giới hạn dữ liệu của quan hệ lồng nhau.

Ví dụ entity `Address`:

```java
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {

    private String street;
    private String city;
    private String postalCode;

    // Getters and setters.
}
```

Projection cho địa chỉ:

```java
public interface AddressExcerpt {

    String getCity();

    String getPostalCode();
}
```

Projection người dùng có thể trả về nested projection:

```java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    String getLastName();

    AddressExcerpt getAddress();
}
```

Ví dụ này giả định `Person` có thuộc tính `address` tương ứng kiểu `Address`. `AddressExcerpt` là nested projection interface được tham chiếu từ projection ngoài; không cần đăng ký nó như một projection độc lập nếu chỉ dùng cho getter lồng nhau. Nested projection giúp representation chỉ công bố `city` và `postalCode` của địa chỉ thay vì toàn bộ thuộc tính.

Với association tới entity khác, có thể dùng projection interface cho kiểu đích tương tự. Cần cân nhắc lazy loading và số lượng association được truy cập; nested projection sâu hoặc lặp qua collection lớn có thể khiến response tốn nhiều truy vấn và payload hơn dự kiến.

## 8. Projection cho collection và association

Projection có thể khai báo getter trả về collection hoặc kiểu lồng nhau. Ví dụ một người có nhiều đơn hàng:

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personOrders", types = Person.class)
public interface PersonOrders {

    String getFirstName();

    List<OrderExcerpt> getOrders();
}

@Projection(name = "orderExcerpt", types = Order.class)
public interface OrderExcerpt {

    Long getId();

    String getStatus();

    BigDecimal getTotal();
}
```

Đoạn code giả định `Person` có thuộc tính `orders` kiểu collection của `Order`. Khi serialize, projection có thể biểu diễn các phần tử theo `OrderExcerpt`.

Không nên đưa một collection không giới hạn vào excerpt projection của mọi item trong một collection resource. Ví dụ `/people` có 100 người, mỗi người lại nhúng hàng trăm đơn hàng sẽ tạo payload rất lớn và có thể phát sinh N+1 query. Nếu client chỉ cần biết có các đơn hàng liên quan, giữ association dưới dạng link thường hợp lý hơn; client có thể theo link khi cần.

## 9. Excerpt projection không phải DTO và không tự tối ưu SQL

Projection của Spring Data REST là cơ chế định hình representation. Nó không đồng nghĩa với việc repository chỉ select đúng các cột mà interface khai báo.

Với repository resource, Spring Data REST thường lấy entity từ repository rồi dùng projection để biểu diễn. Nếu getter truy cập association lazy, quá trình serialize có thể kích hoạt thêm truy vấn. Vì vậy, projection gọn hơn về JSON chưa chắc làm truy vấn database nhẹ hơn.

Phân biệt các cơ chế:

| Cơ chế | Mục đích | Tác động chính |
|---|---|---|
| Spring Data REST projection | Chọn góc nhìn khi serialize repository resource | Thay đổi representation trả về. |
| Spring Data interface/class projection trong repository query | Định nghĩa kiểu kết quả truy vấn | Có thể ảnh hưởng cách Spring Data tạo truy vấn và dữ liệu tải. |
| DTO mapping trong service/controller | Xây response theo hợp đồng do ứng dụng kiểm soát | Có thể kết hợp nhiều nguồn dữ liệu và quy tắc trình bày. |
| JPA entity graph/fetch plan | Điều khiển association cần tải | Tác động đến chiến lược fetch. |

Nếu mục tiêu là tối ưu số cột, số join hoặc số truy vấn, cần xem xét repository query, DTO projection, entity graph và fetch strategy. Không dùng `excerptProjection` như cam kết rằng SQL đã được tối ưu.

## 10. Excerpt projection không phải cơ chế phân quyền

Projection có thể làm một số field không xuất hiện trong một representation, nhưng client có thể yêu cầu projection khác nếu projection đó được công bố. Item resource cũng không tự động bị ràng buộc bởi excerpt projection.

Không dùng excerpt projection để bảo vệ dữ liệu nhạy cảm. Nếu `Person` có `internalNote`, `salary` hoặc thông tin cá nhân cần giới hạn, hãy áp dụng authorization, thiết kế API và chính sách serialization phù hợp. Cần bảo đảm mọi đường truy cập, bao gồm item resource, projection tùy chọn và association resource, đều tuân theo chính sách bảo mật.

Một projection có thể vô tình expose field nhạy cảm khi thêm getter mới. Hãy review projection như một phần của hợp đồng công khai, và kiểm thử các field không được phép xuất hiện.

## 11. Projection và cập nhật dữ liệu

Projection chủ yếu định hình cách đọc resource. Không nên coi projection là payload ghi dữ liệu hoặc kỳ vọng client có thể cập nhật entity bằng cách gửi lại JSON theo projection.

Nếu cần cập nhật, dùng các endpoint ghi do Spring Data REST xuất hoặc controller/service tùy chỉnh theo hợp đồng ứng dụng. Request ghi cần được validate và phân quyền riêng. Projection không thay thế DTO request, command object hoặc logic cập nhật domain.

Ví dụ: `PersonExcerpt` chỉ có tên và thành phố. Điều đó không có nghĩa `PUT /people/1` chỉ được phép cập nhật ba field này. Khả năng cập nhật phụ thuộc mapping entity, repository exposure, HTTP method được export và quy tắc ứng dụng.

## 12. Excerpt projection với repository nhiều kiểu representation

Một repository có thể công bố excerpt projection mặc định và vẫn cho phép các projection khác được chọn theo query parameter:

```java
@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
```

Các request minh họa:

```http
GET /people
Accept: application/hal+json
```

Collection dùng excerpt projection mặc định.

```http
GET /people/1?projection=personContact
Accept: application/hal+json
```

Item resource dùng projection `personContact` đã đăng ký.

```http
GET /people/1
Accept: application/hal+json
```

Item resource không tự động dùng excerpt projection chỉ vì repository đã khai báo `excerptProjection`.

Nếu client yêu cầu một projection không tồn tại hoặc chưa được đăng ký, Spring Data REST không thể phân giải projection name. Client nên dùng tên projection được công bố trong profile/API documentation, không tự suy ra tên từ class Java.

## 13. Kiểm thử excerpt projection bằng MockMvc

Kiểm thử cần xác nhận collection resource dùng projection mặc định và item resource chỉ dùng projection khi được yêu cầu tường minh.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class PersonExcerptProjectionTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void collectionUsesExcerptProjection() throws Exception {
        mockMvc.perform(get("/people").accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$._embedded.people[0].firstName").exists())
                .andExpect(jsonPath("$._embedded.people[0].city").exists())
                .andExpect(jsonPath("$._embedded.people[0].internalNote").doesNotExist());
    }

    @Test
    void itemUsesExplicitProjectionWhenRequested() throws Exception {
        mockMvc.perform(get("/people/1")
                        .param("projection", "personExcerpt")
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.firstName").exists())
                .andExpect(jsonPath("$.city").exists())
                .andExpect(jsonPath("$.internalNote").doesNotExist());
    }
}
```

Ví dụ giả định test fixture đã tạo ít nhất một `Person` có `internalNote`, repository được export dưới `/people`, và `PersonExcerpt` đã được phát hiện. JSONPath của collection phụ thuộc collection relation thực tế; nếu repository dùng path hoặc rel tùy chỉnh, điều chỉnh `_embedded.people` theo response của ứng dụng.

Nên bổ sung test cho projection khác, nested projection, computed property và các field nhạy cảm không được phép xuất hiện. Test cũng cần xác nhận item resource không projection có representation đúng như hợp đồng đã thiết kế.

## 14. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ excerpt projection áp dụng cho item resource | `GET /people/1` vẫn trả representation mặc định. | Dùng `?projection=personExcerpt` khi cần projection cho item. |
| Quên `excerptProjection` trên repository | Collection không dùng projection mong muốn làm mặc định. | Khai báo `excerptProjection = PersonExcerpt.class`. |
| Projection không được phát hiện | Query parameter projection không phân giải được tên. | Đặt trong package repository hoặc đăng ký qua `RepositoryRestConfigurer`. |
| Dùng tên class thay tên projection | Query parameter không khớp projection. | Dùng giá trị `name` trong `@Projection`. |
| Dùng projection để che giấu dữ liệu nhạy cảm | Endpoint khác hoặc projection khác vẫn có thể expose field. | Bảo vệ bằng authorization và thiết kế API. |
| Cho rằng projection tối ưu SQL | Có thể vẫn tải entity đầy đủ hoặc phát sinh lazy query. | Phân tích SQL, dùng query projection/fetch plan khi cần. |
| Nhúng collection lớn trong projection | Payload lớn và có nguy cơ N+1 query. | Dùng association link hoặc endpoint phân trang riêng. |
| Đặt logic nghiệp vụ phức tạp trong SpEL | Khó kiểm thử và khó kiểm soát truy vấn. | Đưa logic vào service hoặc DTO mapper. |
| Coi projection là request DTO | Nhầm lẫn hợp đồng đọc và ghi. | Thiết kế request model và update flow riêng. |

## 15. Quy trình triển khai excerpt projection

Khi muốn rút gọn representation của collection resource, thực hiện theo trình tự:

1. Xác định collection cần hiển thị và các field thực sự cần thiết.
2. Tạo interface projection với `@Projection(name = ..., types = ...)`.
3. Đặt projection trong package repository có thể tự phát hiện hoặc đăng ký rõ ràng.
4. Khai báo `excerptProjection` trên `@RepositoryRestResource`.
5. Kiểm tra collection response để xác nhận `_embedded` dùng đúng projection.
6. Nếu item resource cần góc nhìn khác, yêu cầu `?projection=...` hoặc thiết kế endpoint riêng.
7. Dùng nested projection có chọn lọc và theo dõi lazy loading/N+1 query.
8. Không xem projection là tối ưu SQL hay cơ chế phân quyền.
9. Kiểm thử field được expose, field bị loại bỏ, relation và các projection tùy chọn qua HTTP.

Excerpt projection giúp Spring Data REST công bố một góc nhìn mặc định gọn cho các item trong collection resource. Khi đặt tên projection rõ ràng, hiểu khác biệt giữa collection và item, đồng thời kiểm tra hiệu năng và bảo mật ở các đường truy cập khác, API có thể phục vụ nhiều nhu cầu đọc mà vẫn giữ representation nhất quán.

## Tài liệu tham khảo

- [Spring Data REST – Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST – RepositoryRestResource API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [Spring Data REST – Projection API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/Projection.html)
- [Spring Data Commons – Projections](https://docs.spring.io/spring-data/commons/reference/repositories/projections.html)
