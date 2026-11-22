# Đánh giá chi phí giữa chặn trước, phát hiện xung đột và thực thi lại

Khi nhiều transaction cùng muốn thay đổi dữ liệu, ứng dụng có thể chọn một trong ba cách tiếp cận chính. **Chặn trước** bằng khóa bi quan (*pessimistic locking*) giữ quyền truy cập cần thiết trước khi xử lý. **Phát hiện xung đột** bằng kiểm soát lạc quan (*optimistic concurrency control*) cho phép các transaction làm việc song song rồi kiểm tra xem dữ liệu có còn ở phiên bản đã đọc khi ghi hay không. **Thực thi lại** (*retry*) là chính sách phục hồi sau khi một attempt thất bại vì xung đột tạm thời.

Ba cách này không hoàn toàn loại trừ nhau. Optimistic locking thường cần retry hoặc trả conflict khi version không khớp; pessimistic locking cũng có thể gặp deadlock hoặc lock timeout và cần retry. Câu hỏi thiết kế thực tế là: nên trả chi phí ở đâu và vào lúc nào? Chờ khóa trước khi làm việc, phát hiện xung đột sau khi đã tính toán, hay bỏ attempt hiện tại và thực hiện lại toàn bộ transaction?

Không có lựa chọn tốt nhất cho mọi workload. Quyết định phụ thuộc vào xác suất tranh chấp trên cùng dữ liệu, thời gian giữ khóa, chi phí tính toán trước khi ghi, độ dài transaction, mức độ trễ mà caller chấp nhận và khả năng thực hiện lại thao tác an toàn.

## 1. Ba chiến lược và nơi chúng trả chi phí

### Chặn trước: lấy khóa rồi mới làm việc

Với khóa bi quan, transaction xin khóa trên hàng hoặc phạm vi dữ liệu trước khi thực hiện phần công việc cần được bảo vệ:

```sql
BEGIN;

SELECT balance
FROM accounts
WHERE id = :accountId
FOR UPDATE;

-- Kiểm tra điều kiện và tính toán khi đang giữ khóa.
UPDATE accounts
SET balance = balance - :amount
WHERE id = :accountId;

COMMIT;
```

Transaction khác muốn cập nhật cùng hàng thường phải chờ. Chi phí được trả sớm dưới dạng thời gian chờ khóa và thời gian giữ khóa. Đổi lại, transaction không phải làm một phần lớn công việc dựa trên dữ liệu cũ rồi mới phát hiện nó đã bị thay đổi.

### Phát hiện xung đột: làm việc trước, kiểm tra khi ghi

Với optimistic locking, transaction đọc dữ liệu cùng version, thực hiện tính toán trong ứng dụng, rồi cập nhật có điều kiện:

```sql
UPDATE accounts
SET balance = :newBalance,
    version = version + 1
WHERE id = :accountId
  AND version = :expectedVersion;
```

Nếu một hàng được cập nhật, version khớp và thao tác đã thắng. Nếu không có hàng nào được cập nhật, dữ liệu đã thay đổi hoặc hàng không còn thỏa điều kiện. Transaction không giữ khóa độc quyền suốt thời gian người dùng hoặc ứng dụng tính toán; chi phí xuất hiện khi xung đột được phát hiện và phần công việc đã làm có thể phải bỏ.

### Thực thi lại: phục hồi sau một attempt thất bại

Retry không phải một cơ chế khóa riêng. Nó là chính sách chạy lại logic sau deadlock, serialization failure, optimistic conflict hoặc lỗi tạm thời khác:

```text
BEGIN transaction mới
  đọc trạng thái mới nhất
  kiểm tra lại điều kiện nghiệp vụ
  tính lại kết quả
  ghi thay đổi
COMMIT
```

Retry có thể kết hợp với optimistic hoặc pessimistic control. Nhưng retry phải bắt đầu từ transaction mới khi transaction cũ đã rollback hoặc bị đánh dấu không thể commit; không chỉ chạy lại câu SQL cuối với giá trị đã tính từ snapshot cũ.

### Bảng so sánh ban đầu

| Chiến lược | Chi phí chính | Lợi ích chính | Rủi ro chính |
|---|---|---|---|
| Pessimistic locking | Chờ khóa, giữ khóa, giảm mức song song trên dữ liệu nóng | Tránh nhiều transaction cùng làm phần cập nhật xung đột | Blocking, deadlock, transaction dài giữ tài nguyên |
| Optimistic detection | Đọc version, kiểm tra khi ghi, bỏ công việc của attempt thua | Cho phép nhiều công việc độc lập tiến triển song song | Conflict rate cao làm lãng phí CPU và tăng số lần thất bại |
| Retry | Chạy lại logic, đọc lại dữ liệu, backoff và tiêu thụ thêm tài nguyên | Phục hồi tự động sau xung đột tạm thời | Retry storm, latency tăng, tác dụng phụ bị lặp nếu không idempotent |

## 2. Mô hình hóa chi phí của một transaction

Để so sánh công bằng, cần nhìn toàn bộ vòng đời của một logical operation thay vì chỉ đo thời gian câu `UPDATE`.

Một logical operation có thể tiêu tốn:

- Thời gian chờ lấy connection từ pool.
- Thời gian đọc dữ liệu và tạo snapshot.
- CPU để tính toán trong ứng dụng.
- Thời gian chờ khóa hoặc chờ transaction khác.
- Thời gian thực thi câu lệnh và duy trì index/constraint.
- Thời gian rollback khi attempt thất bại.
- Thời gian backoff trước lần thử lại.
- Thời gian đọc lại và tính toán lại ở attempt sau.
- Chi phí log, trace, retry coordination và xử lý lỗi.

Có thể chia chi phí thành hai nhóm:

1. **Chi phí hữu ích:** công việc cần thiết để tạo ra kết quả nghiệp vụ cuối cùng.
2. **Chi phí cạnh tranh/phục hồi:** chờ khóa, công việc bị bỏ, rollback, retry, backoff và điều phối bổ sung.

Một chiến lược có thể giảm một nhóm nhưng tăng nhóm kia. Ví dụ, lấy khóa trước làm giảm khả năng phải tính lại nhưng làm các transaction khác chờ lâu hơn. Optimistic locking giảm blocking trong lúc tính toán nhưng có thể khiến một transaction phải bỏ toàn bộ công việc đã làm.

### Các biến quan trọng

Để phân tích, ký hiệu:

| Ký hiệu | Ý nghĩa |
|---|---|
| `T` | Thời gian xử lý hữu ích của một attempt nếu không có tranh chấp. |
| `H` | Thời gian giữ khóa trên tài nguyên xung đột. |
| `p` | Xác suất một attempt gặp xung đột làm attempt không thể hoàn tất theo cách dự kiến. |
| `Cw` | Chi phí công việc đã làm nhưng bị bỏ khi attempt thất bại. |
| `Cr` | Chi phí khởi tạo và thực hiện lại một attempt, ngoài phần công việc hữu ích. |
| `B` | Thời gian backoff giữa các attempt. |
| `D` | Deadline tổng của logical operation. |
| `λ` | Tốc độ transaction đến trên một tài nguyên hoặc nhóm tài nguyên. |

Các biến này chỉ là mô hình tư duy. `p` không cố định trong mọi tải; khi số worker tăng hoặc một hàng trở nên nóng, xác suất xung đột có thể tăng theo chính mức tải và chiến lược đang dùng.

## 3. Chi phí của chặn trước bằng khóa bi quan

### Chờ trước khi thực hiện phần công việc cần khóa

Khi transaction yêu cầu khóa độc quyền mà transaction khác đang giữ, nó phải chờ. Nếu hàng được truy cập thường xuyên, các request có thể xếp hàng phía sau nhau.

Ví dụ, 10 worker cùng cập nhật một hàng tồn kho. Nếu mỗi transaction giữ khóa `20 ms`, các cập nhật trên hàng đó về cơ bản phải được tuần tự hóa. Transaction đầu có thể hoàn tất nhanh, nhưng các transaction sau chờ lâu hơn. Nếu một transaction giữ khóa `2 giây` vì gọi dịch vụ ngoài hoặc thực hiện tính toán dài, hàng đợi có thể tăng rất nhanh.

### Thời gian giữ khóa quyết định khả năng phục vụ

Với một tài nguyên bị tuần tự hóa hoàn toàn và thời gian giữ khóa trung bình là `H`, giới hạn lý thuyết thô của số lần cập nhật hoàn tất trên tài nguyên đó xấp xỉ:

\[
throughput_{max} \approx \frac{1}{H}
\]

Nếu `H = 20 ms`, giới hạn thô khoảng 50 lượt cập nhật/giây trên tài nguyên đó. Nếu `H = 200 ms`, con số giảm còn khoảng 5 lượt/giây. Đây không phải dự báo chính xác cho một database; engine còn có scheduling, group commit, nhiều khóa, CPU, I/O và khả năng xử lý song song. Công thức chỉ cho thấy việc kéo dài critical section có thể trực tiếp giảm throughput của một điểm nóng.

### Chi phí của hàng đợi và tail latency

Khi request đến nhanh hơn tốc độ một hàng nóng được giải phóng, hàng đợi tăng. Thời gian chờ trung bình có thể còn chấp nhận được trong lúc tải thấp, nhưng p95/p99 latency thường tăng mạnh khi hệ thống tiến gần giới hạn phục vụ.

Một transaction bị chặn cũng có thể giữ connection, snapshot hoặc các khóa khác đã lấy trước đó. Vì thế, blocking trên một hàng có thể lan sang các tài nguyên khác, làm tăng nguy cơ deadlock và pool exhaustion.

### Deadlock và chi phí victim

Pessimistic locking không loại bỏ deadlock. Nếu hai transaction lấy nhiều khóa theo thứ tự khác nhau, database có thể phát hiện chu trình và rollback một victim. Công việc của victim bị bỏ, ứng dụng có thể phải retry và toàn bộ transaction vẫn tiêu tốn tài nguyên trước khi thất bại.

Do đó, chi phí của khóa bi quan gồm cả thời gian chờ bình thường và chi phí phục hồi khi deadlock/timeout. Thống nhất thứ tự khóa, lấy đúng phạm vi, giữ transaction ngắn và tránh gọi dịch vụ ngoài trong lúc giữ khóa giúp giảm các chi phí này.

## 4. Chi phí của phát hiện xung đột lạc quan

### Đọc và tính toán không cần giữ khóa ghi dài hạn

Optimistic control phù hợp khi phần lớn transaction không đụng cùng dữ liệu. Nhiều client có thể đọc và tính toán song song. Chỉ ở thời điểm ghi, database mới kiểm tra version hoặc điều kiện compare-and-set.

Nếu xung đột hiếm, đa số attempt thành công ngay. Ứng dụng tránh được việc giữ khóa trong lúc người dùng chỉnh sửa hoặc trong khi tính toán kéo dài.

### Chi phí của attempt thua

Khi version không khớp, transaction có thể đã:

- Đọc nhiều hàng.
- Tính toán trong CPU.
- Gọi các hàm nghiệp vụ.
- Xây dựng payload hoặc kết quả trung gian.
- Thực hiện một số câu lệnh trong transaction trước khi conflict được phát hiện.

Nếu attempt bị rollback, phần công việc đó có thể phải làm lại. Chi phí `Cw` càng cao thì optimistic approach càng đắt khi conflict rate tăng.

Ví dụ, một màn hình chỉnh sửa tài liệu được mở trong 15 phút. Giữ khóa độc quyền suốt thời gian đó là không hợp lý; optimistic version phù hợp vì người dùng chỉ cần biết bản tài liệu đã đổi khi bấm lưu. Ngược lại, một thuật toán tính toán rất nặng trên một hàng nóng rồi chỉ kiểm tra version ở cuối có thể lãng phí nhiều CPU khi nhiều worker cùng tranh chấp.

### Conflict không nhất thiết là lỗi hệ thống

Một cập nhật có điều kiện ảnh hưởng `0` hàng có thể là kết quả nghiệp vụ bình thường: người khác đã sửa tài liệu, job đã được worker khác claim hoặc đơn hàng đã chuyển trạng thái. Hệ thống cần đo conflict riêng với lỗi database bất ngờ.

Không nên ghi mọi `row count = 0` thành exception nghiêm trọng. Hãy phân biệt:

- Conflict version có thể yêu cầu người dùng tải lại hoặc merge.
- Trạng thái nguồn không còn hợp lệ là kết quả nghiệp vụ.
- Hàng không tồn tại là not found.
- Điều kiện quyền hoặc phạm vi tenant không còn đúng là kết quả bảo mật/ủy quyền.

### Phạm vi version ảnh hưởng tỷ lệ conflict

Nếu một version ở cấp hàng tăng khi bất kỳ trường nào thay đổi, hai người sửa hai trường độc lập vẫn có thể xung đột. Điều đó đơn giản hóa bảo vệ nhưng làm tăng false conflict theo ý nghĩa nghiệp vụ.

Có thể dùng version theo aggregate, theo hàng hoặc theo phần dữ liệu, nhưng phạm vi càng nhỏ thì logic merge và bảo vệ bất biến càng phức tạp. Chỉ giảm phạm vi version khi có thể chứng minh các thay đổi độc lập và vẫn bảo vệ được các ràng buộc liên quan.

## 5. Chi phí của retry

Retry biến một attempt thất bại thành cơ hội hoàn thành logical operation, nhưng mỗi lần retry tạo thêm công việc.

Chi phí bao gồm:

- Rollback và giải phóng khóa của attempt trước.
- Mượn connection và mở transaction mới.
- Đọc lại dữ liệu và kiểm tra điều kiện.
- Tính toán lại kết quả.
- Thời gian backoff và jitter.
- Tăng latency end-to-end.
- Tăng số transaction attempts trên database.
- Nguy cơ lặp tác dụng phụ nếu thao tác không idempotent.

### Số attempt kỳ vọng trong mô hình đơn giản

Giả sử mỗi attempt độc lập có xác suất thất bại `p`, retry không giới hạn và mỗi attempt có cùng phân phối. Khi đó số attempt kỳ vọng cho đến lần thành công đầu tiên là:

\[
E[A] = \frac{1}{1-p}
\]

Ví dụ:

| Xác suất conflict `p` | Số attempt kỳ vọng `E[A]` |
|---:|---:|
| 1% | 1,010 |
| 5% | 1,053 |
| 10% | 1,111 |
| 20% | 1,250 |
| 40% | 1,667 |
| 60% | 2,500 |

Đây chỉ là mô hình toán học đơn giản, không phải dự báo trực tiếp cho workload thực. Xung đột trong database thường không độc lập: retry ngay có thể gặp lại cùng transaction khác, và tải tăng làm `p` tăng. Với số attempt bị giới hạn, xác suất thành công trong tối đa `N` attempt theo mô hình độc lập là:

\[
P(success\ within\ N) = 1 - p^N
\]

Nếu `p = 0,2` và `N = 3`, xác suất thành công trong tối đa ba attempt là `1 - 0,2^3 = 99,2%`. Tuy nhiên, phép tính không bao gồm deadline, backoff, lỗi không retry được, tải phụ hoặc kết quả commit không xác định.

### Retry có thể khuếch đại tải

Nếu nhiều request cùng thất bại và retry ngay, chúng có thể quay lại đúng hàng nóng cùng lúc. Số attempt tăng, connection pool bị sử dụng nhiều hơn và database nhận thêm công việc trong lúc đang quá tải. Đây là retry storm.

Để hạn chế:

- Giới hạn `maxAttempts` và deadline tổng.
- Dùng exponential backoff có jitter.
- Không retry lỗi validation/constraint/permanent failure.
- Retry toàn bộ transaction trong transaction mới.
- Chọn một tầng sở hữu retry cho từng lỗi để tránh nhân attempt qua nhiều tầng.
- Cân nhắc retry budget hoặc circuit breaker khi dependency quá tải.

## 6. So sánh chi phí theo xác suất xung đột

Một cách định tính:

| Mức tranh chấp | Pessimistic locking | Optimistic detection | Retry |
|---|---|---|---|
| Rất thấp | Có thể trả chi phí lấy khóa dù gần như không có ai tranh chấp | Thường hiệu quả: phần lớn attempt thành công ngay | Ít được kích hoạt, chi phí nhỏ |
| Thấp đến vừa | Có thể phù hợp nếu cần bảo vệ trạng thái trong suốt transaction | Thường vẫn hiệu quả nếu công việc bị bỏ không quá đắt | Retry có giới hạn xử lý các conflict hiếm |
| Cao trên cùng hàng | Hàng đợi và tail latency tăng; critical section phải rất ngắn | Nhiều attempt thua, lãng phí công việc và CPU | Có thể khuếch đại tải nếu tiếp tục retry cùng điểm nóng |
| Cao nhưng trên các hàng độc lập | Khóa theo hàng có thể vẫn song song tốt | Optimistic thường cũng hoạt động tốt | Ít retry nếu key phân tán |
| Người dùng chỉnh sửa lâu | Giữ khóa suốt thời gian chỉnh sửa rất tốn kém | Rất phù hợp để phát hiện bản đọc cũ lúc lưu | Chỉ dùng khi có thể tự áp dụng lại hoặc merge |
| Công việc nặng trước khi ghi | Khóa sớm có thể giữ tài nguyên lâu | Conflict muộn có thể làm mất nhiều công việc | Retry toàn bộ có thể rất đắt |

Điểm quan trọng là **tần suất xung đột trên cùng tài nguyên**, không chỉ tổng số transaction. Một triệu transaction trên một triệu account khác nhau có thể ít cạnh tranh hơn một nghìn transaction cùng cập nhật một tài khoản nóng.

## 7. So sánh theo thời gian giữ khóa và chi phí công việc bị bỏ

Hai workload có cùng conflict rate vẫn có thể cần chiến lược khác nhau.

### Trường hợp A: công việc ngắn, critical section nhỏ

Một transaction chỉ đọc một hàng, kiểm tra trạng thái rồi cập nhật trong vài mili giây. Pessimistic lock có thể là lựa chọn hợp lý nếu tranh chấp thường xuyên và cần bảo vệ một quyết định không thể thực hiện lại dễ dàng. Thời gian giữ khóa nhỏ nên chi phí blocking có thể chấp nhận được.

### Trường hợp B: người dùng chỉnh sửa dữ liệu trong thời gian dài

Một người dùng mở hồ sơ, thay đổi nhiều trường và bấm lưu sau vài phút. Giữ khóa database trong toàn bộ thời gian đó sẽ chiếm tài nguyên và làm người khác chờ. Optimistic version phù hợp: tải version khi mở, kiểm tra lại khi lưu, rồi báo conflict hoặc merge nếu version đã đổi.

### Trường hợp C: tính toán nặng, xung đột thường xuyên

Một worker tính mô hình hoặc xử lý batch trong nhiều giây rồi mới cập nhật một hàng nóng. Optimistic locking có thể khiến nhiều worker lãng phí CPU khi chỉ một worker ghi thành công. Có thể chuyển phần claim/điều phối sang khóa bi quan ngắn, hàng queue hoặc phân vùng theo key để tránh cùng làm một công việc.

### Trường hợp D: xung đột hiếm nhưng có thể retry an toàn

Một giao dịch cập nhật dữ liệu ít cạnh tranh, có thể tính lại nhanh và không phát tác dụng phụ trước commit. Optimistic control cộng bounded retry thường đơn giản và có hiệu năng tốt.

## 8. Mô hình chi phí kỳ vọng để so sánh

Không có công thức tổng quát dự báo chính xác hiệu năng database, nhưng có thể xây dựng mô hình đơn giản để định hướng đo lường.

### Optimistic control với retry

Giả sử:

- `T` là thời gian một attempt nếu không conflict.
- `p` là xác suất attempt conflict.
- `Cw` là phần chi phí đã tiêu tốn trước khi conflict được phát hiện.
- `B` là backoff trung bình trước retry.
- Retry độc lập và không giới hạn trong mô hình lý thuyết.

Chi phí thời gian kỳ vọng có thể hình dung là:

\[
E[C_{opt}] \approx \frac{T + p(C_w + B)}{1-p}
\]

Đây là mô hình gần đúng để nhấn mạnh ba yếu tố: attempt càng dài, conflict càng thường xuyên và công việc bị bỏ càng lớn thì optimistic + retry càng đắt. Trong hệ thống thật, `p`, `Cw` và `B` thay đổi theo tải; số attempt có giới hạn và có thể có lỗi permanent.

### Pessimistic locking

Với khóa bi quan, một transaction có thể phải chờ trước khi vào critical section. Chi phí kỳ vọng gồm:

\[
E[C_{pess}] \approx T + E[W_{lock}] + C_{lock\ overhead}
\]

Trong đó `W_lock` là thời gian chờ khóa. Công thức không thể hiện đầy đủ ảnh hưởng hàng đợi đến các request khác, deadlock victim hoặc việc transaction giữ nhiều khóa. Nó cho thấy khóa bi quan chuyển chi phí sang chờ và giảm mức song song trên tài nguyên nóng.

### Không dùng công thức để thay thế benchmark

Các mô hình trên giả định đơn giản hóa. Trong thực tế:

- Conflict probability phụ thuộc số worker, phân bố key và thời gian transaction.
- Lock wait có phân phối lệch; p99 có thể lớn hơn trung bình rất nhiều.
- Deadlock victim tạo rollback và retry không giống một conflict version đơn giản.
- Database có thể dùng MVCC, row locks, predicate locks hoặc range locks khác nhau.
- Pool, CPU, I/O và network có thể là nút thắt trước khi lock contention xuất hiện.
- Retry có thể thay đổi tải và làm xác suất conflict tăng thêm.

Hãy dùng mô hình để đặt giả thuyết, sau đó đo trên workload đại diện.

## 9. Chi phí không chỉ là thời gian của một transaction

Một chiến lược có thể làm một request nhanh hơn nhưng làm throughput toàn hệ thống thấp hơn. Cần xem chi phí ở ba phạm vi:

### Latency của một logical operation

Đo từ lúc request bắt đầu đến khi trả kết quả cuối, bao gồm pool wait, lock wait, mọi attempt, backoff và xử lý response. Không chỉ đo thời gian statement cuối cùng.

### Throughput của tài nguyên nóng

Đếm số cập nhật hoàn tất trên một hàng/aggregate hoặc một partition trong một giây. Nếu khóa bi quan tuần tự hóa một hàng, throughput của key đó bị giới hạn bởi thời gian giữ khóa. Nếu optimistic retry làm nhiều attempt thua, database có thể tiêu thụ CPU cho các lần cập nhật bị từ chối.

### Hiệu suất toàn hệ thống

Theo dõi:

- Throughput request thành công.
- CPU database và application.
- Connection pool active/pending và acquisition latency.
- Số transaction attempts trên mỗi logical operation.
- Lock wait và transaction duration.
- Rollback, deadlock và serialization failure rate.
- p50/p95/p99 latency và deadline exhaustion.
- I/O và log/redo generation nếu workload ghi nhiều.

Một hệ thống có success rate 99,99% nhờ retry vẫn có thể đang sử dụng gấp đôi CPU và connection so với trước khi contention tăng. Chỉ nhìn lỗi cuối cùng sẽ bỏ sót chi phí đó.

## 10. Chọn chiến lược theo dạng workload

### Workload đọc nhiều, ghi ít

Nếu nhiều transaction chỉ đọc và số ghi tương đối ít, MVCC và optimistic approach thường phù hợp. Reader không cần giữ khóa ghi; writer kiểm tra xung đột khi cập nhật. Pessimistic lock trên các thao tác đọc thông thường có thể tạo blocking không cần thiết.

### Workload ghi nhiều nhưng key phân tán

Nếu mỗi transaction cập nhật các account hoặc aggregate khác nhau, contention có thể thấp dù tổng throughput cao. Optimistic locking hoặc cập nhật nguyên tử thường hoạt động tốt. Khóa bi quan theo từng hàng cũng có thể hiệu quả nếu critical section ngắn.

### Workload có một vài key nóng

Nếu nhiều transaction liên tục cập nhật cùng một tài khoản, bộ đếm hoặc tồn kho, cả hai chiến lược đều có chi phí:

- Pessimistic: xếp hàng trên khóa của key nóng.
- Optimistic: nhiều transaction có thể cùng tính toán nhưng chỉ một số ít commit; attempt thua cần retry hoặc từ chối.

Trong trường hợp này, cân nhắc thay đổi mô hình:

- Shard hoặc phân vùng dữ liệu theo key nếu nghiệp vụ cho phép.
- Dùng câu cập nhật nguyên tử như `counter = counter + delta`.
- Gom nhiều thay đổi thành batch.
- Dùng hàng đợi để tuần tự hóa có chủ đích theo aggregate.
- Tạo một hàng điều phối hoặc actor sở hữu key nóng.
- Giảm số lần cập nhật cùng một hàng bằng cách lưu sự kiện rồi tổng hợp.

Đổi thuật toán khóa mà không giải quyết hotspot có thể chỉ chuyển chi phí từ lock wait sang retry.

### Quy trình người dùng tương tác lâu

Dùng optimistic version/ETag để phát hiện bản đọc cũ khi lưu. Không giữ transaction hoặc connection trong suốt thời gian người dùng mở biểu mẫu. Nếu conflict, hiển thị khác biệt hoặc yêu cầu tải lại.

### Claim job hoặc tài nguyên khan hiếm

Nếu chỉ một worker được phép nhận một job, locking read ngắn như `FOR UPDATE SKIP LOCKED` hoặc conditional update có thể phù hợp. Worker claim và commit nhanh, sau đó xử lý job ngoài transaction. Không giữ khóa database trong suốt công việc dài.

### Giao dịch tài chính hoặc bất biến nghiêm ngặt

Chọn cơ chế dựa trên bất biến và semantics cần bảo vệ, không chỉ benchmark throughput. Dùng conditional update, unique/check constraints, khóa hoặc Serializable khi cần. Retry toàn transaction nếu lỗi tạm thời; đảm bảo idempotency cho tác dụng phụ và không chấp nhận một kết quả chỉ vì nó nhanh.

## 11. Kết hợp các chiến lược thay vì chọn một cho toàn hệ thống

Một ứng dụng có thể dùng các chiến lược khác nhau cho từng thao tác:

| Thao tác | Cách tiếp cận có thể phù hợp |
|---|---|
| Người dùng sửa hồ sơ trong nhiều phút | Optimistic version, conflict UI hoặc merge |
| Trừ tồn kho | Conditional atomic update, constraint và transaction |
| Worker nhận job | Pessimistic claim ngắn hoặc compare-and-set |
| Bộ đếm tăng/giảm | Atomic arithmetic update hoặc event aggregation |
| Chuyển tiền giữa hai tài khoản | Transaction nguyên tử, khóa theo thứ tự ổn định hoặc conditional update; retry lỗi tạm thời |
| Cập nhật cấu hình ít tranh chấp | Optimistic version |
| Ghi dữ liệu nhiều bảng có critical section ngắn | Transaction với khóa cần thiết và thứ tự truy cập nhất quán |

Một mẫu hybrid phổ biến:

1. Dùng optimistic check để tránh khóa dài trong phần tính toán.
2. Khi bước cuối cần bảo vệ một tài nguyên nóng, lấy khóa ngắn hoặc dùng atomic conditional update.
3. Nếu database báo deadlock/serialization conflict, rollback toàn bộ transaction.
4. Retry có giới hạn, đọc lại dữ liệu và tính lại.
5. Nếu xung đột tiếp tục, trả conflict hoặc chuyển công việc sang queue theo key.

Không cần ép mọi thao tác qua cùng một abstraction nếu yêu cầu concurrency khác nhau. Tuy nhiên, cần ghi rõ bất biến được bảo vệ và quyền sở hữu retry để các tầng không thực hiện lại cùng một thao tác nhiều lần.

## 12. Những điều kiện làm thay đổi chi phí

### Thời gian phát hiện xung đột

Optimistic conflict được phát hiện càng muộn, chi phí công việc bị bỏ càng lớn. Nếu có thể kiểm tra version sớm trước một phép tính nặng, có thể giảm công việc lãng phí; nhưng lần kiểm tra sớm không thay thế điều kiện version nguyên tử ở câu ghi cuối cùng.

### Granularity của khóa và version

Khóa quá rộng làm nhiều transaction không liên quan phải chờ. Version quá rộng làm nhiều chỉnh sửa độc lập bị conflict. Thu hẹp phạm vi có thể tăng concurrency nhưng làm logic bảo vệ bất biến phức tạp hơn.

### Thời gian giữ transaction

Transaction càng dài, khóa càng bị giữ lâu, snapshot càng tồn tại lâu và khả năng xung đột càng cao. Chuẩn bị dữ liệu trước, không gọi HTTP trong transaction, commit sớm và chỉ giữ tài nguyên cần thiết.

### Isolation level

Isolation level cao hơn có thể phát hiện thêm các xung đột hoặc buộc transaction retry để bảo vệ tính tuần tự hóa. Không nên giảm isolation chỉ để giảm lỗi nếu bất biến nghiệp vụ cần semantics mạnh hơn. So sánh phải giữ cùng yêu cầu nhất quán.

### Index và phạm vi truy vấn

Index phù hợp có thể giảm số hàng phải quét và phạm vi khóa. Nhưng index phụ làm tăng chi phí ghi và có thể thêm tài nguyên khóa. Benchmark cần giữ schema/index tương đương production.

### Phân bố key

Uniform distribution thường ít hotspot hơn phân bố lệch. Một workload tổng thể có tỷ lệ conflict thấp vẫn có thể có một vài aggregate chịu tranh chấp rất cao. Đo theo operation và key group đã chuẩn hóa, không chỉ tổng toàn database.

## 13. Cách đo để ra quyết định

Không nên chọn pessimistic hay optimistic chỉ từ lý thuyết. Hãy tạo benchmark đại diện cho workload và đo các chỉ số ở cùng điều kiện.

### Chuẩn bị workload

Ghi rõ:

- Số worker/client đồng thời.
- Tỷ lệ đọc/ghi.
- Phân bố key: đều hay có hotspot.
- Số hàng và index được truy cập mỗi transaction.
- Thời gian tính toán trước khi ghi.
- Thời gian critical section và transaction duration.
- Isolation level và database engine/version.
- Pool size, CPU, I/O và network.
- Mức độ retry, max attempts và deadline.

Chạy ít nhất các kịch bản:

1. Không tranh chấp hoặc key phân tán.
2. Tranh chấp vừa trên một nhóm key.
3. Hot key với nhiều worker cùng cập nhật.
4. Transaction ngắn và transaction có phần tính toán dài.
5. Tải tăng dần để tìm điểm throughput bắt đầu suy giảm.

### Metric cần so sánh

| Nhóm | Chỉ số |
|---|---|
| Throughput | Logical operations thành công/giây, transaction attempts/giây |
| Latency | p50/p95/p99 end-to-end, lock wait, thời gian attempt, backoff |
| Contention | Deadlock, serialization failure, optimistic conflict, lock timeout |
| Retry | Retry rate, attempts/logical operation, recovery rate, exhaustion |
| Tài nguyên | CPU database/app, active/pending connections, I/O, memory |
| Đúng đắn | Invariant sau test, số cập nhật mất, duplicate side effect, trạng thái cuối |

### Giữ điều kiện so sánh công bằng

- Dùng cùng database engine, schema, index và dữ liệu.
- Giữ cùng isolation semantics hoặc giải thích rõ khác biệt.
- Dùng cùng số worker và phân bố key.
- Tách warm-up khỏi thời gian đo.
- Chạy đủ lâu để quan sát tail latency và hàng đợi ổn định.
- Đo cả logical operation lẫn attempt.
- Xác nhận không có connection leak hoặc transaction còn mở từ lượt trước.
- Chạy lặp lại và báo độ biến thiên, không chỉ lấy một lần tốt nhất.

Không so sánh một phương án dùng retry vô hạn với một phương án có deadline ngắn rồi kết luận throughput cao hơn là tốt hơn. Cùng một logical operation phải có deadline và hợp đồng thành công tương đương.

## 14. Ví dụ benchmark: một hàng nóng

Giả sử 50 worker cùng tăng một bộ đếm. Có hai cách:

### Cách A: đọc rồi ghi với optimistic version

```sql
SELECT counter_value, version
FROM counters
WHERE id = 1;

UPDATE counters
SET counter_value = :oldValue + 1,
    version = version + 1
WHERE id = 1
  AND version = :expectedVersion;
```

Nếu nhiều worker cùng đọc một version, chỉ một số ít cập nhật thành công. Các worker thua phải đọc lại và retry hoặc bỏ thao tác. Khi hotspot tăng, số attempt trên mỗi lần tăng thành công có thể tăng mạnh.

### Cách B: cập nhật nguyên tử

```sql
UPDATE counters
SET counter_value = counter_value + 1
WHERE id = 1;
```

Database vẫn phải tuần tự hóa các ghi trên cùng hàng và có thể tạo lock wait, nhưng mỗi statement biểu diễn ý định tăng tương đối. Ứng dụng không phải đọc một snapshot cũ rồi thử lại vì version thay đổi. Nếu thao tác chỉ là tăng bộ đếm, cách này thường đơn giản và ít lãng phí hơn.

### Cách C: khóa trước khi đọc và cập nhật

```sql
BEGIN;

SELECT counter_value
FROM counters
WHERE id = 1
FOR UPDATE;

UPDATE counters
SET counter_value = counter_value + 1
WHERE id = 1;

COMMIT;
```

Các transaction xếp hàng trước khi đọc và cập nhật. Không có nhiều worker cùng tính từ một version cũ, nhưng throughput của key vẫn bị giới hạn bởi thời gian giữ khóa. Với một phép tăng đơn giản, conditional/atomic update có thể có ít round trip và ít code hơn.

Benchmark phải xác nhận kết quả cuối là `initial + successful increments`, sau đó so sánh latency và throughput. Không chỉ đếm số conflict: phương án B có thể có lock waits nhưng không có optimistic version conflict; đó là hai loại chi phí khác nhau.

## 15. Ví dụ benchmark: tài liệu được nhiều người chỉnh sửa

Giả sử 100 người dùng có thể mở cùng một tài liệu, nhưng chỉ một tỷ lệ nhỏ lưu thay đổi trong cùng thời điểm.

### Khóa bi quan dài hạn

Nếu mỗi người giữ khóa khi mở tài liệu và chỉ nhả khi bấm lưu hoặc đóng màn hình, người dùng khác có thể phải chờ hàng phút. Connection và transaction bị giữ lâu, không phù hợp với mô hình tương tác này.

### Optimistic version

Mỗi người đọc version `7`. Người đầu tiên lưu thành version `8`; người thứ hai lưu với expected version `7` nhận conflict. Ứng dụng có thể tải bản mới, hiển thị diff và yêu cầu người dùng chọn cách gộp.

Ở đây, chi phí một conflict là công việc người dùng phải xem lại và có thể chỉnh sửa lại. Đổi lại, phần lớn thời gian đọc/chỉnh sửa không giữ database lock. Đây thường là tradeoff phù hợp hơn cho dữ liệu tương tác lâu.

### Retry tự động có thể không phù hợp

Nếu nội dung là văn bản tự do, gửi lại payload cũ sau khi version mismatch có thể ghi đè nội dung người khác. Retry an toàn cần merge ba chiều hoặc áp dụng lại ý định có thể diễn đạt rõ. Nếu không có quy tắc merge, trả conflict cho người dùng tốt hơn tự động retry mù.

## 16. Quy tắc retry ảnh hưởng kết quả so sánh

Khi benchmark optimistic control, phải xác định rõ chính sách sau conflict:

- **Không retry:** trả conflict ngay. Latency và tải database thấp hơn nhưng tỷ lệ lỗi caller có thể cao hơn.
- **Retry một số lần:** đọc lại và tính lại trong giới hạn. Tăng khả năng thành công nhưng thêm latency và attempts.
- **Merge:** kết hợp thay đổi nếu có thể chứng minh không xung đột về ý nghĩa. Có thể giảm yêu cầu người dùng làm lại nhưng tốn CPU và logic.
- **Chuyển queue theo key:** tuần tự hóa công việc nóng ở một worker hoặc partition. Có thể tăng độ trễ chờ queue nhưng giảm retry lặp.

Với pessimistic locking, cũng cần chính sách khi lock timeout hoặc deadlock. Một transaction chờ khóa quá deadline phải trả lỗi hoặc được retry theo giới hạn; không giữ request vô hạn.

### Retry phải tính cả chi phí của attempt thất bại

Nếu một operation mất `200 ms` để tính toán rồi conflict ở câu update cuối, retry hai lần có thể tốn gần `600 ms` cộng backoff. Nếu lấy khóa trước và chỉ một transaction làm phần tính toán sau khi có khóa, tổng CPU có thể thấp hơn nhưng những transaction khác chờ lâu hơn.

So sánh đúng phải đo cả CPU, lock wait, transaction duration và end-to-end latency. Không thể kết luận từ thời gian câu `UPDATE` đơn lẻ.

## 17. Tính an toàn của retry và tác dụng phụ

Retry chỉ hợp lệ khi thao tác có thể thực hiện lại an toàn. Một transaction database rollback có thể hoàn tác các thay đổi bên trong database, nhưng không thể tự hoàn tác email đã gửi, HTTP call đã thành công hoặc message đã phát ra broker.

Ví dụ chuyển tiền:

```text
BEGIN
  ghi ledger
  trừ tài khoản A
  cộng tài khoản B
COMMIT
Gửi thông báo chuyển tiền
```

Nếu deadlock xảy ra trước commit, rollback và retry transaction mới có thể an toàn nếu logic đọc lại số dư và kiểm tra lại. Nhưng nếu gửi email hoặc gọi cổng thanh toán trước commit, retry có thể lặp tác dụng ngoài database.

Các biện pháp:

- Dùng idempotency key cho API có thể nhận request lặp.
- Ghi transactional outbox cùng transaction nghiệp vụ rồi phát sau commit.
- Dùng inbox/dedup ở consumer nhận message.
- Thiết kế saga và hành động bù trừ cho quy trình nhiều dịch vụ.
- Không retry lỗi validation, constraint hoặc lỗi nghiệp vụ không thể thay đổi bằng cách chạy lại.

Retry phải chạy toàn bộ transaction mới, đọc dữ liệu mới và tính lại các điều kiện. Nếu chỉ chạy lại statement cuối với dữ liệu đã tính từ snapshot cũ, ứng dụng có thể tái tạo lost update hoặc vi phạm bất biến.

## 18. Deadlock, serialization failure và optimistic conflict có chi phí khác nhau

Không nên gom mọi xung đột thành một con số:

| Loại | Điều gì đã xảy ra? | Chi phí nổi bật |
|---|---|---|
| Lock wait | Transaction chờ tài nguyên không tương thích | Latency chờ, connection bị giữ, queueing |
| Deadlock victim | Chu trình chờ được phát hiện và một transaction bị rollback | Công việc đã làm bị bỏ, retry hoặc lỗi caller |
| Serialization failure | Database hủy transaction để bảo vệ tính tuần tự hóa | Đọc/tính toán/ghi trong attempt bị bỏ, cần transaction mới |
| Optimistic version conflict | Conditional update không khớp version mong đợi | Phần tính toán từ version cũ bị bỏ hoặc cần merge |
| Lock timeout | Chờ khóa vượt giới hạn | Attempt thất bại sau thời gian chờ, có thể retry hoặc trả lỗi |

Một hệ thống có thể có nhiều lock wait nhưng ít deadlock. Một hệ thống Serializable có thể có serialization failure mà không có deadlock. Optimistic conflict có thể được biểu diễn bằng row count `0`, không phải database error. Instrumentation cần tách các trường hợp này để so sánh chiến lược chính xác.

## 19. Các dấu hiệu cho biết chiến lược hiện tại không còn phù hợp

### Pessimistic locking có thể quá đắt khi

- Lock wait p95/p99 tăng theo số worker.
- Transaction giữ khóa lâu do tính toán hoặc gọi dịch vụ ngoài.
- Connection pool có nhiều request chờ nhưng database CPU không cao.
- Deadlock tăng vì nhiều luồng khóa nhiều hàng theo thứ tự khác nhau.
- Các thao tác độc lập bị chặn do phạm vi khóa quá rộng.

Hướng cải thiện: rút ngắn transaction, khóa đúng hàng, thống nhất thứ tự, dùng atomic update, chuyển việc dài ra ngoài transaction hoặc cân nhắc optimistic control.

### Optimistic control có thể quá đắt khi

- Conflict rate tăng theo số worker.
- Attempts/logical operation tăng liên tục.
- CPU application tăng vì tính toán lại.
- Nhiều transaction rollback sau khi đã làm phần lớn công việc.
- Retry exhaustion và p99 latency tăng.
- Một hoặc vài key nóng chiếm phần lớn conflict.

Hướng cải thiện: khóa/claim ngắn trước phần công việc đắt, atomic update, queue theo key, phân vùng dữ liệu hoặc thay đổi mô hình ghi.

### Retry có thể quá đắt khi

- Nhiều tầng cùng retry làm số lần gọi nhân lên.
- Backoff cộng attempt vượt deadline caller.
- Retry storm xuất hiện trong lúc dependency quá tải.
- Tỷ lệ recovery thấp nhưng attempt vẫn tiếp tục tăng.
- Tác dụng phụ bị lặp hoặc kết quả commit không xác định.

Hướng cải thiện: phân loại lỗi, giới hạn attempt/deadline, backoff+jitter, idempotency, retry budget và circuit breaker; sửa nguyên nhân contention thay vì chỉ tăng số lần thử.

## 20. Quy trình ra quyết định

Khi chọn giữa chặn trước, phát hiện xung đột và thực thi lại, hãy đi theo các câu hỏi:

1. **Bất biến nào cần bảo vệ?** Một hàng, nhiều hàng, một key duy nhất, trạng thái nghiệp vụ hay một quy trình qua nhiều dịch vụ?
2. **Tài nguyên nào thực sự nóng?** Cạnh tranh tập trung vào một hàng, một index range hay phân tán trên nhiều key?
3. **Xung đột xảy ra thường xuyên đến đâu?** Đo theo transaction attempt và logical operation, không chỉ tổng database.
4. **Phần công việc trước khi ghi tốn bao nhiêu?** Nếu attempt thua, chi phí bị bỏ `Cw` lớn hay nhỏ?
5. **Critical section dài bao lâu?** Khóa bi quan có thể giữ tài nguyên trong bao lâu và ảnh hưởng hàng đợi ra sao?
6. **Có thể biểu diễn ý định thành atomic update không?** Ví dụ tăng/giảm tương đối thay vì ghi giá trị tuyệt đối đã tính từ snapshot cũ.
7. **Conflict có thể tự động giải quyết không?** Có thể retry an toàn, merge hoặc phải yêu cầu người dùng quyết định?
8. **Retry có idempotent không?** Có tác dụng phụ ngoài database hoặc kết quả commit không rõ không?
9. **Deadline và SLO cho phép bao nhiêu attempt?** Tính cả pool wait, lock wait, backoff và transaction mới.
10. **Đo lường nào sẽ chứng minh lựa chọn tốt hơn?** Throughput, tail latency, conflict rate, lock wait, CPU, attempts và invariant cuối.

Một lựa chọn hợp lý có thể là khóa bi quan cho bước claim ngắn, optimistic version cho chỉnh sửa kéo dài, atomic update cho bộ đếm và retry bounded cho deadlock/serialization failure. Hãy chọn theo đặc tính từng use case và ghi rõ ranh giới trách nhiệm.

## 21. Kết luận

Chặn trước bằng khóa bi quan trả chi phí dưới dạng lock wait và thời gian giữ khóa; nó phù hợp khi tranh chấp thường xuyên, critical section ngắn và transaction cần bảo vệ trạng thái trước khi làm việc. Phát hiện xung đột lạc quan cho phép làm việc song song và chỉ kiểm tra version khi ghi; nó phù hợp khi conflict hiếm hoặc thời gian đọc/chỉnh sửa dài, nhưng có thể lãng phí phần tính toán đã làm khi attempt thua. Retry giúp phục hồi sau xung đột tạm thời, nhưng tăng attempt, latency và tải; nó phải có giới hạn, backoff, deadline và idempotency phù hợp.

Hãy đánh giá theo logical operation, không chỉ statement: đo throughput, p95/p99 latency, lock wait, conflict rate, deadlock/serialization failure, attempts trên mỗi operation, retry recovery/exhaustion và tài nguyên tiêu thụ. Với hotspot, cân nhắc atomic update, queue theo key, batch hoặc thay đổi mô hình dữ liệu thay vì chỉ đổi loại khóa. Chiến lược tốt là chiến lược bảo vệ đúng bất biến với tổng chi phí chờ, công việc bị bỏ và phục hồi phù hợp với workload thực tế.
