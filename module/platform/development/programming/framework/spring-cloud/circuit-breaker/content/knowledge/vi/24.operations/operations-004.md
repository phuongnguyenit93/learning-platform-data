# Giám sát tải phục hồi khi nhiều bộ ngắt mạch cùng HALF_OPEN

## Vì sao nhiều Circuit Breaker cùng HALF_OPEN có thể gây quá tải?

Trong Spring Cloud Circuit Breaker dùng Resilience4j, trạng thái `HALF_OPEN` cho phép một số lời gọi thử nghiệm đi đến dependency sau khi Circuit Breaker đã ở `OPEN` đủ thời gian. Kết quả của các lời gọi này giúp breaker quyết định đóng mạch trở lại hay mở lại. Cơ chế này ngăn ứng dụng tiếp tục gửi toàn bộ lưu lượng đến một dependency chưa phục hồi.

Vấn đề vận hành xuất hiện khi nhiều breaker cùng chuyển sang `HALF_OPEN` trong một khoảng thời gian ngắn. Các breaker có thể thuộc nhiều dependency khác nhau, hoặc là cùng một dependency nhưng nằm trên nhiều replica của ứng dụng. Nếu chúng cùng cho phép probe, dependency vừa phục hồi có thể nhận một đợt tải đột ngột đúng lúc tài nguyên còn yếu. Nó có thể lại timeout, làm các breaker mở trở lại và tạo chu kỳ phục hồi thất bại.

Hiện tượng này thường được gọi là *recovery surge* hoặc *thundering herd*. Nó có thể xảy ra dù mỗi breaker đều có `permittedNumberOfCallsInHalfOpenState` nhỏ, vì giới hạn đó áp dụng cho từng breaker instance trong từng tiến trình, không tự động là giới hạn toàn cụm.

## Hiểu đúng số probe ở HALF_OPEN

Resilience4j không mặc định chạy một health check riêng khi vào `HALF_OPEN`. Những lời gọi được cho phép trong trạng thái này thường là các lời gọi ứng dụng thực tế đi qua Circuit Breaker. `permittedNumberOfCallsInHalfOpenState` xác định số lời gọi được cấp phép để đánh giá khả năng phục hồi. Khi đủ kết quả, breaker dùng các ngưỡng lỗi và lời gọi chậm để quyết định chuyển về `CLOSED` hay quay lại `OPEN`.

Giả sử một dịch vụ chạy sáu replica và mỗi replica có một Circuit Breaker `catalog` độc lập. Nếu mỗi breaker cho phép ba lời gọi trong `HALF_OPEN`, tổng số probe có thể được gửi đến catalog từ ứng dụng này là:

\[
6 \text{ replica} \times 3 \text{ probe/replica} = 18 \text{ probe}
\]

Nếu ba ứng dụng khác cũng gọi catalog với cùng giới hạn, tổng tải thử nghiệm có thể cao hơn nhiều. Ngoài ra, một replica có thể có nhiều breaker ID cùng trỏ đến cùng một cụm backend. Khi tính ngân sách phục hồi, phải cộng tất cả nguồn gọi cùng chia sẻ năng lực dependency.

| Phạm vi | Giới hạn cần hiểu |
| --- | --- |
| Một Circuit Breaker instance | Số lời gọi được phép trong `HALF_OPEN` theo cấu hình của instance đó. |
| Một tiến trình ứng dụng | Tổng probe từ tất cả breaker đang chuyển sang `HALF_OPEN` trong tiến trình. |
| Toàn bộ replica của một ứng dụng | Tổng probe trên tất cả tiến trình; trạng thái breaker thường không tự đồng bộ giữa các replica. |
| Một dependency dùng chung | Tổng probe từ mọi ứng dụng, route và replica cùng gọi dependency đó. |

Không lấy `permittedNumberOfCallsInHalfOpenState` làm giới hạn tải toàn hệ thống. Hãy tính tổng theo số breaker, số replica và các caller khác.

## Vì sao các breaker có thể chuyển trạng thái cùng lúc?

Có một số nguyên nhân thường gặp:

- Nhiều breaker cùng mở trong một đợt dependency mất kết nối hoặc trả 5xx.
- Các breaker dùng cùng `waitDurationInOpenState`, nên thời điểm hết thời gian chờ gần nhau.
- Các replica khởi động hoặc nhận lưu lượng gần như đồng thời, tạo mẫu lỗi tương tự và cùng chuyển sang `OPEN`.
- `automaticTransitionFromOpenToHalfOpenEnabled` được bật, khiến breaker tự chuyển sau khoảng chờ đã cấu hình. Nếu nhiều breaker mở gần cùng thời điểm và dùng thời gian chờ giống nhau, các lần chuyển có thể tập trung.
- Khi không bật tự động chuyển, breaker thường chuyển khi có lời gọi đến sau khi thời gian `OPEN` đã hết. Một đợt traffic mới có thể kích hoạt nhiều breaker gần như cùng lúc.

`HALF_OPEN` không có nghĩa dependency đã khỏe. Đây là giai đoạn thử có giới hạn. Một số probe thành công chưa chắc đủ để backend chịu được lưu lượng bình thường; cần quan sát cả latency, queue và tài nguyên phía dependency trước khi xem phục hồi là ổn định.

## Thiết lập ngân sách probe

Hãy bắt đầu bằng việc xác định tải thử nghiệm tối đa mà dependency có thể nhận trong lúc phục hồi. Ví dụ, nếu dependency chỉ có thể xử lý an toàn 12 request kiểm tra đồng thời từ toàn bộ hệ thống, tổng số lời gọi `HALF_OPEN` từ tất cả caller phải nằm trong ngân sách đó.

Một phép tính sơ bộ:

\[
P_{total} = \sum_{i=1}^{n} (R_i \times B_i \times H_i)
\]

Trong đó:

- \(R_i\) là số replica của ứng dụng thứ \(i\).
- \(B_i\) là số breaker trên mỗi replica đang trỏ đến dependency cần bảo vệ.
- \(H_i\) là số probe được phép trên mỗi breaker trong `HALF_OPEN`.

Đây là mức tối đa lý thuyết nếu các breaker chuyển trạng thái và có đủ request cùng lúc. Tải thực tế phụ thuộc lưu lượng, cách factory tạo breaker và thời điểm các lời gọi được gửi. Nếu nhiều route dùng chung breaker ID, không đếm chúng thành nhiều breaker; nếu route có ID riêng nhưng cùng backend, phải cộng tất cả.

Chọn `permittedNumberOfCallsInHalfOpenState` nhỏ khi dependency cần phục hồi từ từ. Với dependency có khả năng xử lý lớn hơn, có thể tăng số probe sau khi đo được giới hạn thực tế. Không tăng probe chỉ để breaker đóng nhanh hơn; mục tiêu là xác nhận phục hồi mà không gây một đợt tải mới.

## Cấu hình HALF_OPEN cho từng dependency

Ví dụ cấu hình Resilience4j với số probe nhỏ và ngưỡng khác nhau theo dependency:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 25s
        permittedNumberOfCallsInHalfOpenState: 2
        maxWaitDurationInHalfOpenState: 10s

      payment:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 40
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 40s
        permittedNumberOfCallsInHalfOpenState: 1
        maxWaitDurationInHalfOpenState: 8s
```

`permittedNumberOfCallsInHalfOpenState` giới hạn số lời gọi thử được cấp phép. `maxWaitDurationInHalfOpenState` là giới hạn thời gian breaker có thể ở `HALF_OPEN` chờ các lời gọi thử hoàn tất; nếu các probe không kết thúc trong khoảng này, Resilience4j có thể chuyển breaker về `OPEN` theo hành vi của phiên bản. Giá trị `0` có ý nghĩa đặc biệt trong một số cấu hình và thường biểu thị không đặt giới hạn chờ tối đa; hãy xác nhận tài liệu của phiên bản Resilience4j đang dùng trước khi thay đổi.

`waitDurationInOpenState` quyết định thời gian chờ trước khi có thể thử phục hồi. Ví dụ dùng 25 giây cho catalog và 40 giây cho payment để minh họa chính sách riêng theo dependency. Các con số cần dựa trên thời gian phục hồi thực tế, mức độ quan trọng của dependency và khả năng chịu tải. Khác biệt thời gian chờ giữa các dependency giúp tránh dồn toàn bộ probe vào cùng một thời điểm, nhưng không tự phân tán trạng thái giữa các replica có cùng cấu hình.

`automaticTransitionFromOpenToHalfOpenEnabled` có thể được bật nếu muốn breaker tự chuyển trạng thái sau thời gian `OPEN`, kể cả khi không có request mới. Nếu bật, hãy đặc biệt chú ý việc nhiều breaker dùng cùng thời gian chờ. Nếu tắt, lần gọi tiếp theo sau thời gian chờ thường kích hoạt chuyển trạng thái. Cách nào phù hợp phụ thuộc traffic và mục tiêu vận hành; điều quan trọng là đo thời điểm chuyển trạng thái thực tế.

## Phân tán thời điểm probe

Khi nhiều breaker cùng mở, có thể giảm nguy cơ phục hồi đồng loạt bằng các cách sau:

1. **Đặt thời gian mở khác nhau theo dependency:** không cần mọi dependency có cùng `waitDurationInOpenState`. Dùng thời gian dựa trên khả năng phục hồi và mức độ ưu tiên của từng backend.
2. **Dùng jitter khi provider hỗ trợ:** nếu phiên bản Resilience4j cho phép cấu hình hàm thời gian chờ (`waitIntervalFunctionInOpenState`), có thể áp dụng khoảng biến thiên có giới hạn thay vì một thời điểm cố định. Kiểm tra API đúng phiên bản và bảo đảm khoảng chờ không vượt deadline vận hành.
3. **Giới hạn probe theo dependency:** dùng Bulkhead hoặc một cơ chế admission control dùng chung để giới hạn tổng concurrency đến backend, kể cả khi nhiều breaker cùng `HALF_OPEN`.
4. **Giảm số probe trên mỗi breaker:** bắt đầu với một hoặc hai probe đối với dependency nhạy tải, rồi tăng sau khi quan sát.
5. **Điều tiết lưu lượng bình thường khi phục hồi:** không để traffic mới và probe phục hồi cùng dồn vào backend khi nó chưa ổn định.

Jitter cục bộ trên từng tiến trình chỉ làm lệch thời điểm trong phạm vi cấu hình đó. Nếu mọi replica dùng cùng một giá trị cố định và cùng khởi động, chúng vẫn có thể đồng bộ. Khi cần giới hạn toàn cụm, phải dùng cơ chế chia sẻ hoặc phân phối tải ở tầng phù hợp; không giả định Circuit Breaker state trong bộ nhớ tự phối hợp giữa các pod.

## Dùng Bulkhead và RateLimiter để bảo vệ dependency

Circuit Breaker quyết định có cho phép lời gọi theo trạng thái và kết quả trước đó. Bulkhead giới hạn số lời gọi đang hoạt động, còn RateLimiter giới hạn tốc độ cấp phép. Kết hợp chúng giúp kiểm soát probe và traffic bình thường.

Ví dụ Bulkhead cho catalog:

```yaml
resilience4j:
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 8
        maxWaitDuration: 0ms
```

Giới hạn này áp dụng cho lời gọi đi qua Bulkhead trong phạm vi registry/tiến trình đó. Nếu có sáu replica, giới hạn tổng lý thuyết vẫn có thể lên tới 48 lời gọi, chưa tính caller khác. Muốn giới hạn toàn cụm, cần tính tổng hoặc sử dụng admission control ở tầng có phạm vi toàn cụm.

Khi kết hợp Bulkhead với Circuit Breaker, cần xác định thứ tự decorator. Nếu lỗi `BulkheadFullException` bị ghi nhận như lỗi của dependency, failure rate có thể tăng dù backend không nhận request. Theo dõi riêng lỗi từ chối Bulkhead và lỗi Circuit Breaker; cấu hình predicate hoặc thứ tự tích hợp để phản ánh đúng nguyên nhân.

RateLimiter có thể giới hạn tốc độ probe và request phục hồi, nhưng quota của một RateLimiter cục bộ cũng nhân theo số replica. Nếu dependency có quota toàn cục, cần cơ chế giới hạn ở gateway, service mesh hoặc một thành phần chia sẻ quota phù hợp.

## Retry có thể nhân tải probe

Một probe `HALF_OPEN` có thể được bọc thêm Retry. Nếu mỗi probe được thử tối đa ba lần, hai probe được cấp phép có thể tạo tối đa sáu lần thực thi supplier. Nếu có nhiều replica, số request đến dependency còn tăng theo số breaker trên từng replica.

Trong giai đoạn phục hồi, hãy cân nhắc:

- Giảm hoặc tắt retry tự động cho lời gọi probe nếu retry làm tăng tải vượt ngân sách.
- Nếu vẫn retry, chỉ retry lỗi tạm thời, giới hạn số lần và dùng backoff.
- Đặt deadline tổng để retry không giữ probe quá lâu.
- Đảm bảo thao tác ghi có idempotency key trước khi retry.
- Đo số lần thực thi thực tế đến dependency, không chỉ số lần invocation đi vào Circuit Breaker.

Một probe thành công sau nhiều lần retry có thể làm breaker đóng, nhưng backend đã phải xử lý nhiều request hơn số probe được cấu hình. Khi quan sát, cần tách số invocation, số lần retry và số request thực tế đến dependency.

## Timeout và probe bị treo

Nếu probe không hoàn tất, breaker có thể giữ slot `HALF_OPEN` trong thời gian dài. Khi tất cả slot được cấp phép đều bị giữ bởi lời gọi chậm, các lời gọi tiếp theo không thể cung cấp thêm bằng chứng phục hồi. Cấu hình connect timeout, response/read timeout hoặc TimeLimiter phù hợp với dependency.

`maxWaitDurationInHalfOpenState` có thể giới hạn thời gian chờ kết quả của giai đoạn thử theo phiên bản Resilience4j. Nó không thay thế timeout ở HTTP client và không bảo đảm một thao tác phía server đã bị hủy. Nếu client timeout trong khi server vẫn xử lý, cần xem xét idempotency và khả năng request tiếp tục chạy ở backend.

Slow-call threshold cũng quan trọng. Một backend vừa khởi động có thể trả lời thành công nhưng rất chậm do warm-up, tải cache hoặc khởi tạo connection pool. Nếu chỉ nhìn success/failure, breaker có thể đóng quá sớm. `slowCallDurationThreshold` và `slowCallRateThreshold` giúp phản ánh chất lượng phục hồi, nhưng cần chọn theo latency mục tiêu thực tế.

## Theo dõi trạng thái và tải phục hồi

Dashboard vận hành nên kết hợp trạng thái Circuit Breaker với tải thực tế của dependency. Theo dõi tối thiểu:

| Nhóm | Chỉ số | Câu hỏi vận hành |
| --- | --- | --- |
| Trạng thái breaker | Số breaker ở `OPEN`, `HALF_OPEN`, `CLOSED`; số lần state transition. | Có bao nhiêu dependency hoặc replica đang thử phục hồi? |
| Probe | Số lời gọi được cấp phép ở `HALF_OPEN`, số thành công, thất bại và chậm. | Probe có đủ dữ liệu để quyết định đóng hay mở lại không? |
| Từ chối | `not permitted` của Circuit Breaker và `BulkheadFullException`. | Request bị chặn vì breaker mở hay vì hết capacity? |
| Tải dependency | Request rate, concurrency, queue depth, connection pool, CPU, memory. | Backend có chịu được lượng probe và traffic hiện tại không? |
| Latency | p50, p95, p99 của probe và request bình thường. | Backend đã phục hồi tốc độ hay chỉ trả response thành công? |
| Retry | Số invocation, số lần thử và số request thực tế. | Retry đang nhân tải phục hồi đến mức nào? |
| Fallback | Số lần fallback, latency và tỷ lệ fallback thất bại. | Người dùng đang nhận phản hồi dự phòng trong bao lâu? |

Resilience4j Micrometer integration thường cung cấp metrics về trạng thái, số lời gọi theo kết quả, failure rate, slow-call rate và số lời gọi bị từ chối. Tên metric và tag cụ thể phụ thuộc phiên bản cùng registry. Kiểm tra danh sách meter thực tế qua Actuator metrics hoặc hệ thống quan sát của ứng dụng trước khi viết query dashboard.

Event publisher của Resilience4j cũng có thể phát sự kiện state transition như `OPEN` sang `HALF_OPEN`, `HALF_OPEN` sang `CLOSED` hoặc quay lại `OPEN`. Dùng event để ghi log hoặc phát thông báo vận hành. Ghi kèm breaker name, trạng thái trước/sau, thời điểm và instance ứng dụng; không đưa dữ liệu request nhạy cảm vào log.

## Cảnh báo khi có recovery surge

Không chỉ cảnh báo khi một breaker chuyển sang `OPEN`. Hãy tạo cảnh báo cho những mẫu hình sau:

- Số breaker chuyển sang `HALF_OPEN` tăng đột biến trong một cửa sổ ngắn.
- Nhiều breaker cùng `HALF_OPEN` trong khi concurrency hoặc queue của dependency đã gần giới hạn.
- Probe bị từ chối hoặc chậm tăng liên tục.
- Breaker liên tục dao động `HALF_OPEN` → `OPEN` → `HALF_OPEN`.
- Dependency trả thành công nhưng p95/p99 vẫn cao hoặc queue chưa giảm.
- Fallback rate duy trì cao sau khi breaker bắt đầu thử phục hồi.

Khi đặt ngưỡng cảnh báo, xét cả số lượng tuyệt đối và tỷ lệ. Một breaker có thể chuyển trạng thái nhiều lần trên một lưu lượng nhỏ; nhiều breaker cùng chuyển trong vài giây có thể đáng chú ý hơn. Gắn nhãn theo dependency, breaker ID và instance/pod với cardinality được kiểm soát. Không dùng user ID hoặc request ID làm metric tag.

## Runbook khi nhiều breaker cùng HALF_OPEN

Khi dashboard cho thấy nhiều breaker đang thử phục hồi và dependency bắt đầu tăng tải, thực hiện theo trình tự:

1. **Xác định phạm vi:** liệt kê breaker ID, dependency đích, ứng dụng và replica đang ở `HALF_OPEN`.
2. **Tính tổng probe:** cộng số probe được phép trên tất cả breaker và replica; tính thêm retry và các caller khác.
3. **Đối chiếu năng lực backend:** xem request rate, active connections, queue, CPU, memory, thread pool và latency.
4. **Giảm tốc độ phục hồi nếu cần:** giảm số probe cho các breaker liên quan, tăng khoảng chờ hoặc điều tiết traffic qua Bulkhead/RateLimiter ở phạm vi phù hợp.
5. **Kiểm tra timeout và retry:** bảo đảm probe không giữ slot quá lâu và retry không nhân request vượt ngân sách.
6. **Quan sát kết quả:** xác nhận probe hoàn tất, breaker chuyển về `CLOSED` ổn định hoặc quay lại `OPEN` mà backend không bị quá tải kéo dài.
7. **Chỉ tăng tải dần:** sau khi latency và queue ổn định, tăng giới hạn concurrency hoặc khôi phục lưu lượng theo từng bước.

Không ép breaker sang `CLOSED` chỉ để xóa cảnh báo. Nếu backend chưa chịu được tải, đóng mạch đồng loạt có thể đưa toàn bộ traffic trở lại và tái tạo sự cố. Nếu cần thay đổi cấu hình trong lúc sự cố, ghi nhận breaker ID, giá trị cũ/mới, thời điểm và người thực hiện để có thể hoàn nguyên.

## Kiểm thử tình huống nhiều breaker cùng phục hồi

Trong môi trường kiểm thử, tạo nhiều breaker độc lập cùng trỏ đến một dependency giả lập. Cho dependency lỗi để các breaker chuyển `OPEN`, sau đó khôi phục dependency với giới hạn concurrency thấp. Quan sát xem các breaker có chuyển sang `HALF_OPEN` cùng lúc và tổng probe có vượt khả năng xử lý hay không.

Các kịch bản nên kiểm tra:

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Nhiều breaker có cùng `waitDurationInOpenState` | Probe có tập trung trong một khoảng thời gian ngắn không? |
| Thời gian mở được phân tán | Đỉnh request phục hồi có giảm không? |
| Mỗi breaker chỉ cho một probe | Tổng probe trên nhiều replica có còn vượt ngân sách không? |
| Retry được bật cho probe | Số request thực tế có bị nhân lên không? |
| Probe bị treo | Timeout và giới hạn chờ HALF_OPEN có giải phóng giai đoạn thử không? |
| Dependency trả thành công nhưng chậm | Slow-call threshold có ngăn đóng mạch quá sớm không? |
| Bulkhead đầy trong lúc HALF_OPEN | Lỗi từ chối có bị tính nhầm thành lỗi dependency không? |

Kiểm thử phải quan sát cả số lời gọi thực sự đến dependency và state transition của từng breaker. Chỉ kiểm tra một breaker đơn lẻ không đủ để phát hiện recovery surge trên nhiều replica.

## Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Coi `permittedNumberOfCallsInHalfOpenState` là giới hạn toàn cụm | Tổng probe nhân theo số replica và số breaker. | Tính ngân sách ở phạm vi dependency và caller. |
| Dùng cùng thời gian mở cho mọi dependency | Nhiều breaker có thể thử phục hồi cùng lúc. | Chọn thời gian chờ theo failure domain và cân nhắc jitter có kiểm soát. |
| Tăng số probe để breaker đóng nhanh | Dependency vừa phục hồi có thể bị quá tải lại. | Bắt đầu với probe nhỏ, tăng dần sau khi đo. |
| Bỏ qua retry khi tính tải | Số request thực tế lớn hơn số probe được cấp phép. | Đếm cả số lần thử lại và request đến backend. |
| Không cấu hình timeout | Probe chậm giữ slot HALF_OPEN quá lâu. | Đặt timeout ở client và giới hạn thời gian chờ phù hợp. |
| Gộp Bulkhead rejection vào lỗi dependency | Breaker mở vì ứng dụng gọi hết capacity. | Theo dõi và phân loại lỗi từ chối riêng. |
| Chỉ xem trạng thái breaker | Không thấy backend vẫn chậm hoặc queue còn đầy. | Đối chiếu state với latency, concurrency và tài nguyên dependency. |

Giám sát nhiều Circuit Breaker cùng `HALF_OPEN` là bài toán điều phối tải phục hồi ở phạm vi toàn hệ thống. Hãy tính tổng probe trên tất cả replica và caller, phân tán thời điểm thử, giới hạn concurrency, kiểm soát retry và timeout, đồng thời quan sát latency cùng queue của dependency. Khi probe được cấp theo ngân sách và tải được tăng dần, Circuit Breaker có thể xác nhận phục hồi mà không tạo thêm một đợt quá tải mới.
