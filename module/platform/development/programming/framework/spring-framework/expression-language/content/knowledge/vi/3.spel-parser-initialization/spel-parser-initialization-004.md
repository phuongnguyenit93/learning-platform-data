# TemplateParserContext và phần văn bản bao quanh biểu thức trong SpEL

## Mục tiêu

`SpelExpressionParser` có thể phân tích một biểu thức SpEL độc lập, hoặc phân tích một chuỗi mẫu gồm văn bản thông thường xen kẽ các đoạn SpEL. Trường hợp thứ hai hữu ích khi tạo thông báo, nhãn, nội dung email, câu mô tả hay chuỗi hiển thị có một vài giá trị động.

`TemplateParserContext` cho parser biết chuỗi đầu vào là một template và xác định ký hiệu bắt đầu/kết thúc của từng đoạn biểu thức. Phần nằm ngoài các ký hiệu đó được giữ làm văn bản literal; phần nằm bên trong được phân tích và đánh giá như SpEL bình thường.

## 1. Phân biệt biểu thức SpEL độc lập và template

Khi gọi `parseExpression(expressionString)` mà không truyền `ParserContext`, parser xem toàn bộ chuỗi là một biểu thức SpEL:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("customer.name");
```

Ngược lại, khi truyền `TemplateParserContext`, chuỗi có thể chứa cả văn bản thường và các đoạn biểu thức:

```java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Expression template = parser.parseExpression(
        "Xin chào #{customer.name}, đơn hàng của bạn đã được tiếp nhận!",
        templateContext);
```

Trong ví dụ này, `Xin chào `, `, đơn hàng của bạn đã được tiếp nhận!` là văn bản literal. `customer.name` là đoạn SpEL được đánh giá. Nếu bỏ `templateContext`, parser sẽ cố phân tích cả câu tiếng Việt như một biểu thức SpEL và việc phân tích có thể thất bại.

## 2. Ký hiệu mặc định của TemplateParserContext

Constructor mặc định của `TemplateParserContext` sử dụng:

| Thành phần | Ký hiệu | Vai trò |
| --- | --- | --- |
| Expression prefix | `#{` | Đánh dấu điểm bắt đầu của một đoạn SpEL. |
| Expression suffix | `}` | Đánh dấu điểm kết thúc của đoạn SpEL đó. |

Ví dụ template có nhiều đoạn biểu thức:

```text
Xin chào #{customer.name}, đơn hàng #{order.id} có tổng tiền #{order.total}.
```

Parser xử lý từng phần theo thứ tự:

1. Giữ nguyên `Xin chào `.
2. Đánh giá `customer.name`.
3. Giữ nguyên `, đơn hàng `.
4. Đánh giá `order.id`.
5. Giữ nguyên ` có tổng tiền `.
6. Đánh giá `order.total` rồi giữ nguyên dấu chấm cuối câu.

Khi gọi `getValue`, các phần literal và kết quả của các đoạn biểu thức được ghép thành một chuỗi. Có thể dùng cùng một template nhiều lần và đánh giá nó với context phù hợp ở mỗi lần gọi.

## 3. Ví dụ đầy đủ với root object

Giả sử ứng dụng có `Order` với các property `id`, `customer.name` và `total`. Đặt order làm root object để các property trong từng đoạn `#{...}` được phân giải từ order:

```java
ExpressionParser parser = new SpelExpressionParser();
ParserContext templateContext = new TemplateParserContext();

Order order = orderService.findById(42L);
EvaluationContext evaluationContext = new StandardEvaluationContext(order);

Expression template = parser.parseExpression(
        "Đơn hàng #{id} của #{customer.name} có tổng tiền #{total}.",
        templateContext);

String message = template.getValue(evaluationContext, String.class);
```

Kết quả có dạng như sau (giá trị cụ thể phụ thuộc vào dữ liệu của order):

```text
Đơn hàng 42 của Lan có tổng tiền 1250000.
```

Các đoạn bên trong `#{...}` là biểu thức SpEL độc lập về mặt cú pháp, nên có thể dùng property, phép toán, lời gọi method hoặc các tính năng SpEL khác được evaluation context cho phép. Root object và các biến trong context được dùng chung khi đánh giá những đoạn đó.

## 4. Dùng biến trong template

Có thể đưa dữ liệu thay đổi theo request vào `EvaluationContext` bằng biến, rồi tham chiếu biến bằng dấu `#` bên trong đoạn biểu thức:

```java
ExpressionParser parser = new SpelExpressionParser();
StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("currency", "VND");
context.setVariable("recipient", "Lan");

Expression template = parser.parseExpression(
        "Xin chào #{#recipient}, đơn hàng #{id} có tổng tiền #{total} #{#currency}.",
        new TemplateParserContext());

String message = template.getValue(context, String.class);
```

Ở đây `id` và `total` là property được phân giải từ root object `order`; `#recipient` và `#currency` là biến do ứng dụng đăng ký. Việc dùng template không thay đổi quy tắc phân giải property hay biến của SpEL.

## 5. Tùy chỉnh dấu phân cách

Nếu ký hiệu `#{` và `}` xung đột với nội dung template hoặc quy ước của ứng dụng, hãy truyền prefix và suffix riêng vào constructor:

```java
ParserContext templateContext = new TemplateParserContext("${", "}");

Expression template = parser.parseExpression(
        "Xin chào ${#recipient}, mã đơn hàng là ${id}.",
        templateContext);

String message = template.getValue(context, String.class);
```

Trong trường hợp này, `${` bắt đầu một đoạn biểu thức và `}` kết thúc đoạn đó. Hai tham số là chuỗi delimiter do ứng dụng lựa chọn; cần dùng thống nhất cùng một `ParserContext` khi phân tích template.

`TemplateParserContext` triển khai `ParserContext` và cung cấp ba thông tin chính: đây là template (`isTemplate()` trả về `true`), expression prefix và expression suffix. Nếu cần quy tắc phân tích đặc biệt hơn, ứng dụng có thể tự triển khai `ParserContext`; đa số trường hợp chỉ cần `TemplateParserContext` là đủ.

Khi văn bản literal có chứa chính chuỗi delimiter đã chọn, hãy đổi sang một cặp delimiter khác không xuất hiện trong nội dung. Việc chọn delimiter rõ ràng giúp parser phân biệt phần văn bản với phần biểu thức.

## 6. Template được phân tích và đánh giá ở hai thời điểm

Có hai bước riêng biệt:

1. **Parse:** `parseExpression(templateText, templateContext)` phân tách văn bản literal và các đoạn SpEL, đồng thời kiểm tra cú pháp của các đoạn biểu thức.
2. **Evaluate:** `getValue(evaluationContext, String.class)` thực thi các đoạn SpEL bằng dữ liệu trong context và ghép kết quả với phần văn bản literal.

Có thể parse một template một lần rồi đánh giá nhiều lần với các context khác nhau, miễn là các root object, biến và khả năng truy cập cần thiết đã được cung cấp cho từng lần đánh giá.

Ví dụ:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression template = parser.parseExpression(
        "Hello #{#name}!",
        new TemplateParserContext());

StandardEvaluationContext firstContext = new StandardEvaluationContext();
firstContext.setVariable("name", "An");
String first = template.getValue(firstContext, String.class);

StandardEvaluationContext secondContext = new StandardEvaluationContext();
secondContext.setVariable("name", "Bình");
String second = template.getValue(secondContext, String.class);
```

`first` là `Hello An!`; `second` là `Hello Bình!`. Template đã parse được tái sử dụng, còn giá trị động đến từ context ở mỗi lần đánh giá.

## 7. TemplateParserContext khác SpelParserConfiguration

Hai thành phần này giải quyết hai vấn đề khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `TemplateParserContext` | Cho biết đầu vào là template và xác định prefix/suffix để tách literal text khỏi các đoạn SpEL. |
| `SpelParserConfiguration` | Cấu hình hành vi của parser/engine, chẳng hạn auto-grow collection hoặc auto-grow null references và compiler mode. |

Ví dụ, nếu cần cấu hình parser và đồng thời phân tích template, có thể truyền cấu hình vào `SpelExpressionParser` rồi truyền `TemplateParserContext` vào `parseExpression`:

```java
SpelParserConfiguration configuration = new SpelParserConfiguration();
ExpressionParser parser = new SpelExpressionParser(configuration);
ParserContext templateContext = new TemplateParserContext();

Expression template = parser.parseExpression(
        "Sản phẩm: #{name}",
        templateContext);
```

Không nên dùng `SpelParserConfiguration` để thay delimiter của template; đó là trách nhiệm của `ParserContext`.

## 8. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Câu có chữ thường bị báo lỗi cú pháp SpEL | Đã gọi overload `parseExpression` không có `ParserContext`, nên toàn bộ chuỗi bị coi là biểu thức. | Truyền `new TemplateParserContext()` hoặc một context tùy chỉnh. |
| Không nhận ra đoạn biểu thức | Prefix trong nội dung không trùng với prefix của context. | Kiểm tra chính xác cặp prefix/suffix đã cấu hình. |
| Báo thiếu suffix hoặc lỗi parse ở cuối template | Có prefix mở nhưng không có suffix tương ứng. | Bổ sung delimiter đóng và kiểm tra chuỗi template được ghép từ các phần. |
| Lỗi property hoặc biến khi gọi `getValue` | Cú pháp template hợp lệ nhưng root object, biến hoặc resolver cần thiết chưa có trong evaluation context. | Kiểm tra context tại thời điểm đánh giá, ví dụ root object và `setVariable`. |
| Kết quả có giá trị không đúng định dạng | Giá trị biểu thức được chuyển thành chuỗi theo cơ chế chuyển đổi hiện có; định dạng hiển thị có thể chưa phù hợp. | Định dạng dữ liệu ở tầng ứng dụng hoặc dùng biểu thức/helper được kiểm soát để tạo chuỗi mong muốn. |
| Văn bản literal bị hiểu nhầm thành biểu thức | Nội dung chứa chính delimiter đang dùng. | Chọn một cặp delimiter tùy chỉnh không xung đột với văn bản. |

## 9. Lưu ý khi dùng template trong ứng dụng

- Chỉ đưa biểu thức SpEL do ứng dụng kiểm soát vào template. `TemplateParserContext` không phải cơ chế làm sạch hay sandbox cho biểu thức không đáng tin cậy.
- Nếu người dùng chỉ cung cấp dữ liệu, truyền dữ liệu qua biến trong `EvaluationContext` thay vì nối dữ liệu đó vào chuỗi biểu thức.
- Giới hạn property accessor, method resolver, type locator và bean resolver theo nhu cầu thực tế nếu template có thể đến từ nguồn bên ngoài.
- Kiểm tra cả lỗi parse lẫn lỗi evaluate: parse có thể thành công nhưng evaluation vẫn thất bại nếu property, biến hoặc bean không tồn tại.
- Chọn delimiter ít có khả năng xuất hiện trong văn bản literal và giữ cách cấu hình thống nhất giữa các template.

## Ghi nhớ

- Dùng `parseExpression(text)` cho một biểu thức SpEL độc lập.
- Dùng `parseExpression(text, new TemplateParserContext())` khi chuỗi gồm literal text và các đoạn `#{...}`.
- `TemplateParserContext()` mặc định dùng prefix `#{` và suffix `}`; constructor hai tham số cho phép tùy chỉnh delimiter.
- Các đoạn bên trong delimiter vẫn tuân theo cú pháp và quy tắc evaluation thông thường của SpEL.
- `parseExpression` tạo biểu thức; `getValue` mới đánh giá các đoạn động bằng `EvaluationContext` và tạo chuỗi kết quả.
- `TemplateParserContext` điều khiển cách tách template; `SpelParserConfiguration` điều khiển các hành vi cấu hình khác của parser.