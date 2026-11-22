# Tô màu cú pháp

## 1. Tô màu cú pháp là gì?

Tô màu cú pháp (syntax highlighting) là chức năng của trình soạn thảo mã nguồn dùng màu sắc, kiểu chữ hoặc dấu hiệu trình bày để phân biệt các thành phần trong văn bản chương trình. Với một DSL (Domain-Specific Language), editor có thể hiển thị từ khóa, tên biến, kiểu dữ liệu, chuỗi, số, toán tử, comment và các thành phần đặc thù của miền bằng những kiểu màu khác nhau.

Ví dụ, một rule trong DSL:

~~~text
rule high-value-order {
    when order.total > money(10000000, VND)
    then requireManualReview(order.id)
}
~~~

Editor có thể hiển thị rule, when và then bằng màu keyword; các tên order và requireManualReview bằng màu identifier; total và id bằng màu thuộc tính; 10000000 bằng màu literal số; còn dấu ngoặc và toán tử bằng màu trung tính.

Mục tiêu là giúp người đọc nhận ra cấu trúc nhanh hơn, phát hiện lỗi gõ dễ hơn và điều hướng chương trình thuận tiện. Đây là chức năng trình bày của editor. Màu sắc không làm thay đổi ngữ nghĩa, không thay thế parser và cũng không chứng minh chương trình đúng.

Một đoạn mã có thể được tô màu bình thường nhưng vẫn chứa lỗi cú pháp hoặc lỗi kiểu. Ngược lại, editor có thể chưa tô màu đúng một phần mã mới trong khi compiler vẫn phân tích và chạy được chương trình.

## 2. Vì sao DSL cần tô màu cú pháp?

DSL thường có từ vựng gần với ngôn ngữ nghiệp vụ: rule, policy, condition, action, entity, workflow hoặc schema. Người dùng có thể là developer, analyst hoặc chuyên gia miền nghiệp vụ. Tô màu giúp phân biệt nhanh cấu trúc ngôn ngữ với tên miền và dữ liệu.

Các lợi ích chính:

1. **Nhận biết cấu trúc:** keyword, literal, toán tử và comment dễ phân biệt.
2. **Đọc nhanh:** người dùng có thể quét qua một rule dài và tìm điều kiện hoặc hành động.
3. **Phát hiện lỗi gõ:** chuỗi chưa đóng, keyword viết sai hoặc dấu phân cách lạ có thể được hiển thị khác thường.
4. **Hỗ trợ học ngôn ngữ:** người mới dễ nhận ra thành phần nào là cú pháp và thành phần nào do người dùng đặt tên.
5. **Tăng khả năng điều hướng:** kết hợp với bracket matching, symbol navigation và semantic highlighting.
6. **Hỗ trợ kiểu miền:** Money, Duration, CustomerId hoặc OrderStatus có thể được trình bày nhất quán.

Tô màu không nên quá rực hoặc dùng quá nhiều màu gần nhau. Mục tiêu là làm nổi bật các khác biệt có ích, không biến mỗi từ thành một màu riêng khiến người đọc khó tập trung.

## 3. Tô màu cú pháp và semantic highlighting

Hai kỹ thuật có liên quan nhưng sử dụng thông tin khác nhau.

### 3.1. Lexical syntax highlighting

Lexical highlighting phân loại token dựa trên hình thức từ vựng: chuỗi ký tự, pattern, keyword và dấu phân cách. Nó thường hoạt động nhanh mà không cần hiểu toàn bộ chương trình.

Ví dụ, từ order có thể được tô như identifier dù editor chưa biết biến đó đã được khai báo hay chưa.

### 3.2. Semantic highlighting

Semantic highlighting sử dụng thông tin từ parser, symbol table hoặc language server để hiểu vai trò của một tên trong chương trình.

Ví dụ, cùng một từ customer có thể là biến cục bộ, tham số hàm, kiểu dữ liệu, namespace, thuộc tính hoặc hàm tích hợp. Lexical highlighter thường tô các trường hợp này gần giống nhau vì chúng có cùng dạng identifier. Semantic highlighter có thể phân biệt chúng theo loại symbol.

| Tiêu chí | Lexical highlighting | Semantic highlighting |
|---|---|---|
| Thông tin đầu vào | Ký tự và token | AST, symbol, type hoặc thông tin phân giải tên |
| Độ phức tạp | Thấp đến trung bình | Cao hơn |
| Tốc độ phản hồi | Thường rất nhanh | Có thể phụ thuộc language server |
| Hiểu khai báo và tham chiếu | Hạn chế | Có thể phân biệt chính xác |
| Mã chưa hoàn chỉnh | Thường hoạt động tốt với pattern đơn giản | Phụ thuộc khả năng phục hồi của parser |
| Ví dụ | Tô mọi tên theo identifier | Tô tham số, biến, kiểu và hàm khác nhau |

Một editor tốt có thể kết hợp cả hai. Lexical highlighting cung cấp màu cơ bản ngay khi người dùng gõ; semantic highlighting bổ sung hoặc điều chỉnh màu khi có thêm thông tin ngữ nghĩa.

## 4. Các nhóm token thường được tô màu

Một DSL có thể định nghĩa token groups riêng:

| Nhóm | Ví dụ | Ý nghĩa |
|---|---|---|
| Keyword | rule, when, then, import | Từ dành riêng của ngôn ngữ |
| Identifier | order, calculateTotal | Tên do người dùng khai báo hoặc tham chiếu |
| Type | Money, Order, CustomerId | Tên kiểu hoặc schema |
| Function | requireReview, sum | Tên hàm hoặc callable |
| Property | total, status, id | Thuộc tính hoặc field |
| String | "APPROVED" | Literal chuỗi |
| Number | 1000000, 3.14 | Literal số |
| Boolean | true, false | Literal logic |
| Null-like | null, none | Giá trị vắng mặt |
| Operator | +, >=, and | Toán tử |
| Punctuation | . , : ; | Dấu câu và phân cách |
| Bracket | ( ) { } [ ] | Dấu ngoặc |
| Comment | // note | Văn bản chú thích |
| Annotation | @deprecated | Metadata hoặc annotation |
| Constant | VND, MAX_RETRIES | Hằng số |
| Invalid token | Ký tự không hợp lệ | Đoạn nguồn bị lexer đánh dấu lỗi |

Không phải DSL nào cũng cần mọi nhóm. Nếu ngôn ngữ không có annotation hoặc kiểu generic, không cần tạo scope riêng cho chúng. Nên bắt đầu từ grammar thực tế và mở rộng khi có nhu cầu.

### 4.1. Keyword và identifier

Keyword được nhận diện bằng danh sách từ khóa dành riêng. Identifier là tên do chương trình đặt. Một vấn đề thường gặp là keyword mới trùng với identifier đã được phép trong phiên bản trước.

Ví dụ:

~~~text
let match = "approved";
rule match-order {
    when order.status == match
    then approve()
}
~~~

Nếu match là soft keyword chỉ có ý nghĩa ở một vị trí cú pháp nhất định, highlighter cần tuân theo đúng ngữ cảnh. Một regex đơn giản tô mọi từ match thành keyword có thể hiển thị sai.

### 4.2. Type, function và property

Nếu chỉ dựa trên lexical pattern, editor khó biết một identifier là type hay function. Có thể dùng quy ước tên, chẳng hạn kiểu viết PascalCase, nhưng đó chỉ là heuristic. Semantic highlighting mới có thể dựa trên symbol resolution để xác định chính xác.

### 4.3. Literal và escape

Trong chuỗi:

~~~text
message = "Order status: \n APPROVED";
~~~

Editor có thể tô toàn bộ chuỗi theo string color và escape sequence theo một màu phụ. Chuỗi chưa đóng có thể được tô bằng error scope nếu lexer hoặc grammar xác định được vị trí.

## 5. Kiến trúc tổng quát của syntax highlighter

Một highlighter nhận văn bản từ editor, phân tích thành token hoặc node, sau đó ánh xạ từng đoạn nguồn sang kiểu hiển thị.

~~~mermaid
flowchart TD
    A["Document text"] --> B["Tokenizer / Parser"]
    B --> C["Token or syntax nodes"]
    C --> D["Highlight scopes"]
    D --> E["Theme mapping"]
    E --> F["Editor decorations"]
    G["Semantic information"] --> H["Semantic token provider"]
    H --> F
~~~

Các thành phần chính:

- **Tokenizer hoặc parser:** nhận diện token và cấu trúc.
- **Highlight grammar:** quy định token hoặc node nào thuộc scope nào.
- **Semantic provider:** cung cấp phân loại theo symbol hoặc type.
- **Theme:** ánh xạ scope/token type thành màu, font style và hiệu ứng.
- **Editor renderer:** áp dụng decoration vào các đoạn văn bản.

Editor có thể sử dụng thư viện tokenizer, grammar regex, parser incremental hoặc language server. Việc chọn phụ thuộc vào độ phức tạp của DSL và yêu cầu về độ chính xác.

## 6. TextMate grammar và lexical highlighting

TextMate grammar là cách phổ biến để mô tả token highlighting bằng pattern, thường là regular expression. Nhiều editor hỗ trợ TextMate-compatible grammar hoặc có thể tái sử dụng grammar từ hệ sinh thái VS Code.

Một grammar thường định nghĩa:

- Scope name của toàn bộ ngôn ngữ.
- Pattern nhận diện keyword, comment, string, number và operator.
- Capture group để tô các phần con của một pattern.
- Begin/end rule cho vùng nhiều dòng như string hoặc block comment.
- Repository chứa các rule có thể tái sử dụng.
- Include để ghép grammar khác hoặc nhúng ngôn ngữ.

Ví dụ cấu trúc JSON rút gọn:

~~~json
{
  "scopeName": "source.exampledsl",
  "patterns": [
    { "include": "#comments" },
    { "include": "#strings" },
    { "include": "#keywords" },
    { "include": "#numbers" },
    { "include": "#identifiers" }
  ],
  "repository": {
    "keywords": {
      "patterns": [
        {
          "name": "keyword.control.exampledsl",
          "match": "\\b(rule|when|then|else|import)\\b"
        }
      ]
    },
    "numbers": {
      "patterns": [
        {
          "name": "constant.numeric.exampledsl",
          "match": "\\b[0-9]+(\\.[0-9]+)?\\b"
        }
      ]
    }
  }
}
~~~

Đây là ví dụ minh họa, không phải grammar hoàn chỉnh. Thứ tự pattern quan trọng vì một vùng đã được nhận diện là string hoặc comment thường không nên tiếp tục bị tô như keyword hoặc identifier.

### 6.1. Scope naming

Scope name mô tả vai trò của đoạn văn bản. Một số tên phổ biến trong TextMate:

- keyword.control
- keyword.operator
- entity.name.function
- entity.name.type
- variable
- variable.parameter
- constant.numeric
- string.quoted
- constant.character.escape
- comment.line
- comment.block
- punctuation.definition

Scope riêng của DSL có thể thêm hậu tố, ví dụ keyword.control.exampledsl. Tên scope có cấu trúc giúp theme hiện có áp dụng màu mặc định và theme chuyên biệt có thể ghi đè.

### 6.2. Pattern precedence

Với TextMate, pattern được thử theo cấu trúc grammar và thứ tự khai báo trong các trường hợp cạnh tranh. Một grammar cần đặt các vùng bao như comment và string đúng cách để keyword bên trong không bị tô nhầm.

Ví dụ:

~~~text
message = "when order.status == 'PAID'";
// when this rule is enabled
~~~

Từ when bên trong string và comment không phải keyword cú pháp. Grammar phải nhận diện string/comment trước hoặc dùng begin/end rule để giữ toàn bộ vùng trong scope tương ứng.

### 6.3. Begin/end rule cho vùng nhiều dòng

Block comment có thể bắt đầu ở một dòng và kết thúc ở dòng khác:

~~~text
/*
  Explanation of the policy.
  when and then here are plain comment text.
*/
~~~

Một rule chỉ tìm pattern một dòng có thể không giữ được trạng thái comment qua newline. Begin/end rule cho phép grammar ghi nhớ vùng đã mở cho đến khi gặp delimiter kết thúc.

## 7. Tree-sitter và highlighting dựa trên cú pháp

Tree-sitter là parser generator hỗ trợ parsing incremental. Nó tạo concrete syntax tree (CST) và có thể cập nhật cây khi văn bản thay đổi mà không cần parse lại toàn bộ tệp.

Với DSL có grammar phức tạp, Tree-sitter có thể giúp highlighter hiểu cấu trúc tốt hơn regex:

- Phân biệt identifier ở vị trí khai báo và tham chiếu.
- Tô tên hàm trong function call.
- Nhận diện keyword theo vị trí cú pháp.
- Xử lý biểu thức lồng nhau và dấu ngoặc.
- Cập nhật vùng bị ảnh hưởng khi người dùng sửa văn bản.

Một query Tree-sitter có thể capture các node:

~~~scheme
((rule_declaration
   name: (identifier) @function))

((type_declaration
   name: (type_identifier) @type))

((call_expression
   function: (identifier) @function))

((string_literal) @string)
((number_literal) @number)
((line_comment) @comment)
~~~

Tên node phụ thuộc grammar thực tế. Query minh họa cách capture node và gán highlight category.

### 7.1. Concrete syntax tree và AST

CST thường giữ nhiều chi tiết cú pháp như dấu ngoặc, dấu phân cách và comment. AST thường lược bỏ chi tiết chỉ phục vụ cú pháp và tập trung vào cấu trúc ngữ nghĩa.

Đối với highlighting, CST có thể hữu ích vì editor cần tô cả punctuation và token trivia. AST có thể hữu ích cho semantic highlighting nhưng cần source span để ánh xạ node về văn bản.

### 7.2. Error recovery

Khi người dùng đang gõ, tài liệu thường tạm thời không hợp lệ:

~~~text
rule discount {
    when order.total >
    then applyDiscount(
}
~~~

Parser phục vụ editor nên có khả năng tạo cây một phần và tiếp tục sau vùng lỗi. Nếu parser chỉ dừng ở lỗi đầu tiên, nhiều phần còn lại của tệp sẽ mất màu cho đến khi người dùng sửa xong.

## 8. Semantic tokens và Language Server Protocol

Language Server Protocol (LSP) cho phép editor nhận thông tin ngôn ngữ từ một language server. Ngoài diagnostics, completion và definition, server có thể gửi semantic tokens để tô màu theo ngữ nghĩa.

Một semantic token có thể mô tả:

- Loại token: namespace, type, class, parameter, variable, property, function, keyword hoặc enum member.
- Modifier: declaration, readonly, static, deprecated, abstract, async hoặc modification.
- Vị trí và độ dài của đoạn văn bản.

Ví dụ DSL:

~~~text
let threshold: Money = money(1000000, VND);

function isLarge(order: Order): Boolean {
    return order.total > threshold;
}
~~~

Semantic provider có thể phân biệt threshold ở khai báo là variable declaration; Money và Order là type; money là function; VND là enum member hoặc constant; order là parameter; total là property; và threshold ở biểu thức return là variable reference.

### 8.1. Semantic token encoding

Trong LSP, semantic tokens được gửi dưới dạng các nhóm số nguyên, thường gồm năm giá trị cho mỗi token:

1. Delta line: số dòng chênh lệch so với token trước.
2. Delta start: vị trí bắt đầu tương đối.
3. Length: độ dài token.
4. Token type: chỉ số trong legend do server công bố.
5. Token modifiers: bitset biểu diễn các modifier.

Server và client phải thống nhất token legend và quy ước vị trí. LSP có cơ chế position encoding; UTF-16 là mặc định truyền thống nếu không có thương lượng encoding khác. Nếu offset do parser cung cấp dùng code point hoặc byte, server cần chuyển đổi chính xác.

### 8.2. Full và delta semantic tokens

Server có thể gửi toàn bộ token của tài liệu hoặc chỉ phần thay đổi so với kết quả trước. Delta giúp giảm dữ liệu khi tài liệu lớn và người dùng chỉ sửa một vùng nhỏ.

Client có thể yêu cầu semantic tokens khi tài liệu thay đổi hoặc khi server báo kết quả cũ không còn hợp lệ. Server cần xử lý version của document để không áp dụng kết quả phân tích cũ lên nội dung mới hơn.

### 8.3. Kết hợp lexical và semantic tokens

Semantic tokens có thể ghi đè hoặc bổ sung lexical highlighting tùy editor. Cần thiết kế token type và theme sao cho kết quả không xung đột. Nếu server chưa sẵn sàng, lexical highlighter vẫn cung cấp màu cơ bản.

## 9. Tô màu theo ngữ cảnh của DSL

Một DSL có thể có từ khóa chỉ có ý nghĩa trong một vị trí:

~~~text
rule approval {
    when order.status == APPROVED
    then approve(order)
}
~~~

Trong ví dụ, rule mở đầu khai báo; when mở điều kiện; then mở hành động; APPROVED có thể là enum member; approve có thể là function.

Một highlighter chỉ dựa trên regex có thể tô approve và APPROVED giống nhau vì cả hai đều là identifier. Parser hoặc semantic provider có thể phân biệt chúng.

### 9.1. Soft keyword

Soft keyword chỉ được xem là keyword trong ngữ cảnh phù hợp:

~~~text
let match = "approved";

match order.status {
    case APPROVED -> approve(order)
}
~~~

Nếu match vừa là identifier vừa là từ khóa pattern matching, lexical highlighter đơn giản có thể tô sai một trong hai vị trí. Cách xử lý tốt hơn là dựa vào parse tree hoặc giới hạn keyword pattern theo ngữ cảnh có thể xác định.

### 9.2. Identifier có quy ước tên

Một số DSL dùng quy ước như PascalCase cho type và camelCase cho biến. Có thể dùng để tô màu dự phòng, nhưng không nên xem quy ước đặt tên là bằng chứng ngữ nghĩa. Một type hợp lệ có thể dùng tên chữ thường nếu grammar cho phép.

## 10. Ngôn ngữ nhúng và vùng interpolation

DSL đôi khi chứa một ngôn ngữ khác:

- SQL trong query block.
- JSON hoặc YAML trong cấu hình.
- Regex trong pattern literal.
- Template expression trong string.
- JavaScript trong action block.

Ví dụ:

~~~text
query activeCustomers {
    sql """
        SELECT id, name
        FROM customer
        WHERE status = 'ACTIVE'
    """
}
~~~

Editor nên tô SQL bên trong vùng sql theo grammar SQL, còn phần bên ngoài theo grammar DSL. Nếu dùng một highlighter duy nhất, keyword SELECT có thể bị coi là identifier hoặc keyword DSL không liên quan.

### 10.1. Injection grammar

TextMate hỗ trợ nhúng grammar khác vào một vùng được xác định. Grammar DSL nhận diện delimiter của vùng SQL, sau đó include scope của SQL cho nội dung bên trong.

### 10.2. Parser lồng nhau

Với parser như Tree-sitter, có thể định nghĩa external scanner hoặc node chứa nội dung embedded language rồi dùng injection query để parse vùng đó bằng grammar khác.

### 10.3. Interpolation

Chuỗi template có thể trộn văn bản và biểu thức:

~~~text
message = "Hello, " + customer.name;
~~~

Nếu DSL có cú pháp interpolation riêng, lexer cần phân biệt delimiter mở/đóng với phần văn bản chuỗi và chuyển sang parser biểu thức trong vùng đó. Highlighter phải quay lại string scope sau khi biểu thức kết thúc.

## 11. Comment, string và lexical state

Comment và string thường chứa từ trùng với keyword. Highlighter phải giữ trạng thái vùng để tránh tô nhầm:

~~~text
message = "then approve the request";

/*
  when order.total is large,
  then ask for review.
*/
~~~

Các trạng thái thường gặp:

- Normal code.
- Single-line comment.
- Block comment.
- Quoted string.
- Raw string.
- String escape.
- Template interpolation.
- Embedded language.

Với comment nhiều dòng, chuỗi nhiều dòng hoặc interpolation, grammar cần mô tả delimiter mở/đóng. Nếu delimiter có thể escape, highlighter phải áp dụng đúng quy tắc escape của DSL.

Một lỗi phổ biến là regex nhận diện keyword trước string. Khi đó chữ when trong nội dung chuỗi bị tô như keyword. Hãy xác định vùng bao trước, sau đó mới phân tích token bên trong nếu ngôn ngữ cho phép interpolation.

## 12. Theme và ánh xạ màu

Theme định nghĩa cách token scope hoặc semantic token được hiển thị. Một theme có thể quy định foreground color, font style như bold hoặc italic, underline hoặc strikethrough, và background decoration cho lỗi hoặc vùng được chọn.

Không nên gắn trực tiếp màu cố định vào grammar. Grammar mô tả vai trò; theme quyết định cách trình bày. Cách tách này cho phép cùng DSL hoạt động với theme sáng, tối, tương phản cao và theme do người dùng tự tạo.

Ví dụ bảng ánh xạ khái niệm:

| Token category | Vai trò theme |
|---|---|
| Keyword | Màu keyword |
| Type | Màu type/class |
| Function | Màu function |
| Variable | Màu variable |
| Parameter | Màu parameter |
| String | Màu string |
| Number | Màu numeric constant |
| Comment | Màu comment, thường giảm độ nổi bật |
| Invalid | Underline hoặc error decoration |
| Deprecated | Strikethrough hoặc màu cảnh báo nhẹ |

Màu cụ thể nên do theme quyết định để phù hợp với nền và sở thích người dùng.

## 13. Khả năng tiếp cận và tính dễ đọc

Không nên dùng màu sắc làm tín hiệu duy nhất. Người dùng có thể bị mù màu, dùng màn hình có độ tương phản thấp hoặc chọn theme đơn sắc.

Các nguyên tắc:

1. Duy trì độ tương phản đủ giữa chữ và nền.
2. Không dùng hai màu gần giống cho hai nhóm thường xuất hiện cạnh nhau.
3. Kết hợp màu với kiểu chữ hoặc decoration khi cần.
4. Không dùng màu đỏ/xanh đơn thuần để biểu thị trạng thái đúng/sai.
5. Cho phép người dùng đổi theme hoặc tắt một số semantic highlighting.
6. Kiểm tra ở theme sáng, tối và high-contrast.
7. Hạn chế số lượng category để người đọc không phải học một bảng màu quá lớn.

Ví dụ, deprecated API có thể dùng màu nhẹ kèm gạch ngang; lỗi có thể dùng underline dạng sóng thay vì chỉ đổi foreground. Nhờ đó, thông tin vẫn nhận biết được khi màu không hiển thị chính xác.

## 14. Hiệu năng và cập nhật incremental

Editor cần tô màu khi người dùng gõ, vì vậy highlighter phải phản hồi nhanh. Parse lại toàn bộ tài liệu sau mỗi phím có thể gây trễ với file lớn.

Các chiến lược:

- Tokenize theo dòng hoặc vùng.
- Chỉ phân tích lại phần bị ảnh hưởng.
- Dùng parser incremental như Tree-sitter.
- Cache trạng thái lexical ở ranh giới dòng.
- Debounce semantic request khi người dùng gõ liên tục.
- Hủy tác vụ cũ nếu document version đã thay đổi.
- Dùng semantic token delta thay vì gửi toàn bộ khi phù hợp.

### 14.1. Incremental lexing

Nếu người dùng sửa một dòng trong comment nhiều dòng, lexer có thể cần phân tích lại từ điểm trước đó có trạng thái ổn định cho đến khi trạng thái cuối khớp với bản cũ. Một thay đổi trong dấu mở comment có thể ảnh hưởng nhiều dòng phía sau.

Do đó, không phải mọi chỉnh sửa đều chỉ ảnh hưởng một dòng. Highlighter cần biết trạng thái bắt đầu/kết thúc của vùng để xác định phạm vi cần cập nhật.

### 14.2. Tránh kết quả cũ ghi đè kết quả mới

Language server có thể xử lý request bất đồng bộ. Nếu request cho document version 10 hoàn thành sau request version 11, editor không nên áp dụng token cũ lên văn bản mới. Cần gắn version hoặc result identifier với mỗi kết quả và bỏ kết quả lỗi thời.

### 14.3. Giới hạn chi phí

Regex có backtracking lớn hoặc parser không có giới hạn có thể làm editor treo khi gặp văn bản đặc biệt. Grammar cần tránh pattern quá phức tạp và parser cần có chiến lược xử lý input chưa hoàn chỉnh.

## 15. Diagnostic và tô màu lỗi

Syntax highlighting phân loại thành phần; diagnostics chỉ ra vấn đề. Hai chức năng có thể phối hợp:

- Lexer đánh dấu token không hợp lệ.
- Parser phát hiện cấu trúc sai.
- Type checker phát hiện kiểu không tương thích.
- Language server gửi diagnostic về editor.

Ví dụ:

~~~text
rule approval {
    when order.total >
    then approve(order)
}
~~~

Editor vẫn có thể tô keyword, identifier và dấu ngoặc; đồng thời gạch chân vùng biểu thức thiếu sau toán tử lớn hơn.

Không nên dùng màu syntax để thay thế diagnostics. Một token có màu keyword không có nghĩa nó được phép ở vị trí hiện tại. Tương tự, một tên có màu identifier không chứng minh tên đó đã được khai báo.

## 16. Tích hợp syntax highlighting vào editor

Các editor có cơ chế tích hợp khác nhau.

### 16.1. VS Code và editor tương thích TextMate

Một extension thường cung cấp:

- Language ID và file extension.
- TextMate grammar hoặc grammar tương thích.
- Language configuration cho comment, bracket và auto-closing pairs.
- Semantic token provider hoặc language server nếu cần.
- Theme scopes hoặc tài liệu theme mapping.

File extension giúp editor nhận diện loại tài liệu. Language ID liên kết tài liệu với grammar, formatter, language server và cấu hình ngôn ngữ.

### 16.2. Editor dùng Tree-sitter

Editor có thể tích hợp grammar Tree-sitter để parse incremental và dùng query capture node cho highlight. Cần đóng gói grammar, query và mapping theme theo API của editor.

### 16.3. Editor tự xây dựng

Một editor riêng có thể nhận document text, tokenize hoặc parse, tạo danh sách span cùng category, ánh xạ category qua theme, render decoration trong viewport và cập nhật span khi văn bản thay đổi.

Nên tách grammar khỏi renderer để có thể thay theme hoặc đổi editor framework mà không viết lại toàn bộ logic phân tích.

## 17. Bracket matching và vùng cấu trúc

Tô màu thường đi kèm bracket matching, tức làm nổi bật cặp dấu ngoặc tương ứng:

~~~text
rule approval {
    when (order.total > threshold) {
        approve(order)
    }
}
~~~

Editor cần biết các cặp delimiter: ngoặc tròn, ngoặc nhọn, ngoặc vuông và delimiter của string hoặc interpolation.

Bracket matching không phải syntax highlighting thuần túy nhưng dùng chung thông tin token hoặc parse tree. Nếu editor chỉ tìm ký tự ngoặc bằng văn bản, nó có thể ghép nhầm ngoặc nằm trong comment hoặc string.

Indentation guides, folding ranges và document outline cũng có thể dùng chung cấu trúc parse. Khi grammar được thiết kế tốt, một parser có thể phục vụ nhiều tính năng editor.

## 18. Kiểm thử syntax highlighting

Highlighting cần được kiểm thử với token đơn giản, ngữ cảnh lồng và tài liệu lỗi.

### 18.1. Token fixture

Tạo ví dụ chứa mỗi nhóm token:

~~~text
rule order-check {
    let count: Integer = 10;
    let enabled = true;
    let label = "APPROVED";
    // A comment
    when count >= 5 and enabled
    then approve(label)
}
~~~

Kiểm tra từng đoạn nguồn được gán đúng scope hoặc semantic token type.

### 18.2. Keyword bên trong string và comment

~~~text
message = "rule when then import";
// function and type are ordinary comment text
~~~

Các từ trùng keyword không được tô như keyword trong vùng string/comment.

### 18.3. Nested và multiline construct

Kiểm tra block comment, chuỗi nhiều dòng, template interpolation, block lồng nhau và dấu ngoặc trong literal.

### 18.4. Semantic token test

Tạo chương trình có variable, parameter, function, type, property và enum member. Xác nhận language server phân loại đúng khai báo và tham chiếu.

### 18.5. Incomplete document test

Kiểm tra khi người dùng đang gõ dở:

~~~text
rule example {
    when order.total >
~~~

Highlighter vẫn nên tô phần đã nhận diện được và tiếp tục sau vùng lỗi nếu parser hỗ trợ recovery.

### 18.6. Snapshot hoặc scope test

Với TextMate grammar, có thể lưu fixture và kết quả scope cho từng đoạn. Với Tree-sitter, kiểm tra query captures trên cây parse. Với LSP, kiểm tra token type, modifier, range và document version.

### 18.7. Theme test

Xem kết quả trên theme sáng, tối và tương phản cao. Kiểm tra category quan trọng có thể phân biệt mà không phụ thuộc vào một màu cụ thể.

## 19. Những lỗi thiết kế thường gặp

### Tô keyword bằng regex quá rộng

Regex nhận diện keyword bên trong identifier dài hơn hoặc trong string/comment. Dùng word boundary phù hợp và nhận diện vùng string/comment trước.

### Nhầm lexical với semantic

Tô mọi identifier viết hoa thành type có thể sai với tên biến hoặc hằng. Dùng quy ước tên chỉ như fallback, semantic provider cho thông tin chính xác.

### Không xử lý tài liệu chưa hoàn chỉnh

Parser dừng ngay tại lỗi đầu tiên khiến phần còn lại mất màu khi người dùng đang gõ. Dùng parser có recovery hoặc lexical fallback.

### Grammar không xử lý multiline

Comment hoặc string nhiều dòng bị kết thúc sai. Dùng begin/end state hoặc parser hiểu cấu trúc.

### Quên embedded language

SQL hoặc JSON bên trong DSL bị tô theo grammar ngoài. Xác định vùng nhúng và dùng grammar injection hoặc parser lồng nhau.

### Màu gắn cứng trong grammar

Grammar khó dùng với theme khác nhau. Hãy gán scope/category và để theme quyết định màu.

### Semantic tokens lỗi thời

Kết quả bất đồng bộ của document version cũ ghi đè token mới. Gắn version và loại bỏ response lỗi thời.

### Quá nhiều category

Mỗi loại tên có một màu riêng khiến theme rối và khó tiếp cận. Chỉ tạo nhóm có ý nghĩa đọc hiểu.

### Bỏ qua Unicode và offset

Range bị lệch khi có ký tự Unicode hoặc emoji. Thống nhất position encoding giữa parser, server và editor.

## 20. Quy trình xây dựng syntax highlighting cho DSL

Khi bổ sung highlighting cho một DSL, có thể thực hiện theo trình tự:

1. **Liệt kê token groups.** Xác định keyword, identifier, type, function, literal, operator, comment và delimiter.
2. **Đọc grammar của DSL.** Xác định keyword mềm, vùng lồng, string, comment và embedded language.
3. **Chọn mức phân tích.** Dùng TextMate/regex cho lexical highlighting, Tree-sitter hoặc parser cho cấu trúc, LSP cho semantic tokens.
4. **Định nghĩa scope/token legend.** Dùng tên category ổn định và có ý nghĩa.
5. **Thiết kế theme mapping.** Để màu do theme quyết định, hỗ trợ sáng/tối/high contrast.
6. **Xử lý trạng thái nhiều dòng.** Bảo đảm string, comment và interpolation không bị tô nhầm.
7. **Hỗ trợ mã chưa hoàn chỉnh.** Dùng error recovery và lexical fallback.
8. **Tích hợp incremental update.** Chỉ cập nhật vùng cần thiết và bỏ kết quả cũ.
9. **Thêm semantic highlighting.** Phân biệt symbol sau khi có AST hoặc language server.
10. **Kiểm thử fixture và theme.** Bao gồm token, nested syntax, error case, Unicode và performance.

Nên bắt đầu bằng một bộ lexical highlighting nhỏ nhưng chính xác. Khi người dùng cần phân biệt symbol và type, có thể bổ sung semantic tokens mà không phải thay đổi toàn bộ hệ thống theme.

## 21. Ví dụ end-to-end cho DSL

Xét chương trình:

~~~text
namespace sales;

type OrderStatus {
    PENDING,
    APPROVED
}

rule approval {
    when order.status == OrderStatus.PENDING
    then approve(order.id)
}
~~~

Lexical highlighter có thể nhận diện:

| Đoạn nguồn | Lexical category |
|---|---|
| namespace, type, rule, when, then | Keyword |
| sales, OrderStatus, OrderStatus.PENDING | Identifier hoặc type-like name |
| PENDING, APPROVED | Identifier/constant theo quy ước grammar |
| order, approve, id | Identifier |
| Dấu ngoặc, dấu chấm, dấu phẩy | Punctuation |

Sau khi parser và symbol resolver chạy, semantic highlighter có thể điều chỉnh:

| Đoạn nguồn | Semantic category |
|---|---|
| OrderStatus | Type |
| PENDING và APPROVED | Enum member |
| order | Variable hoặc parameter |
| status và id | Property |
| approve | Function |
| sales | Namespace |

Pipeline tổng hợp:

1. Lexer nhận diện keyword, identifier và punctuation.
2. Parser tạo CST hoặc AST.
3. Symbol resolver phân loại type, enum, property, function và namespace.
4. Language server phát semantic tokens.
5. Editor kết hợp lexical scopes với semantic tokens.
6. Theme ánh xạ category thành màu và style.
7. Khi document thay đổi, parser và semantic provider cập nhật vùng bị ảnh hưởng.

Kết quả là editor có thể cung cấp màu cơ bản ngay lập tức và màu ngữ nghĩa chính xác hơn sau khi phân tích.

## 22. Kết luận

Tô màu cú pháp giúp người dùng đọc DSL bằng cách phân biệt keyword, identifier, type, function, literal, operator, comment và các thành phần khác. Lexical highlighting dựa trên pattern hoặc token; semantic highlighting dựa trên parser, symbol table và language server để hiểu vai trò thực tế của tên.

TextMate grammar phù hợp với lexical highlighting nhẹ và dễ tích hợp; Tree-sitter hỗ trợ parsing incremental và highlight theo cấu trúc; LSP semantic tokens bổ sung thông tin về symbol và type. Một editor có thể kết hợp các cơ chế này, đồng thời xử lý string, comment, embedded language, interpolation, tài liệu chưa hoàn chỉnh và cập nhật bất đồng bộ.

Khi thiết kế, hãy tách grammar khỏi theme, dùng category có ý nghĩa, giữ kết quả nhất quán với parser, hỗ trợ theme dễ tiếp cận và kiểm thử cả mã hợp lệ lẫn mã đang được gõ dở. Tô màu tốt làm DSL dễ học và dễ bảo trì hơn, nhưng luôn là một lớp hỗ trợ đọc hiểu bên cạnh phân tích cú pháp và kiểm tra ngữ nghĩa.
