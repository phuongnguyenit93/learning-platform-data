# Đối chiếu tỷ lệ lỗi của bộ ngắt mạch với kết quả fallback

Khi một dịch vụ phụ thuộc gặp lỗi, ứng dụng có thể trả về dữ liệu dự phòng bằng fallback để tiếp tục phục vụ luồng nghiệp vụ. Tuy nhiên, việc fallback trả về kết quả hợp lệ không có nghĩa là lời gọi đến dịch vụ phụ thuộc đã thành công. Với Spring Cloud CircuitBreaker dùng Resilience4j, cần phân biệt **kết quả của lời gọi được bảo vệ** với **kết quả mà fallback trả về cho bên gọi**. Circuit breaker phân loại lời gọi dựa trên kết quả bên trong vùng được bảo vệ; fallback thường được thực hiện sau khi circuit breaker đã ghi nhận kết quả đó.

Phân biệt hai kết quả này giúp đọc đúng failure rate, slow-call rate và số lời gọi bị từ chối. Nếu gộp lỗi dịch vụ vào fallback rồi trả về như một kết quả thành công ngay bên trong supplier, circuit breaker có thể không nhận ra dịch vụ phụ thuộc đang suy giảm.

## 1. Hai kết quả ở hai thời điểm khác nhau

Một luồng gọi có circuit breaker và fallback thường diễn ra như sau:

1. Ứng dụng gọi circuit breaker.
2. Nếu circuit breaker ở `CLOSED` hoặc cho phép lời gọi thử trong `HALF_OPEN`, supplier thực hiện lời gọi đến dịch vụ phụ thuộc.
3. Circuit breaker ghi nhận kết quả của supplier: thành công, lỗi, hoặc lời gọi chậm theo cấu hình.
4. Nếu supplier ném exception, lớp gọi Spring Cloud hoặc mã xử lý bên ngoài circuit breaker có thể gọi fallback.
5. Bên gọi nhận kết quả từ fallback nếu fallback hoàn tất thành công.

Nếu circuit breaker đã ở `OPEN`, supplier không được thực thi. Circuit breaker từ chối lời gọi mới bằng `CallNotPermittedException`; fallback có thể xử lý trường hợp này và trả về dữ liệu dự phòng.

```text
Yêu cầu nghiệp vụ
       |
       v
  Circuit breaker
       |
       +-- OPEN ----------------------> Từ chối lời gọi
       |                                  |
       |                                  v
       |                              Fallback
       |                                  |
       |                                  v
       |                           Kết quả cho bên gọi
       |
       +-- CLOSED / HALF_OPEN
              |
              v
       Supplier gọi dịch vụ
              |
        +-----+------+
        |            |
     Thành công    Exception
        |            |
        v            v
   Ghi nhận       Ghi nhận lỗi
   thành công         |
        |             v
        |          Fallback
        |             |
        +------> Kết quả cho bên gọi
```

Fallback là cơ chế phục hồi ở tầng ứng dụng. Nó không tự thay đổi lịch sử lời gọi mà circuit breaker vừa ghi nhận. Do đó, fallback có thể trả về dữ liệu hợp lệ trong khi failure rate vẫn tăng.

## 2. Failure rate được tính từ lời gọi được bảo vệ

Resilience4j dùng các kết quả được ghi nhận trong sliding window để tính tỷ lệ lỗi:

\[
\text{failureRate} = \frac{\text{số lời gọi được ghi nhận là thất bại}}{\text{số lời gọi được ghi nhận trong cửa sổ}} \times 100\%
\]

Số lời gọi trong mẫu gồm các kết quả được circuit breaker ghi nhận là thành công hoặc thất bại. Exception bị cấu hình bỏ qua không góp phần vào hai nhóm này. Lời gọi bị từ chối khi breaker đang `OPEN` cũng không phải là một lần gọi dịch vụ phụ thuộc thất bại; supplier không chạy và số lần từ chối được theo dõi riêng.

Ví dụ cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
```

Giả sử có 10 lời gọi được thực hiện khi breaker đang `CLOSED`:

| Kết quả từ dịch vụ phụ thuộc | Số lần | Fallback trả kết quả thành công | Circuit breaker ghi nhận |
| --- | ---: | ---: | --- |
| Dịch vụ trả dữ liệu bình thường | 4 | Không cần fallback | 4 thành công |
| Dịch vụ ném exception | 6 | Có, cả 6 lần | 6 thất bại |

Failure rate là `6 / 10 × 100% = 60%`. Dù bên gọi nhận được kết quả fallback ở cả sáu yêu cầu lỗi, circuit breaker vẫn thấy sáu lời gọi thất bại. Vì `minimumNumberOfCalls` đã đạt 10 và `failureRateThreshold` là 50%, breaker chuyển sang `OPEN`.

Nếu lấy số kết quả trả về cuối cùng cho người dùng làm tử số hoặc mẫu số, ta sẽ tính sai failure rate. Chỉ số của circuit breaker mô tả độ tin cậy của lời gọi phụ thuộc được bảo vệ, còn tỷ lệ fallback thành công mô tả khả năng phục hồi của ứng dụng.

## 3. Slow-call rate cũng độc lập với kết quả fallback

Một lời gọi có thể không ném exception nhưng vẫn mất quá nhiều thời gian. Resilience4j dùng `slowCallDurationThreshold` để xác định lời gọi chậm và `slowCallRateThreshold` để quyết định khi nào tỷ lệ lời gọi chậm đủ cao để mở mạch.

Ví dụ, trong 10 lời gọi, có 7 lời gọi mất hơn 2 giây nhưng cuối cùng vẫn trả về thành công. Nếu ngưỡng slow-call là 60%, circuit breaker có thể chuyển sang `OPEN` vì tỷ lệ lời gọi chậm đạt 70%, dù failure rate bằng 0%.

Nếu một lời gọi chậm sau đó ném exception, nó có thể đóng góp vào cả failure rate và slow-call rate. Hai tỷ lệ được tính riêng, không cộng lại với nhau. Chỉ cần một điều kiện đạt ngưỡng tương ứng là đủ để mở mạch.

Trong cách bọc thông thường, fallback được gọi sau khi supplier đã kết thúc và circuit breaker ghi nhận thời gian thực thi của supplier. Thời gian chạy fallback không được tính là thời gian của lời gọi được bảo vệ. Nếu tự bắt exception và chạy fallback ngay bên trong supplier, toàn bộ thời gian xử lý fallback lại nằm trong thời gian supplier; điều này có thể làm một kết quả thành công bị đánh dấu là lời gọi chậm.

## 4. Đặt fallback bên ngoài supplier để giữ đúng phân loại

Với Spring Cloud CircuitBreaker, có thể truyền fallback vào phương thức `run(...)`:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.fetch(sku),
            error -> inventoryFallback(sku, error)
        );
    }

    private InventoryResult inventoryFallback(String sku, Throwable cause) {
        return InventoryResult.unavailable(sku);
    }
}
```

Trong ví dụ, supplier chỉ thực hiện `inventoryClient.fetch(sku)`. Nếu client ném exception, circuit breaker ghi nhận kết quả theo quy tắc phân loại của Resilience4j rồi Spring Cloud gọi hàm fallback. Nếu breaker đang `OPEN`, supplier không được chạy và fallback vẫn có thể trả về kết quả dự phòng cho yêu cầu.

Với API gốc của Resilience4j, có thể thực thi supplier qua `executeSupplier(...)` rồi xử lý lỗi ở bên ngoài:

```java
try {
    return inventoryBreaker.executeSupplier(
        () -> inventoryClient.fetch(sku)
    );
} catch (CallNotPermittedException ex) {
    return InventoryResult.unavailable(sku);
} catch (RuntimeException ex) {
    return InventoryResult.unavailable(sku);
}
```

Đây là ví dụ rút gọn: ứng dụng thực tế nên phân biệt lỗi nghiệp vụ, lỗi kỹ thuật, timeout và lỗi bị từ chối để quyết định fallback phù hợp. Không nên bắt mọi `Throwable` rồi trả về một giá trị mặc định, vì cách đó có thể che giấu lỗi lập trình, lỗi cấu hình hoặc lỗi nghiêm trọng của tiến trình.

## 5. Điều gì xảy ra nếu bắt lỗi bên trong supplier?

Một cách viết dễ gây hiểu nhầm là bắt exception của dịch vụ phụ thuộc bên trong supplier và trả về dữ liệu dự phòng ngay lập tức:

```java
return circuitBreakerFactory.create("inventory").run(
    () -> {
        try {
            return inventoryClient.fetch(sku);
        } catch (RuntimeException ex) {
            // Fallback được thực hiện bên trong vùng circuit breaker.
            return InventoryResult.unavailable(sku);
        }
    },
    error -> InventoryResult.unavailable(sku)
);
```

Trong trường hợp này, exception đã bị supplier xử lý. Từ góc nhìn circuit breaker, supplier kết thúc bình thường và trả về một giá trị. Breaker ghi nhận lời gọi thành công; nó không biết dịch vụ phụ thuộc đã ném exception. Nếu tất cả lời gọi lỗi đều được chuyển thành kết quả dự phòng bên trong supplier, failure rate có thể luôn bằng 0% và breaker không mở dù dịch vụ đang hỏng.

Cách này chỉ phù hợp nếu ứng dụng chủ động định nghĩa kết quả dự phòng là một kết quả thành công của thao tác được bảo vệ. Nếu mục tiêu là phát hiện lỗi của dịch vụ phụ thuộc, hãy để exception đi ra khỏi supplier để circuit breaker ghi nhận, sau đó thực hiện fallback ở lớp ngoài.

| Vị trí xử lý fallback | Kết quả circuit breaker quan sát | Ảnh hưởng đến failure rate |
| --- | --- | --- |
| Fallback sau `run(...)` hoặc sau `executeSupplier(...)` | Supplier ném exception | Lời gọi được ghi nhận là thất bại nếu exception được cấu hình ghi nhận |
| Bắt exception và trả fallback bên trong supplier | Supplier trả về bình thường | Lời gọi được ghi nhận là thành công |
| Breaker đang `OPEN`, supplier không được chạy | Lời gọi bị từ chối | Không tăng failure rate của lời gọi phụ thuộc; số lần từ chối được thống kê riêng |

## 6. Phân loại exception trước khi đối chiếu fallback

Không phải exception nào cũng nhất thiết phải làm tăng failure rate. Resilience4j cho phép cấu hình các exception cần ghi nhận hoặc bỏ qua. Cần xem chính sách này trước khi so sánh số lần fallback với số lần lỗi.

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
        ignoreExceptions:
          - com.example.inventory.ProductNotFoundException
```

Ví dụ trên thể hiện ý định phân loại: lỗi kết nối và timeout được tính là lỗi; trường hợp không tìm thấy sản phẩm là kết quả nghiệp vụ được bỏ qua. Khi dùng danh sách `recordExceptions`, hãy kiểm tra semantics của phiên bản Resilience4j đang dùng và đảm bảo các exception khác được phân loại như mong muốn. Quy tắc ignore có độ ưu tiên cao hơn quy tắc record đối với exception khớp ignore.

Giả sử 10 lời gọi có 4 kết quả thành công, 4 lỗi kết nối và 2 exception `ProductNotFoundException` bị bỏ qua. Mẫu dùng để tính tỷ lệ gồm 8 kết quả được ghi nhận: 4 thành công và 4 thất bại. Failure rate là `4 / 8 × 100% = 50%`, không phải `4 / 10 = 40%`. Nếu fallback trả kết quả dự phòng cho cả sáu exception, điều đó vẫn không làm thay đổi cách các exception đã được phân loại.

Lỗi nghiệp vụ chỉ nên được bỏ qua nếu nó thực sự không phản ánh suy giảm của dịch vụ phụ thuộc. Ví dụ `ProductNotFoundException` có thể là phản hồi hợp lệ cho một SKU không tồn tại. Ngược lại, lỗi xác thực hệ thống, lỗi kết nối cơ sở dữ liệu hoặc timeout có thể là tín hiệu cần được ghi nhận tùy ranh giới circuit breaker và mục tiêu bảo vệ.

## 7. Lời gọi bị từ chối khi breaker OPEN không phải lỗi mới của dịch vụ

Khi circuit breaker đã chuyển sang `OPEN`, lời gọi mới bị từ chối trước khi supplier chạy. Ứng dụng vẫn có thể gọi fallback và trả về dữ liệu cache, thông báo tạm thời hoặc trạng thái không khả dụng. Tuy nhiên, không nên cộng mỗi lần fallback do `CallNotPermittedException` vào failure rate của dịch vụ phụ thuộc: trong lần gọi đó, ứng dụng không gửi request đến dịch vụ.

Hãy phân biệt ít nhất ba loại số liệu:

- **Lỗi của lời gọi phụ thuộc:** supplier đã chạy và kết thúc bằng exception được ghi nhận.
- **Lời gọi chậm:** supplier hoàn tất sau thời gian `slowCallDurationThreshold`, dù có thể thành công.
- **Lời gọi bị từ chối:** circuit breaker không cho supplier chạy vì trạng thái hiện tại là `OPEN` hoặc không cho phép thêm lời gọi thử.

Các số liệu này trả lời những câu hỏi vận hành khác nhau. Failure rate cho biết chất lượng các lời gọi đã thực hiện. Slow-call rate cho biết độ trễ của các lời gọi đã thực hiện. Số lần bị từ chối cho biết circuit breaker đang chặn bao nhiêu yêu cầu để bảo vệ hệ thống. Tỷ lệ fallback thành công cho biết ứng dụng có thể trả lời bao nhiêu yêu cầu nhờ cơ chế dự phòng.

Khi breaker ở `HALF_OPEN`, chỉ một số lời gọi thử được cho phép. Kết quả supplier của các lời gọi thử quyết định breaker đóng lại hay mở lại. Nếu supplier thất bại nhưng fallback trả về kết quả hợp lệ, breaker vẫn nhìn thấy supplier thất bại và có thể trở về `OPEN`. Kết quả fallback không được xem là bằng chứng dịch vụ phụ thuộc đã phục hồi.

## 8. Đối chiếu các chỉ số để tìm nguyên nhân

Không nên chỉ theo dõi một chỉ số. Kết hợp số lời gọi, failure rate, slow-call rate, số lần bị từ chối và số lần fallback thành công giúp xác định lớp đang gặp vấn đề.

| Quan sát | Diễn giải có thể có | Việc cần kiểm tra |
| --- | --- | --- |
| Failure rate tăng, fallback thành công cao | Dịch vụ phụ thuộc đang lỗi nhưng ứng dụng vẫn trả lời được nhờ dữ liệu dự phòng | Kiểm tra lỗi client, log dịch vụ phụ thuộc và chính sách fallback |
| Slow-call rate tăng, failure rate thấp | Dịch vụ trả lời chậm nhưng vẫn thành công | Kiểm tra độ trễ, timeout và `slowCallDurationThreshold` |
| Số lần bị từ chối tăng mạnh, failure rate không tăng tương ứng | Breaker đang `OPEN` và chặn các lời gọi mới | Kiểm tra thời điểm chuyển trạng thái và thời gian mở mạch |
| Fallback thất bại cùng lúc với lỗi phụ thuộc | Cả dịch vụ chính và cơ chế dự phòng đều không đáp ứng | Kiểm tra cache, nguồn dữ liệu dự phòng và exception của fallback |
| Failure rate không tăng dù log client có nhiều lỗi | Exception có thể bị ignore hoặc bị bắt bên trong supplier | Kiểm tra `recordExceptions`, `ignoreExceptions` và vị trí catch |

Ví dụ: dashboard cho thấy 40% lời gọi đến inventory thất bại, 95% fallback hoàn tất thành công và số lần bị từ chối đang tăng. Có thể kết luận ứng dụng vẫn phục vụ được phần lớn yêu cầu nhờ fallback, nhưng dịch vụ inventory vẫn đang suy giảm và breaker đã bắt đầu chặn lời gọi. Không nên diễn giải 95% fallback thành công là inventory có tỷ lệ thành công 95%.

## 9. Kiểm thử để chứng minh fallback không che giấu lỗi

Một kiểm thử hữu ích cần xác minh cả kết quả bên gọi và trạng thái breaker. Với cấu hình test có `minimumNumberOfCalls: 4`, `failureRateThreshold: 50` và cửa sổ đếm 4 lời gọi, ta có thể mô phỏng bốn lỗi của dịch vụ phụ thuộc rồi xác minh fallback vẫn trả kết quả dự phòng trong khi breaker chuyển sang `OPEN`.

Ví dụ kiểm thử ở mức API native của Resilience4j:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(4)
    .minimumNumberOfCalls(4)
    .failureRateThreshold(50)
    .build();

CircuitBreaker breaker = CircuitBreaker.of("inventory", config);

for (int i = 0; i < 4; i++) {
    InventoryResult result;
    try {
        result = breaker.executeSupplier(() -> {
            throw new IllegalStateException("inventory unavailable");
        });
    } catch (RuntimeException ex) {
        result = InventoryResult.unavailable("SKU-1");
    }

    // Mỗi lần gọi đều có kết quả dự phòng cho tầng nghiệp vụ.
    assert result.isUnavailable();
}

// Bốn supplier thất bại vẫn được circuit breaker ghi nhận là lỗi.
assert breaker.getState() == CircuitBreaker.State.OPEN;
```

Đoạn mã dùng Java `assert` để minh họa ý tưởng; trong dự án, hãy dùng assertion của framework kiểm thử và bật cấu hình test phù hợp. Bài kiểm thử xác nhận hai điều riêng biệt: bên gọi nhận được kết quả fallback, còn breaker chuyển sang `OPEN` vì supplier đã thất bại đủ số lần. Sau khi breaker mở, gọi thêm một lần nữa sẽ bị từ chối trước khi supplier chạy; kiểm thử riêng số lần supplier được gọi để chứng minh điều đó.

Với Spring Cloud CircuitBreaker, thực hiện cùng kịch bản qua `CircuitBreakerFactory` và fallback truyền vào `run(...)`. Xác minh giá trị fallback trả về, sau đó lấy trạng thái từ backend registry hoặc quan sát metric/event tương ứng. Cần bảo đảm factory và registry đang tham chiếu cùng instance; nếu tạo một registry độc lập trong test, trạng thái đọc được có thể không phải trạng thái của breaker do factory quản lý.

Khi kiểm thử slow-call, cho supplier chờ có kiểm soát lâu hơn `slowCallDurationThreshold` rồi trả về thành công. Kết quả mong đợi là fallback không chạy, nhưng slow-call rate tăng. Khi kiểm thử ignored exception, xác minh exception đó không làm tăng số lời gọi thất bại và mẫu được tính đúng theo các kết quả được ghi nhận. Mỗi bài kiểm thử nên làm rõ loại kết quả nào đang được đo.

## 10. Quy tắc vận hành

- Đặt fallback sau vùng supplier được bảo vệ nếu cần circuit breaker nhận biết lỗi thực tế của dịch vụ phụ thuộc.
- Chỉ bắt exception bên trong supplier khi muốn chủ động coi kết quả thay thế là thành công của thao tác được bảo vệ.
- Cấu hình rõ exception được ghi nhận và exception bị bỏ qua; không dùng fallback để thay thế chính sách phân loại.
- Theo dõi failure rate, slow-call rate, số lần bị từ chối và tỷ lệ fallback thành công như các chỉ số riêng.
- Phân biệt fallback do lỗi supplier với fallback do breaker `OPEN`; hai trường hợp có ý nghĩa vận hành khác nhau.
- Trong `HALF_OPEN`, dựa vào kết quả supplier để đánh giá phục hồi; fallback thành công không chứng minh dịch vụ đã khỏe lại.
- Kiểm thử cả trạng thái circuit breaker và kết quả cuối cùng mà tầng nghiệp vụ nhận được.

Khi đối chiếu đúng hai lớp kết quả, nhóm vận hành có thể nhận biết ứng dụng đang trả lời nhờ fallback trong lúc dependency gặp sự cố, hay dependency đã phục hồi và các lời gọi thực sự thành công. Điều này giúp điều chỉnh ngưỡng circuit breaker, cải thiện dữ liệu dự phòng và tránh che giấu lỗi dây chuyền bằng những phản hồi bề ngoài có vẻ thành công.
