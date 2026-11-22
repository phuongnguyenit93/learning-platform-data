# Parser LL và LR

Trong quá trình xây dựng ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), parser có nhiệm vụ xác định chuỗi token có tuân theo grammar hay không và chuyển chuỗi đó thành cấu trúc cú pháp như cây phân tích (parse tree) hoặc cây cú pháp trừu tượng (Abstract Syntax Tree — AST). Cách parser lựa chọn các quy tắc grammar ảnh hưởng đến khả năng biểu đạt của DSL, độ phức tạp triển khai, chất lượng thông báo lỗi và khả năng mở rộng ngôn ngữ.

Hai họ kỹ thuật phân tích cú pháp quan trọng là **LL** và **LR**. LL phân tích từ trên xuống (top-down), bắt đầu từ ký hiệu bắt đầu của grammar và dự đoán các production cần dùng. LR phân tích từ dưới lên (bottom-up), đọc token từ trái sang phải và dần rút gọn các phần đã nhận diện thành nonterminal.

Cả hai đều có thể phân tích nhiều ngôn ngữ phi ngữ cảnh (context-free language), nhưng có cách tổ chức khác nhau và hỗ trợ các lớp grammar khác nhau. LL thường dễ viết thủ công bằng recursive descent; LR thường phù hợp với grammar phức tạp hơn và thường được sinh bằng parser generator.

Bài học này giải thích nguyên lý của hai phương pháp, cách xây dựng parser, các biến thể phổ biến, xung đột grammar và cách lựa chọn chiến lược phù hợp khi thiết kế DSL.

## 1. Parser trong kiến trúc của DSL

Parser là một phần của pipeline xử lý DSL. Thông thường, văn bản nguồn được lexer chuyển thành token trước khi parser phân tích cấu trúc.

~~~text
Văn bản DSL
    |
    v
Lexer / Scanner
    |
    v
Chuỗi token
    |
    v
Parser (LL hoặc LR)
    |
    v
Parse tree / AST
    |
    v
Phân tích ngữ nghĩa
    |
    v
Mô hình đã kiểm tra / chương trình
    |
    v
Thực thi hoặc sinh mã
~~~

Ví dụ, lexer có thể chuyển câu lệnh:

~~~text
set total = price * quantity;
~~~

thành chuỗi token:

~~~text
SET IDENTIFIER EQUALS IDENTIFIER STAR IDENTIFIER SEMICOLON
~~~

Parser xác định set mở đầu một câu lệnh gán, price * quantity là biểu thức và dấu chấm phẩy kết thúc câu lệnh. Sau đó, bước ngữ nghĩa có thể kiểm tra total, price và quantity đã được khai báo hay chưa, kiểu của chúng có phù hợp với phép nhân và phép gán hay không.

Parser chủ yếu xử lý cấu trúc cú pháp. Nó không tự bảo đảm mọi tên đều tồn tại, mọi kiểu đều đúng hoặc mọi quy tắc nghiệp vụ đều được thỏa mãn.

### 1.1. Grammar và production

Grammar phi ngữ cảnh thường được mô tả bằng các production có dạng:

~~~text
Nonterminal -> sequence of symbols
~~~

- **Terminal:** token thực sự xuất hiện trong đầu vào, chẳng hạn IDENTIFIER, PLUS, IF.
- **Nonterminal:** ký hiệu đại diện cho một cấu trúc cú pháp, chẳng hạn Expression, Statement.
- **Production:** quy tắc mô tả một nonterminal có thể được tạo từ những ký hiệu nào.
- **Start symbol:** nonterminal bắt đầu quá trình phân tích.

Ví dụ grammar biểu thức đơn giản:

~~~text
Expression -> Expression "+" Term
            | Term

Term       -> Term "*" Factor
            | Factor

Factor     -> IDENTIFIER
            | NUMBER
            | "(" Expression ")"
~~~

Grammar này thể hiện phép nhân có mức cấu trúc nằm sâu hơn phép cộng. Nó cũng có đệ quy trái ở Expression và Term, điều có ý nghĩa khi chọn parser LL hay LR.

### 1.2. Parse tree và AST

Parse tree thể hiện các nonterminal và terminal theo đúng production đã sử dụng. AST thường loại bỏ các chi tiết cú pháp không cần thiết, chẳng hạn dấu chấm phẩy hoặc dấu ngoặc dùng để nhóm, và giữ cấu trúc có ý nghĩa cho các bước sau.

Với biểu thức:

~~~text
a + b * c
~~~

AST có thể là:

~~~text
       Add
      /   \
     a    Multiply
          /      \
         b        c
~~~

Cả parser LL và LR đều có thể tạo AST tương đương nếu dùng cùng ngữ nghĩa. Khác biệt nằm ở cách nhận diện cấu trúc, không nằm ở loại mô hình miền mà DSL cuối cùng phải tạo ra.

## 2. Phân tích từ trên xuống và từ dưới lên

Khác biệt cơ bản giữa LL và LR là hướng xây dựng dẫn xuất.

### 2.1. LL: phân tích từ trên xuống

LL là viết tắt của:

- **L thứ nhất:** đọc đầu vào từ trái sang phải (Left-to-right).
- **L thứ hai:** xây dựng dẫn xuất trái nhất (Leftmost derivation).

Parser bắt đầu từ start symbol, sau đó chọn production để mở rộng nonterminal. Nó dự đoán cấu trúc cần có dựa trên token tiếp theo.

Ví dụ, với grammar:

~~~text
Statement -> "print" Expression ";"
           | "delete" Identifier ";"
~~~

Nếu token đầu tiên là PRINT, parser chọn nhánh print. Nếu token đầu tiên là DELETE, parser chọn nhánh delete.

LL thường được gọi là predictive parsing khi parser có thể chọn production dựa trên lookahead mà không cần thử rồi quay lui.

### 2.2. LR: phân tích từ dưới lên

LR là viết tắt của:

- **L:** đọc đầu vào từ trái sang phải (Left-to-right).
- **R:** xây dựng dẫn xuất phải nhất theo thứ tự đảo ngược (Rightmost derivation in reverse).

Parser LR bắt đầu từ token đầu vào và dùng stack để nhận diện các chuỗi con khớp vế phải của production. Khi tìm được một chuỗi con cần rút gọn, parser thay chuỗi đó bằng nonterminal ở vế trái.

Ví dụ, với:

~~~text
Expression -> Expression "+" Term
            | Term

Term       -> NUMBER
~~~

Khi đọc NUMBER, parser có thể rút gọn thành Term, rồi thành Expression. Khi đọc thêm + NUMBER, nó có thể rút gọn phần Term và cuối cùng rút gọn toàn bộ thành Expression.

LR không cần dự đoán toàn bộ cây từ start symbol. Nó tích lũy bằng chứng từ đầu vào và rút gọn khi đủ điều kiện.

### 2.3. Hình dung hai hướng

~~~text
LL — top-down

             Expression
                 |
          chọn production
                 |
          Term + Term
           /       \
       Factor     Factor
          |          |
         ...        ...


LR — bottom-up

   token token token token
       \    |    /
        nhận diện cụm
             |
          rút gọn
             |
          nonterminal
             |
       tiếp tục rút gọn
             |
         Start symbol
~~~

LL mở rộng từ cấu trúc tổng quát đến token cụ thể. LR kết hợp token thành các cấu trúc nhỏ rồi rút gọn thành cấu trúc lớn hơn.

## 3. Ý nghĩa ký hiệu LL(k) và LR(k)

Chữ số k cho biết số token lookahead mà parser có thể sử dụng trong mô hình tương ứng.

- **LL(1):** parser LL dùng một token lookahead để chọn production.
- **LL(k):** parser LL dùng tối đa k token lookahead.
- **LR(1):** parser LR dùng một token lookahead trong quyết định phân tích.
- **LR(k):** parser LR dùng k token lookahead.

Trong thực tế, LL(1) và LR(1) là những dạng được nhắc đến thường xuyên. Một số parser LL hiện đại có thể dùng lookahead động hoặc nhiều token; một số parser LR dùng bảng được nén hoặc hợp nhất trạng thái.

Không nên hiểu số 1 là parser chỉ đọc một token trong toàn bộ chương trình. Nó chỉ nói rằng một quyết định cụ thể có thể dựa trên một token nhìn trước. Parser vẫn đọc toàn bộ chuỗi token theo trình tự.

### 3.1. Lookahead trong LL

Ở LL(1), parser dùng nonterminal hiện tại và token lookahead để chọn production. FIRST và FOLLOW là các tập quan trọng để xây dựng bảng phân tích.

### 3.2. Lookahead trong LR

Ở LR(1), lookahead gắn với item LR giúp xác định khi nào được phép reduce. Parser có thể đã đọc một phần đầu vào và đang giữ một cấu trúc trên stack; token tiếp theo quyết định hành động reduce có hợp lệ trong ngữ cảnh đó hay không.

Lookahead trong LL và LR cùng quan sát token phía trước, nhưng vai trò trong thuật toán khác nhau.

## 4. Parser LL(1) và bảng phân tích dự đoán

Parser LL(1) có thể được triển khai bằng đệ quy xuống hoặc bằng bảng phân tích. Để xây dựng bảng, cần tính FIRST và FOLLOW của grammar.

### 4.1. FIRST

FIRST(X) là tập terminal có thể xuất hiện đầu tiên trong chuỗi được sinh ra từ ký hiệu X. Nếu X có thể sinh chuỗi rỗng, FIRST(X) chứa epsilon (ε).

Ví dụ:

~~~text
Statement -> "print" Expression ";"
           | "delete" Identifier ";"
~~~

Ta có:

~~~text
FIRST(Statement) = { PRINT, DELETE }
~~~

Với production có phần tùy chọn:

~~~text
OptionalArgument -> Expression | ε
~~~

ta có:

~~~text
FIRST(OptionalArgument) = { FIRST(Expression), ε }
~~~

Khi tính FIRST của một chuỗi ký hiệu, nếu ký hiệu đầu có thể sinh epsilon thì tiếp tục xét ký hiệu kế tiếp.

### 4.2. FOLLOW

FOLLOW(A) là tập terminal có thể xuất hiện ngay sau nonterminal A trong một dẫn xuất hợp lệ. EOF thường thuộc FOLLOW của start symbol.

Ví dụ:

~~~text
Call      -> IDENTIFIER "(" Arguments ")"
Statement -> Call ";"
~~~

Dấu chấm phẩy có thể đứng ngay sau Call, vì vậy SEMICOLON thuộc FOLLOW(Call).

FOLLOW đặc biệt quan trọng khi một production có thể sinh epsilon. Parser dùng FOLLOW của nonterminal để biết lúc nào phần tùy chọn có thể được bỏ qua.

### 4.3. Tập dự đoán và bảng LL(1)

Với production A -> α, tập dự đoán thường được xác định từ FIRST(α). Nếu α có thể sinh epsilon, cần thêm FOLLOW(A).

Bảng LL(1) có hàng là nonterminal và cột là terminal lookahead. Ô M[A, a] chứa production mà parser phải chọn khi đang phân tích A và nhìn thấy token a.

Xét grammar:

~~~text
Statement -> "print" Expression ";"
           | "delete" Identifier ";"
~~~

Bảng rút gọn:

| Nonterminal | PRINT | DELETE |
| --- | --- | --- |
| Statement | Statement -> PRINT Expression SEMICOLON | Statement -> DELETE IDENTIFIER SEMICOLON |

Mỗi ô chỉ có một production nên parser quyết định được bằng một token lookahead.

Nếu một ô cần chứa hai production khác nhau, grammar có xung đột LL(1). Parser không thể chọn duy nhất nhánh chỉ bằng một token ở vị trí đó.

## 5. Xây dựng grammar phù hợp với LL

Grammar LL(1) cần có những tính chất giúp parser dự đoán production. Hai biến đổi thường gặp là loại bỏ đệ quy trái và left factoring.

### 5.1. Đệ quy trái

Một production có đệ quy trái trực tiếp khi nonterminal xuất hiện ngay đầu vế phải:

~~~text
Expression -> Expression "+" Term
            | Term
~~~

Parser recursive descent gọi parseExpression rồi lại lập tức gọi parseExpression trước khi tiêu thụ token đầu vào. Điều này có thể dẫn đến đệ quy vô hạn.

Có thể chuyển grammar sang dạng không đệ quy trái:

~~~text
Expression -> Term ExpressionTail
ExpressionTail -> "+" Term ExpressionTail
                | ε
~~~

Với phép nhân:

~~~text
Term -> Factor TermTail
TermTail -> "*" Factor TermTail
           | ε
~~~

Grammar mới phù hợp hơn với parser LL(1).

### 5.2. Left factoring

Nếu nhiều production có cùng tiền tố, parser có thể chưa biết chọn nhánh nào. Left factoring đưa phần chung ra trước.

Grammar ban đầu:

~~~text
Statement -> IDENTIFIER "=" Expression ";"
           | IDENTIFIER "(" Arguments ")" ";"
~~~

Grammar sau khi left factoring:

~~~text
Statement -> IDENTIFIER StatementTail
StatementTail -> "=" Expression ";"
               | "(" Arguments ")" ";"
~~~

Sau khi đọc IDENTIFIER, parser nhìn token tiếp theo để phân biệt dấu bằng với dấu ngoặc mở.

### 5.3. Giới hạn của biến đổi grammar

Không phải mọi grammar đều trở thành LL(1) chỉ bằng vài phép biến đổi đơn giản. Một số grammar cần nhiều token lookahead hoặc không thuộc lớp LL(k) với bất kỳ k hữu hạn nào.

Việc biến đổi cũng có thể làm grammar dài hơn hoặc khiến AST cần xử lý thêm các node phụ. Khi thiết kế DSL, cần cân bằng giữa grammar dễ phân tích và cú pháp tự nhiên, dễ đọc.

## 6. Triển khai parser LL bằng recursive descent

Recursive descent là cách triển khai LL phổ biến. Mỗi hàm parser thường tương ứng với một nonterminal hoặc một cấu trúc cú pháp.

Với grammar:

~~~text
Expression -> Term ExpressionTail
ExpressionTail -> "+" Term ExpressionTail | ε

Term -> Factor TermTail
TermTail -> "*" Factor TermTail | ε

Factor -> NUMBER
        | IDENTIFIER
        | "(" Expression ")"
~~~

Có thể viết các hàm như parseExpression, parseTerm và parseFactor.

### 6.1. Hàm peek, match và expect

Parser thường cung cấp một số thao tác cơ bản:

~~~java
Token peek() {
    return tokens.get(position);
}

Token advance() {
    Token current = peek();
    if (current.type() != EOF) {
        position++;
    }
    return current;
}

boolean check(TokenType type) {
    return peek().type() == type;
}

boolean match(TokenType type) {
    if (!check(type)) {
        return false;
    }
    advance();
    return true;
}

Token expect(TokenType type) {
    if (check(type)) {
        return advance();
    }
    throw error(peek(), "Expected " + type);
}
~~~

peek quan sát token hiện tại mà không tiêu thụ; advance tiêu thụ token; match tiêu thụ khi khớp; expect yêu cầu token cụ thể và báo lỗi nếu không có.

### 6.2. Hàm phân tích biểu thức

Ví dụ minh họa:

~~~java
Expression parseExpression() {
    Expression left = parseTerm();

    while (match(PLUS)) {
        Expression right = parseTerm();
        left = new BinaryExpression(left, PLUS, right);
    }

    return left;
}

Expression parseTerm() {
    Expression left = parseFactor();

    while (match(STAR)) {
        Expression right = parseFactor();
        left = new BinaryExpression(left, STAR, right);
    }

    return left;
}

Expression parseFactor() {
    if (match(NUMBER)) {
        return new NumberLiteral(previous());
    }

    if (match(IDENTIFIER)) {
        return new NameExpression(previous());
    }

    if (match(LEFT_PAREN)) {
        Expression nested = parseExpression();
        expect(RIGHT_PAREN);
        return nested;
    }

    throw error(peek(), "Expected a number, name, or parenthesized expression");
}
~~~

Với biểu thức a + b * c, parseExpression gọi parseTerm cho vế trái và vế phải. parseTerm xử lý phép nhân trước, do đó AST có cấu trúc a + (b * c).

Vòng lặp ở parseExpression và parseTerm tạo phép cộng và phép nhân kết hợp trái. Nếu DSL cần kết hợp phải, ví dụ phép lũy thừa, cần grammar và cách xây AST tương ứng.

### 6.3. Ưu điểm và giới hạn của recursive descent

Ưu điểm:

- Mã parser gần với cấu trúc grammar.
- Dễ gỡ lỗi và đặt breakpoint.
- Có thể viết thông báo lỗi riêng cho từng cấu trúc.
- Dễ tích hợp với AST và logic đặc thù của DSL.
- Phù hợp với grammar vừa và nhỏ, đặc biệt khi cú pháp được thiết kế có chủ đích cho LL.

Giới hạn:

- Cần xử lý đệ quy trái trước khi triển khai theo cách thông thường.
- Grammar lớn có thể tạo ra nhiều hàm và nhánh điều kiện.
- Lookahead hoặc xử lý ngoại lệ phức tạp có thể làm parser khó duy trì.
- Cần cẩn thận với phục hồi lỗi để tránh lỗi dây chuyền.

## 7. Parser LL dạng bảng

Ngoài recursive descent, LL(1) có thể được triển khai bằng một bảng phân tích và stack.

Parser duy trì:

- Stack chứa các terminal và nonterminal cần xử lý.
- Chuỗi token đầu vào.
- Bảng M[A, a] xác định production khi đỉnh stack là nonterminal A và lookahead là a.

Thuật toán khái quát:

1. Đẩy EOF và start symbol vào stack.
2. Đọc token lookahead hiện tại.
3. Nếu đỉnh stack là terminal và trùng lookahead, pop và tiêu thụ token.
4. Nếu đỉnh stack là nonterminal, tra bảng M[A, lookahead].
5. Nếu có production, pop A rồi đẩy vế phải vào stack theo thứ tự ngược.
6. Nếu stack và đầu vào cùng kết thúc tại EOF, chấp nhận.
7. Nếu không có hành động hợp lệ, báo lỗi.

Ví dụ, nếu stack cần Statement và lookahead là PRINT, bảng trả về:

~~~text
Statement -> PRINT Expression SEMICOLON
~~~

Parser thay Statement trên stack bằng các ký hiệu của vế phải theo thứ tự phù hợp với stack.

Parser dạng bảng có ưu điểm là thuật toán dùng chung, grammar được biểu diễn trong bảng. Tuy nhiên, để tạo thông báo lỗi thân thiện và gắn hành động xây AST, cần thiết kế thêm metadata hoặc semantic action.

## 8. Parser LR: nguyên lý shift và reduce

LR là parser bottom-up. Nó sử dụng stack và bảng điều khiển để quyết định cách xử lý token hiện tại.

Bốn hành động cơ bản:

- **Shift:** đẩy token đầu vào vào stack và chuyển sang token kế tiếp.
- **Reduce:** nhận diện một chuỗi trên stack khớp vế phải của production, rồi thay bằng nonterminal ở vế trái.
- **Accept:** xác nhận đầu vào hợp lệ.
- **Error:** không có hành động hợp lệ cho trạng thái và lookahead hiện tại.

Ví dụ grammar:

~~~text
Expression -> Expression "+" Term
            | Term
Term       -> NUMBER
~~~

Với đầu vào:

~~~text
NUMBER + NUMBER EOF
~~~

Parser có thể:

1. Shift NUMBER.
2. Reduce NUMBER thành Term.
3. Reduce Term thành Expression nếu trạng thái cho phép.
4. Shift dấu cộng.
5. Shift NUMBER.
6. Reduce NUMBER thành Term.
7. Reduce Expression + Term thành Expression.
8. Accept khi gặp EOF ở trạng thái chấp nhận.

Đây là trình tự minh họa; hành động cụ thể phụ thuộc bảng trạng thái được sinh từ grammar. Điểm quan trọng là LR có thể đợi cho đến khi một cụm token đủ hoàn chỉnh rồi mới reduce.

### 8.1. Stack của parser LR

Một triển khai LR thường giữ stack trạng thái; một số cách trình bày còn giữ cả ký hiệu grammar tương ứng.

Khái niệm:

~~~text
Stack:  state0 ... stateN
Input:  token ... EOF
Action: shift / reduce / accept / error
~~~

Sau mỗi shift hoặc reduce, parser dùng trạng thái trên đỉnh stack và lookahead để tra bảng ACTION. Sau reduce, parser dùng nonterminal vừa tạo và trạng thái còn lại trên stack để tra bảng GOTO.

### 8.2. Bảng ACTION và GOTO

Bảng LR thường có hai phần:

- **ACTION[state, terminal]:** quyết định shift, reduce, accept hoặc error.
- **GOTO[state, nonterminal]:** xác định trạng thái tiếp theo sau khi reduce thành nonterminal.

Ví dụ khái quát:

| Trạng thái | NUMBER | PLUS | EOF | GOTO(Expression) | GOTO(Term) |
| --- | --- | --- | --- | --- | --- |
| s0 | shift s2 | error | error | s1 | s3 |
| s1 | error | shift s4 | accept | — | — |
| s2 | reduce theo grammar | reduce theo grammar | reduce theo grammar | — | — |

Bảng trên chỉ minh họa hình thức, không phải bảng hoàn chỉnh của một grammar cụ thể. Trong parser thật, số trạng thái và các hành động được sinh từ tập LR items.

## 9. LR items và automaton trạng thái

Để tạo bảng LR, parser generator xây dựng các trạng thái từ LR items. Một item biểu diễn vị trí đã nhận diện trong một production.

Ví dụ:

~~~text
Expression -> Expression "+" . Term
~~~

Dấu chấm cho biết parser đã nhận diện Expression + và đang chờ Term.

Một item hoàn tất:

~~~text
Expression -> Expression "+" Term .
~~~

Dấu chấm ở cuối cho biết toàn bộ vế phải đã được nhận diện. Tùy loại LR và lookahead, parser có thể thực hiện reduce bằng production tương ứng.

### 9.1. Augmented grammar

Trước khi xây automaton, grammar thường được mở rộng bằng một start production mới:

~~~text
Start' -> Start
~~~

Production bổ sung giúp xác định trạng thái accept. Khi parser hoàn tất Start và gặp EOF theo điều kiện chấp nhận, đầu vào được công nhận hợp lệ.

### 9.2. Closure và GOTO

Hai thao tác quan trọng khi xây các tập item:

- **Closure(I):** bổ sung các item cần thiết khi dấu chấm đứng trước một nonterminal, để mô tả những production có thể bắt đầu từ đó.
- **GOTO(I, X):** chuyển từ tập item I sang tập item sau khi nhận diện ký hiệu X.

Bằng cách lặp closure và GOTO từ trạng thái ban đầu, parser generator xây dựng automaton hữu hạn. Mỗi trạng thái biểu diễn một tập khả năng phân tích tại vị trí hiện tại.

Không cần tự xây automaton LR bằng tay trong phần lớn dự án DSL. Tuy nhiên, hiểu items, closure và GOTO giúp đọc báo cáo xung đột của parser generator và hiểu vì sao một grammar không tạo được bảng mong muốn.

## 10. Các biến thể parser LR

Có nhiều biến thể LR, khác nhau ở lượng thông tin lookahead và cách xây dựng hoặc gộp trạng thái.

### 10.1. LR(0)

LR(0) items không gắn token lookahead riêng. Khi một item hoàn tất, quyết định reduce ít được giới hạn bởi ngữ cảnh token tiếp theo hơn, vì vậy lớp grammar xử lý được nhỏ hơn các biến thể có lookahead.

LR(0) đơn giản về mặt khái niệm nhưng thường không đủ cho grammar thực tế có nhiều lựa chọn reduce.

### 10.2. SLR(1)

SLR (Simple LR) dùng các trạng thái LR(0), kết hợp tập FOLLOW của nonterminal để xác định những token nào cho phép reduce.

Cách này đơn giản hơn canonical LR(1), nhưng FOLLOW có thể quá rộng và tạo ra xung đột mà grammar thực tế không có trong từng trạng thái cụ thể.

### 10.3. LALR(1)

LALR (Look-Ahead LR) bắt đầu từ thông tin LR(1), sau đó hợp nhất các trạng thái có cùng lõi LR(0) và kết hợp thông tin lookahead tương ứng.

LALR thường tạo bảng nhỏ hơn canonical LR(1), trong khi vẫn xử lý được nhiều grammar thực tế. Đây là lựa chọn truyền thống của nhiều parser generator kiểu yacc.

Việc hợp nhất trạng thái đôi khi có thể tạo ra xung đột mới mà canonical LR(1) không có.

### 10.4. Canonical LR(1)

Canonical LR(1) giữ thông tin lookahead chi tiết cho từng item trong từng trạng thái. Nó thường xử lý được nhiều grammar hơn SLR(1) và LALR(1), nhưng có thể tạo số trạng thái lớn hơn đáng kể.

### 10.5. So sánh các biến thể

| Biến thể | Thông tin dùng để reduce | Đặc điểm |
| --- | --- | --- |
| LR(0) | Item và trạng thái, không có lookahead riêng | Đơn giản, giới hạn hơn |
| SLR(1) | FOLLOW của nonterminal | Bảng tương đối gọn, FOLLOW có thể quá rộng |
| LALR(1) | Lookahead LR(1) sau khi hợp nhất lõi trạng thái | Cân bằng kích thước và khả năng phân tích |
| Canonical LR(1) | Lookahead riêng trong từng item | Mạnh hơn, thường có nhiều trạng thái |

Không nên coi các biến thể là các phiên bản chỉ khác tốc độ. Chúng có khả năng nhận diện grammar khác nhau và có thể tạo ra tập xung đột khác nhau.

## 11. Xung đột trong parser LR

Khi một ô ACTION cần chứa nhiều hơn một hành động, parser generator báo xung đột. Hai dạng phổ biến là shift/reduce và reduce/reduce.

### 11.1. Shift/reduce conflict

Parser không biết nên shift token hiện tại để tiếp tục đọc hay reduce phần đã nhận diện.

Một ví dụ quen thuộc là biểu thức:

~~~text
Expression -> Expression "+" Expression
            | Expression "*" Expression
            | NUMBER
~~~

Với đầu vào a + b * c, sau khi nhận diện a + b, parser có thể đứng trước *. Nó cần quyết định reduce a + b thành Expression hay shift * để tiếp tục xây phần nhân.

Nếu grammar không quy định độ ưu tiên, parser có thể có xung đột. Cách xử lý:

- Viết grammar theo các tầng precedence.
- Khai báo precedence và associativity trong công cụ parser generator nếu được hỗ trợ.
- Dùng dấu ngoặc bắt buộc để làm rõ cấu trúc.
- Chỉ định quy tắc giải quyết xung đột khi đó thực sự là ý định của DSL.

### 11.2. Reduce/reduce conflict

Parser có thể reduce cùng một chuỗi theo hai production khác nhau.

Ví dụ, grammar có hai nonterminal tạo ra cùng một token:

~~~text
Value -> IDENTIFIER
Name  -> IDENTIFIER
Item  -> Value
       | Name
~~~

Khi gặp IDENTIFIER, parser có thể không biết nên reduce thành Value hay Name. Có thể cần tái cấu trúc grammar để hai khái niệm không cạnh tranh cùng một chuỗi đầu vào, hoặc bổ sung dấu hiệu cú pháp phân biệt.

Reduce/reduce conflict thường là dấu hiệu grammar có các cách phân loại chồng lấn hoặc thiếu quy tắc phân biệt.

### 11.3. Không nên bỏ qua cảnh báo xung đột

Một số công cụ cho phép chọn hành động mặc định khi có xung đột. Dựa vào lựa chọn mặc định có thể khiến parser chạy được nhưng ngữ nghĩa không đúng như người thiết kế mong muốn.

Mỗi xung đột cần được hiểu và xử lý có chủ đích. Nếu chấp nhận một xung đột vì ngữ nghĩa đã rõ, cần ghi lại lý do và có kiểm thử cho các trường hợp liên quan.

## 12. Độ ưu tiên và tính kết hợp của toán tử

Grammar cần mô tả cách nhóm biểu thức. Hai khái niệm quan trọng:

- **Precedence (độ ưu tiên):** toán tử nào được nhóm trước.
- **Associativity (tính kết hợp):** các toán tử cùng mức ưu tiên được nhóm từ trái sang phải hay từ phải sang trái.

Ví dụ, với a + b * c, phép nhân thường có độ ưu tiên cao hơn phép cộng:

~~~text
a + (b * c)
~~~

Với a - b - c, phép trừ thường kết hợp trái:

~~~text
(a - b) - c
~~~

Với phép lũy thừa, nhiều ngôn ngữ chọn kết hợp phải:

~~~text
a ^ (b ^ c)
~~~

### 12.1. Mã hóa precedence trong grammar LL

Một grammar phân tầng:

~~~text
Expression -> Term { ("+" | "-") Term }
Term       -> Factor { ("*" | "/") Factor }
Factor     -> NUMBER
            | IDENTIFIER
            | "(" Expression ")"
~~~

Tầng Expression xử lý cộng trừ; Term xử lý nhân chia; Factor xử lý phần tử cơ bản và biểu thức trong ngoặc.

### 12.2. Khai báo precedence trong LR

Một parser generator LR có thể hỗ trợ khai báo precedence và associativity cho terminal. Khi có xung đột shift/reduce, công cụ có thể dùng những khai báo này để chọn shift hoặc reduce.

Cách này tiện cho grammar biểu thức, nhưng quy tắc phải nhất quán với ngữ nghĩa DSL. Không nên dựa vào precedence mặc định không được tài liệu hóa.

## 13. So sánh LL và LR

Hai họ parser có các đặc điểm khác nhau về cách triển khai, yêu cầu grammar và cách xử lý lỗi.

| Tiêu chí | LL | LR |
| --- | --- | --- |
| Hướng phân tích | Từ trên xuống | Từ dưới lên |
| Dẫn xuất | Trái nhất | Phải nhất theo thứ tự đảo ngược |
| Cách ra quyết định | Dự đoán production từ nonterminal và lookahead | Dùng trạng thái, stack và lookahead để shift/reduce |
| Đệ quy trái | Thường phải loại bỏ khi dùng predictive recursive descent | Có thể xử lý trực tiếp |
| Grammar | Cần tổ chức phù hợp với dự đoán | Xử lý được nhiều grammar phi ngữ cảnh hơn |
| Triển khai thủ công | Recursive descent tương đối dễ hiểu | Xây bảng LR thủ công phức tạp |
| Parser generator | Có công cụ LL và predictive parsing | Có nhiều công cụ LALR/LR |
| Thông báo lỗi | Có thể dễ tùy chỉnh theo từng hàm parser | Có thể cần cấu hình và cơ chế phục hồi từ bảng trạng thái |
| Phù hợp | DSL có grammar rõ, ít mơ hồ, cần parser dễ đọc | DSL có grammar phức tạp, cú pháp biểu thức hoặc đệ quy trái |

Bảng này mô tả xu hướng chung. Parser LL hiện đại có thể hỗ trợ lookahead mạnh hơn LL(1), còn parser LR có thể được tùy chỉnh để báo lỗi rất tốt. Chất lượng công cụ và cách thiết kế grammar quan trọng không kém tên thuật toán.

### 13.1. LL không phải lúc nào cũng đơn giản hơn

Recursive descent thường dễ đọc, nhưng grammar lớn có nhiều ngoại lệ hoặc phụ thuộc ngữ cảnh có thể khiến mã parser trở nên phức tạp. Nếu phải viết nhiều lookahead thủ công, backtracking hoặc semantic predicate, lợi thế đơn giản giảm đi.

### 13.2. LR không phải lúc nào cũng tốt hơn

LR xử lý được nhiều grammar hơn trong các lớp tương ứng, nhưng bảng trạng thái và báo cáo xung đột có thể khó hiểu với người mới. Nếu DSL nhỏ và cú pháp có thể thiết kế rõ ràng cho LL, dùng LR có thể tạo thêm công cụ và quy trình không cần thiết.

## 14. Cùng một ngôn ngữ biểu thức dưới dạng LL và LR

Để thấy rõ sự khác nhau, xét biểu thức có cộng và nhân.

### 14.1. Grammar thiên về LR

~~~text
Expression -> Expression "+" Term
            | Term

Term       -> Term "*" Factor
            | Factor

Factor     -> IDENTIFIER
            | NUMBER
            | "(" Expression ")"
~~~

Grammar dùng đệ quy trái để biểu diễn phép cộng và phép nhân kết hợp trái. Parser LR có thể xử lý trực tiếp dạng này.

### 14.2. Grammar chuyển sang LL

~~~text
Expression -> Term ExpressionTail
ExpressionTail -> "+" Term ExpressionTail
                | ε

Term -> Factor TermTail
TermTail -> "*" Factor TermTail
           | ε

Factor -> IDENTIFIER
        | NUMBER
        | "(" Expression ")"
~~~

Grammar không còn đệ quy trái và cho phép parser dự đoán bằng lookahead phù hợp.

### 14.3. Cùng một AST

Với đầu vào:

~~~text
price + tax * quantity
~~~

Cả hai parser cần tạo AST tương đương:

~~~text
        Add
       /   \
   price   Multiply
           /      \
         tax    quantity
~~~

Grammar LL có các nonterminal đuôi như ExpressionTail và TermTail, nhưng những node này không nhất thiết xuất hiện trong AST cuối cùng. Parser có thể tạo AST trực tiếp trong vòng lặp.

Grammar LR dùng đệ quy trái và các reduce để tạo cấu trúc tương ứng. Ngữ nghĩa của biểu thức phải giống nhau dù cách phân tích khác nhau.

## 15. Xây dựng AST và semantic action

Parser thường cần tạo AST trong khi phân tích. Có thể gắn semantic action với production hoặc xây node trong các hàm parser.

Ví dụ, production:

~~~text
Expression -> Expression "+" Term
~~~

có thể tạo node:

~~~java
new BinaryExpression(left, PLUS, right)
~~~

Với LL recursive descent, node thường được tạo trực tiếp trong hàm parse. Với LR parser generator, có thể khai báo semantic action tại production hoặc nhận giá trị ngữ nghĩa từ stack.

### 15.1. Giữ parser tách khỏi tác động phụ

Không nên để việc parser nhận diện một production trực tiếp gửi email, cập nhật cơ sở dữ liệu hoặc gọi API bên ngoài. Parsing nên tạo cấu trúc mô tả trước; việc thực thi diễn ra ở bước sau khi cấu trúc và quyền hạn đã được kiểm tra.

Một pipeline rõ ràng:

~~~text
Parse
  |
  v
AST
  |
  v
Name resolution
  |
  v
Type and semantic validation
  |
  v
Validated model
  |
  v
Execution / code generation
~~~

Cách này giúp parser có thể chạy trong editor, kiểm thử và chế độ dry run mà không gây tác động nghiệp vụ.

### 15.2. Giữ vị trí nguồn trong AST

Mỗi node AST nên giữ source span hoặc vị trí dòng/cột tương ứng. Khi kiểm tra ngữ nghĩa hoặc thực thi phát hiện lỗi, hệ thống có thể chỉ ra đúng phần văn bản liên quan.

Điều này quan trọng với cả LL và LR. Parser generator cần được cấu hình để giữ vị trí token; parser thủ công cần truyền source location khi tạo node.

## 16. Phục hồi lỗi trong LL và LR

Parser không chỉ cần nhận đầu vào hợp lệ mà còn cần giúp người dùng sửa đầu vào không hợp lệ.

### 16.1. Phục hồi trong LL

Recursive descent có thể bắt lỗi tại một production, sau đó bỏ qua token cho đến khi gặp điểm đồng bộ như:

- Dấu chấm phẩy.
- Dấu ngoặc đóng.
- Từ khóa mở đầu câu lệnh mới.
- EOF.

Ví dụ, khi phân tích danh sách câu lệnh, parser có thể dừng bỏ qua tại set, print hoặc if để tiếp tục phân tích câu lệnh kế tiếp.

### 16.2. Phục hồi trong LR

Parser LR có thể dùng trạng thái stack và tập token đồng bộ để tìm trạng thái có thể tiếp tục. Một số công cụ hỗ trợ error productions hoặc cơ chế phục hồi chuyên biệt.

Việc phục hồi cần tránh tạo quá nhiều lỗi dây chuyền. Nếu parser không thể xác định cấu trúc đáng tin cậy sau lỗi, có thể dừng ở phạm vi nhỏ nhất hợp lý thay vì cố gắng tiếp tục toàn bộ tệp.

### 16.3. Chẩn đoán có ích

Thông báo lỗi nên cung cấp:

- Vị trí lỗi.
- Token thực tế đã gặp.
- Những token hoặc cấu trúc được mong đợi.
- Ngữ cảnh đang phân tích.
- Gợi ý sửa khi có thể.

Ví dụ:

~~~text
Syntax error at line 8, column 15.
Found: RIGHT_BRACE
Expected: EXPRESSION after '='.
~~~

Không nên chỉ hiển thị Parse failed nếu parser có đủ thông tin để chỉ ra nguyên nhân.

## 17. Công cụ parser generator

Với DSL lớn, có thể dùng parser generator để sinh parser từ grammar thay vì tự viết toàn bộ thuật toán.

Một số hệ sinh thái thường gặp:

- Công cụ thiên về LL hoặc adaptive predictive parsing, chẳng hạn ANTLR.
- Công cụ parser Java theo phong cách LL như JavaCC.
- Công cụ theo họ yacc/bison, thường tạo parser LALR hoặc các biến thể LR tùy cấu hình.
- Công cụ parser PEG, sử dụng grammar biểu thức phân tích.

Cần kiểm tra tài liệu của phiên bản công cụ cụ thể trước khi chọn vì khả năng, cú pháp grammar, hỗ trợ lookahead và cơ chế tạo AST có thể khác nhau.

### 17.1. Lợi ích

- Sinh parser từ grammar có cấu trúc.
- Báo lỗi grammar và một số xung đột trong lúc xây dựng.
- Tạo parse tree hoặc cơ chế semantic action.
- Có thể hỗ trợ phục hồi lỗi và tích hợp editor.
- Giảm lượng mã parser phải tự duy trì.

### 17.2. Đánh đổi

- Cần học cú pháp grammar và quy tắc của công cụ.
- Báo lỗi hoặc stack trace sinh ra có thể khó hiểu.
- Nâng cấp phiên bản công cụ có thể ảnh hưởng mã tích hợp.
- Một số grammar cần cấu hình precedence, associativity hoặc lookahead đặc biệt.
- Cấu trúc parse tree được sinh ra có thể cần chuyển đổi thành AST riêng.

Không nên chọn parser generator chỉ vì nó phổ biến. Hãy xem xét ngôn ngữ chủ, độ phức tạp grammar, khả năng debug, chất lượng diagnostics và yêu cầu triển khai.

## 18. Lựa chọn LL hay LR cho DSL

Có thể dùng các câu hỏi sau để định hướng lựa chọn.

### 18.1. Cú pháp có thể thiết kế để dự đoán rõ không?

Nếu các khai báo bắt đầu bằng từ khóa khác nhau, biểu thức có thể phân tầng và tiền tố chung dễ xử lý, LL recursive descent thường là lựa chọn tự nhiên.

Ví dụ:

~~~text
entity Customer { ... }
relation places { ... }
workflow processOrder { ... }
query activeOrders { ... }
~~~

Parser có thể chọn cấu trúc ngay từ từ khóa đầu tiên.

### 18.2. Grammar có đệ quy trái hoặc cấu trúc biểu thức phức tạp không?

Nếu DSL cần grammar biểu thức có đệ quy trái tự nhiên, nhiều cấu trúc lồng nhau hoặc grammar gần với một ngôn ngữ lập trình tổng quát, LR có thể thuận lợi hơn. Cũng có thể biến đổi grammar để dùng LL, nhưng cần cân nhắc độ phức tạp và khả năng đọc.

### 18.3. Ai sẽ duy trì parser?

Một nhóm nhỏ quen Java có thể dễ duy trì recursive descent. Một nhóm đã có quy trình grammar và parser generator có thể phù hợp với LR. Khả năng gỡ lỗi và kiến thức của đội ngũ là yếu tố thực tế quan trọng.

### 18.4. Cần thông báo lỗi và IDE đến mức nào?

Nếu DSL được viết trực tiếp trong editor, parser cần cung cấp vị trí lỗi ổn định, phân tích một phần khi tài liệu chưa hoàn chỉnh và phục hồi tốt. Cả LL lẫn LR đều có thể đáp ứng, nhưng chất lượng phụ thuộc cách triển khai và công cụ.

### 18.5. Có thể bắt đầu đơn giản rồi mở rộng không?

Một DSL có thể bắt đầu với recursive descent nếu grammar nhỏ, sau đó chuyển sang parser generator khi ngôn ngữ phát triển. Nếu chọn hướng này, nên giữ AST và semantic model độc lập với chi tiết parser để việc thay đổi không làm ảnh hưởng runtime.

## 19. Quy trình thiết kế và triển khai parser

Một quy trình thực tế có thể gồm các bước sau:

### Bước 1: Xác định cấu trúc DSL

Liệt kê khai báo, câu lệnh, biểu thức, khối, kiểu dữ liệu và các dạng literal. Viết ví dụ hợp lệ và không hợp lệ trước khi triển khai.

### Bước 2: Viết grammar

Dùng EBNF hoặc cú pháp grammar của công cụ. Xác định terminal, nonterminal, start symbol, thứ tự production và các trường hợp epsilon.

### Bước 3: Chọn chiến lược parsing

Đánh giá grammar có phù hợp với LL không, có cần LR không, có thể dùng PEG hoặc parser generator nào. Đừng chỉ chọn theo thói quen; xem xét các cấu trúc thực tế của DSL.

### Bước 4: Giải quyết đệ quy trái và tiền tố chung nếu dùng LL

Loại bỏ đệ quy trái trực tiếp hoặc gián tiếp trong các phần recursive descent không hỗ trợ nó. Left factor những production có chung tiền tố khi cần.

### Bước 5: Xác định precedence và associativity

Đặc biệt với biểu thức toán học, logic, truy vấn và điều kiện. Viết ví dụ cho các tổ hợp toán tử để bảo đảm AST được nhóm đúng.

### Bước 6: Xây lexer và parser

Xác định token, vị trí nguồn, cách xử lý comment, string, number và EOF. Triển khai parser thủ công hoặc sinh parser từ grammar.

### Bước 7: Tạo AST

Giữ node có ý nghĩa đối với miền và source span. Tránh để chi tiết cú pháp không cần thiết lan vào runtime.

### Bước 8: Kiểm tra ngữ nghĩa

Thực hiện name resolution, type checking, kiểm tra ràng buộc và quyền sử dụng sau khi parse.

### Bước 9: Kiểm thử cú pháp và lỗi

Có trường hợp hợp lệ, không hợp lệ, biên, biểu thức lồng nhau, khai báo thiếu, dấu phân cách thiếu và EOF bất ngờ. Kiểm tra cả AST lẫn diagnostics.

### Bước 10: Tích hợp editor và runtime

Cung cấp diagnostics, autocomplete hoặc syntax highlighting nếu cần. Chỉ thực thi mô hình đã qua các bước kiểm tra thích hợp.

## 20. Ví dụ tổng hợp: DSL quy trình đơn hàng

Giả sử DSL cho phép mô tả quy trình:

~~~text
workflow processOrder {
  set status = "PENDING";

  if stockAvailable {
    call reserveInventory(orderId);
    call chargePayment(orderId);
  }

  call sendConfirmation(orderId);
}
~~~

Grammar rút gọn:

~~~text
Workflow -> "workflow" IDENTIFIER "{" Statement* "}"

Statement -> Assignment
           | IfStatement
           | ActionCall

Assignment -> "set" IDENTIFIER "=" Expression ";"

IfStatement -> "if" Expression "{" Statement* "}"

ActionCall -> "call" IDENTIFIER "(" Arguments? ")" ";"
~~~

### 20.1. Phân tích bằng LL

Parser LL có thể chọn Statement dựa trên token đầu tiên:

- set chọn Assignment.
- if chọn IfStatement.
- call chọn ActionCall.
- dấu ngoặc đóng kết thúc danh sách Statement trong khối.

Mỗi cấu trúc có thể được xử lý bằng một hàm recursive descent. Sau khi tạo AST, bước ngữ nghĩa kiểm tra action có tồn tại, tham số có đúng kiểu và biến được tham chiếu có nằm trong scope không.

### 20.2. Phân tích bằng LR

Parser LR đọc token, đẩy trạng thái lên stack và reduce các cụm thành Assignment, IfStatement hoặc ActionCall. Grammar được chuyển thành automaton và bảng ACTION/GOTO.

Nếu grammar được thiết kế rõ, parser LR cũng nhận diện cùng cấu trúc. Khi có biểu thức phức tạp hoặc đệ quy trái, LR có thể giữ grammar tự nhiên hơn.

### 20.3. Kết quả cần thống nhất

Dù dùng LL hay LR, AST cuối cùng có thể có dạng:

~~~text
Workflow(name = "processOrder")
  Assignment(status, "PENDING")
  If(stockAvailable)
    ActionCall(reserveInventory, [orderId])
    ActionCall(chargePayment, [orderId])
  ActionCall(sendConfirmation, [orderId])
~~~

Sau đó, các bước name resolution, type checking, validation và execution dùng cùng mô hình. Đây là cách giữ ngữ nghĩa DSL độc lập với thuật toán parser.

## 21. Những nhầm lẫn thường gặp

**“LL đọc từ trái, LR đọc từ phải.”** Cả hai đều đọc đầu vào từ trái sang phải. Chữ R trong LR nói đến dẫn xuất phải được xây dựng theo thứ tự ngược, không phải đọc văn bản từ phải sang trái.

**“LL chỉ nhìn một token.”** Chỉ LL(1) dùng một token lookahead. LL(k) hoặc parser dự đoán thích nghi có thể nhìn nhiều token hơn.

**“LR luôn cần nhiều token lookahead.”** LR(1) dùng một token lookahead. Khả năng xử lý grammar đến từ trạng thái và automaton, không chỉ từ việc nhìn xa.

**“LL không thể phân tích biểu thức.”** LL có thể phân tích biểu thức khi grammar được tổ chức phù hợp, thường bằng các tầng precedence và loại bỏ đệ quy trái.

**“LR luôn nhanh hơn LL.”** Hiệu năng phụ thuộc grammar, parser generator, kích thước đầu vào, cách tạo token và triển khai. Không thể kết luận chỉ từ tên họ parser.

**“Nếu parser chấp nhận thì DSL hợp lệ về mọi mặt.”** Parser chỉ xác minh cấu trúc cú pháp. Name resolution, type checking, constraint validation và kiểm tra quyền có thể vẫn thất bại.

**“Xung đột LR có thể bỏ qua nếu công cụ vẫn sinh parser.”** Parser có thể chọn hành động mặc định nhưng ngữ nghĩa có thể sai. Mỗi xung đột cần được hiểu và giải quyết có chủ đích.

**“Đổi parser là phải đổi AST.”** Không nhất thiết. Nếu AST và semantic model được thiết kế độc lập, có thể thay parser mà giữ nguyên cấu trúc đầu ra.

## 22. Kết luận

LL và LR là hai họ parser quan trọng với cách phân tích khác nhau. LL phân tích từ trên xuống, dự đoán production từ start symbol và thường phù hợp với recursive descent khi grammar không có đệ quy trái và có thể phân biệt bằng lookahead. LR phân tích từ dưới lên, dùng stack, trạng thái và các hành động shift/reduce để rút gọn token thành cấu trúc lớn hơn; nó xử lý được nhiều grammar phức tạp hơn, bao gồm grammar có đệ quy trái.

Khi xây dựng DSL, hãy bắt đầu từ grammar và các tình huống sử dụng thực tế. Nếu cú pháp có thể thiết kế rõ ràng, LL thường dễ đọc và dễ duy trì. Nếu grammar có nhiều cấu trúc phức tạp hoặc cần giữ dạng đệ quy trái, LR và parser generator có thể phù hợp hơn. Trong cả hai trường hợp, cần quản lý precedence, associativity, xung đột, vị trí nguồn và phục hồi lỗi.

Điều quan trọng là giữ AST và mô hình ngữ nghĩa độc lập với thuật toán parsing. Khi đó, DSL có thể thay đổi hoặc nâng cấp parser mà vẫn bảo toàn ý nghĩa của các chương trình đã viết.

