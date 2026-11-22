# Kiểm tra kiểu động

Trong một ngôn ngữ chuyên biệt theo miền (Domain-Specific Language — DSL), hệ thống cần biết một giá trị thuộc loại nào trước khi thực hiện phép toán hoặc hành động trên giá trị đó. Một số DSL xác định kiểu chủ yếu trước khi chạy; một số DSL cho phép giá trị được xác định hoặc thay đổi kiểu tại thời điểm thực thi. Khi chương trình kiểm tra kiểu của giá trị trong lúc chạy, đó là **kiểm tra kiểu động (dynamic type checking)**.

Kiểm tra kiểu động giúp DSL linh hoạt khi dữ liệu chỉ được biết lúc thực thi, khi cấu hình đến từ nguồn bên ngoài hoặc khi một biểu thức có thể nhận nhiều loại giá trị. Đổi lại, một số lỗi kiểu chỉ xuất hiện khi chương trình đi đến nhánh hoặc dữ liệu gây lỗi. Vì vậy, DSL cần quy định rõ thời điểm kiểm tra, cách chuyển đổi kiểu, hành vi khi không phù hợp và thông tin lỗi mà người dùng nhận được.

## 1. Kiểm tra kiểu động là gì?

Kiểm tra kiểu động là quá trình xác định và kiểm tra kiểu của giá trị khi chương trình đang chạy. Thay vì chỉ dựa vào kiểu được suy ra từ mã nguồn trước khi thực thi, runtime xem giá trị thực tế, xác định kiểu của nó và quyết định thao tác có hợp lệ hay không.

Ví dụ, một DSL biểu thức có thể cho phép:

```text
customer.age + 1
```

Khi thực thi, runtime đọc giá trị `customer.age`. Nếu giá trị là số nguyên, phép cộng có thể hợp lệ. Nếu giá trị thực tế là chuỗi như `"twenty"`, runtime phải từ chối phép cộng hoặc áp dụng quy tắc chuyển đổi nếu DSL đã định nghĩa rõ.

Kiểm tra kiểu động thường bao gồm:

- Xác định kiểu thực tế của từng giá trị.
- Kiểm tra kiểu toán hạng trước khi thực hiện phép toán.
- Kiểm tra đối số khi gọi hàm hoặc hành động.
- Kiểm tra phần tử khi đọc hoặc ghi collection.
- Kiểm tra giá trị trả về của hàm hoặc biểu thức.
- Báo lỗi khi kiểu không đáp ứng yêu cầu của thao tác.

Kiểm tra kiểu động không nhất thiết có nghĩa toàn bộ ngôn ngữ là dynamically typed. Một DSL có thể kiểm tra phần lớn biểu thức trước khi chạy nhưng vẫn kiểm tra lại dữ liệu đến từ API, tệp cấu hình hoặc hệ thống bên ngoài ở runtime.

## 2. Phân biệt kiểu động và kiểm tra kiểu động

Hai khái niệm thường đi cùng nhau nhưng không đồng nghĩa:

- **Kiểu động (dynamic typing):** kiểu gắn với giá trị tại thời điểm chạy; một biến hoặc vị trí lưu trữ có thể lần lượt tham chiếu các giá trị thuộc những kiểu khác nhau, tùy quy tắc ngôn ngữ.
- **Kiểm tra kiểu động (dynamic type checking):** runtime kiểm tra một thao tác có phù hợp với kiểu thực tế của giá trị hay không.

Một ngôn ngữ kiểu động thường cần kiểm tra kiểu trong runtime vì không phải mọi kiểu đều được xác định trước khi chạy. Tuy nhiên, một ngôn ngữ có khai báo kiểu tĩnh vẫn có thể thực hiện kiểm tra động tại ranh giới dữ liệu không đáng tin cậy.

Ví dụ bằng Python:

```python
value = 10
value = "ten"

print(value + 1)  # TypeError lúc chạy
```

Biến `value` lần lượt tham chiếu một số nguyên rồi một chuỗi. Khi phép cộng được thực hiện, runtime phát hiện kiểu thực tế không hỗ trợ phép cộng với số nguyên theo quy tắc tương ứng.

Ngược lại, trong một DSL có khai báo kiểu tĩnh, trường `age: Integer` có thể được kiểm tra trước khi chạy. Nhưng nếu giá trị được đọc từ JSON, runtime vẫn cần xác nhận dữ liệu nhận được thực sự là số nguyên trước khi đưa vào mô hình.

## 3. Kiểu của giá trị tại runtime

Để kiểm tra kiểu động, runtime cần có cách xác định kiểu hoặc loại giá trị. Cách triển khai tùy ngôn ngữ và môi trường thực thi.

### 3.1. Type tag hoặc thông tin kiểu đi kèm giá trị

Một cách phổ biến là mỗi giá trị được lưu cùng một nhãn kiểu (type tag) hoặc thông tin cho phép runtime xác định loại giá trị.

Ví dụ mô hình khái quát:

```text
RuntimeValue
├── type: Integer
└── payload: 42

RuntimeValue
├── type: String
└── payload: "hello"

RuntimeValue
├── type: Boolean
└── payload: true
```

Khi gặp phép cộng, runtime đọc type tag của hai toán hạng để chọn phép toán phù hợp hoặc phát sinh lỗi. Một runtime thực tế có thể dùng tagged union, object header, con trỏ đến descriptor kiểu hoặc cơ chế khác; không bắt buộc phải lưu một trường `type` tường minh như sơ đồ.

### 3.2. Các kiểu nguyên thủy và kiểu miền

DSL thường cần cả kiểu cơ bản và kiểu mang ý nghĩa nghiệp vụ:

| Nhóm kiểu | Ví dụ | Ý nghĩa và kiểm tra thường gặp |
|---|---|---|
| Boolean | `true`, `false` | Dùng trong điều kiện; không tự động coi số 0 là false nếu DSL không quy định |
| Số nguyên | `Integer` | Phép cộng, trừ, nhân, chia nguyên và giới hạn giá trị |
| Số thực/thập phân | `Decimal` | Độ chính xác, làm tròn, overflow và phép toán số |
| Chuỗi | `String` | Nối, tìm kiếm, so sánh và mã hóa ký tự |
| Ngày/giờ | `Date`, `Instant` | So sánh thời gian, múi giờ và phép cộng khoảng thời gian |
| Tiền | `Money` | Số tiền cùng currency, quy đổi và làm tròn |
| Liệt kê | `OrderStatus` | Chỉ chấp nhận các giá trị đã định nghĩa |
| Đối tượng miền | `Customer`, `Order` | Truy cập thuộc tính, quan hệ và quyền |
| Collection | `List<Order>`, `Set<Tag>` | Kiểu phần tử, số lượng, thứ tự và tính duy nhất |
| Hàm | `(Order) -> Boolean` | Kiểu tham số, kiểu trả về và số lượng đối số |

Kiểu miền giúp runtime kiểm tra ý nghĩa nghiệp vụ thay vì chỉ kiểm tra kiểu lưu trữ. Ví dụ, hai giá trị đều được biểu diễn bằng số thập phân nhưng một giá trị là `Money`, giá trị còn lại là `Percentage`; không nên cho phép cộng chúng chỉ vì cùng dạng biểu diễn.

### 3.3. Kiểu động không loại bỏ định nghĩa kiểu

Dù kiểu được kiểm tra lúc chạy, DSL vẫn cần định nghĩa các kiểu được hỗ trợ, quan hệ giữa chúng và các thao tác hợp lệ. Nếu không có quy tắc này, runtime không thể quyết định một phép toán có hợp lệ hay không.

## 4. Kiểm tra kiểu trong pipeline thực thi DSL

Một DSL có thể kiểm tra kiểu ở nhiều giai đoạn. Với kiểm tra động, một phần quan trọng diễn ra trong runtime:

```text
Văn bản DSL / dữ liệu đầu vào
          |
          v
Lexer và parser
          |
          v
AST hoặc biểu diễn trung gian
          |
          v
Phân tích tĩnh (nếu có)
          |
          v
Runtime nhận giá trị thực tế
          |
          v
Xác định kiểu của giá trị
          |
          v
Kiểm tra kiểu cho thao tác
       /       \\
      v         v
  Hợp lệ      Không hợp lệ
    |             |
    v             v
Thực hiện      Phát sinh lỗi kiểu
thao tác       hoặc xử lý theo quy tắc
```

Ví dụ, parser có thể chấp nhận biểu thức `record.amount + adjustment` vì cú pháp đúng. Tại runtime, `record.amount` có thể là `Money`, còn `adjustment` là `String`. Bộ kiểm tra kiểu động phát hiện sự không tương thích trước khi gọi phép cộng.

## 5. Kiểm tra kiểu cho toán tử

Mỗi toán tử cần quy định kiểu toán hạng mà nó chấp nhận và kiểu kết quả được tạo ra.

### 5.1. Phép toán số học

Ví dụ một chính sách kiểu đơn giản:

| Toán tử | Kiểu đầu vào | Kiểu kết quả |
|---|---|---|
| `+`, `-` | Hai giá trị số tương thích | Kiểu số phù hợp |
| `*` | Hai giá trị số tương thích | Kiểu số phù hợp |
| `/` | Hai giá trị số tương thích | Kiểu số hoặc Decimal theo quy tắc DSL |
| `%` | Hai số nguyên nếu DSL chỉ định phép chia dư nguyên | Số nguyên |

Ví dụ:

```text
price * quantity
```

Nếu `price` là `Money` và `quantity` là `Integer`, DSL có thể định nghĩa phép nhân trả về `Money`. Nhưng nếu cả hai đều là `Money`, phép nhân có thể không có ý nghĩa nghiệp vụ hoặc cần một kiểu kết quả đặc biệt. Runtime cần kiểm tra cặp kiểu cụ thể, không chỉ kiểm tra cả hai có phải số hay không.

### 5.2. So sánh

Các phép so sánh cũng cần kiểu tương thích:

```text
order.total >= minimumTotal
order.status == PAID
customer.name == "Lan"
```

`Money` có thể được so sánh khi cùng currency hoặc khi DSL có quy tắc quy đổi; `OrderStatus` có thể so sánh với một giá trị enum cùng kiểu; `String` có thể so sánh với `String` theo quy tắc văn bản đã định nghĩa.

Biểu thức sau nên bị từ chối nếu không có quy tắc chuyển đổi được công bố:

```text
order.total >= "one million"
```

### 5.3. Toán tử logic

Trong một DSL yêu cầu Boolean nghiêm ngặt, `and`, `or` và `not` chỉ nhận toán hạng Boolean:

```text
order.isPaid and order.total > 0
not customer.isBlocked
```

Không nên tự động coi số 0, chuỗi rỗng hoặc collection rỗng là false nếu DSL không định nghĩa truthiness. Quy tắc Boolean rõ ràng giúp điều kiện nghiệp vụ dễ dự đoán.

## 6. Kiểm tra kiểu khi truy cập thuộc tính và gọi hàm

### 6.1. Truy cập thuộc tính

Khi đánh giá `order.total`, runtime cần xác định kiểu của `order`, kiểm tra kiểu đó có thuộc tính `total` không, rồi xác định kiểu của giá trị trả về.

Ví dụ:

```text
order.total
```

Nếu `order` thực tế là một `Customer`, phép truy cập `total` có thể không hợp lệ. Runtime cần báo lỗi có ngữ cảnh thay vì trả về một giá trị không xác định hoặc bỏ qua lỗi.

Với truy cập thuộc tính tùy chọn như `customer.address?.city`, DSL cần định nghĩa cách xử lý khi `address` là null hoặc thiếu. Kết quả có thể là giá trị tùy chọn, null hoặc lỗi tùy ngữ nghĩa.

### 6.2. Gọi hàm và hành động

Khi gọi hàm, runtime cần kiểm tra:

- Giá trị được gọi có thực sự là hàm hoặc callable không.
- Số lượng đối số có phù hợp không.
- Kiểu thực tế của từng đối số có tương thích với tham số không.
- Các giá trị tùy chọn hoặc giá trị mặc định được xử lý thế nào.
- Kiểu trả về có phù hợp với nơi sử dụng không.

Ví dụ DSL:

```text
notifyCustomer(order)
```

Nếu `notifyCustomer` yêu cầu `Customer` nhưng nhận `Order`, runtime phải phát hiện lỗi trước khi gọi hành động. Nếu hàm có tác dụng phụ như gửi email, việc kiểm tra kiểu nên xảy ra trước khi tác động được thực hiện.

### 6.3. Kiểu trả về

Một hàm có thể trả về các kiểu khác nhau tùy nhánh thực thi nếu DSL cho phép. Khi kết quả được dùng trong một biểu thức yêu cầu kiểu cụ thể, runtime cần kiểm tra kiểu trả về thực tế.

Ví dụ, một hàm khai báo theo hợp đồng trả về `Money` nhưng một nhánh lại trả về `String`; runtime có thể phát hiện vi phạm hợp đồng tại thời điểm hàm trả kết quả.

## 7. Kiểm tra kiểu cho collection

Collection đặt ra câu hỏi về kiểu phần tử và thời điểm kiểm tra. Một DSL có thể khai báo `List<Order>`, nhưng dữ liệu thực tế đến từ JSON hoặc plugin có thể chứa phần tử không phải `Order`.

### 7.1. Kiểm tra khi tạo collection

Khi tạo danh sách, runtime có thể kiểm tra từng phần tử:

```text
orders = [orderA, orderB, orderC]
```

Nếu danh sách được khai báo là `List<Order>`, mỗi phần tử phải tương thích với `Order` theo quy tắc kiểu của DSL.

### 7.2. Kiểm tra khi đọc phần tử

Một số hệ thống trì hoãn kiểm tra đến lúc truy cập. Ví dụ, collection bên ngoài có thể được bọc bởi một adapter kiểm tra kiểu mỗi khi đọc phần tử. Khi đó, lỗi xuất hiện tại điểm sử dụng chứ không phải lúc dữ liệu được tải.

### 7.3. Kiểm tra khi ghi phần tử

Với collection mutable, thao tác thêm hoặc cập nhật cũng phải tuân theo kiểu phần tử:

```text
orders.add(newOrder)
```

Nếu `newOrder` là `Customer`, runtime phải từ chối thao tác. Nếu chỉ kiểm tra lúc tạo collection mà không kiểm tra khi ghi, kiểu của collection có thể bị phá vỡ sau khi khởi tạo.

### 7.4. Collection lồng nhau

Với `Map<String, List<Order>>`, runtime có thể cần kiểm tra cả kiểu khóa, kiểu giá trị và kiểu từng phần tử bên trong danh sách. Cần quy định kiểm tra sâu (deep checking) hay chỉ kiểm tra lớp ngoài (shallow checking), đặc biệt khi dữ liệu lớn hoặc được truy cập lười.

## 8. Kiểm tra kiểu và giá trị null hoặc thiếu

Giá trị null thường là nguồn lỗi phổ biến vì nó không đại diện cho một giá trị thông thường của kiểu miền. DSL cần quyết định null là một kiểu riêng, một giá trị đặc biệt hay biểu diễn của thuộc tính tùy chọn.

### 8.1. Null không phải cùng nghĩa với mọi giá trị thiếu

Cần phân biệt:

- Thuộc tính chưa được cung cấp.
- Thuộc tính không áp dụng.
- Giá trị chưa biết.
- Giá trị null có chủ đích.
- Chuỗi rỗng hoặc collection rỗng.

Các trường hợp này có thể cần kiểu hoặc trạng thái riêng. Không nên gộp chúng thành một giá trị chung nếu quy tắc nghiệp vụ cần phân biệt.

### 8.2. Kiểm tra trước khi sử dụng

Ví dụ:

```text
if customer.email != null {
    sendReceipt(customer.email)
}
```

Runtime cần xác định biểu thức so sánh null hợp lệ và nhánh bên trong có thể sử dụng giá trị email theo kiểu không-null hay không. Một số DSL có thể dùng type narrowing: sau khi kiểm tra, kiểu của `customer.email` trong nhánh được thu hẹp từ `EmailAddress?` thành `EmailAddress`.

### 8.3. Optional type

Một kiểu tùy chọn có thể biểu diễn giá trị có hoặc không có:

```text
EmailAddress? = EmailAddress | Null
```

Phép gọi hàm yêu cầu `EmailAddress` không nên nhận `EmailAddress?` trực tiếp nếu chưa kiểm tra hoặc xử lý giá trị null. Runtime cần áp dụng cùng quy tắc ở mọi nơi.

## 9. Coercion và chuyển đổi kiểu

Khi hai kiểu không trùng nhau, DSL có thể từ chối thao tác hoặc chuyển đổi một giá trị. Cần phân biệt **coercion** (chuyển đổi ngầm theo quy tắc ngôn ngữ) với **explicit conversion** (chuyển đổi tường minh do người viết yêu cầu).

### 9.1. Chuyển đổi ngầm

Ví dụ, DSL có thể cho phép chuyển `Integer` sang `Decimal` khi thực hiện phép cộng với số thập phân. Nhưng chuyển `String` thành `Integer` tự động có thể gây bất ngờ hoặc lỗi dữ liệu.

```text
quantity + 1.5
```

Nếu `quantity` là `Integer`, DSL có thể nâng kiểu sang `Decimal` theo quy tắc numeric promotion đã công bố. Quy tắc cần nêu rõ độ chính xác, overflow và kiểu kết quả.

### 9.2. Chuyển đổi tường minh

Ví dụ:

```text
toInteger("42")
toDecimal("12.50")
toDate("2026-11-15")
```

Hàm chuyển đổi tường minh cho người viết biết dữ liệu đang được diễn giải lại. Nếu chuyển đổi thất bại, DSL cần xác định trả về lỗi, optional value hoặc một kiểu kết quả như `Result<Integer, ParseError>`.

### 9.3. Không nên coercion tùy tiện

Chuyển `"false"` thành Boolean, `"0"` thành số hoặc `[]` thành false có thể hợp lý trong một số ngôn ngữ nhưng không phải quy tắc phổ quát. Một DSL phục vụ quy tắc nghiệp vụ thường nên ưu tiên chuyển đổi rõ ràng để tránh dữ liệu sai định dạng được chấp nhận âm thầm.

### 9.4. Numeric promotion

Khi kết hợp các kiểu số, DSL có thể định nghĩa thứ tự nâng kiểu, ví dụ `Integer` sang `Decimal`. Nhưng với `Money`, `Percentage` hoặc `Duration`, không nên coi chúng chỉ là kiểu số. Phép toán cần tuân theo ý nghĩa miền và đơn vị.

## 10. Kiểm tra kiểu trong hàm đa hình và dispatch động

Một DSL có thể hỗ trợ đa hình: cùng một tên thao tác hoạt động với nhiều kiểu dữ liệu. Runtime cần chọn cách thực thi dựa trên kiểu thực tế.

Ví dụ:

```text
format(customer)
format(order)
format(invoice)
```

Có thể có các implementation khác nhau cho `Customer`, `Order` và `Invoice`. Dynamic dispatch chọn implementation phù hợp với kiểu thực tế của đối tượng.

Cần phân biệt dispatch động với coercion. Dispatch chọn hành vi đã định nghĩa cho kiểu; coercion biến đổi giá trị sang kiểu khác. DSL nên quy định thứ tự ưu tiên khi có nhiều overload phù hợp, cách xử lý trường hợp mơ hồ và việc subtype có được ưu tiên hơn supertype không.

Ví dụ, nếu có `format(Entity)` và `format(Order)`, một giá trị runtime có kiểu `Order` thường chọn overload chuyên biệt `format(Order)` nếu semantics của DSL quy định dispatch theo kiểu thực tế.

## 11. Type guard và thu hẹp kiểu tại runtime

Type guard là cấu trúc hoặc hàm kiểm tra kiểu thực tế của giá trị. Khi kiểm tra thành công, hệ thống có thể cho phép sử dụng giá trị như kiểu cụ thể hơn trong phạm vi nhất định.

Ví dụ DSL giả định:

```text
if value is Customer {
    notifyCustomer(value)
}
```

Trong nhánh đúng, runtime đã xác nhận `value` là `Customer`, vì vậy `notifyCustomer` có thể nhận giá trị đó. Trong nhánh sai, giá trị không được coi là `Customer`.

### 11.1. Kiểm tra kiểu tường minh

Một số DSL có hàm hoặc toán tử như `is`, `instanceOf`, `hasType` để kiểm tra kiểu. Kết quả thường là Boolean hoặc một kết quả có khả năng thu hẹp kiểu.

### 11.2. Kiểm tra cấu trúc (structural check)

Thay vì kiểm tra một class cụ thể, DSL có thể kiểm tra đối tượng có các thuộc tính hoặc hành vi cần thiết hay không. Ví dụ, một giá trị được chấp nhận là `AddressLike` nếu có `street`, `city` và `postalCode` với kiểu tương ứng.

Kiểm tra cấu trúc linh hoạt nhưng cần định nghĩa rõ thuộc tính bắt buộc, thuộc tính tùy chọn, kiểu lồng nhau và cách xử lý getter có tác dụng phụ.

### 11.3. Thu hẹp kiểu chỉ có hiệu lực trong phạm vi hợp lệ

Nếu giá trị có thể thay đổi giữa lúc kiểm tra và lúc sử dụng, type guard có thể không còn đúng. DSL cần bảo đảm giá trị ổn định trong phạm vi hoặc kiểm tra lại khi sử dụng. Đây là vấn đề đặc biệt quan trọng khi truy cập dữ liệu chia sẻ hoặc xử lý đồng thời.

## 12. Kiểm tra kiểu tại ranh giới dữ liệu

Ngay cả khi DSL có phân tích kiểu tĩnh, dữ liệu bên ngoài vẫn có thể không đúng như khai báo. Các ranh giới thường cần kiểm tra động:

- Đọc JSON, YAML, CSV hoặc dữ liệu từ tệp.
- Nhận phản hồi từ HTTP API.
- Nhận dữ liệu từ cơ sở dữ liệu hoặc message queue.
- Gọi plugin hoặc hàm mở rộng do bên thứ ba cung cấp.
- Đọc biến môi trường hoặc cấu hình runtime.
- Nhận đầu vào do người dùng nhập.

Ví dụ, schema mong đợi:

```text
CustomerInput {
    name: String
    age: Integer
}
```

Nhưng dữ liệu JSON thực tế có thể là:

```json
{
  "name": "Lan",
  "age": "twenty"
}
```

Parser JSON có thể đọc được cấu trúc, nhưng validator phải phát hiện `age` là chuỗi thay vì số nguyên. Lỗi nên nêu đường dẫn như `$.age`, kiểu mong đợi và kiểu thực tế. Không nên ép chuỗi thành số nếu nội dung không thể chuyển đổi hoặc chính sách không cho phép.

## 13. Xử lý lỗi kiểu động

Một lỗi kiểu động xảy ra khi thao tác không hợp lệ với kiểu thực tế của giá trị tại runtime.

Ví dụ:

```text
customer.age + "years"
```

Nếu DSL không định nghĩa phép cộng giữa `Integer` và `String`, runtime phải phát sinh type error.

### 13.1. Thông báo lỗi hữu ích

Một diagnostic tốt nên cung cấp:

- Vị trí trong tệp DSL hoặc vị trí dữ liệu đầu vào.
- Tên thao tác gây lỗi.
- Kiểu thực tế nhận được.
- Kiểu hoặc nhóm kiểu được yêu cầu.
- Ngữ cảnh gọi hoặc đường dẫn dữ liệu liên quan.
- Gợi ý sửa nếu có thể xác định an toàn.

Ví dụ:

```text
TypeError at rules/shipping.dsl:18:24
Operator "+" does not accept Integer and String.
Left operand: order.quantity (Integer)
Right operand: adjustment (String)
Expected: compatible numeric values.
```

Thông báo cần dùng thuật ngữ nhất quán với tài liệu DSL. Nếu giá trị đến từ dữ liệu ngoài, có thể bổ sung đường dẫn như `$.order.quantity` hoặc tên nguồn dữ liệu.

### 13.2. Fail fast và xử lý lỗi theo kết quả

Có hai hướng phổ biến:

- **Fail fast:** dừng thao tác ngay khi phát hiện kiểu không hợp lệ. Phù hợp khi tiếp tục có thể gây sai dữ liệu hoặc tác dụng phụ.
- **Trả về lỗi có kiểu:** biểu thức trả về `Result<T, TypeError>` hoặc một kiểu tương tự để chương trình gọi quyết định cách xử lý.

Không nên âm thầm thay giá trị sai kiểu bằng `null`, `0` hoặc chuỗi rỗng, vì hành vi đó có thể che giấu lỗi dữ liệu.

### 13.3. Lỗi trong workflow hoặc rule engine

Nếu lỗi xảy ra giữa một workflow nhiều bước, DSL cần xác định bước hiện tại chuyển sang trạng thái nào, có retry hay không, có rollback hoặc compensation không và lỗi có được truyền đến caller không. Một lỗi kiểu trong biểu thức điều kiện thường nên được phân biệt với điều kiện đơn giản trả về false.

## 14. Kiểm tra kiểu động và an toàn kiểu

Kiểm tra kiểu động giúp ngăn các phép toán không hợp lệ, nhưng không tự động bảo đảm toàn bộ chương trình an toàn.

### 14.1. Type safety

Một hệ thống được xem là type-safe khi các quy tắc kiểu bảo đảm chương trình không thực hiện những thao tác ngoài hợp đồng kiểu mà không được phát hiện hoặc xử lý. Với DSL động, runtime cần kiểm tra trước khi thực hiện thao tác có yêu cầu kiểu.

Type safety còn phụ thuộc cách DSL xử lý ép kiểu, truy cập bộ nhớ, plugin, native extension và tác dụng phụ. Chỉ gắn type tag cho giá trị không đủ để bảo đảm an toàn nếu runtime có thể bị bỏ qua hoặc dữ liệu bị diễn giải sai.

### 14.2. Kiểm tra nông và kiểm tra sâu

Kiểm tra nông xác nhận kiểu bên ngoài, ví dụ giá trị là `List`. Kiểm tra sâu còn kiểm tra kiểu từng phần tử, các trường lồng nhau và ràng buộc bên trong.

Kiểm tra sâu đáng tin cậy hơn cho dữ liệu không đáng tin cậy nhưng có thể tốn thời gian và bộ nhớ. DSL cần cân nhắc kích thước dữ liệu, tính lười của collection và việc dữ liệu có thể thay đổi sau khi xác thực.

### 14.3. Ranh giới tin cậy

Kiểm tra kiểu nên được thực hiện tại ranh giới nơi dữ liệu đi vào hệ thống và tại những điểm thao tác cần bảo đảm hợp đồng. Nếu dữ liệu có thể bị thay đổi sau khi kiểm tra, cần xác thực lại hoặc dùng cấu trúc bất biến để giữ bảo đảm.

## 15. Kết hợp kiểm tra kiểu tĩnh và động

Nhiều DSL chọn cách kết hợp hai phương pháp:

- Kiểm tra tĩnh các biểu thức có đủ thông tin kiểu trước khi chạy.
- Kiểm tra động dữ liệu đầu vào, kết quả plugin hoặc giá trị có kiểu chưa biết.
- Dùng type guard để thu hẹp kiểu trong nhánh điều kiện.
- Kiểm tra lại hợp đồng khi gọi hàm hoặc hành động bên ngoài.

Ví dụ, khai báo:

```text
entity Order {
    total: Money
    status: OrderStatus
}
```

có thể được kiểm tra tĩnh trong DSL. Nhưng khi runtime đọc một đối tượng từ JSON, nó cần xác thực `total` có thể chuyển thành `Money` hợp lệ và `status` thuộc enum được phép.

### 15.1. Gradual typing

Gradual typing cho phép kết hợp vùng có kiểu tĩnh và vùng có kiểu động. Một phần chương trình có thể khai báo kiểu cụ thể; phần khác dùng kiểu động hoặc kiểu chưa biết. Runtime checks được chèn tại ranh giới nơi giá trị đi từ vùng động sang vùng có hợp đồng kiểu.

Ví dụ khái quát:

```text
function calculateTax(amount: Money): Money

dynamicValue = readFromExternalSource()
calculateTax(dynamicValue)
```

Trước khi gọi `calculateTax`, runtime phải xác nhận `dynamicValue` là `Money` hợp lệ hoặc chuyển đổi theo quy tắc tường minh. Nếu không, lời gọi bị từ chối với lỗi kiểu.

Gradual typing có thể hữu ích khi DSL phát triển từ cấu hình linh hoạt sang hệ thống có nhiều khai báo kiểu hơn. Tuy nhiên, cần quy định rõ ranh giới kiểm tra và chi phí runtime.

## 16. Hiệu năng của kiểm tra kiểu động

Kiểm tra kiểu động có chi phí vì runtime phải xác định kiểu, kiểm tra tính tương thích và có thể thực hiện chuyển đổi.

Các yếu tố ảnh hưởng:

- Số lượng thao tác cần kiểm tra.
- Độ sâu của cấu trúc dữ liệu.
- Kiểu có cần được phân giải qua descriptor hoặc hierarchy không.
- Collection có được kiểm tra từng phần tử hay không.
- Có cần coercion hoặc dynamic dispatch không.
- Kiểm tra có thể được cache hoặc tối ưu hóa dựa trên thông tin kiểu đã biết không.

Có thể giảm chi phí bằng cách:

- Kiểm tra dữ liệu tại ranh giới nhập thay vì lặp lại cùng một kiểm tra không cần thiết.
- Dùng kiểu miền và cấu trúc bất biến sau khi xác thực.
- Cache kết quả phân giải kiểu khi dữ liệu và schema không đổi.
- Tận dụng thông tin kiểu đã biết từ phân tích tĩnh.
- Tránh deep checking lặp lại trên collection lớn nếu có thể bảo đảm tính hợp lệ bằng hợp đồng dữ liệu.

Tuy nhiên, tối ưu hóa không được loại bỏ kiểm tra cần thiết. Nếu dữ liệu có thể thay đổi hoặc nguồn không đáng tin cậy, cache kiểm tra có thể trở nên lỗi thời.

## 17. Ví dụ tổng hợp: kiểm tra kiểu động trong DSL quy tắc

Giả sử DSL có rule:

```text
rule applyBulkDiscount {
    when order.quantity >= 10
    then order.discount = order.total * 0.1
}
```

Các kiểu được mong đợi:

| Biểu thức | Kiểu mong đợi |
|---|---|
| `order` | `Order` |
| `order.quantity` | `Integer` |
| `10` | `Integer` |
| `order.total` | `Money` |
| `0.1` | `Percentage` hoặc `Decimal` theo đặc tả |
| `order.total * 0.1` | `Money` nếu phép nhân Money × Percentage được định nghĩa |
| `order.discount` | `Money` |

Khi runtime nhận một đơn hàng từ hệ thống bên ngoài, nó cần xác thực kiểu thực tế của `quantity` và `total`. Nếu `quantity` là chuỗi `"12"`, DSL có thể từ chối hoặc chuyển đổi tường minh theo schema; không nên tự đoán. Nếu `total` là tiền VND nhưng `discount` yêu cầu USD, phép gán phải bị từ chối hoặc áp dụng một quy tắc quy đổi đã được định nghĩa.

Luồng xử lý có thể là:

1. Đọc dữ liệu đơn hàng từ nguồn bên ngoài.
2. Xác thực cấu trúc và kiểu của các trường.
3. Tạo đối tượng `Order` hoặc giá trị runtime có thông tin kiểu.
4. Đánh giá điều kiện `order.quantity >= 10`.
5. Nếu điều kiện đúng, đánh giá phép tính chiết khấu.
6. Kiểm tra kiểu và currency của kết quả trước khi gán.
7. Thực hiện cập nhật theo quyền và giao dịch của rule engine.
8. Nếu bất kỳ bước nào vi phạm hợp đồng kiểu, phát sinh diagnostic và áp dụng chính sách lỗi đã định nghĩa.

Ví dụ này cho thấy kiểm tra kiểu động có thể xuất hiện ở nhiều điểm: khi nhập dữ liệu, khi đánh giá toán tử, khi gọi hành động và khi ghi kết quả vào mô hình miền.

## 18. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra kiểu khi tạo giá trị | Collection mutable hoặc dữ liệu thay đổi có thể chứa phần tử sai kiểu | Kiểm tra cả thao tác ghi hoặc dùng collection bất biến |
| Tự động ép kiểu quá rộng | Dữ liệu sai vẫn được chấp nhận và cho kết quả bất ngờ | Giới hạn coercion và ưu tiên chuyển đổi tường minh |
| Không phân biệt false với type error | Rule sai kiểu có thể bị coi như điều kiện không thỏa | Phân biệt kết quả Boolean và lỗi thực thi |
| Bỏ qua currency hoặc đơn vị | Phép tính số học hợp cú pháp nhưng sai nghiệp vụ | Dùng kiểu miền và kiểm tra đơn vị |
| Chỉ kiểm tra kiểu ngoài cùng | Dữ liệu lồng nhau vẫn có thể sai kiểu | Xác định rõ shallow/deep validation |
| Diagnostic chỉ nói “invalid value” | Khó tìm nguyên nhân | Báo kiểu thực tế, kiểu mong đợi và vị trí |
| Thu hẹp kiểu không an toàn | Giá trị có thể đổi sau khi kiểm tra | Giới hạn phạm vi hoặc kiểm tra lại khi dùng |
| Cache kết quả kiểm tra không đúng | Dữ liệu mới có thể không được xác thực | Gắn cache với phiên bản schema và trạng thái dữ liệu |

## 19. Nguyên tắc thiết kế kiểm tra kiểu động cho DSL

Khi xây dựng runtime, có thể áp dụng các nguyên tắc sau:

1. **Định nghĩa hệ kiểu rõ ràng.** Mô tả kiểu cơ bản, kiểu miền, subtype, optional và collection.
2. **Quy định thao tác theo cặp kiểu.** Mỗi toán tử và hàm cần nêu kiểu đầu vào, kiểu kết quả và trường hợp không hợp lệ.
3. **Kiểm tra trước tác dụng phụ.** Xác thực kiểu đối số và điều kiện trước khi gọi API, ghi dữ liệu hoặc thay đổi trạng thái.
4. **Kiểm tra dữ liệu ở ranh giới tin cậy.** Xác thực JSON, plugin, API và nguồn dữ liệu ngoài theo schema.
5. **Hạn chế coercion ngầm.** Chỉ cho phép chuyển đổi có ý nghĩa và có quy tắc cụ thể.
6. **Phân biệt lỗi kiểu với kết quả nghiệp vụ.** `false`, `null`, `unknown` và `TypeError` không nên bị nhập làm một.
7. **Cung cấp diagnostic có ngữ cảnh.** Nêu vị trí, kiểu thực tế, kiểu mong đợi và nguồn dữ liệu.
8. **Xem xét collection và dữ liệu lồng nhau.** Quy định kiểm tra khi tạo, đọc và ghi.
9. **Quản lý hiệu năng có kiểm soát.** Cache hoặc bỏ kiểm tra lặp chỉ khi bảo đảm kiểu không thể thay đổi ngoài dự kiến.
10. **Kết hợp kiểm tra tĩnh và động.** Phát hiện sớm những lỗi có thể biết trước, đồng thời bảo vệ ranh giới runtime.

## 20. Kết luận

Kiểm tra kiểu động là việc runtime xác định kiểu thực tế của giá trị và kiểm tra thao tác có phù hợp với kiểu đó hay không. Nó đặc biệt hữu ích khi DSL làm việc với dữ liệu chỉ biết lúc chạy, cấu hình bên ngoài, plugin, collection động hoặc biểu thức có nhiều dạng giá trị.

Một hệ thống kiểm tra kiểu động tốt cần có hệ kiểu được định nghĩa rõ, quy tắc cho toán tử và hàm, chính sách chuyển đổi, xử lý null, kiểm tra collection, type guard và diagnostic hữu ích. Kiểm tra cần diễn ra trước khi thực hiện tác động không thể đảo ngược, nhất là khi dữ liệu đến từ nguồn không đáng tin cậy.

Kết hợp kiểm tra tĩnh với kiểm tra động thường đem lại sự cân bằng: phát hiện sớm lỗi có thể biết từ mã nguồn và xác thực những giá trị chỉ xuất hiện trong runtime. Mục tiêu là để mọi cấu trúc DSL chỉ được thực thi khi các giá trị thực tế đáp ứng đúng hợp đồng kiểu mà ngôn ngữ đã công bố.
