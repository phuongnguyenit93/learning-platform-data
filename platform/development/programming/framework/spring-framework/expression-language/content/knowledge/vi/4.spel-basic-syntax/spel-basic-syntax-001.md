# Biểu thức nguyên tử và giá trị trả về trong Spring Expression Language

Spring Expression Language (SpEL) cho phép mô tả một giá trị hoặc phép tính bằng chuỗi biểu thức. Có biểu thức rất đơn giản, chẳng hạn một số hoặc chuỗi literal; cũng có biểu thức đọc thuộc tính, lấy biến, gọi phương thức hay kết hợp nhiều toán tử.

Để hiểu cách SpEL xử lý cú pháp cơ bản, cần nắm hai ý:

- **Biểu thức nguyên tử** là những đơn vị cơ bản tạo nên biểu thức lớn hơn, chẳng hạn literal, biến, tham chiếu thuộc tính hoặc lời gọi phương thức.
- **Giá trị trả về** là kết quả mà SpEL tạo ra khi đánh giá biểu thức trong một ngữ cảnh cụ thể. Kiểu và giá trị thực tế phụ thuộc vào biểu thức, dữ liệu và EvaluationContext.

Trong bài này, “nguyên tử” được dùng theo nghĩa sư phạm để chỉ các thành phần cơ bản có thể đứng độc lập hoặc kết hợp thành biểu thức phức tạp hơn.

## 1. Biểu thức SpEL luôn hướng đến một giá trị

Một biểu thức SpEL được phân tích thành đối tượng Expression. Khi ứng dụng gọi getValue(...), SpEL đánh giá biểu thức và trả về một giá trị Java.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("10 + 5");

Object result = expression.getValue();
~~~

Giá trị trả về là số 15. Trong ví dụ này, biểu thức không cần root object hay biến bên ngoài vì tất cả dữ liệu đã nằm trong literal của biểu thức.

Một số biểu thức cơ bản khác:

| Biểu thức | Giá trị trả về | Kiểu thường gặp |
|---|---|---|
| 42 | 42 | Integer |
| 3.14 | 3.14 | Double |
| 'Spring' | Spring | String |
| true | true | Boolean |
| null | null | Không có đối tượng giá trị |
| 10 > 5 | true | Boolean |
| 'Spring'.toUpperCase() | SPRING | String |

Kiểu cụ thể của một biểu thức còn phụ thuộc vào cách viết literal, kiểu dữ liệu của thuộc tính và giá trị trả về của phương thức được gọi.

## 2. Literal — giá trị được viết trực tiếp

Literal là giá trị được ghi ngay trong văn bản biểu thức. SpEL không cần tra cứu biến hay thuộc tính ứng dụng để lấy các giá trị này.

### 2.1. Literal số

Ví dụ:

~~~spel
42
3.14
0x2A
~~~

SpEL hỗ trợ literal số nguyên, số thực và số hexadecimal. Kiểu số được suy ra từ cú pháp literal và có thể được chỉ định bằng hậu tố trong những trường hợp được hỗ trợ.

~~~spel
42L
3.14F
3.14D
~~~

- 42L biểu diễn literal kiểu long.
- 3.14F biểu diễn literal kiểu float.
- 3.14D biểu diễn literal kiểu double.

Khi dùng literal số trong phép toán, cần chú ý kiểu dữ liệu và quy tắc chuyển đổi. Không nên mặc định mọi literal số đều có cùng kiểu Java.

### 2.2. Literal chuỗi

Chuỗi trong SpEL được đặt trong dấu nháy đơn:

~~~spel
'Hello Spring'
'Expression Language'
~~~

Có thể dùng chuỗi làm toán hạng cho phép nối hoặc gọi phương thức:

~~~spel
'Spring' + ' Expression'
'Spring'.toUpperCase()
~~~

Kết quả lần lượt là chuỗi Spring Expression và SPRING.

### 2.3. Literal Boolean và null

SpEL hỗ trợ hai literal logic:

~~~spel
true
false
~~~

Chúng tạo ra giá trị Boolean tương ứng.

Literal null biểu diễn sự vắng mặt của một giá trị tham chiếu:

~~~spel
null
~~~

Khi đánh giá biểu thức null, kết quả là null. Đây là một kết quả hợp lệ, khác với lỗi parsing hoặc lỗi evaluation.

## 3. Tham chiếu thuộc tính và đối tượng hiện tại

Một tên thuộc tính không có tiền tố # thường được tra cứu trên đối tượng hiện tại. Nếu không có ngữ cảnh khác, đối tượng hiện tại ban đầu là root object.

Giả sử có lớp Product:

~~~java
public class Product {
    private final String name;
    private final BigDecimal price;

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Có thể đánh giá thuộc tính name như sau:

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String name = expression.getValue(product, String.class);
~~~

Kết quả là Keyboard.

Biểu thức name được tra cứu trên root object product. Với cú pháp truy cập lồng nhau, có thể viết:

~~~spel
customer.name
customer.address.city
~~~

Mỗi dấu chấm chuyển việc truy cập sang đối tượng được trả về từ phần đứng trước. Nếu một phần tử trung gian là null, truy cập tiếp theo có thể phát sinh lỗi evaluation. Có thể dùng toán tử null-safe navigation ?. trong những trường hợp phù hợp để tránh truy cập tiếp trên đối tượng null.

Ví dụ:

~~~spel
customer?.address?.city
~~~

Khi customer hoặc address là null, phần truy cập null-safe tương ứng trả về null thay vì tiếp tục dereference đối tượng null.

## 4. Biến và các tham chiếu đặc biệt

Biến trong SpEL được viết với tiền tố #. Giá trị của biến phải được cung cấp trong EvaluationContext.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("minimum", new BigDecimal("500000"));
context.setVariable("customerName", "Linh");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#minimum");

Object result = expression.getValue(context);
~~~

Kết quả là đối tượng BigDecimal có giá trị 500000.

Các biến có thể được kết hợp với literal, thuộc tính và toán tử:

~~~spel
#minimum * 2
#customerName.toUpperCase()
price >= #minimum
~~~

SpEL còn có hai biến đặc biệt:

- #root tham chiếu root object của lần đánh giá.
- #this tham chiếu đối tượng đang được đánh giá tại vị trí hiện tại. Trong các phép xử lý collection như selection hoặc projection, #this có thể thay đổi theo từng phần tử.

Ví dụ, nếu root object là Product, biểu thức sau đọc rõ thuộc tính từ đối tượng gốc:

~~~spel
#root.name
~~~

## 5. Lời gọi phương thức và giá trị trả về

Một biểu thức có thể gọi phương thức trên đối tượng hoặc giá trị được truy cập. Giá trị của biểu thức gọi phương thức là giá trị mà phương thức Java trả về.

Ví dụ:

~~~spel
'Spring'.toUpperCase()
'Spring'.length()
~~~

Kết quả tương ứng là chuỗi SPRING và số 6.

Với root object:

~~~java
Expression expression =
    parser.parseExpression("name.toUpperCase()");

String result = expression.getValue(product, String.class);
~~~

SpEL đọc thuộc tính name trên product, sau đó gọi toUpperCase() trên chuỗi nhận được.

Việc tìm phương thức phù hợp được hỗ trợ bởi MethodResolver trong EvaluationContext. Nếu phương thức không tồn tại, không thể truy cập hoặc đối số không tương thích, evaluation có thể thất bại.

## 6. Tham chiếu kiểu và khởi tạo đối tượng

SpEL có thể tham chiếu kiểu Java bằng toán tử T(...). Đây là một biểu thức tạo ra tham chiếu đến đối tượng Class tương ứng.

~~~spel
T(java.lang.Math)
~~~

Có thể kết hợp tham chiếu kiểu với lời gọi phương thức static:

~~~spel
T(java.lang.Math).abs(-10)
~~~

Giá trị trả về là số 10.

SpEL cũng hỗ trợ tạo đối tượng bằng toán tử new:

~~~spel
new java.lang.String('Spring')
~~~

Kết quả là một đối tượng String có nội dung Spring.

Các thao tác này phụ thuộc vào TypeLocator và ConstructorResolver cùng những quy tắc truy cập của EvaluationContext. Một context bị giới hạn có thể không cho phép mọi khả năng tham chiếu kiểu hoặc khởi tạo đối tượng.

## 7. Biểu thức toán học và logic tạo ra giá trị mới

Các toán tử kết hợp những biểu thức nguyên tử thành biểu thức lớn hơn. Giá trị trả về phụ thuộc vào loại toán tử.

| Nhóm | Ví dụ | Giá trị trả về |
|---|---|---|
| Số học | 10 + 5 | Giá trị số 15 |
| So sánh | 10 >= 5 | Boolean true |
| Logic | true && false | Boolean false |
| Nối chuỗi | 'Spring' + ' EL' | String Spring EL |
| Điều kiện | true ? 'YES' : 'NO' | String YES |
| Elvis | name ?: 'Unknown' | name nếu có giá trị, nếu không thì Unknown |

Ví dụ:

~~~spel
(10 + 5) * 2
~~~

Kết quả là 30.

~~~spel
total >= #minimum && status == 'PAID'
~~~

Kết quả là Boolean. SpEL cần đọc total, minimum và status rồi đánh giá các phép so sánh trước khi kết hợp chúng bằng &&.

Khi biểu thức có nhiều toán tử, thứ tự ưu tiên và dấu ngoặc quyết định cách nhóm các phép toán. Dùng dấu ngoặc khi muốn làm rõ ý định hoặc thay đổi thứ tự đánh giá.

## 8. Collection, inline list và inline map

SpEL có thể tạo collection ngay trong biểu thức. Đây là những biểu thức có kết quả là một cấu trúc dữ liệu thay vì một giá trị đơn lẻ.

### 8.1. Inline list

~~~spel
{1, 2, 3}
~~~

Biểu thức tạo ra một danh sách các giá trị. Có thể truy cập phần tử bằng index:

~~~spel
{ 'Java', 'Spring', 'SpEL' }[1]
~~~

Kết quả là Spring.

### 8.2. Inline map

~~~spel
{ 'name': 'Linh', 'active': true }
~~~

Biểu thức tạo ra map gồm các cặp key-value. Có thể lấy giá trị theo key bằng indexer:

~~~spel
{ 'name': 'Linh', 'active': true }['name']
~~~

Kết quả là Linh.

### 8.3. Selection và projection

Selection lọc phần tử collection theo điều kiện:

~~~spel
{1, 2, 3, 4, 5}.?[#this > 3]
~~~

Kết quả là collection gồm các phần tử 4 và 5.

Projection tạo collection mới từ kết quả đánh giá trên từng phần tử:

~~~spel
{1, 2, 3}.![#this * 10]
~~~

Kết quả là collection gồm 10, 20 và 30.

Vì vậy, giá trị trả về của một biểu thức collection có thể là list hoặc map, và biểu thức tiếp theo có thể tiếp tục thao tác trên collection đó.

## 9. Kiểu giá trị trả về và cách nhận kết quả trong Java

Expression cung cấp nhiều overload getValue để phù hợp với cách ứng dụng cần đánh giá.

### 9.1. Nhận kết quả dưới dạng Object

~~~java
Object result = expression.getValue(context);
~~~

Cách này linh hoạt khi kiểu kết quả chưa biết trước. Ứng dụng cần kiểm tra hoặc ép kiểu phù hợp trước khi sử dụng.

### 9.2. Yêu cầu kiểu kết quả

~~~java
Boolean result =
    expression.getValue(context, Boolean.class);
~~~

Overload có tham số Class<T> thể hiện kiểu mà ứng dụng mong muốn nhận. SpEL có thể sử dụng TypeConverter của context để chuyển đổi giá trị khi việc chuyển đổi được hỗ trợ.

Ví dụ, biểu thức số có thể được yêu cầu trả về một kiểu số tương thích:

~~~java
Integer result =
    parser.parseExpression("10 + 5")
          .getValue(Integer.class);
~~~

Kết quả là Integer có giá trị 15.

Nếu kết quả không thể chuyển đổi sang kiểu yêu cầu, lời gọi có thể phát sinh lỗi. Vì vậy, kiểu đích nên phù hợp với giá trị mà biểu thức thực sự tạo ra.

### 9.3. Truyền root object trực tiếp

Nếu không cần cấu hình context riêng, có thể truyền root object trực tiếp:

~~~java
Expression expression =
    parser.parseExpression("price * 2");

BigDecimal result =
    expression.getValue(product, BigDecimal.class);
~~~

Trong trường hợp này, product được dùng làm root object của lần đánh giá.

### 9.4. Phân biệt kiểu khai báo, kiểu runtime và kiểu đích

Ba khái niệm này không nên bị nhầm lẫn:

- **Kiểu khai báo:** kiểu được định nghĩa trong lớp Java, ví dụ getter getPrice() trả về BigDecimal.
- **Kiểu runtime:** kiểu thực tế của đối tượng hoặc giá trị mà expression tạo ra trong lần đánh giá.
- **Kiểu đích:** kiểu ứng dụng yêu cầu thông qua overload getValue(..., Class<T>).

Ba kiểu có thể trùng nhau, nhưng không bắt buộc. Cơ chế chuyển đổi của SpEL có thể giúp chuyển đổi khi tương thích.

## 10. Giá trị null và các trường hợp không có kết quả thông thường

null là một giá trị hợp lệ trong SpEL. Ví dụ:

~~~spel
null
~~~

Hoặc một thuộc tính có thể trả về null:

~~~spel
customer.nickname
~~~

Nếu nickname có giá trị null, expression có thể trả về null. Điều đó khác với trường hợp không tìm thấy thuộc tính hoặc không thể thực hiện thao tác.

Cần phân biệt:

- **Kết quả null:** biểu thức được đánh giá và giá trị nhận được là null.
- **Lỗi evaluation:** SpEL không thể hoàn tất thao tác, ví dụ dereference null ở vị trí không được bảo vệ, biến không tồn tại hoặc không tìm thấy phương thức phù hợp.
- **Lỗi parsing:** văn bản không tạo được cấu trúc biểu thức hợp lệ.

Đối với truy cập thuộc tính có khả năng null, toán tử null-safe navigation có thể giúp biểu thức trả về null thay vì phát sinh lỗi do truy cập tiếp trên đối tượng null.

## 11. Ví dụ tổng hợp các loại giá trị trả về

Các ví dụ sau minh họa rằng SpEL không chỉ trả về Boolean:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Object number = parser.parseExpression("10 + 5").getValue();
Object text = parser.parseExpression("'Spring'").getValue();
Object flag = parser.parseExpression("10 > 5").getValue();
Object list = parser.parseExpression("{1, 2, 3}").getValue();
Object map = parser.parseExpression(
    "{'name': 'Linh', 'active': true}"
).getValue();
Object empty = parser.parseExpression("null").getValue();
~~~

Có thể mô tả kết quả:

| Biến Java | Kiểu giá trị | Giá trị minh họa |
|---|---|---|
| number | Number | 15 |
| text | String | Spring |
| flag | Boolean | true |
| list | List | [1, 2, 3] |
| map | Map | {name=Linh, active=true} |
| empty | null | null |

Kiểu cụ thể của number phụ thuộc vào kiểu literal và quy tắc phép toán. Khi ứng dụng cần một kiểu xác định, nên sử dụng overload getValue có kiểu đích.

## 12. Cách đọc một biểu thức từ trái sang phải

Giả sử có biểu thức:

~~~spel
customer.orders.?[total >= #minimum].![total * #taxRate]
~~~

Có thể đọc theo từng phần:

1. customer.orders: lấy collection orders từ customer.
2. ?[total >= #minimum]: lọc các đơn hàng có total đạt ngưỡng minimum.
3. ![total * #taxRate]: tạo collection mới, mỗi phần tử là total nhân với taxRate.
4. Toàn biểu thức trả về collection chứa kết quả phép tính trên các đơn hàng đã lọc.

Trong quá trình này, #this thay đổi theo phần tử đang được xét trong selection hoặc projection. #root vẫn giữ root object của lần đánh giá.

Ví dụ cho thấy một biểu thức có thể kết hợp nhiều đơn vị cơ bản. Giá trị trả về của một phần trở thành đầu vào cho phần tiếp theo.

## 13. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Literal và biến có cùng cách lấy giá trị.**  
Literal nằm ngay trong biểu thức; biến dạng #name được tra cứu trong EvaluationContext.

**Nhầm lẫn 2: Tên thuộc tính luôn là biến.**  
total thường được đọc từ đối tượng hiện tại; #minimum được đọc từ tập biến của context.

**Nhầm lẫn 3: Parsing đã tạo ra kết quả nghiệp vụ.**  
Parsing tạo cấu trúc Expression. Kết quả chỉ được tính khi gọi getValue trong môi trường đánh giá.

**Nhầm lẫn 4: Mọi expression đều trả về String hoặc Boolean.**  
Kết quả có thể là số, chuỗi, boolean, object, collection, map hoặc null.

**Nhầm lẫn 5: getValue(context, String.class) chỉ ép kiểu Java.**  
SpEL có thể sử dụng TypeConverter để chuyển đổi giá trị khi được hỗ trợ. Nếu không thể chuyển đổi, evaluation có thể thất bại.

**Nhầm lẫn 6: null luôn có nghĩa là lỗi.**  
null có thể là giá trị trả về hợp lệ. Lỗi chỉ xảy ra khi biểu thức không thể thực hiện thao tác cần thiết.

## 14. Ghi nhớ

- Literal, thuộc tính, biến và lời gọi phương thức là những thành phần cơ bản có thể kết hợp thành biểu thức lớn hơn.
- Mỗi biểu thức được đánh giá sẽ tạo ra một giá trị, với kiểu phụ thuộc vào cú pháp và dữ liệu runtime.
- Các toán tử có thể tạo giá trị mới, đặc biệt là Boolean trong phép so sánh và logic.
- Inline list, inline map, selection và projection có thể trả về collection hoặc map.
- Expression.getValue() trả về Object; overload có kiểu đích giúp ứng dụng yêu cầu kiểu mong muốn.
- EvaluationContext cung cấp biến, root object và các cơ chế truy cập hoặc chuyển đổi cần thiết.
- null là kết quả hợp lệ và cần được phân biệt với lỗi parsing hoặc evaluation.
- Khi cần phân tích lỗi, xác định lỗi xảy ra lúc parseExpression hay getValue trước khi kiểm tra cú pháp hoặc dữ liệu runtime.

Khi đọc một biểu thức SpEL, hãy xác định các thành phần cơ bản, theo dõi giá trị của từng phần khi đánh giá, rồi xác định kiểu và giá trị mà nút biểu thức ngoài cùng trả về. Đó là cách hiểu chính xác mối quan hệ giữa cú pháp cơ bản và kết quả cuối cùng.
