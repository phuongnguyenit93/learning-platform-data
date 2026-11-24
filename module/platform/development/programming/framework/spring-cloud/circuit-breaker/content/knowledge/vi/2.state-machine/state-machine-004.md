# Điều kiện chuyển từ CLOSED sang OPEN

Trong Spring Cloud Circuit Breaker, circuit breaker theo dõi kết quả các lời gọi đến dịch vụ phụ thuộc. Khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm đạt hoặc vượt ngưỡng đã cấu hình, nó chuyển từ `CLOSED` sang `OPEN` để ngăn ứng dụng tiếp tục gửi yêu cầu đến một dịch vụ đang gặp sự cố. Với triển khai Resilience4j, quyết định chuyển trạng thái dựa trên số lời gọi tối thiểu và số liệu được tổng hợp trong một **sliding window**.

## Vai trò của trạng thái CLOSED và OPEN

Circuit breaker thường được mô tả bằng ba trạng thái:

| Trạng thái | Hành vi |
| --- | --- |
| `CLOSED` | Cho phép lời gọi đi đến dịch vụ phụ thuộc và ghi nhận kết quả để tính tỷ lệ lỗi, tỷ lệ lời gọi chậm. |
| `OPEN` | Từ chối lời gọi mới ngay tại circuit breaker. Mã gọi nhận lỗi `CallNotPermittedException` và có thể chuyển sang xử lý fallback. |
| `HALF_OPEN` | Cho phép một số lượng lời gọi thử nghiệm giới hạn để kiểm tra dịch vụ đã phục hồi hay chưa. |

Khi đang ở `CLOSED`, circuit breaker không mở chỉ vì một lời gọi đơn lẻ thất bại. Nó cần đủ số mẫu để đánh giá và sau đó kiểm tra các tỷ lệ so với ngưỡng. Điều kiện chuyển trạng thái có thể biểu diễn như sau:

```text
đã có đủ minimumNumberOfCalls
                 AND
  (failureRate >= failureRateThreshold
       OR
   slowCallRate >= slowCallRateThreshold)
                 => OPEN
```

Hai tỷ lệ được đánh giá độc lập. Chỉ cần một trong hai đạt hoặc vượt ngưỡng là đủ để mở circuit breaker.

## Bốn yếu tố quyết định thời điểm mở

### 1. Số lời gọi tối thiểu: minimumNumberOfCalls

`minimumNumberOfCalls` là số lời gọi đã được ghi nhận tối thiểu trong cửa sổ trượt trước khi Resilience4j bắt đầu tính tỷ lệ lỗi và tỷ lệ lời gọi chậm để quyết định mở mạch.

Ví dụ, nếu `minimumNumberOfCalls` bằng `10`, sau 3 lời gọi thất bại circuit breaker vẫn chưa thể kết luận dịch vụ đang lỗi theo tỷ lệ. Khi đã có ít nhất 10 lời gọi được ghi nhận, nó mới tính các tỷ lệ và so sánh với ngưỡng.

Giá trị này giúp tránh quyết định quá sớm từ một tập mẫu quá nhỏ. Tuy nhiên, đặt giá trị quá lớn có thể làm circuit breaker phản ứng chậm khi lưu lượng thấp; đặt quá nhỏ có thể khiến một vài lỗi ngẫu nhiên làm mạch mở. Cần chọn giá trị phù hợp với lưu lượng và mức độ quan trọng của dịch vụ.

### 2. Tỷ lệ lỗi: failureRateThreshold

`failureRateThreshold` là ngưỡng phần trăm lời gọi được ghi nhận là thất bại. Resilience4j tính tỷ lệ theo công thức:

\[
\text{failureRate} = \frac{\text{số lời gọi thất bại}}{\text{tổng số lời gọi được ghi nhận trong cửa sổ}} \times 100\%
\]

Nếu `failureRate` **lớn hơn hoặc bằng** `failureRateThreshold`, circuit breaker chuyển sang `OPEN`, với điều kiện đã đạt `minimumNumberOfCalls`.

Ví dụ: cửa sổ hiện tại có 10 lời gọi được ghi nhận, trong đó 5 lời gọi thất bại. Tỷ lệ lỗi là `5 / 10 × 100% = 50%`. Nếu ngưỡng được đặt là `50`, điều kiện đã đạt và mạch mở. So sánh dùng `>=`, vì vậy tỷ lệ đúng bằng ngưỡng cũng kích hoạt chuyển trạng thái.

Một lời gọi được xem là thất bại theo quy tắc phân loại kết quả và exception của circuit breaker. Khi cấu hình `recordExceptions`, các exception khớp cấu hình được tính là lỗi; exception không khớp thường được tính như lời gọi thành công. Các exception trong `ignoreExceptions` được bỏ qua, không tính là thành công hay thất bại. Có thể dùng predicate trong cấu hình Java để định nghĩa quy tắc phân loại chi tiết hơn.

### 3. Tỷ lệ lời gọi chậm: slowCallRateThreshold

Một lời gọi có thể trả về thành công nhưng vẫn gây hại cho hệ thống nếu mất quá nhiều thời gian. `slowCallDurationThreshold` xác định thời gian từ đó một lời gọi được xem là chậm; `slowCallRateThreshold` xác định tỷ lệ lời gọi chậm tối đa có thể chấp nhận trước khi mở mạch.

Resilience4j tính tỷ lệ lời gọi chậm theo công thức:

\[
\text{slowCallRate} = \frac{\text{số lời gọi chậm}}{\text{tổng số lời gọi được ghi nhận trong cửa sổ}} \times 100\%
\]

Ví dụ: trong 10 lời gọi, có 6 lời gọi mất hơn 2 giây, dù cả 6 đều trả về dữ liệu hợp lệ. Tỷ lệ lời gọi chậm là `60%`. Nếu `slowCallRateThreshold` bằng `60`, circuit breaker chuyển sang `OPEN` khi đã đủ số mẫu tối thiểu.

Một lời gọi vừa thất bại vừa chậm có thể góp phần vào cả hai tỷ lệ. Không cộng hai tỷ lệ với nhau; circuit breaker đánh giá riêng từng điều kiện. Chỉ cần tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm đạt ngưỡng tương ứng là mạch mở.

Circuit breaker nhận biết lời gọi chậm dựa trên thời gian thực tế của lời gọi. Nó không tự ngắt một lời gọi đang chạy khi lời gọi vượt `slowCallDurationThreshold`. Để giới hạn thời gian chờ và giải phóng tài nguyên, cần cấu hình timeout ở HTTP client hoặc dùng `TimeLimiter` phù hợp. Nếu timeout tạo ra exception, exception đó chỉ được tính là lỗi khi quy tắc ghi nhận lỗi cho phép.

### 4. Sliding window: slidingWindowType và slidingWindowSize

Sliding window xác định tập lời gọi được dùng để tính các tỷ lệ. Resilience4j hỗ trợ hai kiểu:

| Kiểu cửa sổ | Cách hoạt động | Ví dụ cấu hình |
| --- | --- | --- |
| `COUNT_BASED` | Theo dõi kết quả của `slidingWindowSize` lời gọi gần nhất. Khi có lời gọi mới, kết quả cũ nhất rời khỏi cửa sổ. | `slidingWindowSize: 20` nghĩa là xét tối đa 20 lời gọi gần nhất. |
| `TIME_BASED` | Theo dõi kết quả trong khoảng thời gian gồm `slidingWindowSize` giây gần nhất. | `slidingWindowSize: 30` nghĩa là xét các lời gọi trong 30 giây gần nhất. |

`minimumNumberOfCalls` vẫn có vai trò riêng: cửa sổ xác định dữ liệu nào còn hiệu lực, còn số lời gọi tối thiểu xác định khi nào dữ liệu đủ để tính tỷ lệ. Ví dụ, với cửa sổ đếm 20 lời gọi và số mẫu tối thiểu 10, circuit breaker bắt đầu đánh giá sau khi có 10 lời gọi được ghi nhận. Khi cửa sổ đã đầy, mỗi kết quả mới sẽ thay thế kết quả cũ nhất.

Với cửa sổ theo thời gian, lưu lượng thấp có thể khiến cửa sổ chưa có đủ số lời gọi tối thiểu. Khi đó circuit breaker tiếp tục ở `CLOSED` dù một số lời gọi gần đây thất bại; nó chỉ đánh giá khi có đủ mẫu trong cửa sổ hiện tại.

## Cấu hình Resilience4j trong Spring Cloud

Ví dụ sau cấu hình circuit breaker có tên `inventoryService`. Tên instance phải trùng với ID mà ứng dụng dùng khi tạo circuit breaker qua Spring Cloud CircuitBreaker hoặc khi khai báo cấu hình Resilience4j tương ứng.

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryService:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
        recordExceptions:
          - java.util.concurrent.TimeoutException
```

Các thuộc tính quyết định trực tiếp việc chuyển từ `CLOSED` sang `OPEN` trong ví dụ:

- `minimumNumberOfCalls: 10`: cần ít nhất 10 lời gọi được ghi nhận trong cửa sổ trước khi tính tỷ lệ.
- `failureRateThreshold: 50`: mở mạch nếu tỷ lệ lỗi đạt từ 50% trở lên.
- `slowCallDurationThreshold: 2s`: lời gọi kéo dài hơn 2 giây được tính là chậm.
- `slowCallRateThreshold: 60`: mở mạch nếu tỷ lệ lời gọi chậm đạt từ 60% trở lên.
- `slidingWindowType` và `slidingWindowSize`: chọn cách xác định tập lời gọi được thống kê.

`waitDurationInOpenState`, `permittedNumberOfCallsInHalfOpenState` và `automaticTransitionFromOpenToHalfOpenEnabled` điều khiển giai đoạn sau khi mạch đã mở. Chúng không thay đổi điều kiện ban đầu để chuyển từ `CLOSED` sang `OPEN`.

## Tính thử điều kiện chuyển trạng thái

Giả sử cấu hình có `minimumNumberOfCalls = 10`, `failureRateThreshold = 50` và `slowCallRateThreshold = 60`. Sau 10 lời gọi được ghi nhận, ta có các trường hợp:

| Kết quả trong 10 lời gọi | Tỷ lệ lỗi | Tỷ lệ chậm | Kết quả |
| --- | ---: | ---: | --- |
| 4 lỗi, 2 lời gọi chậm | 40% | 20% | Tiếp tục `CLOSED` vì cả hai tỷ lệ đều dưới ngưỡng. |
| 5 lỗi, 1 lời gọi chậm | 50% | 10% | Chuyển sang `OPEN` vì tỷ lệ lỗi đạt ngưỡng. |
| 4 lỗi, 6 lời gọi chậm | 40% | 60% | Chuyển sang `OPEN` vì tỷ lệ lời gọi chậm đạt ngưỡng. |
| 3 lỗi, 5 lời gọi chậm | 30% | 50% | Tiếp tục `CLOSED` vì cả hai tỷ lệ đều dưới ngưỡng. |

Ở trường hợp cuối, nếu cửa sổ có kích thước 10 và một lời gọi chậm mới thay thế một lời gọi không chậm cũ, tỷ lệ chậm tăng lên `60%` và mạch chuyển sang `OPEN`. Với cửa sổ `COUNT_BASED`, cần tính lại trên các lời gọi còn nằm trong cửa sổ sau mỗi kết quả mới; không lấy tổng lỗi kể từ lúc ứng dụng khởi động.

## Diễn biến sau khi chuyển sang OPEN

Khi điều kiện mở được thỏa mãn, circuit breaker đổi trạng thái sang `OPEN` và phát sinh sự kiện chuyển trạng thái. Các lời gọi mới bị từ chối nhanh, không tiếp tục chiếm tài nguyên của dịch vụ phụ thuộc. Ứng dụng có thể xử lý `CallNotPermittedException` bằng fallback để trả về dữ liệu dự phòng, thông báo dịch vụ tạm thời không khả dụng hoặc đưa yêu cầu vào cơ chế xử lý khác phù hợp.

Sau `waitDurationInOpenState`, circuit breaker có thể chuyển sang `HALF_OPEN` để thử khả năng phục hồi. Tùy cấu hình, việc chuyển này diễn ra khi có lời gọi tiếp theo hoặc tự động theo bộ lập lịch. Trong `HALF_OPEN`, chỉ số lời gọi thử nghiệm được giới hạn bởi `permittedNumberOfCallsInHalfOpenState`. Kết quả thử nghiệm sẽ quyết định mạch đóng lại hay mở lại. Đây là giai đoạn kiểm tra phục hồi; điều kiện mở ban đầu vẫn là điều kiện dựa trên số mẫu tối thiểu và các tỷ lệ trong cửa sổ.

Sự kiện và số liệu của circuit breaker nên được theo dõi để xác định vì sao mạch mở: tỷ lệ lỗi cao, lời gọi chậm tăng, hay lưu lượng chưa đủ để đánh giá. Khi dùng Micrometer và hệ thống giám sát tương thích, có thể quan sát trạng thái, số lời gọi thành công/thất bại/bị từ chối và các tỷ lệ liên quan. Việc theo dõi giúp điều chỉnh ngưỡng dựa trên hành vi thực tế thay vì chọn giá trị tùy ý.

## Những lỗi cấu hình thường gặp

- **Đặt `minimumNumberOfCalls` cao hơn lưu lượng thực tế:** circuit breaker hiếm khi có đủ mẫu trong cửa sổ nên không mở dù dịch vụ liên tục gặp lỗi.
- **Nhầm `slidingWindowSize` với `minimumNumberOfCalls`:** một giá trị quy định kích thước cửa sổ, giá trị còn lại quy định số mẫu tối thiểu trước khi tính tỷ lệ.
- **Chỉ cấu hình tỷ lệ lỗi:** dịch vụ có thể phản hồi rất chậm nhưng vẫn trả về thành công; cần đặt `slowCallDurationThreshold` và `slowCallRateThreshold` nếu độ trễ cũng là tín hiệu suy giảm.
- **Ghi nhận exception không đúng:** lỗi nghiệp vụ dự kiến hoặc exception bị bỏ qua có thể làm tỷ lệ sai lệch nếu phân loại không phù hợp.
- **Cho rằng circuit breaker thay thế timeout:** circuit breaker phát hiện và chặn lời gọi mới sau khi đủ điều kiện; timeout mới giới hạn thời gian chờ của một lời gọi đang chạy.
- **Đánh giá sai các lời gọi đồng thời:** những lời gọi đã được cho phép trước thời điểm chuyển sang `OPEN` vẫn có thể tiếp tục hoàn tất. Mở mạch không hủy các lời gọi đang bay.

Khi thiết kế, hãy chọn cửa sổ phù hợp với lưu lượng, đặt số mẫu tối thiểu đủ đại diện, xác định rõ exception nào là lỗi, và đặt ngưỡng cho cả lỗi lẫn độ trễ theo mục tiêu dịch vụ. Cách cấu hình này giúp circuit breaker phản ứng có căn cứ, giảm lời gọi lặp lại vào dịch vụ đang suy giảm và hạn chế lỗi dây chuyền trong hệ thống Spring Cloud.
