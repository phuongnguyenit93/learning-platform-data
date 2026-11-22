# RepositoryRestHandlerMapping lựa chọn bộ xử lý yêu cầu như thế nào

## 1. Vai trò của RepositoryRestHandlerMapping

Trong Spring MVC, `DispatcherServlet` không tự đoán controller nào cần chạy. Nó hỏi các đối tượng `HandlerMapping` theo thứ tự ưu tiên đã cấu hình. Mỗi `HandlerMapping` xem request có thuộc phạm vi mình quản lý hay không:

- Có handler phù hợp: trả về handler (thường là một `HandlerMethod`).
- Không có handler phù hợp: trả về `null`, để `DispatcherServlet` thử `HandlerMapping` tiếp theo.

`RepositoryRestHandlerMapping` là `HandlerMapping` chuyên cho Spring Data REST. Nó kế thừa `BasePathAwareHandlerMapping`, vốn dựa trên `RequestMappingHandlerMapping` của Spring MVC. Nhiệm vụ của nó là tìm một phương thức controller nội bộ của Spring Data REST phù hợp với URL và chỉ nhận request nếu segment repository trong URL tương ứng với một repository đang được export.

Điểm cần phân biệt: class này chọn **controller method xử lý HTTP request**. Nó không trực tiếp gọi `findById()`, `save()` hay một query method của repository. Việc phân giải repository và gọi thao tác dữ liệu diễn ra ở các bước tiếp theo.

## 2. Hai lớp điều kiện để nhận một request

Có thể hiểu việc lựa chọn qua hai lớp kiểm tra liên tiếp.

### Lớp 1 — Request có khớp một handler method của Spring Data REST không?

Khi khởi tạo ứng dụng, cơ chế kế thừa từ `RequestMappingHandlerMapping` quét các bean controller và đăng ký những method có mapping phù hợp. Riêng `RepositoryRestHandlerMapping` giới hạn loại controller được xem là handler: implementation hiện tại kiểm tra annotation `@RepositoryRestController` (qua `AnnotatedElementUtils.hasAnnotation`).

Vì vậy, các controller nội bộ như `RepositoryEntityController`, `RepositorySearchController` và `RepositoryPropertyReferenceController` có thể tham gia xử lý những nhóm URL tương ứng. Các method được đăng ký bằng các annotation Spring MVC như `@RequestMapping`, `@GetMapping`, `@PostMapping`, v.v.

Khi có request, phần xử lý kế thừa tìm mapping phù hợp dựa trên các điều kiện của `RequestMappingInfo`, thường gồm:

- Đường dẫn URL và pattern của method.
- HTTP method: GET, POST, PUT, PATCH, DELETE, ...
- Query parameter hoặc header được khai báo trong mapping.
- Điều kiện `consumes` và `produces`, có liên quan đến `Content-Type` và `Accept`.

Nếu không có method nào khớp, kết quả là `null`.

### Lớp 2 — Segment repository trong URL có được export không?

Ngay cả khi tìm được một `HandlerMethod`, `RepositoryRestHandlerMapping` vẫn kiểm tra URL có thực sự thuộc một repository đã export hay không.

Trong implementation hiện tại, logic chính trong `lookupHandlerMethod` diễn ra như sau:

1. Gọi `super.lookupHandlerMethod(lookupPath, request)` để tìm method theo cơ chế mapping của Spring MVC.
2. Nếu không tìm được method, trả về `null`.
3. Dùng `RepositoryRestConfiguration.getBasePath()` để tách base path khỏi URL và lấy phần repository lookup path.
4. Nếu request là root resource (không có repository segment), giữ lại handler đã tìm được. Ví dụ, request đến base path `/api` có thể được xử lý bởi controller cung cấp tài nguyên gốc và các link khám phá API.
5. Nếu có repository segment, lấy segment đầu tiên của repository lookup path. Ví dụ `/people/search/byLastName` có segment đầu tiên là `people`.
6. Gọi `ResourceMappings.exportsTopLevelResourceFor(repositoryBasePath)`. Nếu segment đó không phải tài nguyên cấp cao nhất đang được export, trả về `null`; nếu có, chấp nhận `HandlerMethod`.

Việc kiểm tra này ngăn một route tổng quát của Spring Data REST nhận nhầm URL chỉ vì URL có hình dạng giống route repository. `ResourceMappings` là nguồn metadata cho biết đường dẫn nào đại diện cho tài nguyên repository được export.

## 3. Ví dụ: request tìm kiếm trong repository

Giả sử ứng dụng có repository:

```java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends CrudRepository<Person, Long> {

    @RestResource(path = "byLastName")
    List<Person> findByLastName(@Param("lastName") String lastName);
}
```

Ứng dụng cấu hình base path là `/api`. Client gửi:

```http
GET /api/people/search/byLastName?lastName=Nguyen
Accept: application/hal+json
```

Luồng chọn handler có thể đọc như sau:

| Bước | Giá trị hoặc kiểm tra | Kết quả |
|---|---|---|
| Base path | `/api` | Được loại khỏi phần path dùng để nhận diện repository |
| Repository lookup path | `/people/search/byLastName` | Phần path còn lại |
| Repository base path | `people` | Segment đầu tiên |
| ResourceMappings | `exportsTopLevelResourceFor("people")` | Phải trả về `true` |
| Request mapping | Pattern tìm kiếm và HTTP method GET | Chọn method phù hợp trong `RepositorySearchController` |
| Kết quả | `HandlerMethod` | Chuyển sang bước thực thi handler |

Ở bước mapping, Spring Data REST chọn method tổng quát của `RepositorySearchController` để xử lý request tìm kiếm. Sau đó, các argument resolver và thành phần xử lý của Spring Data REST dùng metadata của repository để xác định tài nguyên `people`, tìm search resource `byLastName`, bind tham số `lastName` và gọi query method tương ứng.

Nói cách khác, `RepositoryRestHandlerMapping` nhận diện **loại endpoint và controller method**; nó chưa thực thi `PersonRepository.findByLastName("Nguyen")`.

## 4. Khi repository không được export

Giả sử URL là:

```http
GET /api/people/42
```

Nếu `people` là repository được export, request có thể khớp method lấy item trong `RepositoryEntityController`, sau đó vượt qua kiểm tra `ResourceMappings`.

Nếu repository được đổi path thành `persons`, hoặc bị tắt export, thì `exportsTopLevelResourceFor("people")` trả về `false`. Dù một pattern tổng quát có thể khớp hình dạng URL, `RepositoryRestHandlerMapping` vẫn trả về `null`. `DispatcherServlet` tiếp tục thử các `HandlerMapping` còn lại; một controller Spring MVC khác có thể xử lý URL đó nếu có mapping phù hợp.

Đây là lý do cần phân biệt hai kết quả:

- **Không tìm được method mapping:** không có controller method phù hợp với path và các điều kiện của request.
- **Có method mapping nhưng repository không export:** method có hình dạng phù hợp, nhưng Spring Data REST từ chối nhận URL vì segment repository không hợp lệ hoặc không được export.

Cả hai trường hợp đều có thể khiến mapping này trả về `null`. Response cuối cùng (ví dụ 404) còn phụ thuộc vào các `HandlerMapping` khác và cấu hình xử lý lỗi của ứng dụng.

## 5. Các cấu hình ảnh hưởng đến kết quả

| Cấu hình hoặc metadata | Ảnh hưởng |
|---|---|
| `spring.data.rest.base-path` hoặc `RepositoryRestConfiguration` | Xác định prefix của API, ví dụ `/api` |
| `@RepositoryRestResource(path = "people")` | Xác định segment public của collection resource |
| `@RepositoryRestResource(exported = false)` | Không export repository; segment không được nhận như top-level resource |
| Repository detection strategy | Ảnh hưởng repository nào được phát hiện và export |
| `@RestResource(path = "byLastName")` | Đặt path cho search resource tương ứng với query method |
| `@RestResource(exported = false)` trên method | Ẩn search resource; URL tìm kiếm đó không được cung cấp như endpoint công khai |
| `@RepositoryRestController` | Đánh dấu controller tùy chỉnh thuộc phạm vi mapping của Spring Data REST |
| HTTP method, `Accept`, `Content-Type` và điều kiện mapping | Ảnh hưởng method nào khớp với request |

Khi method không khai báo `produces` riêng, `RepositoryRestHandlerMapping` còn tùy biến điều kiện media type bằng default media type trong cấu hình và các media type Spring Data REST hỗ trợ, bao gồm HAL JSON và JSON. Vì vậy, header `Accept` cũng có thể ảnh hưởng đến kết quả chọn mapping.

Thứ tự giữa các `HandlerMapping` được quyết định bởi thuộc tính `order` của chúng. Khi hai mapping trong ứng dụng có URL chồng lấn, cần kiểm tra thứ tự thực tế và các điều kiện mapping thay vì chỉ nhìn tên controller.

## 6. Phân biệt các thành phần trong luồng xử lý

| Thành phần | Trách nhiệm |
|---|---|
| `DispatcherServlet` | Điều phối request và hỏi các `HandlerMapping` theo thứ tự |
| `RepositoryRestHandlerMapping` | Tìm `HandlerMethod` thuộc Spring Data REST và xác nhận repository path được export |
| `ResourceMappings` | Cung cấp metadata về resource path và trạng thái export |
| `HandlerAdapter` | Gọi `HandlerMethod` đã được chọn |
| Argument resolvers của Spring Data REST | Phân giải thông tin repository, resource, ID và tham số method |
| Controller và repository invoker | Xử lý endpoint rồi thực hiện thao tác trên repository |

Một cách đọc luồng tổng quát:

```text
HTTP request
    |
    v
DispatcherServlet
    |
    v
RepositoryRestHandlerMapping
    |
    +-- Tìm HandlerMethod theo RequestMappingInfo
    |       |
    |       +-- Không khớp ----------------------> trả null
    |
    +-- Tách base path, lấy repository segment
            |
            +-- Không có repository segment ----> nhận root handler
            |
            +-- Repository không export --------> trả null
            |
            +-- Repository đã export -----------> trả HandlerMethod
                                                     |
                                                     v
                                                HandlerAdapter
                                                     |
                                                     v
                                          Argument resolvers / Controller
                                                     |
                                                     v
                                              Repository operation
```

## 7. Cách lần theo lỗi định tuyến

Khi một URL Spring Data REST không đi vào controller mong muốn, kiểm tra theo thứ tự:

1. Xác nhận request có đi qua đúng `DispatcherServlet` và đúng base path hay không.
2. Xác nhận controller nội bộ hoặc controller tùy chỉnh có thuộc phạm vi `@RepositoryRestController` và method mapping có được đăng ký hay không.
3. So sánh HTTP method, path, query parameter, header, `consumes` và `produces` của request với mapping.
4. Lấy segment đầu tiên sau base path và kiểm tra repository có được export dưới đúng path đó không.
5. Kiểm tra `@RepositoryRestResource`, `@RestResource` và repository detection strategy nếu endpoint hoặc search resource bị ẩn.
6. Nếu có controller Spring MVC khác dùng cùng prefix, kiểm tra `order` của các `HandlerMapping` và mapping cụ thể của controller đó.

Có thể bật log DEBUG/TRACE cho nhóm Spring MVC mapping để xem các request mapping được đăng ký và quá trình tìm handler. Trong môi trường phát triển, endpoint Actuator `/actuator/mappings` (nếu đã bật và được bảo vệ phù hợp) cũng giúp xem các mapping đang hoạt động.

## 8. Kết luận

`RepositoryRestHandlerMapping` lựa chọn handler theo hai câu hỏi: **có controller method của Spring Data REST khớp request không, và repository đứng ở segment đầu tiên sau base path có thực sự được export không?** Chỉ khi cả hai điều kiện phù hợp, mapping mới trả về `HandlerMethod`. Việc phân giải repository cụ thể và thực thi query hoặc thao tác CRUD diễn ra sau đó.

## Tài liệu tham khảo

- [Javadoc — RepositoryRestHandlerMapping](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/RepositoryRestHandlerMapping.html)
- [Mã nguồn — RepositoryRestHandlerMapping.java](https://github.com/spring-projects/spring-data-rest/blob/main/spring-data-rest-webmvc/src/main/java/org/springframework/data/rest/webmvc/RepositoryRestHandlerMapping.java)
- [Spring Data REST — Adding Spring Data REST to an Existing Spring MVC Application](https://docs.spring.io/spring-data/rest/reference/customizing/adding-sdr-to-spring-mvc-app.html)
