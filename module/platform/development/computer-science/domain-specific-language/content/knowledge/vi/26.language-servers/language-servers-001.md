# Vai trò của Language Server Protocol (LSP)

Ngôn ngữ đặc tả miền (Domain-Specific Language, DSL) thường có cú pháp và quy tắc riêng. Người viết DSL cần được hỗ trợ khi nhập mã, tìm lỗi, tra cứu định nghĩa, đổi tên thành phần hoặc hiểu ý nghĩa của một biểu thức. Nếu mỗi trình soạn thảo phải tự triển khai toàn bộ những chức năng này cho từng DSL, chi phí phát triển và bảo trì sẽ rất lớn.

**Language Server Protocol (LSP)** là giao thức chuẩn hóa cách một công cụ soạn thảo giao tiếp với một tiến trình hiểu ngôn ngữ. Tiến trình đó thường được gọi là language server. Editor gửi thông tin về tài liệu, vị trí con trỏ và yêu cầu hỗ trợ; language server phân tích tài liệu rồi trả về chẩn đoán, gợi ý hoàn thành, thông tin kiểu, định nghĩa, tham chiếu và nhiều kết quả khác.

Với DSL, LSP tạo một ranh giới rõ giữa phần hiểu ngôn ngữ và phần giao diện người dùng. Compiler hoặc parser của DSL có thể được dùng bên trong language server, trong khi nhiều editor khác nhau cùng sử dụng một giao thức để cung cấp trải nghiệm nhất quán. LSP không thay thế compiler, parser hay hệ kiểu; nó quy định cách những năng lực đó được cung cấp cho công cụ phát triển.

## 1. Language Server Protocol là gì?

### 1.1. Khái niệm

LSP là giao thức trao đổi thông điệp giữa:

- **Language client:** phần tích hợp trong editor hoặc IDE. Client quản lý giao diện, tài liệu đang mở, vị trí con trỏ và hiển thị kết quả.
- **Language server:** tiến trình hiểu một ngôn ngữ. Server phân tích tài liệu, xây dựng mô hình ngữ nghĩa và trả kết quả theo các yêu cầu của client.

Ví dụ, khi người dùng đặt con trỏ lên một tên trong file DSL và yêu cầu xem thông tin, client gửi yêu cầu hover. Server phân giải tên, xác định kiểu hoặc khai báo tương ứng rồi trả về nội dung để editor hiển thị.

### 1.2. LSP giải quyết vấn đề gì?

Trước LSP, một công cụ ngôn ngữ thường phải tích hợp riêng với từng editor. Mỗi editor có API, mô hình sự kiện và định dạng kết quả khác nhau. Khi có nhiều DSL và nhiều editor, số lượng tích hợp cần duy trì tăng nhanh.

LSP chuẩn hóa phần giao tiếp:

~~~text
                 +----------------------+
                 |   DSL Language       |
                 |   Server             |
                 +----------+-----------+
                            |
                         LSP / JSON-RPC
                            |
             +--------------+--------------+
             |              |              |
       +-----v----+   +-----v----+   +-----v----+
       | Editor A |   | Editor B |   | Editor C |
       +----------+   +----------+   +----------+
~~~

Một language server có thể phục vụ nhiều client hỗ trợ LSP. Một editor cũng có thể kết nối với nhiều server cho các ngôn ngữ khác nhau.

### 1.3. LSP không phải compiler

LSP không định nghĩa grammar, kiểu dữ liệu, quy tắc phân giải tên hoặc cách thực thi DSL. Nó định nghĩa thông điệp để client yêu cầu những dịch vụ ngôn ngữ đó.

Ví dụ:

- Parser xác định tài liệu có cấu trúc cú pháp nào.
- Name resolver tìm khai báo mà một tên tham chiếu đến.
- Type checker xác định kiểu của biểu thức.
- LSP quy định cách client yêu cầu definition, hover hoặc diagnostics và cách server trả kết quả.

Một server có thể dùng compiler hiện có, một thư viện parser hoặc một bộ phân tích riêng. Điều quan trọng là kết quả được chuyển thành cấu trúc LSP hợp lệ.

### 1.4. LSP và language server

LSP là giao thức; language server là implementation sử dụng giao thức. Một server có thể hỗ trợ đầy đủ hoặc chỉ một tập tính năng. Client và server thương lượng khả năng để tránh gọi những tính năng mà phía kia không hỗ trợ.

## 2. Kiến trúc client-server

### 2.1. Trách nhiệm của language client

Client thường đảm nhiệm:

- Mở, chỉnh sửa, lưu và đóng tài liệu.
- Gửi nội dung hoặc thay đổi tài liệu đến server.
- Gửi yêu cầu theo vị trí con trỏ hoặc vùng chọn.
- Hiển thị lỗi, warning và thông tin.
- Hiển thị completion list, hover và signature help.
- Áp dụng text edit hoặc workspace edit sau khi người dùng chấp nhận.
- Quản lý tiến trình server và vòng đời kết nối.
- Chuyển thông điệp giao thức thành tương tác giao diện.

Client không nhất thiết phải hiểu semantics chi tiết của DSL. Nó cần biết cách diễn giải kết quả LSP.

### 2.2. Trách nhiệm của language server

Server thường đảm nhiệm:

- Quản lý workspace và tài liệu.
- Phân tích cú pháp DSL.
- Xây dựng AST hoặc mô hình tài liệu.
- Phân giải tên và import.
- Kiểm tra kiểu và ràng buộc miền.
- Tạo diagnostics.
- Tìm completion, definition, references và symbols.
- Tạo code actions và edits.
- Theo dõi thay đổi file hoặc cấu hình nếu được hỗ trợ.
- Quản lý cache và công việc nền.

Server có thể chia thành các thành phần nội bộ như document manager, parser, semantic model, indexer và feature providers.

### 2.3. Compiler và language server có thể dùng chung lõi

Một kiến trúc tốt thường dùng chung frontend:

~~~text
                    +------------------+
                    | DSL Core         |
                    | Lexer / Parser   |
                    | Resolver / Types |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
       +------v-------+              +------v-------+
       | Compiler CLI |              | LSP Server   |
       +--------------+              +--------------+
              |                             |
        Build artifact                 Editor features
~~~

Nhờ dùng chung parser và semantic model, compiler và language server có thể đưa ra kết quả nhất quán. Nếu hai thành phần triển khai logic phân tích riêng, chúng có thể bất đồng về lỗi, kiểu hoặc cách phân giải tên.

### 2.4. Một server cho nhiều workspace

Một tiến trình server có thể phục vụ một hoặc nhiều workspace folder tùy khả năng client và server. Server cần quản lý phạm vi index, cấu hình, dependency và quyền truy cập cho từng workspace.

Không nên giả định mọi tài liệu mở đều thuộc cùng một dự án hoặc dùng cùng một schema.

## 3. Giao thức nền tảng: JSON-RPC

### 3.1. JSON-RPC 2.0

LSP sử dụng mô hình thông điệp dựa trên JSON-RPC 2.0. Có ba dạng chính:

- Request: có method, params và id; bên nhận phải trả response.
- Response: chứa id tương ứng cùng result hoặc error.
- Notification: có method và params nhưng không yêu cầu response.

Ví dụ request khái niệm:

~~~json
{
  "jsonrpc": "2.0",
  "id": 7,
  "method": "textDocument/hover",
  "params": {
    "textDocument": {
      "uri": "file:///workspace/rules/discount.dsl"
    },
    "position": {
      "line": 4,
      "character": 18
    }
  }
}
~~~

Thông điệp thực tế trong LSP thường được đóng khung bằng header Content-Length theo transport. Ví dụ trên chỉ minh họa phần JSON payload.

### 3.2. Request và notification

Request phù hợp khi client cần kết quả như hover, completion hoặc definition. Notification phù hợp khi client thông báo tài liệu đã thay đổi hoặc server báo diagnostics bằng cơ chế push.

Server không được trả response cho notification vì notification không có request id.

### 3.3. Response và lỗi giao thức

Response có thể chứa result hoặc error. LSP quy định một số mã lỗi JSON-RPC và mã riêng cho các tình huống như request bị hủy hoặc method không được hỗ trợ.

Không nên biểu diễn một lỗi phân tích DSL như lỗi transport. Một tài liệu sai cú pháp vẫn là đầu vào hợp lệ cho giao thức; server nên trả diagnostics thay vì đóng kết nối.

### 3.4. Transport

Các transport thường gặp:

- Standard input/output (stdio): editor khởi chạy server như một tiến trình con và trao đổi qua stdin/stdout.
- Socket hoặc kết nối mạng: client và server trao đổi qua một kênh được cấu hình.

Stdio phổ biến trong môi trường desktop vì đơn giản và không cần mở cổng mạng. Nếu dùng socket, cần kiểm soát xác thực, địa chỉ bind và quyền truy cập.

### 3.5. Framing thông điệp

Transport stdio của LSP dùng header như Content-Length để xác định số byte của JSON payload:

~~~text
Content-Length: 72

{"jsonrpc":"2.0","method":"initialized","params":{}}
~~~

Độ dài được tính theo byte của payload theo quy định transport, không phải số ký tự hiển thị. Server cần đọc đủ header, xác định độ dài, đọc đúng số byte rồi mới parse JSON.

### 3.6. Stdout và stderr

Khi dùng stdio, stdout dành cho thông điệp LSP. Log thông thường nên ghi ra stderr hoặc hệ thống logging riêng. Nếu in log tùy tiện vào stdout, client có thể hiểu nhầm log là một thông điệp giao thức và mất kết nối.

## 4. Vòng đời của language server

### 4.1. Khởi tạo

Client gửi initialize request với thông tin về:

- Process hoặc client identity.
- Root URI hoặc workspace folders.
- Client capabilities.
- Initialization options.
- Phiên bản hoặc thông tin môi trường liên quan.

Server trả về server capabilities và thông tin phiên bản của server nếu có.

### 4.2. initialized

Sau khi nhận initialize response, client gửi notification initialized. Đây là dấu mốc cho biết quá trình khởi tạo giao thức đã hoàn tất và server có thể bắt đầu những hoạt động phù hợp với capabilities đã thương lượng.

### 4.3. Hoạt động bình thường

Trong giai đoạn hoạt động, client và server trao đổi:

- Notification về thay đổi tài liệu.
- Request về completion, hover, definition và những tính năng khác.
- Diagnostics, progress và notification từ server.
- Configuration hoặc workspace change.

### 4.4. Shutdown

Khi client muốn kết thúc phiên, nó gửi shutdown request. Server hoàn tất hoặc hủy công việc cần thiết và trả response. Sau đó client gửi exit notification để kết thúc tiến trình theo vòng đời giao thức.

### 4.5. Sơ đồ vòng đời

~~~mermaid
sequenceDiagram
    participant C as Language Client
    participant S as Language Server
    C->>S: initialize(capabilities, workspace)
    S-->>C: InitializeResult(server capabilities)
    C->>S: initialized
    C->>S: textDocument/didOpen
    C->>S: textDocument/hover
    S-->>C: Hover result
    S-->>C: publishDiagnostics
    C->>S: shutdown
    S-->>C: null result
    C->>S: exit
~~~

Server cần xử lý shutdown và exit đúng cách để editor không để lại tiến trình mồ côi.

## 5. Capability negotiation

### 5.1. Vì sao cần capabilities?

Không phải mọi client hoặc server đều hỗ trợ mọi tính năng. Client có thể hỗ trợ semantic tokens nhưng không hỗ trợ một số dạng completion item; server có thể hỗ trợ definition nhưng chưa triển khai rename.

Capabilities cho phép hai phía công bố những gì mình hỗ trợ trước khi dùng tính năng.

### 5.2. Client capabilities

Client gửi capabilities trong initialize request. Chúng có thể mô tả:

- Khả năng hiển thị diagnostics.
- Completion item kinds và snippets.
- Hỗ trợ markdown trong hover.
- Hỗ trợ semantic token modifiers.
- Hỗ trợ workspace edits.
- Khả năng xử lý progress và partial results.
- Encoding vị trí được hỗ trợ.

Server cần đọc capabilities thay vì giả định client luôn hỗ trợ mọi dạng kết quả.

### 5.3. Server capabilities

Server trả về các khả năng như:

- Text document synchronization.
- Completion provider.
- Hover provider.
- Definition provider.
- References provider.
- Rename provider.
- Code action provider.
- Document symbol provider.
- Semantic tokens provider.
- Formatting provider.
- Workspace symbol provider.

Một số capability có thể được đăng ký động sau khi khởi tạo nếu giao thức và client hỗ trợ.

### 5.4. Static và dynamic registration

Static registration công bố khả năng trong initialize result. Dynamic registration cho phép server đăng ký hoặc hủy đăng ký một số tính năng trong thời gian chạy, ví dụ chỉ bật file watcher khi workspace có cấu hình tương ứng.

Nếu client không hỗ trợ dynamic registration cho một tính năng, server cần dùng cách khai báo tĩnh hoặc không cung cấp tính năng đó.

### 5.5. Không quảng cáo tính năng chưa hoàn chỉnh

Nếu server công bố rename provider nhưng không thể tạo edit an toàn cho mọi symbol hợp lệ, người dùng có thể gặp thay đổi dở dang. Capability nên phản ánh đúng mức hỗ trợ thực tế.

## 6. Đồng bộ tài liệu

### 6.1. Tài liệu đang mở là bản nguồn hiện thời

Khi người dùng mở file DSL, client thông báo cho server bằng textDocument/didOpen, kèm URI, languageId, version và nội dung văn bản.

Server thường giữ bản nội dung này trong bộ nhớ. Khi tài liệu đang mở có thay đổi chưa lưu, nội dung trong editor có thể khác file trên đĩa. Các tính năng LSP cần làm việc với phiên bản đang mở mà client gửi.

### 6.2. didChange

Khi người dùng nhập hoặc xóa văn bản, client gửi textDocument/didChange. Tùy chế độ đồng bộ, notification có thể chứa:

- Toàn bộ nội dung mới.
- Một hoặc nhiều text edit mô tả phần thay đổi.

Với incremental synchronization, server phải áp dụng các edit theo đúng thứ tự và đúng version.

### 6.3. Version tài liệu

Mỗi bản tài liệu đồng bộ thường có version do client quản lý. Server nên lưu version hiện tại để tránh áp dụng kết quả phân tích cũ lên tài liệu mới.

Ví dụ, server bắt đầu phân tích version 10, nhưng trong lúc xử lý client đã gửi version 11. Kết quả diagnostics của version 10 có thể đã lỗi thời và không nên ghi đè trạng thái mới.

### 6.4. didSave và didClose

didSave thông báo tài liệu đã được lưu. Server có thể dùng sự kiện này để chạy kiểm tra phụ thuộc file trên đĩa hoặc đồng bộ với công cụ build.

didClose thông báo tài liệu không còn mở. Server có thể giải phóng bản nội dung tạm và quay lại đọc file trên đĩa, tùy mô hình quản lý tài liệu.

### 6.5. Full và incremental sync

| Chế độ | Nội dung gửi | Ưu điểm | Chi phí |
|---|---|---|---|
| Full | Toàn bộ văn bản mới | Dễ triển khai, ít trạng thái edit | Tốn băng thông và xử lý với file lớn |
| Incremental | Các đoạn thay đổi | Hiệu quả với tài liệu lớn | Phải áp dụng range và version chính xác |

Server công bố chế độ đồng bộ trong capability. Client cần tuân theo chế độ đó.

### 6.6. Range và position

LSP biểu diễn vị trí bằng line và character. Việc diễn giải character phụ thuộc position encoding đã thương lượng. UTF-16 là cách tương thích mặc định trong nhiều phiên bản và implementation; các phiên bản LSP mới hơn cho phép thương lượng encoding khác nếu cả hai phía hỗ trợ.

Một ký tự Unicode có thể chiếm nhiều code unit hoặc byte. Server cần chuyển đổi đúng giữa offset nội bộ của parser và position mà LSP sử dụng.

### 6.7. Tài liệu chưa lưu và file ngoài workspace

Client có thể mở tài liệu chưa lưu hoặc tài liệu nằm ngoài workspace. Server cần xác định chính sách hỗ trợ và không giả định mọi URI là file tồn tại trên đĩa.

## 7. Diagnostics

### 7.1. Diagnostics là gì?

Diagnostics là thông tin về lỗi, warning hoặc vấn đề tiềm ẩn trong tài liệu. Với DSL, chúng có thể đến từ:

- Lexer và parser.
- Phân giải tên.
- Kiểm tra kiểu.
- Validation ràng buộc miền.
- Kiểm tra import và dependency.
- Linter hoặc quy tắc phong cách.

### 7.2. publishDiagnostics

Trong mô hình push, server gửi notification textDocument/publishDiagnostics cho client. Một diagnostic thường chứa:

- Range trong tài liệu.
- Severity.
- Code lỗi.
- Source hoặc tên công cụ phát hiện.
- Message.
- Related information nếu có.
- Tags hoặc data bổ sung nếu được hỗ trợ.

Ví dụ:

~~~json
{
  "range": {
    "start": { "line": 4, "character": 12 },
    "end": { "line": 4, "character": 22 }
  },
  "severity": 1,
  "code": "DSL_UNKNOWN_FIELD",
  "source": "dsl-language-server",
  "message": "Không tìm thấy thuộc tính discountRate trên kiểu Customer"
}
~~~

Range dùng chỉ số bắt đầu từ 0 theo mô hình LSP. Ví dụ chỉ minh họa cấu trúc diagnostic.

### 7.3. Push diagnostics

Server tự gửi diagnostics khi tài liệu thay đổi hoặc khi một dependency làm kết quả phân tích thay đổi. Đây là mô hình quen thuộc và đơn giản với tài liệu nhỏ hoặc server đã có cơ chế cập nhật phù hợp.

### 7.4. Pull diagnostics

Các phiên bản LSP mới hỗ trợ mô hình pull diagnostics, trong đó client yêu cầu diagnostics khi cần. Cách này có thể phù hợp với workspace lớn, kết quả cần cache hoặc server muốn kiểm soát tải tính toán.

Server có thể trả kết quả đầy đủ hoặc báo rằng kết quả không thay đổi dựa trên resultId. Với workspace diagnostics, client có thể yêu cầu kết quả trên nhiều tài liệu.

### 7.5. Chọn push hay pull

Lựa chọn phụ thuộc phiên bản giao thức, client capabilities, kích thước workspace và cách server quản lý trạng thái. Server cần công bố đúng capability và không trộn hai mô hình một cách thiếu nhất quán.

### 7.6. Xóa diagnostics cũ

Khi tài liệu không còn lỗi, server cần gửi trạng thái diagnostics mới hoặc danh sách rỗng theo cơ chế phù hợp. Nếu không, editor có thể tiếp tục hiển thị lỗi cũ.

### 7.7. Tránh diagnostics lỗi thời

Kết quả phân tích bất đồng bộ cần gắn với version tài liệu hoặc revision nội bộ. Trước khi publish, server kiểm tra kết quả có còn tương ứng với bản mới nhất hay không.

### 7.8. Related information

Một lỗi có thể liên quan đến nhiều vị trí. Ví dụ, tham chiếu đến field sai có thể liên kết đến khai báo schema gần nhất hoặc vị trí import. Related information giúp editor điều hướng đến nguồn liên quan.

## 8. Code completion

### 8.1. Mục đích

Completion gợi ý những tên, từ khóa, hàm, kiểu hoặc giá trị hợp lệ tại vị trí con trỏ. Đây là một trong những tính năng quan trọng nhất của language server.

### 8.2. Completion theo ngữ cảnh

Với DSL:

~~~text
rule GoldCustomer {
    when customer.
}
~~~

Sau dấu chấm, server có thể gợi ý các thuộc tính của kiểu Customer như tier, name hoặc email. Nếu người dùng đang ở vị trí cần toán tử, server có thể gợi ý toán tử so sánh phù hợp.

Completion cần dựa vào AST chưa hoàn chỉnh, scope, kiểu suy luận được và schema miền.

### 8.3. Completion item

Một completion item có thể chứa:

- Label hiển thị.
- Kind như function, field, class, keyword hoặc variable.
- Detail hoặc documentation.
- Insert text.
- Text edit.
- Sort text và filter text.
- Commit characters.
- Data riêng để resolve chi tiết sau.

### 8.4. Snippet

Server có thể cung cấp snippet cho cấu trúc DSL:

~~~text
rule RuleName {
    when condition
    then action
}
~~~

Client cần hỗ trợ snippet syntax để đặt placeholder và điều hướng giữa các vị trí.

### 8.5. Completion resolve

Ban đầu server có thể trả danh sách gọn. Khi người dùng chọn hoặc focus một item, client gửi completionItem/resolve để lấy documentation hoặc chi tiết bổ sung.

Điều này giúp giảm payload khi có nhiều gợi ý.

### 8.6. Incomplete completion

Với tập gợi ý lớn, server có thể đánh dấu danh sách chưa đầy đủ để client gửi yêu cầu tiếp theo theo cách giao thức hỗ trợ. Server cần dùng context và dữ liệu đã trả để xử lý nhất quán.

### 8.7. Gợi ý không hợp lệ

Không nên gợi ý mọi symbol trong workspace ở mọi vị trí. Một vị trí yêu cầu kiểu dữ liệu cần ưu tiên type; vị trí biểu thức cần giá trị hoặc hàm phù hợp; vị trí module cần namespace có thể import.

## 9. Hover và signature help

### 9.1. Hover

Hover trả thông tin về symbol hoặc biểu thức tại vị trí con trỏ:

- Tên và loại symbol.
- Kiểu dữ liệu.
- Chữ ký hàm.
- Documentation.
- Giá trị hoặc metadata có thể xác định.
- Vị trí khai báo hoặc module nguồn.

Ví dụ, khi hover lên order.total, server có thể trả:

~~~text
total: Money

Tổng tiền của đơn hàng trước khi áp dụng phí vận chuyển.
~~~

### 9.2. Markdown và nội dung hover

LSP cho phép trả nội dung markup, thường là plaintext hoặc Markdown tùy capability. Server cần công bố định dạng được hỗ trợ và tránh gửi HTML hoặc nội dung không an toàn ngoài quy tắc client.

### 9.3. Signature help

Khi người dùng nhập:

~~~text
calculateTax(order.total, )
~~~

Signature help có thể hiển thị:

~~~text
calculateTax(amount: Money, region: Region): Money
                         ^ region
~~~

Server xác định overload phù hợp và tham số đang được nhập. Client có thể hiển thị danh sách overload, active signature và active parameter.

### 9.4. Phân biệt hover và signature help

Hover giải thích symbol tại một vị trí. Signature help tập trung vào chữ ký hàm trong ngữ cảnh đang nhập đối số. Cùng một semantic model có thể phục vụ cả hai nhưng dữ liệu trả về khác nhau.

## 10. Điều hướng mã nguồn

### 10.1. Go to Definition

Definition giúp đi từ tham chiếu đến nơi khai báo. Với:

~~~text
applyDiscount(order, 0.15)
~~~

người dùng có thể yêu cầu mở định nghĩa applyDiscount.

Server cần phân giải tên trong scope hiện tại và trả location hoặc link phù hợp.

### 10.2. Declaration và Type Definition

Tùy client và capability, server có thể cung cấp:

- Declaration: nơi khai báo symbol.
- Type Definition: nơi định nghĩa kiểu của biểu thức hoặc biến.
- Implementation: nơi triển khai interface hoặc abstraction.

Các tính năng này hữu ích khi DSL cho phép module, interface hoặc hàm external.

### 10.3. Find References

References tìm mọi vị trí tham chiếu đến một symbol. Server có thể tìm trong tài liệu hiện tại hoặc toàn workspace tùy request và index.

### 10.4. Document Symbols

Document symbols cung cấp cây cấu trúc của một tài liệu:

~~~text
discounts.dsl
  Rule MemberDiscount
    Condition
    Action
  Rule FreeShipping
    Condition
    Action
~~~

Editor dùng thông tin này cho outline, breadcrumb và điều hướng trong file.

### 10.5. Workspace Symbols

Workspace symbols tìm symbol trên nhiều file hoặc module. Server thường cần index để truy vấn nhanh, đồng thời hỗ trợ filter theo tên.

### 10.6. Call hierarchy và type hierarchy

Nếu server có đủ semantic model, nó có thể cung cấp call hierarchy hoặc type hierarchy để người dùng khám phá quan hệ gọi hàm và kế thừa. Những tính năng này cần index và xử lý dependency chính xác.

## 11. Rename và refactoring

### 11.1. Rename symbol

Rename cho phép đổi tên một symbol và cập nhật những tham chiếu liên quan. Server cần:

1. Xác định symbol tại vị trí được chọn.
2. Kiểm tra tên mới hợp lệ.
3. Tìm tất cả tham chiếu cần cập nhật.
4. Kiểm tra xung đột trong scope và namespace.
5. Tạo WorkspaceEdit chứa những thay đổi cần thiết.

### 11.2. Vì sao không thể chỉ thay chuỗi?

Nếu đổi tên customer, không được thay mọi chuỗi chứa từ customer. Có thể có comment, string literal hoặc symbol khác cùng tên ở scope riêng.

Rename cần dựa vào identity và phân giải tên, không chỉ dựa vào text search.

### 11.3. Prepare rename

Server có thể cung cấp prepare rename để kiểm tra vị trí có thể rename và trả range hoặc placeholder trước khi client yêu cầu thay đổi.

### 11.4. WorkspaceEdit

WorkspaceEdit có thể chứa text edits cho một hoặc nhiều tài liệu. Client áp dụng thay đổi theo cơ chế của mình và có thể hiển thị xác nhận cho người dùng.

### 11.5. Code actions

Code action cung cấp thao tác sửa theo ngữ cảnh:

- Thêm import còn thiếu.
- Đổi tên field sai chính tả.
- Thêm giá trị bắt buộc.
- Chuyển kiểu tường minh.
- Tạo skeleton cho hàm.
- Sửa cú pháp theo diagnostic.

Code action có thể gắn với diagnostic hoặc xuất hiện theo vùng con trỏ.

### 11.6. Refactoring an toàn

Refactoring có thể thay đổi nhiều file. Server cần kiểm tra quyền ghi, xung đột tên, version tài liệu và khả năng cập nhật toàn bộ workspace. Nếu không thể bảo đảm edit nhất quán, nên từ chối hoặc cung cấp preview thay vì trả kết quả một phần.

## 12. Formatting và các tính năng hỗ trợ tài liệu

### 12.1. Document formatting

Formatting chuẩn hóa toàn bộ tài liệu theo style của DSL:

- Indentation.
- Khoảng trắng.
- Xuống dòng.
- Vị trí dấu ngoặc.
- Căn chỉnh hoặc bố cục tùy formatter.

Server trả danh sách TextEdit; client áp dụng vào tài liệu.

### 12.2. Range formatting

Range formatting chỉ định dạng một vùng. Nó hữu ích khi người dùng muốn sửa một block mà không thay đổi phần khác.

### 12.3. On-type formatting

Một số client có thể yêu cầu formatting khi người dùng nhập ký tự như dấu đóng ngoặc hoặc newline. Server cần phản hồi nhanh để không làm chậm thao tác gõ.

### 12.4. Folding ranges

Folding cho phép thu gọn block rule, function, schema hoặc workflow. Server trả range có thể gập.

### 12.5. Selection ranges

Selection ranges mô tả vùng chọn lồng nhau từ token đến biểu thức, câu lệnh và block. Editor có thể mở rộng vùng chọn theo cấu trúc ngôn ngữ.

### 12.6. Document links

Nếu DSL có import hoặc tham chiếu tài liệu, server có thể cung cấp document links để client mở file hoặc tài nguyên tương ứng.

### 12.7. Code lens

Code lens hiển thị hành động hoặc thông tin gắn trên một đoạn mã, chẳng hạn số tham chiếu, trạng thái kiểm tra hoặc lệnh chạy rule. Nội dung cần được tính từ dữ liệu đáng tin cậy và có thể resolve khi người dùng cần.

### 12.8. Inlay hints

Inlay hints chèn thông tin nhỏ trong editor mà không thay đổi source, ví dụ kiểu được suy luận hoặc tên tham số:

~~~text
let total = calculateTax(order)  // inferred: Money
~~~

Hint nên ngắn, hữu ích và không làm rối giao diện.

### 12.9. Semantic tokens

Semantic tokens cung cấp phân loại ngữ nghĩa cho token như class, function, property, enum member hoặc variable. Chúng giúp editor tô màu dựa trên symbol resolution thay vì chỉ dựa vào grammar.

Server có thể hỗ trợ full, range hoặc delta semantic tokens tùy capability. Delta giúp gửi ít dữ liệu hơn khi chỉ một phần tài liệu thay đổi.

## 13. Workspace và project model

### 13.1. Workspace folders

Một workspace có thể gồm một hoặc nhiều thư mục. Server cần biết phạm vi từng thư mục, cấu hình DSL và dependency.

### 13.2. Configuration

Client có thể gửi cấu hình cho server hoặc server có thể đọc file cấu hình dự án. Ví dụ:

~~~json
{
  "dsl": {
    "languageVersion": "2",
    "schemaPaths": ["schemas"],
    "strictTypes": true
  }
}
~~~

Server cần xác định nguồn cấu hình có thẩm quyền và cập nhật phân tích khi cấu hình thay đổi.

### 13.3. Workspace configuration

LSP có các cơ chế để server yêu cầu client cung cấp configuration. Server không nên giả định client hỗ trợ mọi dạng configuration request; cần xét capability và có fallback phù hợp.

### 13.4. File watching

Server có thể cần biết khi file schema, module hoặc dependency thay đổi dù file đó không đang mở. Có thể dùng workspace file operations hoặc file watcher theo khả năng client.

### 13.5. Indexing

Để hỗ trợ references và workspace symbols, server có thể index tài liệu trong workspace. Index cần cập nhật khi file thay đổi, được thêm, xóa hoặc đổi tên.

### 13.6. Multi-root và dependency graph

Nếu nhiều workspace folder cùng mở, server phải tránh trộn symbol có cùng tên nhưng thuộc project khác. Dependency graph cần xác định module nào được nhìn thấy từ tài liệu nào.

### 13.7. File chưa được mở

Server có thể cần đọc file chưa mở để phân giải import hoặc tìm references. Việc đọc cần tuân theo root và quyền được cấu hình, tránh quét toàn bộ ổ đĩa ngoài workspace.

## 14. Tính năng nâng cao và xử lý tác vụ dài

### 14.1. Cancellation

Người dùng có thể gõ tiếp hoặc di chuyển con trỏ trong khi một request đang chạy. Client có thể gửi cancellation notification cho request có id.

Server nên kiểm tra cancellation token trong công việc dài như workspace search, indexing hoặc semantic analysis. Không cần tiếp tục tính toán kết quả mà client không còn cần.

### 14.2. Progress

Server có thể báo tiến độ cho tác vụ dài như indexing workspace hoặc tải schema. Client có thể hiển thị progress indicator nếu hỗ trợ.

### 14.3. Partial results

Với kết quả lớn, một số request hỗ trợ trả dữ liệu theo từng phần. Server có thể gửi partial result để client hiển thị sớm thay vì chờ toàn bộ workspace được xử lý.

### 14.4. Debounce và coalesce

Khi người dùng gõ nhanh, server có thể gom nhiều thay đổi hoặc trì hoãn phân tích trong một khoảng ngắn để tránh chạy parser liên tục. Tuy nhiên, phải giữ đồng bộ tài liệu và không làm mất edit.

### 14.5. Cache

Server có thể cache AST, symbol index, type information và kết quả completion. Cache key cần bao gồm document version và dependency/configuration revision có ảnh hưởng.

### 14.6. Background indexing

Server có thể index workspace ở nền sau initialize. Những tính năng cần index nên trả kết quả một phần hoặc trạng thái đang xử lý, không nên treo editor trong khi chờ toàn bộ dự án.

## 15. Thiết kế language server cho DSL

### 15.1. Tái sử dụng parser và compiler core

Nếu DSL đã có compiler, nên tái sử dụng lexer, parser, resolver, type checker và semantic model. Language server chuyển kết quả từ core thành LSP structures.

### 15.2. Hỗ trợ tài liệu chưa hoàn chỉnh

Trong lúc nhập, file thường thiếu dấu ngoặc hoặc chỉ có một phần biểu thức. Parser phục vụ LSP cần có khả năng phục hồi và tạo AST một phần để completion, hover và diagnostics vẫn hoạt động.

### 15.3. Phân tích theo version

Mỗi tài liệu đang mở nên có trạng thái version. Kết quả async cần được kiểm tra trước khi publish để không hiển thị kết quả từ nội dung cũ.

### 15.4. Tách document model và workspace model

Document model chứa nội dung, AST và diagnostics của một file. Workspace model chứa module, schema, index và dependency giữa nhiều file.

Tách hai lớp giúp thay đổi một tài liệu không buộc server xây lại toàn bộ workspace nếu không cần.

### 15.5. Phân tích tăng dần

Với DSL lớn, server có thể parse lại vùng thay đổi hoặc chỉ cập nhật subtree bị ảnh hưởng. Semantic dependency graph giúp xác định file hoặc symbol nào cần phân tích lại.

### 15.6. Feature provider

Mỗi tính năng LSP có thể được triển khai thành provider:

~~~text
CompletionProvider
HoverProvider
DefinitionProvider
ReferencesProvider
RenameProvider
DiagnosticsProvider
FormattingProvider
SemanticTokensProvider
~~~

Các provider dùng chung document model và semantic index để tránh lặp logic.

### 15.7. Định vị source span

Parser thường dùng byte offset hoặc code point. LSP dùng line/character theo position encoding đã thương lượng. Server cần một lớp chuyển đổi đáng tin cậy giữa các hệ tọa độ, đặc biệt với Unicode và newline khác nhau.

## 16. Tích hợp LSP với compiler DSL

### 16.1. Một lõi phân tích chung

Compiler CLI và LSP nên gọi cùng một API phân tích:

~~~text
AnalysisResult analyze(
    DocumentSnapshot document,
    WorkspaceSnapshot workspace,
    AnalysisOptions options
)
~~~

Kết quả có thể chứa AST, symbols, diagnostics, type information và index references. CLI có thể dùng nó để biên dịch; LSP dùng nó để phục vụ editor.

### 16.2. Diagnostic mapping

Compiler có thể có Diagnostic nội bộ với code, severity, source span và related locations. LSP adapter chuyển nó thành Diagnostic của giao thức.

Không nên để compiler core phụ thuộc trực tiếp vào kiểu dữ liệu LSP nếu cùng core còn được dùng trong CLI, build hoặc công cụ khác.

### 16.3. Completion mapping

Semantic model có thể cung cấp danh sách symbol hợp lệ tại vị trí. Completion provider xếp hạng và chuyển thành CompletionItem.

### 16.4. Definition và references

Name resolver lưu liên kết giữa reference và declaration. LSP provider dùng các liên kết này để trả Location hoặc LocationLink.

### 16.5. Rename

Rename dùng symbol identity và reference index để tạo edits. Đây là lý do cần lưu identity ổn định trong compiler core.

### 16.6. Không chạy toàn bộ compiler cho mọi request

Một hover nhỏ không nên luôn kích hoạt full build, sinh mã hoặc gọi hệ thống bên ngoài. Nên có API phân tích phù hợp với editor, cache và phân tích tăng dần.

## 17. Bảo mật và độ tin cậy

### 17.1. Workspace là đầu vào không đáng tin mặc định

File DSL, schema, template và cấu hình có thể đến từ repository bên ngoài. Server cần xử lý như dữ liệu không đáng tin cậy.

### 17.2. Không thực thi DSL chỉ để phân tích

Completion, hover và diagnostics nên dựa trên parse và semantic analysis. Không nên thực thi hành động nghiệp vụ hoặc gọi API có tác dụng phụ chỉ để cung cấp gợi ý trong editor.

### 17.3. Giới hạn truy cập file

Server nên giới hạn việc đọc file theo workspace và dependency được cấu hình. Không nên cho một file DSL tùy ý yêu cầu đọc đường dẫn hệ thống.

### 17.4. Không chạy command tùy ý

LSP có thể hỗ trợ command hoặc code action theo khả năng client. Server chỉ nên cung cấp command đã được định nghĩa và kiểm soát. Không biến tên command hoặc tham số từ file DSL thành shell command tùy ý.

### 17.5. Quản lý plugin

Nếu DSL có plugin, server cần xác minh nguồn và quyền của plugin. Một plugin chạy trong quá trình phân tích có thể truy cập tài nguyên hoặc gây treo editor.

### 17.6. Bảo vệ dữ liệu nhạy cảm

Diagnostics, hover và logs không nên đưa secret, token hoặc dữ liệu cá nhân vào nội dung hiển thị hoặc telemetry nếu người dùng không có quyền xem.

### 17.7. Resource limits

Server cần giới hạn:

- Kích thước tài liệu.
- Độ sâu AST.
- Thời gian parse và type checking.
- Số lượng completion item.
- Số lượng workspace symbol.
- Kích thước diagnostics.
- Thời gian và bộ nhớ indexing.

### 17.8. Cập nhật dependency

Server cần quản lý phiên bản parser, schema và plugin. Một workspace độc hại không nên buộc server tự tải và chạy dependency tùy ý khi mở file.

## 18. Hiệu năng và trải nghiệm người dùng

### 18.1. Request tương tác cần nhanh

Completion, hover và signature help ảnh hưởng trực tiếp đến cảm giác gõ. Chúng nên dùng cache và chỉ phân tích vùng cần thiết khi có thể.

### 18.2. Diagnostics có thể chạy nền

Phân tích sâu toàn workspace có thể chạy nền, còn kiểm tra cú pháp cục bộ có thể chạy nhanh sau mỗi thay đổi. Server nên tránh làm editor giật hoặc mất phản hồi.

### 18.3. Ưu tiên kết quả hữu ích

Completion list quá dài làm người dùng khó chọn. Server nên xếp hạng theo scope, kiểu, tần suất hoặc ngữ cảnh và giới hạn kết quả phù hợp.

### 18.4. Debounce diagnostics

Server có thể đợi một khoảng ngắn sau lần gõ cuối để chạy phân tích đầy đủ. Tuy nhiên, lỗi cú pháp cơ bản có thể được phát hiện nhanh hơn để phản hồi kịp thời.

### 18.5. Telemetry

Có thể đo thời gian request, số tài liệu index và số diagnostics để tìm nút thắt. Không nên thu thập nội dung DSL hoặc thông tin nhạy cảm nếu không có chính sách rõ ràng.

### 18.6. Khả năng phục hồi

Nếu một file lỗi parse, server vẫn cần tiếp tục phục vụ các file khác. Một tài liệu hỏng không nên làm sập toàn bộ language server.

## 19. Kiểm thử language server

### 19.1. Kiểm thử giao thức

Kiểm tra initialize, initialized, request-response, notification, shutdown và exit. Đảm bảo framing và JSON-RPC đúng.

### 19.2. Kiểm thử đồng bộ tài liệu

Kiểm tra didOpen, full change, incremental change, version tăng, save và close. Đặc biệt xác nhận range được áp dụng chính xác.

### 19.3. Kiểm thử diagnostics

Tạo fixture có lỗi từ lexer, parser, resolver, type checker và semantic validation. Xác nhận range, severity, code và message.

### 19.4. Kiểm thử completion

Kiểm tra gợi ý ở các ngữ cảnh khác nhau: đầu rule, sau dấu chấm, vị trí kiểu, đối số hàm, biểu thức điều kiện và import.

### 19.5. Kiểm thử navigation

Kiểm tra definition, references, document symbols và workspace symbols trên nhiều file và module.

### 19.6. Kiểm thử rename và code action

Xác nhận edit đúng mọi reference, không sửa string/comment không liên quan và phát hiện xung đột tên.

### 19.7. Kiểm thử Unicode và position encoding

Dùng tên và chuỗi có ký tự ngoài ASCII, ký tự kết hợp và emoji để kiểm tra line/character mapping.

### 19.8. Kiểm thử concurrency và cancellation

Gửi nhiều didChange và request liên tiếp. Xác nhận kết quả cũ không ghi đè kết quả mới và request bị hủy không tiếp tục tiêu tốn tài nguyên lâu.

### 19.9. Kiểm thử nhiều workspace

Mở nhiều root có symbol trùng tên nhưng dependency khác nhau. Server cần phân giải đúng theo workspace.

### 19.10. Kiểm thử client thực tế

Ngoài test giao thức, nên thử với các editor mục tiêu vì cách hiển thị, hỗ trợ capability và hành vi đồng bộ có thể khác nhau.

## 20. Ví dụ luồng tính năng trong DSL

Giả sử người dùng đang sửa:

~~~text
rule GoldDiscount {
    when customer.tier == GOLD
    then applyDiscount(order, 0.15)
}
~~~

### 20.1. Mở tài liệu

Client gửi didOpen với URI, languageId, version và text. Server tạo document snapshot, parse và phân tích.

### 20.2. Diagnostics

Nếu customer chưa được khai báo, server publish diagnostic tại tên customer. Nếu mọi tham chiếu hợp lệ, server gửi danh sách rỗng hoặc kết quả không có diagnostics theo mô hình đã chọn.

### 20.3. Completion

Người dùng nhập customer. Server xác định kiểu Customer và gợi ý tier, name, email hoặc các thuộc tính hợp lệ khác.

### 20.4. Hover

Người dùng hover lên GOLD. Server trả kiểu CustomerTier và documentation về giá trị enum.

### 20.5. Definition

Người dùng yêu cầu definition trên applyDiscount. Server tìm symbol trong module hoặc registry và trả vị trí khai báo.

### 20.6. References

Người dùng yêu cầu references trên applyDiscount. Server dùng index để liệt kê những rule đang gọi hàm.

### 20.7. Rename

Người dùng đổi tên applyDiscount thành applyMemberDiscount. Server xác định symbol identity, tìm references và tạo WorkspaceEdit trên các file liên quan.

### 20.8. Thay đổi schema

Nếu schema Customer thay đổi, server cập nhật workspace model, phân tích lại những tài liệu phụ thuộc và publish diagnostics mới.

Luồng này cho thấy LSP không tự hiểu DSL. Nó chuyển yêu cầu của editor đến các dịch vụ phân tích và đưa kết quả trở lại theo giao thức.

## 21. Những sai lầm thường gặp khi triển khai LSP

### 21.1. Xem LSP như một parser wrapper

Một server chỉ parse file và trả lỗi cú pháp sẽ thiếu nhiều giá trị như completion, navigation và refactoring. Tuy nhiên, không cần triển khai mọi tính năng ngay từ đầu; nên ưu tiên theo nhu cầu người dùng.

### 21.2. Không đồng bộ bản tài liệu đang mở

Đọc file từ đĩa thay vì dùng nội dung didOpen/didChange có thể khiến server phân tích phiên bản cũ chưa lưu.

### 21.3. Bỏ qua version

Kết quả bất đồng bộ cũ có thể đến sau kết quả mới và ghi đè diagnostics hiện tại. Mọi tác vụ phân tích nên gắn với snapshot version.

### 21.4. Tự đoán capabilities

Client có thể không hỗ trợ một loại markup, dynamic registration hoặc workspace edit. Server cần thương lượng capabilities và có fallback.

### 21.5. Ghi log vào stdout

Với stdio transport, log chen vào stream sẽ làm hỏng framing JSON-RPC. Dùng stderr hoặc logger riêng.

### 21.6. Dùng regex cho mọi tính năng

Regex có thể hỗ trợ highlight đơn giản nhưng không đủ cho definition, rename hoặc completion theo kiểu. Những tính năng này cần parser và semantic model.

### 21.7. Rename bằng thay thế chuỗi

Thay mọi lần xuất hiện của tên có thể sửa nhầm comment, string literal hoặc symbol khác. Rename cần dùng symbol identity và references.

### 21.8. Không xử lý file chưa hoàn chỉnh

Người dùng thường nhập cú pháp dang dở. Parser cứng nhắc làm completion và hover ngừng hoạt động đúng lúc người dùng cần nhất.

### 21.9. Phân tích toàn workspace cho mọi request

Một hover đơn giản không nên kích hoạt full build hoặc indexing lại tất cả file. Cần cache và phân tích tăng dần.

### 21.10. Cho phép thực thi hành động khi phân tích

Mở file hoặc yêu cầu completion không nên gửi email, cập nhật database hay gọi dịch vụ nghiệp vụ. Phân tích editor cần an toàn và không có tác dụng phụ.

## 22. Quy trình xây dựng language server cho DSL

Một lộ trình triển khai có thể gồm:

1. **Xác định nhu cầu editor:** chọn các tính năng người viết DSL cần nhất.
2. **Tái sử dụng compiler core:** dùng chung lexer, parser, resolver và type checker.
3. **Xây document manager:** lưu snapshot, version, URI và trạng thái tài liệu.
4. **Thiết lập JSON-RPC transport:** xử lý framing, request, response và notification.
5. **Triển khai lifecycle:** initialize, initialized, shutdown và exit.
6. **Thương lượng capabilities:** chỉ công bố những tính năng thực sự hỗ trợ.
7. **Đồng bộ tài liệu:** full hoặc incremental sync theo capability.
8. **Triển khai diagnostics:** ánh xạ lỗi nội bộ sang LSP và tránh kết quả cũ.
9. **Thêm completion và hover:** dựa trên ngữ cảnh và semantic model.
10. **Thêm navigation:** definition, references và symbols.
11. **Thêm refactoring:** rename, code actions và WorkspaceEdit.
12. **Thêm tính năng hỗ trợ:** formatting, semantic tokens, folding và hints.
13. **Index workspace:** quản lý dependency và file changes.
14. **Tối ưu:** cancellation, progress, cache và incremental analysis.
15. **Bảo mật:** giới hạn file, command, plugin và tài nguyên.
16. **Kiểm thử:** protocol, document sync, Unicode, multi-workspace và client thực tế.

## 23. Câu hỏi tự đánh giá

1. LSP giải quyết vấn đề tích hợp editor như thế nào?
2. Phân biệt language client, language server và compiler.
3. Vì sao LSP dùng JSON-RPC và cần framing transport?
4. initialize, initialized, shutdown và exit có vai trò gì?
5. Client và server capabilities được thương lượng như thế nào?
6. didOpen, didChange, didSave và didClose dùng để làm gì?
7. Full synchronization khác incremental synchronization ra sao?
8. Vì sao server phải quản lý version tài liệu?
9. Diagnostics push khác pull diagnostics như thế nào?
10. Completion cần những thông tin ngữ nghĩa nào?
11. Vì sao rename cần symbol identity thay vì thay chuỗi?
12. Source span nội bộ cần được chuyển sang LSP position ra sao?
13. Cancellation, progress và partial results giúp gì cho workspace lớn?
14. Những giới hạn bảo mật nào cần áp dụng cho language server?

## Kết luận

Language Server Protocol chuẩn hóa cách editor giao tiếp với một tiến trình hiểu ngôn ngữ. Với DSL, language server dùng parser, resolver, type checker và mô hình miền để cung cấp diagnostics, completion, hover, navigation, rename, formatting và những tính năng hỗ trợ khác. LSP là lớp giao tiếp giữa công cụ phát triển và lõi phân tích ngôn ngữ; nó không thay thế compiler hoặc định nghĩa semantics của DSL.

Một implementation đáng tin cậy cần quản lý vòng đời JSON-RPC, thương lượng capabilities, đồng bộ đúng nội dung và version tài liệu, chuyển đổi chính xác vị trí Unicode, tránh kết quả cũ và xử lý tác vụ dài có cancellation. Tái sử dụng compiler core giúp editor và build thống nhất về ngữ nghĩa. Khi kết hợp document model, workspace index, diagnostics có cấu trúc, refactoring dựa trên symbol identity và giới hạn bảo mật, LSP biến DSL thành ngôn ngữ có trải nghiệm phát triển chuyên nghiệp trên nhiều editor.
