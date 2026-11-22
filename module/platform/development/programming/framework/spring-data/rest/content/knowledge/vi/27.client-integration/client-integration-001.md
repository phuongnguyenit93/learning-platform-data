# Khám phá API bằng HAL Explorer và đọc URI template

## Mục tiêu

Spring Data REST dùng HAL làm định dạng hypermedia mặc định. Client bắt đầu từ URI gốc của API, đọc các link relation trong trường **_links**, rồi đi theo **href** để tìm collection, item, association, search và metadata. Với link có **templated: true**, **href** là URI template chứa biến cần được điền trước khi gửi request.

HAL Explorer là giao diện trình duyệt giúp thực hiện quá trình khám phá đó. Bài này hướng dẫn cài HAL Explorer, đọc HAL document, điền URI template, theo dõi metadata và kiểm thử các link mà API công bố.

Ví dụ dùng Java, Spring Boot, Spring Data REST và Spring HATEOAS. Giữ các dependency versions theo Spring Boot hoặc Spring Data BOM của dự án để tránh lệch phiên bản.

## 1. Bật HAL Explorer

Thêm dependency **spring-data-rest-hal-explorer** vào ứng dụng.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.data</groupId>
    <artifactId>spring-data-rest-hal-explorer</artifactId>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation "org.springframework.data:spring-data-rest-hal-explorer"
}
~~~

Khi dùng Spring Boot hoặc Spring Data BOM, không cần tự ghi version cho dependency này. HAL Explorer tự cấu hình giao diện để được phục vụ khi mở URI gốc của ứng dụng. Nếu API có cấu hình base path, ví dụ:

~~~yaml
spring:
  data:
    rest:
      base-path: /api
~~~

hãy mở URI ứng dụng tương ứng với base path, chẳng hạn **http://localhost:8080/api**. Nếu không cấu hình base path, thử **http://localhost:8080/**. Khi trình duyệt gửi request HTML, HAL Explorer hiển thị giao diện; request với Accept **application/hal+json** vẫn dùng để đọc HAL document của API.

HAL Explorer có thể điều hướng bằng GET và hiển thị các thao tác POST, PUT, PATCH, DELETE được API hỗ trợ. Vì giao diện có thể gửi request làm thay đổi dữ liệu, chỉ bật nó ở môi trường phát triển/kiểm thử hoặc bảo vệ nó bằng cùng cơ chế xác thực và phân quyền của API.

## 2. Khám phá từ root resource

Bắt đầu bằng GET đến URI gốc của Spring Data REST:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Ví dụ root document:

~~~json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/api/people"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile"
    }
  }
}
~~~

Đây là ví dụ minh họa; tên relation và URL phụ thuộc repository annotation, base path và cấu hình. Trong HAL:

- **_links** chứa các link relation mà client có thể đi theo.
- **rel** là tên quan hệ, ví dụ **people**, **self**, **search**, **profile**, **next** hoặc **prev**.
- **href** là URI đích. Client nên đọc href từ response thay vì tự ghép hostname và đường dẫn.
- **templated: true** báo rằng href chứa biến URI template.
- **_embedded** thường chứa các resource được nhúng trong collection response.
- **page** chứa metadata phân trang khi endpoint trả về dữ liệu dạng page.

Resource discovery bắt đầu ở root. Theo link relation của collection để lấy danh sách; theo link **self** để quay lại resource hiện tại; theo **search** để tìm query method đã được export; theo **profile** để xem metadata. Không giả định mọi repository đều có search link: link này chỉ xuất hiện khi repository export query methods.

### Phân biệt path và rel

Có hai giá trị thường bị nhầm:

- **path** quyết định đoạn URL của resource.
- **rel** quyết định tên link relation xuất hiện trong HAL document.

Ví dụ:

~~~java
@RepositoryRestResource(path = "people", rel = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "names", rel = "names")
    List<Person> findByName(@Param("name") String name);
}
~~~

Collection có URL **/people** và relation **people** ở root. Query method được phát hiện dưới relation **names** trong resource **search**. Nếu chỉ đặt **path = "people"** mà không đặt **rel**, tên relation vẫn có thể là dạng số nhiều mặc định do Spring Data REST suy ra từ domain class.

## 3. Dùng HAL Explorer để thao tác

Sau khi mở giao diện:

1. Nhìn danh sách link ở khung bên trái. Mỗi link relation là một đường dẫn mà server công bố.
2. Chọn GET để mở collection hoặc resource. Khung chi tiết hiển thị request URI, HTTP method, response headers và HAL body.
3. Khi link có URI template, HAL Explorer mở hộp thoại cho các biến. Điền tham số cần thiết rồi chọn Go. Biến tùy chọn có thể bỏ trống; nếu không nhập, chúng được bỏ khỏi URI đã mở rộng.
4. Với nút không phải GET, chọn thao tác để mở hộp thoại tương ứng. Giao diện hiển thị HTTP method và các trường request body dựa trên metadata resource mà Spring Data REST sinh ra.
5. Kiểm tra response sau khi gửi: status, Location header nếu có, body, các link mới và link điều hướng tiếp theo.

HAL Explorer hiểu HAL và HAL-FORMS, đồng thời hỗ trợ Spring profiles do Spring Data REST sinh ra. Các trường trong hộp thoại request được điền dựa trên metadata; thay đổi domain object hoặc cấu hình representation có thể làm danh sách trường hiển thị thay đổi.

Ví dụ thao tác an toàn trong môi trường local:

- Mở relation **people** bằng GET để xem collection.
- Mở **search**, sau đó chọn relation query được công bố để thử tìm kiếm.
- Dùng link có template để thử page/size/sort.
- Dùng POST với một JSON body hợp lệ để tạo dữ liệu mẫu.
- Mở link **self** của item để kiểm tra resource vừa tạo.

Không nhập dữ liệu thật hoặc thử POST/PUT/PATCH/DELETE trên production chỉ để khám phá giao diện.

## 4. Đọc URI template

Một collection có phân trang thường trả về link **self** và **next** dưới dạng template. Ví dụ:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people{&sort,page,size}",
      "templated": true
    },
    "next": {
      "href": "http://localhost:8080/api/people?page=1&size=5{&sort}",
      "templated": true
    }
  },
  "page": {
    "size": 5,
    "totalElements": 50,
    "totalPages": 10,
    "number": 0
  }
}
~~~

Trong ví dụ này:

- **templated: true** cho biết href chưa phải URI cuối cùng.
- **{&sort,page,size}** biểu diễn các biến query có thể bổ sung vào URI.
- **next** giữ page và size của trang kế tiếp; client có thể đi theo link này thay vì tự tính số trang.
- **page.number** là chỉ số trang bắt đầu từ 0; **page.size** là số phần tử trên một trang.

Với repository hỗ trợ paging, các tham số mặc định thường là **page**, **size**, **sort**. Ví dụ:

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/api/people?page=1&size=5&sort=name,asc"
~~~

Đặt toàn bộ URL trong dấu nháy khi dùng shell nếu query string có ký tự **&**, để shell không diễn giải nó thành toán tử nối lệnh. Tên tham số paging có thể được tùy chỉnh trong cấu hình Spring Data REST; hãy đọc các biến được server công bố thay vì giả định tên luôn cố định.

### Mở rộng template bằng Spring HATEOAS

Spring HATEOAS cung cấp **Link** để kiểm tra và mở rộng URI template. Ví dụ:

~~~java
import java.util.Map;

import org.springframework.hateoas.Link;

Link template = Link.of("/people{?page,size,sort}");

assertThat(template.isTemplated()).isTrue();
assertThat(template.getVariableNames())
    .contains("page", "size", "sort");

String expanded = template.expand(
    Map.of("page", 1, "size", 5)
).getHref();

assertThat(expanded).isEqualTo("/people?page=1&size=5");
~~~

Các thao tác quan trọng:

- **isTemplated()** cho biết link có phải URI template hay không.
- **getVariableNames()** trả về tên các biến mà template khai báo.
- **expand(Map)** tạo link đã thay các biến bằng giá trị truyền vào.
- **getHref()** trả về URI sau khi mở rộng.

Ví dụ trên dùng **{?page,size,sort}** vì template bắt đầu phần query string. Khi URI đã có query parameter và cần nối thêm biến, template có thể dùng toán tử **{&sort}** như trong link **next** của Spring Data REST.

Đừng xóa phần template hoặc tự ghép chuỗi query khi server đã cung cấp link. Dùng link relation và cơ chế expand giúp client không phải biết trước cấu trúc URL.

## 5. Đọc metadata qua profile

Spring Data REST công bố link **profile** ở root hoặc trong representation của resource. Hãy theo link đó để tìm metadata thay vì mặc định ghép đường dẫn. Tài liệu ALPS mô tả semantics của repository: các thuộc tính của resource và các thao tác REST có thể thực hiện.

Một số bước khám phá:

1. GET root, tìm relation **profile** trong **_links**.
2. Theo link profile để lấy các profile resource.
3. Theo profile của collection cần tìm để xem descriptor của domain type và các thao tác được export.
4. Gửi Accept **application/alps+json** để đọc ALPS; nếu cần JSON Schema, thử Accept **application/schema+json** tại profile resource được công bố.

ALPS có thể cho biết các thao tác như get, create, update, patch và delete cùng với các trường của representation. HAL Explorer dùng metadata này để hỗ trợ tạo request body. Metadata không thay thế phân quyền: một thao tác xuất hiện trong profile vẫn có thể bị security policy từ chối khi thực thi.

## 6. Kiểm thử link và template

Nên kiểm tra cả response HAL và khả năng mở rộng template. Ví dụ dùng Spring Boot test và MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class HalDiscoveryTest {

    private static final MediaType HAL_JSON =
        MediaType.parseMediaType("application/hal+json");

    @Autowired
    private MockMvc mvc;

    @Test
    void rootPublishesCollectionRelation() throws Exception {
        mvc.perform(get("/api").accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(HAL_JSON))
            .andExpect(jsonPath("$._links.people.href").exists());
    }

    @Test
    void collectionPublishesTemplatedPagingLink() throws Exception {
        mvc.perform(get("/api/people")
                .param("size", "5")
                .accept(HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.self.templated").value(true))
            .andExpect(jsonPath("$.page.size").value(5));
    }
}
~~~

Nếu ứng dụng không đặt **spring.data.rest.base-path: /api**, thay **/api** bằng URI root thực tế. Repository cần hỗ trợ paging để response có page metadata. Để kiểm tra **next**, chuẩn bị đủ dữ liệu để có ít nhất hai trang; server không phát link next ở trang cuối.

Kiểm thử template expansion riêng:

~~~java
@Test
void expandsPagingTemplate() {
    Link template = Link.of("/people{?page,size}");

    assertThat(template.isTemplated()).isTrue();
    assertThat(template.getVariableNames()).contains("page", "size");

    assertThat(template.expand(Map.of("page", 1, "size", 5)).getHref())
        .isEqualTo("/people?page=1&size=5");
}
~~~

Nếu repository có finder method, kiểm tra relation **search** và relation của query method:

~~~java
mvc.perform(get("/api/people/search")
        .accept(HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.names.href").exists());
~~~

Đoạn test search giả định repository khai báo query method với **@RestResource(rel = "names")** như ví dụ ở phần path/rel. Nếu dùng tên mặc định, thay JSON path bằng relation server thực tế trả về.

## 7. Khắc phục lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Không thấy giao diện HAL Explorer | Thiếu dependency hoặc mở sai URI root/base path | Thêm **spring-data-rest-hal-explorer**, mở URI ứng dụng đúng với **spring.data.rest.base-path** |
| Root trả 404 hoặc không có link collection | Repository không được export, base path sai hoặc repository đặt **exported = false** | Kiểm tra repository scan, cấu hình path và **@RepositoryRestResource** |
| Link key là **persons** thay vì **people** | Chỉ đổi **path**, chưa đổi **rel** | Đặt cả **path = "people"** và **rel = "people"** nếu muốn relation tên people |
| Không có relation **search** | Repository không export query method | Khai báo finder method và kiểm tra method không bị **@RestResource(exported = false)** |
| Không thấy **next** | Dataset chưa đủ để có trang kế tiếp | Tạo đủ bản ghi và thử với **size** nhỏ |
| Link **self** không có **templated: true** | Resource không cung cấp URI template hoặc không hỗ trợ paging | Kiểm tra repository có paging và đọc đúng collection response |
| HAL Explorer yêu cầu biến template | Link có **templated: true** và cần tham số | Điền tên biến đúng như template, ví dụ **page**, **size**, **sort** |
| Query không lọc/sắp xếp như mong đợi | Sai tên biến, giá trị sort không phải property hợp lệ hoặc page bắt đầu từ 0 | Đọc template, dùng tên property domain hợp lệ và kiểm tra **page/size/sort** |
| POST/PUT/PATCH trả 405 | HTTP method hoặc repository method không được export | Kiểm tra method CRUD, **@RestResource(exported = false)** và loại resource đang thao tác |
| Request trả 401/403 | Security yêu cầu đăng nhập hoặc quyền tương ứng | Dùng phiên/credential hợp lệ và kiểm tra authorization policy |
| Hộp thoại không có trường mong muốn | Metadata/representation không công bố trường đó | Theo link **profile**, kiểm tra projection, serialization và trường bị ẩn |

## 8. Checklist thực hành

- [ ] Dependency HAL Explorer được thêm và version do BOM quản lý.
- [ ] Mở đúng root URI hoặc REST base path trong trình duyệt.
- [ ] Root response có content type HAL và công bố collection relation.
- [ ] Đã phân biệt tên relation (**rel**) với đường dẫn (**path**).
- [ ] Đã theo link collection, item, search và profile được server trả về.
- [ ] Đã nhận biết **templated: true** và liệt kê được tên biến của template.
- [ ] Đã thử mở rộng paging template bằng **page**, **size** và **sort**.
- [ ] Đã kiểm tra page metadata và điều kiện xuất hiện của **next/prev**.
- [ ] Đã đọc metadata ALPS hoặc JSON Schema qua profile link.
- [ ] MockMvc kiểm tra root relation và collection paging template.
- [ ] Test riêng xác nhận URI template được mở rộng thành URI đúng.
- [ ] HAL Explorer chỉ được bật ở môi trường phù hợp và có bảo vệ truy cập khi cần.

## 9. Tài liệu chính thức

- [Spring Data REST — Tools / HAL Explorer](https://docs.spring.io/spring-data/rest/reference/tools.html): dependency, giao diện, các thao tác HTTP, URI template và metadata.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): root discovery, collection/item/search resources, media types và HTTP methods.
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): link self/next/prev, URI template và page metadata.
- [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html): profile và ALPS cho repository.
- [Spring Data REST — Configuring the REST URL Path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html): cách dùng path và rel, finder resource và ẩn resource.
- [Spring HATEOAS — Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html): isTemplated, getVariableNames và expand.
- [Spring HATEOAS — UriTemplate API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/UriTemplate.html): tạo, liệt kê biến và mở rộng URI template.
