# Kiểm thử AST

Trong một compiler hoặc công cụ DSL (Domain-Specific Language), parser chuyển văn bản nguồn thành cấu trúc dữ liệu mà các bước xử lý sau có thể hiểu được. Cấu trúc đó thường được biểu diễn bằng **Abstract Syntax Tree (AST)** — cây cú pháp trừu tượng. **Kiểm thử AST** xác nhận parser và các bước xây dựng mô hình tạo ra cấu trúc đúng, giữ đúng quan hệ giữa các node, gán đúng loại biểu thức và bảo toàn thông tin cần thiết cho semantic analysis, code generation và tooling.

Một parser có thể chấp nhận văn bản nhưng vẫn tạo AST sai: toán tử bị nhóm sai, node con bị đặt nhầm cha, thứ tự statement bị đảo, identifier bị mất, source range không chính xác hoặc một cú pháp sugar tạo ra mô hình không như mong đợi. Nếu chỉ kiểm tra rằng parse không ném exception, những lỗi này có thể đi sâu vào compiler và gây ra kết quả sai khó tìm. AST tests giúp phát hiện vấn đề ngay tại ranh giới giữa source text và cấu trúc chương trình.

## 1. AST là gì?

AST là biểu diễn dạng cây của cấu trúc cú pháp có ý nghĩa đối với compiler. Mỗi node đại diện cho một thành phần như module, declaration, statement, expression, type, pattern hoặc literal. Các token thuần túy như dấu ngoặc, dấu chấm phẩy hay whitespace thường không được giữ như node độc lập nếu chúng không cần cho các bước xử lý tiếp theo.

Ví dụ DSL:

~~~text
let total = price * quantity + shipping
~~~

AST có thể có dạng:

~~~text
VariableDeclaration
├── name: total
└── initializer: BinaryExpression (+)
    ├── left: BinaryExpression (*)
    │   ├── Identifier(price)
    │   └── Identifier(quantity)
    └── right: Identifier(shipping)
~~~

Cây thể hiện phép nhân được nhóm trước phép cộng theo precedence của ngôn ngữ.

### 1.1. AST khác parse tree

Parse tree thường phản ánh trực tiếp các production trong grammar, có thể chứa nhiều node trung gian và token punctuation. AST được đơn giản hóa theo cấu trúc có ý nghĩa cho compiler.

| Parse tree | AST |
|---|---|
| Gần với grammar production | Gần với semantics của chương trình |
| Có thể chứa node trung gian | Thường loại bỏ node không cần thiết |
| Giữ nhiều chi tiết cú pháp | Tập trung vào cấu trúc biểu thức/declaration |
| Phù hợp phân tích parser | Phù hợp semantic analysis và transformation |

Một framework có thể gọi model parse được là AST dù nó còn giữ một số chi tiết cú pháp. Điều quan trọng trong kiểm thử là xác định rõ contract của model.

### 1.2. AST và concrete syntax tree

Concrete Syntax Tree (CST) thường giữ chi tiết cú pháp như dấu ngoặc, keyword, comment và token. AST có thể bỏ những chi tiết này hoặc lưu chúng ở node model/source trivia riêng. Nếu formatter, refactoring hoặc round-trip serializer cần comment và whitespace, cần kiểm thử phần dữ liệu cú pháp được giữ riêng.

### 1.3. AST và semantic model

AST phản ánh cấu trúc cú pháp. Semantic model có thể bổ sung symbol binding, type, scope, control-flow và thông tin đã resolve. Một compiler có thể dùng cùng một object graph cho cả hai hoặc chuyển AST sang các intermediate representation (IR) khác nhau.

## 2. Vì sao cần kiểm thử AST?

AST là hợp đồng giữa parser và phần lớn compiler pipeline. Một lỗi ở đây có thể ảnh hưởng nhiều thành phần cùng lúc.

Kiểm thử AST giúp:

- Xác nhận grammar tạo đúng node type.
- Xác nhận precedence và associativity của operator.
- Xác nhận parent-child relationships.
- Kiểm tra thứ tự declaration và statement.
- Bảo đảm literal và identifier giữ đúng giá trị.
- Xác nhận source span và token location.
- Kiểm tra cú pháp sugar được hạ về node đúng.
- Phát hiện node thiếu, node thừa hoặc node bị nhân đôi.
- Bảo đảm AST có thể được visitor/transformer xử lý.
- Giữ ổn định model khi grammar được mở rộng.

### 2.1. Parse thành công chưa đủ

Parser có thể không báo lỗi nhưng vẫn parse sai nghĩa. Ví dụ:

~~~text
a + b * c
~~~

Nếu AST là Multiply(Add(a,b),c) thay vì Add(a,Multiply(b,c)), parser đã tạo cây sai dù không có syntax error.

### 2.2. Snapshot AST chưa đủ

Snapshot giúp nhìn thấy toàn bộ cây, nhưng nếu chỉ so sánh chuỗi serialize mà không kiểm tra semantics của node, test có thể bỏ sót lỗi. Nên kết hợp structural assertions, invariants và test hành vi downstream.

### 2.3. AST tests không thay thế parser tests

Parser tests thường bao gồm acceptance/rejection của cú pháp. AST tests tập trung vào cấu trúc được tạo ra. Hai nhóm liên quan nhưng câu hỏi kiểm tra khác nhau.

## 3. Phạm vi kiểm thử AST

Có thể chia thành nhiều lớp:

| Lớp test | Mục tiêu |
|---|---|
| Node construction | Node type và field được tạo đúng |
| Tree structure | Parent, child và thứ tự đúng |
| Expression structure | Precedence, associativity và operand |
| Literal tests | Giá trị và kiểu literal chính xác |
| Source mapping | Range, token và line/column |
| Desugaring tests | Syntax sugar được chuyển thành core nodes đúng |
| Semantic annotation | Symbol/type metadata gắn đúng nếu thuộc AST contract |
| Visitor tests | Duyệt cây và xử lý node đúng |
| Transformation tests | Rewrite tạo cây hợp lệ |
| Serialization tests | AST được serialize/deserialize đúng |
| Property tests | Invariant đúng trên nhiều input |
| Fuzz tests | Parser/AST builder chịu được input bất thường |

Nên xác định ranh giới rõ: parser/AST tests không cần kiểm tra toàn bộ code generation nếu mục tiêu là xác nhận cây. Tuy nhiên, một số integration tests có thể xác nhận AST được downstream consumer hiểu đúng.

## 4. Thiết kế fixture đầu vào

Fixture là source text nhỏ, tập trung vào một cấu trúc cụ thể. Fixture tốt giúp lỗi dễ đọc và ít phụ thuộc.

Ví dụ:

~~~text
let answer = 42
~~~

Fixture này có thể kiểm tra:

- Root node là Module hoặc Program.
- Có đúng một VariableDeclaration.
- Tên biến là answer.
- Initializer là IntegerLiteral.
- Giá trị literal là 42.
- Source span bao phủ đúng phần khai báo.

### 4.1. Fixture tối thiểu

Mỗi fixture nên kiểm tra một khái niệm chính khi có thể. Ví dụ riêng cho function declaration, call expression, if statement và array literal giúp xác định test fail ở cấu trúc nào.

### 4.2. Fixture tổng hợp

Ngoài fixture nhỏ, cần một số chương trình nhiều thành phần để kiểm tra quan hệ giữa declarations, scope nesting, expression lồng nhau và thứ tự statements.

### 4.3. Valid và invalid inputs

AST tests chủ yếu kiểm tra cây từ input hợp lệ. Với input không hợp lệ, có thể kiểm tra error-recovery AST hoặc partial tree nếu parser có cam kết hỗ trợ. Không nên giả định mọi parser đều tạo AST đầy đủ sau syntax error.

### 4.4. Fixture naming

Tên fixture nên mô tả đặc điểm, ví dụ precedence-multiplication-before-addition.dsl hoặc nested-blocks.dsl. Tên test nên nói rõ invariant cần bảo vệ.

## 5. Kiểm tra root và node types

Bước đầu tiên là xác nhận root node và các node con có đúng loại.

Ví dụ AST model:

~~~text
Program
└── declarations: Declaration[]
    ├── VariableDeclaration
    ├── FunctionDeclaration
    └── TypeDeclaration
~~~

Test cần kiểm tra root có đúng loại, số lượng declaration và node type tại từng vị trí.

### 5.1. Root node

Một file DSL thường tạo Program, Module, Document hoặc CompilationUnit. Cần xác nhận root không null và mang đúng module identity nếu grammar có module declaration.

### 5.2. Node count

Kiểm tra số lượng node có thể phát hiện declaration bị mất hoặc tạo trùng. Tuy nhiên, count đơn thuần không đủ vì hai cây khác cấu trúc vẫn có thể cùng số node.

### 5.3. Node type assertions

Nên assert loại node cụ thể ở các vị trí quan trọng thay vì chỉ so sánh tên class bằng string nếu framework cung cấp type-safe API.

### 5.4. Unknown node types

Khi grammar được mở rộng, test visitor và transformer nên phát hiện node type mới chưa được xử lý. Có thể dùng exhaustive pattern matching hoặc default branch báo lỗi trong test.

## 6. Kiểm tra parent-child relationships

AST là cây có quan hệ sở hữu. Mỗi node con cần thuộc đúng parent, và cấu trúc không được có chu trình nếu mô hình định nghĩa là tree.

Ví dụ:

~~~text
IfStatement
├── condition: BinaryExpression
├── thenBranch: Block
└── elseBranch: Block
~~~

Test có thể kiểm tra:

- Condition là child của IfStatement.
- Then branch và else branch không bị hoán đổi.
- Statements bên trong block thuộc đúng block.
- Node không xuất hiện nhầm ở hai vị trí nếu containment yêu cầu một parent duy nhất.
- Parent pointer, nếu có, trỏ ngược về node cha.

### 6.1. Parent pointer

Một số AST chỉ lưu cạnh parent-to-child; một số lưu thêm parent pointer. Nếu có parent pointer, test phải kiểm tra hai chiều nhất quán.

### 6.2. Shared nodes

Một số representation dùng DAG thay vì tree và cho phép node dùng chung. Khi đó, test cần xác nhận semantics của sharing thay vì mặc định một node chỉ có một parent.

### 6.3. Cycle detection

AST tree không nên có cycle. Một lỗi trong transformer có thể vô tình gắn ancestor làm child. Test invariant hoặc traversal có visited set có thể phát hiện vòng lặp.

## 7. Kiểm thử precedence và associativity

Expression parsing là nơi AST tests đặc biệt quan trọng. Grammar cần phản ánh precedence và associativity đúng.

Ví dụ:

~~~text
a + b * c
~~~

Cây mong đợi:

~~~text
Add
├── a
└── Multiply
    ├── b
    └── c
~~~

### 7.1. Precedence

Toán tử có precedence cao hơn thường được nhóm trước. Test nên bao phủ nhiều cặp operator, ví dụ multiplication/addition, comparison/logical AND và logical AND/OR.

### 7.2. Left associativity

Với phép trừ thường có left associativity:

~~~text
a - b - c
~~~

Cây mong đợi:

~~~text
Subtract
├── Subtract
│   ├── a
│   └── b
└── c
~~~

Nó tương đương (a - b) - c, không phải a - (b - c).

### 7.3. Right associativity

Assignment hoặc exponentiation có thể right-associative tùy DSL:

~~~text
a = b = c
~~~

Nếu assignment right-associative, cây mong đợi là Assign(a, Assign(b,c)).

### 7.4. Parentheses

Ngoặc có thể thay đổi grouping:

~~~text
(a + b) * c
~~~

AST cần thể hiện Add là operand trái của Multiply. Nếu AST loại bỏ ParenthesizedExpression, grouping vẫn phải được bảo toàn.

### 7.5. Unary và binary operators

-a * b cần phân biệt unary minus với binary subtraction. Test nên kiểm tra node type và quan hệ operand.

### 7.6. Chaining

Các biểu thức như a.b(c).d cần kiểm tra chuỗi member access và call được lồng đúng thứ tự.

## 8. Literal và identifier

Literal là các giá trị viết trực tiếp trong source; identifier là tên tham chiếu đến symbol hoặc declaration.

Các literal thường gặp:

- Integer và decimal.
- String.
- Boolean.
- Null.
- Date/time.
- Duration.
- Array/object literal.
- Enum literal hoặc domain-specific literal.

### 8.1. Numeric literals

Test cần kiểm tra giá trị, radix, dấu, separator, precision và overflow behavior theo contract. Ví dụ 1_000 có thể parse thành số 1000 nếu grammar cho phép separator.

### 8.2. String literals

Kiểm tra escape sequence, Unicode, multiline string, raw string và quote style nếu semantics có phân biệt. Giá trị AST thường là decoded string, không phải toàn bộ token source.

### 8.3. Boolean và null

Xác nhận true, false và null tạo đúng literal node và không bị parse thành identifier.

### 8.4. Identifier

Kiểm tra tên, case sensitivity, Unicode identifier rules và qualified name segments. Không nên dùng test chỉ so sánh source text nếu AST lưu normalized name.

### 8.5. Qualified names

Ví dụ sales.Order.total có thể tạo QualifiedName với ba segment hoặc chuỗi đã chuẩn hóa. Test cần phản ánh representation được chọn và bảo đảm thứ tự segment không đổi.

## 9. Declarations và statements

AST cần phân biệt declaration tạo symbol với statement điều khiển hoặc thực hiện hành động.

Ví dụ:

~~~text
module sales

type Money
let taxRate = 0.1

function total(price: Money, quantity: Integer) {
    return price * quantity
}
~~~

Test có thể kiểm tra:

- Module declaration.
- Type declaration.
- Variable declaration.
- Function declaration.
- Parameter list.
- Return statement.
- Body block và statement ordering.

### 9.1. Declaration order

Nếu DSL giữ thứ tự source, danh sách declaration phải có cùng thứ tự. Nếu compiler chuẩn hóa thứ tự, cần kiểm tra contract chuẩn hóa đó.

### 9.2. Optional sections

Một declaration có thể có annotation, generic parameters, modifiers hoặc body tùy chọn. Test cần bao phủ trường hợp có và không có từng phần.

### 9.3. Nested declarations

Một số DSL cho phép type hoặc function lồng trong namespace/module. Test phải xác nhận containment và qualified name được tạo đúng.

### 9.4. Statement sequence

Trong block, thứ tự statements có ý nghĩa. AST không được chuyển hoặc bỏ statement khi parse.

## 10. Kiểm thử type syntax và generic nodes

DSL có thể có type annotation, generic type, union, optional type hoặc function type.

Ví dụ:

~~~text
let orders: List<Order>
let result: Money | Error
let callback: (Order) -> Boolean
~~~

Test cần xác nhận:

- Type reference được tạo đúng node.
- Generic arguments giữ đúng thứ tự.
- Union type có đủ member.
- Optional type được biểu diễn đúng.
- Function type giữ parameter và return type.
- Nested generic không bị tách sai dấu phân cách.

### 10.1. Type syntax và resolved type

AST có thể giữ TypeReference node; semantic analyzer sau đó mới resolve thành TypeSymbol. Test AST không nên nhầm hai tầng này nếu chúng được tách riêng.

### 10.2. Generic parameters

Kiểm tra tên parameter, constraints, default type và thứ tự. Với nested generics, cần test độ sâu và grouping.

### 10.3. Optional và nullable

Cần phân biệt type optional với giá trị null nếu DSL có hai khái niệm riêng. AST phải giữ đúng marker hoặc node tương ứng.

## 11. Source spans và source mapping

Source location giúp compiler gắn diagnostic, editor highlight và refactoring vào đúng đoạn văn bản.

Một node có thể lưu:

- Start offset.
- End offset.
- Start line/column.
- End line/column.
- Token hoặc source slice.
- URI/resource identity.

### 11.1. Range inclusive/exclusive

Cần xác định end offset là inclusive hay exclusive. Hầu hết editor protocol dùng end-exclusive range; test phải phản ánh quy ước cụ thể để tránh lệch ký tự.

### 11.2. Whitespace và comments

Node range có thể chỉ bao phủ token hoặc bao phủ toàn construct. Comment có thể nằm trong trivia riêng. Test nên xác nhận range theo contract, không suy đoán.

### 11.3. Unicode

UTF-8 byte offset, UTF-16 code unit và Unicode code point có thể khác nhau. Fixture có ký tự ngoài ASCII hoặc emoji giúp kiểm tra chuyển đổi offset.

### 11.4. Multiline constructs

String nhiều dòng, block và expression xuống dòng cần có line/column chính xác. Test nên kiểm tra cả start và end.

### 11.5. Generated nodes

Node được tạo bởi desugaring có thể không có source span trực tiếp. Có thể giữ origin mapping về source construct. Test cần xác nhận generated node có thể truy ngược về vị trí nguồn khi tooling yêu cầu.

## 12. Error recovery và partial AST

Editor thường parse khi người dùng đang gõ, nên source có thể chưa hoàn chỉnh. Một số parser tạo partial AST và error nodes thay vì từ chối toàn bộ file.

Ví dụ:

~~~text
function calculate(price: Money {
    return price +
}
~~~

### 12.1. Error nodes

Nếu model có ErrorNode hoặc MissingToken node, test cần kiểm tra vị trí và loại lỗi được tạo. Error node nên chứa đủ thông tin để diagnostic và editor hoạt động.

### 12.2. Partial declarations

Parser có thể tạo FunctionDeclaration dù thiếu dấu ngoặc hoặc body chưa hoàn chỉnh. Các field chưa có cần được biểu diễn nhất quán, ví dụ null, empty list hoặc missing-node marker.

### 12.3. Không crash khi AST không hoàn chỉnh

Visitor, validator và content assist có thể được gọi trên partial AST. Unit tests nên xác nhận chúng xử lý trạng thái thiếu dữ liệu mà không ném exception ngoài dự kiến.

### 12.4. Error recovery không được làm hỏng node lân cận

Một lỗi trong declaration không nên khiến parser mất toàn bộ các declaration sau nếu grammar có recovery strategy. Test nên đặt lỗi giữa hai cấu trúc hợp lệ rồi kiểm tra node sau vẫn được tạo.

## 13. Syntax sugar và desugaring

Syntax sugar là cú pháp tiện dụng được chuyển thành một dạng core representation đơn giản hơn.

Ví dụ DSL cho phép:

~~~text
x += 1
~~~

Desugaring có thể tạo:

~~~text
x = x + 1
~~~

### 13.1. Kiểm tra trước và sau desugaring

Có thể test AST thô từ parser và AST sau normalization riêng biệt. Mỗi bước có contract khác nhau.

### 13.2. Semantics phải được bảo toàn

Desugaring không được thay đổi thứ tự đánh giá hoặc số lần đánh giá expression. Ví dụ nếu target có side effect, rewrite cần tránh evaluate hai lần.

### 13.3. Source origin

Node mới tạo nên giữ origin mapping để diagnostics trên core node có thể hiển thị vị trí syntax sugar ban đầu.

### 13.4. Idempotence

Một số normalization pass nên idempotent: chạy lại không tiếp tục thay đổi cây. Có thể kiểm tra bằng cách serialize hoặc structural compare sau một và hai lần chạy.

## 14. AST visitors và tree traversal

Visitor là cách phổ biến để duyệt AST theo node type.

Ví dụ interface khái niệm:

~~~java
interface AstVisitor<R> {
    R visitProgram(Program node);
    R visitFunction(FunctionDeclaration node);
    R visitBinary(BinaryExpression node);
    R visitLiteral(LiteralExpression node);
}
~~~

### 14.1. Visitor coverage

Khi thêm node type mới, visitor cần có cách xử lý rõ. Test có thể tạo một fixture chứa mọi node type hoặc dùng exhaustive visitor để phát hiện trường hợp chưa được xử lý.

### 14.2. Traversal order

Pre-order, post-order và in-order có ý nghĩa khác nhau. Test cần xác nhận traversal thực hiện theo contract, đặc biệt khi consumer dựa vào thứ tự để tạo output.

### 14.3. Short-circuit traversal

Một visitor có thể dừng khi tìm thấy node phù hợp. Test nên xác nhận callback không được gọi tiếp sau khi visitor yêu cầu stop.

### 14.4. Null/optional children

Visitor cần xử lý optional body, else branch hoặc initializer bị thiếu. Test partial AST giúp bảo đảm traversal không dereference null.

### 14.5. Parent traversal

Nếu visitor có thể đi lên parent, cần tránh vòng lặp vô hạn khi cấu trúc có shared nodes hoặc parent pointer.

## 15. AST transformations

Compiler có thể biến đổi AST qua nhiều pass: desugaring, constant folding, normalization, lowering hoặc instrumentation.

Ví dụ constant folding:

~~~text
2 * (3 + 4)
~~~

Có thể được biến đổi thành:

~~~text
14
~~~

### 15.1. Structural assertions

Sau transformation, test kiểm tra node type, value, child count và invariant. Không chỉ kiểm tra output text vì serializer có thể che lỗi cấu trúc.

### 15.2. Preserve source mapping

Transformation nên giữ source origin cho node được thay thế. Diagnostic sau optimization vẫn cần trỏ về source DSL.

### 15.3. Preserve semantics

Test có thể so sánh evaluation của AST trước và sau transformation trên input mẫu. Với expression thuần, kết quả phải tương đương.

### 15.4. Transformation ordering

Các pass có thể phụ thuộc nhau. Ví dụ desugaring cần chạy trước type lowering. Integration tests cần xác nhận pipeline pass theo đúng thứ tự.

### 15.5. Immutable và mutable AST

Nếu AST immutable, transformation thường tạo cây mới; nếu mutable, cần kiểm tra mutation không làm hỏng node dùng chung. Test cần tuân theo ownership model đã chọn.

## 16. Snapshot/golden tests

Snapshot test serialize AST thành dạng dễ đọc rồi so sánh với expected file.

Ví dụ snapshot:

~~~text
Program
  VariableDeclaration
    name: answer
    initializer:
      IntegerLiteral
        value: 42
~~~

### 16.1. Ưu điểm

- Dễ xem toàn bộ cây.
- Diff cho biết cấu trúc thay đổi.
- Hữu ích khi grammar hoặc AST model được refactor.
- Có thể lưu nhiều fixture mà không cần viết assertion dài.

### 16.2. Hạn chế

- Snapshot có thể thay đổi do formatting hoặc node metadata không quan trọng.
- Expected output dài khó review.
- Test có thể chấp nhận thay đổi sai nếu snapshot được cập nhật máy móc.
- Khó biểu đạt invariant tổng quát chỉ bằng so sánh text.

### 16.3. Chuẩn hóa snapshot

Nên bỏ dữ liệu không ổn định như absolute path, random ID hoặc timestamp nếu chúng không thuộc contract. Giữ source range khi đó là điều cần kiểm tra.

### 16.4. Review snapshot changes

Khi cập nhật snapshot, reviewer cần hiểu vì sao cây thay đổi: grammar mới, semantics mới hay regression. Không nên tự động accept mọi snapshot diff.

## 17. Structural assertions

Structural assertions kiểm tra từng phần của AST bằng API type-safe.

Ví dụ pseudocode:

~~~java
Program program = parser.parse("let answer = 42");

assertThat(program.declarations()).hasSize(1);

VariableDeclaration declaration =
    (VariableDeclaration) program.declarations().get(0);

assertThat(declaration.name()).isEqualTo("answer");
assertThat(declaration.initializer())
    .isInstanceOf(IntegerLiteral.class);

IntegerLiteral literal =
    (IntegerLiteral) declaration.initializer();

assertThat(literal.value()).isEqualTo(42);
~~~

### 17.1. Assert node type trước khi cast

Test nên assert type trước khi cast để lỗi có thông báo dễ hiểu. Nếu language hoặc test framework hỗ trợ typed accessors, ưu tiên chúng.

### 17.2. Assert child order

Dùng list assertion để xác nhận statement/declaration order. Không chuyển danh sách thành set nếu thứ tự có ý nghĩa.

### 17.3. Assert absence

Kiểm tra node không tồn tại cũng quan trọng, ví dụ punctuation token không được tạo thành semantic node hoặc một declaration không bị nhân đôi.

### 17.4. Assert source range

So sánh offset/range với vị trí dự kiến từ fixture. Nên tạo helper để chuyển line/column và test encoding nhất quán.

## 18. Property-based testing cho AST

Property-based testing sinh nhiều input theo generator rồi kiểm tra invariant thay vì chỉ dùng một vài fixture cố định.

Các property hữu ích:

- Mọi node con có loại phù hợp với grammar.
- Tree không có cycle nếu model yêu cầu tree.
- Serialize rồi parse lại giữ cấu trúc theo semantics được hỗ trợ.
- Mọi source range nằm trong giới hạn source.
- Declaration list giữ thứ tự source nếu contract yêu cầu.
- Visitor có thể duyệt toàn cây mà không crash.
- Desugaring giữ kết quả đánh giá cho expression thuần.
- Node ID không trùng trong phạm vi cần duy nhất.

### 18.1. AST generators

Có thể sinh AST hợp lệ trước rồi serialize thành DSL source. Parse lại source và so sánh cấu trúc. Cách này giúp kiểm tra parser trên nhiều dạng lồng nhau.

### 18.2. Bounded depth

Generator cần giới hạn độ sâu expression/block để tránh tạo input quá lớn và test quá chậm. Có thể tăng depth theo một số mức để kiểm tra recursion.

### 18.3. Shrinking

Khi property fail, shrinking tìm input nhỏ hơn vẫn tái hiện lỗi. Một expression 200 node có thể được rút về a + b * c, giúp hiểu lỗi precedence.

### 18.4. Deterministic seeds

Ghi seed khi test fail để có thể tái hiện. CI nên lưu seed và minimized input trong failure artifact.

## 19. Fuzz testing parser và AST builder

Fuzz testing đưa input ngẫu nhiên hoặc biến đổi vào parser để tìm crash, hang, stack overflow và lỗi memory.

Các kỹ thuật:

- Mutation-based fuzzing: thay token, xóa dấu ngoặc, chèn ký tự.
- Grammar-based fuzzing: sinh source theo grammar rồi biến đổi nhẹ.
- Coverage-guided fuzzing: ưu tiên input đi qua code path mới.
- Differential fuzzing: so sánh parser hoặc implementation khác nhau nếu có.

### 19.1. Fuzz invalid inputs

Input sai cú pháp vẫn cần được xử lý an toàn. Parser không nên crash hoặc treo vô hạn khi gặp chuỗi dấu ngoặc, token lạ hoặc nesting sâu.

### 19.2. Fuzz Unicode

Kiểm tra ký tự combining, surrogate pairs, ký tự không hợp lệ theo encoding và identifier Unicode nếu DSL hỗ trợ.

### 19.3. Resource limits

Giới hạn input size, nesting depth và thời gian parse. Fuzz test có thể phát hiện denial-of-service do recursion hoặc backtracking quá mức.

### 19.4. Regression corpus

Mọi input từng làm parser crash nên được lưu thành regression fixture sau khi sửa lỗi.

## 20. Round-trip và serialization tests

Một số DSL cần chuyển AST thành source và parse lại.

~~~text
source
  -> parse
  -> AST
  -> serialize
  -> source2
  -> parse
  -> AST2
~~~

### 20.1. Structural round-trip

Nếu serializer chuẩn hóa format, source2 không cần giống byte-for-byte source ban đầu. Điều quan trọng là AST2 tương đương AST theo semantics được hỗ trợ.

### 20.2. Comment preservation

Nếu serializer phải giữ comment, test cần xác nhận comment và vị trí tương đối không bị mất. Nếu AST không giữ comment, cần test node/trivia model riêng.

### 20.3. Canonical formatting

Nếu serializer tạo canonical form, có thể kiểm tra serialize lần thứ hai không thay đổi output. Đây là idempotence của formatting.

### 20.4. Unsupported constructs

Nếu AST có node không thể serialize, serializer cần báo lỗi rõ thay vì tạo source sai hoặc bỏ node âm thầm.

## 21. AST và semantic analysis

Semantic analyzer thường duyệt AST để resolve symbol, kiểm tra type và phát diagnostic. Một số test có thể xác nhận AST cung cấp đủ thông tin cho các bước này.

Ví dụ:

~~~text
let price: Money = 100
~~~

AST có thể đúng về cú pháp nhưng type checker phát hiện literal số không tương thích với Money nếu DSL không có implicit conversion.

### 21.1. Giữ ranh giới test

AST test xác nhận node và field được parse đúng. Semantic test xác nhận tên resolve, kiểu hợp lệ và rule miền. Nên tách để biết lỗi nằm ở parser hay analyzer.

### 21.2. AST annotations

Nếu semantic pass gắn symbol hoặc type metadata lên node, cần test lifecycle: metadata được tạo, invalidated và cập nhật khi source thay đổi.

### 21.3. Unresolved references

AST vẫn có thể chứa Reference node chưa resolve. Không nên coi unresolved symbol là parser failure nếu linking được thực hiện ở pass sau.

### 21.4. Error-tolerant analysis

Editor có thể chạy semantic analysis trên partial AST. Test cần xác nhận analyzer bỏ qua hoặc báo lỗi phù hợp khi node thiếu child.

## 22. Incremental parsing và AST updates

IDE thường không parse toàn bộ project từ đầu sau mỗi ký tự. Incremental parser có thể cập nhật một phần AST khi document thay đổi.

### 22.1. Document versions

AST cần gắn với version của source snapshot. Diagnostic hoặc semantic result từ version cũ không nên được áp dụng nhầm vào version mới.

### 22.2. Node identity

Một số editor cần giữ identity của node không thay đổi để duy trì selection, outline hoặc cache. Incremental parser có thể reuse node; test cần xác nhận quy tắc reuse nếu đó là contract.

### 22.3. Edit locality

Một thay đổi trong function A không nên làm mất node identity hoặc metadata của function B nếu implementation hứa hỗ trợ reuse. Có thể kiểm tra bằng fixture nhiều declaration.

### 22.4. Invalidation

Thay đổi một declaration có thể ảnh hưởng symbol references ở nhiều file. AST update và semantic cache invalidation là hai lớp khác nhau; test cần phân biệt parser update với downstream reanalysis.

### 22.5. Concurrent edits

Nếu parse task cũ hoàn thành sau task mới, kết quả cũ không được ghi đè AST mới. Test có thể dùng controlled executor để mô phỏng completion order.

## 23. Kiểm thử AST trong framework và DSL model

Framework như Xtext có thể tạo EMF model từ grammar. AST tests khi đó kiểm tra EObject, containment references, attributes và cross-reference nodes theo model contract.

Ví dụ model khái niệm:

~~~text
Workflow
├── name: EString
└── steps: Step[*]

CallStep
├── operation: Operation [cross-reference]
└── arguments: Expression[*]
~~~

### 23.1. Containment

Kiểm tra child object nằm trong containment feature đúng và container pointer nhất quán.

### 23.2. Cross-reference

Parser có thể tạo proxy hoặc reference node trước khi linking. AST/model test cần phân biệt parse structure với resolved EObject.

### 23.3. EMF resource

Nếu DSL dùng Resource, test nên kiểm tra URI, resource contents, diagnostics và resource set khi có import nhiều file.

### 23.4. Generated model code

Không sửa generated model để làm test pass. Test phải dùng metamodel/generated classes được sinh từ grammar hoặc Ecore source.

## 24. Test organization và test helpers

Một bộ AST test tốt nên có cấu trúc rõ ràng và helper dùng lại.

Ví dụ thư mục:

~~~text
src/test/
├── parser/
│   ├── declarations/
│   ├── expressions/
│   ├── statements/
│   └── error-recovery/
├── ast/
│   ├── structure/
│   ├── source-ranges/
│   ├── visitors/
│   └── transformations/
├── fixtures/
│   ├── valid/
│   └── invalid/
└── support/
    ├── AstAssertions
    ├── AstSnapshot
    └── SourcePositionHelper
~~~

### 24.1. Parse helper

Helper có thể parse source và trả AST root, đồng thời báo diagnostic nếu input không hợp lệ. Khi test invalid input, helper nên cho phép kiểm tra partial result.

### 24.2. AST assertion library

Có thể tạo assertion như hasNodeType, hasName, hasChildAt, hasRange hoặc matchesSnapshot. Helper nên tạo failure message mô tả path của node trong cây.

### 24.3. Path notation

Đường dẫn như Program.declarations[0].body.statements[1] giúp xác định node fail mà không phải in toàn bộ AST.

### 24.4. Fixture utilities

Nếu fixture dùng file, helper nên chuẩn hóa encoding và line endings. Không phụ thuộc current working directory hoặc absolute path của máy developer.

### 24.5. Test isolation

Parser state, symbol cache và global registry không nên rò giữa tests. Mỗi test cần resource context riêng hoặc reset state theo contract.

## 25. Ví dụ tổng hợp: kiểm thử AST của biểu thức

Source:

~~~text
let result = a + b * (c - 2)
~~~

Test có thể xác nhận:

1. Root là Program.
2. Có một VariableDeclaration tên result.
3. Initializer là AddExpression.
4. Operand trái của Add là Identifier a.
5. Operand phải là MultiplyExpression.
6. Operand trái của Multiply là Identifier b.
7. Operand phải là SubtractExpression.
8. Operand trái của Subtract là Identifier c.
9. Operand phải là IntegerLiteral có giá trị 2.
10. Source ranges của các node lồng nhau nằm trong source và bao phủ đúng token/construct theo contract.

Snapshot minh họa:

~~~text
Program
└── VariableDeclaration(name="result")
    └── Add
        ├── Identifier("a")
        └── Multiply
            ├── Identifier("b")
            └── Subtract
                ├── Identifier("c")
                └── IntegerLiteral(2)
~~~

## 26. Ví dụ tổng hợp: test bằng Java

Đoạn pseudocode sau minh họa cách kiểm tra cấu trúc AST. API thật phụ thuộc parser và assertion framework của dự án.

~~~java
@Test
void multiplicationBindsMoreTightlyThanAddition() {
    Program program = parser.parse(
        "let result = a + b * c"
    );

    assertThat(program.declarations()).hasSize(1);

    VariableDeclaration declaration =
        (VariableDeclaration) program.declarations().get(0);

    assertThat(declaration.name()).isEqualTo("result");

    BinaryExpression add =
        (BinaryExpression) declaration.initializer();

    assertThat(add.operator()).isEqualTo(Operator.ADD);
    assertThat(add.left()).isInstanceOf(Identifier.class);

    BinaryExpression multiply =
        (BinaryExpression) add.right();

    assertThat(multiply.operator()).isEqualTo(Operator.MULTIPLY);
    assertThat(((Identifier) multiply.left()).name()).isEqualTo("b");
    assertThat(((Identifier) multiply.right()).name()).isEqualTo("c");
}
~~~

Điểm quan trọng là test khẳng định cấu trúc grouping chứ không chỉ khẳng định parser không báo lỗi.

## 27. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra parse không lỗi | AST sai cấu trúc vẫn qua test | Assert node types và relationships |
| Chỉ dùng snapshot | Diff khó hiểu hoặc chấp nhận thay đổi sai | Kết hợp structural assertions |
| Không test precedence | Expression được nhóm sai | Fixture cho từng precedence pair |
| Không test associativity | AST sai với operator chain | Test left/right associativity |
| Bỏ qua source ranges | Diagnostics và editor highlight lệch | Test offsets, line/column và Unicode |
| Không test partial AST | IDE crash khi người dùng đang gõ | Test error recovery và missing nodes |
| Dùng fixture quá lớn | Khó xác định nguyên nhân fail | Fixture nhỏ cộng một số integration cases |
| Không kiểm tra parent-child | Node bị gắn nhầm hoặc trùng | Kiểm tra containment và parent pointer |
| Không test transformation | Desugaring làm đổi semantics | Structural và equivalence tests |
| Không lưu fuzz regression | Lỗi parser cũ tái xuất hiện | Thêm minimized input vào corpus |
| Dùng absolute paths trong snapshot | Test phụ thuộc máy | Normalize URI/path |
| Chia sẻ parser state giữa tests | Kết quả phụ thuộc thứ tự chạy | Cô lập resource và reset cache |
| Bỏ qua Unicode | Range sai với text thực tế | Thêm fixture Unicode và encoding tests |

## 28. Nguyên tắc thiết kế kiểm thử AST

Khi xây dựng test suite cho AST, có thể áp dụng các nguyên tắc sau:

1. **Xác định AST contract.** Ghi rõ root, node types, fields, containment và source mapping.
2. **Kiểm tra cấu trúc cụ thể.** Assert node type, operand, child order và parent relation.
3. **Bao phủ precedence và associativity.** Đặc biệt với biểu thức có nhiều toán tử.
4. **Test literal và identifier.** Kiểm tra giá trị đã decode, format và qualified name.
5. **Kiểm tra source spans.** Bao gồm Unicode, multiline và end-exclusive/inclusive convention.
6. **Tách parser khỏi semantic analysis.** Biết test đang xác nhận cú pháp hay name/type resolution.
7. **Test error recovery.** AST partial phải an toàn cho editor và tooling nếu framework hỗ trợ.
8. **Kết hợp snapshot và assertions.** Snapshot cho khả năng quan sát; assertions cho invariant chính xác.
9. **Dùng property-based và fuzz testing.** Tìm input lồng sâu và trường hợp biên ngoài fixture viết tay.
10. **Kiểm tra transformation.** Bảo toàn semantics và source origin.
11. **Test incremental behavior.** Kiểm tra version, reuse và invalidation nếu IDE phụ thuộc vào chúng.
12. **Cô lập test state.** Tránh cache hoặc resource dùng chung làm test không xác định.
13. **Lưu regression fixtures.** Mọi bug AST đã sửa nên có test tái hiện.
14. **Giữ test dễ đọc.** Failure message nên chỉ rõ path và expected/actual node.

## 29. Kết luận

Kiểm thử AST xác nhận rằng văn bản DSL được chuyển thành cây cú pháp đúng với grammar và semantics cấu trúc đã định. Một bộ test đáng tin cần kiểm tra root, node type, parent-child relationships, thứ tự, precedence, associativity, literal, identifier và source ranges. Với editor và compiler hiện đại, còn cần kiểm tra partial AST, visitor, transformation, serialization và incremental updates.

Structural assertions giúp kiểm tra chính xác từng node; snapshot giúp quan sát toàn cây; property-based và fuzz tests mở rộng phạm vi input; regression fixtures giữ lại các lỗi đã phát hiện. Tách AST tests khỏi semantic tests giúp xác định lỗi ở đúng tầng, trong khi integration tests xác nhận các bước downstream có thể sử dụng cây như mong đợi.

Khi AST contract được kiểm thử có hệ thống, thay đổi grammar hoặc parser ít có nguy cơ làm sai cấu trúc âm thầm. Điều đó tạo nền tảng vững chắc cho name resolution, type checking, refactoring, code generation và trải nghiệm editor của DSL.
