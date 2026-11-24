# Chi phí thống kê theo kích thước cửa sổ và số instance

Mỗi Circuit Breaker cần lưu trạng thái và thống kê kết quả lời gọi để quyết định khi nào chuyển từ CLOSED sang OPEN hoặc HALF_OPEN. Kích thước sliding window và số lượng Circuit Breaker instance vì thế ảnh hưởng trực tiếp đến bộ nhớ, chi phí cập nhật thống kê, số metrics được xuất và thời gian ứng dụng khởi tạo. Tăng cửa sổ hoặc tạo thêm instance có thể giúp phân tích chi tiết hơn, nhưng cũng làm tăng chi phí vận hành.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, cần chọn kích thước cửa sổ và phạm vi instance phù hợp với lưu lượng, số phụ thuộc và ngân sách tài nguyên. Resilience4j dùng các cấu trúc thống kê dạng cửa sổ trượt để tính failure rate và slow call rate; việc hiểu chi phí theo từng instance giúp tránh cấu hình quá lớn hoặc tạo Circuit Breaker động theo từng request.

## 1. Những thành phần tạo nên chi phí của Circuit Breaker

Một Circuit Breaker instance không chỉ là một cờ trạng thái. Nó còn quản lý cấu hình, trạng thái hiện tại, bộ thống kê của sliding window, bộ phát sự kiện và các thành phần tích hợp metrics nếu ứng dụng bật quan sát.

Các thành phần chính:

| Thành phần | Dữ liệu hoặc công việc | Yếu tố ảnh hưởng chi phí |
| --- | --- | --- |
| State machine | CLOSED, OPEN, HALF_OPEN và thời điểm chuyển trạng thái | Số instance |
| Sliding window | Số lượng lời gọi, số lỗi, số lời gọi chậm và dữ liệu tổng hợp | Kích thước cửa sổ và số instance |
| Event publisher | Phát sự kiện thành công, lỗi, từ chối và chuyển trạng thái | Số instance, số sự kiện và công việc của listener |
| Metrics integration | Meter, tag và dữ liệu quan sát của từng instance | Số instance, số metric family và số tổ hợp nhãn |
| Cấu hình | Ngưỡng, thời gian OPEN, loại cửa sổ và các tham số khác | Số cấu hình/instance và cách tổ chức cấu hình |

Có thể mô tả gần đúng chi phí bộ nhớ của phần thống kê như sau:

$$
M_{window} \propto N \times W
$$

Trong đó:

- (N) là số Circuit Breaker instance đang được tạo.
- (W) là kích thước cửa sổ: số lời gọi đối với COUNT_BASED hoặc số giây đối với TIME_BASED.

Đây là mô hình độ phức tạp để so sánh cấu hình, không phải công thức tính chính xác số byte. Mức sử dụng bộ nhớ thực tế còn phụ thuộc phiên bản Resilience4j, JVM, object layout, metrics, event buffer và các thành phần khác của ứng dụng.

## 2. Resilience4j lưu thống kê theo cửa sổ trượt

Resilience4j không cần giữ toàn bộ object request hoặc response của mọi lời gọi chỉ để tính tỷ lệ. Sliding window dùng các bucket thống kê và phép tổng hợp để lưu thông tin cần thiết cho việc đánh giá.

Với COUNT_BASED, cửa sổ có kích thước theo số lời gọi gần nhất. Khi có kết quả mới, dữ liệu cũ nhất bị loại khỏi cửa sổ và thống kê tổng được cập nhật. Với TIME_BASED, cửa sổ được chia theo các bucket thời gian, thường tương ứng với từng giây trong khoảng quan sát; dữ liệu của bucket hết hạn được loại khỏi tổng hợp.

Hai cách này cho phép cập nhật và đọc thống kê với chi phí gần như hằng số theo mỗi lời gọi trong cấu trúc cửa sổ, trong khi lượng bộ nhớ của cửa sổ tăng theo kích thước cấu hình. Do đó, tăng kích thước cửa sổ làm tăng số bucket cần quản lý nhưng không có nghĩa Resilience4j phải giữ toàn bộ payload của từng request.

Điều này không có nghĩa toàn bộ chi phí của ứng dụng luôn là O(1). HTTP client, serialization, logging, event listener, metrics exporter và các thao tác bên trong lời gọi phụ thuộc có chi phí riêng. Mô tả O(1) ở đây nói về thao tác cập nhật và đọc phép tổng hợp của sliding window theo thiết kế cửa sổ.

## 3. Chi phí của COUNT_BASED

Với COUNT_BASED, `slidingWindowSize` là số lượng kết quả lời gọi gần nhất được giữ trong cửa sổ. Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
~~~

Instance `inventory` theo dõi tối đa 100 kết quả gần nhất. Khi có kết quả thứ 101, kết quả cũ nhất rời khỏi cửa sổ và được thay bằng kết quả mới. Bộ thống kê giữ các số tổng hợp cần thiết như số lời gọi, số lỗi, số lời gọi chậm và thời lượng tổng hợp.

Đặc điểm của COUNT_BASED:

- Bộ nhớ của cửa sổ tăng theo `slidingWindowSize`.
- Khoảng thời gian thực tế mà cửa sổ bao phủ thay đổi theo lưu lượng.
- Khi lưu lượng cao, 100 lời gọi có thể chỉ đại diện cho vài giây.
- Khi lưu lượng thấp, cùng 100 lời gọi có thể trải dài trong nhiều phút hoặc lâu hơn.
- Tăng cửa sổ giúp giảm ảnh hưởng của một vài lỗi ngẫu nhiên nhưng làm dữ liệu cũ tồn tại lâu hơn trong tập mẫu.

COUNT_BASED phù hợp khi muốn đánh giá theo số lượng lời gọi, ví dụ “20 lời gọi gần nhất có bao nhiêu lỗi?”. Nếu lưu lượng biến động mạnh và yêu cầu là đánh giá trong một khoảng thời gian cố định, TIME_BASED có thể phù hợp hơn.

## 4. Chi phí của TIME_BASED

Với TIME_BASED, `slidingWindowSize` biểu thị độ dài cửa sổ tính bằng giây:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 60
        minimumNumberOfCalls: 50
        failureRateThreshold: 50
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
~~~

Instance theo dõi kết quả trong 60 giây gần nhất. Cửa sổ dùng các bucket thời gian để tổng hợp kết quả của từng khoảng. Khi một bucket hết hạn, số liệu của bucket đó được loại khỏi tổng.

Đặc điểm của TIME_BASED:

- Bộ nhớ cửa sổ tăng theo số bucket thời gian, tức theo độ dài cửa sổ tính bằng giây.
- Số lời gọi trong mỗi bucket phụ thuộc lưu lượng; cấu trúc thống kê không cần tạo một bucket mới cho mỗi request.
- Khoảng thời gian quan sát ổn định hơn khi lưu lượng thay đổi.
- Khi lưu lượng rất thấp, có thể chưa đủ số lời gọi để vượt `minimumNumberOfCalls` và đánh giá tỷ lệ.
- Khi lưu lượng tăng đột biến, cửa sổ vẫn bao phủ cùng khoảng thời gian nhưng số kết quả trong đó tăng.

TIME_BASED phù hợp với yêu cầu như “tỷ lệ lỗi trong 60 giây gần nhất”. Nếu cần đánh giá theo số mẫu thay vì thời gian, COUNT_BASED có ý nghĩa trực tiếp hơn.

## 5. Kích thước cửa sổ ảnh hưởng độ nhạy và bộ nhớ

Kích thước cửa sổ là một quyết định cân bằng giữa độ nhạy phát hiện và chi phí thống kê:

| Cửa sổ | Tác động đến phát hiện lỗi | Tác động đến tài nguyên |
| --- | --- | --- |
| Nhỏ | Phản ứng nhanh với thay đổi gần đây nhưng dễ dao động do ít mẫu | Ít bucket hơn, chi phí bộ nhớ cửa sổ thấp hơn |
| Vừa phải | Cân bằng giữa biến động ngắn hạn và xu hướng lỗi | Chi phí tương ứng với số bucket vừa phải |
| Lớn | Tỷ lệ ổn định hơn nhưng lỗi mới có thể bị pha loãng bởi lịch sử cũ | Nhiều bucket hơn cho mỗi instance |

Ví dụ, cửa sổ COUNT_BASED 10 có thể mở mạch nhanh khi 5 trong 10 lời gọi lỗi. Tuy nhiên, một vài request lỗi liên tiếp trong thời điểm lưu lượng thấp có thể làm tỷ lệ thay đổi mạnh. Cửa sổ 200 làm tỷ lệ ổn định hơn, nhưng nếu dịch vụ vừa bắt đầu suy giảm, nhiều kết quả thành công cũ vẫn nằm trong cửa sổ và làm chậm quyết định mở mạch.

Không nên tăng cửa sổ chỉ để giảm dao động mà không kiểm tra tốc độ phát hiện sự cố. Mục tiêu là phát hiện đủ nhanh để bảo vệ ứng dụng, đồng thời không mở mạch do một số ít lỗi ngẫu nhiên.

## 6. Vai trò của minimumNumberOfCalls

`minimumNumberOfCalls` xác định số kết quả tối thiểu cần có trước khi Circuit Breaker tính tỷ lệ lỗi và tỷ lệ lời gọi chậm để quyết định mở mạch. Tham số này không thay đổi kích thước sliding window, nhưng ảnh hưởng thời điểm cửa sổ đủ điều kiện đánh giá.

Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
~~~

Với cấu hình này, dù 3 lời gọi đầu tiên đều thất bại, Circuit Breaker chưa đánh giá tỷ lệ để mở mạch vì chưa có đủ 20 kết quả. Khi đạt tối thiểu 20 kết quả, tỷ lệ lỗi được so sánh với ngưỡng 50%.

Một giá trị `minimumNumberOfCalls` quá thấp làm quyết định dễ bị ảnh hưởng bởi mẫu nhỏ. Giá trị quá cao có thể khiến Circuit Breaker chờ lâu mới phản ứng, đặc biệt với phụ thuộc có lưu lượng thấp. Cần chọn đồng thời với cửa sổ và lưu lượng dự kiến.

## 7. Số lượng instance nhân chi phí thống kê

Mỗi Circuit Breaker instance có state và sliding window riêng. Nếu ứng dụng bảo vệ 8 phụ thuộc, mỗi phụ thuộc có 3 nhóm thao tác, tổng số instance có thể là:

$$
N = 8 \times 3 = 24
$$

Nếu mỗi instance dùng COUNT_BASED window size 100, tổng số vị trí thống kê cần quản lý có quy mô tỷ lệ với:

$$
24 \times 100 = 2.400
$$

Đây là số vị trí/bucket tương đương theo mô hình độ phức tạp, không phải 2.400 request object hay số byte cố định. Nếu tăng số instance lên 240 trong khi giữ nguyên cửa sổ 100, chi phí phần cửa sổ tăng xấp xỉ 10 lần.

Không nên tạo Circuit Breaker theo từng khách hàng, SKU, request ID hoặc transaction ID. Ví dụ sau tạo tên instance có cardinality không giới hạn:

~~~java
// Không nên: mỗi customer có thể tạo một instance riêng.
String name = "inventory-" + customerId;
CircuitBreaker breaker = registry.circuitBreaker(name);
~~~

Thay vào đó, dùng tên ổn định theo phụ thuộc hoặc nhóm thao tác:

~~~java
CircuitBreaker breaker = registry.circuitBreaker("inventory-read");
~~~

Nếu hai thao tác cần ngưỡng và lịch sử lỗi khác nhau, có thể dùng hai tên cố định như `inventory-read` và `inventory-reservation`. Mỗi tên phải tương ứng với một chính sách vận hành có ý nghĩa, không phải một giá trị dữ liệu phát sinh từ request.

## 8. Config dùng chung không làm giảm số instance runtime

Resilience4j cho phép khai báo các cấu hình dùng lại trong `configs`, sau đó để nhiều instance tham chiếu bằng `baseConfig`:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventory-read:
        baseConfig: default
      customer-profile-read:
        baseConfig: default
      catalog-read:
        baseConfig: default
~~~

Việc dùng chung config giúp giảm lặp YAML và dễ đồng bộ tham số. Tuy nhiên, ba khóa trong `instances` vẫn đại diện cho ba Circuit Breaker độc lập. Mỗi instance vẫn có state, sliding window và metrics riêng.

Vì vậy, `baseConfig` giúp đơn giản hóa cấu hình, không phải cách gộp nhiều phụ thuộc vào cùng một sliding window và cũng không làm chi phí runtime của ba instance biến mất. Muốn giảm số instance, cần xem lại phạm vi lời gọi nào thực sự cần state độc lập.

## 9. Metrics cũng tăng theo số instance

Khi bật Micrometer integration, mỗi Circuit Breaker instance có thể tạo các meter để theo dõi số lời gọi, trạng thái, failure rate và slow call rate. Số time series phụ thuộc vào số instance, số meter family, các tag và cách exporter biểu diễn metric.

Có thể mô tả gần đúng:

$$
S \approx N \times M \times L
$$

Trong đó:

- (S) là số time series tiềm năng.
- (N) là số instance.
- (M) là số meter family được xuất cho mỗi instance.
- (L) là số tổ hợp nhãn bổ sung cho mỗi meter.

Đây là mô hình ước lượng, không phải công thức cố định cho mọi phiên bản. Nếu có histogram, mỗi label set có thể tạo thêm nhiều chuỗi bucket cùng count và sum. Vì vậy, số series có thể tăng nhanh hơn số instance.

Không thêm nhãn có cardinality cao như request ID, customer ID, SKU hoặc exception message vào metrics. Hãy giữ ID chi tiết trong log và trace. Tên instance nên là tập giá trị hữu hạn và ổn định.

## 10. Chi phí event listener và logging

Circuit Breaker có thể phát sự kiện khi lời gọi thành công, thất bại, bị từ chối hoặc khi trạng thái thay đổi. Event listener giúp quan sát hệ thống, nhưng phần xử lý listener cũng tiêu thụ CPU và có thể ảnh hưởng độ trễ nếu làm việc nặng ngay trong callback.

Ví dụ listener nên xử lý nhanh:

~~~java
circuitBreaker.getEventPublisher()
        .onStateTransition(event ->
                log.info("Circuit breaker state changed: {}", event))
        .onError(event ->
                log.debug("Circuit breaker call failed: {}", event));
~~~

Tránh thực hiện HTTP call, truy vấn database hoặc thao tác blocking trong listener. Nếu cần gửi sự kiện đến hệ thống khác, hãy đưa công việc sang hàng đợi hoặc executor có giới hạn và có chính sách xử lý khi hàng đợi đầy.

Không nên log toàn bộ event ở mức INFO cho một phụ thuộc có lưu lượng rất lớn nếu không có nhu cầu vận hành cụ thể. Có thể dùng metrics để theo dõi số liệu tổng hợp và chỉ log chi tiết các sự kiện quan trọng như chuyển trạng thái. Việc ghi log mỗi request có thể làm tăng I/O, dung lượng lưu trữ và chi phí xử lý.

## 11. Ví dụ so sánh cấu hình theo số instance

Giả sử ứng dụng có 12 thao tác phụ thuộc ổn định. So sánh hai phương án:

| Phương án | Số instance | Window mỗi instance | Tổng quy mô bucket theo mô hình |
| --- | ---: | ---: | ---: |
| A | 12 | 50 | 600 |
| B | 12 | 200 | 2.400 |
| C | 48 | 50 | 2.400 |
| D | 120 | 200 | 24.000 |

Phương án B có cùng số instance với A nhưng cửa sổ lớn gấp 4 lần. Phương án C có cửa sổ bằng A nhưng số instance gấp 4 lần. Cả B và C có quy mô bucket tương đương theo mô hình (N \times W), nhưng số instance nhiều hơn ở C còn làm tăng số state machine, cấu hình, event publisher và meter.

Phương án D kết hợp nhiều instance với cửa sổ lớn, có chi phí cao hơn rõ rệt. Nếu 120 instance được tạo theo từng khách hàng hoặc tài nguyên, ứng dụng còn phải quản lý vòng đời của chúng và tránh giữ các instance không còn được dùng.

Các con số chỉ dùng để so sánh tương đối. Để biết mức heap thực tế, cần đo trên đúng phiên bản JVM, Resilience4j, Micrometer và cấu hình triển khai.

## 12. Cách chọn kích thước cửa sổ theo lưu lượng

Trước khi chọn window size, hãy xác định:

1. Lưu lượng trung bình và đỉnh của phụ thuộc.
2. Khoảng thời gian cần phát hiện sự cố.
3. Số mẫu tối thiểu đủ tin cậy để tính tỷ lệ.
4. Tần suất lỗi ngẫu nhiên bình thường.
5. Mức độ chấp nhận false positive và thời gian phát hiện chậm.

Ví dụ, với phụ thuộc có 100 lời gọi mỗi giây, COUNT_BASED window size 100 bao phủ xấp xỉ một giây ở mức tải đó. Khi lưu lượng giảm còn 2 lời gọi mỗi giây, cùng cửa sổ có thể bao phủ khoảng 50 giây. TIME_BASED window 30 giây giữ khoảng quan sát theo thời gian ổn định hơn, nhưng có thể có ít mẫu khi lưu lượng thấp.

Đừng chọn window size chỉ dựa trên một con số mặc định. Hãy thử các giá trị nhỏ, vừa và lớn dưới tải đại diện, sau đó quan sát:

- Thời gian từ lúc phụ thuộc bắt đầu lỗi đến lúc mạch OPEN.
- Số lần mạch mở do lỗi ngẫu nhiên.
- Thời gian phục hồi và số lần chuyển qua lại giữa OPEN và HALF_OPEN.
- Heap sử dụng khi số instance tăng.
- Số time series và kích thước dữ liệu scrape metrics.

## 13. Những lỗi thường gặp về hiệu năng

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Window quá lớn cho mọi instance | Tăng bộ nhớ mà không cải thiện tương xứng khả năng phát hiện | Chọn window theo lưu lượng và mục tiêu phát hiện |
| Window quá nhỏ | Tỷ lệ dao động mạnh, dễ mở mạch do ít mẫu | Kết hợp window size với minimumNumberOfCalls |
| Tạo instance theo request hoặc customer | State, window và metrics tăng theo dữ liệu đầu vào | Dùng tên instance cố định theo phụ thuộc/operation |
| Dùng chung config rồi nghĩ state cũng được dùng chung | Mỗi instance vẫn có window riêng | Phân biệt cấu hình tái sử dụng với instance runtime |
| Bật quá nhiều nhãn động | Tăng time series và chi phí lưu trữ | Dùng label hữu hạn, chuyển ID sang log/trace |
| Listener thực hiện I/O blocking | Tăng độ trễ và có thể nghẽn luồng phát sự kiện | Giữ listener ngắn hoặc chuyển việc sang executor giới hạn |
| Log mọi lời gọi ở mức cao | Tăng I/O và dung lượng log | Dùng metrics tổng hợp, log có chọn lọc |
| Không đo heap khi tăng số instance | Phát hiện muộn áp lực bộ nhớ và GC | Benchmark với số instance gần môi trường thật |

## 14. Quy trình đo và tối ưu

Khi tối ưu Circuit Breaker, hãy thực hiện theo trình tự:

1. Liệt kê các phụ thuộc và nhóm thao tác thực sự cần Circuit Breaker riêng.
2. Đếm số instance dự kiến và loại bỏ ID động theo request, khách hàng hoặc tài nguyên.
3. Chọn COUNT_BASED hoặc TIME_BASED theo cách muốn xác định khoảng quan sát.
4. Chọn window size và minimumNumberOfCalls dựa trên lưu lượng cùng thời gian phát hiện mong muốn.
5. Dùng config chung cho các chính sách tương tự nhưng giữ instance riêng khi cần state độc lập.
6. Bật metrics với tập nhãn hữu hạn và đăng ký event listener có xử lý nhẹ.
7. Tạo tải thử nghiệm ở mức bình thường và đỉnh; đo heap, GC, CPU, thời gian phản hồi, thời gian mở mạch và số time series.
8. Tăng hoặc giảm window size và số instance từng bước, so sánh kết quả trước khi chốt cấu hình.
9. Theo dõi sau triển khai để phát hiện số instance hoặc cardinality tăng ngoài dự kiến.

Chi phí thống kê của Resilience4j phụ thuộc chủ yếu vào số instance và kích thước cửa sổ của mỗi instance, cùng với phần chi phí metrics và event đi kèm. Cửa sổ lớn hơn làm thống kê ổn định hơn nhưng tiêu tốn thêm bộ nhớ và có thể làm chậm phát hiện thay đổi; số instance nhiều hơn tạo thêm state, window và metrics. Đặt ID ổn định, chọn window theo lưu lượng và đo dưới tải thực tế giúp Circuit Breaker bảo vệ dịch vụ hiệu quả mà vẫn giữ chi phí vận hành trong giới hạn.
