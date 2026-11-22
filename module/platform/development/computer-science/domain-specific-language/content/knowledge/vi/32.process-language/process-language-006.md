# Retry và bù trừ

## 1. Retry và bù trừ trong DSL quy trình

Một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) cho quy trình thường mô tả các bước công việc, điều kiện chuyển trạng thái, lời gọi dịch vụ, thao tác dữ liệu và quan hệ phụ thuộc giữa các bước. Khi quy trình chạy qua nhiều hệ thống, một bước có thể thất bại do mạng gián đoạn, dịch vụ quá tải, timeout, dữ liệu không hợp lệ hoặc lỗi nghiệp vụ. Một số lỗi chỉ tồn tại tạm thời và có thể thành công nếu thử lại; một số thao tác đã hoàn tất nhưng quy trình về sau thất bại, khiến hệ thống cần thực hiện hành động bù trừ.

**Retry (thử lại)** là cơ chế thực hiện lại một thao tác hoặc bước quy trình sau khi thất bại, theo chính sách được định nghĩa. Retry hữu ích với lỗi tạm thời như kết nối bị reset, rate limit hoặc dịch vụ chưa sẵn sàng. Nó cần giới hạn số lần, thời gian chờ và tổng thời gian để tránh tạo tải lớn hơn hoặc lặp vô hạn.

**Compensation (bù trừ)** là hành động nghiệp vụ được thực hiện để đưa hệ thống về một trạng thái chấp nhận được sau khi một phần quy trình đã tạo ra thay đổi mà không thể rollback nguyên tử. Bù trừ thường áp dụng cho quy trình phân tán gồm nhiều dịch vụ hoặc tài nguyên độc lập.

Ví dụ quy trình đặt chuyến đi:

~~~text
reserve_flight
      |
      v
reserve_hotel
      |
      v
charge_payment
      |
      v
send_confirmation
~~~

Nếu reserve_hotel gặp lỗi mạng tạm thời, quy trình có thể retry. Nếu reserve_hotel thành công nhưng charge_payment thất bại vĩnh viễn, hệ thống có thể hủy phòng khách sạn và giải phóng chỗ máy bay. Các thao tác hủy đó là compensation.

Retry và compensation giải quyết hai tình huống khác nhau:

- Retry cố gắng hoàn thành bước hiện tại sau một lỗi có thể phục hồi.
- Compensation xử lý hậu quả của những bước đã thành công khi toàn bộ quy trình không thể tiếp tục theo kế hoạch.

Một DSL quy trình cần biểu diễn được cả hai cơ chế cùng với timeout, trạng thái, idempotency, giới hạn tài nguyên, audit và xử lý lỗi. Nếu chỉ có cú pháp retry hoặc compensate mà không định nghĩa semantics, hệ thống có thể thực hiện thao tác trùng lặp hoặc bù trừ sai thứ tự.

## 2. Phân loại lỗi trước khi retry

Không phải mọi lỗi đều nên được retry. Quyết định retry phải dựa trên loại lỗi và khả năng thao tác có thể thành công ở lần tiếp theo.

### 2.1. Lỗi tạm thời

Lỗi tạm thời (transient error) có thể biến mất sau một khoảng thời gian:

- Connection reset hoặc lỗi DNS tạm thời.
- HTTP 429 do rate limit.
- HTTP 503 do dịch vụ đang quá tải hoặc bảo trì.
- Database deadlock hoặc transaction serialization conflict.
- Resource tạm thời chưa sẵn sàng.
- Lỗi leader election hoặc failover trong hệ thống phân tán.

Những lỗi này thường có thể retry với backoff và jitter, nhưng cần tuân theo tín hiệu từ hệ thống đích.

### 2.2. Lỗi vĩnh viễn

Lỗi vĩnh viễn (permanent error) thường không được khắc phục bằng cách lặp lại cùng một request:

- Dữ liệu đầu vào sai schema.
- Thiếu trường bắt buộc.
- Tài khoản không tồn tại.
- Người gọi không có quyền.
- Thao tác không được hỗ trợ.
- Trạng thái nghiệp vụ không cho phép chuyển tiếp.
- Resource ID không hợp lệ.

Retry các lỗi này chỉ tiêu tốn tài nguyên và có thể làm tăng tải. Quy trình nên chuyển sang nhánh xử lý lỗi hoặc yêu cầu sửa dữ liệu.

### 2.3. Lỗi không xác định

Một số lỗi khiến caller không biết thao tác đã thành công hay chưa. Ví dụ client gửi lệnh tạo đơn hàng, server ghi thành công nhưng phản hồi bị mất. Caller thấy timeout nhưng server có thể đã hoàn tất thao tác.

Đây là tình huống nguy hiểm vì retry có thể tạo đơn hàng thứ hai. Cần idempotency key, truy vấn trạng thái hoặc deduplication để xác định kết quả.

### 2.4. Phân loại theo mã lỗi

Một DSL có thể cho phép khai báo nhóm lỗi:

~~~text
retry when error.kind in [NETWORK, RATE_LIMIT, TEMPORARY_UNAVAILABLE]
fail when error.kind in [VALIDATION, PERMISSION, NOT_FOUND]
~~~

Đây là cú pháp minh họa. Trong thực tế, nên dùng error type hoặc mã lỗi có cấu trúc thay vì so khớp chuỗi message vì message có thể thay đổi hoặc được dịch.

### 2.5. Error taxonomy

Một taxonomy ổn định có thể phân biệt:

| Nhóm lỗi | Ví dụ | Hành vi thường dùng |
|---|---|---|
| Transient | Network reset, 503 | Retry có giới hạn |
| Throttling | 429, quota exceeded | Tôn trọng Retry-After, backoff |
| Conflict | Optimistic lock conflict | Retry transaction nếu an toàn |
| Validation | Sai dữ liệu | Không retry; trả lỗi |
| Authorization | Access denied | Không retry trừ khi quyền được cập nhật có chủ đích |
| Not found | Resource không tồn tại | Thường không retry; có thể retry nếu eventual consistency được kỳ vọng |
| Unknown outcome | Timeout sau khi gửi request | Tra cứu trạng thái hoặc retry idempotent |
| Business rejection | Hạn mức không đủ | Đi theo nhánh nghiệp vụ |

Một lỗi not found có thể tạm thời trong hệ thống eventual consistency, vì vậy classification cần dựa trên hợp đồng dịch vụ và ngữ cảnh, không chỉ tên exception.

## 3. Retry policy

Retry policy xác định khi nào thử lại, thử bao nhiêu lần, chờ bao lâu và khi nào dừng.

### 3.1. Các tham số cơ bản

- **maxAttempts:** tổng số lần thực hiện, thường tính cả lần đầu.
- **initialDelay:** thời gian chờ trước lần retry đầu tiên.
- **multiplier:** hệ số tăng thời gian chờ.
- **maxDelay:** giới hạn thời gian chờ mỗi lần.
- **jitter:** biến thiên ngẫu nhiên để tránh nhiều client retry cùng lúc.
- **retryOn:** nhóm lỗi được phép retry.
- **retryBudget:** giới hạn tổng thời gian hoặc số lần retry.
- **timeout:** giới hạn thời gian cho mỗi lần thực hiện.
- **deadline:** thời điểm muộn nhất toàn bộ bước hoặc workflow được phép tiếp tục.

### 3.2. Ví dụ policy

~~~text
retry_policy "network-retry" {
    max_attempts = 5
    initial_delay = 200ms
    multiplier = 2
    max_delay = 5s
    jitter = 0.2
    retry_on = [NETWORK, RATE_LIMIT, TEMPORARY_UNAVAILABLE]
}
~~~

Nếu max_attempts = 5 được định nghĩa là tổng số lần thực hiện, sẽ có một lần đầu và tối đa bốn lần retry. DSL phải ghi rõ quy ước này vì một số thư viện lại hiểu max retries là số lần thử thêm sau lần đầu.

### 3.3. Retry không giới hạn

Retry vô hạn có thể giữ worker, connection và state trong thời gian không xác định. Trong workflow dài hạn, có thể có wait state bền vững thay vì giữ thread, nhưng vẫn cần deadline, cancellation hoặc cơ chế vận hành để quyết định khi nào kết thúc.

### 3.4. Retry theo từng bước

Mỗi task có thể có policy riêng. Một bước đọc dữ liệu có thể retry nhiều lần với thời gian ngắn; một bước thanh toán cần ít lần hơn và yêu cầu idempotency chặt chẽ.

### 3.5. Kế thừa policy

Workflow có thể định nghĩa policy mặc định và override ở task. Quy tắc ưu tiên phải rõ:

1. Policy riêng của task.
2. Policy của nhóm hoặc scope.
3. Policy mặc định của workflow.

Không nên âm thầm hợp nhất hai policy nếu kết quả không thể dự đoán. Compiler có thể cảnh báo khi override làm nới lỏng giới hạn bảo mật hoặc ngân sách.

## 4. Backoff và jitter

Nếu nhiều client retry ngay lập tức sau khi một dịch vụ gặp sự cố, chúng có thể tạo ra một đợt tải mới đúng lúc dịch vụ đang yếu. Backoff và jitter giúp phân tán các lần retry.

### 4.1. Fixed delay

Mỗi lần retry chờ cùng một khoảng:

~~~text
attempt 1 -> fail
wait 1s
attempt 2 -> fail
wait 1s
attempt 3
~~~

Fixed delay dễ hiểu nhưng có thể khiến nhiều client đồng bộ retry cùng thời điểm.

### 4.2. Exponential backoff

Thời gian chờ tăng theo cấp số nhân:

\[
delay_n = \min(maxDelay,\ initialDelay \times multiplier^{n-1})
\]

Ví dụ initialDelay 200 ms và multiplier 2 tạo chuỗi 200 ms, 400 ms, 800 ms, 1.600 ms trước khi áp dụng maxDelay.

### 4.3. Jitter

Jitter thêm biến thiên vào thời gian chờ. Một dạng full jitter chọn ngẫu nhiên trong khoảng từ 0 đến giới hạn backoff:

\[
delay_n = random(0,\ exponentialCap_n)
\]

Một dạng khác nhân thời gian chờ với hệ số ngẫu nhiên quanh 1. Cần định nghĩa rõ thuật toán và seed nếu muốn tái lập simulation.

### 4.4. Retry-After

Một số dịch vụ trả header hoặc metadata Retry-After. Client nên tôn trọng thời gian đó theo hợp đồng dịch vụ, đồng thời áp dụng deadline và giới hạn nội bộ. Không nên retry sớm hơn thời điểm server yêu cầu chỉ vì policy cục bộ có delay nhỏ hơn.

### 4.5. Backoff không thay thế rate limiting

Backoff điều chỉnh thời gian giữa các lần thử của một request. Rate limiter kiểm soát tổng tốc độ request. Một hệ thống tải cao thường cần cả hai.

## 5. Timeout, deadline và retry budget

Retry policy không thể chỉ dựa vào số lần. Một thao tác có thể mất lâu hơn dự kiến hoặc nhiều lần retry cộng lại vượt thời hạn nghiệp vụ.

### 5.1. Per-attempt timeout

Per-attempt timeout giới hạn thời gian cho một lần gọi:

~~~text
task "fetch-profile" {
    timeout = 2s
    retry max_attempts = 4
}
~~~

### 5.2. Overall deadline

Deadline giới hạn toàn bộ quá trình, bao gồm thời gian thực hiện và thời gian chờ:

~~~text
task "fetch-profile" {
    deadline = 10s
    retry max_attempts = 4
}
~~~

Nếu tổng delay và thời gian chạy đã tiêu hết deadline, không nên bắt đầu một attempt mới.

### 5.3. Retry budget

Retry budget giới hạn phần tài nguyên hoặc thời gian dành cho retry. Ví dụ, trong một khoảng thời gian, tổng số retry không được vượt một tỷ lệ nhất định so với request gốc. Budget giúp ngăn retry amplification khi toàn hệ thống đang suy giảm.

### 5.4. Timeout ambiguity

Timeout không chứng minh thao tác phía server thất bại. Nếu request có thể đã được xử lý, caller phải coi kết quả là unknown cho đến khi tra cứu hoặc dùng idempotency protocol.

### 5.5. Deadline propagation

Workflow cha nên truyền deadline còn lại xuống task con. Nếu mỗi service tự đặt timeout độc lập mà không biết deadline của caller, tổng thời gian có thể vượt kỳ vọng.

### 5.6. Cancellation

Khi workflow bị hủy, scheduler cần ngăn attempt mới, truyền cancellation tới task đang chạy và xử lý các bước đã hoàn tất theo chính sách. Cancellation của caller không tự động hoàn tác side effect đã xảy ra.

## 6. Idempotency và an toàn khi retry

Idempotency là tính chất mà việc thực hiện cùng một thao tác nhiều lần với cùng định danh yêu cầu tạo ra hiệu ứng nghiệp vụ tương đương một lần thực hiện.

### 6.1. Vì sao cần idempotency

Giả sử task tạo thanh toán gửi request đến payment service. Server đã tạo payment nhưng response bị mất. Workflow retry. Nếu server không nhận diện request trùng, khách hàng có thể bị tính tiền hai lần.

### 6.2. Idempotency key

Mỗi thao tác logic có thể gắn một key ổn định:

~~~text
charge_payment {
    order_id = order.id
    amount = order.total
    idempotency_key = workflow.run_id + "/charge-payment"
}
~~~

Key phải giữ nguyên giữa các attempt của cùng thao tác logic. Nếu tạo key mới ở mỗi lần retry, server sẽ xem đó là các thao tác khác nhau.

### 6.3. Server-side deduplication

Service nhận request lưu idempotency key cùng kết quả hoặc trạng thái xử lý. Khi nhận key đã tồn tại, service trả kết quả trước đó hoặc trạng thái đang xử lý theo hợp đồng.

### 6.4. Key scope và retention

Key cần có scope đủ rõ, chẳng hạn tenant, operation và workflow run. Thời gian lưu dedup record phải dài hơn cửa sổ retry và replay có thể xảy ra.

### 6.5. Idempotent PUT và non-idempotent POST

Một số HTTP method có semantics idempotent theo chuẩn, nhưng API ứng dụng vẫn phải định nghĩa hành vi cụ thể. Không nên suy luận rằng mọi POST đều không thể retry hoặc mọi PUT đều an toàn nếu implementation có side effect phụ.

### 6.6. Read-after-timeout

Nếu service hỗ trợ truy vấn theo operation ID, workflow có thể kiểm tra trạng thái trước khi gửi lại:

1. Gửi yêu cầu với operation ID.
2. Nếu timeout, query trạng thái operation.
3. Nếu đã thành công, tiếp tục.
4. Nếu chắc chắn chưa được thực hiện, retry.
5. Nếu vẫn đang xử lý, chờ hoặc query lại theo backoff.

## 7. Retry amplification và retry storm

Retry có thể làm sự cố nghiêm trọng hơn nếu nhiều tầng cùng retry.

### 7.1. Nested retries

Giả sử client retry 3 lần, service gateway retry 3 lần và database driver retry 3 lần. Một thao tác logic có thể tạo tới 27 lần gọi xuống tầng cuối, tùy cách đếm và cách các tầng phối hợp.

### 7.2. Retry storm

Khi một dịch vụ phục hồi, hàng nghìn client có thể cùng retry. Đợt tải đồng loạt này có thể khiến dịch vụ lại quá tải.

### 7.3. Một tầng chịu trách nhiệm retry

Nên xác định tầng nào sở hữu retry policy cho một thao tác. Các tầng dưới có thể retry lỗi nội bộ rất hẹp, nhưng phải phối hợp budget và không nhân bội số lần gọi một cách khó đoán.

### 7.4. Circuit breaker

Circuit breaker tạm ngừng gửi request đến dependency đang có tỷ lệ lỗi cao:

- Closed: request được phép đi qua.
- Open: request bị chặn nhanh trong một khoảng thời gian.
- Half-open: cho phép một số probe để kiểm tra phục hồi.

Circuit breaker và retry bổ sung cho nhau. Retry xử lý lỗi tạm thời ở từng request; circuit breaker ngăn hệ thống tiếp tục gây tải lên dependency đang hỏng.

### 7.5. Bulkhead

Bulkhead giới hạn tài nguyên dành cho từng dependency hoặc nhóm task. Khi một dependency chậm, nó không được phép chiếm hết worker hoặc connection của toàn workflow.

### 7.6. Load shedding

Khi hệ thống quá tải, có thể từ chối sớm một số request thay vì nhận mọi request rồi retry kéo dài. DSL quy trình có thể mô tả nhánh fallback hoặc trạng thái deferred.

## 8. Retry trong DSL quy trình

Một DSL quy trình có thể gắn retry policy vào task hoặc activity.

### 8.1. Retry block

~~~text
task "load-customer" {
    retry {
        max_attempts = 4
        backoff = exponential(
            initial = 200ms,
            multiplier = 2,
            max = 3s
        )
        jitter = full
        on = [NETWORK, TEMPORARY_UNAVAILABLE]
    }

    execute customer_service.load(customer_id)
}
~~~

### 8.2. Retry riêng theo lỗi

~~~text
retry_policy {
    when RATE_LIMIT:
        max_attempts = 6
        respect_retry_after = true

    when NETWORK:
        max_attempts = 4
        backoff = exponential(100ms, 2, 2s)

    otherwise:
        do_not_retry
}
~~~

### 8.3. Retry và nhánh lỗi

~~~text
task "reserve-inventory" {
    retry policy "inventory-retry"

    on_exhausted {
        transition to "inventory-unavailable"
    }
}
~~~

Khi hết retry, workflow cần chuyển sang trạng thái lỗi, fallback, compensation hoặc chờ can thiệp. Không nên để task biến mất khỏi trạng thái đang chạy.

### 8.4. Retry condition

Điều kiện retry có thể dựa trên error type, status code, attempt number hoặc metadata có cấu trúc. Không nên viết expression phụ thuộc vào chuỗi message tùy ý.

### 8.5. Retry callback

Một số hệ thống cần callback trước hoặc sau attempt để ghi metric hoặc cập nhật trace. Callback không nên tạo side effect nghiệp vụ lặp lại ngoài ý muốn.

### 8.6. Retry ở cấp workflow

Retry cả workflow có thể chạy lại những task đã thành công. Nếu workflow chứa side effect, cần checkpoint và idempotency để tránh thực hiện lại thao tác không cần thiết.

## 9. Compensation: khái niệm và mục đích

Trong quy trình phân tán, không phải mọi bước đều nằm trong một transaction database duy nhất. Một bước có thể tạo booking ở dịch vụ A, bước tiếp theo tạo invoice ở dịch vụ B và bước khác gửi yêu cầu thanh toán ở dịch vụ C. Nếu bước cuối thất bại, không thể dùng một lệnh rollback cục bộ để đảo ngược tất cả hệ thống.

**Compensation** là một hành động nghiệp vụ mới nhằm giảm hoặc đảo ngược tác động của bước trước đó.

Ví dụ:

| Bước đã thực hiện | Compensation có thể có |
|---|---|
| Giữ chỗ chuyến bay | Hủy giữ chỗ |
| Đặt phòng khách sạn | Hủy đặt phòng |
| Trừ tiền | Hoàn tiền |
| Tạo đơn hàng | Hủy đơn hoặc đánh dấu cancelled |
| Cấp quyền tạm thời | Thu hồi quyền |
| Tạo tài nguyên cloud | Xóa hoặc đánh dấu cần dọn |

Compensation không phải lúc nào cũng khôi phục chính xác trạng thái ban đầu. Ví dụ hoàn tiền có thể phát sinh phí, hủy vé có thể mất phí hoặc một email đã gửi không thể thu hồi khỏi hộp thư người nhận.

### 9.1. Business compensation

Compensation phản ánh quy tắc nghiệp vụ. Hành động có thể là hủy, hoàn tiền, phát hành credit, thông báo hoặc chuyển sang xử lý thủ công.

### 9.2. Technical rollback

Rollback thường khôi phục trạng thái trong một transaction hoặc hệ thống có cơ chế undo. Compensation thường là một thao tác mới, có thể thất bại và cần retry riêng.

### 9.3. Forward recovery và backward recovery

- **Forward recovery:** tiếp tục đưa quy trình đến trạng thái thành công bằng cách retry hoặc dùng phương án thay thế.
- **Backward recovery:** thực hiện compensation để đưa nghiệp vụ về trạng thái chấp nhận được sau khi không thể tiếp tục.

Một workflow có thể kết hợp cả hai. Ví dụ retry một payment request khi lỗi mạng, nhưng nếu payment bị từ chối vĩnh viễn thì hủy các reservation đã tạo.

## 10. Saga pattern

Saga là mẫu thiết kế cho transaction phân tán, trong đó một quy trình dài được chia thành các local transaction. Mỗi local transaction có thể có một compensation tương ứng.

Ví dụ:

~~~text
T1: Reserve Flight
       |
       v
T2: Reserve Hotel
       |
       v
T3: Charge Payment
       |
       v
T4: Confirm Trip

Nếu T3 thất bại:
C2: Cancel Hotel
       |
       v
C1: Cancel Flight
~~~

Trong ví dụ, compensation thường chạy theo thứ tự ngược của các bước đã hoàn thành để tháo gỡ các phụ thuộc. Tuy nhiên, thứ tự thực tế phải dựa trên semantics nghiệp vụ, không phải mọi compensation đều bắt buộc đảo ngược đơn giản.

### 10.1. Local transaction

Mỗi bước saga thực hiện trong ranh giới transaction của dịch vụ sở hữu dữ liệu. Ví dụ inventory service tự tạo reservation và ghi trạng thái của nó.

### 10.2. Compensation

Mỗi bước có thể khai báo compensation. Compensation cần đủ thông tin để xác định đối tượng đã tạo, ví dụ reservation ID hoặc payment ID.

### 10.3. Saga state

Orchestrator lưu trạng thái các bước, kết quả, correlation ID và compensation cần chạy. State phải bền vững nếu workflow có thể kéo dài qua restart.

### 10.4. Không có atomic commit toàn cục

Saga không làm cho nhiều service trở thành một transaction ACID duy nhất. Trong khoảng thời gian saga chạy, các trạng thái trung gian có thể được nhìn thấy. Hệ thống cần chấp nhận hoặc che giấu trạng thái trung gian theo yêu cầu nghiệp vụ.

### 10.5. Eventual consistency

Sau khi saga hoàn tất hoặc bù trừ, các dịch vụ có thể hội tụ về trạng thái nhất quán cuối cùng. Trong lúc xử lý, một số read model có thể phản ánh trạng thái trung gian.

## 11. Orchestration và choreography

Saga có thể được điều phối theo hai cách chính.

### 11.1. Orchestration

Một orchestrator trung tâm quyết định bước tiếp theo, ghi state và gọi các participant:

~~~text
             Orchestrator
             /    |    \
            v     v     v
         Flight Hotel Payment
~~~

Ưu điểm:

- Luồng quy trình được thể hiện tập trung.
- Dễ quan sát trạng thái tổng thể.
- Có nơi quản lý timeout, retry và compensation.
- Phù hợp với DSL quy trình khai báo.

Nhược điểm:

- Orchestrator trở thành thành phần quan trọng cần bảo đảm availability.
- Logic điều phối có thể phình lớn.
- Cần quản lý version của workflow đang chạy.

### 11.2. Choreography

Các dịch vụ phát và nhận event, mỗi dịch vụ tự quyết định hành động tiếp theo:

~~~text
OrderCreated
    |
    v
InventoryReserved
    |
    v
PaymentRequested
    |
    v
PaymentCompleted
~~~

Ưu điểm:

- Các dịch vụ ít phụ thuộc trực tiếp vào một orchestrator.
- Có thể mở rộng theo event.
- Phù hợp hệ thống hướng sự kiện.

Nhược điểm:

- Khó nhìn toàn bộ luồng khi có nhiều event và subscriber.
- Khó theo dõi retry, duplicate và compensation xuyên dịch vụ.
- Cần correlation và event contract rất rõ.

### 11.3. Hybrid

Một số hệ thống dùng orchestrator cho các quyết định quan trọng và event choreography cho thông báo hoặc cập nhật read model.

### 11.4. Chọn mô hình

Nếu quy trình có nhiều nhánh, timeout và compensation phức tạp, orchestration thường giúp biểu diễn semantics rõ hơn. Nếu các dịch vụ độc lập phản ứng với event và không cần một luồng điều khiển tập trung, choreography có thể phù hợp.

## 12. Định nghĩa compensation trong DSL

DSL có thể khai báo hành động bù trừ ngay cạnh task tạo side effect.

### 12.1. Compensation block

~~~text
task "reserve-hotel" {
    execute hotel.reserve(trip.hotel)

    compensate {
        hotel.cancel(result.reservation_id)
    }
}
~~~

### 12.2. Lưu kết quả cần cho compensation

Compensation thường cần ID hoặc token trả về từ thao tác gốc. Workflow engine phải lưu kết quả đủ bền vững để có thể chạy compensation sau restart.

### 12.3. Compensation theo trạng thái

Không nên chạy compensation nếu thao tác gốc chưa tạo side effect. DSL hoặc runtime cần biết task đã thành công, thất bại trước commit hay có outcome không xác định.

### 12.4. Compensation có điều kiện

~~~text
compensate when reservation.status == CONFIRMED {
    hotel.cancel(reservation.id)
}
~~~

Điều kiện phải dựa trên trạng thái đáng tin cậy. Nếu status không rõ do timeout, cần query service trước khi quyết định.

### 12.5. Compensation registration

Một số engine đăng ký compensation sau khi local transaction thành công. Nếu task chưa hoàn tất, compensation chưa được đưa vào stack. Với kết quả unknown, engine cần một bước reconcile để biết có nên đăng ký hay không.

### 12.6. Compensation scope

Compensation có thể được khai báo theo task, scope hoặc workflow. Nên ưu tiên hành động cụ thể gắn với side effect để giữ rõ quan hệ giữa bước tạo tác động và bước bù trừ.

## 13. Thứ tự và phụ thuộc của compensation

Trong saga tuần tự, compensation thường được chạy ngược thứ tự các local transaction đã hoàn thành.

~~~text
Forward:
T1 -> T2 -> T3 -> T4

Compensation:
C3 -> C2 -> C1
~~~

T4 chưa thành công nên không có C4 trong ví dụ.

### 13.1. Chỉ bù trừ bước đã hoàn thành

Nếu T3 thất bại trước khi tạo side effect, không nên giả định C3 cần chạy. Nếu outcome của T3 không xác định, cần query hoặc reconcile.

### 13.2. Dependency graph

Với workflow song song, compensation order không nhất thiết là một danh sách đảo ngược đơn giản. Nếu task B phụ thuộc A, và cả hai đã tạo side effect, việc bù trừ B trước A thường hợp lý để tháo dependency.

### 13.3. Parallel compensation

Hai compensation độc lập có thể chạy song song để rút ngắn thời gian. Nhưng nếu chúng cùng tác động một resource hoặc có dependency, cần tuần tự hóa.

### 13.4. Compensation dependency

Có thể khai báo dependency riêng:

~~~text
compensation "cancel-hotel" depends_on "release-flight"
~~~

Tên quan hệ phải phản ánh thứ tự thực tế mà engine hiểu. Nên xác định rõ depends_on nghĩa là hành động nào phải hoàn thành trước.

### 13.5. Compensation graph

Engine có thể xây graph từ dependency và thực hiện topological scheduling cho các compensation đủ điều kiện. Nếu graph có chu trình, compiler hoặc workflow validator cần báo lỗi.

## 14. Compensation không phải inverse function

Không phải thao tác nào cũng có phép đảo ngược chính xác.

### 14.1. Hành động có thể đảo ngược gần đúng

Tạo reservation rồi hủy reservation có thể trả tài nguyên về trạng thái có thể đặt lại, nhưng có thể mất phí hoặc thay đổi thứ tự ưu tiên.

### 14.2. Hành động không thể thu hồi

Email đã gửi, thông báo đã hiển thị hoặc dữ liệu đã được người khác đọc không thể hoàn tác. Compensation có thể gửi thông báo đính chính hoặc tạo workflow xử lý tiếp.

### 14.3. Compensation có side effect riêng

Hoàn tiền là một giao dịch mới, có thể phát sinh phí, chờ xử lý hoặc thất bại. Nó cần retry, idempotency và audit riêng.

### 14.4. Business semantics

Compensation cần được chủ sở hữu nghiệp vụ định nghĩa. Không nên tự động suy ra compensation bằng cách đảo dấu một phép toán hoặc chạy ngược code.

### 14.5. Compensated state

Sau compensation, trạng thái thường là CANCELLED, REFUNDED hoặc COMPENSATED, không phải trạng thái ban đầu như thể chưa từng có giao dịch. Lịch sử cần được giữ để audit.

## 15. Retry compensation và lỗi khi bù trừ

Compensation cũng có thể thất bại do lỗi mạng, dịch vụ quá tải hoặc trạng thái không còn phù hợp.

### 15.1. Retry compensation

Một compensation có thể có retry policy riêng:

~~~text
compensate "cancel-reservation" {
    retry {
        max_attempts = 8
        backoff = exponential(500ms, 2, 30s)
        on = [NETWORK, TEMPORARY_UNAVAILABLE]
    }
}
~~~

### 15.2. Compensation failure

Nếu compensation thất bại sau khi hết retry, saga không nên báo đã rollback hoàn toàn. Nó có thể chuyển sang trạng thái COMPENSATION_FAILED hoặc MANUAL_INTERVENTION_REQUIRED.

### 15.3. Retry compensation phải idempotent

Nếu lệnh hủy đã thành công nhưng response bị mất, retry cần không tạo lỗi nghiệp vụ mới hoặc hủy nhầm resource khác. API compensation nên chấp nhận thao tác lặp hoặc cung cấp operation ID để query.

### 15.4. Partial compensation

Một số bước có thể bù trừ thành công, một số bước thất bại. Engine cần ghi trạng thái từng compensation và tiếp tục xử lý những compensation độc lập nếu policy cho phép.

### 15.5. Escalation

Khi không thể tự phục hồi, workflow có thể:

- Gửi alert cho operator.
- Tạo case xử lý thủ công.
- Đưa vào queue cần can thiệp.
- Đặt deadline xử lý.
- Giữ trạng thái nghiệp vụ ở dạng pending compensation.

### 15.6. Không che giấu lỗi bù trừ

Nếu task gốc thất bại và compensation cũng thất bại, báo cáo cần giữ cả hai lỗi. Chỉ hiển thị lỗi ban đầu sẽ khiến operator không biết side effect nào còn tồn tại.

## 16. Pivot transaction và điểm không thể quay lại

Trong saga dài, có thể có một bước được xem là pivot: sau bước này, quy trình không còn dùng backward compensation theo cách thông thường mà chuyển sang forward recovery hoặc hoàn tất.

### 16.1. Pivot step

Ví dụ sau khi thanh toán không hoàn lại được xác nhận, workflow có thể coi đó là điểm chuyển. Nếu bước gửi thông báo thất bại, hệ thống retry gửi thông báo thay vì tự động hoàn tiền.

### 16.2. Compensable, pivot và retryable steps

Một saga có thể gồm:

- Các bước compensable: có hành động bù trừ.
- Pivot: điểm quyết định không thể quay lại theo chính sách.
- Các bước retryable: sau pivot, hệ thống cố gắng hoàn tất bằng retry hoặc xử lý thay thế.

### 16.3. Khai báo trong DSL

~~~text
workflow "purchase" {
    task "reserve-stock" compensable
    task "authorize-payment" pivot
    task "create-shipment" retryable
}
~~~

Đây là cú pháp khái niệm. Engine cần định nghĩa rõ điều gì xảy ra nếu lỗi trước hoặc sau pivot.

### 16.4. Pivot không phải lúc nào cũng là commit kỹ thuật

Pivot là quyết định theo semantics nghiệp vụ. Nó không tự biến nhiều hệ thống thành transaction nguyên tử.

## 17. Retry, compensation và durable execution

Workflow dài có thể kéo dài nhiều phút, giờ hoặc ngày. Engine không nên giữ thread trong suốt thời gian chờ retry hoặc chờ compensation.

### 17.1. Durable state

Engine lưu trạng thái workflow, task, attempt, timer, kết quả và compensation registration vào storage bền vững.

### 17.2. Timer-based retry

Khi cần chờ backoff, engine lưu thời điểm retry tiếp theo rồi giải phóng worker. Đến thời điểm phù hợp, scheduler khôi phục task.

### 17.3. Checkpoint

Checkpoint lưu tiến trình đủ để tiếp tục sau khi process restart. Cần bao gồm trạng thái đã hoàn thành và thông tin side effect.

### 17.4. Event log

Event log có thể ghi task scheduled, attempt started, attempt failed, retry scheduled, task completed, compensation started và compensation completed.

### 17.5. Recovery

Sau restart, engine đọc state và event log, xác định task nào đang chờ, task nào có outcome không xác định và compensation nào còn phải chạy.

### 17.6. Exactly-once execution

Trong hệ thống phân tán, không nên giả định engine có thể bảo đảm một lời gọi bên ngoài chỉ xảy ra đúng một lần trong mọi tình huống lỗi. Thực tế thường là delivery at-least-once kết hợp idempotency, deduplication và reconciliation để tạo hiệu ứng nghiệp vụ tương đương một lần.

## 18. Transactional outbox và phối hợp event

Khi một service cập nhật database và phát event, có thể xảy ra tình huống database commit thành công nhưng event không được gửi, hoặc event gửi thành công nhưng transaction database rollback.

### 18.1. Transactional outbox

Service ghi thay đổi nghiệp vụ và một outbox record trong cùng transaction local. Một publisher riêng đọc outbox và gửi event, sau đó đánh dấu đã gửi.

~~~text
Local DB transaction
   |-- update order
   |-- insert outbox event
   v
Commit
   |
   v
Outbox publisher
   |
   v
Message broker
~~~

Publisher có thể gửi lại cùng event nếu không nhận được xác nhận. Consumer vẫn cần idempotency hoặc inbox deduplication.

### 18.2. Inbox deduplication

Consumer lưu event ID đã xử lý cùng với thay đổi local trong một transaction. Khi event lặp lại, consumer nhận ra và không áp dụng side effect lần thứ hai.

### 18.3. Outbox không thay thế saga

Outbox giúp phối hợp local state change với phát event đáng tin cậy. Saga vẫn cần quản lý tiến trình nhiều bước, retry, compensation và trạng thái cuối.

## 19. Dead-letter queue và xử lý thủ công

Một message hoặc task có thể thất bại lặp lại vì dữ liệu độc hại, lỗi không phân loại hoặc dependency không phục hồi.

### 19.1. Dead-letter queue

Sau khi vượt retry policy, message có thể được chuyển vào dead-letter queue (DLQ) để điều tra hoặc xử lý riêng.

### 19.2. DLQ metadata

Nên lưu:

- Message ID.
- Workflow/run ID.
- Số lần thử.
- Error category và code.
- Thời điểm lỗi cuối.
- Consumer hoặc task.
- Correlation ID.
- Schema version.

Tránh lưu secret hoặc payload nhạy cảm không cần thiết.

### 19.3. Replay từ DLQ

Replay cần quyết định:

- Dùng ruleset version cũ hay mới?
- Có giữ idempotency key cũ không?
- Có bỏ qua event đã xử lý một phần không?
- Có cần operator phê duyệt không?
- Side effect trước đó có tồn tại không?

Replay không có kiểm soát có thể nhân đôi giao dịch hoặc làm sai thứ tự.

### 19.4. Poison message

Poison message là message luôn gây lỗi, ví dụ payload không parse được. Retry liên tục không giúp ích. Cần phát hiện và chuyển sang DLQ hoặc nhánh xử lý lỗi.

### 19.5. Manual intervention

Một số compensation cần quyết định của con người, ví dụ hoàn tiền một phần hoặc liên hệ đối tác. Workflow cần trạng thái chờ can thiệp, audit người xử lý và khả năng tiếp tục an toàn sau quyết định.

## 20. Concurrency và compensation

Workflow có thể chạy nhiều task song song. Điều này làm thứ tự compensation phức tạp hơn.

### 20.1. Parallel branch

~~~text
             Start
             /   \
            v     v
       Reserve A  Reserve B
            \     /
             v   v
             Join
               |
               v
             Charge
~~~

Nếu Reserve A và Reserve B đều thành công nhưng Charge thất bại, hai compensation có thể chạy song song nếu độc lập.

### 20.2. Join semantics

Join có thể chờ tất cả nhánh, một số nhánh hoặc điều kiện quorum. Compensation policy cần biết nhánh nào đã hoàn tất và nhánh nào còn đang chạy.

### 20.3. Cancel in-flight tasks

Khi một nhánh thất bại, engine có thể hủy các nhánh đang chạy. Tuy nhiên, cancellation chỉ dừng công việc nếu participant hỗ trợ; một request đã commit vẫn có thể cần compensation.

### 20.4. Race giữa completion và cancellation

Một task có thể hoàn tất đồng thời với lệnh cancel. Engine cần lưu trạng thái nhất quán để không bỏ sót side effect đã xảy ra. Outcome không xác định cần được reconcile.

### 20.5. Compensation dependency

Nếu compensation A cần kết quả của task B, không thể chạy A trước khi biết trạng thái B. Dependency graph cần bao phủ cả forward và compensation path.

## 21. DSL biểu diễn toàn bộ quy trình retry và bù trừ

Ví dụ workflow đặt chuyến đi:

~~~text
workflow "book-trip" {
    input traveler_id: String
    input flight_id: String
    input hotel_id: String

    task "reserve-flight" {
        retry {
            max_attempts = 4
            backoff = exponential(200ms, 2, 4s)
            on = [NETWORK, TEMPORARY_UNAVAILABLE]
        }

        result flight_reservation =
            flight.reserve(
                traveler_id,
                flight_id,
                idempotency_key = run.id + "/flight"
            )

        compensate {
            flight.cancel(
                flight_reservation.id,
                idempotency_key = run.id + "/cancel-flight"
            )
        }
    }

    task "reserve-hotel" {
        retry {
            max_attempts = 3
            backoff = exponential(300ms, 2, 3s)
            on = [NETWORK, RATE_LIMIT]
        }

        result hotel_reservation =
            hotel.reserve(
                traveler_id,
                hotel_id,
                idempotency_key = run.id + "/hotel"
            )

        compensate {
            hotel.cancel(
                hotel_reservation.id,
                idempotency_key = run.id + "/cancel-hotel"
            )
        }
    }

    task "charge-payment" {
        retry {
            max_attempts = 2
            on = [NETWORK]
        }

        result payment =
            payment.charge(
                traveler_id,
                idempotency_key = run.id + "/payment"
            )
    }

    on_failure {
        compensate_completed_tasks
        if compensation_failed {
            transition to "manual-recovery"
        }
    }
}
~~~

Ví dụ minh họa cần được diễn giải theo semantics cụ thể của engine. Nếu payment request timeout và outcome chưa rõ, engine cần query payment status trước khi quyết định compensation. Nếu payment đã thành công, việc hủy flight và hotel có thể không còn đúng với chính sách nghiệp vụ; có thể cần refund hoặc một nhánh xử lý khác.

## 22. State machine cho retry và compensation

Một task có thể có các trạng thái:

~~~text
PENDING
   |
   v
RUNNING
   | success
   +--------------------> SUCCEEDED
   |
   | retryable failure
   v
RETRY_WAIT
   |
   v
RUNNING
   |
   | attempts exhausted
   v
FAILED
   |
   | compensation required
   v
COMPENSATING
   | success
   v
COMPENSATED
~~~

Các trạng thái bổ sung có thể gồm:

- CANCEL_REQUESTED.
- CANCELLED.
- OUTCOME_UNKNOWN.
- COMPENSATION_RETRY_WAIT.
- COMPENSATION_FAILED.
- MANUAL_INTERVENTION_REQUIRED.
- TIMED_OUT.

### 22.1. State transition rules

Engine cần định nghĩa transition hợp lệ. Ví dụ task không thể chuyển từ PENDING trực tiếp sang COMPENSATED nếu chưa có side effect cần bù trừ.

### 22.2. Durable transition

State transition cần được lưu bền vững trước khi engine thực hiện bước phụ thuộc vào nó. Nếu process crash giữa hai thao tác, recovery phải xác định được trạng thái cuối đã commit.

### 22.3. Duplicate signal

Event completion hoặc timeout có thể đến nhiều lần. State machine cần xử lý signal lặp theo cách idempotent.

### 22.4. Terminal states

SUCCEEDED, COMPENSATED, FAILED và MANUAL_INTERVENTION_REQUIRED có ý nghĩa khác nhau. Không nên gom tất cả thành DONE, vì operator cần biết quy trình kết thúc theo cách nào.

## 23. Observability cho retry và compensation

Retry và compensation có thể kéo dài, vì vậy cần quan sát được từng lần thử và từng hành động bù trừ.

### 23.1. Attempt metrics

Các metric có thể gồm:

- Số attempt trên mỗi task.
- Retry rate.
- Retry exhaustion rate.
- Thời gian chờ backoff.
- Thời gian thực hiện mỗi attempt.
- Lỗi theo category và dependency.

### 23.2. Compensation metrics

Theo dõi:

- Số saga cần compensation.
- Compensation success/failure rate.
- Thời gian từ khi bắt đầu đến khi hoàn tất bù trừ.
- Số workflow đang chờ manual intervention.
- Số side effect còn chưa được reconcile.

### 23.3. Correlation

Log, trace và event nên mang workflow ID, run ID, task ID, attempt number và operation ID. Nhờ vậy có thể nối một retry với side effect và compensation tương ứng.

### 23.4. Trace spans

Mỗi attempt có thể là một span con. Compensation có thể có span riêng liên kết với task gốc. Không nên chỉ tạo một span rất dài cho toàn bộ workflow nếu cần phân tích chi tiết.

### 23.5. Alerting

Cảnh báo có thể kích hoạt khi retry exhaustion tăng, dependency mở circuit breaker kéo dài, compensation thất bại hoặc số workflow ở trạng thái pending recovery vượt ngưỡng.

### 23.6. Không ghi payload nhạy cảm

Trace cần metadata để điều tra nhưng không nên chứa password, token, payment data hoặc dữ liệu cá nhân không cần thiết.

## 24. Kiểm thử retry và compensation

Các cơ chế phục hồi cần được kiểm thử với lỗi được điều khiển, không chỉ chạy happy path.

### 24.1. Retry transient failure

Giả lập dependency thất bại hai lần rồi thành công. Xác nhận số attempt, delay và kết quả cuối.

### 24.2. Permanent failure

Trả lỗi validation hoặc permission. Xác nhận engine không retry nếu policy không cho phép.

### 24.3. Timeout với outcome unknown

Cho server commit side effect nhưng làm mất response. Xác nhận retry dùng idempotency key hoặc query trạng thái, không tạo side effect thứ hai.

### 24.4. Backoff và jitter

Dùng clock giả và random generator có seed để xác nhận delay, maxDelay và jitter theo đúng policy.

### 24.5. Deadline exhaustion

Xác nhận không bắt đầu attempt mới sau deadline và trạng thái task phản ánh timeout hoặc budget exhaustion.

### 24.6. Compensation order

Cho nhiều task thành công rồi làm task tiếp theo thất bại. Xác nhận compensation chạy theo dependency và thứ tự được định nghĩa.

### 24.7. Compensation failure

Giả lập compensation thất bại rồi thành công sau retry. Xác nhận trạng thái, audit và số attempt chính xác.

### 24.8. Crash recovery

Dừng engine sau khi service đã commit nhưng trước khi engine ghi nhận completion. Khi khởi động lại, xác nhận engine reconcile operation và không bỏ sót compensation.

### 24.9. Parallel branch

Chạy nhiều nhánh đồng thời, làm một nhánh thất bại và kiểm tra cancellation, completion race và compensation của các nhánh khác.

### 24.10. Duplicate event

Gửi lại event hoặc completion signal. Xác nhận workflow không thực hiện side effect hai lần.

### 24.11. Property-based testing

Có thể sinh chuỗi event và lỗi ngẫu nhiên, sau đó kiểm tra invariant như:

- Không compensation task chưa từng tạo side effect.
- Mỗi operation ID chỉ có một hiệu ứng logic.
- Không vượt retry budget.
- Workflow cuối cùng đạt terminal state hoặc trạng thái chờ can thiệp được ghi nhận.

## 25. Triển khai retry bằng Java

Ví dụ sau minh họa cấu trúc retry đồng bộ. Một workflow engine thực tế cần thêm deadline, cancellation, scheduler bền vững và idempotency ở service đích.

### 25.1. Retry policy

~~~java
import java.time.Duration;
import java.util.Set;

public record RetryPolicy(
        int maxAttempts,
        Duration initialDelay,
        double multiplier,
        Duration maxDelay,
        Set<Class<? extends Exception>> retryable
) {
}
~~~

### 25.2. Retry executor đơn giản

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class RetryExecutor {
    public static <T> T execute(
            RetryPolicy policy,
            java.util.concurrent.Callable<T> operation
    ) throws Exception {
        Duration delay = policy.initialDelay();

        for (int attempt = 1;
             attempt <= policy.maxAttempts();
             attempt++) {
            try {
                return operation.call();
            } catch (Exception error) {
                boolean retryable = policy.retryable().stream()
                    .anyMatch(type -> type.isInstance(error));

                if (!retryable || attempt == policy.maxAttempts()) {
                    throw error;
                }

                long capMillis = Math.min(
                    policy.maxDelay().toMillis(),
                    delay.toMillis()
                );
                long waitMillis =
                    ThreadLocalRandom.current().nextLong(capMillis + 1);

                Thread.sleep(waitMillis);
                long nextMillis = Math.min(
                    policy.maxDelay().toMillis(),
                    (long) (delay.toMillis() * policy.multiplier())
                );
                delay = Duration.ofMillis(nextMillis);
            }
        }

        throw new IllegalStateException("Retry loop ended unexpectedly");
    }
}
~~~

Đây là ví dụ minh họa full jitter với delay cap. Implementation production cần kiểm tra giá trị policy, xử lý interrupt đúng cách, tôn trọng Retry-After, deadline, retry budget và cancellation. Không nên giữ thread bằng Thread.sleep trong một engine điều phối nhiều workflow; dùng scheduler hoặc timer bền vững.

### 25.3. Không retry mọi exception

Danh sách retryable phải dựa trên error type hoặc mã lỗi ổn định. Các exception validation, authorization và business rejection thường không nên retry.

## 26. Triển khai compensation bằng Java

Một workflow engine có thể đăng ký compensation sau khi task hoàn tất.

### 26.1. Compensation action

~~~java
@FunctionalInterface
public interface CompensationAction {
    void compensate() throws Exception;
}
~~~

### 26.2. Compensation stack

~~~java
import java.util.ArrayDeque;
import java.util.Deque;

public final class CompensationStack {
    private final Deque<CompensationAction> actions =
        new ArrayDeque<>();

    public void register(CompensationAction action) {
        actions.push(action);
    }

    public void compensateAll() throws Exception {
        Exception firstFailure = null;

        while (!actions.isEmpty()) {
            CompensationAction action = actions.pop();
            try {
                action.compensate();
            } catch (Exception error) {
                if (firstFailure == null) {
                    firstFailure = error;
                } else {
                    firstFailure.addSuppressed(error);
                }
            }
        }

        if (firstFailure != null) {
            throw firstFailure;
        }
    }
}
~~~

Stack minh họa thứ tự LIFO. Nó không phải implementation durable: nếu process dừng, stack trong bộ nhớ mất. Production engine cần lưu compensation registration và trạng thái từng action trong storage bền vững.

### 26.3. Đăng ký sau khi thành công

~~~java
Reservation reservation = hotel.reserve(request);

compensationStack.register(
    () -> hotel.cancel(
        reservation.id(),
        "workflow-123/cancel-hotel"
    )
);
~~~

Compensation cần dùng ID trả về từ thao tác gốc và idempotency key ổn định. Nếu thao tác reserve timeout với outcome unknown, không thể đơn giản bỏ qua registration; cần tra cứu reservation trước.

### 26.4. Ghi nhận trạng thái

Trong implementation bền vững, mỗi compensation có thể có trạng thái PENDING, RUNNING, SUCCEEDED, RETRY_WAIT hoặc FAILED. Cập nhật trạng thái và ghi operation result cần được thiết kế để recovery sau crash.

## 27. Thiết kế API cho task có retry và compensation

Một task có side effect nên công bố hợp đồng đủ để workflow engine điều phối an toàn.

### 27.1. Operation identity

Mỗi thao tác logic có operation ID ổn định giữa các lần retry. ID này được dùng để deduplicate và query kết quả.

### 27.2. Result contract

Kết quả nên chứa resource ID, operation ID và trạng thái rõ ràng. Không chỉ trả về boolean thành công/thất bại nếu caller cần reconcile.

### 27.3. Compensation contract

Compensation cần:

- Nhận đúng resource ID do thao tác gốc tạo.
- Chấp nhận retry hoặc hỗ trợ query status.
- Xác định hành vi khi resource đã được bù trừ.
- Trả kết quả có cấu trúc.
- Không xóa audit history.

### 27.4. Error contract

API nên phân loại lỗi bằng code ổn định, retryability hoặc retry-after metadata. Caller không nên suy đoán từ message tự do.

### 27.5. Versioning

Khi API hoặc semantics compensation thay đổi, workflow đang chạy có thể vẫn dùng version cũ. Cần giữ tương thích hoặc lưu version contract theo run.

## 28. Quản lý workflow đang chạy khi DSL thay đổi

Một workflow có thể kéo dài qua nhiều ngày. Trong thời gian đó, source DSL có thể được cập nhật.

### 28.1. Pin workflow version

Run nên gắn với workflow definition version hoặc digest đã khởi tạo nó. Điều này giúp xác định retry và compensation phải dùng logic nào.

### 28.2. Versioned task handlers

Task handler cũ có thể cần tồn tại cho workflow run cũ. Xóa handler ngay sau deploy có thể khiến workflow không thể tiếp tục hoặc bù trừ.

### 28.3. Migration

Engine có thể hỗ trợ migration state, nhưng migration cần quy định cách xử lý task đang retry, compensation đã đăng ký và operation chưa rõ kết quả.

### 28.4. Forward compatibility

Không nên giả định workflow state cũ có thể được đọc bởi engine mới nếu schema state đã thay đổi. Cần version và migration path.

### 28.5. Compensation code retention

Code bù trừ có thể cần lâu hơn code forward path vì một workflow cũ có thể thất bại muộn. Cần giữ handler và contract đủ lâu theo thời hạn tối đa của workflow và retention policy.

## 29. Những sai lầm thường gặp

### 29.1. Retry mọi lỗi

Validation và permission error thường không tự biến mất. Phân loại lỗi trước khi retry.

### 29.2. Không đặt giới hạn

Retry vô hạn giữ tài nguyên và có thể làm workflow treo. Đặt max attempts, deadline và budget.

### 29.3. Retry thao tác không idempotent

Timeout có thể xảy ra sau khi side effect đã hoàn tất. Dùng idempotency key hoặc query trạng thái trước khi gửi lại.

### 29.4. Dùng backoff không có jitter

Nhiều client có thể retry đồng loạt. Thêm jitter và tôn trọng Retry-After.

### 29.5. Retry ở mọi tầng

Nested retries nhân số request và gây retry storm. Xác định tầng sở hữu policy và phối hợp budget.

### 29.6. Coi timeout là thất bại chắc chắn

Caller có thể timeout trong khi server đã commit. Dùng operation status hoặc idempotency để giải quyết outcome unknown.

### 29.7. Coi compensation là rollback

Compensation là hành động nghiệp vụ mới, có thể không đảo ngược hoàn toàn và cũng có thể thất bại. Ghi trạng thái compensated riêng.

### 29.8. Bù trừ cả task chưa thành công

Nếu task chưa tạo side effect, compensation có thể hủy nhầm resource hoặc tạo lỗi mới. Đăng ký compensation sau khi xác nhận thao tác thành công.

### 29.9. Bỏ qua compensation failure

Không được báo workflow đã rollback nếu một compensation chưa hoàn tất. Giữ trạng thái cần can thiệp và cảnh báo.

### 29.10. Compensation không idempotent

Retry lệnh refund hoặc cancel có thể gây hiệu ứng trùng. Compensation cần operation ID và hợp đồng dedup.

### 29.11. Không lưu durable state

Compensation stack trong bộ nhớ mất khi process restart. Lưu registration, task state và attempt history bền vững.

### 29.12. Không reconcile outcome unknown

Nếu service commit nhưng response mất, engine không biết có side effect hay không. Query trạng thái theo operation ID trước khi retry hoặc bù trừ.

### 29.13. Bù trừ sai thứ tự

Compensation có thể phụ thuộc nhau. Dùng dependency graph và chỉ chạy các hành động đã đủ điều kiện.

### 29.14. Thay đổi workflow handler quá sớm

Workflow cũ có thể cần retry hoặc compensation sau khi phiên bản mới được deploy. Pin version và giữ handler tương thích.

### 29.15. Chỉ quan sát kết quả cuối

Không có attempt trace và compensation history thì khó điều tra vì sao quy trình thất bại hoặc còn side effect nào.

## 30. Quy trình thiết kế retry và compensation cho DSL

Một quy trình triển khai có thể gồm:

1. **Liệt kê side effect.** Xác định task nào gọi hệ thống ngoài, tạo resource, ghi dữ liệu hoặc phát event.
2. **Phân loại lỗi.** Tách transient, throttling, conflict, permanent và unknown outcome.
3. **Định nghĩa retry policy.** Chọn attempts, backoff, jitter, timeout, deadline và retry budget.
4. **Thiết kế idempotency.** Tạo operation ID ổn định và hợp đồng dedup/query status ở service đích.
5. **Xác định compensation.** Mô tả hành động nghiệp vụ cho từng side effect có thể bù trừ.
6. **Xác định pivot.** Làm rõ điểm sau đó workflow phải forward-recover hoặc hoàn tất.
7. **Mô hình hóa dependency.** Định nghĩa thứ tự task và compensation, bao gồm các nhánh song song.
8. **Chọn orchestration model.** Orchestration, choreography hoặc hybrid theo độ phức tạp và yêu cầu quan sát.
9. **Lưu durable state.** Persist attempt, timer, result, compensation registration và workflow version.
10. **Thiết kế recovery.** Xử lý crash, duplicate event, timeout và outcome unknown.
11. **Cô lập side effect.** Dùng transaction local, outbox/inbox, sandbox hoặc adapter phù hợp.
12. **Thêm observability.** Ghi workflow ID, operation ID, attempt, error category và compensation state.
13. **Đặt manual recovery.** Có trạng thái, queue và quy trình cho trường hợp không thể tự phục hồi.
14. **Kiểm thử failure path.** Mô phỏng lỗi ở từng bước, response mất, compensation thất bại và restart.
15. **Quản lý version.** Giữ semantics và handler phù hợp cho workflow đang chạy.

## 31. Câu hỏi tự kiểm tra

1. Retry và compensation khác nhau như thế nào trong DSL quy trình?
2. Phân biệt transient error, permanent error và unknown outcome.
3. Một retry policy cần những tham số nào?
4. Exponential backoff và jitter giải quyết vấn đề gì?
5. Timeout khác deadline và retry budget như thế nào?
6. Vì sao timeout không chứng minh thao tác phía server thất bại?
7. Idempotency key cần ổn định như thế nào giữa các attempt?
8. Retry amplification và retry storm xảy ra trong tình huống nào?
9. Circuit breaker và bulkhead phối hợp với retry ra sao?
10. Compensation khác rollback kỹ thuật như thế nào?
11. Saga pattern chia quy trình phân tán thành những thành phần nào?
12. Orchestration và choreography có ưu nhược điểm gì?
13. Vì sao compensation thường chạy theo dependency ngược của các bước đã hoàn thành?
14. Khi nào compensation không thể khôi phục chính xác trạng thái ban đầu?
15. Compensation failure cần được biểu diễn và xử lý như thế nào?
16. Pivot transaction có ý nghĩa gì trong saga?
17. Durable execution giúp retry và compensation sống sót qua restart ra sao?
18. Transactional outbox và inbox deduplication giải quyết vấn đề gì?
19. Vì sao một workflow cần lưu version definition và handler tương ứng?
20. Hãy thiết kế một saga đặt hàng gồm reserve inventory, charge payment và create shipment; xác định retry, idempotency, compensation và pivot.
