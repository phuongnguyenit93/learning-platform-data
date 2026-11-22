# @Consumes, @Produces và ánh xạ media type

## 1. Bài toán: cùng URI nhưng không phải nội dung nào cũng được nhận

Một REST API báo cáo cho phép **POST /reports** để tạo báo cáo bằng JSON và **GET /reports/{id}** để đọc báo cáo bằng JSON. Sau đó đội sản phẩm muốn thêm định dạng CSV ở endpoint **GET /reports/{id}/export**. Client có thể gửi một số yêu cầu:

- **POST** với **Content-Type: application/json** và body JSON hợp lệ.
- **POST** với **Content-Type: text/plain** dù endpoint chỉ chấp nhận JSON.
- **GET** với **Accept: application/json** để lấy representation JSON.
- **GET** với **Accept: text/csv** để tải CSV.
- **GET** với **Accept: application/xml** khi API chưa có định dạng XML.

Ở Jakarta REST (tên trước đây thường gặp: **JAX-RS**), hai annotation quan trọng xử lý việc lựa chọn media type: **@Consumes** mô tả media type của **request entity** mà tài nguyên có thể nhận; **@Produces** mô tả media type **response representation** có thể được tạo ra. Chúng kết nối trực tiếp với **Content-Type, Accept** và cơ chế **MessageBodyReader/MessageBodyWriter**.

Trong module **INTEGRATION_API_REST**, bài tập này gắn content negotiation với thiết kế resource/URI, phương thức và mã HTTP, hợp đồng OpenAPI, xác thực/phân quyền, cache và kiểm thử Java/Jakarta REST. Spring MVC có cách khai báo tương tự nhưng là **framework khác**; bài sẽ đối chiếu đủ để người học không nhầm hai bộ annotation.

**Mục tiêu học tập:** Sau bài, bạn có thể giải thích và cấu hình @Consumes/@Produces ở class/method, phân biệt lỗi **415** với **406**, hiểu vì sao annotation chưa đủ để serialize dữ liệu, thiết kế nhiều representation an toàn, và kiểm thử hợp đồng bằng HTTP/JUnit.

## 2. Content-Type và Accept là hai chiều HTTP khác nhau

**Content-Type** của request mô tả **body client gửi**. Trong ví dụ:

~~~http
POST /reports HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

{"title":"Doanh thu quý IV"}
~~~

Method **@Consumes("application/json")** chấp nhận request media type JSON. Gửi **text/plain** tới endpoint chỉ hỗ trợ JSON thường nhận **415 Unsupported Media Type**. Gửi JSON **sai cú pháp** dù có Content-Type JSON là lỗi parsing/validation (thường **400**), không phải 415.

**Accept** mô tả loại representation **client muốn nhận**. GET chỉ có **@Produces("application/json")** nhưng client gửi **Accept: application/xml** thường nhận **406 Not Acceptable**. Client có thể khai nhiều lựa chọn:

~~~http
Accept: application/json;q=0.9, text/csv;q=0.5
~~~

**q** biểu thị trọng số ưu tiên trong khoảng 0–1; **q=0** là không chấp nhận. **Thiếu Accept** hoặc **Accept: */*** thường cho phép server chọn một representation hỗ trợ. Lựa chọn còn phụ thuộc specificity/media parameters, không chỉ thứ tự từ trái sang phải.

| Thành phần | Ý nghĩa | Điều kiện/response |
|---|---|---|
| Request **Content-Type** | Client khai dạng byte gửi lên | **@Consumes**, reader; không phù hợp → **415** |
| Request **Accept** | Client khai dạng byte mong nhận | **@Produces**, writer; không phù hợp → **406** |
| Response **Content-Type** | Server xác nhận representation thực | Phải khớp body thật, không chỉ annotation |
| **Content-Encoding** | Cách mã hóa representation như gzip | Khác với media type, phải giải mã/giới hạn đúng |

Không trộn lỗi 406 và 415. Authentication, authorization, routing và providers có thể trả lỗi trước bước negotiation; nếu muốn test riêng 406/415, phải gửi request **có quyền hợp lệ** và cấu hình server phù hợp.

## 3. @Consumes và @Produces chọn resource method như thế nào?

Jakarta REST dùng annotation từ package **jakarta.ws.rs**:

- **@Path** định vị resource và sub-resource.
- **@GET, @POST, @PUT, @DELETE...** biểu thị HTTP method.
- **@Consumes("application/json")** khai báo request entity media type được chấp nhận.
- **@Produces("application/json")** khai báo response representation media type có thể xuất.

Hai annotation có thể đặt trên **resource class** hoặc **resource method**:

~~~java
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.MediaType;

@Path("/reports")
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public class ReportResource {

    @POST
    public void create(ReportCreateRequest body) { /* ... */ }

    @PUT
    @Path("{id}/description")
    @Consumes(MediaType.TEXT_PLAIN)
    public void replaceDescription(
            @PathParam("id") String id, String body) {
        /* ... */
    }
}
~~~

Trong ví dụ, POST **kế thừa @Consumes JSON** ở class; PUT description **ghi đè @Consumes ở method** thành text/plain. Chú ý: annotation cấp method **không cộng dồn** thêm media type vào danh sách cấp class. Muốn cho phép nhiều định dạng, liệt kê chúng trong **một annotation**:

~~~java
@Produces({MediaType.APPLICATION_JSON, "text/csv"})
~~~

Tương tự, một @Produces ở method có thể thay thế lựa chọn chung của class. Đặt annotation ngay nơi khác biệt có ý nghĩa giúp tránh vô tình áp JSON cho endpoint chỉ trả file CSV.

### 3.1. @Consumes/@Produces không phải kiểm tra body thủ công

Một Jakarta REST runtime thực hiện đại khái:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Match URI và HTTP method]
    B --> C[Chọn method khớp request Content-Type]
    C -->|Không hỗ trợ| D[415 Unsupported Media Type]
    C --> E[Chọn representation phù hợp Accept]
    E -->|Không có representation| F[406 Not Acceptable]
    E --> G[MessageBodyReader đọc entity]
    G --> H[Resource method + service]
    H --> I[MessageBodyWriter ghi response entity]
    I --> J[HTTP response với Content-Type]
~~~

Đây là **mô hình tư duy**, không phải thứ tự tuyệt đối của mọi container. Authentication, authorization, exception mapping, filters và provider selection có thể tác động hoặc chặn request trước các bước trên. Một resource method được match về annotation chưa đủ để body được đọc/ghi thành công; phải có provider tương thích.

### 3.2. Không nên dùng wildcard quá rộng

**@Consumes("*/*")** cho biết resource có thể chấp nhận mọi media type về mặt lựa chọn method, nhưng body reader vẫn cần hiểu entity; nó không tự cho service khả năng xử lý XML, ảnh hoặc binary. **@Produces("*/*")** cũng không biến đối tượng Java thành mọi định dạng người dùng muốn.

Khai báo media type cụ thể theo contract:

- POST tạo báo cáo: **application/json**.
- PUT ghi một trường text: **text/plain**, nếu đó là thiết kế có chủ đích.
- GET xuất báo cáo: **application/json** và/hoặc **text/csv** nếu có writer phù hợp.

Đừng đặt **@Consumes** chỉ để “mở rộng” GET không có request body; hãy ưu tiên HTTP semantics thật và tránh khiến client tưởng GET cần gửi một entity để hoạt động.

## 4. Ví dụ resource Jakarta REST: tạo và đọc báo cáo

Ví dụ dùng Java 17+, Jakarta REST 3.1+ và **một JSON provider đã được cài đặt**, chẳng hạn triển khai hỗ trợ JSON-B hoặc Jackson. Các type **ReportService, ReportView, ReportCreateRequest** chỉ là thành phần ứng dụng, không phải API chuẩn sẵn có.

~~~java
import java.net.URI;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.*;

record ReportCreateRequest(@NotBlank String title) {}
record ReportView(String id, String title, String state) {}

@Path("/reports")
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public class ReportResource {
    private final ReportService service;

    public ReportResource(ReportService service) {
        this.service = service;
    }

    @POST
    public Response create(
            @Valid ReportCreateRequest request,
            @Context UriInfo uriInfo,
            @Context SecurityContext security) {

        String actor = requireAuthenticatedActor(security);
        ReportView created = service.create(actor, request.title());
        URI location = uriInfo.getAbsolutePathBuilder()
            .path(created.id()).build();

        return Response.created(location)
            .entity(created)
            .type(MediaType.APPLICATION_JSON_TYPE)
            .build();
    }

    @GET
    @Path("{id}")
    public ReportView get(
            @PathParam("id") String id,
            @Context SecurityContext security) {

        String actor = requireAuthenticatedActor(security);
        return service.getVisible(actor, id);
    }

    private String requireAuthenticatedActor(
            SecurityContext security) {
        if (security == null || security.getUserPrincipal() == null) {
            throw new NotAuthorizedException("Bearer");
        }
        return security.getUserPrincipal().getName();
    }
}
~~~

**Giả định:** Báo cáo được tạo đồng bộ và hoàn tất việc tạo resource trong POST, nên trả **201 Created** với **Location**. Nếu công việc chỉ mới được tiếp nhận để xử lý sau, dùng **202 Accepted và một monitor resource** theo hợp đồng riêng, không đổi status vì HTTP request kết thúc nhanh.

**Chỗ phải triển khai thêm:** đăng ký resource và JSON provider trong runtime Jersey/RESTEasy/CXF tương ứng; cấu hình validation, authentication, authorization, exception mapping. Một số provider có yêu cầu riêng để deserialize Java records; kiểm thử thực tế JSON-B/Jackson đang dùng, hoặc thay records bằng DTO có constructor/accessors thích hợp. Service cần kiểm tra quyền trên từng report, không chỉ dựa vào việc actor đã đăng nhập.

## 5. Annotation không tự đọc hoặc ghi dữ liệu

Jakarta REST tách **resource method selection** khỏi việc biến request/response body thành Java object:

| Cơ chế | Trách nhiệm |
|---|---|
| **@Consumes** | Method nhận request media type nào? |
| **MessageBodyReader<T>** | Chuyển byte request thành Java type T |
| **@Produces** | Method có thể trả media type nào? |
| **MessageBodyWriter<T>** | Chuyển Java type T thành byte response |
| **ExceptionMapper<E>** | Tạo response có cấu trúc từ lỗi |

Một method nhận **CreateReportRequest** JSON cần JSON reader; trả **ReportView** JSON cần JSON writer. Runtime có thể dùng providers JSON-B/Jackson, XML/JAXB hoặc String/byte[] theo cấu hình, không phải cứ có @Produces là tự có serializer. Khi thiếu provider hoặc provider lỗi, status phụ thuộc nguyên nhân và thời điểm; không mặc định mọi lỗi serialization đều là **406**.

**Khi POST nhận 415:** kiểm **Content-Type**, @Consumes class/method và provider đọc kiểu request. **Khi GET nhận 406:** kiểm **Accept**, @Produces và representation thực sự có thể ghi. Với JSON sai cú pháp nhưng media type được hỗ trợ, lỗi thuộc parsing/validation (thường **400**), không phải tự chuyển 415.

### 5.1. Charset, subtype và representation thực

~~~http
Content-Type: text/plain; charset=UTF-8
~~~

**charset** mô tả cách mã hóa ký tự, không thay đổi loại văn bản thành JSON. Với **application/problem+json** hoặc **application/vnd.example.report+json**, đừng mặc định **@Consumes("application/json")** bao phủ mọi subtype có hậu tố **+json**; cấu hình provider và media ranges của implementation phải được kiểm thử.

Một response ghi **Content-Type: application/json** nhưng body là **XML/text không phải JSON** vẫn sai hợp đồng. @Produces hỗ trợ negotiation; **MessageBodyWriter và dữ liệu thực** mới quyết định representation đúng. Kiểm body bằng parser tương ứng, không chỉ assert header.

## 6. Cung cấp nhiều representation: JSON và CSV

GET xuất báo cáo có thể hỗ trợ **Accept: application/json** hoặc **Accept: text/csv**, đều phải được phân quyền. Với CSV, response minh họa:

~~~http
GET /reports/r-101/export HTTP/1.1
Accept: text/csv
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: text/csv; charset=UTF-8
Content-Disposition: attachment; filename="report.csv"
Vary: Accept
Cache-Control: private, no-store

id,title,state
r-101,Doanh thu quý IV,READY
~~~

**Vary: Accept** báo cache phải phân biệt representation theo Accept; nó **không** thay thế Cache-Control hoặc phân quyền đối với dữ liệu cá nhân.

### 6.1. Lựa chọn theo HTTP negotiation thay vì so chuỗi

Trong resource class ở phần 4, một method có thể chọn biến thể với **Request.selectVariant**:

~~~java
import java.util.List;
import jakarta.ws.rs.*;
import jakarta.ws.rs.core.*;

@GET
@Path("{id}/export")
@Produces({MediaType.APPLICATION_JSON, "text/csv"})
public Response export(
        @PathParam("id") String id,
        @Context Request request,
        @Context SecurityContext security) {

    String actor = requireAuthenticatedActor(security);
    ReportView report = service.getVisible(actor, id);

    List<Variant> variants = List.of(
        new Variant(MediaType.APPLICATION_JSON_TYPE, null, null),
        new Variant(MediaType.valueOf("text/csv"), null, null)
    );
    Variant chosen = request.selectVariant(variants);
    if (chosen == null) {
        return Response.notAcceptable(variants).build();
    }

    if (chosen.getMediaType().isCompatible(
            MediaType.valueOf("text/csv"))) {
        // Encoder phải escape CSV và ngăn formula injection.
        String csv = reportCsvEncoder.encode(report);
        return Response.ok(csv)
            .type("text/csv; charset=UTF-8")
            .header("Content-Disposition",
                "attachment; filename=\"report.csv\"")
            .header("Vary", "Accept")
            .header("Cache-Control", "private, no-store")
            .build();
    }
    return Response.ok(report)
        .type(MediaType.APPLICATION_JSON_TYPE)
        .header("Vary", "Accept")
        .header("Cache-Control", "private, no-store")
        .build();
}
~~~

Đoạn này là **method minh họa** cần đặt trong resource có injected **service** và **reportCsvEncoder**. Cần provider phù hợp: JSON writer cho ReportView, String/CSV writer cho CSV. Với file lớn, dùng streaming hoặc resource download thay vì dựng một String rất lớn. **Request.selectVariant** xử lý Accept có danh sách/q-values tốt hơn **Accept.equals("text/csv")**.

Nếu chỉ có JSON, runtime thường tự thương lượng theo **@Produces(JSON)**. Cũng có thể dùng hai method cùng path/HTTP method nhưng @Produces khác nhau nếu không gây mơ hồ. Test **Accept JSON, CSV, wildcard, q-values, không hỗ trợ và thiếu Accept**.

## 7. Mã HTTP, lỗi có cấu trúc và thứ tự kiểm tra

| Request | HTTP status phù hợp trong contract ví dụ | Điều phải bảo đảm |
|---|---|---|
| POST JSON hợp lệ | **201 Created** | Location tới report, body JSON hợp schema |
| POST gửi **text/plain** tới method chỉ nhận JSON | **415 Unsupported Media Type** | Không tạo report |
| POST JSON hỏng cú pháp | **400 Bad Request** | Không xử lý như JSON hợp lệ |
| POST JSON hợp lệ nhưng thiếu title | **400/422** theo validation contract | Không tạo report |
| GET chỉ chấp nhận XML trong khi server chỉ có JSON | **406 Not Acceptable** | Không giả vờ trả XML |
| GET JSON/CSV được chấp nhận | **200 OK** | Content-Type đúng byte và schema |
| GET một report không tồn tại | **404 Not Found** | Không lộ report khác tenant |
| Không có credential hợp lệ | **401 Unauthorized** | Cơ chế auth phản hồi đúng, không rò tài nguyên |
| Có credential nhưng không có quyền | **403 Forbidden**, hoặc 404 che giấu | Phân quyền theo resource |
| Server lỗi khi serialize đúng media type đã chọn | **5xx** thích hợp | Không gán thành 406 nếu nguyên nhân là bug dữ liệu |

**Điểm tinh tế:** Nếu request vừa thiếu quyền vừa có Accept không hỗ trợ, hệ thống có thể trả lỗi bảo mật trước khi xét media type, tùy filter chain và implementation. Không nên xây test mặc định “Accept XML luôn phải 406” khi request chưa được xác thực. Tạo fixture có quyền hợp lệ để kiểm chính xác negotiation.

### 7.1. Thông báo lỗi cũng là một representation

Với REST API hiện đại, **application/problem+json** (RFC 9457) là lựa chọn hữu ích:

~~~http
HTTP/1.1 415 Unsupported Media Type
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type":"https://api.example.test/problems/unsupported-media-type",
  "title":"Unsupported Media Type",
  "status":415,
  "code":"UNSUPPORTED_REPORT_FORMAT",
  "detail":"POST /reports chỉ chấp nhận application/json."
}
~~~

Không coi **@Produces(application/json)** trên happy-path là cách tự động bảo đảm mọi exception sẽ có body **application/problem+json**. Error responses do framework, filters hoặc exception mappers tạo ra có quá trình xử lý riêng. Nếu client đặt **Accept: application/xml** nhưng API chỉ có Problem JSON, cần thiết kế và kiểm thử **error representation negotiation/fallback**: không tự tuyên bố mọi lỗi chắc chắn có JSON body ngay cả khi client không chấp nhận nó.

### 7.2. ExceptionMapper và WebApplicationException

Jakarta REST cung cấp **ExceptionMapper<E>** để chuyển exception thành Response. Ví dụ domain validation:

~~~java
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;
import jakarta.ws.rs.ext.ExceptionMapper;
import jakarta.ws.rs.ext.Provider;

record ApiProblem(String type, String title,
                  int status, String code, String detail) {}

@Provider
public class InvalidReportMapper
        implements ExceptionMapper<InvalidReportException> {
    @Override
    public Response toResponse(InvalidReportException error) {
        ApiProblem p = new ApiProblem(
            "https://api.example.test/problems/invalid-report",
            "Invalid Report", 422, "INVALID_REPORT",
            "Thông tin báo cáo không đáp ứng quy tắc nghiệp vụ."
        );
        return Response.status(422)
            .type("application/problem+json")
            .header("Cache-Control", "no-store")
            .entity(p)
            .build();
    }
}
~~~

**InvalidReportException** là kiểu ứng dụng giả định; **ApiProblem** cần provider có khả năng serialize thành JSON cho media type **application/problem+json** (không mặc định mọi JSON provider hỗ trợ mọi subtype +json). Với Jakarta REST, các lỗi HTTP có thể được biểu diễn bằng **BadRequestException, NotAcceptableException, NotSupportedException, NotFoundException** hoặc response do runtime sinh; mapping lại phải bảo đảm không làm mất status, WWW-Authenticate và header quan trọng.

**Không bắt mọi Exception để trả 400, 406 hoặc 415**. Đặc biệt, lỗi database, lỗi cấu hình provider, lỗi mã hóa hoặc sự cố storage cần được quan sát và ánh xạ đúng nguyên nhân. Không phản chiếu stack trace, SQL, credential hoặc raw request body trong error detail.

## 8. Bảo mật và an toàn nội dung

**Content-Type là dữ liệu client khai**, không phải kiểm chứng nội dung hay quyền. API chấp nhận JSON/CSV vẫn phải xác thực token và kiểm tra authorization theo **report/tenant** khi đọc, tạo và xuất.

| Rủi ro | Kiểm soát |
|---|---|
| JSON sai cú pháp, quá lớn hoặc quá sâu | Parser/DTO validation, giới hạn byte/depth, timeout |
| Field **ownerId, tenantId, role** do client tự thêm | Request DTO allowlist; lấy identity từ SecurityContext đã xác thực |
| Report ID thuộc tenant khác | Kiểm quyền trước khi trả body, ETag hoặc representation |
| CSV chứa công thức spreadsheet | CSV escaping và chính sách chống formula injection |
| Browser sniff/hiển thị active content | Content-Type thật, Content-Disposition, cân nhắc **nosniff** và origin cách ly |
| Problem Details lộ thông tin nội bộ | Code ổn định, thông điệp an toàn; log riêng có redaction |
| Shared cache lẫn dữ liệu cá nhân | Cache-Control private/no-store; Vary không phải phân quyền |

Ví dụ POST **Content-Type: application/json** với **{"title":null,"ownerId":"other-tenant"}** vẫn có thể match @Consumes, nhưng phải bị kiểm tra bởi Bean Validation và policy về field không cho phép. Lỗi lúc này thuộc **400/422** theo contract, không phải 415. **SecurityContext.getUserPrincipal()** chỉ đáng tin khi authentication filter/runtime đã thực sự xác minh principal; CORS không phải authorization.

## 9. Liên hệ Spring MVC: cú pháp tương tự, runtime khác

Jakarta REST:

~~~java
@POST
@Consumes(MediaType.APPLICATION_JSON)
@Produces(MediaType.APPLICATION_JSON)
public Response create(ReportCreateRequest request) { /* ... */ }
~~~

Spring MVC có cách biểu diễn tương ứng:

~~~java
@RestController
@RequestMapping("/reports")
class SpringReportController {
    private final ReportService service;

    SpringReportController(ReportService service) {
        this.service = service;
    }

    @PostMapping(
        consumes = org.springframework.http.MediaType.APPLICATION_JSON_VALUE,
        produces = org.springframework.http.MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<ReportView> create(
            @Valid @RequestBody ReportCreateRequest request,
            Principal principal) {

        ReportView view = service.create(
            principal.getName(), request.title());
        return ResponseEntity.created(
            URI.create("/reports/" + view.id())).body(view);
    }
}
~~~

Đây là **controller Spring MVC**, cần imports, DTO/service và security cấu hình phù hợp. **@RequestBody** chuyển request thành Java object bằng **HttpMessageConverter** (ví dụ MappingJackson2HttpMessageConverter), còn **@PostMapping(consumes/produces)** định nghĩa điều kiện mapping; phản hồi media type cần khớp converter và body. Mã status thường tương ứng: unsupported request format → **415**, requested response type không đáp ứng → **406**.

| Jakarta REST | Spring MVC |
|---|---|
| **@Consumes / @Produces** | **@RequestMapping, @PostMapping... consumes/produces** |
| **MessageBodyReader/MessageBodyWriter** | **HttpMessageConverter** |
| **@Provider ExceptionMapper** | **@RestControllerAdvice / @ExceptionHandler** |
| **Response** | **ResponseEntity** |
| **@Context SecurityContext** | Spring Security Authentication/Principal |

Không giả định **@Consumes** có hiệu lực trong một Spring MVC controller thuần khi chưa chạy Jakarta REST runtime, hoặc ngược lại Spring **@PostMapping** được một Jakarta REST implementation tự nhận diện. Cần chọn đúng stack/dependencies, đăng ký provider/converter và chạy integration test.

## 10. Kiểm thử HTTP: status, headers và byte thực

### 10.1. Ma trận kiểm thử tối thiểu

| ID | Request có quyền hợp lệ | Kết quả cần kiểm |
|---|---|---|
| M01 | POST JSON đúng schema, Accept JSON | **201**, Location, Content-Type JSON, body parse được |
| M02 | POST text/plain đến endpoint chỉ nhận JSON | **415**, không tạo report |
| M03 | POST JSON sai cú pháp | **400** theo provider/contract, không tạo report |
| M04 | POST JSON thiếu title | Validation status đúng **400/422**, không lưu |
| M05 | GET với Accept JSON | **200**, JSON đúng schema |
| M06 | GET với Accept XML khi chỉ hỗ trợ JSON | **406** |
| M07 | GET export với Accept CSV | **200**, Content-Type text/csv, body CSV hợp lệ, Content-Disposition |
| M08 | GET export với Accept JSON | **200**, JSON; **Vary: Accept** khi cache thương lượng |
| M09 | GET export với Accept có q-values và wildcard | Lựa chọn theo thương lượng, không tự kiểm chuỗi bằng equals |
| M10 | GET report khác tenant | **403/404** theo policy; không rò JSON/CSV/ETag |
| M11 | Provider JSON/CSV không được đăng ký | Test cấu hình phải phát hiện; không gửi Content-Type giả |
| M12 | Response lỗi do gateway/security filter | Status và schema lỗi được công bố đúng, không lộ nội bộ |

**Quan trọng:** với M02, M06 cần dùng **valid authentication fixture**; nếu request chưa được xác thực, server có thể trả 401/403 trước khi đi đến bước media negotiation. Đừng kết luận 406/415 hỏng chỉ vì test vô tình thiếu token.

### 10.2. Ví dụ JUnit 5 + Java HttpClient

Một integration test đi qua **HTTP server thật** (Jakarta REST runtime đã khởi động, JSON provider được đăng ký) có thể viết:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.net.URI;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;

class ReportMediaTypeIT {
    private final HttpClient client = HttpClient.newHttpClient();

    // Fixture test cung cấp baseUri, testToken và report r-101
    // thuộc về principal được quyền đọc.
    URI baseUri;
    String testToken;

    @Test
    void rejectsUnsupportedRequestMediaType() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                baseUri.resolve("/reports"))
            .header("Authorization", "Bearer " + testToken)
            .header("Content-Type", "text/plain")
            .header("Accept", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString("not-json"))
            .build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
        assertEquals(415, response.statusCode());
        // Thêm assertion DB: không có report mới được tạo.
    }

    @Test
    void rejectsUnsupportedResponseMediaType() throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                baseUri.resolve("/reports/r-101"))
            .header("Authorization", "Bearer " + testToken)
            .header("Accept", "application/xml")
            .GET().build();

        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
        assertEquals(406, response.statusCode());
    }
}
~~~

**Fixture phải tự gán baseUri và testToken**, không sử dụng các field null như một test chạy độc lập. **baseUri.resolve("/reports")** là URI resolution từ root; nếu deployment có base path như **/api/v1**, dùng builder giữ đúng base path khi thực thi. Test cũng cần khởi động/dọn tài nguyên test và tạo báo cáo có quyền trước M06.

Để kiểm serialization, không chỉ assert **Content-Type: application/json**; parse **byte body thật** bằng JSON parser và so schema. Với CSV, đọc file theo charset được công bố, xác minh escape dấu phẩy/quote/newline và phòng ngừa formula injection. Với request có q-values, so đáp án theo các media type server hỗ trợ, không cố định thứ tự nếu nhiều lựa chọn đều hợp lệ.

### 10.3. Đối chiếu với OpenAPI

Trong OpenAPI 3.x, **requestBody.content** xác định loại nội dung được nhận và **responses.<status>.content** xác định loại response. Ví dụ:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: "#/components/schemas/CreateReport"
responses:
  "201":
    description: Created
    content:
      application/json:
        schema:
          $ref: "#/components/schemas/Report"
  "415":
    description: Request Content-Type không được hỗ trợ
~~~

Với GET export, khai cả **application/json** và **text/csv** trong response 200; mô tả **406** khi không có representation chấp nhận được. Lỗi có thể dùng **application/problem+json** riêng. OpenAPI không tự cài provider hoặc annotation; kiểm contract bằng HTTP tests.

## 11. Bài thực hành: sửa hợp đồng media type bị sai

Một API quản lý hóa đơn có các endpoint:

~~~text
POST /invoices          -- nhận JSON
GET  /invoices/{id}     -- trả JSON
GET  /invoices/{id}/export -- trả JSON hoặc CSV
~~~

Hệ thống đang có vấn đề: POST nhận cả **text/plain** rồi lỗi parser; GET khi client gửi **Accept: application/xml** vẫn trả JSON; CSV trả body đúng nhưng **Content-Type: application/json**; một tenant có thể export hóa đơn của tenant khác nếu biết ID.

**Yêu cầu:**

1. Đặt **@Consumes/@Produces** ở class/method để POST chỉ nhận JSON, GET thông thường chỉ trả JSON, export hỗ trợ JSON và CSV.
2. Nêu status khi **POST text/plain**, **POST JSON hỏng**, **GET Accept XML**, **GET export Accept CSV**, **GET không có quyền**.
3. Giải thích vì sao khai **@Produces("text/csv")** chưa đủ nếu thiếu writer hoặc application trả sai byte.
4. Viết ba HTTP integration tests: lỗi 415, lỗi 406 và response CSV đúng **Content-Type/Vary/body**.
5. Kiểm tra khả năng copy response CSV vào bảng tính mà không kích hoạt công thức và xác minh tenant isolation.

**Gợi ý đáp án:** POST **@Consumes(application/json)**, method export **@Produces({application/json, text/csv})**, GET thường dùng @Produces JSON từ class. **415** cho media type request không hỗ trợ, **400** cho JSON malformed, **406** cho Accept XML không thể đáp ứng, **200 + text/csv** khi export hợp lệ, **403/404** theo chính sách quyền. Cần provider/writer, encoder CSV an toàn, authorization trước khi export và test qua runtime thật.

## 12. Checklist và tài liệu tham khảo

- [ ] **@Consumes** khớp **Content-Type của request**; **@Produces** khớp **Accept và response Content-Type**.
- [ ] Nắm quy tắc class/method override; không dùng wildcard để che thiếu provider hoặc validation.
- [ ] Đã đăng ký **MessageBodyReader/Writer** cho Java type và media type thực sự hỗ trợ.
- [ ] Phân biệt **415 request media type**, **406 response negotiation**, **400/422** khi content được chấp nhận nhưng không hợp lệ.
- [ ] JSON/CSV/XML được serialize bằng writer phù hợp, charset và byte đúng với Content-Type.
- [ ] Với nhiều representation, kiểm **Accept q-values, wildcard, Vary: Accept** và cache/privacy.
- [ ] Xác thực, phân quyền theo resource/tenant và DTO validation độc lập với media type.
- [ ] Error mapper không làm mất status/header bảo mật, không lộ stack trace hoặc dữ liệu nội bộ.
- [ ] Test bằng runtime Jakarta REST thực, kiểm cả **HTTP status, headers, body**; so OpenAPI với triển khai.
- [ ] Không nhầm annotation Jakarta REST với **Spring MVC consumes/produces** dù ý tưởng gần nhau.

Tài liệu: [Jakarta RESTful Web Services Specification](https://jakarta.ee/specifications/restful-ws/); [Jakarta REST API](https://jakarta.ee/specifications/restful-ws/); [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) (Content-Type, Accept, 406, 415); [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457); [Spring MVC — Mapping Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html); [OpenAPI Specification](https://spec.openapis.org/oas/latest.html).

**Ghi nhớ:** **@Consumes** xác định nội dung có thể **nhận**, **@Produces** xác định biểu diễn có thể **trả**. Chúng chỉ là điều kiện lựa chọn resource; **provider, dữ liệu hợp lệ, quyền truy cập và kiểm thử HTTP thực** quyết định API có giữ đúng hợp đồng hay không.
