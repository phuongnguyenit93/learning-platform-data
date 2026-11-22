# Tìm tham chiếu

## 1. Tìm tham chiếu trong DSL editor là gì?

Trong một DSL (*Domain-Specific Language*), người dùng thường khai báo biến, kiểu, hàm, rule, workflow, trạng thái hoặc thành phần miền rồi sử dụng chúng ở nhiều vị trí khác nhau. Khi chỉnh sửa một symbol, người dùng cần biết tất cả vị trí đang phụ thuộc vào symbol đó.

**Tìm tham chiếu (*Find References*)** là chức năng của editor giúp tìm các vị trí trong một phạm vi xác định đang tham chiếu đến cùng một symbol. Symbol có thể là biến, hàm, kiểu, field, rule, workflow step, state, module, alias hoặc một phần tử miền khác.

Ví dụ:

~~~text
let customerLimit: Money = 5000

rule "check-limit" {
    when order.total <= customerLimit
    then approve(order)
}

rule "notify-limit" {
    when customerLimit > 0
    then log("Limit configured")
}
~~~

Khi đặt con trỏ trên tên customerLimit và chọn Find References, editor có thể hiển thị:
- Dòng khai báo biến.
- Vị trí customerLimit trong điều kiện check-limit.
- Vị trí customerLimit trong điều kiện notify-limit.

Tất cả các vị trí đó được liên kết với cùng một declaration sau khi semantic analyzer resolve tên.

Tìm tham chiếu giúp người phát triển:
- Hiểu phạm vi ảnh hưởng của một symbol.
- Xác định nơi một giá trị, hàm hoặc rule đang được sử dụng.
- Điều tra phụ thuộc trước khi sửa hoặc xóa khai báo.
- Tìm nơi gọi một operation hoặc workflow.
- Hiểu quan hệ giữa các module.
- Hỗ trợ review và bảo trì chương trình DSL.

Điểm cốt lõi là editor tìm theo **danh tính ngữ nghĩa của symbol**, không chỉ tìm những đoạn văn bản có cùng cách viết.

## 2. Tìm tham chiếu khác tìm kiếm văn bản như thế nào?

Tìm kiếm văn bản (*text search*) tìm chuỗi ký tự khớp trong file. Find References tìm những node đã được xác định là tham chiếu đến một symbol cụ thể.

Giả sử DSL có hai scope:

~~~text
module Billing {
    let status = "PENDING"
    print(status)
}

module Shipping {
    let status = "READY"
    print(status)
}
~~~

Text search với từ status có thể trả về cả bốn vị trí, vì chúng có cùng chuỗi ký tự.

Find References trên declaration status trong Billing chỉ nên trả về declaration và usage thuộc symbol của Billing, theo chính sách có bao gồm declaration hay không. Nó không được đưa status trong Shipping vào kết quả nếu hai declaration là hai symbol khác nhau.

| Khả năng | Text search | Find References |
|---|---|---|
| So khớp chuỗi | Có | Không phải tiêu chí quyết định |
| Phân biệt hai declaration cùng tên | Không tự biết | Có, nếu symbol resolution thành công |
| Hiểu scope | Không | Có |
| Theo alias/import | Không tự hiểu | Có thể, theo semantic model |
| Tìm trong comment/string | Thường có | Thường không, trừ khi DSL định nghĩa nội dung đó là reference |
| Hoạt động khi tên bị shadow | Trả mọi chuỗi giống nhau | Chỉ trả reference đến symbol đã resolve |
| Cần parser/semantic analysis | Không nhất thiết | Thường cần |

Text search vẫn hữu ích khi tìm tài liệu, comment hoặc chuỗi literal. Find References giải quyết một câu hỏi khác: node nào trong chương trình phụ thuộc vào symbol đang được chọn?

## 3. Declaration, definition và reference

Để hiểu kết quả Find References, cần phân biệt một số loại vị trí.

- **Declaration:** nơi giới thiệu tên hoặc symbol vào scope.
- **Definition:** nơi cung cấp phần triển khai hoặc nội dung đầy đủ của symbol.
- **Reference:** nơi sử dụng hoặc nhắc đến symbol theo ngữ nghĩa của DSL.
- **Read:** reference đọc giá trị hoặc truy cập thông tin.
- **Write:** reference ghi hoặc cập nhật giá trị.
- **Call:** reference gọi hàm, rule hoặc operation.
- **Type reference:** reference dùng tên kiểu trong annotation, cast hoặc constraint.

Một số DSL gộp declaration và definition thành một vị trí. DSL khác có khai báo chữ ký ở một file và phần triển khai ở file khác.

Ví dụ:

~~~text
declare function calculateTax(amount: Money): Money

define function calculateTax(amount: Money): Money {
    return amount * taxRate
}

let totalTax = calculateTax(order.total)
~~~

Một symbol function có thể có declaration, definition và call site. Find References có thể trả về call site, declaration và definition tùy chế độ hiển thị. Vì vậy, UI cần phân biệt loại location thay vì hiển thị tất cả như nhau.

### 3.1. Có bao gồm declaration trong kết quả không?

Các editor có thể chọn một trong hai quy ước:
- Find References chỉ hiển thị các usage, còn declaration được truy cập bằng Go to Definition.
- Find References hiển thị cả declaration và usage, hoặc cung cấp tùy chọn Include Declaration.

Cả hai đều có thể hợp lý nếu được dùng nhất quán. Kết quả nên ghi rõ loại vị trí để người dùng biết dòng nào khai báo và dòng nào sử dụng.

### 3.2. Definition và implementation

Một interface hoặc abstract rule có thể có nhiều implementation. Find References trên interface có thể trả về nơi dùng interface, trong khi Find Implementations trả về các kiểu hoặc thành phần triển khai nó.

Không nên nhầm Find References với Find Implementations. Một thao tác tìm usage, thao tác kia tìm quan hệ triển khai hoặc kế thừa.

## 4. Symbol identity và semantic resolution

### 4.1. Symbol là gì?

Symbol là đại diện ngữ nghĩa cho một tên trong chương trình. Một symbol thường chứa:
- Tên và loại symbol.
- Declaration node.
- Scope hoặc namespace.
- Module hoặc file sở hữu.
- Kiểu hoặc chữ ký nếu có.
- Visibility và accessibility.
- Stable ID hoặc internal key.
- Metadata phục vụ navigation và diagnostics.

Hai identifier có cùng lexeme chưa chắc là cùng symbol. Ngược lại, một symbol có thể được tham chiếu qua nhiều cách viết nếu DSL hỗ trợ alias hoặc qualified name.

### 4.2. Resolve reference

Semantic analyzer xác định identifier node tham chiếu đến declaration nào. Quá trình này thường xét:
1. Scope hiện tại.
2. Scope cha.
3. Namespace.
4. Import và alias.
5. Visibility.
6. Overload resolution hoặc loại symbol.
7. Quy tắc shadowing và ambiguity.

Sau khi resolve thành công, reference node có thể được gắn với symbol ID hoặc declaration ID.

Ví dụ:

~~~text
module Store {
    let price = 100

    rule "calculate" {
        let total = price * quantity
    }
}
~~~

Reference price trong rule có thể resolve đến declaration price ở scope module nếu không có declaration cục bộ che khuất.

### 4.3. Shadowing

~~~text
let status = "GLOBAL"

rule "check" {
    let status = "LOCAL"
    print(status)
}

print(status)
~~~

Hai identifier status trong hai lời gọi print không nhất thiết tham chiếu cùng declaration. Reference trong rule trỏ đến local status; reference ngoài rule trỏ đến global status.

Find References trên local declaration không được đưa usage của global symbol vào kết quả.

### 4.4. Qualified names và alias

DSL có thể cho phép:

~~~text
import inventory.Product as Item

let selected: Item
~~~

Reference Item cần resolve về type Product được import qua alias. Một thao tác tìm tham chiếu trên Product có thể cần đưa alias use vào kết quả theo chính sách của language server. Nếu alias là một symbol độc lập, editor có thể hiển thị quan hệ alias riêng.

## 5. Phạm vi tìm kiếm

Find References thường cho phép tìm trong một phạm vi:
- File hiện tại.
- Module hiện tại.
- Project hoặc workspace.
- Tập file đang mở.
- Các module phụ thuộc đã được index.
- Một tập resource do người dùng chọn.

Phạm vi phải được thể hiện rõ vì kết quả có thể khác nhau. Nếu chỉ tìm trong file hiện tại, editor không nên khiến người dùng hiểu nhầm rằng đã tìm hết workspace.

### 5.1. File scope

Tìm trong file hiện tại phù hợp với DSL nhỏ hoặc file có scope cục bộ. Nó nhanh nhưng không tìm thấy usage ở file khác.

### 5.2. Module scope

Module scope cần hiểu import, export, namespace và module dependency. Một symbol private có thể chỉ được tham chiếu trong module; một exported symbol có thể được dùng từ module khác.

### 5.3. Workspace scope

Workspace scope tìm trong các project hoặc folder thuộc workspace. Cần xác định:
- Folder nào được tính là workspace root.
- File nào bị loại trừ.
- Generated files có được tính không.
- Dependency source có được index không.
- File chưa mở có được tìm không.
- Workspace có nhiều project hoặc nhiều DSL version không.

### 5.4. Dependency scope

Một số DSL cho phép tham chiếu symbol từ thư viện hoặc package đã cài. Editor có thể tìm references trong dependency source nếu có dữ liệu và quyền truy cập. Với thư viện chỉ có binary metadata, có thể chỉ điều hướng đến declaration hoặc không có source locations đầy đủ.

## 6. Quy trình Find References

Một quy trình phổ biến:

~~~text
Người dùng đặt con trỏ trên identifier
                |
                v
       Xác định AST node
                |
                v
       Resolve node thành symbol
                |
                v
      Lấy stable symbol identity
                |
                v
      Tra reference index hoặc
      duyệt semantic model
                |
                v
      Lọc theo search scope
                |
                v
      Tạo danh sách source locations
                |
                v
      Sắp xếp và hiển thị kết quả
~~~

### 6.1. Xác định node tại con trỏ

Editor nhận vị trí con trỏ theo document URI và offset hoặc line/character. Parser cần xác định node tương ứng với vị trí đó.

Nếu con trỏ nằm trên:
- Identifier use: tìm symbol được reference.
- Declaration name: tìm symbol được khai báo.
- Property access: xác định property hoặc receiver tùy vị trí.
- Keyword: có thể không có symbol để tìm.
- Comment hoặc string: thông thường không có semantic reference, trừ khi DSL hỗ trợ embedded language hoặc link đặc biệt.

### 6.2. Resolve symbol

Nếu node chưa được resolve, editor có thể yêu cầu semantic analysis. Khi có symbol ID, truy vấn references không cần so sánh tên text trên toàn bộ source.

Nếu resolve thất bại hoặc mơ hồ, editor nên trả thông báo phù hợp thay vì tìm theo chuỗi và tạo kết quả sai.

### 6.3. Truy vấn references

Với symbol ID đã biết, hệ thống lấy các reference locations tương ứng. Kết quả có thể đến từ:
- Reference index trong workspace.
- Symbol graph.
- Semantic model đã parse.
- Language server đang giữ document state.
- Bộ lập chỉ mục nền cho file chưa mở.

### 6.4. Lọc và sắp xếp

Kết quả có thể được lọc theo scope, loại reference và trạng thái file. Thường sắp xếp theo:
1. URI hoặc đường dẫn file.
2. Dòng.
3. Cột.
4. Loại reference nếu cùng vị trí.

Không nên dựa vào thứ tự trả về ngẫu nhiên của hash map hoặc index.

## 7. Reference index

### 7.1. Vì sao cần index?

Nếu workspace có hàng nghìn file, mỗi lần Find References đều parse và resolve toàn bộ project sẽ chậm. Reference index lưu quan hệ giữa symbol và các vị trí sử dụng để truy vấn nhanh.

Một cấu trúc khái niệm:

~~~text
Symbol ID                         Reference locations
------------------------------------------------------------
symbol:Billing.customerLimit      pricing.dsl:8:24
                                  alerts.dsl:12:15
                                  checkout.dsl:31:9

symbol:Shipping.status            shipping.dsl:4:5
                                  shipping.dsl:18:11
~~~

Có thể tổ chức index theo chiều:
- Symbol ID → danh sách reference locations.
- Document URI → các symbol được tham chiếu trong document.
- Document URI → declaration và symbol metadata.

Index hai chiều giúp cả truy vấn references và cập nhật một file khi nội dung thay đổi.

### 7.2. Nội dung một reference record

Một reference record có thể lưu:

| Field | Ý nghĩa |
|---|---|
| symbolId | Stable identity của symbol |
| documentUri | File chứa reference |
| range | Vị trí identifier hoặc node |
| role | Read, write, call, type use hoặc import |
| isDeclaration | Có phải declaration location không |
| containerId | Scope hoặc container |
| documentVersion | Version đã được phân tích |
| origin | Source, generated hoặc dependency |
| metadata | Thông tin bổ sung theo DSL |

Range nên chỉ vào phần identifier có ý nghĩa điều hướng, không nhất thiết bao trọn expression chứa nó.

### 7.3. Stable symbol identity

Không nên dùng tên hiển thị làm khóa duy nhất. Hai scope có thể chứa cùng tên. Symbol ID có thể được tạo từ:
- Module identity.
- Scope identity.
- Declaration identity.
- Symbol kind.
- Stable URI hoặc model ID.

ID không nên phụ thuộc vào line number vì chèn dòng ở phía trên sẽ làm thay đổi vị trí nhưng không làm thay đổi danh tính symbol.

### 7.4. Index persistence

Index có thể:
- Chỉ nằm trong memory và được dựng lại khi mở workspace.
- Lưu trên disk để tăng tốc lần mở sau.
- Lưu trong database hoặc language server cache.

Nếu lưu bền vững, index phải gắn với document version, DSL version, metamodel version và semantic configuration. Khi các thành phần này thay đổi, dữ liệu cũ có thể không còn hợp lệ.

## 8. Xây dựng reference index

### 8.1. Index theo document

Khi một file được parse và resolve, language server có thể tạo danh sách reference records của file đó.

~~~text
DocumentAnalysis {
    uri
    version
    declarations[]
    references[]
    diagnostics[]
}
~~~

Khi phân tích hoàn tất, hệ thống thay thế index cũ của document bằng index mới. Không nên trộn reference từ hai version khác nhau.

### 8.2. Index theo symbol

Từ các document records, xây map:

~~~text
referencesBySymbol[symbolId] = [
    ReferenceLocation(documentUri, range, role),
    ...
]
~~~

Một truy vấn Find References lúc này là lookup theo symbol ID, sau đó lọc theo phạm vi.

### 8.3. Hai phase khi resolve cross-file

Với project nhiều file, có thể cần:
1. Thu thập declaration và export từ các module.
2. Resolve reference sau khi symbol index của dependency đã sẵn sàng.

Nếu resolve trước khi module được nạp, một reference hợp lệ có thể bị báo unresolved tạm thời.

### 8.4. File chưa mở

Editor có thể index file chưa mở bằng background workspace scan. Khi mở file, nội dung trong editor buffer có thể khác nội dung trên disk. Buffer mới là nguồn có thẩm quyền cho document đang mở.

Cần xác định cách hợp nhất:
- Document mở dùng version trong memory.
- Document chưa mở dùng nội dung trên disk hoặc cache hợp lệ.
- Khi save, cập nhật index theo nội dung đã lưu.
- Khi close mà không save, bỏ hoặc giữ buffer theo chính sách editor.

## 9. Incremental indexing khi chỉnh sửa

Người dùng có thể sửa file liên tục. Rebuild toàn bộ workspace sau mỗi thay đổi là không cần thiết và có thể làm editor chậm.

### 9.1. Document version

Mỗi lần document thay đổi, editor hoặc language server có thể tăng document version. Reference records phải gắn với version tương ứng.

Nếu analysis cho version 8 hoàn tất sau analysis version 9, kết quả cũ không được ghi đè index mới.

### 9.2. Thay thế index theo document

Một chiến lược an toàn:
1. Nhận document change.
2. Đánh dấu analysis cũ là stale.
3. Parse và resolve nội dung mới.
4. Tạo document index tạm.
5. Nếu version vẫn là mới nhất, atomically thay index cũ bằng index mới.
6. Cập nhật reverse references và diagnostics.

Cần tránh xóa index cũ quá sớm nếu người dùng vẫn cần navigation trong lúc analysis mới đang chạy. Có thể giữ kết quả cũ với trạng thái stale cho đến khi kết quả mới sẵn sàng.

### 9.3. Invalidation theo dependency

Đổi tên một declaration có thể ảnh hưởng reference ở nhiều file. Sửa import hoặc export có thể làm thay đổi cách resolve symbol của nhiều document.

Dependency graph giữa module, scope và symbol giúp xác định phạm vi cần re-resolve. Nếu chưa có dependency tracking đủ tin cậy, có thể re-index rộng hơn để bảo đảm correctness.

### 9.4. Cancellation

Khi người dùng tiếp tục gõ hoặc phát một truy vấn mới, request Find References hoặc analysis cũ có thể bị hủy. Engine cần hỗ trợ cancellation để tránh lãng phí CPU và tránh trả kết quả cũ sau kết quả mới.

## 10. Find References qua Language Server Protocol

Language Server Protocol (*LSP*) cung cấp cơ chế chuẩn để editor gửi yêu cầu tìm references đến language server.

Một request điển hình là textDocument/references. Request chứa:
- Text document URI.
- Vị trí line và character.
- Context có thể yêu cầu includeDeclaration.

Language server trả về danh sách Location hoặc LocationLink tùy phương thức và khả năng hỗ trợ. Mỗi location chứa URI và range trong document.

### 10.1. Ý nghĩa includeDeclaration

Context includeDeclaration cho biết client có muốn kết quả chứa declaration hay không. Server cần tôn trọng tùy chọn này khi xây response.

Nếu DSL có nhiều loại declaration/definition, server cần có quy tắc nhất quán về vị trí nào được coi là declaration.

### 10.2. LSP không tự giải quyết semantics

LSP chỉ định dạng request/response và khả năng giao tiếp. Language server vẫn phải:
- Parse DSL.
- Resolve symbol.
- Xây reference index hoặc tìm references.
- Áp dụng scope và visibility.
- Trả range đúng với encoding của client.

Một server trả mọi identifier cùng tên không thực hiện semantic Find References đúng nghĩa.

### 10.3. Position encoding

LSP position có thể phụ thuộc encoding được client và server thương lượng, chẳng hạn UTF-16 hoặc UTF-8 trong các phiên bản hỗ trợ. Nếu lexer/parser lưu offset theo Unicode code point hoặc byte, server phải chuyển đổi chính xác.

Ký tự tiếng Việt có dấu kết hợp hoặc ký tự ngoài BMP có thể làm line/character sai nếu các thành phần dùng đơn vị khác nhau.

### 10.4. Kết quả và document changes

Nếu file thay đổi giữa lúc server tìm references và lúc client hiển thị kết quả, range có thể không còn trỏ đúng vị trí. Có thể dùng document version, cancellation và re-request để giảm kết quả stale.

## 11. Các loại reference trong DSL

Không phải mọi reference đều là một identifier đọc giá trị. DSL có thể phân loại reference theo vai trò.

### 11.1. Read reference

~~~text
let total = subtotal + tax
~~~

subtotal và tax là read references vì biểu thức đọc giá trị của chúng.

### 11.2. Write reference

~~~text
customer.status = "ACTIVE"
~~~

Nếu status là field được gán, vị trí status là write reference. Trong một số DSL, receiver customer cũng là read reference.

### 11.3. Read-write reference

~~~text
counter = counter + 1
~~~

Vế phải đọc counter; vế trái ghi counter. Cùng một symbol xuất hiện hai vị trí với hai vai trò khác nhau.

### 11.4. Call reference

~~~text
calculateTax(order.total)
~~~

Tên calculateTax là call reference đến function hoặc operation declaration.

### 11.5. Type reference

~~~text
let customer: Customer
~~~

Customer là type reference. Reference đến type có thể được tìm trong type declaration, generic constraint, cast hoặc function signature.

### 11.6. Import và alias reference

~~~text
import billing.TaxRule as Tax
use Tax
~~~

Tax trong use có thể resolve qua alias. Find References trên symbol gốc hoặc alias cần theo quy tắc language server đã công bố.

### 11.7. Domain reference

DSL có thể tham chiếu entity hoặc resource theo ID:

~~~text
notify customer "C-100"
~~~

Nếu ID được xem là symbol reference, editor có thể cung cấp Find References. Nếu đó chỉ là literal data, chức năng phải dựa trên semantics của DSL thay vì suy đoán từ chuỗi.

## 12. Tìm tham chiếu trong các cấu trúc đặc biệt

### 12.1. Member và property access

~~~text
order.customer.address.city
~~~

Mỗi phần của property chain có thể là một symbol riêng:
- order là biến hoặc object reference.
- customer là member của kiểu Order.
- address là member của kiểu Customer.
- city là member của kiểu Address.

Khi con trỏ ở customer, Find References phải tìm member customer, không phải mọi identifier trong toàn biểu thức.

### 12.2. Overloaded function

~~~text
format(dateValue)
format(moneyValue)
~~~

Nếu DSL hỗ trợ overload, hai lời gọi cùng tên có thể resolve đến hai function symbol khác nhau. Find References trên một overload chỉ nên trả call site đã resolve đến overload đó.

Nếu resolution còn mơ hồ do thiếu type information, editor cần thể hiện kết quả không chắc chắn hoặc chờ semantic analysis.

### 12.3. Generic type và type parameter

~~~text
function identity<T>(value: T): T
~~~

T là type parameter symbol. Các vị trí T trong parameter và return type là references đến declaration T. Nó không phải cùng symbol với một type T có tên giống ở module khác.

### 12.4. Macro và generated code

Nếu DSL hỗ trợ macro hoặc code generation, reference trong generated code có thể được ánh xạ về source macro hoặc template. Editor cần xác định:
- Có tìm generated locations không?
- Có chuyển location về source origin không?
- Một source reference sinh ra nhiều generated references được hiển thị như thế nào?
- Generated file có được phép sửa trực tiếp không?

Không nên trộn generated locations với source locations mà không ghi rõ nguồn gốc.

### 12.5. Embedded language

Một DSL có thể nhúng SQL, expression hoặc template language:

~~~text
query {
    SELECT * FROM orders WHERE customer_id = :customerId
}
~~~

customerId có thể là parameter của embedded SQL hoặc symbol trong DSL host. Language server cần biết vùng embedded language và dùng đúng resolver. Text search đơn giản có thể trả kết quả không liên quan giữa hai ngôn ngữ.

## 13. Find References và Rename Symbol

Find References và Rename Symbol thường dùng chung symbol resolution và reference index, nhưng mục đích khác nhau.

- **Find References:** chỉ hiển thị các vị trí liên quan.
- **Rename Symbol:** tạo workspace edit để đổi declaration và những reference đã resolve.
- **Go to Definition:** chuyển đến declaration hoặc definition.
- **Go to Type Definition:** chuyển đến declaration của kiểu.
- **Find Implementations:** tìm implementation hoặc subtype theo quan hệ của ngôn ngữ.

### 13.1. Vì sao không nên rename bằng text replace?

Giả sử:

~~~text
let status = "READY"
print(status)
print("status")
-- status used by operations
~~~

Rename symbol status cần đổi declaration và usage đã resolve. Nó không nên tự đổi string literal hoặc comment chỉ vì có cùng chuỗi.

### 13.2. Kiểm tra xung đột trước rename

Nếu đổi tên status thành state, cần kiểm tra:
- Có symbol state khác trong cùng scope không?
- Có tạo ambiguity ở scope con không?
- Có làm thay đổi binding do shadowing không?
- Có ảnh hưởng import/export hoặc public API không?
- Có tạo tên trùng trong generated model không?

Find References giúp người dùng xem phạm vi trước khi rename; rename provider cần tự kiểm tra conflict và trả edit an toàn.

### 13.3. Rename không thay thế Find References

Người dùng có thể chỉ muốn xem usage mà không thay đổi source. Find References phải là thao tác read-only và không được ghi file.

## 14. Hiển thị kết quả trong editor

Một panel kết quả hữu ích nên có:
- Tên symbol đang được tìm.
- Loại symbol và declaration location.
- Phạm vi tìm kiếm.
- Số lượng kết quả.
- Nhóm theo file hoặc project.
- Dòng preview có highlight identifier.
- Loại reference nếu có.
- Trạng thái đang tìm, hoàn tất, hủy hoặc lỗi.

Ví dụ:

~~~text
References to customerLimit (Variable)
Workspace: 3 files, 4 references

pricing.dsl
  1. line 4, column 18  declaration
  2. line 12, column 24 read

alerts.dsl
  3. line 8, column 15 read

checkout.dsl
  4. line 31, column 9 read
~~~

### 14.1. Điều hướng

Khi người dùng chọn một kết quả, editor mở đúng document và đặt con trỏ hoặc selection vào range của reference.

Nếu file đã bị xóa hoặc thay đổi, editor nên báo kết quả không còn hợp lệ và có thể yêu cầu tìm lại.

### 14.2. Nhóm và lọc

Workspace lớn có thể trả hàng nghìn references. UI nên:
- Nhóm theo file.
- Có thể thu gọn nhóm.
- Lọc theo read/write/call/type.
- Hiển thị kết quả theo thứ tự ổn định.
- Hỗ trợ load thêm hoặc virtualize danh sách lớn.

### 14.3. Empty state

Nếu không có reference ngoài declaration, UI nên nói rõ không tìm thấy usage trong phạm vi đã chọn. Không nên hiển thị trạng thái lỗi nếu truy vấn thành công nhưng kết quả rỗng.

### 14.4. Progress và cancellation

Truy vấn workspace lớn có thể mất thời gian. UI nên có progress indicator và khả năng hủy. Nếu kết quả đến theo từng batch, cần đánh dấu rõ kết quả partial cho đến khi hoàn tất.

## 15. Xử lý lỗi và kết quả không đầy đủ

Find References có thể không trả được kết quả đầy đủ trong một số tình huống:
- File chưa được parse.
- Semantic analysis đang chạy.
- Module dependency chưa tải.
- Reference index stale.
- Workspace có file bị exclude.
- Parser gặp lỗi và không resolve được một số symbol.
- Generated source không có source map.
- File không có quyền đọc.

Editor cần phân biệt:
- **No references:** truy vấn thành công, không có usage.
- **Partial results:** chỉ một phần workspace đã được index hoặc resolve.
- **Unresolved symbol:** không xác định được symbol tại con trỏ.
- **Indexing:** đang xây dựng index.
- **Cancelled:** người dùng hoặc client đã hủy.
- **Failed:** truy vấn thất bại do lỗi hệ thống.

Không nên trả danh sách rỗng cho mọi tình huống vì người dùng sẽ hiểu nhầm rằng symbol không được sử dụng.

### 15.1. Partial semantic model

Nếu source có syntax error, parser có thể tạo recovery AST. Một số reference vẫn resolve được. Editor có thể trả kết quả partial nếu có thể phân biệt mức độ chắc chắn.

Nếu một identifier không resolve, không nên đoán symbol chỉ dựa trên tên để bổ sung vào kết quả chính thức. Có thể cung cấp text search như thao tác riêng.

### 15.2. Workspace chưa hoàn tất indexing

Khi mở project lần đầu, index có thể chưa đầy đủ. UI nên thông báo đang index hoặc cho biết phạm vi kết quả. Sau khi indexing hoàn tất, có thể cập nhật kết quả.

## 16. Hiệu năng và khả năng mở rộng

Chi phí Find References phụ thuộc kích thước workspace, độ phức tạp semantic resolution và cách lưu index.

Các nguyên tắc:
- Index references theo stable symbol ID.
- Index document theo URI để thay thế hoặc xóa nhanh.
- Cache symbol resolution khi dependency không thay đổi.
- Chỉ re-index document bị sửa và các dependency bị ảnh hưởng.
- Dùng background indexing cho file chưa mở.
- Hỗ trợ cancellation.
- Tránh đọc toàn bộ file từ disk mỗi lần truy vấn.
- Phân trang hoặc stream kết quả lớn.
- Giới hạn memory và số result giữ trong UI.
- Đo latency p50/p95 trên workspace thực tế.

Với index phù hợp, lookup theo symbol có thể gần O(1) trung bình, sau đó chi phí chủ yếu phụ thuộc số reference trả về R và bước lọc/sắp xếp. Nếu không có index, hệ thống có thể phải duyệt O(N) node hoặc nhiều file cho mỗi request.

### 16.1. Background indexing

Indexing có thể chạy nền và ưu tiên:
1. File đang mở.
2. Module hiện tại.
3. Dependency trực tiếp.
4. Phần còn lại của workspace.

Cách này giúp Find References có ích sớm mà không phải chờ toàn workspace hoàn tất.

### 16.2. Kết quả lớn

Một symbol public có thể được tham chiếu hàng chục nghìn lần. Server nên cân nhắc streaming, pagination hoặc giới hạn có thông báo. Nếu giới hạn kết quả, phải nói rõ kết quả bị cắt và cách tải phần tiếp theo.

### 16.3. Cache invalidation

Cache phải được vô hiệu hóa khi:
- Declaration đổi tên hoặc loại.
- Scope thay đổi.
- Import/export thay đổi.
- Metamodel hoặc DSL version đổi.
- Compiler flags hoặc semantic configuration đổi.
- Dependency source thay đổi.

Cache sai có thể nguy hiểm hơn cache miss vì editor sẽ chỉ ra vị trí tham chiếu không còn đúng.

## 17. Bảo mật và quyền riêng tư

Workspace có thể chứa file nhạy cảm hoặc module người dùng không có quyền đọc.

Find References cần tuân thủ:
- Quyền truy cập file và project.
- Tenant isolation.
- Quyền đọc dependency source.
- Chính sách exclude file.
- Quyền hiển thị source preview.
- Quyền truy cập generated artifact.

Không nên để truy vấn trên symbol của tenant này trả location thuộc tenant khác chỉ vì dùng chung index backend.

### 17.1. Không tiết lộ đường dẫn hoặc nội dung

Nếu người dùng không có quyền xem file, editor không nên trả đường dẫn, line preview hoặc symbol metadata có thể tiết lộ thông tin. Reference index phải áp dụng access filter trước khi trả kết quả.

### 17.2. Generated và external resources

Một symbol có thể được tham chiếu từ generated code hoặc dependency. Cần quy định có hiển thị vị trí ngoài workspace hay không và quyền nào cho phép điều đó.

### 17.3. Resource exhaustion

Một truy vấn có thể tạo lượng kết quả rất lớn. Cần giới hạn:
- Số file được index đồng thời.
- Số result được buffer.
- Thời gian truy vấn.
- Bộ nhớ cho index.
- Số request đồng thời.
- Kích thước source preview.

Cancellation phải giải phóng tài nguyên và không để request cũ tiếp tục chạy vô hạn.

## 18. API và kiến trúc triển khai

Một API nội bộ có thể có dạng:

~~~java
interface ReferenceService {
    ReferenceResult findReferences(
        DocumentUri document,
        Position position,
        SearchScope scope,
        boolean includeDeclaration,
        CancellationToken cancellation
    );
}
~~~

ReferenceResult có thể chứa:
- Symbol metadata.
- Declaration location.
- Reference locations.
- Search scope.
- Completeness status.
- Document versions.
- Diagnostic hoặc reason nếu không thể resolve.

### 18.1. Các thành phần chính

~~~text
Editor Client
     |
     v
Language Server
     |
     +---- Document Store
     |
     +---- Parser / Semantic Analyzer
     |
     +---- Symbol Resolver
     |
     +---- Reference Index
     |
     +---- Workspace Indexer
     |
     +---- Reference Query Service
     |
     v
Locations / Result Panel
~~~

- **Document store:** giữ buffer và version của file đang mở.
- **Parser:** tạo AST hoặc syntax tree.
- **Semantic analyzer:** resolve reference và xác định symbol identity.
- **Reference index:** ánh xạ symbol sang source locations.
- **Workspace indexer:** phân tích file chưa mở và dependency.
- **Query service:** áp dụng scope, loại reference và includeDeclaration.
- **LSP adapter:** chuyển request/response sang protocol của editor.

### 18.2. Phân tách protocol và semantics

Không nên đặt logic tìm symbol trực tiếp trong lớp xử lý LSP. Query service nên độc lập với protocol để có thể dùng cho IDE, CLI hoặc web editor khác.

LSP adapter chỉ chịu trách nhiệm:
- Chuyển position và URI.
- Kiểm tra capability.
- Gọi reference service.
- Chuyển location về response.
- Xử lý cancellation và lỗi protocol.

### 18.3. Read-only operation

Find References là thao tác truy vấn. Nó không sửa source model, file hay index theo cách làm thay đổi semantics. Việc cập nhật index nền là trách nhiệm của document analysis và workspace indexer, không phải side effect của mỗi lần truy vấn.

## 19. Kiểm thử Find References

### 19.1. Kiểm thử scope và shadowing

Input:

~~~text
let status = "GLOBAL"

rule "local" {
    let status = "LOCAL"
    print(status)
}

print(status)
~~~

Các test cần xác nhận:
- Find References trên local declaration chỉ trả local usage.
- Find References trên global declaration chỉ trả global usage.
- Declaration có được bao gồm theo includeDeclaration hay không.
- Không nhầm hai symbol cùng tên.

### 19.2. Kiểm thử cross-file

Tạo hai file:
- File A khai báo và export một symbol.
- File B import và sử dụng symbol đó.

Xác nhận workspace search trả đúng reference, file scope không trả kết quả ngoài file và module visibility được tôn trọng.

### 19.3. Kiểm thử reference role

Với assignment và call:
- Read reference được phân loại read.
- Write reference được phân loại write.
- Call reference được phân loại call.
- Type reference được phân loại type.
- Một vị trí read-write có thể có role phù hợp với semantics của DSL.

### 19.4. Kiểm thử LSP position

Kiểm tra:
- Vị trí đầu và cuối identifier.
- Cursor ở giữa identifier.
- UTF-8/UTF-16 position encoding.
- Ký tự tiếng Việt có dấu.
- Ký tự ngoài BMP.
- Range không vượt document length.

### 19.5. Kiểm thử incremental index

Các tình huống:
- Thêm reference.
- Xóa reference.
- Đổi tên declaration.
- Thay đổi import.
- Di chuyển declaration giữa scope.
- Đóng file không save.
- Save file mới.
- Analysis cũ hoàn tất sau analysis mới.

Kết quả Find References phải khớp semantic model của document version mới nhất.

### 19.6. Kiểm thử cancellation và partial result

Xác nhận:
- Request bị hủy không tiếp tục tiêu thụ tài nguyên quá mức.
- Kết quả cũ không ghi đè request mới.
- Partial result được đánh dấu rõ.
- Workspace indexing chưa xong không bị báo thành no references.

### 19.7. Kiểm thử quyền truy cập

Xác nhận kết quả không tiết lộ file ngoài quyền, tenant khác hoặc source preview bị hạn chế. Kiểm tra cả đường dẫn và metadata, không chỉ nội dung dòng code.

## 20. Những sai lầm thường gặp

1. **Tìm theo chuỗi thay vì symbol:** đưa vào kết quả những identifier cùng tên nhưng thuộc scope khác.
2. **Không resolve alias/import:** bỏ sót reference qua namespace hoặc alias.
3. **Dùng line number làm symbol identity:** index hỏng khi chèn hoặc xóa dòng.
4. **Không gắn document version:** trả range stale sau khi file thay đổi.
5. **Không phân biệt declaration và usage:** người dùng khó hiểu kết quả.
6. **Không xử lý shadowing:** nhầm symbol cục bộ với symbol bên ngoài.
7. **Gộp Find References với Rename:** thao tác xem kết quả vô tình làm thay đổi file.
8. **Không báo partial indexing:** danh sách rỗng bị hiểu là không có usage.
9. **Không hỗ trợ cancellation:** request cũ tiếp tục chạy sau khi người dùng đã gõ tiếp.
10. **Không chuyển đổi position encoding:** highlight sai khi source có Unicode.
11. **Không kiểm soát cardinality và memory:** symbol phổ biến làm result panel hoặc server quá tải.
12. **Bỏ qua quyền truy cập:** rò rỉ đường dẫn hoặc nội dung từ module khác.
13. **Index generated code không có provenance:** kết quả khó truy ngược về source.
14. **Không invalidation dependency:** thay đổi import hoặc declaration nhưng reference index vẫn cũ.

## 21. Quy trình triển khai chức năng Find References

Một quy trình triển khai có thể gồm:

1. **Xác định symbol kinds:** liệt kê biến, function, type, property, rule, state và domain entity cần hỗ trợ.
2. **Định nghĩa semantics:** xác định declaration, definition, read, write, call, type reference và alias.
3. **Xây symbol identity:** dùng stable ID gắn với declaration và scope.
4. **Tích hợp semantic resolver:** resolve identifier và tạo reference edges.
5. **Xây document index:** lưu reference locations theo document version.
6. **Xây workspace index:** kết hợp module, import, dependency và file chưa mở.
7. **Thiết kế query API:** position, scope, includeDeclaration và cancellation.
8. **Tích hợp editor/LSP:** chuyển position và trả Location records.
9. **Thiết kế result UI:** nhóm theo file, preview, highlight, progress và empty state.
10. **Hỗ trợ incremental update:** re-index document và invalidation dependency.
11. **Áp dụng access control:** lọc file và metadata theo quyền.
12. **Kiểm thử:** scope, shadowing, cross-file, Unicode, versioning, cancellation và permission.
13. **Đo hiệu năng:** latency truy vấn, thời gian indexing, memory và số result.
14. **Theo dõi chất lượng index:** ghi nhận trạng thái indexing và lỗi resolve để người dùng hiểu độ đầy đủ của kết quả.

## 22. Kết luận

Find References trong DSL editor tìm các vị trí đang tham chiếu đến cùng một symbol đã được semantic analyzer resolve. Chức năng này khác text search vì nó hiểu declaration, scope, shadowing, import, alias và loại symbol. Kết quả có thể bao gồm declaration, read/write/call/type references tùy semantics và tùy chọn của editor.

Một triển khai đáng tin cậy cần stable symbol identity, reference index theo document và symbol, workspace indexing, document versioning, incremental invalidation, source ranges chính xác và tích hợp protocol như LSP. UI phải phân biệt kết quả rỗng với kết quả partial hoặc symbol chưa resolve; hệ thống cũng cần cancellation, access control và giới hạn tài nguyên. Khi những phần này được phối hợp, người dùng có thể hiểu phạm vi sử dụng của một symbol và thay đổi DSL an toàn hơn.

