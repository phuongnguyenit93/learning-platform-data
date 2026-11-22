# Kích thước lô ghi và cân bằng giữa thời gian giữ khóa với chi phí commit

Khi một tác vụ phải ghi hàng trăm nghìn hoặc hàng triệu dòng, thực hiện tất cả trong một transaction duy nhất thường tạo ra transaction kéo dài, giữ nhiều khóa và sinh lượng log lớn. Chia công việc thành các lô nhỏ hơn giúp giới hạn thời gian mỗi transaction, giảm phạm vi tranh chấp và cho phép tiến trình nhường tài nguyên giữa các đợt. Tuy nhiên, lô quá nhỏ lại làm tăng số lần commit, round trip, chi phí flush log và công việc điều phối.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Kích thước lô ghi vì vậy là một quyết định cân bằng: mỗi lô phải đủ lớn để amortize chi phí commit, nhưng đủ nhỏ để giới hạn thời gian giữ khóa, lượng log, bộ nhớ, thời gian rollback và ảnh hưởng đến giao dịch khác.

Bài học này giải thích chi phí của một transaction ghi, cách batch size tác động đến lock duration và commit cost, các khác biệt quan trọng giữa hệ quản trị, cách thiết kế chunk/checkpoint an toàn và cách benchmark để tìm kích thước lô phù hợp với workload thực tế.

## 1. Batch ghi và transaction

Một batch ghi là một nhóm thao tác INSERT, UPDATE hoặc DELETE được thực hiện như một đơn vị công việc. Trong mô hình phổ biến, một batch tương ứng với một transaction:

~~~text
Bắt đầu transaction
        |
        v
Ghi một nhóm dòng
        |
        v
Kiểm tra ràng buộc / trigger / index
        |
        v
COMMIT
        |
        v
Giải phóng khóa và hoàn tất transaction
        |
        v
Bắt đầu batch tiếp theo
~~~

Ví dụ, tác vụ cần cập nhật trạng thái cho 100.000 đơn hàng. Có thể thực hiện theo các cách:

- Một transaction cập nhật cả 100.000 dòng.
- 100 transaction, mỗi transaction cập nhật 1.000 dòng.
- 1.000 transaction, mỗi transaction cập nhật 100 dòng.

Ba phương án có thể tạo ra cùng trạng thái dữ liệu cuối cùng, nhưng khác nhau về số lần commit, thời gian giữ khóa, lượng log đang hoạt động, khả năng rollback và mức tranh chấp với ứng dụng trực tuyến.

### Batch size không chỉ là số dòng

Hai batch cùng có 1.000 dòng vẫn có thể có chi phí rất khác:

- Một batch cập nhật cột số nguyên nhỏ; batch kia cập nhật JSON hoặc văn bản lớn.
- Một batch chạm 1.000 dòng nằm trên ít trang; batch kia chạm 1.000 dòng phân tán khắp bảng.
- Một batch chỉ cập nhật một bảng; batch kia kích hoạt nhiều trigger, cascade và index maintenance.
- Một batch cập nhật các dòng độc lập; batch kia cạnh tranh trên cùng tài khoản, tồn kho hoặc khóa tổng hợp.

Vì vậy, cần xem cả số dòng, số byte, số trang, số index entry, số bảng liên quan và thời gian thực thi.

## 2. Chi phí của một lần commit

COMMIT đánh dấu transaction hoàn tất và yêu cầu hệ quản trị bảo đảm các thay đổi tuân theo chế độ durability đã cấu hình. Chi phí commit có thể bao gồm:

- Hoàn tất và ghi transaction log hoặc WAL.
- Flush log xuống thiết bị lưu trữ theo chính sách durability.
- Chờ xác nhận từ replication nếu cấu hình yêu cầu đồng bộ.
- Cập nhật trạng thái transaction và giải phóng tài nguyên.
- Trao đổi mạng giữa ứng dụng và database.
- Công việc điều phối ở driver, connection pool và tầng ứng dụng.

Với nhiều transaction nhỏ, chi phí cố định của mỗi lần commit có thể chiếm tỷ trọng lớn so với công việc ghi dữ liệu. Một transaction chứa nhiều dòng có thể chia sẻ chi phí bắt đầu/commit và log flush trên nhiều thao tác ghi.

### Commit không nhất thiết tương ứng một lần fsync riêng

Nhiều hệ quản trị hỗ trợ group commit: nhiều transaction cùng chờ có thể được ghi log trong một lần flush. Vì vậy, không nên giả định mỗi COMMIT luôn gây đúng một lần fsync vật lý riêng. Mức lợi ích của batch phụ thuộc tải đồng thời, cấu hình durability, storage và cơ chế log của engine.

Dù có group commit, mỗi transaction nhỏ vẫn có overhead về giao tiếp, quản lý transaction và điều phối. Ngược lại, transaction quá lớn có thể tạo log burst, kéo dài thời gian hoàn tất và làm tăng chi phí phục hồi.

### Commit latency và transaction latency

Cần phân biệt:

- **Statement time:** thời gian chạy một câu SQL.
- **Transaction time:** từ BEGIN đến COMMIT/ROLLBACK.
- **Commit latency:** thời gian từ lúc ứng dụng gửi COMMIT đến khi nhận xác nhận.
- **Lock hold time:** khoảng thời gian transaction giữ khóa có thể gây ảnh hưởng đến transaction khác.
- **End-to-end job time:** tổng thời gian hoàn thành toàn bộ công việc gồm mọi batch.

Một batch có statement time ngắn nhưng chờ lock lâu vẫn có thể làm transaction kéo dài. Một commit có latency cao có thể do log flush, replication hoặc storage, không nhất thiết do khóa.

## 3. Vì sao transaction dài làm tăng tranh chấp?

Nhiều loại khóa được giữ đến khi transaction kết thúc. Khi transaction kéo dài, các giao dịch khác có thể phải chờ lâu hơn để đọc có khóa, cập nhật hoặc xóa những dòng liên quan.

Ví dụ, transaction A cập nhật 20.000 dòng đơn hàng nhưng chỉ commit sau khi hoàn tất toàn bộ batch. Trong thời gian đó, transaction B cần cập nhật một đơn hàng đang bị A khóa có thể phải chờ, dù thao tác của B chỉ thay đổi một dòng.

Thời gian giữ khóa chịu ảnh hưởng của:

- Số dòng và số trang bị khóa.
- Thời gian thực hiện SQL và trigger.
- Thời gian chờ khóa khác trong cùng transaction.
- Thời gian ứng dụng xử lý giữa các câu SQL.
- Công việc ngoài database được thực hiện trước COMMIT.
- Độ trễ log flush và replication ở cuối transaction.

### Không làm việc ngoài database trong khi đang giữ khóa

Một lỗi thường gặp là mở transaction, cập nhật một số dòng, sau đó gọi dịch vụ HTTP, chờ người dùng hoặc xử lý tệp lớn rồi mới commit. Các khóa có thể tiếp tục được giữ trong toàn bộ thời gian chờ đó.

Hãy chuẩn bị dữ liệu cần thiết trước khi mở transaction khi có thể. Giữ transaction tập trung vào các thao tác database cần tính nguyên tử và kết thúc sớm sau khi công việc đã hoàn tất.

### Transaction dài còn ảnh hưởng đến hệ thống ngoài lock

Tùy engine, transaction dài có thể:

- Giữ phiên bản dữ liệu cũ lâu hơn và làm chậm việc thu hồi version.
- Giữ undo record hoặc transaction log cần cho rollback/recovery.
- Tăng lượng WAL/log phải xử lý và truyền sang replica.
- Làm tăng replication lag hoặc thời gian redo.
- Khiến rollback sau lỗi mất nhiều thời gian.
- Giữ connection và transaction state lâu, giảm năng lực connection pool.

Trong PostgreSQL, transaction hoặc snapshot kéo dài có thể giữ xmin cũ và cản trở vacuum loại bỏ row version không còn nhìn thấy. Trong InnoDB, read view và undo history có thể bị giữ lâu. Cơ chế chi tiết khác nhau nhưng hệ quả chung là transaction kéo dài có thể làm tăng chi phí quản lý phiên bản dữ liệu.

## 4. Vì sao batch quá nhỏ cũng tốn kém?

Chia transaction thành nhiều lô làm giảm thời gian giữ khóa mỗi lô, nhưng số lần commit tăng lên.

Nếu một tác vụ cần ghi 1.000.000 dòng:

| Batch size | Số transaction dự kiến |
|---:|---:|
| 10 | 100.000 |
| 100 | 10.000 |
| 1.000 | 1.000 |
| 10.000 | 100 |
| 100.000 | 10 |
| 1.000.000 | 1 |

Bảng chỉ minh họa số transaction, không nói kích thước nào tốt nhất. Batch 10 dòng có thể quá nhỏ vì commit và round trip chiếm phần lớn thời gian. Batch một triệu dòng có thể giữ khóa, log và transaction state quá lâu.

Các chi phí tăng khi batch quá nhỏ:

- Nhiều lần BEGIN/COMMIT và nhiều lượt giao tiếp.
- Nhiều lần kiểm tra transaction state.
- Nhiều lần flush hoặc chờ log durability tùy tải và engine.
- Nhiều lần gọi ứng dụng và cập nhật checkpoint.
- Throughput có thể thấp dù lock duration từng transaction ngắn.

Batch nhỏ vẫn hữu ích khi cần nhường tài nguyên thường xuyên, giảm thời gian chờ của giao dịch trực tuyến hoặc giới hạn rủi ro khi một lô thất bại. Mục tiêu là tìm điểm cân bằng, không phải giảm số transaction bằng mọi giá.

## 5. Vì sao batch quá lớn cũng tốn kém?

Batch lớn giảm số lần commit nhưng tăng lượng công việc nằm trong một transaction.

### Lock footprint lớn hơn

Một transaction cập nhật nhiều dòng có thể giữ nhiều row/key lock, page lock hoặc các khóa liên quan. Nó làm tăng xác suất giao nhau với giao dịch khác và có thể gây lock escalation trong một số hệ quản trị.

### Thời gian chờ và deadlock dài hơn

Transaction càng kéo dài, khoảng thời gian các transaction khác có thể va chạm càng lớn. Nếu hai transaction lấy khóa theo thứ tự khác nhau, nguy cơ deadlock có thể tăng.

### Rollback và recovery lâu hơn

Nếu transaction lớn thất bại ở cuối, hệ quản trị có thể phải undo một lượng thay đổi lớn. Ứng dụng cũng có thể phải chạy lại toàn bộ batch nếu không có checkpoint hoặc cơ chế idempotency.

### Log và replication burst

Một batch lớn có thể tạo lượng WAL/transaction log lớn trong thời gian ngắn, làm tăng áp lực storage, log backup, redo và replication. Replica có thể theo sau primary nếu tốc độ phát log vượt khả năng áp dụng.

### Bộ nhớ và tài nguyên phụ trợ

Các thao tác lớn có thể cần thêm bộ nhớ cho sort/hash, trigger, foreign key checking hoặc cấu trúc trung gian. Một transaction đơn lẻ không phải lúc nào cũng giữ toàn bộ dòng trong RAM, nhưng các operator và engine-specific state có thể làm tăng tài nguyên.

### Một batch lớn có thể chặn công việc quan trọng

Ví dụ, một job cập nhật trạng thái 500.000 dòng theo một transaction có thể chặn thao tác sửa đơn hàng của người dùng trong nhiều phút. Tổng job time có thể thấp nhưng p95/p99 của giao dịch trực tuyến tăng mạnh.

## 6. Mối quan hệ giữa batch size, lock duration và commit cost

Có thể hình dung hai xu hướng:

- Khi batch size tăng, số lần commit cho cùng khối lượng công việc giảm.
- Khi batch size tăng, thời gian một transaction tồn tại và phạm vi khóa thường tăng.

~~~text
Chi phí trên mỗi dòng
^
|  Commit overhead
|  \
|   \____
|         \____
|
|                 Lock/rollback risk
|              ___/
|          ___/
|      ___/
+----------------------------------> Batch size
       nhỏ       vừa       lớn
~~~

Đây là sơ đồ định tính, không phải công thức dự đoán. Đường chi phí thực tế phụ thuộc workload, engine, storage, mức đồng thời và cách truy cập dữ liệu.

Một batch tốt thường nằm ở vùng mà:

- Commit overhead trên mỗi dòng đã đủ thấp.
- Transaction duration vẫn trong giới hạn chấp nhận.
- Số khóa và số trang bị tác động không gây tranh chấp lớn.
- Log generation và replication vẫn theo kịp.
- Rollback một batch vẫn có thể hoàn thành trong thời gian phù hợp.
- Throughput toàn hệ thống tăng mà latency giao dịch trực tuyến không vượt SLO.

### Tối ưu theo hai mục tiêu cùng lúc

Không nên chỉ tối ưu thời gian hoàn thành batch job. Hãy đặt hai nhóm mục tiêu:

1. **Hiệu năng job:** tổng thời gian, rows/second, commit latency và số lần retry.
2. **Sức khỏe workload chung:** lock wait, deadlock, p95/p99 của giao dịch trực tuyến, CPU, I/O, log và replication lag.

Batch size lớn hơn có thể làm job nhanh hơn nhưng khiến giao dịch trực tuyến chậm hơn. Nếu workload dùng chung database, mục tiêu cần xét toàn hệ thống.

## 7. Chọn batch size bằng thời gian thay vì chỉ số dòng

Số dòng là tham số dễ triển khai nhưng không phản ánh đầy đủ chi phí. Một cách vận hành tốt là đặt giới hạn kép:

- Giới hạn số dòng mỗi batch.
- Giới hạn thời gian transaction hoặc thời gian xử lý mục tiêu.

Ví dụ, job có thể bắt đầu với tối đa 1.000 dòng mỗi transaction, nhưng kết thúc batch sớm nếu đã gần ngưỡng thời gian đặt ra. Nếu một nhóm dòng nặng hơn bình thường, giới hạn thời gian giúp không để transaction kéo dài ngoài dự kiến.

Các ngưỡng cần đo và điều chỉnh:

- Thời gian từ BEGIN đến COMMIT.
- Số dòng được insert/update/delete.
- Số trang hoặc index entry bị tác động nếu có thể quan sát.
- Commit latency.
- Lock wait và số lần deadlock.
- Số byte log sinh ra.
- Temp I/O, WAL/log throughput và replication lag.

### Chọn mục tiêu thời gian

Không có một ngưỡng transaction duration chung cho mọi hệ thống. Có thể đặt mục tiêu dựa trên:

- SLO của giao dịch trực tuyến.
- Thời gian chờ khóa tối đa mà nghiệp vụ chấp nhận.
- Thời gian phục hồi hoặc retry.
- Chu kỳ batch và cửa sổ bảo trì.
- Tốc độ ghi log và khả năng áp dụng của replica.

Mục tiêu cần được xác định bằng phép đo tải. Một transaction kéo dài 2 giây có thể bình thường với bulk load ngoại tuyến nhưng không chấp nhận được với bảng nóng phục vụ giao dịch tương tác.

## 8. Truy cập theo thứ tự ổn định và chunking

Khi chia một công việc lớn thành các chunk, cần xác định rõ dòng nào thuộc mỗi chunk. Truy cập theo khóa ổn định thường dễ kiểm soát hơn việc dùng OFFSET để bỏ qua dữ liệu đã xử lý.

Ví dụ, xử lý các bản ghi có id tăng dần theo từng khoảng:

~~~sql
SELECT id
FROM work_items
WHERE id > :last_processed_id
ORDER BY id
LIMIT :batch_size;
~~~

Sau khi xử lý thành công và commit, ứng dụng cập nhật last_processed_id để tiếp tục từ chunk sau.

### Vì sao tránh OFFSET cho job batch sâu?

OFFSET lớn có thể buộc database đọc và bỏ qua nhiều dòng trước khi đến chunk cần xử lý. Khi dữ liệu thay đổi, ranh giới offset cũng có thể dịch chuyển. Key range hoặc cursor theo khóa duy nhất giúp xác định vị trí tiếp tục rõ ràng hơn.

### Cần xử lý khoảng trống và dòng không phù hợp

Nếu job chỉ xử lý các dòng thỏa status = 'PENDING', checkpoint phải bảo đảm các dòng bị bỏ qua do filter hoặc lỗi tạm thời không bị mất vĩnh viễn. Một chiến lược phổ biến là:

- Chia theo khóa ổn định để xác định phạm vi.
- Chọn các dòng còn đủ điều kiện trong phạm vi đó.
- Commit thay đổi và checkpoint một cách nhất quán.
- Có bước quét lại hoặc hàng đợi retry cho các dòng lỗi.

Không tăng last_processed_id vượt qua những dòng chưa xử lý nếu quy tắc nghiệp vụ yêu cầu xử lý tất cả.

## 9. Checkpoint và tính nguyên tử giữa dữ liệu với tiến độ

Khi mỗi batch commit riêng, toàn bộ job không còn là một transaction nguyên tử duy nhất. Nếu job dừng sau batch thứ 20, các batch trước đã được commit và không thể rollback cùng batch cuối.

Để tiếp tục an toàn, cần lưu tiến độ (checkpoint) và bảo đảm checkpoint phản ánh đúng những thay đổi đã commit.

### Cập nhật dữ liệu và checkpoint trong cùng transaction

Nếu checkpoint nằm trong cùng database, có thể cập nhật dữ liệu và checkpoint trong một transaction:

~~~sql
BEGIN;

UPDATE work_items
SET processed = TRUE
WHERE id > :range_start
  AND id <= :range_end
  AND processed = FALSE;

UPDATE batch_progress
SET last_completed_id = :range_end,
    updated_at = CURRENT_TIMESTAMP
WHERE job_name = 'rebuild_work_items';

COMMIT;
~~~

Nếu transaction rollback, cả dữ liệu và checkpoint cùng rollback. Nếu commit thành công, cả hai cùng được ghi nhận.

Ví dụ trên giả định range đã được xác định và tất cả dòng cần xử lý trong khoảng đã được cập nhật thành công. Nếu có lỗi từng dòng hoặc chỉ xử lý một phần, checkpoint phải phản ánh đúng phần đã hoàn tất.

### Checkpoint ở hệ thống ngoài database

Nếu checkpoint nằm trong queue, file hoặc dịch vụ khác, việc commit database và cập nhật checkpoint không tự động nguyên tử. Có thể xảy ra:

- Database commit thành công nhưng checkpoint chưa ghi.
- Checkpoint ghi trước nhưng database rollback.
- Worker mất kết nối sau commit và không biết transaction đã thành công hay chưa.

Trong trường hợp đó, cần thiết kế at-least-once processing kết hợp idempotency, transactional outbox/inbox hoặc giao thức phối hợp phù hợp. Không giả định có thể đạt exactly-once chỉ bằng cách retry request.

## 10. Idempotency và retry khi batch thất bại

Batch có thể thất bại do deadlock, lock timeout, mất kết nối, lỗi constraint hoặc lỗi hạ tầng. Ứng dụng cần xác định thao tác có thể chạy lại an toàn hay không.

### Idempotent operation

Một thao tác idempotent khi thực hiện lặp lại không làm thay đổi kết quả cuối ngoài lần đầu theo ý nghĩa nghiệp vụ.

Ví dụ đặt trạng thái cố định:

~~~sql
UPDATE orders
SET archived = TRUE
WHERE id >= :start_id
  AND id < :end_id
  AND archived = FALSE;
~~~

Nếu chạy lại, các dòng đã archived không bị thay đổi thêm theo logic này. Nhưng nếu thao tác cộng dồn:

~~~sql
UPDATE accounts
SET balance = balance + :amount
WHERE account_id = :account_id;
~~~

chạy lại có thể cộng tiền lần thứ hai. Cần idempotency key, bảng ghi nhận sự kiện đã áp dụng hoặc điều kiện chống xử lý trùng.

### Retry chỉ lỗi có thể retry

Không retry vô hạn mọi lỗi. Có thể cân nhắc retry với backoff và jitter cho deadlock victim hoặc lỗi tạm thời được xác định. Lỗi dữ liệu, constraint hoặc logic thường cần sửa nguyên nhân thay vì lặp lại.

Quy tắc retry:

1. Đảm bảo transaction thất bại đã rollback hoàn toàn.
2. Xác định lỗi có thể retry theo engine/driver.
3. Dùng số lần retry giới hạn.
4. Áp dụng exponential backoff và jitter để tránh nhiều worker retry cùng lúc.
5. Bảo đảm batch idempotent hoặc có khóa chống trùng.
6. Ghi nhận batch id, range, số lần thử và kết quả.
7. Đưa lỗi kéo dài vào dead-letter/reconciliation flow nếu phù hợp.

### Không retry một transaction chưa rõ kết quả

Nếu connection mất ngay sau khi gửi COMMIT, ứng dụng có thể không biết database đã commit hay chưa. Không nên mặc định transaction đã rollback. Hãy kiểm tra trạng thái bằng idempotency key hoặc một bản ghi kết quả có thể truy vấn trước khi thực hiện lại.

## 11. Thứ tự lấy khóa và deadlock

Hai transaction có thể deadlock khi mỗi transaction giữ một khóa mà transaction kia cần.

~~~text
Transaction A                 Transaction B
-------------                 -------------
Khóa dòng 1                   Khóa dòng 2
Cần khóa dòng 2               Cần khóa dòng 1
Chờ B                         Chờ A
             \               /
              \             /
                DEADLOCK
~~~

Một biện pháp quan trọng là truy cập các dòng theo thứ tự ổn định. Nếu nhiều worker cùng cập nhật một tập khóa, hãy cố gắng sắp xếp theo primary key hoặc một thứ tự nhất quán trước khi cập nhật.

Ví dụ:

~~~sql
SELECT id
FROM accounts
WHERE id = ANY(:account_ids)
ORDER BY id;
~~~

Ứng dụng sau đó xử lý các account theo thứ tự đã thống nhất. Khả năng bảo đảm thứ tự khóa thực tế vẫn phụ thuộc kế hoạch, engine và câu lệnh; cần xác nhận bằng execution plan hoặc tài liệu của hệ quản trị.

### Batch nhỏ có loại bỏ deadlock không?

Không. Batch nhỏ giảm số khóa và thời gian transaction trong nhiều trường hợp, nhưng deadlock vẫn có thể xảy ra nếu các transaction lấy khóa theo thứ tự khác nhau hoặc có trigger/cascade truy cập thêm bảng.

Hãy xử lý cả hai khía cạnh:

- Giảm lock footprint và transaction duration.
- Chuẩn hóa thứ tự truy cập tài nguyên.
- Giữ transaction ngắn và tránh chờ ngoài database.
- Có retry có giới hạn cho deadlock victim.
- Ghi nhận deadlock graph hoặc thông tin tương đương để tìm chu trình khóa.

## 12. Khác biệt khóa giữa các hệ quản trị

Không nên áp dụng một mô hình khóa duy nhất cho mọi engine.

### PostgreSQL

PostgreSQL dùng MVCC cho các truy vấn thông thường. Reader không khóa dòng theo cách ngăn writer cập nhật cùng dòng trong nhiều trường hợp; tuy nhiên, các thao tác UPDATE/DELETE và SELECT FOR UPDATE có thể tạo row-level lock. Row lock thường được giữ đến hết transaction.

PostgreSQL không có lock escalation từ row lock lên table lock theo mô hình SQL Server. Tuy nhiên, transaction lớn vẫn có thể giữ nhiều tuple lock, gây chờ trên các dòng nóng, tăng WAL, tạo nhiều dead tuple và làm vacuum khó hơn nếu transaction/snapshot kéo dài.

Có thể xem lock đang chờ qua pg_locks, pg_stat_activity và các công cụ thống kê phù hợp. Các cấu hình log_lock_waits, deadlock_timeout và lock_timeout có thể hỗ trợ điều tra/kiểm soát; cấu hình cần cân nhắc tải và mục tiêu vận hành.

### MySQL InnoDB

InnoDB dùng row-level locking trên index record và có thể dùng gap/next-key lock tùy isolation level, truy vấn và access path. Một transaction cập nhật nhiều dòng có thể giữ nhiều khóa đến commit/rollback. Index phù hợp giúp giới hạn phạm vi record cần khóa; truy vấn thiếu index có thể quét và khóa phạm vi rộng hơn dự kiến.

Cần xem transaction isolation, execution plan, deadlock log và các thông tin lock wait như Performance Schema hoặc công cụ giám sát tương ứng với phiên bản.

### SQL Server

SQL Server dùng khóa ở nhiều mức như row, key, page và table. Engine có thể thực hiện lock escalation từ nhiều khóa chi tiết lên khóa ở mức cao hơn trong một số tình huống để giảm overhead quản lý khóa. Khi escalation xảy ra, phạm vi chặn có thể rộng hơn.

Batch nhỏ có thể giảm lượng khóa đồng thời và nguy cơ escalation, nhưng không bảo đảm ngăn escalation vì quyết định phụ thuộc số khóa, bộ nhớ và cấu hình. Theo dõi actual execution plan, lock escalation events, waits và deadlock graph.

### So sánh khái quát

| Khía cạnh | PostgreSQL | MySQL InnoDB | SQL Server |
|---|---|---|---|
| Cơ chế đọc phổ biến | MVCC | MVCC/consistent read | Locking và row versioning tùy cấu hình |
| Khóa ghi | Row-level tuple locks và table-level locks | Index record, gap/next-key tùy điều kiện | Key/row, page, table |
| Lock escalation | Không có kiểu escalation row-to-table truyền thống | Không theo mô hình escalation phổ biến của SQL Server | Có thể xảy ra |
| Transaction dài | Có thể giữ row locks, snapshot/xmin, tăng vacuum pressure | Giữ record/gap locks và undo history | Giữ locks, log và có thể gây escalation |
| Điều tra | pg_locks, pg_stat_activity, logs | Performance Schema, InnoDB status/deadlock log | DMVs, Extended Events, deadlock graph |

Tên công cụ, view và khả năng quan sát phụ thuộc phiên bản. Hãy dùng tài liệu engine đang triển khai để chọn đúng chỉ số.

## 13. Index và phạm vi khóa của batch

Index không chỉ giúp truy vấn nhanh; nó còn ảnh hưởng số dòng và phạm vi mà UPDATE/DELETE phải tìm.

Ví dụ:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE tenant_id = :tenant_id
  AND created_at < :cutoff
  AND status = 'CLOSED';
~~~

Nếu không có index phù hợp, hệ quản trị có thể quét nhiều dòng để tìm tập cần cập nhật. Tùy engine và isolation, phạm vi khóa hoặc lượng công việc có thể rộng hơn mong đợi.

Một index có thể được cân nhắc:

~~~sql
CREATE INDEX idx_orders_archive_batch
ON orders (tenant_id, status, created_at, order_id);
~~~

Thứ tự cột phải dựa trên điều kiện lọc, cách chia chunk và workload khác. Index thêm vào cũng làm INSERT/UPDATE/DELETE tốn thêm công việc, nên phải đo.

### Index giúp giảm số dòng cần khóa

Nếu điều kiện chọn lọc tốt, index có thể giúp tìm đúng các dòng mục tiêu thay vì quét nhiều dòng không liên quan. Điều này có thể giảm:

- Số dòng phải kiểm tra.
- Số trang đọc.
- Thời gian statement.
- Số dòng có khả năng bị khóa hoặc cập nhật.

Tuy nhiên, với một batch cập nhật phần lớn bảng, sequential scan có thể rẻ hơn. Index không phải luôn có lợi và không loại bỏ khóa trên các dòng thực sự được cập nhật.

### Foreign key, trigger và cascade

Một câu UPDATE trên bảng chính có thể kích hoạt kiểm tra foreign key, trigger hoặc cascade sang bảng khác. Batch size cần tính đến toàn bộ công việc phát sinh, không chỉ số dòng ở bảng đầu tiên.

Nếu một lô 500 dòng kích hoạt 10.000 thay đổi ở bảng con, lock footprint và log volume có thể lớn hơn nhiều so với con số 500 ban đầu.

## 14. Isolation level và phạm vi tranh chấp

Isolation level quyết định mức cô lập giữa các transaction và có thể ảnh hưởng đến khóa hoặc snapshot.

Các mức thường gặp:

- **Read Committed:** mỗi statement có thể nhìn thấy snapshot mới theo quy tắc engine.
- **Repeatable Read:** bảo đảm tính nhất quán đọc trong phạm vi transaction theo đặc tả và triển khai của engine.
- **Serializable:** yêu cầu kết quả tương đương thực thi tuần tự; có thể phát sinh khóa hoặc serialization failure cần retry.

Tên giống nhau không bảo đảm mọi engine có cùng hành vi nội bộ. Ví dụ, InnoDB ở Repeatable Read có thể sử dụng next-key locking cho một số range operation; PostgreSQL Repeatable Read dùng snapshot isolation và có thể phát sinh serialization anomaly khác với Serializable.

### Batch nhỏ không tự thay đổi isolation

Chia một công việc thành nhiều transaction có nghĩa mỗi batch có thể quan sát snapshot khác nhau và commit độc lập. Điều này thay đổi tính nguyên tử và có thể thay đổi kết quả nếu dữ liệu liên quan được cập nhật giữa các batch.

Nếu nghiệp vụ cần một snapshot logic thống nhất cho toàn bộ job, cần thiết kế mốc dữ liệu, version, cutoff hoặc cơ chế snapshot phù hợp. Giữ một transaction lớn chỉ để duy trì snapshot có thể gây áp lực lên database; cần cân bằng yêu cầu nhất quán và tài nguyên.

## 15. Ví dụ batch worker với SKIP LOCKED trong PostgreSQL

Một hàng đợi công việc có thể được nhiều worker xử lý đồng thời. Mỗi worker chọn một nhóm job chưa xử lý, khóa chúng và bỏ qua những dòng đang bị worker khác khóa.

~~~sql
BEGIN;

WITH batch AS (
    SELECT id
    FROM work_items
    WHERE status = 'PENDING'
    ORDER BY id
    LIMIT 500
    FOR UPDATE SKIP LOCKED
)
UPDATE work_items AS w
SET status = 'PROCESSING',
    claimed_at = clock_timestamp()
FROM batch AS b
WHERE w.id = b.id
RETURNING w.id;

COMMIT;
~~~

Ví dụ này minh họa việc claim tối đa 500 dòng trong một transaction ngắn. Sau commit, worker xử lý công việc bên ngoài transaction hoặc theo một transaction riêng tùy yêu cầu nghiệp vụ.

### Vì sao SKIP LOCKED hữu ích?

Worker không phải chờ các dòng đang được worker khác khóa; nó bỏ qua và lấy các dòng khác. Cách này phù hợp với queue-like workload khi không cần đọc mọi dòng theo thứ tự tuyệt đối.

Các giới hạn:

- Một dòng bị khóa lâu có thể bị bỏ qua nhiều lần và chậm được xử lý.
- Thứ tự hoàn thành không được bảo đảm.
- Cần cơ chế lease/timeout để phục hồi job bị worker chết sau khi claim.
- Trạng thái PROCESSING cần có quy tắc hết hạn hoặc tái nhận.
- Cần index hỗ trợ filter và order, ví dụ index phù hợp với status/id.
- Hành vi SKIP LOCKED phụ thuộc engine và isolation level.

Không giữ transaction mở trong suốt thời gian worker gọi dịch vụ ngoài nếu không cần khóa dòng trong toàn bộ thời gian đó. Có thể claim bằng transaction ngắn, commit, xử lý, rồi cập nhật kết quả trong transaction khác. Khi đó cần idempotency và lease để xử lý worker bị lỗi giữa chừng.

## 16. Tính nguyên tử: một transaction lớn hay nhiều transaction nhỏ?

Một transaction lớn có ưu điểm là toàn bộ thay đổi thành công hoặc rollback cùng nhau. Đây là yêu cầu quan trọng với các thao tác tài chính hoặc thay đổi nhiều bảng phải nhất quán tại một thời điểm.

Nhiều batch nhỏ giảm thời gian giữ khóa và giới hạn rollback, nhưng các batch trước đã commit sẽ vẫn tồn tại nếu batch sau thất bại. Vì vậy, không thể chia transaction chỉ vì hiệu năng mà bỏ qua ngữ nghĩa nghiệp vụ.

### Khi cần all-or-nothing

Nếu tất cả thay đổi phải nguyên tử, có thể cần một transaction duy nhất, hoặc một mô hình staging/swap/visibility flag để chuẩn bị dữ liệu theo lô nhưng chỉ công bố khi hoàn tất. Mô hình cụ thể phụ thuộc database và yêu cầu nhất quán.

### Khi chấp nhận tiến độ từng phần

Với backfill, archive hoặc tác vụ bảo trì, có thể chấp nhận commit từng chunk nếu:

- Mỗi chunk độc lập về mặt nghiệp vụ.
- Có checkpoint đáng tin cậy.
- Retry không gây nhân đôi tác động.
- Có khả năng tiếp tục sau lỗi.
- Có báo cáo tiến độ và cơ chế reconciliation.
- Người dùng không nhìn thấy trạng thái trung gian sai quy tắc.

### Ghi staging rồi áp dụng

Một cách khác là nạp dữ liệu vào staging table theo nhiều batch, kiểm tra tính hợp lệ, rồi áp dụng thay đổi cuối trong một bước được kiểm soát. Điều này có thể rút ngắn transaction ảnh hưởng bảng nóng, nhưng bước publish/swap vẫn cần tính nguyên tử và lock phù hợp.

## 17. Điều chỉnh batch size thích nghi

Một kích thước cố định có thể không phù hợp khi tải thay đổi. Một batch 2.000 dòng có thể hoàn thành nhanh lúc tải thấp nhưng kéo dài khi storage hoặc lock contention tăng.

Có thể dùng cơ chế điều chỉnh có giới hạn:

- Nếu transaction duration, lock wait và replication lag thấp, tăng batch size từng bước nhỏ.
- Nếu lock wait, p95/p99, log backlog hoặc transaction duration vượt ngưỡng, giảm batch size.
- Nếu commit latency chiếm tỷ trọng cao trong thời gian job, cân nhắc tăng batch size khi lock duration còn dư địa.
- Nếu batch lớn gây deadlock hoặc rollback dài, giảm batch size và xem lại thứ tự khóa.
- Dùng min/max rõ ràng để tránh dao động hoặc tăng vô hạn.

Không điều chỉnh chỉ dựa trên một chỉ số. Ví dụ, commit latency tăng có thể do storage hoặc replication; giảm batch size có thể làm số lần commit tăng thêm và khiến tình hình xấu hơn. Cần xác định bottleneck trước.

### Điều chỉnh theo thời gian transaction

Một bộ điều khiển đơn giản có thể hướng đến một khoảng transaction duration mục tiêu. Sau mỗi batch, ứng dụng ghi nhận thời gian thực tế và thay đổi số dòng ở batch kế tiếp.

Đây là cơ chế điều chỉnh heuristic, không thay thế giới hạn an toàn. Cần tránh tăng batch quá nhanh, đồng thời giữ các giới hạn về số dòng, thời gian, log và tài nguyên.

## 18. Benchmark để tìm batch size phù hợp

Không chọn batch size bằng cảm tính hoặc dựa trên một lần chạy trên môi trường nhàn rỗi. Hãy thử nhiều mức trong workload đại diện.

### Ma trận thử nghiệm

| Biến thử nghiệm | Các trường hợp |
|---|---|
| Batch size | 50, 100, 500, 1.000, 5.000, 10.000 |
| Loại thao tác | INSERT, UPDATE, DELETE, upsert |
| Dữ liệu | Dòng hẹp/rộng, index ít/nhiều, trigger/FK |
| Tranh chấp | Bảng ít cạnh tranh và bảng nóng |
| Tải đồng thời | Một worker, vài worker, mức tải production |
| Storage | Warm cache, I/O thực tế, log/replication |
| Thời gian | Transaction duration, commit latency, tổng job time |

Các con số chỉ là điểm bắt đầu minh họa. Phạm vi thực tế phải dựa trên quy mô dữ liệu và giới hạn của hệ thống.

### Chỉ số cần ghi

- Rows per second và tổng thời gian job.
- Transaction duration p50/p95/p99.
- Commit latency p50/p95/p99.
- Lock wait time và số lần lock timeout.
- Deadlock count và số lần retry.
- Rows/pages read và written.
- WAL/transaction log bytes per second.
- Log flush latency và storage latency.
- Temp I/O, CPU và memory.
- Replication lag hoặc redo queue.
- Rollback duration khi thử nghiệm lỗi có kiểm soát.
- p95/p99 của giao dịch trực tuyến bị ảnh hưởng.

### Quy trình benchmark

1. Chọn một tập dữ liệu và workload đại diện.
2. Ghi baseline khi chưa thay đổi batch size.
3. Chạy từng batch size với cùng số dòng tổng.
4. Giữ số worker và mức tải tương đương.
5. Warm-up và lặp lại nhiều lần.
6. Thu thập latency, lock, log, I/O và throughput.
7. Kiểm tra kết quả dữ liệu và tính đúng của checkpoint.
8. Thử lỗi giữa các batch để xác minh khả năng resume.
9. So sánh cả job time và tác động đến giao dịch trực tuyến.
10. Chọn vùng batch size đạt throughput tốt mà vẫn đáp ứng SLO và giới hạn vận hành.

Không so sánh một batch nhỏ khi cache nóng với một batch lớn khi cache lạnh. Cũng không chạy tất cả phương án tuần tự trong điều kiện tải khác nhau rồi xem chênh lệch là do batch size.

## 19. Đọc số liệu lock và commit

Khi batch job chậm, cần xác định thời gian bị tiêu tốn ở đâu.

### Nếu lock wait chiếm phần lớn thời gian

- Xem transaction nào đang giữ khóa.
- Xem batch có cập nhật cùng một tập dòng nóng không.
- Kiểm tra index và điều kiện WHERE có giới hạn phạm vi truy cập không.
- Giảm batch size hoặc số worker.
- Chuẩn hóa thứ tự lấy khóa.
- Rút ngắn phần xử lý ngoài database trong transaction.
- Xem isolation level và range locking.

### Nếu commit latency chiếm phần lớn thời gian

- Kiểm tra log flush/WAL latency và storage.
- Kiểm tra replication acknowledgment hoặc synchronous replication.
- Xem có group commit và mức đồng thời phù hợp không.
- Đo số lần commit và chi phí round trip.
- Thử tăng batch size từng bước nếu lock duration còn dư địa.
- Không tắt durability hoặc synchronous replication chỉ để cải thiện benchmark nếu điều đó vi phạm yêu cầu an toàn dữ liệu.

### Nếu statement time lớn nhưng lock wait thấp

- Đọc execution plan.
- Kiểm tra scan, index, sort, trigger và foreign key checks.
- Xem CPU, buffer reads, physical I/O và temp spill.
- Chia nhỏ câu lệnh nếu một statement xử lý quá nhiều dòng và nghiệp vụ cho phép.
- Cân nhắc index phù hợp nhưng đo chi phí ghi bổ sung.

### Nếu replication lag tăng

- Đo tốc độ tạo log và tốc độ apply trên replica.
- Xem batch có tạo log burst hay không.
- Giảm batch size hoặc giảm số worker nếu replica không theo kịp.
- Xem cấu hình đồng bộ và khả năng storage/network.
- Theo dõi thời gian phục hồi backlog sau khi batch kết thúc.

## 20. Các sai lầm thường gặp

- **Chọn batch size chỉ theo số dòng:** bỏ qua độ rộng dữ liệu, index, trigger và số trang.
- **Dùng một transaction cho toàn bộ job lớn:** giữ khóa và snapshot lâu, rollback tốn kém.
- **Chia thành batch quá nhỏ:** commit và round trip có thể chiếm phần lớn thời gian.
- **Tăng batch size chỉ để giảm commit:** có thể làm lock wait, log burst và replication lag tăng.
- **Giữ transaction mở khi gọi dịch vụ ngoài:** kéo dài thời gian giữ khóa không cần thiết.
- **Dùng OFFSET để chia chunk sâu:** tốn công bỏ qua dữ liệu và dễ dịch chuyển ranh giới.
- **Cập nhật checkpoint trước commit:** có thể đánh dấu hoàn tất dù dữ liệu rollback.
- **Cập nhật checkpoint sau commit nhưng không idempotent:** mất kết nối có thể khiến batch chạy lặp và nhân đôi tác động.
- **Không xử lý deadlock retry:** một batch thất bại có thể dừng toàn bộ job.
- **Retry mọi lỗi vô hạn:** che giấu lỗi logic và tạo retry storm.
- **Cho rằng batch nhỏ loại bỏ deadlock:** thứ tự khóa và trigger vẫn có thể tạo chu trình.
- **Tăng số worker mà không đo:** nhiều worker có thể tranh cùng index, page, row hoặc storage.
- **Bỏ qua lock escalation của engine:** hành vi khác nhau giữa PostgreSQL, InnoDB và SQL Server.
- **Chỉ đo job time:** có thể làm p95/p99 của ứng dụng trực tuyến xấu đi.
- **Tắt durability để benchmark:** kết quả không phản ánh cấu hình production và có thể gây mất dữ liệu.

## 21. Checklist thiết kế batch ghi

Trước khi triển khai một tác vụ ghi lớn, hãy trả lời:

1. Batch có bao nhiêu dòng và bao nhiêu byte dữ liệu?
2. Những bảng, index, trigger và foreign key nào bị tác động?
3. Transaction duration và commit latency mục tiêu là bao nhiêu?
4. Các khóa được giữ trong bao lâu và có giao với workload trực tuyến không?
5. Có hot row, hot page, hot key hoặc range lock không?
6. Thứ tự truy cập khóa có nhất quán giữa các worker không?
7. Có thể chia công việc thành các chunk độc lập về nghiệp vụ không?
8. Checkpoint có được commit nguyên tử với dữ liệu không?
9. Batch có idempotent hoặc có cơ chế chống xử lý trùng không?
10. Retry có giới hạn, backoff và phân loại lỗi không?
11. Isolation level có phù hợp với tính nhất quán yêu cầu không?
12. Log throughput và replication có theo kịp không?
13. Rollback một batch mất bao lâu?
14. Số worker và batch size có được điều chỉnh theo tải không?
15. Benchmark đã đo cả job throughput và p95/p99 của workload chung chưa?

## Kết luận

Batch ghi cần cân bằng hai loại chi phí. Batch nhỏ làm transaction ngắn và giảm lock footprint trong nhiều tình huống, nhưng tăng số lần commit và overhead điều phối. Batch lớn giảm số lần commit trên mỗi dòng, nhưng có thể giữ nhiều khóa lâu hơn, tạo log burst, tăng rollback time và ảnh hưởng giao dịch trực tuyến.

Kích thước phù hợp phụ thuộc dữ liệu, index, trigger, isolation, engine, storage và mức đồng thời. Hãy chia chunk theo khóa ổn định, thiết kế checkpoint và retry an toàn, đo transaction duration cùng commit latency, lock wait, deadlock, log throughput và replication lag. Chọn batch size bằng benchmark có thể lặp lại, đồng thời xác nhận throughput của job không làm suy giảm SLO của workload chung.
