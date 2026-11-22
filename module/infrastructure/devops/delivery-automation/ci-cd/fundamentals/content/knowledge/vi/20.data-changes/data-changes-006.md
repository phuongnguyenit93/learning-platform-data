# Kiểm soát khóa, thời lượng và khả năng chạy lại tác vụ dữ liệu

Một tác vụ dữ liệu có thể chạy trong vài giây hoặc nhiều giờ. Nó có thể đọc hàng triệu bản ghi, chuyển đổi dữ liệu, ghi sang bảng đích, cập nhật chỉ mục hoặc đồng bộ sang một hệ thống khác. Trong lúc đó, scheduler có thể kích hoạt lần chạy kế tiếp, người vận hành có thể bấm chạy lại, runner có thể bị dừng hoặc kết nối database có thể mất ngay sau khi transaction đã commit.

Nếu không kiểm soát đồng thời, hai lần chạy có thể cùng xử lý một dữ liệu, ghi đè kết quả hoặc giữ khóa quá lâu làm nghẽn hệ thống. Nếu không kiểm soát thời lượng, một job có thể chờ khóa vô hạn, chạy quá cửa sổ bảo trì hoặc tiêu thụ hết tài nguyên. Nếu không thiết kế khả năng chạy lại, việc phục hồi sau lỗi có thể tạo dữ liệu trùng, bỏ sót bản ghi hoặc cập nhật sai trạng thái.

Trong CI/CD và vận hành dữ liệu, cần thiết kế ba cơ chế cùng nhau:

- **Khóa (locking):** xác định ai được phép xử lý một phạm vi dữ liệu hoặc tác vụ tại một thời điểm.
- **Thời lượng (duration):** giới hạn thời gian chờ, thời gian chạy, thời gian giữ khóa và thời hạn hoàn thành.
- **Khả năng chạy lại (rerun/resume):** bảo đảm tác vụ có thể tiếp tục hoặc thực hiện lại mà không tạo tác dụng phụ sai lệch.

Bài viết trình bày cách chọn phạm vi khóa, quản lý lease và fencing token, chia batch, lưu checkpoint, xử lý timeout, thiết kế truy vấn an toàn và vận hành các data job có thể phục hồi.

## 1. Nhận diện rủi ro của tác vụ dữ liệu

Tác vụ dữ liệu thường xuất hiện ở nhiều giai đoạn của vòng đời CI/CD:

- Migration schema trước hoặc sau khi deploy ứng dụng.
- Backfill dữ liệu cho cột hoặc cấu trúc mới.
- Đồng bộ dữ liệu giữa database, data warehouse và hệ thống bên ngoài.
- Reindex, rebuild materialized view hoặc tạo báo cáo.
- Xử lý hàng đợi và sự kiện.
- Xóa dữ liệu hết hạn hoặc archive dữ liệu cũ.
- Chạy lại một batch bị lỗi hoặc xử lý dữ liệu lịch sử.

Một tác vụ có thể gặp các tình huống sau:

| Tình huống | Rủi ro |
|---|---|
| Hai scheduler kích hoạt cùng job | Cùng bản ghi bị xử lý đồng thời |
| Người vận hành bấm rerun khi job cũ còn chạy | Hai tiến trình cạnh tranh tài nguyên |
| Worker chết khi đang ghi dữ liệu | Chỉ một phần công việc hoàn tất |
| Kết nối mất sau khi database commit | Caller không biết dữ liệu đã được ghi chưa |
| Transaction giữ khóa quá lâu | Request khác bị chặn, deadlock hoặc timeout |
| Job vượt cửa sổ bảo trì | Ảnh hưởng giờ cao điểm hoặc release kế tiếp |
| Checkpoint cập nhật trước dữ liệu | Lần chạy sau bỏ qua dữ liệu chưa ghi |
| Checkpoint cập nhật sau dữ liệu nhưng không nguyên tử | Có thể xử lý trùng khi bị ngắt giữa hai bước |
| Lease hết hạn trong khi worker cũ vẫn sống | Hai worker cùng tác động lên một phạm vi |

Một thiết kế tốt phải trả lời được: phạm vi nào cần độc quyền, khóa tồn tại bao lâu, điều gì xảy ra khi worker chết và lần chạy tiếp theo xác định phần việc còn lại bằng cách nào.

## 2. Phân biệt khóa, transaction và checkpoint

Ba cơ chế này liên quan nhưng giải quyết các vấn đề khác nhau.

**Khóa** kiểm soát quyền truy cập đồng thời. Ví dụ, chỉ một worker được xử lý partition orders-2026-11.

**Transaction** bảo đảm một nhóm thao tác dữ liệu được commit hoặc rollback theo ranh giới mà database hỗ trợ. Transaction giúp tránh trạng thái ghi dở trong phạm vi transaction, nhưng không tự ngăn một job logic khác chạy song song nếu hai job không tranh chấp cùng tài nguyên khóa.

**Checkpoint** ghi nhận tiến độ bền vững để tác vụ có thể tiếp tục sau khi bị gián đoạn. Checkpoint phải phản ánh dữ liệu đã hoàn tất, không chỉ phản ánh dữ liệu đã được đọc.

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Lock | Ai được xử lý phạm vi này ngay lúc này? | Lock theo job hoặc partition |
| Transaction | Những thay đổi nào phải cùng thành công? | Ghi target và đánh dấu source trong một transaction |
| Checkpoint | Đã hoàn thành đến đâu? | Batch cuối cùng đã commit |
| Idempotency | Nếu xử lý lại cùng đầu vào thì có tạo hiệu ứng trùng không? | Upsert theo business key |
| Timeout/deadline | Tác vụ được phép chờ và chạy trong bao lâu? | Lock wait 10 giây, job deadline 30 phút |

Không nên dùng một global lock để thay thế transaction, hoặc dùng checkpoint để giả định không có hai worker cùng chạy. Các cơ chế cần phối hợp theo đúng phạm vi.

## 3. Chọn phạm vi khóa phù hợp

Khóa quá rộng làm giảm khả năng song song; khóa quá hẹp có thể không bảo vệ được invariant dữ liệu.

### Khóa toàn job

Chỉ một instance của một job logic được chạy tại một thời điểm. Phù hợp khi job thay đổi một tập dữ liệu chung mà các phần không thể chia độc lập.

Ví dụ: chỉ cho phép một lần chạy rebuild-customer-index trong cùng một environment.

Ưu điểm là dễ hiểu và dễ bảo vệ. Hạn chế là một partition chậm có thể chặn toàn bộ job, kể cả khi các phần khác không xung đột.

### Khóa theo resource hoặc dataset

Khóa gắn với tài nguyên được sửa, chẳng hạn database, bảng, tenant hoặc loại dữ liệu. Cách này giúp tránh hai tác vụ không tương thích cùng sửa một tài nguyên.

Ví dụ, customer-backfill và customer-deduplicate có thể cần cùng một khóa dataset vì chúng thay đổi cùng các bản ghi. Trong khi invoice-export có thể chạy độc lập nếu chỉ đọc snapshot.

### Khóa theo partition hoặc shard

Chia dữ liệu thành các phạm vi độc lập rồi cấp khóa riêng cho từng phạm vi:

- Theo tenant.
- Theo ngày hoặc tháng.
- Theo hash bucket.
- Theo vùng hoặc shard.
- Theo dải khóa chính.

Ví dụ, worker A xử lý tenant 1-100, worker B xử lý tenant 101-200. Nếu dữ liệu và tác dụng phụ thực sự độc lập, hai worker có thể chạy song song.

### Khóa theo business key

Với một tác vụ tác động tới một thực thể nghiệp vụ, có thể khóa theo customer ID, account ID hoặc order ID. Phải xác định rõ các thao tác nào cần chia sẻ cùng một khóa để bảo vệ invariant.

Không nên khóa theo một ID kỹ thuật khác nhau nếu hai thao tác vẫn có thể cập nhật cùng dữ liệu nghiệp vụ.

### Ma trận chọn phạm vi

| Phạm vi | Mức song song | Phù hợp khi |
|---|---|---|
| Toàn hệ thống | Thấp | Tác vụ độc quyền và ảnh hưởng rộng |
| Theo job | Trung bình | Các lần chạy cùng loại không được chồng lấn |
| Theo dataset/table | Trung bình | Nhiều job có thể xung đột trên cùng dữ liệu |
| Theo partition/tenant | Cao hơn | Dữ liệu được chia độc lập và có ranh giới rõ |
| Theo bản ghi/business key | Cao | Tác vụ xử lý từng thực thể độc lập |

Bắt đầu từ invariant cần bảo vệ rồi chọn phạm vi khóa nhỏ nhất vẫn bảo đảm invariant đó. Đừng chọn phạm vi nhỏ chỉ để tăng throughput nếu nó làm mất tính nhất quán.

## 4. Các loại khóa thường dùng

### Row lock và table lock trong database

Database cung cấp khóa dòng, khóa bảng hoặc các mức khóa nội bộ khác. Chúng phù hợp để bảo vệ thao tác dữ liệu trong transaction.

Ví dụ, một transaction có thể khóa bản ghi job control trước khi chuyển trạng thái từ READY sang RUNNING. Transaction kết thúc thì khóa được giải phóng.

Ưu điểm là khóa gắn với transaction và database tự xử lý khi connection đóng hoặc transaction rollback. Hạn chế là transaction dài có thể giữ nhiều khóa, gây blocking, deadlock và tăng áp lực lên database.

### Advisory lock

Một số database hỗ trợ advisory lock: ứng dụng tự chọn một khóa logic bằng số hoặc chuỗi được ánh xạ thành số. Khóa này hữu ích khi cần điều phối một job không tương ứng trực tiếp với một dòng dữ liệu.

Ví dụ PostgreSQL có advisory lock ở cấp session và transaction. Transaction-scoped advisory lock được giải phóng khi transaction kết thúc; session-scoped lock gắn với session và cần chú ý connection pool, vì connection có thể được tái sử dụng.

Advisory lock chỉ có tác dụng nếu tất cả worker liên quan cùng tuân thủ giao thức khóa đó. Nó không tự ngăn một ứng dụng khác ghi bảng mà không lấy cùng khóa.

### Distributed lock

Distributed lock được dùng khi worker chạy trên nhiều máy hoặc nhiều node. Khóa có thể được lưu trong database, Redis, coordination service hoặc hệ thống orchestration.

Cần hiểu rõ:

- Cơ chế atomic khi acquire.
- Thời hạn lease và cách gia hạn.
- Điều gì xảy ra khi network partition.
- Cách nhận biết owner.
- Cách ngăn owner cũ tiếp tục ghi sau khi lease hết hạn.
- Cách giải phóng khóa khi job kết thúc hoặc bị hủy.

Một distributed lock chỉ an toàn khi giao thức và hệ thống đích cùng bảo vệ quyền ghi. Có khóa trong Redis nhưng database không kiểm tra owner hoặc fencing token thì worker cũ vẫn có thể ghi dữ liệu sau khi mất lease.

### Scheduler lock hoặc concurrency control

Một số scheduler và nền tảng CI có cơ chế giới hạn job chạy đồng thời, chẳng hạn concurrency group, resource group hoặc giới hạn số worker. Cơ chế này hữu ích để tránh kích hoạt trùng từ cùng scheduler.

Tuy nhiên, nó chỉ bảo vệ những job đi qua cùng cơ chế điều phối. Một người vận hành chạy script thủ công hoặc một hệ thống khác gọi cùng database vẫn có thể tạo xung đột. Ràng buộc quan trọng nên được bảo vệ thêm ở tầng dữ liệu hoặc service sở hữu tài nguyên.

## 5. Vòng đời acquire, renew và release khóa

Một giao thức khóa cần mô tả vòng đời đầy đủ.

~~~text
             Request lock
                  |
                  v
          +---------------+
          | Acquire result|
          +-------+-------+
                  |
          +-------+-------+
          |               |
       Granted          Busy
          |               |
          v               v
   Start work       Wait / skip / queue
          |
          v
   Renew if needed
          |
      +---+---+
      |       |
   Renew OK  Lease lost
      |       |
      v       v
   Continue  Stop writes
      |
      v
  Commit work
      |
      v
 Release lock
~~~

### Acquire

Acquire phải là thao tác nguyên tử. Hai worker cùng yêu cầu một khóa không được đồng thời nhận kết quả thành công.

Nếu khóa đang bận, chính sách cần được xác định:

- Chờ trong một khoảng thời gian.
- Đưa job vào queue.
- Bỏ qua lần chạy trùng nếu đã có một lần chạy đang hoạt động.
- Thất bại sớm để scheduler thử lại sau.
- Chia phạm vi thành partition khác nếu có thể.

Không chờ vô hạn. Lock wait cần có timeout riêng.

### Renew lease

Với lease có thời hạn, worker phải gia hạn trước khi hết hạn. Gia hạn chỉ thành công nếu worker vẫn là owner hợp lệ.

Nếu không gia hạn được, worker phải ngừng ghi và chuyển trạng thái sang cần đối soát. Không nên tiếp tục xử lý với giả định mình vẫn giữ khóa.

### Release

Khi hoàn tất, worker giải phóng khóa. Release cần xác minh owner để một worker cũ không vô tình xóa khóa mà worker mới đã nhận.

Nếu worker chết đột ngột, lease hết hạn hoặc database connection đóng có thể giúp thu hồi quyền. Tuy nhiên, việc thu hồi khóa không chứng minh công việc trước đó đã hoàn tất hay rollback toàn bộ; vẫn cần kiểm tra transaction và checkpoint.

## 6. Lease, heartbeat và fencing token

Lease là quyền giữ khóa trong một khoảng thời gian. Ví dụ worker nhận lease 60 giây và gửi heartbeat mỗi 20 giây. Nếu heartbeat ngừng, hệ thống có thể coi lease hết hạn và cấp cho worker khác.

Lease giải quyết việc thu hồi quyền khi worker mất tích, nhưng tạo ra một tình huống khó:

1. Worker A nhận lease và bắt đầu xử lý.
2. A bị treo hoặc mất kết nối lâu hơn thời hạn lease.
3. Lease hết hạn; worker B nhận lease mới.
4. A sống lại và tiếp tục ghi dữ liệu.
5. A và B cùng tác động lên dataset.

### Fencing token

Fencing token là số thứ tự tăng dần được cấp mỗi khi một owner mới nhận khóa. Hệ thống đích lưu token mới nhất và từ chối thao tác mang token cũ.

Ví dụ:

| Worker | Fencing token | Kết quả |
|---|---:|---|
| A | 41 | Được chấp nhận khi 41 là token mới nhất |
| B nhận lease sau | 42 | Token 42 thay thế 41 |
| A sống lại, ghi với 41 | Bị từ chối |
| B ghi với 42 | Được chấp nhận |

Token phải được cấp bởi nguồn có tính tăng đơn điệu và được kiểm tra tại nơi ghi dữ liệu. Chỉ lưu token trong log mà không kiểm tra ở database hoặc service đích thì không tạo được fencing.

### Heartbeat không thay thế timeout

Heartbeat chỉ cho biết worker còn liên lạc được với hệ thống điều phối. Nó không chứng minh worker đang tiến triển hoặc không bị deadlock. Nên theo dõi thêm progress marker, số bản ghi xử lý và thời gian từ lần commit gần nhất.

## 7. Khóa trong database: transaction ngắn và phạm vi rõ

Database lock thường là lựa chọn tốt khi dữ liệu và tiến độ được lưu trong cùng database. Tuy nhiên, khóa chỉ tồn tại trong phạm vi transaction hoặc session theo loại lock.

### Khóa dòng bằng SELECT FOR UPDATE

Ví dụ PostgreSQL:

~~~sql
BEGIN;

SELECT job_id, status
FROM data_jobs
WHERE job_id = 'daily-customer-rollup'
FOR UPDATE;

-- Kiểm tra trạng thái và cập nhật trong cùng transaction.
UPDATE data_jobs
SET status = 'RUNNING',
    started_at = CURRENT_TIMESTAMP
WHERE job_id = 'daily-customer-rollup'
  AND status IN ('READY', 'RETRYABLE');

COMMIT;
~~~

Ví dụ cần được bổ sung kiểm tra số dòng được cập nhật và xử lý trường hợp job đã RUNNING hoặc đã hoàn tất. Khóa dòng được giữ tới khi transaction kết thúc. Không giữ transaction này mở trong suốt một tác vụ xử lý hàng triệu bản ghi.

### Transaction-scoped advisory lock trong PostgreSQL

Có thể dùng pg_try_advisory_xact_lock để lấy khóa logic trong transaction:

~~~sql
BEGIN;

SELECT pg_try_advisory_xact_lock(202611, 6) AS acquired;

-- Chỉ chạy phần thao tác được bảo vệ nếu acquired = true.

COMMIT;
~~~

Cặp số trong ví dụ đại diện cho một khóa logic do ứng dụng quy ước. Nếu kết quả là false, worker không sở hữu khóa. Transaction kết thúc thì khóa tự giải phóng.

Không nên giữ transaction mở nhiều giờ chỉ để giữ advisory lock. Với tác vụ dài, hãy cân nhắc lock record có lease hoặc chia công việc thành batch có transaction ngắn.

### Session lock và connection pool

PostgreSQL còn có advisory lock ở cấp session. Khóa có thể tồn tại qua nhiều transaction cho tới khi được release hoặc session kết thúc. Khi dùng connection pool, connection có thể quay lại pool mà khóa session vẫn còn. Điều này có thể khiến worker khác không lấy được khóa hoặc một session mới vô tình kế thừa trạng thái khóa.

Nếu dùng session lock, phải bảo đảm release trong mọi đường đi và reset connection trước khi trả về pool. Với job dữ liệu thông thường, transaction-scoped lock thường dễ quản lý hơn.

## 8. Tránh deadlock và lock contention

Deadlock xảy ra khi các transaction giữ khóa và chờ khóa của nhau theo chu trình. Database thường phát hiện và hủy một transaction để phá vòng chờ.

Ví dụ:

- Transaction A khóa dòng 1, sau đó chờ dòng 2.
- Transaction B khóa dòng 2, sau đó chờ dòng 1.
- Không transaction nào có thể tiếp tục.

### Cách giảm deadlock

- Luôn lấy khóa theo cùng thứ tự, chẳng hạn tăng dần theo primary key.
- Giữ transaction ngắn.
- Không gọi API bên ngoài trong lúc giữ row lock.
- Chỉ khóa các dòng cần thiết.
- Dùng index phù hợp để tránh quét và khóa phạm vi ngoài dự kiến.
- Chọn mức isolation theo yêu cầu nhất quán, không nâng cao hơn cần thiết.
- Retry transaction bị database hủy do deadlock nếu toàn bộ transaction có thể chạy lại an toàn.

### Lock contention

Lock contention xảy ra khi nhiều worker chờ cùng một khóa. Dấu hiệu thường thấy là thời gian chờ tăng, throughput giảm và job chạy vượt dự kiến.

Có thể giảm contention bằng cách:

- Chia dataset thành partition.
- Xử lý batch nhỏ hơn.
- Rút ngắn thời gian transaction.
- Tách tác vụ đọc khỏi tác vụ ghi khi phù hợp.
- Dùng queue để điều phối thay vì để nhiều worker cùng polling một resource.
- Điều chỉnh số worker theo khả năng database.

Không nên chỉ tăng timeout để che lock contention. Nếu một transaction thường xuyên giữ khóa quá lâu, cần tìm nguyên nhân và sửa phạm vi hoặc cách xử lý.

## 9. Quản lý thời lượng: nhiều loại timeout khác nhau

Một data job không chỉ có một timeout. Nên phân biệt:

| Giới hạn | Kiểm soát điều gì | Ví dụ |
|---|---|---|
| Queue timeout | Thời gian job được phép chờ worker | Chờ tối đa 5 phút |
| Lock acquisition timeout | Thời gian chờ lấy khóa | Chờ tối đa 10 giây |
| Lease duration | Thời hạn sở hữu khóa | 60 giây, có heartbeat |
| Connection timeout | Thời gian thiết lập kết nối | 5 giây |
| Statement/query timeout | Thời gian một câu SQL được chạy | 30 giây |
| Transaction timeout | Thời gian transaction được phép tồn tại | Theo chính sách DB |
| Job deadline | Tổng thời gian từ bắt đầu tới kết thúc | 45 phút |
| Shutdown grace period | Thời gian cho phép hoàn tất batch khi bị dừng | 30 giây |

Các con số trên chỉ minh họa. Cần chọn dựa trên kích thước dữ liệu, SLA, năng lực database và cửa sổ vận hành.

### Deadline tổng và timeout từng bước

Deadline tổng giới hạn thời gian toàn tác vụ. Timeout từng bước giới hạn một lần gọi hoặc một batch. Nếu chỉ đặt timeout ở HTTP client mà không có deadline tổng, một job có thể retry nhiều lần và chạy lâu hơn dự kiến.

Nên truyền deadline hoặc thời gian còn lại qua các bước. Khi deadline gần hết, worker không bắt đầu batch mới nếu không đủ thời gian hoàn tất và commit an toàn.

### Phân biệt timeout với cancellation

Timeout có thể làm caller ngừng chờ, nhưng không nhất thiết dừng truy vấn hoặc worker ở phía server. Cancellation cần được gửi tới đúng hệ thống và xác nhận đã dừng hoặc đã đi tới ranh giới an toàn.

Khi hủy job, không nên giết process ngay giữa một thao tác ghi không rõ kết quả. Ưu tiên dừng nhận batch mới, hoàn tất hoặc rollback transaction hiện tại, ghi checkpoint rồi thoát.

## 10. Chia tác vụ dài thành batch

Một transaction kéo dài hàng giờ có thể giữ nhiều row lock, làm tăng WAL/undo log, chiếm connection và khiến rollback rất tốn kém. Với tác vụ lớn, nên chia thành batch.

Ví dụ backfill 10 triệu bản ghi theo từng nhóm 1.000 hoặc 5.000 bản ghi. Mỗi batch:

1. Chọn một phạm vi bản ghi xác định.
2. Đọc và chuyển đổi dữ liệu.
3. Ghi kết quả vào bảng đích.
4. Cập nhật trạng thái hoặc checkpoint.
5. Commit.
6. Nhả khóa.
7. Chuyển sang batch tiếp theo.

### Chọn kích thước batch

Batch quá lớn:

- Transaction lâu.
- Lock tồn tại lâu.
- Rollback tốn kém.
- Tăng áp lực memory và log.
- Khó dừng đúng hạn.

Batch quá nhỏ:

- Nhiều round trip.
- Tốn chi phí commit.
- Overhead scheduler và checkpoint lớn.
- Throughput có thể thấp.

Hãy đo thời gian xử lý và tài nguyên để chọn batch size. Có thể bắt đầu bằng kích thước vừa phải, quan sát p95 batch duration, lock wait và database load rồi điều chỉnh.

### Batch theo keyset thay vì OFFSET lớn

Với bảng lớn, phân trang bằng OFFSET cao thường phải bỏ qua nhiều dòng và có thể chậm dần. Keyset pagination dùng khóa ổn định để tiếp tục:

~~~sql
SELECT id, payload
FROM source_records
WHERE id > :last_committed_id
ORDER BY id
LIMIT :batch_size;
~~~

Cách này phù hợp khi ID tăng đơn điệu và tập dữ liệu được xác định rõ. Nếu dữ liệu có thể được thêm hoặc cập nhật trong lúc chạy, cần snapshot, watermark hoặc quy tắc xử lý bản ghi mới/late-arriving để không bỏ sót.

## 11. Checkpoint phải gắn với dữ liệu đã commit

Checkpoint cho biết tiến độ đã hoàn tất. Sai thứ tự cập nhật checkpoint là nguyên nhân phổ biến gây mất hoặc lặp dữ liệu.

### Cập nhật checkpoint trước dữ liệu là không an toàn

Giả sử worker cập nhật last_id = 5000, rồi mới ghi target. Nếu process chết sau khi cập nhật checkpoint nhưng trước khi ghi target, lần chạy sau bắt đầu từ 5001 và bỏ qua dữ liệu chưa được ghi.

### Cập nhật checkpoint sau dữ liệu nhưng tách transaction

Nếu target commit thành công rồi process chết trước khi checkpoint được cập nhật, lần chạy sau đọc lại batch cũ. Điều này an toàn chỉ khi ghi target có tính idempotent hoặc có deduplication.

### Tốt nhất: dữ liệu và checkpoint cùng transaction

Khi source, target và checkpoint cùng nằm trong một database hỗ trợ transaction chung:

~~~sql
BEGIN;

-- Ghi hoặc upsert dữ liệu của batch.
INSERT INTO target_records (source_id, payload)
SELECT source_id, payload
FROM staging_batch
ON CONFLICT (source_id)
DO UPDATE SET payload = EXCLUDED.payload;

-- Cập nhật checkpoint của đúng batch.
UPDATE data_job_checkpoint
SET last_committed_id = :batch_end_id,
    updated_at = CURRENT_TIMESTAMP
WHERE job_name = 'customer-backfill';

COMMIT;
~~~

Nếu transaction rollback, cả dữ liệu và checkpoint đều không đổi. Nếu commit thành công nhưng caller mất phản hồi, lần chạy sau đọc checkpoint đã tiến lên và không cần tạo lại batch đã hoàn tất.

Nếu source và target nằm ở hai hệ thống khác nhau, không có transaction chung, cần dùng idempotency key, outbox/inbox, batch ledger hoặc reconciliation để xử lý khoảng trống giữa hai commit.

## 12. Bảng điều khiển job và checkpoint

Một hệ thống data job có thể lưu trạng thái trong các bảng riêng.

Ví dụ cấu trúc khái niệm:

~~~sql
CREATE TABLE data_job_runs (
    run_id           UUID PRIMARY KEY,
    job_name         TEXT NOT NULL,
    scope_key        TEXT NOT NULL,
    status           TEXT NOT NULL,
    owner_id         TEXT,
    fencing_token    BIGINT,
    lease_until      TIMESTAMPTZ,
    started_at       TIMESTAMPTZ,
    heartbeat_at     TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    last_error       TEXT
);

CREATE TABLE data_job_checkpoint (
    job_name             TEXT NOT NULL,
    scope_key            TEXT NOT NULL,
    last_committed_key   TEXT,
    batch_number         BIGINT NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (job_name, scope_key)
);
~~~

Đây là schema minh họa, cần điều chỉnh kiểu dữ liệu, trạng thái và ràng buộc theo database thực tế.

### Các trường cần có

- job_name: tên tác vụ logic.
- scope_key: phạm vi khóa, ví dụ tenant hoặc partition.
- run_id: định danh lần chạy.
- status: trạng thái như READY, RUNNING, SUCCEEDED, FAILED hoặc UNKNOWN.
- owner_id: worker đang sở hữu lease.
- fencing_token: số thứ tự owner.
- lease_until: thời điểm lease hết hạn.
- heartbeat_at: lần gần nhất worker báo còn hoạt động.
- last_committed_key: vị trí dữ liệu đã commit.
- batch_number: số batch đã hoàn tất.
- last_error: thông tin lỗi đã được lọc bỏ secret.

Không nên chỉ lưu một last_processed_id nếu job có nhiều partition. Mỗi scope cần checkpoint riêng.

## 13. Claim batch an toàn với nhiều worker

Khi nhiều worker cùng xử lý một queue, có thể dùng row lock và SKIP LOCKED nếu database hỗ trợ. Mỗi worker lấy một nhóm công việc chưa được claim; worker khác bỏ qua các dòng đang bị khóa.

Ví dụ PostgreSQL:

~~~sql
BEGIN;

WITH picked AS (
    SELECT id
    FROM data_tasks
    WHERE status = 'READY'
    ORDER BY id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
UPDATE data_tasks AS task
SET status = 'RUNNING',
    claimed_at = CURRENT_TIMESTAMP
FROM picked
WHERE task.id = picked.id
RETURNING task.id, task.payload;

COMMIT;
~~~

Worker lấy danh sách task đã claim rồi xử lý. Nếu worker chết sau khi commit claim, các dòng có thể bị kẹt ở RUNNING. Vì vậy, cần thêm lease hoặc claimed_at cùng quy trình phát hiện claim hết hạn.

Khi thu hồi task hết lease, cần bảo đảm worker cũ không tiếp tục ghi kết quả. Có thể dùng fencing token hoặc version của task và kiểm tra điều kiện cập nhật ở bước commit.

### Không giữ row lock trong lúc gọi dịch vụ ngoài

Sau khi claim task, commit transaction rồi mới gọi API hoặc xử lý nặng. Giữ transaction và row lock trong suốt thời gian gọi dịch vụ bên ngoài sẽ làm tăng thời gian khóa và nguy cơ deadlock.

Khi ghi kết quả, mở transaction mới và chỉ cập nhật nếu owner/token vẫn hợp lệ.

## 14. Thiết kế tác vụ chạy lại an toàn

Khả năng chạy lại có nghĩa một job có thể được khởi chạy lại sau lỗi, bị hủy hoặc do người vận hành yêu cầu mà không làm hỏng dữ liệu.

### Dùng khóa nghiệp vụ duy nhất

Nếu mỗi bản ghi đích đại diện cho một thực thể nguồn, tạo unique constraint theo source ID hoặc business key. Khi xử lý lại, dùng upsert hoặc bỏ qua bản ghi đã tồn tại theo đúng quy tắc.

Ví dụ:

~~~sql
INSERT INTO customer_summary (
    customer_id,
    total_orders,
    calculated_at
)
VALUES (
    :customer_id,
    :total_orders,
    :calculated_at
)
ON CONFLICT (customer_id)
DO UPDATE SET
    total_orders = EXCLUDED.total_orders,
    calculated_at = EXCLUDED.calculated_at;
~~~

Upsert giúp không tạo hai dòng cho cùng customer. Tuy nhiên, nếu mỗi lần chạy lại tăng total_orders thêm một lượng thay vì gán giá trị tính toán tuyệt đối, thao tác vẫn có thể không an toàn. Nên tính kết quả từ nguồn có thể xác định và gán trạng thái đích.

### Xử lý bản ghi theo điều kiện

Với backfill, có thể chỉ cập nhật bản ghi chưa được xử lý:

~~~sql
UPDATE customer_records
SET normalized_name = normalize_name(raw_name),
    normalization_version = 2
WHERE normalization_version < 2;
~~~

Điều kiện version giúp tránh lặp lại cùng migration. Cần xác định hành vi nếu một bản ghi bị thay đổi bởi nghiệp vụ khác trong lúc backfill; có thể cần version check hoặc optimistic locking.

### Phân biệt rerun cùng đầu vào và chạy lại với đầu vào mới

Cùng một job name chưa đủ để coi hai lần chạy là cùng thao tác. Cần gắn run với:

- Source snapshot hoặc watermark.
- Phiên bản thuật toán/transform.
- Tham số đầu vào.
- Scope hoặc partition.
- Batch definition.

Nếu code transform thay đổi, có thể cần tạo một lần backfill mới với version mới thay vì tiếp tục checkpoint cũ. Không tái sử dụng checkpoint của thuật toán cũ nếu ý nghĩa dữ liệu đã thay đổi.

## 15. Watermark, dữ liệu đến muộn và snapshot nhất quán

Với tác vụ đồng bộ theo thời gian, checkpoint thường là watermark: mốc dữ liệu đã xử lý tới.

Ví dụ, job xử lý event theo created_at đến 12:00. Lần tiếp theo có thể bắt đầu từ watermark đó. Tuy nhiên, event đến muộn hoặc được cập nhật với timestamp cũ có thể bị bỏ qua nếu chỉ dùng thời gian làm checkpoint.

### Dùng watermark có khoảng lùi

Một cách là đọc lại một khoảng overlap trước watermark:

- Watermark đã commit: 12:00.
- Lần chạy mới bắt đầu đọc từ 11:55.
- Dữ liệu trùng được khử bằng event ID hoặc business key.
- Watermark mới chỉ tiến lên sau khi batch hoàn tất.

Overlap giúp bắt late-arriving data, nhưng cần deduplication để không tạo bản ghi trùng.

### Snapshot và thứ tự ổn định

Nếu dữ liệu nguồn thay đổi trong lúc job chạy, việc phân trang theo ID có thể nhìn thấy tập dữ liệu không nhất quán. Cần chọn một chiến lược:

- Database snapshot hoặc transaction isolation phù hợp.
- Source watermark bất biến.
- CDC offset hoặc log sequence.
- Version/cursor ổn định.
- Một mốc cutoff được lưu trong run metadata.

Không nên dùng CURRENT_TIMESTAMP mới ở mỗi batch làm cutoff khác nhau nếu muốn toàn bộ lần chạy xử lý cùng một phạm vi dữ liệu.

## 16. Tác vụ dữ liệu phân tán và nhiều hệ thống

Khi source và target không cùng database, transaction cục bộ không thể tự bảo đảm cả hai cùng commit.

Ví dụ pipeline đọc từ database A, ghi vào warehouse B rồi gửi message tới broker C. Nếu ghi B thành công nhưng gửi C thất bại, lần chạy sau cần biết B đã hoàn tất để không nhân đôi dữ liệu hoặc phát lại message không kiểm soát.

Các biện pháp thường dùng:

- Batch ID ổn định.
- Event ID hoặc source offset.
- Bảng ledger ghi nhận batch đã áp dụng.
- Idempotent upsert ở target.
- Transactional outbox/inbox trong từng ranh giới phù hợp.
- Reconciliation giữa source và target.
- Checkpoint theo từng sink nếu cần.

### Batch ledger

Một bảng ledger có thể ghi:

| Trường | Ý nghĩa |
|---|---|
| batch_id | Định danh batch ổn định |
| source_range | Phạm vi dữ liệu nguồn |
| transform_version | Phiên bản logic chuyển đổi |
| target | Hệ thống đích |
| status | PENDING, RUNNING, COMMITTED, FAILED |
| checksum/count | Bằng chứng dữ liệu đã xử lý |
| committed_at | Thời điểm xác nhận |

Khi retry cùng batch ID, hệ thống kiểm tra ledger và target trước khi ghi lại. Nếu ledger và target không cùng transaction, cần đối soát trường hợp target commit nhưng ledger chưa cập nhật.

## 17. Lập kế hoạch thời lượng và năng lực xử lý

Ước lượng runtime không chỉ dựa trên số bản ghi. Cần xem kích thước dữ liệu, độ phức tạp transform, index, network, contention và giới hạn tài nguyên.

Có thể đo:

- Bản ghi mỗi giây.
- Thời gian trung bình và p95 của batch.
- Lock wait time.
- Query duration.
- Số lần retry.
- Kích thước dữ liệu đọc/ghi.
- CPU, memory, I/O và network.
- Thời gian commit và checkpoint.
- Thời gian queue trước khi job bắt đầu.

### Tính thời lượng dự kiến

~~~text
estimated_runtime =
  total_records / measured_records_per_second
  + commit_overhead
  + expected_retry_time
  + lock_wait_budget
  + verification_time
~~~

Đây chỉ là mô hình sơ bộ. Với workload thay đổi theo partition hoặc có phân phối dữ liệu lệch, nên đo riêng từng scope và dùng percentile thay vì chỉ lấy trung bình.

### Deadline và cửa sổ vận hành

Nếu job phải hoàn tất trước 06:00, hãy tính cả thời gian chờ scheduler, acquire lock, xử lý, retry, verify và cleanup. Không bắt đầu batch mới khi thời gian còn lại không đủ cho batch và commit an toàn.

Có thể đặt:

- Job deadline.
- Batch deadline.
- Query timeout.
- Lock wait timeout.
- Graceful shutdown period.
- Maximum retry budget.

Các giới hạn cần phối hợp. Ví dụ, statement timeout dài hơn job deadline không giúp job hoàn tất; nó chỉ khiến database tiếp tục xử lý sau khi caller đã từ bỏ.

## 18. Hủy tác vụ và phục hồi sau crash

Hủy job không đồng nghĩa rollback toàn bộ những batch đã commit. Với batch processing, mỗi batch đã commit là một đơn vị hoàn tất riêng.

### Graceful shutdown

Khi nhận tín hiệu dừng:

1. Ngừng claim batch mới.
2. Hoàn tất hoặc rollback batch hiện tại.
3. Cập nhật checkpoint chỉ sau khi dữ liệu batch commit.
4. Ghi trạng thái PAUSED hoặc INTERRUPTED.
5. Release lock/lease nếu còn owner hợp lệ.
6. Đóng connection và giải phóng tài nguyên.
7. Cho phép scheduler tiếp tục từ checkpoint.

### Crash recovery

Nếu process chết mà không thể chạy cleanup:

- Transaction database đang mở thường sẽ rollback khi connection được phát hiện đóng.
- Lease có thể hết hạn và được worker khác tiếp nhận.
- Job record RUNNING có thể được chuyển thành STALE/RECOVERABLE sau khi kiểm tra heartbeat.
- Checkpoint cho biết batch cuối đã commit.
- Batch ledger giúp xác định target đã nhận dữ liệu hay chưa.

Không tự động đánh dấu mọi job RUNNING quá thời gian thành FAILED rồi chạy lại. Có thể worker vẫn đang chạy nhưng heartbeat bị mất tạm thời. Cần lease, fencing hoặc xác minh owner trước khi thu hồi.

## 19. Migration và backfill trong quy trình release

Data migration thường đi cùng deploy ứng dụng. Phiên bản cũ và mới có thể cùng truy cập database trong rolling deployment.

Một quy trình có kiểm soát:

1. Kiểm tra schema và dữ liệu trước migration.
2. Acquire khóa migration theo database/schema.
3. Ghi migration ID và phiên bản nguồn.
4. Thực hiện thay đổi tương thích ngược (expand).
5. Chạy backfill theo batch có checkpoint.
6. Validate số lượng, checksum và invariant dữ liệu.
7. Deploy phiên bản ứng dụng sử dụng cấu trúc mới.
8. Theo dõi lỗi và hiệu năng.
9. Chỉ contract/xóa cấu trúc cũ khi không còn phiên bản phụ thuộc.
10. Release khóa và lưu audit record.

### Không giữ global migration lock trong toàn bộ backfill dài

Có thể cần một lock ngắn để bảo đảm chỉ một migration coordinator thay đổi schema tại một thời điểm. Nhưng backfill hàng giờ nên dùng checkpoint và batch transaction ngắn. Tùy database, việc giữ một transaction/lock schema trong suốt backfill có thể chặn truy cập ứng dụng.

Cần tách phần thay đổi schema cần đồng bộ khỏi phần chuyển dữ liệu có thể chạy dần.

### Kiểm tra trước và sau

Một migration nên có tiêu chí xác minh cụ thể:

- Số bản ghi nguồn và đích.
- Số bản ghi thiếu hoặc trùng.
- Checksum theo partition.
- Ràng buộc unique và foreign key.
- Nullability và miền giá trị.
- Trạng thái version/marker.
- Thời gian query và ảnh hưởng workload.

Không chỉ dựa vào việc migration command trả exit code 0.

## 20. Quan sát khóa và thời lượng trong vận hành

Để xử lý job chậm hoặc bị kẹt, log cần cho biết worker đang chờ gì và đã xử lý tới đâu.

Mỗi lần chạy nên ghi:

- Job name, run ID và scope key.
- Owner ID, lease ID hoặc fencing token.
- Thời điểm yêu cầu, acquire, renew và release lock.
- Lock wait duration và kết quả acquire.
- Batch ID, khoảng key và số bản ghi.
- Thời gian query, transform, write và commit.
- Checkpoint trước/sau batch.
- Số lần retry và loại lỗi.
- Deadline còn lại.
- Trạng thái cuối và nguyên nhân dừng.

Không ghi dữ liệu cá nhân hoặc secret vào log chỉ để điều tra. Dùng ID, số lượng và checksum phù hợp.

### Metrics nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| job_duration_seconds | Tổng thời lượng job |
| batch_duration_seconds | Thời lượng mỗi batch |
| lock_wait_seconds | Thời gian chờ khóa |
| lock_acquire_failures_total | Số lần không lấy được khóa |
| active_job_runs | Số lần chạy đang hoạt động |
| lease_renewal_failures_total | Số lần gia hạn lease thất bại |
| records_processed_total | Tổng bản ghi đã xử lý |
| checkpoint_lag | Khoảng cách giữa nguồn mới nhất và checkpoint |
| retry_attempts_total | Số lần retry |
| stale_runs_total | Số run bị phát hiện stale |
| deadlocks_total | Số deadlock |
| data_validation_failures_total | Số lần xác minh dữ liệu thất bại |

Theo dõi theo job và scope để nhận ra một tenant hoặc partition chậm bất thường. Alert nên dựa vào ngưỡng vận hành và SLO, không chỉ dựa vào một job chạy lâu hơn trung bình.

## 21. Ví dụ quy trình backfill có thể tiếp tục

Giả sử cần chuẩn hóa tên khách hàng cho 5 triệu bản ghi. Có thể thiết kế như sau:

~~~text
Scheduler
   |
   v
Acquire lock: customer-normalization / partition-03
   |
   v
Load checkpoint and transform version
   |
   v
Claim next batch (stable key range)
   |
   v
Read source snapshot
   |
   v
Normalize and validate
   |
   v
BEGIN TRANSACTION
   |-- Upsert target by customer_id
   |-- Mark source rows/version
   |-- Update committed checkpoint
   v
COMMIT
   |
   v
Record metrics and heartbeat
   |
   +------ More rows? ------+
   |                        |
  Yes                      No
   |                        |
   v                        v
Next batch             Verify counts/checksum
                            |
                            v
                     Mark SUCCEEDED
                            |
                            v
                       Release lock
~~~

Nếu worker chết trước COMMIT, batch hiện tại rollback và checkpoint không tiến lên. Lần chạy sau xử lý lại batch đó. Nếu worker chết sau COMMIT nhưng trước khi ghi log thành công, checkpoint đã tiến lên; lần chạy sau tiếp tục từ batch tiếp theo.

Điều kiện để luồng này an toàn:

- Target có unique key theo customer ID.
- Upsert gán giá trị chuẩn hóa, không cộng dồn tác dụng phụ.
- Source marker và checkpoint nằm cùng transaction nếu cùng database.
- Transform version được lưu cùng run.
- Lock scope giới hạn ở partition-03.
- Lease và fencing ngăn worker cũ ghi sau khi mất quyền.
- Verify cuối xác nhận không thiếu hoặc trùng bản ghi.

## 22. Kiểm thử lock, timeout và khả năng chạy lại

Không nên chỉ test đường chạy thành công. Cần mô phỏng cạnh tranh và gián đoạn.

### Test lock

- Hai worker acquire cùng scope đồng thời: chỉ một worker được quyền.
- Hai worker acquire hai partition khác nhau: có thể chạy song song.
- Worker chết khi giữ lease: worker khác tiếp nhận sau khi lease hết hạn.
- Worker cũ sống lại: fencing token ngăn ghi.
- Release từ owner cũ: không xóa lock của owner mới.
- Lock contention: job chờ hoặc thất bại theo timeout đã cấu hình.

### Test duration

- Query vượt statement timeout.
- Job vượt deadline tổng.
- Lock không được giải phóng đúng hạn.
- Heartbeat mất nhưng worker vẫn chạy.
- Shutdown tới giữa batch.
- Retry budget cạn.
- Database chậm hoặc connection pool hết connection.

### Test rerun và checkpoint

- Chết trước khi ghi target.
- Chết sau target write nhưng trước checkpoint.
- Chết sau commit nhưng trước phản hồi.
- Chạy lại cùng batch ID.
- Chạy lại cùng job với transform version mới.
- Có bản ghi nguồn đến muộn.
- Hai worker claim cùng một batch.
- Checkpoint bị thiếu hoặc không khớp batch ledger.

Kết quả cần kiểm tra là trạng thái dữ liệu cuối, số side effect và checkpoint, không chỉ exit code của job.

## 23. Những anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách cải thiện |
|---|---|---|
| Không có lock cho job độc quyền | Hai lần chạy sửa cùng dữ liệu | Khóa theo job/dataset/partition |
| Dùng global lock cho mọi tác vụ | Mất khả năng song song | Chọn scope nhỏ nhất bảo vệ invariant |
| Giữ transaction hàng giờ | Blocking, deadlock, rollback lớn | Chia batch và transaction ngắn |
| Chờ lock vô hạn | Job bị kẹt không rõ nguyên nhân | Đặt lock acquisition timeout |
| Lease không có fencing | Worker cũ có thể ghi sau khi mất lease | Kiểm tra fencing token ở nơi ghi |
| Heartbeat được coi là bằng chứng tiến triển | Job treo vẫn được xem là khỏe | Theo dõi progress và commit time |
| Checkpoint cập nhật trước dữ liệu | Bỏ qua bản ghi chưa commit | Commit dữ liệu và checkpoint nguyên tử |
| Checkpoint tách transaction nhưng target không idempotent | Retry tạo dữ liệu trùng | Upsert, unique key hoặc ledger |
| Dùng OFFSET lớn cho bảng lớn | Query chậm dần | Keyset pagination hoặc partition |
| Retry mọi lỗi | Lặp lỗi không thể khắc phục | Phân loại lỗi và retry budget |
| Rerun với transform version mới nhưng dùng checkpoint cũ | Bỏ qua dữ liệu cần xử lý lại | Gắn checkpoint với transform version |
| Xóa trạng thái job để chạy lại từ đầu | Mất khả năng truy vết và gây side effect trùng | Resume/reconcile từ run record |
| Chỉ dựa vào CI concurrency group | Job từ hệ thống khác vẫn có thể chồng lấn | Bảo vệ thêm ở database/service |
| Đánh dấu job thành công ngay sau khi enqueue | Dữ liệu có thể chưa được xử lý | Chờ terminal state và verify |

## 24. Checklist vận hành tác vụ dữ liệu

### Khóa và concurrency

- [ ] Xác định invariant dữ liệu cần bảo vệ.
- [ ] Chọn lock scope theo job, dataset, partition hoặc business key.
- [ ] Acquire khóa bằng thao tác atomic.
- [ ] Có lock wait timeout và chính sách khi khóa đang bận.
- [ ] Lease có heartbeat/renew và release an toàn.
- [ ] Có fencing hoặc version check để ngăn worker cũ ghi.
- [ ] Tránh giữ transaction trong lúc gọi API hoặc xử lý ngoài database.
- [ ] Có kiểm soát deadlock, lock contention và concurrent runs.

### Thời lượng

- [ ] Có queue timeout, lock timeout, query timeout và job deadline.
- [ ] Có giới hạn số lần retry và tổng thời gian.
- [ ] Batch duration được đo và điều chỉnh.
- [ ] Có grace period khi shutdown.
- [ ] Job không bắt đầu batch mới khi không đủ thời gian commit.
- [ ] Lease duration phù hợp với heartbeat và thời gian batch.
- [ ] Có cảnh báo khi job hoặc checkpoint bị chậm.

### Khả năng chạy lại

- [ ] Mỗi run, scope và batch có định danh ổn định.
- [ ] Ghi dữ liệu có unique key hoặc cơ chế deduplication.
- [ ] Upsert gán trạng thái đích thay vì cộng dồn ngoài ý muốn.
- [ ] Checkpoint chỉ tiến sau khi dữ liệu commit.
- [ ] Dữ liệu và checkpoint cùng transaction khi có thể.
- [ ] Nếu nhiều hệ thống, có ledger/outbox/inbox hoặc reconciliation.
- [ ] Checkpoint gắn với source snapshot và transform version.
- [ ] Có xử lý late-arriving data và backfill.
- [ ] Rerun cùng đầu vào không tạo side effect trùng.

### Xác minh và audit

- [ ] Có số lượng, checksum và invariant để kiểm tra kết quả.
- [ ] Lưu run ID, batch ID, lock owner và fencing token.
- [ ] Ghi nhận thời gian acquire, wait, process, commit và release.
- [ ] Có failure injection test cho các điểm ngắt quan trọng.
- [ ] Có quy trình xử lý trạng thái UNKNOWN hoặc stale.
- [ ] Không ghi secret hoặc dữ liệu nhạy cảm vào log.

## Kết luận

Tác vụ dữ liệu an toàn cần kiểm soát đồng thời, thời lượng và tiến độ như một thiết kế thống nhất. Chọn khóa theo invariant và phạm vi nhỏ nhất phù hợp; giới hạn lock wait, query, batch và job bằng timeout/deadline; dùng lease cùng fencing token khi worker phân tán; chia việc dài thành batch có transaction ngắn; và chỉ cập nhật checkpoint khi dữ liệu tương ứng đã commit. Khi kết hợp unique key, upsert, batch ledger, snapshot/watermark và reconciliation, job có thể được chạy lại hoặc tiếp tục sau crash mà không bỏ sót hay nhân đôi dữ liệu. Cuối cùng, hãy đo lock wait, batch duration, checkpoint lag và retry để phát hiện sớm tình trạng nghẽn trước khi nó ảnh hưởng pipeline hoặc hệ thống production.

