# Kết luận không có lỗi đồng thời chỉ vì kiểm thử tải chưa gặp lỗi

Một hệ thống có thể chạy hàng nghìn request trong bài kiểm thử tải mà không ghi nhận deadlock, lost update hay dữ liệu sai. Kết quả đó là tín hiệu tốt, nhưng chưa đủ để kết luận hệ thống không có lỗi đồng thời.

Lỗi đồng thời thường phụ thuộc vào một tổ hợp cụ thể của trạng thái dữ liệu, thứ tự câu lệnh, lịch xen kẽ giữa các transaction, isolation level, execution plan, thời điểm commit và trạng thái tài nguyên. Kiểm thử tải chỉ tạo ra một số lịch thực thi trong một khoảng thời gian hữu hạn. Nếu lịch gây lỗi hiếm không xuất hiện, hệ thống có thể vượt qua bài test dù lỗi vẫn tồn tại.

Ví dụ, hai transaction chỉ deadlock khi một transaction khóa tài khoản A rồi tài khoản B, còn transaction kia khóa B rồi A. Nếu bài kiểm thử luôn gửi các request theo cùng một thứ tự hoặc dữ liệu không tạo ra hai giao dịch đảo chiều, deadlock sẽ không xuất hiện. Tương tự, một write skew chỉ xảy ra khi hai transaction cùng đọc một invariant trước khi mỗi transaction cập nhật một hàng khác nhau. Tải lớn nhưng không tạo đúng lịch đọc/ghi vẫn có thể bỏ lỡ lỗi.

Vì vậy, cần phân biệt **không quan sát thấy lỗi trong một tập kiểm thử** với **có bằng chứng đủ mạnh rằng invariant được bảo vệ trong các lịch thực thi được phép**. Bài này giải thích giới hạn của load test, cách thiết kế kiểm thử đồng thời có chủ đích và cách xây dựng bằng chứng đáng tin cậy hơn.

## 1. Không thấy lỗi không có nghĩa là không có lỗi

Một bài kiểm thử tải trả về toàn bộ HTTP 200 và không có exception chỉ chứng minh rằng các request đã hoàn thành theo những lịch thực thi xảy ra trong lần chạy đó. Nó không chứng minh mọi lịch xen kẽ hợp lệ đều an toàn.

Hãy phân biệt ba kết quả:

| Kết quả quan sát | Điều có thể kết luận | Điều chưa thể kết luận |
|---|---|---|
| Không có exception trong test | Các lần chạy được quan sát không phát sinh exception được ghi nhận | Không có dữ liệu sai hoặc race condition |
| Không thấy deadlock trong test | Deadlock không xuất hiện trong những lịch test đã tạo | Không thể có deadlock dưới tải khác hoặc dữ liệu khác |
| Các truy vấn cuối trả dữ liệu hợp lệ | Trạng thái được kiểm tra sau test thỏa các điều kiện đã assert | Mọi invariant đều đúng trong toàn bộ quá trình và mọi lịch chạy |
| Tất cả request đều thành công | Ứng dụng không trả lỗi cho các request đã gửi | Không có lost update, duplicate effect hoặc kết quả bị ghi đè âm thầm |
| Chạy tải lâu mà không lỗi | Không quan sát thấy lỗi trong khoảng thời gian đó | Xác suất lỗi bằng 0 hoặc hệ thống đã được chứng minh đúng |

Một số lỗi đồng thời không làm request thất bại. Lost update có thể xảy ra trong khi cả hai UPDATE đều thành công. Một request tạo đơn hàng trùng có thể trả HTTP 201 bình thường. Một giao dịch thanh toán có thể được xử lý hai lần sau timeout nhưng không có exception ở service gọi. Nếu test chỉ đếm mã HTTP và exception, những lỗi này sẽ không được phát hiện.

## 2. Lỗi đồng thời phụ thuộc vào lịch thực thi

Một lịch thực thi (execution schedule) là thứ tự các thao tác của nhiều transaction được xen kẽ. Cùng một tập câu lệnh có thể cho kết quả khác nhau khi thứ tự xen kẽ thay đổi.

Ví dụ hai transaction cùng đọc và ghi một số dư:

~~~text
Trạng thái đầu: balance = 1000

Lịch 1:
  A: đọc 1000
  A: tính 1100
  A: ghi 1100
  A: commit
  B: đọc 1100
  B: tính 1300
  B: ghi 1300
  B: commit
  Kết quả: 1300

Lịch 2:
  A: đọc 1000
  B: đọc 1000
  A: tính 1100
  B: tính 1200
  A: ghi 1100
  A: commit
  B: ghi 1200
  B: commit
  Kết quả: 1200 (lost update)
~~~

Hai lịch dùng cùng hai request. Chỉ khác thời điểm xen kẽ giữa các bước đọc và ghi. Nếu test chỉ chạy request A xong rồi mới chạy B, nó sẽ chỉ quan sát lịch 1 và bỏ lỡ lịch 2.

### Những yếu tố làm thay đổi lịch

- Scheduler của hệ điều hành và thời điểm thread được chạy.
- CPU core, số worker và mức cạnh tranh.
- Connection pool có đủ connection hay đang xếp hàng.
- Độ trễ mạng giữa ứng dụng và database.
- Cache hit/miss, page read và I/O.
- Execution plan, index và số hàng thực tế.
- Lock wait, timeout và thời điểm transaction commit.
- GC pause, context switch và thread bị tạm dừng.
- Retry, backoff và thời gian xử lý của service phụ thuộc.
- Dữ liệu đầu vào và trạng thái ban đầu.

Thay đổi nhỏ về dữ liệu hoặc execution plan có thể làm thứ tự lấy khóa khác đi. Vì vậy, một lỗi không xuất hiện trên máy phát triển có thể xuất hiện ở production khi bảng lớn hơn, index khác, pool đông hơn hoặc độ trễ mạng tăng.

## 3. Vì sao tăng số request chưa chắc tăng độ bao phủ lịch lỗi?

Load test thường tăng số request đồng thời, throughput hoặc thời gian chạy. Những chỉ số đó hữu ích để đo năng lực hệ thống, nhưng số request không trực tiếp cho biết có bao nhiêu lịch quan trọng đã được tạo.

Ví dụ:

- Một triệu request chỉ đọc dữ liệu không kiểm thử đường ghi cạnh tranh.
- Một trăm nghìn request cùng cập nhật các ID khác nhau không tạo xung đột trên cùng hàng.
- Nhiều request tạo đơn hàng nhưng mỗi request dùng SKU riêng không kiểm thử unique-key race.
- Tải lớn nhưng chỉ có một worker xử lý transaction vì connection pool bị cấu hình quá nhỏ có thể vô tình tuần tự hóa thao tác.
- Một bài test chỉ dùng dữ liệu ban đầu lớn không tạo tình huống tồn kho gần bằng 0 hoặc hạn mức gần chạm trần.
- Một bài test không tạo thao tác đảo thứ tự tài nguyên có thể không phát sinh deadlock.

Do đó, cần đo **độ bao phủ trạng thái và lịch xen kẽ**, không chỉ request per second.

### Ví dụ về xác suất bỏ lỡ lỗi hiếm

Giả sử một lỗi có xác suất xuất hiện p trong mỗi lần thử độc lập và cùng phân phối. Xác suất không thấy lỗi sau n lần thử là:

~~~text
P(không thấy lỗi) = (1 - p)^n
P(thấy ít nhất một lần) = 1 - (1 - p)^n
~~~

Nếu xác suất lỗi trong mỗi lần thử là 0,001% (p = 0,00001), sau 10.000 lần thử:

~~~text
P(không thấy lỗi) = (1 - 0,00001)^10000 ≈ 90,5%
P(thấy lỗi) ≈ 9,5%
~~~

Ngay cả khi chạy 100.000 lần:

~~~text
P(không thấy lỗi) = (1 - 0,00001)^100000 ≈ 36,8%
P(thấy lỗi) ≈ 63,2%
~~~

Như vậy, một bài test có thể chạy rất nhiều lần nhưng vẫn có xác suất đáng kể bỏ lỡ một lỗi hiếm. Phép tính này chỉ là mô hình minh họa: các lần chạy thực tế thường không độc lập và không có cùng xác suất. Khi lịch lỗi phụ thuộc dữ liệu hoặc thứ tự cụ thể, giả định xác suất cố định có thể không đúng.

Điểm quan trọng là số lần chạy không biến một phép thử xác suất thành bằng chứng tuyệt đối.

## 4. Phải xác định invariant trước khi đánh giá test

Một test chỉ phát hiện được lỗi mà nó kiểm tra. Nếu chỉ assert rằng API trả 200, test có thể không phát hiện trạng thái dữ liệu sai.

Trước khi viết test, hãy mô tả invariant nghiệp vụ thành điều kiện có thể kiểm chứng:

| Nghiệp vụ | Invariant có thể kiểm tra |
|---|---|
| Tồn kho | Với mọi sản phẩm/kho, quantity không âm và số lượng bán thành công không vượt số lượng khả dụng |
| Chuyển tiền | Tổng số dư được bảo toàn, tài khoản không âm và mỗi transfer được áp dụng đúng một lần |
| Email người dùng | Không có hai tài khoản trong cùng phạm vi tenant có cùng email |
| Đặt phòng | Không có hai booking đang hoạt động của cùng phòng có khoảng thời gian chồng lấn |
| Lịch trực | Mỗi khoa luôn có ít nhất một người trực trong khoảng thời gian bắt buộc |
| Xử lý job | Một job không có hai kết quả nghiệp vụ được ghi nhận cho cùng một lần xử lý logic |
| Thanh toán | Một order không bị charge nhiều lần cho cùng một payment intent |

Sau test, truy vấn database để kiểm tra invariant. Không chỉ kiểm tra số lượng exception hoặc response status.

### Kiểm tra trạng thái cuối và tác động đã phát sinh

Một số invariant cần xem cả bảng nghiệp vụ, ledger, event/outbox hoặc bảng idempotency:

- Tồn kho cuối có âm không?
- Tổng số đơn đã xác nhận có vượt số lần giữ chỗ thành công không?
- Tổng debit có bằng tổng credit không?
- Có duplicate payment key không?
- Có event đã được publish nhưng bản ghi nghiệp vụ tương ứng không tồn tại không?
- Có job đã được đánh dấu DONE nhưng không có kết quả không?

Nếu hệ thống dùng read replica hoặc read model bất đồng bộ, truy vấn xác nhận cần đọc từ nguồn có thẩm quyền hoặc đợi đến điều kiện đồng bộ đã định nghĩa. Đọc một replica đang trễ rồi kết luận dữ liệu sai có thể tạo false positive; ngược lại, chỉ đọc cache có thể che lỗi trong database chính.

## 5. Phân biệt kiểm thử tải, stress, soak và kiểm thử lịch đồng thời

Các loại test có mục tiêu khác nhau:

| Loại test | Mục tiêu chính | Có thể phát hiện | Không tự chứng minh |
|---|---|---|---|
| Load test | Hệ thống xử lý tải dự kiến với latency/throughput nào | Pool exhaustion, timeout, deadlock hoặc dữ liệu sai nếu có assert | Mọi lịch đồng thời đều an toàn |
| Stress test | Hành vi khi vượt tải thiết kế | Queue buildup, starvation, timeout cascade, lỗi khi tài nguyên cạn | Tính đúng đắn ở mọi trạng thái |
| Soak test | Hành vi dưới tải kéo dài | Leak, transaction treo, pool cạn dần, job tồn đọng | Lỗi hiếm theo một lịch cụ thể |
| Spike test | Phản ứng khi tải tăng đột ngột | Retry storm, race quanh khởi tạo tài nguyên, pool ramp-up | Mọi interleaving của transaction |
| Deterministic concurrency test | Tạo một lịch cụ thể để kiểm tra một race | Lost update, write skew, deadlock, stale claim | Tất cả lịch có thể xảy ra |
| Property-based/stateful test | Kiểm tra invariant trên nhiều chuỗi thao tác | Tổ hợp thao tác và trạng thái khó nghĩ thủ công | Toàn bộ trạng thái nếu không gian quá lớn |
| Model checking | Duyệt trạng thái/lịch trong mô hình hữu hạn | Phản ví dụ cho mô hình và invariant đã khai báo | Code production nếu mô hình không phản ánh đúng code/config |

Không nên chọn một loại test rồi dùng nó thay thế mọi loại khác. Load test đo năng lực và có thể tạo lỗi đồng thời; deterministic test kiểm tra một lịch nguy hiểm có chủ đích; property-based test mở rộng tập thao tác; soak test tìm vấn đề phụ thuộc thời gian.

## 6. Dùng hai session để tạo lịch nguy hiểm có chủ đích

Để chứng minh một cơ chế bảo vệ hoạt động, hãy tạo hai hoặc nhiều transaction độc lập và điều khiển thứ tự bước bằng barrier/latch hoặc công cụ tương đương.

Một test cho lost update có thể:

1. Reset dữ liệu về balance = 1000.
2. Mở hai connection độc lập.
3. A và B cùng đọc balance = 1000.
4. Dùng barrier xác nhận cả hai đã đọc xong.
5. Cho A ghi 1100 và commit.
6. Cho B ghi giá trị tính từ snapshot cũ.
7. Xác nhận trạng thái cuối và đối chiếu với invariant.

Nếu code đã sửa bằng optimistic version check, cùng lịch đó phải làm một UPDATE thành công và một UPDATE có affected rows bằng 0 hoặc nhận optimistic conflict. Test cần xác nhận ứng dụng xử lý conflict đúng.

### Vì sao barrier tốt hơn sleep?

Thread.sleep(100) chỉ yêu cầu thread tạm dừng trong một khoảng thời gian. Nó không bảo đảm transaction kia đã hoàn thành bước SELECT hoặc đã giữ khóa. Trên máy chậm, thứ tự có thể khác hoàn toàn.

Barrier/latch tạo điểm đồng bộ tường minh:

~~~java
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch allowWrite = new CountDownLatch(1);

// Mỗi transaction:
var state = readCurrentState();
bothRead.countDown();
bothRead.await(timeout);
allowWrite.await(timeout);
writeUsingReadState(state);
~~~

Đây là mã giả minh họa. Test thực tế cần timeout cho mọi điểm chờ và dọn connection/transaction trong finally. Không để test treo vô hạn nếu một session bị block hoặc exception trước khi tới barrier.

## 7. Xây dựng ma trận lịch cho từng invariant

Không cần thử mọi hoán vị câu lệnh của toàn hệ thống. Hãy xác định những lịch có thể làm invariant bị phá vỡ và xây dựng test nhỏ cho từng lịch.

Ví dụ ma trận:

| Invariant | Lịch nguy hiểm cần tạo | Kết quả mong đợi |
|---|---|---|
| Tồn kho không âm | Hai request cùng đọc số lượng sát ngưỡng rồi cùng bán | Chỉ số request đủ điều kiện được chấp nhận; quantity không âm |
| Version không bị ghi đè | Hai session cùng đọc version V rồi cập nhật | Một update thành công; update dùng V cũ bị conflict |
| Email duy nhất | Hai transaction cùng kiểm tra chưa tồn tại rồi INSERT cùng email | Một bản ghi được tạo; unique constraint từ chối bản còn lại |
| Không chồng lịch phòng | Hai transaction kiểm tra cùng khoảng trống rồi INSERT hai booking overlap | Một booking được chấp nhận; constraint/serialization/guard ngăn booking còn lại |
| Ít nhất một bác sĩ trực | Hai transaction cùng đọc count = 2 rồi tắt hai hàng khác nhau | Không được commit trạng thái count = 0 |
| Không có hai worker cùng claim | Hai worker cùng lấy một job READY | Chỉ một worker nhận claim hợp lệ |
| ACK chỉ từ owner hiện tại | Worker A hết lease, B reclaim, A thức dậy và ACK | ACK của A bị từ chối |
| Không charge hai lần | Payment thành công nhưng response bị mất; client retry | Cùng idempotency key trả lại kết quả, chỉ một hiệu ứng |

Với mỗi hàng trong ma trận, cần có:

- Fixture ban đầu.
- Isolation level và cấu hình DBMS.
- Thứ tự thao tác cụ thể.
- Điểm đồng bộ.
- Assertion trên số hàng bị ảnh hưởng và lỗi.
- Assertion trên invariant cuối.
- Cleanup và reset.

## 8. Tạo dữ liệu sát biên và dữ liệu gây tranh chấp

Một bài test dùng dữ liệu dễ dàng thường không kích hoạt nhánh lỗi. Hãy chọn dữ liệu ở gần ngưỡng quyết định:

- Tồn kho bằng đúng số lượng một request muốn mua.
- Số dư bằng đúng số tiền cần rút.
- Hạn mức tín dụng chỉ còn đủ cho một trong hai request.
- Một khoa có đúng hai người trực trước khi hai transaction cùng muốn tắt trạng thái.
- Hai booking bắt đầu/ kết thúc tại cùng một biên thời gian.
- Một unique key chưa tồn tại nhưng nhiều request cùng tạo.
- Một job chỉ có một hàng READY để nhiều worker cạnh tranh.

Dữ liệu sát biên làm lộ race vì các transaction cùng có thể thấy điều kiện đúng. Tuy nhiên, phải kiểm tra cả giá trị biên hợp lệ và không hợp lệ, ví dụ requested = 0, requested âm, quantity = 0 và quantity đúng bằng requested.

### Tập dữ liệu không nên quá ngẫu nhiên

Random data hữu ích để mở rộng không gian thử, nhưng nếu không lưu seed và thao tác gây lỗi thì khó tái lập. Nên kết hợp:

1. Fixture cố định cho các lịch quan trọng.
2. Seed ngẫu nhiên được ghi lại cho property-based test.
3. Log thao tác và thứ tự sự kiện để tái phát lỗi.
4. Bộ dữ liệu tối thiểu được rút gọn từ lỗi đã tìm thấy.

Khi tìm được một race, hãy giữ lại seed, input, cấu hình DBMS và interleaving đã gây lỗi. Sau đó chuyển nó thành regression test xác định để lỗi không quay lại.

## 9. Property-based và stateful testing

Test thủ công thường kiểm tra một vài lịch đã nghĩ trước. Property-based testing tạo nhiều chuỗi thao tác từ một mô hình trạng thái rồi kiểm tra invariant sau từng bước hoặc sau mỗi transaction.

Ví dụ mô hình tồn kho:

~~~text
Model:
  initial_stock = 10
  accepted_sales = []

Operations:
  reserve(quantity)
  cancel(reservation_id)
  confirm(reservation_id)
  retry(command_id)

Property:
  database_stock >= 0
  tổng quantity đã confirm <= initial_stock
  một command_id không tạo hai reservation thành công
~~~

Framework có thể sinh nhiều sequence như reserve, cancel, retry, confirm và chạy song song trên database thật. Khi một property thất bại, framework thường có thể shrink sequence để tìm một chuỗi thao tác ngắn hơn gây lỗi.

Property-based test không tự tạo concurrency. Cần thiết kế runner có thể chạy operations trên nhiều worker/connection và điều khiển hoặc ngẫu nhiên hóa interleaving. Nếu mọi operation vẫn chạy tuần tự, nó chỉ kiểm tra logic trạng thái tuần tự.

### Stateful model cần phản ánh đúng semantics

Model đơn giản hóa có thể bỏ sót hành vi DBMS như:

- Snapshot visibility.
- Row/range/gap lock.
- Deadlock victim selection.
- Transaction rollback sau lỗi.
- Unique constraint arbitration.
- Retry và duplicate message.

Hãy ghi rõ model đang trừu tượng hóa điều gì. Khi cần kiểm chứng hành vi cụ thể, chạy integration test trên đúng DBMS/engine/version thay vì chỉ dựa vào mock repository.

## 10. Model checking và kiểm chứng lịch hữu hạn

Model checking có thể duyệt các trạng thái và interleaving trong một mô hình hữu hạn để tìm phản ví dụ cho invariant. Nó hữu ích khi quy tắc đồng thời phức tạp, ví dụ nhiều worker cùng claim job, lease hết hạn, worker cũ thức dậy và ACK.

Một mô hình có thể khai báo:

- Trạng thái của job: READY, LEASED, DONE.
- Worker A/B: idle, processing, paused.
- Lease expiry và epoch.
- Các thao tác claim, renew, complete, reclaim.
- Invariant: chỉ owner với fencing token mới nhất được ghi kết quả; job không tạo hiệu ứng nghiệp vụ trùng.

Model checker có thể tìm ra lịch như:

1. A claim epoch 4.
2. A pause.
3. Lease hết hạn.
4. B claim epoch 5 và hoàn tất.
5. A thức dậy và gửi kết quả epoch 4.
6. Nếu hệ thống đích không kiểm tra fencing token, A có thể ghi đè kết quả B.

Đây là một phản ví dụ cụ thể cho thiết kế chỉ dựa vào lease expiry. Tuy nhiên, kết quả model checking chỉ mạnh trong phạm vi mô hình và giả định đã khai báo. Nếu code, driver, isolation hoặc failure mode không được mô hình hóa, vẫn cần integration và production-like testing.

## 11. Kiểm thử trên đúng DBMS và cấu hình thực tế

Mock database thường không mô phỏng đầy đủ concurrency semantics. Một in-memory database có thể dùng isolation, lock manager hoặc execution plan khác với PostgreSQL/MySQL/SQL Server production.

Với lỗi phụ thuộc DBMS, cần chạy integration test trên:

- Đúng loại DBMS và storage engine.
- Phiên bản tương thích với production.
- Isolation level thực tế.
- Cấu hình row versioning/RCSI hoặc autocommit liên quan.
- Index và constraint tương ứng.
- Connection pool có kích thước gần cấu hình mục tiêu.
- Transaction manager và ORM/provider thực tế.

Ví dụ, test write skew trên PostgreSQL REPEATABLE READ không chứng minh SQL Server REPEATABLE READ có cùng kết quả. Test phantom trên MySQL/InnoDB cần phân biệt consistent read với locking read và xét next-key lock. Test SQL Server READ COMMITTED cần ghi rõ READ_COMMITTED_SNAPSHOT đang bật hay tắt.

Nếu production dùng read replica, partitioning hoặc nhiều datasource, test cần mô phỏng đường đọc/ghi tương ứng. Không nhất thiết tái tạo toàn bộ hạ tầng trong mọi test, nhưng phải biết giới hạn của môi trường test.

## 12. Kiểm thử dưới tải vẫn cần thiết

Dù load test không chứng minh không có race, nó vẫn rất quan trọng. Nó có thể phát hiện:

- Deadlock tăng theo throughput.
- Lock wait kéo dài khi transaction giữ tài nguyên lâu.
- Connection pool cạn.
- Retry storm sau khi DB bắt đầu từ chối transaction.
- Starvation của một nhóm request.
- Latency p95/p99 tăng do contention.
- Queue backlog hoặc lease expiry tăng.
- Tỷ lệ optimistic conflict tăng khi có nhiều người cùng sửa dữ liệu.

Để load test có giá trị cho tính đúng đắn, hãy trộn các request cùng tranh chấp một tập khóa nghiệp vụ thay vì chỉ tạo nhiều request độc lập. Ví dụ, nhiều request mua cùng một SKU hoặc cập nhật cùng một tài khoản.

Sau tải, chạy truy vấn kiểm tra invariant trên database có thẩm quyền. Nếu hệ thống có event/outbox, kiểm tra số event, consumer dedup và trạng thái workflow. Ghi lại cả lỗi được xử lý thành công sau retry; không chỉ đếm HTTP 500.

## 13. Soak test và lỗi phụ thuộc thời gian

Một số lỗi không xuất hiện trong vài phút đầu:

- Transaction mở lâu và giữ khóa đến khi pool cạn.
- Worker mất heartbeat, lease hết hạn rồi bị reclaim.
- Message retry nhiều lần và tạo duplicate effect.
- Cache hoặc read replica trễ khiến quyết định dựa trên dữ liệu cũ.
- Retry backoff đồng bộ làm nhiều worker cùng thức dậy.
- Job tích tụ đến lúc nhiều worker cùng xử lý một nhóm dữ liệu.
- Connection/session metadata rò giữa các request khi pool tái sử dụng.

Soak test giữ tải trong thời gian dài giúp phát hiện xu hướng và rò rỉ. Nên theo dõi số transaction đang mở, tuổi transaction lâu nhất, idle-in-transaction, pool active/idle/pending, retry count, job age, lease expiry và message lag.

Tuy nhiên, soak test vẫn có thể không tạo lịch hiếm. Kết quả “chạy 24 giờ không lỗi” cần được ghi đúng là không quan sát thấy lỗi trong thời gian và workload đó.

## 14. Đo đúng các tín hiệu đồng thời

Nếu chỉ theo dõi error rate tổng thể, nhiều vấn đề sẽ bị che khuất. Nên tách metric theo loại:

| Metric | Ý nghĩa |
|---|---|
| Deadlock count/rate | Số deadlock theo thời gian hoặc trên tổng transaction |
| Serialization failure count | Số transaction bị hủy để bảo toàn serializable semantics |
| Lock wait duration | Thời gian chờ khóa; nên có p50/p95/p99 và wait theo resource |
| Lock timeout count | Số request hết thời gian chờ khóa |
| Optimistic conflict count | Số update có version không khớp |
| Conditional update zero-row count | Số lần điều kiện nghiệp vụ không còn đúng tại thời điểm ghi |
| Retry attempts per operation | Phân phối số lần thực hiện, không chỉ số retry trung bình |
| Retry exhausted count | Số đơn vị nghiệp vụ hết giới hạn thử lại |
| Duplicate suppression count | Số event/command lặp bị inbox hoặc idempotency chặn |
| Transaction age | Tuổi transaction đang mở và transaction lâu nhất |
| Pool pending/acquire time | Mức cạnh tranh connection pool |
| Invariant violation count | Số lần phát hiện trạng thái dữ liệu vi phạm quy tắc |

Metric zero không chứng minh không có lỗi nếu instrumentation không bao phủ đường ghi. Cần xác minh mọi datasource, service, batch, trigger, worker và script có thể thay đổi dữ liệu đều được quan sát hoặc có constraint bảo vệ.

### Log đủ để tái dựng một sự cố

Một bản ghi chẩn đoán hữu ích có thể gồm:

~~~text
timestamp
request_id / trace_id / job_id
service / operation
database / session_id / transaction_id
transaction_attempt
isolation_level
statement_fingerprint
resource / wait_type / blocker
rows_affected
commit_or_rollback
error_code
retry_delay
final_outcome
~~~

Không ghi toàn bộ payload hoặc tham số nhạy cảm chỉ để tăng khả năng điều tra. Dùng statement fingerprint, correlation ID và dữ liệu đã redaction.

## 15. Phân biệt lỗi thật với lỗi test hoặc lỗi quan sát

Một bài test có thể báo lỗi vì chính harness, hoặc bỏ lỡ lỗi do instrumentation không đầy đủ.

| Vấn đề | Dấu hiệu | Cách kiểm tra |
|---|---|---|
| Không tạo được concurrency | Chỉ có một connection thực sự chạy transaction tại một thời điểm | Ghi connection ID, pool active count và transaction begin |
| Autocommit ngoài ý muốn | Khóa được giải phóng ngay sau statement | Kiểm tra autocommit và transaction boundary |
| Barrier không đồng bộ đúng | Một transaction đi qua điểm chờ trước transaction còn lại | Ghi timestamp/event cho từng barrier |
| Test đọc replica trễ | Trạng thái cuối chưa phản ánh commit mới | Xác nhận nguồn đọc và replication lag |
| Log mất event | Không thấy deadlock dù DBMS đã chọn victim | Bật nguồn deadlock event/log đúng DBMS và kiểm tra retention |
| Exception bị framework bọc | Class exception không khớp classifier | Kiểm tra cause chain, SQLSTATE và vendor code |
| Assertion quá yếu | API thành công nhưng dữ liệu sai không bị phát hiện | Assert invariant và bảng ledger/event |
| Cleanup không hoàn tất | Transaction trước ảnh hưởng bài tiếp theo | Rollback, kiểm tra session và reset fixture |
| Môi trường DB khác production | Test pass nhưng behavior thực tế khác | Ghi DBMS/version/engine/isolation/config |

Khi test pass bất thường, hãy xác minh rằng nó thực sự đã tạo lịch nguy hiểm. Ví dụ, test deadlock phải chứng minh có hai session giữ hai tài nguyên theo thứ tự ngược nhau trước khi yêu cầu tài nguyên còn lại. Nếu không có điều kiện đó, việc không thấy deadlock không nói lên nhiều điều.

## 16. Đặt ngưỡng kết luận dựa trên bằng chứng

Thay vì viết “hệ thống không có lỗi đồng thời”, báo cáo kiểm thử nên nói rõ phạm vi đã kiểm tra:

- Invariant nào được kiểm tra?
- Đường ghi nào nằm trong phạm vi?
- DBMS/version/engine/isolation nào được dùng?
- Những lịch nguy hiểm nào được tạo tường minh?
- Bao nhiêu lần chạy ngẫu nhiên và với seed nào?
- Tải, thời gian chạy và phân phối dữ liệu ra sao?
- Có deadlock/serialization/retry không và tỷ lệ thế nào?
- Trạng thái cuối đã được kiểm tra bằng nguồn dữ liệu nào?
- Những giả định hoặc đường đi nào chưa được kiểm tra?

Ví dụ kết luận có cơ sở:

> Trong integration test với PostgreSQL phiên bản đã ghi nhận, hai lịch cạnh tranh trên tồn kho và lịch write skew cho lịch trực đã được tạo bằng hai connection độc lập. Conditional UPDATE và SERIALIZABLE giữ invariant trong các lịch đó. Load test 30 phút với workload mô phỏng 500 worker không ghi nhận invariant violation; có 12 serialization retry và không có retry exhaustion. Kết quả không chứng minh mọi lịch có thể xảy ra đều an toàn, nhưng cung cấp bằng chứng cho các invariant và workload trong phạm vi test.

Ví dụ kết luận không đủ cơ sở:

> Đã chạy 100.000 request không có lỗi nên hệ thống không có race condition.

Kết luận thứ nhất mô tả môi trường, lịch, invariant và giới hạn. Kết luận thứ hai suy rộng quá mức từ một phép thử hữu hạn.

## 17. Regression test sau khi tìm được race

Khi phát hiện lỗi đồng thời, đừng chỉ sửa code rồi chạy lại load test. Hãy giữ lại một regression test tái tạo được lịch đã gây lỗi.

Quy trình:

1. Lưu fixture và trạng thái ban đầu.
2. Ghi lại DBMS/version/isolation/index/config.
3. Ghi thứ tự thao tác của từng session hoặc worker.
4. Dùng barrier để tạo lại interleaving.
5. Assert lỗi xuất hiện ở phiên bản code cũ hoặc assert invariant ở phiên bản đã sửa.
6. Assert affected rows, exception và trạng thái cuối.
7. Đưa test vào CI với timeout và cleanup rõ ràng.

Một regression test xác định giúp bảo vệ chính lỗi đã tìm thấy. Sau đó vẫn cần property-based/load/soak test để tìm những lịch khác.

### Lưu lại seed và lịch sự kiện

Với test ngẫu nhiên, log:

- Random seed.
- Danh sách command và input.
- Worker/transaction ID.
- Thứ tự bắt đầu/kết thúc thao tác.
- Barrier event.
- Kết quả commit/rollback.
- Error code và retry attempt.

Nếu lỗi chỉ xuất hiện trong CI, những thông tin này giúp tái phát trên máy phát triển hoặc môi trường debug. Không chỉ lưu stack trace cuối vì nó thường không cho biết transaction kia đã làm gì trước đó.

## 18. Ví dụ tổng hợp: test tải không phát hiện lỗi đặt phòng

Giả sử phòng 20 chưa có booking trong khoảng 13:00–14:00. Hai request đồng thời muốn đặt cùng khoảng đó.

Code ban đầu:

~~~text
SELECT booking
WHERE room_id = 20
  AND start_at < requested_end
  AND end_at > requested_start

if no overlap:
    INSERT booking
~~~

Một load test có thể chạy 10.000 request nhưng mỗi request chọn phòng hoặc khung giờ khác nhau. Không có overlap và không có lỗi.

Lịch nguy hiểm:

~~~text
Session A                           Session B
  SELECT overlap -> 0
                                      SELECT overlap -> 0
  INSERT booking A
                                      INSERT booking B
  COMMIT
                                      COMMIT
~~~

Nếu không có constraint hoặc cơ chế bảo vệ predicate, cả hai booking có thể được commit.

Một cách bảo vệ tùy DBMS:

- PostgreSQL có thể dùng exclusion constraint trên room_id và time range.
- Có thể khóa guard row của phòng trước khi kiểm tra và insert.
- Có thể dùng SERIALIZABLE và xử lý serialization failure.
- Có thể mô hình hóa các slot thời gian thành khóa duy nhất nếu quy tắc nghiệp vụ phù hợp.

Test sau khi sửa phải tạo đúng lịch trên và assert chỉ một booking được chấp nhận. Load test bổ sung kiểm tra latency và contention khi nhiều request đặt cùng phòng, nhưng regression test xác định mới chứng minh được race cụ thể đã được xử lý.

## 19. Ví dụ tổng hợp: test tải không phát hiện duplicate payment

Một payment request được gửi đến provider. Provider xử lý thành công nhưng response bị mất. Client retry với một request mới.

Load test bình thường có thể không tạo tình huống response mất sau khi provider commit. Tất cả request đều nhận response thành công và không có duplicate.

Lịch lỗi:

1. Client gửi charge.
2. Provider commit khoản charge.
3. Response bị mất.
4. Client timeout.
5. Client retry.
6. Provider nhận một yêu cầu mới và charge lần hai nếu không có idempotency.

Test cần fault injection để làm mất response sau khi provider đã ghi nhận hiệu ứng. Sau đó gửi lại cùng idempotency key và assert chỉ có một payment intent/charge.

Đây là lỗi phối hợp liên hệ thống, không phải chỉ là lock race trong database. Một load test database thuần túy sẽ không bao phủ failure window này.

## 20. Những kết luận sai thường gặp

| Kết luận sai | Vì sao không đúng | Cách phát biểu có căn cứ hơn |
|---|---|---|
| Không thấy deadlock nên không có deadlock | Lịch tạo vòng chờ có thể chưa xuất hiện | Không ghi nhận deadlock trong workload và thời gian test đã nêu |
| Mọi request đều 200 nên dữ liệu đúng | Lost update có thể âm thầm thành công | Các invariant đã kiểm tra đều giữ trong phạm vi fixture/lịch test |
| Một triệu request là đủ | Số request không đo độ bao phủ lịch | Đã chạy N request với phân phối dữ liệu và mức cạnh tranh cụ thể |
| Chạy lâu không lỗi chứng minh an toàn | Lỗi có thể phụ thuộc lịch hiếm hoặc trạng thái hiếm | Soak test không ghi nhận lỗi trong thời gian và điều kiện đã mô tả |
| Mock repository pass nên DB concurrency đúng | Mock không mô phỏng lock/isolation thực tế | Integration test trên đúng DBMS đã xác nhận semantics cụ thể |
| Retry làm lỗi biến mất nên đã sửa | Retry có thể chỉ che deadlock hoặc lặp side effect | Retry phục hồi trong test; nguyên nhân contention và tỷ lệ retry vẫn được theo dõi |
| Không có exception nên không có conflict | Conditional UPDATE có thể trả 0 hàng mà không ném exception | Đã assert affected rows và xử lý conflict đúng |
| Chỉ kiểm tra trạng thái cuối là đủ | Một số tác động ngoài hoặc trạng thái trung gian không được lưu trong bảng cuối | Kiểm tra ledger, outbox/inbox, event và invariant liên quan |

## 21. Checklist đánh giá bằng chứng kiểm thử đồng thời

Trước khi kết luận về tính đúng đắn, hãy xác nhận:

1. Invariant nghiệp vụ đã được viết thành điều kiện có thể assert chưa?
2. Các đường ghi có thể ảnh hưởng invariant đã nằm trong phạm vi kiểm tra chưa?
3. Test có dùng đúng DBMS, engine, version và isolation level không?
4. Có ít nhất hai connection/transaction thực sự chạy đồng thời không?
5. Các lịch nguy hiểm đã được tạo bằng barrier/latch thay vì chỉ dựa vào timing ngẫu nhiên chưa?
6. Dữ liệu có bao gồm các giá trị sát ngưỡng và khóa nóng không?
7. Có kiểm tra affected rows, conflict, deadlock, serialization failure và retry exhaustion không?
8. Có assert trạng thái database cuối và tác động phụ như ledger/event/payment không?
9. Có kiểm tra transaction cleanup, connection pool và session state không?
10. Load/stress/soak test có workload và thời lượng được ghi lại không?
11. Random seed, interleaving và DBMS diagnostics có được lưu để tái lập không?
12. Kết luận có nêu rõ giới hạn và phần chưa được kiểm tra không?

## 22. Nguyên tắc kết luận

Kiểm thử tải không gặp lỗi là một kết quả quan sát có giá trị, nhưng không phải bằng chứng rằng hệ thống không có lỗi đồng thời. Một race condition có thể phụ thuộc vào lịch rất hiếm, dữ liệu sát biên, một thứ tự khóa cụ thể hoặc một failure window giữa hai hệ thống. Tăng số request không bảo đảm tạo được các điều kiện đó.

Hãy bắt đầu từ invariant, tạo lịch cạnh tranh có chủ đích bằng nhiều session độc lập, dùng barrier để tái lập interleaving và kiểm tra trạng thái dữ liệu chứ không chỉ response/exception. Kết hợp deterministic concurrency test với property-based, load, stress và soak test; chạy trên DBMS và cấu hình gần production; lưu seed, log và deadlock/lock evidence để tái phát lỗi.

Khi báo cáo, hãy mô tả chính xác invariant, workload, số lần chạy, DBMS, isolation, lịch đã tạo và kết quả quan sát. Có thể nói hệ thống đã vượt qua các kiểm thử trong phạm vi xác định; không nên suy ra rằng lỗi đồng thời không thể xảy ra chỉ vì một lần kiểm thử tải chưa bắt gặp chúng.
