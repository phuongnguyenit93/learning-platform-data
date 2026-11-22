# Gợi ý sửa lỗi

## 1. Gợi ý sửa lỗi là gì?

Trong một ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL), trình phân tích cú pháp, bộ kiểm tra ngữ nghĩa hoặc runtime có thể phát hiện một vấn đề trong chương trình. **Gợi ý sửa lỗi (diagnostic repair suggestion)** là đề xuất cụ thể giúp người viết hiểu cách khắc phục vấn đề đó.

Ví dụ, người dùng viết:

~~~text
discount 10 precent
~~~

Parser hoặc bộ kiểm tra tên có thể phát hiện từ precent không phải đơn vị hợp lệ. Một diagnostic chỉ thông báo:

~~~text
Unknown unit: precent
~~~

cho biết điều gì sai. Một gợi ý hữu ích hơn có thể là:

~~~text
Unknown unit "precent". Did you mean "percent"?
~~~

Nếu công cụ biết chính xác vị trí và cách thay thế, nó có thể cung cấp một thao tác sửa:

~~~text
discount 10 percent
~~~

Gợi ý sửa lỗi giúp người dùng đi từ việc nhận biết vấn đề đến hành động khắc phục. Trong IDE, đề xuất có thể xuất hiện dưới dạng quick fix, code action, nút sửa lỗi hoặc danh sách lựa chọn. Trong CLI, nó có thể được hiển thị dưới dạng dòng lệnh, đoạn mã thay thế hoặc patch.

Một hệ thống tốt cần phân biệt:

- **Diagnostic:** mô tả vấn đề được phát hiện.
- **Suggestion:** đưa ra một hoặc nhiều cách có thể giải quyết vấn đề.
- **Text edit:** thay đổi cụ thể trên văn bản nguồn.
- **Code action:** thao tác mà người dùng có thể chọn, có thể chứa một hoặc nhiều text edit hoặc hành động khác.
- **Refactoring:** thay đổi cấu trúc chương trình nhằm cải thiện thiết kế, thường không nhằm sửa một diagnostic cụ thể.

Một diagnostic có thể không có gợi ý nếu công cụ không đủ thông tin để đề xuất an toàn. Ngược lại, một code action có thể được cung cấp theo ngữ cảnh dù không có lỗi, chẳng hạn tạo khai báo hoặc chuyển đổi cấu trúc.

## 2. Diagnostic tốt là nền tảng của gợi ý sửa lỗi

Không thể tạo gợi ý đáng tin cậy nếu diagnostic không xác định rõ vấn đề và vị trí nguồn.

Một diagnostic thường có:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Code | Mã lỗi ổn định để máy và công cụ nhận diện | DSL_UNKNOWN_UNIT |
| Severity | Mức độ nghiêm trọng | Error, Warning, Information |
| Message | Giải thích ngắn gọn | Unknown unit "precent" |
| Primary range | Vị trí chính của vấn đề | Từ ký tự đầu đến cuối từ precent |
| Related information | Vị trí liên quan | Nơi khai báo unit hợp lệ |
| Expected / actual | Giá trị mong đợi và giá trị gặp phải | percent / precent |
| Tags | Nhãn bổ sung | Deprecated, unnecessary |
| Data | Thông tin nội bộ phục vụ code action | SymbolId hoặc loại lỗi |

Diagnostic nên chỉ ra phần nguồn liên quan trực tiếp. Nếu cả dòng có lỗi nhưng chỉ một identifier sai, hãy đánh dấu identifier đó thay vì tô sáng cả file.

### 2.1 Mã lỗi ổn định

Không nên dùng toàn bộ câu thông báo làm định danh lỗi. Nội dung message có thể được biên tập hoặc dịch sang ngôn ngữ khác. Mã lỗi ổn định cho phép:

- Quick fix tìm đúng loại diagnostic.
- IDE nhóm và lọc lỗi.
- Tài liệu tham chiếu đến quy tắc cụ thể.
- Test xác nhận loại lỗi mà không phụ thuộc câu chữ.
- Chính sách suppress hoặc cấu hình severity theo mã.

Ví dụ:

~~~text
code = DSL_UNKNOWN_IDENTIFIER
message = Unknown identifier "custmer"
~~~

### 2.2 Vị trí nguồn chính xác

Một gợi ý sửa cần biết đoạn văn bản nào được thay đổi. Source range thường có vị trí bắt đầu và kết thúc:

~~~text
start = line 4, column 18
end   = line 4, column 25
~~~

Cần thống nhất cách đếm cột. Một số giao thức dùng UTF-16 code units, trong khi thư viện khác dùng byte offset hoặc Unicode code point. Nếu lexer, parser, editor và code action dùng quy ước khác nhau, thao tác sửa có thể thay nhầm ký tự, nhất là với văn bản Unicode.

### 2.3 Related information

Một diagnostic có thể liên quan đến nhiều vị trí. Ví dụ, khai báo trùng tên nên chỉ ra cả khai báo hiện tại và khai báo trước:

~~~text
Duplicate declaration "taxRate".
The previous declaration is at config.dsl:3:5.
~~~

Related information giúp người dùng hiểu nguồn gốc xung đột và tạo gợi ý đổi tên phù hợp.

## 3. Phân loại gợi ý sửa lỗi

Không phải mọi gợi ý đều giống nhau. Việc phân loại giúp công cụ chọn cách trình bày và mức tự động hóa phù hợp.

### 3.1 Sửa lỗi cú pháp

Ví dụ:

~~~text
if customer.active
  approve()
~~~

Nếu grammar yêu cầu từ khóa then:

~~~text
if customer.active then
  approve()
~~~

Gợi ý có thể chèn token còn thiếu tại vị trí parser mong đợi.

### 3.2 Sửa tên hoặc symbol

Ví dụ:

~~~text
apply_discount(order.totl)
~~~

Nếu có thuộc tính order.total tương tự và đúng kiểu, công cụ có thể đề xuất thay totl bằng total.

### 3.3 Sửa kiểu dữ liệu

Ví dụ:

~~~text
timeout = "30"
~~~

Nếu timeout yêu cầu Duration, gợi ý có thể chuyển thành:

~~~text
timeout = 30 seconds
~~~

Không phải lúc nào cũng có một phép chuyển đổi an toàn. Nếu chuỗi có thể chứa định dạng phức tạp hoặc giá trị không rõ, công cụ nên giải thích kiểu mong đợi thay vì tự tạo một phép chuyển đổi có thể sai.

### 3.4 Sửa tham số và chữ ký hàm

Ví dụ:

~~~text
send_email(customer.email, true, "urgent", 10)
~~~

Nếu hàm chỉ nhận ba tham số, gợi ý có thể chỉ ra đối số thừa hoặc đề xuất hàm khác. Việc tự xóa đối số chỉ an toàn khi công cụ biết chắc đối số đó không cần thiết và không có tác dụng phụ.

### 3.5 Sửa phạm vi và import

Ví dụ:

~~~text
use calculate_tax(order)
~~~

Nếu calculate_tax tồn tại trong module khác, code action có thể đề xuất thêm import tương ứng. Nhưng nếu có nhiều symbol cùng tên, công cụ cần hiển thị các lựa chọn thay vì tự chọn một.

### 3.6 Sửa giá trị cấu hình

Ví dụ:

~~~text
retry_count = -3
~~~

Nếu miền yêu cầu số lần thử không âm, công cụ có thể đề xuất giá trị hợp lệ gần nhất hoặc đưa ra tài liệu về giới hạn. Không nên tự thay -3 thành 0 nếu chưa biết ý định của người dùng.

### 3.7 Sửa lỗi null và dữ liệu tùy chọn

Ví dụ:

~~~text
print(customer.address.city)
~~~

Nếu address có kiểu nullable, gợi ý có thể là kiểm tra null hoặc dùng safe navigation:

~~~text
print(customer.address?.city)
~~~

Hai cách có ngữ nghĩa khác nhau. Kiểm tra null có thể yêu cầu một nhánh xử lý; safe navigation lan truyền null. Công cụ nên cung cấp lựa chọn và giải thích ảnh hưởng, thay vì giả định hai cách tương đương.

## 4. Mô hình dữ liệu cho diagnostic và code action

Một kiến trúc rõ ràng tách diagnostic khỏi các đề xuất sửa.

Ví dụ mô hình Java:

~~~java
record SourceRange(
    int startOffset,
    int endOffset
) {}

enum Severity {
    ERROR,
    WARNING,
    INFORMATION
}

record Diagnostic(
    String code,
    Severity severity,
    String message,
    SourceRange range
) {}

record TextEdit(
    SourceRange range,
    String newText
) {}

record CodeAction(
    String title,
    String kind,
    List<TextEdit> edits,
    boolean preferred
) {}
~~~

Đây là mô hình tối giản để minh họa. Hệ thống thực tế thường cần thêm URI của tài liệu, phiên bản tài liệu, related information, diagnostic association, command, workspace edit và metadata.

### 4.1 Một diagnostic có nhiều code action

Ví dụ, tên không được định nghĩa có thể có các lựa chọn:

- Đổi thành symbol gần giống nhất.
- Thêm import cho symbol phù hợp.
- Tạo khai báo mới.
- Đổi tên một khai báo khác để giải quyết shadowing.

Không nên gộp mọi lựa chọn vào một edit duy nhất. Người dùng cần nhìn thấy ý nghĩa của từng hành động.

### 4.2 Một code action có nhiều text edit

Một thao tác có thể cần sửa nhiều vị trí:

- Đổi tên symbol tại mọi nơi tham chiếu.
- Thêm import ở đầu file và thay tên sử dụng.
- Thêm dấu ngoặc quanh một biểu thức và sửa vị trí liên quan.
- Cập nhật khai báo cùng các điểm sử dụng.

Các edit cần được áp dụng như một thay đổi nhất quán. Nếu một edit thất bại do tài liệu đã thay đổi, không nên để một nửa thao tác được áp dụng.

### 4.3 Diagnostic không bắt buộc có code action

Một lỗi có thể cần người dùng quyết định về nghiệp vụ. Ví dụ, hai rule xung đột không thể tự sửa nếu công cụ không biết rule nào quan trọng hơn. Khi đó, diagnostic rõ ràng và related information có giá trị hơn một quick fix đoán mò.

## 5. Sinh gợi ý từ các loại lỗi khác nhau

Nguồn phát hiện lỗi ảnh hưởng đến cách tạo đề xuất.

### 5.1 Parser diagnostic

Parser biết:

- Token vừa gặp.
- Token hoặc production đang mong đợi.
- Vị trí parser bị dừng.
- Các nhánh grammar có thể áp dụng.

Từ đó, parser có thể đề xuất:

- Chèn token bị thiếu.
- Xóa token thừa.
- Thay token sai bằng token mong đợi.
- Thêm dấu đóng ngoặc hoặc dấu kết thúc.

Ví dụ:

~~~text
discount 10 percent
~~~

Nếu thiếu dấu kết thúc theo grammar:

~~~text
discount 10 percent;
~~~

Parser có thể tạo insertion edit tại vị trí sau percent.

### 5.2 Name resolution diagnostic

Name resolver biết symbol nào tồn tại trong scope và module hiện tại. Nó có thể đề xuất:

- Tên gần giống.
- Import còn thiếu.
- Tạo khai báo.
- Dùng tên đã được phân giải trong scope.

Gợi ý tên gần giống nên dựa trên symbol có thể truy cập và đúng ngữ cảnh, không chỉ so sánh chuỗi trên toàn bộ dự án.

### 5.3 Type checking diagnostic

Type checker biết kiểu thực tế và kiểu mong đợi. Nó có thể đề xuất:

- Chuyển đổi kiểu tường minh.
- Dùng thuộc tính hoặc hàm trả về kiểu phù hợp.
- Thêm kiểm tra null.
- Điều chỉnh literal hoặc đơn vị.
- Chọn overload phù hợp.

Ví dụ:

~~~text
price + duration
~~~

Nếu price có kiểu Money và duration có kiểu Duration, phép cộng có thể không hợp lệ. Không nên đề xuất ép Duration thành Money vì không có phép chuyển đổi hợp lý. Gợi ý nên chỉ ra hai kiểu không tương thích và hướng người dùng đến biểu thức đúng theo mục đích.

### 5.4 Domain validation diagnostic

Bộ kiểm tra miền biết các ràng buộc như số lượng phải dương, ngày kết thúc không trước ngày bắt đầu hoặc tỷ lệ nằm trong một khoảng.

Ví dụ:

~~~text
discount = 150 percent
~~~

Nếu miền giới hạn giảm giá trong khoảng 0 đến 100%, công cụ có thể đề xuất giới hạn hợp lệ. Nhưng nếu có nhiều giá trị hợp lệ, không nên tự chọn một giá trị mà không có cơ sở.

### 5.5 Runtime diagnostic

Runtime có thể phát hiện dữ liệu thực tế không đáp ứng điều kiện:

- Thuộc tính bắt buộc bị thiếu.
- Giá trị vượt giới hạn tại thời điểm chạy.
- Dịch vụ không khả dụng.
- Quyền thực thi bị từ chối.

Các lỗi này thường không thể sửa bằng cách thay văn bản DSL. Gợi ý có thể hướng người dùng đến trường dữ liệu, cấu hình hoặc quyền cần cập nhật. Không nên đề xuất sửa source nếu nguyên nhân nằm ở dữ liệu runtime.

## 6. Gợi ý sửa lỗi từ parser

Parser thường có thể tạo một số loại edit cơ bản.

### 6.1 Chèn token bị thiếu

Input:

~~~text
let total = 10
print(total)
~~~

Nếu DSL yêu cầu dấu chấm phẩy:

~~~text
let total = 10;
print(total);
~~~

Diagnostic có thể chỉ vị trí parser mong đợi SEMICOLON. Code action chèn dấu đó tại cuối câu lệnh.

Chỉ nên tự động chèn khi vị trí được xác định rõ. Nếu có nhiều cách đặt token hoặc việc chèn làm thay đổi cách parse, hãy đưa ra gợi ý có thể xem trước.

### 6.2 Xóa token thừa

Input:

~~~text
print(total)); 
~~~

Nếu dấu đóng ngoặc thứ hai không khớp, parser có thể đề xuất xóa token thừa.

Trước khi xóa, cần xem token có thể thuộc cấu trúc bên ngoài hay không. Trong trường hợp lồng nhiều block, xóa nhầm dấu đóng có thể làm hỏng phần còn lại.

### 6.3 Thay token không hợp lệ

Input:

~~~text
if customer.active ture
~~~

Nếu parser hoặc validator nhận diện ture là literal gần giống true, có thể đề xuất thay từ đó.

Sửa token bằng cách thay thế một range nhỏ thường an toàn hơn việc viết lại cả câu lệnh.

### 6.4 Thêm dấu ngoặc hoặc dấu phân cách

Input:

~~~text
calculate(a, b
~~~

Parser có thể đề xuất thêm dấu đóng ngoặc tại vị trí phù hợp. Nếu thiếu cả dấu ngoặc lẫn dấu chấm phẩy, có thể có nhiều cách sửa; công cụ nên trình bày một hoặc nhiều code action có giải thích.

## 7. Gợi ý tên gần giống

Một lỗi phổ biến trong DSL là viết sai identifier, tên thuộc tính, enum hoặc hàm.

Ví dụ:

~~~text
customer.emali
~~~

Trong scope hiện tại có thuộc tính email. Công cụ có thể đề xuất thay emali bằng email.

### 7.1 Khoảng cách chỉnh sửa

Một cách đơn giản để tìm tên gần giống là Levenshtein distance. Khoảng cách này đếm số phép chèn, xóa hoặc thay ký tự tối thiểu để biến một chuỗi thành chuỗi khác.

Ví dụ:

~~~text
emali -> email
~~~

Có thể tính điểm gần giống dựa trên:

- Khoảng cách chỉnh sửa tuyệt đối.
- Độ dài tên.
- Tiền tố hoặc hậu tố chung.
- Cách viết hoa và dấu gạch dưới.
- Trọng số cho lỗi đảo hai ký tự liền nhau.

Khoảng cách chuỗi chỉ là một tín hiệu. Nó không chứng minh hai symbol có cùng ý nghĩa.

### 7.2 Lọc theo scope và kiểu

Giả sử có hai symbol gần giống:

- customer.email: String
- customer.emailVerified: Boolean

Nếu ngữ cảnh yêu cầu Boolean, emailVerified có thể phù hợp hơn dù khoảng cách ký tự lớn hơn. Vì vậy, xếp hạng cần kết hợp:

1. Symbol có nhìn thấy trong scope hiện tại không?
2. Symbol có thể truy cập theo quyền không?
3. Kiểu của symbol có tương thích với ngữ cảnh không?
4. Symbol có cùng loại vai trò với tên sai không?
5. Tên có gần giống về mặt văn bản không?

### 7.3 Khi có nhiều ứng viên

Nếu hai tên có điểm tương đương, nên hiển thị lựa chọn:

~~~text
Unknown identifier "status".
Possible matches:
  account.status
  order.status
~~~

Không nên tự chọn một symbol khi ngữ cảnh không phân biệt được.

## 8. Gợi ý chuyển đổi kiểu

Type checker có thể tạo gợi ý khi kiểu thực tế không tương thích với kiểu mong đợi.

### 8.1 Chuyển đổi an toàn

Ví dụ, một kiểu Integer có thể được mở rộng sang Decimal nếu DSL định nghĩa phép chuyển đổi không mất thông tin:

~~~text
let amount: Decimal = 10
~~~

Nếu chuyển đổi tự động được hệ kiểu cho phép, không cần quick fix. Nếu DSL yêu cầu tường minh, code action có thể thêm cast hoặc constructor:

~~~text
let amount: Decimal = decimal(10)
~~~

### 8.2 Chuyển đổi có mất thông tin

Chuyển Decimal sang Integer có thể làm mất phần thập phân. Không nên tự đề xuất phép ép kiểu nếu chưa biết quy tắc làm tròn mong muốn.

Có thể đưa ra các lựa chọn:

- Làm tròn gần nhất.
- Làm tròn xuống.
- Làm tròn lên.
- Từ chối chuyển đổi và yêu cầu xử lý riêng.

### 8.3 Chuyển đổi đơn vị

Ví dụ:

~~~text
timeout = 30
~~~

Nếu timeout yêu cầu Duration, có thể đề xuất:

~~~text
timeout = 30 seconds
~~~

Nhưng nếu không biết đơn vị người dùng định dùng, công cụ không nên tự gán seconds. Có thể đề xuất các lựa chọn dựa trên cấu hình miền hoặc hiển thị thông báo kiểu mong đợi.

### 8.4 Nullability

Nếu giá trị có kiểu String? được truyền vào tham số String, gợi ý có thể:

- Kiểm tra null trước khi gọi.
- Dùng giá trị mặc định.
- Dùng safe navigation nếu kết quả cũng được phép nullable.
- Thay API nhận kiểu không nullable bằng API phù hợp nếu có.

Các lựa chọn có ngữ nghĩa khác nhau và cần được trình bày riêng.

## 9. Gợi ý import và phạm vi

Khi identifier tồn tại trong module khác nhưng chưa được import, compiler có thể đề xuất thêm import.

Ví dụ:

~~~text
use calculate_tax(order)
~~~

Symbol calculate_tax tồn tại trong module finance.tax. Code action:

~~~text
import finance.tax.calculate_tax
~~~

Sau đó lời gọi có thể được phân giải.

### 9.1 Nhiều symbol cùng tên

Nếu có nhiều module cung cấp calculate_tax, công cụ nên đưa ra lựa chọn có tên module và chữ ký. Không nên tự chọn module đầu tiên trong kết quả tìm kiếm.

### 9.2 Alias import

Nếu tên bị xung đột, có thể đề xuất alias:

~~~text
import finance.tax.calculate_tax as calculate_vat
~~~

Việc thay đổi tên sử dụng cần được thực hiện nhất quán trong phạm vi thích hợp.

### 9.3 Kiểm tra visibility

Một symbol có thể tồn tại nhưng không public hoặc không được phép truy cập từ module hiện tại. Không nên đề xuất import một symbol không thể truy cập như thể nó là một cách sửa hợp lệ.

## 10. Gợi ý sửa lỗi trong IDE

Trong IDE, gợi ý thường xuất hiện dưới dạng quick fix hoặc code action.

Một quy trình phổ biến:

1. Người dùng đặt con trỏ hoặc mở danh sách lỗi.
2. IDE yêu cầu code action tại range hiện tại.
3. Language server nhận diagnostic và context tài liệu.
4. Server tạo danh sách hành động phù hợp.
5. IDE hiển thị tiêu đề, loại hành động và có thể cả preview.
6. Người dùng chọn một hành động.
7. IDE áp dụng workspace edit.
8. Tài liệu được phân tích lại và diagnostic được cập nhật.

### 10.1 Quick fix và refactoring

Quick fix thường gắn với một diagnostic cụ thể, ví dụ đổi tên identifier sai.

Refactoring có thể được gọi độc lập, ví dụ:

- Rename symbol.
- Extract expression.
- Inline variable.
- Move declaration.

Một code action có thể là quick fix hoặc refactoring. Hãy gắn loại phù hợp để IDE hiển thị và nhóm thao tác đúng.

### 10.2 Preview trước khi áp dụng

Với thay đổi nhiều dòng hoặc nhiều file, preview giúp người dùng hiểu toàn bộ tác động. Các thao tác rủi ro như đổi tên toàn dự án, thay đổi schema hoặc cập nhật nhiều policy nên có preview rõ ràng.

### 10.3 Áp dụng theo phiên bản tài liệu

Code action được tạo dựa trên một phiên bản văn bản cụ thể. Nếu người dùng tiếp tục gõ trước khi chọn action, range cũ có thể không còn đúng.

Hệ thống nên:

- Gắn version hoặc document identifier vào edit.
- Kiểm tra tài liệu vẫn phù hợp trước khi áp dụng.
- Từ chối hoặc tính lại action nếu nội dung đã thay đổi.
- Không áp dụng edit vào range đã lỗi thời.

## 11. Text edit và workspace edit

Một text edit thường gồm:

- Tài liệu cần sửa.
- Source range.
- Nội dung thay thế.

Một workspace edit có thể chứa nhiều text edit trên một hoặc nhiều tài liệu.

Ví dụ đổi tên symbol:

~~~text
Before:
let custmer = load_customer(10)
print(custmer.name)

After:
let customer = load_customer(10)
print(customer.name)
~~~

Code action cần thay cả khai báo lẫn các tham chiếu đã được name resolver xác định. Không nên thay mọi chuỗi custmer trong file vì có thể có chuỗi literal, comment hoặc một symbol khác cùng tên.

### 11.1 Range không chồng lấn

Các edit trong cùng tài liệu thường cần có range không chồng lấn hoặc được áp dụng theo quy tắc xác định. Nếu hai edit chồng lên nhau, kết quả có thể không rõ.

Trước khi gửi workspace edit, cần kiểm tra:

- Mỗi range thuộc tài liệu đúng.
- Các range hợp lệ với phiên bản tài liệu.
- Edit không chồng lấn theo hợp đồng giao thức.
- Thứ tự áp dụng không làm lệch offset của edit khác.
- Tài liệu liên quan vẫn mở hoặc có thể chỉnh sửa.

### 11.2 Áp dụng nguyên tử

Với thao tác nhiều edit, nên áp dụng như một đơn vị nhất quán. Nếu một phần không thể áp dụng, công cụ cần báo lỗi hoặc yêu cầu tính lại thay vì để source ở trạng thái nửa cũ nửa mới.

## 12. Xếp hạng gợi ý sửa lỗi

Một diagnostic có thể có nhiều cách sửa. Hệ thống cần sắp xếp đề xuất để lựa chọn hữu ích xuất hiện trước.

Các tín hiệu có thể dùng:

- Mức độ chắc chắn của quan hệ giữa lỗi và edit.
- Tính tương thích kiểu.
- Symbol có nằm trong scope hiện tại không.
- Số lượng edit cần thực hiện.
- Phạm vi thay đổi: một token, một câu lệnh, một file hay nhiều file.
- Nguy cơ thay đổi hành vi.
- Khả năng áp dụng tự động.
- Lịch sử lựa chọn của người dùng nếu chính sách sản phẩm cho phép.

### 12.1 Điểm xếp hạng minh họa

Có thể mô hình hóa điểm:

\[
Score = w_1 C + w_2 T + w_3 S - w_4 R - w_5 E
\]

Trong đó:

- C: độ tin cậy của quan hệ với diagnostic.
- T: mức phù hợp kiểu.
- S: mức phù hợp scope.
- R: rủi ro thay đổi hành vi.
- E: chi phí hoặc độ rộng của edit.
- w: trọng số được chọn theo mục tiêu của công cụ.

Đây chỉ là một mô hình minh họa, không phải công thức bắt buộc. Hệ thống có thể dùng rule-based ranking hoặc mô hình thống kê, nhưng thứ tự cuối cùng cần có thể giải thích và kiểm thử.

### 12.2 Đề xuất mặc định

Nếu một đề xuất có độ tin cậy cao, chỉ thay một token và không đổi semantics, nó có thể được đánh dấu preferred. Nếu nhiều lựa chọn có rủi ro hoặc ý nghĩa khác nhau, không nên đánh dấu một lựa chọn là mặc định.

### 12.3 Không nhầm độ gần chuỗi với độ đúng

Một tên gần giống có thể thuộc module hoặc scope khác. Một giá trị số gần nhất có thể vẫn sai về nghiệp vụ. Xếp hạng phải kết hợp thông tin cú pháp, symbol, kiểu và miền.

## 13. Mức độ tự động hóa và an toàn

Không phải gợi ý nào cũng nên được tự động áp dụng.

Có thể chia thành:

| Mức | Hành vi | Ví dụ |
|---|---|---|
| Gợi ý thông tin | Chỉ giải thích, không có edit | Nêu kiểu mong đợi |
| Quick fix cần chọn | Người dùng xác nhận một edit | Đổi precent thành percent |
| Preferred quick fix | Một edit có độ tin cậy cao được đề xuất trước | Chèn dấu chấm phẩy bị thiếu |
| Tự sửa theo cấu hình | Công cụ áp dụng các sửa đổi đã được cho phép | Format hoặc thay đổi máy móc |
| Refactoring nhiều phạm vi | Cần preview và xác nhận | Đổi tên symbol toàn dự án |

### 13.1 Sửa tự động khi an toàn

Một edit thường an toàn hơn khi:

- Vị trí lỗi xác định rõ.
- Chỉ có một cách sửa hợp lý.
- Không làm thay đổi ý nghĩa nghiệp vụ ngoài ý muốn.
- Không ảnh hưởng symbol khác.
- Có thể kiểm tra lại sau khi áp dụng.

Ví dụ, thêm dấu chấm phẩy bị thiếu ở cuối câu lệnh có thể khá an toàn nếu grammar không mơ hồ.

### 13.2 Khi không nên tự sửa

Không nên tự động:

- Chọn giữa hai module cùng cung cấp một symbol.
- Đổi giá trị nghiệp vụ chỉ vì muốn đưa nó vào giới hạn.
- Xóa một đối số có thể có tác dụng phụ.
- Chọn một timezone hoặc currency mà người dùng chưa chỉ định.
- Thay một biểu thức nullable bằng giá trị mặc định tùy tiện.
- Xóa rule hoặc khai báo vì đang xung đột.

Trong các trường hợp này, hãy đưa ra giải thích và lựa chọn có thể review.

### 13.3 Không tạo sửa đổi phá hủy dữ liệu

Code action cần giữ nội dung người dùng không liên quan. Thao tác thay thế cả file để sửa một token nhỏ có thể làm mất comment, định dạng hoặc thay đổi chưa lưu.

Ưu tiên edit nhỏ, có range chính xác và chỉ tác động phần cần thiết.

## 14. Sửa lỗi theo ngữ cảnh thay vì chỉ dựa vào chuỗi

Gợi ý tốt cần hiểu cấu trúc DSL.

Ví dụ:

~~~text
discount = "10 percent"
~~~

Nếu trường discount yêu cầu Percentage, một phép thay thế chuỗi không đủ. Công cụ cần biết literal có thể parse thành giá trị số và đơn vị, hoặc cần constructor cụ thể.

Một quy trình theo ngữ cảnh:

1. Xác định node AST gắn với diagnostic.
2. Xác định kiểu mong đợi tại vị trí đó.
3. Tìm các biểu thức hoặc symbol hợp lệ trong scope.
4. Sinh candidate edit theo loại lỗi.
5. Kiểm tra candidate có tạo cấu trúc hợp lệ không.
6. Xếp hạng theo độ phù hợp và rủi ro.

### 14.1 Type-directed suggestion

Nếu một tham số cần Duration, chỉ nên ưu tiên giá trị hoặc biểu thức có kiểu Duration. Không nên chọn một identifier chỉ vì tên của nó gần giống.

### 14.2 Scope-aware suggestion

Nếu tên chưa được định nghĩa trong block hiện tại nhưng có tên tương tự trong module khác, công cụ cần cân nhắc visibility và import. Gợi ý chỉ hợp lệ nếu sau khi thêm import, symbol thực sự có thể được truy cập.

### 14.3 Domain-aware suggestion

Một DSL về lịch làm việc có thể có các giá trị weekday hợp lệ. Gợi ý Saturday cho một giá trị sai gần giống là hợp lý nếu miền định nghĩa rõ. Một DSL về thuế hoặc tiền tệ cần cẩn trọng hơn vì thay giá trị có thể làm thay đổi quyết định tài chính.

## 15. Sửa lỗi trong khi parser đang phục hồi

Parser thường cố gắng tiếp tục sau lỗi để có thể báo nhiều diagnostic. Nhưng parse tree được tạo sau recovery có thể chứa token tổng hợp hoặc context không hoàn chỉnh.

Gợi ý từ parse tree đã phục hồi cần thận trọng:

- Xác định diagnostic có đến từ token thật hay token tổng hợp.
- Không dùng range giả làm vị trí edit trong source.
- Không đề xuất xóa token nếu parser đã tự chèn token thay thế.
- Không tạo code action dựa trên context chưa đủ tin cậy.
- Có thể trì hoãn gợi ý cho đến khi parser có cấu trúc ổn định hơn.

Ví dụ, nếu parser chèn một dấu đóng ngoặc tổng hợp để tiếp tục phân tích, diagnostic có thể đề xuất người dùng thêm dấu đó vào source. Nhưng range của token tổng hợp không phải một range văn bản thực tế; code action cần dùng vị trí insertion do parser cung cấp.

## 16. Gợi ý sửa lỗi và ngôn ngữ máy đọc được

Một số DSL được viết bởi con người; một số được sinh tự động hoặc dùng trong pipeline cấu hình. Cách đề xuất sửa có thể khác nhau.

Với DSL do con người viết:

- Ưu tiên thông báo dễ hiểu.
- Đề xuất một số cách sửa có lý do.
- Giữ định dạng và comment.
- Cho phép preview.

Với DSL được sinh tự động:

- Có thể cung cấp lỗi có mã và cấu trúc JSON.
- Gắn source span hoặc đường dẫn cấu hình.
- Đề xuất sửa ở tầng schema hoặc generator.
- Tránh sửa trực tiếp output nếu cần sửa nguồn tạo ra output.

Nếu file DSL được sinh từ một công cụ khác, sửa output có thể bị ghi đè ở lần build sau. Diagnostic nên chỉ ra nguồn gốc hoặc file cấu hình gốc khi có thể.

## 17. Giao thức Language Server Protocol

Trong IDE, Language Server Protocol (LSP) là một giao thức phổ biến để client và language server trao đổi diagnostic, code action và edit.

Một luồng khái quát:

~~~text
Editor
  |
  | didOpen / didChange
  v
Language Server
  |
  | parse + analyze
  v
Diagnostics
  |
  | publishDiagnostics
  v
Editor
  |
  | codeAction request
  v
Language Server
  |
  | CodeAction + WorkspaceEdit
  v
Editor applies edit
~~~

### 17.1 Publish diagnostics

Server gửi danh sách diagnostic cho tài liệu, thường gồm range, severity, code, source và message. Client có thể hiển thị gạch chân, danh sách lỗi hoặc thông tin khi hover.

### 17.2 Code action request

Client yêu cầu code action cho một range hoặc một số diagnostic. Server có thể trả về:

- Quick fix.
- Refactoring.
- Source action như format hoặc organize imports.
- Command do server định nghĩa.

### 17.3 WorkspaceEdit

Code action có thể chứa WorkspaceEdit với nhiều thay đổi trên một hoặc nhiều tài liệu. Nếu cần xác nhận phiên bản tài liệu, server và client phải dùng cơ chế versioned document changes theo khả năng giao thức.

### 17.4 Resolve code action

Để giảm chi phí, server có thể trả action ban đầu với thông tin tối thiểu rồi tính chi tiết khi client yêu cầu resolve. Ví dụ, danh sách đổi tên có thể được tính khi người dùng mở menu thay vì ngay khi mọi diagnostic được tạo.

Không nên gửi một code action có title nhưng không thể thực hiện. Nếu action cần tính lại do tài liệu thay đổi, server nên trả lỗi phù hợp hoặc yêu cầu client yêu cầu action mới.

## 18. Gợi ý sửa lỗi ở CLI và pipeline tự động

Không phải mọi người dùng DSL đều làm việc trong IDE.

### 18.1 CLI

CLI có thể hiển thị:

~~~text
config.dsl:4:18: error DSL_UNKNOWN_UNIT
Unknown unit "precent".
Suggested replacement: "percent"
~~~

Có thể hỗ trợ:

~~~text
dsl check --suggest
dsl fix --preview
dsl fix --apply
~~~

Đây là tên lệnh minh họa. Một công cụ nên tách rõ chế độ chỉ hiển thị đề xuất, preview patch và áp dụng thay đổi.

### 18.2 CI

Trong CI, gợi ý có thể được xuất dưới dạng:

- JSON diagnostics.
- SARIF hoặc định dạng tương thích công cụ phân tích.
- Patch artifact.
- Annotation gắn với dòng nguồn.

Không nên để CI tự áp dụng thay đổi nghiệp vụ chỉ vì có quick fix. Pipeline có thể tạo patch để review.

### 18.3 Batch fix

Nếu áp dụng nhiều sửa đổi cùng lúc, cần:

- Xác định thứ tự edit.
- Phát hiện edit xung đột.
- Bảo đảm mỗi edit vẫn áp dụng được sau các edit trước.
- Chạy lại parser và validator.
- Ghi nhận file nào đã thay đổi.
- Có khả năng hủy hoặc khôi phục nếu thao tác thất bại.

## 19. Kiểm chứng một gợi ý trước khi hiển thị

Gợi ý được tạo ra từ heuristic có thể không đúng. Hệ thống có thể kiểm tra candidate trước khi đưa ra.

Một quy trình:

1. Tạo bản sửa giả lập trên snapshot source.
2. Parse lại vùng hoặc tài liệu liên quan.
3. Kiểm tra lỗi cú pháp có giảm hay không.
4. Chạy name resolution và type checking ở phạm vi phù hợp.
5. Kiểm tra diagnostic ban đầu đã được giải quyết chưa.
6. Kiểm tra có lỗi mới nghiêm trọng nào xuất hiện không.
7. Đánh giá phạm vi thay đổi và rủi ro.

Không phải mọi gợi ý đều có thể chứng minh là đúng. Việc candidate parse thành công chỉ cho biết cú pháp hợp lệ, không chứng minh ý nghĩa nghiệp vụ đúng.

### 19.1 Không yêu cầu mọi lỗi biến mất

Một sửa đổi có thể giải quyết lỗi hiện tại nhưng để lại lỗi độc lập khác. Hệ thống nên đánh giá lỗi liên quan đến edit thay vì yêu cầu toàn bộ dự án không còn diagnostic.

### 19.2 So sánh trước và sau

Có thể so sánh:

- Diagnostic mục tiêu.
- Diagnostic mới trên vùng thay đổi.
- Kiểu suy luận trước và sau.
- Symbol binding.
- AST hoặc IR liên quan.
- Các test miền nếu có.

Với thay đổi có thể ảnh hưởng behavior, cần preview và xác nhận thay vì coi việc parse thành công là đủ.

### 19.3 Candidate validation không phải bảo đảm tuyệt đối

Một gợi ý được kiểm tra thành công vẫn có thể không đúng ý định người viết. Công cụ nên diễn đạt đây là đề xuất và cho phép người dùng review.

## 20. Kiểm thử hệ thống gợi ý sửa lỗi

Nên kiểm thử cả diagnostic, candidate edit và kết quả sau khi áp dụng.

### 20.1 Kiểm thử diagnostic

- Mã lỗi ổn định.
- Severity đúng.
- Message có nội dung rõ.
- Range đánh dấu đúng token hoặc biểu thức.
- Related information trỏ đúng vị trí.

### 20.2 Kiểm thử gợi ý

- Diagnostic có đúng các action mong đợi không?
- Title có mô tả chính xác thay đổi không?
- Edit có đúng range không?
- Nội dung thay thế có giữ định dạng không?
- Action có bị đưa ra khi thiếu điều kiện không?
- Thứ tự đề xuất có hợp lý không?

### 20.3 Kiểm thử áp dụng edit

Với mỗi quick fix:

1. Chuẩn bị source trước sửa.
2. Tạo diagnostic.
3. Lấy code action.
4. Áp dụng text edit.
5. So sánh source sau sửa với kết quả mong đợi.
6. Parse và kiểm tra lại.

### 20.4 Kiểm thử Unicode và range

Thử với:

- Ký tự có dấu.
- Emoji.
- Ký tự ngoài BMP.
- CRLF và LF.
- Tab và khoảng trắng.
- File có newline cuối hoặc không có newline cuối.

Các test này phát hiện lỗi chuyển đổi offset và cột.

### 20.5 Kiểm thử nhiều edit

- Hai edit không chồng lấn.
- Edit chồng lấn bị từ chối hoặc xử lý theo quy tắc.
- Tài liệu đổi phiên bản trước khi áp dụng.
- Một file trong workspace không thể chỉnh sửa.
- Rename nhiều nơi giữ đúng symbol binding.

## 21. Đo chất lượng gợi ý

Ngoài test chức năng, có thể đo hiệu quả của hệ thống bằng các chỉ số:

- **Acceptance rate:** tỷ lệ gợi ý được người dùng chọn.
- **Application success:** tỷ lệ edit áp dụng thành công.
- **Resolution rate:** tỷ lệ diagnostic mục tiêu biến mất sau khi áp dụng.
- **Regression rate:** tỷ lệ gợi ý tạo thêm lỗi hoặc làm hỏng chương trình.
- **Time to repair:** thời gian trung bình từ khi thấy lỗi đến khi sửa xong.
- **Precision:** tỷ lệ đề xuất đúng trong số đề xuất được hiển thị.

Không nên tối ưu acceptance rate đơn lẻ. Một gợi ý dễ được chọn nhưng thường làm thay đổi semantics sai là một hệ thống kém chất lượng.

Nếu thu thập telemetry, cần tuân thủ chính sách dữ liệu của sản phẩm. Source DSL có thể chứa thông tin nhạy cảm; không nên gửi toàn bộ văn bản hoặc identifier lên dịch vụ phân tích nếu không có cơ sở và sự cho phép phù hợp.

## 22. Những sai lầm thường gặp

### Đưa ra một cách sửa duy nhất khi có nhiều cách hiểu

Một identifier có thể khớp nhiều symbol hoặc một giá trị có thể được diễn giải theo nhiều đơn vị.

**Cách khắc phục:** hiển thị các lựa chọn có ngữ cảnh và giải thích khác biệt.

### Dựa chỉ vào độ gần chuỗi

Tên gần giống có thể sai scope hoặc sai kiểu.

**Cách khắc phục:** kết hợp khoảng cách chỉnh sửa với symbol resolution, visibility và type compatibility.

### Tự sửa giá trị nghiệp vụ

Đổi 150% thành 100% có thể làm chương trình hợp lệ nhưng không đúng ý định.

**Cách khắc phục:** đề xuất giới hạn và để người dùng quyết định giá trị.

### Sửa toàn bộ văn bản thay vì range nhỏ

Thay cả dòng hoặc cả file có thể xóa comment, format hoặc chỉnh sửa khác.

**Cách khắc phục:** dùng text edit nhỏ và source range chính xác.

### Áp dụng action trên phiên bản tài liệu cũ

Range cũ có thể trỏ đến nội dung khác sau khi người dùng tiếp tục gõ.

**Cách khắc phục:** gắn version, kiểm tra snapshot và tính lại action khi cần.

### Không kiểm tra edit nhiều vị trí

Một thao tác rename có thể đổi khai báo nhưng bỏ sót tham chiếu hoặc sửa nhầm string literal.

**Cách khắc phục:** dựa vào symbol binding và kiểm tra toàn bộ workspace edit.

### Coi parse thành công là đúng nghiệp vụ

Một candidate có thể đúng cú pháp nhưng sai semantics.

**Cách khắc phục:** kiểm tra type, symbol binding và ràng buộc miền; với thay đổi quan trọng, yêu cầu review.

### Đề xuất sửa lỗi từ dữ liệu runtime bằng cách sửa source

Nếu dịch vụ bị timeout hoặc dữ liệu bị thiếu, source có thể hoàn toàn đúng.

**Cách khắc phục:** phân biệt lỗi source, lỗi dữ liệu và lỗi hạ tầng trước khi tạo action.

## 23. Quy trình thiết kế gợi ý sửa lỗi

Khi xây dựng tính năng sửa lỗi cho DSL, có thể triển khai theo trình tự:

1. **Chuẩn hóa diagnostic:** mã lỗi, severity, message, source range và related information.
2. **Phân loại nguyên nhân:** cú pháp, tên, kiểu, miền, dữ liệu hay hạ tầng.
3. **Xác định ngữ cảnh:** AST node, symbol, kiểu mong đợi, scope và phiên bản tài liệu.
4. **Sinh candidate:** tạo một hoặc nhiều text edit hoặc code action.
5. **Lọc candidate:** bỏ đề xuất không hợp lệ, không truy cập được hoặc có rủi ro không chấp nhận được.
6. **Xếp hạng:** dùng độ tin cậy, kiểu, scope, phạm vi và rủi ro.
7. **Kiểm tra edit:** range, version, overlap và tính nguyên tử.
8. **Hiển thị phù hợp:** quick fix, preview, lựa chọn hoặc thông tin hướng dẫn.
9. **Áp dụng và phân tích lại:** cập nhật source và diagnostics.
10. **Đo kết quả:** kiểm tra resolution rate, regression và trải nghiệm sửa lỗi.

Mỗi gợi ý nên trả lời được ba câu hỏi: vấn đề nằm ở đâu, công cụ đề xuất thay đổi gì và thay đổi đó có thể ảnh hưởng đến điều gì.

## 24. Ví dụ tổng hợp

Giả sử người dùng viết:

~~~text
policy "Gold discount"
  when customer.tier == GOLD
   and order.total >= 2000000 VND
  then discount 10 precent
~~~

Hệ thống phát hiện precent là unit không được định nghĩa.

### 24.1 Diagnostic

~~~text
code: DSL_UNKNOWN_UNIT
severity: ERROR
message: Unknown unit "precent"
range: token "precent"
~~~

### 24.2 Candidate

Name index chứa unit percent hợp lệ và không có ứng viên nào khác gần tương đương.

Code action:

~~~text
Title: Replace "precent" with "percent"
Edit:
  range = token "precent"
  newText = "percent"
~~~

### 24.3 Kiểm tra candidate

Sau khi áp dụng giả lập:

~~~text
then discount 10 percent
~~~

Parser nhận diện được literal phần trăm. Type checker xác nhận kiểu Percentage phù hợp với hành động discount. Diagnostic DSL_UNKNOWN_UNIT biến mất và không có lỗi liên quan mới xuất hiện.

### 24.4 Kết quả

IDE hiển thị quick fix:

~~~text
Replace "precent" with "percent"
~~~

Người dùng chọn action, editor áp dụng edit đúng range và chạy lại phân tích. Source sau sửa được giữ nguyên các phần không liên quan.

## 25. Câu hỏi tự kiểm tra

1. Phân biệt diagnostic, suggestion, text edit và code action.
2. Vì sao diagnostic cần mã lỗi ổn định và source range chính xác?
3. Gợi ý tên gần giống nên xét những yếu tố nào ngoài khoảng cách chuỗi?
4. Khi nào một sửa đổi cú pháp có thể được tự động áp dụng?
5. Vì sao sửa giá trị nghiệp vụ thường cần người dùng xác nhận?
6. Phân biệt quick fix và refactoring.
7. Một workspace edit nhiều vị trí cần bảo đảm những điều gì?
8. Vì sao cần kiểm tra phiên bản tài liệu trước khi áp dụng edit?
9. Semantic predicate hoặc parser recovery có thể ảnh hưởng gợi ý sửa như thế nào?
10. LSP hỗ trợ trao đổi diagnostic và code action qua những bước nào?
11. Vì sao parse thành công chưa đủ chứng minh candidate đúng?
12. Những chỉ số nào giúp đánh giá chất lượng gợi ý sửa lỗi?

Gợi ý sửa lỗi là cầu nối giữa chẩn đoán và hành động khắc phục. Khi diagnostic có vị trí chính xác, candidate được tạo từ ngữ cảnh cú pháp và ngữ nghĩa, edit được kiểm tra theo phiên bản tài liệu và mức rủi ro, công cụ DSL có thể giúp người dùng sửa nhanh mà vẫn giữ quyền kiểm soát đối với thay đổi của mình.
