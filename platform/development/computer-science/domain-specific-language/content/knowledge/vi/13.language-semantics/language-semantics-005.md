# Ý nghĩa của cấu trúc

Trong một ngôn ngữ chuyên biệt theo miền (Domain-Specific Language — DSL), mỗi cấu trúc cú pháp đều cần có ý nghĩa xác định. Một từ khóa, khai báo, biểu thức, câu lệnh hay khối lệnh không chỉ là một chuỗi ký tự hợp lệ; nó phải biểu đạt một khái niệm, một giá trị, một quyết định hoặc một hành động trong miền mà DSL phục vụ. Phần quy định những ý nghĩa đó được gọi là **ngữ nghĩa (semantics)**.

Hiểu ý nghĩa của cấu trúc giúp người thiết kế DSL tránh tình trạng cú pháp đọc có vẻ rõ ràng nhưng khi thực thi lại cho kết quả khó đoán. Nó cũng giúp người viết biết một cấu trúc tác động lên dữ liệu nào, trong phạm vi nào, theo thứ tự nào và với những giới hạn gì.

## 1. Cấu trúc cú pháp và ý nghĩa của nó

Cấu trúc cú pháp (syntax structure) mô tả cách các thành phần của DSL được ghép lại thành một chương trình hợp lệ. Ngữ nghĩa trả lời câu hỏi: **cấu trúc hợp lệ đó có nghĩa gì?**

Ví dụ, DSL có thể cho phép khai báo:

```text
entity Customer {
    name: String
    email: EmailAddress
}
```

Cú pháp cho biết có một khai báo `entity`, tên `Customer`, và hai thuộc tính nằm trong khối. Nhưng để chương trình hiểu được khai báo này, ngôn ngữ phải định nghĩa thêm:

- `entity` tạo ra khái niệm gì trong mô hình miền?
- `Customer` có trở thành một kiểu dữ liệu có thể tham chiếu ở nơi khác không?
- `name` và `email` là thuộc tính bắt buộc hay tùy chọn?
- Kiểu `EmailAddress` được định nghĩa ở đâu và giá trị nào hợp lệ?
- Hai tên thuộc tính có phải duy nhất trong entity không?
- Khai báo này chỉ mô tả cấu trúc dữ liệu hay còn tạo ra bảng lưu trữ?

Những câu trả lời này thuộc ngữ nghĩa và các quy tắc tĩnh của DSL. Chúng phải được đặc tả rõ thay vì để mỗi công cụ tự suy diễn.

### 1.1. Cú pháp hợp lệ chưa chắc có ý nghĩa hợp lệ

Xét biểu thức:

```text
order.total >= 1_000_000
```

Parser có thể xác nhận biểu thức có dạng một phép so sánh giữa truy cập thuộc tính và literal số. Tuy nhiên, biểu thức chỉ có ý nghĩa nếu `order` được xác định, `total` tồn tại trên kiểu của `order`, và kiểu của `total` có thể so sánh với giá trị bên phải theo quy tắc DSL.

Ngược lại, biểu thức:

```text
order.deliveryDate >= 1_000_000
```

có thể đúng cú pháp nhưng sai ngữ nghĩa nếu `deliveryDate` là ngày và DSL không định nghĩa phép so sánh ngày với số nguyên.

Vì vậy, cần phân biệt ít nhất hai câu hỏi:

1. **Có phân tích cú pháp được không?** Các token có tạo thành cấu trúc được ngữ pháp cho phép không?
2. **Có ý nghĩa hợp lệ không?** Tên, kiểu, phạm vi và quy tắc miền có cho phép cấu trúc đó không?

## 2. Ngữ nghĩa mô tả điều gì?

Ngữ nghĩa của một cấu trúc có thể quy định nhiều khía cạnh khác nhau:

- **Đối tượng được mô tả:** cấu trúc nói về entity, thuộc tính, sự kiện, quy tắc, truy vấn hay quy trình nào.
- **Giá trị tạo ra:** biểu thức trả về Boolean, số tiền, ngày giờ, chuỗi hoặc một giá trị miền khác.
- **Tác động:** câu lệnh có thay đổi trạng thái, tạo bản ghi, gửi thông báo hay gọi một dịch vụ không.
- **Phạm vi:** tên và biến nào có thể được sử dụng trong cấu trúc.
- **Thứ tự:** các phần được đánh giá theo thứ tự nào; có nhánh, lặp hoặc short-circuit không.
- **Điều kiện hợp lệ:** kiểu, miền giá trị, quyền và ràng buộc nào phải được thỏa mãn.
- **Lỗi:** điều gì xảy ra khi dữ liệu thiếu, tham chiếu không tồn tại hoặc thao tác thất bại.
- **Vòng đời:** cấu trúc có hiệu lực khi biên dịch, khi chạy, trong một giao dịch hay trong một khoảng thời gian nào.

Không phải cấu trúc nào cũng cần tất cả các khía cạnh trên. Nhưng những khía cạnh có ảnh hưởng đến kết quả phải được định nghĩa đủ rõ để người dùng và công cụ hiểu giống nhau.

## 3. Ý nghĩa của các loại cấu trúc thường gặp

Các DSL khác nhau có thể dùng từ khóa khác nhau, nhưng nhiều ngôn ngữ có những nhóm cấu trúc tương tự.

### 3.1. Khai báo (declaration)

Khai báo giới thiệu một tên hoặc một thành phần mới vào mô hình của DSL. Ví dụ:

```text
entity Order {
    orderId: OrderId
    total: Money
}
```

Ngữ nghĩa của khai báo `entity` có thể quy định rằng:

- `Order` là một kiểu hoặc khái niệm miền.
- Các thuộc tính `orderId` và `total` thuộc về kiểu đó.
- Tên thuộc tính phải duy nhất trong phạm vi entity.
- Kiểu của thuộc tính phải được định nghĩa hoặc có thể phân giải.
- Một entity có thể được tham chiếu từ rule, query hoặc workflow.

Khai báo thường ảnh hưởng đến symbol table, schema hoặc mô hình miền. Nó không nhất thiết tạo ra một bản ghi dữ liệu ngay khi chương trình được phân tích.

### 3.2. Biểu thức (expression)

Biểu thức là cấu trúc được đánh giá để tạo ra một giá trị hoặc kết quả. Ví dụ:

```text
order.total * 0.1
order.status == PAID
customer.region in ["north", "central"]
```

Ngữ nghĩa cần xác định kiểu kết quả, quy tắc đánh giá toán tử, thứ tự tính toán và cách xử lý dữ liệu thiếu. Ví dụ, `order.status == PAID` có thể trả về Boolean; nếu `status` chưa có giá trị, DSL cần quy định kết quả là `false`, `unknown` hay lỗi.

### 3.3. Câu lệnh hoặc hành động (statement/action)

Câu lệnh thường mô tả một hành động hoặc thay đổi trạng thái:

```text
shipping.fee = 0
notifyCustomer(order)
reserveInventory(order.lines)
```

Ngữ nghĩa cần quy định hành động tác động đến đối tượng nào, có được phép thực hiện trong ngữ cảnh hiện tại không, có tạo tác dụng phụ không, và lỗi được xử lý ra sao. Một phép gán có thể cập nhật trạng thái trong bộ nhớ, ghi dữ liệu xuống kho lưu trữ hoặc chỉ xây dựng một mô tả hành động để thực thi sau; các cách này có ý nghĩa rất khác nhau.

### 3.4. Khối lệnh (block)

Khối lệnh nhóm nhiều cấu trúc thành một đơn vị:

```text
if order.isPaid {
    reserveInventory(order)
    createShipment(order)
}
```

Khối có thể xác định phạm vi tên, thứ tự thực hiện, giới hạn của một giao dịch hoặc đơn vị xử lý. DSL cần nói rõ các câu lệnh trong khối chạy tuần tự hay có thể chạy song song, và điều gì xảy ra nếu một câu lệnh thất bại.

### 3.5. Quy tắc (rule)

Rule thường kết hợp điều kiện với hành động:

```text
rule freeShipping {
    when order.total >= 1_000_000
    then shipping.fee = 0
}
```

Ngữ nghĩa phải xác định rule được đánh giá lúc nào, điều kiện được đọc từ trạng thái nào, hành động có được thực hiện ngay không, rule có thể chạy nhiều lần không và cách xử lý khi nhiều rule cùng phù hợp.

### 3.6. Truy vấn (query)

Query mô tả dữ liệu cần lấy hoặc biến đổi:

```text
query highValueOrders {
    from Order
    where total >= 1_000_000
    select orderId, total
}
```

Ngữ nghĩa cần xác định nguồn dữ liệu, cách lọc, thứ tự, phép chiếu, xử lý giá trị thiếu và việc truy vấn có tác dụng phụ hay không. Một query có thể khai báo kết quả mong muốn để bộ máy tự chọn kế hoạch thực thi.

### 3.7. Workflow hoặc quy trình

Workflow mô tả các bước và quan hệ chuyển tiếp:

```text
workflow fulfillOrder {
    step validateOrder
    step checkPayment
    step prepareShipment
    step dispatchShipment
}
```

Ngữ nghĩa phải làm rõ các bước chạy tuần tự hay theo điều kiện, cách lưu trạng thái giữa các bước, hành vi retry, timeout, bù trừ và khôi phục khi một bước thất bại.

## 4. Ngữ nghĩa tĩnh và ngữ nghĩa động

Một cấu trúc có thể được kiểm tra trước khi chạy và cũng có ý nghĩa khi thực thi. Hai khía cạnh này thường được gọi là ngữ nghĩa tĩnh và ngữ nghĩa động.

### 4.1. Ngữ nghĩa tĩnh (static semantics)

Ngữ nghĩa tĩnh quy định những điều kiện mà chương trình phải thỏa mãn trước khi được chấp nhận hoặc thực thi. Ví dụ:

- Tên phải được khai báo trước khi tham chiếu theo quy tắc scope.
- Thuộc tính phải tồn tại trên kiểu đối tượng.
- Điều kiện của `when` phải có kiểu Boolean.
- Phép cộng tiền chỉ hợp lệ với kiểu và đơn vị phù hợp.
- Một hành động phải được cho phép trong loại rule hiện tại.
- Giá trị literal phải nằm trong miền hợp lệ.

Ví dụ:

```text
when order.total >= "one million"
```

Biểu thức có thể đúng cú pháp, nhưng sai ngữ nghĩa tĩnh nếu `total` là `Money` còn vế phải là `String` và DSL không có phép so sánh tương ứng.

### 4.2. Ngữ nghĩa động (dynamic semantics)

Ngữ nghĩa động mô tả điều xảy ra khi cấu trúc được đánh giá hoặc thực thi. Ví dụ, với:

```text
if order.isPaid {
    createShipment(order)
}
```

Ngữ nghĩa động có thể quy định:

1. Đánh giá `order.isPaid` trong trạng thái hiện tại.
2. Nếu kết quả là `true`, thực hiện `createShipment(order)`.
3. Nếu kết quả là `false`, bỏ qua khối lệnh.
4. Nếu giá trị chưa xác định hoặc truy cập dữ liệu lỗi, xử lý theo chính sách đã định.

Ngữ nghĩa tĩnh và động bổ sung cho nhau. Kiểm tra tĩnh giúp phát hiện lỗi trước khi chạy; ngữ nghĩa động quyết định hành vi thực tế của chương trình.

## 5. Ngữ cảnh và môi trường khi diễn giải cấu trúc

Ý nghĩa của một cấu trúc thường phụ thuộc vào ngữ cảnh. Cùng tên `status` có thể chỉ trạng thái đơn hàng, thanh toán hoặc vận chuyển tùy đối tượng và phạm vi.

### 5.1. Scope và name resolution

Scope xác định tên nào có thể được tham chiếu tại một vị trí. Ví dụ:

```text
entity Order {
    status: OrderStatus
}

entity Payment {
    status: PaymentStatus
}
```

Trong `order.status`, tên `status` được hiểu theo kiểu `Order`; trong `payment.status`, nó được hiểu theo kiểu `Payment`. Ngữ nghĩa truy cập thuộc tính cần dựa trên kiểu của đối tượng, không chỉ dựa vào tên cuối cùng.

Nếu DSL hỗ trợ biến cục bộ, tham số, alias hoặc import, cần xác định quy tắc phân giải tên và xử lý xung đột. Một tên được khai báo ở scope gần hơn có che khuất tên ở scope bên ngoài hay không cũng phải được quy định.

### 5.2. Environment và runtime state

Khi đánh giá biểu thức, interpreter thường cần một môi trường ánh xạ tên đến giá trị hoặc symbol. Khi thực hiện hành động, nó còn cần trạng thái của miền tại thời điểm chạy.

Có thể phân biệt:

- **Environment (môi trường):** ánh xạ tên biến hoặc symbol đến giá trị, kiểu hoặc đối tượng mà nó đại diện.
- **Store/state (trạng thái):** dữ liệu có thể thay đổi trong quá trình thực thi, chẳng hạn trạng thái đơn hàng, số lượng tồn kho hoặc phí vận chuyển.
- **Context (ngữ cảnh):** thông tin bổ sung như người dùng hiện tại, thời điểm, tenant, quyền hạn hoặc giao dịch.

Ý nghĩa của `order.total` phụ thuộc vào đối tượng `order` trong environment; giá trị nó trả về phụ thuộc trạng thái đơn hàng; khả năng đọc hoặc sửa thuộc tính có thể phụ thuộc context và quyền.

### 5.3. Scope không đồng nghĩa với vòng đời dữ liệu

Một biến có thể nằm trong scope của một rule nhưng giá trị mà nó tham chiếu được lấy từ trạng thái hệ thống tại một thời điểm khác. DSL cần xác định dữ liệu được chụp tại lúc khai báo, lúc đánh giá hay lúc thực thi hành động.

Điều này đặc biệt quan trọng với rule trì hoãn, workflow chạy lâu hoặc callback được lưu để thực thi sau. Nếu giá trị có thể thay đổi giữa lúc khai báo và lúc chạy, kết quả phụ thuộc vào semantics snapshot hay semantics đọc trạng thái hiện tại.

## 6. Cách đặc tả ý nghĩa của cấu trúc

Có nhiều phương pháp mô tả semantics. Một dự án DSL có thể kết hợp chúng tùy mức độ phức tạp và yêu cầu kiểm chứng.

### 6.1. Mô tả bằng ngôn ngữ tự nhiên có cấu trúc

Với DSL nhỏ, có thể mô tả mỗi cấu trúc bằng mẫu thống nhất:

| Mục | Nội dung cần định nghĩa |
|---|---|
| Cấu trúc | Tên và dạng cú pháp |
| Mục đích | Khái niệm hoặc tác vụ miền mà cấu trúc biểu đạt |
| Điều kiện hợp lệ | Kiểu, tên, phạm vi và ràng buộc cần thỏa mãn |
| Đầu vào | Dữ liệu hoặc ngữ cảnh được sử dụng |
| Kết quả | Giá trị, trạng thái hoặc cấu trúc được tạo ra |
| Tác dụng phụ | Thay đổi dữ liệu, gọi dịch vụ hoặc ghi log nếu có |
| Thứ tự | Cách đánh giá các phần và tương tác với cấu trúc khác |
| Lỗi | Điều kiện lỗi và cách xử lý |

Ví dụ, đặc tả `when` có thể nói: “Biểu thức sau `when` phải có kiểu Boolean. Khi rule được đánh giá, điều kiện được tính trong context của đối tượng đang xét. Nếu kết quả là true, phần action được chọn để thực thi theo chính sách của rule engine.”

### 6.2. Ngữ nghĩa vận hành (operational semantics)

Ngữ nghĩa vận hành mô tả ý nghĩa bằng các bước thực hiện hoặc chuyển trạng thái. Nó phù hợp khi cần diễn tả rõ trình tự đánh giá.

Ví dụ với cấu trúc điều kiện:

```text
if condition {
    actionA
} else {
    actionB
}
```

Có thể mô tả:

1. Đánh giá `condition` trong môi trường hiện tại.
2. Nếu kết quả là `true`, chuyển sang thực hiện `actionA`.
3. Nếu kết quả là `false`, chuyển sang thực hiện `actionB`.
4. Nếu điều kiện không tạo ra Boolean hợp lệ, phát sinh lỗi theo quy tắc runtime.

Với workflow hoặc rule engine, có thể mô tả semantics bằng hệ chuyển trạng thái (state transition system): mỗi bước nhận trạng thái hiện tại và tạo trạng thái tiếp theo.

### 6.3. Ngữ nghĩa biểu thị (denotational semantics)

Ngữ nghĩa biểu thị gán cho mỗi cấu trúc một ý nghĩa toán học hoặc một hàm từ đầu vào đến kết quả. Ví dụ, một biểu thức Boolean có thể được hiểu là hàm từ environment sang giá trị Boolean:

\[
\llbracket e \rrbracket : Environment \rightarrow Boolean
\]

Với biểu thức số:

\[
\llbracket e \rrbracket : Environment \rightarrow Number
\]

Ký hiệu `⟦e⟧` được đọc là “ý nghĩa của biểu thức e”. Cách biểu diễn này giúp phân biệt văn bản cú pháp với giá trị mà cấu trúc biểu đạt. Với cấu trúc có tác dụng phụ, miền kết quả có thể bao gồm cả trạng thái mới hoặc hiệu ứng.

### 6.4. Ngữ nghĩa tiên đề (axiomatic semantics)

Ngữ nghĩa tiên đề mô tả các điều kiện trước và sau khi một cấu trúc chạy, thường dùng logic và các quy tắc suy luận. Một dạng ký hiệu là Hoare triple:

\[
\{P\}\ C\ \{Q\}
\]

Trong đó `P` là điều kiện trước, `C` là câu lệnh hoặc chương trình, và `Q` là điều kiện sau. Ví dụ:

```text
{ balance >= 100 }
withdraw(100)
{ balance_after = balance_before - 100 }
```

Cách đặc tả này hữu ích khi DSL mô tả hành động có ràng buộc quan trọng, như giao dịch, phân quyền hoặc xử lý dữ liệu. Nó giúp làm rõ điều kiện nào phải đúng trước và điều gì được bảo đảm sau khi thực hiện.

## 7. Ví dụ: xác định ý nghĩa của một rule

Giả sử DSL mô tả chính sách miễn phí vận chuyển:

```text
rule freeShipping {
    when order.total >= 1_000_000
         and order.status == PAID
    then shipping.fee = 0
}
```

Để cấu trúc này có ý nghĩa đầy đủ, đặc tả cần giải thích các phần.

| Thành phần | Ý nghĩa |
|---|---|
| `rule freeShipping` | Khai báo một quy tắc có tên `freeShipping` trong phạm vi module hoặc rule set |
| `when` | Bắt đầu biểu thức điều kiện; biểu thức phải trả về Boolean |
| `order.total >= 1_000_000` | So sánh tổng giá trị đơn hàng với ngưỡng một triệu theo đơn vị tiền tệ đã xác định |
| `and` | Cả hai điều kiện phải đúng; quy tắc đánh giá vế theo thứ tự và short-circuit nếu DSL quy định |
| `order.status == PAID` | Kiểm tra trạng thái đơn hàng bằng giá trị enum `PAID` |
| `then` | Bắt đầu hành động được thực hiện khi điều kiện thỏa mãn |
| `shipping.fee = 0` | Gán phí vận chuyển thành 0 trong đối tượng/context vận chuyển của đơn hàng |

Vẫn còn các quyết định ngữ nghĩa cần nêu rõ:

- `order.total` là tổng trước thuế, sau thuế hay sau chiết khấu?
- `1_000_000` được hiểu là VND hay lấy currency từ đơn hàng?
- Rule được đánh giá một lần khi tạo đơn hay mỗi lần trạng thái thay đổi?
- Nếu phí vận chuyển đã được tính hoặc đã thanh toán, hành động gán 0 có được phép không?
- Nếu nhiều rule cùng thay đổi `shipping.fee`, rule nào được ưu tiên?
- Hành động có được lưu cùng giao dịch với thay đổi trạng thái đơn hàng không?

Những câu hỏi này cho thấy ngữ nghĩa không chỉ là giải thích từ khóa. Nó còn xác định tác động của cấu trúc trong mô hình và vòng đời thực tế của miền.

## 8. Ý nghĩa của thứ tự đánh giá

Khi một cấu trúc có nhiều phần con, DSL cần quy định phần nào được đánh giá trước và phần nào có thể bị bỏ qua.

### 8.1. Thứ tự toán tử

Biểu thức:

```text
A or B and C
```

có thể được hiểu là `A or (B and C)` nếu `and` có precedence cao hơn `or`. Nếu DSL không quy định precedence, người dùng có thể hiểu khác nhau. Có thể yêu cầu ngoặc hoặc công bố bảng thứ tự ưu tiên.

### 8.2. Short-circuit

Với biểu thức `A and B`, DSL có thể quy định không đánh giá `B` nếu `A` đã false. Với `A or B`, có thể không đánh giá `B` nếu `A` đã true.

Short-circuit ảnh hưởng đến tác dụng phụ và lỗi. Nếu `B` gọi dịch vụ hoặc truy cập dữ liệu có thể lỗi, việc có đánh giá nó hay không tạo ra khác biệt quan sát được.

### 8.3. Thứ tự câu lệnh trong block

Trong một block tuần tự, câu lệnh sau thường quan sát được thay đổi của câu lệnh trước. Nếu DSL cho phép thực thi song song, cần xác định quan hệ phụ thuộc và cách xử lý xung đột.

### 8.4. Thứ tự khai báo rule

Nếu nhiều rule cùng phù hợp, có thể dùng thứ tự khai báo, độ ưu tiên, nhóm hoặc cơ chế giải quyết xung đột. Cách nào cũng được, miễn là được định nghĩa và không phụ thuộc vào thứ tự duyệt không ổn định của một cấu trúc dữ liệu nội bộ.

## 9. Ý nghĩa của kiểu dữ liệu và giá trị

Kiểu dữ liệu không chỉ giới hạn hình thức lưu trữ; nó ảnh hưởng đến những phép toán và cấu trúc nào có ý nghĩa.

### 9.1. Kiểu quyết định phép toán hợp lệ

Ví dụ:

| Biểu thức | Ý nghĩa có thể có |
|---|---|
| `Money + Money` | Cộng hai khoản tiền tương thích về currency |
| `Date + Integer` | Cộng số ngày nếu DSL định nghĩa phép toán này |
| `String + String` | Nối chuỗi nếu DSL cho phép |
| `OrderStatus == PAID` | So sánh giá trị enum |
| `Money > Date` | Không hợp lệ vì hai kiểu không có quan hệ so sánh phù hợp |

Ngữ nghĩa phải quy định chuyển kiểu nào được phép, chuyển kiểu nào cần tường minh và trường hợp nào phải báo lỗi.

### 9.2. Giá trị thiếu và null

Giá trị thiếu có thể mang nhiều ý nghĩa: chưa biết, chưa được cung cấp, không áp dụng hoặc thực sự rỗng. DSL cần quyết định cách biểu thức xử lý các trạng thái đó.

Ví dụ, nếu `customer.email` chưa được cung cấp, biểu thức `customer.email == "a@example.com"` có thể:

- Trả về `false` theo logic hai giá trị với quy tắc null cụ thể.
- Trả về `unknown` theo logic ba giá trị.
- Phát sinh lỗi nếu email là thuộc tính bắt buộc.

Không có lựa chọn nào phù hợp với mọi DSL. Quan trọng là các toán tử logic và điều kiện phải áp dụng nhất quán cùng một mô hình giá trị thiếu.

### 9.3. Đơn vị và miền giá trị

Giá trị `100` có thể là 100 đồng, 100 kilogram hoặc 100 phần trăm. Nếu DSL không biểu diễn đơn vị, phép so sánh hoặc tính toán có thể cho kết quả sai dù kiểu lưu trữ đều là số.

Kiểu miền như `Money`, `Duration`, `Distance` hoặc metadata đơn vị có thể giúp xác định phép toán hợp lệ. Ngữ nghĩa cần quy định chuyển đổi, làm tròn và cách xử lý giá trị vượt giới hạn.

## 10. Ý nghĩa của lỗi và hành vi thất bại

Một đặc tả ngữ nghĩa đầy đủ cũng phải nói rõ khi cấu trúc không thể tạo kết quả bình thường.

Các nhóm lỗi thường gặp:

- **Lỗi phân tích:** cấu trúc không tuân theo grammar.
- **Lỗi phân giải tên:** tên hoặc thuộc tính không tồn tại trong scope.
- **Lỗi kiểu:** toán tử hoặc hàm không áp dụng được cho các kiểu nhận được.
- **Lỗi ràng buộc miền:** giá trị hoặc trạng thái vi phạm quy tắc nghiệp vụ.
- **Lỗi quyền:** tác nhân hiện tại không được phép thực hiện hành động.
- **Lỗi runtime:** nguồn dữ liệu không sẵn sàng, timeout, chia cho 0 hoặc dịch vụ ngoài thất bại.

DSL cần quy định lỗi nào được phát hiện tĩnh và lỗi nào chỉ có thể biết khi chạy. Nếu lỗi xảy ra trong một block nhiều hành động, hệ thống có rollback, tiếp tục, bỏ qua hay chuyển sang nhánh xử lý lỗi không?

Ví dụ với giao dịch:

```text
transaction {
    reserveInventory(order)
    chargePayment(order)
    createShipment(order)
}
```

Ngữ nghĩa của `transaction` cần nói rõ phạm vi nguyên tử, những thao tác nào có thể rollback, cách xử lý khi dịch vụ thanh toán đã tạo tác động bên ngoài và cơ chế bù trừ nếu không thể hoàn tác hoàn toàn.

## 11. Ngữ nghĩa của cấu trúc trong các loại DSL

### 11.1. DSL truy vấn dữ liệu

Trong DSL truy vấn, cấu trúc `select`, `from`, `where`, `join` và `groupBy` cần có semantics nhất quán về tập dữ liệu, số lượng kết quả, giá trị trùng lặp, thứ tự và null.

Ví dụ, `where condition` có thể chỉ giữ các hàng mà điều kiện là true. Nếu điều kiện trả về unknown, DSL cần xác định hàng có bị loại hay không. Nếu không có `orderBy`, kết quả có thứ tự xác định hay không cũng cần được nêu rõ.

### 11.2. DSL cấu hình

Trong DSL cấu hình, khai báo thường mô tả trạng thái mong muốn. Ví dụ:

```text
service api {
    replicas = 3
    region = "ap-southeast-1"
}
```

Ngữ nghĩa có thể nói rằng hệ thống phải duy trì ba bản sao dịch vụ ở vùng đã chọn. Nhưng cần phân biệt cấu hình mong muốn với hành động thực tế: khai báo có thể được dùng để tạo kế hoạch triển khai, chứ không nhất thiết khởi chạy dịch vụ ngay lúc parser đọc tệp.

### 11.3. DSL workflow

Trong DSL workflow, `step`, `dependsOn`, `retry`, `timeout` và `onFailure` cần có nghĩa chính xác. Ví dụ, `retry 3` là tổng cộng ba lần thử hay ba lần thử lại sau lần đầu? `timeout 30s` tính từ lúc xếp hàng hay lúc bước bắt đầu? Những khác biệt này ảnh hưởng trực tiếp đến hành vi.

### 11.4. DSL chính sách và luật

Trong DSL chính sách, các cấu trúc `permit`, `deny`, `priority`, `when` hoặc `unless` phải xác định rõ cách kết hợp nhiều quy tắc, mặc định khi không có rule nào khớp và ưu tiên khi rule xung đột. Đặc biệt, chính sách truy cập thường cần hành vi mặc định an toàn và dễ kiểm toán.

## 12. Mô hình hóa ngữ nghĩa trong AST và semantic model

Parser thường tạo AST mô tả cấu trúc cú pháp. Sau đó, semantic analyzer có thể bổ sung thông tin để biểu đạt ý nghĩa đã được xác định.

Ví dụ, node:

```text
MemberAccess(Identifier("order"), "total")
```

có thể được bổ sung:

- Symbol mà `order` tham chiếu đến.
- Kiểu của `order` là `Order`.
- Thuộc tính `total` được phân giải thành một symbol cụ thể.
- Kiểu của kết quả là `Money`.
- Quy tắc quyền đọc thuộc tính nếu DSL có kiểm soát truy cập.

Có thể lưu các thông tin này trong annotation trên AST hoặc một semantic model riêng. Tách riêng giúp AST cú pháp không bị phụ thuộc quá nhiều vào một lần phân tích cụ thể, đồng thời hỗ trợ nhiều backend hoặc nhiều context.

### 12.1. AST mô tả hình thức, semantic model mô tả liên kết đã hiểu

AST có thể giữ nguyên tên mà người dùng viết. Semantic model gắn tên đó với khai báo và kiểu tương ứng. Interpreter hoặc code generator sau đó sử dụng liên kết đã phân giải thay vì tự tìm tên lại.

### 12.2. Một cấu trúc có thể có semantics theo context

Cùng một node truy cập thuộc tính có thể mang ý nghĩa khác tùy context. `currentUser.role` trong rule phân quyền có thể là dữ liệu xác thực; `order.status` trong rule vận chuyển là trạng thái nghiệp vụ. Semantic analyzer cần biết context hợp lệ và giới hạn thao tác trên từng loại dữ liệu.

## 13. Cách viết đặc tả ngữ nghĩa cho DSL

Để tránh mỗi người hiểu một cách, nhóm thiết kế có thể lập bảng semantics cho từng cấu trúc.

Ví dụ cho cấu trúc `when`:

| Thuộc tính | Đặc tả minh họa |
|---|---|
| Cú pháp | `when <BooleanExpression>` |
| Vị trí hợp lệ | Bên trong khai báo `rule` |
| Kiểu yêu cầu | Biểu thức phải có kiểu Boolean |
| Context | Có quyền truy cập các biến và thuộc tính trong context của rule |
| Thời điểm đánh giá | Khi rule engine đánh giá rule trên một đối tượng |
| Kết quả true | Chọn phần action của rule |
| Kết quả false | Không thực hiện action của rule |
| Kết quả unknown | Theo chính sách null/unknown đã công bố |
| Lỗi runtime | Chuyển thành diagnostic hoặc trạng thái lỗi theo hợp đồng thực thi |

Đối với mỗi cấu trúc, nên ghi:

1. Dạng cú pháp và ví dụ.
2. Vị trí hoặc ngữ cảnh được phép sử dụng.
3. Điều kiện tĩnh về tên, kiểu và ràng buộc.
4. Ý nghĩa của kết quả hoặc tác động.
5. Thứ tự đánh giá và tương tác với cấu trúc khác.
6. Hành vi với dữ liệu thiếu, lỗi và ngoại lệ.
7. Các giới hạn về quyền, tài nguyên và tác dụng phụ.

Đặc tả nên có ví dụ hợp lệ và không hợp lệ. Một câu mô tả tổng quát thường chưa đủ để làm rõ trường hợp biên.

## 14. Tính xác định và khả năng dự đoán

Một DSL tốt nên cho kết quả có thể dự đoán khi đầu vào và context giống nhau, trừ khi ngôn ngữ cố ý hỗ trợ thời gian, ngẫu nhiên hoặc trạng thái bên ngoài.

Các câu hỏi cần làm rõ:

- Thứ tự thực thi có phụ thuộc thứ tự khai báo không?
- Có cho phép hai action cùng sửa một thuộc tính không?
- Nếu hai rule xung đột, hệ thống giải quyết thế nào?
- Truy vấn không có `orderBy` có đảm bảo thứ tự kết quả không?
- Hàm có được phép đọc đồng hồ, số ngẫu nhiên hoặc trạng thái toàn cục không?
- Cùng một rule có thể được đánh giá nhiều lần với kết quả khác nhau không?

Nếu semantics phụ thuộc yếu tố bên ngoài, cần nêu rõ yếu tố đó và cách kiểm soát trong kiểm thử hoặc audit. Ví dụ, rule dùng thời điểm hiện tại nên có cách truyền clock hoặc timestamp vào context để kết quả có thể tái lập.

## 15. Những sai lầm khi định nghĩa ý nghĩa cấu trúc

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ mô tả grammar | Cấu trúc hợp lệ nhưng không rõ hành vi | Viết thêm static và dynamic semantics |
| Dùng cùng từ khóa cho nhiều nghĩa không liên quan | Người dùng khó dự đoán kết quả | Tách cấu trúc hoặc định nghĩa context rõ |
| Không quy định scope | Tên có thể được hiểu khác nhau | Đặc tả name resolution và shadowing |
| Không xác định thứ tự đánh giá | Kết quả phụ thuộc implementation | Quy định precedence, evaluation order và short-circuit |
| Bỏ qua null hoặc giá trị thiếu | Các rule cho kết quả không nhất quán | Định nghĩa mô hình giá trị thiếu và logic tương ứng |
| Không mô tả tác dụng phụ | Người dùng không biết cấu trúc có thay đổi dữ liệu hay không | Ghi rõ read/write, transaction và side effects |
| Không xác định lỗi | Công cụ xử lý thất bại theo cách khác nhau | Phân loại lỗi và quy định thời điểm phát hiện |
| Để semantics chỉ tồn tại trong code | Tài liệu và implementation có thể lệch nhau | Duy trì đặc tả và kiểm thử conformance |

## 16. Kiểm thử ngữ nghĩa

Ngữ nghĩa cần được kiểm chứng bằng các trường hợp thể hiện cả kết quả đúng và hành vi biên.

### 16.1. Kiểm thử cấu trúc hợp lệ và không hợp lệ

Kiểm tra parser và semantic analyzer chấp nhận cấu trúc hợp lệ, từ chối cấu trúc sai kiểu, tên không tồn tại hoặc dùng sai context.

### 16.2. Kiểm thử kết quả thực thi

Với mỗi biểu thức hoặc rule, chuẩn bị context đầu vào và xác định kết quả mong đợi. Ví dụ, rule miễn phí vận chuyển cần được kiểm thử với đơn hàng thấp hơn, bằng và cao hơn ngưỡng; trạng thái đã thanh toán và chưa thanh toán; phí đã được áp dụng hoặc chưa áp dụng.

### 16.3. Kiểm thử thứ tự và tác dụng phụ

Kiểm tra short-circuit, thứ tự action, retry, rollback và trường hợp nhiều rule cùng phù hợp. Có thể dùng mock hoặc event log để quan sát thứ tự gọi.

### 16.4. Kiểm thử tương đương giữa các implementation

Nếu DSL có interpreter và code generator, cùng một chương trình nên cho kết quả tương đương trên các backend được hỗ trợ. Một bộ test ngữ nghĩa dùng chung giúp phát hiện sự khác biệt giữa hai cách thực thi.

### 16.5. Kiểm thử property-based

Với cấu trúc biểu thức, có thể sinh nhiều AST hợp lệ và kiểm tra các tính chất đã định nghĩa. Ví dụ, đánh giá một biểu thức sau khi serialize rồi parse lại phải giữ cùng semantics nếu định dạng serialize được thiết kế bảo toàn ngữ nghĩa.

## 17. Kết luận

Ý nghĩa của cấu trúc là phần ngữ nghĩa quy định một khai báo, biểu thức, câu lệnh, khối, rule, query hay workflow thực sự biểu đạt và tác động như thế nào. Cú pháp xác định cấu trúc nào được viết hợp lệ; ngữ nghĩa xác định cấu trúc đó tham chiếu đến đâu, tạo ra giá trị gì, thay đổi trạng thái nào và được xử lý trong điều kiện nào.

Để DSL dễ học và đáng tin cậy, mỗi cấu trúc cần có quy tắc rõ về kiểu, scope, context, thứ tự đánh giá, tác dụng phụ, giá trị thiếu và lỗi. Những quy tắc này có thể được mô tả bằng ngôn ngữ tự nhiên có cấu trúc, ngữ nghĩa vận hành, ngữ nghĩa biểu thị hoặc ngữ nghĩa tiên đề, rồi kiểm chứng bằng bộ test dùng chung.

Một cấu trúc DSL chỉ thực sự hữu ích khi người viết, parser, semantic analyzer, interpreter, compiler và công cụ đều hiểu nó theo cùng một ý nghĩa đã được định nghĩa.
