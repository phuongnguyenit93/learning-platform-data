# REPL

REPL là viết tắt của **Read-Eval-Print Loop**: đọc đầu vào, đánh giá hoặc thực thi, in kết quả rồi lặp lại. Đây là công cụ tương tác cho phép người dùng nhập từng biểu thức, lệnh hoặc đoạn chương trình và nhận phản hồi ngay mà không cần tạo một tệp hoàn chỉnh rồi chạy toàn bộ quy trình build. Với ngôn ngữ miền chuyên biệt (Domain-Specific Language, DSL), REPL giúp thử nhanh cú pháp, kiểm tra giá trị, khám phá mô hình miền, chạy truy vấn hoặc thao tác với một môi trường mô phỏng.

Một REPL tốt không chỉ là vòng lặp đọc chuỗi rồi gọi parser. Nó cần quản lý phiên làm việc, trạng thái và phạm vi tên, nhận biết đầu vào chưa hoàn chỉnh, hiển thị diagnostics dễ hiểu, hỗ trợ lịch sử và hoàn thành lệnh, đồng thời kiểm soát các hiệu ứng có thể xảy ra khi đánh giá. Nếu DSL có khả năng thay đổi cấu hình, tạo tài nguyên hoặc gọi dịch vụ bên ngoài, REPL còn cần phân biệt thao tác thử nghiệm với thao tác có tác động thật.

## 1. REPL là gì?

Một REPL thực hiện lặp lại bốn bước:

1. **Read:** đọc biểu thức hoặc lệnh từ người dùng.
2. **Eval:** phân tích, kiểm tra và đánh giá đầu vào trong một môi trường.
3. **Print:** hiển thị kết quả, diagnostics hoặc thông tin trạng thái.
4. **Loop:** chờ đầu vào tiếp theo cho đến khi người dùng thoát hoặc phiên bị kết thúc.

~~~mermaid
flowchart TD
    A[Prompt] --> B[Read input]
    B --> C{Input complete?}
    C -->|No| D[Read continuation line]
    D --> C
    C -->|Yes| E[Parse]
    E --> F[Resolve and validate]
    F --> G[Evaluate]
    G --> H[Print result or diagnostics]
    H --> A
    B -->|Exit command| I[Close session]
~~~

Với một DSL biểu thức đơn giản, người dùng có thể nhập:

~~~text
> 2 + 3 * 4
14
> upper("hello")
"HELLO"
~~~

Với DSL cấu hình, REPL có thể cho phép truy vấn mô hình:

~~~text
dsl> service "catalog" { replicas = 3 }
Service(name="catalog", replicas=3)
dsl> get service "catalog".replicas
3
~~~

Cú pháp thực tế phụ thuộc DSL. Một số REPL chỉ nhận biểu thức; một số cho phép khai báo, câu lệnh nhiều dòng và lệnh quản trị phiên.

## 2. REPL khác gì với CLI và script runner?

Các công cụ này có thể dùng chung parser và evaluator nhưng phục vụ cách tương tác khác nhau.

| Công cụ | Cách dùng | Đặc điểm |
|---|---|---|
| REPL | Nhập từng đoạn và nhận kết quả ngay | Có phiên, prompt và trạng thái tương tác |
| CLI command | Gọi một lệnh với tham số | Thường thực hiện một tác vụ rồi kết thúc |
| Script runner | Đọc tệp chương trình và chạy | Có đầu vào đầy đủ, thường không cần prompt |
| Debugger console | Đánh giá biểu thức trong context đang dừng | Có quyền truy cập trạng thái chương trình/debug session |
| Notebook | Chạy từng cell có kết quả lưu lại | Thường giữ lịch sử cell và output phong phú |

Một REPL có thể được triển khai như một chế độ của CLI. Ví dụ, chạy lệnh dsl không có đối số sẽ mở prompt; lệnh dsl run file.dsl chạy script; lệnh dsl validate file.dsl kiểm tra một tệp. Dùng chung frontend giúp cú pháp và quy tắc ngữ nghĩa nhất quán.

## 3. Khi nào DSL cần REPL?

REPL hữu ích khi người dùng cần khám phá hoặc thử nghiệm nhanh:

- Thử biểu thức và toán tử của DSL.
- Kiểm tra hàm thư viện hoặc built-in.
- Tạo một mô hình miền nhỏ để xem kết quả.
- Thử truy vấn hoặc bộ lọc.
- Khám phá giá trị mặc định và kiểu suy luận.
- Thử một quy tắc trước khi đưa vào tệp chính thức.
- Tương tác với môi trường mô phỏng hoặc sandbox.
- Học cú pháp bằng phản hồi tức thì.
- Điều tra lỗi mà không phải chạy toàn bộ dự án.

REPL không nhất thiết phù hợp với mọi DSL. Một DSL chỉ mô tả toàn bộ deployment graph hoặc workflow cần nhiều tệp phụ thuộc có thể khó đánh giá từng dòng độc lập. Khi đó, REPL có thể cung cấp lệnh truy vấn, validate hoặc tạo fragment trong một workspace tạm thay vì thực thi từng khai báo riêng lẻ.

## 4. Kiến trúc của một REPL cho DSL

Nên tách phần giao diện terminal khỏi parser, semantic analyzer và evaluator. Cấu trúc khái niệm:

~~~mermaid
flowchart TD
    A[Terminal or editor input] --> B[REPL controller]
    B --> C[Input buffer]
    C --> D[Lexer and parser]
    D --> E[AST]
    E --> F[Name resolution and validation]
    F --> G[Evaluator or interpreter]
    G --> H[Session environment]
    G --> I[Result renderer]
    D --> J[Diagnostic renderer]
    F --> J
    G --> J
    I --> K[Next prompt]
    J --> K
~~~

Các thành phần thường có:

- **Input reader:** nhận dòng, phím điều khiển hoặc cell.
- **Input buffer:** tích lũy nhiều dòng cho đến khi biểu thức hoàn chỉnh.
- **REPL controller:** điều phối vòng lặp và lệnh đặc biệt.
- **Lexer/parser:** dùng grammar chính của DSL.
- **Semantic services:** phân giải tên, kiểm tra kiểu và quy tắc miền.
- **Evaluator:** tính giá trị hoặc thực hiện câu lệnh.
- **Session environment:** giữ biến, khai báo và trạng thái của phiên.
- **Renderer:** định dạng kết quả, lỗi, cảnh báo và trợ giúp.
- **History/completion service:** lưu lịch sử và gợi ý đầu vào.
- **Execution policy:** giới hạn quyền, thời gian và hiệu ứng.

Không nên viết lại parser riêng chỉ cho REPL nếu DSL đã có parser dùng cho tệp. Hai parser khác nhau dễ dẫn đến tình huống một câu lệnh chạy được trong REPL nhưng không hợp lệ trong file, hoặc ngược lại.

## 5. Chu trình Read-Eval-Print-Loop chi tiết

### 5.1. Read

Reader lấy dữ liệu từ terminal. Ở chế độ đơn giản, nó đọc từng dòng. Với input nhiều dòng, reader có thể tiếp tục đọc khi parser xác định cấu trúc chưa hoàn chỉnh.

Một dòng trống có thể có nghĩa kết thúc input, bỏ qua hoặc chèn newline tùy chế độ. Không nên tự coi mọi dòng trống là kết thúc khối nếu DSL cho phép chuỗi nhiều dòng hoặc block rỗng.

### 5.2. Eval

Eval thường gồm nhiều bước:

1. Lex và parse input.
2. Kiểm tra input đã hoàn chỉnh hay còn thiếu delimiter.
3. Phân giải tên trong session environment.
4. Kiểm tra kiểu và quy tắc miền.
5. Xác định có thể đánh giá an toàn hay không.
6. Thực thi hoặc tính giá trị.
7. Cập nhật session state nếu câu lệnh tạo thay đổi.

Biểu thức thuần như 2 + 3 có thể được đánh giá trực tiếp. Câu lệnh khai báo như let total = 5 có thể cập nhật môi trường. Lệnh có tác dụng ngoài như deploy cần policy riêng.

### 5.3. Print

Renderer hiển thị kết quả theo kiểu dữ liệu và ngữ cảnh. Một giá trị số có thể in trực tiếp; một object miền có thể in dưới dạng bảng hoặc cấu trúc rút gọn; một danh sách lớn có thể bị giới hạn số phần tử hiển thị.

Khi có lỗi, cần phân biệt lỗi cú pháp, lỗi tên, lỗi kiểu, lỗi validation và lỗi runtime. Thông báo nên có vị trí trong input hiện tại hoặc tên tệp nguồn nếu REPL đang thao tác trên workspace.

### 5.4. Loop

Sau khi hiển thị kết quả, REPL đưa ra prompt tiếp theo. Nó cần tiếp tục hoạt động sau lỗi thông thường. Một exception trong evaluator không nên làm sập toàn bộ tiến trình REPL nếu lỗi đó có thể được bắt và chuyển thành diagnostic.

## 6. Prompt và chế độ nhập nhiều dòng

Prompt chính thường cho biết REPL sẵn sàng nhận một câu lệnh mới. Prompt phụ (continuation prompt) cho biết input hiện tại chưa hoàn chỉnh.

Ví dụ:

~~~text
dsl> service "catalog" {
...     replicas = 3
...     port = 8080
... }
Service(name="catalog", replicas=3, port=8080)
dsl>
~~~

Parser có thể trả về ba trạng thái:

- **Complete:** input tạo thành một cấu trúc cú pháp hoàn chỉnh.
- **Incomplete:** input có thể hợp lệ nếu người dùng nhập thêm, ví dụ thiếu dấu } hoặc dấu nháy đóng.
- **Invalid:** input đã vi phạm grammar theo cách không thể giải quyết chỉ bằng cách thêm văn bản ở cuối.

Việc phân biệt incomplete với invalid rất quan trọng. Nếu parser báo lỗi ngay khi người dùng mới gõ dấu mở ngoặc, REPL sẽ liên tục hiển thị lỗi dù người dùng chỉ đang nhập dở.

Một kiểu kết quả:

~~~java
sealed interface ParseStatus {
    record Complete(AstNode node) implements ParseStatus {}
    record Incomplete(String expected) implements ParseStatus {}
    record Invalid(List<Diagnostic> diagnostics) implements ParseStatus {}
}
~~~

Đây là mô hình minh họa. Parser có thể dùng trạng thái riêng hoặc exception chuyên biệt, nhưng REPL cần nhận biết input chưa hoàn chỉnh để tiếp tục đọc.

## 7. Xác định input đã hoàn chỉnh

Một cách đơn giản là đếm delimiter mở/đóng như {}, [] và (). Tuy nhiên, cách này không đủ nếu dấu ngoặc xuất hiện bên trong chuỗi hoặc comment.

Ví dụ:

~~~text
message = "text with } inside"
~~~

Dấu } trong chuỗi không đóng block. Vì vậy, cách đáng tin cậy hơn là dùng lexer/parser của DSL để xác định trạng thái cú pháp.

Parser có thể cung cấp expected token set tại EOF. Nếu parser kết thúc vì thiếu }, ), ], hoặc dấu nháy đóng, REPL có thể yêu cầu thêm dòng. Nếu gặp token không thể hợp lệ trong ngữ cảnh hiện tại, nó có thể báo lỗi và reset buffer.

Cần có cách hủy input nhiều dòng, chẳng hạn Ctrl+C hoặc lệnh reset, để người dùng không bị mắc kẹt trong một block chưa đóng.

## 8. Session và môi trường thực thi

REPL thường duy trì session environment giữa các lần nhập. Ví dụ:

~~~text
dsl> let base = 10
10
dsl> let tax = 2
2
dsl> base + tax
12
~~~

Môi trường có thể chứa:

- Biến và giá trị.
- Hàm do người dùng định nghĩa.
- Khai báo kiểu hoặc schema.
- Namespace và import.
- Đối tượng miền đang được thao tác.
- Cấu hình phiên.
- Lịch sử hoặc metadata phục vụ công cụ.

Một môi trường có thể được biểu diễn bằng symbol table hoặc scope chain. Khi người dùng khai báo biến mới, REPL cần xác định phạm vi tồn tại của nó: toàn session, block hiện tại hay module tạm.

### 8.1. Khai báo trùng

Nếu người dùng nhập lại:

~~~text
dsl> let count = 1
dsl> let count = 2
~~~

REPL cần có quy tắc rõ: từ chối khai báo trùng, cho phép shadowing trong scope mới, hay cho phép gán lại bằng cú pháp assignment. Không nên âm thầm thay giá trị nếu ngữ nghĩa DSL phân biệt declaration và assignment.

### 8.2. Reset session

Lệnh reset có thể xóa biến và khai báo do người dùng tạo, đưa environment về trạng thái ban đầu. Nó cần xác định có giữ history, import, cấu hình và kết nối hay không.

Một session có thể hỗ trợ nhiều mức reset:

- Reset toàn bộ biến và khai báo tạm.
- Reset một namespace.
- Xóa một biến cụ thể.
- Khởi tạo lại workspace context.
- Thoát và tạo session mới.

## 9. Phạm vi tên và shadowing

REPL có thể có nhiều scope: built-in, workspace/module, session và block tạm. Quy tắc tra cứu nên nhất quán với DSL khi chạy trong tệp.

Ví dụ:

~~~text
dsl> let rate = 0.1
dsl> {
...     let rate = 0.2
...     rate
... }
0.2
dsl> rate
0.1
~~~

Nếu DSL hỗ trợ lexical scope, block mới tạo scope con và có thể shadow tên ở scope ngoài. Khi block kết thúc, tên cục bộ không còn được nhìn thấy.

Cần xác định khai báo trong REPL có được export ra workspace hay chỉ tồn tại trong session. Một khai báo tạm không nên vô tình trở thành module global hoặc làm thay đổi file nguồn.

## 10. Biểu thức, câu lệnh và lệnh đặc biệt

REPL thường nhận ba loại đầu vào:

1. **Expression:** tính giá trị và in kết quả.
2. **Statement/declaration:** thực hiện hành động hoặc cập nhật environment.
3. **Meta-command:** điều khiển chính REPL, ví dụ help, history, reset hoặc quit.

Ví dụ:

~~~text
dsl> 2 * 21
42
dsl> let name = "catalog"
"catalog"
dsl> :type name
String
dsl> :help
Available commands: :help, :type, :history, :reset, :quit
~~~

Meta-command thường có tiền tố riêng như dấu hai chấm để không xung đột với grammar DSL. Cú pháp chính xác tùy sản phẩm. Một lựa chọn khác là dùng lệnh DSL như help() hoặc typeOf(...), nhưng khi đó chúng thuộc ngữ nghĩa ngôn ngữ và có thể bị shadowing.

Nên phân biệt meta-command với câu lệnh của DSL trong parser hoặc controller. Không nên dùng chuỗi prefix đơn giản nếu nó có thể xuất hiện hợp lệ trong chuỗi hoặc identifier.

## 11. Thiết kế tập lệnh REPL hữu ích

Một bộ lệnh nhỏ có thể gồm:

| Lệnh | Mục đích |
|---|---|
| :help | Hiển thị trợ giúp |
| :quit hoặc :exit | Kết thúc phiên |
| :history | Xem lịch sử nhập |
| :clear | Xóa màn hình terminal |
| :reset | Đặt lại session environment |
| :type expr | Hiển thị kiểu của biểu thức |
| :ast | Hiển thị AST của input gần nhất |
| :env | Liệt kê biến và khai báo trong session |
| :load path | Nạp một tệp vào workspace/session theo policy |
| :save path | Lưu trạng thái session nếu được hỗ trợ |
| :undo | Hoàn tác thao tác có thể đảo ngược |
| :set key value | Thay đổi cấu hình phiên |

Không nhất thiết phải triển khai tất cả. Lệnh cần thiết phụ thuộc vào use case. Ví dụ, REPL chỉ dùng để tính biểu thức có thể không cần load/save workspace; REPL cho DSL cấu hình có thể cần inspect model, validate và export.

## 12. Hiển thị kết quả theo kiểu dữ liệu

Kết quả REPL cần dễ đọc và không làm terminal quá tải.

Các kiểu hiển thị thường gặp:

- Số và boolean: hiển thị giá trị trực tiếp.
- Chuỗi: có thể hiển thị dấu quote để phân biệt với text thường.
- List: hiển thị số phần tử và một số phần tử đầu.
- Map/object: hiển thị tên trường và giá trị.
- Domain object: hiển thị dạng rút gọn với định danh chính.
- Diagnostic: mã lỗi, vị trí, severity và thông điệp.
- Future/async result: hiển thị trạng thái đang chạy hoặc kết quả khi hoàn tất.

Ví dụ:

~~~text
dsl> services()
[
  Service(name="catalog", replicas=3),
  Service(name="checkout", replicas=2)
]
2 items
~~~

Với dữ liệu lớn, renderer nên có giới hạn số dòng hoặc độ sâu. Người dùng có thể gọi lệnh inspect hoặc show để xem chi tiết. Không nên in toàn bộ object graph nếu nó có vòng tham chiếu hoặc chứa dữ liệu nhạy cảm.

## 13. Diagnostics trong REPL

Thông báo lỗi nên cho biết người dùng cần sửa gì và ở đâu. Vì input có thể gồm nhiều dòng, REPL nên hiển thị line/column tương đối với đoạn nhập hiện tại.

Ví dụ:

~~~text
dsl> service "catalog" {
...     replicas =
... }
error DSL-PARSE-EXPECTED-EXPRESSION at 2:16
Expected an expression after '='.
    replicas =
               ^
~~~

Các nhóm lỗi nên được phân biệt:

- Lexical error: ký tự hoặc escape không hợp lệ.
- Syntax error: cấu trúc không khớp grammar.
- Incomplete input: cần thêm dòng.
- Name resolution error: tên chưa được khai báo.
- Type error: kiểu không tương thích.
- Domain validation error: vi phạm bất biến miền.
- Runtime error: lỗi khi đánh giá.
- Permission/policy error: thao tác không được phép.

Nếu REPL chạy trong workspace, diagnostics có thể chứa cả vị trí input tạm và vị trí file được load. Renderer cần phân biệt hai nguồn để người dùng không nhầm line 2 của prompt với line 2 của tệp.

## 14. History và điều hướng dòng

History lưu những lệnh đã nhập để người dùng có thể gọi lại bằng phím mũi tên hoặc lệnh history. Một history hữu ích cần quyết định:

- Có lưu input lỗi không.
- Có lưu input nhiều dòng thành một entry không.
- Có loại bỏ lệnh nhạy cảm không.
- Lịch sử được lưu trong bộ nhớ hay trên đĩa.
- Có giới hạn số entry không.
- Có tách history theo project hoặc user không.

Không nên lưu password, token, secret hoặc dữ liệu nhạy cảm vào history. Nếu DSL có lệnh nhập credential, cần dùng prompt bảo mật hoặc cơ chế secret store thay vì ghi nội dung vào file lịch sử.

Input nhiều dòng nên được lưu thành một entry hoàn chỉnh, không phải từng dòng rời rạc, để khi gọi lại không làm sai cấu trúc.

## 15. Tab completion và gợi ý ngữ cảnh

Completion giúp người dùng khám phá DSL mà không cần nhớ mọi tên. REPL có thể gợi ý:

- Từ khóa hợp lệ tại vị trí hiện tại.
- Tên biến và hàm trong session.
- Thuộc tính của object miền.
- Tên module hoặc namespace đã import.
- Meta-command.
- Đường dẫn file sau lệnh load.
- Giá trị enum hoặc option hợp lệ.

Completion cần dùng parser hoặc context analyzer để biết vị trí hiện tại đang mong đợi loại token nào. Một danh sách từ khóa tĩnh có thể gợi ý sai trong chuỗi, comment hoặc biểu thức con.

Ví dụ:

~~~text
dsl> service "catalog" {
...     rep<TAB>
replicas
~~~

Với tên miền, cần tôn trọng scope và visibility. Không nên gợi ý secret hoặc tài nguyên mà người dùng không có quyền truy cập.

## 16. History, completion và input terminal

Terminal có thể hỗ trợ line editing, history, completion và signal như Ctrl+C. Một số runtime Java dùng thư viện terminal như JLine để có các khả năng này. Nếu không dùng thư viện, có thể triển khai reader cơ bản nhưng cần hiểu rằng console chuẩn của Java không cung cấp đầy đủ trải nghiệm tương tác trên mọi terminal.

Các yếu tố cần xem xét:

- Terminal hỗ trợ ANSI color hay không.
- Môi trường không tương tác như CI hoặc pipe.
- Windows Terminal, PowerShell và Unix shell.
- Unicode và độ rộng ký tự hiển thị.
- Paste nhiều dòng.
- Ctrl+C và Ctrl+D hoặc EOF.
- Resize terminal.
- Input redirection.

Nếu stdin không phải terminal tương tác, REPL có thể chuyển sang chế độ batch hoặc báo rằng interactive mode không khả dụng. Không nên in prompt vào output khi dữ liệu đang được pipe qua công cụ khác.

## 17. Tác dụng phụ và transaction trong session

Không phải mọi câu lệnh đều chỉ tính toán một giá trị. Một DSL có thể cho phép:

- Tạo hoặc sửa đối tượng miền.
- Ghi file.
- Gọi API.
- Khởi chạy tác vụ.
- Triển khai tài nguyên.
- Gửi thông điệp hoặc phát event.

REPL nên phân loại thao tác theo mức tác động. Có thể cung cấp môi trường mặc định an toàn, trong đó thao tác bên ngoài bị mô phỏng hoặc cần xác nhận.

Với các thay đổi chỉ nằm trong session, có thể dùng transaction:

1. Bắt đầu một evaluation context tạm.
2. Thực hiện các thay đổi trên bản sao hoặc transaction.
3. Nếu thành công, commit vào session.
4. Nếu lỗi, rollback thay đổi của câu lệnh.

Cần phân biệt rollback trạng thái bộ nhớ với rollback tác dụng ngoài. Một API call hoặc email đã gửi thường không thể hoàn tác chỉ bằng cách khôi phục biến session. Vì vậy, các thao tác không thể đảo ngược cần được kiểm soát riêng.

## 18. Undo và lịch sử thay đổi

Undo có thể hữu ích khi REPL cho phép cập nhật mô hình. Một cách triển khai là lưu snapshot trước mỗi command hoặc lưu command log có khả năng đảo ngược.

Các chiến lược:

- **Snapshot:** lưu bản sao environment trước thao tác.
- **Command undo:** mỗi command cung cấp hành động đảo ngược.
- **Transaction log:** ghi các thay đổi và trạng thái commit.
- **Persistent data structure:** tạo phiên bản environment mới mà không sửa phiên bản cũ.

Snapshot dễ hiểu nhưng có thể tốn bộ nhớ nếu mô hình lớn. Command undo tiết kiệm hơn nhưng mỗi thao tác cần định nghĩa inverse chính xác. Không phải hành động nào cũng đảo ngược được, nhất là khi gọi hệ thống bên ngoài.

Nếu không thể undo một lệnh, REPL cần nói rõ thay vì giả vờ đã hoàn tác. Có thể cung cấp undo chỉ cho nhóm thao tác được hỗ trợ.

## 19. Load và save trong REPL

Một REPL cho DSL có thể cho phép nạp tệp vào session:

~~~text
dsl> :load config/dev.dsl
Loaded 4 declarations.
dsl> :validate
No errors.
~~~

Lệnh load cần xác định nội dung được nạp vào scope nào, có ghi đè khai báo hiện có không và xử lý import như thế nào. Nếu file có lỗi, session có thể từ chối toàn bộ, nạp phần hợp lệ trong chế độ preview hoặc tạo workspace tạm. Policy phải rõ.

Lệnh save có thể ghi session model thành DSL hoặc định dạng khác:

~~~text
dsl> :save session.dsl
Wrote session.dsl
~~~

Trước khi ghi, cần kiểm chứng mô hình, xác nhận đường dẫn và bảo vệ tệp hiện có. Nếu serializer không thể biểu diễn một phần trạng thái session, phải báo lỗi thay vì bỏ dữ liệu âm thầm.

## 20. Context workspace và import module

Một REPL có thể hoạt động độc lập hoặc gắn với workspace. Trong workspace mode, nó có thể dùng cùng module resolution, schema và symbol index với project.

Ví dụ:

~~~text
dsl> :workspace open ./sample-project
Workspace loaded.
dsl> import module "services"
dsl> service "catalog"
Service(name="catalog", replicas=3)
~~~

Workspace context cần được tách khỏi session-local declarations. Một biến tạm không nên được ghi vào module nguồn trừ khi người dùng thực hiện thao tác save hoặc export rõ ràng.

Nếu workspace thay đổi từ bên ngoài trong lúc REPL mở, cần cập nhật index và xác định các giá trị session nào còn hợp lệ. Có thể giữ snapshot workspace cho phiên hiện tại hoặc refresh theo lệnh tường minh.

## 21. Bảo mật và sandbox

REPL có thể là giao diện rất mạnh vì nó cho phép thực thi biểu thức tùy ý trong môi trường. Nếu DSL có file I/O, network, process execution, reflection hoặc plugin, người dùng có thể gây tác động lớn.

Các biện pháp cần cân nhắc:

- Chạy trong sandbox hoặc process cô lập khi input không tin cậy.
- Chỉ cấp các capability cần thiết.
- Mặc định tắt thao tác phá hủy hoặc yêu cầu xác nhận.
- Giới hạn thời gian thực thi và số bước.
- Giới hạn bộ nhớ, kích thước output và độ sâu đệ quy.
- Hạn chế truy cập file theo workspace root.
- Kiểm soát network và external process.
- Không hiển thị hoặc lưu secret trong output/history.
- Kiểm tra quyền ở runtime cho mỗi hành động.
- Có cơ chế hủy lệnh đang chạy.

Một DSL an toàn về cú pháp không tự động an toàn khi thực thi. Validation tĩnh không thay thế sandbox hoặc kiểm soát quyền. Nếu REPL kết nối môi trường production, cần tách rõ read-only inspection và các thao tác thay đổi trạng thái.

## 22. Timeout, cancellation và lệnh chạy lâu

Một biểu thức có thể chạy vô hạn, gọi API chậm hoặc chờ một tác vụ không hoàn tất. REPL cần có cơ chế giới hạn:

- Timeout theo command.
- Cancellation token.
- Giới hạn số bước evaluator.
- Giới hạn đệ quy hoặc độ sâu.
- Giới hạn output.
- Giới hạn số tác vụ song song.
- Hiển thị trạng thái đang chạy.

Ví dụ:

~~~text
dsl> deploy "production"
Running... (Ctrl+C to cancel)
Deployment cancelled.
~~~

Cancellation chỉ có tác dụng nếu evaluator và các dịch vụ được gọi hỗ trợ hủy hợp tác. Nếu thao tác bên ngoài đã commit, việc hủy client không đảm bảo hành động đó được đảo ngược.

## 23. REPL cho DSL khai báo và DSL mệnh lệnh

DSL khai báo thường mô tả trạng thái mong muốn thay vì yêu cầu từng bước thực thi. REPL cho loại DSL này có thể:

- Nhận fragment khai báo.
- Ghép fragment vào mô hình tạm.
- Validate toàn mô hình.
- Hiển thị diff hoặc kế hoạch áp dụng.
- Chạy mô phỏng.
- Export cấu hình.

Ví dụ:

~~~text
dsl> service "catalog" { replicas = 3 }
Added service to session model.
dsl> :plan
CREATE service catalog
dsl> :validate
No errors.
~~~

DSL mệnh lệnh có thể đánh giá từng biểu thức hoặc câu lệnh tuần tự. REPL cần duy trì biến và trạng thái thực thi, đồng thời xác định semantics của lỗi giữa chuỗi lệnh.

Với DSL khai báo, việc đánh giá một fragment riêng lẻ có thể không đủ vì quy tắc miền phụ thuộc toàn mô hình. Khi đó, mỗi lần nhập có thể cập nhật model tạm rồi validate toàn bộ.

## 24. REPL và kiểu dữ liệu

Một REPL hữu ích có thể cung cấp lệnh xem kiểu hoặc giá trị suy luận:

~~~text
dsl> let timeout = 30s
30s
dsl> :type timeout
Duration
dsl> timeout + 5s
35s
~~~

Type inspection giúp người dùng hiểu literal, overload, generic hoặc kiểu miền. Nếu DSL hỗ trợ type inference, REPL có thể hiển thị kiểu suy luận cùng nguồn gốc:

~~~text
dsl> [1, 2, 3]
List<Integer>
~~~

Kết quả type nên dùng cùng type checker với compiler. Nếu REPL tự suy luận theo một bộ quy tắc khác, người dùng sẽ gặp hành vi không nhất quán giữa thử nghiệm và build.

## 25. REPL và hàm built-in

DSL có thể cung cấp built-in functions cho xử lý chuỗi, số, ngày giờ, collection hoặc mô hình miền.

Ví dụ:

~~~text
dsl> length("catalog")
7
dsl> contains(["dev", "test"], "dev")
true
dsl> now()
2026-11-15T...
~~~

Các hàm phụ thuộc thời gian, random hoặc môi trường có thể làm kết quả không deterministic. Cần xác định chúng có được phép trong cấu hình tĩnh hay chỉ dùng trong REPL/runtime. Nếu build cần tái lập, hàm đọc thời gian hiện tại có thể cần clock được inject thay vì truy cập trực tiếp system clock.

## 26. Tích hợp REPL với Language Server và IDE

REPL có thể chạy độc lập trong terminal hoặc tích hợp vào IDE như một console. Khi tích hợp, nó có thể dùng language server để cung cấp:

- Completion và hover trong dòng đang nhập.
- Syntax highlighting.
- Diagnostics trước khi chạy.
- Hiển thị kiểu suy luận.
- Điều hướng đến khai báo.
- Chạy selection hoặc expression từ editor.
- Chuyển diagnostics runtime về source span.

Console và editor cần chia sẻ cùng định nghĩa language version, schema, module path và position encoding. Tuy nhiên, session state của REPL thường khác workspace state của editor. Một biến khai báo trong console có thể không tồn tại trong tệp và ngược lại.

Nếu REPL dùng chung language server, cần xác định một virtual document URI cho input tạm hoặc một session context riêng. Không nên giả vờ input console là một file thật nếu điều đó làm file watcher hoặc workspace index xử lý sai.

## 27. Ghi log và khả năng quan sát

REPL có thể ghi lại:

- Thời điểm bắt đầu/kết thúc command.
- Loại command và thời gian đánh giá.
- Mã lỗi hoặc kết quả.
- Session ID và workspace revision.
- Cancellation và timeout.
- Tài nguyên sử dụng ở mức tổng hợp.

Không nên ghi toàn bộ input mặc định nếu input có thể chứa secret hoặc dữ liệu riêng tư. Nếu cần audit, nên có policy rõ về nội dung nào được lưu, ai có quyền xem và thời gian lưu.

Một command có thể hiển thị thời gian:

~~~text
dsl> :time 2 + 3
5
Completed in 0.4 ms
~~~

Thông tin thời gian có thể hữu ích khi khám phá hiệu năng, nhưng không nên xem số đo của một lần chạy đơn lẻ là benchmark đáng tin cậy. JIT, cache và hoạt động nền có thể ảnh hưởng kết quả.

## 28. Ví dụ triển khai vòng lặp REPL bằng Java

Một vòng lặp đơn giản có thể dùng BufferedReader và một interface evaluator:

~~~java
interface Evaluator {
    EvaluationResult evaluate(String input, Session session);
}

record EvaluationResult(
    boolean complete,
    Object value,
    List<Diagnostic> diagnostics
) {}

final class Repl {
    private final BufferedReader reader;
    private final PrintWriter output;
    private final Evaluator evaluator;
    private final Session session;

    Repl(
            BufferedReader reader,
            PrintWriter output,
            Evaluator evaluator,
            Session session) {
        this.reader = reader;
        this.output = output;
        this.evaluator = evaluator;
        this.session = session;
    }

    void run() throws IOException {
        StringBuilder buffer = new StringBuilder();

        while (true) {
            output.print(buffer.isEmpty() ? "dsl> " : "... ");
            output.flush();

            String line = reader.readLine();
            if (line == null) {
                break;
            }

            if (buffer.isEmpty() && line.equals(":quit")) {
                break;
            }

            buffer.append(line).append('\n');

            EvaluationResult result =
                evaluator.evaluate(buffer.toString(), session);

            if (!result.complete()) {
                continue;
            }

            render(result);
            buffer.setLength(0);
        }
    }

    private void render(EvaluationResult result) {
        for (Diagnostic diagnostic : result.diagnostics()) {
            output.println(diagnostic.message());
        }
        if (result.value() != null) {
            output.println(result.value());
        }
        output.flush();
    }
}
~~~

Đây là ví dụ kiến trúc giản lược. Một evaluator thực tế cần phân biệt incomplete input với invalid input; nếu invalid, REPL thường phải hiển thị diagnostics và reset buffer thay vì tiếp tục tích lũy vô hạn. Lệnh meta-command cũng cần được phân tích trước hoặc qua một parser riêng. Ngoài ra, code production cần xử lý Ctrl+C, history, completion, encoding và cancellation.

## 29. Tách parser khỏi evaluator

Parser nên trả AST hoặc trạng thái parse, không nên tự thực thi câu lệnh trong lúc nhận token. Tách biệt giúp REPL:

- Kiểm tra cú pháp trước khi chạy.
- Hiển thị AST hoặc kiểu suy luận.
- Tạo preview.
- Từ chối lệnh theo execution policy.
- Dùng cùng parser cho file và REPL.
- Thực hiện transaction hoặc rollback quanh evaluator.

Một pipeline có thể là:

~~~text
Input
  -> Lexer
  -> Parser
  -> AST
  -> Name resolution
  -> Type checking
  -> Policy check
  -> Evaluator
  -> Result renderer
~~~

Nếu DSL hỗ trợ meta-command, controller có thể nhận diện chúng trước pipeline ngôn ngữ. Tuy nhiên, lệnh xem kiểu có thể cần parse phần biểu thức phía sau bằng parser DSL để dùng đúng grammar.

## 30. Kiểm thử REPL

Kiểm thử REPL cần bao gồm vòng lặp, session state, parser và tương tác terminal ở mức phù hợp.

### 30.1. Kiểm thử chu trình cơ bản

- Nhập một biểu thức hợp lệ và nhận kết quả.
- Nhập nhiều biểu thức liên tiếp.
- Nhập câu lệnh khai báo rồi dùng biến ở câu lệnh sau.
- Thoát bằng lệnh quit hoặc EOF.
- Lỗi một câu lệnh không làm dừng toàn bộ REPL.

### 30.2. Kiểm thử input nhiều dòng

- Block mở và đóng qua nhiều dòng.
- Chuỗi nhiều dòng.
- Comment có delimiter.
- Input incomplete rồi tiếp tục.
- Input invalid và reset buffer.
- Hủy input bằng phím điều khiển.

### 30.3. Kiểm thử session

- Biến tồn tại qua nhiều lệnh.
- Scope cục bộ kết thúc đúng.
- Khai báo trùng theo policy.
- Reset xóa đúng trạng thái.
- Import module và workspace context hoạt động đúng.
- Lỗi evaluation không để lại trạng thái dở dang nếu transaction được yêu cầu.

### 30.4. Kiểm thử output và diagnostics

- Giá trị số, chuỗi, list và object.
- Lỗi syntax, name, type và runtime.
- Vị trí dòng/cột nhiều dòng.
- Output lớn được giới hạn.
- Secret không xuất hiện trong history hoặc log.

### 30.5. Kiểm thử an toàn

- Lệnh vượt timeout.
- Cancellation.
- Truy cập file ngoài workspace.
- Network hoặc process execution bị policy chặn.
- Output và memory limit.
- Nhiều session không chia sẻ trạng thái ngoài ý muốn.

## 31. Quy trình xây dựng REPL cho DSL

Có thể triển khai theo trình tự:

1. **Xác định use case:** REPL để học cú pháp, tính biểu thức, khám phá model hay thao tác workspace.
2. **Tái sử dụng frontend:** dùng lexer, parser, type checker và diagnostics của DSL.
3. **Định nghĩa input model:** expression, statement, declaration và meta-command.
4. **Xử lý incomplete input:** parser phải cho biết khi nào cần dòng tiếp theo.
5. **Thiết kế Session:** quản lý scope, biến, import và trạng thái tạm.
6. **Xây evaluator:** tách đánh giá khỏi parser và kiểm soát side effect.
7. **Thiết kế renderer:** hiển thị giá trị, lỗi, kiểu và object miền dễ đọc.
8. **Thêm history/completion:** dùng context parser và tránh lưu secret.
9. **Quản lý lệnh chạy lâu:** timeout, cancellation và giới hạn tài nguyên.
10. **Xác định policy:** sandbox, quyền file/network và thao tác cần xác nhận.
11. **Tích hợp workspace/IDE:** đồng bộ language version và source locations.
12. **Kiểm thử lifecycle:** lỗi, multiline, reset, concurrency và trạng thái session.

## 32. Nguyên tắc thiết kế

- **Dùng chung frontend với compiler:** tránh khác biệt grammar giữa REPL và file.
- **Phân biệt incomplete và invalid:** cho phép nhập block nhiều dòng tự nhiên.
- **Giữ session state có chủ đích:** xác định scope và thời gian tồn tại của khai báo.
- **Tách meta-command khỏi grammar:** tránh xung đột cú pháp và xử lý lệnh rõ ràng.
- **Tách parse khỏi evaluate:** có thể kiểm tra, preview và áp dụng policy trước khi chạy.
- **Bảo vệ trạng thái khi lỗi:** dùng transaction hoặc snapshot cho thay đổi có thể rollback.
- **Hiển thị diagnostics theo nguồn:** phân biệt input tạm với file trong workspace.
- **Giữ history an toàn:** không lưu secret và giới hạn dung lượng.
- **Completion theo ngữ cảnh:** gợi ý tên và từ khóa hợp lệ tại vị trí hiện tại.
- **Kiểm soát side effect:** read-only, simulation hoặc xác nhận trước hành động quan trọng.
- **Giới hạn tài nguyên:** timeout, cancellation, memory và output limit.
- **Tách session khỏi workspace:** biến tạm không tự động ghi vào dự án.
- **Hỗ trợ phục hồi:** lỗi một lệnh không làm sập phiên.
- **Kiểm thử như một công cụ tương tác:** bao gồm terminal, Unicode, multiline và nhiều phiên.

REPL biến DSL thành một môi trường có thể khám phá và thử nghiệm từng bước. Khi vòng lặp đọc-phân tích-đánh giá-hiển thị được tổ chức rõ, parser nhận biết input chưa hoàn chỉnh, session quản lý trạng thái nhất quán và evaluator được giới hạn bởi policy phù hợp, người dùng có thể học cú pháp, kiểm tra mô hình và điều tra vấn đề nhanh chóng mà vẫn giữ được tính đúng đắn và an toàn của hệ thống.
