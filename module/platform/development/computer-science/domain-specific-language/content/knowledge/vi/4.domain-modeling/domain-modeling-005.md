# Chuyển đổi trạng thái trong mô hình miền

Trong một hệ thống phần mềm, một đối tượng miền thường trải qua nhiều giai đoạn trong vòng đời của nó. Đơn hàng được tạo, xác nhận, thanh toán, giao hàng rồi hoàn tất. Yêu cầu hỗ trợ được mở, tiếp nhận, xử lý và đóng. Tài khoản có thể ở trạng thái chờ xác minh, đang hoạt động, bị khóa hoặc đã đóng.

Mỗi giai đoạn thể hiện một trạng thái của đối tượng tại một thời điểm. Khi một sự kiện hoặc yêu cầu hợp lệ xảy ra, đối tượng có thể chuyển từ trạng thái hiện tại sang trạng thái khác. Quy tắc xác định trạng thái nào được phép chuyển sang trạng thái nào, trong điều kiện nào và kèm theo hành động gì được gọi là **chuyển đổi trạng thái** (*state transition*).

Trong mô hình miền, chuyển đổi trạng thái giúp mô tả vòng đời và bảo vệ các quy tắc nghiệp vụ. Khi biểu diễn các quy tắc đó bằng một ngôn ngữ đặc tả miền (DSL), nhóm phát triển có thể đọc, kiểm tra và quản lý quy trình theo khái niệm của nghiệp vụ thay vì rải các điều kiện trạng thái ở nhiều nơi trong mã nguồn.

## 1. Trạng thái và chuyển đổi trạng thái là gì?

### 1.1. Trạng thái

Trạng thái (*state*) mô tả tình trạng hiện tại của một đối tượng hoặc một phần của hệ thống, xét theo những đặc điểm có ý nghĩa đối với miền bài toán.

Ví dụ, một đơn hàng có thể có các trạng thái:

- **Draft:** đơn hàng đang được soạn.
- **PendingPayment:** đơn hàng đã gửi và đang chờ thanh toán.
- **Paid:** thanh toán đã được xác nhận.
- **Shipped:** hàng đã được bàn giao cho đơn vị vận chuyển.
- **Delivered:** hàng đã được giao thành công.
- **Cancelled:** đơn hàng đã bị hủy.

Trạng thái không nhất thiết chỉ là một chuỗi ký tự hay một cột trong cơ sở dữ liệu. Nó là một khái niệm miền có ý nghĩa và ảnh hưởng đến những hành vi được phép của đối tượng.

Chẳng hạn, một đơn hàng ở trạng thái Draft có thể cho phép thêm hoặc xóa sản phẩm. Một đơn hàng ở trạng thái Shipped thường không còn cho phép thay đổi danh sách sản phẩm như khi đang soạn. Nếu hệ thống chỉ lưu một giá trị status mà không xác định các quy tắc liên quan, trạng thái đó chưa tạo thành một mô hình vòng đời đầy đủ.

### 1.2. Chuyển đổi trạng thái

Chuyển đổi trạng thái (*transition*) là sự thay đổi có quy tắc từ trạng thái nguồn sang trạng thái đích khi một tác nhân hoặc sự kiện phù hợp xảy ra.

Một chuyển đổi thường có các thành phần:

| Thành phần | Ý nghĩa | Ví dụ với đơn hàng |
|---|---|---|
| Trạng thái nguồn | Trạng thái hiện tại cần có | PendingPayment |
| Tác nhân kích hoạt | Lệnh hoặc sự kiện khởi đầu việc xử lý | Xác nhận đã nhận tiền |
| Điều kiện bảo vệ (*guard*) | Điều kiện phải đúng để chuyển đổi được phép | Số tiền nhận đủ giá trị đơn hàng |
| Hành động (*action*) | Việc cần thực hiện khi chuyển đổi thành công | Ghi nhận thời điểm thanh toán |
| Trạng thái đích | Trạng thái sau khi chuyển đổi | Paid |
| Sự kiện miền phát ra | Sự kiện mô tả điều đã xảy ra | OrderPaid |

Ví dụ, đơn hàng chỉ chuyển từ PendingPayment sang Paid khi hệ thống xác nhận đã nhận đủ tiền. Nếu số tiền thiếu hoặc thông tin thanh toán không hợp lệ, chuyển đổi không được thực hiện.

Có thể mô tả ngắn gọn một chuyển đổi như sau:

~~~text
PendingPayment --[PaymentConfirmed và đủ tiền]--> Paid
~~~

Mũi tên thể hiện hướng chuyển đổi. Phần trong ngoặc vuông thể hiện điều kiện hoặc tác nhân để chuyển đổi xảy ra.

### 1.3. Mô hình máy trạng thái

Một tập hợp trạng thái và các chuyển đổi giữa chúng có thể được biểu diễn bằng máy trạng thái hữu hạn (*finite-state machine*, FSM).

Ở dạng cơ bản, máy trạng thái có:

- Tập trạng thái có thể có.
- Trạng thái khởi đầu.
- Tập sự kiện hoặc đầu vào có thể kích hoạt chuyển đổi.
- Quy tắc chuyển từ trạng thái này sang trạng thái khác.
- Có thể có một hoặc nhiều trạng thái kết thúc.

Có thể ký hiệu một máy trạng thái đơn giản là:

\[
M = (S, E, T, s_0, F)
\]

Trong đó:

- \(S\) là tập trạng thái.
- \(E\) là tập sự kiện hoặc đầu vào.
- \(T\) là tập quy tắc chuyển đổi.
- \(s_0\) là trạng thái khởi đầu.
- \(F\) là tập trạng thái kết thúc, nếu miền bài toán có khái niệm kết thúc.

Một quy tắc trong \(T\) có thể được mô tả bằng bộ ba trạng thái nguồn, sự kiện và trạng thái đích. Khi có điều kiện bảo vệ hoặc hành động, quy tắc sẽ có thêm thông tin tương ứng.

Mô hình này giúp trả lời một câu hỏi quan trọng: từ trạng thái hiện tại, hệ thống cho phép đi đến những trạng thái nào khi nhận một đầu vào cụ thể?

## 2. Vì sao chuyển đổi trạng thái quan trọng trong mô hình miền?

### 2.1. Mô tả vòng đời của đối tượng

Nhiều đối tượng miền không tồn tại ở một trạng thái cố định. Chúng được tạo ra, thay đổi, hoàn tất hoặc bị hủy theo một vòng đời.

Nếu vòng đời chỉ được thể hiện gián tiếp qua nhiều cờ Boolean hoặc điều kiện rải rác, người đọc khó hiểu một đối tượng đang ở giai đoạn nào và bước tiếp theo có thể là gì. Mô hình trạng thái làm rõ các giai đoạn đó.

Ví dụ, một yêu cầu hỗ trợ có thể đi qua:

~~~text
Open -> Assigned -> InProgress -> Resolved -> Closed
~~~

Từ mô hình này, nhóm có thể xác định khi nào yêu cầu được phân công, ai được phép xử lý, điều kiện nào cho phép đánh dấu đã giải quyết và khi nào yêu cầu được đóng.

### 2.2. Bảo vệ quy tắc nghiệp vụ

Quy tắc nghiệp vụ thường phụ thuộc vào trạng thái hiện tại. Không phải thao tác nào cũng hợp lệ ở mọi thời điểm.

Ví dụ:

- Không thể giao một đơn hàng chưa được thanh toán.
- Không thể hoàn tiền cho một giao dịch chưa thu tiền.
- Không thể đóng một yêu cầu hỗ trợ chưa được giải quyết nếu quy trình yêu cầu xác nhận kết quả.
- Không thể kích hoạt tài khoản khi thông tin bắt buộc chưa được xác minh.

Nếu mọi nơi trong ứng dụng đều tự kiểm tra các điều kiện này, cách triển khai dễ bị lặp lại và không nhất quán. Khi quy tắc thay đổi, một số đường xử lý có thể bị bỏ sót.

Đặt quy tắc chuyển đổi tại nơi chịu trách nhiệm về vòng đời của đối tượng giúp các thao tác phải tuân theo cùng một mô hình.

### 2.3. Làm rõ hành vi hợp lệ và không hợp lệ

Một mô hình chuyển đổi xác định cả những gì được phép và những gì bị cấm. Đây là thông tin hữu ích cho lập trình viên, người kiểm thử, người vận hành và chuyên gia nghiệp vụ.

Ví dụ, nếu đơn hàng đã ở trạng thái Delivered, lệnh Ship lần nữa phải bị từ chối. Nếu đơn hàng đã ở trạng thái Cancelled, lệnh Pay có thể không còn hợp lệ. Các trường hợp bị từ chối cũng là một phần của hợp đồng miền.

### 2.4. Hỗ trợ kiểm thử và theo dõi

Khi các chuyển đổi được mô tả rõ ràng, nhóm có thể xây dựng kiểm thử cho từng đường đi, từng điều kiện và từng trường hợp bị từ chối. Hệ thống cũng có thể ghi lại chuyển đổi để giải thích vì sao đối tượng đang ở trạng thái hiện tại.

Lịch sử chuyển đổi hữu ích trong các miền cần kiểm toán, chẳng hạn tài chính, đơn hàng, quản lý hồ sơ hoặc phê duyệt. Bản ghi nên chứa thông tin cần thiết như trạng thái trước, trạng thái sau, thời điểm, tác nhân và lý do, theo yêu cầu của miền.

## 3. Phân biệt trạng thái, lệnh và sự kiện

Ba khái niệm này có liên quan nhưng không đồng nghĩa.

### 3.1. Trạng thái là tình trạng hiện tại

Trạng thái trả lời câu hỏi: **Đối tượng hiện đang ở giai đoạn nào?**

Ví dụ: một đơn hàng đang ở trạng thái PendingPayment.

### 3.2. Lệnh là yêu cầu thực hiện một hành động

Lệnh (*command*) thể hiện mong muốn của người dùng hoặc một thành phần hệ thống. Lệnh có thể thành công hoặc bị từ chối tùy vào trạng thái và quy tắc nghiệp vụ.

Ví dụ:

- SubmitOrder: yêu cầu gửi đơn hàng.
- CancelOrder: yêu cầu hủy đơn hàng.
- ConfirmPayment: yêu cầu xác nhận thanh toán.

Lệnh không khẳng định hành động đã xảy ra. Việc nhận được CancelOrder không có nghĩa đơn hàng chắc chắn đã bị hủy.

### 3.3. Sự kiện là điều đã xảy ra

Sự kiện miền (*domain event*) mô tả một sự việc đã xảy ra và có ý nghĩa với miền.

Ví dụ:

- OrderSubmitted: đơn hàng đã được gửi.
- OrderCancelled: đơn hàng đã bị hủy.
- PaymentReceived: hệ thống đã nhận được thanh toán.

Sự kiện thường được phát ra sau khi quy tắc nghiệp vụ được kiểm tra và thay đổi trạng thái được chấp nhận. Các thành phần khác có thể đăng ký nhận sự kiện để thực hiện công việc tiếp theo.

Luồng xử lý có thể được hình dung như sau:

~~~text
Command
   |
   v
Kiểm tra trạng thái và điều kiện
   |
   v
Thực hiện chuyển đổi
   |
   +----> Cập nhật trạng thái
   |
   +----> Phát sinh Domain Event
~~~

Ví dụ, người dùng gửi lệnh CancelOrder. Đối tượng đơn hàng kiểm tra xem trạng thái hiện tại có cho phép hủy không. Nếu hợp lệ, đối tượng chuyển sang Cancelled và phát sinh OrderCancelled. Nếu không hợp lệ, lệnh bị từ chối và sự kiện OrderCancelled không được phát ra.

Sự kiện bên ngoài như PaymentProviderConfirmed có thể được tiếp nhận và xử lý để tạo ra một chuyển đổi trong miền. Cần xác định rõ sự kiện nào là đầu vào, sự kiện nào là kết quả do chính miền phát ra, tránh đặt tên khiến người đọc nhầm lẫn.

## 4. Các loại điều kiện và hành động trong chuyển đổi

### 4.1. Điều kiện bảo vệ (guard)

Guard là biểu thức phải đúng để một chuyển đổi được phép xảy ra. Guard thường kiểm tra dữ liệu của đối tượng, quyền của tác nhân hoặc kết quả của một quy tắc nghiệp vụ.

Ví dụ, chuyển đơn hàng từ Draft sang PendingPayment có thể yêu cầu:

- Đơn hàng có ít nhất một sản phẩm.
- Địa chỉ giao hàng hợp lệ.
- Giá trị đơn hàng lớn hơn không.
- Người gửi có quyền gửi đơn hàng.

Một guard cần có ngữ nghĩa rõ ràng. Nếu điều kiện sai, hệ thống nên trả về lỗi miền có thể hiểu được, chẳng hạn “đơn hàng chưa có sản phẩm”, thay vì chỉ trả về một lỗi kỹ thuật chung chung.

### 4.2. Hành động khi chuyển đổi

Action là công việc được thực hiện khi chuyển đổi thành công. Có thể chia thành:

- Thay đổi dữ liệu nội bộ của đối tượng.
- Ghi nhận thời điểm hoặc tác nhân thực hiện.
- Tạo sự kiện miền.
- Lập yêu cầu cho một thành phần bên ngoài thực hiện công việc tiếp theo.

Không phải mọi hành động đều nên được thực hiện trực tiếp trong đối tượng miền. Việc gọi dịch vụ thanh toán, gửi email hoặc gọi API vận chuyển thường thuộc trách nhiệm của lớp ứng dụng hoặc một thành phần tích hợp. Đối tượng miền nên bảo vệ quy tắc và biểu diễn thay đổi thuộc về chính nó.

Ví dụ, khi đơn hàng được xác nhận thanh toán, đối tượng có thể chuyển trạng thái sang Paid và phát ra OrderPaid. Một bộ xử lý sự kiện có thể nhận OrderPaid rồi yêu cầu hệ thống kho chuẩn bị hàng.

### 4.3. Hành động khi vào hoặc rời trạng thái

Một số mô hình máy trạng thái hỗ trợ hành động khi đối tượng đi vào (*entry action*) hoặc rời khỏi (*exit action*) một trạng thái.

Ví dụ:

- Khi vào trạng thái InProgress, ghi nhận thời điểm bắt đầu xử lý.
- Khi rời trạng thái InProgress, ghi nhận thời lượng xử lý.
- Khi vào trạng thái Closed, khóa việc chỉnh sửa nội dung yêu cầu.

Các hành động này cần được dùng có chủ đích. Nếu chúng gây tác động bên ngoài hoặc có thể thất bại độc lập với việc lưu trạng thái, cần thiết kế cách xử lý lỗi và thử lại phù hợp.

### 4.4. Chuyển đổi tự động và chuyển đổi có tác nhân

Một số chuyển đổi xảy ra do người dùng hoặc hệ thống gửi lệnh, chẳng hạn khách hàng yêu cầu hủy đơn. Một số chuyển đổi có thể xảy ra do thời gian hoặc điều kiện tự động, chẳng hạn yêu cầu hết hạn sau một khoảng thời gian.

Với chuyển đổi theo thời gian, cần xác định:

- Mốc thời gian được tính từ đâu.
- Múi giờ và cách xử lý thời gian mùa hè nếu liên quan.
- Hệ thống nào chịu trách nhiệm kích hoạt.
- Điều gì xảy ra nếu bộ lập lịch chạy trễ hoặc chạy lặp.
- Cách bảo đảm cùng một chuyển đổi không được áp dụng sai nhiều lần.

Một bộ lập lịch thường gửi lệnh hoặc sự kiện đến mô hình miền. Quy tắc chuyển đổi vẫn cần được xác thực ở nơi có thẩm quyền thay đổi trạng thái.

## 5. Ví dụ mô hình vòng đời đơn hàng

Xét một hệ thống bán hàng có vòng đời đơn hàng đơn giản. Đơn hàng được tạo ở trạng thái Draft. Khi khách hàng gửi đơn, hệ thống kiểm tra thông tin và chuyển sang PendingPayment. Sau khi nhận đủ tiền, đơn hàng chuyển sang Paid. Khi hàng được bàn giao cho đơn vị vận chuyển, đơn hàng chuyển sang Shipped. Khi xác nhận giao thành công, đơn hàng chuyển sang Delivered.

Đơn hàng cũng có thể bị hủy ở một số giai đoạn trước khi giao hàng. Quy tắc cụ thể phụ thuộc vào chính sách nghiệp vụ, ví dụ có thể cho phép hủy khi đang chờ thanh toán hoặc đã thanh toán nhưng kho chưa bàn giao hàng.

### 5.1. Sơ đồ chuyển đổi

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> PendingPayment: SubmitOrder
    Draft --> Cancelled: CancelOrder
    PendingPayment --> Paid: PaymentConfirmed
    PendingPayment --> Cancelled: CancelOrder
    Paid --> Shipped: ShipmentDispatched
    Paid --> Cancelled: CancelApproved
    Shipped --> Delivered: DeliveryConfirmed
    Delivered --> [*]
    Cancelled --> [*]
~~~

Sơ đồ minh họa một vòng đời có nhiều nhánh. Trong hệ thống thực tế, chuyển đổi Paid sang Cancelled có thể yêu cầu quy trình hoàn tiền hoặc xác nhận từ kho. Sơ đồ chỉ thể hiện trạng thái; điều kiện và hành động chi tiết cần được mô tả thêm.

### 5.2. Bảng chuyển đổi

| Trạng thái hiện tại | Tác nhân hoặc sự kiện | Điều kiện | Trạng thái tiếp theo |
|---|---|---|---|
| Draft | SubmitOrder | Có sản phẩm và địa chỉ giao hàng hợp lệ | PendingPayment |
| Draft | CancelOrder | Đơn hàng thuộc quyền của người yêu cầu | Cancelled |
| PendingPayment | PaymentConfirmed | Số tiền nhận đủ và giao dịch hợp lệ | Paid |
| PendingPayment | CancelOrder | Chưa có thanh toán được xác nhận | Cancelled |
| Paid | ShipmentDispatched | Kho đã xác nhận bàn giao hàng | Shipped |
| Paid | CancelApproved | Chính sách cho phép hủy và đã xử lý nghĩa vụ hoàn tiền | Cancelled |
| Shipped | DeliveryConfirmed | Đơn vị vận chuyển xác nhận giao thành công | Delivered |

Bảng này giúp phát hiện các câu hỏi nghiệp vụ cần được trả lời trước khi triển khai:

- Đơn hàng có thể được gửi lại sau khi đã hủy không?
- Nếu thanh toán đến sau khi đơn hàng bị hủy thì xử lý thế nào?
- Có cho phép hủy khi hàng đã được bàn giao cho đơn vị vận chuyển không?
- Đơn hàng đã giao có thể chuyển lại sang trạng thái khác không?
- Ai có quyền xác nhận từng chuyển đổi?

Không nên tự suy đoán câu trả lời cho những trường hợp ảnh hưởng đến chính sách nghiệp vụ. Chúng cần được thống nhất với người chịu trách nhiệm về miền.

### 5.3. Biểu diễn bằng một DSL minh họa

Một DSL có thể mô tả máy trạng thái bằng cú pháp chuyên biệt. Ví dụ sau chỉ minh họa ý tưởng; đây không phải cú pháp chuẩn của một thư viện cụ thể:

~~~text
stateMachine OrderLifecycle {
    initial Draft

    state Draft
    state PendingPayment
    state Paid
    state Shipped
    state Delivered final
    state Cancelled final

    transition SubmitOrder {
        from Draft
        to PendingPayment
        guard order.hasItems && order.hasValidShippingAddress
        emit OrderSubmitted
    }

    transition PaymentConfirmed {
        from PendingPayment
        to Paid
        guard payment.amount == order.total
        emit OrderPaid
    }

    transition ShipmentDispatched {
        from Paid
        to Shipped
        guard shipment.isAcceptedByCarrier
        emit OrderShipped
    }

    transition DeliveryConfirmed {
        from Shipped
        to Delivered
        emit OrderDelivered
    }
}
~~~

Trong ví dụ:

- Khai báo state liệt kê các trạng thái hợp lệ.
- initial xác định trạng thái khởi đầu.
- final đánh dấu trạng thái kết thúc của vòng đời.
- from và to xác định trạng thái nguồn và trạng thái đích.
- guard chứa điều kiện cho phép chuyển đổi.
- emit mô tả sự kiện miền được phát ra khi chuyển đổi thành công.

Một DSL thực tế cần định nghĩa rõ cú pháp, kiểu dữ liệu, cách tham chiếu thuộc tính miền và cách thực thi. Không nên coi ví dụ minh họa này là định dạng có thể chạy trực tiếp.

### 5.4. Biểu diễn trong mã Java

Với một vòng đời nhỏ, có thể biểu diễn trạng thái bằng enum và đặt hành vi chuyển đổi trong đối tượng miền:

~~~java
public enum OrderStatus {
    DRAFT,
    PENDING_PAYMENT,
    PAID,
    SHIPPED,
    DELIVERED,
    CANCELLED
}
~~~

Đối tượng đơn hàng cung cấp các phương thức nghiệp vụ thay vì cho phép mọi thành phần tùy ý gán trạng thái:

~~~java
public class Order {
    private OrderStatus status = OrderStatus.DRAFT;

    public void submit() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be submitted"
            );
        }

        if (items.isEmpty() || shippingAddress == null) {
            throw new IllegalStateException(
                "Order requires items and a shipping address"
            );
        }

        status = OrderStatus.PENDING_PAYMENT;
        registerEvent(new OrderSubmitted(id));
    }

    public void confirmPayment(Money receivedAmount) {
        if (status != OrderStatus.PENDING_PAYMENT) {
            throw new IllegalStateException(
                "Order is not waiting for payment"
            );
        }

        if (!receivedAmount.equals(total)) {
            throw new IllegalArgumentException(
                "Received amount does not match order total"
            );
        }

        status = OrderStatus.PAID;
        registerEvent(new OrderPaid(id));
    }
}
~~~

Đây là ví dụ rút gọn để minh họa cách đóng gói quy tắc. Một ứng dụng thực tế cần định nghĩa các trường, kiểu tiền tệ, lỗi miền, cơ chế lưu sự kiện và giao dịch phù hợp.

Ưu điểm của cách làm này là trạng thái được thay đổi thông qua hành vi có ý nghĩa nghiệp vụ. Thành phần bên ngoài không cần biết chi tiết nội bộ để yêu cầu đơn hàng được gửi hoặc xác nhận thanh toán.

## 6. Tổ chức chuyển đổi trong mô hình miền

### 6.1. Đặt quyền thay đổi trạng thái đúng nơi

Trong thiết kế hướng miền (*Domain-Driven Design*, DDD), một Aggregate là ranh giới nhất quán cho một nhóm đối tượng miền. Aggregate Root chịu trách nhiệm bảo vệ các bất biến của aggregate.

Nếu trạng thái thuộc vòng đời của một aggregate, các chuyển đổi quan trọng thường nên được thực hiện thông qua hành vi của Aggregate Root. Điều này giúp mọi thay đổi đều đi qua cùng một điểm kiểm tra quy tắc.

Ví dụ, Order có thể là Aggregate Root và sở hữu trạng thái đơn hàng. Một controller không nên tự đặt Order.status thành Paid sau khi nhận một yêu cầu HTTP. Thay vào đó, lớp ứng dụng gọi phương thức nghiệp vụ như confirmPayment, còn Order tự kiểm tra điều kiện chuyển đổi.

Không phải mọi trạng thái trong hệ thống đều cần thuộc một aggregate lớn. Nếu hai đối tượng có vòng đời độc lập và không cần cập nhật nguyên tử cùng nhau, ép chúng vào cùng một aggregate có thể làm tăng phụ thuộc và giảm khả năng mở rộng.

### 6.2. Bảo vệ bất biến

Bất biến (*invariant*) là điều kiện phải luôn đúng đối với mô hình miền ở những ranh giới nhất quán.

Ví dụ:

- Đơn hàng đã giao phải có thông tin giao hàng thành công.
- Đơn hàng đã thanh toán phải có tham chiếu đến giao dịch thanh toán hợp lệ.
- Đơn hàng đã hủy không được tiếp tục chuyển sang Shipped.
- Số lượng sản phẩm trong đơn hàng không được âm.

Guard kiểm tra điều kiện của một chuyển đổi cụ thể. Invariant áp dụng rộng hơn, bảo đảm trạng thái và dữ liệu của đối tượng luôn nhất quán sau các hành vi được phép.

Một chuyển đổi có thể thỏa guard nhưng vẫn vi phạm invariant nếu phần cập nhật dữ liệu được thiết kế không đầy đủ. Vì vậy, cần xác định cả hai loại quy tắc.

### 6.3. Tránh thay đổi trạng thái tùy ý

Một thiết kế dễ gây lỗi là để trạng thái có thể được gán từ bất kỳ lớp nào:

~~~java
order.setStatus(OrderStatus.DELIVERED);
~~~

Lệnh gán này không cho biết đơn hàng đã được giao bằng cách nào, có đủ điều kiện hay không và sự kiện miền nào cần được phát ra. Nó cũng cho phép bỏ qua những bước trung gian bắt buộc.

Nên cung cấp hành vi có ý nghĩa:

~~~java
order.confirmDelivery(deliveryConfirmation);
~~~

Phương thức có thể kiểm tra trạng thái hiện tại, xác minh thông tin giao hàng, cập nhật dữ liệu liên quan và ghi nhận sự kiện miền. Nếu có trường hợp quản trị cần sửa dữ liệu đặc biệt, nên mô hình hóa quyền và lý do của thao tác đó một cách rõ ràng.

### 6.4. Tách quy tắc miền khỏi điều phối kỹ thuật

Lớp ứng dụng thường chịu trách nhiệm điều phối một use case:

1. Nhận lệnh từ giao diện hoặc API.
2. Tải aggregate cần xử lý.
3. Gọi hành vi miền.
4. Lưu thay đổi trong giao dịch.
5. Phát hoặc chuyển tiếp sự kiện sau khi giao dịch thành công.

Đối tượng miền chịu trách nhiệm xác định hành vi đó có hợp lệ và trạng thái mới phải như thế nào. Hạ tầng chịu trách nhiệm lưu trữ, truyền thông điệp và tích hợp dịch vụ.

Sự phân chia này giúp mô hình miền tập trung vào quy tắc nghiệp vụ mà không phải phụ thuộc trực tiếp vào HTTP, cơ sở dữ liệu hoặc nhà cung cấp dịch vụ bên ngoài.

## 7. Xử lý các trường hợp phức tạp

### 7.1. Chuyển đổi không hợp lệ

Khi một lệnh không phù hợp với trạng thái hiện tại, hệ thống cần từ chối hoặc xử lý theo một quy tắc nghiệp vụ đã định nghĩa.

Ví dụ, lệnh ShipOrder gửi đến một đơn hàng đang ở Draft phải bị từ chối. Không nên âm thầm chuyển đơn hàng qua Paid rồi Shipped chỉ để làm cho lệnh thành công.

Lỗi nên phản ánh nguyên nhân miền, chẳng hạn:

- OrderCannotBeShippedBeforePayment.
- OrderAlreadyCancelled.
- PaymentAmountMismatch.

Thông báo lỗi rõ ràng giúp giao diện hiển thị hướng xử lý phù hợp và giúp người vận hành tìm nguyên nhân.

### 7.2. Lệnh lặp và tính idempotent

Trong hệ thống phân tán, một thông điệp có thể được gửi lại do timeout, mất phản hồi hoặc cơ chế retry. Vì vậy, cùng một lệnh có thể đến nhiều lần.

Tính idempotent có nghĩa là thực hiện một thao tác lặp lại không làm phát sinh thêm tác động ngoài ý muốn sau lần xử lý thành công đầu tiên.

Ví dụ, nếu hệ thống nhận hai thông báo xác nhận cùng một giao dịch thanh toán, nó không nên ghi nhận thanh toán hai lần hoặc phát sinh hai lần hành động giao hàng.

Có thể sử dụng mã định danh giao dịch, khóa idempotency hoặc kiểm tra sự kiện đã xử lý. Cần phân biệt hai trường hợp:

- Cùng một lệnh được gửi lại vì chưa nhận được phản hồi.
- Hai lệnh riêng biệt có nội dung giống nhau nhưng đại diện cho hai ý định khác nhau.

Quy tắc miền và cơ chế lưu trữ cần phối hợp để xác định cách xử lý chính xác.

### 7.3. Đồng thời và xung đột cập nhật

Hai yêu cầu có thể cùng đọc một trạng thái rồi cùng cố gắng chuyển đổi đối tượng. Ví dụ, hai nhân viên đồng thời xác nhận một đơn hàng đã được giao.

Nếu cả hai thao tác đều dựa trên cùng một trạng thái cũ mà không có kiểm soát đồng thời, hệ thống có thể ghi đè kết quả hoặc phát sinh sự kiện trùng lặp.

Các kỹ thuật thường dùng gồm:

- Khóa lạc quan bằng version hoặc trường cập nhật.
- Giao dịch cơ sở dữ liệu với mức cô lập phù hợp.
- Ràng buộc duy nhất cho mã giao dịch hoặc sự kiện.
- Kiểm tra lại trạng thái trong cùng giao dịch cập nhật.

Ví dụ, khi lưu aggregate, hệ thống chỉ cập nhật nếu version hiện tại vẫn bằng version đã đọc. Nếu version đã thay đổi, thao tác cần được tải lại và xử lý theo trạng thái mới.

### 7.4. Giao dịch và sự kiện miền

Một chuyển đổi thường cần lưu trạng thái mới và ghi nhận sự kiện miền một cách nhất quán. Nếu trạng thái đã được lưu nhưng sự kiện bị mất, các thành phần phụ thuộc có thể không biết rằng chuyển đổi đã xảy ra. Nếu sự kiện được phát ra nhưng giao dịch lưu trạng thái thất bại, thành phần nhận có thể xử lý một sự việc chưa thực sự được xác nhận.

Mẫu Transactional Outbox thường được dùng để giải quyết vấn đề này. Ứng dụng ghi thay đổi aggregate và bản ghi sự kiện vào cùng một giao dịch cơ sở dữ liệu. Một tiến trình khác đọc outbox và gửi sự kiện đến hệ thống nhắn tin. Việc gửi có thể lặp, vì vậy bên nhận vẫn cần xử lý idempotent.

Không phải mọi ứng dụng đều cần Outbox. Với hệ thống nhỏ hoặc không có nhu cầu tích hợp bất đồng bộ, một cơ chế giao dịch đơn giản có thể đủ. Quyết định nên dựa trên yêu cầu nhất quán và khả năng chịu lỗi.

### 7.5. Từ chối, thử lại và bù trừ

Không phải mọi chuyển đổi đều thành công ngay lần đầu. Một dịch vụ bên ngoài có thể tạm thời không khả dụng, thanh toán có thể đang chờ xác nhận hoặc kho có thể chưa sẵn sàng.

Cần phân biệt:

- **Từ chối nghiệp vụ:** điều kiện không hợp lệ, chẳng hạn đơn hàng không đủ thông tin.
- **Lỗi kỹ thuật tạm thời:** có thể thử lại, chẳng hạn timeout khi gọi dịch vụ.
- **Kết quả chưa xác định:** yêu cầu đã gửi nhưng chưa biết hệ thống bên ngoài đã xử lý hay chưa.
- **Bù trừ:** một hành động nghiệp vụ khác được thực hiện để xử lý hậu quả của bước trước, chẳng hạn hoàn tiền sau khi không thể hoàn tất giao hàng.

Bù trừ không phải lúc nào cũng là đảo ngược chính xác thao tác cũ. Ví dụ, một khoản hoàn tiền là một giao dịch mới có ý nghĩa riêng, không phải xóa lịch sử thanh toán đã xảy ra.

### 7.6. Trạng thái kết thúc và trạng thái có thể mở lại

Một số trạng thái kết thúc vòng đời, chẳng hạn Delivered hoặc Cancelled. Tuy nhiên, có miền cho phép mở lại đối tượng đã đóng.

Nếu việc mở lại được phép, nên mô hình hóa nó thành một chuyển đổi có tên, điều kiện và quyền rõ ràng. Ví dụ, ReopenTicket có thể chỉ được phép trong một khoảng thời gian và bởi người dùng có quyền.

Không nên coi trạng thái kết thúc là bất biến tuyệt đối nếu nghiệp vụ có quy trình mở lại. Ngược lại, nếu nghiệp vụ cấm quay lại, mô hình phải thể hiện rõ điều đó.

## 8. Trạng thái đơn giản, trạng thái kết hợp và state explosion

### 8.1. Một trường trạng thái đơn giản

Một enum có thể đủ khi đối tượng có một vòng đời tuyến tính hoặc chỉ có một số nhánh nhỏ. Ví dụ, trạng thái đơn hàng cơ bản có thể được lưu bằng một trường status.

Tuy nhiên, khi có nhiều khía cạnh hoạt động độc lập, việc gộp tất cả vào một enum có thể tạo ra quá nhiều trạng thái.

### 8.2. Vấn đề state explosion

Giả sử một yêu cầu hỗ trợ có ba khía cạnh độc lập:

- Tiến độ xử lý: Open, InProgress, Resolved.
- Thanh toán: Unpaid, Paid, Refunded.
- Mức ưu tiên: Normal, High, Critical.

Nếu gộp thành một trạng thái duy nhất, số tổ hợp lý thuyết có thể lên đến:

\[
3 \times 3 \times 3 = 27
\]

Khi thêm khía cạnh khác, số trạng thái tăng nhanh. Đây là hiện tượng state explosion.

Một cách mô hình hóa tốt hơn là tách các vòng đời độc lập thành những máy trạng thái riêng, nếu nghiệp vụ cho phép chúng thay đổi độc lập. Ví dụ, trạng thái thanh toán không nhất thiết phải trở thành một phần của mọi tên trạng thái xử lý yêu cầu.

Việc tách không có nghĩa là bỏ qua quan hệ giữa các khía cạnh. Nếu một chuyển đổi ở tiến độ xử lý phụ thuộc vào thanh toán, guard phải kiểm tra điều kiện đó một cách rõ ràng.

### 8.3. Trạng thái phân cấp

Máy trạng thái phân cấp cho phép nhóm nhiều trạng thái con dưới một trạng thái cha. Ví dụ, trạng thái InProgress có thể chứa các trạng thái con như Assigned, Investigating và WaitingForCustomer.

Cách tổ chức này giúp giảm lặp lại khi nhiều trạng thái con cùng chia sẻ một quy tắc. Chẳng hạn, tất cả trạng thái con của InProgress đều có thể cho phép thêm ghi chú xử lý.

Một DSL hỗ trợ trạng thái phân cấp cần định nghĩa rõ cách kế thừa chuyển đổi, guard và hành động giữa trạng thái cha và trạng thái con.

### 8.4. Các trạng thái song song

Một số hệ thống có nhiều khía cạnh hoạt động đồng thời. Ví dụ, một quy trình đặt chỗ có thể đồng thời chờ xác nhận thanh toán và xác nhận chỗ từ nhà cung cấp.

Nếu hai tiến trình thực sự độc lập, mô hình có thể biểu diễn chúng bằng các vùng trạng thái song song. Khi một bước tổng thể chỉ được hoàn tất sau khi cả hai nhánh xong, quy tắc kết hợp cần được mô tả rõ.

Không nên dùng trạng thái song song chỉ để làm sơ đồ ngắn hơn. Cần xác định cách xử lý khi một nhánh thành công còn nhánh kia thất bại, hết hạn hoặc bị hủy.

## 9. Chuyển đổi trạng thái trong DSL: lợi ích và giới hạn

### 9.1. Lợi ích

Khi DSL biểu diễn chuyển đổi trạng thái một cách có cấu trúc, nhóm phát triển có thể:

- Đọc vòng đời đối tượng bằng thuật ngữ nghiệp vụ.
- Tập trung định nghĩa các trạng thái và chuyển đổi ở một nơi.
- Kiểm tra trạng thái nguồn, trạng thái đích và guard.
- Phát hiện trạng thái không thể đi tới hoặc chuyển đổi không có đích.
- Sinh sơ đồ và tài liệu từ cùng một định nghĩa.
- Tạo bộ kiểm thử cho các đường chuyển đổi.
- So sánh thay đổi vòng đời giữa các phiên bản.

Ví dụ, công cụ có thể cảnh báo một trạng thái không thể đạt tới từ trạng thái khởi đầu, hoặc một trạng thái không kết thúc có đường đi nào đến trạng thái kết thúc. Những kiểm tra này giúp phát hiện một số lỗi mô hình trước khi chạy.

### 9.2. Giới hạn

DSL không tự quyết định được quy tắc nghiệp vụ đúng. Người thiết kế vẫn phải hiểu miền, thống nhất điều kiện và xử lý trường hợp ngoại lệ.

Một DSL quá đơn giản có thể không biểu diễn được guard phức tạp, trạng thái phân cấp hoặc các hành động có điều kiện. Một DSL quá mạnh có thể trở thành ngôn ngữ lập trình tổng quát với chi phí phân tích, bảo mật và bảo trì lớn.

DSL cũng không thay thế các cơ chế bảo đảm nhất quán ở thời điểm chạy. Một mô hình tĩnh có thể cho biết chuyển đổi hợp lệ về mặt cấu trúc, nhưng hệ thống vẫn cần xác thực dữ liệu thực tế, quyền truy cập, giao dịch và xung đột đồng thời.

### 9.3. Khi nào nên dùng DSL cho state machine?

DSL hoặc thư viện state machine chuyên biệt đáng cân nhắc khi:

- Vòng đời có nhiều trạng thái và nhánh chuyển đổi.
- Quy tắc thường xuyên thay đổi theo chính sách nghiệp vụ.
- Nhiều thành phần cần dùng chung một mô hình chuyển đổi.
- Cần sinh sơ đồ, tài liệu hoặc kiểm thử tự động.
- Người dùng có chuyên môn miền cần đọc hoặc xem xét định nghĩa.

Với một đối tượng chỉ có hai hoặc ba trạng thái và vài hành vi, enum cùng các phương thức miền có thể dễ hiểu và ít chi phí hơn. Mục tiêu là chọn mức mô hình hóa tương xứng với độ phức tạp thực tế.

## 10. Quy trình xây dựng mô hình chuyển đổi trạng thái

Có thể thực hiện theo các bước sau:

1. **Chọn đối tượng hoặc aggregate:** xác định đối tượng nào sở hữu vòng đời và có quyền thay đổi trạng thái.
2. **Xác định các trạng thái có ý nghĩa:** dùng thuật ngữ miền, tránh tạo trạng thái chỉ để phản ánh chi tiết kỹ thuật.
3. **Xác định trạng thái khởi đầu và kết thúc:** làm rõ đối tượng bắt đầu ở đâu và khi nào vòng đời được xem là hoàn tất.
4. **Liệt kê lệnh và sự kiện kích hoạt:** phân biệt yêu cầu thực hiện với sự kiện đã xảy ra.
5. **Xác định chuyển đổi hợp lệ:** với từng trạng thái nguồn, xác định trạng thái đích có thể đạt tới.
6. **Viết guard:** nêu điều kiện dữ liệu, quyền và chính sách cần thỏa mãn.
7. **Xác định hành động và sự kiện miền:** làm rõ dữ liệu nào thay đổi và sự kiện nào được phát ra.
8. **Xác định trường hợp bị từ chối:** quy định lỗi miền cho chuyển đổi không hợp lệ.
9. **Xem xét đồng thời và thử lại:** kiểm tra thông điệp trùng, xung đột cập nhật và lỗi tích hợp.
10. **Kiểm thử và tài liệu hóa:** kiểm thử đường đi hợp lệ, đường đi không hợp lệ và các trường hợp biên.

Một bảng chuyển đổi thường là công cụ tốt để trao đổi với chuyên gia miền trước khi chọn cú pháp DSL hoặc viết mã.

## 11. Kiểm thử chuyển đổi trạng thái

### 11.1. Kiểm thử chuyển đổi hợp lệ

Với mỗi chuyển đổi, cần kiểm tra rằng:

- Trạng thái ban đầu đúng.
- Guard được thỏa mãn.
- Trạng thái sau chuyển đổi đúng.
- Dữ liệu liên quan được cập nhật đúng.
- Sự kiện miền cần thiết được ghi nhận.

Ví dụ: khi đơn hàng ở PendingPayment và nhận xác nhận thanh toán đủ tiền, kết quả phải là Paid và có sự kiện OrderPaid.

### 11.2. Kiểm thử chuyển đổi bị từ chối

Kiểm thử trường hợp không hợp lệ giúp bảo đảm quy tắc không bị bỏ qua:

- Gửi đơn hàng không có sản phẩm.
- Thanh toán khi đơn hàng đã bị hủy.
- Giao hàng trước khi thanh toán.
- Hủy đơn hàng sau khi đã giao.
- Xác nhận cùng một giao dịch nhiều lần.

Ngoài việc kiểm tra lỗi trả về, cần xác nhận trạng thái và dữ liệu không bị thay đổi ngoài ý muốn.

### 11.3. Kiểm thử guard và trường hợp biên

Với guard dựa trên số tiền, thời gian hoặc quyền, cần kiểm tra giá trị ở hai phía ranh giới:

- Số tiền thấp hơn, bằng và cao hơn số tiền cần thanh toán.
- Thời điểm trước, đúng tại và sau thời hạn.
- Người có quyền và người không có quyền.
- Dữ liệu đầy đủ, thiếu hoặc không hợp lệ.

### 11.4. Kiểm thử đường đi và khả năng đạt tới

Một đối tượng có thể đi qua nhiều chuyển đổi liên tiếp. Cần kiểm thử những đường đi quan trọng từ trạng thái khởi đầu đến trạng thái kết thúc.

Với máy trạng thái lớn, có thể dùng công cụ để kiểm tra:

- Trạng thái không thể đạt tới.
- Chuyển đổi không thể được kích hoạt.
- Trạng thái không có đường thoát ngoài ý muốn.
- Đường đi có thể bỏ qua một bước nghiệp vụ bắt buộc.

Kiểm tra cấu trúc không thay thế kiểm thử nghiệp vụ, nhưng có thể phát hiện lỗi trong mô hình.

### 11.5. Kiểm thử đồng thời và phục hồi

Nếu hệ thống nhận thông điệp bất đồng bộ hoặc nhiều yêu cầu đồng thời, cần kiểm thử:

- Hai lệnh cùng cố gắng thực hiện một chuyển đổi.
- Một thông điệp được gửi lại sau timeout.
- Ứng dụng dừng sau khi lưu trạng thái nhưng trước khi gửi sự kiện.
- Dịch vụ bên ngoài trả kết quả trễ hoặc lặp.
- Phiên bản mô hình mới xử lý dữ liệu cũ.

Các kiểm thử này xác nhận tính nhất quán của toàn bộ luồng xử lý, không chỉ riêng hàm chuyển đổi.

## 12. Những lỗi thiết kế thường gặp

### 12.1. Dùng quá nhiều cờ Boolean thay cho trạng thái

Một đối tượng có các cờ như isPaid, isShipped, isCancelled và isDelivered có thể tạo ra nhiều tổ hợp mâu thuẫn. Ví dụ, đơn hàng vừa isCancelled vừa isShipped.

Nếu các giá trị loại trừ lẫn nhau, một trạng thái rõ ràng thường dễ bảo vệ hơn. Nếu chúng thực sự là các khía cạnh độc lập, nên mô hình hóa từng khía cạnh và xác định quan hệ giữa chúng.

### 12.2. Cho phép mọi chuyển đổi đến mọi trạng thái

Một phương thức setStatus tổng quát cho phép bỏ qua vòng đời. Người gọi có thể chuyển trực tiếp từ Draft sang Delivered dù chưa thanh toán hoặc giao hàng.

Nên định nghĩa hành vi nghiệp vụ cụ thể và chỉ cho phép các chuyển đổi đã được mô hình hóa.

### 12.3. Trộn trạng thái nghiệp vụ với trạng thái kỹ thuật

Các giá trị như PROCESSING, RETRYING hoặc TIMEOUT có thể mô tả trạng thái của một tác vụ kỹ thuật. Chúng không nhất thiết là trạng thái miền của đơn hàng hay tài khoản.

Nếu trộn hai loại trạng thái, mô hình miền sẽ phụ thuộc vào chi tiết triển khai. Nên xác định đối tượng nào sở hữu từng vòng đời và vì sao trạng thái đó có ý nghĩa nghiệp vụ.

### 12.4. Đưa mọi tác động bên ngoài vào chuyển đổi đồng bộ

Nếu phương thức chuyển trạng thái vừa cập nhật đối tượng, vừa gọi thanh toán, gửi email và gọi dịch vụ vận chuyển, một lỗi mạng có thể khiến kết quả trở nên không rõ ràng.

Nên giữ hành vi miền tập trung vào quy tắc và thay đổi nội bộ. Các tác động bên ngoài thường được điều phối qua sự kiện, hàng đợi hoặc lớp ứng dụng với cơ chế retry và quan sát phù hợp.

### 12.5. Không xác định cách xử lý sự kiện đến muộn

Trong hệ thống phân tán, sự kiện có thể đến không theo thứ tự dự kiến. Ví dụ, xác nhận thanh toán đến sau khi lệnh hủy đã được chấp nhận.

Mô hình cần quy định cách xử lý tình huống này: từ chối, chuyển sang quy trình hoàn tiền, đưa vào hàng chờ xử lý thủ công hoặc áp dụng một chính sách khác. Không nên dựa vào giả định rằng thông điệp luôn đến đúng thứ tự.

### 12.6. Dùng tên trạng thái mơ hồ

Các tên như Done, Active hoặc Processed có thể mang nhiều nghĩa. Một trạng thái nên diễn đạt rõ tình trạng mà nghiệp vụ quan tâm.

Ví dụ, thay vì dùng Done cho mọi trường hợp, có thể phân biệt Resolved và Closed nếu hai giai đoạn có quy tắc khác nhau.

## 13. Câu hỏi tự đánh giá

1. Trạng thái và chuyển đổi trạng thái khác nhau như thế nào?
2. Một chuyển đổi thường gồm những thành phần nào? Guard có vai trò gì?
3. Phân biệt command và domain event bằng ví dụ hủy đơn hàng.
4. Vì sao không nên để controller tùy ý gán trạng thái của aggregate?
5. Invariant khác guard của một chuyển đổi như thế nào?
6. Khi nào enum là đủ và khi nào nên cân nhắc state machine hoặc DSL?
7. State explosion là gì? Có thể giảm vấn đề này bằng cách nào?
8. Vì sao hệ thống cần xử lý lệnh lặp và sự kiện đến muộn?
9. Transactional Outbox giải quyết vấn đề nhất quán nào?
10. Những đường chuyển đổi nào cần được kiểm thử trong vòng đời đơn hàng?

## Kết luận

Chuyển đổi trạng thái mô tả cách một đối tượng miền thay đổi qua vòng đời của nó. Một mô hình rõ ràng xác định trạng thái, tác nhân kích hoạt, điều kiện bảo vệ, hành động và trạng thái đích. Nhờ đó, hệ thống có thể bảo vệ quy tắc nghiệp vụ, từ chối hành vi không hợp lệ và giải thích vì sao một đối tượng đang ở trạng thái hiện tại.

Khi vòng đời có nhiều nhánh hoặc cần được chia sẻ giữa nhiều thành phần, DSL hoặc công cụ state machine có thể giúp biểu diễn và kiểm tra quy tắc tập trung. Với vòng đời nhỏ, các phương thức miền và enum thường đã đủ. Dù chọn cách nào, quyền thay đổi trạng thái cần được đặt đúng nơi, bất biến phải được bảo vệ, và các vấn đề giao dịch, đồng thời, thử lại cùng sự kiện phân tán phải được xử lý theo yêu cầu thực tế của miền.
