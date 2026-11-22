# Tránh lặp điều kiện và điều kiện phủ định khó đọc

Trong Spring Expression Language (SpEL), toán tử logic cho phép kết hợp nhiều điều kiện thành một biểu thức. Khi quy tắc nghiệp vụ phát triển, biểu thức dễ xuất hiện các đoạn điều kiện lặp lại, nhiều dấu phủ định hoặc những nhánh logic khó kiểm tra.

Một biểu thức dễ đọc cần thể hiện rõ điều kiện nào phải đúng, điều kiện nào được phép sai và tại sao một trường hợp bị từ chối. Có thể cải thiện bằng cách nhóm điều kiện, đặt tên cho quy tắc dùng chung, tận dụng đánh giá ngắn mạch và viết điều kiện theo hướng khẳng định.

## 1. Các toán tử logic trong SpEL

SpEL cung cấp ba phép toán logic cơ bản:

| Ký hiệu | Từ khóa tương đương | Ý nghĩa |
|---|---|---|
| **&&** | **and** | AND: cả hai vế đều phải đúng |
| **\|\|** | **or** | OR: ít nhất một vế đúng |
| **!** | **not** | NOT: đảo giá trị Boolean |

Ví dụ:

~~~java
order.total > 100 && order.status == 'PAID'
~~~

Điều kiện đúng khi tổng tiền lớn hơn 100 và trạng thái là PAID.

Ví dụ dùng OR:

~~~java
order.status == 'PAID' || order.status == 'SETTLED'
~~~

Điều kiện đúng khi đơn hàng ở một trong hai trạng thái.

Ví dụ dùng NOT:

~~~java
!order.cancelled
~~~

Điều kiện đúng khi cancelled là false.

SpEL hỗ trợ cả ký hiệu và từ khóa. Trong một dự án, nên chọn một cách viết nhất quán. Ký hiệu ngắn gọn, còn từ khóa có thể dễ đọc trong một số biểu thức nghiệp vụ. Dù chọn cách nào, hãy dùng dấu ngoặc khi kết hợp nhiều nhóm điều kiện.

## 2. Đánh giá ngắn mạch (short-circuit)

Một đặc tính quan trọng của AND và OR là SpEL đánh giá ngắn mạch:

- Với AND, nếu vế trái là false thì vế phải không cần đánh giá.
- Với OR, nếu vế trái là true thì vế phải không cần đánh giá.

### 2.1. Dùng AND để bảo vệ truy cập property

Giả sử customer có thể null:

~~~java
order.customer != null && order.customer.active
~~~

Nếu customer là null, vế đầu tiên false và SpEL bỏ qua vế thứ hai. Nhờ đó, biểu thức không cố truy cập active trên một customer null.

Có thể tiếp tục kiểm tra nhiều cấp:

~~~java
order.customer != null
    && order.customer.profile != null
    && order.customer.profile.verified
~~~

Mỗi bước chỉ được đánh giá nếu các điều kiện trước đó đều đúng.

Thứ tự các vế vì vậy có ý nghĩa. Đặt điều kiện kiểm tra null trước phần truy cập phụ thuộc vào object đó.

### 2.2. Dùng OR để cung cấp nhánh dự phòng

~~~java
order.customer == null || order.customer.active
~~~

Nếu customer null, vế đầu tiên true nên vế thứ hai được bỏ qua. Biểu thức trả về true.

Tuy nhiên, hãy kiểm tra xem cách hiểu này có đúng nghiệp vụ không. Biểu thức trên coi trường hợp không có customer là điều kiện được chấp nhận. Nếu nghiệp vụ yêu cầu customer bắt buộc tồn tại, nên dùng AND với kiểm tra null thay vì OR.

### 2.3. Không dựa vào tác dụng phụ trong vế bị bỏ qua

Vì một vế có thể không được đánh giá, không nên dùng lời gọi method có tác dụng phụ để cập nhật trạng thái, ghi dữ liệu hoặc gửi thông báo bên trong điều kiện logic.

Một biểu thức điều kiện nên đọc dữ liệu và trả về kết quả xác định. Nếu cần thực hiện hành động, hãy xử lý hành động đó ở tầng Java sau khi đã đánh giá điều kiện.

## 3. Tránh lặp cùng một điều kiện

### 3.1. Nhận diện điều kiện bị lặp

Một biểu thức có thể lặp lại cùng một phép kiểm tra ở nhiều nhánh:

~~~java
(order.customer != null && order.customer.active && order.total > 0)
||
(order.customer != null && order.customer.active && order.priority)
~~~

Cả hai nhánh đều yêu cầu customer tồn tại và đang active. Có thể nhóm phần điều kiện chung:

~~~java
order.customer != null
    && order.customer.active
    && (order.total > 0 || order.priority)
~~~

Biểu thức mới thể hiện rõ: customer phải tồn tại và active; sau đó đơn hàng phải có tổng tiền dương hoặc được đánh dấu ưu tiên.

Việc nhóm này tương đương về logic vì phần điều kiện chung đều phải đúng trong cả hai nhánh. Dấu ngoặc làm rõ hai lựa chọn ở phía sau.

### 3.2. Đặt tên cho điều kiện dùng chung

Khi một điều kiện được dùng trong nhiều biểu thức hoặc có ý nghĩa nghiệp vụ riêng, nên đặt tên cho nó ở tầng Java.

Ví dụ, model cung cấp property có ý nghĩa:

~~~java
order.eligibleForProcessing
~~~

Thay vì lặp lại:

~~~java
order.customer != null
    && order.customer.active
    && order.payment != null
    && order.payment.confirmed
~~~

Một property hoặc method có tên rõ ràng giúp người đọc hiểu mục đích nghiệp vụ mà không phải phân tích toàn bộ chi tiết triển khai.

Tên nên mô tả trạng thái hoặc kết quả, chẳng hạn:

- **eligibleForProcessing**
- **paymentConfirmed**
- **customerActive**
- **withinCreditLimit**

Tránh tên chung chung như **check1**, **flag2** hoặc **conditionA**.

### 3.3. Dùng biến trong EvaluationContext

Nếu ứng dụng cần tái sử dụng một kết quả đã tính, có thể đặt biến vào EvaluationContext:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("customerActive", customerIsActive);
context.setVariable("withinCreditLimit", withinCreditLimit);
~~~

Biểu thức có thể sử dụng các biến:

~~~java
#customerActive && #withinCreditLimit
~~~

Biến SpEL được tham chiếu bằng dấu **#**. Giá trị của biến được cung cấp từ Java trước khi đánh giá.

Cách này phù hợp khi:

- Một phép kiểm tra tốn công đã được tính ở tầng Java.
- Nhiều biểu thức dùng chung một kết quả.
- Muốn tách việc lấy dữ liệu khỏi việc diễn đạt quy tắc.
- Cần kiểm soát rõ dữ liệu được đưa vào biểu thức.

Cần quản lý vòng đời của context và biến theo đúng request hoặc lần đánh giá. Không chia sẻ context có biến thay đổi giữa các luồng xử lý nếu chưa có cơ chế đồng bộ phù hợp.

### 3.4. Dùng method có tên rõ nghĩa

Có thể gọi method trên root object hoặc một policy object được đưa vào context:

~~~java
order.isEligibleForProcessing()
~~~

hoặc:

~~~java
#policy.canProcess(order)
~~~

Ví dụ:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("policy", processingPolicy);

Boolean allowed = parser
        .parseExpression("#policy.canProcess(#root)")
        .getValue(context, Boolean.class);
~~~

Method nên tập trung vào một quy tắc nghiệp vụ có tên rõ nghĩa. Nên giữ method thuần (pure) hoặc ít nhất không có tác dụng phụ, để kết quả biểu thức dễ dự đoán và có thể kiểm thử độc lập.

Không nên đưa một method quá tổng quát vào context rồi tạo ra các biểu thức gọi method với nhiều argument phức tạp. Nếu quy tắc cần nhiều bước xử lý, hãy chuyển phần đó sang Java.

## 4. Tránh phủ định nhiều tầng

### 4.1. Nhận diện double negative

Biểu thức có nhiều lớp phủ định thường khó hiểu:

~~~java
!(!order.active)
~~~

Biểu thức này tương đương:

~~~java
order.active
~~~

Tương tự, tên property đã mang nghĩa phủ định rồi lại phủ định thêm:

~~~java
!order.notAllowed
~~~

Người đọc phải xử lý hai lần phủ định mới hiểu kết quả. Nếu có thể, hãy đổi tên property hoặc dùng một điều kiện khẳng định:

~~~java
order.allowed
~~~

Tên property nên mô tả trạng thái tích cực và rõ nghĩa. Ví dụ, ưu tiên **enabled**, **verified**, **eligible** hoặc **allowed** khi chúng phản ánh đúng domain.

### 4.2. Dùng phủ định trực tiếp và có dấu ngoặc

Nếu cần phủ định một điều kiện đơn:

~~~java
!order.cancelled
~~~

Nếu cần phủ định cả nhóm điều kiện, hãy đặt nhóm trong ngoặc:

~~~java
!(order.status == 'PAID' || order.status == 'SETTLED')
~~~

Dấu ngoặc cho biết NOT áp dụng lên toàn bộ biểu thức bên trong. Nếu bỏ ngoặc hoặc đặt sai vị trí, ý nghĩa logic có thể thay đổi.

### 4.3. Ưu tiên điều kiện khẳng định

So sánh hai cách:

~~~java
!order.blocked && !order.suspended
~~~

và:

~~~java
order.active
~~~

Nếu domain có trạng thái active được định nghĩa chính xác là không bị block và không bị suspend, property **active** sẽ dễ đọc hơn.

Tuy nhiên, chỉ gộp điều kiện khi ý nghĩa nghiệp vụ thực sự tương đương. Nếu active còn phụ thuộc ngày hết hạn, trạng thái thanh toán hoặc quyền của người dùng, hãy bảo đảm property tổng hợp phản ánh đầy đủ quy tắc đó.

Không nên tạo property khẳng định chỉ để làm biểu thức ngắn hơn nếu nó che giấu nhiều điều kiện khác nhau.

## 5. Biến đổi điều kiện bằng luật De Morgan

Luật De Morgan giúp biến đổi phủ định của một nhóm AND/OR:

| Biểu thức ban đầu | Biểu thức tương đương |
|---|---|
| **!(A && B)** | **!A \|\| !B** |
| **!(A \|\| B)** | **!A && !B** |

Ví dụ:

~~~java
!(order.paid && order.shipped)
~~~

Tương đương:

~~~java
!order.paid || !order.shipped
~~~

Ý nghĩa: không đồng thời thỏa mãn cả hai điều kiện paid và shipped. Chỉ cần một trong hai điều kiện sai là biểu thức đúng.

Ví dụ thứ hai:

~~~java
!(order.cancelled || order.expired)
~~~

Tương đương:

~~~java
!order.cancelled && !order.expired
~~~

Ý nghĩa: đơn hàng vừa chưa bị hủy, vừa chưa hết hạn.

Luật De Morgan hữu ích khi cần chuyển một điều kiện phủ định thành các điều kiện riêng. Nhưng không phải lúc nào biểu thức sau biến đổi cũng dễ đọc hơn. Hãy chọn cách viết thể hiện rõ câu nghiệp vụ nhất và luôn giữ dấu ngoặc khi nhóm điều kiện.

## 6. Kết hợp null check và phủ định

Điều kiện phủ định thường dễ gây lỗi nếu property có thể null.

Ví dụ:

~~~java
!order.customer.active
~~~

Nếu customer null, việc truy cập active có thể thất bại. Không nên giả định NOT tự xử lý giá trị null.

Nếu nghiệp vụ yêu cầu customer tồn tại và không active:

~~~java
order.customer != null && !order.customer.active
~~~

Nếu nghiệp vụ coi customer không tồn tại cũng là trường hợp không active:

~~~java
order.customer == null || !order.customer.active
~~~

Hai biểu thức này không tương đương. Hãy xác định rõ ý nghĩa của null trước khi chọn cách viết.

Với Boolean wrapper có thể null, hãy quyết định null có nghĩa là false, chưa xác định hay dữ liệu lỗi. Có thể kiểm tra tường minh:

~~~java
order.confirmed == true
~~~

hoặc:

~~~java
order.confirmed != null && order.confirmed
~~~

Cách thứ hai thể hiện rõ rằng giá trị phải tồn tại và phải true. Nếu cần phân biệt cả ba trạng thái true, false và null, hãy giữ việc kiểm tra null riêng thay vì ép chúng về một giá trị Boolean.

## 7. Làm rõ nhóm điều kiện bằng dấu ngoặc

Khi kết hợp AND và OR, dấu ngoặc giúp người đọc thấy ranh giới của từng nhóm:

~~~java
(order.status == 'PAID' || order.status == 'SETTLED')
    && (order.total > 0 || order.priority)
~~~

Ý nghĩa:

- Trạng thái phải là PAID hoặc SETTLED.
- Đồng thời, đơn hàng phải có tổng tiền dương hoặc được đánh dấu ưu tiên.

Không nên viết nhiều điều kiện trên một dòng dài nếu có thể chia thành các dòng theo nhóm nghiệp vụ. Xuống dòng và thụt lề nhất quán giúp phát hiện lỗi thiếu ngoặc và giảm khả năng hiểu nhầm thứ tự đánh giá.

Nếu biểu thức có quá nhiều nhóm lồng nhau, đó là dấu hiệu nên chuyển một phần logic sang method hoặc property có tên.

## 8. Ví dụ refactor từ biểu thức khó đọc

Giả sử quy tắc cho phép xử lý đơn hàng khi khách hàng active, đơn hàng chưa bị hủy và thỏa mãn một trong hai điều kiện: đã thanh toán hoặc là đơn hàng ưu tiên có tổng tiền dương.

Biểu thức lặp và nhiều phủ định:

~~~java
(order.customer != null
    && order.customer.active
    && !order.cancelled
    && order.payment != null
    && order.payment.confirmed)
||
(order.customer != null
    && order.customer.active
    && !order.cancelled
    && order.priority
    && order.total > 0)
~~~

Có thể nhóm điều kiện chung:

~~~java
order.customer != null
    && order.customer.active
    && !order.cancelled
    && (
        (order.payment != null && order.payment.confirmed)
        || (order.priority && order.total > 0)
    )
~~~

Biểu thức sau có cấu trúc rõ hơn:

1. Khách hàng phải tồn tại và active.
2. Đơn hàng chưa bị hủy.
3. Đơn hàng đã thanh toán hoặc là đơn ưu tiên có tổng tiền dương.

Nếu quy tắc này được dùng ở nhiều nơi, có thể chuyển phần điều kiện chung sang method:

~~~java
order.isEligibleForProcessing()
~~~

Khi đó, SpEL chỉ còn diễn đạt phần kết hợp với các điều kiện khác:

~~~java
order.isEligibleForProcessing() && request.channel == 'ONLINE'
~~~

Refactor không chỉ nhằm giảm số ký tự. Mục tiêu là để mỗi biểu thức thể hiện một ý nghĩa nghiệp vụ có thể kiểm tra và kiểm thử độc lập.

## 9. Quy trình cải thiện một biểu thức logic

Khi gặp biểu thức dài hoặc khó hiểu, có thể thực hiện theo thứ tự:

1. **Tách các điều kiện nguyên tử.** Viết ra từng phép kiểm tra như customer tồn tại, trạng thái hợp lệ, tổng tiền dương.
2. **Tìm phần lặp.** Xác định điều kiện xuất hiện ở nhiều nhánh và kiểm tra xem có thể nhóm ra ngoài hay không.
3. **Xác định ý nghĩa null.** Kiểm tra property nào có thể null và đặt guard ở trước phần truy cập phụ thuộc.
4. **Giảm phủ định.** Rút gọn double negative, cân nhắc đổi tên property hoặc dùng method khẳng định.
5. **Dùng dấu ngoặc.** Nhóm các điều kiện theo từng quy tắc nghiệp vụ, đặc biệt khi trộn AND và OR.
6. **Đặt tên cho quy tắc dùng chung.** Dùng property, biến context hoặc method nếu một điều kiện được tái sử dụng.
7. **Kiểm thử các trường hợp biên.** Bao gồm null, true, false và các tổ hợp trạng thái quan trọng.
8. **Đánh giá lại khả năng đọc.** Một người khác có thể diễn giải biểu thức thành câu nghiệp vụ mà không cần suy luận nhiều tầng hay không?

Không nên refactor bằng cách chỉ xóa phần lặp về mặt văn bản. Hai điều kiện trông giống nhau có thể khác về null, tác dụng phụ hoặc dữ liệu được đọc. Chỉ nhóm chúng khi đã xác nhận cùng ý nghĩa và cùng điều kiện đánh giá.

## 10. Kiểm thử logic và short-circuit

Nên kiểm thử cả giá trị Boolean và việc các nhánh có được đánh giá hay không.

Ví dụ với các biểu thức thuần:

~~~java
ExpressionParser parser = new SpelExpressionParser();

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("false && true")
                .getValue(Boolean.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("true || false")
                .getValue(Boolean.class)
);

assertEquals(
        Boolean.TRUE,
        parser.parseExpression("!(false || false)")
                .getValue(Boolean.class)
);
~~~

Với biểu thức có null guard, kiểm tra cả hai trường hợp:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

Boolean allowed = parser
        .parseExpression(
                "order.customer != null && order.customer.active"
        )
        .getValue(context, Boolean.class);
~~~

Kiểm thử khi customer null và khi customer tồn tại. Trường hợp null phải cho kết quả theo đúng ý nghĩa đã thiết kế, không phát sinh truy cập property ngoài dự kiến.

Nếu có thể, hãy kiểm thử bảng tổ hợp cho quy tắc nghiệp vụ. Ví dụ, với hai điều kiện A và B, kiểm tra đủ bốn trường hợp true/true, true/false, false/true và false/false. Điều đó giúp phát hiện lỗi biến đổi logic khi nhóm điều kiện hoặc áp dụng De Morgan.

## 11. Những lỗi thiết kế thường gặp

| Vấn đề | Hệ quả | Cách cải thiện |
|---|---|---|
| Lặp cùng điều kiện trong nhiều nhánh | Khó sửa và dễ lệch quy tắc giữa các nhánh | Nhóm điều kiện chung hoặc đặt tên thành property/method |
| Double negative | Người đọc phải đảo nghĩa nhiều lần | Dùng điều kiện khẳng định |
| Thiếu dấu ngoặc khi trộn AND/OR | Khó nhận biết nhóm logic | Thêm ngoặc theo từng quy tắc |
| Không kiểm tra null trước khi truy cập sâu | Lỗi khi evaluate | Dùng short-circuit guard hoặc safe navigation phù hợp |
| Gọi method có tác dụng phụ trong điều kiện | Kết quả phụ thuộc thứ tự và short-circuit | Đưa hành động ra ngoài biểu thức |
| Một biểu thức chứa quá nhiều tầng lồng nhau | Khó review và kiểm thử | Tách thành method hoặc biến có tên |
| Dùng biến context thay đổi giữa nhiều request | Có thể rò rỉ trạng thái giữa các lần đánh giá | Tạo context theo phạm vi sử dụng và quản lý vòng đời |

## 12. Tổng kết

Để viết điều kiện SpEL dễ đọc và dễ bảo trì:

- Dùng **&&** và **||** có chủ đích, tận dụng short-circuit để bảo vệ truy cập null.
- Nhóm điều kiện chung thay vì lặp lại cùng một predicate ở nhiều nhánh.
- Dùng biến trong EvaluationContext, property hoặc method có tên rõ nghĩa khi một quy tắc được tái sử dụng.
- Tránh double negative và ưu tiên diễn đạt theo trạng thái khẳng định.
- Áp dụng luật De Morgan khi giúp câu điều kiện dễ hiểu hơn, không phải chỉ để biến đổi hình thức.
- Dùng dấu ngoặc và kiểm thử các tổ hợp true/false/null quan trọng.

Khi biểu thức đã vượt quá khả năng diễn đạt rõ ràng của một điều kiện ngắn, hãy chuyển phần quy tắc nghiệp vụ sang Java. SpEL nên tập trung vào việc kết hợp những giá trị và predicate có tên rõ nghĩa, để người đọc có thể hiểu kết quả mà không phải giải mã một chuỗi logic dài.