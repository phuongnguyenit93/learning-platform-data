# fixed-delay

## 1. fixed-delay dùng để giải quyết vấn đề gì?

Trong Spring Integration, poller chủ động kiểm tra một nguồn dữ liệu hoặc một `PollableChannel` theo lịch. Cấu hình `fixed-delay` đặt một khoảng nghỉ sau khi một lượt thực thi poll kết thúc rồi mới cho phép lượt kế tiếp bắt đầu.

Ví dụ, ứng dụng kiểm tra hàng đợi nội bộ, lấy đơn hàng và đưa chúng vào luồng xử lý. Nếu một lượt kiểm tra mất 300 ms và `fixed-delay` là 2 giây, lượt sau bắt đầu khoảng 2,3 giây sau thời điểm bắt đầu lượt trước, trong điều kiện scheduler không bị chậm.

Cách lập lịch này phù hợp khi cần:

- Có thời gian nghỉ giữa hai lượt truy cập một nguồn dữ liệu.
- Để lịch thích ứng với thời gian xử lý biến động của mỗi lượt poll.
- Tránh việc một tác vụ poll đồng bộ liên tục chạy để bù lịch sau khi xử lý lâu.
- Cấu hình luồng bằng Java DSL hoặc endpoint có annotation mà vẫn dễ giải thích nhịp lấy dữ liệu.

`fixed-delay` là thuộc tính lập lịch của poller. Nó không phải thời gian trì hoãn của từng `Message`, không phải thời hạn xử lý nghiệp vụ, và không thay thế giới hạn tốc độ gọi dịch vụ bên ngoài.

## 2. Poller đứng ở đâu trong luồng thông điệp?

Có hai vị trí thường dùng poller trong Spring Integration Core.

### 2.1. Inbound channel adapter lấy dữ liệu từ nguồn

Một `MessageSource` cung cấp dữ liệu khi được gọi `receive()`. Poller lập lịch gọi nguồn; khi nguồn trả về message, adapter gửi message vào channel đầu ra.

```text
Scheduler
    |
    v
Poller -> MessageSource.receive()
                   |
                   v
                Message -> MessageChannel -> transformer/filter/router/handler
```

Trong Java DSL, `IntegrationFlow.fromSupplier(...)` là một cách thuận tiện để tạo nguồn polling. Giá trị khác `null` do supplier trả về được chuyển thành message; `null` thể hiện không có dữ liệu ở lần gọi đó.

### 2.2. Endpoint lấy message từ PollableChannel

`QueueChannel` giữ message trong hàng đợi và cho phép bên nhận chủ động lấy ra. Một polling consumer cần poller để gọi `receive()` trên channel rồi chuyển message cho handler.

```text
Producer -> QueueChannel
                ^
                | receive()
          Poller + polling consumer -> handler
```

Ngược lại, endpoint nhận từ `DirectChannel` được gọi theo cơ chế đẩy khi producer gửi message. Không gắn poller vào endpoint đó để làm chậm việc nhận message. Nếu muốn chuyển từ cơ chế đẩy sang cơ chế lấy theo lịch, có thể đặt một `QueueChannel` tại ranh giới phù hợp.

## 3. Ngữ nghĩa thời gian chính xác

Gọi:

- `D`: giá trị `fixed-delay`.
- `S(n)`: thời điểm tác vụ poll thứ `n` bắt đầu.
- `E(n)`: thời điểm tác vụ poll thứ `n` kết thúc.
- `T(n) = E(n) - S(n)`: thời gian thực thi tác vụ đó.

Với poller chạy đồng bộ trên luồng scheduler, lịch có dạng:

```text
S(n + 1) ≈ E(n) + D
S(n + 1) - S(n) ≈ T(n) + D
```

Dấu xấp xỉ thể hiện tác động của scheduler, tải hệ thống và độ chính xác của đồng hồ. `fixed-delay` không cam kết thời gian thực cứng.

Ví dụ `D = 2 giây`:

```text
Thời gian: 0s       1s       2s       3s       4s       5s       6s
           |--------|--------|--------|--------|--------|--------|
Poll 1:    [0,0 -> 0,4]
Nghỉ:                  [0,4 ----------> 2,4]
Poll 2:                                  [2,4 ------> 3,6]
Nghỉ:                                                   [3,6 -> 5,6]
Poll 3:                                                                  [5,6 ...]
```

Các mốc cần nhớ là `0,0`, `0,4`, `2,4`, `3,6` và `5,6` giây; hình chỉ minh họa trình tự, không biểu diễn theo đúng tỉ lệ.

### 3.1. Một lượt poll không nhất thiết là một message

Một lượt tác vụ có thể gọi nguồn hoặc channel nhiều lần, phụ thuộc `maxMessagesPerPoll`. Vì vậy, thời gian thực thi có thể bao gồm:

1. Chờ lấy message.
2. Tạo và gửi message vào luồng.
3. Xử lý downstream nếu các bước đó chạy đồng bộ.
4. Lặp lại để lấy các message tiếp theo trong cùng lượt.
5. Hoàn tất các bước bao quanh lượt poll, chẳng hạn advice hoặc transaction đã cấu hình.

Nếu `maxMessagesPerPoll = 10`, khoảng nghỉ `fixed-delay` nằm giữa các lượt, không tự động nằm giữa từng cặp message trong nhóm mười message đó.

### 3.2. Phạm vi “kết thúc” phụ thuộc ranh giới bất đồng bộ

Với `DirectChannel`, handler downstream thường chạy ngay trên luồng gửi. Thời gian xử lý handler đó được tính vào thời gian thực thi của tác vụ poll.

Nếu luồng gửi vào một `QueueChannel` khác hoặc chuyển sang executor ở downstream, việc gửi có thể hoàn tất trước khi nghiệp vụ kết thúc. Khi đó, `fixed-delay` không chờ toàn bộ công việc downstream bất đồng bộ hoàn tất.

Đây là lý do cần xác định rõ đang đo thời gian của nguồn, của tác vụ poll hay của toàn bộ quy trình nghiệp vụ.

## 4. Ví dụ Java DSL: lấy tối đa một đơn hàng mỗi lượt

Ví dụ dưới đây dùng Java DSL theo kiểu API của Spring Integration 6.x, với `Pollers.fixedDelay(Duration)`. Dự án cần có `spring-integration-core` và được khởi tạo bằng Spring context. Spring Boot có thể quản lý phiên bản dependency cho dự án sử dụng Boot.

```java
import java.time.Duration;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;

@Configuration
@EnableIntegration
public class FixedDelayOrderFlowConfig {

    @Bean
    public Queue<String> pendingOrders() {
        return new ConcurrentLinkedQueue<>(
                List.of("ORDER-101", "ORDER-102", "ORDER-103"));
    }

    @Bean
    public IntegrationFlow orderPollingFlow(Queue<String> pendingOrders) {
        return IntegrationFlow
                .fromSupplier(
                        pendingOrders::poll,
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(2))
                                        .maxMessagesPerPoll(1)))
                .<String, String>transform(String::toUpperCase)
                .handle(message ->
                        System.out.println("Đã nhận: " + message.getPayload()))
                .get();
    }
}
```

Diễn giải:

- `pendingOrders::poll` trả về và loại bỏ một phần tử khỏi hàng đợi; khi hàng đợi rỗng, nó trả về `null` ngay.
- Poller dùng khoảng nghỉ hai giây sau mỗi lượt thực thi.
- `maxMessagesPerPoll(1)` giới hạn một message cho mỗi lượt.
- Transformer minh họa một endpoint trong luồng. Với dữ liệu đã viết hoa ở đây, payload giữ nguyên giá trị.
- Handler kết thúc luồng bằng cách in payload.

Không nên khẳng định message đầu tiên luôn chờ đúng hai giây sau khi ứng dụng khởi động. Khoảng nghỉ giữa các lượt và độ trễ ban đầu là hai cấu hình khác nhau. Nếu muốn trì hoãn lượt đầu, cấu hình `initialDelay` một cách tường minh.

```java
Pollers.fixedDelay(Duration.ofSeconds(2))
        .initialDelay(Duration.ofSeconds(5))
        .maxMessagesPerPoll(1);
```

Lượt đầu được lên lịch với độ trễ ban đầu khoảng năm giây; các lượt sau áp dụng khoảng nghỉ hai giây tính theo ngữ nghĩa của tác vụ poll.

Ví dụ dùng hàng đợi trong bộ nhớ chỉ để minh họa. Phần tử đã bị loại bỏ ngay khi supplier lấy ra, nên một lỗi downstream không tự đưa phần tử trở lại hàng đợi. Với đơn hàng thật, cần thiết kế độ bền dữ liệu, transaction hoặc cơ chế xác nhận phù hợp.

## 5. Ví dụ polling consumer trên QueueChannel

Khi producer chủ động gửi message vào hàng đợi, đặt poller tại endpoint tiêu thụ hàng đợi:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class QueuedOrderFlowConfig {

    @Bean
    public QueueChannel queuedOrders() {
        return new QueueChannel(100);
    }

    @Bean
    public IntegrationFlow queuedOrderFlow(QueueChannel queuedOrders) {
        return IntegrationFlow
                .from(queuedOrders)
                .handle(
                        message -> processOrder(message),
                        endpoint -> endpoint.poller(
                                Pollers.fixedDelay(Duration.ofSeconds(1))
                                        .maxMessagesPerPoll(5)
                                        .receiveTimeout(0)))
                .get();
    }

    private void processOrder(Message<?> message) {
        System.out.println("Xử lý: " + message.getPayload());
    }

    public static boolean enqueue(QueueChannel channel, String orderId) {
        return channel.send(
                MessageBuilder.withPayload(orderId).build(),
                500);
    }
}
```

Ở đây:

- `QueueChannel(100)` có sức chứa tối đa 100 message.
- Producer có thể gọi `enqueue(...)` từ thành phần khác sau khi lấy bean channel từ Spring.
- Mỗi lượt consumer lấy tối đa năm message, dừng sớm nếu channel không có message.
- `receiveTimeout(0)` làm mỗi lần nhận trở thành kiểm tra ngay, không chờ message xuất hiện.
- Sau khi lượt xử lý kết thúc, poller nghỉ khoảng một giây.

Khi còn nhiều message, năm message có thể được xử lý liên tiếp trong cùng lượt. Đây không phải cấu hình “mỗi message cách nhau một giây”.

Giá trị trả về của `send(..., 500)` cần được xử lý ở producer: `false` nghĩa là không gửi được trong thời gian chờ đó. Giới hạn hàng đợi giúp tạo áp lực ngược ở điểm gửi, nhưng ứng dụng vẫn phải quyết định sẽ chờ, từ chối hay lưu lại công việc.

## 6. Dùng annotation khi phù hợp

Nếu ứng dụng khai báo endpoint bằng annotation, có thể cấu hình poller trực tiếp trên service activator nhận từ một channel có khả năng polling.

```java
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class OrderHandler {

    @ServiceActivator(
            inputChannel = "ordersForAnnotatedHandler",
            poller = @Poller(
                    fixedDelay = "1000",
                    maxMessagesPerPoll = "1"))
    public void handle(String orderId) {
        System.out.println("Đơn hàng: " + orderId);
    }
}
```

Khai báo channel tương ứng trong cấu hình Spring:

```java
@Bean
public QueueChannel ordersForAnnotatedHandler() {
    return new QueueChannel(100);
}
```

Trong ví dụ annotation, giá trị số `"1000"` của `fixedDelay` được hiểu theo đơn vị mili giây mặc định. Kiểu chuỗi cũng cho phép đưa giá trị ra cấu hình bằng placeholder, chẳng hạn `fixedDelay = "${orders.poll-delay-ms:1000}"`.

Đây là phương án cấu hình thay thế cho consumer tương đương bằng DSL. Nếu cùng gắn nhiều consumer vào một `QueueChannel`, chúng cạnh tranh lấy message; mỗi message lấy khỏi hàng đợi được giao cho một consumer, không được phát cho tất cả consumer.

## 7. Phân biệt fixed-delay, fixed-rate và cron

| Cách lập lịch | Mốc dùng để xác định lịch | Phù hợp khi |
|---|---|---|
| `fixed-delay` | Thời điểm tác vụ trước kết thúc | Muốn có khoảng nghỉ sau mỗi lượt |
| `fixed-rate` | Chu kỳ theo các mốc bắt đầu dự kiến | Muốn giữ nhịp thực thi theo chu kỳ |
| `cron` | Biểu thức lịch theo thời gian | Muốn chạy vào giờ, ngày hoặc lịch nghiệp vụ cụ thể |

Giả sử một tác vụ mất 700 ms và chu kỳ cấu hình là 1.000 ms:

- Với `fixed-delay`, hai lần bắt đầu liên tiếp cách nhau khoảng 1.700 ms.
- Với `fixed-rate`, lịch mục tiêu có các mốc cách nhau 1.000 ms; thời điểm thực thi thực tế còn phụ thuộc scheduler và thời gian tác vụ.

Không suy ra rằng `fixed-rate` luôn tạo thực thi song song. Mức độ song song còn phụ thuộc cơ chế lập lịch và executor. Cũng không suy ra rằng `fixed-delay` luôn ngăn mọi xử lý song song: ranh giới bất đồng bộ có thể làm tác vụ lập lịch hoàn tất trước công việc nghiệp vụ.

## 8. Các tham số làm thay đổi hành vi thực tế

### 8.1. maxMessagesPerPoll

Tham số này giới hạn số message được xử lý trong một lượt tác vụ poll.

```java
Pollers.fixedDelay(Duration.ofMillis(500))
        .maxMessagesPerPoll(20);
```

Nếu mỗi message mất 50 ms để xử lý đồng bộ, một lượt đủ 20 message cần xấp xỉ một giây, chưa tính chi phí khác. Lượt kế tiếp bắt đầu sau khoảng nghỉ 500 ms, tức khoảng 1,5 giây sau thời điểm bắt đầu lượt trước.

Trong điều kiện luôn có đủ dữ liệu và thời gian xử lý tương đối ổn định, có thể ước tính:

```text
Thông lượng ≈ N / (N × t + D)
```

Trong đó `N` là số message thực sự xử lý trong mỗi lượt, `t` là thời gian trung bình cho một message và `D` là khoảng nghỉ; các thời gian dùng cùng đơn vị. Đây chỉ là mô hình cho một poller xử lý đồng bộ, chưa tính thời gian chờ nhận, lỗi, transaction hoặc cạnh tranh tài nguyên.

Các lưu ý quan trọng:

- Giá trị âm biểu thị không giới hạn số message trong một lượt; lượt có thể tiếp tục cho đến khi nguồn trả về `null`.
- Nếu nguồn luôn trả dữ liệu và số message không bị giới hạn, tác vụ có thể chạy rất lâu mà chưa đi đến khoảng nghỉ `fixed-delay`.
- Không dùng giá trị `0` để diễn đạt “không giới hạn”; giá trị này không cho lượt poll xử lý message.
- Mặc định có thể khác nhau theo loại endpoint. Nên đặt giới hạn tường minh khi hành vi gom nhiều message trong một lượt ảnh hưởng đến thiết kế.

### 8.2. receiveTimeout

Với polling consumer nhận từ `PollableChannel`, `receiveTimeout` là thời gian một lần gọi nhận có thể chờ message.

Giả sử:

```text
fixed-delay = 1.000 ms
receiveTimeout = 3.000 ms
maxMessagesPerPoll = 1
```

Khi channel rỗng, một lần nhận có thể chờ khoảng ba giây rồi trả về không có message. Sau khi tác vụ kết thúc mới áp dụng khoảng nghỉ một giây. Hai thời điểm bắt đầu lượt poll khi nhàn rỗi vì thế có thể cách nhau khoảng bốn giây.

Nếu message đến trong lúc `receive()` đang chờ, nó có thể được lấy ngay trong lần chờ đó; không nhất thiết phải đợi một lịch poll mới.

Không coi `receiveTimeout` là timeout tổng của handler. Nó cũng không tự đặt timeout cho việc supplier gọi một HTTP API hoặc truy vấn cơ sở dữ liệu. Các thao tác đó cần timeout riêng tại client hoặc adapter tương ứng.

### 8.3. initialDelay

`initialDelay` điều khiển thời gian chờ trước lượt đầu. `fixed-delay` điều khiển khoảng nghỉ giữa các lượt. Hai tham số phục vụ hai mục đích khác nhau.

Trì hoãn lượt đầu có thể hữu ích khi ứng dụng cần chờ một khoảng ngắn trước khi bắt đầu lấy dữ liệu. Tuy nhiên, đó không phải cơ chế xác nhận một hệ thống phụ thuộc đã sẵn sàng; nếu sự sẵn sàng là điều kiện bắt buộc, cần kiểm tra điều kiện đó rõ ràng.

### 8.4. Scheduler và executor

Scheduler quyết định khi nào tác vụ được kích hoạt. Khi poller chạy đồng bộ, việc gọi nguồn và xử lý đồng bộ downstream chiếm luồng thực thi tác vụ đó. Nhiều endpoint dùng chung scheduler có thể ảnh hưởng nhau nếu công việc kéo dài và tài nguyên lập lịch không đủ.

Nếu cấu hình `taskExecutor` cho poller, công việc có thể được chuyển sang executor:

```java
Pollers.fixedDelay(Duration.ofSeconds(1))
        .maxMessagesPerPoll(1)
        .taskExecutor(pollingExecutor);
```

`pollingExecutor` ở đây là một `TaskExecutor` do ứng dụng cung cấp, ví dụ một bean `ThreadPoolTaskExecutor` có giới hạn số luồng và sức chứa hàng đợi.

Trong cấu hình này, tác vụ do scheduler chạy có thể kết thúc sau khi giao việc cho executor. Khoảng nghỉ được đo theo sự hoàn tất của tác vụ lập lịch đó, nên lần giao việc sau có thể xảy ra khi công việc trước vẫn đang xử lý. Nếu executor cho phép, các công việc có thể chồng lấn.

Cần đánh giá đồng thời:

- Nguồn dữ liệu và handler có an toàn khi nhiều luồng cùng truy cập hay không.
- Thứ tự message có cần được duy trì hay không.
- Số luồng, dung lượng hàng đợi và chính sách từ chối của executor.
- Thông lượng producer có vượt khả năng tiêu thụ lâu dài hay không.

Tăng số luồng scheduler hoặc executor không tự tạo bảo đảm về thứ tự, giao dịch hay xử lý đúng một lần.

## 9. Chọn fixed-delay theo yêu cầu nghiệp vụ

### 9.1. Nguồn ít dữ liệu, chấp nhận độ trễ vài giây

Bắt đầu với một khoảng nghỉ tương đối dài và giới hạn nhỏ cho mỗi lượt. Mục tiêu là giảm số lần kiểm tra rỗng.

Ví dụ: `fixed-delay = 5 giây`, `maxMessagesPerPoll = 1` cho một nguồn trả kết quả nhanh. Nếu yêu cầu độ trễ thấp hơn, giảm delay sau khi đo chi phí truy cập nguồn.

### 9.2. Cần giải phóng hàng đợi tồn đọng

Có thể tăng `maxMessagesPerPoll` để lấy nhiều message mỗi lượt. Đổi lại, một lượt giữ tài nguyên lâu hơn, và tác động của lỗi hoặc transaction có thể lớn hơn tùy cấu hình.

Ví dụ: delay 200 ms, tối đa 50 message/lượt chỉ phù hợp khi nguồn và downstream chịu được lượng tải đó. Nếu nguồn không thể truy vấn theo lô, nhiều lần gọi `receive()` vẫn có thể tạo ra nhiều lần truy cập nguồn riêng biệt.

### 9.3. Dịch vụ ngoài giới hạn số request

Không dùng phép suy luận “delay một giây tương đương tối đa một request mỗi giây” nếu:

- Một lượt poll xử lý nhiều message.
- Một message làm phát sinh nhiều request.
- Có retry.
- Có nhiều poller hoặc nhiều instance ứng dụng.
- Có xử lý bất đồng bộ hoặc công việc đang chờ trong executor.

Nếu cần giới hạn request dùng chung giữa các instance, phải thiết kế cơ chế điều tiết ở phạm vi tương ứng. `fixed-delay` của từng endpoint chỉ là một phần của cấu hình tải.

## 10. Lỗi, retry và transaction

### 10.1. fixed-delay không phải chính sách retry

Khi handler ném exception, cơ chế xử lý lỗi của endpoint/poller quyết định cách lỗi được chuyển tiếp hoặc ghi nhận. Luồng polling thường sử dụng cơ chế `ErrorHandler` và có thể đưa lỗi tới error channel theo cấu hình.

Khoảng nghỉ không tự bảo đảm message thất bại sẽ được lấy lại. Với `QueueChannel` trong bộ nhớ, message đã được lấy ra không mặc nhiên được khôi phục khi handler thất bại.

Nếu cần retry, hãy cấu hình retry/advice thích hợp và xác định giới hạn số lần thử. Khi retry chạy đồng bộ trong tác vụ poll, thời gian retry và các khoảng chờ của nó làm tăng thời gian tác vụ; khoảng nghỉ `fixed-delay` được áp dụng sau khi tác vụ kết thúc.

### 10.2. Transaction cần tài nguyên tham gia phù hợp

Cấu hình transaction cho poller có thể tạo ranh giới giao dịch quanh công việc polling. Hiệu lực rollback phụ thuộc tài nguyên, transaction manager và cách các thành phần tham gia giao dịch.

Không suy ra rằng mọi thao tác được gọi từ poller đều có thể rollback. Ví dụ, một HTTP request đã được hệ thống ngoài chấp nhận không tự bị hoàn tác chỉ vì transaction cục bộ thất bại.

Với xử lý đơn hàng, nên xác định riêng:

1. Khi nào dữ liệu được coi là đã lấy thành công khỏi nguồn.
2. Khi nào tác động nghiệp vụ được ghi nhận.
3. Khi nào message được xác nhận hoặc có thể được phát lại.
4. Cách handler nhận biết một đơn hàng đã xử lý để hạn chế tác động trùng lặp.

`fixed-delay` giải quyết nhịp kích hoạt; các bảo đảm về độ tin cậy cần thiết kế bổ sung.

## 11. Quan sát và kiểm thử hành vi

### 11.1. Quan sát đúng các mốc

Để kiểm tra cấu hình, ghi nhận tối thiểu thời điểm bắt đầu và kết thúc của mỗi lượt, số message đã lấy, thời gian xử lý và tên luồng. Log chỉ ghi lúc handler nhận message chưa đủ để suy ra thời gian của một lượt có nhiều message hoặc nhiều lần nhận rỗng.

Các số liệu hữu ích gồm:

| Số liệu | Giúp trả lời |
|---|---|
| Thời gian thực thi mỗi lượt | Nguồn hay downstream đang làm lượt poll kéo dài? |
| Số lượt không có dữ liệu | Có đang kiểm tra nguồn quá thường xuyên? |
| Số message mỗi lượt | Giới hạn đã đặt có được sử dụng hết không? |
| Độ dài hàng đợi và tuổi message | Tốc độ tiêu thụ có theo kịp đầu vào không? |
| Số lỗi và số lần thử lại | Lỗi có làm giảm thông lượng hoặc tăng tải không? |
| Số công việc chờ trong executor | Công việc bất đồng bộ có đang tích tụ không? |

### 11.2. Những tình huống kiểm thử nên có

| Tình huống | Kỳ vọng cần xác minh |
|---|---|
| Một nguồn trả về ba message, giới hạn một message/lượt | Mỗi lượt chỉ lấy tối đa một message |
| Channel rỗng và `receiveTimeout = 0` | Lần kiểm tra trả về nhanh và không gọi handler |
| Channel rỗng và có timeout nhận | Thời gian chờ nhận được tính vào tác vụ poll đồng bộ |
| Handler đồng bộ xử lý lâu | Lượt tiếp theo bắt đầu sau khi lượt trước kết thúc cộng khoảng nghỉ |
| Giới hạn nhiều message/lượt | Các message có thể được xử lý liên tiếp trong một lượt |
| Handler ném lỗi | Cơ chế nhận lỗi hoạt động và số phận message đúng với thiết kế |
| Có executor riêng | Kiểm tra khả năng chồng lấn và thứ tự xử lý |

Với kiểm thử tích hợp có thời gian thực, dùng công cụ chờ có timeout, latch hoặc cơ chế đồng bộ phù hợp. Tránh khẳng định một lần chạy phải đúng tuyệt đối một mốc mili giây, vì môi trường CI có thể bận.

Nếu đo khoảng nghỉ, so sánh thời điểm **bắt đầu lượt sau** với **kết thúc lượt trước**. Chỉ so sánh hai thời điểm bắt đầu sẽ trộn thời gian xử lý với `fixed-delay`. Nên dùng đồng hồ đơn điệu như `System.nanoTime()` để đo khoảng thời gian.

Kiểm thử nghiệp vụ của transformer, filter, router hoặc handler có thể thực hiện riêng với message đầu vào xác định. Chỉ dùng kiểm thử có scheduler cho hành vi thật sự phụ thuộc lịch để giữ bộ kiểm thử nhanh và dễ chẩn đoán.

## 12. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| “Delay hai giây nghĩa là hai giây có một message” | Khoảng nghỉ nằm giữa các lượt; một lượt có thể có nhiều message hoặc không có message |
| “Handler mất ba giây, delay một giây nên mỗi giây vẫn lấy một lần” | Với xử lý đồng bộ và một message/lượt, hai lần bắt đầu cách nhau khoảng bốn giây |
| “Cứ đặt delay là tránh được xử lý đồng thời” | Executor, ranh giới bất đồng bộ và nhiều instance có thể tạo xử lý đồng thời |
| “Delay là timeout xử lý” | Delay chỉ quyết định khoảng nghỉ, không hủy handler chạy lâu |
| “Giảm delay luôn tăng thông lượng” | Nguồn hoặc downstream có thể là nút thắt; giảm delay có thể chỉ tăng số lần kiểm tra rỗng |
| “Một lượt có giới hạn âm sẽ luôn kết thúc nhanh” | Nguồn luôn có dữ liệu có thể giữ lượt chạy kéo dài |
| “Lỗi sẽ tự đưa message trở lại QueueChannel” | Việc phục hồi phụ thuộc loại nguồn, transaction và cơ chế xử lý lỗi |

## 13. Bài tập áp dụng

Thiết kế một luồng có `QueueChannel`, một transformer chuẩn hóa mã đơn hàng và một handler ghi kết quả vào danh sách an toàn luồng.

1. Cấu hình poller nghỉ 500 ms, lấy tối đa hai message mỗi lượt và không chờ nhận khi channel rỗng.
2. Gửi năm message vào channel trước khi bắt đầu quan sát.
3. Ghi lại các lượt có dữ liệu. Khi chỉ có một consumer và không có lỗi, ít nhất ba lượt có dữ liệu cần thiết để xử lý hết năm message.
4. Cho mỗi lần xử lý đồng bộ mất khoảng 200 ms. Dự đoán một lượt đủ hai message mất khoảng 400 ms và hai thời điểm bắt đầu liên tiếp cách nhau khoảng 900 ms, chưa tính chi phí khác.
5. Giảm giới hạn xuống một message/lượt rồi so sánh độ trễ của message cuối cùng.
6. Thêm một ranh giới bất đồng bộ và quan sát vì sao thời điểm tác vụ poll kết thúc không còn đồng nghĩa mọi xử lý nghiệp vụ đã hoàn tất.

Sau bài tập, người học cần giải thích được ba yếu tố riêng biệt: khoảng nghỉ giữa các lượt, khối lượng công việc trong mỗi lượt và phạm vi xử lý đồng bộ. Ba yếu tố này quyết định cách `fixed-delay` ảnh hưởng đến độ trễ, thông lượng và tải của một luồng Spring Integration.
