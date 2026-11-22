# Định dạng lỗi validation và kiểm thử dữ liệu không hợp lệ

Spring Data REST có thể công khai các repository thành REST resource mà không cần viết controller cho từng thao tác CRUD. Tuy vậy, API vẫn phải xác định rõ dữ liệu nào hợp lệ, lỗi được trả về theo cấu trúc nào và client có thể dựa vào mã lỗi nào để xử lý. Một endpoint chỉ trả về HTTP 400 khi dữ liệu sai là chưa đủ nếu response không cho biết field nào sai, quy tắc nào bị vi phạm và cách sửa dữ liệu.

Bài này tập trung vào hai phần: xây dựng hợp đồng lỗi validation ổn định cho API Spring Data REST và kiểm thử các request chứa dữ liệu không hợp lệ ở mức tích hợp.

## 1. Validation diễn ra ở những lớp nào?

Không nên gom mọi lỗi đầu vào vào một nhóm. Một request có thể thất bại ở nhiều giai đoạn khác nhau:

| Lớp kiểm tra | Ví dụ dữ liệu sai | Kết quả cần thể hiện |
|---|---|---|
| Cú pháp và chuyển đổi JSON | JSON thiếu dấu ngoặc, gửi chuỗi vào field số | Request không đọc được |
| Validation field | Tên rỗng, email sai định dạng, số lượng âm | Field và constraint vi phạm |
| Quy tắc giữa nhiều field | Ngày kết thúc trước ngày bắt đầu | Quy tắc nghiệp vụ liên quan |
| Trạng thái nghiệp vụ | Đơn hàng đã đóng nhưng client yêu cầu sửa | Conflict hoặc lỗi nghiệp vụ |
| Ràng buộc persistence | Email phải duy nhất nhưng đã tồn tại | Vi phạm dữ liệu, kể cả khi có request đồng thời |
| Xác thực và phân quyền | Người dùng không được sửa resource | Lỗi authentication/authorization |

Mỗi lớp có thời điểm phát hiện và cách xử lý khác nhau. JSON sai cú pháp sẽ bị từ chối trước khi entity được chuyển thành đối tượng Java. Lỗi @NotBlank chỉ có thể được phát hiện sau khi dữ liệu đã được deserialize. Unique constraint của database có thể chỉ thất bại lúc transaction ghi dữ liệu.

Nên đặt validation ở lớp gần với invariant cần bảo vệ nhất:

- Quy tắc về hình dạng dữ liệu thuộc Bean Validation hoặc request model.
- Quy tắc phụ thuộc nhiều field thuộc validator/domain service.
- Quy tắc duy nhất và toàn vẹn dữ liệu cần được bảo vệ bằng constraint ở database.
- Quy tắc phụ thuộc trạng thái hiện tại thuộc nghiệp vụ và cần xử lý cạnh tranh cập nhật.

Validation phía client chỉ giúp người dùng nhận phản hồi sớm. Server vẫn phải kiểm tra lại vì client có thể bị bỏ qua, dữ liệu có thể đến từ integration khác và nhiều request có thể chạy đồng thời.

## 2. Khai báo constraint cho entity

Với Spring Boot 3, Bean Validation sử dụng namespace jakarta.validation. Nếu ứng dụng chưa có implementation validation, thêm dependency phù hợp, thường là:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-validation")
~~~

Ví dụ entity Customer:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

@Entity
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank(message = "Tên khách hàng không được để trống")
    @Size(max = 120, message = "Tên khách hàng tối đa 120 ký tự")
    private String name;

    @NotBlank(message = "Email không được để trống")
    @Email(message = "Email không đúng định dạng")
    private String email;

    @PositiveOrZero(message = "Hạn mức phải lớn hơn hoặc bằng 0")
    private BigDecimal creditLimit;

    // getters and setters
}
~~~

Một số điểm cần chú ý:

- @NotNull chỉ cấm giá trị null; nó không cấm chuỗi rỗng.
- @NotEmpty cấm null và giá trị rỗng nhưng chuỗi chỉ có dấu cách vẫn có thể vượt qua.
- @NotBlank phù hợp với chuỗi bắt buộc có nội dung sau khi xét whitespace.
- @Email kiểm tra định dạng email ở mức validator; nó không chứng minh địa chỉ thực sự tồn tại hoặc thuộc về người dùng.
- @Positive và @PositiveOrZero phù hợp với số cần có giới hạn dấu.
- @Size kiểm soát độ dài chuỗi hoặc kích thước collection; cần chọn giới hạn theo hợp đồng API và database.

Với object lồng nhau, dùng cascade validation để constraint ở object con cũng được thực thi:

~~~java
public class Address {

    @NotBlank
    private String city;

    @NotBlank
    private String street;
}

public class Customer {

    @Valid
    @NotNull
    private Address address;
}
~~~

Nếu một field có thể vắng mặt hợp lệ, không nên áp dụng constraint bắt buộc một cách máy móc. Cần phân biệt field bị bỏ qua, field có giá trị null, chuỗi rỗng và giá trị mặc định do deserialize tạo ra. Điều này đặc biệt quan trọng với PATCH vì client thường chỉ gửi các field muốn thay đổi.

## 3. Kết nối validation với lifecycle của Spring Data REST

Spring Data REST có các repository event trước và sau khi tạo, lưu, liên kết và xóa entity. Hai thời điểm thường dùng để kiểm tra dữ liệu ghi là:

- beforeCreate: trước khi tạo entity mới.
- beforeSave: trước khi lưu thay đổi của entity hiện có.

Các constraint Bean Validation cần được tích hợp vào luồng validation của ứng dụng. Với quy tắc riêng, có thể triển khai org.springframework.validation.Validator và đăng ký validator cho event tương ứng.

Ví dụ kiểm tra khoảng ngày:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

@Component("beforeCreateBookingValidator")
public class BeforeCreateBookingValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return Booking.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        Booking booking = (Booking) target;

        if (booking.getStartDate() != null
                && booking.getEndDate() != null
                && booking.getEndDate().isBefore(booking.getStartDate())) {
            errors.rejectValue(
                "endDate",
                "booking.dateRange.invalid",
                "Ngày kết thúc phải bằng hoặc sau ngày bắt đầu"
            );
        }
    }
}
~~~

Spring Data REST hỗ trợ cơ chế validator gắn với repository event. Một cách đăng ký phổ biến là dùng tên bean theo quy ước beforeCreate<DomainType>Validator hoặc beforeSave<DomainType>Validator. Cần bảo đảm tên domain type khớp với entity mà repository quản lý và kiểm tra cách cấu hình validator của phiên bản đang dùng. Nếu muốn kiểm soát tường minh, có thể cấu hình ValidatingRepositoryEventListener và đăng ký validator theo tên event.

Nếu entity có thể được tạo và cập nhật qua nhiều luồng, hãy áp dụng cùng invariant cho cả hai event cần thiết. Validator chỉ chạy ở beforeCreate sẽ không tự bảo vệ một entity khi nó được cập nhật sau đó.

Không đặt các side effect như gửi email hoặc gọi payment gateway trong validator. Validator nên kiểm tra và báo lỗi. Việc ghi dữ liệu hoặc phát sinh tác vụ chỉ nên xảy ra sau khi validation và transaction nghiệp vụ đã thành công.

## 4. Thiết kế cấu trúc lỗi cho client

Một error response hữu ích cần giúp client trả lời được:

1. Request thất bại ở đâu?
2. Field hoặc resource nào có vấn đề?
3. Quy tắc nào bị vi phạm?
4. Client có thể sửa dữ liệu và gửi lại hay cần xử lý conflict?
5. Có mã tham chiếu nào để tra log khi cần hỗ trợ?

Ví dụ một hợp đồng lỗi validation do ứng dụng chủ động chuẩn hóa theo Problem Details:

~~~json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Dữ liệu không hợp lệ",
  "status": 400,
  "detail": "Một hoặc nhiều trường không đáp ứng quy tắc kiểm tra.",
  "instance": "/customers",
  "errors": [
    {
      "field": "name",
      "code": "NotBlank",
      "message": "Tên khách hàng không được để trống"
    },
    {
      "field": "email",
      "code": "Email",
      "message": "Email không đúng định dạng"
    },
    {
      "field": "creditLimit",
      "code": "PositiveOrZero",
      "message": "Hạn mức phải lớn hơn hoặc bằng 0"
    }
  ],
  "traceId": "01JEXAMPLE9M4Y2"
}
~~~

Các thành phần có ý nghĩa:

| Thành phần | Mục đích |
|---|---|
| type | URI định danh loại lỗi |
| title | Tên ngắn gọn của lỗi |
| status | HTTP status code |
| detail | Giải thích tổng quát cho request hiện tại |
| instance | URI của request hoặc resource gặp lỗi |
| errors | Danh sách lỗi chi tiết theo field |
| field | Tên field theo hợp đồng API |
| code | Mã lỗi ổn định để client xử lý |
| message | Nội dung có thể hiển thị cho người dùng |
| traceId | Mã tra cứu log, nếu hệ thống có tracing |

Đây là cấu trúc minh họa cho một API tự chuẩn hóa lỗi; không nên giả định Spring Data REST tự động trả về đúng JSON này. Spring Data REST có thể sử dụng kiểu lỗi VndErrors cho một số trường hợp. Media type, status và nội dung thực tế phụ thuộc phiên bản, exception handler, cấu hình và content negotiation của ứng dụng.

Trước khi viết client, hãy gửi request thực tế với các header Accept mà client sử dụng và kiểm tra response đang được trả về. Nếu muốn API dùng Problem Details hoặc một schema riêng, cần triển khai cơ chế exception handling phù hợp, sau đó kiểm thử hợp đồng đó ở mức HTTP.

### 4.1. Chọn HTTP status nhất quán

Một quy ước có thể áp dụng:

| HTTP status | Trường hợp |
|---|---|
| 400 Bad Request | JSON sai cú pháp, không deserialize được hoặc field validation thất bại |
| 401 Unauthorized | Thiếu hoặc không hợp lệ thông tin xác thực |
| 403 Forbidden | Đã xác thực nhưng không có quyền |
| 404 Not Found | Resource đích không tồn tại |
| 409 Conflict | Trạng thái hiện tại hoặc unique constraint gây conflict với thao tác |
| 412 Precondition Failed | Điều kiện If-Match hoặc precondition không còn đúng |
| 415 Unsupported Media Type | Content-Type không được endpoint hỗ trợ |
| 422 Unprocessable Content | API chọn quy ước riêng cho nội dung hợp lệ về cú pháp nhưng không thể xử lý về mặt ngữ nghĩa |
| 500 Internal Server Error | Lỗi ngoài dự kiến ở phía server |

Không cần dùng tất cả status trong mọi API. Điều quan trọng là cùng một loại lỗi phải có cách biểu diễn nhất quán. Ví dụ, nếu validation field luôn trả 400 thì client không nên phải xử lý cùng loại lỗi lúc 400, lúc 409 và lúc 500.

Unique constraint có thể được phát hiện sau khi validation ban đầu đã thành công. Trường hợp này thường nên trả conflict theo hợp đồng API, nhưng cần phân biệt với lỗi database không mong đợi. Không biến mọi DataIntegrityViolationException thành 409 một cách mù quáng vì lỗi có thể xuất phát từ nhiều nguyên nhân khác nhau.

### 4.2. Mã lỗi ổn định và thông báo

Client nên dựa vào code để quyết định cách hiển thị hoặc xử lý. Nội dung message có thể được dịch, chỉnh sửa hoặc thay đổi theo ngôn ngữ.

Ví dụ:

- NotBlank: yêu cầu nhập nội dung.
- Email: định dạng email không hợp lệ.
- Size: vượt giới hạn độ dài.
- PositiveOrZero: giá trị phải không âm.
- customer.email.duplicate: email đã được sử dụng.
- booking.dateRange.invalid: khoảng ngày không hợp lệ.

Không dùng câu thông báo tự do làm mã định danh. Cũng không nên trả stack trace, SQL, tên bảng, tên class nội bộ, token, dữ liệu cá nhân hoặc toàn bộ rejected value nếu field có thể chứa thông tin nhạy cảm.

Nếu cần trả rejected value để hỗ trợ người dùng sửa form, hãy lọc theo allowlist. Không phản hồi lại mật khẩu, access token, số thẻ, dữ liệu định danh hoặc payload nhạy cảm.

## 5. Xử lý các loại lỗi khác nhau

### 5.1. JSON sai cú pháp hoặc sai kiểu dữ liệu

Ví dụ client gửi một chuỗi không phải số cho field quantity:

~~~json
{
  "quantity": "many"
}
~~~

Đây là lỗi deserialize, không phải lỗi @Positive hay @NotNull. Validator có thể chưa được gọi vì server chưa tạo được object hợp lệ.

API nên trả lỗi request không đọc được với status phù hợp, thường là 400, và thông báo chỉ ra vị trí hoặc field nếu có thể. Không nên trả stack trace của Jackson cho client.

### 5.2. Field validation thất bại

Ví dụ request có email không hợp lệ hoặc số lượng âm. Đây là lỗi có thể ánh xạ thành danh sách field errors.

Nếu client gửi nhiều field sai, nên trả tất cả lỗi có thể xác định an toàn trong một response thay vì buộc người dùng sửa từng lỗi một lần.

### 5.3. Quy tắc giữa nhiều field

Ví dụ startDate và endDate đều có định dạng hợp lệ nhưng thứ tự ngày không hợp lệ. Đây là lỗi ở mức object hoặc domain rule. Có thể biểu diễn bằng field liên quan (endDate) hoặc mã lỗi object-level như booking.dateRange.invalid.

Không nên gán lỗi tùy tiện cho field đầu tiên chỉ để response có field. Nếu quy tắc áp dụng cho cả object, có thể dùng object hoặc path để thể hiện phạm vi.

### 5.4. Unique constraint và lỗi đồng thời

Một cách kiểm tra “email chưa tồn tại” ở tầng service có thể giúp trả lỗi sớm, nhưng hai request đồng thời vẫn có thể cùng đọc thấy email chưa tồn tại rồi cùng ghi.

Vì vậy, unique constraint ở database vẫn cần thiết. Khi constraint bị vi phạm, chuyển lỗi persistence đã nhận diện được sang mã nghiệp vụ ổn định, ví dụ customer.email.duplicate. Không trả trực tiếp tên constraint hoặc câu SQL cho client.

### 5.5. Lỗi trạng thái nghiệp vụ

Ví dụ đơn hàng đã hoàn tất nên không thể chuyển về trạng thái mới. Đây không phải lỗi định dạng field. Hãy trả lỗi conflict hoặc lỗi domain tương ứng với hợp đồng API và cung cấp mã để client biết cần tải lại trạng thái hoặc yêu cầu người dùng thực hiện thao tác khác.

## 6. Kiểm thử dữ liệu không hợp lệ ở mức nào?

Một bộ test tốt cần kiểm tra từ validator riêng đến HTTP contract của Spring Data REST.

| Mức test | Nội dung cần xác nhận |
|---|---|
| Unit test validator | Constraint, field path và mã lỗi đúng |
| Test domain rule | Quy tắc nhiều field và trạng thái nghiệp vụ |
| Repository/database test | Unique, foreign key, check constraint và transaction |
| Integration test Spring Data REST | HTTP status, media type, error body và repository event |
| Test end-to-end | Client thực tế nhận lỗi và hiển thị đúng |

Unit test không thể thay thế integration test. Một validator có thể chạy đúng khi gọi trực tiếp nhưng chưa được đăng ký với Spring Data REST event. Ngược lại, test HTTP chỉ kiểm tra status mà không xác minh database có bị ghi dở hay không cũng chưa đủ.

### 6.1. Kiểm thử POST với dữ liệu sai

Ví dụ với MockMvc trong ứng dụng Spring Boot:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class CustomerValidationIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void rejectsInvalidCustomerWithoutPersisting() throws Exception {
        long countBefore = customerRepository.count();

        mockMvc.perform(post("/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": " ",
                      "email": "not-an-email",
                      "creditLimit": -1
                    }
                    """))
            .andExpect(status().isBadRequest());

        assertThat(customerRepository.count()).isEqualTo(countBefore);
    }
}
~~~

Test trên minh họa kiểm tra HTTP status và bảo đảm request sai không tạo thêm entity. Nếu API đã chuẩn hóa error schema, bổ sung assertion cho type, errors[*].field và errors[*].code. Nếu API đang dùng VndErrors mặc định, hãy viết assertion theo đúng response thực tế thay vì sao chép path JSON của một schema khác.

Lưu ý: ví dụ dùng application/json cho Accept để minh họa. Với client dùng HAL, hãy chạy thêm test với media type mà client thực tế gửi và xác nhận error response vẫn được thương lượng đúng.

### 6.2. Kiểm thử PUT và PATCH

Với PUT, ngoài status và error body, hãy đọc lại entity sau request để xác nhận dữ liệu cũ vẫn được giữ nếu validation thất bại.

Với PATCH, kiểm tra cả hai tình huống:

- Patch gửi field không hợp lệ.
- Patch chỉ gửi một field nhưng làm vi phạm quy tắc giữa các field sau khi ghép với trạng thái hiện tại.

Ví dụ một booking có startDate là ngày 10 và endDate là ngày 20. PATCH chỉ đổi startDate thành ngày 25 phải bị từ chối nếu invariant yêu cầu endDate không được trước startDate.

Không chỉ validate các field xuất hiện trong patch document. Cần kiểm tra trạng thái entity sau khi áp dụng patch theo đúng semantics của endpoint.

### 6.3. Kiểm thử database constraint

Với unique constraint, test nên tạo hai request có cùng giá trị duy nhất. Test tuần tự giúp kiểm tra mapping lỗi; test đồng thời giúp phát hiện race condition.

Ví dụ:

1. Tạo Customer với email a@example.com.
2. Gửi request tạo Customer thứ hai cùng email.
3. Xác nhận request thứ hai nhận status và error code theo hợp đồng.
4. Xác nhận database chỉ có một Customer với email đó.

Nếu nghiệp vụ cần bảo đảm trong trường hợp đồng thời, chạy hai request song song và xác nhận unique constraint thực sự ngăn dữ liệu trùng.

## 7. Ma trận dữ liệu không hợp lệ cần kiểm tra

Không nên chỉ thử một chuỗi rỗng. Hãy xác định các boundary và biến thể dữ liệu theo từng field.

| Nhóm dữ liệu | Giá trị nên thử |
|---|---|
| Field bắt buộc | Bỏ field, null, "", chuỗi chỉ có whitespace |
| Độ dài | Ngắn hơn giới hạn, đúng giới hạn, vượt một ký tự |
| Email/URL | Hợp lệ, sai cú pháp, khoảng trắng, chuỗi rất dài |
| Số | Âm, 0, số dương, số quá lớn, số thập phân khi chỉ nhận integer |
| Ngày giờ | Sai format, ngày không tồn tại, timezone, start/end đảo thứ tự |
| Enum | Giá trị hợp lệ, sai chữ hoa/thường, giá trị không tồn tại |
| Quan hệ | ID không tồn tại, quan hệ không được phép, nested object thiếu field |
| JSON | Sai cú pháp, sai kiểu, field không biết, body rỗng |
| Unicode | Ký tự tiếng Việt, emoji, ký tự kết hợp, whitespace đặc biệt |
| Trạng thái | Resource đã đóng, đã xóa hoặc đã được cập nhật bởi client khác |

Ngoài nội dung lỗi, mỗi test nên xác nhận:

- HTTP status và Content-Type đúng hợp đồng.
- Error code ổn định, field path chính xác.
- Response không tiết lộ stack trace hoặc dữ liệu nhạy cảm.
- Không tạo entity, không cập nhật dở entity và không phát side effect ngoài ý muốn.
- Request hợp lệ vẫn hoạt động bình thường.
- Kết quả không phụ thuộc thứ tự field trong JSON.
- Các lỗi validation có thể được trả đồng thời khi điều đó an toàn và hữu ích.

## 8. Những lỗi thường gặp khi triển khai

**Có annotation nhưng API vẫn lưu dữ liệu sai:** kiểm tra dependency validation, cấu hình validator và việc Spring Data REST đã gọi validation ở beforeCreate/beforeSave hay chưa.

**POST bị từ chối đúng nhưng PUT vẫn lưu sai:** có thể validator chỉ được gắn với beforeCreate. Kiểm tra cả event cập nhật.

**Test validator pass nhưng test HTTP fail:** validator chưa được đăng ký với repository event hoặc endpoint thực tế đang dùng một luồng ghi khác.

**Response chỉ có thông báo chung:** chuẩn hóa field errors, error code và object-level errors; đừng buộc client phân tích câu văn để xác định nguyên nhân.

**Lỗi database bị trả thành 500:** nhận diện constraint và chuyển thành lỗi nghiệp vụ có chủ đích. Chỉ xử lý các constraint đã biết; lỗi persistence không xác định vẫn cần được ghi nhận là lỗi server.

**PATCH bỏ qua quy tắc giữa field:** validate trạng thái cuối cùng sau khi áp dụng patch, không chỉ validate fragment JSON.

**Dữ liệu đã ghi dù response báo lỗi:** kiểm tra transaction boundary, event listener và side effect. Test phải đọc lại repository sau request thất bại.

**Test chỉ kiểm tra status code:** bổ sung kiểm tra error schema, dữ liệu không thay đổi và side effect không phát sinh.

## 9. Checklist trước khi công bố API

1. Mọi field bắt buộc và giới hạn dữ liệu đều có rule phía server.
2. Rule giữa nhiều field có validator hoặc domain logic rõ ràng.
3. Validator được đăng ký cho cả create và update khi cần.
4. Database bảo vệ các invariant cần đúng trong trường hợp request đồng thời.
5. API có quy ước status code cho validation, conflict, authentication và lỗi hệ thống.
6. Error body có mã lỗi ổn định, field path và message phù hợp.
7. Client không phải phân tích câu thông báo để xác định lỗi.
8. Không trả stack trace, SQL hoặc rejected value nhạy cảm.
9. POST, PUT và PATCH đều có test dữ liệu không hợp lệ.
10. Test xác nhận dữ liệu không bị ghi một phần khi validation thất bại.
11. Có test cho nested object, boundary, null, missing field và dữ liệu Unicode.
12. Có test cho unique constraint và request đồng thời khi invariant yêu cầu.
13. Media type và error response đã được kiểm tra với header Accept thực tế.
14. Request hợp lệ vẫn được lưu và trả response đúng hợp đồng.

## Kết luận

Validation trong Spring Data REST cần được nối đúng vào lifecycle của repository và có một hợp đồng lỗi rõ ràng cho client. Bean Validation phù hợp với constraint của từng field; repository event validator và domain logic xử lý quy tắc nghiệp vụ; database constraint bảo vệ invariant trước cạnh tranh đồng thời.

Kiểm thử không nên dừng ở việc xác nhận HTTP 400. Hãy xác nhận error body có thể sử dụng được, dữ liệu không bị ghi dở, side effect không phát sinh và các request hợp lệ vẫn hoạt động. Khi các lớp kiểm tra này được kiểm chứng cùng nhau, API mới có thể từ chối dữ liệu không hợp lệ một cách dự đoán được và an toàn cho client tích hợp.