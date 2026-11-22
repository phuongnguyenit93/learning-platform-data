# Ràng buộc kiểu

Trong một ngôn ngữ chuyên biệt theo miền (Domain-Specific Language — DSL), một biểu thức có thể đúng cú pháp nhưng vẫn không hợp lệ vì các giá trị và thao tác của nó không tương thích về kiểu. Ví dụ, cộng một ngày với một địa chỉ, truyền chuỗi vào hàm yêu cầu số tiền hoặc gán trạng thái thanh toán vào thuộc tính ngày giờ đều là những trường hợp có thể phân tích được về mặt cú pháp nhưng không có ý nghĩa theo hệ kiểu của DSL.

**Ràng buộc kiểu (type constraints)** là những điều kiện mà các kiểu của biểu thức, biến, tham số, thuộc tính và kết quả phải thỏa mãn để chương trình có ý nghĩa. Trong giai đoạn kiểm tra ngữ nghĩa, compiler hoặc interpreter thu thập các ràng buộc này, xác định xem chúng có thể đồng thời đúng hay không, rồi báo lỗi nếu có mâu thuẫn.

Ràng buộc kiểu giúp DSL ngăn những phép toán vô nghĩa, giữ tính nhất quán của mô hình miền và phát hiện lỗi sớm. Chúng cũng là nền tảng cho suy luận kiểu, kiểm tra lời gọi hàm, generic, overload và xác thực dữ liệu ở ranh giới runtime.

## 1. Ràng buộc kiểu là gì?

Kiểu của một biểu thức mô tả loại giá trị mà biểu thức có thể tạo ra, cùng những thao tác được phép trên giá trị đó. Ràng buộc kiểu là điều kiện quan hệ giữa một hoặc nhiều kiểu.

Ví dụ, với phép cộng:

```text
order.quantity + extraQuantity
```

nếu DSL định nghĩa phép cộng số nguyên, hai toán hạng cần có kiểu tương thích với `Integer`, và kết quả có kiểu `Integer`. Có thể biểu diễn ràng buộc khái quát:

```text
type(order.quantity) = Integer
type(extraQuantity) = Integer
type(result) = Integer
```

Trong thực tế, DSL có thể cho phép nhiều tổ hợp hơn, chẳng hạn `Integer + Decimal -> Decimal`. Khi đó ràng buộc không yêu cầu hai kiểu bằng nhau tuyệt đối mà yêu cầu chúng thuộc một tập tổ hợp được phép.

### 1.1. Ràng buộc khác với khai báo kiểu

Khai báo kiểu nói một thành phần có kiểu nào:

```text
quantity: Integer
```

Ràng buộc kiểu nói những quan hệ nào phải đúng khi thành phần được sử dụng:

```text
quantity + 1       // hợp lệ nếu phép cộng Integer được hỗ trợ
quantity + "one"   // không hợp lệ nếu không có phép cộng Integer với String
```

Khai báo cung cấp thông tin đầu vào cho bộ kiểm tra; ràng buộc xác định thông tin đó phải tương thích với các thao tác trong chương trình như thế nào.

### 1.2. Ràng buộc kiểu thuộc kiểm tra ngữ nghĩa

Parser xác nhận cấu trúc token có tuân theo grammar. Type checker sử dụng AST cùng thông tin symbol và scope để xác định kiểu của từng biểu thức, sau đó kiểm tra các ràng buộc. Vì vậy, lỗi kiểu thường được phân loại là lỗi ngữ nghĩa tĩnh.

Ví dụ:

```text
when order.total > "high"
```

Biểu thức có thể đúng cú pháp. Nhưng nếu `order.total` có kiểu `Money` và literal bên phải có kiểu `String`, type checker phải từ chối phép so sánh trừ khi DSL định nghĩa một phép chuyển đổi hợp lệ.

## 2. Những nơi thường phát sinh ràng buộc kiểu

Ràng buộc xuất hiện ở hầu hết cấu trúc có sử dụng giá trị:

- **Gán:** kiểu của giá trị bên phải phải tương thích với kiểu của biến hoặc thuộc tính bên trái.
- **Toán tử:** kiểu của toán hạng phải được toán tử hỗ trợ.
- **Lời gọi hàm:** kiểu và số lượng đối số phải phù hợp với chữ ký hàm.
- **Giá trị trả về:** kết quả của thân hàm phải tương thích với kiểu trả về được khai báo hoặc suy luận.
- **Điều kiện:** biểu thức điều kiện phải có kiểu Boolean hoặc kiểu điều kiện được DSL cho phép.
- **Collection:** phần tử phải phù hợp với kiểu phần tử; khóa và giá trị phải phù hợp với kiểu của map.
- **Thuộc tính:** giá trị được đọc hoặc ghi phải tuân theo kiểu và quyền của thuộc tính.
- **Nhánh điều kiện:** các nhánh tạo ra giá trị phải có kiểu kết quả có thể kết hợp.
- **Khai báo miền:** quan hệ, trạng thái và đơn vị dữ liệu phải phù hợp với mô hình miền.

Ví dụ một rule:

```text
rule bulkDiscount {
    when order.quantity >= 10
    then order.discount = order.total * 0.1
}
```

Bộ kiểm tra cần xác định `quantity` có thể so sánh với số nguyên; `total` có kiểu tiền; `0.1` là tỷ lệ hoặc số thập phân; phép nhân giữa tiền và tỷ lệ tạo ra tiền; và `discount` nhận được kiểu kết quả đó.

## 3. Tương thích kiểu (type compatibility)

Hai kiểu tương thích khi một giá trị thuộc kiểu này có thể được sử dụng ở vị trí yêu cầu kiểu kia theo quy tắc của DSL. Tương thích có thể dựa trên kiểu bằng nhau, quan hệ subtype, chuyển đổi ngầm hoặc một quy tắc đặc biệt của miền.

### 3.1. Tương thích chính xác

Trong chính sách nghiêm ngặt, kiểu nguồn phải bằng kiểu đích:

```text
let quantity: Integer = 12       // hợp lệ
let quantity: Integer = "12"     // không hợp lệ
```

Cách này dễ dự đoán vì compiler không phải đoán ý định chuyển đổi. Nó phù hợp với DSL nghiệp vụ cần tránh dữ liệu sai định dạng được chấp nhận âm thầm.

### 3.2. Tương thích theo subtype

Nếu `Dog` là subtype của `Animal`, một giá trị `Dog` có thể được dùng ở vị trí yêu cầu `Animal`:

```text
let pet: Animal = dog
```

Đây là phép thay thế theo quan hệ subtype. Chiều ngược lại thường không an toàn: một giá trị `Animal` không nhất thiết là `Dog`.

### 3.3. Tương thích qua chuyển đổi

Một số DSL cho phép chuyển đổi ngầm, ví dụ `Integer` sang `Decimal`. Khi đó, type checker cần tìm một phép chuyển đổi được công bố và xác định kiểu kết quả.

```text
let average: Decimal = itemCount / 2.0
```

Không nên xem mọi chuyển đổi có thể lập trình được đều là chuyển đổi ngầm hợp lệ. Chuyển `String` sang `Date`, `Money` sang `Integer` hoặc `CustomerId` sang `OrderId` cần quy tắc rõ hoặc phải được viết tường minh.

### 3.4. Tương thích cấu trúc

Một số DSL dùng structural typing: hai kiểu tương thích nếu chúng có cấu trúc hoặc tập thuộc tính cần thiết, dù không cùng tên kiểu.

Ví dụ, hàm yêu cầu một giá trị có `name: String` và `email: EmailAddress` có thể nhận bất kỳ record nào đáp ứng hợp đồng đó. Điều này linh hoạt nhưng cần quy định rõ thuộc tính tùy chọn, khả năng ghi, subtype và cách kiểm tra trường lồng nhau.

## 4. Ràng buộc trong phép gán

Phép gán tạo ra quan hệ giữa kiểu của đích và kiểu của giá trị được gán. Với khai báo:

```text
let total: Money = order.total
```

compiler cần kiểm tra kiểu của `order.total` có thể được gán cho `Money` hay không.

### 4.1. Chiều tương thích

Thông thường, nếu biểu thức bên phải có kiểu `S` và vị trí bên trái yêu cầu kiểu `T`, cần kiểm tra:

```text
S <: T
```

Ký hiệu `S <: T` biểu thị `S` là subtype hoặc có thể được dùng thay cho `T` theo quan hệ kiểu của ngôn ngữ. Với kiểu invariant hoặc kiểu miền, quy tắc có thể yêu cầu tương thích chính xác hơn.

### 4.2. Gán vào thuộc tính

Ví dụ:

```text
entity Customer {
    age: Integer
    email: EmailAddress
}

customer.age = 30
customer.email = "not-an-email"
```

Phép gán đầu tiên có thể hợp lệ. Phép gán thứ hai không hợp lệ nếu `EmailAddress` là kiểu miền riêng và DSL không cho phép chuỗi tùy ý được gán trực tiếp. Người dùng cần tạo hoặc xác thực giá trị `EmailAddress` theo quy tắc.

### 4.3. Gán có thể thay đổi trạng thái

Kiểm tra kiểu không tự bảo đảm phép gán được phép về mặt nghiệp vụ. Một thuộc tính có thể đúng kiểu nhưng bất biến trong trạng thái hiện tại, chỉ đọc hoặc chỉ được sửa bởi một workflow nhất định. Type checking cần được phối hợp với kiểm tra quyền và ràng buộc miền, nhưng các nhóm kiểm tra này không nên bị nhầm lẫn.

## 5. Ràng buộc cho toán tử

Mỗi toán tử xác định những kiểu toán hạng mà nó hỗ trợ và kiểu kết quả. Có thể mô hình hóa quy tắc như một chữ ký toán tử.

| Toán tử | Kiểu toán hạng ví dụ | Kiểu kết quả |
|---|---|---|
| `+` | `Integer`, `Integer` | `Integer` |
| `+` | `Decimal`, `Decimal` | `Decimal` |
| `+` | `Money`, `Money` cùng currency | `Money` |
| `*` | `Money`, `Percentage` | `Money` |
| `>` | Hai `Date` | `Boolean` |
| `and` | `Boolean`, `Boolean` | `Boolean` |
| `not` | `Boolean` | `Boolean` |

Ví dụ hợp lệ:

```text
order.total + shipping.fee
order.createdAt > cutoffDate
order.isPaid and order.total > 0
```

Ví dụ có thể không hợp lệ:

```text
order.createdAt + customer.name
order.total and order.isPaid
```

### 5.1. Overload toán tử

Một toán tử có thể có nhiều chữ ký. Ví dụ `+` có thể cộng số, nối chuỗi hoặc cộng hai giá trị `Money` cùng currency. Khi gặp biểu thức, type checker tìm chữ ký phù hợp với kiểu thực tế của toán hạng.

Nếu có nhiều chữ ký phù hợp, cần quy tắc chọn overload rõ ràng. Nếu không có chữ ký phù hợp hoặc có nhiều lựa chọn ngang nhau, compiler báo lỗi thay vì tự chọn ngẫu nhiên.

### 5.2. Toán tử logic và Boolean nghiêm ngặt

DSL có thể yêu cầu điều kiện phải là Boolean:

```text
when order.isPaid and order.total > 0
```

Không nên tự động coi số `0`, chuỗi rỗng hoặc collection rỗng là `false` trừ khi DSL định nghĩa truthiness. Boolean nghiêm ngặt giúp điều kiện nghiệp vụ rõ và giảm nhầm lẫn giữa dữ liệu với quyết định.

### 5.3. Thứ tự đánh giá không phải ràng buộc kiểu

Precedence, associativity và short-circuit là các quy tắc cú pháp/ngữ nghĩa liên quan đến cách đánh giá. Chúng tương tác với type checking nhưng không thay thế ràng buộc kiểu. Một biểu thức có thể có kiểu hợp lệ nhưng vẫn cần nhóm ngoặc hoặc thứ tự thực thi được xác định rõ.

## 6. Ràng buộc trong lời gọi hàm

Mỗi hàm có chữ ký mô tả tên, tham số, kiểu tham số, kiểu trả về và có thể cả generic parameters.

```text
function calculateTax(amount: Money, rate: Percentage): Money
```

Khi gọi:

```text
calculateTax(order.total, 0.1)
```

compiler cần kiểm tra số lượng đối số, kiểu từng đối số và khả năng chuyển đổi. Nếu `0.1` được suy luận là `Decimal` nhưng tham số yêu cầu `Percentage`, DSL cần có quy tắc chuyển đổi rõ hoặc yêu cầu literal tỷ lệ tường minh.

### 6.1. Số lượng và thứ tự tham số

Với hàm có hai tham số, lời gọi cần cung cấp đủ hai giá trị theo đúng thứ tự hoặc theo tên tham số nếu DSL hỗ trợ named arguments.

```text
calculateTax(rate = 0.1, amount = order.total)
```

Named arguments giúp tránh nhầm thứ tự nhưng không bỏ qua kiểm tra kiểu. Tên tham số phải được phân giải và mỗi giá trị phải tương thích với kiểu tham số tương ứng.

### 6.2. Kiểu trả về

Nếu hàm khai báo trả về `Money`, mọi nhánh trả về phải tạo giá trị tương thích với `Money`:

```text
function discountFor(order: Order): Money {
    if order.isPremium {
        return order.total * 0.2
    }
    return order.total * 0.1
}
```

Nếu một nhánh trả về `String`, type checker phải báo lỗi. Nếu hàm không khai báo kiểu trả về, DSL có thể suy luận kiểu từ các câu lệnh `return`, nhưng các kiểu được suy luận phải có một kiểu chung hợp lệ.

### 6.3. Hàm có tác dụng phụ và kiểu Unit

Một hành động như `sendEmail(...)` có thể không tạo giá trị hữu ích. DSL có thể dùng kiểu `Unit` hoặc `Void` cho kết quả đó. Nếu một biểu thức yêu cầu giá trị `Boolean` mà nhận kết quả `Unit`, ràng buộc kiểu không được thỏa mãn.

## 7. Subtyping và quan hệ kiểu

Subtyping xác định quan hệ thay thế giữa các kiểu. Nếu `S` là subtype của `T`, giá trị kiểu `S` có thể được dùng ở vị trí yêu cầu `T` khi các điều kiện của hệ kiểu được đáp ứng.

### 7.1. Nominal typing

Với nominal typing, quan hệ kiểu dựa trên khai báo kế thừa hoặc quan hệ được định danh rõ:

```text
entity Employee extends Person {
    employeeId: EmployeeId
}
```

`Employee` là subtype của `Person` vì khai báo nói rõ quan hệ đó. Một kiểu có cùng thuộc tính nhưng không khai báo quan hệ có thể vẫn không được xem là subtype.

### 7.2. Structural typing

Với structural typing, khả năng tương thích dựa trên cấu trúc. Một giá trị có đủ thuộc tính và chữ ký hành vi mà kiểu yêu cầu có thể được chấp nhận.

```text
type Named = {
    name: String
}
```

Một record có `name: String` có thể tương thích với `Named` mà không cần khai báo `extends`. Cách này hữu ích cho DSL dữ liệu và schema nhưng cần quy tắc rõ về thuộc tính mutable và tính tương thích sâu.

### 7.3. Liskov substitution principle

Khi dùng subtype, giá trị subtype cần có thể thay thế giá trị supertype mà không phá vỡ hợp đồng mà nơi sử dụng mong đợi. Nếu subtype siết điều kiện đầu vào quá mức hoặc làm yếu bảo đảm đầu ra, quan hệ thay thế có thể không an toàn.

Type checker có thể kiểm tra một số quy tắc chữ ký, nhưng tính đúng đắn nghiệp vụ của subtype còn phụ thuộc semantics và thiết kế mô hình miền.

## 8. Variance trong generic types

Generic type có tham số kiểu, ví dụ `List<Order>` hoặc `Handler<Customer>`. Khi xét quan hệ subtype giữa các kiểu generic, cần xác định variance.

### 8.1. Invariance

Với invariant generic, `List<Dog>` không được xem là subtype của `List<Animal>`, dù `Dog` là subtype của `Animal`. Điều này tránh tình huống có thể thêm một `Cat` vào danh sách vốn chỉ chứa `Dog`.

### 8.2. Covariance

Covariance cho phép quan hệ subtype đi cùng chiều với tham số kiểu. Nếu `Dog <: Animal`, một kiểu chỉ đọc `Producer<Dog>` có thể được dùng ở nơi yêu cầu `Producer<Animal>` nếu API không cho phép ghi giá trị `Animal` vào producer.

### 8.3. Contravariance

Contravariance đảo chiều quan hệ kiểu. Một handler có thể xử lý mọi `Animal` cũng có thể xử lý `Dog`, nên `Handler<Animal>` có thể được dùng ở vị trí yêu cầu `Handler<Dog>` nếu semantics của hàm phù hợp.

| Variance | Quan hệ khi `Dog <: Animal` | Ví dụ khái quát |
|---|---|---|
| Invariant | Không suy ra quan hệ giữa `Box<Dog>` và `Box<Animal>` | Collection có thể đọc và ghi |
| Covariant (`out`) | `Producer<Dog> <: Producer<Animal>` | Nguồn chỉ trả về giá trị |
| Contravariant (`in`) | `Consumer<Animal> <: Consumer<Dog>` | Bộ nhận chỉ tiêu thụ giá trị |

Không phải DSL nào cũng cần generic variance. Nhưng nếu hỗ trợ generic, đặc tả phải nói rõ tham số kiểu có invariant, covariant hay contravariant để type checker quyết định tương thích nhất quán.

## 9. Suy luận kiểu và ràng buộc chưa biết

DSL có thể cho phép người dùng bỏ qua một số chú thích kiểu. Compiler khi đó cần suy luận kiểu từ cách giá trị được tạo và sử dụng.

Ví dụ:

```text
let quantity = 10
let label = "priority"
```

Compiler có thể suy luận `quantity: Integer` và `label: String` dựa trên literal.

### 9.1. Type variables

Trong quá trình suy luận, compiler có thể tạo biến kiểu chưa biết, thường ký hiệu `α`, `β` hoặc `T`.

```text
let value = expression
```

Ban đầu, kiểu của `value` có thể là `α`. Khi biết `expression` có kiểu `Money`, compiler thêm ràng buộc `α = Money` và giải quyết biến kiểu.

### 9.2. Unification

Unification là quá trình tìm cách làm cho hai biểu thức kiểu tương thích bằng cách xác định các biến kiểu chưa biết.

Ví dụ:

```text
α = Integer
List<α> = List<Integer>
```

Có thể hợp nhất `α` với `Integer`. Nhưng nếu cùng một biến kiểu phải đồng thời bằng `Integer` và `String`, hệ thống phát hiện mâu thuẫn.

### 9.3. Ràng buộc subtype

Không phải mọi hệ kiểu chỉ dùng phép bằng nhau. Với subtype, compiler có thể tạo điều kiện `α <: Animal` thay vì `α = Animal`. Bộ giải ràng buộc cần xử lý các quan hệ kiểu phù hợp với mô hình ngôn ngữ.

### 9.4. Ràng buộc từ nhiều vị trí sử dụng

Ví dụ:

```text
let value = readValue()
print(value)
let total: Money = value
```

Các nơi sử dụng có thể tạo nhiều điều kiện cho kiểu của `value`. Type inference kết hợp chúng để tìm kiểu hợp lệ hoặc báo lỗi khi chúng không thể cùng đúng.

## 10. Kiểu của nhánh điều kiện và biểu thức kết hợp

Khi một biểu thức có nhiều nhánh tạo ra giá trị, các nhánh cần có kiểu chung phù hợp.

```text
let result = if order.isPaid {
    order.total
} else {
    Money(0, order.currency)
}
```

Cả hai nhánh đều có thể trả về `Money`, nên kiểu của `result` là `Money`.

Nếu một nhánh trả `Money` và nhánh còn lại trả `String`, compiler cần tìm kiểu chung được định nghĩa hoặc báo lỗi. Một số ngôn ngữ dùng least upper bound (LUB), tức kiểu chung gần nhất trong hệ subtype; DSL có thể dùng quy tắc khác nhưng phải nhất quán.

### 10.1. Kiểu kết quả của collection literal

Với danh sách:

```text
values = [1, 2, 3]
```

compiler có thể suy luận `List<Integer>`. Nếu danh sách là `[1, 2.5]`, kết quả phụ thuộc quy tắc numeric promotion: có thể là `List<Decimal>` nếu `Integer` được nâng lên `Decimal`, hoặc lỗi nếu DSL yêu cầu đồng nhất chính xác.

### 10.2. Kiểu của null và optional

Nếu một nhánh trả `Money` và nhánh khác trả `null`, kiểu kết quả có thể là `Money?` hoặc `Optional<Money>`. Ràng buộc cần biểu diễn khả năng vắng mặt để nơi sử dụng phải xử lý null trước khi dùng như `Money` chắc chắn.

## 11. Nullability và ràng buộc kiểu

Nullability mô tả một kiểu có thể chứa giá trị null hoặc thiếu hay không. DSL có thể phân biệt kiểu không-null và kiểu nullable:

```text
customer.email: EmailAddress
customer.backupEmail: EmailAddress?
```

`email` bắt buộc có giá trị; `backupEmail` có thể vắng mặt. Khi truyền `EmailAddress?` vào hàm yêu cầu `EmailAddress`, type checker phải yêu cầu kiểm tra hoặc xử lý giá trị null.

### 11.1. Type narrowing

Sau một phép kiểm tra:

```text
if customer.backupEmail != null {
    sendEmail(customer.backupEmail)
}
```

compiler có thể thu hẹp kiểu của `backupEmail` bên trong nhánh đúng từ `EmailAddress?` thành `EmailAddress`. Cơ chế này được gọi là type narrowing hoặc flow-sensitive typing.

### 11.2. Kiểm tra flow-sensitive

Việc thu hẹp chỉ an toàn nếu giá trị không bị thay đổi theo cách làm mất bảo đảm giữa lúc kiểm tra và lúc sử dụng. Với biến mutable, thuộc tính có getter động hoặc dữ liệu chia sẻ giữa nhiều luồng, compiler có thể cần kiểm tra lại hoặc không cho thu hẹp lâu dài.

### 11.3. Null khác với giá trị nghiệp vụ

Null, chuỗi rỗng, số 0 và trạng thái `UNKNOWN` không nhất thiết cùng nghĩa. Ràng buộc kiểu cần giữ được các khác biệt có ý nghĩa trong miền để tránh chấp nhận dữ liệu sai.

## 12. Refinement types và ràng buộc miền

Kiểu cơ bản đôi khi chưa đủ để mô tả điều kiện hợp lệ. Ví dụ, `Integer` có thể chứa mọi số nguyên, nhưng số lượng sản phẩm phải không âm; `Percentage` có thể cần nằm trong khoảng từ 0 đến 100.

Refinement type (kiểu tinh chỉnh) kết hợp kiểu cơ sở với một điều kiện logic:

```text
type PositiveInteger = Integer where value > 0
type DiscountRate = Decimal where value >= 0 and value <= 1
```

Khi gán hoặc truyền giá trị vào vị trí yêu cầu `PositiveInteger`, compiler hoặc runtime cần chứng minh hoặc kiểm tra điều kiện `value > 0`.

### 12.1. Kiểm tra tĩnh và kiểm tra động cho refinement

Nếu giá trị là literal đã biết, compiler có thể kiểm tra ngay:

```text
let count: PositiveInteger = 5    // hợp lệ
let invalid: PositiveInteger = 0  // lỗi tĩnh
```

Nếu giá trị đến từ dữ liệu runtime, điều kiện cần được xác thực khi dữ liệu được đọc hoặc trước khi sử dụng. Có thể tạo một constructor/validator chỉ trả về refinement value khi điều kiện đúng.

### 12.2. Kiểu miền (domain types)

Kiểu miền biểu đạt ý nghĩa nghiệp vụ rõ hơn kiểu lưu trữ:

- `CustomerId` và `OrderId` có thể đều được lưu bằng chuỗi nhưng không thể thay thế tùy ý.
- `Money` bao gồm số tiền và currency.
- `Percentage` biểu diễn tỷ lệ với miền giá trị cụ thể.
- `EmailAddress` là chuỗi đã qua kiểm tra định dạng.
- `Duration` và `Instant` biểu diễn hai khái niệm thời gian khác nhau.

Ràng buộc kiểu ngăn việc dùng nhầm các giá trị có cùng representation nhưng khác ý nghĩa.

## 13. Đơn vị đo và phép toán có kiểu

Trong DSL kỹ thuật, khoa học hoặc tài chính, đơn vị đo là một phần quan trọng của hệ kiểu.

Ví dụ:

```text
distance: Meter
duration: Second
speed = distance / duration
```

Kết quả có đơn vị `Meter / Second`. Cộng `Meter` với `Second` là không hợp lệ, dù cả hai có thể được biểu diễn bằng số thực.

### 13.1. Tiền tệ

`Money(100, VND)` và `Money(100, USD)` không nên được cộng trực tiếp nếu chưa có quy tắc quy đổi. Một phép cộng tiền có thể yêu cầu cùng currency:

```text
Money<VND> + Money<VND> -> Money<VND>
```

Phép quy đổi tiền tệ cần tỷ giá, nguồn tỷ giá và thời điểm áp dụng; đó là semantics nghiệp vụ bổ sung chứ không phải một phép ép kiểu đơn giản.

### 13.2. Kích thước và độ chính xác

Với Decimal, compiler/runtime cần quy định precision, scale, rounding mode và overflow. Hai giá trị cùng kiểu `Decimal` vẫn có thể không phù hợp với một phép tính nếu đơn vị hoặc độ chính xác khác nhau.

## 14. Generic constraints và giới hạn tham số kiểu

Generic cho phép viết cấu trúc dùng được với nhiều kiểu. Tuy nhiên, thân generic chỉ có thể sử dụng những thao tác được bảo đảm bởi ràng buộc của tham số kiểu.

Ví dụ:

```text
function max<T: Comparable>(left: T, right: T): T {
    if left > right { left } else { right }
}
```

Ràng buộc `T: Comparable` nói rằng kiểu `T` phải hỗ trợ phép so sánh. Nếu không có ràng buộc, compiler không thể giả định `left > right` là hợp lệ cho mọi kiểu.

### 14.1. Ràng buộc interface hoặc trait

DSL có thể yêu cầu tham số kiểu triển khai một interface hoặc trait:

```text
function serialize<T: Serializable>(value: T): String
```

Khi gọi hàm với kiểu `Order`, compiler kiểm tra `Order` có thỏa `Serializable` không. Nếu không, lời gọi bị từ chối.

### 14.2. Ràng buộc nhiều điều kiện

Một tham số kiểu có thể cần nhiều khả năng:

```text
function summarize<T: Comparable & Serializable>(items: List<T>): String
```

Ký hiệu chỉ mang tính minh họa. DSL cần quy định cú pháp và cách kết hợp constraints, đồng thời báo lỗi cụ thể khi thiếu một khả năng.

### 14.3. Ràng buộc kiểu và ràng buộc giá trị

Generic constraint thường giới hạn kiểu, chẳng hạn `T` phải là `Comparable`. Refinement hoặc predicate constraint có thể giới hạn giá trị cụ thể. Hai dạng này có mục đích khác nhau và có thể cần hai cơ chế kiểm tra riêng.

## 15. Overload resolution và ràng buộc kiểu

Khi có nhiều hàm cùng tên, compiler phải chọn overload phù hợp với kiểu đối số.

```text
function format(value: Money): String
function format(value: Date): String
function format(value: Customer): String
```

Lời gọi `format(order.total)` có thể chọn phiên bản nhận `Money` nếu `order.total` có kiểu đó.

### 15.1. Xếp hạng ứng viên

Một chính sách overload có thể xếp hạng:

1. Khớp kiểu chính xác.
2. Khớp qua subtype.
3. Khớp qua chuyển đổi ngầm được cho phép.
4. Các chuyển đổi có chi phí cao hơn nếu DSL có quy định.

Ứng viên tốt nhất phải được xác định duy nhất. Nếu hai ứng viên có cùng mức phù hợp, compiler nên báo lời gọi mơ hồ.

### 15.2. Không chọn overload dựa trên ép kiểu tùy tiện

Nếu `format(String)` và `format(Date)` đều có thể nhận đầu vào sau những chuyển đổi ngầm khác nhau, việc lựa chọn cần có quy tắc công bố. Tránh để kết quả phụ thuộc thứ tự khai báo hàm.

### 15.3. Diagnostic cho overload không phù hợp

Thông báo tốt nên nêu chữ ký đã thử và lý do từng ứng viên bị loại, ví dụ đối số thứ hai cần `Percentage` nhưng nhận `String`. Điều này giúp người dùng sửa đúng kiểu thay vì chỉ nhận “no matching function”.

## 16. Bộ giải ràng buộc kiểu

Trong DSL có suy luận kiểu hoặc generic, compiler thường tạo một tập ràng buộc rồi giải chúng.

Một quy trình khái quát:

1. Duyệt AST và xác định kiểu của literal, identifier và node cơ bản.
2. Tạo biến kiểu cho biểu thức chưa biết kiểu.
3. Thêm ràng buộc từ phép gán, toán tử, lời gọi hàm và ngữ cảnh sử dụng.
4. Giải ràng buộc bằng equality, subtype hoặc conversion rules.
5. Gán kiểu suy luận được cho node.
6. Báo lỗi nếu ràng buộc mâu thuẫn hoặc không đủ thông tin.

### 16.1. Ví dụ tạo ràng buộc

```text
let amount = order.total
let tax = amount * rate
calculateTax(tax)
```

Giả sử `order.total: Money`, `rate: Percentage`, và `calculateTax` yêu cầu `Money`. Bộ kiểm tra có thể tạo:

```text
type(amount) = Money
type(tax) = type(amount) * type(rate)
type(calculateTax.argument1) = Money
type(tax) must be compatible with Money
```

Nếu chữ ký phép nhân định nghĩa `Money * Percentage -> Money`, mọi ràng buộc đều được thỏa mãn. Nếu `rate` là `String`, bộ giải không tìm được phép toán phù hợp và báo lỗi tại biểu thức nhân.

### 16.2. Mâu thuẫn ràng buộc

Ví dụ:

```text
let value = 10
value = "ten"
```

Nếu DSL quy định biến có một kiểu ổn định, lần gán đầu tạo ràng buộc `type(value) = Integer`; lần gán sau tạo `type(value) = String`. Hai ràng buộc mâu thuẫn và chương trình không hợp lệ.

Nếu DSL cho phép biến động, cách diễn giải khác: kiểu của binding có thể thay đổi theo giá trị tại runtime. Khi đó không thể áp dụng quy tắc single-type inference nói trên; ngôn ngữ phải xác định rõ mô hình biến.

### 16.3. Ràng buộc không đủ thông tin

Có trường hợp compiler không thể xác định một kiểu duy nhất:

```text
let empty = []
```

Kiểu phần tử của danh sách chưa biết. DSL có thể yêu cầu chú thích kiểu `List<Order>`, suy luận từ ngữ cảnh sử dụng hoặc gán kiểu tổng quát như `List<Never>` nếu hệ kiểu định nghĩa cách đó.

Không nên tự chọn một kiểu tùy ý vì điều đó có thể làm thay đổi cách kiểm tra ở những nơi sử dụng sau.

## 17. Ràng buộc kiểu và dữ liệu từ bên ngoài

Khai báo kiểu trong DSL không bảo đảm dữ liệu thực tế từ JSON, database, API hoặc plugin tuân theo khai báo. Tại ranh giới nhập dữ liệu, cần validation.

Ví dụ schema:

```text
CustomerInput {
    name: String
    age: Integer where age >= 0
    email: EmailAddress?
}
```

Khi nhận dữ liệu:

```json
{
  "name": "Lan",
  "age": "twenty",
  "email": null
}
```

validator cần phát hiện `age` là chuỗi thay vì số nguyên. `email` có thể hợp lệ nếu kiểu cho phép null. Thông báo nên nêu đường dẫn trường, kiểu mong đợi, kiểu thực tế và điều kiện miền bị vi phạm.

### 17.1. Kiểm tra nông và sâu

Kiểm tra nông xác nhận kiểu ngoài cùng, chẳng hạn giá trị là object hoặc list. Kiểm tra sâu xác thực từng thuộc tính và phần tử lồng nhau. DSL cần quy định mức kiểm tra và thời điểm thực hiện, đặc biệt với collection lớn hoặc dữ liệu lazy.

### 17.2. Validate một lần hay kiểm tra khi dùng?

Nếu dữ liệu bất biến sau khi xác thực, kết quả validation có thể được tin cậy trong vòng đời của đối tượng. Nếu dữ liệu mutable hoặc đến từ nguồn thay đổi, cần kiểm tra lại ở điểm sử dụng hoặc dùng wrapper bảo đảm hợp đồng kiểu.

## 18. Ràng buộc kiểu và kiểm tra runtime

Không phải mọi ràng buộc đều có thể giải quyết tĩnh. Khi kiểu hoặc giá trị chỉ được biết lúc chạy, runtime cần kiểm tra điều kiện tương ứng.

Ví dụ, DSL có thể cho phép tham số `Dynamic` được truyền vào hàm yêu cầu `Money`. Runtime kiểm tra giá trị thực tế trước khi gọi hàm. Nếu không tương thích, phát sinh `TypeError` hoặc trả về kiểu kết quả có lỗi.

### 18.1. Kết hợp static và dynamic checks

Một chiến lược thực tế:

- Kiểm tra tĩnh các khai báo, biểu thức và chữ ký có đủ thông tin.
- Ghi nhận những ràng buộc chưa thể giải quyết trước khi chạy.
- Chèn runtime check ở ranh giới dữ liệu động hoặc plugin.
- Báo lỗi với source span của biểu thức gốc khi runtime check thất bại.

### 18.2. Không nhầm lỗi kiểu với lỗi nghiệp vụ

Giá trị `Money` có thể đúng kiểu nhưng vượt ngân sách. Đây là lỗi ràng buộc nghiệp vụ, không phải lỗi kiểu. Ngược lại, truyền `String` vào vị trí yêu cầu `Money` là lỗi kiểu.

Phân biệt hai loại giúp thông báo, chính sách xử lý và công cụ theo dõi chính xác hơn.

## 19. Chẩn đoán lỗi ràng buộc kiểu

Một diagnostic kiểu nên cho biết biểu thức nào không thỏa ràng buộc và các kiểu liên quan.

Ví dụ:

```text
Type mismatch at rules/shipping.dsl:18:24
Expected: Money
Found: String
Expression: order.total + "free"
Reason: operator "+" has no applicable signature for Money and String.
```

Thông báo tốt có thể bao gồm:

- Vị trí biểu thức hoặc đối số gây lỗi.
- Kiểu mong đợi và kiểu thực tế.
- Ràng buộc hoặc chữ ký không được thỏa.
- Vị trí khai báo kiểu hoặc hàm liên quan.
- Gợi ý chuyển đổi hoặc cách viết đúng nếu xác định được.

### 19.1. Báo lỗi tại vị trí phù hợp

Nếu kiểu sai bắt nguồn từ đối số, nên trỏ vào đối số đó. Nếu vấn đề là chữ ký hàm hoặc khai báo generic, có thể thêm related location trỏ đến khai báo.

### 19.2. Tránh lỗi dây chuyền

Một biểu thức sai kiểu có thể khiến các biểu thức cha không xác định được kiểu. Type checker nên dùng một kiểu lỗi hoặc unknown type để tiếp tục phân tích có kiểm soát, tránh báo hàng loạt lỗi phụ không giúp người dùng.

### 19.3. Gợi ý sửa có cơ sở

Compiler có thể gợi ý `toMoney(...)` hoặc `parseInteger(...)` nếu DSL có hàm chuyển đổi phù hợp. Không nên tự chèn chuyển đổi có thể làm thay đổi semantics hoặc dữ liệu mà người viết không nhận ra.

## 20. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ so sánh kiểu theo representation | Dễ trộn `CustomerId`, `OrderId`, `Money` và số thuần | Dùng kiểu miền riêng và quan hệ tương thích rõ |
| Coercion ngầm quá rộng | Dữ liệu sai được chấp nhận âm thầm | Giới hạn chuyển đổi và yêu cầu chuyển đổi tường minh |
| Không định nghĩa overload resolution | Một lời gọi có thể chọn kết quả khác nhau | Quy định xếp hạng và báo ambiguity |
| Bỏ qua nullability | Lỗi null xuất hiện ở runtime | Mô hình hóa kiểu optional và flow narrowing |
| Không xác định variance | Generic có thể cho phép ghi giá trị không an toàn | Định nghĩa invariant/covariant/contravariant |
| Trộn lỗi kiểu với lỗi nghiệp vụ | Diagnostic không đúng nguyên nhân | Phân loại type constraints và domain constraints |
| Suy luận kiểu thiếu quy tắc | Cùng biểu thức có thể được hiểu khác nhau | Đặc tả inference, unification và trường hợp mơ hồ |
| Chỉ kiểm tra dữ liệu lúc khai báo | Dữ liệu ngoài có thể vi phạm kiểu | Validate tại ranh giới runtime |
| Không giữ source location | Khó tìm vị trí ràng buộc thất bại | Gắn span và related locations cho type diagnostics |

## 21. Quy trình kiểm tra ràng buộc kiểu trong DSL

Một type checker có thể tổ chức theo các bước:

1. **Thu thập khai báo:** đọc kiểu entity, thuộc tính, hàm, rule và generic parameter.
2. **Phân giải tên:** xác định identifier tham chiếu đến symbol nào.
3. **Gán kiểu cơ bản:** xác định kiểu của literal, identifier và truy cập thuộc tính.
4. **Tạo ràng buộc:** thêm điều kiện từ gán, toán tử, lời gọi hàm, nhánh và collection.
5. **Giải ràng buộc:** áp dụng equality, subtype, variance và conversion rules.
6. **Kiểm tra refinement:** xác thực miền giá trị nếu có thể chứng minh tĩnh; nếu không, yêu cầu runtime validation.
7. **Gắn kiểu kết quả:** ghi kiểu đã xác định vào AST hoặc semantic model.
8. **Phát diagnostic:** báo các ràng buộc mâu thuẫn hoặc chưa giải quyết được.
9. **Chuẩn bị runtime checks:** đánh dấu những điểm cần xác thực động.

Không phải compiler nào cũng cần một constraint solver tổng quát. DSL có hệ kiểu đơn giản có thể kiểm tra trực tiếp từng node. Khi có generic, subtype và inference phức tạp, mô hình ràng buộc tường minh thường giúp tổ chức thuật toán tốt hơn.

## 22. Kiểm thử ràng buộc kiểu

Bộ kiểm thử nên xác nhận cả trường hợp hợp lệ, không hợp lệ và trường hợp biên.

Các nhóm test hữu ích:

- Gán cùng kiểu và gán subtype.
- Gán kiểu không tương thích.
- Toán tử với mọi tổ hợp kiểu được hỗ trợ và không được hỗ trợ.
- Gọi hàm đúng/sai số lượng và kiểu đối số.
- Kiểu trả về ở nhiều nhánh.
- Generic constraint và variance.
- Type inference với một và nhiều ràng buộc.
- Ràng buộc mâu thuẫn hoặc thiếu thông tin.
- Nullability và type narrowing.
- Refinement type với giá trị biên.
- Tiền tệ, đơn vị đo và precision.
- Dữ liệu ngoài không tuân theo schema.
- Runtime checks và diagnostic tại source location.

Với các phép biến đổi kiểu hoặc overload phức tạp, nên có test chứng minh cùng một chương trình luôn chọn cùng chữ ký và tạo cùng kiểu kết quả theo đặc tả.

## 23. Nguyên tắc thiết kế ràng buộc kiểu cho DSL

Khi thiết kế hệ kiểu, có thể áp dụng các nguyên tắc sau:

1. **Định nghĩa rõ kiểu và quan hệ kiểu.** Nêu kiểu cơ bản, kiểu miền, subtype, optional và generic.
2. **Công bố chữ ký toán tử và hàm.** Xác định kiểu đầu vào, kiểu kết quả và overload được hỗ trợ.
3. **Quy định chuyển đổi.** Phân biệt chuyển đổi ngầm với chuyển đổi tường minh, giới hạn coercion.
4. **Mô hình hóa miền nghiệp vụ.** Dùng `Money`, `Percentage`, `CustomerId` hoặc refinement type khi representation giống nhau nhưng ý nghĩa khác.
5. **Xác định nullability.** Không gộp null, thiếu, rỗng và unknown nếu nghiệp vụ cần phân biệt.
6. **Đặc tả generic variance.** Cho biết tham số kiểu invariant, covariant hay contravariant.
7. **Định nghĩa suy luận kiểu.** Nêu cách tạo, giải và báo ràng buộc mơ hồ.
8. **Kiểm tra ở ranh giới dữ liệu.** Xác thực nguồn ngoài và plugin trước khi dùng.
9. **Giữ diagnostic có cấu trúc.** Nêu kiểu mong đợi, kiểu thực tế, vị trí và nguyên nhân.
10. **Phân biệt lỗi kiểu với lỗi miền.** Kiểu đúng không đồng nghĩa giá trị đáp ứng mọi quy tắc nghiệp vụ.

## 24. Kết luận

Ràng buộc kiểu là những điều kiện xác định các giá trị và biểu thức có thể được kết hợp an toàn theo hệ kiểu của DSL. Chúng xuất hiện trong phép gán, toán tử, lời gọi hàm, giá trị trả về, collection, nhánh điều kiện, generic và dữ liệu miền.

Type checker có thể dùng tương thích chính xác, subtype, structural typing, chuyển đổi, suy luận và unification để giải các ràng buộc. Những cơ chế như nullability, refinement type, đơn vị đo và generic constraints giúp mô hình hóa chính xác hơn dữ liệu mà DSL phục vụ.

Một DSL đáng tin cậy cần định nghĩa ràng buộc rõ ràng, kiểm tra chúng trước khi thực hiện tác động, xác thực dữ liệu ở ranh giới runtime và đưa ra diagnostic có thể hành động. Nhờ đó, lỗi kiểu được phát hiện đúng lúc, các thao tác có ý nghĩa hơn và mô hình miền được bảo vệ nhất quán.
