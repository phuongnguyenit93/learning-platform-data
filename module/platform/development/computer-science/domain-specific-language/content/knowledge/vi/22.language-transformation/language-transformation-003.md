# Chuẩn hóa mô hình trong biến đổi ngôn ngữ DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích chuẩn hóa mô hình (model normalization) và vai trò của nó trong quá trình biến đổi ngôn ngữ.
- Phân biệt chuẩn hóa mô hình với chuẩn hóa cơ sở dữ liệu, định dạng mã nguồn và kiểm tra tính hợp lệ.
- Giải thích vì sao nhiều cách viết DSL có thể được đưa về cùng một dạng biểu diễn chuẩn.
- Nhận diện các dạng biến đổi như desugaring, chuẩn hóa biểu thức, tên, kiểu, tham chiếu, collection và giá trị mặc định.
- Thiết kế các bước chuẩn hóa có thứ tự, có thể lặp lại và bảo toàn ngữ nghĩa.
- Quản lý nguồn gốc, vị trí nguồn và khả năng truy vết giữa mô hình trước và sau chuẩn hóa.
- Phân biệt chuẩn hóa cú pháp với biến đổi làm thay đổi ý nghĩa hoặc bổ sung chính sách nghiệp vụ.
- Xây dựng pipeline, kiểm tra và kiểm thử cho mô hình đã chuẩn hóa.

## 1. Chuẩn hóa mô hình là gì?

Trong một DSL, người dùng có thể viết cùng một ý tưởng bằng nhiều hình thức cú pháp. Một biểu thức có thể có dấu ngoặc dư, một thuộc tính có thể được bỏ qua vì có giá trị mặc định, một từ khóa rút gọn có thể đại diện cho một cấu trúc dài hơn, hoặc một tham chiếu có thể được viết bằng tên ngắn thay vì định danh đầy đủ.

**Chuẩn hóa mô hình (model normalization)** là quá trình biến đổi mô hình đã phân tích thành một dạng biểu diễn thống nhất, có cấu trúc và quy ước nhất quán. Dạng chuẩn này giúp các bước tiếp theo như phân tích ngữ nghĩa, kiểm tra kiểu, tối ưu hóa, sinh mã, so sánh mô hình hoặc thực thi xử lý ít trường hợp đặc biệt hơn.

Ví dụ, DSL cho phép viết:

~~~text
rule "bulk_discount" {
    when order.quantity >= 10
    then order.discount = 5%
}
~~~

và cũng cho phép dạng rút gọn:

~~~text
rule "bulk_discount" when order.quantity >= 10 => order.discount = 5%
~~~

Parser có thể tạo hai AST khác nhau vì cấu trúc cú pháp khác nhau. Một bước chuẩn hóa có thể chuyển cả hai thành cùng một mô hình nội bộ:

~~~text
Rule(
  name = "bulk_discount",
  conditions = [GreaterOrEqual(Property(order, quantity), 10)],
  actions = [Assign(Property(order, discount), Percentage(5))]
)
~~~

Sau chuẩn hóa, compiler không cần xử lý riêng hai cách viết. Nó làm việc với một cấu trúc chuẩn duy nhất.

Chuẩn hóa không chỉ là làm mã nguồn đẹp hơn. Nó tạo ra một hợp đồng biểu diễn giữa parser và các bước xử lý tiếp theo. Một mô hình chuẩn giúp giảm số nhánh logic, làm phép biến đổi dễ kiểm tra và tăng khả năng tái sử dụng giữa nhiều cú pháp hoặc backend.

## 2. Chuẩn hóa mô hình trong pipeline biến đổi ngôn ngữ

Một pipeline xử lý DSL thường có các giai đoạn:

~~~text
Nguồn DSL
   |
   v
Lexer và Parser
   |
   v
AST theo cú pháp nguồn
   |
   v
Phân giải tên và liên kết tham chiếu
   |
   v
Chuẩn hóa mô hình
   |
   v
Mô hình chuẩn / Canonical IR
   |
   +------> Kiểm tra ngữ nghĩa và kiểu
   |
   +------> Phân tích phụ thuộc
   |
   +------> Tối ưu hóa
   |
   +------> Sinh mã / Chuyển sang DSL khác
   |
   v
Thực thi hoặc xuất kết quả
~~~

Vị trí chính xác của chuẩn hóa phụ thuộc kiến trúc. Một số phép chuẩn hóa cần tên và kiểu đã được phân giải; một số phép khác có thể thực hiện ngay sau parse. Vì vậy, hệ thống có thể có nhiều tầng chuẩn hóa thay vì một bước duy nhất.

### 2.1. AST theo cú pháp nguồn

AST ban đầu thường phản ánh cấu trúc mà parser nhận diện. Nó có thể giữ lại các khác biệt cú pháp như:

- Cú pháp rút gọn và cú pháp đầy đủ.
- Các dạng literal khác nhau.
- Cách nhóm biểu thức bằng dấu ngoặc.
- Từ khóa thay thế hoặc alias.
- Giá trị mặc định được viết tường minh hoặc bị bỏ qua.

AST này hữu ích cho việc chẩn đoán cú pháp và giữ quan hệ với nguồn, nhưng chưa chắc là dạng thuận tiện nhất cho phân tích và sinh mã.

### 2.2. Mô hình chuẩn

Mô hình chuẩn (canonical model) biểu diễn cùng một ý nghĩa theo một cấu trúc được quy định. Ví dụ:

- Mọi điều kiện đều được lưu trong một danh sách conditions.
- Mọi phép gán đều dùng cùng một node Assign.
- Alias được đổi thành định danh chuẩn.
- Giá trị mặc định được thể hiện theo một quy ước thống nhất.
- Các tham chiếu tên được liên kết đến symbol hoặc object ID.

### 2.3. Những bước sau chuẩn hóa

Khi mô hình đã có dạng chuẩn, type checker, optimizer và code generator có thể dựa vào các invariant rõ ràng. Ví dụ, optimizer không cần kiểm tra một rule dùng cú pháp rút gọn hay cú pháp đầy đủ; cả hai đều đã có cùng danh sách điều kiện và hành động.

### 2.4. Chuẩn hóa có thể diễn ra nhiều lần

Một pipeline có thể gồm:

1. Chuẩn hóa cú pháp: loại bỏ khác biệt hình thức và mở rộng cú pháp rút gọn.
2. Chuẩn hóa tên: giải quyết alias và tham chiếu.
3. Chuẩn hóa kiểu: chèn chuyển đổi tường minh hoặc gắn kiểu chuẩn.
4. Chuẩn hóa cấu trúc: tạo các node và collection theo quy ước.
5. Chuẩn hóa ngữ nghĩa: đưa các dạng tương đương về một cấu trúc thống nhất khi đã đủ thông tin.

Mỗi tầng cần có đầu vào, đầu ra và invariant riêng để dễ kiểm soát.

## 3. Phân biệt với các khái niệm khác

Thuật ngữ normalization xuất hiện trong nhiều lĩnh vực. Cần hiểu đúng phạm vi trong biến đổi ngôn ngữ.

| Khái niệm | Mục tiêu chính | Ví dụ |
|---|---|---|
| Chuẩn hóa mô hình | Đưa mô hình về biểu diễn thống nhất | Mở rộng cú pháp rút gọn thành node chuẩn |
| Chuẩn hóa cơ sở dữ liệu | Giảm dư thừa và bất thường cập nhật trong dữ liệu | Tách bảng theo phụ thuộc hàm |
| Định dạng mã nguồn | Trình bày văn bản nhất quán | Căn lề, khoảng trắng, xuống dòng |
| Kiểm tra tính hợp lệ | Xác định mô hình có thỏa ràng buộc không | Kiểm tra rule có ít nhất một action |
| Tối ưu hóa | Cải thiện hiệu năng hoặc tài nguyên | Constant folding, loại bỏ mã chết |
| Refactoring | Thay đổi cấu trúc để dễ bảo trì nhưng giữ hành vi | Tách một biểu thức phức tạp thành hàm |

Các hoạt động có thể phối hợp nhưng không đồng nhất. Một mô hình có thể đã được chuẩn hóa mà vẫn không hợp lệ. Một mô hình hợp lệ có thể chưa ở dạng chuẩn. Định dạng mã nguồn có thể thay đổi cách trình bày mà không thay đổi AST; chuẩn hóa mô hình có thể thay đổi cấu trúc AST mà không cần thay đổi văn bản nguồn.

## 4. Vì sao cần một dạng biểu diễn chuẩn?

### 4.1. Giảm số trường hợp đặc biệt

Nếu cùng một ý nghĩa có năm dạng cú pháp, mọi bước sau parser có thể phải hỗ trợ cả năm. Khi số tính năng tăng, số tổ hợp xử lý tăng nhanh.

Chuẩn hóa đưa các dạng đó về một cấu trúc chung. Các bước sau chỉ cần hỗ trợ một dạng chuẩn.

### 4.2. Tách cú pháp khỏi ngữ nghĩa

Người dùng có thể thích cú pháp ngắn, dễ đọc; compiler cần cấu trúc rõ và dễ phân tích. Chuẩn hóa tạo ranh giới giữa cách viết và ý nghĩa.

### 4.3. Dùng chung nhiều cú pháp

Một hệ thống có thể hỗ trợ DSL dạng văn bản, editor trực quan và file cấu hình JSON. Mỗi frontend tạo AST riêng nhưng cùng chuyển về một mô hình chuẩn. Backend chỉ cần xử lý mô hình chuẩn.

### 4.4. Đơn giản hóa so sánh và phân tích

Hai mô hình cùng ý nghĩa nhưng khác cách viết có thể được chuẩn hóa thành cấu trúc giống nhau. Điều này hữu ích cho:

- So sánh phiên bản.
- Phát hiện thay đổi thực chất.
- Tạo cache key.
- Phân tích phụ thuộc.
- Sinh mã nhất quán.
- Kiểm thử tương đương.

### 4.5. Hỗ trợ tối ưu hóa và sinh mã

Một optimizer hoạt động tốt khi cấu trúc biểu thức và luồng điều khiển nhất quán. Một code generator hoạt động tốt khi không phải hiểu mọi biến thể cú pháp của người dùng.

## 5. Các nguyên tắc của chuẩn hóa mô hình

Một thiết kế chuẩn hóa tốt nên tuân theo các nguyên tắc sau:

1. **Bảo toàn ngữ nghĩa:** mô hình sau chuẩn hóa phải thể hiện cùng hành vi theo hợp đồng của DSL.
2. **Tính xác định:** cùng một mô hình và cùng ngữ cảnh phải tạo ra cùng kết quả chuẩn hóa.
3. **Tính idempotent:** chuẩn hóa một mô hình đã chuẩn hóa không làm thay đổi nó thêm.
4. **Tính nhất quán:** cùng một khái niệm được biểu diễn theo cùng quy ước ở mọi nơi.
5. **Không mất thông tin cần thiết:** giữ nguồn gốc, chú thích hoặc metadata nếu các bước sau cần.
6. **Phân tách trách nhiệm:** chuẩn hóa cấu trúc không tự ý áp dụng chính sách nghiệp vụ chưa được khai báo.
7. **Có thể kiểm tra:** mỗi phép biến đổi có điều kiện áp dụng và invariant rõ ràng.
8. **Có thể truy vết:** có thể xác định node chuẩn đến từ phần nguồn nào.

### 5.1. Bảo toàn ngữ nghĩa

Nếu hai mô hình có cùng ý nghĩa theo DSL, việc chuẩn hóa không được tạo ra hai hành vi khác nhau. Ngược lại, nếu hai cấu trúc có ý nghĩa khác nhau, không được gộp chúng chỉ vì hình thức giống nhau.

### 5.2. Tính xác định

Không nên để kết quả chuẩn hóa phụ thuộc thứ tự duyệt không xác định, thời gian hệ thống hoặc trạng thái bên ngoài nếu những yếu tố đó không thuộc đầu vào được công bố.

### 5.3. Tính idempotent

Gọi N là phép chuẩn hóa. Một phép chuẩn hóa idempotent thỏa:

~~~text
N(N(M)) = N(M)
~~~

Trong đó M là mô hình đầu vào. Sau lần đầu, mô hình đã đạt dạng chuẩn và chạy lại không tạo biến đổi mới.

### 5.4. Không nhầm chuẩn hóa với sửa lỗi

Nếu mô hình thiếu trường bắt buộc, chuẩn hóa không nên tự tạo giá trị giả để làm cho nó có vẻ hợp lệ, trừ khi đặc tả quy định một giá trị mặc định cụ thể. Thiếu dữ liệu có thể là lỗi cần báo, không phải cơ hội để đoán ý định.

## 6. Chuẩn hóa cú pháp và desugaring

Desugaring là biến đổi cú pháp thuận tiện (syntactic sugar) thành cấu trúc cơ bản hơn mà ngôn ngữ đã định nghĩa.

Ví dụ, DSL cho phép:

~~~text
allow user to read and write
~~~

Một mô hình chuẩn có thể biểu diễn:

~~~text
PermissionGrant(
  subject = User,
  actions = [Read, Write]
)
~~~

### 6.1. Mở rộng cú pháp rút gọn

Một cú pháp ngắn:

~~~text
retry 3 times
~~~

có thể được chuẩn hóa thành:

~~~text
RetryPolicy(
  maxAttempts = 3,
  delay = DefaultDelay
)
~~~

Nếu DSL định nghĩa rõ delay mặc định, việc bổ sung giá trị này là một phần của desugaring. Nếu không có quy tắc mặc định, compiler không nên tự đoán.

### 6.2. Alias và từ khóa thay thế

Giả sử DSL cho phép hai từ khóa:

~~~text
when order.total > 100
if order.total > 100
~~~

Nếu đặc tả nói if là alias của when trong ngữ cảnh này, parser hoặc normalizer có thể đưa cả hai về cùng node Condition.

### 6.3. Cấu trúc danh sách rút gọn

Một DSL có thể cho phép:

~~~text
roles: admin, editor
~~~

và:

~~~text
roles: [admin, editor]
~~~

Nếu cả hai có cùng ý nghĩa, mô hình chuẩn nên dùng một collection node thống nhất.

### 6.4. Desugaring không phải lúc nào cũng mất thông tin

AST chuẩn có thể cần giữ metadata về cú pháp gốc để formatter, debugger hoặc IDE biết người dùng đã viết dạng nào. Vì vậy, mở rộng cú pháp không nhất thiết phải xóa hoàn toàn dấu vết nguồn.

## 7. Chuẩn hóa biểu thức

Biểu thức thường có nhiều hình thức tương đương về cấu trúc. Chuẩn hóa biểu thức giúp các bước phân tích sau xử lý ít trường hợp hơn.

### 7.1. Loại bỏ dấu ngoặc không cần thiết

~~~text
(a + b)
~~~

Nếu dấu ngoặc chỉ dùng để nhóm một biểu thức đơn và AST đã ghi nhận đúng cấu trúc, node Parenthesized có thể được loại bỏ sau khi parser hoàn tất việc xác định precedence.

Không được bỏ ngoặc khi làm thay đổi cây biểu thức:

~~~text
a * (b + c)
~~~

không tương đương về cấu trúc với:

~~~text
a * b + c
~~~

### 7.2. Chuẩn hóa toán tử thành node thống nhất

Các dạng:

~~~text
a >= b
a not less than b
~~~

có thể được đưa về cùng node GreaterOrEqual nếu DSL định nghĩa chúng tương đương.

### 7.3. Biểu diễn phủ định

Một số DSL có nhiều dạng:

~~~text
not (a == b)
a != b
~~~

Có thể chuẩn hóa về một node NotEqual nếu phép so sánh và phủ định có cùng ngữ nghĩa. Cần chú ý giá trị null, kiểu ba trạng thái hoặc phép so sánh đặc biệt có thể làm hai dạng không tương đương.

### 7.4. Chuẩn hóa literal

Literal số có thể có nhiều cách viết:

~~~text
1000
1_000
1e3
~~~

Nếu DSL định nghĩa các dạng này tương đương, mô hình chuẩn có thể lưu giá trị số đã phân tích cùng kiểu và đơn vị. Nên giữ lexeme nguồn nếu cần hiển thị lại chính xác.

### 7.5. Chuẩn hóa biểu thức hằng

Một bước normalization có thể đưa biểu thức hằng về literal:

~~~text
2 + 3 * 4
~~~

thành:

~~~text
14
~~~

Đây cũng là constant folding, thường được xếp vào tối ưu hóa. Ranh giới giữa normalization và optimization phụ thuộc kiến trúc. Một compiler có thể giữ normalization chỉ cho dạng chuẩn cấu trúc, còn tính toán biểu thức hằng ở pass tối ưu riêng.

### 7.6. Chuẩn hóa thứ tự toán hạng

Với phép toán giao hoán, compiler có thể sắp xếp toán hạng theo quy tắc chuẩn để so sánh hoặc tạo cache key. Tuy nhiên, không được đổi thứ tự đánh giá nếu toán hạng có tác dụng phụ hoặc nếu phép toán không giao hoán trong kiểu cụ thể.

Ví dụ, a + b và b + a có thể không tương đương với phép nối chuỗi có xử lý kiểu đặc biệt hoặc số học dấu phẩy động theo quy tắc chính xác. Chỉ chuẩn hóa thứ tự khi tính giao hoán đã được chứng minh trong ngữ cảnh đó.

## 8. Chuẩn hóa tên và tham chiếu

Một mô hình có thể tham chiếu cùng một thành phần bằng nhiều tên:

~~~text
customer
Customer
crm.Customer
CustomerRecord
~~~

Nếu DSL hỗ trợ alias hoặc import, các cách viết này có thể trỏ đến cùng một symbol. Chuẩn hóa tên thường được thực hiện sau bước phân giải tên.

### 8.1. Phân giải alias

Ví dụ:

~~~text
use crm.Customer as Client
let buyer: Client
~~~

Sau phân giải, kiểu Client được liên kết đến symbol chuẩn crm.Customer. Mô hình có thể lưu symbol ID hoặc qualified name chuẩn thay vì chỉ giữ chuỗi Client.

### 8.2. Qualified name

Một tên ngắn có thể mơ hồ:

~~~text
Customer
~~~

Nếu nhiều module định nghĩa Customer, cần phân giải theo import và scope. Không nên chuẩn hóa tên trước khi biết symbol nào được tham chiếu.

### 8.3. Định danh ổn định

Trong mô hình có vòng đời dài, ID ổn định có thể phù hợp hơn tên hiển thị. Tên có thể đổi nhưng tham chiếu vẫn giữ nguyên nếu object ID không đổi.

### 8.4. Chuẩn hóa đường dẫn tham chiếu

Các đường dẫn:

~~~text
order.customer.address.city
~~~

có thể được chuyển thành chuỗi tham chiếu đã phân giải:

~~~text
PropertyAccess(
  receiver = PropertyAccess(
    receiver = PropertyAccess(orderSymbol, customerSymbol),
    addressSymbol
  ),
  citySymbol
)
~~~

Điều này giúp type checker và code generator không cần tra tên lại ở mọi lần truy cập.

### 8.5. Không tự đổi tên theo phỏng đoán

Nếu tên không phân giải được, normalizer không nên tự thay bằng tên gần giống. Gợi ý có thể được đưa ra trong diagnostic, nhưng thay đổi tham chiếu cần có cơ sở rõ ràng.

## 9. Chuẩn hóa kiểu dữ liệu

Một DSL có thể có kiểu nguyên thủy, kiểu miền, kiểu collection, kiểu tùy chọn và alias kiểu.

### 9.1. Alias kiểu

~~~text
type CustomerCode = String
~~~

Nếu CustomerCode chỉ là alias không tạo kiểu mới, mô hình chuẩn có thể liên kết nó đến kiểu String đồng thời giữ alias cho tài liệu và diagnostic. Nếu nó là kiểu miền riêng, không được xóa danh tính kiểu đó.

### 9.2. Chuyển đổi kiểu tường minh

Một DSL có thể cho phép chuyển đổi ngầm:

~~~text
let amount: Decimal = 10
~~~

Normalizer sau type checking có thể chèn node chuyển đổi:

~~~text
let amount: Decimal = Convert(Integer(10), Decimal)
~~~

Việc chèn conversion cần dựa trên quy tắc tương thích kiểu, không chỉ dựa vào tên kiểu.

### 9.3. Optional và null

Các dạng khai báo:

~~~text
email: String?
email: Optional<String>
~~~

có thể được chuẩn hóa về cùng một biểu diễn nếu DSL quy định chúng đồng nghĩa. Nhưng Optional, nullable và collection rỗng không phải lúc nào cũng có cùng ngữ nghĩa.

### 9.4. Collection và kiểu phần tử

Các khai báo:

~~~text
tags: String[]
tags: List<String>
~~~

có thể được chuẩn hóa thành List<String> nếu DSL định nghĩa cùng cấu trúc và cùng semantics. Nếu một dạng là Set còn dạng kia là List, không được gộp vì thứ tự và tính duy nhất có thể khác nhau.

### 9.5. Đơn vị và kiểu miền

Các giá trị:

~~~text
5 seconds
5000 milliseconds
~~~

có thể được chuẩn hóa về một đơn vị chuẩn như millisecond, nếu phép chuyển đổi được xác định chính xác. Với Money, cần giữ đơn vị tiền tệ; không được coi 100 USD và 100 VND là cùng một giá trị.

## 10. Chuẩn hóa thuộc tính, giá trị mặc định và collection

Mô hình có thể biểu diễn thuộc tính bị bỏ qua, giá trị mặc định, collection rỗng hoặc giá trị null theo nhiều cách.

### 10.1. Bổ sung giá trị mặc định

Giả sử DSL quy định timeout mặc định là 30 giây:

~~~text
task "send_report" {
    action = sendReport()
}
~~~

và:

~~~text
task "send_report" {
    action = sendReport()
    timeout = 30 seconds
}
~~~

Nếu đặc tả nói timeout mặc định là 30 giây, hai mô hình có thể được chuẩn hóa về cùng giá trị. Cần ghi rõ giá trị được bổ sung đến từ default nào để diagnostic và editor có thể giải thích.

### 10.2. Không đồng nhất giá trị mặc định với giá trị bị thiếu

Một trường bị bỏ qua có thể mang nghĩa “dùng mặc định”, trong khi null có thể mang nghĩa “không áp dụng”. Collection rỗng có thể mang nghĩa “không có phần tử”. Ba trạng thái này cần được giữ riêng nếu nghiệp vụ phân biệt chúng.

### 10.3. Collection rỗng và collection không tồn tại

~~~text
tags = []
~~~

khác với việc không khai báo tags nếu việc không khai báo kích hoạt một giá trị mặc định hoặc kế thừa. Normalizer chỉ được gộp hai dạng nếu hợp đồng DSL xác định chúng tương đương.

### 10.4. Thứ tự collection

Nếu collection có ý nghĩa thứ tự, không được sắp xếp lại phần tử chỉ để tạo một dạng chuẩn. Nếu collection là tập hợp không thứ tự, có thể dùng thứ tự ổn định khi serialize hoặc tạo fingerprint, nhưng không được làm thay đổi semantics.

### 10.5. Tính duy nhất

Một collection có thể cho phép trùng lặp hoặc không. Chuẩn hóa không được tự loại bỏ phần tử trùng nếu DSL quy định List hoặc Bag. Nếu kiểu là Set, có thể cần kiểm tra uniqueness và áp dụng quy tắc thứ tự biểu diễn ổn định.

## 11. Chuẩn hóa cấu trúc mô hình

Ngoài biểu thức và kiểu, mô hình có thể cần một cấu trúc thống nhất cho các thành phần cấp cao.

### 11.1. Chuẩn hóa danh sách câu lệnh

Một rule có thể cho phép viết một action trực tiếp hoặc một block:

~~~text
then approve(order)
~~~

và:

~~~text
then {
    approve(order)
}
~~~

Nếu hai dạng có cùng ngữ nghĩa, mô hình chuẩn có thể luôn lưu actions dưới dạng danh sách, kể cả khi chỉ có một phần tử.

### 11.2. Chuẩn hóa khối rỗng

Một block rỗng có thể được biểu diễn bằng danh sách câu lệnh rỗng. Nếu DSL có phân biệt block không được cung cấp với block được cung cấp nhưng rỗng, không nên gộp hai trạng thái.

### 11.3. Chuẩn hóa nhánh điều kiện

Các dạng if-else, when-case hoặc match có thể được chuyển về một cấu trúc điều khiển chuẩn nếu semantics tương thích:

~~~text
Conditional(
  branches = [
    Branch(conditionA, bodyA),
    Branch(conditionB, bodyB)
  ],
  otherwise = bodyDefault
)
~~~

Không nên gộp các cấu trúc có quy tắc fall-through, ưu tiên nhánh hoặc đánh giá điều kiện khác nhau.

### 11.4. Chuẩn hóa định nghĩa quy trình

Một workflow có thể cho phép khai báo bước nối tiếp hoặc nhánh. Mô hình chuẩn có thể biểu diễn mọi bước bằng node Step và mọi chuyển tiếp bằng edge Transition. Điều này giúp thuật toán kiểm tra chu trình, khả năng tới và sinh engine độc lập với cú pháp nguồn.

### 11.5. Chuẩn hóa node đặc biệt

Các cú pháp rút gọn như return, throw, break hoặc continue có thể được chuyển thành node riêng trong IR. Không nên mô hình hóa chúng thành lời gọi hàm thông thường nếu semantics điều khiển luồng khác nhau.

## 12. Chuẩn hóa và mô hình chuẩn tắc (canonical form)

Canonical form là một dạng biểu diễn được quy ước để các mô hình tương đương có thể đưa về cùng một kết quả, trong phạm vi các phép biến đổi đã định nghĩa.

Ví dụ, DSL hỗ trợ:

~~~text
age >= 18
18 <= age
~~~

Nếu hai biểu thức được xác định tương đương trong miền và kiểu tương ứng, canonicalizer có thể đưa chúng về một dạng GreaterOrEqual(age, 18).

### 12.1. Canonical form không phải lúc nào cũng duy nhất toàn cục

Có thể có nhiều dạng chuẩn khác nhau tùy mục đích:

- Dạng chuẩn để type checking.
- Dạng chuẩn để tối ưu hóa.
- Dạng chuẩn để so sánh mô hình.
- Dạng chuẩn để serialize.
- Dạng chuẩn để tạo cache key.

Một dạng phù hợp cho optimizer chưa chắc phù hợp để hiển thị lại cho người dùng. Ví dụ, optimizer có thể sắp xếp biểu thức thuần túy, nhưng formatter cần giữ thứ tự và phong cách người dùng đã viết.

### 12.2. Chuẩn hóa theo từng tầng

Thay vì cố gắng tạo một canonical form cho mọi mục đích, có thể có nhiều representation với hợp đồng rõ:

~~~text
Source AST
  -> Semantic Model
  -> Canonical IR
  -> Optimized IR
  -> Target Representation
~~~

Mỗi representation giải quyết một nhiệm vụ khác nhau và giữ metadata cần thiết.

### 12.3. Canonicalization và hash

Một hệ thống có thể serialize mô hình chuẩn theo thứ tự ổn định rồi tạo hash để cache hoặc phát hiện thay đổi. Để hash có ý nghĩa, serialization cần xác định rõ:

- Thứ tự thuộc tính.
- Cách biểu diễn literal.
- Cách biểu diễn kiểu và tham chiếu.
- Cách xử lý collection có thứ tự và không thứ tự.
- Cách bỏ hoặc giữ metadata không thuộc ngữ nghĩa.

Nếu source location hoặc comment không ảnh hưởng ngữ nghĩa, chúng có thể không nằm trong semantic hash; nhưng vẫn cần được lưu riêng cho công cụ phát triển.

## 13. Thứ tự các bước chuẩn hóa

Các phép chuẩn hóa có thể phụ thuộc lẫn nhau. Thứ tự sai có thể tạo kết quả không đúng hoặc làm mất thông tin cần thiết.

Một pipeline minh họa:

1. Parse và tạo AST có source span.
2. Chuẩn hóa cú pháp rút gọn.
3. Xây symbol table và phân giải tên.
4. Chuẩn hóa alias và tham chiếu.
5. Kiểm tra kiểu hoặc gắn kiểu.
6. Chèn chuyển đổi kiểu được xác định.
7. Bổ sung giá trị mặc định theo đặc tả.
8. Chuẩn hóa collection và cấu trúc điều khiển.
9. Tạo canonical IR.
10. Chạy kiểm tra invariant và validation.

Không phải mọi DSL đều cần đúng thứ tự này. Ví dụ, default có thể được bổ sung trước type checking nếu kiểu của nó đã biết; ngược lại, một default phụ thuộc kiểu có thể cần chờ type resolution.

### 13.1. Phân tích phụ thuộc giữa các pass

Mỗi pass cần khai báo:

- Dạng mô hình đầu vào mà nó yêu cầu.
- Thông tin semantic nào phải có.
- Node hoặc metadata nào nó có thể thay đổi.
- Invariant nào được bảo đảm sau khi chạy.
- Những pass nào cần chạy lại sau biến đổi.

### 13.2. Tránh vòng phụ thuộc

Nếu pass A cần kết quả của pass B và pass B lại cần kết quả của A, pipeline có thể không có thứ tự tuyến tính đơn giản. Có thể cần chia nhỏ pass, lặp đến điểm cố định hoặc thay đổi thiết kế representation.

### 13.3. Phân biệt normalization với optimization pass

Chuẩn hóa thường nhằm đưa mô hình về dạng thống nhất, còn tối ưu hóa nhằm cải thiện cách thực thi. Một số phép như constant folding có thể nằm ở cả hai tùy mục tiêu. Hãy xác định rõ contract thay vì chỉ dựa vào tên pass.

## 14. Bảo toàn ngữ nghĩa khi chuẩn hóa

Chuẩn hóa thường thay đổi cấu trúc mô hình, vì vậy cần có tiêu chí xác định phép biến đổi có hợp lệ hay không.

### 14.1. Tương đương theo ngữ nghĩa

Gọi M là mô hình trước chuẩn hóa và N(M) là mô hình sau chuẩn hóa. Yêu cầu cơ bản:

~~~text
Semantics(M) = Semantics(N(M))
~~~

Đẳng thức này được hiểu theo quan sát mà DSL công bố: giá trị, tác dụng phụ, ngoại lệ, thứ tự thực thi hoặc các hành vi khác.

### 14.2. Bảo toàn thứ tự đánh giá

Nếu DSL quy định điều kiện được đánh giá từ trái sang phải:

~~~text
checkInventory() and chargeAccount()
~~~

không được đổi thành:

~~~text
chargeAccount() and checkInventory()
~~~

nếu hai lời gọi có tác dụng phụ hoặc có thể phát lỗi khác nhau.

### 14.3. Bảo toàn kiểu và chuyển đổi

Khi chuẩn hóa một literal hoặc biểu thức, cần giữ kiểu. Ví dụ, 1 có thể là Integer, Decimal hoặc một kiểu số miền tùy ngữ cảnh. Chuyển tất cả về Decimal có thể làm thay đổi overload hoặc phép toán được chọn.

### 14.4. Bảo toàn giá trị mặc định

Nếu một thuộc tính bị bỏ qua và dùng default theo phiên bản schema, chuẩn hóa cần gắn đúng default tương ứng. Không nên lấy default mới nhất nếu source đang tham chiếu schema phiên bản cũ.

### 14.5. Bảo toàn hành vi lỗi

Một biểu thức có thể phát lỗi khi được đánh giá. Nếu normalizer tính trước hoặc bỏ biểu thức, cần xem thời điểm và khả năng quan sát lỗi có thay đổi không.

### 14.6. Bảo toàn danh tính đối tượng

Nếu mô hình chứa object có ID hoặc được tham chiếu từ nơi khác, việc thay thế node có thể làm đứt tham chiếu. Cần cập nhật mọi liên kết hoặc dùng mapping từ node cũ sang node mới.

## 15. Idempotence và tính ổn định

Một phép chuẩn hóa nên ổn định sau khi đạt dạng chuẩn.

~~~text
normalize(normalize(model)) = normalize(model)
~~~

### 15.1. Vì sao idempotence quan trọng?

- Có thể chạy lại pipeline khi build hoặc reload mà không làm mô hình biến đổi liên tục.
- Dễ cache kết quả.
- Dễ kiểm thử và so sánh.
- Tránh việc mỗi pass tạo thêm node hoặc wrapper không cần thiết.

### 15.2. Ví dụ vi phạm idempotence

Giả sử một pass luôn bọc biểu thức bằng Conversion node dù nó đã có conversion:

~~~text
Convert(IntegerToDecimal, value)
~~~

Chạy lại có thể tạo:

~~~text
Convert(IntegerToDecimal, Convert(IntegerToDecimal, value))
~~~

Mỗi lần chạy lại lại thêm một lớp. Pass cần nhận diện node đã chuẩn hóa và không bọc lặp.

### 15.3. Chuẩn hóa theo quy tắc một chiều

Một cách giúp đạt idempotence là chọn dạng đích rõ ràng và chỉ biến đổi theo hướng đó. Không nên có hai pass thay phiên đổi qua lại giữa hai dạng tương đương.

### 15.4. Kiểm tra điểm cố định

Với pipeline nhiều pass, có thể chạy đến khi không còn thay đổi. Cần giới hạn số vòng và phát hiện chu kỳ nếu các pass làm mô hình dao động.

## 16. Nguồn gốc và khả năng truy vết (traceability)

Khi chuẩn hóa, một node có thể bị thay thế, mở rộng, gộp hoặc tách thành nhiều node. Công cụ vẫn cần biết node mới đến từ phần nguồn nào.

Ví dụ:

~~~text
retry 3 times
~~~

được mở rộng thành một RetryPolicy gồm nhiều thuộc tính. Tất cả node sinh ra có thể tham chiếu đến span của câu lệnh retry ban đầu.

### 16.1. Source span

Source span lưu vị trí bắt đầu và kết thúc trong nguồn gốc. Nó hỗ trợ:

- Báo lỗi tại dòng và cột người dùng đã viết.
- Highlight node trong editor.
- Đặt breakpoint.
- Tạo source map.
- Giải thích nguồn gốc của node sau biến đổi.

### 16.2. Origin mapping

Một mapping có thể liên kết node đầu vào với một hoặc nhiều node đầu ra:

~~~text
SourceNode A -> CanonicalNode X
SourceNode B -> CanonicalNode X
CanonicalNode X -> OptimizedNode Y
~~~

Hai cú pháp nguồn khác nhau có thể tạo cùng một node chuẩn. Vì vậy, mapping có thể là nhiều-một hoặc một-nhiều, không nhất thiết là một-một.

### 16.3. Node tổng hợp

Một số node được tạo bởi normalizer, chẳng hạn giá trị mặc định hoặc conversion ngầm. Chúng không có span nguồn trực tiếp. Có thể gắn synthetic origin cùng thông tin về lý do và quy tắc đã tạo node.

### 16.4. Giữ lexeme và cách viết gốc

Một literal có thể được chuẩn hóa về giá trị số nhưng formatter vẫn cần biết người dùng viết 1_000 hay 1000. Có thể lưu cả semantic value và raw lexeme.

### 16.5. Chẩn đoán sau biến đổi

Nếu lỗi chỉ được phát hiện sau normalization, diagnostic nên trỏ về nguồn gốc thông qua origin mapping. Nếu không có mapping, người dùng có thể chỉ thấy vị trí trong IR mà không biết sửa dòng DSL nào.

## 17. Chuẩn hóa mô hình giữa nhiều frontend và backend

Một kiến trúc DSL có thể có nhiều cách nhập và nhiều cách xuất.

~~~text
Text DSL ----+Visual Editor --+--> Canonical Model --> Backend A
JSON Config ---/                     --> Backend B
                                      --> Interpreter
                                      --> Model Export
~~~

### 17.1. Nhiều frontend

Text parser, visual editor và JSON loader có thể tạo mô hình ban đầu khác nhau. Mỗi frontend cần chuyển về cùng canonical model để các bước semantic analysis và execution dùng chung.

### 17.2. Nhiều backend

Canonical model không nên phụ thuộc vào chi tiết riêng của một backend nếu hệ thống cần sinh nhiều target. Backend-specific lowering có thể diễn ra ở giai đoạn sau.

### 17.3. Ranh giới giữa canonical model và target model

Một mô hình chuẩn của DSL mô tả ý nghĩa ngôn ngữ. Target model mô tả cách biểu diễn phù hợp với nền tảng đích. Không nên đưa mọi chi tiết của target vào canonical model quá sớm, vì điều đó làm frontend phụ thuộc backend.

### 17.4. Chuẩn hóa khi import và export

Khi import mô hình từ định dạng khác, cần kiểm tra phiên bản schema và chuyển về canonical model. Khi export, có thể cần chuyển từ canonical model sang cấu trúc riêng của định dạng đích. Việc export có thể làm mất một số metadata nếu định dạng đích không hỗ trợ.

## 18. Chuẩn hóa và phiên bản mô hình

Mô hình chuẩn có thể thay đổi khi DSL hoặc metamodel phát triển. Ví dụ, một thuộc tính cũ có thể được tách thành hai trường, một kiểu có thể được đổi tên hoặc một cấu trúc cú pháp được thay thế.

### 18.1. Version của schema/metamodel

Canonical model nên có thông tin phiên bản hoặc một cơ chế xác định phiên bản. Nếu không, cùng một dữ liệu có thể được diễn giải khác nhau theo thời gian.

### 18.2. Migration

Migration chuyển mô hình từ phiên bản cũ sang phiên bản mới:

~~~text
Model v1
   |
   v
Migration v1 -> v2
   |
   v
Model v2
   |
   v
Normalization for v2
~~~

Migration có thể thay đổi cấu trúc để phù hợp metamodel mới. Normalization đưa mô hình đã chuyển đổi về dạng chuẩn của phiên bản mới. Hai hoạt động có liên quan nhưng cần được phân biệt.

### 18.3. Default theo phiên bản

Nếu giá trị mặc định thay đổi giữa v1 và v2, migration cần biết mô hình nguồn thuộc phiên bản nào. Không nên chuẩn hóa mô hình cũ bằng default mới nếu điều đó làm thay đổi ý nghĩa.

### 18.4. Tương thích ngược

Một phiên bản DSL mới có thể tiếp tục chấp nhận cú pháp cũ và desugar về canonical model mới. Cách này giúp người dùng di chuyển dần, nhưng cần thông báo deprecation và thời hạn hỗ trợ rõ ràng.

## 19. Kiểm tra tính hợp lệ của mô hình sau chuẩn hóa

Chuẩn hóa không thay thế validation. Sau khi chuẩn hóa, có thể kiểm tra các invariant của canonical model.

Ví dụ, một Rule chuẩn có thể yêu cầu:

~~~text
Rule {
  name: ResolvedIdentifier
  conditions: List<Expression>
  actions: List<Action>
}
~~~

Các invariant:

- name đã được phân giải.
- Mỗi biểu thức có kiểu xác định hoặc lỗi kiểu được ghi nhận.
- Mỗi action thuộc một loại node được hỗ trợ.
- Danh sách conditions và actions thỏa multiplicity của DSL.
- Tham chiếu không trỏ đến node đã bị xóa.
- Node tổng hợp có nguồn gốc hoặc đánh dấu synthetic.

### 19.1. Validation trước và sau chuẩn hóa

Một số lỗi phải phát hiện trước chuẩn hóa, chẳng hạn cú pháp không thể parse. Một số invariant chỉ có thể kiểm tra sau khi tên được phân giải hoặc default được mở rộng.

Có thể có nhiều lớp validation:

- Validation AST: cấu trúc parser tạo ra có nhất quán không.
- Validation semantic model: tên, kiểu và tham chiếu có hợp lệ không.
- Validation canonical model: mọi node tuân theo invariant chuẩn không.
- Validation runtime: dữ liệu và trạng thái thực tế có hợp lệ không.

### 19.2. Không che giấu lỗi bằng chuẩn hóa

Nếu một rule thiếu action bắt buộc, normalizer không nên tự thêm NoOp action chỉ để thỏa invariant, trừ khi đặc tả quy định hành vi đó. Thông thường cần diagnostic rõ ràng.

### 19.3. Diagnostic và mức độ lỗi

Chuẩn hóa có thể tạo warning khi phát hiện cú pháp cũ, alias sắp bị loại bỏ hoặc default ngầm. Lỗi cấu trúc không thể phục hồi nên ngăn các bước sau tiếp tục với mô hình giả định hợp lệ.

## 20. Cài đặt một normalization pass

Một pass có thể được mô tả bằng đầu vào, đầu ra, điều kiện và invariant.

Ví dụ pass mở rộng cú pháp rút gọn:

~~~text
Input:
  RetryShortcut(count = 3)

Output:
  RetryPolicy(
    maxAttempts = 3,
    delay = DefaultDelay
  )

Precondition:
  DefaultDelay đã được xác định cho phiên bản DSL này.

Postcondition:
  Không còn RetryShortcut trong canonical model.
~~~

### 20.1. Visitor pattern

Với AST dạng cây, visitor có thể duyệt từng node và tạo node mới:

~~~text
function normalize(node):
    match node:
        case RetryShortcut(count):
            return RetryPolicy(
                maxAttempts = normalize(count),
                delay = defaultDelay
            )

        case BinaryExpression(op, left, right):
            return normalizeBinary(
                op,
                normalize(left),
                normalize(right)
            )

        case other:
            return normalizeChildren(other)
~~~

Đây là mã giả minh họa. Một implementation thực tế cần xử lý source span, lỗi, symbol references và metadata.

### 20.2. Rewrite rule

Một phép chuẩn hóa có thể được viết như quy tắc thay thế:

~~~text
Parenthesized(x) -> x
AliasType(T) -> CanonicalType(T)
SingleAction(x) -> ActionList([x])
~~~

Mỗi rewrite rule cần điều kiện áp dụng. Ví dụ, Parenthesized có thể bỏ nếu node chỉ lưu nhóm cú pháp và precedence đã được phản ánh trong cây.

### 20.3. Functional transformation

Một thiết kế có thể tạo mô hình mới thay vì sửa trực tiếp mô hình cũ. Cách này giúp:

- Giữ AST nguồn để diagnostic.
- So sánh trước và sau.
- Dễ cache.
- Tránh trạng thái trung gian bị chia sẻ ngoài ý muốn.

Tuy nhiên, sao chép toàn bộ mô hình có thể tốn bộ nhớ. Có thể dùng immutable nodes, structural sharing hoặc cập nhật có kiểm soát.

### 20.4. In-place transformation

Sửa trực tiếp mô hình có thể hiệu quả hơn nhưng khó bảo toàn nguồn gốc và rollback. Nếu dùng, cần quản lý ownership, invalidation của cache và tham chiếu đến node bị thay thế.

### 20.5. Báo cáo biến đổi

Một pass có thể trả về:

~~~text
NormalizationResult {
  model
  diagnostics
  originMap
  changed
}
~~~

Thông tin changed giúp pass manager biết có cần chạy lại pass phụ thuộc hay không.

## 21. Thứ tự duyệt và chuẩn hóa collection

Khi chuẩn hóa danh sách hoặc tập hợp, cần hiểu collection có giữ thứ tự hay không.

### 21.1. Danh sách có thứ tự

Nếu actions được thực hiện lần lượt, thứ tự phần tử là một phần của semantics. Không được sắp xếp theo tên hoặc ID để tạo canonical form.

### 21.2. Tập hợp không thứ tự

Nếu permissions là tập hợp không thứ tự, có thể serialize theo một thứ tự ổn định để tạo diff hoặc hash. Việc này chỉ thay đổi thứ tự biểu diễn, không được thay đổi cách xử lý nghiệp vụ.

### 21.3. Loại bỏ phần tử trùng

Chỉ loại bỏ trùng lặp khi kiểu collection và semantics quy định unique. Với List, hai phần tử giống nhau có thể có ý nghĩa vì thứ tự hoặc số lần xuất hiện.

### 21.4. Chuẩn hóa map

Map có thể được serialize theo thứ tự key ổn định. Nhưng không nên thay đổi cách so sánh key nếu DSL quy định so sánh phân biệt chữ hoa/chữ thường hoặc theo locale.

## 22. Chuẩn hóa biểu thức điều kiện và logic

Các biểu thức logic có thể có nhiều dạng tương đương. Chuẩn hóa có thể giúp kiểm tra, so sánh hoặc tạo kế hoạch thực thi.

### 22.1. Chuẩn hóa ngoặc và precedence

Parser phải xác định cấu trúc trước. Normalizer không được suy luận lại precedence chỉ từ chuỗi ký tự.

Ví dụ:

~~~text
a or b and c
~~~

Nếu and có precedence cao hơn or, AST phải biểu diễn:

~~~text
Or(a, And(b, c))
~~~

Sau đó có thể loại bỏ node ngoặc không cần thiết mà không đổi cấu trúc.

### 22.2. Đưa về dạng phủ định chuẩn

Có thể dùng các luật De Morgan:

~~~text
not (a and b) -> (not a) or (not b)
not (a or b)  -> (not a) and (not b)
~~~

Chỉ áp dụng nếu semantics Boolean hai giá trị và các biểu thức không có tác dụng phụ hoặc thứ tự đánh giá không bị thay đổi. Với logic ba trạng thái hoặc biểu thức nullable, cần quy tắc riêng.

### 22.3. Chuẩn hóa chuỗi điều kiện

Một DSL có thể biểu diễn:

~~~text
where a and b and c
~~~

thành một node And với danh sách điều kiện. Điều này giúp optimizer xử lý điều kiện theo nhóm. Nhưng không được tự sắp xếp điều kiện nếu chúng có tác dụng phụ hoặc có thể phát lỗi khác nhau.

### 22.4. Chuẩn hóa so sánh

Các dạng:

~~~text
10 < order.quantity
order.quantity > 10
~~~

có thể được đưa về cùng hướng so sánh nếu toán tử và kiểu có quy tắc đảo chiều xác định. Cần đặc biệt chú ý phép so sánh với null, NaN và kiểu miền.

## 23. Chuẩn hóa mô hình cho biến đổi giữa các DSL

Khi chuyển từ DSL nguồn sang DSL đích, canonical model đóng vai trò lớp trung gian.

~~~text
DSL A
  |
  v
Parser A
  |
  v
Canonical Model
  |
  v
Transformation / Mapping
  |
  v
Target Model
  |
  v
DSL B hoặc Backend B
~~~

### 23.1. Tách khác biệt cú pháp khỏi ánh xạ ngữ nghĩa

Nếu parser A và parser B cùng tạo canonical model, phần mapping không cần biết cú pháp của từng DSL. Nó làm việc với khái niệm chung như Rule, Condition, Action hoặc Query.

### 23.2. Canonical model phải đủ biểu đạt

Nếu mô hình chuẩn không thể biểu diễn một tính năng của DSL nguồn, thông tin có thể bị mất trong quá trình chuyển đổi. Cần:

- Mở rộng canonical model.
- Lưu extension metadata.
- Tạo node opaque cho phần chưa hỗ trợ.
- Hoặc báo rõ tính năng không thể chuyển đổi.

Không nên âm thầm bỏ một cấu trúc nguồn chỉ vì mô hình chuẩn không có trường tương ứng.

### 23.3. Mapping không nhất thiết một-một

Một cấu trúc nguồn có thể tạo nhiều node chuẩn; nhiều cấu trúc nguồn có thể hội tụ vào một node chuẩn. Tương tự, một node chuẩn có thể được sinh thành nhiều cấu trúc đích.

### 23.4. Mất mát và không mất mát

Một phép chuyển đổi là lossless nếu có thể khôi phục đầy đủ thông tin cần thiết của mô hình nguồn. Nếu chỉ bảo toàn semantics nhưng bỏ cách viết, comment hoặc metadata, nó có thể là semantic-preserving nhưng không source-preserving.

Nên công bố rõ loại bảo toàn mà pipeline cam kết.

## 24. Ví dụ tổng hợp: chuẩn hóa một mô hình quy tắc

Giả sử DSL hỗ trợ hai cách viết:

~~~text
rule "priority" when order.total >= 1000 => approve(order)
~~~

và:

~~~text
rule "priority" {
    condition order.total >= 1000
    action approve(order)
}
~~~

Ngoài ra, DSL quy định:

- condition có thể được viết bằng when hoặc condition.
- action đơn có thể viết trực tiếp hoặc trong danh sách.
- timeout mặc định là 30 seconds.
- approve là một hàm dựng sẵn.

### 24.1. AST nguồn thứ nhất

~~~text
RuleShortcut(
  name = "priority",
  condition = GreaterOrEqual(
    Property(order, total),
    IntegerLiteral(1000)
  ),
  action = Call(approve, [order])
)
~~~

### 24.2. AST nguồn thứ hai

~~~text
RuleBlock(
  name = "priority",
  condition = GreaterOrEqual(
    Property(order, total),
    IntegerLiteral(1000)
  ),
  action = Call(approve, [order])
)
~~~

### 24.3. Chuẩn hóa cú pháp

Cả hai được chuyển về:

~~~text
Rule(
  name = "priority",
  conditions = [
    GreaterOrEqual(
      Property(order, total),
      IntegerLiteral(1000)
    )
  ],
  actions = [
    Call(approve, [order])
  ],
  timeout = Duration(30, seconds)
)
~~~

### 24.4. Phân giải tên và kiểu

Compiler liên kết order đến symbol trong scope, total đến thuộc tính của Order và approve đến hàm dựng sẵn. Sau type checking, literal 1000 có thể được chuyển thành kiểu Money nếu ngữ cảnh và quy tắc DSL cho phép.

### 24.5. Canonical model

~~~text
Rule(
  name = Symbol("priority"),
  conditions = [
    GreaterOrEqual(
      Property(Symbol(order), Symbol(total)),
      Convert(IntegerToMoney, Integer(1000))
    )
  ],
  actions = [
    Call(Symbol(approve), [Symbol(order)])
  ],
  timeout = Duration(30, seconds)
)
~~~

### 24.6. Những metadata cần giữ

- Source span của rule và từng biểu thức.
- Cách viết ban đầu là dạng rút gọn hay dạng block.
- Nguồn của timeout 30 seconds là default.
- Symbol ID của order, total và approve.
- Kiểu và conversion được chèn.

Nhờ vậy, backend có thể dùng canonical model, còn IDE vẫn có thể hiển thị nguồn gốc và giải thích giá trị mặc định.

## 25. Những lỗi thiết kế thường gặp

### 25.1. Gộp các cấu trúc chỉ giống hình thức

Hai biểu thức có thể trông giống nhau nhưng có semantics khác do kiểu, null, tác dụng phụ hoặc thứ tự đánh giá. Chỉ chuẩn hóa khi có quy tắc tương đương được xác định.

### 25.2. Bổ sung default không rõ nguồn

Nếu normalizer tự thêm giá trị mà không biết default theo phiên bản nào, kết quả có thể thay đổi hành vi khi schema cập nhật.

### 25.3. Làm mất source span

Sau chuẩn hóa, diagnostic có thể trỏ đến IR thay vì nguồn DSL. Cần giữ origin mapping từ đầu.

### 25.4. Chuẩn hóa trước khi phân giải tên

Nếu alias hoặc tên ngắn còn mơ hồ, thay tên quá sớm có thể liên kết sai symbol. Hãy xác định pass nào cần name resolution.

### 25.5. Sắp xếp lại collection có thứ tự

Đổi thứ tự actions hoặc workflow steps có thể thay đổi hành vi. Chỉ chuẩn hóa thứ tự cho collection được định nghĩa là không thứ tự.

### 25.6. Xóa thông tin cú pháp quá sớm

Formatter, refactoring tool và debugger có thể cần biết người dùng viết dạng rút gọn hay đầy đủ. Hãy giữ metadata hoặc AST nguồn song song khi cần.

### 25.7. Pass không idempotent

Chạy lại normalizer tạo thêm wrapper, conversion hoặc default node. Mỗi pass cần có kiểm tra để không lặp biến đổi.

### 25.8. Trộn normalization với optimization

Một pass vừa mở rộng cú pháp, vừa sắp xếp biểu thức, vừa loại bỏ lệnh có thể khó kiểm tra và khó truy nguyên lỗi. Chia pass theo mục tiêu và invariant.

### 25.9. Dùng canonical model quá phụ thuộc backend

Nếu mô hình chuẩn đã chứa chi tiết riêng của một target, frontend khác khó tái sử dụng. Hãy tách canonical semantic model khỏi target-specific lowering.

### 25.10. Che giấu mô hình không hợp lệ

Không nên tạo node giả hoặc bỏ trường sai để pipeline tiếp tục mà không diagnostic. Mô hình không hợp lệ cần được ghi nhận rõ.

## 26. Kiểm thử chuẩn hóa mô hình

Kiểm thử tập trung vào tính đúng đắn của từng phép biến đổi và invariant của mô hình đầu ra. Một số nhóm kiểm thử:

### 26.1. Kiểm thử từng rewrite rule

Với mỗi quy tắc, chuẩn bị:

- Mô hình khớp điều kiện áp dụng.
- Mô hình gần giống nhưng không khớp.
- Trường hợp biên.
- Trường hợp có metadata hoặc tham chiếu.

Ví dụ, chỉ mở rộng RetryShortcut khi default delay đã được xác định.

### 26.2. Kiểm thử idempotence

~~~text
first = normalize(model)
second = normalize(first)
assert equivalentStructure(first, second)
~~~

So sánh cấu trúc semantic, không nhất thiết so sánh source span hoặc metadata thời gian tạo.

### 26.3. Kiểm thử bảo toàn ngữ nghĩa

Chạy mô hình trước và sau chuẩn hóa trong interpreter tham chiếu, rồi so sánh:

- Giá trị kết quả.
- Thứ tự tác dụng phụ.
- Ngoại lệ.
- Sự kiện hoặc thao tác I/O quan sát được.

### 26.4. Kiểm thử canonical equivalence

Hai cách viết được đặc tả là tương đương nên tạo ra canonical model tương đương:

~~~text
normalize(parse(sourceA)) == normalize(parse(sourceB))
~~~

Có thể so sánh semantic structure hoặc canonical serialization.

### 26.5. Kiểm thử không làm mất metadata

Kiểm tra source span, origin map, comment và raw lexeme còn được giữ khi công cụ cần chúng.

### 26.6. Kiểm thử tham chiếu

Sau khi node được thay thế hoặc gộp, xác nhận mọi tham chiếu trỏ đến node mới hoặc symbol chuẩn, không còn trỏ đến object đã bị loại bỏ.

### 26.7. Kiểm thử phiên bản

Chạy mô hình thuộc các phiên bản schema khác nhau để xác nhận default và alias được xử lý đúng phiên bản.

### 26.8. Kiểm thử property-based

Sinh các AST hợp lệ theo grammar, chuẩn hóa rồi kiểm tra invariant, idempotence và tính tương đương. Có thể sinh các biến thể cú pháp tương đương để kiểm tra chúng hội tụ về cùng canonical form.

### 26.9. Kiểm thử hồi quy

Khi thay đổi metamodel hoặc rewrite rule, chạy lại các mô hình đã lưu. Một thay đổi nhỏ trong pass có thể làm thay đổi canonical serialization hoặc cache key.

## 27. Hiệu năng và quản lý bộ nhớ

Chuẩn hóa thường thêm các lượt duyệt cây và có thể tạo node mới. Với mô hình lớn, cần cân nhắc chi phí.

### 27.1. Duyệt cây nhiều lần

Nhiều pass riêng biệt dễ hiểu nhưng có thể quét toàn bộ mô hình nhiều lần. Có thể gộp các phép biến đổi độc lập trong một visitor khi điều đó không làm rối thứ tự và invariant.

### 27.2. Structural sharing

Nếu mô hình bất biến, node không thay đổi có thể được dùng lại thay vì sao chép toàn bộ cây. Điều này giảm allocation nhưng cần quản lý tham chiếu và lifetime.

### 27.3. Cache kết quả

Có thể cache canonical model theo source hash, schema version và compiler version. Cache key cần bao gồm mọi yếu tố ảnh hưởng đến kết quả chuẩn hóa.

### 27.4. Incremental normalization

Trong IDE, chỉ một phần mô hình thay đổi sau mỗi thao tác. Có thể chuẩn hóa lại vùng bị ảnh hưởng nếu biết phụ thuộc giữa các node. Tuy nhiên, thay đổi một khai báo có thể ảnh hưởng nhiều tham chiếu ở nơi khác.

### 27.5. Tránh cache kết quả thiếu ngữ cảnh

Nếu default phụ thuộc schema hoặc profile, cache chỉ theo source text là không đủ. Cần đưa schema version, language version và cấu hình liên quan vào cache key.

## 28. Quy trình thiết kế chuẩn hóa mô hình

Một quy trình thực tế:

1. Xác định mục đích của canonical model và các bước sẽ sử dụng nó.
2. Liệt kê các biến thể cú pháp hoặc cấu trúc cần hội tụ.
3. Xác định những khác biệt có thực sự tương đương về ngữ nghĩa hay không.
4. Thiết kế schema đầu ra và invariant của mô hình chuẩn.
5. Chia biến đổi thành các pass nhỏ theo trách nhiệm.
6. Xác định thứ tự pass và thông tin phụ thuộc.
7. Quy định cách giữ source span, origin map, comment và raw lexeme.
8. Xác định chính sách default, null, collection, kiểu và alias.
9. Viết kiểm thử idempotence, semantics preservation và canonical equivalence.
10. Đo chi phí trên mô hình đại diện và bổ sung cache/incremental processing khi cần.
11. Quản lý version của canonical model và migration.
12. Ghi lại các thay đổi normalization như một phần của đặc tả ngôn ngữ.

## 29. Bài tập tự kiểm tra

### Bài 1: Nhận diện chuẩn hóa

Một DSL cho phép viết một action trực tiếp hoặc danh sách actions trong block. Hãy đề xuất dạng canonical model và giải thích vì sao các bước sau sẽ đơn giản hơn.

### Bài 2: Desugaring

Một câu lệnh retry 3 times được mở rộng thành RetryPolicy. Hãy xác định thông tin cần biết để điền delay mặc định và metadata nào cần giữ.

### Bài 3: Chuẩn hóa biểu thức

Hai biểu thức a >= b và b <= a được cho là tương đương trong DSL. Hãy đề xuất canonical form và nêu các điều kiện kiểu cần kiểm tra trước khi áp dụng.

### Bài 4: Alias và tham chiếu

Một module import Customer dưới alias Client. Hãy mô tả cách phân giải và chuẩn hóa tham chiếu Client mà vẫn giữ tên người dùng đã viết để phục vụ diagnostic.

### Bài 5: Default và null

Một thuộc tính timeout có default 30 seconds. Hãy phân biệt trường hợp bỏ qua thuộc tính, đặt timeout = null và đặt timeout = 0. Trường hợp nào có thể chuẩn hóa về cùng một giá trị?

### Bài 6: Idempotence

Một pass luôn bọc mọi biểu thức số bằng Convert(Decimal, expression). Hãy giải thích vì sao chạy pass lần hai có thể tạo wrapper lồng và đề xuất cách sửa.

### Bài 7: Bảo toàn thứ tự

Một danh sách actions được thực thi theo thứ tự. Hãy giải thích vì sao sắp xếp actions theo tên để tạo canonical form là không an toàn.

### Bài 8: Traceability

Một cú pháp rút gọn tạo ra ba node chuẩn. Hãy đề xuất origin mapping để mỗi node mới có thể truy ngược đến đúng source span.

### Bài 9: Nhiều frontend

Text DSL và visual editor cùng tạo một canonical model. Hãy nêu trách nhiệm của từng frontend và những invariant mà mô hình chung phải bảo đảm.

### Bài 10: Kiểm thử

Hãy thiết kế kiểm thử để xác nhận hai cách viết DSL tương đương tạo cùng canonical model, chuẩn hóa idempotent và không làm thay đổi tác dụng phụ.

## Kết luận

Chuẩn hóa mô hình là quá trình đưa AST hoặc semantic model về một biểu diễn thống nhất để các bước phân tích, tối ưu hóa, sinh mã và thực thi xử lý nhất quán. Các phép biến đổi có thể mở rộng cú pháp rút gọn, chuẩn hóa biểu thức, tên, kiểu, tham chiếu, giá trị mặc định, collection và cấu trúc điều khiển. Một canonical model tốt cần bảo toàn ngữ nghĩa, có tính xác định và idempotent, đồng thời giữ nguồn gốc đủ để diagnostic và debugger truy vết về DSL source. Chuẩn hóa cần được chia thành các pass có invariant rõ ràng, phối hợp với phân giải tên, kiểm tra kiểu, validation và migration phiên bản. Khi thiết kế đúng, nó tạo ranh giới ổn định giữa nhiều frontend DSL và các backend, giảm trường hợp đặc biệt và làm cho toàn bộ pipeline biến đổi ngôn ngữ dễ mở rộng hơn.
