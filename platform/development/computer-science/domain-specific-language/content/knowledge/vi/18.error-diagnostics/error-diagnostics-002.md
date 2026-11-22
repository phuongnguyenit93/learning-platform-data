# Lỗi cú pháp

## 1. Lỗi cú pháp trong DSL là gì?

Lỗi cú pháp (syntax error) xảy ra khi chuỗi token của chương trình không tuân theo cấu trúc mà ngữ pháp (grammar) của ngôn ngữ cho phép. Lexer có thể đã nhận diện được các token, nhưng parser không thể ghép chúng thành một cấu trúc hợp lệ theo grammar.

Ví dụ, một DSL khai báo rule bằng cặp ngoặc nhọn:

~~~text
rule discount {
    when order.total > 1000000
    then applyDiscount(10);
}
~~~

Nếu thiếu dấu ngoặc mở:

~~~text
rule discount
    when order.total > 1000000
    then applyDiscount(10);
}
~~~

Parser có thể báo lỗi vì gặp từ khóa when ở vị trí mà grammar yêu cầu dấu mở block. Vấn đề nằm ở cấu trúc câu lệnh, không phải ở ý nghĩa nghiệp vụ của điều kiện.

Một ví dụ khác:

~~~text
let total = price + ;
~~~

Sau toán tử cộng, parser cần một biểu thức nhưng gặp dấu chấm phẩy. Chuỗi token không thể tạo thành một biểu thức gán hợp lệ.

Lỗi cú pháp cần được phân biệt với:

- **Lỗi từ vựng (lexical error):** một ký tự hoặc lexeme không khớp với token hợp lệ, ví dụ ký tự @ không được DSL hỗ trợ.
- **Lỗi cú pháp (syntax error):** các token hợp lệ xuất hiện sai thứ tự hoặc thiếu thành phần theo grammar.
- **Lỗi ngữ nghĩa tĩnh (static semantic error):** cấu trúc đúng nhưng tên, kiểu hoặc ràng buộc không hợp lệ, ví dụ dùng biến chưa khai báo.
- **Lỗi runtime:** chương trình đã được phân tích và kiểm tra nhưng thất bại khi chạy, ví dụ dịch vụ ngoài không phản hồi.

Phân loại đúng giúp compiler đưa ra thông báo phù hợp và người viết biết nên sửa token, cấu trúc hay quy tắc nghiệp vụ.

## 2. Vai trò của grammar và parser

Grammar mô tả những chuỗi token nào được xem là chương trình hợp lệ. Parser đọc token do lexer phát ra và kiểm tra chúng theo các quy tắc đó.

Một grammar giản lược cho DSL rule có thể viết:

~~~ebnf
program     = { ruleDeclaration } ;
ruleDeclaration
            = "rule", identifier, "{",
              "when", expression,
              "then", action,
              "}" ;
action      = identifier, "(", [ argumentList ], ")", ";" ;
argumentList
            = expression, { ",", expression } ;
~~~

Grammar quy định một rule có từ khóa rule, tên, block, điều kiện when, hành động then và dấu đóng. Nếu người dùng viết then trước when, parser có thể phát hiện thứ tự sai.

Quy trình phát hiện lỗi cú pháp thường diễn ra như sau:

~~~mermaid
flowchart TD
    A["Mã nguồn DSL"] --> B["Lexer"]
    B --> C["Chuỗi token"]
    C --> D["Parser"]
    D --> E{"Có khớp grammar?"}
    E -->|Có| F["AST"]
    E -->|Không| G["Syntax diagnostic"]
    G --> H["Recovery nếu được hỗ trợ"]
    H --> D
~~~

Parser có thể dùng các chiến lược như recursive descent, LL, LR, LALR, PEG hoặc parser generator. Cách triển khai khác nhau nhưng mục tiêu chung là xác định cấu trúc hợp lệ và chỉ ra nơi đầu vào không phù hợp.

Parser thường phát hiện lỗi ở vị trí token đầu tiên không thể tiếp tục theo trạng thái hiện tại. Vị trí này không phải lúc nào cũng chính là nơi người dùng bắt đầu sai. Ví dụ, dấu chấm phẩy có thể là token khiến parser nhận ra lỗi, trong khi nguyên nhân thực sự là người viết quên một biểu thức trước đó.

## 3. Những nguyên nhân phổ biến gây lỗi cú pháp

Lỗi cú pháp thường đến từ một số nhóm:

| Nhóm lỗi | Ví dụ | Vấn đề |
|---|---|---|
| Thiếu token bắt buộc | Thiếu dấu đóng ngoặc hoặc block | Cấu trúc chưa được đóng |
| Thừa token | Có thêm dấu phẩy hoặc chấm phẩy | Token không được phép ở vị trí đó |
| Sai thứ tự | Viết then trước when | Các thành phần không theo grammar |
| Sai dấu phân cách | Dùng dấu hai chấm thay vì dấu bằng | Token không đúng loại mà grammar yêu cầu |
| Biểu thức chưa hoàn chỉnh | price + ; | Thiếu toán hạng |
| Khối lồng nhau sai | Đóng block ngoài trước block trong | Cấu trúc lồng không cân bằng |
| Danh sách sai | Hai dấu phẩy liên tiếp | Thiếu phần tử giữa các dấu phân cách |
| Khai báo thiếu thành phần | function total( | Thiếu tham số đóng hoặc thân hàm |
| Cú pháp literal sai | Chuỗi không có dấu nháy đóng | Token hoặc cấu trúc literal không hoàn chỉnh |

Ví dụ thiếu dấu đóng:

~~~text
rule approval {
    when order.total > 5000000
    then approve();
~~~

Khi tới cuối tệp, parser vẫn đang chờ dấu đóng block. Diagnostic nên nói rõ đang thiếu dấu đóng và vị trí block được mở.

Ví dụ sai danh sách:

~~~text
callService(order,, customer);
~~~

Sau dấu phẩy đầu tiên, grammar yêu cầu một biểu thức đối số. Dấu phẩy thứ hai xuất hiện ngay lập tức nên parser báo thiếu đối số hoặc token không mong đợi.

## 4. Phân biệt lỗi cú pháp với lỗi từ vựng và lỗi ngữ nghĩa

Ba giai đoạn đầu của xử lý ngôn ngữ có trách nhiệm khác nhau:

| Giai đoạn | Ví dụ đầu vào | Loại lỗi |
|---|---|---|
| Lexer | let value = 12@; khi @ không hợp lệ | Lỗi từ vựng |
| Parser | let value = price + ; | Lỗi cú pháp |
| Static checker | let value: Integer = "hello"; | Lỗi kiểu |

Một literal chuỗi chưa đóng có thể được lexer báo là lỗi từ vựng, vì lexer không thể tạo STRING_LITERAL hoàn chỉnh. Trong một thiết kế khác, lexer có thể phát token lỗi và parser tiếp tục báo cấu trúc không hoàn chỉnh. Công cụ nên tránh tạo nhiều diagnostic trùng nhau cho cùng một nguyên nhân.

Ví dụ cú pháp đúng nhưng ngữ nghĩa sai:

~~~text
let total = unknownPrice + tax;
~~~

Nếu grammar cho phép biểu thức cộng, parser tạo AST thành công. Static checker mới phát hiện unknownPrice không được khai báo.

Ví dụ cú pháp và ngữ nghĩa tĩnh đều đúng nhưng runtime có thể lỗi:

~~~text
let average = total / itemCount;
~~~

Nếu itemCount có kiểu số hợp lệ, phép chia vượt qua kiểm tra kiểu. Khi itemCount bằng 0 lúc chạy, hệ thống vẫn cần xử lý lỗi chia cho 0 theo ngữ nghĩa động.

## 5. Parser báo lỗi ở đâu?

Parser thường phát hiện lỗi khi token hiện tại không nằm trong tập token có thể xuất hiện tiếp theo tại trạng thái đang phân tích. Tập token đó thường được gọi là expected set hoặc tập token kỳ vọng.

Ví dụ:

~~~text
let amount = calculateTax(order;
~~~

Sau khi đọc order, parser đang ở trong danh sách đối số và kỳ vọng dấu đóng ngoặc hoặc dấu phẩy. Nhưng nó gặp dấu chấm phẩy. Diagnostic có thể là:

~~~text
Syntax error: unexpected ';'.
Expected ')' or ',' after argument expression.
~~~

Thông báo tốt nên cung cấp:

- Token hoặc đoạn nguồn gây lỗi.
- Vị trí lỗi trong tệp.
- Một số token hoặc cấu trúc đang được kỳ vọng.
- Ngữ cảnh cú pháp, chẳng hạn danh sách tham số hoặc biểu thức.
- Gợi ý sửa nếu có thể xác định với độ tin cậy cao.

Không nên liệt kê toàn bộ token có thể xuất hiện trong grammar nếu danh sách quá dài. Hãy chọn những lựa chọn hữu ích nhất đối với người viết.

## 6. Vị trí nguồn và source span

Diagnostic cần trỏ tới vị trí có ý nghĩa trong mã nguồn. Một vị trí đơn lẻ thường gồm:

- Tên tệp hoặc định danh tài liệu.
- Số dòng.
- Số cột.
- Offset bắt đầu và kết thúc trong văn bản.

Một source span biểu diễn đoạn nguồn từ vị trí bắt đầu đến vị trí kết thúc. Với lỗi thiếu token, không có lexeme sai để gạch chân; compiler có thể trỏ vào vị trí chèn token dự kiến hoặc token kế tiếp.

Ví dụ:

~~~text
ERROR SYN-004: Expected ')' after function arguments.
  at rules/payment.dsl:8:31
  authorizePayment(order, amount;
                                ^
  Hint: Add ')' before ';'.
~~~

Ở đây dấu chấm phẩy là vị trí parser nhận ra danh sách đối số chưa được đóng. Gợi ý thêm dấu đóng ngoặc trước dấu chấm phẩy có thể hữu ích nếu cấu trúc còn lại rõ ràng.

### 6.1. Đơn vị cột và Unicode

Compiler và editor cần thống nhất cách tính cột: byte, Unicode code point, UTF-16 code unit hay cột hiển thị. Một ký tự Unicode có thể chiếm nhiều code unit hoặc được tạo bởi nhiều code point. Nếu lexer và editor dùng đơn vị khác nhau mà không chuyển đổi, dấu chỉ vị trí có thể lệch.

Với DSL hỗ trợ tab, cần quyết định tab được tính là một cột hay mở rộng tới tab stop. Với newline, cần hỗ trợ định dạng LF và CRLF nhất quán.

### 6.2. Lỗi ở cuối tệp

Khi parser cần một token nhưng đã hết đầu vào, diagnostic nên nói rõ token nào còn thiếu:

~~~text
ERROR SYN-002: Unexpected end of file.
Expected '}' to close rule 'discount' opened at line 3.
~~~

Thông báo này có ích hơn Unexpected EOF vì nó liên kết lỗi với block chưa đóng.

## 7. Thiết kế thông báo lỗi dễ hiểu

Một thông báo lỗi nên ngắn gọn, cụ thể và hướng tới hành động. Có thể dùng cấu trúc:

1. Mã lỗi ổn định.
2. Mô tả điều parser gặp phải.
3. Vị trí trong nguồn.
4. Token hoặc cấu trúc kỳ vọng.
5. Gợi ý sửa, nếu có căn cứ.

Ví dụ:

~~~text
SYN-011: Missing expression after '+'.
  at pricing.dsl:14:24
  discount = subtotal + ;
                         ^
  Expected a value, identifier, function call or parenthesized expression.
  Hint: Add the discount amount or remove the '+' operator.
~~~

Thông báo không nên:

- Chỉ ghi Syntax error mà không có vị trí.
- Dùng thuật ngữ parser nội bộ mà người viết DSL không hiểu.
- Đưa ra gợi ý chắc chắn khi có nhiều cách sửa hợp lệ.
- Báo hàng chục lỗi dây chuyền bắt nguồn từ một dấu ngoặc thiếu.
- Hiển thị toàn bộ tệp trong mỗi diagnostic.

Nếu DSL được dùng bởi người làm nghiệp vụ, thông báo có thể dùng tên khái niệm của miền. Ví dụ, “Thiếu biểu thức điều kiện sau when” dễ hiểu hơn “No viable alternative at input”.

## 8. Mã lỗi và cấu trúc diagnostic

Một compiler nên có mã lỗi ổn định để IDE, CI và công cụ khác có thể phân loại. Nội dung message có thể được cải thiện hoặc dịch mà không làm thay đổi mã lỗi.

Ví dụ mô hình:

~~~java
public enum DiagnosticSeverity {
    ERROR,
    WARNING,
    INFO
}

public record SourcePosition(
        String file,
        int line,
        int column,
        int offset) {
}

public record SourceSpan(
        SourcePosition start,
        SourcePosition end) {
}

public record Diagnostic(
        String code,
        DiagnosticSeverity severity,
        String message,
        SourceSpan span,
        List<String> hints) {
}
~~~

Đây là mô hình minh họa. Compiler thực tế có thể thêm related locations, expected tokens, dữ liệu cấu trúc cho quick fix và liên kết tài liệu.

Nên phân biệt:

- **Diagnostic code:** định danh ổn định như SYN-011.
- **Severity:** error, warning hoặc info.
- **Message:** nội dung giải thích cho con người.
- **Primary span:** vị trí chính của vấn đề.
- **Related span:** vị trí liên quan, ví dụ dấu mở block chưa được đóng.
- **Hint hoặc fix:** gợi ý hoặc chỉnh sửa tự động có thể áp dụng.

Mã lỗi không nên phụ thuộc vào số dòng hoặc vị trí cụ thể trong một phiên bản grammar. Nó là một phần của giao diện công cụ.

## 9. Expected token và thông tin ngữ cảnh

Khi parser báo đang chờ token, thông tin đó chỉ hữu ích nếu được trình bày trong ngữ cảnh. Ví dụ, sau function calculate(, người viết có thể cần tên tham số hoặc dấu đóng ngoặc, tùy grammar cho phép danh sách rỗng hay không.

Một diagnostic có thể mô tả:

~~~text
SYN-021: Expected a parameter declaration or ')'.
  at functions.dsl:5:28
  function calculate(
                           ^
  A parameter has the form: name: Type
~~~

Parser có thể tạo thông tin expected token từ trạng thái hiện tại. Với parser LL, thông tin này thường liên quan đến FIRST set của các lựa chọn tiếp theo. Với parser LR, parser có thể biết các terminal hợp lệ từ action table của trạng thái hiện tại.

Không nên phơi bày trực tiếp cấu trúc nội bộ của parser trong thông báo người dùng. Hãy chuyển expected token thành nhóm khái niệm như tên tham số, biểu thức, dấu đóng block hoặc tên kiểu.

## 10. Phục hồi sau lỗi cú pháp

Trong một compiler đơn giản, parser có thể dừng ngay tại lỗi đầu tiên. Nhưng IDE, editor và công cụ kiểm tra thường cần tiếp tục phân tích để hiển thị nhiều lỗi trong một lần. Kỹ thuật này gọi là error recovery.

Mục tiêu của recovery:

- Tránh dừng toàn bộ phân tích vì một lỗi nhỏ.
- Giữ được cấu trúc của các phần chương trình còn hợp lệ.
- Hạn chế diagnostic dây chuyền.
- Đưa parser về trạng thái có thể tiếp tục xử lý.

Recovery không có nghĩa chương trình lỗi vẫn được xem là hợp lệ. AST được tạo sau khi phục hồi có thể chứa error node hoặc phần chưa xác định và không nên được thực thi như chương trình hoàn chỉnh.

## 11. Panic-mode recovery

Panic-mode recovery là kỹ thuật phổ biến: khi gặp lỗi, parser bỏ qua token cho đến một token đồng bộ (synchronization token) mà nó có thể tiếp tục phân tích an toàn.

Ví dụ, nếu mỗi khai báo cấp cao kết thúc bằng dấu chấm phẩy, parser có thể bỏ qua token đến dấu chấm phẩy tiếp theo:

~~~text
let first = 10;
let broken = + * / ;
let second = 20;
~~~

Sau khi phát hiện biểu thức của broken không hợp lệ, parser bỏ qua phần còn lại đến dấu chấm phẩy, rồi tiếp tục tại khai báo second.

Các token đồng bộ thường dùng:

- Dấu chấm phẩy kết thúc câu lệnh.
- Dấu đóng block.
- Từ khóa bắt đầu khai báo mới như rule, function hoặc import.
- Dấu phân cách cấp cao của danh sách.

Chọn token đồng bộ cần dựa trên cấu trúc DSL. Nếu parser đồng bộ ở dấu đóng block nhưng đang ở trong một block lồng nhau, nó có thể bỏ qua quá nhiều hoặc đóng nhầm block. Parser cần theo dõi mức lồng hoặc chọn điểm phục hồi phù hợp.

### 11.1. Ví dụ phục hồi trong DSL khai báo

~~~text
rule first {
    when order.total > 1000
    then approve();
}

rule broken {
    when order.total >
    then reject();
}

rule third {
    when order.status == "PAID"
    then archive();
}
~~~

Parser có thể báo thiếu biểu thức sau toán tử lớn hơn trong rule broken, sau đó đồng bộ tại dấu đóng block của rule đó và tiếp tục parse rule third. Nhờ vậy, người viết thấy được lỗi trong rule broken mà vẫn nhận được cấu trúc của phần sau.

## 12. Phrase-level recovery và error production

### 12.1. Phrase-level recovery

Phrase-level recovery cố gắng sửa cục bộ luồng token để parser có thể tiếp tục. Các thao tác thường gặp:

- Chèn một token bị thiếu.
- Xóa một token thừa.
- Thay token hiện tại bằng token khác.
- Bỏ qua một token rồi thử phân tích tiếp.

Ví dụ:

~~~text
let total = calculateTax(order;
~~~

Parser có thể giả định người viết quên dấu đóng ngoặc và chèn token này trước dấu chấm phẩy trong luồng phân tích. Nó vẫn phải phát diagnostic để người dùng biết nguồn có lỗi.

Chèn hoặc xóa token tự động chỉ nên thực hiện khi sửa đổi có độ tin cậy cao. Nếu có nhiều khả năng sửa, parser nên báo lỗi và để người dùng quyết định.

### 12.2. Error production

Grammar có thể định nghĩa một số cấu trúc sai thường gặp để parser nhận diện và đưa ra thông báo chuyên biệt. Ví dụ, nếu DSL yêu cầu when expression then action, grammar có thể có nhánh nhận diện trường hợp thiếu expression sau when.

~~~ebnf
ruleBody = "when", expression, "then", action
         | "when", "then", action ;
~~~

Nhánh thứ hai không biểu diễn chương trình hợp lệ; nó giúp parser nhận ra lỗi cụ thể “thiếu điều kiện sau when”. Sau khi tạo diagnostic, AST có thể chứa node lỗi để công cụ tiếp tục phân tích.

Error production hữu ích với lỗi phổ biến và có cách giải thích rõ. Không nên bổ sung quá nhiều nhánh lỗi vào grammar vì có thể làm grammar phức tạp hoặc tạo xung đột với cú pháp hợp lệ.

## 13. Tránh lỗi dây chuyền

Một lỗi cú pháp có thể làm parser hiểu sai phần còn lại của tệp. Ví dụ, thiếu dấu đóng block ở đầu có thể khiến mọi khai báo phía sau bị xem là nằm trong block chưa đóng.

Để giảm lỗi dây chuyền:

1. Chọn điểm phục hồi gần nhất nhưng vẫn có cấu trúc đáng tin cậy.
2. Ưu tiên đồng bộ tại ranh giới câu lệnh hoặc khai báo.
3. Dùng error node để đánh dấu vùng không phân tích được.
4. Không chạy các bước ngữ nghĩa sâu trên phần AST đã hỏng nếu điều đó tạo thêm lỗi giả.
5. Gộp hoặc loại bỏ diagnostic trùng nguyên nhân.
6. Giữ vị trí lỗi gốc để các bước sau không báo lỗi ở vị trí sai lệch.

Ví dụ, nếu parser không hiểu một khai báo, type checker không nên tiếp tục báo rằng mọi tên được khai báo trong đó đều chưa tồn tại. Nó nên biết vùng đó đã chứa lỗi cú pháp và giới hạn các diagnostic phát sinh từ vùng đó.

## 14. Lỗi cú pháp trong các cấu trúc thường gặp

### 14.1. Biểu thức

Biểu thức thường có lỗi do thiếu toán hạng, thiếu dấu ngoặc hoặc sai độ ưu tiên:

~~~text
price + * tax
(price + tax
price > 10 and
~~~

Parser nên chỉ ra toán tử hoặc dấu phân cách liên quan. Với biểu thức dài, có thể trỏ vào token bất ngờ và nêu loại biểu thức đang được kỳ vọng.

### 14.2. Danh sách tham số và đối số

~~~text
calculateTax(order, );
function calculate(, rate: Decimal) { ... }
~~~

Grammar cần xác định danh sách rỗng có hợp lệ không, dấu phẩy cuối có được phép không và mỗi phần tử phải có cấu trúc nào.

### 14.3. Block lồng nhau

~~~text
rule outer {
    if condition {
        approve();
    }
}
~~~

Thiếu hoặc đảo thứ tự dấu đóng có thể làm parser mất đồng bộ. Diagnostic nên liên kết dấu mở với dấu đóng tương ứng nếu parser có thể xác định.

### 14.4. Khai báo và import

~~~text
import from sales.orders;
type Order {
    id:
}
~~~

Parser có thể báo thiếu tên sau import hoặc thiếu kiểu sau dấu hai chấm. Với cú pháp khai báo, thông báo nên nêu thành phần bắt buộc thay vì chỉ báo token không hợp lệ.

### 14.5. Template và interpolation

~~~text
message = "Hello, ${customer.name}!";
~~~

Nếu DSL hỗ trợ interpolation, parser phải nhận biết biểu thức bên trong và dấu đóng tương ứng. Khi thiếu dấu đóng, diagnostic nên trỏ tới vị trí gần dấu nháy kết thúc hoặc EOF, đồng thời nêu interpolation đã mở ở đâu.

## 15. Lỗi cú pháp trong DSL cấu hình và DSL nhúng

DSL cấu hình có thể dùng YAML, JSON, HCL hoặc cú pháp riêng. Các lỗi cú pháp phụ thuộc định dạng:

- YAML: thụt lề không nhất quán, dấu hai chấm hoặc dấu gạch ngang sai vị trí.
- JSON: thiếu dấu phẩy, dấu ngoặc kép hoặc dấu ngoặc đóng; JSON chuẩn không cho phép comment.
- HCL: block hoặc biểu thức không đóng.
- DSL nhúng trong Java/Kotlin: lỗi có thể được compiler của ngôn ngữ chủ phát hiện trước khi thư viện DSL chạy.

Với DSL nhúng dùng fluent API:

~~~java
RuleDsl.ruleSet()
    .rule("discount")
    .when(orderTotal().greaterThan(limit))
    .then(applyDiscount(10))
    .build();
~~~

Một dấu ngoặc đóng thiếu có thể được compiler Java báo lỗi. Trong trường hợp này, lỗi cú pháp thuộc ngôn ngữ chủ. Nếu DSL được biểu diễn dưới dạng chuỗi:

~~~java
engine.compile("rule discount { when order.total > then applyDiscount(10); }");
~~~

thì parser của DSL mới chịu trách nhiệm báo lỗi. API nên trả về diagnostic có vị trí bên trong chuỗi DSL và nếu có thể ánh xạ tới vị trí trong tệp chứa chuỗi.

## 16. Gợi ý sửa lỗi (quick fix)

IDE hoặc compiler có thể đề xuất quick fix khi cách sửa có độ tin cậy cao:

| Lỗi | Quick fix có thể đề xuất |
|---|---|
| Thiếu dấu đóng ngoặc trước dấu chấm phẩy | Chèn dấu đóng ngoặc |
| Thiếu dấu đóng block ở cuối | Chèn dấu đóng block tại vị trí phù hợp |
| Dấu hai chấm dùng nhầm thay cho dấu bằng | Đề xuất thay token nếu grammar và ngữ cảnh rõ |
| Thiếu dấu phẩy giữa hai đối số | Chèn dấu phẩy |
| Thiếu biểu thức sau toán tử | Gợi ý hoàn thiện biểu thức, không tự đoán giá trị |

Quick fix nên đi kèm mô tả thay đổi và chỉ áp dụng lên source span xác định. Không nên tự động thay đổi logic nghiệp vụ hoặc tự điền giá trị mà compiler không thể biết.

Một diagnostic có thể cung cấp nhiều lựa chọn sửa:

~~~text
SYN-018: Expected an expression after 'when'.
  at rules/approval.dsl:6:10
  Possible fixes:
    - Add a condition expression.
    - Remove the incomplete 'when' clause.
~~~

Người dùng chọn cách phù hợp với ý định của họ.

## 17. Thiết kế parser để chẩn đoán tốt

Chất lượng diagnostic phụ thuộc vào thiết kế grammar và parser, không chỉ vào câu chữ của thông báo lỗi.

Một parser thân thiện với người dùng nên:

- Giữ source span cho token và node.
- Biết tập token hợp lệ tiếp theo tại mỗi trạng thái.
- Phân biệt EOF với token bất ngờ.
- Có điểm đồng bộ hợp lý cho từng loại cấu trúc.
- Ghi nhận dấu mở block hoặc danh sách để báo vị trí thiếu dấu đóng.
- Hạn chế thông báo trùng lặp.
- Cho phép công cụ nhận diagnostic ở định dạng máy đọc được.

Với grammar mơ hồ hoặc có nhiều cách phân tích, parser có thể chọn một nhánh rồi báo lỗi muộn. Vì vậy, thiết kế grammar rõ ràng, xử lý precedence và associativity nhất quán cũng giúp diagnostic dễ hiểu hơn.

Ví dụ, grammar biểu thức nên quy định độ ưu tiên:

~~~ebnf
expression = comparison ;
comparison = additive, [ comparisonOperator, additive ] ;
additive   = multiplicative, { ("+" | "-"), multiplicative } ;
multiplicative
           = unary, { ("*" | "/"), unary } ;
unary      = [ "-" | "!" ], primary ;
primary    = literal | identifier | "(", expression, ")" ;
~~~

Nếu precedence không được xác định, parser có thể tạo cấu trúc khác nhau cho cùng biểu thức hoặc không biết cách phục hồi khi gặp chuỗi toán tử.

## 18. Kiểm thử xử lý lỗi cú pháp

Parser cần được kiểm thử với cả chương trình hợp lệ và chương trình cố ý sai. Các nhóm test hữu ích:

### 18.1. Test một lỗi đơn

Mỗi test chỉ chứa một lỗi cú pháp chính, ví dụ thiếu dấu ngoặc, thiếu biểu thức hoặc sai thứ tự từ khóa. Test xác nhận mã lỗi, vị trí và thông điệp phù hợp.

### 18.2. Test nhiều lỗi

Tạo tệp có nhiều lỗi ở các khai báo khác nhau để kiểm tra parser có phục hồi và tiếp tục phân tích phần sau hay không.

### 18.3. Test EOF và cấu trúc lồng

Kiểm tra block, danh sách, chuỗi và interpolation chưa đóng tại cuối tệp. Xác nhận diagnostic trỏ tới vị trí hợp lý và nêu thành phần còn thiếu.

### 18.4. Test lỗi từ vựng đi kèm

Kết hợp ký tự không hợp lệ với lỗi cú pháp để bảo đảm lexer và parser không tạo diagnostic trùng hoặc dây chuyền quá mức.

### 18.5. Golden test cho diagnostic

Lưu kết quả diagnostic mong đợi gồm mã lỗi, severity, source span và message. Khi grammar hoặc parser thay đổi, diff cho thấy thông báo đã thay đổi ra sao.

### 18.6. Test recovery

Sau một lỗi, xác nhận parser vẫn nhận diện được khai báo hợp lệ tiếp theo. Điều này quan trọng với IDE và công cụ kiểm tra cả tệp.

## 19. Những lỗi thiết kế thường gặp

### Chỉ báo “Syntax error”

Thông báo chung chung không cho biết vị trí, token gặp phải hoặc cấu trúc kỳ vọng. Hãy cung cấp source span và ngữ cảnh.

### Đổ toàn bộ expected token ra màn hình

Một danh sách dài các token nội bộ gây khó hiểu. Hãy nhóm chúng thành khái niệm có ý nghĩa đối với người dùng.

### Dừng ngay ở mọi lỗi

Fail-fast phù hợp với một số compiler batch, nhưng IDE cần recovery để tìm lỗi tiếp theo. Hãy chọn chính sách theo mục tiêu công cụ.

### Phục hồi quá tham lam

Tự chèn hoặc xóa nhiều token có thể khiến parser hiểu sai ý định. Chỉ áp dụng quick fix khi có độ tin cậy cao và luôn hiển thị thay đổi.

### Không phân biệt lỗi gốc với lỗi dây chuyền

Một dấu ngoặc thiếu có thể gây hàng loạt lỗi giả. Dùng error node và điểm đồng bộ để giới hạn ảnh hưởng.

### Không lưu source location

Diagnostic không thể chỉ đúng chỗ nếu lexer/parser không giữ offset, dòng và cột. Hãy thiết kế source span từ đầu pipeline.

### Để grammar quá mơ hồ

Grammar không rõ precedence hoặc thứ tự cấu trúc làm parser khó đưa ra thông báo cụ thể. Hãy viết grammar rõ và định nghĩa các điểm phục hồi.

### Đưa lỗi ngữ nghĩa vào nhóm lỗi cú pháp

Tên chưa khai báo hoặc sai kiểu không phải lỗi grammar. Phân loại đúng giúp người dùng và công cụ chọn cách xử lý phù hợp.

## 20. Quy trình xử lý và sửa lỗi cú pháp

Khi gặp lỗi cú pháp trong DSL, người viết có thể làm theo các bước:

1. **Đọc vị trí lỗi.** Mở đúng tệp, dòng và cột mà diagnostic cung cấp.
2. **Xem token gây lỗi.** Xác định parser gặp token nào và token nào được kỳ vọng.
3. **Kiểm tra cấu trúc gần đó.** Xem dấu ngoặc, dấu phân cách, thứ tự keyword và biểu thức trước vị trí lỗi.
4. **Kiểm tra cấu trúc lồng.** Đối chiếu các cặp ngoặc và block được mở trước đó.
5. **Sửa lỗi gốc.** Ưu tiên lỗi đầu tiên nếu các lỗi sau có thể là hệ quả.
6. **Chạy parser lại.** Xác nhận lỗi đã hết và xem còn diagnostic độc lập nào khác.
7. **Kiểm tra ngữ nghĩa sau khi parse thành công.** Một chương trình đúng cú pháp vẫn có thể sai tên, kiểu hoặc quy tắc miền.

Với người phát triển DSL, quy trình thiết kế nên gồm:

1. Định nghĩa grammar và precedence rõ ràng.
2. Giữ source span xuyên suốt lexer và parser.
3. Xây dựng mã lỗi cùng cấu trúc diagnostic ổn định.
4. Chọn chiến lược recovery theo mục tiêu compiler hoặc IDE.
5. Định nghĩa token đồng bộ cho từng cấu trúc.
6. Thêm error production cho những lỗi thường gặp và có cách giải thích rõ.
7. Kiểm thử cả lỗi đơn, nhiều lỗi, EOF và phục hồi.
8. Cung cấp quick fix chỉ khi có thể xác định thay đổi an toàn.

## 21. Kết luận

Lỗi cú pháp xuất hiện khi chuỗi token không phù hợp với grammar của DSL. Parser cần chỉ ra token hoặc vị trí khiến cấu trúc không thể tiếp tục, giải thích thành phần đang được kỳ vọng và nếu có thể đưa ra gợi ý sửa. Diagnostic tốt dựa trên source span chính xác, mã lỗi ổn định và cách diễn đạt theo khái niệm của ngôn ngữ.

Với công cụ cần phân tích cả tệp, error recovery giúp tiếp tục sau lỗi bằng cách đồng bộ tại ranh giới phù hợp, chèn hoặc bỏ token trong trường hợp rõ ràng, hoặc dùng error production để nhận diện lỗi thường gặp. Recovery cần tránh tạo AST có vẻ hợp lệ từ nội dung sai và hạn chế lỗi dây chuyền.

Khi thiết kế DSL, hãy xem grammar, vị trí nguồn, thông báo lỗi và phục hồi là các phần liên kết với nhau. Một parser không chỉ xác định chương trình đúng hay sai; nó còn cần giúp người viết hiểu cấu trúc nào sai và cách quay lại trạng thái có thể phân tích tiếp.
