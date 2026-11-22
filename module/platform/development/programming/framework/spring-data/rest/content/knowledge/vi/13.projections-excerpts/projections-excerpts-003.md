# Chọn projection bằng query parameter projection trong Spring Data REST

Spring Data REST mặc định tạo representation từ domain model mà repository công bố. Trong nhiều API, client chỉ cần một phần thuộc tính hoặc muốn xem một association theo cách khác nhau tùy màn hình. **Projection** cho phép định nghĩa một góc nhìn (view) của tài nguyên; client chọn góc nhìn đó bằng query parameter `projection`.

Ví dụ, cùng một người dùng có thể được trả về ở dạng tóm tắt chỉ gồm họ tên, hoặc ở dạng chi tiết có thêm địa chỉ. Client chọn projection ngay trên request GET mà không cần tạo endpoint riêng cho từng cách trình bày.

## 1. Projection là gì?

Projection là một interface mô tả các thuộc tính sẽ xuất hiện trong representation của một domain object. Spring Data REST tạo projection từ entity gốc khi render response.

Giả sử domain model:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;

    @OneToOne
    private Address address;

    // getters and setters
}
~~~

Nếu repository được công bố mà không có projection, Spring Data REST sử dụng representation mặc định của Person theo cấu hình serialization và association. Client có thể nhận các trường dữ liệu cùng những liên kết HAL tới tài nguyên liên quan.

Projection giúp định nghĩa representation thay thế mà không phải thay đổi entity hoặc tạo bản ghi mới. Nó không phải là một entity khác và cũng không tự thay đổi dữ liệu lưu trong database.

## 2. Khai báo projection bằng @Projection

Tạo interface projection và gắn annotation `@Projection`:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Trong ví dụ:

- `name = "personSummary"` là tên projection mà client truyền vào query parameter.
- `types = Person.class` liên kết projection với domain type Person.
- Các getter xác định những thuộc tính được đưa vào representation.
- Tên interface `PersonSummary` không phải giá trị client gửi trong URL.

Projection chỉ khai báo góc nhìn cần render. Spring Data REST sử dụng projection để tạo response tương ứng khi client yêu cầu.

### Vị trí để Spring Data REST phát hiện projection

Theo mặc định, Spring Data REST phát hiện interface có `@Projection` nếu interface nằm trong cùng package với domain type hoặc một sub-package của package đó. Projection cũng có thể được đăng ký thủ công qua cấu hình projection của `RepositoryRestConfiguration`.

Ví dụ cấu trúc package:

~~~text
com.example.people
├── Person.java
├── Address.java
├── PersonRepository.java
└── projection
    ├── PersonSummary.java
    └── PersonDetails.java
~~~

Ở đây, các projection nằm trong sub-package `projection` nên thuộc phạm vi package mà Spring Data REST tìm kiếm cho Person.

Nếu projection không được phát hiện, hãy kiểm tra annotation, thuộc tính `types`, package và cấu hình đăng ký projection. Chỉ đặt interface ở một package bất kỳ không bảo đảm nó tự động được công bố.

## 3. Chọn projection bằng query parameter projection

Giả sử repository được công bố tại đường dẫn `/people`:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Client có thể lấy một tài nguyên Person theo ID và chọn projection:

~~~http
GET /people/42?projection=personSummary
Accept: application/hal+json
~~~

Giá trị của query parameter phải trùng với `name` trong `@Projection`. Vì vậy, `projection=personSummary` chọn interface được khai báo bằng `@Projection(name = "personSummary", ...)`.

Một response minh họa có thể như sau:

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

Các trường email và address không xuất hiện trong góc nhìn này vì projection không khai báo chúng. Cấu trúc HAL thực tế còn phụ thuộc các association và cấu hình của ứng dụng.

### Chọn projection cho collection resource

Projection cũng có thể được yêu cầu khi đọc collection:

~~~http
GET /people?projection=personSummary
Accept: application/hal+json
~~~

Spring Data REST áp dụng projection được chọn khi render các item trong response collection. Client có thể dùng cùng một repository resource nhưng chọn representation phù hợp với nhu cầu của từng màn hình.

Ví dụ:

- Màn hình danh sách chỉ cần `firstName` và `lastName`.
- Màn hình chi tiết cần thêm email và địa chỉ.
- Một tác vụ tích hợp cần representation khác với giao diện người dùng.

Không cần tạo các collection endpoint riêng chỉ để trả về các tập thuộc tính khác nhau nếu projection đáp ứng được nhu cầu.

## 4. Khai báo nhiều projection cho cùng một domain type

Có thể định nghĩa nhiều interface projection cho cùng một entity:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

~~~java
@Projection(name = "personDetails", types = Person.class)
public interface PersonDetails {

    String getFirstName();

    String getLastName();

    String getEmail();

    Address getAddress();
}
~~~

Client chọn góc nhìn tương ứng:

~~~http
GET /people/42?projection=personSummary
~~~

~~~http
GET /people/42?projection=personDetails
~~~

Cả hai request đều đọc cùng Person 42. Khác biệt nằm ở representation được trả về.

Khi projection khai báo getter trả về association như `getAddress()`, dữ liệu association có thể được đưa trực tiếp vào representation theo projection. Nếu ứng dụng cũng công bố Address repository, HAL có thể vẫn cung cấp liên kết tới tài nguyên Address để client tiếp tục điều hướng.

## 5. Projection cho association lồng nhau

Projection có thể sử dụng một projection khác cho association để kiểm soát dữ liệu lồng nhau.

Ví dụ:

~~~java
@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {

    String getCity();

    String getStreet();
}
~~~

Person projection có thể khai báo getter trả về AddressSummary:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    String getLastName();

    AddressSummary getAddress();
}
~~~

Khi client yêu cầu:

~~~http
GET /people/42?projection=personWithAddress
~~~

representation có thể chứa dữ liệu địa chỉ được trình bày lồng trong Person theo các getter của AddressSummary.

Cách này hữu ích khi client cần dữ liệu liên quan trong một response và muốn giới hạn thuộc tính của association. Hãy kiểm tra package discovery và cách Spring Data REST áp dụng projection cho association trong phiên bản đang sử dụng.

## 6. Projection tạo thuộc tính tính toán bằng @Value

Projection interface không chỉ trả về các thuộc tính có sẵn. Có thể tạo một thuộc tính ảo bằng SpEL thông qua annotation `@Value`.

Ví dụ kết hợp họ và tên:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personName", types = Person.class)
public interface PersonName {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getFullName();
}
~~~

Request:

~~~http
GET /people/42?projection=personName
~~~

Representation có thể chứa:

~~~json
{
  "fullName": "An Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

Thuộc tính `fullName` được tính từ object đích khi render response. Nó không phải một field mới được ghi vào bảng Person.

Với projection dùng SpEL, cần hiểu biểu thức đang truy cập thuộc tính nào và tránh đưa logic nghiệp vụ phức tạp vào representation. Nếu phép tính cần truy vấn dữ liệu hoặc quy tắc nghiệp vụ lớn, service hoặc DTO chuyên biệt có thể phù hợp hơn.

## 7. Phân biệt projection được chọn và excerpt projection

**Projection được chọn bằng query parameter** áp dụng theo từng request. Client chỉ định góc nhìn bằng `?projection=...`.

**Excerpt projection** là projection được cấu hình làm representation mặc định khi Spring Data REST nhúng item vào collection resource hoặc related resource.

Ví dụ khai báo excerpt cho Person:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Khi client gọi:

~~~http
GET /people
~~~

Spring Data REST dùng PersonSummary làm góc nhìn mặc định cho các Person được nhúng trong collection response.

Excerpt projection **không tự động được áp dụng cho một item resource riêng lẻ**. Khi cần projection cho item resource, client có thể yêu cầu rõ ràng bằng query parameter:

~~~http
GET /people/42?projection=personSummary
~~~

Sự khác biệt này rất quan trọng khi kiểm tra response: collection có thể hiển thị excerpt trong khi request tới item URI vẫn hiển thị representation đầy đủ theo mặc định.

### Excerpt có thể đưa association vào response

Một excerpt projection có thể khai báo getter cho association:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();

    Address getAddress();
}
~~~

Sau đó cấu hình:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Khi collection được render, dữ liệu address có thể được nhúng vào representation của Person. Liên kết association vẫn có thể được cung cấp để client truy cập tài nguyên Address độc lập.

Cấu hình excerpt làm thay đổi representation mặc định của collection và related resources. Nếu API đã có client sử dụng, thay đổi excerpt có thể làm thay đổi cấu trúc response mà các client đó phụ thuộc vào. Hãy xem đây là một thay đổi hợp đồng API và kiểm tra tương thích trước khi phát hành.

## 8. Khám phá projection được hỗ trợ qua ALPS

Spring Data REST cung cấp metadata ALPS để mô tả các thao tác và thuộc tính của REST resource. Client có thể theo liên kết `profile` được công bố ở root resource, sau đó xem metadata của loại tài nguyên tương ứng.

Trong mô tả thao tác GET, ALPS có thể liệt kê descriptor `projection` cùng những projection name được hỗ trợ. Nhờ đó, client có thể khám phá tên projection thay vì phải tự đoán từ tên interface Java.

Quy trình khám phá:

1. Gọi root resource của API.
2. Theo liên kết `profile` trong HAL.
3. Mở metadata ALPS cho resource, ví dụ profile của Person.
4. Tìm descriptor `projection` và danh sách projection được công bố.
5. Chọn một tên hợp lệ và truyền vào query parameter `projection`.

Metadata có thể khác nhau theo repository, cấu hình và phiên bản. Client nên sử dụng profile được server thực sự công bố.

## 9. Projection không phải cơ chế phân quyền hoặc bảo vệ dữ liệu

Projection giúp chọn representation, nhưng không nên dùng nó làm ranh giới bảo mật.

Một projection có thể đưa dữ liệu vốn bị ẩn khỏi representation mặc định trở lại response. Ví dụ, nếu một thuộc tính được đánh dấu `@JsonIgnore`, projection vẫn có thể expose thuộc tính đó thông qua getter tương ứng. Vì vậy, không thể xem `@JsonIgnore` hoặc việc không xuất hiện trong projection mặc định là bảo đảm rằng dữ liệu nhạy cảm không thể bị truy cập.

Không công bố projection chứa password, token, thông tin bí mật hoặc dữ liệu người dùng không được phép xem. Hãy dùng authorization, kiểm soát export, serialization và thiết kế API phù hợp để bảo vệ dữ liệu. Kiểm tra tất cả projection được đăng ký cho một domain type trước khi công bố endpoint ra bên ngoài.

Projection cũng không thay thế DTO hoặc command object cho thao tác ghi. Query parameter `projection` điều khiển cách render representation, chủ yếu trên các request đọc. Không nên dùng projection như một cách định nghĩa tập field mà client được phép POST, PUT hoặc PATCH.

## 10. Các lỗi thường gặp khi chọn projection

**Request dùng tên interface thay vì projection name**

Ví dụ sai:

~~~http
GET /people/42?projection=PersonSummary
~~~

Nếu annotation khai báo `name = "personSummary"`, client cần gửi đúng giá trị đó:

~~~http
GET /people/42?projection=personSummary
~~~

**Projection không được phát hiện**

Kiểm tra interface có `@Projection`, `types` có đúng domain type và interface nằm trong cùng package hoặc sub-package. Nếu đặt ngoài phạm vi đó, đăng ký projection qua cấu hình phù hợp.

**Projection không hiển thị một thuộc tính**

Chỉ các getter được khai báo trong projection (cùng dữ liệu lồng nhau mà chúng trả về) mới được đưa vào góc nhìn đó. Kiểm tra getter, tên thuộc tính, kiểu trả về và association mapping.

**Excerpt xuất hiện ở collection nhưng không xuất hiện ở item resource**

Đây là hành vi theo thiết kế. Excerpt là mặc định cho item được nhúng trong collection hoặc related resources; muốn chọn projection cho một item cụ thể, truyền query parameter `projection`.

**Client không tìm thấy liên kết hoặc trường sau khi đổi projection**

Projection thay đổi representation. Hãy kiểm tra cả dữ liệu trong JSON, `_links`, `_embedded` và các thuộc tính lồng nhau mà client đang sử dụng.

**Dùng projection để ẩn dữ liệu nhạy cảm**

Projection không phải authorization. Hãy bảo vệ dữ liệu nhạy cảm ở tầng bảo mật và serialization, đồng thời kiểm tra những projection đã đăng ký.

## 11. Kiểm thử projection qua HTTP

Nên kiểm thử endpoint thật để xác nhận projection được phát hiện và được áp dụng đúng.

Một bộ kiểm thử cơ bản:

1. Gọi `GET /people/42` để lấy representation mặc định.
2. Gọi `GET /people/42?projection=personSummary` và xác nhận chỉ có các thuộc tính mà PersonSummary khai báo.
3. Gọi `GET /people?projection=personSummary` và kiểm tra các item trong collection dùng projection đã chọn.
4. Gọi `GET /people` khi repository có excerptProjection và xác nhận excerpt được áp dụng cho các item nhúng.
5. Gọi `GET /people/42` để xác nhận excerpt không tự động áp dụng cho item resource riêng lẻ.
6. Kiểm tra projection có association hoặc thuộc tính tính toán.
7. Kiểm tra ALPS profile có công bố projection name mong muốn.
8. Kiểm tra không projection nào vô tình expose dữ liệu nhạy cảm.
9. Kiểm tra client hiện có khi thay đổi getter, tên projection hoặc excerpt mặc định.

Không chỉ kiểm tra HTTP status 200. Hãy so sánh cấu trúc response, trường dữ liệu, liên kết HAL và dữ liệu lồng nhau với hợp đồng mà client mong đợi.

## 12. Quy trình triển khai

1. Xác định những representation mà client cần cho từng màn hình hoặc use case.
2. Tạo interface projection cho từng góc nhìn, gắn `@Projection` và đặt tên ổn định.
3. Đặt projection trong cùng package hoặc sub-package của domain type, hoặc đăng ký thủ công.
4. Dùng query parameter `projection` để chọn góc nhìn theo từng request GET.
5. Chỉ cấu hình `excerptProjection` khi muốn đặt mặc định cho item được nhúng trong collection hoặc related resources.
6. Dùng projection lồng nhau khi cần kiểm soát association; dùng `@Value` cho thuộc tính tính toán đơn giản.
7. Kiểm tra ALPS, HAL response và authorization để tránh công bố sai hoặc lộ dữ liệu.
8. Chạy integration test và contract test cho collection, item, association và các client liên quan.

## 13. Những điểm cần ghi nhớ

- Projection là góc nhìn của domain object dùng khi Spring Data REST render representation.
- Khai báo projection bằng interface có `@Projection(name = "...", types = ...)`.
- Query parameter `projection` nhận giá trị `name` của annotation, không nhận tên interface Java.
- Có thể chọn projection cho item resource và collection resource theo từng request.
- Spring Data REST tự phát hiện projection trong cùng package hoặc sub-package của domain type; cũng có thể đăng ký thủ công.
- Excerpt projection được cấu hình bằng `@RepositoryRestResource(excerptProjection = ...)` và áp dụng mặc định cho item được nhúng trong collection hoặc related resources.
- Excerpt không tự động áp dụng cho item resource riêng lẻ; dùng `?projection=...` khi cần chọn projection cho item.
- Projection có thể lồng association và tạo thuộc tính ảo bằng `@Value`.
- Projection không phải cơ chế authorization và có thể làm lộ dữ liệu nhạy cảm nếu khai báo getter không phù hợp.
- Kiểm thử response HAL/JSON và ALPS để bảo đảm client nhận đúng representation.

## Nguồn tham khảo

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — RepositoryRestResource API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [Spring Data REST — Projection annotation API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/Projection.html)
