# Cập nhật tăng dần

Language Server cung cấp các dịch vụ ngôn ngữ cho trình soạn thảo như phân tích cú pháp, chẩn đoán lỗi, gợi ý hoàn thành, điều hướng đến khai báo, tìm tham chiếu, tô màu cú pháp và thông tin khi rê chuột. Người dùng thường thay đổi tài liệu liên tục: thêm một ký tự, xóa một biểu thức, đổi tên biến hoặc dán một khối mã. Nếu server phải phân tích lại toàn bộ workspace sau mỗi lần sửa, phản hồi có thể chậm và tiêu tốn tài nguyên. **Cập nhật tăng dần** (*incremental updates*) là cách xử lý chỉ phần dữ liệu hoặc kết quả bị ảnh hưởng bởi thay đổi, đồng thời tái sử dụng phần còn hợp lệ.

Ví dụ, một file DSL có 20.000 dòng chứa nhiều entity và workflow. Người dùng sửa tên một thuộc tính trong một rule ở dòng 8.500. Language Server cần nhận chính xác phần văn bản đã thay đổi, cập nhật snapshot tài liệu, phân tích lại vùng cú pháp liên quan, xác định các symbol và diagnostic bị ảnh hưởng, rồi công bố kết quả cho đúng phiên bản tài liệu. Các module không phụ thuộc vào thay đổi đó có thể tiếp tục dùng kết quả phân tích đã có.

Cập nhật tăng dần không chỉ là nhận một đoạn text edit thay vì toàn bộ file. Nó là một chiến lược xuyên suốt: đồng bộ tài liệu, quản lý version, cấu trúc buffer, lexer/parser, semantic analysis, dependency graph, cache, diagnostics và các tính năng editor. Một hệ thống chỉ cập nhật text buffer nhưng vẫn chạy lại mọi phân tích từ đầu chưa tận dụng đầy đủ lợi ích của incremental processing.

## 1. Cập nhật tăng dần là gì?

Cập nhật tăng dần là quá trình áp dụng một hoặc nhiều thay đổi lên trạng thái hiện tại, sau đó chỉ tính lại những kết quả có thể bị ảnh hưởng. Trạng thái cũ được tái sử dụng ở những vùng mà hệ thống xác định vẫn hợp lệ.

Trong Language Server, có thể có nhiều cấp cập nhật:

- **Incremental document synchronization:** client gửi những đoạn văn bản đã thay đổi thay vì gửi toàn bộ tài liệu.
- **Incremental text storage:** buffer áp dụng edit mà không sao chép toàn bộ chuỗi lớn.
- **Incremental lexing:** lexer chỉ quét lại vùng bị ảnh hưởng và tiếp tục từ checkpoint an toàn.
- **Incremental parsing:** parser cập nhật cây cú pháp, giữ lại các subtree không đổi.
- **Incremental semantic analysis:** chỉ phân giải tên, suy luận kiểu và kiểm tra những phần phụ thuộc vào thay đổi.
- **Incremental diagnostics:** tính lại và công bố những chẩn đoán bị ảnh hưởng.
- **Incremental editor features:** cập nhật outline, folding, semantic tokens, completion context và symbol index theo version mới.

Các cấp này có quan hệ phụ thuộc. Một text edit có thể làm token thay đổi; token thay đổi có thể làm AST thay đổi; AST thay đổi có thể ảnh hưởng symbol table và các file tham chiếu đến symbol đó.

### So sánh full update và incremental update

| Cách xử lý | Dữ liệu client gửi | Công việc server | Đặc điểm |
|---|---|---|---|
| Full synchronization | Toàn bộ nội dung tài liệu sau mỗi thay đổi | Thay snapshot rồi thường phân tích lại toàn bộ | Đơn giản, dễ phục hồi nhưng tốn băng thông và CPU. |
| Incremental synchronization | Các range và nội dung thay thế | Áp dụng edit lên snapshot hiện tại | Giảm dữ liệu truyền, cần quản lý range và version chính xác. |
| Incremental analysis | Thường vẫn nhận edit theo giao thức | Chỉ tính lại vùng và dependency bị ảnh hưởng | Giảm latency phân tích, cần parser và dependency tracking phù hợp. |

Full synchronization và incremental analysis là hai lựa chọn ở hai tầng khác nhau. Một server có thể nhận toàn bộ document nhưng vẫn phân tích tăng dần; ngược lại, server có thể nhận edit nhỏ nhưng sau đó parse lại toàn bộ file.

## 2. Vì sao Language Server cần cập nhật tăng dần?

### Phản hồi nhanh khi gõ

Editor có thể gửi thay đổi sau mỗi thao tác nhập liệu. Nếu mỗi ký tự kích hoạt parse, type checking và workspace scan toàn diện, người dùng sẽ thấy completion, diagnostics hoặc hover xuất hiện trễ.

### Tài liệu và workspace lớn

Một dự án DSL có thể gồm hàng trăm hoặc hàng nghìn file. Một edit trong một file thường chỉ ảnh hưởng một phần dependency graph. Phân tích tăng dần giúp giới hạn công việc.

### Giảm sử dụng CPU và bộ nhớ

Tái sử dụng token, AST, symbol và kết quả semantic hợp lệ giúp giảm allocation và garbage collection. Điều này quan trọng với Language Server chạy nền trong suốt phiên làm việc.

### Giữ trạng thái editor ổn định

Outline, folding, selection, diagnostics và semantic highlighting có thể được cập nhật theo node identity thay vì tạo lại mọi thứ. Người dùng ít gặp hiện tượng cây outline nhấp nháy hoặc mất trạng thái mở rộng.

### Hỗ trợ nhiều tài liệu đồng thời

Một server có thể xử lý nhiều file đang mở, nhiều workspace folder và nhiều request không đồng bộ. Cập nhật tăng dần giúp quản lý tải tốt hơn, miễn là version và dependency được kiểm soát chính xác.

## 3. Document synchronization trong Language Server Protocol

Language Server Protocol (LSP) định nghĩa cách client và server đồng bộ nội dung tài liệu. Client thường gửi thông báo khi tài liệu được mở, thay đổi, lưu hoặc đóng.

Các thông báo văn bản quan trọng gồm:

- `textDocument/didOpen`: tài liệu được mở và nội dung hiện tại được cung cấp.
- `textDocument/didChange`: nội dung tài liệu thay đổi.
- `textDocument/didSave`: tài liệu được lưu; có thể kèm nội dung tùy cấu hình.
- `textDocument/didClose`: tài liệu được đóng.

### didOpen

Khi nhận `didOpen`, server tạo document state cho URI và version do client cung cấp, lưu nội dung văn bản và bắt đầu phân tích. Với tài liệu đã mở, server thường xem nội dung do client quản lý là nguồn mới nhất, kể cả khi file trên đĩa chưa được lưu.

### didChange

`didChange` mang version mới và một danh sách `contentChanges`. Tùy kiểu đồng bộ đã thương lượng, mỗi change có thể chứa toàn bộ văn bản hoặc một range cùng nội dung thay thế.

Trong chế độ incremental, server áp dụng các thay đổi theo đúng thứ tự được gửi. Mỗi change tiếp theo được hiểu trên trạng thái tài liệu sau khi các change trước đó trong cùng thông báo đã được áp dụng. Nếu áp dụng sai thứ tự hoặc dùng range trên snapshot khác, nội dung server có thể lệch client.

### didSave

`didSave` báo rằng tài liệu đã được lưu. Nó không thay thế `didChange`: thay đổi trong editor có thể đã được gửi trước khi người dùng lưu. Server có thể dùng save event để chạy công việc cần nội dung bền vững, chẳng hạn validation toàn dự án hoặc build check.

### didClose

Khi tài liệu đóng, server giải phóng trạng thái document mở hoặc chuyển sang đọc lại nội dung từ filesystem theo chính sách. Nếu tài liệu có thay đổi chưa lưu, server cần phân biệt snapshot editor cuối cùng với file trên đĩa.

## 4. Thương lượng kiểu đồng bộ

Trong LSP, server công bố khả năng đồng bộ tài liệu bằng `textDocumentSync`. Các kiểu đồng bộ văn bản cơ bản gồm:

| Kiểu | Ý nghĩa |
|---|---|
| `None` | Không nhận đồng bộ thay đổi nội dung qua cơ chế text document sync. |
| `Full` | Client gửi toàn bộ nội dung tài liệu sau thay đổi. |
| `Incremental` | Client gửi các đoạn thay đổi có range. |

Server cần công bố kiểu hỗ trợ trong `initialize` response. Client sử dụng khả năng đã thương lượng để quyết định nội dung `didChange` gửi lên.

### Full sync không phải là lựa chọn sai

Với DSL nhỏ, parser rất nhanh hoặc server chưa có incremental parser, full sync có thể là giải pháp phù hợp và ít lỗi hơn. Có thể triển khai full sync trước rồi nâng cấp tầng phân tích sau khi có số liệu cho thấy cần thiết.

### Incremental sync yêu cầu snapshot nhất quán

Khi dùng incremental sync, server phải có đúng nội dung nền để áp dụng edit. Nếu server bỏ lỡ một notification hoặc version bị nhảy không thể giải thích, các range tiếp theo có thể không còn hợp lệ. Cần có chiến lược phát hiện mất đồng bộ và yêu cầu client gửi lại toàn bộ nội dung khi có cơ chế phù hợp.

### Đồng bộ nội dung không đồng nghĩa đồng bộ phân tích

Server có thể áp dụng text edit ngay lập tức, nhưng phân tích cú pháp và semantic chạy bất đồng bộ. Vì thế document state và analysis state cần được quản lý riêng, có version liên kết với nhau.

## 5. Cấu trúc của một text change

Một incremental content change thường chứa:

- `range`: vị trí bắt đầu và kết thúc của đoạn bị thay thế.
- `text`: nội dung mới thay thế range đó.
- `rangeLength`: trường legacy/deprecated trong LSP; không nên dựa vào nó thay cho range và document state.

Ví dụ, tài liệu hiện tại:

~~~text
entity Order {
    total: Money;
}
~~~

Người dùng đổi `Money` thành `Decimal` bằng một edit chỉ bao trùm từ ký tự đầu đến ký tự cuối của tên kiểu. Server thay đúng đoạn đó trong snapshot.

### Range là nửa mở

Range được biểu diễn bằng start và end; vị trí kết thúc không nằm trong đoạn bị thay thế. Quy ước này cho phép biểu diễn đoạn rỗng để chèn text và giúp tính độ dài bằng hiệu giữa end và start trong cùng hệ tọa độ.

### Chèn, xóa và thay thế

- **Insert:** range rỗng tại một vị trí, text chứa nội dung mới.
- **Delete:** range không rỗng, text rỗng.
- **Replace:** range không rỗng, text chứa nội dung thay thế.

### Nhiều change trong một notification

Nếu một notification chứa nhiều content change, server áp dụng theo thứ tự trong mảng. Sau mỗi change, snapshot hiện tại thay đổi; do đó range của change tiếp theo được hiểu trên nội dung đã cập nhật bởi change trước đó. Không được gom tất cả range rồi áp dụng ngược hoặc song song nếu điều đó không bảo toàn thứ tự semantics của giao thức.

## 6. Vị trí dòng, cột và encoding

LSP position có dòng và ký tự, bắt đầu từ 0. Đơn vị của `character` phụ thuộc position encoding đã thương lượng. Nếu không thương lượng encoding khác theo phiên bản giao thức hỗ trợ, UTF-16 là mặc định truyền thống.

Các đơn vị thường gặp:

- UTF-8 code unit: byte trong chuỗi UTF-8.
- UTF-16 code unit: đơn vị mã UTF-16.
- Unicode code point: giá trị mã Unicode.

Chúng không luôn có cùng độ dài. Một ký tự ngoài BMP chiếm hai UTF-16 code unit nhưng một code point; trong UTF-8 có thể chiếm bốn byte.

### Ví dụ Unicode

Giả sử dòng chứa:

~~~text
let symbol = "😀"; let total: Money;
~~~

Nếu server tính offset bằng UTF-8 byte nhưng client gửi UTF-16 position, vị trí `total` có thể bị lệch sau emoji. Các lỗi như vậy thường không xuất hiện trong test chỉ dùng ASCII.

### Chuyển đổi tọa độ

Một source manager có thể cung cấp các hàm:

~~~text
positionToOffset(line, character, encoding)
offsetToPosition(offset, encoding)
~~~

Nên tập trung logic chuyển đổi trong một module thay vì để lexer, parser và LSP adapter tự tính riêng. Cần kiểm thử CRLF, LF, tab, surrogate pair và ký tự kết hợp.

### Line index

SourceText có thể lưu offset bắt đầu từng dòng. Khi edit thay đổi newline, line index cần được cập nhật cho vùng liên quan. Tìm dòng bằng binary search trên line starts có thể nhanh hơn quét từ đầu file cho mỗi request.

## 7. Document version và quản lý snapshot

Mỗi tài liệu mở trong client có version. Server cần gắn nội dung và mọi kết quả phân tích với version tương ứng.

Một trạng thái tài liệu có thể gồm:

~~~text
DocumentState
  uri
  languageId
  clientVersion
  textSnapshot
  lineIndex
  lastAppliedChange
  analysisVersion
  parseResult
  semanticResult
~~~

`clientVersion` là version nội dung mà server đã áp dụng. `analysisVersion` là version của snapshot mà kết quả parse/semantic hiện tại đại diện. Hai version có thể khác nhau trong lúc phân tích nền đang chạy.

### Không dùng một mutable string cho mọi tác vụ

Nếu parser đang đọc nội dung trong khi một thread khác sửa cùng chuỗi hoặc buffer, parser có thể thấy snapshot nửa cũ nửa mới. Dùng immutable snapshot, copy-on-write hoặc versioned buffer để mỗi tác vụ phân tích nhìn thấy một trạng thái nhất quán.

### Version tăng nhưng nội dung có thể giống

Undo/redo hoặc thay đổi rồi hoàn tác có thể tạo version mới với nội dung giống một snapshot trước. Version xác định thứ tự trạng thái theo giao thức, không nhất thiết là hash nội dung.

### Phát hiện version không liên tục

LSP version là số nguyên do client cung cấp và server cần áp dụng chính sách phù hợp với client. Nếu nhận change không thể áp dụng lên snapshot hiện tại, server phải tránh tiếp tục phân tích trên nội dung sai. Có thể đánh dấu document out-of-sync và chờ full content hoặc một cơ chế resynchronization.

## 8. Text buffer hỗ trợ edit hiệu quả

Nếu mỗi edit được áp dụng bằng cách tạo một chuỗi mới có toàn bộ nội dung, chi phí có thể lớn với file dài và nhiều thao tác. Các cấu trúc text buffer hỗ trợ chèn/xóa hiệu quả hơn.

### String đơn giản

Với tài liệu nhỏ, immutable string và thay thế chuỗi có thể đủ đơn giản. Chi phí copy toàn bộ buffer thường không đáng kể nếu file ngắn và số lần cập nhật thấp.

### Rope

Rope biểu diễn văn bản bằng cây các đoạn chuỗi. Chèn hoặc xóa tại một vị trí có thể thay đổi một số node thay vì dịch chuyển toàn bộ phần sau. Rope phù hợp với editor buffer lớn và nhiều edit.

### Piece table

Piece table giữ buffer gốc và buffer chứa nội dung thêm, còn document là danh sách các đoạn tham chiếu đến hai buffer. Chèn/xóa thay đổi danh sách piece, thường tránh copy phần lớn nội dung.

### Gap buffer

Gap buffer giữ một vùng trống tại vị trí edit gần nhất. Chèn/xóa quanh con trỏ có thể nhanh; di chuyển gap xa có thể tốn chi phí. Nó phù hợp với một số editor text buffer.

### Lựa chọn cấu trúc

Language Server có thể dùng text document abstraction của thư viện LSP thay vì tự triển khai buffer phức tạp. Nếu tự quản lý, cần cân nhắc:

- Kích thước tài liệu.
- Tần suất và vị trí edit.
- Chi phí tạo snapshot cho parser.
- Cách tính line index.
- Khả năng lấy substring và ánh xạ offset.
- Độ phức tạp của implementation và kiểm thử.

## 9. Incremental lexing

Lexer chuyển văn bản thành token. Khi một edit chỉ ảnh hưởng một vùng, lexer có thể bắt đầu lại gần vùng đó và tái sử dụng token phía trước hoặc phía sau nếu trạng thái từ vựng hội tụ.

### Vì sao cần lexical state?

Tokenization phụ thuộc ngữ cảnh. Một ký tự `/` có thể bắt đầu comment hoặc là toán tử; dấu nháy có thể mở string; trong template string, `${` có thể chuyển sang chế độ expression. Lexer cần biết trạng thái tại điểm restart.

Một checkpoint có thể lưu:

~~~text
LexerCheckpoint
  offset
  tokenIndex
  lexicalMode
  delimiterStack
  interpolationDepth
  indentationState
~~~

### Restart trước edit

Khi edit xảy ra, lexer tìm checkpoint an toàn đứng trước vùng thay đổi. Không nên restart tùy tiện giữa một string hoặc comment nhiều dòng nếu checkpoint không chứa đủ state để tiếp tục đúng.

### Lex lại đến điểm hội tụ

Sau khi quét vùng mới, lexer có thể dừng khi token mới và lexical state khớp với token/state cũ tại một ranh giới phù hợp. Từ đó có thể tái sử dụng suffix token cũ với offset được ánh xạ sang snapshot mới.

Chỉ so sánh text token là chưa đủ. Hai token giống nhau nhưng lexer state khác có thể khiến cách phân loại token tiếp theo khác nhau.

### Ví dụ

Nếu người dùng sửa một identifier trong một dòng code thông thường, lexer có thể chỉ cần quét lại token ở dòng đó và tiếp tục đến điểm hội tụ. Nếu người dùng thêm dấu `/*` trước một vùng dài, comment có thể nuốt nhiều dòng; lexer phải quét lại đến dấu `*/` hoặc EOF vì tokenization của phần sau thay đổi.

### Trivia

Whitespace và comment có thể được giữ như trivia gắn với token hoặc lưu riêng. Nếu outline hoặc formatter cần comment tài liệu, incremental lexer không được loại bỏ thông tin trivia mà các tính năng đó cần.

## 10. Incremental parsing

Parser biến token thành CST hoặc AST. Incremental parser cố gắng cập nhật cây hiện tại sau token edit thay vì parse lại toàn bộ tài liệu.

### Cây cú pháp bất biến

Một chiến lược là dùng immutable syntax tree. Khi một vùng thay đổi, parser tạo node mới cho vùng đó và các ancestor cần thiết; subtree không đổi được chia sẻ với cây mới. Cách này giúp snapshot cũ vẫn an toàn cho tác vụ đang chạy.

### Reparse vùng bị ảnh hưởng

Parser có thể xác định node nhỏ nhất bao trùm edit và parse lại node đó. Nếu cấu trúc mới không còn khớp với node cha, phạm vi reparse được mở rộng lên ancestor.

### Điểm hội tụ cú pháp

Nếu phần token phía sau edit giống trước và parser state tại ranh giới cũng giống, parser có thể tái sử dụng các node sau đó. Parser state có thể bao gồm grammar state, context, scope nesting hoặc loại block đang mở.

### Error recovery

Trong editor, tài liệu thường chưa hoàn chỉnh. Parser cần tạo cây một phần và phục hồi sau lỗi để outline và diagnostics vẫn hữu ích. Khi edit sửa lỗi, parser cần loại bỏ node lỗi cũ và cập nhật đúng vùng cấu trúc.

### AST và CST

CST giữ nhiều chi tiết cú pháp hơn và thường phù hợp với incremental editing, formatter và source-preserving operations. AST đơn giản hơn cho semantic analysis. Hệ thống có thể giữ CST làm nền và tạo AST/semantic model từ các node liên quan.

## 11. Incremental semantic analysis

Parse tree chỉ mô tả cấu trúc cú pháp. Language Server còn cần phân giải tên, kiểm tra kiểu, kiểm tra reference và xây dựng symbol index. Các bước này có thể phụ thuộc vào nhiều phần của workspace.

### Thay đổi cục bộ

Nếu người dùng sửa literal trong một biểu thức, có thể chỉ cần suy luận lại kiểu và diagnostics của biểu thức chứa nó cùng các ancestor liên quan.

### Thay đổi khai báo

Nếu người dùng đổi tên một entity hoặc thuộc tính public, nhiều file tham chiếu đến symbol đó có thể bị ảnh hưởng. Phạm vi phân tích cần mở rộng theo dependency graph.

### Dependency graph

Một semantic dependency graph có thể ghi nhận:

- File A phụ thuộc vào public symbol của file B.
- Expression X phụ thuộc vào type của variable Y.
- Rule P phụ thuộc vào action descriptor Q.
- Module M phụ thuộc vào schema S.
- Outline node N phụ thuộc vào AST subtree T.

Khi một node thay đổi, server truy ngược dependency để xác định các kết quả cần invalidation.

### Fine-grained và coarse-grained dependency

Fine-grained dependency giảm việc tính lại nhưng tốn chi phí theo dõi. Coarse-grained dependency như “file A phụ thuộc file B” dễ triển khai nhưng có thể phân tích lại nhiều hơn cần thiết. Có thể bắt đầu ở mức file/module rồi tinh chỉnh theo số liệu.

### Scope và symbol table

Thay đổi một declaration có thể ảnh hưởng name resolution trong scope hiện tại và các scope lồng nhau. Nếu symbol table được chia theo scope, server có thể invalidation scope bị ảnh hưởng thay vì xây lại toàn bộ workspace index.

## 12. Phân loại thay đổi và phạm vi ảnh hưởng

Không phải mọi edit đều có phạm vi ảnh hưởng giống nhau.

| Loại edit | Tác động thường gặp | Phạm vi cập nhật có thể cần |
|---|---|---|
| Sửa literal | Giá trị biểu thức và type/error của expression | Node expression và ancestor liên quan. |
| Sửa identifier dùng | Name resolution, type và diagnostics tại reference | Reference node và dependency liên quan. |
| Rename declaration | Symbol index và mọi reference | Các file hoặc scope tham chiếu symbol. |
| Thêm/xóa import | Namespace và name resolution | Toàn file hoặc module phụ thuộc import. |
| Sửa public type/interface | Type checking và reference của consumer | Các module phụ thuộc interface. |
| Sửa comment | Documentation, trivia, formatting | Có thể chỉ cập nhật trivia/documentation. |
| Sửa grammar/configuration | Lexing/parsing hoặc semantics rộng | Nhiều hoặc toàn bộ tài liệu thuộc language version đó. |
| Đổi file path/URI | Import resolution, source identity và workspace index | File cùng dependency graph liên quan. |

Bảng này là hướng dẫn khái quát. Phạm vi chính xác phụ thuộc semantics DSL, cách compiler phân chia module và mức độ chi tiết của dependency tracking.

## 13. Invalidation và cache trong Language Server

Incremental update thường dựa vào cache của token, syntax tree, symbol, type và diagnostics. Mỗi cache entry cần gắn với snapshot hoặc fingerprint của đầu vào.

### Cache theo document version

Token stream và syntax tree có thể được lưu theo document URI và version. Khi version mới đến, server tạo kết quả mới hoặc cập nhật incremental từ snapshot trước.

### Cache semantic theo dependency

Kết quả semantic có thể phụ thuộc vào AST, symbol table, imported module và compiler configuration. Khi một dependency đổi, chỉ những entry liên quan bị invalidated.

### Không tái sử dụng range cũ một cách trực tiếp

Một token hoặc diagnostic có thể vẫn đúng về ngữ nghĩa nhưng offset đã thay đổi do edit trước đó. Nếu tái sử dụng node, server phải ánh xạ range sang snapshot mới. Nếu không có mapping đáng tin cậy, cần tạo lại range hoặc node.

### Cache key

Một cache key có thể gồm:

~~~text
(documentUri, documentVersion, languageVersion, parserConfigHash)
~~~

Với semantic result, key có thể bổ sung dependency fingerprints và project configuration version. Không nên dùng riêng URI vì cùng file có thể có nhiều snapshot và cấu hình phân tích khác nhau.

### Giải phóng cache

Khi tài liệu đóng hoặc workspace thay đổi, server cần giải phóng entry không còn được dùng. Cache phải có giới hạn dung lượng để phiên làm việc dài không làm memory tăng không kiểm soát.

## 14. Diagnostics tăng dần

Diagnostics gồm lỗi cú pháp, lỗi kiểu, unresolved reference, warning và thông tin khác. Sau một edit, server cần cập nhật diagnostics của đúng version và tránh giữ lỗi đã được sửa.

### Tính lại diagnostic bị ảnh hưởng

Nếu sửa một biểu thức, có thể tính lại diagnostics trong node và các ancestor liên quan. Nếu đổi khai báo public, cần cập nhật diagnostics ở các file phụ thuộc.

### Thay thế tập diagnostic

Với cơ chế push diagnostics, `textDocument/publishDiagnostics` thường mang tập diagnostics hiện tại cho một URI; client có thể thay thế danh sách trước đó bằng danh sách mới. Server cần gửi tập kết quả nhất quán, tránh chỉ gửi lỗi mới mà quên xóa lỗi đã hết hiệu lực.

### Version của diagnostic

Nếu client/server hỗ trợ trường version trong diagnostic publication, server nên gắn kết quả với document version tương ứng. Kết quả từ version cũ không được ghi đè diagnostics mới hơn.

### Pull diagnostics

Các phiên bản LSP mới có mô hình pull diagnostics, trong đó client yêu cầu kết quả và có thể dùng result ID để biết kết quả có thay đổi hay không. Server có thể tận dụng cached result và trả trạng thái unchanged khi phù hợp. Dù dùng push hay pull, quy tắc version consistency vẫn quan trọng.

### Xóa diagnostics khi đóng hoặc sửa file

Khi tài liệu đóng hoặc nội dung thay đổi khiến lỗi không còn, server cần làm sạch diagnostic cũ theo giao thức và chính sách client. Nếu không, Problems panel có thể hiển thị lỗi đã lỗi thời.

## 15. Cập nhật tăng dần các tính năng Language Server

Nhiều tính năng editor cũng cần cập nhật theo snapshot.

### Document symbols và outline

Khi thêm hoặc xóa declaration, outline cần cập nhật node tương ứng. Node không đổi có thể giữ expansion state nếu identity được bảo toàn. Range phải thuộc document version mới.

### Folding ranges

Chỉ các block bị ảnh hưởng cần tính lại folding range nếu parser hỗ trợ incremental structure. Range cũ cần được ánh xạ hoặc thay mới.

### Semantic tokens

Semantic highlighting có thể dùng full response hoặc delta response với `resultId`. Khi một vùng đổi, server có thể tính lại token tương ứng và trả delta nếu protocol/client hỗ trợ. Delta cần áp dụng trên đúng result trước đó.

### Completion

Completion phụ thuộc caret position, token trước/sau, scope và expected type. Sau edit, completion context cũ có thể hết hiệu lực. Cache completion cần gắn với document version và context đủ cụ thể.

### Hover và definition

Hover có thể phụ thuộc symbol/type của node tại vị trí. Definition phụ thuộc reference resolution. Thay đổi declaration hoặc import có thể invalidation kết quả ở nhiều file.

### References và rename

Reference index cần cập nhật khi symbol hoặc usage thay đổi. Rename phải dựa trên symbol identity và workspace snapshot nhất quán; không nên áp dụng text replacement dựa trên kết quả index cũ.

## 16. Workspace và thay đổi ngoài tài liệu đang mở

Language Server không chỉ nhận edit từ editor. File có thể thay đổi bởi Git checkout, generator, build tool hoặc một process khác.

### File watcher

Client hoặc server có thể theo dõi thay đổi file trong workspace. Khi file thay đổi ngoài editor, server cần cập nhật snapshot, dependency index và diagnostics liên quan.

### Open document và file trên đĩa

Nếu tài liệu đang mở, nội dung trong editor thường là nguồn mới nhất cho document đó. File watcher báo thay đổi trên đĩa không nên âm thầm ghi đè buffer chưa lưu của người dùng. Server cần phân biệt open-document overlay với filesystem state.

### Import graph

Nếu module được import thay đổi, server xác định consumer nào cần phân tích lại. Nếu file bị xóa hoặc đổi tên, reference resolution và diagnostics của các consumer cần được cập nhật.

### Workspace configuration

Thay đổi DSL version, compiler flags, library path hoặc schema registry có thể ảnh hưởng nhiều file. Những thay đổi này cần một dependency/configuration epoch để invalidation có thể được thực hiện rõ ràng.

### Multi-root workspace

Một client có thể mở nhiều workspace folder. Dependency và symbol index cần được phân vùng đúng để cùng URI hoặc tên module không gây nhầm giữa các project.

## 17. Cập nhật tăng dần và concurrency

Language Server xử lý nhiều notification và request bất đồng bộ. Một request có thể bắt đầu trên version cũ và hoàn tất sau khi tài liệu đã đổi.

### Stale analysis result

Ví dụ:

1. Document ở version 10; server bắt đầu parse và type check.
2. Client gửi edit, document chuyển version 11.
3. Server bắt đầu phân tích version 11.
4. Phân tích version 11 hoàn tất trước.
5. Phân tích version 10 hoàn tất sau.

Nếu kết quả version 10 được publish sau version 11, diagnostics hoặc outline sẽ lùi về trạng thái cũ.

### Version gate

Mỗi tác vụ phân tích nên giữ snapshot version. Trước khi ghi cache hoặc publish kết quả, server kiểm tra version đó còn là version được chấp nhận hay không. Nếu không, kết quả được bỏ qua hoặc chỉ được giữ như cache cho snapshot cũ nếu có ích.

### Immutable snapshot

Parser và semantic analyzer nên đọc snapshot bất biến. Khi có edit mới, server tạo snapshot mới mà không sửa nội dung đang được tác vụ cũ sử dụng.

### Cancellation

Request LSP có thể bị hủy bằng cancellation notification. Server nên kiểm tra cancellation trong các bước tốn thời gian như parse lớn, symbol search, reference search hoặc dependency traversal. Hủy request không nhất thiết có nghĩa bỏ toàn bộ cache computation nếu kết quả vẫn hữu ích cho version hiện tại.

### Debouncing và coalescing

Server có thể gộp nhiều edit nhanh thành một lần phân tích để giảm công việc. Tuy nhiên, document state vẫn phải áp dụng mọi edit theo thứ tự; chỉ phần phân tích có thể được coalesce. Không được bỏ qua text change rồi dùng range của change sau trên snapshot sai.

### Locking và parallelism

Có thể phân tích nhiều document độc lập song song, nhưng việc cập nhật state của cùng một document cần được tuần tự hóa hoặc dùng snapshot/version. Shared symbol index cần đồng bộ và tránh deadlock giữa các dependency.

## 18. Lập lịch phân tích nền

Một Language Server có thể ưu tiên request tương tác trước công việc nền.

### Ưu tiên theo mức độ tương tác

Các request completion hoặc hover thường cần phản hồi nhanh. Workspace-wide diagnostics hoặc indexing có thể chạy nền và bị hạ ưu tiên khi người dùng đang gõ.

### Coalescing work

Nếu có nhiều edit liên tiếp, server có thể chỉ chạy một lần semantic analysis cho snapshot mới nhất thay vì phân tích mọi version trung gian. Nhưng nếu một request cụ thể yêu cầu version cũ, server cần xử lý theo semantics của request hoặc hủy nếu client đã cancel.

### Cancellation của tác vụ lỗi thời

Khi version mới đến, tác vụ phân tích cũ có thể được hủy nếu không còn consumer. Điều này tiết kiệm CPU. Tuy nhiên, task dùng chung cho nhiều request hoặc tạo artifact cache có thể vẫn đáng hoàn tất.

### Backpressure

Nếu edit đến nhanh hơn tốc độ xử lý, queue có thể tăng. Server cần giới hạn queue, gộp công việc, hủy task lỗi thời hoặc giảm mức phân tích. Không nên để queue không giới hạn làm tăng memory.

## 19. Incremental update cho symbol index và references

Symbol index cho phép tìm khai báo, references và workspace symbols. Khi một file thay đổi, server có thể cập nhật phần index thuộc file đó.

### File-level index

Mỗi file có thể lưu danh sách symbol được khai báo, symbol được tham chiếu và dependency metadata. Khi file thay đổi, index file được xây lại hoặc cập nhật theo AST delta.

### Global index

Global index kết hợp các file index và namespace/import graph. Khi một declaration thay đổi, server cập nhật binding và xác định consumer bị ảnh hưởng.

### Rename

Rename cần xác định mọi reference đến cùng symbol identity. Nếu symbol index chưa đồng bộ với document version hiện tại, server cần cập nhật hoặc từ chối tạo workspace edit dựa trên dữ liệu cũ.

### Duplicate symbol

Thêm declaration mới có thể tạo xung đột tên trong scope. Server cần cập nhật diagnostics ở cả declaration mới và các vị trí có thể trở nên ambiguous.

### Index persistence

Index có thể được lưu trên đĩa để khởi động nhanh. Khi nạp lại, server cần kiểm tra source hash, project configuration và schema version trước khi dùng.

## 20. Cập nhật tăng dần trong project có dependency graph

Một DSL nhiều module thường có dependency graph. Incremental analysis có thể dùng graph để tính tập module bị ảnh hưởng.

Ví dụ:

~~~text
OrderWorkflow -> OrderModel
OrderWorkflow -> ApprovalPolicy
ApprovalPolicy -> CustomerModel
ApprovalPolicy -> RoleSchema
~~~

Nếu `RoleSchema` thay đổi, `ApprovalPolicy` có thể cần phân tích lại; `OrderWorkflow` có thể cũng bị ảnh hưởng qua dependency gián tiếp.

### Direct và transitive dependency

Server cần xác định dependency trực tiếp và gián tiếp. Nếu một module chỉ phụ thuộc public interface, thay đổi implementation không nhất thiết invalidation mọi consumer. Nếu compiler inline hoặc đọc implementation, fingerprint cần phản ánh điều đó.

### Topological order

Với graph không chu kỳ, có thể phân tích dependency trước consumer theo thứ tự topo. Nếu graph có cycle, compiler cần semantics module cycle riêng hoặc báo lỗi. Không nên dùng thứ tự filesystem scan làm thứ tự dependency.

### SCC và dependency cycle

Strongly connected components có thể xác định nhóm module liên thông mạnh. Một nhóm có cycle có thể cần được phân tích như một unit hoặc bị từ chối tùy đặc tả DSL.

### Fan-out lớn

Một interface phổ biến có thể được hàng trăm module phụ thuộc. Khi thay đổi, invalidation có thể rất rộng. Server cần giới hạn và lập lịch công việc nền, đồng thời vẫn bảo đảm kết quả cuối cùng nhất quán.

## 21. Cập nhật tăng dần và cấu trúc syntax tree

Incremental syntax tree cần giữ identity của node không đổi khi có thể, vì nhiều tính năng editor phụ thuộc node identity.

### Structural sharing

Immutable tree có thể chia sẻ subtree giữa snapshot cũ và mới. Chỉ node ở đường từ vùng edit đến root cần được tạo lại nếu cấu trúc xung quanh không đổi.

### Node identity

Node identity có thể dựa trên object identity trong snapshot, stable syntax ID hoặc structural matching. Dùng offset làm ID không ổn định vì edit trước node làm offset thay đổi.

### Green/red tree

Một số kiến trúc syntax tree dùng green node bất biến, không lưu absolute position, và red node cung cấp parent/position theo ngữ cảnh. Cách này hỗ trợ chia sẻ node giữa snapshot và tránh lưu lại offset tuyệt đối cho mọi node.

### Reuse criteria

Subtree chỉ được tái sử dụng khi token sequence, parser context và các điều kiện cấu trúc liên quan vẫn phù hợp. Reuse dựa trên text giống nhau đơn thuần có thể sai nếu subtree nằm trong scope hoặc grammar context khác.

## 22. Cập nhật tăng dần và diagnostics theo dependency

Một diagnostic có thể phụ thuộc vào nhiều node hoặc file. Ví dụ lỗi unresolved reference nằm trong file A nhưng nguyên nhân có thể do import hoặc declaration ở file B.

### Diagnostic ownership

Mỗi diagnostic cần URI và range của nguồn chính, code, severity và message. Nếu lỗi có related information, server có thể chỉ ra declaration hoặc vị trí liên quan ở file khác.

### Invalidation theo nguồn

Khi file A thay đổi, xóa diagnostics cũ của A rồi tạo lại diagnostics mới từ snapshot phù hợp. Khi file B thay đổi, diagnostics ở A có thể cũng cần cập nhật nếu reference trong A phụ thuộc vào B.

### Diagnostic deduplication

Nhiều pass có thể phát cùng một lỗi. Server có thể chuẩn hóa key theo code, source, range, symbol và message arguments để tránh duplicate, nhưng không nên gộp hai lỗi khác nguyên nhân chỉ vì range giống nhau.

### Diagnostic stability

Khi lỗi vẫn còn sau edit nhỏ, UI có thể giữ node hoặc marker nếu diagnostic identity được nhận diện. Tuy nhiên, range và version vẫn phải cập nhật; không nên giữ marker cũ bằng cách giả định offset không đổi.

## 23. Cập nhật tăng dần và semantic tokens

Semantic tokens cung cấp thông tin tô màu dựa trên ngữ nghĩa, chẳng hạn phân biệt property, type, function, enum member hoặc variable. LSP hỗ trợ full và delta semantic tokens trong các client/server có capability tương ứng.

### Full semantic tokens

Server trả toàn bộ token data cho document. Đây là cách đơn giản nhưng có thể tốn băng thông với tài liệu lớn.

### Delta semantic tokens

Server có thể trả các edit trên token data trước đó, gắn với `resultId`. Client áp dụng delta lên kết quả tương ứng. Nếu result ID không còn phù hợp, cần yêu cầu hoặc trả full result theo giao thức.

### Token index khác text offset

Semantic token response thường mã hóa line, character, length, token type và modifiers theo dạng số delta. Việc tạo delta cần dựa trên đúng token sequence trước đó và document version.

### Invalidation

Thay đổi identifier có thể làm semantic token của một vùng thay đổi; đổi declaration type có thể ảnh hưởng token của references ở file khác. Dependency graph và semantic index giúp xác định phạm vi cập nhật.

## 24. Cập nhật tăng dần cho completion và hover

Completion và hover thường được yêu cầu tại vị trí caret hiện tại, vì vậy cần dùng snapshot mới nhất có thể.

### Completion context

Completion có thể phụ thuộc:

- Token trước caret.
- Syntax node hiện tại.
- Scope và symbol table.
- Expected type.
- Imported module.
- Trigger character và completion mode.

Cache completion nên gắn với version hoặc fingerprint của các yếu tố này. Nếu người dùng đổi import hoặc khai báo, danh sách gợi ý có thể thay đổi dù vị trí caret không đổi.

### Hover

Hover thường tra symbol hoặc type của expression tại position. Nếu semantic analysis của version mới chưa hoàn tất, server có thể dùng kết quả gần nhất nhưng cần biết nó thuộc version nào. Với dữ liệu không còn phù hợp, có thể trả kết quả rỗng hoặc chờ một khoảng ngắn tùy chính sách.

### Request position

Position trong request được tính trên snapshot client đang gửi. Server phải dùng đúng document version hoặc snapshot tương ứng; không thể áp position mới lên buffer cũ một cách tùy tiện.

## 25. Cập nhật tăng dần cho rename và code actions

Rename và code action có thể tạo thay đổi trên một hoặc nhiều file. Chúng cần semantic information nhất quán.

### Rename

Rename xác định symbol tại vị trí, tìm references và tạo `WorkspaceEdit`. Nếu reference index thuộc version cũ, kết quả có thể bỏ sót hoặc thay nhầm occurrence. Cần cập nhật index hoặc kiểm tra document version trước khi trả edit.

### Code action

Code action có thể được yêu cầu dựa trên diagnostics trước đó. Server nên xác định diagnostic còn phù hợp với document snapshot hiện tại không. Edit được trả về cần có range chính xác và có thể dùng version/documentChanges để bảo vệ trước thay đổi đồng thời theo khả năng giao thức.

### Resolve code action

Một code action có thể được trả ban đầu ở dạng nhẹ rồi resolve thêm khi người dùng chọn. Khi resolve, server cần xác minh document và dependency state chưa làm action trở nên lỗi thời.

### Multi-file edit

Một rename có thể cập nhật nhiều file. Nếu một file thay đổi sau khi server tính workspace edit, client hoặc server cần phát hiện xung đột theo version. Không nên áp dụng range cũ trên file mới.

## 26. File watcher và external change

Language Server có thể nhận thay đổi ngoài luồng editor, ví dụ generator ghi file, Git checkout hoặc người dùng chỉnh sửa file bằng công cụ khác.

### Đồng bộ filesystem

File watcher notification thường báo URI và loại thay đổi, nhưng không nhất thiết cung cấp nội dung mới. Server có thể đọc lại file, cập nhật source snapshot và chạy incremental analysis dựa trên diff giữa nội dung cũ/mới nếu có thể.

### File đang mở

Nếu document đang mở và có unsaved edits, buffer của client thường phải được ưu tiên. File watcher không được ghi đè trạng thái chưa lưu. Server cần theo dõi overlay cho open documents.

### Rename và delete file

Khi file bị rename hoặc delete, server cần cập nhật URI mapping, import graph, symbol index và diagnostics. Nếu một module được tham chiếu qua relative path, các consumer có thể cần resolve lại.

### Configuration change

Thay đổi compiler options hoặc language version có thể làm invalidation rộng hơn một edit text. Cần có notification hoặc reload mechanism để server biết configuration epoch đã thay đổi.

## 27. Error recovery khi nhận edit không hợp lệ

Một edit có thể không áp dụng được nếu server và client mất đồng bộ, range vượt document bounds hoặc encoding conversion sai.

### Kiểm tra range

Server cần xác nhận start/end hợp lệ trong snapshot hiện tại và start không sau end. Nếu range vượt bounds, không được tự cắt range một cách âm thầm vì có thể tạo nội dung khác client.

### Version mismatch

Nếu version hoặc thứ tự notification không phù hợp, server cần phát hiện trạng thái out-of-sync và phục hồi theo chính sách. Có thể cần client gửi full content hoặc đóng/mở lại document.

### Atomic application

Một notification có nhiều changes. Nếu change giữa chừng lỗi, server không nên để snapshot ở trạng thái nửa áp dụng mà client không biết. Có thể áp dụng trên bản sao tạm rồi commit toàn bộ khi thành công, hoặc đánh dấu document invalid và yêu cầu resync.

### Logging

Log nên có URI, version, range và loại lỗi đồng bộ. Tránh ghi toàn bộ nội dung tài liệu vào log mặc định vì có thể chứa dữ liệu nhạy cảm.

## 28. Chiến lược kiến trúc: từ đơn giản đến tăng dần

Không cần xây dựng một incremental compiler hoàn chỉnh ngay từ đầu. Có thể phát triển theo từng lớp, giữ correctness trước rồi tối ưu nơi có số liệu.

### Giai đoạn 1: Full document sync và full parse

Triển khai đúng lifecycle LSP, document version, source manager và parser chịu được tài liệu lỗi. Đây là nền tảng để có kết quả đúng.

### Giai đoạn 2: Incremental text sync

Thương lượng `Incremental`, áp dụng content changes theo thứ tự, quản lý line index và snapshot. Có kiểm thử đối chiếu buffer server với nội dung client.

### Giai đoạn 3: Incremental lexing/parsing

Thêm lexer checkpoint, token cache, syntax tree immutable và cơ chế reparse vùng ảnh hưởng. So sánh cây incremental với kết quả full parse để xác nhận tương đương.

### Giai đoạn 4: Incremental semantic analysis

Xây dependency graph theo module/symbol, invalidation semantic cache và cập nhật diagnostics liên quan.

### Giai đoạn 5: Incremental editor features

Thêm outline reconciliation, folding update, semantic token delta, symbol index update và completion cache theo version.

### Giai đoạn 6: Scheduling và observability

Thêm cancellation, coalescing, backpressure, priority queue và metrics để điều chỉnh theo workload thực tế.

## 29. Ví dụ xử lý một thay đổi từ đầu đến cuối

Giả sử tài liệu ban đầu:

~~~text
entity Order {
    customer: Customer;
    total: Money;
}

policy Approval {
    when order.total >= 1000 then ManagerApproval;
}
~~~

Người dùng đổi `Money` thành `Decimal`.

Một luồng cập nhật tăng dần có thể là:

1. Client gửi `didChange` với version mới và range bao trùm `Money`.
2. Server kiểm tra version, chuyển range sang offset theo encoding đã thương lượng.
3. Text buffer tạo snapshot mới và cập nhật line index.
4. Lexer restart tại checkpoint trước edit, quét token mới và tìm điểm hội tụ.
5. Parser reparse khai báo `Order` hoặc field `total`, giữ subtree không đổi.
6. Semantic analyzer cập nhật type của `Order.total`.
7. Dependency graph cho biết `Approval` tham chiếu `Order.total`; biểu thức và diagnostics liên quan được tính lại.
8. Outline node `Order` được cập nhật detail của field `total` nếu UI hiển thị type.
9. Semantic tokens và diagnostics được cập nhật theo version mới.
10. Server chỉ publish kết quả nếu version vẫn là version hiện hành được chấp nhận.

Nếu type `Money` vẫn tồn tại ở nơi khác, các module không phụ thuộc vào `Order.total` không cần bị phân tích lại. Nếu đổi type làm public interface của `Order` thay đổi, consumer phụ thuộc interface có thể cần semantic update.

## 30. Kiểm thử tính tương đương giữa incremental và full analysis

Một cách quan trọng để xác nhận incremental processing là so sánh kết quả với phân tích toàn phần trên cùng nội dung.

### Differential testing

Với mỗi chuỗi edit:

1. Áp dụng edit vào snapshot incremental.
2. Lấy kết quả token/AST/semantic từ pipeline incremental.
3. Chạy full lexer/parser/semantic analysis trên toàn bộ nội dung mới.
4. Chuẩn hóa các kết quả cần so sánh.
5. Xác nhận chúng tương đương về semantics, diagnostics và source ranges theo hợp đồng.

Không nhất thiết mọi node ID hoặc cache metadata phải giống nhau. Cần so sánh những kết quả quan sát được mà consumer dựa vào.

### Property-based edit sequences

Sinh chuỗi insert, delete, replace ngẫu nhiên với Unicode, newline, comment, string và cấu trúc lồng. Sau mỗi bước, xác nhận snapshot server khớp nội dung kỳ vọng và incremental result tương đương full result.

### Test version race

Cho phân tích version cũ chạy chậm hơn version mới. Xác nhận kết quả cũ không ghi đè diagnostics, outline hoặc semantic tokens mới.

### Test resynchronization

Giả lập range không hợp lệ hoặc bỏ lỡ notification. Xác nhận server phát hiện mất đồng bộ và phục hồi theo chính sách, không tiếp tục phân tích một buffer sai.

## 31. Những trường hợp biên cần kiểm thử

Các trường hợp sau thường làm lộ lỗi incremental:

- Chèn dấu mở comment ở đầu file làm thay đổi tokenization của nhiều dòng.
- Xóa dấu đóng string hoặc dấu ngoặc làm parser state thay đổi đến EOF.
- Đổi newline LF thành CRLF hoặc ngược lại.
- Chèn ký tự ngoài BMP trước range đang được tham chiếu.
- Sửa identifier thành keyword hoặc ngược lại.
- Thêm import làm một tên từ unresolved thành resolved hoặc ambiguous.
- Xóa declaration được nhiều file tham chiếu.
- Đổi public type khiến consumer bị ảnh hưởng.
- Sửa file trên đĩa trong khi buffer editor còn unsaved changes.
- Đóng document khi tác vụ phân tích vẫn đang chạy.
- Nhận nhiều changes trong cùng notification.
- Nhận notification mới khi parse cũ chưa hoàn tất.
- Hủy request trong lúc semantic analysis đang duyệt dependency graph.
- Thay đổi configuration hoặc language version khi workspace đang mở.

## 32. Đo lường hiệu năng cập nhật tăng dần

Không nên chỉ đo thời gian parse. Cần quan sát toàn bộ đường đi từ notification đến kết quả hiển thị.

Các chỉ số có thể theo dõi:

- Kích thước byte của change so với toàn document.
- Thời gian áp dụng text edit.
- Thời gian cập nhật line index và offset mapping.
- Số token được lex lại và số token được reuse.
- Số node parser được tạo lại và số subtree được reuse.
- Số module/symbol bị invalidated.
- Thời gian semantic analysis.
- Thời gian đến diagnostic đầu tiên và diagnostic hoàn chỉnh.
- Số request bị cancel hoặc stale.
- Queue depth và thời gian chờ scheduler.
- CPU, memory allocation và garbage collection.

### Latency theo percentile

Nên đo median, p95 và p99 thay vì chỉ average. Một số edit lớn hoặc dependency fan-out cao có thể tạo đuôi latency dài dù trung bình vẫn thấp.

### Work avoided

Đếm số token, node, module hoặc query không phải tính lại giúp xác định incremental strategy có thực sự giảm công việc. Một parser có thể báo latency tốt trên file nhỏ nhưng vẫn reparse toàn bộ file ở mọi edit.

### Correctness trước throughput

Nếu tăng tốc bằng cách bỏ qua dependency hoặc giữ diagnostics cũ, số liệu latency đẹp nhưng server không còn đúng. Cần theo dõi stale result và differential test song song với metrics hiệu năng.

## 33. Những lỗi thiết kế thường gặp

**Chỉ bật incremental sync nhưng vẫn parse toàn bộ.** Băng thông giảm nhưng CPU và latency phân tích không thay đổi đáng kể. Cần phân biệt document synchronization với incremental analysis.

**Áp dụng nhiều change trên cùng snapshot ban đầu.** LSP content changes được áp dụng theo thứ tự; range của change sau có thể phụ thuộc kết quả change trước.

**Bỏ qua document version.** Kết quả parse cũ có thể ghi đè diagnostics hoặc outline mới.

**Dùng mutable buffer chung cho parser.** Parser có thể đọc nội dung không nhất quán khi edit xảy ra đồng thời.

**Tính offset bằng đơn vị sai.** UTF-8 byte, UTF-16 code unit và code point khác nhau; Unicode có thể làm range lệch.

**Restart lexer tại vị trí không an toàn.** String, comment, interpolation và indentation có thể làm lexical state lan qua nhiều dòng.

**Tái sử dụng token chỉ dựa trên text.** Cần so sánh lexical state và parser context ở ranh giới hội tụ.

**Chỉ reparse node nhỏ nhất mà không mở rộng khi cần.** Thay đổi delimiter hoặc grammar context có thể ảnh hưởng ancestor và sibling.

**Không theo dõi dependency semantic.** Đổi declaration ở một file nhưng không cập nhật diagnostics và type ở consumer khác.

**Không xóa diagnostic cũ.** Lỗi đã sửa vẫn tồn tại trong Problems panel.

**Debounce bằng cách bỏ edit.** Có thể coalesce phân tích, nhưng phải áp dụng mọi text change theo đúng thứ tự để buffer không lệch client.

**Không có backpressure.** Queue phân tích tăng vô hạn khi người dùng gõ nhanh hoặc workspace lớn.

**Không phân biệt open buffer với file trên đĩa.** File watcher có thể ghi đè hoặc làm mất nội dung chưa lưu.

**Không kiểm thử Unicode và edit sequence.** Test chỉ dùng ASCII và một edit đơn giản không phát hiện nhiều lỗi range.

## 34. Quy trình triển khai cập nhật tăng dần trong Language Server

Một quy trình thực tế có thể gồm:

1. **Định nghĩa document lifecycle:** open, change, save, close và quyền sở hữu snapshot.
2. **Thương lượng sync capability:** chọn None, Full hoặc Incremental theo khả năng server/client.
3. **Chuẩn hóa position encoding:** xử lý line/character, UTF-16 mặc định và encoding được thương lượng.
4. **Xây document store:** URI, version, immutable snapshot, line index và trạng thái đồng bộ.
5. **Áp dụng edit tuần tự:** xác thực range, version và atomicity của notification.
6. **Thêm incremental lexer:** checkpoint, lexical state, restart và convergence.
7. **Thêm incremental parser:** reparse region, immutable subtree và error recovery.
8. **Xây semantic dependency graph:** file, scope, symbol, type, schema và import.
9. **Thiết kế invalidation/cache:** gắn version và dependency fingerprint cho từng kết quả.
10. **Cập nhật diagnostics và editor features:** outline, folding, semantic tokens, completion và references.
11. **Quản lý tác vụ bất đồng bộ:** cancellation, version gate, coalescing, priority và backpressure.
12. **Đồng bộ workspace:** file watcher, configuration, multi-root và dependency changes.
13. **Kiểm thử tương đương:** differential, property-based, Unicode, version race và resync.
14. **Đo hiệu năng:** latency, work avoided, memory, queue và stale result.

## 35. Checklist cho một cơ chế incremental mới

Khi thêm một tầng cập nhật tăng dần, cần trả lời:

- Trạng thái cũ nào được tái sử dụng?
- Đầu vào và version của trạng thái đó là gì?
- Edit có thể ảnh hưởng phạm vi nào?
- Có dependency tĩnh hoặc động nào cần theo dõi không?
- Điểm restart an toàn nằm ở đâu?
- Điều kiện convergence hoặc reuse là gì?
- Source range được ánh xạ sang snapshot mới ra sao?
- Nếu không thể xác định phạm vi ảnh hưởng, fallback full recompute thế nào?
- Tác vụ cũ có thể bị cancel không?
- Kết quả có được kiểm tra version trước khi publish không?
- Cache được invalidated khi dependency nào thay đổi?
- Diagnostics cũ được thay thế hoặc xóa ra sao?
- Có xử lý Unicode, newline, nhiều edit và document chưa hoàn chỉnh không?
- Có backpressure và giới hạn bộ nhớ không?
- Có differential test đối chiếu với full computation không?
- Metrics nào cho thấy công việc thực sự được giảm?

## 36. Kết quả cần có sau khi thiết kế cập nhật tăng dần

Một thiết kế incremental update hoàn chỉnh cho Language Server thường có:

- **Document synchronization contract:** lifecycle, sync kind, content change ordering và resynchronization.
- **Versioned document store:** URI, version, immutable snapshot, line index và position encoding.
- **Text buffer strategy:** string, rope, piece table hoặc buffer abstraction phù hợp.
- **Incremental lexer:** checkpoint, lexical state, restart và convergence.
- **Incremental parser:** reparse region, syntax tree reuse, parser context và error recovery.
- **Semantic dependency model:** symbol, scope, type, module, import và invalidation graph.
- **Cache policy:** version/fingerprint, reuse criteria và invalidation.
- **Feature update model:** diagnostics, outline, folding, semantic tokens, completion, hover và references.
- **Concurrency model:** immutable snapshots, cancellation, version gate, coalescing và backpressure.
- **Workspace synchronization:** file watcher, open-buffer overlay, configuration và multi-root support.
- **Correctness strategy:** differential tests, property-based edits, Unicode, race và resync tests.
- **Observability:** latency percentile, work avoided, queue, memory và stale-result metrics.

Cập nhật tăng dần giúp Language Server phản hồi nhanh khi tài liệu thay đổi bằng cách tái sử dụng những phần kết quả vẫn hợp lệ và chỉ tính lại vùng bị ảnh hưởng. Để làm được điều đó một cách đúng đắn, server phải quản lý chặt document snapshot, version và position encoding; lexer/parser cần có checkpoint và điều kiện reuse; semantic analysis cần dependency graph; còn diagnostics và các tính năng editor phải được công bố theo đúng version. Cancellation, concurrency, resynchronization và kiểm thử đối chiếu với full analysis bảo vệ hệ thống trước kết quả lỗi thời hoặc sai lệch. Khi các lớp này phối hợp với nhau, Language Server có thể hỗ trợ tài liệu DSL lớn và nhiều thao tác chỉnh sửa liên tục mà vẫn duy trì tính nhất quán và độ trễ thấp.
