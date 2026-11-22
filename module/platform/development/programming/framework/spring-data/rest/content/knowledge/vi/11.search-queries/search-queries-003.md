# Đặt tên tham số truy vấn bằng @Param

## Mục tiêu

Trong Spring Data REST, query method của repository được công bố dưới resource `search`. Các tham số thông thường của method được truyền từ query string của HTTP GET request. Annotation `@Param` cho phép đặt tên rõ ràng cho từng tham số trên URL.

Ví dụ, method:

~~~java
List<Person> findByLastName(@Param("lastName") String value);
~~~

được gọi qua query resource bằng tham số:

~~~http
GET /api/people/search/findByLastName?lastName=Nguyen
~~~

Ở đây, `lastName` là tên query parameter do `@Param("lastName")` công bố; tên biến Java `value` không phải tên mà client cần gửi.

## 1. Query method được công bố dưới /search

Spring Data REST tự động tạo search resource cho repository được export khi repository có query method đủ điều kiện công bố.

Giả sử repository Person được export tại `/api/people`:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

Search resource thường xuất hiện ở:

~~~http
GET /api/people/search
~~~

Response search resource chứa các link tới query method được export. Với method ví dụ trên, link mặc định có thể là:

~~~json
{
  "_links": {
    "findByLastName": {
      "href": "https://api.example.com/api/people/search/findByLastName{?lastName}",
      "templated": true
    }
  }
}
~~~

Client nên đọc link được server công bố thay vì tự suy đoán URL. Tên path mặc định được suy ra từ query method, còn query parameter được suy ra từ metadata tham số của method.

## 2. @Param đặt tên query parameter

`@Param` thuộc Spring Data Commons:

~~~java
import org.springframework.data.repository.query.Param;
~~~

Gắn annotation vào tham số repository để công bố tên mà query resource nhận từ URL:

~~~java
@RestResource(path = "by-last-name", rel = "byLastName")
List<Person> findPeople(
        @Param("lastName") String value);
~~~

Client gọi:

~~~http
GET /api/people/search/by-last-name?lastName=Nguyen
~~~

Có ba tên khác nhau cần phân biệt:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Tên method Java | `findPeople` | Xác định query method |
| Path của query resource | `by-last-name` | Chọn endpoint dưới `/search` |
| Tên query parameter | `lastName` | Truyền giá trị vào tham số method |

Tên biến Java có thể là `value`, `surname` hoặc một tên khác. Khi đã dùng `@Param("lastName")`, client gửi đúng key `lastName` theo annotation.

### Vì sao nên đặt tên tường minh?

- Tên query parameter trở thành một phần của HTTP API contract.
- Refactor tên biến Java không làm thay đổi URL client đang sử dụng.
- Người đọc repository có thể thấy ngay tên mà client cần gửi.
- Tên tham số không phụ thuộc vào việc compiler có giữ metadata tên tham số hay không.

Nếu dựa vào tên tham số được khám phá từ bytecode, kết quả có thể phụ thuộc cấu hình biên dịch và cơ chế parameter-name discovery. Dùng `@Param` tường minh giúp contract dễ đọc và ổn định hơn.

## 3. Ví dụ đầy đủ với nhiều tham số

Giả sử cần tìm Person theo họ và trạng thái hoạt động, đồng thời hỗ trợ phân trang:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name-and-active", rel = "byLastNameAndActive")
    Page<Person> findByLastNameAndActive(
            @Param("lastName") String lastName,
            @Param("active") boolean active,
            Pageable pageable);
}
~~~

Client gọi:

~~~http
GET /api/people/search/by-last-name-and-active?lastName=Nguyen&active=true&page=0&size=20&sort=lastName,asc
Accept: application/hal+json
~~~

Spring Data REST phân tích request như sau:

| Query parameter | Giá trị | Được bind vào |
|---|---|---|
| `lastName` | `Nguyen` | `@Param("lastName") String lastName` |
| `active` | `true` | `@Param("active") boolean active` |
| `page` | `0` | `Pageable` |
| `size` | `20` | `Pageable` |
| `sort` | `lastName,asc` | `Pageable` |

`@Param` đặt tên cho hai tham số nghiệp vụ. `Pageable` là tham số đặc biệt được Spring Data nhận diện để xử lý phân trang và sắp xếp; không cần gắn `@Param` cho nó.

Với request trên, method repository nhận `lastName = "Nguyen"`, `active = true` và một Pageable mô tả trang đầu, 20 phần tử mỗi trang, sắp xếp theo `lastName` tăng dần.

## 4. @Param và Pageable/Sort

Các tham số phân trang và sắp xếp được Spring Data xử lý theo quy ước riêng:

- `Pageable` nhận các query parameter như `page`, `size` và `sort`.
- `Sort` nhận thông tin sắp xếp từ query parameter `sort`.
- Các tham số nghiệp vụ khác được bind theo tên đã khai báo bằng `@Param` hoặc cơ chế khám phá tên tham số mà repository hỗ trợ.

Ví dụ chỉ dùng Sort:

~~~java
List<Person> findByActive(
        @Param("active") boolean active,
        Sort sort);
~~~

Request:

~~~http
GET /api/people/search/findByActive?active=true&sort=lastName,asc
~~~

Nếu dùng Pageable, có thể chỉ định nhiều tiêu chí sort bằng cách lặp query parameter:

~~~http
GET /api/people/search/findByLastName?lastName=Nguyen&sort=lastName,asc&sort=firstName,asc&page=0&size=20
~~~

Tên `page`, `size`, `sort` là quy ước của Spring Data web support. Không đổi chúng thành tên nghiệp vụ bằng `@Param`; hãy dành `@Param` cho các tham số truy vấn của method.

## 5. Đặt tên path và tên tham số là hai việc độc lập

`@RestResource` và `@Param` giải quyết hai phần khác nhau của URL.

~~~java
@RestResource(path = "by-email", rel = "byEmail")
Optional<Person> findByEmailAddress(
        @Param("email") String emailAddress);
~~~

Request:

~~~http
GET /api/people/search/by-email?email=an%40example.com
~~~

Trong ví dụ:

- `path = "by-email"` quyết định đoạn path sau `/search/`.
- `rel = "byEmail"` quyết định tên relation trong search resource.
- `@Param("email")` quyết định tên query key.
- `emailAddress` là tên biến Java trong method.

Nếu chỉ đổi `path`, query key `email` vẫn giữ nguyên. Nếu chỉ đổi `@Param`, path `by-email` vẫn giữ nguyên. Khi đổi một trong hai, hãy cập nhật client theo đúng phần contract đã thay đổi.

## 6. Dùng @Param với @Query

Trong Spring Data JPA, `@Param` cũng thường liên kết tham số method với named parameter trong JPQL:

~~~java
@Query("""
    select p
    from Person p
    where lower(p.lastName) = lower(:lastName)
    """)
List<Person> findMatchingLastName(
        @Param("lastName") String value);
~~~

Có hai nơi cùng sử dụng tên `lastName` nhưng mang hai vai trò liên quan:

1. Trong JPQL, `:lastName` là named parameter của câu query.
2. Trong Spring Data REST, `@Param("lastName")` công bố query parameter mà HTTP client gửi.

Client gọi search resource:

~~~http
GET /api/people/search/findMatchingLastName?lastName=Nguyen
~~~

Spring Data REST bind giá trị `Nguyen` vào tham số method. Spring Data JPA sau đó dùng giá trị này cho named parameter `:lastName` trong JPQL.

Nếu đổi tên annotation thành `@Param("surname")` nhưng giữ JPQL `:lastName`, hai tên không còn khớp nhau và việc bind named parameter có thể thất bại. Khi đổi tên, hãy đồng bộ tên trong annotation và câu query.

## 7. Nhiều kiểu dữ liệu và chuyển đổi giá trị

Query parameter trên HTTP luôn được truyền dưới dạng text. Spring Data/Spring conversion infrastructure chuyển text sang kiểu tham số method khi có converter phù hợp.

Ví dụ:

~~~java
List<Person> findByAgeGreaterThanAndActive(
        @Param("minimumAge") Integer minimumAge,
        @Param("active") Boolean active);
~~~

Request:

~~~http
GET /api/people/search/findByAgeGreaterThanAndActive?minimumAge=18&active=true
~~~

Một số kiểu thường dùng:

| Kiểu Java | Giá trị query string minh họa |
|---|---|
| `String` | `lastName=Nguyen` |
| `Integer` / `Long` | `minimumAge=18` |
| `Boolean` | `active=true` |
| `Enum` | `status=ACTIVE` |
| `LocalDate` | `createdAfter=2026-01-01` |

Định dạng ngày/giờ, enum và kiểu miền tùy thuộc converter và cấu hình của ứng dụng. Hãy dùng định dạng mà API thực tế hỗ trợ và kiểm tra lỗi chuyển đổi bằng request thử nghiệm.

Nếu thiếu một tham số bắt buộc hoặc giá trị không chuyển đổi được sang kiểu Java, request có thể bị từ chối với lỗi 400 Bad Request. Không nên biến mọi lỗi 400 thành lỗi query database; hãy đọc error response và log binding để xác định nguyên nhân.

## 8. URL encoding cho giá trị query

Giá trị có dấu cách, dấu &, dấu +, ký tự Unicode hoặc ký tự dành riêng phải được URL encode đúng cách.

Ví dụ họ kép:

~~~http
GET /api/people/search/findByLastName?lastName=Van%20Nguyen
~~~

Dùng curl để encode tự động:

~~~bash
curl --get \
  --data-urlencode "lastName=Van Nguyen" \
  --data-urlencode "active=true" \
  -H "Accept: application/hal+json" \
  https://localhost:8080/api/people/search/by-last-name-and-active
~~~

Không tự nối chuỗi query mà không encode. Giá trị chứa `&` có thể bị hiểu nhầm thành tham số tiếp theo; dấu `+` trong query string cũng có thể được diễn giải thành dấu cách theo quy tắc form URL encoding.

## 9. Tên @Param là một phần của API contract

Khi client gọi query resource, tên key trong URL phải khớp với tên công bố bởi `@Param`.

Ví dụ:

~~~java
List<Person> findByCity(
        @Param("cityName") String city);
~~~

Client dùng:

~~~http
GET /api/people/search/findByCity?cityName=Hanoi
~~~

Nếu đổi annotation thành:

~~~java
List<Person> findByCity(
        @Param("city") String city);
~~~

thì query key mới là `city`. Các client vẫn gửi `cityName` cần được cập nhật. Việc đổi tên query parameter là thay đổi API contract dù tên method Java không thay đổi.

Để giảm rủi ro:

- Đặt tên ngắn gọn, rõ nghĩa và nhất quán.
- Dùng cùng convention camelCase cho query keys nếu API đang dùng camelCase.
- Giữ tên ổn định khi refactor biến Java.
- Khi cần đổi key, cân nhắc thời gian tương thích hoặc versioning cho client.
- Kiểm tra search resource sau khi export để xác nhận link template công bố đúng key.

## 10. Phân biệt @Param với các annotation khác

| Annotation | Nơi thường dùng | Mục đích |
|---|---|---|
| `@Param` | Tham số method repository Spring Data | Đặt tên tham số truy vấn, bao gồm query parameter được Spring Data REST công bố |
| `@RequestParam` | Tham số method Spring MVC controller | Bind HTTP request parameter vào controller argument |
| `@PathVariable` | Tham số method Spring MVC controller | Bind một biến trong URI path |
| `@RestResource` | Repository hoặc query method | Tùy chỉnh việc export, path và relation |
| `@RepositoryRestResource` | Repository interface | Tùy chỉnh resource path, relation và export của repository |

Không dùng `@RequestParam` trên repository query method chỉ vì giá trị đến từ query string. Repository method thuộc Spring Data; `@Param` là annotation đúng cho metadata tham số của repository. `@RequestParam` dành cho controller do ứng dụng viết.

## 11. Kiểm tra search resource và debug binding

Khi query method không nhận được tham số như mong đợi, hãy kiểm tra theo thứ tự:

1. Gửi GET tới collection search resource, ví dụ `/api/people/search`, để xem query method có được export không.
2. Theo đúng href của query method; kiểm tra path có được tùy chỉnh bằng `@RestResource(path = "...")` không.
3. Đọc URI template trong `_links`; phần `{?...}` cho biết các query key server công bố.
4. Đối chiếu từng key với `@Param("...")` trên repository method.
5. Kiểm tra các tham số đặc biệt `Pageable`/`Sort`; dùng `page`, `size`, `sort` theo quy ước.
6. Kiểm tra kiểu dữ liệu và định dạng giá trị; chú ý enum, ngày giờ, boolean và ID.
7. Encode các giá trị có ký tự đặc biệt.
8. Kiểm tra method có bị ẩn bằng `@RestResource(exported = false)` hoặc repository có bị tắt export không.
9. Nếu dùng `@Query`, đối chiếu `@Param` với named placeholder trong JPQL.
10. Đọc status code và error body. 404 có thể là path/query resource không tồn tại; 405 có thể là method không được export; 400 thường liên quan binding hoặc payload.

Ví dụ một method có hai tham số:

~~~java
@RestResource(path = "by-last-name-and-active")
Page<Person> findByLastNameAndActive(
        @Param("lastName") String lastName,
        @Param("active") Boolean active,
        Pageable pageable);
~~~

Search resource nên công bố link template tương tự:

~~~text
/api/people/search/by-last-name-and-active{?lastName,active,page,size,sort}
~~~

Nếu link thực tế không có `lastName` hoặc `active`, hãy kiểm tra metadata method và việc export thay vì tự đoán query key.

## 12. Ghi nhớ

- Query method được export của Spring Data REST nằm dưới `/search`.
- `@Param("name")` đặt tên query key mà client gửi; tên biến Java có thể khác.
- `@RestResource(path = "...")` đặt path của query resource; nó không đặt tên query parameter.
- `Pageable`/`Sort` dùng các key riêng như `page`, `size`, `sort`; không cần `@Param` cho các tham số đặc biệt này.
- Với JPQL `@Query`, tên `@Param` cần khớp named placeholder.
- Dữ liệu query string cần được encode và chuyển đổi đúng kiểu.
- Tên `@Param` là một phần của API contract; đổi tên có thể ảnh hưởng client.
- Dùng search resource và URI template do server công bố để xác nhận endpoint cùng query keys.

## Tài liệu tham khảo

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data Commons — Repository query method parameters](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data JPA — Using named parameters](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
