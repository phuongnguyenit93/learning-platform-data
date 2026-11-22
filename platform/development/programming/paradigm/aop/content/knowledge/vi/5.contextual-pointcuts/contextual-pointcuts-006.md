# Ràng buộc biến ngữ cảnh cho advice sử dụng trong AOP

Khi một pointcut chọn được các điểm can thiệp (*join points*), advice thường cần biết **điểm nào đang chạy, ai là đối tượng liên quan, đối số nào được truyền và kết quả hoặc lỗi là gì**. Ví dụ, advice kiểm toán một thao tác gửi hàng cần lấy mã đơn và số lượng từ lời gọi hiện tại; advice đo đạc cần phân biệt lần chạy thành công với lần ném ngoại lệ. **Ràng buộc biến ngữ cảnh (context binding)** là cách nối những dữ kiện hiện diện ở điểm can thiệp với các **tham số có tên và kiểu xác định** mà advice có thể sử dụng.

Ý chính: **pointcut quyết định tập điểm được chọn; binding đưa dữ liệu từ một điểm đã chọn vào advice**. Chúng liên quan chặt chẽ nhưng không đồng nhất. Một biểu thức pointcut chỉ nêu tên phương thức có thể chọn đúng vị trí nhưng chưa cung cấp đối số cần dùng; ngược lại, ràng buộc kiểu/đối số có thể đồng thời thu hẹp điều kiện khớp. Mô hình và cú pháp ràng buộc phụ thuộc công nghệ AOP, loại join point và cơ chế weaving. Không phải hệ AOP nào cũng hỗ trợ mọi dạng ngữ cảnh.

Bài tập trung vào tư duy AOP nói chung, với ví dụ Java 17 mô phỏng việc chuyển dữ liệu vào advice qua một bộ chặn lời gọi giao diện và các ví dụ ký hiệu riêng cho một ngôn ngữ pointcut cụ thể.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **dữ liệu ngữ cảnh**, **biến được ràng buộc**, **tham số advice** và **điều kiện lọc pointcut**.
2. Liệt kê những dữ kiện thường có thể ràng buộc: đối số, đối tượng đang chạy, đối tượng đích, join point, metadata, giá trị trả về, ngoại lệ, annotation hoặc trạng thái điều khiển nếu mô hình hỗ trợ.
3. Giải thích cách ánh xạ tên biến và kiểu dữ liệu từ pointcut sang advice, tránh nhầm theo thứ tự, overload và kiểu runtime.
4. Nêu được **thời điểm** dữ liệu khả dụng: trước lời gọi, sau khi thành công, khi thất bại hoặc bao quanh thao tác.
5. Thiết kế advice chỉ quan sát mà giữ nguyên kết quả/ngoại lệ; hiểu các nguy cơ khi sửa đối số hoặc gọi tiếp nhiều lần.
6. Phân biệt ràng buộc ngữ cảnh với lưu ngữ cảnh dùng chung qua trường tĩnh, `ThreadLocal` hay trạng thái toàn cục.
7. Kiểm thử binding trên nhiều trường hợp, gồm `null`, primitive/boxing, overload, lỗi, đa luồng và đường bỏ qua cơ chế AOP.

## 2. Nhìn vấn đề qua một ví dụ

Giả sử ứng dụng có phương thức:

```java
Receipt submit(String orderId, int quantity)
```

Đây là **chữ ký minh họa**, chưa phải mã biên dịch độc lập. Một chính sách ghi nhận hoạt động cần các dữ kiện:

- **Mã đơn** để liên hệ bản ghi với nghiệp vụ.
- **Số lượng** để áp quy tắc lấy mẫu hoặc ghi thông số thống kê, khi phù hợp.
- **Phương thức đang thực thi** để phân biệt `submit` với `cancel`.
- **Đích thực hiện** để biết thành phần nào xử lý.
- **Kết quả hoặc lỗi** để phân loại trạng thái thao tác.

Nếu advice dùng một biến `orderId` có giá trị của đối số đầu tiên và `quantity` có giá trị của đối số thứ hai, ta đã **ràng buộc** hai dữ kiện tại join point vào hai tham số cục bộ của advice. Khi lần gọi tiếp theo là `submit("O-2", 3)`, giá trị truyền vào advice phải thuộc lần gọi mới, không lấy nhầm dữ liệu lần gọi trước.

### 2.1. Dòng chảy khái niệm

```text
Lời gọi submit("O-2", 3)
             |
             v
[Điểm can thiệp được pointcut lựa chọn]
             |
             +-- Phương thức: submit(String, int)
             +-- Đối số 0: "O-2"
             +-- Đối số 1: 3
             +-- Đối tượng đích: OrderService instance
             |
             v
[Liên kết context -> tham số advice]
             |
             +-- orderId  = "O-2"  (String)
             +-- quantity = 3      (int)
             +-- method   = metadata về join point
             |
             v
[Advice sử dụng các giá trị đã ràng buộc]
             |
             v
[Tiếp tục thao tác chính / xử lý kết quả hoặc lỗi]
```

Mô hình trên giả định cơ chế đang dùng **có thể cung cấp** dữ liệu tương ứng. Một bộ chặn chỉ có tên phương thức nhưng không có giá trị đối số sẽ không tự nhiên cấp đủ dữ kiện cho phép ràng buộc.

### 2.2. Bốn thành phần cần tách bạch

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Join point** | Điểm trong luồng thực thi có thể được can thiệp | Một lần thực thi `submit(String,int)` |
| **Pointcut** | Quy tắc chọn những join point phù hợp | Các thao tác `submit` của thành phần đặt hàng |
| **Binding** | Ánh xạ dữ kiện ở điểm đã chọn vào biến có tên và kiểu | `orderId` nhận đối số thứ nhất |
| **Advice** | Hành vi sử dụng dữ kiện đã ràng buộc | In thông tin đo đạc, ghi kết quả |

Một pointcut có thể dùng điều kiện “đối số thứ nhất phải là đối tượng thuộc kiểu X” vừa để **lọc** vừa để **ràng buộc giá trị**; nhưng điều kiện ấy cần được hiểu theo ngữ nghĩa thực tế của công nghệ (khớp chữ ký tĩnh hay kiểm tra kiểu đối tượng tại thời gian chạy).

## 3. Những loại dữ liệu ngữ cảnh thường gặp

Các công nghệ AOP khác nhau ở phạm vi hỗ trợ. Bảng là tập **khả năng thường gặp**, không phải cam kết một bộ weaving duy nhất luôn cung cấp hết.

| Dữ kiện | Ý nghĩa | Điểm cần lưu ý |
| --- | --- | --- |
| **Arguments (đối số)** | Giá trị truyền vào lời gọi/điểm thực thi | Có thể `null`, boxed primitive hoặc đối tượng có thể thay đổi |
| **Join point signature** | Tên, kiểu khai báo, danh sách tham số, loại join point | Metadata tĩnh khác giá trị đối số ở lần chạy cụ thể |
| **Current context / this** | Đối tượng liên quan tới điểm thực thi ở phía ngữ cảnh hiện tại | Không nhất thiết là cùng đối tượng đích |
| **Target** | Đối tượng nhận/thực hiện thao tác chính, nếu điểm nối có target | Không phải mọi join point đều có target |
| **Return value** | Giá trị hoàn tất khi thành công | Không có ở nhánh lỗi; `void` không có giá trị trả về hữu ích |
| **Thrown exception** | Ngoại lệ từ đường thực thi thất bại | Không có ở nhánh thành công |
| **Annotation/metadata** | Dấu đánh dấu trên lớp/phương thức/tham số tùy mô hình | Phải biết metadata nằm ở interface, implementation hay nơi khác |
| **Control-flow context** | Quan hệ đang nằm trong luồng gọi của một điểm khác, nếu được hỗ trợ | Có thể tăng chi phí; không tự truyền qua ranh giới bất đồng bộ |
| **Execution data** | Thời điểm, mã tương quan, thông tin tracing truyền từ ngoài | Không nhất thiết là dữ kiện built-in của pointcut |

Cần phân biệt hai nguồn dữ liệu:

- **Ngữ cảnh join point do cơ chế AOP cung cấp:** ví dụ đối số, phương thức, target và kết quả.
- **Ngữ cảnh ứng dụng do người lập trình tự truyền vào hoặc tra cứu:** ví dụ danh tính người dùng đã xác minh, transaction ID, trace ID. Đây không phải thông tin tự nhiên xuất hiện trong mọi join point.

## 4. Ràng buộc đối số (argument binding)

Đối số là trường hợp phổ biến và trực quan nhất. Với thao tác:

```java
void transfer(String from, String to, long amount)
```

Advice có thể cần `from`, `to` và `amount`. Một cơ chế hỗ trợ binding cho phép ánh xạ từng dữ kiện vào biến tham số advice.

### 4.1. Ánh xạ theo số lượng, vị trí và kiểu

Nếu advice kỳ vọng:

```text
audit(String source, String destination, long amount)
```

thì ràng buộc cần xác định rõ `source` ứng với tham số đầu, `destination` ứng với tham số thứ hai, `amount` ứng với tham số thứ ba. Không thể suy từ **tên** `source` hay `destination` mà tự biết vị trí chính xác của đối số trong phương thức đích.

Một cách nhìn:

```text
Đích:    transfer( String from, String to, long amount )
Vị trí:            [0]          [1]         [2]
Binding:           |            |           |
Advice:    audit( String source, String dest, long amount )
```

Mỗi hệ pointcut có cú pháp khác nhau để mô tả phép ánh xạ ấy. Một số buộc khai báo tham số của named pointcut rồi chuyển tiếp vào advice; một số cung cấp mảng đối số để advice đọc và ép kiểu. Dù hình thức nào, **nhầm thứ tự có thể tạo lỗi nghiệp vụ mà compiler không phát hiện** nếu hai vị trí cùng kiểu.

### 4.2. Kiểu khai báo và kiểu giá trị runtime

Xét hai overload:

```java
void accept(String value);
void accept(Object value);
```

Lời gọi `accept((Object) "ABC")` chọn overload `accept(Object)` dù giá trị runtime là `String`. Một pointcut chọn **chữ ký khai báo `accept(String)`** không khớp lời gọi này. Ngược lại, một điều kiện theo **kiểu đối số runtime `String`** có thể khớp, tùy ngôn ngữ pointcut.

Nếu mục tiêu là chọn đúng overload, hãy dùng điều kiện chữ ký thích hợp. Nếu mục tiêu là “mọi lời gọi có đối số đầu tiên là một đối tượng String”, điều kiện runtime có thể là điều cần thiết. Hai yêu cầu không tương đương.

### 4.3. `null` và kiểm tra kiểu

Một phép kiểm tra kiểu runtime như `arg instanceof String` trả `false` khi `arg == null`. Vì thế không thể coi ràng buộc dữ liệu `null` là một đối tượng `String` runtime hợp lệ theo `instanceof`.

Ở phía Java, lời gọi `accept(null)` trên cặp overload `String` và `Object` chọn `String` vì cụ thể hơn; nhưng với hai overload `accept(String)` và `accept(Integer)`, `accept(null)` là mơ hồ trừ khi ép kiểu. Phân biệt **lựa chọn overload ở compiler** với **điều kiện binding lúc thực thi** giúp tránh suy luận sai.

### 4.4. Primitive, boxing và varargs

Một phương thức nhận `int count`, nhưng API reflection động như `Method.invoke` hoặc mảng `Object[]` có thể biểu diễn giá trị `int` bằng đối tượng `Integer`. Việc **boxing** này không thay đổi chữ ký đã khai báo: `run(int)` và `run(Integer)` vẫn là hai overload khác nhau.

Varargs như `log(String... messages)` được khai báo ở mức bytecode như một tham số `String[]`. Một lời gọi nguồn `log("a", "b")` không có nghĩa advice nhận hai tham số riêng ở chữ ký runtime. Khi binding cần biết cơ chế trình bày đối số theo **phương thức khai báo** hay **biểu thức lời gọi phía người gọi**.

### 4.5. Mảng, đối tượng mutable và snapshot

Nếu advice nhận `List<Item>` hoặc một đối tượng mutable, nó thường nhận **tham chiếu đến đối tượng**, không tự nhận một bản sao bất biến. Người gọi hoặc luồng khác có thể thay đổi đối tượng trong khi advice đang sử dụng.

Nếu phải ghi lại trạng thái phục vụ kiểm toán, hãy quyết định dữ liệu nào cần sao chụp, cách loại bỏ thông tin nhạy cảm và thời điểm snapshot phù hợp. Binding một biến vào đối tượng **không tự bảo đảm dữ liệu vẫn giữ nguyên** tới lúc bản ghi được xử lý.

## 5. Ràng buộc `this`, `target` và metadata của join point

Đôi khi đối số chưa đủ để phân biệt ngữ cảnh. Một aspect muốn lấy thành phần xử lý hoặc tên điểm can thiệp.

### 5.1. `this` và `target` không nhất thiết giống nhau

Trong những mô hình AOP phân biệt hai khái niệm:

- **`this`** gắn với đối tượng ở ngữ cảnh đang thực thi join point, tùy loại điểm nối.
- **`target`** gắn với đối tượng nhận thao tác chính mà điểm nối đang nói đến, nếu tồn tại.

Tại một điểm thực thi phương thức instance thông thường trong đối tượng đích, hai đối tượng có thể trùng nhau. Tại điểm **lời gọi phương thức**, đối tượng của phía người gọi và đối tượng nhận lời gọi có thể khác. Một mô hình AOP dựa trên proxy có thể quy định khác biệt riêng giữa proxy và đích.

Ví dụ mã trong `Checkout` gọi `gateway.charge(...)`:

```text
checkout.perform()
    |
    +-- gọi ---> paymentGateway.charge(...)
         ^
         |
       điểm call có ngữ cảnh mã phía người gọi,
       còn target là đối tượng nhận lời gọi
```

Không nên mặc định `this` luôn là proxy hoặc luôn là target trên mọi công nghệ, loại join point và kiểu phương thức. Static join point cũng có thể không có đối tượng nhận phù hợp để ràng buộc.

### 5.2. Metadata tĩnh khác dữ liệu từng lần gọi

Thông tin **tĩnh** như tên phương thức, kiểu khai báo, số tham số hoặc vị trí mã thường được mô tả bằng metadata của join point. Thông tin **động** như mã đơn, giá trị số lượng hoặc target instance xuất hiện theo từng lần thực thi.

Ràng buộc một `Method`, một mô tả chữ ký hoặc một đối tượng `JoinPoint` (trong công nghệ hỗ trợ) giúp advice truy cập metadata. Tuy nhiên, *metadata hiện diện* không chứng minh **đường can thiệp thật sự chạy** hoặc cách ánh xạ kiểu từ pointcut sang tham số đúng.

### 5.3. Phân biệt trạng thái đối tượng và ngữ cảnh lời gọi

Nếu advice cần tên loại hàng, nên cân nhắc ràng buộc **tham số của lời gọi**, thay vì ép advice tự gọi thêm getter trên target. Một getter có thể gây tác dụng phụ, phát sinh join point khác hoặc đọc trạng thái vừa bị luồng khác thay đổi.

Tận dụng dữ liệu pointcut cung cấp khi đủ; chỉ truy vấn thêm khi hợp đồng ngữ cảnh yêu cầu và đã tính đến khả năng recursion, đồng thời và bảo mật.

## 6. Ràng buộc dữ liệu kết quả và lỗi

Dữ liệu có thể ràng buộc **phụ thuộc giai đoạn lời gọi**. Không nên giả định trước khi gọi đích đã có kết quả, hoặc khi thao tác lỗi vẫn có một giá trị trả về thành công.

| Giai đoạn advice | Dữ liệu thường có thể dùng | Dữ liệu chưa/không có |
| --- | --- | --- |
| **Before** | Đối số, target, chữ ký, metadata phù hợp | Giá trị trả về của lần thực thi chưa diễn ra |
| **After returning** | Đối số và **giá trị hoàn tất thành công** | Ngoại lệ của đường thất bại đó |
| **After throwing** | Đối số và **ngoại lệ đã ném** | Giá trị trả về thành công |
| **After/finally** | Một số metadata và dữ liệu ngữ cảnh, tùy khả năng công cụ | Không mặc định có cả return và error cùng lúc |
| **Around** | Dữ liệu trước khi tiếp tục, và kết quả/lỗi sau `proceed` nếu thực thi tiếp | Kết quả không tồn tại nếu bỏ qua đích hoặc chưa chạy |

### 6.1. Ràng buộc giá trị trả về

Một advice thực thi sau khi `lookup(id)` trả kết quả có thể cần kiểu của kết quả để ghi trạng thái hoặc đo kích thước. Điểm cần xác định:

- Advice có nhận **kết quả trả về dưới kiểu tĩnh cụ thể** hay một kiểu tổng quát không?
- Nếu kết quả là `null`, điều kiện ràng buộc theo kiểu runtime có còn khớp không?
- Với phương thức `void`, cơ chế biểu diễn sự kiện hoàn tất thành công ra sao?
- Với generics, kiểu ở runtime có bị erasure ảnh hưởng không?

Trong nhiều công nghệ, cơ chế binding kết quả thành công được khai báo riêng với cơ chế lấy đối số. Không nên coi mọi dữ kiện trong `args` cũng có mặt trong `result`.

### 6.2. Ràng buộc ngoại lệ

Một advice theo nhánh lỗi cần biết đối tượng lỗi gốc. Khi reflection dùng `Method.invoke`, ngoại lệ của phương thức đích thường được bọc trong `InvocationTargetException`; muốn hiển thị/tiếp tục lỗi đích phải bóc `getCause()` đúng cách.

Advice thuần quan sát nên **không nuốt ngoại lệ**, không đổi thành kết quả thành công và không tự tạo một loại lỗi khác chỉ do việc ghi log. Nếu chính sách thực sự cần chuyển đổi lỗi, đó là thay đổi ngữ nghĩa có chủ đích và phải được kiểm thử.

### 6.3. `finally` và kết quả

Khối `finally` trong Java chạy dù lời gọi thành công hay thất bại (bỏ qua những trường hợp bất thường như kết thúc tiến trình). Nó thích hợp để ghi kết thúc hoặc thu dọn trạng thái. Nhưng `finally` không có nghĩa **luôn có kết quả trả về**; kết quả đã tính được ở đường thành công khác dữ kiện lỗi ở đường thất bại.

Cũng phải tránh ném lỗi mới trong `finally` khiến ngoại lệ nghiệp vụ ban đầu bị thay thế. Khía cạnh chỉ dùng theo dõi nên giảm tối đa khả năng phát sinh lỗi ở đường dọn dẹp.

## 7. Binding trong pointcut có tên và lời gọi advice

Nhiều ngôn ngữ AOP cho phép khai báo **pointcut có tham số**. Người viết pointcut mô tả dữ kiện lấy từ join point và khai báo tham số để chuyển tiếp cho advice dùng lại.

Có thể nhìn mô hình chung như sau:

```text
pointcut submitOrder(orderCode, quantity):
    chọn execution của submit(String, int)
    AND ràng buộc đối số 0 -> orderCode
    AND ràng buộc đối số 1 -> quantity

before(orderCode, quantity):
    áp dụng ở submitOrder(orderCode, quantity)
    dùng orderCode, quantity trong thân advice
```

Đây là **giả mã mô tả ý tưởng**, không phải cú pháp của Java hoặc của mọi ngôn ngữ AOP.

### 7.1. Ví dụ ký hiệu AspectJ để nhận diện cú pháp thật

AspectJ là một ngôn ngữ/công cụ AOP cho Java có biểu thức pointcut như `execution`, `args`, `this` và `target`. Ví dụ sau là **đoạn aspect minh họa riêng cho công nghệ này** và không được biên dịch trực tiếp bằng `javac`:

```java
public aspect SubmitAuditAspect {
    pointcut selectedSubmit(String code, int count):
        execution(* example.order.OrderService.submit(String, int))
        && args(code, count);

    before(String code, int count): selectedSubmit(code, count) {
        System.out.println("order=" + code + ", count=" + count);
    }
}
```

**Đọc từng thành phần:**

1. `execution(* example.order.OrderService.submit(String, int))` chọn **loại điểm thực thi** với chữ ký mong muốn trong mẫu đã định.
2. `args(code, count)` cho cơ chế ràng buộc **các đối số** tại điểm được chọn vào hai biến tương ứng, theo kiểu và vị trí.
3. `selectedSubmit(String code, int count)` công bố hai tham số của **named pointcut** để advice có thể dùng lại.
4. `before(String code, int count): selectedSubmit(code, count)` khai báo biến trong **phạm vi advice** và dùng được trong phần thân.

Trong Java source thông thường, việc có biến tên `code` ở phương thức đích **không tự chuyển tên biến ấy sang advice**. Tên binding là khai báo trong cấu trúc pointcut/advice; dữ liệu đến từ ngữ cảnh thực thi, không phải từ phép tìm tên biến cục bộ trong bytecode.

Để chạy một ví dụ AspectJ thật cần bộ biên dịch/weaver tương ứng, đường lớp và artifact phù hợp; **mã trên được dùng để phân tích cú pháp**, không phải một chương trình Java độc lập hay đầu ra chạy bằng JDK thuần.

### 7.2. Nguồn ràng buộc ảnh hưởng tập điểm được chọn

Một biểu thức binding có thể đồng thời **ràng buộc giá trị** và **đặt điều kiện khớp**. Ví dụ điều kiện theo kiểu của đối số có thể loại trừ những điểm có giá trị không thỏa mãn, tùy cách công cụ đối chiếu kiểu tĩnh/động và giá trị `null`.

Vì vậy, nếu thêm `args(...)` vào pointcut mà số điểm khớp thay đổi, đó không nhất thiết là lỗi. Phải đọc chính xác ngữ nghĩa biểu thức. Không nên trộn một wildcard “mọi tham số” với ràng buộc “hai tham số” rồi mặc định hai điều kiện giống nhau.

### 7.3. Tham số advice phải tương thích kiểu

Nếu pointcut ràng buộc `quantity` kiểu `int`, advice không được tự giả định giá trị là `String`. Công cụ có thể kiểm tra kiểu ở thời điểm weaving/biên dịch, hoặc lỗi có thể biểu hiện khi chạy nếu cơ chế hoàn toàn động.

Nếu ràng buộc đối tượng tham chiếu kiểu cha, việc ép xuống kiểu con phải có điều kiện đúng; đừng dùng cast vô điều kiện để tránh lỗi bằng cách nuốt ngoại lệ. Với một mảng `Object[]` trong cơ chế tự viết, **bạn chịu trách nhiệm kiểm tra** số phần tử và kiểu trước khi ép.

### 7.4. Một binding có thể dùng cho nhiều advice không?

Một named pointcut định nghĩa tập điểm và hợp đồng tham số có thể được nhiều advice tái sử dụng. Tuy nhiên, mỗi advice có **biến cục bộ và lần thực thi riêng**. Khi hai lời gọi chạy đồng thời, chúng không nên chia sẻ một biến `orderCode` có thể thay đổi nằm trong field instance của aspect chỉ vì pointcut cùng tên.

Tái sử dụng **định nghĩa ràng buộc** khác với dùng chung **trạng thái runtime**.

## 8. Ví dụ Java 17 độc lập: chuyển context vào bộ chặn lời gọi

Ví dụ này dùng **JDK dynamic proxy** để mô phỏng:

- Pointcut chọn chính xác phương thức `ship(String, int)` theo chữ ký khai báo;
- Binding nhận `orderId`, `quantity`, `Method` và target cho lần gọi đó;
- Advice ghi nhận đường thành công, đường lỗi và kết thúc;
- Lời gọi ngoài pointcut hoặc bypass proxy không chạy advice.

Đây là **minh họa cơ chế ở thời gian chạy với proxy**, không phải bộ weaving can thiệp mọi loại join point. Ví dụ không sử dụng thư viện AOP ngoài JDK.

Tạo tệp `ContextBindingDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class ContextBindingDemo {
    interface ShippingPort {
        String ship(String orderId, int quantity);
        String inspect(String orderId);
    }

    static final class ShippingService implements ShippingPort {
        @Override
        public String ship(String orderId, int quantity) {
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }
            return "SHIPPED:" + orderId + ":" + quantity;
        }

        @Override
        public String inspect(String orderId) {
            return "INSPECT:" + orderId;
        }
    }

    static Object invokeTarget(Method method, Object target, Object[] args)
            throws Throwable {
        try {
            return method.invoke(target, args);
        } catch (InvocationTargetException ex) {
            throw ex.getCause();
        }
    }

    static boolean selected(Method method) {
        return method.getName().equals("ship")
                && Arrays.equals(method.getParameterTypes(),
                        new Class<?>[] { String.class, int.class });
    }

    static ShippingPort withAdvice(ShippingPort target) {
        return (ShippingPort) Proxy.newProxyInstance(
                ShippingPort.class.getClassLoader(),
                new Class<?>[] { ShippingPort.class },
                (proxy, method, args) -> {
                    if (!selected(method)) {
                        return invokeTarget(method, target, args);
                    }

                    // Binding minh họa: chuyển đối số và metadata vào tên biến.
                    String orderId = (String) args[0];
                    int quantity = (Integer) args[1];
                    String operation = method.getName();
                    String component = target.getClass().getSimpleName();

                    System.out.println("[BEFORE] method=" + operation
                            + " order=" + orderId
                            + " qty=" + quantity
                            + " target=" + component);
                    try {
                        Object result = invokeTarget(method, target, args);
                        System.out.println("[RETURN] value=" + result);
                        return result;
                    } catch (Throwable ex) {
                        System.out.println("[THROW] type="
                                + ex.getClass().getSimpleName());
                        throw ex;
                    } finally {
                        System.out.println("[FINALLY]");
                    }
                });
    }

    public static void main(String[] args) {
        ShippingPort port = withAdvice(new ShippingService());

        System.out.println("CALLER " + port.ship("SO-7", 2));

        try {
            port.ship("SO-8", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER_ERROR " + ex.getMessage());
        }

        System.out.println("OTHER " + port.inspect("SO-7"));
        System.out.println("DIRECT "
                + new ShippingService().ship("SO-9", 1));
    }
}
```

Chạy từ thư mục chứa tệp, với JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 ContextBindingDemo.java
java ContextBindingDemo
```

Đầu ra dự kiến:

```text
[BEFORE] method=ship order=SO-7 qty=2 target=ShippingService
[RETURN] value=SHIPPED:SO-7:2
[FINALLY]
CALLER SHIPPED:SO-7:2
[BEFORE] method=ship order=SO-8 qty=0 target=ShippingService
[THROW] type=IllegalArgumentException
[FINALLY]
CALLER_ERROR Số lượng phải dương
OTHER INSPECT:SO-7
DIRECT SHIPPED:SO-9:1
```

### 8.1. Những biến nào được ràng buộc?

| Biến trong handler | Nguồn của dữ liệu | Ý nghĩa |
| --- | --- | --- |
| `method` | Thông tin lời gọi giao diện do proxy cung cấp | Tên, danh sách kiểu tham số của phương thức được gọi |
| `args[0]` → `orderId` | Đối số vị trí 0 của lần gọi hiện tại | Mã đơn `String` |
| `args[1]` → `quantity` | Đối số vị trí 1, boxed thành `Integer` trong `Object[]` | Số lượng dạng `int` |
| `target` → `component` | Đối tượng được proxy chuyển tiếp tới | Tên thành phần thực hiện |
| `result` | Giá trị trả về của lần gọi đích sau khi thành công | Dữ liệu phục vụ after-returning |
| `ex` | Ngoại lệ được chuyển tiếp từ đích ở nhánh lỗi | Dữ liệu phục vụ after-throwing |

Ví dụ cố ý dùng `Arrays.equals` với **chữ ký khai báo**, không lọc theo `args[0] instanceof String`; nếu nhiều overload hoặc một phương thức nhận `Object`, kiểm tra kiểu giá trị runtime có thể chọn nhầm.

### 8.2. Vì sao `quantity` phải chuyển từ `Integer`?

`Method.getParameterTypes()` trả về `int.class` cho chữ ký đã khai báo. Nhưng handler nhận đối số trong `Object[]`, không lưu primitive trực tiếp; giá trị `int` được boxing thành `Integer`. Do đó `(Integer) args[1]` rồi unboxing sang `int` là hợp lệ trong ví dụ.

Đây là cách Java reflection/proxy mang dữ liệu. Một cơ chế AOP có hỗ trợ ràng buộc trực tiếp có thể cho advice khai báo tham số `int` mà không cần tự ép phần tử mảng như trên.

### 8.3. Nhánh lỗi vẫn giữ ngoại lệ gốc

`method.invoke` bọc ngoại lệ do phương thức đích ném trong `InvocationTargetException`. Hàm `invokeTarget` bóc `getCause()` rồi ném lại. Handler in loại lỗi và chuyển tiếp, nên người gọi vẫn bắt đúng `IllegalArgumentException`.

Đây là điều quan trọng khi advice chỉ dùng theo dõi: **binding ngoại lệ nhằm đọc/ghi thông tin**, không phải tự cho phép biến một thao tác thất bại thành thành công.

### 8.4. Hai đường không có advice

`port.inspect("SO-7")` vẫn qua proxy nhưng không khớp bộ lọc `selected`; handler chỉ chuyển tiếp. `new ShippingService().ship("SO-9", 1)` gọi thẳng đối tượng gốc, nên không qua proxy. Dù tên/chữ ký `ship(String,int)` khớp, đường gọi trực tiếp không được can thiệp.

Vì thế **“binding đúng”** và **“lời gọi thực sự đi qua cơ chế áp dụng pointcut”** là hai kiểm tra độc lập.

### 8.5. Giới hạn của ví dụ

- JDK dynamic proxy chặn lời gọi **qua giao diện được đại diện**; không tự chặn constructor, đọc/ghi field, phương thức `private` hoặc mọi lời gọi nội bộ.
- `selected` chỉ là bộ lọc Java viết tay, không phải một ngôn ngữ pointcut tổng quát.
- Ví dụ ghi mã đơn và số lượng để dễ quan sát; trong hệ thống thực cần xem quy tắc lưu trữ, che chắn thông tin nhạy cảm và độ tin cậy của kiểm toán.
- Nếu advice được yêu cầu sửa đối số hoặc bỏ qua thao tác đích, phải thiết kế riêng và không thể tự suy rằng ngữ nghĩa nghiệp vụ giữ nguyên.

## 9. Around advice và hành động tiếp tục

**Around advice** có thể dùng dữ liệu ngữ cảnh trước và sau việc chuyển tiếp tới hành vi chính. Nhiều mô hình AOP gọi bước tiếp tục đó là **`proceed`**.

```text
around(context):
    validate/observe(context)
    try:
        result = proceed()
        observe(result)
        return result
    catch error:
        observe(error)
        throw error
    finally:
        cleanup()
```

Đây là **giả mã**, không phải cú pháp Java/AspectJ độc lập.

### 9.1. Ràng buộc không đồng nghĩa quyền sửa dữ liệu

Một advice được cấp `orderId` và `quantity` có thể sử dụng chúng để ghi log hoặc đưa ra điều kiện lọc. Nhưng chuyện **thay giá trị tham số truyền tới đích** là năng lực riêng của cơ chế around/proceed và cần kiểm tra hợp đồng.

Một số công nghệ cho phép `proceed` với danh sách đối số thay thế; một số giới hạn kiểu, số lượng và vị trí. Với một lời gọi đã chọn overload cụ thể, việc thay dữ liệu **không tự chuyển sang overload khác** chỉ vì kiểu runtime mới giống kiểu tham số của overload kia.

### 9.2. Số lần `proceed` thay đổi nghiệp vụ

- Không gọi `proceed`: đích có thể không chạy.
- Gọi một lần: hành vi thường được chuyển tiếp một lần, nếu không có lớp can thiệp khác thay đổi điều đó.
- Gọi nhiều lần: đích có thể được thực thi nhiều lần, kéo theo tác dụng phụ lặp.

Nếu advice chỉ đo thời gian, gọi đúng một lần và bảo toàn kết quả/lỗi là nguyên tắc tốt. Nếu advice chủ ý thử lại, cần đánh giá idempotency, trạng thái không chắc chắn và ranh giới giao dịch.

### 9.3. Binding kết quả phụ thuộc nơi đặt lời gọi

Kết quả trả về có thể khác nhau khi advice bên trong đã chuyển đổi kết quả, cache trả lời mà không thực thi đích, hoặc các aspect khác thay đổi hành vi. Một `result` ở advice ngoài cùng là kết quả từ **chuỗi bên trong** sau khi tiếp tục, không nhất thiết chỉ là giá trị do phương thức nghiệp vụ trực tiếp trả về.

Tương tự, lỗi được around advice bắt có thể phát sinh từ đích hoặc một advice khác nằm bên trong. Nếu cần phân loại nguồn lỗi, chỉ nhìn tên ngoại lệ có thể chưa đủ.

## 10. Scope của biến ràng buộc và an toàn đồng thời

Điều kiện quan trọng: ngữ cảnh của một lời gọi phải thuộc **chính lời gọi ấy**, nhất là khi nhiều luồng chạy đồng thời.

### 10.1. Tham số advice là dữ liệu cục bộ

Một advice có tham số `orderId` nhận dữ liệu theo từng lần thực thi. Hai lời gọi song song có hai lần kích hoạt advice riêng. Đừng chuyển `orderId` vào một field dùng chung rồi giả định field đó luôn chứa mã đơn của “lời gọi hiện tại”.

Ví dụ thiết kế nguy hiểm:

```java
class BadRecorder {
    String currentOrderId;

    void before(String orderId) {
        currentOrderId = orderId;
    }

    void after() {
        System.out.println(currentOrderId);
    }
}
```

Đây là **minh họa vấn đề**, không phải một chương trình chạy độc lập. Nếu cùng một `BadRecorder` được nhiều luồng dùng, lời gọi A và B có thể ghi đè `currentOrderId` của nhau. Binding đúng ở `before` không khiến field dùng chung trở nên an toàn.

### 10.2. `ThreadLocal` cũng không phải binding tự động

`ThreadLocal` có thể lưu một ít trạng thái theo luồng nhưng cần quản lý vòng đời, truyền bối cảnh và xóa dữ liệu đúng lúc, nhất là với pool thread. Khi công việc chuyển sang luồng/tác vụ bất đồng bộ, dữ liệu không nhất thiết tự truyền theo.

Một advice muốn ghi trace ID cần biết trace ID được tạo và truyền bằng cơ chế nào. **Pointcut ràng buộc đối số không tự giải quyết propagation của ngữ cảnh xuyên luồng, tiến trình hoặc hàng đợi.**

### 10.3. Dữ liệu mutable không đồng nghĩa snapshot

Nếu advice nhận một đối tượng `Order`, hai advice ở hai thời điểm có thể nhìn trạng thái khác nhau của cùng tham chiếu. Cần biết có giao dịch/khóa hoặc snapshot không, trước khi tuyên bố dữ liệu ghi là “giá trị tại thời điểm bắt đầu”.

Trong kiểm toán nghiêm ngặt, có thể phải lấy dữ liệu đã xác nhận ở ranh giới nghiệp vụ hơn là đọc đối tượng ở một join point kỹ thuật tùy ý.

## 11. Điều kiện động, độ chính xác và chi phí

Binding có thể đi kèm bộ lọc động: ví dụ chỉ theo dõi khi số lượng vượt ngưỡng, chỉ với đối tượng thuộc loại nhất định, hoặc chỉ khi mã tương quan đã tồn tại.

Tuy nhiên, quyết định theo đối số runtime cần lưu ý:

- Điều kiện có thể khác nhau cho mỗi lần chạy cùng một chữ ký.
- `null` hoặc dữ liệu sai kiểu phải có hành vi rõ ràng.
- Kiểm tra lặp ở nhiều join point nóng có thể tăng thời gian thực thi.
- Lọc dữ liệu trước khi áp advice có thể tạo **vùng quan sát trống** khi chính sách kiểm toán cần đầy đủ.
- Việc dùng dữ liệu nhạy cảm để quyết định pointcut không biện minh cho ghi dữ liệu đó vào log.

Nếu chỉ cần xác định “tất cả lần gọi của `submit(String,int)`”, một điều kiện chữ ký tĩnh có thể đủ. Chỉ thêm điều kiện động khi yêu cầu thật sự cần.

### 11.1. Binding và overload

Cùng một tên phương thức có thể có nhiều danh sách tham số. Nếu advice viết `String code = (String) args[0]` nhưng pointcut lại chọn một overload `submit(int, String)`, cast sẽ lỗi. Vì vậy:

1. Trước tiên chọn **tập chữ ký chính xác** hoặc kiểm tra cấu trúc đối số đúng như yêu cầu.
2. Sau đó ràng buộc dữ liệu theo vị trí/kiểu thích hợp.
3. Thêm kiểm thử âm cho những overload không được chọn.

Đừng chỉ dùng `method.getName().equals("submit")` rồi ép kiểu mù quáng.

### 11.2. Binding và kiểm soát quyền

Một advice nhận `accountId` không chứng minh giá trị ấy thuộc người dùng đang đăng nhập. Nếu `accountId` đến từ yêu cầu bên ngoài, nó có thể bị giả mạo. Một chính sách bảo mật cần dùng danh tính đáng tin cậy, kiểm tra sở hữu tại ranh giới phù hợp và bao phủ các đường truy cập cần thiết.

Binding là **cơ chế chuyển dữ liệu**, không phải chứng thực độ tin cậy của dữ liệu.

## 12. Kiểm thử binding có hiệu lực

| Tình huống | Kỳ vọng kiểm tra |
| --- | --- |
| Phương thức thuộc pointcut, dữ liệu hợp lệ | Advice nhận đúng vị trí và kiểu dữ liệu |
| Thay dữ liệu mỗi lần gọi | Không lấy nhầm dữ liệu của lần trước |
| Phương thức ngoài pointcut | Advice không chạy |
| Overload cùng tên nhưng khác chữ ký | Không ép kiểu sai hoặc khớp ngoài ý muốn |
| Đối số `null` | Hành vi rõ theo điều kiện khớp và hợp đồng |
| Primitive được boxing qua API động | Dữ liệu đúng dù biểu diễn dưới `Object[]` |
| Đích ném ngoại lệ | Advice nhận đúng nhánh lỗi và giữ ngoại lệ gốc |
| Đích trả `null` hoặc phương thức `void` | Không giả định luôn có kết quả đối tượng |
| Hai lời gọi đồng thời | Context của mỗi lời gọi không bị lẫn |
| `this` và `target` khác nhau | Binding đúng đối tượng theo loại join point |
| Bỏ qua proxy hoặc lớp chưa được weaving | Phát hiện được đường không áp advice |
| Có nhiều aspect lồng nhau | Thứ tự và nguồn kết quả/lỗi rõ ràng |

### 12.1. Cách chẩn đoán khi advice nhận sai giá trị

1. **Xác nhận join point:** phương thức/điểm thực thi nào thực sự được chọn?
2. **Xác nhận chữ ký:** tên, số lượng và thứ tự kiểu tham số; có overload hoặc bridge method không?
3. **Xác nhận dữ liệu được cấp:** `Method`, `args`, target hoặc metadata thuộc phía nào?
4. **Xác nhận kiểu runtime:** `null`, boxed primitive, subclass, proxy hoặc generic erasure có liên quan không?
5. **Xác nhận binding:** ánh xạ từng vị trí nguồn vào tham số advice, có nhầm hai biến cùng kiểu không?
6. **Xác nhận nhánh thực thi:** lời gọi đã hoàn tất hay ném lỗi, có around advice khác chặn hoặc biến đổi không?
7. **Xác nhận đồng thời:** dữ liệu nằm trong tham số cục bộ hay bị lưu vào trạng thái dùng chung?
8. **Xác nhận đường kết hợp:** artifact/lớp đã weaving hoặc người gọi có thật sự đi qua proxy?
9. **Kiểm thử cả ca không khớp:** advice không được áp nhầm nơi ngoài phạm vi.
10. **Kiểm tra dữ liệu nhạy cảm:** log có vô tình ghi thông tin riêng tư hay token không?

## 13. Sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi `args` là chữ ký phương thức | Lẫn kiểu runtime với kiểu khai báo | Chọn đúng chữ ký trước, ràng buộc đối số sau |
| Nhầm tên biến advice với tên tham số ở mã nguồn đích | Tưởng binding tự động theo tên | Khai báo ánh xạ thật theo cú pháp công nghệ |
| Hoán đổi hai đối số cùng kiểu | Dữ liệu ghi sai nhưng vẫn chạy | Test dữ liệu khác nhau ở từng vị trí |
| Đọc kết quả trong advice trước lời gọi | Dùng dữ liệu chưa tồn tại | Dùng after-returning hoặc after `proceed` |
| Đọc ngoại lệ như một kết quả thành công | Sai trạng thái | Phân biệt đường throw và return |
| Gọi `proceed` nhiều lần để đo thời gian | Nhân đôi tác dụng phụ | Giữ một lần chuyển tiếp nếu chỉ quan sát |
| Lưu mã yêu cầu trong field aspect dùng chung | Lẫn dữ liệu giữa luồng | Dùng biến theo lần gọi hoặc cơ chế propagation đúng |
| Tự đọc target để lấy thêm dữ liệu | Có thể tạo join point mới hoặc cạnh tranh đồng thời | Ưu tiên dữ kiện đã cấp; giới hạn lời gọi phụ |
| Dùng dữ liệu request chưa kiểm chứng để phân quyền | Có thể cho phép truy cập sai | Dùng định danh đã xác minh và ranh giới an toàn |
| Tin rằng binding đúng thì advice chắc chắn chạy | Quên phạm vi weaving/proxy | Kiểm chứng đường thực thi thực |
| Log toàn bộ đối số khi debugging | Rò rỉ dữ liệu riêng tư | Chọn trường tối thiểu và che thông tin nhạy cảm |

## 14. Bài tập vận dụng

### Bài 1 — Ràng buộc hai giá trị cùng kiểu

Cho phương thức `transfer(String from, String to, long amount)`. Advice muốn ghi `source` và `destination`. Nếu vô tình ánh xạ vị trí 0 vào `destination` và vị trí 1 vào `source`, compiler Java có bắt được không?

**Đáp án:** Không nhất thiết, vì cả hai đều là `String`. Mã có thể hợp lệ nhưng ghi thông tin đảo chiều. Cần kiểm thử với hai giá trị khác nhau, kiểm tra mapping theo vị trí và giữ hợp đồng tên biến rõ.

### Bài 2 — Kết quả và ngoại lệ

Một advice muốn ghi “SUCCESS” với mã trả về hoặc “FAILURE” với loại lỗi. Có thể lấy cùng một biến kết quả trước khi đích chạy cho cả hai nhánh không?

**Đáp án:** Không. Giá trị trả về thành công chỉ có sau khi thao tác hoàn tất bình thường; ngoại lệ chỉ có khi đường thực thi ném lỗi. Cần dùng ngữ nghĩa after-returning/after-throwing hoặc around xử lý hai nhánh sau khi chuyển tiếp.

### Bài 3 — Proxy và kiểu

Một interface có `ship(String,int)` và `ship(Object,int)`. Người gọi thực thi `ship((Object) "SO-1", 2)`. Nếu pointcut chọn chữ ký `ship(String,int)`, có khớp không?

**Đáp án:** Không: overload đã chọn có tham số đầu khai báo là `Object`, dù đối tượng runtime là `String`. Chọn theo giá trị runtime và theo chữ ký là hai yêu cầu khác nhau.

### Bài 4 — An toàn đồng thời

Một aspect dùng field `currentOrderId` để advice before ghi mã đơn, advice after đọc field đó. Khi hai luồng gọi đồng thời, kết quả có chắc đúng không?

**Đáp án:** Không. Trạng thái chung có thể bị ghi đè. Cần giữ dữ kiện theo từng lần gọi, truyền qua tham số advice hoặc dùng cơ chế bối cảnh có vòng đời và an toàn đồng thời phù hợp.

### Bài 5 — `this` và `target`

Trong một mô hình có method-call join point, mã của `Checkout` gọi `PaymentGateway.charge()`. Vì sao đối tượng `this` và target có thể khác nhau?

**Đáp án:** Ngữ cảnh phía mã phát sinh lời gọi thuộc `Checkout`, còn đối tượng nhận thao tác là `PaymentGateway`. Ngữ nghĩa chính xác phụ thuộc mô hình join point và cơ chế AOP, nên phải xác minh bằng công cụ đang dùng.

### Bài 6 — Around advice

Advice chỉ có nhiệm vụ đo thời lượng nhưng gọi `proceed` hai lần để “đo lại”. Rủi ro là gì?

**Đáp án:** Đích có thể chạy hai lần, tạo đơn hàng, chuyển tiền hoặc cập nhật trạng thái trùng lặp. Với advice chỉ quan sát, nên chuyển tiếp một lần và giữ nguyên kết quả/ngoại lệ.

### Bài 7 — Dữ liệu tin cậy

Một advice được ràng buộc với `accountId` từ lời gọi `withdraw(accountId, amount)`. Có thể mặc định rằng người dùng hiện tại sở hữu tài khoản đó không?

**Đáp án:** Không. Binding chỉ đưa giá trị được truyền vào advice; tính xác thực và quyền sở hữu cần được kiểm tra bằng danh tính và trạng thái đáng tin cậy tại ranh giới nghiệp vụ/bảo mật thích hợp.

## 15. Ghi nhớ

- **Binding** đưa dữ kiện tại join point vào các biến có tên/kiểu mà advice sử dụng; **pointcut** quyết định điểm nào được chọn.
- Những ngữ cảnh thường gặp gồm **đối số, `this`, `target`, metadata, giá trị trả về và ngoại lệ**; không phải công nghệ AOP nào cũng hỗ trợ hết.
- **Kiểu khai báo, kiểu runtime và vị trí đối số** khác nhau; phải kiểm tra overload, `null`, primitive boxing và các đối tượng có thể thay đổi.
- **Kết quả/lỗi chỉ khả dụng ở nhánh tương ứng**. Around advice phải chuyển tiếp đúng theo hợp đồng để tránh biến đổi hành vi nghiệp vụ ngoài ý định.
- Biến ràng buộc nên gắn với **mỗi lần advice chạy**, không dựa vào field dùng chung để lưu ngữ cảnh từng yêu cầu.
- Binding không tự chứng thực dữ liệu, truyền dữ liệu qua luồng bất đồng bộ hay bảo đảm mọi đường gọi đều được weaving.
- Khi thiết kế pointcut theo ngữ cảnh, hãy kiểm thử **đúng giá trị, đúng kiểu, đúng thời điểm, đúng số lần và đúng phạm vi**.
