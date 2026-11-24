# Thay thứ tự Retry với Circuit Breaker rồi so sánh thống kê

Trong ứng dụng Spring Cloud CircuitBreaker tích hợp Resilience4j, Retry và Circuit Breaker có thể bọc cùng một lời gọi nhưng thứ tự bọc làm thay đổi số lần gọi đến dependency, số kết quả được ghi vào sliding window và thời điểm bộ ngắt chuyển OPEN. Hai cách phối hợp thường gặp là **Circuit Breaker ở ngoài Retry** và **Retry ở ngoài Circuit Breaker**.

Bài thực hành này dùng cùng một dependency giả lập lỗi, cùng số lần thử và cùng ngưỡng Circuit Breaker để so sánh hai cách sắp xếp. Mục tiêu là quan sát riêng ba đại lượng: số operation logic từ caller, số attempt thực tế đến dependency và số kết quả mà Circuit Breaker ghi nhận. Khi hiểu được khác biệt này, nhóm có thể chọn thứ tự phù hợp với ý nghĩa của failure rate, đồng thời tránh Retry tiếp tục thử khi Circuit Breaker đã từ chối lời gọi.

## 1. Mục tiêu và điều kiện thực hành

Xây dựng một lời gọi đọc Catalog có Retry tối đa ba lần thực thi, tính cả lần đầu. Circuit Breaker mở khi có ít nhất bốn kết quả được ghi nhận và tỷ lệ lỗi đạt từ 50% trở lên.

Thực hiện hai kịch bản độc lập:

- **Kịch bản A — Circuit Breaker ngoài, Retry trong:** một operation logic được Circuit Breaker quan sát như một kết quả sau khi toàn bộ Retry hoàn tất.
- **Kịch bản B — Retry ngoài, Circuit Breaker trong:** mỗi attempt đi qua Circuit Breaker và có thể được ghi nhận thành một kết quả riêng.

Dùng hai Circuit Breaker ID và hai Retry ID riêng để state, metric của hai kịch bản không ảnh hưởng lẫn nhau. Mỗi kịch bản bắt đầu với registry hoặc instance mới ở trạng thái CLOSED.

Điều kiện thử nghiệm:

| Tham số | Giá trị |
|---|---:|
| Retry maxAttempts | 3 |
| Retry waitDuration | 20 ms |
| Circuit Breaker minimumNumberOfCalls | 4 |
| Sliding window size | 10 |
| Failure rate threshold | 50% |
| Open duration | 10 giây |
| Dependency giả lập | Luôn phát TransientCatalogException |
| Fallback | Ghi nhận lỗi cuối cùng và trả kết quả unavailable |

Các giá trị ngắn giúp dễ quan sát trong môi trường thử nghiệm. Khi triển khai thật, phải chọn timeout, số lần thử, khoảng nghỉ và ngưỡng theo SLO, độ trễ và năng lực dependency.

## 2. Chuẩn bị dependency giả lập có thể đếm số attempt

Tạo một client thử nghiệm tăng bộ đếm mỗi khi dependency được gọi. Trong kịch bản cơ bản, client luôn phát lỗi tạm thời để tất cả attempt đều thất bại.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

class FakeCatalogClient {

    private final AtomicInteger attempts = new AtomicInteger();

    Product find(String productId) {
        int attempt = attempts.incrementAndGet();

        throw new TransientCatalogException(
            "Catalog tạm thời không khả dụng, attempt=" + attempt
        );
    }

    int getAttemptCount() {
        return attempts.get();
    }

    void reset() {
        attempts.set(0);
    }
}
~~~

Exception thử nghiệm:

~~~java
class TransientCatalogException extends RuntimeException {
    TransientCatalogException(String message) {
        super(message);
    }
}
~~~

Kết quả dự phòng:

~~~java
record Product(String id, String name, boolean available) {

    static Product unavailable(String id) {
        return new Product(id, "Tạm thời không khả dụng", false);
    }
}
~~~

Bộ đếm của FakeCatalogClient là số lần supplier thực sự gọi dependency. Nó không phải số operation logic và cũng không phải số lần Circuit Breaker ghi nhận. Ba số liệu này cần được đo riêng trong suốt bài thực hành.

Trong môi trường tích hợp thật, thay FakeCatalogClient bằng HTTP stub hoặc WireMock. Stub cần ghi nhận số request nhận được để xác nhận số attempt từ phía server, tránh chỉ dựa vào bộ đếm trong process gọi.

## 3. Cấu hình hai bộ Retry và hai Circuit Breaker độc lập

Khai báo hai nhóm instance trong application YAML:

~~~yaml
resilience4j:
  retry:
    instances:
      catalog-retry-inside:
        maxAttempts: 3
        waitDuration: 20ms
        retryExceptions:
          - com.example.TransientCatalogException
        ignoreExceptions:
          - com.example.ProductNotFoundException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException

      catalog-retry-outside:
        maxAttempts: 3
        waitDuration: 20ms
        retryExceptions:
          - com.example.TransientCatalogException
        ignoreExceptions:
          - com.example.ProductNotFoundException
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException

  circuitbreaker:
    instances:
      catalog-cb-outside:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2

      catalog-cb-inside:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Trong cấu hình:

- **catalog-retry-inside** được dùng khi Retry nằm bên trong Circuit Breaker.
- **catalog-cb-outside** là bộ ngắt bọc toàn bộ chuỗi Retry.
- **catalog-retry-outside** được dùng khi Retry nằm bên ngoài Circuit Breaker.
- **catalog-cb-inside** ghi nhận từng attempt được Retry gọi qua.
- **CallNotPermittedException** bị Retry bỏ qua để dừng ngay khi Circuit Breaker từ chối attempt tiếp theo.
- **ProductNotFoundException** là lỗi nghiệp vụ ví dụ; lỗi này không được thử lại.

Hai cặp instance có cùng ngưỡng để so sánh công bằng. Không tái sử dụng cùng một Circuit Breaker ID cho cả hai kịch bản, vì state và sliding window của kịch bản đầu sẽ làm sai kết quả kịch bản sau.

## 4. Kịch bản A: Circuit Breaker ở ngoài, Retry ở trong

Thứ tự thực thi là:

~~~text
Caller
  |
  v
Circuit Breaker
  |
  v
Retry
  |
  v
Catalog client
~~~

Với cách này, Circuit Breaker cấp quyền một lần cho operation logic. Supplier của nó chứa toàn bộ Retry. Retry có thể gọi Catalog nhiều lần; chỉ khi Retry kết thúc thì Circuit Breaker mới nhận kết quả cuối cùng.

Có thể biểu diễn bằng Resilience4j decorator:

~~~java
Supplier<Product> catalogCall =
    () -> fakeCatalogClient.find(productId);

Retry retry = retryRegistry.retry("catalog-retry-inside");
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.circuitBreaker("catalog-cb-outside");

Supplier<Product> retryInside =
    Retry.decorateSupplier(retry, catalogCall);

Supplier<Product> circuitBreakerOutside =
    CircuitBreaker.decorateSupplier(circuitBreaker, retryInside);

Product product = circuitBreakerOutside.get();
~~~

Nếu dùng Spring Cloud CircuitBreaker factory cho lớp ngoài, có thể giữ Retry bên trong supplier:

~~~java
Retry retry = retryRegistry.retry("catalog-retry-inside");

Product product = circuitBreakerFactory
    .create("catalog-cb-outside")
    .run(
        () -> retry.executeSupplier(
            () -> fakeCatalogClient.find(productId)
        ),
        error -> Product.unavailable(productId)
    );
~~~

Trong ví dụ này, factory tạo Circuit Breaker ở ngoài. Retry chỉ bao quanh lời gọi client bên trong supplier. Fallback được thực thi sau khi operation được bảo vệ kết thúc bằng lỗi hoặc bị từ chối.

Với dependency luôn lỗi và maxAttempts bằng 3, một operation logic tạo ba request đến Catalog. Retry phát lại lỗi cuối cùng sau lần thử thứ ba. Circuit Breaker chỉ ghi nhận một failure cho operation đó.

Nếu chạy bốn operation logic liên tiếp:

| Operation logic | Attempt đến Catalog | Kết quả cuối Retry | Mẫu Circuit Breaker |
|---|---:|---|---|
| 1 | 3 | Failure | 1 failure |
| 2 | 3 | Failure | 1 failure |
| 3 | 3 | Failure | 1 failure |
| 4 | 3 | Failure | 1 failure |
| **Tổng** | **12** | **4 operation thất bại** | **4 failure** |

Sau operation thứ tư, Circuit Breaker có đủ bốn mẫu và failure rate đạt 100%, vượt ngưỡng 50%, nên chuyển OPEN. Operation thứ năm bị Circuit Breaker từ chối trước khi Retry chạy; số request đến Catalog không tăng.

Điểm quan trọng: Circuit Breaker đánh giá kết quả cuối cùng sau Retry. Nếu Retry gặp hai lỗi rồi thành công ở attempt thứ ba, Circuit Breaker chỉ ghi nhận một success. Hai lỗi trung gian không trở thành hai failure trong sliding window của bộ ngắt ngoài.

## 5. Kịch bản B: Retry ở ngoài, Circuit Breaker ở trong

Thứ tự thực thi là:

~~~text
Caller
  |
  v
Retry
  |
  v
Circuit Breaker
  |
  v
Catalog client
~~~

Ở cách này, mỗi attempt do Retry tạo ra đều đi qua Circuit Breaker. Mỗi attempt được cấp quyền và có kết quả riêng trong sliding window.

Biểu diễn bằng decorator:

~~~java
Supplier<Product> catalogCall =
    () -> fakeCatalogClient.find(productId);

Retry retry = retryRegistry.retry("catalog-retry-outside");
CircuitBreaker circuitBreaker =
    circuitBreakerRegistry.circuitBreaker("catalog-cb-inside");

Supplier<Product> circuitBreakerInside =
    CircuitBreaker.decorateSupplier(circuitBreaker, catalogCall);

Supplier<Product> retryOutside =
    Retry.decorateSupplier(retry, circuitBreakerInside);

Product product = retryOutside.get();
~~~

Nếu dùng Spring Cloud CircuitBreaker factory, tạo một Circuit Breaker trước rồi để Retry bọc operation đã bảo vệ:

~~~java
Retry retry = retryRegistry.retry("catalog-retry-outside");
var circuitBreaker = circuitBreakerFactory.create("catalog-cb-inside");

Supplier<Product> circuitBreakerProtected =
    () -> circuitBreaker.run(
        () -> fakeCatalogClient.find(productId),
        error -> {
            if (error instanceof RuntimeException runtimeException) {
                throw runtimeException;
            }
            throw new IllegalStateException(error);
        }
    );

Product product = Retry.decorateSupplier(
    retry,
    circuitBreakerProtected
).get();
~~~

Fallback trong ví dụ này cố ý truyền lỗi ra ngoài để Retry có thể phân loại exception. Nếu fallback trả ngay Product unavailable, Retry sẽ nhìn thấy một kết quả thành công và không thử lại. Khi thiết kế thật, cần quyết định rõ fallback chạy sau Retry hay được thực thi ở từng attempt.

Với cấu hình tối thiểu bốn mẫu, hãy theo dõi diễn biến:

1. Operation logic thứ nhất bắt đầu; Retry gọi attempt 1 qua Circuit Breaker.
2. Dependency lỗi; Circuit Breaker ghi nhận failure thứ nhất.
3. Retry gọi attempt 2; Circuit Breaker ghi nhận failure thứ hai.
4. Retry gọi attempt 3; Circuit Breaker ghi nhận failure thứ ba.
5. Operation logic thứ hai bắt đầu; attempt đầu tiên đi qua Circuit Breaker và tạo failure thứ tư.
6. Circuit Breaker đạt minimumNumberOfCalls và chuyển OPEN.
7. Retry định thực hiện attempt tiếp theo; Circuit Breaker từ chối bằng CallNotPermittedException.
8. Retry bỏ qua exception này và dừng, không tiếp tục gọi dependency.

Bảng minh họa:

| Lần thực thi qua Retry | Circuit Breaker | Gọi Catalog? | Kết quả |
|---|---|---|---|
| Operation 1, attempt 1 | CLOSED, ghi failure 1 | Có | TransientCatalogException |
| Operation 1, attempt 2 | CLOSED, ghi failure 2 | Có | TransientCatalogException |
| Operation 1, attempt 3 | CLOSED, ghi failure 3 | Có | TransientCatalogException |
| Operation 2, attempt 1 | CLOSED, ghi failure 4 rồi OPEN | Có | TransientCatalogException |
| Operation 2, attempt 2 | OPEN, từ chối | Không | CallNotPermittedException |
| Operation 2, attempt tiếp theo | Không được Retry gọi | Không | Retry đã dừng |

Ở kịch bản này, chỉ có bốn request đến dependency trước khi Circuit Breaker mở. Lời gọi bị từ chối không phải request đến Catalog và không nên bị nhầm thành một failure mới của dependency.

## 6. Vì sao phải bỏ qua CallNotPermittedException trong Retry?

Khi Circuit Breaker OPEN, nó phát sinh **CallNotPermittedException** trước khi supplier gọi dependency. Đây là tín hiệu rằng bộ ngắt đang chủ động ngăn lời gọi để bảo vệ hệ thống.

Nếu Retry xem exception này như một lỗi tạm thời có thể thử lại, nó có thể tiếp tục gọi Circuit Breaker nhiều lần trong khi bộ ngắt vẫn OPEN. Những lần đó đều bị từ chối, không giúp dependency phục hồi và chỉ làm tăng số lần thực thi, log và độ trễ.

Cấu hình bỏ qua:

~~~yaml
resilience4j:
  retry:
    instances:
      catalog-retry-outside:
        maxAttempts: 3
        waitDuration: 20ms
        retryExceptions:
          - com.example.TransientCatalogException
        ignoreExceptions:
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException
          - com.example.ProductNotFoundException
~~~

Khi Retry bắt gặp CallNotPermittedException, nó kết thúc chuỗi thử lại và chuyển lỗi ra caller hoặc fallback phía ngoài. Không retry lỗi từ chối của Circuit Breaker.

Cần phân biệt:

- **TransientCatalogException:** dependency đã được gọi và trả lỗi tạm thời; có thể thử lại nếu operation an toàn.
- **CallNotPermittedException:** dependency chưa được gọi vì Circuit Breaker từ chối; dừng Retry.
- **ProductNotFoundException:** kết quả nghiệp vụ; không retry nếu cùng request không thể làm sản phẩm xuất hiện.

Nếu sử dụng một fallback trong Circuit Breaker để chuyển mọi exception thành giá trị mặc định, Retry bên ngoài có thể không còn nhìn thấy exception gốc. Hãy chỉ chuyển lỗi thành fallback ở lớp cuối cùng của chuỗi, hoặc giữ nguyên lỗi khi cần Retry phân loại.

## 7. So sánh hai thứ tự bằng cùng một failure schedule

Để kết quả có thể so sánh, chạy hai kịch bản với cùng điều kiện:

- Cùng dependency giả lập luôn lỗi.
- Cùng maxAttempts bằng 3.
- Cùng waitDuration 20 ms.
- Cùng minimumNumberOfCalls bằng 4.
- Cùng failureRateThreshold 50%.
- Cùng số operation logic được gửi vào.
- Mỗi kịch bản dùng Circuit Breaker instance mới.

Kết quả dự kiến với bốn failure liên tiếp và operation tiếp theo:

| Chỉ số | Circuit Breaker ngoài, Retry trong | Retry ngoài, Circuit Breaker trong |
|---|---:|---:|
| Số operation logic cần để mở mạch | 4 | 2 |
| Attempt đến dependency trước khi OPEN | 12 | 4 |
| Failure được Circuit Breaker ghi nhận trước khi OPEN | 4 | 4 |
| Số attempt bị từ chối sau khi OPEN | 0 trong Retry đang chạy; operation kế tiếp bị chặn ở ngoài | 1 ở lần Retry kế tiếp của operation thứ hai |
| Dependency request sau khi OPEN | Không tăng | Không tăng |
| Ý nghĩa failure rate | Tỷ lệ operation thất bại sau Retry | Tỷ lệ attempt được Circuit Breaker quan sát |

Bảng trên giả định mỗi lần gọi Catalog đều thất bại, Retry thực hiện tối đa ba attempt và Retry bỏ qua CallNotPermittedException. Nếu dependency phục hồi ở attempt thứ hai hoặc thứ ba, kết quả sẽ khác: Circuit Breaker ngoài có thể chỉ ghi một success cho operation; Circuit Breaker trong có thể đã ghi các failure trung gian trước success.

Không dùng số attempt bị từ chối để tính request đến dependency. CallNotPermittedException cho biết lời gọi bị chặn trước supplier; hãy tách chỉ số từ chối khỏi HTTP request count.

## 8. So sánh khi dependency phục hồi ở attempt thứ ba

Failure schedule thứ hai giúp thấy rõ khác biệt khi Retry thành công:

- Attempt 1: TransientCatalogException.
- Attempt 2: TransientCatalogException.
- Attempt 3: trả Product thành công.

Với Circuit Breaker ngoài, Retry chạy đủ ba attempt và trả Product. Circuit Breaker chỉ nhận một kết quả thành công. Sliding window tăng một success.

Với Retry ngoài, Circuit Breaker nhận hai failure rồi một success. Sliding window tăng ba mẫu: hai failure và một success. Nếu hai failure trước đó làm tỷ lệ lỗi vượt ngưỡng sau khi đủ mẫu, Circuit Breaker có thể mở trước attempt thứ ba; lúc đó attempt thứ ba bị từ chối và dependency không được gọi lại.

Điều này có ý nghĩa vận hành:

- Circuit Breaker ngoài ưu tiên đánh giá kết quả cuối cùng của operation sau Retry.
- Circuit Breaker trong phản ứng nhanh hơn với từng lỗi attempt, nhưng có thể mở mạch trước khi Retry hoàn tất.
- Nếu Retry có số lần thử lớn, Circuit Breaker trong có thể tích lũy failure nhanh hơn nhiều so với số operation logic.
- Nếu mục tiêu là đo trải nghiệm cuối cùng của caller, cách bọc ngoài có thể phù hợp hơn.
- Nếu mục tiêu là bảo vệ dependency trước từng attempt thất bại, cách bọc trong có thể phù hợp hơn, nhưng cần bỏ qua CallNotPermittedException.

Không có thứ tự tốt nhất cho mọi hệ thống. Chọn theo ý nghĩa thống kê mà nhóm muốn quan sát và mức độ ưu tiên giữa khả năng phục hồi của một operation với việc giảm tải sớm cho dependency.

## 9. Đo đúng các thống kê cần so sánh

Trong mỗi lần chạy, ghi lại ít nhất các chỉ số sau:

| Chỉ số | Nguồn đo | Ý nghĩa |
|---|---|---|
| Logical operations | Bộ đếm tại service hoặc test harness | Caller đã yêu cầu bao nhiêu operation |
| Dependency attempts | Bộ đếm FakeCatalogClient hoặc HTTP stub | Có bao nhiêu request thực sự đến dependency |
| Retry attempts | Retry metrics hoặc event | Retry đã thực hiện bao nhiêu lần thử |
| Retry success after retry | Retry metrics | Bao nhiêu operation chỉ thành công sau khi thử lại |
| Circuit Breaker successful calls | Circuit Breaker metrics | Số kết quả thành công được bộ ngắt ghi nhận |
| Circuit Breaker failed calls | Circuit Breaker metrics | Số failure được tính vào thống kê |
| Not permitted calls | Circuit Breaker metrics/event | Số lần bộ ngắt từ chối trước khi gọi supplier |
| State transitions | Circuit Breaker events | Thời điểm CLOSED, OPEN và HALF_OPEN thay đổi |
| Fallback count | Bộ đếm fallback | Bao nhiêu operation dùng dữ liệu hoặc phản hồi dự phòng |
| End-to-end latency | Timer tại service | Caller phải chờ bao lâu cho một operation logic |

Không suy luận số request đến backend từ Retry metrics hoặc Circuit Breaker failure count. Với Circuit Breaker ngoài, một failure của bộ ngắt có thể tương ứng ba request đến dependency. Với Circuit Breaker trong, ba failure của bộ ngắt có thể tương ứng ba request. Chỉ dependency request count mới trả lời trực tiếp câu hỏi backend nhận bao nhiêu request.

Trong Resilience4j, có thể quan sát event như state transition, error, success và call not permitted. Micrometer metrics tùy phiên bản và cấu hình registry có thể cung cấp các nhóm số liệu tương ứng. Hãy dùng metric name và tag do phiên bản thực tế xuất ra; không hardcode dashboard theo tên giả định.

## 10. Cách chạy hai kịch bản và reset state

Thực hiện từng kịch bản riêng biệt để không dùng chung state hoặc bộ đếm.

### Kịch bản A

1. Khởi tạo Circuit Breaker **catalog-cb-outside** ở CLOSED.
2. Reset bộ đếm dependency.
3. Gửi bốn operation logic tuần tự, mỗi operation đều gặp ba attempt thất bại.
4. Sau mỗi operation, ghi số request dependency và số mẫu Circuit Breaker.
5. Xác nhận sau operation thứ tư bộ ngắt chuyển OPEN.
6. Gửi operation thứ năm.
7. Xác nhận operation thứ năm bị từ chối và dependency attempt count vẫn là 12.

### Kịch bản B

1. Tạo instance mới **catalog-cb-inside** ở CLOSED.
2. Reset bộ đếm dependency và Retry metrics.
3. Gửi operation logic đầu tiên, cho phép Retry chạy ba attempt thất bại.
4. Gửi operation logic thứ hai.
5. Xác nhận attempt đầu của operation thứ hai là failure thứ tư và làm bộ ngắt OPEN.
6. Xác nhận attempt kế tiếp bị từ chối bằng CallNotPermittedException.
7. Xác nhận dependency attempt count là 4, không tăng khi Circuit Breaker đã OPEN.

Nếu dùng test tự động, không tái sử dụng một instance Circuit Breaker đã OPEN giữa các test. Tạo registry hoặc instance mới cho mỗi scenario, hoặc dùng cơ chế reset state chỉ trong test theo API phiên bản đang dùng. Không dựa vào việc chờ 10 giây để tự reset một bộ ngắt; hết wait duration chỉ cho phép quá trình HALF_OPEN, không tự đưa nó về CLOSED nếu chưa có probe phù hợp.

## 11. Kiểm tra fallback và exception policy

Fallback phải nằm ở vị trí phù hợp với thứ tự bọc.

**Fallback ở ngoài toàn bộ chuỗi Retry và Circuit Breaker:** caller chỉ nhận fallback sau khi Retry kết thúc hoặc Circuit Breaker từ chối operation. Đây thường là vị trí dễ giữ semantics nhất khi muốn Retry xử lý exception gốc trước.

**Fallback bên trong Circuit Breaker khi Retry ở ngoài:** nếu fallback biến lỗi thành Product unavailable, Retry sẽ nhận Product như một kết quả bình thường và không thử lại. Nếu muốn Retry hoạt động, fallback bên trong phải truyền lỗi ra ngoài hoặc chỉ chuyển đổi các exception không cần retry.

Ví dụ fallback cuối cùng:

~~~java
Product getProduct(String productId) {
    try {
        return retryOutsideCircuitBreaker(productId);
    } catch (CallNotPermittedException error) {
        return productCache.find(productId)
            .orElse(Product.unavailable(productId));
    } catch (TransientCatalogException error) {
        return productCache.find(productId)
            .orElse(Product.unavailable(productId));
    }
}
~~~

Trong ứng dụng thật, có thể phân loại thêm lỗi nghiệp vụ để truyền tiếp thay vì trả unavailable. Không biến ProductNotFound thành lỗi hạ tầng; cũng không biến mọi exception thành cache fallback nếu dữ liệu cache có thể cũ hoặc không hợp lệ.

Với thao tác ghi như giữ hàng hoặc thanh toán, chỉ retry khi operation idempotent hoặc có idempotency key. Caller timeout không chứng minh backend chưa thực hiện thao tác; thử lại mù quáng có thể tạo giao dịch lặp.

## 12. Lưu ý khi dùng annotation thay vì decorator

Spring AOP cho phép khai báo Retry và Circuit Breaker bằng annotation, nhưng thứ tự aspect có thể ảnh hưởng cách hai cơ chế bọc nhau. Không nên suy luận thứ tự thực thi chỉ từ thứ tự annotation trên method.

Ví dụ:

~~~java
@CircuitBreaker(name = "catalog", fallbackMethod = "fallback")
@Retry(name = "catalog")
public Product getProduct(String id) {
    return catalogClient.find(id);
}
~~~

Đoạn annotation trên thể hiện các chính sách cùng áp dụng cho method, nhưng thứ tự aspect thực tế cần được xác định theo phiên bản Resilience4j, cấu hình aspect order và cách Spring proxy method. Nếu cần kiểm soát chính xác thứ tự để so sánh, explicit decorator composition dễ đọc và ít phụ thuộc vào thứ tự aspect ngầm hơn.

Khi dùng annotation, hãy:

- Kiểm tra thứ tự aspect của phiên bản đang dùng.
- Kiểm tra method được gọi qua Spring proxy, không phải self-invocation.
- Đặt Retry và Circuit Breaker ID riêng cho từng scenario.
- Cấu hình ignore CallNotPermittedException nếu Retry có thể nằm ngoài Circuit Breaker.
- Dùng test đếm số lần gọi dependency để xác nhận thứ tự thật.
- Kiểm tra fallback không nuốt exception trước khi Retry phân loại.

Không thay đổi aspect order ở production chỉ để làm test đạt kết quả mong muốn. Trước tiên xác định hành vi hiện tại, viết rõ semantics cần có và kiểm chứng bằng một test tích hợp.

## 13. Phân tích kết quả và chọn thứ tự phù hợp

Sau khi chạy, điền số liệu thực tế vào bảng:

| Chỉ số | CB ngoài / Retry trong | Retry ngoài / CB trong |
|---|---:|---:|
| Logical operations trước khi OPEN |  |  |
| Dependency attempts trước khi OPEN |  |  |
| CB failures trước khi OPEN |  |  |
| CB not-permitted |  |  |
| Retry attempts |  |  |
| Fallback count |  |  |
| p95 operation latency |  |  |
| State transition time |  |  |

Dùng các câu hỏi sau để diễn giải:

1. Circuit Breaker đang đếm operation logic hay từng attempt?
2. Khi Retry thành công sau một hoặc nhiều lỗi, failure rate của Circuit Breaker thay đổi ra sao?
3. Circuit Breaker có mở giữa chuỗi Retry hay chỉ sau khi Retry kết thúc?
4. CallNotPermittedException có làm Retry dừng ngay không?
5. Số dependency attempts có khớp với số request mà HTTP stub nhận không?
6. Fallback có chạy sau toàn bộ Retry hay chạy trong từng attempt?
7. Thứ tự nào giảm request đến backend nhanh hơn khi backend liên tục lỗi?
8. Thứ tự nào phản ánh chính xác hơn tỷ lệ operation thất bại mà caller trải nghiệm?

Nếu ưu tiên đánh giá kết quả cuối cùng sau chính sách Retry, Circuit Breaker ngoài Retry thường dễ diễn giải. Nếu ưu tiên ghi nhận từng attempt và mở mạch sớm để giảm tải backend, Retry ngoài Circuit Breaker có thể phù hợp, với điều kiện exception từ chối được bỏ qua và fallback không nuốt lỗi quá sớm.

## 14. Những lỗi thực hành thường gặp

1. **Dùng chung Circuit Breaker ID cho hai scenario.** State từ lần chạy trước làm sai số liệu lần chạy sau; dùng instance riêng.
2. **Chỉ đếm số operation logic.** Một operation có thể tạo nhiều attempt; đo riêng request đến dependency.
3. **Retry ngoài nhưng không bỏ qua CallNotPermittedException.** Retry tiếp tục thử một bộ ngắt đang OPEN và tạo nhiều lần từ chối.
4. **Fallback trả giá trị thành công quá sớm.** Retry không còn thấy exception và dừng trước khi thực hiện lần thử tiếp theo.
5. **Nhầm not permitted với dependency failure.** Lời gọi bị Circuit Breaker chặn chưa hề đến backend.
6. **Không đặt minimumNumberOfCalls phù hợp.** Bộ ngắt có thể chưa đủ mẫu để mở hoặc mở sớm hơn dự kiến.
7. **So sánh các scenario với failure schedule khác nhau.** Kết quả không còn phản ánh tác động của thứ tự decorator.
8. **Không reset dependency counter và metrics.** Số liệu bị cộng dồn qua nhiều lần chạy.
9. **Dùng annotation nhưng giả định aspect order.** Thứ tự thực tế cần được xác minh bằng test.
10. **Retry thao tác ghi không idempotent.** Có thể tạo tác dụng phụ lặp khi response bị mất hoặc timeout.

## Kết luận

Đặt Circuit Breaker ngoài Retry khiến bộ ngắt ghi nhận kết quả cuối cùng của một operation sau khi Retry kết thúc. Đặt Retry ngoài Circuit Breaker khiến từng attempt đi qua bộ ngắt và có thể được ghi vào sliding window riêng. Cách thứ hai có thể mở mạch sớm hơn, nhưng Retry phải bỏ qua **CallNotPermittedException** để dừng ngay khi bộ ngắt từ chối. Khi thực hành, hãy dùng instance độc lập, cùng failure schedule và đo riêng logical operations, dependency attempts, Circuit Breaker failures, not-permitted calls, Retry attempts và fallback để chọn thứ tự theo mục tiêu vận hành.
