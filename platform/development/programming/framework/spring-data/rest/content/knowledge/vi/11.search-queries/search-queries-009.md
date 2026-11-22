# Tham số thiếu, giá trị không hợp lệ và kết quả không có dữ liệu trong truy vấn Spring Data REST

## Mục tiêu

Sau bài này, bạn có thể đọc và gọi đúng search resource của Spring Data REST; phân biệt tham số bắt buộc với tham số tùy chọn; nhận biết lỗi chuyển đổi kiểu và dữ liệu đầu vào không hợp lệ; đồng thời phân biệt một truy vấn chạy thành công nhưng không tìm thấy bản ghi với một endpoint không tồn tại.

## 1. Search resource và query method resource

Khi repository có các query method được Spring Data REST export, API công bố một search resource tại đường dẫn `/search`. Search resource trả về các link đến từng query method resource. Client nên khám phá link này từ HAL thay vì tự đoán URL.

Ví dụ repository:

```java
public interface PersonRepository
        extends PagingAndSortingRepository<Person, Long> {

    List<Person> findByName(String name);

    List<Person> findByAgeGreaterThan(Integer age);
}
```

Với repository có collection path `/people`, các query method thường được công bố dưới:

- `GET /people/search`: liệt kê link đến các query method.
- `GET /people/search/findByName?name=Ada`: chạy truy vấn theo tên.
- `GET /people/search/findByAgeGreaterThan?age=18`: chạy truy vấn theo tuổi.

Search resource chỉ hỗ trợ `GET`; query method resource cũng là resource chỉ đọc và chỉ hỗ trợ `GET`. Nếu method không được export hoặc bị ẩn bằng `@RestResource(exported = false)`, link tương ứng sẽ không xuất hiện trong danh sách search resource.

Có thể tùy chỉnh đường dẫn và relation name của query method:

```java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends CrudRepository<Person, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    List<Person> findByName(@Param("name") String name);
}
```

Trong ví dụ này, query method được công bố tại `/people/search/by-name`, với tham số `name`. `path` thay đổi đoạn URL; `rel` thay đổi tên relation trong HAL. Dùng link server trả về để xác định URL và tên tham số thực tế.

## 2. Truyền tham số truy vấn đúng cách

Tham số của query method được truyền dưới dạng query string trên URL. Tên tham số phải khớp với tên mà Spring Data REST công bố cho method.

Ví dụ:

```http
GET /people/search/findByName?name=Ada
Accept: application/hal+json
```

Với method có nhiều điều kiện:

```java
List<Person> findByNameAndActive(
        @Param("name") String name,
        @Param("active") Boolean active);
```

Request có thể là:

```http
GET /people/search/findByNameAndActive?name=Ada&active=true
```

Giá trị query string ban đầu là văn bản. Spring Data REST cần chuyển chúng sang kiểu tham số Java mà method yêu cầu, ví dụ `String`, `Integer`, `Boolean`, `UUID`, ngày giờ hoặc enum. Với giá trị chứa dấu cách, dấu cộng, dấu &, dấu tiếng Việt hoặc ký tự đặc biệt, hãy URL-encode đúng cách. Khi dùng curl, có thể dùng `--get` và `--data-urlencode` để tránh tự ghép query string sai:

```bash
curl --get http://localhost:8080/people/search/findByName \
  --data-urlencode "name=Ada Lovelace" \
  -H "Accept: application/hal+json"
```

Nếu method sử dụng `@Query` với named parameter trong Spring Data JPA, `@Param("name")` còn liên kết tham số Java với tên bind variable trong câu JPQL. Đây là chức năng binding của query; tên và URI public của query method vẫn nên được kiểm tra qua link search resource.

## 3. Tham số bị thiếu: bắt buộc hay tùy chọn?

Không phải mọi query parameter đều có cùng chính sách khi client bỏ qua. Hành vi phụ thuộc vào kiểu tham số, nullability và cách method được định nghĩa.

Ví dụ method nhận tham số không nullable:

```java
List<Person> findByName(String name);
```

Client nên gửi `name` trong request. Nếu bỏ tham số, framework có thể không có giá trị để chuyển vào method; nếu giá trị null được chuyển tới repository method, quy tắc nullability của Spring Data sẽ quyết định có chấp nhận hay từ chối. Tham số kiểu primitive như `int` và `long` cũng không thể biểu diễn `null`.

Nếu muốn chấp nhận việc không truyền tham số, hãy khai báo rõ ý định trong repository, chẳng hạn dùng kiểu tham chiếu cùng `@Nullable`:

```java
@Nullable
List<Person> findByName(@Nullable String name);
```

Việc cho phép null không có nghĩa Spring Data tự bỏ qua điều kiện lọc. Với query method dẫn xuất, `findByName(null)` có thể được diễn giải thành điều kiện tìm các bản ghi có `name IS NULL`, tùy theo query derivation và store. Nó không tự động trở thành `findAll()`.

Nếu nghiệp vụ muốn bộ lọc thực sự tùy chọn, hãy định nghĩa rõ hành vi. Với Spring Data JPA, có thể viết query có điều kiện:

```java
@Query("""
    select p from Person p
    where (:name is null or p.name = :name)
    """)
List<Person> searchByOptionalName(@Param("name") @Nullable String name);
```

Khi `name` không được truyền và được binding thành null, điều kiện tên được bỏ qua. Với nhiều bộ lọc tùy chọn, có thể dùng Specification, Querydsl hoặc custom repository để tránh một câu query phức tạp. Hãy kiểm tra semantics của store đang dùng.

Với API công khai, cần mô tả rõ tham số nào bắt buộc, tham số nào tùy chọn và giá trị mặc định. Đừng dựa vào việc client tự đoán rằng bỏ tham số có nghĩa là “không lọc”.

## 4. Giá trị không hợp lệ và lỗi chuyển đổi kiểu

Một query parameter có thể có tên đúng nhưng giá trị không chuyển được sang kiểu Java yêu cầu.

Ví dụ repository nhận tuổi dạng số:

```java
List<Person> findByAgeGreaterThan(Integer age);
```

Request hợp lệ:

```http
GET /people/search/findByAgeGreaterThan?age=18
```

Request có giá trị không hợp lệ:

```http
GET /people/search/findByAgeGreaterThan?age=eighteen
```

Chuỗi `eighteen` không thể chuyển thành `Integer`. Spring Data Core có exception `QueryMethodParameterConversionException` để biểu diễn trường hợp không chuyển được giá trị nguồn sang kiểu tham số của query method. Khi chuyển đổi thất bại, repository method không thể chạy với giá trị mong muốn; request được xử lý như lỗi đầu vào. Mã HTTP cụ thể có thể phụ thuộc phiên bản và exception handling của ứng dụng, vì vậy hãy xem cả status code lẫn response body.

Một số ví dụ khác:

| Kiểu Java | Giá trị gửi | Vấn đề |
| --- | --- | --- |
| `Integer` | `age=abc` | Không phải số nguyên |
| `Boolean` | `active=perhaps` | Không phải giá trị boolean hợp lệ |
| `UUID` | `id=123` | Không đúng định dạng UUID |
| `LocalDate` | `date=31-31-2025` | Không khớp định dạng/ngày hợp lệ |
| Enum `Status` | `status=UNKNOWN_VALUE` | Không có enum constant tương ứng |

Với ngày giờ, enum hoặc kiểu miền riêng, định dạng hợp lệ phụ thuộc converter và cấu hình của ứng dụng. Nếu API cần định dạng riêng, đăng ký converter phù hợp và ghi rõ định dạng trong tài liệu API.

Ngoài lỗi chuyển đổi, giá trị có thể chuyển đổi được nhưng không hợp lệ theo nghiệp vụ. Ví dụ `age=-5` là số nguyên hợp lệ về mặt cú pháp nhưng có thể vi phạm quy tắc miền. Query method không tự động thực thi mọi ràng buộc Bean Validation trên tham số truy vấn. Nếu cần giới hạn như tuổi không âm, khoảng ngày hợp lệ hoặc trạng thái được phép, hãy kiểm tra bằng custom repository/service hoặc custom controller trước khi chạy truy vấn.

## 5. Phân biệt lỗi tham số với truy vấn hợp lệ không có dữ liệu

Đây là điểm quan trọng khi đọc response:

- **Lỗi request:** URL sai, tham số bắt buộc không được cung cấp theo hợp đồng, giá trị không chuyển đổi được hoặc truy vấn không thể thực thi. Request không hoàn thành như một truy vấn hợp lệ.
- **Không có dữ liệu phù hợp:** tham số hợp lệ, query chạy thành công nhưng không có bản ghi nào thỏa điều kiện. Đây là kết quả hợp lệ của truy vấn.

Ví dụ, `GET /people/search/findByName?name=NoSuchPerson` có thể chạy thành công nhưng trả về danh sách rỗng. Điều đó không có nghĩa search endpoint bị lỗi hoặc resource không tồn tại.

Kiểu trả về của repository ảnh hưởng đến cách biểu diễn kết quả không có dữ liệu:

| Kiểu trả về | Khi không tìm thấy |
| --- | --- |
| `List<Person>`, `Collection<Person>`, `Iterable<Person>` | Trả collection rỗng, không phải `null` |
| `Page<Person>` | Nội dung trang rỗng và metadata cho biết không có phần tử/trang kết quả |
| `Optional<Person>` | Trả `Optional.empty()` |
| `Person` hoặc kiểu entity đơn | Có thể trả `null` nếu method cho phép; nếu khai báo non-null thì Spring Data có thể ném exception khi không có kết quả |

Với kiểu trả về entity đơn, query phải đảm bảo tối đa một kết quả. Nếu nhiều bản ghi được trả về trong khi method yêu cầu một entity đơn, Spring Data có thể ném `IncorrectResultSizeDataAccessException`. Hãy chọn `List`, `Page`, `Optional` hoặc kiểu trả về phù hợp với cardinality của query.

Không đồng nhất “không có bản ghi” với HTTP 404. 404 thường cho biết URI/resource không được tìm thấy, ví dụ gọi sai đường dẫn query method hoặc resource item không tồn tại. Một query method tồn tại và chạy thành công nhưng trả collection rỗng là một tình huống khác.

## 6. Phân trang và sắp xếp cũng có tham số cần kiểm tra

Nếu query method nhận `Pageable` và trả về `Page` hoặc `Slice`, Spring Data REST có thể công bố các tham số phân trang trong URI template:

- `page`: số trang, bắt đầu từ 0; mặc định là 0.
- `size`: số phần tử mỗi trang; mặc định thường là 20.
- `sort`: thuộc tính và hướng sắp xếp, ví dụ `sort=name,asc`.

Ví dụ:

```http
GET /people/search/findByName?name=Ada&page=0&size=10&sort=name,asc
```

Có thể gửi nhiều tiêu chí sort bằng nhiều tham số `sort`:

```http
GET /people?sort=lastname,asc&sort=firstname,asc
```

Spring Data REST có cấu hình giới hạn page size tối đa. Nếu client yêu cầu page size lớn hơn giới hạn, giá trị được xử lý theo cấu hình max page size của ứng dụng; đừng cho rằng client có thể yêu cầu kích thước trang tùy ý. Kiểm tra các thuộc tính như `spring.data.rest.default-page-size` và `spring.data.rest.max-page-size` trong Spring Boot nếu cần thay đổi hành vi.

Giá trị `page`, `size` hoặc sort property sai có thể gây lỗi binding hoặc truy vấn tùy phiên bản, resolver và datastore. Dùng đúng tên property có thể sắp xếp; kiểm tra response và log khi nhận lỗi. Không sort theo một tên field chỉ vì tên đó xuất hiện trong JSON projection: property cần phù hợp với domain model và khả năng sort của store.

## 7. Đọc đúng status code và response

Khi debug, không kết luận chỉ từ việc response body rỗng. Hãy kiểm tra lần lượt:

1. **HTTP status:** request có hoàn thành thành công hay server trả lỗi?
2. **Content-Type:** response là HAL JSON hay JSON khác?
3. **HAL links:** search resource có công bố query method cần gọi không?
4. **Query string:** tên tham số, encoding và kiểu giá trị có đúng không?
5. **Body và metadata:** collection rỗng, page có `totalElements = 0`, hay body không được trả vì cấu hình?
6. **Server log:** có lỗi conversion, nullability, query creation, SQL hoặc datastore không?

Các tình huống thường gặp:

| Triệu chứng | Khả năng cần kiểm tra |
| --- | --- |
| `404 Not Found` tại `/people/search` | Search resource không tồn tại, repository không export query method hoặc URL/base path sai. HEAD search resource trả 404 khi không có query method resources. |
| `404 Not Found` tại một query path | Sai path, method bị ẩn hoặc query method không được công bố. |
| `405 Method Not Allowed` | Đã gọi method không được hỗ trợ; search và query method resources chỉ hỗ trợ GET. |
| `400 Bad Request` | Có thể là tham số thiếu/không chuyển đổi được hoặc lỗi request khác; đọc response và log để xác định nguyên nhân cụ thể. |
| `200 OK` với collection rỗng | Query chạy thành công nhưng không có bản ghi khớp, hoặc bộ lọc đang quá chặt. |
| `200 OK` với page rỗng | Trang hiện tại không có phần tử; kiểm tra `page`, `size` và `totalElements`. |

Bảng trên là hướng chẩn đoán, không phải ánh xạ cứng cho mọi exception. Status thực tế còn chịu ảnh hưởng bởi phiên bản Spring Data REST, Spring Framework, datastore và exception handler do ứng dụng đăng ký.

## 8. Ví dụ kiểm tra theo từng tình huống

Giả sử repository có:

```java
public interface PersonRepository
        extends PagingAndSortingRepository<Person, Long> {

    List<Person> findByName(@Param("name") String name);

    List<Person> findByAgeGreaterThan(@Param("age") Integer age);

    Page<Person> findByActive(
            @Param("active") Boolean active,
            Pageable pageable);
}
```

**Trường hợp 1 — tham số đúng, có dữ liệu**

```bash
curl -i "http://localhost:8080/people/search/findByName?name=Ada"
```

Kiểm tra response có person phù hợp hay không.

**Trường hợp 2 — tham số đúng, không có dữ liệu**

```bash
curl -i "http://localhost:8080/people/search/findByName?name=NoSuchPerson"
```

Nếu response thành công nhưng collection rỗng, đây là kết quả truy vấn hợp lệ. Kiểm tra điều kiện tìm kiếm và dữ liệu trong datastore.

**Trường hợp 3 — sai kiểu tham số**

```bash
curl -i "http://localhost:8080/people/search/findByAgeGreaterThan?age=abc"
```

Giá trị `abc` không chuyển được thành `Integer`. Xem status, error body và log để tìm thông tin về tham số gây lỗi.

**Trường hợp 4 — tham số phân trang**

```bash
curl -i "http://localhost:8080/people/search/findByActive?active=true&page=0&size=10"
```

Kiểm tra `page`, `size`, tổng số phần tử và các link điều hướng trong HAL.

## 9. Cách thiết kế query method dễ sử dụng

- Đặt tên method phản ánh rõ điều kiện tìm kiếm; dùng `@RestResource(path = "...", rel = "...")` nếu tên mặc định quá dài hoặc khó hiểu.
- Dùng `@Param` rõ ràng cho các named parameter, nhất là khi dùng `@Query`; bảo đảm tên tham số mà client gửi khớp link/URI template được công bố.
- Chỉ cho phép bỏ tham số khi nghiệp vụ xác định rõ ý nghĩa của giá trị thiếu hoặc null.
- Phân biệt null, chuỗi rỗng và giá trị mặc định. Ba trường hợp này không tự động có cùng semantics.
- Dùng kiểu Java phù hợp để nhận biết dữ liệu sai sớm; thêm converter cho định dạng riêng khi cần.
- Dùng `Page` hoặc `Slice` cho tập dữ liệu lớn; cấu hình page size tối đa để tránh request quá nặng.
- Dùng kiểu trả về đơn như `Optional<T>` khi truy vấn mong đợi tối đa một entity; dùng collection khi có thể có nhiều kết quả.
- Không biến kết quả rỗng thành lỗi chỉ vì client mong đợi có dữ liệu. Nếu nghiệp vụ yêu cầu phải tồn tại kết quả, thể hiện điều kiện đó trong một service/controller riêng.

## Tóm tắt

- `GET /{repository}/search` liệt kê query method links; `GET /{repository}/search/{method}` thực thi query method.
- Query string phải có tên và định dạng phù hợp với tham số Java.
- Tham số thiếu/null được xử lý theo kiểu dữ liệu và nullability; muốn bộ lọc tùy chọn phải định nghĩa rõ semantics.
- Giá trị không chuyển đổi được gây lỗi tham số; giá trị chuyển đổi được nhưng vi phạm nghiệp vụ cần validation riêng.
- Collection không có kết quả thường trả collection rỗng; `Optional` biểu diễn kết quả đơn không có dữ liệu bằng `Optional.empty()`.
- 404 cho URI/resource không tồn tại khác với truy vấn hợp lệ trả về 0 bản ghi.
- Luôn đọc status, Content-Type, HAL links, response metadata và server log khi điều tra.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources, search resource and query method resource](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring Data Commons — Defining query methods and return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html)
- [Spring Data JPA — Null handling of repository methods](https://docs.spring.io/spring-data/jpa/reference/repositories/null-handling.html)
- [QueryMethodParameterConversionException — Spring Data API](https://docs.spring.io/spring-data/keyvalue/reference/data-commons/api/java/org/springframework/data/repository/support/QueryMethodParameterConversionException.html)
