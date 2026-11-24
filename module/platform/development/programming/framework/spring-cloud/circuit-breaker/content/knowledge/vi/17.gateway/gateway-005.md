# Chuyển HTTP status được chọn thành lỗi để kích hoạt ngắt mạch

Khi Spring Cloud Gateway chuyển tiếp request đến một dịch vụ phía sau, dịch vụ đó có thể trả HTTP response với mã 5xx mà không ném exception trong luồng xử lý của Gateway. Nếu chỉ dựa vào exception, circuit breaker có thể xem một response 5xx như một lần gọi hoàn tất bình thường và không tăng failure rate. Gateway CircuitBreaker filter giải quyết trường hợp này bằng thuộc tính `statusCodes`: các HTTP status được chọn sẽ được chuyển thành tín hiệu lỗi để circuit breaker ghi nhận.

Cách cấu hình này giúp Gateway mở mạch khi một dịch vụ liên tục trả những mã phản hồi thể hiện sự cố, chẳng hạn 500, 502, 503 hoặc 504. Khi mạch OPEN, Gateway có thể từ chối nhanh các lời gọi tiếp theo và chuyển sang fallback. Cần chọn mã status theo ý nghĩa của dịch vụ để các lỗi nghiệp vụ hoặc lỗi từ client không vô tình làm mở mạch.

## Vì sao cần chuyển HTTP status thành lỗi?

HTTP response có mã 500 vẫn là một response hợp lệ ở tầng giao thức. Gateway nhận được response, đọc status và có thể hoàn tất luồng reactive bình thường. Trong khi đó, circuit breaker thường đánh giá kết quả thành công hoặc thất bại dựa trên exception phát sinh trong lời gọi được bảo vệ.

Nếu Gateway không chuyển mã status đã chọn thành exception, các lần gọi trả 500 có thể không được tính là thất bại của circuit breaker. Khi đó, dịch vụ phía sau có thể liên tục gặp lỗi nhưng circuit breaker vẫn ở CLOSED.

Thuộc tính `statusCodes` cho phép khai báo những mã HTTP cần được xem như lỗi. Khi response từ dịch vụ phía sau có một status khớp danh sách, Gateway CircuitBreaker filter tạo tín hiệu lỗi cho circuit breaker. Tín hiệu này tham gia vào thống kê failure rate giống như một exception của lời gọi.

Cần phân biệt ba trường hợp:

- **HTTP status được chọn:** Gateway chuyển response thành lỗi để circuit breaker ghi nhận.
- **HTTP status không được chọn:** response tiếp tục đi qua Gateway như kết quả HTTP thông thường, trừ khi có cơ chế khác biến nó thành lỗi.
- **Exception khi gọi dịch vụ:** lỗi kết nối, timeout hoặc lỗi thực thi vốn đã đi theo đường exception; không cần một HTTP status để circuit breaker nhận biết.

## Cấu hình statusCodes trong Gateway CircuitBreaker filter

Ví dụ route sau bảo vệ lời gọi đến dịch vụ tồn kho và coi một số mã 5xx là lỗi:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: inventory-route
          uri: lb://inventory-service
          predicates:
            - Path=/api/inventory/**
          filters:
            - name: CircuitBreaker
              args:
                name: inventoryGateway
                fallbackUri: forward:/_fallback/inventory
                statusCodes:
                  - "500"
                  - "502"
                  - "503"
                  - "504"
~~~

Trong cấu hình:

- `name` là tên circuit breaker mà Gateway dùng khi tạo bộ ngắt mạch.
- `fallbackUri` chỉ định endpoint nội bộ được gọi khi circuit breaker chuyển sang fallback do lỗi hoặc đang OPEN.
- `statusCodes` là danh sách mã HTTP cụ thể mà Gateway xem là lỗi của lời gọi được bảo vệ.
- `uri` là dịch vụ đích; ví dụ `lb://inventory-service` dùng cơ chế cân bằng tải của Spring Cloud.

Các giá trị trong `statusCodes` được viết dưới dạng chuỗi mã status. Đây là các mã cụ thể như 500 hoặc 503, không phải biểu thức cho cả một nhóm status. Nếu muốn xem nhiều mã 5xx là lỗi, hãy liệt kê những mã cần áp dụng rõ ràng.

Nếu chỉ muốn 503 kích hoạt ngắt mạch, có thể cấu hình:

~~~yaml
statusCodes:
  - "503"
~~~

Không cần đưa tất cả mã 4xx hoặc 5xx vào danh sách theo thói quen. Mỗi mã cần phản ánh một tình trạng mà ứng dụng muốn circuit breaker thống kê như lỗi của phụ thuộc.

## Tên circuit breaker và cấu hình Resilience4j

Tên trong thuộc tính `name` phải khớp với tên instance Resilience4j nếu muốn áp dụng cấu hình riêng cho route đó. Ví dụ, route sử dụng `inventoryGateway` thì có thể cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryGateway:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Ví dụ này sử dụng cửa sổ 20 lời gọi và chỉ bắt đầu đánh giá tỷ lệ khi có ít nhất 10 mẫu. Nếu failure rate đạt 50%, circuit breaker có thể chuyển sang OPEN. Các status được chọn trong Gateway đã trở thành lỗi của lời gọi nên có thể đóng góp vào tỷ lệ này.

`statusCodes` và `failureRateThreshold` có vai trò khác nhau:

| Thiết lập | Trách nhiệm |
|---|---|
| `statusCodes` | Xác định response HTTP nào được chuyển thành lỗi. |
| `failureRateThreshold` | Xác định tỷ lệ lỗi trong cửa sổ đủ lớn để mở mạch. |
| `slidingWindowSize` | Xác định số mẫu hoặc khoảng thời gian dùng để tính tỷ lệ. |
| `minimumNumberOfCalls` | Ngăn đánh giá tỷ lệ khi chưa có đủ mẫu. |
| `waitDurationInOpenState` | Xác định thời gian chờ trước khi thử phục hồi. |

Một status được chọn không nhất thiết làm mạch mở ngay lập tức. Nó được tính là một kết quả thất bại; circuit breaker vẫn đánh giá theo số mẫu tối thiểu, cửa sổ và ngưỡng đã cấu hình.

## Fallback khi status được chọn

Khi status khớp danh sách, Gateway CircuitBreaker filter chuyển tín hiệu lỗi vào circuit breaker. Nếu lỗi làm mạch mở hoặc mạch đã OPEN, filter có thể chuyển request đến fallback được khai báo bằng `forward:`.

Một fallback handler đơn giản có thể trả phản hồi 503 có cấu trúc:

~~~java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InventoryFallbackController {

    @RequestMapping("/_fallback/inventory")
    public ResponseEntity<Map<String, String>> inventoryUnavailable() {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of(
                        "code", "INVENTORY_TEMPORARILY_UNAVAILABLE",
                        "message", "Dịch vụ tồn kho hiện chưa sẵn sàng"
                ));
    }
}
~~~

Đây là endpoint nội bộ của Gateway được gọi qua `forward:/_fallback/inventory`. Trong ứng dụng thực tế, response fallback cần tuân theo hợp đồng API chung, có thể bổ sung correlation ID hoặc thông tin hướng dẫn thử lại nếu chính sách vận hành cho phép.

Fallback không nên giả lập một kết quả nghiệp vụ đã được xác nhận. Nếu dịch vụ tồn kho không phản hồi, Gateway không nên trả số lượng bằng 0 hoặc khẳng định sản phẩm hết hàng. Hãy trả trạng thái không sẵn sàng hoặc dữ liệu cache có nhãn độ mới rõ ràng nếu nghiệp vụ cho phép.

Cần tránh để fallback endpoint đi qua chính route CircuitBreaker đang lỗi. Với `forward:`, hãy ánh xạ trực tiếp tới handler nội bộ trong Gateway, không gọi ngược lại cùng dịch vụ phía sau. Nếu fallback tự gọi dịch vụ đang lỗi, nó có thể tạo vòng lặp hoặc tiếp tục làm tăng tải.

## Chọn HTTP status nào để kích hoạt ngắt mạch?

Không phải mọi status khác 2xx đều phản ánh sự cố của dịch vụ phụ thuộc. Hãy chọn status dựa trên nguồn phát sinh và ý nghĩa nghiệp vụ.

| HTTP status | Ý nghĩa thường gặp | Có nên đưa vào statusCodes? |
|---|---|---|
| 500 Internal Server Error | Dịch vụ phía sau gặp lỗi xử lý không dự kiến. | Thường phù hợp nếu muốn bảo vệ trước lỗi server lặp lại. |
| 502 Bad Gateway | Gateway/proxy phía sau nhận phản hồi không hợp lệ từ upstream. | Có thể phù hợp nếu status đến từ dịch vụ hoặc proxy phụ thuộc. |
| 503 Service Unavailable | Dịch vụ tạm thời không thể xử lý request. | Thường phù hợp khi thể hiện phụ thuộc không sẵn sàng. |
| 504 Gateway Timeout | Thành phần phía sau không nhận được phản hồi đúng hạn. | Thường phù hợp nếu status phản ánh timeout của phụ thuộc. |
| 400 Bad Request | Request không hợp lệ. | Thường không phù hợp; lỗi đầu vào không cho biết sức khỏe phụ thuộc. |
| 401 Unauthorized / 403 Forbidden | Thiếu xác thực hoặc không đủ quyền. | Thường cần xử lý riêng; có thể là lỗi cấu hình hoặc quyền truy cập. |
| 404 Not Found | Tài nguyên không tồn tại. | Thường không phù hợp với circuit breaker nếu đây là kết quả nghiệp vụ bình thường. |
| 429 Too Many Requests | Client hoặc dịch vụ bị giới hạn tốc độ. | Chỉ chọn khi 429 thực sự biểu thị phụ thuộc quá tải theo chính sách; cần tránh mở mạch vì quota của caller. |

Ví dụ, nếu người dùng yêu cầu một SKU không tồn tại và dịch vụ tồn kho trả 404, đó có thể là kết quả bình thường của nghiệp vụ. Nếu đưa 404 vào `statusCodes`, những truy vấn sản phẩm không tồn tại có thể làm tăng failure rate và khiến mạch mở sai.

Tương tự, 401 hoặc 403 thường chỉ ra vấn đề xác thực hoặc phân quyền. Mở circuit breaker không sửa được token hết hạn hoặc cấu hình quyền sai. Hãy ghi nhận và cảnh báo các lỗi này theo cách phù hợp, trừ khi hệ thống có lý do rõ ràng để xem chúng là tình trạng phụ thuộc không thể phục vụ.

429 cần được đánh giá cẩn thận. Nếu dịch vụ nguồn trả 429 vì chính Gateway vượt quota toàn cục, có thể muốn giảm tốc độ hoặc áp dụng RateLimiter. Nếu 429 là giới hạn riêng của một tenant hoặc người dùng, mở circuit breaker dùng chung cho mọi caller có thể làm ảnh hưởng các request hợp lệ khác.

## Phân biệt status được chuyển thành lỗi với việc đổi status trả về client

`statusCodes` không phải cấu hình viết lại HTTP response. Nó giúp circuit breaker nhận biết response được chọn là một kết quả thất bại. Khi fallback được thực thi, client thường nhận status do fallback handler trả về, chẳng hạn 503 trong ví dụ trên.

Nếu status không khớp danh sách và không có exception khác, Gateway có thể chuyển nguyên response từ dịch vụ phía sau về client. Ví dụ, 404 không nằm trong danh sách thì có thể tiếp tục được trả như 404, thay vì kích hoạt fallback.

Điều này giúp giữ đúng ngữ nghĩa HTTP:

- Status nghiệp vụ như 404 có thể tiếp tục đến client.
- Status sự cố như 503 có thể được dùng để kích hoạt circuit breaker.
- Fallback có thể trả một status suy giảm có kiểm soát, thường là 503 hoặc response cache theo hợp đồng API.

Không nên coi việc kích hoạt circuit breaker là cách chuẩn hóa tất cả lỗi thành 200 hoặc che giấu mã lỗi. Client cần nhận status phản ánh đúng kết quả mà ứng dụng có thể bảo đảm.

## Quan hệ với exception và phân loại lỗi

Gateway CircuitBreaker filter có thể kích hoạt mạch từ hai nhóm tín hiệu:

1. Exception xảy ra khi gọi dịch vụ phía sau, ví dụ lỗi kết nối hoặc timeout.
2. HTTP status thuộc danh sách `statusCodes`, được Gateway chuyển thành exception để circuit breaker ghi nhận.

Các exception và status được chọn cùng tham gia vào chính sách circuit breaker. Nếu ứng dụng có cấu hình phân loại exception riêng ở backend Resilience4j, cần kiểm tra để chắc chắn exception do status được chọn tạo ra không bị bỏ qua ngoài ý muốn.

Đừng nhầm status HTTP với exception class. `statusCodes` nhận diện mã response; `recordExceptions` hoặc predicate của Resilience4j phân loại exception. Khi kết hợp hai cơ chế, cần kiểm tra cả đường response status lẫn đường exception trong kiểm thử tích hợp.

Ví dụ:

- Dịch vụ trả 503: Gateway chuyển status thành lỗi và circuit breaker ghi nhận thất bại.
- Dịch vụ không thể kết nối: HTTP client phát exception; circuit breaker ghi nhận theo cấu hình exception.
- Dịch vụ trả 404 không được chọn: Gateway chuyển response bình thường và không kích hoạt fallback chỉ vì status này.
- Circuit breaker đã OPEN: lời gọi mới bị từ chối trước khi chuyển tiếp đến dịch vụ; Gateway thực hiện fallback nếu được cấu hình.

## Kết hợp statusCodes với timeout và retry

Status 504 thường có thể biểu thị timeout ở một proxy hoặc dịch vụ phía sau. Nhưng Gateway cũng có thể tự phát sinh timeout exception nếu lời gọi vượt giới hạn thời gian đã cấu hình. Hai trường hợp này khác nhau ở nơi tạo ra tín hiệu lỗi, dù cả hai có thể đóng góp vào failure rate.

Retry cũng cần được cấu hình có kiểm soát. Nếu một response 503 được chuyển thành exception, retry có thể thử lại theo chính sách retry của route hoặc tầng gọi. Retry quá nhiều lần có thể làm dịch vụ đang quá tải nhận thêm request. Chỉ retry các lỗi tạm thời có khả năng phục hồi, giới hạn số lần và giữ tổng thời gian trong deadline của request.

Với thao tác ghi, timeout hoặc 5xx không chứng minh rằng dịch vụ nguồn chưa thực hiện thao tác. Trước khi retry lệnh ghi, cần có idempotency key hoặc API tra cứu trạng thái để tránh tạo giao dịch trùng.

Circuit breaker và retry cần có thứ tự rõ ràng. Circuit breaker nên quan sát kết quả cuối của đơn vị công việc mà ứng dụng muốn thống kê; nếu retry được đặt bên trong, một chuỗi thử lại có thể được tính như một lời gọi logic. Nếu retry nằm ngoài, từng lần thử có thể đi qua circuit breaker riêng tùy cấu trúc filter. Hãy xác định mục tiêu đo lường trước khi chọn vị trí.

## Quan sát và chẩn đoán

Khi vận hành Gateway, nên theo dõi riêng status response và trạng thái circuit breaker:

- Số response theo từng mã HTTP trước khi chuyển thành lỗi.
- Số lần statusCodes kích hoạt exception cho circuit breaker.
- Số lỗi kết nối và timeout.
- Failure rate và slow call rate theo tên circuit breaker.
- Số lần circuit breaker chuyển CLOSED, OPEN và HALF_OPEN.
- Số request bị từ chối nhanh khi mạch OPEN.
- Số lần fallback được gọi và status fallback trả về.

Tên circuit breaker trong route cần ổn định để metrics và dashboard có thể nhóm đúng. Không thêm path parameter, SKU, user ID hoặc request ID vào tên. Các giá trị theo request có thể đặt trong log hoặc trace, còn metrics cần nhãn có miền giá trị giới hạn.

Khi thấy mạch mở, hãy kiểm tra nguyên nhân theo thứ tự: status nào được chọn, dịch vụ nào phát status, lỗi kết nối/timeout có tăng không, cửa sổ và ngưỡng đang dùng là gì, fallback có tăng bất thường không. Nếu mạch mở do nhiều 404 hoặc 429 nghiệp vụ, hãy xem lại danh sách `statusCodes` thay vì chỉ tăng failureRateThreshold.

## Kiểm thử cấu hình statusCodes

Dùng dịch vụ giả lập có thể trả các status cụ thể để xác nhận Gateway xử lý đúng. Kiểm tra response cuối cùng của client, trạng thái circuit breaker và việc fallback được gọi.

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Dịch vụ trả 200 | Response được chuyển về client; không tăng failure count do status. |
| Dịch vụ trả 404 và không chọn 404 | 404 tiếp tục được chuyển về client; fallback không bị gọi chỉ vì status này. |
| Dịch vụ trả 500 có trong danh sách | Gateway chuyển status thành lỗi; circuit breaker ghi nhận thất bại. |
| Dịch vụ trả 503 có trong danh sách | Fallback được gọi khi điều kiện circuit breaker/fallback áp dụng. |
| Dịch vụ không thể kết nối | Exception được ghi nhận theo cấu hình circuit breaker. |
| Dịch vụ phản hồi chậm quá timeout | Timeout được ghi nhận; fallback xử lý theo cấu hình. |
| Failure rate đạt ngưỡng | Circuit breaker chuyển OPEN và từ chối nhanh lời gọi tiếp theo. |
| Hết thời gian OPEN | Circuit breaker cho phép các lời gọi thăm dò ở HALF_OPEN. |
| Fallback endpoint lỗi | Gateway trả lỗi phù hợp và ghi nhận sự cố fallback riêng. |
| Status nghiệp vụ như 401/404/429 | Xác nhận chỉ những mã được chọn mới kích hoạt mạch. |

Trong kiểm thử, đặt sliding window nhỏ và minimumNumberOfCalls thấp để quan sát chuyển trạng thái dễ dàng. Sau đó kiểm tra lại bằng ngưỡng gần với lưu lượng thật. Không chỉ xác nhận client nhận 503; cần xác nhận status được chuyển thành lỗi và góp phần vào thống kê của đúng circuit breaker.

## Quy trình triển khai

1. Xác định status HTTP nào phản ánh sự cố của dịch vụ phía sau trong từng route.
2. Chỉ liệt kê mã cụ thể cần kích hoạt circuit breaker trong `statusCodes`.
3. Đặt tên circuit breaker ổn định và khớp với instance Resilience4j.
4. Cấu hình sliding window, minimum number of calls và failure rate phù hợp với lưu lượng.
5. Khai báo fallback nội bộ bằng `forward:` và bảo đảm fallback không gọi ngược route đang lỗi.
6. Phân biệt status nghiệp vụ, lỗi xác thực, quota và lỗi hạ tầng.
7. Phối hợp timeout và retry trong ngân sách request; bảo vệ thao tác ghi bằng idempotency.
8. Theo dõi status nguồn, số lần status được chuyển thành lỗi, trạng thái circuit breaker và fallback.
9. Kiểm thử status được chọn, status không được chọn, exception, timeout và quá trình phục hồi HALF_OPEN.

Trong Spring Cloud Gateway, `statusCodes` giúp chuyển các HTTP response được chọn thành lỗi mà circuit breaker có thể thống kê. Khi danh sách mã phản ánh đúng sự cố của phụ thuộc, Gateway có thể mở mạch trước khi lỗi lan rộng và chuyển request sang fallback có kiểm soát. Hãy chọn mã theo ngữ nghĩa nghiệp vụ, giữ cấu hình tên nhất quán và kiểm thử cả status được chọn lẫn status cần tiếp tục trả về client.

