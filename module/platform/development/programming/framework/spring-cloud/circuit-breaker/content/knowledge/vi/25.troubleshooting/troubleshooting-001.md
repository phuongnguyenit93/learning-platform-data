# Bộ ngắt mạch không mở vì chưa đủ mẫu hoặc cấu hình sai ID

Một circuit breaker có thể tiếp tục ở trạng thái `CLOSED` dù dịch vụ phụ thuộc đang trả lỗi. Hai nguyên nhân cần kiểm tra sớm là **chưa có đủ mẫu để đánh giá tỷ lệ** và **cấu hình đang gắn với một ID khác ID mà ứng dụng thực sự tạo ra**. Ngoài ra, exception có thể bị bỏ qua, response lỗi có thể được coi là kết quả thành công, hoặc reactive pipeline có thể phục hồi lỗi trước khi circuit breaker quan sát.

Với Spring Cloud CircuitBreaker sử dụng Resilience4j, không nên bắt đầu bằng cách giảm ngay `failureRateThreshold`. Hãy xác minh đúng circuit breaker instance, cấu hình runtime, số kết quả được ghi nhận và thời điểm đánh giá. Bài này trình bày một quy trình chẩn đoán có thể áp dụng cho service đồng bộ, WebClient/Reactor và OpenFeign.

## 1. Hiểu điều kiện để circuit breaker chuyển sang OPEN

Ở trạng thái `CLOSED`, circuit breaker cho phép lời gọi đi qua và thu thập kết quả. Resilience4j chỉ tính failure rate hoặc slow-call rate sau khi số kết quả trong sliding window đạt `minimumNumberOfCalls`.

Ví dụ:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
```

Với cấu hình trên:

- Cửa sổ giữ tối đa 20 kết quả gần nhất.
- Cần ít nhất 10 kết quả trong cửa sổ trước khi đánh giá tỷ lệ.
- Khi đủ mẫu, circuit breaker mở nếu failure rate đạt hoặc vượt 50%.

Nếu mới có 8 lời gọi và cả 8 đều thất bại, tỷ lệ quan sát được là 100%, nhưng circuit breaker chưa đủ 10 mẫu để đánh giá. Việc nó vẫn ở `CLOSED` trong tình huống này là hành vi đúng theo cấu hình.

Có thể diễn giải điều kiện cơ bản như sau:

\[
\text{Đủ điều kiện đánh giá} \iff N_{recorded} \geq minimumNumberOfCalls
\]

\[
\text{Mở mạch do lỗi} \iff failureRate \geq failureRateThreshold
\]

Trong đó `N_recorded` là số kết quả được ghi nhận trong cửa sổ hiện tại. Nó không nhất thiết bằng tổng số request đến ứng dụng: các request bị từ chối trước khi supplier chạy và exception bị ignore không đóng góp như một failure thông thường.

## 2. Phân biệt slidingWindowSize và minimumNumberOfCalls

Hai thuộc tính này thường bị nhầm lẫn:

| Thuộc tính | COUNT_BASED | TIME_BASED |
|---|---|---|
| `slidingWindowSize` | Số lời gọi gần nhất được giữ trong cửa sổ. | Độ dài cửa sổ tính bằng giây. |
| `minimumNumberOfCalls` | Số kết quả tối thiểu cần có trước khi đánh giá. | Vẫn là số kết quả tối thiểu cần có trong cửa sổ thời gian. |

Với `COUNT_BASED`, cấu hình `slidingWindowSize: 20` và `minimumNumberOfCalls: 10` cho phép bắt đầu đánh giá khi có 10 kết quả, không cần chờ đủ 20. Khi cửa sổ đã đầy, kết quả mới thay thế kết quả cũ nhất.

Với `TIME_BASED`, giả sử `slidingWindowSize: 10` và `minimumNumberOfCalls: 20`. Circuit breaker cần có ít nhất 20 kết quả trong 10 giây gần nhất. Nếu instance chỉ nhận trung bình một lời gọi mỗi giây, điều kiện này khó đạt. Circuit breaker có thể tiếp tục `CLOSED` dù phần lớn lời gọi bị lỗi vì cửa sổ không bao giờ có đủ mẫu.

Hãy kiểm tra `minimumNumberOfCalls` không lớn hơn sức chứa có thể đạt của cửa sổ. Với count-based window, giá trị tối thiểu không thể lớn hơn kích thước cửa sổ. Với time-based window, hãy ước lượng số lời gọi trên từng instance trong khoảng thời gian cấu hình, không dùng tổng lưu lượng của toàn cụm.

## 3. Kiểm tra ID được tạo trong mã có khớp YAML không

Resilience4j áp dụng cấu hình instance theo ID. Nếu mã tạo circuit breaker bằng `create("inventory")`, nhưng YAML chỉ khai báo `inventoryReadClient`, cấu hình riêng cho `inventoryReadClient` không tự động áp dụng cho instance `inventory`.

Ví dụ có thể bị lệch ID:

```java
return circuitBreakerFactory.create("inventory").run(
    () -> inventoryClient.getStock(sku),
    error -> Stock.unavailable(sku)
);
```

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryReadClient:
        slidingWindowSize: 20
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
```

Ở đây, mã tạo ID `inventory`, còn cấu hình riêng được đặt dưới `inventoryReadClient`. Circuit breaker `inventory` có thể đang dùng cấu hình mặc định hoặc cấu hình khác; các giá trị trong `inventoryReadClient` không điều khiển instance đó.

Hãy dùng cùng một ID ở nơi tạo breaker và nơi khai báo cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 20
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
```

ID cần nhất quán cả trong Java Customizer, properties, event listener, metrics dashboard và alert rule. Nên dùng ID ổn định theo dependency và nhóm thao tác, chẳng hạn `inventory-read` hoặc `payment-authorize`; tránh ghép ID với SKU, user ID hay request ID.

## 4. Với OpenFeign, không đoán tên circuit breaker

Khi bật Spring Cloud CircuitBreaker cho OpenFeign, tên breaker có thể được tạo từ client và method thông qua quy tắc đặt tên của phiên bản Spring Cloud đang dùng. Vì vậy, không nên mặc định tên breaker luôn bằng `name` hoặc `contextId` của `@FeignClient`.

Ví dụ client:

```java
@FeignClient(
    name = "inventory-service",
    contextId = "inventoryReadClient"
)
public interface InventoryReadClient {
    Stock getStock(String sku);
}
```

Một lời gọi Feign có thể tạo breaker ID gắn với client và method. Quy tắc này có thể được tùy chỉnh bằng `CircuitBreakerNameResolver`; một số phiên bản còn hỗ trợ chuyển ID sang dạng alphanumeric. Khi cấu hình Resilience4j, cần lấy **ID thực tế được tạo lúc runtime** rồi dùng đúng tên đó trong `resilience4j.circuitbreaker.instances`.

Quy trình xác minh:

1. Kiểm tra `spring.cloud.openfeign.circuitbreaker.enabled` đã bật nếu muốn OpenFeign gọi qua Spring Cloud CircuitBreaker.
2. Xác định có `CircuitBreakerNameResolver` tùy chỉnh hay không.
3. Kiểm tra tùy chọn `alphanumeric-ids` nếu phiên bản hỗ trợ.
4. Quan sát log, event hoặc metrics để lấy tên breaker thực tế.
5. Đối chiếu chính xác tên đó với khóa instance trong YAML.

Group support không tự động có nghĩa mọi method của một Feign client dùng chung một circuit breaker ID. Group name và breaker ID là hai thông tin riêng; hãy kiểm tra cách factory/provider của phiên bản đang dùng sử dụng chúng.

## 5. Kiểm tra cấu hình runtime thay vì chỉ đọc YAML

Một file YAML đúng cú pháp chưa chứng minh cấu hình đã được bind vào instance đang chạy. Có thể có nhiều profile, file cấu hình ngoài, biến môi trường hoặc nguồn cấu hình khác ghi đè giá trị.

Hãy kiểm tra:

- Profile đang hoạt động và file `application-{profile}.yml` được nạp.
- Tên instance trong YAML có trùng ID runtime không.
- Cấu hình `default` và `instances` có bị hiểu nhầm hoặc ghi đè không.
- Java `Customizer` có cấu hình cùng ID không.
- Thứ tự ưu tiên giữa properties và Java Customizer theo release train Spring Cloud đang sử dụng.
- Có biến môi trường hoặc cấu hình externalized ghi đè các giá trị không.

Ví dụ, khi cần một cấu hình nền và một instance riêng:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventory:
        baseConfig: default
        minimumNumberOfCalls: 5
```

Instance `inventory` dùng cấu hình nền rồi ghi đè `minimumNumberOfCalls`. Nếu một Java Customizer hoặc profile khác cũng cấu hình ID này, hãy xác định nguồn nào đang có hiệu lực. Tránh khai báo cùng một tham số ở nhiều nơi mà không có quy ước ưu tiên rõ ràng.

Không expose công khai endpoint cấu hình hoặc environment chỉ để xem nhanh. Nếu dùng Actuator để chẩn đoán, hãy expose và bảo vệ endpoint theo chính sách bảo mật của ứng dụng; chỉ hiển thị thông tin cần thiết cho người vận hành.

## 6. Kiểm tra exception có thực sự được ghi nhận là failure

Đủ số lời gọi chưa chắc đã đủ số failure. Resilience4j phân loại kết quả dựa trên cách supplier kết thúc và cấu hình exception.

Các trường hợp cần phân biệt:

| Tình huống | Tác động thường gặp đến circuit breaker |
|---|---|
| Supplier ném exception được ghi nhận | Tăng số failure trong cửa sổ. |
| Supplier ném exception nằm trong `ignoreExceptions` | Không được tính là success hoặc failure. |
| Supplier hoàn tất bình thường | Được tính là success, kể cả khi giá trị trả về biểu thị nghiệp vụ không thành công. |
| Circuit breaker từ chối trước khi supplier chạy | Tạo rejection (`CallNotPermittedException`), không phải failure mới của dependency. |
| Supplier trả HTTP response 5xx như một object bình thường | Có thể bị tính là success nếu client không chuyển response thành exception và không có result predicate tương ứng. |

Ví dụ cấu hình phân loại:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
```

Khi khai báo `recordExceptions`, hãy xác nhận các exception thực tế mà client phát ra. Nếu HTTP client bọc `SocketTimeoutException` trong một exception khác, cấu hình có thể không khớp như mong muốn. Với quy tắc `recordExceptions`, exception không thuộc danh sách có thể được xem là success nếu không bị ignore hoặc xử lý bởi predicate khác; hãy kiểm tra semantics của phiên bản Resilience4j đang dùng.

Không nên ignore timeout hoặc lỗi kết nối chỉ để giảm failure rate. Điều đó có thể khiến circuit breaker không mở dù dependency đang không đáp ứng.

## 7. Kiểm tra HTTP client có chuyển response lỗi thành exception không

Circuit breaker theo dõi kết quả của supplier, không tự hiểu mọi status HTTP là lỗi. Hành vi phụ thuộc client:

- Feign thường dùng `ErrorDecoder` để chuyển response không thành công thành exception; custom decoder có thể thay đổi hành vi.
- `WebClient.retrieve()` mặc định chuyển response 4xx/5xx thành `WebClientResponseException` nếu không được xử lý khác.
- `exchangeToMono()` cho phép ứng dụng tự kiểm tra response và có thể trả một object bình thường cho status lỗi.
- Một HTTP client khác có thể trả `ResponseEntity` hoặc response wrapper mà không ném exception.

Nếu supplier trả object `InventoryResponse(status=503)` rồi hoàn tất bình thường, circuit breaker có thể ghi nhận success. Hãy quyết định rõ status nào cần chuyển thành exception hoặc dùng predicate đánh giá kết quả phù hợp. Không chuyển mọi 4xx thành failure một cách máy móc; lỗi validation hoặc quyền truy cập có thể không phản ánh sức khỏe của dependency.

## 8. Kiểm tra vị trí fallback trong reactive pipeline

Trong Reactor, thứ tự operator có thể làm circuit breaker không nhìn thấy lỗi gốc.

Ví dụ này đặt fallback trước circuit breaker:

```java
Mono<Stock> result = inventoryClient.getStock(sku)
    .onErrorResume(error -> Mono.just(Stock.unavailable(sku)))
    .transform(CircuitBreakerOperator.of(circuitBreaker));
```

`onErrorResume` chuyển exception thành publisher hoàn tất bình thường trước khi circuit breaker quan sát. Vì vậy breaker có thể ghi nhận success dù lời gọi HTTP ban đầu đã thất bại.

Nếu muốn circuit breaker ghi nhận lỗi gốc rồi mới fallback, đặt operator trước:

```java
Mono<Stock> result = inventoryClient.getStock(sku)
    .transform(CircuitBreakerOperator.of(circuitBreaker))
    .onErrorResume(error -> Mono.just(Stock.unavailable(sku)));
```

Hãy kiểm tra tương tự với `onErrorReturn`, `onErrorComplete`, `retry` và các operator xử lý lỗi khác. Với reactive, cần xác nhận circuit breaker được gắn vào đúng subscription và supplier thực sự được subscribe; chỉ xây dựng một `Mono` mà không subscribe sẽ không tạo lời gọi.

## 9. Đọc metrics để xác định thiếu mẫu hay sai phân loại

Khi tích hợp Micrometer và Actuator, hãy kiểm tra các số liệu theo đúng breaker ID. Tên meter và tag cụ thể có thể khác theo phiên bản Resilience4j/Micrometer, vì vậy nên xem danh sách thực tế tại `/actuator/metrics` hoặc endpoint Prometheus thay vì đoán tên.

Những chỉ số hữu ích:

- Trạng thái hiện tại của breaker.
- Số lời gọi thành công và thất bại.
- Số lời gọi bị từ chối (`not permitted`).
- Failure rate và slow-call rate.
- Số lượng lời gọi được ghi nhận trong cửa sổ nếu metric/version cung cấp.
- Số lần chuyển trạng thái và event tương ứng.

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Nhiều request đến service nhưng số call của breaker thấp | Request không đi qua breaker đó, sai ID hoặc code path bypass wrapper. |
| Số call tăng nhưng failure luôn bằng 0 | Supplier có thể hoàn tất bình thường, response lỗi chưa thành exception hoặc exception bị ignore. |
| Failure tăng nhưng breaker chưa đánh giá | Chưa đạt `minimumNumberOfCalls` trong cửa sổ. |
| Metrics của ID cấu hình không thay đổi | Mã có thể đang tạo ID khác hoặc cấu hình instance không được dùng. |
| `not permitted` tăng sau khi breaker mở | Breaker đang chặn request; đây không phải failure mới từ supplier. |
| Slow call rate thấp dù latency cao | Ngưỡng slow-call sai đơn vị, sai ID hoặc lời gọi không nằm trong breaker được quan sát. |

Nếu dùng event listener, log `event.getCircuitBreakerName()` cùng state transition để biết ID runtime. Đăng ký listener một lần trong cấu hình hoặc lúc tạo instance; không đăng ký trong mỗi request vì sẽ tạo log trùng.

## 10. Quy trình chẩn đoán theo thứ tự

Khi breaker không mở như mong đợi, thực hiện các bước sau theo thứ tự để tránh thay đổi ngưỡng trước khi hiểu nguyên nhân:

1. **Xác nhận request đi qua breaker:** kiểm tra code path, factory và ID truyền vào `create(...)` hoặc resolver của OpenFeign.
2. **Lấy ID runtime:** quan sát event, metrics hoặc log của breaker; không suy ra tên từ tên service.
3. **Đối chiếu YAML:** khóa dưới `resilience4j.circuitbreaker.instances` phải khớp ID runtime.
4. **Kiểm tra cấu hình hiệu lực:** xem profile, external config, default config, Java Customizer và thứ tự ưu tiên.
5. **Tính số mẫu:** so sánh số kết quả trong cửa sổ với `minimumNumberOfCalls`; với TIME_BASED, tính lưu lượng trên từng instance trong khoảng thời gian đó.
6. **Kiểm tra phân loại exception:** xác nhận timeout/5xx được chuyển thành exception và không bị `ignoreExceptions` hoặc predicate loại bỏ.
7. **Kiểm tra reactive operator:** bảo đảm fallback không xử lý lỗi trước circuit breaker nếu cần thống kê lỗi gốc.
8. **Kiểm tra ngưỡng:** sau khi các điều kiện trên đúng, đối chiếu failure rate/slow-call rate với threshold.
9. **Kiểm tra trạng thái và thời gian:** xác nhận breaker chưa bị force open/closed, reset hoặc dùng instance khác.

## 11. Kịch bản tái hiện lỗi thiếu mẫu

Giả sử cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 8
        failureRateThreshold: 50
        waitDurationInOpenState: 5s
```

Có thể kiểm tra bằng một test điều khiển kết quả supplier:

1. Gửi 7 lời gọi và làm cả 7 thất bại bằng exception được ghi nhận.
2. Xác nhận breaker vẫn `CLOSED` vì mới có 7 mẫu.
3. Gửi lời gọi thứ 8 và làm nó thất bại.
4. Khi đủ 8 mẫu, failure rate là 100%, vượt ngưỡng 50%; xác nhận breaker chuyển `OPEN`.
5. Gửi lời gọi tiếp theo khi mạch `OPEN`; xác nhận supplier không chạy và caller nhận rejection hoặc fallback theo thiết kế.

Khi viết test, cần dùng đúng instance mà service sử dụng. Nếu test tạo một `CircuitBreaker` độc lập còn service gọi factory tạo instance khác, kết quả quan sát không đại diện cho breaker runtime.

## 12. Kịch bản tái hiện lỗi sai ID

Để phát hiện sai ID, có thể cố ý tạo khác biệt giữa mã và YAML trong một test tích hợp:

1. Cấu hình instance `inventory-read` với ngưỡng mẫu thấp.
2. Cho service gọi `circuitBreakerFactory.create("inventory")`.
3. Gửi đủ số lỗi và quan sát cấu hình runtime của ID `inventory`.
4. Xác nhận cấu hình riêng của `inventory-read` không điều khiển ID `inventory`.
5. Sửa mã hoặc YAML để hai bên dùng cùng một ID.
6. Chạy lại test và xác nhận breaker mở theo ngưỡng đã cấu hình.

Nên đặt ID trong hằng số để tránh sai khác do gõ tay:

```java
public final class CircuitBreakerIds {
    private CircuitBreakerIds() {}

    public static final String INVENTORY_READ = "inventory-read";
}
```

Sau đó dùng `CircuitBreakerIds.INVENTORY_READ` trong service và khai báo cùng tên trong YAML. Nếu ID do OpenFeign resolver tạo, hãy kiểm tra tên resolver thực tế thay vì thay bằng một tên suy đoán.

## 13. Những điều không nên làm khi điều tra

- Không giảm `minimumNumberOfCalls` xuống 1 chỉ để breaker mở ngay; một lỗi đơn lẻ có thể tạo quyết định quá nhạy.
- Không hạ `failureRateThreshold` trước khi xác nhận exception được ghi nhận.
- Không ignore timeout hoặc lỗi kết nối để làm dashboard bớt đỏ.
- Không tạo ID mới theo từng request để “tách lỗi”; điều đó làm breaker thiếu mẫu và tăng cardinality.
- Không retry nóng `CallNotPermittedException`; đó là rejection từ cơ chế bảo vệ.
- Không đặt fallback trước circuit breaker trong reactive pipeline nếu muốn breaker ghi nhận lỗi gốc.
- Không giả định tổng lưu lượng của nhiều replica được cộng vào một sliding window cục bộ.
- Không kết luận breaker không hoạt động chỉ từ một response fallback; hãy kiểm tra state và supplier execution.

## 14. Checklist trước khi kết luận

- [ ] Request thực sự đi qua Spring Cloud CircuitBreaker.
- [ ] ID runtime được xác định bằng event, metrics hoặc log.
- [ ] ID trong YAML khớp chính xác ID runtime.
- [ ] Cấu hình runtime đúng profile và không bị nguồn khác ghi đè.
- [ ] `minimumNumberOfCalls` có thể đạt trong sliding window.
- [ ] `minimumNumberOfCalls` không vượt `slidingWindowSize` đối với COUNT_BASED.
- [ ] Exception từ dependency được ghi nhận là failure.
- [ ] Không có ignored exception hoặc predicate loại bỏ lỗi ngoài ý muốn.
- [ ] HTTP response lỗi được chuyển thành exception hoặc được phân loại rõ.
- [ ] Reactive fallback không nuốt lỗi trước circuit breaker.
- [ ] Metrics được đọc theo đúng breaker ID và đúng instance ứng dụng.
- [ ] Test dùng đúng circuit breaker instance mà service đang sử dụng.

Khi circuit breaker không mở, hãy xác minh đúng ID và đủ mẫu trước, sau đó mới kiểm tra cách phân loại lỗi, response của client và vị trí fallback. `minimumNumberOfCalls` quyết định thời điểm bắt đầu đánh giá; ID quyết định cấu hình nào được áp dụng; exception mapping quyết định kết quả nào được tính là failure. Kiểm tra ba điểm này bằng metrics và một test tái hiện có kiểm soát sẽ giúp tìm đúng nguyên nhân mà không làm chính sách bảo vệ trở nên quá nhạy hoặc che giấu lỗi thật.
