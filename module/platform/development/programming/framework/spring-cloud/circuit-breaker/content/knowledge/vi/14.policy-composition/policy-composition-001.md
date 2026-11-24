# Thứ tự bao Circuit Breaker và Retry thay đổi mẫu thống kê

Khi một dịch vụ phụ thuộc gặp lỗi thoáng qua, Retry có thể gọi lại để tăng khả năng thành công. Circuit Breaker theo dõi kết quả lời gọi và ngắt mạch khi dependency có dấu hiệu không khỏe. Hai chính sách này thường được kết hợp, nhưng thứ tự bao quanh lời gọi quyết định Circuit Breaker nhìn thấy từng lần thử hay nhìn thấy kết quả cuối cùng của cả chuỗi thử lại.

Có hai cách lồng phổ biến:

- **Retry ở ngoài, Circuit Breaker ở trong:** mỗi lần thử đi qua Circuit Breaker. Circuit Breaker ghi nhận từng attempt.
- **Circuit Breaker ở ngoài, Retry ở trong:** Circuit Breaker bao trọn chuỗi retry. Nó ghi nhận một kết quả cuối cùng cho mỗi request logic.

Sự khác biệt này ảnh hưởng trực tiếp đến số mẫu trong sliding window, failure rate, slow-call rate, thời điểm mở mạch và lượng tải gửi đến dependency. Bài học giải thích hai thứ tự, minh họa bằng Resilience4j và cách chọn chính sách phù hợp trong Spring Cloud.

## 1. Vai trò của Retry và Circuit Breaker

Retry và Circuit Breaker giải quyết hai vấn đề khác nhau.

**Retry** thực hiện lại một lời gọi khi gặp lỗi được xem là có thể phục hồi. Ví dụ lỗi kết nối tạm thời hoặc HTTP 503 trong một khoảng thời gian ngắn. Retry thường có giới hạn số lần thử, thời gian chờ giữa các lần thử và điều kiện xác định exception nào được thử lại.

**Circuit Breaker** theo dõi các lần gọi đi qua nó. Khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm trong sliding window vượt ngưỡng và đủ số mẫu tối thiểu, nó chuyển sang OPEN để từ chối lời gọi mới. Sau thời gian chờ, nó có thể chuyển sang HALF_OPEN để thăm dò dependency.

Có thể phân biệt bằng câu hỏi:

| Chính sách | Câu hỏi chính |
| --- | --- |
| Retry | Lỗi này có đáng để thử lại không, và thử tối đa bao nhiêu lần? |
| Circuit Breaker | Với tình trạng gần đây của dependency, có nên tiếp tục gửi lời gọi không? |

Retry có thể giúp vượt qua lỗi tạm thời. Nhưng nếu dependency đang gặp sự cố kéo dài, nhiều request cùng retry có thể khuếch đại tải. Circuit Breaker giới hạn việc tiếp tục gọi khi bằng chứng cho thấy dependency không khỏe.

## 2. Thứ tự bao quyết định đơn vị được thống kê

Hãy coi mỗi request nghiệp vụ là một lần gọi logic. Request đó có thể tạo một hoặc nhiều attempt đến Inventory.

~~~text
Một request logic
       |
       v
      Retry
       |
       +---- attempt 1
       |        |
       |        v
       |   Circuit Breaker
       |        |
       |        v
       |   Inventory
       |
       +---- attempt 2
       |        |
       |        v
       |   Circuit Breaker
       |        |
       |        v
       |   Inventory
       |
       +---- attempt 3 ...
~~~

Sơ đồ trên mô tả Retry ở ngoài và Circuit Breaker ở trong. Mỗi attempt đi qua Circuit Breaker, do đó mỗi kết quả attempt có thể trở thành một mẫu trong sliding window.

Nếu đảo thứ tự:

~~~text
Một request logic
       |
       v
Circuit Breaker
       |
       v
      Retry
       |
       +---- attempt 1 ---> Inventory
       |
       +---- attempt 2 ---> Inventory
       |
       +---- attempt 3 ---> Inventory
       |
       v
Kết quả cuối cùng của Retry
~~~

Circuit Breaker chỉ nhận kết quả sau khi Retry hoàn tất. Ba attempt bên trong được xem như một lần thực thi của supplier được bảo vệ. Nếu một attempt thất bại nhưng attempt sau thành công, Circuit Breaker nhận kết quả thành công.

## 3. Retry ở ngoài, Circuit Breaker ở trong

Cách lồng này có dạng:

~~~java
Supplier<Inventory> protectedAttempt =
    CircuitBreaker.decorateSupplier(circuitBreaker, inventoryClient::getInventory);

Supplier<Inventory> retriedCall =
    Retry.decorateSupplier(retry, protectedAttempt);

Inventory result = retriedCall.get();
~~~

Retry gọi supplier được bảo vệ nhiều lần. Mỗi lần Retry thực hiện attempt mới, supplier bên trong lại đi qua Circuit Breaker.

### 3.1. Circuit Breaker ghi nhận từng attempt

Giả sử Retry cho phép tối đa 3 lần thử và mỗi attempt đều thất bại:

| Request logic | Attempt | Kết quả được Circuit Breaker ghi nhận |
| --- | ---: | --- |
| Request A | 1 | Failure |
| Request A | 2 | Failure |
| Request A | 3 | Failure |
| Request B | 1 | Failure |
| Request B | 2 | Failure |
| Request B | 3 | Failure |

Chỉ hai request logic đã tạo ra sáu mẫu lỗi trong sliding window. Nếu cửa sổ có kích thước 10 và minimumNumberOfCalls là 5, Circuit Breaker có thể đạt đủ mẫu sau một phần của request thứ hai, tùy thời điểm và kết quả cụ thể.

Điều này khiến Circuit Breaker phản ứng nhanh hơn với lỗi lặp lại ở cấp attempt. Nó cũng có nghĩa một request nghiệp vụ có thể đóng góp nhiều mẫu vào cùng một cửa sổ.

### 3.2. Ưu điểm và giới hạn

Ưu điểm:

- Circuit Breaker nhìn thấy từng lần gọi đến dependency, kể cả các lỗi được Retry khắc phục sau đó.
- Failure rate phản ánh mức độ lỗi ở cấp attempt.
- Một chuỗi lỗi liên tục có thể làm Circuit Breaker mở mạch sớm.

Giới hạn:

- Một request logic có thể tạo nhiều mẫu, nên sliding window không còn tương đương với số request người dùng.
- Khi Circuit Breaker chuyển sang OPEN sau một attempt thất bại, lần thử tiếp theo có thể bị từ chối bằng CallNotPermittedException.
- Nếu Retry tiếp tục thử lại CallNotPermittedException, nó chỉ lặp lại một lời gọi đã bị Circuit Breaker chặn và làm tăng độ trễ vô ích.

Khi dùng thứ tự này, cần cấu hình Retry bỏ qua CallNotPermittedException. Đây là lỗi từ cơ chế bảo vệ tại caller, không phải một lỗi transient cần gửi lại đến dependency.

## 4. Circuit Breaker ở ngoài, Retry ở trong

Cách lồng này có dạng:

~~~java
Supplier<Inventory> retriedCall =
    Retry.decorateSupplier(retry, inventoryClient::getInventory);

Supplier<Inventory> protectedRequest =
    CircuitBreaker.decorateSupplier(circuitBreaker, retriedCall);

Inventory result = protectedRequest.get();
~~~

Circuit Breaker gọi Retry một lần. Retry thực hiện các attempt bên trong và trả về kết quả cuối cùng hoặc ném exception sau khi hết số lần thử. Circuit Breaker chỉ ghi nhận kết quả cuối cùng đó.

### 4.1. Circuit Breaker ghi nhận một kết quả cho request logic

Giả sử Retry cho phép tối đa 3 lần thử:

| Request logic | Các attempt | Kết quả Retry trả ra | Mẫu Circuit Breaker |
| --- | --- | --- | --- |
| Request A | Failure, Success | Success | Success |
| Request B | Failure, Failure, Success | Success | Success |
| Request C | Failure, Failure, Failure | Failure | Failure |

Mặc dù dependency đã trả về nhiều lỗi ở các attempt đầu, Circuit Breaker chỉ ghi một mẫu thành công cho Request A và Request B. Request C tạo một mẫu lỗi sau khi Retry hết lượt.

Cách này khiến failure rate của Circuit Breaker phản ánh tỷ lệ request logic cuối cùng không thể hoàn thành sau retry, thay vì tỷ lệ attempt thất bại.

### 4.2. Ưu điểm và giới hạn

Ưu điểm:

- Sliding window gần với số request logic mà tầng gọi quan tâm.
- Một lỗi transient được Retry khắc phục không làm tăng failure rate của Circuit Breaker.
- Circuit Breaker chỉ mở mạch khi cả chuỗi thử lại vẫn thất bại hoặc chậm.

Giới hạn:

- Circuit Breaker có thể phản ứng chậm hơn vì phải chờ Retry hoàn tất mới có một mẫu.
- Lỗi ở các attempt đầu không xuất hiện trong failure rate của Circuit Breaker; cần dùng Retry metrics hoặc log để quan sát.
- Thời gian thực thi của supplier bên trong Circuit Breaker bao gồm cả các lần thử và thời gian chờ giữa chúng.

Nếu Retry có backoff dài, Circuit Breaker ở ngoài có thể đánh giá một request là slow call dù từng HTTP attempt riêng lẻ đều nhanh. Đây là hành vi có thể mong muốn nếu mục tiêu là bảo vệ latency của request logic.

## 5. So sánh ảnh hưởng đến sliding window

Xét cấu hình Circuit Breaker có:

- slidingWindowType là COUNT_BASED.
- slidingWindowSize là 10.
- minimumNumberOfCalls là 5.
- failureRateThreshold là 50%.

Giả sử mỗi request logic có tối đa 3 attempt và cả ba attempt đều thất bại.

| Cách lồng | Số mẫu Circuit Breaker sau 2 request logic | Failure rate | Ý nghĩa |
| --- | ---: | ---: | --- |
| Retry ngoài, Circuit Breaker trong | Có thể đạt 6 mẫu lỗi nếu tất cả attempt đều được phép chạy | 100% | Đánh giá lỗi theo từng attempt |
| Circuit Breaker ngoài, Retry trong | 2 mẫu lỗi | 100% | Đánh giá lỗi theo request logic |

Trong ví dụ, failure rate đều là 100%, nhưng số mẫu khác nhau. Với minimumNumberOfCalls bằng 5, cách thứ nhất có thể đủ mẫu để đánh giá sau chưa đến hai request logic; cách thứ hai cần ít nhất năm request logic nếu mỗi request tạo một mẫu.

Nếu attempt đầu thất bại và attempt thứ hai thành công:

- Retry ngoài, Circuit Breaker trong ghi một failure và một success.
- Circuit Breaker ngoài, Retry trong ghi một success.

Đây là khác biệt cốt lõi. Cùng một hành vi của dependency có thể tạo ra failure rate khác nhau chỉ vì thứ tự bao chính sách thay đổi.

## 6. Slow-call rate cũng bị ảnh hưởng

Circuit Breaker có thể đánh giá cả failure rate và slow-call rate. Thứ tự bao ảnh hưởng đến thời lượng mà Circuit Breaker đo.

**Retry ngoài, Circuit Breaker trong:**

- Mỗi attempt được đo riêng.
- Thời gian backoff nằm giữa các lần gọi và không nằm trong thời lượng của từng supplier được Circuit Breaker bảo vệ.
- Một attempt nhanh nhưng thất bại vẫn có thể là failure; một attempt chậm có thể được tính là slow call.

**Circuit Breaker ngoài, Retry trong:**

- Circuit Breaker đo toàn bộ thời gian Retry thực hiện.
- Thời gian của các attempt cộng với thời gian backoff nằm trong một lần thực thi được bảo vệ.
- Một request có thể bị xem là slow call dù từng attempt riêng lẻ đều thấp hơn slowCallDurationThreshold.

Ví dụ:

- Mỗi lần gọi HTTP mất 300 ms.
- Retry có 3 attempt.
- Giữa các attempt có hai khoảng chờ, mỗi khoảng 400 ms.

Tổng thời gian của chuỗi Retry xấp xỉ:

\[
3 \times 300\text{ ms} + 2 \times 400\text{ ms}
= 1{,}700\text{ ms}
\]

Nếu slowCallDurationThreshold là 1 giây:

- Khi Circuit Breaker ở trong Retry, mỗi attempt 300 ms không bị xem là slow call.
- Khi Circuit Breaker bao ngoài Retry, toàn bộ chuỗi khoảng 1,7 giây có thể được xem là một slow call.

Vì vậy, cần xác định mục tiêu thống kê là độ trễ của một lần gọi mạng hay độ trễ mà request nghiệp vụ thực sự phải chờ.

## 7. Cấu hình Retry có kiểm soát

Không nên thử lại mọi exception. Retry chỉ nên áp dụng cho lỗi có khả năng phục hồi và thao tác an toàn khi thực hiện nhiều lần.

Ví dụ cấu hình Resilience4j:

~~~yaml
resilience4j:
  retry:
    instances:
      inventory:
        maxAttempts: 3
        waitDuration: 200ms
        enableExponentialBackoff: true
        exponentialBackoffMultiplier: 2
        retryExceptions:
          - org.springframework.web.client.ResourceAccessException
          - org.springframework.web.client.HttpServerErrorException
        ignoreExceptions:
          - io.github.resilience4j.circuitbreaker.CallNotPermittedException

  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Các giá trị chỉ là ví dụ cho môi trường thực hành. maxAttempts thường tính cả lần gọi đầu tiên, do đó giá trị 3 tương đương tối đa ba attempt, không phải một lần gọi cộng thêm ba lần retry.

Các điểm cần chú ý:

- ResourceAccessException có thể đại diện cho lỗi truy cập mạng hoặc timeout ở Spring HTTP client.
- HttpServerErrorException đại diện cho lỗi HTTP 5xx; trong production nên cân nhắc chính xác status nào có thể thử lại.
- Không nên thử lại lỗi nghiệp vụ 4xx như dữ liệu không hợp lệ hoặc không có quyền.
- CallNotPermittedException nên được bỏ qua trong Retry khi Circuit Breaker nằm bên trong Retry.
- Nếu API hỗ trợ Retry-After, nên tôn trọng hướng dẫn của server thay vì luôn dùng một khoảng chờ cố định.

Đối với thao tác ghi dữ liệu, gửi thanh toán hoặc tạo đơn hàng, chỉ retry khi API có cơ chế idempotency phù hợp. Nếu không, một lần thử đầu có thể đã được server xử lý nhưng response bị mất; retry có thể tạo giao dịch trùng lặp.

## 8. Cấu hình Circuit Breaker và cách đọc metrics

Circuit Breaker dùng sliding window để đánh giá các kết quả mà nó trực tiếp bao quanh. Với COUNT_BASED, mỗi lần hoàn tất supplier được bảo vệ đóng góp một mẫu. Với TIME_BASED, kết quả được tổng hợp theo các bucket thời gian.

Các metrics thường cần quan sát gồm:

- Số lời gọi thành công.
- Số lời gọi thất bại.
- Số lời gọi bị từ chối do Circuit Breaker OPEN.
- Failure rate và slow-call rate.
- Số lần chuyển trạng thái.
- Số attempt và kết quả retry từ Retry metrics.

Khi Retry ở ngoài Circuit Breaker, tổng số lời gọi mà Circuit Breaker ghi nhận có thể lớn hơn số request logic. Hãy đặt tên dashboard và alert rõ ràng để tránh diễn giải attempt failure rate thành tỷ lệ request người dùng thất bại.

Khi Circuit Breaker ở ngoài Retry, số mẫu Circuit Breaker gần với số request logic. Tuy nhiên, Retry metrics vẫn cần thiết để thấy dependency có thường xuyên thất bại ở attempt đầu hay không. Một hệ thống có 99% request cuối cùng thành công nhưng thường xuyên cần ba attempt vẫn có thể đang gặp vấn đề về độ ổn định và độ trễ.

Không nên chỉ nhìn vào failure rate của Circuit Breaker. Hãy đặt cạnh nhau:

| Chỉ số | Câu hỏi giúp trả lời |
| --- | --- |
| Circuit Breaker failure rate | Bao nhiêu lần thực thi được bảo vệ thất bại theo ranh giới đã chọn? |
| Retry attempts | Một request cần bao nhiêu lần gọi để hoàn tất? |
| Retry success after retry | Bao nhiêu lỗi ban đầu được khắc phục nhờ thử lại? |
| End-to-end latency | Người dùng thực sự phải chờ bao lâu? |
| Rejected calls | Có bao nhiêu lời gọi bị Circuit Breaker từ chối? |

## 9. Minh họa bằng Resilience4j Decorators

Có thể dùng Resilience4j Decorators để thể hiện thứ tự rõ ràng trong code. Giả sử đã có CircuitBreaker, Retry và supplier gọi Inventory:

~~~java
Supplier<InventoryResponse> remoteCall =
    () -> inventoryClient.getInventory("SKU-001");
~~~

### 9.1. Retry ngoài, Circuit Breaker trong

~~~java
Supplier<InventoryResponse> circuitProtectedAttempt =
    CircuitBreaker.decorateSupplier(circuitBreaker, remoteCall);

Supplier<InventoryResponse> retryAroundCircuitBreaker =
    Retry.decorateSupplier(retry, circuitProtectedAttempt);

InventoryResponse result = retryAroundCircuitBreaker.get();
~~~

Đọc từ ngoài vào trong: Retry bao supplier đã được Circuit Breaker bảo vệ. Mỗi lần Retry gọi supplier, Circuit Breaker nhận một attempt.

### 9.2. Circuit Breaker ngoài, Retry trong

~~~java
Supplier<InventoryResponse> retriedSequence =
    Retry.decorateSupplier(retry, remoteCall);

Supplier<InventoryResponse> circuitAroundRetry =
    CircuitBreaker.decorateSupplier(circuitBreaker, retriedSequence);

InventoryResponse result = circuitAroundRetry.get();
~~~

Đọc từ ngoài vào trong: Circuit Breaker bao supplier đã được Retry. Circuit Breaker nhận một kết quả sau khi Retry kết thúc.

Hai ví dụ dùng cùng một loại decorator, nhưng thứ tự lồng khác nhau. Khi chạy thử, hãy dùng hai tên instance riêng hoặc reset ứng dụng giữa các kịch bản để sliding window và trạng thái của lần thử trước không làm sai kết quả quan sát.

## 10. Tích hợp trong service Spring Cloud

Spring Cloud CircuitBreaker cung cấp CircuitBreakerFactory để tạo Circuit Breaker theo tên. Có thể đặt Retry bên trong lời gọi được factory bảo vệ:

~~~java
@Service
public class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RetryRegistry retryRegistry;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RetryRegistry retryRegistry,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.retryRegistry = retryRegistry;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResponse getInventory(String sku) {
        Retry retry = retryRegistry.retry("inventory");

        return circuitBreakerFactory.create("inventory").run(
            () -> retry.executeSupplier(
                () -> inventoryClient.getInventory(sku)
            ),
            error -> InventoryResponse.unavailable(sku)
        );
    }
}
~~~

Trong ví dụ này Circuit Breaker của Spring Cloud bao ngoài chuỗi Retry. Supplier được bảo vệ chỉ hoàn tất sau khi Retry trả kết quả hoặc ném lỗi. Fallback của Circuit Breaker được gọi khi chuỗi Retry thất bại hoặc Circuit Breaker từ chối lời gọi.

Nếu muốn Retry ở ngoài Circuit Breaker, cần để mỗi lần thử gọi vào một Circuit Breaker và bảo đảm lỗi được truyền ra ngoài để Retry đánh giá. Không nên đặt fallback trả về một giá trị thành công bên trong mỗi attempt, vì Retry sẽ nhìn thấy kết quả thành công và dừng ngay cả khi đó chỉ là fallback.

Một cách biểu diễn ở cấp Resilience4j là dùng trực tiếp CircuitBreakerRegistry và RetryRegistry với Decorators như phần trước. Khi sử dụng Spring Cloud factory, hãy xác định rõ fallback nằm ở lớp nào và exception nào được truyền qua từng lớp.

## 11. Fallback nằm ở đâu cũng làm thay đổi hành vi

Fallback là một kết quả thay thế khi lời gọi không thành công hoặc bị từ chối. Vị trí của fallback ảnh hưởng đến Retry:

- **Fallback bên trong Retry:** nếu fallback chuyển exception thành một giá trị bình thường, Retry coi attempt đó là thành công và không thử lại.
- **Fallback bên ngoài Retry:** Retry có cơ hội thực hiện đủ các attempt; fallback chỉ chạy sau khi Retry hết lượt và vẫn thất bại.
- **Fallback của Circuit Breaker:** nếu Circuit Breaker nằm ngoài Retry, fallback nhận lỗi cuối cùng của chuỗi Retry hoặc lỗi từ trạng thái OPEN.

Ví dụ không nên làm:

~~~java
Supplier<InventoryResponse> attemptWithFallback = () ->
    inventoryClient.getInventory("SKU-001")
        .orElse(InventoryResponse.unavailable("SKU-001"));
~~~

Nếu hàm trên luôn trả về một giá trị hợp lệ ngay cả khi dependency thất bại, Retry không thể biết rằng cần thử lại. Hãy giữ exception hoặc một kiểu kết quả lỗi được Retry predicate nhận diện cho đến khi Retry hoàn tất; sau đó mới áp dụng fallback.

Fallback cũng cần phân biệt lỗi dependency với lỗi quá tải cục bộ hoặc lỗi nghiệp vụ. Không nên biến mọi exception thành một response thành công mà không ghi rõ trạng thái dữ liệu dự phòng.

## 12. Retry có thể khuếch đại tải

Retry làm tăng số lời gọi đến dependency. Nếu nhiều tầng trong chuỗi đều retry, số attempt có thể nhân lên.

Ví dụ một request đi qua ba tầng, mỗi tầng cho phép tối đa 3 attempt. Trong tình huống xấu nhất, số lời gọi đến tầng cuối có thể lên đến:

\[
3 \times 3 \times 3 = 27
\]

Đây là lý do nên xác định một tầng chịu trách nhiệm retry cho mỗi dependency, giới hạn số lần thử, dùng backoff và jitter, đồng thời đặt timeout tổng thể.

Circuit Breaker ở trong Retry có thể nhìn thấy nhiều attempt và mở mạch sớm. Nhưng khi đã OPEN, Retry phải dừng ngay khi gặp CallNotPermittedException. Circuit Breaker ở ngoài Retry tránh ghi từng attempt vào sliding window, nhưng Retry vẫn tiếp tục tạo tải cho đến khi chuỗi kết thúc hoặc timeout.

Cả hai thứ tự đều cần có giới hạn. Circuit Breaker không thay thế retry budget, và Retry không thay thế Circuit Breaker.

## 13. Cách chọn thứ tự phù hợp

| Mục tiêu | Thứ tự thường phù hợp | Lý do |
| --- | --- | --- |
| Đánh giá sức khỏe dependency theo từng lần gọi thực tế | Retry ngoài, Circuit Breaker trong | Mỗi attempt là một mẫu, kể cả lỗi được retry khắc phục |
| Đánh giá tỷ lệ request nghiệp vụ thất bại cuối cùng | Circuit Breaker ngoài, Retry trong | Mỗi request logic tạo một mẫu cuối cùng |
| Mở mạch nhanh khi dependency liên tục lỗi ở từng attempt | Retry ngoài, Circuit Breaker trong | Failure samples tăng theo số attempt |
| Đánh giá latency mà request phải chờ sau mọi lần retry | Circuit Breaker ngoài, Retry trong | Circuit Breaker đo cả thời gian retry và backoff |
| Theo dõi lỗi transient đã được retry khắc phục | Cả hai thứ tự đều cần Retry metrics | Circuit Breaker có thể không phản ánh các lỗi trung gian nếu nó bao ngoài Retry |

Không có thứ tự đúng cho mọi hệ thống. Hãy chọn theo ý nghĩa mà đội vận hành muốn gán cho failure rate và slow-call rate. Nếu muốn thống kê theo request người dùng, Circuit Breaker ngoài Retry thường dễ diễn giải hơn. Nếu muốn thống kê theo từng attempt gửi đến dependency, đặt Circuit Breaker trong Retry.

## 14. Kịch bản kiểm chứng hai cách lồng

Có thể tạo một supplier giả lập với chuỗi kết quả xác định:

- Attempt 1 thất bại bằng lỗi kết nối.
- Attempt 2 thành công.
- Request tiếp theo thất bại cả ba attempt.

Dùng hai bộ Circuit Breaker và Retry riêng biệt để chạy cùng kịch bản. Ghi lại số lần supplier được gọi, số mẫu Circuit Breaker, số lần Retry và trạng thái sau mỗi request.

Kết quả kỳ vọng:

| Kịch bản | Retry ngoài, Circuit Breaker trong | Circuit Breaker ngoài, Retry trong |
| --- | --- | --- |
| Request có attempt 1 lỗi, attempt 2 thành công | Circuit Breaker ghi một failure và một success | Circuit Breaker ghi một success |
| Request có ba attempt đều lỗi | Circuit Breaker ghi tối đa ba failure nếu cả ba attempt được phép | Circuit Breaker ghi một failure |
| Retry mở rộng thời gian bằng backoff | Mỗi attempt được đo riêng bởi Circuit Breaker | Tổng thời gian retry được đo như một lần gọi |
| Circuit Breaker đã OPEN | Attempt kế tiếp bị từ chối; Retry phải bỏ qua CallNotPermittedException | Supplier Retry không được bắt đầu vì Circuit Breaker từ chối từ bên ngoài |

Khi chạy thực tế, có thể có ít attempt hơn dự kiến nếu Circuit Breaker mở giữa chuỗi retry hoặc Retry predicate quyết định dừng sớm. Đó chính là hành vi cần quan sát, không phải sai lệch của phép thử.

## 15. Những nguyên tắc thiết kế

- Xác định sliding window cần đại diện cho attempt hay request logic.
- Chọn thứ tự bao trước khi tinh chỉnh minimumNumberOfCalls và failureRateThreshold.
- Giới hạn maxAttempts; nhớ rằng số này thường bao gồm lần gọi đầu tiên.
- Chỉ retry lỗi transient và thao tác an toàn để thử lại.
- Bỏ qua CallNotPermittedException trong Retry khi Circuit Breaker nằm bên trong Retry.
- Đặt fallback sau Retry nếu muốn Retry có cơ hội xử lý lỗi trước.
- Theo dõi cả Retry metrics và Circuit Breaker metrics.
- Đánh giá slow-call rate theo thời lượng attempt hoặc thời lượng toàn request tùy thứ tự bao.
- Dùng backoff, jitter, timeout tổng thể và retry budget để tránh khuếch đại tải.
- Kiểm thử cả trường hợp retry thành công, retry hết lượt và Circuit Breaker mở giữa chuỗi.

Thứ tự bao Retry và Circuit Breaker quyết định đơn vị mà Circuit Breaker ghi vào sliding window. Retry ở ngoài khiến mỗi attempt trở thành một mẫu; Circuit Breaker ở ngoài khiến mỗi chuỗi retry trở thành một mẫu cuối cùng. Hiểu rõ khác biệt này giúp chọn ngưỡng, đọc metrics và thiết kế fallback đúng với mục tiêu bảo vệ dependency của ứng dụng Spring Cloud.

## Tài liệu tham khảo

- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j Decorators](https://resilience4j.readme.io/docs/getting-started-3)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)

