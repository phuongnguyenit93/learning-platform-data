# Đặt ngưỡng phù hợp lưu lượng thấp và lưu lượng cao

Ngưỡng Circuit Breaker quyết định khi nào ứng dụng ngừng gửi lời gọi đến một dependency đang có dấu hiệu không khỏe. Nếu ngưỡng quá nhạy, một vài lỗi thoáng qua có thể làm mạch mở dù dịch vụ vẫn phục vụ được phần lớn request. Nếu ngưỡng quá lỏng, ứng dụng tiếp tục gửi nhiều lời gọi vào dependency đang suy giảm, làm tăng độ trễ và tiêu thụ tài nguyên của caller.

Một bộ ngưỡng phù hợp phụ thuộc vào lưu lượng, độ trễ bình thường, mức độ biến động và hậu quả khi lời gọi thất bại. Cùng một cấu hình có thể hoạt động tốt với một dependency có hàng nghìn lời gọi mỗi giây nhưng không phù hợp với dependency chỉ nhận vài lời gọi mỗi phút.

Bài học trình bày cách chọn loại sliding window, số mẫu tối thiểu, failure rate threshold, slow-call threshold và số lời gọi thăm dò HALF_OPEN cho lưu lượng thấp và lưu lượng cao. Các ví dụ sử dụng Resilience4j trong Spring Cloud CircuitBreaker; những con số được đưa ra là điểm khởi đầu để đo lường, không phải ngưỡng dùng chung cho mọi hệ thống.

## 1. Vì sao lưu lượng ảnh hưởng đến ngưỡng?

Circuit Breaker đánh giá các kết quả lời gọi đi qua nó. Để tính failure rate hoặc slow-call rate, Resilience4j cần có đủ số mẫu. Số lượng mẫu đến nhanh hay chậm phụ thuộc trực tiếp vào lưu lượng của dependency.

Giả sử hai dependency cùng có 50% lời gọi thất bại:

- Dependency A nhận 1.000 lời gọi mỗi giây. Chỉ trong một giây đã có khoảng 1.000 mẫu để đánh giá.
- Dependency B nhận 1 lời gọi mỗi phút. Cần nhiều phút mới tích lũy được số mẫu tương đương.

Nếu cả hai dùng minimumNumberOfCalls bằng 100, Circuit Breaker của A có thể bắt đầu đánh giá gần như ngay lập tức, trong khi B có thể không bao giờ đạt đủ 100 mẫu trong cửa sổ thời gian đã chọn.

Ngược lại, nếu đặt minimumNumberOfCalls bằng 1 cho mọi dependency, một lỗi đơn lẻ ở dependency lưu lượng thấp có thể làm mạch mở. Điều đó có thể gây gián đoạn chức năng dù lỗi chỉ là một sự cố thoáng qua.

Vì vậy, cần cân bằng ba yếu tố:

1. **Độ tin cậy của mẫu:** cần bao nhiêu kết quả trước khi kết luận dependency đang lỗi?
2. **Tốc độ phát hiện:** hệ thống có thể chờ bao lâu trước khi ngắt lời gọi?
3. **Mức độ tác động:** nếu tiếp tục gọi dependency đang lỗi, caller sẽ tiêu tốn bao nhiêu tài nguyên và ảnh hưởng bao nhiêu request?

## 2. Sliding window và minimumNumberOfCalls

Resilience4j hỗ trợ hai kiểu sliding window chính:

| Kiểu cửa sổ | Cách tính | Phù hợp khi |
| --- | --- | --- |
| COUNT_BASED | Giữ kết quả của một số lượng lời gọi gần nhất | Muốn đánh giá theo số mẫu và lưu lượng tương đối ổn định |
| TIME_BASED | Tổng hợp kết quả trong một khoảng thời gian gần nhất | Muốn đánh giá theo thời gian thực, nhất là khi lưu lượng biến động |

Với COUNT_BASED, slidingWindowSize là số lời gọi gần nhất được giữ trong cửa sổ. Ví dụ size bằng 100 nghĩa là tỷ lệ được tính trên tối đa 100 lời gọi gần nhất sau khi đạt số mẫu tối thiểu.

Với TIME_BASED, slidingWindowSize là độ dài cửa sổ tính bằng giây. Ví dụ size bằng 60 nghĩa là kết quả trong 60 giây gần nhất được dùng để đánh giá.

minimumNumberOfCalls là số lời gọi tối thiểu cần có trước khi Circuit Breaker tính failure rate và slow-call rate. Nếu số mẫu trong cửa sổ chưa đạt mức này, Circuit Breaker chưa thể kết luận tỷ lệ đã vượt ngưỡng.

Điểm quan trọng: TIME_BASED không tự giải quyết vấn đề ít mẫu. Nếu cửa sổ dài 5 phút nhưng chỉ có một request trong khoảng đó, minimumNumberOfCalls bằng 10 vẫn chưa đạt. Loại cửa sổ quyết định phạm vi thời gian hoặc số lời gọi được giữ; minimumNumberOfCalls quyết định cần có bao nhiêu mẫu để bắt đầu đánh giá.

## 3. Ước lượng số mẫu theo lưu lượng

Có thể ước lượng số lời gọi kỳ vọng trong một cửa sổ bằng công thức đơn giản:

\[
N \approx \lambda \times W
\]

Trong đó:

- N là số lời gọi kỳ vọng trong cửa sổ.
- λ là tốc độ lời gọi trung bình, tính bằng lời gọi mỗi giây.
- W là độ dài cửa sổ tính bằng giây.

Ví dụ, một dependency nhận trung bình 2 lời gọi mỗi phút và dùng cửa sổ 5 phút:

\[
N \approx \frac{2}{60} \times 300 = 10
\]

Với lưu lượng này, một cửa sổ 5 phút kỳ vọng có khoảng 10 mẫu. Nếu minimumNumberOfCalls đặt bằng 20, Circuit Breaker thường không có đủ mẫu để đánh giá trong một cửa sổ như vậy.

Đây chỉ là ước lượng trung bình. Lưu lượng thực tế có thể đến theo burst, có giờ cao điểm và khoảng thời gian không có request. Hãy đo phân phối lưu lượng theo thời gian thay vì chỉ dùng trung bình cả ngày.

Khi thiết kế, nên trả lời:

- Trong điều kiện bình thường, một cửa sổ có bao nhiêu mẫu?
- Khi lưu lượng giảm, Circuit Breaker có còn đủ mẫu không?
- Khi dependency bắt đầu lỗi, mất bao lâu để đạt minimumNumberOfCalls?
- Cần chờ bao lâu trước khi hệ thống có thể phản ứng mà không làm người dùng chịu độ trễ quá lớn?

## 4. Thiết kế cho dependency lưu lượng thấp

Dependency lưu lượng thấp thường gặp ở các chức năng ít được gọi, ví dụ dịch vụ tạo báo cáo định kỳ, kiểm tra hạn mức hiếm khi xảy ra hoặc tích hợp với một hệ thống đối tác ít request.

Với loại dependency này, cửa sổ COUNT_BASED lớn có thể mất nhiều giờ hoặc nhiều ngày mới tích lũy đủ mẫu. TIME_BASED thường dễ diễn giải hơn vì cho biết hệ thống đang đánh giá kết quả trong một khoảng thời gian cụ thể.

Tuy nhiên, cửa sổ thời gian dài không đồng nghĩa phát hiện lỗi nhanh. Nếu lưu lượng rất thấp, cần chọn minimumNumberOfCalls đủ nhỏ để có thể đạt được, nhưng không nhỏ đến mức một lỗi đơn lẻ làm mạch mở ngoài ý muốn.

### 4.1. Ví dụ cấu hình lưu lượng thấp

Giả sử một dependency nhận trung bình 1 đến 2 lời gọi mỗi phút. Có thể bắt đầu thử với cửa sổ 5 phút và tối thiểu 3 mẫu:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      partner-report:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 300
        minimumNumberOfCalls: 3
        failureRateThreshold: 50
        slowCallDurationThreshold: 3s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
~~~

Trong ví dụ:

- TIME_BASED và slidingWindowSize bằng 300 đánh giá kết quả trong 5 phút gần nhất.
- minimumNumberOfCalls bằng 3 cho phép bắt đầu đánh giá khi đã có ít nhất 3 mẫu.
- failureRateThreshold bằng 50 nghĩa là tỷ lệ lỗi đạt hoặc vượt 50% có thể làm mạch mở.
- slowCallDurationThreshold bằng 3 giây đánh dấu lời gọi kéo dài từ ngưỡng đó là chậm.
- waitDurationInOpenState bằng 30 giây là thời gian chờ trước giai đoạn thăm dò.
- permittedNumberOfCallsInHalfOpenState bằng 1 chỉ cho phép một lời gọi thăm dò tại một thời điểm theo cấu hình này.

Các giá trị trên chỉ minh họa. Nếu dependency chỉ nhận một request mỗi 10 phút, cửa sổ 5 phút có thể không đủ mẫu. Có thể cần cửa sổ dài hơn, nhưng cũng phải chấp nhận rằng Circuit Breaker sẽ phản ứng chậm hơn. Nếu không thể đạt đủ mẫu một cách đáng tin cậy, cần bổ sung health check, synthetic probe hoặc cơ chế giám sát độc lập thay vì ép Circuit Breaker kết luận từ quá ít dữ liệu.

### 4.2. Tránh ngưỡng quá nhạy

Với 3 mẫu và failure threshold 50%, hai lỗi tạo ra failure rate khoảng 66,7%, đủ để mở mạch. Điều này có thể hợp lý nếu mỗi lỗi đều có tác động lớn, nhưng có thể quá nhạy nếu dependency đôi khi trả lỗi tạm thời.

Nếu minimumNumberOfCalls bằng 1 và failure threshold bằng 50%, chỉ một lời gọi lỗi đã tạo tỷ lệ 100%. Mạch có thể mở ngay sau lỗi đầu tiên. Cấu hình như vậy chỉ nên dùng khi có lý do vận hành rõ ràng và đã kiểm thử tác động.

Một lựa chọn khác là dùng số mẫu tối thiểu cao hơn, chấp nhận thời gian phát hiện lâu hơn và dùng timeout để giới hạn thời gian chờ của từng request. Không có cách đặt ngưỡng nào vừa phản ứng tức thì vừa loại bỏ hoàn toàn báo động giả khi số mẫu quá ít.

## 5. Thiết kế cho dependency lưu lượng cao

Dependency lưu lượng cao có thể tạo hàng trăm hoặc hàng nghìn mẫu trong vài giây. Với COUNT_BASED window quá nhỏ, cửa sổ có thể thay đổi rất nhanh. Một đợt lỗi ngắn hoặc burst traffic có thể làm failure rate dao động mạnh và khiến Circuit Breaker đóng/mở liên tục nếu các tham số không phù hợp.

Với lưu lượng cao, TIME_BASED giúp đánh giá trong một khoảng thời gian cố định, dễ liên hệ với xu hướng vận hành. Cũng có thể dùng COUNT_BASED với cửa sổ đủ lớn nếu muốn giới hạn số mẫu thay vì thời gian.

### 5.1. Ví dụ cấu hình lưu lượng cao

Giả sử dependency nhận khoảng 500 lời gọi mỗi giây. Có thể bắt đầu với cửa sổ 30 giây và minimumNumberOfCalls bằng 200:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 200
        failureRateThreshold: 40
        slowCallDurationThreshold: 500ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 10
~~~

Trong điều kiện lưu lượng ổn định, 500 lời gọi mỗi giây có thể tạo khoảng 15.000 mẫu trong 30 giây. minimumNumberOfCalls bằng 200 được đạt khá nhanh, nhưng cửa sổ 30 giây giúp tỷ lệ phản ánh xu hướng gần đây thay vì chỉ một nhóm rất nhỏ các request.

Các giá trị 40%, 500 ms, 50% và 15 giây không phải chuẩn chung. Chúng cần được so sánh với baseline của Inventory, SLO và mức độ chịu lỗi của nghiệp vụ. Nếu thời gian phản hồi bình thường ở p99 đã là 700 ms, slowCallDurationThreshold bằng 500 ms sẽ đánh dấu phần lớn request là chậm; ngưỡng phải dựa trên dữ liệu thực tế.

### 5.2. COUNT_BASED với lưu lượng cao

Nếu dùng COUNT_BASED, hãy hiểu cửa sổ tương ứng với bao nhiêu thời gian ở lưu lượng hiện tại.

Ví dụ, cửa sổ 1.000 lời gọi tại 500 lời gọi mỗi giây chỉ bao phủ khoảng 2 giây. Một đợt lỗi kéo dài 2 giây có thể chiếm phần lớn cửa sổ và làm mạch mở nhanh. Nếu mục tiêu là làm mượt dao động trong 30 giây, cần cửa sổ khoảng 15.000 lời gọi hoặc chuyển sang TIME_BASED 30 giây.

Lưu lượng có thể thay đổi mạnh giữa giờ thấp điểm và giờ cao điểm. COUNT_BASED giữ số mẫu cố định nhưng thời gian bao phủ thay đổi theo tốc độ request. TIME_BASED giữ thời gian cố định nhưng số mẫu thay đổi. Hãy chọn theo điều đội vận hành muốn so sánh.

## 6. Chọn failureRateThreshold theo mức chịu lỗi

failureRateThreshold là tỷ lệ phần trăm lỗi để Circuit Breaker chuyển sang OPEN khi đã đủ minimumNumberOfCalls.

Ví dụ với failureRateThreshold bằng 50%:

| Số mẫu | Số lỗi | Failure rate | Kết quả khi đã đủ minimumNumberOfCalls |
| ---: | ---: | ---: | --- |
| 10 | 1 | 10% | Chưa vượt ngưỡng |
| 10 | 4 | 40% | Chưa vượt ngưỡng |
| 10 | 5 | 50% | Đạt ngưỡng, có thể mở mạch |
| 10 | 8 | 80% | Vượt ngưỡng |
| 20 | 10 | 50% | Đạt ngưỡng |

Resilience4j mở mạch khi tỷ lệ đạt hoặc vượt ngưỡng, sau khi số mẫu tối thiểu đã đạt. Không nên chỉ chọn threshold dựa trên một con số đẹp như 50%. Hãy xem mức lỗi mà nghiệp vụ có thể chấp nhận trước khi cần ngừng gửi request.

Một API đọc dữ liệu cache có thể chịu được một tỷ lệ lỗi cao hơn nếu fallback hoạt động tốt. Một API xác nhận thanh toán hoặc giữ hàng có thể cần phản ứng sớm hơn vì lỗi hoặc timeout ảnh hưởng trực tiếp đến giao dịch.

Cần phân biệt failure rate của Circuit Breaker với tỷ lệ lỗi người dùng nhìn thấy. Nếu Retry nằm bên trong Circuit Breaker, một request có thể có nhiều attempt nhưng chỉ tạo một kết quả cuối cùng. Nếu Circuit Breaker nằm bên trong Retry, từng attempt có thể đóng góp một mẫu. Ngưỡng chỉ có ý nghĩa khi hiểu rõ ranh giới lời gọi được thống kê.

## 7. Chọn minimumNumberOfCalls có chủ đích

minimumNumberOfCalls giúp tránh kết luận từ một số mẫu quá nhỏ. Nhưng đặt quá cao có thể làm Circuit Breaker không bao giờ đánh giá được trong cửa sổ đã chọn.

Có thể dùng quy trình sau:

1. Đo tốc độ request ở giờ thấp điểm và cao điểm.
2. Chọn loại cửa sổ và độ dài dự kiến.
3. Ước lượng số mẫu trong điều kiện lưu lượng thấp thường gặp.
4. Chọn minimumNumberOfCalls không vượt quá mức mẫu có thể tích lũy trong cửa sổ bình thường.
5. Kiểm tra thời gian từ lúc dependency bắt đầu lỗi đến khi Circuit Breaker mở mạch.
6. Điều chỉnh nếu phát hiện quá chậm hoặc mở mạch do quá ít mẫu.

Ví dụ một dependency nhận 3 request mỗi phút và dùng cửa sổ 5 phút. Số mẫu kỳ vọng khoảng 15. Nếu đặt minimumNumberOfCalls bằng 50, Circuit Breaker không thể đánh giá trong điều kiện lưu lượng bình thường. Nếu đặt bằng 3, nó có thể đánh giá sớm nhưng tỷ lệ sẽ nhạy hơn với từng lỗi.

Không nên giảm minimumNumberOfCalls chỉ để làm dashboard hiển thị failure rate sớm hơn. Nếu số mẫu ít, hãy thể hiện rõ sample count và tránh tạo cảnh báo dựa trên tỷ lệ chưa đủ tin cậy.

## 8. Chọn slowCallDurationThreshold và slowCallRateThreshold

Failure rate phát hiện lời gọi thất bại. Nhưng một dependency có thể vẫn trả HTTP 200 trong khi mất nhiều giây để phản hồi. Những lời gọi chậm giữ thread, connection và làm tăng độ trễ của caller.

slowCallDurationThreshold xác định thời lượng từ đó một lời gọi được tính là chậm. slowCallRateThreshold xác định tỷ lệ lời gọi chậm khiến Circuit Breaker mở mạch, khi đủ mẫu.

Cách chọn ngưỡng:

- Đo latency bình thường theo percentile như p50, p95 và p99.
- Chọn slowCallDurationThreshold dựa trên latency budget và SLO, không chỉ dựa trên trung bình.
- Chọn slowCallRateThreshold theo mức chậm có thể chấp nhận trong một cửa sổ.
- Kiểm tra timeout của HTTP client và TimeLimiter; slow-call threshold không tự hủy lời gọi.
- Xem xét sự khác nhau giữa giờ thấp điểm và giờ cao điểm.

Ví dụ, nếu SLO yêu cầu 99% lời gọi Inventory hoàn tất trong 700 ms, có thể thử slowCallDurationThreshold khoảng 700 ms và theo dõi tỷ lệ lời gọi chậm. Tuy nhiên, nếu timeout của HTTP client là 500 ms, lời gọi có thể thất bại trước khi đạt 700 ms; khi đó slow-call threshold không có nhiều ý nghĩa cho những request bị timeout.

Không đặt slowCallDurationThreshold thấp hơn latency bình thường của dependency. Nếu đặt thấp hơn p50, phần lớn lời gọi hợp lệ sẽ bị đánh dấu là chậm và Circuit Breaker có thể mở thường xuyên.

## 9. Cấu hình thời gian OPEN và số lời gọi HALF_OPEN

waitDurationInOpenState xác định thời gian Circuit Breaker giữ trạng thái OPEN trước khi cho phép thăm dò phục hồi. Thời gian quá ngắn có thể khiến ứng dụng quay lại gọi dependency khi nó chưa ổn định. Thời gian quá dài làm chức năng bị gián đoạn ngay cả khi dependency đã phục hồi.

permittedNumberOfCallsInHalfOpenState giới hạn số lời gọi thăm dò trong HALF_OPEN. Đây là lượng traffic thử nghiệm được gửi đến dependency trước khi Circuit Breaker quyết định đóng lại hoặc mở lại.

| Điều kiện | Cân nhắc cấu hình |
| --- | --- |
| Dependency lưu lượng thấp | Số probe nhỏ để không tạo burst bất ngờ; có thể cần chờ lâu hơn để quan sát đủ kết quả |
| Dependency lưu lượng cao | Có thể cho phép nhiều probe hơn nhưng phải nằm trong năng lực phục hồi của dependency |
| Dependency phục hồi chậm | Tăng waitDurationInOpenState để tránh thử lại quá sớm |
| Dependency có giới hạn concurrency nghiêm ngặt | Giữ số probe thấp và phối hợp với Bulkhead |
| Nhiều replica cùng mở mạch | Cân nhắc hiệu ứng đồng loạt chuyển HALF_OPEN và tạo burst |

Nếu nhiều replica dùng cùng một wait duration, chúng có thể cùng chuyển sang HALF_OPEN gần như đồng thời. Khi đó nhiều instance caller gửi probe cùng lúc đến dependency. Có thể dùng thời gian chờ khác nhau theo instance hoặc cơ chế điều phối phù hợp nếu hệ thống nhạy với burst phục hồi.

Với lưu lượng thấp, chỉ một probe có thể đủ để xác nhận một kết quả ban đầu, nhưng một probe thành công không bảo đảm dependency đã phục hồi ổn định. Hãy cân nhắc số probe, số request thật trong HALF_OPEN và cách hệ thống xử lý khi một probe thất bại.

## 10. Cấu hình riêng theo dependency

Không nên dùng một cấu hình chung cho tất cả dependency chỉ vì chúng cùng nằm trong một ứng dụng. Mỗi dependency có lưu lượng, SLO, khả năng chịu tải và mức độ quan trọng khác nhau.

Có thể dùng configs làm cấu hình cơ sở rồi ghi đè theo từng instance:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 100
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 5

    instances:
      inventory:
        baseConfig: default
        minimumNumberOfCalls: 200
        slowCallDurationThreshold: 500ms
        failureRateThreshold: 40

      partner-report:
        baseConfig: default
        slidingWindowSize: 300
        minimumNumberOfCalls: 3
        slowCallDurationThreshold: 3s
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
~~~

inventory dùng cấu hình hướng đến lưu lượng cao, với số mẫu tối thiểu và ngưỡng độ trễ riêng. partner-report dùng cửa sổ 5 phút, ít mẫu tối thiểu hơn và chỉ một probe trong HALF_OPEN.

Đây là cấu hình minh họa cách tách chính sách. Trước khi dùng, hãy xác nhận tốc độ request và baseline latency của từng dependency. Nếu partner-report thực tế chỉ nhận một request mỗi 15 phút, cửa sổ 5 phút vẫn không thể tạo đủ ba mẫu; cần điều chỉnh cửa sổ hoặc dùng cơ chế health monitoring khác.

## 11. Khi lưu lượng quá thấp để Circuit Breaker có đủ mẫu

Circuit Breaker dựa trên các lời gọi thực tế đi qua nó. Nó không tự gửi health probe định kỳ trong trạng thái CLOSED để kiểm tra dependency khi không có traffic.

Nếu một dependency chỉ được gọi một lần mỗi giờ, sliding window có thể không tích lũy đủ mẫu trong thời gian hữu ích. Hạ minimumNumberOfCalls xuống 1 có thể làm mạch phản ứng với một lỗi, nhưng cũng làm tăng nguy cơ mở mạch do lỗi đơn lẻ.

Trong trường hợp này, hãy cân nhắc:

- Dùng health endpoint hoặc synthetic probe độc lập để kiểm tra dependency theo lịch.
- Dùng timeout để giới hạn thời gian chờ của request thật.
- Dùng fallback hoặc cache nếu nghiệp vụ cho phép.
- Theo dõi lỗi ở tầng HTTP client và service monitor.
- Giữ Circuit Breaker làm lớp bảo vệ bổ sung khi có đủ request, thay vì dùng nó làm công cụ health check duy nhất.

Health check và Circuit Breaker có mục đích khác nhau. Health check hỏi dependency có đang sẵn sàng hay không tại thời điểm probe. Circuit Breaker đánh giá các lời gọi thực tế mà caller đã thực hiện trong cửa sổ. Kết hợp cả hai giúp xử lý tốt hơn những dependency có traffic rất thưa.

## 12. Tránh mở và đóng mạch liên tục

Circuit Breaker có thể chuyển đổi trạng thái liên tục nếu ngưỡng quá nhạy hoặc dependency dao động quanh mức lỗi. Hiện tượng này đôi khi được gọi là flapping.

Các nguyên nhân thường gặp:

- Cửa sổ quá nhỏ.
- minimumNumberOfCalls quá thấp.
- failureRateThreshold quá gần với tỷ lệ lỗi bình thường.
- waitDurationInOpenState quá ngắn.
- HALF_OPEN cho phép quá nhiều probe cùng lúc.
- Nhiều replica thăm dò đồng bộ.
- Retry làm tăng số mẫu lỗi trong cửa sổ.

Có thể giảm flapping bằng cách:

1. Tăng kích thước cửa sổ hoặc chuyển sang TIME_BASED phù hợp.
2. Tăng minimumNumberOfCalls để tránh quyết định từ quá ít mẫu.
3. Chọn waitDurationInOpenState đủ dài để dependency có thời gian phục hồi.
4. Giới hạn số probe HALF_OPEN.
5. Xem xét jitter hoặc phân tán thời điểm thăm dò giữa các replica ở tầng điều phối phù hợp.
6. Theo dõi số lần chuyển trạng thái và thời gian ở mỗi trạng thái.

Không nên chỉ tăng wait duration để che một cấu hình sai. Hãy xem cả failure rate, slow-call rate, sample count, retry attempts và latency để tìm nguyên nhân.

## 13. Retry làm thay đổi cách chọn ngưỡng

Khi Retry được kết hợp với Circuit Breaker, thứ tự lồng quyết định một request logic đóng góp bao nhiêu mẫu:

- Retry ở ngoài, Circuit Breaker ở trong: mỗi attempt có thể trở thành một mẫu.
- Circuit Breaker ở ngoài, Retry ở trong: Circuit Breaker thường ghi nhận kết quả cuối cùng của cả chuỗi retry.

Ví dụ, một request có ba attempt đều thất bại:

| Cách lồng | Mẫu lỗi Circuit Breaker nhận được |
| --- | ---: |
| Retry ngoài, Circuit Breaker trong | Có thể là 3 |
| Circuit Breaker ngoài, Retry trong | 1 |

Do đó, không thể chọn minimumNumberOfCalls chỉ dựa trên số request HTTP đến ứng dụng mà bỏ qua retry. Hãy xác định mẫu của Circuit Breaker là attempt hay request logic, sau đó hiệu chỉnh window và threshold theo đơn vị đó.

Nếu Retry nằm ngoài Circuit Breaker, cần bỏ qua CallNotPermittedException để không thử lại một lời gọi đã bị Circuit Breaker từ chối. Retry cũng cần giới hạn số lần, backoff và timeout tổng thể để không khuếch đại tải.

## 14. Quy trình hiệu chỉnh bằng dữ liệu

Không nên đưa ngưỡng vào production chỉ dựa trên một ví dụ YAML. Có thể hiệu chỉnh theo chu kỳ:

1. **Đo baseline:** thu thập request rate, failure rate, p50/p95/p99 latency và tỷ lệ timeout trong điều kiện bình thường.
2. **Phân loại lưu lượng:** tách giờ thấp điểm, giờ cao điểm và burst.
3. **Chọn window:** COUNT_BASED nếu muốn số mẫu cố định; TIME_BASED nếu muốn khoảng thời gian cố định.
4. **Chọn minimumNumberOfCalls:** bảo đảm có thể đạt trong điều kiện lưu lượng bình thường và thời gian phát hiện phù hợp.
5. **Chọn failure threshold:** dựa trên mức lỗi mà nghiệp vụ có thể chấp nhận.
6. **Chọn slow-call threshold:** dựa trên latency budget và SLO.
7. **Chọn OPEN duration và HALF_OPEN probes:** cân bằng thời gian phục hồi với tải thăm dò.
8. **Mô phỏng lỗi:** tạo lỗi kết nối, HTTP 5xx, timeout và phản hồi chậm.
9. **Đo thời gian phản ứng:** từ khi lỗi bắt đầu đến khi mạch OPEN.
10. **Đo tác động:** số request bị từ chối, fallback, latency và tài nguyên caller.
11. **Điều chỉnh từng tham số:** thay đổi một yếu tố mỗi lần để hiểu tác động.
12. **Triển khai theo từng giai đoạn:** theo dõi metrics sau khi áp dụng và chuẩn bị khả năng rollback.

Nếu có thể, hãy chạy thử trên staging với traffic gần giống production. Khi triển khai nhiều replica, theo dõi từng instance Circuit Breaker vì mỗi instance thường có state và sliding window riêng. Không nên cộng số mẫu của nhiều replica rồi giả định mỗi Circuit Breaker có cùng một cửa sổ toàn cục.

## 15. Đọc metrics để biết ngưỡng có phù hợp không

Các metrics cần theo dõi gồm:

| Metric | Dùng để đánh giá |
| --- | --- |
| Calls theo kind | Số lời gọi thành công, thất bại, bị bỏ qua |
| Failure rate | Tỷ lệ lỗi trong sliding window |
| Slow-call rate | Tỷ lệ lời gọi vượt slowCallDurationThreshold |
| Buffered calls | Số mẫu hiện có trong cửa sổ |
| Not permitted calls | Số lời gọi bị Circuit Breaker từ chối |
| State transitions | Tần suất chuyển CLOSED, OPEN, HALF_OPEN |
| Retry attempts | Số lần thử lại và tỷ lệ retry thành công |
| HTTP client latency | Độ trễ thực tế của từng lần gọi |
| Fallback count | Số lần ứng dụng dùng kết quả dự phòng |

Dấu hiệu cấu hình có thể quá nhạy:

- Circuit Breaker mở sau một hoặc hai lỗi đơn lẻ.
- State chuyển OPEN và CLOSED liên tục.
- Tỷ lệ lỗi thấp nhưng số lần từ chối tăng mạnh.
- HALF_OPEN thất bại do quá nhiều probe được gửi cùng lúc.

Dấu hiệu cấu hình có thể quá lỏng:

- Dependency lỗi kéo dài nhưng Circuit Breaker vẫn CLOSED.
- Thời gian từ lúc lỗi bắt đầu đến khi mở mạch quá lâu.
- Caller tiếp tục giữ nhiều request đang chờ.
- Timeout và thread/connection usage tăng trước khi Circuit Breaker phản ứng.

Cần đọc metrics cùng với sample count. Một failure rate cao khi mới có vài mẫu có ý nghĩa khác với failure rate cao trên hàng nghìn mẫu. Nếu dashboard không hiển thị số mẫu, hãy bổ sung chỉ số buffered calls hoặc một panel tương đương.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Circuit Breaker không mở ở lưu lượng thấp | Không đạt minimumNumberOfCalls trong cửa sổ | Đo request rate, điều chỉnh window/minimum hoặc bổ sung health probe |
| Một lỗi đơn lẻ làm mạch mở | minimumNumberOfCalls quá thấp | Tăng số mẫu tối thiểu nếu nghiệp vụ cho phép |
| Mạch mở quá nhanh ở giờ cao điểm | COUNT_BASED window quá nhỏ theo thời gian thực | Tăng số mẫu hoặc dùng TIME_BASED |
| Mạch phản ứng quá chậm | Window quá dài hoặc minimumNumberOfCalls quá cao | Đo thời gian tích lũy mẫu và điều chỉnh |
| Tỷ lệ lỗi dao động mạnh | Mẫu ít, burst hoặc threshold sát baseline | Tăng window, sample minimum và xem xu hướng |
| Mạch OPEN/CLOSED liên tục | Wait duration ngắn hoặc HALF_OPEN quá nhiều probe | Tăng thời gian chờ và giới hạn probe |
| Slow-call rate luôn cao | Threshold thấp hơn latency bình thường | Dựa vào percentile và SLO để đặt ngưỡng |
| Dashboard báo failure rate cao nhưng ít request | Không xét sample count | Hiển thị buffered calls và đặt điều kiện alert |
| Cấu hình không áp dụng | Sai tên instance hoặc cấu hình bị ghi đè | Kiểm tra instance name, baseConfig và cấu hình thực tế |
| Retry làm mạch mở nhanh ngoài dự kiến | Circuit Breaker đang thống kê từng attempt | Xác định thứ tự bao và hiệu chỉnh theo attempt count |

## 17. Nguyên tắc thiết kế

- Đo request rate theo từng dependency trước khi chọn window.
- Dùng COUNT_BASED khi muốn cố định số mẫu; dùng TIME_BASED khi muốn cố định thời gian đánh giá.
- Chọn minimumNumberOfCalls để tránh kết luận từ quá ít mẫu nhưng vẫn đạt được trong điều kiện traffic bình thường.
- Không hạ minimumNumberOfCalls chỉ để Circuit Breaker phản ứng nhanh mà không đánh giá báo động giả.
- Đặt failureRateThreshold theo mức lỗi nghiệp vụ có thể chấp nhận.
- Đặt slowCallDurationThreshold dựa trên latency percentile và SLO.
- Chọn waitDurationInOpenState và số probe HALF_OPEN theo khả năng phục hồi của dependency.
- Tách cấu hình cho dependency lưu lượng thấp và lưu lượng cao.
- Xem xét retry order vì nó làm thay đổi số mẫu mà Circuit Breaker nhận được.
- Theo dõi sample count, state transition, rejection, fallback và latency.
- Dùng health check hoặc synthetic probe bổ sung khi dependency có traffic quá thưa.
- Kiểm thử các kịch bản burst, lỗi kéo dài, timeout và phục hồi trước khi phát hành.

Không có một bộ ngưỡng Circuit Breaker phù hợp cho mọi lưu lượng. Với dependency lưu lượng thấp, cần tránh quyết định từ quá ít mẫu và có thể phải dùng cửa sổ thời gian dài hơn hoặc health probe độc lập. Với dependency lưu lượng cao, cần đủ mẫu để làm mượt biến động nhưng vẫn phát hiện sự cố trong thời gian chấp nhận được. Khi window, minimumNumberOfCalls, failure threshold, slow-call threshold và HALF_OPEN probes được chọn dựa trên dữ liệu thực tế, Circuit Breaker trong Spring Cloud và Resilience4j có thể bảo vệ dependency hiệu quả mà không gây gián đoạn không cần thiết.

## Tài liệu tham khảo

- [Resilience4j CircuitBreaker — Sliding window and configuration](https://resilience4j.readme.io/docs/circuitbreaker)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Resilience4j Micrometer metrics](https://resilience4j.readme.io/docs/micrometer)

