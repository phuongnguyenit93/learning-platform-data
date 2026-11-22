# Tốc độ phân tích

Trong một hệ thống sử dụng ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), bước phân tích cú pháp (parsing) chuyển văn bản nguồn thành cấu trúc mà compiler, validator hoặc runtime có thể hiểu. Một DSL có thể được dùng để khai báo rule, workflow, schema, truy vấn, cấu hình hoặc biểu thức. Khi số lượng definition tăng, file lớn hơn hoặc ứng dụng cần xử lý DSL liên tục, tốc độ phân tích ảnh hưởng trực tiếp đến thời gian build, startup, deploy và phản hồi của công cụ phát triển.

**Tốc độ phân tích** (*parsing speed*) là hiệu năng mà parser chuyển input thành cấu trúc cú pháp hoặc model trung gian trong một khoảng thời gian và với mức sử dụng tài nguyên xác định. Nó thường được đo bằng thời gian xử lý, throughput, độ trễ theo kích thước input, allocation, peak memory và khả năng mở rộng khi phân tích nhiều file hoặc nhiều request đồng thời.

Tốc độ parsing không chỉ phụ thuộc thuật toán parser. Nó còn phụ thuộc tokenizer/lexer, thiết kế grammar, kích thước token, lookahead, backtracking, semantic predicate, error recovery, cấu trúc AST, cách đọc file, cache, garbage collection và môi trường chạy. Một parser có độ phức tạp lý thuyết tốt vẫn có thể chậm nếu tạo quá nhiều object nhỏ, dùng regex không phù hợp hoặc liên tục resolve symbol trong lúc parse.

Ví dụ, một pipeline DSL thường có dạng:

~~~mermaid
flowchart LR
    A[Source text] --> B[Lexing]
    B --> C[Tokens]
    C --> D[Parsing]
    D --> E[AST]
    E --> F[Name resolution]
    F --> G[Type and semantic checks]
    G --> H[Executable model]
~~~

Mỗi bước có chi phí riêng. Nếu đo toàn bộ pipeline rồi gọi kết quả là parse time, ta có thể tối ưu nhầm thành phần. Cần tách thời gian đọc source, lexing, parsing, AST construction và semantic analysis để biết chính xác bottleneck.

## 1. Parsing là gì và đo tốc độ parsing như thế nào?

Parsing là quá trình xác định cấu trúc cú pháp của input theo grammar. Parser thường nhận token stream từ lexer và tạo parse tree, abstract syntax tree (AST) hoặc một model tương đương.

Ví dụ DSL:

~~~text
rule EligibleCustomer {
    when customer.age >= 18 and customer.active;
    then approve(customer.id);
}
~~~

Parser xác định rule mở một rule declaration, when chứa biểu thức điều kiện, and nối hai predicate và then chứa action call. Nó cần hiểu precedence, grouping, identifier, literal và ranh giới statement.

### Các đại lượng hiệu năng

| Đại lượng | Ý nghĩa | Cách dùng |
|---|---|---|
| Parse latency | Thời gian phân tích một input. | Đánh giá phản hồi cho một file/request. |
| Throughput | Số byte, token hoặc file xử lý mỗi giây. | Đánh giá batch và build pipeline. |
| CPU time | Thời gian CPU thực sự dùng cho parsing. | Phân biệt tính toán với I/O hoặc chờ. |
| Allocation rate | Lượng object/byte được cấp phát mỗi giây. | Phát hiện AST/token allocation quá lớn. |
| Peak heap | Bộ nhớ heap cao nhất trong lúc parse. | Đánh giá file lớn và khả năng chạy đồng thời. |
| GC pause | Thời gian dừng do garbage collection. | Phát hiện allocation gây gián đoạn. |
| Error-path latency | Thời gian parse input sai cú pháp. | Đánh giá editor và developer feedback. |
| Incremental latency | Thời gian cập nhật parse result sau một chỉnh sửa nhỏ. | Đánh giá IDE/editor. |

### Đo theo nhiều đơn vị

Có thể đo bytes/second, characters/second, tokens/second hoặc declarations/second. Các chỉ số này bổ sung cho nhau. Hai DSL có token density khác nhau nên so sánh tokens/second giữa chúng có thể gây hiểu nhầm.

### Latency percentile

Không chỉ đo trung bình. Với service parse request, p50, p95 và p99 cho biết trải nghiệm ở input thông thường và input khó. Một số grammar có thể xử lý hầu hết file nhanh nhưng chậm bất thường với một pattern backtracking.

### Cold và warm parsing

Cold parse có thể bao gồm class loading, grammar initialization, JIT warm-up và cache miss. Warm parse phản ánh hiệu năng sau khi runtime đã ổn định. Cần báo cáo riêng để không trộn startup overhead với chi phí parse lặp.

## 2. Parsing khác lexing và semantic analysis

Một pipeline compiler thường có nhiều giai đoạn:

- **Source loading:** đọc file hoặc nhận text từ API.
- **Lexing/tokenization:** chuyển ký tự thành token.
- **Parsing:** xác định cấu trúc token theo grammar.
- **AST construction:** tạo node biểu diễn cú pháp trừu tượng.
- **Name resolution:** tìm symbol, type, import và reference.
- **Type checking:** kiểm tra tương thích kiểu.
- **Semantic validation:** kiểm tra invariant và quy tắc miền.
- **Lowering/compilation:** chuyển AST sang IR hoặc executable form.

Một số parser kết hợp AST construction trực tiếp; một số parser tạo concrete syntax tree trước rồi mới chuyển thành AST.

### Vì sao phải tách thời gian?

Nếu lexer chiếm 60% tổng thời gian, đổi parser algorithm có thể chỉ cải thiện rất ít. Nếu semantic resolution chiếm phần lớn, tối ưu parse tree không giải quyết bottleneck. Tách phase giúp đưa quyết định dựa trên số liệu.

### Instrumentation theo phase

Có thể ghi timestamp hoặc dùng profiler span cho từng phase. Không nên thêm logging cho từng token trong benchmark vì logging làm thay đổi chính hiệu năng đang đo.

### Parse-only benchmark

Parse-only benchmark nên dùng input đã có sẵn trong memory để loại trừ filesystem I/O. Benchmark end-to-end vẫn cần thiết để hiểu trải nghiệm thực tế, nhưng phải được báo riêng.

## 3. Những yếu tố ảnh hưởng tốc độ

Tốc độ parser thường chịu tác động bởi các yếu tố sau:

1. Kích thước input và số lượng token.
2. Độ phức tạp, ambiguity và cách viết grammar.
3. Thuật toán parser và chiến lược lookahead.
4. Backtracking, memoization và semantic predicate.
5. Cách lexer nhận diện token.
6. Cách parser tạo node, list và source span.
7. Error recovery và số lượng diagnostic.
8. Name resolution hoặc semantic work bị thực hiện sớm trong parse.
9. Cache grammar, module và compiled artifact.
10. CPU, memory, JIT, garbage collector và mức concurrency.

### Input size không phải thước đo duy nhất

Một file 100 KB gồm nhiều declaration đơn giản có thể parse nhanh hơn file 20 KB chứa expression lồng sâu và nhiều nhánh grammar khó phân biệt. Cần benchmark theo cấu trúc input thực tế.

### Grammar shape

Các production có prefix chung, recursion sâu hoặc lựa chọn mơ hồ có thể khiến parser thử nhiều hướng. Việc tổ chức grammar thường ảnh hưởng lớn hơn một micro-optimization nhỏ trong code.

### Error input

Một input sai cú pháp ở cuối file có thể khiến parser phải đọc gần như toàn bộ input trước khi báo lỗi. Recovery có thể tạo thêm diagnostic và node lỗi. Benchmark chỉ dùng input hợp lệ sẽ bỏ sót trường hợp quan trọng trong IDE.

## 4. Độ phức tạp thuật toán parsing

Nhiều parser thông dụng có thời gian tuyến tính theo độ dài input trong điều kiện grammar và thuật toán phù hợp. Tuy nhiên, một số chiến lược backtracking có thể tạo thời gian tăng nhanh khi gặp input bất lợi.

Gọi n là số token hoặc ký tự đầu vào:

- O(n): thời gian tuyến tính.
- O(n log n): thường xuất hiện khi cần cấu trúc dữ liệu có thao tác logarithmic.
- O(n²): có thể xuất hiện với một số cách thử lại hoặc scan lặp.
- Exponential worst case: có thể xảy ra với backtracking parser không memoize trên grammar/input gây ambiguity.

Không nên chỉ nhìn Big-O. Constant factor, allocation và cache locality cũng quan trọng. Parser tuyến tính nhưng tạo hàng triệu object có thể chậm hơn parser có cấu trúc dữ liệu compact.

### Worst-case và average-case

Input thường gặp có thể không kích hoạt worst case. Cần có cả corpus thực tế và adversarial input để đánh giá tính ổn định.

### Input do người dùng kiểm soát

Nếu DSL được gửi qua API hoặc do người dùng tự viết, parser cần giới hạn kích thước, nesting depth, token count, thời gian và bộ nhớ. Một grammar có worst-case không tốt có thể trở thành điểm gây denial of service.

### Linear-time không đồng nghĩa luôn nhanh

Một parser tuyến tính vẫn có thể bị chậm do regex lexer, allocation, object traversal hoặc I/O. Big-O giúp đánh giá xu hướng tăng trưởng, còn profiling cho biết chi phí thực tế.

## 5. Lexing nhanh và hiệu quả

Lexer đọc ký tự và tạo token như identifier, keyword, number, string, operator và punctuation.

Ví dụ:

~~~text
total >= 100 and status == ACTIVE
~~~

Token stream có thể là:

| Token | Lexeme |
|---|---|
| IDENTIFIER | total |
| GREATER_EQUAL | >= |
| NUMBER | 100 |
| AND | and |
| IDENTIFIER | status |
| EQUAL_EQUAL | == |
| IDENTIFIER | ACTIVE |

### Single-pass scanning

Lexer thường đạt hiệu năng tốt khi duyệt source một lần với index tăng dần. Tránh tạo substring cho mọi token nếu chỉ cần giữ start/end offset.

### Token representation

Một token có thể chứa loại token, start offset, end offset và channel/flags. Token text được cắt từ source khi cần, thay vì copy riêng từng chuỗi.

~~~java
record Token(TokenType type, int start, int end) {}
~~~

Cách này giảm allocation, nhưng yêu cầu source buffer còn tồn tại trong thời gian token/AST cần tham chiếu.

### Keyword recognition

Identifier có thể được scan một lần rồi đối chiếu keyword table. Một hash map hoặc perfect-hash-like lookup có thể phù hợp tùy số keyword. Không nên so sánh hàng chục chuỗi tuần tự cho mỗi identifier nếu lexer nóng.

### Longest match

Khi operator có prefix chung, lexer thường áp dụng maximal munch: chọn lexeme dài nhất hợp lệ. Ví dụ >= phải được nhận diện trước > nếu cả hai đều là token. Thứ tự rule không rõ có thể tạo tokenization sai hoặc thêm backtracking.

### Whitespace và comment

Nếu grammar cho phép bỏ qua whitespace/comment, lexer có thể skip chúng nhanh nhưng vẫn cần giữ source span để diagnostic và formatter. Với formatter hoặc refactoring tool, comment/trivia có thể phải được lưu như token phụ.

### String literal

Escape sequence, Unicode escape và multiline string có thể tốn chi phí. Lexer nên scan bằng state machine thay vì tạo nhiều substring hoặc regex phức tạp. Cần giới hạn độ dài literal nếu input không tin cậy.

### Numeric literal

Number scanner phải xử lý dấu, decimal point, exponent, radix và suffix theo grammar. Tránh parse thành BigDecimal/Integer ngay ở lexer nếu parser chỉ cần token text; conversion có thể thực hiện khi build literal node hoặc semantic phase.

### Unicode

Identifier có thể cho phép Unicode. Cần quy định Unicode category, normalization và code point handling. Duyệt UTF-16 char đơn lẻ có thể tách surrogate pair; nếu grammar hỗ trợ code point ngoài BMP, scanner phải xử lý đúng.

## 6. Chọn thuật toán parser phù hợp

Không có một thuật toán tối ưu cho mọi grammar. Lựa chọn phụ thuộc grammar, khả năng ambiguity, error reporting, incremental support và công cụ sinh parser.

| Thuật toán | Đặc điểm | Ưu điểm | Lưu ý |
|---|---|---|---|
| Recursive descent | Mỗi production thường là một hàm. | Dễ đọc, dễ tùy biến. | Cần xử lý left recursion và lookahead. |
| LL(k) | Parse từ trái sang phải, tạo leftmost derivation với lookahead k. | Predictive, dễ phân tích. | Grammar phải phù hợp LL. |
| Pratt parser | Parse expression dựa trên binding power/precedence. | Rất phù hợp expression grammar. | Cần định nghĩa precedence và associativity rõ. |
| LR/LALR | Bottom-up parsing bằng state/action table. | Hỗ trợ nhiều grammar mạnh. | Table và diagnostics có thể khó tùy biến. |
| GLR | Duy trì nhiều parse path khi grammar mơ hồ. | Có thể xử lý ambiguity. | Tốn tài nguyên nếu nhiều nhánh. |
| PEG/packrat | Ordered choice, có thể memoize rule/position. | Grammar linh hoạt, tránh một số ambiguity. | Memoization có chi phí memory. |
| Parser combinators | Ghép parser nhỏ thành parser lớn. | Composition tốt, tiện cho DSL nhỏ. | Cần chú ý allocation và backtracking. |

### Recursive descent

Recursive descent thường phù hợp DSL có grammar được thiết kế rõ và cần custom diagnostics. Mỗi nonterminal tương ứng một method, nên dễ trace. Tuy nhiên, left recursion trực tiếp có thể gây gọi đệ quy vô hạn.

### LL parsing

LL parser chọn production dựa trên lookahead. Left factoring có thể giúp grammar dễ dự đoán. Nếu parser cần lookahead quá lớn hoặc nhiều semantic predicate, grammar có thể cần tổ chức lại.

### Pratt parser cho expression

Pratt parser xử lý precedence bằng binding power. Nó thường đơn giản hơn viết nhiều tầng grammar cho mọi operator.

### LR/LALR

LR parser phù hợp grammar lớn hoặc grammar cần xử lý cấu trúc phức tạp. Parser generator có thể tạo table hiệu quả và phát hiện conflict trong grammar.

### PEG và ordered choice

Trong PEG, thứ tự alternative ảnh hưởng semantics. Alternative đầu tiên thành công có thể ngăn alternative sau được thử. Grammar cần được viết có chủ đích; đổi thứ tự rule có thể đổi cách parse.

### Chọn theo yêu cầu tổng thể

Cân nhắc cả hiệu năng, khả năng bảo trì grammar, chất lượng error message, hỗ trợ editor, incremental parsing và kinh nghiệm của nhóm. Một parser nhanh nhưng grammar khó bảo trì có thể làm chi phí phát triển tăng cao.

## 7. Thiết kế grammar để tránh ambiguity và backtracking

Grammar có ảnh hưởng trực tiếp đến số lần parser phải thử lại.

### Prefix chung

Ví dụ grammar:

~~~text
Declaration
    = "let" Identifier "=" Expression
    | "let" Identifier ":" Type
~~~

Hai nhánh cùng bắt đầu bằng let Identifier. Có thể left-factor:

~~~text
Declaration
    = "let" Identifier DeclarationTail

DeclarationTail
    = "=" Expression
    | ":" Type
~~~

Parser có thể tiêu thụ prefix một lần rồi chọn nhánh theo token tiếp theo.

### Left recursion

Grammar:

~~~text
Expression = Expression "+" Term | Term
~~~

Recursive descent trực tiếp sẽ gọi Expression lặp lại trước khi tiêu thụ token. Có thể chuyển sang dạng lặp:

~~~text
Expression = Term ("+" Term)*
~~~

Sau đó AST builder tạo phép cộng trái kết hợp nếu semantics yêu cầu.

### Ambiguous grammar

Một biểu thức như a - b - c cần associativity rõ. Nếu không, parser có thể tạo nhiều tree hoặc grammar không xác định kết quả duy nhất.

### Dangling else

Cấu trúc nested if có thể gây ambiguity về else thuộc if nào. Grammar hoặc language rule cần quy định binding rõ, thường là else ghép với if gần nhất chưa có else.

### Precedence table

Expression grammar nên có bảng precedence và associativity:

| Mức | Operator | Associativity |
|---:|---|---|
| Cao | *, /, % | Left |
| Trung bình | +, - | Left |
| So sánh | <, <=, >, >= | Thường non-associative |
| Equality | ==, != | Thường non-associative |
| AND | and | Left |
| OR | or | Left |
| Thấp | ?: | Thường right |

Bảng là ví dụ; DSL phải định nghĩa semantics riêng.

### Semantic predicate

Predicate cho phép parser chọn nhánh dựa trên semantic state. Nó có thể hữu ích nhưng làm parse phụ thuộc symbol table hoặc context, giảm khả năng cache/incremental và có thể tăng chi phí. Chỉ dùng khi grammar thuần cú pháp không đủ.

## 8. Tối ưu expression parser bằng Pratt parsing

Expression thường là phần xuất hiện nhiều và có nhiều operator. Pratt parser là lựa chọn phổ biến để giữ code ngắn và hiệu quả.

Ý tưởng là parser đọc prefix expression, sau đó tiếp tục tiêu thụ infix/postfix operator khi binding power của operator đủ lớn.

~~~java
Expr parseExpression(int minBindingPower) {
    Token first = consume();
    Expr left = parsePrefix(first);

    while (hasInfixOperator()) {
        Operator op = peekOperator();
        BindingPower bp = bindingPower(op);

        if (bp.left() < minBindingPower) {
            break;
        }

        consume();
        Expr right = parseExpression(bp.right());
        left = new BinaryExpr(op, left, right);
    }

    return left;
}
~~~

Đây là pseudocode rút gọn; implementation cần xử lý postfix call, indexing, member access, ternary, assignment và associativity.

### Binding power

Với left-associative operator, right binding power thường lớn hơn left binding power theo quy ước implementation. Với right-associative operator, cặp binding power được chọn để phép đệ quy nhóm đúng.

### Prefix parselet

Prefix parser xử lý literal, identifier, unary operator, parenthesized expression, collection literal hoặc lambda.

### Infix parselet

Infix parser xử lý binary operator, function call, member access, index và conditional expression.

### Lợi ích hiệu năng

Pratt parser thường dùng vòng lặp cho operator chain thay vì nhiều tầng parser method. Nó cũng tránh xây grammar expression quá dài. Tuy vậy, cần benchmark với grammar và AST shape thực tế.

## 9. Tránh backtracking không cần thiết

Backtracking xảy ra khi parser thử một nhánh, thất bại rồi quay lại vị trí cũ để thử nhánh khác.

### Backtracking có kiểm soát

Với parser combinator hoặc PEG, backtracking có thể là phần tự nhiên của thuật toán. Vấn đề xuất hiện khi nhiều nhánh thử cùng một prefix dài.

### Cut/commit point

Sau khi parser đã nhận một token phân biệt một production, có thể commit vào nhánh đó. Nếu phần sau sai, báo lỗi tại nhánh đã chọn thay vì quay lại thử alternative không còn hợp lý.

### Lookahead

Một token lookahead có thể phân biệt hai declaration. Nhưng nếu cần lookahead dài, hãy xem lại grammar và prefix factoring.

### Repeated alternatives

Các alternative có prefix giống nhau có thể khiến parser scan cùng vùng source nhiều lần. Left factoring hoặc parse prefix chung một lần thường giảm chi phí.

### Backtracking budget

Với DSL do người dùng cung cấp, có thể đặt giới hạn parse steps hoặc thời gian để bảo vệ service. Khi vượt giới hạn, trả diagnostic rõ như PARSER_RESOURCE_LIMIT.

### Không tối ưu bằng cách bỏ semantics

Không nên loại bỏ alternative hợp lệ chỉ để parser nhanh hơn nếu điều đó thay đổi ngôn ngữ. Cần giữ grammar contract và kiểm thử regression.

## 10. Memoization và packrat parsing

Memoization lưu kết quả parse của một rule tại một vị trí input để không tính lại cùng cặp rule/position.

Với packrat parsing, mỗi rule-position có thể được tính tối đa một lần trong một parse, giúp kiểm soát backtracking và đạt thời gian tuyến tính theo số rule nhân số vị trí, với giả định phù hợp.

### Memo key

Key thường gồm rule ID và input offset. Nếu parsing phụ thuộc semantic context hoặc mode, key phải bao gồm context identity/version hoặc memoization có thể trả kết quả sai.

### Memory tradeoff

Memo table có thể chiếm memory tỷ lệ với số rule và input position. Với file rất lớn hoặc grammar nhiều rule, memory cost có thể đáng kể.

### Selective memoization

Không nhất thiết memoize mọi rule. Có thể chỉ memoize rule có backtracking lặp hoặc chi phí cao. Cần profiler xác định rule nóng.

### Memo result

Memo entry có thể lưu success/failure, end position và parse node/result. Nếu node mutable hoặc phụ thuộc source lifetime, cần ownership rõ.

### Cache lifetime

Memo table thường chỉ tồn tại trong một parse invocation. Chia sẻ memo table giữa các file hoặc source version cần thiết kế phức tạp hơn và có nguy cơ stale result.

## 11. AST construction và allocation

AST là cấu trúc quan trọng để compiler và tooling sử dụng sau parsing. Cách tạo AST ảnh hưởng đáng kể đến allocation và memory.

### Chỉ tạo node cần thiết

Concrete syntax tree giữ mọi token/trivia; AST thường chỉ giữ cấu trúc có ý nghĩa cho semantic processing. Nếu IDE cần formatting/refactoring, có thể giữ CST riêng hoặc trivia side table.

### Compact node representation

Một node có thể chứa kind, child range và source span. Dùng object hierarchy giúp code dễ đọc nhưng tạo nhiều object; arena/flat array có thể tiết kiệm memory ở workload lớn.

### Immutable AST

AST immutable giúp chia sẻ giữa thread và cache an toàn. Mutation trong semantic phase có thể được thay bằng side table chứa symbol/type information.

### Source span

Lưu start/end offset thay vì copy source substring cho từng node. Diagnostic và editor có thể lấy text từ source buffer.

### Lazy materialization

Một số literal hoặc metadata chỉ cần khi semantic analysis. Có thể trì hoãn conversion tốn kém, ví dụ parse BigDecimal hoặc decode string escape đến khi cần, nhưng phải cân bằng chi phí lặp.

### List building

Không nên nối immutable list bằng cách copy toàn bộ list mỗi lần thêm child. Dùng mutable builder nội bộ rồi freeze, hoặc append-friendly data structure.

### Object pooling?

Object pooling không mặc nhiên nhanh trong Java. Nó có thể giữ object sống lâu, tăng retention và phức tạp concurrency. Hãy đo allocation/GC trước khi dùng pool.

## 12. Giảm chi phí source và token representation

Một số tối ưu không thay đổi grammar nhưng giảm công việc lặp.

### Source buffer

Đọc source một lần vào buffer phù hợp. Với file lớn, có thể dùng byte buffer và decode có kiểm soát; với parser Java thông thường, String hoặc char array có thể đủ tốt.

### Offset thay vì substring

Token lưu start/end offset. Khi cần lexeme, tạo view hoặc lấy substring một lần ở consumer. Cần giữ source immutable trong thời gian node tồn tại.

### Interning identifier

Các identifier lặp như tên keyword hoặc symbol phổ biến có thể dùng symbol table. Không nên gọi String.intern() bừa bãi vì global string pool và lifetime có thể gây vấn đề. Một interner scoped theo compilation unit thường dễ quản lý hơn.

### Token channel

Whitespace/comment có thể nằm ở channel phụ để formatter sử dụng, trong khi parser chính chỉ nhận token có ý nghĩa cú pháp.

### Avoid redundant conversion

Không chuyển token text sang nhiều representation liên tiếp. Ví dụ lexer đã parse integer thành primitive thì AST builder không nên parse lại; ngược lại, nếu chưa cần numeric value thì đừng parse sớm.

### Source encoding

Decode đúng charset và xử lý BOM/newline nhất quán. Sai offset do byte index và character index khác nhau có thể làm diagnostic lệch vị trí.

## 13. Incremental parsing cho IDE và editor

Trong IDE, người dùng thay đổi một vài ký tự nhưng parser có thể được yêu cầu cập nhật cấu trúc nhanh. Parse lại toàn bộ file sau mỗi phím gõ có thể gây latency và làm editor mất phản hồi.

**Incremental parsing** cập nhật parse result bằng cách tái sử dụng phần cấu trúc không bị ảnh hưởng bởi edit.

### Edit range

Một edit thường có start offset, deleted length và inserted text. Parser xác định vùng syntax có thể bị ảnh hưởng.

### Reuse subtree

Nếu subtree nằm ngoài vùng thay đổi và context grammar không đổi, có thể tái sử dụng node cũ. Cần cập nhật source span/offset hoặc dùng structure có relative positions.

### Syntax boundary

Một thay đổi nhỏ có thể ảnh hưởng vùng lớn hơn nếu nó đổi delimiter, quote hoặc comment boundary. Ví dụ thêm dấu ngoặc mở có thể làm phần còn lại của file được parse khác.

### Incremental lexer

Lexer có thể re-tokenize từ một checkpoint trước edit đến khi state/token boundary trở lại ổn định. Với multiline string/comment, checkpoint cần giữ lexical mode.

### Incremental parser

Parser cần xác định vùng grammar phụ thuộc vào token đã đổi. Một số parser generator hoặc tree-sitter-like approach hỗ trợ incremental tree; recursive descent custom có thể cần xây cache/subtree reuse riêng.

### Error-tolerant parse

Trong lúc người dùng gõ, source thường chưa hợp lệ. Parser editor cần tạo error node hoặc missing token placeholder để vẫn cung cấp outline, completion và syntax highlighting.

### Debounce và cancellation

Editor có thể debounce parse request và hủy parse cũ khi edit mới đến. Cancellation phải được kiểm tra ở các điểm an toàn để không tiếp tục tốn CPU cho version source đã lỗi thời.

### Source version

Mỗi parse result cần gắn source version. Kết quả parse từ version cũ không được ghi đè model của version mới khi các request hoàn thành sai thứ tự.

## 14. Error recovery và tốc độ khi source không hợp lệ

Parser trong compiler batch có thể dừng khi gặp lỗi đầu tiên. Parser trong IDE thường cần tiếp tục để phát hiện thêm lỗi và giữ cấu trúc hữu ích.

### Panic-mode recovery

Parser bỏ qua token đến một synchronization token như semicolon, closing brace hoặc keyword bắt đầu declaration tiếp theo.

~~~text
rule First {
    when customer.active
    then approve();
}

rule Second {
    when order.total > 0;
    then process();
}
~~~

Nếu thiếu semicolon sau điều kiện rule đầu, parser có thể skip đến then hoặc closing brace theo recovery strategy.

### Error productions

Grammar có thể định nghĩa một số dạng lỗi phổ biến để tạo diagnostic tốt hơn. Nhưng quá nhiều error production có thể làm grammar lớn và parser phức tạp.

### Missing token insertion

Parser có thể giả định một token bị thiếu, như ) hoặc ;, để tiếp tục. Diagnostic cần đánh dấu token được synthetic tạo ra.

### Error node

AST có thể chứa ErrorNode để downstream tool vẫn hoạt động. Semantic analysis phải biết bỏ qua hoặc xử lý node lỗi an toàn.

### Diagnostic flood

Một lỗi đầu có thể tạo hàng trăm lỗi dây chuyền. Cần giới hạn số diagnostic, ưu tiên lỗi gốc và tránh parse recovery lặp vô hạn.

### Error-path benchmark

Đo source sai ở đầu, giữa và cuối file; thiếu delimiter; string chưa đóng; token lạ; nesting sâu. Error recovery có thể tốn nhiều hơn parse hợp lệ.

## 15. Deep nesting và recursion depth

Grammar có thể cho phép biểu thức hoặc block lồng sâu:

~~~text
((((((((value))))))))
~~~

Recursive descent có thể dùng call stack tỷ lệ với nesting depth. Input rất sâu có thể gây StackOverflowError.

### Giới hạn nesting

Đặt max nesting depth và trả diagnostic thay vì để JVM stack overflow. Giới hạn phải được cấu hình hợp lý với DSL và threat model.

### Iterative parsing

Một số cấu trúc có thể parse bằng explicit stack thay cho recursion. Điều này giúp kiểm soát memory và tránh giới hạn call stack, nhưng code phức tạp hơn.

### Tail recursion

Java không đảm bảo tail-call optimization. Không nên giả định recursive parser sẽ được tối ưu thành vòng lặp.

### AST depth

Ngay cả khi parser không overflow, downstream visitor hoặc serializer đệ quy cũng có thể overflow. Cần xem toàn bộ pipeline với input lồng sâu.

### Adversarial nesting

Test depth lớn, nested parentheses, nested arrays/blocks và chain unary operators để xác định giới hạn an toàn.

## 16. Parsing nhiều file và module song song

Build system hoặc server có thể phân tích nhiều DSL file độc lập.

### File-level parallelism

Nếu file không phụ thuộc nhau về cú pháp, có thể parse song song trên bounded executor. Mỗi parse invocation có lexer, parser và diagnostic buffer riêng.

### Shared immutable grammar

Grammar table hoặc parser metadata bất biến có thể được chia sẻ. Không chia sẻ mutable cursor, token buffer hoặc parse stack giữa thread.

### Module dependency

Nếu file import module khác, parse syntax có thể song song nhưng resolution/semantic analysis cần dependency graph. Có thể chia pipeline thành parse phase độc lập và resolve phase theo DAG.

### CPU saturation

Tăng số thread không giúp khi CPU đã bão hòa; nó còn tăng context switching và memory pressure. Chọn parallelism theo core, workload và giới hạn heap.

### Deterministic diagnostics

Khi parse song song, thứ tự completion không ổn định. Nếu output cần reproducible, sort diagnostics theo file path/source offset thay vì arrival order.

### Cancellation

Nếu một build bị hủy, các parser task cần nhận cancellation và dừng sớm. Không để background parse tiếp tục chiếm executor sau khi caller đã bỏ request.

### Backpressure

Không submit hàng triệu file vào unbounded queue. Dùng bounded queue, streaming submission hoặc batch để kiểm soát memory.

## 17. Cache trong parsing pipeline

Cache có thể giảm thời gian lặp lại khi definition hoặc dependency không đổi.

### Token cache

Có thể cache token stream theo source content hash và lexer version. Cần tính cả lexical options và language version nếu chúng ảnh hưởng tokenization.

### AST cache

Cache AST theo source hash, grammar/language version và parser configuration. Nếu AST chứa mutable semantic annotations, cần tách phần immutable syntax khỏi semantic state.

### Compiled artifact cache

Cache IR/bytecode theo definition version, compiler version và dependency fingerprint. Đây là cache sau parse nhưng thường được gọi chung trong compiler pipeline.

### Incremental dependency cache

Khi module A chỉ import B, thay đổi module C không liên quan không nên buộc parse lại A nếu dependency graph và cache policy cho phép.

### Cache invalidation

Cache key thiếu language version hoặc plugin fingerprint có thể trả AST/executable sai semantics. Invalidation phải dựa trên identity/version đầy đủ.

### Memory bound

Cache phải có giới hạn size/weight và eviction. File cũ hoặc tenant không còn hoạt động không nên giữ memory vô hạn.

### Cache metrics

Theo dõi hit rate, miss rate, load time, eviction, memory weight và stale entry. Hit rate cao không có nghĩa cache có lợi nếu lookup/copy cost lớn.

## 18. Parser generator và runtime overhead

Parser có thể được viết tay hoặc sinh từ grammar bằng parser generator.

### Generated parser

Generator tạo code/table từ grammar. Lợi ích là grammar có thể được kiểm tra conflict và parser runtime được chuẩn hóa. Cần xem kích thước generated code, startup cost và khả năng custom diagnostics.

### Hand-written parser

Parser viết tay có thể tối ưu cho DSL nhỏ hoặc grammar đặc thù. Nó dễ tích hợp semantic context nhưng grammar có thể khó audit và dễ lệch với documentation.

### Runtime grammar loading

Một số hệ thống load grammar động. Khi đó cần đo grammar compilation, cache và thread safety. Nếu grammar cố định, compile/build-time thường giảm startup overhead.

### Parser table size

LR table hoặc grammar metadata có thể lớn. Tối ưu table representation và initialization có thể ảnh hưởng memory/startup.

### Grammar changes

Thay grammar có thể làm thay đổi generated parser và parse tree. Cần test corpus và compatibility, không chỉ benchmark tốc độ.

### Chọn tool theo hệ sinh thái

Cân nhắc khả năng tạo source location, error recovery, incremental parse, Unicode, grammar debugging, IDE integration và licensing/maintenance của tool.

## 19. Regex và lexer performance

Regex có thể tiện cho token đơn giản nhưng cần chú ý catastrophic backtracking.

### Regex cho token nhỏ

Pattern cho identifier hoặc integer đơn giản thường có thể hoạt động tốt. Tuy nhiên, một regex lớn kết hợp nhiều alternative có thể khó đoán hiệu năng.

### Catastrophic backtracking

Một pattern có nhiều nhóm lặp và alternative chồng lấn có thể thử rất nhiều đường trên input bất lợi. Nếu source do người dùng cung cấp, đây có thể là rủi ro từ chối dịch vụ.

### Possessive quantifier và atomic group

Một số regex engine hỗ trợ cách khóa backtracking trong phần pattern đã chắc chắn. Chỉ dùng khi semantics đúng và benchmark chứng minh có lợi.

### State machine lexer

Với lexical grammar phức tạp, state machine hoặc DFA có thể dễ kiểm soát worst-case hơn. Lexer có thể có state cho normal, string, comment, template hoặc interpolation.

### Regex compile cost

Không compile Pattern mới cho mỗi token hoặc mỗi parse. Compile một lần rồi reuse thread-safe Pattern khi phù hợp, hoặc dùng scanner chuyên dụng.

### Benchmark adversarial input

Test chuỗi dài gần giống pattern nhưng không khớp, escape lồng, comment chưa đóng và identifier rất dài.

## 20. Streaming parsing và file lớn

Một số DSL file có thể rất lớn, ví dụ batch import, schema catalog hoặc generated rule set.

### Whole-file parsing

Đọc toàn file vào memory giúp parser random access và source span đơn giản. Phù hợp file vừa phải và cần AST toàn cục.

### Streaming lexer/parser

Streaming parser đọc chunk và giữ state qua chunk boundary. Cách này giảm peak memory nhưng grammar cần hỗ trợ xử lý tuần tự và diagnostic source position phức tạp hơn.

### Chunk boundary

Token có thể bị chia giữa hai chunk, ví dụ identifier dài hoặc string literal. Lexer cần carry state và buffer phần token chưa hoàn chỉnh.

### Top-level streaming

Một giải pháp trung gian là parse từng top-level declaration, giữ source span và index cần thiết. Module có thể xử lý từng declaration rồi giải phóng phần không còn cần.

### Global reference resolution

Nếu declaration tham chiếu lẫn nhau, streaming parse vẫn có thể cần symbol index hoặc deferred resolution. Cần xác định memory tradeoff.

### Backpressure trong stream

Khi parser phát declaration cho downstream processor, downstream cần khả năng báo chậm. Nếu producer tiếp tục đọc vô hạn, queue trung gian có thể chiếm hết memory.

### Partial result

Streaming parser có thể phát declaration đã hoàn tất trước khi file kết thúc. Consumer phải biết result là provisional hay committed và xử lý lỗi cuối file.

## 21. Parallel parsing trong một process Java

Java có thể phân tích nhiều source file song song bằng executor.

~~~java
ExecutorService pool = Executors.newFixedThreadPool(
    Runtime.getRuntime().availableProcessors()
);

try {
    List<Future<ParseResult>> futures = new ArrayList<>();

    for (SourceFile source : sources) {
        futures.add(pool.submit(() -> parserFactory.create().parse(source)));
    }

    for (Future<ParseResult> future : futures) {
        ParseResult result = future.get();
        collect(result);
    }
} finally {
    pool.shutdown();
}
~~~

Ví dụ trên chỉ minh họa. parserFactory.create() tạo parser state riêng cho mỗi task; nếu parser implementation được thiết kế immutable/thread-safe, có thể reuse theo contract.

### Parser thread safety

Parser thường có cursor, token buffer và error list mutable. Không dùng chung một parser instance giữa nhiều thread trừ khi implementation explicitly thread-safe.

### Executor ownership

Nếu pool do application tạo, application chịu trách nhiệm shutdown. Nếu engine tạo pool, engine cần đóng nó trong lifecycle. Tránh đóng executor bên ngoài khi task còn dùng.

### Bounded submission

List Future cho tất cả file có thể giữ quá nhiều task và result. Với corpus lớn, dùng bounded queue hoặc completion service để tiêu thụ dần.

### Deterministic aggregation

Collect result theo source identity rồi sort để output ổn định. Không phụ thuộc thứ tự thread hoàn thành.

### Failure isolation

Một file parse lỗi nên trả ParseResult chứa diagnostic thay vì làm hỏng toàn batch. Lỗi hạ tầng như executor shutdown cần được phân biệt với syntax error.

## 22. Benchmark parser một cách đáng tin cậy

Benchmark cần phản ánh workload thực tế và tránh sai lệch đo lường.

### Corpus

Tạo corpus có:
- File nhỏ, trung bình và lớn.
- Declaration đơn giản và expression phức tạp.
- Nesting nông và sâu.
- Nhiều comment/string literal.
- Module nhiều reference.
- Input hợp lệ và không hợp lệ.
- Input có đặc điểm bất lợi cho backtracking.

### JMH

Với Java, JMH phù hợp cho microbenchmark vì xử lý warm-up, fork, measurement iteration và một số vấn đề tối ưu hóa JVM.

Ví dụ khung benchmark:

~~~java
@State(Scope.Thread)
public class ParserBenchmark {
    private String source;
    private Parser parser;

    @Setup
    public void setup() {
        source = loadBenchmarkSource();
        parser = new Parser();
    }

    @Benchmark
    public ParseResult parseSource() {
        return parser.parse(source);
    }
}
~~~

Đây là khung minh họa. Cần bảo đảm ParseResult được tiêu thụ để tránh dead-code elimination, và parser state được reset đúng giữa các lần đo.

### Warm-up

JVM cần thời gian JIT compile. Không đo vài lần đầu rồi kết luận parser chậm. Dùng warm-up iterations phù hợp và nhiều fork để giảm ảnh hưởng của process state.

### Avoid benchmark contamination

Không đọc file, log hoặc tạo executor mới trong mỗi invocation nếu mục tiêu là đo parser core. Nếu muốn đo end-to-end, tạo benchmark riêng có các chi phí đó.

### Throughput và average time

Có thể dùng benchmark mode throughput và average time. Với request service, cần thêm load test để đo percentile latency dưới concurrency.

### Allocation profiling

Dùng profiler để đo bytes allocated/op và object type nóng. Tối ưu allocation thường mang lại lợi ích lớn cho parser xử lý nhiều file.

### Reproducibility

Ghi CPU, JVM version, heap, GC, OS, benchmark parameters, corpus version và commit. Không so sánh số liệu từ máy khác mà không nêu môi trường.

### Statistical interpretation

Chạy đủ iteration và xem variation/error. Một thay đổi 1-2% có thể chỉ là noise. Dùng confidence interval hoặc so sánh phân phối khi cần.

## 23. Profiling để tìm bottleneck

Benchmark cho biết có vấn đề; profiler giúp xác định vấn đề nằm ở đâu.

### CPU profiling

Xác định method chiếm CPU: lexer scan, parser method, regex, AST builder, string conversion hay semantic callback.

### Allocation profiling

Xác định object nào được tạo nhiều: Token, AST node, substring, collection, diagnostic hoặc temporary wrapper.

### Heap analysis

Kiểm tra retained object sau parse. AST cache hoặc source buffer có thể giữ memory lâu hơn dự kiến.

### GC analysis

Nếu parse throughput dao động, xem GC frequency, pause và allocation rate. Giảm allocation thường tốt hơn tăng heap vô hạn.

### Lock profiling

Parser core thường có thể chạy độc lập. Nếu nhiều thread cùng parse nhưng bị lock ở global symbol table, cache hoặc interner, parallelism sẽ không mở rộng tốt.

### I/O profiling

Nếu source loading chiếm thời gian, parser algorithm không phải bottleneck. Có thể cần buffered read, asynchronous fetch hoặc cache source content.

### Flame graph

Flame graph giúp nhìn phần CPU tích lũy theo call stack. Cần chạy với workload đại diện và không bật instrumentation quá nặng.

## 24. Tối ưu semantic work khỏi parsing

Một parser nên tập trung xây dựng cú pháp. Thực hiện quá nhiều lookup hoặc business validation trong lúc parse có thể làm parsing chậm và phụ thuộc context.

### Parse syntax trước

Tạo AST với identifier và source span. Sau đó name resolution tìm symbol trong scope thích hợp.

### Symbol table

Xây symbol table một lần theo scope/module thay vì tìm tuyến tính trong danh sách mỗi lần gặp identifier.

### Deferred resolution

Reference tới declaration xuất hiện sau có thể được lưu dưới dạng unresolved symbol rồi resolve sau khi đã index module.

### Type checking

Type checker có thể chạy trên AST immutable và lưu type result trong side table. Điều này cho phép reuse syntax tree khi semantic environment thay đổi ít.

### Semantic cache

Cache kết quả resolve/type check cần key gồm AST identity, scope version, dependency version và compiler semantics. Nếu environment đổi, cache cũ phải invalidated.

### Parse API không làm I/O ẩn

Parser không nên truy cập database hoặc network để resolve tên khi parse. Điều đó làm latency không ổn định và khó benchmark. Hãy tách source loading/resolution khỏi parser core.

## 25. Parser cancellation và resource limits

Parsing có thể chạy trong API request, IDE hoặc build. Cần kiểm soát tài nguyên.

### Input size limit

Giới hạn bytes hoặc characters trước khi parse. Nếu DSL cho phép file rất lớn, dùng limit riêng cho trusted build input và untrusted request.

### Token limit

Một input có thể nhỏ nhưng tạo rất nhiều token. Token count limit giúp kiểm soát memory.

### Nesting limit

Giới hạn nested expression/block để tránh stack exhaustion và pathological AST.

### Time budget

Parser có thể kiểm tra deadline hoặc cancellation token định kỳ. Kiểm tra quá thường xuyên cũng có overhead; cần đặt ở loop/phase phù hợp.

### Memory budget

Java không có cơ chế giới hạn heap riêng cho một parse đơn giản. Có thể giới hạn input/token/node count, chạy parser trong isolated process hoặc dùng quota ở service layer.

### Cancellation safety

Khi cancel, parser phải không để shared state ở trạng thái nửa cập nhật. Parse result nên được publish khi hoàn tất hoặc có trạng thái cancelled rõ.

### Diagnostic resource limit

Nếu quá nhiều lỗi, parser có thể dừng sau max diagnostics và trả TOO_MANY_ERRORS cùng vị trí tiếp theo.

## 26. Grammar và parser design cho DSL lớn

DSL lớn thường được chia module hoặc grammar fragment.

### Modular grammar

Chia declaration, expression, type, statement và annotation thành các phần có interface rõ. Module grammar cần khai báo dependency và extension point.

### Avoid uncontrolled grammar extension

Plugin có thể thêm syntax mới, nhưng nhiều extension cùng sửa prefix hoặc precedence có thể gây ambiguity. Cần extension policy và conflict check.

### Language profile

Một engine có thể bật subset syntax theo profile. Profile cần version và xác định token/production được phép, không nên thay đổi grammar âm thầm theo môi trường.

### Reserved keyword

Thêm keyword có thể làm identifier cũ trở thành reserved và gây breaking change. Có thể dùng contextual keyword hoặc language version để tiến hóa.

### Grammar regression corpus

Mỗi grammar change nên chạy corpus đại diện và kiểm tra AST/diagnostics. Đây là kiểm thử của parser implementation, không chỉ benchmark tốc độ.

### Grammar visualization

Railroad diagram, parse tree và grammar report giúp nhóm hiểu production, conflict và lookahead. Tài liệu grammar tốt giảm lỗi khi tối ưu.

## 27. Source location và diagnostic hiệu quả

Diagnostic tốt cần vị trí chính xác mà không làm parser chậm đáng kể.

### Offset

Lưu offset theo code unit hoặc byte cần được quy định. Java String dùng UTF-16 code unit; editor/protocol có thể dùng UTF-16 position hoặc code point. Mapping cần rõ.

### Line map

Có thể tạo line-start index khi lexer gặp newline. Khi cần chuyển offset thành line/column, binary search trên line-start array thay vì scan từ đầu file mỗi lần.

### Column calculation

Tab và Unicode có thể khiến visual column khác character offset. Diagnostic API cần phân biệt raw offset, logical column và display column nếu cần.

### Lazy diagnostic rendering

Lưu error code, source span và arguments; chỉ tạo message string khi client cần. Điều này giảm allocation khi parser sinh nhiều diagnostic nhưng consumer chỉ hiển thị một số.

### Error deduplication

Recovery có thể báo cùng một lỗi ở nhiều phase. Dùng source span/code key để loại duplicate phù hợp.

### Source retention

Nếu AST giữ offset nhưng source buffer đã bị giải phóng, formatter/diagnostic không thể trích text. Cần quản lý lifetime hoặc copy nội dung cần thiết.

## 28. Tốc độ parsing trong production service

Khi DSL được parse theo request, hiệu năng cần nhìn ở mức service.

### Request isolation

Một request parse nên có context, memory budget và cancellation riêng. Không cho một file lớn làm nghẽn toàn bộ request nhỏ.

### Admission control

Giới hạn số parse đồng thời. Nếu quá tải, trả response retryable hoặc queue theo policy thay vì nhận hết.

### Cache và deduplication

Hai request cùng parse một immutable source version có thể share result nếu cache key chính xác. In-flight request deduplication giúp tránh compile cùng definition nhiều lần.

### Tenant fairness

Tenant có thể gửi nhiều definition lớn. Áp quota theo tenant và priority để tránh một tenant chiếm hết CPU.

### Latency budget

Đặt mục tiêu parse latency theo kích thước/complexity class. Nếu vượt budget, ghi metric và có thể trả timeout/resource limit.

### Graceful degradation

Editor có thể ưu tiên outline/syntax highlighting từ partial parse; production publish có thể yêu cầu full parse và semantic validation. Hai use case có latency và correctness contract khác nhau.

### Observability

Ghi source size, token count, parse duration, parser version, cache hit, error count và cancellation reason. Tránh ghi raw DSL source nếu chứa thông tin nhạy cảm.

## 29. Ví dụ pipeline parsing tối ưu trong Java

Một thiết kế tách phase có thể như sau:

~~~java
public final class DslCompiler {
    private final LexerFactory lexerFactory;
    private final ParserFactory parserFactory;
    private final Resolver resolver;
    private final TypeChecker typeChecker;

    public CompilationResult compile(SourceText source) {
        TokenStream tokens = lexerFactory.create().lex(source);
        ParseResult parsed = parserFactory.create().parse(tokens);

        if (!parsed.success()) {
            return CompilationResult.parseFailure(parsed.diagnostics());
        }

        ResolvedModel resolved = resolver.resolve(parsed.ast());

        TypeCheckResult checked = typeChecker.check(resolved);
        if (!checked.success()) {
            return CompilationResult.typeFailure(checked.diagnostics());
        }

        return CompilationResult.success(checked.model());
    }
}
~~~

Ví dụ minh họa này thể hiện separation of concerns:
- Lexer chỉ tạo token.
- Parser chỉ xây syntax model.
- Resolver tìm reference.
- Type checker kiểm tra kiểu.
- Compiler tổng hợp result.

### Parser factory

Factory tạo parser state riêng cho từng invocation hoặc thread. Grammar metadata có thể được chia sẻ nếu immutable.

### Compilation result

Result phân biệt lỗi parse, lỗi resolution, lỗi type và thành công. Điều này giúp benchmark từng phase và báo diagnostic đúng nguồn.

### Avoid parse on every evaluation

Nếu definition không đổi, compile một lần rồi reuse executable artifact. Parse lại cho mỗi request chỉ hợp lý khi source thực sự thay đổi hoặc runtime semantics yêu cầu dynamic evaluation.

### Immutable compiled model

Model sau compile nên immutable hoặc có concurrency contract rõ. Execution context được tạo riêng cho từng request.

## 30. Các chiến lược tối ưu theo loại DSL

| Loại DSL | Bottleneck thường gặp | Hướng tối ưu |
|---|---|---|
| Expression DSL | Operator precedence, function call, repeated parse. | Pratt parser, compiled expression cache. |
| Rule DSL | Nhiều declaration, condition và reference. | Efficient lexer, grammar factoring, batch symbol resolution. |
| Workflow DSL | Nested blocks, graph/reference validation. | Parse syntax riêng, build graph ở semantic phase. |
| Schema DSL | Nested type, import và recursive reference. | Type cache, dependency graph và deferred resolution. |
| Query DSL | Expression tree, identifier lookup và literal. | Specialized expression parser, prepared plan cache. |
| Configuration DSL | Nhiều file nhỏ, startup latency. | Parallel file parse, bounded cache, precompiled config. |
| Editor DSL | Parse sau từng edit, source chưa hoàn chỉnh. | Incremental parser, error recovery, cancellation. |

### Expression DSL

Expression parser thường được gọi nhiều lần. Có thể compile expression thành reusable plan và tránh parse lại khi input expression không đổi.

### Rule DSL

Nhiều rule có thể dùng chung type/function. Resolve symbol một lần và reuse immutable symbol table theo module version.

### Workflow DSL

Parsing syntax chỉ tạo node; kiểm tra graph, reachability và cycle nên được tách thành validation phase để dễ profiling.

### Schema DSL

Nested type và recursive reference cần cache type resolution, nhưng phải pin version để tránh resolve sai dependency.

### Configuration DSL

Startup có thể parse nhiều file độc lập. Parallel parse và prevalidation trong CI có thể giảm thời gian startup.

## 31. Những lỗi tối ưu thường gặp

**Đo cả I/O và gọi đó là parser time.** Không xác định được bottleneck thực sự. Tách source loading, lexing, parsing và semantic phases.

**Chỉ benchmark một file nhỏ.** Không đại diện cho workload production. Dùng corpus nhiều kích thước và cấu trúc.

**Chỉ đo input hợp lệ.** Error recovery có thể là phần lớn trải nghiệm editor. Thêm invalid corpus.

**Tối ưu micro-method trước khi profile.** Có thể làm code khó hiểu mà không cải thiện tổng thể. Dùng CPU/allocation profiler trước.

**Chia sẻ parser mutable giữa thread.** Cursor và token buffer bị race, tạo lỗi không ổn định. Tạo parser state riêng cho mỗi invocation.

**Cache thiếu language/dependency version.** Có thể dùng parse result hoặc artifact sai semantics. Cache key phải đủ identity.

**Tạo substring cho mọi token.** Tăng allocation và GC. Dùng source offset nếu lifetime cho phép.

**Backtracking không giới hạn.** Input bất lợi có thể làm latency tăng mạnh. Left-factor grammar, commit point hoặc memoize có chọn lọc.

**Dùng regex phức tạp cho toàn bộ lexer.** Có thể gặp catastrophic backtracking. Dùng scanner/state machine cho lexical structure phức tạp.

**Tăng thread pool vô hạn.** Làm queue và memory tăng, gây contention. Dùng bounded executor và admission control.

**Object pooling không có số liệu.** Pool có thể làm object sống lâu và khó quản lý. Chỉ dùng khi benchmark chứng minh lợi ích.

**Đưa database lookup vào parser.** Parsing trở nên phụ thuộc network và khó tái lập. Tách resolution/semantic phase.

**Không giới hạn nesting hoặc input size.** Parser có thể bị StackOverflowError hoặc tiêu thụ quá nhiều resource. Đặt budget và diagnostic rõ.

**Tái sử dụng AST mutable giữa request.** Semantic annotation của request này có thể rò sang request khác. Tách immutable syntax tree và per-execution state.

**Bỏ qua source location để tiết kiệm memory.** Diagnostic và IDE experience giảm mạnh. Dùng offset compact thay vì bỏ hẳn vị trí.

## 32. Quy trình cải thiện tốc độ parsing

Một quy trình thực tế có thể gồm:

1. **Xác định workload:** loại DSL, kích thước file, số file, tần suất và môi trường sử dụng.
2. **Đặt metric:** latency, throughput, allocation, peak heap, GC và error-path latency.
3. **Tách pipeline:** đo source loading, lexing, parsing, AST, resolution và validation riêng.
4. **Tạo corpus:** file nhỏ/lớn, syntax phức tạp, nesting sâu và invalid input.
5. **Benchmark baseline:** dùng JMH cho parser core và load test cho service.
6. **Profile:** tìm CPU hotspot, allocation, lock, GC và I/O.
7. **Rà grammar:** prefix chung, left recursion, ambiguity, precedence và backtracking.
8. **Tối ưu lexer:** single-pass scan, token offsets, keyword lookup và string handling.
9. **Tối ưu parser:** chọn algorithm phù hợp, lookahead có giới hạn và memoization có chọn lọc.
10. **Tối ưu AST:** compact node, immutable model, list builder và source span.
11. **Tách semantic work:** resolution/type checking khỏi parse core.
12. **Thêm cache/incremental:** theo version và dependency fingerprint.
13. **Kiểm soát concurrency:** bounded pool, cancellation, quota và backpressure.
14. **Kiểm thử regression:** AST/diagnostic không đổi ngoài dự kiến và performance không suy giảm.
15. **Theo dõi production:** percentile, cache hit, source size, token count, error rate và resource limits.

## 33. Checklist đánh giá parser performance

Trước khi phát hành parser hoặc thay đổi grammar, cần xác nhận:

- Đã tách thời gian loading, lexing, parsing và semantic analysis chưa?
- Benchmark có corpus đại diện cho kích thước và cấu trúc thực tế không?
- Có đo cold start, warm parse và invalid input không?
- Có báo latency percentile và throughput không?
- Có đo allocation, peak heap và GC không?
- Grammar có ambiguity, left recursion hoặc prefix chung không cần thiết không?
- Backtracking có giới hạn hoặc memoization phù hợp không?
- Lexer có scan một lượt và tránh substring allocation không?
- Unicode, string escape và numeric literal có xử lý hiệu quả, đúng semantics không?
- AST có giữ source span mà không copy text dư thừa không?
- Parser state có an toàn khi chạy đồng thời không?
- Cache key có chứa language/parser/dependency version không?
- Incremental parse có gắn source version và cancellation không?
- Input size, token count, nesting và parse time có giới hạn không?
- Error recovery có giới hạn diagnostic và tránh cascade không?
- Batch parsing có bounded executor và backpressure không?
- Semantic lookup có được tách khỏi parser core không?
- Benchmark có ghi JVM, hardware, corpus và commit không?
- Thay đổi hiệu năng có được đối chiếu với correctness/AST regression corpus không?

## 34. Kết quả cần có sau khi tối ưu tốc độ parsing

Một chiến lược parsing performance hoàn chỉnh thường cung cấp:

- **Performance model:** latency, throughput, allocation, memory và GC metrics.
- **Phase instrumentation:** source loading, lexing, parsing, AST construction, resolution và validation.
- **Grammar design:** ambiguity, precedence, associativity, left factoring và recursion policy.
- **Parser algorithm:** recursive descent, LL, Pratt, LR, PEG hoặc combinator được chọn theo yêu cầu.
- **Lexer strategy:** single-pass scanning, token representation, Unicode và literal handling.
- **Backtracking control:** lookahead, commit point, memoization và worst-case budget.
- **AST strategy:** compact nodes, source spans, immutable syntax tree và allocation control.
- **Incremental support:** edit range, subtree reuse, error tolerance và cancellation.
- **Concurrency model:** parser isolation, bounded executor, deterministic result và backpressure.
- **Caching policy:** token/AST/compiled artifact key, versioning, invalidation và memory bound.
- **Resource limits:** input size, token count, nesting depth, time và diagnostic count.
- **Benchmark suite:** JMH, representative corpus, invalid cases và load tests.
- **Operational observability:** parse duration, source size, token count, cache hit, error count và cancellation.
- **Regression evidence:** AST/diagnostic correctness và performance trend qua các phiên bản.

Tốc độ phân tích của DSL được quyết định bởi toàn bộ đường đi từ source text đến syntax model, không chỉ bởi parser algorithm. Muốn cải thiện đáng tin cậy, cần tách các phase để đo, chọn grammar ít ambiguity, tối ưu lexer và AST allocation, kiểm soát backtracking, đồng thời dùng cache hoặc incremental parsing khi source được tái sử dụng hay chỉnh sửa từng phần. Với Java, benchmark có warm-up và allocation profiling giúp phân biệt cải thiện thực với nhiễu của JVM; bounded concurrency, cancellation và resource limits bảo vệ ứng dụng khi xử lý nhiều hoặc input không tin cậy. Mọi tối ưu phải giữ nguyên semantics và diagnostic contract của DSL, vì parser nhanh nhưng tạo AST sai hoặc làm mất vị trí lỗi sẽ khiến toàn bộ hệ thống khó sử dụng và khó vận hành.

