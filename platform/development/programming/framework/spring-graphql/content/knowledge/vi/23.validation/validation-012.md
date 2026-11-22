# Thông báo lỗi an toàn

Một GraphQL API cần thông báo lỗi đủ rõ để client biết phải làm gì, nhưng không được tiết lộ chi tiết nội bộ như câu SQL, tên bảng, hostname, stack trace, token hoặc dữ liệu nhạy cảm. **Thông báo lỗi an toàn** là thông báo được thiết kế cho đúng người nhận: client nhận mã lỗi và hướng xử lý có thể công khai; đội vận hành giữ chi tiết kỹ thuật trong log có kiểm soát.

Trong Spring for GraphQL, exception có thể phát sinh khi bind argument, kiểm tra dữ liệu, chạy resolver hoặc gọi service downstream. Ứng dụng cần phân biệt các giai đoạn này, chuẩn hóa GraphQL error contract và chỉ đưa dữ liệu đã được duyệt vào response. Không nên trả nguyên văn thông điệp của exception cho client chỉ vì nó thuận tiện khi debug.

## 1. Vì sao cần thông báo lỗi an toàn?

Giả sử một mutation đăng ký người dùng gọi service lưu dữ liệu. Database có thể ném exception chứa tên constraint, tên schema hoặc câu SQL. Nếu resolver trả thẳng thông điệp đó, client có thể nhận được thông tin không cần thiết về cấu trúc database.

Ví dụ thông báo không an toàn:

~~~text
duplicate key value violates unique constraint "uk_users_email"
Detail: Key (email)=(person@example.com) already exists.
SQL: insert into internal_schema.users ...
~~~

Client không cần biết tên constraint, câu SQL hay schema nội bộ. API có thể trả thông báo đã được thiết kế:

~~~json
{
  "errors": [
    {
      "message": "An account with this email already exists",
      "extensions": {
        "code": "EMAIL_ALREADY_REGISTERED"
      }
    }
  ]
}
~~~

Thông báo này cho client biết hành động tiếp theo mà không tiết lộ cách database lưu dữ liệu. Chi tiết exception gốc vẫn có thể được ghi vào log nội bộ với quyền truy cập phù hợp.

Thông báo an toàn cần đạt ba mục tiêu:

- **Hữu ích:** client hiểu lỗi thuộc nhóm nào và có thể xử lý bằng mã ổn định.
- **Tối thiểu:** chỉ trả thông tin cần thiết cho người gọi, không đưa dữ liệu nội bộ vào response.
- **Nhất quán:** cùng một lỗi nghiệp vụ được biểu diễn theo cùng một contract trên các resolver và entry point.

## 2. Phân biệt các giai đoạn phát sinh lỗi

Không phải mọi lỗi GraphQL đều đi qua cùng một cơ chế. Cần xác định lỗi xảy ra trước execution, trong DataFetcher hay ở tầng HTTP:

| Giai đoạn | Ví dụ | Nơi xử lý phù hợp |
| --- | --- | --- |
| HTTP/transport | Request body sai định dạng, header không hợp lệ | Web/transport layer |
| Authentication trước GraphQL | Token thiếu hoặc hết hạn ở security filter | Spring Security |
| Parse | GraphQL document sai cú pháp | GraphQL engine |
| Validation | Field không tồn tại, argument không đúng kiểu | GraphQL validation |
| Variable coercion | Thiếu variable non-null hoặc giá trị không phù hợp scalar | GraphQL execution preparation |
| Argument binding | Không bind được input vào kiểu Java đích | Spring for GraphQL argument binding |
| Bean/domain validation | Email sai định dạng, số lượng vượt giới hạn nghiệp vụ | Validation/application service |
| DataFetcher execution | Service ném exception khi resolve field | DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler |
| Async completion | CompletableFuture/Mono hoàn tất bất thường | Cơ chế exception handling của GraphQL execution |

**DataFetcherExceptionResolver** xử lý exception phát sinh trong quá trình thực thi DataFetcher. Nó không phải nơi xử lý lỗi cú pháp document, lỗi validation schema hay mọi lỗi HTTP trước khi GraphQL handler được gọi.

Việc phân biệt giai đoạn giúp đặt thông báo ở đúng tầng. Ví dụ, GraphQL có thể tự báo rằng argument bắt buộc bị thiếu trước khi controller được gọi; còn quy tắc email phải thuộc domain hợp lệ thường cần được kiểm tra ở application layer.

## 3. Cấu trúc GraphQL error response

GraphQL response có thể chứa cả data và errors. Một lỗi ở field không nhất thiết làm toàn bộ operation thất bại:

~~~json
{
  "data": {
    "profile": {
      "displayName": "An"
    },
    "orders": null
  },
  "errors": [
    {
      "message": "Orders are temporarily unavailable",
      "path": ["orders"],
      "extensions": {
        "code": "ORDERS_UNAVAILABLE"
      }
    }
  ]
}
~~~

Các thành phần chính:

- **message:** thông báo dành cho client. Đây là nội dung cần kiểm soát chặt chẽ.
- **locations:** vị trí dòng/cột của field trong GraphQL document nếu lỗi gắn với một vị trí.
- **path:** đường dẫn response đến field phát sinh lỗi. Path dùng alias nếu client đặt alias và có thể chứa chỉ số list.
- **extensions:** metadata bổ sung, thường chứa mã lỗi, nhóm lỗi hoặc danh sách vi phạm input đã được lọc.

Path không phải đường dẫn đến property bên trong input object. Ví dụ lỗi xảy ra khi resolver của field register xử lý input.email thì path GraphQL thường trỏ đến field response register. Nếu client cần biết property input nào không hợp lệ, hãy đưa một danh sách field violations an toàn vào extensions theo contract riêng.

HTTP status không phải cách duy nhất để xác định kết quả của GraphQL operation. Một execution có thể trả HTTP response thành công ở tầng transport nhưng vẫn có phần tử trong errors. Client cần đọc cả data và errors, sau đó dùng extensions.code để quyết định cách xử lý.

## 4. Thiết kế error contract ổn định

Không nên buộc client phân tích message để xác định loại lỗi. Message có thể được chỉnh sửa, dịch sang ngôn ngữ khác hoặc thay đổi cách diễn đạt. Hãy dùng mã lỗi ổn định trong extensions:

~~~json
{
  "message": "The requested book could not be found",
  "extensions": {
    "code": "BOOK_NOT_FOUND",
    "category": "NOT_FOUND"
  }
}
~~~

Một contract đơn giản có thể gồm:

| Field | Ý nghĩa | Quy tắc |
| --- | --- | --- |
| message | Thông báo hiển thị hoặc dùng để hỗ trợ client | Không chứa chi tiết nội bộ hoặc giá trị nhạy cảm |
| extensions.code | Mã lỗi máy đọc được | Ổn định, duy nhất trong phạm vi API |
| extensions.category | Nhóm lỗi tổng quát | Chọn từ tập giá trị được công bố |
| extensions.violations | Danh sách lỗi input theo field | Chỉ gồm tên field công khai, code và message an toàn |
| extensions.correlationId | Mã liên hệ để hỗ trợ tra log nếu policy cho phép | Không dùng làm thông tin xác thực |

Không cần đưa tất cả các field này vào mọi error. Chỉ gửi metadata cần thiết cho loại lỗi tương ứng. Đặc biệt, không đưa exception class, stack trace, SQL, host nội bộ, raw request hay rejected value vào extensions.

Nên duy trì danh mục mã lỗi trong ứng dụng và tài liệu API. Khi thay đổi message, client vẫn dựa trên code cũ. Nếu cần ngừng một mã, hãy quản lý như thay đổi contract có version hoặc lộ trình tương thích.

## 5. Thông báo validation theo field

Với input object, một request có thể có nhiều lỗi cùng lúc. Thay vì chỉ trả một message chung, API có thể trả danh sách violations để client đánh dấu từng field trên form.

Schema ví dụ:

~~~graphql
input RegisterInput {
    email: String!
    password: String!
    displayName: String!
}

type Mutation {
    register(input: RegisterInput!): User!
}
~~~

Một response validation an toàn:

~~~json
{
  "errors": [
    {
      "message": "Input validation failed",
      "path": ["register"],
      "extensions": {
        "code": "VALIDATION_FAILED",
        "violations": [
          {
            "field": "email",
            "code": "INVALID_FORMAT",
            "message": "Enter a valid email address"
          },
          {
            "field": "password",
            "code": "TOO_SHORT",
            "message": "Password does not meet the minimum length"
          }
        ]
      }
    }
  ]
}
~~~

Ở đây API không echo password, email đã gửi hoặc giá trị bị từ chối. Client vẫn biết field nào cần sửa. Tên field trong violations phải là tên input công khai của GraphQL, không phải tên cột database hoặc tên property nội bộ nếu hai bên khác nhau.

Với input lồng nhau, field path có thể là address.postalCode hoặc items[0].quantity. Hãy thống nhất định dạng path để client có thể ánh xạ đến control tương ứng. Không đưa giá trị lỗi vào violation trừ khi đó là dữ liệu không nhạy cảm và có lý do rõ ràng.

## 6. Tạo model validation error an toàn

Có thể biểu diễn một vi phạm bằng kiểu dữ liệu riêng:

~~~java
public record FieldViolation(
        String field,
        String code,
        String message) {
}

public class InputValidationException extends RuntimeException {

    private final List<FieldViolation> violations;

    public InputValidationException(List<FieldViolation> violations) {
        super("Input validation failed");
        this.violations = List.copyOf(violations);
    }

    public List<FieldViolation> getViolations() {
        return violations;
    }
}
~~~

Exception này chỉ mang dữ liệu đã được chuẩn hóa để công khai. Không lưu rejected value hoặc toàn bộ input object trong exception nếu input có thể chứa password, token hay thông tin cá nhân.

Service có thể kiểm tra input và tạo violation theo quy tắc đã định nghĩa:

~~~java
public void validate(RegisterInput input) {
    List<FieldViolation> violations = new ArrayList<>();

    if (input.email() == null || !EMAIL_PATTERN.matcher(input.email()).matches()) {
        violations.add(new FieldViolation(
            "email", "INVALID_FORMAT", "Enter a valid email address"));
    }

    if (input.password() == null || input.password().length() < 12) {
        violations.add(new FieldViolation(
            "password", "TOO_SHORT",
            "Password does not meet the minimum length"));
    }

    if (input.displayName() == null || input.displayName().isBlank()) {
        violations.add(new FieldViolation(
            "displayName", "REQUIRED", "Display name is required"));
    }

    if (!violations.isEmpty()) {
        throw new InputValidationException(violations);
    }
}
~~~

Ví dụ này minh họa cách kiểm soát message và code ở application layer. Trong dự án thực tế, nên dùng Bean Validation cho constraint phù hợp và chuyển kết quả thành public violations bằng một mapper tập trung.

## 7. Dùng Bean Validation mà không làm lộ rejected value

Spring application có thể dùng Jakarta Bean Validation với các constraint như **@NotBlank**, **@Email**, **@Size**, **@Min** và **@Max**. Schema GraphQL kiểm tra kiểu và nullability; Bean Validation kiểm tra các quy tắc dữ liệu sâu hơn.

Ví dụ input DTO:

~~~java
public record RegisterInput(
        @NotBlank
        @Email
        String email,

        @NotBlank
        @Size(min = 12, max = 128)
        String password,

        @NotBlank
        @Size(max = 80)
        String displayName) {
}
~~~

Khi nhận validation violations, không nên serialize trực tiếp toàn bộ ConstraintViolation hoặc BindingResult cho client. Các object này có thể chứa invalid value, object root, property path nội bộ và message template không phù hợp với public API.

Thay vào đó, mapper nên:

1. Lấy property path cần thiết và chuyển sang tên field GraphQL công khai.
2. Xác định constraint/code từ danh sách cho phép.
3. Chọn message an toàn đã được duyệt.
4. Bỏ rejected value và mọi thông tin object nội bộ.
5. Giới hạn số lượng violations để response không bị phình lớn.

Ví dụ mapping theo constraint name:

~~~java
private FieldViolation toPublicViolation(ConstraintViolation<?> violation) {
    String field = violation.getPropertyPath().toString();
    String annotationName = violation.getConstraintDescriptor()
        .getAnnotation().annotationType().getSimpleName();

    return switch (annotationName) {
        case "NotBlank" -> new FieldViolation(
            field, "REQUIRED", "This field is required");
        case "Email" -> new FieldViolation(
            field, "INVALID_FORMAT", "Enter a valid email address");
        case "Size" -> new FieldViolation(
            field, "INVALID_LENGTH", "The value has an invalid length");
        default -> new FieldViolation(
            field, "INVALID_VALUE", "The value is invalid");
    };
}
~~~

Đây là ví dụ rút gọn; mapper thực tế cần xét constraint groups, nested path, class-level constraint và tên field public. Không nên gửi thẳng violation.getMessage() nếu message bundle có thể chứa interpolated value hoặc nội dung dành cho developer. Nếu dùng message template đã được kiểm soát và không có rejected value, có thể dùng chúng như nguồn message sau khi review.

## 8. Ánh xạ exception thành GraphQL error trong Spring

Với exception phát sinh từ DataFetcher, Spring for GraphQL cung cấp **DataFetcherExceptionResolver** và **DataFetcherExceptionResolverAdapter**. Có thể ánh xạ InputValidationException thành một GraphQLError có mã ổn định:

~~~java
@Component
public class SafeValidationExceptionResolver
        extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable ex, DataFetchingEnvironment environment) {

        if (ex instanceof InputValidationException validationException) {
            List<Map<String, String>> violations =
                validationException.getViolations().stream()
                    .map(v -> Map.of(
                        "field", v.field(),
                        "code", v.code(),
                        "message", v.message()))
                    .toList();

            return GraphqlErrorBuilder.newError(environment)
                .errorType(ErrorType.BAD_REQUEST)
                .message("Input validation failed")
                .extensions(Map.of(
                    "code", "VALIDATION_FAILED",
                    "violations", violations))
                .build();
        }

        return null;
    }
}
~~~

**GraphqlErrorBuilder.newError(environment)** gắn error với field đang được thực thi, nhờ đó GraphQL giữ path và location phù hợp. Resolver chỉ xử lý loại exception đã biết; với exception khác, trả null để resolver tiếp theo hoặc default handler xử lý.

Có thể dùng **@GraphQlExceptionHandler** trong controller hoặc **@ControllerAdvice** để tổ chức mapping theo exception type. Dù chọn cơ chế nào, hãy dùng chung mapper và error contract để cùng một lỗi không có message/code khác nhau tùy controller.

Không nên viết một catch-all resolver trả ex.getMessage() cho mọi exception. Exception database, HTTP client hoặc lỗi lập trình có thể chứa dữ liệu không dành cho client.

## 9. Xử lý exception không mong đợi

Với exception không được nhận diện, response nên dùng thông báo tổng quát:

~~~json
{
  "errors": [
    {
      "message": "An unexpected error occurred",
      "path": ["register"],
      "extensions": {
        "code": "INTERNAL_ERROR"
      }
    }
  ]
}
~~~

Chi tiết exception gốc được ghi ở server log với correlation ID để đội vận hành tra cứu. Spring for GraphQL có cơ chế xử lý mặc định cho exception không được resolver xử lý; hãy giữ hành vi che chi tiết nội bộ ở production và không tự thay bằng message nguyên gốc.

Một số nguyên tắc:

- Không trả stack trace, exception class hoặc cause chain.
- Không trả câu SQL, tên bảng, constraint, connection string hoặc hostname.
- Không trả token, cookie, password, API key hoặc header xác thực.
- Không trả raw request, variables hay rejected value.
- Không trả đường dẫn file, thư mục source hoặc tên package nội bộ.
- Không biến lỗi hệ thống thành thành công với data rỗng nếu không có fallback nghiệp vụ rõ ràng.

Trong môi trường development, log chi tiết có thể được bật ở server để hỗ trợ debug. Không nên bật chế độ hiển thị stack trace hoặc exception detail cho client production. Việc dùng profile development không có nghĩa mọi request bên ngoài đều được phép xem thông tin nội bộ.

## 10. Không để thông báo lỗi tiết lộ sự tồn tại của dữ liệu

Thông báo lỗi có thể tạo ra **enumeration side channel**: người gọi dò xem email, tài khoản, đơn hàng hoặc tài nguyên có tồn tại hay không.

Ví dụ một API reset password trả:

- “Email không tồn tại” khi địa chỉ chưa đăng ký.
- “Đã gửi email reset” khi địa chỉ đã đăng ký.

Người gọi có thể dùng response để thu thập danh sách tài khoản. Với use case này, nên trả thông báo chung giống nhau cho cả hai trường hợp, chẳng hạn “If the account is eligible, instructions will be sent”.

Tương tự, nếu việc phân biệt NOT_FOUND và FORBIDDEN làm lộ sự tồn tại của resource, có thể dùng thông báo chung và policy thống nhất. Không phải mọi API đều cần che NOT_FOUND; quyết định phụ thuộc mức nhạy cảm của resource và threat model.

Ngoài message, cần chú ý:

- Response shape và extensions không nên vô tình khác biệt theo trạng thái bí mật.
- Thời gian xử lý không nên tạo chênh lệch rõ rệt nếu có thể bị khai thác.
- Authorization phải được kiểm tra ở server, không dựa vào việc client có chọn field hay không.
- DataLoader/batch query phải áp dụng tenant và quyền truy cập cho từng key.

Không dùng Correlation ID, request ID hoặc mã lỗi làm bằng chứng xác thực. Chúng chỉ là metadata phục vụ quan sát.

## 11. Thiết kế thông báo lỗi theo môi trường và ngôn ngữ

Thông báo dành cho người dùng có thể cần bản địa hóa; mã lỗi dành cho máy nên ổn định. Ví dụ cùng code VALIDATION_FAILED có thể có message tiếng Việt hoặc tiếng Anh tùy locale, nhưng client vẫn xử lý bằng code và field path.

Không nên để client phụ thuộc vào câu chữ cụ thể. Có thể định nghĩa:

~~~json
{
  "message": "Dữ liệu nhập chưa hợp lệ",
  "extensions": {
    "code": "VALIDATION_FAILED",
    "violations": [
      {
        "field": "email",
        "code": "INVALID_FORMAT",
        "message": "Vui lòng nhập địa chỉ email hợp lệ"
      }
    ]
  }
}
~~~

Nếu ứng dụng dùng MessageSource, hãy chọn message key từ danh sách code đã được kiểm soát và resolve theo Locale trong GraphQLContext hoặc request context. Không dùng exception message tự do làm message key.

Nên giới hạn độ dài message, số lượng violations và kích thước extensions. Một input object rất lớn có thể tạo hàng nghìn lỗi; trả toàn bộ lỗi sẽ làm response nặng và có thể bị lạm dụng. Có thể giới hạn số violations trả về và thêm metadata an toàn cho biết danh sách đã bị rút gọn.

## 12. Logging, Correlation ID và bảo vệ log

Client cần message an toàn; operator cần chi tiết đủ để điều tra. Hai mục tiêu này nên được đáp ứng ở hai kênh khác nhau:

| Kênh | Nội dung phù hợp |
| --- | --- |
| GraphQL response | Public message, stable error code, field violations đã lọc |
| Application log | Exception gốc, stack trace khi cần, operation/field name và correlation ID |
| Trace/metrics | Latency, dependency, error category và trace/span context |

Ví dụ log có cấu trúc:

~~~java
log.error(
    "GraphQL field failed: correlationId={}, field={}, errorCode={}",
    correlationId, fieldName, "INTERNAL_ERROR", exception);
~~~

Không log toàn bộ GraphQL variables một cách mặc định. Variables có thể chứa password, email, địa chỉ, token hoặc dữ liệu thanh toán. Nếu cần ghi input để điều tra, hãy lọc theo allowlist, mask dữ liệu nhạy cảm và giới hạn quyền truy cập log.

Correlation ID giúp tìm các log liên quan nhưng không thay thế trace ID. Nếu ứng dụng dùng Micrometer Tracing hoặc OpenTelemetry, hãy để framework quản lý distributed trace propagation và chỉ bổ sung correlation ID theo policy quan sát của hệ thống.

Log cũng là một bề mặt tấn công. Không đưa chuỗi chưa kiểm tra chứa CR/LF hoặc ký tự điều khiển vào log theo cách có thể giả mạo log entry. Dùng structured logging và giới hạn kích thước các giá trị do client kiểm soát.

## 13. Partial data, nullability và thông báo lỗi

Khi một field gặp exception, GraphQL tạo error và xử lý giá trị field theo nullability:

- Nếu field nullable, field đó có thể trở thành null trong khi các field khác vẫn trả dữ liệu.
- Nếu field non-null, null được lan lên parent gần nhất có thể nhận null.
- Error path vẫn trỏ đến field gốc gây lỗi, dù vị trí null trong data đã lan lên parent.

Ví dụ:

~~~graphql
type Query {
    book: Book
}

type Book {
    title: String!
    reviews: [Review!]!
}
~~~

Nếu resolver của reviews lỗi, field reviews non-null khiến giá trị Book có thể trở thành null vì Query.book nullable. Nếu Query.book cũng non-null, null có thể lan tiếp đến root data.

Không nên thay exception bằng null chỉ để tránh hiển thị errors. Điều đó có thể che lỗi hệ thống và khiến client hiểu nhầm là không có dữ liệu. Chỉ trả null khi null là kết quả hợp lệ theo nghiệp vụ và schema.

## 14. Kiểm thử thông báo lỗi an toàn bằng GraphQlTester

Kiểm thử không chỉ xác nhận có error mà còn phải xác nhận response **không chứa dữ liệu nhạy cảm**. Ví dụ với validation error:

~~~java
GraphQlTester.Response response = graphQlTester.document("""
        mutation {
            register(input: {
                email: "not-an-email"
                password: "short-secret"
                displayName: ""
            }) {
                id
            }
        }
        """)
    .execute();

response.errors().satisfy(errors -> {
    assertThat(errors).anySatisfy(error ->
        assertThat(error.getExtensions().get("code"))
            .isEqualTo("VALIDATION_FAILED"));

    assertThat(errors).allSatisfy(error -> {
        assertThat(error.getMessage()).doesNotContain("short-secret");
        assertThat(error.getMessage()).doesNotContain("not-an-email");
        assertThat(error.getExtensions().toString())
            .doesNotContain("short-secret", "not-an-email");
    });
});
~~~

Đây là ví dụ minh họa; API assertion cụ thể có thể được điều chỉnh theo phiên bản GraphQlTester. Trong test thực tế, nên đọc message và extensions từ error response rồi kiểm tra từng trường.

Các tình huống cần kiểm thử:

1. Validation error có đúng code và field path.
2. Rejected value nhạy cảm không xuất hiện trong message hoặc extensions.
3. Unknown exception trả thông báo tổng quát, không có stack trace/cause.
4. Exception database không làm lộ SQL, tên bảng hoặc constraint.
5. Error path đúng khi dùng alias và nested field.
6. Partial data vẫn có mặt khi field khác lỗi và nullability cho phép.
7. Không tiết lộ sự tồn tại của tài khoản/resource nhạy cảm.
8. Correlation ID có thể tìm trong log nhưng không được dùng làm quyền truy cập.
9. Log không chứa password, token hoặc toàn bộ variables.
10. Số lượng và kích thước field violations được giới hạn.

Nên có integration test qua HTTP/WebGraphQlTester để xác nhận cấu hình thực tế của Spring Security, interceptor, exception resolver và GraphQL response. Unit test mapper chỉ chứng minh hàm chuyển đổi hoạt động; nó chưa chứng minh toàn bộ request path an toàn.

## 15. Lỗi thường gặp

| Cách làm sai | Rủi ro | Cách sửa |
| --- | --- | --- |
| Trả thẳng ex.getMessage() | Lộ SQL, hostname, constraint hoặc dữ liệu nhạy cảm | Dùng public message và error code đã định nghĩa |
| Serialize ConstraintViolation trực tiếp | Có thể lộ rejected value và object nội bộ | Map sang FieldViolation allowlist |
| Client parse message để quyết định | Message thay đổi theo ngôn ngữ hoặc phiên bản | Dùng extensions.code ổn định |
| Đưa exception class/stack trace vào extensions | Tiết lộ cấu trúc triển khai | Giữ chi tiết trong log nội bộ |
| Dùng cùng message khác nhau cho tài khoản có/không tồn tại | Cho phép account enumeration | Dùng response chung nếu resource nhạy cảm |
| Trả mọi lỗi thành null | Che lỗi và làm client hiểu sai | Chỉ dùng null cho kết quả nullable hợp lệ |
| Dùng resolver xử lý lỗi parse/validation | Sai lifecycle, resolver không được gọi | Xử lý ở GraphQL validation/request layer |
| Ghi toàn bộ variables vào log | Lộ password, token, PII | Allowlist/mask và structured logging |
| Trả quá nhiều violations | Response lớn, dễ bị lạm dụng | Giới hạn số lượng và kích thước |
| Dùng correlation ID làm security identity | Có thể giả mạo hoặc đoán | Dùng authenticated principal và authorization thực sự |

## 16. Checklist thiết kế public error

Trước khi phát hành một loại lỗi mới, hãy trả lời:

- Client có cần biết chính xác lý do này không, hay một thông báo chung an toàn hơn?
- Message có chứa dữ liệu do client gửi, rejected value hoặc chi tiết nội bộ không?
- Có stable code để client xử lý mà không parse message không?
- Nếu là validation error, field path có khớp tên input công khai không?
- Extensions có chỉ chứa dữ liệu allowlist không?
- Error path/location có được giữ bằng DataFetchingEnvironment khi lỗi gắn với field không?
- Nullability có tạo partial response đúng kỳ vọng không?
- Log nội bộ có correlation/trace ID và exception gốc cần thiết không?
- Có nguy cơ enumeration hoặc timing side channel không?
- Có test chứng minh thông tin nhạy cảm không xuất hiện trong response và log không?

## 17. Nguyên tắc thiết kế

Thiết kế một error contract thống nhất cho toàn bộ Spring for GraphQL API. Dùng message an toàn và stable code; chỉ đưa field violations đã lọc vào extensions; không serialize trực tiếp exception, BindingResult hay ConstraintViolation. Phân biệt lỗi parse/validation, argument binding, domain validation, DataFetcher execution và transport để xử lý ở đúng tầng.

Với exception đã biết, ánh xạ qua DataFetcherExceptionResolver hoặc @GraphQlExceptionHandler. Với exception không mong đợi, giữ thông báo tổng quát cho client và ghi chi tiết ở server log có kiểm soát. Bảo vệ dữ liệu nhạy cảm trong cả response lẫn log, đồng thời chú ý account enumeration, null propagation và partial data.

Thông báo lỗi tốt không phải là thông báo chứa nhiều chi tiết nhất. Nó là hợp đồng giúp client hiểu và xử lý tình huống, trong khi chỉ tiết lộ đúng phần thông tin mà người gọi được phép biết.
