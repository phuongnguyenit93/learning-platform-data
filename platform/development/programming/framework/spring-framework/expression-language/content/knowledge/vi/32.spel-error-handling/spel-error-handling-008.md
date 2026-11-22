# Thông báo lỗi không làm lộ dữ liệu nhạy cảm khi dùng SpEL

## Mục tiêu

Khi Spring Expression Language (SpEL) parse hoặc đánh giá một biểu thức, lỗi có thể phát sinh do cú pháp sai, property không tồn tại, giá trị null, chuyển đổi kiểu thất bại, method không được phép hoặc logic bên trong method ném exception. Thông tin lỗi rất hữu ích cho developer, nhưng message và cause chain đôi khi chứa source expression, giá trị đầu vào, tên class/bean, đường dẫn tài nguyên hoặc dữ liệu nghiệp vụ.

Ứng dụng cần tách thông tin dành cho người gọi khỏi thông tin chẩn đoán nội bộ. Phản hồi bên ngoài nên dùng thông báo ngắn, mã lỗi ổn định và correlation ID nếu cần hỗ trợ. Log nội bộ chỉ nên ghi metadata cần thiết, có kiểm soát truy cập và không ghi raw expression, secret, token, dữ liệu cá nhân hoặc toàn bộ object trong evaluation context.

## 1. Các loại lỗi thường gặp khi đánh giá SpEL

Phân biệt lỗi theo giai đoạn giúp xử lý đúng và tránh trả về thông tin kỹ thuật quá chi tiết:

| Giai đoạn | Loại lỗi | Ví dụ |
| --- | --- | --- |
| Parse | `ParseException` hoặc `SpelParseException` | Thiếu dấu ngoặc, toán tử sai cú pháp, literal không hợp lệ. |
| Evaluation | `EvaluationException` hoặc `SpelEvaluationException` | Property không tồn tại, dereference null, index ngoài phạm vi, không tìm được method hoặc type. |
| Conversion | Lỗi chuyển đổi kiểu trong lúc đánh giá | Kết quả hoặc đối số không chuyển được sang kiểu mong đợi. |
| Method/function execution | Exception phát sinh từ Java method được gọi | Helper hoặc bean ném lỗi khi xử lý đối số. |
| Business validation | Biểu thức chạy thành công nhưng dữ liệu không thỏa quy tắc | Kết quả Boolean là false hoặc giá trị nằm ngoài miền cho phép. |

Lỗi parse và lỗi evaluation không giống một kết quả nghiệp vụ `false`. Một expression có thể đánh giá thành false hợp lệ; điều đó khác với việc expression không thể chạy.

## 2. Không trả exception message trực tiếp cho client

Tránh đưa trực tiếp các giá trị sau vào HTTP response, UI message hoặc API error body:

- `exception.getMessage()` hoặc toàn bộ stack trace.
- Source expression đầy đủ, đặc biệt nếu expression do người dùng gửi.
- Giá trị của root object, context variables, method arguments hoặc rejected values.
- Tên class, package, bean, method nội bộ nếu chúng tiết lộ cấu trúc ứng dụng.
- SQL, URL nội bộ, đường dẫn file, hostname, cấu hình hoặc thông tin kết nối.
- Token, password, session identifier, access key hoặc dữ liệu cá nhân.

Exception message có thể thay đổi theo phiên bản thư viện và nội dung runtime. Không xem message của framework là một API ổn định hoặc một thông báo đã được làm sạch.

Thay vào đó, trả về thông báo theo mã lỗi do ứng dụng định nghĩa:

| Mã lỗi nội bộ | Thông báo bên ngoài có thể dùng |
| --- | --- |
| `RULE_INVALID` | Biểu thức quy tắc không hợp lệ. |
| `RULE_EVALUATION_FAILED` | Không thể đánh giá quy tắc tại thời điểm này. |
| `RULE_RESULT_INVALID` | Quy tắc không trả về kết quả hợp lệ. |
| `INPUT_INVALID` | Dữ liệu đầu vào không hợp lệ. |
| `REQUEST_FAILED` | Không thể xử lý yêu cầu. |

Chỉ trả chi tiết validation cho field nếu nội dung đó đã được thiết kế để hiển thị công khai và không chứa giá trị nhạy cảm.

## 3. Tách parse error, evaluation error và business result

Nên xử lý parse và evaluation ở các ranh giới rõ ràng. Ví dụ dưới đây minh họa cách dùng mã lỗi riêng và không trả exception message:

```java
Expression expression;
try {
    expression = parser.parseExpression(ruleSource);
}
catch (ParseException ex) {
    logger.warn(
            "Rule parse failed: ruleId={}, correlationId={}",
            ruleId, correlationId);
    return RuleResult.error("RULE_INVALID");
}

try {
    Boolean result = expression.getValue(context, Boolean.class);
    if (result == null) {
        return RuleResult.error("RULE_RESULT_INVALID");
    }
    return RuleResult.success(Boolean.TRUE.equals(result));
}
catch (EvaluationException ex) {
    logger.error(
            "Rule evaluation failed: ruleId={}, correlationId={}",
            ruleId, correlationId);
    return RuleResult.error("RULE_EVALUATION_FAILED");
}
```

`RuleResult` là kiểu kết quả do ứng dụng định nghĩa để phân biệt đánh giá thành công với lỗi. Không biến mọi exception thành `false` rồi tiếp tục như thể rule đã chạy bình thường.

Đối với authorization hoặc quyết định cho phép hành động, lỗi evaluation phải dẫn tới trạng thái từ chối hoặc trạng thái lỗi an toàn theo policy. Không được cho phép hành động chỉ vì không đánh giá được rule. Đồng thời, cần giữ mã lỗi riêng để vận hành có thể phát hiện lỗi hệ thống thay vì nhầm nó với một quyết định `false` hợp lệ.

## 4. Log metadata hữu ích, không log dữ liệu đầu vào

Log nên giúp xác định rule và lần request xảy ra lỗi mà không lưu nội dung nhạy cảm:

**Metadata thường hữu ích:**

- ID của rule hoặc expression đã được ứng dụng quản lý.
- Version của rule hoặc cấu hình.
- Correlation ID/request ID.
- Loại lỗi do ứng dụng phân loại: parse, evaluation, conversion hoặc business validation.
- Tên component xử lý và thời điểm xảy ra.
- Mã message/code nội bộ nếu có thể ghi mà không chứa dữ liệu đầu vào.

**Không log mặc định:**

- Raw expression hoặc expression được ghép từ dữ liệu người dùng.
- Toàn bộ `EvaluationContext`, root object hoặc variable map.
- Arguments của method và giá trị trả về.
- Password, token, API key, cookie, session ID hoặc credential.
- Toàn bộ `FieldError.getRejectedValue()` từ DataBinder.
- Exception message/cause chain nếu có thể chứa dữ liệu đầu vào hoặc secret.

Ví dụ log có cấu trúc:

```java
logger.warn(
        "SpEL parse failed: ruleId={}, ruleVersion={}, correlationId={}, category={}",
        ruleId, ruleVersion, correlationId, "RULE_PARSE_FAILED");
```

Không truyền exception làm tham số cuối nếu logger sẽ ghi cả message và stack trace chứa dữ liệu không được làm sạch. Khi cần stack trace để điều tra, dùng một sink nội bộ có quyền truy cập giới hạn, retention phù hợp và cơ chế redact đã được kiểm chứng.

## 5. Cẩn trọng với exception cause chain

Không chỉ exception ngoài cùng mới có thể chứa dữ liệu nhạy cảm. Một method được gọi từ SpEL có thể ném exception từ HTTP client, JDBC driver, ORM, parser hoặc thư viện khác. Cause chain có thể chứa:

- URL nội bộ, query parameters hoặc hostname.
- SQL statement, tên bảng/cột hoặc dữ liệu bind.
- Đường dẫn file và tên thư mục.
- Giá trị đối số hoặc nội dung request.
- Thông tin xác thực do thư viện thêm vào diagnostic.

Vì vậy, không nên giả định rằng chỉ cần thay message bên ngoài là đủ. Cần quyết định rõ nơi nào được phép lưu stack trace, ai có thể đọc log và dữ liệu nào phải được redact trước khi ghi.

Nếu không cần stack trace đầy đủ để xử lý sự cố, log exception category và correlation ID. Nếu cần điều tra sâu, ghi thông tin kỹ thuật vào hệ thống nội bộ được bảo vệ, tránh đưa nó vào response hoặc log mà nhiều người có thể truy cập.

## 6. Không echo source expression của người dùng

Nếu người dùng có thể tạo hoặc sửa rule, source expression có thể chứa dữ liệu bí mật hoặc thông tin cá nhân. Không đưa nguyên văn source vào lỗi validation, audit log, analytics event hoặc thông báo UI.

Thay vì:

```java
logger.warn("Invalid expression: {}", ruleSource);
```

hãy log ID/version của rule:

```java
logger.warn(
        "Invalid expression: ruleId={}, ruleVersion={}, correlationId={}",
        ruleId, ruleVersion, correlationId);
```

Nếu cần nhận diện một phiên bản source cụ thể, có thể lưu một fingerprint/hash được tạo theo policy của ứng dụng; không dùng hash thay cho kiểm soát quyền truy cập và không coi hash là cách ẩn danh tuyệt đối đối với dữ liệu có miền giá trị nhỏ.

Không nối dữ liệu request vào source expression. Dùng expression cố định và truyền dữ liệu qua variable hoặc root DTO:

```java
Expression expression = parser.parseExpression("customerCode == #inputCode");
StandardEvaluationContext context = new StandardEvaluationContext(customerView);
context.setVariable("inputCode", suppliedCode);
```

Cách này tách dữ liệu khỏi cú pháp SpEL. Nếu chính source expression không đáng tin cậy, vẫn phải giới hạn các tính năng và quyền truy cập của EvaluationContext; việc dùng variables không tự biến source thành an toàn.

## 7. Không làm lộ dữ liệu qua DataBinder và validation errors

Trong Spring MVC, lỗi bind hoặc validation có thể chứa `FieldError`, field name, rejected value và thông tin conversion. `rejectedValue` có thể là password, token hoặc dữ liệu riêng tư.

Không serialize toàn bộ `BindingResult` hoặc `FieldError` trực tiếp ra response nếu chưa kiểm soát nội dung. Chọn field và error code được phép hiển thị:

```java
for (FieldError error : bindingResult.getFieldErrors()) {
    String field = error.getField();
    String code = error.getCode();

    // Map field/code sang thông báo đã được ứng dụng định nghĩa.
    // Không log hoặc trả error.getRejectedValue() một cách mặc định.
}
```

Với field nhạy cảm, chỉ trả thông báo chung như “Giá trị không hợp lệ”. Không echo giá trị đã gửi ngay cả khi nó bị từ chối.

## 8. Dùng thông báo API an toàn

Đối với API, trả mã lỗi ổn định và nội dung chung. Ứng dụng dùng Spring Framework 6 trở lên có thể dùng `ProblemDetail` để chuẩn hóa response:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "The supplied rule is invalid.");
problem.setProperty("code", "RULE_INVALID");
problem.setProperty("correlationId", correlationId);
return problem;
```

Với lỗi nội bộ khi đánh giá một rule đã được cấu hình bởi ứng dụng, response thường nên là lỗi xử lý chung (ví dụ HTTP 500) với mã lỗi ổn định. Không nên trả lỗi 400 cho mọi `EvaluationException`, vì nguyên nhân có thể là lỗi cấu hình hoặc lỗi trong code/server chứ không phải dữ liệu client.

Chỉ đưa correlation ID vào response khi hệ thống hỗ trợ tra cứu an toàn theo ID đó. Correlation ID không được chứa thông tin cá nhân hoặc secret.

## 9. Không nuốt lỗi và không dùng fallback nguy hiểm

Tránh các mẫu xử lý sau:

```java
try {
    return expression.getValue(context, Boolean.class);
}
catch (Exception ex) {
    return true; // Không an toàn cho rule quyết định quyền.
}
```

Không trả `true`, `0`, empty collection hoặc một object mặc định tùy tiện khi expression thất bại. Các fallback đó có thể làm lỗi kỹ thuật bị hiểu thành kết quả nghiệp vụ hợp lệ.

Thay vào đó:

- Dùng kiểu kết quả có trạng thái `SUCCESS` hoặc `ERROR` riêng.
- Với authorization, áp dụng fail-closed: không cho phép hành động nếu rule không thể đánh giá.
- Với tính toán tài chính hoặc dữ liệu quan trọng, dừng luồng xử lý và yêu cầu xử lý lỗi rõ ràng.
- Chỉ dùng default khi default đó là một quy tắc nghiệp vụ đã được xác định, không phải cách che exception.
- Không bắt `Exception` quá rộng nếu có thể phân loại `ParseException`, `EvaluationException` và lỗi nghiệp vụ riêng.

## 10. Kiểm soát dữ liệu nhạy cảm trong context

Thông tin có thể bị lộ không chỉ nằm trong source expression. Root object, variables, bean method và property accessors đều có thể đưa dữ liệu nhạy cảm vào quá trình đánh giá.

Thực hành nên áp dụng:

- Tạo DTO/view object chỉ chứa property mà expression cần.
- Không đưa password, credential, access token, secret key hoặc toàn bộ entity vào root object.
- Chỉ đăng ký variables cần thiết; tránh truyền nguyên request/session/security context nếu không cần.
- Không expose bean có method trả về secret hoặc dump toàn bộ cấu hình.
- Tránh getter hoặc method có thể tạo message chứa dữ liệu nhạy cảm khi thất bại.
- Giới hạn quyền đọc log và thời gian lưu diagnostic.

Đặc biệt, không dùng `toString()` của root object hoặc argument làm nội dung log. `toString()` có thể in ra field nhạy cảm hoặc thay đổi theo implementation.

## 11. Giới hạn thông tin lỗi theo môi trường

Thông tin hiển thị cho người dùng cuối và thông tin dành cho developer có thể khác nhau, nhưng cả hai đều cần policy rõ ràng:

| Kênh | Nên chứa | Không nên chứa |
| --- | --- | --- |
| UI/client response | Mã lỗi, thông báo đã chuẩn hóa, correlation ID nếu cần. | Stack trace, expression source, classpath, secret, SQL hoặc file path. |
| Application log | Rule ID/version, correlation ID, error category, component. | Raw input, toàn bộ context, credential hoặc rejected value. |
| Restricted diagnostic store | Chi tiết kỹ thuật cần cho điều tra, đã redact và có kiểm soát truy cập. | Secret không cần thiết hoặc dữ liệu không có retention policy. |
| Metrics/tracing tags | Error category và tên operation có cardinality thấp. | User input, raw expression, token hoặc giá trị cá nhân làm label. |

Không chuyển toàn bộ exception message vào tracing span hoặc metric tag. Các hệ thống observability thường được nhiều nhóm truy cập và có thời gian lưu dài.

## 12. Kiểm thử để chắc chắn thông báo không làm lộ dữ liệu

Kiểm thử nên xác minh cả response lẫn log, không chỉ xác minh exception được bắt:

1. Tạo input chứa một chuỗi sentinel bí mật, ví dụ `SECRET_TEST_92A7`.
2. Làm expression parse hoặc evaluation thất bại bằng input đó.
3. Kiểm tra response không chứa sentinel, raw expression, stack trace hoặc rejected value.
4. Kiểm tra log mặc định chỉ có rule ID, correlation ID và error category.
5. Kiểm tra cause chain không bị ghi vào log công khai hoặc sink có quyền truy cập rộng.
6. Kiểm tra lỗi evaluation không được chuyển thành kết quả allow/true.
7. Kiểm tra lỗi nghiệp vụ false được phân biệt với lỗi không thể evaluate.
8. Kiểm tra lỗi validation không echo dữ liệu từ field nhạy cảm.

Ví dụ assertion ở mức ý tưởng:

```java
assertThat(responseBody).doesNotContain("SECRET_TEST_92A7");
assertThat(responseBody).doesNotContain("SpelEvaluationException");
assertThat(responseBody).doesNotContain("at org.springframework");
assertThat(result.status()).isEqualTo(RuleStatus.ERROR);
```

Trong test thực tế, kiểm tra logger bằng appender test hoặc log capture của dự án. Dùng dữ liệu sentinel giả, không dùng secret production.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| API trả về chi tiết `SpelEvaluationException` | Exception message được serialize trực tiếp. | Map sang mã lỗi và thông báo đã chuẩn hóa; giữ diagnostic ở kênh nội bộ. |
| Log chứa raw expression | Logger ghi source expression để tiện debug. | Log rule ID/version hoặc fingerprint theo policy, không log source. |
| Stack trace làm lộ URL hoặc SQL | Cause chain đến từ HTTP/JDBC/ORM. | Không ghi exception đầy đủ vào log rộng; dùng sink hạn chế và redact. |
| Password xuất hiện trong lỗi binding | `rejectedValue` được log hoặc serialize. | Chỉ dùng field/error code; không echo rejected value của field nhạy cảm. |
| Evaluation error bị hiểu là kết quả false | Exception bị catch rồi thay bằng Boolean mặc định. | Dùng trạng thái lỗi riêng; fail-closed cho quyết định quyền. |
| Lỗi server bị trả thành HTTP 400 | Mọi lỗi SpEL bị xem là input client sai. | Phân biệt lỗi source do client, lỗi cấu hình và lỗi nội bộ; chọn status phù hợp. |
| Log/metric chứa dữ liệu có cardinality cao | Dùng user input hoặc expression làm tag. | Chỉ dùng category/operation ổn định; bỏ dữ liệu tùy ý khỏi label. |
| Diagnostic quá ít để điều tra | Chỉ trả thông báo chung và không lưu metadata nội bộ. | Ghi rule ID/version, correlation ID và category trong log có kiểm soát. |

## Ghi nhớ

- Parse errors, evaluation errors và business results là ba trạng thái khác nhau; không gộp lỗi thành `false`.
- Không trả `exception.getMessage()`, stack trace, source expression hoặc cause chain cho client.
- Dùng error code ổn định và thông báo đã chuẩn hóa; thêm correlation ID khi cần tra cứu.
- Log rule ID/version, correlation ID và error category; tránh raw expression, root object, variables, arguments và rejected values.
- Cause chain từ HTTP, JDBC, ORM hoặc method được gọi có thể chứa URL, SQL, file path hoặc dữ liệu đầu vào.
- Không log `FieldError.getRejectedValue()` hoặc `toString()` của object có dữ liệu nhạy cảm.
- Dùng DTO/view object và chỉ đưa dữ liệu cần thiết vào EvaluationContext.
- Không biến evaluation failure thành `true`, `0` hoặc kết quả mặc định tùy tiện; dùng trạng thái ERROR riêng.
- Với authorization, lỗi đánh giá phải fail-closed và được phân biệt với quyết định deny hợp lệ.
- Kiểm thử response và log bằng sentinel giả để chứng minh secret không bị echo.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — ParseException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParseException.html)
- [Spring Framework API — EvaluationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationException.html)
- [Spring Framework API — SpelParseException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelParseException.html)
- [Spring Framework API — SpelEvaluationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelEvaluationException.html)
- [Spring Framework API — BindingResult](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework Reference — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)