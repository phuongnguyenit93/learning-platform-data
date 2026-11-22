# Chẩn đoán thời gian thực

## 1. Chẩn đoán thời gian thực trong Language Server

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) thường có cú pháp, kiểu dữ liệu, quy tắc nghiệp vụ và tài nguyên riêng. Khi người dùng viết DSL trong editor, họ cần biết sớm đoạn nào sai cú pháp, tên nào chưa được khai báo, biểu thức nào không tương thích kiểu hoặc cấu hình nào vi phạm quy tắc miền.

**Chẩn đoán thời gian thực (real-time diagnostics)** là khả năng phân tích tài liệu trong khi người dùng đang soạn thảo và gửi kết quả chẩn đoán về editor với độ trễ thấp. Chẩn đoán có thể xuất hiện ngay sau khi người dùng dừng gõ trong một khoảng ngắn, sau khi lưu file hoặc khi một tài liệu phụ thuộc thay đổi.

Trong kiến trúc Language Server Protocol (LSP), language server thực hiện phân tích ngôn ngữ và gửi hoặc trả về các diagnostics cho language client. Editor có thể hiển thị gạch chân lỗi, biểu tượng cảnh báo, nội dung giải thích khi hover, danh sách Problems và các hành động sửa lỗi.

Ví dụ, người dùng đang viết:

~~~text
pipeline "daily-sales" {
    source "orders.csv"
    filter amount > "high"
    output "sales.csv"
}
~~~

Parser có thể nhận diện cấu trúc câu lệnh. Semantic analyzer biết amount là số, trong khi "high" là chuỗi, nên tạo diagnostic về phép so sánh không tương thích kiểu. Language server chuyển diagnostic đó thành vị trí và thông tin theo LSP để editor đánh dấu biểu thức gây lỗi.

Chẩn đoán thời gian thực có các mục tiêu:

- Phát hiện lỗi cú pháp và ngữ nghĩa càng sớm càng tốt.
- Chỉ ra chính xác vị trí liên quan trong tài liệu.
- Giải thích nguyên nhân bằng thông báo dễ hiểu.
- Cập nhật kết quả khi nội dung thay đổi.
- Tránh hiển thị kết quả cũ của phiên bản tài liệu trước.
- Giữ editor phản hồi nhanh ngay cả khi workspace lớn.
- Cung cấp thông tin đủ ổn định để tích hợp với Problems, code actions và công cụ khác.

Từ “thời gian thực” ở đây không có nghĩa mọi ký tự đều phải được phân tích đồng bộ ngay trong thao tác gõ. Một language server tốt thường dùng debounce, hủy công việc cũ, phân tích gia tăng và xử lý nền để cân bằng độ trễ với chi phí tính toán.

## 2. Diagnostics và các loại lỗi

Diagnostic là một mô tả có cấu trúc về vấn đề hoặc thông tin mà language server muốn gắn với một vị trí trong tài liệu. Nó không nhất thiết là lỗi nghiêm trọng. Diagnostic có thể là error, warning, information hoặc hint.

### 2.1. Chẩn đoán cú pháp

Parser phát hiện văn bản không tuân theo grammar:

~~~text
pipeline "daily" {
    source "orders.csv"
    filter amount >
}
~~~

Sau dấu lớn hơn, parser mong đợi một biểu thức. Language server có thể báo thiếu toán hạng tại cuối dòng hoặc vị trí ngay sau toán tử.

### 2.2. Chẩn đoán ngữ nghĩa

Cú pháp có thể hợp lệ nhưng ý nghĩa không hợp lệ:

~~~text
filter unknown_field > 10
~~~

Nếu schema nguồn không có unknown_field, name resolver hoặc semantic analyzer báo tham chiếu chưa được nhận diện.

### 2.3. Chẩn đoán kiểu

~~~text
filter order_total > "expensive"
~~~

Nếu order_total có kiểu số, phép so sánh với chuỗi có thể không hợp lệ. Diagnostic nên chỉ ra kiểu thực tế và kiểu được yêu cầu.

### 2.4. Chẩn đoán quy tắc miền

~~~text
service "billing" {
    replicas 0
}
~~~

Giá trị có thể đúng kiểu Integer nhưng vi phạm quy tắc miền yêu cầu replicas lớn hơn hoặc bằng 1. Đây là validation diagnostic, không phải lỗi parser.

### 2.5. Chẩn đoán lint và chất lượng

~~~text
let unused_limit = 100
~~~

Một biến không được sử dụng có thể tạo warning hoặc hint. Đây là gợi ý chất lượng mã, không nhất thiết làm chương trình không thể chạy.

### 2.6. Chẩn đoán môi trường

Language server có thể báo không tìm thấy file nguồn, plugin chưa được cài, schema không tải được hoặc phiên bản runtime không tương thích. Nên phân biệt lỗi trong tài liệu với lỗi môi trường để người dùng biết cần sửa mã hay cấu hình hệ thống.

## 3. Kiến trúc xử lý diagnostics

Một language server thường nhận các sự kiện từ client, cập nhật trạng thái tài liệu, chạy phân tích và chuyển kết quả thành thông điệp LSP.

~~~text
Editor
   |
   | didOpen / didChange
   v
Language Server
   |
   v
Document Store
   |
   v
Debounce / Scheduler
   |
   v
Parser
   |
   v
Name Resolution
   |
   v
Type and Domain Analysis
   |
   v
Diagnostic Mapper
   |
   v
LSP Diagnostics
   |
   v
Editor Problems / Decorations
~~~

Các thành phần chính:

- **Document Store:** giữ nội dung hiện tại, URI và version của tài liệu đang mở.
- **Scheduler:** quyết định thời điểm phân tích, quản lý debounce và hủy công việc lỗi thời.
- **Parser:** tạo cấu trúc cú pháp và phát hiện lỗi grammar.
- **Semantic Analyzer:** resolve symbol, kiểm tra kiểu và quy tắc miền.
- **Diagnostic Collector:** thu thập các vấn đề từ nhiều giai đoạn.
- **Diagnostic Mapper:** chuyển source span nội bộ thành LSP Range và Diagnostic.
- **Publisher hoặc Request Handler:** gửi notification hoặc trả kết quả pull diagnostics.

Không phải language server nào cũng cần các lớp riêng biệt. Tuy nhiên, tách trách nhiệm giúp kiểm soát version, vị trí nguồn và chính sách cập nhật dễ hơn.

## 4. Vòng đời tài liệu trong LSP

Language server cần theo dõi tài liệu để biết nội dung nào đang được phân tích.

### 4.1. didOpen

Khi người dùng mở tài liệu, client gửi textDocument/didOpen với URI, languageId, version và nội dung hiện tại. Server tạo document state và có thể bắt đầu phân tích ngay.

### 4.2. didChange

Khi nội dung thay đổi, client gửi textDocument/didChange. Thông điệp có thể chứa toàn bộ văn bản mới hoặc các incremental text edits tùy cách đồng bộ tài liệu đã thương lượng.

Server cập nhật nội dung và version trước khi khởi chạy phân tích cho trạng thái mới.

### 4.3. didSave

Client có thể gửi textDocument/didSave khi lưu file. Server có thể dùng sự kiện này để chạy kiểm tra cần thao tác trên đĩa hoặc cập nhật artifact phụ thuộc vào nội dung đã lưu.

Không nên mặc định rằng chỉ khi save mới được cập nhật diagnostics. Với cấu hình đồng bộ phù hợp, diagnostics có thể được cập nhật trong lúc soạn thảo.

### 4.4. didClose

Khi tài liệu đóng, server cần dọn trạng thái tạm, hủy phân tích còn chạy và xóa diagnostics đã publish nếu giao thức hoặc chính sách client yêu cầu. Tài liệu có thể vẫn tồn tại trên đĩa; đóng editor không có nghĩa xóa file.

### 4.5. Document version

Version giúp xác định diagnostics thuộc phiên bản văn bản nào. Nếu kết quả phân tích cho version 7 hoàn tất sau khi tài liệu đã chuyển sang version 8, server không nên publish kết quả cũ như thể nó áp dụng cho nội dung mới.

## 5. Push diagnostics và pull diagnostics

LSP hỗ trợ hai mô hình trao đổi diagnostics: server push kết quả bằng notification và client pull kết quả bằng request.

### 5.1. Push diagnostics

Trong mô hình push, server gửi notification textDocument/publishDiagnostics khi có kết quả:

~~~json
{
  "jsonrpc": "2.0",
  "method": "textDocument/publishDiagnostics",
  "params": {
    "uri": "file:///workspace/orders.dsl",
    "version": 12,
    "diagnostics": [
      {
        "range": {
          "start": { "line": 2, "character": 11 },
          "end": { "line": 2, "character": 28 }
        },
        "severity": 1,
        "source": "dsl-semantic",
        "code": "DSL-TYPE-004",
        "message": "Không thể so sánh giá trị Decimal với String."
      }
    ]
  }
}
~~~

Ví dụ minh họa JSON-RPC. Trong LSP, line và character là vị trí zero-based; cách diễn giải character phụ thuộc position encoding đã thương lượng, với UTF-16 là mặc định khi không có thương lượng encoding khác.

Ưu điểm của push:

- Server chủ động cập nhật khi đã phân tích xong.
- Phù hợp với luồng editor truyền thống.
- Không cần client liên tục hỏi kết quả.

Điểm cần chú ý:

- Server phải quản lý kết quả cũ và thứ tự publish.
- Notification cho một URI thay thế tập diagnostics trước đó của URI đó.
- Phải gửi danh sách rỗng khi không còn vấn đề để xóa dấu lỗi cũ.

### 5.2. Pull diagnostics

Trong mô hình pull, client gửi request textDocument/diagnostic và server trả về report. Mô hình pull diagnostics được bổ sung trong LSP 3.17.

Ví dụ request:

~~~json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "textDocument/diagnostic",
  "params": {
    "textDocument": {
      "uri": "file:///workspace/orders.dsl"
    }
  }
}
~~~

Server có thể trả về full report chứa danh sách diagnostics hoặc unchanged report nếu kết quả không thay đổi so với resultId mà client cung cấp.

Ví dụ full report:

~~~json
{
  "jsonrpc": "2.0",
  "id": 42,
  "result": {
    "kind": "full",
    "resultId": "orders-v12",
    "items": []
  }
}
~~~

ResultId cho phép server và client tránh truyền lại dữ liệu không thay đổi. Server chỉ nên trả unchanged khi có thể xác nhận report hiện tại tương ứng chính xác với kết quả đã được client biết.

### 5.3. Workspace diagnostics

Pull diagnostics còn hỗ trợ truy vấn diagnostics cho workspace. Server có thể trả kết quả theo từng tài liệu và dùng partial result/progress để truyền nhiều phần khi workspace lớn.

Workspace diagnostics hữu ích khi:

- Người dùng muốn xem lỗi của các file chưa mở.
- Server cần cập nhật kết quả sau khi schema hoặc module dùng chung thay đổi.
- Công cụ muốn hiển thị tình trạng tổng thể của dự án.

Server cần tôn trọng capability client đã quảng bá và không giả định mọi client hỗ trợ cùng một dạng pull diagnostics.

### 5.4. Chọn push hay pull

| Tiêu chí | Push | Pull |
|---|---|---|
| Bên khởi tạo trao đổi | Server | Client |
| Cách cập nhật | Notification publishDiagnostics | Request diagnostic |
| Caching | Server tự quản lý publish state | Có resultId và report unchanged |
| Workspace lớn | Cần chiến lược publish và giới hạn | Có thể dùng workspace report và partial result |
| Tương thích | Phổ biến trong nhiều language client | Phụ thuộc capability và phiên bản LSP |

Một server có thể hỗ trợ một hoặc cả hai mô hình theo capability negotiation. Cần tránh gửi hai luồng kết quả trùng lặp nếu client không mong đợi.

## 6. Cấu trúc Diagnostic của LSP

Diagnostic là một object có các trường mô tả vị trí, mức độ, mã lỗi, nguồn và nội dung giải thích.

Các trường thường dùng:

| Trường | Mục đích |
|---|---|
| range | Vùng văn bản liên quan |
| severity | Error, Warning, Information hoặc Hint |
| code | Mã định danh loại diagnostic |
| codeDescription | URI đến tài liệu giải thích mã, nếu có |
| source | Tên thành phần tạo diagnostic |
| message | Nội dung giải thích |
| tags | Nhãn như Unnecessary hoặc Deprecated |
| relatedInformation | Các vị trí liên quan trong một hoặc nhiều tài liệu |
| data | Dữ liệu bổ sung để server dùng trong code action hoặc xử lý tiếp |

Không phải trường nào cũng bắt buộc. Server nên cung cấp thông tin đủ dùng và giữ định dạng ổn định.

### 6.1. Range

Range gồm start và end. Vị trí dòng và ký tự bắt đầu từ 0. End thường được hiểu là vị trí kết thúc không bao gồm ký tự tại đó.

Ví dụ:

~~~text
filter amount > "high"
       ^^^^^^^^^^^^^^^
~~~

Diagnostic có thể gắn với toàn biểu thức so sánh hoặc chỉ phần chuỗi sai kiểu. Vùng nên đủ chính xác để editor đánh dấu đúng nội dung mà người dùng cần sửa.

### 6.2. Severity

LSP định nghĩa bốn mức:

| Giá trị | Mức | Ý nghĩa thường dùng |
|---:|---|---|
| 1 | Error | Chương trình hoặc phần cấu trúc không hợp lệ |
| 2 | Warning | Có vấn đề đáng chú ý nhưng có thể tiếp tục |
| 3 | Information | Thông tin hữu ích |
| 4 | Hint | Gợi ý nhẹ hoặc đề xuất cải thiện |

Severity phản ánh mức độ của diagnostic theo chính sách DSL, không nhất thiết là mức ưu tiên xử lý trong mọi editor.

### 6.3. Code và source

Code nên ổn định qua các phiên bản nếu công cụ bên ngoài dùng nó để lọc, liên kết tài liệu hoặc kiểm thử. Ví dụ:

- DSL-PARSE-001: thiếu dấu đóng block.
- DSL-NAME-002: tên chưa được khai báo.
- DSL-TYPE-004: kiểu toán hạng không tương thích.
- DSL-DEPRECATION-003: dùng cú pháp đã lỗi thời.

Source cho biết thành phần phát sinh diagnostic, ví dụ dsl-parser, dsl-typechecker hoặc dsl-linter.

### 6.4. Tags

DiagnosticTag.Unnecessary có thể đánh dấu đoạn mã không cần thiết. DiagnosticTag.Deprecated đánh dấu thành phần đã lỗi thời. Tag hỗ trợ editor trình bày phù hợp, nhưng không thay thế message và severity.

### 6.5. Related information

Một lỗi có thể liên quan đến nhiều vị trí:

~~~text
let total = amount + tax
let amount = "unknown"
~~~

Diagnostic tại phép cộng có thể trỏ thêm đến khai báo amount để giải thích nguồn gốc kiểu String. relatedInformation cho phép client hiển thị các vị trí liên quan, kể cả trong tài liệu khác nếu client hỗ trợ.

### 6.6. Data

Trường data có thể giữ dữ liệu opaque mà server cần khi xử lý code action sau đó. Không nên dùng data để nhúng payload lớn hoặc thông tin nhạy cảm. Client có thể gửi lại data trong một request tiếp theo; server cần xác thực và xử lý như dữ liệu không tin cậy.

## 7. Ánh xạ vị trí nguồn sang LSP Range

Compiler thường lưu vị trí theo byte offset hoặc code point, trong khi LSP dùng Position gồm line và character. Diagnostic mapper phải chuyển đổi chính xác.

### 7.1. Line và character zero-based

Trong LSP:

- Dòng đầu tiên có line = 0.
- Ký tự đầu dòng có character = 0.
- End position xác định ranh giới kết thúc của range.

Nếu parser dùng line/column bắt đầu từ 1, mapper cần chuyển về chỉ số zero-based.

### 7.2. Position encoding

LSP sử dụng position encoding được thương lượng giữa client và server. UTF-16 là mặc định khi không có encoding khác được thương lượng. Một số client/server có thể hỗ trợ UTF-8 hoặc UTF-32.

Với Unicode ngoài Basic Multilingual Plane, số byte UTF-8, số code point và số UTF-16 code unit có thể khác nhau. Nếu parser tính column theo code point nhưng client mong UTF-16, range sẽ lệch trên dòng có emoji hoặc ký tự ngoài BMP.

Ví dụ ký tự:

~~~text
A😀B
~~~

Trong chuỗi này, emoji chiếm một Unicode code point, hai UTF-16 code units và bốn byte UTF-8. Character offset của B vì vậy phụ thuộc encoding.

### 7.3. Offset to position

Một mapper có thể:

1. Giữ bảng offset bắt đầu của từng dòng.
2. Tìm dòng chứa offset bắt đầu và kết thúc.
3. Tính số đơn vị mã từ đầu dòng đến offset.
4. Chuyển sang đơn vị encoding đã thương lượng.
5. Tạo Range.

Nếu xử lý incremental edits, bảng line offset cần được cập nhật hoặc tính lại theo phiên bản văn bản mới.

### 7.4. End of file

Lỗi thiếu thành phần ở cuối file có thể cần range zero-width tại vị trí EOF. Ví dụ parser mong đợi dấu đóng ngoặc nhưng đã hết đầu vào. Server nên đặt vị trí tại cuối tài liệu thay vì tạo range vượt ngoài giới hạn.

### 7.5. Multi-line range

Một diagnostic có thể trải qua nhiều dòng. Tuy nhiên, range quá rộng làm editor đánh dấu cả khối lớn và khó xác định lỗi. Nên chọn vùng nhỏ nhất vẫn giải thích đúng vấn đề.

## 8. Phân tích cú pháp khi tài liệu chưa hoàn chỉnh

Trong lúc gõ, văn bản thường ở trạng thái chưa hoàn chỉnh. Một parser chỉ chấp nhận chương trình hoàn chỉnh có thể báo quá nhiều lỗi tạm thời.

Ví dụ người dùng vừa nhập:

~~~text
pipeline "daily" {
    filter amount >
~~~

Parser có thể phát hiện block chưa đóng và biểu thức còn thiếu. Tuy nhiên, người dùng có thể đang chuẩn bị nhập toán hạng ở dòng tiếp theo.

### 8.1. Error recovery

Parser phục hồi lỗi cố gắng tiếp tục phân tích sau một lỗi để vẫn nhận diện được các cấu trúc phía sau.

Các kỹ thuật:

- Panic-mode recovery: bỏ qua token đến điểm đồng bộ như newline, dấu chấm phẩy hoặc dấu đóng block.
- Insertion: giả định thiếu một token và tiếp tục mà không sửa nguồn thật.
- Deletion: bỏ qua token không mong đợi trong quá trình phân tích.
- Error node: tạo node lỗi trong AST để các bước sau có thể tiếp tục.

### 8.2. Điểm đồng bộ

Điểm đồng bộ phụ thuộc grammar DSL. Với DSL theo dòng, newline có thể là điểm tốt. Với DSL dùng block, dấu đóng block hoặc dấu chấm phẩy có thể phù hợp hơn.

### 8.3. Tránh cascade diagnostics

Một lỗi cú pháp có thể khiến nhiều rule sau đó thất bại. Nếu phát ra mọi lỗi phụ thuộc, editor có thể hiển thị hàng chục gạch chân cho một dấu ngoặc bị thiếu.

Có thể:

- Ưu tiên lỗi gốc gần vị trí đầu tiên.
- Dùng error node để cô lập vùng hỏng.
- Tránh chạy semantic checks trên node không đủ thông tin.
- Giảm severity hoặc ẩn diagnostics được suy ra từ cùng một lỗi gốc.

### 8.4. Provisional diagnostics

Trong lúc người dùng đang gõ, một số lỗi có thể tạm thời. Server có thể đợi debounce ngắn trước khi phân tích hoặc đánh dấu trạng thái đang xử lý trong UI nếu client hỗ trợ. Không nên kéo dài debounce đến mức người dùng cảm thấy editor không phản hồi.

## 9. Pipeline tạo diagnostics

Một pipeline có thể gom kết quả từ nhiều giai đoạn:

~~~text
Current document snapshot
       |
       v
Lexical analysis
       |
       v
Parsing and recovery
       |
       v
Name resolution
       |
       v
Type checking
       |
       v
Domain validation
       |
       v
Lint and deprecation checks
       |
       v
Diagnostic normalization
       |
       v
LSP mapping and publication
~~~

### 9.1. Lexical diagnostics

Phát hiện literal không đóng, escape sequence không hợp lệ hoặc ký tự không được hỗ trợ.

### 9.2. Parse diagnostics

Phát hiện token không mong đợi, thành phần bắt buộc bị thiếu hoặc cấu trúc block sai.

### 9.3. Name resolution diagnostics

Phát hiện symbol chưa khai báo, import không tồn tại, tên trùng hoặc tham chiếu mơ hồ.

### 9.4. Type diagnostics

Kiểm tra toán hạng, kiểu trả về, tham số hàm, chuyển đổi và ràng buộc kiểu.

### 9.5. Domain diagnostics

Kiểm tra required attribute, giá trị ngoài miền, quan hệ giữa thuộc tính và quy tắc nghiệp vụ.

### 9.6. Lint diagnostics

Phát hiện biến không dùng, cú pháp deprecated, cách viết không nhất quán hoặc pattern dễ gây lỗi.

### 9.7. Normalize và deduplicate

Nhiều pass có thể phát hiện cùng một vấn đề. Diagnostic collector có thể chuẩn hóa code, source, range và severity, sau đó loại các bản trùng theo khóa phù hợp.

Không nên gộp hai diagnostic chỉ vì message giống nhau nếu chúng đề cập hai vị trí hoặc hai nguyên nhân khác nhau.

## 10. Cập nhật diagnostics nhanh và hiệu quả

Phân tích sau mỗi ký tự có thể tốn tài nguyên. Language server thường dùng các kỹ thuật điều phối để giảm công việc không cần thiết.

### 10.1. Debounce

Debounce đợi một khoảng thời gian ngắn sau thay đổi cuối cùng rồi mới bắt đầu phân tích:

~~~text
onDocumentChange:
    cancel pending timer
    schedule analysis after quiet interval
~~~

Nếu người dùng gõ liên tục, server chỉ phân tích sau khi họ tạm dừng. Khoảng chờ cần cân bằng giữa độ phản hồi và số lần chạy parser.

### 10.2. Throttle

Throttle giới hạn tần suất phân tích tối đa, ví dụ không chạy quá một lần trong mỗi khoảng thời gian nhất định. Khác với debounce, throttle vẫn có thể chạy khi người dùng đang gõ liên tục.

### 10.3. Cancellation

Khi document thay đổi, công việc phân tích cho version cũ có thể không còn hữu ích. Server nên hủy hoặc đánh dấu kết quả đó là stale.

Cancellation giúp tiết kiệm CPU, nhưng không phải mọi thao tác đều hủy được ngay. Các bước parser hoặc thư viện không hỗ trợ cancellation có thể cần kiểm tra token giữa các giai đoạn.

### 10.4. Snapshot bất biến

Mỗi lần phân tích nên dùng một snapshot nội dung cùng version xác định. Không để parser đọc một buffer đang bị thay đổi đồng thời bởi event didChange.

### 10.5. Bỏ kết quả cũ

Ngay trước khi publish, server kiểm tra version của snapshot với version hiện tại. Nếu không còn khớp, bỏ kết quả hoặc giữ lại chỉ khi protocol semantics cho phép và client có thể nhận biết version.

### 10.6. Ưu tiên công việc

Tài liệu đang được chỉnh sửa có thể được ưu tiên hơn các file không mở. Workspace scan hoặc lint sâu có thể chạy nền với mức ưu tiên thấp hơn.

## 11. Incremental parsing và incremental analysis

Với tài liệu lớn, phân tích lại toàn bộ sau mỗi thay đổi có thể chậm. Incremental processing chỉ tính lại phần bị ảnh hưởng khi có thể.

### 11.1. Incremental parsing

Parser có thể tái sử dụng các node hoặc vùng cú pháp không bị ảnh hưởng bởi edit. Điều này đòi hỏi parser giữ cấu trúc và mapping từ offset cũ sang offset mới.

### 11.2. Incremental name resolution

Nếu một khai báo thay đổi, chỉ các tham chiếu phụ thuộc vào symbol đó có thể cần resolve lại. Dependency graph giúp xác định phạm vi.

### 11.3. Incremental type checking

Thay đổi một biểu thức có thể ảnh hưởng kiểu của các node cha và các use phụ thuộc. Type checker có thể lưu kết quả theo node/version và invalidate khi dependency đổi.

### 11.4. Workspace dependency graph

Một module DSL có thể import module khác hoặc tham chiếu schema dùng chung. Khi file schema đổi, diagnostics của nhiều tài liệu có thể cần cập nhật dù nội dung các file đó không thay đổi.

### 11.5. Correct invalidation

Incremental analysis chỉ đúng nếu mọi dependency liên quan đều được ghi nhận. Nếu quên dependency, server có thể giữ diagnostic cũ hoặc bỏ sót lỗi mới. Khi không chắc chắn, có thể fallback sang phân tích đầy đủ.

## 12. Tránh diagnostics lỗi thời và race condition

Language server thường có nhiều yêu cầu phân tích đang chạy cùng lúc. Kết quả có thể hoàn thành không theo thứ tự khởi chạy.

Ví dụ:

1. Version 10 bắt đầu phân tích.
2. Người dùng sửa file thành version 11.
3. Version 11 được phân tích nhanh và hoàn tất.
4. Version 10 hoàn tất muộn hơn.

Nếu server publish cả hai mà không kiểm tra version, lỗi của version 10 có thể ghi đè diagnostics mới.

### 12.1. Version guard

Gắn version vào mỗi analysis job và chỉ publish khi version vẫn là version hiện tại của document.

### 12.2. Generation token

Mỗi lần thay đổi nội dung, tăng generation counter. Job chỉ được publish nếu generation của nó vẫn khớp với generation hiện tại.

### 12.3. Cancellation token

Truyền cancellation token đến parser, analyzer và các bước truy cập workspace. Các bước dài kiểm tra token định kỳ.

### 12.4. Per-document serialization

Có thể tuần tự hóa cập nhật state cho cùng một document, trong khi phân tích các document khác song song. Cách này giảm race trên document store nhưng không ngăn mọi lỗi nếu analyzer dùng shared cache mutable.

### 12.5. Workspace snapshot

Nếu diagnostic phụ thuộc nhiều file, cần xác định snapshot hoặc version của dependency đã dùng. Một kết quả có thể đúng với file hiện tại nhưng dựa trên schema cũ.

## 13. Quản lý diagnostics đã publish

Diagnostics là trạng thái hiển thị trong client. Server cần quản lý việc thay thế và xóa kết quả.

### 13.1. Publish tập đầy đủ

Với push diagnostics, notification publishDiagnostics cho một URI thường thay thế toàn bộ diagnostics trước đó của URI đó. Vì vậy, server nên gửi tập đầy đủ hiện tại, không chỉ gửi phần vừa thay đổi.

Nếu server chỉ gửi diagnostic mới mà không giữ các diagnostic cũ vẫn còn hiệu lực, chúng có thể biến mất khỏi editor. Ngược lại, nếu không gửi danh sách rỗng khi lỗi đã hết, dấu lỗi cũ có thể còn tồn tại.

### 13.2. Xóa diagnostics

Khi tài liệu không còn lỗi, gửi publishDiagnostics với diagnostics là mảng rỗng cho URI tương ứng nếu đang dùng push.

### 13.3. Tài liệu đóng

Khi tài liệu đóng, server cần dọn trạng thái và xử lý diagnostics theo quy ước LSP/client. Không nên giữ kết quả trong cache như thể tài liệu vẫn đang mở nếu version hoặc nội dung đã thay đổi.

### 13.4. Diagnostics liên tài liệu

Một thay đổi trong schema có thể làm lỗi xuất hiện trong các module phụ thuộc. Server cần xác định URI nào bị ảnh hưởng và cập nhật diagnostics cho các tài liệu đó, hoặc dùng workspace pull diagnostics nếu client hỗ trợ.

### 13.5. Diagnostic ownership

Nếu parser, linter và plugin cùng phát diagnostics, server cần hợp nhất kết quả và tránh một thành phần vô tình xóa diagnostics của thành phần khác. Có thể lưu kết quả theo source/pass rồi tổng hợp thành tập publish cuối.

## 14. Related information và lỗi liên tài liệu

Nhiều lỗi DSL chỉ có thể giải thích khi liên kết nhiều vị trí.

Ví dụ:

~~~text
module billing {
    import common.money
    calculate total = amount + fee
}
~~~

Nếu fee được khai báo trong common.money với kiểu khác, diagnostic tại phép cộng có thể liên kết đến khai báo fee trong tài liệu được import.

### 14.1. RelatedInformation

Related information có thể chứa location và message cho mỗi vị trí liên quan. Editor có thể hiển thị vị trí khai báo hoặc nguồn gốc của lỗi.

### 14.2. Cross-file diagnostics

Một số lỗi không thuộc duy nhất một file:

- Import cycle.
- Tên trùng giữa module.
- Schema không tương thích.
- Hai khai báo cùng sở hữu một tài nguyên.
- Dependency version conflict.

Server nên xác định URI chính cho diagnostic và bổ sung các vị trí liên quan.

### 14.3. Workspace analysis

Workspace analyzer có thể chạy khi mở project, khi một file quan trọng thay đổi hoặc theo yêu cầu. Không nên quét toàn bộ workspace sau mỗi ký tự nếu chi phí quá lớn.

### 14.4. File chưa mở

Client có thể không có buffer cho file liên quan. Server vẫn có thể đọc nội dung từ filesystem hoặc cache theo quyền và chính sách. Cần phân biệt nội dung trên đĩa với buffer chưa lưu của tài liệu đang mở.

## 15. Diagnostic code, severity và cấu hình người dùng

Một language server thường cần cho phép điều chỉnh mức độ của một số quy tắc.

### 15.1. Severity theo quy tắc

Ví dụ:

| Rule | Mặc định | Có thể cấu hình |
|---|---|---|
| Syntax error | Error | Không nên hạ nếu tài liệu không parse được |
| Unknown symbol | Error | Tùy chế độ permissive |
| Unused variable | Warning | Có |
| Deprecated syntax | Warning | Có |
| Style preference | Hint | Có |

Không nên cho cấu hình làm mất những điều kiện cần thiết để bảo đảm runtime an toàn nếu DSL yêu cầu bắt buộc.

### 15.2. Disable rule

Có thể cho phép tắt một số lint rule theo workspace hoặc file. Quy tắc tắt cần được xác định rõ phạm vi và không nên ảnh hưởng các diagnostic từ parser hoặc type checker cốt lõi.

### 15.3. Suppression directive

DSL có thể hỗ trợ directive bỏ qua một rule:

~~~text
# diagnostic: disable DSL-LINT-012
let legacy_name = 1
~~~

Suppression cần giới hạn phạm vi và lưu dấu để nhóm có thể quản lý. Nếu directive sai mã hoặc bỏ qua rule không tồn tại, server có thể báo diagnostic riêng.

### 15.4. Stable diagnostic codes

Code nên ổn định qua các lần phát hành. Message có thể được diễn đạt lại hoặc dịch, nhưng code là định danh phù hợp cho công cụ, tài liệu và cấu hình.

### 15.5. Localization

Message có thể được dịch theo locale của client hoặc server. Nội dung code và cấu trúc diagnostic nên không phụ thuộc ngôn ngữ hiển thị.

## 16. Code actions và quick fixes

Diagnostic mô tả vấn đề; code action đề xuất thao tác để sửa hoặc xử lý vấn đề. Hai khái niệm liên quan nhưng tách biệt.

Ví dụ diagnostic:

~~~text
Unknown attribute "replica_count".
Did you mean "replicas"?
~~~

Code action có thể đổi tên replica_count thành replicas.

### 16.1. Code action theo diagnostic

Client có thể yêu cầu textDocument/codeAction với vùng hoặc diagnostics liên quan. Server trả về các action phù hợp.

### 16.2. Quick fix

Quick fix là code action nhằm sửa vấn đề cụ thể:

- Thêm thuộc tính bắt buộc.
- Sửa tên symbol gần giống.
- Thêm import.
- Đổi kiểu literal.
- Thêm dấu đóng block.

### 16.3. Không tự sửa nguồn trong diagnostic

Diagnostic chỉ báo vấn đề. Server không nên tự sửa nội dung tài liệu khi chỉ publish diagnostics, trừ khi có một protocol feature hoặc hành động riêng được client yêu cầu.

### 16.4. Versioned edits

WorkspaceEdit có thể cần version để tránh áp dụng sửa đổi trên nội dung đã thay đổi kể từ lúc code action được tính. Server nên kiểm tra document version hoặc dùng cơ chế versioned edit phù hợp.

### 16.5. Resolve code action

Nếu có nhiều action hoặc dữ liệu bổ sung chỉ cần khi người dùng chọn, server có thể dùng resolve để tính chi tiết muộn, tùy capability client.

## 17. Pull diagnostics và result caching

Pull diagnostics có thể giảm truyền dữ liệu lặp khi nội dung không đổi.

### 17.1. Result ID

Server có thể tạo resultId đại diện cho một tập diagnostics của tài liệu. Khi client gửi lại resultId, server so sánh với trạng thái hiện tại.

Nếu kết quả vẫn không đổi, server trả report unchanged. Nếu thay đổi, server trả full report mới.

### 17.2. Result ID phải gắn với đúng trạng thái

ResultId nên phản ánh các yếu tố ảnh hưởng diagnostics:

- Document version hoặc content hash.
- Compiler/language server version.
- Schema version.
- Dependency state.
- Cấu hình diagnostics.
- Các tài nguyên workspace liên quan.

Nếu schema thay đổi nhưng document không đổi, diagnostics có thể thay đổi. Khi đó resultId cũ không còn hợp lệ.

### 17.3. Full report

Full report chứa toàn bộ diagnostics hiện tại cho tài liệu. Client có thể thay thế kết quả cũ bằng report mới.

### 17.4. Unchanged report

Unchanged report nói rằng kết quả gắn với resultId đã biết vẫn còn hiệu lực. Server không nên dùng unchanged chỉ vì nội dung tài liệu không đổi nếu dependency hoặc cấu hình có thể đã thay đổi.

### 17.5. Workspace diagnostic

Workspace diagnostics có thể trả nhiều tài liệu, kết hợp partial result và progress để không phải đợi toàn bộ workspace trước khi client nhận phần đầu tiên. Server cần tuân thủ capability đã thương lượng và đảm bảo report không trộn version không nhất quán.

## 18. Performance và khả năng mở rộng

Chẩn đoán thời gian thực phải đủ nhanh để không làm gián đoạn thao tác soạn thảo.

### 18.1. Phân tích theo tầng

Có thể chạy các bước nhanh trước:

1. Lexing và parsing.
2. Kiểm tra cú pháp cơ bản.
3. Resolve symbol cục bộ.
4. Type checking.
5. Phân tích liên tài liệu.
6. Lint sâu hoặc kiểm tra tốn kém.

Kết quả nhanh có thể được cập nhật trước, trong khi phân tích sâu chạy nền. Nếu dùng push diagnostics, cần hợp nhất đúng tập kết quả thay vì để lần publish nhanh xóa các diagnostics sâu vẫn còn hiệu lực.

### 18.2. Caching

Cache có thể lưu:

- AST theo document version.
- Symbol table theo module.
- Schema đã resolve.
- Kết quả phân tích theo node.
- Diagnostics theo content/dependency fingerprint.

Cache cần invalidation đúng khi source, schema, config hoặc dependency thay đổi.

### 18.3. Giới hạn workspace scan

Workspace lớn có thể có hàng nghìn file. Server có thể:

- Quét theo module hoặc thư mục.
- Ưu tiên file đang mở và dependency gần.
- Dùng file watcher để cập nhật phần thay đổi.
- Chạy kiểm tra sâu theo yêu cầu.
- Dùng giới hạn thời gian và số diagnostics.

### 18.4. Giới hạn diagnostics

Một lỗi cú pháp có thể tạo hàng nghìn lỗi phụ. Server có thể giới hạn số diagnostics trên mỗi file hoặc mỗi đợt, đồng thời phát một thông báo tổng hợp nếu đã cắt bớt kết quả.

### 18.5. Không chặn event loop của server

Nếu transport hoặc server framework dùng event loop, các phép phân tích CPU-bound dài không nên chạy trực tiếp trên event loop. Dùng worker executor phù hợp và trả kết quả qua cơ chế an toàn luồng.

### 18.6. Đo độ trễ

Đo các mốc:

- Thời điểm nhận didChange.
- Thời điểm job bắt đầu.
- Thời gian parse.
- Thời gian semantic analysis.
- Thời gian mapping.
- Thời điểm publish hoặc trả response.

Các số liệu này giúp xác định chậm ở scheduler, parser, dependency lookup hay giao tiếp LSP.

## 19. Diagnostics trong DSL có schema và tài nguyên ngoài

DSL có thể tham chiếu schema database, file, plugin hoặc dịch vụ. Chẩn đoán phụ thuộc vào các nguồn này cần được quản lý riêng.

### 19.1. Schema loading

Nếu schema chưa tải xong, server có thể tạm thời chưa xác định được kiểu của field. Cần phân biệt trạng thái pending với lỗi field không tồn tại.

### 19.2. External resource

Nếu file nguồn không tồn tại, diagnostic có thể chỉ ra đường dẫn. Nếu filesystem hoặc network tạm thời không truy cập được, nên phân loại là environment issue thay vì kết luận chắc chắn rằng tham chiếu sai.

### 19.3. Stale schema

Một diagnostic có thể được tính theo schema cũ. Khi schema mới được tải, server cần invalidate các kết quả phụ thuộc và phân tích lại.

### 19.4. Plugin diagnostics

Plugin có thể đóng góp diagnostics. Server cần xác định nguồn, giới hạn thời gian, xử lý lỗi plugin và ngăn plugin làm treo toàn bộ language server.

### 19.5. Partial availability

Nếu một nguồn metadata không sẵn sàng, server có thể tiếp tục cung cấp diagnostics cú pháp và các kiểm tra không phụ thuộc nguồn đó. Cần tránh biến lỗi tạm thời thành hàng loạt unknown symbol giả.

## 20. Diagnostics cho tài liệu sinh ra và tài liệu ảo

Một số DSL có generated file, notebook cell, embedded language hoặc virtual document.

### 20.1. Generated source

Compiler có thể tạo một file trung gian từ DSL. Lỗi ở file sinh ra cần được ánh xạ về nguồn DSL để người dùng sửa đúng chỗ.

### 20.2. Embedded language

Một block DSL có thể chứa SQL hoặc expression language khác. Language server có thể gọi analyzer riêng rồi chuyển diagnostics về vùng tương ứng trong tài liệu chủ.

### 20.3. Virtual document

Một virtual document có URI riêng nhưng không nhất thiết tồn tại trên filesystem. Server cần quản lý mapping từ virtual URI về source document và xử lý vòng đời khi nội dung gốc thay đổi.

### 20.4. Generated diagnostics không có source span trực tiếp

Nếu compiler tạo node synthetic, diagnostic có thể gắn với cấu trúc nguồn đã tạo ra node đó hoặc dùng related information để giải thích. Tránh trả range không hợp lệ hoặc range vượt ngoài tài liệu.

## 21. Bảo mật và quyền riêng tư của diagnostics

Diagnostics có thể vô tình tiết lộ thông tin từ hệ thống ngoài:

- Đường dẫn tuyệt đối trên máy.
- Tên host hoặc endpoint nội bộ.
- Giá trị cấu hình nhạy cảm.
- Nội dung secret trong thông báo lỗi.
- Tên người dùng hoặc tài nguyên không được phép xem.

Một số nguyên tắc:

- Không đưa secret hoặc credential vào message.
- Giới hạn thông tin đường dẫn theo workspace và quyền.
- Xác thực URI và đường dẫn trước khi truy cập file.
- Không tin dữ liệu diagnostic.data do client gửi lại.
- Kiểm soát plugin và extension có quyền phân tích workspace.
- Không thực hiện truy cập network tùy ý chỉ vì nội dung DSL yêu cầu.
- Giới hạn kích thước message và số diagnostics.

Thông báo nên giải thích đủ để sửa lỗi nhưng không tiết lộ dữ liệu ngoài phạm vi người dùng được phép truy cập.

## 22. Kiểm thử real-time diagnostics

Kiểm thử cần xác nhận cả nội dung diagnostic lẫn thời điểm và vòng đời cập nhật.

### 22.1. Kiểm thử mapping vị trí

Bao phủ:

- Dòng đầu và dòng cuối.
- Ký tự Unicode ngoài BMP.
- Tab và newline.
- Range zero-width tại EOF.
- Range nhiều dòng.
- Thay đổi encoding nếu client/server thương lượng.

### 22.2. Kiểm thử version

Tạo hai analysis job cho hai version và cố ý cho job cũ hoàn tất sau job mới. Xác nhận kết quả cũ không ghi đè diagnostics mới.

### 22.3. Kiểm thử xóa diagnostics

Tạo một lỗi, xác nhận diagnostic được publish, sau đó sửa lỗi và xác nhận tập diagnostics được thay bằng tập mới hoặc rỗng.

### 22.4. Kiểm thử incremental edits

Gửi các thay đổi theo range và xác nhận document store có nội dung giống client. Bao phủ nhiều edit trong cùng notification nếu sync mode cho phép.

### 22.5. Kiểm thử error recovery

Dùng tài liệu chưa hoàn chỉnh và xác nhận server vẫn tìm được các lỗi độc lập phía sau mà không tạo quá nhiều lỗi dây chuyền.

### 22.6. Kiểm thử cross-file

Thay schema hoặc module được import và xác nhận diagnostics của các tài liệu phụ thuộc được cập nhật.

### 22.7. Kiểm thử cancellation

Gửi nhiều thay đổi liên tiếp và xác nhận công việc cũ được hủy hoặc bỏ kết quả, không tiêu tốn tài nguyên không cần thiết.

### 22.8. Kiểm thử push/pull

Với push, kiểm tra publishDiagnostics thay thế tập cũ và xóa đúng khi rỗng. Với pull, kiểm tra full, unchanged, resultId và workspace report theo capability.

### 22.9. Kiểm thử hiệu năng

Đo độ trễ trên file nhỏ, file lớn, workspace lớn và tài liệu có nhiều lỗi. Xác nhận server vẫn phản hồi các request tương tác khác trong khi phân tích sâu chạy nền.

## 23. Triển khai diagnostics bằng Java

Java language server có thể dùng thư viện LSP4J để trao đổi LSP. Ví dụ dưới đây minh họa cách tạo và publish diagnostics; tên lớp thuộc API LSP4J phổ biến và có thể thay đổi theo phiên bản thư viện.

### 23.1. Tạo Diagnostic

~~~java
import org.eclipse.lsp4j.Diagnostic;
import org.eclipse.lsp4j.DiagnosticSeverity;
import org.eclipse.lsp4j.Position;
import org.eclipse.lsp4j.Range;

Diagnostic createTypeDiagnostic() {
    Diagnostic diagnostic = new Diagnostic();
    diagnostic.setRange(new Range(
        new Position(2, 11),
        new Position(2, 28)
    ));
    diagnostic.setSeverity(DiagnosticSeverity.Error);
    diagnostic.setCode("DSL-TYPE-004");
    diagnostic.setSource("dsl-typechecker");
    diagnostic.setMessage(
        "Không thể so sánh giá trị Decimal với String."
    );
    return diagnostic;
}
~~~

Vị trí trong ví dụ là zero-based và giả định encoding phù hợp. Trong server thực tế, range phải được tính từ source span theo position encoding đã thương lượng, không nên hard-code.

### 23.2. Publish diagnostics

~~~java
import java.util.List;
import org.eclipse.lsp4j.PublishDiagnosticsParams;

void publish(
        String uri,
        Integer documentVersion,
        List<Diagnostic> diagnostics
) {
    PublishDiagnosticsParams params =
        new PublishDiagnosticsParams(uri, diagnostics);
    params.setVersion(documentVersion);
    client.publishDiagnostics(params);
}
~~~

Ví dụ giả định client là LanguageClient của server. Trước khi gọi publish, cần xác nhận documentVersion vẫn là phiên bản hiện tại. Khi không còn lỗi, truyền danh sách rỗng.

### 23.3. Diagnostic collector

Có thể dùng collector nội bộ để gom kết quả:

~~~java
import java.util.ArrayList;
import java.util.List;

final class DiagnosticCollector {
    private final List<Diagnostic> diagnostics = new ArrayList<>();

    void add(Diagnostic diagnostic) {
        diagnostics.add(diagnostic);
    }

    List<Diagnostic> snapshot() {
        return List.copyOf(diagnostics);
    }
}
~~~

Mỗi analysis phase có thể đóng góp diagnostics. Trước khi publish, server có thể chuẩn hóa, sắp xếp và loại bỏ bản trùng theo chính sách.

### 23.4. Phân tích bất đồng bộ và version guard

~~~java
void analyzeDocument(DocumentSnapshot snapshot) {
    executor.submit(() -> {
        List<Diagnostic> result = analyzer.analyze(snapshot);

        DocumentSnapshot current =
            documentStore.get(snapshot.uri());

        if (current == null) {
            return;
        }

        if (current.version() != snapshot.version()) {
            return;
        }

        publish(
            snapshot.uri(),
            snapshot.version(),
            result
        );
    });
}
~~~

Đây là pseudocode Java. DocumentSnapshot nên bất biến để analyzer luôn đọc đúng nội dung của một version. Trong triển khai thực tế, cần xử lý cancellation, lỗi executor và trạng thái document đóng.

### 23.5. Debounce

Có thể giữ một scheduled task theo URI. Mỗi didChange hủy lịch cũ và đặt lịch mới. Khi tác vụ chạy, nó lấy snapshot version mới nhất và bắt đầu phân tích.

Không nên dùng một timer toàn cục cho mọi file nếu việc gõ trong file này có thể liên tục trì hoãn diagnostics của file khác.

## 24. Thiết kế diagnostics ổn định và dễ dùng

Diagnostic là giao diện giữa compiler và người dùng. Message cần tập trung vào vấn đề có thể hành động.

### 24.1. Message cụ thể

Message yếu:

~~~text
Invalid expression.
~~~

Message hữu ích hơn:

~~~text
Không thể so sánh amount kiểu Decimal với "high" kiểu String.
Hãy dùng một giá trị số hoặc chuyển đổi tường minh.
~~~

### 24.2. Phân biệt lỗi gốc và lỗi hệ quả

Nếu thiếu import khiến nhiều symbol không resolve, nên ưu tiên diagnostic về import và tránh tạo quá nhiều lỗi unknown symbol dây chuyền.

### 24.3. Vị trí đúng

Gắn diagnostic vào phần nhỏ nhất có liên quan. Nếu lỗi do một khai báo định nghĩa sai kiểu, có thể đặt diagnostic ở khai báo và dùng relatedInformation tại chỗ sử dụng.

### 24.4. Code ổn định

Giữ mã diagnostic ổn định để người dùng có thể cấu hình lint, viết test và tra tài liệu. Thay đổi message không nên bắt buộc đổi code nếu bản chất rule không đổi.

### 24.5. Phân biệt trạng thái phân tích

Không tìm thấy lỗi có thể có nghĩa tài liệu hợp lệ, hoặc phân tích chưa hoàn tất, hoặc một dependency chưa tải. Server nên tránh hiển thị trạng thái “không lỗi” nếu thực tế chưa thể kiểm tra các quy tắc quan trọng.

## 25. Những sai lầm thường gặp

### 25.1. Phân tích đồng bộ trên luồng giao tiếp

Parser hoặc semantic analysis dài có thể làm server không xử lý kịp các request khác. Chạy công việc nặng trên executor phù hợp và trả kết quả khi hoàn tất.

### 25.2. Không gắn diagnostics với document version

Job cũ có thể hoàn tất sau job mới và ghi đè kết quả. Dùng snapshot, version hoặc generation token để loại kết quả stale.

### 25.3. Chỉ publish phần diagnostic vừa thay đổi

Push diagnostics thường thay thế toàn bộ danh sách của URI. Gửi một phần có thể làm mất diagnostics còn hiệu lực. Hãy publish tập đầy đủ hoặc dùng cơ chế pull/delta đúng protocol.

### 25.4. Không gửi danh sách rỗng

Khi lỗi đã được sửa, server cần xóa diagnostics cũ. Nếu không, editor có thể tiếp tục hiển thị gạch chân không còn đúng.

### 25.5. Range sai vì Unicode

Dùng code point hoặc byte offset như thể đó là UTF-16 character offset có thể làm range lệch. Chuyển đổi theo encoding đã thương lượng.

### 25.6. Báo quá nhiều lỗi dây chuyền

Parser recovery kém có thể tạo nhiều lỗi từ một nguyên nhân. Dùng error node, synchronization point và kiểm soát semantic checks trên vùng hỏng.

### 25.7. Bỏ qua dependency ngoài tài liệu

Schema hoặc module thay đổi có thể làm diagnostics cũ không còn đúng. Cần dependency graph và invalidation.

### 25.8. Dùng severity tùy tiện

Nếu mọi vấn đề đều là Error, Problems view mất giá trị ưu tiên. Phân loại severity theo khả năng ảnh hưởng chương trình và chính sách DSL.

### 25.9. Nhầm diagnostic với code action

Diagnostic giải thích vấn đề; code action là thao tác sửa. Tách hai trách nhiệm giúp client kiểm soát khi nào thay đổi văn bản.

### 25.10. Không kiểm tra capability

Không phải client nào cũng hỗ trợ mọi tính năng pull, related information, code action hoặc progress. Server cần thương lượng capability và có fallback phù hợp.

### 25.11. Cache resultId không bao gồm dependency

Document không đổi nhưng schema có thể đổi. Nếu resultId chỉ dựa vào nội dung file, server có thể trả unchanged sai.

### 25.12. Message làm lộ dữ liệu

Thông báo lỗi có thể chứa path, endpoint hoặc giá trị cấu hình nhạy cảm. Chỉ đưa thông tin người dùng có quyền xem.

## 26. Quy trình xây dựng real-time diagnostics cho DSL

Một quy trình triển khai có thể gồm:

1. **Xác định các loại diagnostic.** Liệt kê lỗi lexer, parser, name resolution, type, domain, lint và môi trường.
2. **Thiết kế mô hình nội bộ.** Chuẩn hóa code, severity, message, source span, related location và dữ liệu bổ sung.
3. **Xây document store.** Theo dõi URI, nội dung, version và trạng thái mở/đóng.
4. **Tích hợp parser recovery.** Cho phép phân tích tài liệu chưa hoàn chỉnh mà hạn chế lỗi dây chuyền.
5. **Tích hợp semantic analysis.** Resolve symbol, kiểu và dependency.
6. **Xây diagnostic mapper.** Chuyển source span sang LSP Range theo position encoding.
7. **Chọn push hoặc pull.** Thương lượng capability và xác định cách cache kết quả.
8. **Thêm scheduler.** Debounce, cancellation, ưu tiên và worker executor.
9. **Bảo vệ version.** Dùng snapshot và guard trước khi publish hoặc trả report.
10. **Quản lý tập diagnostics.** Thay thế đầy đủ, xóa khi hết lỗi và cập nhật tài liệu phụ thuộc.
11. **Thêm code actions.** Cung cấp quick fixes riêng với diagnostics.
12. **Tối ưu incremental analysis.** Cache và invalidate theo dependency.
13. **Bổ sung observability.** Đo thời gian nhận thay đổi, phân tích và publish.
14. **Kiểm thử protocol và vị trí.** Bao phủ Unicode, version, cancellation, pull/push, workspace và lỗi liên tài liệu.
15. **Kiểm soát quyền và dữ liệu.** Tránh tiết lộ secret hoặc truy cập tài nguyên ngoài phạm vi.

Mục tiêu là làm cho diagnostic chính xác, cập nhật đúng phiên bản và đủ nhanh để hỗ trợ người dùng trong lúc viết DSL.

## 27. Câu hỏi tự kiểm tra

1. Chẩn đoán thời gian thực là gì và Language Server đóng vai trò nào?
2. Phân biệt diagnostic cú pháp, ngữ nghĩa, kiểu, quy tắc miền và lint.
3. Push diagnostics và pull diagnostics khác nhau như thế nào?
4. Những trường quan trọng của LSP Diagnostic là gì?
5. Severity trong LSP có những mức nào?
6. Vì sao LSP Position dùng chỉ số zero-based và vì sao position encoding quan trọng?
7. UTF-8, UTF-16 và Unicode code point có thể tạo ra offset khác nhau như thế nào?
8. Parser recovery giúp diagnostics hữu ích hơn trong lúc người dùng đang gõ ra sao?
9. Debounce, throttle và cancellation giải quyết những vấn đề nào?
10. Vì sao phải gắn analysis result với document version?
11. Incremental analysis cần dependency graph và invalidation như thế nào?
12. Vì sao publishDiagnostics nên gửi tập đầy đủ và gửi danh sách rỗng khi không còn lỗi?
13. RelatedInformation hỗ trợ chẩn đoán liên tài liệu như thế nào?
14. Diagnostic khác code action và quick fix ra sao?
15. ResultId trong pull diagnostics cần phản ánh những yếu tố nào ngoài nội dung tài liệu?
16. Hãy mô tả cách xử lý khi schema được import thay đổi nhưng file DSL đang mở không đổi.
17. Những chỉ số nào giúp đánh giá độ trễ và khả năng mở rộng của real-time diagnostics?
18. Hãy đề xuất kiến trúc diagnostics cho một DSL có parser, type checker, schema ngoài và nhiều file phụ thuộc; nêu cách tránh kết quả stale.
