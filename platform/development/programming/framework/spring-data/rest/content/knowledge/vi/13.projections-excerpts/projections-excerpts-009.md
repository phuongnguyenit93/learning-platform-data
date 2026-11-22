# Phạm vi áp dụng excerpt với tập hợp, quan hệ và tài nguyên đơn

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích excerpt projection được áp dụng ở đâu trong Spring Data REST.
- Phân biệt representation của collection, association resource và item resource.
- Cấu hình excerpt mặc định bằng **@RepositoryRestResource(excerptProjection = ...)**.
- Chủ động yêu cầu projection cho một tài nguyên đơn.
- Hiểu cách projection có thể đưa dữ liệu quan hệ vào body trong khi HAL vẫn giữ link điều hướng.
- Tránh nhầm excerpt với cơ chế bảo mật dữ liệu.

## 1. Projection và excerpt giải quyết vấn đề gì?

Spring Data REST có thể xuất bản entity cùng các thuộc tính và liên kết của nó. Tuy nhiên, một màn hình danh sách thường chỉ cần vài trường ngắn gọn, trong khi trang chi tiết cần nhiều thông tin hơn. Nếu mọi response đều trả cùng một representation đầy đủ, payload có thể lớn và client phải nhận dữ liệu mà nó không dùng.

**Projection** định nghĩa một view của domain object: những thuộc tính nào được đưa vào representation. **Excerpt** là một projection được Spring Data REST tự động áp dụng khi nhúng các item vào collection hoặc các related resources theo cấu hình repository.

Ví dụ một entity Person có nhiều thuộc tính:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phoneNumber;
    private String internalNote;
}
~~~

Màn hình danh sách có thể chỉ cần tên, trong khi màn hình chi tiết cần email và số điện thoại. Excerpt giúp đặt representation mặc định gọn hơn cho những nơi hiển thị danh sách.

Điểm cần nhớ là excerpt điều khiển cách entity được **nhúng vào một representation khác**. Nó không tự động trở thành representation mặc định của mọi URL item.

## 2. Định nghĩa excerpt projection

Tạo projection interface:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();
}
~~~

Projection có tên **personExcerpt** và áp dụng cho domain type **Person**. Các getter xác định những thuộc tính được xuất hiện trong view này.

Cấu hình trên repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Thuộc tính **excerptProjection** chọn projection được dùng khi Spring Data REST nhúng các Person vào collection resource hoặc related resources. Repository vẫn quản lý entity Person như trước; annotation chỉ thay đổi representation mặc định ở các ngữ cảnh nhúng.

Projection phải nhắm đúng domain type. Đặt interface và annotation ở package mà cấu hình ứng dụng có thể phát hiện, đồng thời bảo đảm repository được Spring Data REST xuất bản.

## 3. Phạm vi thứ nhất: collection resource

Khi client gọi collection:

~~~http
GET /api/people
Accept: application/hal+json
~~~

Spring Data REST trả collection representation. Các Person được nhúng trong **_embedded** sẽ dùng excerpt projection đã cấu hình cho PersonRepository.

Ví dụ minh họa:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "Lan",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/1"
          }
        }
      },
      {
        "firstName": "Minh",
        "lastName": "Tran",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/2"
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

Trong ví dụ, các item Person chỉ hiển thị firstName và lastName theo PersonExcerpt. Những trường khác của entity không được đưa vào excerpt này.

Client vẫn có link **self** để mở từng item. Excerpt không xóa tài nguyên chi tiết và cũng không thay đổi ID hoặc dữ liệu lưu trong database.

## 4. Phạm vi thứ hai: related resources và association

Excerpt projection cũng được dùng khi Spring Data REST nhúng entity vào các related resources. Điều này hữu ích với quan hệ giữa các domain object.

Giả sử Person có quan hệ tới Address:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    @ManyToOne
    private Address address;
}
~~~

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String city;
    private String street;
    private String postalCode;
}
~~~

Repository Address có thể cấu hình excerpt riêng:

~~~java
@Projection(name = "addressExcerpt", types = Address.class)
public interface AddressExcerpt {

    String getCity();

    String getStreet();
}
~~~

~~~java
@RepositoryRestResource(
    path = "addresses",
    excerptProjection = AddressExcerpt.class
)
public interface AddressRepository extends JpaRepository<Address, Long> {
}
~~~

Khi Address được nhúng vào collection hoặc related resource theo cơ chế excerpt, Spring Data REST dùng projection của **Address**, tức AddressExcerpt. Cấu hình excerpt của PersonRepository và AddressRepository gắn với domain type mà từng repository quản lý; không nên nhầm projection của entity cha với projection của entity liên quan.

Ví dụ một collection/related representation có thể nhúng Address ở dạng rút gọn và vẫn cung cấp link để điều hướng:

~~~json
{
  "city": "Ho Chi Minh City",
  "street": "Le Loi",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/addresses/9"
    }
  }
}
~~~

Với association resource, hãy quan sát loại entity đang được nhúng. Nếu resource trả một collection các Address, excerpt được cấu hình cho Address là cấu hình liên quan tới các Address được nhúng. Với quan hệ đơn trị hoặc representation lồng nhau, cách hiển thị cụ thể còn phụ thuộc projection được chọn và cách association được biểu diễn.

Không phải cứ có property quan hệ là mọi object liên quan tự động được inline. Mặc định Spring Data REST có thể biểu diễn quan hệ bằng link; projection có thể chủ động đưa dữ liệu liên quan vào body.

## 5. Phân biệt excerpt của entity cha và projection lồng quan hệ

Có hai việc khác nhau:

1. **Excerpt của repository** quyết định view mặc định khi item thuộc domain type đó được nhúng trong collection hoặc related resource.
2. **Getter quan hệ trong projection** quyết định có đưa dữ liệu của association vào representation projection hay không.

Ví dụ PersonExcerpt chỉ có firstName và lastName thì address không được thêm vào view chỉ vì entity có property address.

Nếu muốn in thông tin địa chỉ cùng Person, khai báo getter quan hệ:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    String getLastName();

    Address getAddress();
}
~~~

Khi projection này được sử dụng, dữ liệu Address có thể được inline trong representation theo cách Spring Data REST xử lý projection. HAL vẫn có thể cung cấp link association để client mở resource riêng.

Ví dụ representation minh họa:

~~~json
{
  "firstName": "Lan",
  "lastName": "Nguyen",
  "address": {
    "city": "Ho Chi Minh City",
    "street": "Le Loi"
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
~~~

Projection có thể tạo một representation vừa chứa một phần dữ liệu liên quan vừa giữ link điều hướng. Client không cần phải thực hiện thêm GET chỉ để lấy thông tin đã được inline, nhưng vẫn có thể đi theo link nếu cần resource đầy đủ.

Nếu muốn giới hạn trường được inline của Address, hãy định nghĩa projection phù hợp cho Address và kiểm tra representation thực tế. Đừng giả định getter quan hệ sẽ luôn dùng đúng excerpt của repository đích trong mọi ngữ cảnh lồng nhau; việc inline phụ thuộc projection và cơ chế rendering của Spring Data REST.

## 6. Phạm vi thứ ba: item resource không tự áp dụng excerpt

Đây là khác biệt quan trọng nhất.

Khi client gọi trực tiếp một item:

~~~http
GET /api/people/1
Accept: application/hal+json
~~~

Spring Data REST không tự động áp dụng excerpt projection đã cấu hình cho collection. Item resource mặc định trả representation chi tiết của entity theo cách xuất bản thông thường.

Lý do là collection excerpt là bản xem trước dành cho danh sách. Client truy cập URL item thường đang yêu cầu một tài nguyên cụ thể và có thể cần representation đầy đủ hơn.

Ví dụ collection có thể chỉ chứa:

~~~json
{
  "firstName": "Lan",
  "lastName": "Nguyen"
}
~~~

Trong khi item resource có thể chứa thêm email, phoneNumber và các thuộc tính được xuất bản khác, cùng link association.

Vì vậy, không nên kết luận rằng một trường bị thiếu trong collection excerpt thì trường đó không tồn tại hoặc không được item resource cung cấp.

## 7. Yêu cầu projection rõ ràng cho item resource

Nếu client muốn item resource dùng một projection cụ thể, hãy truyền tên projection qua query parameter **projection**:

~~~http
GET /api/people/1?projection=personExcerpt
Accept: application/hal+json
~~~

Spring Data REST có thể áp dụng projection đã đăng ký tên **personExcerpt** cho response item.

Projection cần được phát hiện và đăng ký cho đúng domain type. Tên trong query parameter là thuộc tính **name** của annotation **@Projection**, không phải tên class Java hay tên repository.

Ví dụ:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();
}
~~~

Client yêu cầu:

~~~text
/api/people/1?projection=personExcerpt
~~~

Đối với collection, client cũng có thể yêu cầu projection tường minh khi API và cấu hình hỗ trợ. Tuy nhiên, excerptProjection trên repository đã là lựa chọn mặc định cho item được nhúng trong collection; query parameter hữu ích khi client cần chọn một view khác.

Không nhầm **excerptProjection** với **projection** query parameter:

- **excerptProjection** cấu hình view mặc định cho item được nhúng.
- **projection=...** yêu cầu một projection cụ thể cho request.

## 8. So sánh phạm vi áp dụng

| Ngữ cảnh | Excerpt mặc định có tự áp dụng? | Cách chọn view |
|---|---|---|
| Collection resource, các item trong _embedded | Có, theo repository của domain type item | **excerptProjection** trên repository |
| Related/association resource có nhúng item | Có thể áp dụng cho item được nhúng theo excerpt đã cấu hình cho domain type đó | Cấu hình excerpt trên repository của domain type liên quan |
| Item resource gọi trực tiếp, ví dụ **/people/1** | Không | Yêu cầu **?projection=personExcerpt** nếu muốn projection |
| Dữ liệu quan hệ được inline qua projection | Theo projection được chọn và cơ chế rendering | Khai báo getter quan hệ trong projection |
| Link tới association resource | Link vẫn có thể được giữ trong HAL | Theo relation và href server công bố |

Cách đọc bảng:

- Hãy hỏi entity nào đang được nhúng vào representation.
- Tìm repository quản lý domain type đó.
- Kiểm tra repository có excerptProjection hay không.
- Nếu đang gọi item URL trực tiếp, hãy yêu cầu projection rõ ràng khi cần.
- Nếu muốn dữ liệu quan hệ inline, khai báo property quan hệ trong projection phù hợp.

## 9. Ví dụ tổng hợp

Giả sử ứng dụng có:

- PersonRepository cấu hình PersonExcerpt.
- AddressRepository cấu hình AddressExcerpt.
- Person có association tới Address.

Repository:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

~~~java
@RepositoryRestResource(
    path = "addresses",
    excerptProjection = AddressExcerpt.class
)
public interface AddressRepository extends JpaRepository<Address, Long> {
}
~~~

Projection:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {
    String getFirstName();
    String getLastName();
}
~~~

~~~java
@Projection(name = "addressExcerpt", types = Address.class)
public interface AddressExcerpt {
    String getCity();
    String getStreet();
}
~~~

Các request:

~~~http
GET /api/people
~~~

Collection nhúng Person theo PersonExcerpt.

~~~http
GET /api/people/1
~~~

Item resource không tự dùng PersonExcerpt; representation mặc định của item được trả về.

~~~http
GET /api/people/1?projection=personExcerpt
~~~

Item resource được yêu cầu dùng projection personExcerpt.

~~~http
GET /api/addresses
~~~

Collection nhúng Address theo AddressExcerpt.

~~~http
GET /api/people/1/address
~~~

Association resource cho biết quan hệ address của Person 1. Nếu response nhúng một Address trong related resource, excerpt của Address có thể được dùng theo cấu hình và ngữ cảnh rendering.

Các URL là ví dụ theo base path **/api**. Hãy lấy URI thực tế từ HAL response của ứng dụng.

## 10. Kiểm tra bằng curl

Đọc collection để xem excerpt:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/people
~~~

Đọc item resource mặc định:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/1
~~~

Yêu cầu projection tường minh cho item:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people/1?projection=personExcerpt"
~~~

Đọc collection của entity liên quan:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/addresses
~~~

So sánh body giữa các response. Kiểm tra các trường xuất hiện trong **_embedded**, trường của item resource và link trong **_links**. Đừng chỉ so sánh số lượng field; hãy xác nhận đúng projection name và domain type đang được áp dụng.

## 11. Lỗi thường gặp

### Mong excerpt xuất hiện trên item URL

**@RepositoryRestResource(excerptProjection = ...)** không tự áp dụng excerpt cho một item resource được gọi trực tiếp. Hãy dùng **?projection=...** khi muốn chọn projection cho item.

### Dùng sai tên projection

Tên trong query parameter phải khớp **@Projection(name = "...")**. Tên class Java không nhất thiết là tên projection.

### Gắn excerpt vào nhầm repository

Excerpt được chọn theo domain type của item đang được nhúng. Nếu collection đang nhúng Address, hãy kiểm tra cấu hình repository quản lý Address thay vì chỉ kiểm tra PersonRepository.

### Nghĩ excerpt xóa link quan hệ

Projection thay đổi representation của dữ liệu. Link hypermedia có thể vẫn được cung cấp để client điều hướng tới association hoặc item resource riêng.

### Nghĩ getter quan hệ luôn inline mọi dữ liệu

Nếu projection không khai báo getter quan hệ, dữ liệu liên quan không tự xuất hiện chỉ vì entity có association. Nếu cần inline, hãy thêm property vào projection và kiểm tra response thực tế.

### Dùng projection để che dữ liệu nhạy cảm

Projection là cách chọn representation cho client. Nó không thay thế authorization hoặc chính sách bảo vệ dữ liệu. Nếu trường nhạy cảm không được phép tiết lộ, hãy kiểm soát quyền truy cập và thiết kế API ở server; đừng chỉ dựa vào excerpt.

### Thay đổi excerpt sau khi API đã được phát hành

Excerpt thay đổi representation mặc định của collection và related resources. Client có thể đang phụ thuộc vào các trường trước đây. Khi đổi projection, hãy xem đây là thay đổi hợp đồng API và kiểm tra tác động tới client.

## 12. Ghi nhớ

- Excerpt là projection tự động dùng khi nhúng item vào collection hoặc related resources.
- **@RepositoryRestResource(excerptProjection = ...)** cấu hình excerpt theo domain type của repository.
- Collection resource dùng excerpt cho các item trong **_embedded**.
- Related/association resource có thể dùng excerpt của domain type được nhúng.
- Item resource gọi trực tiếp không tự áp dụng excerpt.
- Dùng **?projection=tenProjection** để yêu cầu view cụ thể cho item.
- Getter quan hệ trong projection có thể inline dữ liệu liên quan; HAL vẫn có thể giữ link điều hướng.
- Projection và excerpt không phải cơ chế authorization hoặc bảo vệ dữ liệu nhạy cảm.

## Tài liệu tham khảo

- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST — RepositoryRestResource API](https://docs.spring.io/spring-data/rest/reference/5.2-SNAPSHOT/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html)
- [Spring Data REST — CollectionResourceMapping API](https://docs.spring.io/spring-data/rest/docs/3.7.11/api/org/springframework/data/rest/core/mapping/CollectionResourceMapping.html)
