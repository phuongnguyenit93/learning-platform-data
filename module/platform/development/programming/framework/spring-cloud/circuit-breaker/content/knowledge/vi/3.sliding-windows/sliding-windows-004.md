# Tính failureRateThreshold từ các lời gọi được ghi nhận

## failureRateThreshold biểu thị điều gì?

Trong Spring Cloud Circuit Breaker sử dụng Resilience4j, `failureRateThreshold` là ngưỡng phần trăm lỗi mà Circuit Breaker dùng để quyết định chuyển từ `CLOSED` sang `OPEN`. Giá trị cấu hình là phần trăm từ 0 đến 100. Ví dụ `failureRateThreshold: 50` có nghĩa là mạch mở khi tỷ lệ lỗi trong cửa sổ thống kê đạt ít nhất 50%, với điều kiện đã có đủ số lời gọi tối thiểu để đánh giá.

Ngưỡng này được tính từ kết quả mà Circuit Breaker thực sự ghi nhận. Nó không đơn giản là số lỗi chia cho tổng số request mà ứng dụng hoặc API gateway nhìn thấy, bởi một số ngoại lệ có thể được bỏ qua và các lời gọi bị từ chối khi mạch đã mở không thuộc mẫu thống kê của cửa sổ hiện tại.

## Công thức tính

Gọi:

- \(F\) là số lời gọi được ghi nhận là thất bại trong cửa sổ.
- \(N\) là tổng số lời gọi được ghi nhận trong cửa sổ, gồm thành công và thất bại.

Tỷ lệ lỗi được tính như sau:

\[
\text{failureRate} = \frac{F}{N} \times 100\%
\]

Circuit Breaker so sánh tỷ lệ này với `failureRateThreshold`. Nếu `failureRate` lớn hơn hoặc bằng ngưỡng, Resilience4j phát sinh chuyển trạng thái từ `CLOSED` sang `OPEN`. Nếu tỷ lệ thấp hơn ngưỡng, mạch tiếp tục ở `CLOSED` và tiếp tục cập nhật cửa sổ khi có kết quả mới.

Điều kiện đủ mẫu cũng rất quan trọng: chỉ tính tỷ lệ để ra quyết định khi số lời gọi được ghi nhận đạt ít nhất `minimumNumberOfCalls`. Trước thời điểm đó, một vài lỗi liên tiếp chưa đủ để kết luận dịch vụ phụ thuộc đang suy giảm.

## Ví dụ tính từng bước

Giả sử Circuit Breaker được cấu hình với `slidingWindowSize = 10`, `minimumNumberOfCalls = 5` và `failureRateThreshold = 50`. Cửa sổ có thể chứa tối đa 10 kết quả gần nhất, nhưng Circuit Breaker bắt đầu đánh giá ngay khi đã có 5 kết quả.

Sau năm lời gọi đầu tiên, giả sử kết quả là:

| Lời gọi | Kết quả được ghi nhận |
| --- | --- |
| 1 | Thành công |
| 2 | Thất bại |
| 3 | Thất bại |
| 4 | Thành công |
| 5 | Thất bại |

Ta có \(F = 3\), \(N = 5\), do đó:

\[
\text{failureRate} = \frac{3}{5} \times 100\% = 60\%
\]

Vì 60% lớn hơn ngưỡng 50%, Circuit Breaker chuyển sang `OPEN`. Không cần đợi đủ 10 kết quả mới đánh giá. Nếu trong năm lời gọi chỉ có hai lời gọi thất bại, tỷ lệ là \(2/5 \times 100\% = 40\%\), thấp hơn ngưỡng nên mạch vẫn `CLOSED`.

Trường hợp bằng đúng ngưỡng cũng làm mạch mở. Với năm kết quả có hai thất bại và ngưỡng 40%, tỷ lệ bằng 40%, vì vậy điều kiện mở mạch đã được thỏa mãn. Đây là lý do cần hiểu phép so sánh là “lớn hơn hoặc bằng”, không phải chỉ “lớn hơn”.

## Cấu hình cửa sổ và ngưỡng

Ví dụ cấu hình trong `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      orderService:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 20s
```

Các thuộc tính có vai trò khác nhau:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `slidingWindowType` | Chọn cửa sổ theo số lời gọi (`COUNT_BASED`) hoặc theo thời gian (`TIME_BASED`). |
| `slidingWindowSize` | Số kết quả tối đa của cửa sổ đếm, hoặc số giây của cửa sổ thời gian. |
| `minimumNumberOfCalls` | Số lời gọi tối thiểu phải được ghi nhận trước khi tính tỷ lệ để quyết định mở mạch. |
| `failureRateThreshold` | Tỷ lệ lỗi tối thiểu, tính theo phần trăm, để chuyển sang `OPEN`. |
| `waitDurationInOpenState` | Thời gian chờ trong `OPEN` trước khi Circuit Breaker có thể chuyển sang `HALF_OPEN`. |

`minimumNumberOfCalls` phải phù hợp với kích thước cửa sổ. Ví dụ, cửa sổ đếm có kích thước 10 không thể cần 15 lời gọi trong chính cửa sổ đó mới đánh giá. Với `TIME_BASED`, số lời gọi tối thiểu vẫn là số kết quả thực tế được ghi nhận trong khoảng thời gian cấu hình; cửa sổ dài 10 giây không đồng nghĩa luôn có 10 lời gọi.

## COUNT_BASED và TIME_BASED ảnh hưởng đến mẫu số ra sao?

Với `COUNT_BASED`, cửa sổ giữ kết quả của một số lượng lời gọi gần nhất. Khi kết quả mới đi vào một cửa sổ đã đầy, kết quả cũ nhất bị loại khỏi phép tính. Vì thế tỷ lệ phản ánh hành vi của các lời gọi gần đây, thay vì toàn bộ lịch sử từ khi ứng dụng khởi động.

Ví dụ cửa sổ có 10 kết quả, trong đó 4 thất bại và 6 thành công. Tỷ lệ lỗi là 40%. Khi một lời gọi mới thành công đi vào và kết quả cũ nhất vốn là thành công bị loại, cửa sổ vẫn có 4 thất bại trên 10 kết quả. Nếu kết quả bị loại là thất bại, cửa sổ mới có 3 thất bại trên 10 kết quả và tỷ lệ giảm còn 30%.

Với `TIME_BASED`, Resilience4j tổng hợp kết quả trong khoảng thời gian gần nhất được cấu hình, sử dụng các bucket thời gian để cập nhật số liệu. Mẫu số là số lời gọi được ghi nhận trong khoảng thời gian đó. Khi thời gian trôi qua, các kết quả thuộc bucket cũ rời khỏi cửa sổ và tỷ lệ có thể thay đổi ngay cả khi không có thay đổi cấu hình.

## Xác định lời gọi nào được tính là thất bại

Phép chia chỉ có ý nghĩa khi phân loại kết quả đúng. Theo cấu hình mặc định của Resilience4j, ngoại lệ từ lời gọi được ghi nhận là thất bại, ngoại trừ những ngoại lệ được cấu hình bỏ qua. Có thể tùy chỉnh cách phân loại bằng `recordExceptions` và `ignoreExceptions`.

- `recordExceptions` chỉ định các loại ngoại lệ được tính là thất bại. Khi danh sách này được cấu hình, ngoại lệ không thuộc danh sách sẽ được xem là thành công đối với Circuit Breaker, trừ trường hợp được bỏ qua.
- `ignoreExceptions` chỉ định các ngoại lệ không tham gia thống kê: chúng không làm tăng số thất bại cũng không làm tăng số thành công. Quy tắc bỏ qua có độ ưu tiên cao hơn việc ghi nhận lỗi.
- Một lời gọi hoàn tất bình thường được tính là thành công, trừ khi có cấu hình đánh giá kết quả tùy chỉnh.

Ví dụ, nếu cửa sổ có 8 lời gọi hoàn tất bình thường, 2 ngoại lệ được ghi nhận là thất bại và 2 ngoại lệ bị bỏ qua, thì \(N = 10\) và \(F = 2\). Tỷ lệ lỗi là 20%. Hai ngoại lệ bị bỏ qua không nằm trong mẫu số. Nếu tính cả chúng như hai request thất bại hoặc hai request thành công, kết quả sẽ sai.

Một số điểm cần phân biệt:

- Lời gọi bị Circuit Breaker từ chối khi đang `OPEN` thường được thống kê riêng là lời gọi không được phép (`not permitted`), không được cộng vào số thất bại của cửa sổ.
- Lời gọi timeout chỉ được tính là thất bại nếu lỗi timeout được truyền đến Circuit Breaker và được cấu hình ghi nhận. Timeout là cơ chế giới hạn thời gian chờ; `failureRateThreshold` chỉ đánh giá kết quả được ghi nhận.
- Fallback là cách tạo phản hồi thay thế cho tầng gọi. Khi phân tích tỷ lệ lỗi, cần dùng số liệu của Circuit Breaker thay vì đếm phản hồi cuối cùng mà client nhận được, vì fallback có thể che đi ngoại lệ ở giao diện ứng dụng.

## Đọc số liệu để kiểm tra phép tính

Resilience4j cung cấp metrics cho mỗi instance Circuit Breaker. Có thể đọc số lời gọi trong cửa sổ, số lời gọi thất bại và tỷ lệ lỗi để đối chiếu với phép tính:

```java
CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

int bufferedCalls = metrics.getNumberOfBufferedCalls();
int failedCalls = metrics.getNumberOfFailedCalls();
float failureRate = metrics.getFailureRate();

log.info(
    "bufferedCalls={}, failedCalls={}, failureRate={}%, state={}",
    bufferedCalls,
    failedCalls,
    failureRate,
    circuitBreaker.getState()
);
```

Khi số lời gọi chưa đạt `minimumNumberOfCalls`, `getFailureRate()` có thể trả về `-1` để thể hiện chưa đủ dữ liệu đánh giá. Giá trị này không có nghĩa tỷ lệ lỗi âm hoặc bằng 0. Dashboard nên hiển thị riêng trạng thái “chưa đủ mẫu” để người vận hành không hiểu nhầm dịch vụ đang khỏe.

Khi đối chiếu metrics, hãy dùng cùng một thời điểm đọc vì cửa sổ vẫn tiếp tục thay đổi khi lời gọi hoàn tất. Trong môi trường có nhiều instance ứng dụng, mỗi instance có thể có Circuit Breaker và cửa sổ thống kê riêng; tỷ lệ của một instance không nhất thiết bằng tỷ lệ tổng hợp ở API gateway hoặc hệ thống giám sát tập trung.

## Chọn threshold và minimumNumberOfCalls

Ngưỡng thấp khiến Circuit Breaker phản ứng nhanh với một lượng lỗi nhỏ, nhưng cũng dễ mở mạch khi có biến động ngắn. Ngưỡng cao giảm khả năng mở mạch do vài lỗi rời rạc, nhưng có thể để nhiều lời gọi tiếp tục đi đến dịch vụ đang gặp sự cố. Việc chọn ngưỡng nên dựa trên mức lỗi ứng dụng có thể chịu được và hậu quả của việc tiếp tục gọi dịch vụ phụ thuộc.

`minimumNumberOfCalls` giúp tránh kết luận từ mẫu quá nhỏ. Ví dụ, một lỗi trên một lời gọi cho tỷ lệ 100%, nhưng nếu yêu cầu tối thiểu năm lời gọi thì Circuit Breaker chưa mở chỉ vì kết quả đơn lẻ đó. Khi lưu lượng thấp, cần cân nhắc rằng thời gian để tích lũy đủ mẫu có thể dài; khi lưu lượng cao, cửa sổ quá nhỏ có thể phản ứng mạnh với một đợt lỗi thoáng qua.

Không nên chọn `failureRateThreshold` chỉ để dashboard luôn hiển thị trạng thái `CLOSED`. Hãy thử tính với các tình huống vận hành cụ thể: tỷ lệ lỗi bình thường, một đợt lỗi ngắn, dịch vụ mất kết nối và dịch vụ trả lời chậm. Sau đó kiểm tra xem ngưỡng và kích thước cửa sổ có tạo ra thời điểm mở mạch phù hợp với mục tiêu bảo vệ hệ thống hay không.

## Những lỗi tính toán thường gặp

| Cách tính sai | Cách tính đúng |
| --- | --- |
| Lấy tổng request từ gateway làm mẫu số. | Dùng số lời gọi mà Circuit Breaker ghi nhận trong cửa sổ. |
| Chia số lỗi cho `slidingWindowSize` ngay cả khi cửa sổ chưa đầy. | Chia cho số kết quả thực tế đã ghi nhận; chỉ ra quyết định sau khi đủ `minimumNumberOfCalls`. |
| Coi ngoại lệ bị bỏ qua là thành công. | Ngoại lệ bị bỏ qua không thuộc cả tử số lẫn mẫu số. |
| Coi `failureRateThreshold: 50` là 0,5%. | Đây là 50 phần trăm. |
| Nghĩ rằng phải vượt ngưỡng mới mở mạch. | Đạt đúng ngưỡng cũng đủ điều kiện chuyển sang `OPEN`. |
| Cộng lời gọi bị từ chối khi mạch mở vào số thất bại. | Theo dõi lời gọi không được phép riêng với kết quả của các lời gọi đã thực thi. |

Khi hiểu rõ tử số, mẫu số, cách phân loại ngoại lệ và điều kiện đủ mẫu, ta có thể dự đoán chính xác hơn thời điểm Circuit Breaker chuyển từ `CLOSED` sang `OPEN`. Đây là cơ sở để cấu hình Resilience4j phù hợp với lưu lượng thực tế và bảo vệ các dịch vụ phụ thuộc trong hệ thống Spring Cloud.
