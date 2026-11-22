# So sánh khả năng biểu đạt

## DSL nội bộ và DSL bên ngoài

Trong thiết kế ngôn ngữ chuyên miền (domain-specific language, DSL), có hai cách tổ chức phổ biến: xây dựng ngôn ngữ ngay bên trong một ngôn ngữ lập trình có sẵn hoặc tạo một ngôn ngữ có cú pháp riêng. Cách thứ nhất thường được gọi là **DSL nội bộ** (internal DSL, embedded DSL); cách thứ hai là **DSL bên ngoài** (external DSL).

Hai cách tiếp cận đều nhằm giúp người dùng diễn đạt khái niệm và quy tắc của một miền vấn đề. Điểm khác biệt nằm ở nơi cú pháp được định nghĩa, cách chương trình được phân tích và mức độ tự do khi thiết kế cách diễn đạt. DSL nội bộ dựa vào cú pháp, kiểu dữ liệu và công cụ của ngôn ngữ chủ. DSL bên ngoài có thể định nghĩa cú pháp và ngữ nghĩa độc lập với ngôn ngữ triển khai.

Khi so sánh chúng, cần hiểu **khả năng biểu đạt (expressiveness)** theo nghĩa rộng. Khả năng biểu đạt không chỉ là một ngôn ngữ có thể tính toán được bao nhiêu thứ hoặc có bao nhiêu câu lệnh. Trong một DSL, khả năng biểu đạt còn thể hiện ở việc người dùng có thể mô tả đúng khái niệm miền, viết được quy tắc cần thiết, thể hiện ý định rõ ràng, kiểm soát những trường hợp không hợp lệ và duy trì biểu thức khi yêu cầu thay đổi.

Vì vậy, không có kết luận chung rằng DSL nội bộ luôn mạnh hơn vì kế thừa ngôn ngữ chủ, hoặc DSL bên ngoài luôn tốt hơn vì có cú pháp riêng. Cần đánh giá theo miền, người dùng, loại tác vụ, môi trường triển khai và năng lực của nhóm phát triển.

## Khả năng biểu đạt gồm những khía cạnh nào?

Trước khi đối chiếu hai kiểu DSL, cần tách khả năng biểu đạt thành các khía cạnh có thể quan sát được.

### Diễn đạt đúng khái niệm miền

Một DSL biểu đạt tốt khi từ vựng và cấu trúc của nó phản ánh những khái niệm mà người làm trong miền thực sự sử dụng. Trong hệ thống bán hàng, các khái niệm như đơn hàng, khách hàng, dòng hàng, thanh toán và hoàn tiền có thể là trung tâm. Trong DSL cho hạ tầng, tài nguyên, mạng, quyền và trạng thái mong muốn có thể quan trọng hơn.

Nếu người dùng phải liên tục chuyển một khái niệm miền thành nhiều cấu trúc kỹ thuật khó hiểu, ngôn ngữ có thể biểu đạt được về mặt tính toán nhưng chưa biểu đạt tốt về mặt miền. Ngược lại, một cú pháp gần ngôn ngữ nghiệp vụ có thể làm ý định rõ hơn ngay cả khi nó không cung cấp nhiều cấu trúc điều khiển tổng quát.

### Độ ngắn gọn và mức độ trực tiếp

Một biểu thức ngắn có thể làm nổi bật ý định bằng cách lược bỏ các chi tiết lặp lại. Ví dụ, câu lệnh truy vấn khai báo điều kiện và phép nhóm thường trực tiếp hơn một vòng lặp tự quản lý tập kết quả. Tuy nhiên, ngắn gọn quá mức có thể che giấu quy tắc mặc định, thứ tự thực thi hoặc tác dụng phụ.

Độ ngắn gọn có ích khi người đọc vẫn suy ra được hành vi chính xác. Cần đánh giá số lượng khái niệm người dùng phải ghi nhớ, lượng thông tin bị ẩn và khả năng lần theo nguyên nhân khi có lỗi.

### Khả năng kết hợp và mở rộng

Một ngôn ngữ có khả năng kết hợp tốt cho phép ghép các biểu thức nhỏ thành biểu thức lớn mà vẫn giữ được ý nghĩa. DSL cũng cần cách mở rộng để thêm thuật ngữ, phép toán, loại quy tắc hoặc tích hợp với thư viện mà không làm cú pháp trở nên rối.

DSL nội bộ thường tận dụng hàm, lớp, generic, lambda và module của ngôn ngữ chủ để kết hợp biểu thức. DSL bên ngoài có thể thiết kế cấu trúc kết hợp riêng, chẳng hạn biểu thức lồng nhau, module, import hoặc extension point. Mỗi cách có giới hạn và chi phí riêng.

### Khả năng diễn đạt ràng buộc và trường hợp không hợp lệ

Khả năng biểu đạt còn bao gồm việc thể hiện những điều *không được phép*. Ví dụ, một phép toán chỉ áp dụng cho kiểu Money, một thao tác chỉ hợp lệ khi đơn hàng ở trạng thái đã xác nhận, hoặc một vai trò không có quyền phê duyệt giao dịch.

Nếu DSL giúp phát hiện các trường hợp sai trước khi chạy, người dùng có thể hiểu quy tắc miền ngay trong quá trình viết. Cả DSL nội bộ và bên ngoài đều có thể hỗ trợ kiểm tra kiểu hoặc kiểm tra ngữ nghĩa, nhưng cơ chế và mức độ tự động phụ thuộc thiết kế.

### Khả năng đọc, học và kiểm chứng ý định

Người viết và người đọc có thể là những nhóm khác nhau. Một DSL dành cho lập trình viên có thể ưu tiên tích hợp với IDE và hệ kiểu của ngôn ngữ chủ. Một DSL cho chuyên gia nghiệp vụ có thể ưu tiên cách viết gần với thuật ngữ công việc.

Biểu thức dễ đọc cần giúp người khác xác định được điều kiện, hành động, phạm vi và kết quả. Khả năng biểu đạt tốt không chỉ dành cho người tạo ra chương trình; nó còn phải giúp người xem xét hiểu và xác nhận chương trình có đúng ý định hay không.

## DSL nội bộ: biểu đạt thông qua ngôn ngữ chủ

DSL nội bộ được xây dựng như một API hoặc tập cấu trúc có cách sử dụng giống ngôn ngữ riêng, nhưng thực chất tuân theo cú pháp của một ngôn ngữ chủ (host language). Người dùng viết biểu thức DSL bằng các tính năng sẵn có của ngôn ngữ đó.

Các kỹ thuật thường dùng gồm:

- API fluent với các lời gọi phương thức nối tiếp.
- Builder pattern để tạo cấu trúc phức tạp theo từng bước.
- Lambda hoặc closure để biểu diễn khối lệnh và phạm vi.
- Generic và hệ thống kiểu để ràng buộc kiểu dữ liệu.
- Hàm bậc cao để kết hợp điều kiện, phép biến đổi và hành động.
- Annotation hoặc metadata để mô tả cấu hình.
- Operator overloading nếu ngôn ngữ chủ cho phép.

Ví dụ, một thư viện Java có thể cung cấp API để mô tả quy tắc ưu đãi:

```java
Rule vipShipping = rule("VIP shipping")
    .when(allOf(
        orderTotal().atLeast(money(1_000_000, "VND")),
        customerSegment().is("VIP")
    ))
    .then(set(shipmentFee(), money(0, "VND")));
```

Đây là ví dụ giả định về một API fluent. Các hàm `rule`, `allOf`, `orderTotal` và `set` phải do thư viện DSL cung cấp. Cú pháp vẫn là cú pháp Java: biểu thức được tạo từ lời gọi hàm, dấu chấm, dấu ngoặc và lambda nếu cần.

### DSL nội bộ tận dụng khả năng của ngôn ngữ chủ

Một lợi thế quan trọng là DSL có thể sử dụng trực tiếp các cơ chế đã được ngôn ngữ chủ hỗ trợ. Nếu ngôn ngữ chủ có kiểu tĩnh, compiler có thể phát hiện một số lỗi kiểu khi biên dịch. Nếu có generic, DSL có thể giới hạn kiểu đầu vào và đầu ra. Nếu có lambda, người dùng có thể mô tả hành vi hoặc phạm vi bằng các khối biểu thức quen thuộc.

Ví dụ, một API Java có thể thiết kế kiểu để điều kiện chỉ nhận kết quả Boolean và hành động chỉ nhận đối tượng có thể thay đổi:

```java
Condition<Order> condition = order ->
    order.total().compareTo(minimumTotal) >= 0;

Action<Order> action = order ->
    order.setPriority(Priority.HIGH);
```

Hệ thống kiểu Java có thể kiểm tra một số lỗi như truyền nhầm kiểu `Customer` vào nơi yêu cầu `Order`. Tuy nhiên, kiểu tĩnh không tự động kiểm tra được mọi quy tắc miền. Điều kiện “chỉ được thay đổi ưu tiên khi đơn hàng chưa giao” vẫn cần được mô hình hóa và xác thực riêng.

### Giới hạn cú pháp của DSL nội bộ

DSL nội bộ phải tuân theo ngữ pháp của ngôn ngữ chủ. Người thiết kế có thể tạo API dễ đọc, nhưng không thể tự do thêm từ khóa, dấu phân cách hoặc cấu trúc cú pháp tùy ý.

Ví dụ, trong Java, người dùng không thể định nghĩa một câu lệnh mới như:

```text
WHEN order.total >= 1000000 VND
THEN shipment.fee = 0 VND
```

trừ khi câu lệnh đó được viết dưới dạng chuỗi rồi phân tích bằng một parser riêng, khi ấy phần cú pháp chuỗi thực chất đã trở thành một DSL bên ngoài. API nội bộ thường phải biểu diễn cùng ý tưởng bằng phương thức, đối tượng, lambda hoặc builder.

Ngôn ngữ chủ có thể khiến DSL nội bộ dài hơn hoặc kém tự nhiên với người không quen lập trình. Ví dụ, các dấu ngoặc, dấu chấm phẩy, generic và kiểu tham số có thể là chi tiết không liên quan trực tiếp đến nghiệp vụ nhưng vẫn xuất hiện trong biểu thức.

### Khả năng biểu đạt của DSL nội bộ

DSL nội bộ thường có khả năng biểu đạt mạnh khi người dùng cần kết hợp logic tổng quát với các khái niệm miền. Người thiết kế có thể tận dụng cấu trúc điều khiển, hàm, kiểu, module và thư viện của ngôn ngữ chủ thay vì xây dựng lại toàn bộ.

Tuy nhiên, khả năng biểu đạt miền bị ảnh hưởng bởi giới hạn cú pháp của host language. Một số khái niệm có thể khó biểu diễn trực tiếp hoặc buộc phải tạo ra nhiều lớp builder và phương thức. Cú pháp có thể trở nên sâu, nhiều dấu ngoặc hoặc khó đọc nếu API không được thiết kế cẩn thận.

## DSL bên ngoài: biểu đạt bằng cú pháp riêng

DSL bên ngoài có ngữ pháp và cách viết độc lập với ngôn ngữ triển khai. Người dùng viết chương trình theo cú pháp của DSL; frontend đọc nội dung, phân tích cú pháp và chuyển thành AST hoặc IR. Backend có thể diễn giải, sinh mã hoặc chuyển đổi nội dung sang một hệ thống khác.

Ví dụ, DSL bên ngoài cho quy tắc ưu đãi có thể dùng cú pháp:

```text
RULE "VIP shipping"
WHEN order.total >= 1000000 VND
  AND customer.segment IS "VIP"
THEN shipment.fee = 0 VND
```

Đây là cú pháp minh họa do một ngôn ngữ giả định định nghĩa. Người thiết kế có thể chọn từ khóa, toán tử, đơn vị đo, dấu phân cách và cấu trúc khối sao cho phù hợp với miền. Parser sẽ kiểm tra văn bản theo ngữ pháp đó.

### Tự do thiết kế từ vựng và cấu trúc

Vì không phải tuân theo ngữ pháp của một ngôn ngữ chủ, DSL bên ngoài có thể tạo ra cú pháp gần với cách chuyên gia miền mô tả vấn đề. Có thể định nghĩa các từ khóa như `WHEN`, `THEN`, `MATCH`, `RESOURCE`, `POLICY`, hoặc cú pháp khai báo theo khối, bảng hay biểu thức.

Ngôn ngữ cũng có thể hỗ trợ kiểu dữ liệu và literal chuyên miền, chẳng hạn `1000000 VND`, `5 days`, `3 meters` hoặc `2026-11-15`. Những cách viết này giúp ý nghĩa rõ hơn nếu được quy định chính xác và có kiểm tra đơn vị.

Sự tự do đó đi kèm trách nhiệm. Nhóm phát triển phải thiết kế lexer, parser, ngữ pháp, kiểm tra ngữ nghĩa, thông báo lỗi, tài liệu và công cụ hỗ trợ. Cú pháp riêng không tự động làm ngôn ngữ dễ học; nếu từ khóa mơ hồ hoặc quy tắc không nhất quán, người dùng sẽ khó sử dụng.

### Khả năng biểu đạt của DSL bên ngoài

DSL bên ngoài có thể tập trung vào một mô hình miền cụ thể và bỏ qua những cấu trúc không cần thiết. Điều này cho phép tạo ra biểu thức khai báo, gần với ngôn ngữ nghiệp vụ và dễ kiểm soát phạm vi.

Ví dụ, một DSL truy vấn có thể cho phép người dùng mô tả điều kiện lọc và nhóm mà không cần viết vòng lặp. Một DSL hạ tầng có thể mô tả trạng thái mong muốn của tài nguyên mà không yêu cầu người dùng chỉ định thứ tự từng lệnh tạo tài nguyên.

Tuy nhiên, DSL bên ngoài thường chỉ cung cấp những cấu trúc mà người thiết kế chủ động đưa vào. Nếu người dùng cần một phép tính hoặc luồng điều khiển chưa được hỗ trợ, họ có thể phải chờ mở rộng ngôn ngữ hoặc gọi đến một phần mở rộng được cung cấp. Giới hạn này có thể là ưu điểm khi cần giữ DSL an toàn, đơn giản và dễ kiểm tra.

## So sánh trực tiếp khả năng biểu đạt

Bảng sau đối chiếu hai cách tiếp cận theo những khía cạnh quan trọng khi xây dựng DSL:

| Khía cạnh | DSL nội bộ | DSL bên ngoài |
|---|---|---|
| Nguồn cú pháp | Kế thừa cú pháp của ngôn ngữ chủ | Có ngữ pháp riêng |
| Từ vựng miền | Thể hiện qua tên hàm, lớp, thuộc tính và phương thức | Có thể định nghĩa từ khóa và cấu trúc chuyên miền |
| Độ tự nhiên với lập trình viên | Thường cao nếu họ quen ngôn ngữ chủ | Phụ thuộc thiết kế và công cụ; cần học cú pháp riêng |
| Độ tự nhiên với chuyên gia không lập trình | Có thể thấp nếu API mang nhiều chi tiết của host language | Có thể cao nếu cú pháp gần thuật ngữ nghiệp vụ |
| Độ ngắn gọn | Bị giới hạn bởi cú pháp host language | Có thể tối ưu riêng cho tác vụ miền |
| Logic tổng quát | Dễ tận dụng hàm, vòng lặp, điều kiện và thư viện chủ | Chỉ có trong phạm vi cú pháp được DSL định nghĩa hoặc qua phần mở rộng |
| Kiểu dữ liệu | Có thể tận dụng hệ kiểu của ngôn ngữ chủ | Cần thiết kế hệ kiểu và kiểm tra riêng, hoặc ánh xạ sang kiểu backend |
| Kiểm tra ngữ nghĩa miền | Có thể kết hợp compiler chủ với kiểm tra của thư viện | Có thể xây dựng bộ phân tích và kiểm tra chuyên biệt |
| Khả năng mở rộng | Thêm API, kiểu, module và thư viện | Mở rộng grammar, AST, ngữ nghĩa và công cụ |
| IDE và gỡ lỗi | Thường tận dụng IDE của host language; cần tích hợp thêm thông tin miền | Cần đầu tư language server, formatter, debugger hoặc plugin |
| Tích hợp ứng dụng | Thuận lợi khi cùng hệ sinh thái và runtime | Cần cầu nối giữa DSL với ứng dụng hoặc ngôn ngữ triển khai |
| Tách biệt khỏi công nghệ triển khai | Thấp hơn vì gắn với host language | Cao hơn nếu đặc tả độc lập với backend |
| Chi phí ban đầu | Thường thấp hơn khi có sẵn thư viện và công cụ | Thường cao hơn do cần frontend và hệ sinh thái riêng |
| Khả năng kiểm soát phạm vi | Phụ thuộc quyền truy cập vào API và cấu trúc host language | Có thể giới hạn chính xác những gì DSL cho phép |

Các nhận xét trong bảng là xu hướng thường gặp, không phải bảo đảm. Một DSL nội bộ có thể có API rất dễ đọc và kiểm tra chặt; một DSL bên ngoài có thể có cú pháp khó hiểu và công cụ kém. Chất lượng thực tế phụ thuộc thiết kế cụ thể.

## Cùng một yêu cầu qua hai kiểu DSL

Để so sánh rõ hơn, hãy xét yêu cầu: nếu tổng giá trị đơn hàng đạt ngưỡng và khách hàng thuộc nhóm VIP, miễn phí vận chuyển.

### Biểu diễn bằng DSL nội bộ trong Java

```java
Rule freeShipping = rule("Free shipping")
    .when(allOf(
        orderTotal().atLeast(money(1_000_000, VND)),
        customerSegment().is(VIP)
    ))
    .then(set(shipmentFee(), money(0, VND)));
```

Biểu thức sử dụng các lời gọi API và hằng số do thư viện định nghĩa. Người lập trình Java có thể dùng IDE để xem kiểu tham số, đi đến định nghĩa phương thức và tái sử dụng các hàm. Compiler có thể phát hiện một số lỗi kiểu trước khi chạy.

Điểm hạn chế là người đọc cần biết Java và cách dùng API. Nếu chuyên gia nghiệp vụ không quen với lời gọi hàm, kiểu generic và cấu trúc builder, họ có thể khó tự viết hoặc xác nhận quy tắc.

### Biểu diễn bằng DSL bên ngoài

```text
RULE "Free shipping"
WHEN order.total >= 1000000 VND
  AND customer.segment IS VIP
THEN shipment.fee = 0 VND
```

Biểu thức có thể gần với cách mô tả nghiệp vụ hơn. Người thiết kế DSL có thể định nghĩa `VND` là đơn vị tiền tệ, `VIP` là một giá trị thuộc kiểu CustomerSegment và `AND` là phép kết hợp Boolean. Parser và semantic analyzer kiểm tra cấu trúc, kiểu và quy tắc miền.

Đổi lại, nhóm phải xây dựng và duy trì ngữ pháp, frontend, thông báo lỗi và công cụ. Nếu muốn tích hợp với Java, hệ thống cần chuyển AST hoặc IR sang đối tượng miền hoặc mã thực thi tương ứng.

### So sánh ý nghĩa, không chỉ số dòng

Hai biểu thức đều có thể diễn đạt cùng một yêu cầu. Để xác định cách nào phù hợp hơn, hãy hỏi:

- Người dùng mục tiêu có đọc được biểu thức mà không cần học thêm nhiều khái niệm kỹ thuật không?
- Có thể xác định rõ ngưỡng tính trên tổng trước hay sau giảm giá, có bao gồm thuế không?
- Kiểu tiền tệ và đơn vị có được kiểm tra không?
- Có thể tái sử dụng điều kiện VIP ở nhiều quy tắc không?
- Có thể phát hiện xung đột khi nhiều quy tắc cùng áp dụng không?
- Khi có lỗi, người dùng có nhận được vị trí và lý do dễ hiểu không?

Khả năng biểu đạt tốt thể hiện ở việc ngôn ngữ giúp người dùng viết đúng ý định và giúp hệ thống kiểm tra ý định đó, chứ không chỉ ở việc biểu thức trông ngắn hơn.

## Vai trò của hệ thống kiểu trong khả năng biểu đạt

Hệ thống kiểu ảnh hưởng đáng kể đến những lỗi mà DSL có thể phát hiện trước khi thực thi. DSL nội bộ có thể tận dụng kiểu của host language; DSL bên ngoài có thể định nghĩa kiểu riêng hoặc ánh xạ sang kiểu của runtime.

### Kiểu của ngôn ngữ chủ

Trong DSL nội bộ Java, generic và interface có thể ràng buộc dữ liệu đầu vào:

```java
interface Condition<T> {
    boolean test(T value);
}

Condition<Order> hasMinimumTotal = order ->
    order.total().compareTo(minimumTotal) >= 0;
```

Compiler có thể kiểm tra `Condition<Order>` được dùng ở nơi cần điều kiện cho `Order`. Các kiểu này cũng giúp IDE hiển thị gợi ý và tài liệu API.

Nhưng hệ kiểu chủ có thể không mô tả đầy đủ quy tắc miền. Ví dụ, Java có thể biết `order.status()` trả về `OrderStatus`, nhưng không tự biết hành động hoàn tiền chỉ hợp lệ khi trạng thái là `PAID` và số tiền còn lại đủ lớn. Thư viện DSL cần bổ sung kiểm tra đó.

### Hệ kiểu riêng của DSL bên ngoài

DSL bên ngoài có thể định nghĩa các kiểu như `Money`, `Percentage`, `Duration`, `Customer`, `Order` và `Shipment`. Nó có thể quy định phép toán hợp lệ, chuyển đổi đơn vị và kiểu kết quả.

Ví dụ:

```text
1000000 VND + 50000 VND       // Money + Money -> Money
10% * order.total             // Percentage * Money -> Money
order.total + 3 days          // không hợp lệ về kiểu
```

Các chú thích chỉ thể hiện ý định của hệ kiểu giả định. Đặc tả cần xác định làm tròn, độ chính xác, đơn vị tiền tệ, chuyển đổi và cách xử lý giá trị thiếu. Một hệ kiểu riêng tạo được sự phù hợp cao với miền nhưng cũng cần được thiết kế, triển khai và bảo trì.

### Kiểu tĩnh và kiểm tra lúc chạy

Kiểm tra tĩnh phát hiện lỗi trước khi chương trình được thực thi hoặc triển khai. Kiểm tra lúc chạy xác nhận điều kiện dựa trên dữ liệu thực tế. Cả hai đều có thể cần thiết.

Ví dụ, DSL có thể kiểm tra tĩnh rằng `order.total` có kiểu Money và `shipment.fee` nhận Money. Nhưng việc khách hàng thực sự có hạng VIP hay không phụ thuộc dữ liệu tại thời điểm chạy. Thiết kế tốt phân biệt lỗi cấu trúc hoặc kiểu có thể phát hiện sớm với điều kiện nghiệp vụ chỉ biết khi có dữ liệu thực tế.

## Khả năng kết hợp và tái sử dụng

Một DSL cần cho phép người dùng xây dựng quy tắc lớn từ những thành phần nhỏ. Khả năng kết hợp ảnh hưởng đến mức độ biểu đạt khi miền phát triển.

### Kết hợp trong DSL nội bộ

DSL nội bộ có thể dùng hàm bậc cao và abstraction của ngôn ngữ chủ:

```java
Condition<Order> eligibleForFreeShipping = allOf(
    orderTotal().atLeast(minimumTotal),
    customerSegment().is(VIP),
    destination().isWithin(supportedRegion)
);

Rule rule = rule("Free shipping")
    .when(eligibleForFreeShipping)
    .then(set(shipmentFee(), money(0, VND)));
```

Điều kiện có thể được đặt tên, tái sử dụng, truyền vào hàm và kiểm thử bằng công cụ Java. Người dùng cũng có thể sử dụng các thư viện thông thường để xử lý ngày tháng, tập hợp hoặc dữ liệu.

Nhược điểm có thể xuất hiện khi API cho phép quá nhiều cách kết hợp không hợp lệ hoặc khi biểu thức phụ thuộc vào trạng thái thay đổi của đối tượng. Cần thiết kế kiểu và builder sao cho cấu trúc được tạo ra phản ánh đúng ngữ nghĩa.

### Kết hợp trong DSL bên ngoài

DSL bên ngoài có thể hỗ trợ khai báo điều kiện dùng chung:

```text
condition eligibleForFreeShipping =
    order.total >= 1000000 VND
    AND customer.segment IS VIP
    AND destination.region IN supportedRegions

RULE "Free shipping"
WHEN eligibleForFreeShipping
THEN shipment.fee = 0 VND
```

Ngôn ngữ cần định nghĩa cách khai báo, phạm vi, tham chiếu và quy tắc tái sử dụng. Khi có module, import và namespace, người dùng có thể chia quy tắc theo lĩnh vực hoặc nhóm trách nhiệm.

DSL bên ngoài có thể giới hạn cách kết hợp để giữ tính khai báo. Đây là lợi thế nếu mục tiêu là kiểm tra và tối ưu quy tắc, nhưng có thể gây bất tiện nếu người dùng cần một phép biến đổi tổng quát chưa được ngôn ngữ hỗ trợ.

## Khả năng kiểm soát và phân tích chương trình

Một yếu tố quan trọng khác là công cụ có thể hiểu chương trình ở mức cấu trúc đến đâu. Khả năng phân tích giúp phát hiện xung đột, kiểm tra chính sách, tối ưu hóa hoặc sinh tài liệu.

### Phân tích DSL nội bộ

Vì DSL nội bộ thường là chương trình của host language, compiler chủ nhìn thấy cấu trúc theo mô hình của ngôn ngữ đó. Nếu biểu thức DSL chỉ gọi các hàm tạo đối tượng và không thực thi logic tùy ý, thư viện có thể xây dựng AST hoặc rule model để phân tích tiếp.

Tuy nhiên, nếu DSL nội bộ cho phép gọi bất kỳ hàm Java nào, tạo vòng lặp hoặc thực thi mã tùy ý, công cụ DSL khó xác định đầy đủ hành vi chỉ từ các lời gọi API. Một chương trình có thể có tác dụng phụ hoặc phụ thuộc vào trạng thái bên ngoài. Muốn phân tích tĩnh sâu, nhóm cần giới hạn bề mặt API và biểu diễn logic bằng các đối tượng dữ liệu có cấu trúc.

### Phân tích DSL bên ngoài

Vì cú pháp và ngữ nghĩa do DSL kiểm soát, frontend có thể tạo AST có cấu trúc rõ ràng. Điều này thuận lợi cho việc:

- Phát hiện hai quy tắc mâu thuẫn.
- Xác định điều kiện không thể xảy ra.
- Kiểm tra tài nguyên hoặc thuộc tính không tồn tại.
- Phân tích quyền hạn và phạm vi tác động.
- Sinh tài liệu hoặc sơ đồ từ quy tắc.
- Tối ưu hóa thứ tự đánh giá nếu ngữ nghĩa cho phép.

Khả năng này không tự động xuất hiện chỉ vì DSL có parser riêng. Ngữ nghĩa phải được thiết kế đủ khai báo và công cụ phải có các bộ phân tích phù hợp.

## Độ an toàn và phạm vi quyền hạn

Khả năng biểu đạt càng rộng thì người dùng có thể thực hiện càng nhiều loại hành động. Trong một DSL cho phép cấu hình hoặc quy tắc do nhiều người viết, nhóm cần cân bằng giữa sức mạnh và khả năng kiểm soát.

DSL nội bộ có thể kế thừa khả năng của host language, bao gồm truy cập thư viện, tệp, mạng hoặc hệ thống. Nếu người viết DSL thực chất đang viết mã Java tùy ý, việc giới hạn quyền cần được thực hiện bằng sandbox, quy tắc triển khai hoặc kiến trúc thực thi phù hợp; chỉ bọc các lời gọi trong một API không tạo ra ranh giới bảo mật.

DSL bên ngoài có thể chỉ cung cấp những thao tác được phép, chẳng hạn khai báo điều kiện và thay đổi một tập thuộc tính cụ thể. Backend có thể kiểm tra quyền trên từng action. Tuy nhiên, DSL bên ngoài vẫn có thể gây tác động lớn nếu backend thực thi lệnh nguy hiểm hoặc truy cập dữ liệu nhạy cảm. Cần kiểm soát quyền ở lớp thực thi và dữ liệu, không chỉ dựa vào cú pháp.

Trong các miền có rủi ro cao, một ngôn ngữ hạn chế có thể có lợi hơn một ngôn ngữ đa dụng. Người dùng có thể biểu đạt đúng nhóm yêu cầu được cho phép mà không có quyền gọi các thao tác nằm ngoài phạm vi.

## Tác động đến công cụ và trải nghiệm phát triển

Khả năng biểu đạt trên giấy không đủ để đánh giá một DSL. Trải nghiệm viết, đọc, gỡ lỗi và kiểm thử cũng ảnh hưởng đến khả năng sử dụng thực tế.

### Công cụ cho DSL nội bộ

DSL nội bộ thường được hưởng lợi từ IDE của ngôn ngữ chủ: tự động hoàn thành, điều hướng symbol, refactoring, debugger, formatter và hệ thống build. Tài liệu thư viện và kiểm tra kiểu có thể được tích hợp sẵn.

Nhưng IDE thường hiểu biểu thức theo ngữ nghĩa Java hoặc ngôn ngữ chủ, không nhất thiết hiểu được khái niệm miền. Nếu API có nhiều phương thức nối tiếp, gợi ý tự động có thể hiển thị tên hàm nhưng chưa giải thích điều kiện nghiệp vụ hoặc tác động của quy tắc. Nhóm có thể cần plugin hoặc công cụ riêng để bổ sung hỗ trợ.

### Công cụ cho DSL bên ngoài

DSL bên ngoài cần frontend và thường cần thêm formatter, syntax highlighting, language server, debugger hoặc trình xem AST. Đây là chi phí đáng kể, nhưng nhóm có thể thiết kế trải nghiệm dành riêng cho người dùng DSL.

Ví dụ, editor có thể gợi ý các thuộc tính hợp lệ của `order`, hiển thị kiểu tiền tệ của `order.total`, cảnh báo một trạng thái không cho phép hoàn tiền và cung cấp liên kết đến định nghĩa thuật ngữ. Những chức năng này cần dữ liệu ngữ nghĩa và source location từ frontend.

### Khả năng gỡ lỗi

Với DSL nội bộ, lỗi có thể xuất hiện ở compile time của host language, trong thư viện DSL hoặc lúc chạy ứng dụng. Cần phân biệt lỗi API với lỗi quy tắc miền.

Với DSL bên ngoài, parser và semantic analyzer có thể báo lỗi theo dòng/cột của tệp DSL. Nhưng nếu có include hoặc macro, cần giữ source map để lỗi vẫn trỏ về vị trí người dùng viết. Nếu backend sinh mã, cần có cách liên hệ lỗi thực thi với biểu thức nguồn.

Một DSL biểu đạt tốt cần làm cho lỗi có thể hiểu và sửa được. Ngôn ngữ ngắn gọn nhưng không có diagnostics tốt có thể gây chi phí lớn trong vận hành.

## Chi phí phát triển và bảo trì

Chi phí ban đầu và chi phí dài hạn có thể khác nhau đáng kể.

DSL nội bộ thường có thể bắt đầu bằng một thư viện nhỏ: mô hình đối tượng, API fluent và các hàm tạo biểu thức. Nhóm có thể tận dụng compiler, hệ build, thư viện và quy trình kiểm thử hiện có. Tuy nhiên, API cần được duy trì tương thích với phiên bản host language và có thể bị ảnh hưởng bởi cách tổ chức mã của ứng dụng.

DSL bên ngoài cần đầu tư vào ngữ pháp, lexer/parser, AST, phân tích ngữ nghĩa, diagnostics, tài liệu và công cụ. Khi ngôn ngữ thay đổi, nhóm phải quản lý tương thích cú pháp và phiên bản. Đổi lại, đặc tả DSL có thể ổn định độc lập với ngôn ngữ backend nếu thiết kế đúng.

Chi phí cần tính cả người sử dụng. DSL nội bộ có thể rẻ với nhóm Java nhưng đắt nếu muốn chuyên gia nghiệp vụ tự viết quy tắc. DSL bên ngoài có thể cần đầu tư công cụ ban đầu nhưng giảm chi phí trao đổi và chỉnh sửa khi nhiều nhóm nghiệp vụ dùng chung.

## Chọn cách tiếp cận theo bối cảnh

### Khi DSL nội bộ phù hợp

DSL nội bộ thường phù hợp khi:

- Người viết DSL chủ yếu là lập trình viên đã quen ngôn ngữ chủ.
- Tác vụ miền cần kết hợp nhiều logic tổng quát và thư viện hiện có.
- Nhóm muốn thử nghiệm nhanh một mô hình hoặc API trước khi đầu tư frontend riêng.
- DSL chỉ là một phần nhỏ trong ứng dụng và cần tích hợp trực tiếp với đối tượng, kiểu và dịch vụ của ứng dụng.
- Cú pháp của ngôn ngữ chủ đủ để diễn đạt các thao tác miền mà không gây khó hiểu.
- Công cụ IDE, build và kiểm thử của host language mang lại lợi ích đáng kể.

Ví dụ, một thư viện Java cho phép mô tả cấu hình kiểm thử hoặc xây dựng truy vấn nội bộ có thể phù hợp với DSL nhúng vì người dùng chính là kỹ sư phần mềm.

### Khi DSL bên ngoài phù hợp

DSL bên ngoài thường phù hợp khi:

- Cần cú pháp gần với thuật ngữ nghiệp vụ hoặc cách chuyên gia mô tả công việc.
- Người viết không nhất thiết là lập trình viên của ngôn ngữ backend.
- Ngôn ngữ chủ không có cấu trúc phù hợp để diễn đạt tự nhiên khái niệm miền.
- Cần giới hạn rõ các thao tác được phép và kiểm tra chương trình trước khi thực thi.
- Cùng một DSL cần được dùng bởi nhiều backend hoặc nhiều ứng dụng.
- Đặc tả ngôn ngữ cần độc lập với nền tảng triển khai trong thời gian dài.
- Cần phân tích, trực quan hóa hoặc tối ưu hóa quy tắc ở mức cấu trúc.

Ví dụ, một DSL cho chính sách truy cập, quy tắc tính phí hoặc cấu hình hạ tầng có thể cần cú pháp riêng để người dùng tập trung vào khai báo và miền nghiệp vụ.

### Khi nên trì hoãn việc tạo ngôn ngữ riêng

Không phải mọi API có nhiều lời gọi phương thức đều cần trở thành DSL bên ngoài. Nếu chỉ có vài cấu hình, một tệp YAML/JSON có schema rõ hoặc một API thông thường có thể đáp ứng đủ nhu cầu. Nếu cú pháp nghiệp vụ chưa ổn định, hãy xác nhận mô hình và thuật ngữ trước khi đầu tư parser.

Một cách tiếp cận thực tế là bắt đầu với API nội bộ hoặc mô hình khai báo đơn giản, quan sát cách người dùng sử dụng, sau đó chỉ tạo DSL bên ngoài khi có bằng chứng rằng cú pháp host language cản trở khả năng biểu đạt hoặc có nhu cầu tách biệt rõ ràng.

## Có thể kết hợp DSL nội bộ và DSL bên ngoài không?

Hai cách tiếp cận không nhất thiết loại trừ nhau. Một hệ thống có thể cung cấp DSL bên ngoài cho người dùng, sau đó frontend chuyển nó thành AST hoặc IR. Phần backend được triển khai bằng Java và có thể dùng một API nội bộ để xây dựng hoặc thực thi các node.

Ví dụ kiến trúc:

```text
Người dùng nghiệp vụ
        |
        v
DSL bên ngoài (tệp quy tắc)
        |
        v
Lexer / Parser / Semantic Analyzer
        |
        v
AST hoặc IR
        |
        v
API / Runtime Java
        |
        v
Ứng dụng và dịch vụ miền
```

Trong mô hình này, DSL bên ngoài tối ưu cách biểu đạt cho người viết; API Java cung cấp kiểu, dịch vụ và khả năng tích hợp cho runtime. Cần duy trì ranh giới rõ giữa đặc tả DSL và các lớp triển khai để thay đổi backend không làm thay đổi ý nghĩa của chương trình.

Một phương án khác là cung cấp hai giao diện cho cùng mô hình quy tắc: lập trình viên dùng API Java, còn chuyên gia hoặc quản trị viên dùng cú pháp DSL bên ngoài. Cả hai đầu vào được chuyển thành cùng một IR, sau đó dùng chung bộ kiểm tra và backend. Cách này giảm nguy cơ hai giao diện có ngữ nghĩa khác nhau, nhưng đòi hỏi thiết kế mô hình trung gian đủ ổn định.

## Phương pháp đánh giá khả năng biểu đạt

Để lựa chọn có căn cứ, nên dùng một tập tác vụ đại diện thay vì chỉ tranh luận về cú pháp. Chọn các tình huống thực tế gồm trường hợp thông thường, điều kiện phức tạp, ngoại lệ và yêu cầu thay đổi. Sau đó thử biểu diễn từng tình huống bằng cả hai cách tiếp cận.

Có thể đánh giá theo các tiêu chí:

| Tiêu chí đánh giá | Câu hỏi gợi ý |
|---|---|
| Độ đầy đủ | Có diễn đạt được toàn bộ yêu cầu trong phạm vi không? |
| Độ rõ nghĩa | Người khác có hiểu đúng ý định mà không cần tác giả giải thích không? |
| Mức độ gần miền | Thuật ngữ và cấu trúc có phù hợp cách chuyên gia suy nghĩ không? |
| Độ ngắn gọn | Có giảm được mã phụ trợ mà không che giấu quy tắc không? |
| Khả năng kết hợp | Có thể tái sử dụng và kết hợp biểu thức một cách tự nhiên không? |
| Kiểm tra lỗi | Có phát hiện được lỗi cú pháp, kiểu và quy tắc miền trước khi chạy không? |
| Khả năng mở rộng | Khi thêm yêu cầu mới, ngôn ngữ có thể mở rộng mà không phá vỡ biểu thức cũ không? |
| Trải nghiệm công cụ | IDE, tài liệu, formatter và diagnostics có hỗ trợ đủ không? |
| Tính an toàn | Có giới hạn được quyền và tác động của chương trình không? |
| Chi phí sở hữu | Chi phí xây dựng, học, vận hành và bảo trì có hợp lý không? |

Có thể cho người dùng mục tiêu thực hiện cùng một tập tác vụ và ghi nhận thời gian, số lần hỏi lại, lỗi diễn giải, số lỗi được phát hiện sớm và mức độ cần hỗ trợ. Các số đo này không thay thế đánh giá định tính, nhưng giúp quyết định dựa trên trải nghiệm thực tế.

### Ví dụ ma trận quyết định

Giả sử nhóm xây dựng công cụ quy tắc cho hai nhóm: lập trình viên Java và chuyên viên nghiệp vụ. Có thể lập ma trận sơ bộ:

| Nhu cầu | DSL nội bộ | DSL bên ngoài |
|---|---|---|
| Lập trình viên Java viết quy tắc phức tạp | Phù hợp nếu API rõ và tích hợp tốt | Có thể phù hợp nhưng cần học cú pháp mới |
| Chuyên viên nghiệp vụ tự đọc và chỉnh quy tắc | Có thể khó nếu biểu thức chứa nhiều cấu trúc Java | Có lợi nếu cú pháp dùng thuật ngữ nghiệp vụ |
| Tận dụng thư viện Java | Trực tiếp | Qua backend hoặc adapter |
| Dùng cùng quy tắc trên nhiều runtime | Cần tách logic khỏi host language | Thuận lợi nếu IR và ngữ nghĩa độc lập |
| Phân tích tĩnh và giới hạn thao tác | Cần hạn chế API và biểu diễn logic có cấu trúc | Có thể kiểm soát qua grammar và semantic model |

Ma trận chỉ là điểm khởi đầu. Kết quả cuối cùng cần dựa trên các tác vụ và người dùng thật của dự án.

## Những hiểu lầm khi so sánh khả năng biểu đạt

### Ngôn ngữ tổng quát mạnh hơn nên DSL nội bộ luôn biểu đạt tốt hơn

Ngôn ngữ chủ có thể tính toán tổng quát, nhưng điều đó không đồng nghĩa người dùng diễn đạt được ý định miền một cách ngắn gọn hoặc dễ hiểu. Một chương trình Java có thể thực hiện mọi bước xử lý, nhưng một biểu thức SQL có thể mô tả truy vấn trực tiếp hơn.

### DSL bên ngoài có cú pháp riêng nên luôn dễ dùng hơn

Cú pháp riêng chỉ tạo cơ hội tối ưu cách diễn đạt. Nếu từ khóa khó nhớ, quy tắc ngữ pháp không nhất quán hoặc thông báo lỗi kém, DSL bên ngoài có thể khó dùng hơn API nội bộ được thiết kế tốt.

### Ít dòng mã hơn nghĩa là khả năng biểu đạt cao hơn

Một biểu thức ngắn có thể dựa trên nhiều quy tắc mặc định không được nhìn thấy. Cần xem xét khả năng hiểu, kiểm tra và bảo trì, không chỉ số dòng hoặc số ký tự.

### Có kiểu tĩnh là đã kiểm tra được quy tắc nghiệp vụ

Hệ kiểu phát hiện một số lỗi cấu trúc và kiểu dữ liệu. Nhiều quy tắc miền phụ thuộc trạng thái, dữ liệu và quyền tại thời điểm chạy, nên vẫn cần semantic validation hoặc runtime validation.

### DSL nội bộ không cần parser nên không có chi phí ngôn ngữ

DSL nội bộ có thể không cần lexer/parser riêng, nhưng vẫn cần thiết kế API, mô hình biểu thức, thông báo lỗi miền, kiểm tra và tài liệu. Nếu DSL nội bộ nhận chuỗi và tự phân tích, nó đã có một frontend cho cú pháp chuỗi đó.

### DSL bên ngoài luôn độc lập với backend

Một DSL có cú pháp riêng vẫn có thể phụ thuộc sâu vào một runtime hoặc hệ thống cụ thể. Sự độc lập chỉ có khi ngữ nghĩa và mô hình trung gian được thiết kế tách khỏi cách triển khai.

## Kết luận

DSL nội bộ biểu đạt miền thông qua cú pháp và hệ sinh thái của ngôn ngữ chủ. Nó thường phù hợp với lập trình viên, dễ tích hợp và có thể tận dụng hệ kiểu cùng công cụ sẵn có, nhưng bị giới hạn bởi cú pháp host language và mức độ quen thuộc của người dùng.

DSL bên ngoài có thể định nghĩa từ vựng, cấu trúc và quy tắc riêng để diễn đạt miền trực tiếp hơn, hỗ trợ người dùng không chuyên lập trình và kiểm soát phạm vi chương trình. Đổi lại, nhóm phải đầu tư frontend, hệ kiểu hoặc kiểm tra ngữ nghĩa, diagnostics và công cụ phát triển.

Khả năng biểu đạt nên được đánh giá theo mức độ ngôn ngữ giúp người dùng mô tả đúng vấn đề, hiểu đúng ý định, kết hợp quy tắc, phát hiện lỗi và duy trì chương trình. Khi quyết định giữa DSL nội bộ và DSL bên ngoài, hãy thử cả hai trên những tác vụ thật và lựa chọn cách phù hợp với người dùng cùng chi phí sở hữu lâu dài.
