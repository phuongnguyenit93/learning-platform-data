# Công bố derived query method thành tài nguyên chỉ đọc

## Mục tiêu

Spring Data REST có thể tự động công bố các query method của repository thành search resource. Với một derived query method, Spring Data phân tích tên method để tạo truy vấn từ tên thuộc tính và điều kiện. Spring Data REST cung cấp endpoint HTTP `GET` để client gọi truy vấn đó mà không cần viết Controller riêng.

Một search resource là tài nguyên chỉ đọc: client gửi điều kiện qua query parameter và nhận kết quả truy vấn. Việc công bố search method không tự tạo endpoint ghi dữ liệu cho method đó. Tuy nhiên, repository vẫn có thể có collection và item resource với các thao tác POST, PUT, PATCH hoặc DELETE nếu các thao tác CRUD tương ứng đang được export.

## 1. Derived query method là gì?

Derived query method là phương thức repository có tên tuân theo quy ước của Spring Data. Spring phân tích tên method để xác định thuộc tính, toán tử và thứ tự sắp xếp cần dùng.

Ví dụ:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);

    List<Person> findByActiveTrue();

    List<Person> findByAgeGreaterThan(int age);

    Optional<Person> findByEmailIgnoreCase(String email);
}
~~~

Spring Data suy ra các điều kiện tương ứng:

- `findByLastName`: so khớp thuộc tính `lastName`.
- `findByActiveTrue`: chỉ lấy entity có `active = true`.
- `findByAgeGreaterThan`: lọc entity có `age` lớn hơn giá trị truyền vào.
- `findByEmailIgnoreCase`: so khớp email không phân biệt chữ hoa/chữ thường.

Các tên method này là quy tắc truy vấn của Spring Data, không phải tên URL mà client nhất thiết phải gọi. Spring Data REST tạo search URI dựa trên repository và cấu hình export của method.

## 2. Spring Data REST công bố search resource

Khi query method được export, Spring Data REST đặt nó dưới đường dẫn `search` của collection resource. Ví dụ repository có collection path là `people`, search resource có dạng:

~~~text
/people/search/{search-method}
~~~

Nếu khai báo:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByLastName(String lastName);
}
~~~

Spring Data REST có thể công bố method với đường dẫn mặc định dựa trên tên method, chẳng hạn:

~~~http
GET /people/search/findByLastName?lastName=Nguyen
~~~

Request này gọi finder `findByLastName` và trả về danh sách Person phù hợp. Endpoint được gọi bằng HTTP GET, nên client không gửi một lệnh cập nhật entity qua search resource.

Các finder được export còn xuất hiện trong liên kết `search` của collection representation HAL. Client nên khám phá liên kết do server trả về thay vì ghép URL theo giả định:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "search": {
      "href": "http://localhost:8080/people/search"
    }
  }
}
~~~

Khi GET vào search resource, server cung cấp các liên kết đến từng finder được export và URI template cho các parameter mà method cần.

## 3. Đặt tên URL và relation bằng @RestResource

Có thể dùng `@RestResource` trên query method để đặt tên path và relation rõ ràng, ổn định hơn tên Java method:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "by-last-name")
    List<Person> findByLastName(
        @Param("lastName") String lastName);
}
~~~

Client gọi:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
Accept: application/hal+json
~~~

Hai thuộc tính có ý nghĩa riêng:

- `path`: phần đường dẫn của search endpoint.
- `rel`: tên relation được công bố trong liên kết HAL của search resource.

Đặt path bằng tên nghiệp vụ giúp API dễ đọc và giảm phụ thuộc vào cách đặt tên method trong Java. Nếu đổi tên method nhưng giữ nguyên path và rel, client có thể tiếp tục dùng cùng endpoint.

Không nên đặt path search trùng với item path hoặc một search method khác trong cùng repository. Hãy giữ các finder dưới namespace `/search` và chọn path duy nhất, có ý nghĩa.

## 4. Đặt tên query parameter bằng @Param

Dùng `@Param` để xác định tên parameter mà client gửi trên URL:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "by-last-name")
    List<Person> findByLastName(
        @Param("lastName") String value);
}
~~~

Method dùng biến Java tên `value`, nhưng tên công khai trên URL là `lastName` vì được khai báo trong `@Param`.

Request:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
~~~

Khi có nhiều tham số:

~~~java
@RestResource(path = "by-name-and-status", rel = "by-name-and-status")
List<Person> findByLastNameAndActive(
    @Param("lastName") String lastName,
    @Param("active") boolean active);
~~~

Client gửi cả hai parameter:

~~~http
GET /people/search/by-name-and-status?lastName=Nguyen&active=true
~~~

Tên parameter trong request phải khớp với tên đã công bố. Giá trị trên URL được chuyển đổi sang kiểu Java tương ứng; nếu giá trị không hợp lệ với kiểu đích, request có thể thất bại ở bước conversion.

## 5. Phân trang và sắp xếp cho search resource

Nếu finder trả về `Page<T>` và nhận `Pageable`, client có thể dùng các parameter phân trang và sort chuẩn của Spring Data REST:

~~~java
@RestResource(path = "by-last-name", rel = "by-last-name")
Page<Person> findByLastNameIgnoreCase(
    @Param("lastName") String lastName,
    Pageable pageable);
~~~

Request:

~~~http
GET /people/search/by-last-name?lastName=nguyen&page=0&size=20&sort=firstName,asc
Accept: application/hal+json
~~~

Các parameter thường dùng:

- `page`: số trang, bắt đầu từ 0.
- `size`: số phần tử yêu cầu trong một trang.
- `sort`: tên thuộc tính và hướng sắp xếp, ví dụ `firstName,asc` hoặc `createdAt,desc`.

Có thể truyền nhiều tiêu chí sort bằng cách lặp lại parameter `sort`. Kích thước trang mặc định và giới hạn tối đa có thể được điều chỉnh trong cấu hình Spring Data REST. Client nên tôn trọng các giới hạn server áp dụng.

Nếu không cần metadata phân trang, finder có thể trả về `List<T>`. Chọn kiểu trả về theo nhu cầu API: `Page<T>` hữu ích khi client cần thông tin trang và tổng số kết quả; `List<T>` phù hợp với tập kết quả nhỏ hoặc không cần phân trang.

## 6. Các kiểu trả về thường gặp

Một derived query method có thể trả về nhiều kiểu kết quả được Spring Data hỗ trợ:

| Kiểu trả về | Ý nghĩa |
|---|---|
| `List<Person>` hoặc `Collection<Person>` | Danh sách kết quả |
| `Page<Person>` | Kết quả có phân trang và metadata |
| `Slice<Person>` | Một lát dữ liệu, hữu ích khi không cần tổng số phần tử |
| `Optional<Person>` | Không hoặc một kết quả |
| `Person` | Một kết quả đơn, nếu truy vấn bảo đảm tối đa một kết quả |
| `long` hoặc `boolean` | Kết quả tổng hợp hoặc kiểm tra tồn tại, tùy query method |

Chọn kiểu trả về tương ứng với số lượng kết quả mà điều kiện truy vấn có thể tạo ra. Nếu method có thể trả nhiều entity, không nên khai báo kiểu đơn có thể gây lỗi khi có nhiều kết quả. Với dữ liệu lớn, ưu tiên phân trang thay vì trả toàn bộ danh sách.

## 7. Chỉ công bố finder cần thiết

Theo mặc định, Spring Data REST có thể export các query method đủ điều kiện trên repository. Có thể đổi path/rel của method hoặc tắt export riêng một finder bằng `@RestResource(exported = false)`:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "by-last-name")
    List<Person> findByLastName(
        @Param("lastName") String lastName);

    @RestResource(exported = false)
    List<Person> findByInternalReviewStatus(String status);
}
~~~

Trong ví dụ:

- `findByLastName` được công bố dưới `/people/search/by-last-name`.
- `findByInternalReviewStatus` không được công bố thành search endpoint.

Ẩn một finder là lựa chọn hữu ích khi method chỉ phục vụ nội bộ, chứa điều kiện không dành cho client hoặc chưa phải một phần của hợp đồng API. Sau khi tắt export, ứng dụng vẫn có thể gọi method đó từ service/repository Java như bình thường.

Có thể tắt export toàn bộ repository bằng `@RepositoryRestResource(exported = false)`, nhưng khi đó các tài nguyên và finder thuộc repository cũng không còn được công bố theo cách thông thường. Chỉ dùng lựa chọn này khi mục tiêu là ẩn toàn bộ repository.

## 8. Vì sao search resource là chỉ đọc?

Spring Data REST công bố query method dưới dạng thao tác tìm kiếm qua HTTP GET. Client cung cấp tiêu chí truy vấn bằng path/query parameter; server thực thi finder và trả kết quả. Search URI không phải endpoint để tạo, thay thế hoặc xóa entity.

Ví dụ:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
~~~

Request chỉ đọc kết quả. Nó không tương đương với:

- `POST /people`: tạo entity mới.
- `PUT /people/42`: thay thế trạng thái item.
- `PATCH /people/42`: cập nhật một phần item.
- `DELETE /people/42`: xóa item.

Một query method dùng để tìm kiếm nên thực sự là truy vấn đọc. Không thiết kế finder có tác dụng phụ hoặc cập nhật dữ liệu rồi công bố nó như một search resource GET. Theo ngữ nghĩa HTTP, GET phải an toàn để client, proxy và cache có thể gọi lại mà không mong đợi thay đổi trạng thái server.

**Phạm vi chỉ đọc cần hiểu chính xác:** finder endpoint là GET-only, nhưng điều đó không tự động biến toàn bộ repository thành read-only. Nếu `PersonRepository` vẫn export CRUD methods, collection/item resource vẫn có thể cho phép ghi. Khi cần khóa ghi ở cấp repository, phải cấu hình exposure cho các HTTP method ghi hoặc ẩn các thao tác CRUD tương ứng, đồng thời áp dụng phân quyền ở tầng bảo mật.

## 9. Giới hạn quyền truy cập và dữ liệu trả về

Một search endpoint được công bố không đồng nghĩa mọi người dùng đều nên được phép gọi nó. Nếu kết quả chứa dữ liệu nhạy cảm hoặc chỉ dành cho một nhóm người dùng:

- Dùng Spring Security để yêu cầu xác thực và phân quyền cho endpoint.
- Chỉ export các finder thực sự cần cho client.
- Dùng projection hoặc cấu hình serialization để giới hạn field được trả về.
- Kiểm tra dữ liệu đầu vào và giới hạn phân trang để tránh truy vấn quá rộng.
- Không xem việc dùng HTTP GET hay `exported = false` là cơ chế thay thế cho authorization.

Nếu muốn giới hạn repository chỉ đọc, có thể cấu hình exposure theo collection và item. Ví dụ minh họa tắt các method ghi:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getExposureConfiguration()
            .withCollectionExposure((metadata, methods) ->
                methods.disable(HttpMethod.POST));

        config.getExposureConfiguration()
            .withItemExposure((metadata, methods) ->
                methods.disable(
                    HttpMethod.PUT,
                    HttpMethod.PATCH,
                    HttpMethod.DELETE));
    }
}
~~~

Đoạn cấu hình trên áp dụng theo exposure collection/item trên toàn bộ repository trong cấu hình tương ứng. Nếu chỉ muốn giới hạn một domain type, dùng API `forDomainType(Person.class)` theo phiên bản Spring Data REST đang sử dụng. Kiểm tra chữ ký API của dependency thực tế trước khi áp dụng; authorization vẫn cần được cấu hình riêng.

## 10. Kiểm thử search resource

Có thể dùng MockMvc để kiểm tra endpoint finder được export và xác nhận nó hoạt động bằng GET:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonSearchResourceTests {

    @Autowired
    MockMvc mvc;

    @Test
    void searchByLastNameReturnsHalCollection() throws Exception {
        mvc.perform(get("/people/search/by-last-name")
                .param("lastName", "Nguyen")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaTypes.HAL_JSON));
    }

    @Test
    void searchEndpointDoesNotAcceptPost() throws Exception {
        mvc.perform(post("/people/search/by-last-name")
                .param("lastName", "Nguyen"))
            .andExpect(status().isMethodNotAllowed());
    }
}
~~~

Đây là khung kiểm thử tích hợp; cần chuẩn bị dữ liệu test, cấu hình repository export và kiểm tra status phù hợp với ứng dụng. Bổ sung assertion cho nội dung kết quả và link HAL để bảo đảm finder trả đúng dữ liệu.

Nên kiểm tra thêm:

- Search link có xuất hiện trong collection representation hay không.
- Path tùy chỉnh và relation `rel` có đúng như cấu hình hay không.
- Query parameter có tên và kiểu đúng hay không.
- Finder bị `exported = false` không còn được công bố.
- Request POST/PUT/PATCH/DELETE tới search URI không được xử lý như thao tác ghi.
- Các endpoint CRUD khác của repository vẫn tuân theo chính sách exposure dự kiến.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Không thấy liên kết search | Finder không được export hoặc repository không được export | Kiểm tra annotation repository và `exported` trên method |
| Search URL mặc định khó đọc | Path được sinh từ tên Java method | Đặt `@RestResource(path = "...", rel = "...")` |
| Query parameter không nhận giá trị | Thiếu hoặc sai tên `@Param` | Dùng tên parameter rõ ràng và gửi đúng key trên URL |
| Request sai kiểu trả lỗi | Giá trị query parameter không chuyển đổi được | Kiểm tra kiểu Java và định dạng URL |
| Finder trả quá nhiều dữ liệu | Dùng List/Collection không phân trang | Dùng `Page<T>` và `Pageable` |
| Client gọi POST vào search URI bị từ chối | Search resource chỉ công bố GET | Dùng GET cho truy vấn; dùng collection/item endpoint cho thao tác ghi phù hợp |
| Đã ẩn finder nhưng client vẫn truy cập được dữ liệu | Một finder khác hoặc endpoint CRUD khác vẫn export | Kiểm tra toàn bộ search links và exposure của repository |
| Search trả dữ liệu không nên công khai | Thiếu phân quyền hoặc projection chưa giới hạn field | Cấu hình Spring Security và representation phù hợp |

## 12. Checklist công bố derived query method

- Chọn method name đúng quy tắc derived query của Spring Data.
- Chỉ công bố finder có mục đích đọc và không gây side effect.
- Dùng `@RestResource(path = "...", rel = "...")` để đặt URL và relation rõ ràng.
- Dùng `@Param` cho tên query parameter công khai.
- Chọn kiểu trả về phù hợp: List, Page, Slice hoặc Optional.
- Dùng Pageable/Sort khi cần phân trang và sắp xếp.
- Ẩn finder nội bộ bằng `@RestResource(exported = false)`.
- Kiểm tra search link trong HAL và thử request GET thực tế.
- Phân biệt finder GET-only với chính sách ghi của collection/item resource.
- Áp dụng authorization và giới hạn field nếu dữ liệu không dành cho mọi client.

## Kết luận

Spring Data REST có thể công bố derived query method thành search resource chỉ đọc dưới `/{collection}/search/{path}`. Spring Data suy ra truy vấn từ tên method; `@RestResource` đặt path và relation, còn `@Param` xác định tên parameter trên URL. Client gọi finder bằng GET và có thể dùng Pageable/Sort nếu method hỗ trợ. Dùng `exported = false` để ẩn finder không dành cho client. Search endpoint là GET-only, nhưng repository vẫn có thể có endpoint ghi riêng; muốn toàn bộ tài nguyên chỉ đọc phải cấu hình exposure và authorization tương ứng.

## Tài liệu tham khảo

- Spring Data REST – Defining repository resources and query methods: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data Commons – Query method keywords: https://docs.spring.io/spring-data/commons/reference/repositories/query-keywords-reference.html
- Spring Data Commons – Repository query return types: https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html
- Spring Data REST – Projections and excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
