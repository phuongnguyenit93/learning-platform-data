# Đơn giản hóa luật ngữ pháp trong DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích luật ngữ pháp (grammar rule hoặc production rule) và vai trò của chúng trong việc mô tả cú pháp DSL.
- Nhận diện các luật dư thừa, lặp lại, khó đọc hoặc gây nhập nhằng.
- Đơn giản hóa ngữ pháp bằng cách gom nhóm, loại bỏ quy tắc không cần thiết, dùng ký hiệu lặp và tùy chọn, tách mức ưu tiên toán tử và phân tích theo cấu trúc rõ ràng.
- Hiểu khi nào cần loại bỏ đệ quy trái hoặc thực hiện left factoring để phù hợp với parser.
- Phân biệt việc rút gọn cách viết grammar với việc thay đổi ngôn ngữ mà grammar chấp nhận.
- Kiểm tra rằng grammar sau khi đơn giản hóa vẫn mô tả đúng các cấu trúc hợp lệ và giữ được ý nghĩa mong muốn.

## 1. Luật ngữ pháp là gì?

Ngữ pháp (grammar) mô tả cách các thành phần của một ngôn ngữ có thể kết hợp để tạo thành biểu thức, câu lệnh hoặc chương trình hợp lệ. Trong DSL, grammar quy định người dùng được viết từ khóa, tên, literal, toán tử, khối lệnh và cấu trúc miền theo trật tự nào.

Một **luật ngữ pháp** (grammar rule hoặc production rule) mô tả cách một ký hiệu phi kết thúc (nonterminal) có thể được thay thế bằng một chuỗi gồm terminal và/hoặc nonterminal khác.

Ví dụ, một DSL đơn giản có thể dùng:

~~~text
assignment ::= IDENTIFIER "=" expression
expression ::= INTEGER
             | IDENTIFIER
~~~

Trong đó:

- assignment và expression là nonterminal, tức các cấu trúc được định nghĩa bằng những luật khác.
- IDENTIFIER, INTEGER và dấu bằng là terminal hoặc token do lexer cung cấp.
- Ký hiệu ::= có nghĩa là “được định nghĩa thành”.
- Dấu | biểu thị các lựa chọn thay thế.

Luật assignment cho biết một phép gán gồm tên định danh, dấu bằng và biểu thức. Luật expression cho biết biểu thức có thể là một số nguyên hoặc một định danh.

Grammar thường được biểu diễn bằng BNF (Backus-Naur Form), EBNF (Extended Backus-Naur Form), PEG hoặc cú pháp riêng của công cụ parser. Ký hiệu cụ thể có thể khác nhau, nhưng mục đích chung là mô tả cấu trúc hợp lệ của ngôn ngữ.

## 2. Vì sao cần đơn giản hóa luật?

Khi DSL phát triển, grammar thường được bổ sung qua nhiều lần thay đổi. Một quy tắc mới có thể được thêm để hỗ trợ cú pháp mới; một quy tắc khác được sao chép để xử lý trường hợp tương tự; hoặc nhiều nhánh được thêm vào mà không xem xét cấu trúc chung. Kết quả có thể là grammar dài, khó hiểu và khó bảo trì.

Đơn giản hóa luật giúp:

- **Giảm lặp lại:** những cấu trúc giống nhau có thể dùng chung một nonterminal.
- **Làm rõ ý định:** tên luật và cách nhóm thể hiện rõ các thành phần của cú pháp.
- **Giảm nhập nhằng:** các lựa chọn, thứ tự ưu tiên và phạm vi của toán tử được thể hiện minh bạch.
- **Hỗ trợ parser:** grammar có thể được điều chỉnh để phù hợp với parser LL, LR, PEG hoặc bộ sinh parser cụ thể.
- **Dễ mở rộng:** thêm một cấu trúc mới ít làm thay đổi nhiều luật không liên quan.
- **Dễ kiểm thử:** mỗi luật có thể được kiểm tra bằng ví dụ hợp lệ và không hợp lệ.
- **Giúp người dùng hiểu DSL:** cú pháp nhất quán thường dễ học và dễ giải thích hơn.

Tuy nhiên, grammar ngắn hơn không mặc nhiên tốt hơn. Một luật quá tổng quát có thể che giấu khác biệt quan trọng, làm parser khó xử lý hoặc khiến lỗi chỉ xuất hiện ở bước sau. Mục tiêu là giảm độ phức tạp không cần thiết mà vẫn giữ được cấu trúc và ý nghĩa của ngôn ngữ.

## 3. Nhận diện luật dư thừa và khó bảo trì

Trước khi sửa grammar, cần hiểu những dấu hiệu cho thấy luật đang có vấn đề.

### 3.1. Các nhánh lặp lại

Ví dụ:

~~~text
statement ::= printStatement
            | logStatement
            | sendStatement

printStatement ::= "print" STRING
logStatement   ::= "log" STRING
sendStatement  ::= "send" STRING
~~~

Ba luật cuối có cùng cấu trúc: một từ khóa theo sau bởi một chuỗi. Nếu sự khác nhau chỉ nằm ở từ khóa, có thể gom cấu trúc chung:

~~~text
statement ::= outputCommand
outputCommand ::= outputKeyword STRING
outputKeyword ::= "print" | "log" | "send"
~~~

Cách viết mới thể hiện rõ phần chung và phần khác biệt. Tuy nhiên, nếu mỗi lệnh có ngữ nghĩa hoặc tham số khác nhau, không nên gom chỉ vì chúng trông giống nhau. Grammar cần phản ánh các khác biệt có ý nghĩa đối với parser và các bước xử lý sau.

### 3.2. Luật chỉ có một lựa chọn không cần thiết

Ví dụ:

~~~text
expression ::= simpleExpression
simpleExpression ::= INTEGER
~~~

Nếu simpleExpression không được dùng ở nơi khác và không giúp biểu đạt một khái niệm quan trọng, có thể rút gọn:

~~~text
expression ::= INTEGER
~~~

Nhưng nếu simpleExpression là một khái niệm có ý nghĩa trong đặc tả hoặc được dùng ở nhiều luật khác, giữ lại tên riêng có thể làm grammar dễ đọc hơn.

### 3.3. Các luật trung gian không tạo thêm ý nghĩa

Ví dụ:

~~~text
statement ::= statementCore
statementCore ::= assignment
               | conditional
               | loop
~~~

Nếu statementCore chỉ được dùng một lần và không đại diện cho một lớp cấu trúc có ý nghĩa, có thể đưa các lựa chọn trực tiếp vào statement:

~~~text
statement ::= assignment
            | conditional
            | loop
~~~

Không nên loại bỏ mọi nonterminal trung gian. Một nonterminal có tên tốt có thể giúp chia grammar thành các phần dễ hiểu, ngay cả khi nó chỉ được dùng ở một nơi.

### 3.4. Luật quá dài và chứa nhiều trường hợp không liên quan

Một luật có hàng chục nhánh có thể khó đọc và dễ bị bỏ sót khi cập nhật:

~~~text
value ::= INTEGER | DECIMAL | STRING | TRUE | FALSE
        | IDENTIFIER | DATE | TIME | DURATION
        | "(" expression ")" | listLiteral
        | objectLiteral | functionCall
~~~

Có thể chia thành các nhóm có ý nghĩa:

~~~text
value ::= literal
        | nameOrCall
        | collectionLiteral
        | groupedExpression

literal ::= INTEGER | DECIMAL | STRING | TRUE | FALSE | DATE | TIME | DURATION
nameOrCall ::= IDENTIFIER | functionCall
collectionLiteral ::= listLiteral | objectLiteral
groupedExpression ::= "(" expression ")"
~~~

Cách chia nhóm không nhất thiết làm giảm tổng số dòng, nhưng làm cho mỗi luật có trách nhiệm rõ ràng. Đó cũng là một hình thức đơn giản hóa nhận thức và bảo trì.

### 3.5. Quy tắc khó đoán hoặc nhập nhằng

Ví dụ:

~~~text
expression ::= expression "+" expression
             | expression "*" expression
             | INTEGER
~~~

Luật này cho phép cả phép cộng và phép nhân nhưng không thể hiện rõ toán tử nào có ưu tiên cao hơn. Một biểu thức như 2 + 3 * 4 có thể được phân tích theo nhiều cây cú pháp nếu không có quy tắc ưu tiên.

Đơn giản hóa cần làm rõ thứ tự kết hợp và ưu tiên, không chỉ làm cho luật ngắn hơn.

## 4. Nguyên tắc trước khi đơn giản hóa

### 4.1. Xác định ngôn ngữ hiện tại phải chấp nhận

Trước khi sửa một luật, hãy liệt kê các câu lệnh hoặc biểu thức mà DSL phải chấp nhận. Tập ví dụ này là cơ sở để so sánh trước và sau.

Ví dụ, nếu grammar hiện tại chấp nhận:

~~~text
price = 10
price = 10 + 5
price = (10 + 5) * 2
~~~

thì grammar mới cần tiếp tục chấp nhận những biểu thức đó nếu mục tiêu chỉ là tái cấu trúc. Đồng thời, cần xác định các trường hợp không hợp lệ như phép toán thiếu toán hạng hoặc dấu ngoặc không cân bằng.

### 4.2. Phân biệt cú pháp với ngữ nghĩa

Grammar trả lời cấu trúc nào hợp lệ. Nó thường không quyết định tên biến có tồn tại, kiểu có tương thích, người dùng có quyền thực hiện hành động hoặc quy tắc nghiệp vụ có thỏa mãn hay không.

Ví dụ, grammar có thể chấp nhận:

~~~text
cancel order
~~~

Nhưng ngữ nghĩa của DSL có thể từ chối thao tác nếu đơn hàng đã giao. Không nên làm grammar phức tạp bằng cách cố mã hóa mọi trạng thái dữ liệu động nếu các điều kiện đó phù hợp hơn với bước kiểm tra ngữ nghĩa hoặc runtime.

### 4.3. Giữ ranh giới giữa lexer và parser

Lexer nhận diện token như IDENTIFIER, INTEGER, STRING, PLUS hoặc WHEN. Parser dùng các token đó để xây dựng cấu trúc.

Nếu lexer đã nhận diện >= thành một token GREATER_EQUAL, grammar nên tham chiếu token đó thay vì lặp lại chi tiết ký tự. Việc đơn giản hóa grammar không nên trộn trách nhiệm nhận diện ký tự với trách nhiệm tổ chức cấu trúc.

### 4.4. Chọn mức trừu tượng phù hợp

Tên luật nên mô tả khái niệm có ý nghĩa đối với ngôn ngữ, ví dụ expression, statement, condition, parameterList hoặc objectLiteral. Tránh tên quá chung như part1, item2 hoặc groupA vì chúng không giúp người đọc hiểu cấu trúc.

### 4.5. Ưu tiên tính rõ ràng hơn số lượng dòng

Hai luật có thể tương đương về ngôn ngữ được chấp nhận nhưng một luật dễ hiểu hơn nhiều. Ví dụ, biểu diễn danh sách bằng EBNF thường rõ hơn một chuỗi đệ quy dài. Chọn cách viết giúp người đọc dự đoán được cấu trúc và giúp công cụ xử lý ổn định.

## 5. Kỹ thuật 1: Gom các cấu trúc chung

Khi nhiều luật có cùng một phần cấu trúc, hãy tạo nonterminal dùng chung.

### 5.1. Trước khi gom nhóm

~~~text
variableDeclaration ::= "let" IDENTIFIER "=" expression
constantDeclaration ::= "const" IDENTIFIER "=" expression
parameterDeclaration ::= "param" IDENTIFIER "=" expression
~~~

Ba luật có cùng cấu trúc từ khóa, định danh, dấu bằng và biểu thức. Có thể biểu diễn:

~~~text
declaration ::= declarationKind IDENTIFIER "=" expression
declarationKind ::= "let" | "const" | "param"
~~~

Cách viết này giảm lặp lại và giúp thêm một loại khai báo mới dễ dàng hơn.

### 5.2. Khi nào không nên gom nhóm?

Nếu một loại khai báo có cấu trúc khác, việc gom quá mức có thể làm luật trở nên khó hiểu:

~~~text
declaration ::= declarationKind IDENTIFIER "=" expression
              | "const" IDENTIFIER ":" type "=" expression
              | "param" IDENTIFIER ":" type
~~~

Có thể tách các trường hợp khác nhau:

~~~text
declaration ::= variableDeclaration
              | constantDeclaration
              | parameterDeclaration

variableDeclaration ::= "let" IDENTIFIER "=" expression
constantDeclaration ::= "const" IDENTIFIER ":" type "=" expression
parameterDeclaration ::= "param" IDENTIFIER ":" type
~~~

Số luật nhiều hơn nhưng cấu trúc từng loại rõ ràng. Đơn giản hóa phải giữ được ý nghĩa và khác biệt thật sự của từng cấu trúc.

## 6. Kỹ thuật 2: Dùng ký hiệu lặp và tùy chọn

Nhiều grammar có các luật đệ quy chỉ để biểu diễn danh sách hoặc thành phần có thể xuất hiện nhiều lần. EBNF cung cấp ký hiệu giúp viết các cấu trúc này ngắn gọn hơn.

### 6.1. Danh sách bằng đệ quy

BNF có thể biểu diễn danh sách tham số:

~~~text
parameterList ::= parameter
                | parameter "," parameterList
~~~

Luật này mô tả một hoặc nhiều tham số, phân cách bằng dấu phẩy.

Trong EBNF có thể viết:

~~~text
parameterList ::= parameter { "," parameter }
~~~

Trong ký hiệu EBNF thường dùng:

- { X } nghĩa là X xuất hiện không hoặc nhiều lần.
- [ X ] nghĩa là X là tùy chọn, có thể xuất hiện không hoặc một lần.
- ( X | Y ) dùng để nhóm các lựa chọn.

Quy ước chính xác của từng công cụ có thể khác nhau, nên phải đọc tài liệu của định dạng grammar đang sử dụng.

### 6.2. Thành phần tùy chọn

Một câu lệnh gọi hàm có thể có danh sách đối số tùy chọn:

~~~text
functionCall ::= IDENTIFIER "(" [ argumentList ] ")"
~~~

Luật này cho phép cả:

~~~text
refresh()
refresh(orderId)
refresh(orderId, true)
~~~

Nếu không dùng ký hiệu tùy chọn, BNF có thể cần hai nhánh:

~~~text
functionCall ::= IDENTIFIER "(" ")"
               | IDENTIFIER "(" argumentList ")"
~~~

Ký hiệu tùy chọn giúp thể hiện rõ rằng phần argumentList có thể không xuất hiện.

### 6.3. Danh sách có thể rỗng

Danh sách tham số có thể cho phép rỗng:

~~~text
argumentList ::= [ expression { "," expression } ]
~~~

Hoặc có thể viết:

~~~text
argumentList ::= expression { "," expression }
~~~

Hai luật không tương đương. Luật thứ nhất cho phép danh sách rỗng; luật thứ hai yêu cầu ít nhất một biểu thức. Cần chọn theo yêu cầu của DSL.

### 6.4. Danh sách có dấu phẩy cuối

Một số ngôn ngữ cho phép dấu phẩy cuối:

~~~text
argumentList ::= expression { "," expression } [ "," ]
~~~

Nhờ đó cả hai dạng có thể hợp lệ:

~~~text
calculate(1, 2, 3)
calculate(1, 2, 3,)
~~~

Nếu DSL không muốn cho phép dấu phẩy cuối, không thêm phần tùy chọn đó. Những chi tiết nhỏ như vậy ảnh hưởng trực tiếp đến tính tương thích của grammar.

## 7. Kỹ thuật 3: Loại bỏ đệ quy trái khi parser yêu cầu

Đệ quy trái (left recursion) xảy ra khi một nonterminal có thể mở rộng thành một chuỗi bắt đầu bằng chính nó.

### 7.1. Đệ quy trái trực tiếp

Ví dụ:

~~~text
expression ::= expression "+" term
             | term
~~~

Luật này mô tả biểu thức cộng gồm một biểu thức trước đó, dấu cộng và một term. Nó là cách tự nhiên để mô tả tính kết hợp trái của phép cộng.

Tuy nhiên, một parser recursive descent đơn giản có thể gọi expression, rồi lại gọi expression ngay lập tức mà không tiêu thụ token nào. Điều đó gây đệ quy vô hạn.

### 7.2. Chuyển sang dạng không đệ quy trái

Có thể chuyển luật trên thành:

~~~text
expression ::= term expressionTail
expressionTail ::= "+" term expressionTail
                 | ε
~~~

ε (epsilon) biểu thị chuỗi rỗng. Luật mới yêu cầu một term trước, sau đó là không hoặc nhiều cặp dấu cộng và term.

Nếu dùng EBNF:

~~~text
expression ::= term { "+" term }
~~~

Cách viết EBNF ngắn hơn và thường dễ đọc hơn.

### 7.3. Đệ quy trái gián tiếp

Đệ quy trái gián tiếp xảy ra khi một luật dẫn đến chính nó qua một hoặc nhiều nonterminal khác:

~~~text
A ::= B "x" | "a"
B ::= A "y" | "b"
~~~

A có thể bắt đầu bằng B, B lại có thể bắt đầu bằng A. Khi parser mở rộng theo đường này, nó có thể quay lại A trước khi tiêu thụ token.

Việc loại bỏ đệ quy trái gián tiếp cần xem xét thứ tự các nonterminal và thay thế các luật phụ thuộc. Không nên chỉ thay một dòng mà không kiểm tra toàn bộ chuỗi suy dẫn.

### 7.4. Không phải parser nào cũng cần loại bỏ đệ quy trái

Đệ quy trái không phải lúc nào cũng là lỗi. Parser LR thường xử lý đệ quy trái tốt và có thể tạo cấu trúc phù hợp cho chuỗi phép toán. PEG và các parser generator hiện đại có thể có cơ chế riêng.

Do đó, chỉ biến đổi đệ quy trái khi parser hoặc công cụ yêu cầu, hoặc khi việc biến đổi giúp grammar dễ hiểu hơn. Nếu chuyển đổi, cần bảo toàn cấu trúc cây và tính kết hợp của toán tử.

## 8. Kỹ thuật 4: Left factoring để tách phần chung

Left factoring (tách tiền tố chung) là kỹ thuật đưa phần tiền tố giống nhau của nhiều nhánh thành một phần chung. Kỹ thuật này hữu ích với parser cần quyết định nhánh dựa trên một lượng token nhìn trước giới hạn.

### 8.1. Ví dụ có tiền tố chung

~~~text
statement ::= "if" expression "then" statement
            | "if" expression "then" statement "else" statement
~~~

Hai nhánh cùng bắt đầu bằng if, expression, then và statement. Có thể tách phần chung:

~~~text
statement ::= "if" expression "then" statement optionalElse
optionalElse ::= "else" statement
               | ε
~~~

Hoặc dùng EBNF:

~~~text
statement ::= "if" expression "then" statement [ "else" statement ]
~~~

Cách viết mới thể hiện phần else là tùy chọn.

### 8.2. Vì sao cần left factoring?

Nếu parser phải chọn một nhánh trước khi đọc đủ token để phân biệt, tiền tố chung có thể gây xung đột hoặc yêu cầu backtracking. Left factoring trì hoãn quyết định cho đến khi parser nhìn thấy phần khác nhau.

### 8.3. Cẩn thận với nhập nhằng dangling else

Ví dụ if lồng nhau có thể gây nhập nhằng:

~~~text
if a then if b then x else y
~~~

Từ khóa else gắn với if gần nhất hay if ngoài cùng? Đây là vấn đề ngữ nghĩa cú pháp, không chỉ là vấn đề rút ngắn luật. Grammar hoặc quy tắc parser cần quy định rõ. Một cách là tách statement thành matched statement và unmatched statement; một cách khác là định nghĩa quy tắc ưu tiên cụ thể trong parser.

Left factoring không tự động loại bỏ mọi nhập nhằng. Nó chỉ tách tiền tố chung; quy tắc gắn else vẫn cần được xác định.

## 9. Kỹ thuật 5: Tách mức ưu tiên và tính kết hợp của toán tử

Một trong những nguyên nhân làm grammar DSL khó hiểu là tất cả toán tử được đặt trong cùng một luật expression.

### 9.1. Luật nhập nhằng

~~~text
expression ::= expression "+" expression
             | expression "*" expression
             | INTEGER
             | "(" expression ")"
~~~

Với grammar này, biểu thức:

~~~text
2 + 3 * 4
~~~

có thể được hiểu theo hai cây:

~~~text
      +
     / \
    2   *
       / \
      3   4
~~~

hoặc:

~~~text
      *
     / \
    +   4
   / \
  2   3
~~~

Hai cây cho kết quả khác nhau. Grammar cần thể hiện rằng phép nhân có ưu tiên cao hơn phép cộng.

### 9.2. Tách expression theo tầng ưu tiên

Có thể viết:

~~~text
expression ::= addition
addition ::= multiplication { ("+" | "-") multiplication }
multiplication ::= unary { ("*" | "/") unary }
unary ::= ("-" | "!") unary
        | primary
primary ::= INTEGER
          | IDENTIFIER
          | "(" expression ")"
~~~

Trong cấu trúc này:

- primary là thành phần cơ bản.
- unary xử lý toán tử một ngôi.
- multiplication xử lý phép nhân và chia.
- addition xử lý phép cộng và trừ.

Vì addition dùng multiplication làm toán hạng, phép nhân được nhóm trước phép cộng. Biểu thức 2 + 3 * 4 được phân tích thành 2 + (3 * 4).

### 9.3. Tính kết hợp trái

Phép cộng thường kết hợp trái trong nhiều ngôn ngữ:

~~~text
10 - 3 - 2
~~~

được hiểu là:

~~~text
(10 - 3) - 2
~~~

Luật EBNF:

~~~text
addition ::= multiplication { ("+" | "-") multiplication }
~~~

thể hiện một chuỗi toán hạng theo thứ tự. Khi xây AST, parser thường lặp từ trái sang phải để tạo cây kết hợp trái.

### 9.4. Tính kết hợp phải

Phép lũy thừa thường kết hợp phải trong một số ngôn ngữ:

~~~text
2 ^ 3 ^ 2
~~~

được hiểu là:

~~~text
2 ^ (3 ^ 2)
~~~

Có thể mô tả bằng đệ quy phải:

~~~text
power ::= primary [ "^" power ]
~~~

Không nên dùng một mẫu lặp chung cho tất cả toán tử nếu chúng có tính kết hợp khác nhau.

### 9.5. Ưu tiên và kết hợp cần được ghi rõ

Với mỗi nhóm toán tử, đặc tả nên cho biết:

- Nhóm có ưu tiên cao hay thấp hơn nhóm khác.
- Toán tử kết hợp trái hay phải.
- Các toán tử trong cùng nhóm có cùng mức ưu tiên không.
- Có toán tử không được kết hợp hoặc cần dấu ngoặc rõ ràng không.
- Các kiểu dữ liệu nào được phép dùng.

Tách tầng grammar là cách phổ biến để thể hiện ưu tiên. Một số parser generator cho phép khai báo precedence và associativity riêng; khi đó có thể giữ grammar ngắn hơn, nhưng cần tài liệu rõ ràng về các khai báo đó.

## 10. Kỹ thuật 6: Chuẩn hóa cấu trúc danh sách và dấu phân cách

Các danh sách xuất hiện thường xuyên trong DSL: tham số hàm, trường cấu hình, điều kiện, mục trong collection và danh sách kiểu.

### 10.1. Danh sách một hoặc nhiều phần tử

BNF:

~~~text
identifierList ::= IDENTIFIER
                 | IDENTIFIER "," identifierList
~~~

EBNF:

~~~text
identifierList ::= IDENTIFIER { "," IDENTIFIER }
~~~

Luật EBNF nói rõ danh sách có ít nhất một định danh và các phần tử tiếp theo được phân cách bằng dấu phẩy.

### 10.2. Danh sách có thể rỗng

~~~text
identifierList ::= [ IDENTIFIER { "," IDENTIFIER } ]
~~~

Luật này cho phép không có phần tử nào. Nếu cấu trúc cần ít nhất một phần tử, không dùng dấu ngoặc vuông.

### 10.3. Danh sách có dấu phân cách tùy chọn cuối

~~~text
identifierList ::= IDENTIFIER { "," IDENTIFIER } [ "," ]
~~~

Dấu phẩy cuối có thể giúp viết danh sách nhiều dòng và giảm thay đổi khi thêm phần tử. Nhưng nó cũng là một lựa chọn cú pháp; cần quyết định có hỗ trợ trong DSL hay không.

### 10.4. Tránh lặp luật danh sách ở nhiều nơi

Nếu DSL có nhiều loại danh sách cùng dùng dấu phẩy, có thể tạo quy tắc chung ở mức phù hợp:

~~~text
argumentList ::= expression { "," expression }
fieldList ::= field { "," field }
parameterList ::= parameter { "," parameter }
~~~

Không nên tạo một generic list rule nếu các phần tử có ranh giới hoặc dấu phân cách khác nhau. Tên riêng giúp parser và tài liệu diễn đạt đúng vai trò của danh sách.

## 11. Kỹ thuật 7: Đơn giản hóa bằng EBNF

EBNF mở rộng BNF bằng ký hiệu lặp, tùy chọn và nhóm. Nó giúp biểu diễn các cấu trúc phổ biến gọn hơn.

| Nhu cầu | BNF thường dùng | EBNF thường dùng |
|---|---|---|
| Một lựa chọn | A có thể sinh B hoặc C | A có thể sinh B hoặc C |
| Tùy chọn | Hai nhánh có và không có X | A ::= [ X ] |
| Lặp không hoặc nhiều | Đệ quy với epsilon | A ::= { X } |
| Nhóm lựa chọn | Tạo nonterminal phụ | A ::= (B hoặc C) |
| Một hoặc nhiều | Đệ quy danh sách | A ::= X { X } |

Ví dụ cấu trúc khối:

~~~text
block ::= "{" { statement } "}"
~~~

Luật này nói một khối gồm dấu ngoặc nhọn mở, không hoặc nhiều câu lệnh, rồi dấu ngoặc nhọn đóng.

EBNF giúp người đọc thấy rõ số lần xuất hiện mà không cần theo dõi nhiều luật đệ quy. Nhưng cần chú ý rằng ký hiệu EBNF có thể khác giữa các công cụ. Một số công cụ dùng ? cho tùy chọn, * cho lặp không hoặc nhiều và + cho lặp một hoặc nhiều; công cụ khác dùng dấu ngoặc vuông và ngoặc nhọn.

## 12. Đơn giản hóa mà không làm thay đổi ngôn ngữ

Một phép biến đổi grammar có thể làm thay đổi tập chuỗi mà ngôn ngữ chấp nhận. Vì vậy, cần phân biệt hai mục tiêu:

1. **Tái cấu trúc tương đương:** thay đổi cách viết hoặc cấu trúc luật nhưng vẫn chấp nhận cùng tập chuỗi.
2. **Thay đổi đặc tả:** chủ động thêm hoặc loại bỏ cú pháp, nghĩa là tập chuỗi hợp lệ thay đổi.

### 12.1. Ví dụ tương đương

BNF:

~~~text
items ::= item
        | item "," items
~~~

EBNF tương đương:

~~~text
items ::= item { "," item }
~~~

Cả hai mô tả một hoặc nhiều item được phân cách bằng dấu phẩy, nếu quy ước EBNF đang dùng có nghĩa như trên.

### 12.2. Ví dụ không tương đương

~~~text
arguments ::= expression { "," expression }
~~~

Nếu đổi thành:

~~~text
arguments ::= [ expression { "," expression } ]
~~~

grammar mới chấp nhận danh sách rỗng, trong khi grammar cũ yêu cầu ít nhất một biểu thức. Đây là thay đổi ngôn ngữ, không chỉ là cách viết ngắn hơn.

### 12.3. Giữ ngữ nghĩa và cấu trúc AST

Hai grammar có thể chấp nhận cùng chuỗi nhưng tạo ra cây phân tích khác nhau. Nếu AST khác, phần xử lý sau có thể cần thay đổi.

Ví dụ, grammar cũ có nonterminal additionTail; grammar mới dùng EBNF lặp. Parser có thể xây AST theo cách khác dù chuỗi nguồn giống nhau. Cần bảo đảm AST vẫn thể hiện đúng toán hạng, thứ tự và tính kết hợp.

Khi tái cấu trúc grammar, nên xác định:

- Tập đầu vào hợp lệ có thay đổi không?
- Mỗi đầu vào tạo ra cấu trúc AST tương đương không?
- Thứ tự đánh giá biểu thức có được giữ không?
- Các thông báo lỗi có còn trỏ đúng vị trí không?
- Các công cụ formatter, syntax highlighting và editor có cần cập nhật không?

## 13. Quy trình đơn giản hóa một grammar

Có thể thực hiện theo các bước sau:

### Bước 1: Thu thập ví dụ đầu vào

Ghi lại các chương trình DSL hợp lệ, không hợp lệ và các trường hợp biên. Bao gồm biểu thức đơn giản, cấu trúc lồng nhau, danh sách rỗng, dấu phân cách cuối và các toán tử.

### Bước 2: Xác định luật và quan hệ phụ thuộc

Liệt kê nonterminal, terminal và các luật đang dùng. Vẽ hoặc ghi lại quan hệ giữa chúng để biết một luật được tham chiếu ở đâu.

### Bước 3: Tìm điểm lặp và luật không cần thiết

Xem xét các nhánh có cùng cấu trúc, nonterminal trung gian không tạo ý nghĩa, danh sách đệ quy và các luật quá dài. Không xóa luật trước khi biết các nơi phụ thuộc.

### Bước 4: Chọn phép biến đổi phù hợp

- Gom cấu trúc chung thành nonterminal có tên rõ.
- Dùng EBNF cho lặp và tùy chọn nếu công cụ hỗ trợ.
- Loại bỏ đệ quy trái khi parser cần.
- Left factoring khi có tiền tố chung gây khó dự đoán.
- Tách tầng ưu tiên toán tử và quy định tính kết hợp.
- Tách các cấu trúc khác ngữ nghĩa dù có vẻ giống nhau.

### Bước 5: So sánh tập chuỗi được chấp nhận

Chạy các ví dụ trước đây qua grammar mới. Kiểm tra các trường hợp hợp lệ vẫn được chấp nhận và trường hợp không hợp lệ vẫn bị từ chối theo chủ đích.

### Bước 6: Kiểm tra AST và ngữ nghĩa

Xem cấu trúc cây phân tích, thứ tự toán hạng, ranh giới khối và cách gắn nhánh. Kiểm tra các bước phân giải tên, kiểm tra kiểu và thực thi có nhận đúng cấu trúc hay không.

### Bước 7: Cập nhật tài liệu và công cụ

Nếu grammar thay đổi cú pháp, cập nhật hướng dẫn người dùng, ví dụ, parser, formatter, syntax highlighting, language server và thông báo lỗi.

### Bước 8: Ghi lại quyết định

Ghi rõ luật nào đã thay đổi, vì sao, thay đổi có tương thích không và phiên bản nào áp dụng. Điều này giúp nhóm hiểu được mục đích của cấu trúc grammar mới.

## 14. Ví dụ tổng hợp: đơn giản hóa grammar biểu thức DSL

Giả sử DSL ban đầu có grammar:

~~~text
expression ::= expression "+" expression
             | expression "-" expression
             | expression "*" expression
             | expression "/" expression
             | INTEGER
             | IDENTIFIER
             | "(" expression ")"
~~~

Các vấn đề:

- Đệ quy trái trực tiếp có thể không phù hợp với recursive descent parser.
- Không thể hiện ưu tiên giữa nhân/chia và cộng/trừ.
- Không thể hiện rõ tính kết hợp của các toán tử.
- Các trường hợp cơ bản và toán tử được trộn trong cùng một luật.

### 14.1. Chia theo tầng ưu tiên

Có thể tái cấu trúc:

~~~text
expression ::= additive

additive ::= multiplicative { ("+" | "-") multiplicative }

multiplicative ::= unary { ("*" | "/") unary }

unary ::= ("+" | "-") unary
        | primary

primary ::= INTEGER
          | IDENTIFIER
          | "(" expression ")"
~~~

Grammar mới có các tầng:

| Tầng | Vai trò |
|---|---|
| expression | Điểm vào chung cho biểu thức |
| additive | Phép cộng và trừ |
| multiplicative | Phép nhân và chia |
| unary | Dấu cộng hoặc trừ một ngôi |
| primary | Literal, tên và biểu thức trong ngoặc |

### 14.2. Cách grammar mới phân tích biểu thức

Với:

~~~text
2 + 3 * 4
~~~

Tầng additive nhận hai toán hạng multiplicative. Toán hạng bên phải là 3 * 4, được xử lý ở tầng multiplicative trước. Vì vậy, cây kết quả tương ứng với 2 + (3 * 4).

Với:

~~~text
10 - 3 - 2
~~~

Vòng lặp ở additive có thể xây cây từ trái sang phải, tương ứng với (10 - 3) - 2. Nếu muốn kết hợp phải, cần quy tắc khác thay vì dùng cùng mẫu lặp.

### 14.3. Mở rộng biểu thức với so sánh và logic

Nếu DSL hỗ trợ so sánh, AND và OR, có thể thêm các tầng:

~~~text
expression ::= logicalOr

logicalOr ::= logicalAnd { "or" logicalAnd }

logicalAnd ::= comparison { "and" comparison }

comparison ::= additive [ comparator additive ]

comparator ::= "==" | "!=" | ">" | ">=" | "<" | "<="

additive ::= multiplicative { ("+" | "-") multiplicative }

multiplicative ::= unary { ("*" | "/") unary }

unary ::= ("not" | "+" | "-") unary
        | primary

primary ::= INTEGER
          | IDENTIFIER
          | "(" expression ")"
~~~

Tầng thấp hơn trong chuỗi này được phân tích trước và trở thành toán hạng cho tầng cao hơn. Nhờ vậy, phép nhân ưu tiên hơn cộng; cộng ưu tiên hơn so sánh; so sánh ưu tiên hơn AND; AND ưu tiên hơn OR.

Đây là một thiết kế minh họa. DSL thực tế có thể chọn mức ưu tiên khác hoặc không cho phép chuỗi so sánh liên tiếp. Các quy tắc phải phù hợp với ý nghĩa của miền và được tài liệu hóa.

## 15. Các lỗi thường gặp khi đơn giản hóa luật

### 15.1. Rút gọn quá mức

Gộp nhiều cấu trúc khác nhau vào một luật tổng quát có thể làm grammar khó hiểu và khiến parser phải xử lý nhiều ngoại lệ. Giữ các nonterminal riêng khi chúng thể hiện khái niệm khác nhau.

### 15.2. Xóa luật đang được sử dụng

Một nonterminal tưởng như thừa có thể được tham chiếu bởi parser, tài liệu, test hoặc công cụ khác. Trước khi xóa, cần xác định các quan hệ phụ thuộc.

### 15.3. Vô tình cho phép đầu vào mới

Đổi danh sách một hoặc nhiều phần tử thành danh sách tùy chọn có thể làm cấu trúc rỗng trở nên hợp lệ. Thêm dấu phân cách tùy chọn cuối cũng mở rộng tập đầu vào.

### 15.4. Làm thay đổi ưu tiên toán tử

Gộp mọi toán tử vào một luật có thể làm cây phân tích thay đổi. Với phép trừ, chia hoặc lũy thừa, thứ tự kết hợp ảnh hưởng trực tiếp đến kết quả.

### 15.5. Nhầm đệ quy trái với lỗi grammar

Đệ quy trái có thể phù hợp với parser LR. Chỉ loại bỏ khi parser được dùng không hỗ trợ hoặc khi cần cấu trúc khác. Biến đổi không phù hợp có thể làm grammar khó đọc hơn hoặc đổi cây cú pháp.

### 15.6. Dùng EBNF nhưng không thống nhất ký hiệu

Các tài liệu có thể dùng ngoặc nhọn cho lặp hoặc cho nhóm literal; một số parser generator dùng cú pháp khác. Không nên trộn ký hiệu từ nhiều biến thể mà không giải thích.

### 15.7. Chỉ kiểm tra parser chấp nhận hay từ chối

Parser có thể vẫn chấp nhận đầu vào nhưng tạo AST khác. Cần kiểm tra cả cấu trúc cây, thứ tự đánh giá và hành vi của các bước sau.

## 16. Bài tập tự kiểm tra

### Bài 1: Tìm luật dư thừa

Cho grammar:

~~~text
statement ::= assignment | printStatement
assignment ::= IDENTIFIER "=" expression
printStatement ::= "print" expression
expression ::= INTEGER | IDENTIFIER
~~~

Hãy xác định luật nào có thể gom nhóm hoặc giữ nguyên. Giải thích vì sao không nên gom assignment và printStatement chỉ vì cả hai đều có expression.

### Bài 2: Chuyển BNF sang EBNF

Cho:

~~~text
nameList ::= IDENTIFIER
           | IDENTIFIER "," nameList
~~~

Hãy viết lại bằng EBNF và giải thích danh sách có cho phép rỗng hay không.

### Bài 3: Loại bỏ đệ quy trái

Chuyển luật:

~~~text
term ::= term "*" factor | factor
~~~

sang dạng phù hợp với recursive descent parser. Giải thích vai trò của epsilon hoặc ký hiệu lặp.

### Bài 4: Left factoring

Cho:

~~~text
command ::= "open" IDENTIFIER
          | "open" IDENTIFIER "with" expression
~~~

Hãy tách phần tiền tố chung và viết lại bằng EBNF. Nêu trường hợp nào phần with được chấp nhận.

### Bài 5: Xác định ưu tiên toán tử

Với biểu thức 4 + 5 * 2 - 3, hãy xác định thứ tự nhóm nếu nhân ưu tiên hơn cộng/trừ và cộng/trừ kết hợp trái. Vẽ hoặc mô tả cây AST tương ứng.

### Bài 6: Kiểm tra tính tương đương

So sánh hai luật:

~~~text
list ::= item { "," item }
~~~

và:

~~~text
list ::= [ item { "," item } ]
~~~

Giải thích chúng có chấp nhận cùng tập chuỗi hay không và nêu một đầu vào chỉ luật thứ hai chấp nhận.

### Bài 7: Lập kế hoạch tái cấu trúc

Một DSL có grammar biểu thức dài, tất cả toán tử ở cùng một luật và parser đang gặp xung đột. Hãy đề xuất các bước đơn giản hóa, cách kiểm tra tập đầu vào trước và sau, và cách xác nhận AST không thay đổi ngoài ý muốn.

## Kết luận

Đơn giản hóa luật ngữ pháp là quá trình làm cho grammar rõ ràng, ít lặp lại và dễ xử lý hơn trong khi vẫn giữ đúng các cấu trúc mà DSL cần hỗ trợ. Các kỹ thuật thường dùng gồm gom phần chung, dùng ký hiệu lặp và tùy chọn của EBNF, loại bỏ đệ quy trái khi parser yêu cầu, left factoring và tách tầng ưu tiên toán tử. Mỗi biến đổi cần được xem xét về tập chuỗi được chấp nhận, cấu trúc AST, tính kết hợp và ngữ nghĩa. Grammar tốt không nhất thiết là grammar ngắn nhất; nó là grammar thể hiện chính xác ý định của DSL, phù hợp với parser và có thể được người phát triển duy trì lâu dài.
