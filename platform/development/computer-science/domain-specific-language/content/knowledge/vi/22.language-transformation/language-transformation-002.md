# Desugaring

Trong quá trình biến đổi ngôn ngữ (*language transformation*), **desugaring** là bước chuyển những cấu trúc cú pháp thuận tiện, giàu tính biểu đạt hoặc chuyên biệt thành các cấu trúc đơn giản hơn đã được ngôn ngữ lõi hỗ trợ. Cấu trúc ban đầu thường được gọi là *syntactic sugar* (cú pháp đường), còn dạng sau khi chuyển đổi là biểu diễn lõi (*core representation* hoặc *core language*).

Ví dụ, một DSL có thể cho phép viết vòng lặp ngắn:

```text
repeat 3 times {
    send("hello")
}
```

Nếu ngôn ngữ lõi chỉ có biến, điều kiện và vòng lặp `while`, compiler có thể chuyển cấu trúc `repeat` thành một biến đếm cùng vòng lặp `while`. Các giai đoạn kiểm tra, tối ưu hóa và sinh mã phía sau chỉ cần xử lý dạng lõi.

Desugaring giúp DSL có cú pháp dễ đọc cho người dùng miền nghiệp vụ mà không buộc compiler phải có một cơ chế thực thi riêng cho mọi dạng cú pháp tiện lợi. Nó cũng tạo ra một ranh giới rõ giữa ngôn ngữ bề mặt (*surface language*) và ngôn ngữ lõi.

Điều quan trọng là phép biến đổi phải giữ nguyên ý nghĩa chương trình theo hợp đồng của DSL. Một phép desugaring sai có thể thay đổi thứ tự đánh giá, số lần thực hiện biểu thức, phạm vi biến, xử lý lỗi hoặc tác dụng phụ.

## 1. Syntactic sugar và ngôn ngữ lõi

Syntactic sugar là cú pháp được bổ sung để người viết diễn đạt một ý tưởng ngắn gọn hoặc tự nhiên hơn. Thông thường, nó không làm tăng sức biểu đạt tính toán của ngôn ngữ lõi vì có thể được chuyển thành những cấu trúc đã tồn tại.

Ví dụ, nếu DSL hỗ trợ:

```text
when user.isActive {
    grantAccess(user)
}
```

nhưng core language chỉ có `if`, desugaring có thể tạo:

```text
if user.isActive {
    grantAccess(user)
}
```

Trong trường hợp này, `when` chỉ là cách viết khác của điều kiện `if` theo quy tắc đã định.

### 1.1. Surface language

Surface language là tập cú pháp mà người dùng DSL trực tiếp viết. Nó có thể bao gồm:

- Cấu trúc điều khiển chuyên biệt theo miền.
- Cú pháp khai báo rút gọn.
- Toán tử tiện lợi.
- Cấu trúc truy vấn hoặc pipeline.
- Cú pháp mặc định, tùy chọn hoặc bao gói tài nguyên.
- Cú pháp gần với ngôn ngữ nghiệp vụ.

Surface language ưu tiên khả năng đọc và cách diễn đạt tự nhiên của người dùng.

### 1.2. Core language

Core language là tập cấu trúc nền tảng mà các giai đoạn sau của compiler hiểu. Nó thường nhỏ hơn surface language và có ngữ nghĩa đơn giản, thống nhất.

Một core language có thể chỉ bao gồm:

- Literal và biến.
- Khai báo và truy cập biến.
- Hàm và lời gọi hàm.
- Biểu thức toán học và logic cơ bản.
- Điều kiện và vòng lặp.
- Khối lệnh và điều khiển luồng.
- Kiểu dữ liệu, tham chiếu và thao tác nền tảng.

Không có một danh sách core language chung cho mọi DSL. Core được lựa chọn theo mục tiêu của compiler và miền ứng dụng.

### 1.3. Quan hệ giữa hai dạng

```text
Surface DSL
    |
    | parse
    v
Surface AST
    |
    | desugar
    v
Core AST
    |
    | semantic analysis / optimization
    v
IR or executable representation
    |
    v
Target code
```

Một số compiler thực hiện name resolution hoặc type checking trước desugaring; một số thực hiện một phần sau đó. Thứ tự cụ thể tùy cấu trúc AST, kiểu cú pháp và các quy tắc cần áp dụng. Điểm cốt lõi là những cấu trúc bề mặt được chuyển thành biểu diễn mà các bước tiếp theo có thể xử lý nhất quán.

## 2. Vì sao cần desugaring?

Nếu mọi cú pháp bề mặt đều có đường thực thi riêng, compiler và runtime có thể trở nên phức tạp. Mỗi tính năng cần parser, semantic checks, optimizer, code generator, debugger và tooling riêng.

Desugaring mang lại một số lợi ích:

- **Giảm kích thước core language:** nhiều cú pháp tiện lợi dùng chung một số cấu trúc lõi.
- **Tái sử dụng các giai đoạn sau:** type checker, optimizer và backend chỉ cần hiểu core nodes.
- **Tách cú pháp khỏi thực thi:** người thiết kế có thể cải thiện cách viết mà ít thay đổi runtime.
- **Tạo quy tắc ngữ nghĩa nhất quán:** các dạng bề mặt tương đương được xử lý qua cùng cơ chế lõi.
- **Hỗ trợ nhiều backend:** một core representation có thể được sinh mã cho nhiều nền tảng.
- **Đơn giản hóa kiểm thử:** có thể kiểm tra phép biến đổi bề mặt sang lõi độc lập với backend.

Ví dụ, DSL workflow có thể có cú pháp `retry`, `transaction`, `unless` và `for each`. Nếu chúng đều được hạ về các node điều kiện, vòng lặp, lời gọi hàm và khối xử lý lỗi, backend không cần hiểu từng từ khóa bề mặt.

## 3. Desugaring khác parsing và code generation như thế nào?

Các giai đoạn này có liên quan nhưng làm những công việc khác nhau.

| Giai đoạn | Nhiệm vụ | Ví dụ đầu ra |
|---|---|---|
| Lexing | Chuyển ký tự thành token | `IF`, `IDENTIFIER`, `LBRACE` |
| Parsing | Xây cấu trúc cú pháp | Surface AST có node `Repeat` |
| Desugaring | Chuyển cú pháp tiện lợi thành cấu trúc lõi | `Let`, `While`, `If` |
| Semantic analysis | Phân giải tên, kiểm tra kiểu và quy tắc | AST có symbol/type information |
| Lowering | Chuyển cấu trúc cấp cao sang IR thấp hơn | Basic blocks, temporaries |
| Code generation | Sinh mã cho target | Bytecode, JavaScript, native code |

Ranh giới giữa desugaring và lowering không phải lúc nào cũng tuyệt đối. Trong một compiler, desugaring có thể là một phần của lowering. Tuy nhiên, về mặt khái niệm, desugaring thường tập trung vào việc loại bỏ cú pháp đường ở mức ngôn ngữ, còn lowering có thể tiếp tục chuyển cấu trúc lõi sang biểu diễn gần máy hoặc runtime hơn.

### 3.1. Parsing không tự động loại bỏ cú pháp đường

Parser có thể tạo node riêng cho cú pháp bề mặt:

```text
RepeatStatement(count, body)
```

Node đó giữ được ý định ban đầu của người viết. Desugaring là bước tiếp theo chuyển nó thành các node core.

### 3.2. Desugaring không nhất thiết sinh mã máy

Sau desugaring, chương trình vẫn có thể ở dạng AST. Compiler chưa cần quyết định thanh ghi, địa chỉ bộ nhớ hoặc lệnh máy.

### 3.3. Một phép biến đổi có thể gồm nhiều bước

Một cấu trúc bề mặt có thể được chuyển qua một hoặc nhiều biểu diễn trung gian:

```text
Surface AST -> Normalized AST -> Core AST -> IR
```

Tách thành nhiều bước giúp mỗi phép biến đổi có phạm vi rõ, dễ truy vết và dễ xác định lỗi.

## 4. Ví dụ đơn giản: cú pháp `unless`

Một DSL có thể hỗ trợ:

```text
unless user.isBlocked {
    allowRequest(user)
}
```

Nếu core language chỉ có `if`, có thể chuyển thành:

```text
if not user.isBlocked {
    allowRequest(user)
}
```

Quy tắc chuyển đổi:

```text
Unless(condition, body)
    => If(Not(condition), body, EmptyBlock)
```

Trong đó `EmptyBlock` là nhánh else rỗng nếu core AST yêu cầu đủ hai nhánh. Nếu core AST cho phép else tùy chọn, không cần node rỗng.

Phép biến đổi này đơn giản vì điều kiện chỉ được đánh giá một lần trong cả hai dạng. Nếu DSL có quy tắc đặc biệt về giá trị null hoặc truthiness, `not` phải giữ đúng quy tắc đó.

## 5. Desugaring vòng lặp `repeat`

Giả sử DSL hỗ trợ:

```text
repeat 3 times {
    log("step")
}
```

Core language có biến, phép so sánh, phép tăng và `while`. Một phép desugaring có thể tạo:

```text
let counter = 0
while counter < 3 {
    log("step")
    counter = counter + 1
}
```

### 5.1. Quy tắc chuyển đổi

Có thể mô tả bằng quy tắc:

```text
Repeat(count, body)
    => Let(temp, 0,
           While(temp < count,
                 Block(body, temp = temp + 1)))
```

Đây là mô tả khái niệm. Trong triển khai thực tế, cần xử lý giá trị `count`, kiểu của bộ đếm, tên biến tạm, overflow và quy tắc khi số lần lặp âm hoặc không phải số nguyên.

### 5.2. Đánh giá biểu thức số lần lặp đúng một lần

Xét:

```text
repeat calculateLimit() times {
    work()
}
```

Nếu phép desugaring tạo:

```text
while counter < calculateLimit() {
    work()
    counter = counter + 1
}
```

thì `calculateLimit()` được gọi ở mỗi lần kiểm tra điều kiện. Điều này khác với một cấu trúc `repeat` có ngữ nghĩa đánh giá số lần lặp đúng một lần trước khi bắt đầu.

Để giữ ngữ nghĩa, cần lưu kết quả vào biến tạm:

```text
let limit = calculateLimit()
let counter = 0
while counter < limit {
    work()
    counter = counter + 1
}
```

Đây là ví dụ quan trọng cho thấy desugaring không chỉ là thay từ khóa bằng một đoạn mã trông tương tự. Nó phải giữ số lần đánh giá và tác dụng phụ của biểu thức.

## 6. Desugaring phép gán kết hợp

Một DSL có thể hỗ trợ toán tử gán kết hợp:

```text
total += amount
```

Nếu core language chỉ có phép gán và phép cộng, có thể chuyển thành:

```text
total = total + amount
```

Với biến đơn giản, phép chuyển đổi thường đúng. Nhưng với biểu thức đích phức tạp:

```text
getAccount().balance += calculateFee()
```

Nếu chuyển trực tiếp thành:

```text
getAccount().balance = getAccount().balance + calculateFee()
```

thì `getAccount()` bị gọi hai lần. Nếu hàm có tác dụng phụ hoặc trả về hai đối tượng khác nhau, hành vi đã thay đổi.

Một phép desugaring đúng cần đánh giá phần đích một lần và lưu tham chiếu cần thiết:

```text
let receiver = getAccount()
let oldValue = receiver.balance
let newValue = oldValue + calculateFee()
receiver.balance = newValue
```

Chi tiết triển khai phụ thuộc mô hình l-value, getter/setter, thuộc tính có thể tính toán và quy tắc thứ tự đánh giá của DSL.

## 7. Desugaring toán tử logic

Một DSL có thể hỗ trợ toán tử `and` và `or` với đánh giá ngắn mạch (*short-circuit evaluation*).

Nếu core language chỉ có `if`, biểu thức:

```text
a and b
```

có thể được chuyển thành:

```text
if a then b else false
```

Và:

```text
a or b
```

có thể được chuyển thành:

```text
if a then true else b
```

Điểm quan trọng là `b` chỉ được đánh giá khi cần thiết. Nếu chuyển thành một lời gọi hàm thông thường:

```text
and(a, b)
```

và ngôn ngữ chủ đánh giá cả hai tham số trước khi gọi hàm, `b` sẽ luôn được đánh giá. Điều đó phá vỡ short-circuit nếu `b` có thể lỗi hoặc tạo tác dụng phụ.

Desugaring phải dùng một cấu trúc core có khả năng trì hoãn việc đánh giá nhánh chưa cần thiết, chẳng hạn `if` hoặc một node điều khiển luồng tương đương.

## 8. Desugaring toán tử null-coalescing

Một DSL có thể cung cấp toán tử `??` để chọn giá trị mặc định khi biểu thức bên trái là null:

```text
displayName = user.nickname ?? "Anonymous"
```

Nếu core language có điều kiện và biến tạm, có thể chuyển thành:

```text
let temp = user.nickname
let displayName = if temp != null then temp else "Anonymous"
```

Biến tạm bảo đảm `user.nickname` chỉ được đọc một lần. Điều này có thể quan trọng nếu truy cập thuộc tính là getter có hiệu ứng hoặc giá trị có thể thay đổi giữa hai lần đọc.

### 8.1. Phân biệt null với giá trị false

Một số ngôn ngữ dùng toán tử fallback theo truthiness, nhưng `??` thường chỉ kiểm tra null hoặc giá trị vắng mặt. Nếu DSL phân biệt `false`, `0`, chuỗi rỗng và null, phép desugaring phải kiểm tra đúng điều kiện.

Ví dụ, `0 ?? 10` thường trả về `0`, không phải `10`, nếu toán tử chỉ thay thế null.

### 8.2. Kiểu dữ liệu

Nếu `user.nickname` có kiểu `Option<String>` hoặc nullable string, phép desugaring phải tạo kết quả đúng kiểu. Core language có thể dùng pattern matching hoặc kiểm tra null để lấy giá trị bên trong.

## 9. Desugaring optional chaining

Optional chaining giúp truy cập sâu qua một giá trị có thể null mà không gây lỗi khi một mắt xích vắng mặt.

Ví dụ:

```text
city = customer?.address?.city
```

Một phép chuyển đổi khái niệm:

```text
let c = customer
if c == null {
    null
} else {
    let a = c.address
    if a == null {
        null
    } else {
        a.city
    }
}
```

Các biến tạm bảo đảm mỗi receiver được đánh giá đúng số lần. Nếu truy cập thuộc tính có getter, việc gọi lặp có thể tạo tác dụng phụ hoặc kết quả khác.

### 9.1. Optional method call

Một cú pháp như:

```text
customer?.refresh()
```

cần được chuyển thành điều kiện chỉ gọi `refresh()` khi `customer` khác null. Không được gọi phương thức trước rồi mới kiểm tra receiver.

### 9.2. Optional chaining và kiểu kết quả

Kết quả thường được nâng thành kiểu nullable hoặc optional. Nếu `city` vốn có kiểu `String`, biểu thức optional chaining có thể có kiểu `String?`. Type checker cần hiểu kiểu sau desugaring hoặc lưu metadata về phép nâng kiểu.

## 10. Desugaring vòng lặp `for each`

Một DSL có thể cho phép:

```text
for item in items {
    process(item)
}
```

Nếu core language có iterator protocol, có thể chuyển thành:

```text
let iterator = items.iterator()
while iterator.hasNext() {
    let item = iterator.next()
    process(item)
}
```

### 10.1. Đánh giá collection một lần

Collection expression cần được đánh giá đúng một lần:

```text
for item in loadItems() {
    process(item)
}
```

Nếu gọi `loadItems()` ở mỗi vòng lặp, hành vi và hiệu năng có thể thay đổi. Desugaring nên lưu collection hoặc iterator vào biến tạm.

### 10.2. Phạm vi biến lặp

Biến `item` thường chỉ tồn tại trong thân vòng lặp. Nếu core representation dùng một biến có phạm vi rộng hơn, compiler phải tạo scope hoặc tên tạm để tránh xung đột với biến cùng tên bên ngoài.

### 10.3. Break và continue

Nếu DSL hỗ trợ `break` và `continue`, phép chuyển đổi phải giữ đúng điểm điều khiển. Với iterator loop, `continue` thường quay lại kiểm tra `hasNext`; `break` thoát khỏi vòng lặp. Nếu vòng lặp được hạ thành cấu trúc phức tạp hơn, cần ánh xạ chính xác các nhánh này.

## 11. Desugaring khai báo mặc định

Một DSL khai báo có thể cho phép bỏ qua giá trị mặc định:

```text
service "catalog" {
    region = "asia"
}
```

Nếu `replicas` mặc định là `1`, compiler có thể mở rộng thành biểu diễn đầy đủ:

```text
service "catalog" {
    replicas = 1
    region = "asia"
}
```

Đây có thể được xem là desugaring hoặc một bước chuẩn hóa mô hình, tùy kiến trúc compiler.

### 11.1. Phân biệt giá trị vắng mặt và giá trị null

Nếu người dùng không khai báo `timeout`, điều đó có thể có nghĩa “dùng mặc định”. Nếu họ khai báo `timeout = null`, ý nghĩa có thể là “không đặt timeout”. Hai trường hợp không được hợp nhất nếu DSL quy định chúng khác nhau.

### 11.2. Giá trị mặc định có thể phụ thuộc ngữ cảnh

Một giá trị mặc định có thể phụ thuộc target, môi trường hoặc cấu hình module. Nếu vậy, desugaring cần có đủ context để tính giá trị, và cache hoặc source mapping phải ghi nhận các dependency đó.

## 12. Desugaring cú pháp khai báo thành lời gọi API

DSL có thể cho phép cú pháp chuyên biệt cho miền nhưng core language chỉ có lời gọi hàm.

Ví dụ:

```text
database "orders" {
    engine = "postgres"
    replicas = 2
}
```

Cấu trúc này có thể được chuyển thành một lời gọi builder:

```text
DatabaseBuilder.create("orders")
    .engine("postgres")
    .replicas(2)
    .build()
```

Hoặc thành một node core khai báo resource có schema chuẩn hóa. Cách chuyển đổi phụ thuộc runtime và kiến trúc DSL.

### 12.1. Builder không phải lúc nào cũng tương đương

Nếu builder gọi từng setter theo thứ tự, thứ tự đánh giá và tác dụng phụ có thể khác với cấu trúc khai báo vốn được xem là dữ liệu thuần. Cần xác định liệu các thuộc tính có thứ tự có ý nghĩa hay không và khi nào builder được thực thi.

### 12.2. Validation trước khi thực thi

Một DSL khai báo thường muốn kiểm tra toàn bộ cấu hình trước khi tạo tài nguyên. Vì vậy, desugaring thành lời gọi builder không nên vô tình thực hiện I/O ngay trong lúc phân tích cú pháp. Có thể tạo một mô hình cấu hình lõi rồi để runtime áp dụng sau validation.

## 13. Desugaring và bảo toàn ngữ nghĩa

Một phép desugaring đúng cần bảo toàn hành vi theo định nghĩa ngữ nghĩa của DSL. Đây thường được gọi là **semantic preservation**.

Có thể diễn đạt trực giác:

\[
\operatorname{Meaning}(source)
\equiv
\operatorname{Meaning}(desugar(source))
\]

Ký hiệu trên biểu thị hai dạng phải tương đương theo những quan sát mà DSL cam kết. Tùy ngôn ngữ, các quan sát có thể gồm giá trị, trạng thái cuối, thứ tự I/O, ngoại lệ, thời điểm đánh giá và luồng điều khiển.

### 13.1. Thứ tự đánh giá

Nếu DSL quy định đánh giá từ trái sang phải, desugaring phải giữ thứ tự đó. Không được chuyển biểu thức thành các lời gọi tạm theo thứ tự khác nếu các biểu thức có tác dụng phụ.

Ví dụ:

```text
combine(nextId(), writeAudit())
```

Nếu `nextId()` phải chạy trước `writeAudit()`, core representation cần giữ thứ tự này.

### 13.2. Số lần đánh giá

Một biểu thức trong cú pháp đường có thể chỉ được đánh giá một lần. Nếu phép chuyển đổi sao chép biểu thức vào nhiều vị trí, nó có thể được đánh giá nhiều lần.

Ví dụ, `getValue()` trong `x += getValue()` chỉ nên được gọi một lần. Desugaring phải dùng temporary để giữ kết quả.

### 13.3. Tác dụng phụ

Desugaring phải giữ nguyên những tác động quan sát được như ghi dữ liệu, phát sự kiện hoặc thay đổi trạng thái. Không được bỏ một lời gọi chỉ vì giá trị trả về không được sử dụng nếu lời gọi đó có hiệu ứng.

### 13.4. Ngoại lệ và lỗi

Thứ tự đánh giá có thể quyết định lỗi nào xảy ra trước. Nếu cú pháp đường đánh giá một biểu thức trước biểu thức khác, dạng core phải giữ thứ tự để ngoại lệ và diagnostic runtime không thay đổi bất ngờ.

### 13.5. Phạm vi và binding

Biến tạm được tạo trong quá trình desugaring không được làm xung đột với tên do người dùng khai báo. Compiler cần tạo tên nội bộ hoặc symbol ID riêng, đồng thời giữ đúng lexical scope.

## 14. Hygiene và tên biến tạm

Khi desugaring tạo biến mới, cần tránh capture hoặc shadowing ngoài ý muốn.

Ví dụ người dùng viết:

```text
let temp = 100
repeat 2 times {
    use(temp)
}
```

Nếu compiler cũng tạo biến tạm tên `temp`, nó có thể che khuất biến của người dùng hoặc khiến tham chiếu bên trong thân vòng lặp trỏ sai symbol.

### 14.1. Fresh names

Compiler thường tạo tên nội bộ duy nhất như:

```text
__desugar_counter_17
```

Tuy nhiên, chỉ tạo chuỗi tên khó trùng không phải giải pháp mạnh nhất. Một AST có thể dùng symbol ID hoặc identifier được đánh dấu internal để bảo đảm không nhầm với tên nguồn.

### 14.2. Scope chính xác

Biến tạm phải được khai báo trong phạm vi nhỏ nhất phù hợp với ngữ nghĩa. Nếu biến chỉ cần trong một vòng lặp, không nên để nó trở thành biến công khai của module.

### 14.3. Hygiene và macro

Hygienic macro là cơ chế rộng hơn desugaring đơn giản. Nó bảo đảm định danh được tạo bởi macro không vô tình bắt giữ định danh ở nơi gọi, và ngược lại. Một hệ thống desugaring có thể cần một số nguyên tắc hygiene tương tự khi tạo biến hoặc mở rộng cú pháp.

Không phải mọi phép desugaring đều là macro expansion. Desugaring thường là biến đổi có quy tắc cố định do compiler định nghĩa; macro có thể cho phép người dùng hoặc thư viện định nghĩa phép mở rộng mới.

## 15. Desugaring pattern matching

Một DSL có thể hỗ trợ `match`:

```text
match result {
    Success(value) => use(value)
    Failure(error) => report(error)
}
```

Nếu core language chỉ có kiểm tra tag, điều kiện và truy cập trường, compiler có thể chuyển pattern matching thành chuỗi kiểm tra.

Biểu diễn khái niệm:

```text
let temp = result
if temp.tag == Success {
    let value = temp.value
    use(value)
} else if temp.tag == Failure {
    let error = temp.error
    report(error)
} else {
    unreachable()
}
```

### 15.1. Exhaustiveness

Trước hoặc trong quá trình desugaring, compiler có thể kiểm tra mọi trường hợp của kiểu sum type đã được bao phủ chưa. Nếu `Result` chỉ có `Success` và `Failure`, hai nhánh trên là đầy đủ.

### 15.2. Pattern lồng nhau

Pattern có thể chứa tuple, record, literal hoặc pattern lồng. Việc chuyển đổi có thể cần tạo cây quyết định (*decision tree*) để tránh kiểm tra lặp và giữ đúng thứ tự.

### 15.3. Guard

Một nhánh có guard như:

```text
Success(value) if value > 0 => use(value)
```

cần kiểm tra pattern trước, sau đó mới đánh giá guard. Nếu guard thất bại, quá trình matching có thể tiếp tục nhánh tiếp theo theo ngữ nghĩa DSL. Desugaring phải giữ thứ tự và phạm vi binding.

## 16. Desugaring comprehension và pipeline

DSL dữ liệu có thể cung cấp list comprehension:

```text
activeNames = [user.name for user in users if user.active]
```

Nếu core language chỉ có iterator và vòng lặp, có thể chuyển thành:

```text
let result = newList()
for user in users {
    if user.active {
        result.add(user.name)
    }
}
```

### 16.1. Thứ tự duyệt

Nếu comprehension lồng nhiều vòng lặp, thứ tự duyệt phải được giữ. Ví dụ:

```text
[(x, y) for x in xs for y in ys]
```

thường có nghĩa với mỗi `x`, duyệt tất cả `y`. Đổi thứ tự hai vòng lặp có thể thay đổi thứ tự phần tử và tác dụng phụ trong điều kiện hoặc biểu thức.

### 16.2. Lazy và eager evaluation

Một comprehension có thể tạo danh sách ngay (*eager*) hoặc tạo luồng giá trị lười (*lazy*). Chuyển lazy sequence thành list eagerly có thể làm thay đổi thời điểm đánh giá, bộ nhớ sử dụng và tác dụng phụ.

Desugaring cần giữ mô hình đánh giá mà DSL công bố. Nếu core language không biểu diễn được lazy sequence, có thể cần thêm iterator/generator primitive thay vì hạ tất cả thành danh sách.

### 16.3. Pipeline operator

Một cú pháp pipeline:

```text
orders |> filter(isPaid) |> map(total) |> sum
```

có thể được chuyển thành lời gọi lồng nhau:

```text
sum(map(filter(orders, isPaid), total))
```

Phép biến đổi phải xác định cách truyền đối số, xử lý hàm nhiều tham số, thứ tự đánh giá và việc pipeline có lazy hay eager.

## 17. Desugaring và type checking

Thứ tự giữa type checking và desugaring là quyết định kiến trúc quan trọng.

### 17.1. Desugar trước type checking

Ưu điểm:

- Type checker chỉ cần xử lý core AST.
- Những cú pháp tương đương dùng chung quy tắc kiểu.
- Có thể giảm số trường hợp trong semantic analyzer.

Hạn chế:

- Một số cú pháp bề mặt cần kiểm tra kiểu riêng trước khi chuyển đổi.
- Diagnostic có thể khó gắn với cú pháp ban đầu nếu mất source mapping.
- Thông tin về ý định của người dùng có thể bị loại bỏ quá sớm.

### 17.2. Type check trước desugaring

Ưu điểm:

- Có thể kiểm tra quy tắc kiểu đặc thù của cú pháp bề mặt.
- Dễ tạo diagnostic theo khái niệm mà người dùng đã viết.

Hạn chế:

- Type checker phải hiểu nhiều node bề mặt hơn.
- Có thể lặp logic kiểu giữa cú pháp đường và core construct tương ứng.

### 17.3. Hybrid approach

Một compiler có thể thực hiện một số bước trước và sau desugaring:

```text
Surface AST
   |
   v
Name resolution and surface checks
   |
   v
Desugaring
   |
   v
Core type checking
   |
   v
IR lowering
```

Ví dụ, compiler có thể resolve tên và kiểm tra số lượng tham số của cú pháp đặc biệt trước, rồi desugar và dùng type checker lõi cho phần còn lại.

## 18. Source mapping và diagnostic sau desugaring

Sau desugaring, một node core có thể được tạo từ nhiều node nguồn, hoặc nhiều node core cùng bắt nguồn từ một cú pháp bề mặt.

Ví dụ:

```text
repeat 5 times { work() }
```

có thể tạo các node core:

- Khai báo biến đếm.
- Khởi tạo giá trị đếm.
- Kiểm tra điều kiện.
- Thực hiện thân vòng lặp.
- Tăng biến đếm.

Người dùng không trực tiếp viết những node này. Nếu lỗi phát sinh ở một node core, compiler nên ánh xạ diagnostic về dòng `repeat` hoặc đoạn thân phù hợp.

### 18.1. Giữ source span

Node được tạo có thể mang source span của node bề mặt đã tạo ra nó. Nếu một node core tương ứng với một phần nhỏ cụ thể, có thể giữ span chính xác hơn.

### 18.2. Origin metadata

Compiler có thể lưu metadata như:

```text
CoreNode {
    kind: While
    origin: SurfaceNodeId(42)
    generated: true
}
```

Nếu node sinh ra từ nhiều nguồn, metadata có thể lưu nhiều origin hoặc một quan hệ expansion.

### 18.3. Diagnostic dễ hiểu

Thông báo lỗi nên ưu tiên khái niệm bề mặt. Ví dụ, thay vì báo “invalid comparison in generated while condition”, có thể báo “số lần lặp của `repeat` phải là số nguyên không âm”.

Source mapping giúp compiler giữ được trải nghiệm này dù các bước semantic analysis làm việc trên core AST.

## 19. Desugaring và macro expansion

Desugaring và macro expansion đều có thể biến đổi cú pháp, nhưng mục đích và mức độ mở rộng khác nhau.

| Tiêu chí | Desugaring | Macro expansion |
|---|---|---|
| Nguồn quy tắc | Thường do compiler định nghĩa | Có thể do ngôn ngữ hoặc người dùng/thư viện định nghĩa |
| Phạm vi | Cú pháp đường đã biết | Có thể tạo cú pháp mới hoặc mở rộng cấu trúc tổng quát |
| Tính tùy biến | Thường cố định theo phiên bản compiler | Có thể mở rộng theo module hoặc package |
| Hygiene | Cần quản lý tên tạm và scope | Thường cần cơ chế hygiene rõ ràng |
| Mục tiêu | Chuyển surface syntax về core syntax | Mở rộng hoặc biến đổi chương trình theo quy tắc macro |

Một compiler có thể chạy macro expansion trước desugaring, hoặc xen kẽ các bước tùy ngôn ngữ. Cần tránh để macro tạo ra cú pháp mà desugarer không hiểu hoặc để desugarer làm mất metadata cần cho macro diagnostics.

## 20. Desugaring và tối ưu hóa

Desugaring thường không nhằm tối ưu chương trình. Mục tiêu chính là chuyển cú pháp bề mặt thành cấu trúc lõi tương đương.

Ví dụ:

```text
unless condition { action() }
```

được chuyển thành `if not condition`. Compiler chưa cần quyết định có inline `action`, loại bỏ nhánh không thể xảy ra hay kết hợp basic blocks.

### 20.1. Tách desugaring và optimization

Tách hai bước giúp:

- Dễ xác định phép biến đổi nào chỉ thay cú pháp.
- Dễ kiểm tra semantic preservation.
- Dễ bật/tắt optimization mà vẫn giữ cùng ngữ nghĩa.
- Dễ phân tích lỗi do frontend hay optimizer gây ra.

### 20.2. Có thể có normalization

Sau desugaring, compiler có thể chuẩn hóa core AST về một dạng thống nhất, ví dụ chuyển mọi vòng lặp về `while`, mọi phép gán mở rộng về assignment cơ bản hoặc mọi pattern thành decision tree. Normalization có thể được xem là một phần của desugaring hoặc một pass riêng.

## 21. Thiết kế core language cho DSL

Chất lượng desugaring phụ thuộc vào việc core language có đủ primitive để biểu diễn các cấu trúc bề mặt hay không.

### 21.1. Core quá nhỏ

Nếu core chỉ có biến và lời gọi hàm, việc biểu diễn `try/catch`, lazy evaluation hoặc generator có thể rất khó. Compiler có thể phải tạo nhiều runtime helper hoặc mất khả năng giữ nguyên ngữ nghĩa.

### 21.2. Core quá lớn

Nếu core giữ gần như mọi cú pháp bề mặt, desugaring không giảm đáng kể độ phức tạp. Các giai đoạn sau vẫn phải xử lý nhiều loại node và nhiều trường hợp đặc biệt.

### 21.3. Chọn primitive theo nhu cầu

Một core hợp lý thường giữ những khái niệm nền tảng khó biểu diễn hiệu quả bằng các primitive khác, chẳng hạn:

- Conditional branch.
- Function call và return.
- Mutable binding hoặc immutable binding.
- Loop hoặc jump primitives.
- Exception/effect handling nếu ngôn ngữ cần.
- Pattern matching primitive nếu không thể hạ an toàn về điều kiện cơ bản.

Không nhất thiết phải hạ mọi cấu trúc xuống mức thấp nhất ngay lập tức. Một số node cấp cao có thể tồn tại trong core hoặc IR để backend và optimizer khai thác.

## 22. Tổ chức desugaring pass

Một compiler có thể triển khai desugaring như một visitor hoặc transformer duyệt AST.

Ví dụ giao diện khái niệm:

```text
desugar(node: SurfaceNode, context: Context): CoreNode
```

Mỗi loại node được xử lý theo quy tắc riêng:

```text
desugar(Unless(condition, body)):
    return If(Not(desugar(condition)), desugar(body), EmptyBlock)

desugar(Repeat(count, body)):
    limit = freshTemporary()
    index = freshTemporary()
    return Let(limit, desugar(count),
        Let(index, 0,
            While(index < limit,
                Block(desugar(body), index = index + 1))))
```

Đây là mã giả. Một triển khai thực tế cần xử lý kiểu dữ liệu, source origin, scope, symbol identity, control-flow target và lỗi biến đổi.

### 22.1. Transformer bất biến

Một cách thiết kế là tạo AST mới thay vì sửa trực tiếp node cũ. Transformer nhận node bề mặt và trả node core mới. Cách này giúp giữ lại AST nguồn để hiển thị lỗi hoặc debug.

### 22.2. Context

Context có thể chứa:

- Bảng cấp tên tạm.
- Scope và symbol environment.
- Kiểu đã biết hoặc thông tin type inference.
- Source mapping.
- Target feature flags.
- Diagnostic collector.

Context cần được quản lý rõ để phép biến đổi có thể lặp lại và không phụ thuộc trạng thái toàn cục không xác định.

### 22.3. Nhiều pass nhỏ

Thay vì một hàm khổng lồ xử lý mọi cú pháp đường, có thể chia thành nhiều pass:

```text
DesugarControlFlow
DesugarAssignments
DesugarOptionalAccess
DesugarDeclarations
NormalizeCoreAst
```

Thứ tự pass phải được xác định. Một pass có thể tạo node mà pass sau hiểu, nhưng không nên tạo cấu trúc mà pass trước đã chạy rồi.

## 23. Kiểm thử desugaring

Phép desugaring cần được kiểm thử như một phép biến đổi ngữ nghĩa, không chỉ kiểm tra AST đầu ra có đúng loại node mong muốn.

### 23.1. Kiểm tra cấu trúc đầu ra

Với:

```text
unless blocked { allow() }
```

có thể kiểm tra AST core có dạng `If(Not(blocked), allow(), ...)`.

### 23.2. Kiểm tra số lần đánh giá

Với:

```text
repeat getLimit() times { action() }
```

cần xác nhận `getLimit()` chỉ được gọi một lần nếu đó là ngữ nghĩa của surface construct.

### 23.3. Kiểm tra thứ tự và tác dụng phụ

Tạo các biểu thức có log hoặc cập nhật trạng thái để xác nhận thứ tự đánh giá trước và sau desugaring tương đương.

### 23.4. Kiểm tra scope và capture

Tạo chương trình có biến trùng với tên mà compiler thường dùng cho temporary. Kết quả phải giữ tham chiếu đúng symbol nguồn.

### 23.5. Kiểm tra lỗi và source mapping

Nếu node core gây lỗi, diagnostic cần trỏ về vị trí bề mặt có ý nghĩa. Không nên chỉ hiển thị tên biến tạm hoặc node được sinh tự động.

### 23.6. Kiểm tra tương đương thực thi

Với một tập chương trình mẫu, có thể so sánh quan sát của chương trình surface chạy qua interpreter tham chiếu với chương trình core sau desugaring. Quan sát có thể gồm giá trị trả về, trạng thái cuối, thứ tự sự kiện và lỗi.

## 24. Những sai lầm thường gặp

**Chỉ thay cú pháp bằng đoạn mã trông tương tự.** Phép chuyển đổi phải giữ ngữ nghĩa, không chỉ giữ hình thức.

**Đánh giá biểu thức nhiều lần.** Khi mở rộng `+=`, optional chaining hoặc vòng lặp, cần lưu kết quả trung gian nếu biểu thức nguồn chỉ được đánh giá một lần.

**Làm mất short-circuit.** Chuyển `and` hoặc `or` thành lời gọi hàm thông thường có thể khiến cả hai vế đều được đánh giá.

**Tạo biến tạm có thể xung đột.** Tên do compiler sinh cần fresh identity và scope chính xác.

**Làm mất source location.** Diagnostic sau desugaring phải truy ngược được về cú pháp người dùng viết.

**Trộn desugaring với optimization.** Khi hai loại biến đổi nằm trong cùng pass không rõ ranh giới, việc chứng minh và tìm lỗi trở nên khó hơn.

**Hạ quá nhiều cấu trúc xuống core quá sớm.** Một số cấu trúc cấp cao vẫn có giá trị cho type checking, diagnostics, optimization hoặc backend.

**Bỏ qua thứ tự đánh giá và ngoại lệ.** Thay đổi thứ tự có thể làm chương trình quan sát được hành vi khác.

**Giả định mọi cú pháp đường đều có thể hạ thành lời gọi hàm.** Short-circuit, binding, control flow và lazy evaluation có thể cần primitive chuyên biệt.

## 25. Ví dụ tổng hợp: DSL workflow

Giả sử DSL workflow hỗ trợ:

```text
workflow notifyCustomer(order) {
    repeat 2 times {
        retry sendEmail(order.customer) on NetworkError
    }

    unless order.isPaid {
        raise PaymentRequired
    }

    displayName = order.customer?.profile?.name ?? "Guest"
}
```

Core language có thể hỗ trợ:

- Biến và temporary.
- `while` và `if`.
- Function call.
- Kiểm tra null.
- Exception handling.
- Assignment.

Các phép desugaring có thể được tổ chức:

1. `repeat 2 times` thành temporary counter và `while`.
2. `retry ... on NetworkError` thành vòng điều khiển thử lại với handler lỗi phù hợp.
3. `unless condition` thành `if not condition`.
4. Optional chaining thành kiểm tra null lồng nhau với temporary.
5. `??` thành kiểm tra null và chọn giá trị mặc định.

Thứ tự các bước cần bảo đảm các pass hiểu được node mà pass trước tạo ra. `retry` có thể cần giữ lại thông tin loại lỗi và ranh giới tác vụ cho đến khi exception lowering xử lý. Optional chaining cần giữ đúng số lần đánh giá từng receiver. `repeat` cần đánh giá số lần lặp đúng theo quy tắc DSL.

Sau desugaring, type checker và backend có thể làm việc với core AST thống nhất hơn, trong khi source mapping vẫn cho phép diagnostics hiển thị `repeat`, `unless`, `?.` hoặc `??` như người dùng đã viết.

## 26. Ghi nhớ

- Desugaring chuyển cú pháp đường của surface language thành cấu trúc đơn giản hơn trong core language.
- Syntactic sugar giúp DSL dễ viết và dễ đọc; core language giúp compiler dùng chung các giai đoạn semantic analysis, optimization và code generation.
- Desugaring khác parsing: parser tạo AST bề mặt, còn desugarer biến đổi AST đó.
- Desugaring không đồng nghĩa với code generation; kết quả thường vẫn là AST hoặc biểu diễn trung gian.
- Semantic preservation yêu cầu giữ giá trị, trạng thái, thứ tự đánh giá, số lần đánh giá, tác dụng phụ, ngoại lệ và scope theo hợp đồng DSL.
- Temporary và symbol identity giúp tránh đánh giá lặp và tránh capture tên.
- Short-circuit, optional chaining, vòng lặp và gán kết hợp là các ví dụ cần xử lý cẩn thận.
- Source mapping giúp diagnostic sau biến đổi vẫn trỏ về cú pháp bề mặt.
- Desugaring khác macro expansion; macro thường mở rộng khả năng tùy biến cú pháp rộng hơn.
- Tách desugaring khỏi optimization giúp compiler dễ hiểu, kiểm thử và bảo trì.

## 27. Câu hỏi tự kiểm tra

1. Desugaring là gì? Syntactic sugar và core language khác nhau như thế nào?
2. Vì sao một DSL có thể cung cấp nhiều cú pháp bề mặt nhưng chỉ cần một tập core construct nhỏ?
3. Phân biệt parsing, desugaring, lowering và code generation.
4. Khi chuyển `repeat calculateLimit() times`, vì sao cần lưu kết quả `calculateLimit()` vào temporary?
5. Vì sao không thể luôn chuyển `a and b` thành lời gọi hàm `and(a, b)`?
6. Khi desugar `getAccount().balance += fee()`, cần bảo đảm điều gì về số lần gọi `getAccount()`?
7. Optional chaining cần giữ những thuộc tính ngữ nghĩa nào?
8. Vì sao biến tạm do compiler sinh cần fresh identity và scope riêng?
9. Semantic preservation cần xem xét những quan sát nào ngoài giá trị trả về?
10. Source mapping giúp người dùng như thế nào khi lỗi phát sinh trong node core được sinh tự động?
11. Desugaring khác macro expansion ở mục tiêu và khả năng mở rộng ra sao?
12. Hãy mô tả cách hạ `for item in items` thành vòng lặp iterator và giải thích cách giữ đúng `break`/`continue`.
13. Khi nào nên giữ một cấu trúc cấp cao trong core hoặc IR thay vì hạ ngay thành primitive thấp hơn?
14. Hãy đề xuất các trường hợp cần kiểm thử để chứng minh phép desugaring của một toán tử tiện lợi không làm thay đổi tác dụng phụ.
