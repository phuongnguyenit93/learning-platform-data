# Điều hướng tham chiếu

Trong một DSL (Domain-Specific Language), người viết thường đặt tên cho entity, kiểu dữ liệu, hàm, rule, workflow, biến và thuộc tính rồi sử dụng những tên đó ở nhiều nơi. Khi cần hiểu một symbol đang được dùng ở đâu, người dùng muốn xem tất cả vị trí tham chiếu đến nó thay vì tìm từng chuỗi văn bản bằng tay. **Điều hướng tham chiếu (reference navigation)** là nhóm chức năng của editor và language server giúp tìm, liệt kê và chuyển đến những vị trí đang tham chiếu một symbol cụ thể.

Điều hướng tham chiếu thường được cung cấp qua thao tác **Find All References** hoặc **Go to References**. Người dùng đặt con trỏ trên tên symbol, kích hoạt lệnh và nhận danh sách các vị trí có liên kết ngữ nghĩa đến symbol đó. Kết quả có thể nằm trong cùng file, nhiều module, dependency, tệp generated hoặc tài liệu đang mở.

Để làm chính xác, language server phải hiểu symbol identity và phân giải tên giống compiler. Nó cần phân biệt tham chiếu thật với chuỗi ký tự trùng tên, xử lý scope, import, overload và shadowing, duy trì workspace index khi file thay đổi, rồi trả các source location cho editor. Tính năng này còn là nền tảng cho rename symbol, tìm nơi sử dụng API và phân tích ảnh hưởng của một thay đổi.

## 1. Điều hướng tham chiếu là gì?

Reference là một vị trí trong chương trình sử dụng hoặc phụ thuộc vào một symbol đã được khai báo. Điều hướng tham chiếu tìm những vị trí như vậy và cho phép người dùng mở chúng trực tiếp.

Ví dụ:

```text
// model/order.dsl
entity Order {
    id: OrderId
    total: Money
}
```

```text
// rules/shipping.dsl
import model.Order

rule freeShipping {
    when order.total >= minimumTotal
    then createShipment(order)
}
```

Khi con trỏ đặt trên khai báo `Order`, Find All References có thể liệt kê import, chú thích kiểu, lời gọi hoặc truy cập thuộc tính có liên quan đến symbol `Order` theo semantics của DSL. Nếu người dùng đặt con trỏ trên `total`, kết quả chỉ nên gồm những tham chiếu đến field `Order.total`, không phải mọi chuỗi `total` trong workspace.

### 1.1. Reference navigation khác với tìm kiếm văn bản

Tìm kiếm văn bản trả về mọi đoạn có chuỗi ký tự khớp. Reference navigation trả về những vị trí đã được phân giải đến cùng symbol.

```text
let status = "DRAFT"
log("status")
if status == PAID {
    submitOrder()
}
```

Chuỗi `"status"` trong lời gọi `log` không phải reference đến biến `status`. Identifier trong điều kiện là reference. Tìm kiếm văn bản không phân biệt được hai trường hợp này; language server dùng parser và semantic model để làm điều đó.

### 1.2. Reference có thể là nhiều loại sử dụng

Một reference có thể đọc biến, ghi biến, gọi hàm, truy cập field, dùng type trong annotation hoặc import symbol. Một số editor còn phân loại reference theo vai trò để người dùng hiểu symbol được dùng như thế nào.

### 1.3. Reference navigation và nơi khai báo

Go to Definition tìm nơi symbol được định nghĩa. Find All References tìm các vị trí sử dụng symbol. Hai chức năng bổ sung cho nhau: một giúp tìm nguồn gốc, chức năng kia giúp hiểu phạm vi ảnh hưởng và cách sử dụng.

## 2. Phân biệt các thao tác điều hướng liên quan

Editor có thể cung cấp nhiều thao tác với mục tiêu khác nhau:

| Thao tác | Câu hỏi được trả lời |
|---|---|
| Go to Definition | Symbol được định nghĩa ở đâu? |
| Go to Declaration | Symbol được khai báo ở đâu? |
| Go to Implementation | Có implementation nào của contract hoặc interface này? |
| Find All References | Những vị trí nào tham chiếu đến symbol này? |
| Find Usages | Symbol được sử dụng ở đâu, thường kèm phân loại cách dùng? |
| Document Highlight | Những lần xuất hiện liên quan trong file hiện tại là gì? |
| Rename Symbol | Có thể đổi tên symbol và cập nhật các reference ra sao? |
| Call Hierarchy | Hàm được gọi từ đâu và gọi những hàm nào? |

Các editor có thể đặt tên hoặc gộp một số thao tác khác nhau, nhưng language service nên giữ semantics rõ ràng. Ví dụ Find All References không đồng nghĩa với Call Hierarchy: một thao tác tìm vị trí tham chiếu đến symbol, thao tác kia phân tích quan hệ gọi hàm.

## 3. Symbol identity là nền tảng của reference navigation

Để biết hai vị trí có tham chiếu cùng một symbol hay không, language server cần một định danh ngữ nghĩa cho symbol. Tên hiển thị không đủ vì nhiều symbol có thể cùng tên.

Ví dụ:

```text
module sales.orders
enum Status { DRAFT, PAID }

module billing.payments
enum Status { PENDING, SETTLED }
```

`Status` trong module sales và `Status` trong module billing là hai symbol khác nhau. Reference navigation phải tìm đúng nhóm sử dụng của từng symbol.

Một symbol record có thể chứa:

| Trường | Mục đích |
|---|---|
| Symbol ID | Định danh nội bộ cho symbol |
| Name | Tên hiển thị |
| Qualified name | Tên kèm module hoặc namespace |
| Kind | Type, entity, function, field, rule, variable... |
| Owner | Module, scope hoặc type sở hữu |
| Signature/type | Kiểu, tham số và kiểu trả về |
| Definition location | URI và range của khai báo |
| Visibility | Private, module, public hoặc mức khác |
| Origin | Source DSL, built-in, dependency hay generated |

### 3.1. Vì sao không dùng tên làm khóa?

Giả sử hai hàm cùng tên:

```text
function format(value: Money): String
function format(value: Date): String
```

Lời gọi `format(order.total)` chỉ tham chiếu overload nhận `Money` nếu `order.total` có kiểu `Money`. Nếu index chỉ lưu chuỗi `format`, kết quả sẽ trộn references của hai overload.

### 3.2. Symbol ID và reference binding

Trong AST hoặc semantic model, mỗi identifier reference nên được liên kết đến symbol ID cụ thể sau name resolution. Reference index có thể ánh xạ symbol ID sang danh sách source locations.

```text
ReferenceIndex
├── symbol: sales.Order
│   ├── rules/shipping.dsl:1:8
│   ├── rules/refund.dsl:3:15
│   └── tests/order.dsl:7:12
└── symbol: billing.Invoice
    ├── reports/monthly.dsl:2:10
    └── rules/billing.dsl:4:20
```

### 3.3. Symbol identity ổn định đến mức nào?

Có thể dùng ID nội bộ theo workspace hoặc build. Khi file được sửa, symbol ID có thể được tái sử dụng nếu compiler xác định cùng declaration; nếu không, index cần cập nhật cả declaration và reference. ID không nhất thiết phải ổn định qua mọi phiên bản compiler, nhưng cache phải biết khi nào ID cũ không còn hợp lệ.

## 4. Những vị trí nào được tính là reference?

Ngôn ngữ cần định nghĩa rõ những loại sử dụng nào được tính vào kết quả.

| Loại reference | Ví dụ |
|---|---|
| Đọc biến | `if total > limit` |
| Ghi biến | `total = 0` |
| Đọc/ghi thuộc tính | `order.status = PAID` |
| Gọi hàm | `calculateTax(order)` |
| Dùng kiểu | `value: Money` |
| Import | `import model.Order` |
| Dùng enum member | `status == OrderStatus.PAID` |
| Kế thừa/implements | `entity Employee extends Person` |
| Generic constraint | `T: Comparable` |
| Tham chiếu trong annotation | `@Table(Customer)` |
| Macro/template reference | `generateEntity(Order)` |

Comment, string literal và ví dụ trong tài liệu thường không phải semantic reference, trừ khi DSL có cơ chế link hoặc embedded language riêng.

### 4.1. Declaration có được tính vào kết quả không?

Nhiều API cho phép chọn có bao gồm vị trí khai báo hay không. Người dùng Find All References có thể muốn chỉ xem các lần sử dụng, hoặc muốn cả khai báo để có danh sách đầy đủ.

Editor cần hiển thị rõ vị trí khai báo nếu nó được trả về, tránh khiến người dùng nhầm rằng declaration là một lần sử dụng.

### 4.2. Read và write references

Với biến hoặc thuộc tính mutable, phân biệt đọc và ghi rất hữu ích:

```text
let initial = account.balance       // read
account.balance = initial + amount  // read + write
resetBalance(account)               // có thể là write qua lời gọi
```

Phân loại chính xác có thể cần phân tích AST và semantics của hàm. Một lời gọi có thể thay đổi dữ liệu dù cú pháp trông như chỉ đọc; language server chỉ nên khẳng định read/write khi có thông tin về effects hoặc contract.

### 4.3. Type references và value references

Một tên có thể được dùng trong ngữ cảnh kiểu hoặc giá trị. Nếu DSL có namespace riêng cho type và value, reference index phải lưu loại namespace để tránh trộn symbol cùng tên.

## 5. Từ vị trí con trỏ đến danh sách references

Khi người dùng gọi Find All References, editor gửi vị trí tài liệu và con trỏ. Language server cần xác định symbol tại vị trí đó, rồi truy vấn reference index.

Quy trình tổng quát:

```text
Editor position
      |
      v
Find token and AST node
      |
      v
Resolve reference to symbol ID
      |
      v
Query reference index
      |
      v
Filter by scope / workspace / options
      |
      v
Map to document URI and source ranges
      |
      v
Return locations to editor
```

### 5.1. Xác định token tại vị trí con trỏ

Language server nhận document URI và position. Nó cần tìm identifier hoặc AST node chứa vị trí đó. Nếu con trỏ nằm trong dấu chấm của `order.total`, server có thể chọn token gần nhất theo quy ước editor hoặc trả kết quả không có symbol.

### 5.2. Xác định AST node

Parser cho biết token đang đóng vai trò gì: identifier expression, type name, import path, field access hay một phần của declaration. Đây là bước phân biệt semantic reference với text.

### 5.3. Resolve symbol

Resolver áp dụng scope, import, namespace, alias, visibility, generic substitution và overload resolution. Kết quả là symbol cụ thể hoặc tập candidate nếu chưa đủ thông tin.

### 5.4. Truy vấn reference index

Khi có symbol ID, server lấy danh sách reference locations. Có thể lọc theo workspace, module, document, reference kind hoặc tùy chọn include declaration.

### 5.5. Chuyển thành location

Mỗi reference cần URI và range chính xác. Editor dùng các location này để hiển thị danh sách, mở file hoặc đánh dấu vị trí.

## 6. Phân giải tham chiếu trong scope

Reference navigation phải tuân theo quy tắc scope của DSL. Với lexical scope, tên thường được resolve đến binding gần nhất bao quanh vị trí tham chiếu.

```text
let status = "NEW"

function processOrder() {
    let status = "REVIEW"
    log(status)
}
```

Reference `status` trong `log(status)` thuộc biến cục bộ của `processOrder`. Find All References trên biến ngoài không nên bao gồm vị trí này.

### 6.1. Shadowing

Khi biến bên trong shadow biến bên ngoài, mỗi identifier reference cần liên kết với binding tương ứng. Reference index không được nhóm chỉ theo tên.

### 6.2. Closure capture

Closure có thể tham chiếu binding được khai báo ở scope bao quanh. Các lần sử dụng bên trong closure vẫn là reference đến symbol đã capture, kể cả khi closure chạy sau khi hàm ngoài kết thúc.

### 6.3. Function parameter

Tham số là symbol riêng. Một identifier cùng tên trong scope ngoài không được trộn với reference đến parameter.

### 6.4. Module và global scope

Các reference đến constant, function hoặc type cấp module cần được phân giải qua import/export và namespace. Symbol global hoặc built-in có thể được index riêng để hỗ trợ navigation trên toàn workspace.

## 7. Reference qua import và nhiều module

Trong dự án DSL nhiều file, một symbol có thể được tham chiếu qua import trực tiếp, alias, wildcard hoặc re-export.

Ví dụ:

```text
// rules/shipping.dsl
import sales.Order as Purchase

function shippingCost(order: Purchase): Money {
    return order.total
}
```

Các vị trí `Purchase` và `Order` trong import đều có thể được coi là references đến symbol `sales.Order`, tùy chính sách tính reference của ngôn ngữ. Field access `order.total` lại tham chiếu đến symbol field `Order.total`.

### 7.1. Alias

Alias là tên cục bộ cho symbol đã được import. Reference đến alias cần được liên kết với symbol gốc, đồng thời có thể lưu alias usage để người dùng thấy cách symbol được dùng trong module hiện tại.

### 7.2. Wildcard import

Với wildcard import, không phải mọi symbol trong module đều được tham chiếu. Chỉ những symbol thực sự được dùng ở các identifier tương ứng mới thuộc reference set. Bản thân wildcard import có thể được ghi nhận như một dependency hoặc import reference riêng.

### 7.3. Re-export

Khi module A export lại symbol từ module B, người dùng có thể muốn biết nơi nào dùng symbol gốc và nơi nào đi qua re-export. Reference index có thể giữ cả symbol origin lẫn export edge để hỗ trợ navigation và phân tích phụ thuộc.

### 7.4. Dependency packages

Reference có thể nằm trong package phụ thuộc nếu source được cài đặt và index. Nếu chỉ có binary/interface metadata, language server có thể chỉ biết declaration và không có toàn bộ source usages. Kết quả nên phản ánh phạm vi index thực tế.

## 8. Reference trong overload và generic

Overload resolution quyết định lời gọi cụ thể tham chiếu đến hàm nào.

```text
function format(value: Money): String
function format(value: Date): String

let label = format(order.total)
let dateLabel = format(order.createdAt)
```

Reference từ `format(order.total)` thuộc overload `format(Money)`; reference từ `format(order.createdAt)` thuộc overload `format(Date)` nếu kiểu tương ứng đã được resolve.

### 8.1. Overload chưa thể xác định

Nếu kiểu đối số chưa rõ hoặc dynamic, language server có thể có nhiều candidate. Nó nên hiển thị ambiguity hoặc tập candidate thay vì gộp mọi overload vào một nhóm references mà không nói rõ.

### 8.2. Generic instantiation

Một hàm generic có thể được gọi với nhiều kiểu thực tế. References thường được gom theo generic declaration, nhưng đôi khi người dùng muốn lọc theo instantiation cụ thể. Language server có thể lưu cả symbol generic và instantiated symbol để hỗ trợ các góc nhìn khác nhau.

### 8.3. Extension methods và implicit conversions

Nếu DSL hỗ trợ extension method hoặc implicit conversion, cú pháp gọi có thể không chỉ rõ tên owner. Resolver phải xác định symbol thực sự được chọn; nếu không, Find All References có thể bỏ sót hoặc đưa vào các ứng viên không liên quan.

## 9. Reference index trong language server

Để tìm references nhanh, language server thường duy trì index từ symbol đến các vị trí sử dụng.

Một cấu trúc khái quát:

```text
WorkspaceIndex
├── SymbolTable
│   ├── symbol ID -> metadata
│   └── module -> exported symbols
├── ReferenceIndex
│   ├── symbol ID -> locations
│   └── document URI -> references
└── DependencyGraph
    ├── module imports
    └── API dependencies
```

### 9.1. Index theo symbol

Truy vấn symbol ID trả về danh sách vị trí nhanh. Đây là cấu trúc phù hợp cho Find All References.

### 9.2. Index theo document

Index theo document giúp xóa hoặc thay thế toàn bộ references của một file khi file thay đổi. Server parse lại file, tạo tập reference mới rồi cập nhật index theo version.

### 9.3. Index theo module

Partition theo module/package giúp tải và cập nhật độc lập, nhất là workspace lớn. Dependency graph cho biết những module nào có thể bị ảnh hưởng khi API của module khác thay đổi.

### 9.4. Persisted index

Index có thể được lưu giữa các lần mở workspace. Cache cần gắn với hash nội dung, compiler version, schema DSL, dependency versions và cấu hình build. Nếu một yếu tố ảnh hưởng đến name resolution thay đổi, index liên quan phải được invalidated.

## 10. Xây dựng và cập nhật reference index

Có nhiều chiến lược index tùy kích thước workspace và yêu cầu phản hồi.

### 10.1. Full indexing

Khi mở workspace, server quét các file, parse và thu thập declarations cùng references. Cách này tạo index đầy đủ nhưng có thể mất thời gian và bộ nhớ.

### 10.2. Incremental indexing

Khi một file thay đổi, server chỉ parse lại file đó và thay thế các entries cũ của file trong index. Nếu exported API thay đổi, các consumer liên quan có thể cần resolve lại.

### 10.3. Lazy indexing

Server có thể chỉ index file khi mở hoặc khi được tham chiếu. Cách này giảm chi phí khởi động nhưng kết quả Find All References có thể chưa đầy đủ cho đến khi workspace indexing hoàn tất.

### 10.4. Hybrid indexing

Một chiến lược thực tế là index declarations toàn workspace trước, sau đó index references đầy đủ cho module đang mở hoặc module được truy vấn. Khi người dùng yêu cầu tìm toàn workspace, server có thể mở rộng index theo nhu cầu.

### 10.5. Xử lý file bị xóa hoặc đổi tên

Khi document bị xóa, tất cả reference entries thuộc document đó phải bị loại bỏ. Khi đổi tên, URI mới phải được ghi nhận và dependency graph cập nhật; không được giữ location trỏ đến file cũ.

## 11. Language Server Protocol: textDocument/references

Language Server Protocol (LSP) cung cấp request chuẩn để editor yêu cầu danh sách references. Request thường có tên `textDocument/references`.

Request gồm document URI, position và context. Context có trường `includeDeclaration` để cho biết kết quả có nên chứa vị trí khai báo hay không.

Ví dụ request dạng JSON:

```json
{
  "textDocument": {
    "uri": "file:///workspace/rules/shipping.dsl"
  },
  "position": {
    "line": 8,
    "character": 21
  },
  "context": {
    "includeDeclaration": false
  }
}
```

Ví dụ trên minh họa cấu trúc; line và character trong LSP thường dùng chỉ số bắt đầu từ 0. Server cần tuân thủ position encoding đã thương lượng với client.

### 11.1. Response locations

Server trả về một danh sách location, mỗi phần tử gồm URI và range. Editor có thể dùng danh sách đó để hiển thị panel references, mở từng file hoặc highlight các vị trí.

### 11.2. Include declaration

Khi `includeDeclaration` là false, server thường chỉ trả các references. Khi true, declaration có thể được thêm vào danh sách. Server cần thực hiện đúng option và editor nên phân biệt declaration với usage nếu giao thức hoặc UI cho phép.

### 11.3. Không tìm thấy reference

Nếu không có vị trí phù hợp, server trả danh sách rỗng. Đây là kết quả hợp lệ, không nhất thiết là lỗi giao thức.

### 11.4. Request cancellation

Workspace lớn có thể khiến truy vấn mất thời gian. Server nên hỗ trợ cancellation và tránh tiếp tục tính toán cho request đã bị người dùng thay thế bằng thao tác mới.

### 11.5. Partial results và progress

Với kết quả lớn, server có thể dùng cơ chế progress hoặc partial result mà giao thức hỗ trợ. Editor có thể hiển thị kết quả dần, nhưng cần xử lý trùng lặp và hủy request đúng cách.

## 12. Source location và position encoding

Mỗi reference cần một vị trí nguồn chính xác. Location thường gồm document URI và range bao phủ identifier hoặc node sử dụng.

Ví dụ:

```text
ReferenceLocation
├── uri: file:///workspace/rules/shipping.dsl
└── range:
    ├── start: line 8, character 21
    └── end:   line 8, character 25
```

### 12.1. Token range và AST range

Range của reference thường bao phủ tên được sử dụng, không phải toàn bộ câu lệnh. Với field access `order.total`, range có thể chỉ bao phủ `total`; với qualified name `sales.Order`, có thể chọn toàn qualified name hoặc segment hiện tại theo semantics editor.

### 12.2. Unicode

Lexer nội bộ có thể lưu UTF-8 byte offsets trong khi editor protocol dùng UTF-16 hoặc một encoding đã thương lượng. Server phải chuyển đổi nhất quán để highlight đúng ký tự, nhất là khi dòng có emoji hoặc ký tự ngoài BMP.

### 12.3. Tệp chưa lưu

Reference locations phải được tính từ document snapshot hiện tại. Nếu người dùng đổi tên biến trong buffer chưa lưu, index dựa trên file disk cũ có thể trả kết quả sai.

### 12.4. Generated location

Nếu reference xuất hiện trong generated file, URI có thể là file generated hoặc virtual document. Server cần bảo đảm editor có thể mở URI đó hoặc ánh xạ location về DSL source tương ứng.

## 13. Phạm vi tìm kiếm

Find All References có thể tìm trong nhiều phạm vi khác nhau. Cần xác định rõ phạm vi mặc định và cách người dùng mở rộng.

| Phạm vi | Nội dung |
|---|---|
| Current document | Chỉ file hiện tại |
| Current module | Các file thuộc module hiện tại |
| Workspace | Các file trong dự án đang mở |
| Dependencies | Source của package được tham chiếu |
| Standard library | Built-in hoặc thư viện chuẩn có metadata |
| Generated sources | Mã được sinh và metadata origin |

### 13.1. Workspace references

Workspace là phạm vi thường dùng cho Find All References. Server cần biết những file nào thuộc workspace và những file nào bị loại như build output, cache hoặc thư mục vendor không được index.

### 13.2. External dependencies

Không phải dependency nào cũng có source. Nếu không có reference index đầy đủ, server có thể chỉ tìm được usages trong workspace hiện tại. UI hoặc documentation nên thể hiện giới hạn này.

### 13.3. Multi-root workspace

Một editor có thể mở nhiều project root. Reference query cần biết tìm trong root hiện tại hay toàn bộ workspace. Các symbol ID cần phân biệt cùng tên giữa các root và dependency version khác nhau.

### 13.4. Generated/build folders

Indexing generated files có thể làm kết quả trùng hoặc quá lớn. Có thể mặc định loại chúng khỏi danh sách source references, nhưng vẫn giữ origin mapping để điều hướng giữa DSL và generated code khi cần.

## 14. Reference của field, property và member access

Field reference thường khó hơn variable reference vì cần biết receiver có kiểu nào.

Ví dụ:

```text
entity Order {
    total: Money
}

entity Invoice {
    total: Decimal
}

let orderTotal = order.total
let invoiceTotal = invoice.total
```

Hai field đều tên `total`, nhưng là hai symbol khác nhau. Resolver phải dùng kiểu của receiver (`Order` hoặc `Invoice`) để xác định member.

### 14.1. Inherited members

Nếu `Employee` kế thừa `Person`, reference `employee.name` có thể resolve đến field được khai báo trong `Person`. Find All References trên `Person.name` cần bao gồm những truy cập thông qua receiver subtype nếu semantics xác định chúng là cùng symbol.

### 14.2. Extension members

Extension property hoặc method có thể được áp dụng cho kiểu mà không nằm trong khai báo gốc. Resolver cần xác định extension nào được import và được chọn ở vị trí sử dụng.

### 14.3. Dynamic property access

Với cú pháp như `record[fieldName]`, field có thể được chọn lúc runtime. Nếu `fieldName` là biểu thức động, language server có thể không biết một symbol cụ thể. Nó có thể tìm các candidate hoặc đánh dấu kết quả là không đầy đủ.

## 15. Read/write references và phân tích tác động

Biết một biến được dùng ở đâu là hữu ích; biết nó được đọc hay ghi còn hữu ích hơn.

Ví dụ:

```text
var retryCount = 0

function retry() {
    retryCount = retryCount + 1
    log(retryCount)
}
```

Reference đầu tiên trong biểu thức bên phải là read; assignment target là write; đối số truyền vào `log` là read.

### 15.1. Read references

Read reference tiêu thụ giá trị của symbol. Nó giúp tìm nơi logic phụ thuộc vào biến hoặc field.

### 15.2. Write references

Write reference thay đổi binding hoặc trạng thái. Nó giúp tìm nơi có thể làm thay đổi dữ liệu và hỗ trợ phân tích mutation.

### 15.3. Read-write references

Các phép như `count += 1` vừa đọc giá trị cũ vừa ghi giá trị mới. Language server có thể phân loại thành read-write.

### 15.4. Indirect writes

Lời gọi `resetAccount(account)` có thể thay đổi `account.balance`. Nếu language server có effect metadata hoặc contract, nó có thể chỉ ra indirect write. Nếu không, nên tránh khẳng định chính xác vì tác dụng phụ có thể nằm trong implementation.

### 15.5. Tìm nơi thay đổi trạng thái

Một giao diện Find Usages có thể lọc read, write và call sites. Điều này hữu ích khi điều tra vì sao một trạng thái thay đổi hoặc khi muốn kiểm tra mọi nơi có thể ghi vào field.

## 16. References trong macro, template và generated code

DSL có thể có macro hoặc template tạo ra symbol và reference sau expansion.

Ví dụ:

```text
generateEntity(Customer)
```

Macro có thể sinh field `id`, constructor hoặc method. Reference đến symbol được sinh có thể không tồn tại trực tiếp trong văn bản nguồn.

### 16.1. Origin mapping

Compiler có thể lưu mapping từ generated node đến macro invocation và template definition. Reference navigation có thể:

- Hiển thị vị trí invocation trong DSL.
- Hiển thị template tạo ra symbol.
- Mở generated virtual document.
- Cung cấp nhiều location nếu người dùng cần cả nguồn và expansion.

### 16.2. Generated references

Một reference được tạo ra từ code generation không nên bị trộn với reference người dùng viết nếu mục tiêu là hiểu usages trong DSL. Có thể cung cấp bộ lọc “include generated code”.

### 16.3. Source maps

Source map cần giữ cả source range và generated range. Với reference query, server có thể dùng mapping để chuyển location từ generated representation về source DSL hoặc ngược lại.

## 17. Dynamic references và giới hạn phân tích tĩnh

Không phải mọi tham chiếu đều có thể biết trước khi chạy.

Ví dụ:

```text
let handlerName = config["handler"]
invokeByName(handlerName, order)
```

Nếu tên hàm được tạo từ dữ liệu runtime, static resolver không thể biết chắc hàm nào được gọi. Find All References có thể không bao gồm lời gọi động hoặc chỉ hiển thị những candidate được suy ra từ schema/configuration.

### 17.1. Reflection

Reflection cho phép chương trình tìm type hoặc method theo chuỗi tên lúc runtime. Reference navigation tĩnh thường không thể bảo đảm đầy đủ nếu tên chỉ xuất hiện trong dữ liệu hoặc cấu hình.

### 17.2. String-based references

Một DSL có thể quy định một số string literal là symbol reference, ví dụ tên workflow trong cấu hình. Khi đó parser hoặc schema cần đánh dấu chúng là embedded references để language server có thể resolve.

### 17.3. Plugin và extension point

Plugin có thể đăng ký symbol sau khi runtime khởi động. Language server chỉ có thể index các plugin được khai báo trong workspace hoặc metadata đã cài đặt. Kết quả cần thể hiện phạm vi và độ chắc chắn.

### 17.4. Reference completeness

Không nên khẳng định danh sách references là đầy đủ nếu có dynamic dispatch, reflection hoặc dependency source chưa được index. Có thể cung cấp trạng thái “workspace results” và giải thích phần không thể phân tích tĩnh.

## 18. Cập nhật index và tránh stale references

Reference index có thể trở nên lỗi thời khi file thay đổi, module đổi tên hoặc dependency version được cập nhật.

### 18.1. Document version

Mỗi lần document thay đổi, server nên gắn version cho snapshot và kết quả parse. Reference entries cần được thay thế bằng kết quả từ version mới.

### 18.2. Invalidation theo file

Khi file thay đổi, server có thể xóa tất cả references do file đó tạo ra rồi thêm tập mới. Cách này tránh phải tìm và sửa từng reference cũ trong index.

### 18.3. Invalidation theo dependency

Khi public symbol của module thay đổi, các module phụ thuộc có thể cần resolve lại. Dependency graph giúp giới hạn vùng invalidation.

### 18.4. Rename và delete

Khi file đổi tên hoặc bị xóa, reference index cần cập nhật URI và loại bỏ location cũ. Khi một symbol bị xóa, các references chưa được resolve phải được xử lý như lỗi semantic thay vì giữ liên kết cũ.

### 18.5. Request đang chạy trong lúc edit

Một Find All References query có thể chạy khi người dùng tiếp tục sửa code. Server cần dùng snapshot nhất quán, hỗ trợ cancellation và không trả kết quả từ index version không tương thích với document position.

## 19. Reference navigation và Rename Symbol

Find All References là nền tảng cho Rename Symbol, nhưng rename có yêu cầu chặt hơn.

### 19.1. Find references

Find references chỉ đọc index và trả locations. Nó không thay đổi file.

### 19.2. Rename

Rename cần:

1. Resolve symbol tại vị trí con trỏ.
2. Tìm mọi reference và declaration cần đổi.
3. Phân biệt semantic references với string/comment không liên quan.
4. Tạo edits theo document URI và range.
5. Kiểm tra collision với symbol khác và scope.
6. Áp dụng thay đổi nguyên tử hoặc thông qua workspace edit của editor.

### 19.3. Vì sao rename cần nhiều kiểm tra hơn?

Một vị trí reference sai có thể khiến rename làm hỏng chương trình. Với dynamic reference, macro expansion hoặc string-based reference, có thể cần thêm quy tắc đặc biệt hoặc yêu cầu xác nhận người dùng.

### 19.4. Rename và file/module names

Đổi tên symbol không nhất thiết đổi tên file hoặc module. Nếu DSL có quy tắc file name gắn với symbol, language server cần công bố và xử lý riêng file operations.

## 20. Giao diện kết quả Find All References

Kết quả nên giúp người dùng hiểu nơi symbol được sử dụng và chọn vị trí phù hợp.

### 20.1. Nhóm theo file

Với nhiều references, editor thường nhóm kết quả theo URI/file rồi hiển thị từng dòng. Người dùng có thể mở một location và xem context xung quanh.

### 20.2. Preview và context

Preview có thể hiển thị dòng chứa reference cùng vài dòng lân cận. Nên highlight đúng identifier range, không chỉ highlight cả dòng.

### 20.3. Loại reference

Nếu server cung cấp metadata read/write/call/type, UI có thể cho lọc theo loại. Nếu giao thức chỉ trả location, client có thể chỉ hiển thị danh sách vị trí đơn giản.

### 20.4. Declaration trong kết quả

Khi include declaration, UI nên đánh dấu riêng để người dùng phân biệt nơi định nghĩa với nơi sử dụng.

### 20.5. Kết quả lớn

Với symbol được dùng hàng nghìn nơi, UI có thể cần progress, giới hạn hiển thị, lọc theo file/module hoặc tải thêm kết quả. Server không nên âm thầm cắt danh sách mà không thông báo.

### 20.6. Navigation history

Khi người dùng mở một reference, editor nên giữ lịch sử điều hướng để quay lại vị trí tìm kiếm hoặc vị trí trước đó.

## 21. Hiệu năng và khả năng mở rộng

Trong workspace lớn, tìm references bằng cách parse mọi file ở mỗi request sẽ chậm. Reference index giúp chuyển phần lớn công việc sang giai đoạn indexing.

Các kỹ thuật phổ biến:

- Index theo symbol ID để truy vấn trực tiếp.
- Index ngược theo document để cập nhật file nhanh.
- Incremental parsing và semantic analysis.
- Dependency graph để invalidation theo module.
- Cache query theo symbol ID và workspace version.
- Lazy loading dependency source.
- Cancellation và partial progress cho request lớn.
- Giới hạn indexing generated folders không cần thiết.

### 21.1. Query complexity

Nếu reference index lưu danh sách location theo symbol, truy vấn có thể gần với O(k), trong đó k là số kết quả cần trả về, thay vì quét toàn bộ N token của workspace. Chi phí xây dựng và cập nhật index vẫn cần được tính đến.

### 21.2. Bộ nhớ

Có thể lưu symbol ID, URI, range và loại reference ở dạng compact. Không nhất thiết giữ toàn bộ AST của mọi file trong bộ nhớ nếu source map và semantic metadata đủ cho truy vấn.

### 21.3. Cache invalidation

Cache phải gắn với workspace version và dependency state. Chỉ dùng symbol name làm cache key có thể trả nhầm kết quả khi scope hoặc module thay đổi.

## 22. Bảo mật và ranh giới workspace

Reference navigation thường chỉ đọc dữ liệu, nhưng language server vẫn cần xử lý đường dẫn và dependency an toàn.

Các điểm cần chú ý:

- Chỉ index file trong workspace hoặc dependency root được phép.
- Chuẩn hóa URI và canonical path để tránh path traversal.
- Xử lý symlink theo chính sách rõ ràng.
- Không tải source từ mạng tùy tiện chỉ để tìm references.
- Giới hạn kích thước và độ sâu khi parse dependency không tin cậy.
- Không để virtual URI khiến editor mở tài nguyên ngoài phạm vi.
- Không tiết lộ đường dẫn hoặc metadata nhạy cảm của môi trường khác.

Với multi-root workspace, cần xác định rõ query tìm trong root hiện tại hay tất cả root. Dependency cùng tên ở hai project không được gộp nếu chúng là hai version hoặc hai symbol identity khác nhau.

## 23. Diagnostic và trường hợp không tìm thấy references

Không có kết quả có thể là trạng thái bình thường. Nhưng đôi khi việc không tìm thấy references là dấu hiệu index hoặc resolver chưa hoàn chỉnh.

Các nguyên nhân thường gặp:

- Con trỏ không nằm trên symbol reference.
- Symbol chưa được phân giải do lỗi cú pháp hoặc kiểu.
- Symbol chưa có usages trong phạm vi tìm kiếm.
- Một số file chưa được index.
- Dependency source không có sẵn.
- Symbol là dynamic hoặc reflection-based.
- Index đang stale hoặc chưa cập nhật.
- URI hoặc source location không còn tồn tại.

Language server nên phân biệt “no references found” với “reference search incomplete” khi có thể. UI có thể hiển thị trạng thái indexing hoặc phạm vi đã tìm.

### 23.1. Ambiguous symbol

Nếu reference position có nhiều candidate, server cần dùng type/context để resolve. Nếu vẫn mơ hồ, có thể trả candidate hoặc diagnostic thay vì gộp usages của mọi symbol cùng tên.

### 23.2. Error-tolerant parsing

Khi file có syntax error, parser có thể giữ AST một phần. Language server vẫn có thể tìm references ở vùng không bị ảnh hưởng, nhưng cần tránh dùng semantic model không nhất quán.

## 24. Ví dụ tổng hợp: tìm references trong DSL nhiều module

Workspace:

```text
workspace/
├── common/
│   └── money.dsl
├── sales/
│   ├── order.dsl
│   └── customer.dsl
└── shipping/
    └── rules.dsl
```

`common/money.dsl`:

```text
module common
export type Money {
    amount: Decimal
    currency: CurrencyCode
}
```

`sales/order.dsl`:

```text
module sales
import common.Money

export entity Order {
    id: OrderId
    total: Money
    shippingFee: Money
}
```

`shipping/rules.dsl`:

```text
module shipping
import sales.Order

rule freeShipping {
    when order.total.amount >= 1_000_000
    then order.shippingFee = Money.zero(VND)
}
```

Khi người dùng chọn `Order.total` và gọi Find All References, language server cần:

1. Resolve `total` thành field symbol thuộc `sales.Order`.
2. Truy vấn reference index theo symbol ID của field.
3. Tìm các field access như `order.total`, không trộn với `Invoice.total`.
4. Có thể bao gồm field declaration nếu `includeDeclaration` được bật.
5. Trả URI/range cho từng location.
6. Editor nhóm theo file và highlight chính xác token `total`.

Nếu người dùng chọn `Money`, kết quả sẽ gồm type annotation trong `Order.total`, các field khác có kiểu `Money`, lời gọi constructor hoặc các function signature tham chiếu đến type này. Tập kết quả phụ thuộc vào định nghĩa reference của DSL và việc các file liên quan đã được index hay chưa.

## 25. Kiểm thử reference navigation

Kiểm thử nên xác nhận symbol identity, phạm vi và source ranges.

Các trường hợp quan trọng:

- Một biến có nhiều references trong cùng file.
- Hai biến cùng tên ở scope khác nhau.
- Shadowing và closure capture.
- Function overload cùng tên.
- Field trùng tên trong hai entity.
- Reference qua import, alias và re-export.
- Type reference và value reference cùng tên.
- Inherited field và extension method.
- Read, write và read-write usage.
- Include hoặc exclude declaration.
- Reference trong dependency package.
- Built-in và generated symbol.
- Dynamic/reflection reference không resolve tĩnh.
- Tài liệu chưa lưu và document version mới.
- File rename/delete và incremental index update.
- Workspace nhiều root và dependency nhiều version.
- Unicode source range.
- Cancellation và kết quả lớn/partial progress.
- Rename dựa trên reference set.

### 25.1. Resolver tests

Có thể tạo fixture nhiều file, đặt vị trí con trỏ tại reference và xác nhận symbol ID được resolve. Test này kiểm tra semantics độc lập với giao thức editor.

### 25.2. Index tests

Kiểm tra reference entries được thêm, thay thế và xóa đúng khi file thay đổi. Có thể xác nhận index không giữ URI cũ sau rename/delete.

### 25.3. LSP integration tests

Gửi `textDocument/references` với URI, position và `includeDeclaration`; kiểm tra danh sách URI/range trả về. Cần xác nhận line/character theo đúng position encoding.

### 25.4. Editor UX tests

Kiểm tra nhóm kết quả theo file, preview, lọc read/write nếu có, điều hướng đến location và thông báo khi index chưa đầy đủ.

## 26. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Tìm chuỗi thay vì symbol | Trả về comment, string và tên trùng không liên quan | Dùng AST và semantic resolution |
| Dùng tên làm identity | Trộn overload hoặc symbol từ module khác | Dùng symbol ID và owner/type metadata |
| Bỏ qua scope/shadowing | Reference bị gán nhầm binding | Áp dụng đúng lexical resolution |
| Chỉ index file đang mở | Bỏ sót usages ở file khác | Workspace và dependency indexing |
| Không cập nhật index khi edit | Kết quả chứa location cũ | Versioned incremental indexing |
| Coi mọi call là cùng overload | Tập references không chính xác | Dùng kiểu đối số và overload resolution |
| Không phân biệt read/write | Khó phân tích mutation | Lưu reference role khi có thể xác định |
| Gộp declaration và usage | Người dùng khó hiểu kết quả | Tôn trọng includeDeclaration và đánh dấu riêng |
| Không thể hiện dynamic limitations | Kết quả trông đầy đủ nhưng thiếu usages runtime | Công bố phạm vi và độ đầy đủ |
| Index generated code không kiểm soát | Kết quả trùng và nhiễu | Phân loại generated/source references |
| Sai position encoding | Highlight lệch ký tự | Chuyển đổi range nhất quán |
| Không hủy request cũ | UI nhận kết quả stale | Cancellation và document version check |

## 27. Nguyên tắc thiết kế reference navigation cho DSL

Khi xây dựng language server, có thể áp dụng các nguyên tắc sau:

1. **Resolve theo symbol identity.** Không dùng text search làm kết quả chính.
2. **Tuân thủ compiler semantics.** Scope, import, overload và visibility phải giống compiler.
3. **Xác định loại reference.** Phân biệt read, write, call, type, import và declaration khi có thể.
4. **Duy trì workspace reference index.** Hỗ trợ file, module, dependency và multi-root workspace.
5. **Cập nhật index theo version.** Loại bỏ entries cũ khi file thay đổi, đổi tên hoặc bị xóa.
6. **Trả source ranges chính xác.** URI và position encoding phải tương thích editor.
7. **Hỗ trợ LSP chuẩn.** Xử lý `textDocument/references`, `includeDeclaration`, cancellation và kết quả lớn.
8. **Thể hiện giới hạn phân tích tĩnh.** Dynamic dispatch, reflection và dependency thiếu source có thể làm kết quả không đầy đủ.
9. **Giữ origin mapping.** Hỗ trợ references trong macro expansion và generated code.
10. **Phân biệt Find References với Call Hierarchy và Rename.** Các thao tác liên quan nhưng không có cùng semantics.
11. **Bảo vệ ranh giới workspace.** Kiểm soát URI, symlink và nguồn dependency.
12. **Kiểm thử resolver, index và UI.** Xác nhận cả symbol identity lẫn trải nghiệm điều hướng.

## 28. Kết luận

Điều hướng tham chiếu giúp người viết DSL tìm mọi vị trí sử dụng một symbol cụ thể trong workspace. Để trả kết quả chính xác, language server cần phân giải identifier thành symbol identity, áp dụng scope và overload semantics, duy trì reference index và ánh xạ mỗi lần sử dụng đến source URI/range.

Trong dự án nhiều module, index cần bao gồm import, dependency, generated source và các thay đổi chưa lưu. LSP cung cấp request `textDocument/references` cùng tùy chọn include declaration để editor yêu cầu danh sách locations. Các trường hợp dynamic, reflection hoặc thiếu source cần được thể hiện như giới hạn thay vì tạo cảm giác kết quả đầy đủ.

Khi reference navigation được xây dựng trên cùng mô hình ngữ nghĩa với compiler, người dùng có thể khám phá codebase, tìm nơi đọc/ghi dữ liệu, đánh giá ảnh hưởng của API và thực hiện rename an toàn hơn. Đây là một năng lực cốt lõi giúp DSL trở nên dễ bảo trì và có trải nghiệm phát triển tương đương các ngôn ngữ lập trình tổng quát.
