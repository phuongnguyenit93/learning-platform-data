# Thông tin vị trí nguồn

Trong một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), công cụ thường chuyển văn bản nguồn thành token, cây cú pháp và các biểu diễn trung gian để phân tích hoặc thực thi. Trong suốt quá trình đó, công cụ cần biết mỗi token hay nút cú pháp bắt nguồn từ đoạn nào trong tệp. Thông tin này được gọi là **thông tin vị trí nguồn** (*source location information* hoặc *source span*).

Thông tin vị trí nguồn giúp công cụ chỉ đúng nơi xảy ra lỗi, gắn cảnh báo với đoạn mã liên quan, hỗ trợ điều hướng trong IDE, tạo thông báo giải thích dễ hiểu và truy ngược kết quả sau các bước biến đổi. Nếu vị trí nguồn bị mất hoặc không nhất quán, người dùng có thể chỉ nhận được lỗi chung chung ở cuối quá trình biên dịch hoặc thực thi mà không biết cần sửa dòng nào.

Thông tin vị trí không phải là ngữ nghĩa của chương trình. Nó là metadata gắn với văn bản và cấu trúc cú pháp, nhưng có vai trò quan trọng trong toàn bộ trải nghiệm sử dụng DSL.

## 1. Vị trí nguồn là gì?

Vị trí nguồn mô tả nơi một thành phần của chương trình xuất hiện trong văn bản đầu vào. Một vị trí đơn lẻ có thể gồm tệp, dòng, cột hoặc offset. Một khoảng nguồn (*source span* hoặc *source range*) mô tả đoạn bắt đầu và kết thúc.

Ví dụ DSL:

```text
service "catalog" {
    replicas = 3
    port = 8080
}
```

Nếu giá trị `replicas` không hợp lệ, công cụ nên báo lỗi ngay tại `3`, chẳng hạn dòng 2, cột 16. Để làm được điều đó, lexer cần lưu vị trí của token `3`, parser cần gắn vị trí vào node literal, và semantic analyzer cần giữ lại vị trí khi kiểm tra quy tắc miền.

Một khoảng nguồn thường có dạng:

```text
SourceSpan {
    sourceFile: "config.dsl",
    start: 31,
    end: 32
}
```

Trong ví dụ, `start` và `end` là offset minh họa. Quy ước chính xác về đơn vị và việc có tính ký tự kết thúc hay không phải được xác định thống nhất trong công cụ.

## 2. Các thành phần của vị trí nguồn

### 2.1. Định danh tệp nguồn

Một chương trình DSL có thể gồm nhiều tệp. Vì vậy, chỉ lưu dòng và cột là chưa đủ: dòng 5, cột 10 có thể xuất hiện trong hàng chục tệp khác nhau.

Thông tin nguồn nên có định danh ổn định cho tệp, ví dụ:

- Đường dẫn tương đối trong dự án.
- URI của tài liệu hoặc tệp.
- Mã nguồn nội bộ do trình biên dịch cấp.
- Tên tài nguyên nếu DSL được nạp từ database hoặc hệ thống quản lý cấu hình.

Ví dụ cấu trúc:

```java
record SourceFileId(String uri) {}

record SourcePosition(
    SourceFileId file,
    int line,
    int column,
    int offset
) {}
```

Đây chỉ là cấu trúc minh họa. Một hệ thống có thể lưu đối tượng `SourceFile` riêng để quản lý nội dung, phiên bản, đường dẫn và bảng ánh xạ offset sang dòng/cột.

### 2.2. Dòng và cột

**Dòng** cho biết vị trí theo chiều dọc trong văn bản. **Cột** cho biết vị trí theo chiều ngang trong dòng đó.

Đặc tả cần xác định cách đánh số:

- Dòng bắt đầu từ 0 hay 1.
- Cột bắt đầu từ 0 hay 1.
- Cột được tính theo byte, code point Unicode, đơn vị UTF-16 hay cột hiển thị.
- Tab được tính là một ký tự hay mở rộng đến một cột tab kế tiếp.

Trong thông báo lỗi cho người dùng, dòng và cột thường được hiển thị bắt đầu từ 1 vì cách đánh số này quen thuộc. Trong cấu trúc nội bộ và API editor, chỉ số bắt đầu từ 0 cũng thường được sử dụng. Điều quan trọng là không trộn lẫn các quy ước.

### 2.3. Offset

Offset là vị trí tính từ đầu nội dung nguồn. Nó thuận tiện cho lexer vì lexer thường đọc chuỗi từ trái sang phải và có thể lưu chỉ số bắt đầu/kết thúc của mỗi token.

Ví dụ:

```text
name = "Ada"
```

Nếu offset tính theo đơn vị ký tự của chuỗi, token `Ada` nằm trong một khoảng offset cụ thể. Công cụ có thể dùng offset để lấy lại đoạn văn bản, tô sáng vùng lỗi hoặc thay thế đoạn mã.

Offset chỉ có ý nghĩa khi đơn vị đo được xác định. Một offset theo byte UTF-8 không giống offset theo code point Unicode hoặc UTF-16 code unit.

### 2.4. Khoảng nguồn bắt đầu và kết thúc

Thay vì chỉ lưu một vị trí, token và node thường lưu cả điểm bắt đầu lẫn điểm kết thúc. Một quy ước phổ biến là khoảng nửa mở (*half-open range*):

\[
[start, end)
\]

`start` được tính vào đoạn, còn `end` là vị trí ngay sau ký tự cuối cùng. Ví dụ, chuỗi `cat` ở offset 4 đến 7 có khoảng `[4, 7)` và độ dài `3`.

Ưu điểm của khoảng nửa mở:

- Độ dài được tính trực tiếp bằng `end - start`.
- Hai đoạn liền nhau có thể có chung ranh giới, ví dụ `[0, 3)` và `[3, 5)`.
- Đoạn rỗng có thể biểu diễn bằng `start == end`.
- Dễ dùng với thao tác cắt chuỗi trong nhiều ngôn ngữ lập trình.

Một số API hoặc định dạng khác dùng điểm cuối bao gồm (*inclusive end*). Không có lựa chọn nào tự động đúng trong mọi hệ thống; cần chọn một quy ước và ghi rõ trong kiểu dữ liệu cùng tài liệu API.

## 3. Vì sao cây cú pháp cần thông tin vị trí nguồn?

AST (*Abstract Syntax Tree* – cây cú pháp trừu tượng) lưu cấu trúc có ý nghĩa của chương trình. Mỗi node có thể đại diện cho literal, biểu thức, khai báo, câu lệnh hoặc toàn bộ chương trình.

Nếu AST không lưu nguồn gốc, các bước sau chỉ biết cấu trúc nội bộ mà không biết cấu trúc đó đến từ đâu trong tệp. Điều này gây khó khăn cho:

- Báo lỗi cú pháp và ngữ nghĩa tại vị trí chính xác.
- Gắn cảnh báo hoặc gợi ý sửa với đoạn mã.
- Điều hướng từ node trong AST đến tệp nguồn.
- Tô sáng biểu thức hoặc khai báo trong IDE.
- Truy vết lỗi phát sinh sau tối ưu hóa hoặc sinh mã.
- Tạo thông tin nguồn cho debugger và stack trace.

Ví dụ, AST của biểu thức:

```text
price * quantity + shipping
```

có thể được biểu diễn như sau:

```text
Add [span: 0..29]
├── Multiply [span: 0..16]
│   ├── Name("price") [span: 0..5]
│   └── Name("quantity") [span: 8..16]
└── Name("shipping") [span: 19..27]
```

Các offset trong sơ đồ chỉ minh họa. AST giữ được cả cấu trúc phép tính và vùng nguồn tương ứng của từng node.

## 4. Gắn vị trí nguồn từ lexer đến AST

Thông tin vị trí thường được thu thập ngay từ lexer rồi truyền qua parser đến AST.

### 4.1. Lexer ghi nhận vị trí token

Lexer đọc từng ký tự và theo dõi offset, dòng, cột. Khi nhận diện xong một token, nó tạo token cùng khoảng nguồn.

Ví dụ cấu trúc Java:

```java
record SourceSpan(
    SourceFileId file,
    int startOffset,
    int endOffset
) {}

record Token(
    TokenType type,
    String lexeme,
    Object literalValue,
    SourceSpan span
) {}
```

Lexer có thể dùng `startOffset` trước khi bắt đầu nhận diện token, sau đó cập nhật con trỏ cho đến khi token kết thúc và tạo span `[startOffset, currentOffset)`.

### 4.2. Parser gắn span cho node

Parser sử dụng token để tạo AST. Node có thể lấy span từ token đầu tiên đến token cuối cùng tạo nên node đó.

Ví dụ:

```java
record BinaryExpression(
    Expression left,
    Token operator,
    Expression right,
    SourceSpan span
) implements Expression {}
```

Parser tạo `BinaryExpression` sau khi phân tích được vế trái, toán tử và vế phải. Span của node có thể bắt đầu tại `left.span.startOffset` và kết thúc tại `right.span.endOffset`.

Giữ token toán tử riêng cũng hữu ích: nếu cần báo lỗi về chính phép toán, công cụ có thể trỏ đến ký hiệu `+` thay vì tô sáng toàn bộ biểu thức.

### 4.3. Node cha và node con

Thông thường, span của node cha bao phủ các node con và những token cấu thành nó. Tuy nhiên, không phải lúc nào span cha cũng chỉ là hợp của span con: cú pháp có thể chứa dấu ngoặc, từ khóa hoặc dấu phân cách không được lưu thành node riêng trong AST.

Ví dụ:

```text
if (age >= 18) { approve() }
```

Node `IfStatement` có thể bao phủ từ `if` đến dấu `}` cuối cùng. Node biểu thức điều kiện chỉ bao phủ `age >= 18`. Node `approve()` chỉ bao phủ lời gọi hàm. Việc chọn span nào nên được xác định nhất quán để thông báo lỗi và công cụ editor có thể sử dụng.

## 5. Vị trí nguồn trong CST và AST

**CST** (*Concrete Syntax Tree* – cây cú pháp cụ thể) thường giữ lại nhiều chi tiết của cú pháp gốc như dấu ngoặc, dấu phẩy, từ khóa, comment hoặc khoảng trắng tùy parser. **AST** lược bỏ các chi tiết trình bày không cần thiết và tập trung vào cấu trúc có ý nghĩa.

| Đặc điểm | CST | AST |
|---|---|---|
| Chi tiết cú pháp | Thường giữ nhiều chi tiết | Thường lược bỏ dấu câu và chi tiết không cần thiết |
| Khoảng trắng/comment | Có thể giữ dưới dạng trivia hoặc node | Thường không giữ trực tiếp, trừ khi cần cho tooling |
| Vị trí nguồn | Có thể gắn cho terminal và node cú pháp | Có thể gắn span cho node biểu đạt ý nghĩa |
| Mục đích | Format lại, refactoring chính xác, phân tích cú pháp cụ thể | Semantic analysis, tối ưu và thực thi |

Thông tin vị trí nguồn hữu ích cho cả hai. CST giúp công cụ biết chính xác dấu ngoặc hoặc comment nằm ở đâu. AST giúp semantic analyzer biết node nghiệp vụ tương ứng với đoạn mã nào.

Nếu DSL cần formatter giữ nguyên comment và cách trình bày, có thể cần CST hoặc một mô hình token/trivia đi kèm AST. Nếu chỉ cần thực thi và báo lỗi cơ bản, AST có span thường đã đủ.

## 6. Các hệ tọa độ văn bản và vấn đề Unicode

Một trong những nguồn lỗi phổ biến là không thống nhất đơn vị của offset và cột. Một ký tự hiển thị trên màn hình có thể được biểu diễn bằng nhiều byte hoặc nhiều đơn vị mã.

### 6.1. Byte, code point và UTF-16 code unit

Với văn bản Unicode, cần phân biệt:

- **Byte:** đơn vị lưu trữ. Trong UTF-8, một ký tự có thể chiếm từ 1 đến 4 byte.
- **Unicode code point:** mã điểm Unicode của ký tự trừu tượng.
- **UTF-16 code unit:** đơn vị 16 bit; một số code point ngoài BMP cần hai code unit (surrogate pair).
- **Cột hiển thị:** vị trí nhìn thấy trên màn hình; có thể bị ảnh hưởng bởi tab, ký tự kết hợp và độ rộng glyph.

Ví dụ, ký tự `😀` được mã hóa bằng 4 byte trong UTF-8, một Unicode code point và hai UTF-16 code unit. Vì vậy, offset byte, offset code point và offset UTF-16 tại các vị trí sau ký tự này sẽ khác nhau.

### 6.2. Chọn đơn vị nội bộ

Một công cụ DSL nên chọn một đơn vị chuẩn nội bộ và ghi rõ trong API. Ví dụ:

- Nếu nguồn được lưu dưới dạng UTF-8 byte array, có thể dùng byte offset để cắt dữ liệu gốc.
- Nếu lexer xử lý chuỗi Java, offset theo UTF-16 code unit thường phù hợp với chỉ số chuỗi Java.
- Nếu cần làm việc theo Unicode code point, có thể lưu code point offset hoặc chuyển đổi khi cần.

Không nên dùng một trường `column` mà không ghi rõ nó đếm theo đơn vị nào.

### 6.3. Cột logic và cột hiển thị

Tab có thể làm con trỏ hiển thị nhảy đến cột tab kế tiếp. Một ký tự Unicode kết hợp có thể hiển thị cùng ký tự trước đó; emoji hoặc ký tự Đông Á có thể chiếm hai ô hiển thị tùy môi trường.

Vì vậy, parser thường nên lưu offset và vị trí logic, còn editor hoặc giao diện hiển thị chuyển đổi sang cột màn hình theo quy tắc trình bày của nó. Nếu công cụ tự tính cột hiển thị, cần dùng cùng quy tắc tab width và độ rộng ký tự với editor.

## 7. Dòng mới và vị trí nguồn

Tệp có thể sử dụng LF (`\n`), CRLF (`\r\n`) hoặc định dạng dòng cũ dùng CR (`\r`). Nếu lexer đếm CRLF thành hai dòng, thông báo lỗi sẽ bị lệch.

Một chiến lược phổ biến là xem CRLF như một dấu kết thúc dòng logic duy nhất. Lexer cần cập nhật dòng, cột và offset theo đúng cách biểu diễn nguồn đã chọn.

Ví dụ:

```text
service "catalog" {\r\n
    replicas = 3\r\n
}\r\n
```

Trong đoạn minh họa trên, mỗi cặp CRLF phải làm tăng số dòng logic một lần. Offset vẫn phải phản ánh đúng số đơn vị trong nội dung gốc nếu công cụ dùng offset để cắt hoặc tô sáng văn bản.

Nếu formatter chuẩn hóa CRLF thành LF, các span của AST cũ không còn khớp với văn bản mới. Khi đó cần parse lại hoặc tạo ánh xạ vị trí giữa phiên bản trước và sau định dạng.

## 8. Truyền vị trí qua các bước xử lý

Thông tin vị trí không chỉ dùng trong lexer và parser. Nó cần được bảo toàn qua các bước semantic analysis, lowering, tối ưu hóa và sinh mã ở mức phù hợp.

Một pipeline tổng quát:

```text
Source text
   |
   v
Lexer -- token + source span
   |
   v
Parser -- AST node + source span
   |
   v
Semantic analysis -- resolved symbol/type + source span
   |
   v
IR / lowering -- node + origin metadata
   |
   v
Optimizer -- transformed node + origin mapping
   |
   v
Backend / runtime -- diagnostic or source map
```

Mỗi bước có thể tạo node mới hoặc gộp nhiều node cũ. Nếu không xác định cách truyền nguồn gốc, thông tin vị trí có thể bị mất khi chương trình rời AST.

### 8.1. Semantic analysis giữ span của biểu thức

Khi kiểm tra tên hoặc kiểu, analyzer nên gắn lỗi với node có liên quan. Ví dụ, nếu trường `salary` không tồn tại, diagnostic có thể trỏ vào token định danh `salary`. Nếu toàn bộ điều kiện không tương thích, có thể trỏ vào biểu thức so sánh.

### 8.2. Lowering tạo node mới

Một lệnh DSL cấp cao có thể được chuyển thành nhiều node IR. Ví dụ:

```text
repeat 3 times { send("hello") }
```

có thể được hạ thành vòng lặp và lời gọi hàm. Các node mới không xuất hiện nguyên văn trong nguồn. Chúng có thể mang span của câu lệnh `repeat` đã tạo ra chúng, hoặc một quan hệ `origin` trỏ đến node nguồn.

### 8.3. Tối ưu hóa gộp hoặc loại bỏ node

Optimizer có thể gộp hai biểu thức, loại bỏ phép tính hằng hoặc sắp xếp lại các thao tác nếu ngữ nghĩa cho phép. Sau biến đổi:

- Node mới có thể tương ứng với nhiều đoạn nguồn.
- Node cũ có thể bị loại bỏ.
- Một node được giữ lại có thể chỉ đại diện cho một phần của biểu thức ban đầu.

Vì vậy, một trường span đơn giản đôi khi không đủ. Có thể cần metadata nguồn gốc (*origin metadata*) hoặc danh sách các span liên quan.

## 9. Source mapping và node được sinh tự động

Trong một số DSL, chương trình được mở rộng macro, sinh mã hoặc chuyển thành ngôn ngữ khác. Khi đó, mã thực thi có thể không giống văn bản nguồn mà người dùng viết.

**Source map** là cơ chế ánh xạ vị trí trong đầu ra hoặc mã đã biến đổi trở lại vị trí trong nguồn ban đầu.

Ví dụ, một DSL template có thể sinh JavaScript:

```text
template "welcome" {
    print("Hello, " + user.name)
}
```

Mã JavaScript sinh ra có thể chứa các hàm hỗ trợ và đoạn chuyển đổi không xuất hiện trực tiếp trong DSL. Khi runtime báo lỗi ở một dòng JavaScript, source map giúp công cụ chỉ về câu lệnh `print` hoặc biểu thức `user.name` trong tệp template.

### 9.1. Node tổng hợp (synthetic node)

Node tổng hợp là node được tạo bởi compiler hoặc công cụ biến đổi, không tương ứng với một đoạn văn bản trực tiếp. Ví dụ:

- Node kiểm tra null được chèn tự động.
- Node gọi hàm hỗ trợ được sinh khi mở rộng cú pháp.
- Node chuyển kiểu được thêm trong lowering.
- Node biểu diễn giá trị mặc định không được người dùng viết rõ.

Không nên gán một vị trí nguồn giả như thể người dùng đã viết node đó. Thay vào đó, có thể:

- Đánh dấu node là synthetic.
- Lưu node nguồn hoặc span đã khiến node được tạo.
- Lưu nhiều origin nếu node tổng hợp xuất phát từ nhiều biểu thức.
- Cung cấp cách báo lỗi phù hợp, có thể chỉ đến câu lệnh gốc hoặc thông báo đây là lỗi phát sinh trong mã được sinh.

### 9.2. Macro và mở rộng cú pháp

Macro có thể mở rộng một cấu trúc ngắn thành nhiều node. Các node được mở rộng nên giữ thông tin về vị trí lời gọi macro và, nếu có, vị trí định nghĩa macro.

Khi lỗi phát sinh trong phần mở rộng, IDE có thể hiển thị cả hai vị trí: nơi người dùng gọi macro và nơi macro được định nghĩa. Điều này giúp xác định lỗi nằm ở cách sử dụng hay ở chính phần định nghĩa.

## 10. Thiết kế kiểu dữ liệu cho source span

Một mô hình đơn giản có thể gồm:

```java
record SourceFileId(String uri) {}

record SourceSpan(
    SourceFileId file,
    int startOffset,
    int endOffset
) {
    SourceSpan {
        if (startOffset < 0 || endOffset < startOffset) {
            throw new IllegalArgumentException("Invalid source span");
        }
    }
}

record SourceOrigin(
    SourceSpan primary,
    List<SourceSpan> related,
    boolean synthetic
) {}
```

Trong mô hình này:

- `file` xác định tệp nguồn.
- `startOffset` và `endOffset` xác định khoảng nửa mở.
- `primary` là vị trí chính để hiển thị.
- `related` lưu các đoạn nguồn có liên quan khi node được tạo từ nhiều nơi.
- `synthetic` cho biết node được tạo tự động.

Đây chỉ là một thiết kế minh họa. Một hệ thống nhỏ có thể chỉ cần `SourceSpan`; hệ thống hỗ trợ macro, template hoặc code generation có thể cần source map phức tạp hơn.

### 10.1. Bảng ánh xạ offset sang dòng/cột

Nếu thường xuyên cần chuyển offset sang dòng/cột, có thể xây dựng bảng lưu offset bắt đầu của từng dòng:

```text
lineStarts = [0, 18, 42, 57, ...]
```

Với một offset, tìm dòng có `lineStart` lớn nhất nhưng không vượt quá offset. Cột được tính từ `offset - lineStart` theo đơn vị đã chọn.

Nếu cần chuyển đổi theo code point, UTF-16 hoặc cột hiển thị, có thể lưu thêm bảng ánh xạ hoặc tính toán trong lớp quản lý source file. Cách này tránh việc mỗi node phải lưu lặp lại cả dòng và cột nếu offset đã đủ để khôi phục.

### 10.2. Lưu span hay lưu vị trí dòng/cột?

Hai cách có ưu và nhược điểm:

| Cách lưu | Ưu điểm | Hạn chế |
|---|---|---|
| Offset bắt đầu/kết thúc | Nhỏ gọn, dễ cắt văn bản và tạo range | Cần source file để đổi sang dòng/cột |
| Dòng/cột bắt đầu/kết thúc | Dễ hiển thị trong thông báo lỗi | Khó thao tác chính xác với chuỗi và chỉnh sửa văn bản |
| Cả offset và dòng/cột | Truy cập nhanh ở nhiều ngữ cảnh | Tốn bộ nhớ và phải giữ đồng bộ |

Một lựa chọn phổ biến là lưu offset trong token/node và dùng `SourceFile` để chuyển đổi khi cần hiển thị. Với IDE hoặc hệ thống cần nhiều thao tác vị trí, cache dòng/cột có thể cải thiện hiệu năng.

## 11. Thông tin vị trí trong diagnostic

Diagnostic là thông báo về lỗi, cảnh báo hoặc thông tin mà công cụ phát hiện trong chương trình DSL. Một diagnostic hữu ích thường có:

- Mã định danh hoặc loại thông báo.
- Nội dung giải thích.
- Mức độ: lỗi, cảnh báo hoặc thông tin.
- Span chính cần tô sáng.
- Các span liên quan nếu cần giải thích nguyên nhân.
- Gợi ý sửa hoặc hành động khắc phục nếu có thể.

Ví dụ:

```text
config.dsl:2:16: error DSL102: replicas must be a positive integer
    replicas = -3
               ^^
```

Span có thể bao phủ `-3`, còn nội dung thông báo giải thích quy tắc miền bị vi phạm.

### 11.1. Span chính và span liên quan

Một lỗi có thể liên quan đến nhiều vị trí. Ví dụ, tên biến được khai báo hai lần:

```text
let region = "asia"
let region = "europe"
```

Diagnostic có thể đặt span chính ở khai báo thứ hai và thêm thông tin liên quan trỏ đến khai báo đầu tiên. Người dùng thấy được cả nơi phát sinh xung đột và nơi tên đã được khai báo.

### 11.2. Fix-it và vùng thay thế

Một số công cụ có thể đề xuất sửa tự động. Để làm được điều đó, diagnostic cần chỉ ra vùng nguồn sẽ được thay thế và văn bản thay thế.

Ví dụ, nếu DSL yêu cầu dấu `;` mà người dùng bỏ quên, công cụ có thể đề xuất chèn dấu tại vị trí rỗng sau câu lệnh. Một span rỗng `[p, p)` có thể biểu diễn vị trí chèn.

Fix-it cần thận trọng: chỉ đề xuất khi công cụ xác định chắc chắn cách sửa, và phải tránh làm thay đổi ý nghĩa ngoài ý muốn.

## 12. Tích hợp với IDE và Language Server Protocol

IDE sử dụng vị trí nguồn để hiển thị lỗi, tô sáng token, điều hướng, gợi ý sửa và hỗ trợ refactoring.

Một DSL có Language Server có thể gửi diagnostic gồm URI tệp và range. Editor dùng range đó để gạch chân đoạn mã hoặc hiển thị thông báo khi người dùng di chuột.

Các tính năng thường dựa vào source location:

- **Diagnostics:** gạch chân lỗi và cảnh báo.
- **Go to definition:** từ một tham chiếu đi đến nơi khai báo.
- **Find references:** tìm các vị trí sử dụng một định danh.
- **Hover:** hiển thị kiểu hoặc tài liệu tại vị trí con trỏ.
- **Rename:** thay tên ở các tham chiếu phù hợp.
- **Code action:** đề xuất sửa lỗi hoặc chuyển đổi cú pháp.
- **Semantic highlighting:** tô màu theo vai trò ngữ nghĩa của token.

Để hỗ trợ những tính năng này, AST hoặc symbol table thường lưu tham chiếu đến span của khai báo và từng lần sử dụng. Khi tài liệu được chỉnh sửa, các span phải được cập nhật hoặc tính lại để không trỏ đến văn bản cũ.

## 13. Vị trí nguồn trong môi trường nhiều tệp

DSL lớn có thể hỗ trợ import, include, module hoặc tham chiếu đến tệp khác.

Ví dụ:

```text
import "network.dsl"

service "catalog" {
    network = network.default
}
```

Nếu lỗi xảy ra trong `network.dsl`, diagnostic cần chỉ đúng tệp đó. Nếu lỗi là tham chiếu sai tại `config.dsl`, span chính nên nằm ở biểu thức `network.default`, có thể kèm thông tin về khai báo hoặc module được tham chiếu.

Một hệ thống nhiều tệp nên:

- Dùng định danh nguồn riêng cho mỗi tệp.
- Quản lý nội dung và phiên bản tài liệu.
- Giữ span cùng source file identity trong AST và symbol table.
- Hỗ trợ diagnostic liên tệp.
- Xử lý đường dẫn tương đối và URI nhất quán.
- Làm mới phân tích khi một tệp phụ thuộc thay đổi.

Không nên chỉ lưu đường dẫn tuyệt đối nếu dự án cần di chuyển giữa máy hoặc môi trường. Đường dẫn dự án tương đối hoặc URI chuẩn hóa thường dễ quản lý hơn.

## 14. Vị trí nguồn khi tài liệu thay đổi

Trong IDE, người dùng có thể sửa tệp trong khi parser và analyzer đang giữ AST cũ. Các offset của AST cũ có thể không còn khớp với nội dung mới.

Có một số cách xử lý:

- Phân tích lại toàn bộ tệp sau mỗi thay đổi.
- Phân tích tăng dần (*incremental parsing*) chỉ cập nhật vùng bị ảnh hưởng.
- Dùng phiên bản tài liệu để đảm bảo diagnostic được gửi cho đúng nội dung editor.
- Dùng edit map để chuyển span từ phiên bản cũ sang phiên bản mới nếu cần giữ node.

Với DSL nhỏ, parse lại toàn bộ tệp thường đơn giản và đủ nhanh. Với tệp lớn hoặc IDE cần phản hồi tức thời, incremental parsing có thể tiết kiệm thời gian nhưng đòi hỏi quản lý phụ thuộc và span phức tạp hơn.

### 14.1. Phiên bản nguồn

Mỗi lần tài liệu thay đổi, có thể tăng số phiên bản (*document version*). Diagnostic tạo từ phiên bản cũ không nên được áp dụng lên văn bản mới nếu offset đã thay đổi.

### 14.2. Edit map

Nếu một thao tác chèn hoặc xóa văn bản xảy ra trước span, offset của span phía sau có thể dịch chuyển. Edit map lưu các thay đổi để chuyển vị trí cũ sang vị trí mới. Tuy nhiên, nếu chỉnh sửa nằm ngay trong vùng của node hoặc làm thay đổi cấu trúc, node đó có thể cần được phân tích lại thay vì chỉ dịch offset.

## 15. Bảo toàn vị trí nguồn trong formatter và refactoring

Formatter thay đổi cách trình bày nhưng thường muốn giữ ngữ nghĩa. Refactoring thay đổi cấu trúc mã có chủ đích, ví dụ đổi tên hoặc trích xuất biểu thức.

Nếu công cụ dùng CST hoặc token/trivia, nó có thể giữ comment và khoảng trắng khi thay đổi một phần văn bản. Nếu chỉ dùng AST, công cụ có thể cần tái tạo cú pháp từ node và source span.

Một số nguyên tắc:

- Không dùng span cũ sau khi nội dung nguồn đã thay đổi mà không cập nhật hoặc parse lại.
- Khi tạo node mới trong refactoring, xác định span và nguồn gốc phù hợp.
- Khi xóa hoặc di chuyển node, cập nhật các tham chiếu nguồn và diagnostics.
- Giữ comment nếu công cụ cam kết bảo toàn comment.
- Kiểm tra rằng formatter không làm thay đổi AST hoặc ngữ nghĩa.

## 16. Ví dụ tổng hợp: phát hiện lỗi kiểu dữ liệu

Giả sử DSL khai báo dịch vụ:

```text
service "catalog" {
    replicas = "three"
    port = 8080
}
```

Quy tắc miền yêu cầu `replicas` là số nguyên dương. Luồng xử lý có thể diễn ra như sau:

1. Lexer tạo token `IDENTIFIER("replicas")`, `EQUALS` và `STRING("three")`, mỗi token có span.
2. Parser tạo node `Property` với tên thuộc tính và node literal chuỗi, giữ span của cả khai báo.
3. Semantic analyzer tra schema của `service` và biết `replicas` phải là integer.
4. Analyzer phát hiện literal có kiểu String, không tương thích với kiểu mong đợi.
5. Diagnostic dùng span của literal `"three"` để tô sáng đúng vùng, đồng thời có thể đưa span của tên `replicas` vào thông tin liên quan.

Thông báo có thể là:

```text
service.dsl:2:16: error: property "replicas" expects an integer, found a string
    replicas = "three"
               ^^^^^^^
```

Nếu AST không lưu vị trí nguồn, analyzer vẫn có thể biết kiểu sai nhưng không thể chỉ chính xác đoạn mã cần sửa. Điều này cho thấy source span phải được truyền xuyên suốt từ lexer đến các bước ngữ nghĩa.

## 17. Những sai lầm thường gặp

**Chỉ lưu dòng và cột mà không lưu tệp.** Trong dự án nhiều tệp, vị trí không xác định được nguồn nếu thiếu file identity.

**Không thống nhất đơn vị offset.** Byte, code point và UTF-16 code unit khác nhau; dùng lẫn chúng làm range bị lệch khi có Unicode.

**Nhầm cột logic với cột hiển thị.** Tab và ký tự có độ rộng khác nhau khiến vị trí màn hình không luôn bằng số ký tự đã đọc.

**Dùng quy ước điểm cuối không rõ ràng.** Inclusive end và exclusive end tạo ra range khác nhau; API phải ghi rõ.

**Mất span khi tạo AST hoặc IR mới.** Diagnostic ở bước sau không còn trỏ được về mã nguồn.

**Gán vị trí giả cho node tổng hợp.** Node do compiler sinh nên có metadata synthetic và quan hệ nguồn gốc thay vì giả vờ người dùng đã viết nó.

**Dùng diagnostic của phiên bản tài liệu cũ.** Sau khi editor thay đổi nội dung, offset cũ có thể tô sáng nhầm vị trí.

**Coi source map là thông tin trang trí.** Với macro, template hoặc code generation, source map có thể là cách duy nhất để truy ngược lỗi runtime về DSL ban đầu.

## 18. Ghi nhớ

- Thông tin vị trí nguồn mô tả tệp và đoạn văn bản tạo ra token hoặc node cú pháp.
- Source span thường gồm định danh tệp cùng offset bắt đầu và kết thúc; cần quy định đơn vị và quy ước đầu/cuối.
- Lexer gắn span cho token; parser truyền span vào AST; các bước ngữ nghĩa và biến đổi cần bảo toàn hoặc ánh xạ nguồn gốc.
- CST có thể giữ nhiều chi tiết cú pháp hơn AST, hữu ích cho formatter và refactoring.
- Unicode, tab và CRLF làm cho việc tính offset, dòng và cột cần có quy tắc thống nhất.
- Node tổng hợp và mã sinh tự động cần metadata nguồn gốc hoặc source map.
- Diagnostic, IDE, Language Server, formatter và debugger đều sử dụng thông tin vị trí nguồn.
- Khi tài liệu thay đổi, cần cập nhật hoặc tính lại span để tránh dùng vị trí cũ.

## 19. Câu hỏi tự kiểm tra

1. Thông tin vị trí nguồn là gì và vì sao AST cần lưu thông tin này?
2. Source span khác một vị trí đơn lẻ như thế nào?
3. Vì sao khoảng nửa mở `[start, end)` thường thuận tiện cho biểu diễn vùng nguồn?
4. Phân biệt byte offset, Unicode code point và UTF-16 code unit.
5. Lexer và parser đóng vai trò gì trong việc gắn span cho token và AST node?
6. Vì sao một node tổng hợp cần metadata nguồn gốc thay vì một vị trí giả?
7. Source map hỗ trợ truy vết lỗi như thế nào khi DSL sinh mã JavaScript hoặc mã đích khác?
8. Diagnostic có thể dùng nhiều span trong trường hợp nào?
9. Vì sao diagnostic được tạo từ phiên bản tài liệu cũ có thể trỏ sai sau khi người dùng chỉnh sửa tệp?
10. Hãy mô tả cách thông tin vị trí đi từ token `"three"` đến thông báo lỗi kiểu dữ liệu trong ví dụ dịch vụ.
