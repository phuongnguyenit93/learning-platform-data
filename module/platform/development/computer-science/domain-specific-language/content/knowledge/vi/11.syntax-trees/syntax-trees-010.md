# Truy vết về mã nguồn

## 1. Vai trò của truy vết nguồn trong cây cú pháp

Trong một công cụ ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL), parser chuyển văn bản nguồn thành cây cú pháp để các giai đoạn sau có thể kiểm tra, phân tích, chuyển đổi hoặc thực thi chương trình. Tuy nhiên, cây cú pháp chỉ hữu ích cho người dùng khi công cụ vẫn biết mỗi nút được tạo ra từ phần nào của văn bản ban đầu.

**Truy vết về mã nguồn (source tracking hoặc source mapping)** là việc duy trì mối liên hệ giữa cấu trúc nội bộ của chương trình và vị trí tương ứng trong tệp nguồn DSL. Nhờ liên kết này, công cụ có thể báo lỗi tại đúng biểu thức, hiển thị cảnh báo trong IDE, điều hướng từ một nút AST về văn bản, giải thích mã được sinh từ đâu và ánh xạ lỗi của runtime hoặc backend trở lại dòng DSL mà người dùng đã viết.

Ví dụ, xét DSL giả định:

~~~text
pipeline "daily-revenue" {
    source "orders.csv"
    filter status == "PAID"
    aggregate total = sum(amount)
}
~~~

Parser có thể tạo một nút FilterStatement và bên trong là nút biểu thức so sánh. Nếu quá trình kiểm tra ngữ nghĩa phát hiện trường status không tồn tại, công cụ cần biết vị trí của tham chiếu trường đó trong tệp để báo lỗi có ích. Nếu chỉ giữ AST mà không lưu vị trí nguồn, công cụ có thể biết biểu thức sai nhưng không thể chỉ chính xác chỗ người dùng cần sửa.

Truy vết nguồn cũng quan trọng khi DSL được chuyển thành ngôn ngữ khác. Một câu lệnh DSL có thể sinh ra nhiều câu lệnh SQL hoặc Java. Khi backend báo lỗi, người dùng cần biết lỗi bắt nguồn từ câu lệnh DSL nào, thay vì phải đọc mã sinh tự động.

## 2. Những thông tin nguồn cần theo dõi

Một công cụ DSL có thể cần giữ nhiều loại thông tin liên quan đến văn bản nguồn:

| Thông tin | Ý nghĩa | Công dụng |
|---|---|---|
| Source file / source ID | Tệp hoặc nguồn văn bản chứa đoạn mã | Phân biệt nhiều tệp, nội dung nhập từ chuỗi hoặc bộ nhớ |
| Start position | Vị trí bắt đầu của cấu trúc | Đặt con trỏ lỗi hoặc đánh dấu đoạn mã |
| End position | Vị trí kết thúc của cấu trúc | Xác định toàn bộ đoạn mã tương ứng |
| Line và column | Vị trí theo dòng và cột | Hiển thị thông báo lỗi trong editor |
| Character offset | Vị trí theo offset trong văn bản | Cắt đoạn nguồn, ánh xạ token và thao tác văn bản |
| Token range | Khoảng token tạo nên nút | Liên kết CST, AST và token stream |
| Origin / provenance | Nguồn gốc của nút sau biến đổi | Theo dõi macro, cú pháp đường tắt hoặc mã sinh |
| Related locations | Những vị trí liên quan | Chỉ ra khai báo gốc, nơi tham chiếu hoặc vị trí mở khối |

Không phải công cụ nào cũng cần lưu tất cả thông tin. Một interpreter nhỏ có thể chỉ cần tệp, dòng và cột. Một IDE hoặc compiler có refactoring, macro và nhiều giai đoạn sinh mã có thể cần offset, token range, nhiều vị trí nguồn và quan hệ nguồn gốc qua từng bước biến đổi.

## 3. Source span: đoạn nguồn của một nút

**Source span** là khoảng văn bản trong một nguồn được một token hoặc nút cú pháp đại diện. Thông thường, span có vị trí bắt đầu và kết thúc.

Ví dụ:

~~~text
filter status == "PAID"
       ^^^^^^^^^^^^^^^^
       source span của biểu thức điều kiện
~~~

Một biểu diễn khái quát:

~~~text
SourceSpan
    sourceId = "daily.pipe"
    startOffset = 31
    endOffset = 48
    startLine = 3
    startColumn = 12
    endLine = 3
    endColumn = 29
~~~

Quy ước khoảng đóng/mở phải được xác định. Một lựa chọn phổ biến là khoảng nửa mở `[start, end)`: vị trí bắt đầu được tính vào span, vị trí kết thúc nằm ngay sau ký tự cuối cùng. Với quy ước này, độ dài span là `end - start` và có thể dùng trực tiếp để cắt chuỗi theo đơn vị offset tương ứng.

### 3.1. Span của token và span của nút

Token thường có span nhỏ, tương ứng với một từ khóa, dấu ngoặc, định danh hoặc literal. Nút AST có thể bao phủ nhiều token.

Ví dụ:

~~~text
filter status == "PAID"
       ^^^^^^    ^^^^^^
       Field     StringLiteral

filter status == "PAID"
       ^^^^^^^^^^^^^^^^
       EqualExpression
~~~

Nút FieldReference có span của tên trường. Nút StringLiteral có span của chuỗi. Nút EqualExpression có thể có span bao phủ cả toán hạng trái, toán tử và toán hạng phải. Nút FilterStatement có thể có span rộng hơn, bao gồm cả từ khóa filter.

Span của nút cha thường bao phủ các nút con, nhưng không phải lúc nào cũng chỉ bằng hợp của chúng. Nó có thể bao gồm từ khóa, dấu phân cách hoặc phần cú pháp không được biểu diễn thành nút AST riêng.

### 3.2. Span chính xác và span bao phủ

Có thể phân biệt:

- **Span chính xác (exact span):** đoạn văn bản trực tiếp tạo ra nút.
- **Span bao phủ (covering span):** khoảng nhỏ nhất bao trọn các thành phần liên quan, có thể gồm khoảng trắng hoặc dấu phân cách ở giữa.

Ví dụ, một khai báo có thể có span bao phủ từ từ khóa mở đầu đến dấu kết thúc, còn span của tên định danh chỉ bao phủ phần tên. Nên giữ span đủ chi tiết cho nhu cầu chẩn đoán và điều hướng.

### 3.3. Span không có hoặc không liên tục

Một nút được tạo tổng hợp có thể không tương ứng với một đoạn văn bản liên tục. Ví dụ, transformer tạo một nút mặc định từ cấu hình ngầm định hoặc ghép thông tin từ nhiều vị trí. Trong trường hợp này, không nên giả vờ nút có một span chính xác duy nhất.

Có thể biểu diễn:

- Span không xác định cho nút do công cụ tạo.
- Nhiều source span cho nút được tổng hợp từ nhiều đoạn.
- Một vị trí nguồn chính cùng các vị trí liên quan.
- Metadata nguồn gốc chỉ ra bước biến đổi đã tạo nút.

## 4. Offset, dòng và cột

Các hệ thống thường hiển thị lỗi theo dòng và cột, trong khi parser thường làm việc thuận tiện hơn với offset.

### 4.1. Offset ký tự

Offset là vị trí của ký tự trong văn bản tính từ đầu. Khi có offset bắt đầu và kết thúc, công cụ có thể lấy lại đoạn văn bản tương ứng.

Tuy nhiên, cần xác định đơn vị offset:

- Byte trong mã hóa UTF-8.
- Unicode code point.
- UTF-16 code unit như cách đánh chỉ số chuỗi của Java.

Ba cách đếm này không luôn giống nhau. Một ký tự ngoài Basic Multilingual Plane có thể chiếm nhiều byte UTF-8 và hai code unit UTF-16 nhưng chỉ là một Unicode code point. Nếu lexer dùng offset UTF-16 còn editor hoặc thư viện khác dùng code point, việc đánh dấu có thể lệch.

### 4.2. Dòng và cột

Dòng thường bắt đầu từ 1 trong thông báo cho người dùng. Cột có thể bắt đầu từ 1 hoặc 0 tùy giao thức và thư viện. Cần thống nhất khi chuyển giữa parser, diagnostic và IDE.

Ngoài ra, một số hệ thống tính cột theo code unit, Unicode code point hoặc số cột hiển thị trên màn hình. Tab có thể chiếm một ký tự nhưng hiển thị rộng nhiều cột; ký tự kết hợp Unicode có thể gồm nhiều code point nhưng hiển thị như một ký tự. Vì vậy, cột parser tính được chưa chắc trùng với cột trực quan trong editor. Công cụ tích hợp IDE nên chuyển đổi theo quy ước của giao thức editor.

### 4.3. Quy tắc xuống dòng

Tệp có thể dùng LF (`\n`), CRLF (`\r\n`) hoặc dạng xuống dòng khác. Bộ đọc nguồn cần chuẩn hóa hoặc lưu thông tin gốc theo một quy tắc nhất quán. Nếu chuẩn hóa xuống dòng trước khi parse, offset sau chuẩn hóa sẽ không còn tương ứng trực tiếp với byte offset trong tệp gốc.

Một cách đơn giản là parser làm việc trên chuỗi đã chuẩn hóa và mọi source span đều dùng offset trong chuỗi đó. Khi cần sửa tệp gốc, lớp quản lý nguồn phải biết cách chuyển đổi hoặc giữ ánh xạ giữa vị trí chuẩn hóa và vị trí ban đầu.

## 5. Lưu vị trí nguồn trong mô hình AST

Có nhiều cách gắn source span vào cây cú pháp.

### 5.1. Gắn span trực tiếp vào mỗi nút

Một cách đơn giản là mọi nút AST đều có trường vị trí:

~~~java
record SourceSpan(
    String sourceId,
    int startOffset,
    int endOffset,
    int startLine,
    int startColumn,
    int endLine,
    int endColumn
) {}

interface AstNode {
    SourceSpan span();
}
~~~

Các record biểu diễn nút có thể lưu span:

~~~java
record NameExpr(
    String name,
    SourceSpan span
) implements AstNode {}

record BinaryExpr(
    AstNode left,
    String operator,
    AstNode right,
    SourceSpan span
) implements AstNode {}
~~~

Ưu điểm là mỗi nút tự mang thông tin nguồn, dễ dùng trong visitor và diagnostic. Hạn chế là mọi nút phải mang metadata, kể cả khi một số nút tổng hợp không có vị trí nguồn tự nhiên.

### 5.2. Dùng wrapper hoặc node metadata

Một thiết kế khác tách nội dung nút khỏi thông tin nguồn:

~~~java
record LocatedNode<T extends AstNode>(
    T node,
    SourceSpan span
) {}
~~~

Cách này hữu ích khi muốn tái sử dụng mô hình nút cho dữ liệu không có nguồn văn bản, hoặc khi một node có thể có nhiều nguồn gốc. Tuy nhiên, nó khiến code truy cập nút phải đi qua wrapper.

### 5.3. Lưu vị trí trong bảng phụ

Nếu AST bất biến và muốn giảm metadata trên mỗi nút, công cụ có thể cấp node ID rồi lưu span trong bảng:

~~~text
Node ID       Source span
------------------------------------
node-001      daily.pipe:1:1-4:2
node-002      daily.pipe:2:5-2:24
node-003      daily.pipe:3:12-3:28
~~~

Cách này tách metadata khỏi cấu trúc cú pháp và có thể thuận tiện khi quản lý nhiều loại dữ liệu phân tích. Đổi lại, mọi truy cập cần tra bảng và node ID phải ổn định trong phạm vi mà bảng được dùng.

### 5.4. Chọn cách biểu diễn

| Cách | Lợi ích | Chi phí |
|---|---|---|
| Span trực tiếp trên node | Truy cập đơn giản, dễ truyền qua visitor | Tăng kích thước node, metadata gắn chặt với AST |
| Wrapper | Tách nội dung và vị trí | Thêm lớp truy cập, cần quản lý wrapper qua biến đổi |
| Bảng phụ theo node ID | AST gọn, metadata có thể thay đổi độc lập | Cần quản lý ID và tra cứu, dễ mất liên kết nếu node bị thay thế |

Với DSL nhỏ, lưu span trực tiếp thường dễ hiểu. Với IDE hoặc compiler có nhiều dạng metadata, bảng phụ hoặc wrapper có thể phù hợp hơn. Dù chọn cách nào, cần bảo đảm span không bị mất khi AST được biến đổi.

## 6. Từ token đến AST: bảo toàn vị trí nguồn

Để truy vết chính xác, vị trí cần được ghi nhận từ giai đoạn lexer và truyền qua parser đến AST builder.

### 6.1. Token giữ span

Một token có thể chứa:

~~~text
Token
    kind = IDENTIFIER
    lexeme = "status"
    startOffset = 37
    endOffset = 43
    line = 3
    column = 12
~~~

Lexer biết chính xác vị trí bắt đầu và kết thúc khi nhận diện token. Đây là thời điểm thuận lợi để ghi lại source span vì sau đó AST có thể bỏ qua các chi tiết token.

### 6.2. Parser kết hợp span cho nút cha

Khi parser tạo nút biểu thức từ nhiều token hoặc nút con, nó có thể kết hợp span:

~~~text
FieldReference span: [37, 43)
Operator token:      [44, 46)
StringLiteral span:  [47, 53)

EqualExpression span: [37, 53)
~~~

Span cha được tính từ điểm bắt đầu của thành phần đầu tiên đến điểm kết thúc của thành phần cuối cùng, theo quy tắc của grammar. Nếu cấu trúc có từ khóa mở đầu hoặc dấu kết thúc cần đưa vào span, parser phải lấy vị trí từ token tương ứng.

### 6.3. Không tính lại vị trí bằng cách tìm chuỗi

Một cách làm không đáng tin cậy là parse AST xong rồi tìm tên hoặc literal trong văn bản để đoán vị trí. Một tên có thể xuất hiện nhiều lần:

~~~text
filter status == "PAID" or previousStatus == "PAID"
~~~

Tìm chuỗi PAID hoặc status có thể trả về lần xuất hiện đầu tiên thay vì vị trí của nút đang xử lý. Token và parser đã có thông tin chính xác, vì vậy hãy truyền vị trí theo luồng phân tích thay vì tìm lại bằng văn bản.

## 7. Diagnostic và liên kết về nguồn

Diagnostic là thông tin về lỗi, cảnh báo hoặc ghi chú do công cụ phát hiện. Một diagnostic hữu ích cần liên kết với source span và có thể có thêm các vị trí liên quan.

### 7.1. Cấu trúc diagnostic

Một mô hình khái quát:

~~~text
Diagnostic
    severity = ERROR
    code = "UNKNOWN_FIELD"
    message = "Trường 'status' không tồn tại trong nguồn orders.csv"
    primarySpan = daily.pipe:3:12-3:18
    relatedSpans = [...]
~~~

Các trường thường có:

- Mức độ: error, warning, information hoặc hint.
- Mã lỗi ổn định để IDE và công cụ tự động nhận diện.
- Thông điệp hướng đến người dùng.
- Vị trí chính cần đánh dấu.
- Vị trí liên quan, ví dụ nơi khai báo hoặc nơi mở khối.
- Gợi ý sửa nếu công cụ có thể xác định an toàn.

### 7.2. Vị trí chính và vị trí liên quan

Ví dụ DSL tham chiếu biến chưa được khai báo:

~~~text
pipeline "report" {
    filter amount > threshold
}
~~~

Diagnostic có thể đánh dấu threshold là vị trí chính. Nếu có một khai báo gần đó nhưng không nằm trong scope, công cụ có thể đính kèm vị trí khai báo như một vị trí liên quan và giải thích vì sao không thể tham chiếu.

Với lỗi thiếu dấu đóng, vị trí chính có thể là cuối tệp, trong khi vị trí liên quan là dấu mở khối:

~~~text
daily.pipe:8:1: error: thiếu '}' để đóng khối pipeline
daily.pipe:1:24: khối được mở tại đây
~~~

### 7.3. Chẩn đoán không nên phụ thuộc văn bản lỗi

IDE và công cụ tự động nên dựa vào mã lỗi, severity và source span thay vì phân tích chuỗi thông báo. Văn bản có thể được dịch hoặc thay đổi; mã lỗi ổn định giúp giữ tương thích giữa các phiên bản công cụ.

## 8. Truy vết khi biến đổi AST

Sau khi parse, AST có thể được chuẩn hóa, mở rộng cú pháp đường tắt, tối ưu hóa hoặc chuyển thành IR. Mỗi lần biến đổi có thể tạo nút mới, gộp nút hoặc xóa nút. Nếu không quản lý nguồn gốc, thông tin vị trí sẽ bị mất hoặc trở nên sai lệch.

### 8.1. Nút giữ nguyên nguồn

Nếu transformer chỉ tạo một wrapper hoặc thay đổi cấu trúc mà vẫn đại diện cho cùng đoạn DSL, nút mới có thể kế thừa span của nút gốc.

Ví dụ, cú pháp đường tắt:

~~~text
is_paid(order)
~~~

có thể được mở rộng thành:

~~~text
order.status == "PAID"
~~~

Các nút được tạo ra từ việc mở rộng có thể cùng liên kết về span của lời gọi is_paid(order). Nhờ đó, lỗi trong biểu thức mở rộng vẫn có thể được báo tại lời gọi mà người dùng nhìn thấy.

### 8.2. Nút tổng hợp từ nhiều nguồn

Một nút có thể được tạo từ nhiều vị trí nguồn, ví dụ khi DSL hỗ trợ ghép cấu hình hoặc kế thừa:

~~~text
base_config "common"
service "billing" extends "common" {
    replicas 4
}
~~~

Giá trị hiệu lực của cấu hình dịch vụ có thể kết hợp thuộc tính từ cấu hình gốc và phần ghi đè tại dịch vụ. Một nút kết quả có thể có:

- Nguồn gốc chính là nơi khai báo dịch vụ.
- Vị trí liên quan là thuộc tính được kế thừa.
- Quy tắc hợp nhất xác định nguồn nào thắng khi có xung đột.

Không nên gộp mọi vị trí thành một span liên tục nếu chúng nằm ở các tệp hoặc đoạn văn bản khác nhau.

### 8.3. Nút không có nguồn trực tiếp

Một số nút do compiler tạo ra như giá trị mặc định, lời gọi runtime ẩn hoặc lệnh chuyển đổi có thể không tương ứng với văn bản người dùng. Có thể gắn loại nguồn SYNTHETIC và lưu vị trí của cấu trúc đã kích hoạt việc tạo nút.

Khi báo lỗi, công cụ có thể:

- Trỏ về cấu trúc DSL đã tạo ra nút tổng hợp.
- Trỏ về vị trí cấu hình mặc định nếu có.
- Báo lỗi ở mức hệ thống nếu không có vị trí người dùng phù hợp.

Điều quan trọng là phân biệt vị trí thật với vị trí suy ra. Gắn một span bất kỳ cho nút tổng hợp có thể dẫn người dùng đến sai chỗ.

### 8.4. Source origin hoặc provenance

Có thể biểu diễn nguồn gốc của một nút như:

~~~text
Origin
    kind = DESUGARED
    primary = daily.pipe:3:12-3:25
    related = common.rules:8:1-8:16
    transformation = "expand-is-paid"
~~~

Provenance có thể là một cây hoặc đồ thị vì một nút kết quả có thể được tạo từ nhiều nút đầu vào, và một nút đầu vào có thể tạo ra nhiều nút kết quả. Cấu trúc provenance cần giữ đủ thông tin để truy vết nhưng tránh tạo liên kết vòng hoặc giữ toàn bộ lịch sử không cần thiết.

## 9. Source map khi sinh mã

Nhiều DSL không được thực thi trực tiếp. Công cụ có thể chuyển DSL thành SQL, Java, JavaScript, cấu hình hoặc một định dạng backend khác. Khi đó, **source map** liên kết vị trí trong mã đích với vị trí trong mã nguồn DSL.

Ví dụ:

~~~text
DSL:
    filter amount > 100

SQL sinh ra:
    WHERE amount > 100
~~~

Nếu backend báo lỗi ở đoạn amount > 100, compiler cần biết đoạn SQL đó được sinh từ câu lệnh filter nào trong DSL.

### 9.1. Ánh xạ theo đoạn mã

Một source map có thể lưu nhiều bản ghi:

| Mã đích | Nguồn DSL | Ý nghĩa |
|---|---|---|
| SQL dòng 4, cột 7-20 | daily.pipe dòng 3, cột 12-25 | Biểu thức lọc |
| SQL dòng 5, cột 1-18 | daily.pipe dòng 4, cột 5-22 | Biểu thức tổng hợp |
| SQL dòng 6, cột 1-35 | daily.pipe dòng 5, cột 5-29 | Khai báo đầu ra hoặc cấu hình đích |

Ánh xạ có thể dựa trên khoảng ký tự, token, node ID hoặc source span. Nếu một đoạn mã đích được ghép từ nhiều nguồn, source map cần biểu diễn nhiều nguồn hoặc chọn một vị trí chính kèm các vị trí liên quan.

### 9.2. Ánh xạ qua nhiều giai đoạn

Một pipeline compiler có thể gồm:

~~~text
DSL source
   |
   v
AST
   |
   v
Normalized IR
   |
   v
SQL IR
   |
   v
Generated SQL
~~~

Mỗi giai đoạn có thể thay đổi cấu trúc. Để lỗi backend quay về đúng dòng DSL, thông tin nguồn phải được truyền qua các giai đoạn hoặc được giữ trong bảng ánh xạ. Nếu một giai đoạn loại bỏ node ID và source span, các giai đoạn sau khó khôi phục mối liên hệ.

### 9.3. Nguồn gốc một-nhiều và nhiều-một

- **Một-nhiều:** một câu lệnh DSL sinh ra nhiều câu lệnh backend. Các đoạn mã đích đều có thể ánh xạ về cùng một source span.
- **Nhiều-một:** nhiều cấu trúc DSL được gộp thành một biểu thức hoặc câu lệnh backend. Source map có thể lưu nhiều nguồn gốc.
- **Không có nguồn:** mã đích được sinh từ giá trị mặc định hoặc cơ chế runtime. Có thể đánh dấu là synthetic.

Source map không nhất thiết là phép ánh xạ một-một. Mô hình cần hỗ trợ các trường hợp biến đổi thực tế của compiler.

## 10. Truy vết qua macro, include và import

Một số DSL hỗ trợ tái sử dụng cấu trúc qua macro, template, include hoặc import. Khi đó, một nút có thể xuất phát từ tệp được nhập hoặc từ nội dung được mở rộng.

### 10.1. Include hoặc import

Ví dụ:

~~~text
import "common/pipeline.rules"

pipeline "daily" {
    use common_filters
}
~~~

Khi phân tích, công cụ có thể đọc nhiều tệp. Mỗi source span phải gắn với đúng source ID, không chỉ dòng và cột. Dòng 5 ở tệp hiện tại khác dòng 5 ở tệp được import.

Source manager thường quản lý:

- ID duy nhất cho mỗi nguồn.
- Nội dung nguồn và đường dẫn hiển thị.
- Phiên bản hoặc checksum của nội dung nếu cần cache.
- Ánh xạ giữa source ID và văn bản.
- Quan hệ include/import giữa các nguồn.

### 10.2. Macro hoặc template

Giả sử DSL có macro:

~~~text
macro paid(order) {
    order.status == "PAID"
}

filter paid(currentOrder)
~~~

Sau mở rộng, biểu thức so sánh được tạo từ thân macro nhưng được kích hoạt bởi lời gọi paid(currentOrder). Nếu lỗi phát sinh trong thân macro, người dùng có thể cần xem cả vị trí lời gọi lẫn vị trí định nghĩa macro.

Một diagnostic tốt có thể cung cấp:

- Vị trí chính tại biểu thức lỗi trong thân macro.
- Vị trí liên quan tại nơi macro được gọi.
- Tên macro hoặc bước mở rộng.

Nếu macro được mở rộng nhiều lần, một vị trí định nghĩa có thể liên quan đến nhiều vị trí gọi. Provenance cần giữ được chuỗi mở rộng để công cụ không nhầm lần gọi này với lần gọi khác.

### 10.3. Chuỗi nguồn gốc

Một nút sau nhiều lần biến đổi có thể có lịch sử:

~~~text
Nút IR
  <- được tạo từ AST sau desugar
  <- được mở rộng từ macro "paid"
  <- lời gọi macro tại daily.pipe:8
  <- định nghĩa macro tại common/rules.dsl:2
~~~

Không phải mọi lỗi đều cần hiển thị toàn bộ chuỗi này. Công cụ nên chọn vị trí hữu ích nhất làm vị trí chính và giữ các bước còn lại làm thông tin liên quan hoặc chi tiết gỡ lỗi.

## 11. Truy vết trong IDE và công cụ phát triển

Source tracking là nền tảng cho nhiều tính năng IDE:

### 11.1. Đánh dấu lỗi và cảnh báo

IDE nhận diagnostic cùng source range để gạch chân biểu thức hoặc hiển thị biểu tượng ở lề. Khi người dùng sửa văn bản, công cụ cần cập nhật range theo nội dung mới.

### 11.2. Go to definition

Khi người dùng chọn một tham chiếu, semantic model xác định symbol mà nó trỏ đến. Source span của khai báo cho phép IDE mở đúng tệp và đặt con trỏ tại định nghĩa.

### 11.3. Find references

Ngược lại, từ một khai báo, IDE có thể tìm các nút tham chiếu trong những AST hoặc module đã phân tích. Mỗi tham chiếu cần có source span để editor đánh dấu vị trí.

### 11.4. Hover và tài liệu ngữ cảnh

Khi trỏ vào một nút hoặc tên, IDE có thể hiển thị kiểu dữ liệu, mô tả, nguồn khai báo hoặc kết quả phân tích. Việc này dựa trên liên kết giữa node, symbol và vị trí nguồn.

### 11.5. Quick fix và code action

Một diagnostic có thể đề xuất thay thế đoạn văn bản:

~~~text
Unknown field "custmer_id".
Suggested correction: "customer_id"
~~~

Code action cần source range để thay đúng đoạn. Nếu công cụ chỉ lưu tên trường sai mà không lưu span, việc sửa tự động có thể thay nhầm một lần xuất hiện khác.

### 11.6. Refactoring

Đổi tên một biến hoặc trường miền cần cập nhật khai báo và tất cả tham chiếu hợp lệ. Semantic reference giúp xác định đúng symbol; source span giúp sửa từng đoạn trong tệp. Chỉ thay thế chuỗi theo tên có thể vô tình sửa chú thích, chuỗi literal hoặc một symbol khác trùng tên.

## 12. Truy vết trong phân tích tăng dần

IDE thường không parse lại toàn bộ dự án sau mỗi lần gõ phím. Parser tăng dần (incremental parser) cố gắng tái sử dụng các phần cây không bị ảnh hưởng.

Khi văn bản thay đổi:

1. Editor gửi vùng thay đổi hoặc nội dung mới.
2. Source manager cập nhật phiên bản văn bản.
3. Lexer/parser xác định vùng cấu trúc bị ảnh hưởng.
4. Các nút cũ có thể được tái sử dụng nếu vẫn hợp lệ.
5. Span của các nút sau vùng chỉnh sửa có thể cần dịch offset.
6. Semantic analysis cập nhật các liên kết bị ảnh hưởng.
7. Diagnostic và source map được làm mới theo phiên bản nguồn mới.

### 12.1. Vì sao offset cũ có thể không còn đúng?

Nếu người dùng chèn 5 ký tự trước một nút, offset của nút đó trong văn bản mới tăng thêm 5 theo đơn vị offset đã chọn. Nếu chỉ tái sử dụng AST cũ mà không cập nhật span, diagnostic sẽ đánh dấu sai vị trí.

### 12.2. Phiên bản nguồn

Một source span nên được hiểu trong ngữ cảnh phiên bản nội dung mà nó được tạo ra. Có thể gắn source ID cùng revision hoặc version. Nếu văn bản đã thay đổi, span cũ không nhất thiết còn hợp lệ.

Điều này đặc biệt quan trọng khi xử lý tác vụ bất đồng bộ: kết quả phân tích của phiên bản trước có thể trả về sau khi người dùng đã sửa tệp. IDE cần bỏ qua hoặc chuyển đổi kết quả cũ thay vì áp dụng range sai lên văn bản mới.

## 13. Sửa mã nguồn dựa trên source span

Ngoài việc hiển thị vị trí, công cụ có thể dùng span để thay thế hoặc chèn văn bản.

Ví dụ, một quick fix thay tên trường:

~~~text
filter custmer_id == "C-01"
       ^^^^^^^^^^^
~~~

Nếu span xác định chính xác tên sai, công cụ có thể thay đoạn đó bằng customer_id. Khi áp dụng nhiều chỉnh sửa cùng lúc, cần xử lý thứ tự offset. Thông thường, các chỉnh sửa được áp dụng từ cuối tệp về đầu tệp để việc thay đổi độ dài đoạn trước không làm lệch offset của đoạn sau.

Một mô hình chỉnh sửa có thể gồm:

~~~text
TextEdit
    sourceId
    range
    replacementText
~~~

Trước khi áp dụng, cần xác nhận edit vẫn gắn với phiên bản văn bản mà nó được tạo ra. Nếu tệp đã thay đổi, công cụ nên tính lại hoặc yêu cầu phân tích lại.

## 14. Ví dụ Java: gắn span và tạo diagnostic

Ví dụ sau minh họa một mô hình nhỏ để gắn vị trí nguồn cho nút và tạo diagnostic. Nó không phải parser hoàn chỉnh.

~~~java
record SourcePosition(int offset, int line, int column) {}

record SourceSpan(
    String sourceId,
    SourcePosition start,
    SourcePosition end
) {}

record Diagnostic(
    String code,
    String message,
    SourceSpan primarySpan
) {}

record FieldReference(
    String name,
    SourceSpan span
) {}
~~~

Khi semantic analyzer kiểm tra trường:

~~~java
void validateField(
    FieldReference field,
    java.util.Set<String> knownFields,
    java.util.List<Diagnostic> diagnostics
) {
    if (!knownFields.contains(field.name())) {
        diagnostics.add(new Diagnostic(
            "UNKNOWN_FIELD",
            "Trường '" + field.name() + "' không tồn tại",
            field.span()
        ));
    }
}
~~~

Nút FieldReference mang span từ parser. Semantic analyzer không cần tìm lại tên trường trong văn bản; nó chỉ tạo diagnostic dựa trên span đã được bảo toàn.

Trong hệ thống thực tế, nên dùng một kiểu source ID ổn định, quy ước offset rõ ràng, mã lỗi có tài liệu và cơ chế gom nhiều vị trí liên quan.

## 15. Kiểm thử khả năng truy vết

Kiểm thử source tracking cần xác nhận cả giá trị span lẫn hành vi sử dụng span.

| Trường hợp | Điều cần kiểm tra |
|---|---|
| Token ASCII trên một dòng | Offset, dòng và cột đúng |
| Nhiều dòng | Dòng/cột được tính chính xác sau newline |
| CRLF và LF | Quy tắc chuẩn hóa hoặc ánh xạ nhất quán |
| Ký tự Unicode ngoài BMP | Không lệch giữa UTF-16, code point và vị trí editor |
| Chuỗi có dấu ngoặc | Lexer không tính nhầm ký tự trong chuỗi là cấu trúc |
| Chú thích | Span và token tiếp theo không bị lệch |
| Nút cha và nút con | Span cha bao phủ đúng cấu trúc theo quy ước |
| Lỗi ngữ nghĩa | Diagnostic trỏ đúng tên hoặc biểu thức gây lỗi |
| Macro hoặc include | Vị trí định nghĩa và lời gọi được phân biệt |
| Sinh mã | Lỗi backend ánh xạ về đúng đoạn DSL |
| Chỉnh sửa văn bản | Span được cập nhật hoặc vô hiệu hóa theo revision |
| Quick fix | Chỉ thay đúng đoạn văn bản dự kiến |

Nên tạo các ví dụ nguồn nhỏ với vị trí mong đợi được xác định rõ. Có thể kiểm tra bằng snapshot diagnostic, nhưng cần bảo đảm snapshot phản ánh đúng quy ước offset và cột của công cụ.

## 16. Những sai lầm thường gặp

### 16.1. Chỉ lưu dòng và cột

Dòng và cột hữu ích cho hiển thị nhưng không đủ cho cắt đoạn, thay thế văn bản hoặc ánh xạ qua biến đổi. Thường nên giữ offset hoặc token range cùng với vị trí hiển thị.

### 16.2. Không xác định đơn vị offset

Byte, code point và UTF-16 code unit có thể khác nhau. Nếu các thành phần trong hệ thống dùng quy ước khác nhau, vị trí lỗi sẽ lệch, đặc biệt với Unicode.

### 16.3. Tìm lại vị trí sau khi đã tạo AST

Tìm tên hoặc literal trong văn bản có thể trả về lần xuất hiện sai. Vị trí nên được ghi nhận ngay trong lexer/parser và truyền theo các nút.

### 16.4. Mất span khi biến đổi cây

Transformer tạo nút mới nhưng không truyền nguồn gốc khiến lỗi ở giai đoạn sau không thể quay lại DSL. Mỗi phép biến đổi cần quy định cách kế thừa, kết hợp hoặc đánh dấu span.

### 16.5. Coi source map luôn là ánh xạ một-một

Một nút có thể sinh nhiều đoạn mã; nhiều nút có thể được gộp thành một đoạn; một nút tổng hợp có thể không có nguồn trực tiếp. Mô hình ánh xạ cần hỗ trợ nhiều nguồn và nguồn synthetic.

### 16.6. Dùng span của cha cho mọi lỗi con

Nếu mọi diagnostic đều trỏ vào cả câu lệnh, người dùng khó biết phần nào sai. Hãy giữ span đủ nhỏ cho identifier, toán tử, literal và biểu thức khi parser có thể xác định.

### 16.7. Không gắn phiên bản nguồn

Trong IDE hoặc tác vụ bất đồng bộ, span được tạo từ nội dung cũ có thể bị áp dụng lên nội dung mới. Cần gắn revision hoặc kiểm tra phiên bản trước khi dùng span.

## 17. Quy trình triển khai source tracking

Một quy trình có thể áp dụng cho DSL:

1. **Xác định nhu cầu truy vết.** Liệt kê các tính năng cần vị trí nguồn: diagnostic, IDE, refactoring, macro, code generation hay debugging.
2. **Chọn mô hình source ID.** Quy định cách nhận diện tệp, chuỗi nhập trực tiếp và tài nguyên được import.
3. **Chọn đơn vị vị trí.** Xác định offset, dòng, cột và quy ước khoảng nửa mở.
4. **Ghi span trong lexer.** Mỗi token có vị trí bắt đầu và kết thúc.
5. **Truyền span qua parser.** Nút AST lấy span từ token và các nút con theo grammar.
6. **Giữ nguồn qua biến đổi.** Transformer xác định span kế thừa, nhiều nguồn hoặc nguồn synthetic.
7. **Thiết kế diagnostic.** Dùng mã lỗi ổn định, vị trí chính và vị trí liên quan.
8. **Tạo source map cho backend.** Liên kết đoạn mã đích với nguồn DSL qua các giai đoạn.
9. **Tích hợp editor.** Chuyển đổi range đúng giao thức và cập nhật theo revision.
10. **Kiểm thử bằng nguồn đại diện.** Bao gồm Unicode, nhiều tệp, macro, lỗi và chỉnh sửa tăng dần.

Không phải DSL nhỏ nào cũng cần source map nhiều tầng. Có thể bắt đầu với source ID và span trên token/AST, sau đó mở rộng provenance khi xuất hiện nhu cầu macro, sinh mã hoặc IDE.

## 18. Câu hỏi tự kiểm tra

1. Truy vết về mã nguồn có vai trò gì trong một công cụ DSL?
2. Source span là gì? Vì sao cần quy định rõ khoảng đóng/mở?
3. Phân biệt span của token, span của nút AST và span bao phủ.
4. Byte offset, Unicode code point và UTF-16 code unit khác nhau như thế nào?
5. Vì sao nên ghi vị trí trong lexer/parser thay vì tìm lại chuỗi sau khi đã tạo AST?
6. Diagnostic cần những thông tin nào để IDE đánh dấu lỗi và hiển thị vị trí liên quan?
7. Một transformer tạo nút mới cần xử lý source span và provenance ra sao?
8. Source map hỗ trợ ánh xạ lỗi từ SQL hoặc mã được sinh về DSL như thế nào?
9. Vì sao source map có thể cần biểu diễn quan hệ một-nhiều hoặc nhiều-một?
10. Trình bày cách source tracking hỗ trợ Go to definition, Find references và quick fix.
11. Khi văn bản thay đổi trong IDE, vì sao span cũ có thể không còn hợp lệ?
12. Hãy đề xuất mô hình source span và diagnostic cho một DSL bạn biết, nêu rõ quy ước offset và cách truy vết qua một bước biến đổi.
