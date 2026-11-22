# PriorityChannel và Comparator

Trong Spring Integration Runtime, PriorityChannel là một channel dạng hàng đợi dùng để chọn message tiếp theo theo mức ưu tiên. Comparator quyết định thứ tự lấy message ra khỏi hàng đợi. Hai thành phần này hữu ích khi một IntegrationFlow phải xử lý yêu cầu khẩn cấp trước yêu cầu thông thường, nhưng chúng chỉ điều phối thứ tự trong hàng đợi của channel; chúng không tự tạo worker, không ngắt một handler đang chạy và không bảo đảm message được xử lý xong theo đúng thứ tự đã lấy ra.

## PriorityChannel nằm ở đâu trong message flow?

PriorityChannel triển khai PollableChannel. Producer gửi message vào channel; một polling consumer gọi receive thông qua poller để lấy message; sau đó endpoint chuyển message cho handler. Channel không tự khởi chạy luồng xử lý.

~~~mermaid
flowchart LR
    P["Producer"] -->|"send(Message)"| Q["PriorityChannel"]
    Q -->|"poll / receive"| C["Polling consumer"]
    C --> H["Service Activator hoặc handler"]
~~~

Khác với DirectChannel, việc gửi vào PriorityChannel thường chỉ đưa message vào hàng đợi. Producer không chờ handler xử lý xong. Consumer lấy message theo thứ tự do comparator xác định, vì vậy thời điểm poll và số consumer đều ảnh hưởng đến hành vi runtime.

## Quy tắc ưu tiên mặc định

Comparator mặc định của PriorityChannel đọc header priority của message. Giá trị priority lớn hơn được lấy trước; message không có header này được xem như có mức ưu tiên 0. Ví dụ, nếu hàng đợi đang chứa các message có priority lần lượt là 0, 5 và 10, consumer sẽ lấy message priority 10 trước, sau đó đến 5 và 0.

Có thể tạo message bằng IntegrationMessageHeaderAccessor.PRIORITY:

~~~java
import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

PriorityChannel channel = new PriorityChannel();

Message<String> normal = MessageBuilder.withPayload("normal")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 0)
        .build();

Message<String> urgent = MessageBuilder.withPayload("urgent")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 10)
        .build();

channel.send(normal);
channel.send(urgent);

Message<?> first = channel.receive(0);
// first.getPayload() là "urgent"
~~~

receive(0) thử lấy message ngay lập tức và trả về null nếu hàng đợi đang rỗng. Trong ứng dụng thực tế, polling consumer thường gọi receive theo lịch poller thay vì tự gọi receive trong mã nghiệp vụ.

Nếu không cần quy tắc riêng, dùng PriorityChannel mặc định giúp producer chỉ cần gắn header priority. Hãy thống nhất thang điểm trong toàn flow, chẳng hạn 0 là bình thường, 5 là cần chú ý và 10 là khẩn cấp. Tránh để mỗi producer tự diễn giải cùng một giá trị theo cách khác nhau.

## Tùy biến bằng Comparator

Khi cần thêm tiêu chí, truyền Comparator<Message<?>> vào constructor. Ví dụ dưới đây sắp xếp theo priority giảm dần, rồi theo enqueueSequence tăng dần. Tiêu chí thứ hai giúp giữ thứ tự FIFO giữa các message cùng mức ưu tiên, miễn là producer cấp sequence theo một bộ đếm dùng chung trong phạm vi cần bảo đảm thứ tự.

~~~java
import java.util.Comparator;

import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;

@Bean
PriorityChannel priorityChannel() {
    Comparator<Message<?>> comparator =
            Comparator.<Message<?>>comparingInt(message -> {
                Integer priority = message.getHeaders().get(
                        IntegrationMessageHeaderAccessor.PRIORITY, Integer.class);
                return priority != null ? priority : 0;
            }).reversed()
              .thenComparingLong(message -> {
                  Long sequence = message.getHeaders().get(
                          "enqueueSequence", Long.class);
                  return sequence != null ? sequence : Long.MAX_VALUE;
              });

    return new PriorityChannel(comparator);
}
~~~

Producer phải gắn cả hai header theo cùng quy ước:

~~~java
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.integration.IntegrationMessageHeaderAccessor;
import org.springframework.integration.channel.PriorityChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class PriorityPublisher {

    private final PriorityChannel channel;
    private final AtomicLong sequence = new AtomicLong();

    PriorityPublisher(PriorityChannel channel) {
        this.channel = channel;
    }

    public void publish(String payload, int priority) {
        Message<String> message = MessageBuilder.withPayload(payload)
                .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, priority)
                .setHeader("enqueueSequence", sequence.incrementAndGet())
                .build();

        if (!channel.send(message)) {
            throw new IllegalStateException("Không gửi được message vào PriorityChannel");
        }
    }
}
~~~

Bộ đếm AtomicLong ở ví dụ chỉ cấp thứ tự trong một publisher instance. Nếu nhiều instance cùng ghi vào channel hoặc sequence được tạo ở nhiều node, cần một nguồn sequence có phạm vi phù hợp, hoặc chấp nhận rằng FIFO chỉ được bảo đảm trong từng nguồn. Nếu không có enqueueSequence, comparator trả Long.MAX_VALUE cho tiêu chí phụ; những message cùng priority và cùng giá trị phụ không có bảo đảm FIFO.

Có thể thay tiêu chí phụ bằng deadline, loại công việc hoặc nhóm khách hàng. Comparator nên đọc các header bất biến đã được gắn trước khi gửi message. Tránh truy vấn cơ sở dữ liệu, phân tích payload lớn hoặc đọc trạng thái có thể thay đổi trong lúc message nằm trong queue. Một comparator phải tạo ra quan hệ thứ tự nhất quán, có tính bắc cầu và cho cùng kết quả khi so sánh cùng một cặp message. Nếu kết quả thay đổi theo thời gian, cấu trúc heap có thể không còn được sắp xếp đúng.

## Kết nối polling consumer và IntegrationFlow

Vì PriorityChannel là PollableChannel, consumer cần một poller. Có thể khai báo endpoint bằng annotation:

~~~java
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.messaging.Message;
import org.springframework.stereotype.Component;

@Component
class PriorityHandler {

    @ServiceActivator(
            inputChannel = "priorityChannel",
            poller = @Poller(fixedDelay = "100")
    )
    public void handle(Message<?> message) {
        // Xử lý payload và headers của message.
    }
}
~~~

Trong cấu hình này, endpoint poll channel theo fixed delay 100 ms. Poller quyết định nhịp lấy message; comparator chỉ quyết định message nào đứng đầu hàng đợi tại thời điểm receive. Khi dùng Java DSL, cấu hình poller tại endpoint đọc từ pollable channel theo API của phiên bản Spring Integration đang dùng. Đừng nhầm poller với executor: poller lên lịch việc lấy message, còn executor (nếu được cấu hình ở endpoint hoặc thành phần kế tiếp) quyết định nơi và mức độ song song khi thực thi công việc.

## Những giới hạn cần hiểu đúng

- **Không preempt:** nếu consumer đã lấy message priority thấp và handler đang chạy, message priority cao vừa đến không thể chen ngang handler đó. Message mới chỉ được ưu tiên ở lần lấy tiếp theo.
- **Thứ tự lấy khác thứ tự hoàn tất:** với nhiều consumer hoặc xử lý bất đồng bộ, message có priority cao có thể được lấy trước nhưng hoàn tất sau một message khác. Nếu cần thứ tự hoàn tất nghiêm ngặt, phải giới hạn concurrency hoặc thiết kế bước tuần tự hóa riêng.
- **Không mặc định FIFO khi bằng điểm:** priority queue không cam kết thứ tự đến trước cho các phần tử có comparator trả về 0. Hãy thêm sequence header nếu thứ tự đó là yêu cầu nghiệp vụ.
- **Có thể starvation:** luồng message ưu tiên cao liên tục có thể khiến message ưu tiên thấp phải chờ rất lâu. Nếu cần công bằng, cân nhắc chia lớp ưu tiên, giới hạn tỷ lệ xử lý hoặc thiết kế scheduler có weighted fairness.
- **Không có thứ tự toàn cục:** comparator chỉ sắp xếp message trong cùng một PriorityChannel. Hai channel riêng biệt không phối hợp để tạo một hàng đợi ưu tiên chung.
- **Không thay thế durability:** PriorityChannel là hàng đợi trong bộ nhớ. Nó không tự cung cấp lưu trữ bền vững qua lần khởi động lại, retry nghiệp vụ hay transaction với hệ thống bên ngoài. Nếu cần phục hồi message sau sự cố, hãy dùng cơ chế lưu trữ hoặc broker phù hợp và cấu hình transaction/retry ở endpoint theo yêu cầu.
- **Theo dõi backlog:** các implementation dựa trên PriorityBlockingQueue dùng hàng đợi không giới hạn. Tham số initial capacity, nếu constructor của phiên bản đang dùng có cung cấp, là dung lượng khởi tạo chứ không phải giới hạn cứng để tạo back-pressure. Theo dõi queue depth, tốc độ vào/ra, tuổi của message cũ nhất và thời gian xử lý; kiểm soát tốc độ producer hoặc dùng một cơ chế bounded/broker khi cần giới hạn backlog.

Message có correlationId vẫn được sắp xếp theo comparator như message khác. Nếu các message cùng correlation group cần được xử lý theo thứ tự nghiệp vụ, hãy đưa sequence vào comparator hoặc bảo đảm thứ tự ở một bước riêng. Việc chỉ gắn correlationId không tự giữ thứ tự đến.

## Kiểm tra hành vi

Một kiểm tra nhỏ có thể xác nhận comparator đang được áp dụng như dự kiến:

~~~java
PriorityChannel channel = new PriorityChannel();

channel.send(MessageBuilder.withPayload("low")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 1)
        .build());
channel.send(MessageBuilder.withPayload("high")
        .setHeader(IntegrationMessageHeaderAccessor.PRIORITY, 9)
        .build());

assertThat(channel.receive(0).getPayload()).isEqualTo("high");
assertThat(channel.receive(0).getPayload()).isEqualTo("low");
~~~

Khi chẩn đoán kết quả sai, kiểm tra lần lượt: producer có gắn đúng header priority không; header có phải kiểu Integer không; channel bean thực tế có dùng comparator dự kiến không; consumer có đọc đúng PriorityChannel không; có consumer khác lấy message trước không; và handler có chạy song song khiến thứ tự hoàn tất khác thứ tự lấy không.

## Khi nào nên dùng?

| Nhu cầu runtime | Cách chọn |
|---|---|
| Chỉ cần message priority cao được lấy trước | PriorityChannel với comparator mặc định |
| Cần tie-break theo deadline hoặc sequence | PriorityChannel với Comparator<Message<?>> tùy chỉnh |
| Cần FIFO tuyệt đối cho toàn bộ luồng | Thiết kế tuần tự hóa phù hợp; không dựa riêng vào priority queue |
| Cần giới hạn backlog hoặc lưu message bền vững | Chọn channel/broker có bounded capacity hoặc persistence phù hợp |
| Cần công bằng giữa các lớp ưu tiên | Bổ sung chính sách fairness thay vì chỉ dùng strict priority |

PriorityChannel giải quyết một quyết định cụ thể trong runtime: message nào được consumer lấy tiếp theo từ hàng đợi này. Hãy đặt chính sách priority ở producer, giữ comparator thuần và ổn định, cấu hình poller/concurrency theo năng lực handler, rồi theo dõi backlog để phát hiện starvation hoặc tốc độ tiêu thụ không theo kịp.
