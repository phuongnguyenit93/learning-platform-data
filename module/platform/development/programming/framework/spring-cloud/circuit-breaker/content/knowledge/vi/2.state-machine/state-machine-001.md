# CLOSED: cho phép lời gọi và ghi nhận kết quả

## Vị trí của CLOSED trong mô hình trạng thái

Trong Spring Cloud Circuit Breaker, Circuit Breaker theo dõi kết quả gọi đến một dịch vụ phụ thuộc để hạn chế lỗi dây chuyền khi dịch vụ đó chậm hoặc không khả dụng. Với Resilience4j, `CLOSED` là trạng thái hoạt động bình thường: lời gọi mới được phép đi đến dịch vụ đích, và kết quả của mỗi lời gọi được ghi nhận vào cửa sổ trượt (*sliding window*).

Một Circuit Breaker mới thường bắt đầu ở `CLOSED`. Trạng thái này không có nghĩa dịch vụ phụ thuộc chắc chắn khỏe mạnh. Nó chỉ cho biết bộ ngắt mạch hiện chưa có đủ bằng chứng theo ngưỡng cấu hình để ngăn lời gọi. Vì vậy, lời gọi trong `CLOSED` vẫn có thể thành công, thất bại hoặc mất quá nhiều thời gian.

Luồng xử lý cơ bản:

1. Ứng dụng yêu cầu gọi dịch vụ phụ thuộc.
2. Circuit Breaker kiểm tra trạng thái. Khi đang `CLOSED`, nó cho phép lời gọi tiếp tục.
3. Lời gọi thực thi qua HTTP client, SDK hoặc thành phần tương ứng.
4. Khi lời gọi hoàn tất, Circuit Breaker phân loại kết quả và cập nhật số liệu trong sliding window.
5. Sau khi đạt số lời gọi tối thiểu, Circuit Breaker tính tỷ lệ lỗi và tỷ lệ lời gọi chậm. Nếu một ngưỡng mở mạch bị chạm hoặc vượt qua, nó chuyển sang `OPEN`.

Các lời gọi đã được cho phép trước thời điểm chuyển trạng thái vẫn có thể đang chạy. Circuit Breaker không tự hủy những lời gọi đang thực thi; nó quyết định có cho phép những lời gọi mới hay không.

## Kết quả nào được ghi nhận?

Resilience4j theo dõi kết quả của lời gọi trong cửa sổ trượt. Những thông tin quan trọng gồm:

- **Thành công:** lời gọi hoàn tất bình thường.
- **Thất bại:** lời gọi kết thúc bằng ngoại lệ được cấu hình để ghi nhận là lỗi.
- **Lời gọi chậm:** thời gian thực thi vượt `slowCallDurationThreshold`, kể cả khi lời gọi cuối cùng vẫn thành công.

Tỷ lệ lỗi được tính từ số lời gọi thất bại chia cho số lời gọi được tính trong cửa sổ. Tỷ lệ lời gọi chậm được tính tương tự từ số lời gọi chậm. Ngoại lệ được cấu hình bỏ qua không làm tăng tỷ lệ lỗi. Nếu khai báo `recordExceptions`, cần nhớ rằng các ngoại lệ không nằm trong danh sách đó được xem là thành công đối với bộ ngắt mạch; hãy chọn danh sách theo hợp đồng lỗi thực tế của dịch vụ.

Sliding window có hai kiểu phổ biến:

| Kiểu cửa sổ | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| `COUNT_BASED` | Giữ kết quả của một số lượng lời gọi gần nhất, chẳng hạn 10 lời gọi. | Lưu lượng tương đối ổn định và muốn đánh giá theo số lần gọi. |
| `TIME_BASED` | Tổng hợp kết quả trong một khoảng thời gian, chẳng hạn 10 giây gần nhất. | Muốn đánh giá theo thời gian, nhất là khi lưu lượng thay đổi. |

`minimumNumberOfCalls` quy định số lời gọi tối thiểu cần có trước khi tính tỷ lệ để quyết định mở mạch. Ví dụ, với `slidingWindowSize = 10` và `minimumNumberOfCalls = 5`, Circuit Breaker có thể đánh giá sau năm lời gọi đầu tiên; nó không cần chờ đủ cả mười kết quả. Nếu chưa đạt số lời gọi tối thiểu, tỷ lệ lỗi chưa đủ cơ sở để kích hoạt chuyển trạng thái.

## Cấu hình ngưỡng cho trạng thái CLOSED

Ví dụ cấu hình một Circuit Breaker tên `inventory` trong `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

Với cấu hình này, Circuit Breaker ghi nhận tối đa 10 kết quả gần nhất và bắt đầu đánh giá khi có ít nhất 5 lời gọi. Nếu tỷ lệ lỗi đạt từ 50% trở lên, hoặc tỷ lệ lời gọi chậm đạt từ 60% trở lên, nó có thể chuyển từ `CLOSED` sang `OPEN`. Chẳng hạn, trong năm lời gọi đủ điều kiện đầu tiên có ba lời gọi thất bại thì tỷ lệ lỗi là `3 / 5 = 60%`, vượt ngưỡng 50%.

`waitDurationInOpenState` và `permittedNumberOfCallsInHalfOpenState` điều khiển hành vi ở các trạng thái tiếp theo. Chúng được đặt cạnh cấu hình `CLOSED` vì cùng thuộc một Circuit Breaker, nhưng không thay đổi cách ghi nhận kết quả khi mạch đang đóng.

Khi chọn ngưỡng, hãy cân nhắc lưu lượng thật. Với lưu lượng thấp, việc chờ đủ `minimumNumberOfCalls` có thể mất nhiều thời gian; với lưu lượng cao, cửa sổ quá nhỏ có thể phản ứng mạnh trước một đợt lỗi ngắn. Ngưỡng lời gọi chậm cũng cần khớp với thời gian đáp ứng mà ứng dụng có thể chấp nhận.

## Tích hợp với lời gọi Spring và fallback

Khi dùng tích hợp annotation của Resilience4j trong Spring Boot, có thể đặt `@CircuitBreaker` trên phương thức gọi dịch vụ phụ thuộc:

```java
@Service
public class InventoryService {
    private final InventoryClient client;

    public InventoryService(InventoryClient client) {
        this.client = client;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "availabilityFallback")
    public String getAvailability(String sku) {
        return client.fetchAvailability(sku);
    }

    public String availabilityFallback(String sku, Throwable cause) {
        return "UNKNOWN";
    }
}
```

Tên `inventory` phải khớp với tên instance trong cấu hình. Phương thức fallback có cùng kiểu trả về và các tham số nghiệp vụ như phương thức gốc, sau đó nhận thêm tham số ngoại lệ. Giá trị `UNKNOWN` chỉ là ví dụ: ứng dụng cần quy định rõ cách biểu diễn dữ liệu chưa xác định để tầng gọi không nhầm nó với kết quả hợp lệ.

Trong lúc Circuit Breaker còn `CLOSED`, lời gọi vẫn đến `InventoryClient`. Nếu lời gọi thất bại và có fallback phù hợp, Resilience4j có thể gọi fallback để tạo phản hồi thay thế. Việc fallback chạy không tự động có nghĩa Circuit Breaker đã mở; quyết định chuyển trạng thái vẫn dựa trên các kết quả được ghi nhận và ngưỡng cấu hình. Khi dùng annotation dựa trên Spring AOP, lời gọi cần đi qua Spring proxy; lời gọi nội bộ bằng `this.someMethod()` trong cùng bean có thể bỏ qua interceptor.

## Lời gọi reactive

Với Reactor, có thể áp dụng `CircuitBreakerOperator` lên `Mono` hoặc `Flux`. Dùng `transformDeferred` để áp dụng bộ ngắt mạch cho từng lần subscribe:

```java
Mono<String> availability = webClient.get()
    .uri("/inventory/{sku}", sku)
    .retrieve()
    .bodyToMono(String.class)
    .transformDeferred(CircuitBreakerOperator.of(circuitBreaker));
```

Khi mạch đang `CLOSED`, subscription được phép chạy và tín hiệu hoàn tất hoặc lỗi được dùng để cập nhật số liệu. Trong pipeline reactive, nên xử lý fallback bằng các toán tử như `onErrorResume` theo quy tắc nghiệp vụ; tránh chặn luồng bằng `block()` chỉ để lấy kết quả.

## Phân biệt Circuit Breaker với timeout và bulkhead

Ở trạng thái `CLOSED`, một lời gọi chậm vẫn được phép tiếp tục cho đến khi client hoặc cơ chế timeout khác kết thúc nó. Circuit Breaker ghi nhận lời gọi chậm sau khi có kết quả, nhưng bản thân nó không đặt giới hạn thời gian và không hủy request đang chạy.

- **Timeout / TimeLimiter** giới hạn thời gian chờ một lời gọi.
- **Bulkhead** giới hạn số lời gọi đồng thời hoặc tài nguyên được dùng cho một dịch vụ phụ thuộc.
- **Circuit Breaker** quan sát kết quả và ngăn các lời gọi mới khi tỷ lệ lỗi hoặc chậm vượt ngưỡng.

Kết hợp các cơ chế này giúp ứng dụng vừa giới hạn thời gian chờ, vừa kiểm soát mức đồng thời, vừa ngăn tiếp tục dồn tải vào một dịch vụ đang suy giảm.

## Theo dõi hoạt động khi CLOSED

Nên theo dõi trạng thái hiện tại cùng số lời gọi thành công, thất bại, chậm và bị từ chối. Resilience4j cung cấp metrics và event publisher để tích hợp với log, Micrometer và hệ thống giám sát. Ví dụ đọc một số chỉ số từ instance:

```java
CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

log.info(
    "state={}, failureRate={}, slowCallRate={}, failedCalls={}, successfulCalls={}",
    circuitBreaker.getState(),
    metrics.getFailureRate(),
    metrics.getSlowCallRate(),
    metrics.getNumberOfFailedCalls(),
    metrics.getNumberOfSuccessfulCalls()
);
```

Khi chưa đủ `minimumNumberOfCalls`, `getFailureRate()` có thể trả về `-1` để biểu thị chưa có tỷ lệ đủ điều kiện đánh giá. Vì vậy, dashboard nên phân biệt trạng thái chưa đủ mẫu với tỷ lệ lỗi bằng 0. Khi cần điều tra một lần chuyển trạng thái, hãy đối chiếu sự kiện Circuit Breaker với log của HTTP client, thời gian phản hồi và số request đồng thời.

## Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| `CLOSED` nghĩa là dịch vụ phụ thuộc đang khỏe. | Nó chỉ cho biết bộ ngắt mạch vẫn cho phép lời gọi; lỗi vẫn có thể xảy ra. |
| Chỉ cần có một lỗi là mạch mở. | Circuit Breaker đánh giá theo cửa sổ và chỉ tính tỷ lệ sau khi đủ số lời gọi tối thiểu. |
| Gọi fallback sẽ tự mở mạch. | Fallback xử lý kết quả ở tầng ứng dụng; chuyển trạng thái phụ thuộc vào metrics và ngưỡng. |
| Circuit Breaker tự timeout request đang chạy. | Timeout cần được cấu hình ở HTTP client hoặc TimeLimiter; Circuit Breaker không tự hủy lời gọi đã được cho phép. |

Khi thiết kế trạng thái `CLOSED`, hãy bảo đảm cửa sổ trượt phản ánh đúng lưu lượng, `minimumNumberOfCalls` đủ tin cậy, danh sách ngoại lệ khớp với lỗi cần bảo vệ và ngưỡng lời gọi chậm phù hợp với SLA. Đây là nền tảng để Circuit Breaker phát hiện suy giảm sớm và chuyển sang `OPEN` đúng lúc, giảm nguy cơ lỗi lan truyền trong hệ thống Spring Cloud.
