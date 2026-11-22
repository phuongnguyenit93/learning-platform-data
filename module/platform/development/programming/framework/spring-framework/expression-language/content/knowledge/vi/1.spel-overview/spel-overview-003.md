# Đặt Spring Expression Language bên cạnh Java code, placeholder cấu hình và template expression

## 1. Bốn cách biểu đạt, bốn vai trò

Trong Spring, cùng một giá trị có thể được tạo ra hoặc chèn vào ứng dụng bằng Java code, property placeholder, Spring Expression Language (SpEL) hoặc template expression. Chúng có thể xuất hiện cạnh nhau, nhưng không cùng một loại cơ chế:

- **Java code** thực thi logic đã được biên dịch. Ta gọi method, truy cập object và tính toán bằng cú pháp Java.
- **Property placeholder** `${...}` tra cứu một giá trị cấu hình theo key từ Environment hoặc property sources. Nó chủ yếu thay thế key bằng giá trị.
- **SpEL** là ngôn ngữ biểu thức được Spring phân tích và đánh giá lúc chạy. Nó có thể đọc property, gọi method, truy cập collection và tính toán trên object trong một evaluation context.
- **Template expression** ghép văn bản cố định với một hoặc nhiều biểu thức được đánh giá. Với SpEL, parser dùng template context để nhận diện phần nằm giữa cặp dấu phân cách, mặc định là `#{` và `}`.

Điểm dễ nhầm nhất là `${...}` và `#{...}`: dấu đầu tiên thường có nghĩa “lấy giá trị cấu hình theo tên”; dấu thứ hai có nghĩa “đánh giá biểu thức SpEL”. Cả hai có thể được dùng trong cấu hình Spring, nhưng chúng giải quyết hai bài toán khác nhau.

## 2. Java code: logic tường minh và được biên dịch

Giả sử ứng dụng có cấu hình số lần thử lại và cần nhân đôi giá trị đó, nhưng kết quả tối thiểu phải là 1:

```java
int configuredRetries = properties.getRetryCount();
int effectiveRetries = Math.max(configuredRetries * 2, 1);
```

Đây là Java thuần. Compiler kiểm tra cú pháp và kiểu dữ liệu; IDE có thể hỗ trợ rename, navigation và refactor; logic có thể được gọi từ bất kỳ vị trí Java phù hợp nào. Người đọc thấy rõ dữ liệu đi vào từ đâu và phép tính được thực hiện như thế nào.

Java code thường là lựa chọn tốt khi logic là một phần của hành vi nghiệp vụ, cần nhiều nhánh, cần kiểm thử trực tiếp hoặc cần kiểm soát kiểu dữ liệu chặt chẽ. Đưa một phép tính dài hoặc quy tắc nghiệp vụ phức tạp vào chuỗi SpEL thường làm code khó tìm, khó refactor và khó debug hơn.

## 3. Property placeholder: thay thế giá trị cấu hình

Một file `application.properties` có thể chứa:

```properties
app.name=Order Service
app.retry-count=3
app.timeout-ms=2500
```

Spring có thể đưa các giá trị này vào bean bằng placeholder:

```java
@Component
class RetrySettings {
    private final int retryCount;
    private final long timeoutMs;

    RetrySettings(
            @Value("${app.retry-count}") int retryCount,
            @Value("${app.timeout-ms}") long timeoutMs) {
        this.retryCount = retryCount;
        this.timeoutMs = timeoutMs;
    }
}
```

`@Value("${app.retry-count}")` yêu cầu Spring tìm key `app.retry-count` trong các property sources rồi chuyển giá trị sang kiểu đích nếu có thể. Placeholder có thể khai báo giá trị mặc định:

```java
@Value("${app.retry-count:3}")
private int retryCount;
```

Nếu key không có giá trị, phần sau dấu hai chấm được dùng làm mặc định. Placeholder không phải một ngôn ngữ biểu thức: bản thân `${app.retry-count}` không gọi method, không truy cập `order.customer.name` và không tính `retry-count * 2`. Nó chỉ giải quyết một key cấu hình và trả về giá trị thay thế.

Hãy dùng placeholder khi điều cần làm là đưa cấu hình bên ngoài vào ứng dụng: URL, tên queue, timeout, feature flag, số lần retry hoặc thông tin môi trường. Nếu cần logic dựa trên nhiều object hay phép tính, hãy dùng Java hoặc SpEL tùy vị trí và độ phức tạp.

## 4. SpEL: đánh giá biểu thức trên object lúc chạy

SpEL cho phép biểu đạt thao tác trên object bằng chuỗi biểu thức. Ví dụ, với object đơn hàng có `customer.name` và `total`:

```text
order.customer.name
order.total > 1000000
order.items[0].sku
```

Biểu thức có thể truy cập property lồng nhau, index của array/list/map, so sánh, toán tử logic, toán tử số học và gọi method được phép trong evaluation context. Một số cú pháp thường gặp:

| Cú pháp | Ý nghĩa |
|---|---|
| `customer.name` | Đọc property `name` từ object `customer` |
| `#limit` | Đọc biến tên `limit` trong evaluation context |
| `#root` | Object gốc đang được đánh giá |
| `items[0]` | Truy cập phần tử theo index |
| `total >= 1000` | So sánh giá trị |
| `T(java.lang.Math).max(2, 5)` | Tham chiếu type và gọi static method |
| `@pricingService.taxRate` | Tham chiếu bean theo tên trong context có bean resolver |

Khi dùng parser trực tiếp trong Java, chuỗi truyền vào thường là biểu thức thuần, không cần bọc `#{...}`:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("total * 1.1");

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

BigDecimal amount = expression.getValue(context, BigDecimal.class);
```

Trong ví dụ này, `order` là root object. Vì vậy `total` được hiểu là property của root object. Nếu muốn truy cập biến được đặt tên, dùng tiền tố `#` và đăng ký biến vào context:

```java
Expression expression = parser.parseExpression("#quantity * #unitPrice");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("quantity", 3);
context.setVariable("unitPrice", 12.5);

Double subtotal = expression.getValue(context, Double.class);
```

`ExpressionParser` phân tích chuỗi thành `Expression`; `EvaluationContext` cung cấp root object, variables, property accessors, method resolvers và các khả năng khác để đánh giá biểu thức. Cùng một biểu thức có thể cho kết quả khác nhau khi context hoặc dữ liệu đầu vào khác nhau.

Trong Spring configuration, SpEL thường xuất hiện với dấu `#{...}`, chẳng hạn:

```java
@Value("#{T(java.lang.Math).max(3, 5)}")
private int retryFloor;
```

Ở đây Spring nhận diện phần trong `#{...}` là biểu thức SpEL rồi đánh giá nó để lấy giá trị gán cho field. Dấu `#{...}` là cách đánh dấu biểu thức trong các điểm tích hợp cấu hình của Spring; khi tự gọi `parseExpression("...")`, ta thường truyền biểu thức bên trong.

## 5. Đặt cạnh nhau trong cùng một ví dụ

Giả sử `app.retry-count=3`. Có ba cách để nhận hoặc biến đổi giá trị:

**Chỉ lấy cấu hình bằng placeholder:**

```java
@Value("${app.retry-count:3}")
private int retryCount;
```

Kết quả là số lần retry được cấu hình, hoặc mặc định bằng 3. Không có phép tính nào được thực hiện bởi placeholder.

**Tính toán bằng SpEL:**

```java
@Value("#{T(java.lang.Math).max(${app.retry-count:3} * 2, 1)}")
private int effectiveRetries;
```

Spring thay placeholder bằng giá trị cấu hình, sau đó biểu thức SpEL thực hiện phép nhân và gọi `Math.max`. Ví dụ này cho thấy hai cơ chế có thể phối hợp: placeholder cung cấp đầu vào cấu hình, SpEL đánh giá biểu thức trên đầu vào đó. Giá trị cấu hình phải phù hợp với biểu thức; nếu đặt một chuỗi không phải số vào `app.retry-count`, phép nhân sẽ không đánh giá được.

**Tính toán bằng Java:**

```java
int effectiveRetries = Math.max(retrySettings.getRetryCount() * 2, 1);
```

Kết quả có thể tương đương, nhưng logic nằm trong Java và được compiler kiểm tra theo kiểu dữ liệu. Khi quy tắc bắt đầu có nhiều điều kiện, nhiều bước hoặc cần test như hành vi nghiệp vụ, Java thường dễ bảo trì hơn.

## 6. Template expression: trộn văn bản với SpEL

Một biểu thức SpEL thông thường trả về kết quả của toàn bộ biểu thức. Template expression hữu ích khi ta cần tạo một chuỗi có cả văn bản cố định lẫn giá trị động, ví dụ thông báo:

```text
Đơn hàng #{#order.code} của #{#order.customer.name} có tổng tiền #{#order.total}
```

Để parser hiểu văn bản bên ngoài là phần cố định và chỉ đánh giá các đoạn nằm trong `#{...}`, hãy dùng `TemplateParserContext`:

```java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression expression = parser.parseExpression(
        "Đơn hàng #{#order.code} của #{#order.customer.name} "
                + "có tổng tiền #{#order.total}",
        templateContext);

StandardEvaluationContext evaluationContext =
        new StandardEvaluationContext();
evaluationContext.setVariable("order", order);

String message = expression.getValue(
        evaluationContext, String.class);
```

`TemplateParserContext` mặc định dùng `#{` làm prefix và `}` làm suffix. Parser giữ nguyên phần văn bản ngoài các đoạn biểu thức, đánh giá từng đoạn SpEL rồi ghép kết quả thành chuỗi. Ta có thể tạo parser context với prefix/suffix khác nếu định dạng của ứng dụng yêu cầu.

Phân biệt hai cách gọi:

- `parseExpression("order.total")`: toàn bộ chuỗi là một biểu thức SpEL.
- `parseExpression("Tổng tiền: #{order.total}", new TemplateParserContext())`: chuỗi là template, chỉ phần nằm trong dấu phân cách được đánh giá.

Template expression phù hợp cho nội dung có cấu trúc tương đối ổn định nhưng cần chèn dữ liệu động, như thông báo, nhãn hoặc đoạn mô tả. Nếu chuỗi chỉ là một giá trị cấu hình đơn giản, placeholder thường đủ. Nếu nội dung cần bản địa hóa, định dạng số/ngày tháng hoặc quy tắc hiển thị phức tạp, hãy cân nhắc cơ chế message/template chuyên dụng thay vì dồn mọi thứ vào một biểu thức dài.

## 7. So sánh nhanh

| Tiêu chí | Java code | Property placeholder `${...}` | SpEL `#{...}` | SpEL template expression |
|---|---|---|---|---|
| Mục đích | Thực thi logic ứng dụng | Lấy giá trị cấu hình theo key | Đánh giá biểu thức trên dữ liệu/context | Tạo chuỗi từ văn bản và biểu thức |
| Thời điểm | Khi chương trình chạy; code đã biên dịch | Khi Spring resolve cấu hình/giá trị bean | Khi Spring hoặc ứng dụng đánh giá biểu thức | Khi parser đánh giá template |
| Kiểu dữ liệu | Kiểu Java rõ ràng | Thường bắt đầu từ giá trị cấu hình dạng chuỗi rồi được chuyển đổi | Có thể trả về nhiều kiểu tùy biểu thức | Thường dùng để tạo chuỗi |
| Truy cập object | Qua biến, field, method Java | Không tự truy cập object | Có, tùy evaluation context | Có, bên trong từng đoạn SpEL |
| Tính toán | Có | Không phải chức năng của placeholder | Có | Có trong các đoạn SpEL |
| Refactor/kiểm tra kiểu | Hỗ trợ tốt bởi compiler và IDE | Key cấu hình cần quản lý riêng | Chuỗi động nên ít hỗ trợ refactor/kiểu hơn | Tương tự SpEL |
| Nơi thường gặp | Service, domain, helper, configuration class | `@Value`, cấu hình Spring | `@Value`, bean definition, rule hoặc API dùng SpEL | Nội dung chuỗi cần chèn giá trị động |

## 8. Chọn đúng công cụ

Có thể quyết định theo câu hỏi đang cần trả lời:

1. **“Giá trị cấu hình của key này là gì?”** Dùng `${...}`. Ví dụ: `@Value("${app.api-url}")`.
2. **“Tôi cần tính hoặc đọc dữ liệu từ object trong một điểm cấu hình hỗ trợ expression.”** Dùng SpEL. Ví dụ: `@Value("#{systemProperties['user.timezone']}")`.
3. **“Tôi cần một chuỗi cố định có chèn dữ liệu động.”** Dùng template expression. Ví dụ: `"Hello #{#customer.name}"` cùng `TemplateParserContext`.
4. **“Đây là quy tắc nghiệp vụ hoặc logic có nhiều bước.”** Viết Java code, đặt logic ở class/method có tên rõ ràng và kiểm thử như code thông thường.

Một quy tắc thực tế: cấu hình nên mô tả giá trị; biểu thức nên ngắn và dễ đọc; logic nghiệp vụ nên có tên và vị trí rõ ràng trong Java. SpEL rất tiện tại ranh giới cấu hình hoặc khi cần đánh giá dữ liệu động, nhưng không nên biến chuỗi expression thành nơi chứa toàn bộ hành vi của ứng dụng.

## 9. Các nhầm lẫn thường gặp

- **Dùng nhầm dấu:** `${app.name}` là placeholder; `#{...}` là dấu đánh dấu SpEL trong Spring configuration. Hai cú pháp không thể thay thế tùy ý cho nhau.
- **Quên context:** `#order` chỉ hoạt động nếu biến `order` được đưa vào evaluation context. `order.total` chỉ hoạt động nếu root object hoặc context có thể phân giải tên đó.
- **Nhầm raw expression với template:** parser mặc định hiểu toàn bộ chuỗi là biểu thức. Muốn giữ văn bản bên ngoài và đánh giá các đoạn `#{...}`, phải dùng template parser context.
- **Kỳ vọng placeholder tính toán:** `${app.a * 2}` không phải biểu thức nhân. Hãy đưa giá trị vào SpEL hoặc tính trong Java.
- **Giấu logic quá dài trong annotation:** biểu thức nhiều tầng làm cấu hình khó đọc và khó kiểm thử. Chuyển logic phức tạp sang method Java có tên mô tả mục đích.
- **Đánh giá expression không đáng tin cậy:** `StandardEvaluationContext` có thể cung cấp quyền truy cập property, method và type tùy cấu hình. Không nên đánh giá chuỗi SpEL do người dùng không tin cậy gửi lên. Với nhu cầu data binding giới hạn, cân nhắc `SimpleEvaluationContext` và chỉ bật các khả năng thực sự cần thiết.

## 10. Ghi nhớ

- Java code là lựa chọn mặc định cho logic ứng dụng có cấu trúc và cần kiểm soát kiểu.
- `${...}` lấy giá trị từ cấu hình theo key.
- SpEL đánh giá biểu thức trên root object, variables và các thành phần được cấp trong evaluation context.
- `#{...}` là cách Spring configuration đánh dấu đoạn SpEL; API parser thường nhận biểu thức thuần.
- Template expression giữ văn bản cố định và đánh giá những đoạn SpEL nằm giữa prefix/suffix.
- Có thể kết hợp placeholder và SpEL: placeholder đưa giá trị cấu hình vào, SpEL thực hiện phép tính hoặc truy cập dữ liệu.
