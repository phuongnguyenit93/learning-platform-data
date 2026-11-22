# Biến truyền từ context của ứng dụng

## Mục tiêu

Trong Spring Expression Language (SpEL), biến cho phép ứng dụng truyền dữ liệu vào biểu thức tại thời điểm đánh giá. Thay vì ghép giá trị trực tiếp vào chuỗi expression, ứng dụng đăng ký một giá trị trong **EvaluationContext** rồi tham chiếu nó bằng cú pháp **#variableName**.

Cách làm này giúp tái sử dụng cùng một biểu thức với nhiều bộ dữ liệu, giữ dữ liệu đầu vào tách khỏi cú pháp SpEL và hỗ trợ các điều kiện có tham số như ngưỡng giá, trạng thái được phép, người dùng hiện tại hoặc chính sách nghiệp vụ.

Sau bài này, bạn có thể:

- Đăng ký biến bằng phương thức **setVariable()** trong EvaluationContext.
- Tham chiếu biến bằng cú pháp **#name**.
- Phân biệt biến context với property của root object và phần tử hiện tại.
- Truyền số, chuỗi, enum, collection và object vào biểu thức.
- Dùng biến trong selection, projection và điều kiện lồng nhau.
- Tái sử dụng Expression với các giá trị biến khác nhau.
- Xử lý biến thiếu, null, sai kiểu và kiểm soát dữ liệu được đưa vào context.

## 1. Biến trong SpEL là gì?

Biến là một giá trị được ứng dụng đặt vào EvaluationContext để biểu thức có thể đọc trong lúc chạy. Trong SpEL, tên biến được viết với dấu # ở phía trước:

~~~text
#minimumPrice
#currentUser
#allowedStatuses
~~~

Dấu # là một phần của cú pháp tham chiếu trong expression. Khi đăng ký biến bằng Java, truyền tên biến không có dấu #:

~~~java
context.setVariable("minimumPrice", new BigDecimal("100.00"));
~~~

Sau đó, expression có thể dùng:

~~~text
#minimumPrice
~~~

Hãy thống nhất quy ước: tên truyền cho setVariable() không có dấu thăng; tên trong SpEL có dấu thăng.

Biến có thể chứa nhiều kiểu dữ liệu: String, số, Boolean, enum, collection, Map hoặc một object nghiệp vụ. SpEL đánh giá biến dựa trên giá trị và kiểu object mà ứng dụng đã truyền vào.

## 2. Đăng ký biến trong EvaluationContext

Ví dụ cơ bản dùng StandardEvaluationContext:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimumPrice", new BigDecimal("100.00"));
context.setVariable("requiredStatus", "APPROVED");

Expression expression = parser.parseExpression(
    "#minimumPrice <= 150 and #requiredStatus == 'APPROVED'");

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Ứng dụng đăng ký hai biến rồi đánh giá expression. Kết quả là Boolean true vì cả hai điều kiện đều đúng.

Có thể truyền root object cùng lúc với các biến:

~~~java
Order order = loadOrder();

StandardEvaluationContext context = new StandardEvaluationContext(order);
context.setVariable("minimumTotal", new BigDecimal("100.00"));

Expression expression = parser.parseExpression(
    "#root.total >= #minimumTotal");

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

Trong ví dụ này:

- order là root object của context.
- #root.total đọc property total từ root object.
- #minimumTotal đọc biến do ứng dụng đăng ký.
- Kết quả được yêu cầu dưới dạng Boolean.

Biến được đăng ký trên context dùng để đánh giá expression. Nếu một expression được đánh giá với context khác, context đó cần được cung cấp các biến mà expression yêu cầu.

## 3. Phân biệt biến, root object và object hiện tại

Ba tham chiếu sau có ý nghĩa khác nhau:

| Cú pháp | Ý nghĩa |
|---|---|
| **#minimumTotal** | Biến do ứng dụng truyền vào EvaluationContext |
| **#root.total** | Property total của root object |
| **#this.total** | Property total của object hiện tại trong ngữ cảnh đang đánh giá |
| **total** | Property total trên object hiện tại, nếu property đó có thể truy cập |

Giả sử root object là Order và expression được đánh giá trực tiếp trên Order:

~~~text
#root.total >= #minimumTotal
~~~

Khi đang ở trong collection selection, #this thường đại diện cho phần tử hiện tại:

~~~text
#root.orders.?[#this.total >= #minimumTotal]
~~~

Ở đây, #root vẫn là object chứa danh sách orders; #this thay đổi theo từng Order đang được xét; #minimumTotal vẫn là biến context có cùng giá trị trong toàn bộ lần đánh giá.

Đừng nhầm property với biến chỉ vì chúng có tên giống nhau. Ví dụ:

- minimumTotal đọc property minimumTotal của object hiện tại.
- #minimumTotal đọc biến minimumTotal trong EvaluationContext.

Khi một expression có nhiều tầng object, dùng #root, #this và #variableName một cách tường minh giúp tránh truy cập nhầm dữ liệu.

## 4. Truyền các kiểu dữ liệu khác nhau

### Chuỗi và trạng thái

~~~java
context.setVariable("requiredStatus", "PAID");
context.setVariable("regionCode", "HCM");
~~~

Biểu thức:

~~~text
#order.status == #requiredStatus and #order.region == #regionCode
~~~

Nếu root object là order và các property tương ứng tồn tại, expression so sánh trạng thái và khu vực với dữ liệu ứng dụng cung cấp.

### Số và ngưỡng nghiệp vụ

~~~java
context.setVariable("minimumScore", 80);
context.setVariable("maximumDiscount", new BigDecimal("0.15"));
~~~

Biểu thức:

~~~text
#student.score >= #minimumScore
~~~

Hoặc:

~~~text
#discount <= #maximumDiscount
~~~

Hãy dùng kiểu số phù hợp với nghiệp vụ. Với số tiền và tỷ lệ cần độ chính xác thập phân, BigDecimal thường phù hợp hơn phép tính dựa trên floating point.

### Enum

~~~java
context.setVariable("requiredStatus", OrderStatus.APPROVED);
~~~

Biểu thức:

~~~text
#order.status == #requiredStatus
~~~

Dùng enum giúp tránh lỗi chính tả và giới hạn giá trị vào tập trạng thái đã định nghĩa trong Java.

### Collection và Map

~~~java
context.setVariable(
    "allowedStatuses",
    Set.of(OrderStatus.PAID, OrderStatus.SHIPPED));

context.setVariable(
    "priceLimits",
    Map.of("STANDARD", new BigDecimal("100"),
           "PREMIUM", new BigDecimal("500")));
~~~

Biểu thức có thể gọi method phù hợp trên giá trị collection hoặc truy cập Map bằng index:

~~~text
#allowedStatuses.contains(#order.status)
~~~

~~~text
#priceLimits['PREMIUM']
~~~

Khả năng gọi method phụ thuộc MethodResolver và cấu hình EvaluationContext. Hãy kiểm thử expression trong chính context mà ứng dụng sử dụng.

### Object nghiệp vụ

Ứng dụng cũng có thể truyền một object làm biến:

~~~java
context.setVariable("policy", policy);
~~~

Biểu thức:

~~~text
#policy.minimumTotal
#policy.allowedStatuses
~~~

SpEL đọc property của object được gán cho biến theo PropertyAccessor của context. Vì vậy, object truyền vào cần cung cấp các property mà expression sử dụng.

## 5. Dùng biến trong selection và projection

Biến đặc biệt hữu ích khi điều kiện collection thay đổi theo dữ liệu ứng dụng.

Giả sử root object có danh sách đơn hàng:

~~~text
#root.orders.?[#this.total >= #minimumTotal]
~~~

Ứng dụng có thể thay đổi minimumTotal mà không cần tạo chuỗi expression mới.

Ví dụ đánh giá với hai ngưỡng:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
    "#root.orders.?[#this.total >= #minimumTotal]");

StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("minimumTotal", new BigDecimal("100"));

List<?> regularOrders =
    expression.getValue(context, List.class);

context.setVariable("minimumTotal", new BigDecimal("500"));

List<?> highValueOrders =
    expression.getValue(context, List.class);
~~~

Cùng một Expression được đánh giá với hai giá trị ngưỡng khác nhau. Trong ứng dụng thực tế, nếu context được dùng đồng thời ở nhiều luồng, không nên thay đổi biến trên cùng một context trong lúc các lần đánh giá đang chạy. Hãy tạo context riêng cho mỗi lần đánh giá hoặc quản lý vòng đời context theo cách không có cập nhật cạnh tranh.

Biến cũng có thể dùng trong projection:

~~~text
#root.orders.?[#this.total >= #minimumTotal].![#this.id]
~~~

Expression lọc đơn hàng đạt ngưỡng rồi trả về danh sách ID của chúng.

### Dùng biến ở nhiều tầng

~~~text
#root.departments.![employees.?[#this.salary >= #minimumSalary].![name]]
~~~

Trong biểu thức trên, #minimumSalary có thể được dùng ở mọi selection bên trong projection. #this là Department ở operation ngoài, rồi là Employee ở selection bên trong. Biến vẫn là giá trị do context cung cấp.

Nếu điều kiện có nhiều biến, hãy chọn tên rõ nghĩa:

~~~text
#root.orders.?[
    #this.total >= #minimumTotal and
    #this.status == #requiredStatus
]
~~~

Tên biến nên phản ánh đơn vị và mục đích. Ví dụ #minimumTotal rõ hơn #limit, đặc biệt khi expression có nhiều ngưỡng khác nhau.

## 6. Biến và việc tái sử dụng Expression

Một lợi ích quan trọng của biến là có thể parse expression một lần rồi đánh giá nhiều lần với dữ liệu khác nhau.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#quantity * #unitPrice");

StandardEvaluationContext context = new StandardEvaluationContext();

context.setVariable("quantity", 3);
context.setVariable("unitPrice", new BigDecimal("12.50"));

BigDecimal firstResult =
    expression.getValue(context, BigDecimal.class);

context.setVariable("quantity", 5);

BigDecimal secondResult =
    expression.getValue(context, BigDecimal.class);
~~~

Expression không cần thay đổi khi quantity thay đổi. Ứng dụng chỉ cập nhật giá trị biến trước lần đánh giá tiếp theo.

Việc parse một lần và tái sử dụng Expression có thể giảm chi phí parse lặp lại. Tuy nhiên, hãy phân biệt vòng đời của Expression với vòng đời của EvaluationContext. Expression có thể được lưu để tái sử dụng; context chứa root object và biến của một lần đánh giá nên được quản lý phù hợp với dữ liệu và tính đồng thời của ứng dụng.

Không nên chia sẻ một context có biến mutable giữa nhiều request rồi ghi đè biến theo từng request. Điều đó có thể khiến một lần đánh giá đọc giá trị được đặt bởi request khác. Tạo context mới hoặc context riêng theo request giúp dữ liệu đầu vào rõ ràng hơn.

## 7. Biến null, thiếu biến và sai kiểu

Một expression chỉ hoạt động đúng nếu các biến mà nó cần đã được cung cấp với kiểu dữ liệu phù hợp.

Cần phân biệt:

- **Biến có giá trị:** expression có thể sử dụng giá trị đó.
- **Biến được đặt thành null:** expression nhận giá trị null; các thao tác tiếp theo phải xử lý null phù hợp.
- **Biến chưa được đăng ký:** lookup không cung cấp giá trị như ứng dụng mong đợi; tùy expression, kết quả có thể null hoặc phát sinh lỗi ở thao tác tiếp theo.
- **Biến sai kiểu:** phép so sánh, truy cập property hoặc lời gọi method có thể thất bại khi đánh giá.

Ví dụ, nếu #minimumTotal cần là BigDecimal, không nên lúc thì truyền String, lúc thì truyền Integer mà không có quy tắc chuyển đổi rõ ràng.

Trước khi đánh giá, ứng dụng nên kiểm tra các đầu vào bắt buộc:

~~~java
if (minimumTotal == null) {
    throw new IllegalArgumentException("minimumTotal is required");
}

context.setVariable("minimumTotal", minimumTotal);
~~~

Nếu biến tùy chọn, xác định rõ ý nghĩa của null. Có thể dùng điều kiện:

~~~text
#optionalLimit == null or #order.total <= #optionalLimit
~~~

Biểu thức này thể hiện rằng không có giới hạn thì điều kiện được chấp nhận; nếu có giới hạn thì total phải nằm trong giới hạn. Hãy chọn chính sách theo nghiệp vụ, không để null vô tình quyết định kết quả.

Tên biến nên được quản lý tập trung hoặc có hằng số trong Java để tránh sai chính tả giữa nơi đăng ký và nơi tham chiếu.

## 8. StandardEvaluationContext và SimpleEvaluationContext

Cả hai loại context đều phục vụ việc đánh giá SpEL, nhưng mục đích và phạm vi khả năng khác nhau.

**StandardEvaluationContext** có thể được cấu hình với root object, biến, property accessor, method resolver, type locator, bean resolver và các thành phần mở rộng khác. Đây là lựa chọn linh hoạt khi expression cần nhiều khả năng của SpEL.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setVariable("minimumTotal", new BigDecimal("100"));
~~~

**SimpleEvaluationContext** được thiết kế cho các trường hợp data binding có phạm vi giới hạn hơn. Nó cho phép ứng dụng cấu hình các khả năng cần thiết mà không mở toàn bộ tập chức năng như StandardEvaluationContext.

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimumTotal", new BigDecimal("100"));
~~~

Hãy chọn context theo những thao tác expression cần thực hiện. Việc truyền biến không đồng nghĩa với việc mọi property, method, type reference, constructor hoặc bean reference đều được phép. Các khả năng đó vẫn phụ thuộc context và accessor/resolver đã cấu hình.

Dùng cùng cách tạo context trong test và production để tránh expression hoạt động trong một môi trường nhưng thất bại ở môi trường khác.

## 9. Truyền biến thay vì ghép chuỗi expression

Không nên ghép dữ liệu đầu vào trực tiếp vào chuỗi SpEL:

~~~java
String expressionText =
    "total >= " + request.getMinimumTotal();
Expression expression = parser.parseExpression(expressionText);
~~~

Cách này trộn dữ liệu với cú pháp. Nếu dữ liệu chứa dấu nháy hoặc ký tự đặc biệt, expression có thể bị tạo sai. Nếu dữ liệu đến từ nguồn không đáng tin, việc ghép chuỗi còn có thể cho phép đầu vào thay đổi cấu trúc expression.

Nên giữ expression cố định và truyền dữ liệu qua biến:

~~~java
Expression expression =
    parser.parseExpression("total >= #minimumTotal");

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable("minimumTotal", request.getMinimumTotal());

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Cách này có các lợi ích:

- Cú pháp expression không phụ thuộc vào nội dung đầu vào.
- Giá trị được truyền với kiểu Java thay vì chuyển thành một đoạn text.
- Cùng một Expression có thể dùng với nhiều request.
- Việc kiểm tra đầu vào được thực hiện trong Java trước khi đánh giá.
- Dễ kiểm thử riêng expression và dữ liệu.

Tuy vậy, truyền biến không tự làm một expression không đáng tin trở nên an toàn. Nếu người dùng được phép gửi toàn bộ chuỗi SpEL, họ vẫn có thể viết expression với các khả năng mà EvaluationContext cho phép. Hãy kiểm soát cả nguồn expression lẫn phạm vi context.

## 10. Giới hạn quyền truy cập và dữ liệu trong context

EvaluationContext là ranh giới quan trọng giữa expression và object của ứng dụng. Chỉ đưa vào context những biến và object mà expression thực sự cần.

Một số nguyên tắc:

- Tránh truyền toàn bộ application context, service registry hoặc object có quyền rộng khi expression chỉ cần một vài giá trị.
- Ưu tiên DTO hoặc object chỉ đọc có các property cần thiết.
- Kiểm tra kiểu và miền giá trị của biến trước khi đăng ký.
- Không đưa secret, credential hoặc dữ liệu nhạy cảm vào context nếu expression không cần.
- Dùng SimpleEvaluationContext khi phạm vi data binding giới hạn đáp ứng được nhu cầu.
- Cấu hình property accessor và method resolver có chủ đích.
- Không đánh giá expression tùy ý từ người dùng với StandardEvaluationContext có đầy đủ quyền.
- Ghi nhận ID expression và lỗi đánh giá mà không ghi log dữ liệu nhạy cảm.

Biến là dữ liệu được cung cấp cho expression; nó không phải một cơ chế phân quyền. Việc một biến được đăng ký không có nghĩa người dùng cuối được phép xem hoặc thay đổi object mà biến tham chiếu tới.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Biến trả về null | Chưa đăng ký, sai tên hoặc giá trị được đặt là null | Đối chiếu tên trong setVariable và #name; xác thực biến bắt buộc |
| Không phân giải được biến | Tham chiếu sai cú pháp hoặc context không có giá trị tương ứng | Kiểm tra dấu # và tên biến |
| Lỗi khi so sánh | Hai giá trị có kiểu không tương thích | Chuẩn hóa kiểu trước khi setVariable |
| Lỗi khi truy cập property của biến | Object biến không cung cấp property hoặc accessor không hỗ trợ | Kiểm tra kiểu object và PropertyAccessor |
| Lỗi khi gọi method trên biến | Method không tồn tại hoặc context không cho phép resolver đó | Kiểm tra chữ ký method và MethodResolver |
| Kết quả thay đổi giữa các request | Context mutable bị chia sẻ và biến bị ghi đè | Tạo context riêng hoặc quản lý đồng thời phù hợp |
| Expression chứa giá trị đầu vào sai cú pháp | Dữ liệu bị ghép trực tiếp vào chuỗi expression | Giữ expression cố định và truyền dữ liệu qua biến |
| Biến collection không hoạt động trong selection | Kiểu collection hoặc predicate không đúng | Kiểm tra kiểu phần tử và điều kiện |
| Biến không có trong production | Factory tạo context không đăng ký biến giống test | Dùng chung quy trình tạo context và test |

Khi chẩn đoán, kiểm tra theo thứ tự: expression đang được parse, tên biến được tham chiếu, biến đã được đăng ký trên đúng context chưa, kiểu và giá trị của biến, rồi mới tới phép toán hoặc property được áp dụng lên biến.

## 12. Kiểm thử biến context

Kiểm thử nên xác nhận expression nhận đúng giá trị từ context và có thể tái sử dụng với các giá trị khác nhau.

Ví dụ:

~~~java
@Test
void evaluatesExpressionWithContextVariable() {
    ExpressionParser parser = new SpelExpressionParser();
    Expression expression =
        parser.parseExpression("#amount >= #minimumAmount");

    StandardEvaluationContext context = new StandardEvaluationContext();
    context.setVariable("amount", new BigDecimal("150"));
    context.setVariable("minimumAmount", new BigDecimal("100"));

    assertEquals(Boolean.TRUE, expression.getValue(context, Boolean.class));

    context.setVariable("minimumAmount", new BigDecimal("200"));

    assertEquals(Boolean.FALSE, expression.getValue(context, Boolean.class));
}
~~~

Các trường hợp nên kiểm tra:

- Biến được đăng ký đúng tên và đúng kiểu.
- Biến số, chuỗi, enum và object được đọc đúng.
- Biến dùng trong selection và projection.
- Biến dùng cùng root object và #this.
- Biến bắt buộc bị thiếu.
- Biến có giá trị null.
- Biến có kiểu không phù hợp.
- Cùng Expression được đánh giá với nhiều bộ biến.
- Mỗi request có context riêng nếu giá trị thay đổi đồng thời.
- Context production có cùng cấu hình với context trong test.

Với biến object, kiểm tra cả property mà expression truy cập. Với biến collection, xác nhận kiểu phần tử và kết quả selection/projection. Với biến cấu hình, kiểm tra cả giá trị biên và giá trị ngoài miền được phép.

## 13. Quy trình sử dụng biến trong ứng dụng

Khi xây dựng expression có tham số:

1. **Xác định đầu vào cần thiết.** Liệt kê tên, kiểu và việc bắt buộc/tùy chọn của từng biến.
2. **Viết expression cố định.** Tham chiếu biến bằng #name, không ghép dữ liệu vào chuỗi.
3. **Chọn EvaluationContext.** Dùng context có đúng khả năng cần thiết cho property, method và các thao tác khác.
4. **Tạo context cho lần đánh giá.** Đặt root object và đăng ký đầy đủ biến trước khi gọi getValue.
5. **Xác thực dữ liệu.** Kiểm tra null, kiểu, miền giá trị và quyền sử dụng object.
6. **Đánh giá expression.** Yêu cầu kiểu kết quả rõ ràng khi ứng dụng cần Boolean, số hoặc collection cụ thể.
7. **Quản lý vòng đời context.** Tránh cập nhật biến trên một context đang được nhiều luồng sử dụng.
8. **Kiểm thử và ghi nhận lỗi.** Dùng cùng context factory như production và ghi ID expression để truy vết.

Nếu danh sách biến trở nên dài hoặc expression phụ thuộc quá nhiều vào object bên ngoài, hãy cân nhắc tạo một object đầu vào duy nhất như EvaluationParameters. Object này gom các giá trị liên quan, có kiểu rõ ràng và dễ kiểm tra trước khi đánh giá.

## 14. Thực hành tốt

- Dùng setVariable("name", value) để đăng ký; dùng #name trong expression.
- Chọn tên biến rõ nghĩa, có đơn vị khi phù hợp như minimumTotal hoặc maximumAge.
- Phân biệt #name với property name của object hiện tại.
- Dùng #root cho root object và #this cho phần tử hiện tại trong collection operation.
- Truyền object, collection hoặc enum theo kiểu Java thay vì chuyển tất cả thành chuỗi.
- Tái sử dụng Expression khi cú pháp không đổi và chỉ thay dữ liệu context.
- Tạo context riêng cho request hoặc lần đánh giá khi biến thay đổi theo request.
- Xác thực biến bắt buộc, null, kiểu và miền giá trị trước khi đánh giá.
- Giữ expression tách khỏi dữ liệu đầu vào để tránh lỗi ghép chuỗi.
- Chỉ đưa các object cần thiết vào context và giới hạn quyền truy cập.
- Dùng cùng context factory trong kiểm thử và production.
- Chuyển logic nhiều bước hoặc có tác dụng phụ sang Java method có tên rõ ràng.

## 15. Checklist review

Trước khi chấp nhận expression dùng biến context, hãy kiểm tra:

- [ ] Mỗi biến có tên, kiểu và mục đích rõ ràng.
- [ ] setVariable dùng tên không có dấu #.
- [ ] Expression tham chiếu biến bằng cú pháp #name.
- [ ] Không nhầm biến với property của root hoặc object hiện tại.
- [ ] Root object và #this được dùng đúng phạm vi.
- [ ] Biến bắt buộc được đăng ký trước khi đánh giá.
- [ ] Null và kiểu dữ liệu sai được xử lý có chủ đích.
- [ ] Biến collection/object có cấu trúc và property phù hợp.
- [ ] Dữ liệu không được ghép trực tiếp vào chuỗi expression.
- [ ] EvaluationContext chỉ cung cấp quyền và dữ liệu cần thiết.
- [ ] Context mutable không bị cập nhật cạnh tranh giữa các request.
- [ ] Có kiểm thử nhiều bộ giá trị, giá trị biên và context production.

## Kết luận

Biến trong SpEL cho phép ứng dụng truyền dữ liệu vào expression thông qua EvaluationContext và tham chiếu dữ liệu đó bằng cú pháp **#name**. Đăng ký biến bằng tên không có dấu #, giữ root object và #this tách biệt với biến, rồi dùng giá trị đã có kiểu Java trong điều kiện hoặc collection operation. Cách này giúp tái sử dụng Expression mà không ghép dữ liệu vào chuỗi cú pháp. Hãy xác thực biến trước khi đánh giá, quản lý context theo vòng đời phù hợp và giới hạn object cùng quyền truy cập mà expression được phép sử dụng.