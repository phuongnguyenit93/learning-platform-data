# Kiểu trả về đơn, Optional, tập hợp, Page và Slice trong truy vấn tìm kiếm Spring Data REST

## Mục tiêu

Spring Data REST xuất các query method của repository thành các search resources có thể gọi bằng HTTP GET. Kiểu trả về của method quyết định hình dạng và lượng dữ liệu mà endpoint truy vấn cung cấp.

Năm kiểu thường gặp:

- **Entity đơn `T`**: truy vấn kỳ vọng tối đa một kết quả.
- **`Optional<T>`**: cũng là truy vấn đơn, nhưng biểu diễn rõ trường hợp không tìm thấy.
- **Collection** như `List<T>`, `Set<T>`: trả về nhiều kết quả trong một lần truy vấn.
- **`Page<T>`**: trả về một trang cùng thông tin tổng số phần tử và tổng số trang.
- **`Slice<T>`**: trả về một lát dữ liệu và cho biết còn trang tiếp theo hay không.

Chọn đúng kiểu trả về ảnh hưởng tới hợp đồng API, hiệu năng truy vấn và cách client xây dựng giao diện phân trang. Bài này dùng `PersonRepository` làm ví dụ và giải thích cả repository semantics lẫn representation HAL do Spring Data REST xuất ra.

## 1. Query method được xuất thành search resource

Giả sử repository được khai báo:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST xuất trang search tại:

~~~http
GET /api/people/search
Accept: application/hal+json
~~~

Trang search trả về các liên kết tới query method đã được export. Mỗi method có một query method resource riêng và được gọi bằng GET. Có thể tùy chỉnh path và relation của method bằng `@RestResource`.

Ví dụ:

~~~java
@RestResource(path = "by-username", rel = "byUsername")
Optional<Person> findByUsernameIgnoreCase(
        @Param("username") String username);
~~~

Link được công bố trên search resource có relation `byUsername`; client theo `href` của link đó để thực thi truy vấn:

~~~http
GET /api/people/search/by-username?username=lan
Accept: application/hal+json
~~~

Kiểu trả về không làm thay đổi nguyên tắc discoverability: search resource liệt kê link, query method resource thực thi truy vấn. Client nên sử dụng URL thực tế trong HAL thay vì tự ghép path từ tên Java method.

## 2. Ví dụ repository có nhiều kiểu trả về

Một repository có thể cung cấp các truy vấn với cardinality khác nhau:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-username", rel = "byUsername")
    Optional<Person> findByUsernameIgnoreCase(
            @Param("username") String username);

    @RestResource(path = "latest-active", rel = "latestActive")
    Person findFirstByActiveTrueOrderByCreatedAtDesc();

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findAllByLastNameIgnoreCase(
            @Param("lastName") String lastName);

    @RestResource(path = "by-status-page", rel = "byStatusPage")
    Page<Person> findByStatus(
            @Param("status") PersonStatus status,
            Pageable pageable);

    @RestResource(path = "by-city-slice", rel = "byCitySlice")
    Slice<Person> findByCity(
            @Param("city") String city,
            Pageable pageable);
}
~~~

Các import chính:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.rest.core.annotation.RestResource;
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
~~~

Ví dụ giả định các thuộc tính `username`, `active`, `createdAt`, `lastName`, `status` và `city` tồn tại trên domain type. Tùy store module, kiểu dữ liệu và toán tử query được hỗ trợ có thể khác nhau.

Không thể khai báo hai method Java chỉ khác kiểu trả về nhưng có cùng tên và cùng danh sách tham số. Nếu cần thử nhiều kiểu trả về cho cùng tiêu chí, đặt tên method khác nhau hoặc dùng repository riêng trong test.

## 3. Trả về một entity đơn: T

Khi method trả về trực tiếp domain type, Spring Data mong đợi truy vấn có tối đa một kết quả:

~~~java
Person findByUsername(String username);
~~~

Ngữ nghĩa ở tầng repository:

- Tìm thấy đúng một entity: trả về entity đó.
- Không tìm thấy: trả về `null`.
- Tìm thấy nhiều hơn một entity: phát sinh `IncorrectResultSizeDataAccessException`.

Vì vậy, kiểu `T` phù hợp khi tiêu chí truy vấn là duy nhất theo thiết kế dữ liệu, ví dụ username có unique constraint hoặc một mã định danh nghiệp vụ duy nhất.

Nếu truy vấn không bảo đảm duy nhất nhưng nghiệp vụ chỉ cần một kết quả đầu tiên, có thể dùng giới hạn `First` hoặc `Top`:

~~~java
Person findFirstByActiveTrueOrderByCreatedAtDesc();
~~~

Method này yêu cầu kết quả mới nhất trong nhóm active và giới hạn tối đa một bản ghi. Thứ tự phải được khai báo rõ để kết quả không phụ thuộc vào thứ tự mặc định của database.

Khi query method được xuất qua Spring Data REST, kết quả tìm được được biểu diễn như một tài nguyên đơn. Ví dụ minh họa HAL:

~~~json
{
  "id": 12,
  "username": "lan",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/12"
    }
  }
}
~~~

Không nên suy luận status code hoặc body cụ thể của trường hợp không có kết quả chỉ từ kiểu Java `T`. Hành vi HTTP còn chịu ảnh hưởng của phiên bản exporter và cách xử lý kết quả rỗng; hãy kiểm thử endpoint trên đúng ứng dụng đang chạy.

## 4. Trả về Optional<T>

`Optional<T>` biểu diễn truy vấn có thể không tìm thấy một entity:

~~~java
Optional<Person> findByUsernameIgnoreCase(String username);
~~~

Ngữ nghĩa repository:

- Có một kết quả: `Optional.of(person)`.
- Không có kết quả: `Optional.empty()`.
- Có nhiều kết quả: `IncorrectResultSizeDataAccessException`.

So với trả về `T`, Optional giúp code Java thể hiện rõ khả năng không có dữ liệu và buộc caller xử lý trường hợp rỗng. Nó không biến một truy vấn nhiều kết quả thành truy vấn hợp lệ; method vẫn phải có cardinality tối đa một.

Một endpoint tìm theo username phù hợp với Optional khi người dùng có thể nhập username không tồn tại:

~~~http
GET /api/people/search/by-username?username=lan
Accept: application/hal+json
~~~

Khi có kết quả, response chứa representation của Person tương ứng. Khi không có kết quả, repository trả `Optional.empty()`. Ở tầng HTTP, hãy xác định và kiểm thử status/body mà phiên bản Spring Data REST của ứng dụng thực sự trả về; đừng mặc định rằng mọi Optional rỗng luôn được chuyển thành cùng một status code ở mọi phiên bản.

Không dùng `Optional<List<Person>>` để diễn đạt một collection query thông thường. Với truy vấn nhiều kết quả, trả trực tiếp `List<Person>` hoặc một kiểu collection phù hợp; collection rỗng đã diễn tả trường hợp không có phần tử.

## 5. Trả về Collection: List, Set, Collection hoặc Iterable

Nếu truy vấn có thể trả về nhiều entity và không cần metadata phân trang, dùng kiểu collection:

~~~java
List<Person> findAllByLastNameIgnoreCase(String lastName);
~~~

Spring Data cũng hỗ trợ các kiểu Java như `Collection<T>`, `Iterable<T>`, `List<T>` và `Set<T>`, cùng một số abstraction như `Streamable<T>` và collection Vavr nếu store module hỗ trợ.

Ngữ nghĩa:

- Có kết quả: trả về các entity trong collection.
- Không có kết quả: trả về collection rỗng, ví dụ `List.of()` hoặc một list rỗng do framework tạo.
- Không có khái niệm tổng số trang hoặc link next/prev chỉ vì method trả về List.

Một query result nhiều phần tử được Spring Data REST biểu diễn như collection resource. Phản hồi HAL minh họa:

~~~json
{
  "_embedded": {
    "people": [
      {
        "id": 12,
        "username": "lan",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/12"
          }
        }
      },
      {
        "id": 18,
        "username": "minh",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/18"
          }
        }
      }
    ]
  }
}
~~~

Tên relation trong `_embedded` phụ thuộc vào cấu hình resource/domain type; ví dụ trên chỉ minh họa. Với kết quả rỗng, collection vẫn là kết quả của query method, nhưng phần `_embedded` có thể không chứa phần tử hoặc không xuất hiện tùy cách serialize.

**Lưu ý về dữ liệu lớn:** List thường tải toàn bộ kết quả vào bộ nhớ. Nếu truy vấn có thể trả về hàng nghìn hoặc hàng triệu bản ghi, hãy dùng Page hoặc Slice để giới hạn lượng dữ liệu trả về.

Một method nhận `Pageable` nhưng trả `List<T>` có thể giới hạn phần dữ liệu được lấy ở tầng repository, song không tạo đầy đủ metadata Page/Slice cho Spring Data REST. Để có các liên kết điều hướng và metadata phân trang trong API, khai báo kiểu trả về `Page<T>` hoặc `Slice<T>`.

## 6. Trả về Page<T>: trang có tổng số kết quả

`Page<T>` đại diện cho một trang kết quả và bổ sung thông tin về toàn bộ tập kết quả:

~~~java
Page<Person> findByStatus(PersonStatus status, Pageable pageable);
~~~

Method phải nhận `Pageable`. Spring Data dùng thông tin này để xác định offset, page size và sort.

Ví dụ gọi endpoint:

~~~http
GET /api/people/search/by-status-page?status=ACTIVE&page=0&size=20&sort=lastName,asc
Accept: application/hal+json
~~~

Các tham số phổ biến:

| Tham số | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `page` | Số thứ tự trang, bắt đầu từ 0 | `0` |
| `size` | Số phần tử yêu cầu trên mỗi trang | `20` |
| `sort` | Thuộc tính và hướng sắp xếp | Không có sort bổ sung |

Có thể truyền nhiều điều kiện sort bằng cách lặp lại tham số `sort`, ví dụ `sort=lastName,asc&sort=createdAt,desc`. Tên thuộc tính phải là property mà repository có thể sắp xếp; sorting trên linkable association không được hỗ trợ theo quy tắc Spring Data REST hiện hành.

Response HAL của Page thường có:

- `_embedded`: các entity trong trang hiện tại.
- `_links.self`: URL hoặc URI template của trang hiện tại.
- `_links.next`: trang tiếp theo nếu có.
- `_links.prev`: trang trước nếu có.
- `page.size`: kích thước trang.
- `page.totalElements`: tổng số phần tử của toàn bộ truy vấn.
- `page.totalPages`: tổng số trang.
- `page.number`: chỉ số trang hiện tại, bắt đầu từ 0.

Ví dụ rút gọn:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/search/by-status-page?status=ACTIVE{&page,size,sort}",
      "templated": true
    },
    "next": {
      "href": "http://localhost:8080/api/people/search/by-status-page?status=ACTIVE&page=1&size=20{&sort}",
      "templated": true
    }
  },
  "_embedded": {
    "people": [
      {
        "id": 12,
        "username": "lan"
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 47,
    "totalPages": 3,
    "number": 0
  }
}
~~~

Ở trang đầu không có link `prev`; ở trang cuối không có link `next`. Client nên theo các link này thay vì tự tính URL trang kế tiếp.

Để biết `totalElements` và `totalPages`, Spring Data thường cần chạy thêm count query. Count query có thể tốn kém với truy vấn phức tạp, join lớn hoặc datastore có chi phí đếm cao. Nếu client không cần tổng số kết quả, cân nhắc dùng Slice.

## 7. Trả về Slice<T>: một lát dữ liệu có thể đi tiếp

`Slice<T>` cũng cần `Pageable`, nhưng mục tiêu là cho biết còn dữ liệu tiếp theo hay không:

~~~java
Slice<Person> findByCity(String city, Pageable pageable);
~~~

Khác biệt chính:

- Slice biết có phần tiếp theo hay không thông qua `hasNext()`.
- Slice không cung cấp tổng số phần tử hoặc tổng số trang như Page.
- Spring Data thường đọc thêm một phần tử ngoài page size để xác định còn dữ liệu hay không.
- Không cần count query chỉ để tính tổng số bản ghi.

Ví dụ request:

~~~http
GET /api/people/search/by-city-slice?city=HCMC&page=0&size=20
Accept: application/hal+json
~~~

Spring Data REST nhận diện kết quả Page/Slice và thêm các link điều hướng `prev` và `next` khi phù hợp. Nội dung entity được biểu diễn tương tự collection result. Client không có tổng số trang để hiển thị kiểu “trang 1 trên 12”, nhưng có thể hiển thị nút “Tiếp theo” khi link `next` có mặt.

Dùng Slice phù hợp cho:

- Danh sách cuộn liên tục (infinite scroll).
- Giao diện chỉ cần nút tải thêm.
- Batch processing duyệt tuần tự theo từng lát.
- Truy vấn lớn mà count query không cần thiết.

Với phân trang offset, trang ở offset rất lớn vẫn có thể chậm vì database phải xử lý lượng bản ghi trước offset. Nếu hệ thống cần duyệt dữ liệu lớn và liên tục, cân nhắc keyset/scrolling query hoặc cursor-based approach mà store hỗ trợ.

## 8. So sánh nhanh năm kiểu trả về

| Kiểu trả về | Số kết quả dự kiến | Không tìm thấy | Thông tin điều hướng | Chi phí đáng chú ý |
| --- | --- | --- | --- | --- |
| `T` | Tối đa một | `null` | Không có Page/Slice links | Truy vấn đơn |
| `Optional<T>` | Tối đa một | `Optional.empty()` | Không có Page/Slice links | Truy vấn đơn |
| `List<T>` / Collection | Không giới hạn theo kiểu trả về | Collection rỗng | Không có metadata Page/Slice | Có thể tải toàn bộ kết quả |
| `Page<T>` | Một trang | Page rỗng | Có next/prev và total metadata | Có thể cần count query |
| `Slice<T>` | Một lát | Slice rỗng | Có next/prev khi phù hợp | Thường lấy thêm một phần tử để biết hasNext |

Chọn theo nhu cầu client:

- Cần một bản ghi duy nhất theo key/username/email: `T` hoặc `Optional<T>`.
- Cần danh sách nhỏ, có giới hạn tự nhiên: `List<T>`.
- Cần tổng số bản ghi và tổng số trang: `Page<T>`.
- Chỉ cần biết còn dữ liệu để tải tiếp: `Slice<T>`.

## 9. Search resource và URI template phân trang

Spring Data REST có hai cấp liên kết:

1. Search resource liệt kê các query method được export.
2. Query method resource thực thi truy vấn cụ thể.

Ví dụ:

~~~http
GET /api/people/search
Accept: application/hal+json
~~~

Phản hồi có thể chứa:

~~~json
{
  "_links": {
    "byUsername": {
      "href": "http://localhost:8080/api/people/search/by-username{?username}",
      "templated": true
    },
    "byStatusPage": {
      "href": "http://localhost:8080/api/people/search/by-status-page{?status,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Một query method nhận `Pageable` và trả Page/Slice sẽ có URI template chứa tham số phân trang. Client cần mở rộng template bằng giá trị tham số phù hợp hoặc sử dụng HAL client để điều hướng.

Query method resource là read-only và hỗ trợ GET. Nếu một repository không có query method nào được export, search resource có thể không khả dụng; Spring Data REST trả 404 cho HEAD search resource khi không có query method resource nào.

## 10. Giới hạn số lượng và sắp xếp kết quả

Ngoài Page/Slice, Spring Data hỗ trợ giới hạn kết quả bằng `First`, `Top` hoặc `Limit`:

~~~java
Person findFirstByOrderByCreatedAtDesc();

List<Person> findTop10ByStatusOrderByCreatedAtDesc(PersonStatus status);

Slice<Person> findTop3ByStatus(PersonStatus status, Pageable pageable);
~~~

`First` và `Top` có thể dùng thay thế nhau. Nếu không ghi số lượng, giới hạn mặc định là 1. Có thể kết hợp giới hạn với Pageable; giới hạn tổng số kết quả trước, còn Pageable có thể giảm lượng dữ liệu trong từng lần truy vấn.

Không kết hợp `Pageable` với `Sort` hoặc `Limit` trong cùng một method vì Pageable đã chứa sort và giới hạn trang. Nếu chỉ cần sắp xếp, dùng `Sort`:

~~~java
List<Person> findByCity(String city, Sort sort);
~~~

Ví dụ sort động qua URL:

~~~http
GET /api/people/search/by-city?city=HCMC&sort=lastName,asc&sort=createdAt,desc
~~~

Sort property phải là thuộc tính hợp lệ của domain model. Kiểm tra cấu hình expose và các quy tắc sort của store module trước khi công bố cho client.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Truy vấn đơn phát sinh lỗi nhiều kết quả | Method trả về T/Optional nhưng điều kiện không duy nhất | Thêm unique constraint, đổi sang collection hoặc dùng First/Top nếu nghiệp vụ cho phép. |
| Optional rỗng nhưng client xử lý sai | Client giả định một status/body cố định | Kiểm thử response HTTP thực tế theo phiên bản Spring Data REST và xử lý kết quả rỗng rõ ràng. |
| List quá lớn làm chậm hoặc tốn bộ nhớ | Method trả về toàn bộ kết quả | Dùng Page hoặc Slice và yêu cầu Pageable. |
| Page query chậm | Count query tốn kém | Đổi sang Slice nếu không cần total count; tối ưu query/index nếu cần Page. |
| Không thấy link next | Đang ở lát/trang cuối hoặc method không trả Page/Slice | Kiểm tra return type, Pageable và số lượng dữ liệu còn lại. |
| Page không nhận page/size/sort | Method thiếu Pageable hoặc URI không chứa template | Thêm Pageable và trả Page/Slice; kiểm tra link trên search resource. |
| GET search trả 404 | Không có query method được export hoặc method bị ẩn | Kiểm tra repository method, @RestResource và cấu hình export. |
| Query đơn trả IncorrectResultSizeDataAccessException | Dữ liệu có nhiều dòng phù hợp | Sửa tính duy nhất hoặc dùng kiểu collection. |

## 12. Kiểm thử query method resource

Nên kiểm tra cả response HTTP, nội dung representation và trạng thái dữ liệu. Ví dụ với Page:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonSearchResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void pageQueryExposesPageMetadata() throws Exception {
        mockMvc.perform(get("/api/people/search/by-status-page")
                .param("status", "ACTIVE")
                .param("page", "0")
                .param("size", "10")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.size").value(10))
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$._links.self.href").exists());
    }
}
~~~

Ví dụ kiểm tra collection result:

~~~java
mockMvc.perform(get("/api/people/search/by-last-name")
        .param("lastName", "Nguyen")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk());
~~~

Với Slice, tạo fixture có nhiều hơn một trang rồi kiểm tra link `next` ở trang đầu và trạng thái không còn link tiếp theo ở lát cuối. Với Optional, kiểm thử riêng trường hợp tìm thấy và không tìm thấy; không dựa vào giả định về status code khi chưa xác nhận behavior của phiên bản đang dùng.

Ngoài MockMvc, nên có repository integration test cho:

- Query đơn có 0, 1 và nhiều kết quả.
- Collection rỗng và collection có dữ liệu.
- Page ở trang đầu, trang giữa và trang cuối.
- Slice có và không có phần tiếp theo.
- Tham số sort hợp lệ và không hợp lệ.
- Query giới hạn bằng First/Top.

## 13. Lưu ý hiệu năng và khả năng hỗ trợ của store

Các kiểu trả về chung được Spring Data hỗ trợ, nhưng danh sách chính xác phụ thuộc store module. Hãy kiểm tra tài liệu Spring Data JPA, MongoDB, JDBC, Redis hoặc module thực tế của dự án.

Một số lưu ý:

- `List<T>` và `Streamable<T>` thường cần toàn bộ kết quả; có thể tốn bộ nhớ.
- `Stream<T>` có thể giữ tài nguyên datastore như cursor hoặc ResultSet. Phải đóng stream, thường bằng try-with-resources; không phải module nào cũng hỗ trợ.
- `Page<T>` cần tổng số kết quả để tạo total metadata; count query có thể là phần tốn kém.
- `Slice<T>` chỉ cần xác định có dữ liệu tiếp theo, phù hợp khi không cần tổng số trang.
- Offset paging có thể chậm ở offset lớn; cân nhắc scrolling/keyset nếu store hỗ trợ.
- Reactive return types như `Mono<T>` và `Flux<T>` thuộc repository reactive; không thay thế tùy tiện cho Page/Slice trong repository imperative.

Không chọn kiểu trả về chỉ theo sở thích Java. Hãy cân nhắc kích thước dữ liệu, nhu cầu UI, khả năng của datastore và chi phí query.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): search resource, query method resource, GET result và media types.
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): dùng Pageable với Page/Slice, liên kết prev/next và metadata trang.
- [Spring Data Commons — Defining Query Methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): collection return types, Pageable, Page, Slice, giới hạn và hiệu năng truy vấn.
- [Spring Data JPA — Repository query return types](https://docs.spring.io/spring-data/jpa/reference/repositories/query-return-types-reference.html): ngữ nghĩa T, Optional, Collection, Page, Slice và các kiểu trả về được hỗ trợ.
