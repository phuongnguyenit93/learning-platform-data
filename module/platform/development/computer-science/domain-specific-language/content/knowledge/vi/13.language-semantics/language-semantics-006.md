# Tác dụng phụ

Trong ngữ nghĩa của một DSL (*Domain-Specific Language* – ngôn ngữ chuyên biệt theo miền), **tác dụng phụ** (*side effect*) là ảnh hưởng mà một biểu thức hoặc thao tác tạo ra ngoài giá trị mà nó trả về. Ảnh hưởng đó có thể làm thay đổi trạng thái, ghi dữ liệu, gửi yêu cầu ra bên ngoài, phát sinh sự kiện hoặc tác động đến môi trường thực thi.

Ví dụ, biểu thức `price * quantity` thường chỉ tính và trả về một giá trị. Ngược lại, thao tác `saveOrder(order)` có thể ghi đơn hàng vào cơ sở dữ liệu. Hai thao tác có vai trò khác nhau: một thao tác tính toán kết quả, thao tác kia còn làm thay đổi trạng thái mà những phần khác của hệ thống có thể quan sát được.

Tác dụng phụ là một phần của **ngữ nghĩa thực thi** (*execution semantics*). DSL cần xác định thao tác nào có thể tạo tác dụng phụ, tác dụng đó xảy ra khi nào, theo thứ tự nào, có thể lặp lại hay không và lỗi được xử lý ra sao. Những quy tắc này ảnh hưởng đến cách người dùng hiểu chương trình, cách engine thực thi và những phép tối ưu mà compiler được phép áp dụng.

## 1. Giá trị trả về và tác dụng phụ

Một biểu thức có thể được xem xét qua hai khía cạnh:

- **Giá trị kết quả:** dữ liệu mà biểu thức tạo ra và trả về.
- **Tác động quan sát được:** thay đổi hoặc sự kiện bên ngoài mà biểu thức gây ra trong quá trình tính toán.

Ví dụ:

```text
total = price * quantity
```

Nếu `price` và `quantity` chỉ được đọc, phép nhân trả về một giá trị và không thay đổi trạng thái. Đây thường là biểu thức thuần (*pure expression*).

Ngược lại:

```text
account.balance = account.balance - amount
```

thay đổi trạng thái của tài khoản. Giá trị biểu thức gán có thể là giá trị mới, giá trị cũ hoặc không có giá trị tùy DSL, nhưng tác động thay đổi số dư là điều cần được tính đến.

Một lời gọi hàm cũng có thể vừa trả về giá trị vừa tạo tác dụng phụ:

```text
result = chargeCard(order.total)
```

Hàm có thể trả về kết quả thanh toán, đồng thời gửi yêu cầu đến cổng thanh toán và tạo giao dịch bên ngoài. Chỉ nhìn kiểu trả về không đủ để biết đầy đủ hành vi của lời gọi.

### 1.1. Tác dụng phụ có thể quan sát được

Không phải mọi thao tác nội bộ đều được xem là tác dụng phụ theo cùng một cách. Việc cấp phát một đối tượng tạm trong bộ nhớ có thể không làm thay đổi trạng thái quan sát được của chương trình, trong khi ghi tệp hoặc cập nhật biến dùng chung thường có thể được quan sát từ nơi khác.

Một cách hiểu thực tế là: tác động được xem là tác dụng phụ nếu nó làm thay đổi điều mà một phần khác của chương trình, người dùng hoặc hệ thống bên ngoài có thể quan sát, ngoài giá trị kết quả của biểu thức.

Ví dụ về các tác động quan sát được:

- Ghi hoặc xóa một bản ghi trong cơ sở dữ liệu.
- Gửi email, thông báo hoặc yêu cầu HTTP.
- Ghi tệp hoặc thay đổi cấu hình.
- Thay đổi biến trạng thái dùng chung.
- Phát sự kiện lên message broker.
- Đọc đồng hồ hệ thống hoặc nguồn dữ liệu thay đổi theo thời gian.
- Ghi log hoặc phát metric nếu những thao tác đó là một phần hành vi cần quan sát.

Định nghĩa chính xác phụ thuộc vào mô hình của DSL. Chẳng hạn, một DSL có thể coi đọc cơ sở dữ liệu là hiệu ứng vì kết quả phụ thuộc vào trạng thái bên ngoài, dù thao tác đọc không sửa dữ liệu.

## 2. Những loại tác dụng phụ thường gặp

Tác dụng phụ có nhiều dạng. Việc phân loại giúp người thiết kế DSL xác định quyền truy cập, thứ tự thực thi, cách kiểm thử và giới hạn tối ưu hóa.

### 2.1. Thay đổi trạng thái trong bộ nhớ

Thao tác thay đổi giá trị của biến, trường đối tượng hoặc cấu trúc dữ liệu dùng chung là một loại tác dụng phụ phổ biến.

```text
counter = counter + 1
items.append(newItem)
user.status = "active"
```

Nếu một biểu thức khác đọc `counter`, `items` hoặc `user.status` sau đó, kết quả có thể phụ thuộc vào việc thao tác thay đổi đã chạy hay chưa.

### 2.2. Đọc và ghi dữ liệu bên ngoài

Đọc tệp, truy vấn cơ sở dữ liệu hoặc gọi API khiến kết quả phụ thuộc vào môi trường bên ngoài. Ghi tệp, cập nhật database hoặc gửi yêu cầu thay đổi trạng thái bên ngoài.

```text
orders = database.query("SELECT * FROM orders")
database.insert("orders", newOrder)
file.write("report.csv", content)
```

Đọc dữ liệu có thể không sửa nguồn, nhưng vẫn là một hiệu ứng quan sát được trong mô hình ngữ nghĩa vì kết quả phụ thuộc vào dữ liệu hiện tại, quyền truy cập, kết nối và thời điểm đọc.

### 2.3. Giao tiếp mạng và hệ thống khác

Các thao tác gửi HTTP request, publish message, gọi dịch vụ thanh toán hoặc gửi email tạo tương tác với hệ thống khác.

```text
response = http.post(paymentEndpoint, paymentRequest)
messageBus.publish("order.created", event)
email.send(customer.email, receipt)
```

Các tác động này thường có độ trễ, có thể thất bại và có thể đã được hệ thống nhận xử lý ngay cả khi phía gọi không nhận được phản hồi. Vì vậy, retry và xử lý lỗi cần được thiết kế cẩn thận.

### 2.4. I/O và tài nguyên hệ thống

Mở hoặc đóng tệp, đọc bàn phím, ghi màn hình, sử dụng socket, tạo tiến trình hoặc truy cập thiết bị đều có thể tạo tác động bên ngoài.

Một số tài nguyên cần được giải phóng sau khi sử dụng. DSL có thể cung cấp cấu trúc như `with`, `using` hoặc khối `try/finally` để bảo đảm tệp, kết nối hoặc transaction được đóng đúng cách.

### 2.5. Ngoại lệ và lỗi

Phát sinh ngoại lệ làm thay đổi luồng điều khiển: chương trình có thể dừng biểu thức hiện tại, nhảy đến handler hoặc kết thúc tác vụ. Trong một số mô hình effect, khả năng thất bại cũng được xem là hiệu ứng cần khai báo.

```text
result = parseInteger(input)
```

Nếu đầu vào không hợp lệ, thao tác có thể phát sinh lỗi thay vì trả về số nguyên. DSL cần xác định lỗi được biểu diễn bằng exception, giá trị `Result`, nhánh `error` hay một cơ chế khác.

### 2.6. Tính không xác định và phụ thuộc môi trường

Một biểu thức đọc thời gian hiện tại, số ngẫu nhiên, trạng thái mạng hoặc dữ liệu bên ngoài có thể trả về kết quả khác nhau dù văn bản chương trình không đổi.

```text
now = clock.currentTime()
token = random.uuid()
weather = weatherService.current(city)
```

Những thao tác này không nhất thiết ghi thay đổi, nhưng làm kết quả phụ thuộc vào môi trường hoặc thời điểm. Một số mô hình phân loại chúng là hiệu ứng đọc, hiệu ứng không xác định hoặc hiệu ứng môi trường.

## 3. Hàm thuần và hàm có tác dụng phụ

Một **hàm thuần** (*pure function*) có hai đặc điểm quan trọng:

1. Với cùng đầu vào, hàm luôn tạo cùng kết quả trong cùng ngữ nghĩa tính toán.
2. Việc gọi hàm không tạo tác động quan sát được ngoài kết quả trả về.

Ví dụ:

```text
function calculateTax(amount, rate):
    return amount * rate
```

Nếu hàm chỉ tính toán từ hai tham số và không đọc hoặc ghi trạng thái bên ngoài, nó là hàm thuần.

Hàm có tác dụng phụ có thể đọc hoặc thay đổi trạng thái, thực hiện I/O, phát sự kiện hoặc thất bại theo cách ảnh hưởng đến môi trường:

```text
function saveInvoice(invoice):
    database.insert(invoice)
    log("Invoice saved")
```

### 3.1. Bảng so sánh

| Tiêu chí | Hàm thuần | Hàm có tác dụng phụ |
|---|---|---|
| Kết quả với cùng đầu vào | Ổn định theo cùng ngữ nghĩa | Có thể phụ thuộc trạng thái hoặc môi trường |
| Trạng thái bên ngoài | Không đọc/ghi trạng thái có thể quan sát | Có thể đọc hoặc thay đổi trạng thái |
| Kiểm thử | Thường chỉ cần đầu vào và kết quả mong đợi | Có thể cần mock, fixture hoặc hệ thống tích hợp |
| Tái sử dụng kết quả | Có thể cache nếu điều kiện phù hợp | Không thể tùy tiện cache hoặc bỏ qua lời gọi |
| Thực thi song song | Dễ lý luận hơn nếu không có phụ thuộc dùng chung | Cần xem xét xung đột và thứ tự |
| Tối ưu hóa | Nhiều phép biến đổi an toàn hơn | Phải giữ nguyên tác động quan sát được |

### 3.2. Hàm đọc trạng thái cũng có thể không thuần

Một hàm không sửa dữ liệu vẫn có thể không thuần nếu kết quả phụ thuộc vào trạng thái thay đổi theo thời gian.

Ví dụ:

```text
function currentBalance(accountId):
    return database.readBalance(accountId)
```

Hai lần gọi với cùng `accountId` có thể trả về số dư khác nhau nếu có giao dịch xảy ra giữa hai lần gọi. Hàm không ghi database nhưng vẫn có hiệu ứng đọc dữ liệu bên ngoài.

### 3.3. Hàm có thể vừa thuần vừa có hiệu ứng ở những lớp khác nhau

Một hàm có thể nhận dữ liệu đã được đọc từ database rồi tính toán thuần:

```text
orders = database.loadOrders(customerId)
total = calculateTotal(orders)
```

`database.loadOrders` có hiệu ứng đọc bên ngoài. `calculateTotal` có thể là hàm thuần. Việc tách hai phần giúp logic tính toán dễ kiểm thử và có thể tái sử dụng độc lập.

## 4. Tác dụng phụ trong ngữ nghĩa của DSL

DSL cần mô tả không chỉ cú pháp của thao tác mà còn tác động mà thao tác tạo ra. Hai câu lệnh có cùng kiểu trả về vẫn có thể có ngữ nghĩa rất khác nếu một câu lệnh thay đổi trạng thái còn câu kia không.

Ví dụ, trong DSL workflow:

```text
let total = calculateTotal(order)
save(order)
notify(customer)
```

Có thể phân biệt:

- `calculateTotal`: tính toán giá trị, có thể thuần.
- `save`: ghi dữ liệu, tạo hiệu ứng ghi.
- `notify`: gửi thông báo, tạo hiệu ứng giao tiếp bên ngoài.

Một DSL khai báo có thể cho phép người dùng mô tả trạng thái mong muốn, rồi engine quyết định các bước tạo tác động. Một DSL mệnh lệnh có thể biểu diễn trực tiếp thứ tự thao tác. Dù theo phong cách nào, ngữ nghĩa hiệu ứng cần được xác định.

### 4.1. Biểu thức và câu lệnh

Một số DSL phân biệt biểu thức (*expression*) với câu lệnh (*statement*):

- Biểu thức tạo ra giá trị và có thể được lồng trong biểu thức khác.
- Câu lệnh thực hiện một hành động, có thể không trả về giá trị.

Đây là một cách thiết kế hữu ích để làm rõ vị trí cho phép tác dụng phụ. Ví dụ, DSL có thể cho phép biểu thức thuần ở trong điều kiện, nhưng chỉ cho phép thao tác ghi ở cấp câu lệnh.

```text
if order.total > 0 {
    save(order)
}
```

Điều kiện có thể được yêu cầu là thuần để tránh việc kiểm tra điều kiện tự thay đổi trạng thái. Phần thân chứa câu lệnh có hiệu ứng.

### 4.2. Ngữ nghĩa của thao tác đọc và thao tác ghi

Một DSL dữ liệu có thể phân biệt rõ query và command:

- **Query:** đọc dữ liệu và trả về kết quả, không chủ ý thay đổi trạng thái nghiệp vụ.
- **Command:** yêu cầu thay đổi trạng thái hoặc thực hiện hành động.

Ví dụ:

```text
orders = query Orders where customerId == id
command CancelOrder(orderId)
```

Phân biệt này giúp người đọc biết thao tác nào có thể làm thay đổi hệ thống. Tuy nhiên, query vẫn có thể tạo hiệu ứng kỹ thuật như ghi audit log hoặc cập nhật cache; cần xác định hiệu ứng nào được coi là một phần ngữ nghĩa nghiệp vụ.

## 5. Thứ tự thực thi và tác dụng phụ

Khi nhiều biểu thức có tác dụng phụ được thực hiện, thứ tự có thể làm thay đổi kết quả quan sát được.

Ví dụ:

```text
setBalance(100)
charge(20)
```

Nếu `charge` đọc số dư, nó phải chạy sau `setBalance` để quan sát giá trị mới. Đổi thứ tự hai thao tác có thể làm hành vi khác đi.

DSL cần xác định:

- Các câu lệnh trong một khối có chạy tuần tự theo thứ tự viết không?
- Các biểu thức con trong một biểu thức được đánh giá theo thứ tự nào?
- Có cho phép engine thực thi song song các thao tác độc lập không?
- Một thao tác lỗi có ngăn các thao tác sau chạy không?
- Thao tác đã hoàn tất trước khi lỗi xảy ra có được hoàn tác không?

### 5.1. Thứ tự đánh giá biểu thức

Xét:

```text
result = updateLeft() + updateRight()
```

Nếu cả hai hàm đều thay đổi trạng thái dùng chung, thứ tự gọi có thể ảnh hưởng đến kết quả. Tính kết hợp của toán tử `+` không tự quyết định thứ tự đánh giá hai hàm.

Một DSL nên tránh để biểu thức có tác dụng phụ phụ thuộc vào thứ tự không được đặc tả. Có thể quy định đánh giá từ trái sang phải, hoặc hạn chế lời gọi có hiệu ứng trong biểu thức phức tạp.

### 5.2. Đánh giá ngắn mạch

Toán tử logic có thể dùng đánh giá ngắn mạch (*short-circuit*): vế phải chỉ được đánh giá khi cần thiết.

```text
isAuthenticated and loadSensitiveProfile()
```

Nếu `isAuthenticated` là `false`, DSL có thể không gọi `loadSensitiveProfile()`. Nếu vế phải có tác dụng phụ, quy tắc short-circuit quyết định tác dụng đó có xảy ra hay không.

Vì vậy, đặc tả cần nêu rõ:

- `and` có bỏ qua vế phải khi vế trái là false không?
- `or` có bỏ qua vế phải khi vế trái là true không?
- Có thứ tự đánh giá cố định không?
- Các biểu thức được phép có hiệu ứng trong điều kiện không?

### 5.3. Tác dụng phụ và tối ưu hóa

Compiler có thể tối ưu biểu thức thuần bằng cách tính trước hằng số, loại bỏ phép tính không dùng đến hoặc dùng lại kết quả. Với biểu thức có tác dụng phụ, các phép biến đổi đó có thể làm thay đổi hành vi.

Ví dụ:

```text
sendEmail(customer)
sendEmail(customer)
```

Compiler không được gộp hai lời gọi thành một chỉ vì chúng có cùng tham số. Hai email có thể là hai tác động mà chương trình yêu cầu.

Tương tự:

```text
if false and writeAuditRecord():
    doSomething()
```

Nếu `and` dùng short-circuit, `writeAuditRecord()` không được gọi. Một phép biến đổi không giữ quy tắc này có thể tạo ra bản ghi audit không mong muốn.

## 6. Khả năng lặp lại và tính tham chiếu minh bạch

Một biểu thức có tính **tham chiếu minh bạch** (*referential transparency*) nếu có thể thay biểu thức bằng giá trị của nó mà không làm thay đổi hành vi chương trình.

Ví dụ:

```text
subtotal = calculateSubtotal(items)
```

Nếu `calculateSubtotal` là hàm thuần, có thể thay lời gọi bằng giá trị kết quả trong cùng ngữ cảnh mà không tạo khác biệt quan sát được.

Nhưng không thể thay tùy tiện:

```text
id = random.uuid()
```

bằng một UUID cố định đã quan sát từ một lần chạy, vì lần gọi tiếp theo có thể tạo giá trị khác. Cũng không thể thay một lời gọi ghi dữ liệu bằng giá trị trả về mà bỏ qua tác động ghi.

### 6.1. Cache và memoization

Memoization lưu kết quả của một hàm để tránh tính lại với cùng đầu vào. Cách này phù hợp với hàm thuần nếu đầu vào và ngữ nghĩa không đổi.

Với hàm đọc database, cache có thể trả dữ liệu cũ. Với hàm ghi dữ liệu, cache có thể khiến thao tác không được thực hiện. Vì vậy, muốn cache một thao tác có hiệu ứng cần có chính sách nhất quán và invalidation rõ ràng.

### 6.2. Tái thực thi và retry

Một tác vụ có thể được chạy lại khi timeout hoặc lỗi mạng. Nếu tác vụ có tác dụng phụ, chạy lại có thể tạo hành động trùng lặp.

Ví dụ, nếu yêu cầu tạo hóa đơn đã được xử lý ở hệ thống đích nhưng phản hồi bị mất, client có thể gửi lại yêu cầu. Nếu không có cơ chế nhận diện trùng, hệ thống có thể tạo hai hóa đơn.

Do đó, DSL workflow hoặc integration nên phân biệt thao tác có thể lặp an toàn và thao tác cần bảo vệ chống lặp.

## 7. Tính idempotent và tác dụng phụ

Một thao tác là **idempotent** nếu thực hiện nhiều lần với cùng ý định và điều kiện phù hợp cho kết quả trạng thái tương đương với thực hiện một lần.

Ví dụ:

```text
setServiceReplicas("catalog", 3)
```

Nếu thao tác đặt số replica thành 3, gọi lại có thể vẫn giữ trạng thái mong muốn là 3. Đây thường là thao tác idempotent về trạng thái.

Ngược lại:

```text
incrementCounter("requests")
```

gọi hai lần làm bộ đếm tăng hai đơn vị, nên không idempotent.

### 7.1. Idempotent không có nghĩa là không có tác dụng phụ

Một thao tác đặt trạng thái có thể ghi database, phát log hoặc gọi API. Nó vẫn tạo tác dụng phụ dù trạng thái cuối cùng sau nhiều lần gọi giống nhau.

### 7.2. Idempotency key

Với các thao tác như tạo thanh toán hoặc tạo đơn hàng, hệ thống có thể dùng khóa idempotency để nhận diện các yêu cầu lặp lại thuộc cùng một ý định.

```text
payment = chargeCard(
    orderId = order.id,
    amount = order.total,
    idempotencyKey = order.paymentRequestId
)
```

Nếu yêu cầu được gửi lại với cùng khóa, hệ thống có thể trả lại kết quả đã ghi nhận thay vì tạo giao dịch mới. Cách triển khai cụ thể phụ thuộc dịch vụ đích và hợp đồng API.

## 8. Tác dụng phụ và giao dịch

Khi nhiều thao tác ghi liên quan đến cùng một nghiệp vụ, DSL hoặc runtime có thể cung cấp **giao dịch** (*transaction*) để nhóm chúng thành một đơn vị nhất quán.

Ví dụ:

```text
transaction {
    debit(sourceAccount, amount)
    credit(destinationAccount, amount)
    recordTransfer(sourceAccount, destinationAccount, amount)
}
```

Mong muốn nghiệp vụ là nếu một bước thất bại, toàn bộ thay đổi liên quan được xử lý theo chính sách transaction để không tạo trạng thái chuyển tiền dở dang.

### 8.1. Commit và rollback

- **Commit:** xác nhận các thay đổi của transaction thành công.
- **Rollback:** hủy các thay đổi chưa được commit theo khả năng của hệ thống lưu trữ.

Một DSL có thể biểu diễn ranh giới transaction rõ ràng hoặc để runtime quản lý. Dù theo cách nào, cần xác định thao tác nào tham gia transaction và lỗi nào kích hoạt rollback.

### 8.2. Không phải mọi tác dụng phụ đều rollback được

Ghi database trong transaction có thể rollback, nhưng gửi email hoặc gọi một dịch vụ bên ngoài thường không thể tự động hoàn tác.

Ví dụ:

```text
transaction {
    saveOrder(order)
    email.send(customer, receipt)
}
```

Nếu email đã gửi nhưng transaction database rollback, hệ thống có thể gửi thông báo về một đơn hàng không tồn tại. Vì vậy, cần thiết kế ranh giới hiệu ứng phù hợp.

Một giải pháp thường gặp là **transactional outbox**: ghi đơn hàng và một sự kiện cần gửi vào cùng transaction database; một tiến trình riêng đọc outbox rồi gửi thông báo. Cách này giúp đồng bộ việc lưu trạng thái nghiệp vụ với việc lên lịch phát sự kiện, dù vẫn cần xử lý gửi lặp và xác nhận.

### 8.3. Saga và hành động bù trừ

Với quy trình kéo dài qua nhiều dịch vụ, một transaction cơ sở dữ liệu duy nhất thường không bao trùm được mọi hệ thống. Mô hình Saga chia quy trình thành các bước; mỗi bước có thể có một hành động bù trừ (*compensating action*) để xử lý khi bước sau thất bại.

Ví dụ đặt hàng:

1. Giữ hàng trong kho.
2. Thu tiền.
3. Tạo vận đơn.

Nếu tạo vận đơn thất bại sau khi đã thu tiền, quy trình có thể hoàn tiền và giải phóng hàng theo chính sách nghiệp vụ. Hành động bù trừ không phải lúc nào cũng xóa được hoàn toàn tác động đã xảy ra, nhưng giúp hệ thống tiến về trạng thái nghiệp vụ chấp nhận được.

## 9. Cách DSL biểu diễn và kiểm soát tác dụng phụ

Một DSL có thể chọn nhiều chiến lược để làm rõ hiệu ứng của chương trình.

### 9.1. Tách biểu thức thuần và câu lệnh có hiệu ứng

DSL có thể yêu cầu biểu thức điều kiện, biểu thức tính toán hoặc giá trị cấu hình phải thuần. Các hành động ghi hoặc giao tiếp bên ngoài được đặt trong câu lệnh riêng.

```text
let total = calculateTotal(order)

if total > creditLimit {
    reject(order)
} else {
    save(order)
}
```

Cách tổ chức này giúp người đọc nhận ra ranh giới giữa tính toán và hành động.

### 9.2. Khai báo effect trong kiểu hoặc chữ ký

Một DSL có thể khai báo hiệu ứng của thao tác để validator và công cụ biết lời gọi có thể làm gì.

Ví dụ cú pháp giả định:

```text
function calculateTotal(order): Money
    effects: none

function saveOrder(order): OrderId
    effects: [DatabaseWrite]

function sendReceipt(order): Unit
    effects: [Network, Email]
```

Thông tin effect có thể được kiểm tra tĩnh, dùng để sinh tài liệu, giới hạn môi trường thực thi hoặc giúp optimizer tránh biến đổi không an toàn.

### 9.3. Effect system

**Hệ thống hiệu ứng** (*effect system*) mở rộng thông tin kiểu để mô tả không chỉ giá trị mà một biểu thức tạo ra, mà cả những hiệu ứng mà biểu thức có thể thực hiện.

Ví dụ, kiểu thông thường có thể mô tả:

```text
saveOrder : Order -> OrderId
```

Một cách biểu diễn có effect có thể mô tả thêm:

```text
saveOrder : Order -> OrderId ! DatabaseWrite
```

Ký hiệu `! DatabaseWrite` chỉ là cách viết minh họa. Mỗi ngôn ngữ có thể dùng cú pháp và mô hình effect khác nhau.

Validator có thể dùng thông tin đó để kiểm tra rằng một biểu thức được yêu cầu thuần không gọi hàm có hiệu ứng ghi dữ liệu.

### 9.4. Capability và quyền truy cập

Một DSL chạy trong môi trường giới hạn có thể yêu cầu chương trình nhận capability để thực hiện hiệu ứng.

Ví dụ:

```text
run workflow with capabilities [DatabaseRead, EmailSend]
```

Nếu chương trình gọi thao tác ghi database nhưng chỉ được cấp `DatabaseRead`, runtime hoặc validator có thể từ chối. Cơ chế này giúp giới hạn quyền của DSL theo nhu cầu thực tế.

Khai báo capability không tự bảo đảm an toàn. Runtime vẫn phải kiểm tra quyền thực tế ở điểm thực thi, đặc biệt khi DSL gọi plugin hoặc mã bên ngoài.

### 9.5. Mô hình command/query

DSL có thể tách thao tác truy vấn và thao tác thay đổi trạng thái thành hai nhóm. Cách phân tách này giúp API rõ ràng và dễ kiểm tra hơn, nhất là trong hệ thống dữ liệu hoặc nghiệp vụ.

## 10. Tác dụng phụ trong DSL khai báo và DSL mệnh lệnh

DSL mệnh lệnh thường biểu diễn trực tiếp chuỗi hành động:

```text
readFile("input.csv")
parseRows()
writeFile("output.csv")
```

Thứ tự câu lệnh thường thể hiện thứ tự thực hiện. Người đọc có thể thấy rõ thao tác I/O nằm ở đâu.

DSL khai báo thường mô tả trạng thái hoặc kết quả mong muốn:

```text
service "catalog" {
    replicas = 3
    region = "asia-southeast1"
}
```

Engine quyết định cần tạo, cập nhật hoặc xóa tài nguyên nào để đạt trạng thái đó. Tác dụng phụ xảy ra trong quá trình engine áp dụng kế hoạch, dù văn bản DSL không mô tả từng bước.

### 10.1. Tác dụng phụ ẩn trong DSL khai báo

Một cấu hình khai báo có thể trông như dữ liệu thuần, nhưng khi áp dụng lại tạo ra nhiều thay đổi bên ngoài. Vì vậy, cần phân biệt:

- Phân tích hoặc xác thực cấu hình.
- Lập kế hoạch thay đổi.
- Áp dụng thay đổi lên môi trường.

Một công cụ triển khai có thể cung cấp chế độ `plan` để xem trước các thay đổi mà không thực hiện chúng, rồi chế độ `apply` để thực hiện tác dụng phụ.

### 10.2. Tính xác định của kế hoạch

Nếu cùng một cấu hình tạo ra kế hoạch khác nhau do thời gian, trạng thái cloud hoặc dữ liệu bên ngoài, công cụ nên chỉ rõ những phụ thuộc đó. Việc tách bước đọc trạng thái, lập kế hoạch và áp dụng giúp người dùng hiểu khi nào hệ thống chỉ tính toán và khi nào nó thay đổi môi trường.

## 11. Tác dụng phụ, đồng thời và tranh chấp dữ liệu

Khi nhiều tác vụ cùng đọc hoặc ghi trạng thái dùng chung, kết quả có thể phụ thuộc vào cách chúng xen kẽ.

Ví dụ, hai tác vụ cùng đọc số dư `100`, rồi mỗi tác vụ trừ `80` và ghi kết quả `20`. Nếu không có kiểm soát đồng thời, cả hai giao dịch có thể thành công dù tổng số tiền bị trừ là `160`.

Đây là dạng lỗi cập nhật bị mất (*lost update*).

### 11.1. Race condition

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự hoặc thời điểm tương đối của các thao tác đồng thời. Nếu DSL cho phép chạy song song, cần quy định những hiệu ứng nào có thể chạy đồng thời và những hiệu ứng nào cần đồng bộ.

### 11.2. Đồng bộ và cô lập

Các kỹ thuật thường dùng gồm:

- Khóa (*locking*) để giới hạn truy cập đồng thời.
- Transaction và mức cô lập của cơ sở dữ liệu.
- Compare-and-set hoặc cập nhật có điều kiện.
- Actor hoặc hàng đợi tuần tự hóa thao tác theo một thực thể.
- Chia sẻ trạng thái bất biến thay vì cho nhiều tác vụ cùng sửa.

DSL không nhất thiết phải phơi bày tất cả cơ chế thấp cấp. Nó có thể cung cấp các cấu trúc như `transaction`, `parallel`, `lock` hoặc `serial` với ngữ nghĩa rõ ràng.

### 11.3. Hiệu ứng và thực thi song song

Hai biểu thức thuần độc lập thường có thể được đánh giá song song mà không ảnh hưởng kết quả. Hai thao tác cùng ghi một tài nguyên cần có quy tắc đồng bộ hoặc thứ tự.

Compiler hoặc scheduler có thể dùng metadata effect để xác định phụ thuộc. Ví dụ, `DatabaseWrite(accountA)` và `DatabaseWrite(accountB)` có thể độc lập nếu tài nguyên và transaction không liên quan; hai thao tác ghi cùng `accountA` có thể cần tuần tự hóa.

## 12. Tác dụng phụ và xử lý lỗi

Một thao tác có tác dụng phụ có thể thất bại trước, trong hoặc sau khi hệ thống đích đã xử lý yêu cầu. Điều này tạo ra tình huống khó xác định trạng thái thực tế.

Ví dụ, client gửi yêu cầu tạo thanh toán. Dịch vụ đã xử lý nhưng phản hồi bị mất do timeout. Client không biết giao dịch đã thành công hay chưa.

DSL hoặc runtime cần quy định:

- Lỗi nào được retry tự động.
- Lỗi nào cần dừng workflow.
- Khi retry, có dùng idempotency key không.
- Có thể rollback hay cần hành động bù trừ.
- Trạng thái chưa xác định được biểu diễn thế nào.
- Log và event có đủ thông tin để điều tra không.

### 12.1. Retry có điều kiện

Retry phù hợp với lỗi tạm thời như timeout hoặc giới hạn tốc độ, nhưng không phải lỗi nào cũng nên thử lại. Lỗi dữ liệu không hợp lệ thường không thể khắc phục bằng cách gửi lại cùng yêu cầu.

Một DSL workflow có thể mô tả:

```text
retry 3 times with exponentialBackoff {
    callExternalService(request)
}
```

Ngữ nghĩa cần nêu rõ số lần thử có tính lần đầu hay không, khoảng chờ, lỗi nào được retry và hành động có cần idempotent hay không.

### 12.2. Bù trừ thay vì rollback

Với tác động đã xảy ra ở hệ thống ngoài, rollback kỹ thuật có thể không tồn tại. Một thao tác bù trừ như hoàn tiền, hủy đặt chỗ hoặc phát thông báo đính chính có thể được dùng để xử lý nghiệp vụ.

## 13. Kiểm thử chương trình có tác dụng phụ

Hàm thuần thường dễ kiểm thử bằng cách so sánh đầu vào và đầu ra. Chương trình có tác dụng phụ cần kiểm tra cả hành động và trạng thái sau khi thực thi.

### 13.1. Unit test với dependency được thay thế

Có thể thay database, email sender hoặc HTTP client bằng mock/fake để kiểm tra:

- Thao tác nào được gọi.
- Tham số được truyền có đúng không.
- Thứ tự lời gọi có đúng hợp đồng không.
- Lỗi được xử lý như mong đợi không.
- Có lời gọi trùng không mong muốn không.

### 13.2. Integration test

Integration test kiểm tra tương tác với hệ thống thật hoặc môi trường thử nghiệm, chẳng hạn database, message broker hoặc dịch vụ HTTP giả lập.

Các kiểm thử này giúp phát hiện vấn đề transaction, serialization, timeout, quyền truy cập và tính nhất quán mà unit test có thể bỏ sót.

### 13.3. Kiểm thử tính idempotent và retry

Với thao tác có thể được chạy lại, nên kiểm tra nhiều lần cùng một yêu cầu có tạo trạng thái trùng hoặc tác động lặp không. Cũng cần mô phỏng trường hợp hệ thống đích đã xử lý nhưng phản hồi bị mất.

### 13.4. Kiểm thử thứ tự và đồng thời

Nếu DSL có `parallel`, `transaction` hoặc thao tác trên trạng thái dùng chung, cần kiểm tra các thứ tự thực thi khác nhau và các tình huống tranh chấp. Không nên chỉ kiểm thử một lịch chạy may mắn.

## 14. Thiết kế DSL để quản lý tác dụng phụ

Một DSL tốt nên giúp người dùng nhận biết và kiểm soát hiệu ứng mà chương trình có thể tạo ra.

### 14.1. Làm rõ ranh giới hiệu ứng

Đặt thao tác có hiệu ứng trong câu lệnh hoặc khối rõ ràng. Tránh để một hàm có tên giống phép tính thuần nhưng âm thầm ghi dữ liệu hoặc gửi yêu cầu ra ngoài.

### 14.2. Khai báo effect hoặc quyền cần thiết

Nếu DSL có hệ thống effect, chữ ký thao tác có thể nêu rõ khả năng đọc/ghi database, mạng, tệp hoặc trạng thái. Nếu DSL chạy trong môi trường hạn chế, capability có thể xác định quyền được cấp.

### 14.3. Định nghĩa thứ tự thực thi

Quy định thứ tự câu lệnh, thứ tự đánh giá toán hạng, short-circuit và hành vi khi có lỗi. Nếu một số thao tác được chạy song song, cần xác định phụ thuộc và điều kiện an toàn.

### 14.4. Tách lập kế hoạch và áp dụng

Với DSL khai báo có thể thay đổi hạ tầng hoặc dữ liệu, nên cân nhắc các bước phân tích, plan, review và apply. Người dùng có thể xem trước tác động trước khi engine thực hiện.

### 14.5. Cung cấp transaction và hành động bù trừ phù hợp

Những thao tác ghi liên quan nên có ranh giới nhất quán. Với hệ thống ngoài transaction, cần xác định chiến lược retry, idempotency và compensation.

### 14.6. Ghi nhận và quan sát hiệu ứng

Log, trace, audit event và metric giúp người vận hành biết tác động nào đã xảy ra. Thông tin nên bao gồm mã tác vụ, đối tượng nghiệp vụ, kết quả và correlation ID mà không ghi lộ dữ liệu nhạy cảm.

## 15. Ví dụ tổng hợp: DSL xử lý đơn hàng

Giả sử một DSL workflow xử lý đơn hàng gồm tính tổng, kiểm tra tồn kho, thu tiền và gửi xác nhận:

```text
workflow processOrder(order):
    total = calculateTotal(order.items)

    if inventory.available(order.items):
        payment = payment.charge(
            order.customer,
            total,
            idempotencyKey = order.id
        )

        if payment.success:
            database.save(order.withStatus("paid"))
            events.publish("order.paid", order.id)
        else:
            return PaymentFailed
    else:
        return OutOfStock
```

Các thao tác có thể được phân loại như sau:

| Thao tác | Loại hiệu ứng | Ghi chú |
|---|---|---|
| `calculateTotal` | Thuần nếu chỉ tính từ đầu vào | Có thể kiểm thử độc lập |
| `inventory.available` | Đọc trạng thái bên ngoài | Kết quả có thể thay đổi theo thời điểm |
| `payment.charge` | Mạng và ghi trạng thái thanh toán | Cần xử lý timeout, retry và idempotency |
| `database.save` | Ghi database | Có thể tham gia transaction database |
| `events.publish` | Phát sự kiện ra ngoài | Cần xử lý trường hợp publish thất bại hoặc lặp |

Trong hệ thống thực tế, giữa kiểm tra tồn kho và thu tiền có thể có tranh chấp: hàng có thể bị người khác đặt sau khi kiểm tra. Việc giữ hàng, xác nhận tồn kho và thanh toán cần được thiết kế theo hợp đồng nghiệp vụ. Tương tự, nếu database lưu thành công nhưng publish event thất bại, transactional outbox có thể giúp bảo đảm sự kiện được gửi lại.

Ví dụ này cho thấy một workflow có thể kết hợp tính toán thuần, đọc trạng thái và nhiều tác động ghi. DSL cần làm rõ ranh giới và chính sách của từng loại hiệu ứng.

## 16. Những sai lầm thường gặp

**Coi mọi hàm trả về giá trị là thuần.** Một hàm có thể trả về kết quả nhưng vẫn ghi database, gửi mạng hoặc thay đổi trạng thái.

**Coi thao tác đọc luôn không có hiệu ứng.** Đọc dữ liệu ngoài làm kết quả phụ thuộc trạng thái và thời điểm, nên có thể cần được mô hình hóa như một hiệu ứng đọc.

**Ẩn tác dụng phụ trong biểu thức điều kiện.** Một điều kiện có thể được đánh giá nhiều lần hoặc bỏ qua do short-circuit. Nếu nó ghi dữ liệu, hành vi sẽ khó dự đoán.

**Cho compiler loại bỏ lời gọi có hiệu ứng không dùng giá trị trả về.** Lời gọi có thể vẫn cần xảy ra vì tác động của nó là mục tiêu chính.

**Đồng nhất tính kết hợp với thứ tự thực thi.** Cấu trúc nhóm toán tử không tự quyết định thứ tự gọi hàm hoặc thực hiện I/O.

**Retry mọi lỗi.** Thử lại thao tác không idempotent có thể tạo giao dịch, email hoặc đơn hàng trùng lặp.

**Giả định mọi tác dụng phụ đều rollback được.** Hệ thống ngoài database thường không tham gia cùng transaction; cần outbox, saga hoặc hành động bù trừ.

**Cho phép chạy song song mà không xét hiệu ứng.** Các thao tác ghi cùng trạng thái có thể tạo race condition hoặc lost update.

**Không công bố quyền mà DSL cần.** Một workflow có thể âm thầm truy cập mạng hoặc tệp nếu runtime không kiểm soát capability.

## 17. Ghi nhớ

- Tác dụng phụ là ảnh hưởng quan sát được ngoài giá trị trả về, như thay đổi trạng thái, I/O, giao tiếp mạng hoặc phát sinh sự kiện.
- Hàm thuần không tạo tác động quan sát được và cho kết quả ổn định với cùng đầu vào trong cùng ngữ nghĩa.
- Đọc dữ liệu bên ngoài cũng có thể được mô hình hóa là hiệu ứng vì kết quả phụ thuộc trạng thái và thời điểm.
- Tác dụng phụ khiến thứ tự đánh giá, short-circuit, tối ưu hóa và thực thi song song cần được quy định rõ.
- Idempotent giúp thao tác an toàn hơn khi retry, nhưng không có nghĩa thao tác không tạo tác dụng phụ.
- Transaction hỗ trợ nhất quán cho các thay đổi nằm trong phạm vi của nó; tác động bên ngoài có thể cần outbox hoặc saga.
- DSL có thể quản lý hiệu ứng bằng cách tách expression/statement, khai báo effect, capability và ranh giới command/query.
- Kiểm thử chương trình có hiệu ứng cần kiểm tra cả kết quả, hành động, thứ tự, lỗi và khả năng chạy lặp.

## 18. Câu hỏi tự kiểm tra

1. Tác dụng phụ là gì? Nó khác giá trị trả về như thế nào?
2. Vì sao một hàm chỉ đọc database vẫn có thể được xem là có hiệu ứng?
3. Nêu ba loại tác dụng phụ thường gặp trong DSL workflow.
4. Hai đặc điểm nào xác định một hàm thuần?
5. Vì sao compiler không được tùy tiện loại bỏ hai lời gọi `sendEmail(customer)` giống nhau?
6. Phân biệt tính kết hợp của toán tử với thứ tự đánh giá biểu thức có lời gọi hàm.
7. Short-circuit ảnh hưởng thế nào đến việc một tác dụng phụ ở vế phải có xảy ra hay không?
8. Idempotent là gì? Vì sao một thao tác idempotent vẫn có thể tạo tác dụng phụ?
9. Vì sao gửi email thường không thể được rollback cùng transaction database?
10. Effect system hoặc capability giúp công cụ DSL kiểm soát thao tác như thế nào?
11. Nêu một rủi ro khi chạy song song hai thao tác cùng cập nhật một trạng thái dùng chung.
12. Trong workflow xử lý đơn hàng, hãy phân loại thao tác thuần, thao tác đọc và thao tác ghi; đề xuất cách xử lý retry cho bước thanh toán.
