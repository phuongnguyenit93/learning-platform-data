# setVariable và cú pháp #variable trong Spring Expression Language

Spring Expression Language (SpEL) cho phép một biểu thức sử dụng dữ liệu được cung cấp từ bên ngoài chuỗi biểu thức. Cách phổ biến là đăng ký một biến trong \`EvaluationContext\` rồi tham chiếu biến đó bằng cú pháp \`#variableName\`.

Trong Java, với \`StandardEvaluationContext\`, ứng dụng có thể dùng \`setVariable(name, value)\` để đăng ký giá trị. Khi viết expression, tên biến có tiền tố \`#\`. Ví dụ, đăng ký \`minimum\` bằng \`context.setVariable("minimum", ...)\`, rồi tham chiếu bằng \`#minimum\`.

Hai phía phải dùng cùng tên biến. Khi hiểu rõ quy ước này, có thể truyền dữ liệu, object, collection hoặc giá trị cấu hình vào SpEL mà không phải nhúng dữ liệu trực tiếp vào chuỗi biểu thức.

## 1. Biến trong SpEL là gì?

Biến là một giá trị được lưu trong EvaluationContext và được expression truy cập bằng tên có tiền tố \`#\`.

Ví dụ:

~~~spel
#minimum
#customerName
#order.total
~~~

Trong đó:

- \`#minimum\` tham chiếu biến tên minimum.
- \`#customerName\` tham chiếu biến customerName.
- \`#order.total\` lấy biến order rồi đọc property total trên object đó.

Biến có thể chứa nhiều kiểu dữ liệu:

- String, Boolean và các kiểu số.
- Object domain như Customer, Order hoặc Product.
- Collection, array và Map.
- Object dịch vụ hoặc object tiện ích nếu ứng dụng chủ động cung cấp.

SpEL không cần biết trước kiểu cụ thể của mọi biến khi parse expression. Giá trị thực tế được tra cứu trong context tại thời điểm evaluation.

## 2. Đăng ký biến bằng setVariable

Với \`StandardEvaluationContext\`, phương thức \`setVariable(String name, Object value)\` đăng ký hoặc cập nhật một biến.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("minimum", 500);
context.setVariable("customerName", "Linh");
context.setVariable("active", true);
~~~

Tên truyền vào \`setVariable\` không có tiền tố \`#\`. Tiền tố chỉ xuất hiện khi tham chiếu biến trong chuỗi SpEL.

Ví dụ, sau khi đăng ký:

~~~java
context.setVariable("minimum", 500);
~~~

biểu thức sử dụng:

~~~spel
#minimum
~~~

Không viết tên biến thành \`"#minimum"\` trong lời gọi setVariable. Tên đăng ký là \`"minimum"\`; cú pháp \`#minimum\` thuộc về expression.

## 3. Đọc biến bằng cú pháp #variable

Sau khi biến được đăng ký, SpEL có thể đọc giá trị bằng tên có tiền tố \`#\`.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", "Linh");

ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#customerName");

String name =
    expression.getValue(context, String.class);
~~~

Kết quả:

~~~text
Linh
~~~

Quá trình gồm ba bước:

1. Tạo EvaluationContext.
2. Đăng ký giá trị dưới tên customerName.
3. Parse expression có tham chiếu #customerName và đánh giá với context.

Nếu context không được truyền vào lần đánh giá, expression không có dữ liệu biến từ context đã tạo. Vì vậy, hãy bảo đảm lời gọi getValue sử dụng đúng EvaluationContext chứa các biến cần thiết.

## 4. Dùng nhiều biến trong một expression

Một biểu thức có thể tham chiếu nhiều biến cùng lúc:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("price", new BigDecimal("250000"));
context.setVariable("quantity", 3);
context.setVariable("taxRate", new BigDecimal("0.10"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#price * #quantity * (1 + #taxRate)"
);

BigDecimal total =
    expression.getValue(context, BigDecimal.class);
~~~

Kết quả:

~~~text
825000.00
~~~

Mỗi biến cung cấp một toán hạng cho expression:

- #price cung cấp đơn giá.
- #quantity cung cấp số lượng.
- #taxRate cung cấp tỷ lệ thuế.
- Các toán tử số học kết hợp những giá trị này thành kết quả.

Cách làm này giữ logic trong expression và dữ liệu ở context. Khi dữ liệu thay đổi, ứng dụng có thể cập nhật biến mà không cần tạo chuỗi expression mới.

## 5. Cập nhật giá trị biến

Gọi \`setVariable\` lần nữa với cùng tên sẽ cập nhật giá trị biến trong context:

~~~java
context.setVariable("minimum", 500);

Expression expression =
    parser.parseExpression("#minimum * 2");

Integer first =
    expression.getValue(context, Integer.class);

// Cập nhật giá trị biến.
context.setVariable("minimum", 900);

Integer second =
    expression.getValue(context, Integer.class);
~~~

Kết quả:

~~~text
first = 1000
second = 1800
~~~

Expression có thể được tái sử dụng. Khi gọi getValue lần tiếp theo, SpEL tra cứu giá trị biến hiện tại trong context.

Điều này hữu ích khi cùng một quy tắc cần được đánh giá với nhiều dữ liệu đầu vào. Ứng dụng có thể giữ Expression đã parse và thay đổi các biến theo từng lần xử lý.

## 6. Đăng ký nhiều biến cùng lúc

Ngoài \`setVariable\`, \`StandardEvaluationContext\` cung cấp \`setVariables(Map<String, Object>)\` để đăng ký một nhóm biến:

~~~java
Map<String, Object> variables = new HashMap<>();
variables.put("minimum", new BigDecimal("500000"));
variables.put("customerName", "Linh");
variables.put("quantity", 3);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariables(variables);
~~~

Sau đó expression có thể tham chiếu từng biến:

~~~spel
#minimum
#customerName
#quantity
~~~

Cách đăng ký theo Map thuận tiện khi dữ liệu đã được gom thành một cấu trúc trước khi đánh giá.

Tên key trong Map là tên biến và không bao gồm dấu \`#\`. Ví dụ key \`"quantity"\` được tham chiếu bằng \`#quantity\`.

## 7. Biến có thể chứa object

Biến không chỉ chứa kiểu nguyên thủy hoặc String. Nó có thể chứa một object Java đầy đủ.

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

Đăng ký object:

~~~java
Product product =
    new Product("Keyboard", new BigDecimal("750000"));

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("product", product);
~~~

Expression có thể đọc property trên biến object:

~~~spel
#product.name
#product.price
#product.price * 2
~~~

Ví dụ:

~~~java
Expression expression =
    parser.parseExpression("#product.name");

String name =
    expression.getValue(context, String.class);
~~~

Kết quả là Keyboard.

Cú pháp \`#product.name\` có hai thao tác: tra cứu biến product trong context, sau đó đọc property name trên object được trả về.

## 8. Phân biệt biến với root object

Root object là đối tượng gốc của một lần đánh giá. Biến là giá trị được đăng ký riêng trong EvaluationContext.

Giả sử có Product làm root object và một biến minimum:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(product);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);
~~~

Expression:

~~~spel
price >= #minimum
~~~

Trong đó:

- \`price\` được đọc trên object hiện tại, ban đầu là root object product.
- \`#minimum\` được lấy từ tập biến của context.

Có thể tham chiếu tường minh root object bằng \`#root\`:

~~~spel
#root.price >= #minimum
~~~

Hai cách trên cùng diễn đạt việc so sánh giá của root object với biến minimum.

## 9. Phân biệt biến với #root và #this

SpEL có hai biến đặc biệt:

- \`#root\` tham chiếu root object của lần đánh giá.
- \`#this\` tham chiếu object đang là mục tiêu đánh giá hiện tại.

Chúng không phải các biến nghiệp vụ thông thường được đăng ký bằng setVariable.

Ví dụ:

~~~spel
#root.customer.name
~~~

Biểu thức đọc customer.name từ root object.

Trong selection hoặc projection trên collection:

~~~spel
#orders.?[#this.total >= #minimum]
~~~

\`#this\` là order đang được xét; \`#minimum\` là biến do ứng dụng đăng ký. Root object ban đầu vẫn được tham chiếu bởi \`#root\`.

Phân biệt các tên này giúp tránh nhầm lẫn giữa dữ liệu do ứng dụng truyền vào và các tham chiếu đặc biệt của SpEL.

## 10. Biến không tồn tại và biến có giá trị null

Một biến có thể chưa được đăng ký hoặc được đăng ký với giá trị null. Trong cả hai trường hợp, khi expression đọc biến, giá trị nhận được là null.

Ví dụ:

~~~java
context.setVariable("nickname", null);
~~~

Biểu thức:

~~~spel
#nickname
~~~

trả về null.

Nếu một biến chưa được đăng ký, việc tra cứu cũng không cung cấp giá trị và expression nhận null. Vì vậy, không nên chỉ dựa vào kết quả #variable để phân biệt biến chưa tồn tại với biến đã đăng ký nhưng có giá trị null.

Nếu ứng dụng cần biết một biến đã được cung cấp hay chưa, hãy quản lý sự hiện diện của key trong Map dữ liệu hoặc kiểm tra ở mã Java trước khi đánh giá.

Có thể dùng Elvis để cung cấp giá trị mặc định:

~~~spel
#nickname ?: 'Anonymous'
~~~

Nếu nickname là null, kết quả là Anonymous. Nếu có giá trị, expression trả về giá trị nickname.

## 11. Tên biến phân biệt chữ hoa và chữ thường

Tên biến cần được tham chiếu nhất quán. Ví dụ:

~~~java
context.setVariable("customerName", "Linh");
~~~

Expression đúng:

~~~spel
#customerName
~~~

Expression dùng tên khác:

~~~spel
#customername
~~~

không tham chiếu cùng tên biến. Nên dùng một quy ước đặt tên nhất quán, thường là lower camel case theo phong cách Java.

Khi kiểm tra lỗi, hãy so sánh chính xác tên truyền vào setVariable với tên sau dấu # trong expression.

## 12. Biến và bean reference là hai cơ chế khác nhau

SpEL dùng hai ký hiệu khác nhau:

| Cú pháp | Cơ chế | Cách cung cấp |
|---|---|---|
| #customer | Variable reference | Đăng ký trong EvaluationContext |
| @customerService | Bean reference | BeanResolver tìm bean trong Spring container |

Ví dụ:

~~~java
context.setVariable("customer", customer);
~~~

Expression dùng:

~~~spel
#customer.name
~~~

Trong khi đó:

~~~spel
@customerService.findById(#customerId)
~~~

tham chiếu bean do Spring quản lý và truyền biến customerId làm đối số.

Đăng ký một biến tên customerService không tự động biến #customerService thành @customerService. Hai namespace này độc lập.

## 13. Đăng ký function thông qua variable

SpEL cũng có thể gọi function được đăng ký trong context. Trong StandardEvaluationContext, function được đăng ký bằng một đối tượng Method gắn với tên biến.

Ví dụ, tạo một phương thức static:

~~~java
public class TextFunctions {
    public static String upper(String value) {
        return value.toUpperCase();
    }
}
~~~

Đăng ký Method:

~~~java
Method upperMethod =
    TextFunctions.class.getDeclaredMethod(
        "upper",
        String.class
    );

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("upper", upperMethod);
~~~

Gọi function trong expression:

~~~spel
#upper('spring')
~~~

Kết quả:

~~~text
SPRING
~~~

Tên function được đăng ký không có dấu # trong setVariable; cú pháp gọi function trong SpEL dùng #name(...).

Nên đăng ký method public, có chữ ký rõ ràng và phù hợp với kiểu đối số mà expression truyền vào. Function reference là một khả năng khác với việc lưu một giá trị thông thường trong biến, dù cả hai được tra cứu trong không gian biến của context.

## 14. Biến có thể được dùng trong template expression

Biến cũng hoạt động trong các đoạn SpEL bên trong template:

~~~java
ExpressionParser parser = new SpelExpressionParser();
ParserContext parserContext = new TemplateParserContext();

Expression template = parser.parseExpression(
    "Xin chào #{#customerName}, tổng tiền là #{#total}.",
    parserContext
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", "Linh");
context.setVariable("total", new BigDecimal("750000"));

String message =
    template.getValue(context, String.class);
~~~

Kết quả:

~~~text
Xin chào Linh, tổng tiền là 750000.
~~~

ParserContext quyết định cách phân tích template. EvaluationContext cung cấp biến được sử dụng khi đánh giá các đoạn SpEL.

## 15. Quản lý context và dữ liệu giữa các lần đánh giá

EvaluationContext lưu các biến mà ứng dụng đăng ký. Nếu nhiều lần xử lý dùng cùng một context, việc cập nhật biến có thể ảnh hưởng đến lần đánh giá tiếp theo.

Ví dụ:

~~~java
context.setVariable("customerName", "Linh");
String first =
    expression.getValue(context, String.class);

context.setVariable("customerName", "Minh");
String second =
    expression.getValue(context, String.class);
~~~

Cùng Expression nhưng kết quả có thể khác nhau vì giá trị biến đã thay đổi.

Trong ứng dụng xử lý nhiều request đồng thời, cần quản lý context theo phạm vi dữ liệu phù hợp. Không nên vô tình dùng chung context có biến thay đổi giữa các request độc lập, vì một lần cập nhật có thể làm ảnh hưởng lần đánh giá khác.

Một cách rõ ràng là tạo context cho từng lần xử lý hoặc từng đơn vị công việc, đăng ký các biến cần thiết rồi đánh giá expression.

## 16. Ví dụ hoàn chỉnh: truyền dữ liệu nghiệp vụ qua biến

Giả sử ứng dụng cần tính tổng tiền của một đơn hàng và kiểm tra đơn hàng có vượt ngưỡng hay không.

~~~java
BigDecimal price = new BigDecimal("250000");
int quantity = 3;
BigDecimal minimum = new BigDecimal("700000");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("price", price);
context.setVariable("quantity", quantity);
context.setVariable("minimum", minimum);

ExpressionParser parser = new SpelExpressionParser();

Expression totalExpression =
    parser.parseExpression("#price * #quantity");

Expression eligibleExpression =
    parser.parseExpression("#price * #quantity >= #minimum");

BigDecimal total =
    totalExpression.getValue(context, BigDecimal.class);

Boolean eligible =
    eligibleExpression.getValue(context, Boolean.class);

System.out.println(total);
System.out.println(eligible);
~~~

Kết quả:

~~~text
750000
true
~~~

Cách tổ chức này tách ba phần:

1. Java chuẩn bị dữ liệu và đăng ký biến.
2. SpEL mô tả quy tắc tính toán bằng #variable.
3. getValue đánh giá quy tắc trên dữ liệu hiện tại và trả về kết quả.

Nếu quantity hoặc minimum thay đổi, ứng dụng chỉ cần cập nhật biến trong context rồi đánh giá lại expression.

## 17. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Truyền tên biến vào setVariable phải có dấu #.**  
Tên đăng ký là \`"minimum"\`; expression mới dùng \`#minimum\`.

**Nhầm lẫn 2: Biến và property trên root object giống nhau.**  
\`#minimum\` tra cứu biến trong context; \`minimum\` thường tra cứu property trên object hiện tại.

**Nhầm lẫn 3: Biến là bean Spring.**  
Biến được đăng ký trong EvaluationContext; bean reference dùng @ và cần BeanResolver.

**Nhầm lẫn 4: Parse expression sẽ cố định giá trị biến.**  
Giá trị được tra cứu khi evaluation. Cập nhật biến có thể làm cùng Expression trả về kết quả khác.

**Nhầm lẫn 5: Biến null và biến chưa đăng ký luôn phân biệt được trong expression.**  
Cả hai đều có thể được đọc thành null. Nếu cần phân biệt, hãy quản lý sự hiện diện của key ở phía Java.

**Nhầm lẫn 6: Có thể dùng chung context có trạng thái cho mọi request mà không cần quản lý.**  
Biến được cập nhật trong context có thể ảnh hưởng lần đánh giá khác. Cần chọn vòng đời context phù hợp.

## 18. Ghi nhớ

- \`StandardEvaluationContext.setVariable(name, value)\` đăng ký hoặc cập nhật một biến.
- Tên trong setVariable không có tiền tố #; expression tham chiếu biến bằng \`#variableName\`.
- \`setVariables(Map<String, Object>)\` cho phép đăng ký nhiều biến cùng lúc.
- Biến có thể chứa giá trị đơn giản, object, collection hoặc array.
- Có thể đọc property trên object biến bằng cú pháp như \`#product.price\`.
- Biến khác với root property, #root, #this và bean reference @.
- Biến được tra cứu khi evaluation, nên cùng Expression có thể cho kết quả khác sau khi cập nhật context.
- Giá trị null và biến chưa đăng ký có thể cùng được đọc thành null.
- Function có thể được đăng ký bằng Method trong không gian biến và gọi bằng cú pháp #function(...).
- Quản lý vòng đời EvaluationContext để tránh chia sẻ trạng thái biến ngoài ý muốn.

Khi sử dụng biến trong SpEL, hãy thống nhất tên giữa setVariable và #variable, đăng ký đúng kiểu dữ liệu, truyền đúng EvaluationContext khi gọi getValue và quản lý context theo phạm vi của dữ liệu cần đánh giá.
