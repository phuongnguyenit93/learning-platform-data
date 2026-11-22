# max-messages-per-poll

## 1. Giới hạn công việc trong một lượt poll

Trong chương **Poller** của module **SPRING_INTEGRATION_CORE**, `max-messages-per-poll` giúp kiểm soát lượng công việc mà một polling endpoint thực hiện trong mỗi lượt được kích hoạt. Thuộc tính này liên hệ trực tiếp với ba thành phần cốt lõi của Spring Integration:

- `MessageSource` cung cấp thông điệp cho một inbound channel adapter có cơ chế polling.
- `PollableChannel`, chẳng hạn `QueueChannel`, giữ thông điệp để một polling consumer chủ động nhận.
- Endpoint thực hiện thao tác nhận và chuyển thông điệp vào luồng xử lý, nơi transformer, filter, router hoặc service activator tiếp tục làm việc.

Tên thuộc tính trong XML là `max-messages-per-poll`; trong Java DSL là `maxMessagesPerPoll(...)`.

Giả sử một `QueueChannel` đang có 20 thông điệp. Poller chạy với `fixedDelay = 1.000 ms` và `maxMessagesPerPoll = 5`. Khi không có lỗi, không có consumer cạnh tranh và không có thành phần chặn việc nhận, một lượt poll lấy và chuyển tối đa 5 thông điệp cho endpoint xử lý. Nếu queue chỉ còn 2 thông điệp, lượt đó dừng sau khi xử lý chúng rồi gặp lần nhận không có dữ liệu.

**Đây là giới hạn trên cho một lượt poll, không phải số thông điệp bắt buộc phải xử lý và cũng không phải giới hạn kích thước queue.**

## 2. Một lần kích hoạt có thể nhận nhiều thông điệp

Cần phân biệt lịch kích hoạt poller và vòng lặp nhận thông điệp bên trong mỗi lần kích hoạt:

```text
Trigger kích hoạt một lượt poll
    |
    +-- Nhận thông điệp thứ 1 -> xử lý/chuyển tiếp
    +-- Nhận thông điệp thứ 2 -> xử lý/chuyển tiếp
    +-- ...
    +-- Dừng khi đạt giới hạn hoặc không nhận được thông điệp
```

Có thể hình dung bằng mã giả sau. Đây không phải mã nguồn của framework:

```java
void runOnePollingTask() {
    long processed = 0;

    while (endpointIsRunning()
            && (maxMessagesPerPoll < 0 || processed < maxMessagesPerPoll)) {
        Message<?> message = receiveOneMessage();

        if (message == null) {
            break;
        }

        processOrForward(message);
        processed++;
    }
}
```

Mã giả minh họa đường đi thành công. Advice, transaction, lỗi, trạng thái lifecycle và cấu hình executor có thể ảnh hưởng việc thực thi thực tế. Nếu một lần nhận hoặc xử lý ném ngoại lệ ra ngoài, không được giả định rằng các thông điệp còn lại trong lượt đó chắc chắn tiếp tục được xử lý.

Với luồng đồng bộ qua `DirectChannel`, thời gian xử lý downstream thường nằm trong thời gian của lượt poll. Nếu thông điệp được bàn giao qua `ExecutorChannel` hoặc một ranh giới bất đồng bộ khác, poller có thể hoàn tất việc bàn giao trước khi nghiệp vụ phía sau hoàn tất.

## 3. Ý nghĩa của các giá trị

| Giá trị | Hành vi trong mỗi lượt poll | Điều cần lưu ý |
|---|---|---|
| Số dương, ví dụ `1`, `5`, `20` | Thực hiện tối đa số lần nhận và xử lý thành công tương ứng, dừng sớm khi không có thông điệp | Phù hợp khi cần giới hạn công việc mỗi lượt |
| `0` | Không thực hiện thao tác nhận thông điệp trong lượt poll | Không đồng nghĩa với dừng lifecycle của endpoint |
| Số âm, thường dùng `-1` | Không giới hạn số thông điệp theo bộ đếm; tiếp tục cho đến khi lần nhận không có dữ liệu hoặc lượt poll bị ngắt bởi điều kiện khác | Có thể kéo dài rất lâu nếu nguồn liên tục có dữ liệu |

### 3.1. Giá trị `1`

Mỗi lượt poll xử lý tối đa một thông điệp. Cấu hình dễ quan sát, tạo điểm kết thúc thường xuyên giữa các lượt, nhưng khi tồn đọng nhiều thông điệp thì khả năng rút queue có thể thấp nếu khoảng nghỉ lớn.

### 3.2. Giá trị dương lớn hơn `1`

Một lượt poll có thể nhận nhiều thông điệp liên tiếp mà không chờ trigger kế tiếp giữa từng thông điệp. Tuy nhiên, nếu lần nhận đầu tiên trả về `null`, lượt đó kết thúc ngay; poller không cố gọi nhận đủ số lần đã cấu hình.

Giá trị `10` cũng không yêu cầu poller chờ queue tích lũy đủ 10 thông điệp rồi mới bắt đầu.

### 3.3. Giá trị `0`

`0` bỏ qua công việc nhận thông điệp. Lịch của endpoint có thể vẫn hoạt động trong khi mỗi lượt không lấy dữ liệu. Khi cần dừng endpoint để vận hành, hãy sử dụng cơ chế lifecycle phù hợp và phân biệt rõ mục đích với việc đặt giới hạn bằng `0`.

### 3.4. Giá trị âm

`-1` không có nghĩa là xử lý âm một thông điệp. Nó biểu thị việc không đặt giới hạn số lượng trong vòng poll.

Đặc biệt, một nguồn luôn trả về một thông điệp mới có thể khiến một lượt poll không kết thúc theo cách thông thường. Khi đó, khoảng chờ của `fixedDelay` chưa có cơ hội bắt đầu vì lượt hiện tại chưa hoàn thành.

## 4. Phân biệt hai loại endpoint và giá trị mặc định

Không nên suy từ tên “poller” rằng mọi endpoint đều có cùng giá trị mặc định.

| Trường hợp | Endpoint thường gặp | Thao tác nhận | Mặc định khi không ghi đè cấu hình |
|---|---|---|---|
| Inbound channel adapter đọc một nguồn | `SourcePollingChannelAdapter` | `MessageSource.receive()` | `1` |
| Consumer đọc một pollable channel | `PollingConsumer` | `PollableChannel.receive(...)` | `-1` |

Inbound adapter sử dụng mặc định `1` vì nhiều `MessageSource` có thể tạo dữ liệu mỗi khi được gọi. Ví dụ, một supplier tạo timestamp mới sẽ không tự trả về `null` để báo hết dữ liệu. Nếu cho nguồn này chạy không giới hạn trong một lượt, nó có thể phát liên tục trong chính lượt đó.

Polling consumer trên `QueueChannel` có khả năng rút nhiều thông điệp trong một lượt. Với giá trị âm, lượt poll thường kết thúc khi queue không còn dữ liệu và thao tác nhận không lấy được thông điệp trong thời gian chờ.

Các giá trị trong bảng là mặc định theo loại endpoint; một poller dùng chung hoặc cấu hình tường minh có thể thay đổi hành vi cuối cùng. Trong ví dụ học tập và cấu hình cần kiểm soát tải, nên đặt rõ giá trị thay vì dựa vào mặc định.

`DirectChannel` chuyển thông điệp trực tiếp đến subscriber nên consumer trên channel này không cần poller để nhận. Thuộc tính đang học thuộc về polling endpoint, không phải tùy chọn giới hạn chung cho mọi `MessageChannel`.

## 5. Java DSL: lấy tối đa ba thông điệp từ QueueChannel

Ví dụ dưới đây tạo một cấu hình độc lập để quan sát cách một polling consumer đọc `QueueChannel`. Mỗi thông điệp được chuyển sang chữ hoa rồi đưa vào queue kết quả.

Giả định ứng dụng đã có các dependency Spring Context và Spring Integration Core tương thích. Nếu dùng Spring Boot, có thể đặt cấu hình vào ứng dụng đã bật hạ tầng Spring Integration; không cần tạo thêm context thủ công như phần chạy thử bên dưới.

```java
import java.util.Locale;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
public class BoundedPollerConfig {

    @Bean
    public QueueChannel workQueue() {
        return new QueueChannel(100);
    }

    @Bean
    public QueueChannel resultQueue() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow boundedFlow() {
        return IntegrationFlow.from(workQueue())
                .bridge(endpoint -> endpoint
                        .id("boundedBridge")
                        .autoStartup(false)
                        .poller(
                        Pollers.fixedDelay(1000)
                                .maxMessagesPerPoll(3)
                                .receiveTimeout(0)))
                .<String, String>transform(
                        value -> value.toUpperCase(Locale.ROOT))
                .channel(resultQueue())
                .get();
    }
}
```

Trong ví dụ này:

- `workQueue()` là `PollableChannel`, nên endpoint bridge nhận đầu vào cần poller.
- `autoStartup(false)` giữ endpoint chưa chạy để chương trình minh họa nạp dữ liệu trước; sau đó chương trình gọi `start()` tường minh. Khi triển khai luồng tự khởi động bình thường, có thể bỏ tùy chọn này.
- `fixedDelay(1000)` cấu hình khoảng nghỉ 1.000 ms tính từ khi lượt trước hoàn tất trong cách thực thi đồng bộ đang minh họa.
- `maxMessagesPerPoll(3)` giới hạn một lượt nhận tối đa ba thông điệp.
- `receiveTimeout(0)` làm thao tác nhận trên queue trả về ngay nếu queue rỗng.
- Transformer và việc gửi vào `resultQueue()` chạy đồng bộ theo luồng này.
- Dung lượng `100` của queue là cấu hình độc lập với giới hạn `3` của poller.

Không đặt poller lên transformer phía sau chỉ vì muốn “xử lý theo nhóm”. Trong cấu hình trên, bridge là endpoint nhận từ queue; poller đặt tại đó mới điều khiển việc rút queue.

### 5.1. Chạy thử với dữ liệu nạp trước

Endpoint bridge ở trên có `autoStartup(false)`, nên context có thể khởi tạo đầy đủ mà poller chưa nhận dữ liệu. Chương trình nạp bảy message, sau đó khởi động đúng endpoint qua giao diện `Lifecycle`.

```java
import java.util.List;

import org.springframework.context.Lifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class BoundedPollerDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                BoundedPollerConfig.class)) {
            QueueChannel input = context.getBean("workQueue", QueueChannel.class);
            QueueChannel output = context.getBean("resultQueue", QueueChannel.class);

            for (String value : List.of("a", "b", "c", "d", "e", "f", "g")) {
                boolean sent = input.send(
                        MessageBuilder.withPayload(value).build(), 0);
                if (!sent) {
                    throw new IllegalStateException("Không nạp được dữ liệu mẫu");
                }
            }

            context.getBean("boundedBridge", Lifecycle.class).start();

            for (int i = 0; i < 7; i++) {
                Message<?> message = output.receive(5000);
                if (message == null) {
                    throw new IllegalStateException("Quá thời gian chờ kết quả");
                }
                System.out.println(message.getPayload());
            }
        }
    }
}
```

Bảy kết quả sẽ là `A` đến `G`. Trong điều kiện ví dụ, giới hạn công việc của các lượt có dữ liệu lần lượt là `3 + 3 + 1`. Thời điểm in thực tế còn phụ thuộc scheduler và tải hệ thống; không nên coi các mốc thời gian tuyệt đối là hợp đồng của poller.

## 6. Java DSL: giới hạn poller của MessageSource

Đoạn cấu hình sau minh họa riêng một inbound channel adapter. Giả định `externalBuffer` và `sourceOutput` là các bean dùng cho luồng này, độc lập với ví dụ trước.

```java
@Bean
public java.util.concurrent.BlockingQueue<String> externalBuffer() {
    return new java.util.concurrent.LinkedBlockingQueue<>();
}

@Bean
public org.springframework.integration.core.MessageSource<String> bufferedSource(
        java.util.concurrent.BlockingQueue<String> externalBuffer) {

    return () -> {
        String value = externalBuffer.poll();
        if (value == null) {
            return null;
        }
        return org.springframework.messaging.support.MessageBuilder
                .withPayload(value)
                .build();
    };
}

@Bean
public QueueChannel sourceOutput() {
    return new QueueChannel(100);
}

@Bean
public IntegrationFlow sourceFlow(
        org.springframework.integration.core.MessageSource<String> bufferedSource) {

    return IntegrationFlow.from(bufferedSource,
                    endpoint -> endpoint.poller(
                            Pollers.fixedDelay(1000)
                                    .maxMessagesPerPoll(5)))
            .channel(sourceOutput())
            .get();
}
```

Mỗi lượt gọi nguồn tối đa năm lần để lấy tối đa năm thông điệp. Nếu `externalBuffer.poll()` trả về `null`, `MessageSource` cũng trả về `null`, báo cho adapter kết thúc lượt sớm.

Vì nguồn dùng `BlockingQueue.poll()` không có tham số thời gian, thao tác lấy dữ liệu là không chờ. `receiveTimeout` của poller đọc một `PollableChannel` không phải cách điều khiển timeout nội bộ của một nguồn tùy ý; thời gian chờ đọc file, HTTP, JDBC hoặc buffer còn phụ thuộc triển khai và cấu hình của nguồn tương ứng.

Nếu sửa `bufferedSource` thành một nguồn luôn tạo dữ liệu mới, hãy giữ giới hạn dương để mỗi lượt có điểm kết thúc rõ ràng.

## 7. Không nhầm với batch nghiệp vụ và số lượng phần tử payload

`maxMessagesPerPoll` đếm thông điệp được polling endpoint nhận, không tự đếm các phần tử bên trong payload.

| Dữ liệu được nhận | Với `maxMessagesPerPoll(3)` |
|---|---|
| Mỗi message chứa một mã đơn hàng | Nhận tối đa ba message, tương ứng tối đa ba mã |
| Mỗi message chứa `List<Order>` với 100 đơn | Nhận tối đa ba message; payload có thể chứa tổng cộng 300 đơn |
| Một message được splitter tách thành 20 message | Một lần nhận ở poller có thể dẫn đến 20 message downstream |
| Nhiều message được aggregator gom thành một nhóm | Số message đầu ra do chiến lược gom nhóm quyết định |

Thuộc tính này không tự tạo một `List` từ nhiều message, không đặt release strategy cho aggregator và không tạo ranh giới commit theo nhóm. Nếu yêu cầu nghiệp vụ là “ghi database mỗi nhóm 50 đơn hàng”, cần thiết kế việc gom nhóm, ghi dữ liệu và transaction tương ứng.

Tương tự, nếu JDBC adapter đọc nhiều dòng trong một lần truy vấn rồi đóng gói thành một message, giới hạn số message của poller và giới hạn số dòng mỗi lần truy vấn là hai cấu hình khác nhau.

## 8. Quan hệ với lịch, timeout và thông lượng

### 8.1. Fixed delay không phải thời gian giữa từng message

Giả sử mỗi message cần 40 ms xử lý đồng bộ, `maxMessagesPerPoll = 5` và `fixedDelay = 1.000 ms`:

```text
Lượt 1: [m1 40ms][m2 40ms][m3 40ms][m4 40ms][m5 40ms]
        <---------------- khoảng 200ms ---------------->
                                                        nghỉ 1000ms
                                                                    Lượt 2...
```

Bỏ qua overhead và các thời gian chờ khác, thông lượng xấp xỉ:

```text
Thông lượng ≈ M / (M × T + D)

M: số message thực tế được xử lý trong mỗi lượt
T: thời gian xử lý trung bình mỗi message, tính bằng giây
D: fixed delay, tính bằng giây
```

Với `M = 5`, `T = 0,04` và `D = 1`, kết quả khoảng `4,17 message/giây` khi nguồn luôn đủ dữ liệu. Không phải cứ cấu hình năm message với delay một giây là chắc chắn đạt năm message/giây.

Công thức chỉ phù hợp với mô hình đồng bộ đơn giản. Executor, xử lý song song, thời gian chờ gửi vào channel, advice và tải hệ thống có thể làm mô hình thay đổi.

### 8.2. Receive timeout ảnh hưởng độ dài lượt poll

Với poller đọc `QueueChannel`, nếu đã lấy hai message nhưng giới hạn là mười, lần nhận tiếp theo có thể chờ thêm theo `receiveTimeout`. Lượt poll chỉ kết thúc sau khi lần nhận đó không có dữ liệu và trả về `null`.

Do đó, thời gian của một lượt có thể bao gồm cả thời gian chờ khi queue rỗng. Đặt timeout dài kết hợp với fixed delay có thể tăng thời gian trước lượt tiếp theo.

Nếu đã nhận đủ mười message, vòng lặp dừng theo giới hạn; không cần một lần nhận thứ mười một chỉ để xác định queue còn dữ liệu hay không.

### 8.3. Fixed rate và task executor

Đổi sang `fixedRate` không biến giới hạn này thành hạn mức message mỗi giây. Trigger xác định lịch; giới hạn xác định lượng công việc tối đa trong từng tác vụ poll.

Khi có `taskExecutor`, cần phân biệt thời điểm scheduler gửi tác vụ với thời điểm tác vụ thực sự chạy và hoàn tất. Pool, hàng đợi executor và chính sách từ chối tác vụ có thể làm nhiều lượt chờ hoặc có cơ hội chạy đồng thời. Không suy luận mức song song chỉ từ `maxMessagesPerPoll`.

Giới hạn `10` cũng không tự tạo mười thread. Một lượt poll thông thường lặp qua các lần nhận; khả năng xử lý song song phụ thuộc cấu hình thực thi và các channel phía sau.

## 9. Lỗi, transaction và việc xử lý lại

Nếu message thứ hai gây lỗi khi giới hạn là năm, không được suy ra rằng cả năm message thuộc một đơn vị retry hoặc cùng được rollback.

Cần xác định riêng:

1. Lỗi xuất hiện khi đọc nguồn, gọi handler hay bàn giao sang channel khác.
2. Poller và handler có advice hoặc transaction nào.
3. Nguồn hoặc channel có tham gia transaction và hỗ trợ phục hồi message hay không.
4. Luồng có ranh giới bất đồng bộ hay không.
5. Lỗi được đưa vào error channel nào và có cơ chế xử lý lại nào.

Đặc biệt, `QueueChannel` trong bộ nhớ ở ví dụ không tự khôi phục message vừa lấy nếu transformer ném ngoại lệ. Đặt `maxMessagesPerPoll(3)` không tạo bảo đảm xử lý đúng một lần hoặc bảo đảm phát lại.

Với poller có transaction advice, cần xét phạm vi advice thực tế và tài nguyên tham gia. Không dùng riêng giá trị giới hạn để khẳng định transaction bao trùm từng message hay cả lượt. Nếu downstream chuyển sang thread khác, transaction gắn với thread hiện tại cũng không tự đi theo message sang thread đó.

## 10. Chọn giá trị theo đặc tính công việc

Một cách bắt đầu là đặt giới hạn dương nhỏ, đo lượng tồn đọng và thời gian lượt poll, rồi điều chỉnh theo tải thực tế.

| Hiện tượng | Hướng xem xét |
|---|---|
| Queue tăng đều nhưng handler còn khả năng xử lý | Tăng giới hạn hoặc giảm khoảng nghỉ sau khi đo |
| Một lượt poll chạy rất lâu | Giảm giới hạn; kiểm tra latency downstream và timeout |
| Nguồn luôn sinh thông điệp | Dùng giới hạn dương để lượt poll có thể kết thúc |
| Hệ thống ngoài bị dồn yêu cầu | Giảm lượng nhận mỗi lượt và kiểm tra thêm concurrency, retry, rate limiting |
| Kích thước payload chênh lệch lớn | Theo dõi số phần tử/byte và thời gian xử lý, không chỉ số message |
| Scheduler bị giữ lâu, endpoint khác chậm | Kiểm tra pool scheduler và thời gian chiếm thread; cân nhắc executor phù hợp |

Ví dụ, một luồng đồng bộ gọi API ngoài mất khoảng 200 ms cho mỗi message. Nếu muốn phần xử lý message trong một lượt nằm quanh một giây, có thể bắt đầu thử với giới hạn năm. Đây là điểm xuất phát để đo, không phải bảo đảm thời gian thực vì độ trễ API có thể biến động.

Nếu API cho phép tối đa 100 yêu cầu mỗi phút, giới hạn message mỗi lượt không tự bảo đảm hạn mức đó. Nhiều instance, retry, splitter hoặc xử lý song song đều có thể tăng số yêu cầu thực tế. Khi cần hạn mức theo thời gian, phải có cơ chế điều tiết tương ứng.

## 11. Kịch bản kiểm chứng hành vi

Những kịch bản sau dùng để thực hành quan sát hoặc viết kiểm thử riêng cho cấu hình ứng dụng; nội dung bài không khẳng định đã chạy chúng trong repository.

| Kịch bản | Kết quả cần kiểm tra |
|---|---|
| Nạp sẵn 7 message, giới hạn 3 | Các lượt có dữ liệu xử lý theo giới hạn `3 + 3 + 1` nếu không có yếu tố khác can thiệp |
| Nạp sẵn 2 message, giới hạn 10, timeout 0 | Hai message được chuyển đi; lần nhận kế tiếp không có dữ liệu làm lượt kết thúc |
| Queue rỗng, timeout 0 | Lượt không tạo message đầu ra và kết thúc nhanh |
| Giới hạn 0 | Queue không bị poller lấy message |
| Nguồn hữu hạn, giới hạn -1 | Một lượt có thể rút hết dữ liệu sẵn có cho đến khi nguồn trả về `null` |
| Một message chứa danh sách 100 phần tử, giới hạn 1 | Poller nhận một message; payload vẫn có 100 phần tử |
| Handler ném ngoại lệ | Xác minh đường lỗi và khả năng phục hồi theo cấu hình thực tế |

Để kiểm chứng ranh giới từng lượt, nên gắn quan sát tại nguồn hoặc endpoint và điều khiển trigger trong kiểm thử. Chỉ đếm tổng số message sau vài giây không chứng minh được mỗi lượt tuân thủ giới hạn. Tránh kiểm thử chỉ dựa vào `Thread.sleep()` rồi yêu cầu một số đếm đúng tuyệt đối tại một mốc thời gian ngắn vì scheduler có thể bị trễ.

Với ví dụ Java DSL, có thể kiểm tra payload đầu ra và số lượng kết quả bằng `QueueChannel.receive(timeout)` có giới hạn chờ. Việc kiểm tra đó xác minh luồng đã chuyển đủ dữ liệu; muốn xác minh riêng nhịp `3 + 3 + 1`, cần quan sát thêm ranh giới các lượt poll.

## 12. Những điểm cần ghi nhớ

`max-messages-per-poll` đặt trần số message mà một polling endpoint nhận và xử lý/chuyển tiếp trong mỗi lượt. Giới hạn dương tạo điểm kết thúc theo số lượng; `0` bỏ qua việc nhận; giá trị âm tiếp tục cho đến khi nguồn hoặc channel không cung cấp message hay xuất hiện điều kiện kết thúc khác.

Khi thiết kế một luồng Spring Integration, hãy xác định endpoint đang đọc `MessageSource` hay `PollableChannel`, vị trí ranh giới đồng bộ/bất đồng bộ, thời gian chờ và đặc tính payload. Kết hợp những yếu tố đó mới giải thích được tác động thực tế của giới hạn lên độ trễ, thông lượng và tải downstream.