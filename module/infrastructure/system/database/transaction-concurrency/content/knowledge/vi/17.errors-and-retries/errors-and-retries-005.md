# Lùi thời gian theo cấp số nhân và thêm độ lệch ngẫu nhiên

Khi một request gặp lỗi tạm thời, ứng dụng thường thử lại thay vì thất bại ngay. Nhưng nếu nhiều client cùng retry ngay lập tức, chúng có thể tiếp tục gửi tải vào đúng thời điểm hệ thống đang quá tải. Các lần retry đồng loạt làm tăng số request, kéo dài thời gian phục hồi và có thể tạo thành vòng lặp quá tải.

**Exponential backoff** giải quyết một phần vấn đề bằng cách tăng dần thời gian chờ giữa các lần thử. **Jitter** thêm một khoảng ngẫu nhiên vào thời gian chờ để các client không cùng thức dậy và gửi lại request tại một thời điểm. Hai kỹ thuật thường được dùng cùng nhau, kèm giới hạn số lần thử, deadline và quy tắc xác định lỗi nào có thể retry.

Trong xử lý transaction cơ sở dữ liệu, retry còn phải bảo đảm đúng ranh giới transaction. Nếu DBMS hủy một transaction do serialization failure hoặc deadlock, ứng dụng thường cần rollback và chạy lại toàn bộ transaction trong một transaction mới. Không được chỉ gửi lại câu UPDATE cuối cùng khi các quyết định trước đó dựa trên snapshot cũ.

## 1. Vì sao retry ngay lập tức có thể làm hệ thống tệ hơn?

Giả sử một dịch vụ phụ thuộc đang quá tải hoặc vừa khởi động lại. Một nghìn client cùng gửi request và nhận timeout. Nếu tất cả lập tức retry, dịch vụ nhận thêm một nghìn request đúng lúc đang cố phục hồi.

Một chuỗi đơn giản có thể xảy ra:

1. Dịch vụ chậm vì tải cao.
2. Client timeout và retry ngay.
3. Request retry làm tải tăng thêm.
4. Dịch vụ càng chậm, nhiều client timeout hơn.
5. Các client tiếp tục retry, tạo ra một đợt tải mới.

Hiện tượng này thường được gọi là retry storm. Nếu nhiều client có cùng lịch retry cố định, chúng còn có thể tạo thành các đợt request đồng bộ, hay còn gọi là thundering herd.

### Ví dụ retry đồng bộ

Giả sử 500 worker cùng gặp lỗi lúc 10:00:00 và đều chờ đúng 2 giây:

~~~text
10:00:00  500 worker nhận lỗi
10:00:02  500 worker retry cùng lúc
10:00:04  Những worker thất bại lại retry cùng lúc
10:00:06  Một đợt request đồng bộ khác
~~~

Ngay cả khi dịch vụ đã bắt đầu phục hồi, các đợt tải dồn cục vẫn có thể làm nó tiếp tục quá tải.

Jitter làm thời điểm retry phân tán ra một khoảng thời gian, nhờ đó giảm đỉnh tải do nhiều client cùng hành động.

## 2. Exponential backoff hoạt động như thế nào?

Exponential backoff tăng thời gian chờ sau mỗi lần thất bại. Một công thức cơ bản:

\[
d_n = \min(d_{\max}, d_0 \times r^{n-1})
\]

Trong đó:

- \(d_n\): thời gian chờ trước lần retry thứ \(n\).
- \(d_0\): thời gian chờ ban đầu.
- \(r\): hệ số tăng, thường lớn hơn 1, ví dụ 2.
- \(d_{\max}\): thời gian chờ tối đa.

Ví dụ:

- Lần đầu chờ 200 ms.
- Hệ số tăng là 2.
- Giới hạn tối đa là 5 giây.

| Lần retry | Thời gian chờ trước jitter |
|---:|---:|
| 1 | 200 ms |
| 2 | 400 ms |
| 3 | 800 ms |
| 4 | 1.600 ms |
| 5 | 3.200 ms |
| 6 | 5.000 ms |
| 7 | 5.000 ms |

Thời gian chờ tăng nhanh ở các lần đầu để ứng dụng không liên tục đánh vào dịch vụ đang lỗi. Sau khi đạt mức tối đa, nó không tiếp tục tăng vô hạn.

### Chọn tham số ban đầu

Không có một bộ tham số phù hợp cho mọi hệ thống. Cần xét:

- Độ trễ bình thường của dịch vụ.
- Thời gian dịch vụ thường cần để phục hồi.
- Deadline của request phía trên.
- Số lần retry tối đa.
- Số lượng client có thể cùng retry.
- Tác động của một request bị lặp lên dữ liệu.
- Chính sách retry của thư viện, proxy và message broker.

Một request tương tác người dùng có deadline ngắn không thể chờ hàng phút. Một job nền có thể chờ lâu hơn, nhưng vẫn cần giới hạn tổng thời gian và số lần thử.

## 3. Jitter là gì?

Jitter là độ ngẫu nhiên được thêm vào lịch retry. Thay vì mọi client chờ cùng một khoảng cố định, mỗi client chọn thời gian chờ trong một miền cho phép.

Ví dụ, exponential backoff tạo ra thời gian cơ sở 4 giây. Nếu dùng full jitter, mỗi client chọn một giá trị ngẫu nhiên từ 0 đến 4 giây. Một client có thể retry sau 0,6 giây, client khác sau 2,8 giây. Các lần retry không còn tập trung vào cùng một mốc.

Jitter có ích khi:

- Nhiều worker hoặc client có thể gặp lỗi cùng thời điểm.
- Hệ thống phụ thuộc có giới hạn thông lượng.
- Các instance được khởi động hoặc phục hồi cùng lúc.
- Nhiều request tranh chấp cùng tài nguyên nóng.
- Retry được phân phối trên nhiều máy hoặc vùng triển khai.

Jitter không thay thế giới hạn số lần retry, deadline hay cơ chế giới hạn tải. Nó chỉ làm phân tán thời điểm gửi lại.

## 4. Các chiến lược jitter phổ biến

Có nhiều cách kết hợp thời gian backoff và số ngẫu nhiên. Cần chọn một chiến lược rõ ràng, không trộn công thức tùy tiện giữa các service.

### Full jitter

Tính thời gian backoff có giới hạn \(c_n\), rồi chọn ngẫu nhiên:

\[
d_n \sim U(0, c_n)
\]

với:

\[
c_n = \min(d_{\max}, d_0 \times r^{n-1})
\]

Mỗi lần retry chọn ngẫu nhiên từ 0 đến mức backoff hiện tại.

Ví dụ:

| Lần retry | Mức backoff tối đa | Khoảng có thể chọn |
|---:|---:|---:|
| 1 | 200 ms | 0–200 ms |
| 2 | 400 ms | 0–400 ms |
| 3 | 800 ms | 0–800 ms |
| 4 | 1.600 ms | 0–1.600 ms |
| 5 | 3.200 ms | 0–3.200 ms |

Full jitter thường giúp giảm đỉnh tải rõ rệt khi rất nhiều client cùng retry. Đổi lại, một số client có thể chọn thời gian chờ khá ngắn, kể cả ở lần retry đã có backoff lớn.

### Equal jitter

Chia thời gian backoff thành một nửa cố định và một nửa ngẫu nhiên:

\[
d_n = \frac{c_n}{2} + U(0, \frac{c_n}{2})
\]

Nếu mức backoff là 4 giây, thời gian chờ nằm trong khoảng 2–4 giây. Chiến lược này giữ lại một phần thời gian chờ tối thiểu, tránh trường hợp full jitter chọn một giá trị rất gần 0.

### Decorrelated jitter

Decorrelated jitter dùng thời gian chờ trước đó để tạo thời gian chờ mới. Một dạng thường gặp:

\[
d_n = \min(d_{\max}, U(d_0, 3 \times d_{n-1}))
\]

Lần đầu dùng \(d_0\); các lần sau chọn ngẫu nhiên dựa trên thời gian chờ trước, rồi giới hạn ở \(d_{\max}\).

Chiến lược này tạo ra chuỗi thời gian chờ ít đồng bộ hơn. Nó không giống full jitter: thời gian retry mới phụ thuộc vào giá trị lần trước, nên cần lưu trạng thái backoff của request hoặc operation.

### So sánh

| Chiến lược | Công thức khái quát | Đặc điểm |
|---|---|---|
| Backoff cố định | \(d_n = d_0\) | Dễ làm nhưng nhiều client dễ đồng bộ |
| Exponential không jitter | \(d_n = \min(d_{\max}, d_0r^{n-1})\) | Khoảng cách tăng nhưng client cùng thời điểm vẫn retry cùng lúc |
| Full jitter | \(U(0,c_n)\) | Phân tán rộng, giảm đỉnh tải |
| Equal jitter | \(c_n/2 + U(0,c_n/2)\) | Có thời gian chờ tối thiểu |
| Decorrelated jitter | \(U(d_0,3d_{n-1})\), có giới hạn | Phụ thuộc lần chờ trước, phân tán theo chuỗi |

Không có chiến lược nào luôn tốt nhất. Full jitter là lựa chọn mặc định hữu ích cho nhiều workload phân tán; equal jitter có ích khi muốn giữ một khoảng chờ tối thiểu; decorrelated jitter phù hợp khi cần phân tán lịch retry theo trạng thái trước đó. Hãy đo tải và độ trễ thực tế thay vì chọn chỉ dựa trên công thức.

## 5. Ví dụ triển khai pseudocode

Mẫu sau minh họa full jitter với số lần thử hữu hạn:

~~~text
base_delay = 200 milliseconds
max_delay = 5 seconds
multiplier = 2
max_attempts = 6

for attempt from 1 to max_attempts:
    result = call_service()

    if result is success:
        return result

    if error is not retryable:
        raise error

    if attempt == max_attempts:
        raise retry_exhausted

    cap = min(max_delay, base_delay * multiplier^(attempt - 1))
    delay = random_duration(0, cap)

    sleep(delay)
~~~

Đây là pseudocode. Trong code thực tế:

- Dùng bộ sinh số ngẫu nhiên phù hợp với môi trường chạy.
- Dùng kiểu thời gian đủ lớn để phép nhân không bị overflow.
- Giới hạn thời gian chờ trước khi chuyển sang kiểu integer của thư viện timer.
- Không giữ transaction database mở trong lúc sleep.
- Hủy sleep khi request bị cancel hoặc deadline đã hết.
- Ghi nhận attempt number và thời gian chờ thực tế để quan sát.

### Ví dụ Python minh họa

~~~python
import random
import time

def retry_with_full_jitter(
    operation,
    max_attempts=6,
    base_delay=0.2,
    max_delay=5.0,
):
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except TemporaryError:
            if attempt == max_attempts:
                raise

            cap = min(
                max_delay,
                base_delay * (2 ** (attempt - 1)),
            )
            delay = random.uniform(0.0, cap)
            time.sleep(delay)
~~~

TemporaryError là kiểu lỗi giả định trong ví dụ. Ứng dụng phải thay bằng các exception thực tế có thể retry. Không được bắt mọi exception rồi retry, vì lỗi validation, quyền truy cập, cú pháp SQL hoặc dữ liệu sai sẽ không tự biến mất khi chờ.

Mẫu production cần thêm deadline, cancellation, retry budget, phân loại lỗi và bảo vệ idempotency.

## 6. Capped backoff và giới hạn tổng thời gian

Nếu chỉ dùng exponential backoff, thời gian chờ có thể tăng rất lớn. Cần giới hạn bằng \(d_{\max}\).

Ngoài giới hạn từng lần chờ, cần có **deadline tổng**. Ví dụ request có deadline 8 giây. Dù lần retry tiếp theo có backoff hợp lệ 5 giây, nếu chỉ còn 1 giây trước deadline thì không nên ngủ 5 giây rồi gửi request đã hết hạn.

Mẫu quyết định:

~~~text
remaining = deadline - now

if remaining <= 0:
    stop retrying

delay = calculate_backoff_with_jitter(attempt)

if delay >= remaining:
    stop retrying or wait only if policy explicitly allows it

sleep(delay)
call operation with remaining timeout
~~~

Deadline nên được truyền xuyên suốt các tầng gọi. Nếu API gateway có timeout 10 giây nhưng service con tự retry trong 30 giây, công việc phía dưới có thể tiếp tục sau khi caller đã bỏ cuộc.

### Tổng thời gian chờ

Với exponential backoff không jitter, tổng thời gian chờ trước các lần thử có thể tính bằng tổng các \(d_n\). Ví dụ base 200 ms, multiplier 2, cap 5 giây và 6 attempts:

- Trước attempt 2: 0,2 giây.
- Trước attempt 3: 0,4 giây.
- Trước attempt 4: 0,8 giây.
- Trước attempt 5: 1,6 giây.
- Trước attempt 6: 3,2 giây.

Tổng thời gian chờ tối đa trong lịch này là 6,2 giây, chưa tính thời gian thực thi mỗi request. Nếu mỗi lần gọi dịch vụ cũng có timeout 2 giây, tổng thời gian có thể vượt 10 giây. Cần tính cả thời gian chờ lẫn thời gian thực thi.

## 7. Retry budget ngăn retry chiếm hết năng lực hệ thống

Giới hạn số lần retry cho từng request là cần thiết nhưng chưa đủ. Nếu số request ban đầu rất lớn, mỗi request vẫn có thể tạo nhiều lần thử bổ sung.

Retry budget giới hạn lượng tải phát sinh do retry trong một khoảng thời gian. Ví dụ:

- Cho phép tối đa 10% số request ban đầu trở thành retry trong một cửa sổ thời gian.
- Giới hạn số retry đồng thời cho một dependency.
- Dùng token bucket để cấp quota retry.
- Khi budget cạn, trả lỗi hoặc đưa công việc vào hàng đợi thay vì tiếp tục thử.

Một retry budget cần có phạm vi rõ ràng: theo service, dependency, tenant hoặc loại công việc. Nếu mọi instance tự có budget riêng, tổng tải vẫn có thể tăng theo số instance. Có thể cần budget phân tán hoặc giới hạn ở gateway nếu phải kiểm soát toàn hệ thống.

### Ví dụ token bucket

Giả sử bucket có dung lượng 100 token và nạp lại 10 token mỗi giây. Mỗi retry tiêu thụ một token. Khi bucket hết token, request không được retry ngay; ứng dụng trả lỗi có thể retry sau hoặc chuyển công việc sang hàng đợi phù hợp.

Token bucket giúp giới hạn tốc độ retry theo thời gian. Nó khác với max_attempts: max_attempts giới hạn một operation, còn budget giới hạn tổng tải retry của nhiều operation.

## 8. Chỉ retry lỗi tạm thời

Retry chỉ hữu ích nếu lỗi có khả năng biến mất sau một khoảng thời gian. Cần phân loại lỗi trước khi triển khai.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi tạm thời | Connection reset, service unavailable, một số timeout | Có thể retry nếu operation an toàn |
| Xung đột đồng thời | Deadlock, serialization failure | Rollback và retry toàn bộ transaction nếu nghiệp vụ cho phép |
| Giới hạn tải | HTTP 429, throttling | Tuân thủ Retry-After nếu có, kết hợp backoff và jitter |
| Lỗi tạm thời từ server | HTTP 502, 503, 504 | Có thể retry theo chính sách và deadline |
| Lỗi xác thực/quyền | HTTP 401/403, database permission denied | Không retry vô hạn; sửa credential/quyền |
| Lỗi dữ liệu/nghiệp vụ | Validation error, số dư không đủ, unique conflict mang ý nghĩa nghiệp vụ | Trả lỗi hoặc yêu cầu xử lý khác |
| Lỗi lập trình | SQL syntax error, mapping sai, null không hợp lệ | Không retry; sửa code |

Một số mã lỗi có ngữ nghĩa phụ thuộc ngữ cảnh. Ví dụ HTTP 409 có thể là xung đột nghiệp vụ cần người dùng giải quyết, hoặc có thể biểu thị một trạng thái có thể thử lại sau. Không quyết định retry chỉ dựa vào mã HTTP chung; cần dựa vào hợp đồng API.

### Retry-After

Nếu server trả HTTP 429 hoặc 503 cùng header Retry-After, client nên xem đây là tín hiệu thời gian server đề nghị chờ. Giá trị có thể là số giây hoặc một HTTP-date.

Cần:

- Parse đúng định dạng.
- Không retry trước thời điểm server yêu cầu.
- Kết hợp với deadline và retry budget.
- Thêm jitter sau thời gian tối thiểu nếu nhiều client có thể cùng nhận một Retry-After.
- Giới hạn thời gian chờ theo chính sách client và deadline.

Nếu Retry-After dài hơn deadline của request, hãy kết thúc request hiện tại thay vì giữ nó chờ vô ích. Với job nền, có thể đưa công việc trở lại queue với thời điểm chạy sau nếu hệ thống hỗ trợ.

## 9. Retry trong transaction cơ sở dữ liệu

Deadlock và serialization failure là hai ví dụ phổ biến của lỗi có thể retry. Nhưng transaction đã bị hủy phải được chạy lại trong một transaction mới.

Ví dụ chuyển trạng thái một đơn hàng:

~~~sql
BEGIN;

SELECT status
FROM orders
WHERE order_id = 42;

-- Kiểm tra trạng thái hiện tại và các điều kiện nghiệp vụ.

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 42;

INSERT INTO order_events (order_id, event_type)
VALUES (42, 'CONFIRMED');

COMMIT;
~~~

Nếu DBMS trả serialization failure hoặc deadlock, ứng dụng không nên chỉ retry INSERT hoặc UPDATE cuối. Nó cần rollback và chạy lại toàn bộ transaction:

1. Bắt đầu transaction mới.
2. Đọc lại trạng thái đơn hàng.
3. Kiểm tra lại điều kiện nghiệp vụ.
4. Thực hiện cập nhật và ghi event.
5. Commit.

Snapshot mới có thể cho kết quả khác. Ví dụ, request khác đã hủy đơn trong lúc transaction đầu tiên bị hủy. Lần retry phải nhìn thấy trạng thái CANCELLED và không được tiếp tục xác nhận đơn.

### Pseudocode retry transaction

~~~text
for attempt in 1..MAX_ATTEMPTS:
    begin new transaction

    try:
        read current rows
        validate business rules
        apply updates
        write database events
        commit
        return success

    catch retryable database conflict:
        rollback
        if no attempts remain:
            return retryable failure
        sleep(exponential_backoff_with_jitter(attempt))

    catch permanent error:
        rollback
        raise error
~~~

Không được giữ transaction cũ hoặc connection ở trạng thái lỗi trong lúc sleep. Với một số DBMS, transaction đã gặp lỗi không thể tiếp tục câu SQL tiếp theo trước khi rollback.

### Không retry mọi lỗi database

Một số ví dụ:

- PostgreSQL SQLSTATE **40001**: serialization failure, thường retry toàn bộ transaction.
- PostgreSQL SQLSTATE **40P01**: deadlock detected, thường rollback rồi retry transaction.
- MySQL InnoDB error **1213**: deadlock victim, transaction bị rollback; có thể retry.
- SQL Server error **1205**: deadlock victim; có thể retry transaction.
- Oracle **ORA-00060**: deadlock detected; cần xử lý trạng thái transaction theo ngữ nghĩa Oracle.
- Unique constraint violation: thường là xung đột dữ liệu hoặc nghiệp vụ; retry mù có thể lặp lại cùng lỗi.
- Check constraint violation: thường là dữ liệu hoặc logic không hợp lệ; chờ rồi retry không làm điều kiện tự đúng.

Mã lỗi cụ thể và phạm vi rollback phụ thuộc DBMS, driver và cấu hình. Hãy phân loại theo mã lỗi của driver, kiểm tra transaction state và rollback đúng cách.

## 10. Idempotency: điều kiện quan trọng trước khi retry

Một operation idempotent có thể được thực hiện nhiều lần mà kết quả nghiệp vụ tương đương với thực hiện một lần. Ví dụ, đặt trạng thái một resource thành DISABLED có thể idempotent nếu thao tác chỉ đặt trạng thái đích. Nhưng cộng 10 vào số dư không idempotent: gửi lại sẽ cộng thêm lần nữa.

Nếu client timeout sau khi server đã commit, client không biết operation đã thành công hay chưa. Retry có thể thực hiện cùng nghiệp vụ lần thứ hai.

### Dùng idempotency key

Client gửi một mã yêu cầu duy nhất:

~~~http
POST /payments
Idempotency-Key: 7f9b7f0e-...
Content-Type: application/json
~~~

Server lưu key cùng kết quả xử lý. Nếu cùng key được gửi lại:

- Nếu request đã hoàn tất, trả lại kết quả đã lưu.
- Nếu request đang xử lý, trả trạng thái phù hợp hoặc cho client chờ.
- Nếu key được dùng lại với payload khác, từ chối theo hợp đồng API.
- Nếu chưa từng xử lý, thực hiện và lưu kết quả trong cùng cơ chế transaction phù hợp.

Idempotency key cần có phạm vi và thời hạn lưu rõ ràng. Nếu xóa key quá sớm, request cũ có thể được thực hiện lại sau khi record idempotency biến mất.

### Side effect ngoài database

Email, gọi cổng thanh toán hoặc publish message không tự rollback cùng database transaction. Nếu thực hiện side effect rồi transaction bị rollback, retry có thể gửi side effect lần nữa.

Một cách phổ biến là transactional outbox:

1. Trong database transaction, cập nhật dữ liệu nghiệp vụ và ghi một event vào outbox.
2. Commit.
3. Worker đọc outbox và gửi event ra hệ thống ngoài.
4. Worker đánh dấu event đã xử lý theo cách idempotent.

Retry transaction không được gửi email hoặc publish message trực tiếp trước commit nếu muốn tránh side effect trùng hoặc side effect cho dữ liệu chưa commit.

## 11. Tránh retry ở nhiều tầng cùng lúc

Một request có thể đi qua frontend, API gateway, service A, service B, database driver và message broker. Nếu mỗi tầng đều retry nhiều lần, số lần gọi thực tế có thể nhân lên.

Ví dụ, ba tầng mỗi tầng thử tối đa 3 lần có thể tạo đến \(3^3 = 27\) lần gọi ở tầng sâu nhất trong một tình huống xấu.

Nên xác định một tầng chịu trách nhiệm retry cho mỗi loại lỗi. Các tầng khác có thể áp dụng timeout, circuit breaker hoặc truyền lỗi lên thay vì tự retry thêm.

Cần thống nhất:

- Tổng deadline.
- Số lần thử tối đa.
- Retry budget.
- Loại lỗi được retry.
- Idempotency key hoặc operation id.
- Tầng sở hữu logic retry.
- Cách ghi nhận attempt để quan sát.

## 12. Kết hợp backoff với circuit breaker và giới hạn đồng thời

Backoff làm chậm lần thử tiếp theo, nhưng khi dependency lỗi kéo dài, nhiều request mới vẫn tiếp tục đi vào. Circuit breaker có thể tạm dừng gọi dependency khi tỷ lệ lỗi vượt ngưỡng:

- **Closed**: cho phép request đi qua và theo dõi lỗi.
- **Open**: từ chối nhanh hoặc chuyển sang fallback trong thời gian chờ.
- **Half-open**: cho một số request thử nghiệm đi qua để kiểm tra dịch vụ đã phục hồi chưa.

Backoff và jitter hữu ích cho các lần retry khi circuit breaker cho phép thử lại. Giới hạn concurrency hoặc bulkhead giúp một dependency lỗi không chiếm hết thread, connection hoặc worker của các dịch vụ khác.

Không nên để mỗi request retry và ngủ bằng cách giữ một thread quý giá trong thời gian dài nếu hệ thống có thể dùng scheduler hoặc queue để lên lịch lại công việc.

## 13. Cách kiểm thử retry và jitter

Một test tốt phải kiểm tra cả thời điểm retry lẫn tính đúng của operation.

### Test công thức và giới hạn

- Backoff tăng theo hệ số đã cấu hình.
- Giá trị không vượt max_delay.
- Jitter nằm trong khoảng cho phép.
- Attempt cuối không tạo thêm lần chờ không cần thiết.
- Deadline ngăn request tiếp tục khi đã hết thời gian.
- Phép tính không overflow với attempt lớn.

### Test phân tán thời điểm retry

Dùng hàng trăm worker giả lập cùng nhận lỗi tại một thời điểm. Ghi lại thời điểm chúng retry và phân bố theo các bucket thời gian.

So sánh:

- Backoff cố định.
- Exponential backoff không jitter.
- Full jitter.
- Equal jitter hoặc decorrelated jitter.

Kết quả mong đợi là jitter làm giảm đỉnh request tập trung vào một thời điểm. Không cần các thời điểm phân bố hoàn toàn đều; điều cần tránh là một đợt retry đồng loạt.

### Test phân loại lỗi

- Lỗi transient được retry.
- Lỗi validation không retry.
- Lỗi authentication không retry liên tục.
- HTTP 429/503 tuân thủ Retry-After.
- Deadlock/serialization failure retry toàn bộ transaction.
- Unique/check constraint violation được xử lý theo nghiệp vụ.

### Test idempotency và mất kết nối

Mô phỏng trường hợp DB commit thành công nhưng response bị mất. Gửi lại cùng idempotency key và xác nhận không tạo thêm payment, order hoặc side effect.

### Test cancellation

Khi caller hủy request hoặc deadline hết, timer retry phải dừng. Không tiếp tục gửi request nền nếu operation không được phép chạy tiếp.

## 14. Quan sát retry trong production

Retry có thể che giấu lỗi tạm thời, nhưng cũng có thể làm độ trễ tăng và tiêu tốn năng lực. Cần đo:

- Số request ban đầu và số request retry.
- Retry rate theo dependency và endpoint.
- Phân bố attempt count.
- Thời gian chờ backoff thực tế.
- Số lần retry budget cạn.
- Tỷ lệ thành công sau retry.
- Tỷ lệ thất bại sau khi hết attempts.
- Deadline exceeded và cancellation.
- Deadlock/serialization failure của database.
- Độ trễ p50/p95/p99 và throughput.
- Số operation bị thực hiện trùng hoặc idempotency conflict.

Log nên ghi operation/request id, attempt number, loại lỗi, delay được chọn, dependency và kết quả. Không ghi token xác thực, dữ liệu thanh toán hoặc payload nhạy cảm chỉ để chẩn đoán retry.

Nếu retry rate tăng đột ngột, cần điều tra nguyên nhân gốc như dependency quá tải, connection pool cạn, lock contention hoặc timeout cấu hình quá thấp. Tăng max_attempts có thể làm hệ thống tải nặng hơn mà không giải quyết lỗi ban đầu.

## 15. Cấu hình tham khảo và cách chọn

Một cấu hình tham khảo cho request dịch vụ nội bộ có deadline ngắn:

| Tham số | Giá trị minh họa |
|---|---:|
| Số lần thử tối đa (tính cả lần đầu) | 4 |
| Backoff ban đầu | 100 ms |
| Hệ số tăng | 2 |
| Backoff cap | 1 giây |
| Jitter | Full jitter |
| Timeout mỗi lần gọi | 500 ms, điều chỉnh theo dependency |
| Deadline tổng | 3 giây |
| Retry budget | Có giới hạn theo service/dependency |
| Điều kiện retry | Chỉ lỗi transient và operation an toàn |

Đây chỉ là giá trị minh họa. Cần điều chỉnh theo SLA, độ trễ thực tế, thời gian phục hồi của dependency, số lượng client và chi phí một lần gọi.

Với job nền, có thể dùng backoff cap và deadline dài hơn, đồng thời đưa message trở lại queue với thời điểm xử lý tiếp theo thay vì giữ worker ngủ. Với transaction database, retry phải tạo transaction mới và không giữ khóa trong lúc chờ.

## 16. Quy trình thiết kế retry có kiểm soát

1. **Xác định operation**: biết request có thể tạo thay đổi dữ liệu hoặc side effect nào.
2. **Phân loại lỗi**: chỉ retry lỗi transient hoặc xung đột mà hợp đồng cho phép.
3. **Đảm bảo idempotency**: dùng idempotency key, conditional update hoặc cơ chế tương đương.
4. **Chọn backoff**: đặt base delay, multiplier và cap dựa trên SLA.
5. **Thêm jitter**: chọn full/equal/decorrelated jitter và dùng random source phù hợp.
6. **Đặt max attempts và deadline**: tính cả thời gian thực thi và chờ.
7. **Đặt retry budget**: giới hạn tải bổ sung lên dependency.
8. **Chọn một tầng retry**: tránh nhân số lần gọi qua nhiều tầng.
9. **Xử lý cancellation và Retry-After**: tôn trọng tín hiệu từ caller/server.
10. **Kiểm thử và đo lường**: mô phỏng nhiều client, lỗi transient, xung đột DB và response bị mất.

Exponential backoff giúp các lần thử cách nhau ngày càng xa; jitter phân tán thời điểm retry giữa các client. Khi kết hợp hai kỹ thuật với giới hạn attempts, deadline, retry budget và idempotency, ứng dụng có thể phục hồi từ lỗi tạm thời mà không tạo thêm một đợt tải đồng bộ. Với transaction database, nguyên tắc quan trọng là rollback transaction lỗi, chờ bên ngoài transaction và chạy lại toàn bộ logic trên snapshot mới.
