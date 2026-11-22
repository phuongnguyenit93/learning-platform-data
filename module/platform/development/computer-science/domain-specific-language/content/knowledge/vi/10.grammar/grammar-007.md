# Đệ quy trái

## 1. Đệ quy trái là gì?

Trong ngữ pháp hình thức của một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), một nonterminal được gọi là **đệ quy trái (left-recursive)** nếu nó có thể suy dẫn ra một chuỗi bắt đầu bằng chính nó.

Ký hiệu:

\[
A \Rightarrow^+ A\alpha
\]

Trong đó:

- \(A\) là nonterminal đang xét.
- \(\Rightarrow^+\) nghĩa là thực hiện một hoặc nhiều bước suy dẫn.
- \(\alpha\) là phần có thể rỗng hoặc không rỗng tùy dạng quy tắc.

Trường hợp trực tiếp thường có dạng:

~~~text
Expression -> Expression "+" Term
           | Term
~~~

Vế phải của nhánh đầu tiên bắt đầu bằng Expression, chính là nonterminal ở vế trái. Đây là **đệ quy trái trực tiếp**.

Đệ quy trái cũng có thể xuất hiện gián tiếp qua một hoặc nhiều nonterminal khác:

~~~text
A -> B "x"
B -> A "y"
  | "b"
~~~

Từ A, ta có thể suy dẫn:

~~~text
A => B "x"
  => A "y" "x"
~~~

Chuỗi suy dẫn bắt đầu lại bằng A, vì vậy A có đệ quy trái gián tiếp. B cũng tham gia chu trình đệ quy này.

Đệ quy trái là một đặc điểm của ngữ pháp, không tự động có nghĩa ngữ pháp sai hoặc mơ hồ. Nó chỉ trở thành vấn đề khi chiến lược phân tích cú pháp được sử dụng không xử lý được dạng đệ quy đó.

## 2. Vì sao đệ quy trái quan trọng khi xây parser?

Ảnh hưởng phụ thuộc vào loại parser.

### 2.1 Recursive descent và parser LL

Recursive descent thường triển khai mỗi nonterminal bằng một hàm. Hàm của nonterminal đọc token hiện tại rồi gọi các hàm tương ứng với cấu trúc ở vế phải.

Với grammar:

~~~text
Expression -> Expression "+" Term
           | Term
~~~

Một hàm đơn giản có thể được viết như sau:

~~~java
Expression parseExpression() {
    Expression left = parseExpression();
    expect(PLUS);
    Term right = parseTerm();
    return new AddExpression(left, right);
}
~~~

Lời gọi parseExpression đầu tiên lập tức gọi lại chính nó mà chưa tiêu thụ token nào. Lời gọi tiếp theo lại làm tương tự. Parser có thể lặp vô hạn cho đến khi tràn stack.

Đây là lý do grammar dùng cho recursive descent LL thường cần loại bỏ đệ quy trái hoặc được chuyển sang một dạng mà parser có thể xử lý.

### 2.2 Parser LR

Parser LR phân tích từ dưới lên. Đệ quy trái thường là dạng tự nhiên và có thể hiệu quả cho các chuỗi toán hạng kết hợp trái.

Ví dụ:

~~~text
Expression -> Expression "+" Term
           | Term
~~~

Grammar này thường được dùng trong parser LR để biểu diễn phép cộng kết hợp trái. Không cần loại bỏ đệ quy trái chỉ vì nhìn thấy nó; phải xét loại parser và mục tiêu của grammar.

### 2.3 Parser generator và PEG

Khả năng xử lý đệ quy trái khác nhau giữa các công cụ:

- Nhiều parser generator LL yêu cầu grammar không có đệ quy trái trong các quy tắc được phân tích theo kiểu top-down.
- Một số công cụ hỗ trợ đệ quy trái trực tiếp bằng cách tự biến đổi grammar hoặc dùng thuật toán riêng.
- ANTLR 4 hỗ trợ một số dạng đệ quy trái trực tiếp, đặc biệt hữu ích cho grammar biểu thức; không nên suy ra rằng mọi dạng đệ quy gián tiếp đều được hỗ trợ.
- PEG parser kiểu recursive descent truyền thống có thể gặp đệ quy vô hạn; một số triển khai mở rộng hỗ trợ left recursion, nhưng hành vi phụ thuộc công cụ.

Trước khi thay đổi grammar, hãy đọc tài liệu của parser generator và thử một grammar nhỏ. Đừng áp dụng quy tắc loại bỏ đệ quy trái một cách máy móc nếu công cụ đã hỗ trợ dạng đó và việc giữ grammar ban đầu giúp thể hiện ngữ nghĩa rõ hơn.

## 3. Các dạng đệ quy trái

### 3.1 Đệ quy trái trực tiếp

Một nonterminal gọi lại chính nó ngay ở đầu một nhánh:

~~~text
A -> A alpha
   | beta
~~~

Ví dụ:

~~~text
List -> List "," Item
     | Item
~~~

Nhánh List "," Item bắt đầu bằng List, nên List có đệ quy trái trực tiếp.

### 3.2 Đệ quy trái gián tiếp

Một nonterminal quay lại chính nó thông qua các nonterminal khác:

~~~text
A -> B "x"
B -> C "y"
C -> A "z"
  | "c"
~~~

Ta có:

~~~text
A => B "x"
  => C "y" "x"
  => A "z" "y" "x"
~~~

A suy dẫn ra chuỗi bắt đầu bằng A, dù quy tắc của A không có A ngay đầu vế phải.

### 3.3 Đệ quy trái qua nonterminal nullable

Một trường hợp khó nhận diện hơn xuất hiện khi ký hiệu đứng trước nonterminal đệ quy có thể sinh chuỗi rỗng.

Ví dụ:

~~~text
A -> B A "x"
   | "y"

B -> epsilon
   | "b"
~~~

Vì B có thể sinh epsilon, ta có:

~~~text
A => B A "x"
  => A "x"
~~~

Do đó, A vẫn có đệ quy trái. Nếu chỉ nhìn ký hiệu đầu tiên của vế phải mà không xét khả năng nullable, ta có thể bỏ sót chu trình.

Khi phân tích đệ quy trái, cần xét chuỗi nonterminal nullable ở đầu mỗi vế phải, không chỉ kiểm tra ký hiệu đầu tiên.

### 3.4 Chu trình không tiêu thụ token

Ví dụ:

~~~text
A -> A
   | "x"
~~~

Nhánh A -> A không tiêu thụ hay tạo thêm cấu trúc nào. Đây là một chu trình không tiến triển. Các chu trình như vậy cần được phát hiện riêng vì phép loại bỏ đệ quy trái tiêu chuẩn giả định nhánh đệ quy có phần hậu tố tạo tiến triển.

## 4. Đệ quy trái khác với kết hợp trái

Hai khái niệm thường bị nhầm:

- **Đệ quy trái** là thuộc tính của grammar: nonterminal có thể suy dẫn thành chuỗi bắt đầu bằng chính nó.
- **Kết hợp trái (left associativity)** là quy tắc xác định cách nhóm các toán tử cùng mức ưu tiên trong biểu thức.

Ví dụ, phép trừ thường kết hợp trái:

~~~text
a - b - c
~~~

được hiểu là:

~~~text
(a - b) - c
~~~

Grammar:

~~~text
Expression -> Expression "-" Term
           | Term
~~~

vừa có đệ quy trái vừa thể hiện cấu trúc phù hợp với kết hợp trái trong parser LR.

Nếu loại bỏ đệ quy trái để dùng recursive descent, vẫn phải giữ kết hợp trái trong AST. Chuyển đổi grammar không được làm thay đổi ngữ nghĩa biểu thức.

## 5. Loại bỏ đệ quy trái trực tiếp

Xét dạng tổng quát:

~~~text
A -> A alpha
   | beta
~~~

Trong đó beta là nhánh không bắt đầu bằng A, còn alpha là phần theo sau A ở nhánh đệ quy.

Ta có thể biến đổi thành:

~~~text
A  -> beta A'
A' -> alpha A'
    | epsilon
~~~

A' là một nonterminal mới. Ý tưởng là:

1. Phân tích phần cơ sở beta trước.
2. Sau đó lặp lại phần mở rộng alpha không hoặc nhiều lần.
3. Dừng khi không còn phần mở rộng.

### 5.1 Ví dụ đơn giản

Grammar ban đầu:

~~~text
Expression -> Expression "+" Number
           | Number
~~~

Đặt:

- A = Expression
- alpha = "+" Number
- beta = Number

Sau khi loại bỏ đệ quy trái:

~~~text
Expression  -> Number ExpressionTail
ExpressionTail -> "+" Number ExpressionTail
               | epsilon
~~~

Parser recursive descent có thể triển khai:

~~~java
Expression parseExpression() {
    Expression result = parseNumber();

    while (match(PLUS)) {
        Number right = parseNumber();
        result = new AddExpression(result, right);
    }

    return result;
}
~~~

Vòng lặp xử lý số lượng phép cộng bất kỳ mà không gọi lại parseExpression trước khi tiêu thụ token.

### 5.2 Có nhiều nhánh đệ quy và nhánh cơ sở

Dạng tổng quát hơn:

~~~text
A -> A alpha1
   | A alpha2
   | beta1
   | beta2
~~~

Biến đổi thành:

~~~text
A  -> beta1 A'
    | beta2 A'

A' -> alpha1 A'
    | alpha2 A'
    | epsilon
~~~

Mỗi nhánh cơ sở có thể tiếp tục bằng không hoặc nhiều phần mở rộng. Các nhánh alpha phải được giữ đúng thứ tự hoặc lựa chọn theo quy tắc ưu tiên của grammar khi thứ tự có ý nghĩa.

### 5.3 Ví dụ với danh sách

Grammar ban đầu:

~~~text
Items -> Items "," Item
       | Item
~~~

Grammar sau biến đổi:

~~~text
Items -> Item ItemsTail
ItemsTail -> "," Item ItemsTail
           | epsilon
~~~

Có thể viết parser:

~~~java
List<Item> parseItems() {
    List<Item> items = new ArrayList<>();
    items.add(parseItem());

    while (match(COMMA)) {
        items.add(parseItem());
    }

    return List.copyOf(items);
}
~~~

Kết quả là một danh sách theo thứ tự xuất hiện trong nguồn. Nếu grammar cho phép danh sách rỗng, cần thêm nhánh cơ sở tương ứng và xác định rõ dấu phẩy cuối có được phép hay không.

## 6. Giữ ngữ nghĩa khi loại bỏ đệ quy trái

Biến đổi grammar chỉ bảo toàn ngôn ngữ được sinh ra trong những điều kiện phù hợp. Nó không tự động bảo toàn hình dạng parse tree hoặc cách thực thi semantic action.

Xét biểu thức:

~~~text
a - b - c
~~~

Grammar đệ quy trái:

~~~text
Expression -> Expression "-" Number
           | Number
~~~

Parse tree thường phản ánh kết hợp trái:

~~~text
        -
       / \
      -   c
     / \
    a   b
~~~

Sau khi biến đổi:

~~~text
Expression -> Number ExpressionTail
ExpressionTail -> "-" Number ExpressionTail
               | epsilon
~~~

Parse tree của phần đuôi có dạng lặp hoặc đệ quy phải. Nếu xây AST theo cấu trúc cây đó một cách trực tiếp, ta có thể vô tình tạo kết hợp phải:

~~~text
a - (b - c)
~~~

Để giữ kết hợp trái, parser cần **fold từ trái sang phải**: lấy toán hạng đầu làm kết quả, sau đó áp dụng từng toán tử với toán hạng tiếp theo.

~~~java
Expression parseExpression() {
    Expression left = parseNumber();

    while (match(MINUS)) {
        Expression right = parseNumber();
        left = new SubtractExpression(left, right);
    }

    return left;
}
~~~

Với a - b - c, bước đầu tạo Subtract(a, b), bước tiếp theo tạo Subtract(Subtract(a, b), c). AST vẫn kết hợp trái.

Đây là điểm quan trọng khi chuyển grammar cho recursive descent: cần kiểm tra cả tập chuỗi được chấp nhận lẫn cấu trúc AST và kết quả thực thi.

## 7. Loại bỏ đệ quy trái gián tiếp

Đệ quy trái gián tiếp cần được xử lý bằng cách thay thế các nonterminal đứng trước để đưa chu trình về dạng trực tiếp.

Xét grammar:

~~~text
A -> B "a"
   | "c"

B -> A "b"
   | "d"
~~~

Từ B -> A "b" và A -> B "a", ta có:

~~~text
B => A "b"
  => B "a" "b"
~~~

B có đệ quy trái gián tiếp.

### 7.1 Thay thế theo thứ tự nonterminal

Chọn thứ tự:

~~~text
A1 = A
A2 = B
~~~

Xét A trước. Các nhánh của A không bắt đầu bằng A, nên chưa có đệ quy trái trực tiếp.

Khi xét B, có nhánh:

~~~text
B -> A "b"
~~~

Thay A bằng các vế phải của nó:

~~~text
B -> B "a" "b"
   | "c" "b"
   | "d"
~~~

Bây giờ đệ quy trái đã trở thành trực tiếp.

### 7.2 Loại bỏ đệ quy trái trực tiếp

Đặt:

- Phần đệ quy alpha = "a" "b".
- Các nhánh cơ sở là "c" "b" và "d".

Biến đổi:

~~~text
B -> "c" "b" B'
   | "d" B'

B' -> "a" "b" B'
    | epsilon
~~~

Grammar mới không còn chu trình trái nói trên. Khi triển khai thuật toán tổng quát, cần xử lý mọi cặp nonterminal theo thứ tự và loại bỏ đệ quy trực tiếp sau mỗi bước thay thế.

### 7.3 Thuật toán tổng quát

Cho các nonterminal theo thứ tự A1, A2, ..., An:

~~~text
for i = 1 .. n:
    for j = 1 .. i - 1:
        thay mỗi production Ai -> Aj gamma
        bằng các production Ai -> delta gamma
        với từng production Aj -> delta

    loại bỏ đệ quy trái trực tiếp của Ai
~~~

Đây là mô tả khái quát của thuật toán chuẩn. Khi áp dụng cho grammar thực tế, cần xử lý cẩn thận epsilon production, production rỗng, chu trình không tiến triển và các nhánh không có cơ sở. Không nên triển khai phép thay thế văn bản đơn giản mà không phân tích cấu trúc production.

## 8. Nonterminal nullable và việc phát hiện đệ quy trái

Một nonterminal được gọi là **nullable** nếu nó có thể suy dẫn ra chuỗi rỗng:

\[
A \Rightarrow^* \epsilon
\]

Khi kiểm tra đệ quy trái, cần đi qua các ký hiệu nullable ở đầu vế phải.

Ví dụ:

~~~text
Expression -> OptionalSign Expression "+" Term
            | Term

OptionalSign -> epsilon
              | "+"
~~~

Vì OptionalSign có thể rỗng, nhánh đầu tiên có thể bắt đầu hiệu dụng bằng Expression. Đây là một chu trình trái dù Expression không phải ký hiệu đầu tiên được viết trên vế phải.

Một cách tư duy khi phân tích:

1. Tính tập nullable cho các nonterminal.
2. Với mỗi production, duyệt từ trái sang phải.
3. Nếu gặp terminal, dừng vì chuỗi chắc chắn bắt đầu bằng terminal.
4. Nếu gặp nonterminal, ghi nhận cạnh phụ thuộc; tiếp tục nếu nonterminal đó nullable.
5. Phát hiện chu trình trong đồ thị phụ thuộc đầu production.

Đồ thị này giúp phát hiện cả đệ quy trái gián tiếp và đệ quy qua các ký hiệu nullable. Một triển khai cụ thể có thể dùng DFS hoặc thuật toán tìm strongly connected components để nhận diện chu trình.

## 9. Kết hợp đệ quy trái với precedence và associativity

Grammar biểu thức thường dùng đệ quy trái để biểu diễn phép toán kết hợp trái và phân tầng ưu tiên.

Ví dụ:

~~~text
Expression -> Expression "+" Term
           | Expression "-" Term
           | Term

Term -> Term "*" Factor
     | Term "/" Factor
     | Factor

Factor -> "(" Expression ")"
        | NUMBER
~~~

Trong grammar này:

- * và / có ưu tiên cao hơn + và - vì chúng nằm ở tầng Term.
- Các phép cộng, trừ ở cùng tầng kết hợp trái.
- Các phép nhân, chia ở cùng tầng kết hợp trái.
- Ngoặc cho phép thay đổi thứ tự nhóm.

### 9.1 Dạng phù hợp với recursive descent

Có thể viết lại bằng các phần lặp:

~~~text
Expression -> Term (("+" | "-") Term)*
Term       -> Factor (("*" | "/") Factor)*
Factor     -> "(" Expression ")"
            | NUMBER
~~~

Parser:

~~~java
Expression parseExpression() {
    Expression left = parseTerm();

    while (match(PLUS, MINUS)) {
        Token operator = previous();
        Expression right = parseTerm();
        left = new BinaryExpression(operator, left, right);
    }

    return left;
}

Expression parseTerm() {
    Expression left = parseFactor();

    while (match(STAR, SLASH)) {
        Token operator = previous();
        Expression right = parseFactor();
        left = new BinaryExpression(operator, left, right);
    }

    return left;
}
~~~

Vòng lặp ở tầng Expression tiêu thụ các phép cộng/trừ; vòng lặp ở tầng Term tiêu thụ phép nhân/chia. Cấu trúc hàm giữ đúng precedence và fold-left giữ đúng associativity.

### 9.2 Phép toán kết hợp phải

Một số toán tử thường kết hợp phải, chẳng hạn phép lũy thừa trong nhiều ngôn ngữ:

~~~text
a ^ b ^ c
~~~

thường được hiểu là:

~~~text
a ^ (b ^ c)
~~~

Grammar có thể biểu diễn bằng đệ quy phải:

~~~text
Power -> Unary "^" Power
       | Unary
~~~

Không được áp dụng fold-left cho mọi chuỗi toán tử. Cách xây AST phải theo associativity mà DSL quy định.

### 9.3 Toán tử unary và precedence

Unary minus thường có grammar dạng:

~~~text
Unary -> "-" Unary
       | Primary
~~~

Nhưng quan hệ ưu tiên giữa unary minus và exponent cần được định nghĩa. Ví dụ -2^2 có thể được hiểu là -(2^2) hoặc (-2)^2 tùy ngôn ngữ. Grammar và test phải xác nhận cách hiểu được chọn.

## 10. Đệ quy trái và left factoring là hai phép biến đổi khác nhau

**Left factoring** xử lý các nhánh có chung tiền tố để parser có thể trì hoãn quyết định lựa chọn production.

Ví dụ:

~~~text
Statement -> "if" Expression "then" Statement
           | "if" Expression "then" Statement "else" Statement
~~~

Hai nhánh cùng bắt đầu bằng một chuỗi. Có thể left-factor:

~~~text
Statement -> "if" Expression "then" Statement OptionalElse
OptionalElse -> "else" Statement
              | epsilon
~~~

Phép biến đổi này giải quyết vấn đề chung tiền tố. Nó không phải là cách loại bỏ đệ quy trái.

Ngược lại, grammar:

~~~text
Expression -> Expression "+" Term
           | Term
~~~

cần loại bỏ đệ quy trái nếu parser top-down không hỗ trợ. Left factoring không giải quyết được lời gọi đệ quy trước khi tiêu thụ token.

Hai phép biến đổi có thể cùng cần thiết trong một grammar, nhưng phải xác định vấn đề cụ thể trước khi áp dụng.

## 11. Các cách khác để xử lý biểu thức

Không phải lúc nào cũng cần biến đổi grammar thành nhiều tầng nonterminal.

### 11.1 Pratt parser

Pratt parser phân tích biểu thức bằng binding power hoặc precedence của toán tử. Parser đọc một biểu thức tiền tố rồi tiếp tục mở rộng nó bằng các toán tử hậu tố/infix theo mức ưu tiên.

Ý tưởng khái quát:

~~~text
parseExpression(minBindingPower):
    left = parsePrefix()

    while next token is an infix operator
          and precedence(next) >= minBindingPower:
        operator = consume()
        right = parseExpression(rightBindingPower(operator))
        left = makeNode(operator, left, right)

    return left
~~~

Pratt parser hữu ích khi DSL có nhiều toán tử, precedence và associativity khác nhau. Nó không loại bỏ đệ quy trái bằng phép biến đổi grammar; thay vào đó, thuật toán parser xử lý trực tiếp cấu trúc biểu thức theo binding power.

### 11.2 Precedence climbing

Precedence climbing là một kỹ thuật tương tự, thường dùng một hàm parse expression với mức ưu tiên tối thiểu. Nó có thể đơn giản hơn khi chỉ cần xử lý các toán tử infix.

### 11.3 Giữ đệ quy trái với parser hỗ trợ

Nếu parser generator hỗ trợ đệ quy trái trực tiếp và có cách xử lý precedence rõ ràng, giữ grammar đệ quy trái có thể làm grammar ngắn và gần với ngữ nghĩa toán học hơn.

Lựa chọn này cần dựa trên giới hạn công cụ, khả năng debug, thông báo lỗi và cách nhóm muốn duy trì grammar.

## 12. Các trường hợp cần cẩn thận khi biến đổi

### 12.1 Không có nhánh cơ sở

Ví dụ:

~~~text
A -> A "x"
~~~

Không có nhánh cơ sở để bắt đầu suy dẫn. Ngôn ngữ sinh ra không có chuỗi hữu hạn từ A. Không thể áp dụng công thức thông thường với một beta không tồn tại rồi giả định rằng đã có grammar hữu ích.

### 12.2 Nhánh đệ quy không tạo tiến triển

Ví dụ:

~~~text
A -> A
   | "x"
~~~

Nhánh A -> A không thêm ký hiệu nào. Cần loại bỏ production không tiến triển hoặc phân tích chu trình trước khi dùng phép biến đổi tiêu chuẩn.

### 12.3 Nhánh cơ sở có thể rỗng

Nếu beta có thể sinh epsilon, việc biến đổi cần giữ đúng khả năng sinh chuỗi rỗng và tránh tạo chu trình mới. Không nên áp dụng công thức mà không kiểm tra nullable và tập chuỗi được sinh.

### 12.4 Semantic action gắn trực tiếp với production

Trong một số parser generator, production chứa semantic action. Khi thay đổi cấu trúc grammar, vị trí và thứ tự thực thi action có thể thay đổi.

Hãy chuyển các action sang giai đoạn xây AST hoặc visitor nếu phù hợp, rồi kiểm tra AST sau biến đổi. Không giả định rằng grammar tương đương thì các action cũ sẽ tự động tạo cùng kết quả.

### 12.5 Error recovery

Grammar sau biến đổi có thể tạo parse tree khác và ảnh hưởng vị trí parser phát hiện lỗi. Cần kiểm tra cả thông báo lỗi với các input không hợp lệ, đặc biệt khi DSL hướng tới người dùng nghiệp vụ.

## 13. Kiểm thử grammar sau khi loại bỏ đệ quy trái

Sau khi biến đổi, cần xác nhận grammar mới nhận đúng ngôn ngữ và giữ đúng ngữ nghĩa.

### 13.1 Kiểm thử đầu vào hợp lệ

Với biểu thức số học:

~~~text
1
1 + 2
1 + 2 + 3
1 * 2 + 3
(1 + 2) * 3
~~~

Các trường hợp này kiểm tra:

- Nhánh cơ sở.
- Một phần mở rộng.
- Nhiều phần mở rộng.
- Thứ tự ưu tiên.
- Ngoặc lồng nhau.

### 13.2 Kiểm thử đầu vào không hợp lệ

~~~text
+ 1
1 +
1 + * 2
(1 + 2
1 2
~~~

Parser cần từ chối đúng vị trí và cung cấp thông báo đủ rõ. Sau khi loại bỏ đệ quy trái, cần bảo đảm parser không rơi vào vòng lặp hoặc tiêu thụ token sai khi gặp input lỗi.

### 13.3 Kiểm thử associativity

Đối với phép trừ:

~~~text
10 - 3 - 2
~~~

Kết quả kết hợp trái là 5:

~~~text
(10 - 3) - 2 = 5
~~~

Nếu kết hợp phải, kết quả là 9:

~~~text
10 - (3 - 2) = 9
~~~

Test này phát hiện lỗi fold AST sau khi grammar được chuyển sang dạng không đệ quy trái.

### 13.4 Kiểm thử tương đương trước và sau biến đổi

Nếu có parser cũ hoặc parser tham chiếu, có thể chạy cùng tập input và so sánh:

- Input được chấp nhận hoặc từ chối.
- AST chuẩn hóa.
- Kết quả đánh giá.
- Vị trí và loại lỗi trong các trường hợp quan trọng.

Không nhất thiết parse tree thô phải giống nhau vì cấu trúc grammar đã thay đổi. Hãy so sánh AST ngữ nghĩa hoặc kết quả theo hợp đồng DSL.

## 14. Quy trình xử lý đệ quy trái

Một quy trình thực tế:

1. **Xác định parser:** biết parser là LL, recursive descent, LR, PEG hay công cụ có hỗ trợ riêng.
2. **Phát hiện chu trình:** kiểm tra đệ quy trực tiếp, gián tiếp và qua nonterminal nullable.
3. **Xác định mục tiêu:** quyết định giữ đệ quy trái hay biến đổi dựa trên parser.
4. **Ghi nhận ngữ nghĩa:** xác định precedence, associativity và semantic action hiện tại.
5. **Loại bỏ trực tiếp:** dùng công thức với nhánh cơ sở và phần mở rộng khi cần parser top-down.
6. **Loại bỏ gián tiếp:** sắp thứ tự nonterminal, thay thế production và xử lý đệ quy trực tiếp phát sinh.
7. **Xử lý nullable và chu trình đặc biệt:** kiểm tra epsilon, production không tiến triển và nhánh không có cơ sở.
8. **Xây AST:** bảo toàn associativity và cấu trúc miền.
9. **Kiểm thử:** dùng input hợp lệ, không hợp lệ, biên và các biểu thức có nhiều toán tử.
10. **Đánh giá diagnostics:** xác nhận lỗi vẫn dễ hiểu sau biến đổi.

Đừng bắt đầu bằng việc thay mọi production có tên xuất hiện ở đầu vế phải. Cần xác định chu trình suy dẫn thực sự và loại parser đang dùng.

## 15. Những sai lầm thường gặp

### Cho rằng đệ quy trái luôn là grammar sai

Đệ quy trái hợp lệ trong nhiều grammar và được parser LR xử lý tự nhiên.

**Cách khắc phục:** quyết định theo chiến lược parser và yêu cầu công cụ.

### Chỉ tìm đệ quy trái trực tiếp

Đệ quy gián tiếp hoặc qua nonterminal nullable có thể bị bỏ sót.

**Cách khắc phục:** xét chu trình phụ thuộc và khả năng sinh epsilon ở đầu production.

### Dùng left factoring để giải quyết đệ quy trái

Left factoring xử lý tiền tố chung, không xử lý lời gọi đệ quy trái.

**Cách khắc phục:** xác định đúng loại vấn đề trước khi biến đổi grammar.

### Làm mất associativity sau biến đổi

Grammar mới có thể tạo parse tree đuôi đệ quy phải, khiến AST bị nhóm sai.

**Cách khắc phục:** fold-left hoặc fold-right theo associativity được định nghĩa.

### Không kiểm tra precedence

Các toán tử có thể bị nhóm sai sau khi gộp hoặc tách production.

**Cách khắc phục:** phân tầng grammar hoặc dùng Pratt/precedence climbing, sau đó kiểm thử biểu thức hỗn hợp.

### Áp dụng công thức khi không có nhánh cơ sở

Grammar có thể không sinh được chuỗi hữu hạn hoặc có chu trình không tiến triển.

**Cách khắc phục:** phân tích production rỗng, nullable và tính khả sinh trước khi biến đổi.

### Giả định parser generator nào cũng hỗ trợ giống nhau

Mỗi công cụ có giới hạn riêng về direct recursion, indirect recursion và precedence.

**Cách khắc phục:** xác minh tài liệu và thử nghiệm trên đúng phiên bản công cụ.

## 16. Câu hỏi tự kiểm tra

1. Định nghĩa đệ quy trái bằng quan hệ suy dẫn.
2. Phân biệt đệ quy trái trực tiếp và gián tiếp.
3. Vì sao recursive descent có thể lặp vô hạn với grammar đệ quy trái?
4. Vì sao parser LR thường xử lý đệ quy trái tự nhiên?
5. Nonterminal nullable có thể tạo đệ quy trái như thế nào?
6. Viết lại A -> A "+" Number | Number để loại bỏ đệ quy trái.
7. Nêu các bước xử lý đệ quy trái gián tiếp.
8. Phân biệt đệ quy trái với kết hợp trái.
9. Vì sao cần fold-left khi parse phép trừ sau khi biến đổi grammar?
10. Phân biệt loại bỏ đệ quy trái và left factoring.
11. Pratt parser xử lý precedence mà không cần grammar biểu thức đệ quy trái như thế nào?
12. Những kiểm thử nào cần chạy sau khi biến đổi grammar?

Khi làm việc với grammar DSL, hãy xem đệ quy trái như một đặc điểm cần được hiểu trong mối quan hệ với parser. Nếu cần chuyển grammar sang dạng top-down, hãy biến đổi có kiểm soát và bảo toàn AST, precedence, associativity cùng thông báo lỗi mà người dùng cần.
