# Khởi tạo phiên

Trong kiến trúc **Language Server**, client và server là hai tiến trình phối hợp để cung cấp các tính năng ngôn ngữ như hoàn thành mã, diagnostics, điều hướng symbol, rename, formatting và hỗ trợ refactoring. Trước khi trao đổi những yêu cầu này, hai bên cần thống nhất môi trường làm việc và những khả năng mà mỗi bên hỗ trợ. Bước trao đổi ban đầu đó được gọi là **khởi tạo phiên (initialization)**.

Với Language Server Protocol (LSP), client gửi một yêu cầu JSON-RPC có method là **initialize**. Yêu cầu này mang thông tin về client, workspace và các capability mà client hỗ trợ. Server đọc thông tin đó, chuẩn bị trạng thái cần thiết rồi trả về **InitializeResult**, trong đó công bố capability của server. Sau khi nhận kết quả, client gửi notification **initialized** để thông báo rằng quá trình khởi tạo đã hoàn tất và phiên có thể chuyển sang trao đổi các thông điệp thông thường.

Khởi tạo phiên không chỉ là bước mở socket hoặc tạo tiến trình. Đây là hợp đồng ban đầu xác định server sẽ hoạt động trong môi trường nào, hỗ trợ những tính năng nào, quản lý workspace ra sao và xử lý vòng đời phiên như thế nào. Một server khởi tạo sai có thể chạy được nhưng không cung cấp đúng tính năng, gửi thông điệp mà client không hiểu hoặc dùng nhầm thư mục dự án.

## 1. Khởi tạo phiên là gì?

**Initialization** là giai đoạn đầu của vòng đời một phiên LSP. Client và server trao đổi thông tin để thiết lập ngữ cảnh và thương lượng khả năng trước khi xử lý các yêu cầu ngôn ngữ.

Quá trình này thường gồm ba thông điệp chính:

1. Client gửi request **initialize**.
2. Server trả response chứa **InitializeResult**.
3. Client gửi notification **initialized**.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant C as Language Client
    participant S as Language Server
    C->>S: initialize request
    Note over S: Đọc client capabilities, workspace và options
    S-->>C: InitializeResult + server capabilities
    C->>S: initialized notification
    Note over C,S: Phiên đã sẵn sàng cho trao đổi thông thường
    C->>S: textDocument/didOpen
    S-->>C: publishDiagnostics
~~~

Trong LSP, initialize là request đầu tiên mà client gửi tới server sau khi thiết lập transport. Server cần tuân thủ trạng thái khởi tạo: không xử lý các request nghiệp vụ thông thường như thể phiên đã sẵn sàng trước khi hoàn tất handshake. Notification initialized đánh dấu thời điểm client đã nhận và áp dụng capability của server.

### 1.1. Vì sao phải có handshake?

Client và server có thể khác nhau về:

- Phiên bản LSP được hỗ trợ.
- Các tính năng editor có thể hiển thị.
- Cách quản lý workspace và nhiều thư mục.
- Khả năng gửi progress, diagnostics hoặc semantic tokens.
- Cách biểu diễn vị trí văn bản.
- Những tùy chọn riêng của server hoặc extension.

Handshake giúp hai bên không giả định rằng đối phương có mọi tính năng. Client công bố khả năng của mình; server công bố khả năng mà nó sẽ cung cấp trong phiên hiện tại.

### 1.2. Phiên LSP và tiến trình server

Một tiến trình language server có thể phục vụ một phiên hoặc nhiều phiên tùy kiến trúc client và server. Nhiều triển khai khởi chạy một tiến trình cho một workspace hoặc một nhóm workspace. Dù số tiến trình thế nào, mỗi kết nối hoặc session cần có trạng thái khởi tạo riêng và không được trộn capability, workspace hay tài liệu giữa các session.

## 2. Vị trí của initialize trong vòng đời LSP

Vòng đời một phiên LSP thường có các giai đoạn:

1. Client khởi chạy server hoặc kết nối tới server đang chạy.
2. Hai bên thiết lập transport, thường là stdio hoặc socket.
3. Client gửi initialize request.
4. Server trả InitializeResult.
5. Client gửi initialized notification.
6. Hai bên trao đổi request, response và notification.
7. Client gửi shutdown request khi muốn kết thúc có trật tự.
8. Client gửi exit notification sau khi xử lý shutdown.
9. Tiến trình hoặc session kết thúc.

~~~mermaid
stateDiagram-v2
    [*] --> Starting
    Starting --> Initializing: initialize
    Initializing --> AwaitingInitialized: InitializeResult
    AwaitingInitialized --> Running: initialized
    Running --> ShuttingDown: shutdown
    ShuttingDown --> Exiting: shutdown response
    Exiting --> [*]: exit
~~~

Server nên biểu diễn vòng đời bằng trạng thái rõ ràng, chẳng hạn:

| Trạng thái | Ý nghĩa | Thông điệp thường hợp lệ |
|---|---|---|
| Starting | Process hoặc transport vừa được tạo | Chờ initialize |
| Initializing | Đang xử lý initialize | initialize đang được thực hiện |
| AwaitingInitialized | Đã trả kết quả initialize, chờ client xác nhận | initialized |
| Running | Phiên đã sẵn sàng | Các request/notification LSP đã thương lượng |
| ShuttingDown | Đang xử lý shutdown | shutdown và hoàn tất |
| Exiting | Chờ kết thúc process/session | exit |

Tên trạng thái là chi tiết triển khai, không phải các enum bắt buộc của LSP. Điều quan trọng là server thực thi đúng quy tắc chuyển trạng thái.

## 3. Initialize request

Client gửi JSON-RPC request có method là initialize. Request có ID để client ghép response với yêu cầu ban đầu.

Ví dụ rút gọn:

~~~json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "processId": 12345,
    "rootUri": "file:///projects/shop",
    "capabilities": {}
  }
}
~~~

Ví dụ trên chỉ minh họa cấu trúc cơ bản. Trong LSP thực tế, params có nhiều trường tùy phiên bản và client. Server cần đọc theo schema của phiên bản protocol được hỗ trợ, đồng thời xử lý trường tùy chọn hoặc giá trị null đúng cách.

Initialize request thường mang các nhóm thông tin:

- Thông tin tiến trình client.
- Workspace hoặc thư mục gốc.
- Capability của client.
- Tùy chọn khởi tạo riêng.
- Locale và mức trace nếu được cung cấp.
- Token dùng cho work-done progress nếu được hỗ trợ.

Server không nên coi mọi trường là bắt buộc. Ví dụ, client có thể không cung cấp processId hoặc workspace root; một số client không hỗ trợ workspace folders.

## 4. InitializeParams

Trong LSP, tham số initialize được biểu diễn bằng cấu trúc **InitializeParams**. Các trường thường gặp gồm:

| Trường | Mục đích |
|---|---|
| processId | ID tiến trình client hoặc null nếu không biết |
| clientInfo | Tên và phiên bản client |
| locale | Locale của client nếu được cung cấp |
| rootPath | Đường dẫn root kiểu cũ, đã deprecated |
| rootUri | URI workspace root kiểu cũ, đã deprecated |
| initializationOptions | Dữ liệu tùy chọn riêng dành cho server |
| capabilities | Các capability mà client hỗ trợ |
| trace | Mức trace mong muốn |
| workspaceFolders | Danh sách workspace folder nếu client hỗ trợ |
| workDoneToken | Token dùng cho progress của quá trình khởi tạo |

Các trường cụ thể phụ thuộc phiên bản LSP. Một server nên chọn phiên bản protocol rõ ràng, đọc trường theo đặc tả tương ứng và không giả định mọi client gửi cùng một tập dữ liệu.

### 4.1. processId

processId cho biết process ID của client nếu client có thể cung cấp. Giá trị có thể là null khi client không biết hoặc không thể cung cấp thông tin này.

Server có thể dùng thông tin này cho quản lý process hoặc diagnostics vận hành, nhưng không nên phụ thuộc vào nó để xác định workspace hay quyền truy cập. Process ID có ý nghĩa trong hệ điều hành và môi trường cụ thể; nó không phải định danh ổn định của người dùng hoặc project.

### 4.2. clientInfo

clientInfo có thể chứa tên và phiên bản client. Ví dụ:

~~~json
{
  "name": "Example Editor",
  "version": "8.2.1"
}
~~~

Server có thể dùng thông tin này để chẩn đoán tương thích hoặc ghi log. Không nên dùng tên client làm cơ chế bảo mật hoặc giả định rằng hai client cùng tên luôn có capability giống nhau.

### 4.3. locale

locale cho biết ngôn ngữ hoặc locale mà client muốn dùng nếu có hỗ trợ. Server có thể dùng nó để chọn ngôn ngữ cho thông báo hoặc nội dung hiển thị. Các mã locale và fallback cần được xử lý nhất quán; nếu locale không được hỗ trợ, server nên dùng fallback đã định nghĩa.

### 4.4. rootPath và rootUri

rootPath là trường cũ biểu diễn đường dẫn workspace và đã deprecated. rootUri cũng là trường cũ cho URI gốc; các phiên bản LSP mới khuyến nghị dùng workspaceFolders để mô tả workspace.

Server vẫn có thể cần hỗ trợ client cũ. Khi đó, cần có chính sách fallback rõ:

1. Dùng workspaceFolders nếu được cung cấp và phù hợp.
2. Nếu không có, xem xét rootUri theo phiên bản protocol.
3. Chỉ dùng rootPath cho tương thích với client cũ khi cần.
4. Nếu không có workspace root, chuyển sang chế độ không có workspace hoặc yêu cầu cấu hình riêng.

Không nên giả định rootUri luôn là một URI hợp lệ hoặc luôn trỏ tới thư mục hiện có.

### 4.5. initializationOptions

initializationOptions là dữ liệu tùy chọn do client gửi cho server. Đây là nơi một client có thể chuyển cấu hình riêng như:

~~~json
{
  "settingsProfile": "strict",
  "enableExperimentalRules": true,
  "libraryPaths": ["./dsl-libs"],
  "analysisMode": "workspace"
}
~~~

Nội dung thực tế phụ thuộc hợp đồng giữa client và server. LSP không áp đặt một schema chung cho mọi initializationOptions.

Server nên:

- Xác thực kiểu và giá trị của từng trường.
- Cung cấp giá trị mặc định.
- Bỏ qua hoặc báo rõ trường không được hỗ trợ theo chính sách đã định.
- Không coi dữ liệu client là đáng tin cậy.
- Tài liệu hóa schema và version của options riêng.

Không nên nhầm initializationOptions với workspace configuration được lấy qua các request cấu hình sau khi phiên đã chạy. Initialization options phù hợp cho dữ liệu cần có ngay trong handshake; cấu hình có thể thay đổi trong phiên thường cần cơ chế configuration riêng.

### 4.6. trace

Trường trace cho phép client yêu cầu mức thông tin trace. Các mức thường gặp là:

- off: không yêu cầu trace thông điệp ở mức protocol.
- messages: ghi nhận thông điệp.
- verbose: ghi nhận thông tin chi tiết hơn.

Trace hữu ích khi debug handshake và giao tiếp LSP. Server cần kiểm soát lượng log, tránh ghi dữ liệu nhạy cảm của tài liệu hoặc cấu hình vào log ngoài ý muốn.

### 4.7. workDoneToken

workDoneToken cho phép gắn quá trình khởi tạo với cơ chế progress. Nếu server thực hiện công việc khởi tạo kéo dài như lập chỉ mục workspace, nó có thể báo tiến độ theo khả năng client đã công bố.

Token là định danh cho progress operation, không phải dữ liệu để xác thực hoặc quyền truy cập.

## 5. Workspace và workspaceFolders

Workspace xác định phạm vi dự án mà language server phân tích. Với DSL, workspace có thể chứa source file, module, schema, thư viện, cấu hình và các file được import.

Trong các phiên bản LSP hỗ trợ workspace folders, client có thể gửi danh sách thư mục:

~~~json
{
  "workspaceFolders": [
    {
      "uri": "file:///projects/shop",
      "name": "shop"
    },
    {
      "uri": "file:///projects/shared-rules",
      "name": "shared-rules"
    }
  ]
}
~~~

Server cần phân biệt:

- Client không hỗ trợ workspace folders.
- Client hỗ trợ nhưng hiện không mở workspace folder nào.
- Client cung cấp một hoặc nhiều workspace folder.

Không nên mặc định chỉ có một root. Một client có thể mở nhiều project hoặc nhiều thư mục liên quan trong cùng một cửa sổ.

### 5.1. URI và đường dẫn hệ thống

LSP sử dụng URI để định danh tài nguyên. Server cần chuyển URI sang đường dẫn hệ thống bằng thư viện URI phù hợp, không tự cắt chuỗi theo tiền tố file://.

Ví dụ:

~~~text
file:///C:/work/shop
file:///home/dev/shop
~~~

Hai dạng URI trên minh họa đường dẫn trên các hệ điều hành khác nhau. Cách giải mã percent-encoding, xử lý dấu cách, ký tự Unicode và phân biệt chữ hoa/chữ thường cần dựa trên URI parser và quy tắc filesystem của nền tảng.

### 5.2. Workspace không phải sandbox

Workspace root cho biết phạm vi dự án, không tự động cấp quyền truy cập an toàn vào mọi file con hoặc file ngoài workspace. Nếu server đọc file, resolve import hoặc chạy tool, nó cần áp dụng chính sách truy cập và xác thực path phù hợp.

### 5.3. Workspace thay đổi sau khởi tạo

Client có thể thêm hoặc xóa workspace folder trong phiên nếu client và server hỗ trợ khả năng này. Server cần đăng ký hoặc công bố khả năng workspace folder tương ứng, rồi xử lý notification thay đổi theo protocol.

Initialize chỉ thiết lập trạng thái ban đầu; nó không có nghĩa workspace bất biến trong toàn bộ vòng đời session.

## 6. Client capabilities

Trường capabilities trong InitializeParams mô tả những tính năng mà client có thể xử lý. Server dùng thông tin này để quyết định capability nào có thể cung cấp và cách gửi dữ liệu.

Ví dụ rút gọn:

~~~json
{
  "capabilities": {
    "textDocument": {
      "completion": {
        "completionItem": {
          "snippetSupport": true,
          "documentationFormat": ["markdown", "plaintext"]
        }
      },
      "hover": {
        "contentFormat": ["markdown", "plaintext"]
      },
      "publishDiagnostics": {
        "relatedInformation": true
      }
    },
    "workspace": {
      "workspaceFolders": true,
      "configuration": true
    }
  }
}
~~~

Ví dụ chỉ nêu một số trường. Capability tree thực tế khá rộng và được mở rộng qua các phiên bản LSP.

### 6.1. Vì sao client phải công bố capability?

Một server có thể hỗ trợ nhiều dạng thông tin hơn client hiển thị được. Ví dụ:

- Client có thể hỗ trợ Markdown trong hover hoặc chỉ hỗ trợ plaintext.
- Client có thể hiển thị completion item dạng snippet hoặc chỉ text đơn giản.
- Client có thể nhận diagnostics kèm related information hoặc chỉ nhận message cơ bản.
- Client có thể hỗ trợ dynamic registration hoặc chỉ capability tĩnh.
- Client có thể hỗ trợ workspace folders, configuration hoặc progress.

Server phải chọn cách phản hồi tương thích với khả năng đã công bố.

### 6.2. Capability không phải cấu hình tính năng của người dùng

Capability mô tả client có thể xử lý điều gì, không nhất thiết cho biết người dùng đã bật mọi tính năng đó. Ví dụ client hỗ trợ semantic tokens nhưng người dùng có thể tắt semantic highlighting trong giao diện. Cấu hình người dùng và capability protocol là hai khái niệm khác nhau.

### 6.3. Capability lồng nhau

Capability được tổ chức theo nhóm như general, textDocument, workspace và experimental. Server cần đọc đúng vị trí của trường theo schema LSP. Không nên kiểm tra một boolean ở nhầm cấp hoặc suy ra capability từ việc một object cha có tồn tại.

## 7. Server capabilities

Server trả về các capability mà nó sẽ cung cấp cho phiên hiện tại. Kết quả thường nằm trong trường capabilities của InitializeResult.

Ví dụ:

~~~json
{
  "capabilities": {
    "textDocumentSync": {
      "openClose": true,
      "change": 2
    },
    "hoverProvider": true,
    "definitionProvider": true,
    "completionProvider": {
      "resolveProvider": true,
      "triggerCharacters": [".", ":"]
    }
  },
  "serverInfo": {
    "name": "Example DSL Language Server",
    "version": "1.4.0"
  }
}
~~~

Đây là ví dụ rút gọn. Server chỉ nên công bố những capability mà nó thực sự triển khai và có thể duy trì trong phiên.

Một số nhóm capability thường gặp:

| Nhóm | Ví dụ |
|---|---|
| Đồng bộ văn bản | textDocumentSync |
| Điều hướng | definitionProvider, referencesProvider, implementationProvider |
| Thông tin ngữ cảnh | hoverProvider, signatureHelpProvider |
| Hoàn thành | completionProvider |
| Phân tích và sửa mã | codeActionProvider, renameProvider |
| Cấu trúc tài liệu | documentSymbolProvider, foldingRangeProvider |
| Định dạng | documentFormattingProvider, documentRangeFormattingProvider |
| Phân tích nâng cao | semanticTokensProvider, inlayHintProvider |
| Workspace | workspaceSymbolProvider, executeCommandProvider |

Danh sách này chỉ là ví dụ về các khả năng phổ biến, không phải danh sách bắt buộc.

### 7.1. Công bố đúng capability

Nếu server khai báo hoverProvider là true, client có thể gửi textDocument/hover. Nếu server không có handler tương ứng nhưng vẫn công bố capability, client có thể gửi request mà server không xử lý đúng.

Ngược lại, nếu server triển khai một tính năng nhưng không công bố capability theo cách protocol yêu cầu, client có thể không bao giờ gọi tính năng đó.

### 7.2. Static capability và dynamic registration

Một số tính năng có thể được công bố ngay trong InitializeResult. Một số tính năng khác có thể được đăng ký động sau đó nếu client hỗ trợ dynamic registration.

Ví dụ, server có thể đăng ký formatter cho một loại tài liệu hoặc một workspace cụ thể sau khi nhận cấu hình. Client cần quảng bá dynamicRegistration tương ứng; server không được tự ý gửi registration mà client không hỗ trợ.

### 7.3. Capability phụ thuộc workspace

Server có thể có khả năng chung nhưng chỉ bật một số tính năng khi workspace chứa cấu hình hoặc dependency phù hợp. Khi capability được công bố tĩnh, cần bảo đảm nó hoạt động đúng cho phiên. Nếu cần bật/tắt theo tài liệu hoặc workspace, dynamic registration có thể là cách biểu diễn phù hợp khi được hỗ trợ.

## 8. InitializeResult

Sau khi đọc InitializeParams và chuẩn bị trạng thái, server trả về **InitializeResult**. Thành phần chính là server capabilities; server có thể kèm thông tin server và dữ liệu experimental theo schema protocol.

Ví dụ:

~~~json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "capabilities": {
      "textDocumentSync": 2,
      "hoverProvider": true,
      "definitionProvider": true
    },
    "serverInfo": {
      "name": "Example DSL Server",
      "version": "1.0.0"
    }
  }
}
~~~

### 8.1. capabilities

Đây là phần quan trọng nhất của InitializeResult. Nó cho client biết các request, notification hoặc hành vi mà server hỗ trợ trong phiên.

Server cần bảo đảm capability công bố phù hợp với:

- Các handler đã được đăng ký.
- Phiên bản protocol.
- Client capabilities.
- Cấu hình runtime.
- Trạng thái khởi tạo thành công.

### 8.2. serverInfo

serverInfo có thể cung cấp tên và phiên bản server. Nó hữu ích cho diagnostics, log, báo lỗi và hỗ trợ tương thích. Đây là metadata nhận diện, không phải cơ chế thương lượng phiên bản duy nhất.

### 8.3. experimental

Một số implementation có thể sử dụng trường experimental cho tính năng thử nghiệm. Client và server phải thống nhất schema riêng. Không nên đặt tính năng cốt lõi hoặc hợp đồng ổn định vào trường này nếu đã có capability chuẩn tương ứng.

### 8.4. positionEncoding

Trong các phiên bản LSP mới, server có thể thương lượng cách biểu diễn vị trí văn bản thông qua position encoding. Nếu không thương lượng encoding khác, UTF-16 là mặc định theo đặc tả LSP. Server và client cần thống nhất cách đếm offset để range, diagnostic và edit trỏ đúng ký tự, đặc biệt với ký tự Unicode nằm ngoài Basic Multilingual Plane.

## 9. Thông báo initialized

Sau khi nhận InitializeResult và áp dụng server capabilities, client gửi notification:

~~~json
{
  "jsonrpc": "2.0",
  "method": "initialized",
  "params": {}
}
~~~

Notification này không có response vì nó là notification JSON-RPC, không phải request.

Server có thể dùng thời điểm này để:

- Bắt đầu công việc nền không cần thiết phải hoàn thành trước InitializeResult.
- Đăng ký capability động nếu client hỗ trợ.
- Gửi thông báo trạng thái hoặc progress theo protocol.
- Yêu cầu cấu hình workspace nếu phù hợp.
- Bắt đầu lập chỉ mục hoặc phân tích workspace.

Không nên gửi các thông điệp yêu cầu client hỗ trợ một capability trước khi handshake đã hoàn tất và capability liên quan đã được thương lượng.

### 9.1. Công việc khởi tạo trước và sau initialized

Một số công việc cần hoàn thành trước khi trả InitializeResult, ví dụ:

- Đọc cấu hình thiết yếu để xác định capability.
- Chọn target hoặc dialect DSL.
- Tạo các service cần thiết cho request đầu tiên.
- Xác định encoding và protocol behavior.

Các công việc tốn thời gian như lập chỉ mục toàn bộ workspace có thể tiếp tục sau initialized nếu kiến trúc cho phép. Khi đó, server có thể cung cấp progress hoặc xử lý request trong khi index chưa hoàn tất, miễn là hành vi chưa sẵn sàng được xác định rõ.

## 10. Dynamic registration sau khởi tạo

Một số capability có thể được đăng ký động sau khi phiên đã khởi tạo. Client cần công bố rằng nó hỗ trợ dynamic registration cho nhóm tương ứng.

Ví dụ khái niệm:

~~~text
client capabilities:
    textDocument.completion.dynamicRegistration = true

server:
    client/registerCapability(
        method = "textDocument/completion",
        registerOptions = ...
    )
~~~

Dynamic registration hữu ích khi:

- Capability phụ thuộc vào loại file.
- Workspace bật hoặc tắt tính năng.
- Server nạp extension sau khi khởi tạo.
- Một số tài liệu có language mode khác.
- Server cần đăng ký hoặc hủy đăng ký provider theo trạng thái dự án.

Server cần lưu registration ID để có thể unregister đúng lúc. Nếu client không hỗ trợ dynamic registration, server phải chọn capability tĩnh hoặc không cung cấp tính năng đó.

## 11. Thương lượng position encoding

Vị trí trong LSP được biểu diễn bằng line và character. Cách đếm character có ảnh hưởng tới range trong diagnostic, completion, text edit và selection.

Trong các phiên bản protocol có position encoding negotiation:

- Client có thể quảng bá các encoding mà nó hỗ trợ.
- Server chọn một encoding tương thích và công bố trong InitializeResult.
- Nếu không có lựa chọn khác được thương lượng, UTF-16 là mặc định theo protocol.

Ví dụ:

~~~json
{
  "capabilities": {
    "general": {
      "positionEncodings": ["utf-8", "utf-16"]
    }
  }
}
~~~

Server có thể chọn một encoding được cả hai bên hỗ trợ. Cần dùng cùng encoding trong mọi thông điệp chứa position hoặc range của phiên.

### 11.1. Vì sao Unicode làm vấn đề này quan trọng?

Một ký tự nhìn thấy trên màn hình có thể chiếm nhiều code unit hoặc byte. Ví dụ, emoji hoặc ký tự ngoài BMP có độ dài khác nhau khi đếm theo UTF-8, UTF-16 và Unicode scalar value. Nếu server và client dùng cách đếm khác nhau, một text edit có thể thay nhầm vị trí.

### 11.2. Tránh tự tính offset theo byte

Không nên dùng chỉ số byte UTF-8 làm character offset nếu phiên đang dùng UTF-16. Server nên có abstraction position conversion và kiểm thử với chuỗi chứa dấu tiếng Việt, combining mark và emoji.

## 12. Cấu hình ban đầu và cấu hình thay đổi

InitializeParams có initializationOptions cho cấu hình riêng. Tuy nhiên, nhiều cấu hình có thể thay đổi trong lúc phiên hoạt động và cần cơ chế workspace/configuration hoặc didChangeConfiguration theo khả năng client.

Ví dụ options ban đầu:

~~~json
{
  "dialect": "strict",
  "enableExperimentalParser": false
}
~~~

Ví dụ cấu hình workspace có thể được yêu cầu sau:

~~~json
{
  "dsl": {
    "validation": "strict",
    "maxDiagnostics": 100
  }
}
~~~

Server nên phân biệt:

- Cấu hình bắt buộc để dựng session.
- Cấu hình có thể đọc sau khi initialized.
- Cấu hình có thể thay đổi và cần refresh analysis.
- Cấu hình riêng của từng workspace folder.
- Cấu hình riêng của từng document nếu DSL cho phép.

Khi cấu hình thay đổi, server cần xác định tài liệu hoặc cache nào bị ảnh hưởng và chạy lại phân tích tương ứng.

## 13. Khởi tạo workspace và indexing

Language server cho DSL thường cần tìm module, schema, import và dependency trong workspace. Công việc này có thể bắt đầu trong initialization hoặc sau initialized.

Một trình tự khả thi:

1. Đọc workspace folders.
2. Nạp cấu hình cấp workspace.
3. Xác định file pattern và dialect.
4. Tạo project model.
5. Quét manifest và module metadata.
6. Lập chỉ mục symbol.
7. Phân tích dependency.
8. Sẵn sàng cung cấp navigation và completion đầy đủ.

### 13.1. Indexing không nên chặn handshake quá lâu

Nếu workspace lớn, lập chỉ mục toàn bộ trước khi trả InitializeResult có thể làm client chờ lâu hoặc timeout. Server nên chỉ làm những việc cần thiết để xác định capability và cấu hình ban đầu, sau đó chạy indexing nền nếu có thể.

### 13.2. Request đến khi indexing chưa hoàn tất

Client có thể gửi didOpen hoặc request khác ngay sau initialized trong khi indexing vẫn chạy. Server cần có chính sách:

- Trả kết quả cục bộ từ document hiện tại.
- Chờ phần index cần thiết trong giới hạn thời gian.
- Trả kết quả một phần nếu tính năng cho phép.
- Gửi progress để client biết trạng thái.
- Cập nhật kết quả khi index hoàn tất.

Không nên trả kết quả sai chỉ vì index chưa sẵn sàng.

### 13.3. Nhiều workspace folder

Mỗi folder có thể có cấu hình, module root hoặc dialect riêng. Server cần quản lý project context theo URI và không dùng một global root duy nhất nếu client mở nhiều workspace.

## 14. Khởi tạo và capability của một DSL Language Server

Một server cho DSL có thể cung cấp các tính năng sau:

| Tính năng | Capability LSP tương ứng |
|---|---|
| Đồng bộ source text | textDocumentSync |
| Hoàn thành keyword, symbol | completionProvider |
| Hiển thị kiểu và documentation | hoverProvider |
| Đi tới khai báo | definitionProvider |
| Tìm nơi sử dụng | referencesProvider |
| Rename symbol | renameProvider |
| Hiển thị diagnostics | publishDiagnostics qua text synchronization/analysis |
| Quick fix | codeActionProvider |
| Cấu trúc file/module | documentSymbolProvider |
| Formatting | documentFormattingProvider |
| Semantic highlighting | semanticTokensProvider |
| Inlay hints | inlayHintProvider |

Server không nhất thiết phải hỗ trợ tất cả. Capability set nên phản ánh implementation thực tế và mức trưởng thành của từng tính năng.

### 14.1. Capability theo loại tài liệu

Một DSL có thể có nhiều loại file:

- File source chính.
- File schema.
- File manifest.
- File template.
- File generated hoặc embedded DSL.

Server cần xác định language ID và file scheme phù hợp. Capability có thể áp dụng theo selector hoặc registration options tùy tính năng và protocol version.

### 14.2. Capability phụ thuộc extension

Nếu một plugin bổ sung completion hoặc semantic tokens, server có thể thêm capability tương ứng khi plugin đã được nạp. Nếu việc nạp plugin diễn ra sau initialized, cần dynamic registration khi client hỗ trợ.

## 15. Xử lý lỗi trong quá trình khởi tạo

Khởi tạo có thể thất bại vì:

- InitializeParams không hợp lệ.
- Client dùng phiên bản hoặc cấu trúc protocol không được hỗ trợ.
- Options riêng sai kiểu hoặc giá trị.
- Cấu hình thiết yếu không thể đọc.
- Workspace URI không hợp lệ.
- Runtime dependency không có.
- Server không thể khởi tạo service bắt buộc.

Server cần trả JSON-RPC error response phù hợp thay vì im lặng đóng kết nối hoặc trả InitializeResult không nhất quán.

### 15.1. Lỗi có thể retry

Protocol có cơ chế biểu diễn lỗi khởi tạo và thông tin retry trong những trường hợp được định nghĩa. Server chỉ nên cho phép retry khi trạng thái có thể được làm sạch và việc gửi initialize lại là hợp lệ theo hợp đồng. Không nên dùng retry như cách che giấu lỗi cấu hình cố định.

### 15.2. Không để lại trạng thái nửa khởi tạo

Nếu khởi tạo thất bại sau khi đã mở file, tạo thread hoặc cấp tài nguyên, server cần giải phóng chúng. Một lần retry không nên kế thừa cache hoặc transaction context lỗi từ lần trước.

### 15.3. Diagnostics và log

Log nên ghi:

- Client name/version nếu có.
- Protocol mode hoặc version được hỗ trợ.
- Workspace URI đã được chấp nhận.
- Lý do initialize thất bại.
- Service hoặc dependency không thể khởi tạo.

Không nên ghi toàn bộ initializationOptions nếu chúng có thể chứa đường dẫn nhạy cảm, token hoặc thông tin xác thực.

## 16. Các quy tắc trạng thái trước và sau initialize

Server cần xử lý đúng các thông điệp đến sai thời điểm.

Ví dụ:

- Request hover trước khi initialize hoàn tất: chưa thể xử lý như phiên Running.
- Notification initialized trước khi có InitializeResult: sai thứ tự.
- Request initialize lặp lại trên cùng session: cần xử lý theo quy tắc protocol và kiến trúc session, không tự tạo một trạng thái chồng lấn.
- Request thông thường sau shutdown: không được xử lý như phiên đang hoạt động.

LSP có các mã lỗi và quy tắc JSON-RPC cho những trường hợp protocol không hợp lệ. Implementation nên dùng error handling theo đặc tả thay vì tự tạo response không chuẩn.

### 16.1. Một state machine trong code

Ví dụ mã giả:

~~~text
onMessage(message):
    switch session.state:
        case Starting:
            require message.method == "initialize"
            handleInitialize(message)

        case AwaitingInitialized:
            require message.method == "initialized"
            session.state = Running

        case Running:
            dispatchNegotiatedMessage(message)

        case ShuttingDown:
            handleShutdownStateMessage(message)

        case Exiting:
            rejectOrIgnoreAccordingToProtocol(message)
~~~

Đây là phác thảo. Server thực tế cần phân biệt request, response và notification, cũng như các thông điệp đặc biệt được protocol cho phép ở từng trạng thái.

## 17. Ví dụ initialize handshake hoàn chỉnh

### 17.1. Client gửi initialize

~~~json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "processId": 12345,
    "clientInfo": {
      "name": "Example Editor",
      "version": "8.2"
    },
    "rootUri": "file:///workspace/inventory",
    "capabilities": {
      "textDocument": {
        "completion": {
          "completionItem": {
            "snippetSupport": true
          }
        },
        "hover": {
          "contentFormat": ["markdown", "plaintext"]
        }
      },
      "workspace": {
        "workspaceFolders": true
      }
    },
    "initializationOptions": {
      "dialect": "inventory-v2"
    },
    "trace": "off"
  }
}
~~~

### 17.2. Server trả InitializeResult

~~~json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "capabilities": {
      "textDocumentSync": {
        "openClose": true,
        "change": 2
      },
      "completionProvider": {
        "triggerCharacters": [".", ":"]
      },
      "hoverProvider": true,
      "definitionProvider": true,
      "documentSymbolProvider": true
    },
    "serverInfo": {
      "name": "Inventory DSL Language Server",
      "version": "1.2.0"
    }
  }
}
~~~

### 17.3. Client gửi initialized

~~~json
{
  "jsonrpc": "2.0",
  "method": "initialized",
  "params": {}
}
~~~

Sau đó client có thể mở tài liệu:

~~~json
{
  "jsonrpc": "2.0",
  "method": "textDocument/didOpen",
  "params": {
    "textDocument": {
      "uri": "file:///workspace/inventory/rules.dsl",
      "languageId": "inventory-dsl",
      "version": 1,
      "text": "rule stock-check { ... }"
    }
  }
}
~~~

Server dùng document text cùng workspace model đã khởi tạo để phân tích và có thể gửi publishDiagnostics nếu capability và trạng thái cho phép.

## 18. Ví dụ xử lý initialize trong server

Mã giả sau minh họa trách nhiệm của handler:

~~~text
handleInitialize(params):
    assert session.state == Starting
    session.state = Initializing

    clientCaps = parseClientCapabilities(params.capabilities)
    workspace = resolveWorkspace(
        params.workspaceFolders,
        params.rootUri,
        params.rootPath
    )
    options = validateInitializationOptions(
        params.initializationOptions
    )
    encoding = negotiatePositionEncoding(clientCaps)

    services = createRequiredServices(workspace, options)
    serverCaps = computeServerCapabilities(
        clientCaps,
        services,
        encoding
    )

    session.clientCapabilities = clientCaps
    session.workspace = workspace
    session.services = services
    session.positionEncoding = encoding
    session.state = AwaitingInitialized

    return InitializeResult(
        capabilities = serverCaps,
        serverInfo = currentServerInfo()
    )
~~~

Handler không nên chỉ trả một object capability tĩnh mà không kiểm tra môi trường. Nếu parser, indexer hoặc provider chưa được tạo, server có thể công bố capability không hoạt động.

### 18.1. Phân chia trách nhiệm trong implementation

Có thể tách các phần:

- Protocol decoder xác thực JSON-RPC envelope.
- Initialize handler đọc params.
- Capability negotiator tính giao của khả năng client/server.
- Workspace manager dựng project context.
- Configuration loader xác thực options.
- Service container tạo các service cần thiết.
- Session manager lưu trạng thái và metadata.

Tách trách nhiệm giúp kiểm thử từng phần và tránh một handler khởi tạo quá nhiều logic không liên quan.

## 19. Capability negotiation như một phép giao

Một cách suy nghĩ hữu ích là capability được sử dụng trong phiên phải phù hợp đồng thời với:

1. Server có implementation.
2. Client có khả năng tiếp nhận.
3. Protocol version cho phép.
4. Cấu hình và workspace hiện tại bật tính năng.

Có thể mô tả:

\[
C_{\text{session}} =
C_{\text{server}}
\cap C_{\text{client}}
\cap C_{\text{protocol}}
\cap C_{\text{configuration}}
\]

Đây là mô hình khái niệm, không phải phép toán literal trong protocol. Một số capability được công bố theo cấu trúc riêng, một số có thể được đăng ký động. Tuy nhiên, mô hình này nhấn mạnh rằng server không nên công bố tính năng chỉ vì code handler tồn tại.

Ví dụ, server có semantic tokens provider nhưng client không hỗ trợ loại token hoặc registration mode cần thiết. Server phải chọn cấu hình tương thích hoặc không bật provider trong session.

## 20. Multi-root workspace và session context

Với client hỗ trợ nhiều workspace folder, server cần thiết kế project context sao cho request có thể được định tuyến đúng.

Ví dụ:

~~~text
Session
├── WorkspaceFolder: /workspace/app
│   ├── dialect: app-dsl
│   └── project index
└── WorkspaceFolder: /workspace/shared
    ├── dialect: shared-schema
    └── project index
~~~

Một tài liệu mở có URI thuộc folder nào thì server cần xác định project context tương ứng. Nếu file nằm ngoài mọi folder, server có thể xử lý theo chế độ standalone hoặc chính sách đã định.

### 20.1. Trùng file hoặc module

Hai workspace folder có thể cùng chứa module name hoặc file name giống nhau. Server cần định danh theo URI và project context, không chỉ dùng basename.

### 20.2. Workspace folder thay đổi

Khi client thêm hoặc xóa folder, server cần cập nhật index, module resolution và diagnostics. Những tài liệu đang mở có thể cần được resolve lại nếu dependency graph thay đổi.

## 21. Security và trust boundary khi khởi tạo

InitializeParams đến từ client và phải được xem là input cần xác thực. Các trường có thể chứa URI, đường dẫn, options hoặc metadata không đáng tin cậy.

Các nguyên tắc:

- Validate URI scheme và path.
- Không thực thi command chỉ vì options yêu cầu.
- Không tải plugin tùy ý từ đường dẫn client gửi.
- Giới hạn kích thước và độ sâu dữ liệu options.
- Không ghi secret hoặc token vào log.
- Áp dụng quyền filesystem và network của process.
- Kiểm tra symlink và path traversal nếu server đọc file trong workspace.
- Không coi workspace root là ranh giới bảo mật tuyệt đối.

Nếu server hỗ trợ extension hoặc command execution, capability đó cần được kiểm soát riêng. Khởi tạo phiên không nên trở thành con đường để client gửi cấu hình làm server thực thi mã tùy ý.

## 22. Hiệu năng và khả năng phục hồi khi khởi tạo

Khởi tạo cần đủ nhanh để editor không bị treo, nhưng vẫn phải thiết lập trạng thái nhất quán.

### 22.1. Phân biệt critical path và background work

Critical path thường gồm:

- Parse và validate params.
- Chọn protocol behavior.
- Nạp cấu hình bắt buộc.
- Tạo các service tối thiểu.
- Tính server capabilities.

Background work có thể gồm:

- Quét toàn bộ workspace.
- Lập chỉ mục symbol.
- Tính dependency graph lớn.
- Tải metadata không bắt buộc.
- Xây cache.

### 22.2. Progress

Nếu client hỗ trợ work-done progress, server có thể báo tiến độ indexing hoặc setup. Progress nên phản ánh công việc thực tế, không phát thông báo giả chỉ để giữ giao diện hoạt động.

### 22.3. Cache

Server có thể tái sử dụng cache giữa các phiên nếu cache được gắn với workspace identity, cấu hình, phiên bản compiler và dependency. Không nên dùng cache cũ khi dialect hoặc project configuration đã thay đổi.

### 22.4. Phục hồi khi service phụ trợ lỗi

Nếu indexer không khởi động được nhưng parser và diagnostics cơ bản vẫn hoạt động, server có thể chạy ở chế độ giảm tính năng nếu hợp đồng cho phép. Khi đó, InitializeResult phải phản ánh đúng capability thực tế. Nếu service bắt buộc không thể khởi tạo, server nên trả lỗi initialize.

## 23. Kiểm thử quá trình khởi tạo

Kiểm thử initialization tập trung vào handshake, trạng thái và capability negotiation.

### 23.1. Kiểm thử params hợp lệ

- Client cung cấp một workspace folder.
- Client cung cấp nhiều workspace folder.
- Client không cung cấp workspace root.
- processId là null.
- clientInfo hoặc locale bị thiếu.
- initializationOptions rỗng hoặc chứa giá trị hợp lệ.

### 23.2. Kiểm thử capability

- Client hỗ trợ snippet và server công bố completion tương ứng.
- Client chỉ hỗ trợ plaintext và hover không gửi Markdown không được quảng bá.
- Client không hỗ trợ dynamic registration.
- Server không công bố capability khi provider chưa sẵn sàng.
- Position encoding được thương lượng nhất quán.

### 23.3. Kiểm thử lifecycle

- initialize là request đầu tiên.
- initialized chỉ được xử lý sau InitializeResult.
- Request thông thường trước khi Running được xử lý theo protocol error policy.
- shutdown và exit đi đúng thứ tự.
- Lỗi initialize giải phóng tài nguyên.
- Retry chỉ xảy ra khi được cho phép.

### 23.4. Kiểm thử workspace

- URI có dấu cách và Unicode.
- URI trên Windows và Unix.
- Nhiều root có module trùng tên.
- Workspace folder được thêm hoặc xóa.
- File nằm ngoài workspace.

### 23.5. Kiểm thử tích hợp với client

Một test tích hợp nên khởi chạy server qua transport thật, gửi initialize request, kiểm tra response, gửi initialized và gọi ít nhất một tính năng đã công bố. Test này xác nhận handshake không chỉ đúng ở cấp object mà còn hoạt động qua framing và JSON-RPC.

## 24. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Xử lý request nghiệp vụ trước initialized | Session ở trạng thái chưa sẵn sàng | Dùng state machine và kiểm tra lifecycle |
| Coi rootUri luôn có giá trị | Lỗi khi client không mở workspace | Hỗ trợ null và workspaceFolders |
| Chỉ hỗ trợ một workspace root | Phân tích sai multi-root project | Quản lý context theo workspace folder |
| Công bố mọi server capability | Client gọi provider chưa triển khai | Tính capability từ implementation và client support |
| Bỏ qua client capabilities | Response không tương thích với editor | Thương lượng capability trước khi trả kết quả |
| Dùng initializationOptions không validate | Cấu hình sai hoặc dữ liệu nguy hiểm đi vào runtime | Validate schema và giới hạn giá trị |
| Chạy indexing lớn trước response | Editor chờ initialize quá lâu | Tách critical setup và background indexing |
| Dùng sai position encoding | Diagnostics và edit lệch ký tự Unicode | Thương lượng và dùng một encoding thống nhất |
| Nạp plugin từ path không tin cậy | Có thể thực thi mã ngoài dự kiến | Trust policy và allowlist |
| Không cleanup khi initialize lỗi | Rò rỉ thread, file handle hoặc cache | Dùng cleanup path cho trạng thái thất bại |
| Ghi toàn bộ options vào log | Có thể lộ thông tin nhạy cảm | Redact và chỉ log metadata cần thiết |
| Coi initialized là request | Server chờ response không tồn tại | Xử lý đúng đây là notification |

## 25. Quy trình thiết kế initialization cho DSL Language Server

Khi triển khai khởi tạo phiên, có thể thực hiện theo các bước:

1. **Chọn phiên bản LSP:** xác định protocol version và tập tính năng cần hỗ trợ.
2. **Định nghĩa session lifecycle:** Starting, Initializing, Running, ShuttingDown và các trạng thái cần thiết.
3. **Đọc InitializeParams:** xác thực process metadata, workspace, locale, trace và options.
4. **Thiết kế workspace model:** hỗ trợ workspaceFolders, fallback cho client cũ và chế độ không có workspace.
5. **Xây capability negotiator:** đối chiếu client capabilities với provider thực tế.
6. **Chọn position encoding:** áp dụng mặc định hoặc thương lượng theo protocol.
7. **Tạo service thiết yếu:** parser, project model, configuration và các provider cần cho session.
8. **Tạo InitializeResult:** chỉ công bố capability đã sẵn sàng và tương thích.
9. **Xử lý initialized:** bắt đầu công việc nền và dynamic registration được phép.
10. **Quản lý cấu hình thay đổi:** xác định phần nào cần refresh sau handshake.
11. **Thiết kế lỗi và cleanup:** phân loại lỗi, retry policy và giải phóng tài nguyên.
12. **Kiểm thử transport và lifecycle:** kiểm tra request/notification thực tế, workspace và Unicode positions.

Một tài liệu initialization nên mô tả schema options riêng, capability được hỗ trợ, phiên bản protocol, workspace behavior, encoding và trạng thái server sau mỗi thông điệp.

## 26. Tiêu chí của một quá trình khởi tạo phiên tốt

Một quá trình khởi tạo tốt hoàn tất handshake nhanh, xác định rõ môi trường workspace, thương lượng đúng capability và đưa server vào trạng thái sẵn sàng có thể dự đoán. Khi có lỗi, nó phải trả thông tin đủ rõ và giải phóng tài nguyên đã tạo.

Các câu hỏi quan trọng:

- Initialize request có được xử lý trước mọi request nghiệp vụ không?
- Server hiểu đúng phiên bản và schema InitializeParams nào?
- WorkspaceFolders, rootUri và trường hợp không có workspace được xử lý ra sao?
- Client capabilities được dùng để quyết định server capabilities thế nào?
- InitializeResult chỉ công bố tính năng thực sự hoạt động không?
- Notification initialized có được xử lý đúng là notification không?
- Dynamic registration chỉ dùng khi client hỗ trợ không?
- Position encoding có nhất quán với mọi range và text edit không?
- Indexing có được tách khỏi critical path khi cần không?
- Lỗi khởi tạo có cleanup và retry policy rõ ràng không?

Khởi tạo phiên thiết lập hợp đồng ban đầu giữa Language Client và Language Server. Khi InitializeParams, workspace context, capability negotiation, InitializeResult và notification initialized được xử lý đúng, server có thể cung cấp các tính năng DSL phù hợp với client và môi trường dự án, đồng thời duy trì một vòng đời phiên rõ ràng và có thể kiểm soát.
