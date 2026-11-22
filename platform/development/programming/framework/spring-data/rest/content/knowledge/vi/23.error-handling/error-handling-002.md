# 400 cho tham số, JSON hoặc dữ liệu đầu vào không hợp lệ

## Mục tiêu

Sau bài này, bạn có thể:

- Nhận diện những trường hợp Spring Data REST thường trả HTTP **400 Bad Request**.
- Phân biệt lỗi parse tham số, deserialize JSON và validation dữ liệu.
- Tìm đúng nguyên nhân từ request, response body và server log.
- Dùng Bean Validation hoặc Spring Validator để kiểm tra dữ liệu đầu vào.
- Thiết kế error response nhất quán, có mã lỗi và thông tin field phù hợp.
- Phân biệt 400 với 404, 406, 409, 412 và 415.
- Viết kiểm thử cho request hợp lệ và các dạng input sai thường gặp.

## 1. HTTP 400 có nghĩa gì?

**400 Bad Request** cho biết server không thể xử lý request vì request hoặc dữ liệu đầu vào không hợp lệ theo hợp đồng API. Với Spring Data REST, lỗi có thể xuất hiện trước khi repository được gọi hoặc trong lúc framework chuyển dữ liệu HTTP thành domain object.

Ví dụ:

- Query parameter yêu cầu số nguyên nhưng client gửi chữ.
- Path variable không chuyển được sang kiểu ID mà endpoint mong đợi.
- JSON sai cú pháp hoặc có kiểu dữ liệu không thể deserialize vào entity.
- Request thiếu field bắt buộc theo hợp đồng.
- Giá trị enum, ngày tháng hoặc định dạng đầu vào không hợp lệ.
- Validation phát hiện field vi phạm constraint nghiệp vụ.

HTTP 400 là một status tổng quát. Chỉ nhìn status code chưa đủ để biết lỗi nằm ở query parameter, JSON parser, data binding hay validation. Cần đọc error response và log tương ứng để xác định chính xác.

## 2. Request đi qua những bước nào?

Một request ghi qua Spring Data REST thường đi qua các bước khái quát:

1. Web server và Spring MVC nhận HTTP request.
2. Handler mapping xác định repository resource và HTTP operation.
3. Framework đọc path variable, query parameter, header và Content-Type.
4. HttpMessageConverter deserialize body, ví dụ JSON thành entity.
5. Spring Data REST chạy các validator phù hợp với repository event.
6. Repository thực hiện thao tác persistence.
7. Framework serialize response representation, thường là HAL.

400 có thể được phát sinh ở nhiều bước đầu:

| Vị trí | Ví dụ | Dấu hiệu thường gặp |
|---|---|---|
| Parse parameter | ?page=abc khi page cần số | Không chuyển được kiểu dữ liệu |
| Convert path variable | ID không chuyển được sang Long | Path variable/type mismatch |
| Deserialize body | JSON thiếu dấu ngoặc hoặc age là object thay vì số | HttpMessageNotReadableException hoặc lỗi parse |
| Validate entity | name rỗng hoặc age âm | Field validation error |
| Bind request cho custom handler | Thiếu tham số bắt buộc hoặc body sai kiểu | Binding/argument resolution error |

Repository có thể chưa được gọi nếu lỗi xảy ra ở bước parse, convert hoặc deserialize. Khi validation thất bại, thao tác lưu cũng phải bị từ chối.

## 3. Lỗi query parameter và path variable

Spring Data REST nhận query parameter để phân trang, sắp xếp, tìm kiếm hoặc điều khiển finder method. Giá trị gửi lên phải tương thích với kiểu dữ liệu mà endpoint yêu cầu.

Ví dụ collection có hỗ trợ page và size:

~~~http
GET /api/people?page=abc&size=20
Accept: application/hal+json
~~~

Nếu page được chuyển sang số nguyên, giá trị abc không hợp lệ và request có thể bị trả 400.

Ví dụ finder method nhận tham số enum:

~~~java
public interface PersonRepository extends JpaRepository<Person, Long> {

    List<Person> findByStatus(@Param("status") PersonStatus status);
}
~~~

Request hợp lệ:

~~~http
GET /api/people/search/findByStatus?status=ACTIVE
Accept: application/hal+json
~~~

Nếu gửi một giá trị không ánh xạ được vào enum PersonStatus, quá trình convert tham số có thể thất bại và trả lỗi client.

Các trường hợp cần kiểm tra:

- Số nguyên, số thập phân và kiểu ID.
- Enum phải khớp một giá trị được hỗ trợ.
- Ngày giờ phải theo định dạng mà converter của ứng dụng chấp nhận.
- Boolean phải dùng giá trị được converter hỗ trợ.
- Query parameter bắt buộc của custom endpoint phải có mặt.
- Giá trị sort phải trỏ tới property hợp lệ mà API cho phép.

Không tự giả định mọi giá trị sai đều được xử lý giống nhau. Một số endpoint có thể bỏ qua parameter không biết, dùng default hoặc trả lỗi tùy resolver và cấu hình. Hãy kiểm thử đúng endpoint và kiểu dữ liệu thực tế.

## 4. Lỗi JSON và deserialize request body

Spring Data REST dùng HttpMessageConverter để chuyển body HTTP thành entity hoặc representation tương ứng. Với JSON, lỗi cú pháp hoặc kiểu dữ liệu không tương thích thường khiến request bị từ chối trước khi gọi repository.

JSON sai cú pháp:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan",
  "age": 25,
~~~

Body trên thiếu phần kết thúc object nên JSON parser không thể đọc.

JSON hợp lệ về cú pháp nhưng sai kiểu dữ liệu:

~~~json
{
  "name": "Lan",
  "age": {
    "value": 25
  }
}
~~~

Nếu age trong entity là Integer, object JSON không thể chuyển thành Integer theo cấu trúc này.

Request hợp lệ theo ví dụ:

~~~http
POST /api/people
Content-Type: application/json
Accept: application/hal+json

{
  "name": "Lan",
  "email": "lan@example.com",
  "age": 25
}
~~~

Cần phân biệt ba nhóm:

- **Malformed JSON**: body không phải JSON hợp lệ.
- **Deserialization/type mismatch**: JSON hợp lệ nhưng không khớp kiểu Java hoặc cấu trúc property.
- **Semantic validation**: body có thể deserialize thành entity nhưng giá trị vi phạm quy tắc nghiệp vụ.

Hai nhóm đầu thường phát sinh trong quá trình đọc body; nhóm cuối được xử lý bởi validation sau khi entity đã được tạo từ request.

Việc một JSON property không được khai báo trong entity có bị bỏ qua hay gây lỗi phụ thuộc Jackson configuration và cấu hình ứng dụng. Không nên mặc định unknown property luôn trả 400; hãy quyết định rõ API có từ chối field lạ hay không và kiểm thử theo cấu hình thực tế.

## 5. Content-Type và Accept là hai trường hợp khác

Không phải mọi lỗi liên quan representation đều là 400.

- **Content-Type** mô tả định dạng body client gửi.
- **Accept** mô tả định dạng response client muốn nhận.

Ví dụ client gửi XML vào endpoint chỉ nhận JSON có thể nhận **415 Unsupported Media Type**.

~~~http
POST /api/people
Content-Type: application/xml
Accept: application/hal+json
~~~

Nếu client yêu cầu một response representation server không hỗ trợ, server có thể trả **406 Not Acceptable**.

~~~http
GET /api/people
Accept: application/x-unknown-format
~~~

Khi chẩn đoán, kiểm tra cả method, Content-Type, Accept và body. Sửa JSON không giải quyết được 415 nếu Content-Type vẫn sai; đổi Accept không giải quyết được lỗi parse body.

## 6. Validation dữ liệu sau khi deserialize

Một request có JSON hợp lệ vẫn có thể chứa dữ liệu không được phép lưu. Ví dụ Person cần có name, email hợp lệ và age không âm.

Có thể khai báo constraint bằng Jakarta Bean Validation:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(0)
    private Integer age;

    // Getters and setters
}
~~~

Ứng dụng cần có Bean Validation provider phù hợp với phiên bản Spring/Jakarta đang dùng. Với Spring Boot, dependency thường là starter validation.

Spring Data REST cũng hỗ trợ Spring Validator gắn với repository event bằng quy ước tên bean. Ví dụ:

~~~java
@Component("beforeCreatePersonValidator")
public class BeforeCreatePersonValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return Person.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Person person = (Person) target;

        if (person.getAge() != null && person.getAge() < 0) {
            errors.rejectValue(
                "age",
                "person.age.negative",
                "Tuổi không được âm"
            );
        }
    }
}
~~~

Tên **beforeCreatePersonValidator** gắn validator với event trước khi tạo Person. Với quy tắc phải luôn đúng trước khi lưu thay đổi, có thể đăng ký validator cho **beforeSave** hoặc đặt logic dùng chung ở tầng service/domain phù hợp.

Phân biệt:

- Bean Validation dùng annotation như **@NotBlank**, **@Email**, **@Min**.
- Spring Validator triển khai **supports** và **validate**, ghi lỗi qua **Errors**.
- Cả hai cần được cấu hình và kiểm tra trong luồng ghi thực tế; đừng giả định chỉ khai báo annotation là mọi entry point đều đã chạy đúng validation.

## 7. Phân biệt lỗi định dạng và lỗi nghiệp vụ

Một cách phân loại hữu ích:

| Loại lỗi | Ví dụ | Nơi xử lý phù hợp |
|---|---|---|
| Syntax | JSON thiếu dấu } | HTTP message converter/parser |
| Type conversion | age: "abc" trong khi cần Integer | Data binding/conversion |
| Required field | name không được để trống | Bean Validation hoặc Spring Validator |
| Range/format | age âm, email sai định dạng | Bean Validation hoặc Spring Validator |
| Cross-field rule | startDate phải trước endDate | Class-level constraint hoặc service/domain validation |
| State-dependent rule | Không thể đổi trạng thái đơn đã giao | Service/domain rule có quyền truy cập trạng thái hiện tại |

Lỗi cú pháp và chuyển kiểu thường có thể sửa bằng cách gửi request đúng định dạng. Lỗi nghiệp vụ cần client hiểu quy tắc nào bị vi phạm để người dùng sửa dữ liệu.

Không đưa mọi exception vào một thông báo “Invalid request”. Điều đó làm client khó khắc phục và che khuất lỗi lập trình hoặc lỗi hệ thống.

## 8. Response body của lỗi 400

HTTP status cho biết loại kết quả, còn response body nên giúp client xác định và sửa input. Hình dạng body mặc định của Spring Data REST có thể khác theo phiên bản, exception handler và cấu hình Spring Boot. Có thể có message tổng quát, lỗi field hoặc thông tin validation; không nên phụ thuộc vào một JSON shape chưa được kiểm chứng.

Một hợp đồng lỗi do ứng dụng thiết kế có thể dùng cấu trúc:

~~~json
{
  "type": "https://api.example.com/problems/invalid-input",
  "title": "Dữ liệu đầu vào không hợp lệ",
  "status": 400,
  "detail": "Có 2 trường cần được sửa.",
  "instance": "/api/people",
  "code": "VALIDATION_FAILED",
  "violations": [
    {
      "field": "name",
      "code": "NOT_BLANK",
      "message": "Tên không được để trống"
    },
    {
      "field": "email",
      "code": "EMAIL_INVALID",
      "message": "Email không đúng định dạng"
    }
  ]
}
~~~

Các trường có ích:

- **status**: HTTP status.
- **code**: mã lỗi ổn định cho client logic.
- **detail**: giải thích ngắn gọn ở cấp request.
- **instance**: path request gây lỗi.
- **violations**: danh sách lỗi theo field, kèm mã lỗi.
- **traceId**: mã tương quan để tìm log nếu hệ thống hỗ trợ.

Thông báo dành cho người dùng nên rõ ràng nhưng không tiết lộ stack trace, SQL, tên bảng nội bộ, token, mật khẩu hoặc dữ liệu nhạy cảm. Tránh trả lại nguyên văn input có thể chứa bí mật.

Nếu dùng Spring Framework 6 trở lên, có thể cân nhắc **ProblemDetail** theo RFC 9457 cho custom MVC exception handler. Hãy xác nhận phiên bản và cách Spring Data REST xử lý exception trước khi áp dụng chung một handler cho mọi endpoint. Không thay đổi error contract mặc định nếu client hiện tại đang phụ thuộc vào nó mà chưa có kế hoạch tương thích.

## 9. Xử lý lỗi trong custom controller

Với custom endpoint do ứng dụng tự viết, có thể dùng **@ExceptionHandler** hoặc **@ControllerAdvice** để ánh xạ exception đầu vào sang response có cấu trúc.

Ví dụ với Spring Framework hỗ trợ ProblemDetail:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.http.converter.HttpMessageNotReadableException;

@RestControllerAdvice(assignableTypes = PersonCommandController.class)
public class PersonCommandErrorHandler {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ProblemDetail invalidJson(
            HttpMessageNotReadableException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "Body JSON không hợp lệ hoặc không đúng kiểu dữ liệu."
        );

        problem.setTitle("Dữ liệu đầu vào không hợp lệ");
        problem.setProperty("code", "INVALID_JSON");
        return problem;
    }
}
~~~

Ví dụ giới hạn advice vào controller được chỉ định để tránh vô tình thay đổi cách xử lý lỗi của toàn bộ Spring Data REST exporter. Trong ứng dụng thật, có thể bổ sung handler cho validation exception hoặc lỗi nghiệp vụ riêng.

Với repository resource do Spring Data REST quản lý, ưu tiên cơ chế validation event và exception handling tương thích với phiên bản Spring Data REST. Không giả định **@RestControllerAdvice** giới hạn cho custom controller sẽ tự động thay thế handler nội bộ của exporter.

Nếu cần response contract thống nhất cho toàn API, hãy thiết kế một exception mapping có phạm vi rõ ràng, kiểm tra thứ tự handler và viết integration test cho cả repository resource lẫn custom controller.

## 10. Phân biệt 400 với các status thường gặp

| Status | Ý nghĩa | Ví dụ |
|---|---|---|
| **400 Bad Request** | Request hoặc dữ liệu đầu vào không hợp lệ | JSON sai cú pháp, parameter không convert được, validation thất bại |
| **404 Not Found** | Resource hoặc endpoint không tồn tại | ID không có trong repository |
| **405 Method Not Allowed** | Endpoint tồn tại nhưng không hỗ trợ HTTP method đó | Gửi DELETE tới endpoint chỉ cho GET |
| **406 Not Acceptable** | Không có response representation phù hợp với Accept | Client yêu cầu media type không hỗ trợ |
| **409 Conflict** | Request xung đột với trạng thái hiện tại của resource | Một số xung đột nghiệp vụ hoặc persistence |
| **412 Precondition Failed** | Điều kiện HTTP như If-Match không thỏa | ETag đã cũ khi cập nhật có điều kiện |
| **415 Unsupported Media Type** | Server không hỗ trợ định dạng body gửi lên | Content-Type không được hỗ trợ |
| **500 Internal Server Error** | Lỗi ngoài dự kiến phía server | Bug hoặc lỗi hạ tầng chưa được ánh xạ |

Một số framework hoặc ứng dụng có thể ánh xạ một loại exception cụ thể sang status khác. Ví dụ optimistic locking có thể được chuyển thành 409 hoặc 412 tùy hợp đồng API và cơ chế precondition. Hãy xác định status mà phiên bản ứng dụng thực sự trả về.

Không trả 400 cho mọi lỗi chỉ vì request đến từ client. ID không tồn tại thường là 404; media type không hỗ trợ là 415; lỗi ngoài dự kiến phía server không nên bị che thành 400.

## 11. Kiểm tra bằng curl

### JSON sai cú pháp

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","age":25' \
  http://localhost:8080/api/people
~~~

Mục tiêu là xác nhận parser từ chối body và response có status client error phù hợp, thường là 400.

### JSON đúng cú pháp nhưng sai kiểu

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","age":{"value":25}}' \
  http://localhost:8080/api/people
~~~

Nếu entity cần age là Integer, object JSON này không phù hợp kiểu dữ liệu.

### Query parameter không convert được

~~~bash
curl -i \
  -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people?page=abc&size=20"
~~~

Xác nhận lỗi xảy ra ở parameter conversion và không bị nhầm với lỗi repository query.

### Validation thất bại

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"invalid","age":-1}' \
  http://localhost:8080/api/people
~~~

Kiểm tra response chỉ ra field nào vi phạm và xác nhận entity không được lưu.

### Request hợp lệ

~~~bash
curl -i -X POST \
  -H "Accept: application/hal+json" \
  -H "Content-Type: application/json" \
  -d '{"name":"Lan","email":"lan@example.com","age":25}' \
  http://localhost:8080/api/people
~~~

Request hợp lệ phải đi qua validation và tạo resource theo hợp đồng API. Dùng self link hoặc Location từ response để xác định item vừa tạo.

## 12. Kiểm tra bằng integration test

Nên kiểm tra cả status code lẫn tác động persistence. Ví dụ với MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonRestApiTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    PersonRepository repository;

    @Test
    void rejectsMalformedJson() throws Exception {
        long before = repository.count();

        mockMvc.perform(post("/api/people")
                .contentType(MediaType.APPLICATION_JSON)
                .accept("application/hal+json")
                .content("{\"name\":\"Lan\",\"age\":"))
            .andExpect(status().isBadRequest());

        assertThat(repository.count()).isEqualTo(before);
    }
}
~~~

Ví dụ minh họa cho test body JSON sai cú pháp. Cần import MockMvc, request builder, MediaType, status matcher và assertion library theo test stack của dự án.

Với validation, kiểm tra thêm:

- Status là 400 theo hợp đồng ứng dụng.
- Field error có tên và mã lỗi ổn định.
- Không có entity mới được lưu.
- Request hợp lệ vẫn tạo được resource.
- Các exception không liên quan không bị chuyển nhầm thành 400.

Nếu dùng database test có transaction rollback sau mỗi test, hãy lưu ý assertion repository count trong test và transaction boundary của request. Với test HTTP end-to-end, có thể dùng database test riêng hoặc kiểm tra persistence qua transaction khác để tránh đọc nhầm persistence context.

## 13. Log và chẩn đoán lỗi

Khi request trả 400, hãy tìm nguyên nhân theo thứ tự:

1. Ghi lại method, path, query string và Content-Type.
2. Xác nhận body có JSON hợp lệ hay không.
3. Kiểm tra field Java và kiểu JSON tương ứng.
4. Xem exception gốc trong server log, ví dụ lỗi deserialize hoặc conversion.
5. Nếu body deserialize thành công, kiểm tra Bean Validation và Spring Validator.
6. Xác nhận request có tới repository event hay chưa.
7. Kiểm tra entity có được lưu hoặc thay đổi hay không.

Có thể log exception class và mã lỗi nội bộ mà không ghi toàn bộ body. Nếu body chứa PII hoặc credential, không bật request-body logging ở production một cách thiếu kiểm soát.

Một trace ID hoặc correlation ID giúp nối response lỗi với server log. Trả mã đó cho client để đội hỗ trợ có thể tìm sự kiện tương ứng mà không cần tiết lộ stack trace.

## 14. Nguyên tắc thiết kế error contract

- Dùng status code đúng với bản chất lỗi.
- Giữ mã lỗi máy đọc được ổn định, ví dụ **INVALID_JSON**, **INVALID_PARAMETER**, **VALIDATION_FAILED**.
- Với validation, trả danh sách field violation thay vì chỉ một câu chung chung.
- Thông báo cho người dùng nên ngắn, có thể hành động và không tiết lộ chi tiết nội bộ.
- Không trả stack trace, SQL, class name nội bộ hoặc secret.
- Không echo toàn bộ request body nếu body có dữ liệu cá nhân.
- Giữ error response tương thích giữa các phiên bản API hoặc version contract rõ ràng.
- Ghi log phía server với trace ID để điều tra.
- Kiểm tra rằng request thất bại không tạo ra thay đổi persistence ngoài ý muốn.

## 15. Lỗi thường gặp

### Mọi lỗi đều bị trả 400

Một exception handler quá rộng có thể che lỗi 404, 409 hoặc 500 thành 400. Chỉ ánh xạ các exception thực sự thể hiện input không hợp lệ.

### JSON parse lỗi bị nhầm với validation

Nếu JSON chưa deserialize được, validator chưa có entity hợp lệ để kiểm tra. Hãy tìm lỗi message converter trước khi xem validation.

### Dùng sai Content-Type

Body JSON nhưng thiếu hoặc khai báo Content-Type không phù hợp có thể gây lỗi media type. Phân biệt 415 với 400 do nội dung JSON sai.

### Chỉ kiểm tra status code

Hai request đều trả 400 nhưng một request sai page parameter, request còn lại vi phạm email. Response body và log phải giúp xác định đúng nguyên nhân.

### Unknown JSON property luôn được coi là hợp lệ

Hành vi field lạ phụ thuộc Jackson configuration. Quyết định rõ có từ chối field không biết hay không và viết test cho hợp đồng đó.

### Validation thất bại nhưng dữ liệu vẫn được lưu

Kiểm tra validator có được đăng ký đúng event/domain type không, exception có bị bắt rồi bỏ qua không và transaction có rollback đúng không.

### Trả chi tiết exception cho client

Stack trace hoặc message từ database có thể lộ cấu trúc nội bộ và dữ liệu nhạy cảm. Dùng thông báo an toàn cho client và giữ chi tiết ở log có kiểm soát.

### Dùng 400 cho resource không tồn tại

ID không tìm thấy thường là 404. Đừng biến mọi tình huống “không thể hoàn tất” thành Bad Request.

## 16. Ghi nhớ

- **400 Bad Request** dùng khi request hoặc input không hợp lệ.
- Lỗi có thể xảy ra khi parse parameter, convert path variable, deserialize JSON hoặc validate entity.
- JSON sai cú pháp khác với JSON đúng cú pháp nhưng sai kiểu; cả hai khác với validation nghiệp vụ.
- Dùng Bean Validation hoặc Spring Validator để kiểm tra field và quy tắc nghiệp vụ.
- Response lỗi nên có mã lỗi ổn định, thông báo rõ và danh sách field violation khi phù hợp.
- Phân biệt 400 với 404, 405, 406, 409, 412, 415 và 500.
- Kiểm tra status, response body, exception gốc, repository event và tác động persistence.
- Không log hoặc trả dữ liệu nhạy cảm, stack trace hay SQL cho client.
- Viết integration test cho malformed JSON, parameter sai, validation fail và request hợp lệ.

## Tài liệu tham khảo

- [Spring Data REST Reference — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST Reference — Handling Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [RFC 9110 — HTTP Semantics: 400 Bad Request](https://www.rfc-editor.org/rfc/rfc9110.html#name-400-bad-request)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
