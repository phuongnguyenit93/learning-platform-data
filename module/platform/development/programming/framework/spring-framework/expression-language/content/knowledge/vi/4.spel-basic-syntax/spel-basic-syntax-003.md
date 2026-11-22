# Khoảng trắng và cách đọc token trong SpEL

Spring Expression Language (SpEL) nhận đầu vào dưới dạng một chuỗi biểu thức. Trước khi biểu thức được thực thi, parser phải nhận diện chuỗi đó thành các **token** rồi kiểm tra xem các token có tạo thành một cấu trúc hợp lệ hay không. Vì thế, khi đọc hoặc sửa một biểu thức SpEL, cần phân biệt ba việc: ký tự trong chuỗi nguồn, token mà lexer nhận ra và ý nghĩa mà parser tạo ra từ các token đó.

Khoảng trắng thường chỉ đóng vai trò phân tách token. Nó giúp biểu thức dễ đọc nhưng không phải lúc nào cũng là một phần của giá trị. Ngoại lệ dễ thấy nhất là khoảng trắng nằm bên trong string literal: phần đó thuộc dữ liệu của chuỗi và được giữ nguyên.

## 1. Từ chuỗi biểu thức đến kết quả đánh giá

Quá trình xử lý SpEL có thể hình dung theo ba bước:

1. **Tokenize (nhận diện token):** lexer đọc chuỗi nguồn và nhận ra identifier, literal, dấu phân cách, toán tử và các ký hiệu đặc biệt.
2. **Parse (phân tích cú pháp):** parser kiểm tra thứ tự token theo grammar của SpEL và tạo cấu trúc biểu thức, thường được biểu diễn bằng expression tree hoặc abstract syntax tree.
3. **Evaluate (đánh giá):** expression được chạy trong một EvaluationContext cụ thể. Ở bước này, SpEL mới phân giải biến, property, method, bean reference và các giá trị thực tế.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("#order.total >= 1000");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("order", order);

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Khi gọi **parseExpression(...)**, parser kiểm tra cú pháp và xây dựng biểu thức. Khi gọi **getValue(...)**, SpEL mới tìm biến **order**, đọc property **total** và so sánh với số **1000**.

Sự phân biệt này giúp chẩn đoán lỗi:

- **ParseException:** chuỗi không tạo thành biểu thức hợp lệ, thường do thiếu toán hạng, dấu ngoặc hoặc toán tử sai vị trí.
- **EvaluationException:** cú pháp đã được chấp nhận nhưng việc đánh giá gặp vấn đề, chẳng hạn biến không tồn tại, property không đọc được hoặc method không gọi được trong context hiện tại.

Một biểu thức parse thành công chưa có nghĩa là nó chắc chắn chạy được với mọi EvaluationContext.

## 2. Token là gì?

Token là đơn vị cú pháp mà lexer nhận ra. Một token có thể gồm nhiều ký tự. Chẳng hạn **>=** là một toán tử, **customer** là một identifier, còn **'READY FOR PICKUP'** là một string literal duy nhất dù bên trong có dấu cách.

Các nhóm token thường gặp trong SpEL:

| Nhóm | Ví dụ | Vai trò |
| --- | --- | --- |
| Identifier | **order**, **customer**, **total** | Tên property, method hoặc thành phần định danh |
| Variable reference | **#order**, **#root**, **#this** | Truy cập biến trong EvaluationContext hoặc đối tượng hiện tại |
| Bean reference | **@policyService** | Tham chiếu bean trong application context |
| Type reference | **T(java.lang.Math)** | Tham chiếu một kiểu Java |
| String literal | **'READY'**, **'Hello SpEL'** | Giá trị chuỗi |
| Numeric literal | **42**, **3.14**, **0x2A** | Giá trị số |
| Boolean / null | **true**, **false**, **null** | Giá trị logic và giá trị rỗng |
| Punctuation | **.**, **,**, **(**, **)**, **[**, **]** | Phân nhóm, truy cập property, truyền đối số hoặc lấy phần tử |
| Operator | **+**, **>=**, **and**, **matches** | Thực hiện phép toán hoặc so sánh |

Không phải token nào cũng có ý nghĩa độc lập. Dấu chấm trong **order.total** nối một lần truy cập property; dấu ngoặc trong **max(3, 7)** gom danh sách đối số của lời gọi method; dấu **#** mở đầu một variable reference.

## 3. Khoảng trắng được xử lý như thế nào?

### 3.1. Khoảng trắng giữa các token thường không làm đổi ý nghĩa

SpEL bỏ qua khoảng trắng dùng để phân tách các token hoàn chỉnh. Vì vậy, hai biểu thức sau có cùng ý nghĩa:

~~~text
#order.total >= 1000
#order.total>=1000
~~~

Tương tự, có thể xuống dòng để làm biểu thức dài dễ đọc hơn, miễn là ngắt giữa các token:

~~~text
#order.status == 'READY'
    and #order.total >= 1000
~~~

Trong biểu thức trên, xuống dòng và dấu cách quanh **and** không làm thay đổi điều kiện. Lexer vẫn nhận được cùng chuỗi token theo cùng thứ tự.

Cách viết nên dùng là đặt khoảng trắng quanh toán tử nhị phân, sau dấu phẩy và giữa các nhánh logic. Đây là quy ước trình bày giúp người đọc nhìn rõ từng phần, không phải yêu cầu bắt buộc của parser trong mọi vị trí.

### 3.2. Không chèn khoảng trắng vào giữa một token

Khoảng trắng không thể thay thế cho một phần của token. Ví dụ:

| Viết | Cách lexer/parser hiểu |
| --- | --- |
| **total >= 1000** | Một identifier, một toán tử so sánh và một số |
| **total > = 1000** | Dấu **>** và dấu **=** tách rời; không còn toán tử **>=** |
| **#order.total** | Variable reference **order**, sau đó truy cập property **total** |
| **#ord er.total** | Identifier bị tách thành hai phần; không còn là biến **order** |
| **1000** | Một numeric literal |
| **1 000** | Hai phần số tách rời; không phải số một nghìn |

Một số cặp ký hiệu cũng phải được giữ liền nhau vì chúng tạo thành toán tử riêng:

- **?.** là safe-navigation operator.
- **?:** là Elvis operator.
- **>=** và **<=** là toán tử so sánh.
- **!=** là toán tử khác nhau.

Ví dụ **#customer?.address** dùng safe navigation để truy cập **address** khi **customer** không null. Nếu tách ký hiệu thành **? .**, chuỗi token đã khác và không còn là cách viết toán tử safe navigation.

### 3.3. Khoảng trắng bên trong string literal là dữ liệu

String literal được bao bởi dấu nháy. Dấu cách nằm bên trong chuỗi được giữ nguyên:

~~~text
'READY FOR PICKUP'
'Hello    Spring'
~~~

Hai chuỗi trên chứa khoảng trắng trong chính giá trị của chúng. Chúng không tương đương với **'READY FOR PICKUP'** và **'Hello Spring'** nếu ứng dụng so sánh chuỗi chính xác.

SpEL cho phép dùng dấu nháy đơn hoặc nháy kép cho string literal. Khi cần biểu diễn dấu nháy đơn bên trong một chuỗi được bao bằng nháy đơn, có thể viết lặp dấu nháy:

~~~text
'O''Reilly'
~~~

Giá trị chuỗi nhận được là **O'Reilly**. Không đặt khoảng trắng tùy ý giữa dấu mở và dấu đóng của literal vì các ký tự bên trong là nội dung, không phải khoảng trắng phân tách cú pháp.

### 3.4. Toán tử dạng chữ cần được nhận diện như một token riêng

SpEL có các toán tử được viết bằng từ, ví dụ:

- So sánh: **lt**, **le**, **gt**, **ge**, **eq**, **ne**.
- Logic: **and**, **or**, **not**.
- Số học: **div**, **mod**.

Các từ này là toán tử khi lexer nhận diện được chúng như một token riêng. Không ghép chúng vào identifier khác. Ví dụ:

~~~text
#order.total gt 1000
#order.total >= 1000
~~~

Hai biểu thức trên đều diễn đạt phép so sánh lớn hơn. Nhưng **totalgt** là một identifier, không phải identifier **total** theo sau bởi toán tử **gt**.

Các toán tử dạng chữ hữu ích trong cấu hình XML, nơi ký tự **<** và **>** có ý nghĩa đặc biệt với cú pháp XML. Ví dụ:

~~~xml
<int:filter
    input-channel="orders"
    expression="payload.total gt 1000" />
~~~

Nếu viết toán tử dạng ký hiệu trong XML, cần escape các ký tự theo quy tắc XML, chẳng hạn **&lt;** và **&gt;**.

## 4. Đọc một biểu thức theo thứ tự token

Xét biểu thức:

~~~text
#order.status == 'READY FOR PICKUP' and #order.total >= 1000
~~~

Có thể tách thành các token theo thứ tự:

| Thứ tự | Token | Ý nghĩa |
| --- | --- | --- |
| 1 | **#** | Bắt đầu variable reference |
| 2 | **order** | Tên biến |
| 3 | **.** | Toán tử truy cập property |
| 4 | **status** | Property của đối tượng order |
| 5 | **==** | Toán tử bằng |
| 6 | **'READY FOR PICKUP'** | String literal; khoảng trắng bên trong được giữ lại |
| 7 | **and** | Toán tử logic AND |
| 8 | **#order** | Tham chiếu cùng biến order |
| 9 | **.** | Truy cập property |
| 10 | **total** | Property total |
| 11 | **>=** | Toán tử lớn hơn hoặc bằng |
| 12 | **1000** | Numeric literal |

Parser nhóm các token thành cấu trúc tương đương:

~~~text
(#order.status == 'READY FOR PICKUP')
and
(#order.total >= 1000)
~~~

Khi đánh giá, SpEL lấy biến **order** từ context, đọc **status** và **total**, sau đó thực hiện hai phép so sánh và kết hợp kết quả bằng **and**.

Điều đáng chú ý là lexer không hiểu ý nghĩa nghiệp vụ của **READY FOR PICKUP** hay **total**. Nó chỉ nhận diện literal và identifier. Việc **status** có tồn tại hay **total** có kiểu dữ liệu so sánh được hay không thuộc về giai đoạn đánh giá và mô hình đối tượng.

## 5. Nhận diện dấu phân cách và toán tử trong biểu thức phức hợp

### 5.1. Property, method và indexer

Các ký hiệu **.**, **()** và **[]** giúp parser nhận biết thao tác đang được thực hiện:

~~~text
#order.customer.name
#name.toUpperCase()
#orders[0]
#headers['tenantId']
~~~

- **.** truy cập property hoặc method kế tiếp.
- **()** gom các đối số của lời gọi method.
- **[]** truy cập phần tử collection, array hoặc map theo index/key.

Dấu phẩy phân tách các đối số hoặc phần tử:

~~~text
T(java.lang.Math).max(3, 7)
{1, 2, 3}
~~~

Trong ví dụ đầu, **3** và **7** là hai đối số khác nhau. Trong ví dụ sau, dấu phẩy phân tách các phần tử của inline list.

### 5.2. Dấu ngoặc và thứ tự nhóm biểu thức

Dấu ngoặc tròn làm rõ phần biểu thức cần được nhóm:

~~~text
(#order.total + #order.shippingFee) >= 1000
~~~

Không nên dựa vào trí nhớ về precedence khi một biểu thức có nhiều phép toán. Dùng dấu ngoặc giúp người đọc xác định ngay phần nào được tính trước và giảm nguy cơ hiểu nhầm khi sửa điều kiện.

### 5.3. Ternary và Elvis operator

Ternary operator có dạng **condition ? valueIfTrue : valueIfFalse**:

~~~text
#order.total >= 1000 ? 'FREE_SHIPPING' : 'STANDARD_SHIPPING'
~~~

Elvis operator **?:** cung cấp giá trị thay thế khi vế trái null hoặc được xem là không có giá trị theo quy tắc của SpEL:

~~~text
#customer.nickname ?: #customer.name
~~~

Dấu **?** và dấu **:** trong ternary là các token phân tách cấu trúc. Trong Elvis operator, cặp **?:** phải được viết liền nhau để lexer nhận diện đúng toán tử.

### 5.4. Selection và projection

Với collection, SpEL dùng các ký hiệu mở đầu bằng dấu chấm để chọn hoặc biến đổi phần tử:

~~~text
#orders.?[total >= 1000]
#orders.![customer.name]
#orders.^[total >= 1000]
#orders.$[total >= 1000]
~~~

- **.?[ ... ]** chọn các phần tử thỏa điều kiện.
- **.![ ... ]** projection: tạo collection mới từ biểu thức áp dụng lên từng phần tử.
- **.^[ ... ]** lấy phần tử đầu tiên thỏa điều kiện.
- **.$[ ... ]** lấy phần tử cuối cùng thỏa điều kiện.

Các ký hiệu này là cấu trúc cú pháp riêng. Khi đọc, hãy nhận diện cả cụm **.?[**, **.![**, **.^[** hoặc **.$[** trước khi phân tích phần điều kiện bên trong.

## 6. Phân biệt các ký hiệu mở đầu quan trọng

Một số ký hiệu xuất hiện ở đầu biểu thức hoặc trước tên định danh, nhưng mỗi ký hiệu có chức năng khác nhau:

| Cách viết | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **#name** | Biến trong evaluation context | **#order**, **#root** |
| **@name** | Bean trong application context | **@permissionService** |
| **T(Type)** | Tham chiếu kiểu Java | **T(java.time.LocalDate)** |
| **${{...}** | Property placeholder của Spring, không phải cú pháp SpEL | **${{app.region}** |
| **#{...}** | Delimiter nhúng SpEL trong những vị trí hỗ trợ template/expression | **#{T(java.lang.Math).PI}** |

Cần nhớ rằng không phải annotation nào cũng yêu cầu viết expression trong **#{...}**. Một số thuộc tính nhận trực tiếp nội dung SpEL, ví dụ:

~~~java
@Cacheable(key = "#isbn")
@PreAuthorize("hasAuthority('invoice:read')")
~~~

Trong khi đó, **@Value** thường dùng placeholder hoặc expression với delimiter phù hợp:

~~~java
@Value("${{app.region:ap-southeast-1}")
private String region;

@Value("#{T(java.lang.Math).PI}")
private double pi;
~~~

**${{...}** lấy giá trị cấu hình; **#{...}** yêu cầu đánh giá biểu thức SpEL ở những điểm tích hợp hỗ trợ. Hai cơ chế có thể cùng xuất hiện trong một số cấu hình, nhưng không phải là hai cách viết thay thế nhau.

## 7. Quy tắc trình bày biểu thức dễ đọc

Khi viết SpEL trong annotation, XML hoặc cấu hình Java, nên áp dụng một số quy ước:

1. Đặt khoảng trắng quanh toán tử nhị phân như **+**, **==**, **>=**, **and**, **or**.
2. Xuống dòng tại ranh giới token hoặc giữa các nhánh logic dài; không tách đôi identifier, literal hay toán tử ghép.
3. Dùng dấu ngoặc để thể hiện rõ thứ tự nhóm khi có nhiều phép toán.
4. Giữ liền các toán tử nhiều ký tự như **?.**, **?:**, **>=**, **!=**.
5. Giữ nguyên khoảng trắng có chủ đích bên trong string literal.
6. Dùng toán tử dạng chữ như **lt**, **gt**, **le**, **ge** khi biểu thức nằm trong XML và cần tránh ký tự đặc biệt.
7. Phân biệt rõ biến **#order**, bean **@orderService** và property của root object **order**.
8. Khi biểu thức dài hoặc chứa nhiều quy tắc nghiệp vụ, chuyển phần logic vào method của bean rồi gọi method đó từ SpEL.

Một biểu thức có thể viết trên một dòng hoặc nhiều dòng. Điều quan trọng là ranh giới token không bị phá vỡ và cấu trúc vẫn dễ đọc.

## 8. Cách chẩn đoán lỗi token và khoảng trắng

Khi parser báo lỗi, hãy kiểm tra theo thứ tự:

1. **Kiểm tra toán tử ghép:** có vô tình viết **> =** thay vì **>=**, hoặc **? :** thay vì **?:** không?
2. **Kiểm tra identifier:** tên biến/property/method có bị chèn khoảng trắng hoặc gõ sai chữ hoa/chữ thường không?
3. **Kiểm tra literal:** dấu nháy mở/đóng đã cân bằng chưa; dấu nháy nằm trong chuỗi đã được escape đúng chưa?
4. **Kiểm tra ngoặc và dấu phân cách:** **()**, **[]**, dấu phẩy và dấu hai chấm có đủ cặp và đúng vị trí không?
5. **Kiểm tra toán tử dạng chữ:** **and**, **or**, **not**, **gt**, **lt** có được tách khỏi identifier lân cận không?
6. **Tách lỗi parse khỏi lỗi evaluate:** nếu parse thành công, kiểm tra EvaluationContext, biến, property, method và kiểu dữ liệu thực tế.

Có thể rút biểu thức thành một ví dụ nhỏ để kiểm tra parser:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("#order.total >= 1000");

System.out.println(expression.getExpressionString());
~~~

Đoạn mã này cho phép kiểm tra riêng chuỗi expression có được parser chấp nhận hay không. Muốn kiểm tra kết quả thực thi, cần cung cấp EvaluationContext có biến **order** và đối tượng có property **total** phù hợp.

Không nên sửa lỗi bằng cách thêm/xóa khoảng trắng một cách ngẫu nhiên. Hãy xác định token nào đang bị tách hoặc ghép sai, rồi chỉnh đúng ranh giới cú pháp.

## 9. Ghi nhớ nhanh

- Lexer nhận diện token; parser ghép token thành cấu trúc biểu thức; evaluator chạy cấu trúc đó trong EvaluationContext.
- Khoảng trắng giữa các token hoàn chỉnh thường không ảnh hưởng kết quả.
- Khoảng trắng bên trong string literal là dữ liệu và được giữ nguyên.
- Không chèn khoảng trắng vào giữa identifier, numeric literal hoặc toán tử nhiều ký tự.
- **#** mở đầu biến, **@** tham chiếu bean, **T(...)** tham chiếu kiểu Java.
- **.**, **()**, **[]** lần lượt phục vụ truy cập property, gọi method và truy cập phần tử.
- **?.**, **?:**, **>=**, **!=** cần được giữ nguyên như các toán tử ghép.
- Parse thành công chỉ xác nhận cú pháp; biến và property vẫn phải tồn tại khi đánh giá.
- Dùng khoảng trắng có quy ước để biểu thức ngắn gọn, nhất quán và dễ rà soát.

## 10. Tài liệu tham khảo chính thức

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Expression Language Basics](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [Spring Framework — Operators in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)
- [Spring Framework — Parser Configuration](https://docs.spring.io/spring-framework/reference/core/expressions/parser.html)
- [Spring Framework — Expression Templating](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/templating.html)
