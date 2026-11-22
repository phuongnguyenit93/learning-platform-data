# Parser, expression tree và quá trình phân tích cú pháp

## 1. Parser nằm ở đâu trong kiến trúc SpEL?

Spring Expression Language (SpEL) là ngôn ngữ biểu thức mà Spring dùng để mô tả phép tính, điều kiện và thao tác trên object graph. Một biểu thức như `order.total * (1 - discount)` nhìn giống một dòng code ngắn, nhưng Spring phải hiểu cấu trúc cú pháp của nó trước khi có thể tính kết quả.

Parser đảm nhiệm bước chuyển chuỗi ký tự thành một cấu trúc có ý nghĩa. Cấu trúc trung gian đó thường được gọi là **expression tree** hoặc **abstract syntax tree (AST)**. Khi đã có AST, Spring có thể đánh giá biểu thức với một object cụ thể và một `EvaluationContext`.

Luồng tổng quát:

    Chuỗi biểu thức
          |
          v
    Parser / Tokenizer
          |
          v
    Danh sách token
          |
          v
    Phân tích cú pháp theo grammar
          |
          v
    Expression Tree (AST)
          |
          v
    Expression
          |
          v
    EvaluationContext + root object
          |
          v
    Giá trị kết quả

Hai giai đoạn cần được phân biệt rõ:

- **Parsing** trả lời câu hỏi: chuỗi này có đúng cú pháp SpEL không, và cấu trúc của nó là gì?
- **Evaluation** trả lời câu hỏi: với dữ liệu và context hiện tại, biểu thức cho ra kết quả nào?

Parser không cần gọi method nghiệp vụ hoặc đọc giá trị property của object thật để dựng AST. Những việc đó thuộc giai đoạn evaluation.

## 2. Các thành phần chính

### ExpressionParser

`ExpressionParser` là abstraction công khai để phân tích một biểu thức. Code ứng dụng thường phụ thuộc vào interface này để giảm phụ thuộc vào implementation cụ thể.

Implementation tiêu chuẩn là `SpelExpressionParser` trong package `org.springframework.expression.spel.standard`.

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression("2 + 3 * 4");

    Integer result = expression.getValue(Integer.class);
    // result = 14

Lệnh `parseExpression` tạo ra một `Expression`. Việc gọi `getValue` mới thực sự đánh giá biểu thức.

### SpelExpressionParser

`SpelExpressionParser` là điểm vào tiêu chuẩn của SpEL. Nó nhận chuỗi đầu vào, cấu hình parser nếu có, và trả về đối tượng biểu thức đã được phân tích.

Trong implementation của Spring, công việc parsing chi tiết được thực hiện bởi parser nội bộ. Khi đọc source code, có thể gặp các thành phần như `InternalSpelExpressionParser`, tokenizer và các loại token. Đây là chi tiết triển khai; code ứng dụng thông thường chỉ cần dùng `ExpressionParser`.

### ParserContext

`ParserContext` cho parser biết chuỗi đầu vào là một biểu thức độc lập hay một template có chứa các đoạn biểu thức.

Với biểu thức độc lập, parser hiểu toàn bộ chuỗi là SpEL:

    parser.parseExpression("order.total > 1000");

Với template, văn bản thông thường được giữ nguyên và phần nằm trong delimiter mới được phân tích như SpEL:

    ExpressionParser parser = new SpelExpressionParser();

    Expression template = parser.parseExpression(
        "Xin chào, #{#user.name}!",
        new TemplateParserContext()
    );

    String message = template.getValue(context, String.class);

`TemplateParserContext` mặc định dùng `#{` và `}` làm delimiter. Có thể truyền một `ParserContext` khác nếu ứng dụng cần quy ước delimiter riêng. Không nên nhầm dấu `#{...}` của template với việc parser luôn yêu cầu mọi biểu thức độc lập phải có dấu này.

### SpelParserConfiguration

`SpelParserConfiguration` cho phép cấu hình một số hành vi của SpEL, chẳng hạn compiler mode và một số giới hạn hoặc hành vi hỗ trợ truy cập dữ liệu. Cấu hình được truyền vào khi tạo `SpelExpressionParser`.

    SpelParserConfiguration configuration =
        new SpelParserConfiguration();

    ExpressionParser parser =
        new SpelExpressionParser(configuration);

Chỉ nên bật các hành vi mở rộng khi đã hiểu tác động của chúng lên dữ liệu và hiệu năng. Cấu hình parser không thay thế cho việc thiết kế một `EvaluationContext` phù hợp.

### Expression và SpelExpression

`Expression` là abstraction mà ứng dụng dùng để lấy hoặc gán giá trị biểu thức. `SpelExpression` là implementation của SpEL, giữ kết quả parsing và điều phối việc evaluation.

Với `SpelExpression`, phương thức `toStringAST()` hữu ích khi cần xem biểu diễn AST ở dạng chuỗi để hỗ trợ debug. Không nên dựa vào định dạng chuỗi này như một giao thức serialization ổn định.

### EvaluationContext

`EvaluationContext` cung cấp môi trường để đánh giá AST. Nó có thể chứa:

- Root object mà biểu thức truy cập mặc định.
- Variables, ví dụ `#minimum` hoặc `#user`.
- Property accessors để đọc hoặc ghi property.
- Method resolvers và constructor resolvers.
- Type locator, bean resolver và cơ chế chuyển đổi kiểu.
- Các thành phần hỗ trợ kiểm soát cách biểu thức truy cập dữ liệu.

`StandardEvaluationContext` cung cấp nhiều khả năng truy cập linh hoạt. `SimpleEvaluationContext` được thiết kế cho các trường hợp data binding cần giới hạn tập tính năng được phép.

Điểm quan trọng: `EvaluationContext` thường được sử dụng khi evaluation, không phải dữ liệu đầu vào bắt buộc để parser dựng cấu trúc cú pháp.

## 3. Từ ký tự thành token: lexical analysis

Trước khi hiểu một biểu thức, parser cần nhận diện các đơn vị cú pháp. Quá trình này gọi là **lexical analysis** (phân tích từ vựng). Tokenizer đọc chuỗi ký tự và tạo ra các token.

Ví dụ:

    2 + 3 * 4

Có thể được tách thành các token có ý nghĩa:

| Phần đầu vào | Ý nghĩa |
| --- | --- |
| `2` | Literal số |
| `+` | Toán tử cộng |
| `3` | Literal số |
| `*` | Toán tử nhân |
| `4` | Literal số |

Một biểu thức truy cập property:

    customer.address.city

có các thành phần nhận diện như identifier và dấu chấm truy cập property.

Tùy cú pháp, tokenizer cần nhận diện các nhóm như:

- **Identifier:** tên property, method, variable hoặc tên kiểu.
- **Literal:** số, chuỗi, boolean và null.
- **Operator:** toán tử số học, so sánh, logic, gán và toán tử đặc biệt của SpEL.
- **Delimiter:** dấu ngoặc tròn, ngoặc vuông, dấu phẩy và dấu chấm.
- **Keyword hoặc token chuyên biệt:** các từ khóa và ký hiệu có ý nghĩa riêng trong grammar.

Token thường giữ thông tin loại token và vị trí trong chuỗi nguồn. Vị trí này giúp parser xác định đoạn nào gây lỗi và đưa ra thông báo có thể chỉ đến vị trí ký tự.

Tokenizer chỉ nhận diện các đơn vị cú pháp. Nó chưa quyết định phép toán nào phải thực hiện trước, cũng chưa biết property có tồn tại trên object tại runtime hay không.

## 4. Parsing: áp dụng grammar và precedence

Sau khi có token, parser phân tích thứ tự và mối quan hệ giữa chúng theo grammar của SpEL. Kết quả không chỉ là danh sách token mà là một cấu trúc lồng nhau.

Một parser biểu thức cần xử lý ít nhất các vấn đề sau:

1. Xác định đâu là biểu thức con và đâu là dấu phân cách.
2. Áp dụng độ ưu tiên của toán tử.
3. Áp dụng tính kết hợp trái hoặc phải theo grammar.
4. Nhận diện các cấu trúc như lời gọi method, truy cập property, index, điều kiện và collection operation.
5. Phát hiện cú pháp không hợp lệ hoặc biểu thức chưa hoàn chỉnh.

Ví dụ:

    2 + 3 * 4

Phép nhân có độ ưu tiên cao hơn phép cộng. Vì vậy cây cú pháp có dạng:

          +
         / \
        2   *
           / \
          3   4

Nghĩa là parser hiểu biểu thức thành:

    2 + (3 * 4)

chứ không phải:

    (2 + 3) * 4

Nếu cần thay đổi thứ tự, dấu ngoặc tạo ra một cấu trúc con rõ ràng:

    (2 + 3) * 4

Khi đọc một biểu thức phức tạp, hãy phân tích từ các phần có độ ưu tiên cao và cấu trúc lồng nhau trước. Không nên đọc biểu thức như một chuỗi trái sang phải rồi giả định mọi toán tử có cùng mức ưu tiên.

## 5. Expression tree (AST)

AST là biểu diễn cấu trúc của biểu thức sau parsing. Mỗi node mô tả một thành phần cú pháp hoặc một phép toán. Node có thể chứa các node con, nhờ vậy cấu trúc lồng nhau được thể hiện rõ.

Với biểu thức:

    2 + 3 * 4

AST có thể được hình dung như sau:

    Plus
    |-- Literal(2)
    |-- Multiply
        |-- Literal(3)
        |-- Literal(4)

Node gốc là phép cộng. Nhánh phải của nó là phép nhân; hai literal 3 và 4 là con của node nhân. Cây này giữ lại ý nghĩa precedence mà parser đã xác định.

Một số nhóm node có thể xuất hiện trong AST SpEL:

| Nhóm node | Vai trò |
| --- | --- |
| Literal | Giá trị hằng như số, chuỗi, boolean hoặc null |
| Operator | Phép toán số học, so sánh hoặc logic |
| Property/field reference | Truy cập property hoặc field |
| Method reference | Biểu diễn lời gọi method |
| Indexer | Truy cập phần tử theo index hoặc key |
| Type reference | Tham chiếu kiểu bằng cú pháp SpEL |
| Constructor reference | Biểu diễn thao tác tạo object |
| Ternary/Elvis | Biểu thức điều kiện và giá trị thay thế |
| Selection/projection | Lọc hoặc biến đổi phần tử collection |
| Compound expression | Kết hợp nhiều bước truy cập liên tiếp |

Ví dụ:

    customer.address.city

có thể được hiểu là một chuỗi truy cập liên tiếp: bắt đầu từ `customer`, lấy `address`, sau đó lấy `city`. Nếu một bước truy cập trả về null, việc truy cập bước tiếp theo có thể thất bại khi evaluation, trừ khi biểu thức dùng safe navigation phù hợp.

AST không phải bản sao nguyên văn của source. Nó mô tả ý nghĩa cú pháp. Những khoảng trắng, cách viết tương đương hoặc dấu ngoặc không cần thiết có thể không còn được giữ như cách người viết ban đầu đã nhập.

Trong implementation SpEL, các node được tổ chức qua abstraction như `SpelNode` và các implementation node cụ thể. `SpelExpression` giữ root node của biểu thức đã parse. Đây là lý do expression tree là cấu trúc trung tâm nối parsing với evaluation.

## 6. Parser không thực thi biểu thức

Xét ví dụ:

    account.balance >= 500

Khi parsing, Spring có thể xác định:

- `account` là một phần truy cập đối tượng.
- `balance` là property tiếp theo.
- `>=` là toán tử so sánh.
- `500` là literal số.
- Toàn bộ biểu thức là phép so sánh hai vế.

Nhưng parser chưa thể kết luận biểu thức trả về true hay false nếu chưa có object và context để đánh giá.

Khi gọi:

    ExpressionParser parser = new SpelExpressionParser();
    Expression expression = parser.parseExpression(
        "account.balance >= 500"
    );

ta đã có một đối tượng `Expression`. Để evaluation, cần cung cấp biến hoặc root object tương ứng:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("account", account);

    Boolean allowed =
        expression.getValue(context, Boolean.class);

Ở đây `#account` là cú pháp tham chiếu variable trong SpEL. Vì vậy, nếu dùng variable thì biểu thức phải viết:

    #account.balance >= 500

Ví dụ đầy đủ hơn:

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression =
        parser.parseExpression("#account.balance >= #minimum");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("account", account);
    context.setVariable("minimum", 500);

    Boolean allowed =
        expression.getValue(context, Boolean.class);

Parser xử lý cú pháp của `#account` và `#minimum`; evaluation context cung cấp giá trị thật của hai variable đó.

## 7. Quá trình evaluation sau khi có AST

Khi gọi `getValue(...)`, SpEL điều phối việc đánh giá các node trong AST. Tùy loại node, quá trình có thể cần:

- Đọc literal trực tiếp.
- Đánh giá các node con trước rồi áp dụng toán tử.
- Tìm property accessor phù hợp để đọc property.
- Tìm method resolver để chọn method có thể gọi.
- Chuyển đổi kiểu khi phép toán hoặc method yêu cầu.
- Truy cập collection, map hoặc phần tử theo index.
- Xử lý root object, variable và function trong context.

Ví dụ với:

    #order.total * (1 - #discount)

SpEL cần lấy giá trị `order.total`, lấy variable `discount`, tính phần trong ngoặc rồi thực hiện phép nhân. Cây AST cho biết cấu trúc và thứ tự phép toán; context cung cấp dữ liệu để từng node có thể được đánh giá.

Property hoặc method chỉ được giải quyết khi evaluation cần truy cập chúng. Vì vậy một biểu thức có thể parse thành công nhưng vẫn thất bại khi chạy, chẳng hạn property không tồn tại, method không phù hợp, giá trị null ở vị trí không cho phép hoặc kiểu dữ liệu không tương thích.

## 8. Expression template

SpEL có thể được nhúng vào một chuỗi văn bản. Trong trường hợp này, parser cần phân biệt phần văn bản thường và phần biểu thức.

Ví dụ:

    String source = "Đơn hàng #{#order.id} có tổng tiền #{#order.total}";

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
        source,
        new TemplateParserContext()
    );

    String output = expression.getValue(context, String.class);

Parser template chia source thành các đoạn văn bản và các đoạn biểu thức nằm trong delimiter. Những đoạn biểu thức được parse theo grammar SpEL; văn bản ngoài delimiter được giữ như nội dung tĩnh.

Dùng template khi cần ghép kết quả biểu thức vào nội dung thông báo. Dùng parsing thông thường khi toàn bộ chuỗi đầu vào chính là một biểu thức.

## 9. Parse error và evaluation error

Hai loại lỗi xảy ra ở hai thời điểm khác nhau:

| Loại lỗi | Thời điểm | Ví dụ |
| --- | --- | --- |
| Parse error | Khi gọi `parseExpression` | Thiếu dấu ngoặc, toán tử không có toán hạng, cấu trúc cú pháp sai |
| Evaluation error | Khi gọi `getValue` hoặc `setValue` | Property không tồn tại, method không gọi được, truy cập null, chuyển đổi kiểu thất bại |

Parse error thường được biểu diễn bởi `SpelParseException`. Thông báo lỗi có thể cung cấp vị trí trong chuỗi nguồn để xác định đoạn cú pháp có vấn đề.

Evaluation error thường được biểu diễn bởi `SpelEvaluationException`. Lỗi này cho biết cú pháp đã được chấp nhận nhưng không thể thực hiện với dữ liệu hoặc context hiện tại.

Khi debug, hãy xác định lỗi xảy ra ở dòng `parseExpression` hay ở dòng `getValue`. Nếu parse thất bại, kiểm tra grammar, dấu ngoặc, literal và thứ tự token. Nếu evaluation thất bại, kiểm tra root object, variable, property accessor, method resolver, giá trị null và kiểu dữ liệu.

## 10. Parsing, caching và compiler

Một biểu thức thường được parse một lần rồi sử dụng nhiều lần. Giữ lại đối tượng `Expression` giúp tránh phải parse lại cùng một chuỗi trong mỗi lần xử lý request.

Ví dụ:

    private final ExpressionParser parser =
        new SpelExpressionParser();

    private final Expression eligibility =
        parser.parseExpression("#customer.active and #customer.score >= 80");

    public boolean isEligible(Customer customer) {
        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.setVariable("customer", customer);

        return Boolean.TRUE.equals(
            eligibility.getValue(context, Boolean.class)
        );
    }

Ví dụ này giữ lại `Expression` sau khi khởi tạo. Mỗi lần evaluation vẫn cần context phù hợp với dữ liệu của lần gọi đó. Không chia sẻ một context có state thay đổi giữa các request đồng thời nếu chưa kiểm soát an toàn việc truy cập.

SpEL còn có compiler để tối ưu một số biểu thức khi đủ điều kiện. Các compiler mode thường gặp là `OFF`, `IMMEDIATE` và `MIXED`. Compiler có thể tạo implementation thực thi nhanh hơn cho những biểu thức hỗ trợ được. Không phải mọi cấu trúc SpEL đều có thể compile; ở chế độ phù hợp, framework có thể tiếp tục dùng cơ chế evaluation thông thường khi không compile được.

Compiler là bước tối ưu thực thi sau parsing. Nó không thay đổi vai trò của AST trong việc biểu diễn cấu trúc cú pháp.

## 11. Cách debug parser và AST

Khi cần hiểu một biểu thức khó đọc, hãy đi theo các bước sau:

1. Lưu nguyên chuỗi source của biểu thức để có thể đối chiếu vị trí lỗi.
2. Gọi `parseExpression` riêng để xác định cú pháp có hợp lệ không.
3. Nếu đang dùng `SpelExpression`, xem `toStringAST()` để quan sát biểu diễn AST.
4. Thử chia biểu thức thành các phần nhỏ, parse từng phần để tìm node hoặc cấu trúc gây lỗi.
5. Chỉ sau khi parsing thành công mới kiểm tra evaluation context và dữ liệu runtime.
6. Kiểm tra kiểu kết quả mong muốn khi dùng overload `getValue(..., desiredResultType)`.

Ví dụ:

    SpelExpressionParser parser = new SpelExpressionParser();

    SpelExpression expression =
        (SpelExpression) parser.parseExpression(
            "#order.total + #shipping.fee * 2"
        );

    System.out.println(expression.toStringAST());

Ép kiểu sang `SpelExpression` ở đây nhằm dùng API debug riêng của implementation SpEL. Nếu code chỉ cần đọc giá trị biểu thức, giữ kiểu abstraction `Expression` sẽ phù hợp hơn.

## 12. Giới hạn quyền truy cập khi đánh giá biểu thức

Vì SpEL có thể hỗ trợ truy cập property, gọi method, tham chiếu type, tạo object và truy cập bean tùy context, không nên đánh giá tùy ý biểu thức do người dùng không tin cậy cung cấp bằng một context có đầy đủ quyền.

Một số nguyên tắc:

- Không ghép trực tiếp input không tin cậy vào chuỗi biểu thức rồi đánh giá.
- Chỉ đưa vào context những variable và object mà biểu thức thực sự cần.
- Dùng `SimpleEvaluationContext` khi nghiệp vụ chỉ cần một tập tính năng giới hạn.
- Cấu hình property accessor hoặc method resolver theo đúng phạm vi cần thiết.
- Không bật quyền truy cập rộng chỉ để làm cho một biểu thức hoạt động.
- Xem expression text như một loại đầu vào có khả năng thực thi logic.

Parser chỉ kiểm tra và tạo cấu trúc cú pháp. Việc giới hạn những gì biểu thức được phép truy cập chủ yếu nằm ở evaluation context và các thành phần resolver/accessor mà ứng dụng cung cấp.

## 13. Những điểm cần nhớ

- `ExpressionParser` là abstraction công khai; `SpelExpressionParser` là implementation tiêu chuẩn của SpEL.
- Tokenizer nhận diện các đơn vị cú pháp; parser áp dụng grammar, precedence và associativity.
- AST biểu diễn cấu trúc biểu thức bằng các node lồng nhau.
- `Expression` là kết quả parsing mà ứng dụng có thể giữ lại và đánh giá nhiều lần.
- `EvaluationContext` cung cấp root object, variable và cơ chế truy cập dữ liệu khi evaluation.
- Parse thành công không đảm bảo evaluation thành công.
- Template parsing cho phép trộn văn bản thường với các đoạn SpEL.
- Compiler có thể tối ưu một số biểu thức, nhưng không thay thế trách nhiệm của parser và AST.
- Khi nhận biểu thức từ nguồn không tin cậy, cần giới hạn quyền trong evaluation context.

Khi đọc hoặc thiết kế một luồng dùng SpEL, hãy tách rõ ba câu hỏi: chuỗi được phân tích thành cấu trúc nào, cấu trúc đó được đánh giá với context nào, và context đó cho phép truy cập đến những gì. Ba câu hỏi này giúp xác định đúng nơi cần sửa khi biểu thức sai cú pháp, sai dữ liệu hoặc vượt quá quyền truy cập mong muốn.
