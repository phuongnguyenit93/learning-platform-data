# Tùy chỉnh RetryPolicy, thời gian mở mạch và RetryListener

Trong hệ thống Spring Cloud, một lời gọi đến dịch vụ phụ thuộc có thể thất bại tạm thời do mất kết nối, timeout hoặc dịch vụ đang quá tải. Retry cho phép thử lại một số lỗi có khả năng phục hồi. Circuit breaker quan sát kết quả lời gọi và tạm ngừng gửi yêu cầu khi phụ thuộc liên tục lỗi. Hai cơ chế bổ sung cho nhau nhưng có mục tiêu khác nhau: RetryPolicy quyết định có nên thử lại một lời gọi; thời gian OPEN xác định khi nào circuit breaker được thử phục hồi; RetryListener quan sát vòng đời của các lần thử.

Khi tùy chỉnh chúng, cần giới hạn số lần thử, chọn đúng loại exception, đặt backoff phù hợp và tránh retry trong lúc circuit breaker đang OPEN. Nếu retry quá nhiều hoặc không có giới hạn thời gian, chính cơ chế phục hồi có thể làm tăng tải và kéo dài sự cố.

## Phân biệt RetryPolicy, thời gian OPEN và RetryListener

Ba thành phần xử lý ba câu hỏi riêng:

| Thành phần | Câu hỏi | Trách nhiệm |
|---|---|---|
| RetryPolicy | Có được thử lại sau lỗi này không? | Quyết định điều kiện retry, số lần thử và loại lỗi được phép thử lại. |
| Thời gian OPEN của circuit breaker | Mạch cần chờ bao lâu trước khi thử phục hồi? | Giữ lời gọi bị từ chối trong một khoảng thời gian, sau đó cho phép thăm dò ở HALF_OPEN. |
| RetryListener | Điều gì xảy ra trong vòng đời retry? | Ghi nhận bắt đầu, lỗi từng lần thử, kết quả cuối và số lần thử. |

RetryPolicy không thay thế circuit breaker. Một lời gọi có thể được thử lại vài lần nhưng vẫn thất bại; circuit breaker có thể ghi nhận kết quả cuối cùng và mở mạch nếu tỷ lệ lỗi vượt ngưỡng. Ngược lại, khi mạch đang OPEN, circuit breaker từ chối lời gọi ngay; retry lặp lại trong trạng thái này thường không giúp phụ thuộc phục hồi.

Trong ví dụ dưới đây dùng Spring Retry để minh họa `RetryPolicy` và `RetryListener`, kết hợp Resilience4j làm circuit breaker. Đây là hai thư viện có API và cấu hình riêng; cần dùng phiên bản tương thích với Spring Boot và Spring Cloud của dự án.

## Tùy chỉnh RetryPolicy theo loại lỗi

Spring Retry cung cấp `RetryPolicy` để quyết định một thao tác có thể tiếp tục thử hay không. Có thể dùng policy có sẵn như `SimpleRetryPolicy` để giới hạn số lần thử và chọn các exception được phép retry.

Ví dụ, lời gọi đọc tồn kho chỉ được thử lại khi gặp lỗi kết nối hoặc timeout. Các lỗi nghiệp vụ như mã SKU không hợp lệ hoặc sản phẩm không tồn tại không nên retry.

~~~java
import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.HashMap;
import java.util.Map;

import org.springframework.retry.policy.SimpleRetryPolicy;

Map<Class<? extends Throwable>, Boolean> retryable =
        new HashMap<>();

retryable.put(ConnectException.class, true);
retryable.put(SocketTimeoutException.class, true);
retryable.put(IOException.class, true);
retryable.put(InvalidSkuException.class, false);
retryable.put(ProductNotFoundException.class, false);

SimpleRetryPolicy retryPolicy =
        new SimpleRetryPolicy(3, retryable, true);
~~~

Trong ví dụ, `3` là số lần thực thi tối đa, bao gồm lần gọi đầu tiên. Tham số `true` yêu cầu policy xét cause chain khi phân loại ngoại lệ, hữu ích khi HTTP client hoặc adapter bọc lỗi gốc trong một exception khác. Hãy kiểm tra constructor phù hợp với phiên bản Spring Retry đang dùng.

Khi cấu hình danh sách retryable, cần xác định rõ các loại lỗi còn lại. Không nên retry mọi `RuntimeException`, vì nhóm này có thể bao gồm lỗi lập trình, lỗi đầu vào hoặc vi phạm quy tắc nghiệp vụ. Retry chỉ có ý nghĩa với lỗi có khả năng tự phục hồi khi thử lại sau một khoảng thời gian.

### Khi nào cần tự triển khai RetryPolicy?

Policy có sẵn phù hợp với phần lớn trường hợp giới hạn số lần thử và phân loại exception. Có thể tự triển khai `RetryPolicy` khi điều kiện retry phụ thuộc vào ngữ cảnh, chẳng hạn:

- Chỉ retry một số mã lỗi từ dịch vụ đối tác.
- Dừng retry khi đã hết deadline của request.
- Giới hạn số lần thử khác nhau theo loại thao tác.
- Không retry khi request đã bị caller hủy.
- Chỉ retry khi thao tác có idempotency key.

Một policy tùy chỉnh cần quản lý trạng thái qua `RetryContext`. Các phương thức chính của hợp đồng gồm:

| Phương thức | Vai trò |
|---|---|
| `open(parent)` | Tạo context cho lần thực thi retry và liên kết context cha nếu có. |
| `canRetry(context)` | Quyết định có cho phép tiếp tục thực thi hay không. |
| `registerThrowable(context, throwable)` | Ghi nhận exception của lần thử vừa thất bại. |
| `close(context)` | Giải phóng hoặc hoàn tất context sau khi kết thúc. |

Nếu tự viết policy, hãy đảm bảo `canRetry` luôn có giới hạn rõ ràng và không cho phép retry vô hạn. Nên dùng lại `SimpleRetryPolicy` hoặc các policy có sẵn khi chúng đáp ứng yêu cầu; một policy tự triển khai làm tăng trách nhiệm kiểm thử và bảo trì.

## Kết hợp RetryPolicy với BackOffPolicy

RetryPolicy trả lời có được thử lại hay không. BackOffPolicy quyết định khoảng chờ trước lần thử tiếp theo. Hai phần này nên được cấu hình riêng để dễ hiểu và điều chỉnh.

Ví dụ dùng `RetryTemplate` với tối đa ba lần thực thi và exponential backoff:

~~~java
import java.time.Duration;

import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;

RetryTemplate retryTemplate = new RetryTemplate();
retryTemplate.setRetryPolicy(retryPolicy);

ExponentialBackOffPolicy backOffPolicy =
        new ExponentialBackOffPolicy();
backOffPolicy.setInitialInterval(100);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(1_000);

retryTemplate.setBackOffPolicy(backOffPolicy);
~~~

Với cấu hình này, khoảng chờ tăng theo cấp số nhân: khoảng 100 ms, 200 ms rồi 400 ms, tối đa không vượt 1.000 ms. Các giá trị là ví dụ; cần căn cứ vào thời gian phản hồi của phụ thuộc và deadline của request.

Trong hệ thống nhiều replica, backoff có jitter giúp các client không đồng loạt retry cùng một thời điểm sau khi phụ thuộc phục hồi. Nếu phiên bản Spring Retry đang dùng cung cấp random/exponential backoff policy, có thể chọn policy đó hoặc bổ sung jitter theo cơ chế phù hợp. Không nên tự tạo vòng lặp sleep trong mã nghiệp vụ để thay thế BackOffPolicy.

## Sử dụng RetryTemplate và fallback sau khi hết lần thử

Có thể dùng `RetryTemplate.execute` để thực thi thao tác và cung cấp `RecoveryCallback` khi số lần thử đã hết:

~~~java
import org.springframework.retry.RecoveryCallback;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.support.RetryTemplate;

public Inventory findInventory(String sku) {
    RetryCallback<Inventory, RuntimeException> operation =
            context -> inventoryClient.fetch(sku);

    RecoveryCallback<Inventory> recovery =
            context -> Inventory.unavailable(sku);

    return retryTemplate.execute(operation, recovery);
}
~~~

`Inventory` và `Inventory.unavailable` là kiểu dữ liệu minh họa. Trong ứng dụng thực tế, fallback cần thể hiện rõ dữ liệu không sẵn sàng hoặc dữ liệu cache có độ mới xác định. Không nên trả số lượng tồn kho mặc định như thể đã được dịch vụ nguồn xác nhận.

RecoveryCallback chỉ chạy khi policy kết thúc retry mà thao tác vẫn thất bại. Nếu exception không được policy cho phép retry, thao tác có thể kết thúc ngay và đi tới recovery. Nếu cần phân biệt lỗi nghiệp vụ với lỗi phụ thuộc, hãy xử lý chúng theo hợp đồng API thay vì trả cùng một kết quả mặc định cho mọi exception.

## Tùy chỉnh thời gian circuit breaker ở trạng thái OPEN

Trong Resilience4j, `waitDurationInOpenState` xác định khoảng thời gian circuit breaker giữ trạng thái OPEN trước khi chuyển sang HALF_OPEN để thử phục hồi. Đây không phải thời gian chờ giữa hai lần retry.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

Với cấu hình trên, mạch giữ OPEN trong 15 giây. Sau khoảng chờ, nó chuyển sang HALF_OPEN và cho phép tối đa ba lời gọi thăm dò. Nếu các lời gọi thăm dò đạt yêu cầu, circuit breaker trở lại CLOSED; nếu tiếp tục lỗi hoặc chậm vượt ngưỡng, mạch mở lại.

Có thể cấu hình thời gian OPEN bằng Java khi xây dựng instance:

~~~java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .waitDurationInOpenState(Duration.ofSeconds(15))
        .permittedNumberOfCallsInHalfOpenState(3)
        .build();
~~~

Chọn thời gian OPEN theo khả năng phục hồi của phụ thuộc:

- Quá ngắn: ứng dụng thử lại liên tục khi dịch vụ chưa kịp hồi phục, gây thêm tải.
- Quá dài: dịch vụ đã khỏe nhưng caller vẫn bị từ chối lâu hơn cần thiết.
- Phù hợp: đủ thời gian để phụ thuộc giải phóng tài nguyên hoặc phục hồi, đồng thời không làm gián đoạn chức năng quá lâu.

Với hệ thống có nhiều replica, thời gian OPEN thường được quản lý trong từng instance circuit breaker của mỗi tiến trình. Các replica có thể chuyển trạng thái ở thời điểm khác nhau; nếu cần đồng bộ quota hoặc trạng thái toàn cụm, phải dùng cơ chế phân tán phù hợp thay vì giả định circuit breaker cục bộ tự chia sẻ trạng thái.

## Phân biệt thời gian OPEN và backoff của retry

Hai khoảng chờ này dễ bị nhầm vì đều làm lời gọi chờ trước khi thử tiếp:

| Thời gian | Nằm ở đâu? | Điều gì xảy ra khi hết thời gian? |
|---|---|---|
| Retry backoff | Giữa các lần thực thi của cùng một thao tác retry. | RetryTemplate thực hiện lần thử tiếp theo nếu RetryPolicy còn cho phép. |
| `waitDurationInOpenState` | Trong vòng đời circuit breaker đang OPEN. | Circuit breaker cho phép thử phục hồi ở HALF_OPEN. |
| Timeout của lời gọi | Bao quanh một lần thực thi. | Lời gọi bị kết thúc theo chính sách timeout; có thể được ghi nhận là lỗi. |

Ví dụ, RetryTemplate có thể thử ba lần với backoff 100 ms và 200 ms. Nếu toàn bộ chuỗi vẫn thất bại, circuit breaker ghi nhận kết quả thất bại và chuyển OPEN khi đạt ngưỡng. Mạch giữ OPEN 15 giây rồi mới cho phép thăm dò. Retry backoff không rút ngắn thời gian OPEN, và thời gian OPEN cũng không quyết định số lần thử của RetryTemplate.

## Gắn RetryListener để quan sát vòng đời retry

Spring Retry cung cấp `RetryListener` để theo dõi thao tác trước, trong và sau các lần thử. Listener hữu ích cho log, metrics và chẩn đoán; nó không quyết định thay cho RetryPolicy có được thử lại hay không.

Các callback chính:

| Callback | Thời điểm | Cách sử dụng |
|---|---|---|
| `open` | Khi bắt đầu một phiên retry. | Gắn ngữ cảnh hoặc ghi nhận thao tác bắt đầu. |
| `onError` | Sau mỗi lần thử thất bại. | Ghi loại lỗi và số lần thử hiện tại. |
| `close` | Khi phiên retry kết thúc. | Ghi kết quả cuối và giải phóng tài nguyên theo dõi. |

Ví dụ listener:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

public class InventoryRetryListener implements RetryListener {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryRetryListener.class);

    @Override
    public <T, E extends Throwable> boolean open(
            RetryContext context,
            RetryCallback<T, E> callback) {
        log.debug("Starting inventory retry operation");
        return true;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        log.warn(
                "Inventory attempt {} failed with {}",
                context.getRetryCount(),
                throwable.getClass().getSimpleName()
        );
    }

    @Override
    public <T, E extends Throwable> void close(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {
        if (throwable == null) {
            log.debug(
                    "Inventory retry operation succeeded after {} retries",
                    context.getRetryCount()
            );
        } else {
            log.error(
                    "Inventory retry operation exhausted after {} retries",
                    context.getRetryCount(),
                    throwable
            );
        }
    }
}
~~~

Đăng ký listener với RetryTemplate:

~~~java
retryTemplate.registerListener(new InventoryRetryListener());
~~~

Trong ví dụ, `onError` được gọi cho từng lần thực thi thất bại. `close` nhận exception cuối cùng nếu phiên retry kết thúc bằng lỗi; nếu thao tác thành công, throwable có thể là null. Số đếm trong RetryContext thường biểu thị số lần retry đã xảy ra, không nhất thiết bằng tổng số lần thực thi; khi hiển thị metrics, hãy đặt tên chỉ số rõ ràng để tránh nhầm lẫn.

Listener nên giữ callback ngắn. Tránh gọi HTTP, truy vấn cơ sở dữ liệu hoặc thực hiện xử lý blocking trong listener, vì điều đó kéo dài thời gian retry và có thể tạo thêm một phụ thuộc trên đường xử lý. Không ghi token, dữ liệu cá nhân hoặc toàn bộ payload nhạy cảm vào log.

## Đăng ký listener và metrics

Có thể đăng ký một hoặc nhiều listener tùy nhu cầu:

~~~java
RetryTemplate retryTemplate = new RetryTemplate();
retryTemplate.setRetryPolicy(retryPolicy);
retryTemplate.setBackOffPolicy(backOffPolicy);
retryTemplate.registerListener(new InventoryRetryListener());
~~~

Trong hệ thống cần metrics, listener có thể tăng bộ đếm số lần thử lại hoặc số phiên retry kết thúc bằng lỗi. Nên dùng các nhãn có miền giá trị giới hạn như dependency, operation và exception family. Không dùng SKU, user ID, order ID hoặc request ID làm nhãn metrics vì cardinality sẽ tăng theo lưu lượng.

Các chỉ số hữu ích:

- Số phiên retry bắt đầu.
- Số lần thử lại bổ sung trên mỗi phiên.
- Số phiên thành công sau retry.
- Số phiên cạn số lần thử và đi tới recovery.
- Độ trễ tổng của thao tác gồm cả backoff.
- Phân bố exception dẫn đến retry.

Không nên chỉ đo số retry mà bỏ qua số phiên thành công cuối cùng. Retry tăng có thể giúp phục hồi lỗi thoáng qua, nhưng cũng có thể là dấu hiệu phụ thuộc đang suy giảm hoặc timeout được đặt quá thấp.

## Phối hợp RetryTemplate với CircuitBreaker

Thứ tự bọc retry và circuit breaker ảnh hưởng đến số mẫu mà circuit breaker ghi nhận.

**Retry bên trong circuit breaker:** circuit breaker bao quanh toàn bộ chuỗi retry. Một thao tác logic được ghi nhận theo kết quả cuối sau khi retry thành công hoặc cạn lần thử. Cách này giảm việc một thao tác tạo nhiều mẫu failure trong cửa sổ, nhưng circuit breaker chỉ nhận biết thất bại sau khi retry hoàn tất.

**Retry bên ngoài circuit breaker:** mỗi lần thử có thể đi qua circuit breaker. Khi mạch OPEN, lần thử tiếp theo bị từ chối nhanh. Cách này giúp circuit breaker nhìn thấy các lần lỗi sớm hơn, nhưng cần phân loại `CallNotPermittedException` để retry không lặp lại vô ích khi mạch đang mở.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A[Yêu cầu nghiệp vụ] --> B[RetryTemplate]
    B --> C[Circuit Breaker]
    C --> D[HTTP client]
    D -->|Thành công| E[Kết quả]
    D -->|Lỗi| F[RetryPolicy đánh giá]
    F -->|Còn lần thử| G[Backoff]
    G --> B
    F -->|Hết lần thử| H[Recovery / fallback]
    C -->|OPEN| I[Từ chối nhanh]
~~~

Sơ đồ thể hiện một cách phối hợp minh họa. Khi triển khai, hãy quyết định rõ circuit breaker đang thống kê từng lần gọi vật lý hay một thao tác logic gồm nhiều lần thử. Với phụ thuộc đang quá tải, retry cần rất thận trọng; nếu mọi caller cùng retry theo cùng nhịp, lưu lượng có thể tăng mạnh ngay khi dịch vụ bắt đầu phục hồi.

Không retry các lỗi từ chối do circuit breaker đang OPEN. Nếu retry policy cho phép thử lại `CallNotPermittedException`, mỗi lần thử chỉ tạo thêm một lần từ chối mà không tiếp cận được dịch vụ. Hãy loại exception này khỏi nhóm retryable hoặc đặt circuit breaker ở vị trí phù hợp để lỗi từ chối không bị retry.

## Đặt deadline tổng cho toàn bộ retry

Số lần thử và backoff phải nằm trong ngân sách thời gian của request. Nếu mỗi lần gọi có timeout hai giây, retry ba lần và backoff tổng một giây, thời gian xử lý có thể vượt bảy giây, chưa tính thời gian xử lý ở các tầng khác.

Trước khi bật retry, hãy tính:

- Timeout tối đa của mỗi lần gọi.
- Số lần thực thi tối đa, bao gồm lần đầu.
- Tổng thời gian backoff giữa các lần thử.
- Thời gian còn lại cho xử lý và phản hồi ở tầng trên.

Nếu request có deadline 2 giây, có thể cần giới hạn mỗi lần gọi còn 500 ms và chỉ cho phép một lần retry ngắn. Khi deadline đã hết, không nên tiếp tục retry dù policy vẫn còn lượt. Với thao tác ghi, chỉ retry khi có idempotency key hoặc cơ chế xác định trạng thái để tránh giao dịch trùng.

## Kiểm thử RetryPolicy, thời gian OPEN và RetryListener

Nên kiểm thử ba phần riêng trước khi kiểm thử kết hợp:

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Gặp ConnectException được phép retry | RetryPolicy cho phép lần thử tiếp theo nếu còn số lần. |
| Gặp InvalidSkuException bị loại | Không thực hiện retry không cần thiết. |
| Đạt maxAttempts | RetryTemplate dừng và gọi recovery nếu được cấu hình. |
| Backoff tăng theo cấu hình | Khoảng chờ giữa các lần thử tăng và không vượt giới hạn. |
| Listener nhận lỗi từng lần thử | onError được gọi với exception và retry count phù hợp. |
| Phiên retry kết thúc thành công | close nhận kết quả không có exception cuối. |
| Phiên retry cạn lượt | close nhận exception cuối cùng và recovery được gọi. |
| Circuit breaker chuyển OPEN | Lời gọi tiếp theo bị từ chối trong khoảng waitDurationInOpenState. |
| Hết thời gian OPEN | Mạch chuyển HALF_OPEN và cho phép số lời gọi thăm dò đã cấu hình. |
| Retry gặp CallNotPermittedException | Không retry lặp lại khi mạch đang OPEN. |
| Request hết deadline | Dừng retry và trả kết quả theo chính sách timeout. |

Dùng clock hoặc scheduler giả lập khi kiểm thử thời gian để tránh chờ thật. Kiểm tra cả số lần thực thi, thời gian chờ, số lần listener được gọi và trạng thái circuit breaker. Không chỉ kiểm tra giá trị fallback cuối vì cùng một fallback có thể xuất phát từ timeout, lỗi nghiệp vụ hoặc mạch OPEN.

## Quy trình triển khai

1. Chọn exception tạm thời có thể retry và loại trừ lỗi nghiệp vụ, lỗi xác thực cùng lỗi không thể phục hồi.
2. Cấu hình RetryPolicy với số lần thực thi tối đa rõ ràng.
3. Cấu hình BackOffPolicy có giới hạn và cân nhắc jitter khi nhiều replica cùng retry.
4. Đặt deadline tổng cho chuỗi thử lại và timeout riêng cho từng lần gọi.
5. Cấu hình `waitDurationInOpenState` theo thời gian phụ thuộc cần phục hồi.
6. Chọn số lời gọi thăm dò HALF_OPEN phù hợp với năng lực phụ thuộc.
7. Đăng ký RetryListener để quan sát lỗi từng lần thử và kết quả cuối.
8. Chọn thứ tự retry/circuit breaker và loại `CallNotPermittedException` khỏi retry.
9. Kiểm thử lỗi tạm thời, lỗi nghiệp vụ, hết lượt, OPEN/HALF_OPEN, timeout và cancellation.

RetryPolicy quyết định có thử lại một lỗi hay không; BackOffPolicy điều chỉnh thời gian giữa các lần thử; `waitDurationInOpenState` quyết định khi nào circuit breaker thử phục hồi; RetryListener cung cấp tín hiệu quan sát cho từng phiên retry. Khi giới hạn số lần thử, phân loại đúng exception và phối hợp chúng trong deadline của request, ứng dụng Spring Cloud có thể xử lý lỗi tạm thời mà không khuếch đại tải lên dịch vụ phụ thuộc.

