# Chuỗi xử lý từ văn bản biểu thức đến giá trị cuối cùng trong Spring Expression Language

Spring Expression Language (SpEL) nhận một biểu thức được viết dưới dạng văn bản, phân tích văn bản đó thành cấu trúc có thể thực thi, rồi đánh giá cấu trúc ấy trên dữ liệu của ứng dụng. Kết quả cuối cùng không được tính ngay khi parser đọc chuỗi. Nó chỉ xuất hiện khi ứng dụng yêu cầu đánh giá biểu thức trong một ngữ cảnh cụ thể.

Có thể theo dõi toàn bộ quá trình qua sáu chặng:

1. Nhận văn bản biểu thức và cấu hình parser.
2. Tách token và phân tích cú pháp.
3. Tạo cây biểu thức (AST) và đối tượng Expression.
4. Chuẩn bị EvaluationContext cùng root object.
5. Đánh giá các nút trong AST, tra cứu dữ liệu và thực hiện phép toán.
6. Trả về giá trị, hoặc chuyển đổi sang kiểu mà ứng dụng yêu cầu.

## 1. Toàn cảnh pipeline

~~~text
Văn bản biểu thức
       |
       v
ExpressionParser / SpelExpressionParser
       |
       v
Tokenizer: nhận diện token
       |
       v
Parser: kiểm tra cú pháp và dựng cấu trúc
       |
       v
AST (cây cú pháp trừu tượng)
       |
       v
Expression (SpelExpression)
       |
       | getValue(context, ...)
       v
EvaluationState + EvaluationContext + root object
       |
       v
Các AST node được đánh giá
       |
       +--> đọc thuộc tính / biến
       +--> gọi phương thức / truy cập kiểu
       +--> thực hiện toán tử / chuyển đổi kiểu
       |
       v
Giá trị Object
       |
       v
Trả về trực tiếp hoặc chuyển đổi sang kiểu đích
       |
       v
Kết quả cuối cùng
~~~

Hai nửa của pipeline có nhiệm vụ khác nhau:

- **Parsing:** biến văn bản thành một đối tượng biểu diễn logic của biểu thức. Parsing kiểm tra cú pháp và chuẩn bị cấu trúc, nhưng chưa tính giá trị dựa trên dữ liệu nghiệp vụ cụ thể.
- **Evaluation:** thực thi cấu trúc đã phân tích trên root object và EvaluationContext. Đây là lúc SpEL đọc dữ liệu, gọi phương thức, áp dụng toán tử và tạo ra kết quả.

## 2. Chặng 1 — Nhận văn bản và chọn parser

Ứng dụng thường bắt đầu bằng giao diện ExpressionParser và sử dụng SpelExpressionParser làm bộ phân tích cụ thể:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");
~~~

Chuỗi truyền vào parseExpression là ngôn ngữ SpEL. Nó có thể chứa literal, tên thuộc tính, biến, lời gọi phương thức, toán tử, truy cập collection và nhiều cấu trúc khác.

Parser có thể nhận cấu hình thông qua SpelParserConfiguration. Cấu hình này điều chỉnh một số hành vi trong lúc phân tích hoặc đánh giá, chẳng hạn tự khởi tạo thuộc tính null và tự mở rộng collection trong những tình huống được hỗ trợ. Nếu không cần hành vi đặc biệt, có thể dùng cấu hình mặc định.

Ở bước này, ứng dụng chỉ cần đưa văn bản biểu thức cho parser. Dữ liệu như một đơn hàng cụ thể hoặc giá trị biến minimum sẽ được cung cấp khi đánh giá.

## 3. Chặng 2 — Tokenizer và parser xử lý văn bản

### 3.1. Tokenizer nhận diện các thành phần

Tokenizer đọc chuỗi ký tự và nhận diện những đơn vị cú pháp như:

- Identifier: tên thuộc tính hoặc tên phương thức, ví dụ total, status.
- Variable marker: dấu # mở đầu tên biến, ví dụ #minimum.
- Literal: số, chuỗi, boolean, null.
- Operator: các ký hiệu như >=, &&, +, ==.
- Delimiter: dấu ngoặc, dấu chấm, dấu phẩy và các ký hiệu phân tách khác.

Với biểu thức:

~~~spel
total >= #minimum && status == 'PAID'
~~~

có thể nhận diện các nhóm token tương ứng với tên total, toán tử so sánh, biến minimum, toán tử logic, tên status, toán tử bằng và chuỗi PAID.

Token chỉ là những đơn vị cú pháp. Chúng chưa phải là giá trị của các thuộc tính trong một đối tượng Java.

### 3.2. Parser kiểm tra cấu trúc và thứ tự ưu tiên

Parser sử dụng token để xác định cách các thành phần kết hợp với nhau. Ví dụ, nó cần biết phép so sánh nào thuộc về toán tử &&, dấu ngoặc nào nhóm một biểu thức con và một lời gọi phương thức có những đối số nào.

Với biểu thức ví dụ, cấu trúc logic tương đương:

~~~text
AND
|-- GREATER_THAN_OR_EQUAL
|   |-- PROPERTY: total
|   |-- VARIABLE: minimum
|
|-- EQUAL
    |-- PROPERTY: status
    |-- LITERAL: 'PAID'
~~~

Sơ đồ này thể hiện quan hệ giữa các phần của biểu thức. Nó không phải là kết quả đánh giá và cũng không chứa giá trị thực tế của total hay minimum.

Nếu chuỗi sai cú pháp, lỗi có thể xuất hiện ngay tại parseExpression. Ví dụ, thiếu toán hạng hoặc đóng ngoặc không đúng sẽ khiến parser không thể tạo cấu trúc hợp lệ. Nhóm lỗi này thuộc giai đoạn parsing.

## 4. Chặng 3 — AST trở thành đối tượng Expression

### 4.1. AST biểu diễn biểu thức dưới dạng cây

AST (Abstract Syntax Tree) là cấu trúc nút cha và nút con mô tả ý nghĩa cú pháp của biểu thức. Mỗi nút đại diện cho một thành phần hoặc thao tác:

| Loại nút | Ví dụ | Trách nhiệm khi đánh giá |
|---|---|---|
| Literal | 'PAID', 100, true | Cung cấp giá trị cố định |
| Property | total, customer.name | Đọc thuộc tính từ đối tượng hiện tại |
| Variable | #minimum | Lấy biến từ EvaluationContext |
| Operator | >=, &&, + | Đánh giá toán hạng và áp dụng phép toán |
| Method call | customer.isActive() | Tìm và gọi phương thức phù hợp |
| Selection / Projection | items.?[...], items.![...] | Lọc hoặc biến đổi phần tử collection |

Parser xây dựng các nút theo cấu trúc và thứ tự ưu tiên của biểu thức. Khi đánh giá, các nút phối hợp với nhau để tạo giá trị của biểu thức cha.

### 4.2. Expression là giao diện ứng dụng dùng để đánh giá

Sau khi parsing thành công, parser trả về một đối tượng Expression. Với SpelExpressionParser, đối tượng triển khai cụ thể là SpelExpression và giữ cấu trúc biểu thức đã phân tích.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");
~~~

Ứng dụng thường thao tác qua giao diện Expression thay vì phải gọi trực tiếp các AST node. Những overload getValue(...) là điểm vào chính để yêu cầu SpEL đánh giá biểu thức.

Một điểm cần nhớ: đối tượng Expression mô tả logic đã phân tích. Nó không tự quyết định total thuộc đơn hàng nào, biến minimum có giá trị bao nhiêu hoặc kết quả lần đánh giá này là true hay false.

## 5. Chặng 4 — Chuẩn bị EvaluationContext và root object

Khi ứng dụng gọi getValue(...), SpEL cần biết môi trường đánh giá. Môi trường này được cung cấp thông qua EvaluationContext và root object.

Ví dụ:

~~~java
Order order = new Order(
    new BigDecimal("750000"),
    "PAID"
);

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);
~~~

Trong ví dụ:

- order là root object.
- total và status được tra cứu trên đối tượng hiện tại, ban đầu chính là order.
- minimum là biến được đăng ký trong context và được tham chiếu bằng #minimum.

EvaluationContext còn có thể cung cấp những cơ chế cần thiết để giải quyết các thao tác trong AST:

| Thành phần của context | Công việc trong pipeline |
|---|---|
| PropertyAccessor | Đọc hoặc ghi thuộc tính trên đối tượng |
| MethodResolver | Tìm phương thức phù hợp khi biểu thức gọi phương thức |
| ConstructorResolver | Tìm constructor khi biểu thức tạo đối tượng |
| TypeLocator | Tìm kiểu Java trong biểu thức như T(java.time.LocalDate) |
| TypeConverter | Chuyển đổi giá trị khi thao tác yêu cầu chuyển đổi |
| BeanResolver | Giải quyết tham chiếu bean nếu ứng dụng đã cấu hình |
| OperatorOverloader | Cho phép tùy chỉnh một số phép toán |

StandardEvaluationContext hỗ trợ nhiều cơ chế và khả năng cấu hình. SimpleEvaluationContext giới hạn một số tính năng để phù hợp với các trường hợp cần kiểm soát phạm vi truy cập, chẳng hạn data binding. Loại context được chọn ảnh hưởng đến những biểu thức có thể đánh giá thành công.

### Root object, #root và #this

Root object là điểm bắt đầu để tra cứu thuộc tính không có tiền tố biến. SpEL cung cấp hai biến đặc biệt:

- #root tham chiếu root object của lần đánh giá.
- #this tham chiếu đối tượng đang là mục tiêu đánh giá hiện tại. Trong selection hoặc projection, đối tượng hiện tại có thể lần lượt là từng phần tử collection.

Ví dụ:

~~~spel
orders.?[total >= #minimum]
~~~

Trong điều kiện lọc, total được đọc trên từng phần tử đang xét. #this cũng trỏ đến phần tử đó, trong khi #root vẫn giữ đối tượng gốc của toàn bộ lần đánh giá.

## 6. Chặng 5 — AST được đánh giá

Đây là lúc văn bản biểu thức bắt đầu tạo ra kết quả dựa trên dữ liệu thực tế.

Khi gọi getValue(...), SpEL thiết lập trạng thái đánh giá (EvaluationState) từ EvaluationContext và root object phù hợp. Trạng thái này giúp các nút trong AST truy cập context, root object và đối tượng hiện tại trong quá trình thực thi.

Có thể hình dung quá trình như sau:

~~~text
Expression.getValue(...)
       |
       v
Tạo trạng thái đánh giá
       |
       v
Đánh giá nút gốc của AST
       |
       +--> đánh giá nút con bên trái
       |
       +--> đánh giá nút con bên phải
       |
       +--> tra cứu dữ liệu qua context
       |
       +--> thực hiện phép toán
       |
       v
Nút gốc nhận giá trị cuối cùng
~~~

### 6.1. Nút Property đọc dữ liệu

Với biểu thức total, nút thuộc tính yêu cầu đọc total trên đối tượng hiện tại. SpEL sử dụng PropertyAccessor phù hợp. Trong cấu hình mặc định, việc truy cập thuộc tính Java thường được thực hiện thông qua cơ chế reflection và các accessor được cung cấp sẵn.

Nếu root object là Order và có getter getTotal(), SpEL có thể lấy giá trị tương ứng thông qua cơ chế truy cập thuộc tính.

Nếu không tìm được thuộc tính hoặc không thể đọc thuộc tính trên đối tượng hiện tại, evaluation có thể phát sinh lỗi.

### 6.2. Nút Variable lấy giá trị từ context

Với #minimum, nút biến tra cứu tên minimum trong EvaluationContext. Giá trị được trả về là BigDecimal mà ứng dụng đã đăng ký.

Sự khác biệt giữa total và #minimum rất quan trọng:

- total là tên thuộc tính được giải quyết trên đối tượng hiện tại.
- #minimum là tên biến được giải quyết từ context.

### 6.3. Nút Method Call tìm và gọi phương thức

Với biểu thức như customer.isActive(), SpEL cần tìm phương thức phù hợp trên đối tượng customer. MethodResolver trong context tham gia vào quá trình tìm phương thức; sau khi xác định được phương thức có thể gọi, SpEL thực hiện lời gọi và nhận giá trị trả về.

Việc tìm phương thức còn phụ thuộc vào số lượng đối số, kiểu đối số, các cơ chế chuyển đổi và khả năng truy cập của context.

### 6.4. Nút Operator đánh giá toán hạng

Với biểu thức total >= #minimum, nút so sánh cần giá trị của hai toán hạng:

1. Đánh giá total để lấy tổng tiền.
2. Đánh giá #minimum để lấy ngưỡng.
3. So sánh hai giá trị theo quy tắc toán tử của SpEL.
4. Trả về một giá trị Boolean.

Với toán tử logic &&, SpEL kết hợp kết quả của các biểu thức con theo quy tắc logic. Một số toán tử logic có cơ chế đánh giá ngắn mạch: nếu toán hạng đầu đã quyết định kết quả, toán hạng còn lại có thể không cần đánh giá.

### 6.5. Chuyển đổi kiểu trong lúc đánh giá

Một số thao tác cần giá trị được chuyển sang kiểu phù hợp. EvaluationContext cung cấp TypeConverter để hỗ trợ các chuyển đổi mà môi trường cho phép.

Chuyển đổi có thể liên quan đến việc gán giá trị, truyền đối số cho phương thức hoặc thực hiện thao tác yêu cầu kiểu tương thích. Không nên giả định mọi kiểu dữ liệu đều có thể chuyển đổi cho mọi phép toán. Nếu không có chuyển đổi phù hợp, evaluation có thể thất bại.

## 7. Chặng 6 — Nhận và chuyển đổi kết quả cuối cùng

Khi nút gốc của AST được đánh giá xong, SpEL thu được giá trị của toàn biểu thức. Giá trị này có thể là Boolean, Number, String, một object Java, collection hoặc null, tùy theo biểu thức.

Nếu gọi getValue(context) mà không yêu cầu kiểu cụ thể, ứng dụng nhận kết quả dưới dạng Object:

~~~java
Object value = expression.getValue(context);
~~~

Nếu biết kiểu mong đợi, ứng dụng có thể yêu cầu SpEL trả về kiểu đó:

~~~java
Boolean eligible =
    expression.getValue(context, Boolean.class);
~~~

Với overload có kiểu đích, SpEL sử dụng cơ chế chuyển đổi của context khi cần và khi có thể. Nếu giá trị không tương thích và không thể chuyển đổi, lời gọi có thể phát sinh lỗi.

Cần phân biệt hai việc:

- **Giá trị do AST tạo ra:** đầu ra của quá trình đánh giá biểu thức.
- **Kiểu mà ứng dụng yêu cầu:** kiểu nhận kết quả từ overload getValue có tham số Class.

Kiểu đích không thay đổi logic của biểu thức. Nó quy định dạng kết quả mà ứng dụng muốn nhận.

## 8. Ví dụ xuyên suốt: từ chuỗi đến Boolean

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

Mục tiêu là kiểm tra đơn hàng có tổng tiền đạt ngưỡng tối thiểu và có trạng thái PAID hay không.

~~~java
// 1. Chuẩn bị dữ liệu nghiệp vụ.
Order order = new Order(
    new BigDecimal("750000"),
    "PAID"
);

// 2. Phân tích văn bản thành Expression.
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "total >= #minimum && status == 'PAID'"
);

// 3. Chuẩn bị EvaluationContext.
StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable(
    "minimum",
    new BigDecimal("500000")
);

// 4. Đánh giá AST và nhận kết quả Boolean.
Boolean eligible =
    expression.getValue(context, Boolean.class);
~~~

Luồng xử lý của ví dụ:

| Chặng | Hoạt động | Dữ liệu hoặc kết quả |
|---|---|---|
| Nhận văn bản | Parser nhận chuỗi điều kiện | total >= #minimum && status == 'PAID' |
| Tokenize và parse | Nhận diện tên, biến, literal và toán tử | Cấu trúc cú pháp hợp lệ |
| Tạo AST | Tạo các nút thuộc tính, biến, so sánh và logic | Cây biểu thức |
| Tạo context | Đặt order làm root object và đăng ký minimum | total = 750000, minimum = 500000, status = PAID |
| Evaluate | Đọc thuộc tính, biến và thực hiện hai phép so sánh | true && true |
| Trả kết quả | Nút gốc trả về Boolean | eligible = true |

Nếu minimum đổi thành 900000, biểu thức và AST vẫn giữ nguyên. Lần đánh giá mới sẽ đọc giá trị biến mới, phép so sánh đầu tiên trả về false và kết quả cuối cùng là false.

Ví dụ này cho thấy văn bản biểu thức chỉ mô tả logic. Dữ liệu trong context quyết định kết quả của mỗi lần đánh giá.

## 9. Parsing và evaluation có những loại lỗi khác nhau

Phân biệt hai giai đoạn giúp khoanh vùng lỗi nhanh hơn.

### Lỗi parsing

Lỗi xuất hiện khi parser không thể hiểu văn bản theo cú pháp SpEL, ví dụ:

- Thiếu toán hạng trong một phép toán.
- Dấu ngoặc không cân bằng.
- Cấu trúc lời gọi phương thức hoặc truy cập collection không hợp lệ.
- Sử dụng toán tử sai vị trí.

Lỗi thường xuất hiện ngay tại parseExpression(...). Khi parsing thất bại, ứng dụng chưa có một Expression hợp lệ để đánh giá.

### Lỗi evaluation

Lỗi xuất hiện khi cú pháp hợp lệ nhưng dữ liệu hoặc môi trường không đáp ứng yêu cầu, ví dụ:

- Biến được tham chiếu nhưng chưa đăng ký trong context.
- Thuộc tính không tồn tại hoặc không đọc được.
- Đối tượng hiện tại là null ở vị trí cần truy cập thuộc tính.
- Không tìm thấy phương thức phù hợp.
- Context không hỗ trợ tính năng mà biểu thức yêu cầu.
- Chuyển đổi kiểu cần thiết không thực hiện được.

Những lỗi này xuất hiện khi gọi getValue(...), sau khi parsing đã thành công.

Một cách điều tra thực tế là xác định chính xác lỗi xảy ra ở parseExpression hay getValue, sau đó kiểm tra lần lượt cú pháp, root object, biến, accessor/resolver và kiểu dữ liệu.

## 10. Tái sử dụng biểu thức và vòng đời context

Ứng dụng có thể phân tích một chuỗi thành Expression một lần rồi đánh giá lại với nhiều context:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("total >= #minimum");

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

Trong cách sử dụng này:

- Expression giữ logic đã phân tích.
- Mỗi context cung cấp root object và các biến của lần đánh giá tương ứng.
- Mỗi lời gọi getValue tạo ra kết quả theo dữ liệu được cung cấp tại thời điểm đó.

Context có thể chứa trạng thái có thể thay đổi. Trong ứng dụng xử lý nhiều yêu cầu đồng thời, nên quản lý context theo phạm vi công việc phù hợp và tránh vô tình dùng chung root object hoặc biến giữa các yêu cầu.

## 11. Cách lần theo pipeline khi đọc mã SpEL

Khi gặp một đoạn mã sử dụng SpEL, có thể lần theo các điểm sau:

1. **Tìm chuỗi đầu vào:** biểu thức được tạo từ hằng số, cấu hình hay dữ liệu người dùng?
2. **Tìm parser:** đoạn mã gọi parseExpression ở đâu và có cấu hình parser đặc biệt không?
3. **Tìm Expression:** đối tượng biểu thức được lưu và tái sử dụng như thế nào?
4. **Tìm điểm gọi getValue:** lúc nào biểu thức thực sự được đánh giá?
5. **Tìm context và root object:** dữ liệu nào là đối tượng gốc, những biến nào được đăng ký?
6. **Tìm cơ chế truy cập:** có accessor, resolver, converter hoặc bean resolver tùy chỉnh không?
7. **Tìm kiểu kết quả:** ứng dụng nhận Object hay yêu cầu một kiểu cụ thể?
8. **Tìm xử lý lỗi:** parsing exception và evaluation exception được xử lý ở đâu?

Cách lần theo này giúp nối được mã cấu hình với kết quả thực tế, thay vì chỉ nhìn vào chuỗi biểu thức.

## 12. Ghi nhớ

- Parser nhận văn bản, tokenize và phân tích cú pháp để tạo AST.
- AST mô tả cấu trúc và thứ tự thực hiện các thành phần của biểu thức.
- Expression là đối tượng ứng dụng dùng để yêu cầu đánh giá cấu trúc đã phân tích.
- EvaluationContext và root object cung cấp dữ liệu, biến cùng cơ chế truy cập cần thiết.
- EvaluationState hỗ trợ các AST node trong lúc đánh giá, bao gồm việc theo dõi root object và đối tượng hiện tại.
- Các nút thuộc tính, biến, lời gọi phương thức và toán tử phối hợp để tạo giá trị của biểu thức.
- getValue trả kết quả; overload có kiểu đích có thể chuyển đổi kết quả theo khả năng của context.
- Lỗi parsing xảy ra khi văn bản không tạo được biểu thức hợp lệ; lỗi evaluation xảy ra khi thực thi biểu thức với dữ liệu hoặc môi trường không phù hợp.

Khi cần giải thích một biểu thức SpEL, hãy đi từ đầu vào đến đầu ra: **văn bản được phân tích thành cấu trúc nào, context cung cấp dữ liệu gì, các nút được đánh giá ra sao và giá trị cuối cùng được trả về theo kiểu nào.**
