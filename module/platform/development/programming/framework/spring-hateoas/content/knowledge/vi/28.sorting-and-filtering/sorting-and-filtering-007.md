# Mô tả filter trong affordance

Trong REST API, client thường cần lọc một collection theo tiêu chí như tên, trạng thái, phòng ban hoặc khoảng thời gian. Một endpoint có thể nhận các tiêu chí đó qua query parameter, ví dụ `GET /employees/search?name=Frodo&role=developer`. Khi dùng Spring HATEOAS, server có thể mô tả thao tác tìm kiếm này như một **affordance** gắn với link của tài nguyên collection.

Affordance cho client biết một link hỗ trợ thao tác HTTP nào, đích của thao tác là gì, kiểu dữ liệu đầu vào/đầu ra ra sao và có những query parameter nào. Spring HATEOAS biểu diễn metadata query bằng `QueryParameter`; mỗi tham số có tên, giá trị tùy chọn và trạng thái bắt buộc. Có thể tạo metadata từ phương thức controller hoặc khai báo thủ công qua API `Affordances`.

Trong module SPRING_HATEOAS, mô tả filter trong affordance giúp client khám phá khả năng tìm kiếm của collection mà không phải đoán tên query parameter hoặc tự xây dựng URL. Bài học này tập trung vào `QueryParameter`, cách gắn affordance tìm kiếm vào link, phân biệt query filter với payload body, và các lưu ý khi kết hợp lọc với sắp xếp, phân trang cùng content negotiation.

Sau bài học, bạn có thể:

- Giải thích affordance và vai trò của metadata filter.
- Phân biệt query parameter với input payload của POST/PATCH.
- Dùng `QueryParameter.required`, `optional`, `of` và `withValue`.
- Tạo affordance từ phương thức Spring MVC controller.
- Tạo affordance thủ công bằng `Affordances` và `ConfigurableAffordance`.
- Hiểu sự khác nhau giữa `addParameters` và `withParameters`.
- Kết hợp filter với sorting, pagination và query parameter nhiều giá trị.
- Kiểm thử hành vi filter và metadata hypermedia.

## Filter và affordance trong REST

Filter là một tiêu chí dùng để giới hạn tập kết quả của collection. Ví dụ, collection nhân viên có thể hỗ trợ:

| Query parameter | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| name | Tìm theo tên hoặc một phần tên | name=Frodo |
| role | Lọc theo vai trò | role=developer |
| department | Lọc theo phòng ban | department=engineering |
| status | Lọc theo trạng thái | status=ACTIVE |
| createdAfter | Lọc từ một thời điểm | createdAfter=2026-01-01 |

Client có thể gọi trực tiếp một URL đã biết, nhưng cách đó buộc client phải biết trước tên tham số và cấu trúc endpoint. Hypermedia cho phép server công bố khả năng tìm kiếm qua link và affordance:

~~~text
GET /employees
  |
  +-- self
  |
  +-- search affordance
        method: GET
        target: /employees/search
        query parameters:
          name (optional)
          role (optional)
~~~

Client theo relation `search`, đọc metadata affordance rồi tạo request với các query parameter phù hợp. Nếu server thay đổi target URI nhưng vẫn giữ relation và semantics, client có thể tiếp tục khám phá thao tác từ response mới.

### Affordance mô tả thao tác, không thực thi thao tác

Affordance là metadata gắn với link. Nó mô tả thao tác mà client có thể thực hiện, chẳng hạn:

- HTTP method như GET, POST, PUT, PATCH hoặc DELETE.
- Target URI của thao tác.
- Input payload và media type nếu thao tác gửi body.
- Output model mà thao tác có thể trả về.
- Query parameter mà thao tác nhận.
- Tên affordance để client nhận biết thao tác.

Affordance không tự chạy truy vấn và cũng không thay thế controller. Khi client gửi request, server vẫn thực thi endpoint, kiểm tra quyền, xác thực dữ liệu và áp dụng quy tắc nghiệp vụ.

## QueryParameter là gì?

`org.springframework.hateoas.QueryParameter` là value object mô tả một query parameter của request. Một query parameter có ba thông tin chính:

| Thông tin | API | Ý nghĩa |
| --- | --- | --- |
| Tên tham số | getName() | Key xuất hiện trong query string |
| Giá trị | getValue() | Giá trị hiện tại nếu được cung cấp; có thể null |
| Bắt buộc | isRequired() | Client có phải cung cấp tham số hay không |

Spring HATEOAS cung cấp các factory method:

- `QueryParameter.required("page")` tạo tham số bắt buộc.
- `QueryParameter.optional("status")` tạo tham số tùy chọn.
- `QueryParameter.of(methodParameter)` tạo metadata từ một Spring `MethodParameter`.
- `withValue("ACTIVE")` tạo một bản sao có giá trị được gán.

Ví dụ:

~~~java
import org.springframework.hateoas.QueryParameter;

QueryParameter name = QueryParameter.optional("name");
QueryParameter page = QueryParameter.required("page");
QueryParameter activeStatus =
    QueryParameter.optional("status").withValue("ACTIVE");
~~~

Trong trường hợp filter collection, phần lớn tiêu chí thường là tùy chọn. Nếu client không gửi status, server có thể trả tất cả trạng thái; nếu gửi status=ACTIVE, server giới hạn kết quả theo trạng thái đó. Tham số như tenant hoặc accountId có thể là bắt buộc trong một số hợp đồng, nhưng thông tin định danh hoặc phân quyền nhạy cảm thường nên lấy từ security context thay vì yêu cầu client tự truyền.

### Required và optional

Hai trạng thái này mô tả hợp đồng query:

~~~java
QueryParameter.required("fromDate");
QueryParameter.optional("toDate");
~~~

Ví dụ, một báo cáo yêu cầu fromDate nhưng cho phép bỏ toDate để hiểu là đến hiện tại. Client có thể dùng metadata để biết trường nào phải điền trước khi gửi request.

Đừng đánh dấu mọi filter là required. Nếu tham số tùy chọn bị đánh dấu bắt buộc, client có thể từ chối gửi request dù endpoint thực tế vẫn xử lý được trường hợp không có filter.

### Gán giá trị cho query parameter

`withValue` trả về một `QueryParameter` mới với giá trị được cập nhật:

~~~java
QueryParameter currentStatus =
    QueryParameter.optional("status").withValue("ACTIVE");
~~~

Giá trị này có thể hữu ích khi mô tả một truy vấn đã có ngữ cảnh hoặc một tham số mặc định. Nó không phải cơ chế lưu trạng thái filter phía server. Server vẫn đọc giá trị thực tế từ request khi client gọi endpoint.

## Phân biệt query filter với input payload

Một affordance có thể mô tả query parameter và input payload. Hai loại dữ liệu này có vị trí và semantics khác nhau:

| Đặc điểm | Query parameter | Input payload |
| --- | --- | --- |
| Vị trí | Query string của URI | HTTP request body |
| Ví dụ | ?status=ACTIVE&page=0 | JSON chứa các trường cần tạo/cập nhật |
| API Spring HATEOAS | QueryParameter | withInput(...) hoặc withInputAndOutput(...) |
| Thường dùng với | GET search/filter, pagination | POST, PUT, PATCH |

Ví dụ filter:

~~~http
GET /employees/search?name=Frodo&role=developer
Accept: application/hal+json
~~~

Request không có body. name và role là query parameter.

Ví dụ tạo nhân viên:

~~~http
POST /employees
Content-Type: application/json

{
  "name": "Frodo",
  "role": "developer"
}
~~~

name và role ở đây thuộc JSON payload. Không mô tả chúng bằng QueryParameter chỉ vì chúng có cùng tên với filter.

Điểm phân biệt này đặc biệt quan trọng khi dùng HAL-FORMS. Các phần tử trong properties của template mô tả trường thuộc payload; QueryParameter là metadata cho query method parameters. Không nên giả định mọi query parameter tự động trở thành một property trong HAL-FORMS form body.

## Tạo affordance từ phương thức controller

Cách tự nhiên trong Spring MVC là định nghĩa endpoint search với các tham số `@RequestParam`, sau đó gắn affordance trỏ đến phương thức đó vào link của collection.

Ví dụ controller:

~~~java
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.Link;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.afford;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/employees")
class EmployeeController {

    private final EmployeeService employeeService;
    private final EmployeeModelAssembler assembler;

    EmployeeController(
            EmployeeService employeeService,
            EmployeeModelAssembler assembler) {
        this.employeeService = employeeService;
        this.assembler = assembler;
    }

    @GetMapping
    CollectionModel<EmployeeModel> all() {
        var employees = assembler.toCollectionModel(employeeService.findAll());

        Link search = linkTo(methodOn(EmployeeController.class)
                .search(null, null))
            .withRel("search")
            .andAffordance(afford(methodOn(EmployeeController.class)
                .search(null, null)));

        return employees.add(
            linkTo(methodOn(EmployeeController.class).all()).withSelfRel(),
            search);
    }

    @GetMapping("/search")
    CollectionModel<EmployeeModel> search(
            @RequestParam(name = "name", required = false) String name,
            @RequestParam(name = "role", required = false) String role) {

        var result = employeeService.search(name, role);
        return assembler.toCollectionModel(result);
    }
}
~~~

Ví dụ giả định `EmployeeService.search(name, role)` áp dụng các filter tương ứng và assembler chuyển kết quả thành `EmployeeModel`. Các dependency được inject qua constructor.

Điểm quan trọng nằm ở:

~~~java
andAffordance(afford(methodOn(EmployeeController.class)
    .search(null, null)))
~~~

Spring HATEOAS phân tích phương thức controller được tham chiếu để thu thập thông tin mapping, HTTP method, input/output và các query method parameters. Các tham số `@RequestParam` giúp xác định tên và tính bắt buộc của filter. Giá trị null trong lời gọi proxy ở đây dùng để tạo method invocation mô tả; nó không chạy phương thức search và không thực hiện truy vấn dữ liệu.

Link `search` cho biết nơi client khám phá thao tác tìm kiếm. Affordance gắn trên link mô tả rằng thao tác đó dùng GET và nhận các filter đã khai báo.

### Đặt tên query parameter rõ ràng

Nên khai báo tên `@RequestParam` tường minh:

~~~java
@RequestParam(name = "createdAfter", required = false)
LocalDate createdAfter
~~~

Điều này giúp hợp đồng API không phụ thuộc vào tên biến Java hoặc cấu hình biên dịch giữ parameter names. Khi đổi tên biến nội bộ, tên query parameter công khai vẫn ổn định.

### Dùng kiểu dữ liệu phù hợp

Filter có thể nhận nhiều kiểu dữ liệu:

~~~java
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;

@GetMapping("/search")
CollectionModel<EmployeeModel> search(
        @RequestParam(name = "status", required = false) EmployeeStatus status,
        @RequestParam(name = "departmentId", required = false) Long departmentId,
        @RequestParam(name = "createdAfter", required = false)
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate createdAfter) {
    // Validate and apply filters.
}
~~~

Spring MVC chuyển query string sang kiểu Java tương ứng nếu có converter phù hợp. Affordance mô tả tên và tính chất của query parameter; nó không thay thế quy tắc chuyển đổi hay validation phía server.

## Tạo affordance thủ công bằng Affordances API

Trong một số trường hợp, affordance không xuất phát trực tiếp từ một phương thức controller, hoặc cần khai báo metadata tường minh. Spring HATEOAS cung cấp API `Affordances`:

~~~java
import org.springframework.hateoas.Link;
import org.springframework.hateoas.QueryParameter;
import org.springframework.hateoas.mediatype.Affordances;
import org.springframework.http.HttpMethod;

Link collection = Link.of("/employees").withSelfRel();

Link search = Affordances.of(collection)
    .afford(HttpMethod.GET)
    .withOutput(Employee.class)
    .addParameters(
        QueryParameter.optional("name"),
        QueryParameter.optional("role"),
        QueryParameter.optional("department"))
    .withName("search")
    .toLink();
~~~

Ví dụ này tạo một affordance GET có output model là `Employee` và ba query parameter tùy chọn. Tên affordance `search` giúp client phân biệt thao tác này với các affordance khác gắn trên cùng link.

Các bước chính:

1. `Affordances.of(collection)` bắt đầu xây dựng affordance từ link hiện có.
2. `afford(HttpMethod.GET)` khai báo HTTP method.
3. `withOutput(Employee.class)` mô tả kiểu dữ liệu trả về.
4. `addParameters(...)` thêm metadata query parameter.
5. `withName("search")` đặt tên affordance.
6. `toLink()` trả về link có affordance vừa tạo.

Nếu affordance cần mô tả request body, có thể dùng `withInput(...)` hoặc `withInputAndOutput(...)`. Với thao tác GET lọc collection, thường chỉ cần output model và query parameters.

### addParameters và withParameters

Hai method có semantics khác nhau:

| Method | Hành vi |
| --- | --- |
| addParameters(...) | Bổ sung các tham số vào danh sách hiện tại |
| withParameters(...) | Thay thế toàn bộ danh sách tham số hiện tại |

Ví dụ:

~~~java
var searchLink = Affordances.of(collection)
    .afford(HttpMethod.GET)
    .withOutput(Employee.class)
    .addParameters(QueryParameter.optional("name"))
    .addParameters(QueryParameter.optional("role"))
    .withName("search")
    .toLink();
~~~

Sau hai lần gọi `addParameters`, affordance có cả `name` và `role`.

Nếu gọi:

~~~java
var affordance = Affordances.of(collection)
    .afford(HttpMethod.GET)
    .withOutput(Employee.class)
    .addParameters(QueryParameter.optional("name"))
    .withParameters(QueryParameter.optional("role"))
    .toLink();
~~~

Danh sách cuối cùng chỉ còn `role`, vì `withParameters` thay thế danh sách cũ.

### Dùng QueryParameter.of(MethodParameter)

Khi đã có metadata phương thức Spring, có thể tạo `QueryParameter` từ `MethodParameter`:

~~~java
import java.lang.reflect.Method;

import org.springframework.core.MethodParameter;
import org.springframework.hateoas.QueryParameter;

Method searchMethod = EmployeeController.class.getDeclaredMethod(
    "search", String.class, String.class);

MethodParameter nameParameter = new MethodParameter(searchMethod, 0);
QueryParameter nameFilter = QueryParameter.of(nameParameter);
~~~

`QueryParameter.of(...)` tạo metadata từ tham số phương thức. Cách này hữu ích khi xây dựng affordance bằng reflection hoặc khi muốn tái sử dụng metadata khai báo trên controller method. Với trường hợp thông thường, affordance tạo từ `methodOn(...)` đơn giản hơn vì Spring HATEOAS đã phân tích method mapping.

## QueryParameter và URI template

Query parameter có thể xuất hiện trong URI template:

~~~java
Link searchTemplate =
    Link.of("/employees/search{?name,role,department}")
        .withRel("search");
~~~

Client có thể mở rộng template bằng các giá trị:

~~~java
import java.util.Map;

Link filtered = searchTemplate.expand(Map.of(
    "name", "Frodo",
    "role", "developer"));
~~~

URI template và `QueryParameter` bổ sung cho nhau nhưng không phải cùng một thứ:

- URI template cho biết những biến nào có thể được thay thế để tạo URI.
- `QueryParameter` mô tả query parameter của affordance, gồm tên, giá trị và trạng thái required.
- Affordance còn mô tả method, target, input/output và metadata khác.

Một URI template chỉ có tên biến không nhất thiết diễn tả đầy đủ quy tắc bắt buộc hay tùy chọn. Ngược lại, metadata query parameter không tự đảm bảo mọi client có thể mở rộng URI nếu link không được tạo đúng target/template. Hãy giữ tên biến của URI template đồng bộ với tên `QueryParameter`.

## Filter nhiều giá trị

Một filter có thể nhận nhiều giá trị, ví dụ:

~~~http
GET /employees/search?role=developer&role=designer
~~~

Spring MVC có thể bind query parameter lặp thành collection:

~~~java
@GetMapping("/search")
CollectionModel<EmployeeModel> search(
        @RequestParam(name = "role", required = false) List<String> roles) {
    // Filter by any of the supplied roles.
}
~~~

Một cách biểu diễn khác là danh sách phân tách bằng dấu phẩy:

~~~http
GET /employees/search?role=developer,designer
~~~

Spring HATEOAS hỗ trợ điều khiển cách render collection-valued request parameter qua `@NonComposite`. Mặc định, URI builder dùng dạng composite, tức lặp lại tên tham số cho từng giá trị. Khi dùng `@NonComposite`, các giá trị được nối bằng dấu phẩy:

~~~java
import org.springframework.hateoas.NonComposite;

@GetMapping("/search")
CollectionModel<EmployeeModel> search(
        @NonComposite
        @RequestParam(name = "role", required = false)
        Collection<String> roles) {
    // ...
}
~~~

`@NonComposite` ảnh hưởng cách URI được tạo khi xây link từ method invocation. Hãy thống nhất một cách mã hóa danh sách và kiểm thử cả chiều tạo link lẫn chiều bind request. Không nên để client tự đoán server chấp nhận dấu phẩy, tham số lặp hay cả hai.

## Kết hợp filter với sorting và pagination

Một collection endpoint thường hỗ trợ nhiều nhóm query parameter:

| Nhóm | Ví dụ | Mục đích |
| --- | --- | --- |
| Filter | status=ACTIVE, department=engineering | Chọn tập kết quả |
| Sorting | sort=lastName,asc | Sắp xếp tập kết quả |
| Pagination | page=0&size=20 | Chia kết quả thành từng trang |

Ví dụ request:

~~~http
GET /employees/search?status=ACTIVE&department=engineering&sort=lastName,asc&page=0&size=20
~~~

Khi xây affordance thủ công, có thể mô tả toàn bộ query parameter:

~~~java
Link search = Affordances.of(Link.of("/employees/search").withRel("search"))
    .afford(HttpMethod.GET)
    .withOutput(Employee.class)
    .addParameters(
        QueryParameter.optional("status"),
        QueryParameter.optional("department"),
        QueryParameter.optional("sort"),
        QueryParameter.optional("page"),
        QueryParameter.optional("size"))
    .withName("search")
    .toLink();
~~~

Trong API thực tế, page và size thường có giá trị mặc định. Nếu chúng không bắt buộc, mô tả là optional và công bố rõ giá trị mặc định trong tài liệu/profile của API hoặc metadata phù hợp. `QueryParameter` không tự mô tả mọi quy tắc như page size tối đa, danh sách sort field được phép hoặc thứ tự mặc định.

### Giữ filter khi điều hướng trang

Khi client chuyển từ trang đầu sang trang tiếp theo, các filter và sort đang áp dụng phải được giữ lại:

~~~text
Trang đầu:
/employees/search?status=ACTIVE&sort=lastName,asc&page=0&size=20

Trang tiếp:
/employees/search?status=ACTIVE&sort=lastName,asc&page=1&size=20
~~~

Nếu server trả link `next`, client nên theo link đó thay vì tự ghép URL. Server chịu trách nhiệm tạo link trang kế tiếp với filter/sort hiện tại. Điều này tránh mất tiêu chí lọc khi client điều hướng.

## Media type quyết định cách affordance được biểu diễn

`Affordances` và `QueryParameter` là metadata tổng quát của Spring HATEOAS. Các media type cụ thể có thể chuyển metadata đó thành cấu trúc representation riêng.

### HAL và HAL-FORMS

HAL JSON tập trung vào links và embedded resources. Bản thân HAL không định nghĩa cấu trúc chuẩn để mô tả đầy đủ method và input của affordance.

HAL-FORMS mở rộng HAL bằng `_templates` để mô tả thao tác và các trường của request payload. Trong HAL-FORMS:

- Template có `method`, `target`, `contentType`, `title` và `properties`.
- `properties` mô tả các trường thuộc payload body.
- Query method parameters là metadata riêng trong mô hình affordance tổng quát.

Do đó, không nên đồng nhất query filter với property của body. Với một GET search, filter nằm trong query string. Với một POST search nhận JSON, các tiêu chí có thể nằm trong input payload và được mô tả bằng input model.

Client nên đọc representation theo media type mà server công bố. Khi cần xác nhận cách query metadata được serialize cho media type cụ thể, hãy kiểm tra response thực tế và tài liệu của media type đó; không suy đoán rằng mọi `QueryParameter` sẽ xuất hiện dưới `_templates.properties`.

### Content negotiation

Client có thể yêu cầu HAL-FORMS:

~~~http
GET /employees
Accept: application/prs.hal-forms+json
~~~

Nếu ứng dụng bật HAL-FORMS và link có affordance tương ứng, response có thể chứa `_templates`. Nếu client yêu cầu `application/hal+json`, response HAL tập trung vào links; client không nên mong chờ metadata form giống HAL-FORMS.

## Thiết kế filter an toàn và dễ tiến hóa

Query parameter là dữ liệu đầu vào do client kiểm soát. Việc công bố filter trong affordance không có nghĩa server có thể tin giá trị mà client gửi.

Hãy chú ý:

- **Whitelist filter:** chỉ hỗ trợ những trường nghiệp vụ đã công bố.
- **Whitelist sort field:** không đưa trực tiếp tên cột từ query string vào SQL hoặc JPQL.
- **Validate kiểu và miền giá trị:** ngày tháng, enum, số lượng, khoảng giá trị phải được kiểm tra.
- **Giới hạn collection:** đặt page size tối đa và giới hạn số giá trị trong filter nhiều phần tử.
- **Bảo vệ dữ liệu:** không công bố filter cho thuộc tính nội bộ hoặc dữ liệu nhạy cảm.
- **Phân quyền:** người dùng chỉ được lọc trên tập dữ liệu mà họ có quyền xem.
- **Giữ semantics ổn định:** đổi tên query parameter có thể phá vỡ client đã tích hợp.

Nếu một filter không còn được hỗ trợ, hãy có kế hoạch tương thích hoặc versioning phù hợp. Không âm thầm thay đổi ý nghĩa `status=ACTIVE` hoặc `createdAfter` trong khi giữ nguyên tên tham số.

### Không biến affordance thành cam kết quyền truy cập

Affordance mô tả thao tác mà server có thể cung cấp trong representation hiện tại. Quyền thực hiện request vẫn phải được kiểm tra ở endpoint. Link hoặc affordance có thể bị ẩn theo trạng thái và người dùng, nhưng việc ẩn metadata không thay thế authorization.

Ví dụ, một user chỉ được xem nhân viên trong phòng ban của mình. Dù client gửi `department=finance`, server vẫn phải áp dụng phạm vi truy cập theo người dùng hiện tại. Không cho phép query parameter mở rộng quyền xem dữ liệu.

## Kiểm thử filter và affordance

Nên kiểm thử hai lớp riêng:

1. **Hành vi endpoint:** query parameters thực sự lọc đúng kết quả.
2. **Hợp đồng hypermedia:** response công bố đúng relation và affordance cho media type đang dùng.

### Kiểm thử QueryParameter

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.hateoas.QueryParameter;

class QueryParameterTest {

    @Test
    void describesOptionalAndRequiredFilters() {
        QueryParameter status = QueryParameter.optional("status");
        QueryParameter fromDate = QueryParameter.required("fromDate");

        assertThat(status.getName()).isEqualTo("status");
        assertThat(status.isRequired()).isFalse();
        assertThat(fromDate.getName()).isEqualTo("fromDate");
        assertThat(fromDate.isRequired()).isTrue();
    }

    @Test
    void canAttachAValueToAQueryParameter() {
        QueryParameter status =
            QueryParameter.optional("status").withValue("ACTIVE");

        assertThat(status.getValue()).isEqualTo("ACTIVE");
    }
}
~~~

Test này xác minh semantics cơ bản của value object. Nó không kiểm tra cách một media type cụ thể serialize affordance.

### Kiểm thử hành vi filter endpoint

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class EmployeeSearchTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void filtersEmployeesByRole() throws Exception {
        mockMvc.perform(get("/employees/search")
                .accept("application/hal+json")
                .param("role", "developer"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._embedded.employees").isArray());
    }
}
~~~

Test giả định endpoint trả collection HAL và dữ liệu kiểm thử được chuẩn bị trước. Trong test đầy đủ, nên kiểm tra từng item trong collection đều thỏa điều kiện role, đồng thời kiểm tra trường hợp không có kết quả.

### Kiểm thử affordance theo media type

Khi kiểm thử metadata, gửi `Accept` đúng media type mà ứng dụng hỗ trợ. Với HAL-FORMS, có thể kiểm tra response có template cho thao tác search:

~~~java
mockMvc.perform(get("/employees")
        .accept("application/prs.hal-forms+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$._links.search.href").exists());
~~~

Nếu ứng dụng cấu hình HAL-FORMS để render affordance thành template, hãy kiểm tra tên template, method và target theo JSON thực tế. Query parameter có thể được biểu diễn khác nhau tùy media type và cách affordance được xây dựng; không nên hard-code một JSONPath cho query metadata khi chưa xác nhận hợp đồng output.

Các trường hợp nên kiểm thử:

1. Relation search xuất hiện trên collection resource.
2. Affordance dùng đúng HTTP method và target.
3. Tên query parameter khớp tên endpoint thực sự nhận.
4. Tham số optional và required được khai báo đúng.
5. Giá trị filter hợp lệ tạo ra tập kết quả chính xác.
6. Filter không hợp lệ nhận lỗi validation phù hợp.
7. Filter nhiều giá trị được parse theo định dạng đã công bố.
8. Sorting và pagination giữ lại các filter đang áp dụng.
9. Người dùng không có quyền không thể mở rộng tập dữ liệu bằng query parameter.
10. HAL và HAL-FORMS trả representation phù hợp với `Accept`.

## Những sai lầm thường gặp

**Nhầm query filter với request body.** Filter GET thường nằm trong query string và được mô tả bằng `QueryParameter`; input payload của POST/PATCH được mô tả bằng input model.

**Chỉ tạo URI template mà không mô tả affordance.** URI template cho biết biến có thể mở rộng; affordance bổ sung method, target và metadata query.

**Đánh dấu tất cả filter là required.** Filter thường tùy chọn. Chỉ dùng `required` khi endpoint thực sự yêu cầu tham số.

**Dùng withParameters khi muốn bổ sung.** Method này thay thế danh sách hiện tại. Dùng `addParameters` để nối thêm tham số.

**Cho rằng QueryParameter tự thực thi filter.** Nó chỉ mô tả hợp đồng. Controller/service vẫn phải đọc và áp dụng tiêu chí lọc.

**Coi QueryParameter là HAL-FORMS property.** Query parameter và body property là hai nhóm metadata khác nhau. Hình dạng serialize phụ thuộc media type.

**Không đồng bộ tên query parameter và URI template.** Client có thể tạo URI sai nếu metadata và biến template không khớp.

**Để client tự ghép URL trang tiếp theo.** Theo link pagination từ server để giữ nguyên filter và sorting.

**Tin query parameter vì server đã công bố affordance.** Mọi giá trị vẫn phải được validate và authorize ở server.

**Không kiểm thử representation theo Accept.** HAL và HAL-FORMS có khả năng mô tả affordance khác nhau; kiểm thử đúng media type mà client sử dụng.

## Kết luận

Mô tả filter trong affordance giúp server công bố các query parameter mà thao tác tìm kiếm hoặc lọc collection hỗ trợ. Spring HATEOAS dùng `QueryParameter` để biểu diễn tên, giá trị và tính bắt buộc của tham số; `Affordances` và `ConfigurableAffordance` cho phép gắn metadata đó vào link theo cách thủ công. Khi tạo affordance từ controller method, Spring HATEOAS có thể phân tích mapping và tham số phương thức để thu thập thông tin.

Hãy tách query filter khỏi input payload, giữ tên tham số ổn định, dùng `addParameters` để bổ sung và `withParameters` để thay thế danh sách. Kết hợp filter với sorting/pagination bằng các link do server tạo, kiểm thử output theo media type, và luôn validate/authorize giá trị ở server. Affordance giúp client khám phá hợp đồng; endpoint vẫn là nơi thực thi quy tắc tìm kiếm.

Tài liệu tham khảo:

- [Spring HATEOAS Reference — Affordances and manual construction](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#fundamentals.affordances).
- [Spring HATEOAS API — QueryParameter](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/QueryParameter.html).
- [Spring HATEOAS API — ConfigurableAffordance](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/ConfigurableAffordance.html).
- [Spring HATEOAS API — Affordances](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/mediatype/Affordances.html).
- [Spring Framework Reference — @RequestParam](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestparam.html).
