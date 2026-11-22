# Đọc expression string và expression tree khi chẩn đoán lỗi

Khi một biểu thức Spring Expression Language (SpEL) hoạt động sai, chỉ nhìn vào exception cuối cùng thường chưa đủ để tìm nguyên nhân. Cần xác định chính xác source expression đã được parse, cấu trúc mà parser tạo ra, object và biến được dùng khi evaluate, cùng vị trí xảy ra lỗi.

SpEL cung cấp hai góc nhìn hữu ích:

- **Expression string**: chuỗi biểu thức đầu vào mà ứng dụng gửi cho parser.
- **Expression tree (AST)**: cây cú pháp trừu tượng mà parser tạo ra để biểu diễn các toán tử, property access, method call, literal và các thành phần con.

Đọc hai góc nhìn này giúp phân biệt lỗi cú pháp với lỗi dữ liệu runtime, xác định một biểu thức phức tạp được phân tích thành những phần nào và thu hẹp vị trí cần kiểm tra. AST phục vụ chẩn đoán; không nên dựa vào tên class nội bộ của từng node để xây dựng logic nghiệp vụ vì cấu trúc triển khai có thể thay đổi giữa các phiên bản Spring.

## 1. Hai thứ cần quan sát khi debug

### 1.1. Expression string

Expression string là source mà ứng dụng truyền vào ExpressionParser:

~~~java
String source =
        "orders.?[total >= #minimum].![id]";
~~~

Chuỗi này thể hiện cú pháp mà người viết hoặc hệ thống sinh ra. Khi debug, hãy giữ lại đúng source được dùng ở lần đánh giá thất bại, bao gồm:

- Khoảng trắng và dấu ngoặc.
- Tên property và method.
- Literal và kiểu literal.
- Tên biến bắt đầu bằng dấu #.
- Bean reference bắt đầu bằng dấu @ nếu được phép.
- Index, selection, projection và toán tử lồng nhau.

Không nên chỉ log một chuỗi đã được format lại hoặc dựng lại từ dữ liệu sau khi lỗi xảy ra. Nếu source được tạo động, hãy lưu đúng phiên bản đã truyền cho parser để có thể tái hiện lỗi.

### 1.2. Expression tree (AST)

Parser phân tích source thành một cấu trúc node. Mỗi node đại diện cho một thành phần cú pháp hoặc một phép tính.

Ví dụ:

~~~java
orders.?[total >= #minimum].![id]
~~~

Ở mức khái niệm, biểu thức có:

- Truy cập property orders.
- Thao tác selection trên collection.
- Phép so sánh total với biến #minimum.
- Thao tác projection để lấy id.

AST thể hiện quan hệ cha/con giữa các thành phần đó. Khi duyệt cây, có thể nhìn thấy node gốc, các node con, vị trí source và biểu diễn AST của từng node.

AST hữu ích khi source dài hoặc được sinh tự động, vì nó cho thấy parser đã hiểu biểu thức theo cấu trúc nào. Tuy nhiên, AST không chứa toàn bộ trạng thái runtime như giá trị thực tế của từng property, bean nào đã được phân giải hay dữ liệu mà method trả về.

### 1.3. Source và AST có mục đích khác nhau

| Góc nhìn | Trả lời câu hỏi | Dùng khi |
|---|---|---|
| Expression string | Parser đã nhận chính xác chuỗi nào? | Kiểm tra source, ký tự đặc biệt, dữ liệu ghép động |
| AST | Parser hiểu chuỗi thành những thành phần nào? | Phân tích toán tử, thứ tự cấu trúc và node con |
| EvaluationContext | Expression được đánh giá trên object và biến nào? | Tìm lỗi dữ liệu, accessor, resolver và converter |
| Exception | Thao tác nào thất bại và ở vị trí nào? | Thu hẹp nguyên nhân runtime hoặc parse |

Không dùng AST thay cho source gốc. Một AST có thể cung cấp biểu diễn chuẩn hóa, nhưng không nhất thiết giữ nguyên khoảng trắng hoặc cách viết ban đầu.

## 2. Lấy expression string từ Expression

### 2.1. Giữ source trước khi parse

Khi ứng dụng nhận hoặc tạo expression, nên giữ source trong biến riêng:

~~~java
String source = "total >= #minimum";

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(source);
~~~

Cách này giúp log đúng chuỗi đã parse và thuận tiện khi cần tái hiện lỗi.

Nếu source được lấy từ database hoặc cấu hình, nên lưu thêm định danh và phiên bản cấu hình. Hai expression có cùng tên rule nhưng source khác nhau có thể tạo ra kết quả khác.

### 2.2. Dùng getExpressionString()

Interface Expression cung cấp phương thức getExpressionString():

~~~java
String expressionString = expression.getExpressionString();
~~~

Có thể log source cùng định danh rule:

~~~java
logger.debug(
        "Evaluating ruleId={}, expression={}",
        ruleId,
        expression.getExpressionString()
);
~~~

Với expression được tạo bởi parser thông thường, phương thức này trả về chuỗi expression gắn với đối tượng Expression. Hãy giữ source đầu vào riêng nếu cần bảo đảm có bản ghi chính xác về payload ban đầu hoặc nếu ứng dụng dùng parser context/template.

### 2.3. Expression template

SpEL cũng hỗ trợ template expression, trong đó phần văn bản thông thường xen kẽ với phần expression được đánh dấu:

~~~java
String template =
        "Hello #{customer.name}, order total is #{order.total}";
~~~

Parse template:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        template,
        new TemplateParserContext()
);
~~~

Khi debug template, hãy ghi nhận cả template source và parser context. Một lỗi có thể nằm trong đoạn expression được nhúng, trong khi phần văn bản thông thường vẫn hợp lệ.

Không giả định AST của template có cùng cấu trúc với AST của một expression thuần. Template parser có thể tạo cấu trúc kết hợp các đoạn literal và expression.

## 3. Lấy AST từ SpelExpression

### 3.1. ExpressionParser trả về interface Expression

Thông thường ứng dụng parse bằng interface:

~~~java
Expression expression =
        parser.parseExpression("total >= #minimum");
~~~

Interface Expression cung cấp các thao tác evaluate, lấy kiểu kết quả và lấy expression string. Để truy cập cây node cụ thể của SpEL, có thể kiểm tra implementation là SpelExpression.

~~~java
if (expression instanceof SpelExpression spelExpression) {
    SpelNode ast = spelExpression.getAST();
}
~~~

SpelExpression thuộc package:

~~~java
org.springframework.expression.spel.standard.SpelExpression
~~~

SpelNode thuộc package:

~~~java
org.springframework.expression.spel.SpelNode
~~~

### 3.2. Dùng getAST()

Ví dụ lấy node gốc:

~~~java
SpelExpression spelExpression =
        (SpelExpression) parser.parseExpression(
                "total >= #minimum"
        );

SpelNode ast = spelExpression.getAST();
~~~

Node gốc đại diện cho cấu trúc expression đã parse. Từ node này có thể đọc biểu diễn AST, số lượng node con và duyệt các node con theo API SpelNode.

Việc ép kiểu chỉ phù hợp khi biết parser đang dùng trả về SpelExpression. Nếu ứng dụng nhận Expression từ một implementation khác hoặc wrapper, hãy kiểm tra kiểu trước khi truy cập API riêng của SpelExpression.

### 3.3. Dùng toStringAST()

SpelNode cung cấp phương thức toStringAST():

~~~java
String astText = ast.toStringAST();
~~~

Ví dụ:

~~~java
SpelExpression spelExpression =
        (SpelExpression) parser.parseExpression(
                "total >= #minimum"
        );

String astText =
        spelExpression.getAST().toStringAST();
~~~

toStringAST() trả về biểu diễn cú pháp của node hoặc cây con. Nó hữu ích để xem parser đã biểu diễn expression ra sao.

Đây không phải bản sao byte-for-byte của source. Khoảng trắng, dấu ngoặc không cần thiết hoặc một số chi tiết cách viết có thể không được giữ nguyên. Khi cần tái hiện chính xác input, hãy dùng getExpressionString() hoặc source đã lưu.

## 4. Duyệt expression tree

### 4.1. Các phương thức của SpelNode

SpelNode cung cấp các phương thức chính để duyệt và quan sát cây:

- **getChildCount()**: số node con trực tiếp.
- **getChild(index)**: lấy node con theo vị trí.
- **getStartPosition()**: vị trí bắt đầu của node trong source.
- **getEndPosition()**: vị trí kết thúc theo thông tin node cung cấp.
- **toStringAST()**: biểu diễn AST của node.

Có thể dùng các phương thức này để xây dựng cây debug dạng text mà không cần phụ thuộc vào tên class của từng implementation node.

### 4.2. Hàm in cây đệ quy

Ví dụ một hàm duyệt AST:

~~~java
static void printTree(SpelNode node, int depth) {
    String indent = "  ".repeat(depth);

    System.out.printf(
            "%s%s [%d, %d] %s%n",
            indent,
            node.getClass().getSimpleName(),
            node.getStartPosition(),
            node.getEndPosition(),
            node.toStringAST()
    );

    for (int i = 0; i < node.getChildCount(); i++) {
        printTree(node.getChild(i), depth + 1);
    }
}
~~~

Sử dụng:

~~~java
SpelExpression expression =
        (SpelExpression) parser.parseExpression(
                "orders.?[total >= #minimum].![id]"
        );

printTree(expression.getAST(), 0);
~~~

Đoạn mã minh họa việc in tên class node, vị trí source và biểu diễn AST của từng node. Tên class node cụ thể và cách parser tổ chức node con là chi tiết triển khai; không nên viết test phụ thuộc vào toàn bộ cây chính xác giữa các phiên bản Spring nếu đó không phải mục tiêu của test.

Nếu ứng dụng chạy trên Java trước phiên bản hỗ trợ String.repeat(), có thể thay phần tạo indent bằng một helper tương thích.

### 4.3. Duyệt cây không giả định số cấp

Không nên chỉ đọc node gốc và một cấp node con. Expression có thể lồng nhiều tầng:

~~~java
orders.?[
    customer != null
    && customer.active
    && total >= #minimum
].![id]
~~~

Hãy duyệt đệ quy hoặc dùng stack để xử lý toàn bộ cây. Mỗi node có thể có số node con khác nhau; không giả định mọi loại node đều có cùng cấu trúc.

### 4.4. Dùng stack thay cho recursion sâu

Nếu source do hệ thống sinh ra và có thể lồng rất sâu, duyệt đệ quy có thể làm tăng độ sâu call stack. Có thể dùng Deque:

~~~java
Deque<SpelNode> pending = new ArrayDeque<>();
pending.push(root);

while (!pending.isEmpty()) {
    SpelNode node = pending.pop();

    System.out.println(node.toStringAST());

    for (int i = node.getChildCount() - 1; i >= 0; i--) {
        pending.push(node.getChild(i));
    }
}
~~~

Ví dụ trên duyệt theo chiều sâu và giữ thứ tự node con từ trái sang phải bằng cách push ngược. Nếu cần lưu depth hoặc parent, hãy đặt node cùng metadata vào một record hoặc object riêng trong stack.

## 5. Hiểu node trong một expression

### 5.1. Literal

Expression:

~~~java
'Spring'
~~~

hoặc:

~~~java
42
~~~

chứa node đại diện cho literal. Literal cung cấp giá trị cố định đã được parser nhận diện.

Khi debug, kiểm tra literal giúp phát hiện các vấn đề như:

- Chuỗi bị đóng/mở dấu nháy sai.
- Giá trị số có định dạng không mong đợi.
- Kiểu literal không phù hợp với method hoặc property đích.
- Source generator đã escape ký tự không đúng.

### 5.2. Property access

Expression:

~~~java
customer.address.city
~~~

có các thành phần truy cập property theo chuỗi. Khi evaluate, SpEL phải phân giải từng bước qua PropertyAccessor phù hợp.

Nếu lỗi xuất hiện ở city, hãy kiểm tra:

- customer có null không.
- address có null không.
- Kiểu thực tế của customer và address.
- Property city có tồn tại và accessor có thể đọc không.
- Getter có ném exception hoặc thực hiện truy cập backend không.

AST cho biết đường dẫn property mà parser đã nhận. Nó không cho biết giá trị runtime của từng bước.

### 5.3. Method call

Expression:

~~~java
customer.findAddress('HOME')
~~~

có node biểu diễn target, tên method và argument. Khi evaluate, MethodResolver tìm executor phù hợp và các argument được đánh giá/chuyển đổi.

Nếu method resolution thất bại, hãy kiểm tra tên method, số argument, kiểu argument và resolver đang cấu hình. Nếu method được gọi nhưng ném exception, kiểm tra cause từ logic Java bên trong.

### 5.4. Operator

Expression:

~~~java
total >= #minimum && active
~~~

kết hợp các node phép so sánh và logic. AST giúp thấy cách parser nhóm các toán tử và toán hạng.

Dùng dấu ngoặc khi muốn thể hiện thứ tự ưu tiên rõ ràng:

~~~java
(total >= #minimum) && active
~~~

Không dựa vào việc người đọc tự nhớ mọi mức precedence khi biểu thức có nhiều toán tử. Một expression dễ đọc giúp debug nhanh hơn và giảm nguy cơ logic khác với dự định.

### 5.5. Selection và projection

Selection:

~~~java
orders.?[total >= #minimum]
~~~

Projection:

~~~java
orders.![id]
~~~

AST thể hiện selection/projection cùng predicate hoặc expression được áp dụng cho từng phần tử. Trong lúc evaluate, #this thay đổi theo phần tử hiện tại còn #root vẫn là root object của context.

Nếu selection trả về rỗng hoặc projection cho kết quả bất ngờ, hãy kiểm tra cả node collection nguồn lẫn predicate/projection. Cây cú pháp không thể cho biết collection runtime đang chứa phần tử nào.

### 5.6. Ternary và Elvis operator

Ví dụ:

~~~java
active ? 'enabled' : 'disabled'
~~~

và:

~~~java
nickname ?: 'anonymous'
~~~

AST giúp nhìn thấy node điều kiện và các nhánh. Khi debug, hãy kiểm tra nhánh nào thực sự được evaluate. Không giả định cả hai nhánh ternary đều chạy; thông thường chỉ nhánh được chọn mới được đánh giá.

Với Elvis operator, kiểm tra giá trị runtime của vế trái để biết fallback có được dùng hay không.

## 6. Phân biệt lỗi parse và lỗi evaluate

### 6.1. Parse error

Parse error xảy ra khi source không phù hợp cú pháp SpEL:

~~~java
total >= && active
~~~

Ví dụ:

~~~java
try {
    parser.parseExpression("total >= && active");
} catch (SpelParseException ex) {
    logger.error(
            "Could not parse expression at position {}",
            ex.getPosition(),
            ex
    );
}
~~~

SpelParseException là exception chuyên biệt cho lỗi parse của SpEL. Nó có thể cung cấp vị trí, message code và các dữ liệu liên quan tới lỗi theo API phiên bản đang dùng.

Khi gặp parse error, hãy kiểm tra source và vị trí lỗi trước. Không cần kiểm tra root object hoặc giá trị runtime nếu parser chưa tạo được expression.

### 6.2. Evaluation error

Evaluation error xảy ra sau khi parse thành công, khi SpEL cần truy cập dữ liệu hoặc thực thi một node:

~~~java
try {
    Object result = expression.getValue(context);
} catch (SpelEvaluationException ex) {
    logger.error(
            "Expression evaluation failed at position {}",
            ex.getPosition(),
            ex
    );
}
~~~

Nguyên nhân có thể gồm:

- Property không tồn tại hoặc receiver null.
- Method không có overload phù hợp.
- Constructor không thể được gọi.
- Bean reference không phân giải được.
- TypeConverter không chuyển được argument.
- Getter, method hoặc constructor ném exception.
- Index vượt phạm vi hoặc thao tác ghi không được hỗ trợ.

Khi gặp evaluation error, hãy kiểm tra context và target runtime cùng với node/position được báo.

### 6.3. Không gộp hai loại lỗi

Parse error và evaluation error cần được ghi nhận riêng:

| Giai đoạn | Exception thường gặp | Hướng điều tra |
|---|---|---|
| Parse | SpelParseException | Source, cú pháp, vị trí và parser configuration |
| Evaluate | SpelEvaluationException | AST, root object, biến, accessor, resolver, converter và dữ liệu |
| Code bên trong method/getter | Exception gốc hoặc được bọc | Logic Java, backend và cause chain |

Không bắt mọi exception rồi báo “expression không hợp lệ”. Câu thông báo đó không phân biệt source sai cú pháp với dữ liệu runtime bị thiếu hoặc service bên trong bị lỗi.

## 7. Dùng vị trí node để khoanh vùng lỗi

### 7.1. Source position

SpelNode cung cấp start và end position cho node. Thông tin này có thể giúp xác định đoạn source tương ứng với node.

Khi in cây, hãy giữ lại vị trí của từng node:

~~~java
System.out.printf(
        "%s [%d, %d]%n",
        node.toStringAST(),
        node.getStartPosition(),
        node.getEndPosition()
);
~~~

Vị trí được tính theo cách parser của phiên bản Spring cung cấp. Khi hiển thị cho người dùng, hãy đối chiếu với cùng source string đã parse; đừng áp vị trí từ expression đã format lại lên source ban đầu.

### 7.2. Position trong exception

ExpressionException và các exception SpEL liên quan có thể cung cấp vị trí lỗi. Với SpelEvaluationException, hãy ghi nhận:

- getPosition().
- getMessageCode() nếu cần phân loại theo mã lỗi.
- getInserts() khi cần các tham số mô tả lỗi.
- Cause chain để tìm lỗi gốc.

Các API và thông tin cụ thể có thể khác giữa phiên bản Spring. Khi viết diagnostic helper dùng chung, hãy biên dịch và kiểm thử với phiên bản dependency thực tế của dự án.

### 7.3. Vị trí không luôn xác định nguyên nhân cuối cùng

Một node có thể gọi getter, method hoặc resolver. Exception có thể được báo tại node đang thực hiện thao tác, trong khi nguyên nhân gốc nằm sâu trong code Java.

Ví dụ, lỗi tại customer.address có thể do getter getAddress() gọi repository và repository bị lỗi. AST giúp xác định điểm SpEL đang truy cập; cause chain giúp xác định lỗi bên trong getter.

Hãy kết hợp vị trí với loại target và stack trace, không kết luận chỉ từ một số offset.

## 8. Một quy trình debug có thể lặp lại

### 8.1. Ghi nhận source và định danh expression

Trước khi parse, ghi lại định danh rule, phiên bản cấu hình và source đã được kiểm soát:

~~~java
logger.debug(
        "Parsing expressionId={}, version={}, source={}",
        expressionId,
        version,
        source
);
~~~

Nếu source có thể chứa thông tin nhạy cảm, không log nguyên văn trong log production. Có thể log expression ID, hash, độ dài và một bản đã redact theo chính sách.

### 8.2. Parse riêng và bắt lỗi parse

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
} catch (SpelParseException ex) {
    logger.error(
            "SpEL parse failed: position={}, code={}",
            ex.getPosition(),
            ex.getMessageCode(),
            ex
    );
    throw ex;
}
~~~

Tách bước parse giúp biết lỗi có xảy ra trước khi context tham gia hay không.

### 8.3. In AST khi cần

Nếu parser trả về SpelExpression, lấy AST và in cấu trúc:

~~~java
if (expression instanceof SpelExpression spelExpression) {
    printTree(spelExpression.getAST(), 0);
}
~~~

Chỉ bật log AST khi cần chẩn đoán. Một expression lớn có thể tạo nhiều dòng log; tránh ghi liên tục ở mức production nếu không có nhu cầu.

### 8.4. Đánh giá với context xác định

Khi evaluate, ghi nhận loại root object và các loại biến cần thiết:

~~~java
logger.debug(
        "Evaluating expressionId={}, rootType={}",
        expressionId,
        rootObject == null
                ? "null"
                : rootObject.getClass().getName()
);
~~~

Không log toàn bộ object hoặc biến nếu chúng có thể chứa thông tin cá nhân, token, secret hay dữ liệu khách hàng.

Để tái hiện lỗi, cần dùng đúng:

- Source expression.
- Phiên bản parser và SpelParserConfiguration.
- Loại root object và trạng thái dữ liệu liên quan.
- Biến context và kiểu của chúng.
- PropertyAccessor, MethodResolver, BeanResolver và ConstructorResolver.
- TypeConverter/ConversionService.
- Parser context nếu dùng template.

### 8.5. Bắt lỗi evaluate và giữ cause

~~~java
try {
    Object result = expression.getValue(context);
    return result;
} catch (SpelEvaluationException ex) {
    logger.error(
            "SpEL evaluation failed: position={}, code={}",
            ex.getPosition(),
            ex.getMessageCode(),
            ex
    );
    throw ex;
}
~~~

Không chuyển mọi lỗi thành null hoặc false. Điều đó có thể khiến ứng dụng tiếp tục với kết quả sai và làm mất thông tin điều tra.

## 9. Ví dụ hoàn chỉnh: in source và AST

Ví dụ sau parse một expression, ghi source, in AST rồi evaluate:

~~~java
ExpressionParser parser = new SpelExpressionParser();

String source =
        "orders.?[total >= #minimum].![id]";

Expression expression = parser.parseExpression(source);

System.out.println(
        "Expression: " + expression.getExpressionString()
);

if (expression instanceof SpelExpression spelExpression) {
    SpelNode ast = spelExpression.getAST();

    System.out.println(
            "AST: " + ast.toStringAST()
    );

    printTree(ast, 0);
}

StandardEvaluationContext context =
        new StandardEvaluationContext(report);

context.setVariable(
        "minimum",
        new BigDecimal("100")
);

List<?> ids = expression.getValue(context, List.class);
~~~

Trong ví dụ:

1. Source được lưu trong biến source.
2. Parser tạo Expression.
3. getExpressionString() cung cấp chuỗi gắn với Expression.
4. getAST() lấy node gốc của SpelExpression.
5. toStringAST() hiển thị biểu diễn AST.
6. printTree() duyệt cấu trúc node.
7. EvaluationContext cung cấp root object và biến minimum.
8. getValue() thực hiện đánh giá trên dữ liệu runtime.

Nếu lỗi xảy ra ở bước 7 hoặc 8, AST vẫn có thể hoàn toàn hợp lệ. Khi đó hãy kiểm tra dữ liệu và các resolver/accessor thay vì sửa source theo suy đoán.

## 10. AST và SpEL compiler

### 10.1. AST thuộc giai đoạn parse

AST là cấu trúc cú pháp được tạo khi parser xử lý source. SpEL có thể dùng cấu trúc này để đánh giá expression và, trong một số chế độ, biên dịch expression thành dạng thực thi tối ưu hơn.

AST giúp hiểu parser đã nhận dạng cú pháp nào. Nó không phải bytecode đã biên dịch và không hiển thị đầy đủ trạng thái của compiler hoặc class được tạo ra.

### 10.2. Khác biệt giữa interpreted và compiled mode

Nếu ứng dụng bật SpEL compiler, một expression có thể được thực thi theo đường đã biên dịch sau khi đủ điều kiện. Khi debug lỗi chỉ xuất hiện ở một chế độ, hãy tái hiện bằng đúng compiler mode của ứng dụng.

Có thể so sánh chế độ interpreted và compiled trong một test riêng với cấu hình tương ứng của phiên bản Spring đang dùng. Không kết luận AST sai chỉ vì hành vi runtime khác nhau giữa hai chế độ.

### 10.3. AST node là chi tiết triển khai

Không nên viết code nghiệp vụ kiểu:

~~~java
if (node.getClass().getSimpleName().equals("SomeInternalNode")) {
    // quyết định quyền nghiệp vụ
}
~~~

Tên class và cách chia node có thể thay đổi khi Spring cập nhật parser. Nếu cần kiểm soát expression, hãy dùng allowlist cú pháp hoặc validation được thiết kế rõ ràng, không dựa vào tên class nội bộ của AST như ranh giới bảo mật.

AST traversal phù hợp cho logging, diagnostics và công cụ phân tích. Việc cho phép hay từ chối expression cần một chính sách riêng và được kiểm thử theo phiên bản.

## 11. Những lỗi thường gặp khi đọc source và AST

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Expression string khác source đã nhập | Source được normalize hoặc lấy từ cấu hình khác phiên bản | Lưu source gốc và version |
| Không cast được sang SpelExpression | Parser trả về implementation khác hoặc wrapper | Kiểm tra instanceof trước khi gọi getAST() |
| Không thấy khoảng trắng trong AST | toStringAST() là biểu diễn cú pháp, không phải source nguyên văn | Dùng getExpressionString() để xem source |
| AST đúng nhưng evaluate lỗi | Lỗi nằm ở dữ liệu hoặc resolver runtime | Kiểm tra EvaluationContext và cause |
| Không biết node nào gây lỗi | Chỉ log exception message | Ghi position, message code và duyệt AST |
| Vị trí không khớp source hiển thị | Dùng source đã format lại hoặc template context khác | Đối chiếu với đúng chuỗi đã parse |
| Log AST quá lớn | Expression có nhiều node hoặc lồng sâu | Giới hạn mức log và chỉ bật khi cần |
| Code debug phụ thuộc tên node | Dùng implementation class như API ổn định | Dựa vào SpelNode interface và tránh logic nghiệp vụ |
| Lỗi chỉ xuất hiện khi compiler bật | Khác biệt giữa interpreted và compiled execution | Tái hiện với đúng compiler mode |
| Log lộ dữ liệu nhạy cảm | Ghi toàn bộ expression hoặc biến | Redact, log ID/hash và metadata an toàn |

## 12. Nguyên tắc logging an toàn

Expression source có thể chứa tên bean, property nội bộ, dữ liệu người dùng hoặc literal nhạy cảm. AST cũng có thể hiển thị lại các literal đó.

Khi ghi log:

- Ưu tiên expression ID, version, hash và độ dài.
- Chỉ log source hoặc AST ở môi trường phát triển hoặc khi đã redact.
- Không log password, token, email, số tài khoản hay dữ liệu cá nhân.
- Không log toàn bộ root object hoặc collection lớn.
- Ghi nhận class của root object và kiểu biến thay vì giá trị nhạy cảm.
- Giới hạn độ dài log để tránh một expression lớn làm phình log.
- Giữ exception cause trong log nội bộ nhưng không trả stack trace cho client.
- Phân biệt parse failure và evaluation failure bằng event hoặc mã lỗi riêng.

Nếu cần lưu source để tái hiện, hãy dùng kho diagnostic có kiểm soát quyền truy cập và thời hạn lưu trữ phù hợp.

## 13. Checklist chẩn đoán expression

Khi điều tra một expression lỗi, hãy xác nhận:

- Source chính xác đã được lưu trước khi parse.
- Đúng parser và SpelParserConfiguration được dùng.
- Expression parse thành công hay thất bại.
- Nếu parse thành công, Expression implementation có phải SpelExpression không.
- AST được lấy qua getAST() và biểu diễn bằng toStringAST().
- Node con và source position được ghi nhận khi cần.
- Đúng root object, biến và kiểu dữ liệu runtime.
- Accessor, resolver và TypeConverter giống cấu hình production.
- Exception được phân loại theo parse/evaluate và giữ cause.
- Source/AST/log đã được redact nếu có dữ liệu nhạy cảm.
- Nếu compiler mode được bật, lỗi đã được tái hiện với đúng chế độ.

Không cần in toàn bộ AST cho mọi request. Hãy bật diagnostics có chọn lọc theo expression ID hoặc khi có lỗi để tránh log quá nhiều và lộ dữ liệu.

## 14. Tổng kết

Đọc expression string và expression tree giúp tách lỗi source khỏi lỗi xảy ra khi đánh giá:

- **getExpressionString()** cung cấp chuỗi expression gắn với Expression.
- **SpelExpression.getAST()** lấy node gốc khi parser trả về SpelExpression.
- **SpelNode.toStringAST()** cung cấp biểu diễn cú pháp của node.
- **getChildCount()** và **getChild(index)** cho phép duyệt cây.
- **getStartPosition()** và **getEndPosition()** hỗ trợ khoanh vùng source.
- **SpelParseException** giúp điều tra lỗi cú pháp; **SpelEvaluationException** giúp điều tra lỗi runtime.
- AST không chứa trạng thái dữ liệu runtime và không nên được dùng như API nội bộ ổn định để phân quyền.
- Logging cần bảo vệ source, literal và dữ liệu trong EvaluationContext.

Quy trình hiệu quả là lưu source chính xác, parse riêng, quan sát AST khi cần, evaluate với context có thể tái hiện và đọc cause chain cùng vị trí lỗi. Cách này giúp xác định lỗi nằm ở cú pháp, cấu trúc biểu thức, dữ liệu runtime hay extension point mà không phải suy đoán từ exception cuối cùng.