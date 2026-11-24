# Cấu hình fixedDelay, initialDelay, cron và maxMessagesPerPoll

Trong Spring Cloud Stream, `Supplier<T>` là nguồn phát dữ liệu. Khác với `Function` và `Consumer` được gọi khi có message đầu vào, một supplier không có destination đầu vào để kích hoạt. Framework cần một cơ chế khác để gọi phương thức `get()` và lấy dữ liệu gửi tới binding đầu ra. Cơ chế mặc định là **poller**: bộ lập lịch gọi supplier theo chu kỳ, sau đó chuyển kết quả thành message và gửi qua binder tới Kafka, RabbitMQ hoặc Pulsar.

Poller cho phép điều khiển thời điểm bắt đầu, khoảng cách giữa các lần gọi, lịch chạy theo cron và số message tối đa trong một lần poll. Cấu hình phù hợp giúp nguồn phát dữ liệu đúng nhịp, tránh truy vấn nguồn quá dày, giới hạn tải và kiểm soát lượng dữ liệu được đưa vào broker.

## 1. Supplier và poller hoạt động như thế nào?

Một supplier đơn giản có thể được khai báo như sau:

```java
import java.time.Instant;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OrderEventSource {

    @Bean
    Supplier<OrderSnapshot> orderSnapshot(OrderService orderService) {
        return () -> orderService.nextSnapshot()
            .orElse(null);
    }
}

record OrderSnapshot(String orderId, Instant capturedAt) {}
```

Supplier trả về một `OrderSnapshot` mỗi khi được gọi. Spring Cloud Stream thiết lập binding đầu ra `orderSnapshot-out-0`. Poller mặc định gọi supplier mỗi giây; nếu supplier trả về dữ liệu, framework chuyển kết quả thành message và gửi tới destination đã cấu hình. Nếu nguồn chưa có dữ liệu và trả `null`, không có message payload để phát ở lần gọi đó.

```yaml
spring:
  cloud:
    function:
      definition: orderSnapshot
    stream:
      bindings:
        orderSnapshot-out-0:
          destination: orders.snapshots
          content-type: application/json
```

Poller là cơ chế kích hoạt phía ứng dụng cho supplier. Nó không phải cấu hình consumer polling của Kafka, RabbitMQ hoặc Pulsar, cũng không phải lịch chạy của một `@Scheduled` method do ứng dụng tự viết. Khi supplier được kích hoạt, binder vẫn chịu trách nhiệm gửi message tới broker.

## 2. Bốn thuộc tính cần hiểu

| Thuộc tính | Ý nghĩa | Giá trị mặc định trong default poller |
|---|---|---|
| `fixedDelay` | Khoảng chờ giữa các lần poll định kỳ, tính bằng đơn vị thời gian được cấu hình. | 1000 ms |
| `initialDelay` | Thời gian chờ trước lần poll đầu tiên của lịch định kỳ. | 0 |
| `cron` | Biểu thức lịch xác định những thời điểm poller được kích hoạt. | Không cấu hình |
| `maxMessagesPerPoll` | Số message tối đa mà một sự kiện poll có thể lấy/phát. | 1 |

Trong cấu hình YAML, Spring Boot sử dụng dạng kebab-case: `fixed-delay`, `initial-delay`, `max-messages-per-poll`, `time-unit`. Tên thuộc tính Java trong tài liệu API thường được viết camelCase; hai cách viết ánh xạ tới cùng một cấu hình.

Với cấu hình Spring Cloud Stream hiện hành, các thuộc tính default poller được expose dưới prefix `spring.integration.poller`. Những phiên bản Spring Cloud Stream cũ từng dùng `spring.cloud.stream.poller`; prefix cũ đã bị deprecated từ Spring Cloud Stream 3.2. Khi nâng cấp ứng dụng, cần kiểm tra phiên bản Spring Cloud Stream/Spring Boot và dùng prefix tương ứng, tránh trộn cấu hình cũ với cấu hình mới.

## 3. fixedDelay: khoảng chờ giữa các lần gọi

`fixedDelay` quy định khoảng thời gian poller chờ sau khi một lần poll hoàn tất trước khi bắt đầu lần tiếp theo. Với default poller, giá trị mặc định là 1000 mili giây, tương đương một giây.

Ví dụ, đặt chu kỳ chờ là 5 giây:

```yaml
spring:
  integration:
    poller:
      fixed-delay: 5000
      time-unit: MILLISECONDS
```

Nếu một lần gọi supplier và gửi message mất 400 mili giây, lần poll tiếp theo sẽ bắt đầu sau khoảng 5 giây kể từ khi lần trước hoàn tất. Thời gian giữa hai lần bắt đầu vì thế xấp xỉ 5,4 giây trong ví dụ này, chưa tính biến động do scheduler và tải hệ thống.

Có thể đổi đơn vị để cấu hình dễ đọc hơn:

```yaml
spring:
  integration:
    poller:
      fixed-delay: 5
      time-unit: SECONDS
```

Không nên đặt `fixedDelay` quá nhỏ nếu supplier truy vấn database, gọi API ngoài hoặc thực hiện công việc tốn tài nguyên. Một chu kỳ ngắn có thể làm nguồn dữ liệu bị truy vấn liên tục, tăng tải database và tạo message nhanh hơn khả năng xử lý của consumer.

## 4. initialDelay: trì hoãn lần poll đầu tiên

`initialDelay` xác định thời gian chờ từ lúc poller được khởi động tới lần poll định kỳ đầu tiên. Giá trị mặc định là 0, nghĩa là poller có thể bắt đầu ngay khi lịch được kích hoạt.

Ví dụ, đợi 10 giây sau khi ứng dụng khởi động rồi mới bắt đầu poll; các lần tiếp theo cách nhau 5 giây:

```yaml
spring:
  integration:
    poller:
      initial-delay: 10000
      fixed-delay: 5000
      time-unit: MILLISECONDS
```

`initialDelay` hữu ích khi ứng dụng cần thời gian hoàn tất khởi tạo, chờ kết nối database, nạp cache hoặc chờ một dịch vụ phụ thuộc sẵn sàng. Nó không thay thế readiness check và không bảo đảm các phụ thuộc đã hoạt động; nếu cần điều kiện sẵn sàng thực sự, ứng dụng vẫn phải kiểm tra kết nối và xử lý lỗi phù hợp.

`initialDelay` áp dụng cho lịch định kỳ dùng delay/rate. Khi sử dụng `cron`, lịch được xác định bởi các mốc thời gian của biểu thức cron; không nên kỳ vọng `initialDelay` sẽ dịch chuyển các mốc cron.

## 5. cron: chạy theo lịch thời gian

`cron` dùng biểu thức cron để xác định các thời điểm poller được gọi. Cách này phù hợp với nguồn dữ liệu cần chạy vào những mốc cố định, chẳng hạn đầu mỗi giờ, mỗi 15 phút hoặc vào một khung giờ nhất định.

Spring sử dụng biểu thức cron sáu trường, gồm giây, phút, giờ, ngày trong tháng, tháng và ngày trong tuần. Ví dụ:

| Biểu thức | Lịch chạy |
|---|---|
| `0 * * * * *` | Mỗi phút, tại giây 0. |
| `0 */5 * * * *` | Mỗi 5 phút, tại giây 0. |
| `0 0 * * * *` | Mỗi giờ, tại phút 0 và giây 0. |
| `0 30 2 * * *` | Hằng ngày lúc 02:30:00. |
| `0 0 9 * * MON-FRI` | Các ngày trong tuần lúc 09:00:00. |

Ví dụ cấu hình poller chạy mỗi 15 phút:

```yaml
spring:
  integration:
    poller:
      cron: "0 */15 * * * *"
      max-messages-per-poll: 10
```

Khi dùng cron, không cấu hình đồng thời `fixed-delay` cho cùng một poller. Hai thuộc tính đại diện hai cách lập lịch khác nhau: fixed delay tính khoảng chờ sau lần poll trước, còn cron xác định các mốc trên lịch. `initialDelay` không được dùng để dịch các mốc cron.

Cron phù hợp khi nghiệp vụ gắn với thời điểm lịch, ví dụ tổng hợp dữ liệu cuối mỗi giờ hoặc phát báo cáo đầu ngày. Nếu chỉ cần chạy lại sau một khoảng chờ kể từ khi lần trước kết thúc, `fixedDelay` dễ dự đoán hơn.

## 6. maxMessagesPerPoll: giới hạn số message trong một lần poll

`maxMessagesPerPoll` quy định số message tối đa được lấy/phát trong một sự kiện poll. Mặc định là 1. Với supplier kiểu imperative, một lần gọi `get()` thường tạo một message; nếu đặt giới hạn lớn hơn 1, poller có thể gọi supplier nhiều lần trong cùng một đợt poll để lấy thêm message, cho tới khi đạt giới hạn hoặc nguồn không còn dữ liệu.

Ví dụ:

```yaml
spring:
  integration:
    poller:
      fixed-delay: 2000
      max-messages-per-poll: 20
```

Với cấu hình trên, poller chờ 2 giây giữa các đợt poll và có thể lấy tối đa 20 message trong một đợt. Nếu supplier chỉ có 3 bản ghi chờ phát, đợt poll có thể kết thúc sau khi lấy hết 3 bản ghi; giới hạn 20 không có nghĩa ứng dụng luôn phải tạo đủ 20 message.

`maxMessagesPerPoll` không đồng nghĩa với kích thước batch trong một payload. Nó giới hạn số message nguồn được xử lý trong một lần poll. Nếu ứng dụng muốn gửi một message chứa danh sách nhiều bản ghi, đó là quyết định về kiểu payload và cách serialize riêng.

Tăng giới hạn có thể tăng throughput và giảm chi phí kích hoạt poller, nhưng cũng có thể tạo burst message, tăng áp lực lên broker và consumer, kéo dài một đợt poll và làm các công việc khác chờ lâu hơn. Chọn giá trị theo tốc độ nguồn dữ liệu, khả năng gửi của producer, dung lượng broker và năng lực xử lý downstream.

## 7. Cấu hình default poller

Các thuộc tính dưới `spring.integration.poller` tạo cấu hình default poller dùng chung cho các binding cần polling. Ví dụ đầy đủ:

```yaml
spring:
  cloud:
    function:
      definition: orderSnapshot
    stream:
      bindings:
        orderSnapshot-out-0:
          destination: orders.snapshots
          content-type: application/json
  integration:
    poller:
      fixed-delay: 3000
      initial-delay: 5000
      max-messages-per-poll: 5
      time-unit: MILLISECONDS
```

Ứng dụng bắt đầu poll sau khoảng 5 giây, sau đó chờ 3 giây kể từ khi mỗi lần poll hoàn tất trước khi bắt đầu lần tiếp theo. Mỗi đợt có thể phát tối đa 5 message. Default poller thuận tiện khi ứng dụng chỉ có một nguồn poll hoặc nhiều nguồn có cùng lịch.

Nếu nhiều supplier trong cùng ứng dụng cần lịch khác nhau, cấu hình global có thể không đủ. Khi đó, cân nhắc cấu hình poller riêng cho từng output binding.

## 8. Cấu hình poller riêng cho từng binding

Spring Cloud Stream hỗ trợ cấu hình poller theo output binding. Ví dụ, ứng dụng có hai supplier: một nguồn phát snapshot mỗi 5 giây và một nguồn phát báo cáo mỗi giờ. Có thể đặt lịch riêng cho từng binding thay vì buộc cả hai dùng chung default poller.

Ví dụ cấu hình riêng cho `orderSnapshot-out-0` và `dailyReport-out-0`:

```yaml
spring:
  cloud:
    function:
      definition: orderSnapshot;dailyReport
    stream:
      bindings:
        orderSnapshot-out-0:
          destination: orders.snapshots
          producer:
            poller:
              fixed-delay: 5000
              initial-delay: 1000
              max-messages-per-poll: 10
        dailyReport-out-0:
          destination: reports.daily
          producer:
            poller:
              cron: "0 0 2 * * *"
```

Đường dẫn cấu hình riêng có dạng `spring.cloud.stream.bindings.<binding>.producer.poller.*`. Cấu hình per-binding hữu ích khi mỗi nguồn có nhịp phát khác nhau. Hãy kiểm tra thuộc tính được hỗ trợ bởi phiên bản Spring Cloud Stream đang dùng; tránh giả định mọi phiên bản binder đều hỗ trợ mọi tùy chọn poller giống nhau.

## 9. fixedDelay và cron: chọn theo yêu cầu nghiệp vụ

| Nhu cầu | Cách cấu hình phù hợp | Lý do |
|---|---|---|
| Đọc nguồn định kỳ, đợi một khoảng sau khi lần trước hoàn tất | `fixed-delay` | Chu kỳ không bị chồng lấn do thời gian xử lý thay đổi. |
| Chạy đúng các mốc giờ cố định | `cron` | Lịch gắn với thời gian trên đồng hồ. |
| Chờ ứng dụng khởi động ổn định rồi mới chạy | `initial-delay` kết hợp fixed delay | Trì hoãn lần poll đầu. |
| Lấy nhiều bản ghi mỗi đợt từ nguồn có backlog | `max-messages-per-poll` lớn hơn 1 | Tăng lượng message tối đa trong một đợt. |
| Mỗi supplier cần nhịp khác nhau | Per-binding poller | Tránh áp dụng một lịch toàn cục cho các nguồn khác nhau. |

Ví dụ, một nguồn kiểm tra outbox có thể chạy fixed delay ngắn vì cần phát sự kiện tương đối nhanh. Nguồn tổng hợp báo cáo cuối ngày nên dùng cron để chạy tại thời điểm đã định. Nguồn nhập dữ liệu lịch sử có thể tăng `max-messages-per-poll` trong một giai đoạn backfill rồi giảm lại sau khi bắt kịp.

## 10. Supplier trả về dữ liệu reactive

Không phải mọi supplier đều được poll theo cùng cách. Supplier imperative như `Supplier<OrderEvent>` thường được poll định kỳ và mỗi lần gọi tạo một kết quả. Supplier reactive như `Supplier<Flux<OrderEvent>>` có thể đại diện cho một luồng liên tục; trong trường hợp đó, framework thường gọi supplier một lần để lấy publisher, thay vì gọi lại mỗi chu kỳ.

Nếu cần poll nguồn dữ liệu định kỳ nhưng muốn supplier trả về một `Flux` hữu hạn cho mỗi lần truy vấn, có thể dùng `@PollableBean` để báo cho framework rằng supplier reactive này vẫn cần được poll:

```java
import java.util.function.Supplier;

import org.springframework.cloud.function.context.PollableBean;
import reactor.core.publisher.Flux;

@PollableBean
Supplier<Flux<OrderEvent>> pendingOrderEvents(OrderService orderService) {
    return () -> Flux.fromIterable(orderService.findPendingEvents());
}
```

Với `@PollableBean`, framework có thể poll supplier reactive hữu hạn theo lịch và tách từng phần tử thành message riêng theo cấu hình `splittable` mặc định. Nếu muốn giữ toàn bộ `Flux` như một kết quả thay vì tách phần tử, cần xem xét thuộc tính `splittable` và hợp đồng payload. Không nên dùng poller định kỳ cho một `Flux` vô hạn vốn đã tự phát dữ liệu liên tục; điều đó có thể tạo nhiều subscription không mong muốn.

## 11. Lưu ý về xử lý nguồn và tính an toàn khi phát lặp

Poller gọi supplier theo lịch, nhưng không tự bảo đảm bản ghi nguồn chỉ được phát đúng một lần. Nếu supplier truy vấn database để lấy các bản ghi chờ gửi, ứng dụng cần có cơ chế đánh dấu hoặc claim bản ghi một cách an toàn.

Ví dụ, nếu supplier đọc 10 bản ghi pending nhưng không đánh dấu chúng đã được xử lý, lần poll tiếp theo có thể phát lại cùng dữ liệu. Nếu ứng dụng đánh dấu đã gửi trước khi publish thành công, lỗi broker có thể làm mất sự kiện. Các mẫu như transactional outbox, trạng thái `NEW/IN_PROGRESS/SENT`, khóa claim, lease và idempotency giúp quản lý ranh giới này.

Khi `max-messages-per-poll` lớn hơn 1, cần bảo đảm mỗi lần gọi supplier lấy phần dữ liệu tiếp theo thay vì luôn trả cùng một bản ghi. Việc claim dữ liệu phải an toàn khi ứng dụng có nhiều instance hoặc khi một instance khởi động lại giữa đợt poll.

Poller cũng không thay thế retry và error handling. Nếu supplier ném exception, lần poll có thể thất bại và được ghi nhận theo cơ chế của Spring Integration/Spring Cloud Stream. Cần xác định cách xử lý lỗi nguồn, lỗi gửi broker và khả năng thử lại; không giả định một lần poll lỗi sẽ tự động bảo đảm mọi bản ghi được phát sau đó.

## 12. Những lỗi cấu hình thường gặp

1. **Dùng nhầm prefix phiên bản cũ.** Cấu hình `spring.cloud.stream.poller` ở phiên bản mới có thể không còn được bind như mong đợi; kiểm tra phiên bản và dùng `spring.integration.poller` khi phù hợp.
2. **Cấu hình đồng thời fixed delay và cron.** Đây là hai trigger khác nhau; chọn một cơ chế cho mỗi poller.
3. **Nghĩ initialDelay dịch lịch cron.** Initial delay dành cho periodic trigger; cron vẫn chạy theo các mốc thời gian của biểu thức.
4. **Đặt maxMessagesPerPoll quá cao.** Một đợt poll có thể tạo burst lớn, làm tăng áp lực lên broker và consumer.
5. **Cho rằng poller điều khiển consumer broker.** Poller ở đây kích hoạt supplier; consumer nhận message theo cơ chế của binder/broker.
6. **Dùng poller cho supplier reactive liên tục.** Một supplier trả `Flux` vô hạn thường chỉ cần được gọi một lần; dùng `@PollableBean` cho trường hợp Flux hữu hạn cần polling.
7. **Không đánh dấu dữ liệu nguồn sau khi phát.** Supplier có thể phát lại bản ghi ở lần poll sau hoặc bỏ sót bản ghi nếu cập nhật trạng thái sai thời điểm.
8. **Cấu hình lịch không tính thời gian xử lý.** Với fixed delay, khoảng chờ bắt đầu sau khi poll trước hoàn tất; chu kỳ bắt đầu-thực tế dài hơn thời gian cấu hình nếu xử lý tốn thời gian.

## 13. Kiểm thử và quan sát poller

Nên kiểm thử hành vi thời gian và số lượng message ở cấp ứng dụng:

| Trường hợp | Điều cần xác minh |
|---|---|
| fixed delay | Thời gian giữa các lần poll phù hợp với khoảng chờ sau khi lần trước hoàn tất. |
| initial delay | Không phát trước khi hết thời gian chờ ban đầu. |
| cron | Poller chỉ chạy tại các mốc được biểu thức chỉ định. |
| max messages | Một đợt không vượt giới hạn đã cấu hình và dừng khi nguồn hết dữ liệu. |
| Per-binding poller | Hai supplier có thể chạy theo lịch độc lập. |
| Supplier lỗi | Exception được quan sát và nguồn có thể phục hồi theo chính sách đã thiết kế. |
| Nhiều instance | Không phát trùng ngoài ý muốn khi cùng truy cập một nguồn dữ liệu. |

Không nên dùng `Thread.sleep()` dài trong unit test để chờ lịch chạy. Có thể kiểm thử logic supplier riêng, kiểm thử binding bằng Spring Cloud Stream Test Binder và dùng scheduler/clock có thể kiểm soát nếu kiến trúc cho phép. Kiểm thử tích hợp nên xác minh message thực sự được gửi tới binder và đo thời điểm phát trong một khoảng sai số hợp lý.

Các chỉ số nên theo dõi gồm số lần poll, thời gian thực thi supplier, số message tạo ra mỗi đợt, số đợt không có dữ liệu, lỗi truy vấn nguồn, lỗi publish và độ trễ từ lúc dữ liệu sẵn sàng tới lúc message được gửi. Nếu backlog tăng liên tục, cần xem xét tăng giới hạn hoặc tần suất poll, đồng thời xác nhận broker và consumer đủ năng lực nhận tải.

## 14. Quy trình chọn cấu hình

Trước khi đặt poller cho một supplier, hãy trả lời:

1. Nguồn dữ liệu cần phát theo chu kỳ tương đối hay tại mốc thời gian cố định?
2. Có cần chờ một khoảng sau khi ứng dụng khởi động không?
3. Một lần gọi supplier mất bao lâu và có thể phát sinh tải lên database/API nào?
4. Mỗi đợt cần phát tối đa bao nhiêu message để vừa đạt throughput vừa tránh burst?
5. Nguồn có nhiều instance cùng truy cập không, và dữ liệu được claim/đánh dấu thế nào?
6. Supplier là imperative, reactive liên tục hay reactive hữu hạn cần polling?
7. Ứng dụng dùng default poller hay cần cấu hình riêng cho từng output binding?
8. Có metric và cảnh báo để nhận biết poller chậm, nguồn lỗi hoặc backlog tăng không?

Với nguồn cần chạy đều sau mỗi lần xử lý, bắt đầu bằng `fixed-delay` vừa phải và `max-messages-per-poll` nhỏ. Dùng `initial-delay` khi cần thời gian khởi động. Chọn `cron` khi nghiệp vụ yêu cầu lịch cố định theo đồng hồ. Chỉ tăng giới hạn message khi nguồn, broker và consumer có đủ năng lực. Cấu hình poller tốt phải phù hợp với tốc độ dữ liệu thực tế và cơ chế quản lý trạng thái nguồn, để việc phát message ổn định qua cả lúc tải cao lẫn khi ứng dụng gặp lỗi.

## Tài liệu tham khảo

- [Spring Cloud Stream Reference – Producing and Consuming Messages, Polling Configuration Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
