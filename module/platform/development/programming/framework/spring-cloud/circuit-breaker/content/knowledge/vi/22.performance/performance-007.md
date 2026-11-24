# Điều chỉnh ngưỡng bằng số liệu thay vì sao chép cấu hình mẫu

Các giá trị như `failureRateThreshold: 50`, `slidingWindowSize: 100` hay `waitDurationInOpenState: 10s` thường xuất hiện trong ví dụ CircuitBreaker. Chúng giúp minh họa API, nhưng không phải bộ thông số tối ưu cho mọi dịch vụ. Một dependency đọc cache trong 30 ms, một API tìm kiếm mất 800 ms và một cổng thanh toán có thời gian xử lý vài giây có đặc tính tải, độ trễ và mức độ rủi ro khác nhau.

Với Spring Cloud Circuit Breaker dùng Resilience4j, hãy điều chỉnh `CircuitBreakerConfig` từ số liệu đo được của đúng dependency và đúng loại thao tác. Mục tiêu là phát hiện suy giảm đủ sớm để ngăn lỗi dây chuyền, đồng thời tránh mở breaker vì một vài request bất thường hoặc vì ngưỡng không phù hợp với latency bình thường.

## Bắt đầu từ SLO và đường cơ sở

Trước khi thay đổi cấu hình, xác định hành vi bình thường của dependency trong điều kiện tải đại diện. Thu thập dữ liệu riêng cho từng failure domain, tối thiểu gồm:

- **Thông lượng:** request mỗi giây, tổng số lời gọi trong mỗi khoảng thời gian và mức burst.
- **Độ trễ:** p50, p90, p95, p99 và độ trễ tối đa có ý nghĩa; không chỉ nhìn giá trị trung bình.
- **Lỗi:** timeout, lỗi kết nối, lỗi máy chủ, lỗi giao thức và lỗi nghiệp vụ được phân loại riêng.
- **Concurrency:** số lời gọi đang chạy, hàng đợi, giới hạn connection pool và số lần bị từ chối bởi Bulkhead.
- **Thời gian phục hồi:** mất bao lâu để dependency trở lại độ trễ và tỷ lệ lỗi bình thường sau một sự cố.
- **Ngân sách thời gian:** deadline của request đầu cuối, timeout của HTTP client và thời gian caller có thể chờ.

Đường cơ sở nên bao gồm giờ cao điểm, tải thấp, burst và các kiểu request có độ phức tạp khác nhau. Một p95 tổng hợp của toàn bộ API có thể che giấu endpoint chậm; nếu các thao tác có đặc tính rất khác nhau, hãy tách chúng thành các breaker hoặc nhóm đo lường riêng.

SLO của caller giúp chuyển số liệu thành quyết định. Ví dụ, nếu request đầu cuối phải hoàn tất trong 1 giây và các bước khác đã tiêu thụ 250 ms, dependency chỉ còn khoảng 750 ms trong ngân sách. Ngưỡng lời gọi chậm cần phản ánh phần ngân sách này và độ trễ bình thường của dependency, thay vì chọn một con số tròn từ ví dụ trên mạng.

## Phân biệt hai tỷ lệ mà breaker đánh giá

Resilience4j đánh giá failure rate và slow call rate độc lập. Sau khi có đủ số lời gọi tối thiểu, breaker chuyển sang `OPEN` nếu **một trong hai tỷ lệ đạt hoặc vượt ngưỡng** tương ứng.

\[
\text{Failure rate} = \frac{\text{Số lời gọi được ghi nhận là lỗi}}{\text{Tổng số lời gọi được ghi nhận}} \times 100\%
\]

\[
\text{Slow call rate} = \frac{\text{Số lời gọi vượt slowCallDurationThreshold}}{\text{Tổng số lời gọi được ghi nhận}} \times 100\%
\]

Một lời gọi có thể vừa lỗi vừa chậm. Khi đó, tổng số lời gọi chỉ tăng một, nhưng nó góp phần vào cả tử số failure rate và tử số slow call rate. Không cộng hai tỷ lệ để tạo một tỷ lệ lỗi tổng hợp.

Ví dụ, cửa sổ có 200 lời gọi được ghi nhận. Có 34 lời gọi lỗi, 58 lời gọi chậm, trong đó 20 lời gọi vừa lỗi vừa chậm:

| Chỉ số | Số lượng | Tỷ lệ |
|---|---:|---:|
| Tổng lời gọi | 200 | 100% |
| Lời gọi lỗi | 34 | 17% |
| Lời gọi chậm | 58 | 29% |
| Vừa lỗi vừa chậm | 20 | 10% |
| Thuộc ít nhất một nhóm lỗi/chậm | 72 | 36% |

Nếu `failureRateThreshold` là 20% và `slowCallRateThreshold` là 30%, breaker chưa mở theo cửa sổ này. Nếu ngưỡng slow call là 25%, breaker mở vì 29% đã đạt ngưỡng, dù failure rate chỉ là 17%. Quyết định này cho thấy dịch vụ có thể vẫn trả response thành công nhưng chậm tới mức làm ảnh hưởng caller.

Chỉ các exception được phân loại là lỗi mới góp phần vào failure rate. Exception bị `ignoreExceptions` hoặc predicate bỏ qua không được tính như một lỗi thông thường. Vì vậy, trước khi điều chỉnh `failureRateThreshold`, hãy xác minh `recordExceptions`, `ignoreExceptions`, `recordExceptionPredicate` và cách HTTP client chuyển lỗi thành exception. Nếu phân loại sai, thay ngưỡng sẽ chỉ che giấu vấn đề.

## Chọn slowCallDurationThreshold từ phân phối latency

`slowCallDurationThreshold` là mốc thời gian mà một lời gọi vượt qua sẽ được ghi nhận là chậm. Không nên đặt nó bằng latency trung bình: trung bình thường thấp hơn nhiều so với các request ở đuôi phân phối.

Một cách bắt đầu:

1. Đo p50, p95 và p99 của dependency khi tải bình thường và khi tải cao nhưng vẫn nằm trong SLO.
2. Xác định latency mà tại đó request bắt đầu tiêu thụ quá nhiều ngân sách thời gian của caller.
3. Đặt `slowCallDurationThreshold` cao hơn vùng latency bình thường có thể chấp nhận, nhưng thấp hơn mức mà caller thường xuyên vi phạm deadline.
4. Kiểm tra lại với các loại request có độ phức tạp khác nhau và với timeout của client.

Ví dụ, p50 là 90 ms, p95 là 260 ms, p99 là 430 ms; caller có deadline 900 ms và các bước khác tiêu thụ khoảng 250 ms. Một ngưỡng ban đầu khoảng 500 ms có thể là giả thuyết để thử nghiệm. Nếu đặt 200 ms, nhiều request ở vùng p95 bình thường có thể bị tính là chậm. Nếu đặt 850 ms, phần lớn request đã vượt ngân sách caller trước khi được đánh dấu chậm.

Đây chỉ là cách chọn điểm bắt đầu, không phải công thức cố định. Hãy so sánh số lời gọi bị đánh dấu chậm với SLO và tỷ lệ request thực sự bị timeout. Khi client timeout ở 700 ms nhưng `slowCallDurationThreshold` là 1 giây, request timeout có thể kết thúc trước khi vượt ngưỡng slow call. Nếu muốn timeout cũng phản ánh suy giảm latency, đặt ngưỡng chậm phù hợp với timeout và ngân sách caller.

`slowCallDurationThreshold` không thay thế timeout. Nó chỉ phân loại kết quả để breaker tính slow call rate. Hãy cấu hình connect/read/response timeout ở HTTP client hoặc `TimeLimiter` cho thời gian chờ tối đa; hai lớp có mục đích khác nhau.

## Chọn failureRateThreshold từ mức lỗi chấp nhận được

`failureRateThreshold` xác định tỷ lệ lỗi tối đa mà breaker cho phép trong cửa sổ trước khi mở. Ngưỡng thấp làm breaker phản ứng sớm nhưng nhạy với các lỗi rải rác; ngưỡng cao chịu được nhiều lỗi hơn nhưng có thể tiếp tục gửi tải tới dependency đang suy giảm.

Để chọn ngưỡng, xem xét:

- Tỷ lệ lỗi nền của dependency trong điều kiện bình thường.
- Mức lỗi mà caller có thể chịu trước khi SLO bị vi phạm.
- Mức độ nghiêm trọng của lỗi và khả năng fallback cung cấp kết quả thay thế.
- Tốc độ dependency suy giảm và lượng tải tăng thêm do retry.
- Số mẫu có trong cửa sổ để phân biệt dao động ngẫu nhiên với sự cố có hệ thống.

Ví dụ, dependency thường có failure rate dưới 0,5% và khi gặp sự cố tăng lên 20–40%. Một ngưỡng 10% có thể phát hiện sớm; nhưng cần thử với lỗi ngẫu nhiên trong giờ cao điểm để biết có mở nhầm không. Nếu lỗi nền đã là 3% do một loại exception nghiệp vụ bị phân loại sai, ngưỡng 10% sẽ mở breaker thường xuyên cho đến khi sửa classification.

Không dùng `failureRateThreshold` để thay thế chính sách nghiệp vụ. Lỗi “sản phẩm không tồn tại” hoặc validation không nên tự động được ghi nhận như lỗi dependency nếu caller nhận đó là kết quả bình thường. Hãy phân loại exception trước, sau đó mới hiệu chỉnh tỷ lệ.

## Chọn COUNT_BASED hay TIME_BASED

Kiểu cửa sổ quyết định cách breaker gom kết quả gần đây:

| Kiểu | Ý nghĩa | Phù hợp khi |
|---|---|---|
| `COUNT_BASED` | Giữ kết quả của tối đa N lời gọi gần nhất | Lưu lượng tương đối ổn định hoặc muốn đánh giá theo số mẫu |
| `TIME_BASED` | Tổng hợp kết quả trong một khoảng thời gian chia thành các bucket | Lưu lượng biến động và muốn cửa sổ phản ánh một khoảng thời gian thực |

Với `COUNT_BASED`, `slidingWindowSize: 100` nghĩa là đánh giá tối đa 100 lời gọi gần nhất. Nếu dependency nhận 1.000 request/giây, cửa sổ có thể thay đổi rất nhanh; nếu chỉ nhận 2 request/phút, cần lâu hơn để thay thế các mẫu cũ.

Với `TIME_BASED`, `slidingWindowSize: 60` tương ứng cửa sổ 60 giây. Các bucket thời gian được tổng hợp và bucket cũ bị loại khi cửa sổ trượt. Kiểu này hữu ích khi muốn đánh giá tỷ lệ lỗi trong khoảng thời gian cố định dù lưu lượng thay đổi.

`minimumNumberOfCalls` là số lời gọi tối thiểu cần ghi nhận trước khi tính tỷ lệ. Nếu đặt quá thấp, một vài lỗi đầu tiên có thể làm breaker mở. Nếu đặt quá cao so với lưu lượng thực tế, breaker có thể không bao giờ có đủ mẫu để đánh giá. Với `COUNT_BASED`, chọn giá trị phù hợp với kích thước cửa sổ; với `TIME_BASED`, chọn giá trị mà lưu lượng bình thường có thể đạt được trong khoảng cửa sổ.

Ví dụ: một endpoint nhận trung bình 20 request/giây. Cửa sổ 100 lời gọi chỉ đại diện khoảng 5 giây. Nếu muốn quyết định ổn định hơn qua 30 giây, có thể thử `TIME_BASED` với cửa sổ 30 giây và đặt `minimumNumberOfCalls` dựa trên số request dự kiến trong khoảng đó. Ngược lại, endpoint chỉ nhận 1 request/giây không nên đặt minimum 100 trong cửa sổ 30 giây vì điều kiện mẫu sẽ không đạt trong phần lớn thời gian.

## Chọn waitDurationInOpenState và probe HALF_OPEN

`waitDurationInOpenState` là thời gian breaker giữ trạng thái `OPEN` trước khi cho phép kiểm tra phục hồi. Thời lượng quá ngắn có thể tạo chu kỳ mở/đóng liên tục khi dependency chưa ổn định. Thời lượng quá dài làm ứng dụng tiếp tục fallback dù dependency đã phục hồi.

Hãy dựa vào:

- Thời gian dependency thường cần để phục hồi sau lỗi (restart, autoscaling, failover hoặc khôi phục connection pool).
- Mức tải mà dependency có thể tiếp nhận khi vừa hoạt động trở lại.
- Chi phí của fallback và mức độ chấp nhận được khi tiếp tục từ chối lời gọi.
- Cách vận hành của dependency: phục hồi nhanh trong vài giây hay cần thời gian dài để warm cache và ổn định.

Trong `HALF_OPEN`, `permittedNumberOfCallsInHalfOpenState` xác định số probe được phép. Probe quá nhiều có thể làm dependency vừa phục hồi bị dồn tải; probe quá ít có thể khiến kết luận bị chi phối bởi một request bất thường. Chọn số probe theo năng lực tiếp nhận an toàn và số lượng mẫu cần để đánh giá.

`maxWaitDurationInHalfOpenState` có thể giới hạn thời gian breaker ở `HALF_OPEN` khi các probe không hoàn tất. Giá trị này cần tương thích với timeout của từng lời gọi; nếu probe có thể treo lâu hơn giới hạn HALF_OPEN, cần điều chỉnh timeout ở client hoặc TimeLimiter để kết quả được trả về trong thời gian dự kiến.

## Ví dụ cấu hình từ một bộ số liệu giả định

Giả sử một API catalog có các số đo trong tải đại diện:

| Chỉ số | Số đo giả định |
|---|---:|
| Thông lượng giờ cao điểm | 200 request/giây |
| p50 / p95 / p99 | 90 / 260 / 430 ms |
| Failure rate nền | 0,5% |
| Slow call rate khi bình thường với mốc 500 ms | 1,2% |
| Deadline caller | 900 ms |
| Thời gian phục hồi thường gặp | 10–15 giây |

Một cấu hình thử nghiệm ban đầu có thể là:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 100
        failureRateThreshold: 15
        slowCallRateThreshold: 25
        slowCallDurationThreshold: 500ms
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 5
        maxWaitDurationInHalfOpenState: 5s
```

Đây là giả thuyết cấu hình để thử nghiệm với số liệu giả định, không phải khuyến nghị mặc định cho mọi catalog. Cửa sổ 30 giây ở 200 request/giây thường có nhiều hơn 100 mẫu; `minimumNumberOfCalls: 100` tránh đánh giá quá sớm khi mới có vài request. Ngưỡng lỗi 15% và slow call 25% cao hơn đáng kể so với mức nền giả định, nhưng đủ thấp để phát hiện sự suy giảm rõ rệt. `waitDurationInOpenState` gần với thời gian phục hồi đã đo. Năm probe giới hạn tải kiểm tra ban đầu.

Trong triển khai thực tế, kiểm tra `minimumNumberOfCalls` với lưu lượng thấp nhất, không chỉ giờ cao điểm. Nếu có giờ đêm chỉ vài request mỗi giây, điều kiện 100 mẫu trong 30 giây có thể không đạt; khi đó cần chọn cửa sổ dài hơn, minimum thấp hơn hoặc một chính sách riêng cho instance ít lưu lượng.

## Quy trình điều chỉnh bằng thử nghiệm

Không thay nhiều thông số cùng lúc rồi kết luận từ một lần chạy. Dùng quy trình lặp có thể so sánh:

1. **Ghi baseline:** lưu latency percentile, throughput, lỗi, concurrency, timeout và tỷ lệ fallback khi breaker đang dùng cấu hình hiện tại.
2. **Đặt giả thuyết:** ví dụ “ngưỡng slow call 500 ms sẽ phát hiện phần lớn request vượt ngân sách nhưng không đánh dấu p99 bình thường là chậm”.
3. **Thay đổi có kiểm soát:** chỉ thay một nhóm thông số liên quan, ghi lại cấu hình, phiên bản và tải thử nghiệm.
4. **Tạo các tình huống:** tải bình thường, burst, lỗi rải rác, lỗi liên tục, độ trễ tăng dần, timeout và phục hồi.
5. **Đo kết quả:** thời gian phát hiện, số lần mở nhầm, số request bị từ chối, tail latency, số lần fallback, tải còn lại trên dependency và thời gian phục hồi.
6. **So sánh với SLO:** xác định caller có được bảo vệ tốt hơn không và dependency có cơ hội phục hồi không.
7. **Triển khai canary:** áp dụng cho một phần traffic hoặc một replica trước, theo dõi rồi mới mở rộng.
8. **Lưu quyết định:** ghi lý do chọn threshold, dữ liệu hỗ trợ và điều kiện cần xem xét lại.

Nên thử ít nhất các kịch bản sau:

| Kịch bản | Điều cần quan sát |
|---|---|
| Latency bình thường có một số outlier | Breaker không mở chỉ vì vài request chậm |
| Failure rate tăng đột ngột | Breaker mở trong khoảng thời gian phù hợp với SLO |
| Chỉ latency tăng, response vẫn thành công | Slow call rate kích hoạt đúng khi cần |
| Lỗi nghiệp vụ bị ignore | Không làm tăng failure rate ngoài ý muốn |
| Burst traffic | Cửa sổ và minimum calls không khiến quyết định quá nhạy hoặc quá chậm |
| Dependency phục hồi rồi lại lỗi | HALF_OPEN không tạo tải probe quá lớn và không đóng/mở liên tục |
| Lưu lượng thấp | Breaker có đủ mẫu trong khoảng thời gian chấp nhận được |

## Theo dõi sau khi triển khai

Metric cần quan sát không chỉ là trạng thái hiện tại. Theo dõi cùng nhau:

- `state` của từng breaker và số lần chuyển trạng thái.
- `failureRate` và `slowCallRate` theo cửa sổ.
- Số lời gọi thành công, lỗi, chậm và bị từ chối (`not permitted`).
- Số lần fallback và kết quả fallback.
- Latency p95/p99 của dependency và của request đầu cuối.
- Số lần timeout ở HTTP client/TimeLimiter và số lời gọi đang chạy.

Resilience4j có thể xuất metric qua Micrometer khi có dependency và Actuator phù hợp. Bảo đảm tên instance có cardinality thấp; không tạo breaker ID từ user ID, request ID hoặc URL có tham số tùy ý. Theo dõi event chuyển trạng thái để biết lúc nào breaker mở và đóng, còn metric giúp giải thích vì sao tỷ lệ thay đổi.

Nếu breaker mở liên tục nhưng dependency không có dấu hiệu suy giảm, kiểm tra classification, `minimumNumberOfCalls`, latency nền và ngưỡng. Nếu breaker không mở dù caller timeout hàng loạt, kiểm tra exception có được ghi nhận không, cửa sổ có đủ mẫu không và threshold có quá cao không. Nếu breaker liên tục chuyển `OPEN`/`HALF_OPEN`, xem lại thời gian phục hồi, số probe, timeout và tải khi dependency vừa hoạt động lại.

## Các sai lầm khi tinh chỉnh

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Sao chép threshold từ ví dụ | Ngưỡng không phản ánh latency và lỗi nền của dependency | Đo baseline và SLO trước khi chọn |
| Dùng latency trung bình làm slow threshold | Bỏ qua tail latency hoặc đánh dấu quá nhiều request bình thường | Dùng percentile và ngân sách thời gian |
| Đặt `minimumNumberOfCalls` quá thấp | Một vài lỗi ngẫu nhiên có thể mở breaker | Chọn số mẫu đủ đại diện |
| Đặt minimum cao hơn lưu lượng cửa sổ có thể đạt | Breaker ít khi đánh giá tỷ lệ | Tính theo throughput và kiểu cửa sổ |
| Dùng cùng một cấu hình cho mọi dependency | Dependency nhanh/chậm và mức rủi ro khác nhau bị đánh giá sai | Cấu hình theo failure domain |
| Nhầm slow threshold với timeout | Request có thể chờ quá lâu dù breaker không phân loại chậm | Cấu hình timeout riêng ở client/TimeLimiter |
| Chỉ kiểm tra giờ cao điểm | Cấu hình không phản ứng đúng ở tải thấp hoặc burst | Thử nhiều profile tải |
| Tăng threshold để tránh mở breaker | Có thể che giấu sự cố và kéo dài lỗi dây chuyền | Kiểm tra classification, mẫu và fallback trước |

## Nguyên tắc lựa chọn

Hãy để số liệu quyết định ngưỡng. `failureRateThreshold` phản ánh mức lỗi có thể chấp nhận; `slowCallDurationThreshold` phản ánh ngân sách latency của caller; `slowCallRateThreshold` phản ánh tỷ lệ request chậm có thể chịu; cửa sổ và `minimumNumberOfCalls` xác định độ ổn định của mẫu; `waitDurationInOpenState` và probe HALF_OPEN phản ánh thời gian cũng như năng lực phục hồi của dependency. Sau mỗi thay đổi, xác minh bằng tải đại diện, lỗi có kiểm soát và metric trong môi trường canary. Cấu hình tốt là cấu hình có bằng chứng phù hợp với failure domain cụ thể và được xem xét lại khi traffic hoặc SLO thay đổi.
