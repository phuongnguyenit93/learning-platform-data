# Retry có giới hạn, backoff và tránh nhiều tầng cùng thử lại

Retry là việc thực hiện lại một thao tác sau khi lần gọi trước thất bại. Trong hệ thống messaging, retry giúp chịu được lỗi tạm thời như broker khởi động lại, kết nối bị reset, timeout ngắn hoặc dịch vụ đích đang quá tải. Retry chỉ có ích khi lỗi có khả năng tự hết, thao tác có thể được thực hiện lại an toàn và chính sách thử lại có giới hạn.

Một chính sách tốt phải trả lời được năm câu hỏi: lỗi nào được thử lại, tối đa bao nhiêu lần, chờ bao lâu giữa các lần, tổng thời gian được phép tiêu tốn là bao nhiêu và tầng nào chịu trách nhiệm retry. Thiếu một trong các giới hạn này có thể biến một sự cố ngắn thành retry storm, tăng tải lên dịch vụ đang lỗi và kéo dài hàng đợi message.

## 1. Phân biệt lỗi tạm thời và lỗi không thể tự phục hồi

Không nên retry mọi exception. Trước khi cấu hình số lần thử, hãy phân loại nguyên nhân thất bại.

| Nhóm lỗi | Ví dụ trong messaging | Hành động phù hợp |
|---|---|---|
| Lỗi tạm thời | Broker tạm thời unavailable, connection reset, DNS lỗi thoáng qua, timeout do mạng, server trả 503 | Có thể retry có giới hạn và backoff |
| Quá tải có thể hồi phục | HTTP 429, 503 hoặc broker từ chối tạm thời do quota/concurrency | Retry theo backoff; tôn trọng Retry-After hoặc thời gian retry do broker chỉ định |
| Lỗi dữ liệu/contract | Payload sai schema, thiếu trường bắt buộc, metadata không hợp lệ, không deserialize được | Không retry nguyên trạng; đưa message vào luồng xử lý lỗi hoặc dead-letter |
| Lỗi xác thực/phân quyền | Token hết hạn, credentials sai, principal không có quyền gửi/nhận | Không retry liên tục; sửa credentials hoặc quyền |
| Lỗi cấu hình/định tuyến | Destination không tồn tại, route sai, serializer không tương thích | Không retry nếu cấu hình chưa thay đổi |
| Lỗi nghiệp vụ có chủ đích | Đơn hàng đã bị hủy, trạng thái không cho phép chuyển bước, dữ liệu vi phạm quy tắc | Trả lỗi nghiệp vụ hoặc chuyển xử lý; chỉ retry nếu domain xác định trạng thái có thể thay đổi và có lịch thử lại rõ ràng |

Một lỗi chỉ nên được coi là retryable khi có lý do cụ thể để tin rằng một lần gọi sau có thể thành công mà không cần thay đổi input hay cấu hình. Không dùng việc “bắt được RuntimeException” làm tiêu chí retry chung.

Với exception bọc nhiều lớp, cần kiểm tra nguyên nhân gốc. Ví dụ, một MessageDeliveryException có thể bao quanh lỗi mạng tạm thời nhưng cũng có thể bao quanh lỗi destination hoặc cấu hình. Hãy chuyển lỗi từ adapter thành exception có ý nghĩa của ứng dụng, chẳng hạn TransientDeliveryException, sau khi đã phân loại nguyên nhân.

## 2. Giới hạn số lần thử và phân biệt attempts với retries

Một lần thực thi ban đầu được gọi là initial attempt. Mỗi lần gọi lại sau thất bại là một retry.

- **Total attempts** = số lần thực thi ban đầu cộng số lần retry.
- **Max retries** = số lần gọi lại tối đa sau lần đầu.
- **Max attempts** = tổng số lần thực thi tối đa ở các API dùng tên này.

Ví dụ: initial attempt + 3 retries = tối đa 4 lần thực thi. Khi cấu hình, phải kiểm tra semantics của thư viện; các API khác nhau có thể đặt tên cho cùng một giới hạn theo cách khác nhau.

Giới hạn số lần thử bảo vệ hệ thống khỏi việc giữ request vô hạn. Khi hết retry, trả lỗi cuối cùng cho caller hoặc chuyển message sang dead-letter queue (DLQ) theo chính sách của hệ thống. Không âm thầm bỏ lỗi và không tiếp tục retry vô hạn trong một thread, listener hoặc request đang chờ.

Ngoài giới hạn theo từng request, hệ thống có thể đặt retry budget ở cấp dịch vụ: chỉ cho phép một tỷ lệ nhỏ lưu lượng bổ sung dành cho retry trong một khoảng thời gian. Khi ngân sách retry cạn, request mới thất bại nhanh hoặc đi theo fallback đã thiết kế. Cách này ngăn retry làm tăng tải đúng lúc dịch vụ đang suy giảm.

## 3. Backoff: tăng thời gian chờ giữa các lần retry

Nếu mọi client đều thử lại ngay sau lỗi, các request mới sẽ dồn vào dịch vụ đang phục hồi. Backoff tạo khoảng nghỉ giữa các lần gọi để dịch vụ có thời gian ổn định.

### 3.1. Fixed backoff

Fixed backoff dùng cùng một khoảng chờ cho mỗi lần retry. Ví dụ: chờ 500 ms sau mỗi lần thất bại.

Cách này đơn giản và phù hợp khi lỗi ngắn, lưu lượng nhỏ hoặc broker đã cung cấp thời gian redelivery cố định. Tuy nhiên, nếu hàng nghìn client cùng thất bại, chúng có thể tiếp tục thử lại gần như đồng thời.

### 3.2. Exponential backoff

Exponential backoff tăng thời gian chờ theo cấp số nhân:

~~~text
delay(n) = min(maxDelay, initialDelay × multiplier^(n - 1))
~~~

Trong đó:

- initialDelay là thời gian chờ trước retry đầu tiên.
- multiplier thường lớn hơn 1, ví dụ 2.
- n là thứ tự lần retry, bắt đầu từ 1.
- maxDelay là mức chờ tối đa, tránh thời gian tăng không giới hạn.

Ví dụ với initialDelay = 200 ms, multiplier = 2 và maxDelay = 2.000 ms:

| Lần retry | Thời gian chờ trước lần đó |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 2.000 ms (đã chạm giới hạn) |
| 6 | 2.000 ms |

Backoff tăng dần giúp giảm tốc độ gửi lại khi lỗi kéo dài. Luôn đặt maxDelay và giới hạn tổng số lần retry.

### 3.3. Jitter để tránh retry storm

Exponential backoff đơn thuần vẫn có thể đồng bộ. Nếu nhiều instance cùng nhận lỗi tại một thời điểm và cùng dùng lịch 200 ms, 400 ms, 800 ms, chúng có thể cùng gửi lại theo từng đợt. Hiện tượng này tạo retry storm.

Jitter thêm độ ngẫu nhiên vào thời gian chờ để các client phân tán lần retry. Một biến thể phổ biến là full jitter:

~~~text
cap(n) = min(maxDelay, initialDelay × multiplier^(n - 1))
actualDelay(n) = random(0, cap(n))
~~~

Một số thư viện dùng jitter theo tỷ lệ quanh thời gian backoff thay vì full jitter. Hãy kiểm tra semantics của thư viện đang dùng, đồng thời bảo đảm delay cuối vẫn nằm trong giới hạn min/max đã đặt.

Jitter đặc biệt hữu ích khi nhiều instance cùng kết nối tới một broker, API hoặc dịch vụ downstream. Không cần tự viết bộ sinh số ngẫu nhiên nếu thư viện đã cung cấp jitter phù hợp.

## 4. Ngân sách thời gian: giới hạn cả một chu kỳ retry

Giới hạn số lần retry chưa đủ. Nếu mỗi lần gọi có thể chờ vô hạn hoặc backoff quá dài, request vẫn giữ tài nguyên quá lâu.

Tổng thời gian một chu kỳ retry gồm thời gian thực thi từng attempt và thời gian chờ giữa các attempt:

~~~text
totalTime = Σ attemptTimeout(i) + Σ backoffDelay(i)
~~~

Ví dụ, một thao tác có tối đa 4 attempts, mỗi attempt có timeout 700 ms và các khoảng backoff là 200, 400, 800 ms. Thời gian tối đa theo mô hình này xấp xỉ:

~~~text
4 × 700 ms + 200 ms + 400 ms + 800 ms = 4.200 ms
~~~

Đây là phép tính ngân sách; cần tính thêm overhead của scheduler, kết nối, serialization và xử lý lỗi khi đặt deadline thực tế.

Các nguyên tắc quan trọng:

1. Đặt timeout riêng cho mỗi lần gọi tới broker hoặc dịch vụ downstream.
2. Đặt deadline tổng cho toàn bộ thao tác, bao gồm cả các lần chờ backoff.
3. Không bắt đầu retry nếu thời gian còn lại của deadline không đủ cho một attempt hợp lý.
4. Khi caller hủy request hoặc reactive subscription bị cancel, dừng lịch retry và giải phóng tài nguyên.
5. Với message được lưu bền vững trong broker, deadline xử lý có thể dài hơn request đồng bộ; khi đó dùng retry schedule và retention phù hợp với vòng đời message.

Nếu upstream đã truyền deadline hoặc timeout budget, hãy truyền phần thời gian còn lại xuống downstream. Không để mỗi tầng tự bắt đầu một timeout mới đầy đủ, vì tổng thời gian đầu cuối sẽ vượt quá giới hạn mà caller dự kiến.

## 5. Chọn đúng nơi chịu trách nhiệm retry

Một message thường đi qua nhiều tầng: API gateway, service, messaging client, broker và consumer. Mỗi tầng có thể có retry riêng. Nếu không phối hợp, số lần thực thi downstream bị nhân lên.

Giả sử có 4 tầng, mỗi tầng cho phép tổng cộng 3 lần thực thi. Số lần gọi có thể tới tầng cuối là:

~~~text
3 × 3 × 3 × 3 = 81 lần
~~~

Nếu mỗi tầng cấu hình 3 retries cộng với lần đầu, tổng cộng là 4 attempts mỗi tầng:

~~~text
4 × 4 × 4 × 4 = 256 lần
~~~

Đây là lý do không nên đặt retry lặp lại ở mọi tầng.

### 5.1. Phân công theo loại lỗi

| Vị trí | Trách nhiệm hợp lý |
|---|---|
| API/client | Giữ deadline đầu cuối, giới hạn retry cho thao tác mà client sở hữu |
| Messaging producer | Retry lỗi gửi có thể phục hồi, dựa trên cơ chế xác nhận của broker và tính idempotent |
| Broker/consumer container | Quản lý redelivery khi consumer chưa xác nhận message, giới hạn delivery attempts và DLQ |
| Consumer/application service | Retry một dependency cụ thể nếu lỗi đó thuộc phạm vi thao tác; tránh lặp lại chính sách redelivery của broker |
| Database client | Retry lỗi transaction tạm thời theo chính sách transaction, không bọc thêm một vòng retry không giới hạn bên ngoài |

Chọn một tầng làm chủ sở hữu cho retry nghiệp vụ của một thao tác. Các tầng dưới có thể có cơ chế phục hồi kết nối hoặc retry nội bộ phục vụ giao thức, nhưng phải biết rõ chúng có lặp lại thao tác nghiệp vụ hay không và phải tính vào ngân sách tổng.

### 5.2. Không retry cùng một thao tác hai lần

Ví dụ, NotificationService.publish() được đánh dấu @Retryable, nhưng MessageGateway bên trong cũng retry ba lần. Khi gateway lỗi, một lần gọi publish có thể tạo nhiều lần gửi. Nếu consumer còn có redelivery, số lần xử lý tiếp tục tăng.

Hãy chọn một nơi quản lý retry cho việc gửi message. Các tầng khác nên trả lỗi gốc hoặc lỗi đã phân loại lên tầng đó, thay vì tự lặp lại cùng thao tác. Ghi rõ retry owner trong tài liệu vận hành để tránh việc một nhóm thêm retry mà không biết chính sách đã có ở nơi khác.

## 6. Retry an toàn: idempotency và nguy cơ gửi trùng

Timeout không chứng minh thao tác chưa được thực hiện. Có thể broker đã nhận message nhưng ACK bị mất trên đường về. Producer thấy timeout và gửi lại; broker có thể nhận cùng một message hai lần.

Tương tự, consumer có thể đã ghi dữ liệu vào database nhưng tiến trình bị dừng trước khi ACK message. Broker giao lại message và consumer xử lý lần nữa.

Vì vậy, retry trong hệ thống phân tán thường tạo ra ngữ nghĩa at-least-once. Không được suy ra exactly-once chỉ từ việc có retry hoặc ACK.

### 6.1. Dùng idempotency key

Mỗi thao tác nghiệp vụ có thể có một idempotency key ổn định, ví dụ orderId + eventType hoặc một UUID được tạo trước lần gửi đầu tiên. Khi retry, giữ nguyên key; không tạo key mới cho từng attempt.

Consumer lưu key đã xử lý trong một bảng deduplication hoặc inbox. Việc kiểm tra key và ghi kết quả nghiệp vụ cần nằm trong cùng transaction để tránh race condition.

Ví dụ logic:

~~~text
BEGIN TRANSACTION

Nếu inbox đã có messageId:
    bỏ qua tác động nghiệp vụ và trả kết quả đã xử lý
Ngược lại:
    áp dụng thay đổi nghiệp vụ
    ghi messageId vào inbox

COMMIT
ACK message
~~~

Nếu thao tác gọi dịch vụ ngoài không nằm trong transaction của database, cần idempotency key được dịch vụ đích hỗ trợ hoặc một quy trình bù trừ/reconciliation phù hợp.

### 6.2. Outbox và inbox

Transactional outbox ghi sự kiện cần gửi vào cùng transaction với dữ liệu nghiệp vụ. Một publisher riêng đọc outbox và gửi lại cho tới khi nhận được xác nhận. Việc gửi có thể lặp, vì vậy consumer vẫn cần inbox/deduplication.

Mẫu này tách transaction nghiệp vụ khỏi việc gửi message và giúp phục hồi sau khi ứng dụng dừng giữa hai bước. Outbox không làm cho việc truyền message trở thành exactly-once; nó cung cấp cách lưu ý định gửi bền vững và xử lý trùng có kiểm soát.

### 6.3. Khi nào không thể retry an toàn?

Không retry tự động một thao tác có side effect nếu không biết kết quả lần trước. Ví dụ: trừ tiền, tạo đơn hàng hoặc gửi thông báo có thể đã hoàn thành dù caller nhận timeout.

Trước khi retry, phải có ít nhất một trong các điều kiện: thao tác idempotent; endpoint hỗ trợ idempotency key; có thể truy vấn trạng thái theo request ID; hoặc có quy trình nghiệp vụ xác minh và xử lý kết quả chưa rõ. Nếu không có, hãy trả trạng thái chưa xác định và để quy trình reconciliation xử lý.

## 7. Retry khi gửi message và khi consumer xử lý

Hai vị trí này có semantics khác nhau.

### 7.1. Producer gửi message

Producer cần phân biệt:

- Lỗi xảy ra trước khi message được gửi đi.
- Broker từ chối rõ ràng và xác nhận không nhận message.
- Producer không nhận được ACK nên không biết broker đã nhận hay chưa.

Trường hợp thứ ba là kết quả mơ hồ. Retry có thể tạo message trùng. Dùng message ID ổn định, producer confirmation nếu broker hỗ trợ, idempotent producer nếu nền tảng có tính năng đó và deduplication ở consumer.

### 7.2. Consumer xử lý message

Consumer thường chỉ ACK sau khi xử lý thành công. Nếu xử lý lỗi tạm thời, broker có thể redeliver message sau một khoảng chờ. Nếu lỗi không thể phục hồi, message nên được chuyển sang DLQ hoặc vùng quarantine để điều tra.

Không để một poison message được giao lại vô hạn. Cần giới hạn delivery attempts, ghi nhận nguyên nhân, giữ payload/metadata cần thiết để điều tra theo chính sách bảo mật và có quy trình replay sau khi đã sửa lỗi.

Khi kết hợp retry trong listener với broker redelivery, phải tính tổng số lần thực thi. Ví dụ listener thử 3 lần trong một lần giao, broker giao tối đa 5 lần thì một message có thể kích hoạt tới 15 lần xử lý.

### 7.3. Reactive messaging và stream

Với Mono, retry thường tạo subscription mới cho publisher. Với Flux, retry có thể subscribe lại và phát lại dữ liệu từ đầu tùy nguồn. Nếu nguồn là stream sự kiện, việc resubscribe có thể đọc lại những phần đã nhận trước đó.

Dùng cursor/offset hoặc resume token do nguồn dữ liệu hỗ trợ, lưu checkpoint nghiệp vụ và thiết kế consumer idempotent. Không xem retry của publisher là cơ chế khôi phục vị trí stream tự động.

## 8. Cấu hình retry trong Spring Framework

Cách cấu hình phụ thuộc phiên bản Spring Framework và kiểu xử lý đồng bộ hay reactive.

### 8.1. Spring Framework 7.0 trở lên: @Retryable tích hợp trong core

Từ Spring Framework 7.0, core framework có resilience support với @Retryable, @ConcurrencyLimit và programmatic retry. Cần bật xử lý annotation bằng @EnableResilientMethods.

Ví dụ sau giới hạn số lần gửi và chỉ retry exception mà adapter đã xác định là lỗi giao nhận tạm thời:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.resilience.annotation.EnableResilientMethods;
import org.springframework.resilience.annotation.Retryable;
import org.springframework.stereotype.Service;

@Configuration
@EnableResilientMethods
class MessagingResilienceConfiguration {
}

@Service
class NotificationPublisher {

    private final NotificationTransport transport;

    NotificationPublisher(NotificationTransport transport) {
        this.transport = transport;
    }

    @Retryable(
            includes = TransientDeliveryException.class,
            maxRetries = 4,
            delay = 100,
            jitter = 20,
            multiplier = 2,
            maxDelay = 1_000,
            timeout = 5_000
    )
    public void publish(Message<?> message) {
        transport.send(message);
    }
}

interface NotificationTransport {
    void send(Message<?> message);
}

class TransientDeliveryException extends RuntimeException {
    TransientDeliveryException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Đây là ví dụ cấu hình theo Spring Framework 7.0.2+ vì thuộc tính timeout được bổ sung từ 7.0.2. Các thành phần NotificationTransport và TransientDeliveryException là kiểu của ứng dụng, cần triển khai theo adapter thực tế.

Ý nghĩa các thuộc tính:

- includes: loại exception được phép retry. Chỉ đưa vào đây những lỗi đã phân loại là tạm thời.
- maxRetries: số lần retry sau lần đầu. Giá trị 4 có nghĩa tối đa 5 lần gọi phương thức.
- delay: thời gian chờ cơ sở, tính bằng millisecond theo mặc định.
- jitter: độ ngẫu nhiên bổ sung cho thời gian chờ.
- multiplier: hệ số tăng delay sau mỗi retry.
- maxDelay: giới hạn thời gian chờ tối đa.
- timeout: tổng thời gian cho lần gọi ban đầu, các lần retry và khoảng chờ; giá trị 0 nghĩa là không áp dụng timeout.

Không mặc định retry tất cả exception. @Retryable mặc định cho phép retry mọi exception nếu không cấu hình includes, excludes hoặc predicate; điều đó có thể khiến lỗi validation, authentication hay cấu hình bị lặp lại vô ích.

Annotation được áp dụng qua proxy của Spring. Phương thức cần được gọi từ bean khác thông qua Spring proxy; gọi nội bộ bằng this.publish(...) không đi qua proxy nên không kích hoạt retry advice. Hãy kiểm tra điều này khi retry không hoạt động như mong đợi.

Nếu cùng phương thức có @Transactional, retry advice mặc định nằm ngoài transaction advice. Mỗi attempt chạy trong một transaction mới; lỗi của attempt trước phải được rollback trước khi attempt kế tiếp bắt đầu. Điều này hữu ích với lỗi transaction tạm thời nhưng vẫn cần bảo đảm side effect bên ngoài transaction có thể được thực hiện lại an toàn.

### 8.2. Spring Framework 6.x và dự án dùng Spring Retry

@Retryable tích hợp trong core theo package org.springframework.resilience.annotation chỉ có từ Spring Framework 7.0. Với Spring Framework 6.x, không sao chép import hoặc cấu hình của ví dụ 7.x. Dự án có thể dùng thư viện Spring Retry riêng nếu đã đưa dependency đó vào, hoặc dùng Reactor Retry cho publisher reactive.

Spring Retry và Spring Framework 7 core có các annotation/package khác nhau. Hãy kiểm tra dependency tree và phiên bản thực tế để tránh khai báo đồng thời hai retry interceptor cho cùng một phương thức.

### 8.3. Reactive flow với Reactor Retry

Với thao tác trả về Mono hoặc Flux, dùng retryWhen thay vì chặn thread bằng sleep. Ví dụ:

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<Receipt> publish(Message<?> message) {
    return Mono.defer(() -> reactiveTransport.publish(message))
            .retryWhen(
                    Retry.backoff(3, Duration.ofMillis(200))
                            .maxBackoff(Duration.ofSeconds(2))
                            .jitter(0.5)
                            .filter(this::isTransient)
            );
}
~~~

Đây là fragment cần được đặt trong service có reactiveTransport và isTransient(Throwable). Retry.backoff(3, ...) cho phép tối đa 3 retry sau lần subscribe ban đầu, tức tối đa 4 subscriptions. maxBackoff giới hạn thời gian chờ và jitter phân tán các lần retry.

Mono.defer tạo publisher mới cho mỗi lần subscribe. Điều này hữu ích khi thao tác gửi message phải được tạo lại theo từng attempt. Nếu publisher là hot hoặc side effect đã được kích hoạt trước khi retryWhen được áp dụng, retry có thể không thực hiện lại thao tác như mong muốn.

Không áp dụng đồng thời @Retryable ở method và retryWhen trên cùng một operation trừ khi đã tính rõ tổng số attempts. Nếu cả hai cùng retry 4 lần, số lần thực thi thực tế có thể cao hơn nhiều so với dự kiến.

## 9. Retry, circuit breaker và concurrency limit

Retry phù hợp với lỗi ngắn và có khả năng tự phục hồi. Khi downstream đang lỗi kéo dài, tiếp tục retry chỉ làm tăng tải.

Circuit breaker theo dõi lỗi và tạm ngừng gọi downstream khi vượt ngưỡng. Sau thời gian chờ, nó cho phép một số request thử lại để kiểm tra dịch vụ đã phục hồi chưa. Retry và circuit breaker giải quyết hai vấn đề khác nhau:

- Retry xử lý một lần gọi thất bại có khả năng thành công ở lần tiếp theo.
- Circuit breaker ngăn nhiều request tiếp tục gọi một dependency đang lỗi.
- Concurrency limit giới hạn số thao tác đồng thời để bảo vệ tài nguyên.

Trong Spring Framework 7, @ConcurrencyLimit có thể giới hạn số lần truy cập đồng thời vào một method. Đây là kiểm soát tải, không thay thế retry policy. Không dùng retry để thay thế backpressure hoặc giới hạn concurrency.

Thứ tự kết hợp các decorator/interceptor ảnh hưởng đến số lần lỗi được ghi nhận và cách tính transaction. Hãy chọn thứ tự có chủ đích, kiểm tra behavior bằng integration test và tránh để circuit breaker bị mở bởi chính các exception đã được retry nội bộ nếu đó không phải ý định.

## 10. Quan sát và chẩn đoán

Một hệ thống retry cần metric để phân biệt lỗi gốc với lỗi do retry tạo thêm.

Nên theo dõi:

- Số lần gọi ban đầu và số lần retry theo dependency/operation.
- Tỷ lệ request thành công ngay lần đầu và thành công sau retry.
- Số lần retry exhaustion và số thao tác thất bại cuối cùng.
- Thời gian chờ backoff thực tế, tổng latency và số request hết deadline.
- Số message redelivery, số lần gửi vào DLQ và tuổi message lâu nhất trong queue.
- Số message trùng bị deduplicate và số lần xảy ra kết quả gửi mơ hồ.
- Trạng thái circuit breaker, số request bị từ chối nhanh và concurrency đang sử dụng.

Log mỗi lần retry với operation name, attempt index, nguyên nhân phân loại và delay đã chọn. Tránh log toàn bộ payload, token, thông tin cá nhân hoặc credentials. Dùng message ID hoặc correlation ID để nối log producer, broker và consumer.

Nếu tỷ lệ retry tăng nhưng tỷ lệ thành công sau retry giảm, hãy kiểm tra tình trạng downstream và mở circuit breaker hoặc giảm tải. Nếu retry exhaustion tập trung ở một loại exception, kiểm tra xem lỗi đó có thực sự transient hay đã trở thành lỗi cấu hình/contract kéo dài.

## 11. Kiểm thử chính sách retry

Kiểm thử phải xác nhận cả điều kiện retry lẫn điều kiện dừng.

1. Với lỗi tạm thời, thao tác được thực hiện lại đúng số lần tối đa.
2. Với lỗi validation, authentication hoặc lỗi contract, thao tác thất bại ngay mà không retry.
3. Backoff tăng đúng quy luật và không vượt maxDelay.
4. Jitter nằm trong giới hạn được thư viện quy định.
5. Deadline tổng ngăn một request chờ vượt ngân sách.
6. Khi hết retry, exception cuối cùng hoặc trạng thái thất bại được chuyển tới caller đúng cách.
7. Khi producer timeout sau khi broker đã nhận message, message trùng không gây side effect lặp.
8. Khi consumer commit xong nhưng ACK thất bại, redelivery không làm lặp tác động nghiệp vụ.
9. Retry ở client, service, listener và broker không nhân lên vượt quá ngân sách đã thiết kế.
10. Khi reactive subscriber bị cancel, không tiếp tục tạo lần retry mới.

Dùng mock hoặc test broker để mô phỏng connection reset, timeout, broker unavailable, ACK bị mất và message lỗi vĩnh viễn. Với backoff, dùng scheduler/clock có thể điều khiển để test nhanh và ổn định thay vì chờ thời gian thực trong mọi test.

## 12. Checklist trước khi đưa vào production

- [ ] Chỉ retry lỗi đã được phân loại là transient.
- [ ] Đã xác định rõ maxRetries hay maxAttempts và tổng số lần gọi thực tế.
- [ ] Có initial delay, multiplier, maxDelay và jitter phù hợp.
- [ ] Mỗi attempt có timeout; toàn bộ operation có deadline.
- [ ] Có một tầng sở hữu retry nghiệp vụ và đã tính retry của broker/client.
- [ ] Các thao tác có side effect dùng idempotency key, deduplication hoặc cơ chế xác minh trạng thái.
- [ ] Consumer có giới hạn redelivery, DLQ và quy trình replay.
- [ ] Có circuit breaker, concurrency limit hoặc backpressure khi cần bảo vệ downstream.
- [ ] Có metric/log cho retry, exhaustion, redelivery và duplicate.
- [ ] Có kiểm thử lỗi tạm thời, lỗi vĩnh viễn, timeout mơ hồ và retry trùng tầng.
- [ ] Đã xác nhận API retry đúng với phiên bản Spring Framework, Spring Retry và Reactor trong dependency tree.

## Tài liệu tham khảo

- Spring Framework Reference — Resilience Features (Spring Framework 7.0): https://docs.spring.io/spring-framework/reference/core/resilience.html
- Spring Framework Javadoc — org.springframework.resilience.annotation.Retryable: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/resilience/annotation/Retryable.html
- Spring Framework Javadoc — EnableResilientMethods: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/resilience/annotation/EnableResilientMethods.html
- Project Reactor Javadoc — RetryBackoffSpec: https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html
- Spring Retry project (dành cho ứng dụng đang sử dụng dependency Spring Retry riêng): https://github.com/spring-attic/spring-retry
