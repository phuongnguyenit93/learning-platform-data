# @Tag ở cấp Controller và operation

Khi API có nhiều endpoint, Swagger UI cần một cách nhóm các thao tác để người đọc tìm đúng chức năng. OpenAPI dùng **tag** cho mục đích đó. springdoc-openapi có thể lấy thông tin tag từ annotation trên controller, từ metadata OpenAPI dùng chung và từ danh sách tag được khai báo cho từng operation.

Hai vị trí thường dùng nhất trong Spring Boot là:

- **@Tag** đặt trên class controller để mô tả nhóm chức năng gắn với controller.
- **@Operation(tags = {...})** đặt trên method để chỉ định nhóm cho operation cụ thể.

Hai annotation có vai trò liên quan nhưng không thay thế nhau hoàn toàn. @Tag mô tả một Tag Object, gồm tên và metadata như description; thuộc tính tags của @Operation gắn tên tag vào operation. Hiểu rõ sự khác biệt này giúp tài liệu có nhóm nhất quán và tránh tạo ra các nhóm trùng tên hoặc thiếu mô tả.

## 1. Tag trong OpenAPI là gì?

Trong OpenAPI, tag là nhãn phân loại operation. Mỗi operation có thể tham chiếu một hoặc nhiều tên tag. Giao diện như Swagger UI thường dùng các tag này để gom endpoint thành từng nhóm có thể mở rộng hoặc thu gọn.

Một tài liệu OpenAPI có hai vị trí quan trọng liên quan đến tag:

1. **Root-level tags**: danh sách Tag Object ở cấp tài liệu, thường chứa tên, mô tả và liên kết tài liệu bổ sung.
2. **Operation tags**: danh sách tên tag được gắn vào từng operation trong phần paths.

Ví dụ rút gọn:

~~~yaml
tags:
  - name: Books
    description: Các thao tác quản lý sách
  - name: Authors
    description: Các thao tác quản lý tác giả

paths:
  /api/books:
    get:
      summary: Liệt kê sách
      tags:
        - Books
      responses:
        "200":
          description: Danh sách sách
  /api/authors:
    get:
      summary: Liệt kê tác giả
      tags:
        - Authors
      responses:
        "200":
          description: Danh sách tác giả
~~~

Phần root-level tags cung cấp metadata để công cụ hiển thị tên và mô tả nhóm. Phần tags bên trong operation cho biết operation thuộc nhóm nào. Hai tên phải khớp chính xác để metadata của Tag Object được áp dụng đúng.

Tên trong danh sách root-level tags cần duy nhất. Nếu hai Tag Object dùng cùng một tên nhưng có mô tả khác nhau, công cụ đọc tài liệu có thể không biết metadata nào là chính xác. Hãy duy trì một định nghĩa cho mỗi tên tag trong toàn bộ tài liệu.

Một operation có thể có nhiều tag. Khi đó, một số giao diện tài liệu có thể hiển thị operation trong nhiều nhóm. Hãy dùng nhiều tag khi thao tác thực sự thuộc nhiều lĩnh vực, không thêm tag chỉ để tạo thêm điểm truy cập trong giao diện.

## 2. Dùng @Tag ở cấp Controller

Annotation **io.swagger.v3.oas.annotations.tags.Tag** thường được đặt trên class controller. springdoc dùng thông tin này để mô tả nhóm gắn với các operation thuộc controller.

~~~java
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(
    name = "Books",
    description = "Các thao tác tra cứu và quản lý sách"
)
@RestController
@RequestMapping("/api/books")
public class BookController {

    @GetMapping
    public List<BookResponse> findAll() {
        // ...
        return List.of();
    }

    @GetMapping("/{bookId}")
    public BookResponse findById(@PathVariable UUID bookId) {
        // ...
        return null;
    }
}
~~~

Trong ví dụ, tag **Books** mô tả nhóm chức năng của BookController. Các operation được phát hiện từ @GetMapping vẫn do Spring MVC tạo ra; @Tag chỉ bổ sung thông tin phân loại và mô tả cho tài liệu OpenAPI.

Các thuộc tính thường dùng của @Tag:

| Thuộc tính | Ý nghĩa |
|---|---|
| **name** | Tên tag; đây là khóa dùng để gắn tag vào operation |
| **description** | Giải thích nhóm endpoint phục vụ chức năng nào |
| **externalDocs** | Liên kết tới tài liệu bổ sung về nhóm |
| **extensions** | Metadata mở rộng theo quy ước x-* của OpenAPI |

Nên đặt tên tag ngắn gọn, ổn định và phản ánh miền nghiệp vụ hoặc tài nguyên. Ví dụ **Books**, **Authors**, **Orders** dễ hiểu hơn những tên chung như **Controller1**, **GET APIs** hoặc **Misc**.

### Một controller nên có một nhóm chính

Nếu controller quản lý một tài nguyên hoặc một miền chức năng rõ ràng, một tag ở cấp class giúp tài liệu nhất quán mà không phải lặp lại mô tả trên từng method.

~~~java
@Tag(name = "Authors", description = "Tra cứu và quản lý tác giả")
@RestController
@RequestMapping("/api/authors")
public class AuthorController {

    @GetMapping
    public List<AuthorResponse> findAll() {
        // ...
        return List.of();
    }

    @PostMapping
    public AuthorResponse create(@RequestBody CreateAuthorRequest request) {
        // ...
        return null;
    }
}
~~~

Khi thêm endpoint mới vào controller này, nhóm tag của controller tiếp tục mô tả cùng một miền chức năng. Nếu controller bắt đầu chứa nhiều miền nghiệp vụ không liên quan, nên cân nhắc tách controller hoặc gắn tag riêng ở cấp operation để người đọc không phải tìm trong một nhóm quá lớn.

## 3. Dùng tags của @Operation ở cấp method

**@Tag** là annotation mô tả tag metadata, còn thuộc tính **tags** của **@Operation** là danh sách tên tag gắn trực tiếp với một operation. Đây là cách phổ biến để phân loại endpoint riêng lẻ.

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public class CatalogController {

    @Operation(
        summary = "Tìm kiếm sách",
        operationId = "searchBooks",
        tags = {"Books"}
    )
    @GetMapping("/books")
    public List<BookResponse> searchBooks(@RequestParam String keyword) {
        // ...
        return List.of();
    }

    @Operation(
        summary = "Lấy danh sách thể loại",
        operationId = "listCategories",
        tags = {"Categories"}
    )
    @GetMapping("/categories")
    public List<CategoryResponse> listCategories() {
        // ...
        return List.of();
    }
}
~~~

Hai method thuộc cùng một class Java nhưng được phân vào hai nhóm tài liệu khác nhau. Cách này hữu ích khi controller tổ chức theo luồng xử lý kỹ thuật, còn tài liệu cần nhóm theo chức năng mà client quan tâm.

Thuộc tính tags nhận mảng tên tag, không nhận annotation @Tag. Ví dụ **tags = {"Books", "Search"}** gắn operation với cả hai tên đó. Metadata mô tả cho từng tên cần được khai báo ở cấp tài liệu hoặc bằng annotation @Tag thích hợp.

### @Tag không phải annotation gắn trực tiếp cho method

Trong swagger-annotations, @Tag được thiết kế để mô tả tag metadata ở cấp type (và dùng trong một số annotation khác). Để gắn tên tag cho method operation, dùng **@Operation(tags = {...})**. Không đặt @Tag trên method theo suy luận từ tên annotation; hãy dùng đúng thuộc tính của @Operation.

Phân biệt nhanh:

| Mục tiêu | Cách khai báo |
|---|---|
| Mô tả tag của một controller | @Tag trên class controller |
| Gắn một operation vào một hoặc nhiều tag | @Operation(tags = {...}) trên method |
| Khai báo metadata tag dùng chung cho tài liệu | tags của @OpenAPIDefinition hoặc OpenAPI bean |

## 4. Kết hợp tag ở Controller và operation

Một ứng dụng có thể dùng tag cấp controller làm nhóm mặc định, sau đó bổ sung tag ở các operation cần phân loại chi tiết. Ví dụ:

~~~java
@Tag(
    name = "Books",
    description = "Các thao tác liên quan đến sách"
)
@RestController
@RequestMapping("/api/books")
public class BookController {

    @Operation(
        summary = "Lấy thông tin sách",
        operationId = "getBook",
        tags = {"Books"}
    )
    @GetMapping("/{bookId}")
    public BookResponse get(@PathVariable UUID bookId) {
        // ...
        return null;
    }

    @Operation(
        summary = "Tìm sách theo từ khóa",
        operationId = "searchBooks",
        tags = {"Books", "Search"}
    )
    @GetMapping("/search")
    public List<BookResponse> search(@RequestParam String keyword) {
        // ...
        return List.of();
    }
}
~~~

Operation searchBooks có hai tag trong metadata operation. Công cụ tài liệu có thể dùng cả hai nhóm để hiển thị thao tác. Với cấu hình và phiên bản springdoc cụ thể, cách hợp nhất tag khai báo trên controller với tag của @Operation có thể ảnh hưởng danh sách tags cuối cùng. Vì vậy, hãy kiểm tra phần tags trong JSON được sinh ra khi kết hợp hai cấp annotation, đặc biệt nếu muốn một operation chỉ xuất hiện trong một nhóm.

Nếu mục tiêu là phân loại hoàn toàn theo từng operation, hãy cân nhắc không đặt tag mặc định ở class, rồi khai báo tags rõ ràng cho các method. Nếu controller có một nhóm chính và chỉ một số method cần thêm nhãn phụ, giữ tag cấp class và bổ sung tag operation có chủ đích.

### Tag bổ sung không thay đổi route

Các annotation tag không thay đổi:

- HTTP method hoặc path mapping.
- Cách Spring bind path, query, header, cookie hoặc request body.
- Quyền truy cập và cơ chế xác thực.
- Mã trạng thái hoặc nội dung response.

Nếu đổi tên tag, endpoint vẫn có thể được gọi bằng URL cũ. Thay đổi chỉ tác động đến cách operation được phân nhóm và metadata mà công cụ tài liệu hiển thị.

## 5. Khai báo metadata tag dùng chung bằng @OpenAPIDefinition

Khi muốn quản lý danh sách tag ở một vị trí cấu hình, có thể dùng thuộc tính **tags** của **@OpenAPIDefinition**. Cách này tách metadata mô tả nhóm khỏi controller:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Library API",
        version = "v1",
        description = "API quản lý thư viện"
    ),
    tags = {
        @Tag(
            name = "Books",
            description = "Tra cứu và quản lý sách"
        ),
        @Tag(
            name = "Authors",
            description = "Tra cứu và quản lý tác giả"
        ),
        @Tag(
            name = "Categories",
            description = "Quản lý thể loại sách"
        )
    }
)
public class OpenApiConfiguration {
}
~~~

Các operation vẫn cần gắn tên tag phù hợp bằng @Tag trên controller hoặc @Operation(tags = {...}) trên method. Khai báo tag ở cấp tài liệu cung cấp mô tả dùng chung; nó không tự tạo endpoint và cũng không tự gắn tất cả operation vào các nhóm.

Nếu dự án đã khai báo OpenAPI bằng bean, có thể định nghĩa Tag Object bằng swagger-models:

~~~java
@Bean
public OpenAPI libraryApi() {
    return new OpenAPI()
        .info(new Info()
            .title("Library API")
            .version("v1"))
        .tags(List.of(
            new io.swagger.v3.oas.models.tags.Tag()
                .name("Books")
                .description("Tra cứu và quản lý sách"),
            new io.swagger.v3.oas.models.tags.Tag()
                .name("Authors")
                .description("Tra cứu và quản lý tác giả")
        ));
}
~~~

Trong ví dụ bean, dùng tên đầy đủ **io.swagger.v3.oas.models.tags.Tag** để phân biệt model Tag với annotation **io.swagger.v3.oas.annotations.tags.Tag**. Chọn một nơi quản lý metadata tag chính để tránh định nghĩa trùng lặp và khó duy trì.

## 6. Quy tắc đặt tên và tổ chức tag

Một bộ tag tốt giúp người tích hợp tìm endpoint nhanh mà vẫn phản ánh cấu trúc nghiệp vụ. Có thể áp dụng các nguyên tắc sau:

| Nguyên tắc | Ví dụ nên dùng | Lý do |
|---|---|---|
| Đặt tên theo tài nguyên hoặc miền nghiệp vụ | Books, Orders, Payments | Người đọc nhận biết ngay nhóm chức năng |
| Giữ nguyên cách viết ở mọi operation | Luôn dùng Books, không trộn Book và books | Tránh sinh nhiều nhóm gần giống nhau |
| Dùng mô tả ngắn, cụ thể | Quản lý sách và thông tin xuất bản | Người đọc hiểu phạm vi nhóm |
| Hạn chế tag quá rộng | Tránh Common, Other, Misc | Nhóm rộng làm tài liệu khó tìm |
| Không tạo tag theo HTTP method | Tránh GET, POST, DELETE | Client thường tìm theo tài nguyên hoặc nghiệp vụ |
| Dùng nhiều tag có chọn lọc | Books và Search khi phù hợp | Hỗ trợ nhiều góc nhìn nhưng tránh lặp nhóm vô ích |

Tên tag là chuỗi được so khớp trong tài liệu. Nên coi khác biệt chữ hoa/chữ thường hoặc khoảng trắng là khác biệt tên, và thống nhất một quy ước. Không nên đổi tên tag tùy tiện giữa các bản phát hành nếu khách hàng đang dùng cấu trúc tài liệu hoặc quy trình sinh SDK dựa trên tên nhóm.

### Thứ tự tag trong giao diện

OpenAPI cho phép khai báo danh sách tags ở cấp tài liệu. Thứ tự của danh sách này có thể được công cụ sử dụng để hiển thị nhóm. Nếu thứ tự là yêu cầu quan trọng, hãy khai báo tag theo thứ tự mong muốn ở một nơi cấu hình tập trung và kiểm tra Swagger UI sau khi sinh tài liệu.

Không nên dựa vào thứ tự khai báo method trong controller để quyết định thứ tự nhóm. Thứ tự hiển thị còn phụ thuộc công cụ giao diện, cấu hình và phiên bản đang sử dụng.

## 7. Ví dụ hoàn chỉnh: nhiều controller, nhóm tài liệu rõ ràng

Giả sử một hệ thống thư viện có ba miền: sách, tác giả và mượn trả. Mỗi controller mô tả nhóm chính bằng @Tag:

~~~java
@Tag(name = "Books", description = "Tra cứu và quản lý sách")
@RestController
@RequestMapping("/api/books")
class BookController {

    @Operation(
        summary = "Liệt kê sách",
        operationId = "listBooks"
    )
    @GetMapping
    List<BookResponse> list() {
        return List.of();
    }

    @Operation(
        summary = "Tìm sách theo tên",
        operationId = "searchBooks",
        tags = {"Books", "Search"}
    )
    @GetMapping("/search")
    List<BookResponse> search(@RequestParam String title) {
        return List.of();
    }
}

@Tag(name = "Authors", description = "Tra cứu và quản lý tác giả")
@RestController
@RequestMapping("/api/authors")
class AuthorController {

    @Operation(
        summary = "Liệt kê tác giả",
        operationId = "listAuthors"
    )
    @GetMapping
    List<AuthorResponse> list() {
        return List.of();
    }
}

@Tag(name = "Loans", description = "Quản lý giao dịch mượn và trả sách")
@RestController
@RequestMapping("/api/loans")
class LoanController {

    @Operation(
        summary = "Tạo giao dịch mượn",
        operationId = "createLoan"
    )
    @PostMapping
    LoanResponse create(@RequestBody CreateLoanRequest request) {
        return null;
    }
}
~~~

Kết quả mong đợi về mặt tổ chức:

| Tag | Operation |
|---|---|
| Books | listBooks, searchBooks |
| Search | searchBooks nếu operation được gắn thêm tag này |
| Authors | listAuthors |
| Loans | createLoan |

Trong Swagger UI, người dùng có thể tìm nhóm Books để xem thao tác sách, Authors để xem tác giả và Loans để xem nghiệp vụ mượn trả. Operation searchBooks có thể xuất hiện dưới cả Books và Search tùy cách giao diện xử lý nhiều tag.

Để mô tả đầy đủ tên và nội dung của nhóm Search, hãy bổ sung Tag Object ở cấp tài liệu bằng @OpenAPIDefinition hoặc OpenAPI bean. Nếu không khai báo metadata bổ sung, operation vẫn có thể chứa tên tag Search nhưng phần mô tả nhóm có thể không có.

## 8. Đọc kết quả trong OpenAPI JSON

Sau khi ứng dụng khởi động, mở **/v3/api-docs** để xem JSON do springdoc sinh ra. Một phần tài liệu có thể có dạng:

~~~json
{
  "tags": [
    {
      "name": "Books",
      "description": "Tra cứu và quản lý sách"
    },
    {
      "name": "Search",
      "description": "Tìm kiếm tài nguyên"
    }
  ],
  "paths": {
    "/api/books/search": {
      "get": {
        "operationId": "searchBooks",
        "summary": "Tìm sách theo tên",
        "tags": [
          "Books",
          "Search"
        ],
        "responses": {
          "200": {
            "description": "Thành công"
          }
        }
      }
    }
  }
}
~~~

Hãy kiểm tra hai phần:

- Mảng root-level **tags** có tên và mô tả nhóm đúng không?
- Mảng **paths.*.*.tags** có gắn đúng tên tag vào từng operation không?

Nếu một operation có tên tag nhưng root-level tags không chứa Tag Object tương ứng, tài liệu vẫn có thể được xử lý bởi công cụ OpenAPI, nhưng giao diện có thể không có description hoặc externalDocs cho nhóm đó. Nếu tên không khớp, metadata mô tả sẽ không được liên kết như mong muốn.

Có thể kiểm tra nhanh bằng jq:

~~~bash
curl -s http://localhost:8080/v3/api-docs | jq '{
  tags: .tags,
  operations: [
    .paths
    | to_entries[]
    | .key as $path
    | .value
    | to_entries[]
    | select(.value.operationId != null)
    | {
        path: $path,
        method: .key,
        operationId: .value.operationId,
        tags: .value.tags
      }
  ]
}'
~~~

Nếu môi trường không có jq, mở trực tiếp JSON hoặc dùng công cụ kiểm tra OpenAPI tương ứng. Điểm quan trọng là xác minh dữ liệu đầu ra, vì Swagger UI chỉ hiển thị theo tài liệu mà nó nhận được.

## 9. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Mọi endpoint nằm trong một nhóm mặc định | Operation chưa có tag phù hợp | Thêm @Tag ở controller hoặc @Operation(tags = {...}) |
| Xuất hiện hai nhóm gần giống nhau | Tên tag không thống nhất, khác chữ hoa hoặc khoảng trắng | Chuẩn hóa tên tag trên toàn API |
| Nhóm có tên nhưng thiếu mô tả | Chưa khai báo Tag Object ở cấp tài liệu hoặc controller | Bổ sung @Tag hoặc root-level tags |
| Một operation xuất hiện ở nhiều nhóm | Operation có nhiều tên tag hoặc tag class và method được kết hợp | Kiểm tra tags trong JSON, quyết định có chủ đích |
| Đặt @Tag trên method nhưng không biên dịch | Annotation không dùng cho target method | Dùng @Operation(tags = {...}) |
| Thêm @Tag nhưng endpoint không xuất hiện | Controller hoặc mapping không được Spring đăng ký | Kiểm tra component scan và mapping; tag không tạo route |
| Đổi tên nhóm làm người dùng khó tìm tài liệu | Tag name bị đổi giữa các lần phát hành | Duy trì tên ổn định và ghi nhận thay đổi tài liệu |
| Thứ tự nhóm không như mong đợi | Công cụ UI dùng thứ tự hoặc quy tắc riêng | Kiểm tra root-level tags và cấu hình giao diện |

Một lỗi quan trọng là nhầm tag với bảo mật. Tag chỉ là metadata để phân loại tài liệu. Muốn giới hạn người dùng gọi API, phải cấu hình Spring Security, xác thực, phân quyền và bảo vệ endpoint tài liệu theo yêu cầu triển khai.

## 10. Quy trình kiểm tra tag sau khi cấu hình

Sau khi thêm hoặc thay đổi annotation, thực hiện các bước sau:

1. Khởi động ứng dụng và xác nhận controller được Spring đăng ký.
2. Mở endpoint **/v3/api-docs** và tìm path của controller.
3. Kiểm tra operation có mảng tags và tên tag có đúng quy ước không.
4. Kiểm tra root-level tags có Tag Object với description hoặc externalDocs cần thiết không.
5. Mở Swagger UI để xác nhận nhóm và thao tác hiển thị đúng như mong đợi.
6. Kiểm tra các operation có nhiều tag để chắc chắn việc xuất hiện ở nhiều nhóm là có chủ đích.
7. Nếu tài liệu được dùng để sinh SDK hoặc tích hợp CI, lưu snapshot và kiểm tra thay đổi tag như một phần của review hợp đồng.

Đối với API có nhiều nhóm hoặc nhiều tài liệu (GroupedOpenApi), kiểm tra từng endpoint tài liệu của group. Tag chỉ tổ chức các operation đã có trong tài liệu hiện tại; nó không đưa endpoint bị path/package filter loại bỏ trở lại tài liệu.

## Kết luận

Tag giúp tổ chức operation theo nhóm chức năng trong OpenAPI và Swagger UI. **@Tag** ở cấp controller cung cấp tên và mô tả nhóm cho các endpoint thuộc controller; **@Operation(tags = {...})** gắn một hoặc nhiều tên tag vào operation cụ thể. Metadata tag dùng chung có thể được khai báo bằng **@OpenAPIDefinition** hoặc OpenAPI bean. Hãy giữ tên tag nhất quán, tách rõ metadata mô tả và việc gắn tag vào operation, rồi kiểm tra JSON tại **/v3/api-docs** để xác nhận tài liệu được sinh đúng.
