# Phân biệt BulkheadFullException với CallNotPermittedException

Trong ứng dụng Spring Cloud dùng Resilience4j, `Bulkhead` và `CircuitBreaker` đều có thể từ chối một lời gọi trước khi mã gọi dịch vụ phụ thuộc được thực thi. Tuy nhiên, hai cơ chế từ chối vì những lý do khác nhau và phát ra exception khác nhau:

- `BulkheadFullException` cho biết giới hạn tài nguyên đồng thời hoặc hàng đợi của bulkhead đã đạt mức cho phép. Ứng dụng hiện không nhận thêm công việc ở khu vực được bảo vệ.
- `CallNotPermittedException` cho biết circuit breaker không cấp quyền thực hiện lời gọi, thường vì breaker đang `OPEN` hoặc không còn lượt gọi thăm dò được phép trong `HALF_OPEN`.

Phân biệt hai exception giúp gateway chọn fallback phù hợp, tránh retry làm tăng tải và giữ cho thống kê circuit breaker phản ánh đúng tình trạng của dịch vụ phụ thuộc. Bulkhead kiểm soát số công việc được chạy cùng lúc; circuit breaker đánh giá kết quả các lời gọi gần đây để quyết định có tiếp tục gọi hay không.

## 1. Hai exception biểu thị hai điều kiện từ chối khác nhau

| Exception | Package Resilience4j | Cơ chế phát sinh | Lời gọi đến dịch vụ đích? |
|---|---|---|---|
| `BulkheadFullException` | `io.github.resilience4j.bulkhead.BulkheadFullException` | Không lấy được permit hoặc không thể đưa tác vụ vào hàng đợi của bulkhead | Không, lời gọi bị từ chối tại bulkhead |
| `CallNotPermittedException` | `io.github.resilience4j.circuitbreaker.CallNotPermittedException` | Circuit breaker không cấp permission để thực thi supplier | Không, supplier được bảo vệ không chạy |

Hai exception đều có thể xuất hiện trong fallback của Spring Cloud CircuitBreaker, nhưng ý nghĩa vận hành khác nhau. `BulkheadFullException` thường báo hiệu áp lực đồng thời hoặc giới hạn hàng đợi tại tiến trình gọi. `CallNotPermittedException` báo hiệu chính sách circuit breaker đang chặn lời gọi vì trạng thái hoặc số permission hiện có.

Một request bị từ chối không có nghĩa dịch vụ đích vừa trả lỗi. Trong cả hai trường hợp, lần gọi cụ thể có thể chưa gửi bất kỳ request HTTP nào đến backend. Vì vậy, không nên ghi cả hai thành HTTP 5xx từ dịch vụ đích hoặc gộp chúng vào cùng một loại lỗi mạng.

## 2. Khi nào BulkheadFullException xuất hiện?

Bulkhead giới hạn lượng công việc có thể đi vào một khu vực được bảo vệ. Mục đích là ngăn một phụ thuộc chậm hoặc một nhóm tác vụ chiếm hết thread, connection hoặc tài nguyên của toàn bộ ứng dụng.

Resilience4j có hai kiểu bulkhead thường dùng:

- **Semaphore bulkhead:** giới hạn số lời gọi đồng thời bằng permit. Khi không còn permit và lời gọi không được phép chờ thêm, bulkhead từ chối lời gọi bằng `BulkheadFullException`. Nếu cấu hình `maxWaitDuration` lớn hơn 0, lời gọi có thể chờ permit trong khoảng thời gian đó; nếu không lấy được permit trước khi hết thời gian chờ, nó bị từ chối.
- **Thread pool bulkhead:** dùng thread pool và hàng đợi riêng để thực thi tác vụ bất đồng bộ. Khi thread pool và hàng đợi đều không thể nhận thêm công việc, tác vụ mới bị từ chối; Resilience4j biểu diễn tình trạng đầy bằng `BulkheadFullException`.

Ví dụ, bulkhead semaphore của dịch vụ tồn kho chỉ cho phép 20 lời gọi đồng thời:

```yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0
```

Nếu 20 lời gọi đang giữ permit, lời gọi thứ 21 bị từ chối ngay vì `maxWaitDuration` bằng 0. Dịch vụ tồn kho có thể vẫn hoạt động; ứng dụng gọi đang chủ động giới hạn số request được phép đi qua để bảo vệ tài nguyên.

Với thread pool bulkhead, có thể cấu hình riêng kích thước pool và hàng đợi:

```yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 5
        maxThreadPoolSize: 10
        queueCapacity: 20
        keepAliveDuration: 20ms
```

Trong ví dụ này, thread pool có thể tăng đến 10 thread và hàng đợi chứa tối đa 20 tác vụ. Khi pool đã đạt giới hạn và hàng đợi đầy, tác vụ mới không được nhận. Giá trị thực tế cần dựa trên thời gian xử lý, tài nguyên CPU, số connection và tải mà backend có thể chịu được.

Bulkhead không đo tỷ lệ lỗi để quyết định mở mạch. Nó chỉ giới hạn mức công việc được chấp nhận. `BulkheadFullException` do đó thường là tín hiệu quá tải hoặc từ chối admission ở phía ứng dụng gọi, không phải bằng chứng rằng backend đã trả lỗi.

## 3. Khi nào CallNotPermittedException xuất hiện?

Circuit breaker theo dõi kết quả lời gọi và trạng thái của phụ thuộc. Khi ở `CLOSED`, breaker cho phép supplier chạy và ghi nhận kết quả. Khi tỷ lệ lỗi hoặc lời gọi chậm vượt ngưỡng sau khi có đủ mẫu, breaker chuyển sang `OPEN`.

Ở trạng thái `OPEN`, breaker từ chối lời gọi mới ngay lập tức. Resilience4j ném `CallNotPermittedException` và không gọi supplier. Sau thời gian chờ, breaker có thể chuyển sang `HALF_OPEN` để cho phép một số lời gọi thăm dò. Khi các lượt thăm dò đã được cấp hết, lời gọi bổ sung cũng có thể bị từ chối bằng `CallNotPermittedException` cho đến khi có kết quả và breaker chuyển trạng thái.

Ví dụ cấu hình circuit breaker cho dịch vụ tồn kho:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
```

Nếu breaker đang `OPEN`, request mới bị từ chối mà không tạo thêm tải cho dịch vụ tồn kho. Khi chuyển sang `HALF_OPEN`, tối đa ba lời gọi thăm dò được cho phép theo cấu hình. Lời gọi đến khi các permission thăm dò đã được cấp hết có thể bị từ chối bằng `CallNotPermittedException`.

`CallNotPermittedException` vì vậy không biểu thị rằng supplier vừa timeout hoặc dịch vụ đích vừa trả 500. Nó cho biết breaker đang thực thi chính sách bảo vệ và không cho phép lời gọi đi tiếp.

## 4. Phân biệt theo nguyên nhân và tác động

| Khía cạnh | `BulkheadFullException` | `CallNotPermittedException` |
|---|---|---|
| Lý do | Hết năng lực tiếp nhận công việc đồng thời hoặc hàng đợi | Circuit breaker không cấp quyền thực thi |
| Phạm vi | Giới hạn concurrency/queue của một bulkhead | Trạng thái và permission của một circuit breaker |
| Tín hiệu vận hành | Áp lực tài nguyên hoặc giới hạn admission | Phụ thuộc đang bị breaker bảo vệ hoặc đang thăm dò có giới hạn |
| Supplier của lời gọi hiện tại | Không được gọi nếu bulkhead từ chối trước khi chạy | Không được gọi khi breaker từ chối |
| Có nên retry ngay? | Thường không; retry tức thì làm tăng áp lực | Không; cần chờ trạng thái breaker thay đổi hoặc dùng fallback |
| Hướng xử lý | Giảm concurrency, điều tiết lưu lượng, kiểm tra thời gian giữ permit và queue | Kiểm tra breaker state, lỗi/slow call gần đây và thời gian phục hồi |

Ví dụ thực tế: dịch vụ giá đang xử lý nhiều request chậm. Bulkhead giới hạn 15 lời gọi đồng thời; khi đủ 15 permit, request mới nhận `BulkheadFullException`. Trong khi đó, circuit breaker của dịch vụ giá có thể vẫn `CLOSED` vì chưa đủ mẫu lỗi hoặc tỷ lệ lỗi chưa vượt ngưỡng. Nếu sau đó nhiều request timeout và breaker mở, request tiếp theo có thể nhận `CallNotPermittedException`.

## 5. Thứ tự ghép Bulkhead và CircuitBreaker ảnh hưởng exception quan sát được

Khi dùng đồng thời hai cơ chế, thứ tự decorator quyết định cơ chế nào kiểm tra trước. Nếu cả bulkhead đã đầy và circuit breaker đang `OPEN`, exception được nhìn thấy phụ thuộc vào lớp ngoài cùng.

### CircuitBreaker ở ngoài, Bulkhead ở trong

```java
Supplier<InventoryView> protectedCall =
        CircuitBreaker.decorateSupplier(
                circuitBreaker,
                Bulkhead.decorateSupplier(
                        bulkhead,
                        () -> inventoryClient.find(sku)
                )
        );
```

Luồng thực thi:

1. Circuit breaker kiểm tra và cấp permission.
2. Nếu breaker đang `OPEN`, nó ném `CallNotPermittedException`; bulkhead và HTTP client không được gọi.
3. Nếu breaker cho phép, bulkhead thử lấy permit.
4. Nếu bulkhead đầy, nó ném `BulkheadFullException`; supplier HTTP không chạy.
5. Nếu bulkhead cấp permit, lời gọi đến dịch vụ tồn kho mới được thực thi.

Trong thứ tự này, circuit breaker bao ngoài bulkhead và có thể quan sát `BulkheadFullException` như exception từ supplier. Nếu không cấu hình ignore phù hợp, lỗi từ chối cục bộ có thể làm tăng failure rate của circuit breaker dù backend chưa nhận request.

### Bulkhead ở ngoài, CircuitBreaker ở trong

```java
Supplier<InventoryView> protectedCall =
        Bulkhead.decorateSupplier(
                bulkhead,
                CircuitBreaker.decorateSupplier(
                        circuitBreaker,
                        () -> inventoryClient.find(sku)
                )
        );
```

Luồng thực thi:

1. Bulkhead thử lấy permit trước.
2. Nếu bulkhead đầy, nó ném `BulkheadFullException`; circuit breaker không được gọi.
3. Nếu bulkhead cấp permit, circuit breaker kiểm tra trạng thái.
4. Nếu breaker đang `OPEN`, nó ném `CallNotPermittedException`; supplier HTTP không chạy và permit bulkhead được giải phóng khi lời gọi kết thúc bằng exception.
5. Nếu breaker cấp permission, supplier mới thực hiện lời gọi.

Trong thứ tự này, circuit breaker không quan sát được `BulkheadFullException` vì exception phát sinh ở lớp ngoài. Hai cách ghép có hành vi quan sát khác nhau; lựa chọn cần dựa trên chính sách đo lỗi và kiểm soát tải của ứng dụng.

## 6. Không để lỗi đầy Bulkhead làm sai failure rate

Khi CircuitBreaker bao ngoài Bulkhead, `BulkheadFullException` có thể đi qua supplier của breaker. Theo cấu hình mặc định, exception phát sinh từ supplier thường được tính là lỗi, trừ khi được ignore hoặc phân loại bằng predicate. Nếu mục tiêu là đo lỗi của dịch vụ phụ thuộc, việc tính lỗi từ chối cục bộ vào failure rate có thể làm breaker mở vì chính giới hạn concurrency của ứng dụng gọi.

Có thể bỏ qua `BulkheadFullException` trong cấu hình circuit breaker:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        ignoreExceptions:
          - io.github.resilience4j.bulkhead.BulkheadFullException
```

Exception bị ignore không được tính là success hay failure trong sliding window. Nó vẫn có thể được xử lý ở fallback và ghi metric riêng. Cách này giúp phân biệt tình trạng bulkhead từ chối với lỗi thật của phụ thuộc.

Không cần coi `CallNotPermittedException` là một lỗi supplier thông thường. Breaker phát exception này khi chính nó từ chối lời gọi; lời gọi bị chặn không phải một lần gọi backend thất bại. Nên theo dõi số lần breaker từ chối qua sự kiện/metric tương ứng thay vì cộng chúng vào lỗi HTTP của dịch vụ đích.

Nếu ứng dụng muốn bulkhead rejection góp vào một chỉ số quá tải tổng thể, hãy tạo metric riêng cho số lần bị từ chối, số permit đang dùng và thời gian chờ permit. Không nên dùng failure rate của circuit breaker để thay thế các chỉ số admission control.

## 7. Phân loại exception trong fallback

Spring Cloud CircuitBreaker cho phép cung cấp fallback nhận `Throwable`. Gateway có thể phân biệt hai exception để trả trạng thái phù hợp:

```java
import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

public InventoryView find(String sku) {
    return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.find(sku),
            failure -> {
                if (hasCause(failure, BulkheadFullException.class)) {
                    return InventoryView.busy(sku);
                }
                if (hasCause(failure, CallNotPermittedException.class)) {
                    return InventoryView.temporarilyUnavailable(sku);
                }
                return InventoryView.unavailable(sku);
            }
    );
}

private boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType) {
    for (Throwable current = error;
         current != null;
         current = current.getCause()) {
        if (expectedType.isInstance(current)) {
            return true;
        }
    }
    return false;
}
```

`InventoryView.busy`, `temporarilyUnavailable` và `unavailable` là các trạng thái minh họa của ứng dụng. Kiểu fallback thực tế phải phù hợp với hợp đồng API. Một số lớp tích hợp hoặc adapter có thể bọc exception trong một exception khác; kiểm tra cause chain giúp tránh bỏ sót nguyên nhân gốc. Nếu hệ thống có wrapper đặc thù, cần kiểm tra cấu trúc exception thực tế trước khi phân loại.

Không nên trả về số lượng tồn kho bằng 0 cho cả hai trường hợp. Khi bulkhead đầy hoặc circuit breaker mở, ứng dụng chưa biết tồn kho thực tế. `BUSY` hoặc `UNAVAILABLE` thể hiện rõ dữ liệu chưa được xác nhận. Nếu có cache, có thể trả dữ liệu gần nhất cùng dấu thời gian và trạng thái stale khi nghiệp vụ cho phép.

## 8. Chọn hành vi retry phù hợp

Retry ngay lập tức khi nhận `BulkheadFullException` thường làm tình trạng tắc nghẽn nặng hơn. Nhiều client có thể cùng thử lại và tiếp tục tranh permit. Nếu cần thử lại, hãy dùng backoff và jitter, giới hạn số lần, hoặc để tầng gọi điều tiết tốc độ. Với request tương tác, trả trạng thái bận sớm đôi khi phù hợp hơn việc giữ request chờ lâu.

Với `CallNotPermittedException`, breaker đang chủ động ngăn lời gọi. Retry liên tục trong lúc breaker `OPEN` chỉ tạo thêm request bị từ chối và log/metric nhiễu. Có thể đợi đến thời gian phục hồi hoặc để một request sau đó thử khi breaker chuyển `HALF_OPEN`. Không nên để nhiều client đồng loạt retry đúng thời điểm breaker hết thời gian mở; backoff và jitter giúp giảm đợt tải đột ngột.

| Tình huống | Phản ứng phù hợp |
|---|---|
| Bulkhead semaphore hết permit | Từ chối nhanh hoặc chờ trong giới hạn ngắn đã định; kiểm tra concurrency và thời gian giữ permit |
| Thread pool bulkhead và queue đầy | Giảm tốc độ nhận việc, xem xét kích thước pool/queue và thời gian xử lý |
| Circuit breaker `OPEN` | Fallback hoặc trả trạng thái tạm thời không sẵn có; không retry liên tục |
| Circuit breaker `HALF_OPEN` hết lượt thăm dò | Để các lời gọi thăm dò hoàn tất; tránh tạo thêm request đồng thời |

Nếu retry một thao tác có tác động phụ, như tạo đơn hàng hoặc thanh toán, phải dùng idempotency key hoặc cơ chế nhận diện yêu cầu lặp. Một request bị từ chối bởi bulkhead hoặc breaker thường chưa gọi backend qua supplier đó, nhưng không nên suy luận trạng thái của những lần thử trước từ exception của lần hiện tại.

## 9. Theo dõi riêng Bulkhead và CircuitBreaker

Không nên gộp mọi lần từ chối thành một metric lỗi chung. Theo dõi từng cơ chế giúp xác định hệ thống đang thiếu năng lực xử lý đồng thời hay đang bảo vệ một phụ thuộc suy giảm.

**Với Bulkhead**, quan sát:

- Số permit đang sử dụng và số permit còn trống.
- Số lời gọi bị từ chối do không lấy được permit.
- Thời gian chờ permit nếu `maxWaitDuration` lớn hơn 0.
- Kích thước thread pool, số thread hoạt động và độ dài hàng đợi nếu dùng thread pool bulkhead.
- Thời gian giữ permit và latency của lời gọi được bảo vệ.

**Với CircuitBreaker**, quan sát:

- Trạng thái `CLOSED`, `OPEN`, `HALF_OPEN` và số lần chuyển trạng thái.
- Failure rate, slow call rate và số mẫu trong sliding window.
- Số lời gọi bị từ chối do breaker không cấp permission.
- Số lời gọi thành công, thất bại và số lần fallback.

Resilience4j cung cấp event và metric cho từng thành phần khi được tích hợp với Micrometer/Actuator. Tên metric cụ thể phụ thuộc phiên bản và cấu hình; hãy kiểm tra endpoint metrics của ứng dụng thay vì giả định mọi phiên bản đều có cùng tên. Dùng breaker/bulkhead ID và dependency làm nhãn có giới hạn; tránh đưa request ID hoặc user ID vào metric label.

Một số cách đọc tín hiệu:

- `BulkheadFullException` tăng nhưng circuit breaker vẫn `CLOSED`: kiểm tra concurrency, queue, thread pool và thời gian phản hồi; chưa thể kết luận backend đang trả lỗi.
- `CallNotPermittedException` tăng và breaker ở `OPEN`: kiểm tra failure/slow call rate trước thời điểm mở mạch, đồng thời xác nhận fallback đang hoạt động.
- Cả hai cùng tăng: có thể hệ thống vừa có áp lực concurrency vừa có breaker mở; kiểm tra thứ tự decorator để hiểu exception nào được quan sát ở mỗi request.
- Bulkhead thường xuyên đầy nhưng latency backend bình thường: có thể giới hạn concurrency đặt quá thấp hoặc lưu lượng đột biến; điều chỉnh dựa trên tải đo được và khả năng backend.
- Bulkhead đầy cùng latency tăng và connection pool cạn: phụ thuộc có thể đang chậm, khiến permit bị giữ lâu; xem xét timeout và circuit breaker cùng lúc.

## 10. Kiểm thử hai trường hợp từ chối

Kiểm thử cần xác nhận exception, số lần supplier được gọi và thống kê của từng cơ chế. Có thể xây dựng các tình huống sau:

1. **Bulkhead đầy:** giữ tất cả permit bằng các tác vụ đang chạy, gửi thêm một lời gọi và xác nhận nhận `BulkheadFullException` khi không còn khả năng chờ.
2. **Bulkhead có thời gian chờ:** giữ permit lâu hơn `maxWaitDuration`, sau đó xác nhận lời gọi chờ bị từ chối khi hết thời gian.
3. **Thread pool và queue đầy:** chiếm hết worker thread và lấp đầy queue, sau đó xác nhận tác vụ tiếp theo bị từ chối.
4. **Circuit breaker `OPEN`:** chuyển breaker sang `OPEN`, gọi supplier và xác nhận nhận `CallNotPermittedException`; bộ đếm supplier không tăng.
5. **Circuit breaker `HALF_OPEN`:** dùng hết số permission thăm dò, gửi thêm lời gọi và xác nhận lời gọi bổ sung bị từ chối.
6. **Hai cơ chế cùng giới hạn:** cấu hình bulkhead đầy và breaker `OPEN`, sau đó đổi thứ tự decorator để xác nhận exception xuất hiện từ lớp kiểm tra đầu tiên.
7. **Failure rate:** đặt `BulkheadFullException` vào `ignoreExceptions` khi breaker bao ngoài bulkhead và xác nhận lỗi từ chối không làm tăng số mẫu failure hoặc success.
8. **Fallback:** xác nhận fallback phân biệt được `BUSY` với `UNAVAILABLE` và không phát sinh request HTTP bổ sung ngoài ý muốn.

Trong test, nên dùng latch hoặc cơ chế điều khiển publisher để giữ permit có chủ đích, tránh dùng `sleep` tùy tiện khiến kết quả không ổn định. Kiểm tra cả đường thành công, exception trực tiếp và exception có wrapper nếu ứng dụng có lớp adapter riêng.

## 11. Quy trình chẩn đoán khi gặp exception

Khi gateway nhận một trong hai exception, có thể xử lý theo trình tự sau:

1. Ghi nhận exception ngoài cùng và cause chain để tìm loại exception thực tế.
2. Xác định request đã đi qua bulkhead hay circuit breaker trước, dựa trên thứ tự decorator và cấu hình tích hợp.
3. Nếu là `BulkheadFullException`, kiểm tra permit, queue, thread pool, thời gian giữ permit và latency của tác vụ đang chạy.
4. Nếu là `CallNotPermittedException`, kiểm tra trạng thái breaker, failure/slow call rate, số mẫu và thời gian ở `OPEN` hoặc permission `HALF_OPEN`.
5. Kiểm tra fallback có phân biệt trạng thái bận do admission control với trạng thái phụ thuộc đang bị breaker chặn.
6. Xem lại retry policy để bảo đảm không tạo thêm tải trong thời gian hệ thống đang từ chối request.
7. Đối chiếu metric của bulkhead và circuit breaker với trace của lời gọi backend trước khi thay đổi ngưỡng.

`BulkheadFullException` và `CallNotPermittedException` đều báo rằng một lời gọi không được thực thi, nhưng chúng chỉ ra hai lớp bảo vệ khác nhau. Bulkhead từ chối vì đã hết năng lực tiếp nhận công việc; circuit breaker từ chối vì chính sách trạng thái không cho phép gọi phụ thuộc. Phân loại riêng hai exception, hiểu thứ tự kết hợp và đo metric tương ứng giúp ứng dụng Spring Cloud kiểm soát concurrency, bảo vệ dịch vụ suy giảm và trả fallback đúng ý nghĩa.
