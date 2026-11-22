# Đổi tên an toàn

## 1. Đổi tên an toàn là gì?

Trong một trình soạn thảo dành cho ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), **đổi tên an toàn (safe rename)** là thao tác đổi tên một symbol và cập nhật chính xác những nơi tham chiếu đến symbol đó, đồng thời giữ nguyên ý nghĩa của chương trình.

Ví dụ, DSL có:

~~~text
let taxRate = 0.1

policy "Standard tax"
  when order.total > 0
  then tax = order.total * taxRate
~~~

Người dùng muốn đổi taxRate thành standardTaxRate. Một thao tác đổi tên đúng phải cập nhật khai báo và tham chiếu đã được phân giải đến cùng symbol:

~~~text
let standardTaxRate = 0.1

policy "Standard tax"
  when order.total > 0
  then tax = order.total * standardTaxRate
~~~

Thao tác thay mọi chuỗi taxRate trong file không phải safe rename. Chuỗi đó có thể xuất hiện trong comment, string literal, tên một symbol khác, tài liệu hoặc một scope không liên quan.

Safe rename dựa trên **symbol identity** và quan hệ tham chiếu do semantic analysis xác định. Nó phải hiểu declaration nào được đổi, reference nào thuộc declaration đó và những tên nào chỉ tình cờ giống nhau.

Một thao tác rename đáng tin cậy thường cần:

- Xác định symbol tại vị trí con trỏ.
- Kiểm tra tên mới hợp lệ trong ngữ cảnh và target.
- Tìm declaration cùng tất cả reference thực sự trỏ đến symbol.
- Tránh đổi nhầm symbol bị shadowing hoặc overload.
- Phát hiện collision và variable capture.
- Hiển thị phạm vi thay đổi để người dùng xem trước.
- Áp dụng các chỉnh sửa nhất quán trên các file liên quan.
- Kiểm tra lại chương trình sau khi đổi tên.

## 2. Đổi tên symbol khác tìm và thay thế văn bản

Tìm và thay thế (Find and Replace) thao tác trên chuỗi ký tự. Safe rename thao tác trên thực thể ngữ nghĩa.

Ví dụ:

~~~text
let status = "pending"
let paymentStatus = "paid"

// status is updated after payment
print(status)
print("status")
~~~

Nếu đổi symbol status thành orderState:

- Khai báo status cần đổi.
- Lời gọi print(status) cần đổi.
- Tên paymentStatus không được đổi.
- Comment có thể giữ nguyên.
- String literal "status" phải giữ nguyên.

Thay chuỗi toàn cục có thể vô tình đổi paymentStatus, comment và string literal.

| Thao tác | Cơ sở chọn vị trí | Hiểu scope và kiểu | Rủi ro |
|---|---|---|---|
| Replace text | Chuỗi ký tự khớp | Không | Cao nếu tên xuất hiện nhiều nghĩa |
| Rename theo regex | Mẫu văn bản | Hạn chế | Có thể đổi nhầm hoặc bỏ sót |
| Rename symbol | Symbol identity và reference graph | Có | Thấp hơn khi semantic model chính xác |

Find and Replace vẫn hữu ích khi muốn sửa văn bản thuần, comment hoặc nội dung tài liệu. Khi đổi tên biến, hàm, kiểu, rule hoặc field, nên dùng rename symbol.

## 3. Symbol identity và reference graph

### 3.1 Symbol identity

Một khai báo cần có định danh nội bộ độc lập với tên hiển thị. Ví dụ:

~~~text
SymbolId: module.sales.scope3.taxRate
Name: taxRate
Kind: variable
~~~

Khi đổi tên, SymbolId vẫn đại diện cho cùng một symbol; chỉ tên hiển thị và các reference tương ứng thay đổi.

Nếu dùng chuỗi tên làm identity, việc đổi tên sẽ khiến hệ thống khó xác định đâu là thực thể cũ và đâu là thực thể mới. Hai scope cũng có thể chứa các symbol cùng tên.

### 3.2 Reference graph

Semantic analyzer có thể lưu các quan hệ:

~~~text
Declaration taxRate
   | 
   +---- Read reference at line 8
   |
   +---- Read reference at line 14
   |
   +---- Write reference at line 19
~~~

Mỗi reference cần liên kết đến SymbolId. Rename engine lấy danh sách reference từ index hoặc phân tích lại các tài liệu có liên quan.

### 3.3 Các loại reference

Một symbol có thể được dùng theo nhiều cách:

- Read: đọc giá trị.
- Write: gán hoặc cập nhật.
- Call: gọi hàm hoặc rule.
- Type reference: dùng tên kiểu trong khai báo.
- Import reference: truy cập symbol từ module khác.
- Annotation hoặc metadata reference.
- Reference trong biểu thức truy vấn hoặc cấu hình được DSL hỗ trợ.

Rename cần cập nhật tất cả loại reference mà ngôn ngữ xác định là liên kết đến symbol đó.

### 3.4 Declaration và reference không phải lúc nào cũng giống nhau

Một số cú pháp vừa khai báo vừa tham chiếu tên:

~~~text
function calculateTax(order)
  ...
~~~

Tên calculateTax là declaration. Trong:

~~~text
calculateTax(currentOrder)
~~~

nó là call reference. Parser và resolver phải phân biệt hai vai trò.

## 4. Xác định symbol tại vị trí con trỏ

Khi người dùng gọi Rename Symbol, editor thường gửi vị trí con trỏ hoặc vùng được chọn.

Quy trình:

1. Chuyển vị trí editor thành offset theo quy ước của giao thức.
2. Tìm token hoặc AST node chứa vị trí đó.
3. Xác định node là declaration hay reference.
4. Lấy SymbolId từ semantic model.
5. Kiểm tra symbol có hỗ trợ rename không.
6. Trả tên hiện tại và phạm vi dự kiến.

Ví dụ:

~~~text
let taxRate = 0.1
              ^
~~~

Con trỏ nằm trên taxRate. Resolver xác định token này trỏ đến symbol variable taxRate.

Nếu con trỏ nằm trên từ khóa let hoặc trên một string literal chứa taxRate, editor không nên tự coi đó là symbol.

### 4.1 Rename từ declaration

Người dùng có thể gọi rename trên chính khai báo. Engine lấy symbol được khai báo tại node đó rồi tìm tất cả reference.

### 4.2 Rename từ reference

Người dùng cũng có thể gọi rename trên một chỗ sử dụng. Engine phải đi ngược từ reference đến declaration thông qua SymbolId.

### 4.3 Vị trí không có symbol

Nếu con trỏ nằm trên khoảng trắng, comment hoặc token không đại diện cho symbol, editor nên từ chối thao tác hoặc không hiển thị action rename.

### 4.4 Model chưa hoàn chỉnh

Trong lúc người dùng đang gõ, parser có thể chưa tạo được AST hoàn chỉnh. Rename có thể bị trì hoãn hoặc dùng phần semantic model còn hợp lệ. Nếu không thể xác định symbol chắc chắn, nên báo không thể đổi tên tại vị trí này thay vì đoán theo chuỗi.

## 5. Phạm vi và scope

Tên có ý nghĩa trong một phạm vi. Hai symbol cùng tên ở hai scope khác nhau không nhất thiết là một.

Ví dụ:

~~~text
let rate = 5

function calculate()
  let rate = 10
  return rate * 2

print(rate)
~~~

Ở đây có hai symbol rate:

- rate ở scope ngoài.
- rate cục bộ trong calculate.

Nếu đổi tên symbol ngoài thành baseRate, chỉ khai báo ngoài và print(rate) cuối chương trình cần được cập nhật. Biến rate trong calculate không thuộc symbol đó.

### 5.1 Shadowing

Shadowing xảy ra khi một khai báo bên trong che khuất tên của khai báo bên ngoài.

Rename engine phải dùng binding đã resolve. Không được giả định mọi identifier giống nhau đều tham chiếu đến declaration gần nhất theo văn bản nếu scope hoặc import có quy tắc phức tạp hơn.

### 5.2 Scope lồng nhau

Một hàm có thể chứa block, lambda hoặc nested function. Reference trong closure có thể trỏ đến biến bên ngoài. Rename cần đi theo binding thực tế xuyên qua các scope.

### 5.3 Module và namespace

Hai module có thể cùng khai báo Customer:

~~~text
module sales
  entity Customer

module support
  entity Customer
~~~

Đổi sales.Customer không được làm thay đổi support.Customer. Reference được xác định bằng qualified symbol identity, không chỉ local name.

### 5.4 Visibility và quyền truy cập

Symbol private, protected hoặc public có phạm vi tham chiếu khác nhau. Rename public symbol có thể ảnh hưởng nhiều module hoặc project phụ thuộc. Editor cần phân biệt workspace hiện tại với các consumer bên ngoài mà nó không thể lập chỉ mục.

## 6. Tránh variable capture và thay đổi binding

Một rename có thể tạo tên trùng với symbol khác trong scope. Khi đó, các reference có thể bị liên kết lại ngoài ý muốn.

Ví dụ ban đầu:

~~~text
let customer = loadCustomer()

function display()
  let name = "Guest"
  print(customer.name)
~~~

Nếu đổi customer thành name:

~~~text
let name = loadCustomer()

function display()
  let name = "Guest"
  print(name.name)
~~~

Trong scope của display, name cục bộ có thể che khuất symbol ngoài. Reference cuối có thể bị hiểu thành biến local thay vì customer object. Đây là variable capture hoặc name capture.

### 6.1 Kiểm tra collision trước khi áp dụng

Trước khi thực hiện rename, engine cần kiểm tra tên mới trong từng scope chứa declaration hoặc reference. Nếu tên mới xung đột với symbol khác, có thể:

- Từ chối rename.
- Đề xuất đổi tên symbol gây xung đột.
- Điều chỉnh một số binding bằng qualification nếu DSL hỗ trợ.
- Đề xuất một tên khác.

Không nên áp dụng rename rồi để lỗi binding xuất hiện sau đó nếu collision có thể được phát hiện trước.

### 6.2 Alpha-renaming

Một số ngôn ngữ hoặc refactoring engine có thể đổi tên biến cục bộ khác để tránh capture. Đây là thao tác bổ sung và cần được hiển thị rõ vì nó thay đổi nhiều symbol.

Ví dụ:

~~~text
let customer = loadCustomer()

function display()
  let name = "Guest"
  print(customer.name)
~~~

Nếu người dùng muốn đổi customer thành name, công cụ có thể đề xuất đổi biến local name thành localName trước hoặc đồng thời:

~~~text
let name = loadCustomer()

function display()
  let localName = "Guest"
  print(name.name)
~~~

Phương án này chỉ hợp lệ nếu mọi reference của local name được cập nhật đúng và không tạo collision khác.

### 6.3 Không phải collision nào cũng là lỗi

Một số ngôn ngữ cho phép overload hoặc shadowing có chủ đích. Rename engine phải dùng quy tắc ngôn ngữ, không áp dụng chính sách "mọi tên trùng đều bị cấm".

## 7. Overload và loại symbol

Một tên có thể đại diện cho nhiều khai báo trong hệ thống overload.

Ví dụ:

~~~text
function find(id: Integer): Customer
function find(email: String): Customer
~~~

Đổi tên find thành lookup thường phải đổi cả nhóm overload vì tên hàm là một phần của cùng API overload. Tuy nhiên, một ngôn ngữ có thể cho phép overload theo module hoặc extension khác nhau.

### 7.1 Rename một overload hay cả nhóm?

Chính sách phải được định nghĩa:

- Rename một declaration có đổi toàn bộ overload set không?
- Các call site được phân giải đến overload cụ thể có cần cập nhật không?
- Có reference qua function pointer hoặc method reference không?
- Có generic specialization hoặc extension method không?

Nếu ngôn ngữ xem các overload cùng tên là một API, thường nên đổi tên toàn nhóm. Nếu chúng là các symbol độc lập theo scope, có thể chỉ đổi một symbol.

### 7.2 Constructor

Trong một số ngôn ngữ, constructor có tên gắn với class. Đổi tên class cần cập nhật constructor, factory, type references và cú pháp tạo instance.

### 7.3 Enum và member

Đổi tên enum member có thể ảnh hưởng:

- Các pattern match.
- Giá trị serialization.
- Database mapping.
- API contract.

Nếu tên member được ghi ra dữ liệu, đổi tên source symbol có thể là thay đổi tương thích cần migration riêng.

### 7.4 Import alias

Ví dụ:

~~~text
import finance.tax.calculate as tax
~~~

Tên tax có thể là alias cục bộ. Rename alias tax không nhất thiết đổi symbol calculate trong module gốc. Ngược lại, rename calculate cần cập nhật import path nhưng có thể giữ alias tax nếu alias vẫn hợp lệ.

## 8. Phân biệt code reference với văn bản thường

Tên symbol có thể xuất hiện trong:

- Code.
- Comment.
- String literal.
- Tài liệu Markdown.
- Query string.
- Tên file.
- Annotation.
- Template hoặc macro.

Không phải mọi lần xuất hiện đều là reference ngữ nghĩa.

Ví dụ:

~~~text
let orderTotal = 100
print(orderTotal)
log("orderTotal is calculated here")
// orderTotal is the amount before tax
~~~

Rename orderTotal thành subtotal cần đổi khai báo và print(orderTotal). String và comment có thể giữ nguyên.

### 8.1 Rename trong comment và string

Một số IDE cung cấp tùy chọn riêng để tìm kiếm văn bản có cùng tên trong comment hoặc string. Đây nên là lựa chọn bổ sung, không mặc định gộp vào semantic rename.

### 8.2 Reflection và tên dạng chuỗi

Một số DSL hoặc target có thể tra cứu symbol theo tên chuỗi:

~~~text
invokeByName("calculateTax")
~~~

Resolver có thể không biết string này là reference. Nếu DSL có reflection hoặc dynamic lookup, cần cơ chế annotation, metadata hoặc convention để rename có thể tìm các reference dạng chuỗi.

Nếu không thể xác định đầy đủ, editor nên thông báo rằng dynamic references có thể cần cập nhật thủ công.

### 8.3 Generated code và macro

Một symbol có thể được tạo từ macro hoặc code generator. Rename source symbol cần biết vị trí nguồn gốc và quan hệ với generated node. Không nên sửa trực tiếp file generated nếu lần build tiếp theo sẽ ghi đè.

## 9. Tìm reference trong workspace

Có hai cách chính:

### 9.1 Dùng reference index

Language server hoặc compiler có thể duy trì index:

~~~text
SymbolId -> [
  declaration location,
  reference location 1,
  reference location 2,
  ...
]
~~~

Ưu điểm:

- Tìm nhanh trên project lớn.
- Hỗ trợ Find All References.
- Dễ tái sử dụng cho rename.
- Có thể cập nhật incremental khi file thay đổi.

Hạn chế:

- Index có thể cũ.
- Cần đồng bộ với nội dung chưa lưu trong editor.
- Cần quản lý dependency giữa file và module.

### 9.2 Phân tích lại khi rename

Với project nhỏ hoặc khi index chưa đầy đủ, engine có thể phân tích lại các file liên quan để tìm reference.

Phương án này tốn thời gian hơn nhưng có thể dùng snapshot hiện tại để tránh stale index.

### 9.3 Reference ngoài workspace

Một public API có thể được dùng trong repository khác hoặc bởi client đã biên dịch. Editor hiện tại có thể không nhìn thấy các reference đó.

Rename cần cảnh báo phạm vi:

- Tất cả reference trong workspace hiện tại.
- Các project phụ thuộc đã được index.
- Các reference dynamic hoặc external chưa thể xác định.

Không nên khẳng định đã cập nhật mọi consumer nếu chỉ phân tích một workspace.

## 10. Quy trình safe rename hoàn chỉnh

Một thao tác rename có thể gồm các bước:

1. Xác định symbol tại vị trí con trỏ.
2. Kiểm tra symbol có hỗ trợ rename.
3. Nhận tên mới từ người dùng.
4. Kiểm tra cú pháp identifier theo loại symbol.
5. Kiểm tra keyword, reserved name và naming constraint.
6. Tìm declaration và reference trong phạm vi đã chọn.
7. Kiểm tra collision, overload và capture.
8. Tạo danh sách text edit hoặc workspace edit.
9. Hiển thị preview và phạm vi thay đổi.
10. Kiểm tra phiên bản tài liệu và áp dụng chỉnh sửa.
11. Parse, resolve và type-check lại.
12. Cung cấp undo hoặc phục hồi nếu áp dụng thất bại.

Sơ đồ:

~~~text
Cursor position
      |
      v
Resolve SymbolId
      |
      v
Validate new name
      |
      v
Find declarations and references
      |
      v
Check collisions / capture
      |
      +---- conflict ----> explain / suggest alternative
      |
      v
Build workspace edits
      |
      v
Preview changes
      |
      v
Apply versioned edit
      |
      v
Reparse and re-resolve
      |
      v
Updated diagnostics
~~~

Nếu một bước quan trọng không thể xác minh, editor nên dừng hoặc giới hạn phạm vi thay đổi thay vì tiếp tục với một giả định không chắc chắn.

## 11. Kiểm tra tên mới

Tên mới cần hợp lệ với loại symbol và grammar của DSL.

### 11.1 Identifier syntax

Nếu người dùng đổi tên biến, tên mới phải đáp ứng quy tắc identifier:

- Ký tự đầu hợp lệ.
- Các ký tự tiếp theo được phép.
- Không chứa delimiter hoặc whitespace cấm.
- Không phải keyword nếu DSL không cho phép.
- Đúng quy tắc Unicode của language.

Nếu tên mới là một qualified name, engine cần xác định thao tác đang đổi một segment hay toàn bộ path.

### 11.2 Tên dành riêng

Tên như if, rule hoặc type có thể là keyword. Editor nên báo lý do và có thể gợi ý tên thay thế.

### 11.3 Quy tắc theo loại symbol

Một tên hợp lệ cho variable có thể không hợp lệ cho module, file hoặc endpoint. Rename cần biết NameKind và áp dụng policy tương ứng.

### 11.4 Case-only rename

Đổi customer thành Customer có thể được xem là thay đổi tên trên ngôn ngữ phân biệt hoa thường. Nhưng file system không phân biệt hoa thường có thể xử lý rename file theo cách đặc biệt.

Editor cần kiểm tra cả semantics ngôn ngữ và quy tắc file system mục tiêu.

## 12. Collision và tên đã tồn tại

Tên mới có thể đã được dùng trong cùng scope.

Ví dụ:

~~~text
let taxRate = 0.1
let standardTaxRate = 0.08
~~~

Đổi taxRate thành standardTaxRate sẽ tạo hai khai báo trùng tên nếu cả hai ở cùng scope và DSL không hỗ trợ shadowing ở vị trí đó.

Rename engine nên:

- Phát hiện collision trước khi tạo edit.
- Xác định symbol xung đột.
- Nêu vị trí khai báo hiện có.
- Đề xuất một tên khác nếu có thể.
- Không áp dụng một phần rename.

### 12.1 Collision trong nhiều namespace

Một tên có thể hợp lệ trong namespace type nhưng xung đột trong namespace value. Ngôn ngữ có thể tách hoặc gộp các namespace này. Engine phải dùng quy tắc thực tế của DSL.

### 12.2 Overload set

Nếu tên mới đã có overload cùng tên nhưng chữ ký khác, có thể hợp lệ. Nếu chữ ký trùng hoặc overload resolution trở nên mơ hồ, rename cần bị từ chối.

### 12.3 Collision với generated name

Nếu generator tạo getter hoặc helper từ tên field, rename cần kiểm tra cả các tên được sinh tự động. Nếu không, source có thể hợp lệ nhưng generated target lại có duplicate member.

## 13. Multi-file rename và workspace edit

Một symbol có thể được khai báo trong một file và được dùng trong nhiều file:

~~~text
models/customer.dsl
services/billing.dsl
policies/discount.dsl
tests/customer-test.dsl
~~~

Rename cần cập nhật tất cả các file trong phạm vi được hỗ trợ.

### 13.1 Workspace edit

Workspace edit là tập thay đổi trên một hoặc nhiều tài liệu. Một rename có thể chứa:

- Text edit trong file declaration.
- Text edit ở các file reference.
- Thay đổi import path.
- Đổi tên file hoặc thư mục nếu tên symbol quyết định đường dẫn.
- Cập nhật metadata được quản lý bởi editor.

### 13.2 Tính nguyên tử

Các thay đổi nên được áp dụng như một thao tác logic duy nhất. Nếu một file không thể sửa hoặc version đã thay đổi, client cần từ chối hoặc tính lại toàn bộ workspace edit.

Không nên để declaration được đổi nhưng references ở file khác chưa đổi.

### 13.3 Thứ tự edit và offset

Nếu nhiều edit trong cùng file dùng offset của snapshot ban đầu, client cần áp dụng theo quy tắc giao thức để tránh offset bị lệch. Các range chồng lấn cần được phát hiện hoặc xử lý tường minh.

### 13.4 File rename

Nếu tên entity gắn với tên file, thao tác có thể cần cả text edit và file operation. Cần kiểm tra:

- File đích đã tồn tại chưa.
- Hệ điều hành có phân biệt hoa thường không.
- File có đang được mở hoặc bị khóa không.
- Import path có cần cập nhật không.
- Build manifest có tham chiếu path cũ không.

## 14. Phiên bản tài liệu và thay đổi đồng thời

Trong IDE, người dùng có thể tiếp tục gõ sau khi rename action được tính nhưng trước khi action được áp dụng.

Ví dụ:

1. Language server tìm reference tại phiên bản tài liệu 12.
2. Người dùng sửa file, tạo phiên bản 13.
3. Code action cũ vẫn chứa range của phiên bản 12.
4. Áp dụng range cũ có thể đổi nhầm nội dung.

Để tránh:

- Gắn version hoặc document snapshot với edit.
- Kiểm tra version trước khi áp dụng.
- Nếu version không khớp, yêu cầu tính lại rename.
- Không tự điều chỉnh range theo vị trí cũ mà không có mapping chính xác.

### 14.1 Open buffer và file trên disk

Nội dung trong editor có thể khác file đã lưu. Rename nên dùng nội dung buffer hiện tại cho tài liệu đang mở và đồng bộ các tài liệu khác theo snapshot nhất quán.

### 14.2 Stale reference index

Index có thể chưa cập nhật sau một lần sửa. Trước khi áp dụng rename quan trọng, engine cần bảo đảm index tương ứng với phiên bản hiện tại hoặc cập nhật lại phần bị ảnh hưởng.

### 14.3 Concurrent edits từ công cụ khác

Một formatter, generator hoặc tiến trình ngoài có thể thay đổi file trong lúc rename. Client cần phát hiện thay đổi và tránh ghi đè nội dung mới.

## 15. Rename qua Language Server Protocol

Language Server Protocol (LSP) cung cấp các request phổ biến để editor và language server hỗ trợ rename.

Một luồng khái quát:

~~~text
Editor
  |
  | textDocument/prepareRename
  v
Language Server
  |
  | range + placeholder
  v
Editor asks for new name
  |
  | textDocument/rename
  v
Language Server
  |
  | WorkspaceEdit
  v
Editor applies changes
~~~

### 15.1 prepareRename

Request này cho phép server kiểm tra vị trí có thể rename và trả về range cùng placeholder phù hợp. Server có thể từ chối nếu vị trí không chứa symbol có thể đổi tên.

### 15.2 rename

Request rename nhận vị trí và tên mới, sau đó server tạo WorkspaceEdit chứa các thay đổi cần thiết.

### 15.3 WorkspaceEdit

WorkspaceEdit có thể chứa text document edits và file operations tùy khả năng client/server. Với thay đổi versioned, server cần cung cấp version hoặc thông tin phù hợp theo giao thức.

### 15.4 Client capability

Không phải editor nào cũng hỗ trợ mọi loại resource operation hoặc annotation. Server nên kiểm tra capability và chỉ trả về thao tác client có thể áp dụng.

### 15.5 Không coi LSP là semantic engine

LSP chỉ định nghĩa cách trao đổi. Việc tìm symbol, phát hiện collision và bảo toàn binding vẫn là trách nhiệm của language server hoặc compiler service.

## 16. Rename trong DSL có import và alias

Import tạo thêm quan hệ tên cần xử lý.

Ví dụ:

~~~text
import finance.tax.calculateTax

calculateTax(order)
~~~

Nếu đổi tên function calculateTax thành computeTax, cần cập nhật:

- Declaration trong module finance.tax.
- Import path.
- Call references đã resolve đến function.

Nếu người dùng đã tạo alias:

~~~text
import finance.tax.calculateTax as tax
tax(order)
~~~

Rename function có thể chỉ cần đổi path calculateTax, giữ alias tax. Rename alias tax chỉ đổi alias và các reference cục bộ, không đổi function gốc.

### 16.1 Wildcard import

Nếu DSL cho phép import toàn bộ module:

~~~text
import finance.tax.*
~~~

Reference có thể được resolve từ wildcard import. Rename vẫn cần cập nhật symbol usage, nhưng không nhất thiết sửa wildcard import nếu tên module không đổi.

### 16.2 Re-export

Một module có thể re-export symbol từ module khác. Rename public symbol có thể cần cập nhật re-export path và documentation. Engine cần phân biệt symbol gốc với alias được export.

## 17. Rename và API công khai

Đổi tên một biến local thường là refactoring nội bộ. Đổi tên public type, function, field hoặc rule có thể phá vỡ consumer.

Trước khi đổi public symbol, nên xác định:

- Có consumer ngoài workspace không?
- Tên có được serialize vào JSON/XML/DB không?
- Tên có được dùng trong config hoặc script không?
- Có reflection hoặc dynamic lookup không?
- Có schema migration cần thiết không?
- Có version compatibility policy không?

### 17.1 Source name và external name

Một field có thể có tên source:

~~~text
customerId
~~~

nhưng tên JSON:

~~~text
customer_id
~~~

Rename source field không nhất thiết phải đổi external JSON property. Nếu external name được khai báo tường minh, nên giữ contract đó trừ khi người dùng yêu cầu migration.

### 17.2 Deprecation và alias

Với public API, có thể giữ tên cũ như alias hoặc deprecated wrapper trong một giai đoạn:

~~~text
new function computeTax(...)
deprecated function calculateTax(...) -> computeTax(...)
~~~

Cách này giảm tác động với consumer cũ nhưng cần semantics rõ và kế hoạch loại bỏ.

### 17.3 Migration plan

Một công cụ có thể tạo báo cáo:

- Symbol cũ và mới.
- File trong workspace đã cập nhật.
- Consumer chưa được tìm thấy.
- External contract cần migration.
- Các string-based reference cần kiểm tra thủ công.

Không nên tuyên bố rename public API hoàn tất toàn hệ sinh thái nếu công cụ chỉ có thể sửa workspace hiện tại.

## 18. Rename trong generated code, macro và source map

Một số DSL sinh mã hoặc mở rộng macro trước khi semantic analysis. Rename có thể gặp node được sinh ra thay vì node nguồn.

### 18.1 Source origin

Generated node cần giữ source origin hoặc mapping đến node DSL tạo ra nó. Khi người dùng rename trên generated view, editor có thể chuyển vị trí về source declaration nếu mapping là duy nhất.

### 18.2 Một generated node từ nhiều source node

Một đoạn mã đích có thể được tạo từ nhiều khai báo DSL. Khi đó, rename cần xác định symbol nào đang được chọn và tránh sửa các source node khác.

### 18.3 Không sửa file generated trực tiếp

Nếu generated file được tạo lại, sửa trực tiếp có thể mất. Rename nên cập nhật source DSL hoặc metadata điều khiển generator, sau đó chạy generation theo workflow được thiết kế.

### 18.4 Dynamic name construction

Nếu tên được ghép từ chuỗi hoặc tính tại runtime, reference index có thể không tìm được đầy đủ. Editor cần cảnh báo về giới hạn thay vì giả định đã cập nhật mọi chỗ.

## 19. Undo, transaction và phục hồi

Rename thường thay đổi nhiều file. Editor nên coi đó là một thao tác có thể undo như một đơn vị logic.

### 19.1 Undo

Undo cần khôi phục:

- Nội dung trước rename.
- Tên file hoặc thư mục nếu có file operation.
- Import và metadata liên quan.
- Trạng thái editor phù hợp.

### 19.2 Transaction

Có thể mô hình hóa:

~~~text
Prepare edits
    |
    v
Validate versions and ranges
    |
    v
Apply workspace edit
    |
    +---- failure ----> rollback / reject
    |
    v
Reanalyze
    |
    v
Commit editor undo step
~~~

Editor hoặc language server có thể không có database transaction thực sự. Tuy vậy, hành vi cần tránh trạng thái nửa cập nhật.

### 19.3 File system failure

Đổi tên file có thể thất bại do quyền, lock, path đích tồn tại hoặc filesystem không hỗ trợ thao tác mong muốn. UI cần báo file operation nào thất bại và giữ nội dung nhất quán.

### 19.4 Undo sau khi người dùng chỉnh sửa thêm

Nếu người dùng thực hiện nhiều thay đổi sau rename, undo stack cần bảo đảm chỉ đảo thao tác rename mà không xóa các chỉnh sửa mới. Đây là trách nhiệm của editor transaction model.

## 20. Hiệu năng và incremental indexing

Project lớn có thể có hàng trăm nghìn reference. Tìm toàn bộ mỗi lần rename có thể chậm.

### 20.1 Reference index

Index có thể lưu:

- SymbolId.
- Declaration location.
- Reference locations.
- Document version.
- Module dependency.
- Loại reference.

### 20.2 Incremental update

Khi file thay đổi:

1. Xóa reference cũ của snapshot trước.
2. Parse và resolve phần thay đổi.
3. Thêm reference mới.
4. Cập nhật dependency của module.
5. Đánh dấu index version mới.

Nếu một symbol thay đổi visibility hoặc import, các file phụ thuộc có thể cần resolve lại.

### 20.3 Giới hạn kết quả

Nếu engine không thể tìm hết reference do file chưa được tải, project ngoài workspace hoặc dynamic lookup, cần nêu rõ giới hạn. Có thể cung cấp chế độ tìm kiếm mở rộng hoặc yêu cầu người dùng xác nhận phạm vi.

### 20.4 Cancellation

Rename trên project lớn có thể mất thời gian. Editor nên cho phép hủy quá trình tìm reference hoặc preview trước khi áp dụng.

## 21. Kiểm thử safe rename

Safe rename cần kiểm thử trên symbol binding, không chỉ kiểm tra chuỗi đầu ra.

### 21.1 Kiểm thử cơ bản

- Rename từ declaration.
- Rename từ reference.
- Cập nhật mọi read/write reference.
- Giữ nguyên symbol khác cùng tên.
- Từ chối keyword hoặc identifier không hợp lệ.
- Từ chối collision trong cùng scope.

### 21.2 Kiểm thử scope

- Shadowing.
- Nested block.
- Closure capture.
- Hai module cùng tên symbol.
- Import alias.
- Wildcard import.
- Overload set.
- Generic type và type parameter.

### 21.3 Kiểm thử variable capture

Sau rename, parse và resolve lại. Với mỗi reference được cập nhật, xác nhận nó vẫn trỏ đến SymbolId mong muốn hoặc đến symbol tương ứng sau rename.

Đồng thời kiểm tra các reference không thuộc symbol mục tiêu vẫn giữ binding ban đầu.

### 21.4 Kiểm thử multi-file

- Reference trong nhiều file.
- File chưa lưu trong editor.
- File read-only.
- File đích đã tồn tại.
- Import path cần cập nhật.
- Rename case-only trên file system không phân biệt hoa thường.
- Workspace edit có version cũ.

### 21.5 Kiểm thử comment và string

Đảm bảo semantic rename không đổi comment hoặc string literal mặc định. Nếu có tùy chọn tìm văn bản trong comment/string, test riêng hành vi đó.

### 21.6 Kiểm thử undo

Áp dụng rename, undo và xác nhận mọi file, tên file, import và binding trở lại trạng thái trước thao tác.

## 22. Những sai lầm thường gặp

### Dùng Find and Replace cho symbol

Có thể đổi nhầm string, comment, symbol khác scope hoặc một phần tên dài hơn.

**Cách khắc phục:** dùng SymbolId và reference graph.

### Chỉ đổi declaration

Chương trình có thể còn reference đến tên cũ và không compile.

**Cách khắc phục:** tìm declaration và tất cả reference đã resolve.

### Đổi mọi identifier cùng chuỗi

Hai symbol ở hai scope có thể cùng tên nhưng độc lập.

**Cách khắc phục:** kiểm tra binding tại từng vị trí.

### Bỏ qua shadowing và capture

Tên mới có thể khiến reference trỏ sang symbol khác.

**Cách khắc phục:** kiểm tra scope và resolve lại sau rename.

### Không kiểm tra collision

Tên mới có thể trùng declaration hoặc generated member đã tồn tại.

**Cách khắc phục:** validate trước khi tạo workspace edit.

### Dùng reference index cũ

Index không khớp với buffer hiện tại có thể bỏ sót hoặc đổi nhầm vị trí.

**Cách khắc phục:** gắn version và cập nhật index theo snapshot.

### Áp dụng multi-file edit không nguyên tử

Một số file được đổi, file khác thất bại, làm project ở trạng thái không nhất quán.

**Cách khắc phục:** dùng workspace edit, kiểm tra version và hỗ trợ rollback/undo.

### Bỏ qua dynamic references

Reflection hoặc tên ghép từ chuỗi có thể không xuất hiện trong reference index.

**Cách khắc phục:** nêu rõ giới hạn và cung cấp tìm kiếm văn bản bổ sung.

### Khẳng định đã cập nhật mọi consumer bên ngoài

Workspace hiện tại có thể không chứa toàn bộ client của public API.

**Cách khắc phục:** mô tả chính xác phạm vi đã phân tích và đưa ra migration guidance.

## 23. Quy trình thiết kế tính năng safe rename

Khi xây dựng rename cho DSL editor, có thể triển khai:

1. **Xác định symbol model:** mỗi declaration có SymbolId ổn định.
2. **Lưu reference binding:** mỗi identifier reference trỏ đến symbol cụ thể.
3. **Xử lý vị trí con trỏ:** xác định declaration/reference tại vị trí được yêu cầu.
4. **Kiểm tra tên mới:** grammar, keyword, loại symbol và naming policy.
5. **Tìm phạm vi reference:** workspace, module, project hoặc consumer đã index.
6. **Kiểm tra collision:** scope, overload, generated names và file path.
7. **Kiểm tra capture:** bảo đảm binding không thay đổi ngoài ý muốn.
8. **Tạo workspace edit:** giữ source range và document version.
9. **Preview:** cho người dùng xem file và vị trí bị thay đổi.
10. **Áp dụng nhất quán:** xử lý lỗi file operation và version conflict.
11. **Phân tích lại:** parse, resolve và kiểm tra binding sau rename.
12. **Undo và báo cáo:** hỗ trợ phục hồi và nêu rõ reference ngoài phạm vi.

Một rename chỉ nên được xem là an toàn khi engine có đủ thông tin để xác định symbol và bảo đảm các reference trong phạm vi hỗ trợ vẫn liên kết đúng sau thay đổi.

## 24. Ví dụ tổng hợp

Giả sử DSL có:

~~~text
module billing

let taxRate = 0.1

entity Order {
  field total: Money
}

function calculateTax(order: Order): Money
  return order.total * taxRate

function display(order: Order)
  let taxRate = 0
  print(calculateTax(order))
  print(taxRate)
~~~

Người dùng đặt con trỏ trên taxRate ở khai báo cấp module và chọn Rename thành standardTaxRate.

### 24.1 Resolve symbol

Editor xác định SymbolId của biến cấp module. Reference trong calculateTax trỏ đến symbol này. Biến taxRate cục bộ trong display là symbol khác.

### 24.2 Kiểm tra collision

Engine kiểm tra standardTaxRate chưa tồn tại trong module scope và không xung đột với import hoặc generated name.

### 24.3 Tạo edit

Các vị trí cần đổi:

- Declaration taxRate ở cấp module.
- Reference taxRate trong calculateTax.

Vị trí trong display không đổi vì nó trỏ đến biến local khác.

### 24.4 Kết quả

~~~text
module billing

let standardTaxRate = 0.1

entity Order {
  field total: Money
}

function calculateTax(order: Order): Money
  return order.total * standardTaxRate

function display(order: Order)
  let taxRate = 0
  print(calculateTax(order))
  print(taxRate)
~~~

Sau khi áp dụng, editor parse và resolve lại. Reference trong calculateTax phải trỏ đến symbol đã đổi tên; biến local trong display vẫn giữ binding cũ.

## 25. Câu hỏi tự kiểm tra

1. Safe rename khác Find and Replace như thế nào?
2. Vì sao symbol cần identity độc lập với tên hiển thị?
3. Reference graph giúp tìm những vị trí nào?
4. Làm thế nào để xác định symbol tại vị trí con trỏ?
5. Shadowing và variable capture có thể làm rename sai ra sao?
6. Rename một overload có cần đổi cả overload set không?
7. Vì sao comment và string literal thường không được đổi trong semantic rename?
8. Dynamic lookup và reflection tạo giới hạn gì cho reference search?
9. Workspace edit cần bảo đảm những điều gì khi thay đổi nhiều file?
10. Vì sao cần kiểm tra document version trước khi áp dụng rename?
11. LSP prepareRename và rename có vai trò gì?
12. Rename public API khác rename local variable như thế nào?
13. Source map giúp rename symbol được sinh từ macro ra sao?
14. Vì sao cần kiểm tra lại binding sau khi áp dụng?
15. Undo và transaction giúp tránh trạng thái rename dở dang như thế nào?

Đổi tên an toàn là một refactoring dựa trên ngữ nghĩa. Khi editor dùng symbol identity, reference binding, kiểm tra scope và collision, đồng thời áp dụng workspace edit theo phiên bản tài liệu, người dùng có thể đổi tên mà không vô tình thay đổi những symbol hoặc hành vi không liên quan.
