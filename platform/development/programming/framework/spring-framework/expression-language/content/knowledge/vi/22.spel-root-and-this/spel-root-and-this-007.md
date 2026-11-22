# Root object null và chiến lược xử lý

Trong Spring Expression Language (SpEL), **root object** là đối tượng gốc mà biểu thức sử dụng khi đọc property hoặc gọi method mà không chỉ rõ một biến hay đối tượng khác. Root object có thể được cung cấp khi tạo **EvaluationContext**, hoặc truyền trực tiếp vào mỗi lần gọi **Expression.getValue(...)**.

Root object không bắt buộc phải khác null. Tuy nhiên, nếu biểu thức truy cập property hoặc gọi method trực tiếp trên một root object null, quá trình đánh giá sẽ thất bại. Vì vậy, ứng dụng cần xác định rõ null có phải trạng thái hợp lệ hay là dữ liệu đầu vào không hợp lệ, rồi chọn cách xử lý phù hợp.

## Root object được cung cấp như thế nào?

Có hai cách phổ biến để đặt root object cho lần đánh giá.

Cách thứ nhất là đặt root object trong StandardEvaluationContext:

~~~java
Customer customer = new Customer("An");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(customer);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String name = expression.getValue(context, String.class);
~~~

Trong ví dụ, **customer** là root object của context. Biểu thức **name** đọc property name từ đối tượng đó.

Cách thứ hai là truyền root object tại thời điểm đánh giá:

~~~java
Expression expression = parser.parseExpression("name");

String name =
        expression.getValue(context, customer, String.class);
~~~

Cách này hữu ích khi cùng một Expression được đánh giá trên nhiều đối tượng khác nhau. Context có thể giữ các biến và cấu hình chung, còn root object được thay đổi theo từng lần gọi.

## Điều gì xảy ra khi root object là null?

Nếu root object null, SpEL vẫn có thể đánh giá những biểu thức không cần truy cập root object, chẳng hạn literal hoặc biến đã được khai báo trong context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(null);
context.setVariable("greeting", "Hello");

ExpressionParser parser = new SpelExpressionParser();

String literal =
        parser.parseExpression("'Spring'")
                .getValue(context, String.class);

String greeting =
        parser.parseExpression("#greeting")
                .getValue(context, String.class);
~~~

Hai biểu thức trên không cần đọc property từ root object nên vẫn có thể trả về giá trị. Biểu thức **#root** cũng có thể được dùng để kiểm tra tham chiếu root hiện tại.

Ngược lại, biểu thức truy cập property trực tiếp như **name** hoặc gọi method như **getName()** cần một đối tượng đích. Nếu root object null, SpEL không có object để thực hiện thao tác và sẽ phát sinh lỗi evaluation.

~~~java
Expression expression =
        parser.parseExpression("name");

String name =
        expression.getValue(context, String.class);
~~~

Nếu context không có root object, biểu thức trên không thể đọc property name. Đây là lỗi ở giai đoạn evaluation, không phải lỗi cú pháp: chuỗi **name** vẫn là một biểu thức hợp lệ, nhưng không có đối tượng phù hợp để đánh giá.

## Phân biệt root object null với property null

Hai trường hợp này khác nhau:

- **Root object null:** không có đối tượng gốc để biểu thức đọc property.
- **Root object tồn tại nhưng một property null:** có đối tượng gốc, nhưng một phần dữ liệu bên trong object graph không có giá trị.
- **Collection rỗng:** collection tồn tại nhưng không chứa phần tử.
- **Collection null:** không có collection để duyệt.

Ví dụ, Customer tồn tại nhưng address null:

~~~java
Customer customer = new Customer("An");
customer.setAddress(null);

context.setRootObject(customer);
~~~

Biểu thức **name** vẫn có thể đọc tên khách hàng. Biểu thức **address.city** sẽ gặp vấn đề vì address null. Nếu toàn bộ customer null, ngay cả việc đọc **name** cũng không thực hiện được.

Không nên xem null và collection rỗng là cùng một trạng thái. Collection rỗng thường có nghĩa là dữ liệu tồn tại nhưng hiện không có phần tử; collection null có thể biểu thị dữ liệu chưa được cung cấp hoặc chưa khởi tạo. Chính sách nghiệp vụ nên quyết định cách diễn giải hai trường hợp này.

## Dùng #root để kiểm tra root object

SpEL cung cấp biến đặc biệt **#root** để tham chiếu đến root object ban đầu của lần đánh giá:

~~~java
Expression expression =
        parser.parseExpression("#root == null");

Boolean isRootNull =
        expression.getValue(context, rootObject, Boolean.class);
~~~

Nếu rootObject là null, kết quả là true. Việc dùng #root giúp biểu thức kiểm tra rõ đối tượng gốc, đặc biệt khi biểu thức còn có biến khác hoặc khi đang ở trong một ngữ cảnh collection operation.

Cần phân biệt **#root** với **#this**:

- **#root** giữ tham chiếu đến root object ban đầu trong toàn bộ lần đánh giá.
- **#this** là đối tượng hiện tại tại vị trí biểu thức đang được đánh giá; trong selection hoặc projection, nó có thể là phần tử hiện tại của collection.

Trong một biểu thức top-level đơn giản, #this thường trùng với root object. Nhưng khi đi vào collection operation hoặc một ngữ cảnh đánh giá lồng nhau, không nên xem hai biến này là tương đương.

## Null-safe navigation với toán tử ?.

SpEL hỗ trợ **null-safe navigation operator** là **?.**. Toán tử này cho phép truy cập property hoặc gọi method trên một đối tượng có thể null mà không phát sinh lỗi chỉ vì đối tượng đích null.

Ví dụ, thay vì truy cập trực tiếp **name**, có thể viết:

~~~java
Expression expression =
        parser.parseExpression("#root?.name");

String name =
        expression.getValue(context, rootObject, String.class);
~~~

Nếu rootObject null, phần truy cập name trả về null. Nếu rootObject tồn tại, SpEL đọc property name như bình thường.

Có thể dùng null-safe navigation cho chuỗi property lồng nhau:

~~~java
Expression expression =
        parser.parseExpression(
                "#root?.customer?.address?.city");

String city =
        expression.getValue(context, rootObject, String.class);
~~~

Mỗi đoạn **?.** bảo vệ bước truy cập kế tiếp nếu đối tượng ở bên trái đang null. Cách viết này phù hợp khi từng mắt xích trong object graph đều có thể vắng mặt.

### Đặt null-safe ở đúng từng bước

Null-safe navigation chỉ bảo vệ thao tác ngay sau toán tử. Nếu một bước trả về null rồi biểu thức tiếp tục truy cập property bằng dấu chấm thông thường, lỗi vẫn có thể xảy ra.

Ví dụ:

~~~text
#root?.customer.address.city
~~~

Nếu root tồn tại nhưng customer null, bước truy cập address tiếp theo không được bảo vệ. Cách an toàn hơn khi cả customer và address đều có thể null là:

~~~text
#root?.customer?.address?.city
~~~

Hãy đặt null-safe navigation ở mọi vị trí mà giá trị trung gian có thể null. Không nên cho rằng chỉ cần đặt **?.** ở đầu chuỗi là toàn bộ biểu thức phía sau tự động an toàn.

## Dùng Elvis operator để cung cấp giá trị mặc định

Nếu null có thể được thay bằng một giá trị mặc định hợp lệ, có thể dùng **Elvis operator ?:**:

~~~java
Expression expression =
        parser.parseExpression("#root?.name ?: 'Guest'");

String displayName =
        expression.getValue(context, rootObject, String.class);
~~~

Nếu root object null hoặc property name không có giá trị, biểu thức có thể trả về **Guest**. Khi có tên, biểu thức trả về tên đó.

Elvis operator giúp viết gọn trường hợp thường gặp so với toán tử điều kiện ba ngôi. Trong SpEL, vế trái null hoặc chuỗi rỗng cũng có thể dẫn đến việc dùng giá trị ở vế phải. Nếu ứng dụng cần phân biệt chuỗi rỗng với null, hãy dùng điều kiện tường minh thay vì dựa vào Elvis.

Giá trị mặc định chỉ nên dùng khi nó đúng với nghiệp vụ. Ví dụ, dùng Guest cho tên hiển thị có thể hợp lý; dùng một giá trị mặc định cho customerId hoặc quyền truy cập có thể che giấu dữ liệu thiếu và tạo hành vi sai.

## Dùng toán tử điều kiện để quyết định rõ ràng

Với trường hợp cần kiểm tra root object trước khi truy cập, có thể dùng toán tử ba ngôi:

~~~java
Expression expression =
        parser.parseExpression(
                "#root == null ? 'No customer' : #root.name");

String label =
        expression.getValue(context, rootObject, String.class);
~~~

Khi root null, biểu thức chọn nhánh đầu và không truy cập name. Khi root tồn tại, biểu thức mới đọc property name.

Cách viết này thể hiện rõ hai nhánh xử lý và phù hợp khi trạng thái null cần một kết quả riêng. Nếu property name cũng có thể null, cần bổ sung điều kiện hoặc dùng null-safe navigation và giá trị mặc định phù hợp.

## Xử lý property lồng nhau có thể null

Một object graph thường có nhiều tầng property. Chẳng hạn Order có customer, Customer có address và Address có city. Chỉ cần một tầng ở giữa null, truy cập sâu bằng dấu chấm thông thường có thể thất bại.

~~~java
Expression expression =
        parser.parseExpression(
                "#root?.customer?.address?.city ?: 'Unknown'");
~~~

Biểu thức này trả về city nếu toàn bộ chuỗi property tồn tại và có giá trị; nếu một mắt xích null hoặc kết quả cuối không có giá trị, Elvis cung cấp nhãn Unknown.

Nếu từng trạng thái null có ý nghĩa khác nhau, không nên gom tất cả thành một giá trị mặc định. Hãy kiểm tra và phân loại trong Java hoặc dùng các nhánh điều kiện rõ ràng để phân biệt:

- Không có Order.
- Order chưa gắn Customer.
- Customer chưa có Address.
- Address có tồn tại nhưng city chưa được nhập.

Cách phân biệt này hữu ích khi ứng dụng cần hiển thị thông báo cụ thể, ghi log hoặc yêu cầu người dùng bổ sung dữ liệu.

## Truyền biến khi không có root object

Một biểu thức không nhất thiết cần root object nếu dữ liệu được cung cấp qua variable:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setRootObject(null);
context.setVariable("displayName", "An");

Expression expression =
        parser.parseExpression("#displayName ?: 'Guest'");

String result =
        expression.getValue(context, String.class);
~~~

Biểu thức sử dụng #displayName nên không cần đọc property từ root. Đây là một cách tổ chức phù hợp khi dữ liệu đầu vào là các tham số độc lập, không thuộc về một object gốc duy nhất.

Tuy nhiên, nếu biến chứa object và biểu thức truy cập property của biến đó, object trong biến vẫn có thể null. Khi ấy, cần dùng null-safe navigation hoặc kiểm tra điều kiện tương tự như với root object.

## Xử lý root null trong Java trước khi đánh giá

Không phải mọi trường hợp null đều nên được xử lý trong SpEL. Nếu root object là dữ liệu bắt buộc của nghiệp vụ, cách rõ ràng nhất thường là xác thực trong Java trước khi gọi getValue:

~~~java
Objects.requireNonNull(
        customer,
        "Customer is required");

String name =
        expression.getValue(context, customer, String.class);
~~~

Cách này làm lỗi đầu vào xuất hiện sớm và giữ biểu thức tập trung vào logic cần thực hiện. Nó cũng giúp phân biệt lỗi dữ liệu ở ranh giới ứng dụng với lỗi đánh giá biểu thức.

Có thể dùng kiểm tra điều kiện thay vì ném exception nếu ứng dụng cần trả về kết quả nghiệp vụ:

~~~java
if (customer == null) {
    return "No customer";
}

return expression.getValue(context, customer, String.class);
~~~

Chọn cách xử lý theo ý nghĩa của null: từ chối đầu vào, trả kết quả mặc định, bỏ qua thao tác hay biểu diễn trạng thái chưa xác định.

## Root collection null và collection rỗng

Nếu root object chính là một collection, cần phân biệt collection null với collection rỗng:

~~~java
List<String> names = Collections.emptyList();

Expression expression =
        parser.parseExpression("#root.?[#this.startsWith('A')]");

List<?> result =
        expression.getValue(context, names, List.class);
~~~

Với collection rỗng, selection có thể trả về collection kết quả rỗng vì không có phần tử nào để kiểm tra. Nếu root collection null, SpEL không có collection để thực hiện selection và biểu thức thông thường có thể phát sinh lỗi evaluation.

Nếu null được phép hiểu như collection rỗng, hãy chuẩn hóa trước khi đánh giá:

~~~java
List<String> safeNames =
        names == null ? Collections.emptyList() : names;

List<?> result =
        expression.getValue(context, safeNames, List.class);
~~~

Cách này làm chính sách chuyển null thành collection rỗng rõ ràng trong Java. Nếu null có ý nghĩa khác với rỗng, không nên tự động thay thế.

## Root object trong các tích hợp Spring

Khi dùng SpEL thông qua annotation hoặc module của Spring, framework thường chuẩn bị EvaluationContext và root object theo ngữ cảnh tích hợp. Root object trong một biểu thức cache, security hoặc bean configuration không nhất thiết giống root object của một lần đánh giá độc lập do ứng dụng tự tạo.

Vì vậy, không nên giả định **#root** luôn là bean đang được cấu hình hoặc một đối tượng nghiệp vụ cụ thể. Hãy xem tài liệu của integration tương ứng để biết root object, biến và property nào được cung cấp.

Nếu tự đánh giá biểu thức, ứng dụng có thể kiểm soát rõ root object bằng StandardEvaluationContext hoặc truyền nó vào getValue. Nếu dùng annotation, hãy viết biểu thức dựa trên dữ liệu mà integration thực sự expose.

## Lỗi khi truy cập root object null

Cần phân biệt lỗi cú pháp và lỗi khi đánh giá:

- **ParseException:** chuỗi SpEL sai cú pháp, chẳng hạn thiếu dấu ngoặc hoặc toán tử không hợp lệ.
- **EvaluationException:** biểu thức hợp lệ nhưng không thể thực hiện trên root object hoặc context hiện tại, ví dụ đọc property trên root null hoặc gọi method trên một giá trị null.

Ví dụ xử lý:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("name");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    String name =
            expression.getValue(context, rootObject, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot evaluate expression for the supplied root object", ex);
}
~~~

Nếu root null là trạng thái hợp lệ, nên xử lý nó bằng null-safe navigation, Elvis, điều kiện ba ngôi hoặc chuẩn hóa dữ liệu trước khi đánh giá. Nếu root bắt buộc, hãy xác thực sớm và trả lỗi đầu vào rõ ràng.

Không nên bắt mọi EvaluationException rồi trả về null một cách tổng quát. Cách đó có thể che giấu property sai tên, lỗi method, kiểu dữ liệu không tương thích hoặc những vấn đề khác không liên quan đến root null.

## Quy tắc thực hành

- Xác định root object được cung cấp ở đâu: trong EvaluationContext hay tại mỗi lần gọi getValue.
- Phân biệt root null với property null, collection null và collection rỗng.
- Dùng **#root** khi cần tham chiếu rõ ràng đến đối tượng gốc.
- Dùng **?.** ở từng bước có thể null trong chuỗi truy cập.
- Dùng **?:** hoặc toán tử ba ngôi khi có giá trị thay thế đúng với nghiệp vụ.
- Nếu root là dữ liệu bắt buộc, kiểm tra trong Java trước khi evaluate.
- Không chia sẻ một context mutable chứa root hoặc biến theo request giữa nhiều luồng nếu có thể gây lẫn dữ liệu.
- Xử lý lỗi evaluation tại ranh giới phù hợp và giữ lại thông tin đủ để chẩn đoán.

## Kết luận

Root object null không ngăn SpEL đánh giá mọi loại biểu thức. Literal và variable vẫn có thể hoạt động, nhưng thao tác đọc property hoặc gọi method trực tiếp trên root null sẽ thất bại. **#root** cho phép kiểm tra đối tượng gốc; **?.** bảo vệ truy cập null-safe; **?:** và toán tử ba ngôi cung cấp giá trị thay thế hoặc nhánh xử lý rõ ràng.

Hãy quyết định null có hợp lệ theo nghiệp vụ hay không. Nếu dữ liệu bắt buộc, xác thực trong Java trước khi đánh giá. Nếu null là trạng thái bình thường, dùng null-safe navigation và giá trị mặc định có chủ đích. Với object graph lồng nhau, bảo vệ từng bước có thể null và phân biệt rõ root null với property null sẽ giúp biểu thức dễ dự đoán, dễ chẩn đoán và dễ bảo trì hơn.
