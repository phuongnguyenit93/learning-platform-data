# ArgumentCaptor để kiểm tra dữ liệu đã gửi

Trong kiểm thử với Mockito, đôi khi điều quan trọng không chỉ là một dependency đã được gọi hay chưa, mà còn là dữ liệu mà đối tượng đang kiểm thử gửi cho dependency đó. Ví dụ, một service có thể nhận yêu cầu tạo đơn hàng, chuẩn hóa tên khách hàng, tính tổng tiền rồi gửi một event sang thành phần khác. Ta cần xác nhận event chứa đúng mã đơn hàng, khách hàng và số tiền đã tính.

`ArgumentCaptor` của Mockito giúp thu thập đối số được truyền vào một mock trong lúc xác minh tương tác. Sau khi capture, bài kiểm thử có thể đọc giá trị đó và kiểm tra từng thuộc tính. Kỹ thuật này đặc biệt hữu ích khi đối số là một DTO, command, event hoặc object có nhiều trường mà việc so sánh toàn bộ object không diễn đạt rõ điều cần kiểm tra.

## 1. ArgumentCaptor giải quyết vấn đề gì?

Giả sử service gọi một cổng gửi thông báo:

```java
notificationGateway.send("customer-42", confirmation);
```

Một assertion đơn giản có thể xác nhận gateway đã được gọi:

```java
verify(notificationGateway).send(anyString(), any(Confirmation.class));
```

Nhưng assertion này chưa cho biết service đã gửi đúng người nhận hay nội dung xác nhận chưa. Ta có thể viết matcher để so sánh toàn bộ đối số, nhưng khi object có nhiều thuộc tính, matcher dễ trở nên dài và khó đọc.

Với `ArgumentCaptor`, bài kiểm thử yêu cầu Mockito ghi lại đối số trong lần xác minh, sau đó kiểm tra giá trị:

```java
ArgumentCaptor<Confirmation> captor =
        ArgumentCaptor.forClass(Confirmation.class);

verify(notificationGateway).send(eq("customer-42"), captor.capture());

Confirmation sent = captor.getValue();
assertEquals("ORD-100", sent.orderNumber());
assertEquals(new BigDecimal("125.00"), sent.total());
```

Ở đây `verify(...)` xác nhận tương tác và `capture()` đánh dấu vị trí đối số cần thu thập. `getValue()` trả về đối tượng đã được capture để bài kiểm thử kiểm tra nội dung.

## 2. Cách hoạt động của ArgumentCaptor

`ArgumentCaptor` là một đối tượng giữ các giá trị đối số mà Mockito thu được trong quá trình verify. Nó không tự gọi method, không tạo dữ liệu đầu vào và cũng không thay thế mock hoặc stub.

Luồng cơ bản gồm ba bước:

1. Tạo captor với kiểu đối số cần thu thập.
2. Thực thi hành vi của đối tượng đang kiểm thử để mock nhận được lời gọi.
3. Dùng `verify(mock).method(captor.capture())`, rồi đọc giá trị bằng `getValue()` hoặc `getAllValues()`.

Ví dụ tối giản:

```java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class MessageServiceTest {

    @Test
    void capturesMessagePassedToGateway() {
        MessageGateway gateway = mock(MessageGateway.class);
        MessageService service = new MessageService(gateway);

        service.notifyCustomer("Lan");

        ArgumentCaptor<String> captor =
                ArgumentCaptor.forClass(String.class);

        verify(gateway).send(captor.capture());

        assertEquals("Hello, Lan", captor.getValue());
    }
}

interface MessageGateway {
    void send(String message);
}

class MessageService {
    private final MessageGateway gateway;

    MessageService(MessageGateway gateway) {
        this.gateway = gateway;
    }

    void notifyCustomer(String name) {
        gateway.send("Hello, " + name);
    }
}
```

Captor được tạo sau lời gọi service trong ví dụ để làm rõ rằng nó không tham gia xử lý nghiệp vụ. Trong thực tế, tạo captor trước hoặc sau lời gọi đều được; điều quan trọng là `capture()` phải được dùng trong một thao tác verify tương ứng.

## 3. Kiểm tra DTO hoặc event đã gửi

ArgumentCaptor thường có giá trị nhất khi đối số là một object chứa nhiều trường. Ta có thể kiểm tra chính xác dữ liệu mà service gửi qua ranh giới giữa hai thành phần.

Giả sử một service tạo đơn hàng và phát event:

```java
import java.math.BigDecimal;

record OrderCreatedEvent(
        String orderId,
        String customerId,
        BigDecimal total
) {
}

interface OrderEventPublisher {
    void publish(OrderCreatedEvent event);
}

class OrderApplicationService {
    private final OrderEventPublisher publisher;

    OrderApplicationService(OrderEventPublisher publisher) {
        this.publisher = publisher;
    }

    void completeOrder(String orderId, String customerId, BigDecimal total) {
        OrderCreatedEvent event = new OrderCreatedEvent(
                orderId,
                customerId,
                total
        );
        publisher.publish(event);
    }
}
```

Bài kiểm thử có thể capture event và xác nhận từng trường:

```java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class OrderApplicationServiceTest {

    @Test
    void publishesEventWithOrderData() {
        OrderEventPublisher publisher = mock(OrderEventPublisher.class);
        OrderApplicationService service =
                new OrderApplicationService(publisher);

        service.completeOrder(
                "ORD-100",
                "CUS-42",
                new BigDecimal("125.00")
        );

        ArgumentCaptor<OrderCreatedEvent> eventCaptor =
                ArgumentCaptor.forClass(OrderCreatedEvent.class);

        verify(publisher).publish(eventCaptor.capture());

        OrderCreatedEvent event = eventCaptor.getValue();
        assertEquals("ORD-100", event.orderId());
        assertEquals("CUS-42", event.customerId());
        assertEquals(new BigDecimal("125.00"), event.total());
    }
}
```

Kiểm thử này xác nhận dữ liệu đi qua ranh giới publisher. Nó có thể phát hiện lỗi ánh xạ nhầm `customerId`, truyền sai mã đơn hàng hoặc tính sai tổng tiền trước khi phát event.

Nếu object có `equals()` được định nghĩa theo đúng hợp đồng giá trị và toàn bộ nội dung cần so sánh, có thể dùng `verify(publisher).publish(expectedEvent)` trực tiếp. Captor phù hợp hơn khi muốn kiểm tra một số thuộc tính cụ thể, muốn dùng assertion có thông điệp rõ ràng hoặc cần phân tích nhiều đối số được gửi qua các lần gọi.

## 4. Capture nhiều đối số trong cùng một lời gọi

Một method có thể nhận nhiều tham số. Có thể tạo một captor cho mỗi vị trí cần kiểm tra:

```java
interface EmailGateway {
    void send(String recipient, String subject, String body);
}

@Test
void capturesRecipientSubjectAndBody() {
    EmailGateway gateway = mock(EmailGateway.class);
    EmailService service = new EmailService(gateway);

    service.sendWelcome("lan@example.com", "Lan");

    ArgumentCaptor<String> recipientCaptor =
            ArgumentCaptor.forClass(String.class);
    ArgumentCaptor<String> subjectCaptor =
            ArgumentCaptor.forClass(String.class);
    ArgumentCaptor<String> bodyCaptor =
            ArgumentCaptor.forClass(String.class);

    verify(gateway).send(
            recipientCaptor.capture(),
            subjectCaptor.capture(),
            bodyCaptor.capture()
    );

    assertEquals("lan@example.com", recipientCaptor.getValue());
    assertEquals("Welcome", subjectCaptor.getValue());
    assertEquals("Hello, Lan", bodyCaptor.getValue());
}
```

Ví dụ giả định `EmailService` xây dựng tiêu đề và nội dung rồi gọi gateway. Các captor được đặt đúng vị trí tham số trong lời gọi `verify`, do đó mỗi captor thu thập giá trị tương ứng. Nếu một tham số không cần kiểm tra, có thể dùng matcher phù hợp cho vị trí đó, chẳng hạn `anyString()` hoặc `eq(...)`.

Khi kết hợp matcher và captor trong cùng một lời gọi verify, Mockito yêu cầu các đối số được biểu diễn bằng matcher nhất quán. `capture()` bản thân nó hoạt động như một matcher. Vì vậy, nếu dùng một giá trị cố định cho tham số khác, hãy dùng `eq("value")` thay vì truyền literal trực tiếp:

```java
verify(gateway).send(
        eq("lan@example.com"),
        subjectCaptor.capture(),
        bodyCaptor.capture()
);
```

Quy tắc này tránh lỗi `InvalidUseOfMatchersException` khi trộn matcher với giá trị thường trong cùng một lời gọi.

## 5. Capture nhiều lần gọi với getAllValues()

Nếu mock được gọi nhiều lần và bài kiểm thử cần xác nhận tất cả dữ liệu đã gửi, dùng `getAllValues()`.

Ví dụ, service gửi một thông báo cho từng người nhận:

```java
interface NotificationGateway {
    void send(String recipient, String message);
}

class CampaignService {
    private final NotificationGateway gateway;

    CampaignService(NotificationGateway gateway) {
        this.gateway = gateway;
    }

    void sendCampaign(List<String> recipients) {
        for (String recipient : recipients) {
            gateway.send(recipient, "New announcement");
        }
    }
}
```

Bài kiểm thử capture hai lần gọi:

```java
@Test
void sendsMessageToEveryRecipientInOrder() {
    NotificationGateway gateway = mock(NotificationGateway.class);
    CampaignService service = new CampaignService(gateway);

    service.sendCampaign(List.of("lan@example.com", "minh@example.com"));

    ArgumentCaptor<String> recipientCaptor =
            ArgumentCaptor.forClass(String.class);
    ArgumentCaptor<String> messageCaptor =
            ArgumentCaptor.forClass(String.class);

    verify(gateway, times(2)).send(
            recipientCaptor.capture(),
            messageCaptor.capture()
    );

    assertEquals(
            List.of("lan@example.com", "minh@example.com"),
            recipientCaptor.getAllValues()
    );
    assertEquals(
            List.of("New announcement", "New announcement"),
            messageCaptor.getAllValues()
    );
}
```

`getAllValues()` trả về danh sách các đối số đã capture theo thứ tự các lần gọi được xác minh. `times(2)` làm rõ rằng bài kiểm thử mong đợi đúng hai lần gửi. Nếu chỉ dùng `verify(gateway)` mặc định, Mockito xác minh một lần gọi; các lần gọi bổ sung có thể khiến xác minh thất bại.

Hai phương thức thường dùng:

| Phương thức | Kết quả |
|---|---|
| `getValue()` | Giá trị capture cuối cùng; hữu ích khi chỉ có một lần gọi hoặc khi chỉ quan tâm lần gọi cuối |
| `getAllValues()` | Danh sách mọi giá trị đã capture trong các lần gọi được xác minh |

Khi capture nhiều lần, `getValue()` không đại diện cho toàn bộ lịch sử. Nếu thứ tự gửi là một phần của hợp đồng, kiểm tra danh sách từ `getAllValues()` hoặc dùng `InOrder` để xác minh thứ tự tương tác một cách tường minh.

## 6. Dùng @Captor trong JUnit Jupiter

Thay vì gọi `ArgumentCaptor.forClass(...)` trong từng test, có thể khai báo field bằng annotation `@Captor`. Mockito sẽ khởi tạo captor khi test chạy thông qua `MockitoExtension` hoặc cơ chế khởi tạo annotation tương ứng.

Ví dụ với JUnit Jupiter:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Captor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class OrderEventTest {

    @Mock
    private OrderEventPublisher publisher;

    @Captor
    private ArgumentCaptor<OrderCreatedEvent> eventCaptor;

    @Test
    void capturesPublishedEvent() {
        publisher.publish(new OrderCreatedEvent(
                "ORD-200",
                "CUS-77",
                new BigDecimal("80.00")
        ));

        verify(publisher).publish(eventCaptor.capture());

        assertEquals("ORD-200", eventCaptor.getValue().orderId());
        assertEquals("CUS-77", eventCaptor.getValue().customerId());
    }
}
```

`@Captor` chỉ là metadata để Mockito khởi tạo captor; bản thân annotation không tự khởi tạo field nếu test không bật cơ chế xử lý annotation. Với JUnit Jupiter, `@ExtendWith(MockitoExtension.class)` là cách thông dụng. Nếu không dùng extension, có thể tự tạo captor trong method hoặc khởi tạo các annotation bằng `MockitoAnnotations.openMocks(this)` và đóng handle phù hợp sau test.

Một cách khác là dùng `@Captor` cùng `@Mock` trong test class có `MockitoExtension`. Cách này làm các dependency test được khai báo tập trung, giảm phần khởi tạo thủ công và dễ đọc khi có nhiều mock/captor.

## 7. Capture đối số khi kiểm thử controller hoặc service Spring

ArgumentCaptor cũng hữu ích trong kiểm thử lớp web. Ví dụ controller nhận request HTTP, chuyển dữ liệu thành command rồi gọi service. `@WebMvcTest` có thể mock service và captor giúp kiểm tra command mà controller đã gửi.

Giả sử command và service:

```java
record RegisterCustomerCommand(String email, String displayName) {
}

interface CustomerApplicationService {
    void register(RegisterCustomerCommand command);
}
```

Controller:

```java
@RestController
@RequestMapping("/customers")
class CustomerController {

    private final CustomerApplicationService service;

    CustomerController(CustomerApplicationService service) {
        this.service = service;
    }

    @PostMapping
    ResponseEntity<Void> register(@RequestBody RegisterCustomerRequest request) {
        service.register(new RegisterCustomerCommand(
                request.email().trim().toLowerCase(),
                request.displayName().trim()
        ));
        return ResponseEntity.accepted().build();
    }
}
```

Bài kiểm thử web có thể gửi JSON, xác nhận response và capture command:

```java
@WebMvcTest(CustomerController.class)
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private CustomerApplicationService service;

    @Test
    void sendsNormalizedCommandToService() throws Exception {
        mockMvc.perform(post("/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "email": "  LAN@EXAMPLE.COM ",
                                  "displayName": " Lan Nguyen "
                                }
                                """))
                .andExpect(status().isAccepted());

        ArgumentCaptor<RegisterCustomerCommand> captor =
                ArgumentCaptor.forClass(RegisterCustomerCommand.class);

        verify(service).register(captor.capture());

        assertEquals("lan@example.com", captor.getValue().email());
        assertEquals("Lan Nguyen", captor.getValue().displayName());
    }
}
```

Đoạn ví dụ giả định dự án có `RegisterCustomerRequest`, `@WebMvcTest`, `MockMvc` và cấu hình Spring Test phù hợp. `@MockBean` là cách khai báo mock bean trong nhiều phiên bản Spring Boot; ở các phiên bản mới, dự án có thể sử dụng annotation thay thế được Spring Boot cung cấp. Điểm cốt lõi là captor cho biết controller đã ánh xạ request thành command như thế nào trước khi gọi service.

Không cần dùng ArgumentCaptor để kiểm tra mọi request. Nếu chỉ cần xác nhận service nhận đúng một giá trị đơn giản, `verify(service).register(eq(expectedCommand))` có thể ngắn gọn hơn. Hãy dùng captor khi việc đọc và kiểm tra từng trường giúp ý định của test rõ hơn.

## 8. ArgumentCaptor và các matcher khác

Mockito cung cấp nhiều cách xác minh đối số. Chọn công cụ dựa trên điều cần thể hiện trong test.

| Cách làm | Phù hợp khi | Ví dụ |
|---|---|---|
| Giá trị trực tiếp | Đối số có thể so sánh rõ ràng bằng `equals()` | `verify(repo).findById("42")` |
| `eq(...)` | Cần so sánh một giá trị cụ thể cùng các matcher khác | `verify(gateway).send(eq("ops"), any())` |
| `any(...)` | Chỉ cần xác nhận method được gọi với một đối số thuộc kiểu nhất định | `verify(repo).save(any(Order.class))` |
| `argThat(...)` | Cần biểu diễn điều kiện khớp ngay tại lời gọi verify | `verify(repo).save(argThat(o -> o.total().signum() > 0))` |
| `ArgumentCaptor` | Cần lấy đối số ra để kiểm tra nhiều thuộc tính hoặc dùng trong nhiều assertion | `verify(publisher).publish(captor.capture())` |

Ví dụ, nếu chỉ cần xác nhận repository lưu một đơn hàng có mã cụ thể, so sánh trực tiếp có thể phù hợp. Nếu cần kiểm tra tổng tiền, danh sách dòng hàng và địa chỉ giao hàng riêng rẽ, captor giúp các assertion diễn đạt cụ thể hơn.

`argThat` và captor đều có thể kiểm tra điều kiện trên object. Khác biệt chính nằm ở cách trình bày: matcher quyết định ngay đối số có khớp hay không; captor giữ đối số để bài kiểm thử kiểm tra sau đó. Tránh dùng captor chỉ vì nó có sẵn nếu một matcher đơn giản đã diễn đạt đầy đủ yêu cầu.

## 9. Không dùng captor làm cơ chế stubbing mặc định

ArgumentCaptor được thiết kế chủ yếu cho verification. Có thể thấy một số ví dụ dùng `capture()` trong `when(...)`, nhưng cách này thường làm ý định của test khó hiểu và có thể khiến lỗi xuất hiện ở bước stubbing thay vì ở assertion.

Không nên viết kiểu sau chỉ để kiểm tra đối số khi mock được gọi:

```java
ArgumentCaptor<String> captor = ArgumentCaptor.forClass(String.class);
when(gateway.lookup(captor.capture())).thenReturn(result);
```

Nếu cần trả về kết quả dựa trên đối số đầu vào, hãy dùng `thenAnswer(...)` hoặc matcher `argThat(...)` trong stubbing. Ví dụ:

```java
when(gateway.lookup(argThat(key -> key.startsWith("CUS-"))))
        .thenReturn(customer);
```

Sau khi thực thi hành vi, dùng captor trong `verify(...)` nếu cần kiểm tra chính xác giá trị đã gửi. Như vậy, phần stubbing mô tả phản hồi của dependency, còn phần verification mô tả tương tác cần xác nhận.

## 10. Đối tượng mutable và thời điểm capture

Captor lưu tham chiếu tới đối tượng được truyền vào mock. Nó không tự tạo bản sao sâu của object tại thời điểm gọi. Nếu service gửi một object mutable rồi tiếp tục thay đổi chính object đó sau lời gọi, giá trị đọc qua captor có thể phản ánh trạng thái đã bị thay đổi.

Ví dụ:

```java
List<String> recipients = new ArrayList<>();
recipients.add("lan@example.com");

gateway.send(recipients);
recipients.add("minh@example.com");
```

Nếu gateway nhận cùng tham chiếu `recipients`, captor có thể nhìn thấy danh sách sau khi đã thêm phần tử thứ hai. Điều đó không chứng minh gateway đã nhận snapshot ban đầu hay service đã gửi danh sách có hai phần tử ngay từ đầu.

Để tránh mơ hồ:

- Ưu tiên truyền object bất biến (immutable) hoặc collection không thể sửa đổi sau khi tạo.
- Nếu hợp đồng yêu cầu snapshot tại thời điểm gửi, hãy tạo bản sao trước khi chuyển giao và kiểm tra bản sao đó.
- Nếu cần xác minh trạng thái đúng tại thời điểm tương tác của một object mutable, có thể dùng `thenAnswer(...)` để ghi lại một bản sao trong lúc mock nhận lời gọi.

Ví dụ ghi snapshot trong answer:

```java
List<List<String>> snapshots = new ArrayList<>();

doAnswer(invocation -> {
    List<String> argument = invocation.getArgument(0);
    snapshots.add(List.copyOf(argument));
    return null;
}).when(gateway).send(anyList());
```

`List.copyOf(...)` tạo danh sách không thể sửa đổi với các phần tử hiện tại. Đây là snapshot nông; nếu phần tử bên trong cũng mutable, cần sao chép chúng theo cấu trúc dữ liệu của ứng dụng. Với trường hợp đơn giản, dùng captor thông thường vẫn là lựa chọn rõ ràng nhất.

## 11. Những lỗi thường gặp khi sử dụng ArgumentCaptor

### 11.1. Quên gọi method trước khi verify

Captor chỉ thu thập đối số của tương tác đã xảy ra. Nếu service chưa được thực thi hoặc nhánh code không gọi mock, `verify(...)` sẽ thất bại vì không tìm thấy invocation phù hợp.

### 11.2. Dùng getValue() khi có nhiều lần gọi

`getValue()` trả về giá trị capture cuối cùng. Nếu cần kiểm tra toàn bộ dữ liệu gửi đi, dùng `getAllValues()` và xác minh số lần gọi tương ứng.

### 11.3. Khai báo @Captor nhưng không khởi tạo Mockito annotation

Field có `@Captor` sẽ chưa được khởi tạo nếu không dùng `MockitoExtension`, `MockitoAnnotations.openMocks(...)` hoặc cơ chế tương ứng. Khi đó, truy cập field có thể gây `NullPointerException`.

### 11.4. Trộn matcher và giá trị literal

Khi một đối số dùng `capture()` hoặc matcher khác, các đối số còn lại trong cùng lời gọi phải dùng matcher tương ứng. Dùng `eq(...)` cho giá trị cố định để tránh `InvalidUseOfMatchersException`.

### 11.5. Capture sai kiểu hoặc sai vị trí

Captor phải có kiểu tương ứng với đối số của method và được đặt đúng vị trí trong lời gọi verify. Với method overload, cần kiểm tra chữ ký được Mockito chọn để bảo đảm captor đang thu thập đúng tham số.

### 11.6. Dùng captor để kiểm tra chi tiết nội bộ không thuộc hợp đồng

Nếu test kiểm tra mọi trường của một object nội bộ mà không ảnh hưởng hành vi công khai, nó có thể trở nên mong manh khi refactor. Chỉ capture dữ liệu ở ranh giới có ý nghĩa: command gửi sang application service, event phát ra, request gửi tới gateway hoặc dữ liệu truyền tới repository khi đó là hành vi cần bảo vệ.

### 11.7. Nhầm captor với việc kiểm tra dữ liệu đã được lưu

Capture đối số gửi vào repository chỉ xác nhận dữ liệu mà service truyền tới repository. Nó không chứng minh database đã lưu dữ liệu thành công, trigger đã xử lý ra sao hoặc transaction đã commit. Muốn kiểm tra persistence, cần kiểm thử tích hợp phù hợp và đọc lại trạng thái lưu trữ.

## 12. Thực hành thiết kế test với ArgumentCaptor

Khi quyết định dùng captor, hãy xác định rõ ranh giới tương tác và dữ liệu quan trọng cần kiểm tra:

1. Chọn mock đại diện cho dependency mà đối tượng đang kiểm thử gọi tới.
2. Thực thi hành vi qua public method của đối tượng đang kiểm thử.
3. Xác minh đúng method và số lần gọi bằng `verify(...)`, `times(...)` hoặc chế độ xác minh phù hợp.
4. Đặt `capture()` ở các vị trí đối số cần quan sát.
5. Đọc `getValue()` cho một lần gọi hoặc `getAllValues()` cho nhiều lần gọi.
6. Assertion vào các trường thuộc hợp đồng tương tác, chẳng hạn mã định danh, người nhận, số tiền, trạng thái hoặc nội dung event.
7. Kiểm tra thêm các tương tác không mong muốn nếu đó là một phần của yêu cầu, nhưng tránh xác minh quá nhiều chi tiết triển khai.

Ví dụ, khi kiểm tra một service phát event sau khi tạo đơn hàng, test có thể xác nhận event chứa đúng `orderId`, `customerId` và `total`, đồng thời xác minh publisher chỉ được gọi một lần. Nếu dữ liệu không hợp lệ thì có thể xác minh publisher không được gọi. Những assertion này bảo vệ hành vi quan trọng tại ranh giới giữa service và hệ thống nhận event.

ArgumentCaptor giúp bài kiểm thử nhìn thấy dữ liệu thực sự được truyền qua một lời gọi mock. Khi kết hợp đúng với `verify`, nó làm rõ trách nhiệm ánh xạ và truyền dữ liệu của service hoặc controller, hỗ trợ kiểm tra DTO/event nhiều trường và nhiều lần gửi. Hãy giữ captor ở các ranh giới có ý nghĩa, kiểm tra đúng số lần gọi và lưu ý rằng captor giữ tham chiếu tới object được gửi thay vì tự tạo snapshot của nó.
