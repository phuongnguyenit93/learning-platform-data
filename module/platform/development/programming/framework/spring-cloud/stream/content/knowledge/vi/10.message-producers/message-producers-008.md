# Xử lý nguồn không có dữ liệu và lỗi phát sinh khi lấy dữ liệu

Trong Spring Cloud Stream, một nguồn phát có thể được gọi theo chu kỳ để lấy dữ liệu từ API, cơ sở dữ liệu, hệ thống tệp hoặc một dịch vụ bên ngoài. Không phải lần gọi nào cũng có dữ liệu mới. Nguồn cũng có thể tạm thời không truy cập được, trả về dữ liệu không hợp lệ hoặc gặp lỗi cấu hình.

Thiết kế Supplier tốt cần phân biệt rõ ba tình huống: không có dữ liệu mới, có dữ liệu hợp lệ và không thể lấy dữ liệu do lỗi. Không có dữ liệu thường là trạng thái bình thường của một lần polling; lỗi nguồn cần được quan sát, phân loại và xử lý theo chính sách retry hoặc phục hồi. Nếu gộp hai trường hợp này, ứng dụng có thể âm thầm bỏ qua sự cố hoặc phát ra các event không có ý nghĩa nghiệp vụ.

## 1. Hiểu vòng đời của một nguồn Supplier

Spring Cloud Stream hỗ trợ mô hình hàm Supplier, Function và Consumer. Supplier là nguồn không có input binding; framework gọi hàm Supplier theo poller và chuyển giá trị trả về tới output binding.

~~~text
Poller
  |
  | gọi Supplier.get()
  v
Supplier đọc nguồn dữ liệu
  |
  +---- Không có dữ liệu mới ----> Không phát message
  |
  +---- Có dữ liệu hợp lệ -------> Tạo payload/message
  |                                  |
  |                                  v
  |                              Output binding
  |                                  |
  |                                  v
  |                               Binder
  |                                  |
  |                                  v
  |                               Broker
  |
  +---- Nguồn gặp lỗi -----------> Error handling / retry / alert
~~~

Ví dụ, một Supplier có thể kiểm tra API đối tác mỗi vài giây để lấy trạng thái đơn hàng mới. Có lúc API trả về một đơn hàng, có lúc không có thay đổi, và có lúc API timeout. Ba kết quả này cần được xử lý khác nhau.

Supplier đồng bộ thường trả về một giá trị mỗi lần được gọi. Khi không có message để phát, Supplier có thể trả về null; poller sẽ không tạo message đầu ra cho lần gọi đó. Nếu nguồn nội bộ của ứng dụng trả về Optional<T>, có thể dùng Optional để biểu diễn kết quả tìm kiếm rồi chuyển trường hợp rỗng thành null tại ranh giới Supplier.

Không nên phát một object rỗng chỉ để thay thế cho kết quả không có dữ liệu. Một payload rỗng vẫn là message và có thể khiến consumer hiểu nhầm rằng một sự kiện nghiệp vụ đã xảy ra.

## 2. Phân biệt không có dữ liệu với một sự kiện có kết quả rỗng

Không có dữ liệu mới và một sự kiện báo kết quả rỗng có ý nghĩa khác nhau.

| Tình huống | Ý nghĩa | Hành động |
|---|---|---|
| Không có bản ghi mới trong lần polling | Nguồn hiện không có gì cần phát | Không phát message |
| Truy vấn nghiệp vụ hoàn tất với 0 kết quả | Một hoạt động đã hoàn tất và kết quả là rỗng | Phát event rõ nghĩa nếu consumer cần biết kết quả |
| Nguồn timeout hoặc mất kết nối | Không xác định được nguồn có dữ liệu hay không | Báo lỗi, retry hoặc mở circuit |
| Nguồn trả dữ liệu sai schema | Có dữ liệu nhưng không thể diễn giải an toàn | Cách ly bản ghi, ghi lỗi và cảnh báo |
| Nguồn trả lại bản ghi đã phát | Dữ liệu có thể bị giao lặp | Dùng event ID và idempotency để chống trùng |

Ví dụ, một Supplier kiểm tra các đơn hàng cần đồng bộ. Nếu không có đơn hàng mới, nó không cần phát event OrderCreated với orderId rỗng. Nếu một báo cáo tìm kiếm hoàn tất và không tìm thấy đơn hàng nào, hệ thống có thể phát SearchCompleted với resultCount bằng 0, vì đó là một kết quả nghiệp vụ có ý nghĩa.

Không dùng null, danh sách rỗng, chuỗi rỗng và exception thay thế tùy tiện cho nhau. Hãy định nghĩa ý nghĩa từng trường hợp ngay tại adapter đọc nguồn.

## 3. Viết Supplier khi nguồn không có dữ liệu

Giả sử một client trả về Optional<OrderSnapshot> khi kiểm tra nguồn:

Đây là ba file Java riêng được đặt cạnh nhau để minh họa hợp đồng giữa client và kiểu dữ liệu:

~~~java
import java.util.Optional;

public interface OrderSourceClient {
    Optional<OrderSnapshot> fetchNext();
}

public record OrderSnapshot(
    String orderId,
    String customerId,
    long total
) {}

public record OrderCreated(
    String orderId,
    String customerId,
    long total
) {}
~~~

Supplier chuyển kết quả có dữ liệu thành event, còn kết quả rỗng thì không phát message:

~~~java
import java.util.Optional;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderSourceConfiguration {

    @Bean
    Supplier<OrderCreated> orderSource(OrderSourceClient client) {
        return () -> client.fetchNext()
            .map(snapshot -> new OrderCreated(
                snapshot.orderId(),
                snapshot.customerId(),
                snapshot.total()
            ))
            .orElse(null);
    }
}
~~~

Nếu client không có dữ liệu, Optional rỗng được chuyển thành null. Poller không phát message cho lần gọi đó. Khi có dữ liệu, Supplier tạo một payload OrderCreated và output binding mặc định có tên orderSource-out-0.

Optional là kiểu trả về nội bộ của client trong ví dụ này. Không nên mặc định rằng Supplier<Optional<OrderCreated>> sẽ tự động bỏ qua Optional.empty(); khi dùng kiểu đó, Optional có thể trở thành payload message tùy cấu hình conversion. Chuyển kết quả rỗng thành hành vi không phát message một cách rõ ràng tại Supplier.

Không dùng giá trị mặc định giả như orderId = "UNKNOWN", total = 0 hoặc một event rỗng để che giấu nguồn không có dữ liệu. Nếu giá trị 0 là dữ liệu nghiệp vụ hợp lệ, nó phải được phân biệt với việc không có bản ghi.

## 4. Cấu hình poller và output binding

Một Supplier được kích hoạt bởi poller. Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    function:
      definition: orderSource

    stream:
      bindings:
        orderSource-out-0:
          destination: orders.created
          content-type: application/json

  integration:
    poller:
      fixed-delay: 2000
      initial-delay: 1000
~~~

Trong ví dụ:

- orderSource là tên bean Supplier được kích hoạt.
- orderSource-out-0 là output binding do framework tạo từ tên bean.
- orders.created là destination trên broker.
- content-type khai báo kiểu nội dung của payload.
- fixed-delay đặt khoảng chờ giữa các lần polling theo cấu hình Spring Integration.
- initial-delay đặt thời gian chờ trước lần polling đầu tiên.

Điều chỉnh chu kỳ polling theo giới hạn API, tốc độ cập nhật dữ liệu và khả năng xử lý của broker. Poll quá nhanh khi nguồn thường xuyên rỗng sẽ tạo tải không cần thiết. Poll quá chậm làm tăng độ trễ phát hiện dữ liệu mới.

Đặt timeout cho lời gọi nguồn nhỏ hơn hoặc phù hợp với chu kỳ polling và thời gian xử lý tối đa. Nếu một lần gọi kéo dài quá lâu, poller có thể bị chiếm dụng và dữ liệu mới bị phát hiện chậm. Không dùng vòng lặp vô hạn hoặc Thread.sleep bên trong Supplier để tự điều khiển chu kỳ; hãy dùng poller hoặc cơ chế scheduling phù hợp.

Nếu ứng dụng có nhiều instance, mỗi instance có thể cùng gọi nguồn. Với nguồn không hỗ trợ đọc song song, cần cơ chế phân phối công việc, lease, lock hoặc phân vùng để tránh nhiều instance lấy cùng một bản ghi ngoài ý muốn.

## 5. Phân loại lỗi khi lấy dữ liệu

Không phải mọi lỗi nguồn đều có cùng cách phục hồi. Trước khi thêm retry, hãy phân loại lỗi:

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Timeout, kết nối bị reset, broker/API quá tải | Retry có giới hạn và backoff |
| Bị giới hạn tốc độ | HTTP 429 hoặc thông báo throttling | Tuân thủ Retry-After nếu có, giảm tần suất |
| Dịch vụ không khả dụng | HTTP 5xx, database failover | Retry có giới hạn, circuit breaker và cảnh báo |
| Cấu hình/xác thực | Sai credential, thiếu quyền, URL sai | Dừng retry dày đặc, báo lỗi vận hành |
| Dữ liệu không hợp lệ | Thiếu trường bắt buộc, sai kiểu, schema không tương thích | Cách ly dữ liệu, ghi nhận lỗi và điều tra |
| Lỗi lập trình | Null ngoài dự kiến, lỗi mapping, invariant bị vi phạm | Để lỗi lộ rõ, sửa code và kiểm thử |

Một lỗi timeout không có nghĩa là nguồn không có dữ liệu. Nếu bắt exception rồi trả về null, ứng dụng sẽ coi sự cố là lần polling rỗng và có thể không phát hiện việc nguồn đã ngừng hoạt động.

Không bắt mọi Exception rồi chỉ ghi log ở mức DEBUG. Hãy phân loại lỗi có chủ đích. Lỗi tạm thời có thể retry; lỗi cấu hình hoặc dữ liệu không hợp lệ cần được cảnh báo và xử lý theo một quy trình riêng.

## 6. Để lỗi nguồn đi vào cơ chế error handling

Ví dụ Supplier có thể để lỗi từ client truyền ra ngoài:

~~~java
// ExternalSourceConfiguration.java
import java.util.Optional;
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ExternalSourceConfiguration {

    public interface ExternalOrderClient {
        Optional<ExternalOrderResponse> fetchNext();
    }

    @Bean
    Supplier<ExternalOrder> externalOrderSource(
            ExternalOrderClient client) {

        return () -> client.fetchNext()
            .map(this::toEvent)
            .orElse(null);
    }

    private ExternalOrder toEvent(ExternalOrderResponse response) {
        if (response.orderId() == null || response.orderId().isBlank()) {
            throw new IllegalArgumentException(
                "External order is missing orderId"
            );
        }

        return new ExternalOrder(
            response.orderId(),
            response.total()
        );
    }

    public record ExternalOrderResponse(String orderId, long total) {}
    public record ExternalOrder(String orderId, long total) {}
}
~~~

ExternalOrderClient cần được cung cấp như một bean riêng, ví dụ adapter gọi REST API hoặc truy vấn database. Cấu hình Supplier chỉ chịu trách nhiệm chuyển kết quả adapter thành payload và để lỗi truyền tới cơ chế xử lý lỗi.

Khi client ném exception, Supplier không được biến nó thành kết quả rỗng. Exception đi vào cơ chế xử lý lỗi của poller/Spring Integration. Cách retry, định tuyến lỗi và thông báo phụ thuộc vào loại poller, error channel, error handler và cấu hình của ứng dụng.

Trong ứng dụng thực tế, nên tạo exception có ngữ nghĩa rõ như TransientSourceException và PermanentSourceException. Exception tạm thời có thể được retry; lỗi vĩnh viễn cần đưa vào luồng cảnh báo hoặc cách ly. Tránh để một lỗi dữ liệu không thể khắc phục bị retry vô hạn.

Nếu bắt exception để bổ sung ngữ cảnh, hãy giữ nguyên nguyên nhân:

~~~java
try {
    return client.fetchNext()
        .map(this::toEvent)
        .orElse(null);
} catch (SourceTimeoutException ex) {
    throw new TransientSourceException(
        "Could not fetch the next order from partner API",
        ex
    );
}
~~~

Chỉ bắt loại exception đã xác định được cách xử lý. Nếu không thể phục hồi tại Supplier, hãy để exception truyền tới error handling để hệ thống có thể quan sát và quyết định bước tiếp theo.

## 7. Retry, backoff và circuit breaker

Retry phù hợp với lỗi có khả năng tự phục hồi. Chính sách nên có giới hạn số lần thử, khoảng chờ tăng dần và jitter để nhiều instance không đồng loạt gọi lại nguồn.

Ví dụ lịch retry minh họa:

| Lần thử | Thời điểm tương đối |
|---|---:|
| Lần đầu | 0 giây |
| Retry 1 | Sau 1 giây |
| Retry 2 | Sau 2 giây |
| Retry 3 | Sau 4 giây |
| Sau giới hạn | Ghi nhận lỗi và chuyển sang trạng thái phục hồi |

Đây là ví dụ backoff lũy tiến; giá trị thực tế phải dựa trên timeout, giới hạn dịch vụ và mức độ khẩn cấp của dữ liệu.

Circuit breaker tạm ngừng gọi nguồn khi tỷ lệ lỗi vượt ngưỡng. Sau thời gian chờ, nó cho phép một số request thăm dò để xác định dịch vụ đã phục hồi hay chưa. Cơ chế này tránh việc hàng loạt instance liên tục gây tải lên nguồn đang gặp sự cố.

Không retry mọi lỗi. Sai credential, thiếu quyền, URL không hợp lệ hoặc dữ liệu không thể giải mã thường không được khắc phục bằng việc gọi lại ngay. Với HTTP 429, tôn trọng thời gian chờ do đối tác cung cấp nếu có. Với timeout, cân nhắc rằng request có thể đã được đối tác xử lý dù response bị mất; thao tác đọc nên an toàn khi lặp, còn thao tác ghi cần idempotency key.

Không đặt retry vô hạn bên trong Supplier mà không có giới hạn thời gian. Poller cần tiếp tục hoạt động và hệ thống cần có cách cảnh báo khi nguồn ngừng cung cấp dữ liệu.

## 8. Không có dữ liệu không phải là lỗi và không nên tạo log cảnh báo liên tục

Một nguồn polling có thể rỗng trong phần lớn thời gian. Đây là trạng thái bình thường nếu nguồn chỉ phát khi có dữ liệu mới.

Nên theo dõi các metric riêng:

- Số lần polling.
- Số lần polling không có dữ liệu.
- Thời gian trung bình và phân vị cao của một lần đọc nguồn.
- Số lần đọc thành công.
- Số lỗi theo nhóm: timeout, throttling, authentication, invalid data.
- Số lần retry và circuit breaker đang mở.
- Tuổi của bản ghi chưa được xử lý lâu nhất.
- Số message phát thành công và số lần publish thất bại.

Không ghi WARN cho mỗi lần nguồn rỗng. Có thể dùng metric hoặc log ở mức DEBUG cho trạng thái bình thường. Cảnh báo nên kích hoạt khi không có dữ liệu lâu bất thường so với nhịp nguồn, backlog tăng, nguồn liên tục lỗi hoặc circuit breaker mở quá lâu.

Nếu nguồn thường xuyên có dữ liệu theo lịch, có thể theo dõi thời điểm bản ghi gần nhất và độ trễ từ occurredAt đến thời điểm publish. Nhờ vậy phân biệt nguồn thực sự không có thay đổi với việc pipeline đã ngừng hoạt động.

## 9. Bảo vệ dữ liệu khi đọc nguồn và phát message

Dữ liệu nguồn có thể chứa thông tin nhạy cảm hoặc payload lớn. Trước khi phát, cần:

- Xác thực dữ liệu bắt buộc và giới hạn kích thước payload.
- Loại bỏ trường nội bộ hoặc thông tin bí mật không thuộc event contract.
- Chuẩn hóa timestamp, timezone, số tiền và enum.
- Không ghi toàn bộ response hoặc token vào log.
- Giới hạn thời gian chờ và số lần gọi đồng thời.
- Quản lý credential bằng secret manager hoặc biến môi trường.
- Kiểm tra schema trước khi gửi để tránh phát message không thể tiêu thụ.

Nếu dữ liệu nguồn không hợp lệ, hãy giữ lại đủ thông tin chẩn đoán như source, record key, thời điểm nhận và lý do validation thất bại. Không nhất thiết phải lưu toàn bộ payload lỗi nếu nó chứa dữ liệu nhạy cảm. Có thể lưu bản đã che dữ liệu hoặc mã tham chiếu tới kho cách ly được kiểm soát quyền truy cập.

## 10. Phân biệt lỗi đọc nguồn với lỗi gửi tới broker

Một lần phát event có hai chặng độc lập:

1. Đọc dữ liệu từ nguồn.
2. Gửi message qua output binding tới broker.

Lỗi ở chặng đầu xảy ra trước khi có payload hợp lệ. Lỗi ở chặng thứ hai xảy ra sau khi ứng dụng đã có dữ liệu và đang vận chuyển message. Hai loại lỗi cần metric, log và quy trình phục hồi riêng.

| Chặng | Ví dụ lỗi | Cách điều tra |
|---|---|---|
| Đọc nguồn | API timeout, database unavailable | Kiểm tra kết nối, timeout, credential, rate limit |
| Mapping/validation | Sai schema, thiếu trường | Kiểm tra dữ liệu đầu vào và mapper |
| Gửi broker | Broker unreachable, authorization failed | Kiểm tra binder, destination, quyền và broker health |
| Xác nhận gửi | Mất kết nối trong lúc chờ kết quả | Xác định message có thể đã được nhận hay chưa; dùng ID ổn định để chống trùng |

Không nên dùng DLQ của consumer để xử lý mọi lỗi đọc nguồn. Khi chưa lấy được dữ liệu, chưa có event hợp lệ để gửi vào destination lỗi. Có thể ghi nhận lỗi nguồn trong kho vận hành hoặc error topic riêng nếu đã có một payload chẩn đoán được định nghĩa; không phát một event nghiệp vụ giả chỉ để đưa lỗi vào DLQ.

Khi send API trả về thành công, cần hiểu chính xác mức xác nhận mà binder cung cấp. Việc message được chấp nhận vào channel ứng dụng không phải lúc nào cũng đồng nghĩa broker đã lưu bền vững. Nếu cần bảo đảm mạnh hơn, cấu hình producer acknowledgement/confirmation phù hợp với binder và theo dõi kết quả publish.

## 11. Bảo đảm không mất dữ liệu khi nguồn có trạng thái

Nếu Supplier đọc một bản ghi rồi đánh dấu đã xử lý trước khi broker nhận message, sự cố ở bước publish có thể làm mất event. Nếu publish thành công nhưng ứng dụng không ghi nhận đã xử lý, lần polling tiếp theo có thể phát lại event. Đây là ranh giới giữa nguồn dữ liệu và broker.

Với dữ liệu quan trọng, dùng mô hình claim/lease hoặc transactional outbox:

~~~text
Nguồn dữ liệu / Outbox
       |
       v
Claim một bản ghi có lease
       |
       v
Tạo event có eventId ổn định
       |
       v
Publish qua binder
       |
       +---- Xác nhận theo chính sách broker
       |              |
       |              v
       |         Đánh dấu đã gửi
       |
       +---- Lỗi hoặc không rõ kết quả
                      |
                      v
              Giữ/release lease
              và thử lại có kiểm soát
~~~

Outbox ghi thay đổi nghiệp vụ và event cần phát trong cùng transaction cơ sở dữ liệu. Relay đọc các bản ghi chưa gửi, phát chúng rồi đánh dấu đã gửi theo cơ chế xác nhận phù hợp. Nếu relay dừng sau khi publish nhưng trước khi cập nhật trạng thái, event có thể được phát lại. Vì vậy, event ID phải ổn định và consumer phải idempotent.

Một Supplier poller đơn giản không tự tạo ra transaction nguyên tử giữa nguồn dữ liệu và broker. Nếu cần cập nhật cursor, xác nhận bản ghi nguồn sau khi publish hoặc phối hợp nhiều bước, hãy dùng relay có trạng thái rõ ràng, outbox hoặc connector chuyên dụng. Không đánh dấu nguồn đã hoàn tất chỉ vì Supplier đã trả về payload.

Với API bên ngoài có cursor hoặc pagination token, chỉ cập nhật cursor sau khi dữ liệu tương ứng đã được lưu bền vững hoặc publish theo quy trình có thể phục hồi. Nếu không, lỗi giữa lúc lấy trang và lúc lưu cursor có thể bỏ sót dữ liệu.

## 12. Xử lý dữ liệu sai và cách ly bản ghi

Một nguồn có thể trả về bản ghi thiếu trường bắt buộc hoặc không đúng schema. Không nên bỏ qua âm thầm, cũng không nên retry vô hạn một bản ghi chắc chắn không thể hợp lệ.

Một quy trình xử lý có thể gồm:

1. Xác định record key, source và thời điểm lấy dữ liệu.
2. Validate payload trước khi tạo event.
3. Nếu hợp lệ, ánh xạ sang event contract.
4. Nếu không hợp lệ, ghi lý do và chuyển bản ghi vào vùng quarantine có kiểm soát.
5. Phát cảnh báo hoặc tạo ticket theo mức độ ảnh hưởng.
6. Sau khi sửa dữ liệu hoặc mapper, cho phép xử lý lại bản ghi với event ID ổn định nếu event đã được tạo.

Quarantine là nơi lưu dữ liệu lỗi để điều tra. Nó khác DLQ: DLQ thường giữ message đã được broker giao tới consumer nhưng consumer không xử lý được; quarantine có thể giữ dữ liệu nguồn chưa trở thành message hợp lệ.

## 13. Kiểm thử nguồn rỗng, lỗi và phục hồi

Kiểm thử Supplier cần xác nhận cả kết quả không phát message và đường đi lỗi:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Client trả Optional.empty() | Supplier trả null, không có output message |
| Client trả một bản ghi hợp lệ | Supplier tạo đúng event |
| Client timeout tạm thời | Lỗi được phân loại và đi vào retry/error handling |
| Client trả lỗi xác thực | Không retry dày đặc; có cảnh báo vận hành |
| Payload thiếu trường bắt buộc | Validation thất bại và dữ liệu được cách ly |
| Broker không khả dụng | Publish failure được ghi nhận; dữ liệu nguồn có thể phục hồi |
| Relay restart sau publish | Có thể phát lại cùng event ID; consumer chống trùng |
| Nhiều instance cùng polling | Không claim cùng một bản ghi nếu nguồn yêu cầu độc quyền |

Ví dụ unit test cho Supplier:

~~~java
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Optional;
import java.util.function.Supplier;

import org.junit.jupiter.api.Test;

class OrderSourceConfigurationTest {

    @Test
    void emitsNothingWhenSourceIsEmpty() {
        OrderSourceClient client = () -> Optional.empty();
        OrderSourceConfiguration configuration =
            new OrderSourceConfiguration();

        Supplier<OrderCreated> supplier = configuration.orderSource(client);

        assertNull(supplier.get());
    }

    @Test
    void mapsAvailableRecordToEvent() {
        OrderSourceClient client = () -> Optional.of(
            new OrderSnapshot("ord-100", "cus-200", 50000)
        );
        OrderSourceConfiguration configuration =
            new OrderSourceConfiguration();

        Supplier<OrderCreated> supplier = configuration.orderSource(client);

        OrderCreated event = supplier.get();
        assertEquals("ord-100", event.orderId());
        assertEquals(50000, event.total());
    }
}
~~~

Bổ sung test cho exception để xác nhận lỗi không bị chuyển thành null. Test binder có thể xác nhận Supplier rỗng không phát message và Supplier có dữ liệu phát đúng payload. Integration test với broker thật cần kiểm tra publish failure, retry, xác nhận producer và khả năng phát lại sau restart.

Test binder không mô phỏng đầy đủ timeout của API đối tác, rate limit, lease của nguồn hoặc broker acknowledgement. Những hành vi đó cần được kiểm tra bằng fake server, database test hoặc broker thật trong integration test.

## 14. Trình tự thực hành và tiêu chí hoàn thành

Thực hiện bài tập với một nguồn đơn hàng bên ngoài:

1. Tạo client có phương thức fetchNext trả về Optional<OrderSnapshot>.
2. Viết Supplier chuyển bản ghi hợp lệ thành OrderCreated.
3. Khi nguồn rỗng, trả null và xác nhận không có output message.
4. Cấu hình poller và output binding trong application.yml.
5. Mô phỏng timeout, throttling, lỗi xác thực và payload không hợp lệ.
6. Phân loại lỗi tạm thời và lỗi vĩnh viễn; thêm retry có giới hạn và cảnh báo.
7. Theo dõi số lần polling rỗng, thời gian đọc, lỗi và backlog.
8. Mô phỏng broker ngắt kết nối sau khi nguồn đã trả dữ liệu.
9. Thiết kế cách claim/lease hoặc outbox để không mất dữ liệu khi publish thất bại.
10. Khởi động nhiều instance và kiểm tra không đọc trùng ngoài ý muốn.

Hoàn thành bài khi có thể giải thích vì sao không có dữ liệu không phải lỗi, cách Supplier không phát message khi nguồn rỗng, cách phân loại lỗi đọc nguồn, cách dùng retry/backoff và cách bảo toàn dữ liệu qua ranh giới publish. Cần quan sát được cả trạng thái bình thường lẫn lỗi trong log, metric và integration test.

## 15. Tài liệu tham khảo chính thức

- [Spring Cloud Stream Reference](https://docs.spring.io/spring-cloud-stream/reference/index.html) — kiến trúc function, binding và binder.
- [Spring Cloud Stream — Programming model](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/programming-model.html) — Supplier, Function và Consumer.
- [Spring Cloud Stream — Configuration options](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html) — cấu hình binding và producer.
- [Spring Integration — Endpoint and Poller Configuration](https://docs.spring.io/spring-integration/reference/endpoint.html) — poller, fixed delay và polling endpoint.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html) — error channel và xử lý exception.
- [Spring Cloud Stream — Error handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html) — xử lý lỗi trong ứng dụng stream.
- [Spring Cloud Stream — StreamBridge](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html) — phát message từ thành phần không phải function.

