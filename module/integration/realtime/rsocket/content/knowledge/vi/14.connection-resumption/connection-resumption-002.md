# Thử kết nối lại với backoff, jitter và số lần thử hữu hạn

## Mục tiêu bài học

Kết nối RSocket có thể bị gián đoạn do mạng chập chờn, server khởi động lại, proxy đóng kết nối hoặc hệ thống đang triển khai phiên bản mới. Client cần một chính sách kết nối lại đủ kiên nhẫn để vượt qua lỗi tạm thời, đồng thời có giới hạn để không tạo thêm áp lực lên hệ thống đang gặp sự cố.

Sau bài này, bạn có thể:

- Phân biệt lỗi kết nối tạm thời với lỗi cấu hình hoặc xác thực cần xử lý ngay.
- Thiết kế exponential backoff có giới hạn và thêm jitter để phân tán thời điểm retry.
- Đặt số lần thử hữu hạn và deadline tổng cho quá trình kết nối.
- Triển khai retry bất đồng bộ bằng Reactor.
- Tránh nhiều luồng đồng thời tạo nhiều vòng reconnect cho cùng một client.
- Phân biệt mở kết nối/session mới với phục hồi session RSocket bằng resume.
- Xử lý request đang chạy và trạng thái nghiệp vụ chưa xác định khi kết nối bị mất.

## Vì sao không nên reconnect liên tục?

Giả sử một server vừa khởi động lại và hàng nghìn client phát hiện kết nối bị đóng gần như cùng lúc. Nếu tất cả client lập tức kết nối lại, server có thể nhận một đợt tải lớn ngay khi đang phục hồi. Nếu kết nối thất bại, các client tiếp tục thử liên tục, tạo thành retry storm.

Một chính sách retry tốt cần cân bằng ba mục tiêu:

- **Khả năng phục hồi:** tiếp tục thử khi lỗi có khả năng chỉ là tạm thời.
- **Giới hạn tải:** giảm tần suất thử khi server chưa sẵn sàng.
- **Thời gian chờ có thể dự đoán:** kết thúc sau số lần thử hoặc deadline đã định.

Kết nối lại là một hoạt động bất đồng bộ. Không nên dùng vòng lặp chặt hoặc Thread.sleep() trên event loop để chờ lần thử tiếp theo. Hãy để scheduler của thư viện reactive quản lý khoảng nghỉ và tiếp tục pipeline khi đến thời điểm retry.

## Phân loại lỗi trước khi retry

Không phải lỗi nào cũng nên thử lại. Trước tiên, cần xác định lỗi có khả năng tự biến mất hay không.

| Loại lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Connection reset, server đang restart, network timeout | Retry có backoff và giới hạn |
| Quá tải | Server từ chối hoặc tạm thời không tiếp nhận kết nối | Retry chậm hơn, có jitter; tôn trọng tín hiệu retry-after nếu ứng dụng có |
| Cấu hình | Sai host, port, route transport hoặc MIME type | Dừng và sửa cấu hình |
| Xác thực/phân quyền | Credential hết hạn, token không hợp lệ, bị từ chối | Làm mới credential hoặc xử lý quyền; không retry mù |
| Không tương thích | Hai phía không thống nhất giao thức hoặc serialization | Sửa phiên bản/cấu hình |
| Lỗi lập trình | Null, lỗi khởi tạo bean hoặc exception không liên quan kết nối | Sửa lỗi; không xem như lỗi mạng |

Một predicate phân loại lỗi nên dựa vào exception cụ thể của transport, client và framework đang sử dụng. Tránh viết quy tắc chung kiểu “mọi exception đều retry”, vì điều đó che giấu lỗi cấu hình và có thể làm hệ thống thử lại vô hạn.

Với lỗi xác thực, chỉ retry sau khi có hành động thay đổi điều kiện, ví dụ làm mới token thành công. Gửi lại cùng credential không hợp lệ thường không làm lỗi tự biến mất.

## Exponential backoff

Backoff tăng khoảng nghỉ sau mỗi lần thử thất bại. Một công thức thường dùng là:

d(n) = min(d(max), d(base) × 2^(n-1))

Trong đó:

- d(base) là khoảng nghỉ ban đầu.
- n là số thứ tự lần retry.
- d(max) là khoảng nghỉ tối đa.

Ví dụ với khoảng nghỉ ban đầu 250 ms và giới hạn 4 giây:

| Lần retry | Khoảng nghỉ trước jitter |
|---:|---:|
| 1 | 250 ms |
| 2 | 500 ms |
| 3 | 1.000 ms |
| 4 | 2.000 ms |
| 5 trở đi | Tối đa 4.000 ms |

Backoff giúp client giảm tần suất kết nối khi lỗi kéo dài. Giới hạn tối đa ngăn khoảng nghỉ tăng đến mức quá lớn và khó dự đoán.

Backoff không đồng nghĩa với việc request được xếp hàng an toàn. Nếu ứng dụng cần giữ các lệnh trong thời gian mất kết nối, phải thiết kế queue riêng có giới hạn, thời hạn sống và chính sách xử lý khi queue đầy.

## Jitter giúp tránh retry đồng loạt

Nếu mọi client dùng cùng một khoảng nghỉ cố định hoặc cùng một lịch exponential backoff, chúng có thể thử lại gần như cùng thời điểm. Hiện tượng này thường gọi là *thundering herd*.

**Jitter** thêm một thành phần ngẫu nhiên vào thời gian chờ. Nhờ đó, các client phân tán lần thử trong một khoảng thời gian thay vì đồng loạt reconnect.

~~~mermaid
flowchart TD
    E[Connection lost] --> B[Calculate exponential backoff]
    B --> J[Apply random jitter]
    J --> W[Wait asynchronously]
    W --> A[Attempt connection]
    A -->|Success| C[Connected]
    A -->|Transient failure| B
    A -->|Permanent failure| F[Stop and report failure]
    A -->|Retry budget exhausted| X[Stop / open circuit]
~~~

Ví dụ, một nhóm client cùng có backoff danh nghĩa 2 giây. Khi có jitter, thời điểm thử lại của từng client sẽ dao động quanh khoảng đó. Server nhờ vậy nhận các kết nối rải đều hơn.

Jitter nên được áp dụng cùng backoff và giới hạn tối đa. Chỉ thêm random delay nhưng không giới hạn số lần thử vẫn có thể khiến client retry mãi.

## Số lần thử hữu hạn và deadline tổng

Một chính sách retry cần nói rõ số lần thử được tính như thế nào. Ví dụ:

- Một lần thử ban đầu.
- Tối đa bốn lần retry sau khi lần thử trước thất bại.
- Tổng cộng tối đa năm lần gọi kết nối.

Ngoài số lần thử, hãy đặt deadline tổng cho cả quá trình. Mỗi lần thử có thể có timeout riêng, còn deadline tổng ngăn việc nhiều lần thử cộng với thời gian backoff kéo dài quá lâu.

Hai giới hạn giải quyết hai vấn đề khác nhau:

| Giới hạn | Mục đích |
|---|---|
| Timeout mỗi lần thử | Tránh một lần mở kết nối bị treo quá lâu |
| Số lần retry tối đa | Giới hạn số lần tạo kết nối mới |
| Deadline tổng | Giới hạn thời gian người gọi phải chờ kết nối sẵn sàng |

Khi hết retry budget, pipeline nên phát lỗi cuối cùng hoặc chuyển sang trạng thái offline có thể quan sát được. Nếu hệ thống có circuit breaker, có thể mở circuit trong một khoảng thời gian rồi cho phép một số lần thử thăm dò. Circuit breaker và retry là hai cơ chế bổ sung, không thay thế lẫn nhau.

## Ví dụ retry kết nối bằng Reactor

Đoạn code sau minh họa một chính sách cho quá trình thiết lập kết nối. Phương thức connectOnce() là phương thức của ứng dụng, trả về Mono<RSocketRequester> khi kết nối và setup thành công. Chi tiết tạo requester phụ thuộc vào transport và phiên bản Spring RSocket đang dùng.

~~~java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

class RSocketConnectionManager {

    private Mono<RSocketRequester> connectWithRetry() {
        Retry retryPolicy = Retry
            .backoff(4, Duration.ofMillis(250))
            .maxBackoff(Duration.ofSeconds(4))
            .jitter(0.5)
            .filter(this::isTransientConnectionFailure)
            .doBeforeRetry(signal ->
                log.warn(
                    "RSocket reconnect retry {}/{} after failure",
                    signal.totalRetries() + 1,
                    4,
                    signal.failure()
                )
            );

        return Mono.defer(this::connectOnce)
            .timeout(Duration.ofSeconds(3))
            .retryWhen(retryPolicy)
            .timeout(Duration.ofSeconds(20));
    }

    private Mono<RSocketRequester> connectOnce() {
        // Tạo kết nối và hoàn tất RSocket SETUP.
        // Trả về requester mới khi session sẵn sàng.
        return createAndConnectRequester();
    }

    private boolean isTransientConnectionFailure(Throwable error) {
        // Phân loại exception theo transport/client thực tế.
        return error instanceof TransientConnectionException
            || error instanceof java.util.concurrent.TimeoutException;
    }
}
~~~

Các điểm cần chú ý:

- Mono.defer(this::connectOnce) tạo một lần kết nối mới cho mỗi lần subscribe/retry. Không tái sử dụng một publisher nóng đã bị kết thúc hoặc một tài nguyên kết nối đã đóng.
- timeout(Duration.ofSeconds(3)) giới hạn thời gian cho từng lần kết nối.
- Retry.backoff(4, ...) cho phép tối đa bốn lần retry sau lần thử ban đầu, tức tối đa năm lần thử.
- maxBackoff giới hạn khoảng nghỉ tăng dần.
- jitter(0.5) thêm dao động ngẫu nhiên quanh backoff để giảm việc client thử lại đồng loạt.
- filter chỉ cho retry những lỗi được xác định là tạm thời.
- timeout(Duration.ofSeconds(20)) giới hạn thời gian tổng của pipeline kết nối.

Các kiểu exception trong ví dụ là minh họa. Hãy thay bằng exception thực tế của transport và thư viện đang sử dụng. Nếu timeout tổng xảy ra hoặc retry budget hết, ứng dụng cần phát trạng thái offline và để tầng gọi quyết định bước tiếp theo.

## Quản lý một vòng reconnect cho mỗi client

Một lỗi phổ biến là mỗi request đang chờ tự khởi tạo một vòng reconnect riêng. Khi kết nối mất, 50 request có thể tạo 50 tác vụ mở kết nối cùng lúc.

Hãy đặt reconnect ở một thành phần quản lý kết nối dùng chung:

1. Theo dõi trạng thái kết nối hiện tại.
2. Khi phát hiện mất kết nối, chuyển sang trạng thái DISCONNECTED.
3. Chỉ tạo một tác vụ reconnect đang hoạt động cho mỗi kết nối logic.
4. Các request mới quan sát trạng thái và chờ kết nối, bị từ chối hoặc vào queue hữu hạn theo chính sách.
5. Khi kết nối sẵn sàng, phát sự kiện CONNECTED và cho phép request mới tiếp tục.
6. Nếu retry budget hết, chuyển sang trạng thái FAILED hoặc OFFLINE để tầng vận hành có thể xử lý.

Một state machine đơn giản:

~~~mermaid
stateDiagram-v2
    [*] --> DISCONNECTED
    DISCONNECTED --> CONNECTING: start
    CONNECTING --> CONNECTED: setup success
    CONNECTING --> RETRY_WAIT: transient failure
    RETRY_WAIT --> CONNECTING: backoff elapsed
    CONNECTING --> FAILED: permanent failure / budget exhausted
    CONNECTED --> DISCONNECTED: transport lost
    FAILED --> CONNECTING: explicit recovery
~~~

Cần tránh tạo reconnect loop mới khi loop cũ chưa kết thúc. Có thể dùng một publisher dùng chung, atomic state hoặc cơ chế single-flight phù hợp với kiến trúc. Khi reconnect thành công ổn định, reset retry counter theo chính sách; không reset ngay sau một handshake chớp nhoáng rồi lại mất kết nối liên tục.

## Reconnect khác gì RSocket connection resumption?

Hai khái niệm này liên quan nhưng không giống nhau.

**Reconnect** là mở lại transport và thiết lập một kết nối/session mới. Nếu session cũ đã mất, các request đang chạy trên session đó có thể bị gián đoạn. Ứng dụng phải quyết định có gửi lại thao tác hay không.

**RSocket resumption** là cơ chế giao thức cho phép hai peer tiếp tục một session đã được hỗ trợ resume sau khi transport bị gián đoạn tạm thời. Việc này cần được cấu hình và hỗ trợ bởi implementation ở cả hai phía. Quá trình resume dựa trên trạng thái phiên và vị trí frame đã trao đổi; nó không phải là một lần SETUP hoàn toàn mới.

Một số điểm cần nhớ:

- Không phải mọi RSocket client/server đều bật resumption mặc định.
- Resumption cần bộ đệm và trạng thái phiên trong giới hạn cấu hình.
- Nếu peer không còn giữ trạng thái cần thiết hoặc thời hạn resume đã hết, resume có thể thất bại.
- Khi resume thất bại, ứng dụng có thể cần tạo session mới và khôi phục trạng thái nghiệp vụ ở tầng ứng dụng.
- Resumption không tự bảo đảm exactly-once cho tác dụng phụ nghiệp vụ.

~~~mermaid
flowchart TD
    L[Transport bị gián đoạn] --> R{Có cấu hình và hỗ trợ resume?}
    R -->|Có| A[Thử RESUME session cũ]
    A -->|Thành công| S[Tiếp tục session và stream được hỗ trợ]
    A -->|Thất bại| N[Tạo session mới nếu chính sách cho phép]
    R -->|Không| N
    N --> P[Khôi phục trạng thái nghiệp vụ]
~~~

Chính sách retry kết nối vẫn cần thiết để thiết lập lại transport hoặc thử resume. Tuy nhiên, logic resume và logic mở session mới cần được phân biệt để ứng dụng không vô tình coi một session mới là session cũ.

## Điều gì xảy ra với request đang chạy?

Khi kết nối bị mất, kết quả của request có thể thuộc một trong ba trạng thái:

- **Chưa được gửi hoặc server chưa nhận:** thao tác có thể cần gửi lại.
- **Server đã xử lý nhưng response chưa đến:** gửi lại có thể tạo tác dụng phụ trùng.
- **Đã nhận được kết quả:** không cần retry nghiệp vụ.

Ở phía client, hai trường hợp đầu có thể khó phân biệt nếu kết nối đứt đúng lúc đang trao đổi. Không nên tự động phát lại tất cả request chỉ vì reconnect thành công.

Với thao tác có tác dụng phụ, hãy dùng:

- commandId hoặc correlation ID để truy vết.
- Idempotency key ổn định qua các lần retry.
- Route truy vấn trạng thái để biết server đã ghi nhận hay hoàn tất chưa.
- Kho lưu trạng thái hoặc outbox nếu nghiệp vụ yêu cầu tiếp nhận bền vững.

Với request-stream và request-channel, cần quyết định có tiếp tục từ cursor/sequence number hay tạo một tương tác mới. Việc subscribe lại một stream từ đầu có thể phát dữ liệu trùng hoặc bỏ lỡ sự kiện nếu nguồn dữ liệu không hỗ trợ replay.

## Hàng đợi trong thời gian mất kết nối

Nếu ứng dụng cần tiếp tục nhận lệnh từ tầng nghiệp vụ khi RSocket đang reconnect, có thể dùng queue tạm thời. Queue này phải có giới hạn rõ ràng:

- Giới hạn số phần tử hoặc tổng dung lượng.
- Giới hạn thời gian một lệnh được phép chờ.
- Quy định xử lý khi queue đầy: từ chối, lưu bền vững hoặc bỏ dữ liệu theo mức độ quan trọng.
- Phân biệt lệnh có thể gộp với lệnh phải giữ nguyên thứ tự.
- Dùng idempotency key khi gửi lại lệnh sau khi kết nối phục hồi.

Không nên giữ mọi payload trong RAM vô thời hạn. Nếu lệnh phải tồn tại qua lần restart của client hoặc server, hãy lưu bền vững ở tầng nghiệp vụ hoặc dùng message broker phù hợp.

## Kiểm thử chính sách reconnect

Nên kiểm tra các trường hợp sau:

1. Kết nối thành công ở lần thử đầu tiên.
2. Một số lỗi mạng tạm thời rồi kết nối thành công.
3. Lỗi kéo dài đến khi hết số lần retry.
4. Lỗi cấu hình hoặc xác thực không bị retry lặp lại.
5. Backoff tăng dần và không vượt giới hạn tối đa.
6. Jitter tạo thời điểm retry phân tán trong phạm vi cấu hình.
7. Timeout mỗi lần thử và deadline tổng đều có hiệu lực.
8. Nhiều request cùng phát hiện mất kết nối nhưng chỉ có một reconnect loop.
9. Queue đầy trong lúc offline được xử lý theo chính sách.
10. Kết nối phục hồi nhưng request cũ có kết quả chưa xác định được xử lý an toàn.

Dùng clock hoặc scheduler giả khi kiểm thử thời gian backoff để test chạy nhanh và ổn định. Không nên dùng Thread.sleep() thật trong unit test để chờ nhiều giây.

## Quan sát và vận hành

Các metric hữu ích gồm:

- Số lần mất kết nối và số lần reconnect thành công.
- Số lần retry theo loại lỗi.
- Thời gian từ lúc mất kết nối đến khi session sẵn sàng.
- Khoảng backoff được chọn và số lần retry đã dùng.
- Tỷ lệ hết retry budget hoặc deadline tổng.
- Số reconnect loop đồng thời.
- Độ sâu queue và số lệnh hết hạn khi offline.
- Số lần resume thành công/thất bại nếu implementation hỗ trợ resumption.

Log nên có connection ID, endpoint, attempt number, loại lỗi và trạng thái chuyển đổi. Tránh ghi token, credential hoặc payload nhạy cảm. Khi một client reconnect liên tục, hãy kiểm tra xem server có đang restart, proxy có timeout quá ngắn, credential có hết hạn hoặc chính sách backoff có bị reset quá sớm không.

## Checklist thiết kế

Trước khi triển khai reconnect, hãy trả lời:

1. Những loại lỗi nào được xem là tạm thời và có thể retry?
2. Mỗi lần kết nối có timeout bao lâu?
3. Backoff bắt đầu ở mức nào, tăng ra sao và giới hạn tối đa bao nhiêu?
4. Jitter được dùng để phân tán retry như thế nào?
5. Có bao nhiêu lần retry và deadline tổng là bao lâu?
6. Nhiều request có dùng chung một reconnect loop không?
7. Trong lúc offline, request mới được chờ, từ chối hay xếp hàng?
8. Request đang chạy có thể bị phát lại an toàn không?
9. Ứng dụng dùng reconnect session mới hay có hỗ trợ RSocket resumption?
10. Khi retry budget hết, hệ thống báo trạng thái và phục hồi thủ công như thế nào?

Một chính sách reconnect đáng tin cậy cần có phân loại lỗi, backoff, jitter, giới hạn số lần thử và deadline tổng. Khi kết hợp với quản lý một vòng reconnect dùng chung, queue hữu hạn và xử lý idempotent cho request chưa rõ kết quả, ứng dụng RSocket có thể phục hồi có kiểm soát mà không khuếch đại sự cố mạng hoặc server.

