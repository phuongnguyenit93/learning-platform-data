# Collection resource của repository

## Mục tiêu

Sau bài này, bạn có thể giải thích collection resource mà Spring Data REST tạo ra từ một repository, phân biệt collection resource với item resource, cấu hình URI path và relation bằng `@RepositoryRestResource`, công bố truy vấn tìm kiếm bằng `@RestResource`, đọc cấu trúc HAL có embedded items và links, đồng thời kiểm soát phân trang, sắp xếp và phạm vi repository được export.

## 1. Spring Data REST biến repository thành tài nguyên HTTP

Spring Data REST xây dựng REST API trên các Spring Data repository. Khi repository được export, framework tự tạo endpoint cho collection và từng item, đồng thời công bố các liên kết hypermedia để client khám phá tài nguyên.

Ví dụ repository quản lý `Person` có thể tự động cung cấp:

| Request | Tài nguyên hoặc hành động |
|---|---|
| `GET /people` | Đọc collection people |
| `POST /people` | Tạo một person mới |
| `GET /people/{id}` | Đọc một person |
| `PUT /people/{id}` | Thay thế dữ liệu person |
| `PATCH /people/{id}` | Cập nhật một phần person |
| `DELETE /people/{id}` | Xóa person |
| `GET /people/search` | Khám phá các truy vấn tìm kiếm được export |

Các đường dẫn cụ thể phụ thuộc cấu hình repository, base path và loại ID. Spring Data REST tạo những endpoint này từ metadata của repository; bạn không cần viết controller CRUD thủ công cho từng thao tác cơ bản.

**Collection resource** đại diện cho một tập hợp tài nguyên cùng các khả năng điều hướng liên quan. **Item resource** đại diện cho một phần tử cụ thể trong collection. Hai loại tài nguyên có cấu trúc và mục đích khác nhau.

## 2. Khai báo repository được export

Giả sử ứng dụng quản lý danh bạ. Entity `Person` có ID, tên và họ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "people")
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;

    protected Person() {
    }

    public Person(String firstName, String lastName) {
        this.firstName = firstName;
        this.lastName = lastName;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    }

    public void setLastName(String lastName) {
        this.lastName = lastName;
    }
}
```

Repository:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(
        collectionResourceRel = "people",
        path = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Hai thuộc tính trong `@RepositoryRestResource` có vai trò riêng:

- `path = "people"` xác định path segment của collection resource, nên endpoint collection là `/people`.
- `collectionResourceRel = "people"` xác định relation dùng khi liên kết đến collection và khi đặt các item trong `_embedded`.

Nếu không khai báo, Spring Data REST suy ra path và relation từ domain type theo quy tắc mặc định. Với API public, khai báo tường minh giúp URL và relation ít bị ảnh hưởng bởi việc đổi tên class Java.

Repository phải nằm trong phạm vi package được Spring Data scan. Ứng dụng cũng cần cấu hình Spring Data REST và module repository tương ứng, ví dụ Spring Data JPA cùng Spring Data REST starter trong ứng dụng Spring Boot.

## 3. Collection resource khác item resource

Khi client gọi `GET /people`, Spring Data REST trả collection representation. Khi client gọi `GET /people/42`, framework trả representation của một item cụ thể.

Collection resource có thể chứa:

- `_embedded`: các item thuộc collection.
- `_links.self`: link đến collection hiện tại.
- `_links.profile`: link đến profile mô tả cấu trúc hoặc semantics của resource.
- `_links.search`: link đến các truy vấn tìm kiếm được export.
- `page`: metadata phân trang khi kết quả được phân trang.

Item resource thường chứa dữ liệu của một `Person` cùng các link như `self` và link liên quan đến collection.

Ví dụ response HAL minh họa cho `GET /people`:

```json
{
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/1"
          }
        }
      },
      {
        "firstName": "Binh",
        "lastName": "Tran",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/2"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people{?page,size,sort}",
      "templated": true
    },
    "profile": {
      "href": "http://localhost:8080/profile/people"
    },
    "search": {
      "href": "http://localhost:8080/people/search"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 2,
    "totalPages": 1,
    "number": 0
  }
}
```

Đây là response minh họa; host, số lượng link và metadata thực tế phụ thuộc cấu hình, dữ liệu và phiên bản Spring Data REST.

Điểm quan trọng là collection không được biểu diễn như một JSON array trần. HAL bọc các item trong `_embedded` và cung cấp `_links` ở cấp collection. Client có thể khám phá trang tiếp theo hoặc endpoint tìm kiếm từ response mà không cần tự đoán URL.

## 4. Khám phá repository từ API root

Spring Data REST có thể công bố các repository được export tại API root. Với repository trên, request:

```http
GET /
Accept: application/hal+json
```

có thể trả link đến collection:

```json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/people"
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
```

Relation `people` xuất phát từ `collectionResourceRel`. Client bắt đầu ở root, tìm relation cần thiết rồi theo `href` để đến collection resource.

Nếu ứng dụng đặt base path:

```yaml
spring:
  data:
    rest:
      base-path: /api
```

thì collection có thể nằm ở `/api/people`. Các link do Spring Data REST tạo sẽ phản ánh base path được cấu hình. Client nên theo các link trong response thay vì hard-code `/people`.

## 5. Tùy chỉnh path và relation

`path` và relation là hai phần khác nhau của hợp đồng:

| Cấu hình | Ảnh hưởng |
|---|---|
| `path` | URI path của collection resource |
| `collectionResourceRel` | Relation dùng để khám phá collection và đặt collection trong HAL |
| `exported` | Quyết định repository có được công bố hay không |

Ví dụ, nếu domain class tên `Person` nhưng API muốn dùng tên `contacts`:

```java
@RepositoryRestResource(
        path = "contacts",
        collectionResourceRel = "contacts"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

Collection được truy cập qua `/contacts`, và relation collection là `contacts`. Đổi path không làm đổi tên class Java hoặc bảng database.

Đừng nhầm relation với endpoint path. `contacts` trong `_links` là ngữ nghĩa của liên kết; `/contacts` là URI cụ thể mà server đang dùng. Hai giá trị có thể giống nhau nhưng chúng phục vụ hai mục đích khác nhau.

## 6. Công bố truy vấn tìm kiếm của repository

Spring Data REST có thể export các query method trong repository dưới một search resource. Ví dụ tìm người theo họ:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
        collectionResourceRel = "people",
        path = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    @RestResource(
            path = "by-last-name",
            rel = "byLastName"
    )
    Page<Person> findByLastName(
            @Param("name") String lastName,
            Pageable pageable
    );
}
```

Spring Data REST công bố truy vấn này dưới search resource:

```http
GET /people/search
Accept: application/hal+json
```

Search resource liệt kê các query method được export. Client có thể thấy relation `byLastName` và theo link đến truy vấn tương ứng.

Request tìm người theo họ:

```http
GET /people/search/by-last-name?name=Nguyen&page=0&size=20
Accept: application/hal+json
```

Ý nghĩa annotation:

- `@RestResource(path = "by-last-name")` đặt path của query endpoint.
- `rel = "byLastName"` đặt tên relation mà search resource công bố.
- `@Param("name")` xác định tên query parameter nhận giá trị họ.
- `Pageable` cho phép truy vấn trả kết quả theo trang.

Nếu không tùy chỉnh bằng `@RestResource`, Spring Data REST suy ra path và relation từ tên phương thức repository. Đặt tên tường minh khi client cần một relation ổn định, dễ hiểu.

## 7. Phân trang và sắp xếp collection

Collection resource có thể được phân trang. Các query parameter mặc định thường dùng:

- `page`: chỉ số trang, mặc định bắt đầu từ 0.
- `size`: số phần tử tối đa trong trang.
- `sort`: thuộc tính và hướng sắp xếp.

Ví dụ:

```http
GET /people?page=0&size=20&sort=lastName,asc
Accept: application/hal+json
```

Spring Data REST trả các item của trang hiện tại cùng metadata:

```json
{
  "_embedded": {
    "people": []
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/people?page=0&size=20&sort=lastName,asc"
    },
    "next": {
      "href": "http://localhost:8080/people?page=1&size=20&sort=lastName,asc"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 85,
    "totalPages": 5,
    "number": 0
  }
}
```

Các relation `first`, `prev`, `self`, `next` và `last` xuất hiện tùy vị trí trang. Client nên theo href do server cung cấp; không tự ghép URL hoặc tự tính số trang tiếp theo.

Có thể điều chỉnh chính sách phân trang trong cấu hình Spring Boot:

```yaml
spring:
  data:
    rest:
      default-page-size: 20
      max-page-size: 100
```

`default-page-size` được dùng khi client không truyền `size`. `max-page-size` giới hạn số phần tử tối đa server chấp nhận cho một request. Giá trị mặc định và giới hạn nên được chọn dựa trên chi phí truy vấn, kích thước representation và khả năng của client.

Nếu thay đổi tên tham số page, size hoặc sort, cần cập nhật tài liệu API và kiểm thử các link được sinh ra. Không nên giả định client luôn dùng tên query parameter mặc định nếu ứng dụng đã tùy chỉnh cấu hình.

## 8. Collection resource và dữ liệu nhúng

Relation collection quyết định tên khóa trong `_embedded`. Với:

```java
@RepositoryRestResource(
        collectionResourceRel = "people",
        path = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

các item được nhúng dưới `_embedded.people`.

Đây là một phần của hợp đồng hypermedia. Nếu đổi relation thành `contacts`, client đang đọc `_embedded.people` có thể không tìm thấy collection nữa dù dữ liệu entity không thay đổi.

Không nên nhúng toàn bộ quan hệ entity chỉ vì Spring Data REST có thể phát hiện association. Hãy xem xét dữ liệu nào được phép công bố, kích thước response và khả năng truy cập của client. Với quan hệ cần điều hướng riêng, Spring Data REST thường công bố link đến tài nguyên liên quan; client có thể theo link đó khi cần.

Các liên kết association và dữ liệu nhúng cũng chịu ảnh hưởng của cấu hình repository, projection, Jackson và quyền truy cập. Hãy kiểm thử response thực tế thay vì giả định mọi quan hệ JPA đều xuất hiện trực tiếp trong `_embedded`.

## 9. Kiểm soát repository nào được export

Không phải repository nào trong ứng dụng cũng nên trở thành API public. Có thể tắt export ở cấp repository:

```java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
```

Có thể ẩn một query method riêng:

```java
@RestResource(exported = false)
List<Person> findByInternalFlagTrue();
```

Khi một method không được export, client không thể gọi nó thông qua endpoint repository tương ứng. Điều này giúp giới hạn bề mặt API, nhưng không thay thế authorization.

Nếu repository được export, hãy cấu hình Spring Security để kiểm soát ai được đọc collection, tạo item, cập nhật hoặc xóa tài nguyên. Không dựa vào việc một link có xuất hiện hay không để bảo vệ dữ liệu; server phải kiểm tra quyền ở từng request.

Cũng cần cân nhắc các method kế thừa từ `CrudRepository` hoặc `JpaRepository`. Spring Data REST có quy tắc export mặc định cho các thao tác repository. Nếu một thao tác không phù hợp với hợp đồng hoặc chính sách bảo mật, hãy cấu hình rõ ràng thay vì giả định client sẽ không tìm thấy endpoint đó.

## 10. Projection và hình dạng item trong collection

Mặc định, representation của item phản ánh các thuộc tính được Spring Data REST expose từ domain object. Nếu collection cần một góc nhìn gọn hơn, có thể dùng projection để công bố một tập trường cụ thể.

Ví dụ projection:

```java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "summary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
```

Client có thể yêu cầu projection đã đăng ký:

```http
GET /people?projection=summary
Accept: application/hal+json
```

Projection thay đổi hình dạng dữ liệu item trong representation; collection resource vẫn giữ vai trò tập hợp cùng links và metadata phân trang.

Projection không phải cơ chế phân quyền. Nếu một trường nhạy cảm không được phép truy cập, cần kiểm soát việc expose ở domain/API và authorization, không chỉ dựa vào việc client không chọn projection chứa trường đó.

## 11. Kiểm thử collection resource

Có thể kiểm tra endpoint Spring Data REST bằng MockMvc trong một test context có repository và cấu hình Spring Data REST.

Ví dụ kiểm tra collection HAL:

```java
mockMvc.perform(get("/people")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
            MediaTypes.HAL_JSON))
    .andExpect(jsonPath("$._embedded.people").isArray())
    .andExpect(jsonPath("$._links.self.href").exists())
    .andExpect(jsonPath("$._links.search.href").exists())
    .andExpect(jsonPath("$.page.number").value(0));
```

Kiểm tra search resource:

```java
mockMvc.perform(get("/people/search")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.byLastName.href").exists());
```

Kiểm tra query endpoint:

```java
mockMvc.perform(get("/people/search/by-last-name")
        .param("name", "Nguyen")
        .param("page", "0")
        .param("size", "10")
        .accept(MediaTypes.HAL_JSON))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._embedded.people").isArray())
    .andExpect(jsonPath("$._links.self.href")
            .value(containsString("name=Nguyen")));
```

Các assertion trên giả định repository method được export với relation `byLastName`, collection relation là `people` và ứng dụng dùng HAL. Hãy điều chỉnh theo base path, cấu hình relation và response thực tế của dự án.

Nên kiểm tra thêm:

1. API root có relation `people` trỏ đến collection.
2. Collection rỗng vẫn giữ cấu trúc và relation theo hợp đồng.
3. Item trong `_embedded.people` có self link hợp lệ.
4. `page`, `size` và `sort` được áp dụng đúng.
5. Link điều hướng giữ lại query parameter tìm kiếm khi phù hợp.
6. Query method bị đánh dấu `exported = false` không xuất hiện trong search resource.
7. Repository bị tắt export không được công bố ở API root.
8. Người dùng không có quyền nhận status phù hợp khi truy cập collection hoặc item.

## 12. Những lỗi thường gặp

**Nhầm collection resource với JSON array.** Spring Data REST trả một hypermedia resource có `_embedded`, `_links` và có thể có metadata phân trang. Client cần đọc cấu trúc HAL.

**Nhầm path với relation.** `path` xác định URI; `collectionResourceRel` xác định tên relation. Đổi một giá trị không nhất thiết đổi giá trị còn lại.

**Đổi tên repository hoặc domain class làm thay đổi hợp đồng.** Nếu dựa hoàn toàn vào tên suy ra, refactor Java có thể ảnh hưởng path hoặc relation mặc định. Khai báo tường minh cho API public.

**Cho rằng search resource tự công bố mọi method service.** Chỉ các query method repository đủ điều kiện export mới được công bố. Dùng `@RestResource` để tùy chỉnh path, relation hoặc tắt export.

**Để lộ repository nội bộ.** Repository được scan có thể trở thành endpoint. Kiểm tra repository nào được export và giới hạn method không dành cho client.

**Coi projection là bảo mật.** Projection chỉ định hình representation. Authorization vẫn phải kiểm tra quyền truy cập dữ liệu.

**Tự ghép URL phân trang.** Client có thể làm mất sort hoặc filter. Theo các link mà collection resource cung cấp.

**Tạo controller CRUD trùng với repository resource.** Có thể gây xung đột mapping hoặc tạo hai hợp đồng khác nhau cho cùng dữ liệu. Dùng controller tùy chỉnh khi có yêu cầu nghiệp vụ riêng và xác định rõ ranh giới với endpoint repository.

## 13. Nguyên tắc thiết kế

- Dùng Spring Data REST khi muốn expose repository như REST resource với ít mã controller CRUD.
- Dùng `@RepositoryRestResource` để đặt path và collection relation tường minh.
- Phân biệt collection resource với item resource.
- Đọc `_embedded`, `_links` và `page` như các phần của hợp đồng HAL.
- Công bố query method có chủ đích bằng `@RestResource`.
- Giới hạn kích thước trang và cho phép sort theo thuộc tính phù hợp.
- Dùng `exported = false` để loại repository hoặc method khỏi bề mặt API khi cần.
- Dùng projection để định hình dữ liệu, đồng thời áp dụng authorization độc lập.
- Kiểm thử API root, collection, search resource, pagination và quyền truy cập bằng MockMvc.
- Giữ path và relation ổn định để client có thể khám phá API qua hypermedia.

## Kết luận

Spring Data REST biến repository được export thành các REST resource. Collection resource đại diện cho tập hợp, chứa các item trong `_embedded`, các link trong `_links` và metadata phân trang khi cần; item resource đại diện cho một entity cụ thể. `@RepositoryRestResource` kiểm soát path và collection relation, còn `@RestResource` điều chỉnh query endpoint. Hãy giới hạn repository và method được export, giữ relation ổn định, cấu hình pagination hợp lý và kiểm thử response HAL thực tế để bảo vệ hợp đồng hypermedia.

## Tài liệu tham khảo

- [Spring Data REST Reference – Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST Reference – Excerpt projections and projections](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring Data REST Reference – Customizing the REST API](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST Reference – Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)

