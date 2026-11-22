# So sánh an toàn kiểu giữa DSL nội bộ và DSL bên ngoài

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích an toàn kiểu (type safety) và phân biệt nó với kiểm tra cú pháp, kiểm tra kiểu tĩnh và xác thực quy tắc nghiệp vụ.
- Mô tả cách DSL nội bộ (internal hoặc embedded DSL) tận dụng hệ thống kiểu của ngôn ngữ chủ.
- Mô tả cách DSL bên ngoài (external DSL) xây dựng hệ thống kiểu và bộ kiểm tra ngữ nghĩa riêng.
- So sánh thời điểm phát hiện lỗi, khả năng diễn đạt, chất lượng thông báo lỗi, công cụ và chi phí triển khai của hai cách tiếp cận.
- Nhận diện những trường hợp một DSL trông có vẻ an toàn kiểu nhưng vẫn có thể nhận dữ liệu sai hoặc gây lỗi khi chạy.
- Lựa chọn chiến lược kiểm tra kiểu phù hợp với miền, người dùng và môi trường thực thi.

## 1. Bối cảnh: DSL nội bộ và DSL bên ngoài

Ngôn ngữ chuyên biệt miền (Domain-Specific Language, DSL) cung cấp cách diễn đạt phù hợp với một lĩnh vực hoặc nhóm tác vụ. Khi thiết kế DSL, nhóm cần quyết định ngôn ngữ sẽ dựa trên cú pháp của một ngôn ngữ lập trình có sẵn hay có cú pháp độc lập.

**DSL nội bộ (internal DSL hoặc embedded DSL)** được xây dựng bên trong một ngôn ngữ chủ. Nó tận dụng hàm, đối tượng, kiểu dữ liệu, generic, toán tử và các cơ chế của ngôn ngữ chủ để tạo ra cách diễn đạt chuyên biệt. Ví dụ, Gradle Kotlin DSL dùng Kotlin để mô tả cấu hình build; LINQ trong C# cho phép biểu diễn truy vấn bằng các cấu trúc của C#.

**DSL bên ngoài (external DSL)** có cú pháp riêng, tách biệt với cú pháp của ngôn ngữ lập trình chủ. Một công cụ chuyên biệt đọc và xử lý ngôn ngữ đó. SQL, CSS và regex là những ví dụ quen thuộc. Một DSL bên ngoài thường cần grammar, parser và bộ xử lý ngữ nghĩa hoặc runtime tương ứng.

Hai cách tiếp cận khác nhau ở nơi cú pháp được định nghĩa và nơi chương trình được kiểm tra. Sự khác biệt này ảnh hưởng đến an toàn kiểu, nhưng không quyết định trước DSL nào an toàn hơn. DSL nội bộ có thể tận dụng hệ kiểu mạnh của ngôn ngữ chủ; DSL bên ngoài có thể tự xây dựng hệ kiểu tĩnh rất chặt chẽ. Ngược lại, cả hai đều có thể được thiết kế lỏng lẻo và chỉ phát hiện lỗi khi chạy.

## 2. An toàn kiểu là gì?

An toàn kiểu (type safety) là mức độ mà một ngôn ngữ hoặc hệ thống ngăn chương trình thực hiện những thao tác không hợp lệ đối với kiểu dữ liệu. Ví dụ, cộng hai số nguyên có thể hợp lệ; lấy độ dài của một chuỗi có thể hợp lệ; nhưng gọi thao tác chỉ dành cho số nguyên trên một giá trị là đối tượng đơn hàng cần bị từ chối nếu không có quy tắc chuyển đổi thích hợp.

Trong thực tế, an toàn kiểu không chỉ là việc khai báo biến có kiểu. Một hệ thống an toàn kiểu cần bảo đảm các biểu thức được tạo ra và xử lý theo các quy tắc kiểu đã xác định. Tùy ngôn ngữ, việc kiểm tra có thể diễn ra trước khi chạy, trong khi chạy hoặc kết hợp cả hai.

### 2.1. Kiểm tra kiểu tĩnh và kiểm tra kiểu động

- **Kiểm tra kiểu tĩnh (static type checking):** hệ thống kiểm tra kiểu trước khi thực thi, thường trong quá trình biên dịch hoặc phân tích chương trình. Lỗi không tương thích kiểu có thể được phát hiện sớm.
- **Kiểm tra kiểu động (dynamic type checking):** hệ thống kiểm tra kiểu khi biểu thức được thực thi. Một chương trình có thể được chấp nhận trước khi chạy nhưng phát sinh lỗi kiểu ở một nhánh hoặc dữ liệu cụ thể.

Kiểm tra tĩnh giúp phát hiện nhiều lỗi sớm và hỗ trợ công cụ phát triển. Kiểm tra động linh hoạt hơn khi kiểu chỉ biết được từ dữ liệu thực tế, nhưng một số lỗi chỉ xuất hiện khi chương trình chạy đến trường hợp liên quan.

Một DSL có thể kết hợp hai cách. Chẳng hạn, trình biên dịch có thể kiểm tra kiểu của biểu thức đã biết, còn runtime tiếp tục xác thực dữ liệu nhận từ tệp hoặc dịch vụ bên ngoài.

### 2.2. Cú pháp đúng không đồng nghĩa với kiểu đúng

Cú pháp (syntax) quy định cấu trúc nào được phép viết. Kiểm tra cú pháp trả lời câu hỏi: chuỗi đầu vào có tuân theo grammar hay không?

Kiểm tra kiểu trả lời câu hỏi: các giá trị và thao tác trong cấu trúc đó có tương thích với nhau hay không?

Ví dụ, một grammar có thể chấp nhận biểu thức:

~~~text
total + "free"
~~~

Biểu thức này có thể đúng cú pháp nếu grammar cho phép phép cộng giữa hai biểu thức bất kỳ. Tuy nhiên, nếu total có kiểu số và "free" có kiểu chuỗi, bộ kiểm tra kiểu có thể từ chối vì phép cộng không được định nghĩa cho cặp kiểu đó.

Parser thành công chỉ chứng minh đầu vào có cấu trúc hợp lệ. Nó chưa chứng minh biểu thức có ý nghĩa hoặc có thể thực thi an toàn.

### 2.3. Kiểu đúng không đồng nghĩa với đúng nghiệp vụ

Một biểu thức có thể hoàn toàn hợp lệ về kiểu nhưng vẫn vi phạm quy tắc miền. Ví dụ, phép trừ hai giá trị tiền có cùng kiểu Money có thể hợp lệ về kiểu, nhưng số tiền hoàn lại có thể lớn hơn số tiền đã thu. Tương tự, một giá trị ngày có thể đúng kiểu Date nhưng nằm ngoài khoảng thời gian mà nghiệp vụ cho phép.

Vì vậy, cần phân biệt ít nhất bốn lớp kiểm tra:

| Lớp kiểm tra | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| Cú pháp | Cấu trúc có đúng grammar không? | Thiếu dấu đóng ngoặc |
| Phân giải tên | Tên có tồn tại trong ngữ cảnh không? | Tham chiếu trường order.prcie không tồn tại |
| Kiểu và ngữ nghĩa tĩnh | Các toán hạng và thao tác có tương thích không? | Cộng Money với Customer |
| Quy tắc miền và runtime | Giá trị cụ thể có hợp lệ trong tình huống thực tế không? | Hoàn tiền vượt số tiền đã thu |

Một DSL tốt xác định rõ lớp nào được kiểm tra ở thời điểm nào và trả về lỗi đủ cụ thể để người viết sửa.

### 2.4. Vì sao an toàn kiểu quan trọng với DSL?

DSL thường được dùng để mô tả quy tắc, truy vấn, cấu hình hoặc quy trình. Một biểu thức sai kiểu có thể làm cấu hình thất bại, tạo kết quả sai hoặc gây lỗi trong lúc xử lý dữ liệu thật.

An toàn kiểu có thể:

- Phát hiện sớm những phép toán không có ý nghĩa.
- Ngăn truy cập thuộc tính không tồn tại hoặc gọi thao tác trên sai loại đối tượng.
- Giảm lỗi do nhầm đơn vị, trạng thái hoặc loại dữ liệu.
- Hỗ trợ tự hoàn thành, điều hướng và tái cấu trúc trong IDE.
- Làm rõ hợp đồng giữa người viết DSL và bộ máy thực thi.

Mức độ an toàn cần phù hợp với hậu quả của lỗi. DSL cấu hình màu sắc có thể chấp nhận một số lỗi được phát hiện lúc tải cấu hình; DSL điều khiển thanh toán, quyền truy cập hoặc quy trình sản xuất cần xác thực chặt hơn.

## 3. An toàn kiểu trong DSL nội bộ

### 3.1. DSL nội bộ tận dụng hệ kiểu của ngôn ngữ chủ

Vì DSL nội bộ được biểu diễn bằng mã của một ngôn ngữ lập trình, trình biên dịch hoặc bộ kiểm tra kiểu của ngôn ngữ chủ có thể kiểm tra nhiều biểu thức. Nếu API DSL được thiết kế với kiểu cụ thể, người dùng có thể nhận lỗi ngay khi biên dịch.

Ví dụ, một DSL truy vấn nhúng trong Kotlin có thể cung cấp các hàm và kiểu biểu thức. Một DSL trong Java có thể dùng generic và interface để giới hạn các phép toán hợp lệ. C# có thể dùng kiểu, extension method và expression tree để xây dựng truy vấn.

Lợi thế lớn là nhóm không phải xây dựng toàn bộ hệ thống kiểu từ đầu. Hệ kiểu, compiler, IDE, công cụ refactor và thư viện của ngôn ngữ chủ đã có sẵn.

### 3.2. Ví dụ: biểu thức có kiểu trong DSL nhúng

Giả sử DSL cần biểu diễn biểu thức số nguyên. Ta có thể mô hình hóa biểu thức với tham số kiểu:

~~~kotlin
sealed interface Expr<T>

data class IntLiteral(val value: Int) : Expr<Int>
data class TextLiteral(val value: String) : Expr<String>

data class Add(
    val left: Expr<Int>,
    val right: Expr<Int>
) : Expr<Int>

fun add(left: Expr<Int>, right: Expr<Int>): Expr<Int> =
    Add(left, right)
~~~

Ở đây, Expr<Int> biểu diễn một biểu thức tạo ra số nguyên; Expr<String> biểu diễn một biểu thức tạo ra chuỗi. Hàm add chỉ nhận hai biểu thức số nguyên. Khi lập trình viên cố truyền TextLiteral vào vị trí yêu cầu Expr<Int>, trình biên dịch Kotlin có thể báo lỗi trước khi chương trình chạy.

Ví dụ cách sử dụng:

~~~kotlin
val price = IntLiteral(120)
val quantity = IntLiteral(3)
val total = add(price, quantity)
~~~

Lời gọi dưới đây sẽ không thỏa kiểu tham số của hàm:

~~~kotlin
val invalid = add(IntLiteral(120), TextLiteral("three"))
~~~

Các đoạn mã trên minh họa ý tưởng thiết kế kiểu, không phải một thư viện DSL hoàn chỉnh. Điểm quan trọng là chữ ký API thể hiện ràng buộc miền ở ngay trong hệ kiểu của ngôn ngữ chủ.

### 3.3. Dùng kiểu riêng để phân biệt khái niệm nghiệp vụ

Một lỗi thường gặp là dùng cùng một kiểu nguyên thủy cho nhiều khái niệm khác nhau. Ví dụ, mã khách hàng và mã đơn hàng đều được biểu diễn bằng String. Trình biên dịch không thể phân biệt hai giá trị nếu API chỉ yêu cầu String.

DSL nội bộ có thể tạo kiểu riêng:

~~~kotlin
@JvmInline
value class CustomerId(val value: String)

@JvmInline
value class OrderId(val value: String)

data class Order(
    val id: OrderId,
    val customerId: CustomerId
)

fun loadOrder(id: OrderId): Order = TODO()
~~~

Khi dùng CustomerId ở nơi cần OrderId, lỗi kiểu có thể được phát hiện lúc biên dịch. Cách làm này giúp phân biệt hai khái niệm ngay cả khi cách lưu trữ bên dưới đều là chuỗi.

Có thể mở rộng ý tưởng với kiểu Money, Percentage, EmailAddress, PositiveQuantity hoặc kiểu trạng thái riêng. Các kiểu chuyên biệt làm cho chữ ký DSL phản ánh từ vựng miền và giảm việc nhầm lẫn giữa những giá trị có cùng dạng vật lý.

### 3.4. Mã hóa trạng thái hợp lệ bằng kiểu

Một số DSL nội bộ có thể dùng kiểu tổng quát hoặc kiểu trạng thái để giới hạn trình tự thao tác. Ví dụ, API mô tả quy trình có thể phân biệt đơn hàng ở trạng thái nháp và đơn hàng đã xác nhận:

~~~kotlin
sealed interface OrderStage
data object Draft : OrderStage
data object Confirmed : OrderStage

class Order<S : OrderStage> internal constructor(
    val id: OrderId
)

fun confirm(order: Order<Draft>): Order<Confirmed> =
    Order(order.id)
~~~

Chữ ký của confirm cho biết thao tác nhận một đơn hàng nháp và trả về một đơn hàng đã xác nhận. Một API được thiết kế đầy đủ có thể không cung cấp thao tác chỉ dành cho trạng thái đã xác nhận trên Order<Draft>.

Đây là kỹ thuật thường được gọi là kiểu trạng thái (typestate). Nó đưa một phần quy tắc chuyển trạng thái vào hệ thống kiểu để compiler có thể kiểm tra.

Tuy nhiên, typestate không tự xác minh mọi điều kiện nghiệp vụ. Ví dụ, đơn hàng có thể chỉ được xác nhận khi còn hàng và phương thức thanh toán hợp lệ. Những điều kiện phụ thuộc dữ liệu thực tế vẫn cần được kiểm tra trong runtime hoặc một lớp xác thực khác.

### 3.5. Generic và kiểu biểu thức giúp ràng buộc phép toán

Generic cho phép API biểu diễn quan hệ giữa kiểu đầu vào và đầu ra. Ví dụ, một hàm lọc có thể nhận một biểu thức boolean và một tập phần tử kiểu T, rồi trả về một tập phần tử cùng kiểu T.

~~~kotlin
data class Field<T>(val name: String)
data class Predicate<T>(val description: String)

fun <T> greaterThan(field: Field<Int>, value: Int): Predicate<T> =
    Predicate("$field > $value")
~~~

Đây chỉ là phác thảo ý tưởng. Trong một DSL thực tế, chữ ký nên thể hiện rõ kiểu của đối tượng chứa trường, kiểu giá trị của trường và kiểu kết quả. Generic tốt giúp loại bỏ nhiều tổ hợp sai ngay tại API.

Người thiết kế cũng có thể dùng sealed class, interface, variance, extension function, type inference hoặc các kiểu đánh dấu (marker types) để giới hạn cấu trúc hợp lệ.

### 3.6. Ưu điểm của an toàn kiểu trong DSL nội bộ

- **Tái sử dụng compiler:** nhiều lỗi kiểu được phát hiện bằng công cụ sẵn có của ngôn ngữ chủ.
- **Phản hồi sớm:** lỗi có thể xuất hiện ngay trong IDE hoặc khi biên dịch.
- **Tự hoàn thành và điều hướng:** IDE hiểu kiểu của biểu thức nên có thể gợi ý trường, hàm và phương thức phù hợp.
- **Tái cấu trúc an toàn hơn:** đổi tên kiểu hoặc hàm DSL có thể được công cụ hỗ trợ tìm và sửa các nơi sử dụng.
- **Tận dụng thư viện:** DSL có thể dùng hệ kiểu, generic, collection và abstraction của ngôn ngữ chủ.
- **Chi phí triển khai thấp hơn:** nhóm có thể tập trung vào API miền thay vì viết parser và type checker độc lập.

### 3.7. Giới hạn và rủi ro của DSL nội bộ

DSL nội bộ không tự động an toàn chỉ vì ngôn ngữ chủ có hệ kiểu mạnh.

**API quá tổng quát:** nếu mọi giá trị được nhận dưới dạng Any, Object, dynamic hoặc một kiểu chung, compiler không còn đủ thông tin để kiểm tra các thao tác miền.

~~~kotlin
fun setValue(target: Any, value: Any) {
    // Kiểm tra tính tương thích có thể bị đẩy sang runtime.
}
~~~

**Ép kiểu không an toàn:** các phép ép kiểu thủ công, unchecked cast, reflection hoặc truy cập dữ liệu không có kiểu có thể phá vỡ bảo đảm mà API tạo ra.

**Dữ liệu bên ngoài:** giá trị đọc từ JSON, CSV, cơ sở dữ liệu hoặc HTTP thường cần được parse và xác thực. Việc một đối tượng trong mã có kiểu Order không chứng minh dữ liệu đầu vào ban đầu đã là một đơn hàng hợp lệ.

**Ràng buộc miền không được mã hóa:** API có thể cho phép cộng hai Money nhưng không kiểm tra đơn vị tiền tệ; có thể cho phép đặt số lượng âm nếu chỉ dùng Int; hoặc cho phép gọi thao tác trên trạng thái không hợp lệ nếu kiểu quá rộng.

**Thông báo lỗi mang tính kỹ thuật:** lỗi compiler có thể nói về generic, overload hoặc kiểu tham số, trong khi người dùng DSL cần biết rằng “số lượng phải lớn hơn 0”.

**Cú pháp bị giới hạn bởi ngôn ngữ chủ:** nếu ngôn ngữ chủ không cho phép một cách diễn đạt phù hợp, DSL có thể khó đọc hoặc cần nhiều dấu ngoặc và lời gọi hàm. Điều này không trực tiếp làm giảm an toàn kiểu, nhưng có thể làm API khó dùng và khuyến khích người viết đi vòng qua các cơ chế kiểm tra.

## 4. An toàn kiểu trong DSL bên ngoài

### 4.1. DSL bên ngoài cần tự định nghĩa quá trình kiểm tra

DSL bên ngoài có cú pháp riêng nên compiler của ngôn ngữ chủ không trực tiếp hiểu nội dung DSL. Một công cụ xử lý thường cần các giai đoạn:

1. Đọc chuỗi nguồn.
2. Phân tích từ vựng và cú pháp.
3. Tạo cây cú pháp trừu tượng (Abstract Syntax Tree, AST).
4. Phân giải tên và phạm vi.
5. Kiểm tra kiểu và ngữ nghĩa tĩnh.
6. Diễn giải, sinh mã hoặc tạo kế hoạch thực thi.
7. Kiểm tra điều kiện phụ thuộc dữ liệu thực tế trong runtime.

Parser có thể xác nhận rằng biểu thức tuân theo grammar, nhưng bộ kiểm tra kiểu cần hiểu kiểu của từng biểu thức và quy tắc của từng toán tử. Đây là trách nhiệm mà nhóm phát triển DSL bên ngoài phải thiết kế và triển khai.

### 4.2. Ví dụ: kiểm tra kiểu cho một DSL biểu thức

Giả sử một DSL bên ngoài cho phép viết:

~~~text
let quantity = 3
let unitPrice = 120
let total = quantity * unitPrice
~~~

Parser có thể tạo AST gồm các khai báo biến và phép nhân. Bộ kiểm tra kiểu xác định quantity và unitPrice là số nguyên, phép nhân hai số nguyên trả về số nguyên, nên biểu thức cuối cùng hợp lệ.

Nếu người viết đổi thành:

~~~text
let quantity = 3
let unitPrice = "one hundred twenty"
let total = quantity * unitPrice
~~~

Grammar vẫn có thể chấp nhận chuỗi này. Tuy nhiên, type checker cần xác định phép nhân giữa Int và String không được hỗ trợ, rồi báo lỗi tại biểu thức nhân.

Thông báo hữu ích có thể là:

~~~text
Type error at line 3:
  quantity * unitPrice
Expected: numeric operand
Found: String for unitPrice
~~~

Thông báo này đòi hỏi công cụ phải giữ vị trí nguồn trong AST và biết kiểu của từng biến. Parser đơn thuần không cung cấp đầy đủ thông tin đó.

### 4.3. Xây dựng hệ kiểu riêng

Một DSL bên ngoài có thể chọn hệ kiểu phù hợp với miền:

- **Kiểu nguyên thủy:** số nguyên, số thực, chuỗi, boolean, ngày giờ.
- **Kiểu miền:** đơn hàng, khách hàng, tiền, địa chỉ, sản phẩm.
- **Kiểu tổng hợp:** danh sách, tập hợp, bản ghi, tùy chọn, kết quả.
- **Kiểu liệt kê:** trạng thái đơn hàng, loại thanh toán, mức ưu tiên.
- **Kiểu hàm:** kiểu đầu vào và kiểu kết quả của một biểu thức hoặc hành động.
- **Kiểu tham số hóa:** ví dụ List<Order> hoặc Option<Customer>.

Hệ kiểu cần định nghĩa phép gán, chuyển kiểu, tương thích giữa các kiểu, suy luận kiểu và cách xử lý giá trị thiếu. Không nhất thiết phải hỗ trợ toàn bộ tính năng của một ngôn ngữ đa dụng; chỉ cần đủ cho tác vụ trong miền.

### 4.4. Kiểm tra kiểu trên AST

Một cách triển khai phổ biến là gắn kiểu vào mỗi nút AST sau khi phân tích. Ví dụ, AST cho phép cộng có thể gồm hai nút con. Bộ kiểm tra đệ quy xác định kiểu của từng nút con rồi tra quy tắc phép cộng.

Có thể mô tả quy tắc đơn giản:

~~~text
type(42) = Int
type("hello") = String
type(left + right) = Int
    if type(left) = Int and type(right) = Int
~~~

Nếu một điều kiện không thỏa, checker tạo lỗi kiểu và không cho biểu thức đi tiếp đến giai đoạn thực thi.

Trong DSL phức tạp hơn, type checker có thể cần môi trường kiểu (type environment), bảng ký hiệu (symbol table), phạm vi tên, kiểu tham số hóa và quy tắc suy luận. Một số DSL dùng type checker một lượt; DSL khác cần nhiều lượt để giải quyết tham chiếu hoặc phụ thuộc.

### 4.5. Kiểm tra theo schema và ngữ cảnh

DSL truy vấn hoặc cấu hình thường phụ thuộc vào schema bên ngoài. Ví dụ, biểu thức order.total chỉ hợp lệ nếu schema hiện tại có đối tượng order và trường total với kiểu đã biết.

Type checker cần được cung cấp thông tin schema hoặc mô hình miền. Nếu schema thay đổi, kết quả kiểm tra cũng có thể thay đổi. Vì vậy, cần xác định phiên bản schema, cách nạp metadata và thời điểm kiểm tra.

Một DSL truy vấn có thể kiểm tra:

- Tên bảng, đối tượng hoặc trường có tồn tại không.
- Kiểu của trường là gì.
- Phép so sánh có tương thích không.
- Hàm có nhận đúng số lượng và kiểu đối số không.
- Giá trị kết quả có phù hợp với ngữ cảnh sử dụng không.

Ví dụ, nếu order.createdAt có kiểu DateTime, so sánh nó với một chuỗi tùy ý cần bị từ chối hoặc yêu cầu chuyển đổi rõ ràng. Nếu hệ thống tự chuyển chuỗi thành ngày, quy tắc chuyển đổi và lỗi parse phải được định nghĩa.

### 4.6. Các mức an toàn kiểu mà DSL bên ngoài có thể cung cấp

DSL bên ngoài không bắt buộc phải là ngôn ngữ động. Nhóm có thể chọn một trong các chiến lược:

| Chiến lược | Hành vi |
|---|---|
| Không có kiểm tra kiểu riêng | Parser chỉ tạo cấu trúc; nhiều lỗi chỉ xuất hiện khi thực thi |
| Kiểm tra kiểu động | Kiểm tra kiểu khi đánh giá biểu thức |
| Kiểm tra kiểu tĩnh | Phân tích và từ chối biểu thức sai kiểu trước khi thực thi |
| Kiểm tra tĩnh kết hợp runtime | Kiểm tra phần biết trước; xác thực thêm dữ liệu và điều kiện thực tế khi chạy |
| Kiểu theo schema | Kiểm tra biểu thức dựa trên schema hoặc metadata của môi trường đích |

Ví dụ, một DSL quy tắc có thể kiểm tra kiểu của biểu thức ngay khi lưu quy tắc, nhưng vẫn phải kiểm tra dữ liệu đơn hàng thực tế khi áp dụng quy tắc.

### 4.7. Ưu điểm của an toàn kiểu trong DSL bên ngoài

- **Tự do thiết kế hệ kiểu:** ngôn ngữ có thể chọn khái niệm kiểu gần với miền và không bị giới hạn bởi ngôn ngữ chủ.
- **Cú pháp phù hợp người dùng:** có thể thiết kế từ khóa và cấu trúc dễ đọc với chuyên gia miền.
- **Thông báo lỗi theo miền:** công cụ có thể giải thích lỗi bằng thuật ngữ nghiệp vụ, vị trí nguồn và gợi ý sửa.
- **Phân tích độc lập môi trường:** cùng một DSL có thể được kiểm tra trên nhiều nền tảng nếu quy tắc kiểu được đặc tả nhất quán.
- **Có thể kiểm tra trước khi chạy:** công cụ có thể từ chối cấu hình hoặc quy tắc sai kiểu trước khi đưa vào vận hành.
- **Có thể hỗ trợ nhiều giao diện:** cùng một AST và mô hình kiểu có thể được dùng bởi trình soạn thảo văn bản, giao diện trực quan hoặc API.

### 4.8. Chi phí và rủi ro

**Phải tự xây dựng và duy trì type checker:** nhóm cần đặc tả quy tắc, xử lý lỗi, kiểm thử các trường hợp biên và giữ hành vi nhất quán qua các phiên bản.

**Parser không thay thế type checker:** một grammar chặt chẽ vẫn có thể chấp nhận biểu thức không hợp lệ về kiểu hoặc nghiệp vụ.

**Thông tin schema có thể lỗi thời:** một biểu thức hợp lệ với schema cũ có thể sai với schema mới. Công cụ cần phát hiện sai khác phiên bản hoặc xác minh lại trước khi thực thi.

**Khả năng mở rộng của hệ kiểu:** khi thêm generic, overload, suy luận kiểu, hàm bậc cao hoặc kiểu tùy chọn, độ phức tạp của checker tăng lên. Nếu ngôn ngữ phát triển thiếu kiểm soát, thông báo lỗi có thể khó hiểu và hiệu năng phân tích giảm.

**Khác biệt giữa kiểm tra tĩnh và dữ liệu thực tế:** checker chỉ có thể chứng minh những điều mà mô hình kiểu và thông tin đầu vào cho phép. Nó không thể biết trước mọi giá trị từ dịch vụ bên ngoài hoặc mọi điều kiện môi trường.

## 5. So sánh trực tiếp DSL nội bộ và DSL bên ngoài

| Tiêu chí | DSL nội bộ | DSL bên ngoài |
|---|---|---|
| Nơi định nghĩa cú pháp | Cú pháp của ngôn ngữ chủ và API DSL | Grammar riêng |
| Nơi kiểm tra kiểu | Chủ yếu qua compiler/type checker của ngôn ngữ chủ và kiểm tra bổ sung của thư viện | Type checker riêng của công cụ DSL |
| Chi phí ban đầu | Thường thấp hơn nếu ngôn ngữ chủ phù hợp | Cao hơn do cần parser, AST và checker |
| Khả năng kiểm tra tĩnh | Tận dụng hệ kiểu của ngôn ngữ chủ; phụ thuộc chất lượng API | Có thể xây dựng kiểm tra tĩnh riêng với mức độ tùy chọn |
| Mức tự do của hệ kiểu | Bị giới hạn hoặc định hình bởi ngôn ngữ chủ | Có thể thiết kế sát miền |
| Thông báo lỗi | Có thể là lỗi compiler mang tính kỹ thuật | Có thể tùy biến theo ngôn ngữ và nghiệp vụ |
| IDE và refactor | Thường tận dụng công cụ của ngôn ngữ chủ | Cần tích hợp language server hoặc plugin nếu muốn trải nghiệm tương đương |
| Dữ liệu ngoài | Vẫn cần parse và xác thực tại ranh giới | Parser và checker thường xử lý dữ liệu nguồn DSL; dữ liệu miền vẫn cần xác thực |
| Khả năng dùng cho chuyên gia không lập trình | Phụ thuộc mức quen thuộc với ngôn ngữ chủ | Có thể thiết kế cú pháp riêng dễ tiếp cận hơn |
| Khả năng triển khai đa nền tảng | Phụ thuộc runtime và hệ sinh thái ngôn ngữ chủ | Có thể độc lập hơn nếu có nhiều backend |
| Kiểm soát phiên bản | Gắn với API và phiên bản ngôn ngữ chủ | Nhóm quản lý grammar, hệ kiểu và runtime của DSL |
| Rủi ro chính | API quá tổng quát hoặc lạm dụng escape hatch | Checker thiếu chính xác, lỗi khó hiểu hoặc schema lỗi thời |

Không nên hiểu bảng này như quy tắc tuyệt đối. Một DSL nội bộ có thể xây dựng validator riêng và thông báo lỗi thân thiện; một DSL bên ngoài có thể chỉ kiểm tra kiểu động. Mức an toàn thực tế phụ thuộc vào cách triển khai, không chỉ phụ thuộc nhãn internal hay external.

## 6. Cùng một bài toán qua hai cách triển khai

Giả sử miền bán hàng có quy tắc: chỉ được áp dụng giảm giá theo phần trăm cho một đơn hàng khi phần trăm nằm trong khoảng từ 0 đến 100.

### 6.1. Biểu diễn bằng DSL nội bộ

Một API nhúng có thể định nghĩa các kiểu riêng:

~~~kotlin
@JvmInline
value class Percentage private constructor(val value: Int) {
    companion object {
        fun of(value: Int): Percentage {
            require(value in 0..100)
            return Percentage(value)
        }
    }
}

data class OrderId(val value: String)

fun applyDiscount(
    orderId: OrderId,
    percentage: Percentage
) {
    // Gửi yêu cầu áp dụng giảm giá.
}

val discount = Percentage.of(15)
applyDiscount(OrderId("ORD-100"), discount)
~~~

Kiểu Percentage không cho phép tạo giá trị thông qua constructor công khai; hàm tạo kiểm tra phạm vi. Hàm applyDiscount yêu cầu đúng OrderId và Percentage, do đó không nhận nhầm một chuỗi tùy ý hoặc một kiểu số chưa được xác thực.

Tuy nhiên, ví dụ này vẫn có thể cần kiểm tra thêm: đơn hàng có tồn tại không, đơn hàng có được phép giảm giá không, người gọi có quyền không và chương trình có thể kết nối đến dịch vụ hay không. Hệ kiểu giải quyết một phần hợp đồng, còn các điều kiện phụ thuộc trạng thái thực tế vẫn cần xử lý.

### 6.2. Biểu diễn bằng DSL bên ngoài

Một cú pháp bên ngoài có thể cho phép:

~~~text
discount order "ORD-100" by 15 percent
~~~

Parser xác nhận cấu trúc câu lệnh. Sau đó, bộ phân giải tên xác định order và kiểu của đối tượng; type checker xác nhận 15 percent có kiểu Percentage và toán hạng phù hợp; validator kiểm tra giá trị nằm trong phạm vi 0 đến 100. Cuối cùng, runtime tìm đơn hàng và xác minh quy tắc nghiệp vụ còn lại.

Nếu người viết nhập:

~~~text
discount order "ORD-100" by "fifteen" percent
~~~

parser có thể vẫn đọc được chuỗi, nhưng checker cần báo rằng giá trị phần trăm phải là số. Nếu nhập 150 percent, kiểu vẫn là Percentage về mặt cấu trúc, nhưng kiểm tra miền cần từ chối vì giá trị nằm ngoài phạm vi.

### 6.3. So sánh các bảo đảm

| Trường hợp | DSL nội bộ | DSL bên ngoài |
|---|---|---|
| Truyền chuỗi vào vị trí yêu cầu phần trăm | Compiler có thể từ chối nếu API dùng kiểu Percentage | Type checker riêng cần phát hiện |
| Giá trị phần trăm ngoài phạm vi | Constructor hoặc factory phải kiểm tra | Validator hoặc kiểu miền cần kiểm tra |
| Mã đơn hàng không hợp lệ | Cần parse/validate khi tạo OrderId hoặc khi truy cập dữ liệu | Cần kiểm tra cú pháp literal và xác thực ID |
| Đơn hàng không tồn tại | Runtime phải kiểm tra | Runtime phải kiểm tra |
| Đơn hàng đã giao nên không được giảm giá | Quy tắc miền/runtime phải kiểm tra | Quy tắc miền/runtime phải kiểm tra |

Hai cách triển khai có thể đạt mức bảo đảm tương đương nếu cùng định nghĩa kiểu, quy tắc và kiểm tra dữ liệu. Khác biệt nằm ở công cụ và nơi các quy tắc được biểu diễn.

## 7. Những nguyên tắc thiết kế để tăng an toàn kiểu

### 7.1. Mô hình hóa kiểu theo khái niệm miền

Tránh dùng một kiểu chung cho những giá trị có ý nghĩa khác nhau. Ví dụ, OrderId, CustomerId và ProductId nên là các kiểu riêng nếu việc tráo đổi chúng có thể gây lỗi.

Tương tự, có thể dùng kiểu Money thay cho Double, kiểu Percentage thay cho số thực bất kỳ, kiểu EmailAddress thay cho chuỗi chưa xác thực và kiểu trạng thái riêng cho các giai đoạn quy trình.

### 7.2. Ưu tiên biểu diễn chỉ các trạng thái hợp lệ

Nếu miền có một tập trạng thái hữu hạn, hãy dùng enum hoặc kiểu đại diện rõ. Nếu chỉ một số thao tác được phép ở từng trạng thái, cân nhắc typestate hoặc API tách theo trạng thái.

Đối với DSL bên ngoài, có thể định nghĩa kiểu liệt kê và quy tắc chuyển trạng thái trong type checker. Một biểu thức gọi hành động chỉ hợp lệ khi trạng thái nguồn phù hợp.

### 7.3. Giảm kiểu quá rộng và ép kiểu tùy tiện

Các kiểu như Any, Object, dynamic, chuỗi tự do hoặc bản đồ key-value không có schema làm mất thông tin mà checker cần. Nếu phải dùng chúng ở ranh giới hệ thống, hãy chuyển đổi sớm sang kiểu miền đã xác thực.

Không nên dùng ép kiểu để làm im lặng lỗi compiler mà không chứng minh được dữ liệu thực sự đúng kiểu.

### 7.4. Tách parse, type check và validate miền

Thiết kế pipeline rõ ràng giúp lỗi được báo đúng nguyên nhân:

~~~text
Nguồn DSL
   |
   v
Parser
   |
   v
AST
   |
   v
Phân giải tên và kiểu
   |
   v
Kiểm tra quy tắc miền
   |
   v
Kế hoạch thực thi / mã đích
   |
   v
Runtime validation và thực thi
~~~

Với DSL nội bộ, một phần pipeline được compiler của ngôn ngữ chủ đảm nhiệm. Nhưng parse dữ liệu, kiểm tra giá trị miền và thực thi vẫn có thể cần các lớp riêng.

### 7.5. Xác thực tại ranh giới dữ liệu

Dữ liệu từ tệp, người dùng, API, message queue hoặc cơ sở dữ liệu có thể sai định dạng hoặc vi phạm quy tắc. Không nên coi dữ liệu bên ngoài là hợp lệ chỉ vì sau khi parse nó được gán vào một kiểu rộng.

Một cách làm là dùng kiểu chưa xác thực ở ranh giới, sau đó chuyển sang kiểu đã xác thực chỉ khi tất cả điều kiện cần thiết đã đạt. Ví dụ, chuỗi đầu vào được parse thành OrderId; sau đó hệ thống có thể kiểm tra định dạng hoặc xác nhận mã có tồn tại tùy yêu cầu.

### 7.6. Đặc tả quy tắc kiểu bằng ví dụ

Với mỗi phép toán DSL, nên ghi:

- Kiểu đầu vào được chấp nhận.
- Kiểu kết quả.
- Quy tắc chuyển kiểu hoặc ép kiểu.
- Cách xử lý null hoặc giá trị thiếu.
- Điều kiện lỗi và thông báo tương ứng.
- Các trường hợp hợp lệ và không hợp lệ.

Ví dụ, phép so sánh Date với Date có thể hợp lệ; Date với String cần chuyển đổi rõ ràng; Money với Money chỉ được so sánh nếu đơn vị tiền tệ tương thích.

### 7.7. Làm cho lỗi có thể hành động

Một thông báo tốt nên nêu vị trí, biểu thức, kiểu mong đợi, kiểu thực tế và hướng sửa. Với DSL hướng đến chuyên gia nghiệp vụ, nên diễn đạt bằng từ vựng miền.

Ví dụ:

~~~text
Không thể so sánh Tổng tiền với Ngày tạo đơn.
Tổng tiền có kiểu Money; Ngày tạo đơn có kiểu DateTime.
Hãy chọn một trường tiền tệ hoặc so sánh ngày với một giá trị ngày.
~~~

Thông báo lỗi rõ giúp người dùng sửa đúng nguyên nhân và giảm nhu cầu hiểu chi tiết nội bộ của compiler.

## 8. Kiểm thử an toàn kiểu

### 8.1. Kiểm thử các biểu thức hợp lệ

Với mỗi kiểu và toán tử, cần có trường hợp chứng minh các tổ hợp hợp lệ được chấp nhận. Ví dụ:

- Int + Int trả về Int.
- Money + Money trả về Money nếu cùng đơn vị.
- Date < Date trả về Boolean.
- Trường tồn tại được truy cập trong đúng ngữ cảnh.

### 8.2. Kiểm thử các biểu thức sai kiểu

Tạo trường hợp âm để xác nhận checker từ chối các tổ hợp không hợp lệ:

- Int + String.
- Money * Customer.
- Truy cập trường không tồn tại.
- Gọi hàm với sai số lượng đối số.
- Truyền CustomerId vào tham số yêu cầu OrderId.
- So sánh giá trị có kiểu không tương thích.

Với DSL nội bộ, các trường hợp này có thể được kiểm tra bằng test biên dịch hoặc test xác nhận đoạn mã không biên dịch. Với DSL bên ngoài, kiểm thử parser và type checker cần xác nhận cả loại lỗi lẫn vị trí nguồn.

### 8.3. Kiểm thử quy tắc miền và dữ liệu runtime

Kiểm tra kiểu không thay thế kiểm thử nghiệp vụ. Cần thử:

- Giá trị biên như 0, số âm, giới hạn lớn nhất.
- Giá trị thiếu hoặc null.
- Đơn vị không tương thích.
- Trạng thái không cho phép thao tác.
- Dữ liệu schema thay đổi.
- Tài nguyên không tồn tại hoặc không còn truy cập được.
- Lỗi từ dịch vụ bên ngoài.

### 8.4. Kiểm thử tính nhất quán giữa phiên bản

Khi thay đổi hệ kiểu hoặc schema, hãy kiểm tra các DSL source cũ. Nếu một biểu thức trước đây hợp lệ nay bị từ chối, cần xác định đó là thay đổi có chủ đích hay lỗi tương thích.

Đối với DSL nội bộ, thay đổi chữ ký API có thể làm mã người dùng không biên dịch. Đối với DSL bên ngoài, thay đổi grammar hoặc type checker có thể làm tệp cấu hình cũ không còn hợp lệ. Cần ghi rõ quy tắc chuyển đổi và phiên bản áp dụng.

## 9. Khi nào nên chọn DSL nội bộ hoặc DSL bên ngoài?

### 9.1. DSL nội bộ thường phù hợp khi

- Người viết DSL là lập trình viên quen với ngôn ngữ chủ.
- Hệ sinh thái hiện có cung cấp hệ kiểu và công cụ phát triển tốt.
- Tác vụ miền có thể diễn đạt rõ bằng API, hàm hoặc builder.
- Việc tái sử dụng kiểu, thư viện và compiler quan trọng.
- Nhóm muốn giảm chi phí xây dựng parser và công cụ riêng.

Nếu cần mức an toàn cao, hãy thiết kế API với kiểu miền, generic, sealed type hoặc typestate; tránh API nhận mọi giá trị dưới dạng kiểu chung.

### 9.2. DSL bên ngoài thường phù hợp khi

- Người dùng cần cú pháp riêng, dễ đọc theo nghiệp vụ.
- DSL phải được viết hoặc chỉnh sửa bởi người không quen ngôn ngữ lập trình chủ.
- Cú pháp cần ổn định và độc lập với ngôn ngữ triển khai.
- Cần hỗ trợ nhiều runtime hoặc nhiều backend.
- Ngôn ngữ cần các cấu trúc không thể diễn đạt thuận tiện bằng cú pháp của ngôn ngữ chủ.

Nếu cần an toàn kiểu, hãy coi type checker là thành phần cốt lõi của công cụ DSL. Đặc tả hệ kiểu, schema, kiểm tra ngữ nghĩa, thông báo lỗi và tương thích phiên bản ngay từ đầu.

### 9.3. Kết hợp hai cách tiếp cận

Một hệ thống có thể dùng DSL bên ngoài để người dùng mô tả quy tắc, sau đó phân tích thành AST hoặc mô hình có kiểu trong một ngôn ngữ đa dụng. Phần thực thi có thể được xây dựng bằng Kotlin, Java, C# hoặc ngôn ngữ khác.

Ngược lại, một DSL nội bộ có thể đọc cấu hình bên ngoài, parse thành dữ liệu rồi chuyển thành các kiểu miền đã xác thực. Đây là cách thường gặp khi muốn có cú pháp cấu hình thuận tiện nhưng vẫn giữ API thực thi có kiểu.

Ranh giới quan trọng là không để dữ liệu chưa xác thực đi sâu vào phần xử lý chỉ vì nó đã được parse thành một cấu trúc tổng quát.

## 10. Quy trình ra quyết định

Khi lựa chọn cách triển khai, nhóm có thể đi qua các câu hỏi sau:

1. Ai là người viết và bảo trì DSL: lập trình viên hay chuyên gia miền?
2. Ngôn ngữ chủ có hệ kiểu đủ biểu đạt các khái niệm của miền không?
3. Người dùng có cần cú pháp riêng hoặc cú pháp gần ngôn ngữ nghiệp vụ không?
4. Lỗi nào cần phát hiện trước khi chạy và lỗi nào phụ thuộc dữ liệu thực tế?
5. Schema và metadata có sẵn tại thời điểm kiểm tra không?
6. Mức độ nghiêm ngặt của kiểu cần thiết đến đâu?
7. Có cần IDE, tự hoàn thành, refactor và thông báo lỗi theo miền không?
8. Ai sẽ xây dựng và bảo trì parser, type checker hoặc API DSL?
9. DSL có cần chạy trên nhiều nền tảng hoặc phiên bản không?
10. Chi phí duy trì hệ kiểu có tương xứng với lợi ích giảm lỗi không?

Có thể ghi lại quyết định bằng một bảng ngắn:

| Yếu tố | Lựa chọn hoặc yêu cầu |
|---|---|
| Người dùng chính | Lập trình viên / chuyên gia miền / cả hai |
| Cách triển khai | Nội bộ / bên ngoài / kết hợp |
| Mức kiểm tra | Tĩnh / động / tĩnh kết hợp runtime |
| Kiểu miền | Nguyên thủy / kiểu riêng / kiểu tham số hóa |
| Schema | Cố định / theo phiên bản / tải động |
| Thời điểm xác thực | Khi biên dịch, khi lưu, khi triển khai, khi chạy |
| Thông báo lỗi | Kỹ thuật / theo miền / kết hợp |
| Tương thích | Chính sách phiên bản và di chuyển |

## 11. Những hiểu lầm thường gặp

### “DSL nội bộ luôn an toàn kiểu vì dùng ngôn ngữ có kiểu tĩnh”

Không chính xác. Nếu API dùng Any, Object, dynamic, ép kiểu không an toàn hoặc chỉ kiểm tra dữ liệu lúc chạy, nhiều lỗi vẫn có thể lọt qua compiler. An toàn kiểu phụ thuộc vào cách thiết kế API và các ranh giới dữ liệu.

### “DSL bên ngoài không thể kiểm tra kiểu tĩnh”

Không chính xác. DSL bên ngoài có thể có grammar, AST, hệ kiểu và type checker riêng. Nhiều công cụ có thể từ chối biểu thức sai kiểu trước khi thực thi.

### “Parser chấp nhận nghĩa là biểu thức hợp lệ”

Không chính xác. Parser chủ yếu kiểm tra cấu trúc. Tên có tồn tại, kiểu có tương thích và quy tắc miền có hợp lệ hay không là các bước phân tích khác.

### “Nếu compiler không báo lỗi thì nghiệp vụ chắc chắn đúng”

Không chính xác. Compiler kiểm tra những điều được mã hóa trong hệ kiểu và API. Nó không tự biết một đơn hàng có thực sự tồn tại, người dùng có quyền thao tác hay chính sách hiện tại có cho phép giao dịch hay không.

### “Kiểu càng phức tạp thì càng an toàn”

Không nhất thiết. Hệ kiểu quá phức tạp có thể khó học, khó bảo trì và tạo thông báo lỗi khó hiểu. Mục tiêu là mã hóa những khác biệt có ý nghĩa và ngăn các thao tác sai phổ biến, với chi phí hợp lý.

## 12. Bài tập tự kiểm tra

### Bài 1: Phân biệt các lớp kiểm tra

Một DSL có câu lệnh:

~~~text
set order.total = "one hundred"
~~~

Hãy giải thích parser, type checker và validator nghiệp vụ sẽ kiểm tra những gì. Nêu trường hợp câu lệnh đúng cú pháp nhưng sai kiểu.

### Bài 2: Thiết kế kiểu miền

Một hệ thống có CustomerId, OrderId và ProductId, nhưng hiện đều dùng chuỗi. Hãy đề xuất kiểu riêng cho ba khái niệm và mô tả một lỗi mà compiler có thể ngăn khi API yêu cầu đúng kiểu.

### Bài 3: So sánh hai cách triển khai

Hãy biểu diễn một điều kiện lọc đơn hàng theo hai cách:

- Một API DSL nhúng trong Kotlin, Java hoặc C#.
- Một cú pháp DSL bên ngoài do bạn tự thiết kế.

Chỉ ra ở đâu diễn ra kiểm tra kiểu, ai chịu trách nhiệm triển khai checker và thông báo lỗi có thể khác nhau thế nào.

### Bài 4: Tìm giới hạn của kiểm tra tĩnh

Một DSL chỉ cho phép hủy đơn hàng có trạng thái PENDING. Biểu thức được kiểm tra kiểu hợp lệ, nhưng khi chạy đơn hàng đã chuyển sang SHIPPED. Giải thích vì sao lỗi này không thể được loại bỏ chỉ bằng kiểm tra kiểu tĩnh và đề xuất bước xác thực cần thiết.

### Bài 5: Lập chiến lược an toàn kiểu

Một nhóm muốn cho chuyên viên nghiệp vụ viết quy tắc giá bằng tệp văn bản. Hãy đề xuất pipeline từ parser đến runtime, các kiểu miền cần có, cách kiểm tra giá trị phần trăm và cách báo lỗi. Nêu thêm cách quản lý phiên bản khi tên trường trong schema thay đổi.

## Kết luận

An toàn kiểu là khả năng ngăn các thao tác không hợp lệ đối với kiểu dữ liệu. DSL nội bộ có thể tận dụng compiler và hệ kiểu của ngôn ngữ chủ, đặc biệt khi API dùng kiểu miền, generic và kiểu trạng thái một cách có chủ đích. DSL bên ngoài có thể xây dựng hệ kiểu và type checker riêng để kiểm tra AST, schema và quy tắc của miền trước khi thực thi. Cả hai cách đều cần xác thực dữ liệu đầu vào và điều kiện nghiệp vụ phụ thuộc runtime. Vì vậy, mức an toàn thực tế được quyết định bởi các quy tắc được đặc tả, cách triển khai checker, chất lượng thông báo lỗi và quy trình kiểm thử, chứ không chỉ bởi việc DSL là nội bộ hay bên ngoài.
