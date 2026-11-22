# Tùy chỉnh path và rel của truy vấn bằng @RestResource

## Mục tiêu

Sau bài này, bạn có thể:

- Xác định vị trí query method trong search resource của Spring Data REST.
- Dùng **@RestResource(path = ...)** để đổi URL của query method.
- Dùng **@RestResource(rel = ...)** để đổi tên quan hệ hypermedia trong HAL.
- Phân biệt path, rel và tên query parameter.
- Kết hợp **@Param** để công bố tham số tìm kiếm ổn định.
- Kiểm tra link tìm kiếm bằng HAL và gọi endpoint với tham số phù hợp.

## 1. Query method được công bố ở đâu?

Spring Data REST có thể tự công bố các query method hợp lệ của Spring Data repository thành search resource. Giả sử repository:

~~~java
public interface MemberRepository extends JpaRepository<Member, Long> {

    List<Member> findByLastName(String lastName);
}
~~~

Khi repository được công bố dưới đường dẫn **/api/members**, query method có thể được truy cập dưới search resource:

~~~text
/api/members/search/findByLastName
~~~

Search resource có một endpoint chỉ mục để client khám phá các query method đã công bố:

~~~http
GET /api/members/search
Accept: application/hal+json
~~~

Response HAL có thể chứa link đến từng finder method. Khi client gọi link tìm kiếm, method được thực thi với các query parameter tương ứng.

Đây là cách Spring Data REST tạo API tìm kiếm từ repository mà không cần viết controller cho từng truy vấn. Đường dẫn cụ thể phụ thuộc repository path, cấu hình base path và annotation trên method.

## 2. @RestResource điều khiển method-level resource

Annotation **@RestResource** có thể đặt trên query method để tùy chỉnh cách method được công bố.

~~~java
import java.util.List;

import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RestResource;

public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-surname", rel = "surname")
    List<Member> findByLastName(@Param("lastName") String lastName);
}
~~~

Trong ví dụ:

- **path = "by-surname"** đặt đoạn URL cho query method.
- **rel = "surname"** đặt tên relation mà client nhìn thấy trong HAL.
- **@Param("lastName")** đặt tên query parameter mà client gửi.
- Tên Java method vẫn là **findByLastName**; annotation không đổi tên method trong code.

Nếu base path là **/api** và repository path là **members**, endpoint tìm kiếm có dạng:

~~~text
GET /api/members/search/by-surname?lastName=Nguyen
~~~

Ba tên **by-surname**, **surname** và **lastName** có ba vai trò riêng. Đừng dùng thay thế cho nhau khi viết client.

## 3. Phân biệt path, rel và @Param

| Cấu hình | Điều khiển | Ví dụ |
|---|---|---|
| **path** | URL segment của finder method | **by-surname** |
| **rel** | Tên relation trong HAL | **surname** |
| **@Param** | Tên query parameter | **lastName** |

### path: client gọi URL nào?

**path** thay đổi đoạn URL cuối của query method dưới **/search**. Với **path = "by-surname"**, client gọi:

~~~text
/api/members/search/by-surname
~~~

Nếu đổi path thành **surname-search**, URL method sẽ đổi theo cấu hình mới. Client đang lưu URL cũ có thể không còn gọi đúng endpoint.

Path nên ngắn, dễ hiểu, ổn định và không trùng với path của finder method khác trong cùng search resource.

### rel: client tìm link bằng tên nào?

**rel** điều khiển relation name trong HAL. Ví dụ response có thể chứa:

~~~json
{
  "_links": {
    "surname": {
      "href": "http://localhost:8080/api/members/search/by-surname{?lastName}",
      "templated": true
    }
  }
}
~~~

Client tìm relation **surname** trong **_links**, lấy **href** rồi mở rộng template. Nếu chỉ đổi rel thành **membersBySurname**, key relation thay đổi; URL trong href vẫn có thể giữ nguyên nếu path không đổi.

Relation name là một phần của hợp đồng hypermedia. Nếu client khám phá API qua HAL, hãy dùng rel server trả về thay vì đoán relation từ tên Java method.

### @Param: query parameter có tên gì?

**@Param** đặt tên biến mà client gửi trong query string. Với:

~~~java
List<Member> findByLastName(@Param("lastName") String surname);
~~~

client gửi:

~~~text
?lastName=Nguyen
~~~

Tên biến Java **surname** không quyết định tên HTTP parameter trong ví dụ này; tên được công bố là **lastName**. Hãy dùng **@Param** để hợp đồng HTTP không phụ thuộc vào việc compiler có lưu tên tham số Java hay không.

Đổi **@Param("lastName")** thành **@Param("familyName")** làm thay đổi tên query parameter. Việc đó ảnh hưởng client dù path và rel không đổi.

## 4. Ví dụ tùy chỉnh độc lập path và rel

Bạn có thể đặt path và rel khác nhau để phân biệt URL với tên quan hệ:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-surname", rel = "membersBySurname")
    List<Member> findByLastName(@Param("lastName") String lastName);
}
~~~

Search index có thể trả về:

~~~json
{
  "_links": {
    "membersBySurname": {
      "href": "http://localhost:8080/api/members/search/by-surname{?lastName}",
      "templated": true
    }
  }
}
~~~

Client thực hiện theo ba bước:

1. Tìm relation **membersBySurname** trong **_links**.
2. Lấy URI template trong **href**.
3. Điền biến **lastName** rồi gửi request.

Ví dụ request sau khi điền:

~~~http
GET /api/members/search/by-surname?lastName=Nguyen
Accept: application/hal+json
~~~

Nếu client chỉ biết relation name, nó vẫn tìm được endpoint dù path URL không giống tên relation. Đó là lý do path và rel nên được xem là hai phần độc lập của hợp đồng API.

## 5. URI template của query method

Khi query method có tham số, HAL link thường được biểu diễn dưới dạng URI template:

~~~json
{
  "href": "http://localhost:8080/api/members/search/by-surname{?lastName}",
  "templated": true
}
~~~

Biểu thức **{?lastName}** cho biết client có thể điền query parameter **lastName**. Khi mở rộng với giá trị **Nguyen**, URI trở thành:

~~~text
http://localhost:8080/api/members/search/by-surname?lastName=Nguyen
~~~

Với dữ liệu có dấu hoặc ký tự đặc biệt, hãy để URI template processor hoặc HTTP client mã hóa tham số đúng cách. Không nối chuỗi thủ công và không encode trước rồi lại encode lần nữa.

Ví dụ curl:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "lastName=Nguyễn" \
  "http://localhost:8080/api/members/search/by-surname"
~~~

Lệnh **--data-urlencode** mã hóa giá trị query parameter. Trong ứng dụng, client nên lấy href và tên biến từ HAL response rồi mở rộng template thay vì tự tạo URL từ chuỗi cố định.

## 6. Tùy chỉnh nhiều query method

Một repository có thể công bố nhiều finder method với path và rel riêng:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-surname", rel = "membersBySurname")
    List<Member> findByLastName(@Param("lastName") String lastName);

    @RestResource(path = "by-status", rel = "membersByStatus")
    List<Member> findByStatus(@Param("status") MemberStatus status);

    @RestResource(path = "recent", rel = "recentMembers")
    List<Member> findTop10ByOrderByCreatedAtDesc();
}
~~~

Search index có thể cung cấp ba relation tương ứng:

- **membersBySurname**: tìm theo họ.
- **membersByStatus**: tìm theo trạng thái.
- **recentMembers**: lấy tối đa 10 member mới nhất.

Các finder method có tham số sẽ có URI template cho query parameter. Method không có tham số có thể có link hoàn chỉnh. Tên relation và URL cuối cùng phải được xác nhận bằng response HAL thực tế.

Không đặt trùng path cho các finder method trong cùng search resource. Nếu hai method cùng dùng path, routing hoặc việc khám phá link sẽ trở nên mơ hồ và khó bảo trì.

## 7. Ẩn query method khỏi REST API

Nếu một query method chỉ dành cho xử lý nội bộ, có thể đặt **exported = false**:

~~~java
@RepositoryRestResource(path = "members")
public interface MemberRepository extends JpaRepository<Member, Long> {

    @RestResource(path = "by-surname", rel = "membersBySurname")
    List<Member> findByLastName(@Param("lastName") String lastName);

    @RestResource(exported = false)
    List<Member> findByInternalReviewFlagTrue();
}
~~~

Method **findByInternalReviewFlagTrue()** vẫn là method của repository và code phía server vẫn có thể gọi nó. Spring Data REST không công bố method đó thành search endpoint.

Ẩn query method không phải authorization rule. Nếu dữ liệu có thể truy cập qua collection resource, item resource, association hoặc controller khác, ứng dụng vẫn phải kiểm tra quyền truy cập ở server.

## 8. Mô tả query method

**@RestResource** cũng hỗ trợ metadata mô tả thông qua thuộc tính **description**:

~~~java
import org.springframework.data.rest.core.annotation.Description;
import org.springframework.data.rest.core.annotation.RestResource;

@RestResource(
    path = "by-surname",
    rel = "membersBySurname",
    description = @Description("Tìm thành viên theo họ")
)
List<Member> findByLastName(@Param("lastName") String lastName);
~~~

Mô tả giúp diễn giải mục đích của finder method trong metadata Spring Data REST/ALPS. Nó không tự thay thế tài liệu API đầy đủ hoặc cơ chế sinh OpenAPI của dự án.

Hãy viết mô tả ngắn, chính xác và phù hợp với hành vi thật của query method. Nếu method tìm theo họ chính xác, đừng mô tả nó như tìm kiếm gần đúng hoặc tìm kiếm toàn văn.

## 9. Kiểm tra search resource

Bắt đầu bằng cách đọc collection hoặc API root để khám phá link **search**:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/members
~~~

Tiếp theo, đọc search index:

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  http://localhost:8080/api/members/search
~~~

Kiểm tra relation đã tùy chỉnh, ví dụ **membersBySurname**, và xác nhận href có path **by-surname** cùng biến **lastName**. Sau đó gọi finder:

~~~bash
curl -i -G \
  -H "Accept: application/hal+json" \
  --data-urlencode "lastName=Nguyen" \
  http://localhost:8080/api/members/search/by-surname
~~~

Hãy kiểm tra:

1. Search index có chứa relation mong đợi không?
2. Relation name có đúng giá trị **rel** không?
3. Href có path đúng với **path** không?
4. URI template có chứa đúng tên biến **@Param** không?
5. Response có status code, Content-Type và dữ liệu phù hợp không?

Nếu thay đổi path hoặc rel, hãy kiểm tra lại search index. Đây là nơi xác nhận hợp đồng mà client thực sự nhìn thấy.

## 10. Lỗi thường gặp

### Đổi rel nhưng client vẫn gọi URL cũ

Rel là tên liên kết trong HAL; path mới quyết định URL. Client nên tìm link theo relation mới và lấy href thay vì lưu cứng URL.

### Đổi path nhưng vẫn tìm relation theo tên method

Path và rel độc lập. Nếu rel được tùy chỉnh, key trong **_links** có thể không còn là tên method Java. Hãy đọc search index.

### Dùng nhầm tên query parameter

Path là **by-surname**, rel là **membersBySurname**, nhưng query parameter vẫn là **lastName**. Dùng **surname** hoặc **name** thay cho **lastName** có thể khiến request thiếu tham số cần thiết.

### Quên @Param

Nếu hợp đồng cần một tên parameter ổn định, hãy khai báo rõ **@Param**. Đừng phụ thuộc vào tên tham số Java được giữ lại bởi compiler.

### Trùng path của finder method

Hai query method có cùng path có thể gây xung đột khi công bố search resource. Chọn path duy nhất và có ý nghĩa cho từng method.

### Finder method không xuất hiện

Kiểm tra repository có được Spring Data REST phát hiện không, method có bị **exported = false** không, query method có hợp lệ không và cấu hình path có xung đột không.

### Nhầm rel/path với bảo mật

Đổi tên hoặc ẩn link chỉ điều khiển cách API được công bố. Authorization vẫn phải được thực hiện ở server cho từng tài nguyên và thao tác.

## 11. Ghi nhớ

- Query method được công bố dưới search resource của repository.
- **@RestResource(path = ...)** tùy chỉnh URL của finder method.
- **@RestResource(rel = ...)** tùy chỉnh relation name trong HAL.
- **@Param(...)** đặt tên query parameter; nó độc lập với path và rel.
- Client nên khám phá search index, lấy href và mở rộng URI template.
- Dùng path duy nhất cho mỗi finder method được công bố.
- **exported = false** ẩn finder method khỏi REST API nhưng không xóa method khỏi repository.
- Path, rel và metadata không thay thế validation hoặc authorization.
