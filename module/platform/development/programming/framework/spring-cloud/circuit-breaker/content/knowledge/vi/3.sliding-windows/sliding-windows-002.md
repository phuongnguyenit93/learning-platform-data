# slidingWindowSize và lượng dữ liệu được lưu

Trong Spring Cloud CircuitBreaker sử dụng Resilience4j, Circuit Breaker cần quan sát các kết quả gọi gần đây để quyết định có tiếp tục gửi request đến dependency hay chuyển sang trạng thái OPEN. Cửa sổ thống kê (*sliding window*) xác định phạm vi dữ liệu được dùng cho quyết định đó. Thuộc tính `slidingWindowSize` cấu hình kích thước cửa sổ, nhưng ý nghĩa của con số này phụ thuộc vào kiểu cửa sổ được chọn.

Điểm cần hiểu rõ là cửa sổ thống kê lưu các phép đo phục vụ tính tỷ lệ lỗi và tỷ lệ lời gọi chậm. Nó không lưu toàn bộ request, response hay nội dung nghiệp vụ. Vì vậy, kích thước cửa sổ quyết định lượng lịch sử thống kê được giữ lại, chứ không phải số byte dữ liệu HTTP mà ứng dụng có thể lưu.

## 1. Sliding window dùng để làm gì?

Mỗi lần lời gọi đi qua Circuit Breaker, Resilience4j ghi nhận kết quả theo cấu hình của Circuit Breaker đó. Kết quả có thể là thành công, thất bại hoặc lời gọi chậm. Từ các phép đo trong cửa sổ hiện tại, Circuit Breaker tính:

- **Failure rate**: tỷ lệ lời gọi được ghi nhận là thất bại.
- **Slow call rate**: tỷ lệ lời gọi có thời gian thực thi vượt ngưỡng lời gọi chậm.
- **Số lời gọi đã được ghi nhận** trong cửa sổ, làm cơ sở xác định đã đủ dữ liệu đánh giá hay chưa.

Cửa sổ trượt giúp quyết định dựa trên tình trạng gần đây. Ví dụ, một dependency có thể từng lỗi nhiều lần nhưng đã phục hồi. Nếu Circuit Breaker tiếp tục tính cả các lỗi xảy ra từ rất lâu trước đó, nó có thể giữ đánh giá xấu quá lâu. Khi cửa sổ dịch chuyển, các phép đo cũ lần lượt rời khỏi phạm vi thống kê và phép đo mới được đưa vào.

Có thể hình dung quy trình như sau:

~~~mermaid
flowchart LR
    A[Lời gọi đến dependency] --> B[Ghi nhận kết quả và thời gian]
    B --> C[Cập nhật sliding window]
    C --> D{Đủ minimumNumberOfCalls?}
    D -- Chưa --> E[Tiếp tục thu thập dữ liệu]
    D -- Đủ --> F[Tính failure rate và slow call rate]
    F --> G{Có ngưỡng nào bị vượt?}
    G -- Không --> H[Tiếp tục CLOSED]
    G -- Có --> I[Chuyển OPEN]
~~~

Cửa sổ không tự quyết định một lời gọi có được retry hay không. Nó cung cấp số liệu cho Circuit Breaker đánh giá trạng thái. Retry là cơ chế riêng và cần được cấu hình theo chính sách lỗi tạm thời của ứng dụng.

## 2. Hai kiểu cửa sổ và ý nghĩa của slidingWindowSize

Resilience4j hỗ trợ hai kiểu cửa sổ chính:

| Kiểu cửa sổ | Ý nghĩa của `slidingWindowSize` | Phạm vi lịch sử được giữ |
|---|---|---|
| `COUNT_BASED` | Số lời gọi gần nhất | Tối đa N lời gọi được ghi nhận gần đây |
| `TIME_BASED` | Số giây gần nhất | Các phép đo trong N giây gần đây |

### COUNT_BASED: cửa sổ theo số lời gọi

Với `COUNT_BASED`, `slidingWindowSize: 100` có nghĩa là Circuit Breaker thống kê tối đa 100 lời gọi gần nhất. Mỗi lời gọi mới được ghi nhận sẽ làm cửa sổ tiến lên. Khi cửa sổ đã đủ 100 phép đo, phép đo cũ nhất bị loại khỏi phạm vi và phép đo mới được thêm vào.

Ví dụ, cửa sổ có kích thước 5:

| Thời điểm | Năm phép đo đang được giữ |
|---|---|
| Sau lời gọi 5 | 1, 2, 3, 4, 5 |
| Sau lời gọi 6 | 2, 3, 4, 5, 6 |
| Sau lời gọi 7 | 3, 4, 5, 6, 7 |
| Sau lời gọi 8 | 4, 5, 6, 7, 8 |

Khi có lời gọi mới, kết quả cũ nhất lần lượt rời cửa sổ. Nếu lưu lượng tăng mạnh, 100 lời gọi có thể chỉ đại diện cho vài giây. Nếu lưu lượng rất thấp, 100 lời gọi có thể trải dài trong nhiều phút hoặc nhiều giờ. Do đó, kiểu này phản ánh số lượng request gần nhất, không đảm bảo một khoảng thời gian cố định.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
~~~

Trong ví dụ, Circuit Breaker giữ tối đa 100 phép đo lời gọi gần nhất. Khi có ít nhất 20 lời gọi được ghi nhận trong cửa sổ, nó mới bắt đầu đánh giá tỷ lệ lỗi và tỷ lệ lời gọi chậm. Ngưỡng 50 nghĩa là tỷ lệ tương ứng đạt từ 50% trở lên có thể khiến Circuit Breaker mở mạch.

### TIME_BASED: cửa sổ theo thời gian

Với `TIME_BASED`, `slidingWindowSize: 10` có nghĩa là Circuit Breaker thống kê các phép đo trong 10 giây gần nhất. Kích thước ở đây là số giây, không phải số request.

Resilience4j chia cửa sổ thời gian thành các bucket theo từng giây. Mỗi bucket tổng hợp các phép đo phát sinh trong giây tương ứng. Nếu một giây có 500 lời gọi, các kết quả được cộng dồn vào phép tổng hợp của bucket đó; Circuit Breaker không cần tạo một bucket riêng cho từng request.

Ví dụ, cửa sổ thời gian 5 giây:

| Thời điểm đánh giá | Các bucket thời gian được tính |
|---|---|
| 12:00:05 | 12:00:01 đến 12:00:05 |
| 12:00:06 | 12:00:02 đến 12:00:06 |
| 12:00:07 | 12:00:03 đến 12:00:07 |

Khi thời gian tiến lên, bucket cũ nhất rời cửa sổ và bucket của giây mới được sử dụng. Số request trong mỗi giây có thể thay đổi, nhưng số bucket của cửa sổ vẫn được giới hạn theo số giây đã cấu hình.

Ví dụ cấu hình:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
~~~

Trong ví dụ, Circuit Breaker xem xét dữ liệu trong 10 giây gần nhất. Nó chỉ đánh giá tỷ lệ khi có tối thiểu 20 lời gọi được ghi nhận trong cửa sổ đó. Nếu trong 10 giây chỉ có 8 lời gọi, dù cả 8 đều thất bại, điều kiện số mẫu tối thiểu vẫn chưa đạt.

## 3. slidingWindowSize có lưu toàn bộ request không?

Không. Sliding window của Resilience4j được thiết kế để thống kê hiệu quả, không phải để lưu lịch sử giao dịch đầy đủ.

Các phép đo được dùng để tổng hợp những thông tin như:

- Số lời gọi được ghi nhận.
- Số lời gọi thất bại.
- Số lời gọi chậm.
- Tổng thời lượng thực thi được dùng cho thống kê.

Tùy kiểu cửa sổ, các phép đo được giữ dưới dạng từng measurement hoặc các bucket tổng hợp. Circuit Breaker không cần lưu toàn bộ nội dung request, response body, header HTTP, dữ liệu nghiệp vụ hay bản ghi đầy đủ của từng giao dịch để tính các tỷ lệ này. Muốn lưu những thông tin phục vụ điều tra request cụ thể, ứng dụng cần dùng log, tracing hoặc hệ thống lưu sự kiện phù hợp.

Sự khác biệt về cách lưu giữa hai kiểu cửa sổ:

| Đặc điểm | COUNT_BASED | TIME_BASED |
|---|---|---|
| Đơn vị của kích thước | Một lời gọi | Một giây |
| Cấu trúc khái niệm | Vòng đệm gồm N phép đo lời gọi | Vòng đệm gồm N bucket, mỗi bucket tổng hợp một giây |
| Khi có thêm lưu lượng | Mỗi lời gọi mới thay thế phép đo cũ nhất khi cửa sổ đầy | Các lời gọi trong cùng giây được cộng vào bucket thời gian |
| Yếu tố quyết định dung lượng cấu trúc cửa sổ | Kích thước N lời gọi | Kích thước N giây |
| Có lưu request/response body không? | Không | Không |

Cả hai kiểu đều dùng cấu trúc vòng đệm và số liệu tổng hợp để tránh phải duyệt lại toàn bộ lịch sử mỗi lần cần lấy snapshot. Chi phí cập nhật và lấy snapshot được thiết kế ở mức hằng số theo số phép đo trong cửa sổ; dung lượng cấu trúc tăng theo kích thước cửa sổ đã cấu hình.

Điều này không có nghĩa toàn bộ ứng dụng luôn dùng cùng một lượng bộ nhớ. Mỗi Circuit Breaker instance có trạng thái và cửa sổ riêng. Nếu ứng dụng tạo rất nhiều instance với tên khác nhau, tổng dung lượng dành cho các cửa sổ cũng tăng theo số instance.

## 4. Phân biệt slidingWindowSize và minimumNumberOfCalls

Hai thuộc tính này thường bị nhầm lẫn vì đều liên quan đến số lượng phép đo.

- `slidingWindowSize` xác định kích thước cửa sổ: số lời gọi với `COUNT_BASED`, hoặc số giây với `TIME_BASED`.
- `minimumNumberOfCalls` xác định số lời gọi tối thiểu cần có trong cửa sổ trước khi Circuit Breaker tính tỷ lệ lỗi và tỷ lệ lời gọi chậm để đánh giá ngưỡng.

Ví dụ với `COUNT_BASED`:

~~~yaml
slidingWindowType: COUNT_BASED
slidingWindowSize: 50
minimumNumberOfCalls: 20
failureRateThreshold: 50
~~~

Diễn giải:

1. Cửa sổ có thể chứa kết quả của tối đa 50 lời gọi gần nhất.
2. Sau 10 lời gọi, Circuit Breaker vẫn chưa có đủ 20 mẫu để đánh giá tỷ lệ.
3. Khi có 20 lời gọi được ghi nhận, Circuit Breaker bắt đầu tính tỷ lệ trên số mẫu hiện có.
4. Khi cửa sổ đầy, mỗi lời gọi mới làm phép đo cũ nhất rời cửa sổ và số liệu được tính trên 50 lời gọi gần nhất.

Nếu 20 lời gọi đầu tiên có 10 lời gọi thất bại, failure rate là 50%. Với `failureRateThreshold: 50`, ngưỡng lỗi đã đạt và Circuit Breaker có thể chuyển sang OPEN.

Ví dụ với `TIME_BASED`:

~~~yaml
slidingWindowType: TIME_BASED
slidingWindowSize: 10
minimumNumberOfCalls: 20
failureRateThreshold: 50
~~~

Diễn giải:

1. Cửa sổ thống kê bao phủ 10 giây gần nhất.
2. `minimumNumberOfCalls: 20` yêu cầu có ít nhất 20 lời gọi trong khoảng thời gian đó.
3. Nếu chỉ có 8 lời gọi trong 10 giây, Circuit Breaker chưa đánh giá tỷ lệ.
4. Nếu có 40 lời gọi, tỷ lệ được tính trên các lời gọi được ghi nhận trong cửa sổ 10 giây.

Với `COUNT_BASED`, số mẫu tối thiểu phải phù hợp với số lượng lời gọi tối đa mà cửa sổ có thể chứa. Với `TIME_BASED`, số lời gọi tối thiểu là một ngưỡng độc lập với số giây của cửa sổ; một cửa sổ 10 giây hoàn toàn có thể yêu cầu 100 lời gọi tối thiểu nếu lưu lượng dự kiến đủ cao.

## 5. Dữ liệu nào được tính là thành công, thất bại hoặc lời gọi chậm?

Cửa sổ chỉ hữu ích khi hiểu rõ cách Circuit Breaker phân loại kết quả. Resilience4j có cấu hình để xác định exception nào được ghi nhận là thất bại, exception nào được bỏ qua, và có thể dùng predicate để quyết định theo loại lỗi.

Một lời gọi thành công làm tăng số lời gọi thành công. Một exception được cấu hình ghi nhận là thất bại làm tăng số lời gọi thất bại. Exception bị cấu hình bỏ qua không được tính như một lời gọi thành công hoặc thất bại trong phép thống kê của Circuit Breaker.

Lời gọi chậm được xác định theo `slowCallDurationThreshold`. Một lời gọi có thể thành công nhưng vẫn được tính là chậm nếu thời gian thực thi vượt ngưỡng. Một lời gọi thất bại cũng có thể đồng thời là lời gọi chậm nếu nó kéo dài quá ngưỡng thời gian.

Công thức khái quát:

\[
\text{Failure rate} =
\frac{\text{Số lời gọi thất bại}}{\text{Số lời gọi được ghi nhận}}
\times 100\%
\]

\[
\text{Slow call rate} =
\frac{\text{Số lời gọi chậm}}{\text{Số lời gọi được ghi nhận}}
\times 100\%
\]

Mẫu số là số lời gọi được ghi nhận trong cửa sổ hiện tại. Các exception bị bỏ qua không được xem như mẫu thành công để làm giảm tỷ lệ lỗi. Vì vậy, việc cấu hình `recordExceptions`, `ignoreExceptions` hoặc các predicate liên quan có thể ảnh hưởng trực tiếp đến quyết định mở mạch.

Ví dụ, một dịch vụ tồn kho trả lỗi 404 vì mã sản phẩm không tồn tại. Nếu đây là kết quả nghiệp vụ bình thường, ứng dụng nên cân nhắc không tính lỗi này như một lỗi hạ tầng của dependency. Ngược lại, lỗi kết nối hoặc lỗi 503 có thể là tín hiệu cần ghi nhận để Circuit Breaker đánh giá sức khỏe dịch vụ.

## 6. Chọn kích thước cửa sổ theo lưu lượng và mục tiêu bảo vệ

Không có một con số `slidingWindowSize` phù hợp cho mọi dependency. Cần xem xét lưu lượng, độ biến động của traffic, thời gian phản hồi và mức độ nhanh nhạy mà hệ thống mong muốn khi phát hiện sự cố.

### Khi nên chọn COUNT_BASED?

COUNT_BASED phù hợp khi muốn đánh giá một số lượng request gần nhất và lưu lượng có thể biến động theo thời gian. Ví dụ, hệ thống muốn luôn xem xét 100 lời gọi gần nhất bất kể chúng phát sinh trong một giây hay một phút.

Cửa sổ quá nhỏ có thể khiến một vài lỗi ngẫu nhiên làm tỷ lệ thay đổi mạnh. Cửa sổ quá lớn làm các lỗi mới bị pha loãng bởi nhiều kết quả cũ hơn, khiến Circuit Breaker phản ứng chậm hơn với sự cố vừa xuất hiện.

### Khi nên chọn TIME_BASED?

TIME_BASED phù hợp khi muốn đánh giá tình trạng dependency trong một khoảng thời gian cố định, ví dụ 10 giây hoặc 60 giây gần nhất. Kiểu này hữu ích khi cần so sánh tỷ lệ lỗi theo thời gian thực, đặc biệt khi traffic thay đổi đáng kể giữa các thời điểm.

Cửa sổ quá ngắn có thể phản ứng mạnh với một đợt lỗi nhỏ hoặc traffic đột biến. Cửa sổ quá dài có thể duy trì ảnh hưởng của sự cố đã kết thúc lâu hơn mong muốn. Cần chọn `minimumNumberOfCalls` phù hợp để tránh đưa ra quyết định từ một số lượng mẫu quá ít.

### Một số yếu tố cần cân nhắc

| Yếu tố | Câu hỏi cần trả lời | Hướng cân nhắc |
|---|---|---|
| Lưu lượng trung bình | Dependency nhận bao nhiêu lời gọi mỗi giây? | Ước lượng số mẫu thực tế trong cửa sổ |
| Lưu lượng đột biến | Traffic có tăng mạnh theo giờ hoặc theo chiến dịch không? | TIME_BASED giữ phạm vi thời gian cố định; COUNT_BASED giữ số request cố định |
| Tốc độ phát hiện lỗi | Hệ thống cần phản ứng nhanh đến mức nào? | Cửa sổ ngắn nhạy hơn nhưng dễ dao động |
| Độ ổn định của tỷ lệ | Có cần nhiều mẫu để tránh quyết định từ vài lỗi ngẫu nhiên không? | Điều chỉnh minimumNumberOfCalls |
| Số Circuit Breaker instance | Ứng dụng có tạo nhiều instance theo tenant hoặc dependency không? | Tránh tạo instance không cần thiết và theo dõi tổng tài nguyên |
| Tài nguyên bộ nhớ | Có bao nhiêu phép đo hoặc bucket được giữ đồng thời? | Chọn kích thước cửa sổ theo nhu cầu thực tế |

## 7. Ví dụ tính toán và lựa chọn cấu hình

Giả sử dịch vụ đơn hàng gọi dịch vụ tồn kho trung bình 40 lần mỗi giây. Nhóm phát triển muốn Circuit Breaker đánh giá lỗi trên khoảng 10 giây gần nhất và yêu cầu ít nhất 100 lời gọi trước khi quyết định.

Cấu hình có thể là:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 100
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Ở mức 40 lời gọi mỗi giây, cửa sổ 10 giây có thể quan sát khoảng 400 lời gọi khi traffic ổn định. Đây là ước lượng lưu lượng, không phải số lượng cố định mà cửa sổ cam kết lưu. Nếu traffic giảm, số mẫu trong cửa sổ giảm; nếu traffic tăng, số lời gọi được cộng vào các bucket cũng tăng.

Giả sử trong 10 giây gần nhất có 200 lời gọi được ghi nhận, trong đó 120 thất bại và 80 thành công. Failure rate là:

\[
\frac{120}{200}\times100\%=60\%
\]

Với ngưỡng 50%, tỷ lệ lỗi đã vượt ngưỡng. Nếu đã đủ số mẫu tối thiểu, Circuit Breaker có thể chuyển sang OPEN.

Nếu dùng COUNT_BASED với `slidingWindowSize: 400`, Circuit Breaker sẽ đánh giá 400 lời gọi gần nhất. Khi traffic ổn định 40 lời gọi mỗi giây, con số này tương đương khoảng 10 giây. Nhưng khi traffic tăng lên 100 lời gọi mỗi giây, 400 lời gọi chỉ bao phủ khoảng 4 giây; khi traffic giảm xuống 10 lời gọi mỗi giây, chúng có thể bao phủ khoảng 40 giây. Đây là khác biệt quan trọng khi chọn kiểu cửa sổ.

## 8. Ảnh hưởng đến bộ nhớ và số lượng Circuit Breaker instance

Kích thước cửa sổ là một phần của chi phí bộ nhớ. Với COUNT_BASED, mỗi instance giữ cấu trúc thống kê cho tối đa N phép đo lời gọi. Khi tăng N từ 100 lên 10.000, lượng cấu trúc dành cho phép đo tăng đáng kể.

Với TIME_BASED, số bucket phụ thuộc vào số giây cấu hình. Ví dụ, cửa sổ 10 giây có 10 bucket thời gian, cửa sổ 60 giây có 60 bucket. Mỗi bucket tổng hợp các lời gọi trong giây đó, vì vậy traffic tăng không làm số bucket tăng theo số request.

Tuy nhiên, không nên chỉ nhìn vào kích thước một cửa sổ. Nếu ứng dụng có 200 Circuit Breaker instance, mỗi instance có một cửa sổ riêng. Tổng chi phí phụ thuộc vào số instance và kích thước cấu trúc của từng instance. Cần tránh tạo instance động theo từng request hoặc theo những giá trị có cardinality rất cao.

Ví dụ, nếu mỗi tenant tạo một Circuit Breaker riêng và hệ thống có hàng chục nghìn tenant, tổng bộ nhớ có thể tăng mạnh ngay cả khi từng cửa sổ đều nhỏ. Nên chọn phạm vi instance theo dependency hoặc nhóm thao tác có đặc tính vận hành tương tự, đồng thời theo dõi số lượng instance thực tế.

Cũng cần phân biệt bộ nhớ của sliding window với bộ nhớ của log, tracing và metric. Log có thể chứa nội dung request nếu ứng dụng ghi lại; tracing có thể lưu span và thuộc tính; metric có thể tăng cardinality theo nhãn. Các thành phần này có chính sách lưu trữ riêng và không được quyết định chỉ bằng `slidingWindowSize`.

## 9. Quan sát cửa sổ và tinh chỉnh trong vận hành

Resilience4j có thể tích hợp với Micrometer và Spring Boot Actuator để xuất metric. Tùy cấu hình ứng dụng, các số liệu này có thể được thu thập bởi Prometheus và hiển thị trên Grafana.

Khi theo dõi một Circuit Breaker, nên quan sát:

- Số lời gọi được ghi nhận và số lời gọi trong cửa sổ hiện tại.
- Số lời gọi thất bại và failure rate.
- Số lời gọi chậm và slow call rate.
- Số lần chuyển trạng thái CLOSED, OPEN và HALF_OPEN.
- Số lời gọi bị từ chối khi Circuit Breaker đang OPEN.
- Tỷ lệ fallback và độ trễ phản hồi của luồng nghiệp vụ.

Khi Circuit Breaker mở quá thường xuyên, hãy kiểm tra lỗi gốc, lưu lượng, timeout và cách phân loại exception trước khi tăng kích thước cửa sổ. Nếu mở mạch quá muộn, cửa sổ có thể quá lớn hoặc ngưỡng chưa phù hợp. Nếu mở mạch do vài lỗi ngẫu nhiên, hãy xem lại minimumNumberOfCalls và độ ổn định của dependency.

Nên thay đổi từng nhóm cấu hình có chủ đích và quan sát tác động trong điều kiện tải đại diện. Không nên tăng `slidingWindowSize` chỉ với mục tiêu làm giảm tỷ lệ lỗi hiển thị: cửa sổ lớn có thể làm các lỗi mới bị pha loãng, khiến Circuit Breaker phát hiện sự cố muộn hơn.

## 10. Các nhầm lẫn thường gặp

- **Cho rằng COUNT_BASED size 100 nghĩa là 100 giây**: thực tế là 100 lời gọi gần nhất, thời gian bao phủ phụ thuộc traffic.
- **Cho rằng TIME_BASED size 10 nghĩa là 10 request**: thực tế là 10 giây gần nhất, mỗi giây có thể chứa rất nhiều lời gọi.
- **Cho rằng sliding window lưu request body**: cửa sổ giữ phép đo và số liệu tổng hợp, không phải nội dung giao dịch đầy đủ.
- **Đồng nhất slidingWindowSize với minimumNumberOfCalls**: một thuộc tính xác định kích thước cửa sổ, thuộc tính còn lại xác định số mẫu tối thiểu để đánh giá tỷ lệ.
- **Bỏ qua số lượng instance**: nhiều cửa sổ nhỏ vẫn có thể cộng lại thành chi phí bộ nhớ lớn.
- **Chỉ nhìn failure rate**: lời gọi thành công nhưng chậm vẫn có thể là dấu hiệu dependency suy giảm; cần theo dõi slow call rate.
- **Tăng cửa sổ mà không xem lại độ nhạy**: cửa sổ lớn hơn có thể làm quyết định ổn định hơn nhưng chậm phản ứng với lỗi mới.

## 11. Quy trình cấu hình thực tế

Khi cấu hình sliding window cho một dependency trong Spring Cloud CircuitBreaker với Resilience4j, có thể thực hiện theo các bước:

1. Đo lưu lượng và độ trễ thực tế của dependency trong giờ bình thường và giờ cao điểm.
2. Chọn COUNT_BASED nếu muốn giữ số lượng lời gọi gần nhất; chọn TIME_BASED nếu muốn giữ một khoảng thời gian gần nhất.
3. Đặt `slidingWindowSize` theo đúng đơn vị của kiểu cửa sổ đã chọn.
4. Đặt `minimumNumberOfCalls` để có đủ mẫu trước khi đánh giá tỷ lệ.
5. Xác định exception nào được ghi nhận, exception nào được bỏ qua.
6. Đặt `failureRateThreshold`, `slowCallDurationThreshold` và `slowCallRateThreshold` theo SLA và hành vi dependency.
7. Theo dõi metric, số lần chuyển trạng thái và fallback trong điều kiện tải thực tế.
8. Tinh chỉnh cửa sổ và ngưỡng dựa trên dữ liệu quan sát được, đồng thời kiểm tra tác động bộ nhớ khi số instance tăng.

Khi hiểu đúng `slidingWindowSize`, nhóm phát triển có thể kiểm soát phạm vi lịch sử mà Circuit Breaker sử dụng, ước lượng chi phí bộ nhớ và chọn được độ nhạy phù hợp với lưu lượng. COUNT_BASED giữ số lời gọi gần nhất; TIME_BASED giữ các bucket thống kê theo giây. Cả hai đều giúp Resilience4j đánh giá lỗi và lời gọi chậm mà không cần lưu toàn bộ dữ liệu request/response.
