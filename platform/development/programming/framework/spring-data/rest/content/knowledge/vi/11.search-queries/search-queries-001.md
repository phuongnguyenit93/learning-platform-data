# Tài nguyên /search và cơ chế khám phá các phương thức truy vấn trong Spring Data REST

## Mục tiêu

Spring Data REST có thể xuất bản các query method của Spring Data Repository thành các endpoint REST có thể khám phá. Với một repository đã export, client thường tìm các endpoint truy vấn thông qua tài nguyên \`/search\`.

Cần nắm ba lớp liên quan:

- **Search resource:** điểm vào để khám phá các truy vấn được export của một repository, thường ở URI \`/people/search\`.
- **Search method resource:** endpoint đại diện cho một query method cụ thể, ví dụ \`/people/search/findByLastName\`.
- **HAL link:** relation và href mà server công bố để client tìm endpoint search và gọi truy vấn mà không phải tự đoán URI.

Tài nguyên \`/search\` không tự tạo ra truy vấn tùy ý trên database. Nó là nơi công bố những query method mà repository đã khai báo và Spring Data REST cho phép export. Nếu repository không có query method được export, search resource có thể không có link tới phương thức nào.

Bài này trình bày cách search resource được tạo, cách method trở thành endpoint, cách truyền tham số, cách tùy chỉnh tên relation/path, cách dùng phân trang và sorting, và cách client khám phá API qua HAL.

## 1. Search resource nằm ở đâu?

Giả sử repository được export:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Với base path là \`/api\`, collection resource có URI:

~~~text
/api/people
~~~

Search resource được đặt dưới collection resource:

~~~text
/api/people/search
~~~

Khi client gọi collection:

~~~http
GET /api/people
Accept: application/hal+json
~~~

response có thể chứa link \`search\`:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people"
    },
    "search": {
      "href": "http://localhost:8080/api/people/search"
    }
  }
}
~~~

Relation \`search\` cho biết repository có search resource để khám phá các query endpoint. Client theo href này để đọc các search link chi tiết.

Không nên ghép cứng \`/search\` trong client nếu API đã công bố relation. Base path, collection path hoặc cấu hình URL có thể thay đổi; HAL link là nguồn URI do server công bố.

## 2. Khai báo một query method trong repository

Spring Data hỗ trợ derived query method dựa trên tên phương thức. Ví dụ:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

Để Spring Data REST công bố phương thức như một search endpoint, method phải là query method phù hợp và được export. Thông thường nên khai báo rõ tên query parameter bằng \`@Param\`:

~~~java
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("name") String lastName);
}
~~~

Với repository trên, Spring Data REST có thể tạo search method resource dưới search resource. URI mặc định dựa trên tên method, ví dụ:

~~~text
/api/people/search/findByLastName
~~~

Client gọi truy vấn bằng query parameter:

~~~http
GET /api/people/search/findByLastName?name=Lovelace
Accept: application/hal+json
~~~

Spring Data chuyển giá trị \`name\` tới tham số method và thực thi truy vấn. Nếu có kết quả, response biểu diễn các Person phù hợp; nếu không có kết quả, search endpoint vẫn tồn tại và có thể trả collection representation rỗng.

### Vì sao dùng @Param?

\`@Param("name")\` xác định tên query parameter công khai của endpoint. Tên tham số Java như \`lastName\` không nhất thiết là tên mà client phải gửi. Dùng \`@Param\` giúp hợp đồng HTTP rõ ràng và không phụ thuộc việc compiler có lưu thông tin tên parameter hay không.

Ví dụ:

| Khai báo method | Query parameter client gửi |
|---|---|
| \`findByLastName(@Param("name") String lastName)\` | \`?name=Lovelace\` |
| \`findByAgeGreaterThan(@Param("minAge") int age)\` | \`?minAge=30\` |
| \`findByStatus(@Param("status") PersonStatus status)\` | \`?status=ACTIVE\` |

Tên trong \`@Param\` là một phần hợp đồng API. Khi đổi tên, cần cân nhắc ảnh hưởng tới client đang gọi endpoint.

## 3. Khám phá các search method qua HAL

Khi gọi search resource:

~~~http
GET /api/people/search
Accept: application/hal+json
~~~

Spring Data REST có thể trả representation như:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/search"
    },
    "findByLastName": {
      "href": "http://localhost:8080/api/people/search/findByLastName{?name}",
      "templated": true
    },
    "findByStatus": {
      "href": "http://localhost:8080/api/people/search/findByStatus{?status}",
      "templated": true
    }
  }
}
~~~

Đây là ví dụ minh họa khi repository export hai query method. Link thực tế phụ thuộc tên method, annotation và phiên bản/cấu hình.

Các phần quan trọng:

- \`self\` trỏ tới chính search resource.
- \`findByLastName\` là relation cho một search method.
- \`href\` là URI template có biến query parameter.
- \`templated: true\` cho biết client cần mở rộng template trước khi gửi request.

Client không cần biết repository có bao nhiêu method hoặc tên URL của từng method từ trước. Nó có thể lấy danh sách relation trong \`_links\`, chọn relation phù hợp và mở rộng href tương ứng.

### Search resource có thể rỗng

Nếu repository không có query method nào được export, search resource có thể không xuất hiện hoặc không có các link method cụ thể, tùy cấu hình và phiên bản. Client nên kiểm tra link \`search\` ở collection trước, sau đó kiểm tra các relation thực tế trong response search.

Không nên giả định mọi repository đều có \`findById\`, \`findAll\` hoặc một search method tùy ý dưới \`/search\`. Các thao tác CRUD chuẩn có resource riêng; search resource dành cho các query method được công bố.

## 4. Tùy chỉnh tên relation và URI của search method

Có thể dùng \`@RestResource\` trên query method để tùy chỉnh path và relation:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastName(@Param("name") String lastName);
}
~~~

Với cấu hình này, search method endpoint có thể dùng path:

~~~text
/api/people/search/by-last-name?name=Lovelace
~~~

và search representation công bố relation:

~~~json
{
  "_links": {
    "byLastName": {
      "href": "http://localhost:8080/api/people/search/by-last-name{?name}",
      "templated": true
    }
  }
}
~~~

Hai thuộc tính có ý nghĩa khác nhau:

| Thuộc tính | Vai trò | Ví dụ |
|---|---|---|
| \`path\` | Segment URI của endpoint search method. | \`by-last-name\` |
| \`rel\` | Tên relation trong HAL mà client dùng để nhận diện link. | \`byLastName\` |

Đổi \`rel\` không nhất thiết đổi URL. Đổi \`path\` làm thay đổi endpoint URI. Client hypermedia nên đọc href từ response thay vì giả định relation và path giống nhau.

### Ẩn một query method

Nếu một query method không nên được công bố qua REST, có thể đánh dấu:

~~~java
@RestResource(exported = false)
List<Person> findByInternalFlagTrue();
~~~

Method này không được export thành search endpoint. Relation tương ứng sẽ không được công bố trong search resource. Việc ẩn endpoint giúp quản lý bề mặt API, nhưng không thay thế authorization cho các đường truy cập khác tới dữ liệu.

## 5. Truyền tham số truy vấn

Tham số của search method được truyền qua query string. Spring Data REST dùng tên \`@Param\` để ánh xạ request parameter tới method argument.

Ví dụ:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("name") String lastName);

    List<Person> findByAgeGreaterThan(
        @Param("minAge") int age
    );

    List<Person> findByStatusAndLastName(
        @Param("status") PersonStatus status,
        @Param("name") String lastName
    );
}
~~~

Các request tương ứng:

~~~http
GET /api/people/search/findByLastName?name=Lovelace
~~~

~~~http
GET /api/people/search/findByAgeGreaterThan?minAge=30
~~~

~~~http
GET /api/people/search/findByStatusAndLastName?status=ACTIVE&name=Lovelace
~~~

Spring chuyển đổi giá trị query string sang kiểu Java của method argument. Ví dụ chuỗi \`30\` thành \`int\`, \`ACTIVE\` thành enum \`PersonStatus\`, nếu converter tương ứng hỗ trợ.

Nếu tham số thiếu, sai định dạng hoặc không chuyển đổi được, request có thể thất bại với lỗi 400 hoặc lỗi chuyển đổi được xử lý theo exception handling của ứng dụng.

### Tham số bắt buộc và tùy chọn

Cách method được khai báo quyết định cách Spring Data xử lý argument. Nếu method cần một giá trị để thực thi truy vấn, client nên gửi parameter tương ứng. Không nên coi việc bỏ query parameter là truy vấn không giới hạn, trừ khi chữ ký method và query semantics cho phép điều đó.

Với nhiều tham số, mỗi \`@Param\` nên có tên duy nhất và được ghi rõ trong tài liệu API.

## 6. Kết hợp search với phân trang và sorting

Một query method có thể trả về \`Page<T>\` và nhận \`Pageable\`:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.query.Param;

public interface PersonRepository extends JpaRepository<Person, Long> {

    Page<Person> findByLastName(
        @Param("name") String lastName,
        Pageable pageable
    );
}
~~~

Client có thể gọi:

~~~http
GET /api/people/search/findByLastName?name=Lovelace&page=0&size=10&sort=firstName,asc
Accept: application/hal+json
~~~

Các query parameter thường dùng:

| Parameter | Ý nghĩa |
|---|---|
| \`page\` | Chỉ số trang, thường bắt đầu từ 0. |
| \`size\` | Số phần tử tối đa trong trang. |
| \`sort\` | Thuộc tính và chiều sắp xếp, ví dụ \`firstName,asc\`. |

Khi method trả về \`Page<T>\`, response có thể chứa collection representation với \`_embedded\`, \`_links\` và metadata \`page\`, gồm \`size\`, \`totalElements\`, \`totalPages\`, \`number\`.

Nếu method trả \`List<T>\`, response có thể là collection kết quả nhưng không nhất thiết có metadata phân trang của \`Page\`. Chọn kiểu trả về theo nhu cầu client và chi phí truy vấn.

### Search kết quả rỗng

Nếu query hợp lệ nhưng không tìm thấy bản ghi, endpoint search vẫn tồn tại. Response thường là collection rỗng với status 200. Client cần phân biệt trường hợp này với:

- Search method không được export hoặc URL sai: có thể 404.
- Query parameter không hợp lệ: có thể 400.
- Không đủ quyền: có thể 401/403 hoặc bị che giấu bởi security.
- Method HTTP không được hỗ trợ: có thể 405.

## 7. Search method và các kiểu truy vấn của Spring Data

Spring Data REST export các query method được Spring Data repository nhận diện và có thể công bố. Các query method thường đến từ:

- **Derived query:** Spring Data suy ra điều kiện từ tên method, ví dụ \`findByLastName\`, \`findByStatusAndAgeGreaterThan\`.
- **Declared query:** method dùng \`@Query\` để khai báo JPQL, SQL hoặc query theo module store.
- **Named query:** query được định nghĩa bằng cơ chế named query của module đang dùng.

Ví dụ derived query:

~~~java
List<Person> findByStatusAndAgeGreaterThan(
    @Param("status") PersonStatus status,
    @Param("minAge") int age
);
~~~

Ví dụ declared query với JPA:

~~~java
@Query("select p from Person p where lower(p.lastName) = lower(:name)")
List<Person> searchByLastNameIgnoreCase(@Param("name") String name);
~~~

Khi query method được export, Spring Data REST có thể tạo endpoint search tương ứng. Cách query được thực thi do Spring Data repository và store module đảm nhiệm; Spring Data REST cung cấp lớp HTTP resource và representation.

Không phải mọi method tùy ý trong interface đều trở thành endpoint. Method phải được Spring Data nhận diện là query method phù hợp, được phép export và không bị ẩn bởi annotation/cấu hình.

## 8. Search resource không phải API truy vấn tùy ý

Search resource là tập hợp các endpoint đã được khai báo. Nó không cho phép client gửi tên bảng, tên cột hoặc biểu thức SQL tùy ý.

Ví dụ, client không thể tự gọi một URI giả định như:

~~~text
/api/people/search?where=age%3E30
~~~

rồi mong Spring Data REST tự hiểu một query tổng quát, trừ khi ứng dụng chủ động định nghĩa một query method hoặc custom endpoint hỗ trợ cú pháp đó.

Thiết kế query method có lợi ích:

- Server kiểm soát điều kiện truy vấn được phép.
- Query parameter có kiểu dữ liệu và tên rõ ràng.
- API có thể khám phá qua HAL.
- Authorization và validation có thể áp dụng theo từng use case.
- Client không phải gửi cấu trúc truy vấn nội bộ của database.

Nếu cần tìm kiếm linh hoạt với nhiều bộ lọc kết hợp, hãy thiết kế custom controller/service hoặc một search model rõ ràng, giới hạn các trường và toán tử được phép, thay vì mở endpoint nhận truy vấn tùy ý.

## 9. Khám phá và gọi search bằng curl

Lấy collection để tìm link search:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people
~~~

Lấy danh sách search method:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/search
~~~

Gọi method tìm theo last name:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "name=Lovelace" \
  http://localhost:8080/api/people/search/findByLastName
~~~

Gọi method phân trang:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "name=Lovelace" \
  --data-urlencode "page=0" \
  --data-urlencode "size=10" \
  --data-urlencode "sort=firstName,asc" \
  http://localhost:8080/api/people/search/findByLastName
~~~

Dùng \`--data-urlencode\` giúp client mã hóa ký tự đặc biệt trong query parameter. Khi viết client thực tế, nên dùng URI builder thay vì nối chuỗi thủ công.

## 10. Từ HAL link tới request: quy trình client

Một client hypermedia có thể thực hiện theo trình tự:

1. Gọi API entry point hoặc collection resource.
2. Tìm relation \`search\` trong \`_links\`.
3. Theo href để mở search resource.
4. Đọc các relation đại diện cho query method.
5. Chọn relation phù hợp với tác vụ.
6. Mở rộng URI template bằng các query parameter tương ứng.
7. Gửi GET tới href đã mở rộng.
8. Đọc collection, item hoặc page representation được trả về.
9. Nếu response có link phân trang, theo \`next\` hoặc \`prev\` để điều hướng tiếp.

Ví dụ search representation có link:

~~~json
{
  "_links": {
    "findByLastName": {
      "href": "http://localhost:8080/api/people/search/findByLastName{?name}",
      "templated": true
    }
  }
}
~~~

Client mở rộng biến \`name\` với giá trị \`Lovelace\` rồi gửi request. Trong ứng dụng Java, Spring HATEOAS có các abstraction hỗ trợ đọc link và mở rộng URI template. Với client khác, dùng thư viện URI template hoặc URI builder phù hợp.

Client không nên giả định query method luôn được đặt tên theo convention mặc định. Annotation \`@RestResource\` có thể đổi relation/path, vì vậy hãy dùng relation và href thực tế.

## 11. Bảo mật và kiểm soát query endpoint

Một query method được export có thể cho phép client đọc tập dữ liệu theo tiêu chí của method. Cần kiểm soát những dữ liệu nào được công bố:

- Không export query method chỉ dùng nội bộ.
- Dùng \`@RestResource(exported = false)\` để ẩn method không cần public.
- Dùng Spring Security để kiểm soát quyền đọc theo URI, method và principal.
- Kiểm tra query có thể tiết lộ dữ liệu nhạy cảm hoặc cho phép dò tìm quá rộng không.
- Giới hạn page size và tránh query gây tải lớn.
- Dùng validation cho tham số đầu vào và kiểu dữ liệu.
- Không coi việc không xuất hiện link trong HAL là một ranh giới bảo mật.

Một endpoint search GET vẫn có thể bị gọi trực tiếp nếu URI bị lộ. Server phải kiểm tra authorization ở request thực tế, không chỉ ẩn relation trong response.

## 12. Những lỗi thường gặp

1. **Không thấy link \`search\` trong collection response.** Kiểm tra repository có được export không, representation đang dùng và search resource có được công bố không.
2. **Search resource tồn tại nhưng không có method link.** Kiểm tra repository có query method phù hợp và method đó có bị \`exported = false\` không.
3. **Gọi tên method nhưng nhận 404.** Kiểm tra relation/path tùy chỉnh bằng \`@RestResource\`; tên method mặc định có thể không còn là URL thực tế.
4. **Gửi sai tên query parameter.** Dùng tên trong \`@Param\`, không đoán từ tên biến Java.
5. **Không chuyển đổi được enum hoặc số.** Kiểm tra kiểu parameter, giá trị query string và converter.
6. **Dùng sai URI template.** Nếu link có \`templated: true\`, mở rộng biến trước khi gửi request.
7. **Nhầm query không có kết quả với endpoint không tồn tại.** Endpoint hợp lệ có thể trả collection rỗng; endpoint không export có thể trả 404.
8. **Không có metadata phân trang.** Kiểm tra method trả \`Page<T>\` hay \`List<T>\`, và method có nhận \`Pageable\` không.
9. **Page size quá lớn.** Kiểm tra giới hạn page size của REST exporter và đọc metadata response.
10. **Lộ query method nội bộ.** Kiểm tra export configuration và security policy cho từng method.

## 13. Checklist chẩn đoán

Khi search endpoint không hoạt động, kiểm tra theo thứ tự:

1. Repository collection resource có được export và truy cập được không?
2. Collection response có relation \`search\` không?
3. \`GET /search\` có trả về các method relation không?
4. Query method có được Spring Data nhận diện và có được export không?
5. Có annotation \`@RestResource(path=..., rel=...)\` tùy chỉnh endpoint không?
6. Tên parameter client gửi có khớp với \`@Param\` không?
7. Kiểu giá trị có chuyển đổi được sang kiểu Java không?
8. Method trả về \`Page\`, \`List\` hay một kiểu khác?
9. Nếu dùng \`Pageable\`, client có gửi page/size/sort phù hợp không?
10. Security có cho principal gọi search method không?
11. Có giới hạn page size hoặc query nào làm thay đổi kết quả không?

Khi debug, lưu request URI, query string, Accept header, status code, response headers và HAL body. So sánh response collection với response search resource để xác định lỗi nằm ở repository export, method export, parameter binding hay query execution.

## Tóm tắt

Search resource \`/search\` là điểm khám phá các query method được Spring Data REST export cho một repository. Collection thường công bố relation \`search\`; search resource tiếp tục công bố relation cho từng method, với href có thể là URI template. Client đọc relation, mở rộng href bằng query parameter và gửi GET để thực thi truy vấn.

Query method được định nghĩa trong repository, có thể là derived query hoặc declared query. \`@Param\` đặt tên parameter công khai; \`@RestResource\` tùy chỉnh relation/path hoặc ẩn method bằng \`exported = false\`. Method trả về \`Page<T>\` có thể cung cấp metadata và link phân trang, trong khi method trả \`List<T>\` thường chỉ biểu diễn danh sách kết quả.

Hãy để client khám phá endpoint qua HAL, kiểm soát rõ query method được export và bảo vệ mọi search request bằng security/validation ở server.

## Tài liệu tham khảo

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Repository Resources and Search](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data Commons — Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
