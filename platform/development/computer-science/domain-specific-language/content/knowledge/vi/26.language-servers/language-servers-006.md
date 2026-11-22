# Symbol và workspace

## 1. Symbol là gì trong Language Server?

Trong một ngôn ngữ lập trình hoặc DSL (Domain-Specific Language), **symbol** là định danh đại diện cho một thành phần có ý nghĩa trong chương trình, chẳng hạn biến, hàm, kiểu dữ liệu, namespace, thuộc tính, hằng số, rule hoặc module. Symbol kết nối nơi một thành phần được khai báo với những nơi thành phần đó được sử dụng.

Ví dụ:

~~~text
namespace sales;

type Order {
    id: OrderId
    total: Money
}

function calculateTax(order: Order): Money {
    return order.total * taxRate;
}

rule review-large-order {
    when calculateTax(order) > money(1000000, VND)
    then requireManualReview(order.id)
}
~~~

Language server có thể nhận diện các symbol như sales, Order, id, total, calculateTax, order, taxRate, review-large-order và requireManualReview. Nó ghi nhận nơi khai báo, phạm vi nhìn thấy, kiểu hoặc chữ ký, module chứa symbol và những tham chiếu liên quan.

Nhờ thông tin đó, editor có thể hỗ trợ:

- Go to Definition: đi tới nơi khai báo symbol.
- Find References: tìm mọi vị trí sử dụng symbol.
- Rename: đổi tên symbol và các tham chiếu an toàn.
- Hover: hiển thị kiểu, chữ ký hoặc tài liệu.
- Completion: gợi ý symbol có thể truy cập tại vị trí hiện tại.
- Document Symbols: hiển thị outline của tệp đang mở.
- Workspace Symbols: tìm symbol trong nhiều tệp của dự án.
- Call Hierarchy: xem quan hệ gọi hàm nếu language server hỗ trợ.

Symbol vì vậy là mô hình ngữ nghĩa cốt lõi của Language Server. Nó giúp editor hiểu tên trong chương trình thay vì chỉ tìm kiếm chuỗi ký tự giống nhau.

## 2. Symbol khác token và text occurrence

Ba khái niệm này không đồng nhất:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Token | Đơn vị từ vựng được lexer nhận diện | IDENTIFIER với lexeme calculateTax |
| Text occurrence | Một đoạn văn bản có cùng ký tự | Từ calculateTax trong comment |
| Symbol | Thành phần được khai báo hoặc tham chiếu theo ngữ nghĩa | Hàm calculateTax có chữ ký cụ thể |

Một từ có thể xuất hiện nhiều lần nhưng không phải mọi lần đều tham chiếu cùng symbol. Ví dụ:

~~~text
let status = "PENDING";

function process(status: String) {
    let message = "status is " + status;
    return message;
}

// status is used by the workflow
~~~

Ở đây có một biến status bên ngoài, một tham số status trong hàm và hai lần xuất hiện trong string/comment. Hai định danh đầu là hai symbol khác nhau vì thuộc scope khác nhau. Các từ trong string và comment không phải tham chiếu symbol.

Tìm kiếm văn bản có thể tìm tất cả chuỗi status, nhưng Find References cần trả về các tham chiếu ngữ nghĩa của đúng symbol được chọn. Rename cũng phải đổi đúng symbol cùng các tham chiếu, không thay mọi chuỗi trùng tên.

## 3. Mô hình symbol

Một symbol thường cần lưu nhiều thông tin hơn tên:

| Thuộc tính | Mục đích |
|---|---|
| Name | Tên hiển thị hoặc tên khai báo |
| Kind | Loại symbol: function, variable, class, property, namespace... |
| Qualified name | Tên đầy đủ theo module hoặc namespace |
| Container | Scope hoặc symbol cha chứa khai báo |
| Location | Tệp và vùng nguồn của khai báo |
| Selection range | Vùng chính xác chứa tên symbol |
| Type/signature | Kiểu, tham số, kiểu trả về hoặc schema |
| Visibility | Phạm vi truy cập public, private, internal... |
| Modifiers | Static, readonly, deprecated, async... |
| Documentation | Mô tả hoặc liên kết tài liệu |
| Identity | Định danh nội bộ để phân biệt symbol |

Ví dụ mô hình khái niệm:

~~~text
Symbol
  id: symbol-1042
  name: calculateTax
  kind: Function
  qualifiedName: sales.tax.calculateTax
  container: sales.tax
  location:
    uri: file:///workspace/src/tax.dsl
    range: line 12, columns 1-13
  signature: (order: Order) -> Money
  visibility: public
~~~

Tên symbol có thể trùng nhau trong các scope khác nhau. Vì vậy, chỉ dùng name làm khóa duy nhất là không đủ. Một language server thường cần symbol identity hoặc khóa kết hợp từ module, scope, loại khai báo và vị trí.

## 4. Symbol kinds và cấu trúc phân cấp

Language server thường phân loại symbol theo kind. Các loại phổ biến:

- File hoặc module.
- Namespace hoặc package.
- Class, struct, record hoặc type.
- Interface hoặc trait.
- Enum và enum member.
- Function, method hoặc constructor.
- Variable, constant hoặc field.
- Property hoặc accessor.
- Parameter hoặc local variable.
- Event, operator hoặc macro nếu DSL hỗ trợ.

Một chương trình có thể được biểu diễn thành cây:

~~~text
Workspace
  Module: sales
    Namespace: tax
      Type: TaxPolicy
        Field: rate
        Method: calculate
      Function: calculateTax
    Rule: high-value-order
~~~

Cấu trúc này hữu ích cho Document Outline và Workspace Symbol search. Người dùng có thể mở rộng namespace, type hoặc module để tìm thành phần con.

Không phải mọi symbol đều cần xuất hiện trong outline. Một local variable có thể hữu ích cho Go to Definition và Rename nhưng không nhất thiết cần hiển thị ở cấp workspace. Language server nên phân biệt symbol dùng cho phân tích nội bộ với symbol được công bố cho editor.

## 5. Document scope và workspace scope

Một language server thường làm việc ở hai phạm vi lớn:

### 5.1. Document scope

Document scope là phạm vi của một tài liệu đang mở hoặc một tệp nguồn cụ thể. Nó chứa:

- Token và syntax tree của tệp.
- Các khai báo trong tệp.
- Scope cục bộ và block lồng nhau.
- Tham chiếu tới symbol bên ngoài.
- Diagnostic và source range của tài liệu.

Ví dụ, trong một hàm, tham số và biến cục bộ có thể chỉ nhìn thấy trong thân hàm hoặc block con. Khi document thay đổi, language server cần cập nhật cấu trúc của tệp đó.

### 5.2. Workspace scope

Workspace scope bao gồm nhiều tệp và module thuộc dự án. Nó có thể chứa:

- Tất cả module của project.
- Các symbol được export từ từng module.
- Import và dependency giữa các module.
- Symbol từ thư viện hoặc package phụ thuộc.
- Cấu hình build và language version.
- Workspace folders hoặc project roots.

Một symbol được khai báo trong file A có thể được tham chiếu từ file B nếu module và visibility cho phép. Để hỗ trợ điều đó, language server cần index workspace hoặc có cơ chế tra cứu symbol tương đương.

### 5.3. Phạm vi không đồng nghĩa với thư mục

Workspace không nhất thiết chỉ là một thư mục vật lý. Một project có thể gồm nhiều source root, generated source, package ngoài, file cấu hình và thư viện. Một workspace cũng có thể chứa nhiều project độc lập.

Language server cần lấy cấu trúc dự án từ build file, manifest, cấu hình DSL hoặc quy ước workspace. Chỉ quét mọi file trong một thư mục có thể đưa nhầm file vào project hoặc bỏ sót module nằm ngoài root.

## 6. Scope và quy tắc nhìn thấy symbol

Scope xác định nơi một symbol có thể được tham chiếu. Các loại scope thường gặp:

- Global hoặc workspace scope.
- Module hoặc namespace scope.
- Type scope.
- Function scope.
- Block scope.
- Parameter scope.
- Scope riêng của lambda hoặc closure.

Ví dụ:

~~~text
let taxRate = 0.08;

function calculate(order: Order) {
    let subtotal = order.total;

    if (order.isTaxable) {
        let tax = subtotal * taxRate;
        return tax;
    }

    return 0;
}
~~~

taxRate được khai báo ở scope ngoài và có thể nhìn thấy trong hàm. subtotal chỉ có ý nghĩa trong calculate. tax chỉ nhìn thấy trong block if nếu DSL dùng block scope.

### 6.1. Lexical scope

Với lexical scoping, khả năng nhìn thấy symbol được xác định từ cấu trúc khai báo trong source. Khi phân giải một tên, language server tìm từ scope hiện tại rồi đi dần ra các scope cha theo quy tắc của ngôn ngữ.

Pseudocode:

~~~text
resolve(name, currentScope):
    scope = currentScope
    while scope exists:
        if scope contains a visible declaration named name:
            return that declaration
        scope = scope.parent
    return unresolved
~~~

Đây là mô hình giản lược. Thực tế còn phải xét overload, import, namespace, generic parameter, visibility và các quy tắc ưu tiên.

### 6.2. Shadowing

Một khai báo bên trong có thể che khuất khai báo cùng tên ở scope ngoài:

~~~text
let limit = 100;

function check() {
    let limit = 50;
    return limit;
}
~~~

Trong hàm, limit tham chiếu tới biến cục bộ có giá trị 50. Symbol index phải giữ cả hai khai báo và resolver phải chọn đúng symbol theo vị trí tham chiếu.

### 6.3. Overloading

Một ngôn ngữ có thể cho phép nhiều hàm cùng tên nhưng khác chữ ký:

~~~text
function format(value: Integer): String;
function format(value: Date): String;
~~~

Tên format không xác định duy nhất một hàm. Resolver cần xét số lượng và kiểu đối số để chọn overload phù hợp. Find References và Rename có thể áp dụng cho toàn bộ nhóm overload theo chính sách ngôn ngữ, hoặc cho từng declaration nếu ngôn ngữ phân biệt chúng.

## 7. Qualified names và namespace

Qualified name là tên đầy đủ xác định vị trí của symbol trong namespace hoặc module:

~~~text
sales.tax.calculateTax
inventory.stock.available
~~~

Qualified name hữu ích khi:

- Nhiều module có symbol cùng tên.
- Import cần xác định nguồn.
- Workspace symbol search cần phân biệt kết quả.
- Runtime cần liên kết function hoặc type.
- Rename hoặc refactor phải cập nhật namespace path.

Language server cần lưu cả tên ngắn và tên đầy đủ. Tên ngắn thuận tiện cho completion và hiển thị; tên đầy đủ giúp phân biệt symbol và giải quyết import.

Không phải mọi ngôn ngữ đều dùng dấu chấm cho qualified name. Một số dùng dấu gạch chéo, dấu hai chấm hoặc package path. Resolver phải theo grammar và module system của DSL thay vì giả định một cách viết cố định.

## 8. Import và phân giải symbol giữa các module

Import cho phép một module sử dụng symbol được export từ module khác:

~~~text
import sales.tax.calculateTax;
import inventory.Order;

rule review {
    when calculateTax(order) > money(1000000, VND)
    then requireManualReview(order.id)
}
~~~

Khi xử lý import, language server cần:

1. Parse đường dẫn module hoặc qualified name.
2. Xác định module đích theo cấu hình project.
3. Tải hoặc tìm index của module.
4. Kiểm tra symbol có được export và có visibility phù hợp.
5. Gắn import reference với symbol identity.
6. Phát diagnostic nếu module hoặc symbol không tồn tại.

### 8.1. Import alias

Alias tạo tên cục bộ cho symbol:

~~~text
import sales.tax.calculateTax as taxForOrder;
~~~

Trong file hiện tại, taxForOrder là tên dùng để tham chiếu; symbol gốc vẫn là calculateTax. Rename cần hiểu alias là một binding riêng liên kết tới symbol gốc. Tùy yêu cầu người dùng, thao tác rename có thể đổi tên khai báo gốc và cập nhật alias, hoặc chỉ đổi tên alias tại module nhập.

### 8.2. Wildcard import

~~~text
import sales.tax.*;
~~~

Wildcard import có thể đưa nhiều symbol vào scope. Language server cần biết tập export của module và giải quyết xung đột nếu hai module cùng export tên giống nhau.

Để completion và diagnostics ổn định, nên xác định rõ thứ tự ưu tiên giữa local declaration, explicit import, wildcard import và built-in symbol.

### 8.3. Circular dependency

Nếu module A import B và B import A, language server cần xử lý graph phụ thuộc có chu trình. Một số ngôn ngữ cho phép khai báo type vòng nhưng không cho phép khởi tạo hoặc thực thi vòng.

Indexing có thể dùng hai pha:

1. Thu thập declaration và module identity của mọi file.
2. Resolve reference và dependency sau khi symbol skeleton đã có.

Cách này tránh yêu cầu một module phải được phân tích hoàn chỉnh trước khi module khác có thể nhìn thấy declaration của nó. Quy tắc hợp lệ của circular import vẫn do ngôn ngữ quyết định.

## 9. Workspace model

Workspace model mô tả những gì language server xem là một dự án và cách các file liên hệ với nhau. Một model có thể gồm:

~~~text
Workspace
  id: workspace-main
  folders:
    - /project/app
    - /project/shared
  projects:
    - app
    - shared
  sourceRoots:
    - app/src
    - shared/src
  dependencies:
    - standard-library
    - domain-types
  configuration:
    languageVersion: 2
    moduleResolution: strict
~~~

Workspace model có thể được tạo từ:

- Workspace folder do editor gửi qua LSP.
- Build system như Gradle, Maven hoặc công cụ riêng.
- Manifest của DSL.
- File cấu hình project.
- Package manager hoặc dependency lockfile.

Language server nên phân biệt workspace root, project root và source root. Workspace root là phạm vi editor mở; project root là đơn vị build hoặc cấu hình; source root là nơi chứa source module. Chúng có thể trùng nhau nhưng không bắt buộc.

## 10. Workspace folders và multi-root workspace

Một editor có thể mở nhiều thư mục trong cùng workspace. Trong LSP, client có thể cung cấp danh sách workspace folders và thông báo khi danh sách thay đổi.

Ví dụ:

~~~text
Workspace
  - services/orders
  - services/billing
  - libraries/common
~~~

Language server cần quyết định:

- Mỗi folder là một project riêng hay một phần của project chung?
- Có chia sẻ symbol index giữa các folder không?
- Import từ folder này sang folder khác được phép theo dependency nào?
- Cấu hình language version có giống nhau không?
- Rename có được phép sửa file ở nhiều folder không?
- Nếu hai folder có module cùng tên, cách phân giải là gì?

Không nên giả định một language server process luôn chỉ phục vụ một root. Nếu server hỗ trợ multi-root, mọi index key, cache và diagnostic cần được gắn với workspace/project phù hợp.

## 11. Workspace indexing

Workspace indexing là quá trình thu thập thông tin từ các file trong dự án để tạo chỉ mục symbol và quan hệ tham chiếu. Index cho phép language server trả lời truy vấn trên nhiều file mà không phải parse lại toàn bộ workspace mỗi lần người dùng yêu cầu.

Một pipeline indexing:

~~~mermaid
flowchart TD
    A["Workspace folders"] --> B["Discover source files"]
    B --> C["Read project configuration"]
    C --> D["Parse documents"]
    D --> E["Extract declarations"]
    E --> F["Build symbol index"]
    F --> G["Resolve imports and references"]
    G --> H["Publish workspace features"]
~~~

Các bước có thể gồm:

1. Xác định file nguồn thuộc project.
2. Loại trừ build output, dependency cache và file không liên quan.
3. Đọc cấu hình, module path và language version.
4. Parse file hoặc dùng cache AST.
5. Thu thập declaration.
6. Tạo symbol index theo tên, module và loại.
7. Resolve import và reference.
8. Lưu metadata cần cho definition, references, rename và workspace search.

### 11.1. File discovery

Không nên quét mọi file không phân biệt. Workspace có thể chứa:

- Source DSL.
- Generated source.
- Build output.
- Vendor dependencies.
- Test fixtures.
- Documentation.
- File tạm hoặc cache.

Project configuration cần xác định file nào thuộc ngôn ngữ và phạm vi indexing. Bỏ qua build directory thường giúp giảm thời gian và tránh index cả artifact được sinh từ source đã có.

### 11.2. Index declarations trước references

Một chiến lược hữu ích là index declarations trước, rồi resolve references sau. Điều này cho phép file A tham chiếu symbol khai báo trong file B ngay cả khi B chưa được xử lý trước A.

Nếu parser có thể tạo declaration outline từ file lỗi, index vẫn có thể giữ một phần symbol để hỗ trợ editor trong lúc người dùng đang sửa.

### 11.3. Symbol index

Index có thể hỗ trợ nhiều truy vấn:

- Tra cứu symbol theo tên hoặc qualified name.
- Tra cứu declaration theo symbol identity.
- Tìm references theo symbol identity.
- Tìm symbol theo module hoặc container.
- Tìm export của module.
- Tìm file phụ thuộc vào một module.

Với workspace lớn, nên dùng map hoặc database/index phù hợp thay vì duyệt toàn bộ danh sách symbol cho mọi request.

## 12. LSP DocumentSymbol và WorkspaceSymbol

Language Server Protocol cung cấp các request để editor lấy danh sách symbol.

### 12.1. DocumentSymbol

textDocument/documentSymbol trả về các symbol trong tài liệu hiện tại. Kết quả thường có cấu trúc phân cấp:

~~~text
Document
  Namespace: sales
    Type: Order
      Field: id
      Field: total
    Function: calculateTax
  Rule: high-value-order
~~~

DocumentSymbol có thể chứa:

- name: tên symbol.
- detail: thông tin phụ như kiểu hoặc chữ ký.
- kind: loại symbol.
- tags: trạng thái như deprecated nếu được hỗ trợ.
- range: vùng nguồn bao trọn khai báo.
- selectionRange: vùng tên được chọn khi người dùng điều hướng.
- children: các symbol con.

range và selectionRange có mục đích khác nhau. range có thể bao gồm toàn bộ thân function; selectionRange chỉ bao gồm tên function. Nếu selectionRange quá rộng hoặc sai vị trí, thao tác chọn symbol trong outline có thể gây trải nghiệm khó chịu.

### 12.2. WorkspaceSymbol

workspace/symbol cho phép tìm symbol trong workspace theo query. Kết quả thường chứa tên, kind, container và location của symbol.

Ví dụ người dùng gõ calculateTax, server có thể trả:

~~~text
calculateTax
  Function
  sales.tax
  src/tax.dsl:12
~~~

WorkspaceSymbol thường được dùng cho chức năng Go to Symbol in Workspace. Kết quả nên được xếp hạng phù hợp, loại bỏ duplicate không cần thiết và có vị trí đủ chính xác để editor mở đúng file.

### 12.3. DocumentSymbol dạng cây và dạng phẳng

LSP có dạng DocumentSymbol phân cấp và dạng SymbolInformation phẳng trong một số tương thích cũ. Server cần hỗ trợ theo capability của client và phiên bản giao thức. Nếu client không hỗ trợ hierarchical document symbols, server có thể trả danh sách phẳng có containerName.

## 13. Go to Definition và Find References

### 13.1. Go to Definition

Khi người dùng đặt con trỏ trên một identifier, editor gửi textDocument/definition. Language server:

1. Xác định token tại vị trí con trỏ.
2. Tìm binding hoặc reference node tương ứng.
3. Resolve reference thành symbol identity.
4. Trả location hoặc location link của declaration.

Ví dụ:

~~~text
// file: rules/approval.dsl
import sales.tax.calculateTax;

rule approval {
    when calculateTax(order) > threshold
    then approve(order)
}
~~~

Khi con trỏ nằm trên calculateTax trong lời gọi, server điều hướng tới declaration trong sales/tax.dsl.

### 13.2. Find References

textDocument/references tìm các vị trí tham chiếu tới symbol được chọn. Server có thể bao gồm hoặc loại trừ declaration theo tùy chọn includeDeclaration.

Một reference record nội bộ có thể gồm:

~~~text
Reference
  symbolId: symbol-1042
  uri: file:///workspace/rules/approval.dsl
  range: line 4, columns 10-22
  role: call
~~~

Reference index nên lưu symbol identity thay vì chỉ lưu tên. Nếu chỉ tìm text, kết quả sẽ bao gồm comment, string và các symbol cùng tên trong scope khác.

### 13.3. References chưa resolve

Khi người dùng đang gõ hoặc dependency chưa tải, reference có thể tạm thời chưa resolve. Language server có thể lưu unresolved reference và thử resolve lại khi index hoặc cấu hình thay đổi. Diagnostic cần phân biệt unresolved tạm thời với tên chắc chắn không tồn tại.

## 14. Rename symbol

Rename là một thao tác refactoring có rủi ro nếu chỉ thay chuỗi văn bản. Một rename an toàn thường gồm:

1. Xác định symbol tại vị trí con trỏ.
2. Kiểm tra tên mới có hợp lệ theo grammar không.
3. Tìm tất cả references của đúng symbol.
4. Kiểm tra xung đột trong scope và module.
5. Tạo WorkspaceEdit chứa các text edits.
6. Trả edit cho client để người dùng áp dụng.

Ví dụ đổi tên calculateTax thành computeTax:

~~~text
Before:
import sales.tax.calculateTax;
let tax = calculateTax(order);

After:
import sales.tax.computeTax;
let tax = computeTax(order);
~~~

Nếu có một function calculateTax khác trong module khác, nó không được đổi trừ khi cùng symbol identity theo quy tắc của ngôn ngữ.

### 14.1. Prepare rename

Một số client hỗ trợ prepareRename để server xác nhận vị trí hiện tại có thể rename và trả range hoặc placeholder. Điều này giúp editor không mở hộp nhập tên mới tại một vị trí không phải symbol.

### 14.2. Xung đột tên

Tên mới có thể trùng với biến, hàm hoặc import đã có trong scope:

~~~text
let tax = 10;
let amount = 100;
~~~

Nếu đổi amount thành tax, có thể tạo xung đột. Server nên kiểm tra theo quy tắc scope và trả lỗi hoặc từ chối rename thay vì tạo source không hợp lệ.

### 14.3. Rename qua nhiều file

Rename workspace có thể sửa nhiều tài liệu. WorkspaceEdit cần dùng URI và range chính xác. Với tài liệu đang mở có thay đổi chưa lưu, server cần dựa trên document version hoặc cơ chế đồng bộ để tránh áp dụng edit lên nội dung khác với nội dung đã phân tích.

## 15. Symbol identity và reference graph

Một symbol identity cần phân biệt các khai báo cùng tên. Có thể xây dựng từ:

- Project hoặc workspace identity.
- Module path.
- Container hoặc scope identity.
- Declaration kind.
- Signature hoặc overload key.
- Stable declaration ID nếu ngôn ngữ có.

Không nên chỉ dùng vị trí dòng/cột làm identity lâu dài vì thêm dòng ở đầu file sẽ làm vị trí thay đổi. Tuy vậy, source location vẫn hữu ích để định vị khai báo hiện tại.

Reference graph mô tả quan hệ giữa symbol và nơi sử dụng:

~~~mermaid
flowchart LR
    A["Function: calculateTax"] --> B["Call in approval.dsl"]
    A --> C["Call in invoice.dsl"]
    A --> D["Import in report.dsl"]
    E["Type: Order"] --> F["Parameter in tax.dsl"]
    E --> G["Variable in approval.dsl"]
~~~

Graph này có thể hỗ trợ:

- Find References.
- Rename.
- Call hierarchy.
- Dead code analysis.
- Dependency visualization.
- Impact analysis khi thay đổi API.

Một số reference chỉ có thể xác định sau type checking hoặc overload resolution. Vì vậy, index cần hỗ trợ trạng thái unresolved hoặc ambiguous thay vì ép mọi tên thành một symbol.

## 16. Workspace dependency graph

Ngoài reference giữa symbol, workspace còn có graph phụ thuộc giữa module hoặc project:

~~~text
app
  -> sales-domain
  -> shared-types

sales-domain
  -> shared-types

reporting
  -> sales-domain
  -> shared-types
~~~

Dependency graph giúp language server:

- Xác định module nào cần re-index khi dependency đổi.
- Phân giải import và package.
- Tìm project chứa declaration.
- Hạn chế phân tích các module không liên quan.
- Phát hiện dependency cycle nếu ngôn ngữ hoặc build system không cho phép.

Dependency giữa module khác với reference giữa symbol. Một module có thể phụ thuộc module khác mà không tham chiếu mọi symbol trong đó. Cần giữ hai khái niệm riêng để cập nhật index hiệu quả.

## 17. Cập nhật workspace khi file thay đổi

Editor gửi các notification khi tài liệu mở, thay đổi, lưu hoặc đóng. Workspace cũng có thể thay đổi khi file được tạo, đổi tên hoặc xóa.

Một language server cần phối hợp:

- didOpen: nạp văn bản và tạo document state.
- didChange: áp dụng thay đổi và cập nhật parse/index.
- didSave: xử lý nội dung đã lưu nếu server cần.
- didClose: giải phóng state riêng của tài liệu nếu phù hợp.
- File watcher: phát hiện thay đổi trên filesystem.
- Workspace folder change: cập nhật root và project membership.

### 17.1. Open document và file trên đĩa

Nội dung trong editor có thể khác file đã lưu. Khi document đang mở, language server thường phải xem nội dung đồng bộ từ client là nguồn hiện hành cho các tính năng editor. Nếu chỉ đọc file trên đĩa, definition hoặc references có thể không phản ánh thay đổi chưa lưu.

Khi document đóng, server có thể quay lại dùng nội dung trên filesystem hoặc cache đã xác thực.

### 17.2. Incremental indexing

Không nên rebuild toàn bộ workspace sau mỗi phím. Có thể:

1. Parse lại document đã thay đổi.
2. Tạo declaration index mới cho document đó.
3. So sánh export hoặc symbol signature cũ và mới.
4. Nếu public symbol không đổi, chỉ cập nhật reference trong document.
5. Nếu public interface thay đổi, đánh dấu module phụ thuộc cần resolve lại.
6. Chạy cập nhật ở background và công bố index mới theo cách nhất quán.

### 17.3. File create, rename và delete

Khi file được đổi tên, URI cũ không còn hợp lệ. Language server cần cập nhật module path, file index, import path và source locations. Nếu file bị xóa, phải loại bỏ declaration và references của nó, sau đó phát diagnostic cho những nơi còn phụ thuộc.

## 18. File watchers và phạm vi quét

Language server có thể đăng ký file watcher hoặc nhận thông báo từ client. Watcher giúp cập nhật index khi file thay đổi bên ngoài editor.

Nên lọc theo:

- File extension của DSL.
- Source root.
- Include/exclude pattern.
- Generated directory.
- Vendor và dependency cache.
- File tạm hoặc backup.

Theo dõi toàn bộ filesystem có thể tốn tài nguyên và tạo nhiều event không liên quan. Cấu hình watcher nên bám theo workspace model và project configuration.

Một số filesystem gửi nhiều event cho một lần lưu hoặc đổi tên. Server có thể cần debounce hoặc gom event, nhưng phải bảo đảm không bỏ sót trạng thái cuối.

## 19. Workspace configuration và dependency resolution

Symbol index chỉ chính xác khi language server biết cách project được cấu hình. Các thông tin quan trọng:

- Language version.
- Module search path.
- Source roots.
- Dependency và package versions.
- Conditional compilation hoặc feature flags.
- Generated source roots.
- Case sensitivity của module path.
- Quy tắc visibility và export.

Ví dụ:

~~~yaml
languageVersion: 2
sourceRoots:
  - src
  - generated/dsl
dependencies:
  - name: standard-library
    version: 2.1
  - name: sales-domain
    version: 4.0
exclude:
  - build
  - .cache
~~~

Đây là cấu hình minh họa. Language server có thể lấy thông tin tương đương từ build system thay vì yêu cầu một file riêng.

Nếu cấu hình thay đổi, server có thể phải xây dựng lại module graph và symbol index. Nên phát hiện cấu hình thay đổi qua watcher hoặc notification và thông báo trạng thái indexing cho client nếu cần.

## 20. Workspace symbols trong LSP

Workspace symbol search thường được gọi khi người dùng muốn tìm function, class, rule hoặc type ở bất kỳ đâu trong project.

Request có thể chứa query dạng chuỗi. Server có thể hỗ trợ:

- Prefix matching.
- Substring matching.
- Fuzzy matching.
- Tìm theo qualified name.
- Xếp hạng theo mức độ phù hợp và phạm vi hiện tại.

Ví dụ query tax có thể tìm:

~~~text
calculateTax      Function   sales.tax
TaxPolicy         Type       sales.policy
taxRate           Variable   sales.config
~~~

### 20.1. Ranking

Khi có nhiều kết quả, thứ tự nên hữu ích:

1. Symbol khớp chính xác.
2. Symbol có prefix khớp.
3. Symbol gần với project/module hiện tại.
4. Symbol có tên gần theo fuzzy matching.
5. Dependency hoặc thư viện ngoài.

Đây là chính sách xếp hạng, không phải quy tắc bắt buộc của LSP. Nên tránh trả quá nhiều kết quả trùng hoặc symbol từ build output.

### 20.2. Partial results và cancellation

Workspace lớn có thể có hàng trăm nghìn symbol. Nếu giao thức và client hỗ trợ, server có thể trả partial result hoặc progress trong lúc tìm kiếm. Request cũ nên được hủy khi người dùng tiếp tục nhập query mới.

Server cần tôn trọng cancellation để không tiêu tốn CPU cho các truy vấn không còn cần thiết. Nếu chỉ hỗ trợ một truy vấn đồng thời, cần tránh để truy vấn cũ chặn request mới trong thời gian dài.

## 21. Workspace symbol index và cache

Index có thể được giữ trong bộ nhớ, lưu trên đĩa hoặc kết hợp cả hai.

| Chiến lược | Ưu điểm | Đánh đổi |
|---|---|---|
| In-memory index | Truy vấn nhanh, cập nhật trực tiếp | Tốn RAM, mất khi server dừng |
| Disk cache | Khởi động nhanh hơn sau lần đầu | Cần version và invalidation |
| Lazy indexing | Không phân tích file chưa cần | Kết quả đầu tiên có thể chậm |
| Eager indexing | Sẵn sàng cho truy vấn toàn workspace | Tốn thời gian khởi động |
| Hybrid | Cân bằng tốc độ và tài nguyên | Phức tạp hơn trong quản lý trạng thái |

Cache key cần xét những yếu tố ảnh hưởng kết quả:

- File content hash hoặc timestamp đáng tin cậy.
- Language server/parser version.
- Language version.
- Project configuration.
- Dependency versions.
- Schema của symbol index.

Nếu bỏ qua cấu hình hoặc phiên bản grammar, server có thể nạp index cũ và đưa ra definition sai dù source không đổi.

### 21.1. Index generation và tính nhất quán

Khi cập nhật nhiều file, server không nên để một request đọc nửa index cũ và nửa index mới. Có thể xây dựng index generation mới ở background rồi thay thế snapshot khi hoàn tất.

Mỗi request có thể đọc một snapshot nhất quán. Cách này giúp references và workspace search không trộn lẫn symbol đã bị xóa với symbol mới.

## 22. Multi-project và dependency ngoài workspace

Một workspace có thể chứa nhiều project với cấu hình khác nhau. Language server cần biết project nào sở hữu file và dependency nào được phép nhìn thấy.

Ví dụ:

~~~text
workspace/
  application/
    project.dsl.yml
    src/
  domain/
    project.dsl.yml
    src/
  tools/
    project.dsl.yml
    src/
~~~

Một file trong application có thể phụ thuộc domain nhưng không nhất thiết được import symbol từ tools. Dependency resolution phải tuân theo build graph, không chỉ dựa trên việc file tồn tại trong cùng workspace.

Với package ngoài, server có thể dùng:

- Package metadata.
- Export index được đóng gói.
- Source archive.
- Generated symbol database.
- API stub hoặc declaration file.

Không nhất thiết phải parse toàn bộ source của dependency nếu package cung cấp symbol metadata đủ dùng. Điều này giúp giảm thời gian index và bộ nhớ.

## 23. Symbol trong generated source

DSL có thể sinh mã hoặc declaration file. Language server cần quyết định generated source có tham gia workspace symbol index hay không.

Một số trường hợp:

- Generated source là nơi debugger cần điều hướng.
- Generated declaration cung cấp API của module.
- Generated code chỉ là artifact tạm và trùng symbol với DSL source.
- Người dùng không nên rename trực tiếp generated symbol.

Có thể gắn quan hệ source-to-generated:

~~~text
DSL declaration:
  rules/approval.dsl:12

Generated declaration:
  build/generated/ApprovalRule.java:30

Origin:
  symbol-approval-01
~~~

Khi editor chọn symbol trong generated file, language server có thể điều hướng về DSL source nếu có source map. Nếu generated source được index như một file bình thường mà không có mapping, kết quả WorkspaceSymbol có thể trùng với symbol DSL gốc.

Nên có chính sách rõ:

- Có index generated source hay không.
- Generated symbol được hiển thị hay ẩn.
- Definition ưu tiên source DSL hay generated file.
- Rename có sửa DSL source, generated source hay cả hai.
- Generated file có được phép chỉnh sửa thủ công không.

## 24. WorkspaceEdit và thao tác trên nhiều tài liệu

Một số chức năng như Rename hoặc code action có thể sửa nhiều file. LSP biểu diễn thay đổi bằng WorkspaceEdit, gồm các text edit theo URI và range hoặc document changes có version.

Một thao tác đổi tên module có thể cần:

- Đổi tên file.
- Cập nhật import.
- Cập nhật qualified name.
- Sửa manifest hoặc dependency reference.
- Cập nhật generated artifact nếu có.

Server cần kiểm tra quyền và xung đột trước khi gửi edit. Client có thể áp dụng edit hoặc yêu cầu xác nhận tùy khả năng. Nếu file đã thay đổi sau khi server phân tích, version check giúp tránh ghi đè nội dung mới.

## 25. Xử lý lỗi và trạng thái workspace

Workspace có thể tạm thời ở trạng thái chưa hoàn chỉnh:

- Build file không hợp lệ.
- Dependency chưa tải.
- Một source file đang được sửa dở.
- Project root chưa được xác định.
- Index đang chạy.
- Generated source chưa được tạo.
- File bị xóa hoặc đổi tên giữa lúc request đang xử lý.

Language server nên phân biệt:

- Symbol không tồn tại chắc chắn.
- Symbol chưa được resolve vì dependency đang thiếu.
- Index chưa hoàn tất.
- File chưa được parse thành công.
- Workspace configuration lỗi.

Nếu mọi trạng thái đều được báo là undefined symbol, người dùng sẽ nhận nhiều diagnostic giả khi project vừa mở hoặc dependency đang tải.

Có thể cung cấp progress notification hoặc trạng thái indexing. Những tính năng chỉ cần document scope, như lexical highlighting hoặc một phần completion, vẫn có thể hoạt động trước khi workspace index hoàn tất.

## 26. Hiệu năng và khả năng mở rộng

Workspace lớn có thể có hàng nghìn file và hàng triệu symbol. Language server cần tối ưu cả indexing lẫn request latency.

Một số kỹ thuật:

1. Incremental parsing và indexing.
2. Chỉ re-resolve module phụ thuộc khi public interface thay đổi.
3. Dùng cache AST và symbol index có version.
4. Index theo project hoặc module thay vì một map toàn cục không phân vùng.
5. Lazy load dependency metadata.
6. Dùng snapshot hoặc read-copy-update để request đọc index nhất quán.
7. Hủy request cũ khi client không còn cần kết quả.
8. Giới hạn kết quả WorkspaceSymbol và hỗ trợ partial result.
9. Theo dõi memory, indexing time và request latency.

Không phải mọi file thay đổi đều yêu cầu re-index toàn workspace. Nếu một biến cục bộ đổi tên, thường chỉ document đó cần cập nhật. Nếu public type hoặc exported function đổi chữ ký, các module phụ thuộc có thể cần resolve lại.

## 27. Bảo mật và quyền truy cập workspace

Workspace có thể chứa source code, file cấu hình, secret hoặc dữ liệu nhạy cảm. Language server cần:

- Chỉ đọc file trong phạm vi workspace hoặc dependency được phép.
- Tôn trọng ignore/exclude configuration.
- Không theo symlink ra ngoài workspace nếu policy không cho phép.
- Không thực thi build script hoặc plugin tùy ý chỉ để index.
- Không gửi source hoặc symbol metadata tới dịch vụ ngoài nếu chưa được phép.
- Kiểm soát URI scheme và file access.
- Không ghi nội dung nhạy cảm vào log.

Nếu language server chạy trong môi trường remote hoặc multi-tenant, workspace identity và index cache phải được cô lập để tránh lộ symbol giữa các project hoặc người dùng.

## 28. Kiểm thử symbol và workspace features

Language server cần được kiểm thử theo từng lớp:

### 28.1. Symbol extraction

Tạo file có namespace, type, function, field, parameter, local variable và rule. Xác nhận symbol name, kind, container và source range.

### 28.2. Scope resolution

Kiểm tra lexical scope, shadowing, import alias, wildcard import và overload. Xác nhận reference được liên kết đúng symbol.

### 28.3. Document symbols

Xác nhận cây DocumentSymbol có parent/child đúng, range bao trọn khai báo và selectionRange chỉ chứa tên.

### 28.4. Workspace symbols

Tạo nhiều file và module. Kiểm tra query prefix, substring hoặc fuzzy theo chính sách server, container và location.

### 28.5. Definition và references

Đặt con trỏ trên identifier, kiểm tra definition trả đúng file và references chỉ gồm các tham chiếu ngữ nghĩa.

### 28.6. Rename

Kiểm tra rename cập nhật khai báo, references và import liên quan; không đổi string, comment hoặc symbol trùng tên ở scope khác. Kiểm tra xung đột và document version.

### 28.7. Incremental update

Thay đổi một declaration, xóa file, đổi tên file và thay cấu hình. Xác nhận index được cập nhật và không còn kết quả cũ.

### 28.8. Multi-root workspace

Mở nhiều project, kiểm tra symbol cùng tên, dependency và quyền rename qua các root.

### 28.9. Large workspace và cancellation

Kiểm tra thời gian indexing, memory, partial result và việc hủy truy vấn không còn cần thiết.

## 29. Những lỗi thiết kế thường gặp

### Dùng tên làm symbol identity

Hai biến cùng tên ở scope khác nhau bị gộp. Dùng identity riêng và giữ scope/container.

### Tìm references bằng text search

Comment, string và symbol cùng tên bị đưa vào kết quả. Resolve reference thành symbol trước khi tìm.

### Chỉ index file đang mở

Definition hoặc WorkspaceSymbol không tìm được declaration ở file khác. Xây dựng workspace index hoặc index theo nhu cầu.

### Quét toàn bộ workspace sau mỗi lần gõ

Editor bị chậm và tốn CPU. Dùng incremental indexing, dependency graph và cache.

### Không theo dõi cấu hình project

Import được resolve theo search path sai hoặc language version sai. Đưa cấu hình vào workspace model và cache key.

### Không phân biệt document scope với workspace scope

Completion có thể gợi ý symbol ngoài project hoặc bỏ sót symbol import. Áp dụng quy tắc visibility và dependency rõ ràng.

### Index generated source trùng lặp

Một declaration xuất hiện hai lần trong WorkspaceSymbol. Gắn source mapping và quy tắc ưu tiên generated artifact.

### Áp dụng kết quả bất đồng bộ lỗi thời

Request cũ ghi đè index hoặc semantic state mới. Dùng document version, index generation và cancellation.

### Không xử lý multi-root

Cache và symbol cùng tên bị lẫn giữa các project. Phân vùng index theo workspace/project identity.

## 30. Quy trình xây dựng symbol và workspace support

Khi triển khai symbol support cho DSL, có thể thực hiện theo trình tự:

1. **Định nghĩa symbol kinds.** Liệt kê declaration và symbol có ý nghĩa trong ngôn ngữ.
2. **Thiết kế symbol identity.** Phân biệt tên trùng, overload và khai báo trong scope khác nhau.
3. **Xây dựng scope model.** Xác định lexical scope, visibility, shadowing và import precedence.
4. **Xây dựng document symbol tree.** Giữ source range và selection range chính xác.
5. **Xác định workspace model.** Project root, source root, module, dependency và multi-root.
6. **Thiết kế index.** Thu thập declaration, export, reference và dependency.
7. **Tích hợp LSP requests.** DocumentSymbol, WorkspaceSymbol, Definition, References và Rename.
8. **Cập nhật incremental.** Đồng bộ document, file watcher, file rename/delete và configuration change.
9. **Quản lý cache và snapshot.** Gắn version, giữ consistency và hỗ trợ cancellation.
10. **Kiểm thử và quan sát.** Đo indexing, memory, request latency và độ chính xác của symbol resolution.

Nên bắt đầu với DocumentSymbol và Go to Definition trong một file, sau đó mở rộng sang workspace index, references và rename. Khi quy mô project tăng, bổ sung dependency graph, cache và incremental indexing dựa trên nhu cầu đo được.

## 31. Ví dụ end-to-end: tìm symbol trong workspace

Giả sử workspace có:

~~~text
project/
  dsl-project.yml
  src/
    sales/
      tax.dsl
      approval.dsl
    shared/
      money.dsl
~~~

Trong tax.dsl:

~~~text
namespace sales.tax;

function calculateTax(order: Order): Money {
    return order.total * taxRate;
}
~~~

Trong approval.dsl:

~~~text
namespace sales.approval;

import sales.tax.calculateTax;

rule review {
    when calculateTax(order) > money(1000000, VND)
    then requireManualReview(order.id)
}
~~~

Language server có thể thực hiện:

1. Đọc dsl-project.yml để xác định source root và module path.
2. Index declaration calculateTax trong tax.dsl.
3. Index declaration review trong approval.dsl.
4. Resolve import calculateTax sang symbol identity của hàm trong tax.dsl.
5. Resolve lời gọi calculateTax trong điều kiện.
6. Khi người dùng gọi Go to Definition, trả location của declaration.
7. Khi người dùng Find References tại declaration, trả import và lời gọi.
8. Khi người dùng Rename, tạo WorkspaceEdit đổi declaration, import và call site.

Nếu người dùng đổi tên hàm trong tax.dsl, language server chỉ cần cập nhật document đó và những module phụ thuộc trực tiếp. Các request khác có thể tiếp tục dùng index snapshot cũ cho đến khi snapshot mới sẵn sàng, miễn server không trộn trạng thái giữa các generation.

## 32. Kết luận

Symbol là mô hình định danh ngữ nghĩa của thành phần trong DSL; workspace là phạm vi dự án nơi các symbol, module, file và dependency được tổ chức. Language server cần kết hợp document scope với workspace scope để hiểu khai báo, phân giải import, tìm definition, references và hỗ trợ rename an toàn.

Một kiến trúc tốt xác định symbol identity rõ ràng, xây dựng scope và dependency graph, index declarations trước khi resolve references, và cập nhật index theo thay đổi của tài liệu cùng workspace. Các request LSP như DocumentSymbol, WorkspaceSymbol, Definition, References và Rename dùng chung nền tảng symbol model đó.

Khi workspace lớn hoặc có nhiều project, incremental indexing, cache có version, snapshot nhất quán, cancellation và multi-root support trở nên quan trọng. Nếu phân biệt đúng symbol với text occurrence, document với workspace, và source với generated artifact, language server có thể cung cấp điều hướng và refactoring chính xác mà vẫn phản hồi tốt khi dự án thay đổi liên tục.
