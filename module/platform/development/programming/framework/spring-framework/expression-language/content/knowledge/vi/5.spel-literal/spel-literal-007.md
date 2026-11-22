# Literal không thay đổi với dữ liệu đầu vào

Trong Spring Expression Language (SpEL), **literal** là giá trị được viết trực tiếp trong chuỗi biểu thức, chẳng hạn một số, một chuỗi ký tự, giá trị Boolean hoặc **null**. Literal biểu diễn một giá trị cố định ngay trong biểu thức. Khi ứng dụng đánh giá biểu thức trên những root object hoặc dữ liệu đầu vào khác nhau, bản thân literal vẫn giữ nguyên giá trị đã khai báo.

Đặc điểm này giúp biểu thức có thể dùng các hằng số để so sánh, tính toán, tạo nhãn hoặc chọn kết quả. Tuy nhiên, cần phân biệt giá trị literal với kết quả của toàn bộ biểu thức: một literal không đổi, nhưng kết quả của biểu thức chứa literal vẫn có thể thay đổi theo dữ liệu đầu vào.

## Literal là gì?

Literal là một trong những thành phần cơ bản của cú pháp SpEL. Nó không cần lấy dữ liệu từ root object, biến hay bean. Parser đọc giá trị được viết trực tiếp trong chuỗi và tạo thành một phần của biểu thức.

Ví dụ, các biểu thức sau chứa literal:

| Biểu thức SpEL | Giá trị |
|---|---|
| **42** | Số nguyên 42 |
| **3.14** | Số thực 3.14 |
| **'Spring'** | Chuỗi ký tự Spring |
| **true** | Giá trị Boolean đúng |
| **false** | Giá trị Boolean sai |
| **null** | Giá trị null |

Nếu parse biểu thức **'Spring'**, kết quả của biểu thức là chuỗi Spring. Root object không cần chứa property tên Spring và cũng không làm thay đổi nội dung literal này.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("'Spring'");

String value = expression.getValue(String.class);
~~~

Trong ví dụ trên, parser nhận một chuỗi biểu thức có chứa string literal. Khi gọi **getValue(String.class)**, SpEL trả về giá trị của literal. Không có dữ liệu đầu vào bên ngoài nào được dùng để tạo ra chuỗi Spring.

## Các nhóm literal thường dùng

### String literal

String literal được đặt trong dấu nháy đơn:

~~~java
Expression expression =
        parser.parseExpression("'Hello Spring'");

String message = expression.getValue(String.class);
~~~

Kết quả là chuỗi **Hello Spring**. Nội dung chuỗi được xác định ngay trong biểu thức và không tự thay đổi khi root object thay đổi.

Nếu nội dung cần chứa dấu nháy đơn, có thể biểu diễn dấu nháy đơn bên trong bằng cách lặp lại nó:

~~~java
Expression expression =
        parser.parseExpression("'It''s Spring'");
~~~

Literal chuỗi này biểu diễn nội dung **It's Spring**. Dấu nháy đơn bên ngoài xác định ranh giới string literal của SpEL; quy tắc escape giúp parser phân biệt dấu nháy nằm trong nội dung với dấu nháy kết thúc chuỗi.

### Numeric literal

SpEL hỗ trợ literal số nguyên và số thực. Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer count = parser.parseExpression("25")
        .getValue(Integer.class);

Double rate = parser.parseExpression("0.85")
        .getValue(Double.class);
~~~

Các giá trị 25 và 0.85 được viết trực tiếp trong biểu thức. Chúng không phụ thuộc vào property của object đang được đánh giá.

Literal số có thể được dùng làm toán hạng trong phép tính:

~~~java
Integer result =
        parser.parseExpression("10 * 5 + 2")
                .getValue(Integer.class);
~~~

Kết quả là 52. Các số 10, 5 và 2 vẫn là những giá trị cố định; phép toán kết hợp chúng tạo ra một giá trị khác.

SpEL cũng hỗ trợ cách viết số theo hệ thập lục phân và ký hiệu số thực theo dạng khoa học. Khi cần biểu diễn một kiểu số cụ thể, có thể dùng các hậu tố số được SpEL hỗ trợ, chẳng hạn hậu tố dành cho Long hoặc BigDecimal. Kiểu kết quả thực tế cần phù hợp với quy tắc phân tích số và phép chuyển đổi kiểu của context.

### Boolean literal

Hai literal Boolean là **true** và **false**:

~~~java
Boolean enabled =
        parser.parseExpression("true").getValue(Boolean.class);

Boolean disabled =
        parser.parseExpression("false").getValue(Boolean.class);
~~~

Chúng hữu ích khi một biểu thức cần một cờ cố định hoặc một nhánh điều kiện luôn đúng/sai theo cấu hình của biểu thức. Literal Boolean không tự đọc trạng thái bật/tắt từ object.

### Null literal

**null** biểu diễn giá trị rỗng:

~~~java
Object value =
        parser.parseExpression("null").getValue();
~~~

Literal này có thể dùng trong biểu thức so sánh hoặc điều kiện:

~~~java
Boolean missing =
        parser.parseExpression("null == null")
                .getValue(Boolean.class);
~~~

Kết quả của phép so sánh trên là true. Khi dùng null trong biểu thức có property hoặc method, cần chú ý rằng việc truy cập tiếp vào một giá trị null có thể phát sinh lỗi evaluation tùy thao tác và cấu hình parser.

## Literal không phụ thuộc root object

Root object là đối tượng mà SpEL sử dụng khi biểu thức cần đọc property hoặc gọi hành vi trên dữ liệu đó. Một biểu thức chỉ chứa literal không cần root object để xác định giá trị.

Ví dụ, cùng một Expression có thể được đánh giá với hai object khác nhau:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("'ACTIVE'");

String first = expression.getValue(userOne, String.class);
String second = expression.getValue(userTwo, String.class);
~~~

Cả hai lần đánh giá đều trả về chuỗi **ACTIVE**. Các root object không tham gia vào biểu thức nên không ảnh hưởng đến giá trị của literal.

Điều này cũng đúng với biểu thức chỉ chứa phép toán trên literal:

~~~java
Expression expression =
        parser.parseExpression("100 + 50");

Integer first = expression.getValue(orderOne, Integer.class);
Integer second = expression.getValue(orderTwo, Integer.class);
~~~

Cả hai kết quả đều bằng 150 vì biểu thức không tham chiếu đến dữ liệu của order. Việc truyền root object không làm cho các số 100 và 50 trở thành giá trị động.

## Literal trong biểu thức kết hợp với dữ liệu đầu vào

Trong ứng dụng thực tế, literal thường xuất hiện cùng property, biến hoặc lời gọi phương thức. Khi đó, literal vẫn cố định nhưng toàn bộ biểu thức có thể phụ thuộc dữ liệu đầu vào.

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("price >= 100");

Boolean first = expression.getValue(
        new StandardEvaluationContext(productA), Boolean.class);

Boolean second = expression.getValue(
        new StandardEvaluationContext(productB), Boolean.class);
~~~

Trong biểu thức này, **100** là numeric literal cố định. Property **price** được đọc từ root object. Nếu productA có giá 120 và productB có giá 80, kết quả lần lượt là true và false.

Vì vậy, câu nói “literal không thay đổi với dữ liệu đầu vào” nói về giá trị của thành phần literal, không có nghĩa mọi biểu thức chứa literal đều trả về một kết quả bất biến.

Một ví dụ khác là biểu thức điều kiện:

~~~java
Expression expression = parser.parseExpression(
        "status == 'PAID' ? 'Ready' : 'Waiting'");
~~~

Các chuỗi **'PAID'**, **'Ready'** và **'Waiting'** là literal. Property **status** lấy từ object. Kết quả có thể là Ready hoặc Waiting tùy trạng thái của object, trong khi nội dung của ba literal không đổi.

## Phân biệt literal với property và variable

Khi đọc một biểu thức SpEL, cần nhận ra giá trị nào được viết cố định và giá trị nào được lấy từ môi trường đánh giá:

| Thành phần | Ví dụ | Nguồn giá trị |
|---|---|---|
| Literal | **100**, **'PAID'**, **true** | Viết trực tiếp trong biểu thức |
| Root object property | **price**, **status** | Property của root object |
| Variable | **#minimumPrice** | Biến được đặt trong EvaluationContext |
| Bean reference | **@pricingService** | Bean được context hỗ trợ phân giải |

Ví dụ, biểu thức **price >= #minimumPrice** có hai phần lấy giá trị từ môi trường: property **price** đến từ root object và biến **#minimumPrice** đến từ evaluation context. Nếu thay bằng **price >= 100**, ngưỡng 100 là literal cố định.

Sự phân biệt này hữu ích khi cần hiểu vì sao một biểu thức cho kết quả thay đổi. Nếu muốn ngưỡng so sánh thay đổi theo cấu hình hoặc theo từng yêu cầu, nên dùng property, variable hoặc một cơ chế cấu hình phù hợp thay vì ghi cứng literal trong chuỗi.

## Dùng literal làm giá trị mặc định và nhánh thay thế

Literal thường được dùng trong toán tử điều kiện để cung cấp kết quả thay thế:

~~~java
Expression expression = parser.parseExpression(
        "displayName != null ? displayName : 'Unknown'");
~~~

Chuỗi **'Unknown'** là literal. Nếu property displayName có giá trị, biểu thức trả về property đó; nếu không, biểu thức trả về literal Unknown.

Có thể dùng literal trong các phép so sánh, biểu thức logic và phép tính tương tự:

~~~java
"quantity > 0"
"status == 'ACTIVE'"
"enabled == true"
"price * 1.1"
~~~

Trong các ví dụ trên, số, chuỗi và Boolean được ghi trực tiếp. Các phần property vẫn được lấy từ root object khi đánh giá.

## Literal và cấu hình ứng dụng

Literal là giá trị nằm trong nội dung biểu thức. Nếu muốn giá trị thay đổi theo môi trường triển khai, người vận hành hoặc cấu hình runtime, nên dùng nguồn cấu hình thay vì xem literal như một placeholder.

Ví dụ, ngưỡng cố định:

~~~java
@Value("#{10}")
private int retryLimit;
~~~

Giá trị 10 là literal trong biểu thức SpEL. Nếu muốn lấy ngưỡng từ file cấu hình, property placeholder thường phù hợp hơn:

~~~java
@Value("${app.retry-limit:10}")
private int retryLimit;
~~~

Ở ví dụ thứ hai, Spring lấy giá trị từ property **app.retry-limit**, dùng 10 làm giá trị mặc định nếu property chưa được khai báo. Số 10 trong cú pháp placeholder là giá trị mặc định của cơ chế cấu hình, không phải một biến động tự thay đổi trong literal SpEL.

Có thể kết hợp nguồn cấu hình với SpEL nếu cần tính toán trên giá trị đã được inject. Điều quan trọng là chọn đúng cơ chế theo ý định: literal cho hằng số được ghi trực tiếp, property cho giá trị cấu hình, variable cho dữ liệu được đưa vào evaluation context và property access cho dữ liệu của root object.

## Literal có thay đổi sau khi parse không?

Literal được biểu diễn trong cấu trúc Expression tạo ra từ chuỗi đã parse. Khi đánh giá lại cùng biểu thức, literal vẫn biểu diễn cùng giá trị. Thay đổi root object hoặc biến không sửa nội dung literal trong biểu thức.

Nếu ứng dụng muốn thay đổi giá trị, có thể tạo hoặc parse một biểu thức khác, hoặc đưa giá trị cần thay đổi vào property, variable hay một thành phần động của context. Không nên kỳ vọng việc sửa một field của root object sẽ tự động cập nhật literal đã viết trực tiếp trong chuỗi.

Điều này cũng có nghĩa là khi biểu thức được cache theo chuỗi, mỗi chuỗi biểu thức khác nhau đại diện cho nội dung cấu hình khác nhau. Nếu cấu hình thay đổi, ứng dụng cần quản lý việc nạp lại hoặc thay thế Expression theo vòng đời cấu hình của mình.

## Lưu ý khi nhận literal từ đầu vào bên ngoài

Một literal được ghi trong mã nguồn hoặc cấu hình tin cậy thường dễ hiểu và ổn định. Tuy nhiên, nếu ứng dụng lấy cả chuỗi biểu thức từ người dùng, không nên cho rằng biểu thức chỉ chứa literal vì giao diện chỉ yêu cầu nhập một giá trị.

Chuỗi đầu vào có thể chứa property access, method call, toán tử hoặc cú pháp khác. Parser sẽ diễn giải theo toàn bộ ngôn ngữ SpEL. Nếu chỉ muốn người dùng nhập một giá trị văn bản hoặc con số, hãy xác thực và chuyển đổi dữ liệu theo kiểu tương ứng thay vì đánh giá một chuỗi biểu thức tùy ý.

Khi use case thật sự cần cho phép biểu thức, hãy giới hạn evaluation context và root object, chỉ expose dữ liệu cần thiết, đồng thời xử lý lỗi parse và evaluation. Việc giới hạn độ dài chuỗi cũng hữu ích để tránh biểu thức quá lớn hoặc không cần thiết.

## Kết luận

Literal là giá trị được viết trực tiếp trong biểu thức SpEL, bao gồm chuỗi, số, Boolean và null. Giá trị của literal không phụ thuộc root object hoặc biến trong evaluation context. Khi literal được kết hợp với property hay variable, kết quả của toàn biểu thức vẫn có thể thay đổi theo dữ liệu đầu vào.

Hãy dùng literal cho các giá trị cố định có chủ đích như ngưỡng, nhãn hoặc giá trị mặc định. Nếu giá trị cần thay đổi theo môi trường hay theo từng yêu cầu, hãy đưa nó vào nguồn cấu hình, root object hoặc evaluation context. Sự phân biệt này làm cho biểu thức dễ đọc, dễ dự đoán và dễ bảo trì hơn.
