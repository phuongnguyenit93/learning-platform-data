# Phân biệt điều phối quy trình với quyết định thuộc quy tắc nghiệp vụ

Bài học này thuộc module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED`, nhằm giúp người học tổ chức phần mềm theo kiến trúc phân tầng. Trong chương **Tầng ứng dụng**, ta tập trung vào ranh giới giữa hai loại trách nhiệm thường bị trộn lẫn: điều phối một quy trình để hoàn thành ca sử dụng và quyết định điều gì được phép theo quy tắc nghiệp vụ.

## 1. Hai câu hỏi khác nhau

Khi xử lý một yêu cầu, hãy tách hai câu hỏi:

- **Quy trình cần thực hiện những bước nào, theo thứ tự nào?** Đây là câu hỏi về điều phối. Tầng ứng dụng thường chịu trách nhiệm tải dữ liệu cần thiết, gọi các đối tượng hoặc dịch vụ phù hợp, mở ranh giới giao dịch, lưu kết quả và phối hợp với hệ thống bên ngoài.
- **Trong nghiệp vụ, hành động này có hợp lệ không và kết quả phải là gì?** Đây là câu hỏi về quy tắc nghiệp vụ. Quyết định này thuộc mô hình miền hoặc thành phần nghiệp vụ sở hữu quy tắc đó.

Ví dụ, khi khách hàng yêu cầu hủy đơn hàng, quy trình có thể là tìm đơn hàng, yêu cầu đơn hàng tự xử lý việc hủy, lưu trạng thái mới và phát thông báo cho phần xử lý hoàn tiền. Nhưng việc đơn hàng đã giao có được hủy hay không, hoặc khách hàng còn trong thời hạn được hủy hay không, là quyết định nghiệp vụ.

Tầng ứng dụng trả lời câu hỏi **làm các bước nào và phối hợp chúng ra sao**. Miền nghiệp vụ trả lời câu hỏi **điều gì đúng theo chính sách của hệ thống**. Đây là cách phân chia trách nhiệm, không phải yêu cầu mọi dự án phải có một số lượng lớp hay cách đặt package cố định.

## 2. Trách nhiệm của tầng ứng dụng

Một use case hoặc application service thường đại diện cho một hành động mà hệ thống cung cấp, chẳng hạn `CancelOrder`, `PlaceOrder` hoặc `RegisterCustomer`. Nó điều phối các bước để hành động đó hoàn tất.

Các trách nhiệm thường gặp gồm:

| Trách nhiệm | Ví dụ |
|---|---|
| Tiếp nhận dữ liệu ca sử dụng | Nhận `CancelOrderCommand` chứa mã đơn và lý do hủy |
| Tải dữ liệu qua cổng | Gọi `OrderRepository.findById(...)` |
| Điều phối lời gọi nghiệp vụ | Gọi `order.cancel(...)` để yêu cầu đối tượng miền thực hiện quy tắc |
| Quản lý ranh giới giao dịch | Đảm bảo thay đổi trạng thái và lưu đơn hàng nằm trong giao dịch phù hợp |
| Phối hợp hệ thống ngoài | Ghi sự kiện vào outbox hoặc yêu cầu cổng thanh toán hoàn tiền theo quy trình |
| Trả kết quả ca sử dụng | Trả mã đơn hàng, kết quả hoặc lỗi phù hợp với hợp đồng ứng dụng |

Application service không nên trở thành nơi tập trung mọi quy tắc chỉ vì nó là điểm bắt đầu của luồng xử lý. Nếu service tự kiểm tra trạng thái, thời hạn, hạn mức và quyền lợi rồi tự thay đổi dữ liệu, quy tắc sẽ khó được bảo vệ khi một luồng khác cũng cần sử dụng chúng.

## 3. Trách nhiệm của miền nghiệp vụ

Quy tắc nghiệp vụ mô tả chính sách và bất biến mà hệ thống phải giữ, bất kể yêu cầu đến từ HTTP, tác vụ nền, giao diện dòng lệnh hay một dịch vụ khác. Chúng thường gồm:

- Trạng thái nào được phép chuyển sang trạng thái nào.
- Một đơn hàng có được hủy tại thời điểm hiện tại hay không.
- Số lượng đặt hàng có hợp lệ và có vượt giới hạn cho phép không.
- Chiết khấu có áp dụng cho khách hàng hoặc loại sản phẩm này không.
- Số dư có đủ để thực hiện giao dịch hay không.

Quy tắc nên nằm ở nơi có đủ dữ liệu và ngữ nghĩa để diễn đạt nó. Nếu quy tắc liên quan đến một đối tượng miền, hãy cân nhắc đặt hành vi trên chính đối tượng đó. Nếu quy tắc phối hợp nhiều đối tượng hoặc không tự nhiên thuộc về một đối tượng riêng lẻ, có thể dùng domain service hoặc một chính sách miền. Không nhất thiết mọi quy tắc đều phải nằm trong một entity.

Một phép kiểm tra cú pháp như chuỗi mã đơn không được rỗng thường thuộc tầng trình bày hoặc kiểm tra đầu vào của ca sử dụng. Một bất biến như đơn hàng đã giao không thể chuyển sang trạng thái đã hủy là quy tắc miền. Việc phân biệt dựa trên ý nghĩa và phạm vi áp dụng của quy tắc, không chỉ dựa vào việc câu lệnh có chứa `if` hay không.

## 4. Ví dụ Java: điều phối hủy đơn hàng

Giả sử hệ thống cho phép hủy đơn hàng nếu đơn chưa được giao và yêu cầu được gửi trước thời hạn hủy. Quy tắc này phải được bảo vệ ở miền nghiệp vụ để mọi đường gọi đều tuân thủ.

### Mô hình miền giữ quyết định

```java
package com.example.orders.domain;

import java.time.Instant;

public class Order {
    private final OrderId id;
    private final Instant cancellationDeadline;
    private OrderStatus status;
    private CancelReason cancellationReason;

    public void cancel(CancelReason reason, Instant requestedAt) {
        if (!status.canBeCancelled()) {
            throw new OrderCannotBeCancelledException(status);
        }

        if (requestedAt.isAfter(cancellationDeadline)) {
            throw new CancellationWindowExpiredException(id);
        }

        status = OrderStatus.CANCELLED;
        cancellationReason = reason;
    }
}
```

`Order.cancel(...)` là nơi quyết định việc hủy có hợp lệ không và thay đổi trạng thái khi hợp lệ. Ví dụ đã lược bỏ constructor, getter và một số kiểu phụ trợ để tập trung vào ranh giới trách nhiệm. Truyền thời điểm vào phương thức giúp kiểm thử quy tắc ở những thời điểm cụ thể mà không phụ thuộc đồng hồ hệ thống.

### Application service điều phối quy trình

```java
package com.example.orders.application;

import com.example.orders.domain.Order;
import com.example.orders.domain.OrderRepository;
import java.time.Clock;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CancelOrderService {
    private final OrderRepository orders;
    private final Clock clock;

    public CancelOrderService(OrderRepository orders, Clock clock) {
        this.orders = orders;
        this.clock = clock;
    }

    @Transactional
    public void handle(CancelOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFoundException(command.orderId()));

        order.cancel(command.reason(), clock.instant());
        orders.save(order);
    }
}
```

Service trên biết phải tải đơn hàng, gọi hành vi miền và lưu kết quả. Nó không tự kiểm tra trạng thái hoặc thời hạn hủy. `Clock` được cung cấp qua constructor để có thể thay bằng clock cố định trong kiểm thử; trong ứng dụng thực tế có thể cấu hình bean dùng `Clock.systemUTC()`.

`OrderRepository` là hợp đồng mà tầng ứng dụng sử dụng. Tùy kiến trúc, hợp đồng này có thể do miền hoặc tầng ứng dụng sở hữu; adapter lưu trữ hiện thực nó ở tầng hạ tầng. Điều quan trọng của ví dụ là application service chỉ dựa vào hợp đồng cần thiết và không phụ thuộc trực tiếp vào chi tiết JPA hay SQL.

### Cách viết dễ làm lẫn trách nhiệm

Một cách triển khai kém phù hợp là đưa quyết định hủy vào application service:

```java
// Minh họa cách làm nên tránh
if (!order.status().equals(OrderStatus.PENDING)
        || clock.instant().isAfter(order.cancellationDeadline())) {
    throw new CannotCancelOrderException();
}

order.setStatus(OrderStatus.CANCELLED);
orders.save(order);
```

Đoạn mã này làm application service biết chi tiết chính sách và cách thay đổi trạng thái. Khi một tác vụ nền hoặc một API quản trị cũng cần hủy đơn, cùng quy tắc có thể bị chép lại. Sau này chính sách thay đổi, các bản sao có nguy cơ không được cập nhật đồng bộ. Việc để đối tượng miền thực hiện `cancel(...)` gom quyết định và bảo vệ trạng thái tại một nơi.

## 5. Không phải mọi nhánh điều kiện đều là quy tắc miền

Phân biệt trách nhiệm không có nghĩa tầng ứng dụng không được chứa câu lệnh điều kiện. Application service vẫn phải điều phối theo kết quả của các bước và tình trạng kỹ thuật của quy trình.

| Tình huống | Nơi xử lý phù hợp | Lý do |
|---|---|---|
| Không tìm thấy đơn hàng theo mã yêu cầu | Tầng ứng dụng | Đây là kết quả của bước tải dữ liệu trong use case; ứng dụng quyết định trả lỗi phù hợp |
| Đơn đã giao nên không được hủy | Miền nghiệp vụ | Đây là chính sách về trạng thái đơn hàng |
| Hết thời hạn được hủy | Miền nghiệp vụ | Đây là điều kiện hợp lệ của hành động hủy |
| Gọi cổng thanh toán thất bại tạm thời | Tầng ứng dụng hoặc adapter theo chính sách vận hành | Cần quyết định retry, ghi nhận lỗi hoặc tiếp tục xử lý theo quy trình kỹ thuật |
| Khách hàng có đủ điều kiện nhận ưu đãi hay không | Miền nghiệp vụ hoặc domain policy | Đây là chính sách quyền lợi, có thể được nhiều use case sử dụng |
| Request thiếu trường bắt buộc hoặc sai định dạng | Tầng trình bày / kiểm tra đầu vào | Dữ liệu chưa đạt hợp đồng giao tiếp |

Một use case có thể kiểm tra kết quả trả về từ cổng, chọn bước tiếp theo, hoặc chuyển một lỗi kỹ thuật thành kết quả ứng dụng. Đó vẫn là điều phối. Nhưng nếu nhánh `if` quyết định khách hàng có được hưởng chiết khấu, đơn hàng có được hủy hoặc giao dịch có vi phạm hạn mức hay không, đó là chính sách nghiệp vụ và cần được đặt ở miền.

## 6. Quy tắc liên quan nhiều đối tượng

Không phải lúc nào một entity cũng đủ thông tin để quyết định. Ví dụ, việc áp dụng mức chiết khấu có thể phụ thuộc vào hạng thành viên, tổng giá trị giỏ hàng và chương trình đang hoạt động. Tầng ứng dụng có thể tải các dữ liệu cần thiết qua những cổng tương ứng, sau đó gọi một `DiscountPolicy` thuộc miền để đưa ra quyết định.

```java
// Phác thảo: policy chứa quyết định nghiệp vụ nhiều dữ kiện.
public class DiscountPolicy {
    public Discount calculate(
            CustomerMembership membership,
            ShoppingCart cart,
            Promotion promotion) {
        // Kiểm tra điều kiện và tính mức giảm theo chính sách.
    }
}
```

Application service có thể điều phối việc lấy `CustomerMembership`, `ShoppingCart` và `Promotion`, rồi yêu cầu policy tính chiết khấu. Việc truy xuất dữ liệu là một phần của quy trình; việc kết luận mức giảm nào được phép là quyết định nghiệp vụ. Nếu dữ liệu đầu vào không đầy đủ, policy cần có hợp đồng rõ ràng về lỗi hoặc kết quả không đủ điều kiện.

Không nên biến domain service thành nơi gọi tùy tiện mọi repository và API ngoài. Hãy giữ cho policy nhận các khái niệm miền cần thiết và để tầng ứng dụng điều phối việc thu thập dữ liệu, trừ khi kiến trúc cụ thể có một lý do rõ ràng khác.

## 7. Từ use case đến hệ thống bên ngoài

Một quy trình thực tế có thể cần lưu trạng thái đơn hàng rồi yêu cầu hoàn tiền. Tầng ứng dụng điều phối các bước đó, nhưng cần chú ý ranh giới giao dịch: giao dịch cơ sở dữ liệu không thể tự bảo đảm một lời gọi mạng đến cổng thanh toán cũng thành công hoặc thất bại cùng lúc.

Một cách thường dùng là lưu thay đổi đơn hàng và một sự kiện như `OrderCancelled` vào outbox trong cùng giao dịch. Một tiến trình khác đọc sự kiện và gọi cổng thanh toán để hoàn tiền; nếu dịch vụ ngoài tạm thời lỗi, tiến trình có thể thử lại theo chính sách vận hành. Quy tắc đơn hàng có được phép hủy hay không vẫn do miền quyết định. Application và hạ tầng chịu trách nhiệm phối hợp việc phát sự kiện và giao tiếp đáng tin cậy với dịch vụ ngoài.

Điều này cũng cho thấy application service không nhất thiết phải thực hiện mọi bước đồng bộ trong một phương thức. Nó có thể khởi tạo quy trình, lưu trạng thái và phát sự kiện để các bước tiếp theo được xử lý bất đồng bộ. Ranh giới giữa điều phối và quyết định nghiệp vụ vẫn giữ nguyên.

## 8. Kiểm thử đúng trách nhiệm

Phân chia rõ trách nhiệm giúp kiểm thử tập trung vào điều cần xác minh:

- **Kiểm thử miền:** kiểm tra đơn đang ở trạng thái nào được phép hủy, thời điểm đúng hạn và thời điểm quá hạn, cũng như trạng thái sau khi hủy thành công. Các bài kiểm thử này không cần khởi động Spring hoặc kết nối cơ sở dữ liệu.
- **Kiểm thử tầng ứng dụng:** dùng repository giả để xác minh use case tải đúng đơn, gọi hành vi `cancel`, lưu khi hợp lệ và trả lỗi khi không tìm thấy đơn. Kiểm thử cũng có thể xác minh các cổng ngoài được gọi theo đúng thứ tự hoặc sự kiện được ghi nhận.
- **Kiểm thử tích hợp hạ tầng:** xác minh adapter repository ánh xạ và lưu dữ liệu đúng; kiểm thử outbox hoặc adapter thanh toán ở ranh giới tích hợp tương ứng.

Nếu kiểm thử application service phải tạo rất nhiều đối tượng Spring, JPA và HTTP chỉ để kiểm tra thứ tự gọi, có thể service đang phụ thuộc quá nhiều chi tiết. Nếu kiểm thử miền phải dựng database hoặc mock hàng loạt repository, có thể quy tắc nghiệp vụ đang bị đặt sai chỗ hoặc mô hình chưa có ranh giới rõ ràng.

## 9. Cách rà soát một application service

Khi review một use case, hãy lần lượt hỏi:

1. Service đang điều phối những bước nào, và mỗi bước thuộc hợp đồng nào?
2. Các điều kiện trong service là điều kiện của quy trình hay là chính sách quyết định một hành động có hợp lệ về nghiệp vụ không?
3. Quy tắc có được bảo vệ nếu cùng hành động được gọi từ một API, tác vụ nền hoặc giao diện khác không?
4. Nếu chính sách thay đổi, có phải sửa nhiều use case hay chỉ sửa một hành vi hoặc policy miền?
5. Giao dịch, sự kiện và lời gọi dịch vụ ngoài có được xử lý tại ranh giới phù hợp không?

Một dấu hiệu cần xem lại là application service có nhiều nhánh điều kiện về trạng thái, hạn mức, giá, quyền lợi hoặc thời hạn và tự sửa các trường miền. Một dấu hiệu khác là entity chỉ chứa dữ liệu, trong khi mọi quy tắc bị gom vào một service dùng chung. Tuy vậy, không nên áp dụng máy móc: một ứng dụng nhỏ hoặc một quy trình nghiệp vụ đơn giản có thể dùng mô hình thủ tục gọn nhẹ. Mục tiêu là để mỗi quyết định có một nơi sở hữu rõ ràng và tránh lặp lại chính sách.

## 10. Ghi nhớ

Tầng ứng dụng điều phối ca sử dụng: nhận yêu cầu, tải dữ liệu, gọi các hành vi cần thiết, quản lý giao dịch, phối hợp hệ thống ngoài và trả kết quả. Miền nghiệp vụ sở hữu các quyết định về tính hợp lệ, chính sách và bất biến của hoạt động kinh doanh. Application service có thể chứa nhánh điều kiện để điều khiển quy trình, nhưng không nên tự thực hiện các quyết định nghiệp vụ mà những luồng khác cũng phải tuân theo. Hãy đặt quy tắc tại nơi có đủ ngữ nghĩa để bảo vệ nó, rồi kiểm thử riêng quyết định miền và trình tự điều phối của use case.
