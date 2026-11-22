# Phân biệt tài nguyên không tồn tại, tập hợp rỗng và phương thức bị tắt trong Spring Data REST

## Mục tiêu

Khi gọi một REST API, ba tình huống có thể tạo cảm giác giống nhau ở phía client: không nhận được entity mong muốn, collection không có item hoặc một thao tác không thực hiện được. Tuy nhiên, chúng có ý nghĩa khác nhau:

1. **Tài nguyên không tồn tại:** URI đang trỏ tới một repository resource hoặc item resource không được tìm thấy. Trường hợp điển hình là HTTP \`404 Not Found\`.
2. **Tập hợp rỗng:** collection resource vẫn tồn tại và request GET thành công, nhưng không có item phù hợp. Trường hợp điển hình là HTTP \`200 OK\` với collection representation rỗng.
3. **Phương thức bị tắt:** resource có thể tồn tại, nhưng một HTTP method hoặc một endpoint repository đã bị cấu hình không export. Tùy cách tắt, request có thể nhận \`405 Method Not Allowed\` hoặc \`404 Not Found\`.

Phân biệt đúng ba trường hợp giúp client xử lý response chính xác, giúp developer tìm đúng lớp cấu hình và tránh biến lỗi routing hoặc authorization thành logic nghiệp vụ sai.

## 1. Bảng nhận diện nhanh

| Tình huống | Ví dụ | Kết quả HTTP thường gặp | Ý nghĩa |
|---|---|---|---|
| Item không tồn tại | \`GET /api/people/9999\` khi không có Person đó | \`404 Not Found\` | Server không tìm thấy item resource tại URI được yêu cầu. |
| Repository resource không được export hoặc sai URI | \`GET /api/unknown\` | \`404 Not Found\` | Đường dẫn không ánh xạ tới resource được xuất bản. |
| Collection tồn tại nhưng không có item | \`GET /api/people\` khi repository chưa có dữ liệu | \`200 OK\` | Collection hợp lệ, nội dung hiện tại rỗng. |
| Search trả về không có kết quả | \`GET /api/people/search/by-status?status=UNKNOWN\` | \`200 OK\` | Search resource tồn tại và truy vấn chạy thành công, nhưng không có item phù hợp. |
| HTTP method không được cho phép trên resource | \`POST /api/people\` khi POST đã bị disable | Thường là \`405 Method Not Allowed\` | URI/resource được nhận diện, nhưng method đó không được hỗ trợ hoặc đã bị tắt. |
| Query method không được export | Gọi URI search của method có \`exported=false\` | Có thể là \`404 Not Found\` | Endpoint search không được công bố nên route có thể không tồn tại. |
| Request bị từ chối bởi security | Gọi endpoint cần quyền nhưng user không đủ quyền | \`401\` hoặc \`403\` (cấu hình có thể che giấu bằng \`404\`) | Đây là vấn đề xác thực/phân quyền, không đồng nghĩa resource rỗng. |

Các status code là dấu hiệu đầu tiên để chẩn đoán, không phải bằng chứng duy nhất. Đặc biệt, cách vô hiệu hóa endpoint ảnh hưởng đến việc server trả về 404 hay 405.

## 2. Tài nguyên không tồn tại: HTTP 404

### Item resource không có dữ liệu tương ứng

Giả sử repository Person đã được export:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Nếu entity có ID 42 nhưng không có ID 9999:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

có thể trả về item representation:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "id": 42,
  "firstName": "Ada",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42"
    }
  }
}
~~~

Trong khi request:

~~~http
GET /api/people/9999
Accept: application/hal+json
~~~

thường trả về:

~~~http
HTTP/1.1 404 Not Found
~~~

Spring Data REST không tìm thấy entity để biểu diễn thành item resource. Client không nên xử lý response này như một collection rỗng, vì URI đang đại diện cho một item cụ thể.

### Repository resource không tồn tại hoặc không được export

Một request như:

~~~http
GET /api/unknown
~~~

có thể trả 404 nếu:

- Không có repository nào được export tại resource path đó.
- Repository bị ẩn bằng \`@RepositoryRestResource(exported = false)\`.
- Base path hoặc collection path trong request bị sai.
- Repository không được scan hoặc không được đăng ký trong ApplicationContext.
- Resource path thực tế đã được tùy chỉnh và client đang dùng URL cũ.

Trong trường hợp này, collection resource không được tìm thấy. Đây là khác biệt quan trọng với một collection hợp lệ nhưng không có item: collection rỗng vẫn có URI và GET thành công.

### Kiểm tra khi nhận 404

1. Đọc link từ API entry point hoặc response HAL gần nhất để lấy URI do server công bố.
2. Kiểm tra base path trong \`spring.data.rest.base-path\` hoặc \`RepositoryRestConfiguration\`.
3. Kiểm tra \`path\` và \`collectionResourceRel\` trên \`@RepositoryRestResource\`.
4. Kiểm tra repository có được scan, tạo bean và export theo repository detection strategy hiện tại không.
5. Nếu gọi item URI, kiểm tra identifier có tồn tại trong store không.
6. Kiểm tra endpoint có bị ẩn bởi \`exported = false\` hoặc security configuration không.

Không nên kết luận rằng database không có dữ liệu chỉ từ một response 404. Có thể request đang đi tới URI sai hoặc repository không được export.

## 3. Tập hợp rỗng: HTTP 200 với collection representation hợp lệ

### Collection resource vẫn tồn tại

Giả sử repository Person đã được export nhưng database chưa có Person nào. Request:

~~~http
GET /api/people
Accept: application/hal+json
~~~

vẫn truy cập một collection resource hợp lệ. Response có thể có dạng:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/people"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 0,
    "totalPages": 0,
    "number": 0
  }
}
~~~

Tùy phiên bản và representation, response collection rỗng có thể chứa \`"_embedded": {"people": []}\` hoặc không có \`_embedded\` khi không có resource nào để nhúng. Client cần chấp nhận cả hai dạng.

Điểm cốt lõi là collection resource đã tồn tại và request GET được xử lý thành công. Việc không có item không phải lỗi tìm resource.

### Search trả về rỗng

Ví dụ repository có query method được export:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByStatus(PersonStatus status);
}
~~~

Nếu search resource có relation \`byStatus\`, request:

~~~http
GET /api/people/search/byStatus?status=UNKNOWN
Accept: application/hal+json
~~~

có thể trả collection rỗng với status 200 khi query hợp lệ nhưng không tìm thấy bản ghi phù hợp.

Cần phân biệt:

- Search resource không tồn tại vì method không được export hoặc URI sai: có thể 404.
- Search resource tồn tại, query hợp lệ nhưng không có kết quả: 200 với kết quả rỗng.
- Query parameter không hợp lệ hoặc không chuyển đổi được: có thể 400 Bad Request.
- Request không có quyền truy cập: có thể 401/403 hoặc bị security che giấu.

### Collection rỗng và trang vượt quá giới hạn

Một trường hợp dễ nhầm khác là client yêu cầu một page index nằm ngoài số trang hiện có.

Ví dụ repository có 5 phần tử, page size là 2, nhưng client gọi:

~~~http
GET /api/people?page=9&size=2
Accept: application/hal+json
~~~

Server có thể trả 200 với nội dung trang hiện tại rỗng, nhưng metadata cho biết collection thực tế vẫn có dữ liệu:

~~~json
{
  "page": {
    "size": 2,
    "totalElements": 5,
    "totalPages": 3,
    "number": 9
  }
}
~~~

Đây không giống collection rỗng hoàn toàn:

| Metadata | Collection không có dữ liệu | Page index vượt quá phạm vi |
|---|---:|---:|
| \`totalElements\` | 0 | Lớn hơn 0 |
| \`totalPages\` | 0 (với page size dương) | Số trang thực tế lớn hơn 0 |
| Item trong trang hiện tại | 0 | 0 |
| Ý nghĩa | Không có kết quả cho collection/query | Collection có dữ liệu, nhưng trang được yêu cầu không chứa item |

Client nên kiểm tra \`totalElements\` và \`totalPages\`, không chỉ nhìn vào việc mảng item đang rỗng.

## 4. Phương thức bị tắt: resource có thể tồn tại nhưng thao tác không được phép

Spring Data REST có thể giới hạn những thao tác HTTP mà client được thực hiện trên collection hoặc item resource. Ví dụ, ứng dụng có thể cho phép GET nhưng tắt POST, PUT, PATCH hoặc DELETE.

Giả sử collection \`/api/people\` được export và GET hoạt động, nhưng POST đã bị vô hiệu hóa. Request:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "Ada",
  "lastName": "Lovelace"
}
~~~

có thể trả:

~~~http
HTTP/1.1 405 Method Not Allowed
Allow: GET, HEAD, OPTIONS
~~~

Header \`Allow\` (nếu server gửi) cho biết các HTTP method được hỗ trợ tại URI đó. Status 405 nói rằng server nhận diện được resource/URI nhưng method đang yêu cầu không được phép.

### Disable HTTP method bằng ExposureConfiguration

Có thể cấu hình exposure theo domain type và loại resource thông qua \`RepositoryRestConfigurer\`:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.HttpMethod;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;

@Configuration
class DataRestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getExposureConfiguration()
            .forDomainType(Person.class)
            .withCollectionExposure((metadata, methods) ->
                methods.disable(HttpMethod.POST))
            .withItemExposure((metadata, methods) ->
                methods.disable(
                    HttpMethod.PUT,
                    HttpMethod.PATCH,
                    HttpMethod.DELETE
                ));
    }
}
~~~

Ý nghĩa của cấu hình:

- \`withCollectionExposure\` điều chỉnh method trên collection resource, ví dụ \`POST /people\`.
- \`withItemExposure\` điều chỉnh method trên item resource, ví dụ \`PUT /people/42\`, \`PATCH /people/42\`, \`DELETE /people/42\`.
- GET vẫn có thể được phép để client đọc dữ liệu.
- Các method bị disable sẽ không được exporter cho phép theo cấu hình đó.

API và chữ ký callback cần tương thích với phiên bản Spring Data REST của dự án. Nếu đang dùng phiên bản cũ, kiểm tra Javadoc tương ứng trước khi áp dụng cấu hình.

### Tắt một query method hoặc resource bằng exported=false

Có một cách khác để không công bố endpoint: đánh dấu repository hoặc method là không export.

Ẩn một query method:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(exported = false)
    List<Person> findByInternalFlagTrue();
}
~~~

Ẩn toàn bộ repository:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalPersonRepository
        extends JpaRepository<InternalPerson, Long> {
}
~~~

Hai trường hợp này có phạm vi khác nhau:

- \`@RestResource(exported = false)\` trên method ẩn endpoint query method tương ứng.
- \`@RepositoryRestResource(exported = false)\` trên repository ẩn repository resource khỏi Spring Data REST.

Khi endpoint không được đăng ký, link search hoặc link resource tương ứng có thể không xuất hiện trong HAL. Gọi trực tiếp URI đó có thể trả 404 vì route không được export. Đây là khác biệt với việc một URI đã được nhận diện nhưng HTTP method bị cấm, vốn thường thể hiện bằng 405.

## 5. Phân biệt 404, 405, 401, 403 và 200

| Status | Diễn giải | Hành động chẩn đoán |
|---|---|---|
| \`200 OK\` | GET thành công; collection có thể có item hoặc rỗng. | Đọc \`_embedded\` và \`page.totalElements\`. |
| \`204 No Content\` | Request thành công nhưng không có response body, thường gặp ở một số thao tác ghi/xóa. | Kiểm tra method và hợp đồng response; không suy ra collection rỗng. |
| \`400 Bad Request\` | Request hoặc query parameter không hợp lệ, không chuyển đổi được hoặc vi phạm đầu vào. | Kiểm tra body, kiểu dữ liệu và query parameter. |
| \`401 Unauthorized\` | Chưa xác thực hoặc thông tin xác thực không hợp lệ. | Kiểm tra token, session hoặc cơ chế authentication. |
| \`403 Forbidden\` | Đã xác thực nhưng không có quyền thực hiện thao tác. | Kiểm tra authorization policy và quyền trên method/resource. |
| \`404 Not Found\` | URI hoặc item resource không được tìm thấy; endpoint có thể không được export. | Kiểm tra URI, repository export, identifier và security masking. |
| \`405 Method Not Allowed\` | URI được nhận diện nhưng HTTP method không được cho phép. | Kiểm tra method exposure và header \`Allow\`. |
| \`409 Conflict\` | Request xung đột với trạng thái hiện tại hoặc ràng buộc dữ liệu. | Kiểm tra trạng thái entity và quy tắc ghi. |

Không dùng riêng status code để kết luận về quyền truy cập. Một số cấu hình Spring Security cố ý trả 404 để che giấu sự tồn tại của resource. Trong tình huống đó, cần xem security filter chain, log và quyền của principal.

## 6. Đọc HAL để xác định endpoint có được công bố hay không

Collection response có thể cung cấp các link:

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

Client có thể dùng các link để khám phá API:

- Có \`self\`: collection resource hiện tại có URI được công bố.
- Có \`search\`: repository có search resource được công bố.
- Có các relation tới query method: client có thể khám phá các search endpoint cụ thể.
- Không thấy link của một method: có thể method không được export, nhưng cũng cần xem profile, cấu hình và loại representation trước khi kết luận.

HAL là tài liệu khám phá API, không phải cơ chế authorization. Việc một link không xuất hiện không đảm bảo client không thể gọi URI trực tiếp; server vẫn phải thực thi export rules và security rules.

### Dùng OPTIONS và Allow

Khi nghi ngờ một HTTP method bị tắt, có thể thử:

~~~http
OPTIONS /api/people
~~~

Nếu server trả header \`Allow\`, danh sách đó giúp xác định method được chấp nhận tại resource. Với request POST/PUT/PATCH/DELETE trả 405, cũng nên lưu header \`Allow\`.

Hành vi OPTIONS phụ thuộc cấu hình MVC, CORS, servlet container và security. Nếu OPTIONS không cho kết quả rõ ràng, dùng response 405 và kiểm tra exposure configuration trong ứng dụng.

## 7. Kiểm tra bằng curl

Lấy collection:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people
~~~

Lấy một item có thể tồn tại:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/42
~~~

Lấy một item không tồn tại:

~~~bash
curl -i -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/9999
~~~

Gọi search resource:

~~~bash
curl -i -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people/search/byStatus?status=UNKNOWN"
~~~

Kiểm tra method trên collection:

~~~bash
curl -i -X OPTIONS \
  http://localhost:8080/api/people
~~~

Thử method ghi trong môi trường kiểm thử:

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/hal+json" \
  -d '{"firstName":"Ada","lastName":"Lovelace"}' \
  http://localhost:8080/api/people
~~~

Khi kiểm tra các thao tác ghi, chỉ dùng dữ liệu và môi trường thử nghiệm phù hợp. Mục đích ở đây là quan sát status, header và cách exporter phản hồi theo cấu hình.

## 8. Quy trình chẩn đoán theo response

### Trường hợp A: GET trả 404

1. Kiểm tra URL có đúng base path và collection path không.
2. Kiểm tra link \`self\` hoặc relation từ API entry point.
3. Nếu là item, xác minh identifier có tồn tại không.
4. Nếu là repository/search endpoint, kiểm tra repository hoặc method có được export không.
5. Kiểm tra security có đang che giấu resource bằng 404 không.

### Trường hợp B: GET trả 200 nhưng không có item

1. Xác định request gọi collection hay search endpoint.
2. Kiểm tra \`_embedded\` có rỗng hoặc không xuất hiện không.
3. Nếu có \`page\`, đọc \`totalElements\`, \`totalPages\` và \`number\`.
4. Kiểm tra filter/query parameter và dữ liệu thực tế.
5. Nếu \`totalElements > 0\` nhưng trang hiện tại không có item, kiểm tra page index có vượt phạm vi không.

### Trường hợp C: POST/PUT/PATCH/DELETE trả 405

1. Xác nhận GET tới cùng resource có hoạt động không.
2. Đọc header \`Allow\` nếu có.
3. Kiểm tra \`ExposureConfiguration\` của domain type.
4. Kiểm tra repository detection, annotation export và method exposure.
5. Kiểm tra request có gọi đúng collection URI hoặc item URI không.

### Trường hợp D: Endpoint trả 404 sau khi disable

1. Kiểm tra có dùng \`@RestResource(exported = false)\` trên query method không.
2. Kiểm tra repository có \`@RepositoryRestResource(exported = false)\` không.
3. Kiểm tra URI search/resource có còn được đăng ký trong mapping không.
4. Phân biệt route không được công bố với route có tồn tại nhưng method không được phép.

## 9. Thiết kế client xử lý đúng ba tình huống

Client nên phân nhánh theo HTTP status và cấu trúc response:

- **200 với item:** parse representation của entity và dùng link \`self\`.
- **200 với collection rỗng:** hiển thị trạng thái không có kết quả; không báo lỗi kết nối hoặc resource không tồn tại.
- **200 với trang rỗng nhưng totalElements lớn hơn 0:** thông báo trang hiện tại không có item hoặc điều chỉnh page index.
- **404:** thông báo resource/item không được tìm thấy, đồng thời cho phép xử lý URL cũ hoặc identifier không hợp lệ.
- **405:** thông báo thao tác không được hỗ trợ trên resource; không lặp lại request với cùng method.
- **401/403:** xử lý xác thực hoặc quyền truy cập.
- **400:** hiển thị lỗi đầu vào hoặc query parameter.

Không nên biến mọi response không có item thành cùng một trạng thái UI. Một trang tìm kiếm không có kết quả có thể là kết quả hợp lệ; một item không tồn tại là một trạng thái khác; một thao tác bị cấm cần thông báo rằng hành động đó không được hỗ trợ.

## 10. Những nhầm lẫn thường gặp

1. **Coi 404 là collection rỗng.** 404 nói rằng URI hoặc item resource không được tìm thấy; collection rỗng thường trả 200.
2. **Coi 200 không có \`_embedded\` là lỗi.** Collection rỗng có thể không có trường \`_embedded\`, tùy representation.
3. **Chỉ kiểm tra mảng item mà bỏ qua page metadata.** Trang vượt phạm vi có thể rỗng dù collection vẫn có dữ liệu.
4. **Coi 405 giống 404.** 405 thường cho biết URI được nhận diện nhưng method không được phép; 404 có thể là route không tồn tại hoặc bị che giấu.
5. **Coi mọi \`exported=false\` đều trả 405.** Khi method hoặc resource không được đăng ký, direct URI có thể trả 404.
6. **Coi 403 là method bị disable.** 403 thường liên quan đến authorization; method exposure và security là hai lớp khác nhau.
7. **Dựa vào link HAL để bảo vệ endpoint.** Ẩn link không thay thế việc server từ chối request không hợp lệ hoặc không có quyền.
8. **Không kiểm tra header Allow.** Header này có thể giúp xác định các method hợp lệ tại URI.
9. **Dựng URL thủ công rồi kết luận endpoint không tồn tại.** Hãy lấy href từ response và kiểm tra relation thực tế.
10. **Không phân biệt query không có kết quả với query endpoint không được export.** Một endpoint search hợp lệ có thể trả collection rỗng; endpoint không được công bố có thể không có route.

## 11. Checklist khi đưa vào production

- Collection GET trả representation ổn định ngay cả khi không có dữ liệu.
- Client xử lý được cả \`_embedded\` rỗng và trường hợp \`_embedded\` không xuất hiện.
- Item không tồn tại được xử lý như 404.
- Search không có kết quả được xử lý như collection rỗng.
- Page metadata được dùng để phân biệt collection thực sự rỗng với page index vượt phạm vi.
- HTTP method không cần thiết được disable tại đúng collection/item exposure.
- Query method hoặc repository không công khai được đánh dấu \`exported=false\` khi phù hợp.
- Security vẫn kiểm tra quyền ở server; việc ẩn link không được xem là bảo vệ.
- API documentation mô tả status code và method được hỗ trợ.
- Integration test kiểm tra cả status, headers và body representation.

## Tóm tắt

Tài nguyên không tồn tại thường thể hiện bằng 404. Collection resource tồn tại nhưng không có item vẫn là request GET thành công và thường trả 200 với representation rỗng. Phương thức bị tắt thường trả 405 khi URI được nhận diện nhưng HTTP method không được phép; nếu endpoint đã bị loại khỏi export bằng \`exported=false\`, URI có thể không còn được đăng ký và trả 404.

Khi chẩn đoán, hãy kết hợp status code, header \`Allow\`, HAL links, \`_embedded\`, page metadata, export configuration và security configuration. Cách này giúp xác định đúng liệu client đang gọi sai URI, không có dữ liệu, đang yêu cầu trang rỗng hay thực hiện một thao tác mà API không công bố.

## Tài liệu tham khảo

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Repository Resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Configuring the REST URL Path and Exposure](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfiguration.html)
- [Spring Framework — HTTP Status Codes](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-exceptionhandler.html)
