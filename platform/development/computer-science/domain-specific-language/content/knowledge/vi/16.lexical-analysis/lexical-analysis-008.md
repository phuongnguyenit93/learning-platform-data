# Lexer tăng dần

Trong một ngôn ngữ miền đặc thù (Domain-Specific Language — DSL), lexer chuyển văn bản nguồn thành chuỗi token để parser có thể nhận diện khai báo, biểu thức, câu lệnh và cấu trúc của ngôn ngữ. Với một trình biên dịch chạy theo lô, lexer thường đọc toàn bộ tệp mỗi khi biên dịch. Nhưng trong IDE hoặc trình soạn thảo DSL, người dùng sửa văn bản liên tục: thêm một ký tự, xóa dấu ngoặc, đổi tên thuộc tính hoặc chèn một dòng. Nếu mỗi thay đổi đều khiến hệ thống phân tích từ đầu toàn bộ tài liệu, phản hồi có thể chậm khi tệp lớn hoặc khi có nhiều tài liệu đang mở.

**Lexer tăng dần** (*incremental lexer* hoặc *incremental lexing*) là cơ chế cập nhật chuỗi token sau một thay đổi nhỏ của văn bản bằng cách tái phân tích phần có thể bị ảnh hưởng và tái sử dụng những token còn hợp lệ. Lexer tăng dần cần biết trạng thái từ vựng tại các điểm có thể bắt đầu lại, xác định phạm vi bị ảnh hưởng bởi chỉnh sửa, rồi tìm thời điểm kết quả mới hội tụ với kết quả cũ. Khi hội tụ, phần token phía sau có thể được dùng lại với vị trí đã điều chỉnh.

Ví dụ, một tệp DSL có hàng nghìn dòng và người dùng chỉ đổi `order.total` thành `order.grandTotal` ở dòng 120. Lexer tăng dần có thể bắt đầu lại từ một checkpoint gần trước vị trí sửa, phân tích phần bị ảnh hưởng, sau đó tái sử dụng token của các dòng phía sau khi trạng thái lexer và nội dung token đã trở lại tương đương. Nếu chỉnh sửa mở một chuỗi nhiều dòng hoặc comment kéo dài đến cuối tệp, phạm vi cần phân tích lại có thể lớn hơn nhiều, thậm chí phải đi đến cuối tài liệu.

Mục tiêu của lexer tăng dần là duy trì kết quả tương đương với việc chạy lexer đầy đủ trên phiên bản văn bản mới, đồng thời giảm công việc trung bình cho các chỉnh sửa cục bộ. Nó là một kỹ thuật về hiệu năng và trải nghiệm công cụ; nó không được phép làm thay đổi cách token hóa mà đặc tả DSL quy định.

## 1. Lexer tăng dần là gì?

### Lexer thông thường

Lexer thông thường đọc văn bản theo thứ tự, nhận diện các lexeme và tạo token. Một token thường có loại, giá trị hoặc đoạn văn bản gốc, cùng vị trí nguồn.

Ví dụ DSL:

~~~text
policy OrderPolicy {
    when order.total >= 1000 then approveOrder;
}
~~~

Lexer có thể tạo chuỗi token:

| Thứ tự | Loại token | Lexeme |
|---:|---|---|
| 1 | `POLICY` | `policy` |
| 2 | `IDENTIFIER` | `OrderPolicy` |
| 3 | `LBRACE` | `{` |
| 4 | `WHEN` | `when` |
| 5 | `IDENTIFIER` | `order` |
| 6 | `DOT` | `.` |
| 7 | `IDENTIFIER` | `total` |
| 8 | `GREATER_EQUAL` | `>=` |
| 9 | `NUMBER` | `1000` |
| 10 | `THEN` | `then` |
| 11 | `IDENTIFIER` | `approveOrder` |
| 12 | `SEMICOLON` | `;` |
| 13 | `RBRACE` | `}` |

Với cách làm toàn phần, lexer thường xóa hoặc thay thế danh sách token cũ rồi quét lại toàn bộ tài liệu sau mỗi lần người dùng sửa.

### Lexer tăng dần

Lexer tăng dần giữ lại kết quả của lần phân tích trước. Khi tài liệu thay đổi, nó:

1. Nhận vùng văn bản bị sửa và phiên bản tài liệu mới.
2. Xác định checkpoint an toàn trước vùng sửa.
3. Khôi phục trạng thái từ vựng tại checkpoint đó.
4. Quét văn bản mới từ checkpoint.
5. So sánh token và trạng thái mới với phần token cũ đã được dịch vị trí.
6. Dừng khi tìm được điểm hội tụ an toàn.
7. Tái sử dụng phần token cũ còn hợp lệ phía sau điểm hội tụ.
8. Cập nhật bảng vị trí, diagnostic và dữ liệu phụ trợ liên quan.

Điểm quan trọng là lexer không chỉ quét lại các ký tự được chèn hoặc xóa. Một chỉnh sửa nhỏ có thể làm thay đổi cách diễn giải các ký tự ở phía sau. Chẳng hạn, thêm dấu nháy mở chuỗi có thể khiến dấu chấm phẩy và từ khóa trên nhiều dòng tiếp theo trở thành nội dung chuỗi thay vì token độc lập.

### Ví dụ chỉnh sửa cục bộ

Trước khi sửa:

~~~text
let total = 100;
let tax = 8;
let payable = total + tax;
~~~

Sau khi sửa `100` thành `150`:

~~~text
let total = 150;
let tax = 8;
let payable = total + tax;
~~~

Token của literal ở dòng đầu thay đổi. Nếu trạng thái từ vựng ở cuối dòng và các token sau đó không đổi, lexer có thể giữ nguyên token của hai dòng còn lại, chỉ cập nhật offset nếu độ dài văn bản thay đổi.

## 2. Vì sao cần lexer tăng dần?

### Phản hồi nhanh trong IDE

Người dùng mong muốn lỗi cú pháp, tô màu token, gợi ý mã và thông tin hover cập nhật gần như ngay sau khi gõ. Quét lại toàn bộ một tài liệu lớn sau từng phím có thể gây trễ, nhất là khi editor phải xử lý nhiều tệp hoặc các DSL có chuỗi, comment và biểu thức lồng nhau.

### Tái sử dụng kết quả không bị ảnh hưởng

Phần lớn thao tác chỉnh sửa trong editor là cục bộ. Khi người dùng sửa một định danh ở một dòng, nhiều token ở các vùng khác thường không thay đổi về ý nghĩa. Tái sử dụng token giúp giảm số lần quét, giảm cấp phát bộ nhớ và giảm công việc cho parser tăng dần.

### Hỗ trợ phân tích liên tục

Một IDE thường duy trì lexer, parser, bộ phân giải tên, kiểm tra kiểu và diagnostic cho tài liệu đang mở. Lexer tăng dần có thể cung cấp một chuỗi token cập nhật để parser chỉ xử lý các vùng cấu trúc bị ảnh hưởng.

### Cải thiện trải nghiệm với tài liệu lớn

Các DSL mô tả workflow, mô hình miền, quy tắc hoặc cấu hình có thể chứa hàng nghìn đến hàng triệu ký tự. Incremental lexing giúp các chỉnh sửa nhỏ không phải chịu chi phí quét lại toàn bộ tài liệu trong trường hợp thông thường.

### Giảm công việc cho các dịch vụ phụ thuộc

Khi lexer xác định được vùng token thay đổi, hệ thống có thể truyền thông tin này cho parser, syntax highlighter và một số công cụ khác. Tuy nhiên, mỗi thành phần vẫn phải tự xác định phạm vi phụ thuộc của nó; token không đổi không có nghĩa AST hoặc ngữ nghĩa chắc chắn không đổi.

## 3. Đặc điểm quan trọng của lexer tăng dần

Một triển khai cần giải quyết các vấn đề sau:

- **Vùng chỉnh sửa:** phần văn bản nào đã được chèn, xóa hoặc thay thế?
- **Checkpoint:** tại vị trí nào lexer có thể khởi động lại với trạng thái đầy đủ?
- **Trạng thái từ vựng:** lexer đang ở chế độ bình thường, trong chuỗi, comment, interpolation hay một chế độ đặc biệt khác?
- **Phạm vi tái phân tích:** cần quét lại bao xa để bảo đảm các token mới đúng?
- **Điểm hội tụ:** khi nào token và trạng thái mới đủ tương đương với kết quả cũ để tái sử dụng suffix?
- **Dịch vị trí:** offset, dòng và cột của token cũ thay đổi thế nào sau chỉnh sửa?
- **Phiên bản tài liệu:** kết quả của một lần phân tích có còn khớp với văn bản editor đang hiển thị không?
- **Phục hồi lỗi:** lexer xử lý ra sao khi người dùng đang gõ một cấu trúc chưa hoàn chỉnh?

Các vấn đề này phải được thiết kế cùng nhau. Chỉ lưu danh sách token mà không lưu trạng thái lexer hoặc phiên bản nguồn thường không đủ để tái phân tích an toàn.

## 4. Mô hình dữ liệu cho lexer tăng dần

### Văn bản nguồn có phiên bản

Lexer tăng dần cần làm việc trên một snapshot văn bản nhất quán. Mỗi phiên bản tài liệu nên có ID hoặc số version tăng dần.

Ví dụ mô hình khái niệm:

~~~text
DocumentSnapshot
  documentId
  version
  textBuffer
  lineIndex
~~~

`textBuffer` có thể là chuỗi bất biến, rope hoặc piece table. `lineIndex` giúp chuyển đổi giữa offset và dòng/cột. Version giúp phân biệt token được tạo từ nội dung cũ với token thuộc nội dung mới.

### Token

Một token có thể chứa:

~~~text
Token
  kind
  startOffset
  endOffset
  lexemeOrSlice
  leadingTrivia
  trailingTrivia
  lexicalFlags
~~~

Các trường cụ thể phụ thuộc lexer. Một số lexer gắn comment và khoảng trắng vào token dưới dạng trivia; một số giữ chúng thành token riêng. Token có thể lưu lexeme trực tiếp hoặc giữ span để truy xuất từ text buffer.

### Lexical state

Trạng thái từ vựng mô tả thông tin cần thiết để tiếp tục token hóa chính xác từ một vị trí. Ví dụ:

~~~text
LexerState
  mode
  stringDelimiter
  commentDepth
  interpolationDepth
  indentationStack
  atLineStart
  pendingTokenContext
~~~

Không phải DSL nào cũng cần mọi trường này. Một lexer đơn giản chỉ có trạng thái bình thường có thể dùng một giá trị state duy nhất. DSL có string interpolation, nested comment, heredoc, indentation-sensitive syntax hoặc nhiều chế độ có thể cần state phong phú hơn.

### Checkpoint

Checkpoint là vị trí mà lexer đã lưu trạng thái để có thể tiếp tục quét từ đó:

~~~text
LexerCheckpoint
  sourceOffset
  tokenIndex
  stateBeforeNextToken
  documentVersion
~~~

Checkpoint thường được đặt tại đầu dòng hoặc ranh giới token thuận tiện. Nhưng checkpoint chỉ an toàn nếu state được lưu đủ để tái tạo chính xác cách lexer tiếp tục.

## 5. Trạng thái từ vựng và lý do phải lưu nó

Lexer không phải lúc nào cũng ở cùng một chế độ. Các ký tự giống nhau có thể tạo token khác nhau tùy trạng thái hiện tại.

### Chuỗi nhiều dòng

Ví dụ DSL cho phép chuỗi nhiều dòng:

~~~text
let message = "Order is pending
and requires manual review";
let status = PENDING;
~~~

Nếu lexer đang ở trong chuỗi tại cuối dòng đầu, các ký tự ở dòng tiếp theo vẫn thuộc string token cho đến dấu nháy đóng. Checkpoint ở đầu dòng thứ hai phải ghi nhận `mode = STRING`; nếu chỉ lưu offset mà không lưu mode, lexer có thể nhầm `and`, `requires` hoặc `PENDING` thành từ khóa và định danh bình thường.

### Comment nhiều dòng

~~~text
/*
  This is a long comment.
  The word when here is not a keyword.
*/
when order.isPaid then approveOrder;
~~~

Nếu người dùng xóa dấu `*/`, phần còn lại của tài liệu có thể trở thành comment. Lexer phải tái phân tích cho đến khi trạng thái comment hội tụ, hoặc đến cuối tệp nếu comment không bao giờ đóng.

### Comment lồng nhau

Nếu DSL cho phép comment lồng nhau:

~~~text
/* outer
   /* inner */
   still outer
*/
~~~

Lexer cần lưu độ sâu comment, chẳng hạn `commentDepth = 1` ở cuối dòng có comment còn mở. Một cờ boolean `insideComment` không đủ nếu cần phân biệt nhiều cấp lồng.

### String interpolation

Một DSL có thể cho phép:

~~~text
let message = "Order ${order.id} has total ${order.total}";
~~~

Lexer có thể chuyển qua lại giữa chế độ string và expression khi gặp `${` và `}`. Nếu chỉnh sửa làm thay đổi dấu ngoặc trong interpolation, trạng thái ở phía sau có thể thay đổi. Checkpoint cần giữ mode stack hoặc thông tin tương đương.

### Indentation-sensitive syntax

Với DSL mà thụt lề có ý nghĩa, lexer có thể tạo token `INDENT` và `DEDENT`. Trạng thái cần lưu stack độ sâu thụt lề. Thay đổi khoảng trắng ở đầu một dòng có thể làm thay đổi token cấu trúc của các dòng sau nếu stack không trở lại trạng thái cũ.

### Lexer nhiều chế độ

Một DSL có thể dùng các chế độ khác nhau cho phần văn bản, biểu thức, template, truy vấn hoặc khối mã nhúng. Trạng thái cần lưu chế độ hiện tại và ngữ cảnh chuyển đổi. Nếu mode được chọn bởi parser hoặc cấu trúc bên ngoài, ranh giới giữa lexer và parser cần được thiết kế rõ để lexer tăng dần biết đủ thông tin khi restart.

## 6. Checkpoint an toàn

Checkpoint giúp lexer không phải quay lại đầu tệp sau mỗi chỉnh sửa. Tuy nhiên, chọn checkpoint quá gần mà không lưu đủ trạng thái có thể tạo token sai.

### Checkpoint tại đầu dòng

Một chiến lược phổ biến là lưu trạng thái tại đầu mỗi dòng. Khi có edit, lexer tìm checkpoint ở dòng chứa vị trí bắt đầu chỉnh sửa hoặc dòng trước đó, rồi khôi phục trạng thái và quét lại.

Ưu điểm:

- Dễ ánh xạ với editor vì chỉnh sửa thường được báo theo range dòng/cột.
- Giới hạn khoảng phải quay lại trong trường hợp cấu trúc từ vựng không kéo dài quá xa.
- Dễ lưu state cho indentation, newline và chế độ string/comment.

Nhược điểm:

- Tệp có dòng rất dài vẫn có thể cần quét nhiều ký tự.
- Một cấu trúc nhiều dòng có thể khiến state lan truyền qua nhiều checkpoint.
- Tạo checkpoint quá dày làm tăng bộ nhớ và chi phí cập nhật.

### Checkpoint tại ranh giới token

Lexer có thể lưu checkpoint sau một số token hoặc tại ranh giới chắc chắn. Cách này giảm số checkpoint nhưng khi sửa có thể phải quay về token trước đó hoặc xa hơn để bảo đảm không có token bị ghép lại.

Ví dụ, trước khi sửa:

~~~text
count + total
~~~

Nếu chèn ký tự giữa `cou` và `nt`, token định danh thay đổi. Nếu chèn dấu `/` ngay trước `*`, hai ký tự có thể tạo delimiter comment `/*`. Do đó, lexer cần restart đủ sớm để nhận diện các delimiter nhiều ký tự và các token có thể hợp nhất qua vị trí edit.

### Checkpoint chỉ hợp lệ khi state đầy đủ

Checkpoint không chỉ là offset. Nó là cặp vị trí và trạng thái:

~~~text
Checkpoint = (offset, lexicalState)
~~~

Hai checkpoint ở cùng offset nhưng có state khác nhau không tương đương. Nếu lexer khởi động lại với state sai, token đầu tiên có thể khác và sai lệch tiếp tục lan truyền.

### Chọn checkpoint trước vùng sửa

Nếu edit bắt đầu ở offset `editStart`, một cách an toàn là chọn checkpoint gần nhất có offset không lớn hơn `editStart`. Với lexer có token cần lookahead hoặc delimiter nhiều ký tự, checkpoint cần nằm trước ranh giới có thể bị ảnh hưởng. Nếu checkpoint nằm ngay tại ranh giới token đã được xác nhận và state đầy đủ, có thể bắt đầu từ đó.

## 7. Thuật toán lexer tăng dần tổng quát

Giả sử phiên bản cũ có văn bản `S_old`, token `T_old` và checkpoint `C_old`. Người dùng áp dụng một edit thay đoạn `[a, b)` bằng văn bản mới `inserted`. Phiên bản mới là `S_new`.

Độ dịch offset sau edit đơn giản được tính:

~~~text
delta = length(inserted) - (b - a)
~~~

Các vị trí trước `a` không đổi. Các vị trí sau `b` được dịch thêm `delta` theo cùng hệ tọa độ. Vùng nằm trong hoặc chồng lấn với `[a, b)` cần được tính lại.

### Các bước xử lý

1. Xác định edit range và snapshot văn bản mới.
2. Tìm checkpoint cũ an toàn gần nhất trước `a`.
3. Giữ lại các token hoàn toàn nằm trước checkpoint.
4. Khởi tạo lexer mới tại checkpoint với lexical state đã lưu.
5. Quét token từ vị trí restart trên văn bản mới.
6. Sau vùng edit, so sánh chuỗi token mới với token cũ đã dịch offset.
7. Chỉ công nhận hội tụ khi token và lexical state tương ứng giống nhau trong một ranh giới an toàn.
8. Ghép token mới với prefix cũ và suffix cũ đã được dịch vị trí.
9. Cập nhật checkpoint, line index và thông tin phiên bản.

### Sơ đồ quy trình

~~~mermaid
flowchart TD
    A[Nhận edit và snapshot mới] --> B[Tìm checkpoint trước edit]
    B --> C[Khôi phục lexical state]
    C --> D[Quét token mới]
    D --> E{Đã qua edit và tìm được điểm hội tụ?}
    E -- Chưa --> D
    E -- Rồi --> F[Giữ token mới trong vùng ảnh hưởng]
    F --> G[Tái sử dụng suffix token cũ đã dịch offset]
    G --> H[Cập nhật checkpoint và token cache]
    H --> I[Thông báo token delta cho parser/editor]
~~~

Điều kiện hội tụ cần được định nghĩa cẩn thận. Chỉ thấy một token giống nhau chưa đủ; lexer phải xác nhận trạng thái sau token cũng tương đương để các token tiếp theo được phân tích theo cùng quy tắc.

## 8. Điểm hội tụ (convergence point)

**Điểm hội tụ** là vị trí sau vùng chỉnh sửa tại đó việc phân tích mới đã trở lại cùng trạng thái từ vựng và cùng chuỗi token như lần phân tích cũ, sau khi điều chỉnh vị trí do edit. Từ đó trở đi, phần suffix cũ có thể được tái sử dụng nếu không có phụ thuộc khác làm thay đổi cách token hóa.

### Vì sao phải so sánh cả token lẫn state?

Xét hai vị trí có cùng ký tự `abc`. Ở chế độ bình thường, lexer có thể tạo `IDENTIFIER("abc")`; ở trong chuỗi, nó chỉ là nội dung của `STRING_TEXT`. Lexeme giống nhau nhưng token kind hoặc mode khác nhau.

Ngay cả khi token hiện tại giống nhau, state sau token có thể khác. Ví dụ, một token mở string hoặc delimiter interpolation có thể khiến các ký tự tiếp theo được đọc theo chế độ khác. Do đó, điều kiện hội tụ cần bao gồm:

- Token kind giống nhau.
- Lexeme hoặc nội dung token tương đương.
- Các thông tin từ vựng ảnh hưởng token hóa tiếp theo giống nhau.
- Trạng thái lexer sau ranh giới so sánh giống nhau.
- Các điều kiện phụ thuộc phiên bản hoặc cấu hình lexer không thay đổi.

### So sánh với token cũ đã dịch offset

Sau khi edit, token phía sau thường đổi offset dù nội dung không đổi. Vì vậy, không thể so sánh span cũ và mới một cách trực tiếp. Lexer cần ánh xạ vị trí cũ sang vị trí mới bằng edit map hoặc `delta`.

Ví dụ, nếu chèn thêm 4 ký tự trước token `approveOrder`, token cũ có start offset `100` có thể tương ứng với token mới ở offset `104`. So sánh phải dùng nội dung, loại token và state; span được kiểm tra sau khi đã dịch.

### Một token giống nhau có đủ không?

Không nhất thiết. Một lexer có thể dùng lookahead, chế độ hoặc trạng thái phụ thuộc dòng. Để an toàn, có thể yêu cầu một chuỗi token liên tiếp cùng state đầu/cuối, hoặc so sánh tại checkpoint nơi state đã được lưu đầy đủ. Số token cần so sánh phụ thuộc cách lexer hoạt động; không có con số cố định đúng cho mọi DSL.

### Hội tụ không xảy ra

Nếu một chỉnh sửa làm thay đổi trạng thái từ vựng đến cuối tệp, sẽ không có điểm hội tụ trước EOF. Ví dụ, xóa dấu đóng comment nhiều dòng có thể khiến toàn bộ suffix trở thành comment. Khi đó, lexer phải quét đến cuối tài liệu và tạo token mới cho toàn bộ phần bị ảnh hưởng. Đây là trường hợp xấu nhất hợp lệ, không phải lỗi của thuật toán.

## 9. Ví dụ: sửa định danh và tái sử dụng suffix

Trước chỉnh sửa:

~~~text
let order = loadOrder();
let total = order.total;
let tax = calculateTax(total);
return total + tax;
~~~

Người dùng đổi `total` ở dòng hai thành `grandTotal`:

~~~text
let order = loadOrder();
let grandTotal = order.total;
let tax = calculateTax(grandTotal);
return grandTotal + tax;
~~~

Nếu lexer không có từ khóa ngữ cảnh phụ thuộc tên biến, việc đổi định danh chỉ ảnh hưởng token của tên đó và các offset phía sau. Lexer có thể:

- Giữ token của dòng đầu.
- Token hóa lại vùng chứa định danh được đổi.
- Cập nhật offset các token phía sau theo độ dài chênh lệch.
- Tái sử dụng token suffix nếu state hội tụ.

Parser và bộ phân giải tên vẫn phải xử lý các tham chiếu `grandTotal` ở những nơi liên quan. Việc token hóa không đổi ở một dòng không có nghĩa binding ngữ nghĩa của nó chắc chắn không đổi.

## 10. Ví dụ: chỉnh sửa làm thay đổi trạng thái nhiều dòng

Trước chỉnh sửa:

~~~text
let title = "Order summary";
when order.isPaid then approveOrder;
let status = PENDING;
~~~

Người dùng xóa dấu nháy đóng ở dòng đầu:

~~~text
let title = "Order summary;
when order.isPaid then approveOrder;
let status = PENDING;
~~~

Nếu chuỗi trong DSL kéo dài đến khi có dấu nháy đóng, các ký tự từ `when` đến cuối có thể trở thành nội dung chuỗi. Token hóa của nhiều dòng thay đổi. Lexer không thể chỉ quét lại dòng đầu rồi tái sử dụng suffix cũ. Nó phải tiếp tục quét cho đến khi tìm được dấu nháy đóng và state trở lại chế độ bình thường, hoặc đến EOF.

Trường hợp này cho thấy phạm vi lexing bị ảnh hưởng được xác định bởi ngữ nghĩa từ vựng, không chỉ bởi số ký tự đã chỉnh sửa.

## 11. Xử lý token có thể ghép qua ranh giới edit

Một lỗi triển khai phổ biến là bắt đầu lexer đúng tại ký tự đầu tiên được chèn rồi chỉ quét phần văn bản mới. Token có thể được hình thành từ ký tự ở cả hai phía của vùng sửa.

Ví dụ trước chỉnh sửa:

~~~text
count / value
~~~

Nếu chèn `*` ngay sau `/`, kết quả có thể chứa delimiter comment `/*` tùy quy tắc DSL. Tương tự, ghép `=` với `=` có thể tạo toán tử `==`; ghép chữ cái và chữ số có thể tạo thành một định danh hoặc literal khác.

Vì vậy:

- Bắt đầu từ checkpoint trước token hoặc ranh giới có thể bị ghép.
- Để lexer xử lý lại token ở hai phía nếu edit chạm ranh giới token.
- Không tái sử dụng token có span chồng lấn vùng sửa.
- Dùng đúng quy tắc longest match và lookahead của lexer.

Một số lexer dùng maximal munch: chọn lexeme dài nhất phù hợp. Với lexer như vậy, việc chèn một ký tự có thể làm thay đổi token liền kề dù ký tự đó nằm ngoài đoạn chèn.

## 12. Trivia, comment và khoảng trắng

Lexer thường phân biệt token có ý nghĩa cú pháp với **trivia** như khoảng trắng, tab, newline và comment. Cách lưu trivia ảnh hưởng đến incremental lexing và khả năng giữ nguyên văn bản trong editor.

### Trivia gắn với token

Một chiến lược là gắn leading trivia vào token tiếp theo. Ví dụ:

~~~text
Token: IDENTIFIER("order")
Leading trivia: newline + spaces
~~~

Nếu người dùng chỉ đổi comment hoặc khoảng trắng, token cú pháp có thể giữ nguyên nhưng trivia thay đổi. Lexer cần thông báo thay đổi trivia cho formatter hoặc công cụ hiển thị nếu chúng quan tâm.

### Comment có ảnh hưởng đến trạng thái

Comment một dòng thường kết thúc tại newline; comment nhiều dòng có thể kéo dài qua nhiều dòng. Sửa delimiter comment có thể ảnh hưởng đến mọi token phía sau. Vì vậy, dù comment không được parser xem như token cú pháp, trạng thái comment vẫn là một phần của lexical state.

### Giữ comment khi tái sử dụng suffix

Nếu comment được lưu riêng, suffix chỉ có thể tái sử dụng khi cả token và trivia tương ứng vẫn giống nhau theo quy tắc của hệ thống. Không nên giữ token cũ nhưng vô tình làm mất comment mới hoặc gắn comment vào token sai sau khi chèn/xóa.

## 13. Lexer tăng dần với newline và indentation

DSL có thể dùng newline như dấu kết thúc câu lệnh hoặc dùng thụt lề để tạo cấu trúc. Khi đó, thay đổi một dòng có thể ảnh hưởng các token cấu trúc ở những dòng sau.

### Newline có ý nghĩa cú pháp

Nếu newline tạo token `NEWLINE`, chèn hoặc xóa newline có thể thay đổi ranh giới câu lệnh. Lexer phải cập nhật token newline và có thể cả token nối dòng hoặc kết thúc câu lệnh tự động.

### Indentation-sensitive lexer

Một lexer kiểu Python có thể duy trì stack độ sâu thụt lề:

~~~text
indentStack = [0]
~~~

Khi bắt đầu một dòng mới:

- Nếu độ thụt lề lớn hơn đỉnh stack, phát `INDENT` và đẩy mức mới.
- Nếu bằng đỉnh stack, không phát token thay đổi mức.
- Nếu nhỏ hơn, phát một hoặc nhiều `DEDENT` cho đến khi khớp mức đã có.
- Nếu mức thụt lề không khớp bất kỳ mức nào hợp lệ, báo lỗi theo quy tắc DSL.

Ví dụ:

~~~text
workflow Order {
    validate;
    if paid:
        approve;
    archive;
}
~~~

Nếu người dùng tăng thụt lề của `archive`, token `INDENT`/`DEDENT` có thể thay đổi và làm parser nhóm câu lệnh khác đi. Checkpoint cần giữ indentation stack, không chỉ mode bình thường.

### Hội tụ của indentation state

Ngay cả khi token văn bản ở một dòng giống cũ, indentation stack có thể khác do một dòng trước đó đã đổi. Lexer chỉ nên tái sử dụng suffix khi stack và mọi trạng thái ảnh hưởng token hóa đã trở lại giống trạng thái cũ.

## 14. Tài liệu chưa hoàn chỉnh trong lúc người dùng gõ

Trong editor, lexer thường phải xử lý chương trình đang ở trạng thái chưa hoàn chỉnh. Người dùng có thể vừa gõ dấu nháy mở, dấu ngoặc hoặc một từ khóa mà chưa gõ phần còn lại.

Ví dụ:

~~~text
let message = "Order
~~~

Đây có thể là chuỗi chưa đóng tại thời điểm hiện tại. Lexer nên tạo trạng thái hoặc token lỗi có thể phục hồi, thay vì dừng toàn bộ dịch vụ ngôn ngữ. Khi người dùng gõ thêm dấu nháy ở lần sửa sau, lexer sẽ cập nhật vùng bị ảnh hưởng.

### Token lỗi và trạng thái phục hồi

Lexer có thể biểu diễn:

- Token hợp lệ.
- Token lỗi chứa đoạn văn bản không hợp lệ.
- Trạng thái chưa hoàn chỉnh, chẳng hạn string chưa đóng.
- Diagnostic gắn với vị trí hoặc span thích hợp.

Chính sách cụ thể tùy lexer. Điều quan trọng là lexer phải tiếp tục được gọi sau lần sửa tiếp theo và không giữ state lỗi cũ khi nội dung đã được sửa.

### Error recovery

Một lexer có thể phục hồi bằng cách tiêu thụ ký tự không hợp lệ, phát token lỗi và tiếp tục từ một ranh giới có thể nhận diện. Khi incremental lexing, vùng phục hồi cũng cần được tính lại nếu edit thay đổi delimiter hoặc ký tự gây lỗi.

## 15. Cấu trúc dữ liệu lưu token và checkpoint

Một triển khai có thể dùng danh sách token cùng chỉ mục checkpoint. Ví dụ khái niệm:

~~~java
record Token(
    TokenKind kind,
    int startOffset,
    int endOffset,
    String lexeme
) {}

record LexerState(
    LexicalMode mode,
    int commentDepth,
    List<Integer> indentationStack
) {}

record Checkpoint(
    int sourceOffset,
    int tokenIndex,
    LexerState state,
    long documentVersion
) {}
~~~

Đây là mô hình minh họa. Trong hệ thống thực tế, `LexerState` có thể cần stack mode, delimiter chuỗi, trạng thái interpolation, trạng thái escape, thông tin dòng và các tham số khác. Cấu trúc state cần bất biến hoặc được sao chép an toàn khi tạo checkpoint; không nên để mọi checkpoint cùng tham chiếu đến một stack mutable đang tiếp tục thay đổi.

### Lưu state trước hay sau token?

Checkpoint có thể lưu state ngay trước token kế tiếp hoặc ngay sau token vừa quét. Cả hai cách đều dùng được, miễn là hợp đồng nhất quán. Ví dụ, nếu checkpoint lưu `stateBeforeNextToken`, khi restart lexer phải bắt đầu tại `sourceOffset` và xử lý token kế tiếp từ state đó.

### Snapshot của trạng thái

Nếu state chứa stack hoặc danh sách, checkpoint phải lưu snapshot độc lập hoặc một cấu trúc persistent. Nếu chỉ giữ tham chiếu đến stack mutable, các lần quét sau có thể làm thay đổi state của checkpoint cũ và khiến việc restart không còn đúng.

## 16. Pseudocode cho incremental lexing

Pseudocode dưới đây mô tả một edit đơn giản trên tài liệu có một vùng thay thế. Nó tập trung vào nguyên tắc, không phải API của một thư viện cụ thể.

~~~text
applyEdit(oldDocument, oldTokens, oldCheckpoints, edit):
    newDocument = oldDocument.apply(edit)

    restart = nearestSafeCheckpointBefore(
        oldCheckpoints,
        edit.start
    )

    newTokens = copyTokensBefore(oldTokens, restart.tokenIndex)
    lexer = Lexer(
        source = newDocument,
        offset = restart.offset,
        state = restart.state
    )

    while not lexer.atEnd():
        token = lexer.nextToken()
        newTokens.append(token)

        if lexer.isPastEditedRegion(edit):
            oldPosition = mapNewOffsetToOldOffset(
                lexer.currentOffset,
                edit
            )

            oldCheckpoint = findComparableCheckpoint(
                oldCheckpoints,
                oldPosition
            )

            if oldCheckpoint exists
               and lexer.state == oldCheckpoint.state
               and recentTokensMatch(
                   newTokens,
                   oldTokens,
                   edit
               ):
                suffix = reuseOldSuffix(
                    oldTokens,
                    oldCheckpoint.tokenIndex,
                    edit.offsetDelta
                )
                newTokens.appendAll(suffix)
                break

    newCheckpoints = rebuildAffectedCheckpoints(...)
    return TokenSnapshot(newDocument.version, newTokens, newCheckpoints)
~~~

Trong triển khai thật, `mapNewOffsetToOldOffset`, `findComparableCheckpoint` và `recentTokensMatch` phải xử lý chính xác edit map, ranh giới token, state và nhiều edit. Không nên sao chép pseudocode thành thuật toán mà chưa xác định hợp đồng của các hàm này.

### Vì sao cần so sánh chuỗi token gần nhất?

Một điểm trùng state tại một offset có thể chưa đủ nếu token vừa tạo ra đang thuộc một vùng bị thay đổi hoặc nếu lexer có lookahead chưa được phản ánh trong checkpoint. Một số triển khai so sánh một đoạn token liên tiếp cùng checkpoint state; số token hoặc chiều dài đoạn phụ thuộc thiết kế. Mục tiêu là chứng minh phần suffix cũ vẫn được token hóa theo đúng cùng trạng thái.

## 17. Ánh xạ offset sau chỉnh sửa

Khi nội dung thay đổi, offset của phần văn bản phía sau có thể dịch chuyển. Incremental lexer cần một edit map để so sánh token cũ và mới cũng như cập nhật span.

### Một edit

Với edit thay đoạn cũ `[a, b)` bằng `inserted`, đặt:

~~~text
delta = insertedLength - (b - a)
~~~

Ánh xạ vị trí cũ sang mới:

- `p < a`: vị trí không đổi.
- `p >= b`: vị trí mới là `p + delta`.
- `a <= p < b`: vị trí nằm trong vùng bị thay; không thể ánh xạ trực tiếp nếu không có quy tắc riêng.

Span nằm hoàn toàn trước edit có thể giữ nguyên. Span nằm hoàn toàn sau edit có thể dịch cả hai đầu. Span chồng lấn edit cần được tạo lại.

### Nhiều edit

Editor có thể gửi một hoặc nhiều thay đổi trong cùng một phiên cập nhật. Nếu có nhiều edit, cần áp dụng theo thứ tự và hệ tọa độ được giao thức quy định. Một số giao thức gửi các range tính trên nội dung trước mọi thay đổi; một số cơ chế gửi từng thay đổi tuần tự trên snapshot mới nhất. Lexer phải tuân theo đúng hợp đồng đầu vào.

### Không dùng offset cũ với văn bản mới

Token cũ thuộc version `v` không nên được cắt trực tiếp từ text buffer version `v+1` bằng offset cũ nếu edit đã làm dịch vị trí. Cần giữ snapshot cũ, ánh xạ offset hoặc dùng token slice gắn với phiên bản nguồn. Đây là một nguồn lỗi phổ biến khi tái sử dụng token.

## 18. Tổ chức bộ đệm văn bản

Hiệu quả của incremental lexing phụ thuộc cả cấu trúc lưu văn bản. Nếu chèn một ký tự vào đầu chuỗi lớn khiến toàn bộ chuỗi phải sao chép, chi phí buffer có thể lấn át lợi ích của lexer.

### String hoặc mảng ký tự liên tục

Ưu điểm là truy cập offset nhanh và đơn giản. Nhược điểm là chèn/xóa giữa tài liệu có thể phải sao chép phần lớn nội dung tùy runtime.

### Piece table

Piece table giữ nội dung gốc và nội dung chèn trong các buffer riêng, còn tài liệu hiện tại là danh sách các đoạn tham chiếu đến buffer. Chỉnh sửa có thể tạo hoặc tách piece thay vì sao chép toàn bộ văn bản.

### Rope

Rope biểu diễn văn bản bằng cây các đoạn chuỗi. Chèn/xóa có thể thực hiện bằng cách thay đổi một số nút trong cây thay vì di chuyển toàn bộ ký tự. Rope phù hợp với tài liệu lớn và chỉnh sửa thường xuyên, nhưng việc ánh xạ offset, dòng và cột cần được triển khai cẩn thận.

### Chọn cấu trúc dữ liệu

Không phải DSL nào cũng cần rope hoặc piece table. Với tệp nhỏ và ít chỉnh sửa, chuỗi đơn giản có thể đủ. Với editor chuyên nghiệp và tài liệu lớn, cấu trúc dữ liệu hỗ trợ chỉnh sửa hiệu quả có thể đáng đầu tư. Cần đo thời gian cập nhật tổng thể gồm buffer, lexer, parser và diagnostic.

## 19. Kết hợp lexer tăng dần với parser tăng dần

Lexer tăng dần chỉ cập nhật token. Parser cần nhận biết vùng token nào đã thay đổi để cập nhật cây cú pháp. Hai thành phần có thể được thiết kế độc lập nhưng phải thống nhất về version, token identity và phạm vi thay đổi.

### Token delta

Thay vì gửi lại toàn bộ danh sách token, lexer có thể cung cấp delta:

~~~text
TokenDelta
  oldTokenRange: [startIndex, endIndex)
  newTokens: [...]
  documentVersion: 42
~~~

Parser có thể dùng delta để xác định các node hoặc production có thể bị ảnh hưởng. Nếu parser không hỗ trợ cập nhật gia tăng, nó vẫn có thể phân tích lại toàn bộ token mới; lexer tăng dần vẫn có ích cho highlighting và các dịch vụ khác.

### Token không đổi không đồng nghĩa AST không đổi

Một chỉnh sửa có thể không đổi token kind nhưng làm thay đổi vị trí hoặc binding. Ví dụ đổi tên một định danh từ `limit` thành `cap` vẫn tạo token `IDENTIFIER`, nhưng parser có thể tạo cùng cấu trúc AST trong khi name resolution phải cập nhật symbol reference. Vì vậy, các tầng sau cần nhận biết cả nội dung token và vị trí/phiên bản phù hợp.

### Contextual keyword

Nếu một từ chỉ được xem là keyword trong một ngữ cảnh cú pháp cụ thể, lexer có thể phát token `IDENTIFIER` chung rồi parser diễn giải theo ngữ cảnh. Đây thường là cách giữ lexer đơn giản và giảm phụ thuộc ngữ nghĩa. Nếu lexer trực tiếp phân loại contextual keyword dựa trên parser state, incremental restart phải lưu hoặc khôi phục đủ context đó.

### Phạm vi invalidation

Parser có thể cần tái phân tích xa hơn vùng token thay đổi do cấu trúc cú pháp lồng nhau. Ví dụ, thêm dấu ngoặc mở có thể làm thay đổi cách nhóm biểu thức đến dấu ngoặc đóng tương ứng. Do đó, phạm vi incremental parsing không nhất thiết bằng phạm vi incremental lexing.

## 20. Lexer tăng dần và syntax highlighting

Syntax highlighter cần phân loại token để tô màu. Khi lexer cập nhật token, highlighter có thể chỉ cập nhật các vùng bị ảnh hưởng.

### Tái sử dụng token để tô màu

Nếu token kind và lexical state không đổi, vùng highlight tương ứng thường có thể được giữ. Nếu token kind đổi từ `IDENTIFIER` sang `STRING_TEXT`, highlighter phải cập nhật màu cho vùng đó và mọi phần bị ảnh hưởng.

### Semantic highlighting

Một số màu phụ thuộc vào phân giải tên và kiểu, không chỉ token kind. Ví dụ, hai token đều là identifier nhưng một token là biến cục bộ, token kia là tên kiểu. Lexer tăng dần không tự quyết định semantic highlighting; bộ phân giải và type checker cần phát delta riêng.

### Tokenization trong tài liệu chưa hoàn chỉnh

Editor có thể tô màu chuỗi chưa đóng, comment chưa đóng hoặc token chưa hoàn chỉnh theo một kiểu riêng. Khi người dùng tiếp tục gõ, lexer cập nhật state và highlighter cập nhật lại phần bị ảnh hưởng. Không nên để lỗi chưa hoàn chỉnh khiến toàn bộ highlighting biến mất.

## 21. Những cấu trúc làm phạm vi tái phân tích mở rộng

Một số cấu trúc có thể khiến một chỉnh sửa nhỏ ảnh hưởng đến phần lớn tài liệu:

| Cấu trúc | Chỉnh sửa | Phạm vi có thể bị ảnh hưởng |
|---|---|---|
| Chuỗi nhiều dòng | Xóa dấu nháy đóng | Từ vị trí sửa đến dấu nháy đóng tiếp theo hoặc EOF. |
| Comment nhiều dòng | Xóa `*/` | Có thể đến delimiter đóng tiếp theo hoặc EOF. |
| Comment lồng nhau | Thay đổi delimiter ở một cấp | Đến khi comment depth trở lại giá trị cũ. |
| String interpolation | Thay đổi `${`, `{` hoặc `}` | Có thể ảnh hưởng mode stack đến điểm cân bằng tiếp theo. |
| Indentation-sensitive syntax | Thay đổi thụt lề | Đến khi indentation stack hội tụ lại. |
| Heredoc/template | Thay đổi identifier delimiter | Đến delimiter kết thúc tương ứng. |
| Escape sequence | Chèn/xóa dấu `\\` | Có thể làm thay đổi cách hiểu ký tự kế tiếp và phần sau. |
| Multi-character operator | Chèn ký tự ở ranh giới | Các token lân cận có thể ghép hoặc tách. |

Đây là lý do incremental lexer cần dựa vào state và convergence thay vì giới hạn cứng việc quét lại ở một số dòng cố định.

## 22. Tối ưu checkpoint và token reuse

Checkpoint quá dày làm tăng bộ nhớ; checkpoint quá thưa làm tăng khoảng phải quét lại. Thiết kế cần cân bằng giữa chi phí lưu state và chi phí restart.

### Checkpoint theo dòng

Phù hợp với DSL có newline rõ ràng và state nhỏ. Có thể lưu ở mọi dòng hoặc mỗi một số dòng, tùy kích thước tài liệu và tần suất edit.

### Checkpoint theo token

Phù hợp khi dòng rất dài hoặc cấu trúc token hóa có nhiều điểm restart an toàn. Cần bảo đảm checkpoint không nằm giữa một token hoặc giữa một chuỗi escape chưa hoàn chỉnh.

### Checkpoint thích ứng

Hệ thống có thể tăng mật độ checkpoint quanh vùng thường xuyên chỉnh sửa hoặc trong vùng có cấu trúc nhiều dòng, nhưng phải bảo đảm state snapshot chính xác. Tối ưu thích ứng chỉ nên triển khai khi số liệu đo cho thấy lợi ích.

### Structural reuse

Khi suffix token được tái sử dụng, có thể dùng lại đối tượng token cũ nếu:

- Nội dung và loại token không đổi.
- State đầu vào tương ứng giống nhau.
- Token không phụ thuộc vào phiên bản nguồn theo cách không thể cập nhật.
- Span và trivia có thể được dịch hoặc biểu diễn qua source slice hợp lệ.
- Metadata gắn với token vẫn còn hiệu lực.

Nếu token giữ offset tuyệt đối bên trong đối tượng bất biến, việc dịch vị trí có thể yêu cầu tạo wrapper hoặc token mới. Một cách khác là lưu token theo offset tương đối trong segment, rồi đặt segment vào vị trí mới.

## 23. Nhiều chỉnh sửa và cập nhật liên tục

Trong khi lexer đang xử lý một snapshot, người dùng có thể tiếp tục sửa tài liệu. Hệ thống cần tránh để kết quả cũ ghi đè kết quả mới.

### Versioning

Mỗi lần thay đổi tài liệu tăng version. Kết quả lexer phải gắn với version đầu vào. Trước khi công bố kết quả, hệ thống kiểm tra version đó còn là version hiện hành hay không.

### Hủy tác vụ cũ

Nếu lexing trên tài liệu lớn mất nhiều thời gian và có edit mới, có thể hủy hoặc bỏ qua tác vụ cũ để ưu tiên snapshot mới nhất. Tuy nhiên, tác vụ bị hủy không được để lại token cache ở trạng thái nửa cũ nửa mới.

### Gộp chỉnh sửa

Khi có nhiều edit liên tiếp, hệ thống có thể gộp chúng thành một vùng thay đổi lớn hơn để giảm số lần restart. Việc gộp phải giữ đúng thứ tự và mapping offset. Không nên gộp các edit từ những version khác nhau nếu không có phép biến đổi range tương ứng.

### Kết quả lỗi thời

Diagnostic hoặc token delta thuộc version cũ phải được bỏ qua hoặc được đánh dấu rõ. Nếu không, editor có thể hiển thị lỗi ở vị trí không còn liên quan đến nội dung hiện tại.

## 24. Unicode và hệ tọa độ trong incremental lexing

Lexer có thể dùng byte offset, Unicode code point hoặc UTF-16 code unit. Edit range từ editor có thể dùng hệ tọa độ khác với lexer. Cần chuyển đổi chính xác trước khi tính restart, delta và span.

### Chỉnh sửa ký tự nhiều byte

Với UTF-8, một code point có thể chiếm nhiều byte. Không được đặt checkpoint ở giữa chuỗi byte của một code point. Nếu editor gửi UTF-16 position, cần ánh xạ sang byte boundary hợp lệ.

### Surrogate pair

Trong UTF-16, một code point ngoài BMP chiếm hai code unit. Nếu edit chỉ thay một nửa surrogate pair, văn bản có thể ở trạng thái Unicode không hợp lệ theo cách biểu diễn chuỗi của hệ thống. Lớp text buffer và giao thức editor cần xác định cách xử lý.

### Combining marks

Một ký tự hiển thị có thể gồm nhiều code point. Offset logic của lexer vẫn phải dựa trên đơn vị đã chọn, không dựa vào số ô hiển thị. Khi hiển thị lỗi, editor tự ánh xạ span sang vị trí hiển thị.

### Newline và tab

CRLF có hai code unit hoặc byte nhưng thường là một newline logic. Tab có thể chiếm nhiều ô hiển thị. Edit mapping và line index cần dùng cùng một quy ước để không làm lệch checkpoint hoặc diagnostic.

## 25. Lexer tăng dần trong DSL có nhiều nguồn

Một chương trình DSL có thể được tạo từ nhiều tệp, import hoặc include. Mỗi tài liệu nên có lexer state, token cache và version riêng.

Nếu một tệp được sửa:

- Lexer của tệp đó cập nhật token theo snapshot mới.
- Các tệp khác không cần tái phân tích từ vựng nếu nội dung không đổi.
- Parser hoặc name resolver có thể cần cập nhật các module phụ thuộc nếu khai báo hoặc interface thay đổi.
- Nếu lexer có directive làm thay đổi cách token hóa của tệp khác, hệ thống cần mô hình hóa phụ thuộc đó rõ ràng.

Ví dụ, một DSL có directive cấu hình chế độ từ vựng cho toàn module. Nếu thay đổi directive làm đổi quy tắc token hóa ở nhiều tệp, chỉ lex lại tệp chứa directive là chưa đủ. Thiết kế tốt thường cố gắng giữ cấu hình lexer ở cấp tài liệu hoặc module rõ ràng, tránh phụ thuộc ẩn.

## 26. Phân biệt incremental lexing với incremental parsing

Hai kỹ thuật thường đi cùng nhau nhưng giải quyết các bài toán khác nhau.

| Tiêu chí | Incremental lexing | Incremental parsing |
|---|---|---|
| Đầu vào | Văn bản nguồn và lexical state. | Chuỗi token và trạng thái/cấu trúc parser. |
| Đầu ra | Token mới và token được tái sử dụng. | CST/AST mới và các nút cú pháp được tái sử dụng. |
| Phụ thuộc chính | Delimiter, mode, escape, comment, indentation và ranh giới token. | Grammar, cấu trúc lồng nhau, precedence và trạng thái parser. |
| Phạm vi ảnh hưởng | Có thể kéo dài đến khi lexical state hội tụ. | Có thể kéo dài đến khi cấu trúc cú pháp hội tụ hoặc đến ranh giới production an toàn. |
| Lỗi thường gặp | Token kind hoặc span sai sau edit. | Cây cú pháp sai hoặc tái sử dụng node không hợp lệ. |

Ví dụ, đổi tên `total` thành `grandTotal` có thể chỉ thay token identifier ở lexer, nhưng parser có thể tái sử dụng gần như toàn bộ cấu trúc biểu thức. Name resolver vẫn cần cập nhật symbol references. Ngược lại, thêm một dấu ngoặc mở có thể khiến lexer không thay đổi nhiều token, nhưng parser phải tái phân tích một biểu thức hoặc block lớn hơn.

## 27. Độ phức tạp và hiệu năng

Với lexer toàn phần, chi phí một lần quét thường là (O(n)), trong đó `n` là độ dài văn bản. Với lexer tăng dần, chi phí một edit lý tưởng gần với kích thước vùng bị ảnh hưởng cộng khoảng tìm hội tụ:

~~~text
incremental cost ≈ restart distance + relexed region + convergence check
~~~

Nếu edit cục bộ và state nhanh chóng hội tụ, lượng công việc có thể nhỏ hơn đáng kể so với `O(n)`. Tuy nhiên, trường hợp xấu nhất vẫn là `O(n)` khi chỉnh sửa làm thay đổi lexical state đến cuối tệp.

### Các yếu tố ảnh hưởng hiệu năng

- Khoảng cách từ edit đến checkpoint gần nhất.
- Kích thước vùng cần lex lại trước khi hội tụ.
- Chi phí snapshot và so sánh lexical state.
- Cách lưu token và trivia.
- Cấu trúc text buffer và edit mapping.
- Mật độ checkpoint.
- Số lượng tài liệu và version đang được giữ.
- Chi phí thông báo token delta cho parser/editor.

### Đo lường đúng

Không nên chỉ đo thời gian `nextToken()`. Cần đo toàn bộ đường đi từ nhận edit đến khi token delta và diagnostic có thể được hiển thị. Các chỉ số hữu ích gồm:

- Số ký tự được quét lại.
- Số token được tạo mới.
- Số token được tái sử dụng.
- Số checkpoint được truy vấn hoặc tạo lại.
- Thời gian trung bình và percentile cao của cập nhật.
- Bộ nhớ token cache và checkpoint.
- Tỷ lệ edit phải quét đến EOF.

Đo trên các tài liệu thực tế và các kiểu chỉnh sửa phổ biến giúp quyết định có cần tối ưu phức tạp hơn hay không.

## 28. Kiểm thử tính đúng đắn

Lexer tăng dần cần được kiểm thử để bảo đảm kết quả luôn tương đương với lexer toàn phần trên cùng snapshot mới. Đây là cách kiểm chứng quan trọng nhất vì thuật toán tái sử dụng token có thể tạo lỗi khó nhận ra.

### Differential testing với full lexer

Quy trình:

1. Tạo văn bản ban đầu và chạy full lexer để có token chuẩn.
2. Áp dụng một edit bất kỳ lên văn bản.
3. Chạy incremental lexer với token cache và checkpoint cũ.
4. Chạy full lexer độc lập trên toàn bộ văn bản mới.
5. So sánh chuỗi token, lexeme, span, trivia, lexical state và diagnostic liên quan.
6. Lặp lại với nhiều edit và nhiều loại cấu trúc.

Kết quả incremental phải tương đương với full lexer theo hợp đồng đã chọn. Nếu token ID khác nhau do tái sử dụng hoặc cấp phát mới, so sánh nên tập trung vào nội dung và ngữ nghĩa token, không bắt buộc ID nội bộ giống nhau.

### Property-based testing

Sinh văn bản DSL hợp lệ hoặc gần hợp lệ, sau đó sinh ngẫu nhiên các thao tác chèn, xóa và thay thế. Sau mỗi edit, so sánh kết quả incremental với full lexing. Cách này có thể tìm được các trường hợp ranh giới khó như delimiter nhiều ký tự, escape và Unicode.

### Các nhóm ca kiểm thử

| Nhóm | Ví dụ |
|---|---|
| Chỉnh sửa trong token | Đổi một ký tự của identifier hoặc number. |
| Ranh giới token | Chèn/xóa ký tự làm ghép `=`, `==`, `/*`, `*/`. |
| Chuỗi | Thêm/xóa dấu nháy, escape, string nhiều dòng. |
| Comment | Mở/đóng comment, comment lồng nhau. |
| Interpolation | Thêm/xóa `${`, `{` hoặc `}`. |
| Indentation | Thay tab, spaces hoặc mức thụt lề. |
| Newline | LF, CRLF, CR, chèn/xóa newline cuối tệp. |
| Unicode | UTF-8 nhiều byte, surrogate pair, combining marks. |
| EOF | Xóa token cuối, thêm delimiter chưa đóng, thêm whitespace cuối. |
| Nhiều edit | Chèn và xóa ở nhiều vị trí trong cùng version update. |
| Versioning | Bỏ kết quả cũ khi snapshot mới đã được tạo. |
| Error recovery | Sửa dần token lỗi thành token hợp lệ. |

### Kiểm thử state và checkpoint

Ngoài so sánh token cuối, nên kiểm tra state tại các checkpoint tương ứng. Một lỗi state có thể chưa biểu hiện ngay ở token kế tiếp nhưng làm sai token ở các dòng xa hơn.

## 29. Kiểm thử hiệu năng và trường hợp xấu

Một lexer tăng dần có thể đúng nhưng không đem lại lợi ích nếu luôn quét lại phần lớn tài liệu. Cần đo các trường hợp đại diện:

- Đổi một ký tự trong identifier ngắn.
- Chèn một dòng ở đầu, giữa và cuối tệp.
- Thay đổi delimiter của string nhiều dòng.
- Xóa delimiter comment gần đầu tệp.
- Chỉnh sửa trong tệp có indentation-sensitive syntax.
- Thay đổi nhiều vùng trong một lần đồng bộ editor.
- Gõ liên tục với tốc độ cao khi tác vụ lex trước chưa hoàn tất.

Đặc biệt, cần kiểm tra trường hợp không hội tụ đến EOF. Hệ thống nên vẫn đúng và không rơi vào vòng lặp hoặc giữ token cache hỏng, dù hiệu năng không thể tốt như edit cục bộ.

## 30. Những lỗi thiết kế thường gặp

**Chỉ lex lại đoạn văn bản được chèn.** Token có thể ghép qua ranh giới edit, và state có thể ảnh hưởng đến phần suffix. Cần restart từ checkpoint an toàn.

**Không lưu lexical state trong checkpoint.** Lexer có thể khởi động lại trong chế độ bình thường dù thực tế đang ở trong string hoặc comment.

**Dùng checkpoint giữa token hoặc giữa một đơn vị mã Unicode.** Việc restart có thể tạo lexeme sai hoặc chuỗi byte không hợp lệ.

**Dừng khi gặp một token giống token cũ.** Cần so sánh cả state và đủ ngữ cảnh để chứng minh suffix cũ còn hợp lệ.

**So sánh offset cũ và mới trực tiếp.** Edit có thể dịch vị trí của toàn bộ suffix. Cần edit map hoặc ánh xạ offset.

**Tái sử dụng token có span lỗi thời.** Token cũ có thể trỏ đến văn bản khác sau khi buffer thay đổi. Cần cập nhật span hoặc dùng source slice gắn với snapshot.

**Không xử lý multi-line constructs.** Xóa dấu nháy hoặc comment delimiter có thể làm thay đổi token đến cuối tệp.

**Bỏ qua trivia.** Comment và whitespace có thể cần cho formatter, editor hoặc quy tắc newline; token cache phải cập nhật chúng đúng cách.

**Trộn lexical state với ngữ nghĩa parser mà không có hợp đồng.** Nếu lexer phụ thuộc parser context, checkpoint phải lưu đủ trạng thái hoặc kiến trúc cần tách contextual interpretation sang parser.

**Để kết quả cũ ghi đè kết quả mới.** Cần gắn version và bỏ kết quả lỗi thời.

**Chỉ kiểm thử ASCII và edit đơn giản.** Unicode, CRLF, escape và delimiter lồng nhau thường là nơi phát sinh lỗi vị trí và state.

## 31. Quy trình triển khai lexer tăng dần

Một quy trình thực tế có thể gồm:

1. **Đặc tả token và state:** liệt kê token, delimiter, chế độ lexer, comment, string, interpolation, indentation và quy tắc newline.
2. **Xây dựng full lexer làm chuẩn:** bảo đảm lexer toàn phần có thể xử lý cả văn bản chưa hoàn chỉnh theo chính sách đã chọn.
3. **Định nghĩa snapshot và version:** mỗi tài liệu có nội dung nhất quán, ID và version rõ ràng.
4. **Định nghĩa edit model:** xác định range, thứ tự edit, hệ tọa độ và cách tính delta.
5. **Thiết kế checkpoint:** chọn vị trí checkpoint và cấu trúc lexical state snapshot đầy đủ.
6. **Triển khai restart:** tìm checkpoint an toàn trước edit và khởi động lexer với state tương ứng.
7. **Triển khai convergence:** so sánh token và state mới với token cũ đã ánh xạ vị trí.
8. **Tái sử dụng suffix:** chỉ ghép lại phần cũ sau khi chứng minh hội tụ; cập nhật span, trivia và metadata.
9. **Tích hợp token delta:** thông báo vùng token thay đổi cho parser, highlighter và các dịch vụ phụ thuộc.
10. **Kiểm thử đối chiếu:** so sánh incremental với full lexer sau các edit đơn và chuỗi edit ngẫu nhiên.
11. **Đo hiệu năng:** đo thời gian, số ký tự quét lại, token reuse, bộ nhớ và trường hợp đến EOF.
12. **Xử lý version và hủy tác vụ:** bảo đảm kết quả chỉ được công bố cho snapshot còn hiện hành.

## 32. Ví dụ kiến trúc lexer tăng dần cho DSL chính sách

Giả sử DSL có các cấu trúc:

~~~text
policy OrderPolicy {
    // rule comment
    when order.payment.status == ACCEPTED then approveOrder;
}
~~~

Lexer hỗ trợ identifier, keyword, toán tử, comment một dòng, string và block. Kiến trúc có thể gồm:

~~~text
TextBuffer
  └── DocumentSnapshot(version, lineIndex)

IncrementalLexer
  ├── TokenCache(version, tokens)
  ├── CheckpointIndex(offset, state, tokenIndex)
  ├── EditMapper
  ├── RestartSelector
  ├── Scanner
  └── ConvergenceDetector

Output
  ├── TokenDelta
  ├── NewCheckpointIndex
  └── LexicalDiagnostics
~~~

Khi người dùng đổi `ACCEPTED` thành `DECLINED`, lexer nhận edit, tìm checkpoint trước token, quét lại và xác nhận state bình thường ở cuối token. Nếu các token tiếp theo và state tương ứng khớp với suffix cũ, nó tái sử dụng phần còn lại. Parser sau đó cập nhật cây cú pháp; name resolver và semantic analyzer cập nhật các thông tin phụ thuộc.

Nếu người dùng xóa `//` trước `rule comment`, phần văn bản sau đó có thể trở thành token thay vì comment. Lexer phải quét lại đến newline để xác định trạng thái và token mới. Nếu DSL dùng comment block kéo dài nhiều dòng, phạm vi có thể dài hơn.

## 33. Ranh giới giữa lexer tăng dần và phân tích ngữ nghĩa

Lexer nên chịu trách nhiệm nhận diện token dựa trên quy tắc từ vựng và trạng thái từ vựng. Một số DSL có contextual keyword hoặc token phụ thuộc kiểu dữ liệu, nhưng đưa quá nhiều logic ngữ nghĩa vào lexer sẽ làm incremental lexing phức tạp.

Ví dụ, từ `order` có thể là identifier ở mọi vị trí, còn việc nó đại diện cho biến, kiểu hay tên thực thể được quyết định trong bước phân giải tên. Cách tách này cho phép lexer tái sử dụng token khi chỉ có thay đổi khai báo ở một scope, trong khi name resolver cập nhật binding.

Nếu từ khóa chỉ có ý nghĩa đặc biệt trong một production, có thể lexer phát token identifier và parser diễn giải nó theo ngữ cảnh. Nếu lexer thực sự cần context từ parser, context đó phải là một phần của trạng thái restart và convergence. Thiết kế cần tránh trạng thái ẩn khiến cùng văn bản và cùng lexical state tạo token khác nhau.

## 34. Kết quả cần có khi thiết kế lexer tăng dần

Một thiết kế incremental lexer đầy đủ thường cần các đầu ra sau:

- **Đặc tả từ vựng:** token, longest-match, comment, string, escape, interpolation, newline và indentation.
- **Mô hình lexical state:** các mode và stack cần thiết để restart chính xác.
- **Mô hình checkpoint:** vị trí, token index, state snapshot và version.
- **Mô hình edit:** range, offset mapping, thứ tự cập nhật và quy tắc Unicode.
- **Thuật toán convergence:** điều kiện so sánh token, state và suffix để tái sử dụng.
- **Token cache:** cách lưu lexeme, span, trivia, metadata và identity.
- **Cơ chế versioning:** bỏ kết quả cũ và xử lý các chỉnh sửa liên tiếp.
- **Giao diện token delta:** cách thông báo thay đổi cho parser và editor.
- **Bộ kiểm thử:** differential, property-based, Unicode, multi-line, error recovery và trường hợp xấu.
- **Chỉ số hiệu năng:** lượng văn bản quét lại, token reuse, latency và bộ nhớ.

Lexer tăng dần giúp DSL phản hồi nhanh trong editor bằng cách tái phân tích phần thực sự bị ảnh hưởng và tái sử dụng kết quả còn hợp lệ. Để làm được điều đó, lexer phải lưu trạng thái đầy đủ tại checkpoint, xử lý chính xác vị trí sau edit và chỉ dừng khi trạng thái mới hội tụ với trạng thái cũ. Các cấu trúc nhiều dòng, comment, string interpolation, indentation và Unicode có thể khiến phạm vi tái phân tích mở rộng; đây là hệ quả của ngữ nghĩa từ vựng cần được bảo toàn. Khi incremental lexer luôn cho kết quả tương đương với full lexer trên cùng snapshot, đồng thời được kiểm thử bằng các chuỗi chỉnh sửa thực tế, nó trở thành nền tảng đáng tin cậy cho parser tăng dần, syntax highlighting và các dịch vụ ngôn ngữ trong IDE.
