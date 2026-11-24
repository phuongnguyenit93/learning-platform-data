# slowCallRateThreshold khác ngưỡng tỷ lệ lỗi

Trong Spring Cloud CircuitBreaker sử dụng Resilience4j, circuit breaker có thể mở khi dịch vụ phụ thuộc trả lỗi quá thường xuyên hoặc phản hồi quá chậm. Hai tín hiệu này được theo dõi riêng: **failureRateThreshold** giới hạn tỷ lệ lời gọi thất bại, còn **slowCallRateThreshold** giới hạn tỷ lệ lời gọi có thời gian thực thi vượt ngưỡng được xem là chậm.

Phân biệt hai ngưỡng giúp bảo vệ dịch vụ trước cả lỗi rõ ràng lẫn tình trạng suy giảm hiệu năng. Một dịch vụ vẫn có thể trả HTTP 200 cho hầu hết yêu cầu nhưng mất vài giây mới phản hồi; nếu chỉ đo tỷ lệ lỗi, circuit breaker có thể tiếp tục cho phép nhiều lời gọi chậm và làm cạn tài nguyên của dịch vụ gọi.

## Hai loại tín hiệu mà circuit breaker đo

Resilience4j ghi nhận kết quả và thời gian thực thi của lời gọi trong sliding window. Từ tập mẫu đó, nó tính hai tỷ lệ độc lập:

| Thiết lập | Đo lường | Câu hỏi được trả lời |
|---|---|---|
| **failureRateThreshold** | Phần trăm lời gọi được ghi nhận là thất bại. | Bao nhiêu lời gọi không hoàn thành thành công? |
| **slowCallRateThreshold** | Phần trăm lời gọi có thời gian thực thi bằng hoặc dài hơn ngưỡng chậm. | Bao nhiêu lời gọi mất quá nhiều thời gian? |
| **slowCallDurationThreshold** | Thời lượng tuyệt đối dùng để phân loại một lời gọi là chậm. | Một lời gọi phải mất bao lâu thì được tính là chậm? |

Điểm dễ nhầm là **slowCallRateThreshold không phải thời gian chờ**. Đây là một tỷ lệ phần trăm, giống failureRateThreshold. Thời gian được dùng để nhận diện từng lời gọi chậm là slowCallDurationThreshold.

Ví dụ, cấu hình slowCallDurationThreshold là 800 ms và slowCallRateThreshold là 60 có nghĩa là lời gọi mất ít nhất 800 ms được đánh dấu là chậm; khi ít nhất 60% lời gọi trong tập mẫu được đánh giá là chậm, circuit breaker có thể mở. Ngưỡng failureRateThreshold được đánh giá độc lập trên cùng cửa sổ.

## Lời gọi chậm và lời gọi thất bại không đồng nghĩa

Một lời gọi được phân loại theo hai khía cạnh khác nhau:

- **Thành công nhưng chậm:** dịch vụ trả kết quả hợp lệ, nhưng thời gian thực thi vượt slowCallDurationThreshold. Lời gọi này làm tăng slow call rate mà không nhất thiết làm tăng failure rate.
- **Thất bại nhanh:** lời gọi ném ngoại lệ hoặc được phân loại là thất bại trước khi vượt ngưỡng thời gian chậm. Lời gọi này làm tăng failure rate, nhưng không nhất thiết làm tăng slow call rate.
- **Thất bại và chậm:** lời gọi vừa được phân loại là thất bại, vừa mất ít nhất thời lượng ngưỡng chậm. Nó có thể đóng góp vào cả hai tỷ lệ.

Hai nhóm số liệu không loại trừ nhau. Không được cộng failure rate và slow call rate để suy ra tỷ lệ yêu cầu có vấn đề, vì một lời gọi có thể xuất hiện trong cả hai nhóm.

Ví dụ thực tế: dịch vụ đặt hàng gọi dịch vụ tồn kho. Dịch vụ tồn kho vẫn trả dữ liệu đúng, nhưng do truy vấn cơ sở dữ liệu chậm, một số lời gọi mất 1,5 giây. Những lời gọi này là thành công về kết quả nhưng vẫn là lời gọi chậm. Nếu chúng xuất hiện đủ thường xuyên, circuit breaker nên mở để giảm áp lực lên dịch vụ đang suy giảm, dù tỷ lệ lỗi gần bằng 0.

## Cách hai ngưỡng làm circuit breaker mở

Resilience4j đánh giá failure rate và slow call rate sau khi đã có đủ số mẫu tối thiểu. Khi một trong hai tỷ lệ đạt hoặc vượt ngưỡng tương ứng, circuit breaker có thể chuyển từ CLOSED sang OPEN.

~~~mermaid
flowchart TD
    A[Kết quả lời gọi trong sliding window] --> B{Đủ minimumNumberOfCalls?}
    B -->|Chưa| C[Tiếp tục thu thập mẫu]
    B -->|Đủ| D[Tính failure rate]
    D --> E[Tính slow call rate]
    E --> F{Failure rate đạt ngưỡng?}
    F -->|Có| G[Chuyển OPEN]
    F -->|Không| H{Slow call rate đạt ngưỡng?}
    H -->|Có| G
    H -->|Không| I[Tiếp tục CLOSED]
~~~

Điều kiện mở mạch là quan hệ **HOẶC** giữa hai tín hiệu:

- Failure rate đạt ngưỡng, dù các lời gọi còn lại phản hồi nhanh.
- Slow call rate đạt ngưỡng, dù phần lớn lời gọi vẫn trả kết quả thành công.

Không cần cả hai tỷ lệ cùng vượt ngưỡng. Cơ chế này giúp circuit breaker phát hiện được hai dạng sự cố khác nhau: dịch vụ không hoàn thành yêu cầu và dịch vụ vẫn trả kết quả nhưng không đáp ứng trong thời gian chấp nhận được.

Khi mạch đang OPEN, lời gọi mới bị từ chối nhanh. Sau thời gian chờ đã cấu hình, circuit breaker chuyển sang HALF_OPEN để cho phép một số lời gọi thăm dò. Các kết quả thăm dò tiếp tục được đánh giá theo tỷ lệ lỗi và tỷ lệ lời gọi chậm; nếu dịch vụ đã phục hồi, mạch có thể đóng lại, còn nếu vẫn vượt ngưỡng thì mạch mở lại.

## Ví dụ tính tỷ lệ trên cùng một sliding window

Giả sử circuit breaker có các thiết lập:

- slidingWindowType: COUNT_BASED
- slidingWindowSize: 20
- minimumNumberOfCalls: 10
- failureRateThreshold: 50
- slowCallDurationThreshold: 800 ms
- slowCallRateThreshold: 60

Sau khi có 10 lời gọi được ghi nhận, hãy xét các kết quả sau:

| Lời gọi | Kết quả | Thời gian | Thất bại? | Chậm? |
|---:|---|---:|---|---|
| 1 | Thành công | 200 ms | Không | Không |
| 2 | Thành công | 1.000 ms | Không | Có |
| 3 | Thành công | 1.200 ms | Không | Có |
| 4 | Thành công | 300 ms | Không | Không |
| 5 | Thành công | 900 ms | Không | Có |
| 6 | Thất bại | 250 ms | Có | Không |
| 7 | Thành công | 1.100 ms | Không | Có |
| 8 | Thành công | 1.300 ms | Không | Có |
| 9 | Thành công | 400 ms | Không | Không |
| 10 | Thành công | 950 ms | Không | Có |

Trong 10 lời gọi:

- Có 1 lời gọi thất bại, nên failure rate là 1/10 = 10%.
- Có 6 lời gọi chậm, nên slow call rate là 6/10 = 60%.

Failure rate 10% thấp hơn ngưỡng 50%, nhưng slow call rate bằng ngưỡng 60%. Circuit breaker có thể mở vì tín hiệu lời gọi chậm. Đây là tình huống mà failureRateThreshold không phát hiện được vấn đề, còn slowCallRateThreshold phát hiện được sự suy giảm hiệu năng.

Xét trường hợp khác: có 5 lời gọi thất bại nhanh và 5 lời gọi thành công trong 10 mẫu; không lời gọi nào vượt 800 ms. Khi đó failure rate là 50%, slow call rate là 0%. Circuit breaker mở vì failure rate đạt ngưỡng, dù không có vấn đề về thời gian phản hồi.

Hai ví dụ cho thấy mỗi ngưỡng bảo vệ một mục tiêu khác nhau. Failure rate phát hiện tính không sẵn sàng hoặc lỗi xử lý; slow call rate phát hiện dịch vụ vẫn phản hồi nhưng không còn đáp ứng nhanh như yêu cầu.

## Cấu hình trong Spring Cloud CircuitBreaker

Với Spring Cloud CircuitBreaker tích hợp Resilience4j, có thể cấu hình các ngưỡng theo từng instance trong application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

Trong cấu hình này:

- slidingWindowSize là 20, nên cửa sổ giữ kết quả của tối đa 20 lời gọi gần nhất.
- minimumNumberOfCalls là 10, nên circuit breaker cần ít nhất 10 kết quả trước khi đánh giá tỷ lệ.
- failureRateThreshold là 50, nên tỷ lệ lời gọi thất bại đạt 50% có thể làm mạch mở.
- slowCallDurationThreshold là 800 ms, nên lời gọi mất từ 800 ms trở lên được phân loại là chậm.
- slowCallRateThreshold là 60, nên tỷ lệ lời gọi chậm đạt 60% có thể làm mạch mở.
- waitDurationInOpenState là 10 giây, là khoảng thời gian chờ trước khi thử phục hồi.
- permittedNumberOfCallsInHalfOpenState là 3, giới hạn số lời gọi thăm dò trong HALF_OPEN.

Tên instance inventory phải khớp với tên circuit breaker mà ứng dụng tạo, ví dụ inventory khi gọi CircuitBreakerFactory.create("inventory"). Tên và cách cấu hình instance cần nhất quán giữa mã nguồn và application.yml.

Nếu dùng TIME_BASED, slidingWindowSize biểu thị độ dài cửa sổ theo giây thay vì số lời gọi. Hai tỷ lệ vẫn được tính từ các lời gọi nằm trong cửa sổ thời gian đó. Với lưu lượng thấp, cần chú ý minimumNumberOfCalls: nếu chưa đủ mẫu thì chưa có cơ sở để đánh giá tỷ lệ, dù một vài lời gọi đã rất chậm.

## Chọn slowCallDurationThreshold và slowCallRateThreshold

Hai tham số chậm phải được chọn cùng nhau nhưng giải quyết hai câu hỏi khác nhau.

**slowCallDurationThreshold** đặt ranh giới giữa lời gọi bình thường và lời gọi chậm. Hãy căn cứ vào thời gian phản hồi mục tiêu, độ trễ quan sát được của dịch vụ phụ thuộc và ngân sách thời gian còn lại của yêu cầu phía trên. Nếu đặt quá thấp, biến động độ trễ bình thường cũng bị tính là chậm. Nếu đặt quá cao, circuit breaker chỉ nhận ra sự cố khi người dùng đã phải chờ quá lâu.

**slowCallRateThreshold** xác định mức phổ biến của tình trạng chậm trước khi mở mạch. Nếu đặt quá thấp, chỉ một tỷ lệ nhỏ lời gọi chậm cũng có thể làm gián đoạn lời gọi đến phụ thuộc. Nếu đặt quá cao, hệ thống có thể tiếp tục gửi nhiều yêu cầu chậm và chiếm dụng tài nguyên trong thời gian dài.

Có thể dùng số liệu độ trễ p95 hoặc p99 trong điều kiện vận hành bình thường để chọn ngưỡng thời gian ban đầu. Sau đó quan sát tỷ lệ lời gọi vượt ngưỡng khi có tải tăng hoặc phụ thuộc suy giảm. Không nên sao chép nguyên một bộ giá trị giữa các dịch vụ, vì mỗi dịch vụ có mục tiêu độ trễ, lưu lượng và mức độ quan trọng khác nhau.

Một cách tiếp cận thực tế:

1. Xác định thời gian phản hồi mà nghiệp vụ chấp nhận cho lời gọi phụ thuộc.
2. Đo độ trễ bình thường và đặt slowCallDurationThreshold cao hơn vùng biến động thông thường, nhưng vẫn nằm trong ngân sách thời gian.
3. Chọn slowCallRateThreshold theo mức độ suy giảm có thể chấp nhận trước khi ngắt mạch.
4. Chọn sliding window và minimumNumberOfCalls để tỷ lệ phản ánh đủ số mẫu.
5. Quan sát số liệu trong môi trường thử nghiệm và điều chỉnh ngưỡng dựa trên hành vi thực tế.

## Quan hệ với timeout và fallback

slowCallRateThreshold không thay thế timeout. Circuit breaker đánh giá tỷ lệ lời gọi chậm từ kết quả và thời gian thực thi đã ghi nhận; nó không tự dừng một lời gọi đang chạy chỉ vì lời gọi đó đã vượt slowCallDurationThreshold.

Ví dụ, một lời gọi có thể mất 2 giây mới trả kết quả thành công. Circuit breaker có thể ghi nhận đây là lời gọi chậm sau khi lời gọi hoàn tất, rồi mở mạch cho các lời gọi tiếp theo nếu tỷ lệ chậm vượt ngưỡng. Lời gọi hiện tại vẫn có thể trả kết quả thành công cho người gọi.

Timeout giới hạn thời gian chờ của từng lời gọi. Khi timeout được kích hoạt và lời gọi được phân loại là thất bại, nó có thể làm tăng failure rate; nếu thời gian thực thi đã vượt ngưỡng chậm, nó cũng có thể góp phần vào slow call rate. Cần cấu hình timeout của HTTP client hoặc TimeLimiter phù hợp với ngân sách đáp ứng, đồng thời hiểu cách hủy tác vụ của client đang sử dụng.

Fallback xử lý kết quả khi lời gọi thất bại hoặc circuit breaker từ chối lời gọi vì đang OPEN. Một lời gọi chậm nhưng cuối cùng thành công không nhất thiết kích hoạt fallback cho chính lời gọi đó. Tuy nhiên, kết quả chậm vẫn có thể khiến mạch mở và những lời gọi tiếp theo được chuyển sang fallback.

Với dịch vụ tồn kho, fallback có thể trả dữ liệu cache gần nhất kèm trạng thái cho biết dữ liệu có thể chưa cập nhật. Không nên trả một kết quả giả định là chính xác khi nghiệp vụ cần số lượng tồn kho hiện tại để xác nhận đơn hàng. Hãy thiết kế fallback theo mức độ chấp nhận dữ liệu cũ của từng chức năng.

## Kiểm thử và theo dõi hai ngưỡng

Để xác nhận cấu hình, hãy kiểm thử riêng từng tín hiệu và một tình huống kết hợp:

| Kịch bản | Kết quả mong đợi |
|---|---|
| Dịch vụ trả lỗi nhanh vượt failureRateThreshold, thời gian dưới ngưỡng chậm. | Mạch mở do failure rate. |
| Dịch vụ trả thành công nhưng độ trễ vượt slowCallDurationThreshold đủ thường xuyên. | Mạch mở do slow call rate. |
| Một số lời gọi vừa lỗi vừa chậm. | Các lời gọi đó có thể đóng góp vào cả hai tỷ lệ. |
| Số lời gọi thấp hơn minimumNumberOfCalls. | Chưa đánh giá ngưỡng tỷ lệ từ tập mẫu chưa đủ. |
| Dịch vụ phục hồi trong HALF_OPEN và các lời gọi thăm dò đạt yêu cầu. | Mạch chuyển về CLOSED. |
| Dịch vụ vẫn chậm hoặc lỗi trong HALF_OPEN. | Mạch quay lại OPEN. |

Khi vận hành, theo dõi trạng thái circuit breaker cùng failure rate, slow call rate và thời gian phản hồi. Nếu mạch mở do failure rate, hãy tìm nguyên nhân của ngoại lệ, lỗi mạng hoặc lỗi nghiệp vụ. Nếu mạch mở do slow call rate, hãy kiểm tra truy vấn cơ sở dữ liệu, độ trễ mạng, giới hạn tài nguyên, hàng đợi và tải của dịch vụ phụ thuộc.

Cần xem xét cả tần suất fallback và số lời gọi bị từ chối. Fallback tăng có thể giúp API tiếp tục phản hồi, nhưng cũng có thể cho thấy người dùng thường xuyên nhận dữ liệu suy giảm. Sau khi điều chỉnh ngưỡng, hãy kiểm tra lại cả tình huống lỗi nhanh lẫn phản hồi chậm để tránh bảo vệ tốt một loại sự cố nhưng bỏ sót loại còn lại.

## Ghi nhớ khi thiết kế

failureRateThreshold đo tỷ lệ lời gọi thất bại; slowCallRateThreshold đo tỷ lệ lời gọi vượt ngưỡng thời gian chậm; slowCallDurationThreshold xác định thời lượng phân loại một lời gọi là chậm. Resilience4j đánh giá hai tỷ lệ trên sliding window sau khi có đủ số mẫu và có thể mở circuit breaker khi một trong hai tỷ lệ đạt ngưỡng.

Vì vậy, một dịch vụ có thể vẫn trả lời thành công nhưng circuit breaker vẫn mở để bảo vệ hệ thống gọi khỏi độ trễ kéo dài. Kết hợp hai ngưỡng với timeout, bulkhead và fallback phù hợp giúp dịch vụ vừa giới hạn tác động của lỗi, vừa duy trì khả năng phục vụ khi phụ thuộc suy giảm hiệu năng.

