# Biểu thức nguyên tử và giá trị trả về trong Spring Expression Language

Spring Expression Language (SpEL) dùng một cú pháp biểu thức để truy cập dữ liệu và tính toán trên các đối tượng Java. Một biểu thức có thể chỉ là một giá trị đơn giản như `42`, nhưng cũng có thể kết hợp thuộc tính, biến, lời gọi phương thức và toán tử thành một phép tính phức tạp.

Để đọc cú pháp SpEL chính xác, cần phân biệt hai khái niệm:

- **Biểu thức nguyên tử (atomic expression):** thành phần cơ bản có thể cung cấp một giá trị hoặc một đối tượng làm đầu vào cho biểu thức khác, chẳng hạn literal, tham chiếu biến, thuộc tính, lời gọi phương thức hoặc tham chiếu kiểu.
- **Giá trị trả về (evaluation result):** giá trị mà SpEL tạo ra khi đánh giá biểu thức trong một ngữ cảnh cụ thể. Giá trị có thể là số, chuỗi, Boolean, object, collection, map hoặc null.

Các thành phần nguyên tử thường được kết hợp với toán tử và dấu ngoặc để tạo biểu thức lớn hơn. Khi ứng dụng gọi `getValue(...)`, SpEL đánh giá cấu trúc đó và trả về giá trị cuối cùng.

## 1. Một biểu thức SpEL được tạo từ những thành phần nào?

Có thể chia cú pháp cơ bản thành ba nhóm:

1. **Giá trị và tham chiếu:** literal, tên thuộc tính, biến, root object, tham chiếu kiểu và tham chiếu bean.
2. **Truy cập và gọi:** truy cập thuộc tính, indexer, lời gọi phương thức và khởi tạo đối tượng.
3. **Kết hợp và biến đổi:** toán tử số học, so sánh, logic, điều kiện, selection, projection và các phép thao tác collection.

Ví dụ:

~~~spel
customer.orders.?[total >= #minimum].![total * #taxRate]
~~~

Biểu thức trên kết hợp nhiều thành phần: truy cập thuộc tính, selection, biến, phép so sánh, projection và phép nhân. Giá trị trả về là collection được tạo từ những đơn hàng thỏa điều kiện.

## 2. Literal: giá trị được viết trực tiếp

Literal là thành phần đơn giản nhất. Giá trị của nó được xác định ngay trong chuỗi biểu thức, không cần tra cứu từ root object hoặc biến.

### 2.1. Literal số

~~~spel
42
3.14
0x2A
42L
3.14F
3.14D
3.14M
~~~

SpEL hỗ trợ số nguyên, số thực và số hexadecimal. Một số hậu tố thường gặp:

- `L`: chỉ định literal kiểu long.
- `F`: chỉ định literal kiểu float.
- `D`: chỉ định literal kiểu double.
- `M`: chỉ định literal kiểu BigDecimal.

Ví dụ, `42L` là literal long, còn `3.14M` là literal BigDecimal. Kiểu số cụ thể quan trọng khi biểu thức kết hợp nhiều kiểu toán hạng hoặc khi ứng dụng yêu cầu kiểu kết quả cụ thể.

### 2.2. Literal chuỗi

Chuỗi được đặt trong dấu nháy đơn:

~~~spel
'Spring'
'Expression Language'
'Hello, SpEL!'
~~~

Chuỗi có thể được dùng trực tiếp hoặc kết hợp với toán tử và lời gọi phương thức:

~~~spel
'Spring' + ' Expression'
'Spring'.toUpperCase()
~~~

Kết quả lần lượt là `Spring Expression` và `SPRING`.

### 2.3. Literal Boolean và null

~~~spel
true
false
null
~~~

Hai literal đầu tạo giá trị Boolean. Literal `null` tạo ra giá trị tham chiếu rỗng. Kết quả null là hợp lệ và cần được phân biệt với lỗi xảy ra trong quá trình đánh giá.

## 3. Tham chiếu thuộc tính và root object

Một tên định danh không có tiền tố `#` thường được hiểu là thuộc tính hoặc thành phần của đối tượng hiện tại.

Giả sử có lớp:

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

Có thể đánh giá thuộc tính `name` trên root object:

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String name = expression.getValue(product, String.class);
~~~

Kết quả là `Keyboard`.

Các biểu thức thuộc tính có thể nối tiếp nhau bằng dấu chấm:

~~~spel
customer.name
customer.address.city
product.category.name
~~~

SpEL đọc phần đầu trên đối tượng hiện tại, sau đó tiếp tục truy cập thuộc tính của đối tượng được trả về.

Hai tham chiếu đặc biệt giúp xác định đối tượng hiện tại:

- `#root` luôn tham chiếu root object của lần đánh giá.
- `#this` tham chiếu đối tượng đang là mục tiêu đánh giá hiện tại. Trong selection hoặc projection trên collection, đối tượng này có thể thay đổi theo từng phần tử.

Ví dụ:

~~~spel
#root.customer.name
~~~

Biểu thức trên chỉ rõ rằng name được đọc từ customer thuộc root object.

## 4. Biến: tham chiếu giá trị từ EvaluationContext

Biến có tiền tố `#`. Ứng dụng đăng ký biến trên EvaluationContext rồi biểu thức tham chiếu đến tên biến đó.

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

Kết quả là giá trị BigDecimal đã đăng ký cho biến `minimum`.

Biến có thể kết hợp với những thành phần khác:

~~~spel
#minimum * 2
#customerName.toUpperCase()
price >= #minimum
~~~

Cần phân biệt `minimum` và `#minimum`:

- `minimum` là tên thuộc tính được tra cứu trên đối tượng hiện tại.
- `#minimum` là biến được tra cứu trong EvaluationContext.

Nếu biến chưa được đăng ký hoặc tên biến không khớp, biểu thức có thể không đánh giá được như mong đợi.

## 5. Truy cập thuộc tính, indexer và lời gọi phương thức

Ngoài việc tham chiếu trực tiếp, SpEL cho phép tiếp tục thao tác trên giá trị được trả về từ một thành phần nguyên tử.

### 5.1. Truy cập thuộc tính

~~~spel
customer.name
customer.address.city
~~~

Mỗi dấu chấm chuyển sang đối tượng được trả về từ phần trước. Việc đọc thuộc tính được thực hiện thông qua PropertyAccessor phù hợp trong EvaluationContext.

### 5.2. Indexer

Indexer dùng dấu ngoặc vuông để truy cập phần tử theo chỉ số hoặc khóa:

~~~spel
items[0]
customerMap['primary']
'Spring'[0]
~~~

Tùy đối tượng, indexer có thể truy cập phần tử của array, list, map hoặc chuỗi. Ví dụ, `'Spring'[0]` lấy ký tự đầu tiên theo cơ chế indexer của SpEL.

Với map, biểu thức trong ngoặc vuông được dùng làm khóa. Với list hoặc array, chỉ số xác định phần tử cần đọc.

### 5.3. Lời gọi phương thức

Tên phương thức theo sau bởi cặp ngoặc và danh sách đối số:

~~~spel
'Spring'.toUpperCase()
'Spring'.substring(0, 3)
customer.isActive()
~~~

Giá trị của biểu thức lời gọi phương thức là giá trị mà phương thức Java trả về. Nếu phương thức trả về String, expression có thể tạo ra String; nếu trả về Boolean, kết quả có thể là Boolean.

SpEL sử dụng MethodResolver trong context để tìm phương thức phù hợp. Việc gọi thành công phụ thuộc vào đối tượng hiện tại, tên phương thức, số lượng và kiểu đối số, cũng như khả năng truy cập được cấu hình.

## 6. Tham chiếu kiểu, thành viên static và khởi tạo đối tượng

SpEL có thể tham chiếu kiểu Java bằng toán tử `T(...)`:

~~~spel
T(java.lang.Math)
~~~

Tham chiếu kiểu thường được dùng để gọi thành viên static:

~~~spel
T(java.lang.Math).abs(-10)
T(java.lang.Math).max(10, 25)
~~~

Kết quả tương ứng là `10` và `25`.

Toán tử `new` cho phép khởi tạo đối tượng:

~~~spel
new java.lang.String('Spring')
~~~

Biểu thức tạo một đối tượng String có nội dung Spring.

Việc tham chiếu kiểu và khởi tạo đối tượng phụ thuộc vào TypeLocator, ConstructorResolver và khả năng mà EvaluationContext cho phép. Không phải context nào cũng mở mọi tính năng này.

## 7. Tham chiếu bean

Trong môi trường Spring có cấu hình BeanResolver, biểu thức có thể tham chiếu bean theo tên bằng ký hiệu `@`:

~~~spel
@systemProperties
~~~

Có thể truy cập thuộc tính hoặc gọi phương thức trên bean được giải quyết:

~~~spel
@environment.getProperty('app.name')
~~~

Cú pháp này hữu ích khi biểu thức cần sử dụng một thành phần do Spring quản lý. Tuy nhiên, việc phân giải bean phải được hỗ trợ và cấu hình trong EvaluationContext. Chỉ viết `@beanName` không tự động khiến mọi context tìm được bean.

## 8. Toán tử kết hợp các thành phần nguyên tử

Thành phần nguyên tử thường là toán hạng cho các toán tử. Kết quả của toán tử lại có thể trở thành một biểu thức con trong phép tính lớn hơn.

| Nhóm | Ví dụ | Kiểu kết quả thường gặp |
|---|---|---|
| Số học | `10 + 5`, `10 * 2` | Number |
| So sánh | `10 >= 5`, `'A' == 'A'` | Boolean |
| Logic | `true && false` | Boolean |
| Nối chuỗi | `'Spring' + ' EL'` | String |
| Điều kiện | `true ? 'YES' : 'NO'` | Kiểu của nhánh được chọn |
| Elvis | `name ?: 'Unknown'` | Giá trị name hoặc giá trị mặc định |
| Kiểm tra kiểu | `'text' instanceof T(String)` | Boolean |
| Biểu thức chính quy | `'abc' matches 'a.*'` | Boolean |

Ví dụ, biểu thức:

~~~spel
(price * quantity) >= #minimum
~~~

được tạo từ hai tham chiếu, phép nhân và phép so sánh. Phép nhân tạo ra một giá trị số; phép so sánh dùng giá trị đó để tạo Boolean.

Dấu ngoặc giúp nhóm các biểu thức con và làm rõ thứ tự thực hiện. Khi có nhiều toán tử, thứ tự ưu tiên của SpEL quyết định cách phân tích nếu không có dấu ngoặc.

## 9. Inline collection, map, selection và projection

SpEL có thể tạo cấu trúc dữ liệu ngay trong biểu thức.

### 9.1. Inline list

~~~spel
{1, 2, 3}
~~~

Biểu thức tạo một list. Có thể truy cập phần tử bằng indexer:

~~~spel
{'Java', 'Spring', 'SpEL'}[1]
~~~

Kết quả là `Spring`.

### 9.2. Inline map

~~~spel
{'name': 'Linh', 'active': true}
~~~

Biểu thức tạo một map chứa các cặp key-value. Có thể truy cập giá trị bằng khóa:

~~~spel
{'name': 'Linh', 'active': true}['name']
~~~

Kết quả là `Linh`.

### 9.3. Selection

Selection lọc phần tử collection theo điều kiện:

~~~spel
{1, 2, 3, 4, 5}.?[#this > 3]
~~~

Kết quả là collection gồm các phần tử 4 và 5. Trong điều kiện selection, `#this` tham chiếu phần tử đang được xét.

SpEL cũng có các dạng selection lấy phần tử đầu tiên hoặc cuối cùng thỏa điều kiện, dùng các toán tử `.^[...]` và `.$[...]`.

### 9.4. Projection

Projection tạo collection mới bằng cách đánh giá một biểu thức trên từng phần tử:

~~~spel
{1, 2, 3}.![#this * 10]
~~~

Kết quả là collection gồm 10, 20 và 30.

Giá trị trả về của selection hoặc projection là collection hoặc giá trị tương ứng theo dạng thao tác được sử dụng.

## 10. Null, null-safe navigation và Elvis

SpEL có thể trả về null khi biểu thức là literal null hoặc khi một thuộc tính có giá trị null:

~~~spel
null
customer.nickname
~~~

Truy cập tiếp trên một đối tượng null có thể gây lỗi. Toán tử null-safe navigation `?.` giúp dừng việc truy cập khi đối tượng ở bên trái là null:

~~~spel
customer?.address?.city
~~~

Nếu customer hoặc address là null, biểu thức trả về null tại vị trí truy cập tương ứng.

Toán tử Elvis `?:` cung cấp giá trị thay thế khi biểu thức bên trái là null:

~~~spel
customer.nickname ?: 'Unknown'
~~~

Nếu nickname có giá trị, kết quả là nickname; nếu null, kết quả là chuỗi Unknown.

Null là một giá trị có thể trả về hợp lệ. Nó khác với lỗi evaluation do không thể thực hiện thao tác.

## 11. Giá trị trả về của Expression trong Java

Expression cung cấp các overload getValue để lấy kết quả theo cách phù hợp.

### 11.1. Lấy kết quả dưới dạng Object

~~~java
Object value = expression.getValue(context);
~~~

Cách này phù hợp khi kiểu kết quả chưa biết trước. Giá trị trả về có thể là một object thuộc bất kỳ kiểu nào mà biểu thức tạo ra, hoặc null.

### 11.2. Yêu cầu kiểu kết quả

~~~java
Boolean result =
    expression.getValue(context, Boolean.class);
~~~

Overload có kiểu đích cho phép ứng dụng chỉ rõ kiểu mong muốn. SpEL có thể sử dụng TypeConverter của context để chuyển đổi nếu có thể.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("10 + 5");

Integer result = expression.getValue(Integer.class);
~~~

Kết quả là Integer có giá trị 15.

Nếu giá trị không thể chuyển đổi sang kiểu đích, evaluation có thể phát sinh lỗi. Vì vậy, nên chọn kiểu đích phù hợp với kết quả dự kiến.

### 11.3. Truyền root object trực tiếp

Khi không cần cấu hình context riêng, có thể truyền root object trực tiếp:

~~~java
Expression expression =
    parser.parseExpression("price * 2");

BigDecimal result =
    expression.getValue(product, BigDecimal.class);
~~~

Ở đây product là root object của lần đánh giá.

## 12. Một biểu thức có thể trả về những kiểu nào?

| Dạng biểu thức | Ví dụ | Kết quả |
|---|---|---|
| Literal số | `42` | Number |
| Literal chuỗi | `'Spring'` | String |
| Literal logic | `true` | Boolean |
| Literal null | `null` | null |
| Thuộc tính | `product.price` | Kiểu của thuộc tính |
| Biến | `#minimum` | Kiểu của giá trị biến |
| Phép so sánh | `price > 100` | Boolean |
| Phép tính | `price * 2` | Kiểu số phù hợp |
| Gọi phương thức | `name.toUpperCase()` | Kiểu phương thức trả về |
| Inline list | `{1, 2, 3}` | List |
| Inline map | `{'a': 1}` | Map |
| Selection / Projection | `items.?[active]` | Collection hoặc kết quả theo phép chọn |

Kiểu trả về không chỉ được quyết định bởi tên biểu thức. Nó còn phụ thuộc vào kiểu thực tế của đối tượng, giá trị biến, phương thức được gọi và các phép chuyển đổi trong context.

## 13. Ví dụ tổng hợp: từ thành phần nguyên tử đến giá trị cuối cùng

Giả sử có lớp Product với thuộc tính name và price. Ứng dụng muốn kiểm tra giá sản phẩm có đạt ngưỡng tối thiểu và tạo thông báo tương ứng.

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "price >= #minimum ? name.toUpperCase() : 'BELOW LIMIT'"
);

StandardEvaluationContext context =
    new StandardEvaluationContext(product);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

String result = expression.getValue(context, String.class);
~~~

Kết quả:

~~~text
KEYBOARD
~~~

Có thể phân rã biểu thức như sau:

1. `price` là tham chiếu thuộc tính trên root object.
2. `#minimum` là biến lấy từ EvaluationContext.
3. `price >= #minimum` là biểu thức so sánh tạo Boolean.
4. Toán tử điều kiện `?:` chọn một trong hai nhánh dựa trên Boolean.
5. `name.toUpperCase()` đọc thuộc tính name rồi gọi phương thức trên chuỗi.
6. Nhánh được chọn tạo chuỗi KEYBOARD.
7. `getValue(context, String.class)` trả kết quả theo kiểu String mà ứng dụng yêu cầu.

Nếu minimum tăng lên 900000, nhánh đầu không được chọn và kết quả trở thành BELOW LIMIT. Expression vẫn giữ nguyên; dữ liệu trong context quyết định nhánh và giá trị cuối cùng.

## 14. Phân biệt kết quả null với lỗi

Khi làm việc với giá trị trả về, cần phân biệt ba tình huống:

- **Giá trị bình thường:** biểu thức đánh giá thành công và trả về số, chuỗi, Boolean, object hoặc collection.
- **Giá trị null:** biểu thức đánh giá thành công nhưng giá trị của nó là null.
- **Lỗi:** SpEL không thể phân tích hoặc thực hiện biểu thức, ví dụ sai cú pháp, biến không tồn tại, không truy cập được thuộc tính hoặc không chuyển đổi được kiểu.

Lỗi parsing thường xảy ra khi gọi parseExpression. Lỗi evaluation thường xuất hiện khi gọi getValue.

Nếu ứng dụng cần xử lý null, có thể kiểm tra giá trị trả về hoặc dùng các cú pháp như null-safe navigation và Elvis phù hợp với mục đích biểu thức.

## 15. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Mọi tên không có dấu # đều là biến.**  
Tên như price thường được tra cứu như thuộc tính trên đối tượng hiện tại. Biến được tham chiếu bằng #price.

**Nhầm lẫn 2: Literal và giá trị runtime là một.**  
Literal được viết trực tiếp trong biểu thức. Giá trị runtime của thuộc tính hoặc biến chỉ được xác định khi evaluation diễn ra.

**Nhầm lẫn 3: Biểu thức luôn trả về kiểu đã biết khi parsing.**  
Kiểu kết quả thực tế có thể phụ thuộc vào dữ liệu runtime và phương thức được gọi.

**Nhầm lẫn 4: null có nghĩa là parsing thất bại.**  
null có thể là kết quả hợp lệ của một biểu thức đã được phân tích và đánh giá thành công.

**Nhầm lẫn 5: Kiểu đích của getValue làm thay đổi phép tính.**  
Kiểu đích quy định dạng kết quả mà ứng dụng muốn nhận. Logic biểu thức vẫn được xác định bởi cú pháp SpEL.

## 16. Ghi nhớ

- Literal, thuộc tính, biến, lời gọi phương thức và tham chiếu kiểu là những thành phần cơ bản có thể cung cấp giá trị cho biểu thức.
- Tên thuộc tính thường được tra cứu trên root object hoặc đối tượng hiện tại; tên biến có tiền tố # và được lấy từ EvaluationContext.
- Indexer, lời gọi phương thức và toán tử cho phép kết hợp các thành phần thành biểu thức phức tạp.
- Biểu thức có thể trả về Number, String, Boolean, object, collection, map hoặc null.
- getValue() trả kết quả dưới dạng Object; overload có kiểu đích giúp ứng dụng yêu cầu kiểu mong muốn.
- TypeConverter của context có thể hỗ trợ chuyển đổi kiểu khi tương thích.
- null là kết quả hợp lệ và khác với lỗi parsing hoặc evaluation.

Khi phân tích một biểu thức SpEL, hãy xác định từng thành phần cơ bản, xem mỗi thành phần lấy giá trị từ đâu, theo dõi cách toán tử kết hợp chúng và cuối cùng kiểm tra kiểu cùng giá trị mà getValue trả về.
