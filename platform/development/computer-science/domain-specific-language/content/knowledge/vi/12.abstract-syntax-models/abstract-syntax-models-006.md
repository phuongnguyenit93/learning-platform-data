# Giá trị mặc định thuộc tính

Trong mô hình trừu tượng của một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL), **giá trị mặc định thuộc tính (property default value)** là giá trị mà hệ thống sử dụng cho một thuộc tính khi người dùng không cung cấp giá trị tường minh tại thời điểm tạo hoặc cấu hình đối tượng.

Ví dụ, một mô hình đơn hàng có thuộc tính `currency` với giá trị mặc định là `"VND"`. Khi người dùng tạo đơn hàng mà không chỉ định tiền tệ, bộ thực thi có thể gán `"VND"` cho thuộc tính đó. Nếu người dùng cung cấp `"USD"`, giá trị được cung cấp sẽ được sử dụng theo quy tắc ưu tiên của DSL.

Giá trị mặc định giúp mô hình ngắn gọn, giảm thao tác lặp lại và thể hiện những giả định phổ biến của miền. Tuy nhiên, nếu định nghĩa không rõ, mặc định có thể tạo ra hành vi bất ngờ, che giấu dữ liệu thiếu hoặc làm thay đổi ý nghĩa của mô hình giữa các phiên bản.

Khi thiết kế thuộc tính có giá trị mặc định, cần xác định giá trị đó thuộc kiểu nào, được áp dụng khi nào, có thể bị ghi đè hay không, được kế thừa ra sao và cách phân biệt trường hợp không cung cấp giá trị với trường hợp cố ý cung cấp giá trị rỗng.

## 1. Khái niệm giá trị mặc định thuộc tính

Một thuộc tính mô tả một đặc điểm của khái niệm trong mô hình miền. Thuộc tính có thể có tên, kiểu dữ liệu, bội số, tính bắt buộc, khả năng thay đổi và các ràng buộc khác.

Ví dụ:

~~~text
entity Order {
  property id: OrderId
  property currency: String = "VND"
  property status: OrderStatus = PENDING
  property note: String?
}
~~~

Trong mô hình giả định này:

- `id` là thuộc tính định danh và không có mặc định được khai báo.
- `currency` có mặc định là chuỗi `"VND"`.
- `status` có mặc định là giá trị enum `PENDING`.
- `note` có thể không có giá trị; ký hiệu `?` biểu thị khả năng vắng mặt theo quy ước của DSL này.

Khi tạo một Order mà không truyền `currency` hoặc `status`, hệ thống có thể áp dụng các giá trị mặc định đã khai báo. Thuộc tính `note` có thể vắng mặt mà không cần một giá trị thay thế.

Cú pháp trên chỉ nhằm minh họa. Mỗi DSL cần định nghĩa rõ ký hiệu, thời điểm áp dụng và cách lưu trữ giá trị mặc định.

### 1.1. Mặc định là hành vi khi thiếu giá trị

Một giá trị mặc định thường được dùng khi không có giá trị tường minh. Có thể biểu diễn quy tắc cơ bản như sau:

~~~text
effectiveValue =
  explicitValue, if an explicit value is supplied
  defaultValue,  otherwise, if a default exists
  absent,        otherwise
~~~

Ví dụ:

| Đầu vào | Giá trị mặc định | Giá trị hiệu lực |
| --- | --- | --- |
| Không khai báo `currency` | `"VND"` | `"VND"` |
| `currency = "USD"` | `"VND"` | `"USD"` |
| `currency = ""` | `"VND"` | Chuỗi rỗng nếu DSL cho phép |
| `currency = null` | `"VND"` | `null` nếu DSL cho phép và định nghĩa null là giá trị tường minh |

Điểm quan trọng là **không cung cấp giá trị** và **cung cấp một giá trị rỗng hoặc null** có thể mang ý nghĩa khác nhau. DSL phải quy định sự khác biệt này thay vì tự động xem tất cả là “chưa có giá trị”.

### 1.2. Mặc định trong mô hình trừu tượng

Mô hình trừu tượng (abstract model) mô tả cấu trúc và ngữ nghĩa của DSL mà không phụ thuộc hoàn toàn vào cách người dùng viết cú pháp. Một thuộc tính trong mô hình có thể được biểu diễn bằng metadata như:

- Tên thuộc tính.
- Kiểu dữ liệu.
- Giá trị mặc định, nếu có.
- Bội số hoặc tính tùy chọn.
- Ràng buộc hợp lệ.
- Quy tắc kế thừa.
- Nguồn và thời điểm đánh giá mặc định.

Ví dụ, mô hình trừu tượng có thể lưu một thuộc tính `currency` với kiểu `String` và một value specification biểu diễn chuỗi `"VND"`. Parser chuyển cú pháp DSL thành cấu trúc này; bộ kiểm tra ngữ nghĩa xác minh giá trị phù hợp kiểu; bộ tạo đối tượng hoặc runtime áp dụng giá trị theo quy tắc đã định nghĩa.

Trong UML, một Property có thể có `defaultValue` dưới dạng ValueSpecification. Giá trị đó mô tả giá trị được sử dụng khi không cung cấp giá trị khác theo ngữ nghĩa của mô hình. Việc DSL có dùng đúng thuật ngữ hoặc cơ chế của UML hay không phụ thuộc vào metamodel của nó.

## 2. Phân biệt giá trị mặc định với các khái niệm gần giống

Giá trị mặc định thường bị nhầm với giá trị khởi tạo, giá trị rỗng, giá trị bắt buộc hoặc ràng buộc. Những khái niệm này có liên quan nhưng không đồng nghĩa.

### 2.1. Giá trị mặc định và giá trị tường minh

Giá trị tường minh (explicit value) là giá trị người dùng trực tiếp cung cấp trong cấu hình hoặc khi tạo đối tượng. Giá trị mặc định chỉ được xem xét khi không có giá trị tường minh theo quy tắc của DSL.

Ví dụ:

~~~text
entity Report {
  property format: String = "CSV"
}

report MonthlySales {
  format = "PDF"
}
~~~

Thuộc tính `format` có mặc định `"CSV"`, nhưng khai báo `MonthlySales` cung cấp `"PDF"`. Giá trị hiệu lực của thuộc tính trong instance này là `"PDF"` nếu DSL cho phép ghi đè mặc định ở cấp instance.

### 2.2. Giá trị mặc định và giá trị khởi tạo

Hai thuật ngữ có thể được dùng gần nhau, nhưng cần xác định chính xác trong DSL:

- **Giá trị mặc định:** giá trị được chọn khi người dùng không cung cấp giá trị.
- **Giá trị khởi tạo (initial value):** giá trị mà thuộc tính hoặc đối tượng có tại một thời điểm bắt đầu cụ thể.
- **Giá trị hiện tại (current value):** giá trị đang được giữ sau các thao tác cập nhật.

Ví dụ, `status` mặc định của đơn hàng mới là `PENDING`. Sau khi thanh toán, trạng thái hiện tại có thể là `PAID`. Giá trị mặc định không có nghĩa thuộc tính phải giữ nguyên giá trị đó trong toàn bộ vòng đời đối tượng.

Một DSL có thể áp dụng mặc định khi tạo instance, sau đó cho phép nghiệp vụ thay đổi thuộc tính. Nếu DSL chỉ mô tả cấu hình bất biến, giá trị mặc định có thể tồn tại suốt vòng đời cấu hình. Ngữ nghĩa này phải được công bố rõ.

### 2.3. Giá trị mặc định và giá trị null

`null` thường biểu thị không có giá trị, nhưng không phải DSL nào cũng hỗ trợ null hoặc dùng nó theo cùng một cách.

Xét thuộc tính:

~~~text
property description: String? = "No description"
~~~

Có thể có ba tình huống:

1. Người dùng bỏ qua `description`: hệ thống dùng `"No description"`.
2. Người dùng cung cấp `"Seasonal report"`: hệ thống dùng chuỗi đó.
3. Người dùng cung cấp `null`: kết quả phụ thuộc vào việc DSL có cho phép null tường minh và có xem null là giá trị ghi đè hay không.

Nếu DSL cho phép trường nullable và phân biệt null với vắng mặt, trường hợp thứ ba có thể giữ null thay vì quay về mặc định. Đây là lựa chọn thiết kế, không nên để runtime tự suy đoán.

### 2.4. Giá trị mặc định và tính bắt buộc

Tính bắt buộc (requiredness) quy định người dùng có phải cung cấp thuộc tính hay không. Giá trị mặc định quy định hệ thống dùng gì khi thuộc tính không được cung cấp.

Hai khái niệm có thể kết hợp theo nhiều cách:

| Khai báo | Ý nghĩa có thể có |
| --- | --- |
| Bắt buộc, không có mặc định | Người dùng phải cung cấp giá trị |
| Không bắt buộc, không có mặc định | Giá trị có thể vắng mặt |
| Bắt buộc, có mặc định | Có thể coi thuộc tính là luôn có sau khi áp dụng mặc định; cần xác định yêu cầu nhập liệu có được miễn hay không |
| Không bắt buộc, có mặc định | Khi bỏ qua thì dùng mặc định; tùy DSL, người dùng có thể vẫn để thuộc tính vắng mặt bằng cú pháp riêng |

Ví dụ, `id` thường bắt buộc và không nên tự sinh một giá trị tùy tiện nếu DSL không có cơ chế sinh định danh được định nghĩa rõ. Ngược lại, `currency` có thể có mặc định để giảm thao tác nhập.

Không nên suy luận rằng một thuộc tính có mặc định thì tự động là tùy chọn ở mọi giai đoạn. Một biểu mẫu có thể yêu cầu người dùng xác nhận trường dù hệ thống có giá trị gợi ý; một API có thể bỏ qua trường vì runtime sẽ áp dụng mặc định.

### 2.5. Giá trị mặc định và ràng buộc

Ràng buộc (constraint) quy định điều kiện giá trị phải thỏa mãn. Mặc định chỉ cung cấp một giá trị ứng viên; giá trị đó vẫn phải hợp lệ.

~~~text
property retryCount: Integer = 3
constraint retryCount >= 0
constraint retryCount <= 10
~~~

Giá trị mặc định `3` thỏa mãn hai ràng buộc. Nếu một mô hình đặt mặc định là `20`, parser có thể vẫn đọc được cú pháp, nhưng kiểm tra ngữ nghĩa cần báo rằng mặc định vi phạm giới hạn tối đa.

Một mặc định hợp lệ không làm cho mọi giá trị ghi đè trở nên hợp lệ. Mỗi giá trị tường minh cũng cần được kiểm tra.

## 3. Những loại giá trị mặc định thường gặp

DSL có thể hỗ trợ nhiều dạng mặc định, từ literal đơn giản đến biểu thức phụ thuộc ngữ cảnh.

### 3.1. Mặc định dạng literal

Literal là giá trị được viết trực tiếp trong cú pháp, chẳng hạn chuỗi, số, boolean hoặc enum.

~~~text
entity ServiceConfig {
  property enabled: Boolean = true
  property port: Integer = 8080
  property protocol: String = "HTTPS"
  property mode: ServiceMode = STANDARD
}
~~~

Ưu điểm của literal:

- Dễ đọc và dễ phân tích.
- Có thể kiểm tra kiểu ngay khi phân tích mô hình.
- Có tính xác định nếu giá trị không phụ thuộc môi trường.
- Dễ hiển thị trong tài liệu và công cụ biên tập.

Literal thường là lựa chọn phù hợp cho các mặc định ổn định như số lần thử lại, trạng thái ban đầu hoặc định dạng mặc định.

### 3.2. Mặc định bằng biểu thức

Một số DSL cho phép giá trị mặc định được tính từ biểu thức:

~~~text
entity Invoice {
  property quantity: Integer = 1
  property unitPrice: Decimal
  property total: Decimal = quantity * unitPrice
}
~~~

Trong ví dụ này, `total` được tính từ hai thuộc tính khác. Tuy nhiên, DSL cần xác định đây là mặc định được tính một lần khi tạo instance hay thuộc tính dẫn xuất được tính lại mỗi khi đầu vào thay đổi.

Hai cách hiểu khác nhau:

- **Mặc định biểu thức:** chỉ dùng kết quả biểu thức nếu không có giá trị tường minh; kết quả có thể được lưu như giá trị ban đầu.
- **Thuộc tính dẫn xuất (derived property):** giá trị được tính từ các thuộc tính khác theo quy tắc; có thể không được lưu độc lập và có thể thay đổi khi dữ liệu nguồn thay đổi.

Không nên dùng cú pháp mặc định để biểu diễn thuộc tính dẫn xuất nếu hai ngữ nghĩa này khác nhau trong mô hình.

### 3.3. Mặc định phụ thuộc ngữ cảnh

Một giá trị có thể được xác định từ ngữ cảnh tạo đối tượng, ví dụ người dùng hiện tại, ngày hiện tại, tổ chức hoặc môi trường:

~~~text
entity AuditRecord {
  property createdAt: Instant = currentTime()
  property createdBy: UserId = currentUser()
}
~~~

Các hàm `currentTime()` và `currentUser()` là ví dụ giả định. DSL cần quy định chúng có được phép dùng hay không, lấy ngữ cảnh từ đâu và được đánh giá vào thời điểm nào.

Mặc định phụ thuộc ngữ cảnh có thể làm cho cùng một cấu hình tạo ra kết quả khác nhau ở những thời điểm hoặc môi trường khác nhau. Điều đó có thể phù hợp với thời gian tạo bản ghi, nhưng không phù hợp với các giá trị cần tái lập chính xác.

### 3.4. Mặc định cho tập hợp

Với thuộc tính dạng danh sách hoặc tập hợp, DSL cần định nghĩa giá trị mặc định. Một lựa chọn phổ biến là tập rỗng:

~~~text
entity Project {
  property members: List<UserId> = []
  property labels: Set<String> = {}
}
~~~

Tập rỗng có nghĩa là thuộc tính hiện diện với không phần tử. Nó khác với thuộc tính không tồn tại hoặc có giá trị null.

Cần xác định collection mặc định là đối tượng dùng chung hay được tạo mới cho từng instance. Nếu dùng chung một collection có thể thay đổi, việc sửa danh sách ở một instance có thể vô tình ảnh hưởng instance khác. Thông thường, mỗi instance nên nhận một collection độc lập hoặc collection bất biến.

### 3.5. Mặc định được tham chiếu từ một hằng số

Để tránh lặp lại giá trị, DSL có thể cho phép khai báo hằng số:

~~~text
constant DEFAULT_CURRENCY = "VND"
constant DEFAULT_RETRY_COUNT = 3

entity PaymentConfig {
  property currency: String = DEFAULT_CURRENCY
  property retryCount: Integer = DEFAULT_RETRY_COUNT
}
~~~

Cách này giúp dùng chung một giá trị và tập trung việc thay đổi. Tuy nhiên, cần quy định phạm vi hằng số, thứ tự khai báo, khả năng tham chiếu giữa mô-đun và cách phát hiện vòng phụ thuộc.

## 4. Giá trị mặc định trong mô hình trừu tượng và metamodel

Trong thiết kế DSL, cú pháp chỉ là một lớp biểu diễn. Giá trị mặc định cần được lưu trong mô hình trừu tượng để các thành phần khác có thể kiểm tra và thực thi nhất quán.

### 4.1. Mô tả thuộc tính trong metamodel

Một thuộc tính trong metamodel có thể có cấu trúc khái quát:

~~~text
Property
  name: Identifier
  type: TypeReference
  multiplicity: Multiplicity
  isOptional: Boolean
  defaultValue: ValueSpecification?
  constraints: List<Constraint>
~~~

Trong đó:

- `name` là tên thuộc tính.
- `type` xác định kiểu dữ liệu.
- `multiplicity` quy định số lượng giá trị.
- `isOptional` biểu thị thuộc tính có thể vắng mặt theo quy tắc mô hình.
- `defaultValue` chứa mô tả giá trị mặc định hoặc không có giá trị mặc định.
- `constraints` chứa các điều kiện bổ sung.

`ValueSpecification` có thể là literal, tham chiếu hằng số hoặc biểu thức. Nếu hỗ trợ biểu thức, mô hình nên giữ cấu trúc biểu thức thay vì chỉ lưu văn bản để có thể kiểm tra kiểu và tham chiếu.

### 4.2. Tách khai báo khỏi giá trị đã áp dụng

Cần phân biệt metadata của thuộc tính với giá trị cụ thể của một instance.

Ví dụ, định nghĩa:

~~~text
property currency: String = "VND"
~~~

là metadata của thuộc tính. Khi tạo hai instance:

~~~text
orderA = Order()
orderB = Order(currency = "USD")
~~~

giá trị hiệu lực có thể là:

| Instance | Giá trị tường minh | Mặc định trong mô hình | Giá trị hiệu lực |
| --- | --- | --- | --- |
| orderA | Không có | `"VND"` | `"VND"` |
| orderB | `"USD"` | `"VND"` | `"USD"` |

Không nên sửa metadata mặc định của lớp thành `"USD"` chỉ vì một instance ghi đè. Mỗi instance có trạng thái riêng; định nghĩa thuộc tính vẫn giữ mặc định ban đầu.

### 4.3. Mặc định trong UML

Trong UML, Property có thể khai báo `defaultValue` dưới dạng ValueSpecification. Điều này cho phép mô hình biểu diễn giá trị mặc định của thuộc tính ở mức mô hình, thay vì chỉ ghi một giá trị trong mã nguồn.

Ví dụ khái niệm:

~~~text
Property: retryCount
Type: Integer
DefaultValue: LiteralInteger(3)
~~~

Khi chuyển mô hình UML hoặc metamodel tương tự sang DSL, cần bảo toàn kiểu và ngữ nghĩa của ValueSpecification. Một giá trị mặc định kiểu số không nên bị chuyển thành chuỗi văn bản `"3"` nếu kiểu thuộc tính là Integer.

UML cung cấp khái niệm mô hình tổng quát; từng DSL vẫn cần quy định cách áp dụng mặc định trong runtime, đặc biệt với biểu thức, collection và giá trị phụ thuộc ngữ cảnh.

## 5. Thời điểm áp dụng giá trị mặc định

Một trong những quyết định quan trọng nhất là xác định khi nào hệ thống đánh giá và áp dụng mặc định. Có nhiều thời điểm có thể lựa chọn.

### 5.1. Khi phân tích cú pháp

Parser có thể điền giá trị mặc định ngay khi đọc cấu hình. Cách này đơn giản đối với cấu hình tĩnh, nhưng có thể làm mất thông tin về việc người dùng đã bỏ qua thuộc tính hay cố ý cung cấp giá trị.

Ví dụ, nếu parser tự điền `retryCount = 3`, bước sau không còn biết trường này đến từ tệp hay từ mặc định. Điều đó gây khó khăn khi cần hiển thị lại cấu hình, tạo cảnh báo hoặc phân biệt giá trị tường minh với giá trị được suy ra.

Vì vậy, parser thường nên giữ trạng thái “không được cung cấp” trong mô hình cú pháp hoặc mô hình đầu vào, rồi để bước áp dụng mặc định xử lý sau.

### 5.2. Khi kiểm tra và chuẩn hóa mô hình

Sau khi parse, một bước chuẩn hóa có thể áp dụng mặc định và tạo mô hình đã hoàn thiện (normalized model). Đây là lựa chọn phù hợp khi các bước kiểm tra tiếp theo cần làm việc với giá trị hiệu lực.

Quy trình:

~~~text
Văn bản DSL
    |
    v
Parser
    |
    v
Mô hình đầu vào (giữ dấu hiệu absent)
    |
    v
Kiểm tra kiểu và tham chiếu
    |
    v
Áp dụng giá trị mặc định
    |
    v
Kiểm tra ràng buộc
    |
    v
Mô hình đã chuẩn hóa
~~~

Thứ tự kiểm tra và áp dụng mặc định cần được định nghĩa. Ví dụ, parser phải xác định trường có được cung cấp hay không; giá trị mặc định sau khi áp dụng phải được kiểm tra kiểu và ràng buộc như một giá trị bình thường.

### 5.3. Khi tạo instance

Với DSL mô tả mô hình đối tượng, mặc định có thể được áp dụng khi tạo instance.

~~~text
customer = Customer(name = "Lan")
~~~

Nếu `active` có mặc định `true`, instance có thể được tạo với `active = true`. Cách này phù hợp khi mặc định là một phần của trạng thái khởi tạo đối tượng.

Nếu giá trị mặc định phụ thuộc ngữ cảnh, runtime cần có context tạo instance tại thời điểm đó.

### 5.4. Khi đọc thuộc tính

Một hệ thống có thể không lưu giá trị mặc định vào dữ liệu mà chỉ trả về mặc định khi đọc thuộc tính chưa có giá trị. Đây là kiểu fallback khi truy cập.

Ví dụ, nếu cấu hình không lưu `theme`, giao diện có thể trả về `"light"` khi đọc.

Cách này có thể hữu ích cho cấu hình phân tầng, nhưng cần phân biệt giá trị được lưu với giá trị hiệu lực. Khi người dùng cập nhật mặc định, mọi đối tượng chưa có giá trị tường minh có thể nhận kết quả mới ngay lập tức. Điều đó khác với việc gán mặc định vào instance tại thời điểm tạo.

### 5.5. So sánh thời điểm áp dụng

| Thời điểm | Đặc điểm | Cần chú ý |
| --- | --- | --- |
| Parse | Có thể đơn giản hóa mô hình đầu vào | Dễ mất dấu hiệu giá trị vắng mặt |
| Chuẩn hóa mô hình | Tách parser khỏi chính sách mặc định | Cần định nghĩa thứ tự kiểm tra |
| Tạo instance | Mặc định trở thành trạng thái ban đầu | Cần quản lý thời điểm và ngữ cảnh |
| Khi đọc | Giá trị có thể thay đổi theo cấu hình hiện tại | Cần phân biệt giá trị lưu và giá trị hiệu lực |

Không có thời điểm đúng cho mọi DSL. Hãy chọn theo mục tiêu của mô hình và đảm bảo cùng một cấu hình có hành vi dự đoán được.

## 6. Quy tắc ưu tiên khi có nhiều nguồn giá trị

Trong một hệ thống lớn, giá trị của thuộc tính có thể đến từ nhiều nguồn:

- Giá trị tường minh trong instance.
- Giá trị khai báo ở loại hoặc lớp.
- Giá trị mặc định của mô hình.
- Cấu hình của môi trường.
- Giá trị mặc định tích hợp sẵn trong runtime.

Nếu không quy định thứ tự ưu tiên, cùng một thuộc tính có thể nhận các giá trị khác nhau tùy đường thực thi.

Một thứ tự ưu tiên minh họa:

~~~text
Giá trị tường minh của instance
        >
Giá trị cấu hình được áp dụng ở phạm vi instance
        >
Giá trị mặc định của mô hình
        >
Giá trị mặc định tích hợp của runtime
~~~

Thứ tự này chỉ là ví dụ. Một DSL khác có thể đặt cấu hình môi trường lên trên giá trị trong mô hình, hoặc không cho phép runtime tự thêm mặc định.

### 6.1. Ví dụ về ưu tiên

Giả sử `timeout` có giá trị mặc định của runtime là 30 giây, mô hình khai báo 20 giây và instance ghi rõ 5 giây.

| Nguồn | Giá trị |
| --- | --- |
| Runtime | 30 giây |
| Mô hình | 20 giây |
| Instance | 5 giây |

Nếu quy tắc ưu tiên là instance cao hơn mô hình, mô hình cao hơn runtime, giá trị hiệu lực là 5 giây.

Nếu instance không cung cấp giá trị, giá trị hiệu lực sẽ là 20 giây. Nếu mô hình cũng không khai báo, runtime có thể dùng 30 giây nếu đặc tả cho phép.

### 6.2. Tránh nhiều tầng mặc định không rõ ràng

Quá nhiều lớp cấu hình có thể khiến người dùng khó biết giá trị thực tế đến từ đâu. Công cụ nên có khả năng giải thích nguồn gốc giá trị (provenance), ví dụ:

~~~text
timeout = 5s
source = instance override
overrode = model default (20s)
~~~

Thông tin này hữu ích khi gỡ lỗi, kiểm tra cấu hình và giải thích vì sao một instance có hành vi khác với mặc định chung.

## 7. Mặc định tĩnh và mặc định động

Một thuộc tính có thể có giá trị mặc định cố định hoặc được tính tại thời điểm chạy.

### 7.1. Mặc định tĩnh

Mặc định tĩnh là literal hoặc biểu thức chỉ phụ thuộc vào hằng số và có kết quả xác định trước.

~~~text
property maxRetries: Integer = 3
property encoding: String = "UTF-8"
property enabled: Boolean = true
~~~

Ưu điểm:

- Dễ kiểm tra kiểu và ràng buộc trước khi chạy.
- Có thể hiển thị rõ trong tài liệu.
- Dễ so sánh mô hình và tái lập kết quả.
- Ít phụ thuộc vào môi trường.

### 7.2. Mặc định động

Mặc định động được tính khi tạo hoặc sử dụng instance, thường dựa trên thời gian, người dùng, cấu hình môi trường hoặc dữ liệu khác.

~~~text
property createdAt: Instant = now()
property owner: UserId = currentUser()
~~~

Cần quy định:

- Hàm được phép gọi.
- Dữ liệu ngữ cảnh được cung cấp.
- Thời điểm đánh giá.
- Có đánh giá một lần hay nhiều lần.
- Kết quả có được lưu lại không.
- Cách kiểm thử và tái lập kết quả.

### 7.3. Hạn chế tác động phụ trong biểu thức mặc định

Biểu thức mặc định nên có ngữ nghĩa rõ và dễ dự đoán. Nếu cho phép biểu thức gọi dịch vụ mạng, ghi tệp hoặc thay đổi trạng thái, việc tạo instance có thể gây tác động phụ bất ngờ.

Ví dụ, một mặc định như:

~~~text
property customerId: CustomerId = createCustomer()
~~~

có thể tạo một khách hàng mới chỉ vì người dùng đọc hoặc khởi tạo cấu hình. Điều đó thường khó kiểm soát.

Một thiết kế an toàn hơn là chỉ cho phép biểu thức thuần (pure expression) trong mặc định, hoặc yêu cầu tác động phụ phải được mô tả bằng một bước thực thi riêng có quyền hạn và xử lý lỗi rõ ràng.

## 8. Kiểm tra kiểu và ràng buộc của giá trị mặc định

Giá trị mặc định là một giá trị của thuộc tính nên phải tuân thủ kiểu dữ liệu và các quy tắc miền giống giá trị tường minh.

### 8.1. Kiểm tra kiểu dữ liệu

Ví dụ:

~~~text
property retryCount: Integer = 3
property enabled: Boolean = true
property name: String = "Default"
~~~

Các mặc định này phù hợp với kiểu tương ứng.

Một khai báo không phù hợp:

~~~text
property retryCount: Integer = "three"
~~~

Nếu DSL không có quy tắc chuyển đổi chuỗi sang số, parser hoặc bước kiểm tra kiểu phải báo lỗi. Không nên âm thầm ép `"three"` thành một giá trị số hoặc thay bằng 0.

### 8.2. Kiểm tra miền giá trị

Một giá trị có thể đúng kiểu nhưng vi phạm ràng buộc:

~~~text
property retryCount: Integer = -1
constraint retryCount >= 0
~~~

`-1` là Integer hợp lệ về kiểu nhưng vi phạm điều kiện miền. Mô hình cần bị từ chối hoặc phát cảnh báo theo chính sách đã định nghĩa; không nên thực thi với mặc định sai.

### 8.3. Kiểm tra multiplicity và collection

Nếu thuộc tính có multiplicity tối thiểu là một phần tử, mặc định là collection rỗng sẽ không hợp lệ.

~~~text
property approvers: List<UserId> [1..*] = []
~~~

Mặc định `[]` chứa không phần tử, trong khi multiplicity yêu cầu ít nhất một. Kiểm tra ngữ nghĩa phải phát hiện xung đột này.

Nếu thuộc tính có multiplicity `0..*`, collection rỗng có thể hợp lệ. Cần xác định `null`, vắng mặt và collection rỗng có ý nghĩa khác nhau hay không.

### 8.4. Kiểm tra phụ thuộc giữa các thuộc tính

Nếu một mặc định tham chiếu thuộc tính khác, cần xác định thuộc tính nguồn đã có giá trị hay chưa và thứ tự đánh giá.

~~~text
property unitPrice: Decimal
property quantity: Integer = 1
property total: Decimal = quantity * unitPrice
~~~

Nếu `unitPrice` không được cung cấp, biểu thức `total` có thể không tính được. DSL cần quy định lỗi, giá trị vắng mặt hoặc thứ tự khởi tạo. Không nên để kết quả phụ thuộc vào thứ tự duyệt thuộc tính tình cờ trong runtime.

## 9. Mặc định trong kế thừa và tái sử dụng mô hình

Khi DSL hỗ trợ kế thừa, mixin hoặc tái sử dụng kiểu, một thuộc tính có thể nhận mặc định từ loại cha hoặc được loại con ghi đè.

Ví dụ:

~~~text
entity Document {
  property format: String = "PDF"
}

entity Spreadsheet extends Document {
  property format: String = "XLSX"
}
~~~

Nếu DSL cho phép ghi đè thuộc tính, instance của Spreadsheet có thể dùng `"XLSX"`, còn Document thông thường dùng `"PDF"`.

### 9.1. Quy tắc ghi đè

Cần định nghĩa:

- Loại con có được phép thay đổi mặc định không?
- Loại con có được thay đổi kiểu thuộc tính không?
- Có được thay đổi tính bắt buộc hoặc multiplicity không?
- Nếu loại con không khai báo lại, có kế thừa mặc định của loại cha không?
- Nếu nhiều mixin cung cấp cùng một thuộc tính, cách giải quyết xung đột là gì?

Một quy tắc đơn giản có thể là: thuộc tính không bị ghi đè thì kế thừa mặc định từ loại cha; nếu loại con khai báo lại mặc định, giá trị mới áp dụng cho instance của loại con. Nhưng phải giữ tương thích kiểu và ràng buộc.

### 9.2. Xung đột giữa nhiều nguồn kế thừa

Giả sử hai mixin đều định nghĩa `timeout` với mặc định khác nhau. DSL cần có quy tắc rõ:

- Cấm xung đột và yêu cầu loại con khai báo lại.
- Ưu tiên mixin theo thứ tự đã định nghĩa.
- Yêu cầu cấu hình tường minh tại nơi kết hợp.
- Chỉ cho phép kế thừa nếu các giá trị tương đương.

Không nên dựa vào thứ tự nạp tệp hoặc thứ tự plugin ngẫu nhiên để chọn mặc định.

## 10. Mặc định trong cấu hình phân cấp và môi trường

DSL cấu hình thường có nhiều tầng như mặc định hệ thống, mặc định dự án, môi trường và instance.

Ví dụ:

~~~text
defaults {
  timeout = 30s
  retryCount = 2
}

environment production {
  timeout = 10s
}

service payment {
  retryCount = 5
}
~~~

Nếu quy tắc ưu tiên là cấu hình service cao hơn environment, environment cao hơn defaults, giá trị hiệu lực của service payment trong production có thể là:

| Thuộc tính | Giá trị hiệu lực | Nguồn |
| --- | --- | --- |
| `timeout` | `10s` | production |
| `retryCount` | `5` | service payment |

Nếu một service không ghi `retryCount`, nó nhận 2 từ defaults. DSL cần định nghĩa rõ cách hợp nhất cấu hình (configuration merge), đặc biệt với collection, map và giá trị null.

### 10.1. Thay thế hay hợp nhất collection?

Với scalar, ghi đè thường dễ hiểu. Với collection, có thể có hai chính sách:

- **Replace:** collection ở tầng sau thay toàn bộ collection trước.
- **Merge:** hợp nhất phần tử của các tầng.

Ví dụ:

~~~text
defaults {
  tags = ["managed", "internal"]
}

service payment {
  tags = ["critical"]
}
~~~

Theo replace, tags hiệu lực là `["critical"]`. Theo merge, tags có thể là `["managed", "internal", "critical"]`.

Hai kết quả khác nhau. DSL cần quy định theo từng loại thuộc tính hoặc cung cấp cú pháp chỉ rõ replace/merge.

## 11. Giá trị mặc định và dữ liệu được lưu trữ

Một quyết định quan trọng là có lưu giá trị mặc định vào instance hay chỉ tính giá trị hiệu lực khi đọc.

### 11.1. Ghi giá trị mặc định khi tạo

Khi tạo instance, runtime có thể ghi giá trị mặc định vào dữ liệu.

Ví dụ, một bản ghi được lưu:

~~~json
{
  "id": 42,
  "currency": "VND",
  "status": "PENDING"
}
~~~

Ưu điểm là dữ liệu thể hiện rõ trạng thái tại thời điểm tạo. Khi mặc định của mô hình thay đổi, bản ghi cũ vẫn giữ giá trị đã lưu.

Đổi lại, dữ liệu có thể lặp lại nhiều giá trị mặc định và cần xử lý migration khi muốn thay đổi dữ liệu cũ.

### 11.2. Chỉ áp dụng mặc định khi đọc

Hệ thống có thể lưu:

~~~json
{
  "id": 42
}
~~~

Khi đọc, runtime trả về `currency = "VND"` vì mô hình hiện tại quy định như vậy.

Ưu điểm là dữ liệu lưu gọn và thay đổi mặc định có thể áp dụng cho các bản ghi chưa có giá trị tường minh. Nhược điểm là cùng một dữ liệu cũ có thể được diễn giải khác nhau sau khi mô hình đổi mặc định.

### 11.3. So sánh hai cách

| Cách lưu | Khi thay đổi mặc định | Điểm cần chú ý |
| --- | --- | --- |
| Ghi mặc định vào instance | Giá trị cũ thường được giữ | Có thể cần migration dữ liệu |
| Chỉ fallback khi đọc | Bản ghi thiếu trường nhận mặc định mới | Ý nghĩa dữ liệu lịch sử có thể thay đổi |
| Lưu cả giá trị và nguồn | Có thể phân biệt tường minh với mặc định | Mô hình lưu trữ phức tạp hơn |

Với dữ liệu nghiệp vụ quan trọng như tiền tệ, thuế suất hoặc chính sách tính phí, cần cân nhắc lưu giá trị hiệu lực tại thời điểm giao dịch để giữ ý nghĩa lịch sử.

## 12. Thay đổi giá trị mặc định và tương thích phiên bản

Thay đổi giá trị mặc định có thể là thay đổi ngữ nghĩa ngay cả khi không đổi cú pháp.

Giả sử phiên bản 1 có:

~~~text
property retryCount: Integer = 2
~~~

Phiên bản 2 đổi thành:

~~~text
property retryCount: Integer = 5
~~~

Một cấu hình không khai báo `retryCount` có thể thực hiện số lần thử khác trước. Điều này có thể làm tăng thời gian xử lý, tải hệ thống hoặc chi phí.

### 12.1. Những thay đổi cần đánh giá

- Thay đổi literal mặc định.
- Thay đổi biểu thức mặc định.
- Thay đổi thứ tự ưu tiên giữa các nguồn.
- Thay đổi thời điểm áp dụng.
- Thay đổi cách xử lý null hoặc trường vắng mặt.
- Thay đổi chính sách merge collection.
- Thay đổi mặc định kế thừa từ loại cha hoặc mixin.

Tất cả đều có thể làm thay đổi kết quả dù tệp DSL không thay đổi.

### 12.2. Chiến lược quản lý thay đổi

Có thể sử dụng các biện pháp:

1. Gắn mặc định với phiên bản mô hình hoặc schema.
2. Ghi nhận mặc định đã áp dụng trong dữ liệu nếu cần tái lập lịch sử.
3. Phát cảnh báo khi giá trị mặc định thay đổi.
4. Yêu cầu cấu hình tường minh với những thuộc tính có tác động lớn.
5. Cung cấp công cụ migration cho cấu hình hoặc dữ liệu cũ.
6. Lưu nguồn gốc giá trị để giải thích hành vi.

Không nên thay đổi mặc định nhạy cảm mà không đánh giá tác động đến cấu hình hiện có.

## 13. Biểu diễn và triển khai mặc định trong DSL

Có nhiều cách để thể hiện mặc định trong cú pháp. Cần chọn cách phù hợp với phong cách khai báo của DSL.

### 13.1. Dùng dấu bằng

~~~text
property enabled: Boolean = true
property retryCount: Integer = 3
~~~

Cú pháp ngắn, quen thuộc và dễ đọc. Tuy nhiên, nếu DSL dùng dấu bằng cho phép gán trong câu lệnh thực thi, cần xác định ngữ cảnh để tránh mơ hồ.

### 13.2. Dùng từ khóa default

~~~text
property currency: String default "VND"
property retryCount: Integer default 3
~~~

Cách này làm rõ ý nghĩa mặc định và có thể dễ mở rộng cho biểu thức hoặc chính sách:

~~~text
property createdAt: Instant default now()
~~~

Đổi lại, cú pháp dài hơn. Cần thống nhất vị trí từ khóa `default` trong khai báo.

### 13.3. Dùng khối cấu hình mặc định

~~~text
defaults {
  currency = "VND"
  retryCount = 3
}

entity Payment {
  property currency: String
  property retryCount: Integer
}
~~~

Cách này hữu ích khi nhiều thuộc tính chia sẻ một bộ mặc định. DSL cần định nghĩa phạm vi áp dụng và hành vi khi một thuộc tính không có trong khối defaults.

### 13.4. Parser và bộ áp dụng mặc định

Một kiến trúc xử lý có thể gồm:

~~~text
Parser
  |
  v
Property Declaration
  |
  v
Type Checker
  |
  v
Default Resolver
  |
  v
Constraint Validator
  |
  v
Normalized Model
~~~

- Parser nhận diện cú pháp và giữ lại việc thuộc tính có được cung cấp hay không.
- Type Checker xác minh kiểu của literal hoặc biểu thức mặc định.
- Default Resolver xác định nguồn và giá trị hiệu lực.
- Constraint Validator kiểm tra giá trị sau khi áp dụng mặc định.
- Normalized Model cung cấp cấu trúc thống nhất cho bộ thực thi hoặc công cụ sinh mã.

Không nên để parser tự gọi các hàm runtime có tác động phụ chỉ để lấy mặc định. Việc phân tích cú pháp và việc đánh giá biểu thức nên có ranh giới rõ.

## 14. Ví dụ triển khai trong Java

Một cách biểu diễn đơn giản trong Java có thể dùng một đối tượng mô tả thuộc tính và một bộ giải quyết mặc định.

~~~java
import java.util.Optional;

record PropertyDefinition<T>(
    String name,
    Class<T> type,
    Optional<T> defaultValue
) {}

static <T> T resolve(
    PropertyDefinition<T> definition,
    Optional<T> suppliedValue
) {
    return suppliedValue
        .or(() -> definition.defaultValue())
        .orElseThrow(() ->
            new IllegalArgumentException(
                "Missing required property: " + definition.name()
            )
        );
}
~~~

Ví dụ sử dụng:

~~~java
var currency = new PropertyDefinition<>(
    "currency",
    String.class,
    Optional.of("VND")
);

String effectiveCurrency = resolve(
    currency,
    Optional.empty()
);
~~~

`effectiveCurrency` nhận giá trị `"VND"`.

Đây là ví dụ tối giản. Trong hệ thống thật, `Optional.empty()` chỉ thể hiện không có giá trị được truyền; nếu cần phân biệt “không được cung cấp” với “được cung cấp null”, phải dùng kiểu biểu diễn trạng thái đầu vào riêng. Ngoài ra, kiểm tra `Class<T>` chưa đủ cho các kiểu generic hoặc kiểu miền phức tạp; cần hệ thống type descriptor phù hợp.

### 14.1. Phân biệt absent, null và value

Một mô hình đầu vào rõ ràng có thể dùng ba trạng thái:

~~~java
sealed interface InputValue<T> {
    record Absent<T>() implements InputValue<T> {}
    record ExplicitNull<T>() implements InputValue<T> {}
    record Present<T>(T value) implements InputValue<T> {}
}
~~~

Bộ giải quyết có thể quy định:

- Absent: dùng mặc định nếu có, nếu không thì báo thiếu hoặc giữ vắng mặt.
- ExplicitNull: giữ null nếu kiểu và chính sách cho phép; không tự động dùng mặc định trừ khi đặc tả nói rõ.
- Present: dùng giá trị được cung cấp sau khi kiểm tra kiểu và ràng buộc.

Cách biểu diễn này giúp tránh mất thông tin khi đọc JSON, YAML hoặc các nguồn cấu hình khác.

## 15. Kiểm thử giá trị mặc định

Mặc định là một phần của ngữ nghĩa DSL, do đó cần có kiểm thử ở nhiều mức.

### 15.1. Kiểm thử phân tích cú pháp

Kiểm tra parser nhận diện đúng:

- Thuộc tính có literal mặc định.
- Thuộc tính không có mặc định.
- Mặc định là enum, collection hoặc biểu thức.
- Cú pháp mặc định sai định dạng.
- Giá trị mặc định thiếu hoặc có token không hợp lệ.

### 15.2. Kiểm thử kiểu và ràng buộc

Kiểm tra:

- Giá trị mặc định đúng kiểu.
- Giá trị mặc định sai kiểu bị từ chối.
- Giá trị mặc định thỏa mãn ràng buộc.
- Collection mặc định thỏa multiplicity.
- Biểu thức mặc định tham chiếu đến thuộc tính hợp lệ.
- Vòng phụ thuộc giữa các biểu thức mặc định được phát hiện.

### 15.3. Kiểm thử ưu tiên và trạng thái đầu vào

Với mỗi thuộc tính, nên có trường hợp:

| Trường hợp | Kết quả cần xác định |
| --- | --- |
| Không cung cấp | Có áp dụng mặc định không? |
| Cung cấp giá trị bình thường | Giá trị nào thắng? |
| Cung cấp chuỗi rỗng | Có được coi là giá trị tường minh không? |
| Cung cấp null | Giữ null, dùng mặc định hay báo lỗi? |
| Cung cấp sai kiểu | Báo lỗi ở bước nào? |
| Giá trị bị ghi đè ở tầng khác | Nguồn nào có độ ưu tiên cao hơn? |

### 15.4. Kiểm thử tương thích

Khi thay đổi mặc định, cần có kiểm thử cho cấu hình cũ không khai báo thuộc tính. Kiểm tra cả giá trị hiệu lực, hành vi runtime và dữ liệu được lưu.

Với mặc định động, cần cố định đồng hồ, người dùng hoặc môi trường trong kiểm thử để kết quả có thể lặp lại. Không nên phụ thuộc vào thời gian thật hoặc tài khoản thực khi chạy kiểm thử tự động.

## 16. Những lỗi thiết kế thường gặp

**Không phân biệt vắng mặt và null.** Điều này khiến người dùng không thể yêu cầu giữ giá trị rỗng nếu runtime luôn tự thay bằng mặc định. Hãy quy định trạng thái đầu vào riêng.

**Đặt mặc định sai kiểu.** Giá trị mặc định phải tuân thủ type system. Không nên âm thầm ép kiểu hoặc thay bằng giá trị khác khi không hợp lệ.

**Dùng mặc định để che giấu dữ liệu bắt buộc bị thiếu.** Các thuộc tính định danh, quyền hạn hoặc thông tin giao dịch quan trọng thường cần được cung cấp hoặc sinh bằng cơ chế có ngữ nghĩa rõ ràng.

**Đánh giá biểu thức mặc định nhiều lần ngoài dự kiến.** Một biểu thức thời gian có thể cho kết quả khác mỗi lần đọc. Hãy quy định rõ đánh giá một lần hay mỗi lần truy cập.

**Cho phép tác động phụ trong mặc định.** Việc tạo tài nguyên hoặc gọi dịch vụ bên ngoài trong lúc khởi tạo có thể gây khó khăn cho kiểm thử và phục hồi. Nên tách tác động phụ thành bước thực thi riêng.

**Dùng collection mặc định có thể thay đổi chung.** Các instance có thể vô tình chia sẻ trạng thái. Hãy tạo collection riêng hoặc dùng cấu trúc bất biến.

**Không quy định thứ tự ưu tiên.** Giá trị từ instance, mô hình, môi trường và runtime có thể xung đột. Cần một quy tắc hợp nhất rõ ràng.

**Thay đổi mặc định mà không xét dữ liệu cũ.** Cấu hình cũ có thể thay đổi hành vi khi chạy trên phiên bản mới. Cần versioning, migration hoặc ghi lại giá trị đã áp dụng khi phù hợp.

**Nhầm mặc định với thuộc tính dẫn xuất.** Một giá trị được tính lại từ thuộc tính khác có thể là derived property chứ không phải default. Hãy chọn khái niệm đúng với vòng đời và ngữ nghĩa của dữ liệu.

## 17. Quy trình thiết kế giá trị mặc định thuộc tính

Khi định nghĩa một thuộc tính trong metamodel hoặc DSL, có thể tiến hành theo các bước:

### Bước 1: Xác định ý nghĩa nghiệp vụ

Hỏi vì sao thuộc tính cần có mặc định. Đây có phải giá trị phổ biến, giá trị an toàn, giá trị khởi tạo hay một quy ước của môi trường? Nếu không có lý do rõ ràng, có thể nên yêu cầu người dùng cung cấp giá trị.

### Bước 2: Xác định kiểu và tính tùy chọn

Chọn kiểu dữ liệu, multiplicity và khả năng vắng mặt. Làm rõ thuộc tính bắt buộc có thể được đáp ứng bằng mặc định hay phải do người dùng nhập.

### Bước 3: Chọn dạng mặc định

Quyết định dùng literal, hằng số, biểu thức thuần hay giá trị phụ thuộc ngữ cảnh. Hạn chế biểu thức có tác động phụ.

### Bước 4: Xác định thời điểm áp dụng

Chọn áp dụng khi chuẩn hóa, tạo instance hay đọc thuộc tính. Quyết định này ảnh hưởng đến lưu trữ, khả năng tái lập và thay đổi mặc định về sau.

### Bước 5: Định nghĩa ưu tiên và ghi đè

Xác định giá trị tường minh, mặc định của mô hình, cấu hình môi trường và runtime được ưu tiên thế nào. Làm rõ null, chuỗi rỗng và trường bị bỏ qua.

### Bước 6: Kiểm tra kiểu và ràng buộc

Đảm bảo mặc định hợp lệ với kiểu, multiplicity, invariant và các điều kiện miền. Phát hiện tham chiếu không tồn tại hoặc phụ thuộc vòng.

### Bước 7: Xem xét kế thừa và tương thích

Xác định mặc định có được kế thừa, ghi đè hoặc hợp nhất hay không. Đánh giá tác động khi thay đổi mặc định ở phiên bản sau.

### Bước 8: Tài liệu hóa và kiểm thử

Ghi rõ mặc định, nguồn, thời điểm áp dụng, cách ghi đè và hành vi khi thiếu giá trị. Viết kiểm thử cho các trường hợp absent, null, explicit value và các tầng cấu hình.

## 18. Ví dụ tổng hợp: mô hình cấu hình dịch vụ

Giả sử một DSL được dùng để mô tả dịch vụ ứng dụng:

~~~text
entity ServiceConfig {
  property enabled: Boolean = true
  property port: Integer = 8080
  property timeout: Duration = 30s
  property retryCount: Integer = 2
  property labels: List<String> = []
}

constraint ValidPort {
  require ServiceConfig.port >= 1
  require ServiceConfig.port <= 65535
}

constraint ValidRetryCount {
  require ServiceConfig.retryCount >= 0
}
~~~

Người dùng tạo cấu hình:

~~~text
service payment {
  port = 9090
  timeout = 10s
}
~~~

Sau khi áp dụng mặc định, mô hình hiệu lực có thể là:

| Thuộc tính | Giá trị hiệu lực | Nguồn |
| --- | --- | --- |
| `enabled` | `true` | Mặc định của ServiceConfig |
| `port` | `9090` | Giá trị tường minh của service |
| `timeout` | `10s` | Giá trị tường minh của service |
| `retryCount` | `2` | Mặc định của ServiceConfig |
| `labels` | `[]` | Mặc định của ServiceConfig |

Bộ kiểm tra tiếp tục xác minh `port` nằm trong khoảng hợp lệ và `retryCount` không âm. Nếu người dùng đặt `port = 70000`, giá trị tường minh ghi đè mặc định nhưng vẫn bị từ chối vì vi phạm ràng buộc.

Nếu cấu hình môi trường production quy định `timeout = 15s`, kết quả cuối cùng phụ thuộc quy tắc ưu tiên đã công bố. Công cụ nên giải thích giá trị hiệu lực đến từ nguồn nào để người vận hành hiểu được cấu hình thực tế.

## 19. Kết luận

Giá trị mặc định thuộc tính mô tả giá trị được sử dụng khi người dùng không cung cấp giá trị tường minh theo quy tắc của DSL. Trong mô hình trừu tượng, mặc định là một phần của metadata thuộc tính và có thể được biểu diễn bằng literal, hằng số hoặc ValueSpecification. Runtime hoặc bước chuẩn hóa áp dụng giá trị đó tại thời điểm đã được đặc tả.

Khi thiết kế, cần phân biệt mặc định với giá trị khởi tạo, null, tính bắt buộc, giá trị dẫn xuất và ràng buộc. Cần định nghĩa thời điểm đánh giá, thứ tự ưu tiên, khả năng ghi đè, cách kế thừa, cách xử lý collection và tác động của thay đổi mặc định đến dữ liệu cũ.

Một mặc định tốt làm cho mô hình ngắn gọn và dễ sử dụng mà vẫn giữ được hành vi dự đoán được. Hãy chỉ đặt mặc định khi có lý do miền rõ ràng, kiểm tra nó như mọi giá trị khác và giúp người dùng biết giá trị hiệu lực được lấy từ đâu.

