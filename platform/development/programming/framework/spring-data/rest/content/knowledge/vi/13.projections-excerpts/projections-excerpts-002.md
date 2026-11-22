# Khai báo interface @Projection với name và types

Spring Data REST có thể trả về nhiều cách biểu diễn khác nhau cho cùng một entity. **Projection** cho phép định nghĩa một view chỉ đọc bằng interface: interface khai báo những thuộc tính cần xuất hiện trong response, còn Spring Data tạo implementation proxy để lấy dữ liệu từ entity.

Annotation **@Projection** gắn projection với một hoặc nhiều kiểu domain và đặt tên để client có thể chọn view đó. Hai thuộc tính cần hiểu rõ là:

- **`name`**: tên định danh projection, được dùng trong query parameter **`projection`**.
- **`types`**: các kiểu domain mà projection áp dụng, thường là entity class như **`Person.class`**.

Projection giúp kiểm soát representation REST mà không cần tạo một DTO và controller riêng cho mỗi cách hiển thị.

## 1. @Projection khai báo một view bằng interface

Annotation **`@Projection`** thuộc package:

~~~java
import org.springframework.data.rest.core.config.Projection;
~~~

Ví dụ entity Person:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phone;
    private boolean active;

    // getters and setters
}
~~~

Tạo một interface projection chỉ chứa các getter cần công bố:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "summary", types = { Person.class })
public interface PersonSummary {

    String getFirstName();

    String getLastName();

    boolean isActive();
}
~~~

Trong khai báo này:

- **`PersonSummary`** là tên interface Java.
- **`name = "summary"`** là tên projection mà client dùng để chọn view.
- **`types = { Person.class }`** cho biết projection áp dụng cho domain type **`Person`**.
- Các getter xác định các thuộc tính được đưa vào representation.

Tên interface và giá trị **`name`** không bắt buộc phải giống nhau. Nên chọn một tên ngắn, có ý nghĩa và ổn định để client dễ sử dụng.

## 2. Hiểu thuộc tính name

**`name`** là tên định danh của projection trong Spring Data REST. Ví dụ:

~~~java
@Projection(name = "summary", types = { Person.class })
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
~~~

Client chọn projection bằng query parameter:

~~~http
GET /people/1?projection=summary
Accept: application/hal+json
~~~

Response chỉ hiển thị các thuộc tính được projection công bố cùng những metadata/links cần thiết của HAL. Ví dụ phần dữ liệu có thể có dạng:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/1"
    }
  }
}
~~~

Nếu đổi tên projection thành **`compact`**, client cũng phải dùng:

~~~http
GET /people/1?projection=compact
~~~

Tên projection là một phần contract mà client phụ thuộc. Khi đổi tên, hãy cập nhật các client đang gửi query parameter cũ.

## 3. Hiểu thuộc tính types

**`types`** xác định domain type mà projection áp dụng. Đây là một mảng class, do đó có thể khai báo một hoặc nhiều kiểu domain nếu cùng một interface projection phù hợp với các kiểu đó.

Ví dụ áp dụng cho Person:

~~~java
@Projection(name = "summary", types = { Person.class })
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
~~~

Nếu một projection thực sự dùng được cho nhiều kiểu domain có cùng các thuộc tính cần đọc, có thể khai báo:

~~~java
@Projection(
    name = "named",
    types = { Person.class, Employee.class }
)
public interface NamedSummary {
    String getName();
}
~~~

Các kiểu được liệt kê phải có những thuộc tính tương thích với getter trong projection. Nếu một type không có thuộc tính mà interface yêu cầu, việc tạo representation cho type đó có thể thất bại.

Không nên thêm nhiều class vào **`types`** chỉ để tái sử dụng tên projection. Hãy bảo đảm mọi domain type được khai báo đều có contract getter phù hợp.

## 4. Vị trí đặt interface projection

Spring Data REST cần phát hiện interface projection khi khởi tạo cấu hình repository. Theo quy ước, đặt interface có **`@Projection`** trong cùng package với domain type hoặc một package con của package đó.

Ví dụ cấu trúc:

~~~text
com.example.demo
├── person
│   ├── Person.java
│   └── PersonSummary.java
└── repository
    └── PersonRepository.java
~~~

Nếu **`Person`** nằm trong package **`com.example.demo.person`**, projection **`PersonSummary`** đặt cùng package này sẽ được phát hiện theo quy ước.

Nếu projection nằm ngoài package được quét, query parameter **`projection=summary`** có thể không được nhận diện như mong đợi. Hãy kiểm tra package của domain type, vị trí interface và cấu hình scan của ứng dụng.

## 5. Getter quyết định thuộc tính được xuất

Projection interface thường khai báo getter tương ứng với property của entity:

| Getter trong projection | Property được đọc |
|---|---|
| **`String getFirstName()`** | **`firstName`** |
| **`String getEmail()`** | **`email`** |
| **`boolean isActive()`** | **`active`** |
| **`AddressSummary getAddress()`** | Quan hệ **`address`** qua projection lồng nhau |

Chỉ khai báo các getter mà client cần. Ví dụ không muốn công bố số điện thoại thì không thêm **`getPhone()`** vào projection.

Projection interface không cần triển khai các getter bằng tay. Spring Data tạo proxy để đọc giá trị từ entity khi tạo representation.

Projection là view chỉ đọc. Nó không thay đổi entity, không ghi dữ liệu xuống database và không thay thế cơ chế authorization. Không công bố một thuộc tính nhạy cảm chỉ vì getter có thể đọc được thuộc tính đó.

## 6. Projection lồng nhau cho quan hệ

Một projection có thể trả về projection khác để định hình representation của quan hệ.

Ví dụ entity Person có quan hệ tới Address:

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String city;
    private String street;

    // getters and setters
}
~~~

Tạo projection cho Address:

~~~java
@Projection(name = "addressSummary", types = { Address.class })
public interface AddressSummary {

    String getCity();
}
~~~

Sau đó dùng projection này trong Person:

~~~java
@Projection(name = "withAddress", types = { Person.class })
public interface PersonWithAddress {

    String getFirstName();

    AddressSummary getAddress();
}
~~~

Khi client gọi:

~~~http
GET /people/1?projection=withAddress
~~~

representation có thể bao gồm **firstName** và phần địa chỉ được giới hạn bởi **AddressSummary**. Điều này giúp tránh xuất toàn bộ thuộc tính của object liên quan khi client chỉ cần một phần.

Projection lồng nhau cần được phát hiện và có getter tương thích với quan hệ thực tế. Với collection association, getter có thể trả về collection hoặc danh sách projection phù hợp, ví dụ **`List<RoleSummary> getRoles()`**.

## 7. Thuộc tính tính toán và open projection

Ngoài getter trực tiếp ánh xạ tới property, interface projection có thể cung cấp thuộc tính tính toán.

Một cách là dùng default method dựa trên các getter khác:

~~~java
@Projection(name = "nameCard", types = { Person.class })
public interface PersonNameCard {

    String getFirstName();

    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
~~~

Một cách khác là dùng **`@Value`** với SpEL:

~~~java
import org.springframework.beans.factory.annotation.Value;

@Projection(name = "fullName", types = { Person.class })
public interface PersonFullName {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
~~~

Projection sử dụng SpEL như trên thường được gọi là open projection. Vì biểu thức có thể tham chiếu tới nhiều thuộc tính của target, framework khó xác định chính xác tập property cần tải trước. Nếu có thể, ưu tiên closed projection với getter trực tiếp hoặc default method dựa trên getter đã khai báo.

## 8. Chọn projection khi gọi REST API

Khi projection đã được phát hiện, client có thể chọn nó bằng query parameter **`projection`** trên resource hỗ trợ projection.

Ví dụ lấy một item:

~~~http
GET /people/1?projection=summary
Accept: application/hal+json
~~~

Ví dụ lấy collection:

~~~http
GET /people?projection=summary
Accept: application/hal+json
~~~

Nếu không truyền **`projection`**, Spring Data REST trả về representation mặc định của resource, theo cấu hình và các excerpt projection nếu có.

Projection được chọn chỉ định hình phần dữ liệu của representation. URI resource, phân trang, liên kết HAL và quyền truy cập vẫn tuân theo cấu hình endpoint tương ứng.

## 9. Đặt excerptProjection mặc định cho collection

Nếu muốn collection luôn dùng một projection cụ thể khi nhúng các item, có thể cấu hình **`excerptProjection`** trên **`@RepositoryRestResource`**.

Ví dụ:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(excerptProjection = PersonSummary.class)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Khi client gọi:

~~~http
GET /people
Accept: application/hal+json
~~~

các item được nhúng trong collection representation có thể sử dụng **`PersonSummary`** làm excerpt mặc định.

Excerpt projection chủ yếu điều khiển cách các item được hiển thị bên trong collection. Khi đọc một item resource riêng lẻ, client vẫn có thể chọn projection qua query parameter nếu projection được công bố.

Chỉ định **`excerptProjection`** cần trỏ tới một interface projection phù hợp với domain type của repository. Nếu không cần excerpt mặc định, có thể bỏ thuộc tính này.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| **`projection=summary`** không có tác dụng | Projection chưa được phát hiện hoặc tên không khớp | Kiểm tra **`@Projection`**, package và giá trị **`name`** |
| Projection không áp dụng cho entity | **`types`** thiếu hoặc khai báo sai domain class | Thêm đúng class vào mảng **`types`** |
| Response thiếu thuộc tính mong đợi | Getter không khớp property hoặc property không được cung cấp | Kiểm tra tên getter và model entity |
| Projection lồng nhau không hiển thị đúng | Getter trả về sai kiểu hoặc projection con chưa được phát hiện | Kiểm tra kiểu quan hệ và interface projection con |
| Collection dùng excerpt mặc định không như mong muốn | Repository chưa cấu hình **`excerptProjection`** hoặc class không phù hợp | Kiểm tra annotation trên repository |
| Projection làm lộ dữ liệu nhạy cảm | Interface có getter cho thuộc tính không nên công bố | Bỏ getter không cần thiết và áp dụng authorization phù hợp |

## 11. Quy trình thực hành

Có thể thực hành với **Person**:

1. Tạo entity **`Person`** có các thuộc tính **`firstName`**, **`lastName`**, **`email`** và **`phone`**.
2. Tạo interface **`PersonSummary`** với **`@Projection(name = "summary", types = { Person.class })`**.
3. Khai báo getter chỉ cho **`firstName`**, **`lastName`** và thuộc tính mà client cần.
4. Đặt interface trong package được Spring Data REST phát hiện.
5. Khởi động ứng dụng và gọi **`GET /people/1?projection=summary`**.
6. Kiểm tra response có các thuộc tính đã chọn và không xuất các thuộc tính bị bỏ qua.
7. Nếu muốn collection dùng view này mặc định, cấu hình **`excerptProjection = PersonSummary.class`** trên repository rồi gọi **`GET /people`**.

Ví dụ interface hoàn chỉnh:

~~~java
package com.example.demo.person;

import org.springframework.data.rest.core.config.Projection;

@Projection(name = "summary", types = { Person.class })
public interface PersonSummary {

    String getFirstName();

    String getLastName();

    boolean isActive();
}
~~~

Ví dụ request:

~~~http
GET http://localhost:8080/people/1?projection=summary
Accept: application/hal+json
~~~

Hãy so sánh response có projection với response mặc định để thấy rõ projection thay đổi representation như thế nào.

## 12. Lưu ý thiết kế API

- Đặt **`name`** ngắn gọn, có ý nghĩa và giữ ổn định vì client dùng tên này trong URL.
- Khai báo chính xác các domain class trong **`types`**; chỉ dùng nhiều type khi getter thực sự tương thích.
- Chỉ đưa vào projection các getter cần thiết cho use case.
- Dùng projection lồng nhau để kiểm soát dữ liệu của association.
- Ưu tiên closed projection khi có thể để framework xác định property cần đọc rõ ràng hơn.
- Dùng **`excerptProjection`** khi muốn đặt view mặc định cho item được nhúng trong collection.
- Projection chỉ điều khiển representation, không thay thế bảo mật, validation hoặc giới hạn truy cập dữ liệu.

Tài liệu tham khảo chính thức:

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Projection annotation API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/Projection.html)
