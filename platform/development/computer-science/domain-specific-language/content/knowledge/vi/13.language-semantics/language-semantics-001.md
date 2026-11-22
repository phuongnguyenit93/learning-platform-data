# Ngữ nghĩa tĩnh

## 1. Ngữ nghĩa tĩnh trong một DSL là gì?

Ngữ nghĩa tĩnh (static semantics) là tập hợp các quy tắc xác định một chương trình có hợp lệ về mặt ý nghĩa trước khi được thực thi hay không. Những quy tắc này được kiểm tra trên mã nguồn, cây cú pháp hoặc mô hình chương trình đã phân tích. Chúng bổ sung cho ngữ pháp cú pháp: một đoạn mã có thể đúng cấu trúc nhưng vẫn không có ý nghĩa hợp lệ trong miền của ngôn ngữ.

Ví dụ, một DSL quy tắc có thể cho phép cú pháp:

~~~text
rule large-order {
    when order.total > 10000000
    then require_manual_review()
}
~~~

Đoạn mã có thể đúng grammar, nhưng vẫn có những câu hỏi cần kiểm tra:

- Biến order có được khai báo trong phạm vi hiện tại không?
- order có phải là một kiểu dữ liệu có thuộc tính total không?
- total có phải là số có thể so sánh với số nguyên 10000000 không?
- Hàm require_manual_review có tồn tại và có thể gọi trong ngữ cảnh này không?
- Rule large-order có bị khai báo trùng tên không?
- Hành động có trả về kiểu phù hợp với vị trí được dùng không?

Các câu hỏi này thuộc ngữ nghĩa tĩnh. Chúng thường được giải quyết trước khi chương trình chạy, trong giai đoạn phân tích, kiểm tra kiểu hoặc biên dịch.

Ngữ nghĩa tĩnh đặc biệt quan trọng với DSL vì ngôn ngữ thường biểu diễn các quy tắc nghiệp vụ, cấu hình hạ tầng, truy vấn hoặc workflow. Một lỗi nhỏ như dùng sai đơn vị tiền tệ, tham chiếu nhầm thuộc tính hay gọi một hành động không tồn tại có thể dẫn đến kết quả sai trong hệ thống thực tế.

## 2. Phân biệt cú pháp, ngữ nghĩa tĩnh và ngữ nghĩa động

Ba khái niệm này trả lời ba câu hỏi khác nhau:

| Khía cạnh | Câu hỏi | Ví dụ |
|---|---|---|
| Cú pháp (syntax) | Chương trình có được viết theo cấu trúc mà grammar cho phép không? | Một khối rule có đủ dấu ngoặc và từ khóa không? |
| Ngữ nghĩa tĩnh (static semantics) | Các thành phần trong chương trình có được dùng hợp lệ theo quy tắc của ngôn ngữ không? | Biến có được khai báo, kiểu dữ liệu có tương thích không? |
| Ngữ nghĩa động (dynamic semantics) | Khi thực thi, chương trình tạo ra hành vi và kết quả gì? | Rule có được kích hoạt khi đơn hàng đạt ngưỡng không? |

Ví dụ:

~~~text
let quantity: Integer = "three";
~~~

Nếu grammar cho phép khai báo biến và literal chuỗi ở vị trí này, câu lệnh có thể đúng cú pháp. Tuy nhiên, nó vi phạm ngữ nghĩa tĩnh nếu Integer không thể nhận giá trị kiểu String. Chương trình cần bị từ chối trước khi thực thi.

Một ví dụ khác:

~~~text
let quantity: Integer = 3;
let available: Integer = 0;
let average = quantity / available;
~~~

Các biến và phép chia có thể hợp lệ về kiểu, do đó vượt qua kiểm tra tĩnh. Nhưng khi chạy, phép chia cho 0 có thể gây lỗi. Đây là vấn đề ngữ nghĩa động vì nó phụ thuộc giá trị thực tế tại thời điểm thực thi.

Ranh giới không phải lúc nào cũng tuyệt đối. Một số ngôn ngữ có thể kiểm tra phép chia cho 0 khi mẫu số là hằng số đã biết, trong khi vẫn cần kiểm tra lúc chạy nếu giá trị đến từ dữ liệu bên ngoài. Điểm cốt lõi là ngữ nghĩa tĩnh kiểm tra những thuộc tính có thể xác định từ chương trình và thông tin sẵn có trước khi thực thi.

## 3. Những quy tắc thường thuộc ngữ nghĩa tĩnh

Một DSL có thể định nghĩa nhiều loại quy tắc tĩnh:

| Nhóm quy tắc | Nội dung kiểm tra | Ví dụ |
|---|---|---|
| Khai báo và định danh | Tên phải được khai báo, không trùng trong phạm vi cấm trùng | Không tham chiếu biến chưa tồn tại |
| Phạm vi (scope) | Tên chỉ được sử dụng ở nơi nó có hiệu lực | Biến cục bộ không được dùng ngoài block |
| Hệ kiểu (type system) | Kiểu của biểu thức phù hợp với vị trí sử dụng | Không cộng String với Money |
| Chữ ký hàm | Số lượng và kiểu tham số phù hợp | Hàm nhận Region không thể nhận Order |
| Quy tắc miền có thể kiểm tra trước | Giá trị khai báo hoặc cấu trúc tĩnh đáp ứng giới hạn | Không khai báo hai rule có cùng định danh |
| Tính đầy đủ cấu trúc | Các trường hoặc nhánh bắt buộc đã được cung cấp | Action bắt buộc phải có destination |
| Quyền và khả năng | Thành phần chỉ được gọi trong ngữ cảnh được phép | Hàm truy cập dữ liệu nhạy cảm chỉ dùng trong policy được cấp quyền |

Không phải mọi quy tắc nghiệp vụ đều có thể kiểm tra tĩnh. Ví dụ, một tài khoản có đủ số dư hay không thường phụ thuộc dữ liệu runtime. Nhưng ngôn ngữ có thể kiểm tra trước rằng biểu thức số dư được so sánh với một giá trị tiền tệ cùng loại.

## 4. Phân giải tên và phạm vi

### 4.1. Phân giải tên là gì?

Phân giải tên (name resolution) là quá trình xác định một tên trong chương trình đang tham chiếu tới khai báo nào. Khi gặp một tên như order, customer hoặc calculateFee, bộ phân tích cần tìm đúng biến, hàm, kiểu, module hoặc thuộc tính tương ứng.

Ví dụ:

~~~text
let threshold: Money<VND> = money(5000000, VND);

rule review-order {
    when order.total > threshold
    then require_manual_review()
}
~~~

Trong rule, threshold phải được phân giải về khai báo ở phạm vi có thể truy cập. Nếu không có khai báo đó, chương trình có lỗi tên chưa xác định (undefined name).

### 4.2. Phạm vi (scope)

Scope xác định nơi một tên có hiệu lực. DSL có thể có:

- Global scope: khai báo dùng được trong toàn bộ chương trình hoặc module.
- Module scope: khai báo chỉ được nhìn thấy trong module.
- Block scope: khai báo có hiệu lực trong một khối.
- Function scope: tham số và biến cục bộ chỉ tồn tại trong hàm.
- Scope của rule hoặc workflow: các biến ngữ cảnh chỉ tồn tại trong một rule hay bước xử lý.

Ví dụ:

~~~text
let currency = VND;

rule domestic-order {
    let threshold = money(1000000, currency);
    when order.total > threshold
    then approve()
}

rule international-order {
    when order.total > threshold
    then request_review()
}
~~~

Nếu threshold chỉ được khai báo trong scope của domestic-order, rule international-order không thể sử dụng tên đó. Một trình kiểm tra tĩnh cần phát hiện lỗi này thay vì chờ đến khi rule được kích hoạt.

### 4.3. Che khuất tên và khai báo trùng

Một số ngôn ngữ cho phép khai báo tên bên trong scope con che khuất (shadow) tên ở scope cha:

~~~text
let limit = 100;

rule special-case {
    let limit = 50;
    when order.quantity > limit
    then request_review()
}
~~~

Trong rule special-case, limit có thể tham chiếu tới giá trị 50. Nếu DSL cho phép shadowing, quy tắc này phải được tài liệu hóa rõ ràng. Nếu không cho phép, checker cần báo lỗi khai báo trùng hoặc che khuất không hợp lệ.

Không nên để kết quả phân giải tên phụ thuộc thứ tự duyệt file một cách ngầm định. Nếu DSL hỗ trợ nhiều module, cần quy định cách import, namespace, alias, thứ tự tìm kiếm và xử lý vòng phụ thuộc.

## 5. Hệ kiểu và kiểm tra kiểu

### 5.1. Kiểu dữ liệu giúp ngăn biểu thức vô nghĩa

Hệ kiểu (type system) quy định những giá trị nào có thể được sử dụng ở mỗi vị trí và những phép toán nào hợp lệ. Nó giúp phát hiện sớm các lỗi như:

- Cộng một ngày với một địa chỉ.
- So sánh tiền VND với tiền USD mà không có chuyển đổi.
- Gọi hàm với thiếu hoặc sai kiểu tham số.
- Gán kết quả có thể rỗng vào biến bắt buộc có giá trị.
- Dùng một hành động ở vị trí cần một biểu thức trả về Boolean.

Ví dụ DSL:

~~~text
let quantity: Integer = 3;
let unitPrice: Money<VND> = money(120000, VND);
let total: Money<VND> = quantity * unitPrice;

when total > money(500000, VND) {
    require_manual_review();
}
~~~

Checker có thể xác nhận:

- quantity có kiểu Integer.
- unitPrice có kiểu Money<VND>.
- Phép nhân Integer với Money<VND> trả về Money<VND>.
- Hai vế của phép so sánh đều là Money<VND>.
- Điều kiện của when có kiểu Boolean.

Nếu thay literal cuối bằng money(500000, USD), chương trình phải bị từ chối hoặc yêu cầu một phép chuyển đổi tiền tệ được khai báo rõ.

### 5.2. Quy tắc kiểu có thể mô tả bằng phán đoán

Trong lý thuyết kiểu, một phán đoán thường được viết dưới dạng:

\[
\Gamma \vdash e : T
\]

Ký hiệu này có nghĩa: trong môi trường khai báo Γ, biểu thức e có kiểu T. Môi trường Γ chứa thông tin về biến, hàm, kiểu và các khai báo đang có hiệu lực.

Ví dụ, nếu Γ cho biết quantity có kiểu Integer và unitPrice có kiểu Money<VND>, một quy tắc kiểu có thể suy ra:

\[
\frac{
  \Gamma \vdash quantity : Integer
  \qquad
  \Gamma \vdash unitPrice : Money<VND>
}{
  \Gamma \vdash quantity \times unitPrice : Money<VND>
}
\]

Quy tắc này minh họa phép nhân số lượng với đơn giá tạo ra một giá trị tiền cùng loại tiền tệ. Một DSL thực tế có thể có hệ kiểu đơn giản hơn hoặc phong phú hơn, nhưng cần định nghĩa nhất quán cách suy ra kiểu cho từng biểu thức.

### 5.3. Kiểu tĩnh và kiểu động

Trong ngôn ngữ có kiểu tĩnh, kiểu của biểu thức được xác định hoặc kiểm tra trước khi chạy. Trong ngôn ngữ có kiểu động, nhiều lỗi kiểu chỉ xuất hiện khi chương trình thực thi.

| Cách tiếp cận | Đặc điểm | Ưu điểm | Đánh đổi |
|---|---|---|---|
| Kiểu tĩnh | Kiểm tra kiểu trước khi chạy | Phát hiện sớm, hỗ trợ IDE và tối ưu hóa | Có thể cần khai báo kiểu hoặc quy tắc suy luận |
| Kiểu động | Kiểm tra kiểu trong khi chạy | Linh hoạt với dữ liệu và cấu trúc thay đổi | Một số lỗi chỉ xuất hiện khi đi vào nhánh thực thi |
| Kiểu dần (gradual typing) | Kết hợp vùng có kiểu tĩnh và vùng linh hoạt | Cho phép chuyển đổi từng phần | Cần quy định kiểm tra ở ranh giới giữa hai vùng |

DSL cấu hình nghiệp vụ thường có lợi khi dùng kiểu tĩnh cho những khái niệm cốt lõi như tiền, ngày, định danh, trạng thái và kết quả điều kiện. Một số dữ liệu đầu vào vẫn có thể chỉ biết kiểu cụ thể khi chạy; khi đó cần kiểm tra runtime tại ranh giới nhận dữ liệu.

## 6. Suy luận kiểu và kiểu biểu thức

Không phải DSL nào cũng yêu cầu người viết khai báo kiểu ở mọi biến. Trình kiểm tra có thể suy luận kiểu (type inference) từ biểu thức gán hoặc ngữ cảnh sử dụng.

Ví dụ:

~~~text
let quantity = 3;
let unitPrice = money(120000, VND);
let total = quantity * unitPrice;
~~~

Nếu literal 3 được suy ra là Integer, money(...) trả về Money<VND>, và phép nhân có quy tắc đã định, checker có thể suy ra total có kiểu Money<VND>.

Suy luận kiểu giúp DSL ngắn gọn, nhưng không nên khiến kiểu trở nên khó đoán. Khi không đủ thông tin, compiler cần báo rằng không thể suy luận kiểu thay vì tự chọn một kiểu không an toàn.

Ví dụ:

~~~text
let result = empty();
~~~

Nếu empty() có thể trả về một danh sách thuộc bất kỳ kiểu phần tử nào, checker không thể xác định kiểu danh sách chỉ từ lời gọi này. Người dùng có thể cần khai báo kiểu rõ ràng:

~~~text
let result: List<Order> = empty();
~~~

### 6.1. Kiểm tra biểu thức theo ngữ cảnh

Một số biểu thức có thể được kiểm tra dựa trên kiểu mà ngữ cảnh yêu cầu. Ví dụ, một lambda có thể suy ra kiểu tham số từ hàm nhận lambda:

~~~text
orders.filter(order => order.status == "PAID")
~~~

Nếu filter nhận một hàm Order -> Boolean, checker có thể suy ra order có kiểu Order và biểu thức so sánh trả về Boolean.

Ngược lại, khi có nhiều overload hoặc nhiều kiểu ứng viên, checker cần quy tắc chọn rõ ràng. Nếu không thể chọn duy nhất, nên yêu cầu chú thích kiểu hoặc báo lỗi mơ hồ.

## 7. Kiểm tra chữ ký hàm và overload

Hàm trong DSL có một chữ ký gồm tên, số lượng tham số, kiểu tham số và kiểu trả về. Static checker cần xác nhận lời gọi phù hợp với một chữ ký hợp lệ.

Ví dụ:

~~~text
function isEligible(customer: Customer): Boolean;
function calculateFee(order: Order): Money<VND>;

let eligible = isEligible(currentCustomer);
let fee = calculateFee(currentOrder);
~~~

Nếu người dùng viết calculateFee(currentCustomer), checker phát hiện đối số Customer không tương thích với tham số Order.

DSL có thể hỗ trợ overload, tức nhiều hàm cùng tên nhưng có chữ ký khác nhau:

~~~text
function format(value: Date): String;
function format(value: Money): String;
~~~

Khi gặp format(order.createdAt), checker chọn overload nhận Date nếu kiểu của createdAt là Date. Nếu có nhiều overload phù hợp như nhau, chương trình có lỗi lời gọi mơ hồ.

Quy tắc overload cần xác định:

- Có cho phép chuyển kiểu ngầm định không?
- Chuyển kiểu nào được xem là an toàn?
- Có ưu tiên kiểu chính xác hơn kiểu cha không?
- Giá trị null có thể khớp nhiều overload không?
- Generic type được suy luận từ tham số và kiểu trả về ra sao?

Chuyển kiểu ngầm định quá rộng có thể che giấu lỗi. Với DSL miền nghiệp vụ, thường nên yêu cầu chuyển đổi tường minh đối với các đại lượng quan trọng như tiền tệ, múi giờ hoặc đơn vị đo.

## 8. Kiểm tra thuộc tính và cấu trúc miền

Ngoài kiểu cơ bản, DSL thường có kiểu miền như Order, Customer, Product, Region hoặc Money. Ngữ nghĩa tĩnh có thể kiểm tra thành phần nào được truy cập và cấu trúc nào bắt buộc.

Ví dụ:

~~~text
when order.customer.status == "ACTIVE"
    and order.total > money(1000000, VND)
then approve()
~~~

Checker cần biết:

- order có kiểu Order.
- Order có thuộc tính customer và total.
- customer có thuộc tính status.
- status có kiểu có thể so sánh với String hoặc enum tương ứng.
- total có kiểu Money<VND>.
- approve() có thể gọi trong vị trí hành động.

Nếu DSL dùng schema để định nghĩa cấu trúc, checker có thể tải schema và kiểm tra đường dẫn thuộc tính. Khi schema thay đổi, cần có phiên bản schema hoặc chính sách tương thích để chương trình cũ không bị diễn giải khác ngoài dự kiến.

### 8.1. Ràng buộc miền tĩnh

Một số điều kiện nghiệp vụ có thể kiểm tra trước vì giá trị đã biết trong chương trình:

~~~text
policy "domestic-shipping" {
    allowedRegions = ["NORTH", "CENTRAL", "SOUTH"];
    defaultRegion = "MOON";
}
~~~

Nếu checker biết tập giá trị hợp lệ của Region, nó có thể phát hiện defaultRegion không thuộc tập cho phép. Ngược lại, nếu region đến từ yêu cầu API lúc chạy, việc kiểm tra giá trị thực tế phải diễn ra runtime.

Ranh giới giữa static validation và runtime validation phụ thuộc dữ liệu có sẵn ở thời điểm kiểm tra. Không nên gọi một quy tắc là tĩnh nếu kết quả của nó phụ thuộc vào dữ liệu thay đổi mà compiler không thể biết.

## 9. Các bước kiểm tra tĩnh trong pipeline xử lý DSL

Một pipeline thường có thể được tổ chức như sau:

~~~mermaid
flowchart TD
    A["Mã nguồn"] --> B["Lexer"]
    B --> C["Parser"]
    C --> D["AST"]
    D --> E["Name resolution"]
    E --> F["Type checking"]
    F --> G["Static validation"]
    G --> H["IR / Code generation"]
    H --> I["Runtime"]
~~~

Các bước chính:

1. **Lexer:** nhận diện token và vị trí nguồn.
2. **Parser:** kiểm tra cấu trúc theo grammar và tạo AST.
3. **Name resolution:** tìm khai báo tương ứng với mỗi tên.
4. **Type checking:** suy luận và kiểm tra kiểu của biểu thức.
5. **Static validation:** kiểm tra ràng buộc miền và quy tắc cấu trúc có thể xác định trước khi chạy.
6. **IR hoặc code generation:** tạo biểu diễn trung gian hoặc mã đích nếu chương trình hợp lệ.

Thứ tự cụ thể có thể khác. Ví dụ, parser có thể xây dựng một phần symbol table trong lúc đọc, còn kiểm tra kiểu có thể cần thông tin từ nhiều module. Một số compiler thực hiện nhiều vòng phân tích để xử lý khai báo tiến về phía trước hoặc phụ thuộc giữa module.

Điều quan trọng là các giai đoạn phải có hợp đồng rõ: lỗi cú pháp, lỗi tên, lỗi kiểu và lỗi ràng buộc tĩnh cần được phân loại và báo đúng nguồn.

## 10. Symbol table và môi trường kiểm tra

Symbol table là cấu trúc dữ liệu lưu thông tin về các định danh đã khai báo. Nó có thể chứa:

- Tên biến, hàm, kiểu hoặc module.
- Kiểu dữ liệu và chữ ký.
- Scope hoặc namespace.
- Vị trí khai báo trong mã nguồn.
- Quyền truy cập hoặc trạng thái export.
- Metadata phục vụ kiểm tra và gợi ý IDE.

Ví dụ mô hình đơn giản:

~~~java
public record Symbol(
        String name,
        Type type,
        SymbolKind kind,
        SourceLocation declarationLocation) {
}

public enum SymbolKind {
    VARIABLE,
    FUNCTION,
    TYPE,
    MODULE
}
~~~

Khi checker gặp một identifier, nó tra symbol table theo scope hiện tại rồi lần lượt tìm scope cha hoặc namespace đã import theo quy tắc của DSL. Nếu không tìm thấy, nó tạo diagnostic về tên chưa khai báo.

Với DSL nhiều module, symbol table có thể được chia theo module và liên kết qua import graph. Cần phát hiện import vòng nếu ngôn ngữ không cho phép, đồng thời xác định cách xử lý khi hai module export cùng một tên.

## 11. Chẩn đoán lỗi ngữ nghĩa tĩnh

Một checker tốt không chỉ nói chương trình sai mà còn giúp người viết tìm đúng vị trí và cách sửa.

Một diagnostic thường có:

- Mã lỗi ổn định.
- Mức độ: error, warning hoặc info.
- Thông điệp ngắn gọn.
- Vị trí bắt đầu và kết thúc trong mã nguồn.
- Ngữ cảnh hoặc tên symbol liên quan.
- Gợi ý sửa nếu có thể.

Ví dụ:

~~~text
ERROR DSL-TYPE-014: Cannot compare Money<VND> with Money<USD>.
  at rules/discount.dsl:12:18
  Expression: order.total > money(100, USD)
  Hint: Convert currencies explicitly or compare values with the same currency.
~~~

Thông báo chỉ rõ lỗi kiểu, vị trí và hướng khắc phục. Nó hữu ích hơn một lỗi chung chung như Invalid expression.

### 11.1. Error, warning và lint

Không phải mọi vấn đề đều phải làm chương trình thất bại:

| Mức độ | Ý nghĩa | Ví dụ |
|---|---|---|
| Error | Chương trình không hợp lệ và không thể tiếp tục compile theo hợp đồng | Tên hàm không tồn tại, sai kiểu |
| Warning | Chương trình hợp lệ nhưng có nguy cơ hoặc dùng cấu trúc sắp bị loại bỏ | Dùng cú pháp deprecated |
| Info | Gợi ý giúp mã rõ ràng hơn | Biểu thức có thể viết ngắn hơn |
| Lint | Quy tắc chất lượng hoặc phong cách của nhóm | Tên rule không theo quy ước |

Ngữ nghĩa tĩnh nên tập trung vào tính hợp lệ theo ngôn ngữ. Lint có thể bổ sung quy tắc phong cách và khuyến nghị. Nếu trộn tất cả thành lỗi bắt buộc, người dùng khó phân biệt lỗi thực sự với sở thích định dạng của nhóm.

### 11.2. Nhiều lỗi và phục hồi sau lỗi

Một compiler có thể phát hiện nhiều lỗi trong một lần kiểm tra thay vì dừng ngay ở lỗi đầu tiên. Tuy nhiên, sau một lỗi cú pháp hoặc lỗi phân giải tên, các bước sau có thể thiếu thông tin để kiểm tra tiếp.

Checker có thể dùng kiểu lỗi nội bộ hoặc unknown type để tiếp tục phân tích phần còn lại mà không tạo hàng loạt lỗi dây chuyền. Ví dụ, nếu customer không được khai báo, checker không nên phát thêm nhiều lỗi gây nhiễu cho mọi thuộc tính phía sau như customer.name, customer.email và customer.status.

## 12. Giới hạn của kiểm tra tĩnh

Kiểm tra tĩnh không thể biết mọi giá trị và mọi tình huống runtime. Một chương trình hợp lệ về ngữ nghĩa tĩnh vẫn có thể thất bại khi chạy do:

- Dữ liệu đầu vào không thỏa điều kiện nghiệp vụ.
- Dịch vụ bên ngoài không sẵn sàng.
- Tệp hoặc tài nguyên không tồn tại.
- Quyền truy cập thực tế bị từ chối.
- Xung đột đồng thời hoặc timeout.
- Một phép tính hợp lệ về kiểu nhưng không hợp lệ với giá trị cụ thể.

Ví dụ, checker có thể xác nhận order.customerId có kiểu CustomerId và hàm loadCustomer nhận CustomerId. Nó không thể đảm bảo khách hàng đó tồn tại trong cơ sở dữ liệu tại thời điểm chạy.

Vì vậy, kiểm tra tĩnh và kiểm tra runtime bổ sung cho nhau:

- Kiểm tra tĩnh phát hiện sớm lỗi có thể suy ra từ chương trình và schema.
- Kiểm tra runtime xác nhận dữ liệu và điều kiện thực tế.
- Ràng buộc ở tầng lưu trữ bảo vệ dữ liệu trước các đường ghi và tranh chấp.
- Quy trình vận hành ghi nhận lỗi không thể phát hiện trước khi chạy.

Không nên hứa rằng một chương trình vượt qua static checker là chắc chắn chạy thành công hoặc an toàn trong mọi môi trường.

## 13. Thiết kế ngữ nghĩa tĩnh cho một DSL mới

Khi xây dựng DSL, cần xác định rõ những gì được kiểm tra trước khi chạy:

1. **Định nghĩa namespace và scope.** Tên được khai báo ở đâu, có thể import thế nào và có cho phép shadowing không?
2. **Xây dựng mô hình kiểu.** Có kiểu nguyên thủy, kiểu miền, generic, nullable hay union type không?
3. **Định nghĩa quy tắc biểu thức.** Mỗi toán tử nhận kiểu nào và trả về kiểu nào?
4. **Quy định chuyển kiểu.** Chuyển kiểu nào tự động, chuyển kiểu nào phải tường minh?
5. **Định nghĩa chữ ký hàm.** Tham số, kiểu trả về, overload và generic được xử lý thế nào?
6. **Chọn ràng buộc miền có thể kiểm tra tĩnh.** Phân biệt dữ liệu khai báo trước với dữ liệu chỉ biết lúc chạy.
7. **Xây dựng symbol table và checker.** Giữ thông tin vị trí nguồn để báo lỗi chính xác.
8. **Thiết kế diagnostics.** Mã lỗi, mức độ, thông điệp và gợi ý cần nhất quán.
9. **Tạo bộ kiểm thử.** Bao gồm chương trình hợp lệ, chương trình sai cú pháp, sai tên, sai kiểu và trường hợp biên.
10. **Tài liệu hóa hợp đồng.** Nêu rõ điều kiện nào được kiểm tra trước khi chạy và điều kiện nào được xác nhận trong runtime.

Ví dụ, nếu DSL dùng cho định giá, hệ kiểu có thể phân biệt Money<VND>, Money<USD>, Percentage và Quantity. Khi đó checker có thể phát hiện phép cộng giữa phần trăm và tiền, hoặc so sánh hai loại tiền khác nhau, trước khi chương trình được triển khai.

## 14. Kiểm thử bộ kiểm tra tĩnh

Static checker cần được kiểm thử bằng cả chương trình hợp lệ và không hợp lệ. Mỗi quy tắc nên có ví dụ làm đúng và ví dụ vi phạm:

~~~text
# Hợp lệ: hai vế cùng kiểu tiền
let total: Money<VND> = money(500000, VND);
when total > money(100000, VND) {
    approve();
}

# Không hợp lệ: so sánh hai loại tiền khác nhau
when total > money(100, USD) {
    approve();
}
~~~

Các nhóm kiểm thử thường dùng:

- Unit test cho từng quy tắc phân giải tên và suy luận kiểu.
- Golden test cho diagnostic, vị trí dòng/cột và gợi ý sửa.
- Test tích hợp cho import, namespace và phụ thuộc giữa module.
- Test hồi quy cho những lỗi checker từng xử lý sai.
- Property-based test cho các biểu thức và tổ hợp kiểu được sinh tự động.
- Test hiệu năng với chương trình lớn hoặc nhiều module.

Khi thay đổi grammar hoặc hệ kiểu, cần kiểm tra các chương trình đã hợp lệ trước đó có còn được chấp nhận theo chính sách tương thích hay không. Một checker thay đổi có thể vô tình từ chối chương trình hợp lệ hoặc chấp nhận chương trình sai.

## 15. Những lỗi thiết kế thường gặp

### Chỉ kiểm tra cú pháp

Một chương trình parse thành công chưa chắc có ý nghĩa. Nếu không có name resolution và type checking, nhiều lỗi chỉ xuất hiện khi rule được thực thi. Hãy xác định các quy tắc tĩnh tối thiểu của miền.

### Dùng kiểu quá tổng quát

Nếu mọi giá trị đều được xem là Object hoặc String, checker khó phát hiện lỗi đơn vị, tiền tệ và kiểu miền. Dùng kiểu cụ thể cho các khái niệm quan trọng.

### Chuyển kiểu ngầm định quá rộng

Tự động chuyển String thành số hoặc USD thành VND mà không có tỷ giá có thể che giấu lỗi. Chỉ cho phép chuyển đổi khi có quy tắc rõ và không làm mất ý nghĩa.

### Không xác định scope và thứ tự phân giải

Nếu cùng một tên có thể trỏ đến nhiều khai báo mà không có quy tắc ưu tiên rõ ràng, chương trình trở nên khó dự đoán. Cần quy định namespace, import, shadowing và duplicate declaration.

### Nhầm static validation với runtime validation

Checker không thể đảm bảo một bản ghi bên ngoài sẽ tồn tại hoặc một dịch vụ sẽ phản hồi. Hãy phân chia trách nhiệm theo thời điểm có dữ liệu.

### Diagnostic khó hiểu

Thông báo lỗi không có vị trí hoặc chỉ nêu sai cú pháp làm người dùng khó sửa. Hãy gắn lỗi với source span, mã lỗi ổn định và ngữ cảnh biểu thức.

### Tạo quá nhiều lỗi dây chuyền

Một lỗi chưa khai báo có thể kéo theo hàng loạt lỗi kiểu giả. Checker cần cơ chế phục hồi và kiểu unknown để giảm nhiễu.

## 16. Kết luận

Ngữ nghĩa tĩnh xác định những điều kiện mà chương trình DSL phải thỏa mãn trước khi thực thi. Nó bao gồm phân giải tên, phạm vi, kiểm tra kiểu, chữ ký hàm, cấu trúc miền và các ràng buộc có thể xác định từ mã nguồn cùng metadata sẵn có. Nhờ đó, nhiều lỗi được phát hiện sớm và người viết nhận được chẩn đoán ngay tại vị trí gây ra vấn đề.

Một thiết kế tốt cần phân biệt cú pháp, ngữ nghĩa tĩnh và ngữ nghĩa động; định nghĩa hệ kiểu và scope nhất quán; tổ chức pipeline phân tích rõ ràng; đồng thời cung cấp thông báo lỗi có vị trí và mã ổn định. Kiểm tra tĩnh không thay thế kiểm tra runtime, vì dữ liệu và môi trường thực tế chỉ được biết khi chương trình chạy.

Khi thiết kế một DSL, hãy tự hỏi: những lỗi nào có thể phát hiện từ chương trình trước khi chạy, thông tin nào cần để chứng minh tính hợp lệ, và điều gì vẫn phải kiểm tra ở runtime? Trả lời rõ các câu hỏi này giúp ngôn ngữ vừa an toàn, dễ hiểu vừa phù hợp với miền bài toán.
