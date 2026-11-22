# Tương thích và chuyển kiểu

Trong một **Domain-Specific Language (DSL)**, hệ kiểu quy định những loại giá trị mà chương trình có thể sử dụng, những phép toán được phép thực hiện và cách dữ liệu được truyền giữa các thành phần. Hai khái niệm quan trọng của hệ kiểu là **tương thích kiểu (type compatibility)** và **chuyển kiểu (type conversion)**.

Tương thích kiểu xác định một giá trị hoặc biểu thức thuộc kiểu nào có thể được sử dụng tại một vị trí đang yêu cầu kiểu khác hay không. Chuyển kiểu là quá trình biến một giá trị từ kiểu nguồn sang kiểu đích theo một quy tắc được định nghĩa. Hai khái niệm có liên quan nhưng không đồng nhất: một kiểu có thể tương thích với kiểu khác nhờ quan hệ subtype mà không cần biến đổi giá trị; trong trường hợp khác, hệ thống phải thực hiện một phép chuyển đổi cụ thể.

Thiết kế rõ các quy tắc này giúp DSL phát hiện lỗi trước khi chạy, hạn chế mất dữ liệu, bảo đảm hành vi nhất quán giữa interpreter và compiler, đồng thời giúp người viết hiểu được giá trị nào có thể truyền vào biến, tham số, thuộc tính hoặc phép toán.

## 1. Kiểu dữ liệu và ngữ cảnh sử dụng

Một kiểu dữ liệu mô tả tập giá trị mà một biểu thức có thể tạo ra cùng những phép toán hợp lệ trên các giá trị đó. Ví dụ:

- Integer biểu diễn số nguyên.
- Decimal hoặc Real biểu diễn số có phần thập phân.
- Boolean biểu diễn đúng hoặc sai.
- String biểu diễn văn bản.
- Date và Duration biểu diễn ngày tháng và khoảng thời gian.
- List<T> biểu diễn danh sách các giá trị có kiểu phần tử T.
- Một kiểu miền như Customer hoặc Order biểu diễn đối tượng nghiệp vụ.

Một biểu thức được kiểm tra kiểu trong một ngữ cảnh. Chẳng hạn, biến có khai báo kiểu, tham số hàm có kiểu đầu vào, hàm có kiểu trả về và toán tử có yêu cầu kiểu toán hạng.

Ví dụ DSL:

~~~text
let quantity: Integer = 3
let unitPrice: Decimal = 12500.50
let total: Decimal = unitPrice * quantity
~~~

Trong ví dụ, phép gán cho quantity yêu cầu giá trị Integer; phép nhân cần quy tắc xác định cách kết hợp Integer và Decimal; kết quả được gán cho total có kiểu Decimal. Nếu DSL không định nghĩa phép nhân giữa hai kiểu này, chương trình phải bị từ chối hoặc người viết phải chuyển kiểu tường minh.

Một phán đoán kiểu thường được viết:

\[
\Gamma \vdash e : T
\]

Ký hiệu này có nghĩa: trong môi trường kiểu \(\Gamma\), biểu thức \(e\) có kiểu \(T\). Môi trường kiểu lưu thông tin về kiểu của các biến, hàm, tài nguyên và tên định danh đang có hiệu lực.

## 2. Tương thích kiểu là gì?

Hai kiểu được xem là tương thích trong một ngữ cảnh nếu giá trị thuộc kiểu nguồn có thể được sử dụng an toàn tại vị trí yêu cầu kiểu đích theo quy tắc của ngôn ngữ. Từ “an toàn” cần được hiểu theo hợp đồng của DSL: không làm sai kiểu dữ liệu, không gây mất thông tin ngoài quy định và không vi phạm những bất biến mà kiểu đích yêu cầu.

Ví dụ, nếu Integer là subtype của Number, một giá trị Integer có thể được dùng ở nơi cần Number. Đây là quan hệ tương thích dựa trên hệ thống subtype. Giá trị không nhất thiết phải được thay đổi thành một object khác.

Ngược lại, một chuỗi như "42" không tự động là số nguyên. Nếu DSL cho phép chuyển từ String sang Integer, nó cần quy định phép chuyển đó, chẳng hạn parse chuỗi theo định dạng số. Việc chuỗi có thể chứa số không đồng nghĩa String và Integer tương thích trực tiếp.

### 2.1. Tương thích phụ thuộc ngữ cảnh

Một kiểu có thể được chấp nhận trong phép gán nhưng không được chấp nhận trong một phép toán khác. Ví dụ, Integer có thể được gán vào biến Number, nhưng điều đó không có nghĩa mọi phép toán giữa Number và String đều hợp lệ.

Các ngữ cảnh thường cần quy tắc tương thích riêng:

- Gán giá trị cho biến hoặc thuộc tính.
- Truyền đối số vào tham số hàm.
- Trả kết quả từ hàm.
- Kết hợp toán hạng của toán tử.
- Thêm phần tử vào collection.
- Gán một đối tượng vào biến có kiểu interface hoặc kiểu cha.
- So sánh hai giá trị.

Vì vậy, tài liệu của DSL cần mô tả kiểu nguồn và kiểu đích được chấp nhận trong từng ngữ cảnh, thay vì chỉ nói chung rằng hai kiểu “tương thích”.

## 3. Bằng kiểu, subtype và khả năng gán

Ba khái niệm thường xuất hiện khi xét tương thích là type equivalence, subtyping và assignability.

### 3.1. Bằng kiểu (type equivalence)

Hai kiểu bằng nhau khi hệ thống xem chúng là cùng một kiểu theo quy tắc định danh hoặc cấu trúc của ngôn ngữ. Có hai cách định nghĩa phổ biến:

- **Bằng danh định (nominal equivalence)**: hai kiểu được xem là cùng kiểu dựa trên tên và vị trí khai báo theo quy tắc của ngôn ngữ.
- **Bằng cấu trúc (structural equivalence)**: hai kiểu được xem là cùng kiểu nếu cấu trúc và kiểu thành phần của chúng tương ứng theo quy tắc.

Ví dụ về kiểu cấu trúc:

~~~text
type Point2D = {
    x: Decimal
    y: Decimal
}

type Coordinate = {
    x: Decimal
    y: Decimal
}
~~~

Nếu DSL dùng structural typing, Point2D và Coordinate có thể tương thích vì cùng có hai trường x và y với kiểu Decimal. Nếu DSL dùng nominal typing, chúng vẫn có thể là hai kiểu riêng vì được khai báo dưới hai tên khác nhau.

Nominal typing giúp phân biệt các khái niệm nghiệp vụ có cấu trúc giống nhau nhưng ý nghĩa khác nhau, ví dụ CustomerId và OrderId đều có thể được lưu bằng String nhưng không nên truyền nhầm cho nhau. Structural typing linh hoạt khi làm việc với record, object literal hoặc interface theo hình dạng.

### 3.2. Quan hệ subtype

Ký hiệu:

\[
S <: T
\]

được đọc là S là subtype của T. Giá trị có kiểu S có thể được dùng ở vị trí yêu cầu T nếu quan hệ subtype bảo đảm các hành vi mà T yêu cầu.

Ví dụ:

~~~text
type Animal
type Dog extends Animal

let pet: Animal = Dog()
~~~

Dog là subtype của Animal nên một Dog có thể được dùng như Animal. Đây là phép thay thế theo quan hệ kiểu, thường không cần thay đổi bản chất đối tượng.

Một quan hệ subtype tốt cần tuân theo nguyên tắc thay thế: nơi chương trình yêu cầu giá trị của kiểu cha, việc cung cấp giá trị của kiểu con không được phá vỡ những kỳ vọng hợp lệ của kiểu cha. Nếu kiểu con làm yếu các điều kiện đầu vào hoặc làm sai hợp đồng kết quả, quan hệ subtype có thể không an toàn.

### 3.3. Khả năng gán (assignability)

Assignability là quy tắc xác định một biểu thức có thể được gán vào biến hoặc thuộc tính có kiểu đích hay không. Quy tắc này có thể bao gồm:

- Kiểu nguồn và kiểu đích bằng nhau.
- Kiểu nguồn là subtype của kiểu đích.
- Có phép chuyển kiểu ngầm định được cho phép.
- Kiểu nguồn là một kiểu literal có thể được suy ra hoặc thu hẹp an toàn theo ngữ cảnh.

Ví dụ, DSL có thể cho phép:

~~~text
let count: Number = 12
~~~

vì Integer là subtype của Number hoặc được chuyển ngầm định theo quy tắc numeric widening. Nhưng DSL có thể từ chối:

~~~text
let count: Integer = 12.75
~~~

vì chuyển Decimal sang Integer có thể làm mất phần thập phân. Người viết cần chỉ định rõ cách làm tròn hoặc dùng một phép chuyển có kiểm tra.

## 4. Chuyển kiểu là gì?

Chuyển kiểu là phép biến đổi một giá trị có kiểu nguồn S thành giá trị có kiểu đích T. Có thể biểu diễn một phép chuyển như hàm:

\[
convert_{S \rightarrow T}: S \rightarrow T
\]

Nếu mọi giá trị nguồn đều có thể chuyển thành giá trị đích theo một quy tắc xác định, phép chuyển có thể là toàn phần (total). Nếu một số giá trị không chuyển được, phép chuyển là bộ phận (partial) và cần biểu diễn khả năng thất bại.

Ví dụ:

- Integer sang Decimal: thường có thể chuyển toàn phần nếu Decimal biểu diễn chính xác miền Integer được hỗ trợ.
- Decimal sang Integer: có thể mất phần thập phân hoặc vượt giới hạn; cần quy tắc làm tròn và xử lý overflow.
- String sang Integer: chỉ thành công khi chuỗi có định dạng số nguyên hợp lệ.
- Integer sang Boolean: không nên tự suy đoán rằng 0 là false và số khác 0 là true nếu DSL chưa quy định như vậy.

Chuyển kiểu có thể xảy ra tự động hoặc do người viết yêu cầu tường minh.

## 5. Chuyển kiểu ngầm định và tường minh

### 5.1. Chuyển kiểu ngầm định (implicit conversion)

Chuyển kiểu ngầm định, còn gọi là coercion, được hệ thống tự thực hiện khi một biểu thức được dùng trong ngữ cảnh yêu cầu kiểu khác và quy tắc của DSL cho phép.

Ví dụ:

~~~text
let small: Integer = 12
let amount: Decimal = small
~~~

Nếu DSL định nghĩa Integer có thể mở rộng sang Decimal, phép gán thứ hai không cần cú pháp chuyển đổi riêng.

Ưu điểm:

- Giảm cú pháp lặp lại.
- Giúp biểu thức ngắn và tự nhiên.
- Hữu ích cho các chuyển đổi an toàn, phổ biến như mở rộng số nguyên sang kiểu số rộng hơn.

Rủi ro:

- Người đọc có thể không nhận ra hệ thống đang đổi kiểu.
- Nhiều đường chuyển đổi có thể làm overload resolution trở nên mơ hồ.
- Chuyển đổi có thể làm mất độ chính xác hoặc thay đổi giá trị nếu quy tắc không được giới hạn.
- Hai implementation có thể xử lý khác nhau nếu quy tắc coercion không được đặc tả chính xác.

Một DSL nên giới hạn implicit conversion vào những trường hợp có hành vi dễ dự đoán và được xem là an toàn theo hợp đồng của kiểu.

### 5.2. Chuyển kiểu tường minh (explicit conversion)

Chuyển kiểu tường minh yêu cầu người viết chỉ ra ý định chuyển đổi trong source:

~~~text
let raw: Decimal = 19.8
let rounded: Integer = toInteger(raw)
~~~

Hoặc:

~~~text
let rounded: Integer = raw as Integer
~~~

Cú pháp cụ thể phụ thuộc DSL. Một số ngôn ngữ dùng cast, một số dùng hàm chuyển đổi có tên như toInteger, parseDecimal hoặc formatDate.

Chuyển tường minh hữu ích khi phép chuyển có thể mất thông tin, có thể thất bại hoặc mang ý nghĩa nghiệp vụ cần được nhìn thấy trong source. Tên hàm như floor, ceil, round hoặc truncate cũng diễn đạt rõ hơn một cast chung chung khi chuyển Decimal sang Integer.

### 5.3. So sánh

| Tiêu chí | Implicit conversion | Explicit conversion |
|---|---|---|
| Ai yêu cầu chuyển đổi? | Hệ thống theo quy tắc | Người viết DSL |
| Cú pháp | Thường không có dấu hiệu riêng | Có cast hoặc hàm chuyển đổi |
| Độ ngắn gọn | Cao | Thấp hơn |
| Khả năng nhận biết | Có thể khó thấy | Thể hiện ý định rõ |
| Trường hợp phù hợp | Chuyển đổi an toàn, không mơ hồ | Chuyển đổi có rủi ro hoặc cần lựa chọn chính sách |

## 6. Chuyển kiểu mở rộng và thu hẹp

Trong các kiểu số, hai nhóm chuyển đổi thường gặp là widening và narrowing.

### 6.1. Mở rộng kiểu (widening conversion)

Widening chuyển giá trị sang kiểu có miền biểu diễn rộng hơn hoặc có khả năng chứa giá trị nguồn theo quy tắc của hệ thống.

Ví dụ minh họa:

~~~text
Integer -> Long
Integer -> Decimal
Float -> Double
~~~

Widening thường được cho phép ngầm định vì có thể bảo toàn giá trị trong miền đã xác định. Tuy nhiên, “kiểu rộng hơn” không phải lúc nào cũng đồng nghĩa mọi giá trị đều được biểu diễn chính xác. Ví dụ, một kiểu số thực có thể không biểu diễn chính xác mọi số nguyên rất lớn. Vì vậy, DSL cần định nghĩa dựa trên miền giá trị thực tế của kiểu, không chỉ dựa vào tên kiểu.

### 6.2. Thu hẹp kiểu (narrowing conversion)

Narrowing chuyển sang kiểu có miền biểu diễn nhỏ hơn hoặc ít khả năng hơn. Phép chuyển có thể làm mất phần thập phân, tràn miền hoặc không biểu diễn được giá trị nguồn.

Ví dụ:

~~~text
Decimal -> Integer
Long -> Short
Double -> Float
~~~

Nếu DSL cho phép narrowing, cần quy định:

- Có làm tròn, cắt bỏ phần thập phân hay từ chối không nguyên?
- Khi giá trị vượt giới hạn, có báo lỗi, bão hòa ở giá trị cực đại hay wrap-around?
- Có kiểm tra ở compile time khi giá trị đã biết hay chỉ kiểm tra lúc chạy?
- Lỗi chuyển kiểu được báo ở vị trí source nào?

Không nên để hành vi overflow phụ thuộc vào nền tảng hoặc thư viện số học mà người dùng DSL không biết.

## 7. Chuyển đổi số và promotion trong biểu thức

Khi một toán tử nhận hai toán hạng có kiểu khác nhau, hệ thống cần xác định kiểu kết quả và cách xử lý từng toán hạng. Quy tắc này thường được gọi là numeric promotion.

Ví dụ:

~~~text
let quantity: Integer = 3
let unitPrice: Decimal = 12.50
let total = quantity * unitPrice
~~~

DSL có thể quy định Integer được mở rộng sang Decimal trước phép nhân:

\[
3 \times 12.50 \Rightarrow 3.0 \times 12.50 = 37.50
\]

Kết quả có kiểu Decimal. Quy tắc này cần nhất quán với các phép cộng, trừ, chia và so sánh.

Một bảng promotion đơn giản có thể là:

| Kiểu trái | Kiểu phải | Kiểu kết quả | Quy tắc |
|---|---|---|---|
| Integer | Integer | Integer | Tính số nguyên |
| Integer | Decimal | Decimal | Mở rộng Integer sang Decimal |
| Decimal | Integer | Decimal | Mở rộng Integer sang Decimal |
| Decimal | Decimal | Decimal | Tính Decimal |
| String | Integer | Không hợp lệ | Không có phép cộng số học giữa hai kiểu |

Bảng chỉ là ví dụ. DSL thực tế cần quy định riêng cho phép chia, modulo, overflow, độ chính xác và kiểu literal.

### 7.1. Chia số nguyên và số thập phân

Hai biểu thức sau có thể có kết quả khác nhau:

~~~text
let a = 5 / 2
let b = 5.0 / 2
~~~

Nếu phép chia Integer trả về Integer theo phép chia nguyên, a có thể bằng 2. Nếu numeric promotion chuyển toán hạng sang Decimal khi một bên là Decimal, b có thể bằng 2.5.

Ngôn ngữ phải quy định rõ:

- Kiểu kết quả của phép chia.
- Cách làm tròn hoặc cắt phần dư.
- Hành vi khi chia cho 0.
- Kiểu kết quả khi một hoặc cả hai toán hạng là Decimal.

### 7.2. Literal và kiểu theo ngữ cảnh

Literal số đôi khi có thể được suy ra theo kiểu đích. Ví dụ, literal 1 có thể được chấp nhận trong ngữ cảnh yêu cầu Byte nếu giá trị nằm trong miền Byte. Nhưng biến Integer đã được khai báo không nhất thiết được thu hẹp tự động sang Byte.

~~~text
let small: Byte = 1
let count: Integer = 300
let another: Byte = count
~~~

DSL có thể chấp nhận dòng đầu vì literal 1 được kiểm tra trong miền Byte, nhưng từ chối dòng cuối vì count là một giá trị Integer tổng quát và có thể vượt giới hạn Byte. Quy tắc này cần được định nghĩa rõ để tránh phụ thuộc vào suy đoán của compiler.

## 8. Chuyển đổi giữa chuỗi và kiểu dữ liệu khác

Chuyển đổi giữa String và kiểu dữ liệu khác thường không giống numeric widening. Nó thường là thao tác phân tích hoặc định dạng văn bản.

### 8.1. Parse String thành giá trị

Ví dụ:

~~~text
let count: Integer = parseInteger("42")
let startedAt: Date = parseDate("2026-11-15")
let timeout: Duration = parseDuration("30s")
~~~

Các phép parse có thể thất bại nếu chuỗi sai định dạng, vượt miền giá trị hoặc không hợp lệ theo locale. Vì vậy, kết quả nên được biểu diễn như một giá trị có khả năng lỗi, chẳng hạn Result<Integer, ParseError> hoặc Option<Integer> tùy chính sách.

Một DSL có thể dùng cú pháp kiểm tra:

~~~text
let parsed = tryParseInteger(input)
if parsed.isSuccess {
    use parsed.value
} else {
    report parsed.error
}
~~~

### 8.2. Format giá trị thành String

Chuyển giá trị thành chuỗi cũng cần quy tắc rõ. Ví dụ, format ngày theo ISO 8601 hay theo locale; format Decimal có bao nhiêu chữ số thập phân; Boolean dùng "true"/"false" hay nhãn khác.

Không nên dùng một phép chuyển String ngầm định cho mọi kiểu nếu kết quả phụ thuộc locale, múi giờ hoặc định dạng hiển thị. Đặc biệt, chuỗi hiển thị không nhất thiết là định dạng có thể parse lại chính xác.

### 8.3. Parse khác với cast

Cast thường dựa trên quan hệ kiểu hoặc biểu diễn đã biết giữa các kiểu. Parse đọc nội dung văn bản và tạo ra một giá trị mới theo grammar của kiểu đích.

Ví dụ:

- Integer sang Number có thể là widening.
- Number sang Integer có thể là narrowing cast.
- String "42" sang Integer là parse.
- Integer 42 sang String là format.

Việc phân biệt này giúp API đặt tên đúng và giúp người dùng hiểu loại lỗi có thể xảy ra.

## 9. Chuyển kiểu tham chiếu và subtype

Với kiểu object, interface hoặc kiểu miền, chuyển kiểu có thể là upcast hoặc downcast.

### 9.1. Upcast

Upcast chuyển một tham chiếu từ kiểu cụ thể sang kiểu cha hoặc interface mà nó triển khai:

~~~text
type Animal
type Dog extends Animal

let dog: Dog = Dog()
let animal: Animal = dog
~~~

Upcast thường an toàn vì mọi Dog phải đáp ứng hợp đồng của Animal. Thông thường không cần tạo object mới; biến animal chỉ nhìn cùng object dưới kiểu trừu tượng hơn.

### 9.2. Downcast

Downcast chuyển tham chiếu từ kiểu cha sang kiểu con:

~~~text
let animal: Animal = loadAnimal()
let dog: Dog = animal as Dog
~~~

Phép chuyển này chỉ hợp lệ nếu object thực tế là Dog. Nếu không, nó có thể thất bại lúc chạy. DSL nên cung cấp cách kiểm tra an toàn:

~~~text
if animal is Dog {
    let dog: Dog = animal as Dog
    dog.fetch()
}
~~~

Hoặc dùng pattern matching để kiểm tra và ràng buộc biến trong cùng một thao tác:

~~~text
match animal {
    Dog dog => dog.fetch()
    Cat cat => cat.purr()
    _ => log("Unknown animal")
}
~~~

Nếu DSL hỗ trợ downcast không kiểm tra, cần chỉ rõ lỗi runtime có thể xảy ra. Với hệ thống yêu cầu an toàn kiểu cao, nên ưu tiên cast có kiểm tra hoặc pattern matching.

## 10. Kiểu nullable, optional và chuyển kiểu

Một giá trị có thể không tồn tại. Hệ kiểu cần biểu diễn khả năng đó thay vì giả định mọi biến luôn chứa một giá trị thông thường.

Ví dụ, kiểu String? có thể biểu thị một String hoặc null. Kiểu Option<String> có thể biểu diễn rõ hai trường hợp Some(value) và None.

~~~text
let nickname: String? = findNickname(userId)
~~~

Nếu một vị trí yêu cầu String không nullable, không nên tự động gán String? vào đó mà không kiểm tra:

~~~text
let displayName: String = nickname
~~~

Phép gán trên có thể bị từ chối vì nickname có thể là null. Người viết cần xử lý:

~~~text
let displayName: String = nickname ?? "Guest"
~~~

Hoặc:

~~~text
if nickname != null {
    show(nickname)
}
~~~

Tương thích giữa nullable và non-nullable thường có hướng:

- Non-null String có thể được dùng ở nơi yêu cầu String?.
- String? không thể tự động được dùng ở nơi yêu cầu String.

Quy tắc này ngăn lỗi truy cập null và buộc người viết xử lý trường hợp thiếu dữ liệu. Nếu DSL dùng Option thay vì null, cần quy định cách unwrap, map, default và propagate lỗi.

## 11. Tương thích kiểu của collection và generic

Collection có tham số kiểu, chẳng hạn List<Dog> hoặc List<Animal>. Câu hỏi quan trọng là List<Dog> có thể được dùng như List<Animal> hay không.

Nếu cho phép covariance một cách không kiểm soát, chương trình có thể thêm một Cat vào danh sách vốn chỉ chứa Dog thông qua tham chiếu List<Animal>, làm sai bất biến của danh sách ban đầu.

Ví dụ:

~~~text
let dogs: List<Dog> = [Dog()]
let animals: List<Animal> = dogs
animals.add(Cat())
~~~

Nếu phép gán được chấp nhận và danh sách có thể sửa, dogs có thể chứa Cat dù kiểu của nó hứa rằng mọi phần tử là Dog. Đây là lý do nhiều hệ kiểu giữ List<T> là invariant (bất biến tham số kiểu).

### 11.1. Invariance

List<S> chỉ tương thích với List<T> khi S và T tương đương theo quy tắc của generic. Đây là lựa chọn an toàn cho collection mutable khi cùng một kiểu được dùng để đọc và ghi.

### 11.2. Covariance

Một kiểu generic là covariant nếu khi S <: T thì G<S> <: G<T>. Covariance phù hợp với cấu trúc chỉ cung cấp giá trị để đọc. Ví dụ, một nguồn chỉ đọc Dog cũng có thể được dùng như nguồn đọc Animal.

### 11.3. Contravariance

Một kiểu generic là contravariant nếu quan hệ subtype đảo chiều: khi S <: T thì G<T> <: G<S>. Điều này thường phù hợp với consumer chỉ nhận giá trị đầu vào. Một hàm có thể xử lý mọi Animal thì cũng có thể được dùng ở nơi cần xử lý Dog.

| Variance | Quan hệ khi S <: T | Trường hợp thường gặp |
|---|---|---|
| Covariant | G<S> <: G<T> | Nguồn chỉ đọc, producer |
| Contravariant | G<T> <: G<S> | Consumer chỉ nhận đầu vào |
| Invariant | Không suy ra quan hệ | Collection có cả đọc và ghi |

Một số ngôn ngữ cho phép khai báo variance ngay trên tham số kiểu; một số ngôn ngữ suy ra từ cách tham số được sử dụng. DSL có generic cần quy định rõ để compiler và người dùng dự đoán được khả năng gán.

## 12. Tương thích kiểu hàm

Kiểu hàm có thể được biểu diễn như:

\[
Function<A, B>
\]

nghĩa là hàm nhận A và trả về B. Khi so sánh hai kiểu hàm, tham số và kiểu trả về không nhất thiết có cùng hướng tương thích.

Theo quy tắc variance thông dụng, kiểu hàm:

- **Contravariant** ở kiểu tham số: hàm nhận một kiểu tổng quát hơn có thể dùng ở nơi cần hàm nhận kiểu cụ thể hơn.
- **Covariant** ở kiểu kết quả: hàm trả về kiểu cụ thể hơn có thể dùng ở nơi chấp nhận kiểu tổng quát hơn.

Ví dụ, nếu Dog <: Animal:

- Một hàm nhận Animal có thể xử lý Dog.
- Một hàm trả về Dog có thể được dùng ở nơi chỉ yêu cầu kết quả Animal.

Điều này giúp callback và API hàm linh hoạt mà vẫn bảo toàn hợp đồng kiểu. Tuy nhiên, nếu DSL có nhiều tham số, generic constraints hoặc hiệu ứng, quy tắc cần được mở rộng tương ứng.

## 13. Union type, intersection type và tương thích

Một số DSL hoặc ngôn ngữ chủ hỗ trợ kiểu hợp (union) và kiểu giao (intersection).

**Union type** biểu diễn giá trị thuộc một trong nhiều kiểu:

~~~text
type Identifier = Integer | String
~~~

Biến Identifier có thể chứa Integer hoặc String. Khi sử dụng, người viết thường phải kiểm tra nhánh hoặc dùng pattern matching để biết giá trị cụ thể.

**Intersection type** biểu diễn giá trị đồng thời thỏa mãn nhiều hợp đồng:

~~~text
type AuditableService = Service & Auditable
~~~

Giá trị AuditableService phải đáp ứng cả Service và Auditable. Kiểu này có thể hữu ích khi ghép các capability hoặc interface.

Tương thích với union và intersection cần có quy tắc rõ. Ví dụ, một giá trị Dog có thể được gán cho Animal | String vì Dog là subtype của Animal. Nhưng khi đọc một giá trị có kiểu union, chương trình không thể mặc định nó là Animal nếu chưa loại trừ nhánh String.

## 14. Tương thích kiểu cấu trúc và danh định trong DSL

DSL có thể chọn nominal typing, structural typing hoặc kết hợp.

Ví dụ nominal:

~~~text
type CustomerId = String
type OrderId = String

let customerId: CustomerId = "C-100"
let orderId: OrderId = customerId
~~~

Nếu CustomerId và OrderId là hai kiểu danh định riêng, phép gán cuối có thể bị từ chối dù cả hai cùng dựa trên String. Điều này giúp tránh truyền nhầm mã khách hàng vào vị trí cần mã đơn hàng.

Ví dụ structural:

~~~text
type HasName = {
    name: String
}

type User = {
    name: String
    email: String
}
~~~

Nếu User có ít nhất cấu trúc mà HasName yêu cầu, một User có thể được dùng ở vị trí cần HasName theo quy tắc structural subtyping.

Một DSL có thể kết hợp hai cách: kiểu miền dùng danh định để giữ ranh giới nghiệp vụ, còn record hoặc interface dùng cấu trúc để tăng khả năng tái sử dụng.

## 15. Kiểu động, kiểu tĩnh và chuyển kiểu lúc chạy

Trong DSL có kiểu tĩnh, compiler hoặc validator kiểm tra tương thích trước khi chương trình chạy. Ví dụ, phép cộng String với Boolean có thể bị từ chối ngay khi phân tích ngữ nghĩa.

Trong DSL có kiểu động, một số quyết định kiểu chỉ được đưa ra khi chạy. Biểu thức có thể được chấp nhận khi parse nhưng gây lỗi nếu giá trị thực tế không hỗ trợ phép toán.

Một số DSL dùng kiểu tĩnh nhưng vẫn có dynamic value hoặc kiểu Any. Khi đó, compiler có thể không biết chính xác kiểu cho tới runtime và cần chèn runtime type check.

| Cách kiểm tra | Thời điểm | Lợi ích | Đánh đổi |
|---|---|---|---|
| Static type checking | Trước khi chạy | Phát hiện lỗi sớm, hỗ trợ IDE | Có thể hạn chế biểu thức động |
| Dynamic type checking | Khi chạy | Linh hoạt với dữ liệu thay đổi | Lỗi có thể xuất hiện muộn |
| Kết hợp | Một phần trước, một phần khi chạy | Cân bằng an toàn và linh hoạt | Cần quy định rõ phần nào được kiểm tra ở đâu |

Nếu DSL cho phép giá trị Any, việc chuyển sang kiểu cụ thể nên dùng kiểm tra runtime hoặc phép chuyển có kết quả lỗi. Không nên giả định giá trị Any luôn phù hợp với kiểu đích.

## 16. Suy luận kiểu và chuyển kiểu

Type inference cho phép hệ thống suy ra kiểu từ biểu thức và ngữ cảnh mà không yêu cầu người dùng khai báo mọi kiểu.

~~~text
let count = 3
let message = "ready"
~~~

Compiler có thể suy ra count là Integer và message là String. Nếu sau đó count được gán vào biến Decimal, quy tắc tương thích hoặc coercion vẫn cần được áp dụng.

Suy luận kiểu không có nghĩa hệ thống được tự ý chọn bất kỳ phép chuyển nào để làm chương trình hợp lệ. Compiler cần xác định kiểu biểu thức theo quy tắc inference trước, sau đó kiểm tra quan hệ tương thích trong ngữ cảnh sử dụng.

Với literal hoặc generic, ngữ cảnh có thể tham gia vào quá trình suy luận. Ví dụ, literal số có thể được suy ra trực tiếp thành kiểu đích nếu giá trị nằm trong miền cho phép. Những quy tắc như vậy phải được xác định để kết quả không phụ thuộc vào thứ tự kiểm tra hoặc implementation.

## 17. Overload resolution và chuyển kiểu

Một DSL có thể cho phép nhiều hàm cùng tên nhưng nhận các kiểu tham số khác nhau:

~~~text
function format(value: Integer): String
function format(value: Decimal): String
function format(value: Date): String
~~~

Khi người dùng gọi format(x), compiler phải chọn overload phù hợp. Nếu có nhiều phép chuyển kiểu ngầm định, có thể xuất hiện nhiều ứng viên cùng hợp lệ.

Một chính sách overload resolution thường cần xác định:

1. Ứng viên có đúng số lượng tham số không?
2. Kiểu đối số có tương thích trực tiếp với kiểu tham số không?
3. Nếu cần chuyển kiểu, phép chuyển nào được phép?
4. Ưu tiên exact match, subtype hay implicit conversion ra sao?
5. Nếu có nhiều ứng viên tốt ngang nhau, compiler báo mơ hồ hay áp dụng quy tắc tie-break?

Ví dụ, nếu x có kiểu Integer và có overload cho Integer lẫn Decimal, exact match thường được ưu tiên hơn việc mở rộng Integer sang Decimal. Nếu không có quy tắc ưu tiên, thêm một overload mới có thể khiến lời gọi cũ trở nên mơ hồ.

## 18. Chuyển kiểu có thể thất bại và cách biểu diễn kết quả

Không phải phép chuyển nào cũng thành công. Chuyển String sang Integer, Decimal sang Byte hoặc một kiểu cha sang kiểu con đều có thể thất bại.

Có thể mô hình hóa phép chuyển bằng một kết quả có hai nhánh:

\[
convert: S \rightarrow Result<T, ConversionError>
\]

Ví dụ:

~~~text
let parsed: Result<Integer, ParseError> = parseInteger("42")
~~~

Nếu parse thành công, kết quả chứa Integer 42. Nếu chuỗi sai định dạng, kết quả chứa lỗi. Người viết có thể xử lý:

~~~text
match parseInteger(input) {
    Success(value) => use(value)
    Failure(error) => report(error)
}
~~~

Một số ngôn ngữ dùng exception, Option, nullable hoặc phép thử cast thay cho Result. Dù chọn cách nào, DSL cần phân biệt rõ:

- Giá trị đích hợp lệ.
- Giá trị không tồn tại hoặc không thể chuyển.
- Lỗi định dạng.
- Lỗi vượt miền hoặc overflow.
- Lỗi do kiểu runtime không đúng.

## 19. Thiết kế quy tắc chuyển kiểu cho một DSL

Khi định nghĩa hệ kiểu, nhóm phát triển có thể xây dựng một bảng tương thích có hướng. Ví dụ:

| Kiểu nguồn | Kiểu đích | Mặc định | Ghi chú |
|---|---|---|---|
| Integer | Decimal | Cho phép ngầm định | Chỉ khi bảo toàn giá trị theo miền Decimal |
| Decimal | Integer | Yêu cầu tường minh | Chọn round, floor, ceil hoặc truncate |
| String | Integer | Yêu cầu parse | Có thể thất bại |
| Dog | Animal | Cho phép qua subtype | Upcast |
| Animal | Dog | Kiểm tra tường minh | Có thể thất bại lúc chạy |
| String? | String | Không cho phép trực tiếp | Cần xử lý null |
| List<Dog> | List<Animal> | Phụ thuộc variance | Mutable list thường invariant |

Quy trình thiết kế:

1. Liệt kê các kiểu dữ liệu của DSL và miền giá trị của từng kiểu.
2. Xác định quan hệ bằng kiểu và subtype.
3. Xác định các ngữ cảnh cần kiểm tra tương thích: gán, gọi hàm, trả về, toán tử và collection.
4. Liệt kê phép chuyển đổi được hỗ trợ theo hướng nguồn-đích.
5. Phân loại từng phép chuyển là implicit hay explicit.
6. Xác định phép chuyển có bảo toàn giá trị, có thể mất thông tin hay có thể thất bại.
7. Định nghĩa lỗi, overflow, rounding, null và giá trị ngoài miền.
8. Định nghĩa numeric promotion và overload resolution.
9. Viết ví dụ hợp lệ, không hợp lệ và trường hợp biên.
10. Bảo đảm interpreter, compiler và công cụ IDE dùng cùng quy tắc.

## 20. Ví dụ tổng hợp: hệ kiểu cho DSL đặt hàng

Giả sử DSL mô tả đơn hàng có các kiểu:

~~~text
type CustomerId = String
type OrderId = String
type Quantity = Integer
type Money = Decimal

type OrderLine = {
    sku: String
    quantity: Quantity
    unitPrice: Money
}

type Order = {
    id: OrderId
    customerId: CustomerId
    lines: List<OrderLine>
    total: Money
}
~~~

Một khai báo:

~~~text
let quantity: Quantity = 2
let unitPrice: Money = 125000.50
let lineTotal: Money = quantity * unitPrice
~~~

Hệ kiểu có thể cho phép Integer được mở rộng sang Decimal khi tính lineTotal. Nhưng nó không cho phép gán CustomerId sang OrderId chỉ vì cả hai có biểu diễn nền là String.

Nếu dữ liệu nhập từ file:

~~~text
let rawQuantity: String = "2"
let quantity: Quantity = parseInteger(rawQuantity)
~~~

phép parse cần xử lý lỗi. Nếu DSL định nghĩa Quantity là kiểu miền có ràng buộc dương, sau khi parse Integer thành công vẫn cần kiểm tra quantity > 0. Tương thích kiểu chỉ xác nhận giá trị có dạng Integer; nó chưa tự bảo đảm mọi bất biến nghiệp vụ của Quantity.

Nếu một hàm nhận Order:

~~~text
function calculateTotal(order: Order): Money
~~~

đối số phải có kiểu tương thích với Order. Một map tùy ý có các trường trông giống Order không nhất thiết được chấp nhận nếu DSL dùng nominal typing. Nếu dùng structural typing, nó có thể được chấp nhận khi đáp ứng đầy đủ cấu trúc và quy tắc.

Ví dụ này cho thấy hệ kiểu có thể kết hợp kiểu cơ bản, kiểu miền, generic, chuyển đổi số, parse dữ liệu và validation nghiệp vụ. Mỗi lớp cần có trách nhiệm rõ ràng để lỗi được phát hiện ở đúng giai đoạn.

## 21. Thông báo lỗi kiểu và trải nghiệm người dùng

Một hệ kiểu tốt không chỉ từ chối chương trình sai mà còn giải thích nguyên nhân và hướng sửa.

Thông báo quá chung:

~~~text
Type error
~~~

Thông báo hữu ích hơn:

~~~text
service.dsl:12:18
Cannot assign Decimal to Integer.
The value may contain a fractional part.
Use round(), floor(), ceil(), or an explicit checked conversion.
~~~

Một diagnostic nên cho biết:

- Vị trí của biểu thức hoặc giá trị.
- Kiểu thực tế và kiểu mong đợi.
- Ngữ cảnh gây ra yêu cầu kiểu, ví dụ phép gán hoặc đối số hàm.
- Lý do không tương thích nếu có thể xác định.
- Gợi ý chuyển kiểu phù hợp nhưng không tự chọn chính sách làm mất dữ liệu.

Nếu lỗi xuất phát từ một chuỗi chuyển đổi nhiều bước, công cụ có thể giải thích đường chuyển đổi không hợp lệ. Với overload mơ hồ, nên liệt kê các ứng viên và chỉ ra phép chuyển khiến chúng cùng hợp lệ.

## 22. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Cho phép mọi chuyển kiểu ngầm định | Mất dữ liệu và hành vi khó dự đoán | Chỉ cho phép coercion an toàn, không mơ hồ |
| Xem parse String như cast thông thường | Bỏ qua lỗi định dạng và dữ liệu ngoài miền | Dùng parse có kết quả lỗi |
| Không phân biệt widening và narrowing | Có thể âm thầm cắt hoặc overflow | Yêu cầu tường minh cho chuyển đổi có rủi ro |
| Dùng biểu diễn nền thay cho kiểu miền | Dễ truyền nhầm CustomerId và OrderId | Dùng nominal types khi ý nghĩa nghiệp vụ khác nhau |
| Không định nghĩa numeric promotion | Interpreter và compiler có thể cho kết quả khác nhau | Đặc tả kiểu toán hạng và kiểu kết quả |
| Cho phép covariance trên collection mutable | Có thể đưa phần tử sai kiểu vào collection | Dùng invariance hoặc giao diện chỉ đọc |
| Bỏ qua nullability | Lỗi null xuất hiện lúc chạy | Biểu diễn optional và kiểm tra khi unwrap |
| Không định nghĩa overload priority | Lời gọi trở nên mơ hồ khi thêm overload | Đặc tả thứ tự ưu tiên ứng viên |
| Downcast không kiểm tra | Có thể lỗi runtime | Dùng checked cast hoặc pattern matching |
| Chỉ kiểm tra kiểu mà không kiểm tra bất biến miền | Giá trị đúng kiểu nhưng sai nghiệp vụ | Tách type checking và domain validation |

## 23. Tiêu chí của một hệ tương thích và chuyển kiểu tốt

Một hệ kiểu dễ hiểu cần cho người viết biết giá trị nào có thể sử dụng ở đâu, phép chuyển nào được thực hiện tự động và phép chuyển nào cần nêu rõ. Những quy tắc đó phải nhất quán giữa gán biến, gọi hàm, trả về, toán tử, generic và các cấu trúc miền.

Các câu hỏi quan trọng cần trả lời:

- Hai kiểu được xem là bằng nhau theo tên hay theo cấu trúc?
- Quan hệ subtype nào được hỗ trợ và có bảo đảm thay thế không?
- Ngữ cảnh nào cho phép chuyển kiểu ngầm định?
- Phép chuyển có bảo toàn giá trị hay có thể mất thông tin?
- Parse và cast khác nhau ra sao?
- Overflow, rounding, null và lỗi runtime được xử lý thế nào?
- Generic có covariance, contravariance hay invariance?
- Overload resolution chọn ứng viên bằng quy tắc nào?
- Interpreter và compiler có thực hiện cùng một quy tắc không?

Tương thích kiểu xác định liệu một giá trị có thể được dùng trong một ngữ cảnh hay không; chuyển kiểu xác định cách tạo giá trị ở kiểu đích khi cần. Khi quan hệ subtype, coercion, cast và lỗi chuyển đổi được đặc tả rõ ràng, DSL có thể giữ được tính an toàn kiểu mà vẫn cung cấp cách biểu đạt linh hoạt và dễ dự đoán.
