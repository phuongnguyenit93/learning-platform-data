# Lookahead

Trong phân tích cú pháp (parsing) của ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), **lookahead** là kỹ thuật quan sát một hoặc nhiều token tiếp theo để quyết định parser nên xử lý cấu trúc hiện tại như thế nào. Parser thường cần biết token sắp tới trước khi chọn một quy tắc grammar, nhưng việc quan sát này không nhất thiết tiêu thụ token đó.

Lookahead giúp parser phân biệt các lựa chọn có chung phần mở đầu, xây dựng parser dự đoán, xử lý cú pháp có điều kiện và đưa ra thông báo lỗi chính xác hơn. Đây là khái niệm quan trọng trong các parser LL, LR, parser đệ quy xuống (recursive descent) và một số hệ thống PEG.

Ví dụ, một DSL có thể cho phép cả phép gán và lời gọi hành động bắt đầu bằng định danh:

~~~text
status = "PAID";
status("PAID");
~~~

Sau khi đọc token `status`, parser chưa thể biết câu lệnh là phép gán hay lời gọi. Nó cần nhìn token tiếp theo: `=` gợi ý phép gán, còn `(` gợi ý lời gọi. Token được nhìn trước chính là lookahead.

## 1. Lookahead là gì?

Lookahead là thông tin về token hoặc ký tự ở phía trước vị trí parser đang xử lý. Parser dùng thông tin đó để chọn một hành động, chẳng hạn:

- Chọn một production trong grammar.
- Chọn giữa hai dạng câu lệnh có chung tiền tố.
- Quyết định có đọc tiếp một cấu trúc hay kết thúc cấu trúc hiện tại.
- Xác định token hiện tại có thể là dấu kết thúc của một biểu thức hay không.
- Phát hiện sớm một cú pháp không hợp lệ.

Cần phân biệt hai thao tác:

- **Quan sát (peek):** đọc loại hoặc giá trị của token sắp tới mà không di chuyển vị trí đọc.
- **Tiêu thụ (consume/advance):** lấy token đó làm một phần của cấu trúc đang phân tích và chuyển sang token kế tiếp.

Ví dụ, parser đang đứng trước token `=`. Nó có thể gọi hàm peek để kiểm tra token này có phải phép gán hay không. Nếu đúng, parser mới gọi hàm match hoặc expect để tiêu thụ token.

Một chuỗi token đơn giản:

~~~text
IDENTIFIER("status")  EQUALS  STRING("PAID")  SEMICOLON  EOF
          ^
     vị trí hiện tại
~~~

Sau khi tiêu thụ IDENTIFIER, parser có thể nhìn trước token EQUALS. Lookahead là EQUALS, nhưng token vẫn còn ở đầu vào cho đến khi parser tiêu thụ nó.

Lookahead thường được nói đến ở cấp token sau khi lexer đã chuyển văn bản thành token. Tuy nhiên, lexer cũng có thể dùng lookahead ở cấp ký tự để quyết định ranh giới token. Hai trường hợp có liên quan nhưng thuộc hai giai đoạn khác nhau.

## 2. Vì sao parser cần lookahead?

Grammar thường cho phép một vị trí có nhiều lựa chọn. Nếu các lựa chọn bắt đầu bằng những token khác nhau, parser có thể chọn ngay bằng token hiện tại. Nhưng nếu chúng có chung tiền tố, parser cần nhìn thêm.

### 2.1. Phân biệt các câu lệnh có chung tiền tố

Xét DSL đơn giản có hai loại câu lệnh:

~~~text
Assignment  = Identifier, "=", Expression, ";" ;
ActionCall  = Identifier, "(", Arguments, ")", ";" ;
Statement   = Assignment | ActionCall ;
~~~

Hai production đều bắt đầu bằng Identifier. Khi parser gặp `status`, chỉ nhìn token hiện tại thì chưa thể chọn Assignment hay ActionCall.

Hai ví dụ:

~~~text
status = "PAID";
status("PAID");
~~~

Parser cần nhìn token tiếp theo:

| Token sau Identifier | Cách diễn giải |
| --- | --- |
| `=` | Bắt đầu một phép gán |
| `(` | Bắt đầu một lời gọi hành động |
| `;` hoặc token khác | Không khớp hai dạng câu lệnh trên; có thể báo lỗi |

Lookahead cung cấp thông tin cần thiết để đưa ra quyết định mà không phải thử thực thi cả hai nhánh.

### 2.2. Xác định điểm kết thúc của cấu trúc

Lookahead còn giúp parser biết khi nào một danh sách hoặc biểu thức đã kết thúc.

Ví dụ:

~~~text
createOrder(customerId, quantity, "VND");
~~~

Khi phân tích danh sách tham số, dấu phẩy cho biết còn một tham số tiếp theo; dấu ngoặc đóng cho biết danh sách đã kết thúc. Parser nhìn token tiếp theo để quyết định tiếp tục đọc biểu thức hay hoàn tất danh sách.

Tương tự, trong:

~~~text
where active == true and country == "VN";
~~~

Parser cần nhận biết các toán tử logic và dấu kết thúc câu lệnh để xây dựng biểu thức đúng theo grammar.

### 2.3. Chọn cấu trúc mà không tiêu thụ nhầm token

Lookahead cho phép parser kiểm tra trước một token rồi giữ nguyên token đó cho bước phân tích tiếp theo. Điều này rất quan trọng ở ranh giới giữa các production.

Ví dụ, sau khi phân tích một biểu thức, parser có thể nhìn thấy dấu `)` để biết biểu thức đã kết thúc. Dấu `)` thuộc cấu trúc gọi hàm hoặc biểu thức nhóm bên ngoài, nên parser biểu thức không nên tự tiêu thụ nó nếu grammar quy định phần gọi bên ngoài chịu trách nhiệm.

## 3. Lookahead ở cấp lexer và parser

Từ lookahead có thể được dùng ở nhiều tầng. Cần phân biệt rõ để tránh nhầm lẫn.

### 3.1. Lookahead trong lexer

Lexer đọc ký tự và quyết định tạo token nào. Khi nhiều token có chung tiền tố, lexer có thể nhìn thêm ký tự.

Ví dụ, DSL hỗ trợ các toán tử:

- `=`: gán.
- `==`: so sánh bằng.
- `>`: lớn hơn.
- `>=`: lớn hơn hoặc bằng.

Khi đọc ký tự `=`, lexer cần nhìn ký tự tiếp theo:

| Ký tự hiện tại | Ký tự tiếp theo | Token |
| --- | --- | --- |
| `=` | `=` | `==` |
| `=` | Khác `=` hoặc hết đầu vào | `=` |
| `>` | `=` | `>=` |
| `>` | Khác `=` hoặc hết đầu vào | `>` |

Lexer thường áp dụng quy tắc khớp dài nhất (maximal munch): chọn token hợp lệ dài nhất tại vị trí hiện tại. Vì vậy, `>=` phải được nhận diện thành một token thay vì `>` rồi `=`.

Đây là lookahead ở cấp ký tự. Lexer chưa biết cấu trúc câu lệnh; nó chỉ quyết định cách chia chuỗi ký tự thành token.

### 3.2. Lookahead trong parser

Parser làm việc với chuỗi token do lexer tạo ra. Nó nhìn token kế tiếp để chọn production hoặc quyết định kết thúc một cấu trúc.

Ví dụ, lexer đã tạo:

~~~text
IDENTIFIER  LEFT_PAREN  STRING  RIGHT_PAREN  SEMICOLON
~~~

Parser có thể nhìn token LEFT_PAREN sau định danh để xác định đây là lời gọi hàm hoặc hành động.

Đây là lookahead ở cấp token. Parser sử dụng grammar để hiểu quan hệ giữa các token và xây dựng cây cú pháp.

### 3.3. Lookahead ngữ nghĩa

Một số DSL có cú pháp phụ thuộc vào thông tin đã khai báo trước đó. Khi đó, parser hoặc bước phân tích sau parser có thể cần tra cứu bảng ký hiệu (symbol table) để xác định ý nghĩa của một tên.

Ví dụ, trong một DSL kiểu dữ liệu:

~~~text
type Money
value: Money
~~~

Nếu cú pháp cho phép cùng một dạng tên xuất hiện ở nhiều vai trò, việc phân biệt có thể cần biết `Money` đã được khai báo là kiểu hay chưa.

Đây thường là kiểm tra ngữ nghĩa hoặc semantic predicate, không phải lookahead cú pháp thuần túy. Parser có thể dùng thông tin bảng ký hiệu để quyết định trong một số thiết kế, nhưng cách làm đó làm grammar phụ thuộc ngữ cảnh và cần được thiết kế rõ ràng.

## 4. Lookahead k và các chiến lược phân tích

Ký hiệu lookahead k (k-token lookahead) nói đến việc parser có thể xem trước tối đa k token để đưa ra quyết định. Giá trị k thể hiện lượng thông tin đầu vào được quan sát trước.

### 4.1. Lookahead 1 (LL(1))

LL(1) là một dạng parser dự đoán từ trái sang phải:

- Chữ L thứ nhất: đọc đầu vào từ trái sang phải (Left-to-right).
- Chữ L thứ hai: xây dựng dẫn xuất trái nhất (Leftmost derivation).
- Số 1: dùng một token lookahead để chọn production.

Với LL(1), parser chọn production dựa trên nonterminal hiện tại và token lookahead kế tiếp. Nếu grammar được thiết kế phù hợp, parser không cần thử nhiều nhánh hoặc quay lui.

Ví dụ:

~~~text
Statement = "print", Expression, ";"
          | "delete", Identifier, ";" ;
~~~

Nếu lookahead là `print`, parser chọn production thứ nhất. Nếu lookahead là `delete`, parser chọn production thứ hai. Hai tập token đầu tiên không giao nhau nên quyết định được bằng một token.

### 4.2. Lookahead k lớn hơn 1

Có những grammar mà một token không đủ để phân biệt các lựa chọn. Parser có thể cần nhìn trước nhiều token.

Ví dụ giả định:

~~~text
Declaration = "type", Identifier, "{", ...
             | "type", Identifier, "=", TypeName, ";" ;
~~~

Hai dạng đều bắt đầu bằng `type Identifier`. Sau token Identifier, parser cần nhìn tiếp:

- `{` cho biết khai báo dạng khối.
- `=` cho biết khai báo bí danh kiểu.

Một parser có thể đọc nhiều token để phân biệt. Tuy nhiên, không phải cứ tăng k là giải quyết được mọi vấn đề. Một số grammar không thể được phân tích dự đoán bằng bất kỳ k hữu hạn nào trong mô hình LL(k) tiêu chuẩn; khi đó cần biến đổi grammar hoặc dùng kỹ thuật parser khác.

### 4.3. Lookahead không đồng nghĩa với đọc trước toàn bộ chương trình

Lookahead k chỉ giới hạn số token cần quan sát để đưa ra một quyết định cụ thể. Parser vẫn xử lý đầu vào theo từng phần và có thể giữ một bộ đệm token nhỏ.

Trong thực tế, lexer thường tạo token khi parser yêu cầu. Parser có thể yêu cầu thêm token để lấp bộ đệm lookahead, nhưng không cần nạp toàn bộ tệp DSL vào bộ nhớ nếu kiến trúc hỗ trợ streaming.

## 5. FIRST và FOLLOW trong parser LL(1)

FIRST và FOLLOW là hai tập hợp quan trọng để xác định parser LL(1) có thể dùng một token lookahead để chọn production hay không.

### 5.1. Tập FIRST

FIRST(X) là tập token có thể xuất hiện đầu tiên trong chuỗi được sinh ra từ ký hiệu X.

Nếu X có thể sinh ra chuỗi rỗng (epsilon), thì epsilon cũng thuộc FIRST(X).

Ví dụ:

~~~text
Expression = Number | Identifier ;
~~~

Khi đó:

~~~text
FIRST(Expression) = { NUMBER, IDENTIFIER }
~~~

Với:

~~~text
OptionalSign = "+" | "-" | ε ;
~~~

ta có:

~~~text
FIRST(OptionalSign) = { PLUS, MINUS, ε }
~~~

Nếu production có dạng `A -> X Y`, cần xét FIRST(X); nếu X có thể sinh epsilon, tiếp tục xét FIRST(Y), và cứ tiếp tục cho đến khi gặp ký hiệu không thể rỗng hoặc hết production.

### 5.2. Tập FOLLOW

FOLLOW(A) là tập token có thể xuất hiện ngay sau nonterminal A trong một dẫn xuất hợp lệ. Ký hiệu kết thúc đầu vào EOF thường được đưa vào FOLLOW của ký hiệu bắt đầu.

Ví dụ:

~~~text
Call = Identifier, "(", Arguments, ")" ;
Statement = Call, ";" ;
~~~

Dấu `;` có thể xuất hiện ngay sau Call, do đó SEMICOLON thuộc FOLLOW(Call).

FOLLOW đặc biệt hữu ích khi một nonterminal có thể sinh epsilon. Parser cần biết token nào cho phép bỏ qua phần tùy chọn và tiếp tục với cấu trúc phía sau.

### 5.3. Quy tắc chọn production

Với production:

~~~text
A -> α
~~~

Parser LL(1) có thể chọn production dựa trên các quy tắc:

1. Với mỗi token thuộc FIRST(α) trừ epsilon, đưa production vào ô tương ứng trong bảng phân tích của A.
2. Nếu epsilon thuộc FIRST(α), đưa production vào các ô ứng với token trong FOLLOW(A).
3. Nếu hai production khác nhau cùng cần đặt vào một ô, grammar có xung đột LL(1) tại vị trí đó.

Nói cách khác, các lựa chọn của cùng một nonterminal cần có tập dự đoán không giao nhau. Nếu không, một token lookahead chưa đủ để chọn duy nhất production.

### 5.4. Ví dụ bảng dự đoán

Xét grammar:

~~~text
Statement -> "print" Expression ";"
           | "delete" Identifier ";"
~~~

Các tập FIRST:

~~~text
FIRST("print" Expression ";") = { PRINT }
FIRST("delete" Identifier ";") = { DELETE }
~~~

Bảng dự đoán rút gọn:

| Nonterminal | Lookahead PRINT | Lookahead DELETE |
| --- | --- | --- |
| Statement | Chọn production print | Chọn production delete |

Vì PRINT và DELETE khác nhau, parser có thể quyết định bằng một token.

Với một production có epsilon, bảng còn cần các cột tương ứng với FOLLOW của nonterminal. Nếu hai production xung đột ở cùng một ô, cần xem lại grammar hoặc chọn parser mạnh hơn.

## 6. Dùng lookahead để xử lý tiền tố chung

Một vấn đề phổ biến là hai production có cùng tiền tố. Kỹ thuật **left factoring (tách nhân tử trái)** đưa phần tiền tố chung ra một production riêng để parser trì hoãn quyết định đến khi có đủ lookahead.

### 6.1. Grammar ban đầu

Xét DSL có phép gán và lời gọi hành động:

~~~text
Statement -> Identifier "=" Expression ";"
           | Identifier "(" Arguments? ")" ";"
~~~

Cả hai production bắt đầu bằng Identifier. Bảng LL(1) sẽ có xung đột vì FIRST của hai nhánh đều chứa IDENTIFIER.

Parser không thể chọn nhánh ngay khi gặp định danh đầu tiên.

### 6.2. Grammar sau khi left factoring

Đưa phần chung ra ngoài:

~~~text
Statement -> Identifier StatementTail ;

StatementTail -> "=" Expression
               | "(" Arguments? ")" ;
~~~

Sau khi tiêu thụ Identifier, parser nhìn token tiếp theo:

| Lookahead | Production được chọn |
| --- | --- |
| `=` | Phân tích phần bên phải của phép gán |
| `(` | Phân tích danh sách tham số của lời gọi |
| Token khác | Báo lỗi cú pháp |

Grammar mới cho phép parser trì hoãn quyết định đến vị trí mà hai lựa chọn khác nhau. Nếu các token phân biệt tiếp tục có chung tiền tố, có thể cần left factoring thêm hoặc tăng lượng lookahead.

### 6.3. Ví dụ mã parser đệ quy xuống

Một parser đơn giản có thể dùng hàm peek để nhìn token hiện tại:

~~~java
Statement parseStatement() {
    Token name = expect(IDENTIFIER);

    if (check(EQUALS)) {
        advance();
        Expression value = parseExpression();
        expect(SEMICOLON);
        return new Assignment(name, value);
    }

    if (check(LEFT_PAREN)) {
        advance();
        List<Expression> args = parseArguments();
        expect(RIGHT_PAREN);
        expect(SEMICOLON);
        return new ActionCall(name, args);
    }

    throw error(peek(), "Expected '=' or '(' after identifier");
}
~~~

Trong ví dụ:

- `expect(IDENTIFIER)` tiêu thụ định danh đầu tiên.
- `check(EQUALS)` nhìn token hiện tại mà không tiêu thụ.
- Nếu là phép gán, `advance()` mới tiêu thụ dấu bằng.
- Nếu là lời gọi, parser tiêu thụ dấu ngoặc mở rồi phân tích tham số.
- Nếu không khớp lựa chọn nào, parser báo lỗi tại token đang nhìn thấy.

Đây là ví dụ minh họa cách tổ chức parser. Một parser thực tế cần định nghĩa rõ hành vi của check, advance, expect, cách lưu vị trí nguồn và kiểu lỗi.

## 7. Lookahead trong parser đệ quy xuống

Parser đệ quy xuống (recursive descent parser) thường được xây dựng bằng các hàm tương ứng với nonterminal hoặc cấu trúc cú pháp. Mỗi hàm đọc token và gọi các hàm khác để phân tích thành phần con.

Lookahead thường được triển khai bằng một hàm peek:

~~~java
Token peek() {
    return tokens.get(position);
}

Token advance() {
    if (!isAtEnd()) {
        position++;
    }
    return previous();
}

boolean check(TokenType type) {
    return !isAtEnd() && peek().type() == type;
}

boolean match(TokenType... types) {
    for (TokenType type : types) {
        if (check(type)) {
            advance();
            return true;
        }
    }
    return false;
}
~~~

Trong cách triển khai này:

- peek() trả về token ở vị trí hiện tại.
- advance() tiêu thụ token hiện tại và chuyển vị trí.
- check() chỉ kiểm tra loại token, không tiêu thụ.
- match() kiểm tra một hoặc nhiều loại token và tiêu thụ nếu khớp.

Một parser có thể dùng match để lựa chọn giữa các câu lệnh:

~~~java
Statement parseStatement() {
    if (match(PRINT)) {
        return parsePrintStatement();
    }

    if (match(DELETE)) {
        return parseDeleteStatement();
    }

    if (check(IDENTIFIER)) {
        return parseIdentifierStatement();
    }

    throw error(peek(), "Expected a statement");
}
~~~

Khi hai cấu trúc cùng bắt đầu bằng IDENTIFIER, hàm parseIdentifierStatement tiếp tục dùng lookahead để phân biệt. Điều này giúp giữ các hàm parser ngắn và tập trung vào từng cấu trúc.

### 7.1. Lookahead nhiều token

Nếu cần nhìn trước nhiều token, parser có thể cung cấp hàm peek(k):

~~~java
Token peek(int distance) {
    int index = position + distance;
    if (index >= tokens.size()) {
        return tokens.get(tokens.size() - 1); // EOF
    }
    return tokens.get(index);
}
~~~

Ở đây, peek(0) là token hiện tại, peek(1) là token tiếp theo. Parser có thể dùng nhiều token để nhận diện một mẫu cú pháp.

Tuy nhiên, cần giới hạn lookahead cần thiết và quản lý token EOF rõ ràng. Không nên để các hàm parser tự truy cập mảng token tùy ý vì dễ tạo lỗi vượt giới hạn hoặc không nhất quán trong cách xử lý cuối đầu vào.

## 8. Lookahead trong parser LR

LL không phải chiến lược duy nhất dùng lookahead. Parser LR (Left-to-right, Rightmost derivation in reverse) cũng sử dụng lookahead, nhưng theo cách khác.

Parser LR thường dùng một bảng ACTION/GOTO và trạng thái parser để quyết định:

- **Shift:** đưa token hiện tại vào stack và đọc token tiếp theo.
- **Reduce:** áp dụng một production để thay thế phần vế phải bằng nonterminal tương ứng.
- **Accept:** chấp nhận đầu vào.
- **Error:** báo lỗi.

Trong parser LR(1), một item có thể được viết:

~~~text
[A -> α ·, a]
~~~

Ý nghĩa:

- A -> α là production.
- Dấu chấm cho biết vị trí parser đã nhận diện trong production.
- a là token đầu vào tiếp theo mà trong ngữ cảnh đó cho phép parser reduce bằng production A -> α.

Khi parser đã nhận diện phần vế phải của một production, lookahead giúp xác định liệu có được phép reduce ở token tiếp theo hay không. Điều này giúp LR xử lý được nhiều grammar mà parser LL(1) không xử lý trực tiếp, bao gồm nhiều grammar có đệ quy trái.

Ví dụ, grammar biểu thức:

~~~text
Expression -> Expression "+" Term
            | Term
~~~

có đệ quy trái. Parser recursive descent trực tiếp có thể gọi lại Expression ngay khi đang phân tích Expression và dẫn đến đệ quy vô hạn. Parser LR có thể xử lý dạng đệ quy trái này bằng các thao tác shift/reduce phù hợp.

LR có nhiều biến thể:

- **LR(0):** các item không gắn token lookahead; với một trạng thái có item hoàn tất, thao tác reduce không bị giới hạn bởi một token theo sau cụ thể.
- **SLR(1):** dùng FOLLOW để hỗ trợ quyết định reduce.
- **LALR(1):** gộp một số trạng thái LR có lõi tương ứng để giảm kích thước bảng.
- **Canonical LR(1):** giữ thông tin lookahead chi tiết hơn cho từng item.

Các biến thể này có độ mạnh, kích thước bảng và độ phức tạp triển khai khác nhau. Khi xây dựng DSL, thường nên dùng công cụ parser generator phù hợp thay vì tự triển khai bảng LR nếu grammar có độ phức tạp đáng kể.

## 9. Lookahead trong PEG và cú pháp dự đoán có điều kiện

Parsing Expression Grammar (PEG) sử dụng lựa chọn có thứ tự (ordered choice). Khác với lựa chọn trong CFG thông thường, thứ tự các nhánh có ý nghĩa: parser thử nhánh đầu tiên; nếu thất bại, nó có thể thử nhánh tiếp theo theo quy tắc PEG.

PEG còn cung cấp các toán tử lookahead:

- **Positive lookahead (`&e`):** kiểm tra biểu thức e có khớp từ vị trí hiện tại hay không; không tiêu thụ đầu vào.
- **Negative lookahead (`!e`):** kiểm tra biểu thức e không khớp; cũng không tiêu thụ đầu vào.

Ví dụ minh họa:

~~~text
Identifier <- !Keyword [A-Za-z_] [A-Za-z0-9_]*
Keyword    <- "entity" / "field" / "relation"
~~~

Quy tắc này kiểm tra tên không phải một từ khóa đã liệt kê trước khi nhận diện nó là Identifier. Đây là minh họa ý tưởng; grammar thực tế cần xử lý ranh giới từ để `entityName` không bị coi là từ khóa `entity` theo tiền tố.

Một ví dụ khác về positive lookahead:

~~~text
Assignment <- Identifier &"=" "=" Expression ";"
~~~

Ở đây, `&"="` kiểm tra dấu bằng sắp tới mà không tiêu thụ nó; phần `"="` tiếp theo mới tiêu thụ dấu bằng. Cú pháp PEG cụ thể phụ thuộc công cụ, và ví dụ chỉ nhằm thể hiện ý nghĩa không tiêu thụ của lookahead.

Lookahead trong PEG là toán tử của grammar. Nó khác với việc parser LL dùng token kế tiếp để chọn production, dù cả hai đều dựa trên việc quan sát đầu vào phía trước.

## 10. Lookahead và backtracking

Lookahead và backtracking (quay lui) có liên quan nhưng không đồng nghĩa.

- **Lookahead:** quan sát token hoặc ký tự tiếp theo để quyết định.
- **Backtracking:** thử một nhánh phân tích; nếu nhánh đó thất bại, quay lại vị trí trước đó để thử nhánh khác.

Một parser dự đoán LL(1) thường dùng lookahead để chọn nhánh mà không cần backtracking. Một số parser PEG hoặc parser combinator có thể thử nhánh và quay lui khi thất bại. Parser có thể dùng cả hai kỹ thuật.

Ví dụ, một parser thử phân tích:

~~~text
Identifier "(" Arguments ")"
~~~

Nếu nhánh lời gọi thất bại sau khi đã tiêu thụ một số token, parser có thể quay về điểm bắt đầu để thử nhánh khác nếu framework hỗ trợ backtracking. Một parser dự đoán tốt có thể dùng lookahead để biết nhánh nào cần chọn ngay từ đầu, tránh việc thử rồi quay lại.

Backtracking có thể làm grammar dễ viết hơn trong một số trường hợp, nhưng nếu không kiểm soát có thể gây chi phí lớn vì parser thử lại cùng một đoạn đầu vào nhiều lần. Một số parser dùng memoization hoặc packrat parsing để tránh phân tích lặp lại.

## 11. Lookahead và tính mơ hồ của grammar

Lookahead có thể giải quyết việc chọn nhánh khi đủ thông tin phân biệt, nhưng không tự động làm cho một grammar mơ hồ trở nên không mơ hồ.

Ví dụ, biểu thức:

~~~text
a + b * c
~~~

Nếu grammar không quy định độ ưu tiên toán tử, biểu thức có thể được hiểu là:

- (a + b) * c
- a + (b * c)

Parser cần grammar hoặc quy tắc ngữ nghĩa quy định `*` có độ ưu tiên cao hơn `+`. Chỉ nhìn thêm token không tự xác định ý nghĩa mà đặc tả chưa định nghĩa.

Có thể thiết kế grammar phân tầng:

~~~text
Expression = Term, { ("+" | "-"), Term } ;
Term       = Factor, { ("*" | "/"), Factor } ;
Factor     = Number | Identifier | "(", Expression, ")" ;
~~~

Grammar này đặt phép nhân và chia ở mức Term, nằm bên trong Expression. Do đó, chúng được phân tích trước phép cộng và trừ.

Lookahead giúp parser chọn giữa các production ở từng tầng, còn độ ưu tiên được mã hóa trong cấu trúc grammar.

### 11.1. Vấn đề dangling else

Một ví dụ kinh điển về mơ hồ là câu lệnh if lồng nhau:

~~~text
if conditionA
  if conditionB
    actionOne
  else
    actionTwo
~~~

Từ khóa `else` thuộc về if nào? Một quy tắc phổ biến là gắn else với if gần nhất chưa có else. Quy tắc này cần được thể hiện trong grammar hoặc quy tắc phân tích. Lookahead có thể hỗ trợ parser nhận diện `else`, nhưng ngữ nghĩa gắn kết phải được đặc tả.

Nếu DSL muốn tránh mơ hồ, có thể yêu cầu khối rõ ràng:

~~~text
if conditionA {
  if conditionB {
    actionOne
  } else {
    actionTwo
  }
}
~~~

Dấu ngoặc hoặc từ khóa kết thúc khối giúp parser và người đọc nhận biết ranh giới.

## 12. Lookahead trong DSL có từ khóa theo ngữ cảnh

Một DSL có thể cho phép một từ vừa là tên định danh vừa là từ khóa trong ngữ cảnh nhất định.

Ví dụ, `where` có thể là từ khóa mở đầu điều kiện truy vấn, nhưng cũng có thể là tên thuộc tính trong một mô hình khác. Parser cần xác định ngữ cảnh để diễn giải đúng.

Có thể giải quyết theo một số cách:

1. **Từ khóa dành riêng:** cấm dùng tên đó làm định danh thông thường.
2. **Từ khóa theo ngữ cảnh:** chỉ nhận diện là từ khóa ở vị trí grammar phù hợp.
3. **Escape identifier:** cho phép viết tên đặc biệt bằng cú pháp trích dẫn.
4. **Tra cứu ngữ nghĩa:** dùng bảng ký hiệu để xác định một tên đã khai báo thuộc loại nào.

Lookahead thường giúp phân biệt vị trí cú pháp, nhưng không thay thế việc quản lý phạm vi và bảng ký hiệu. Nếu một từ khóa chỉ có ý nghĩa sau `query`, parser có thể dùng trạng thái grammar hoặc token phía trước để nhận diện. Nếu ý nghĩa phụ thuộc vào việc tên đã được khai báo là kiểu hay biến, cần kiểm tra ngữ nghĩa.

Một thiết kế tốt nên ưu tiên quy tắc đơn giản, dễ dự đoán. Dùng quá nhiều contextual keyword và semantic predicate có thể khiến người dùng khó hiểu vì sao cùng một từ lại được phân tích khác nhau.

## 13. Xử lý lỗi và phục hồi bằng lookahead

Lookahead còn hữu ích khi parser phát hiện lỗi và cần tìm điểm tiếp tục phân tích.

Giả sử DSL dùng dấu chấm phẩy để kết thúc câu lệnh:

~~~text
set status = "PAID"
set total = 100
print status
~~~

Câu đầu thiếu dấu `;`. Parser có thể báo lỗi rồi tìm token đồng bộ (synchronization token), chẳng hạn dấu chấm phẩy hoặc từ khóa bắt đầu câu lệnh tiếp theo.

Một chiến lược phục hồi đơn giản:

- Nếu gặp lỗi, bỏ qua token cho đến khi thấy `;`, `}` hoặc EOF.
- Nếu thấy token có thể bắt đầu một câu lệnh mới, dừng bỏ qua để parser tiếp tục.
- Giữ lại token đồng bộ nếu nó thuộc cấu trúc bên ngoài và chưa được tiêu thụ.

Ví dụ, các token bắt đầu câu lệnh có thể là `set`, `print`, `delete` hoặc `if`. Parser có thể nhìn trước token hiện tại để quyết định dừng đồng bộ.

Lookahead giúp tránh bỏ qua quá nhiều đầu vào, nhưng phục hồi cần được thiết kế cẩn thận. Nếu dừng ở token không đúng ranh giới, parser có thể tạo thêm nhiều lỗi dây chuyền. Một parser tốt nên báo lỗi đầu tiên có ích, giữ vị trí nguồn và hạn chế các thông báo lỗi phát sinh do hậu quả của lỗi ban đầu.

## 14. Chi phí và giới hạn của lookahead

Lookahead làm parser linh hoạt hơn, nhưng lượng lookahead lớn hoặc phụ thuộc ngữ cảnh có thể làm tăng độ phức tạp.

### 14.1. Chi phí bộ nhớ và xử lý

Parser nhìn trước k token có thể cần giữ một bộ đệm token. Với k nhỏ, chi phí thường không đáng kể. Với lookahead lớn hoặc đầu vào streaming, parser cần quản lý bộ đệm và vị trí đọc cẩn thận.

Một số parser có thể đọc trước bằng cách lưu token, một số dùng checkpoint và khôi phục vị trí. Nếu kết hợp backtracking, cùng một đoạn đầu vào có thể bị phân tích nhiều lần.

### 14.2. Grammar khó hiểu

Nếu người thiết kế dựa vào nhiều token lookahead để phân biệt các nhánh, người đọc grammar có thể khó hiểu vì sao một production được chọn. Left factoring, cấu trúc khối rõ ràng và từ khóa phân biệt thường làm grammar dễ đọc hơn.

### 14.3. Lookahead hữu hạn không giải quyết mọi grammar

Tăng k không bảo đảm mọi grammar đều trở thành LL(k). Một số cấu trúc cần parser mạnh hơn, ngữ nghĩa bổ sung hoặc thay đổi thiết kế cú pháp.

Nếu DSL thường xuyên cần nhìn xa hoặc dùng nhiều ngoại lệ, hãy cân nhắc:

- Viết lại grammar để giảm tiền tố chung.
- Chuyển cấu trúc sang cú pháp rõ ràng hơn.
- Dùng parser LR hoặc parser generator phù hợp.
- Dùng PEG nếu ordered choice và lookahead predicate phù hợp với yêu cầu.
- Tách cú pháp khỏi kiểm tra ngữ nghĩa.

## 15. Cách thiết kế grammar để giảm nhu cầu lookahead

Lookahead là công cụ hữu ích, nhưng một grammar tốt thường có thể giảm lượng thông tin cần nhìn trước.

Một số nguyên tắc:

- Dùng từ khóa mở đầu khác nhau cho các loại khai báo.
- Tránh để nhiều câu lệnh có cùng tiền tố dài nếu không cần thiết.
- Dùng dấu phân cách và dấu kết thúc nhất quán.
- Left factor các production có tiền tố chung.
- Loại bỏ đệ quy trái nếu dùng parser LL đệ quy xuống.
- Xác định rõ độ ưu tiên và tính kết hợp của toán tử.
- Dùng dấu ngoặc hoặc khối để làm rõ phạm vi.
- Hạn chế từ khóa theo ngữ cảnh nếu chúng tạo ra nhiều cách hiểu.

Ví dụ, thay vì hai dạng khai báo đều bắt đầu bằng `define`, DSL có thể dùng từ khóa cụ thể:

~~~text
entity Customer { ... }
relation places { ... }
constraint ActiveCustomer { ... }
~~~

Cách này giúp parser quyết định nhanh và giúp người đọc nhận diện cấu trúc.

Nếu cú pháp cần ngắn gọn và các nhánh phải chia sẻ tiền tố, có thể giữ tiền tố chung rồi dùng lookahead hoặc left factoring. Quyết định nên cân bằng giữa tính dễ đọc, tính nhất quán và độ phức tạp của parser.

## 16. Quy trình lựa chọn lookahead khi thiết kế DSL

Khi xây dựng parser, có thể tiến hành theo các bước:

### Bước 1: Xác định các production có chung tiền tố

Liệt kê các loại câu lệnh và khai báo. Tìm những production có cùng FIRST token hoặc cùng chuỗi token mở đầu.

### Bước 2: Xác định token phân biệt sớm nhất

Tìm vị trí đầu tiên mà các nhánh có token khác nhau. Nếu khác ngay ở token đầu tiên, lookahead 1 thường đủ. Nếu khác sau vài token, cần lookahead lớn hơn hoặc left factoring.

### Bước 3: Tính FIRST và FOLLOW nếu dùng LL

Tính FIRST cho từng vế phải và FOLLOW cho nonterminal. Kiểm tra các tập dự đoán có giao nhau không. Nếu có, grammar chưa phù hợp với LL(1) ở vị trí đó.

### Bước 4: Chọn cách xử lý

Có thể:

- Left factor grammar.
- Dùng LL(k) nếu lượng lookahead nhỏ và có giới hạn rõ.
- Dùng parser LR nếu grammar có cấu trúc phù hợp.
- Dùng PEG nếu ordered choice và predicate là lựa chọn thích hợp.
- Tách kiểm tra ngữ nghĩa ra khỏi parser.

### Bước 5: Kiểm thử trường hợp biên

Tạo ví dụ cho từng nhánh, tiền tố chung, token kết thúc, đầu vào thiếu, token không hợp lệ và cấu trúc lồng nhau. Kiểm tra parser không tiêu thụ nhầm token lookahead.

### Bước 6: Đánh giá thông báo lỗi

Khi lookahead không khớp lựa chọn nào, parser nên báo các token được mong đợi trong ngữ cảnh hiện tại. Tránh thông báo lỗi chỉ nêu token cuối cùng mà không chỉ ra vị trí và cấu trúc đang được phân tích.

## 17. Ví dụ tổng hợp: parser cho DSL quy trình

Giả sử DSL có các câu lệnh:

~~~text
workflow processOrder {
  set status = "PENDING";
  call reserveInventory(orderId);
  if stockAvailable {
    call chargePayment(orderId);
  }
}
~~~

Grammar giản lược:

~~~text
Workflow   -> "workflow" Identifier "{" Statement* "}" ;
Statement  -> Assignment
            | ActionCall
            | IfStatement ;

Assignment -> "set" Identifier "=" Expression ";" ;
ActionCall -> "call" Identifier "(" Arguments? ")" ";" ;
IfStatement -> "if" Expression "{" Statement* "}" ;
~~~

Các câu lệnh được phân biệt ngay từ token đầu tiên:

| Lookahead | Cấu trúc |
| --- | --- |
| `set` | Assignment |
| `call` | ActionCall |
| `if` | IfStatement |
| `}` | Kết thúc danh sách Statement trong khối |
| EOF | Kết thúc đầu vào ở vị trí hợp lệ |

Parser có thể chọn production Statement bằng một token lookahead. Trong ActionCall, sau `call` là Identifier rồi đến `(`; nếu grammar cho phép nhiều dạng action khác nhau có chung tiền tố, parser có thể cần nhìn thêm.

Khi phân tích khối `{ ... }`, parser dùng `}` làm lookahead để biết danh sách Statement đã kết thúc. Token `}` được giữ lại cho hàm phân tích khối tiêu thụ, tránh để hàm phân tích Statement ăn mất dấu ngoặc đóng.

Ví dụ này cho thấy lookahead không chỉ chọn câu lệnh. Nó còn giúp quản lý ranh giới giữa các cấu trúc lồng nhau và đảm bảo token được tiêu thụ đúng nơi.

## 18. Những nhầm lẫn thường gặp

**“Lookahead là tiêu thụ token tiếp theo.”** Không đúng. Lookahead là quan sát token phía trước. Token chỉ được tiêu thụ khi parser thực hiện thao tác advance hoặc tương đương.

**“Lookahead và backtracking là một.”** Không đúng. Lookahead quan sát trước để ra quyết định; backtracking quay về vị trí trước đó khi một nhánh phân tích thất bại. Một parser có thể dùng một trong hai hoặc cả hai.

**“LL(1) nghĩa là grammar chỉ có một token.”** Không đúng. Số 1 nói rằng parser dùng một token lookahead để chọn production. Câu lệnh vẫn có thể dài tùy ý.

**“Tăng lookahead luôn giải quyết được xung đột.”** Không đúng. Một số grammar không thuộc LL(k) với bất kỳ k hữu hạn nào. Cần biến đổi grammar hoặc dùng parser khác.

**“Lookahead tự giải quyết sự mơ hồ.”** Không đúng. Lookahead chỉ cung cấp thông tin đầu vào. Ngữ nghĩa, độ ưu tiên và cách gắn kết cấu trúc phải được đặc tả.

**“Lexer và parser dùng lookahead theo cùng cách.”** Không hoàn toàn. Lexer nhìn ký tự để tạo token; parser nhìn token để chọn cấu trúc grammar.

**“Parser chỉ cần lookahead khi bắt đầu câu lệnh.”** Không đúng. Lookahead còn được dùng để xác định kết thúc danh sách, biểu thức, khối, tham số và phục hồi sau lỗi.

## 19. Kết luận

Lookahead là kỹ thuật quan sát token hoặc ký tự phía trước để parser đưa ra quyết định mà không tiêu thụ đầu vào ngay lập tức. Ở cấp lexer, lookahead giúp nhận diện token như `==` và `>=`; ở cấp parser, nó giúp chọn production, phân biệt câu lệnh có chung tiền tố và xác định ranh giới cấu trúc.

Trong LL(1), parser dùng một token lookahead cùng các tập FIRST và FOLLOW để chọn production. Khi các nhánh có tiền tố chung, left factoring có thể làm grammar phù hợp hơn với parser dự đoán. Parser LR dùng lookahead trong quyết định shift/reduce, còn PEG cung cấp các toán tử lookahead không tiêu thụ đầu vào.

Khi thiết kế DSL, hãy dùng lookahead có chủ đích, giữ grammar dễ hiểu và xác định rõ quy tắc token, độ ưu tiên, ranh giới cấu trúc và xử lý lỗi. Nếu parser cần nhìn trước quá nhiều hoặc dựa vào nhiều ngoại lệ, hãy xem lại grammar hoặc chọn chiến lược parsing phù hợp hơn. Mục tiêu là để mỗi câu lệnh có cách diễn giải rõ ràng và parser có thể xử lý nó nhất quán.

