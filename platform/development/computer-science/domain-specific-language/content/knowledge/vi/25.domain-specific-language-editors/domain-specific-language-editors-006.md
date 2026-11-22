# Đi tới định nghĩa

Trong một DSL (Domain-Specific Language), người viết thường sử dụng tên để tham chiếu đến entity, kiểu dữ liệu, hàm, rule, workflow, biến hoặc trường của một đối tượng. Khi đọc một chương trình lớn, người dùng cần biết một tên được khai báo ở đâu và muốn mở ngay vị trí khai báo đó trong trình soạn thảo. Tính năng **Đi tới định nghĩa (Go to Definition)** hỗ trợ thao tác này: từ một tham chiếu đang được con trỏ đặt vào, editor tìm symbol tương ứng và điều hướng đến nơi symbol được định nghĩa.

Đi tới định nghĩa là một chức năng điều hướng mã nguồn dựa trên phân giải tên và mô hình ngữ nghĩa của DSL. Nó không chỉ tìm chuỗi có cùng cách viết. Một tên có thể xuất hiện ở nhiều module, nhiều scope hoặc nhiều overload; editor phải xác định đúng symbol mà tham chiếu hiện tại biểu thị, rồi chuyển người dùng đến vị trí nguồn chính xác.

Trong DSL có nhiều tệp, tính năng này đặc biệt hữu ích vì định nghĩa có thể nằm trong file khác, package phụ thuộc, thư viện chuẩn hoặc mã được sinh. Để hoạt động tin cậy, editor cần phối hợp parser, symbol index, name resolver, source location và giao thức tích hợp với IDE.

## 1. Go to Definition là gì?

Go to Definition là thao tác điều hướng từ một vị trí tham chiếu đến vị trí khai báo hoặc định nghĩa của symbol được tham chiếu. Người dùng thường kích hoạt bằng phím tắt, menu chuột phải hoặc Ctrl/Cmd + click vào tên.

Ví dụ DSL:

```text
// models/order.dsl
entity Order {
    id: OrderId
    total: Money
}
```

```text
// rules/shipping.dsl
import models.Order

rule freeShipping {
    when order.total >= minimumTotal
    then createShipment(order)
}
```

Khi con trỏ đặt trên `Order` trong import hoặc trên `Order` trong một chú thích kiểu, editor có thể mở `models/order.dsl` tại dòng khai báo `entity Order`. Khi con trỏ đặt trên `createShipment`, editor tìm định nghĩa hàm hoặc action tương ứng.

### 1.1. Definition khác với mọi lần xuất hiện của tên

Một tên có thể xuất hiện trong khai báo, tham chiếu, comment, string literal hoặc tài liệu. Go to Definition chỉ nên điều hướng từ một tham chiếu ngữ nghĩa đã được phân giải đến symbol đích.

Ví dụ:

```text
let status = "DRAFT"
log("status")
if status == DRAFT {
    submitOrder()
}
```

Tên `status` trong lời gọi `log("status")` nằm trong string literal, không phải tham chiếu biến. Tên `status` trong điều kiện là tham chiếu biến. Tìm kiếm văn bản đơn thuần không thể phân biệt hai trường hợp này.

### 1.2. Định nghĩa và khai báo

Một số ngôn ngữ phân biệt declaration và definition. Declaration giới thiệu tên hoặc chữ ký; definition cung cấp thân triển khai. Ví dụ một hàm có thể được khai báo trong interface và định nghĩa ở module khác.

DSL cần xác định Go to Definition trỏ đến đâu khi có cả declaration và implementation. Có thể điều hướng đến implementation, đến declaration đầu tiên hoặc hiển thị nhiều đích nếu có nhiều định nghĩa hợp lệ.

## 2. Vì sao tính năng này quan trọng trong DSL?

DSL thường dùng tên nghiệp vụ có ý nghĩa như `Customer`, `OrderStatus`, `calculateTax`, `approvePayment` hoặc `shippingAddress`. Khi dự án lớn, người viết cần khám phá cách các tên được khai báo, kiểu của chúng và logic liên quan.

Go to Definition giúp:

- Hiểu nguồn gốc của entity, field, function, rule và workflow.
- Khám phá API của module hoặc thư viện được import.
- Điều tra lỗi kiểu hoặc lỗi phân giải tên.
- Theo dõi một thuộc tính từ nơi sử dụng đến schema hoặc model.
- Đọc logic được tái sử dụng mà không cần tìm kiếm thủ công.
- Điều hướng qua nhiều tệp và package trong workspace.
- Hiểu quan hệ giữa DSL source và generated code khi có source mapping.

Đối với người mới học DSL, tính năng này còn là một công cụ khám phá ngôn ngữ: từ một tên được sử dụng, họ có thể xem định nghĩa, kiểu, tài liệu và các ràng buộc liên quan.

## 3. Những loại symbol có thể điều hướng

Editor cần biết DSL hỗ trợ những loại symbol nào và vị trí định nghĩa tương ứng của từng loại.

| Loại symbol | Ví dụ tham chiếu | Đích điều hướng |
|---|---|---|
| Biến | `minimumTotal` | Nơi khai báo biến hoặc binding |
| Tham số | `order` trong thân hàm | Khai báo tham số trong chữ ký hàm |
| Entity/record | `Order` | Khai báo entity hoặc record |
| Kiểu dữ liệu | `Money` | Khai báo type hoặc alias |
| Enum và member | `OrderStatus.PAID` | Khai báo enum hoặc member tương ứng |
| Function | `calculateTax(...)` | Khai báo hoặc thân hàm |
| Rule | `freeShipping` | Khai báo rule |
| Workflow | `fulfillOrder` | Khai báo workflow |
| Field/property | `order.total` | Khai báo field trong entity hoặc schema |
| Module/package | `models.Order` | Module descriptor hoặc file nguồn đại diện |
| Constant | `DEFAULT_TIMEOUT` | Khai báo constant |
| Built-in symbol | `String`, `now()` | Tài liệu hoặc định nghĩa thư viện chuẩn |

Không phải mọi token đều là symbol có thể điều hướng. Dấu ngoặc, toán tử hoặc literal thường không có định nghĩa theo nghĩa này, trừ khi DSL cung cấp operator overload hoặc macro symbol.

## 4. Từ vị trí con trỏ đến symbol

Để điều hướng chính xác, editor cần chuyển vị trí con trỏ thành một tham chiếu ngữ nghĩa.

Một quy trình khái quát:

```text
Vị trí con trỏ trong editor
          |
          v
Xác định token / AST node
          |
          v
Xác định scope và ngữ cảnh
          |
          v
Phân giải tên thành symbol
          |
          v
Tìm source location của symbol
          |
          v
Chuyển file và đặt con trỏ tại định nghĩa
```

### 4.1. Xác định token tại vị trí con trỏ

Editor gửi URI của tài liệu và vị trí dòng/cột. Language service xác định token hoặc AST node bao phủ vị trí đó.

Ví dụ:

```text
when order.total >= minimumTotal
                    ^^^^^^^^^^^^^
```

Nếu con trỏ nằm trong `minimumTotal`, parser hoặc semantic model cần xác định đây là identifier expression, không phải text bất kỳ.

### 4.2. Xác định ngữ cảnh cú pháp

Cùng một lexeme có thể mang ý nghĩa khác tùy vị trí. `Order` có thể là tên type trong khai báo, tên module trong qualified name hoặc một identifier trong biểu thức nếu DSL cho phép. AST giúp xác định vai trò của token.

### 4.3. Phân giải tên

Name resolver áp dụng quy tắc scope, import, namespace, visibility và overload để tìm symbol. Kết quả tốt nhất là symbol ID ổn định, không chỉ là chuỗi tên.

### 4.4. Tìm vị trí định nghĩa

Symbol record nên giữ source URI và source range của declaration/definition. Editor dùng vị trí đó để mở tài liệu, tải file nếu cần và đặt con trỏ đúng vào tên khai báo.

## 5. Symbol identity và symbol index

Go to Definition cần phân biệt các symbol có thể trùng tên. Ví dụ hai module đều có `Status`, nhưng chúng là hai symbol khác nhau.

```text
sales.orders.Status
billing.payments.Status
```

Một symbol index có thể lưu:

| Thuộc tính | Mục đích |
|---|---|
| Symbol ID | Định danh nội bộ ổn định trong workspace hoặc build |
| Name | Tên hiển thị của symbol |
| Qualified name | Tên đầy đủ gồm module/namespace |
| Kind | Entity, function, field, rule, variable... |
| Definition URI | Tệp chứa định nghĩa |
| Definition range | Vùng văn bản của tên hoặc khai báo |
| Scope/module | Phạm vi sở hữu symbol |
| Visibility | Private, module, public... |
| Signature/type | Kiểu, tham số hoặc metadata liên quan |
| Origin | Nguồn DSL, thư viện, generated code hoặc built-in |

### 5.1. Symbol ID thay vì tên văn bản

Không nên dùng tên hiển thị làm định danh duy nhất. Hai function overload có cùng tên nhưng chữ ký khác nhau; hai module có thể định nghĩa cùng `Order`; biến cục bộ có thể shadow biến ngoài.

Resolver nên tạo liên kết từ identifier reference trong AST đến symbol ID cụ thể. Go to Definition sử dụng liên kết đó để tìm đúng đích.

### 5.2. Qualified name

Qualified name cung cấp đường dẫn đầy đủ đến symbol:

```text
commerce.sales.Order
commerce.shipping.Shipment
```

Nó giúp hiển thị nguồn gốc và hỗ trợ tìm kiếm, nhưng không thay thế symbol identity nếu có generic instantiation, overload hoặc local scope.

### 5.3. Overload

Ví dụ:

```text
function format(value: Money): String
function format(value: Date): String
```

Khi con trỏ đặt trên lời gọi `format(order.total)`, resolver cần dùng kiểu đối số để xác định overload `format(Money)`. Nếu chỉ tìm tên `format`, editor có thể mở nhầm overload hoặc phải hiển thị danh sách đích.

## 6. Scope, shadowing và lexical resolution

Go to Definition phải tuân theo đúng quy tắc phân giải tên của DSL. Với lexical scope, binding gần nhất bao quanh vị trí tham chiếu thường được ưu tiên.

```text
let status = "NEW"

function processOrder() {
    let status = "REVIEW"
    log(status)
}
```

Tham chiếu `status` trong `log(status)` trỏ đến biến cục bộ trong `processOrder`, không phải biến bên ngoài. Editor phải mở đúng khai báo cục bộ.

### 6.1. Shadowing

Khi tên bên trong che khuất tên bên ngoài, resolver cần giữ binding cụ thể của từng reference. Tìm kiếm chuỗi `status` không đủ để quyết định đích.

### 6.2. Function parameters

Tham số cũng là symbol. Trong thân hàm, Go to Definition trên tên tham số nên điều hướng đến vị trí tham số trong chữ ký, không phải một biến cùng tên ở scope ngoài.

### 6.3. Closure capture

Closure có thể tham chiếu biến ở scope đã bao quanh nơi định nghĩa closure. Reference trong closure phải liên kết đến binding được capture theo lexical environment, kể cả khi hàm tạo closure đã kết thúc.

### 6.4. Dynamic scope

Nếu DSL dùng dynamic scope, đích có thể phụ thuộc call chain runtime và không thể luôn xác định tĩnh. Editor cần thể hiện giới hạn: có thể điều hướng đến khai báo gần nhất hoặc liệt kê các binding tiềm năng, nhưng không nên khẳng định một đích duy nhất khi semantics không xác định trước.

## 7. Import, module và nhiều tệp

Trong DSL nhiều tệp, một tham chiếu có thể đi qua import và namespace để đến định nghĩa ở file khác.

Ví dụ:

```text
// rules/shipping.dsl
import models.Order
import common.Money

function shippingCost(order: Order): Money {
    return order.total
}
```

Khi người dùng kích hoạt Go to Definition trên `Order`, editor cần:

1. Xác định `Order` là type reference.
2. Kiểm tra import hiện tại và alias nếu có.
3. Phân giải `models.Order` theo module resolver.
4. Kiểm tra symbol được export và có thể truy cập.
5. Tìm source URI và range của khai báo.
6. Mở `models/order.dsl` tại declaration.

### 7.1. Alias import

```text
import models.Order as Purchase
let order: Purchase
```

Reference `Purchase` vẫn phải điều hướng đến symbol `models.Order`, không phải tìm một khai báo literal tên `Purchase` trong module.

### 7.2. Wildcard import

Với `import models.*`, resolver cần tìm symbol theo export table của module. Nếu nhiều module import cùng một tên và gây ambiguity, editor nên báo mơ hồ hoặc cung cấp danh sách ứng viên.

### 7.3. Re-export

Một module có thể export lại symbol từ module khác. Go to Definition có thể mở định nghĩa gốc hoặc dừng tại re-export declaration tùy chính sách. Hành vi nên nhất quán và có thể cung cấp thêm lựa chọn “Go to declaration” nếu cần.

### 7.4. Package phụ thuộc

Định nghĩa có thể nằm trong dependency đã cài. Editor cần biết package root, version và vị trí source archive. Nếu chỉ có binary hoặc interface metadata, có thể điều hướng đến stub, API declaration hoặc tài liệu.

## 8. Definition, declaration và implementation

Trong một số DSL, tên được khai báo ở một nơi và triển khai ở nơi khác.

Ví dụ:

```text
// contracts/payment.dsl
interface PaymentService {
    function charge(amount: Money): PaymentResult
}
```

```text
// adapters/card-payment.dsl
implements PaymentService
function charge(amount: Money): PaymentResult {
    ...
}
```

Khi con trỏ đặt trên `charge` ở lời gọi, có thể có nhiều đích:

- Declaration trong interface.
- Implementation trong adapter cụ thể.
- Một implementation được chọn theo dependency injection hoặc runtime configuration.

Editor có thể ưu tiên declaration được resolve tĩnh, hoặc nếu chỉ có một implementation đã biết thì mở implementation. Nếu có nhiều implementation, nên hiển thị danh sách thay vì tự chọn một cách tùy tiện.

### 8.1. Go to Declaration

Go to Declaration thường đưa đến nơi symbol được khai báo, kể cả khi thân định nghĩa ở nơi khác. Với ngôn ngữ phân biệt rõ hai khái niệm, đây là thao tác riêng hữu ích.

### 8.2. Go to Implementation

Go to Implementation tìm phần triển khai cụ thể của interface, abstract function hoặc contract. Nó có thể trả về nhiều kết quả.

### 8.3. Go to Type Definition

Go to Type Definition điều hướng đến định nghĩa kiểu của biểu thức hoặc biến hiện tại. Ví dụ từ `order.total`, thao tác này có thể mở kiểu `Money` thay vì khai báo field `total`.

Ba thao tác này có mục tiêu khác nhau và không nên bị gộp nếu DSL có đủ thông tin để hỗ trợ riêng.

## 9. Vị trí nguồn và source range

Để mở đúng chỗ, compiler hoặc language server cần giữ source location của symbol.

Một location thường gồm:

- URI hoặc đường dẫn tài liệu.
- Start line và start character.
- End line và end character.
- Có thể thêm source version hoặc content hash.

Ví dụ khái niệm:

```text
DefinitionLocation
├── uri: file:///workspace/models/order.dsl
└── range:
    ├── start: line 2, character 7
    └── end:   line 2, character 12
```

Range nên bao phủ identifier hoặc vùng khai báo phù hợp. Nếu chỉ trỏ đến đầu file, editor vẫn có thể mở đúng file nhưng người dùng phải tự tìm tên.

### 9.1. Token range và declaration range

Có thể lưu cả range của tên symbol và range toàn declaration. Go to Definition thường đặt con trỏ tại tên; peek definition có thể hiển thị toàn declaration.

### 9.2. UTF-16, code point và byte offset

Editor và parser có thể dùng các đơn vị vị trí khác nhau. Giao thức editor có thể yêu cầu UTF-16 code units, trong khi lexer nội bộ lưu UTF-8 byte offsets. Cần chuyển đổi chính xác, đặc biệt với ký tự Unicode nhiều byte hoặc ký tự ngoài BMP.

### 9.3. Tệp chưa lưu

Editor có thể đang hiển thị nội dung chưa được lưu xuống disk. Language server nên phân tích text document đang mở theo version hiện tại, không chỉ đọc file trên filesystem. Nếu index vẫn dùng nội dung cũ, Go to Definition có thể trỏ sai.

## 10. Workspace indexing

Để tìm định nghĩa nhanh trong dự án lớn, language service thường xây dựng workspace symbol index.

Index có thể chứa:

- Danh sách file thuộc workspace.
- Module/package và quan hệ import.
- Các khai báo symbol.
- Qualified name và symbol ID.
- Source range và visibility.
- Dependency version và nguồn thư viện.
- Hash hoặc version nội dung để phát hiện stale entry.

### 10.1. Full workspace scan

Khi mở dự án, language server có thể quét các tệp DSL, parse và thu thập khai báo. Cách này đơn giản nhưng có thể chậm với workspace lớn.

### 10.2. Incremental indexing

Khi một file thay đổi, chỉ parse lại file đó và cập nhật symbol index cùng các dependency bị ảnh hưởng. Nếu API công khai của module thay đổi, những consumer tham chiếu đến symbol đó có thể cần được phân giải lại.

### 10.3. Lazy indexing

Có thể chỉ index file khi mở hoặc khi một module được tham chiếu. Cách này giảm thời gian khởi động nhưng lần điều hướng đầu tiên có thể chậm hơn.

### 10.4. Persisted index

Index có thể được lưu vào cache giữa các lần mở workspace. Cache cần gắn với phiên bản compiler, schema DSL, cấu hình, dependency và hash nguồn. Nếu một yếu tố ảnh hưởng đến symbol resolution thay đổi, entry liên quan phải được invalidated.

## 11. Language Server Protocol và editor integration

Nhiều editor tích hợp ngôn ngữ thông qua Language Server Protocol (LSP). Editor gửi yêu cầu điều hướng, language server phân tích tài liệu và trả về location.

### 11.1. Request textDocument/definition

Trong LSP, thao tác Go to Definition thường được biểu diễn bằng request `textDocument/definition`. Request chứa document URI và position của con trỏ. Server trả về một `Location`, nhiều `Location` hoặc `LocationLink` tùy kết quả và khả năng giao thức.

Ví dụ cấu trúc khái quát:

```json
{
  "textDocument": {
    "uri": "file:///workspace/rules/shipping.dsl"
  },
  "position": {
    "line": 8,
    "character": 21
  }
}
```

Đây là dạng minh họa. LSP dùng zero-based line và character; phần chuyển đổi từ vị trí nội bộ cần tuân theo encoding position negotiation của phiên bản giao thức.

### 11.2. Kết quả Location

Kết quả có thể bao gồm URI đích và range. Với nhiều overload hoặc nhiều implementation, server có thể trả nhiều location để editor hiển thị danh sách.

### 11.3. LocationLink

LocationLink cho phép cung cấp range của vùng nguồn và vùng đích, giúp editor preview chính xác hơn. Nó hữu ích khi muốn hiển thị đoạn tham chiếu đang được resolve và vùng khai báo tương ứng.

### 11.4. Không tìm thấy definition

Nếu con trỏ không nằm trên symbol có thể điều hướng hoặc resolver không tìm được đích, server có thể trả kết quả rỗng. Editor nên xử lý nhẹ nhàng, không coi đây là lỗi hệ thống.

### 11.5. Hủy request và phản hồi lỗi

Workspace lớn có thể khiến request mất thời gian. Server nên hỗ trợ cancellation, không trả kết quả cũ sau khi tài liệu đã đổi version và không chặn UI thread của editor.

## 12. Định nghĩa trong thư viện chuẩn và dependency

Go to Definition không chỉ hoạt động trong source của dự án. Tên có thể trỏ đến built-in type, standard library hoặc package bên ngoài.

Các cách cung cấp đích:

- Source file đi kèm package.
- Interface hoặc stub được tạo từ binary metadata.
- Declaration file hoặc schema.
- Tài liệu API có location hoặc URL.
- Built-in virtual document do language server cung cấp.

Ví dụ, khi điều hướng đến `String`, editor có thể mở virtual document mô tả built-in type nếu không có source code để hiển thị.

### 12.1. Dependency source

Nếu package đã cài source archive, language server có thể resolve location trong archive hoặc cache đã giải nén. URI cần được editor hỗ trợ; một số editor có thể chỉ mở được file URI thông thường.

### 12.2. Binary-only dependency

Khi không có source, có thể tạo virtual declaration từ metadata. Điều này vẫn giúp người dùng xem chữ ký và documentation, dù không thể mở implementation thật.

### 12.3. Version resolution

Nếu hai version của package cùng tồn tại, definition phải trỏ đến version mà module hiện tại thực sự resolve. Không nên mở source của phiên bản mới nhất chỉ vì nó có cùng tên.

## 13. Generated code và source mapping

DSL có thể được biên dịch thành Java, SQL, bytecode hoặc một dạng output khác. Một số symbol chỉ tồn tại sau khi sinh mã; một số symbol DSL lại ánh xạ đến nhiều đoạn generated code.

### 13.1. Điều hướng từ DSL sang DSL

Đây là trường hợp thông thường: reference trong DSL mở declaration trong source DSL. Symbol index giữ source URI và range ban đầu.

### 13.2. Điều hướng từ generated code về DSL

Khi người dùng debug generated Java, có thể muốn mở rule DSL gốc. Source map hoặc metadata origin liên kết generated range với source range.

### 13.3. Điều hướng từ DSL đến generated implementation

Một thao tác riêng như “Go to Generated Code” có thể mở đoạn mã target tương ứng. Không nên thay Go to Definition mặc định bằng generated code nếu người dùng đang mong đợi định nghĩa nguồn.

### 13.4. Một node sinh nhiều đoạn mã

Một rule DSL có thể sinh method kiểm tra, method thực thi và metadata. Source mapping có thể trả nhiều generated locations. Editor nên phân biệt navigation đến source definition với navigation đến generated implementation.

## 14. Macro, template và code expansion

Nếu DSL hỗ trợ macro hoặc template, một tên có thể được tạo ra sau expansion. Go to Definition cần xác định người dùng đang điều hướng đến macro/template nguồn hay symbol được tạo.

Ví dụ:

```text
generateEntity(Customer)
```

Macro `generateEntity` có thể sinh ra field hoặc method. Khi con trỏ đặt trên tên macro, Go to Definition mở macro. Khi đặt trên field được sinh, editor có thể mở vị trí invocation hoặc virtual expansion view.

### 14.1. Expansion mapping

Compiler có thể lưu origin mapping từ generated node về macro invocation và template definition. Tùy thao tác, editor chọn một trong các location này.

### 14.2. Symbol không có source trực tiếp

Một symbol có thể được sinh từ schema hoặc plugin. Nếu không có source location, language server có thể cung cấp virtual document hoặc thông báo nguồn gốc thay vì trả một đường dẫn không tồn tại.

## 15. Cập nhật index khi tài liệu thay đổi

Go to Definition cần phản ánh nội dung hiện tại, không dùng symbol index đã lỗi thời.

### 15.1. Open/change/save

Khi tài liệu mở, editor gửi nội dung hiện tại. Khi người dùng chỉnh sửa, server nhận change notification với version mới. Index cần được cập nhật hoặc đánh dấu dirty.

### 15.2. Đổi tên hoặc xóa file

Khi file bị rename/delete, symbol index cần loại bỏ URI cũ và thêm URI mới nếu có. Dependency graph và import resolver cũng cần cập nhật.

### 15.3. Thay đổi API công khai

Nếu một module đổi tên symbol hoặc chữ ký, consumer có thể cần re-resolve. Chỉ rebuild index của file khai báo mà không cập nhật các reference có thể khiến navigation mở đích sai hoặc không tìm thấy.

### 15.4. Race giữa request và edit

Một request Go to Definition có thể đang xử lý khi người dùng tiếp tục sửa file. Server nên gắn kết quả với document version và hủy hoặc bỏ kết quả nếu version không còn phù hợp.

### 15.5. File chưa lưu và file ngoài workspace

Có thể có file tạm, generated file hoặc external document. Language server cần chính sách rõ về việc index và theo dõi chúng, tránh giữ location đến file đã bị xóa.

## 16. Ambiguity và nhiều đích điều hướng

Không phải lúc nào một tham chiếu cũng có duy nhất một đích.

Các tình huống:

- Overload chưa thể chọn vì kiểu đối số chưa đủ thông tin.
- Interface có nhiều implementation.
- Conditional compilation hoặc target profile khác nhau.
- Dynamic dispatch có nhiều subtype khả dĩ.
- Symbol được re-export qua nhiều module.
- Macro tạo nhiều declaration cùng origin.

### 16.1. Trả về nhiều location

Nếu semantics cho phép nhiều đích, language server có thể trả danh sách. Editor hiển thị Quick Pick với tên, module, kind và file để người dùng chọn.

### 16.2. Không chọn ngẫu nhiên

Không nên lấy kết quả đầu tiên từ symbol index nếu thứ tự index không có ý nghĩa. Nếu resolver không thể xác định một đích duy nhất, cần thể hiện ambiguity.

### 16.3. Dynamic dispatch

Với lời gọi phương thức qua interface, Go to Definition có thể mở interface declaration. Go to Implementation có thể liệt kê các implementation. Điều này giúp phân biệt đích tĩnh với các đích có thể được gọi lúc runtime.

## 17. Fallback khi không có semantic result

Có lúc parser hoặc resolver chưa hoàn tất, hoặc người dùng đang đặt con trỏ trên văn bản không phải identifier.

Các fallback có thể gồm:

- Không làm gì và không hiển thị lỗi.
- Hiển thị symbol candidates từ lexical scope nếu semantic resolution tạm thời thất bại.
- Dùng workspace symbol search khi không thể resolve chính xác.
- Hiển thị thông báo rằng definition chưa được xác định.

Fallback phải được phân biệt với kết quả chính xác. Không nên trình bày một kết quả tìm kiếm văn bản như thể đó là semantic definition.

### 17.1. Parser đang ở trạng thái lỗi

Khi file có syntax error, AST có thể chưa hoàn chỉnh. Language service có thể dùng error-tolerant parser để giữ phần cây hợp lệ và vẫn hỗ trợ điều hướng cho các vùng không bị ảnh hưởng.

### 17.2. Chưa hoàn tất indexing

Khi workspace index đang xây dựng, server có thể ưu tiên kết quả từ file đang mở và scope hiện tại, sau đó cập nhật khả năng điều hướng khi index hoàn tất. UI nên thể hiện trạng thái nếu request phải chờ.

## 18. Trải nghiệm người dùng trong editor

Go to Definition thường có nhiều cách kích hoạt và cách hiển thị kết quả.

### 18.1. Phím tắt và chuột

Editor có thể hỗ trợ phím tắt chuẩn, context menu và Ctrl/Cmd + click. Người dùng cần thấy thao tác có sẵn khi con trỏ nằm trên symbol có thể điều hướng.

### 18.2. Peek Definition

Peek Definition hiển thị nội dung định nghĩa trong một panel nhỏ mà không rời file hiện tại. Nó hữu ích khi người dùng chỉ cần đọc nhanh chữ ký hoặc vài dòng code.

### 18.3. Mở definition

Go to Definition điều hướng sang file đích và đặt con trỏ tại range. Editor có thể lưu navigation history để người dùng quay lại vị trí trước đó.

### 18.4. Nhiều kết quả

Khi có nhiều đích, danh sách nên hiển thị:

- Tên symbol hoặc chữ ký.
- Loại symbol.
- Module/package.
- Đường dẫn file và dòng.
- Có thể thêm preview hoặc documentation.

### 18.5. Không có kết quả

Thông báo nên ngắn gọn, chẳng hạn “No definition found for this symbol”. Nếu nguyên nhân là dependency chưa được tải hoặc index chưa sẵn sàng, có thể đưa ra hướng xử lý cụ thể.

### 18.6. Navigation history

Khi người dùng đi qua nhiều definition, editor nên cho phép quay lại và đi tới trong lịch sử. Điều này đặc biệt hữu ích khi lần theo chuỗi phụ thuộc giữa nhiều module.

## 19. Hiệu năng và khả năng mở rộng

Workspace lớn có thể có hàng nghìn file và hàng trăm nghìn symbol. Go to Definition cần phản hồi nhanh mà không quét toàn bộ dự án mỗi lần bấm.

Các kỹ thuật thường dùng:

- Workspace symbol index được cập nhật incremental.
- Hash hoặc version để phát hiện file không đổi.
- Cache kết quả name resolution theo document version.
- Dependency graph để chỉ invalidation phần liên quan.
- Symbol ID và map lookup thay vì quét chuỗi tên.
- Lazy load dependency source.
- Cancellation cho request đã lỗi thời.
- Giới hạn công việc nặng khỏi UI thread.

### 19.1. Index theo module

Có thể partition index theo module/package để tải và cập nhật độc lập. Import graph giúp biết module nào cần được nạp khi resolve một symbol.

### 19.2. Cache có version

Cache resolution cần gắn với version của tài liệu, symbol index, compiler và dependency. Nếu một file khai báo thay đổi, cache của reference liên quan phải được invalidated.

### 19.3. Bộ nhớ và workspace lớn

Không nhất thiết giữ toàn bộ AST của mọi file trong bộ nhớ. Có thể lưu symbol index gọn nhẹ và parse đầy đủ khi file mở hoặc khi cần phân tích ngữ nghĩa sâu.

## 20. Bảo mật và quyền truy cập

Editor có thể mở definition từ dependency hoặc nguồn bên ngoài. Language server cần bảo vệ workspace và không để dữ liệu không tin cậy dẫn đến truy cập file tùy ý.

Các điểm cần xem xét:

- Chỉ resolve file nằm trong workspace hoặc dependency root được phép, trừ khi người dùng cấu hình khác.
- Chuẩn hóa URI và đường dẫn để tránh path traversal.
- Không thực thi script hoặc macro chỉ vì người dùng điều hướng đến symbol.
- Không tải source từ mạng theo cách tự động nếu chưa có chính sách rõ.
- Kiểm soát virtual document và URI scheme mà editor được yêu cầu mở.
- Không tiết lộ đường dẫn hoặc metadata nhạy cảm ngoài workspace.

### 20.1. Symlink và canonical path

Symlink có thể trỏ ra ngoài workspace. Resolver cần chính sách về việc theo symlink, canonical path và quyền truy cập. Nếu không, một import tưởng như nội bộ có thể mở file ngoài vùng cho phép.

### 20.2. Dependency chưa tin cậy

Source archive hoặc package metadata có thể chứa đường dẫn bất thường. Khi index dependency, cần giới hạn giải nén và kiểm tra URI, không để tên file độc hại truy cập tùy ý.

## 21. Diagnostic khi điều hướng thất bại

Go to Definition không nên biến mọi trường hợp không có đích thành lỗi nghiêm trọng. Tuy nhiên, nếu symbol đáng lẽ phải resolve mà không tìm thấy, có thể cung cấp thông tin hữu ích.

Ví dụ:

```text
Cannot find definition for "Order".
The import "models.Order" could not be resolved.
Check that module "models" is included in the workspace or dependency path.
```

Các nguyên nhân có thể là:

- Tên chưa được khai báo.
- Import sai hoặc module không tồn tại.
- Symbol không được export.
- Tên mơ hồ giữa nhiều module.
- Dependency source chưa có.
- Workspace index stale.
- Parser chưa tạo được node do syntax error.
- Source location bị mất trong generated metadata.

Diagnostic nên phân biệt unknown symbol, inaccessible symbol, ambiguous symbol và missing source. Mỗi trường hợp có cách xử lý khác nhau.

## 22. Thiết kế API cho language service

Ngay cả khi không dùng LSP, editor và language service vẫn cần một API nội bộ nhất quán.

Ví dụ interface khái quát:

```text
DefinitionProvider
    findDefinition(documentUri, position, documentVersion)
        -> DefinitionResult

DefinitionResult
    -> None
    -> One(Location)
    -> Many(List<Location>)
```

Provider có thể thực hiện:

1. Lấy document snapshot theo version.
2. Tìm AST node tại position.
3. Lấy symbol reference của node.
4. Resolve symbol theo semantic model.
5. Chọn declaration/definition theo navigation policy.
6. Trả location hoặc danh sách location.

### 22.1. Tách resolver khỏi UI

Name resolution nên là logic của language service, không đặt trong extension UI. Nhờ vậy nhiều editor có thể dùng cùng semantics và test resolver độc lập.

### 22.2. API bất đồng bộ

Indexing hoặc dependency loading có thể mất thời gian. API bất đồng bộ cho phép editor hủy request cũ và tiếp tục nhận tương tác.

### 22.3. Snapshot nhất quán

Resolver nên làm việc trên snapshot tài liệu và index version nhất quán. Nếu AST từ version mới nhưng symbol index từ version cũ, location có thể không còn đúng.

## 23. Ví dụ tổng hợp: điều hướng trong DSL nhiều module

Giả sử workspace:

```text
workspace/
├── common/
│   └── money.dsl
├── sales/
│   ├── customer.dsl
│   └── order.dsl
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
    status: OrderStatus
}
```

`shipping/rules.dsl`:

```text
module shipping
import sales.Order

rule reviewLargeOrder {
    when order.total.amount >= 1_000_000
    then approveOrder(order)
}
```

Các thao tác điều hướng:

1. Trên `Order` trong import: mở `sales/order.dsl` tại khai báo entity.
2. Trên `Money` trong field `total`: mở `common/money.dsl` tại type declaration.
3. Trên `total` trong `order.total`: mở field declaration trong entity `Order`.
4. Trên `approveOrder`: mở function hoặc action definition đã được resolve.
5. Trên `amount`: mở field declaration trong `Money`.

Nếu `approveOrder` có nhiều overload, type checker dùng kiểu `Order` của đối số để chọn đúng symbol. Nếu có nhiều implementation của một contract, Go to Definition có thể mở declaration và Go to Implementation hiển thị các implementation.

## 24. Kiểm thử Go to Definition

Kiểm thử cần xác nhận cả symbol resolution lẫn source location.

Các trường hợp quan trọng:

- Tham chiếu biến trong cùng block.
- Tham chiếu biến shadowed trong block lồng nhau.
- Tham số hàm và biến closure capture.
- Field access qua entity hoặc record.
- Type reference qua import.
- Qualified name và alias import.
- Symbol được re-export.
- Hai module có tên trùng.
- Overload được chọn theo kiểu đối số.
- Private symbol không thể truy cập từ module khác.
- Definition trong package dependency.
- Built-in symbol không có source file.
- Tệp chưa lưu và document version mới.
- File rename/delete và index invalidation.
- Nhiều implementation hoặc dynamic dispatch.
- Source map từ generated code về DSL.
- Unicode trong source range.
- Request bị hủy khi tài liệu đổi.

### 24.1. Kiểm thử resolver riêng

Có thể xây dựng test từ source fixture nhiều file, xác định vị trí reference và expected symbol ID/location. Test này không cần mở UI thật, giúp xác nhận semantics điều hướng.

### 24.2. Kiểm thử LSP integration

Gửi request `textDocument/definition` với URI và position, sau đó kiểm tra URI/range trả về. Cần dùng đúng quy ước vị trí và document version.

### 24.3. Kiểm thử trải nghiệm editor

Kiểm tra phím tắt, context menu, preview, nhiều kết quả, navigation history và hành vi khi không tìm thấy đích. UI cần phản hồi mà không bị treo khi workspace lớn.

## 25. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Tìm chuỗi thay vì resolve symbol | Mở nhầm tên trong comment, string hoặc scope khác | Dùng AST và semantic symbol reference |
| Dùng tên làm identity | Nhầm overload hoặc symbol cùng tên ở module khác | Dùng symbol ID và qualified name |
| Bỏ qua shadowing | Điều hướng đến biến ngoài thay vì binding gần nhất | Áp dụng đúng scope resolution |
| Chỉ index file đang mở | Không tìm được definition ở module khác | Workspace/dependency symbol index |
| Index không cập nhật khi file đổi | Điều hướng đến vị trí cũ | Versioned incremental indexing |
| Chọn kết quả đầu tiên khi ambiguous | Đích điều hướng không xác định | Trả nhiều location hoặc diagnostic ambiguity |
| Không giữ source range | Mở file nhưng không đến đúng khai báo | Lưu declaration range trong symbol metadata |
| Nhầm declaration với implementation | Người dùng không đến được code cần xem | Tách Go to Definition/Declaration/Implementation |
| Bỏ qua package version | Mở source của dependency sai version | Resolve theo dependency graph thực tế |
| Không hỗ trợ generated origin | Khó truy ngược generated code | Lưu source map và origin metadata |
| Đọc file disk thay vì document snapshot | Kết quả sai với nội dung chưa lưu | Dùng document version hiện tại |
| Không hủy request cũ | UI nhận location đã lỗi thời | Cancellation và version check |

## 26. Nguyên tắc thiết kế Go to Definition cho DSL

Khi xây dựng language service, có thể áp dụng các nguyên tắc sau:

1. **Dựa trên symbol resolution.** Điều hướng từ AST reference đã được phân giải, không tìm kiếm chuỗi đơn thuần.
2. **Dùng symbol identity ổn định.** Phân biệt tên trùng, overload và binding bị shadow.
3. **Tuân thủ scope và import semantics.** Resolver của editor phải dùng cùng quy tắc với compiler.
4. **Lưu source URI và range.** Định nghĩa phải có vị trí đủ chính xác để editor mở trực tiếp.
5. **Index toàn workspace và dependency.** Hỗ trợ nhiều file, module và package version.
6. **Cập nhật index theo document version.** Tránh kết quả stale khi người dùng đang chỉnh sửa.
7. **Phân biệt navigation modes.** Definition, declaration, implementation và type definition có mục tiêu riêng.
8. **Thể hiện ambiguity.** Trả danh sách khi có nhiều đích hợp lệ, không chọn ngẫu nhiên.
9. **Giữ source mapping.** Hỗ trợ truy ngược generated code và macro expansion.
10. **Tích hợp giao thức chuẩn.** Dùng LSP hoặc API editor nhất quán, hỗ trợ cancellation.
11. **Xử lý dependency an toàn.** Kiểm soát URI, path, symlink và nguồn bên ngoài.
12. **Thiết kế fallback trung thực.** Phân biệt semantic result với tìm kiếm văn bản hoặc candidate chưa chắc chắn.
13. **Kiểm thử cả resolver và UI.** Xác nhận đúng symbol, range và hành vi tương tác.

## 27. Kết luận

Đi tới định nghĩa là tính năng điều hướng từ một tham chiếu trong DSL đến khai báo hoặc định nghĩa của symbol tương ứng. Để làm đúng, editor cần hiểu token và AST tại vị trí con trỏ, áp dụng quy tắc scope/import/overload của ngôn ngữ, tìm symbol identity và mở source location chính xác.

Trong workspace nhiều module, tính năng này cần symbol index, incremental update, dependency resolution và source mapping. Language Server Protocol cung cấp cách chuẩn để editor gửi request và nhận location; các thao tác như Go to Declaration, Go to Implementation và Go to Type Definition có thể bổ sung những mục tiêu điều hướng khác nhau.

Một triển khai đáng tin cậy không dựa vào trùng khớp văn bản, không dùng index lỗi thời và không tự chọn khi có nhiều đích mơ hồ. Khi resolver, source range và editor integration cùng tuân theo semantics của DSL, người dùng có thể khám phá codebase nhanh hơn, hiểu quan hệ giữa các thành phần và sửa lỗi với ít thao tác thủ công hơn.
