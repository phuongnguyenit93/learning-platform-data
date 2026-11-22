# Đo thông lượng, độ trễ và tỷ lệ giao dịch thành công

Đánh giá hiệu năng đồng thời của cơ sở dữ liệu cần trả lời ba câu hỏi: hệ thống hoàn tất được bao nhiêu transaction trong một đơn vị thời gian, mỗi transaction mất bao lâu và bao nhiêu yêu cầu thực sự thành công. Một con số TPS cao chưa đủ chứng minh hệ thống khỏe nếu độ trễ p99 tăng mạnh, deadlock thường xuyên hoặc nhiều transaction bị từ chối rồi retry.

Đo đúng cần phân biệt transaction logic với lần thử thực thi, thời điểm bắt đầu với thời điểm commit được xác nhận, và tải mà client gửi với công việc database thực sự hoàn tất. Kết quả cũng phải đi cùng bối cảnh: số worker, workload, dữ liệu, isolation level, cấu hình connection pool và giới hạn tài nguyên.

## 1. Ba nhóm chỉ số cốt lõi

### 1.1. Thông lượng (throughput)

Thông lượng cho biết hệ thống hoàn tất bao nhiêu đơn vị công việc trong một khoảng thời gian. Với transaction, đơn vị thường dùng là transaction mỗi giây (TPS):

\[
TPS = \frac{\text{số transaction hoàn tất}}{\text{thời gian đo tính bằng giây}}
\]

Khi đánh giá tính đúng đắn, nên tính riêng số transaction commit thành công. Số câu SQL thực thi hoặc số transaction được gửi đến database không đồng nghĩa với số transaction thành công.

Ví dụ, trong 60 giây có 48.000 transaction được xác nhận commit:

\[
TPS_{success} = \frac{48.000}{60} = 800
\]

Nếu client gửi 55.000 yêu cầu nhưng 3.000 yêu cầu thất bại và 4.000 yêu cầu còn đang chạy khi phép đo kết thúc, không được ghi nhận 55.000 là transaction thành công.

### 1.2. Độ trễ (latency)

Độ trễ là thời gian một đơn vị công việc mất từ mốc bắt đầu đã định nghĩa đến mốc kết thúc tương ứng. Với transaction, mốc kết thúc hữu ích thường là khi client nhận được xác nhận `COMMIT` thành công.

Độ trễ cần được xem dưới dạng phân phối, không chỉ một giá trị trung bình. Các percentile thường dùng:

| Chỉ số | Ý nghĩa |
|---|---|
| p50 | Một nửa số transaction có độ trễ bằng hoặc thấp hơn giá trị này. |
| p90 | 90% transaction hoàn tất trong hoặc dưới giá trị này. |
| p95 | 95% transaction hoàn tất trong hoặc dưới giá trị này. |
| p99 | 99% transaction hoàn tất trong hoặc dưới giá trị này; hữu ích để thấy đuôi độ trễ. |
| p99.9 | Cho thấy những trường hợp rất chậm khi số mẫu đủ lớn. |
| max | Mẫu chậm nhất; nhạy với một sự kiện đơn lẻ nhưng vẫn có giá trị điều tra. |

Nếu p50 là 12 ms nhưng p99 là 2,5 giây, phần lớn transaction nhanh nhưng một nhóm nhỏ đang chịu chờ khóa, tranh chấp tài nguyên hoặc pause ở tầng ứng dụng. Chỉ báo cáo trung bình có thể che khuất vấn đề này.

### 1.3. Tỷ lệ giao dịch thành công

Tỷ lệ thành công đo phần công việc logic được hoàn tất đúng yêu cầu trong tổng số yêu cầu hợp lệ đã được chấp nhận:

\[
Success\ Rate = \frac{\text{số yêu cầu logic thành công}}{\text{số yêu cầu logic được chấp nhận}} \times 100\%
\]

Ví dụ, hệ thống nhận 10.000 yêu cầu logic, 9.850 yêu cầu được xác nhận hoàn tất và 150 yêu cầu kết thúc thất bại:

\[
Success\ Rate = \frac{9.850}{10.000} \times 100\% = 98,5\%
\]

Hãy định nghĩa rõ “thành công”. Một câu lệnh `UPDATE` ảnh hưởng một hàng nhưng transaction chưa commit không phải một transaction thành công. Một transaction commit nhưng vi phạm invariant do lỗi thiết kế cũng không phải kết quả thành công về mặt nghiệp vụ.

## 2. Phân biệt transaction logic và transaction attempt

Một yêu cầu logic có thể được thử nhiều lần do deadlock, serialization failure hoặc lỗi mạng tạm thời. Cần theo dõi hai cấp:

- **Logical transaction/request:** thao tác nghiệp vụ mà người dùng hoặc hệ thống yêu cầu, ví dụ chuyển tiền một lần.
- **Attempt:** một lần mở transaction database và thử thực hiện thao tác đó. Một logical request có thể có nhiều attempt.

Ví dụ:

```text
Logical request #R42: chuyển 100 từ A sang B
   |
   +-- Attempt 1: deadlock -> rollback
   |
   +-- Attempt 2: serialization failure -> rollback
   |
   +-- Attempt 3: commit thành công
```

Nếu chỉ đo attempt, ta có thể báo ba lần thử và hai lần lỗi. Nếu chỉ đo logical request, ta báo một yêu cầu thành công nhưng bỏ lỡ chi phí retry. Cả hai góc nhìn đều cần thiết:

| Chỉ số | Cách đếm |
|---|---|
| Logical request success rate | Số yêu cầu nghiệp vụ thành công / số yêu cầu được chấp nhận. |
| Attempt success rate | Số attempt commit thành công / tổng attempt đã kết thúc. |
| Retry rate | Số attempt bổ sung do retry / số logical request hoặc tổng attempt, tùy định nghĩa được công bố. |
| Attempts per request | Tổng attempt / số logical request. |
| Final failure rate | Số yêu cầu logic cuối cùng thất bại / số yêu cầu được chấp nhận. |

Không gộp lỗi deadlock đã được retry thành công với lỗi nghiệp vụ cuối cùng. Hãy báo cáo riêng số lỗi cạnh tranh, số lần retry và số yêu cầu cuối cùng thất bại.

## 3. Xác định ranh giới đo độ trễ

Độ trễ chỉ có ý nghĩa khi mốc bắt đầu và kết thúc được định nghĩa nhất quán. Với một transaction qua connection pool, có thể tách thành các khoảng:

```text
Yêu cầu đến
   |
   +-- Chờ lấy connection từ pool
   |
   +-- Bắt đầu transaction
   |
   +-- Thực thi các câu SQL
   |       +-- Thời gian chạy CPU/I/O
   |       +-- Thời gian chờ khóa
   |
   +-- Gửi COMMIT và chờ xác nhận
   |
   +-- Hoàn tất transaction
```

Nên thu thập ít nhất:

1. **End-to-end latency:** từ lúc hệ thống nhận yêu cầu đến khi trả kết quả cho caller.
2. **Pool acquisition latency:** thời gian chờ connection.
3. **Transaction latency:** từ khi bắt đầu attempt hoặc `BEGIN` đến khi nhận xác nhận commit/rollback.
4. **Statement latency:** thời gian từng câu SQL hoặc nhóm câu lệnh.
5. **Commit latency:** từ lúc gửi commit đến khi client nhận xác nhận.
6. **Retry/backoff time:** thời gian tiêu tốn cho các lần thử lại và khoảng chờ giữa chúng.

Nếu chỉ đo thời gian câu `UPDATE`, bạn sẽ bỏ qua thời gian chờ connection, các lần đọc trước đó, khóa, commit và retry. Nếu chỉ đo end-to-end, bạn thấy trải nghiệm tổng thể nhưng khó biết bottleneck ở tầng nào. Hãy dùng cả metric tổng hợp và metric thành phần.

Với một API sử dụng transaction, mốc bắt đầu end-to-end thường là khi request được nhận tại service; mốc kết thúc là khi response được tạo và gửi đi theo định nghĩa telemetry của hệ thống. Mốc transaction nên bắt đầu trước `BEGIN` hoặc trước lần gọi đầu tiên có thể tự động mở transaction, và kết thúc sau khi commit/rollback đã được xác nhận.

## 4. Công thức và ví dụ tính toán

Giả sử một phép đo kéo dài 5 phút:

- 150.000 logical request được chấp nhận.
- 147.000 request thành công.
- 3.000 request cuối cùng thất bại.
- 155.500 attempt đã được thực hiện do một số request retry.
- 147.000 attempt commit thành công; phần còn lại thất bại hoặc bị hủy.

Thông lượng thành công:

\[
TPS_{success} = \frac{147.000}{300} = 490
\]

Tỷ lệ thành công theo logical request:

\[
Success\ Rate = \frac{147.000}{150.000} \times 100\% = 98\%
\]

Số attempt trung bình trên mỗi logical request:

\[
Attempts/request = \frac{155.500}{150.000} \approx 1,037
\]

Retry rate theo số attempt bổ sung trên logical request:

\[
Retry\ Rate = \frac{155.500 - 150.000}{150.000} \times 100\% \approx 3,67\%
\]

Các công thức retry rate có thể khác giữa tổ chức. Điều quan trọng là ghi rõ mẫu số: tỷ lệ request phải retry, tỷ lệ attempt là retry hay số attempt bổ sung trên logical request.

## 5. Đo latency bằng phân phối và histogram

Để tính percentile đáng tin cậy, cần lưu phân phối độ trễ bằng histogram hoặc một hệ thống lưu trữ mẫu có hỗ trợ percentile. Không nên lấy trung bình các p99 theo từng phút để suy ra p99 của cả giờ; percentile không có tính kết hợp tuyến tính như tổng và số lượng.

Histogram chia độ trễ vào các bucket. Ví dụ:

| Bucket | Số transaction |
|---|---:|
| 0–10 ms | 12.000 |
| 10–25 ms | 28.000 |
| 25–50 ms | 35.000 |
| 50–100 ms | 18.000 |
| 100–250 ms | 5.000 |
| 250 ms–1 s | 1.500 |
| Trên 1 s | 500 |

Bucket cần đủ chi tiết ở vùng latency mục tiêu và vùng đuôi. Nếu tất cả giá trị trên 100 ms nằm trong một bucket, bạn không thể phân biệt p99 là 110 ms hay 5 giây.

Khi hệ thống telemetry dùng histogram có bucket tích lũy, percentile được ước lượng từ số lượng quan sát trong các bucket. Khi dùng HDR Histogram hoặc cấu trúc tương tự, cần cấu hình dải giá trị và độ chính xác phù hợp với latency thực tế.

## 6. Throughput và latency thay đổi theo concurrency

Khi tăng số worker đồng thời, throughput thường tăng lúc đầu vì database có thêm việc để thực hiện trong khi một số worker chờ I/O. Sau một điểm, tài nguyên bắt đầu bão hòa. Throughput có thể chững lại, trong khi latency và lỗi tăng nhanh.

Một đường cong khái niệm:

```text
Throughput
   ^                    __________
   |                ___/
   |            ___/
   |        ___/
   |    ___/
   +--------------------------------> Concurrency
                         vùng bão hòa
```

Latency thường có hình dạng ngược về mức độ tăng:

```text
Latency
   ^                         /
   |                       _/
   |                    __/
   |                ___/
   |___________ ___/
   +--------------------------------> Concurrency
                         vùng chờ tăng mạnh
```

Ở concurrency thấp, thêm worker có thể tăng mức sử dụng CPU và I/O. Khi CPU, storage, connection pool, lock manager hoặc một hàng dữ liệu nóng đạt giới hạn, worker bổ sung chủ yếu tạo thêm hàng đợi. Vì vậy, không nên mặc định càng nhiều connection càng tốt.

## 7. Little's Law và mối quan hệ giữa concurrency, throughput, latency

Trong một hệ thống ổn định, Little's Law mô tả quan hệ:

\[
L = \lambda W
\]

Trong đó:

- `L`: số công việc trung bình đang ở trong hệ thống (in-flight work).
- `λ`: tốc độ đến hoặc hoàn tất trung bình trong trạng thái ổn định.
- `W`: thời gian trung bình một công việc ở trong hệ thống.

Ví dụ, nếu hệ thống duy trì trung bình 120 transaction đang chạy hoặc chờ, throughput là 600 transaction/giây thì thời gian trung bình trong hệ thống xấp xỉ:

\[
W = \frac{L}{\lambda} = \frac{120}{600} = 0,2\text{ giây}
\]

Đây là quan hệ trung bình trong điều kiện ổn định, không phải công thức để suy ra p99. Khi hệ thống chưa ổn định, backlog tăng liên tục hoặc công việc bị drop, cần thận trọng khi áp dụng.

Little's Law giúp kiểm tra tính hợp lý của số liệu. Nếu dashboard báo concurrency trung bình 100, throughput 1.000 TPS và latency trung bình 5 giây, các con số không phù hợp với cùng một ranh giới đo và cùng một tập công việc; cần kiểm tra định nghĩa hoặc dữ liệu telemetry.

## 8. Closed-loop và open-loop load test

Hai mô hình tải phổ biến có thể tạo ra kết quả rất khác nhau.

### 8.1. Closed-loop: số worker cố định

Mỗi worker gửi một yêu cầu, đợi hoàn tất rồi mới gửi yêu cầu tiếp theo. Nếu có 100 worker, số request đồng thời thường bị giới hạn gần mức đó.

Ưu điểm:

- Dễ mô phỏng một số ứng dụng có worker cố định.
- Dễ kiểm soát số người dùng đồng thời.
- Không tạo thêm request mới khi tất cả worker đang bận.

Hạn chế là khi hệ thống chậm, tốc độ gửi tải tự giảm. Điều này có thể che giấu mức quá tải vì client tự điều chỉnh theo latency.

### 8.2. Open-loop: tốc độ đến được định trước

Generator phát request theo tốc độ mục tiêu, chẳng hạn 500 request/giây, bất kể request trước đã hoàn tất hay chưa. Mô hình này phù hợp khi muốn kiểm tra hệ thống trước một tốc độ đến dự kiến.

Ưu điểm:

- Thể hiện rõ offered load (tải được gửi đến).
- Cho thấy backlog, timeout và dropped request khi hệ thống không theo kịp.
- Phù hợp để xác định ngưỡng tải bền vững.

Hạn chế là cần quản lý số request đang chờ và tránh để chính load generator trở thành bottleneck.

### 8.3. Coordinated omission

Một vấn đề của closed-loop load test là coordinated omission. Khi server bị chậm, worker đang chờ không gửi request mới. Những request lẽ ra được gửi trong khoảng thời gian server chậm không xuất hiện trong mẫu latency. Kết quả percentile có thể trông tốt hơn trải nghiệm của hệ thống nhận tải liên tục.

Với open-loop, hãy ghi nhận cả:

- Số request được lên lịch gửi.
- Số request thực sự được gửi.
- Số request hoàn tất.
- Số request bị drop hoặc timeout trước khi vào hệ thống.
- Số request còn in-flight khi test kết thúc.

Không chỉ tính latency của những request đã hoàn tất rồi bỏ qua phần bị drop. Nếu công cụ hỗ trợ coordinated-omission correction hoặc ghi latency từ thời điểm request đáng lẽ được gửi, hãy cấu hình và công bố rõ cách tính.

## 9. Thiết kế workload đại diện

Một benchmark chỉ có ý nghĩa khi workload gần với hành vi thật. Hãy mô tả workload trước khi chạy:

- Tỷ lệ transaction đọc/ghi.
- Số câu SQL trong mỗi transaction.
- Số hàng trung bình và phân phối số hàng bị ảnh hưởng.
- Mức độ trùng lặp khóa (hot keys) và phân phối dữ liệu.
- Tỷ lệ transaction truy cập cùng hàng hoặc cùng phạm vi.
- Isolation level và kiểu commit.
- Kích thước payload, index, foreign key và trigger.
- Tỷ lệ lỗi nghiệp vụ và retry được mong đợi.

Ví dụ workload:

| Loại transaction | Tỷ trọng | Công việc |
|---|---:|---|
| Đọc hồ sơ | 50% | Đọc một khách hàng và một số quan hệ. |
| Cập nhật tồn kho | 20% | Kiểm tra và trừ số lượng theo sản phẩm. |
| Tạo đơn hàng | 20% | Insert order, order lines và cập nhật reservation. |
| Hủy đơn | 10% | Đổi trạng thái, hoàn reservation và ghi audit. |

Nếu mọi worker cập nhật cùng một hàng counter, benchmark chủ yếu đo contention trên hot row. Nếu dữ liệu phân tán đều, kết quả có thể rất khác. Cần mô phỏng đúng phân phối truy cập, kể cả trường hợp dữ liệu nóng nếu hệ thống thực tế có.

## 10. Chuẩn bị môi trường benchmark

Trước khi đo:

1. Dùng database và dữ liệu thử nghiệm có quy mô đủ gần với workload mục tiêu.
2. Ghi lại phiên bản DBMS, schema, index, isolation level và cấu hình quan trọng.
3. Cố định hoặc ghi lại cấu hình máy chủ, storage, network, connection pool và JVM.
4. Tách tải của generator khỏi tải database; kiểm tra CPU, network và memory của máy phát tải.
5. Đảm bảo không có backup, migration hoặc batch không liên quan làm sai lệch phép đo, hoặc ghi nhận rõ nếu chúng là một phần workload thật.
6. Khởi tạo dữ liệu và cache theo kịch bản nhất quán giữa các lần chạy.
7. Xác nhận test thực hiện đúng transaction semantics và kiểm tra invariant sau khi kết thúc.

Không so sánh hai kết quả nếu một lần chạy dùng cache ấm và lần kia dùng cache lạnh mà không ghi rõ. Cũng không so sánh TPS của hai DBMS khi schema, index, durability, replication hoặc mức xác nhận commit khác nhau.

## 11. Quy trình chạy benchmark

Một phép đo có thể chia thành các giai đoạn:

### 11.1. Warm-up

Chạy workload trước khi lấy số liệu chính thức để JVM JIT, connection pool, prepared statement, buffer cache và các cấu trúc nội bộ đạt trạng thái ổn định. Không tính warm-up vào kết quả steady-state nếu mục tiêu là đo hiệu năng sau khi hệ thống đã nóng.

### 11.2. Ramp-up

Tăng dần concurrency hoặc offered load theo các mức. Ví dụ 10, 25, 50, 100, 150 và 200 worker. Ở mỗi mức, chờ hệ thống ổn định rồi mới đo.

### 11.3. Steady-state measurement

Giữ tải đủ lâu để có số mẫu đại diện và để quan sát resource saturation, lock wait, retry, GC và log flush. Một phép đo quá ngắn có thể bỏ lỡ checkpoint, autovacuum, purge hoặc chu kỳ tải.

### 11.4. Cool-down và xác minh

Dừng phát tải, chờ request in-flight kết thúc hoặc ghi nhận chúng bị hủy, rồi kiểm tra dữ liệu cuối cùng. Xác nhận số transaction commit, số lỗi, invariant và backlog còn lại.

Lặp lại từng mức tải nhiều lần. Báo cáo median giữa các lần chạy hoặc phân phối kết quả, không chọn riêng lần tốt nhất.

## 12. Instrumentation trong ứng dụng Java

Đo tại tầng ứng dụng giúp gắn transaction với loại nghiệp vụ và kết quả commit. Dùng đồng hồ đơn điệu như `System.nanoTime()` để đo khoảng thời gian; không dùng `System.currentTimeMillis()` để tính duration vì đồng hồ tường có thể bị điều chỉnh.

Ví dụ khái niệm với Micrometer:

```java
try (Connection connection = dataSource.getConnection()) {
    // Bắt đầu đo sau khi đã lấy connection để không tính pool wait
    // vào transaction duration.
    Timer.Sample sample = Timer.start(registry);
    String outcome = "failure";
    try {
        connection.setAutoCommit(false);
        executeBusinessTransaction(connection);
        connection.commit();
        outcome = "success";
    } catch (SQLException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    } finally {
        sample.stop(Timer.builder("db.transaction.duration")
            .tag("operation", "create_order")
            .tag("outcome", outcome)
            .register(registry));
    }
}
```

Đây là ví dụ rút gọn. Code production cần phân loại lỗi, xử lý connection không an toàn sau rollback failure hoặc commit outcome unknown, và đo riêng thời gian lấy connection nếu cần. Với retry, mỗi attempt có thể có timer riêng; logical request có timer bao trùm cả retry và backoff.

### 12.1. Metric nên xuất

Một bộ metric có thể gồm:

| Metric | Loại | Dùng để làm gì |
|---|---|---|
| `db.logical_transactions_total` | Counter | Số yêu cầu nghiệp vụ đã kết thúc theo outcome. |
| `db.transaction.attempts_total` | Counter | Số lần thử transaction database. |
| `db.transaction.duration` | Histogram/Timer | Phân phối thời gian attempt đến commit/rollback. |
| `db.logical_request.duration` | Histogram/Timer | Độ trễ end-to-end của yêu cầu có thể retry. |
| `db.transaction.retries_total` | Counter | Số lần retry theo loại lỗi. |
| `db.pool.acquire.duration` | Histogram/Timer | Thời gian chờ connection pool. |
| `db.transaction.in_flight` | Gauge | Số attempt đang hoạt động. |
| `db.transaction.commit.duration` | Histogram/Timer | Thời gian commit được xác nhận. |

Tên metric cần tuân theo quy ước telemetry của dự án. Tránh label có cardinality cao như `order_id`, `customer_id`, SQL đầy đủ hoặc request UUID; chúng có thể làm hệ thống metrics tăng kích thước rất nhanh. Dùng label có tập giá trị nhỏ như `operation`, `outcome`, `db_system` và `error_category`.

## 13. Đo ở database và tầng hạ tầng

Metric ứng dụng cho biết trải nghiệm và kết quả transaction. Metric database giúp giải thích nguyên nhân:

- CPU utilization và runnable queue.
- Storage latency, IOPS, throughput và fsync/log flush.
- Buffer/cache hit ratio và physical reads.
- Lock wait time, deadlock count và số transaction chờ.
- Active/idle connections và pool saturation.
- Transaction age, long-running query và open transaction.
- WAL/redo/undo generation và checkpoint/purge/vacuum.
- Replication lag nếu transaction phải chờ replica hoặc commit theo cấu hình đồng bộ.
- Temp space, sort/hash spill và memory pressure.

Không có một metric database đơn lẻ giải thích toàn bộ hiệu năng. Ví dụ, CPU thấp nhưng latency cao có thể do lock wait hoặc storage. CPU cao có thể do query plan kém, contention trên latch nội bộ hoặc tải generator. Hãy đặt metric ứng dụng cạnh metric DBMS và hệ điều hành trên cùng timeline.

## 14. Phân biệt lỗi cạnh tranh với lỗi nghiệp vụ

Tỷ lệ thành công chỉ có ý nghĩa nếu lỗi được phân loại. Một số nhóm:

| Nhóm | Ví dụ | Ý nghĩa vận hành |
|---|---|---|
| Deadlock | Transaction bị chọn làm nạn nhân. | Có thể retry toàn transaction; điều tra thứ tự khóa. |
| Serialization conflict | SSI hoặc snapshot update conflict. | Retry toàn transaction với snapshot mới nếu an toàn. |
| Lock timeout/NOWAIT | Không lấy được khóa trong giới hạn. | Có thể trả busy hoặc retry có backoff. |
| Constraint violation | Unique, FK, check constraint. | Thường là dữ liệu hoặc xung đột nghiệp vụ; không retry mù. |
| Validation/business rejection | Không đủ số dư, hết hàng, trạng thái không hợp lệ. | Kết quả nghiệp vụ dự kiến, không nhất thiết là lỗi hạ tầng. |
| Connection/network error | Mất kết nối trước hoặc trong commit. | Kết quả có thể chưa xác định; cần đối soát idempotency key. |
| Cancellation/timeout ở client | Caller hết thời gian chờ. | Phải xác định câu lệnh và transaction đã thực sự kết thúc chưa. |

Có thể báo cáo hai tỷ lệ: tỷ lệ kỹ thuật thành công (database commit được xác nhận) và tỷ lệ nghiệp vụ thành công (yêu cầu đạt mục tiêu nghiệp vụ). Một yêu cầu bị từ chối vì hết hàng có thể là transaction database thành công nhưng nghiệp vụ không thực hiện được; không nên gộp nó với deadlock.

## 15. Xác định sustainable capacity

Peak throughput là throughput cao nhất quan sát được trong một khoảng ngắn. Sustainable capacity là mức tải hệ thống có thể duy trì trong thời gian đại diện mà vẫn đáp ứng các SLO về latency, success rate và tài nguyên.

Ví dụ một SLO benchmark:

- Logical request success rate ít nhất 99,9% (không tính các từ chối nghiệp vụ được định nghĩa riêng).
- p95 transaction latency dưới 100 ms.
- p99 transaction latency dưới 300 ms.
- Deadlock/serialization retry rate dưới ngưỡng đã thống nhất.
- Queue backlog không tăng liên tục.
- CPU, storage và connection pool còn headroom vận hành.

Các con số trên chỉ là ví dụ. Ngưỡng thực tế phải xuất phát từ SLA/SLO của sản phẩm và workload. Mức tải cao nhất còn đáp ứng mọi tiêu chí trong thời gian đủ dài là ứng viên sustainable capacity; không lấy điểm TPS cao nhất nếu tại đó p99 hoặc error rate đã vượt ngưỡng.

## 16. Đọc kết quả benchmark

Một báo cáo tốt nên có bảng theo từng mức concurrency hoặc offered load:

| Concurrency | Offered req/s | Successful TPS | p50 | p95 | p99 | Success rate | Retry rate |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 100 | 98 | 8 ms | 18 ms | 30 ms | 99,9% | 0,1% |
| 25 | 250 | 242 | 10 ms | 25 ms | 45 ms | 99,8% | 0,2% |
| 50 | 500 | 470 | 15 ms | 55 ms | 120 ms | 99,4% | 0,8% |
| 100 | 1.000 | 620 | 35 ms | 180 ms | 900 ms | 96,0% | 4,5% |

Số liệu trên chỉ minh họa cách trình bày. Ở mức 100 concurrency, offered load tăng nhưng successful TPS chỉ tăng nhẹ, p99 và retry rate tăng mạnh. Đây là dấu hiệu hệ thống đã gần hoặc vượt điểm bão hòa; tăng worker thêm có thể chỉ làm hàng đợi và latency lớn hơn.

Hãy ghi rõ đơn vị và định nghĩa cột. `Successful TPS` phải là số logical transaction hoặc attempt commit thành công theo định nghĩa đã chọn. Không trộn hai loại trong cùng biểu đồ.

## 17. Công cụ đo và benchmark

Có thể dùng nhiều công cụ, tùy mục tiêu:

- **pgbench:** benchmark workload PostgreSQL, chạy script transaction với nhiều client và báo TPS/latency.
- **sysbench:** tạo workload database, đặc biệt phổ biến với MySQL và một số backend khác.
- **JMeter hoặc Gatling:** mô phỏng luồng request/API và workload hỗn hợp từ góc nhìn ứng dụng.
- **k6:** phát tải theo arrival rate hoặc virtual users, hữu ích cho open-loop/closed-loop API testing.
- **Custom JDBC harness:** phù hợp khi cần kiểm soát chính xác transaction, barrier, dữ liệu và lỗi cạnh tranh.
- **Micrometer/Prometheus/Grafana hoặc hệ telemetry tương đương:** thu thập metrics liên tục trong ứng dụng và hạ tầng.

Không dùng microbenchmark như JMH để thay thế benchmark end-to-end database. JMH phù hợp đo đoạn code JVM nhỏ; transaction thực tế còn phụ thuộc network, driver, pool, database, storage và concurrency.

## 18. Các sai lầm thường gặp khi đo

1. **Đếm request gửi đi thay cho transaction commit:** làm throughput bị phóng đại.
2. **Chỉ báo cáo trung bình latency:** che khuất p95/p99 và đuôi chậm.
3. **Không phân biệt logical request và retry attempt:** làm success/retry rate sai.
4. **Chỉ dùng closed-loop:** có thể bỏ qua tải đáng lẽ đến trong lúc hệ thống chậm.
5. **Không đo dropped request:** kết quả trông tốt vì những request khó đã biến mất khỏi mẫu.
6. **Load generator bị bão hòa:** TPS thấp do máy phát tải không gửi đủ request, không phải database.
7. **Dữ liệu quá nhỏ hoặc quá đều:** không đại diện cache, index và hot-key contention thật.
8. **Chỉ chạy vài giây:** bỏ qua warm-up, checkpoint, purge và biến động tải.
9. **Không kiểm tra tính đúng đắn sau benchmark:** throughput cao nhưng transaction có thể bị mất hoặc trùng.
10. **So sánh cấu hình không tương đương:** durability, isolation level, replication hoặc schema khác nhau.
11. **Không ghi cấu hình và phiên bản:** kết quả không thể tái hiện.
12. **Lấy lần chạy tốt nhất:** che giấu độ biến động giữa các lần đo.

## 19. Quy trình đo từ đầu đến cuối

1. Xác định đơn vị logical transaction và định nghĩa success/failure.
2. Chọn workload mix, dữ liệu và phân phối truy cập gần thực tế.
3. Đặt ranh giới đo end-to-end, pool, transaction, statement và commit.
4. Instrument counter, histogram, retry và in-flight work ở tầng ứng dụng.
5. Thu thập CPU, I/O, lock wait, deadlock, connection pool và transaction age ở tầng database/hạ tầng.
6. Chọn mô hình closed-loop, open-loop hoặc cả hai; ghi offered load và dropped request.
7. Warm-up, ramp-up, đo steady-state và cool-down theo kịch bản cố định.
8. Tăng concurrency theo nhiều mức để tìm điểm throughput bão hòa và latency tăng mạnh.
9. Lặp lại các lần chạy và báo cáo phân phối, không chỉ kết quả tốt nhất.
10. Kiểm tra dữ liệu cuối, invariant, số commit, lỗi, retry và backlog.
11. Xác định sustainable capacity theo SLO, không chỉ peak TPS.
12. Lưu phiên bản DBMS, schema, index, cấu hình, seed dữ liệu và cấu hình load generator cùng báo cáo.

## 20. Checklist cho báo cáo hiệu năng đồng thời

- [ ] Đã định nghĩa logical transaction và attempt.
- [ ] Throughput được tính từ transaction hoàn tất/commit theo định nghĩa rõ ràng.
- [ ] Đã đo end-to-end latency và transaction latency.
- [ ] Đã báo cáo p50, p95, p99 và số lượng mẫu.
- [ ] Đã tính success rate, final failure rate và retry rate riêng.
- [ ] Đã phân loại lỗi deadlock, serialization, timeout, constraint và nghiệp vụ.
- [ ] Đã ghi offered load, completed throughput, in-flight và dropped request.
- [ ] Đã xem xét coordinated omission trong load model.
- [ ] Đã kiểm tra load generator không phải bottleneck.
- [ ] Workload mix, dữ liệu và hot-key distribution đại diện.
- [ ] Đã warm-up, ramp-up, đo steady-state và lặp lại nhiều lần.
- [ ] Đã thu thập metric DBMS, connection pool, CPU, storage và lock wait.
- [ ] Đã kiểm tra invariant và dữ liệu sau benchmark.
- [ ] Đã xác định sustainable capacity theo SLO.
- [ ] Báo cáo ghi rõ phiên bản, cấu hình và ranh giới đo để tái hiện.

Đo thông lượng, độ trễ và tỷ lệ giao dịch thành công cần nhìn đồng thời vào công việc được gửi, công việc đã commit và chất lượng kết quả. Throughput cho biết năng lực hoàn tất; percentile latency cho biết người dùng phải chờ bao lâu; success và retry rate cho biết hệ thống có giữ được độ tin cậy dưới tải hay không. Khi đo đúng ranh giới, dùng workload đại diện và đối chiếu metric ứng dụng với database, bạn có thể tìm được mức concurrency bền vững thay vì chỉ tối đa hóa một con số TPS.
