# Bổ sung tìm kiếm, phân trang, sắp xếp và projection trong Spring Data REST

> Phạm vi: Spring Data REST xuất repository thành REST resource dùng Spring MVC và HAL. Các ví dụ dùng Spring Data JPA với `JpaRepository`; thay entity, package và repository theo dự án. Kiểm tra phiên bản Spring Boot/Spring Data do BOM quản lý trước khi áp dụng API cấu hình.

## 1. Mục tiêu và luồng khám phá API

Một collection API thực tế thường cần bốn khả năng phối hợp:

- **Tìm kiếm**: lọc theo tiêu chí nghiệp vụ và công bố các query method phù hợp.
- **Phân trang**: trả một phần tập kết quả, tránh tải toàn bộ dữ liệu.
- **Sắp xếp**: xác định thứ tự ổn định khi duyệt qua nhiều trang.
- **Projection**: chọn hình dạng dữ liệu trả về cho từng nhu cầu đọc.

Spring Data REST xuất collection resource cho repository, ví dụ `/people`, item resource như `/people/{id}` và search resource `/people/search` nếu repository có query method được export. Mặc định response dùng HAL. Client bắt đầu từ root URL, theo relation trong `_links`, sau đó theo link `search` và các link query method. Khi link là URI template, client điền biến được công bố thay vì tự đoán URL hoặc ghép đường dẫn.

```bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
curl -i -H "Accept: application/hal+json" http://localhost:8080/people
curl -i -H "Accept: application/hal+json" http://localhost:8080/people/search
```

Đường dẫn `/people` trong ví dụ phụ thuộc cấu hình repository. `@RepositoryRestResource(path=..., collectionResourceRel=...)` có thể thay path và relation; base path cũng có thể được cấu hình. Dùng link `self`, `search` và các link do server trả về để giữ client tương thích khi path thay đổi.

## 2. Khai báo query method có thể tìm kiếm

### 2.1. Repository và method finder

Spring Data REST tạo search resource từ query method công khai được export trên repository. Dùng derived query khi tiêu chí đủ rõ ràng; tên method phải khớp property của domain type và các từ khóa truy vấn mà store hỗ trợ.

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(path = "people", collectionResourceRel = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "byLastName", rel = "byLastName")
    Page<Person> findByLastNameContainingIgnoreCase(
            @Param("q") String q, Pageable pageable);
}
```

Với repository trên, search resource công bố relation `byLastName`, thường có URL dạng `/people/search/byLastName`. `@Param("q")` đặt tên query parameter là `q`, vì vậy request mẫu là:

```bash
curl -G "http://localhost:8080/people/search/byLastName" \
  -H "Accept: application/hal+json" \
  --data-urlencode "q=son" \
  --data-urlencode "page=0" \
  --data-urlencode "size=10" \
  --data-urlencode "sort=lastName,asc" \
  --data-urlencode "sort=id,asc"
```

`@RestResource` cho phép đổi `path` và `rel` của query method. Nếu không cần công bố một method, đánh dấu `@RestResource(exported = false)`. Không thêm finder chỉ để tiện truy vấn nội bộ nếu method đó không nên trở thành một phần của API.

### 2.2. Chọn kiểu kết quả phù hợp

| Kiểu trả về | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `Page<T>` | Nội dung trang cùng thông tin tổng số phần tử/trang | UI cần tổng số trang hoặc số kết quả |
| `Slice<T>` | Nội dung trang và thông tin còn trang tiếp theo hay không | Duyệt tiếp từng trang, không cần tổng số |
| `List<T>` | Danh sách kết quả | Tập kết quả đã giới hạn nhỏ; không cần metadata trang |

Với query method cần phân trang theo hợp đồng Spring Data REST, khai báo tham số `Pageable` và trả về `Page` hoặc `Slice`. `Page` thường cần thêm count query để tính `totalElements` và `totalPages`; count query có thể tốn kém với truy vấn phức tạp. `Slice` chỉ cần biết còn dữ liệu tiếp theo hay không và thường tránh count query. Không trả `List` lớn rồi kỳ vọng server tự chia trang.

Ví dụ các dạng method Spring Data hỗ trợ:

```java
Page<Person> findByLastName(String lastName, Pageable pageable);
Slice<Person> findByCity(String city, Pageable pageable);
List<Person> findByLastName(String lastName, Sort sort);
```

Chỉ dùng một tham số đặc biệt tương ứng trong method. `Pageable` đã bao gồm sort và page size, vì vậy không khai báo thêm `Sort` hoặc `Limit` trong cùng method với `Pageable`.

## 3. Phân trang collection và search result

Spring Data REST nhận các query parameter mặc định:

| Parameter | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `page` | Số trang, bắt đầu từ `0` | `0` |
| `size` | Số item tối đa trong trang | `20` |
| `sort` | Thuộc tính và chiều sắp xếp | Không yêu cầu sort riêng |

Ví dụ trang đầu gồm 5 item: `GET /people?page=0&size=5`. Trang thứ hai: `GET /people?page=1&size=5`. Cùng các tham số này áp dụng cho query method có hỗ trợ `Pageable`.

Response HAL phân trang chứa `_embedded` với các resource của trang hiện tại, `_links.self` và khi phù hợp có `_links.next`/`_links.prev`. Object `page` cung cấp `size`, `totalElements`, `totalPages` và `number`. `number` cũng là số trang bắt đầu từ `0`. Trang đầu không có `prev`; trang cuối không có `next`.

Ví dụ rút gọn:

```json
{
  "_links": {
    "self": { "href": "http://localhost:8080/people{&sort,page,size}", "templated": true },
    "next": { "href": "http://localhost:8080/people?page=1&size=5{&sort}", "templated": true }
  },
  "_embedded": { "people": [ { "firstName": "An", "lastName": "Nguyen" } ] },
  "page": {
    "size": 5,
    "totalElements": 50,
    "totalPages": 10,
    "number": 0
  }
}
```

Client nên dùng `next` và `prev` để điều hướng, thay vì tự tăng page và dựng URL. Khi người dùng đổi filter hoặc sort, hãy bắt đầu lại từ trang `0`; link trang trước/sau của truy vấn cũ không còn đại diện cho tiêu chí mới.

### 3.1. Giới hạn page size

Không cho client yêu cầu một trang quá lớn. Có thể đặt page size mặc định và mức tối đa trong `RepositoryRestConfigurer`:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestRepositoryConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config, CorsRegistry cors) {
        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);
    }
}
```

Các giá trị `25` và `100` chỉ là ví dụ. Chọn giới hạn theo kích thước payload, độ phức tạp projection, tải database và giới hạn của client. Xác nhận hành vi khi request `size` vượt ngưỡng bằng integration test trên phiên bản đang chạy.

Phân trang theo offset có thể chậm khi `page` rất lớn vì database vẫn phải bỏ qua nhiều bản ghi. Với bảng lớn và yêu cầu duyệt sâu, cân nhắc chiến lược keyset/scrolling phù hợp store hoặc API chuyên biệt; không mặc định rằng query parameter `page` của Spring Data REST tự chuyển thành cursor pagination.

## 4. Sắp xếp một hoặc nhiều thuộc tính

Tham số `sort` có dạng `sort=property,direction`, trong đó direction là `asc` hoặc `desc`. Có thể lặp lại tham số để sắp xếp theo nhiều tiêu chí; thứ tự xuất hiện trong query string quyết định thứ tự ưu tiên:

```bash
curl "http://localhost:8080/people?sort=lastName,asc&sort=firstName,asc&sort=id,asc"
```

Ví dụ trên sắp xếp theo họ, sau đó tên, cuối cùng là ID. Thêm một thuộc tính duy nhất làm tie-breaker như `id` giúp thứ tự ổn định khi nhiều hàng có cùng họ và tên. Điều này đặc biệt quan trọng khi kết hợp với phân trang để tránh một bản ghi di chuyển giữa các trang do thứ tự không xác định.

Có thể sort theo property cấp cao nhất hoặc nested property bằng property path notation, nếu store hỗ trợ. Sort theo association được export thành link tới top-level resource không được hỗ trợ trực tiếp. Tên property phải khớp domain model, không phải tên cột database tùy ý.

Ví dụ dùng sort động trong code Spring Data:

```java
Sort sort = Sort.by(Sort.Order.asc("lastName"))
        .and(Sort.by(Sort.Order.asc("firstName")))
        .and(Sort.by(Sort.Order.asc("id")));

Pageable pageable = PageRequest.of(0, 25, sort);
Page<Person> result = personRepository.findByLastNameContainingIgnoreCase("son", pageable);
```

`Pageable` đã mang theo sort. Nếu repository method có thứ tự tĩnh trong tên như `findByStatusOrderByCreatedAtDesc`, hãy kiểm tra cách thứ tự tĩnh kết hợp với sort động trong store cụ thể; tránh để API phụ thuộc vào hai nguồn sort khó dự đoán.

## 5. Projection và excerpt

### 5.1. Projection theo request

Mặc định Spring Data REST render domain object theo representation mặc định. Projection là interface có `@Projection`, chỉ khai báo getter của các thuộc tính cần đưa vào response. Ví dụ:

```java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "summary", types = Person.class)
public interface PersonSummary {
    String getFirstName();
    String getLastName();
}
```

Đặt interface trong cùng package với domain type hoặc một sub-package để Spring Data REST tự phát hiện. Nếu cần, có thể đăng ký thủ công qua `RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)`. Tên query parameter là giá trị `name` trong `@Projection`, không phải tên interface.

Khi server công bố projection, client có thể yêu cầu item resource như sau:

```bash
curl -H "Accept: application/hal+json" \
  "http://localhost:8080/people/42?projection=summary"
```

`self` link của resource có thể được render thành URI template có biến `projection`. ALPS `profile` link ở root và ALPS descriptor của resource cũng giúp client khám phá các projection đã công bố. Ưu tiên metadata và link do server trả về để biết tên projection khả dụng.

### 5.2. Excerpt projection cho collection

Có thể đặt projection mặc định cho resource được embed trong collection bằng `excerptProjection`:

```java
@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        excerptProjection = PersonSummary.class)
public interface PersonRepository extends JpaRepository<Person, Long> {
    // Query methods...
}
```

Excerpt projection được áp dụng tự động cho representation của resource trong collection hoặc related resource. Nó không tự động áp dụng cho một item resource được gọi trực tiếp. Khi đọc `/people/42`, client cần gửi `?projection=summary` nếu muốn projection đó. Hai đường truy cập vì vậy có thể có representation khác nhau.

Excerpt giúp collection preview gọn hơn và có thể đưa một số dữ liệu liên quan vào response. Nếu projection chứa getter association như `Address getAddress()`, nội dung address có thể được embed trong JSON trong khi link association vẫn được cung cấp để điều hướng.

### 5.3. Projection không phải ranh giới bảo mật

Projection thay đổi representation, không thay thế authorization. Spring Data REST cảnh báo projection có thể đưa cả dữ liệu vốn bị ẩn ra response; ví dụ getter trong projection có thể làm lộ property dù entity có `@JsonIgnore`. Vì vậy:

- Không tạo projection chứa password, token, secret, internal flag hoặc thông tin cá nhân không dành cho client.
- Rà soát mọi getter, nested projection và SpEL `@Value` trước khi export.
- Kiểm tra cả collection excerpt, item projection và projection của search result.
- Dùng Spring Security và policy truy cập ở tầng phù hợp để quyết định ai được đọc resource.
- Khi thêm `excerptProjection` vào API đã phát hành, xem đây là thay đổi representation có thể ảnh hưởng client hiện hữu.

Projection chỉ quyết định field được serialize. Nó không đảm bảo query database chỉ tải đúng các field đó trong mọi store, và không tự giải quyết N+1 khi getter truy cập association lazy. Đo SQL và kiểm thử hiệu năng bằng dữ liệu đại diện trước khi coi projection là tối ưu truy vấn.

## 6. Kết hợp tìm kiếm, phân trang, sort và projection

Một request search có thể kết hợp query parameter nghiệp vụ, paging, sort và projection:

```bash
curl -G "http://localhost:8080/people/search/byLastName" \
  -H "Accept: application/hal+json" \
  --data-urlencode "q=son" \
  --data-urlencode "page=0" \
  --data-urlencode "size=20" \
  --data-urlencode "sort=lastName,asc" \
  --data-urlencode "sort=id,asc" \
  --data-urlencode "projection=summary"
```

Chỉ dùng biến projection nếu query method resource công bố biến đó trong URI template. Hãy kiểm tra link từ `/people/search` hoặc link query method thay vì giả định mọi query method đều nhận mọi biến. Khi response có `_links.next`, đi theo link đó để giữ các tham số cần thiết cho trang tiếp theo.

Một cách cấu hình repository hoàn chỉnh có thể kết hợp excerpt và finder như sau:

```java
@RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people",
        excerptProjection = PersonSummary.class)
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "byLastName", rel = "byLastName")
    Page<Person> findByLastNameContainingIgnoreCase(
            @Param("q") String q, Pageable pageable);
}
```

Ở đây excerpt điều khiển representation mặc định của collection; query method cung cấp tập kết quả lọc; `Pageable` xử lý page/size/sort; query parameter `projection` có thể chọn representation khác nếu URI template của endpoint công bố biến đó.

## 7. Kiểm thử hợp đồng HTTP bằng MockMvc

Kiểm thử ở tầng HTTP để xác nhận repository method thật sự được export, link HAL có mặt, query parameter được bind và representation đúng. Ví dụ dưới đây giả định có ba fixture `Person`, repository dùng path `/people`, relation collection là `people`, và entity có constructor phù hợp:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PersonRepositoryRestTest {

    @Autowired MockMvc mockMvc;
    @Autowired PersonRepository people;

    @BeforeEach
    void seed() {
        people.deleteAll();
        people.saveAll(List.of(
                new Person("An", "Nguyen"),
                new Person("Binh", "Nguyen"),
                new Person("Chi", "Tran")));
    }

    @Test
    void collectionSupportsPagingAndStableSorting() throws Exception {
        mockMvc.perform(get("/people")
                .param("page", "0")
                .param("size", "2")
                .param("sort", "lastName,asc")
                .param("sort", "id,asc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$.page.size").value(2))
            .andExpect(jsonPath("$._embedded.people").isArray())
            .andExpect(jsonPath("$._links.next.href").exists());
    }

    @Test
    void searchMethodBindsQueryAndPageable() throws Exception {
        mockMvc.perform(get("/people/search/byLastName")
                .param("q", "nguyen")
                .param("page", "0")
                .param("size", "1")
                .param("sort", "lastName,asc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.page.size").value(1))
            .andExpect(jsonPath("$._embedded.people").isArray());
    }

    @Test
    void itemCanSelectProjection() throws Exception {
        Person person = people.findAll().stream()
                .filter(p -> p.getFirstName().equals("An"))
                .findFirst().orElseThrow();

        mockMvc.perform(get("/people/{id}", person.getId())
                .param("projection", "summary")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.firstName").value("An"))
            .andExpect(jsonPath("$.lastName").value("Nguyen"));
    }
}
```

Bổ sung import `MockMvc`, `MediaTypes`, `BeforeEach`, `SpringBootTest`, `AutoConfigureMockMvc` và các static import MockMvc/JSONPath/JUnit phù hợp. Điều chỉnh constructor, fixture, path và relation theo model thật. Nếu test cần xác nhận excerpt, gọi `GET /people` và assert field của `PersonSummary` trong `$. _embedded.people[0]`; nếu test item, dùng query parameter `projection` rõ ràng.

Các kiểm thử nên bao gồm:

- Root resource công bố collection relation; collection công bố `search` khi có query method.
- Search resource liệt kê đúng query method đã export; method `exported = false` không xuất hiện.
- `page` bắt đầu từ `0`, `size` bị giới hạn, metadata và `next`/`prev` thay đổi đúng ở đầu/cuối tập kết quả.
- Nhiều `sort` parameter tạo đúng thứ tự; thêm tie-breaker để kết quả giữa các trang ổn định.
- Query method bind đúng `@Param` và nhận `Pageable`; kết quả chỉ chứa record phù hợp.
- Projection item và excerpt collection trả đúng field; không trả field nhạy cảm.
- Thay đổi `excerptProjection` không vô tình phá hợp đồng response đã được client sử dụng.

## 8. Troubleshooting

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có relation `search` | Repository không có query method được export hoặc method đã bị ẩn | Kiểm tra method công khai, `@RestResource(exported = false)` và repository export config |
| `GET /people/search` trả `404` | Search resource không có query method khả dụng | Kiểm tra repository declaration và các finder được export |
| Query method URL không đúng | Path/relation đã được tùy chỉnh hoặc base path khác | Theo link từ collection `search`, kiểm tra `@RestResource(path, rel)` và base path |
| Query trả toàn bộ dữ liệu hoặc không có page metadata | Method trả `List` hoặc thiếu `Pageable` | Dùng `Page<T>`/`Slice<T>` cùng tham số `Pageable` |
| Page bắt đầu ở kết quả thứ hai | Client gửi `page=1` trong khi page index bắt đầu từ `0` | Dùng `page=0` cho trang đầu |
| Request `size` lớn gây tải database | Chưa đặt giới hạn page size hoặc client gửi page quá lớn | Đặt `setMaxPageSize`, chọn default phù hợp và đo tải thực tế |
| Sort không áp dụng | Tên property sai, direction sai hoặc sort theo association link | Dùng tên property của entity, `asc`/`desc`, và sort field có thể truy vấn |
| Bản ghi lặp hoặc biến mất giữa các trang | Sort không xác định khi nhiều record có cùng giá trị | Thêm khóa duy nhất làm tiêu chí sort cuối cùng; cân nhắc dữ liệu thay đổi đồng thời |
| Projection không được nhận diện | Interface thiếu `@Projection` hoặc nằm ngoài package scan | Đặt trong package domain/sub-package hoặc đăng ký thủ công |
| Excerpt không xuất hiện khi GET item | Excerpt chỉ áp dụng tự động cho collection/related resource | Gửi `?projection=<name>` cho item resource |
| Field nhạy cảm xuất hiện trong JSON | Getter projection đã export field vốn bị ẩn | Rà soát projection, nested getter, SpEL và authorization |
| Page query chậm dù chỉ lấy ít row | Count query, offset sâu, join hoặc N+1 khi serialize projection | Đo SQL; cân nhắc `Slice`, index, fetch strategy hoặc API truy vấn chuyên biệt |

Khi debug, kiểm tra theo thứ tự: root HAL links → collection `search` link → query method URI template → query parameter và response metadata → SQL/query plan → projection representation. Cách này tách lỗi discoverability, binding, paging và serialization.

## 9. Tài liệu tham khảo chính thức

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, search resource, query method resource, HTTP method và parameter.
- [Spring Data REST — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): page/size/sort, `Pageable`, HAL `next`/`prev` links và page metadata.
- [Spring Data REST — Projections and excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): `@Projection`, projection discovery, ALPS, excerpt và giới hạn áp dụng cho item resource.
- [Spring Data REST — Getting started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): base path và các thuộc tính cấu hình như default/max page size.
- [RepositoryRestConfiguration Javadoc](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html): `setDefaultPageSize`, `setMaxPageSize` và cấu hình exporter.
- [Spring Data Commons — Defining query methods](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html): derived query, `Page`, `Slice`, `Pageable`, `Sort`, count query và giới hạn offset.
- [Spring Data Commons — Paging, iterating, sorting and limiting](https://docs.spring.io/spring-data/commons/reference/repositories/query-methods-details.html#repositories.special-parameters): tham số đặc biệt và cách chọn kiểu kết quả cho truy vấn lớn.