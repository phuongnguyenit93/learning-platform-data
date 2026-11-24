# slowCallDurationThreshold và phân loại lời gọi chậm

Trong Spring Cloud Circuit Breaker sử dụng Resilience4j, circuit breaker có thể mở khi dịch vụ phụ thuộc phản hồi quá chậm, kể cả khi các lời gọi vẫn trả về kết quả thành công. Thuộc tính `slowCallDurationThreshold` xác định thời gian mà một lời gọi vượt qua sẽ được xem là chậm. Resilience4j thống kê các lời gọi chậm trong **sliding window**; khi tỷ lệ này đạt ngưỡng `slowCallRateThreshold` và đã có đủ số mẫu `minimumNumberOfCalls`, circuit breaker có thể chuyển từ `CLOSED` sang `OPEN`.

Điểm quan trọng là thời gian và kết quả của lời gọi là hai khía cạnh độc lập. Một lời gọi có thể thành công nhưng chậm, thất bại nhưng nhanh, hoặc vừa chậm vừa thất bại. Hiểu cách phân loại này giúp cấu hình circuit breaker theo chất lượng phản hồi thực tế thay vì chỉ dựa vào exception.

## `slowCallDurationThreshold` xác định điều gì?

`slowCallDurationThreshold` là ngưỡng thời lượng cho một lời gọi được circuit breaker theo dõi. Khi thời gian thực hiện lời gọi vượt ngưỡng, Resilience4j đánh dấu lời gọi đó là **slow call**. Giá trị thường được khai báo dưới dạng Duration, ví dụ `2s`, `500ms` hoặc `1500ms`.

Ngưỡng này được áp dụng cho từng lời gọi. Nó trả lời câu hỏi: *một lần gọi mất bao lâu thì được coi là chậm?* Nó không quyết định tỷ lệ lời gọi chậm được chấp nhận trong toàn bộ cửa sổ. Việc đó thuộc về `slowCallRateThreshold`.

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `slowCallDurationThreshold` | Thời lượng để phân loại một lời gọi là chậm. | `2s`: lời gọi vượt 2 giây được xem là chậm. |
| `slowCallRateThreshold` | Tỷ lệ phần trăm lời gọi chậm tối đa trong cửa sổ trước khi mạch mở. | `50`: mở mạch khi tỷ lệ lời gọi chậm đạt từ 50% trở lên. |
| `minimumNumberOfCalls` | Số lời gọi tối thiểu cần có trước khi tính tỷ lệ. | `10`: cần ít nhất 10 lời gọi được ghi nhận. |
| `slidingWindowType` và `slidingWindowSize` | Xác định tập lời gọi được dùng để thống kê. | 20 lời gọi gần nhất hoặc 30 giây gần nhất. |

Ví dụ, dịch vụ danh mục sản phẩm có SLA phản hồi trong khoảng 1 giây. Nhóm phát triển chọn `slowCallDurationThreshold: 2s` để nhận diện những lời gọi vượt xa thời gian phản hồi mong muốn. Một lời gọi mất 2,5 giây nhưng trả về dữ liệu hợp lệ vẫn là slow call, dù không phát sinh exception.

## Phân loại lời gọi theo thời gian và kết quả

Resilience4j đánh giá thời lượng và kết quả độc lập. Bảng sau minh họa bốn trường hợp khi ngưỡng thời gian là 2 giây:

| Thời gian và kết quả | Phân loại theo thời gian | Phân loại theo kết quả |
| --- | --- | --- |
| Trả về dữ liệu sau 400 ms | Không chậm | Thành công |
| Trả về dữ liệu sau 3 giây | Chậm | Thành công |
| Ném exception sau 300 ms | Không chậm | Thất bại nếu exception được ghi nhận là lỗi |
| Ném exception sau 4 giây | Chậm | Thất bại nếu exception được ghi nhận là lỗi |

Một lời gọi vừa chậm vừa thất bại được tính vào cả thống kê slow call và thống kê failure. Tuy nhiên, hai tỷ lệ được tính riêng:

- `failureRate` phản ánh tỷ lệ lời gọi được phân loại là thất bại.
- `slowCallRate` phản ánh tỷ lệ lời gọi vượt `slowCallDurationThreshold`.

Vì vậy, dịch vụ có thể có `failureRate` thấp nhưng `slowCallRate` cao. Đây là tình huống thường gặp khi dịch vụ phụ thuộc vẫn xử lý được yêu cầu nhưng độ trễ tăng do quá tải, truy vấn cơ sở dữ liệu chậm hoặc tài nguyên bị tranh chấp.

## Điều kiện tỷ lệ lời gọi chậm làm mở circuit breaker

Resilience4j tính tỷ lệ lời gọi chậm trên các kết quả còn nằm trong sliding window:

\[
\text{slowCallRate} = \frac{\text{số lời gọi chậm}}{\text{tổng số lời gọi được ghi nhận trong cửa sổ}} \times 100\%
\]

Chỉ khi số mẫu đạt `minimumNumberOfCalls`, circuit breaker mới đánh giá tỷ lệ. Nếu `slowCallRate` đạt hoặc vượt `slowCallRateThreshold`, mạch chuyển sang `OPEN`. Điều kiện này độc lập với điều kiện mở theo `failureRateThreshold`.

Giả sử cấu hình có:

- `minimumNumberOfCalls = 10`
- `slowCallDurationThreshold = 2s`
- `slowCallRateThreshold = 50`

Sau khi có 10 lời gọi trong cửa sổ, các trường hợp sau xảy ra:

| Lời gọi vượt 2 giây | Tỷ lệ slow call | Quyết định theo slow call |
| ---: | ---: | --- |
| 3 trên 10 | 30% | Chưa mở mạch theo tỷ lệ chậm. |
| 5 trên 10 | 50% | Đạt ngưỡng, chuyển sang `OPEN`. |
| 7 trên 10 | 70% | Vượt ngưỡng, chuyển sang `OPEN`. |

Ví dụ, 5 lời gọi mất 2,8 giây nhưng đều thành công và 5 lời gọi còn lại mất 200 ms. Tỷ lệ lỗi có thể là 0%, trong khi tỷ lệ slow call là 50%. Nếu cấu hình và số mẫu tối thiểu đã thỏa mãn, circuit breaker vẫn mở để giảm áp lực lên dịch vụ đang phản hồi chậm.

Lời gọi làm tỷ lệ vượt ngưỡng phải hoàn tất để circuit breaker ghi nhận thời lượng và kết quả. Nếu lời gọi đó thành công, kết quả của chính lời gọi vẫn có thể được trả về cho bên gọi; trạng thái `OPEN` sẽ chặn các lời gọi tiếp theo. Circuit breaker không tự hủy các lời gọi đang chạy khi chuyển trạng thái.

## Cấu hình trong Spring Cloud với Resilience4j

Ví dụ sau cấu hình instance `catalogService` trong `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogService:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        failureRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

Trong cấu hình này, circuit breaker theo dõi tối đa 20 lời gọi gần nhất. Khi đã có ít nhất 10 lời gọi được ghi nhận, nếu ít nhất một nửa số lời gọi trong cửa sổ vượt 2 giây thì điều kiện mở theo slow call được thỏa mãn. Tỷ lệ lỗi có ngưỡng riêng là 60%; chỉ cần một trong hai điều kiện tỷ lệ đạt ngưỡng là circuit breaker có thể mở.

Tên `catalogService` phải khớp với ID mà ứng dụng sử dụng khi tạo circuit breaker. Với Spring Cloud CircuitBreaker, có thể gọi qua factory và cung cấp fallback:

```java
@Service
public class CatalogService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public Product findProduct(String sku) {
        return circuitBreakerFactory.create("catalogService").run(
            () -> catalogClient.findProduct(sku),
            error -> cachedProduct(sku)
        );
    }

    private Product cachedProduct(String sku) {
        return Product.unavailable(sku);
    }
}
```

Khi circuit breaker ở `OPEN`, lời gọi mới bị từ chối và hàm fallback được gọi. Fallback cũng có thể được gọi khi lời gọi phụ thuộc phát sinh lỗi. Còn khi một lời gọi chỉ bị đánh dấu là chậm nhưng vẫn thành công, kết quả thành công của nó vẫn được trả về; việc phân loại slow call cập nhật số liệu để circuit breaker quyết định trạng thái cho những lời gọi sau.

## Phân loại exception có ảnh hưởng đến slow call không?

Các thuộc tính `recordExceptions` và `ignoreExceptions` điều khiển cách circuit breaker phân loại exception khi tính tỷ lệ thất bại. Chúng không thay thế `slowCallDurationThreshold` và không quyết định một lời gọi có chậm hay không.

Ví dụ cấu hình:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogService:
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        recordExceptions:
          - java.net.SocketTimeoutException
          - java.io.IOException
        ignoreExceptions:
          - com.example.catalog.ProductNotFoundException
```

Với cấu hình này, `SocketTimeoutException` và `IOException` được tính là lỗi theo danh sách ghi nhận; `ProductNotFoundException` được bỏ qua trong thống kê của circuit breaker. Exception không khớp danh sách ghi nhận và không nằm trong danh sách bỏ qua thường được xem như kết quả thành công. Vì exception bị bỏ qua không phải kết quả thành công hay thất bại thông thường được ghi vào cửa sổ, không nên mặc định tính chúng vào `slowCallRate`. Nếu cần theo dõi độ trễ của cả các kết quả bị bỏ qua, hãy đo thêm ở tầng client hoặc kiểm thử hành vi của phiên bản Resilience4j đang sử dụng.

Khi cần quy tắc phân loại phức tạp hơn, có thể cấu hình predicate trong Java thông qua `CircuitBreakerConfig`, chẳng hạn chỉ ghi nhận một số loại exception nhất định là lỗi. Hãy kiểm tra cả hai nhóm thống kê trong kiểm thử: lỗi được ghi nhận và lời gọi vượt ngưỡng thời gian.

## Phân biệt slow call với timeout

`slowCallDurationThreshold` chỉ đánh dấu lời gọi chậm sau khi có thời lượng thực tế để ghi nhận. Nó không đặt giới hạn chờ và không tự hủy lời gọi đang chạy. Nếu một lời gọi mất 8 giây trong khi ngưỡng slow call là 2 giây, circuit breaker có thể ghi nhận nó là chậm sau khi lời gọi hoàn tất ở giây thứ 8.

Timeout có mục đích khác: giới hạn thời gian chờ của thao tác. Có thể cấu hình timeout tại HTTP client, WebClient hoặc dùng `TimeLimiter` phù hợp với kiểu lời gọi. Khi timeout kích hoạt, thao tác có thể bị hủy hoặc kết thúc bằng exception tùy client và cách tích hợp. Exception đó được tính vào failure rate nếu quy tắc ghi nhận lỗi cho phép; thời lượng cũng có thể khiến lời gọi được phân loại là chậm.

Khi phối hợp hai cơ chế, hãy chọn ngưỡng slow call phù hợp với SLA và đặt timeout để giới hạn thời gian chờ tối đa. Ví dụ, nếu lời gọi bình thường thường hoàn tất dưới 500 ms, có thể đặt ngưỡng slow call ở 2 giây và timeout ở 4 giây. Khi đó circuit breaker nhận diện xu hướng chậm trước khi timeout cắt lời gọi. Cần xác minh thứ tự các decorator và cách client đo thời gian để đảm bảo circuit breaker quan sát đúng khoảng thời gian của thao tác cần bảo vệ.

## Lời gọi reactive và thời gian thực thi

Với luồng reactive, việc tạo một `Mono` hoặc `Flux` thường chưa thực hiện I/O ngay. Thao tác chỉ bắt đầu khi có subscription. Vì vậy, thời gian cần theo dõi là thời gian của lời gọi được circuit breaker trang trí trong quá trình subscribe cho đến khi luồng kết thúc bằng tín hiệu hoàn tất hoặc lỗi.

Trong Spring Cloud CircuitBreaker reactive, hãy tạo circuit breaker từ `ReactiveCircuitBreakerFactory` và áp dụng nó trực tiếp lên publisher của lời gọi phụ thuộc:

```java
@Service
public class ReactiveCatalogService {
    private final ReactiveCircuitBreakerFactory<?, ?> factory;
    private final ReactiveCatalogClient client;

    public ReactiveCatalogService(
            ReactiveCircuitBreakerFactory<?, ?> factory,
            ReactiveCatalogClient client) {
        this.factory = factory;
        this.client = client;
    }

    public Mono<Product> findProduct(String sku) {
        return factory.create("catalogService").run(
            client.findProduct(sku),
            error -> Mono.just(Product.unavailable(sku))
        );
    }
}
```

Đảm bảo publisher được thực thi bên trong phần được bảo vệ. Nếu chỉ đo một đoạn tạo publisher mà không bao gồm thời gian thực thi, số liệu sẽ không phản ánh độ trễ thực tế của dịch vụ phụ thuộc. Với luồng có nhiều bước, vị trí đặt circuit breaker quyết định phần công việc nào được tính vào thời lượng.

## Theo dõi và điều chỉnh ngưỡng

Khi circuit breaker mở do slow call, cần tìm nguyên nhân độ trễ thay vì chỉ tăng ngưỡng. Hãy quan sát thời gian phản hồi của dịch vụ phụ thuộc, số lượng slow call, tỷ lệ lỗi, trạng thái circuit breaker và lưu lượng trong cùng khoảng thời gian. Micrometer cùng hệ thống giám sát tương thích có thể cung cấp số liệu lời gọi theo trạng thái và kết quả để hỗ trợ phân tích.

Một số nguyên tắc khi điều chỉnh:

- Chọn `slowCallDurationThreshold` dựa trên SLA, phân vị độ trễ bình thường (chẳng hạn p95 hoặc p99) và thời gian người dùng có thể chấp nhận.
- Đặt `slowCallRateThreshold` để xác định mức độ suy giảm đủ nghiêm trọng cần mở mạch; tỷ lệ quá thấp có thể khiến biến động ngắn hạn kích hoạt thường xuyên.
- Chọn `minimumNumberOfCalls` phù hợp với lưu lượng. Nếu số mẫu tối thiểu quá cao so với số lời gọi trong cửa sổ, circuit breaker có thể không đánh giá được tỷ lệ.
- Đảm bảo timeout của client và ngưỡng slow call có quan hệ hợp lý. Nếu timeout ngắn hơn ngưỡng slow call quá nhiều, các lời gọi có thể bị timeout trước khi được phân loại là slow call theo ngưỡng mong muốn.
- Kiểm tra riêng các lời gọi thành công chậm, lỗi nhanh và lỗi chậm để xác nhận số liệu phản ánh đúng hành vi hệ thống.

Các lỗi cấu hình thường gặp là coi slow call như exception, nghĩ rằng circuit breaker tự ngắt request chậm, hoặc chỉ xem failure rate mà bỏ qua slow call rate. Khi phân biệt rõ thời lượng, kết quả và tỷ lệ trong cửa sổ, nhóm phát triển có thể phát hiện dịch vụ suy giảm sớm hơn, bảo vệ tài nguyên của các dịch vụ gọi đến và hạn chế độ trễ lan truyền trong hệ thống Spring Cloud.
