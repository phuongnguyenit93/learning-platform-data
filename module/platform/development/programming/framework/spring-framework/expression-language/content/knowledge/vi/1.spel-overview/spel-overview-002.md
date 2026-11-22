# Biểu thức, ngữ cảnh đánh giá và kết quả đánh giá trong Spring Expression Language

Spring Expression Language (SpEL) cho phép viết một biểu thức dưới dạng chuỗi rồi đánh giá biểu thức đó trên dữ liệu của ứng dụng. Để hiểu SpEL hoạt động như thế nào, cần nhìn rõ mối quan hệ giữa ba thành phần:

1. **Biểu thức (Expression):** mô tả phép tính hoặc điều kiện cần thực hiện.
2. **Ngữ cảnh đánh giá (EvaluationContext):** cung cấp dữ liệu và quy tắc để SpEL hiểu các tên, thuộc tính, phương thức và phép toán trong biểu thức.
3. **Kết quả đánh giá (Evaluation Result):** giá trị thu được sau khi biểu thức được thực thi trong một ngữ cảnh cụ thể.

Ba thành phần này nối với nhau theo một luồng: phân tích chuỗi biểu thức thành một đối tượng Expression, đưa đối tượng đó vào một ngữ cảnh để đánh giá, rồi nhận kết quả.

## 1. Luồng hoạt động tổng thể

Một ứng dụng thường sử dụng SpEL theo các bước sau:

~~~text
Chuỗi biểu thức
      |
      v
ExpressionParser.parseExpression(...)
      |
      v
Đối tượng Expression
      |
      | getValue(EvaluationContext, ...)
      v
EvaluationContext cung cấp dữ liệu và cách truy cập
      |
      v
SpEL đánh giá biểu thức
      |
      v
Kết quả: Boolean, Number, String, object, collection, null, ...
~~~

Ví dụ, chuỗi:

~~~spel
total >= #minimum && status == 'PAID'
~~~

mô tả điều kiện: tổng tiền của đối tượng hiện tại phải đạt ngưỡng tối thiểu và trạng thái đơn hàng phải là PAID.

Bản thân chuỗi biểu thức chưa biết total thuộc đối tượng nào, #minimum có giá trị bao nhiêu, hoặc status được đọc bằng cách nào. Những thông tin đó được cung cấp khi đánh giá thông qua EvaluationContext.

### Phân tích và đánh giá là hai thời điểm khác nhau

- **Phân tích (parsing):** ExpressionParser đọc chuỗi, kiểm tra cú pháp và tạo ra đối tượng Expression biểu diễn cấu trúc biểu thức. Bước này chưa cần tính ra kết quả dựa trên một đơn hàng cụ thể.
- **Đánh giá (evaluation):** ứng dụng gọi getValue(...). SpEL sử dụng biểu thức đã phân tích cùng ngữ cảnh được cung cấp để truy cập dữ liệu, thực hiện phép toán và trả về giá trị.

Vì vậy, một biểu thức có thể được phân tích một lần rồi đánh giá nhiều lần với các đối tượng hoặc ngữ cảnh khác nhau.

## 2. Biểu thức (Expression) mô tả điều gì?

Expression là đại diện đã được phân tích của một biểu thức SpEL. Ứng dụng tạo nó thông qua ExpressionParser, thường là SpelExpressionParser.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");
~~~

Ở đây:

- parser chịu trách nhiệm phân tích cú pháp.
- parseExpression(...) nhận chuỗi SpEL và trả về một Expression.
- expression giữ cấu trúc cần được đánh giá về sau.

Biểu thức có thể chứa nhiều loại thành phần:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Thuộc tính | total, customer.name | Đọc dữ liệu từ đối tượng đang xét |
| Biến | #minimum | Đọc giá trị được đăng ký trong ngữ cảnh |
| Literal | 100, 'PAID', true | Giá trị được viết trực tiếp trong biểu thức |
| Toán tử | +, >, && | Tính toán hoặc kết hợp điều kiện |
| Gọi phương thức | name.toUpperCase() | Gọi phương thức nếu ngữ cảnh cho phép |
| Truy cập kiểu | T(java.time.LocalDate) | Tham chiếu kiểu Java theo khả năng của ngữ cảnh |

Một Expression không tự chứa mọi dữ liệu cần thiết để chạy. Chẳng hạn, total được tra cứu trên root object trong ngữ cảnh; còn #minimum được tra cứu trong tập biến của ngữ cảnh.

## 3. Ngữ cảnh đánh giá (EvaluationContext) cung cấp môi trường chạy

EvaluationContext định nghĩa môi trường mà biểu thức được đánh giá trong đó. Nó giúp SpEL trả lời các câu hỏi như:

- Đối tượng nào là đối tượng gốc?
- Biến nào đã được khai báo và giá trị của chúng là gì?
- Có thể đọc thuộc tính hoặc gọi phương thức bằng cách nào?
- Có thể chuyển đổi kiểu dữ liệu ra sao?
- Có thể tham chiếu kiểu Java, constructor hoặc bean hay không?

### 3.1. Root object

Root object là đối tượng mặc định mà các tên thuộc tính không có tiền tố biến được tra cứu trên đó.

Ví dụ:

~~~spel
total >= 500000
~~~

Nếu root object là một Order, SpEL sẽ tìm thuộc tính total trên đối tượng đó. Trong Java, việc đọc thuộc tính thường được thực hiện thông qua getter tương ứng, ví dụ getTotal().

Có thể đặt root object khi tạo ngữ cảnh:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(order);
~~~

Hoặc truyền root object trực tiếp vào một overload của getValue(...):

~~~java
Boolean result =
    expression.getValue(context, order, Boolean.class);
~~~

Trong biểu thức, #root tham chiếu root object hiện tại. Ví dụ #root.total diễn đạt rõ rằng total được đọc từ đối tượng gốc.

### 3.2. Biến trong ngữ cảnh

Tên biến trong SpEL có tiền tố #. Ứng dụng đăng ký biến trên EvaluationContext rồi tham chiếu biến đó trong biểu thức.

~~~java
context.setVariable(
    "minimum",
    new BigDecimal("500000")
);
~~~

Biểu thức có thể dùng biến vừa đăng ký:

~~~spel
total >= #minimum
~~~

Nếu biểu thức tham chiếu #minimum nhưng ngữ cảnh không có biến tương ứng, việc đánh giá có thể thất bại. Do đó, biểu thức và ngữ cảnh phải thống nhất về tên biến.

### 3.3. #root và #this

Hai biến đặc biệt này giúp xác định đối tượng mà biểu thức đang làm việc:

- #root luôn tham chiếu đối tượng gốc của lần đánh giá.
- #this tham chiếu đối tượng đang là mục tiêu đánh giá hiện tại. Trong biểu thức thao tác với collection như selection hoặc projection, #this có thể thay đổi theo từng phần tử.

Ví dụ, khi lọc các đơn hàng trong một collection:

~~~spel
orders.?[total >= #minimum]
~~~

Điều kiện bên trong ?[...] được đánh giá lần lượt trên từng phần tử của orders. Trong phạm vi điều kiện đó, total và #this.total cùng chỉ thuộc tính của phần tử đang được xét. #root vẫn chỉ đối tượng gốc ban đầu.

### 3.4. Các thành phần khác của EvaluationContext

Ngoài root object và biến, ngữ cảnh còn có thể cấu hình các cơ chế sau:

| Cơ chế | Vai trò |
|---|---|
| PropertyAccessor | Xác định cách đọc hoặc ghi thuộc tính |
| MethodResolver | Xác định cách tìm phương thức cần gọi |
| ConstructorResolver | Xác định cách tìm constructor |
| TypeLocator | Tìm kiểu Java được tham chiếu trong biểu thức |
| TypeConverter | Chuyển đổi giá trị giữa các kiểu tương thích |
| BeanResolver | Giải quyết tham chiếu bean, ví dụ cú pháp @myBean khi đã cấu hình |
| OperatorOverloader | Tùy chỉnh cách xử lý một số toán tử |

StandardEvaluationContext cung cấp môi trường SpEL đầy đủ và có thể cấu hình sâu. SimpleEvaluationContext cung cấp một môi trường giới hạn hơn, phù hợp với các tình huống data binding cần kiểm soát những tính năng được phép sử dụng. Việc chọn loại context quyết định những khả năng mà biểu thức có thể dùng.

## 4. Kết quả đánh giá (Evaluation Result)

Kết quả là giá trị mà Expression trả về sau khi được đánh giá trong một ngữ cảnh. Kiểu kết quả phụ thuộc vào biểu thức và dữ liệu thực tế, có thể là:

- Giá trị logic Boolean.
- Số nguyên, số thực hoặc một kiểu số khác.
- Chuỗi String.
- Một object Java.
- Một collection hoặc mảng.
- null, nếu biểu thức hợp lệ và giá trị được tính ra là null.

Ví dụ:

~~~spel
total >= #minimum
~~~

trả về true hoặc false nếu các giá trị cần thiết có thể được đọc và so sánh.

Trong khi đó:

~~~spel
customer.name
~~~

có thể trả về một String, tùy thuộc vào object và thuộc tính thực tế.

Kết quả không được cố định chỉ bởi lúc phân tích cú pháp. Cùng một Expression có thể trả về kết quả khác nhau khi được đánh giá với các root object hoặc biến khác nhau.

### Nhận kết quả không định kiểu và có định kiểu

Nếu gọi getValue(...) mà không chỉ định kiểu mong muốn, phương thức trả về Object:

~~~java
Object value = expression.getValue(context);
~~~

Nếu ứng dụng biết kiểu kết quả mong đợi, có thể yêu cầu kiểu đó:

~~~java
Boolean value =
    expression.getValue(context, Boolean.class);
~~~

SpEL sử dụng cơ chế chuyển đổi kiểu của ngữ cảnh khi cần và khi có thể. Nếu kết quả không thể chuyển đổi sang kiểu yêu cầu, quá trình đánh giá có thể phát sinh lỗi. Vì vậy, kiểu đích trong getValue(...) vừa giúp mã Java rõ ràng hơn, vừa thể hiện hợp đồng kiểu mà ứng dụng mong đợi.

## 5. Ví dụ hoàn chỉnh: kết hợp Expression, EvaluationContext và kết quả

Giả sử ứng dụng có lớp Order:

~~~java
public class Order {
    private final BigDecimal total;
    private final String status;

    public Order(BigDecimal total, String status) {
        this.total = total;
        this.status = status;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Ứng dụng muốn kiểm tra một đơn hàng có được xem là đủ điều kiện xử lý hay không. Điều kiện là tổng tiền đạt ngưỡng tối thiểu và trạng thái là PAID.

~~~java
Order order = new Order(
    new BigDecimal("750000"),
    "PAID"
);

// 1. Phân tích chuỗi thành Expression.
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "total >= #minimum && status == 'PAID'"
);

// 2. Tạo ngữ cảnh với Order làm root object.
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

// 3. Cung cấp biến mà biểu thức cần sử dụng.
context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

// 4. Đánh giá và nhận kết quả Boolean.
Boolean eligible =
    expression.getValue(context, Boolean.class);
~~~

Có thể đọc ví dụ theo đúng quan hệ giữa ba thành phần:

1. **Expression:** biểu thức yêu cầu đọc total, so sánh với #minimum, rồi kiểm tra status.
2. **EvaluationContext:** cung cấp order làm root object và đăng ký biến minimum với giá trị 500000. Context cũng cung cấp các cơ chế để SpEL truy cập thuộc tính và thực hiện phép so sánh.
3. **Evaluation Result:** vì total là 750000 và status là PAID, kết quả eligible là true.

Nếu thay minimum thành 900000, không cần phân tích lại biểu thức. Chỉ cần đánh giá với giá trị biến mới thì kết quả sẽ là false. Tương tự, có thể dùng cùng Expression với một Order khác bằng cách tạo context mới cho đơn hàng đó.

## 6. Quan hệ giữa ba thành phần khi dữ liệu thay đổi

Có thể hình dung vai trò của từng thành phần bằng cách giữ nguyên hai thành phần và thay đổi thành phần còn lại:

| Thay đổi | Điều gì xảy ra? |
|---|---|
| Thay chuỗi biểu thức | Parser tạo một Expression khác, mô tả logic khác |
| Giữ Expression, đổi root object | Các thuộc tính được đọc từ đối tượng mới; kết quả có thể thay đổi |
| Giữ Expression, đổi biến trong context | Những phần tham chiếu biến nhận giá trị mới; kết quả có thể thay đổi |
| Giữ Expression và context, gọi đánh giá lại | SpEL thực hiện lại phép tính theo dữ liệu mà context cung cấp tại thời điểm đánh giá |
| Yêu cầu kiểu kết quả khác | SpEL thử trả về hoặc chuyển đổi kết quả sang kiểu đích nếu tương thích |

Điểm quan trọng là Expression mô tả logic, còn EvaluationContext cung cấp môi trường và dữ liệu để chạy logic đó. Kết quả là đầu ra của sự kết hợp giữa hai thành phần tại một lần đánh giá cụ thể.

## 7. Tái sử dụng Expression và quản lý EvaluationContext

Khi một biểu thức được dùng nhiều lần, ứng dụng thường phân tích nó một lần rồi tái sử dụng đối tượng Expression. Cách này tránh phải phân tích lại cùng một chuỗi trong mỗi lần xử lý.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");

// Với mỗi lần xử lý, cung cấp context phù hợp.
StandardEvaluationContext firstContext =
    new StandardEvaluationContext(firstOrder);
firstContext.setVariable("minimum", minimum);

Boolean firstResult =
    expression.getValue(firstContext, Boolean.class);

StandardEvaluationContext secondContext =
    new StandardEvaluationContext(secondOrder);
secondContext.setVariable("minimum", minimum);

Boolean secondResult =
    expression.getValue(secondContext, Boolean.class);
~~~

Ngữ cảnh có thể chứa root object và biến có trạng thái thay đổi. Vì thế, ứng dụng nên quản lý vòng đời của context phù hợp với dữ liệu của từng lần đánh giá, tránh vô tình dùng lại biến hoặc root object của một yêu cầu cho yêu cầu khác. Đặc biệt trong ứng dụng web xử lý nhiều yêu cầu đồng thời, cần cân nhắc việc tạo context riêng cho từng lần xử lý hoặc từng phạm vi công việc.

## 8. Lỗi có thể xuất hiện ở giai đoạn nào?

Tách riêng parsing và evaluation giúp xác định nguyên nhân lỗi dễ hơn:

- **Lỗi phân tích cú pháp:** chuỗi biểu thức sai cú pháp, chẳng hạn thiếu dấu ngoặc hoặc dùng toán tử không hợp lệ. Lỗi xuất hiện khi gọi parseExpression(...).
- **Lỗi đánh giá:** cú pháp đã hợp lệ nhưng dữ liệu hoặc môi trường không đáp ứng yêu cầu, chẳng hạn biến chưa được đăng ký, thuộc tính không tồn tại, gọi phương thức không phù hợp hoặc chuyển đổi kiểu thất bại. Lỗi xuất hiện khi gọi getValue(...).

Một số câu hỏi hữu ích khi xử lý lỗi:

1. Chuỗi biểu thức có được phân tích thành công không?
2. Root object có đúng kiểu và có thuộc tính mà biểu thức cần không?
3. Tất cả biến dạng #... đã được đăng ký với đúng tên chưa?
4. Loại EvaluationContext đang dùng có cho phép tính năng mà biểu thức yêu cầu không?
5. Kiểu kết quả yêu cầu có tương thích với giá trị thực tế không?

## 9. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Gọi parseExpression(...) là đã chạy biểu thức.**  
Parsing chỉ tạo cấu trúc biểu thức. Việc tính giá trị xảy ra khi gọi getValue(...).

**Nhầm lẫn 2: Cho rằng biến trong biểu thức tự có giá trị.**  
Tên có tiền tố # phải được cung cấp trong ngữ cảnh, trừ các biến đặc biệt do SpEL định nghĩa.

**Nhầm lẫn 3: Cho rằng mọi tên thuộc tính đều là biến.**  
total thường được tra cứu trên root object hoặc đối tượng hiện tại; #minimum được tra cứu như một biến trong context. Hai cách viết có ý nghĩa khác nhau.

**Nhầm lẫn 4: Cho rằng một Expression chỉ có một kết quả cố định.**  
Kết quả được tạo ra tại thời điểm đánh giá và phụ thuộc vào root object, biến cùng môi trường của lần đánh giá đó.

**Nhầm lẫn 5: Cho rằng kiểu kết quả luôn được quyết định từ chuỗi biểu thức.**  
Cấu trúc biểu thức có thể dự đoán loại giá trị trong nhiều trường hợp, nhưng giá trị và kiểu thực tế vẫn phụ thuộc vào dữ liệu lúc chạy. Overload getValue(..., Class<T>) thể hiện kiểu mà ứng dụng mong muốn nhận.

## 10. Ghi nhớ

- ExpressionParser phân tích chuỗi và tạo đối tượng Expression.
- Expression mô tả logic cần đánh giá, chưa tự cung cấp dữ liệu ứng dụng.
- EvaluationContext cung cấp root object, biến và các quy tắc truy cập, chuyển đổi, gọi phương thức hoặc giải quyết kiểu.
- getValue(...) kết hợp Expression với context (và có thể với root object hoặc kiểu kết quả mong muốn) để thực hiện đánh giá.
- Evaluation result là giá trị được tạo ra cho lần đánh giá đó; cùng một expression có thể cho kết quả khác nhau khi context hoặc dữ liệu thay đổi.
- Phân biệt lỗi parsing với lỗi evaluation để tìm đúng giai đoạn gây ra vấn đề.

Khi đọc hoặc viết mã SpEL, hãy lần theo ba câu hỏi: **Biểu thức yêu cầu điều gì? Ngữ cảnh cung cấp dữ liệu và khả năng nào? Lần đánh giá này trả về giá trị gì?** Trả lời được ba câu hỏi đó là nắm được mối quan hệ cốt lõi giữa Expression, EvaluationContext và Evaluation Result.
