# Tối ưu hóa trong biên dịch và thông dịch DSL

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích mục tiêu của tối ưu hóa trong compiler và interpreter của một DSL.
- Phân biệt tối ưu hóa mã nguồn, cây cú pháp, biểu diễn trung gian và hành vi lúc chạy.
- Mô tả pipeline tối ưu hóa và vai trò của các optimization pass.
- Hiểu các kỹ thuật như constant folding, constant propagation, dead code elimination, common subexpression elimination và inlining.
- Nhận biết các kỹ thuật tối ưu luồng điều khiển, vòng lặp, bộ nhớ và runtime.
- Giải thích vì sao tối ưu hóa phải bảo toàn ngữ nghĩa chương trình.
- Chọn chiến lược tối ưu dựa trên số liệu đo, đặc điểm DSL và chi phí thực thi.
- Kiểm thử tính tương đương, đo hiệu năng và xử lý vấn đề khi tối ưu hóa làm thay đổi hành vi.

## 1. Tối ưu hóa là gì?

Tối ưu hóa (optimization) là quá trình biến đổi chương trình hoặc cách thực thi chương trình nhằm cải thiện một hay nhiều thuộc tính như tốc độ, mức sử dụng bộ nhớ, dung lượng mã, mức tiêu thụ năng lượng hoặc độ trễ. Trong ngữ cảnh biên dịch và thông dịch DSL, tối ưu hóa thường được thực hiện sau khi nguồn đã được phân tích thành AST hoặc một biểu diễn trung gian (Intermediate Representation, IR).

Ví dụ, một DSL quy tắc có thể chứa:

~~~text
let subtotal = order.quantity * order.unitPrice
let shipping = 0
let total = subtotal + shipping
return total
~~~

Nếu shipping luôn bằng 0 và phép cộng không có tác dụng phụ, compiler có thể rút gọn:

~~~text
let subtotal = order.quantity * order.unitPrice
return subtotal
~~~

Chương trình sau có ít phép tính hơn nhưng vẫn phải tạo ra cùng kết quả và giữ nguyên các hành vi quan sát được.

Tối ưu hóa không đơn thuần là làm mã ngắn hơn. Mã ngắn hơn có thể chạy chậm hơn; mã có ít phép toán hơn có thể dùng nhiều bộ nhớ hơn; một phép biến đổi có vẻ hiển nhiên có thể làm thay đổi thứ tự tác dụng phụ hoặc cách xử lý lỗi. Vì vậy, mọi tối ưu hóa phải được đánh giá bằng cả tính đúng đắn và lợi ích thực tế.

## 2. Vì sao DSL cần tối ưu hóa?

Một DSL thường được thiết kế để giải quyết một nhóm tác vụ cụ thể: mô tả quy tắc nghiệp vụ, truy vấn dữ liệu, cấu hình quy trình, định nghĩa giao diện, tính toán tài chính hoặc điều khiển thiết bị. Dù cú pháp có thể ngắn gọn, chương trình DSL vẫn có thể tạo ra lượng công việc lớn khi thực thi.

Ví dụ, một DSL truy vấn có thể mô tả:

~~~text
from orders
where status == "PAID"
select customerId, total
order by total descending
~~~

Compiler có thể phân tích truy vấn và chọn cách thực thi phù hợp: lọc sớm, chỉ đọc các cột cần thiết, dùng chỉ mục hoặc đẩy phép lọc xuống hệ quản trị dữ liệu. Đây là tối ưu hóa dựa trên ngữ nghĩa của DSL và khả năng của backend.

Các mục tiêu thường gặp:

- **Tốc độ thực thi:** giảm số phép tính, số lần gọi hàm hoặc số lần truy cập dữ liệu.
- **Độ trễ:** giảm thời gian phản hồi của một yêu cầu, đặc biệt với hệ thống tương tác.
- **Thông lượng:** tăng số chương trình hoặc tác vụ có thể xử lý trong một đơn vị thời gian.
- **Bộ nhớ:** giảm cấp phát, giảm bản sao dữ liệu hoặc tái sử dụng cấu trúc.
- **Kích thước mã:** giảm bytecode, mã máy hoặc gói triển khai.
- **Chi phí runtime:** giảm số lần dispatch, tra cứu, chuyển đổi kiểu hoặc gọi dịch vụ.
- **Khả năng mở rộng:** giúp chương trình lớn vẫn chạy ổn định khi dữ liệu hoặc số quy tắc tăng.

Không phải mục tiêu nào cũng có thể tối ưu đồng thời. Chẳng hạn, inlining có thể tăng tốc lời gọi hàm nhưng làm mã lớn hơn. Caching có thể giảm thời gian tính toán nhưng tăng bộ nhớ và tạo yêu cầu invalidation.

## 3. Tối ưu hóa ở những giai đoạn nào?

Compiler hoặc interpreter có thể tối ưu hóa ở nhiều tầng:

~~~text
DSL source
    |
    v
Lexer và Parser
    |
    v
AST
    |  AST simplification
    v
Semantic analysis và type checking
    |
    v
Intermediate Representation (IR)
    |  IR optimization passes
    v
Backend hoặc bytecode
    |  code generation / bytecode optimization
    v
Runtime
    |  caching, specialization, JIT
    v
Thực thi
~~~

### 3.1. Tối ưu hóa ở mức nguồn

Ở mức nguồn, công cụ có thể chuẩn hóa cú pháp hoặc loại bỏ cấu trúc không cần thiết trước khi tạo IR. Tuy nhiên, biến đổi mã nguồn có thể làm mất comment, định dạng hoặc vị trí gốc. Nếu DSL hỗ trợ formatter hay IDE, nên giữ metadata để ánh xạ kết quả về nguồn ban đầu.

### 3.2. Tối ưu hóa AST

AST chứa cấu trúc có ý nghĩa như biểu thức cộng, lời gọi hàm, câu lệnh điều kiện và vòng lặp. Một số phép đơn giản hóa có thể thực hiện trực tiếp trên AST, chẳng hạn thay biểu thức số học hằng bằng literal kết quả.

### 3.3. Tối ưu hóa IR

IR là dạng biểu diễn độc lập hơn với cú pháp DSL và có cấu trúc thuận tiện cho phân tích dữ liệu. Đây thường là nơi thực hiện nhiều optimization pass vì các phép biến đổi có thể dùng chung cho nhiều cú pháp nguồn và nhiều backend.

### 3.4. Tối ưu hóa bytecode hoặc mã máy

Backend có thể chọn lệnh máy, thanh ghi, cách bố trí dữ liệu hoặc chuỗi lệnh phù hợp với kiến trúc đích. Một số tối ưu hóa chỉ có ý nghĩa khi biết đặc điểm CPU hoặc runtime.

### 3.5. Tối ưu hóa lúc chạy

Interpreter có thể theo dõi kiểu dữ liệu và hành vi thực tế để tối ưu các điểm nóng. JIT compiler có thể biên dịch những đoạn được thực thi thường xuyên thành mã máy chuyên biệt.

## 4. Điều kiện quan trọng nhất: bảo toàn ngữ nghĩa

Một phép tối ưu hóa hợp lệ phải giữ nguyên hành vi mà chương trình được phép quan sát. Điều này thường được gọi là semantic preservation hoặc semantics-preserving transformation.

Hành vi quan sát được có thể bao gồm:

- Giá trị kết quả.
- Thứ tự tác dụng phụ như ghi dữ liệu, gửi thông báo hoặc gọi dịch vụ.
- Ngoại lệ và lỗi được phát sinh.
- Thứ tự đánh giá biểu thức nếu nó có tác dụng phụ.
- Kết quả phụ thuộc thời gian, trạng thái hoặc dữ liệu bên ngoài.
- Hành vi đồng thời và đồng bộ nếu DSL hỗ trợ thực thi song song.

Ví dụ:

~~~text
let a = chargeCard(order)
let b = writeAuditLog(order)
return b
~~~

Không thể loại bỏ lời gọi chargeCard chỉ vì biến a không được dùng. Lời gọi có tác dụng phụ và có thể thay đổi trạng thái thanh toán.

Ngược lại:

~~~text
let unused = 10 * 20
return order.total
~~~

Nếu phép nhân chỉ là phép tính thuần túy và không thể phát sinh lỗi quan sát được, biểu thức gán unused có thể bị loại bỏ.

### 4.1. Hàm thuần túy và tác dụng phụ

Hàm thuần túy (pure function) có kết quả chỉ phụ thuộc vào đối số và không làm thay đổi trạng thái bên ngoài. Hàm thuần túy dễ tối ưu hơn vì compiler có thể tính trước, gộp hoặc loại bỏ lời gọi khi chứng minh được kết quả không cần thiết.

Hàm có tác dụng phụ (side effect) có thể đọc hoặc ghi trạng thái bên ngoài, thực hiện I/O, ném lỗi, thay đổi dữ liệu hoặc gọi hệ thống khác. Compiler phải bảo toàn các hành vi đó.

Ví dụ:

~~~text
tax = calculateTax(amount)
log("tax calculated")
~~~

Nếu calculateTax là hàm thuần túy, compiler có thể tính trước khi amount là hằng. Nhưng log không thể bị xóa chỉ vì giá trị trả về của nó không được dùng.

### 4.2. Thứ tự đánh giá

Giả sử DSL quy định đánh giá đối số từ trái sang phải:

~~~text
combine(nextValue(), updateCounter())
~~~

Đổi thứ tự hai lời gọi có thể làm kết quả khác nếu cả hai thay đổi trạng thái. Một tối ưu hóa chỉ được hoán đổi phép tính khi chứng minh được chúng độc lập hoặc không có tác dụng phụ ảnh hưởng lẫn nhau.

### 4.3. Số học dấu phẩy động

Các phép tính dấu phẩy động có thể bị ảnh hưởng bởi thứ tự kết hợp và làm tròn:

~~~text
(a + b) + c
a + (b + c)
~~~

Hai biểu thức có thể cho kết quả khác nhau do độ chính xác hữu hạn. Vì vậy, compiler không được tùy tiện đổi thứ tự phép toán nếu DSL yêu cầu tuân thủ ngữ nghĩa IEEE hoặc kết quả số học chính xác theo quy tắc đã công bố.

### 4.4. Tràn số và chia cho không

Tối ưu hóa phép tính hằng cần biết quy tắc của DSL đối với tràn số, chia cho không và phép toán không hợp lệ. Ví dụ, nếu phép chia cho 0 phải phát lỗi tại runtime, compiler không nên biến đổi hoặc loại bỏ biểu thức theo cách làm mất lỗi đó.

### 4.5. Giả định về dữ liệu và môi trường

Một phép biến đổi chỉ đúng khi các giả định của nó đúng. Nếu compiler giả định một trường không thể null nhưng dữ liệu runtime có thể null, tối ưu hóa truy cập thuộc tính có thể làm chương trình lỗi. Các giả định cần được bảo đảm bằng type system, schema, validation hoặc guard lúc chạy.

## 5. Biểu diễn trung gian và optimization pass

IR là biểu diễn của chương trình sau khi đã được phân tích. Một IR có thể gần với AST, dạng ba địa chỉ, bytecode, control-flow graph hoặc SSA (Static Single Assignment).

Ví dụ, biểu thức:

~~~text
total = quantity * unitPrice + shipping
~~~

có thể được chuyển thành IR dạng ba địa chỉ:

~~~text
t1 = quantity * unitPrice
t2 = t1 + shipping
total = t2
~~~

Mỗi lệnh thực hiện một thao tác đơn giản. Điều này giúp compiler phân tích phụ thuộc và biến đổi từng bước.

### 5.1. Control-flow graph

Control-flow graph (CFG) biểu diễn các khối lệnh cơ bản (basic block) và cạnh chuyển điều khiển giữa chúng.

~~~text
          [Entry]
             |
         [Check x]
          /     \
       true     false
        /         \
 [Block A]       [Block B]
        \         /
         [Merge]
             |
          [Exit]
~~~

CFG giúp compiler xác định nhánh nào có thể đến được, biến nào được định nghĩa ở đâu và những phép tính nào có thể di chuyển giữa các khối.

### 5.2. Static Single Assignment

Trong dạng SSA, mỗi biến chỉ được gán một lần. Các giá trị mới nhận tên phiên bản khác nhau:

~~~text
x1 = 10
x2 = x1 + 5
x3 = x2 * 2
~~~

Nếu nhiều nhánh tạo ra các giá trị khác nhau cho cùng một biến, SSA có thể dùng nút phi (phi node) để hợp nhất giá trị tại điểm nhập luồng.

~~~text
if condition:
    x1 = 10
else:
    x2 = 20
x3 = phi(x1, x2)
~~~

SSA giúp phân tích định nghĩa và sử dụng biến rõ ràng hơn, hỗ trợ constant propagation, dead code elimination và nhiều tối ưu hóa khác.

### 5.3. Optimization pass

Một optimization pass là một bước phân tích hoặc biến đổi IR. Ví dụ:

- Constant folding: tính trước biểu thức hằng.
- Constant propagation: truyền giá trị hằng đến nơi sử dụng.
- Dead code elimination: loại bỏ lệnh không ảnh hưởng kết quả.
- Common subexpression elimination: dùng lại kết quả biểu thức giống nhau.
- Loop invariant code motion: đưa phép tính không đổi ra khỏi vòng lặp.

Các pass thường chạy theo chuỗi. Một pass có thể làm lộ cơ hội cho pass khác, nên thứ tự và số lần chạy cần được thiết kế có chủ đích.

## 6. Constant folding

Constant folding (gấp hằng) là tính trước biểu thức mà mọi toán hạng đều đã biết tại thời điểm biên dịch.

Trước:

~~~text
timeout = 60 * 5
threshold = 100 + 20
~~~

Sau:

~~~text
timeout = 300
threshold = 120
~~~

Compiler không cần thực hiện phép nhân hoặc cộng đó mỗi lần chương trình chạy.

### 6.1. Biểu thức lồng nhau

~~~text
limit = (10 + 5) * (8 - 2)
~~~

Có thể rút gọn thành:

~~~text
limit = 90
~~~

Compiler thường duyệt AST theo kiểu hậu tự: tối ưu các nút con trước, rồi mới xét nút cha.

### 6.2. Literal và kiểu

Constant folding phải tuân thủ kiểu và quy tắc số học của DSL. Nếu 10 là Integer còn 2.5 là Decimal, kết quả có thể là Decimal. Nếu kiểu Money yêu cầu đơn vị tiền tệ, không thể chỉ tính số học trên phần số mà bỏ qua đơn vị.

### 6.3. Biểu thức hằng có thể phát lỗi

~~~text
ratio = 10 / 0
~~~

Compiler cần biết DSL quy định chia cho không như thế nào. Có thể báo lỗi ngay lúc biên dịch nếu đây là lỗi chắc chắn và ngữ nghĩa cho phép phát hiện sớm. Nếu ngôn ngữ quy định ngoại lệ phải xảy ra khi thực thi, compiler phải bảo toàn thời điểm và hành vi lỗi.

### 6.4. Giới hạn của constant folding

Không thể tính trước một biểu thức phụ thuộc dữ liệu runtime:

~~~text
discount = order.total * rate
~~~

trừ khi compiler có bằng chứng order.total và rate là hằng tại thời điểm biên dịch. Việc một biến thường có cùng giá trị trong ví dụ không đủ để coi nó là hằng.

## 7. Constant propagation

Constant propagation (lan truyền hằng) thay các lần sử dụng biến bằng giá trị hằng khi compiler chứng minh biến vẫn giữ giá trị đó.

Trước:

~~~text
let limit = 100
let accepted = order.quantity <= limit
~~~

Sau khi truyền hằng:

~~~text
let accepted = order.quantity <= 100
~~~

Nếu sau đó có constant folding hoặc simplification khác, compiler có thể tối ưu thêm.

### 7.1. Khi giá trị không còn là hằng

~~~text
let limit = 100
if urgent:
    limit = 50
check(order.quantity <= limit)
~~~

Sau nhánh điều kiện, limit không còn một giá trị hằng duy nhất trong mọi đường đi. Compiler cần phân tích luồng điều khiển để biết giá trị có thể là 100 hoặc 50.

### 7.2. Kết hợp với SSA

SSA giúp mỗi phiên bản của biến có một định nghĩa rõ ràng. Nếu một phiên bản được gán literal hằng, compiler có thể truyền hằng đến mọi nơi sử dụng phiên bản đó, miễn là không có biến đổi làm mất giả định.

### 7.3. Hằng theo cấu hình

Một DSL cấu hình có thể có giá trị được xác định lúc biên dịch theo profile:

~~~text
constant MAX_RETRIES = 3
if retryCount < MAX_RETRIES:
    retry()
~~~

Nếu profile và constant đã cố định, compiler có thể truyền giá trị 3. Nhưng nếu cùng một artifact được dùng cho nhiều profile, không nên gắn cứng một cấu hình vào artifact dùng chung.

## 8. Dead code elimination

Dead code elimination (DCE) loại bỏ câu lệnh hoặc phép tính không ảnh hưởng đến kết quả quan sát được của chương trình.

Ví dụ:

~~~text
let temporary = 10 * 2
let result = order.total
return result
~~~

Nếu temporary không được sử dụng và phép nhân không có tác dụng phụ, compiler có thể xóa phép tính:

~~~text
let result = order.total
return result
~~~

### 8.1. Mã không thể tới được

~~~text
return result
log("This line cannot run")
~~~

Nếu return kết thúc hàm, lời gọi log phía sau không thể được thực thi. Compiler có thể loại bỏ khối mã không thể tới được, đồng thời phát cảnh báo nếu phù hợp.

### 8.2. Nhánh điều kiện luôn đúng hoặc luôn sai

~~~text
if true:
    approve(order)
else:
    reject(order)
~~~

Nếu true là hằng và điều kiện không có tác dụng phụ, compiler có thể giữ nhánh approve và loại nhánh reject.

### 8.3. Không được xóa tác dụng phụ

~~~text
sendNotification(customer)
let unused = 5
return success
~~~

Biến unused có thể bị xóa, nhưng sendNotification không thể bị xóa chỉ vì không dùng giá trị trả về.

### 8.4. Dead store elimination

Một giá trị được ghi vào biến rồi bị ghi đè trước khi đọc có thể là dead store:

~~~text
status = "NEW"
status = "PAID"
return status
~~~

Nếu phép gán đầu tiên không có tác dụng phụ và không bị quan sát bởi closure, callback hoặc cơ chế khác, có thể loại bỏ phép gán status = "NEW".

## 9. Common subexpression elimination

Common subexpression elimination (CSE) phát hiện cùng một biểu thức được tính nhiều lần và dùng lại kết quả khi điều đó an toàn.

Trước:

~~~text
let a = order.quantity * order.unitPrice
let b = order.quantity * order.unitPrice + 10000
~~~

Sau:

~~~text
let product = order.quantity * order.unitPrice
let a = product
let b = product + 10000
~~~

Compiler tránh tính lại phép nhân.

### 9.1. Điều kiện an toàn

Hai biểu thức giống nhau về cú pháp chưa chắc có cùng kết quả nếu chúng đọc trạng thái thay đổi hoặc gọi hàm có tác dụng phụ.

Ví dụ:

~~~text
let a = currentTime()
let b = currentTime()
~~~

Hai lời gọi có thể trả về thời điểm khác nhau. Không được gộp chúng nếu hàm không được xác định là thuần túy hoặc có kết quả ổn định.

### 9.2. CSE cục bộ và toàn cục

- **CSE cục bộ:** tìm biểu thức lặp trong cùng một basic block.
- **CSE toàn cục:** tìm biểu thức có thể dùng chung giữa nhiều block trong CFG.

CSE toàn cục cần phân tích luồng dữ liệu và kiểm tra xem biến đầu vào có bị thay đổi giữa hai vị trí không.

### 9.3. Chi phí lưu kết quả

Giữ một kết quả trung gian cũng có chi phí: cần thanh ghi hoặc bộ nhớ, có thể làm tăng áp lực thanh ghi. Nếu biểu thức rẻ nhưng giá trị trung gian sống quá lâu, tính lại đôi khi nhanh hơn lưu và tải.

## 10. Copy propagation và đơn giản hóa đại số

### 10.1. Copy propagation

Nếu một biến chỉ sao chép giá trị từ biến khác, compiler có thể thay nơi sử dụng bằng biến gốc:

~~~text
let a = order.total
let b = a
return b
~~~

Có thể rút gọn:

~~~text
return order.total
~~~

Chỉ thực hiện nếu không có thay đổi giá trị, alias hoặc tác dụng phụ làm mất tính tương đương.

### 10.2. Đại số cơ bản

Một số phép biến đổi thường gặp:

| Biểu thức | Dạng rút gọn có thể có |
|---|---|
| x + 0 | x |
| x * 1 | x |
| x - 0 | x |
| x * 0 | 0 |
| x / 1 | x |
| true and x | x |
| false or x | x |

Các quy tắc này chỉ đúng khi phù hợp với kiểu và ngữ nghĩa của DSL.

### 10.3. Cẩn thận với tác dụng phụ

~~~text
calculateAndLog() * 0
~~~

Không thể thay toàn bộ biểu thức thành 0 nếu calculateAndLog có tác dụng phụ hoặc có thể phát lỗi. Compiler có thể loại bỏ kết quả phép nhân nhưng vẫn phải giữ lời gọi hàm theo đúng thứ tự.

### 10.4. Cẩn thận với số học dấu phẩy động

x * 0 không phải lúc nào cũng có thể thay bằng số 0 theo đúng ngữ nghĩa dấu phẩy động, do NaN, vô cực và dấu của zero. Compiler phải theo chính sách số học của DSL và mức tối ưu hóa được chọn.

## 11. Tối ưu hóa luồng điều khiển

Luồng điều khiển xác định thứ tự thực hiện các khối lệnh. Tối ưu hóa ở tầng này có thể giảm nhánh, loại bỏ block không cần thiết hoặc hợp nhất các đường đi tương đương.

### 11.1. Constant branch elimination

~~~text
if environment == "production":
    enableCache()
else:
    disableCache()
~~~

Nếu environment là constant của bản build hiện tại, compiler có thể giữ nhánh tương ứng. Nếu artifact cần chạy ở nhiều môi trường, không thể cố định nhánh theo một giá trị cụ thể.

### 11.2. Branch simplification

~~~text
if condition:
    result = true
else:
    result = false
~~~

Có thể thay bằng:

~~~text
result = condition
~~~

Biến đổi này yêu cầu condition được đánh giá đúng một lần và giữ nguyên thứ tự đánh giá.

### 11.3. Hợp nhất block

Nếu một block chỉ chuyển tiếp đến block khác và không có hành động cần thiết, compiler có thể hợp nhất chúng để giảm cạnh CFG và đơn giản hóa phân tích.

### 11.4. Loại bỏ nhánh không thể tới

Nếu CFG chứng minh một block không thể được đi tới từ entry, block đó có thể bị loại bỏ. Cần cẩn thận với nhãn, breakpoint, metadata hoặc cấu trúc mà debugger cần giữ.

## 12. Tối ưu hóa vòng lặp

Vòng lặp có thể thực hiện cùng một công việc nhiều lần, nên thường là nơi có tiềm năng tối ưu lớn.

### 12.1. Loop invariant code motion

Loop invariant là biểu thức có kết quả không đổi giữa các lần lặp. Nếu biểu thức không phụ thuộc biến thay đổi trong vòng lặp và không có tác dụng phụ, có thể đưa nó ra ngoài.

Trước:

~~~text
for item in items:
    threshold = baseLimit * multiplier
    if item.price > threshold:
        flag(item)
~~~

Sau:

~~~text
threshold = baseLimit * multiplier
for item in items:
    if item.price > threshold:
        flag(item)
~~~

Compiler cần chứng minh baseLimit và multiplier không thay đổi trong vòng lặp và phép nhân không có tác dụng phụ hoặc hành vi lỗi bị thay đổi.

### 12.2. Induction variable simplification

Biến quy nạp là biến thay đổi theo quy luật cố định qua mỗi lần lặp, ví dụ i tăng một đơn vị. Compiler có thể thay phép tính lặp lại bằng cập nhật đơn giản hơn.

~~~text
for i from 0 to n:
    index = i * 4
    use(index)
~~~

Backend có thể duy trì index bằng cách cộng thêm 4 sau mỗi vòng thay vì nhân i với 4 ở mỗi vòng. Phép biến đổi phải giữ đúng giới hạn và hành vi tràn số.

### 12.3. Loop unrolling

Loop unrolling mở rộng thân vòng lặp để giảm chi phí kiểm tra điều kiện và nhảy:

~~~text
for i from 0 to 3:
    process(items[i])
~~~

Có thể chuyển thành các lệnh process riêng cho từng phần tử nếu compiler biết chính xác số lần lặp và việc mở rộng không làm thay đổi tác dụng phụ.

Unrolling có thể tăng kích thước mã và áp lực cache lệnh. Với vòng lặp lớn hoặc số lần lặp không xác định, unrolling quá mức có thể làm chậm chương trình.

### 12.4. Vectorization

Vectorization thực hiện cùng một phép toán trên nhiều phần tử bằng lệnh SIMD hoặc primitive collection. Ví dụ, tính tổng các giá trị số có thể xử lý nhiều phần tử trong một lần.

Không phải mọi vòng lặp đều vector hóa được. Nếu mỗi vòng phụ thuộc kết quả vòng trước hoặc có nhánh phức tạp, compiler có thể không áp dụng được. Với số học dấu phẩy động, vectorization có thể thay đổi thứ tự tính toán nên phải phù hợp chính sách độ chính xác.

### 12.5. Loop fusion và loop fission

- **Loop fusion:** gộp hai vòng lặp cùng duyệt dữ liệu để giảm chi phí lặp và cải thiện locality.
- **Loop fission:** tách một vòng lặp thành nhiều vòng khi việc tách giúp vector hóa, song song hóa hoặc cải thiện truy cập bộ nhớ.

Hai phép biến đổi đều cần phân tích phụ thuộc dữ liệu và thứ tự tác dụng phụ.

## 13. Function inlining và tối ưu lời gọi

Inlining thay lời gọi hàm bằng phần thân hàm tại vị trí gọi.

Trước:

~~~text
function addTax(amount):
    return amount * 1.1

total = addTax(subtotal)
~~~

Sau inlining:

~~~text
total = subtotal * 1.1
~~~

Inlining có thể loại bỏ chi phí gọi hàm và mở ra cơ hội constant folding hoặc CSE. Nhưng nó cũng có thể:

- Làm mã lớn hơn.
- Tăng thời gian biên dịch.
- Làm tăng áp lực thanh ghi.
- Làm giảm hiệu quả instruction cache.
- Làm stack trace và debug khó theo dõi hơn nếu metadata không được giữ.

### 13.1. Khi nào nên inline?

Các hàm nhỏ, được gọi thường xuyên hoặc có đối số hằng có thể là ứng viên tốt. Hàm lớn hoặc chỉ được gọi một lần có thể không đáng inline.

### 13.2. Hàm đệ quy

Inlining hàm đệ quy cần giới hạn để tránh mở rộng vô hạn. Compiler có thể inline một số mức đầu, hoặc không inline nếu lợi ích không rõ.

### 13.3. Hàm có tác dụng phụ

Inlining không được phép thay đổi số lần gọi, thứ tự thực hiện hoặc hành vi lỗi của hàm. Việc thay thân hàm vào chỗ gọi không tự động làm các phép biến đổi bên trong an toàn.

## 14. Tối ưu hóa bộ nhớ và dữ liệu

Trong DSL thao tác với collection, object hoặc dữ liệu nghiệp vụ, chi phí bộ nhớ có thể lớn hơn chi phí phép toán.

### 14.1. Loại bỏ cấp phát tạm

~~~text
result = filter(items, predicate).map(transform)
~~~

Một cách thực thi đơn giản có thể tạo collection trung gian sau filter rồi tạo collection thứ hai sau map. Compiler hoặc runtime có thể kết hợp hai bước thành một vòng duyệt để tránh collection tạm nếu semantics cho phép.

### 14.2. Escape analysis

Escape analysis xác định object có thoát khỏi phạm vi tạo ra nó hay không. Nếu object chỉ được dùng bên trong một hàm và không được lưu ra ngoài, runtime có thể tối ưu cấp phát hoặc thời gian sống của nó.

Một số runtime có thể loại bỏ allocation hoặc đặt dữ liệu ở vùng nhớ phù hợp hơn. Kỹ thuật cụ thể phụ thuộc ngôn ngữ chủ và runtime.

### 14.3. Object layout và locality

Truy cập các trường được bố trí gần nhau trong bộ nhớ có thể cải thiện cache locality. Với DSL xử lý dữ liệu lớn, lựa chọn cấu trúc hàng, cột, map hoặc array có thể ảnh hưởng đáng kể đến tốc độ.

### 14.4. Copy elimination

Nếu một giá trị lớn được sao chép nhưng không cần bản sao độc lập, runtime có thể dùng tham chiếu hoặc move semantics khi mô hình sở hữu dữ liệu cho phép. Không được loại bỏ bản sao nếu người dùng có thể quan sát việc thay đổi một bản làm thay đổi bản kia.

### 14.5. Caching

Caching giữ kết quả tính toán hoặc tra cứu để dùng lại. Cần xác định:

- Key của cache.
- Thời hạn và chính sách loại bỏ.
- Dữ liệu nào làm kết quả mất hiệu lực.
- Có an toàn khi chạy đồng thời không.
- Bộ nhớ tối đa dành cho cache.

Cache thiếu invalidation đúng có thể trả về dữ liệu cũ và làm sai ngữ nghĩa, dù tốc độ nhanh hơn.

## 15. Tối ưu hóa riêng cho DSL

Một lợi thế của DSL là compiler biết ý nghĩa miền của câu lệnh. Nhờ vậy, nó có thể tối ưu hóa ở mức cao hơn các phép toán máy thông thường.

### 15.1. Query optimization

Với DSL truy vấn, compiler có thể:

- Đẩy filter gần nguồn dữ liệu hơn (predicate pushdown).
- Chỉ chọn các cột cần thiết (projection pruning).
- Đổi thứ tự join dựa trên ước lượng kích thước.
- Dùng index hoặc partition pruning.
- Gộp các bước biến đổi tương thích.

Ví dụ:

~~~text
from orders
where status == "PAID"
select customerId, total
~~~

Nếu backend hỗ trợ lọc tại nguồn, compiler có thể gửi điều kiện xuống database thay vì tải toàn bộ bảng rồi mới lọc trong interpreter.

### 15.2. Rule engine optimization

Với DSL quy tắc, compiler có thể:

- Nhóm các điều kiện dùng chung.
- Sắp xếp điều kiện thuần túy theo chi phí và khả năng loại sớm, nếu thứ tự không quan sát được.
- Tạo chỉ mục theo thuộc tính thường được so sánh.
- Chia nhóm rule theo loại sự kiện hoặc trường dữ liệu.
- Tránh đánh giá lại điều kiện bất biến.

Không được đổi thứ tự điều kiện nếu chúng có tác dụng phụ, phát lỗi khác nhau hoặc DSL quy định đánh giá tuần tự.

### 15.3. Workflow optimization

Với DSL quy trình, compiler có thể loại bỏ bước không thể tới, gộp các bước thuần túy hoặc tính trước biểu thức cấu hình. Tuy nhiên, không thể bỏ một bước gửi email, ghi audit hoặc gọi dịch vụ chỉ vì nó không tạo giá trị trả về.

### 15.4. Tối ưu hóa theo schema

Nếu schema cho biết trường có kiểu cố định và chỉ mục sẵn có, compiler có thể chọn đường truy cập hiệu quả. Nếu schema thay đổi theo phiên bản, artifact tối ưu hóa cần gắn với phiên bản hoặc có cơ chế kiểm tra tương thích.

## 16. Tối ưu hóa trong interpreter

Interpreter thường thực thi AST hoặc bytecode trực tiếp. Dù không tạo mã máy trước, interpreter vẫn có nhiều cơ hội tối ưu.

### 16.1. Biên dịch AST sang bytecode

Thay vì duyệt AST và dispatch theo loại nút mỗi lần, interpreter có thể biên dịch AST sang bytecode gọn hơn:

~~~text
LOAD order.quantity
LOAD order.unitPrice
MULTIPLY
STORE subtotal
~~~

Bytecode giảm chi phí đi qua cấu trúc AST và có thể được tối ưu trước khi thực thi.

### 16.2. Dispatch hiệu quả

Interpreter có thể giảm chi phí chọn handler cho từng opcode bằng cách tổ chức dispatch phù hợp, gom các thao tác hoặc dùng cơ chế thực thi tối ưu của ngôn ngữ chủ.

### 16.3. Inline cache

Nếu một biểu thức thường truy cập cùng một kiểu object hoặc cùng một trường, runtime có thể cache thông tin tra cứu. Ví dụ, order.total thường truy cập thuộc tính total trên object kiểu Order. Inline cache có thể ghi nhớ vị trí trường hoặc đường truy cập.

Nếu kiểu object thay đổi, cache cần kiểm tra guard và cập nhật hoặc quay về đường thực thi tổng quát.

### 16.4. Specialization

Runtime có thể tạo phiên bản chuyên biệt của phép toán dựa trên kiểu thường gặp:

- Đường nhanh cho Integer + Integer.
- Đường nhanh cho Money + Money.
- Đường tổng quát khi kiểu không biết trước.

Specialization phải có guard để xác nhận giả định còn đúng. Nếu không, chương trình có thể chạy sai khi dữ liệu có kiểu khác.

## 17. JIT compilation và tối ưu hóa dựa trên profile

Just-in-time compilation (JIT) biên dịch một phần chương trình thành mã máy trong lúc chạy. JIT thường phù hợp khi một số đoạn được thực thi lặp lại nhiều lần.

### 17.1. Interpreter và JIT

Một runtime có thể:

1. Bắt đầu thực thi bằng interpreter.
2. Thu thập số lần gọi hàm hoặc số lần chạy vòng lặp.
3. Xác định vùng nóng (hot spot).
4. Biên dịch vùng nóng thành mã máy.
5. Thực thi mã máy khi các giả định còn đúng.
6. Quay lại interpreter hoặc deoptimize nếu giả định bị vi phạm.

### 17.2. Profile-guided optimization

Profile-guided optimization (PGO) dùng dữ liệu chạy thực tế để định hướng tối ưu. Profile có thể cho biết:

- Hàm nào được gọi thường xuyên.
- Nhánh nào thường được chọn.
- Kiểu nào xuất hiện tại một vị trí.
- Vòng lặp nào chạy nhiều vòng.
- Truy cập dữ liệu nào chiếm nhiều thời gian.

Compiler có thể dùng thông tin đó để ưu tiên inlining, specialization hoặc bố trí nhánh.

### 17.3. Guard và deoptimization

Giả sử JIT tối ưu biểu thức dựa trên giả định order luôn có kiểu Order. Mã máy chuyên biệt có thể kiểm tra guard trước khi truy cập trường. Nếu guard thất bại, runtime quay về đường tổng quát hoặc hủy phiên bản chuyên biệt.

Deoptimization giúp giữ tính đúng đắn khi giả định runtime không còn đúng. Cơ chế này cần ánh xạ trạng thái mã máy về trạng thái interpreter để tiếp tục thực thi.

### 17.4. Chi phí JIT

JIT có chi phí khởi động, bộ nhớ cho mã máy và thời gian biên dịch. Với chương trình chạy một lần hoặc rất ngắn, chi phí này có thể lớn hơn lợi ích. Không phải DSL nào cũng cần JIT; bytecode interpreter hoặc compiler ahead-of-time có thể phù hợp hơn.

## 18. Các mức tối ưu hóa

Compiler thường cung cấp các mức tối ưu hóa để cân bằng tốc độ biên dịch, tốc độ thực thi và khả năng debug.

| Mức | Mục tiêu thường gặp | Đặc điểm |
|---|---|---|
| O0 | Dễ debug, biên dịch nhanh | Ít hoặc không tối ưu |
| O1 | Tối ưu cơ bản | Constant folding, propagation, DCE đơn giản |
| O2 | Tối ưu mạnh hơn | CSE, tối ưu CFG, vòng lặp và inlining có chọn lọc |
| O3 | Ưu tiên hiệu năng | Có thể thêm vectorization, unrolling và inlining mạnh |
| Os | Giảm kích thước | Ưu tiên mã nhỏ |
| Oz | Giảm kích thước tối đa theo compiler | Có thể hy sinh tốc độ để giảm dung lượng |

Tên và nội dung các mức không phải chuẩn thống nhất giữa mọi compiler. Một DSL có thể đặt tên profile khác hoặc chỉ cung cấp vài lựa chọn.

### 18.1. Mức debug

Ở chế độ debug, công cụ có thể giữ biến, vị trí nguồn và ranh giới câu lệnh để breakpoint và stepping hoạt động dễ dự đoán.

### 18.2. Mức production

Ở chế độ production, compiler có thể tối ưu mạnh hơn, nhưng cần giữ source map và metadata đủ để log hoặc stack trace vẫn hữu ích.

### 18.3. Tối ưu theo kích thước

Với DSL được nhúng vào thiết bị hoặc gửi qua mạng, kích thước bytecode và thời gian tải có thể quan trọng hơn tốc độ tối đa. Khi đó, loại bỏ mã lặp và tránh inlining quá mức có thể là lựa chọn tốt.

## 19. Thứ tự và tương tác giữa các optimization pass

Các pass có thể tạo cơ hội cho nhau. Ví dụ:

1. Constant propagation thay biến bằng hằng.
2. Constant folding tính biểu thức mới thành literal.
3. Branch simplification loại nhánh không thể tới.
4. Dead code elimination xóa các lệnh chỉ còn ở nhánh bị loại.

~~~text
Trước:
limit = 10
if limit > 5:
    result = 2 * 3
else:
    result = 99
return result

Sau một số pass:
return 6
~~~

### 19.1. Pass manager

Pass manager quản lý thứ tự chạy, điều kiện chạy và thông tin phân tích được tái sử dụng. Một pass có thể khai báo nó làm thay đổi CFG hoặc dữ liệu, để các phân tích phụ thuộc được tính lại khi cần.

### 19.2. Chạy lặp đến điểm cố định

Một số pass được chạy nhiều lần cho đến khi không còn biến đổi mới hoặc đạt giới hạn số vòng. Đây là cách tìm trạng thái ổn định (fixed point).

Không nên lặp vô hạn. Compiler cần giới hạn vòng lặp, phát hiện pass dao động và ghi lại lý do dừng.

### 19.3. Tránh pass xung đột

Một pass có thể làm mất cấu trúc mà pass khác cần. Ví dụ, inlining có thể giúp constant propagation nhưng làm mã lớn hơn và gây khó cho một số phân tích. Pass manager cần sắp xếp và giới hạn phạm vi để cân bằng lợi ích.

## 20. Chi phí và đánh đổi của tối ưu hóa

Không có phép tối ưu nào luôn có lợi. Cần đánh giá theo workload thực tế.

| Kỹ thuật | Lợi ích có thể có | Chi phí hoặc rủi ro |
|---|---|---|
| Constant folding | Giảm phép tính runtime | Tốn thời gian biên dịch; phải đúng quy tắc số học |
| CSE | Tránh tính lại | Tăng thời gian sống của giá trị và áp lực thanh ghi |
| DCE | Giảm lệnh và mã | Cần phân tích tác dụng phụ chính xác |
| Inlining | Giảm chi phí gọi | Tăng kích thước mã |
| Loop unrolling | Giảm chi phí nhánh | Mã lớn, instruction cache kém |
| Vectorization | Tăng thông lượng phép toán | Yêu cầu phụ thuộc dữ liệu và ngữ nghĩa số học phù hợp |
| Caching | Giảm tính toán hoặc tra cứu | Bộ nhớ, invalidation và tính nhất quán |
| JIT | Tăng tốc vùng nóng | Chi phí khởi động, biên dịch và quản lý mã |

### 20.1. Amdahl's Law

Nếu chỉ tối ưu một phần nhỏ của chương trình, mức tăng tốc tổng thể sẽ bị giới hạn bởi phần còn lại. Ví dụ, nếu 80% thời gian chạy nằm ở truy vấn dữ liệu và chỉ 20% nằm ở biểu thức DSL, tăng tốc biểu thức lên gấp đôi không làm toàn bộ hệ thống nhanh gấp đôi.

Do đó, cần đo để tìm nút thắt cổ chai (bottleneck) trước khi chọn kỹ thuật.

### 20.2. Thời gian biên dịch và thời gian chạy

Một compiler có thể dành thêm thời gian tối ưu để giảm thời gian chạy. Điều đó phù hợp với chương trình được chạy hàng nghìn lần, nhưng có thể không phù hợp với một rule chỉ được thực thi một lần.

### 20.3. Bộ nhớ và cache

Tối ưu hóa bằng cache hoặc inlining có thể giảm thời gian xử lý nhưng tăng bộ nhớ. Với thiết bị giới hạn tài nguyên, mục tiêu tối ưu phải phản ánh cả RAM, flash và năng lượng.

## 21. Debugging và khả năng quan sát sau tối ưu hóa

Tối ưu hóa có thể làm cấu trúc mã thực thi khác đáng kể so với nguồn DSL. Một biểu thức có thể bị gộp, biến bị loại bỏ hoặc hàm bị inline.

Để hỗ trợ debugging, compiler nên giữ metadata:

- Source span của biểu thức và câu lệnh.
- Ánh xạ từ IR hoặc bytecode về vị trí nguồn.
- Thông tin tên biến và phạm vi.
- Ranh giới hàm và thông tin inline.
- ID của optimization pass hoặc lý do biến đổi nếu cần phân tích.

### 21.1. Source map

Source map ánh xạ lệnh IR/bytecode hoặc vị trí mã máy về dòng và cột trong nguồn DSL. Khi runtime phát lỗi, công cụ có thể hiển thị vị trí người viết nhận ra thay vì chỉ vị trí trong mã sinh ra.

### 21.2. Tối ưu hóa và breakpoint

Nếu một câu lệnh bị loại bỏ hoặc gộp với câu lệnh khác, breakpoint có thể không còn ánh xạ một-một. Debugger cần quy tắc rõ ràng: breakpoint đặt tại câu lệnh nguồn có thể dừng ở lệnh tương ứng gần nhất hoặc được báo là không thể đặt chính xác.

### 21.3. Chẩn đoán tối ưu hóa

Một chế độ explain hoặc optimization report có thể cho biết:

- Pass nào đã thay đổi IR.
- Biểu thức nào được gấp hằng.
- Hàm nào được inline.
- Vòng lặp nào được vector hóa.
- Tại sao một tối ưu hóa không được áp dụng.

Thông tin này hữu ích cho nhà phát triển DSL, nhưng không nhất thiết phải hiển thị cho người dùng nghiệp vụ thông thường.

## 22. Kiểm thử tính đúng đắn của tối ưu hóa

Một chương trình tối ưu phải giữ kết quả và các hành vi quan sát được theo ngữ nghĩa của DSL.

### 22.1. Kiểm thử trước và sau biến đổi

Chạy cùng đầu vào qua chương trình chưa tối ưu và đã tối ưu, so sánh kết quả và các tác dụng phụ được phép quan sát.

Ví dụ:

~~~text
source program -> interpreter without optimization -> result A
source program -> optimized IR -> interpreter or backend -> result B
~~~

Kết quả cần tương đương theo định nghĩa của DSL.

### 22.2. Differential testing

Nếu DSL có interpreter tham chiếu và backend tối ưu, chạy cùng chương trình trên cả hai để so sánh. Khác biệt có thể chỉ ra lỗi trong pass, runtime hoặc đặc tả ngữ nghĩa.

### 22.3. Property-based testing

Sinh nhiều biểu thức ngẫu nhiên theo grammar và kiểm tra rằng kết quả trước/sau tối ưu tương đương. Cần giới hạn kích thước, tránh chỉ tạo biểu thức hằng và bao phủ cả kiểu, nhánh, lỗi và tác dụng phụ.

### 22.4. Kiểm thử tác dụng phụ

Không chỉ so sánh giá trị cuối. Hãy ghi lại thứ tự lời gọi, số lần ghi dữ liệu, log hoặc sự kiện. Nếu tối ưu hóa làm mất hoặc đổi thứ tự tác dụng phụ, đó là lỗi dù kết quả cuối tình cờ giống nhau.

### 22.5. Kiểm thử số học

Bao gồm:

- Giá trị âm và dương.
- Giá trị lớn gần giới hạn kiểu.
- Tràn số theo quy tắc DSL.
- Chia cho không.
- NaN và vô cực nếu có floating point.
- Làm tròn và độ chính xác.
- Giá trị tiền tệ và đơn vị đo.

### 22.6. Benchmark

Benchmark đo hiệu năng trên workload đại diện. Cần:

- Dùng dữ liệu có kích thước và phân bố gần thực tế.
- Chạy nhiều lần và tính thống kê phù hợp.
- Tách thời gian parse, compile, warm-up và execute.
- Tránh benchmark bị ảnh hưởng bởi cache hoặc tác vụ nền không kiểm soát.
- Đo cả thời gian, bộ nhớ và kích thước mã khi cần.

Một tối ưu hóa chỉ nên được giữ nếu lợi ích đo được đủ lớn và không làm tăng rủi ro bảo trì quá mức.

## 23. Quy trình áp dụng tối ưu hóa

Một quy trình thực tế có thể gồm:

1. Xác định mục tiêu: thời gian chạy, độ trễ, bộ nhớ, kích thước hay thông lượng.
2. Đo baseline trên workload đại diện.
3. Xác định bottleneck bằng profiler hoặc thống kê runtime.
4. Chọn một phép tối ưu phù hợp với nguyên nhân đã xác định.
5. Viết hoặc bật pass với phạm vi nhỏ.
6. Kiểm tra điều kiện bảo toàn ngữ nghĩa.
7. Chạy kiểm thử tương đương và kiểm thử hồi quy.
8. Đo lại hiệu năng và chi phí bộ nhớ.
9. So sánh kết quả với baseline.
10. Ghi lại giả định, lợi ích, giới hạn và điều kiện vô hiệu hóa tối ưu.

Không nên áp dụng nhiều biến đổi cùng lúc mà không biết biến đổi nào tạo ra lợi ích hoặc gây lỗi. Thực hiện từng thay đổi có thể đo lường giúp việc điều tra dễ hơn.

## 24. Ví dụ tổng hợp: tối ưu một quy tắc DSL

Xét chương trình:

~~~text
rule "bulk_discount" {
    let minimumQuantity = 10
    let unitDiscount = 5

    if true:
        let subtotal = order.quantity * order.unitPrice
        let repeated = order.quantity * order.unitPrice
        let discount = repeated * unitDiscount / 100
        let unused = minimumQuantity * 2
        if order.quantity >= minimumQuantity:
            return subtotal - discount
        else:
            return subtotal
}
~~~

Giả sử:

- minimumQuantity và unitDiscount là hằng trong rule.
- Các phép toán trên kiểu dữ liệu này thuần túy và không gây tác dụng phụ.
- order.quantity và order.unitPrice không thay đổi trong quá trình đánh giá rule.
- Điều kiện true không có tác dụng phụ.
- Ngữ nghĩa số học cho phép các phép biến đổi được áp dụng.

Compiler có thể lần lượt:

### 24.1. Constant folding

Tính trước unused:

~~~text
unused = 10 * 2
~~~

thành:

~~~text
unused = 20
~~~

### 24.2. Dead code elimination

Vì unused không được dùng và phép tính thuần túy, loại bỏ khai báo đó.

### 24.3. Constant propagation

Thay minimumQuantity bằng 10 và unitDiscount bằng 5 tại nơi sử dụng.

### 24.4. Common subexpression elimination

Gộp hai biểu thức order.quantity * order.unitPrice thành một kết quả dùng chung.

### 24.5. Constant branch elimination

Vì điều kiện if true luôn đúng và không có tác dụng phụ, loại bỏ nhánh else.

Một dạng rút gọn minh họa:

~~~text
rule "bulk_discount" {
    let subtotal = order.quantity * order.unitPrice
    let discount = subtotal * 5 / 100
    if order.quantity >= 10:
        return subtotal - discount
    else:
        return subtotal
}
~~~

Ví dụ này chỉ minh họa các bước biến đổi. Compiler thực tế phải xem xét kiểu Money, phần trăm, làm tròn, tràn số và quy tắc nghiệp vụ trước khi gộp biểu thức hoặc tính trước giá trị.

## 25. Những lỗi thiết kế thường gặp

### 25.1. Tối ưu trước khi đo

Tối ưu một đoạn mã không phải bottleneck có thể làm compiler phức tạp mà không cải thiện hệ thống. Hãy đo trước và xác định phần chiếm thời gian.

### 25.2. Cho rằng biểu thức giống nhau luôn có thể gộp

Hai lời gọi cùng tên có thể đọc thời gian, trạng thái hoặc dữ liệu bên ngoài. Cần biết tính thuần túy và tác dụng phụ trước khi dùng CSE.

### 25.3. Loại bỏ lệnh chỉ vì kết quả không được dùng

Lệnh có thể ghi dữ liệu, gửi thông báo hoặc phát lỗi. DCE phải dựa trên tác dụng quan sát được, không chỉ dựa trên việc biến kết quả có được tham chiếu hay không.

### 25.4. Đổi thứ tự phép toán số thực

Tái kết hợp phép cộng hoặc nhân có thể làm thay đổi kết quả dấu phẩy động. Cần tuân thủ chế độ độ chính xác của DSL.

### 25.5. Inline quá nhiều

Inlining không giới hạn làm mã lớn, tăng thời gian biên dịch và có thể giảm hiệu năng cache. Cần có ngưỡng và dữ liệu profile.

### 25.6. Tối ưu dựa trên giả định không được bảo vệ

Nếu JIT giả định một thuộc tính luôn có kiểu cụ thể, cần guard hoặc cơ chế deoptimization khi giả định sai.

### 25.7. Bỏ metadata debug

Mã tối ưu nhưng không thể truy ngược lỗi về nguồn DSL sẽ khó vận hành. Cần giữ source map và thông tin chẩn đoán phù hợp.

### 25.8. Benchmark không đại diện

Một microbenchmark có thể làm một pass trông rất nhanh nhưng không phản ánh workload thực. Cần đo trên dữ liệu và đường chạy đại diện.

## 26. Bài tập tự kiểm tra

### Bài 1: Constant folding

Cho biểu thức:

~~~text
limit = (20 + 5) * 4 - 10
~~~

Hãy thực hiện constant folding và xác định kết quả nếu tất cả toán hạng là Integer và không có tràn số.

### Bài 2: Constant propagation

~~~text
let rate = 5
let discount = order.total * rate / 100
~~~

Hãy viết dạng IR sau khi truyền hằng rate. Nêu điều kiện để phép biến đổi hợp lệ.

### Bài 3: Dead code elimination

~~~text
let temporary = calculate()
return order.total
~~~

Khi nào có thể xóa temporary và lời gọi calculate? Khi nào chỉ có thể xóa phép gán mà vẫn phải giữ lời gọi?

### Bài 4: Common subexpression elimination

~~~text
a = order.quantity * order.price
b = order.quantity * order.price + fee
~~~

Hãy viết dạng dùng chung kết quả. Nêu điều kiện để CSE an toàn nếu order có thể bị thay đổi.

### Bài 5: Tối ưu vòng lặp

Một biểu thức phụ thuộc vào biến cấu hình không đổi trong suốt vòng lặp. Hãy mô tả cách đưa biểu thức ra ngoài vòng lặp và điều kiện cần chứng minh.

### Bài 6: Inlining

Một hàm có ba phép toán đơn giản nhưng được gọi hàng nghìn lần. Hãy nêu lợi ích và chi phí có thể có khi inline. Vì sao cần xem xét kích thước mã?

### Bài 7: Tác dụng phụ

Hai điều kiện trong rule lần lượt gọi logDecision() và checkLimit(). Hãy giải thích vì sao không thể tự ý đổi thứ tự đánh giá nếu DSL cho phép hàm có tác dụng phụ.

### Bài 8: Số học dấu phẩy động

Hãy giải thích vì sao (a + b) + c có thể khác a + (b + c) với floating point. Một DSL nên công bố điều gì để compiler biết có thể tái kết hợp phép toán hay không?

### Bài 9: Interpreter và JIT

Hãy mô tả cách runtime xác định một hàm là hot spot, biên dịch nó bằng JIT và dùng guard để bảo đảm giả định kiểu vẫn đúng.

### Bài 10: Đánh giá một tối ưu hóa

Một pass làm thời gian chạy giảm 8% nhưng thời gian biên dịch tăng 40% và kích thước mã tăng 25%. Hãy nêu các thông tin cần biết trước khi quyết định bật pass mặc định.

## Kết luận

Tối ưu hóa trong biên dịch và thông dịch DSL là quá trình biến đổi AST, IR, bytecode hoặc cách thực thi để cải thiện tốc độ, độ trễ, bộ nhớ và các chi phí khác. Những kỹ thuật phổ biến gồm constant folding, constant propagation, dead code elimination, common subexpression elimination, đơn giản hóa luồng điều khiển, tối ưu vòng lặp, inlining, tối ưu bộ nhớ và specialization lúc chạy. Mọi biến đổi phải bảo toàn ngữ nghĩa, bao gồm kết quả, tác dụng phụ, thứ tự đánh giá và hành vi lỗi. Compiler nên tối ưu dựa trên phân tích và số liệu đo, giữ metadata phục vụ debug, đồng thời kiểm thử tương đương trước và sau biến đổi. Một chiến lược tốt cân bằng lợi ích runtime với chi phí biên dịch, bộ nhớ, kích thước mã và khả năng bảo trì.
