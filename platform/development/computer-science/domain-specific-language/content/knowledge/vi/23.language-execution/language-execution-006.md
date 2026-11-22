# Giao dịch

Trong một **Domain-Specific Language (DSL)** dùng để mô tả nghiệp vụ, workflow, truy vấn hoặc thao tác dữ liệu, một lệnh thường không chỉ tính ra một giá trị. Nó có thể đọc nhiều bản ghi, cập nhật trạng thái, tạo đơn hàng, ghi nhận thanh toán hoặc phát sinh sự kiện. Nếu chương trình dừng giữa chừng, hệ thống có thể bị để lại ở trạng thái chỉ hoàn thành một phần. **Giao dịch (transaction)** cung cấp một ranh giới để nhóm nhiều thao tác thành một đơn vị xử lý có kết quả nhất quán.

Ví dụ, một DSL xử lý chuyển tiền có thể mô tả:

~~~text
transaction "transfer" {
    debit account(source) by amount
    credit account(destination) by amount
    record transfer(source, destination, amount)
}
~~~

Ý định của giao dịch là khoản tiền được trừ ở tài khoản nguồn, cộng ở tài khoản đích và ghi nhận lịch sử chuyển tiền như một đơn vị. Nếu một thao tác thất bại trước khi giao dịch hoàn tất, hệ thống cần xử lý theo chính sách đã định để không giữ lại một phần cập nhật.

Trong ngữ cảnh thực thi DSL, giao dịch là hợp đồng giữa ngôn ngữ, runtime và các dịch vụ mà chương trình sử dụng. Nó xác định thao tác nào thuộc cùng một đơn vị, khi nào thay đổi trở nên có hiệu lực, cách xử lý lỗi và cách phối hợp với dữ liệu hoặc hệ thống bên ngoài.

## 1. Giao dịch là gì?

**Transaction** là một đơn vị công việc gồm một hoặc nhiều thao tác được quản lý như một thể thống nhất. Hệ thống thường cung cấp hai kết quả chính:

- **Commit:** xác nhận giao dịch thành công và làm cho các thay đổi được chấp nhận theo chính sách lưu trữ.
- **Rollback:** hủy các thay đổi chưa được commit và đưa dữ liệu được quản lý về trạng thái phù hợp trước giao dịch.

Một giao dịch thường có trình tự:

1. Bắt đầu giao dịch.
2. Đọc dữ liệu và thực hiện các thao tác.
3. Kiểm tra các điều kiện và bất biến.
4. Commit nếu tất cả điều kiện cần thiết được thỏa mãn.
5. Rollback nếu có lỗi hoặc điều kiện không đạt.

Trong DSL, ranh giới giao dịch có thể được thể hiện bằng block, câu lệnh hoặc annotation:

~~~text
transaction {
    let order = createOrder(input)
    reserveInventory(order)
    calculateTotal(order)
    commit
}
~~~

Đây là cú pháp minh họa. Một DSL khác có thể không cho người viết gọi commit tường minh; runtime tự commit khi block kết thúc bình thường và rollback khi block ném lỗi.

Giao dịch không nhất thiết chỉ liên quan đến database. Nó có thể quản lý một tập thay đổi trong bộ nhớ, một nhóm thao tác trên kho dữ liệu, một quy trình cập nhật trạng thái hoặc một workflow phân tán. Tuy nhiên, mức bảo đảm khác nhau tùy tài nguyên và cơ chế tham gia giao dịch.

## 2. Vì sao DSL cần hỗ trợ giao dịch?

DSL thường giúp người dùng mô tả nghiệp vụ ở mức cao. Khi một quy tắc hoặc workflow gồm nhiều thao tác có liên quan, ngôn ngữ cần biểu diễn cách chúng thành công hoặc thất bại cùng nhau.

Ví dụ quy trình tạo đơn hàng:

~~~text
process order(input) {
    let order = createOrder(input)
    reserveStock(order.items)
    chargePayment(order.payment)
    markOrderConfirmed(order)
}
~~~

Nếu thanh toán thất bại sau khi kho đã giữ hàng, hệ thống cần biết có phải giải phóng hàng đã giữ hay không. Nếu tạo đơn thành công nhưng bước xác nhận thất bại, trạng thái đơn hàng cần được xử lý thế nào? Những câu hỏi đó là vấn đề giao dịch và điều phối, không chỉ là vấn đề cú pháp.

Hỗ trợ giao dịch giúp DSL:

- Nhóm thao tác dữ liệu thành một đơn vị nghiệp vụ.
- Bảo vệ các bất biến khi cập nhật nhiều bản ghi.
- Xác định hành vi khi một bước thất bại.
- Quản lý xung đột giữa các lần thực thi đồng thời.
- Phối hợp cập nhật dữ liệu và phát sự kiện.
- Làm rõ trách nhiệm của runtime và ứng dụng chủ.
- Cung cấp cách viết nhất quán cho các thao tác có tính nguyên tử.

Không phải mọi thao tác trong DSL đều cần transaction. Một biểu thức thuần chỉ tính giá trị thường không cần ranh giới commit. Giao dịch có ý nghĩa khi có trạng thái hoặc hiệu ứng cần được quản lý theo một đơn vị.

## 3. Bốn thuộc tính ACID

Các hệ quản trị giao dịch thường mô tả bốn thuộc tính ACID: Atomicity, Consistency, Isolation và Durability. Đây là một mô hình quan trọng khi thiết kế transaction trong DSL, đặc biệt khi runtime làm việc với cơ sở dữ liệu.

### 3.1. Atomicity — Tính nguyên tử

Tính nguyên tử có nghĩa giao dịch được chấp nhận như một đơn vị: các thay đổi thuộc giao dịch cùng được commit hoặc được rollback theo khả năng của hệ thống tham gia.

Ví dụ chuyển tiền:

~~~text
transaction {
    withdraw(source, 100)
    deposit(destination, 100)
}
~~~

Nếu withdraw thành công nhưng deposit thất bại, hệ thống không được để khoản tiền bị trừ mà không được cộng vào tài khoản đích. Một transaction manager có thể rollback cả hai cập nhật nếu chúng nằm trong cùng một transaction resource hỗ trợ atomic commit.

Atomicity không tự động hoàn tác được email đã gửi, tin nhắn đã phát ra ngoài hoặc thao tác trên một API không hỗ trợ rollback. Với những side effect đó, cần thiết kế cơ chế khác như outbox, retry hoặc saga compensation.

### 3.2. Consistency — Tính nhất quán

Consistency nghĩa là giao dịch phải đưa hệ thống từ một trạng thái hợp lệ sang một trạng thái hợp lệ khác, theo các invariant được xác định.

Ví dụ:

~~~text
invariant account.balance >= 0
invariant order.total == sum(order.items.amount)
~~~

Một giao dịch cập nhật số dư phải bảo đảm số dư không âm nếu đó là quy tắc miền. Một giao dịch cập nhật đơn hàng phải giữ tổng tiền khớp với các dòng hàng và chiết khấu.

Database constraint có thể bảo vệ một phần invariant, nhưng DSL thường cần kiểm tra thêm các quy tắc nghiệp vụ. Runtime phải xác định kiểm tra diễn ra trước commit, ở database hay trong một service miền.

### 3.3. Isolation — Tính cô lập

Isolation kiểm soát cách các giao dịch đồng thời nhìn thấy thay đổi của nhau. Mục tiêu là ngăn các lần thực thi tương tác theo cách tạo ra trạng thái không hợp lệ.

Ví dụ, hai yêu cầu cùng đọc số lượng tồn kho là 1 rồi cùng đặt mua một sản phẩm. Nếu cả hai cùng quyết định có thể đặt hàng dựa trên cùng dữ liệu cũ, hệ thống có thể bán vượt số lượng.

Isolation không nhất thiết có nghĩa mọi giao dịch phải chạy tuần tự hoàn toàn. Hệ thống có thể dùng khóa, MVCC hoặc phát hiện xung đột để đạt mức cô lập được công bố.

### 3.4. Durability — Tính bền vững

Durability nghĩa là sau khi commit thành công, thay đổi được lưu bền vững theo cam kết của hệ thống, kể cả khi tiến trình hoặc máy chủ gặp sự cố.

Runtime DSL thường không tự bảo đảm durability. Nó dựa vào database, log bền vững hoặc dịch vụ lưu trữ tham gia giao dịch. Khi runtime báo commit thành công, cần hiểu chính xác dịch vụ lưu trữ đã xác nhận điều gì.

### 3.5. Tóm tắt ACID

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Atomicity | Các thay đổi có được chấp nhận hoặc hủy như một đơn vị không? | Không trừ tiền nếu không thể ghi có |
| Consistency | Trạng thái sau giao dịch có giữ invariant không? | Số dư không âm |
| Isolation | Giao dịch đồng thời có nhìn thấy nhau theo quy tắc nào? | Không bán vượt tồn kho |
| Durability | Commit thành công có tồn tại sau sự cố không? | Đơn hàng đã commit vẫn được lưu |

ACID là tập bảo đảm của cơ chế giao dịch, không phải một từ khóa cú pháp. Việc DSL có block transaction không tự động chứng minh runtime hoặc database thực hiện đủ cả bốn thuộc tính.

## 4. Ranh giới giao dịch trong DSL

Ranh giới giao dịch xác định thao tác nào thuộc cùng một đơn vị commit hoặc rollback. Thiết kế ranh giới cần phù hợp với đơn vị nghiệp vụ và giới hạn của tài nguyên lưu trữ.

Ví dụ:

~~~text
transaction "confirm-order" {
    let order = loadOrder(orderId)
    require order.status == "PENDING"
    reserveInventory(order.items)
    updateOrderStatus(order, "CONFIRMED")
}
~~~

Trong ví dụ này, việc giữ hàng và chuyển trạng thái đơn hàng cần được xem xét cùng nhau. Nếu hai thao tác cùng dùng một database transaction, chúng có thể commit nguyên tử. Nếu reserveInventory gọi một dịch vụ kho độc lập, một transaction database đơn lẻ không thể tự bảo đảm atomicity xuyên hai hệ thống.

### 4.1. Transaction block

Một cú pháp block thường giúp người đọc nhìn thấy phạm vi:

~~~text
transaction {
    operationA()
    operationB()
    operationC()
}
~~~

Runtime có thể tự động:

- Mở transaction trước khi chạy block.
- Gắn transaction context vào các lời gọi bên trong.
- Commit khi block kết thúc bình thường.
- Rollback khi có exception hoặc lỗi được quy định là fatal.
- Giải phóng khóa và tài nguyên khi kết thúc.

### 4.2. Commit tường minh và commit tự động

**Commit tường minh** cho phép chương trình chỉ ra điểm xác nhận:

~~~text
transaction {
    updateAccount()
    validateTransfer()
    commit
}
~~~

**Commit tự động** thường dùng quy tắc: kết thúc block bình thường thì commit; thoát do lỗi thì rollback:

~~~text
transaction {
    updateAccount()
    validateTransfer()
}
~~~

Commit tự động làm cú pháp gọn hơn và giảm nguy cơ quên commit. Commit tường minh có thể hữu ích khi DSL có nhiều nhánh hoặc cần biểu diễn rõ thời điểm xác nhận. Dù chọn cách nào, hành vi khi return, break, cancellation và exception phải được xác định.

### 4.3. Ranh giới quá rộng hoặc quá hẹp

Giao dịch quá rộng có thể giữ khóa lâu, tăng xung đột và làm rollback nhiều công việc. Giao dịch quá hẹp có thể để lộ trạng thái trung gian không hợp lệ.

Ví dụ, nếu cập nhật từng dòng đơn hàng trong một transaction riêng, người đọc khác có thể nhìn thấy đơn hàng mới chỉ có một phần dòng hàng. Nếu toàn bộ quy trình gồm gọi API bên ngoài kéo dài nhiều phút được giữ trong một database transaction, khóa có thể bị giữ quá lâu.

Ranh giới tốt nên bao phủ những cập nhật cần nguyên tử với nhau và giữ thời gian thực thi ngắn nhất có thể.

## 5. Vòng đời của một giao dịch

Một transaction thường trải qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> Active: begin
    Active --> Preparing: commit requested
    Preparing --> Committed: checks succeed
    Preparing --> RollingBack: validation or commit fails
    Active --> RollingBack: exception or rollback
    RollingBack --> RolledBack
    Committed --> [*]
    RolledBack --> [*]
~~~

Ý nghĩa:

- **Active:** các thao tác được thực hiện trong transaction context.
- **Preparing:** runtime hoặc resource participant kiểm tra điều kiện commit.
- **Committed:** các thay đổi được xác nhận.
- **RollingBack:** hệ thống đang hoàn tác các thay đổi có thể rollback.
- **RolledBack:** giao dịch đã bị hủy.

Một số database có thêm trạng thái như prepared, failed hoặc in-doubt trong distributed transaction. DSL không nhất thiết phải expose tất cả trạng thái nội bộ, nhưng runtime cần xử lý chúng.

### 5.1. Pseudocode của transaction manager

~~~text
executeTransaction(block):
    tx = transactionManager.begin()

    try:
        result = block.execute(context.withTransaction(tx))
        transactionManager.commit(tx)
        return result
    catch error:
        transactionManager.rollback(tx)
        throw error
    finally:
        transactionManager.release(tx)
~~~

Đây là mã giả. Một implementation thực tế cần xử lý lỗi trong commit, lỗi trong rollback, cancellation, timeout và trạng thái không xác định khi kết nối bị ngắt đúng lúc server đang commit.

## 6. Commit và rollback

### 6.1. Commit

Commit là bước yêu cầu hệ thống xác nhận những thay đổi đã thực hiện. Trước khi commit, runtime có thể chạy:

- Kiểm tra invariant nghiệp vụ.
- Kiểm tra constraint.
- Xác thực read/write set.
- Kiểm tra xung đột đồng thời.
- Chuẩn bị ghi log hoặc dữ liệu bền vững.
- Yêu cầu các resource participant xác nhận.

Khi commit thành công, runtime có thể trả kết quả cho caller hoặc phát thông báo theo chính sách đã thiết kế.

### 6.2. Rollback

Rollback hủy các thay đổi chưa commit trong phạm vi tài nguyên hỗ trợ rollback. Ví dụ:

~~~text
transaction {
    createInvoice(order)
    reserveStock(order.items)

    if order.isBlocked {
        rollback
    }
}
~~~

Nếu rollback là lệnh tường minh, DSL cần quy định block kết thúc như thế nào sau lệnh đó: dừng ngay, trả một kết quả đặc biệt hay cho phép nhánh xử lý khác. Không nên để lệnh rollback tiếp tục chạy các thao tác ghi như thể transaction vẫn hoạt động.

### 6.3. Lỗi trong lúc commit

Một trường hợp khó là client gửi yêu cầu commit nhưng mất kết nối trước khi nhận phản hồi. Client không biết transaction đã commit hay chưa. Đây là **kết quả không xác định (in-doubt outcome)**.

Không nên tự động kết luận rằng commit thất bại chỉ vì không nhận được response. Hệ thống có thể cần transaction ID, idempotency key hoặc truy vấn trạng thái để xác định kết quả.

## 7. Isolation và các bất thường đồng thời

Khi nhiều transaction chạy cùng lúc, việc đọc và ghi có thể xen kẽ. Isolation level mô tả mức độ mà các giao dịch được cô lập.

### 7.1. Dirty read

Một transaction đọc dữ liệu do transaction khác ghi nhưng chưa commit. Nếu transaction ghi sau đó rollback, transaction đọc đã sử dụng dữ liệu không bao giờ được xác nhận.

### 7.2. Non-repeatable read

Một transaction đọc cùng một bản ghi hai lần nhưng nhận giá trị khác nhau vì transaction khác đã commit cập nhật ở giữa.

### 7.3. Phantom read

Một transaction chạy lại truy vấn theo điều kiện và nhận thêm hoặc mất các dòng vì transaction khác chèn hoặc xóa dữ liệu phù hợp với điều kiện đó.

### 7.4. Lost update

Hai transaction cùng đọc một giá trị, tính giá trị mới rồi ghi đè nhau. Một cập nhật có thể bị mất nếu không có khóa hoặc kiểm tra version.

Ví dụ:

~~~text
T1 reads balance = 100
T2 reads balance = 100
T1 writes balance = 90
T2 writes balance = 80
~~~

Nếu mục tiêu là trừ 10 và trừ 20, kết quả đúng có thể phải là 70. Ghi đè tuần tự theo dữ liệu cũ tạo kết quả sai.

### 7.5. Write skew

Hai transaction đọc cùng một tập dữ liệu, mỗi transaction cập nhật một bản ghi khác nhau và cả hai cùng thỏa điều kiện dựa trên snapshot cũ. Kết quả kết hợp có thể vi phạm invariant.

Ví dụ, quy tắc yêu cầu luôn có ít nhất một bác sĩ trực. Hai transaction đồng thời kiểm tra người còn lại vẫn trực rồi mỗi transaction tắt lịch trực của chính mình. Nếu không có cơ chế cô lập đủ mạnh, cả hai có thể commit và không còn ai trực.

## 8. Isolation level

Các database thường cung cấp một số mức cô lập. Tên và bảo đảm chính xác có thể khác giữa hệ quản trị.

| Mức | Ý tưởng | Đánh đổi thường gặp |
|---|---|---|
| Read Uncommitted | Có thể đọc dữ liệu chưa commit | Cho phép nhiều bất thường |
| Read Committed | Chỉ đọc dữ liệu đã commit | Cùng một transaction có thể đọc hai giá trị khác nhau |
| Repeatable Read | Bảo vệ việc đọc lặp lại theo định nghĩa của hệ thống | Phantom hoặc write skew có thể còn tùy engine |
| Serializable | Kết quả tương đương một thứ tự chạy tuần tự | Có thể tăng khóa, xung đột hoặc retry |

DSL có thể cho phép chỉ định isolation:

~~~text
transaction isolation serializable {
    let stock = readInventory(productId)
    require stock >= quantity
    decrementInventory(productId, quantity)
}
~~~

Đây là cú pháp minh họa. Runtime cần chuyển lựa chọn này tới resource manager và phải báo nếu backend không hỗ trợ mức yêu cầu. Không nên âm thầm hạ xuống một mức yếu hơn mà không có chính sách rõ ràng.

### 8.1. Serializable

Serializable là mức bảo đảm mạnh: kết quả của các transaction đồng thời tương đương với một thứ tự thực hiện tuần tự nào đó. Cơ chế thực tế có thể dùng locking, serialization validation hoặc phương pháp khác.

### 8.2. Snapshot isolation

Snapshot isolation thường cho transaction đọc một snapshot nhất quán tại một thời điểm. Nó giảm nhiều xung đột đọc nhưng không đồng nghĩa với serializable trong mọi trường hợp; write skew vẫn có thể xảy ra.

### 8.3. Chọn isolation theo invariant

Không nên chọn mức isolation chỉ dựa vào tốc độ. Cần xác định invariant nào phải giữ, loại anomaly nào có thể làm vi phạm nó và database/runtime cung cấp bảo đảm nào. Một số thao tác cần atomic update hoặc constraint ở database thay vì chỉ đọc rồi kiểm tra trong DSL.

## 9. Locking và MVCC

Runtime thường dựa vào database hoặc transaction resource để điều phối truy cập đồng thời.

### 9.1. Pessimistic locking

Pessimistic locking giả định xung đột có thể xảy ra và khóa tài nguyên trước hoặc trong lúc cập nhật.

~~~text
transaction {
    let account = select accountId for update
    require account.balance >= amount
    account.balance = account.balance - amount
}
~~~

Khóa giúp ngăn transaction khác sửa cùng tài nguyên theo cách không tương thích trong thời gian khóa. Tuy nhiên, khóa lâu có thể gây chờ, deadlock và giảm throughput.

### 9.2. Optimistic concurrency control

Optimistic concurrency control cho phép nhiều transaction làm việc mà chưa khóa độc quyền ngay từ đầu. Khi ghi, hệ thống kiểm tra version hoặc read/write set để phát hiện xung đột.

Ví dụ:

~~~text
transaction {
    let account = readAccount(id)
    let newBalance = account.balance - amount
    updateAccount(
        id,
        expectedVersion = account.version,
        balance = newBalance
    )
}
~~~

Nếu version đã thay đổi, update thất bại và transaction có thể được thử lại theo chính sách.

### 9.3. MVCC

Multi-Version Concurrency Control lưu nhiều phiên bản dữ liệu để reader có thể đọc snapshot trong khi writer tạo phiên bản mới. MVCC có thể tăng concurrency, nhưng vẫn cần quy tắc phát hiện xung đột và dọn phiên bản cũ.

DSL thường không cần expose chi tiết MVCC. Tuy nhiên, runtime nên hiểu backend đang dùng cơ chế nào để diễn giải đúng lỗi conflict và retry.

## 10. Deadlock và xử lý xung đột

Deadlock xảy ra khi các transaction giữ tài nguyên và chờ tài nguyên của nhau theo một chu trình.

Ví dụ:

~~~text
T1 locks account A, waits for account B
T2 locks account B, waits for account A
~~~

Database có thể phát hiện deadlock và hủy một transaction làm nạn nhân. Runtime cần phân loại lỗi này để có thể retry toàn bộ transaction nếu thao tác an toàn.

Một số cách giảm nguy cơ:

- Truy cập tài nguyên theo thứ tự thống nhất.
- Giữ transaction ngắn.
- Tránh gọi API bên ngoài khi đang giữ khóa.
- Giới hạn số lượng bản ghi khóa.
- Chọn isolation phù hợp với invariant.
- Retry có giới hạn và có backoff khi gặp lỗi retryable.

Không phải mọi lỗi commit đều là deadlock. Lỗi constraint, quyền truy cập hoặc dữ liệu không hợp lệ thường không được giải quyết bằng cách retry nguyên trạng.

## 11. Transaction lồng nhau và savepoint

DSL có thể cho phép một transaction block nằm trong một block khác:

~~~text
transaction {
    updateCustomer()

    transaction {
        createInvoice()
    }
}
~~~

Tuy nhiên, “nested transaction” có nhiều cách hiểu.

### 11.1. Join transaction cha

Block con tham gia cùng transaction với block cha. Nếu block con thất bại và lỗi được truyền lên, toàn bộ transaction cha có thể rollback. Commit trong block con không thực sự commit độc lập; transaction cha mới quyết định kết quả cuối.

### 11.2. Savepoint

Một số database cho phép tạo savepoint trong transaction. Block con có thể rollback về savepoint mà vẫn giữ những thay đổi trước savepoint trong transaction cha:

~~~text
transaction {
    updateCustomer()

    savepoint "invoice-step"
    try {
        createInvoice()
    } catch InvoiceError {
        rollbackTo "invoice-step"
    }

    updateAuditRecord()
}
~~~

Savepoint không tương đương một transaction độc lập đã commit. Các thay đổi sau savepoint vẫn thuộc transaction cha và có thể bị rollback khi cha thất bại.

### 11.3. Transaction độc lập

Một số hệ thống cho phép block con chạy bằng transaction riêng. Điều này có nghĩa block con có thể commit dù transaction cha rollback. Cần thiết kế rõ vì nó phá vỡ giả định rằng mọi thao tác trong block ngoài cùng cùng thành công hoặc thất bại.

### 11.4. Quy tắc cần công bố

DSL cần xác định:

- Transaction lồng nhau join, tạo savepoint hay độc lập?
- Commit của block con có hiệu lực ngay không?
- Lỗi block con có làm rollback block cha không?
- Có thể rollback tới savepoint nào?
- Isolation level có được kế thừa không?
- Runtime xử lý transaction context khi gọi hàm lồng nhau ra sao?

Nếu không có nhu cầu rõ ràng, hỗ trợ một transaction context duy nhất và savepoint có thể dễ hiểu hơn việc giả lập nested transaction độc lập.

## 12. Exception, lỗi và rollback

Một giao dịch cần quy định lỗi nào làm rollback. Có thể phân loại:

- **Fatal error:** lỗi khiến transaction không thể tiếp tục, ví dụ lỗi constraint hoặc dữ liệu không hợp lệ.
- **Retryable error:** xung đột hoặc lỗi tạm thời có thể thử lại toàn bộ transaction.
- **Business rejection:** điều kiện nghiệp vụ không đạt, có thể trả kết quả từ chối mà không coi là lỗi hệ thống.
- **Recoverable error:** có thể xử lý trong transaction nếu trạng thái vẫn hợp lệ.

Ví dụ:

~~~text
transaction {
    let order = loadOrder(id)

    try {
        reserveStock(order)
    } catch OutOfStock {
        return Rejected("Insufficient inventory")
    }

    confirmOrder(order)
}
~~~

DSL cần định nghĩa return trong transaction có tự commit hay rollback. Nếu block kết thúc bình thường thì commit tự động, return có thể được xem như kết thúc bình thường; nhưng nếu business rejection cần rollback, chương trình phải có cách thể hiện rõ.

Một cách khác:

~~~text
transaction {
    let result = tryReserveStock(order)

    if result is Rejected {
        rollback
        return result
    }

    confirmOrder(order)
}
~~~

Điểm quan trọng là exception handling và transaction handling phải có thứ tự rõ ràng. Bắt lỗi rồi tiếp tục không tự động có nghĩa transaction còn hợp lệ; runtime hoặc database có thể đã đánh dấu transaction là aborted.

## 13. Retry giao dịch

Một số lỗi như serialization conflict hoặc deadlock có thể được giải quyết bằng cách chạy lại toàn bộ transaction.

DSL có thể biểu diễn:

~~~text
transaction retry {
    maxAttempts = 3
    backoff = exponential(100ms, 2s)

    updateInventory(productId, quantity)
    createReservation(orderId)
}
~~~

### 13.1. Vì sao retry toàn bộ block?

Nếu transaction thất bại do dữ liệu đã thay đổi, các giá trị đọc trước đó có thể đã lỗi thời. Chỉ chạy lại câu lệnh cuối có thể không giữ được logic ban đầu. Thường cần chạy lại toàn bộ block để đọc snapshot mới và tính lại quyết định.

### 13.2. Chỉ retry lỗi phù hợp

Nên retry các lỗi được phân loại là tạm thời hoặc conflict. Không nên retry vô hạn các lỗi như:

- Sai kiểu hoặc vi phạm schema.
- Không đủ quyền.
- Dữ liệu đầu vào không hợp lệ.
- Vi phạm invariant nghiệp vụ không thể tự thay đổi.
- Tài nguyên không tồn tại.

### 13.3. Backoff và jitter

Nếu nhiều transaction cùng retry ngay lập tức, chúng có thể tiếp tục xung đột. Exponential backoff tăng thời gian chờ sau mỗi lần thử; jitter thêm độ lệch ngẫu nhiên để giảm việc các client retry đồng bộ.

### 13.4. Giới hạn retry

Runtime cần giới hạn số lần thử và tổng thời gian. Khi hết giới hạn, nó trả lỗi hoặc kết quả phù hợp để ứng dụng chủ quyết định.

## 14. Idempotency và an toàn khi thử lại

Một thao tác **idempotent** là thao tác mà việc thực hiện lặp lại cùng một yêu cầu không tạo thêm hiệu ứng ngoài kết quả đã định. Idempotency đặc biệt quan trọng khi client không biết một yêu cầu đã commit hay chưa.

Ví dụ, API tạo thanh toán có thể nhận một idempotency key:

~~~text
transaction {
    chargePayment(
        orderId = order.id,
        amount = order.total,
        idempotencyKey = request.id
    )
}
~~~

Nếu request được gửi lại do timeout, hệ thống có thể nhận ra key đã xử lý và trả lại kết quả cũ thay vì tạo một khoản thu mới.

### 14.1. Idempotency key

Key nên gắn với một thao tác nghiệp vụ duy nhất, có phạm vi và thời gian lưu giữ được xác định. Nếu cùng key được dùng cho payload khác, hệ thống cần từ chối hoặc có quy tắc rõ ràng.

### 14.2. Không nhầm retry với idempotency

Retry là cơ chế thực hiện lại. Idempotency là thuộc tính hoặc hợp đồng giúp việc lặp lại không nhân đôi hiệu ứng. Retry một thao tác không idempotent có thể tạo bản ghi hoặc side effect trùng lặp.

### 14.3. Transaction ID và trạng thái kết quả

Khi commit outcome không rõ, runtime có thể dùng transaction ID hoặc request ID để truy vấn trạng thái. Hệ thống phải phân biệt transaction chưa bắt đầu, đang xử lý, đã commit, đã rollback và trạng thái không thể xác định.

## 15. Side effect bên ngoài transaction

Database transaction có thể rollback các thay đổi trong database, nhưng không thể tự động hoàn tác mọi side effect bên ngoài.

Ví dụ:

~~~text
transaction {
    createOrder()
    sendEmail("Order created")
    updateInventory()
}
~~~

Nếu sendEmail đã gửi thành công rồi updateInventory thất bại, rollback database không thể thu hồi email đã gửi. Người nhận vẫn nhận được thông báo về một đơn hàng chưa được xác nhận.

### 15.1. Phân loại thao tác

Khi thiết kế DSL, có thể phân loại effect:

- Transactional data operation: được resource transaction quản lý.
- Read-only external operation: đọc dữ liệu từ service bên ngoài.
- Non-transactional side effect: gửi email, gọi webhook hoặc phát message.
- Compensatable operation: có hành động nghiệp vụ ngược để bù trừ.

Runtime có thể dùng effect metadata để cảnh báo khi một block transaction chứa side effect không thể rollback.

### 15.2. Transactional outbox

Một mẫu phổ biến là ghi dữ liệu nghiệp vụ và một bản ghi sự kiện vào cùng database transaction:

~~~text
transaction {
    createOrder(order)
    insertOutboxEvent(
        type = "OrderCreated",
        payload = order.id
    )
}
~~~

Một worker riêng đọc outbox và gửi sự kiện sau khi transaction commit. Nếu gửi thất bại, worker có thể thử lại. Consumer nên xử lý message idempotently vì việc gửi có thể lặp.

Outbox giúp gắn thay đổi dữ liệu với ý định phát sự kiện trong cùng transaction lưu trữ. Nó không tự bảo đảm message chỉ được gửi đúng một lần.

### 15.3. Gửi side effect sau commit

DSL có thể cung cấp hook:

~~~text
transaction {
    createOrder(order)

    afterCommit {
        publish OrderCreated(order.id)
    }
}
~~~

Hook afterCommit chỉ chạy sau khi commit thành công. Tuy nhiên, nếu tiến trình dừng sau commit nhưng trước khi hook chạy, sự kiện có thể bị mất. Với yêu cầu độ tin cậy cao, outbox thường phù hợp hơn callback trong bộ nhớ.

## 16. Giao dịch phân tán

Khi một DSL workflow thao tác với nhiều hệ thống độc lập, một transaction database đơn lẻ không thể tự bảo đảm atomicity xuyên mọi dịch vụ.

Ví dụ:

~~~text
process checkout {
    createOrder()
    reserveWarehouseStock()
    chargePaymentProvider()
    scheduleDelivery()
}
~~~

Các thao tác có thể thuộc database, kho hàng, payment provider và dịch vụ vận chuyển khác nhau. Mỗi hệ thống có transaction manager riêng.

### 16.1. Two-phase commit (2PC)

Two-phase commit phối hợp các participant qua hai pha:

1. **Prepare:** coordinator yêu cầu các participant chuẩn bị commit và giữ trạng thái cần thiết.
2. **Commit/Abort:** nếu tất cả participant sẵn sàng, coordinator yêu cầu commit; nếu không, yêu cầu abort.

~~~mermaid
sequenceDiagram
    participant C as Coordinator
    participant A as Participant A
    participant B as Participant B
    C->>A: Prepare
    C->>B: Prepare
    A-->>C: Ready
    B-->>C: Ready
    C->>A: Commit
    C->>B: Commit
    A-->>C: Committed
    B-->>C: Committed
~~~

2PC có thể cung cấp atomic commit cho các resource participant hỗ trợ protocol, nhưng có chi phí phối hợp và trạng thái chờ. Coordinator hoặc participant gặp sự cố có thể làm giao dịch bị kẹt ở trạng thái in-doubt. Nhiều API bên ngoài không hỗ trợ 2PC.

### 16.2. Saga

Saga chia một quy trình phân tán thành nhiều local transaction. Mỗi bước có thể có một hành động bù trừ (compensation) nếu bước sau thất bại.

Ví dụ:

~~~text
saga "checkout" {
    step createOrder {
        do createOrder()
        compensate cancelOrder()
    }

    step reserveStock {
        do reserveStock()
        compensate releaseStock()
    }

    step chargePayment {
        do chargePayment()
        compensate refundPayment()
    }
}
~~~

Nếu chargePayment thất bại, saga có thể chạy compensation cho reserveStock rồi createOrder theo thứ tự ngược. Compensation là thao tác nghiệp vụ mới, không phải rollback vật lý của transaction đã commit. Nó cũng có thể thất bại và cần retry hoặc xử lý thủ công.

### 16.3. Chọn 2PC hay saga

| Tiêu chí | Two-phase commit | Saga |
|---|---|---|
| Mô hình | Một distributed transaction | Chuỗi local transaction |
| Hoàn tác | Abort trước commit toàn cục | Compensation sau các bước đã commit |
| Participant | Cần hỗ trợ protocol | Có thể là các service độc lập |
| Trạng thái trung gian | Có thể bị giữ trong thời gian prepare | Có trạng thái nghiệp vụ từng bước |
| Phù hợp | Các resource phối hợp được | Workflow dài và hệ thống phân tán |

DSL cần biểu diễn đúng mức bảo đảm. Không nên gọi một saga là transaction ACID nếu các bước đã commit riêng và chỉ được bù trừ sau đó.

## 17. Transaction trong workflow dài

Một workflow có thể chạy trong vài phút hoặc vài ngày. Giữ một database transaction mở suốt thời gian đó thường không phù hợp vì khóa và snapshot bị giữ lâu, tài nguyên bị chiếm và lỗi mạng có thể làm trạng thái khó phục hồi.

Thay vào đó, workflow dài thường dùng:

- Local transaction ngắn cho từng bước.
- Lưu trạng thái tiến trình bền vững.
- Event hoặc message để tiếp tục bước sau.
- Retry có giới hạn.
- Timeout và cancellation.
- Compensation cho bước đã hoàn thành.
- Idempotency cho thao tác có thể lặp.

Ví dụ:

~~~text
workflow "onboard-customer" {
    step createProfile {
        transaction {
            saveProfile(customer)
        }
    }

    step verifyIdentity {
        call identityProvider()
    }

    step activateAccount {
        transaction {
            activate(customer)
        }
    }
}
~~~

Ở đây mỗi transaction ngắn bảo vệ một nhóm cập nhật cục bộ. Toàn bộ workflow được điều phối bởi state machine hoặc saga, thay vì giữ một transaction database mở qua mọi bước.

## 18. Truyền transaction context qua các lời gọi

Một hàm DSL có thể gọi hàm khác:

~~~text
transaction {
    confirmOrder(orderId)
}

function confirmOrder(id) {
    reserveStock(id)
    updateStatus(id, "CONFIRMED")
}
~~~

Runtime cần quyết định các lời gọi bên trong có tự động tham gia transaction hiện tại hay không.

### 18.1. Context propagation

Transaction context có thể được truyền ngầm qua execution context hoặc truyền tường minh qua tham số. Truyền ngầm giúp cú pháp gọn nhưng cần bảo đảm context không bị mất qua async boundary, callback hoặc task mới.

### 18.2. Async execution

Nếu DSL cho phép:

~~~text
transaction {
    await reserveStock(order)
    await updateOrder(order)
}
~~~

Runtime phải xác định transaction có tồn tại qua thời gian await không, connection có được giữ không và cancellation xử lý thế nào. Một số resource không cho phép dùng cùng transaction context đồng thời từ nhiều task.

### 18.3. Task con

Nếu block transaction tạo nhiều task song song, cần quy định:

- Các task có dùng chung transaction không?
- Có được phép ghi đồng thời trên cùng connection không?
- Khi một task lỗi, các task khác bị hủy hay tiếp tục?
- Commit chỉ diễn ra sau khi tất cả task hoàn tất hay không?

Không nên tự động chia sẻ transaction context cho các task song song nếu resource manager không hỗ trợ cách dùng đó.

## 19. Read-only transaction

Một transaction chỉ đọc có thể bảo đảm các lần đọc nhất quán theo snapshot hoặc isolation level được chọn mà không thực hiện cập nhật.

Ví dụ:

~~~text
transaction readOnly isolation repeatableRead {
    let account = loadAccount(id)
    let transactions = loadTransactions(id)
    return buildStatement(account, transactions)
}
~~~

Read-only transaction có thể giúp:

- Tạo báo cáo nhất quán từ nhiều truy vấn.
- Ngăn accidental write.
- Cho database tối ưu cách thực thi.
- Tách quyền đọc và quyền ghi.

Read-only không có nghĩa kết quả không thay đổi theo thời gian giữa các transaction. Nó chỉ quy định cách transaction hiện tại đọc dữ liệu và có thể phụ thuộc isolation được hỗ trợ.

## 20. Timeout, cancellation và giới hạn giao dịch

Giao dịch có thể chờ khóa, gọi service hoặc thực hiện nhiều thao tác. Runtime cần giới hạn thời gian và tài nguyên:

~~~text
transaction timeout 5s {
    reserveInventory(order)
    updateOrder(order)
}
~~~

Khi timeout:

- Runtime yêu cầu hủy thao tác đang chạy nếu có thể.
- Transaction được rollback nếu còn khả năng.
- Tài nguyên và khóa được giải phóng.
- Caller nhận timeout error hoặc trạng thái phù hợp.

Cancellation phức tạp hơn việc dừng một luồng thực thi. Một lời gọi external service có thể đã hoàn thành dù caller hủy request. Vì vậy, runtime cần định nghĩa cancellation propagation và xử lý kết quả không xác định.

Các giới hạn khác có thể gồm:

- Số lượng câu lệnh hoặc record được xử lý.
- Số lần gọi service.
- Kích thước read/write set.
- Số lượng lock.
- Bộ nhớ tạm.
- Số lần retry.

## 21. Giao dịch và hiệu ứng trong ngữ nghĩa DSL

DSL có thể mô hình hóa thao tác theo effect để xác định hành động nào được phép trong transaction.

Ví dụ:

~~~text
effect ReadDatabase
effect WriteDatabase
effect SendMessage
effect ExternalCall
~~~

Một block transaction database có thể chỉ cho phép ReadDatabase và WriteDatabase. SendMessage hoặc ExternalCall cần được đưa vào afterCommit hoặc xử lý qua outbox/saga.

Một khai báo hàm có thể ghi effect:

~~~text
function updateOrder(order): Order
    effects { ReadDatabase, WriteDatabase }
~~~

Compiler có thể kiểm tra hàm được gọi trong transaction có effect tương thích hay không. Cơ chế này giúp phát hiện sớm việc một block được cho là atomic nhưng lại chứa side effect không thể rollback.

Effect system là một lựa chọn thiết kế, không bắt buộc cho mọi DSL. Với ngôn ngữ nhỏ, có thể dùng metadata hoặc quy tắc runtime đơn giản hơn.

## 22. Diagnostics cho giao dịch

Thông báo lỗi cần chỉ ra giao dịch thất bại ở đâu và loại vấn đề nào xảy ra.

Ví dụ lỗi constraint:

~~~text
orders.dsl:18:5
Transaction rejected: order total must be greater than zero.
No changes were committed.
~~~

Ví dụ lỗi isolation conflict:

~~~text
Transaction conflict while updating account 42.
The record changed after it was read.
Retry the whole transaction if the operation is safe to repeat.
~~~

Ví dụ side effect không được phép:

~~~text
workflow.dsl:12:9
Sending an external message inside this database transaction
is not rollback-safe.
Move the operation to afterCommit or use an outbox event.
~~~

Ví dụ timeout:

~~~text
Transaction exceeded its 5-second deadline.
The runtime requested rollback; external operations may need
their own cancellation or compensation handling.
~~~

Diagnostics tốt nên phân biệt:

- Lỗi trong logic nghiệp vụ.
- Vi phạm constraint.
- Xung đột concurrency.
- Deadlock hoặc timeout.
- Lỗi kết nối resource.
- Lỗi commit có kết quả chưa xác định.
- Side effect không tương thích với transaction.

## 23. Kiểm thử giao dịch

Kiểm thử transaction cần xác nhận cả kết quả thành công lẫn hành vi khi thất bại.

### 23.1. Kiểm thử commit

- Các thao tác hợp lệ được commit.
- Dữ liệu sau commit phản ánh toàn bộ thay đổi.
- Kết quả trả về phù hợp.
- Event hoặc outbox record được ghi đúng.

### 23.2. Kiểm thử rollback

- Lỗi giữa các thao tác làm rollback các thay đổi được quản lý.
- Constraint failure không để lại dữ liệu một phần.
- Exception được truyền theo hợp đồng.
- Tài nguyên và khóa được giải phóng.

### 23.3. Kiểm thử isolation

- Hai transaction cập nhật cùng bản ghi.
- Kiểm tra lost update và conflict.
- Kiểm tra snapshot hoặc repeatable read theo mức hỗ trợ.
- Kiểm tra invariant dưới tải đồng thời.

### 23.4. Kiểm thử retry và idempotency

- Retry chỉ xảy ra với lỗi được phân loại retryable.
- Số lần retry và backoff tuân theo cấu hình.
- Request lặp với cùng idempotency key không tạo side effect trùng.
- Kết quả commit không xác định được xử lý qua transaction/request ID.

### 23.5. Kiểm thử distributed workflow

- Compensation chạy theo thứ tự đã định.
- Compensation có thể retry.
- Workflow có thể phục hồi sau khi process khởi động lại.
- Message gửi lặp không làm nhân đôi hiệu ứng.
- Trạng thái saga phản ánh đúng bước đã hoàn thành.

### 23.6. Kiểm thử lỗi bất ngờ

Mô phỏng mất kết nối trước, trong và sau commit; runtime dừng giữa hai thao tác; participant không phản hồi; timeout khi đang giữ khóa. Những trường hợp này giúp xác nhận hệ thống không đưa ra cam kết sai về kết quả transaction.

## 24. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Coi transaction block là ACID mặc định | Runtime có thể không bảo đảm atomicity hoặc durability | Công bố resource và mức bảo đảm thực tế |
| Giữ transaction quá lâu | Khóa và snapshot bị giữ, tăng xung đột | Giữ transaction ngắn và tách workflow dài |
| Gọi API ngoài trong transaction rồi mong rollback | Side effect đã xảy ra không thể tự hoàn tác | Dùng outbox, afterCommit hoặc saga |
| Retry mọi exception | Lặp lại lỗi không thể khắc phục và side effect | Phân loại retryable error |
| Retry thao tác không idempotent | Có thể tạo thanh toán hoặc message trùng | Idempotency key và kiểm tra trạng thái |
| Cho rằng nested transaction luôn độc lập | Commit con có thể không có hiệu lực độc lập | Định nghĩa join, savepoint hoặc independent transaction |
| Không xác định hành vi khi return | Transaction có thể commit/rollback ngoài dự kiến | Đặc tả mọi đường thoát khỏi block |
| Hạ isolation âm thầm | Invariant có thể bị vi phạm | Kiểm tra khả năng backend và báo rõ |
| Chỉ kiểm tra lỗi trước commit | Constraint hoặc conflict vẫn có thể xuất hiện khi commit | Xử lý lỗi commit và outcome không xác định |
| Chạy task song song dùng chung transaction không an toàn | Race hoặc lỗi connection | Định nghĩa context propagation và concurrency |
| Gửi event trước commit | Consumer có thể thấy dữ liệu chưa tồn tại | Ghi outbox hoặc phát sau commit |
| Gọi saga compensation là rollback | Người dùng hiểu sai mức bảo đảm | Mô tả compensation là hành động nghiệp vụ bù trừ |

## 25. Quy trình thiết kế giao dịch cho DSL

Khi thêm transaction vào DSL, có thể đi theo các bước:

1. **Xác định loại trạng thái:** database, object trong bộ nhớ, file, service hoặc workflow.
2. **Xác định invariant:** những điều kiện nào phải đúng trước và sau mỗi đơn vị công việc?
3. **Chọn ranh giới:** thao tác nào phải commit hoặc rollback cùng nhau?
4. **Chọn mô hình commit:** tự động hay tường minh; xử lý return và exception ra sao?
5. **Xác định resource participant:** những tài nguyên nào thực sự hỗ trợ transaction?
6. **Chọn isolation:** cần bảo vệ trước anomaly nào và backend hỗ trợ mức nào?
7. **Quy định nested transaction:** join, savepoint hay transaction độc lập.
8. **Phân loại effect:** thao tác nào rollback được, thao tác nào cần outbox hoặc compensation?
9. **Thiết kế retry:** lỗi nào được thử lại, số lần, backoff và idempotency ra sao?
10. **Thiết kế distributed workflow:** dùng 2PC khi participant hỗ trợ hoặc saga cho quy trình nhiều service.
11. **Định nghĩa context propagation:** transaction đi qua lời gọi hàm, async và task con như thế nào?
12. **Thiết kế diagnostics và quan sát:** transaction ID, trạng thái, lỗi và trace được ghi nhận ra sao?
13. **Kiểm thử failure mode:** commit, rollback, conflict, timeout, crash và kết quả không xác định.

Một đặc tả transaction cần nói rõ bảo đảm nào do DSL, runtime, database và service bên ngoài cung cấp. Nếu không có ranh giới này, người dùng có thể tưởng một block transaction bảo vệ cả những side effect mà runtime không thể kiểm soát.

## 26. Tiêu chí của cơ chế giao dịch tốt

Một cơ chế giao dịch tốt giúp người viết DSL xác định rõ đơn vị công việc, hiểu điều gì được commit, điều gì được rollback và cách hệ thống phản ứng khi nhiều lần thực thi xảy ra đồng thời. Runtime phải thực thi hợp đồng đó nhất quán, quản lý lỗi và tài nguyên, đồng thời phân biệt transaction cục bộ với quy trình phân tán.

Các câu hỏi quan trọng:

- Ranh giới giao dịch được xác định bằng block, câu lệnh hay context?
- Kết thúc bình thường, return, exception và cancellation ảnh hưởng transaction thế nào?
- Những resource nào tham gia atomic commit?
- Isolation level nào được hỗ trợ và có anomaly nào còn tồn tại?
- Nested block join transaction cha hay dùng savepoint?
- Side effect bên ngoài được xử lý bằng outbox, afterCommit hay saga?
- Retry có giới hạn và idempotency được thiết kế ra sao?
- Transaction context được truyền qua lời gọi và async boundary thế nào?
- Commit timeout hoặc mất kết nối được biểu diễn như kết quả nào?
- Diagnostics có đủ thông tin để xác định transaction và nguyên nhân thất bại không?

Giao dịch là cơ chế giúp DSL mô tả những thay đổi trạng thái cần được quản lý như một đơn vị. Khi ranh giới, ACID, isolation, commit/rollback, retry và side effect được đặc tả rõ, runtime có thể thực thi các thao tác nghiệp vụ đáng tin cậy hơn. Với quy trình phân tán hoặc kéo dài, DSL cần dùng mô hình điều phối như outbox và saga thay vì hứa hẹn một transaction nguyên tử vượt quá khả năng của các hệ thống tham gia.
