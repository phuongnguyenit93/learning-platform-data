# Hiển thị hover

Trong một trình soạn thảo DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), **hiển thị hover** (*hover display* hoặc *hover information*) là tính năng hiện một bảng thông tin ngắn khi người dùng đưa con trỏ chuột lên một vị trí trong mã nguồn. Thông tin thường giải thích symbol đang được trỏ tới, kiểu dữ liệu, chữ ký hàm, tài liệu hướng dẫn, giá trị hoặc cảnh báo liên quan.

Ví dụ, người dùng viết:

```text
service "catalog" {
    replicas = 3
    region = "asia-southeast1"
}
```

Khi di chuyển con trỏ lên `replicas`, editor có thể hiển thị:

```text
replicas: Integer
Số lượng instance của dịch vụ.
Giá trị hợp lệ: số nguyên dương.
```

Khi trỏ vào `region`, hover có thể cho biết kiểu, mô tả trường, các giá trị được hỗ trợ hoặc liên kết đến tài liệu cấu hình.

Hover giúp người dùng hiểu mã ngay tại vị trí đang làm việc mà không phải chuyển sang tài liệu khác hoặc tìm định nghĩa thủ công. Nó đặc biệt hữu ích với DSL có nhiều thuộc tính, kiểu miền, hàm tích hợp và quy tắc cấu hình.

## 1. Hover trong trải nghiệm editor

Hover là một dạng trợ giúp theo ngữ cảnh (*contextual assistance*). Editor xác định vị trí con trỏ, hỏi language service thông tin phù hợp với vị trí đó, rồi hiển thị kết quả trong một popup hoặc tooltip.

Thông tin có thể gồm:

- Tên và loại symbol đang được trỏ tới.
- Kiểu dữ liệu của biến, thuộc tính hoặc biểu thức.
- Chữ ký hàm, tham số và kiểu trả về.
- Mô tả tài liệu (*documentation*) của symbol.
- Giá trị hoặc biểu thức đã được suy luận.
- Thông tin về enum, constant hoặc literal.
- Cảnh báo, deprecation hoặc trạng thái không còn được khuyến nghị.
- Tài liệu ngắn về quy tắc DSL hoặc cú pháp hiện tại.

Hover thường chỉ hiển thị thông tin để đọc. Nó khác với completion, nơi editor đề xuất những nội dung có thể chèn vào mã; khác với go to definition, nơi editor điều hướng đến vị trí khai báo; và khác với diagnostic, nơi editor báo một vấn đề cần chú ý.

### 1.1. Ví dụ về các loại hover

Với DSL khai báo dịch vụ:

```text
service "catalog" {
    replicas = 3
    image = "catalog:v2"
    deploy(region = "asia-southeast1")
}
```

Hover có thể cung cấp nội dung khác nhau tùy vị trí:

| Vị trí | Thông tin có thể hiển thị |
|---|---|
| `replicas` | Kiểu `Integer`, mô tả thuộc tính, giới hạn giá trị |
| `3` | Kiểu literal, giá trị suy luận, đơn vị nếu có |
| `image` | Kiểu `String`, mô tả thuộc tính và ví dụ |
| `deploy` | Chữ ký hàm, tham số, kiểu trả về |
| `region` trong lời gọi | Tên tham số, kiểu, giá trị được chấp nhận |
| Tên enum | Mô tả thành viên và trạng thái deprecated nếu có |

### 1.2. Hover theo vị trí, không chỉ theo từ

Một chuỗi ký tự giống nhau có thể đại diện cho các symbol khác nhau tùy phạm vi.

```text
namespace billing {
    model Invoice { }
}

namespace inventory {
    model Invoice { }
}
```

Nếu hover lên `Invoice` trong namespace `billing`, editor phải hiển thị tài liệu của `billing.Invoice`; trong namespace `inventory`, nó phải hiển thị tài liệu của `inventory.Invoice`.

Vì vậy, hover chất lượng cao thường dựa trên kết quả phân giải tên và symbol identity, không chỉ tìm từ gần con trỏ rồi tra một bảng tên đơn giản.

## 2. Luồng xử lý hover

Một tính năng hover thường phối hợp editor client, language server hoặc language service, parser, semantic analyzer và hệ thống tài liệu.

```text
Người dùng đặt con trỏ lên mã
            |
            v
Editor xác định document và position
            |
            v
Gửi yêu cầu hover đến language service
            |
            v
Tìm token / AST node tại position
            |
            v
Phân giải symbol và kiểu dữ liệu
            |
            v
Thu thập documentation và metadata
            |
            v
Tạo nội dung hover có cấu trúc
            |
            v
Editor hiển thị popup
```

Tùy kiến trúc, một số bước có thể đã được tính trước. Ví dụ, AST, symbol table và type information có thể được lưu trong workspace snapshot; khi nhận yêu cầu hover, language service chỉ cần tra cứu dữ liệu đã có.

### 2.1. Xác định document

Editor cần gửi định danh tài liệu đang mở, thường là URI hoặc một document handle. URI giúp language service phân biệt những tệp có cùng tên nhưng nằm ở thư mục khác nhau.

### 2.2. Xác định position

Vị trí hover thường được gửi dưới dạng dòng và cột hoặc offset. Language service cần quy đổi chính xác về vị trí trong nội dung tài liệu, có xét quy ước encoding mà giao thức sử dụng.

### 2.3. Tìm node hoặc symbol

Language service tìm token, AST node hoặc semantic token chứa vị trí được yêu cầu. Nếu con trỏ nằm trên identifier, nó có thể tra symbol reference tương ứng. Nếu con trỏ nằm trên biểu thức, nó có thể lấy kiểu suy luận của biểu thức đó.

### 2.4. Tạo nội dung và trả kết quả

Sau khi có thông tin, service tạo nội dung hover. Kết quả có thể gồm nội dung định dạng Markdown hoặc plaintext, cùng một source range tùy giao thức.

## 3. Hover và Language Server Protocol

Một editor có thể tích hợp trực tiếp với compiler hoặc language service riêng. Một cách phổ biến để hỗ trợ nhiều editor là dùng **Language Server Protocol (LSP)**. LSP định nghĩa giao tiếp giữa editor client và language server cho các tính năng như hover, completion, diagnostics và go to definition.

Trong LSP, client gửi yêu cầu `textDocument/hover` với tài liệu và vị trí con trỏ. Server trả về một `Hover` chứa nội dung và có thể kèm range.

Ví dụ JSON minh họa yêu cầu:

```json
{
  "jsonrpc": "2.0",
  "id": 12,
  "method": "textDocument/hover",
  "params": {
    "textDocument": {
      "uri": "file:///workspace/service.dsl"
    },
    "position": {
      "line": 1,
      "character": 5
    }
  }
}
```

Server có thể trả về nội dung dạng Markdown:

```json
{
  "jsonrpc": "2.0",
  "id": 12,
  "result": {
    "contents": {
      "kind": "markdown",
      "value": "**replicas**: `Integer`\n\nSố lượng instance của dịch vụ."
    }
  }
}
```

Đây là ví dụ rút gọn để minh họa cấu trúc. Tên trường, quy tắc position encoding và chi tiết tương thích cần tuân theo phiên bản LSP mà client/server hỗ trợ.

### 3.1. `textDocument/hover`

Đây là request client gửi khi cần thông tin hover. Server nhận document URI và position, sau đó trả về hover hoặc `null` nếu không có thông tin phù hợp.

### 3.2. Nội dung hover

LSP cho phép nội dung có định dạng, phổ biến là Markdown hoặc plaintext. Markdown giúp trình bày tên symbol, code block, danh sách tham số và liên kết tài liệu.

### 3.3. Range

Kết quả hover có thể chứa range mà nội dung áp dụng. Range giúp client biết vùng văn bản liên quan, nhưng việc hiển thị popup cụ thể do editor quyết định.

### 3.4. Khả năng của client

Không phải editor nào cũng hiển thị mọi định dạng hoặc tính năng phụ giống nhau. Language server nên trả nội dung theo khả năng được thương lượng hoặc quy ước mà client hỗ trợ.

## 4. Xác định đối tượng được hover

Việc tìm đối tượng tại vị trí con trỏ là bước nền tảng. Có thể có nhiều trường hợp:

- Con trỏ nằm trên identifier.
- Con trỏ nằm trên tên hàm hoặc tên kiểu.
- Con trỏ nằm trên tên tham số.
- Con trỏ nằm trên literal.
- Con trỏ nằm trên toán tử.
- Con trỏ nằm trên keyword.
- Con trỏ nằm trong comment hoặc string literal.
- Con trỏ nằm trên khoảng trắng hoặc vị trí không có node.

### 4.1. Hover trên identifier

Ví dụ:

```text
customerId = customer.id
```

Hover trên `customerId` có thể cho biết biến có kiểu gì và được khai báo ở đâu. Hover trên `customer` có thể hiển thị kiểu của biến; hover trên `id` có thể hiển thị kiểu và tài liệu của thuộc tính.

### 4.2. Hover trên hàm

Ví dụ:

```text
result = calculateTotal(items, taxRate)
```

Hover trên `calculateTotal` có thể hiển thị:

```text
calculateTotal(items: List<Item>, taxRate: Decimal): Money

Tính tổng giá trị các mặt hàng sau khi áp dụng thuế.
```

### 4.3. Hover trên tham số

Nếu con trỏ nằm trên `taxRate` trong lời gọi có tên tham số, editor có thể hiển thị mô tả tham số và kiểu mong đợi.

### 4.4. Hover trên literal

Với:

```text
timeout = 30s
```

Hover trên `30s` có thể hiển thị kiểu `Duration`, giá trị chuẩn hóa tương đương 30 giây hoặc quy tắc đơn vị của DSL.

### 4.5. Hover trên keyword

Một số editor cung cấp mô tả cú pháp cho keyword như `workflow`, `retry`, `transaction` hoặc `match`. Nội dung có thể lấy từ grammar documentation hoặc metadata của language server.

### 4.6. Hover trên comment và string

Nếu vị trí nằm trong comment hoặc string literal, server có thể trả về thông tin về escape sequence, interpolation hoặc quy tắc định dạng. Nếu không có nội dung hữu ích, trả `null` là hợp lý.

## 5. Hover dựa trên semantic analysis

Hover hữu ích nhất khi phản ánh ý nghĩa thực tế của mã. Vì vậy, nó thường sử dụng kết quả semantic analysis.

### 5.1. Symbol resolution

Với tên `Customer`, analyzer cần biết nó trỏ đến khai báo nào trong namespace, module và import hiện tại. Hover có thể sử dụng symbol ID để lấy tài liệu và metadata đúng.

### 5.2. Type information

Type checker có thể cung cấp:

- Kiểu khai báo của biến.
- Kiểu suy luận của biểu thức.
- Kiểu tham số và kiểu trả về.
- Kiểu generic sau khi thay thế type arguments.
- Kiểu nullable hoặc optional.
- Kiểu literal hoặc constant value.

Ví dụ:

```text
let subtotal = 120.50
let tax = subtotal * 0.1
let total = subtotal + tax
```

Hover trên `total` có thể hiển thị `Decimal` nếu DSL suy luận kiểu thập phân cho các biểu thức này.

### 5.3. Generic type

Với:

```text
repository: Repository<Customer>
```

Hover nên hiển thị kiểu đã được áp dụng `Customer`, không chỉ dạng tổng quát `Repository<T>` nếu type checker đã có thông tin cụ thể.

### 5.4. Overload resolution

Một tên hàm có thể có nhiều overload. Hover tại một lời gọi cụ thể nên ưu tiên chữ ký đã được resolver chọn. Nếu chưa đủ thông tin để phân biệt, server có thể hiển thị các overload phù hợp hoặc thông báo chưa thể xác định.

### 5.5. Type inference chưa hoàn tất

Trong lúc người dùng đang gõ, biểu thức có thể chưa hoàn chỉnh. Hover có thể hiển thị kiểu tạm thời, thông tin một phần hoặc không trả kết quả. Không nên khẳng định một kiểu cuối cùng nếu analyzer chưa đủ dữ liệu.

## 6. Nội dung hover cho từng loại symbol

Một hover provider có thể dùng template khác nhau tùy loại symbol.

| Loại symbol | Nội dung phù hợp |
|---|---|
| Variable | Tên, kiểu, giá trị suy luận, vị trí khai báo |
| Field/property | Kiểu, mô tả, default, constraint |
| Function | Chữ ký, tham số, kiểu trả về, documentation |
| Model/type | Tên đầy đủ, fields, generic parameters, mô tả |
| Enum member | Enum cha, giá trị, ý nghĩa |
| Constant | Kiểu và giá trị hằng |
| Keyword | Ý nghĩa cú pháp và ví dụ |
| Operator | Kiểu toán hạng, kết quả và semantics |
| Resource | Loại tài nguyên, thuộc tính và trạng thái |
| Deprecated symbol | Lý do deprecated, phiên bản và thay thế đề xuất |

### 6.1. Hover cho thuộc tính DSL

Ví dụ:

```text
database "orders" {
    replicas = 2
}
```

Hover trên `replicas` có thể hiển thị:

```text
replicas: Integer

Số bản sao của database service.

Default: 1
Minimum: 1
Maximum: 10
```

Thông tin này có thể được định nghĩa trong schema DSL, annotation hoặc metadata của compiler.

### 6.2. Hover cho hàm tích hợp

Một DSL có thể cung cấp hàm miền như:

```text
publish(event: DomainEvent): Result
```

Hover có thể giải thích hàm gửi event đến broker, nêu điều kiện lỗi và link đến tài liệu API.

### 6.3. Hover cho enum

```text
status = OrderStatus.PAID
```

Hover trên `PAID` có thể hiển thị:

```text
OrderStatus.PAID

Đơn hàng đã được thanh toán thành công.
```

### 6.4. Hover cho deprecated symbol

Nếu một thuộc tính đã deprecated:

```text
legacyRegion = "asia"
```

Hover có thể hiển thị cảnh báo và gợi ý:

```text
legacyRegion: String

Deprecated since version 2.4.
Use `region` instead.
```

Nội dung này bổ sung cho diagnostic warning, không thay thế diagnostic nếu công cụ cần báo vấn đề ở cấp file hoặc CI.

## 7. Kết hợp documentation với type information

Hover thường có hai nguồn nội dung:

1. Thông tin do analyzer suy ra từ chương trình hiện tại.
2. Tài liệu do người thiết kế DSL hoặc tác giả thư viện cung cấp.

Ví dụ, analyzer biết `timeout` có kiểu `Duration`, còn documentation giải thích đơn vị mặc định và giới hạn.

Một cấu trúc hover có thể được xây dựng như sau:

```text
HoverInfo {
    signature: "timeout: Duration"
    documentation: "Thời gian tối đa chờ phản hồi."
    details: [
        "Default: 30s",
        "Minimum: 1s"
    ]
    links: [
        "Configuration reference"
    ]
}
```

### 7.1. Documentation từ source comment

DSL có thể hỗ trợ comment tài liệu:

```text
/// Số lượng instance của dịch vụ.
/// Phải là số nguyên dương.
property replicas: Integer = 1
```

Compiler có thể gắn documentation comment với symbol `replicas`, sau đó cung cấp cho hover provider.

### 7.2. Documentation từ schema metadata

Một số DSL mô tả model bằng metadata:

```text
@description("Vùng triển khai của dịch vụ")
@example("asia-southeast1")
region: String
```

Hover provider có thể đọc các annotation này và trình bày nội dung theo template.

### 7.3. Documentation từ thư viện

Nếu symbol đến từ dependency, documentation có thể được lấy từ package metadata, generated API docs hoặc symbol index của thư viện. Cần xác định version dependency để tránh hiển thị tài liệu của phiên bản khác với symbol đang được sử dụng.

### 7.4. Ưu tiên và hợp nhất nội dung

Một symbol có thể có tài liệu từ nhiều nguồn: comment nguồn, schema registry, package docs và metadata sinh tự động. Công cụ cần quy tắc ưu tiên, tránh hiển thị trùng lặp hoặc nội dung mâu thuẫn.

## 8. Định dạng nội dung hover

Hover nên ngắn gọn, có cấu trúc và dễ quét mắt. Markdown thường hữu ích vì hỗ trợ tiêu đề, code, danh sách và liên kết.

Ví dụ:

```markdown
**calculateTotal**(`items: List<Item>`): `Money`

Tính tổng giá trị của danh sách mặt hàng.

**Parameters**
- `items`: Các mặt hàng cần tính.

**Returns**
- `Money`: Tổng giá trị trước khi ghi nhận hóa đơn.
```

### 8.1. Hiển thị chữ ký trước

Với function hoặc method, chữ ký thường là thông tin người dùng cần nhanh nhất. Documentation dài có thể đặt phía dưới.

### 8.2. Dùng code formatting cho tên kỹ thuật

Tên symbol, kiểu, tham số và literal thường dễ đọc hơn khi dùng inline code hoặc code block.

### 8.3. Tránh nội dung quá dài

Hover không phải trang tài liệu đầy đủ. Nếu documentation dài, nên hiển thị phần tóm tắt và liên kết mở tài liệu chi tiết. Nội dung quá dài có thể che mã và khiến người dùng khó điều hướng.

### 8.4. Liên kết tài liệu

Có thể cung cấp link đến API reference hoặc hướng dẫn. Link cần trỏ đến đúng version của thư viện hoặc DSL để người dùng không đọc nhầm tài liệu mới hơn/cũ hơn.

### 8.5. Nội dung có thể copy

Một số editor cho phép chọn và copy nội dung hover. Nên giữ định dạng văn bản rõ ràng và không dựa hoàn toàn vào màu sắc hoặc biểu tượng để truyền đạt ý nghĩa.

## 9. Hover cho diagnostics và cảnh báo

Hover có thể bổ sung thông tin về diagnostic tại vị trí đang trỏ tới.

Ví dụ:

```text
replicas = 0
```

Nếu quy tắc yêu cầu số nguyên dương, hover có thể giải thích:

```text
replicas: Integer

Số lượng instance phải lớn hơn 0.
Current value: 0
```

Tuy nhiên, diagnostic vẫn là cơ chế riêng để báo lỗi. Hover chỉ xuất hiện khi người dùng chủ động trỏ vào vị trí; một lỗi cần được hiển thị liên tục trong Problems panel hoặc dưới dạng underline thì không nên chỉ dựa vào hover.

### 9.1. Diagnostic code

Nếu có mã lỗi, hover có thể hiển thị mã cùng liên kết giải thích. Điều này giúp người dùng tra cứu chi tiết mà không làm thông điệp chính quá dài.

### 9.2. Quick fix

Hover có thể giải thích cách sửa, nhưng thao tác áp dụng quick fix thường thuộc code action. Không nên làm cho việc hover tự động sửa nội dung mà không có hành động rõ ràng từ người dùng.

### 9.3. Lỗi cú pháp

Nếu parser chưa tạo được node đáng tin cậy tại vị trí đó, service có thể hiển thị thông tin grammar hoặc expected token. Nếu không có thông tin chính xác, trả về không có hover tốt hơn là tạo một mô tả đoán.

## 10. Thiết kế hover provider

Trong kiến trúc language service, hover provider là thành phần nhận document và position rồi trả nội dung hover.

Một interface khái niệm:

```text
HoverProvider {
    provideHover(document, position, context): HoverResult?
}
```

Provider có thể phối hợp nhiều thành phần:

- Syntax service tìm node.
- Symbol resolver xác định symbol.
- Type service cung cấp kiểu.
- Documentation provider lấy mô tả.
- Diagnostic service lấy cảnh báo liên quan.
- Renderer định dạng nội dung theo khả năng client.

### 10.1. Tách provider theo loại thông tin

Có thể có provider cho:

- Symbol hover.
- Type hover.
- Documentation hover.
- Literal/value hover.
- Keyword hover.
- Diagnostic hover.

Một orchestrator kết hợp kết quả theo thứ tự ưu tiên. Ví dụ, hover trên identifier đã resolve có thể ưu tiên signature và documentation của symbol; hover trên literal có thể ưu tiên kiểu và giá trị.

### 10.2. Quy tắc ưu tiên

Nếu nhiều provider cùng trả kết quả, cần quy tắc xác định nội dung nào được hiển thị. Có thể hợp nhất các phần bổ sung hoặc chọn provider có độ tin cậy cao nhất.

Không nên ghép nhiều đoạn giống nhau khiến hover lặp signature hoặc documentation.

### 10.3. Không có kết quả

Nếu con trỏ nằm trên khoảng trắng, comment không có metadata hoặc một token không có thông tin hữu ích, provider có thể trả `null`. Popup rỗng hoặc thông điệp chung chung thường làm trải nghiệm kém hơn.

## 11. Hiệu năng và độ trễ

Hover là thao tác tương tác thường xuyên. Người dùng có thể di chuyển chuột liên tục qua nhiều token, nên service cần trả kết quả nhanh và tránh công việc nặng không cần thiết.

### 11.1. Dùng semantic result đã có

Nếu AST, symbol index và type information đã được tính cho document version hiện tại, hover nên tra cứu những kết quả này thay vì chạy lại toàn bộ compiler pipeline.

### 11.2. Debounce và delay ở client

Editor thường chờ một khoảng ngắn sau khi con trỏ dừng trước khi gửi yêu cầu hover. Cơ chế này tránh gửi request cho mọi pixel di chuyển. Thời gian chờ là quyết định UX của client, không phải quy tắc của DSL.

### 11.3. Hủy request cũ

Nếu người dùng di chuyển con trỏ sang vị trí khác, request cũ có thể không còn cần thiết. Client/server nên hỗ trợ cancellation nếu giao thức cho phép và không tiếp tục tính toán tốn kém cho kết quả đã lỗi thời.

### 11.4. Không chặn giao diện

Language service có thể chạy bất đồng bộ. Editor không nên đóng băng khi hover provider truy vấn symbol index hoặc tài liệu lớn.

### 11.5. Giới hạn công việc

Hover nên có giới hạn thời gian và kích thước nội dung. Nếu tài liệu ngoài hoặc truy vấn từ xa không phản hồi, có thể trả thông tin cục bộ trước hoặc bỏ phần không thiết yếu.

## 12. Cache hover

Hover result có thể được cache để giảm độ trễ, nhưng cache phải gắn với đúng document và semantic state.

### 12.1. Cache key

Một cache key có thể dựa trên:

- Document URI.
- Document version hoặc content hash.
- Position hoặc symbol identity.
- Workspace snapshot ID.
- Dependency version nếu documentation phụ thuộc dependency.
- Locale hoặc định dạng nếu nội dung được dịch.

Nếu chỉ cache theo tên symbol, cùng một tên trong hai namespace có thể trả nhầm tài liệu.

### 12.2. Invalidation

Cache cần được làm mới khi:

- Tài liệu thay đổi.
- Symbol được rename hoặc đổi kiểu.
- Dependency version thay đổi.
- Documentation comment thay đổi.
- Workspace symbol index được cập nhật.
- Cấu hình hoặc locale ảnh hưởng nội dung thay đổi.

### 12.3. Cache theo symbol identity

Nếu nhiều vị trí cùng tham chiếu một symbol, phần documentation và signature có thể được cache theo symbol identity. Phần type inference hoặc context-specific detail có thể cần cache riêng theo vị trí và document snapshot.

### 12.4. Tránh dữ liệu lỗi thời

Một hover có thể được tính khi người dùng đang sửa file. Nếu kết quả trả về sau khi document đã đổi version, editor nên bỏ qua hoặc service cần xác nhận version trước khi trả kết quả.

## 13. Hover trong workspace nhiều tệp

DSL thường cho phép import symbol từ file khác. Hover cần hoạt động xuyên file.

Ví dụ:

```text
# models/customer.dsl
namespace crm {
    /// Hồ sơ khách hàng trong hệ thống.
    public model Customer {
        id: String
        name: String
    }
}
```

```text
# api/registration.dsl
import crm.Customer

function register(customer: Customer): Result
```

Hover trên `Customer` trong `registration.dsl` có thể hiển thị documentation từ khai báo ở `customer.dsl`, cùng qualified name và kiểu.

### 13.1. Symbol index

Language service cần có cách tra symbol giữa các tệp. Symbol index có thể lưu qualified name, symbol ID, declaration location, type, visibility và documentation.

### 13.2. Dependency chưa resolve

Nếu module chưa được tải hoặc dependency chưa resolve, hover có thể hiển thị tên và thông tin một phần, hoặc cho biết symbol chưa được phân giải. Không nên trình bày metadata từ một phiên bản dependency không đúng.

### 13.3. Tài liệu từ thư viện ngoài

Nếu symbol đến từ package, hover có thể dùng package documentation hoặc metadata đi kèm. Nội dung cần gắn với đúng package version.

## 14. Hover và nội dung chưa hoàn chỉnh

Người dùng thường hover khi đang viết mã, lúc source có thể chưa parse hoàn chỉnh.

Ví dụ:

```text
workflow createOrder(order: Order) {
    validate order.
```

Parser có thể chưa biết phần sau dấu chấm. Hover trên `order` vẫn có thể cung cấp kiểu `Order`, trong khi hover trên vị trí sau dấu chấm có thể không có kết quả.

### 14.1. Error recovery

Parser có thể tạo AST một phần hoặc node lỗi để language service tiếp tục cung cấp hover cho các vùng không bị ảnh hưởng.

### 14.2. Semantic result một phần

Type checker có thể biết kiểu của một số biểu thức dù phần chương trình còn lại lỗi. Hover nên sử dụng thông tin chắc chắn và tránh suy diễn vượt quá dữ liệu hiện có.

### 14.3. Trạng thái chưa xác định

Nếu kiểu chưa suy luận được, service có thể hiển thị `Unknown`, `Unresolved` hoặc thông báo phù hợp theo quy ước của DSL. Không nên giả vờ rằng kiểu đã được xác định.

## 15. Trải nghiệm người dùng

Hover cần xuất hiện đúng lúc, đủ thông tin và không cản trở thao tác soạn thảo.

### 15.1. Thời điểm xuất hiện

Popup thường xuất hiện sau khi con trỏ dừng trên một vùng có thể cung cấp thông tin. Nếu xuất hiện ngay lập tức khi con trỏ đi qua, nó có thể gây nhấp nháy và che mã.

### 15.2. Vị trí popup

Editor thường đặt popup gần con trỏ nhưng tránh vượt khỏi viewport. Nếu popup che dòng quan trọng, người dùng có thể di chuyển con trỏ hoặc mở nội dung ở một panel khác.

### 15.3. Kích thước và cuộn

Nội dung nên ưu tiên thông tin chính. Nếu cần hiển thị documentation dài, popup có thể có giới hạn chiều cao và cuộn nội bộ, hoặc cung cấp thao tác mở tài liệu đầy đủ.

### 15.4. Không che thao tác chính

Hover không nên xuất hiện khi người dùng đang chọn văn bản, kéo thả, chỉnh sửa hoặc thực hiện thao tác mà popup gây cản trở. Client cần cân nhắc trạng thái con trỏ và tương tác hiện tại.

### 15.5. Tương tác với popup

Một số editor cho phép di chuyển con trỏ vào popup để chọn và copy nội dung hoặc nhấn liên kết. Popup cần có hành vi ổn định để không biến mất ngay khi con trỏ rời khỏi token.

## 16. Khả năng truy cập

Hover bằng chuột không đủ cho mọi người dùng. Một tính năng trợ giúp tốt cần có cách truy cập bằng bàn phím và công nghệ hỗ trợ.

Các nguyên tắc quan trọng:

- Có lệnh hoặc phím tắt để hiển thị thông tin tại vị trí con trỏ.
- Popup có thể nhận focus nếu người dùng cần tương tác.
- Có thể đóng bằng Escape hoặc thao tác tương đương.
- Nội dung có thứ tự đọc rõ ràng cho screen reader.
- Không dùng màu sắc duy nhất để phân biệt error, warning hoặc deprecated.
- Liên kết có nhãn mô tả, không chỉ là biểu tượng khó hiểu.
- Nội dung không biến mất quá nhanh khi người dùng chuyển focus.

### 16.1. Keyboard-triggered hover

Editor có thể cung cấp lệnh “Show Hover” hoặc “Show Documentation” để người dùng mở thông tin tại caret hiện tại mà không cần chuột.

### 16.2. Screen reader

Nội dung hover nên dùng cấu trúc heading, danh sách và code hợp lý. Khi popup mở, editor cần thông báo phù hợp mà không đọc lại quá nhiều nội dung ngoài ngữ cảnh.

### 16.3. Touch device

Thiết bị cảm ứng không có hover liên tục như chuột. Có thể cung cấp thao tác chạm vào symbol, nhấn giữ hoặc lệnh context để mở cùng loại thông tin.

## 17. Bảo mật khi hiển thị hover

Hover content có thể lấy từ source comment, package documentation hoặc nội dung do người dùng khác cung cấp. Vì vậy, editor cần xử lý nội dung như dữ liệu không đáng tin cậy.

### 17.1. Markdown và HTML

Nếu cho phép Markdown hoặc HTML, renderer cần áp dụng chính sách an toàn. Không nên thực thi script hoặc cho phép nội dung tùy ý truy cập môi trường của editor.

### 17.2. Liên kết ngoài

Link trong documentation nên được xử lý theo chính sách của editor. Người dùng cần biết khi một liên kết sẽ mở trang bên ngoài.

### 17.3. Không thực thi mã để tạo hover

Hover không nên tự động chạy mã DSL, macro hoặc script tùy ý chỉ để lấy mô tả. Thông tin nên được lấy từ AST, semantic metadata hoặc documentation đã được xử lý an toàn.

### 17.4. Bí mật trong dữ liệu

Không nên hiển thị password, token hoặc dữ liệu nhạy cảm trong hover chỉ vì chúng xuất hiện trong giá trị literal. Nếu hover có hiển thị constant value, cần áp dụng chính sách che thông tin cho các trường được đánh dấu secret.

### 17.5. Tài liệu từ dependency

Package documentation có thể chứa nội dung độc hại hoặc liên kết không an toàn. Renderer nên sanitize nội dung và giới hạn khả năng tương tác.

## 18. Cấu hình hover trong DSL tooling

Một công cụ DSL có thể cho phép cấu hình loại thông tin hiển thị:

```text
editor {
    hover {
        showType = true
        showDocumentation = true
        showDefaultValue = true
        showDeprecatedNotice = true
        maxDocumentationLines = 20
    }
}
```

Đây là cấu hình minh họa. Một số tùy chọn thuộc editor client, một số thuộc language server; không nên giả định tất cả đều do DSL source điều khiển.

### 18.1. Tùy chọn theo workspace

Workspace có thể chọn mức thông tin hoặc tắt một provider nếu tài liệu quá dài hoặc có quy định bảo mật.

### 18.2. Tùy chọn theo người dùng

Người dùng có thể thay đổi delay, kích thước popup hoặc phím tắt theo editor. Những tùy chọn này thường không cần lưu trong source DSL.

### 18.3. Locale

Documentation có thể có nhiều ngôn ngữ. Hover provider có thể chọn nội dung theo locale người dùng nếu package cung cấp bản dịch, đồng thời giữ nguyên tên symbol và chữ ký kỹ thuật.

## 19. Tương tác với các tính năng editor khác

Hover là một phần trong hệ sinh thái language tooling và thường chia sẻ dữ liệu với các tính năng khác.

| Tính năng | Quan hệ với hover |
|---|---|
| Completion | Có thể dùng cùng symbol/type metadata để giải thích mục được đề xuất |
| Go to definition | Cùng symbol identity, nhưng điều hướng đến declaration thay vì hiển thị nội dung |
| Find references | Cùng symbol index để tìm mọi nơi sử dụng |
| Signature help | Hiển thị tham số trong lúc nhập lời gọi; hover có thể hiển thị toàn bộ signature |
| Diagnostics | Hover có thể giải thích lỗi tại vị trí, nhưng diagnostic vẫn có vòng đời riêng |
| Rename | Dựa trên symbol identity, không dựa trên chuỗi tên trong hover |
| Code actions | Có thể cung cấp cách sửa được nhắc đến trong nội dung hover |
| Semantic highlighting | Có thể dùng cùng semantic classification để xác định loại symbol |

### 19.1. Dùng chung semantic model

Nếu mỗi tính năng tự phân giải tên theo cách riêng, kết quả có thể mâu thuẫn: hover nói một kiểu, completion gợi ý kiểu khác, go to definition mở nhầm khai báo. Dùng chung semantic model giúp các tính năng nhất quán.

### 19.2. Hover và signature help

Signature help thường được kích hoạt khi người dùng đang nhập dấu ngoặc hoặc dấu phẩy trong lời gọi hàm. Nó tập trung vào tham số hiện tại. Hover có thể cung cấp chữ ký và documentation khi trỏ vào tên hàm.

### 19.3. Hover và go to definition

Hover có thể hiển thị qualified name hoặc vị trí khai báo, nhưng thao tác điều hướng vẫn nên được cung cấp qua go to definition. Không nên biến popup hover thành cách duy nhất để truy cập định nghĩa.

## 20. Ví dụ triển khai hover provider

Một provider có thể thực hiện các bước khái niệm:

```text
provideHover(document, position):
    snapshot = workspace.currentSnapshot(document)
    node = snapshot.syntax.findNodeAt(position)

    if node is none:
        return null

    symbol = snapshot.semantics.resolve(node)

    if symbol exists:
        signature = snapshot.types.signatureOf(symbol)
        docs = documentationStore.lookup(symbol.id)
        details = metadataProvider.details(symbol)
        return renderHover(signature, docs, details)

    typeInfo = snapshot.types.typeOf(node)
    if typeInfo exists:
        return renderExpressionHover(typeInfo)

    return keywordOrLiteralHover(node)
```

Đây là pseudocode, không phải API của một thư viện cụ thể. Một implementation thực tế cần xử lý document version, cancellation, range, error recovery và khả năng client.

### 20.1. Tránh tính lại semantic analysis

`workspace.currentSnapshot` đại diện cho kết quả đã được cập nhật từ những thay đổi gần nhất. Nếu snapshot chưa sẵn sàng, service có thể chờ một tác vụ ngắn, trả kết quả một phần hoặc không có hover tùy chính sách.

### 20.2. Trả range phù hợp

Nếu hover được tạo cho một identifier, range có thể là toàn bộ identifier. Nếu hover áp dụng cho biểu thức, range có thể bao trùm biểu thức đó.

### 20.3. Xử lý nhiều provider

Một orchestrator có thể thử symbol provider, type provider và keyword provider theo thứ tự. Khi một provider trả nội dung có độ tin cậy cao, nó có thể được ưu tiên; hoặc nhiều phần có thể được hợp nhất nếu không trùng lặp.

## 21. Ví dụ hover trong DSL khai báo

Giả sử DSL:

```text
/// Cấu hình triển khai của một dịch vụ.
service "catalog" {
    replicas = 3
    region = "asia-southeast1"
    image = "catalog:v2"
}
```

Metadata schema:

```text
property replicas: Integer {
    description = "Số lượng instance của dịch vụ."
    default = 1
    minimum = 1
    maximum = 20
}

property region: String {
    description = "Vùng triển khai."
    allowedValues = ["asia-southeast1", "us-central1"]
}
```

Hover trên `replicas` có thể hiển thị:

```text
replicas: Integer

Số lượng instance của dịch vụ.

Default: 1
Range: 1..20
```

Hover trên `region` có thể hiển thị:

```text
region: String

Vùng triển khai.

Allowed values:
- asia-southeast1
- us-central1
```

Nếu giá trị hiện tại là `europe-west1`, diagnostic có thể báo giá trị không được hỗ trợ; hover có thể bổ sung danh sách giá trị hợp lệ.

## 22. Ví dụ hover trong DSL có hàm và kiểu

Giả sử thư viện cung cấp:

```text
/// Tính tổng tiền của các dòng hàng.
/// Không bao gồm phí vận chuyển.
function subtotal(items: List<LineItem>): Money
```

Trong mã:

```text
let total = subtotal(order.items)
```

Hover trên `subtotal` có thể hiển thị:

```text
subtotal(items: List<LineItem>): Money

Tính tổng tiền của các dòng hàng.
Không bao gồm phí vận chuyển.

Parameter:
- items: Danh sách dòng hàng.

Returns:
- Money: Tổng giá trị hàng hóa.
```

Hover trên `total` có thể hiển thị kiểu suy luận `Money`, trong khi hover trên `order.items` có thể hiển thị `List<LineItem>`.

## 23. Kiểm thử hover

Hover cần được kiểm thử cả dữ liệu trả về lẫn hành vi tương tác.

### 23.1. Kiểm thử vị trí

Đặt cursor tại:

- Giữa tên symbol.
- Ký tự đầu và cuối identifier.
- Tên hàm, tham số và kiểu.
- Literal và keyword.
- Comment, string và khoảng trắng.
- Vị trí ngoài nội dung hoặc cuối dòng.

Xác nhận provider tìm đúng node hoặc trả không có kết quả khi phù hợp.

### 23.2. Kiểm thử name resolution

Tạo hai symbol cùng tên trong namespace khác nhau và xác nhận hover hiển thị đúng symbol theo import và scope.

### 23.3. Kiểm thử type information

Kiểm tra biến, biểu thức, generic, overload, nullable type và literal. Đặc biệt kiểm tra trạng thái khi type inference chưa hoàn tất.

### 23.4. Kiểm thử documentation

Xác nhận documentation comment, package docs, default value và deprecation metadata được hợp nhất theo quy tắc. Kiểm tra trường hợp thiếu documentation.

### 23.5. Kiểm thử nội dung định dạng

Kiểm tra Markdown, code block, link, ký tự đặc biệt và nội dung dài. Xác nhận client hiển thị nội dung đúng mà không thực thi HTML hoặc script không an toàn.

### 23.6. Kiểm thử cập nhật và cache

Sau khi đổi kiểu hoặc documentation, hover phải phản ánh document version mới. Không được trả nội dung từ cache cũ hoặc từ dependency version khác.

### 23.7. Kiểm thử hiệu năng

Đo thời gian phản hồi khi hover symbol cục bộ, symbol từ dependency và symbol trong workspace lớn. Kiểm tra cancellation khi người dùng di chuyển con trỏ liên tục.

### 23.8. Kiểm thử khả năng truy cập

Kiểm tra lệnh keyboard-triggered hover, focus, Escape, screen reader và hành vi trên thiết bị không có chuột.

## 24. Những sai lầm thường gặp

**Chỉ tìm từ gần con trỏ.** Tên giống nhau ở namespace khác nhau có thể là symbol khác nhau. Hover nên dùng semantic resolution khi có thể.

**Hiển thị kiểu khai báo thay vì kiểu thực tế.** Với generic, overload hoặc inference, cần dùng kết quả semantic của vị trí hiện tại.

**Chạy lại toàn bộ compiler cho mỗi hover.** Điều này gây độ trễ. Nên tái sử dụng AST, symbol index và semantic snapshot đã có.

**Trả nội dung quá dài.** Hover nên là thông tin ngắn tại chỗ, còn tài liệu đầy đủ có thể mở qua link.

**Không xử lý document version.** Kết quả cũ có thể xuất hiện sau khi người dùng đã sửa mã.

**Cache chỉ theo tên symbol.** Hai symbol cùng tên có thể có kiểu và tài liệu khác nhau. Cần cache theo symbol identity và snapshot phù hợp.

**Dùng hover thay diagnostics.** Lỗi quan trọng cần có diagnostic riêng để người dùng vẫn thấy khi không hover.

**Không hỗ trợ bàn phím và screen reader.** Người dùng không sử dụng chuột sẽ khó tiếp cận thông tin.

**Render documentation không an toàn.** Nội dung từ source hoặc dependency không được phép thực thi script tùy ý.

**Hiển thị giá trị nhạy cảm.** Hover trên literal secret có thể vô tình tiết lộ token hoặc password.

**Không xét workspace nhiều tệp.** Symbol từ module khác cần được phân giải và lấy tài liệu theo đúng dependency version.

## 25. Ghi nhớ

- Hover hiển thị thông tin theo ngữ cảnh khi người dùng trỏ vào vị trí trong editor.
- Nội dung thường gồm symbol, kiểu, signature, documentation, metadata và cảnh báo.
- Hover tốt dựa trên AST, symbol resolution và type information, không chỉ tìm chuỗi ký tự.
- LSP cung cấp request `textDocument/hover` để editor và language server trao đổi thông tin hover.
- Nội dung có thể dùng Markdown hoặc plaintext; range giúp xác định vùng liên quan.
- Documentation có thể đến từ comment nguồn, schema metadata hoặc package docs.
- Hover khác completion, go to definition, signature help và diagnostics dù có thể dùng chung semantic model.
- Hiệu năng cần được bảo đảm bằng semantic snapshot, cancellation, giới hạn nội dung và cache có invalidation.
- Hover trong workspace nhiều tệp cần symbol index và dependency version chính xác.
- Tính năng cần hỗ trợ bàn phím, screen reader và thiết bị cảm ứng.
- Nội dung hover phải được sanitize và không được tiết lộ bí mật.

## 26. Câu hỏi tự kiểm tra

1. Hiển thị hover là gì và nó giúp người dùng DSL như thế nào?
2. Hover khác completion, go to definition và diagnostics ở điểm nào?
3. Vì sao hover trên hai symbol cùng tên ở namespace khác nhau phải cho kết quả khác nhau?
4. Luồng xử lý `textDocument/hover` trong LSP gồm những bước nào?
5. Những loại thông tin nào có thể được hiển thị khi hover trên biến, hàm, thuộc tính và literal?
6. Vì sao hover nên dùng kết quả semantic analysis thay vì chỉ tìm token theo văn bản?
7. Documentation có thể được lấy từ những nguồn nào và cần hợp nhất ra sao?
8. Vì sao hover cần xử lý document version và cancellation?
9. Cache hover cần những thành phần nào trong cache key và khi nào cần invalidation?
10. Khi parser chưa hoàn chỉnh, language service có thể cung cấp hover một phần như thế nào?
11. Những nguyên tắc nào giúp hover dễ truy cập bằng bàn phím và screen reader?
12. Vì sao nội dung Markdown hoặc documentation từ dependency cần được xử lý an toàn?
13. Làm thế nào để hover hiển thị đúng symbol trong workspace có nhiều tệp và nhiều module?
14. Hãy mô tả một hover provider cho thuộc tính `replicas` gồm kiểu, mô tả, default và giới hạn giá trị.
