# Phân biệt ngữ nghĩa Spring Retry với cửa sổ tỷ lệ lỗi Resilience4j

Spring Retry và Resilience4j Circuit Breaker đều có thể giúp ứng dụng chịu được lỗi tạm thời của dịch vụ phụ thuộc, nhưng chúng quan sát những điều khác nhau. Spring Retry quyết định có thực hiện lại một thao tác trong cùng một lần gọi hay không. Resilience4j Circuit Breaker quan sát kết quả của nhiều lời gọi qua một cửa sổ trượt, tính tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm, rồi quyết định có cho phép lời gọi tiếp theo đi qua hay không.

Khi triển khai **SPRING_CLOUD_CIRCUIT_BREAKER**, cần phân biệt rõ hai ngữ nghĩa này. Retry có thể giúp vượt qua một lỗi thoáng qua; Circuit Breaker giúp ngừng gửi thêm request khi phụ thuộc đang suy giảm. Dùng retry không đồng nghĩa đã có Circuit Breaker, và bật Circuit Breaker cũng không tự động thực hiện retry.

## 1. Hai cơ chế trả lời hai câu hỏi khác nhau

| Khía cạnh | Spring Retry | Resilience4j Circuit Breaker |
| --- | --- | --- |
| Câu hỏi chính | Có nên thử lại thao tác vừa thất bại không? | Có nên cho phép lời gọi mới đến phụ thuộc không? |
| Phạm vi quan sát | Các lần thử của một thao tác logic | Kết quả của nhiều lời gọi trong một cửa sổ |
| Đơn vị quyết định | Một lần gọi có thể có nhiều attempt | Một lời gọi được ghi nhận thành công, thất bại hoặc chậm |
| Điều kiện dừng | Hết số lần thử, gặp lỗi không được retry hoặc policy không cho thử tiếp | Mạch chuyển OPEN khi tỷ lệ đạt ngưỡng; chỉ thử lại có kiểm soát trong HALF_OPEN |
| Thời gian chờ | Backoff giữa các lần thử | Thời gian duy trì trạng thái OPEN trước khi cho phép thử phục hồi |
| Phản hồi cuối | Kết quả từ lần thử thành công hoặc phương thức recover khi hết retry | Kết quả lời gọi, fallback hoặc lỗi từ chối do mạch OPEN |

Ví dụ, dịch vụ Đơn hàng gọi dịch vụ Kho. Một request gặp lỗi kết nối thoáng qua. Spring Retry có thể thử lại request đó thêm hai lần. Nếu cả ba lần đều thất bại, thao tác kết thúc bằng lỗi hoặc phương thức recover. Resilience4j Circuit Breaker không tự gửi lại request; nó ghi nhận kết quả và có thể mở mạch sau khi đủ mẫu trong sliding window.

## 2. Spring Retry: số lần thử trong một lần gọi

Spring Retry cung cấp các abstraction như `RetryTemplate`, `RetryPolicy`, `BackOffPolicy` và annotation `@Retryable`. Một policy xác định exception nào được thử lại và khi nào dừng. Backoff xác định khoảng chờ giữa các attempt.

Với annotation, có thể cấu hình số lần thử và backoff:

~~~java
import org.springframework.retry.annotation.Backoff;
import org.springframework.retry.annotation.Recover;
import org.springframework.retry.annotation.Retryable;
import org.springframework.stereotype.Service;

@Service
public class InventoryClientService {
    @Retryable(
            retryFor = InventoryUnavailableException.class,
            noRetryFor = InventoryNotFoundException.class,
            maxAttempts = 3,
            backoff = @Backoff(
                    delay = 200,
                    multiplier = 2.0,
                    maxDelay = 1000
            )
    )
    public InventoryResult getInventory(String sku) {
        return inventoryClient.get(sku);
    }

    @Recover
    public InventoryResult recover(
            InventoryUnavailableException failure,
            String sku) {
        return InventoryResult.unavailable(sku);
    }
}
~~~

Ví dụ cần bật annotation processing bằng `@EnableRetry` trong cấu hình Spring và có dependency Spring Retry tương thích với phiên bản Spring đang dùng. `InventoryClient`, `InventoryResult` và các exception là kiểu nghiệp vụ minh họa.

Các điểm cần hiểu:

- `maxAttempts = 3` tính cả lần gọi đầu tiên, tức tối đa ba attempt tổng cộng, không phải ba lần retry cộng thêm lần đầu.
- `retryFor` chỉ định exception được phép thử lại.
- `noRetryFor` loại trừ lỗi không nên thử lại, chẳng hạn SKU không tồn tại.
- `@Backoff` đặt khoảng chờ giữa các attempt; với multiplier 2, thời gian chờ tăng theo cấp số nhân cho đến `maxDelay`.
- Khi hết attempt, Spring Retry tìm phương thức `@Recover` phù hợp nếu có. Nếu không có recover phù hợp, exception cuối cùng được truyền lên.

Retry phù hợp với lỗi tạm thời có khả năng tự phục hồi, chẳng hạn lỗi kết nối ngắn hoặc phản hồi 503. Không nên retry mọi exception. Lỗi đầu vào, lỗi xác thực hoặc thao tác không idempotent có thể gây tác dụng phụ nếu thực hiện lại.

Với annotation dựa trên proxy Spring, lời gọi nội bộ từ một phương thức sang phương thức `@Retryable` khác trong cùng object thường không đi qua proxy. Hãy gọi qua bean được Spring quản lý hoặc dùng `RetryTemplate` nếu cần kiểm soát rõ ràng tại điểm gọi.

## 3. RetryTemplate biểu diễn vòng lặp thử lại

Khi muốn điều khiển retry bằng code, có thể dùng `RetryTemplate`:

~~~java
import org.springframework.retry.support.RetryTemplate;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;

RetryTemplate retryTemplate = new RetryTemplate();

SimpleRetryPolicy retryPolicy = new SimpleRetryPolicy(
        3,
        Map.of(InventoryUnavailableException.class, true)
);
retryTemplate.setRetryPolicy(retryPolicy);

ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
backOff.setInitialInterval(200);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(1000);
retryTemplate.setBackOffPolicy(backOff);

InventoryResult result = retryTemplate.execute(
        context -> inventoryClient.get(sku),
        context -> InventoryResult.unavailable(sku)
);
~~~

Trong ví dụ, retry policy cho phép tối đa ba attempt đối với `InventoryUnavailableException`; backoff tăng thời gian chờ giữa các attempt. Callback thứ hai là recovery callback được dùng khi retry đã cạn. Cấu hình thực tế nên được tạo và quản lý như bean dùng chung thay vì khởi tạo lại cho từng request.

RetryTemplate quản lý trạng thái thử lại của thao tác hiện tại. Nó không tự duy trì một sliding window gồm các kết quả của nhiều request để tính failure rate như Resilience4j Circuit Breaker.

## 4. Resilience4j Circuit Breaker: tỷ lệ trên sliding window

Resilience4j Circuit Breaker ghi nhận kết quả của các lời gọi được bảo vệ. Sliding window có thể dựa trên số lượng lời gọi hoặc khoảng thời gian:

| Kiểu cửa sổ | Ý nghĩa |
| --- | --- |
| `COUNT_BASED` | Theo dõi một số lượng lời gọi gần nhất |
| `TIME_BASED` | Theo dõi kết quả trong một khoảng thời gian gần nhất |

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Trong cấu hình này:

- `slidingWindowSize: 20` theo dõi tối đa 20 lời gọi gần nhất.
- `minimumNumberOfCalls: 10` yêu cầu có ít nhất 10 kết quả trước khi tính tỷ lệ.
- `failureRateThreshold: 50` đặt ngưỡng mở mạch khi tỷ lệ lỗi đạt 50% trở lên sau khi đủ mẫu.
- `slowCallDurationThreshold: 2s` xác định lời gọi chậm.
- `slowCallRateThreshold: 60` đặt ngưỡng tỷ lệ lời gọi chậm.
- `waitDurationInOpenState: 10s` là thời gian chờ trong OPEN trước khi cho phép kiểm tra phục hồi.
- `permittedNumberOfCallsInHalfOpenState: 3` giới hạn số lời gọi thử nghiệm trong HALF_OPEN.

Ví dụ, sau khi có đủ 10 lời gọi, nếu 5 lời gọi thất bại thì failure rate là 50%. Mạch có thể chuyển từ CLOSED sang OPEN. Nếu 4 lời gọi thất bại và 2 lời gọi chậm thành công, failure rate là 40%, còn slow call rate là 20%; hai tỷ lệ được đánh giá riêng theo ngưỡng đã cấu hình.

Resilience4j Circuit Breaker không thực hiện lại lời gọi khi gặp exception. Nó quyết định có cho lời gọi mới đi qua hay từ chối nhanh khi mạch OPEN. Khi hết thời gian OPEN, mạch chuyển sang HALF_OPEN để kiểm tra khả năng phục hồi bằng một số lời gọi giới hạn.

## 5. Một request có ba attempt nhưng Circuit Breaker có thể chỉ ghi nhận một kết quả

Điểm khác biệt quan trọng xuất hiện khi kết hợp retry với Circuit Breaker. Nếu Retry nằm bên trong Circuit Breaker, Circuit Breaker bao quanh toàn bộ quá trình thử lại. Nó chỉ nhìn thấy kết quả cuối cùng của thao tác logic:

~~~mermaid
flowchart TD
    A[Một request nghiệp vụ] --> B[Circuit Breaker]
    B --> C[Spring Retry]
    C --> D[Attempt 1]
    D -->|Thất bại| E[Backoff]
    E --> F[Attempt 2]
    F -->|Thất bại| G[Backoff]
    G --> H[Attempt 3]
    H --> I[Kết quả cuối]
    I --> J[Circuit Breaker ghi nhận một kết quả]
~~~

Ví dụ, hai attempt đầu thất bại nhưng attempt thứ ba thành công. Retry trả kết quả thành công cho Circuit Breaker; Circuit Breaker ghi nhận một lời gọi logic thành công. Hai lỗi trung gian vẫn cần được log hoặc đo lường riêng nếu muốn quan sát chất lượng retry.

Nếu cả ba attempt thất bại, Circuit Breaker thường ghi nhận một lời gọi logic thất bại sau khi Retry kết thúc. Vì vậy, một request bên ngoài có ba attempt HTTP nhưng đóng góp một kết quả vào cửa sổ của Circuit Breaker.

Thứ tự này phù hợp khi muốn Circuit Breaker đo tỷ lệ thành công cuối cùng mà người gọi nhận được sau chính sách retry.

## 6. Nếu Circuit Breaker nằm bên trong Retry

Nếu mỗi attempt đi qua Circuit Breaker rồi Retry bọc bên ngoài, mỗi attempt có thể được ghi nhận như một lời gọi riêng:

~~~mermaid
flowchart TD
    A[Một request nghiệp vụ] --> B[Spring Retry]
    B --> C[Circuit Breaker]
    C --> D[Attempt 1]
    D -->|Thất bại| E[Retry backoff]
    E --> F[Circuit Breaker]
    F --> G[Attempt 2]
    G -->|Thất bại| H[Retry backoff]
    H --> I[Circuit Breaker]
    I --> J[Attempt 3]
~~~

Khi đó, một request nghiệp vụ có thể đóng góp nhiều kết quả lỗi vào sliding window. Mạch có thể mở ngay giữa chuỗi retry. Những attempt tiếp theo sẽ bị từ chối bằng `CallNotPermittedException` nếu Circuit Breaker đã OPEN.

Nếu Retry cũng thử lại `CallNotPermittedException`, nó có thể tiếp tục lặp trong lúc mạch vẫn OPEN mà không tạo thêm cơ hội phục hồi cho phụ thuộc. Vì vậy, cần cấu hình Retry chỉ xử lý exception phù hợp và loại trừ lỗi từ chối của Circuit Breaker.

Thứ tự này có thể hữu ích khi muốn Circuit Breaker phản ứng với từng lần thử thực tế, nhưng nó làm số liệu cửa sổ phản ánh attempt thay vì kết quả cuối của request nghiệp vụ. Hãy chọn có chủ đích và kiểm tra bằng metrics.

## 7. So sánh bằng một ví dụ số

Giả sử có 10 request nghiệp vụ. Mỗi request được Spring Retry thử tối đa ba lần. Trong 10 request:

- 6 request thành công ngay ở attempt đầu.
- 2 request thất bại ở attempt đầu nhưng thành công ở attempt thứ hai.
- 2 request thất bại cả ba attempt.

Kết quả khác nhau tùy thứ tự:

| Cách bọc | Số kết quả Circuit Breaker có thể ghi nhận | Số lỗi được ghi nhận |
| --- | ---: | ---: |
| Circuit Breaker ngoài, Retry trong | 10 kết quả cuối của 10 request | 2 lỗi cuối cùng |
| Retry ngoài, Circuit Breaker trong | 16 attempt | 8 attempt lỗi |

Số attempt ở cách thứ hai là 6 request thành công ngay ở attempt đầu, 4 attempt cho hai request thành công sau một lần retry và 6 attempt cho hai request thất bại hoàn toàn, tổng cộng 16 attempt. Số attempt lỗi là 2 lỗi đầu của hai request retry thành công cộng với 6 lỗi của hai request thất bại hoàn toàn, tức 8 lỗi.

Trong cả hai cách, có 2 request nghiệp vụ cuối cùng thất bại. Tuy nhiên, cửa sổ của Circuit Breaker nhìn thấy 2/10 lỗi ở cách thứ nhất và 8/16 lỗi ở cách thứ hai. Tỷ lệ lần lượt là 20% và 50%. Đây là lý do thứ tự bọc thay đổi ý nghĩa của failure rate.

Các số liệu trong ví dụ giả định Retry dừng ngay khi một attempt thành công và chưa có attempt nào bị Circuit Breaker từ chối. Nếu mạch chuyển OPEN giữa chuỗi retry, số lần thực thi thực tế còn phụ thuộc cách Retry phân loại `CallNotPermittedException`.

## 8. Recovery của Spring Retry và fallback của Circuit Breaker

Spring Retry dùng `@Recover` hoặc recovery callback của `RetryTemplate` khi retry đã hết. Resilience4j Circuit Breaker có thể dùng fallback khi lời gọi thất bại hoặc bị từ chối vì mạch OPEN. Hai cơ chế fallback có thời điểm kích hoạt khác nhau:

| Cơ chế | Khi chạy | Mục tiêu |
| --- | --- | --- |
| Spring Retry `@Recover` | Sau khi retry policy không cho thử thêm | Cung cấp kết quả hoặc xử lý sau khi các attempt đã cạn |
| Circuit Breaker fallback | Khi thao tác được bảo vệ ném lỗi hoặc mạch từ chối lời gọi | Cung cấp phản hồi thay thế trong lúc phụ thuộc lỗi hoặc đang bị ngắt |

Nếu Retry nằm trong Circuit Breaker, recovery của Spring Retry có thể biến các attempt thất bại thành một kết quả bình thường trước khi Circuit Breaker nhận kết quả. Khi đó Circuit Breaker có thể ghi nhận thành công nếu recover trả về giá trị. Nếu muốn Circuit Breaker ghi nhận lỗi cuối cùng, hãy để exception truyền ra khỏi Retry hoặc thiết kế recovery theo cách giữ lại tín hiệu lỗi phù hợp.

Không nên để cả hai lớp fallback cùng trả một giá trị mặc định mà không ghi nhận nguyên nhân. Nếu không, dashboard có thể cho thấy API thành công dù dịch vụ phụ thuộc liên tục lỗi và mọi request đều đang dùng dữ liệu dự phòng.

## 9. Spring Retry không thay thế sliding window

Spring Retry chủ yếu quyết định có thử lại một thao tác hay không dựa trên policy và context của thao tác đó. Một retry policy thường giới hạn số attempt, loại exception được retry và khoảng backoff. Nó không mặc định tính tỷ lệ lỗi của 20 lời gọi gần nhất hoặc tỷ lệ lời gọi chậm trong 10 giây như Resilience4j Circuit Breaker.

Một số phiên bản Spring Retry có policy mang tên Circuit Breaker để ngăn các lần thử trong một khoảng thời gian sau khi thất bại. Tuy nhiên, không nên đồng nhất cơ chế policy đó với mô hình sliding-window failure-rate của Resilience4j. Cần đọc đúng API và ngữ nghĩa của phiên bản đang dùng thay vì suy ra từ tên gọi.

Nếu yêu cầu là:

- Thử lại tối đa ba lần khi gặp lỗi kết nối ngắn: dùng Spring Retry hoặc Resilience4j Retry.
- Mở mạch khi ít nhất 50% trong 20 lời gọi gần nhất thất bại: dùng Resilience4j Circuit Breaker với COUNT_BASED sliding window.
- Mở mạch khi tỷ lệ lời gọi chậm trong 10 giây vượt ngưỡng: dùng TIME_BASED sliding window và cấu hình slow-call threshold.
- Vừa thử lại lỗi tạm thời, vừa ngừng gọi khi phụ thuộc suy giảm kéo dài: kết hợp Retry và Circuit Breaker với thứ tự, timeout và phân loại exception rõ ràng.

## 10. Chọn lỗi nào được retry và lỗi nào được ghi nhận

Retry và Circuit Breaker cần chính sách exception thống nhất:

| Loại lỗi | Spring Retry | Resilience4j Circuit Breaker |
| --- | --- | --- |
| Lỗi kết nối tạm thời | Có thể retry với số lần giới hạn và backoff | Ghi nhận lỗi nếu exception không bị ignore |
| HTTP 503 | Có thể retry nếu phụ thuộc có khả năng phục hồi nhanh | Thường ghi nhận là lỗi phụ thuộc |
| HTTP 404 do tài nguyên không tồn tại | Thường không retry | Có thể ignore nếu là kết quả nghiệp vụ bình thường |
| HTTP 400 do request sai | Không retry | Thường ignore để không làm tăng failure rate phụ thuộc |
| Timeout | Có thể retry nếu thao tác an toàn và còn ngân sách thời gian | Thường ghi nhận lỗi hoặc slow call tùy thời điểm hoàn tất |
| CallNotPermittedException | Không nên retry | Là tín hiệu Circuit Breaker đang OPEN, không phải lỗi mới của phụ thuộc |
| BulkheadFullException hoặc RequestNotPermitted | Không nên retry ngay khi giới hạn nội bộ đã đầy | Thường ignore trong failure rate của phụ thuộc và theo dõi riêng |

Không nên retry các thao tác ghi không idempotent nếu chưa có idempotency key hoặc cơ chế chống xử lý trùng. Ví dụ, timeout khi gửi lệnh thanh toán không chứng minh giao dịch chưa được xử lý; retry có thể tạo giao dịch thứ hai.

## 11. Ngân sách thời gian và số lần thử

Retry làm tăng thời gian hoàn tất vì mỗi attempt có thể tiêu tốn thời gian gọi và khoảng backoff. Nếu timeout của một attempt là 1 giây và retry tối đa ba attempt, tổng thời gian có thể vượt 3 giây khi cộng cả backoff. Cần tính ngân sách tổng thể:

$$
T_{total} \approx \sum_{i=1}^{n} T_{attempt_i}
 + \sum_{i=1}^{n-1} T_{backoff_i}
$$

Tổng thời gian này cần nằm trong deadline của request bên ngoài. Không nên đặt timeout của API ngắn hơn tổng thời gian retry dự kiến, vì client có thể bỏ cuộc trong khi các attempt vẫn tiếp tục chạy.

Circuit Breaker cũng cần phối hợp với timeout. Nếu phụ thuộc treo vô thời hạn, Circuit Breaker không thể ghi nhận kết quả chưa hoàn tất để cập nhật cửa sổ. Hãy đặt timeout ở HTTP client hoặc TimeLimiter để thao tác kết thúc và phát ra kết quả lỗi có thể quan sát.

Khi mạch OPEN, không nên để Retry tiếp tục thử cùng phụ thuộc. Hãy loại trừ `CallNotPermittedException` khỏi danh sách retry và để Circuit Breaker từ chối nhanh. Retry chỉ nên áp dụng cho lỗi có thể phục hồi trong ngân sách thời gian.

## 12. Quy trình kết hợp Spring Retry và Resilience4j

Khi một phụ thuộc cần cả retry lẫn circuit breaker, hãy thực hiện:

1. Xác định lỗi tạm thời nào có thể retry và lỗi nghiệp vụ nào phải trả ngay.
2. Chọn số attempt tối đa, backoff và timeout sao cho không vượt deadline của request.
3. Chọn sliding window COUNT_BASED hoặc TIME_BASED cho Circuit Breaker dựa trên lưu lượng.
4. Quyết định Circuit Breaker đo kết quả cuối của một request hay đo từng attempt bằng cách xác định thứ tự bọc.
5. Nếu Retry nằm trong Circuit Breaker, xác định recovery có biến lỗi cuối thành kết quả bình thường hay không.
6. Nếu Circuit Breaker nằm trong Retry, loại trừ `CallNotPermittedException` khỏi retry để tránh thử lại khi mạch OPEN.
7. Phân loại lỗi từ Rate Limiter và Bulkhead để không nhầm quá tải nội bộ với lỗi của phụ thuộc.
8. Theo dõi riêng số request nghiệp vụ, số attempt, số lỗi từng attempt, failure rate, slow call rate và số lần fallback.
9. Kiểm thử tình huống thành công sau retry, hết retry, mạch OPEN, timeout và phục hồi HALF_OPEN.

Spring Retry và Resilience4j Circuit Breaker có thể phối hợp nhưng không có cùng ngữ nghĩa. Retry điều khiển các attempt trong một thao tác; Circuit Breaker dùng sliding window để đánh giá sức khỏe của phụ thuộc qua nhiều lời gọi. Chọn đúng thứ tự và chính sách exception giúp hệ thống vừa vượt qua lỗi tạm thời, vừa ngừng tạo tải khi dịch vụ thực sự suy giảm.
