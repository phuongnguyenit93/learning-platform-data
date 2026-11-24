# minimumNumberOfCalls và thời điểm đủ mẫu để đánh giá

Trong Spring Cloud CircuitBreaker, khi dùng Resilience4j, circuit breaker không mở mạch chỉ vì một lời gọi thất bại. Nó cần quan sát một số lượng kết quả đủ lớn trong *sliding window* rồi mới tính tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm. Tham số `minimumNumberOfCalls` quy định số lời gọi tối thiểu phải được ghi nhận trong cửa sổ hiện tại trước khi Resilience4j bắt đầu đánh giá các tỷ lệ này.

Tham số này giúp tránh quyết định vội vàng từ một mẫu quá nhỏ. Chẳng hạn, nếu chỉ có một yêu cầu và yêu cầu đó thất bại, tỷ lệ lỗi là 100%, nhưng một lỗi đơn lẻ chưa chắc cho thấy dịch vụ phụ thuộc đang gặp sự cố. Ngược lại, nếu đặt số mẫu tối thiểu quá cao so với lưu lượng thực tế, circuit breaker có thể mất nhiều thời gian mới phát hiện vấn đề hoặc không bao giờ có đủ mẫu để đánh giá.

## 1. `minimumNumberOfCalls` có ý nghĩa gì?

Resilience4j lưu kết quả lời gọi trong một cửa sổ trượt. Khi số lời gọi được ghi nhận trong cửa sổ đạt `minimumNumberOfCalls`, circuit breaker mới tính các tỷ lệ dùng để quyết định có mở mạch hay không. Với cấu hình có cả `failureRateThreshold` và `slowCallRateThreshold`, circuit breaker có thể mở khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm đạt ngưỡng tương ứng.

Hai tỷ lệ chính được hiểu như sau:

\[
\text{Failure rate} = \frac{\text{Số lời gọi thất bại}}{\text{Tổng lời gọi được ghi nhận}} \times 100\%
\]

\[
\text{Slow call rate} = \frac{\text{Số lời gọi chậm}}{\text{Tổng lời gọi được ghi nhận}} \times 100\%
\]

Ví dụ, cấu hình `minimumNumberOfCalls: 8` có nghĩa là circuit breaker cần ít nhất 8 kết quả được ghi nhận trong cửa sổ hiện tại trước khi đánh giá tỷ lệ. Nếu mới có 7 kết quả, dù 4 kết quả trong số đó thất bại (tỷ lệ lỗi quan sát được là khoảng 57%), circuit breaker vẫn chưa dùng tỷ lệ đó để mở mạch. Khi kết quả thứ 8 được ghi nhận, nó mới có đủ mẫu để đánh giá.

`minimumNumberOfCalls` không phải số yêu cầu tính từ lúc ứng dụng khởi động, cũng không phải số lời gọi được phép trong trạng thái `HALF_OPEN`. Đây là ngưỡng số mẫu trong cửa sổ thống kê đang hoạt động. Khi cửa sổ trượt, các kết quả cũ lần lượt rời khỏi cửa sổ và các kết quả mới được đưa vào; việc đánh giá luôn dựa trên mẫu hiện có trong cửa sổ đó.

## 2. Thời điểm bắt đầu đánh giá với count-based window

Với `COUNT_BASED`, `slidingWindowSize` là số lời gọi gần nhất được giữ trong cửa sổ. Ví dụ, `slidingWindowSize: 20` nghĩa là cửa sổ thống kê chứa tối đa 20 kết quả gần nhất.

Nếu `minimumNumberOfCalls` nhỏ hơn kích thước cửa sổ, circuit breaker không cần chờ cửa sổ đầy mới bắt đầu đánh giá. Nó có thể bắt đầu ngay khi số kết quả được ghi nhận đạt ngưỡng tối thiểu. Khi cửa sổ đã đầy, mỗi kết quả mới đi vào sẽ thay thế kết quả cũ nhất; các tỷ lệ được cập nhật theo dữ liệu còn lại trong cửa sổ.

Ví dụ với cửa sổ 20 lời gọi, ngưỡng tối thiểu 8 và ngưỡng lỗi 50%:

| Số kết quả đã ghi nhận trong cửa sổ | Thất bại | Thành công | Tỷ lệ lỗi quan sát được | Có đánh giá tỷ lệ? |
|---:|---:|---:|---:|---|
| 5 | 3 | 2 | 60% | Chưa, vì chưa đủ 8 mẫu |
| 7 | 4 | 3 | 57,1% | Chưa, vì chưa đủ 8 mẫu |
| 8 | 4 | 4 | 50% | Có, tỷ lệ đạt ngưỡng mở mạch |
| 9 | 4 | 5 | 44,4% | Có, tỷ lệ dưới ngưỡng 50% |

Ở dòng thứ ba, khi kết quả thứ 8 được ghi nhận, circuit breaker có đủ mẫu và tỷ lệ lỗi đạt 50%, vì vậy có thể chuyển từ `CLOSED` sang `OPEN`. Bảng minh họa thời điểm đủ mẫu; kết quả thực tế còn phụ thuộc vào ngoại lệ nào được cấu hình là lỗi, cách đánh giá lời gọi chậm và các tùy chọn của instance.

Với count-based window, nên bảo đảm `minimumNumberOfCalls` không lớn hơn `slidingWindowSize`. Nếu ngưỡng tối thiểu lớn hơn số phần tử tối đa của cửa sổ, cửa sổ không thể chứa đủ mẫu để bắt đầu đánh giá.

## 3. Thời điểm bắt đầu đánh giá với time-based window

Với `TIME_BASED`, `slidingWindowSize` là độ dài cửa sổ tính bằng giây. Ví dụ, `slidingWindowSize: 10` nghĩa là circuit breaker xem xét các kết quả trong 10 giây gần nhất. `minimumNumberOfCalls` vẫn là số lượng lời gọi tối thiểu, không phải thời lượng.

Giả sử cấu hình cửa sổ 10 giây và `minimumNumberOfCalls: 20`:

- Nếu trong 10 giây gần nhất mới có 12 kết quả được ghi nhận, circuit breaker chưa đủ mẫu để đánh giá tỷ lệ.
- Khi số kết quả trong cửa sổ đạt 20, circuit breaker bắt đầu đánh giá.
- Khi lưu lượng giảm và các kết quả cũ lần lượt hết hạn khỏi cửa sổ, số mẫu hiện có có thể giảm xuống dưới 20. Khi đó không còn đủ dữ liệu trong cửa sổ để thực hiện một lần đánh giá tỷ lệ mới.

Điểm cần chú ý là lưu lượng phải đủ cao trong chính khoảng thời gian của cửa sổ. Nếu một instance chỉ nhận trung bình một lời gọi mỗi giây, cửa sổ 10 giây khó có thể tích lũy 20 kết quả. Circuit breaker có thể ở `CLOSED` mà không có đủ mẫu để đánh giá tỷ lệ lỗi, dù dịch vụ phụ thuộc đang có vấn đề.

## 4. Cấu hình trong Resilience4j

Ví dụ sau dùng count-based window cho dịch vụ tồn kho:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 8
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

Trong cấu hình này:

- `slidingWindowSize: 20` giữ kết quả của tối đa 20 lời gọi gần nhất.
- `minimumNumberOfCalls: 8` yêu cầu ít nhất 8 kết quả trong cửa sổ trước khi tính tỷ lệ.
- `failureRateThreshold: 50` đặt ngưỡng tỷ lệ lỗi ở 50%.
- `slowCallDurationThreshold: 2s` xác định lời gọi từ 2 giây trở lên là lời gọi chậm.
- `slowCallRateThreshold: 50` đặt ngưỡng tỷ lệ lời gọi chậm ở 50%.
- `waitDurationInOpenState: 15s` quy định thời gian chờ trong `OPEN` trước khi chuyển sang giai đoạn thăm dò.
- `permittedNumberOfCallsInHalfOpenState: 3` giới hạn số lời gọi thăm dò được phép ở `HALF_OPEN`.

Nếu muốn đánh giá theo thời gian, có thể thay đổi hai thuộc tính cửa sổ như sau:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
```

Ví dụ thứ hai yêu cầu có ít nhất 20 kết quả trong cửa sổ 10 giây. Cần chọn giá trị phù hợp với lưu lượng thực tế của instance và độ trễ phát hiện sự cố mong muốn.

## 5. Phân biệt ngưỡng mẫu với các tham số liên quan

Các thuộc tính dưới đây thường được cấu hình cùng nhau nhưng có vai trò khác nhau:

| Thuộc tính | Vai trò | Câu hỏi được trả lời |
|---|---|---|
| `slidingWindowType` | Chọn cửa sổ theo số lượng hoặc thời gian. | Cửa sổ được đo theo lời gọi hay theo giây? |
| `slidingWindowSize` | Xác định số phần tử tối đa hoặc độ dài thời gian của cửa sổ. | Cần xem xét bao nhiêu lời gọi gần nhất hoặc bao nhiêu giây gần nhất? |
| `minimumNumberOfCalls` | Xác định số kết quả tối thiểu cần có trong cửa sổ trước khi đánh giá tỷ lệ. | Khi nào đã đủ mẫu để bắt đầu đánh giá? |
| `failureRateThreshold` | Xác định tỷ lệ lỗi khiến circuit breaker mở. | Bao nhiêu phần trăm lời gọi lỗi là không thể chấp nhận? |
| `slowCallRateThreshold` | Xác định tỷ lệ lời gọi chậm khiến circuit breaker mở. | Bao nhiêu phần trăm lời gọi chậm là đáng lo ngại? |
| `permittedNumberOfCallsInHalfOpenState` | Giới hạn số lời gọi thăm dò khi mạch ở `HALF_OPEN`. | Sau khi chờ, cho phép bao nhiêu lời gọi kiểm tra khả năng phục hồi? |

Đặc biệt, `minimumNumberOfCalls` và `permittedNumberOfCallsInHalfOpenState` không thay thế cho nhau. Tham số thứ nhất điều khiển thời điểm đánh giá tỷ lệ trong cửa sổ khi circuit breaker ở `CLOSED`. Tham số thứ hai giới hạn số lời gọi thăm dò sau khi circuit breaker đã ở `OPEN` và chuyển sang `HALF_OPEN`.

## 6. Chọn số mẫu tối thiểu như thế nào?

Không có một giá trị `minimumNumberOfCalls` phù hợp cho mọi dịch vụ. Việc lựa chọn cần cân bằng giữa độ tin cậy của mẫu và tốc độ phát hiện sự cố.

**Nếu đặt quá thấp**, một vài lỗi ngẫu nhiên có thể làm tỷ lệ lỗi tăng mạnh. Circuit breaker dễ mở mạch do nhiễu ngắn hạn, đặc biệt ở dịch vụ có lưu lượng thấp hoặc không đều.

**Nếu đặt quá cao**, circuit breaker cần nhiều thời gian để tích lũy đủ kết quả. Khi dịch vụ phụ thuộc mới bắt đầu lỗi, các lời gọi tiếp tục được gửi đi trong thời gian chờ đủ mẫu. Với cửa sổ thời gian, ngưỡng quá cao còn có thể khiến mạch không bao giờ đủ mẫu nếu lưu lượng không đạt yêu cầu.

Khi chọn giá trị, nên xem xét:

1. **Lưu lượng trên từng instance:** mỗi instance thường có circuit breaker và cửa sổ thống kê riêng. Hãy dùng lưu lượng thực tế của instance, không chỉ tổng lưu lượng toàn cụm.
2. **Độ biến động của lưu lượng:** dịch vụ có lưu lượng theo đợt cần được đánh giá bằng cửa sổ phù hợp với chu kỳ hoạt động. Cửa sổ thời gian quá ngắn có thể thường xuyên thiếu mẫu giữa các đợt lưu lượng.
3. **Mức độ nhạy với lỗi:** phụ thuộc quan trọng như thanh toán có thể cần phát hiện sự cố nhanh, nhưng vẫn phải tránh mở mạch vì một lỗi đơn lẻ không đại diện.
4. **Mục tiêu thời gian phát hiện:** ước lượng thời gian cần để instance tích lũy đủ số mẫu. Ngưỡng tối thiểu và kích thước cửa sổ phải cho phép phát hiện trong khoảng thời gian chấp nhận được.
5. **Đặc tính lỗi và độ trễ:** ngoài tỷ lệ lỗi, cần chọn ngưỡng lời gọi chậm dựa trên thời gian phản hồi mà nghiệp vụ có thể chấp nhận.

Với count-based window, `minimumNumberOfCalls` nhỏ hơn kích thước cửa sổ cho phép đánh giá sớm khi cửa sổ chưa đầy. Với time-based window, hãy ước lượng số lời gọi có thể xuất hiện trong khoảng thời gian đã chọn. Nếu số mẫu tối thiểu không thể đạt được trong điều kiện vận hành thông thường, cần xem lại cả kích thước thời gian lẫn ngưỡng mẫu.

## 7. Ngoại lệ được ghi nhận và mẫu thống kê

Số mẫu dùng để đánh giá phụ thuộc vào cách circuit breaker phân loại kết quả. Lời gọi thành công và lời gọi được ghi nhận là thất bại đóng góp vào thống kê. Các ngoại lệ được cấu hình là *ignored* không được tính là thành công hay thất bại, vì vậy không nên xem mọi lần ném ngoại lệ đều tự động làm tăng số mẫu lỗi.

Ví dụ, lỗi dữ liệu đầu vào do người dùng gửi có thể không phản ánh sức khỏe của dịch vụ tồn kho. Nếu loại lỗi đó được cấu hình để bỏ qua, nó không nên làm tăng tỷ lệ lỗi của phụ thuộc. Ngược lại, timeout hoặc lỗi kết nối thường là tín hiệu cần ghi nhận nếu chúng phản ánh dịch vụ phụ thuộc không thể đáp ứng.

Do đó, khi quan sát thấy circuit breaker chưa đủ mẫu, cần kiểm tra cả lưu lượng và quy tắc phân loại ngoại lệ. Chỉ tăng lưu lượng thử nghiệm hoặc giảm `minimumNumberOfCalls` mà không xem xét quy tắc ghi nhận có thể dẫn đến cấu hình sai.

## 8. Quan sát và kiểm thử thời điểm đủ mẫu

Để xác minh cấu hình, nên quan sát số lời gọi thành công, thất bại, tỷ lệ lỗi, tỷ lệ lời gọi chậm và trạng thái circuit breaker thông qua metrics phù hợp của Resilience4j, Micrometer và Spring Boot Actuator. Cần đối chiếu số mẫu trong cửa sổ với `minimumNumberOfCalls` để hiểu vì sao tỷ lệ chưa được đánh giá.

Một kịch bản kiểm thử đơn giản cho cấu hình count-based có cửa sổ 20 và ngưỡng mẫu 8:

1. Gửi 7 lời gọi, trong đó 4 lời gọi thất bại. Xác nhận circuit breaker chưa mở chỉ dựa trên tỷ lệ của 7 mẫu này vì chưa đạt ngưỡng tối thiểu.
2. Gửi lời gọi thứ 8 và tạo kết quả thành công. Khi đó tỷ lệ lỗi là 4/8 = 50%; nếu ngưỡng lỗi là 50%, xác nhận circuit breaker chuyển sang `OPEN`.
3. Thử gọi tiếp khi mạch `OPEN`; xác nhận lời gọi bị từ chối sớm và fallback hoặc lỗi được xử lý đúng.
4. Sau thời gian chờ, xác nhận circuit breaker chuyển sang `HALF_OPEN` và chỉ cho phép số lời gọi thăm dò đã cấu hình.
5. Cho các lời gọi thăm dò thành công để xác nhận circuit breaker có thể quay về `CLOSED`.

Khi kiểm thử time-based window, cần kiểm soát cả số lượng lời gọi và thời gian phát sinh chúng. Gửi đủ 20 lời gọi nhưng trải dài ngoài cửa sổ 10 giây không tương đương với việc có 20 kết quả trong 10 giây gần nhất. Kiểm thử nên phản ánh đúng tốc độ lưu lượng mà instance có thể nhận trong môi trường thật.

Khi vận hành, nếu circuit breaker thường xuyên ở `CLOSED` dù phụ thuộc lỗi, hãy kiểm tra số mẫu trong cửa sổ, thời gian tích lũy mẫu, loại ngoại lệ bị bỏ qua và mức lưu lượng trên từng instance. Nếu mạch mở quá thường xuyên, hãy xem xét mẫu quá nhỏ, tỷ lệ lỗi ngẫu nhiên và ngưỡng lỗi. Điều chỉnh từng tham số có kiểm soát rồi quan sát lại số liệu để tránh làm giảm khả năng bảo vệ.
