# Thiết kế fallback rõ ràng thay vì nuốt lỗi expression trong SpEL

## 1. Vì sao không nên nuốt lỗi expression?

Spring Expression Language (SpEL) cho phép đọc property, gọi method, tính toán, truy cập collection và kết hợp nhiều điều kiện. Khi expression không đánh giá được, ứng dụng cần quyết định rõ: đây là dữ liệu tùy chọn có thể dùng giá trị thay thế, hay là lỗi cấu hình/lỗi chương trình cần được báo lên.

Một cách xử lý nguy hiểm là bắt mọi exception rồi trả về một giá trị mặc định:

```java
try {
    return expression.getValue(context, root, Boolean.class);
}
catch (Exception ex) {
    return false;
}
```

Đoạn code này làm mất nguyên nhân thật của lỗi. Một expression viết sai, property bị đổi tên, converter bị thiếu, method phát sinh lỗi hoặc dữ liệu không đúng kiểu đều có thể bị biến thành `false`. Ứng dụng tiếp tục chạy nhưng kết quả nghiệp vụ có thể sai mà không ai nhận ra.

Một fallback tốt cần trả lời được bốn câu hỏi:

1. Trường hợp nào được phép dùng fallback?
2. Giá trị fallback có đúng kiểu và an toàn cho nghiệp vụ không?
3. Lỗi gốc có được ghi nhận và theo dõi không?
4. Trường hợp nào phải dừng xử lý và truyền lỗi lên caller?

Không phải mọi lỗi expression đều là tình huống có thể phục hồi. Chỉ dùng fallback cho trường hợp đã được xác định trước, chẳng hạn dữ liệu tùy chọn bị thiếu hoặc một giá trị có thể null theo hợp đồng dữ liệu.

## 2. Tách parse error khỏi evaluation error

SpEL có hai giai đoạn riêng:

- Parse: `ExpressionParser.parseExpression(source)` phân tích cú pháp và tạo Expression.
- Evaluation: `Expression.getValue(...)` thực thi expression trên EvaluationContext và root object.

Ví dụ:

```java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("customer.age >= 18");

Boolean allowed =
        expression.getValue(customer, Boolean.class);
```

Nếu source sai cú pháp, lỗi xảy ra ở bước parse. Nếu expression đúng cú pháp nhưng property `age` không tồn tại trên object, lỗi xảy ra ở bước evaluation.

| Giai đoạn | Nhóm exception thường gặp | Ví dụ nguyên nhân |
|---|---|---|
| Parse | `ParseException`, thường là `SpelParseException` | Thiếu dấu ngoặc, quote không đóng, toán tử sai vị trí. |
| Evaluation | `EvaluationException`, thường là `SpelEvaluationException` | Property không tồn tại, gọi method không phù hợp, lỗi chuyển đổi hoặc lỗi trong phép toán. |

Nếu expression đến từ cấu hình cố định, nên parse và kiểm tra ngay khi ứng dụng khởi động. Một lỗi cú pháp trong cấu hình thường là lỗi triển khai; không nên đợi đến lúc một request chạy qua mới thay bằng giá trị mặc định.

Với expression do administrator cập nhật, hãy parse trước khi chấp nhận bản cấu hình mới. Chỉ đưa expression đã parse thành công vào luồng sử dụng. Giữ lại bản cấu hình đang hoạt động nếu bản mới không hợp lệ và thông báo rõ lỗi cho người quản trị.

## 3. Dùng Elvis operator cho giá trị null hoặc chuỗi rỗng

SpEL hỗ trợ Elvis operator `?:` để chọn giá trị thay thế khi vế trái là null. Với String, chuỗi rỗng cũng được xem như không có giá trị.

Ví dụ:

```text
customer.nickname ?: 'Guest'
```

Nếu `nickname` là null hoặc chuỗi rỗng, kết quả là `'Guest'`. Nếu nickname có giá trị, SpEL giữ giá trị đó.

Có thể kết hợp với safe navigation:

```text
customer?.profile?.displayName ?: 'Guest'
```

Trong ví dụ, nếu `customer`, `profile` hoặc `displayName` không có giá trị do object trung gian null, biểu thức có thể trả về fallback `'Guest'`.

Elvis operator phù hợp cho dữ liệu tùy chọn, ví dụ tên hiển thị, nhãn hoặc mô tả không bắt buộc. Nó không phải cơ chế bắt exception.

Các trường hợp sau vẫn có thể phát sinh lỗi:

- Property `nickname` không tồn tại.
- Property có getter ném exception.
- Method được gọi ở vế trái phát sinh exception.
- Expression có cú pháp không hợp lệ.
- Kết quả không thể chuyển sang kiểu đích mà caller yêu cầu.

Ví dụ `unknownProperty ?: 'Guest'` không bảo đảm trả về Guest. Nếu `unknownProperty` không tồn tại trên object, SpEL không thể đọc vế trái để áp dụng Elvis.

## 4. Safe navigation xử lý null, không xử lý exception

Toán tử safe navigation `?.` dừng truy cập property hoặc gọi method khi object ngay trước toán tử là null và trả về null.

Ví dụ:

```text
customer?.address?.city
```

Nếu customer null, SpEL không cố đọc address. Nếu address null, SpEL không cố đọc city. Kết quả của đoạn truy cập an toàn là null.

Có thể dùng cùng Elvis để tạo giá trị mặc định:

```text
customer?.address?.city ?: 'Unknown city'
```

Nhưng safe navigation không bắt lỗi do getter hoặc method ném ra:

```text
customer?.loadProfile()?.displayName
```

Nếu customer khác null nhưng `loadProfile()` ném exception, exception vẫn được truyền ra. Safe navigation chỉ kiểm tra null của object nhận lời gọi.

Với chuỗi truy cập nhiều cấp, hãy đặt `?.` ở mỗi đoạn có thể null. Không giả định một toán tử safe navigation đầu tiên làm toàn bộ expression phía sau an toàn.

## 5. Fallback cho dữ liệu tùy chọn và fallback cho lỗi là hai việc khác nhau

Hãy phân biệt các trường hợp:

| Tình huống | Cơ chế phù hợp |
|---|---|
| Property tồn tại nhưng có giá trị null | Safe navigation hoặc Elvis. |
| String tùy chọn là chuỗi rỗng | Elvis operator. |
| Property không tồn tại hoặc sai tên | Sửa expression/model; không dùng Elvis để che lỗi. |
| Expression sai cú pháp | Báo lỗi cấu hình ở giai đoạn parse. |
| Giá trị không chuyển được sang kiểu đích | Xác định lỗi dữ liệu/conversion và xử lý riêng. |
| Method được gọi ném exception | Chẩn đoán method và quyết định có được phục hồi theo hợp đồng hay không. |
| Dịch vụ bên ngoài tạm thời không khả dụng | Dùng retry/timeout/circuit breaker hoặc fallback của tầng dịch vụ, không giả định Elvis xử lý được. |

Ví dụ, một nhãn giao diện có thể dùng fallback khi thiếu:

```java
String label = parser.parseExpression(
        "customer?.profile?.displayName ?: 'Guest'")
        .getValue(context, customer, String.class);
```

Ngược lại, với điều kiện quyết định quyền truy cập hoặc tính phí, thiếu property hoặc lỗi evaluation thường phải được xem là lỗi cần xử lý rõ ràng. Không tự động đổi thành kết quả cho phép hoặc số tiền bằng 0.

## 6. Thiết kế wrapper để giữ nguyên nguyên nhân lỗi

Một lớp wrapper có thể thêm ngữ cảnh nghiệp vụ vào lỗi SpEL mà vẫn giữ exception gốc làm cause.

Ví dụ:

```java
public class RuleEvaluationException extends RuntimeException {

    private final String ruleId;

    public RuleEvaluationException(
            String ruleId,
            String message,
            Throwable cause) {
        super(message, cause);
        this.ruleId = ruleId;
    }

    public String getRuleId() {
        return ruleId;
    }
}
```

Parse expression khi nạp rule:

```java
public Expression parseRule(
        String ruleId,
        String source,
        ExpressionParser parser) {

    try {
        return parser.parseExpression(source);
    }
    catch (ParseException ex) {
        throw new IllegalArgumentException(
                "Invalid SpEL rule: " + ruleId, ex);
    }
}
```

Đánh giá expression:

```java
public <T> T evaluateRule(
        String ruleId,
        Expression expression,
        EvaluationContext context,
        Object root,
        Class<T> targetType) {

    try {
        return expression.getValue(context, root, targetType);
    }
    catch (EvaluationException ex) {
        throw new RuleEvaluationException(
                ruleId,
                "Could not evaluate SpEL rule: " + ruleId,
                ex);
    }
}
```

Caller có thể phân biệt rule nào thất bại và vẫn truy cập nguyên nhân gốc qua `getCause()`. Wrapper không biến lỗi thành một giá trị giả; nó làm lỗi dễ định vị và xử lý hơn.

Tùy ứng dụng, có thể bổ sung rule version, tenant, correlation ID hoặc tên operation. Không đưa toàn bộ expression hay dữ liệu nhạy cảm vào thông báo lỗi trả về client.

## 7. Khi nào được phép fallback sau EvaluationException?

Một số hệ thống có hợp đồng rõ ràng cho phép fallback nếu một điều kiện cụ thể không thể đánh giá, ví dụ một nhãn tùy chọn được tính từ dữ liệu không bắt buộc. Trong trường hợp đó, phải phân loại lỗi có thể phục hồi thay vì bắt tất cả exception.

Có thể tách chính sách fallback khỏi code đánh giá:

```java
public <T> T evaluateOptionalRule(
        String ruleId,
        Expression expression,
        EvaluationContext context,
        Object root,
        Class<T> targetType,
        T fallbackValue,
        Predicate<EvaluationException> recoverable) {

    try {
        return expression.getValue(context, root, targetType);
    }
    catch (EvaluationException ex) {
        if (!recoverable.test(ex)) {
            throw new RuleEvaluationException(
                    ruleId,
                    "Could not evaluate rule: " + ruleId,
                    ex);
        }

        log.warn(
                "Using fallback for optional rule {}",
                ruleId,
                ex);

        return fallbackValue;
    }
}
```

`recoverable` phải là chính sách do ứng dụng định nghĩa dựa trên loại lỗi hoặc điều kiện đã được cho phép. Không đặt nó thành `ex -> true`, vì như vậy mọi lỗi evaluation đều bị nuốt.

Nếu phiên bản Spring cung cấp mã lỗi SpEL phù hợp, có thể dùng mã lỗi đó để phân loại. Tuy nhiên, nên kiểm tra mã lỗi và hành vi của phiên bản đang dùng; không dựa vào việc phân tích chuỗi message để quyết định lỗi có thể phục hồi.

Giá trị fallback phải tương thích với `targetType`. Nếu target type là Boolean, fallback phải là Boolean; nếu target type là BigDecimal, fallback phải là một BigDecimal có ý nghĩa nghiệp vụ. Tránh ép một giá trị mặc định tùy tiện qua conversion để làm biến mất lỗi.

## 8. Không dùng fallback permissive cho quyết định nhạy cảm

Fallback cần phù hợp với hậu quả của quyết định:

| Ngữ cảnh | Ví dụ fallback có thể phù hợp | Cần tránh |
|---|---|---|
| Nhãn hiển thị | `"Guest"`, `"Unknown"` | Làm mất lỗi cấu hình tên property mà không ghi nhận. |
| Mô tả tùy chọn | Chuỗi rỗng hoặc thông điệp chung đã thống nhất. | Trả về dữ liệu cũ mà không cho biết dữ liệu đã stale. |
| Feature flag không quan trọng | Giá trị mặc định đã được phê duyệt và ghi log. | Mặc định bật tính năng nhạy cảm khi rule lỗi. |
| Authorization | Từ chối hoặc dừng quyết định theo chính sách fail-closed. | Trả về `true` khi expression lỗi. |
| Pricing/billing | Dừng giao dịch và yêu cầu xử lý lỗi. | Trả về 0 hoặc mức giá mặc định không có căn cứ. |
| Quy tắc giới hạn/risk | Dừng hoặc áp dụng hành động bảo vệ đã định nghĩa. | Bỏ qua kiểm tra vì expression không đánh giá được. |

Với bảo mật và tiền tệ, “fail closed” thường an toàn hơn “fail open”. Tuy nhiên, hành vi cụ thể phải được xác định bởi nghiệp vụ; không nên tự chọn một default cho mọi hệ thống.

## 9. Property placeholder và Elvis operator không giống nhau

Trong Spring configuration có thể gặp hai cơ chế:

- Property placeholder lấy giá trị từ cấu hình bên ngoài và có thể khai báo default value khi property không tồn tại.
- SpEL Elvis operator chọn giá trị thay thế khi kết quả expression là null hoặc String rỗng.

Ví dụ property placeholder trong annotation:

```java
@Value("${app.display-name:Guest}")
private String displayName;
```

Ví dụ SpEL Elvis trong annotation:

```java
@Value("#{systemProperties['user.region'] ?: 'unknown'}")
private String region;
```

Placeholder không bắt lỗi SpEL evaluation. Elvis cũng không xử lý lỗi phân giải bean hoặc property path. Hãy dùng đúng cơ chế cho nguồn giá trị tương ứng.

Nếu property cấu hình bắt buộc phải có, không nên đặt default tùy tiện. Hãy để ứng dụng fail fast khi thiếu cấu hình để lỗi triển khai được phát hiện sớm.

## 10. Phân loại và ghi log lỗi một cách hữu ích

Khi expression thất bại, log cần đủ thông tin để tìm ra rule và giai đoạn lỗi, nhưng không tiết lộ dữ liệu nhạy cảm.

Thông tin thường hữu ích:

- Rule ID hoặc tên cấu hình.
- Version của rule.
- Giai đoạn parse hay evaluation.
- Loại exception và mã lỗi nếu có.
- Correlation ID hoặc request ID.
- Thời gian đánh giá và loại operation.
- Fallback có được dùng hay không và theo policy nào.

Ví dụ:

```java
try {
    return expression.getValue(context, root, Boolean.class);
}
catch (EvaluationException ex) {
    log.error(
            "SpEL evaluation failed: ruleId={}, errorType={}",
            ruleId,
            ex.getClass().getSimpleName(),
            ex);

    throw new RuleEvaluationException(
            ruleId,
            "Rule evaluation failed",
            ex);
}
```

Không log password, token, dữ liệu cá nhân, toàn bộ root object hoặc rejected value nhạy cảm. Nếu expression chứa bí mật hoặc thông tin tenant, hãy dùng ID/phiên bản đã kiểm soát thay vì ghi nguyên văn source.

Nếu có fallback hợp lệ, log rõ fallback đã được áp dụng. Nên có metric riêng cho số lần fallback, số parse failure và số evaluation failure để phát hiện cấu hình hỏng hoặc dữ liệu bất thường.

## 11. Không retry expression một cách mù quáng

Retry có ý nghĩa với lỗi tạm thời của một dịch vụ bên ngoài nếu thao tác có thể retry an toàn. Nhưng nhiều lỗi SpEL là lỗi xác định:

- Cú pháp sai sẽ không tự đúng khi thử lại.
- Property không tồn tại sẽ tiếp tục không tồn tại.
- Kiểu dữ liệu không phù hợp thường vẫn không phù hợp.
- Converter chưa được đăng ký sẽ không tự xuất hiện.

Nếu expression gọi method có side effect, retry có thể thực hiện hành động hai lần. Chỉ retry khi biết lỗi có tính tạm thời, method có thể lặp an toàn (idempotent) và có giới hạn số lần/thời gian.

Đối với lỗi parse, sửa source/configuration rồi parse lại. Đối với lỗi evaluation do dữ liệu, xác thực hoặc sửa dữ liệu. Đối với lỗi dịch vụ ngoài, dùng cơ chế resilience ở tầng service thay vì retry toàn bộ expression mà không kiểm soát.

## 12. Kiểm thử fallback và đường lỗi

Test cần chứng minh cả hai hành vi: fallback chỉ chạy trong tình huống được phép, còn lỗi không được phép phục hồi phải được truyền lên.

Các trường hợp nên có:

1. Property null: Elvis trả về default.
2. String rỗng: Elvis trả về default.
3. Property có giá trị: kết quả gốc được giữ.
4. Object trung gian null: safe navigation trả về null để Elvis chọn default.
5. Property không tồn tại: evaluation thất bại, không bị coi là null.
6. Expression sai cú pháp: parse thất bại trước khi evaluation.
7. Method ném exception: exception được ghi nhận/truyền lên theo policy.
8. Conversion thất bại: không thay bằng default nếu chưa có policy rõ ràng.
9. Fallback đúng kiểu đích và có ý nghĩa nghiệp vụ.
10. Log/metric ghi nhận khi fallback được dùng.

Ví dụ JUnit cho Elvis:

```java
@Test
void usesDefaultForNullProperty() {
    StandardEvaluationContext context =
            new StandardEvaluationContext(customerWithNullNickname);

    String value = parser.parseExpression(
            "nickname ?: 'Guest'")
            .getValue(context, String.class);

    assertEquals("Guest", value);
}
```

Ví dụ xác nhận property không tồn tại không bị Elvis che:

```java
@Test
void missingPropertyStillFails() {
    StandardEvaluationContext context =
            new StandardEvaluationContext(customer);

    Expression expression = parser.parseExpression(
            "missingProperty ?: 'Guest'");

    assertThrows(
            EvaluationException.class,
            () -> expression.getValue(context, String.class));
}
```

Tên class và exception cụ thể trong test có thể điều chỉnh theo API/version Spring đang dùng. Điều cần bảo đảm là lỗi property không bị biến thành fallback chỉ vì expression có Elvis operator.

## 13. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Mọi lỗi đều trả về default | Catch quá rộng và không phân loại exception. | Chỉ fallback cho tình huống được policy cho phép; giữ cause của lỗi còn lại. |
| Elvis không xử lý property sai tên | Elvis chỉ xử lý giá trị null/chuỗi rỗng, không bắt evaluation exception. | Sửa property path hoặc validate expression khi nạp cấu hình. |
| Safe navigation vẫn ném exception | Getter/method được gọi đã tự ném exception. | Chẩn đoán method; safe navigation chỉ xử lý receiver null. |
| Fallback làm sai quyết định nghiệp vụ | Default không phù hợp với kiểu hoặc hậu quả của quyết định. | Định nghĩa fallback theo từng rule và dùng fail-closed khi cần. |
| Lỗi cấu hình chỉ xuất hiện lúc request chạy | Expression chưa được parse lúc startup/config update. | Parse và xác thực cấu hình trước khi đưa vào sử dụng. |
| Log không tìm được rule gây lỗi | Chỉ ghi message chung hoặc không có rule ID/version. | Ghi rule ID, version, phase, exception type và correlation ID. |
| Retry làm hành động lặp lại | Method trong expression có side effect. | Không retry mù; chỉ retry operation idempotent có giới hạn. |
| Fallback trả sai kiểu | Giá trị mặc định không tương thích target type. | Dùng fallback có kiểu rõ ràng và test target type. |
| Lỗi dữ liệu bị che thành kết quả hợp lệ | Dùng fallback cho conversion/property/method failure không mong muốn. | Tách lỗi dữ liệu, lỗi cấu hình và tình huống optional theo policy. |

## 14. Quy trình thiết kế fallback cho SpEL

1. Xác định expression là cấu hình cố định hay do người dùng/admin cung cấp.
2. Parse expression sớm và từ chối cấu hình sai cú pháp.
3. Xác định property nào được phép null hoặc rỗng theo hợp đồng dữ liệu.
4. Dùng safe navigation và Elvis cho trường hợp null/empty có chủ đích.
5. Không kỳ vọng Elvis hoặc safe navigation bắt exception.
6. Chọn target type rõ ràng khi gọi `getValue()`.
7. Bọc lỗi parse/evaluation bằng exception có rule ID và giữ nguyên cause.
8. Nếu cho phép fallback sau lỗi evaluation, định nghĩa classifier/policy cho các lỗi phục hồi cụ thể.
9. Không fallback permissive cho authorization, pricing, billing hoặc kiểm tra rủi ro.
10. Không retry method có side effect nếu chưa bảo đảm idempotency.
11. Ghi log/metric khi fallback được dùng và bảo vệ dữ liệu nhạy cảm.
12. Test cả null, empty, missing property, invalid syntax, conversion failure và method exception.

## 15. Ghi nhớ

- Không bắt mọi exception rồi trả về một default; cách đó che lỗi cấu hình và lỗi chương trình.
- Parse error và evaluation error xảy ra ở hai giai đoạn khác nhau, cần chẩn đoán riêng.
- Elvis `?:` chọn fallback khi giá trị trái null hoặc String rỗng; nó không bắt exception.
- Safe navigation `?.` xử lý receiver null; nó không bắt exception từ getter hoặc method.
- Missing property, sai method, conversion failure và syntax error phải được xử lý theo nguyên nhân.
- Bọc exception để thêm rule ID/context nhưng giữ nguyên cause.
- Chỉ fallback sau EvaluationException khi có policy rõ ràng cho loại lỗi đó và fallback đúng kiểu/ngữ nghĩa.
- Quyết định bảo mật, pricing và billing thường cần fail-closed hoặc dừng giao dịch.
- Parse expression trước khi đưa vào sử dụng; log lỗi và metric fallback có kiểm soát.
- Retry chỉ phù hợp với lỗi tạm thời và thao tác idempotent.

## Tài liệu tham khảo

- [Spring Framework Reference — Elvis Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-elvis.html)
- [Spring Framework Reference — Safe Navigation Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operator-safe-navigation.html)
- [Spring Framework Reference — Evaluation and Exception Handling](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [ExpressionParser Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ExpressionParser.html)
- [EvaluationException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationException.html)
- [ParseException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParseException.html)
