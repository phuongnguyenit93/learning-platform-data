# Đánh giá thiết kế bằng một thay đổi cụ thể

Một cấu trúc có thể trông gọn, nhiều interface và tuân theo các quy tắc đặt tên, nhưng điều đó chưa chứng minh nó dễ thay đổi. Cách kiểm tra thực tế hơn là đặt ra **một yêu cầu thay đổi rõ ràng**, lần theo các nơi bị tác động rồi xem thiết kế giúp hay cản trở việc thực hiện yêu cầu.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chất lượng mã liên quan đến việc mã có **đáng tin cậy, dễ hiểu và dễ thay đổi** hay không. Với chủ đề **Cấu trúc và phụ thuộc**, câu hỏi quan trọng là: **“Khi một yêu cầu cụ thể xuất hiện, chúng ta phải sửa những trách nhiệm nào, vì sao và có thể kiểm chứng thay đổi an toàn không?”**

Bài học sử dụng một tình huống xuyên suốt trong ứng dụng bán hàng: **thêm kênh SMS vào hệ thống thông báo xác nhận đơn**, vốn mới hỗ trợ email. Từ đó, chúng ta đánh giá mức độ kết dính, ghép nối, hướng phụ thuộc, khả năng định vị hành vi, phạm vi thay đổi và chi phí kiểm thử.

## 1. Bắt đầu từ yêu cầu có tiêu chí kiểm chứng

Giả sử hệ thống hiện tại xác nhận đơn hàng và gửi email cho khách. Sản phẩm đưa ra yêu cầu mới:

> Sau khi đơn được xác nhận thành công, gửi thông báo bằng **email hoặc SMS** theo lựa chọn của khách hàng. Nếu dịch vụ gửi thông báo gặp sự cố, đơn đã xác nhận không bị tự ý chuyển về trạng thái trước đó. Sự cố gửi phải được ghi nhận để có thể xử lý lại an toàn.

Yêu cầu này có ít nhất bốn phần khác nhau:

| Phần của yêu cầu | Điều cần xác định | Ai nên chịu trách nhiệm chính? |
| --- | --- | --- |
| **Xác nhận đơn** | Khi nào đơn đủ điều kiện chuyển sang CONFIRMED? | Nghiệp vụ đơn hàng. |
| **Chọn kênh** | Khách đã chọn email hay SMS? Mặc định khi chưa có lựa chọn là gì? | Chính sách và dữ liệu tùy chọn thông báo. |
| **Gửi thông báo** | Làm sao gửi nội dung qua từng nhà cung cấp? | Adapter cho email/SMS. |
| **Xử lý lỗi** | Nếu gửi thất bại, trạng thái đơn và cơ chế thử lại ra sao? | Luồng điều phối, lưu sự kiện và worker gửi. |

Để đánh giá thiết kế công bằng, trước hết phải xác định các **bất biến**:

- Đơn chỉ được xác nhận khi quy tắc xác nhận và cập nhật dữ liệu thành công.
- Thông báo được gửi tới đúng người nhận và đúng kênh đã được phép sử dụng.
- Lỗi nhà cung cấp SMS không được biến thành lỗi “đơn hàng không hợp lệ”.
- Một yêu cầu gửi lại không được tạo tác dụng phụ lặp ngoài chính sách đã chấp nhận.
- Đường xử lý phải đủ quan sát được để tìm nguyên nhân khi có sự cố.

Nếu chưa có hợp đồng rõ ràng cho các tình huống này, việc thêm interface chưa giúp bảo đảm hệ thống tốt hơn. **Chất lượng thiết kế chỉ có ý nghĩa khi đối chiếu với hành vi mong muốn.**

## 2. Thiết kế ban đầu: kết nối trực tiếp với email

Một phiên bản tối giản của ứng dụng có thể viết:

~~~java
final class OrderService {
    private final OrderRepository orders;
    private final EmailClient emailClient;

    OrderService(OrderRepository orders, EmailClient emailClient) {
        this.orders = orders;
        this.emailClient = emailClient;
    }

    void confirm(String orderId, String email) {
        orders.markConfirmed(orderId);
        emailClient.send(email, "Your order " + orderId + " is confirmed");
    }
}
~~~

Trong ví dụ này, **OrderRepository** và **EmailClient** là các kiểu được giả định đã tồn tại; mã chỉ minh họa cấu trúc phụ thuộc.

Sơ đồ phụ thuộc trực tiếp:

~~~mermaid
flowchart LR
    C["OrderController"] --> S["OrderService"]
    S --> R["OrderRepository"]
    S --> E["EmailClient"]
    E --> P["Email provider"]
~~~

Thiết kế này đủ đơn giản để hiểu khi yêu cầu chỉ có một kênh email. Nhưng khi thêm SMS, các quyết định bắt đầu chồng lên nhau trong OrderService:

- Làm sao xác định kênh mà khách chọn?
- Với SMS phải lấy số điện thoại đã xác thực ở đâu?
- Service có cần biết API và lỗi riêng của nhà cung cấp SMS không?
- Nếu email thành công nhưng cập nhật đơn thất bại, hoặc ngược lại, hệ thống xử lý ra sao?
- Ai chịu trách nhiệm retry và ngăn gửi trùng?

Nếu thêm tất cả bằng những nhánh **if** ngay trong OrderService, một ca sử dụng đơn hàng dễ trở thành nơi chứa cả **quy tắc xác nhận** và **chi tiết gửi thông báo**.

Lưu ý: đoạn code ban đầu cũng chưa đảm bảo an toàn khi một thao tác thành công và thao tác kia thất bại. Đây là **vấn đề thiết kế đã tồn tại**, và yêu cầu mới làm nó lộ rõ hơn.

## 3. Đánh giá thiết kế qua bản đồ tác động thay đổi

Trước khi sửa, hãy lập **change impact map**: những phần có lý do hợp lệ để thay đổi và những phần đáng lẽ không cần biết về kênh SMS.

| Thành phần | Có khả năng cần đổi? | Lý do |
| --- | :---: | --- |
| Dữ liệu lựa chọn kênh của khách | Có | Cần biểu diễn giá trị EMAIL/SMS và xử lý dữ liệu hiện có. |
| Giao diện/API thay đổi lựa chọn kênh | Có, nếu chưa hỗ trợ | Người dùng cần cách chọn và xác nhận thông tin liên hệ. |
| Nội dung thông báo | Có thể | SMS có giới hạn độ dài và định dạng khác email. |
| Adapter kết nối nhà cung cấp SMS | Có | Đây là năng lực mới. |
| Cấu hình kênh, phụ thuộc và giám sát | Có | Cần cấu hình nhà cung cấp, ghi nhận lỗi và vận hành. |
| Quy tắc xác nhận đơn hàng | Thông thường không | Điều kiện CONFIRMED không thay đổi chỉ vì thêm cách thông báo. |
| Cách lưu dữ liệu đơn hàng cốt lõi | Thông thường không | Không có yêu cầu mới về trạng thái hoặc cấu trúc đơn. |
| Quy tắc tính giá, thuế, tồn kho | Không theo yêu cầu này | Chúng không quyết định kênh gửi xác nhận. |

Bảng là **phân tích giả định của tình huống học tập**, không phải kết quả đo từ một repository cụ thể. Thiết kế thực tế có thể khiến các phần khác cần sửa vì ràng buộc dữ liệu hoặc tích hợp đang tồn tại.

Nếu một thay đổi thêm SMS buộc phải sửa **PriceCalculator**, **StockService** và nhiều quy tắc đơn hàng không liên quan, đó là tín hiệu cần xem lại cách phụ thuộc đã lan rộng. Ngược lại, thay đổi dữ liệu khách hàng và cấu hình gửi là phạm vi có thể hợp lý.

### Đường lan truyền thay đổi

Một cách đặt câu hỏi hữu ích:

1. **Điểm bắt đầu:** yêu cầu có tính chất mới ở đâu?
2. **Nơi sở hữu quyết định:** ai quyết định kênh, nội dung và điều kiện gửi?
3. **Nơi chịu tác động kỹ thuật:** cần cập nhật hợp đồng hoặc adapter nào?
4. **Người tiêu thụ hợp đồng:** caller nào phải đổi chữ ký hoặc dữ liệu?
5. **Điểm kết thúc:** thay đổi lan tới đâu thì dừng?

Thiết kế tốt tạo ra một **ranh giới dừng hợp lý**. Thay đổi nhà cung cấp SMS có thể cần sửa adapter SMS, nhưng không cần sửa quy tắc xác nhận đơn nếu hợp đồng gửi thông báo vẫn giữ nguyên.

## 4. Tại sao phạm vi thay đổi phản ánh chất lượng thiết kế?

Một số khía cạnh cần đánh giá:

| Thuộc tính | Khi thiết kế hỗ trợ thay đổi tốt | Dấu hiệu cần xem lại |
| --- | --- | --- |
| **Cohesion – tính kết dính** | Mỗi thành phần tập trung vào một nhóm trách nhiệm có liên quan. | OrderService vừa quyết định trạng thái đơn, vừa điều khiển SMS API và định dạng email. |
| **Coupling – mức ghép nối** | Một thành phần biết vừa đủ về hợp đồng mà nó sử dụng. | Nghiệp vụ nhập trực tiếp kiểu dữ liệu từ SDK của nhà cung cấp SMS. |
| **Hướng phụ thuộc** | Quy tắc ổn định phụ thuộc vào hợp đồng phù hợp, chi tiết kỹ thuật phụ thuộc vào hoặc triển khai hợp đồng đó. | Thay đổi thư viện gửi SMS buộc thay đổi ca sử dụng xác nhận đơn. |
| **Change amplification** | Một yêu cầu mới dẫn đến số nơi sửa có lý do rõ ràng. | Phải chỉnh nhiều wrapper chỉ để truyền thêm một tham số. |
| **Khả năng khám phá hành vi** | Dễ tìm nơi chọn kênh, nơi gửi và nơi xử lý lỗi. | Quyết định nằm rải rác qua controller, entity, helper và interceptor. |
| **Khả năng kiểm thử** | Có thể kiểm tra quy tắc độc lập với lỗi mạng và nhà cung cấp. | Mọi test nghiệp vụ đều phải gọi dịch vụ email/SMS thật. |
| **Khả năng quan sát** | Thất bại có mã lỗi, ngữ cảnh và nơi chịu trách nhiệm rõ. | Lỗi gửi bị nuốt hoặc bị báo nhầm thành lỗi xác nhận đơn. |

**Đánh giá dựa trên lý do của thay đổi**, chứ không đơn giản đếm file: một thay đổi hợp lý có thể cần cập nhật nhiều lớp đúng trách nhiệm (API, dữ liệu, adapter, kiểm thử). Ít file hơn không luôn đồng nghĩa tốt hơn nếu bạn phải trộn nhiều mối quan tâm vào một class.

## 5. Hai hướng giải quyết và đánh đổi

### Phương án A — Giữ logic trong một service

Nếu sản phẩm rất nhỏ, chỉ có email và SMS, nhà cung cấp ổn định và không có yêu cầu mở rộng khác, một cách viết tường minh có thể đủ:

~~~java
void sendConfirmation(Channel channel, String destination, String message) {
    if (channel == Channel.EMAIL) {
        emailClient.send(destination, message);
    } else if (channel == Channel.SMS) {
        smsClient.send(destination, message);
    } else {
        throw new IllegalArgumentException("Unsupported channel");
    }
}
~~~

Ưu điểm là ít thành phần và dễ lần theo với hai lựa chọn. Đổi lại, service phụ thuộc trực tiếp vào cả hai client, biết chi tiết gửi và có thể phải sửa mỗi lần thêm kênh. Cũng cần xác định cách xử lý ngoại lệ của từng nhà cung cấp.

Phương án này **không tự động sai**. Nó có thể là lựa chọn hợp lý nếu độ phức tạp nhỏ, các phụ thuộc được cách ly đủ tốt và phần xử lý không kéo theo nhiều trách nhiệm khác.

### Phương án B — Tách hợp đồng gửi và adapter theo kênh

Khi các nhà cung cấp có SDK, cách xác thực, lỗi và chu kỳ thay đổi khác nhau, một hợp đồng gửi ổn định có ích:

~~~mermaid
flowchart LR
    O["Order confirmation"] --> X["Notification outbox"]
    X --> W["Notification worker"]
    W --> D["ConfirmationRouter"]
    D --> A["EmailSender adapter"]
    D --> B["SmsSender adapter"]
    A --> E["Email provider"]
    B --> S["SMS provider"]
~~~

Trong thiết kế này, ca sử dụng xác nhận chỉ tạo ra yêu cầu thông báo; worker đảm nhiệm việc phát đi; router chọn adapter; adapter xử lý chi tiết nhà cung cấp. Các ranh giới cần có **hợp đồng và trách nhiệm rõ**. Không cần tạo thêm tầng manager, facade hoặc handler nếu chúng chỉ chuyển nguyên lời gọi.

Việc dùng **outbox** ở đây nhằm minh họa nhu cầu giữ sự kiện gửi khi hệ thống gặp lỗi sau khi xác nhận đơn. Để bảo đảm an toàn thực tế, ghi trạng thái đơn và bản ghi outbox phải nằm trong **một giao dịch lưu trữ phù hợp**, worker cần cơ chế claim/retry, và nhà cung cấp có thể không hỗ trợ giao hàng đúng một lần. Đây là các quyết định đáng kể, cần cân nhắc theo độ tin cậy yêu cầu.

### So sánh theo tình huống

| Tiêu chí | A: Nhánh trực tiếp | B: Hợp đồng + adapter |
| --- | --- | --- |
| **Số thành phần ban đầu** | Ít. | Nhiều hơn. |
| **Thêm kênh thứ ba** | Thường sửa nhánh điều phối và thêm client. | Thêm adapter và đăng ký kênh; router có thể giữ nguyên. |
| **Thay SDK của SMS** | Có thể chạm service nếu SDK nằm trong đó. | Chủ yếu nằm ở adapter SMS. |
| **Kiểm thử lựa chọn kênh** | Có thể mock cả hai client trong service. | Kiểm tra định tuyến bằng sender giả; kiểm tra adapter riêng. |
| **Tác dụng phụ và lỗi nhà cung cấp** | Dễ bị trộn với xử lý đơn nếu đặt cùng service. | Có vị trí rõ để xử lý và giám sát gửi thông báo. |
| **Rủi ro trừu tượng hóa quá mức** | Thấp hơn ban đầu. | Có nếu hợp đồng chung bị ép che các khác biệt quan trọng. |

**Không chọn phương án B chỉ vì có nhiều interface.** Chọn khi yêu cầu thực sự cần ranh giới thay đổi, kiểm thử độc lập và khả năng phục hồi; chọn A khi nó vẫn bảo đảm hành vi với chi phí hiểu phù hợp.

## 6. Ví dụ Java 17: một hợp đồng định tuyến thông báo

Sau đây là **ví dụ tự chứa** thể hiện cách tách quy tắc định tuyến khỏi SDK email/SMS. Hai adapter thật triển khai cùng interface Sender nhưng có thể xử lý endpoint, xác thực và lỗi của riêng mình.

~~~java
import java.util.Map;
import java.util.Objects;

public final class ConfirmationRouter {
    public enum Channel {
        EMAIL, SMS
    }

    public record Message(
            String orderId,
            String destination,
            String text) {
        public Message {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(destination, "destination");
            Objects.requireNonNull(text, "text");
        }
    }

    @FunctionalInterface
    public interface Sender {
        void send(Message message);
    }

    private final Map<Channel, Sender> senders;

    public ConfirmationRouter(Map<Channel, Sender> senders) {
        // Bản sao bất biến để cấu hình không bị đổi ngầm từ bên ngoài.
        this.senders = Map.copyOf(Objects.requireNonNull(senders));
    }

    public void send(Channel channel, Message message) {
        Objects.requireNonNull(channel, "channel");
        Objects.requireNonNull(message, "message");

        Sender sender = senders.get(channel);
        if (sender == null) {
            throw new IllegalStateException(
                    "Notification channel not configured: " + channel);
        }
        sender.send(message);
    }
}
~~~

Việc lắp ghép diễn ra ở **composition root** (nơi cấu hình phụ thuộc):

~~~java
ConfirmationRouter.Sender emailSender = message -> {
    // Adapter email thật sẽ gọi email provider.
    System.out.println("EMAIL: " + message.destination());
};

ConfirmationRouter.Sender smsSender = message -> {
    // Adapter SMS thật sẽ gọi SMS provider.
    System.out.println("SMS: " + message.destination());
};

ConfirmationRouter router = new ConfirmationRouter(Map.of(
        ConfirmationRouter.Channel.EMAIL, emailSender,
        ConfirmationRouter.Channel.SMS, smsSender));

router.send(
        ConfirmationRouter.Channel.SMS,
        new ConfirmationRouter.Message(
                "order-42", "+84900000000", "Order 42 confirmed"));
~~~

Trong đoạn lắp ghép, **System.out.println** chỉ là minh họa thay cho tích hợp bên ngoài. Không dùng nó như cơ chế gửi thật. Router không cần biết email sử dụng SMTP, HTTP hay SDK nào; nó chỉ biết **hợp đồng Sender**.

Đánh giá một thay đổi tiếp theo: nếu thêm **PUSH**, chúng ta cần bổ sung cách biểu diễn kênh, adapter PUSH và đăng ký trong cấu hình. Bản thân thuật toán tra cứu Sender trong router không cần viết thêm nhánh if. Tuy nhiên, API sở thích người dùng và mô hình lưu dữ liệu có thể phải cập nhật tùy hợp đồng: **thay đổi được cô lập, không biến mất**.

### Điều không nên giấu trong interface chung

Email và SMS có yêu cầu khác nhau:

- Email có địa chỉ email, subject, HTML và khả năng đính kèm.
- SMS có số điện thoại, giới hạn độ dài và nhiều ràng buộc riêng từ nhà cung cấp.
- Thời điểm gửi, sự đồng ý nhận thông báo và chính sách retry có thể khác nhau.

Một Message chung đơn giản có thể đủ để dạy ý tưởng định tuyến, nhưng hệ thống thật nên làm rõ **địa chỉ nhận**, **nội dung theo kênh**, **validation** và **chính sách nhà cung cấp**. Nếu interface khiến mọi adapter phải nhận vô số trường không liên quan, thiết kế trừu tượng đang che một khác biệt có ý nghĩa.

## 7. Kiểm chứng bằng test: lỗi ở đâu và thay đổi có lan rộng không?

Tách adapter có giá trị nếu chúng ta có thể kiểm tra định tuyến độc lập với mạng. Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class ConfirmationRouterTest {
    @Test
    void smsSelectionInvokesOnlySmsSender() {
        AtomicInteger emailCalls = new AtomicInteger();
        AtomicInteger smsCalls = new AtomicInteger();

        ConfirmationRouter router = new ConfirmationRouter(Map.of(
                ConfirmationRouter.Channel.EMAIL,
                message -> emailCalls.incrementAndGet(),
                ConfirmationRouter.Channel.SMS,
                message -> smsCalls.incrementAndGet()));

        router.send(
                ConfirmationRouter.Channel.SMS,
                new ConfirmationRouter.Message(
                        "order-42", "+84900000000", "Confirmed"));

        assertEquals(0, emailCalls.get());
        assertEquals(1, smsCalls.get());
    }

    @Test
    void missingConfigurationFailsClearly() {
        ConfirmationRouter router = new ConfirmationRouter(Map.of());

        var failure = assertThrows(IllegalStateException.class,
                () -> router.send(
                        ConfirmationRouter.Channel.SMS,
                        new ConfirmationRouter.Message(
                                "order-42", "+84900000000", "Confirmed")));

        assertTrue(failure.getMessage().contains("SMS"));
    }
}
~~~

Hai test trên chỉ xác minh **hợp đồng định tuyến**: đúng sender được gọi và thiếu cấu hình được báo rõ. Chúng **không chứng minh** tin nhắn đã đến điện thoại, không kiểm tra độ hợp lệ của số điện thoại và không bảo đảm retry an toàn. Những điều đó cần kiểm thử adapter, tích hợp với dịch vụ ngoài và luồng outbox/worker tùy yêu cầu.

Đối với thay đổi từ email sang hỗ trợ SMS, có thể lập ma trận kiểm tra:

| Trường hợp | Bằng chứng cần có |
| --- | --- |
| Khách chọn email | Đi đúng email adapter; nội dung/email đích hợp lệ. |
| Khách chọn SMS | Đi đúng SMS adapter; nội dung/số nhận hợp lệ. |
| Chưa có kênh trong dữ liệu cũ | Áp dụng mặc định đã được xác nhận trong yêu cầu; không suy đoán. |
| Kênh không hỗ trợ hoặc cấu hình thiếu | Báo lỗi có ý nghĩa, không gửi nhầm sang kênh khác. |
| Nhà cung cấp SMS timeout | Kết quả gửi được ghi nhận là chưa chắc chắn; retry theo chính sách an toàn. |
| Worker xử lý cùng sự kiện lần nữa | Không tạo tác dụng phụ lặp ngoài mức được chấp nhận; kiểm tra idempotency hoặc đối soát. |
| Lỗi gửi sau khi đơn đã được xác nhận | Không làm mất trạng thái đơn; có tín hiệu để xử lý gửi thất bại. |
| Khách không đồng ý nhận kênh đã chọn | Chặn gửi và phản hồi theo chính sách đã xác định. |

### Không nhầm “test nhiều” với “thiết kế dễ thay đổi”

Nếu một ca test đơn hàng phải biết đối tượng request của nhà cung cấp SMS, đó có thể là dấu hiệu phụ thuộc hạ tầng đã lan vào nghiệp vụ. Nếu test router có thể dùng các sender giả rất nhỏ, ranh giới đã giúp **kiểm tra riêng hành vi định tuyến**.

Nhưng đừng tạo interface chỉ để mock: đôi khi một lớp với dependency injection thông thường đã đủ kiểm thử. Giá trị kiến trúc cần được giải thích bằng **trách nhiệm và thay đổi thực tế**.

## 8. Vấn đề transaction và độ tin cậy khi thêm SMS

Một thay đổi về kênh gửi có thể bộc lộ vấn đề cũ:

~~~java
// Minh họa nguy cơ mất thông báo.
orders.markConfirmed(orderId);
smsSender.send(message);
~~~

Nếu dòng đầu thành công nhưng tiến trình dừng trước dòng sau, đơn đã xác nhận mà không có thông báo. Nếu dòng gửi xảy ra trước cập nhật đơn, khách có thể nhận thông báo cho đơn chưa được xác nhận.

Một giải pháp phù hợp với yêu cầu gửi đáng tin cậy là **transactional outbox**:

~~~text
Trong cùng một transaction của kho dữ liệu:
  1. Cập nhật trạng thái đơn thành CONFIRMED
  2. Lưu bản ghi thông báo cần gửi vào outbox
  3. Commit

Ngoài transaction:
  4. Worker đọc bản ghi chưa gửi, chọn adapter
  5. Thực hiện gửi và ghi kết quả
  6. Retry có giới hạn, theo dõi thất bại
~~~

Cách này giúp tránh khoảng trống giữa việc commit đơn và lưu **ý định gửi**, khi cùng một cơ sở dữ liệu hỗ trợ transaction thích hợp. Nó **không tự bảo đảm gửi đúng một lần**: worker có thể gửi thành công rồi gặp lỗi trước khi đánh dấu hoàn tất. Cần cơ chế idempotency của nhà cung cấp (nếu có), chống xử lý lặp hoặc đối soát phù hợp với kỳ vọng nghiệp vụ.

Điều rút ra về thiết kế: yêu cầu mới có thể làm rõ những ranh giới **thật sự cần có**. Thêm outbox là thay đổi lớn hơn việc thêm một interface, nhưng có cơ sở khi hành vi thất bại phải đáng tin cậy.

## 9. Đánh giá mức độ ghép nối bằng hướng phụ thuộc

Một thay đổi ở SDK gửi SMS có nên buộc sửa nghiệp vụ xác nhận đơn không?

Nếu **OrderService** nhập trực tiếp các class từ SMS SDK, đường phụ thuộc là:

~~~mermaid
flowchart LR
    A["Order business logic"] --> B["SMS SDK"]
    B --> C["SMS provider"]
~~~

Khi chuyển sang một nhà cung cấp khác, thay đổi kỹ thuật có thể lan vào logic nghiệp vụ.

Với ranh giới thích hợp:

~~~mermaid
flowchart LR
    A["Notification workflow"] --> I["Sender contract"]
    B["SMS adapter"] -. "implements" .-> I
    B --> C["SMS SDK"]
    C --> D["SMS provider"]
~~~

Nghiệp vụ và luồng điều phối phụ thuộc vào **hợp đồng ổn định**, adapter chịu trách nhiệm với chi tiết dễ thay đổi. Điều này liên quan đến nguyên tắc **đảo chiều phụ thuộc (Dependency Inversion)**: logic ở mức cao không bị ràng buộc bởi implementation kỹ thuật cụ thể, và thành phần chi tiết có thể triển khai hợp đồng đã định nghĩa.

Không cần áp dụng cơ học cho mọi class. Hợp đồng chỉ có ý nghĩa nếu nó mô tả khả năng mà các bên sử dụng thực sự cần. Interface có hàng chục phương thức đặc thù SMS rồi bắt email adapter triển khai các phương thức không dùng là tín hiệu ranh giới trừu tượng hóa chưa đúng.

## 10. Dùng một thay đổi để đánh giá: quy trình thực hành

Để đánh giá một thiết kế đang có, hãy chọn **một thay đổi đại diện** và đi theo quy trình:

1. **Viết yêu cầu dưới dạng hành vi quan sát được.** Ai thực hiện? Đầu vào, kết quả, giới hạn và trường hợp thất bại là gì?
2. **Liệt kê bất biến.** Điều gì tuyệt đối không được sai trước, trong và sau thay đổi?
3. **Vẽ đường đi hiện tại.** Từ điểm vào tới quy tắc, nơi lưu dữ liệu, phụ thuộc ngoài và phản hồi.
4. **Dự đoán phạm vi ảnh hưởng.** Ghi các thành phần đáng lẽ phải sửa và lý do. Sau đó so với thay đổi thực tế.
5. **Đánh giá ranh giới.** Mỗi lớp có trách nhiệm rõ không? Các phụ thuộc có đi qua hợp đồng phù hợp không?
6. **Thực hiện thay đổi đủ nhỏ để kiểm tra.** Ưu tiên chỉnh nơi sở hữu hành vi; tránh nhân bản cùng quy tắc.
7. **Kiểm chứng.** Kiểm thử thành công, thất bại, tác dụng phụ, khả năng tương thích dữ liệu và tình huống triển khai.
8. **Đọc lại bản thay đổi.** Người review có thể chỉ ra nơi nào đổi và vì sao, hay phải lần qua nhiều file không liên quan?

Đánh giá tốt phải dẫn đến câu trả lời có căn cứ: **thay đổi nào lan rộng không cần thiết, ranh giới nào bảo vệ được phần ổn định và sửa ở đâu sẽ giảm rủi ro lần sau**.

### Bảng ghi nhận khi review

| Câu hỏi đánh giá | Bằng chứng nên đưa ra |
| --- | --- |
| “Chỉnh kênh SMS có đụng logic xác nhận đơn không?” | Diff, call graph, loại dependency được import. |
| “Muốn đổi nhà cung cấp SMS cần sửa đâu?” | Vị trí SDK, adapter, cấu hình và contract test. |
| “Thêm PUSH có làm sửa mọi service không?” | Nơi định tuyến và điểm đăng ký adapter. |
| “Lỗi gửi có ảnh hưởng trạng thái đơn?” | Transaction boundary, outbox và test lỗi. |
| “Có làm hỏng dữ liệu cũ không?” | Quy tắc default, migration và test tương thích. |
| “Có quá nhiều lớp gián tiếp không?” | Những lớp chỉ chuyển tiếp, lý do tồn tại và hành vi ẩn. |

## 11. Đọc các chỉ số đúng cách

Có thể quan sát một số dấu hiệu, nhưng không nên coi chúng là điểm chất lượng tuyệt đối:

- **Số file phải sửa:** Hữu ích để thấy phạm vi, nhưng nhiều file đúng trách nhiệm có thể tốt hơn một file khổng lồ.
- **Số module phụ thuộc một class:** Gợi ý mức ảnh hưởng khi class thay đổi; cần xem chúng phụ thuộc vào hợp đồng ổn định hay chi tiết cụ thể.
- **Số lần trùng quy tắc:** Một chính sách bị sao chép ở nhiều nơi dễ sửa thiếu; nhưng các biểu thức giống nhau về cú pháp chưa chắc cùng ý nghĩa nghiệp vụ.
- **Số lớp chuyển tiếp:** Quá nhiều lớp không thêm trách nhiệm làm tăng chi phí điều hướng; một số lớp có thể tồn tại vì transaction hoặc tương thích API.
- **Độ bao phủ kiểm thử:** Giúp tìm đường chưa chạy, nhưng không chứng minh kết quả đúng nếu thiếu assertion và ca thất bại.
- **Thời gian review/sửa lỗi:** Có thể phản ánh khả năng hiểu, nhưng cũng chịu ảnh hưởng bởi kinh nghiệm nhóm và mức độ quen thuộc với hệ thống.

Thay vì dùng một con số duy nhất, hãy ghép **bằng chứng từ diff, đường phụ thuộc, test và hành vi thực tế**.

## 12. Ba sai lầm khi đánh giá thiết kế bằng một thay đổi

### Sai lầm 1 — Đếm class mà không xét trách nhiệm

“Sau refactor còn ba class thay vì sáu, nên chắc chắn tốt hơn” là kết luận thiếu căn cứ. Nếu gộp cả kiểm tra quyền, gửi SMS và SQL vào OrderController, số class ít đi nhưng trách nhiệm bị trộn.

**Cách tốt hơn:** giải thích vì sao mỗi ranh giới được giữ hoặc bỏ, và kiểm tra khả năng đổi riêng các phần.

### Sai lầm 2 — Đòi mọi thay đổi chỉ sửa một tệp

Thêm SMS **hợp lý phải** chạm tới cấu hình, adapter, kiểm thử và có thể cả dữ liệu sở thích của khách. Cố giấu toàn bộ vào một file có thể làm code khó hiểu hoặc vi phạm hợp đồng các lớp.

**Cách tốt hơn:** phân biệt **thay đổi cần thiết theo trách nhiệm** với **thay đổi lan truyền chỉ vì phụ thuộc sai**.

### Sai lầm 3 — Xem thử chạy thành công là đủ

Gửi một SMS thành công chưa chứng minh hệ thống xử lý được timeout, duplicate, thiếu cấu hình, người dùng chưa đồng ý, hay mất tiến trình sau khi xác nhận đơn.

**Cách tốt hơn:** dùng ma trận hành vi và bất biến làm tiêu chí; đánh giá cả đường thất bại và khả năng vận hành.

## 13. Bài tập thực hành

### Bài tập A — Thêm kênh PUSH

Hệ thống đã hỗ trợ email và SMS qua ConfirmationRouter. Sản phẩm yêu cầu thêm PUSH cho khách dùng ứng dụng di động.

**Câu hỏi:** Những phần nào nên thay đổi và phần nào nên giữ nguyên?

**Gợi ý:** Thêm cách biểu diễn kênh, adapter PUSH, cấu hình, dữ liệu thiết bị/đồng ý nhận thông báo, nội dung phù hợp và kiểm thử. Quy tắc xác nhận đơn, tính giá và tồn kho không nên đổi nếu nghiệp vụ của chúng không thay đổi.

### Bài tập B — Một class làm quá nhiều việc

Lớp **OrderService** đang chứa các phương thức: confirmOrder, calculateTax, sendEmail, sendSms, buildSmsPayload, saveOrderToDatabase và refundPayment.

**Câu hỏi:** Dựa vào yêu cầu “thêm PUSH”, bạn tìm dấu hiệu kết dính thấp ở đâu?

**Gợi ý:** Class chứa cả quy tắc đơn, thuế, lưu trữ, thanh toán và chi tiết nhà cung cấp. Những trách nhiệm thay đổi vì lý do khác nhau đang nằm chung. Cần phân ranh giới theo hành vi thật, không đơn giản chuyển mỗi method sang một class mới.

### Bài tập C — Một interface cho mọi thao tác

Một interface NotificationProvider có hàng chục method chuyên email (sendHtmlEmail, attachFile, setReplyTo) và một method sendSms. Mọi implementation bị bắt triển khai tất cả method.

**Câu hỏi:** Điều gì xảy ra khi thêm PUSH?

**Gợi ý:** Interface chung trở nên quá rộng, adapter phải biết các năng lực không liên quan. Nên định nghĩa hợp đồng theo khả năng thực sự dùng chung hoặc tách các hợp đồng đặc thù có ý nghĩa.

### Bài tập D — Nhà cung cấp SMS không phản hồi

Đơn đã ghi CONFIRMED. Worker gửi SMS nhưng bị timeout; người dùng ấn xác nhận lại.

**Câu hỏi:** Thiết kế tốt cần cho thấy điều gì trước khi gọi lại?

**Gợi ý:** Phải phân biệt tình trạng xác nhận đơn với kết quả gửi; có bản ghi yêu cầu gửi, khóa định danh, trạng thái xử lý và chính sách chống lặp. Timeout không chứng minh phía nhận chưa gửi tin.

---

**Ghi nhớ:** Đánh giá cấu trúc và phụ thuộc có sức thuyết phục nhất khi dựa trên **một thay đổi cụ thể**. Hãy xem thay đổi đi qua những thành phần nào, có chạm các trách nhiệm không liên quan hay không, ranh giới nào giữ ổn định hợp đồng và cách kiểm thử chứng minh hành vi vẫn đúng. Thiết kế tốt không hứa rằng mọi thay đổi đều nhỏ; nó giúp **đưa thay đổi đến đúng nơi, giới hạn tác động ngoài ý muốn và làm kết quả dễ kiểm chứng**.
