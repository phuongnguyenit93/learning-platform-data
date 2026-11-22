# Xử lý lookahead

## 1. Lookahead là gì?

Trong phân tích cú pháp (parsing) của một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **lookahead** là kỹ thuật xem trước một hoặc nhiều token tiếp theo để quyết định parser nên áp dụng production, nhánh xử lý hoặc hành động nào.

Parser thường đọc token từ trái sang phải. Khi gặp một điểm có nhiều khả năng phân tích, nó cần thêm thông tin để chọn đúng hướng. Thay vì tiêu thụ token ngay lập tức, parser quan sát token kế tiếp rồi đưa ra quyết định.

Ví dụ, DSL có hai câu lệnh:

~~~text
let customer = load_customer(10)
print(customer.name)
~~~

Parser có thể nhận diện câu lệnh bắt đầu bằng từ khóa let là khai báo biến, còn câu lệnh bắt đầu bằng print là lời gọi thao tác. Nhưng nếu grammar cho phép một identifier vừa là tên biến vừa là tên rule hoặc function, parser có thể cần xem token tiếp theo để phân biệt.

Ví dụ:

~~~text
customer = load_customer(10)
customer(name)
~~~

Sau khi đọc identifier customer:

- Nếu token tiếp theo là dấu bằng, parser có thể đang đọc phép gán.
- Nếu token tiếp theo là dấu mở ngoặc, parser có thể đang đọc lời gọi hàm.

Token tiếp theo là lookahead giúp parser chọn nhánh mà không phải đoán tùy tiện.

Lookahead không nhất thiết chỉ là một token. Parser có thể xem trước một token (LL(1)), hai token (LL(2)), k token (LL(k)) hoặc dùng chiến lược khác như backtracking, semantic predicate hay parsing expression với precedence.

## 2. Lookahead trong lexer và parser

Lookahead có thể xuất hiện ở hai tầng khác nhau.

### 2.1 Lookahead trong lexer

Lexer đọc ký tự đầu vào và gom chúng thành token. Nó có thể phải xem ký tự tiếp theo để quyết định token nào đang được tạo.

Ví dụ:

~~~text
>
>=
>>
>>=
~~~

Khi gặp ký tự >, lexer chưa thể kết luận ngay token là GREATER, GREATER_EQUAL, SHIFT_RIGHT hay SHIFT_RIGHT_ASSIGN. Nó cần xem các ký tự tiếp theo.

Ví dụ khác:

~~~text
/
//
/*
~~~

Ký tự / có thể bắt đầu toán tử chia, comment một dòng hoặc comment nhiều dòng. Lexer cần lookahead để phân biệt.

### 2.2 Lookahead trong parser

Parser nhận token đã được lexer tạo. Nó xem token tiếp theo để chọn production.

Ví dụ:

~~~text
statement
    : variableDeclaration
    | expressionStatement
    ;
~~~

Nếu cả hai production đều có thể bắt đầu bằng identifier, parser cần xem thêm token hoặc dùng một quy tắc grammar khác để phân biệt.

### 2.3 Hai tầng không thay thế nhau

Lexer lookahead giải quyết câu hỏi: chuỗi ký tự này tạo thành token nào?

Parser lookahead giải quyết câu hỏi: chuỗi token này thuộc cấu trúc cú pháp nào?

Nếu lexer tạo token sai, parser có thể không bao giờ khôi phục được ý nghĩa ban đầu. Ngược lại, lexer có thể tạo token hoàn toàn đúng nhưng parser vẫn cần lookahead để chọn production.

## 3. Token stream và thao tác xem trước

Để hỗ trợ lookahead, parser thường đọc token qua một token stream có khả năng:

- Xem token hiện tại hoặc token thứ k tiếp theo.
- Tiêu thụ token hiện tại và chuyển sang token kế tiếp.
- Kiểm tra token có loại mong đợi hay không.
- Giữ lại token đã đọc để có thể xem trước mà chưa mất dữ liệu.
- Nhận diện EOF khi đã hết đầu vào.

Một giao diện khái quát:

~~~java
interface TokenStream {
    Token lookahead(int k);
    Token consume();
    boolean match(TokenType type);
    Token expect(TokenType type);
}
~~~

Quy ước phổ biến là lookahead(1) trả token hiện tại chưa tiêu thụ, lookahead(2) trả token tiếp theo và cứ thế. Cần ghi rõ chỉ số bắt đầu từ 1 hay 0 để tránh lỗi off-by-one.

### 3.1 Lookahead không tiêu thụ token

Giả sử token stream là:

~~~text
IDENTIFIER  LPAREN  NUMBER  RPAREN  EOF
~~~

Nếu parser đang ở IDENTIFIER:

| Lệnh | Kết quả | Vị trí đọc |
|---|---|---|
| lookahead(1) | IDENTIFIER | Không đổi |
| lookahead(2) | LPAREN | Không đổi |
| lookahead(3) | NUMBER | Không đổi |
| consume() | IDENTIFIER | Chuyển sang LPAREN |

Lookahead chỉ quan sát. Chỉ consume mới làm tiến vị trí đọc.

### 3.2 EOF cũng là một token

Parser cần biết khi nào đầu vào kết thúc. EOF giúp phân biệt:

- Một cấu trúc hoàn chỉnh kết thúc đúng lúc.
- Một cấu trúc còn thiếu token.
- Một token thừa xuất hiện sau cấu trúc chính.

Ví dụ, sau khi parse một expression ở cấp chương trình, parser thường yêu cầu EOF để bảo đảm toàn bộ nguồn đã được tiêu thụ:

~~~text
program -> expression EOF
~~~

Nếu không kiểm tra EOF, parser có thể chấp nhận một tiền tố hợp lệ và bỏ qua phần văn bản thừa.

## 4. Lookahead và ký hiệu LL(k)

Ký hiệu LL(k) mô tả một lớp parser:

- Chữ L đầu tiên: đọc input từ trái sang phải (Left-to-right).
- Chữ L thứ hai: xây dựng derivation trái nhất (Leftmost derivation).
- k: số token lookahead tối đa cần xem để chọn production.

Ví dụ:

- LL(1) chỉ cần xem một token tiếp theo.
- LL(2) có thể cần xem hai token.
- LL(k) dùng một lượng lookahead hữu hạn k.

Một grammar LL(1) cho phép parser chọn production dựa trên token lookahead đầu tiên mà không cần backtracking.

### 4.1 Vì sao LL(1) được ưa chuộng?

LL(1) thường phù hợp với recursive descent và predictive parser vì:

- Quyết định production đơn giản.
- Parser có thể chạy tuyến tính theo số token.
- Không cần thử nhiều nhánh rồi quay lui.
- Thông báo lỗi có thể gắn với tập token được mong đợi.
- Code parser thường dễ đọc và dễ kiểm soát.

Tuy nhiên, không phải grammar nào cũng LL(1). Một số grammar cần left factoring, loại bỏ left recursion hoặc dùng lookahead lớn hơn.

### 4.2 LL(1) không có nghĩa parser chỉ có một hàm

LL(1) là thuộc tính của grammar và chiến lược phân tích, không phải số lượng hàm parser. Một parser LL(1) vẫn có thể có nhiều hàm cho các nonterminal khác nhau. Điều kiện quan trọng là mỗi quyết định production có thể thực hiện chỉ bằng một token lookahead.

## 5. FIRST và FOLLOW hỗ trợ quyết định lookahead

Để biết một token có thể bắt đầu một production hay không, ta dùng tập FIRST. Để biết token nào có thể xuất hiện sau một nonterminal, ta dùng tập FOLLOW.

### 5.1 Tập FIRST

FIRST(α) là tập terminal có thể xuất hiện đầu tiên trong một chuỗi được suy dẫn từ α. Nếu α có thể suy dẫn ra chuỗi rỗng, FIRST(α) cũng chứa epsilon.

Ví dụ:

~~~text
number -> NUMBER

primary -> NUMBER
         | IDENTIFIER
         | "(" expression ")"
~~~

Ta có:

~~~text
FIRST(number) = { NUMBER }
FIRST(primary) = { NUMBER, IDENTIFIER, LPAREN }
~~~

Nếu một production bắt đầu bằng terminal, terminal đó thuộc FIRST của production. Nếu bắt đầu bằng nonterminal, cần xét FIRST của nonterminal đó và tiếp tục nếu nonterminal có thể sinh epsilon.

### 5.2 Tính FIRST của một chuỗi

Với chuỗi X1 X2 ... Xn:

1. Thêm FIRST(X1) trừ epsilon.
2. Nếu X1 nullable, tiếp tục xét X2.
3. Lặp lại cho đến khi gặp một ký hiệu không nullable.
4. Nếu tất cả ký hiệu đều nullable, thêm epsilon.

Ví dụ:

~~~text
A -> B C D
B -> "b" | epsilon
C -> "c"
D -> "d"
~~~

Vì B có thể rỗng, FIRST(A) gồm "b" và FIRST(C), tức "c". C không nullable nên không cần xét D.

~~~text
FIRST(A) = { "b", "c" }
~~~

### 5.3 Tập FOLLOW

FOLLOW(A) là tập terminal có thể xuất hiện ngay sau nonterminal A trong một sentential form hợp lệ. EOF thường thuộc FOLLOW của ký hiệu bắt đầu.

Ví dụ:

~~~text
statement -> "print" expression ";"
program   -> statement*
~~~

Trong trường hợp này, dấu chấm phẩy xuất hiện sau expression, nên SEMICOLON thuộc FOLLOW(expression).

FOLLOW rất quan trọng khi một nonterminal có thể sinh epsilon. Nếu parser chọn nhánh epsilon, nó cần biết token hiện tại có thể hợp lệ để xuất hiện sau nonterminal hay không.

### 5.4 Nullable

Một nonterminal A nullable nếu:

\[
A \Rightarrow^* \epsilon
\]

Tập nullable có thể được tính bằng cách lặp qua các production:

- Nếu một production có vế phải rỗng, nonterminal bên trái nullable.
- Nếu mọi ký hiệu trên một vế phải đều nullable, nonterminal bên trái cũng nullable.
- Lặp đến khi không có thay đổi.

FIRST, FOLLOW và nullable là nền tảng để xây bảng phân tích LL(1).

## 6. Điều kiện để grammar LL(1)

Xét một nonterminal A có hai production:

~~~text
A -> alpha
   | beta
~~~

Để parser chọn nhánh bằng một token lookahead, các tập dự đoán của hai nhánh không được giao nhau.

Nếu cả hai nhánh không nullable, điều kiện cơ bản là:

\[
FIRST(\alpha) \cap FIRST(\beta) = \varnothing
\]

Nếu một nhánh có thể sinh epsilon, cần xét thêm FOLLOW(A). Tập dự đoán của một production A → α là:

- FIRST(α) trừ epsilon.
- Nếu α nullable, thêm FOLLOW(A).

Hai production cùng một nonterminal phải có tập dự đoán đôi một không giao nhau.

### 6.1 Ví dụ grammar LL(1)

~~~text
statement
    -> "let" IDENTIFIER "=" expression ";"
    | "print" expression ";"
~~~

Hai nhánh có token đầu khác nhau:

~~~text
FIRST(let-branch) = { LET }
FIRST(print-branch) = { PRINT }
~~~

Giao của hai tập rỗng, nên parser có thể chọn nhánh chỉ bằng một token.

### 6.2 Ví dụ không LL(1)

~~~text
statement
    -> IDENTIFIER "=" expression ";"
    | IDENTIFIER "(" arguments? ")" ";"
~~~

Cả hai nhánh đều bắt đầu bằng IDENTIFIER:

~~~text
FIRST(branch1) = { IDENTIFIER }
FIRST(branch2) = { IDENTIFIER }
~~~

Với một token lookahead, parser chưa biết identifier sẽ được theo sau bởi dấu bằng hay dấu mở ngoặc. Grammar này không LL(1) tại quyết định đó.

Có thể dùng LL(2), left factoring hoặc một thiết kế grammar khác.

## 7. Bảng phân tích dự đoán LL(1)

Predictive parsing table ánh xạ cặp (nonterminal, lookahead token) đến production cần dùng.

Ví dụ grammar:

~~~text
S -> "a" A
A -> "b" | epsilon
~~~

Các tập:

~~~text
FIRST(S) = { "a" }
FIRST(A) = { "b", epsilon }
FOLLOW(A) = { EOF }
~~~

Bảng:

| Nonterminal | Lookahead a | Lookahead b | Lookahead EOF |
|---|---|---|---|
| S | S → a A | error | error |
| A | error | A → b | A → epsilon |

Khi parser đang xử lý A:

- Nếu lookahead là b, chọn A → b.
- Nếu lookahead là EOF, chọn A → epsilon.
- Với token khác, báo lỗi.

### 7.1 Ô bảng có nhiều production

Nếu một ô của bảng LL(1) nhận nhiều production, grammar có xung đột predictive parsing. Điều đó cho thấy một token lookahead chưa đủ để quyết định theo grammar hiện tại.

Nguyên nhân có thể là:

- Các nhánh có FIRST giao nhau.
- Một nhánh nullable và token trong FOLLOW cũng thuộc FIRST của nhánh khác.
- Grammar có cấu trúc cần left factoring.
- Grammar không phù hợp LL(1) và cần parser khác.

Không nên tự chọn production đầu tiên trong danh sách khi có xung đột. Cách đó biến một grammar mơ hồ hoặc không LL(1) thành hành vi phụ thuộc thứ tự khai báo.

## 8. Lookahead trong recursive descent

Recursive descent thường dùng một hàm cho mỗi nonterminal. Các hàm kiểm tra token hiện tại rồi chọn nhánh.

Ví dụ:

~~~text
statement
    -> "let" IDENTIFIER "=" expression ";"
    | "print" expression ";"
~~~

Java:

~~~java
Statement parseStatement() {
    if (check(TokenType.LET)) {
        return parseVariableDeclaration();
    }

    if (check(TokenType.PRINT)) {
        return parsePrintStatement();
    }

    throw error("Expected let or print");
}
~~~

Ở đây, check chỉ xem token hiện tại, không tiêu thụ. Mỗi hàm parse nhánh sẽ tiêu thụ token bằng expect hoặc consume.

### 8.1 Lookahead một token

Ví dụ phân biệt phép gán và lời gọi:

~~~text
statement
    -> IDENTIFIER "=" expression ";"
    | IDENTIFIER "(" arguments? ")" ";"
~~~

Parser có thể xem hai token:

~~~java
Statement parseIdentifierStatement() {
    Token name = expect(TokenType.IDENTIFIER);

    if (match(TokenType.EQUAL)) {
        Expression value = parseExpression();
        expect(TokenType.SEMICOLON);
        return new Assignment(name, value);
    }

    if (match(TokenType.LPAREN)) {
        List<Expression> args = parseArgumentsAfterOpenParen();
        expect(TokenType.SEMICOLON);
        return new CallStatement(name, args);
    }

    throw error("Expected '=' or '(' after identifier");
}
~~~

Ở ví dụ này, parser đã consume identifier rồi mới kiểm tra token tiếp theo. Về bản chất, token sau identifier là lookahead tại thời điểm quyết định.

Nếu muốn quyết định trước khi tiêu thụ identifier, có thể dùng lookahead(2):

~~~java
if (peek(1).type() == IDENTIFIER
        && peek(2).type() == EQUAL) {
    return parseAssignment();
}
~~~

Cả hai cách đều có thể đúng. Chọn cách nào phụ thuộc vào thiết kế parser và khả năng khôi phục khi nhánh thất bại.

## 9. Cài đặt token stream có lookahead trong Java

Một token stream đơn giản có thể dùng danh sách token đã được lexer tạo:

~~~java
final class ListTokenStream {
    private final List<Token> tokens;
    private int position;

    ListTokenStream(List<Token> tokens) {
        this.tokens = List.copyOf(tokens);
    }

    Token lookahead(int k) {
        if (k < 1) {
            throw new IllegalArgumentException("k must be >= 1");
        }

        int index = position + k - 1;
        if (index >= tokens.size()) {
            return tokens.get(tokens.size() - 1);
        }
        return tokens.get(index);
    }

    Token current() {
        return lookahead(1);
    }

    Token consume() {
        Token token = current();
        if (token.type() != TokenType.EOF) {
            position++;
        }
        return token;
    }

    boolean match(TokenType type) {
        if (current().type() != type) {
            return false;
        }
        consume();
        return true;
    }

    Token expect(TokenType type) {
        Token token = current();
        if (token.type() != type) {
            throw new ParseException(
                "Expected " + type + " but found " + token.type(),
                token.span()
            );
        }
        return consume();
    }
}
~~~

Ví dụ giả định lexer luôn thêm một token EOF ở cuối danh sách. Vì vậy, lookahead vượt quá cuối stream vẫn trả EOF. Việc không consume EOF giúp parser không đi ra ngoài danh sách.

Trong parser thực tế, cần bảo đảm:

- Danh sách token không rỗng.
- EOF luôn có mặt.
- Source span được giữ để báo lỗi.
- Token stream không bị nhiều parser dùng đồng thời.
- Chỉ số lookahead được kiểm tra.

### 9.1 Buffer thay vì lưu toàn bộ token

Với file lớn hoặc input streaming, không nhất thiết phải giữ toàn bộ token trong bộ nhớ. Có thể dùng buffer vòng hoặc queue:

1. Nếu buffer đã có đủ k token, trả token thứ k.
2. Nếu chưa đủ, yêu cầu lexer đọc thêm.
3. Giữ token chưa tiêu thụ trong buffer.
4. Khi consume, bỏ token đầu và điều chỉnh vị trí.

Nếu parser cần quay lui, buffer phải giữ lại đủ token cho đến khi mọi nhánh có thể cần chúng đã được quyết định.

## 10. Lookahead k token

Một token đôi khi không đủ để phân biệt hai production. LL(k) cho phép xem trước tối đa k token.

Ví dụ:

~~~text
statement
    -> IDENTIFIER "." IDENTIFIER "=" expression ";"
    | IDENTIFIER "(" arguments? ")" ";"
~~~

Sau IDENTIFIER, token tiếp theo có thể là dấu chấm hoặc dấu mở ngoặc, nên LL(2) đủ phân biệt hai nhánh.

Một ví dụ khác:

~~~text
declaration
    -> "type" IDENTIFIER "=" typeExpression ";"
    | "type" IDENTIFIER "{" fieldList "}"
~~~

Sau token type và identifier:

- Nếu token thứ ba là dấu bằng, đây là type alias.
- Nếu token thứ ba là dấu mở ngoặc nhọn, đây là record declaration.

Parser có thể dùng lookahead(3) nếu đang đứng ở token đầu tiên.

### 10.1 Lookahead hữu hạn và giới hạn k

LL(k) giả định tồn tại một số k hữu hạn đủ để phân biệt các production tại mọi điểm quyết định. Có grammar cần k lớn hơn 1; cũng có grammar không thuộc bất kỳ lớp LL(k) nào với k cố định.

Tăng k không phải lúc nào cũng giải quyết được vấn đề. Nếu hai nhánh có thể bắt đầu bằng chuỗi token dài tùy ý giống nhau rồi mới khác nhau, cần thay đổi grammar hoặc dùng chiến lược parser khác.

### 10.2 Chi phí của lookahead lớn

Lookahead lớn có thể:

- Tăng lượng token phải buffer.
- Làm code quyết định khó đọc.
- Khiến parser phụ thuộc chặt vào chi tiết grammar.
- Làm diagnostics khó xác định điểm bắt đầu của cấu trúc.
- Tăng chi phí khi cần quét nhiều token trước khi parse.

Hãy dùng lượng lookahead nhỏ nhất đủ để grammar có quyết định rõ ràng.

## 11. Left factoring để giảm nhu cầu lookahead

Khi nhiều production có chung tiền tố, có thể đưa phần chung ra trước và trì hoãn quyết định đến sau.

Grammar ban đầu:

~~~text
statement
    -> IDENTIFIER "=" expression ";"
    | IDENTIFIER "(" arguments? ")" ";"
~~~

Hai nhánh có tiền tố IDENTIFIER. Left factoring:

~~~text
statement
    -> IDENTIFIER statementTail

statementTail
    -> "=" expression ";"
    | "(" arguments? ")" ";"
~~~

Sau khi parse identifier, parser chỉ cần xem token tiếp theo:

- EQUAL: parse assignment tail.
- LPAREN: parse call tail.

Left factoring không thay đổi ngôn ngữ được sinh ra nếu biến đổi đúng, nhưng thay đổi cấu trúc parse tree. AST builder cần được điều chỉnh theo grammar mới.

### 11.1 Ví dụ với câu lệnh có từ khóa chung

Grammar:

~~~text
statement
    -> "if" expression "then" statement
    | "if" expression "then" statement "else" statement
~~~

Hai nhánh có chung tiền tố dài. Có thể factor:

~~~text
statement
    -> "if" expression "then" statement optionalElse

optionalElse
    -> "else" statement
    | epsilon
~~~

Tuy nhiên, trường hợp này còn liên quan đến dangling else. Cần quy định else gắn với if gần nhất hay có quy tắc khác. Left factoring một mình không giải quyết mọi vấn đề về ngữ nghĩa hoặc ambiguity.

## 12. Lookahead và lựa chọn nhánh có epsilon

Khi một production có thể sinh epsilon, parser phải dùng FOLLOW để biết khi nào nên chọn nhánh rỗng.

Ví dụ:

~~~text
arguments
    -> expression argumentsTail
    | epsilon

argumentsTail
    -> "," expression argumentsTail
    | epsilon
~~~

Trong lời gọi:

~~~text
notify()
~~~

Sau dấu mở ngoặc, token tiếp theo là dấu đóng ngoặc. Nếu RPAREN thuộc FOLLOW(arguments), parser có thể chọn arguments → epsilon.

Trong lời gọi:

~~~text
notify("hello", 10)
~~~

Token đầu tiên là string literal, thuộc FIRST(expression), nên parser chọn nhánh có expression.

Nếu token hiện tại vừa thuộc FIRST của nhánh không rỗng vừa thuộc FOLLOW của nonterminal nullable, grammar có thể có xung đột LL(1).

## 13. Backtracking: thử nhánh rồi quay lui

Một cách khác để giải quyết lựa chọn nhánh là backtracking:

1. Lưu vị trí token hiện tại.
2. Thử parse nhánh thứ nhất.
3. Nếu thành công, giữ kết quả.
4. Nếu thất bại theo cách có thể phục hồi, quay lại vị trí đã lưu.
5. Thử nhánh tiếp theo.

Ví dụ khái quát:

~~~java
Statement parseStatement() {
    int mark = tokens.mark();
    try {
        return parseVariableDeclaration();
    } catch (NoMatchException ex) {
        tokens.reset(mark);
    }

    return parseExpressionStatement();
}
~~~

Đây là mã giả về cơ chế backtracking. Parser thật cần phân biệt lỗi "nhánh này không khớp" với lỗi cú pháp nghiêm trọng sau khi nhánh đã được xác nhận. Nếu mọi lỗi đều bị bắt rồi quay lui, parser có thể che giấu lỗi thật và đưa ra thông báo khó hiểu.

### 13.1 Ưu điểm

- Có thể giữ grammar gần với cách mô tả ban đầu.
- Hữu ích khi các nhánh khó phân biệt bằng một lookahead nhỏ.
- Dễ triển khai cho grammar nhỏ hoặc parser thử nghiệm.

### 13.2 Hạn chế

- Có thể parse lại cùng một đoạn nhiều lần.
- Một số grammar gây thời gian chạy tăng mạnh.
- Cần lưu và khôi phục trạng thái parser.
- Diagnostics có thể phản ánh nhánh thử cuối cùng thay vì lỗi có ý nghĩa nhất.
- Tác dụng phụ trong semantic action có thể bị thực hiện lặp.

Nếu dùng backtracking, semantic action nên trì hoãn đến khi nhánh được xác nhận hoặc phải có khả năng rollback.

## 14. PEG và ordered choice

Parsing Expression Grammar (PEG) dùng ordered choice. Nếu có hai lựa chọn:

~~~text
A <- B / C
~~~

parser thử B trước. Nếu B thành công, C không được thử, ngay cả khi C cũng có thể khớp. Thứ tự nhánh là một phần của semantics grammar.

Điều này khác với CFG thông thường, nơi hai production không mặc nhiên được ưu tiên theo thứ tự viết.

### 14.1 Ví dụ

~~~text
keyword <- "if" / identifier
~~~

Nếu identifier có thể khớp chuỗi if, việc đặt keyword "if" trước giúp nhận diện từ khóa. Nếu đảo thứ tự:

~~~text
keyword <- identifier / "if"
~~~

nhánh identifier có thể nhận if trước, khiến nhánh keyword không bao giờ được dùng.

### 14.2 Lookahead phủ định và khẳng định

PEG thường có predicate:

- Positive lookahead: xác nhận một biểu thức có thể khớp mà không tiêu thụ input.
- Negative lookahead: xác nhận một biểu thức không thể khớp.

Ví dụ minh họa:

~~~text
identifier <- !reservedWord [a-zA-Z_] [a-zA-Z0-9_]*
~~~

Parser kiểm tra chuỗi hiện tại không phải reserved word trước khi nhận nó là identifier. Cú pháp cụ thể tùy PEG implementation.

### 14.3 Packrat parsing

Packrat parser ghi nhớ kết quả parse của một rule tại một vị trí input để tránh tính lại cùng một cặp rule/vị trí. Với memoization đầy đủ, nhiều PEG parser có thể đạt thời gian tuyến tính theo kích thước input, đổi lại chi phí bộ nhớ có thể lớn.

Packrat không đồng nghĩa với mọi dạng lookahead đều miễn phí. Số rule, vị trí input, semantic predicate và cách implementation ảnh hưởng đáng kể đến bộ nhớ và hiệu năng.

## 15. Semantic predicate và lookahead phụ thuộc ngữ cảnh

Có trường hợp token lookahead chưa đủ vì quyết định còn phụ thuộc symbol table, kiểu đã biết hoặc trạng thái ngữ nghĩa.

Ví dụ, một identifier có thể là type name hoặc variable name:

~~~text
TypeName value
~~~

Parser có thể cần biết TypeName đã được khai báo là kiểu hay chưa. Đây là một quyết định dựa trên ngữ nghĩa, không chỉ token tiếp theo.

Semantic predicate là điều kiện Boolean được dùng để cho phép hoặc chọn một nhánh parse dựa trên ngữ cảnh.

Ví dụ khái quát:

~~~text
if isKnownType(lookaheadIdentifier):
    parseVariableDeclaration()
else:
    parseExpressionStatement()
~~~

Predicate cần được thiết kế cẩn thận:

- Kết quả phải ổn định trong lúc parse.
- Không nên thay đổi trạng thái chương trình như một side effect.
- Cần xác định symbol table đã được xây đến giai đoạn nào.
- Nếu parser backtrack, predicate phải không làm hỏng trạng thái.
- Diagnostics cần chỉ rõ tên chưa được phân giải hoặc nhánh không hợp lệ.

Một grammar phụ thuộc quá nhiều vào trạng thái ngữ nghĩa có thể khó phân tích độc lập và khó dùng trong editor. Hãy ưu tiên grammar rõ ràng nếu có thể.

## 16. Lookahead trong ANTLR

ANTLR sinh parser từ grammar và tự quản lý token stream cùng quyết định lookahead. ANTLR 4 dùng cơ chế adaptive prediction cho nhiều quyết định, thay vì yêu cầu người viết tự tính một k cố định cho mọi điểm.

Ví dụ grammar:

~~~text
statement
    : LET IDENTIFIER EQUAL expression SEMI
    | PRINT expression SEMI
    ;
~~~

Với hai nhánh bắt đầu bằng token khác nhau, parser có thể quyết định nhanh dựa trên token hiện tại.

Ví dụ có tiền tố chung:

~~~text
statement
    : IDENTIFIER EQUAL expression SEMI
    | IDENTIFIER LPAREN arguments? RPAREN SEMI
    ;
~~~

ANTLR có thể phân tích lookahead cần thiết dựa trên grammar. Tuy nhiên, grammar vẫn cần được thiết kế sao cho các quyết định có ý nghĩa và không mơ hồ ngoài dự kiến.

### 16.1 Adaptive prediction

ANTLR 4 sử dụng ATN và DFA để dự đoán nhánh. Parser có thể dùng thông tin lookahead động và cache kết quả dự đoán để tái sử dụng trong những trường hợp phù hợp.

Điều đó không có nghĩa parser luôn đọc toàn bộ file trước khi quyết định. Nó phân tích đủ thông tin cần thiết tại điểm quyết định và có thể dùng nhiều chiến lược tùy tình huống.

### 16.2 Explicit lookahead và semantic predicate

Trong một số grammar, người viết có thể thêm predicate để giới hạn nhánh:

~~~text
{isTypeName(_input.LT(1).getText())}? IDENTIFIER
~~~

Đây là ví dụ ý tưởng theo cú pháp ANTLR; predicate cụ thể phụ thuộc target language và vị trí grammar. Không nên dùng predicate để che một grammar có cấu trúc chưa rõ nếu có thể sửa bằng cách tách rule hoặc left factoring.

### 16.3 Debug prediction

Khi parser chọn nhánh không như mong đợi:

- Xem token stream tại điểm quyết định.
- Xác định các alternative có thể khớp.
- Kiểm tra FIRST/FOLLOW hoặc prefix chung.
- Xem predicate có loại nhánh hay không.
- Dùng công cụ diagnostic của parser generator.
- Tạo input nhỏ nhất tái hiện quyết định.

Không nên chỉ thay thứ tự alternative rồi kết luận đã sửa đúng. Cần hiểu grammar đang cho phép điều gì.

## 17. Lookahead và precedence của biểu thức

Parser biểu thức thường cần quyết định toán tử thuộc tầng nào và toán hạng kết thúc ở đâu.

Grammar phân tầng:

~~~text
expression
    : term (("+" | "-") term)*
    ;

term
    : factor (("*" | "/") factor)*
    ;

factor
    : NUMBER
    | "(" expression ")"
    ;
~~~

Lookahead cho biết token hiện tại có phải toán tử thuộc tầng đang xử lý hay không:

- Trong expression, PLUS hoặc MINUS tiếp tục vòng lặp.
- Trong term, STAR hoặc SLASH tiếp tục vòng lặp.
- Nếu gặp RPAREN, SEMI hoặc EOF tùy ngữ cảnh, tầng hiện tại kết thúc.

Parser không cần nhìn trước nhiều token nếu grammar đã phân tầng rõ và các token kết thúc được xác định tốt.

### 17.1 Pratt parser

Pratt parser sử dụng binding power để quyết định toán tử tiếp theo có được đưa vào biểu thức hiện tại hay không. Nó thường dùng lookahead token hiện tại để xem token đó có phải infix hoặc postfix operator.

Kỹ thuật này hữu ích khi DSL có nhiều toán tử, precedence và associativity. Thay vì viết một tầng grammar cho từng mức ưu tiên, parser tra cứu bảng binding power.

### 17.2 Lookahead không thay thế precedence

Biết token tiếp theo là dấu nhân không tự động bảo đảm phép nhân có ưu tiên cao hơn phép cộng. Precedence phải được thể hiện trong grammar hoặc thuật toán parse biểu thức.

Lookahead giúp chọn bước tiếp theo; precedence quy định cấu trúc nhóm của biểu thức.

## 18. Dangling else và lookahead

Một trường hợp nổi tiếng liên quan đến quyết định parser là dangling else:

~~~text
if a then
  if b then
    action1
  else
    action2
~~~

Else thuộc if nào? Nhiều ngôn ngữ gắn else với if gần nhất chưa có else. Đây là một quy tắc ngữ pháp/ưu tiên cần được thể hiện rõ.

Có thể giải quyết bằng:

- Grammar phân biệt matched và unmatched statement.
- Quy tắc precedence của parser generator.
- Cấu trúc block có dấu kết thúc tường minh.

Chỉ nhìn token ELSE không đủ nếu grammar cho phép nhiều cách gắn kết. Lookahead phải kết hợp với cấu trúc grammar và quy tắc ưu tiên.

## 19. Lookahead trong phân biệt declaration và expression

DSL có thể cho phép identifier mở đầu cả khai báo lẫn biểu thức.

Ví dụ:

~~~text
Customer customer
customer = load_customer(10)
~~~

Nếu tên kiểu không phải keyword, parser cần biết Customer đã được đăng ký như một type name chưa, hoặc xem chuỗi token tiếp theo có hình dạng của declaration không.

Các chiến lược:

1. Dùng từ khóa riêng như let hoặc type để grammar dễ dự đoán.
2. Dùng lookahead nhiều token nếu có prefix đủ phân biệt.
3. Dùng symbol table và semantic predicate nếu quyết định thật sự phụ thuộc loại tên.
4. Tách declaration và expression thành các vùng cú pháp rõ ràng.
5. Dùng parser có hỗ trợ backtracking nếu grammar cần thiết.

Thiết kế cú pháp có keyword riêng thường giúp parser, IDE và người đọc cùng dễ hiểu hơn.

## 20. Error handling và expected tokens

Lookahead không chỉ giúp chọn nhánh mà còn giúp tạo thông báo lỗi tốt.

Khi parser đang ở một vị trí, nó có thể biết tập token hợp lệ tiếp theo:

~~~text
After LET:
  expected IDENTIFIER

After IDENTIFIER in assignment:
  expected EQUAL

After expression:
  expected SEMICOLON
~~~

Thông báo:

~~~text
Expected ';' after expression, but found '}'
~~~

thường hữu ích hơn:

~~~text
Syntax error
~~~

### 20.1 Expected set

Với predictive parser, tập token hợp lệ có thể được suy ra từ FIRST và FOLLOW. Nếu một production có thể sinh epsilon, FOLLOW giúp xác định token nào cho phép kết thúc nonterminal.

Parser có thể hiển thị một số token dễ hiểu thay vì toàn bộ token nội bộ:

~~~text
Expected one of: identifier, number, '('
~~~

### 20.2 Error recovery

Khi gặp lỗi, parser có thể:

- Dừng ngay (fail-fast).
- Bỏ token đến một điểm đồng bộ (synchronization token).
- Chèn token còn thiếu nếu có thể suy luận an toàn.
- Bỏ qua token thừa.
- Tiếp tục parse phần sau để báo nhiều lỗi.

Các token đồng bộ thường gồm dấu chấm phẩy, dấu đóng block hoặc từ khóa bắt đầu câu lệnh mới. Lookahead giúp nhận diện điểm mà parser có thể tiếp tục.

### 20.3 Tránh recovery quá rộng

Nếu parser bỏ qua quá nhiều token, lỗi gốc có thể tạo ra nhiều lỗi giả phía sau. Hãy chọn tập đồng bộ theo cấu trúc grammar và giữ source span của lỗi đầu tiên.

## 21. Lookahead và hiệu năng

Lookahead thường rẻ khi token stream đã có buffer, nhưng chi phí thực tế phụ thuộc cách triển khai.

Các yếu tố:

- Số token cần xem trước.
- Token có được tạo lazy hay đã được lex toàn bộ.
- Buffer có phải giữ token để backtracking không.
- Có semantic predicate gọi symbol table hoặc dịch vụ không.
- Có parse lại cùng vùng input không.
- Có memoization hoặc caching không.

### 21.1 Tránh lookahead không giới hạn

Nếu parser phải quét đến cuối một cấu trúc tùy độ dài trước khi quyết định, cần xem xét lại grammar. Có thể:

- Tách cú pháp bằng keyword hoặc delimiter.
- Left factor các nhánh.
- Dùng parser strategy phù hợp.
- Dùng semantic phase sau parsing thay vì quyết định quá sớm.

### 21.2 Token buffering

Với parser LL(k), buffer thường cần giữ ít nhất k token chưa tiêu thụ. Với backtracking, buffer có thể cần giữ nhiều hơn vì parser phải quay lại điểm đánh dấu.

Nếu parser streaming, cần cân nhắc giới hạn buffer và cách xử lý khi lookahead yêu cầu dữ liệu chưa đến.

### 21.3 Đo hiệu năng

Không nên tối ưu bằng cách giảm k một cách tùy tiện nếu điều đó làm grammar sai. Hãy đo trên file DSL đại diện và xem:

- Thời gian lex.
- Thời gian parse.
- Số token được xem trước.
- Số lần backtrack.
- Số lần predicate được gọi.
- Bộ nhớ của token buffer và memoization.

## 22. Các lỗi thiết kế thường gặp

### Chỉ nhìn một token dù grammar cần nhiều hơn

Hai nhánh cùng bắt đầu bằng một token sẽ không thể được phân biệt chỉ bằng LL(1).

**Cách xử lý:** dùng lookahead phù hợp, left factoring hoặc thay đổi grammar.

### Tăng lookahead mà không hiểu xung đột

Tăng k có thể chỉ che giấu một grammar khó hiểu và làm parser phụ thuộc vào prefix dài.

**Cách xử lý:** tính FIRST/FOLLOW, xác định prefix chung và cân nhắc cấu trúc cú pháp rõ hơn.

### Consume token khi chỉ muốn kiểm tra

Nếu hàm check vô tình tiêu thụ token, các hàm parse sau đó sẽ bắt đầu sai vị trí.

**Cách xử lý:** tách rõ peek/lookahead và consume; đặt tên API thể hiện tác dụng.

### Backtracking nhưng không rollback trạng thái

Parser quay lại token nhưng symbol table, AST builder hoặc semantic action vẫn giữ thay đổi từ nhánh thất bại.

**Cách xử lý:** trì hoãn side effect, dùng transaction cho parser state hoặc thiết kế predicate thuần.

### Dùng thứ tự alternative như ưu tiên ngoài ý muốn

Trong CFG thông thường, thứ tự production không mặc nhiên là ưu tiên. Trong PEG, ordered choice có semantics rõ.

**Cách xử lý:** hiểu parser model và khai báo precedence/priority một cách tường minh.

### Bỏ qua EOF

Parser có thể chấp nhận một prefix hợp lệ rồi bỏ qua phần còn lại.

**Cách xử lý:** yêu cầu EOF ở entry rule khi parse một tài liệu hoàn chỉnh.

### Dùng semantic predicate để thay grammar

Predicate phức tạp có thể làm parser phụ thuộc symbol table và trạng thái khó tái lập.

**Cách xử lý:** chỉ dùng predicate khi quyết định thực sự phụ thuộc ngữ nghĩa; ưu tiên cú pháp rõ và phân tích nhiều giai đoạn.

## 23. Quy trình thiết kế và xử lý lookahead

Khi một điểm trong grammar cần lựa chọn nhánh, có thể làm theo các bước:

1. **Liệt kê alternatives:** ghi rõ các production parser có thể chọn.
2. **Xác định prefix chung:** so sánh token đầu của từng nhánh.
3. **Tính FIRST:** tìm token có thể bắt đầu mỗi production.
4. **Tính nullable và FOLLOW:** xử lý đúng các nhánh có epsilon.
5. **Kiểm tra xung đột:** xem các tập dự đoán có giao nhau không.
6. **Chọn chiến lược:** LL(1), LL(k), left factoring, predicate, backtracking hoặc parser khác.
7. **Tách peek và consume:** bảo đảm quan sát token không làm thay đổi vị trí.
8. **Xác định EOF và điểm đồng bộ:** hỗ trợ kết thúc và phục hồi lỗi.
9. **Viết test quyết định:** dùng input đại diện cho từng nhánh và prefix chung.
10. **Đo khi cần:** kiểm tra buffer, backtracking và predicate trên input lớn.

Một grammar tốt giúp quyết định lookahead dễ giải thích. Nếu người viết parser phải thêm nhiều điều kiện đặc biệt để đoán ý định, có thể grammar cần được tổ chức lại.

## 24. Ví dụ tổng hợp: parser cho câu lệnh DSL

Giả sử DSL có:

~~~text
let total = 100
print(total)
total = total + 10
~~~

Grammar:

~~~text
statement
    -> variableDeclaration
    | printStatement
    | assignment

variableDeclaration
    -> LET IDENTIFIER EQUAL expression SEMICOLON

printStatement
    -> PRINT LPAREN expression RPAREN SEMICOLON

assignment
    -> IDENTIFIER EQUAL expression SEMICOLON
~~~

### 24.1 Quyết định theo token đầu

| Lookahead(1) | Nhánh |
|---|---|
| LET | variableDeclaration |
| PRINT | printStatement |
| IDENTIFIER | cần xem tiếp |
| token khác | lỗi cú pháp |

### 24.2 Quyết định khi token đầu là identifier

Xem lookahead(2):

| Lookahead(2) | Nhánh |
|---|---|
| EQUAL | assignment |
| LPAREN | có thể là expression/call statement nếu grammar hỗ trợ |
| token khác | lỗi theo grammar hiện tại |

### 24.3 Parser minh họa

~~~java
Statement parseStatement() {
    return switch (tokens.current().type()) {
        case LET -> parseVariableDeclaration();
        case PRINT -> parsePrintStatement();
        case IDENTIFIER -> parseIdentifierStatement();
        default -> throw error("Expected a statement");
    };
}

Statement parseIdentifierStatement() {
    Token name = expect(TokenType.IDENTIFIER);

    if (match(TokenType.EQUAL)) {
        Expression value = parseExpression();
        expect(TokenType.SEMICOLON);
        return new Assignment(name, value);
    }

    if (match(TokenType.LPAREN)) {
        List<Expression> args = parseArgumentsAfterOpenParen();
        expect(TokenType.SEMICOLON);
        return new CallStatement(name, args);
    }

    throw error("Expected '=' or '(' after identifier");
}
~~~

Trong grammar ở trên, nhánh assignment được nêu rõ. Nếu DSL không có call statement, parser không nên tự chấp nhận LPAREN chỉ vì token đó xuất hiện. Tập token hợp lệ phải phản ánh đúng grammar được công bố.

## 25. Câu hỏi tự kiểm tra

1. Lookahead là gì và khác consume như thế nào?
2. Phân biệt lookahead trong lexer và parser.
3. Ký hiệu LL(k) biểu thị những đặc điểm nào?
4. FIRST, FOLLOW và nullable được dùng để xây dựng quyết định dự đoán ra sao?
5. Điều kiện cơ bản để hai production có thể được chọn bằng LL(1) là gì?
6. Khi một nhánh nullable, vì sao phải xét FOLLOW?
7. Left factoring giúp giảm xung đột lookahead như thế nào?
8. Backtracking có ưu điểm và chi phí gì?
9. PEG ordered choice khác CFG alternatives như thế nào?
10. Semantic predicate hữu ích trong trường hợp nào?
11. Vì sao parser cần yêu cầu EOF ở entry rule?
12. Lookahead hỗ trợ error recovery và expected-token diagnostics ra sao?
13. Khi nào nên dùng LL(k), khi nào nên thay đổi grammar?
14. Vì sao precedence không thể được quyết định chỉ bằng cách nhìn token kế tiếp?

Lookahead là cơ chế giúp parser đưa ra quyết định có căn cứ tại những điểm grammar có nhiều lựa chọn. Khi kết hợp token stream rõ ràng, FIRST/FOLLOW, grammar phù hợp và chiến lược xử lý lỗi nhất quán, parser DSL có thể vừa dự đoán chính xác vừa dễ bảo trì.
