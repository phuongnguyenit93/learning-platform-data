# Tái cấu trúc

Khi một mô hình hoặc chương trình được viết bằng ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) phát triển theo thời gian, người dùng thường cần đổi tên thành phần, tách một biểu thức dài, gom các bước lặp lại, di chuyển khai báo sang module khác hoặc thay đổi chữ ký của một operation. Những thay đổi này nhằm làm cấu trúc chương trình rõ ràng hơn mà vẫn giữ nguyên hành vi đã được xác định. Trong kỹ thuật phần mềm, hoạt động đó được gọi là **tái cấu trúc (refactoring)**.

Trong trình soạn thảo DSL, tái cấu trúc là nhóm thao tác phân tích mã nguồn và áp dụng các chỉnh sửa có hiểu biết về cú pháp, phạm vi, kiểu và quan hệ giữa các ký hiệu. Một thao tác đổi tên không nên chỉ thay mọi chuỗi giống nhau; nó cần xác định chính xác khai báo và các tham chiếu đến khai báo đó. Một thao tác di chuyển entity cần cập nhật import và tham chiếu liên quan. Một thao tác trích xuất biểu thức cần giữ đúng thứ tự đánh giá, kiểu dữ liệu và phạm vi biến.

Tái cấu trúc tốt giúp chương trình dễ đọc, dễ mở rộng và dễ bảo trì. Để làm được điều đó, editor cần phối hợp parser, AST hoặc concrete syntax tree, symbol table, type checker, source map và cơ chế chỉnh sửa tài liệu. Các thao tác cũng cần có quy tắc an toàn, xem trước thay đổi, xử lý xung đột và hỗ trợ hoàn tác.

Bài học này trình bày nguyên tắc tái cấu trúc trong editor DSL, các thao tác thường gặp, cách phân tích và tạo workspace edit, giới hạn an toàn, tích hợp Language Server, kiểm thử và một quy trình triển khai thực tế.

## 1. Tái cấu trúc là gì?

Tái cấu trúc là thay đổi cấu trúc bên trong của chương trình mà không chủ ý thay đổi hành vi quan sát được của chương trình đó trong những điều kiện đã xác định.

Ví dụ, một query có biểu thức điều kiện dài:

~~~text
query eligibleOrders {
  from Order
  where status == PAID
    and total >= minimumAmount
    and customer.active == true
}
~~~

Có thể trích điều kiện kiểm tra khách hàng thành một hàm:

~~~text
function isActiveCustomer(customer: Customer): Boolean {
  return customer.active == true
}

query eligibleOrders {
  from Order
  where status == PAID
    and total >= minimumAmount
    and isActiveCustomer(customer)
}
~~~

Mục đích là đặt tên cho một khái niệm có ý nghĩa. Tuy nhiên, thao tác chỉ là refactoring nếu biểu thức mới có cùng semantics trong mọi context mà query được phép chạy. Nếu hàm mới đọc một binding khác, thay đổi thứ tự gọi hàm hoặc xử lý null khác trước, hành vi có thể thay đổi.

### 1.1. Tái cấu trúc khác với sửa lỗi và bổ sung tính năng

Ba hoạt động này có mục tiêu khác nhau:

| Hoạt động | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Refactoring | Cải thiện cấu trúc, giữ hành vi | Đổi tên operation và cập nhật mọi tham chiếu |
| Bug fix | Sửa hành vi sai | Sửa điều kiện khiến đơn hàng bị từ chối nhầm |
| Feature change | Bổ sung hoặc thay đổi hành vi | Thêm trạng thái REFUNDED vào vòng đời đơn hàng |

Một thay đổi có thể kết hợp nhiều mục tiêu, nhưng editor nên làm rõ thao tác nào đang được thực hiện. Nếu một người dùng chọn Rename, editor không nên âm thầm thay đổi logic hoặc chuẩn hóa các giá trị nghiệp vụ khác.

### 1.2. Tái cấu trúc có hiểu biết về ngôn ngữ

Một trình soạn thảo văn bản thông thường chỉ biết vị trí ký tự. Một DSL editor có thể biết:

- Token nào là identifier, keyword, literal hoặc operator.
- Một identifier đang tham chiếu đến symbol nào.
- Khai báo thuộc scope hoặc namespace nào.
- Kiểu của biểu thức và tham số.
- Quan hệ giữa entity, property, workflow và action.
- Import nào cần cập nhật khi di chuyển khai báo.
- Vị trí nguồn của từng node trong AST.

Nhờ thông tin đó, editor có thể thực hiện thay đổi có chọn lọc và giải thích vì sao một tham chiếu được sửa.

### 1.3. Hành vi quan sát được

Hành vi của DSL có thể bao gồm nhiều yếu tố hơn giá trị trả về:

- Giá trị biểu thức.
- Thứ tự thực hiện action.
- Tác động phụ và lời gọi dịch vụ.
- Ngoại lệ hoặc diagnostic runtime.
- Quyền truy cập và ranh giới transaction.
- Thứ tự phát sự kiện.
- Kết quả serialization.
- Khả năng tương thích với các chương trình hoặc consumer khác.

Vì vậy, tính đúng đắn của refactoring phụ thuộc semantics mà DSL định nghĩa. Một phép biến đổi tương đương về mặt cú pháp chưa chắc tương đương về hành vi.

## 2. Vai trò của editor trong tái cấu trúc

Editor là nơi người dùng yêu cầu thao tác và xem kết quả. Nó có thể tự phân tích tài liệu hoặc gửi yêu cầu đến Language Server để thực hiện refactoring.

Một kiến trúc điển hình:

~~~text
Người dùng chọn phần mã
        |
        v
Editor / Language Server Client
        |
        v
Phân tích tài liệu và workspace
        |
        +--> Parser / AST
        +--> Symbol Table
        +--> Type Information
        +--> Dependency Index
        |
        v
Refactoring Engine
        |
        v
Edit Plan / Workspace Edit
        |
        v
Preview và xác nhận
        |
        v
Áp dụng chỉnh sửa
        |
        v
Phân tích lại và cập nhật diagnostics
~~~

Refactoring engine cần sử dụng cùng quy tắc cú pháp và ngữ nghĩa với compiler hoặc runtime. Nếu editor và compiler hiểu scope khác nhau, Rename hoặc Move có thể tạo mã mà editor coi là hợp lệ nhưng compiler lại phân giải sang symbol khác.

### 2.1. Tài liệu hiện tại và toàn workspace

Một số thao tác chỉ cần tài liệu đang mở. Ví dụ, Extract Variable thường sửa một vùng trong một file.

Các thao tác khác cần quét nhiều file:

- Rename symbol được tham chiếu từ nhiều module.
- Move entity sang namespace khác.
- Đổi chữ ký operation được gọi ở nhiều nơi.
- Đổi tên enum value được dùng trong nhiều schema.
- Di chuyển file và cập nhật import.

Editor cần phân biệt thao tác document-level với workspace-level. Không nên hiển thị rằng Rename hoàn tất nếu chỉ cập nhật file đang mở trong khi các tham chiếu khác vẫn còn.

### 2.2. Refactoring engine và giao diện người dùng

Giao diện có thể cung cấp các mục như:

- Rename.
- Extract Variable.
- Extract Function hoặc Operation.
- Inline Variable.
- Inline Function.
- Move Declaration.
- Change Signature.
- Convert to Named Parameter.
- Organize Imports.

Tên và danh sách thao tác phụ thuộc DSL. Không phải mọi phép refactoring của ngôn ngữ lập trình tổng quát đều có ý nghĩa trong DSL miền nghiệp vụ.

### 2.3. Khả năng hỗ trợ một phần

Một editor có thể hỗ trợ Rename đầy đủ nhưng chỉ hỗ trợ Extract Function cho một số loại biểu thức. Điều này tốt hơn việc cung cấp thao tác có tên hấp dẫn nhưng không thể bảo đảm semantics.

Nếu engine không đủ thông tin để thực hiện an toàn, editor nên giải thích giới hạn và đề xuất chỉnh sửa thủ công có hướng dẫn.

## 3. Các cấu trúc nền tảng cần có

Refactoring phụ thuộc vào mô hình cú pháp và ngữ nghĩa mà editor xây dựng.

### 3.1. AST và source range

AST biểu diễn cấu trúc có ý nghĩa của chương trình. Mỗi node nên giữ source range để editor biết node tương ứng với đoạn ký tự nào.

Ví dụ:

~~~text
Expression
  BinaryExpression
    left: PropertyAccess
      receiver: NameReference("order")
      property: "total"
    operator: ">="
    right: NameReference("minimumTotal")
~~~

Nếu node giữ vị trí nguồn, editor có thể thay đúng đoạn biểu thức hoặc identifier. Nếu chỉ có AST không có source range, engine phải tìm lại văn bản bằng cách so khớp chuỗi, dễ sửa nhầm khi cùng một đoạn xuất hiện nhiều lần.

### 3.2. Concrete syntax tree và trivia

AST thường loại bỏ dấu ngoặc, comment, khoảng trắng và một số chi tiết cú pháp. Refactoring cần giữ những phần này khi có thể.

Concrete Syntax Tree (CST) hoặc token stream có trivia có thể lưu:

- Comment.
- Whitespace.
- Dấu phân cách.
- Dấu ngoặc.
- Cách viết literal.
- Vị trí và khoảng ký tự.

Ví dụ, hai khai báo có AST tương tự nhưng comment và format khác nhau:

~~~text
// Giá trị tối thiểu để chấp nhận đơn hàng
constant minimumTotal = 100000
~~~

Nếu refactoring thay toàn bộ node bằng một đoạn text được format lại, comment có thể bị mất. CST hoặc cơ chế giữ trivia giúp bảo toàn nội dung không thuộc semantics.

### 3.3. Symbol table

Symbol table liên kết khai báo với tham chiếu:

~~~text
Symbol
  id
  name
  kind
  declaringScope
  type
  declarationLocation
  references
~~~

Mỗi lần xuất hiện của identifier có thể được gắn với Symbol ID. Rename dùng danh tính symbol để tìm đúng references, kể cả khi nhiều scope có biến cùng tên.

### 3.4. Type information

Các phép Extract hoặc Inline thường cần kiểu của biểu thức. Ví dụ, khi trích xuất biểu thức order.total * quantity, engine cần biết kiểu kết quả để tạo khai báo biến hoặc chữ ký hàm phù hợp.

Type information cũng giúp kiểm tra phép biến đổi có làm thay đổi overload resolution hoặc conversion hay không.

### 3.5. Dependency graph

Một declaration có thể được tham chiếu từ nhiều module hoặc được dùng trong schema và workflow. Dependency graph giúp engine xác định phạm vi cập nhật khi di chuyển hoặc thay đổi chữ ký.

Graph cần thể hiện loại phụ thuộc, chẳng hạn:

- Type reference.
- Function call.
- Property access.
- Import.
- Inheritance.
- Schema reference.
- Generated artifact dependency.

Không phải mọi dependency đều được cập nhật giống nhau.

## 4. Quy trình chung của một thao tác refactoring

Một thao tác refactoring có thể được mô hình hóa thành các giai đoạn:

1. Xác định phần tử hoặc vùng mã được chọn.
2. Phân tích cú pháp và ngữ nghĩa cần thiết.
3. Kiểm tra điều kiện áp dụng.
4. Tính tập vị trí bị ảnh hưởng.
5. Tạo kế hoạch chỉnh sửa.
6. Kiểm tra xung đột và tính hợp lệ.
7. Hiển thị preview nếu phù hợp.
8. Áp dụng chỉnh sửa theo cách nhất quán.
9. Phân tích lại và cập nhật diagnostics.
10. Hỗ trợ undo hoặc khôi phục nếu cần.

### 4.1. Preconditions

Precondition là điều kiện phải đúng trước khi phép biến đổi được áp dụng.

Ví dụ Rename:

- Con trỏ đang nằm trên một identifier được phân giải.
- Tên mới hợp lệ theo grammar.
- Tên mới không xung đột trong scope đích.
- Tất cả reference cần sửa đều có thể xác định.
- Không có file phụ thuộc đang ở trạng thái không thể chỉnh sửa.

Ví dụ Extract Function:

- Vùng chọn tạo thành một hoặc nhiều node cú pháp hợp lệ.
- Không cắt ngang cấu trúc không thể tách.
- Các biến được dùng trong vùng chọn có thể trở thành tham số hoặc capture hợp lệ.
- Luồng return và control flow có thể biểu diễn trong hàm mới.

### 4.2. Postconditions

Postcondition mô tả trạng thái cần đạt sau khi áp dụng:

- Chỉ symbol được chọn đổi tên.
- Các reference đã phân giải đến symbol đó được cập nhật.
- Không phát sinh xung đột tên mới.
- AST vẫn parse được.
- Các liên kết ngữ nghĩa vẫn trỏ đến đúng khai báo.
- Các file được chỉnh sửa đồng bộ.

Postcondition có thể được kiểm tra trước khi commit edit bằng cách áp dụng edit trên bản sao tài liệu hoặc mô hình tạm.

### 4.3. Edit plan

Không nên sửa từng file ngay khi engine tìm thấy reference đầu tiên. Hãy tạo một kế hoạch đầy đủ trước:

~~~text
RefactoringPlan
  operation: Rename
  targetSymbol: SymbolId(42)
  edits:
    - file: sales.dsl
      range: 12:8..12:16
      replacement: customerCode
    - file: report.dsl
      range: 4:18..4:26
      replacement: customerCode
  conflicts:
    - none
~~~

Edit plan có thể được hiển thị cho người dùng, kiểm tra, ghi log hoặc áp dụng như một đơn vị.

## 5. Rename: đổi tên symbol an toàn

Rename là một trong những thao tác phổ biến nhất. Người dùng chọn một khai báo hoặc tham chiếu, nhập tên mới và editor cập nhật các vị trí thuộc cùng symbol.

Ví dụ:

~~~text
entity Customer {
  property customerName: String
}

query activeCustomers {
  from Customer
  select customerName
}
~~~

Đổi customerName thành displayName cần cập nhật khai báo và tham chiếu tương ứng.

### 5.1. Vì sao không thể thay chuỗi toàn cục?

Giả sử DSL có hai scope:

~~~text
workflow processOrder {
  variable status = "NEW"

  step check {
    variable status = "READY"
    log(status)
  }

  publish(status)
}
~~~

Nếu Rename chỉ nhắm đến biến ở workflow, việc thay mọi chuỗi status trong file sẽ sửa nhầm biến cục bộ trong step check. Symbol resolution xác định từng reference thuộc khai báo nào.

### 5.2. Quy trình Rename

1. Xác định symbol tại vị trí con trỏ.
2. Kiểm tra loại symbol có hỗ trợ rename.
3. Thu thập declaration và references.
4. Xác thực tên mới theo quy tắc identifier của DSL.
5. Kiểm tra xung đột trong scope và namespace.
6. Cập nhật import hoặc alias nếu quy tắc yêu cầu.
7. Tạo workspace edit.
8. Áp dụng và phân tích lại workspace liên quan.

### 5.3. Kiểm tra tên mới

Tên mới có thể bị từ chối nếu:

- Là keyword dành riêng.
- Không phù hợp grammar.
- Trùng với khai báo khác trong cùng scope.
- Gây mơ hồ trong namespace.
- Làm một reference đổi nghĩa do shadowing.
- Vi phạm convention hoặc constraint của DSL.

Editor có thể hiển thị xung đột trước khi áp dụng thay đổi.

### 5.4. Rename từ reference

Người dùng có thể bắt đầu Rename tại một lần sử dụng thay vì tại declaration. Vì symbol table liên kết reference với symbol, editor vẫn có thể tìm đúng khai báo.

Nếu reference chưa phân giải do chương trình đang có lỗi, editor cần quyết định có hỗ trợ rename văn bản cục bộ hay không. Một chế độ textual rename nên được phân biệt rõ với semantic rename vì độ an toàn thấp hơn.

### 5.5. Tên được tạo hoặc tham chiếu gián tiếp

Một số DSL cho phép tên được tạo từ convention, reflection hoặc chuỗi literal:

~~~text
invokeByName("calculateTotal")
~~~

Nếu engine không thể chứng minh chuỗi này là reference đến symbol, nó không nên tự sửa một cách chắc chắn. Có thể cung cấp tùy chọn tìm kiếm textual occurrences để người dùng xem xét riêng.

### 5.6. Rename nhiều file

Khi symbol được import ở nhiều module, edit cần cập nhật mọi file liên quan. Nếu file ở trạng thái chỉ đọc hoặc có thay đổi đồng thời từ editor khác, thao tác cần xử lý version và báo xung đột thay vì ghi đè dữ liệu mới.

## 6. Extract Variable: trích xuất biến

Extract Variable đặt tên cho một biểu thức và thay biểu thức đó bằng biến mới.

Trước:

~~~text
query highValueOrders {
  from Order
  where order.total >= minimumAmount * exchangeRate
}
~~~

Sau:

~~~text
query highValueOrders {
  from Order
  let threshold = minimumAmount * exchangeRate
  where order.total >= threshold
}
~~~

Cú pháp let ở đây là ví dụ minh họa; DSL thực tế cần có quy tắc khai báo biến tương ứng.

### 6.1. Chọn vùng biểu thức

Editor cần xác định selection có tương ứng với một expression node hay không. Nếu vùng chọn chỉ cắt một phần token hoặc bao gồm hai expression không liên quan, thao tác có thể không hợp lệ.

Có thể hỗ trợ chọn một biểu thức bằng cách đặt con trỏ trong biểu thức mà không cần bôi đen toàn bộ. Engine chọn node nhỏ nhất hoặc lớn nhất theo quy tắc giao diện.

### 6.2. Xác định vị trí khai báo

Biến mới cần được khai báo tại scope mà mọi lần thay thế đều có thể truy cập. Đặt biến quá sâu khiến một số reference không nhìn thấy nó; đặt quá cao có thể làm thay đổi thời điểm đánh giá.

Ví dụ, nếu biểu thức phụ thuộc current row trong query, khai báo phải nằm trong scope của từng row hoặc một vị trí có cùng semantics.

### 6.3. Thứ tự đánh giá và tác động phụ

Xét biểu thức:

~~~text
calculateNextSequence() + calculateNextSequence()
~~~

Nếu hàm có tác động phụ, trích xuất thành một biến:

~~~text
let sequence = calculateNextSequence()
sequence + sequence
~~~

đã thay đổi số lần gọi từ hai xuống một. Đây không phải refactoring bảo toàn hành vi.

Với biểu thức thuần, có thể dễ chứng minh hơn rằng việc trích xuất không thay đổi kết quả. Với biểu thức có tác động phụ hoặc phụ thuộc thời gian, cần từ chối hoặc yêu cầu người dùng xác nhận một thay đổi hành vi riêng.

### 6.4. Chọn tên biến

Editor có thể đề xuất tên dựa trên biểu thức hoặc kiểu, nhưng cần cho người dùng sửa tên. Tên phải hợp lệ và không shadow hoặc xung đột với binding hiện có.

### 6.5. Kiểm tra kiểu

Kiểu của biến mới phải tương đương kiểu biểu thức. Nếu DSL hỗ trợ type inference, có thể sinh khai báo không ghi kiểu; nếu không, engine cần tạo type annotation.

## 7. Extract Function hoặc Operation

Extract Function chuyển một đoạn logic thành hàm hoặc operation riêng có tên.

Trước:

~~~text
workflow processOrder(order) {
  if order.total > 0 and order.customer.active {
    reserveInventory(order)
    chargePayment(order)
  }
}
~~~

Sau:

~~~text
function canProcess(order: Order): Boolean {
  return order.total > 0 and order.customer.active
}

workflow processOrder(order) {
  if canProcess(order) {
    reserveInventory(order)
    chargePayment(order)
  }
}
~~~

### 7.1. Xác định vùng có thể trích xuất

Vùng chọn cần tạo thành một cấu trúc cú pháp hợp lệ. Có thể trích xuất:

- Một biểu thức thành hàm trả về giá trị.
- Một nhóm câu lệnh thành operation.
- Một điều kiện thành predicate.
- Một nhóm bước workflow thành sub-workflow nếu DSL hỗ trợ.

Không phải mọi selection đều có thể trở thành hàm. Ví dụ, selection bắt đầu bên trong một if và kết thúc bên ngoài block có thể cắt ngang control flow.

### 7.2. Xác định input và output

Engine phân tích các biến được đọc và ghi trong vùng chọn:

- Biến được đọc nhưng khai báo bên ngoài có thể trở thành tham số hoặc captured variable.
- Biến được khai báo bên trong thường trở thành local variable của hàm mới.
- Giá trị được tạo trong vùng và dùng bên ngoài có thể trở thành return value.
- Nhiều output có thể cần một object kết quả hoặc cấu trúc tuple nếu DSL hỗ trợ.

Ví dụ:

~~~text
variable subtotal = calculateSubtotal(order)
variable tax = calculateTax(subtotal)
variable total = subtotal + tax
~~~

Nếu trích cả ba câu lệnh thành function, function có thể trả về total nếu đó là giá trị duy nhất được dùng bên ngoài. Nếu cả subtotal và tax còn được dùng, cần thiết kế kết quả chứa nhiều trường.

### 7.3. Control flow

Các lệnh return, break, continue, throw và early exit làm Extract phức tạp hơn.

Ví dụ:

~~~text
for item in items {
  if item.invalid {
    continue
  }
  process(item)
}
~~~

Nếu chỉ trích phần if vào một hàm, continue không thể tự động có cùng nghĩa trong hàm mới vì nó thuộc vòng lặp ở caller. Engine cần biến đổi thành giá trị điều khiển tường minh hoặc từ chối thao tác.

### 7.4. Tham số và capture

Nếu function mới nằm ở scope khác, các biến bên ngoài cần được truyền thành tham số hoặc capture theo semantics của DSL.

Ví dụ:

~~~text
function calculateDiscount(order: Order, customer: Customer): Decimal {
  ...
}
~~~

Engine cần xác định tham số theo symbol identity, không chỉ theo tên. Thứ tự tham số nên ổn định và dễ hiểu.

### 7.5. Tên và vị trí hàm mới

Hàm có thể được tạo trong module hiện tại, namespace gần nhất hoặc bên trong scope nếu DSL hỗ trợ nested function. Editor nên chọn vị trí không làm thay đổi visibility ngoài ý muốn.

## 8. Inline Variable và Inline Function

Inline thực hiện chiều ngược lại với Extract: thay reference bằng nội dung khai báo hoặc thân hàm.

### 8.1. Inline Variable

Trước:

~~~text
let threshold = minimumAmount * exchangeRate
where order.total >= threshold
~~~

Sau:

~~~text
where order.total >= minimumAmount * exchangeRate
~~~

Thao tác này chỉ an toàn nếu thay thế không làm thay đổi số lần đánh giá hoặc thời điểm đánh giá biểu thức.

Nếu biến được sử dụng ba lần và initializer là biểu thức thuần, Inline có thể nhân bản biểu thức ba lần mà vẫn giữ kết quả. Nếu initializer có tác động phụ, việc nhân bản sẽ thay đổi hành vi.

### 8.2. Inline Function

Trước:

~~~text
function isEligible(order: Order): Boolean {
  return order.total >= minimumAmount
}

where isEligible(order)
~~~

Sau:

~~~text
where order.total >= minimumAmount
~~~

Engine cần xử lý tham số, capture, overload và đệ quy. Một function có nhiều call site có thể được inline tại một nơi hoặc tất cả nơi tùy lựa chọn người dùng.

### 8.3. Giữ ngoặc và precedence

Khi inline biểu thức, cần thêm ngoặc khi cần để giữ precedence:

~~~text
let value = a + b
result = value * c
~~~

Inline đúng:

~~~text
result = (a + b) * c
~~~

Nếu bỏ ngoặc, kết quả trở thành a + (b * c), khác semantics.

### 8.4. Comment và formatting

Comment gắn với khai báo cần được xử lý có chủ đích. Khi inline, editor có thể giữ comment cạnh biểu thức, chuyển nó đến call site hoặc yêu cầu người dùng quyết định nếu không có vị trí tương đương.

## 9. Move Declaration: di chuyển khai báo

Move chuyển một declaration sang module, namespace hoặc file khác. Thao tác thường cần cập nhật import và reference.

Ví dụ:

~~~text
namespace sales {
  entity Customer {
    id: UUID
    name: String
  }
}
~~~

Di chuyển Customer sang namespace crm có thể tạo:

~~~text
namespace crm {
  entity Customer {
    id: UUID
    name: String
  }
}
~~~

Các module đang dùng Customer cần import hoặc dùng qualified name mới.

### 9.1. Kiểm tra visibility

Trước khi di chuyển, engine cần kiểm tra:

- Declaration có được export không?
- Scope đích có cho phép loại declaration này không?
- Các dependency có thể truy cập từ namespace mới không?
- Có circular dependency mới không?
- Có trùng tên ở namespace đích không?

### 9.2. Cập nhật reference

Các tham chiếu có thể được cập nhật theo một trong các cách:

- Thêm import vào module dùng.
- Thay tên thành qualified name.
- Dùng alias nếu có xung đột.
- Chuyển một nhóm declaration phụ thuộc cùng nhau.

Chính sách nên nhất quán với import style của DSL.

### 9.3. Di chuyển file

Nếu mỗi module tương ứng với file, Move cần cập nhật file path và metadata dự án. Cần bảo đảm tên module và vị trí file vẫn tuân theo quy ước của build system hoặc workspace.

### 9.4. Di chuyển một nhóm declaration

Một entity có thể phụ thuộc mạnh vào enum, type hoặc helper khác. Editor có thể đề xuất di chuyển cả nhóm hoặc chỉ di chuyển một declaration và cập nhật import.

Không nên tự động di chuyển mọi dependency nếu điều đó vượt quá ý định người dùng.

## 10. Change Signature: thay đổi chữ ký operation

Change Signature cho phép thêm, bỏ, đổi tên, đổi thứ tự hoặc đổi kiểu tham số của function, operation hay action.

Trước:

~~~text
function calculateTax(amount: Decimal, rate: Decimal): Decimal
~~~

Sau khi đổi thứ tự và thêm currency:

~~~text
function calculateTax(
  amount: Decimal,
  currency: Currency,
  rate: Decimal
): Decimal
~~~

Các call site cần được cập nhật theo symbol và quy tắc tham số.

### 10.1. Thêm tham số

Khi thêm tham số, editor cần biết giá trị cho các call site hiện có. Có thể:

- Dùng default value.
- Thêm argument placeholder để người dùng điền.
- Dùng named argument.
- Báo rằng một số call site không thể cập nhật tự động.

Không nên tự tạo một giá trị giả có thể làm sai nghiệp vụ.

### 10.2. Xóa tham số

Khi xóa tham số, cần xem thân hàm còn dùng binding đó không. Nếu còn, thao tác không hợp lệ cho đến khi logic được sửa hoặc tham số được thay bằng nguồn khác.

### 10.3. Đổi kiểu

Đổi kiểu tham số có thể khiến một số call site không còn hợp lệ. Engine cần dùng type checker để xác định argument có chuyển đổi hợp lệ không.

Nếu cần cast hoặc conversion, editor chỉ nên thêm khi quy tắc chuyển đổi được DSL định nghĩa rõ và bảo toàn ý nghĩa.

### 10.4. Đổi thứ tự và named arguments

Nếu DSL hỗ trợ named arguments, đổi thứ tự tham số có thể không ảnh hưởng call site đã dùng tên. Nếu call site dùng positional arguments, editor phải cập nhật thứ tự.

Ví dụ:

~~~text
calculateTax(amount = total, rate = taxRate)
~~~

Named arguments giúp thay đổi thứ tự declaration ít rủi ro hơn, nhưng vẫn cần cập nhật tên argument khi tham số đổi tên.

### 10.5. Overload và default parameter

Nếu có nhiều overload cùng tên, Change Signature cần xác định chính xác overload được sửa và các call site đang chọn overload đó. Thay đổi chữ ký có thể khiến một lời gọi chuyển sang overload khác; cần kiểm tra lại resolution sau khi tạo edit plan.

## 11. Organize Imports và tối ưu khai báo

Một editor DSL có thể cung cấp thao tác sắp xếp import và loại bỏ import không dùng.

Trước:

~~~text
import sales.Order
import crm.Customer
import sales.Order
import billing.Invoice

query activeOrders {
  from Order
}
~~~

Sau:

~~~text
import sales.Order

query activeOrders {
  from Order
}
~~~

Kết quả chính xác phụ thuộc quy ước import và namespace của DSL.

### 11.1. Xác định import được dùng

Không nên chỉ tìm chuỗi tên trong file. Một tên có thể xuất hiện trong comment hoặc string literal mà không phải reference. Engine cần dùng AST và symbol resolution.

### 11.2. Wildcard import

Nếu DSL hỗ trợ wildcard import, việc loại bỏ import có thể phức tạp vì một wildcard có thể cung cấp nhiều symbol. Engine cần xác định chính sách giữ wildcard hoặc thay bằng import tường minh.

### 11.3. Import mơ hồ

Nếu hai namespace export cùng tên, Organize Imports không được tự chọn một import tùy thứ tự. Nó cần giữ qualifier hoặc báo mơ hồ.

## 12. Các refactoring dành riêng cho DSL miền nghiệp vụ

DSL thường có khái niệm mà ngôn ngữ lập trình tổng quát không có. Editor có thể cung cấp thao tác dựa trên semantics miền.

### 12.1. Extract Query

Một query con được đặt tên để tái sử dụng:

Trước:

~~~text
from Order
where status == PAID and total > 0
select id
~~~

Sau:

~~~text
query payableOrders {
  from Order
  where status == PAID and total > 0
}

query paidOrderIds {
  from payableOrders
  select id
}
~~~

Engine cần kiểm tra query mới có giữ kiểu đầu ra, scope và filter semantics không.

### 12.2. Extract Workflow Step

Một nhóm step có thể được chuyển thành sub-workflow:

~~~text
workflow processOrder {
  step validate
  step reserve
  step charge
  step notify
}
~~~

Sau khi tách, sub-workflow cần nhận đúng input và công bố đúng output. Thứ tự thực thi, retry, transaction và compensation phải được giữ.

### 12.3. Extract Constraint

Các điều kiện lặp lại có thể trở thành constraint có tên:

Trước:

~~~text
where order.total >= 0 and order.tax >= 0
~~~

Sau:

~~~text
constraint nonNegativeAmounts {
  require Order.total >= 0
  require Order.tax >= 0
}
~~~

Việc chuyển predicate từ query sang constraint chỉ hợp lệ nếu DSL định nghĩa cùng semantics và thời điểm kiểm tra.

### 12.4. Convert Literal to Enum

Nếu một trường đang dùng các chuỗi lặp lại:

~~~text
status == "PENDING"
status == "PAID"
~~~

Editor có thể hỗ trợ tạo enum và thay các literal bằng enum value. Thao tác cần kiểm tra toàn bộ giá trị, serialization contract và consumer.

### 12.5. Extract Shared Type

Nếu nhiều entity có cùng cấu trúc địa chỉ, editor có thể trích thành value object:

~~~text
type Address {
  street: String
  city: String
  postalCode: String
}
~~~

Sau đó thay các trường lặp lại bằng Address. Engine cần xác định việc nhúng object có cùng semantics lưu trữ và serialization hay không.

### 12.6. Rename Domain Concept

Một thao tác đổi tên entity có thể ảnh hưởng:

- Type reference.
- Relationship endpoint.
- Query source.
- Workflow parameter.
- Schema definition.
- API operation.
- Tên bảng hoặc resource.
- Tài liệu và metadata.

Cần phân biệt rename symbol với đổi tên vật lý đã được công bố ra bên ngoài. Nếu tên là một phần của API hoặc database contract, có thể cần migration hoặc alias compatibility.

## 13. Text edit và workspace edit

Sau khi tính toán, engine cần biểu diễn các thay đổi để editor áp dụng.

### 13.1. Text edit

Text edit thay một khoảng văn bản trong một tài liệu bằng nội dung mới:

~~~text
TextEdit
  range
  newText
~~~

Range thường được tính theo line/character hoặc offset theo giao thức. Cần thống nhất encoding và quy tắc range giữa server và client.

### 13.2. Workspace edit

Workspace edit có thể chứa nhiều text edit ở nhiều tài liệu và thao tác file:

~~~text
WorkspaceEdit
  documentChanges:
    - edit sales.dsl
    - edit report.dsl
    - rename customer.dsl to crm/customer.dsl
~~~

Workspace edit phù hợp với Rename, Move và Change Signature trên nhiều file.

### 13.3. Sắp xếp edit theo vị trí

Nếu áp dụng nhiều edit trong cùng một file dựa trên offset ban đầu, nên áp dụng từ cuối file về đầu để thay đổi phía sau không làm lệch vị trí phía trước.

Một lựa chọn khác là dùng API workspace edit của editor có khả năng xử lý version và range theo giao thức. Không nên tự thay chuỗi liên tiếp mà không tính lại offset.

### 13.4. Version của tài liệu

Workspace edit nên gắn với document version mà engine đã phân tích. Nếu người dùng sửa file trong lúc server tính edit, version không còn khớp.

Client có thể từ chối edit cũ hoặc yêu cầu engine tính lại. Điều này tránh áp dụng range lên nội dung đã thay đổi.

### 13.5. Tính nguyên tử

Với thao tác nhiều file, người dùng kỳ vọng tất cả thay đổi cùng được áp dụng hoặc không có thay đổi nào. Khả năng atomicity phụ thuộc editor và giao thức.

Nếu client không hỗ trợ transaction thực sự, engine nên giảm nguy cơ bằng cách tạo edit plan đầy đủ, xác minh version và tránh thực hiện file operation trước khi các text edit sẵn sàng.

## 14. Preview, xác nhận và undo

Một thao tác có phạm vi lớn nên cho người dùng xem trước.

### 14.1. Preview

Preview có thể hiển thị:

- Danh sách file bị thay đổi.
- Declaration được sửa.
- References được cập nhật.
- Import được thêm hoặc bỏ.
- File được di chuyển.
- Conflict hoặc vị trí không thể cập nhật tự động.

Người dùng có thể xem diff theo file và chọn áp dụng hoặc hủy.

### 14.2. Inline rename preview

Với Rename cục bộ, editor có thể cập nhật trực tiếp các reference đang hiển thị khi người dùng nhập tên. Đây là trải nghiệm nhanh, nhưng cần giữ khả năng hủy nếu phát hiện conflict.

### 14.3. Undo

Undo nên hoàn tác toàn bộ refactoring như một đơn vị lịch sử nếu editor hỗ trợ. Với workspace edit nhiều file, việc chỉ undo file hiện tại có thể để lại trạng thái không nhất quán.

### 14.4. Lịch sử và audit

Trong môi trường có kiểm soát, có thể lưu operation, symbol được thay đổi, file bị tác động và người thực hiện. Không nhất thiết phải lưu toàn bộ nội dung source trong audit nếu đã có version control.

## 15. An toàn ngữ nghĩa và giới hạn của refactoring

Không phải phép biến đổi nào cũng có thể chứng minh an toàn trong mọi DSL. Engine cần đánh giá khả năng chứng minh và mức độ rủi ro.

### 15.1. Semantic equivalence

Hai chương trình tương đương nếu chúng có cùng hành vi quan sát được trong miền đầu vào và môi trường được xét theo đặc tả DSL.

Một refactoring có thể dựa vào các giả định:

- Hàm là pure.
- Biểu thức không ném lỗi.
- Binding không thay đổi.
- Không có dynamic lookup.
- Không có reflection.
- Không có macro hoặc code generation ẩn.
- Thứ tự đánh giá được xác định.

Nếu giả định không đúng hoặc không thể xác minh, engine không nên tuyên bố phép biến đổi hoàn toàn an toàn.

### 15.2. Side effects

Các action ghi dữ liệu, gửi sự kiện hoặc gọi API làm cho việc đổi thứ tự hoặc số lần đánh giá trở nên nhạy cảm.

Ví dụ:

~~~text
if reserveInventory(order) and chargePayment(order) {
  publishConfirmation(order)
}
~~~

Tách hai lời gọi thành biến hoặc đổi thứ tự có thể thay đổi hành vi. Refactoring engine cần biết effect metadata hoặc từ chối thao tác khi không thể chứng minh.

### 15.3. Exceptions và error behavior

Một biểu thức có thể phát sinh lỗi khi đánh giá. Di chuyển biểu thức sang vị trí khác có thể khiến lỗi xảy ra sớm hơn hoặc muộn hơn, hoặc nằm ngoài phạm vi catch.

Ví dụ, trích biểu thức khỏi nhánh if có thể khiến nó được tính ngay cả khi nhánh không chạy. Giá trị bình thường có thể giống nhau nhưng lỗi runtime khác nhau.

### 15.4. Nullability và short-circuit

Chuyển đổi biểu thức có thể làm thay đổi việc truy cập null hoặc việc bỏ qua vế phải của toán tử logic. Engine cần giữ thứ tự và short-circuit semantics.

### 15.5. Dynamic features

Reflection, string-based invocation, dynamic property access và macro có thể tạo reference mà static index không thấy. Khi các tính năng này tồn tại, Rename và Move có thể cần cảnh báo về các tham chiếu không thể xác định.

### 15.6. Refactoring có mức độ bảo đảm

Có thể phân loại:

- **Guaranteed:** engine có đủ thông tin để xác minh các điều kiện đã định nghĩa.
- **Conditionally safe:** cần người dùng xác nhận một hoặc nhiều giả định.
- **Textual:** chỉ thay đổi văn bản, không bảo đảm liên kết ngữ nghĩa.
- **Unsupported:** không thể tạo edit đáng tin cậy.

Giao diện nên trình bày mức bảo đảm phù hợp, tránh gọi một thao tác textual là semantic refactoring.

## 16. Comments, formatting và vùng được sinh tự động

Refactoring không chỉ thay đổi node cú pháp. Nó còn cần bảo toàn cách người dùng tổ chức tài liệu.

### 16.1. Comment gắn với node

Comment có thể đứng trước declaration, cuối dòng hoặc bên trong block. Engine cần quy tắc xác định comment thuộc node nào.

Ví dụ:

~~~text
// Số ngày tối đa để giữ đơn ở trạng thái chờ
constant pendingDays = 7
~~~

Khi di chuyển constant, comment có thể cần di chuyển cùng. Nếu comment chỉ mô tả block cha, không nên gắn nó vào declaration một cách máy móc.

### 16.2. Formatting

Sau refactoring, editor có thể format vùng thay đổi hoặc toàn bộ file. Format toàn file có thể tạo diff lớn và che khuất thay đổi thực sự.

Có thể ưu tiên giữ trivia và chỉ format đoạn mới, hoặc cho người dùng chọn Format Document riêng.

### 16.3. Generated region

Một số DSL cho phép sinh mã hoặc đánh dấu vùng do generator quản lý. Refactoring không nên sửa vùng được sinh nếu source of truth nằm ở mô hình DSL khác.

Editor có thể điều hướng người dùng đến source model hoặc hiển thị vùng đó ở chế độ read-only.

### 16.4. Comment trong code block và literal

Không tìm kiếm và thay thế tên trong comment hoặc string literal khi thực hiện semantic Rename, trừ khi DSL định nghĩa rõ đó là reference có ý nghĩa. Có thể cung cấp tùy chọn tìm textual occurrence riêng.

## 17. Tích hợp Language Server Protocol

Language Server Protocol (LSP) cung cấp các request phổ biến cho refactoring và chỉnh sửa mã.

Một số capability liên quan:

- Rename.
- Prepare Rename.
- Code Action.
- Workspace Edit.
- Document Changes.
- Execute Command.
- Formatting.
- References và Definition.

Tên request và chi tiết hỗ trợ phụ thuộc phiên bản LSP và client.

### 17.1. Prepare Rename

Prepare Rename cho phép server kiểm tra vị trí con trỏ có thể đổi tên không và trả về range hoặc placeholder phù hợp.

Server có thể từ chối nếu con trỏ nằm trên keyword, literal hoặc một reference chưa phân giải.

### 17.2. Rename request

Client gửi vị trí và tên mới. Server trả workspace edit chứa các vị trí cần sửa.

Server nên xác thực tên mới, kiểm tra conflict và cập nhật tất cả references đã biết.

### 17.3. Code Action

Các thao tác Extract, Inline, Move hoặc Convert có thể được cung cấp dưới dạng Code Action. Một action có thể có diagnostics liên quan hoặc chỉ xuất hiện khi con trỏ nằm trên node phù hợp.

### 17.4. Resolve action trì hoãn

Nếu có nhiều code action hoặc việc tính toán tốn kém, server có thể gửi action chưa có edit đầy đủ rồi resolve khi người dùng chọn. Điều này giúp editor hiển thị danh sách gợi ý nhanh hơn.

### 17.5. Server và client cùng quản lý tài liệu

LSP client thường quản lý buffer đang mở; server giữ bản sao nội dung đã đồng bộ. Workspace edit cần phù hợp version và URI. Với file chưa mở, server có thể cần đọc workspace hoặc dùng cơ chế file operation được client hỗ trợ.

### 17.6. Capability negotiation

Không phải client nào cũng hỗ trợ mọi loại workspace edit hoặc file operation. Server cần kiểm tra capability đã được thương lượng và có fallback phù hợp.

Không nên trả một edit chứa thao tác di chuyển file nếu client không hỗ trợ file rename theo giao thức.

## 18. Hiệu năng và phân tích gia tăng

Workspace lớn có thể chứa hàng nghìn file và nhiều reference. Refactoring engine cần cân bằng độ chính xác với thời gian phản hồi.

### 18.1. Index symbol và reference

Có thể duy trì index:

~~~text
SymbolIndex
  SymbolId -> declaration
  SymbolId -> references
  FileUri -> symbols
~~~

Khi file thay đổi, cập nhật phần index liên quan thay vì quét toàn workspace cho mọi thao tác.

### 18.2. Incremental parsing

Parser có thể phân tích lại vùng thay đổi và tái sử dụng node không bị ảnh hưởng. Tuy nhiên, một thay đổi ở declaration có thể ảnh hưởng name resolution của nhiều file, nên semantic index vẫn cần cập nhật dependency.

### 18.3. Giới hạn tìm kiếm

Với một số DSL có dynamic reference, có thể cần textual search bổ sung. Hãy phân biệt kết quả semantic references và textual matches để người dùng hiểu độ tin cậy.

### 18.4. Hủy tác vụ

Nếu người dùng đổi tên liên tục hoặc đóng tài liệu trong lúc engine đang tính edit, tác vụ cũ có thể bị hủy. Kết quả cũ không nên được áp dụng sau khi đã có yêu cầu mới.

### 18.5. Cache và invalidation

Cache symbol/reference giúp tăng tốc nhưng cần invalidation khi file, import, build configuration hoặc generated index thay đổi. Cache lỗi thời có thể nguy hiểm hơn việc chậm vì nó tạo edit sai.

## 19. Diagnostics và xử lý conflict

Một phép refactoring có thể thất bại do xung đột hoặc thiếu thông tin. Editor cần giải thích rõ.

### 19.1. Conflict tên

Ví dụ, đổi tên property total thành status trong cùng entity đã có property status. Engine nên từ chối hoặc yêu cầu người dùng giải quyết conflict.

### 19.2. Conflict import

Di chuyển Customer vào namespace đã có một Customer khác có thể làm tên không đủ rõ. Editor có thể đề xuất alias hoặc qualified reference.

### 19.3. Conflict kiểu

Change Signature có thể khiến một call site truyền String trong khi tham số mới yêu cầu Decimal. Engine có thể đánh dấu call site cần sửa thủ công.

### 19.4. Conflict quyền sửa file

Một file read-only, file không thuộc workspace hoặc file do extension khác quản lý có thể không được cập nhật. Editor nên liệt kê file bị bỏ qua và mức độ ảnh hưởng.

### 19.5. Conflict khi tài liệu thay đổi đồng thời

Nếu file thay đổi sau khi edit plan được tạo, range có thể không còn đúng. Server cần dùng version hoặc hash để phát hiện stale edit và tính lại.

### 19.6. Không che giấu thay đổi chưa hoàn tất

Nếu một refactoring chỉ cập nhật được một phần, editor cần báo trạng thái partial và liệt kê các vị trí còn lại. Không nên thông báo thành công toàn bộ.

## 20. Kiểm thử refactoring

Refactoring engine cần kiểm thử cả edit text lẫn semantics.

### 20.1. Golden edit tests

Mỗi test có:

- Input DSL.
- Vị trí hoặc selection.
- Refactoring operation.
- Tham số, chẳng hạn tên mới.
- Expected output.

Ví dụ Rename:

Input:

~~~text
entity Order {
  property total: Decimal
}
query orders {
  from Order
  select total
}
~~~

Operation: đổi tên property total thành amount.

Expected:

~~~text
entity Order {
  property amount: Decimal
}
query orders {
  from Order
  select amount
}
~~~

Test cần xác minh những symbol cùng tên nhưng khác scope không bị thay đổi.

### 20.2. Semantic tests

Sau khi áp dụng edit, phân tích và kiểm tra:

- AST hợp lệ.
- Name resolution vẫn trỏ đến đúng symbol.
- Type checking không phát sinh lỗi mới ngoài phạm vi được chấp nhận.
- Overload resolution không thay đổi ngoài ý muốn.
- Dependency graph được cập nhật.

### 20.3. Behavior tests

Với các phép Extract hoặc Inline có ảnh hưởng đến evaluation, có thể chạy chương trình trước và sau trên cùng bộ input và so sánh kết quả, diagnostics và side effects quan sát được.

Đây không phải chứng minh tương đương cho mọi input, nhưng là lớp kiểm tra thực tế hữu ích.

### 20.4. Negative tests

Kiểm tra thao tác bị từ chối khi:

- Tên mới không hợp lệ.
- Có duplicate declaration.
- Selection cắt ngang node.
- Biểu thức có side effect không thể bảo toàn.
- Function có control flow không thể trích xuất.
- File phụ thuộc không thể chỉnh sửa.
- Workspace version đã thay đổi.

### 20.5. Multi-file tests

Tạo workspace fixture có nhiều module, import, alias và references. Kiểm tra Rename, Move và Change Signature cập nhật toàn bộ file đúng cách.

### 20.6. Undo và redo tests

Áp dụng refactoring, undo và redo. So sánh nội dung tất cả tài liệu với trạng thái trước và sau thao tác.

### 20.7. Property-based tests

Có thể sinh các AST hoặc chương trình nhỏ theo grammar, áp dụng một refactoring hợp lệ rồi kiểm tra invariant như parse success, không có duplicate symbol và source map nhất quán.

## 21. Ví dụ triển khai Rename bằng symbol index

Một API đơn giản có thể tách bước lập kế hoạch khỏi bước áp dụng.

~~~java
record TextRange(int startOffset, int endOffset) {}

record TextEdit(
    String documentUri,
    TextRange range,
    String newText
) {}

record Symbol(
    String id,
    String name,
    String kind,
    String documentUri,
    TextRange declarationRange
) {}

record RenamePlan(
    String symbolId,
    String newName,
    List<TextEdit> edits
) {}
~~~

Refactoring engine:

~~~java
RenamePlan prepareRename(
    Symbol target,
    String newName,
    SymbolIndex index,
    ScopeModel scopes
) {
    validateIdentifier(newName);

    if (scopes.hasConflict(
        target.id(),
        target.declarationScope(),
        newName
    )) {
        throw new RefactoringConflict(
            "The new name conflicts with an existing declaration."
        );
    }

    List<Reference> references =
        index.referencesOf(target.id());

    List<TextEdit> edits = new ArrayList<>();

    edits.add(new TextEdit(
        target.documentUri(),
        target.declarationRange(),
        newName
    ));

    for (Reference reference : references) {
        edits.add(new TextEdit(
            reference.documentUri(),
            reference.range(),
            newName
        ));
    }

    return new RenamePlan(target.id(), newName, edits);
}
~~~

Đây là pseudocode mang tính minh họa. Implementation thực tế cần xử lý import, alias, file version, encoding, reference động, file read-only và workspace edit theo giao thức.

### 21.1. Áp dụng edit theo thứ tự

Nếu dùng offset trong cùng một file, có thể sắp xếp edit giảm dần theo startOffset:

~~~java
edits.sort(
    Comparator.comparingInt(
        edit -> edit.range().startOffset()
    ).reversed()
);
~~~

Sau đó áp dụng từ cuối file về đầu để offset ở phần trước không bị dịch chuyển bởi edit ở phần sau.

### 21.2. Kiểm tra sau khi áp dụng

Trước khi gửi edit cho client hoặc sau khi client áp dụng, server có thể phân tích lại nội dung mới trong một workspace snapshot và xác nhận:

- Tên mới phân giải đến cùng symbol identity logic.
- Không có reference nào còn trỏ đến tên cũ trong tập semantic references.
- Không xuất hiện duplicate declaration.
- Mọi import liên quan còn hợp lệ.

Nếu validation thất bại, engine nên hủy hoặc báo conflict thay vì áp dụng một edit không nhất quán.

## 22. Ví dụ tổng hợp: tái cấu trúc workflow đơn hàng

Giả sử DSL ban đầu:

~~~text
workflow processOrder(order: Order) {
  if order.customer.active == true
      and order.total > 0
      and order.items.size() > 0 {
    reserveInventory(order)
    chargePayment(order)
    publishConfirmation(order)
  }
}
~~~

Người dùng muốn cải thiện khả năng đọc và tái sử dụng.

### 22.1. Extract Function cho điều kiện

Editor trích điều kiện thành hàm:

~~~text
function canProcessOrder(order: Order): Boolean {
  return order.customer.active == true
      and order.total > 0
      and order.items.size() > 0
}
~~~

Workflow:

~~~text
workflow processOrder(order: Order) {
  if canProcessOrder(order) {
    reserveInventory(order)
    chargePayment(order)
    publishConfirmation(order)
  }
}
~~~

Engine cần xác minh hàm mới nhận đúng order và không thay đổi semantics của biểu thức.

### 22.2. Extract Workflow Step

Nếu DSL hỗ trợ sub-workflow, nhóm các thao tác thanh toán và thông báo có thể được tách:

~~~text
workflow completeOrder(order: Order) {
  chargePayment(order)
  publishConfirmation(order)
}
~~~

Workflow chính:

~~~text
workflow processOrder(order: Order) {
  if canProcessOrder(order) {
    reserveInventory(order)
    completeOrder(order)
  }
}
~~~

Thao tác này chỉ an toàn nếu thứ tự, transaction, retry và error handling của hai action được giữ nguyên.

### 22.3. Rename

Nếu canProcessOrder được đổi thành isOrderEligible, editor cần cập nhật declaration và tất cả call site đã phân giải đến symbol đó.

Một function khác cùng tên trong namespace khác không được đổi.

### 22.4. Preview và kiểm tra

Trước khi áp dụng, preview có thể liệt kê:

- Tạo function isOrderEligible trong module sales.
- Thay một biểu thức điều kiện trong processOrder.
- Tạo workflow completeOrder.
- Thay nhóm action bằng một lời gọi sub-workflow.
- Không có conflict tên hoặc import.
- Các source range liên quan.

Sau khi áp dụng, editor parse lại, kiểm tra kiểu, cập nhật references và chạy các kiểm thử phù hợp.

Ví dụ này cho thấy refactoring có thể kết hợp nhiều thao tác. Mỗi thao tác cần một edit plan và điều kiện semantics riêng để người dùng có thể hiểu và hoàn tác.

## 23. Những lỗi thiết kế thường gặp

**Thay chuỗi thay cho symbol.** Có thể sửa nhầm biến cùng tên trong scope khác. Hãy dùng symbol identity và reference index.

**Chỉ sửa file đang mở.** Rename hoặc Move có thể ảnh hưởng nhiều module. Hãy tính workspace edit đầy đủ.

**Không kiểm tra conflict trước khi áp dụng.** Tên mới có thể shadow hoặc làm mơ hồ một symbol khác. Hãy xác minh scope và namespace.

**Trích xuất biểu thức có side effect mà không giữ số lần đánh giá.** Có thể làm thay đổi hành vi. Hãy dùng effect information hoặc từ chối thao tác.

**Không xử lý control flow.** Return, break và continue có thể không còn cùng nghĩa sau Extract Function. Hãy phân tích luồng điều khiển trước khi tạo hàm mới.

**Inline mà bỏ ngoặc.** Precedence có thể thay đổi kết quả. Hãy dùng AST để render biểu thức với ngoặc cần thiết.

**Làm mất comment và formatting.** Thay toàn bộ node có thể xóa trivia. Hãy giữ CST hoặc có quy tắc di chuyển comment.

**Không kiểm tra version tài liệu.** Edit plan có thể dùng range cũ. Hãy xác minh document version trước khi áp dụng.

**Áp dụng nhiều file không nhất quán.** Một phần workspace có thể được sửa trong khi phần còn lại thất bại. Hãy tạo plan đầy đủ và dùng workspace edit có khả năng nhất quán.

**Không hỗ trợ undo toàn thao tác.** Người dùng khó khôi phục khi nhiều file bị thay đổi. Hãy nhóm edit thành một đơn vị lịch sử khi client hỗ trợ.

**Gọi textual rename là semantic rename.** Chuỗi trong comment, literal hoặc dynamic invocation có thể không phải reference. Hãy phân biệt mức bảo đảm.

**Không phân tích lại sau refactoring.** Mã có thể không parse hoặc type-check. Hãy xác minh kết quả trước khi báo thành công.

## 24. Quy trình xây dựng tính năng refactoring cho DSL editor

Một quy trình triển khai có thể gồm các bước:

### Bước 1: Xác định semantics của DSL

Ghi rõ scope, binding, overload, import, type, evaluation order, side effect, null và control flow. Refactoring dựa vào các quy tắc này.

### Bước 2: Xây nền tảng phân tích

Parser cần cung cấp AST và source range. Symbol resolver cần liên kết declaration với reference. Type checker và dependency index cung cấp thông tin cho các phép biến đổi.

### Bước 3: Chọn thao tác đầu tiên

Rename thường là điểm khởi đầu tốt vì có phạm vi tương đối rõ khi symbol resolution đáng tin cậy. Sau đó có thể mở rộng sang Extract Variable, Inline và Move.

### Bước 4: Định nghĩa preconditions và postconditions

Mỗi thao tác cần tài liệu hóa điều kiện áp dụng, conflict có thể xảy ra và invariant phải giữ.

### Bước 5: Tạo edit plan độc lập với UI

Refactoring engine nhận mô hình và trả edit plan. Editor quyết định cách preview, xác nhận và áp dụng. Điều này giúp engine dễ kiểm thử.

### Bước 6: Xử lý multi-file và document version

Dùng workspace edit, xác minh URI và version, xử lý file read-only và capability của client.

### Bước 7: Bảo toàn trivia và định dạng

Giữ comment, literal và formatting khi có thể. Chỉ format phạm vi cần thiết nếu người dùng không yêu cầu format toàn tài liệu.

### Bước 8: Kiểm tra semantics sau biến đổi

Parse lại, resolve lại symbol, type-check và kiểm tra các invariant. Với phép biến đổi có thể ảnh hưởng runtime, bổ sung behavior tests.

### Bước 9: Cung cấp preview, undo và diagnostics

Người dùng cần biết file nào thay đổi, lý do conflict và cách khôi phục thao tác.

### Bước 10: Mở rộng theo khả năng chứng minh

Chỉ cung cấp thao tác khi engine có đủ thông tin. Nếu không, hiển thị giới hạn hoặc chuyển thành code action yêu cầu người dùng hoàn thiện thủ công.

## 25. Kết luận

Tái cấu trúc trong DSL editor là quá trình thay đổi cấu trúc mã có hiểu biết về cú pháp và ngữ nghĩa, với mục tiêu giữ hành vi của chương trình theo đặc tả. Các thao tác phổ biến gồm Rename, Extract Variable, Extract Function, Inline, Move Declaration, Change Signature và Organize Imports. DSL miền nghiệp vụ còn có thể hỗ trợ Extract Query, Extract Workflow Step, Extract Constraint hoặc chuyển literal thành enum.

Một refactoring engine đáng tin cậy cần AST hoặc CST có source range, symbol table, type information, dependency index và edit plan. Engine phải kiểm tra precondition, conflict, thứ tự đánh giá, side effect, control flow, nullability và dynamic reference trước khi tạo workspace edit. Preview, document version, undo và phân tích lại giúp bảo vệ workspace khi áp dụng thay đổi.

Hãy bắt đầu với những thao tác có thể xác định chính xác symbol và reference, rồi mở rộng khi mô hình ngữ nghĩa đủ mạnh. Khi refactoring được thiết kế như một phép biến đổi có điều kiện rõ ràng và có thể kiểm tra, editor giúp người viết DSL cải thiện cấu trúc chương trình mà vẫn giữ được ý nghĩa nghiệp vụ.

