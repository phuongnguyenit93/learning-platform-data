# Xây parser và AST

Một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL) cần một cách chuyển source text thành cấu trúc có thể kiểm tra, biến đổi và thực thi. Parser đảm nhận việc đọc token theo grammar; Abstract Syntax Tree (AST) biểu diễn cấu trúc có ý nghĩa của chương trình sau khi bỏ qua chi tiết cú pháp không cần thiết. Đây là nền tảng cho type checking, name resolution, formatter, compiler, interpreter, diagnostics và IDE tooling.

**Xây parser và AST** là dự án thực hành giúp đi từ một grammar nhỏ đến một front end hoàn chỉnh: đọc source, tokenize, parse declaration/expression, tạo AST, lưu source location, báo lỗi có cấu trúc và kiểm thử các trường hợp hợp lệ/không hợp lệ. Dự án nên bắt đầu với một DSL đủ nhỏ để hiểu rõ từng phase, nhưng có đủ construct đại diện như declaration, expression, operator precedence, block, function call và rule.

Ta sẽ xây một DSL minh họa có tên MiniRule. Nó hỗ trợ khai báo biến, rule với điều kiện và action, biểu thức số học/logic, function call, member access và block statement.

Ví dụ source:

~~~text
let minimumAge = 18;

rule ApproveAdult {
    when customer.age >= minimumAge
         and customer.isActive
         and not customer.isBlocked;

    then approve(customer.id);
}
~~~

Parser sẽ chuyển source thành token stream, sau đó tạo AST. AST không chỉ là một bản sao của text; nó biểu diễn rõ đây là một variable declaration, một rule declaration, một binary expression và một function call.

~~~mermaid
flowchart TD
    A[Source text] --> B[Lexer]
    B --> C[Token stream]
    C --> D[Parser]
    D --> E[AST]
    E --> F[Name resolution]
    F --> G[Type checking]
    G --> H[Interpreter or compiler]
~~~

Trong phạm vi dự án này, trọng tâm là lexer, parser và AST. Name resolution, type checking và execution có thể được mở rộng sau khi front end hoạt động ổn định.

## 1. Mục tiêu và phạm vi dự án

Sau khi hoàn thành, một chương trình Java có thể:

- Nhận source text từ String hoặc file.
- Chuyển ký tự thành token có loại và source position.
- Parse một chương trình gồm nhiều declaration.
- Tạo AST cho variable, rule, statement và expression.
- Xử lý precedence/associativity của operator.
- Phát hiện syntax error và trả diagnostic có vị trí.
- Tiếp tục parse sau một số lỗi để thu thập nhiều diagnostic.
- In AST dưới dạng tree hoặc format source.
- Kiểm thử lexer/parser bằng ví dụ và property-based test.

### Chưa cần triển khai ngay

Để giữ dự án tập trung, có thể hoãn:
- Generic type system.
- Macro và compile-time metaprogramming.
- Plugin grammar.
- Module import.
- Incremental parsing.
- Full semantic analysis.
- Code generation sang JVM bytecode.

Khi parser và AST có contract rõ, các tính năng này có thể được thêm dần.

### Chọn phiên bản Java

Ví dụ dùng Java 17 trở lên để tận dụng record và sealed interface. Nếu project dùng Java thấp hơn, có thể thay record bằng class bất biến và sealed interface bằng interface/abstract class thông thường.

## 2. Cấu trúc project

Một cấu trúc thư mục đơn giản:

~~~text
mini-rule/
  src/
    main/
      java/
        example/minirule/
          Main.java
          source/
            SourceText.java
            SourceSpan.java
          lexer/
            TokenType.java
            Token.java
            Lexer.java
          ast/
            Expr.java
            Stmt.java
            Declaration.java
            AstPrinter.java
          parser/
            Parser.java
            ParseResult.java
            Diagnostic.java
            DiagnosticCode.java
    test/
      java/
        example/minirule/
          LexerTest.java
          ParserTest.java
          AstPrinterTest.java
          ParserPropertyTest.java
  examples/
    basic.mr
    invalid.mr
~~~

### Tách package theo trách nhiệm

- source: quản lý source buffer và vị trí.
- lexer: nhận diện token.
- ast: mô hình cú pháp.
- parser: chuyển token thành AST và diagnostic.
- test: kiểm tra từng phase.
- examples: chương trình DSL để chạy thử.

### Luồng phụ thuộc

Lexer chỉ cần source model và token model. AST không phụ thuộc lexer. Parser dùng lexer output và AST model. Điều này giúp kiểm thử từng thành phần độc lập.

### Entry point

Main chỉ orchestration: đọc source, tạo lexer, parse, in diagnostic hoặc AST. Không đặt logic lexer/parser vào Main.

## 3. Thiết kế grammar trước khi viết code

Grammar là hợp đồng cú pháp của language. Viết grammar trước giúp xác định token, AST node và parser method.

Grammar MiniRule:

~~~text
program         -> declaration* EOF ;

declaration     -> variableDecl
                 | ruleDecl
                 | statement ;

variableDecl    -> "let" IDENTIFIER "=" expression ";" ;

ruleDecl        -> "rule" IDENTIFIER "{"
                     "when" expression ";"
                     "then" statement
                   "}" ;

statement       -> block
                 | printStmt
                 | expressionStmt ;

block           -> "{" declaration* "}" ;
printStmt       -> "print" expression ";" ;
expressionStmt -> expression ";" ;

expression      -> assignment ;
assignment      -> logicOr ;
logicOr         -> logicAnd ( "or" logicAnd )* ;
logicAnd        -> equality ( "and" equality )* ;
equality        -> comparison ( ( "==" | "!=" ) comparison )* ;
comparison      -> term ( ( ">" | ">=" | "<" | "<=" ) term )* ;
term            -> factor ( ( "+" | "-" ) factor )* ;
factor          -> unary ( ( "*" | "/" ) unary )* ;
unary           -> ( "!" | "-" ) unary
                 | call ;
call            -> primary ( "(" arguments? ")" | "." IDENTIFIER )* ;
arguments       -> expression ( "," expression )* ;
primary         -> NUMBER
                 | STRING
                 | "true"
                 | "false"
                 | "null"
                 | IDENTIFIER
                 | "(" expression ")" ;
~~~

### Grammar notation

- Terminal là token cụ thể như let, identifier, dấu ngoặc.
- Nonterminal là production như expression hoặc declaration.
- Dấu * nghĩa là lặp zero hoặc nhiều lần.
- Dấu ? nghĩa là tùy chọn.
- Dấu | biểu diễn lựa chọn.
- Parentheses nhóm một phần production.

### Vì sao dùng grammar phân tầng?

Expression được chia thành logicOr, logicAnd, equality, comparison, term, factor và unary. Cấu trúc này mã hóa precedence: nhân/chia bind chặt hơn cộng/trừ; cộng/trừ bind chặt hơn comparison; AND bind chặt hơn OR.

### Grammar và semantics khác nhau

Grammar chỉ mô tả cấu trúc hợp lệ. Nó không xác định customer có tồn tại hay không, age có phải Integer hay không hoặc approve có được phép gọi trong rule không. Những điều đó thuộc name resolution/type/semantic analysis.

### Tránh grammar mơ hồ

Mỗi input hợp lệ nên có cách parse xác định theo semantics. Nếu grammar có nhiều cách nhóm expression, phải định nghĩa precedence/associativity hoặc dùng parser algorithm hỗ trợ ambiguity có chủ đích.

## 4. Xác định token set

Lexer cần phân biệt các token. Trước khi viết scanner, liệt kê token type.

~~~java
public enum TokenType {
    // Single-character punctuation
    LEFT_PAREN, RIGHT_PAREN,
    LEFT_BRACE, RIGHT_BRACE,
    COMMA, DOT, SEMICOLON,

    // Operators
    PLUS, MINUS, STAR, SLASH,
    BANG, BANG_EQUAL,
    EQUAL, EQUAL_EQUAL,
    GREATER, GREATER_EQUAL,
    LESS, LESS_EQUAL,

    // Literals and names
    IDENTIFIER, STRING, NUMBER,

    // Keywords
    LET, RULE, WHEN, THEN,
    PRINT, TRUE, FALSE, NULL,
    AND, OR, NOT,

    EOF
}
~~~

### Token type và lexeme

Token type cho biết vai trò cú pháp. Lexeme là đoạn text nguồn tạo token đó. Ví dụ token GREATER_EQUAL có lexeme >=.

### Keyword và identifier

Lexer thường scan identifier trước, sau đó tra keyword table. Như vậy customer là IDENTIFIER, còn rule là RULE.

### Literal value

Token NUMBER có thể giữ raw lexeme và numeric value. Trong dự án nhỏ, có thể lưu cả hai; với DSL có precision phức tạp, nên trì hoãn conversion đến AST literal builder.

### EOF

EOF là token đặc biệt giúp parser biết source đã kết thúc. Nó không tương ứng ký tự thực tế.

## 5. Source text và source span

Diagnostic tốt cần biết lỗi nằm ở đâu. Không nên chỉ lưu message text.

Một source span biểu diễn đoạn source:

~~~java
public record SourceSpan(
    int startOffset,
    int endOffset,
    int startLine,
    int startColumn,
    int endLine,
    int endColumn
) {}
~~~

### Offset

Java String dùng UTF-16 code unit. Offset trong ví dụ này được tính theo index của String. Nếu IDE protocol dùng code point hoặc UTF-8 byte offset, cần mapping rõ ràng.

### Line và column

Lexer duy trì line/column khi tiêu thụ ký tự. Line thường bắt đầu từ 1; column có thể bắt đầu từ 1 hoặc 0 nhưng phải nhất quán.

### SourceSpan của token

Token nên lưu span. Parser dùng span của token đầu/cuối để gán span cho AST node.

### Synthetic token/node

Khi parser recovery bằng cách giả định token bị thiếu, token đó là synthetic và có span zero-width hoặc metadata riêng. Không giả vờ nó xuất hiện trong source.

### SourceText

Có thể tạo một wrapper bất biến:

~~~java
public final class SourceText {
    private final String name;
    private final String text;

    public SourceText(String name, String text) {
        this.name = name;
        this.text = text;
    }

    public String name() {
        return name;
    }

    public String text() {
        return text;
    }

    public int length() {
        return text.length();
    }
}
~~~

Trong implementation đầy đủ, có thể thêm line-start index để chuyển offset thành line/column hiệu quả.

## 6. Xây Token model

Token giữ type, lexeme, literal và span.

~~~java
public record Token(
    TokenType type,
    String lexeme,
    Object literal,
    SourceSpan span
) {
    @Override
    public String toString() {
        return type + " " + lexeme + " " + literal;
    }
}
~~~

### Vì sao cần literal?

Lexeme 123 là String; literal có thể là Integer/Long/BigDecimal. AST literal node nên giữ giá trị đã parse theo semantics.

### Vì sao giữ lexeme?

Lexeme hữu ích cho diagnostic, formatter, source reconstruction và debugging. Nếu chỉ giữ literal, không thể biết người dùng viết 1.0 hay 1.00.

### Token bất biến

Record giúp token immutable, dễ chia sẻ và test. Lexer tạo token mới, parser chỉ đọc.

## 7. Xây lexer theo single-pass scanner

Lexer thường dùng cursor index và scan source từ trái sang phải.

Các state cơ bản:
- start: đầu token.
- current: vị trí đang đọc.
- line/column: vị trí hiện tại.
- tokens: danh sách token.
- diagnostics: lỗi lexical.

~~~java
public final class Lexer {
    private final SourceText source;
    private final String text;
    private final List<Token> tokens = new ArrayList<>();
    private final List<Diagnostic> diagnostics = new ArrayList<>();

    private int start;
    private int current;
    private int line = 1;
    private int column = 1;
    private int startLine = 1;
    private int startColumn = 1;

    public Lexer(SourceText source) {
        this.source = source;
        this.text = source.text();
    }

    public LexResult scan() {
        while (!isAtEnd()) {
            start = current;
            startLine = line;
            startColumn = column;
            scanToken();
        }

        tokens.add(new Token(
            TokenType.EOF,
            "",
            null,
            new SourceSpan(current, current, line, column, line, column)
        ));

        return new LexResult(tokens, diagnostics);
    }

    private boolean isAtEnd() {
        return current >= text.length();
    }

    private char advance() {
        char c = text.charAt(current++);
        if (c == '\n') {
            line++;
            column = 1;
        } else {
            column++;
        }
        return c;
    }

    private char peek() {
        return isAtEnd() ? '\0' : text.charAt(current);
    }

    private char peekNext() {
        return current + 1 >= text.length()
            ? '\0'
            : text.charAt(current + 1);
    }

    private boolean match(char expected) {
        if (isAtEnd() || text.charAt(current) != expected) {
            return false;
        }
        advance();
        return true;
    }

    private String lexeme() {
        return text.substring(start, current);
    }

    private SourceSpan span() {
        return new SourceSpan(
            start, current,
            startLine, startColumn,
            line, column
        );
    }
}
~~~

Đây là skeleton; các method scanToken, string, number, identifier và comment sẽ được bổ sung.

### Single-pass

Cursor chỉ tiến về phía trước trong lexer. Tránh scan lại source nhiều lần hoặc tạo substring trung gian cho mọi ký tự.

### Whitespace

Whitespace thường bị bỏ qua nhưng vẫn cập nhật line/column. Tab cần policy về column: đếm một code unit hay visual tab stop. Với diagnostics cơ bản, có thể đếm một column và để editor tự tính visual position.

### Comment

Có thể hỗ trợ line comment bắt đầu bằng // và block comment bắt đầu bằng /* kết thúc bằng */. Block comment chưa đóng phải tạo diagnostic.

### Longest match

Các operator hai ký tự như ==, !=, >=, <= cần được nhận diện trước operator một ký tự. Lexer dùng lookahead một ký tự để chọn token dài nhất.

## 8. Lexer cho punctuation và operator

Một scanner có thể dùng switch:

~~~java
private void scanToken() {
    char c = advance();

    switch (c) {
        case '(' -> addToken(TokenType.LEFT_PAREN);
        case ')' -> addToken(TokenType.RIGHT_PAREN);
        case '{' -> addToken(TokenType.LEFT_BRACE);
        case '}' -> addToken(TokenType.RIGHT_BRACE);
        case ',' -> addToken(TokenType.COMMA);
        case '.' -> addToken(TokenType.DOT);
        case ';' -> addToken(TokenType.SEMICOLON);
        case '+' -> addToken(TokenType.PLUS);
        case '-' -> addToken(TokenType.MINUS);
        case '*' -> addToken(TokenType.STAR);
        case '/' -> scanSlashOrComment();
        case '!' -> addToken(
            match('=') ? TokenType.BANG_EQUAL : TokenType.BANG
        );
        case '=' -> addToken(
            match('=') ? TokenType.EQUAL_EQUAL : TokenType.EQUAL
        );
        case '>' -> addToken(
            match('=') ? TokenType.GREATER_EQUAL : TokenType.GREATER
        );
        case '<' -> addToken(
            match('=') ? TokenType.LESS_EQUAL : TokenType.LESS
        );
        case ' ', '\r', '\t', '\n' -> { }
        case '"' -> scanString();
        default -> {
            if (isDigit(c)) {
                scanNumber();
            } else if (isIdentifierStart(c)) {
                scanIdentifier();
            } else {
                reportUnexpectedCharacter(c);
            }
        }
    }
}
~~~

### addToken

~~~java
private void addToken(TokenType type) {
    tokens.add(new Token(type, lexeme(), null, span()));
}
~~~

### Slash và comment

Nếu ký tự tiếp theo là /, scan đến newline. Nếu là *, scan đến */. Nếu không, tạo token SLASH.

### Unexpected character

Không nên silently bỏ ký tự lạ. Tạo diagnostic với code như LEX_UNEXPECTED_CHARACTER và span chính xác.

### Lexical progress

Mỗi vòng scanToken phải tiêu thụ ít nhất một ký tự hoặc kết thúc. Điều này tránh infinite loop khi gặp invalid input.

## 9. Lexer cho identifier và keyword

Identifier có thể bắt đầu bằng chữ cái hoặc underscore, sau đó gồm chữ, số và underscore.

~~~java
private boolean isIdentifierStart(char c) {
    return Character.isLetter(c) || c == '_';
}

private boolean isIdentifierPart(char c) {
    return Character.isLetterOrDigit(c) || c == '_';
}

private void scanIdentifier() {
    while (isIdentifierPart(peek())) {
        advance();
    }

    String text = lexeme();
    TokenType type = KEYWORDS.getOrDefault(
        text,
        TokenType.IDENTIFIER
    );

    addToken(type);
}
~~~

Keyword table:

~~~java
private static final Map<String, TokenType> KEYWORDS = Map.of(
    "let", TokenType.LET,
    "rule", TokenType.RULE,
    "when", TokenType.WHEN,
    "then", TokenType.THEN,
    "print", TokenType.PRINT,
    "true", TokenType.TRUE,
    "false", TokenType.FALSE,
    "null", TokenType.NULL,
    "and", TokenType.AND,
    "or", TokenType.OR,
    "not", TokenType.NOT
);
~~~

### Keyword boundary

Identifier customerRule không được tách thành keyword customer và identifier Rule. Scan toàn identifier rồi lookup keyword.

### Unicode identifier

Nếu language hỗ trợ Unicode identifier đầy đủ, dùng code point API thay vì char đơn lẻ để không tách surrogate pair. Grammar cần nêu normalization policy.

### Case sensitivity

Chọn language case-sensitive hoặc case-insensitive. Không nên lowercase tùy tiện nếu identifier có semantics phân biệt case.

## 10. Lexer cho number và string literal

### Number literal

Ví dụ DSL hỗ trợ integer và decimal:

~~~text
42
3.1415
0
-10
~~~

Dấu trừ thường là unary operator, không thuộc number token. Điều này giúp parser xử lý precedence thống nhất.

~~~java
private void scanNumber() {
    while (isDigit(peek())) {
        advance();
    }

    if (peek() == '.' && isDigit(peekNext())) {
        advance();
        while (isDigit(peek())) {
            advance();
        }
    }

    String raw = lexeme();
    Object value = raw.contains(".")
        ? new BigDecimal(raw)
        : Long.parseLong(raw);

    addLiteralToken(TokenType.NUMBER, value);
}
~~~

Implementation production cần bắt NumberFormatException và tạo diagnostic thay vì để exception thoát ra. Cũng cần định nghĩa exponent, radix, separator và numeric suffix nếu grammar hỗ trợ.

### String literal

Ví dụ:

~~~text
"hello"
"customer\napproved"
"quote: \""
~~~

Lexer cần xử lý escape như newline, tab, quote và backslash. Nếu string chưa đóng trước EOF, tạo diagnostic LEX_UNTERMINATED_STRING.

### Raw lexeme và decoded value

Raw lexeme giữ nguyên source; literal value chứa chuỗi đã decode escape. Giữ cả hai giúp formatter/diagnostic.

### String newline

Nếu cho phép multiline string, line/column phải cập nhật đúng. Nếu không, newline trước closing quote là lỗi.

### Literal size limit

Nếu source không tin cậy, giới hạn string/number literal size để tránh memory exhaustion.

## 11. LexResult và Diagnostic model

Lexer có thể gặp nhiều lỗi trong một source. Không nên chỉ throw exception đầu tiên.

~~~java
public enum DiagnosticSeverity {
    ERROR, WARNING, INFO
}

public record Diagnostic(
    String code,
    DiagnosticSeverity severity,
    String message,
    SourceSpan span
) {}

public record LexResult(
    List<Token> tokens,
    List<Diagnostic> diagnostics
) {}
~~~

### Stable code

Code như LEX_UNTERMINATED_STRING ổn định hơn message text. IDE/CI có thể dựa vào code để xử lý.

### Diagnostic span

Span chỉ rõ đoạn source gây lỗi. Với EOF error, dùng zero-width span ở cuối source.

### Lexer recovery

Sau ký tự không hợp lệ, lexer có thể bỏ qua ký tự đó và tiếp tục. Với string chưa đóng, thường kết thúc token/error ở EOF.

### Không dùng exception cho lỗi cú pháp thường gặp

Syntax/lexical error là kết quả dự kiến của việc parse source người dùng. Nên trả diagnostics; exception dành cho lỗi nội bộ hoặc resource failure.

## 12. Thiết kế AST

AST biểu diễn cấu trúc cú pháp có ý nghĩa, không giữ mọi chi tiết formatting.

Ví dụ source:

~~~text
let minimumAge = 18;
~~~

AST tương ứng:

~~~text
VariableDeclaration
  name: minimumAge
  initializer:
    NumberLiteral(18)
~~~

### AST và parse tree/CST

| Cấu trúc | Mục đích | Nội dung |
|---|---|---|
| Token stream | Lexical units | Token, lexeme, source span. |
| Parse tree/CST | Cấu trúc grammar đầy đủ | Rule node, punctuation, trivia nếu giữ. |
| AST | Cấu trúc có ý nghĩa | Declaration, statement, expression. |
| IR | Mô hình phục vụ phân tích/thực thi | Typed/resolved/normalized representation. |

### Khi nào cần CST?

IDE formatter/refactoring cần comment, whitespace và dấu ngoặc nguyên bản có thể cần CST hoặc trivia. Compiler đơn giản thường chỉ cần AST.

### Node identity

Mỗi node nên có source span. Có thể có stable node ID nếu editor cần incremental updates hoặc diagnostics reference.

### Immutability

AST immutable giúp visitor, cache và concurrent analysis dễ dự đoán. Parser tạo node; semantic analysis lưu kết quả ở side table thay vì sửa node nếu cần chia sẻ.

## 13. AST model bằng Java records và sealed interfaces

Tách expression và statement thành hierarchy riêng.

~~~java
public sealed interface Expr
    permits LiteralExpr, NameExpr, UnaryExpr,
            BinaryExpr, CallExpr, MemberExpr, GroupExpr {
    SourceSpan span();
}

public record LiteralExpr(
    Object value,
    Token token,
    SourceSpan span
) implements Expr {}

public record NameExpr(
    Token name,
    SourceSpan span
) implements Expr {}

public record UnaryExpr(
    Token operator,
    Expr operand,
    SourceSpan span
) implements Expr {}

public record BinaryExpr(
    Expr left,
    Token operator,
    Expr right,
    SourceSpan span
) implements Expr {}

public record CallExpr(
    Expr callee,
    List<Expr> arguments,
    SourceSpan span
) implements Expr {}

public record MemberExpr(
    Expr object,
    Token member,
    SourceSpan span
) implements Expr {}

public record GroupExpr(
    Expr expression,
    SourceSpan span
) implements Expr {}
~~~

### LiteralExpr

Giữ giá trị literal đã decode và token gốc. Có thể tách NumberLiteral/StringLiteral nếu type system yêu cầu.

### NameExpr

Biểu diễn một identifier được dùng như expression. Resolver sẽ tìm symbol sau.

### UnaryExpr

Biểu diễn operator một ngôi như ! hoặc -.

### BinaryExpr

Biểu diễn operator hai ngôi như +, >=, and.

### CallExpr

Biểu diễn function call. Callee có thể là NameExpr hoặc MemberExpr.

### MemberExpr

Biểu diễn access như customer.age. Không cần biến mọi member thành string path ngay trong parser; AST giữ cấu trúc để resolver phân biệt.

### GroupExpr

Có thể giữ node group nếu CST/formatter cần parentheses. Nếu AST chỉ phục vụ semantics, có thể bỏ group node sau khi parser đã dùng nó để xác định precedence.

## 14. AST cho declaration và statement

~~~java
public sealed interface Declaration
    permits VariableDeclaration, RuleDeclaration, Statement {
    SourceSpan span();
}

public sealed interface Statement extends Declaration
    permits BlockStatement, PrintStatement, ExpressionStatement {}

public record VariableDeclaration(
    Token name,
    Expr initializer,
    SourceSpan span
) implements Declaration {}

public record RuleDeclaration(
    Token name,
    Expr condition,
    Statement action,
    SourceSpan span
) implements Declaration {}

public record BlockStatement(
    List<Declaration> declarations,
    SourceSpan span
) implements Statement {}

public record PrintStatement(
    Expr expression,
    SourceSpan span
) implements Statement {}

public record ExpressionStatement(
    Expr expression,
    SourceSpan span
) implements Statement {}
~~~

Đây là một model tối giản. Nếu Java version hoặc sealed hierarchy không phù hợp, có thể dùng interface thường và class bất biến.

### Program root

~~~java
public record Program(
    List<Declaration> declarations,
    SourceSpan span
) {}
~~~

Root node giúp parser luôn trả về một object nhất quán ngay cả khi source rỗng.

### RuleDeclaration

Rule gồm name, condition và action. Có thể mở rộng metadata như priority, tags, description và source version sau.

### BlockStatement

Block chứa declaration/statement trong scope. Name resolution có thể tạo scope riêng khi đi qua block.

### Source span cho AST

Span của parent thường bắt đầu ở keyword đầu và kết thúc sau token đóng cuối. Với nested node, span child thường nằm trong span parent.

## 15. Parser architecture: recursive descent

Với grammar có declaration và statement rõ ràng, recursive descent dễ triển khai và debug. Mỗi nonterminal thường có một method.

Parser giữ:
- Token list.
- Current token index.
- Diagnostics.
- Helper peek/advance/match/consume.
- Các method parse declaration/statement/expression.

~~~java
public final class Parser {
    private final List<Token> tokens;
    private final List<Diagnostic> diagnostics = new ArrayList<>();
    private int current;

    public Parser(List<Token> tokens) {
        this.tokens = tokens;
    }

    public ParseResult parse() {
        List<Declaration> declarations = new ArrayList<>();

        while (!check(TokenType.EOF)) {
            int before = current;
            try {
                declarations.add(declaration());
            } catch (ParseFailure failure) {
                synchronize();
            }

            if (current == before && !check(TokenType.EOF)) {
                advance();
            }
        }

        return new ParseResult(
            new Program(declarations, programSpan()),
            diagnostics
        );
    }
}
~~~

### Parser cursor

Current là index token tiếp theo sẽ được đọc. Parser chỉ di chuyển cursor về phía trước trong recursive descent cơ bản.

### check

check(type) nhìn token hiện tại nhưng không consume.

### advance

advance consume token hiện tại và trả về token vừa consume.

### match

match một trong các token type; nếu match thì consume và trả true.

### consume

consume token nếu đúng type, nếu sai thì tạo ParseFailure/diagnostic.

### EOF safety

Các helper cần xử lý EOF an toàn để không truy cập index vượt token list.

## 16. Parser helper methods

~~~java
private boolean check(TokenType type) {
    if (isAtEnd()) return type == TokenType.EOF;
    return peek().type() == type;
}

private Token peek() {
    return tokens.get(current);
}

private Token previous() {
    return tokens.get(current - 1);
}

private boolean isAtEnd() {
    return peek().type() == TokenType.EOF;
}

private Token advance() {
    if (!isAtEnd()) current++;
    return previous();
}

private boolean match(TokenType... types) {
    for (TokenType type : types) {
        if (check(type)) {
            advance();
            return true;
        }
    }
    return false;
}

private Token consume(TokenType type, String message) {
    if (check(type)) return advance();
    throw error(peek(), message);
}
~~~

### ParseFailure

Có thể dùng exception nội bộ không stack trace nặng để thoát khỏi production hiện tại. Parser bắt nó ở declaration boundary và thực hiện synchronization.

### Error reporting

error(token, message) thêm diagnostic và trả ParseFailure. Không để lỗi cú pháp thông thường biến thành NullPointerException hoặc IndexOutOfBoundsException.

### Parser progress

Sau khi recovery, cursor phải tiến lên hoặc parse loop phải dừng. Điều này ngăn parser lặp vô hạn trên cùng token lỗi.

## 17. Parse declaration

Declaration là entry point cho các cấu trúc top-level hoặc block-level.

~~~java
private Declaration declaration() {
    if (match(TokenType.LET)) {
        return variableDeclaration();
    }

    if (match(TokenType.RULE)) {
        return ruleDeclaration();
    }

    return statement();
}
~~~

### Variable declaration

~~~java
private VariableDeclaration variableDeclaration() {
    Token name = consume(
        TokenType.IDENTIFIER,
        "Expected variable name"
    );

    consume(TokenType.EQUAL, "Expected '=' after variable name");
    Expr initializer = expression();
    Token end = consume(
        TokenType.SEMICOLON,
        "Expected ';' after variable declaration"
    );

    return new VariableDeclaration(
        name,
        initializer,
        span(previousStart(name), end.span())
    );
}
~~~

Helper span ở đây minh họa ý tưởng; implementation cần lấy start từ keyword LET và end từ semicolon.

### Rule declaration

~~~java
private RuleDeclaration ruleDeclaration() {
    Token name = consume(
        TokenType.IDENTIFIER,
        "Expected rule name"
    );

    consume(TokenType.LEFT_BRACE, "Expected '{' after rule name");
    consume(TokenType.WHEN, "Expected 'when' in rule");

    Expr condition = expression();
    consume(TokenType.SEMICOLON, "Expected ';' after condition");

    consume(TokenType.THEN, "Expected 'then' in rule");
    Statement action = statement();

    Token end = consume(TokenType.RIGHT_BRACE, "Expected '}' after rule");

    return new RuleDeclaration(
        name,
        condition,
        action,
        combineSpan(name.span(), end.span())
    );
}
~~~

Ví dụ này dùng span từ name; có thể mở rộng để bắt đầu từ keyword RULE.

### Declaration order

Grammar cho phép nhiều declaration nối tiếp. Parser không cần biết symbol đã khai báo trước hay sau; name resolution xử lý scope/order policy ở phase tiếp theo.

## 18. Parse statement

~~~java
private Statement statement() {
    if (match(TokenType.LEFT_BRACE)) {
        return blockStatement();
    }

    if (match(TokenType.PRINT)) {
        return printStatement();
    }

    return expressionStatement();
}
~~~

### Block

~~~java
private BlockStatement blockStatement() {
    List<Declaration> declarations = new ArrayList<>();

    while (!check(TokenType.RIGHT_BRACE) && !isAtEnd()) {
        declarations.add(declaration());
    }

    Token end = consume(
        TokenType.RIGHT_BRACE,
        "Expected '}' after block"
    );

    return new BlockStatement(declarations, blockSpan(end));
}
~~~

### Print

~~~java
private PrintStatement printStatement() {
    Expr value = expression();
    Token end = consume(
        TokenType.SEMICOLON,
        "Expected ';' after print expression"
    );

    return new PrintStatement(value, statementSpan(end));
}
~~~

### Expression statement

~~~java
private ExpressionStatement expressionStatement() {
    Expr value = expression();
    Token end = consume(
        TokenType.SEMICOLON,
        "Expected ';' after expression"
    );

    return new ExpressionStatement(value, statementSpan(end));
}
~~~

### Semicolon policy

Nếu DSL dùng newline làm statement terminator, lexer/parser cần xử lý newline token hoặc semicolon insertion. Dự án ban đầu dùng semicolon tường minh để giảm ambiguity.

## 19. Parse expression theo precedence levels

Cách recursive descent phổ biến là một method cho mỗi precedence level.

~~~java
private Expr expression() {
    return logicOr();
}

private Expr logicOr() {
    Expr expr = logicAnd();

    while (match(TokenType.OR)) {
        Token operator = previous();
        Expr right = logicAnd();
        expr = new BinaryExpr(
            expr, operator, right,
            combineSpan(expr.span(), right.span())
        );
    }

    return expr;
}

private Expr logicAnd() {
    Expr expr = equality();

    while (match(TokenType.AND)) {
        Token operator = previous();
        Expr right = equality();
        expr = new BinaryExpr(
            expr, operator, right,
            combineSpan(expr.span(), right.span())
        );
    }

    return expr;
}
~~~

Các method equality, comparison, term và factor theo cùng pattern.

### Left associativity

Vòng lặp xây AST từ trái sang phải. Với a - b - c, tree là (a - b) - c.

### Precedence

logicOr gọi logicAnd; logicAnd gọi equality; equality gọi comparison; comparison gọi term; term gọi factor. Vì vậy factor bind chặt hơn term, term chặt hơn comparison.

### Vì sao không parse mọi expression trong một method?

Nếu chỉ có một method parseExpression với nhiều if lồng nhau, precedence dễ bị nhầm và code khó mở rộng.

### Khi nào dùng Pratt parser?

Pratt parser hữu ích khi có nhiều prefix/infix/postfix operator, operator custom hoặc grammar expression thường xuyên mở rộng. Recursive descent precedence ladder dễ hiểu với DSL nhỏ; Pratt linh hoạt hơn với expression-rich DSL.

## 20. Pratt parser cho expression

Pratt parser dựa trên binding power. Parser đọc prefix trước, sau đó tiếp tục tiêu thụ operator có binding power đủ lớn.

~~~java
private Expr parseExpression(int minBindingPower) {
    Token first = advance();
    Expr left = parsePrefix(first);

    while (hasInfixOperator()) {
        Token operator = peek();
        BindingPower bp = bindingPower(operator.type());

        if (bp.left() < minBindingPower) {
            break;
        }

        advance();
        Expr right = parseExpression(bp.right());

        left = new BinaryExpr(
            left,
            operator,
            right,
            combineSpan(left.span(), right.span())
        );
    }

    return left;
}
~~~

### Prefix parser

~~~java
private Expr parsePrefix(Token token) {
    return switch (token.type()) {
        case NUMBER, STRING, TRUE, FALSE, NULL ->
            literalExpression(token);

        case IDENTIFIER ->
            new NameExpr(token, token.span());

        case MINUS, BANG, NOT -> {
            Expr operand = parseExpression(PREFIX_BINDING_POWER);
            yield new UnaryExpr(
                token,
                operand,
                combineSpan(token.span(), operand.span())
            );
        }

        case LEFT_PAREN -> {
            Expr inner = parseExpression(0);
            Token close = consume(
                TokenType.RIGHT_PAREN,
                "Expected ')' after expression"
            );
            yield new GroupExpr(
                inner,
                combineSpan(token.span(), close.span())
            );
        }

        default -> throw error(token, "Expected expression");
    };
}
~~~

### Binding power table

| Operator | Left binding power | Right binding power |
|---|---:|---:|
| OR | 10 | 11 |
| AND | 20 | 21 |
| ==, != | 30 | 31 |
| <, <=, >, >= | 40 | 41 |
| +, - | 50 | 51 |
| *, / | 60 | 61 |
| Prefix !, - | 70 | — |
| Call/member access | 80 | 81 |

Các con số chỉ là ví dụ. Với left-associative operator, right binding power thường cao hơn left theo quy ước này; right-associative operator dùng cặp phù hợp để nhóm từ phải sang trái.

### Postfix operator

Function call và member access thường bind chặt. Có thể xử lý trong parsePrefix loop hoặc như infix/postfix parselet.

### Không trộn hai chiến lược tùy tiện

Có thể dùng recursive descent cho declaration/statement và Pratt cho expression. Đây là kết hợp phổ biến. Nhưng không nên triển khai cùng một expression grammar bằng hai parser path khác nhau nếu không có lý do rõ.

## 21. Parse function call và member access

Grammar:

~~~text
call -> primary ( "(" arguments? ")" | "." IDENTIFIER )* ;
~~~

Ví dụ:

~~~text
approve(customer.id)
money.round(invoice.total, 2)
customer.address.city
~~~

### Call node

Callee có thể là NameExpr hoặc MemberExpr. Arguments là danh sách Expr.

### Member node

customer.address tạo MemberExpr(object = customer, member = address). Tiếp tục .city tạo MemberExpr trên node trước.

### Call chaining

customer.getAddress().city có thể parse thành MemberExpr(CallExpr(MemberExpr(...)), city).

### Argument parsing

Arguments ngăn cách bằng comma; parser phải xử lý empty list, trailing comma theo grammar policy và missing closing parenthesis.

### Arity và type

Parser chỉ kiểm tra cấu trúc. Function tồn tại hay không và số argument có đúng không thuộc resolver/type checker.

## 22. Error recovery và synchronization

Một parser hữu ích không chỉ dừng ở lỗi đầu tiên. Nó có thể đồng bộ tại điểm bắt đầu declaration tiếp theo.

Ví dụ source lỗi:

~~~text
let minimumAge = 18

rule ApproveAdult {
    when customer.age >= minimumAge;
    then approve(customer.id);
}

let retryLimit = 3;
~~~

Thiếu semicolon sau declaration đầu. Parser có thể báo lỗi rồi đồng bộ tại keyword rule hoặc let tiếp theo.

~~~java
private void synchronize() {
    if (!isAtEnd()) advance();

    while (!isAtEnd()) {
        if (previous().type() == TokenType.SEMICOLON) {
            return;
        }

        switch (peek().type()) {
            case LET, RULE, PRINT, WHEN, THEN, RIGHT_BRACE -> {
                return;
            }
            default -> advance();
        }
    }
}
~~~

### Synchronization token

Chọn token thường xuất hiện ở ranh giới declaration/statement. Tùy grammar, semicolon, closing brace, let hoặc rule có thể là điểm đồng bộ.

### Recovery không được lặp vô hạn

Nếu parser đang ở token synchronization, không advance có thể khiến vòng lặp ngoài lặp lại cùng token. Parse loop cần kiểm tra cursor progress.

### Error node

Với IDE, có thể thêm ErrorDeclaration/ErrorExpression vào AST để giữ cấu trúc xung quanh lỗi. Với compiler batch đơn giản, có thể bỏ node lỗi và trả diagnostics.

### Error cascade

Một lỗi thiếu delimiter có thể tạo nhiều diagnostic giả. Recovery cần ưu tiên root error và tránh báo quá nhiều lỗi dây chuyền.

### EOF error

Nếu thiếu closing brace ở EOF, diagnostic span có thể zero-width tại cuối source.

## 23. ParseResult và error model

Parser nên trả cả AST và diagnostics.

~~~java
public record ParseResult(
    Program program,
    List<Diagnostic> diagnostics
) {
    public boolean hasErrors() {
        return diagnostics.stream()
            .anyMatch(d -> d.severity() == DiagnosticSeverity.ERROR);
    }
}
~~~

### Partial AST

Nếu parser recovery, Program có thể chứa các declaration parse thành công trước/sau lỗi. Consumer cần biết AST có lỗi hay không trước khi compile/execute.

### Parse success

Có thể định nghĩa success là không có ERROR diagnostic. WARNING không làm parse fail.

### Internal exception

Parser có thể dùng ParseFailure nội bộ để thoát production. Không expose exception đó như public result nếu đó là syntax error dự kiến.

### Diagnostic code

Dùng code ổn định như PARSE_EXPECTED_SEMICOLON hoặc PARSE_EXPECTED_EXPRESSION. Message có thể được dịch hoặc thay đổi.

### Expected token set

Diagnostic có thể chứa token types mong đợi, actual token và source span để IDE đưa suggestion.

## 24. AstPrinter để kiểm tra cấu trúc

Trước khi có interpreter, cần công cụ in AST để xác nhận parser tạo tree đúng.

Ví dụ output:

~~~text
Program
  VariableDeclaration(minimumAge)
    Literal(18)
  RuleDeclaration(ApproveAdult)
    Condition
      Binary(AND)
        Binary(GREATER_EQUAL)
          Member(customer, age)
          Name(minimumAge)
        Member(customer, isActive)
    Action
      Call(approve)
        Member(customer, id)
~~~

### Prefix notation

AstPrinter có thể in dạng prefix để thấy grouping:

~~~text
(and (>= (. customer age) minimumAge)
     (. customer isActive))
~~~

### Vì sao AST printer hữu ích?

Hai source khác nhau có thể cùng AST. AST printer giúp xác nhận precedence, associativity và nesting mà không bị nhiễu bởi formatting.

### Stable output

Test có thể so sánh AST printer output với expected tree string. Cần giữ format ổn định để test dễ đọc.

### Visitor pattern

Với AST lớn, visitor cho phép triển khai printer, evaluator và analyzer mà không đặt logic vào từng node. Có thể dùng pattern matching/switch nếu Java version hỗ trợ.

## 25. AstVisitor và traversal

Một visitor interface có thể định nghĩa method cho từng node:

~~~java
public interface ExprVisitor<R> {
    R visitLiteral(LiteralExpr expr);
    R visitName(NameExpr expr);
    R visitUnary(UnaryExpr expr);
    R visitBinary(BinaryExpr expr);
    R visitCall(CallExpr expr);
    R visitMember(MemberExpr expr);
    R visitGroup(GroupExpr expr);
}
~~~

Expr có thể có method accept:

~~~java
public sealed interface Expr
    permits LiteralExpr, NameExpr, UnaryExpr,
            BinaryExpr, CallExpr, MemberExpr, GroupExpr {
    SourceSpan span();
    <R> R accept(ExprVisitor<R> visitor);
}
~~~

### Printer

AstPrinter implements ExprVisitor<String> và tạo string cho từng node.

### Evaluator

Evaluator implements ExprVisitor<Value> và thực thi expression. Đây là phase sau parser, nhưng là cách kiểm tra AST có đủ cấu trúc không.

### Semantic analyzer

Analyzer có thể dùng visitor để resolve name, kiểm tra type và thu thập diagnostic.

### Trade-off visitor

Visitor dễ mở rộng operation mới nhưng thêm node mới yêu cầu cập nhật visitor. Với AST ổn định và nhiều operation, đây thường là lựa chọn tốt.

## 26. Kiểm thử lexer

Lexer test nên kiểm tra token type, lexeme, literal và source span.

Ví dụ input:

~~~text
let age = 18 >= 18;
~~~

Expected token sequence:

| Index | Type | Lexeme |
|---:|---|---|
| 0 | LET | let |
| 1 | IDENTIFIER | age |
| 2 | EQUAL | = |
| 3 | NUMBER | 18 |
| 4 | GREATER_EQUAL | >= |
| 5 | NUMBER | 18 |
| 6 | SEMICOLON | ; |
| 7 | EOF | empty |

### Test nhóm token

- Punctuation một ký tự.
- Operator một/hai ký tự.
- Keyword và identifier.
- Integer/decimal literal.
- String escape.
- Comment và whitespace.
- Unicode.
- Unexpected character.
- Unterminated string/comment.
- Empty source và EOF.

### Test source span

Kiểm tra offset, line và column ở đầu file, sau newline và trong multiline string/comment.

### Test keyword boundary

Ví dụ rule và ruleName phải được token hóa khác nhau.

### Test malformed input

Lexer phải trả diagnostic, không crash hoặc lặp vô hạn.

## 27. Kiểm thử parser

Parser test nên so sánh AST structure, không chỉ xác nhận không có exception.

### Variable declaration

Input:

~~~text
let count = 3;
~~~

Kiểm tra root có một VariableDeclaration, tên count và initializer LiteralExpr(3).

### Rule declaration

Kiểm tra name, condition tree và action statement.

### Operator precedence

Input:

~~~text
1 + 2 * 3
~~~

AST phải là:

~~~text
(+ 1 (* 2 3))
~~~

### Associativity

Input:

~~~text
10 - 3 - 2
~~~

AST phải là:

~~~text
(- (- 10 3) 2)
~~~

### Parentheses

Input:

~~~text
(1 + 2) * 3
~~~

AST phải nhóm phép cộng trước phép nhân.

### Function call/member access

Kiểm tra approve(customer.id) tạo CallExpr có MemberExpr argument.

### Nested blocks

Kiểm tra declaration và statement lồng đúng scope structure.

### Error tests

Kiểm tra missing semicolon, unmatched brace, missing expression, wrong token và EOF.

## 28. JUnit test mẫu

~~~java
class ParserTest {
    @Test
    void multiplicationBindsMoreTightlyThanAddition() {
        SourceText source = new SourceText(
            "test.mr",
            "let result = 1 + 2 * 3;"
        );

        LexResult lexed = new Lexer(source).scan();
        ParseResult parsed = new Parser(lexed.tokens()).parse();

        assertFalse(parsed.hasErrors());

        VariableDeclaration declaration =
            assertInstanceOf(
                VariableDeclaration.class,
                parsed.program().declarations().get(0)
            );

        BinaryExpr plus =
            assertInstanceOf(BinaryExpr.class, declaration.initializer());

        assertEquals(TokenType.PLUS, plus.operator().type());

        BinaryExpr multiply =
            assertInstanceOf(BinaryExpr.class, plus.right());

        assertEquals(TokenType.STAR, multiply.operator().type());
    }
}
~~~

Ví dụ trên kiểm tra AST structure cụ thể. Test helper có thể giảm boilerplate nhưng không nên che điều kiện đang được xác nhận.

### Golden AST test

Với chương trình lớn, có thể lưu AstPrinter output làm golden file. Khi grammar thay đổi, diff thể hiện tree đã đổi ở đâu.

### Test diagnostic

Không chỉ kiểm tra diagnostics count. Kiểm tra error code và source span để bảo đảm message gắn đúng token.

## 29. Property-based test cho parser

Property-based testing có thể sinh AST hợp lệ, format thành source rồi parse lại.

Property:

~~~text
canonicalize(parse(format(ast))) == canonicalize(ast)
~~~

### AST generator

Sinh literal, name, unary, binary, call và member node với depth giới hạn.

### Source formatter

Formatter phải thêm ngoặc cần thiết theo precedence để source parse lại cùng tree.

### Shrinking

Nếu round-trip fail, shrinker giảm AST subtree, số argument, nesting và literal để tạo phản ví dụ nhỏ.

### Whitespace metamorphic property

Thêm whitespace/comment hợp lệ không được đổi canonical AST.

### Invalid source property

Sinh source arbitrary trong giới hạn và xác nhận parser không crash, diagnostic span hợp lệ, parse luôn kết thúc.

### Differential parser

Nếu có parser reference hoặc grammar-generated parser thứ hai, so sánh canonical AST trên corpus supported.

## 30. Fuzzing và resource limits

Parser là boundary xử lý input, vì vậy cần kiểm tra input xấu.

### Deep nesting

Sinh hàng nghìn dấu ngoặc hoặc block lồng sâu để tìm StackOverflowError. Đặt max nesting depth hoặc dùng iterative parser khi cần.

### Long token

Sinh identifier/string cực dài để kiểm tra memory/time. Giới hạn source size và literal size.

### Backtracking

Nếu parser có backtracking, tạo input gây nhiều nhánh thử. Đặt parse budget hoặc dùng grammar/algorithm có worst-case phù hợp.

### Invalid encoding

Nếu API nhận bytes, kiểm tra UTF-8 malformed input và decoding policy.

### Cancellation

Parser chạy trong server/editor có thể cần cancellation token. Kiểm tra cancellation không để shared state nửa cập nhật.

### Fuzz corpus

Lưu mọi crash/hang/minimized counterexample làm regression input.

## 31. Tối ưu sau khi có correctness baseline

Không nên tối ưu parser trước khi có grammar, AST và test đáng tin cậy.

### Measure phases

Đo lexing, parsing, AST construction riêng. Đừng gọi toàn bộ compiler pipeline là parser time.

### Avoid substring allocation

Token giữ source offsets thay vì copy lexeme cho mọi token nếu source buffer được giữ đủ lâu.

### Compact AST

Dùng immutable record/node, tránh metadata lặp không cần thiết. Nếu memory là bottleneck, xem flat node array/arena.

### Avoid repeated list copy

Dùng mutable builder nội bộ rồi freeze thành immutable list.

### Parser reuse

Grammar metadata có thể chia sẻ; cursor/token buffer/diagnostic list phải riêng cho invocation nếu mutable.

### Cache

Cache AST theo source hash, language version và parser version. Cache phải có memory bound và invalidation.

### Parallel file parsing

Dùng bounded executor cho file độc lập. Resolution/semantic phase cần dependency graph và deterministic aggregation.

### Profile before micro-optimization

Dùng CPU/allocation profiler để tìm hotspot. Không thêm object pool hoặc custom data structure chỉ dựa trên suy đoán.

## 32. Mở rộng parser sau phiên bản đầu tiên

Khi core ổn định, có thể thêm:

### Type syntax

~~~text
let amount: Decimal = 12.50;
let tags: List<String> = ["new", "priority"];
~~~

Cần thêm type AST và parser production.

### If/else

~~~text
if customer.isBlocked {
    print "rejected";
} else {
    approve(customer.id);
}
~~~

Cần statement node và grammar branch.

### Function declaration

~~~text
function isAdult(customer: Customer): Boolean {
    return customer.age >= 18;
}
~~~

Cần parameter list, return type và scope.

### Import/module

~~~text
import commerce.customer as customer;
~~~

Cần module resolver và dependency graph.

### Error-tolerant editor mode

Giữ partial AST và error node để IDE có thể hiển thị outline/completion khi source chưa hoàn chỉnh.

### Incremental parsing

Sau khi có source span và stable node identity, có thể tái sử dụng subtree không bị ảnh hưởng bởi edit.

### Language version

Khi grammar tiến hóa, source/project nên pin language version để parse reproducible.

## 33. Quy trình thực hiện project

Một lộ trình thực tế:

1. **Chốt language scope:** chọn declaration, statement, literal, operator và function call cần hỗ trợ.
2. **Viết grammar:** xác định production, precedence và associativity.
3. **Thiết kế source/token model:** offset, line/column, token type và literal.
4. **Viết lexer:** punctuation, operator, keyword, identifier, number, string, comment và diagnostics.
5. **Viết AST:** expression, statement, declaration, program và source span.
6. **Viết parser skeleton:** cursor helpers, EOF handling và parse loop.
7. **Parse declaration/statement:** variable, rule, block, print và expression statement.
8. **Parse expression:** precedence ladder hoặc Pratt parser.
9. **Thêm error recovery:** synchronization và diagnostic model.
10. **Viết AstPrinter:** kiểm tra tree và precedence.
11. **Viết tests:** lexer, parser, AST span, error cases và golden examples.
12. **Thêm property tests:** round-trip, whitespace invariance và no-crash fuzz property.
13. **Profile:** đo phase và allocation trên corpus đại diện.
14. **Mở rộng:** type, function, import, semantic analysis và editor support.

## 34. Definition of done cho parser/AST project

Dự án có thể xem là đạt phiên bản đầu khi:

- Lexer nhận diện đầy đủ token trong grammar đã công bố.
- Keyword/identifier boundary hoạt động đúng.
- Literal được decode và validate theo policy.
- Token và AST node có source span.
- Parser xử lý toàn bộ declaration/statement/expression trong scope.
- Operator precedence và associativity được kiểm thử.
- Parser tạo AST ổn định cho source giống nhau.
- Syntax error trả diagnostic có code và span.
- Error recovery không lặp vô hạn.
- AstPrinter hiển thị cấu trúc dễ kiểm tra.
- Unit tests bao phủ valid/invalid input.
- Property test kiểm tra ít nhất một round-trip/invariant.
- Input size/nesting có giới hạn phù hợp.
- Main có thể parse file ví dụ và in AST/diagnostics.

## 35. Những lỗi thường gặp khi xây parser và AST

**Viết parser trước khi có grammar.** Method phát triển theo nhu cầu tức thời và precedence dễ không nhất quán. Viết grammar và test case trước.

**Gộp lexer vào parser.** Khó kiểm tra tokenization, source position và comment. Tách phase để có contract rõ.

**Không lưu source span.** Diagnostic không chỉ đúng vị trí và refactoring khó. Gắn span cho token và AST node từ đầu.

**Dùng String cho mọi literal.** Mất type/precision và conversion bị lặp. Lưu typed literal value theo semantics.

**Parse expression một cách tùy tiện.** Precedence/associativity sai. Dùng precedence ladder hoặc Pratt parser.

**AST phản chiếu mọi token.** Compiler phải xử lý quá nhiều punctuation/trivia. Phân biệt CST và AST.

**AST bỏ quá nhiều thông tin.** Formatter/refactoring không thể giữ comment hoặc source form. Xác định nhu cầu tooling trước khi bỏ trivia.

**Throw exception cho mọi lỗi người dùng.** Không thu thập được nhiều diagnostics và IDE experience kém. Trả ParseResult với diagnostic.

**Error recovery không tiến triển.** Parser lặp vô hạn ở token sai. Đảm bảo cursor advance hoặc loop kết thúc.

**Resolver chạy bên trong parser.** Parse phụ thuộc symbol table/I/O và khó tái sử dụng. Tách name resolution và semantic analysis.

**Dùng parser mutable chung giữa thread.** Cursor và diagnostics bị race. Tạo parser state riêng mỗi invocation.

**Test chỉ kiểm tra parser không crash.** AST có thể sai mà test vẫn pass. Kiểm tra tree structure và semantic relations.

**Không giới hạn nesting/input.** Có thể StackOverflow hoặc resource exhaustion. Đặt budget và test adversarial input.

## 36. Checklist review parser và AST

Khi hoàn thành project, có thể xác nhận:

- Grammar có tài liệu và không có ambiguity chưa xử lý không?
- Token set bao phủ terminal trong grammar không?
- Lexer có longest-match, keyword boundary và Unicode policy không?
- Source span có đúng ở newline, comment và EOF không?
- AST có phân biệt expression, statement và declaration không?
- AST node có bất biến và có source span không?
- Parser có EOF-safe helper và cursor progress guarantee không?
- Precedence/associativity có test rõ không?
- Call/member access có parse chain đúng không?
- Error recovery có synchronization token phù hợp không?
- Diagnostic có code, severity, message và span không?
- AstPrinter giúp kiểm tra cấu trúc tree không?
- Unit test có valid, invalid, boundary và nested input không?
- Property test có round-trip hoặc invariant không?
- Fuzz/resource test có deep nesting và malformed input không?
- Parser state có thread-safety contract rõ không?
- Source/AST/cache lifetime có được quản lý không?

## 37. Kết quả cần có sau khi xây parser và AST

Một front end DSL hoàn chỉnh ở mức dự án đầu tiên thường có:

- **Grammar specification:** declaration, statement, expression, precedence và associativity.
- **Source model:** source identity, offsets, line/column và source span.
- **Lexer:** token types, keyword table, literal scanner, comment handling và lexical diagnostics.
- **AST model:** program, declaration, statement, expression và immutable node hierarchy.
- **Parser:** recursive descent cho declaration/statement và precedence parser/Pratt cho expression.
- **Error handling:** parse result, diagnostic codes, synchronization và partial AST policy.
- **AST tooling:** printer/visitor để debug và hỗ trợ phase sau.
- **Test suite:** lexer tests, parser tests, AST structure, source span và error recovery.
- **Property/fuzz suite:** round-trip, metamorphic whitespace, malformed input và resource limits.
- **Extension path:** name resolution, type checking, formatter, interpreter, compiler và IDE integration.

Xây parser và AST là bước đầu biến một tập quy tắc DSL thành một language có thể xử lý có hệ thống. Bắt đầu bằng grammar nhỏ, token model rõ và source span nhất quán; sau đó tách lexer, parser và AST để mỗi phase có thể kiểm thử độc lập. Recursive descent phù hợp cho declaration/statement có cấu trúc rõ, còn Pratt parser hoặc precedence ladder xử lý expression. AST bất biến giúp các phase sau như name resolution, type checking, formatter và interpreter làm việc an toàn. Khi có diagnostic tốt, error recovery, unit/property tests và resource limits, parser không chỉ xử lý được chương trình hợp lệ mà còn hỗ trợ developer hiểu và sửa source sai một cách đáng tin cậy.

