# Literal null, Boolean, số nguyên và số thực trong Spring Expression Language (SpEL)

Literal là giá trị được viết trực tiếp trong biểu thức SpEL. Khi parser phân tích biểu thức, các literal được nhận diện và tạo thành giá trị tương ứng để dùng trong phép so sánh, tính toán, điều kiện hoặc truyền vào lời gọi phương thức.

Bài này tập trung vào bốn nhóm literal: null, Boolean (true, false), số nguyên và số thực. Nắm rõ cú pháp cùng kiểu dữ liệu của từng nhóm giúp tránh nhầm lẫn giữa giá trị literal, chuỗi ký tự và thuộc tính của đối tượng.

## 1. Literal là gì?

Literal là một giá trị cố định được biểu diễn ngay trong mã biểu thức. Ví dụ:

~~~text
null
true
false
42
0x2A
3.14
1.25e3
~~~

Các giá trị trên có thể được dùng độc lập hoặc kết hợp với những thành phần khác của SpEL:

~~~text
age >= 18
enabled == true
discount == null
price * 1.08
~~~

Parser phân tích literal cùng toàn bộ biểu thức. Khi gọi getValue(), SpEL đánh giá biểu thức và trả về kết quả có kiểu phù hợp.

Literal khác với thuộc tính của root object và biến trong EvaluationContext:

- **18** là số nguyên được viết trực tiếp trong biểu thức.
- **age** thường là thuộc tính được phân giải từ root object.
- **#minimumAge** là biến đã được đăng ký trong EvaluationContext.
- **'18'** là chuỗi ký tự, không phải số nguyên.

Phân biệt đúng các dạng này là cơ sở để viết điều kiện và phép tính chính xác.

## 2. Literal null

SpEL dùng từ khóa null để biểu diễn giá trị không có đối tượng tham chiếu. Từ khóa này được viết thường và không đặt trong dấu nháy.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object value = parser.parseExpression("null").getValue();

// value == null
~~~

Có thể yêu cầu kiểu kết quả khi đánh giá literal null. Kết quả vẫn là null nếu kiểu yêu cầu tương thích với giá trị null:

~~~java
String name = parser.parseExpression("null").getValue(String.class);

// name == null
~~~

### 2.1. So sánh với null

Literal null thường được dùng để kiểm tra một thuộc tính hoặc kết quả có đang thiếu giá trị hay không:

~~~text
email == null
email != null
discount == null or discount == 0
~~~

Ví dụ dùng root object:

~~~java
public class Customer {
    private final String email;

    public Customer(String email) {
        this.email = email;
    }

    public String getEmail() {
        return email;
    }
}

Customer customer = new Customer(null);

Expression expression = parser.parseExpression("email == null");

Boolean missingEmail =
        expression.getValue(customer, Boolean.class);

// missingEmail == true
~~~

Biểu thức email == null đọc thuộc tính email từ root object rồi so sánh kết quả với literal null. Nếu email có giá trị chuỗi, điều kiện sẽ là false.

### 2.2. Những điểm dễ nhầm

- null là literal null; 'null' là chuỗi có bốn ký tự.
- Từ khóa được viết thường. NULL không phải cách viết literal null của SpEL và có thể bị hiểu như một tên thuộc tính hoặc định danh.
- Không nên gọi phương thức hoặc truy cập thuộc tính tiếp theo trên một kết quả null nếu biểu thức không có cách xử lý null phù hợp. Việc dereference null có thể làm phát sinh lỗi trong lúc đánh giá.
- So sánh với null chỉ kiểm tra sự hiện diện của giá trị. Nó không tự kiểm tra chuỗi rỗng '' hoặc chuỗi chỉ chứa khoảng trắng.

Nếu cần phân biệt null, chuỗi rỗng và chuỗi có nội dung, hãy viết điều kiện riêng cho từng trường hợp.

## 3. Literal Boolean: true và false

SpEL biểu diễn hai giá trị logic bằng các từ khóa viết thường:

~~~text
true
false
~~~

Chúng tương ứng với java.lang.Boolean.TRUE và java.lang.Boolean.FALSE.

~~~java
Boolean active = parser.parseExpression("true")
        .getValue(Boolean.class);

Boolean disabled = parser.parseExpression("false")
        .getValue(Boolean.class);
~~~

Boolean literal có thể được dùng trong phép so sánh hoặc làm toán hạng của biểu thức logic:

~~~text
enabled == true
enabled == false
enabled and retryCount < 3
enabled or administrator
not enabled
~~~

SpEL hỗ trợ các toán tử logic dạng từ khóa như and, or, not và dạng ký hiệu tương ứng như &&, ||, !.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression rule = parser.parseExpression("true and (false or true)");

Boolean result = rule.getValue(Boolean.class);

// result == true
~~~

Trong ví dụ, parser tạo biểu thức logic từ các Boolean literal và các toán tử. getValue(Boolean.class) trả về một Boolean.

### 3.1. Boolean literal và chuỗi

Dấu nháy làm thay đổi ý nghĩa của giá trị:

| Biểu thức | Ý nghĩa |
|---|---|
| true | Giá trị Boolean true |
| false | Giá trị Boolean false |
| 'true' | Chuỗi ký tự "true" |
| 'false' | Chuỗi ký tự "false" |

Tương tự như null, True hoặc FALSE không phải cách viết từ khóa Boolean chuẩn của SpEL. Hãy dùng đúng chữ thường.

Không nên so sánh một thuộc tính Boolean với chuỗi 'true'. Hãy dùng Boolean literal không có dấu nháy hoặc chuyển đổi dữ liệu đầu vào ở ranh giới phù hợp trước khi đánh giá biểu thức.

## 4. Literal số nguyên

Số nguyên được viết bằng các chữ số thập phân. SpEL cũng hỗ trợ cách viết số nguyên hệ thập lục phân với tiền tố 0x.

~~~text
0
7
42
2026
0x2A
~~~

0x2A biểu diễn cùng giá trị số với 42 trong hệ thập phân.

Ví dụ:

~~~java
Integer decimal = parser.parseExpression("42")
        .getValue(Integer.class);

Integer hexadecimal = parser.parseExpression("0x2A")
        .getValue(Integer.class);

// decimal == 42
// hexadecimal == 42
~~~

Số nguyên âm được tạo bằng toán tử một ngôi trừ đứng trước literal:

~~~text
-1
-42
-0x2A
~~~

Dấu trừ là toán tử của biểu thức; nó không làm thay đổi quy tắc viết phần literal số nguyên.

### 4.1. Kiểu số nguyên

SpEL xác định kiểu số nguyên dựa trên giá trị và hậu tố kiểu được chỉ định. Với các giá trị thông thường, kiểu số nguyên phù hợp thường là Integer. Có thể dùng hậu tố L hoặc l để biểu thị literal kiểu Long:

~~~java
Integer count = parser.parseExpression("42")
        .getValue(Integer.class);

Long population = parser.parseExpression("9000000000L")
        .getValue(Long.class);
~~~

Dùng hậu tố Long khi giá trị vượt phạm vi Integer hoặc khi muốn thể hiện rõ kiểu số nguyên dài trong biểu thức. Nếu ứng dụng cần một kiểu kết quả ổn định, hãy chỉ định kiểu qua overload getValue(Class<T>) thay vì phụ thuộc vào việc ép kiểu thủ công sau khi nhận Object.

Các số nguyên rất lớn cần được xem xét theo kiểu số mà biểu thức và ứng dụng hỗ trợ. Không nên giả định một literal có thể được gán trực tiếp cho mọi kiểu số nguyên Java mà không có chuyển đổi phù hợp.

### 4.2. Hệ thập phân và hệ thập lục phân

SpEL cho phép dùng số thập lục phân khi cần biểu diễn các giá trị thường gặp trong lập trình cấp thấp, bit mask hoặc mã màu:

~~~text
0x10
0xFF
0x7FFFFFFF
~~~

Ví dụ, 0xFF bằng 255 ở hệ thập phân.

~~~java
Integer mask = parser.parseExpression("0xFF")
        .getValue(Integer.class);
~~~

Hãy dùng tiền tố 0x và các chữ số thập lục phân hợp lệ từ 0 đến 9, A đến F hoặc a đến f. Nếu biểu thức chứa giá trị không đúng cú pháp số, parser sẽ báo lỗi phân tích.

## 5. Literal số thực

Số thực có phần thập phân và có thể dùng ký pháp khoa học. Dấu chấm được dùng làm dấu phân cách phần nguyên và phần thập phân:

~~~text
0.5
3.14
10.0
1.25e3
6.02E23
~~~

1.25e3 biểu diễn 1.25 nhân 10 mũ 3, tức 1250. Ký pháp khoa học hữu ích với các giá trị rất lớn hoặc rất nhỏ.

Ví dụ:

~~~java
Double ratio = parser.parseExpression("0.75")
        .getValue(Double.class);

Double distance = parser.parseExpression("1.25e3")
        .getValue(Double.class);
~~~

Các literal số thực mặc định thường được biểu diễn bằng Double. Có thể dùng hậu tố để chỉ định kiểu số thực cụ thể.

### 5.1. Hậu tố kiểu số thực

Các hậu tố phổ biến:

| Hậu tố | Kiểu số | Ví dụ |
|---|---|---|
| F hoặc f | Float | 3.14F |
| D hoặc d | Double | 3.14D |
| M hoặc m | BigDecimal | 19.99M |

Ví dụ:

~~~java
Float temperature = parser.parseExpression("36.5F")
        .getValue(Float.class);

Double average = parser.parseExpression("3.14159D")
        .getValue(Double.class);

BigDecimal price = parser.parseExpression("19.99M")
        .getValue(BigDecimal.class);
~~~

Hậu tố giúp biểu thức thể hiện rõ kiểu số cần dùng. BigDecimal đặc biệt hữu ích khi biểu diễn giá trị thập phân cần kiểm soát độ chính xác, chẳng hạn số tiền hoặc tỷ lệ nghiệp vụ.

### 5.2. Độ chính xác của số thực

Float và Double là kiểu dấu phẩy động nhị phân. Một số phân số thập phân, chẳng hạn 0.1, không có biểu diễn nhị phân hữu hạn chính xác. Vì vậy, phép tính có thể tạo ra sai số làm tròn nhỏ.

Khi cần giữ biểu diễn thập phân chính xác hơn cho nghiệp vụ tài chính hoặc phép tính yêu cầu quy tắc làm tròn rõ ràng, cân nhắc dùng BigDecimal literal với hậu tố M:

~~~java
BigDecimal amount = parser.parseExpression("1250.75M")
        .getValue(BigDecimal.class);
~~~

Dùng BigDecimal không tự quyết định chính sách làm tròn cho toàn bộ nghiệp vụ. Ứng dụng vẫn cần chọn scale, rounding mode và cách xử lý kết quả theo yêu cầu.

### 5.3. Số thực âm và số mũ

Số âm dùng toán tử trừ một ngôi:

~~~text
-3.14
-0.5F
-1.25e-4
~~~

Phần số mũ có thể mang dấu dương hoặc âm:

~~~text
1.2e3
1.2e+3
1.2e-3
~~~

Hãy kiểm tra dấu chấm, chữ e hoặc E, dấu của số mũ và hậu tố kiểu khi viết literal. Một lỗi nhỏ trong cú pháp có thể khiến parser từ chối biểu thức.

## 6. Kết hợp các literal trong một biểu thức

Literal thường được dùng cùng thuộc tính, biến và toán tử. Ví dụ:

~~~text
age >= 18
price > 0.0
enabled == true and retryCount < 3
discount == null or discount == 0.0
temperature >= 36.0 and temperature <= 37.5
~~~

Một ví dụ dùng dữ liệu từ root object:

~~~java
public class Order {
    private final BigDecimal total;
    private final Boolean approved;
    private final String coupon;

    public Order(BigDecimal total, Boolean approved, String coupon) {
        this.total = total;
        this.approved = approved;
        this.coupon = coupon;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public Boolean getApproved() {
        return approved;
    }

    public String getCoupon() {
        return coupon;
    }
}

Order order = new Order(new BigDecimal("125.50"), true, null);

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "approved == true and total >= 100M and coupon == null"
);

Boolean eligible = expression.getValue(order, Boolean.class);

// eligible == true
~~~

Trong biểu thức trên:

- true là Boolean literal.
- 100M là BigDecimal literal.
- null là null literal.
- approved, total và coupon là các thuộc tính được phân giải từ root object order.

Ví dụ cho thấy các nhóm literal có thể kết hợp trực tiếp với dữ liệu miền nghiệp vụ mà không cần tạo biến trung gian cho từng giá trị cố định.

## 7. Lấy giá trị và kiểu Java từ literal

parseExpression(...) trả về Expression. Gọi getValue() sẽ đánh giá literal và trả về kết quả. Khi cần kiểu cụ thể, có thể dùng getValue(Class<T>):

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object rawBoolean = parser.parseExpression("true").getValue();
Boolean booleanValue = parser.parseExpression("true")
        .getValue(Boolean.class);

Object rawInteger = parser.parseExpression("42").getValue();
Integer integerValue = parser.parseExpression("42")
        .getValue(Integer.class);

Double realValue = parser.parseExpression("3.14")
        .getValue(Double.class);

Object nullValue = parser.parseExpression("null").getValue();
~~~

Kết quả của getValue() có kiểu khai báo Object, nhưng đối tượng thực tế phụ thuộc literal. Khi dùng overload có kiểu, SpEL sử dụng cơ chế chuyển đổi kiểu của EvaluationContext nếu cần và nếu có chuyển đổi phù hợp.

Không nên nhầm việc yêu cầu kiểu kết quả với việc thay đổi cú pháp literal. Ví dụ, hậu tố L thể hiện literal Long, trong khi getValue(Long.class) yêu cầu kết quả được cung cấp dưới dạng Long.

Nếu không thể chuyển đổi kết quả sang kiểu yêu cầu, quá trình đánh giá có thể phát sinh EvaluationException. Hãy chọn kiểu phù hợp với giá trị và hợp đồng dữ liệu của ứng dụng.

## 8. Những lỗi thường gặp

| Cách viết hoặc tình huống | Vấn đề | Cách xử lý |
|---|---|---|
| 'null' | Đây là chuỗi, không phải null. | Dùng null nếu cần giá trị null. |
| 'true' | Đây là chuỗi, không phải Boolean. | Dùng true hoặc false. |
| True, FALSE | Sai cách viết từ khóa Boolean chuẩn. | Dùng chữ thường. |
| '42' | Đây là chuỗi ký tự, không phải số nguyên. | Dùng 42 nếu cần số. |
| '3.14' | Đây là chuỗi, không phải số thực. | Dùng 3.14 hoặc literal có hậu tố kiểu. |
| Dùng literal Long cho biến Integer mà không kiểm tra chuyển đổi | Có thể không phù hợp với kiểu đích. | Chọn kiểu số nhất quán hoặc yêu cầu kiểu kết quả phù hợp. |
| Dùng Double cho phép tính tiền tệ cần độ chính xác thập phân | Có thể gặp sai số dấu phẩy động. | Cân nhắc BigDecimal với hậu tố M. |
| Truy cập thuộc tính tiếp theo từ kết quả null | Có thể phát sinh lỗi đánh giá. | Kiểm tra null trước khi truy cập hoặc thiết kế biểu thức xử lý null phù hợp. |

### 8.1. Phân biệt lỗi cú pháp và lỗi đánh giá

Lỗi cú pháp xảy ra khi chuỗi literal không được parser chấp nhận, chẳng hạn một hậu tố hoặc ký hiệu số không hợp lệ. Lỗi đánh giá có thể xảy ra khi biểu thức hợp lệ nhưng dữ liệu hoặc kiểu kết quả không phù hợp, ví dụ truy cập thuộc tính trên null hoặc không thể chuyển đổi kết quả.

~~~java
try {
    Expression expression = parser.parseExpression("3.14F");
    Float value = expression.getValue(Float.class);
} catch (ParseException ex) {
    // Xử lý cú pháp SpEL không hợp lệ.
} catch (EvaluationException ex) {
    // Xử lý lỗi khi đánh giá hoặc chuyển đổi kết quả.
}
~~~

Khi điều tra lỗi, hãy xác định nó phát sinh tại parseExpression(...) hay getValue(...), sau đó kiểm tra cú pháp literal, kiểu dữ liệu, context và kiểu kết quả được yêu cầu.

## 9. Quy tắc sử dụng trong ứng dụng

1. Viết null, true và false bằng chữ thường, không đặt trong dấu nháy nếu cần giá trị tương ứng.
2. Dùng dấu nháy đơn khi thực sự muốn một chuỗi. Dấu nháy làm thay đổi kiểu và ý nghĩa của literal.
3. Dùng hậu tố L cho số nguyên Long khi cần thể hiện kiểu rõ ràng.
4. Dùng hậu tố F hoặc D khi cần chỉ định Float hoặc Double.
5. Cân nhắc hậu tố M cho BigDecimal trong các phép tính thập phân cần độ chính xác.
6. Dùng 0x cho số nguyên hệ thập lục phân và dùng ký pháp e hoặc E cho số thực dạng khoa học.
7. Chọn kiểu kết quả tường minh qua getValue(Class<T>) khi mã Java cần một kiểu cụ thể.
8. Kiểm tra null trước khi dùng kết quả như một đối tượng có thuộc tính hoặc phương thức.
9. Không coi dữ liệu đầu vào là literal an toàn chỉ vì nó trông giống một con số hoặc từ khóa. Hãy kiểm soát cách ghép chuỗi biểu thức và nguồn dữ liệu được phép đưa vào parser.

## 10. Ghi nhớ

- null biểu diễn giá trị null; true và false biểu diễn Boolean.
- Số nguyên có thể viết ở hệ thập phân hoặc hệ thập lục phân với tiền tố 0x; hậu tố L chỉ định Long.
- Số thực hỗ trợ phần thập phân và ký pháp khoa học; mặc định thường là Double.
- Hậu tố F, D và M lần lượt biểu thị Float, Double và BigDecimal.
- Dấu nháy đơn biến nội dung thành chuỗi; 'true' không giống true.
- Có thể kết hợp literal với thuộc tính, biến và toán tử trong cùng biểu thức SpEL.
- Dùng kiểu kết quả tường minh khi cần hợp đồng dữ liệu rõ ràng và xử lý riêng trường hợp null.
