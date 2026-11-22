# Chia nhỏ lô xử lý và rút ngắn vùng giữ khóa

Transaction càng giữ nhiều khóa và giữ chúng càng lâu thì càng có nhiều cơ hội xung đột với transaction khác. Một lô xử lý hàng chục nghìn bản ghi trong một transaction có thể làm tăng thời gian chờ, deadlock, lượng log cần phục hồi và phạm vi rollback. Chia công việc thành các lô nhỏ hơn, với transaction ngắn và có ranh giới rõ ràng, thường giúp hệ thống duy trì khả năng đồng thời tốt hơn.

Tuy nhiên, chia nhỏ lô không chỉ là thêm `LIMIT` vào câu truy vấn. Mỗi lần commit tạo ra một ranh giới nhất quán mới: dữ liệu có thể thay đổi giữa các lô, một phần công việc có thể đã hoàn tất khi lô sau thất bại, và nhiều worker có thể cùng tranh lấy một bản ghi. Thiết kế đúng cần cân bằng kích thước lô, thời gian giữ khóa, chi phí commit, tính nguyên tử nghiệp vụ và khả năng tiếp tục sau lỗi.

## 1. Vì sao lô lớn làm tăng chờ khóa?

Giả sử một tác vụ cuối ngày cần cập nhật trạng thái 50.000 đơn hàng. Nếu toàn bộ công việc nằm trong một transaction:

```sql
BEGIN;

UPDATE orders
SET status = 'ARCHIVED'
WHERE created_at < :cutoff
  AND status = 'COMPLETED';

-- Còn nhiều bước xử lý và kiểm tra khác.

COMMIT;
```

Hệ quản trị có thể phải khóa một số lượng lớn hàng, index entry hoặc tài nguyên liên quan trong suốt transaction. Những request cần đọc hoặc cập nhật cùng dữ liệu có thể phải chờ. Nếu transaction còn chạy truy vấn tổng hợp, ghi audit, gọi logic ứng dụng hoặc đợi một dịch vụ bên ngoài trước commit, thời gian giữ khóa tiếp tục kéo dài.

Lô lớn còn làm tăng một số chi phí khác:

- Transaction log hoặc undo/redo cần giữ nhiều thay đổi hơn.
- Rollback sau lỗi có thể mất nhiều thời gian.
- Deadlock có thể liên quan đến nhiều tài nguyên hơn.
- Một transaction chậm có thể chặn nhiều request bình thường.
- Một lần retry có thể phải thực hiện lại khối lượng công việc lớn.
- Lock escalation hoặc khóa phạm vi rộng có thể xảy ra tùy hệ quản trị.

Chia thành các transaction nhỏ làm giảm số tài nguyên thường được giữ cùng lúc và cho phép giải phóng khóa sớm hơn sau mỗi commit. Lợi ích thực tế phụ thuộc truy vấn, index, isolation level và cơ chế khóa của hệ quản trị.

## 2. Ranh giới transaction quyết định điều gì được commit cùng nhau

Một transaction nên bao gồm đơn vị công việc cần thành công hoặc thất bại cùng nhau. Nếu mỗi đơn hàng có thể được lưu trữ độc lập, có thể xử lý từng nhóm đơn hàng trong một transaction. Nếu một quy tắc nghiệp vụ yêu cầu tất cả 50.000 đơn hàng phải thay đổi cùng lúc hoặc không hàng nào được thay đổi, chia thành nhiều transaction sẽ thay đổi ngữ nghĩa đó.

Trước khi chia lô, hãy xác định:

- Đơn vị dữ liệu nào có thể commit độc lập?
- Các thay đổi nào phải cùng thành công để giữ invariant?
- Nếu lô thứ 4 thất bại sau khi ba lô trước đã commit, hệ thống có chấp nhận trạng thái một phần không?
- Công việc có thể tiếp tục từ checkpoint sau khi tiến trình khởi động lại không?
- Dữ liệu có thể bị người dùng hoặc worker khác thay đổi giữa các lô không?

Ví dụ, cập nhật trạng thái từng đơn hàng có thể độc lập, nhưng ghi tổng số đơn đã xử lý và chi tiết audit của mỗi đơn cần nằm trong cùng transaction với cập nhật đơn đó. Khi đó, mỗi lô có thể commit nhiều đơn, miễn là mỗi đơn và các bản ghi phụ thuộc của nó được cập nhật nguyên tử.

Nếu nghiệp vụ cần kết quả toàn cục nhất quán, có thể cần một thiết kế khác như bảng staging, phiên bản dữ liệu, cờ chuyển đổi ở cuối, hoặc một bước publish nguyên tử. Không nên âm thầm đổi một transaction toàn cục thành nhiều commit một phần mà không xem xét ý nghĩa nghiệp vụ.

## 3. Chọn kích thước lô

Kích thước lô (batch size) là số đơn vị công việc được xử lý trong một transaction hoặc một lần lấy việc. Không có một con số tối ưu cho mọi hệ thống.

| Lô nhỏ | Lô lớn |
|---|---|
| Ít hàng bị khóa cùng lúc hơn. | Giảm số lần commit và round trip. |
| Transaction thường ngắn hơn, rollback nhẹ hơn. | Có thể đạt thông lượng cao hơn khi chi phí cố định của mỗi transaction lớn. |
| Tăng số lần commit và có thể tăng overhead. | Giữ khóa lâu hơn và làm tăng phạm vi xung đột. |
| Dễ checkpoint và retry một phần nhỏ. | Một lần thất bại có thể phải làm lại nhiều việc. |
| Có thể không hiệu quả nếu mỗi lô quá nhỏ. | Có thể tăng log, bộ nhớ, thời gian rollback và nguy cơ lock escalation. |

Hãy bắt đầu với kích thước vừa phải rồi đo trên workload đại diện. Có thể tăng hoặc giảm dựa trên:

- Thời gian trung bình và p95/p99 của một lô.
- Số hàng được đọc, cập nhật và khóa trong mỗi transaction.
- Thời gian chờ khóa và tỷ lệ deadlock.
- Thông lượng commit và áp lực transaction log.
- Tỷ lệ retry, timeout và lỗi một phần.
- Độ trễ của request tương tác đang dùng chung cơ sở dữ liệu.

Đừng chỉ tối ưu số bản ghi mỗi giây. Một batch đạt throughput cao nhưng khiến request người dùng chờ lâu hoặc tạo deadlock thường xuyên vẫn là một lựa chọn kém.

## 4. Chọn bản ghi theo thứ tự ổn định

Một batch cần xác định rõ những bản ghi nào thuộc lô. Nếu không có thứ tự ổn định, các lần chạy có thể xử lý trùng, bỏ sót hoặc lặp lại nhiều hàng.

Truy vấn dùng `OFFSET` có thể đơn giản:

```sql
SELECT order_id
FROM orders
WHERE status = 'COMPLETED'
ORDER BY order_id
OFFSET :offset ROWS
FETCH NEXT :batch_size ROWS ONLY;
```

Nhưng khi các hàng được cập nhật hoặc xóa giữa các lô, vị trí offset có thể dịch chuyển. Ví dụ, lô đầu lấy 100 hàng rồi đổi trạng thái khiến chúng không còn thỏa điều kiện. Nếu lô tiếp theo dùng `OFFSET 100` trên tập kết quả mới đã ngắn đi, nó có thể bỏ qua 100 hàng tiếp theo.

Với tập dữ liệu lớn và có khóa định danh ổn định, keyset pagination thường phù hợp hơn:

```sql
SELECT order_id
FROM orders
WHERE status = 'COMPLETED'
  AND order_id > :last_order_id
ORDER BY order_id
FETCH FIRST :batch_size ROWS ONLY;
```

Sau khi xử lý thành công lô, lưu `last_order_id` làm checkpoint. Lần tiếp theo bắt đầu sau ID cuối cùng. Cần có index phù hợp với điều kiện lọc và khóa sắp xếp, ví dụ index kết hợp theo `(status, order_id)` nếu kế hoạch truy vấn và workload cho thấy phù hợp.

Keyset pagination tránh chi phí bỏ qua nhiều hàng ở offset lớn và ít bị dịch chuyển vị trí hơn. Tuy vậy, nó không tự giải quyết mọi thay đổi dữ liệu:

- Nếu một hàng có ID nhỏ hơn checkpoint chuyển sang trạng thái đủ điều kiện sau khi con trỏ đã đi qua, lô hiện tại có thể bỏ sót hàng đó.
- Nếu điều kiện lọc thay đổi trong lúc chạy, tập dữ liệu không còn là một tập cố định.
- Nếu nhiều worker cùng chạy, checkpoint toàn cục đơn giản có thể không đại diện cho tiến độ của từng worker.

Hãy xác định tập công việc tại một thời điểm, dùng trạng thái hàng đợi, snapshot hoặc một quy tắc quét lại có chủ đích. Không coi `last_id` là bằng chứng rằng mọi bản ghi thỏa điều kiện đã được xử lý nếu tập điều kiện còn thay đổi.

## 5. Rút ngắn thời gian từ lúc lấy khóa đến lúc commit

Thời gian giữ khóa không chỉ phụ thuộc số hàng. Nó còn phụ thuộc mọi việc xảy ra sau khi transaction lấy khóa và trước commit.

Một transaction dài thường có dạng:

```text
BEGIN
  đọc và khóa hàng
  tính toán trong ứng dụng
  gọi HTTP service
  chờ phản hồi
  ghi nhiều bảng
  ghi log/audit
COMMIT
```

Nếu HTTP service mất vài giây, khóa vẫn có thể bị giữ trong suốt thời gian đó. Transaction cơ sở dữ liệu không nên giữ khóa trong khi chờ người dùng, mạng, file hoặc một dịch vụ độc lập nếu có thể tách các bước an toàn.

Một cấu trúc thường tốt hơn:

```text
Đọc dữ liệu cần thiết
Tính toán hoặc gọi dịch vụ bên ngoài khi chưa giữ khóa

BEGIN
  lấy khóa cần thiết
  xác nhận lại điều kiện và version
  ghi thay đổi nhỏ, cần thiết
COMMIT

Gửi tác dụng phụ sau commit bằng cơ chế có thể retry an toàn
```

Điều kiện quan trọng là dữ liệu có thể thay đổi giữa bước đọc và bước ghi. Vì vậy, khi vào transaction cuối, phải xác nhận lại điều kiện bằng version, câu lệnh cập nhật có điều kiện hoặc khóa phù hợp. Không dùng kết quả đọc cũ để ghi mà không kiểm tra.

## 6. Dùng cập nhật theo tập thay vì vòng lặp từng hàng

Nếu cùng một phép biến đổi áp dụng cho nhiều hàng, một câu lệnh set-based thường hiệu quả hơn việc ứng dụng tải từng hàng rồi gửi nhiều câu `UPDATE` riêng lẻ.

Ví dụ, đánh dấu một nhóm bản ghi hết hạn:

```sql
UPDATE reservation
SET status = 'EXPIRED'
WHERE status = 'ACTIVE'
  AND expires_at < :now;
```

Ưu điểm là giảm round trip và để optimizer chọn kế hoạch phù hợp. Tuy nhiên, một câu lệnh lớn vẫn có thể cập nhật hàng trăm nghìn bản ghi trong một transaction và giữ khóa lâu. Set-based không tự có nghĩa là batch nhỏ.

Có thể kết hợp điều kiện keyset hoặc tập ID được chọn trước để giới hạn mỗi lần cập nhật:

```sql
UPDATE reservation
SET status = 'EXPIRED'
WHERE reservation_id IN (
    SELECT reservation_id
    FROM reservation
    WHERE status = 'ACTIVE'
      AND expires_at < :now
      AND reservation_id > :last_id
    ORDER BY reservation_id
    FETCH FIRST :batch_size ROWS ONLY
);
```

Đây là ví dụ khái niệm; cú pháp giới hạn hàng trong subquery và cách khóa phụ thuộc hệ quản trị. Cần bảo đảm tập ID được chọn và câu lệnh cập nhật được thực thi với ngữ nghĩa phù hợp khi có transaction đồng thời.

## 7. Chia lô nhưng vẫn bảo vệ dữ liệu khi nhiều worker cùng xử lý

Nếu có nhiều worker, chỉ dùng `SELECT` lấy một nhóm ID rồi commit trước khi xử lý có thể khiến nhiều worker chọn cùng bản ghi. Cần một cơ chế claim công việc rõ ràng.

Một mẫu phổ biến là dùng trạng thái hàng đợi:

```text
PENDING -> PROCESSING -> DONE
                  \-> RETRY/FAILED
```

Worker lấy một lô bản ghi đang `PENDING`, đánh dấu chúng thuộc quyền xử lý của worker và commit nhanh. Việc xử lý dài diễn ra ngoài transaction giữ khóa. Khi hoàn tất, worker mở transaction ngắn để lưu kết quả và chuyển trạng thái sang `DONE`.

Với hệ quản trị hỗ trợ `SKIP LOCKED`, có thể dùng mẫu như sau:

```sql
BEGIN;

SELECT job_id
FROM job_queue
WHERE status = 'PENDING'
ORDER BY job_id
FETCH FIRST :batch_size ROWS ONLY
FOR UPDATE SKIP LOCKED;

UPDATE job_queue
SET status = 'PROCESSING',
    claimed_by = :worker_id,
    claimed_at = :now,
    lease_until = :lease_until
WHERE job_id IN (:selected_job_ids);

COMMIT;
```

Thứ tự cú pháp `FETCH` và `FOR UPDATE` có thể khác theo sản phẩm; một số hệ quản trị dùng `LIMIT`, một số dùng `TOP` hoặc cú pháp khác, và không phải hệ quản trị nào cũng hỗ trợ `SKIP LOCKED`. Đây là mẫu minh họa, cần điều chỉnh theo tài liệu hệ quản trị.

`SKIP LOCKED` cho phép worker bỏ qua hàng đang bị worker khác khóa để lấy công việc khác. Nó hữu ích cho hàng đợi, nhưng không phù hợp nếu nghiệp vụ yêu cầu mọi lần đọc phải nhìn thấy một tập kết quả đầy đủ hoặc theo thứ tự nghiêm ngặt. Hàng bị bỏ qua có thể được xử lý ở vòng sau.

## 8. Lease, worker chết và công việc bị nhận lại

Nếu worker đánh dấu `PROCESSING` rồi bị dừng đột ngột, bản ghi có thể bị kẹt mãi nếu không có cơ chế thu hồi. Lease đặt thời hạn quyền xử lý:

- `claimed_by` cho biết worker đang sở hữu claim.
- `lease_until` cho biết thời điểm claim hết hạn.
- Worker gia hạn lease khi cần nếu công việc còn chạy.
- Worker khác có thể claim lại công việc khi lease hết hạn, theo quy tắc đồng bộ.

Khi hoàn tất, worker chỉ được ghi kết quả nếu claim vẫn thuộc về nó. Có thể dùng token claim hoặc version để ngăn worker cũ ghi kết quả sau khi lease đã hết hạn và công việc được worker mới nhận lại.

Ví dụ điều kiện hoàn tất:

```sql
UPDATE job_queue
SET status = 'DONE',
    completed_at = :now
WHERE job_id = :job_id
  AND status = 'PROCESSING'
  AND claimed_by = :worker_id
  AND claim_token = :claim_token;
```

Nếu số hàng bị ảnh hưởng bằng 0, worker không còn quyền sở hữu claim hiện tại và không được ghi đè kết quả của worker khác. Token claim nên thay đổi mỗi lần claim lại để tránh ABA khi trạng thái quay về `PROCESSING`.

## 9. Retry, idempotency và checkpoint

Chia lô đồng nghĩa với việc có thể một số lô đã commit trước khi lô tiếp theo thất bại. Hệ thống cần biết lô nào đã hoàn tất và cách chạy lại an toàn.

Một số nguyên tắc:

- Ghi checkpoint trong cùng transaction với kết quả lô nếu checkpoint mô tả tiến độ đã commit.
- Đặt khóa duy nhất hoặc idempotency key cho tác vụ có thể được gửi lại.
- Thiết kế thao tác ghi sao cho chạy lại không nhân đôi kết quả.
- Phân biệt lỗi tạm thời có thể retry với lỗi nghiệp vụ không thể tự sửa.
- Giới hạn số lần retry và dùng backoff để tránh nhiều worker cùng retry dồn dập.
- Ghi lại số lượng thành công, thất bại và bản ghi đang chờ xử lý.

Ví dụ, nếu mỗi đơn hàng cần tạo một hóa đơn, đặt unique constraint trên `invoice.order_id` có thể ngăn tạo hai hóa đơn cho cùng đơn hàng. Khi lô được chạy lại, thao tác có thể kiểm tra hóa đơn đã tồn tại và tiếp tục theo quy tắc nghiệp vụ.

Không ghi checkpoint trước khi kết quả được commit. Nếu checkpoint đi trước dữ liệu, tiến trình có thể bỏ qua công việc chưa thực sự hoàn tất. Nếu dữ liệu đã commit nhưng checkpoint chưa cập nhật, công việc có thể được chạy lại; vì vậy idempotency vẫn cần thiết.

## 10. Tác dụng phụ bên ngoài và transactional outbox

Một lô có thể cập nhật cơ sở dữ liệu rồi gửi email, gọi API thanh toán hoặc phát message. Nếu gửi tác dụng phụ trong khi transaction đang mở, khóa có thể bị giữ trong suốt thời gian chờ mạng. Nếu gửi trước commit rồi transaction rollback, hệ thống bên ngoài đã nhận một sự kiện không có dữ liệu tương ứng. Nếu commit trước rồi tiến trình chết trước khi gửi, sự kiện có thể bị mất.

Transactional outbox giải quyết việc ghi dữ liệu nghiệp vụ và ghi yêu cầu gửi sự kiện trong cùng transaction:

```sql
BEGIN;

UPDATE orders
SET status = 'SHIPPED'
WHERE order_id = :order_id
  AND status = 'READY';

INSERT INTO outbox (event_id, event_type, aggregate_id, payload, status)
VALUES (:event_id, 'ORDER_SHIPPED', :order_id, :payload, 'PENDING');

COMMIT;
```

Một worker khác đọc outbox theo lô, gửi sự kiện rồi đánh dấu đã gửi. Worker gửi cần hỗ trợ retry và consumer cần idempotent vì message có thể được gửi nhiều lần. Transaction nghiệp vụ không phải giữ khóa trong lúc chờ dịch vụ bên ngoài.

## 11. Những điều không nên chia nhỏ tùy tiện

Chia lô làm giảm phạm vi một transaction, nhưng không phải lúc nào cũng phù hợp:

- Nếu một invariant yêu cầu nhiều hàng cùng thay đổi nguyên tử, phải giữ chúng trong cùng transaction hoặc thiết kế lại invariant.
- Nếu báo cáo cần một snapshot nhất quán trên toàn bộ tập dữ liệu, mỗi batch ở thời điểm khác nhau có thể tạo kết quả tổng hợp không nhất quán.
- Nếu người dùng cần thấy một thay đổi toàn cục xuất hiện cùng lúc, có thể cần staging rồi publish bằng một thao tác chuyển phiên bản.
- Nếu batch sau phụ thuộc chính xác vào kết quả batch trước, cần lưu trạng thái tiến trình và xác định thứ tự.
- Nếu có hàng bị bỏ qua do lock contention, phải có vòng quét tiếp theo để bảo đảm chúng không bị bỏ quên.

Một phương án cho báo cáo là chụp danh sách ID hoặc một watermark tại thời điểm bắt đầu, sau đó xử lý từng lô trên tập đã xác định. Nhưng snapshot ID không tự đóng băng nội dung của từng hàng; nếu nội dung thay đổi trong lúc xử lý, cần version, snapshot isolation phù hợp hoặc lưu bản sao dữ liệu cần thiết.

## 12. Giảm deadlock khi xử lý nhiều lô

Batch nhỏ hơn thường làm giảm số khóa cùng lúc, nhưng không loại bỏ deadlock. Hai worker vẫn có thể lấy những hàng trong cùng lô theo thứ tự khác nhau hoặc tranh chấp khóa ngầm qua index, FK, trigger và bảng liên quan.

Các biện pháp hữu ích:

1. Sắp xếp ID theo một thứ tự toàn cục trước khi cập nhật.
2. Giữ cùng thứ tự truy cập giữa các bảng trong mọi worker.
3. Tạo index phù hợp để tránh quét và khóa quá nhiều hàng.
4. Không giữ khóa khi thực hiện tính toán dài hoặc I/O bên ngoài.
5. Chia batch lớn thành các transaction ngắn, nhưng vẫn giữ đơn vị nghiệp vụ nguyên tử.
6. Khi deadlock xảy ra, rollback và retry toàn bộ batch hoặc đơn vị công việc bị hủy.
7. Dùng jitter/backoff để nhiều worker không lập tức va chạm lại cùng một thời điểm.

Nếu một batch chứa nhiều ID, sort danh sách trước khi khóa có thể giúp ứng dụng giữ thứ tự nhất quán. Tuy nhiên, `ORDER BY` của truy vấn không phải trên mọi hệ quản trị là cam kết thứ tự khóa vật lý. Hãy xác nhận bằng tài liệu, lock metadata và deadlock graph.

## 13. Thiết kế một worker xử lý batch từ đầu đến cuối

Một quy trình điển hình cho hàng đợi công việc:

```text
1. Claim batch
   BEGIN
     chọn một nhóm PENDING theo thứ tự ổn định
     khóa/claim các hàng, gán worker và lease
   COMMIT

2. Process outside the claim transaction
   xử lý từng công việc
   không giữ khóa hàng đợi trong lúc gọi dịch vụ ngoài

3. Persist result
   BEGIN
     xác nhận claim_token còn thuộc worker
     ghi kết quả và trạng thái DONE
     ghi outbox nếu cần phát sự kiện
   COMMIT

4. Advance checkpoint / report metrics
   ghi nhận số lượng đã xử lý và lỗi
   tiếp tục claim batch kế tiếp
```

Nếu xử lý một công việc cần cập nhật nhiều bảng, các thay đổi trong bước 3 phải cùng transaction. Nếu công việc bị lỗi tạm thời, chuyển sang `RETRY` hoặc để lease hết hạn theo một chính sách có giới hạn; không giữ transaction mở để chờ retry.

## 14. Theo dõi và điều chỉnh batch size

Không nên chọn batch size một lần rồi bỏ qua. Workload có thể thay đổi theo kích thước dữ liệu, index, số worker và lưu lượng tương tác.

Theo dõi các chỉ số:

| Chỉ số | Điều cần quan sát |
|---|---|
| Batch duration | Thời gian p50/p95/p99 của một lô. |
| Rows affected | Số hàng đọc, claim, cập nhật và xóa. |
| Lock wait | Thời gian và số lần chờ khóa. |
| Deadlock | Tần suất, tài nguyên và cặp transaction gây deadlock. |
| Commit rate | Số transaction commit mỗi giây và chi phí log. |
| Retry rate | Tỷ lệ lô hoặc công việc phải chạy lại. |
| Queue age | Thời gian công việc nằm chờ trước khi được xử lý. |
| Interactive latency | Ảnh hưởng đến request người dùng dùng chung cơ sở dữ liệu. |

Nếu batch duration dài và lock wait tăng, thử giảm kích thước lô hoặc rút ngắn phần xử lý trong transaction. Nếu lô quá ngắn và overhead commit chiếm phần lớn thời gian, có thể tăng dần kích thước. Thay đổi từng yếu tố và đo dưới tải đại diện để biết tác động thực tế.

## 15. Checklist trước khi chia lô xử lý

- [ ] Đã xác định đơn vị nghiệp vụ có thể commit độc lập.
- [ ] Đã hiểu trạng thái một phần nếu các lô trước commit nhưng lô sau thất bại.
- [ ] Đã chọn batch size dựa trên thời gian giữ khóa, throughput và chi phí commit.
- [ ] Đã dùng thứ tự chọn bản ghi ổn định và checkpoint phù hợp.
- [ ] Đã tránh `OFFSET` trên tập kết quả đang thay đổi nếu có nguy cơ bỏ sót.
- [ ] Đã có cơ chế claim khi nhiều worker xử lý cùng hàng đợi.
- [ ] Đã có lease/token để thu hồi công việc khi worker chết hoặc hết quyền sở hữu.
- [ ] Đã xác nhận version hoặc điều kiện ghi trước khi lưu kết quả từ dữ liệu đã đọc cũ.
- [ ] Đã thiết kế retry, idempotency và checkpoint nhất quán với commit.
- [ ] Đã tách I/O bên ngoài khỏi transaction đang giữ khóa.
- [ ] Đã giữ các cập nhật cần nguyên tử trong cùng transaction.
- [ ] Đã theo dõi lock wait, deadlock, batch duration, retry và độ trễ người dùng.

Chia nhỏ lô giúp giới hạn số tài nguyên bị giữ cùng lúc và cho phép giải phóng khóa sớm hơn. Hiệu quả chỉ đạt được khi mỗi lô có ranh giới nghiệp vụ rõ, lựa chọn bản ghi ổn định, transaction ngắn và quy trình retry có thể tiếp tục an toàn. Hãy điều chỉnh batch size bằng số liệu vận hành, đồng thời bảo vệ invariant và tính nhất quán qua các lần commit.
