# GET tài nguyên gốc và xác định các repository đang được công bố trong Spring Data REST

## Mục tiêu

Spring Data REST tự động xuất các Spring Data repository thành REST resources và mặc định biểu diễn phản hồi theo HAL (Hypertext Application Language). Client có thể bắt đầu khám phá API bằng cách gửi HTTP GET tới **tài nguyên gốc (API root)**. Phản hồi root chứa các liên kết dẫn tới những tài nguyên cấp tiếp theo, thường là collection resource của các repository được công bố.

Thay vì phải biết trước mọi đường dẫn như `/employees`, `/orders` hay `/products`, client đọc `_links` trong phản hồi root, nhận diện relation và theo URL `href` tương ứng. Đây là cơ chế discoverability của HATEOAS.

Bài này tập trung vào cách gọi API root, đọc HAL, nhận biết repository collection, phân biệt link repository với link metadata, và xử lý trường hợp một repository không xuất hiện trong danh sách.

## 1. API root là điểm bắt đầu khám phá

Giả sử ứng dụng chạy tại `http://localhost:8080`. Nếu không cấu hình base path riêng, root resource của Spring Data REST thường nằm tại:

~~~http
GET /
Accept: application/hal+json
~~~

Dùng curl để xem cả status code và response headers:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
~~~

Nếu ứng dụng cấu hình base path, ví dụ:

~~~properties
spring.data.rest.base-path=/api
~~~

thì gọi root của Spring Data REST tại:

~~~http
GET /api
Accept: application/hal+json
~~~

Nếu ứng dụng còn cấu hình servlet context path, chẳng hạn `server.servlet.context-path=/myapp`, URL bên ngoài sẽ bao gồm cả context path và Spring Data REST base path, ví dụ `/myapp/api`.

Một phản hồi root điển hình có thể trông như sau:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "_links": {
    "employees": {
      "href": "http://localhost:8080/api/employees"
    },
    "orders": {
      "href": "http://localhost:8080/api/orders"
    },
    "profile": {
      "href": "http://localhost:8080/api/alps"
    }
  }
}
~~~

Trong ví dụ này:

- `employees` và `orders` là relation dẫn tới collection resource của hai repository được công bố.
- Giá trị `href` là URL collection mà client cần gọi tiếp.
- `profile` là liên kết tới metadata mô tả API theo ALPS, không phải repository collection.

Số lượng và tên liên kết phụ thuộc vào repository thực tế và cấu hình export của ứng dụng. Không nên giả định root luôn có đúng các relation trong ví dụ.

## 2. Đọc cấu trúc HAL trong phản hồi root

HAL đặt các liên kết trong thuộc tính `_links`. Mỗi key trong `_links` là một **link relation (rel)**; giá trị tương ứng là một object chứa URL và có thể có thêm metadata của link.

Ví dụ:

~~~json
{
  "_links": {
    "employees": {
      "href": "http://localhost:8080/api/employees"
    }
  }
}
~~~

Có thể đọc theo cách sau:

| Thành phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `_links` | Object | Tập hợp các liên kết HAL của tài nguyên root. |
| `employees` | Relation | Tên quan hệ mô tả tài nguyên collection tiếp theo. |
| `href` | URL | Địa chỉ thực tế để client điều hướng tới collection. |

**Relation và path không nhất thiết giống nhau.** Ví dụ relation có thể là `staff`, trong khi path lại là `/employees`. Vì thế client nên dùng `href` được trả về, không tự nối `/api/` với tên relation.

Một số response có thể có link bổ sung như `profile`, `curies` hoặc link dành cho chức năng khác. Không phải mọi key trong `_links` đều là repository. Hãy hiểu ý nghĩa relation theo HAL và tài liệu API; với Spring Data REST, `profile` là link metadata ở cấp root.

## 3. Repository nào xuất hiện trong root?

Spring Data REST tạo collection resource cho repository được export. Mặc định, tên collection và relation được suy ra từ tên đơn giản của domain class, chuyển thành chữ thường và số nhiều theo quy tắc đặt tên của framework.

Ví dụ:

~~~java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Nếu repository được phát hiện và export, collection resource mặc định có thể là:

~~~text
/employees
~~~

Đường dẫn và relation có thể được tùy chỉnh bằng `@RepositoryRestResource`:

~~~java
@RepositoryRestResource(
        path = "employees",
        collectionResourceRel = "staff"
)
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
~~~

Với cấu hình này, root có thể chứa:

~~~json
{
  "_links": {
    "staff": {
      "href": "http://localhost:8080/api/employees"
    }
  }
}
~~~

Ở đây `staff` là relation name; `/api/employees` là path. Hai giá trị được cấu hình riêng:

- `path`: đoạn đường dẫn dùng để truy cập collection resource.
- `collectionResourceRel`: tên relation được dùng khi liên kết tới collection trong HAL.

Do đó, khi kiểm tra một ứng dụng, hãy ghi nhận cả rel và href. Đừng suy ra tên repository Java hoặc đường dẫn chỉ từ một trong hai giá trị.

## 4. Theo link từ root tới collection resource

Sau khi đọc root, client gọi URL trong `href` của relation mong muốn:

~~~http
GET /api/employees
Accept: application/hal+json
~~~

Collection resource trả về các entity được quản lý bởi repository, cùng những link liên quan. Ví dụ:

~~~json
{
  "_embedded": {
    "employees": [
      {
        "firstName": "Lan",
        "lastName": "Pham",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/employees/12"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/employees?page=0&size=20"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/employees"
    },
    "search": {
      "href": "http://localhost:8080/api/employees/search"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

Những liên kết ở cấp collection có ý nghĩa riêng:

- `self`: URL của collection hiện tại, có thể bao gồm tham số phân trang.
- `profile`: metadata mô tả collection/domain resource.
- `search`: xuất hiện nếu repository có query methods được công bố.

`search` thường nằm trong phản hồi collection, không phải danh sách collection ở API root. Client đi tiếp bằng `href` của link `search`, rồi đọc danh sách query method resources ở đó.

Tương tự, các link association như `department`, `manager` hoặc `roles` thường xuất hiện trong item resource. Root không phải nơi liệt kê toàn bộ item, association và query method của mọi repository; nó là điểm bắt đầu để khám phá từng nhánh.

## 5. Xác định repository đang được công bố

Khi kiểm tra API, có thể lập danh sách repository collection từ các link ở root:

| Relation trong `_links` | Href | Kết luận |
| --- | --- | --- |
| `employees` | `/api/employees` | Collection resource được công bố với relation employees. |
| `staff` | `/api/employees` | Cùng path employees nhưng relation tùy chỉnh thành staff. |
| `orders` | `/api/orders` | Collection resource orders được công bố. |
| `profile` | `/api/alps` | Link metadata ALPS, không phải repository collection. |

Một quy trình thực tế:

1. Gọi root URL đúng với base path và context path của ứng dụng.
2. Kiểm tra status code và content type. Với HAL, response thường có `Content-Type: application/hal+json`.
3. Đọc các relation trong `_links`.
4. Nhận diện relation repository collection và lấy `href` tương ứng.
5. Gọi từng `href` để xác nhận collection resource và xem các link cấp tiếp theo.
6. Ở collection, kiểm tra `search` nếu cần khám phá query methods; ở item, kiểm tra các link association.

Danh sách relation và href thu được từ root là bằng chứng runtime cho những collection resource được Spring Data REST công bố tại thời điểm gọi. Đây là cách đáng tin cậy để client khám phá API mà không phải hardcode danh sách endpoint.

## 6. Vì sao một repository không xuất hiện?

Không phải mọi interface repository trong source code đều tự động trở thành link ở API root. Việc phát hiện repository và cấu hình export quyết định repository nào được công bố.

Ví dụ, có thể ẩn toàn bộ repository bằng `exported = false`:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

Repository này không được công bố như một collection resource qua Spring Data REST, vì vậy client không nên mong đợi relation tương ứng trong root.

Ngoài annotation, cần kiểm tra các yếu tố sau khi một repository không xuất hiện:

- Repository interface có nằm trong package được Spring Data scan hay không.
- Repository có được phát hiện theo `RepositoryDetectionStrategy` đang cấu hình hay không.
- `@RepositoryRestResource(exported = false)` có được đặt trên repository không.
- Cấu hình export tùy chỉnh có loại repository khỏi REST API không.
- Ứng dụng có đang chạy đúng profile, module và cấu hình base path không.
- Spring Security có chặn request root hoặc collection không.

Cũng cần phân biệt việc export repository với việc export từng method. Một repository collection có thể được phát hiện, nhưng một số thao tác HTTP có thể không được hỗ trợ nếu method nền tảng tương ứng không có hoặc đã bị ẩn bằng `@RestResource(exported = false)`. Ví dụ, tài liệu Spring Data REST quy định GET collection cần một phương thức `findAll(...)` được export; nếu không, GET collection có thể trả `405 Method Not Allowed`.

Vì vậy, thấy link ở root chứng minh collection resource được công bố, nhưng không có nghĩa mọi HTTP method trên collection đều khả dụng.

## 7. Phân biệt các loại link trong quá trình khám phá

| Nơi xuất hiện | Link thường gặp | Ý nghĩa |
| --- | --- | --- |
| API root | Relation như `employees`, `orders` | Đi tới repository collection resource. |
| API root | `profile` | Metadata ALPS ở cấp API. |
| Collection resource | `self` | Collection hiện tại, có thể kèm paging/sorting parameters. |
| Collection resource | `profile` | Metadata cho collection/domain resource. |
| Collection resource | `search` | Trang liệt kê query methods được export. |
| Search resource | Relation theo tên query method | Đi tới query method resource. |
| Item resource | `self` | Item hiện tại. |
| Item resource | Relation theo thuộc tính association | Đi tới association resource. |

Ví dụ, nếu root trả `employees`, client đi tới collection; collection trả `search`, client đi tới search; search trả `byDepartment`, client tiếp tục theo link của query method đó. Mỗi bước đều dựa trên relation và href của response hiện tại.

Không nên nhầm `profile` với collection path, `search` với một repository độc lập, hoặc association link với root repository link.

## 8. Gọi API root bằng công cụ và client

### curl

~~~bash
curl -i   -H "Accept: application/hal+json"   http://localhost:8080/api
~~~

### HTTP client

Trong Postman, Insomnia hoặc REST Client:

- Method: `GET`
- URL: `http://localhost:8080/api`
- Header: `Accept: application/hal+json`

Mở response body và tìm `_links`. Nếu công cụ hiển thị JSON tree, mở từng relation rồi lấy trường `href`.

### JavaScript fetch

~~~javascript
const response = await fetch("http://localhost:8080/api", {
  headers: {
    Accept: "application/hal+json"
  }
});

if (!response.ok) {
  throw new Error(`API root returned HTTP ${response.status}`);
}

const root = await response.json();

for (const [rel, link] of Object.entries(root._links ?? {})) {
  console.log(rel, link.href);
}
~~~

Ví dụ trên chỉ in các relation và URL để quan sát. Trong client thực tế, nên phân biệt các relation theo hợp đồng API và theo link đang cần sử dụng, thay vì coi mọi link ở root đều là collection.

Nếu link object có `templated: true`, đó là URI template và client phải mở rộng template theo quy tắc URI Template trước khi gọi. Đừng xử lý mọi `href` như một URL hoàn chỉnh nếu HAL đánh dấu link là templated.

## 9. Kiểm thử API root bằng MockMvc

Có thể kiểm tra root resource bằng Spring MVC Test. Ví dụ dưới đây xác nhận API root trả HTTP 200 và có link relation `staff`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class RepositoryRootResourceTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rootListsExportedEmployeeCollection() throws Exception {
        mockMvc.perform(get("/api")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaTypes.HAL_JSON))
            .andExpect(jsonPath("$._links.staff.href")
                    .value(containsString("/api/employees")));
    }
}
~~~

Nếu dùng relation mặc định hoặc cấu hình khác, thay `staff` và path kỳ vọng theo `@RepositoryRestResource` của ứng dụng.

Có thể kiểm tra repository bị ẩn không xuất hiện:

~~~java
mockMvc.perform(get("/api")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.internalAudit").doesNotExist());
~~~

Bài test nên sử dụng cấu hình Spring Data REST thực tế của ứng dụng, bao gồm base path, repository detection strategy và security. Nếu endpoint yêu cầu đăng nhập, test cần cung cấp principal/role thích hợp.

## 10. Xử lý các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| GET `/` trả 404 | Spring Data REST có base path hoặc context path khác | Kiểm tra `spring.data.rest.base-path` và `server.servlet.context-path`; gọi đúng root. |
| GET `/api` trả 404 | Base path chưa được cấu hình hoặc ứng dụng chưa triển khai Spring Data REST tại path đó | Kiểm tra dependency, cấu hình và mapping runtime. |
| GET root trả 401/403 | Spring Security yêu cầu đăng nhập hoặc thiếu quyền | Gửi thông tin xác thực và kiểm tra security rules. |
| Root không có relation mong đợi | Repository không được scan, không được phát hiện hoặc bị đánh dấu không export | Kiểm tra package scan, detection strategy và `exported`. |
| Relation có tên khác dự kiến | `collectionResourceRel` đã được tùy chỉnh | Đọc key thực tế trong `_links` và dùng href. |
| GET collection trả 405 | Collection có thể được export nhưng phương thức đọc `findAll` không khả dụng hoặc bị ẩn | Kiểm tra repository methods và `@RestResource(exported = false)`. |
| Link sai host hoặc scheme sau reverse proxy | Proxy headers hoặc forwarded-header configuration chưa phù hợp | Kiểm tra cấu hình proxy và URL tuyệt đối được sinh ra. |
| Không thấy query method ở root | Query methods được liệt kê ở resource `search` của collection | Theo link collection rồi theo `search`. |

## 11. Nguyên tắc khi xây dựng client HATEOAS

1. Bắt đầu từ root URL do cấu hình ứng dụng cung cấp.
2. Dùng `Accept: application/hal+json` để yêu cầu biểu diễn HAL.
3. Dựa vào relation để hiểu mục đích của link.
4. Theo đúng `href` được trả về; tránh tự dựng URL từ tên class hoặc tên relation.
5. Khám phá search và association tại resource cấp tương ứng.
6. Xử lý trường hợp link không tồn tại, request bị từ chối hoặc endpoint trả status code không thành công.
7. Không giả định tên relation, hostname, port hay base path cố định giữa các môi trường.

Cách tiếp cận này giúp client ít phụ thuộc vào cấu trúc nội bộ của repository và chịu được thay đổi path hoặc relation khi server vẫn duy trì hợp đồng hypermedia.

## Tài liệu tham khảo

- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): mục “Resource Discoverability” mô tả GET root URL, HAL `_links`, collection, item và search resources.
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): cấu hình repository exposure và resource mappings.
- [Spring Data REST — Getting Started: Accessing JPA Data with REST](https://spring.io/guides/gs/accessing-data-rest): ví dụ response HAL, collection links và profile/search relations.
- [Spring Data REST — Spring project overview](https://spring.io/projects/spring-data-rest/): tổng quan repository resources, HAL, ALPS và discoverability.
