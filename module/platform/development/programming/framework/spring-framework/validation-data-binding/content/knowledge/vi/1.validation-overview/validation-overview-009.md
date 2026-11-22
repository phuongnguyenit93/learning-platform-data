# Phân biệt kiểm tra đầu vào, quy tắc nghiệp vụ và ràng buộc lưu trữ

> Bài Knowledge thuộc **Spring Framework – validation/data binding**. Ví dụ sử dụng Java 17+, Spring Framework 6/Spring Boot 3 và Jakarta Bean Validation. Trọng tâm là nhận diện đúng trách nhiệm của từng tầng, cách phối hợp chúng trong một use case và giới hạn của mỗi cơ chế.

## 1. Vì sao phải tách ba loại kiểm tra?

Giả sử API nhận yêu cầu đăng ký tài khoản có `email` và `password`. Ba câu hỏi sau rất khác nhau:

1. **Kiểm tra đầu vào (input validation):** email có bị bỏ trống hoặc sai định dạng không? Mật khẩu có đủ độ dài theo hợp đồng request không?
2. **Quy tắc nghiệp vụ (business rule):** hệ thống có đang mở đăng ký không? Người dùng có đủ điều kiện đăng ký không? Một email đã sử dụng được phép đăng ký lại trong trường hợp tài khoản bị khóa/xóa mềm hay không?
3. **Ràng buộc lưu trữ (storage constraint):** DB có chấp nhận hai hàng cùng `normalized_email` không? Có thể ghi `NULL` vào cột bắt buộc không? Quan hệ khóa ngoại còn hợp lệ không?

Một request vượt qua `@Valid` vẫn có thể bị từ chối tại service. Một use case đã kiểm tra trạng thái trong service vẫn có thể thất bại khi lưu vì transaction khác vừa thay đổi dữ liệu.

**Nguyên tắc:** mỗi tầng kiểm tra điều nó biết và điều nó có khả năng bảo đảm. Có những bất biến cần bảo vệ ở hai hoặc ba tầng với mục đích khác nhau; đó là sự phối hợp có chủ đích, miễn là chúng dùng cùng một định nghĩa.

## 2. Bảng phân biệt

| Tiêu chí | Kiểm tra đầu vào | Quy tắc nghiệp vụ | Ràng buộc lưu trữ |
| --- | --- | --- | --- |
| Câu hỏi | Dữ liệu nhận được có đúng cấu trúc, kiểu, phạm vi, định dạng? | Hành động hoặc trạng thái có được cho phép theo chính sách sản phẩm? | Dữ liệu đã ghi có luôn đáp ứng bất biến lưu trữ? |
| Dữ liệu cần | Request DTO, JSON, kiểu, các trường liên quan trong request | Đối tượng domain, trạng thái hiện tại, quyền, thời điểm, chính sách | Hàng/cột, khóa, quan hệ, dữ liệu trong transaction |
| Thường triển khai tại | Converter/data binder, DTO, Jakarta Bean Validation, Spring MVC | Application service, domain model, domain service | Schema/migration, constraint, index, transaction/locking |
| Ví dụ | Email không trống, tối đa 254 ký tự | Chỉ đăng ký khi chiến dịch đang mở | `UNIQUE(normalized_email)` |
| Phản hồi | Lỗi theo trường hoặc dữ liệu không đọc được | Lỗi nghiệp vụ rõ nghĩa | Lỗi constraint được ứng dụng nhận diện/dịch phù hợp |
| Điều không bảo đảm | Không biết trạng thái đã bị transaction khác thay đổi | Kiểm tra trước khi ghi có thể gặp race condition | Không biểu diễn hết quyền, workflow, quy tắc dịch vụ ngoài |

Không thể phân loại chỉ dựa vào cách viết annotation. Ví dụ “số lượng phải lớn hơn 0” có thể xuất hiện dưới dạng `@Positive` trên DTO, điều kiện trong domain và `CHECK (quantity > 0)` trên DB. Mỗi chỗ bảo vệ một ranh giới.

## 3. Luồng request trong Spring

```text
Client
  |
  v
HTTP -> JSON parsing / Data binding / Type conversion
         |  JSON lỗi, sai kiểu -> lỗi đọc hoặc bind dữ liệu
         v
      Bean Validation trên Request DTO
         |  rỗng, sai format, ngoài phạm vi -> lỗi đầu vào
         v
      Controller
         v
      Application/Domain Service
         |  kiểm tra chính sách, quyền và bất biến use case
         v
      Repository (JPA/JDBC)
         v
      Database
            NOT NULL / UNIQUE / CHECK / FOREIGN KEY
            transaction + concurrency control
```

**Data binding và validation là hai bước khác nhau.** Dữ liệu `{"quantity":"abc"}` không thể bind sang kiểu số ở bước chuyển đổi. Dữ liệu `{"quantity":-2}` có thể bind thành công nhưng vi phạm `@Positive`. JSON không hợp lệ và giá trị đã bind nhưng sai constraint không nên bị gộp thành một loại lỗi kỹ thuật.

Trong Spring MVC, `@Valid @RequestBody` kích hoạt validation đối tượng sau khi request body được đọc và chuyển thành Java object (khi có Bean Validation provider thích hợp). Lỗi constraint thường dẫn tới `MethodArgumentNotValidException`; lỗi JSON không đọc được thường dẫn tới `HttpMessageNotReadableException`. Với `@ModelAttribute` hoặc method parameters, con đường binding và exception có thể khác. Ứng dụng cần xử lý theo loại thực tế.

## 4. Kiểm tra đầu vào: hợp đồng giữa client và hệ thống

Đây là những điều xác định được từ request mà không cần hỏi trạng thái thay đổi của hệ thống:

- **Bắt buộc:** `@NotNull` chỉ cấm `null`; `@NotBlank` còn cấm chuỗi rỗng/toàn khoảng trắng; `@NotEmpty` cấm chuỗi hoặc collection rỗng.
- **Phạm vi:** `@Size` cho chuỗi/collection, `@Min`/`@Max`/`@Positive`/`@DecimalMin` cho số.
- **Định dạng:** `@Email`, `@Pattern`, validator riêng theo định nghĩa API.
- **Dữ liệu lồng nhau:** `@Valid` dùng để cascade validation; nếu cả đối tượng lồng nhau bắt buộc có mặt, cần thêm `@NotNull`.
- **Quan hệ giữa các trường request:** chẳng hạn `startDate <= endDate` có thể đặt ở custom class-level validator nếu không phụ thuộc dữ liệu hệ thống.

Ví dụ DTO:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RegisterAccountRequest(
    @NotBlank
    @Email
    @Size(max = 254)
    String email,

    @NotBlank
    @Size(min = 12, max = 128)
    String password
) {}
```

`@Email` chỉ đánh giá định dạng theo validator sử dụng; nó **không xác minh hộp thư tồn tại, quyền sở hữu hay tính duy nhất của email**. `@Size` trên `String` là điều kiện về độ dài chuỗi; giới hạn byte thực tế trong giao thức hoặc DB phải được xét riêng nếu liên quan.

Controller nhận DTO để tách API contract khỏi persistence entity:

```java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/accounts")
public class AccountController {
    private final RegistrationService registrationService;

    public AccountController(RegistrationService registrationService) {
        this.registrationService = registrationService;
    }

    @PostMapping
    public ResponseEntity<Map<String, Long>> register(
            @Valid @RequestBody RegisterAccountRequest request) {
        long id = registrationService.register(request);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("id", id));
    }
}
```

Đây là mã minh họa dành cho dự án Spring đã cấu hình các dependencies và có `RegistrationService`; **không phải chương trình độc lập chạy trực tiếp bằng `javac`**. Spring Framework 6/Spring Boot 3 sử dụng namespace `jakarta.validation` thay cho namespace `javax.validation` của thế hệ trước.

Cần phân biệt:

- `@Valid` là cơ chế kích hoạt/cascade Jakarta Bean Validation. `@Validated` của Spring có hỗ trợ nhóm validation và có thể dùng trong thiết lập method validation thích hợp; không tự thay thế điều kiện nghiệp vụ.
- Validator DTO chỉ nên kiểm tra những trường mà client được quyền nhập. Tránh bind trực tiếp request vào entity có `id`, `role`, `approved` hoặc `status` nội bộ: điều này có thể dẫn tới lỗi *mass assignment*.
- Nếu service còn được gọi từ scheduled job, consumer hoặc tiến trình nội bộ, quy tắc domain cốt lõi vẫn phải được kiểm soát tại service/domain. Không thể xem controller validation là tấm chắn duy nhất.

## 5. Quy tắc nghiệp vụ: tính hợp lệ của một hành động

Business rule mô tả hành vi của sản phẩm. Một vài ví dụ:

- Chỉ tài khoản `ACTIVE` mới được đặt hàng.
- Không thể hủy đơn đã bàn giao vận chuyển.
- Số tiền hoàn không vượt tổng tiền còn được phép hoàn.
- Người dùng chỉ được sử dụng một mã ưu đãi trong một chiến dịch.
- Việc đăng ký tài khoản chỉ hợp lệ khi chính sách cho đăng ký đang mở.

Các điều kiện này thường cần đọc repository, truy vấn domain, kiểm tra trạng thái hoặc quyền. Chúng thích hợp trong application service/domain model/domain service thay vì nhét vào request DTO.

Ví dụ phần nghiệp vụ đăng ký:

```java
import java.util.Locale;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {
    private final AccountRepository accounts;
    private final RegistrationPolicy policy;
    private final PasswordEncoder passwordEncoder;

    public RegistrationService(
            AccountRepository accounts,
            RegistrationPolicy policy,
            PasswordEncoder passwordEncoder) {
        this.accounts = accounts;
        this.policy = policy;
        this.passwordEncoder = passwordEncoder;
    }

    @Transactional
    public long register(RegisterAccountRequest request) {
        if (!policy.isRegistrationOpen()) {
            throw new RegistrationClosedException();
        }

        // Chuẩn hóa phải nhất quán với chính sách sản phẩm và DB.
        String normalizedEmail = request.email()
                .trim().toLowerCase(Locale.ROOT);

        if (accounts.existsByNormalizedEmail(normalizedEmail)) {
            throw new EmailAlreadyUsedException();
        }

        Account account = new Account(
                normalizedEmail,
                passwordEncoder.encode(request.password())
        );
        return accounts.save(account).getId();
    }
}
```

Các kiểu `Account`, `AccountRepository`, `RegistrationPolicy` và các exception là thành phần khác cần định nghĩa trong ứng dụng; ví dụ trên minh họa ranh giới trách nhiệm, không phải một dự án build hoàn chỉnh. `PasswordEncoder` thuộc Spring Security Crypto và cần dependency tương ứng.

Ở đây `policy.isRegistrationOpen()` là điều kiện nghiệp vụ. `existsByNormalizedEmail(...)` giúp trả lỗi thân thiện nếu email đã tồn tại. Quyết định email chuẩn hóa như thế nào và account bị xóa mềm có được dùng lại email không cũng là **chính sách nghiệp vụ**, phải thống nhất với cách lưu/index dữ liệu.

**Giới hạn của kiểm tra nghiệp vụ trước khi ghi:** nếu hai request đồng thời cùng thấy email chưa tồn tại, chúng vẫn có thể cùng thử tạo tài khoản. Một `@Transactional` thông thường không tự làm thao tác “kiểm tra rồi chèn” trở thành atomic ở mọi isolation level. Với dữ liệu cần duy nhất, database cần constraint bảo vệ.

Với các rule như “tồn kho đủ để trừ”, chỉ đọc tồn kho rồi kiểm tra trong Java cũng có thể bị race. Có thể cần optimistic locking, pessimistic locking, conditional update hoặc transaction isolation phù hợp. Quy tắc nghiệp vụ xác định *điều phải đúng*; thiết kế đồng thời xác định *làm sao giữ nó đúng khi tranh chấp*.

## 6. Ràng buộc lưu trữ: bảo vệ dữ liệu kể cả khi không đi qua REST API

Ràng buộc lưu trữ là quy tắc mà hệ thống quản lý dữ liệu thực thi trên thao tác ghi. Chúng còn hoạt động khi dữ liệu được thêm bởi job, import, script SQL, ứng dụng khác hoặc giao dịch chạy đồng thời.

Ví dụ DDL cho PostgreSQL:

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    normalized_email VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT uq_accounts_normalized_email
        UNIQUE (normalized_email),
    CONSTRAINT ck_accounts_status
        CHECK (status IN ('ACTIVE', 'LOCKED'))
);
```

- `NOT NULL` không cho phép SQL `NULL`, nhưng không ngăn `''` hoặc chuỗi chỉ có khoảng trắng.
- `UNIQUE` đảm bảo uniqueness theo semantics của DB/index đã định nghĩa. Nếu cột được phép `NULL`, cách xử lý nhiều `NULL` có thể khác nhau giữa các DB/kiểu constraint; kết hợp `NOT NULL` khi trường bắt buộc.
- `CHECK` bảo vệ bất biến biểu diễn được bằng biểu thức DB, ví dụ `CHECK (quantity > 0)` hoặc tập giá trị status.
- `FOREIGN KEY` đảm bảo bản ghi tham chiếu tồn tại và được bảo vệ theo quy tắc referential integrity; nó **không xác minh người dùng có quyền** truy cập bản ghi.
- Transaction, khóa và isolation phối hợp với constraint để duy trì tính nhất quán của các thay đổi nhiều bước.

JPA annotations như `@Column(nullable = false)` hoặc `@Table(uniqueConstraints = ...)` mô tả mapping và có thể ảnh hưởng việc tạo schema tự động, nhưng **không chứng minh schema production thực tế đã có constraint tương ứng**. Với cơ sở dữ liệu quản lý bằng Flyway/Liquibase, cần migration DDL đúng và kiểm thử trên schema đã triển khai. `@NotNull` của Bean Validation không thay được `NOT NULL` của DB.

### Race condition khi kiểm tra email trùng

```text
Thời điểm       Transaction T1              Transaction T2
---------       -------------------------   -------------------------
t1              SELECT email -> chưa có
t2                                          SELECT email -> chưa có
t3              INSERT -> thành công
t4                                          INSERT -> UNIQUE violation
```

Nếu không có unique constraint, hai transaction có thể tạo hai hàng trùng. Khi DB có unique constraint, một giao dịch bị từ chối; ứng dụng nên dịch **vi phạm unique đã nhận diện** thành mã lỗi nghiệp vụ tương ứng (thường HTTP 409 Conflict). Không được suy diễn mọi `DataIntegrityViolationException` đều nghĩa là email trùng vì nó cũng có thể đại diện cho `FOREIGN KEY`, `NOT NULL`, `CHECK` và lỗi integrity khác.

Với JPA, lỗi constraint có thể xuất hiện ở `flush` hoặc lúc transaction `commit`, không nhất thiết ngay tại `repository.save()`. Cần xử lý ở ranh giới có thể thấy lỗi sau khi ghi/commit và nhận diện nguyên nhân dựa trên constraint/code DB đáng tin cậy. Không trả nguyên message SQL ra client vì có thể lộ tên bảng, schema hoặc dữ liệu nhạy cảm.

## 7. Một quy tắc có thể xuất hiện ở nhiều tầng

| Yêu cầu | Đầu vào | Nghiệp vụ | Lưu trữ |
| --- | --- | --- | --- |
| Email đăng ký | `@NotBlank`, `@Email`, `@Size` | Có được đăng ký; chính sách chuẩn hóa; cách xử lý email đã dùng | `NOT NULL`, `UNIQUE(normalized_email)` |
| Số lượng hàng mua | `@Positive` | Không vượt giới hạn đặt mua/tồn kho; xử lý cập nhật đồng thời | `CHECK(quantity > 0)` trên dòng đơn; transaction/locking cho tồn |
| Đặt lịch hẹn | Kiểu ngày giờ, start trước end nếu là điều kiện cố định | Không trùng slot; còn trong giờ làm; đúng quyền | Khóa/constraint/transaction phù hợp cho invariant có thể biểu diễn |
| Hủy đơn | Mã đơn đúng kiểu/format | Người dùng có quyền; trạng thái cho phép hủy | FK và constraint trạng thái biểu diễn được |
| Gán role | Chỉ nhận trường client được gửi | Người cấp role có đủ quyền và phê duyệt | `FOREIGN KEY` tới role, `UNIQUE(user_id, role_id)` |

Ví dụ **uniqueness** cần được hiểu bằng cả chính sách và cơ chế bảo vệ:

- Service có thể kiểm tra trước để cho thông báo “Email đã được đăng ký”.
- DB giữ `UNIQUE` để không bị race hoặc bị bỏ qua bởi job/import.
- Nếu nghiệp vụ cho phép tái sử dụng email của tài khoản soft-delete, `UNIQUE(email)` thông thường có thể không đúng với chính sách; phải thiết kế khóa/index (chẳng hạn partial unique index khi dùng PostgreSQL) và logic dịch lỗi nhất quán.
- Nếu nghiệp vụ coi email không phân biệt hoa/thường, chỉ lower-case ở service nhưng dữ liệu cũ/job lại ghi nguyên dạng sẽ tạo lỗ hổng; dùng chuẩn hóa nhất quán tại mọi writer và/hoặc chiến lược index/DB hỗ trợ tương ứng.

Không cần “ép” mọi quy tắc vào cả ba tầng. Có quy tắc chỉ ở request (một tham số UI có format đặc biệt), chỉ ở domain (trạng thái quy trình), hoặc chỉ khả thi tại DB (một số constraint toàn vẹn). Hãy lựa chọn dựa trên rủi ro và khả năng bảo đảm.

## 8. Phân loại và trả lỗi có chủ đích

| Trường hợp | Nơi phát hiện | Hướng phản hồi API |
| --- | --- | --- |
| JSON hỏng, không thể chuyển kiểu | Parsing/binding | Thường HTTP 400; mô tả request không đọc được |
| Email trống, mật khẩu quá ngắn | Bean Validation | Thường HTTP 400; danh sách lỗi theo trường |
| Đăng ký đang đóng | Service/domain | Lỗi nghiệp vụ rõ nghĩa; status tùy hợp đồng (ví dụ 403/409/422) |
| Email trùng theo chính sách | Service hoặc DB `UNIQUE` | Cùng một mã lỗi ứng dụng; thường HTTP 409 |
| DB vi phạm constraint không dự kiến | DB | Ghi nhận để điều tra, không tự đoán là lỗi email |
| DB mất kết nối | Infrastructure | Lỗi hệ thống phù hợp; không biến thành “validation failed” |

Dùng `@RestControllerAdvice` và `@ExceptionHandler` để thống nhất response. Với `MethodArgumentNotValidException`, lấy field errors thay vì trả nguyên exception. Với business error, định nghĩa exception/mã lỗi domain rõ ràng. Với DB error, chỉ dịch khi đã xác định nguyên nhân; còn lại trả response an toàn và log phục vụ điều tra.

Ví dụ response cho request không hợp lệ (format cụ thể do API tự quy định):

```json
{
  "code": "INVALID_INPUT",
  "errors": [
    {
      "field": "email",
      "message": "Email không đúng định dạng"
    }
  ]
}
```

Với email trùng, có thể trả `code: "EMAIL_ALREADY_USED"` và HTTP 409, bất kể phát hiện ở service hay DB. Không lộ tên constraint, SQL hoặc thông tin mật khẩu. Cũng cần lưu ý rằng HTTP 400/409/422 là lựa chọn thiết kế hợp đồng API; Spring không tự quyết định toàn bộ semantic status theo nghiệp vụ của bạn.

## 9. Quy trình đặt một điều kiện vào đúng tầng

1. **Viết rule dưới dạng yêu cầu cụ thể.** “Email không rỗng; đăng ký phải đang mở; email chuẩn hóa chỉ có một tài khoản hoạt động”.
2. **Tách điều kiện đánh giá được chỉ từ request.** Đặt tại DTO, conversion hoặc validator. Nếu là quan hệ giữa các trường request ổn định, class-level validator có thể phù hợp.
3. **Tách điều kiện phụ thuộc trạng thái/quyền/chính sách.** Đặt tại application/domain service, ở gần thao tác thay đổi trạng thái để các adapter khác cũng tuân thủ.
4. **Xác định bất biến phải đúng khi concurrent write.** Chọn unique index, versioning, khóa, conditional update hoặc cơ chế DB phù hợp. Một câu `SELECT` trước `INSERT` không thay thế được constraint.
5. **Quản lý DDL bằng migrations và kiểm thử trên DB thực.** Đồng bộ kiểu dữ liệu, nullability, kích thước, chuẩn hóa và uniqueness giữa API, domain, schema.
6. **Định nghĩa response và quan sát lỗi.** Input error, business rejection, known integrity conflict và infrastructure failure cần được phân biệt; thống nhất mã lỗi cho cùng một nguyên nhân.
7. **Kiểm thử ở biên thích hợp.** DTO/MVC tests, unit tests cho chính sách domain, integration tests cho constraints và giao dịch đồng thời.

Một số ca kiểm thử cần có:

| Ca | Kỳ vọng |
| --- | --- |
| Email thiếu hoặc sai định dạng | Bị chặn trước khi thực hiện use case |
| Password không đạt `@Size` | Lỗi trường `password` |
| Dữ liệu hợp lệ nhưng đăng ký đã đóng | Service trả lỗi nghiệp vụ |
| Email đã có từ trước | Client nhận conflict phù hợp |
| Hai request đồng thời cùng email | Chỉ một bản ghi thỏa unique constraint được ghi |
| SQL trực tiếp chèn `normalized_email = NULL` | DB từ chối bằng `NOT NULL` |
| SQL trực tiếp chèn status không nằm trong tập hợp | DB từ chối bằng `CHECK` |
| DB integrity error không liên quan email | Không bị dịch nhầm thành `EMAIL_ALREADY_USED` |

Unit test với mock repository trả `existsBy... = false` không chứng minh được khả năng chống race. Cần integration test với hai transaction thực tế để xác minh constraint và cách dịch lỗi.

## 10. Các lỗi thiết kế phổ biến

**Lỗi 1 – Nghĩ `@Valid` chứng minh use case hợp lệ:** annotation chủ yếu kiểm tra dữ liệu được truyền vào, không thay kiểm tra quyền, tồn kho, trạng thái và cạnh tranh ghi.

**Lỗi 2 – Đặt toàn bộ business rule trong controller/custom constraint:** dễ trộn API với nghiệp vụ, cần DB ngay trong validator, khó tái sử dụng từ job/consumer. Business rule thuộc nơi thực thi hành động.

**Lỗi 3 – Kiểm tra trùng trong service rồi bỏ `UNIQUE`:** race giữa SELECT và INSERT vẫn tồn tại. Constraint DB là cơ chế bảo vệ cuối cùng.

**Lỗi 4 – Chỉ tin DB và trả thẳng lỗi SQL:** dữ liệu có thể được bảo vệ nhưng client không hiểu; response có thể lộ chi tiết nội bộ. Cần ánh xạ lỗi rõ nghĩa, có kiểm soát.

**Lỗi 5 – Tin annotation JPA đồng nghĩa schema deployed:** thay đổi entity không đảm bảo migration đã chạy. Kiểm tra schema thực và contract dữ liệu.

**Lỗi 6 – Các tầng hiểu rule khác nhau:** API cho chuỗi dài hơn cột DB; service so sánh email không phân biệt hoa thường nhưng index phân biệt; nghiệp vụ cho phép soft-delete reuse nhưng DB chặn. Phải thống nhất semantics, dữ liệu chuẩn hóa và test end-to-end.

**Lỗi 7 – Đồng nhất mọi lỗi với validation:** malformed JSON, bean constraint, business rejection và storage constraint có nguyên nhân và chủ sở hữu khác nhau. Việc phân biệt giúp API rõ ràng và hệ thống dễ bảo trì.

## 11. Checklist ngắn khi thiết kế

- Nếu chỉ nhìn request là quyết định được, đây thường là **input validation**.
- Nếu cần biết người thực hiện, trạng thái hệ thống, thời điểm hoặc chính sách sản phẩm, đây là **business rule**.
- Nếu điều kiện phải đúng kể cả khi có job, script hoặc transaction đồng thời ghi thẳng DB, hãy cân nhắc **storage constraint** cùng cơ chế concurrency thích hợp.
- Nếu một rule ở nhiều tầng, kiểm tra xem định nghĩa của chúng có **hoàn toàn nhất quán** không.
- Nếu constraint thất bại, xác định được nguyên nhân cụ thể mới dịch thành lỗi nghiệp vụ; không biến mọi DB error thành một mã chung.

Ba tầng cùng phục vụ một mục tiêu nhưng ở các ranh giới khác nhau: **đầu vào hợp lệ để xử lý, hành động hợp lệ theo nghiệp vụ, và dữ liệu lưu trữ giữ toàn vẹn**. Hệ thống đúng cần cả phản hồi dễ hiểu lẫn bảo đảm an toàn dưới tải đồng thời.