# Đánh đổi giữa chờ khóa, hủy giao dịch, độ mới dữ liệu và thông lượng

Khi nhiều transaction cùng truy cập database, mức cô lập càng mạnh không đơn giản là “tốt hơn” trong mọi tình huống. Một lựa chọn có thể giúp các thao tác nhìn dữ liệu nhất quán hơn nhưng làm tăng thời gian giữ snapshot, chờ khóa hoặc số transaction bị hủy do xung đột. Ở chiều ngược lại, một mức cô lập cho phép nhiều thao tác chạy đồng thời có thể tăng thông lượng, nhưng ứng dụng phải chấp nhận dữ liệu đọc thay đổi giữa các câu lệnh và tự bảo vệ các bất biến nghiệp vụ quan trọng.

Bốn yếu tố cần cân nhắc là:

- **Chờ khóa (lock wait):** transaction phải đợi transaction khác nhả tài nguyên đang bị khóa.
- **Hủy giao dịch (abort):** database từ chối hoàn tất transaction vì deadlock, xung đột serialization, timeout hoặc lỗi khác; ứng dụng có thể cần chạy lại toàn bộ transaction.
- **Độ mới dữ liệu (data freshness):** dữ liệu được đọc phản ánh các commit mới đến thời điểm nào và các phần dữ liệu có cùng mốc snapshot hay không.
- **Thông lượng (throughput):** số công việc nghiệp vụ hoàn tất trong một đơn vị thời gian, không chỉ số câu SQL được gửi tới database.

Mục tiêu thiết kế là chọn cơ chế đảm bảo đúng bất biến với chi phí vận hành chấp nhận được. Không có một mức cô lập duy nhất tối ưu cho tất cả workload.

## 1. Bốn yếu tố và quan hệ giữa chúng

### Chờ khóa

Khóa giúp phối hợp các transaction khi chúng cùng muốn sửa hoặc khóa một tài nguyên. Nếu T1 giữ khóa trên hàng A trong khi T2 cần cập nhật A, T2 có thể phải đợi T1 commit hoặc rollback.

Thời gian chờ phụ thuộc vào nhiều yếu tố: transaction đang giữ khóa kéo dài bao lâu, số transaction tranh chấp, thứ tự lấy khóa, index và phạm vi dữ liệu được quét, kế hoạch thực thi và cấu hình database.

Một câu lệnh nhanh có thể trở thành một request chậm nếu nó phải chờ khóa lâu. Vì vậy, cần phân biệt **query execution time** (thời gian thực thi) và **lock wait time** (thời gian chờ khóa).

### Hủy giao dịch

Database có thể chủ động hủy một transaction để bảo vệ tính đúng đắn hoặc giải phóng hệ thống khỏi vòng chờ. Ví dụ:

- Deadlock: hai transaction chờ khóa của nhau.
- Serialization failure: sự xen kẽ không thể được chấp nhận ở mức Serializable.
- Lock timeout hoặc statement timeout: transaction/câu lệnh vượt ngưỡng thời gian.
- Constraint violation: thao tác vi phạm ràng buộc dữ liệu.
- Connection failure: session bị mất hoặc không thể tiếp tục.

Không phải mọi lỗi đều nên retry. Serialization failure thường có thể thử lại toàn bộ transaction; duplicate key do người dùng gửi ID đã tồn tại thường là lỗi nghiệp vụ cần xử lý khác.

### Độ mới dữ liệu

Một query có thể đọc dữ liệu mới đã commit, nhưng độ mới phải được hiểu theo **snapshot của nó**. Một snapshot được chốt trước commit mới nhất sẽ không tự thay đổi giữa câu truy vấn chỉ vì một transaction khác vừa commit.

Độ mới và tính nhất quán cũng là hai yêu cầu khác nhau:

- Đọc ở snapshot mới hơn có thể đưa thêm commit gần đây vào kết quả.
- Đọc nhiều câu lệnh từ một snapshot cố định có thể cho góc nhìn nhất quán, dù snapshot đó cũ hơn trạng thái mới nhất.
- Đọc từng chỉ số ở snapshot riêng có thể cho thông tin mới hơn ở mỗi chỉ số, nhưng không đảm bảo chúng cùng phản ánh một thời điểm.

### Thông lượng

Thông lượng thường được đo bằng số transaction hoàn tất thành công mỗi giây (TPS), hoặc số yêu cầu nghiệp vụ hoàn tất mỗi giây. Nó chịu ảnh hưởng bởi thời gian thực thi, khóa, I/O, CPU, mạng, pool connection, retry và transaction abort.

Nếu hệ thống nhận 1.000 request/giây nhưng 30% transaction bị hủy và retry nhiều lần, số câu lệnh xử lý có thể rất lớn trong khi số nghiệp vụ thành công vẫn thấp. Cần theo dõi cả **attempts** lẫn **successful commits**.

## 2. Isolation level là một phần của quyết định, không phải toàn bộ giải pháp

Các mức cô lập thường gặp trong SQL:

| Mức | Bảo đảm/đặc trưng khái quát | Đánh đổi cần quan tâm |
|---|---|---|
| READ UNCOMMITTED | Cho phép bảo đảm yếu nhất theo mô hình SQL; dirty read có thể được phép | Có thể quan sát dữ liệu chưa commit; một số engine nâng mức này lên cao hơn |
| READ COMMITTED | Không đọc dữ liệu chưa commit theo semantics thông thường; snapshot thường theo câu lệnh ở PostgreSQL | Nhiều câu đọc có thể nhìn các commit khác nhau; read skew/non-repeatable/phantom tùy engine |
| REPEATABLE READ | Giữ góc nhìn đọc ổn định hơn trong transaction | Snapshot có thể cũ hơn; triển khai khác nhau; write skew vẫn có thể xảy ra ở một số engine |
| SERIALIZABLE | Transaction commit thành công tương đương một thứ tự tuần tự | Có thể tăng chờ, xung đột hoặc abort/retry; chi phí phụ thuộc engine và workload |

Không nên đọc bảng này như một bảng hiệu năng cố định. Hai hệ quản trị có thể thực hiện cùng tên mức cô lập bằng cơ chế khác nhau. Một engine dùng khóa phạm vi có thể làm tăng lock wait; một engine dùng MVCC và phát hiện phụ thuộc có thể ít chặn đọc hơn nhưng hủy transaction khi thấy xung đột.

Cần biết database thực tế đang chạy, isolation được thiết lập ở đâu, transaction manager cấu hình ra sao, và driver có truyền đúng cấu hình hay không.

## 3. Locking và MVCC tạo ra những kiểu đánh đổi khác nhau

### Khóa bi quan (pessimistic locking)

Với khóa bi quan, transaction lấy khóa trước hoặc trong khi đọc/ghi để ngăn thao tác xung đột diễn ra đồng thời.

Ví dụ PostgreSQL:

```sql
BEGIN;

SELECT quantity
FROM inventory
WHERE sku = 'BOOK-01'
FOR UPDATE;

-- Kiểm tra số lượng và cập nhật khi đang giữ khóa.
UPDATE inventory
SET quantity = quantity - 1
WHERE sku = 'BOOK-01' AND quantity > 0;

COMMIT;
```

Giao dịch khác muốn khóa/sửa hàng đó có thể phải chờ. Khóa bi quan phù hợp khi xung đột xảy ra thường xuyên hoặc thao tác đọc rồi ghi cần một vùng bảo vệ rõ ràng.

Đánh đổi:

- Tạo lock wait khi nhiều transaction cùng cần tài nguyên.
- Transaction giữ khóa càng lâu, hàng đợi phía sau càng dài.
- Khóa nhiều hàng theo thứ tự khác nhau có thể tạo deadlock.
- Khóa hàng hiện có chưa chắc bảo vệ một predicate hoặc hàng chưa tồn tại.
- Nếu transaction làm việc ngoài database trong lúc đang giữ khóa, thời gian chặn có thể tăng mạnh.

### MVCC (Multi-Version Concurrency Control)

MVCC cho phép transaction đọc phiên bản dữ liệu phù hợp với snapshot thay vì luôn phải chặn một writer. Trong PostgreSQL, đọc thông thường dưới MVCC thường không chặn ghi và ghi không cần chặn mọi lần đọc thông thường.

Đánh đổi:

- Các phiên bản cũ phải được giữ khi còn snapshot cần chúng.
- Transaction dài có thể giữ snapshot lâu, làm chậm quá trình thu hồi phiên bản cũ.
- Các transaction cùng ghi một hàng vẫn có thể phải chờ/xung đột.
- Snapshot ổn định không tự giải quyết mọi bất biến nhiều hàng; write skew có thể xảy ra ở mức snapshot isolation.
- Cơ chế Serializable có thể cần phát hiện phụ thuộc và hủy transaction.

MVCC không có nghĩa “database không còn khóa”. Database vẫn dùng khóa cho ghi, DDL, locking read, ràng buộc và các tình huống điều phối khác.

### So sánh theo góc nhìn vận hành

| Câu hỏi | Khóa bi quan | MVCC / snapshot |
|---|---|---|
| Reader có phải chờ writer không? | Có thể, tùy loại khóa và engine | Đọc thông thường thường đọc phiên bản phù hợp mà không chờ writer |
| Writer có thể chờ writer không? | Có, khi cùng tài nguyên | Có, đặc biệt khi cập nhật cùng hàng |
| Làm sao bảo vệ đọc rồi ghi? | Khóa tài nguyên trước khi quyết định | Dùng isolation phù hợp, kiểm tra xung đột hoặc phối hợp khóa |
| Rủi ro transaction dài | Giữ khóa, chặn transaction khác | Giữ snapshot/phiên bản cũ, đồng thời có thể giữ khóa nếu có ghi |
| Rủi ro chính khi nhiều hàng | Deadlock và contention | Write skew/serialization conflict tùy mức và engine |

## 4. Chờ khóa: vì sao transaction ngắn quan trọng?

Giả sử T1 lấy khóa hàng A, sau đó gọi một API thanh toán mất 2 giây rồi mới cập nhật và commit. T2 và T3 cùng cần cập nhật A trong thời gian đó.

```text
T1: BEGIN
T1: UPDATE A             -> giữ khóa A
T1: gọi API ngoài        -> chờ 2 giây
T2: UPDATE A             -> chờ T1
T3: UPDATE A             -> chờ T1
T1: COMMIT
T2: tiếp tục
T3: tiếp tục
```

Nếu T1 chỉ cần 20 ms để cập nhật database nhưng giữ khóa trong 2 giây để đợi API, nó làm tăng thời gian chờ của các transaction khác đáng kể.

Các nguyên tắc giảm lock wait:

1. Giữ transaction ngắn, chỉ bao quanh các thao tác database cần nguyên tử.
2. Không chờ người dùng, gọi HTTP, gửi email hoặc xử lý tệp khi đang giữ khóa.
3. Khóa nhiều tài nguyên theo một thứ tự ổn định, ví dụ account ID tăng dần.
4. Dùng index phù hợp để tránh quét quá nhiều hàng và khóa ngoài ý muốn.
5. Kiểm tra đúng phạm vi của locking read và điều kiện WHERE.
6. Đặt timeout có chủ đích, nhưng phải hiểu timeout sẽ hủy statement hay transaction theo engine/configuration.

### Thứ tự khóa ổn định giúp giảm deadlock

Hai giao dịch chuyển tiền có thể khóa tài khoản theo thứ tự ngược nhau:

```text
T1: khóa A -> cần B
T2: khóa B -> cần A
```

Nếu cả hai giữ khóa đầu tiên, chúng đợi nhau tạo vòng chờ. Một chiến lược là luôn khóa account có ID nhỏ hơn trước:

```sql
BEGIN;

SELECT account_id, balance
FROM account
WHERE account_id IN (:accountA, :accountB)
ORDER BY account_id
FOR UPDATE;

-- Sau khi đã lấy các khóa theo cùng thứ tự, thực hiện chuyển tiền.

COMMIT;
```

Chiến lược này giảm một nguyên nhân deadlock phổ biến, nhưng không thể loại bỏ mọi deadlock: database còn nhiều loại khóa và đường thực thi khác nhau. Ứng dụng vẫn phải xử lý lỗi deadlock nếu xảy ra.

## 5. Hủy giao dịch: chi phí không chỉ là một exception

Một transaction bị hủy đã tiêu tốn tài nguyên để đọc, tính toán, lấy khóa hoặc ghi dữ liệu trước khi bị rollback. Nếu retry, phần công việc đó có thể phải thực hiện lại.

Ví dụ ở SERIALIZABLE:

```text
Lần thử 1:
  BEGIN
  đọc hạn mức
  đọc các tài khoản
  tính toán
  ghi hàng A
  serialization failure
  ROLLBACK

Lần thử 2:
  BEGIN mới
  đọc lại hạn mức
  đọc lại các tài khoản
  tính toán lại
  ghi hàng A
  COMMIT
```

Chi phí retry tăng lên theo số lần transaction bị hủy và lượng công việc phải làm lại. Nếu logic transaction dài hoặc có truy vấn tốn kém, abort rate cao có thể làm thông lượng giảm.

### Không được retry phần cuối transaction một cách máy móc

Khi serialization failure, dữ liệu mà transaction đã đọc có thể là nguyên nhân dẫn tới quyết định không còn hợp lệ. Chỉ chạy lại câu UPDATE cuối sẽ dùng quyết định dựa trên snapshot cũ.

Cách đúng là retry **toàn bộ đơn vị nghiệp vụ** trong transaction mới:

- Bắt đầu transaction mới.
- Đọc lại các hàng và điều kiện liên quan.
- Kiểm tra lại bất biến.
- Tính toán lại.
- Ghi và commit.
- Giới hạn số lần thử và có chính sách backoff khi tranh chấp cao.

### Không phải lỗi nào cũng retry được

| Nhóm lỗi | Ví dụ | Cách xử lý thường phù hợp |
|---|---|---|
| Serialization conflict | PostgreSQL SQLSTATE 40001 | Rollback và retry toàn transaction nếu nghiệp vụ cho phép |
| Deadlock victim | PostgreSQL SQLSTATE 40P01 | Retry toàn transaction có giới hạn; xem lại thứ tự khóa |
| Duplicate key | SQLSTATE 23505 ở PostgreSQL | Xác định trùng nghiệp vụ, idempotency hoặc lỗi đầu vào; không retry mù quáng |
| Check constraint violation | SQLSTATE 23514 | Sửa dữ liệu/logic hoặc trả lỗi nghiệp vụ |
| Validation failure | Số dư không đủ, hạn mức vượt | Thường trả kết quả thất bại, không retry ngay cùng dữ liệu |
| Connection loss trước/đang commit | Lỗi mạng, SQLSTATE lớp 08 hoặc timeout | Kết quả commit có thể chưa xác định; cần đối soát bằng request ID/idempotency |

### Retry cần kiểm soát

Một chính sách retry tốt cần có:

- **Giới hạn attempts:** tránh vòng lặp vô hạn.
- **Backoff:** tăng khoảng nghỉ giữa các lần thử khi hệ thống tranh chấp cao.
- **Jitter:** thêm ngẫu nhiên để nhiều request không cùng thử lại đúng một thời điểm.
- **Phân loại lỗi:** chỉ retry lỗi có thể phục hồi.
- **Idempotency:** bảo vệ tác động nghiệp vụ khỏi bị thực hiện lặp.
- **Quan sát:** ghi nhận số lần retry, lý do và kết quả cuối.

Nếu hệ thống đang quá tải, retry quá tích cực có thể tạo vòng khuếch đại: nhiều transaction thất bại làm tăng số request, gây thêm tải, khiến nhiều transaction khác thất bại hơn.

## 6. Độ mới dữ liệu và sự ổn định của snapshot

Độ mới dữ liệu không chỉ là “query có thấy commit mới nhất không”. Có ít nhất ba khía cạnh:

1. **Snapshot time:** snapshot được chốt ở thời điểm nào?
2. **Consistency scope:** một câu lệnh, một transaction, hay nhiều nguồn dữ liệu?
3. **Staleness tolerance:** nghiệp vụ cho phép kết quả cũ bao lâu?

### READ COMMITTED ở PostgreSQL

Mỗi câu SELECT thông thường dùng snapshot riêng. Nếu transaction khác commit giữa hai câu, câu sau có thể thấy dữ liệu mới hơn.

Ưu điểm:
- Các thao tác đọc tiếp theo có thể thấy commit gần đây.
- Transaction đọc không bị đóng băng ở snapshot cũ suốt vòng đời transaction.
- Thích hợp với nhiều thao tác CRUD độc lập.

Giới hạn:
- Nhiều câu lệnh có thể tạo read skew.
- Một báo cáo nhiều bước có thể ghép dữ liệu từ các thời điểm khác nhau.
- Đọc rồi ra quyết định ghi có thể cần bảo vệ mạnh hơn.

### REPEATABLE READ / snapshot cấp transaction

Trong PostgreSQL, REPEATABLE READ dùng snapshot cấp transaction cho các truy vấn thông thường. Các câu đọc tiếp theo tiếp tục nhìn trạng thái đã xác lập, ngay cả khi transaction khác commit thêm dữ liệu.

Ưu điểm:
- Báo cáo nhiều câu truy vấn có thể nhìn một snapshot ổn định.
- Ngăn non-repeatable read và phantom read theo cách PostgreSQL triển khai.
- Hạn chế read skew qua nhiều câu SELECT.

Giới hạn:
- Snapshot có thể cũ hơn trạng thái hiện tại.
- Transaction dài có thể làm tăng áp lực giữ phiên bản cũ.
- Không tự ngăn write skew trên các hàng khác nhau.
- Các xung đột cập nhật nhất định có thể khiến transaction bị hủy.

### SERIALIZABLE

Serializable bảo đảm các transaction commit thành công có hiệu ứng tương đương một thứ tự chạy tuần tự. Trong PostgreSQL, cơ chế Serializable Snapshot Isolation (SSI) theo dõi phụ thuộc nguy hiểm và có thể hủy transaction thay vì chặn tất cả thao tác ngay từ đầu.

Ưu điểm:
- Bảo vệ các bất biến có quan hệ phức tạp giữa nhiều hàng tốt hơn snapshot isolation đơn thuần.
- Ứng dụng có thể suy luận theo mô hình transaction tuần tự đối với các transaction thành công.

Giới hạn:
- Có thể phát sinh serialization failure và cần retry.
- Retry làm tăng công việc thực thi và latency.
- Transaction dài hoặc workload xung đột cao có thể làm tăng khả năng bị hủy.
- Phải đo trên workload thực tế; không thể suy ra chi phí chỉ từ tên isolation level.

## 7. Một workload minh họa: độ mới và thông lượng

Giả sử hệ thống có hai kiểu request:

- **Dashboard:** đọc nhiều chỉ số để hiển thị, chấp nhận số liệu có thể thay đổi giữa các phần và được cập nhật thường xuyên.
- **Chốt hạn mức:** đọc tổng hạn mức nhiều tài khoản và quyết định cho phép một khoản tăng mới hay từ chối.

Dùng cùng một mức cô lập cho cả hai chưa chắc là lựa chọn tốt.

| Workload | Ưu tiên | Cơ chế có thể phù hợp |
|---|---|---|
| Dashboard cập nhật nhanh | Độ mới từng chỉ số và throughput | Một query aggregate hoặc READ COMMITTED; công bố thời điểm/độ mới của số liệu |
| Báo cáo cần một mốc nhất quán | Snapshot nhất quán nhiều câu đọc | REPEATABLE READ hoặc reporting snapshot |
| Kiểm tra rồi cập nhật hạn mức chung | Bảo vệ bất biến xuyên nhiều hàng | Constraint/mô hình dữ liệu, khóa điều phối hoặc SERIALIZABLE |
| Cập nhật tồn kho cùng SKU | Không bán quá số lượng | UPDATE nguyên tử có điều kiện hoặc khóa hàng |
| Chuyển tiền hai tài khoản | Hai phía cùng commit hoặc rollback, không âm số dư | Transaction ngắn, khóa hàng theo thứ tự, constraint và kiểm tra số hàng cập nhật |

Một dashboard thường không cần khóa hàng làm chậm giao dịch nghiệp vụ. Ngược lại, chốt hạn mức không thể chỉ tăng độ mới dữ liệu bằng cách dùng READ COMMITTED nếu hai transaction có thể cùng ra quyết định trên tổng cũ và vi phạm giới hạn.

## 8. Thông lượng: vì sao concurrency cao không đồng nghĩa throughput cao?

Tăng số request chạy đồng thời có thể tăng throughput tới một điểm. Khi tài nguyên đã bão hòa hoặc contention tăng, thêm concurrency có thể làm hiệu năng xấu đi.

Ví dụ:

```text
Concurrency thấp:
  ít chờ khóa
  CPU/I/O có thể chưa được tận dụng hết
  throughput tăng khi thêm worker

Concurrency phù hợp:
  tài nguyên được sử dụng tốt
  lock wait và retry ở mức chấp nhận được
  throughput đạt vùng tốt

Concurrency quá cao:
  nhiều request tranh cùng khóa
  hàng đợi dài
  context switching, retry, timeout tăng
  latency tăng và throughput có thể giảm
```

Có thể hình dung đường throughput tăng rồi tiến tới bão hòa; sau điểm đó, contention và retry khiến lượng công việc thành công không tăng tương ứng với số request gửi vào.

### Little's Law và hàng đợi

Một quan hệ cơ bản trong hệ thống ổn định:

[
L = lambda W
]

Trong đó:

- (L): số request trung bình đang ở trong hệ thống.
- (lambda): throughput (request hoàn tất mỗi đơn vị thời gian).
- (W): thời gian trung bình một request ở trong hệ thống.

Nếu thời gian chờ khóa tăng, (W) tăng. Với lượng request vào ổn định, số request đang chờ trong hệ thống (L) cũng tăng. Connection pool có thể bị chiếm hết bởi các transaction đang đợi khóa, khiến request khác không lấy được connection dù chưa chạy câu SQL nào.

Vì thế cần quan sát latency theo percentile (p50, p95, p99), pool wait, lock wait, transaction age và throughput thành công. Trung bình latency có thể che khuất một nhóm nhỏ request bị chặn rất lâu.

## 9. Ví dụ đo đạc: query nhanh nhưng request chậm

Giả sử một request cập nhật hàng tồn kho có số liệu:

| Thành phần | Thời gian |
|---|---:|
| Chờ lấy connection từ pool | 8 ms |
| Chờ khóa hàng | 450 ms |
| Thực thi UPDATE sau khi có khóa | 4 ms |
| Commit và xử lý mạng | 3 ms |
| Tổng thời gian gần đúng | 465 ms |

Tối ưu câu UPDATE từ 4 ms xuống 2 ms chỉ tiết kiệm 2 ms. Vấn đề chính là lock wait 450 ms. Cần tìm transaction đang giữ khóa và vì sao nó chưa kết thúc, thay vì chỉ tối ưu cú pháp query.

Một trường hợp khác:

| Thành phần | Lần thử 1 | Lần thử 2 |
|---|---:|---:|
| Đọc/kiểm tra | 12 ms | 12 ms |
| Ghi | 8 ms | 8 ms |
| Kết quả | Serialization failure | Commit thành công |
| Tổng công việc ứng dụng | 20 ms | 20 ms |

Request thành công phải làm 40 ms công việc DB thay vì 20 ms, chưa tính thời gian backoff. Nếu abort rate tăng, throughput trên mỗi đơn vị CPU có thể giảm ngay cả khi không có lock wait kéo dài.

Các con số chỉ minh họa cách phân rã latency, không phải số liệu chuẩn của một hệ quản trị.

## 10. Deadlock, timeout và cấu hình cần cân nhắc

### Deadlock timeout / detection

Database có thể phát hiện deadlock và chọn transaction victim. Ở PostgreSQL, lỗi deadlock thường có SQLSTATE `40P01`. Cách giảm:
- Lấy khóa theo một thứ tự thống nhất.
- Giữ transaction ngắn.
- Tránh khóa hàng không cần thiết.
- Dùng index để thao tác nhắm đúng tập hàng.
- Xử lý retry có giới hạn cho transaction bị chọn làm victim.

Không nên chỉ tăng timeout để “chữa” deadlock. Deadlock là vòng phụ thuộc chờ; tăng thời gian chờ không loại bỏ vòng đó.

### Lock timeout và statement timeout

PostgreSQL có các thiết lập khác nhau:
- `lock_timeout`: giới hạn thời gian một câu lệnh chờ lấy khóa.
- `statement_timeout`: giới hạn tổng thời gian thực thi câu lệnh.
- `idle_in_transaction_session_timeout`: giới hạn thời gian session ở trạng thái idle trong transaction.

Chúng không có cùng semantics. Một timeout có thể làm câu lệnh lỗi và transaction hiện tại chuyển sang failed state; cần rollback hoặc phục hồi theo savepoint. Ứng dụng phải xử lý trạng thái transaction trước khi tái sử dụng connection.

### Transaction timeout ở tầng ứng dụng

Timeout HTTP hoặc timeout request phía client không nhất thiết hủy transaction tại database ngay lập tức. Client có thể đã bỏ cuộc trong khi server còn chạy. Cần liên kết cancellation, timeout database và cleanup transaction một cách rõ ràng; không giả định timeout của một tầng tự động kết thúc mọi tầng khác.

### Khác biệt giữa các database

- PostgreSQL READ COMMITTED dùng snapshot theo câu lệnh; locking read và UPDATE có semantics cụ thể khi gặp hàng bị cập nhật đồng thời.
- MySQL InnoDB sử dụng MVCC cho consistent reads; locking reads và các thao tác ghi có quy tắc khóa riêng, và REPEATABLE READ mặc định có semantics khác PostgreSQL.
- SQL Server có thể dùng khóa truyền thống hoặc row-versioning tùy isolation và các database options như READ_COMMITTED_SNAPSHOT / SNAPSHOT.
- Oracle sử dụng read consistency theo statement và cơ chế transaction consistency riêng.

Không thể chuyển nguyên một lịch lock-wait hoặc snapshot từ engine này sang engine khác mà không kiểm tra implementation và cấu hình. Khi thay database hoặc bật chế độ row versioning, phải thử lại các kịch bản concurrency quan trọng.

## 11. JDBC: quản lý isolation và retry có ranh giới rõ

Ví dụ JDBC sử dụng PostgreSQL SERIALIZABLE để bảo vệ một quyết định nhiều hàng:

```java
public void applyLimitChange(DataSource dataSource, long groupId,
                             BigDecimal increase) throws SQLException {
    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            connection.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE);

            try {
                BigDecimal currentTotal =
                        readGroupTotal(connection, groupId);

                if (currentTotal.add(increase)
                        .compareTo(new BigDecimal("10000")) > 0) {
                    connection.rollback();
                    throw new IllegalStateException("Group limit exceeded");
                }

                updateOneAccount(connection, groupId, increase);
                connection.commit();
                return;

            } catch (SQLException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }

                if (!isSerializationFailure(ex) || attempt == maxAttempts) {
                    throw ex;
                }
                // Connection đóng ở cuối try; lần thử tiếp theo lấy transaction mới.
            }
        }
    }
}

private boolean isSerializationFailure(SQLException ex) {
    for (SQLException current = ex;
         current != null;
         current = current.getNextException()) {
        if ("40001".equals(current.getSQLState())) {
            return true;
        }
    }
    return false;
}
```

Ví dụ phác thảo này nhấn mạnh các nguyên tắc:

- Mỗi attempt có transaction mới và đọc lại dữ liệu.
- Chỉ retry lỗi serialization đã phân loại, không retry mọi SQLException.
- Giới hạn số lần thử.
- Rollback khi transaction thất bại.
- Không thực hiện tác động ngoài database trong đoạn có thể chạy lại nếu chưa có idempotency.

Code thực tế cần thêm backoff, quản lý exception/wrapping của driver, kiểm tra dữ liệu đầu vào và thiết kế idempotency. Nếu connection mất phản hồi trong lúc commit, không thể mặc định rollback đã thành công; kết quả nghiệp vụ có thể cần đối soát bằng request ID.

## 12. Spring: mức cô lập, propagation và retry

Spring cho phép chỉ định isolation:

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public DashboardSummary loadDashboard() {
    // Các truy vấn hiển thị có thể chấp nhận snapshot riêng từng câu
}
```

Một thao tác bảo vệ bất biến nhiều hàng có thể chọn:

```java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void reserveCapacity(...) {
    // Đọc trạng thái, kiểm tra giới hạn và ghi trong transaction.
}
```

Nhưng annotation không tự giải quyết retry. Cần lưu ý:

- Retry phải tạo một transaction vật lý mới cho mỗi lần thử.
- Đặt vòng retry ở một bean/lớp bên ngoài transaction method để mỗi lần gọi đi qua transaction proxy như mong đợi.
- Không bắt exception rồi nuốt lỗi trong transaction nếu transaction cần rollback.
- Transaction đang tham gia vào transaction ngoài có thể không áp dụng isolation level như method con khai báo.
- Không giữ transaction trong khi chờ API ngoài hoặc người dùng.

Một cấu trúc dễ hiểu là:

```text
Retry coordinator (ngoài transaction)
   |
   +-- Attempt 1 -> transactional service -> abort 40001
   |
   +-- backoff
   |
   +-- Attempt 2 -> transactional service -> commit
```

Nếu một lần thử gửi email hoặc gọi payment provider trước khi commit, retry có thể tạo tác động trùng. Hãy dùng outbox hoặc idempotency key phù hợp; transaction database không tự rollback hành động của hệ thống bên ngoài.

## 13. Quy trình chọn giải pháp theo đặc tính workload

Có thể dùng trình tự sau khi thiết kế:

### Bước 1: Xác định bất biến nghiệp vụ

Viết chính xác điều phải luôn đúng sau commit:
- Số dư không được âm.
- Một vé không thể bán cho hai người.
- Tổng hạn mức nhóm không được vượt giới hạn.
- Một báo cáo phải khớp ở cùng một mốc dữ liệu.

Nếu chưa nêu được bất biến, chưa thể biết mức cô lập nào đủ.

### Bước 2: Xác định phạm vi đọc/ghi

Transaction có:
- Đọc và ghi cùng một hàng?
- Đọc nhiều hàng nhưng ghi một hàng?
- Đọc một predicate rồi insert hàng mới?
- Đọc nhiều bảng để ra quyết định?
- Ghi vào nhiều tài nguyên theo thứ tự khác nhau?

Phạm vi này giúp nhận diện lost update, phantom, write skew, deadlock và những phụ thuộc khác.

### Bước 3: Chọn cơ chế nhỏ nhất đáp ứng bất biến

- Một điều kiện đơn giản trên một hàng: constraint hoặc UPDATE nguyên tử.
- Đọc rồi ghi một hàng: SELECT FOR UPDATE hoặc optimistic versioning.
- Báo cáo nhiều câu lệnh cần cùng snapshot: REPEATABLE READ phù hợp với engine.
- Bất biến nhiều hàng khó khóa thủ công: SERIALIZABLE hoặc mô hình hóa một điểm đồng bộ.
- Dashboard chấp nhận không cùng snapshot: READ COMMITTED có thể phù hợp, nhưng cần hiểu độ mới và công bố rõ.

### Bước 4: Đánh giá contention và chi phí lỗi

Đo lock wait, deadlock, serialization failure, retry, pool exhaustion, p95/p99 latency và successful TPS. Nếu bật mức cô lập mạnh làm abort tăng, xem transaction nào đọc/ghi chồng lấn và liệu có thể giảm phạm vi hoặc thời gian transaction.

### Bước 5: Kiểm thử với lịch đồng thời đại diện

Không chỉ chạy một request đơn lẻ. Tạo các tình huống:
- Hai transaction cập nhật cùng hàng.
- Hai transaction lấy khóa theo thứ tự ngược.
- Một transaction đọc nhiều hàng trong khi transaction khác commit.
- Hai transaction đọc predicate rồi insert/update các hàng khác nhau.
- Timeout hoặc mất kết nối khi đang gửi commit.

Xác minh cả kết quả dữ liệu lẫn latency và số lần retry.

## 14. Bài tập suy luận

### Bài 1: Cạnh tranh trên cùng hàng

T1 và T2 cùng dùng SELECT FOR UPDATE trên một hàng inventory. T1 giữ khóa 800 ms, sau đó commit. T2 chờ 800 ms rồi cập nhật.

- Thành phần nào chi phối latency của T2?
- Tối ưu câu UPDATE từ 5 ms xuống 2 ms có giải quyết phần lớn vấn đề không?
- Làm sao tìm transaction đang giữ khóa?

### Bài 2: Snapshot và độ mới

Một dashboard chạy 5 câu SELECT dưới PostgreSQL READ COMMITTED. T1 commit cập nhật giữa truy vấn thứ hai và thứ ba.

- Dashboard có thể phản ánh dữ liệu mới ở truy vấn thứ ba không?
- Các chỉ số có cùng snapshot không?
- Khi nào cần REPEATABLE READ, khi nào có thể công bố mỗi chỉ số được cập nhật gần thời điểm riêng?

### Bài 3: Serializable và retry

Hai transaction cùng kiểm tra tổng hạn mức rồi cập nhật hai hàng khác nhau. Một transaction nhận SQLSTATE 40001.

- Vì sao database có thể hủy transaction?
- Vì sao retry chỉ câu UPDATE cuối không an toàn?
- Nêu ba điều kiện cần có của một cơ chế retry production.

### Bài 4: Throughput và concurrency

Tăng số worker từ 20 lên 100 khiến request/s đầu vào tăng gấp đôi, nhưng successful TPS giảm, p99 latency tăng và serialization failure tăng mạnh.

- Vì sao tăng concurrency lại có thể làm throughput giảm?
- Những metric nào cần kiểm tra?
- Có thể giảm contention bằng cách chia phạm vi dữ liệu hoặc thay đổi thứ tự transaction không?

### Bài 5: Chọn cơ chế

Một endpoint vừa hiển thị tổng số dư nhiều tài khoản, vừa cho phép chuyển tiền. Hãy tách yêu cầu đọc và ghi:
- Báo cáo chỉ cần một snapshot nhất quán.
- Chuyển tiền phải debit/credit cùng thành công hoặc cùng rollback.
- Quy tắc hạn mức nhóm phải luôn đúng với nhiều transaction đồng thời.

Đề xuất query, isolation và cơ chế khóa/ràng buộc cho từng yêu cầu.

## Kết luận

Chọn mức cô lập là bài toán cân bằng giữa tính đúng đắn, độ mới dữ liệu, chờ khóa, transaction abort và thông lượng. Khóa bi quan tạo điều phối trực tiếp nhưng có thể làm tăng lock wait và deadlock. MVCC giúp đọc theo snapshot mà ít chặn writer, nhưng snapshot dài gây chi phí giữ phiên bản và snapshot isolation chưa tự bảo vệ mọi bất biến nhiều hàng. Serializable bảo đảm mạnh hơn cho transaction commit thành công nhưng có thể yêu cầu retry toàn bộ transaction.

Hãy bắt đầu từ bất biến nghiệp vụ và phạm vi đọc/ghi, sau đó chọn constraint, UPDATE nguyên tử, khóa, snapshot hoặc Serializable. Đo **successful throughput, lock wait, abort/retry và latency percentile** trên workload thực tế để đánh giá. Một thiết kế tốt không chạy ở isolation mạnh nhất bằng mọi giá; nó cung cấp đúng bảo đảm cần thiết với chi phí mà hệ thống có thể vận hành ổn định.
