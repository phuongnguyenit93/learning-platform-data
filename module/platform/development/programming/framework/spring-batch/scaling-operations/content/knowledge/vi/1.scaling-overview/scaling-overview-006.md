# Giới hạn của tốc độ đọc và ghi trong Spring Batch

## Mục tiêu bài học

Một job Spring Batch có thể chạy trên 16 thread hoặc nhiều worker JVM mà vẫn không nhanh hơn, bởi tất cả cùng chờ một câu truy vấn nguồn, một database đích hoặc dịch vụ bên ngoài. Để mở rộng workload dữ liệu lớn, cần phân biệt **khả năng đọc (read throughput)**, **khả năng xử lý (processing throughput)** và **khả năng ghi (write throughput)**, sau đó xác định phần nào đang giới hạn tốc độ hoàn thành của toàn job.

Bài thuộc chương **Tổng quan scaling** trong module **SPRING_BATCH_SCALING_OPERATIONS**. Nội dung gắn việc đo nút thắt đọc/ghi với lựa chọn multi-threaded step, parallel steps, partitioning, các mô hình phân tán, thread safety, retry/restart và vận hành theo tài nguyên thật.

Sau bài học, bạn có thể:

- Đo và phân biệt item đọc/giây, item ghi/giây, byte/giây, latency và thời gian hoàn thành job.
- Giải thích vì sao tăng số thread/worker không vượt được giới hạn của hệ thống nguồn hoặc đích.
- Ước lượng giới hạn throughput của pipeline, kể cả trường hợp processor lọc hoặc tạo ra nhiều item đầu ra.
- Nhận diện các nút thắt về query plan, index, cursor, pagination, JDBC, batch write, lock, transaction log và connection pool.
- Chọn hướng cải thiện đọc/ghi trước khi tăng concurrency hoặc phân tán sang nhiều JVM.
- Xây dựng benchmark có kiểm soát, kiểm tra lỗi/restart và tránh đánh đổi tốc độ lấy tính đúng dữ liệu.

## 1. Tốc độ đọc và ghi là những đại lượng khác nhau

Một step theo mô hình chunk thường có đường xử lý:

~~~mermaid
flowchart LR
    A[(Nguồn)] --> R["ItemReader<br/>đọc dữ liệu"]
    R --> P["ItemProcessor<br/>lọc / biến đổi"]
    P --> W["ItemWriter<br/>ghi theo chunk"]
    W --> B[(Đích)]
~~~

Có thể định nghĩa:

- **Read throughput:** số item được reader ghi nhận đã đọc trong một giây.
- **Process throughput:** số item được xử lý trong một giây; khi retry, cần xác định đang đếm số lượt xử lý hay số item duy nhất.
- **Write throughput:** số item đầu ra được writer ghi nhận thành công trong một giây.
- **Byte throughput:** dung lượng dữ liệu được chuyển qua mạng/đĩa trong một giây; hữu ích khi item có kích thước rất khác nhau.
- **Latency:** thời gian hoàn tất một thao tác đọc, ghi, chunk hoặc giao dịch; là yếu tố quyết định mức concurrency cần thiết.
- **Job elapsed time:** tổng thời gian từ khi job/step bắt đầu đến lúc kết thúc, bao gồm mở kết nối, khởi tạo, chờ, retry và phối hợp các step.

Spring Batch có thể ghi các chỉ số **readCount**, **writeCount**, **filterCount**, **skipCount**, **commitCount** và **rollbackCount** vào StepExecution. Chúng giúp quan sát kết quả nhưng không tự nói chính xác phần nào chậm: để biết nguyên nhân cần thêm metric từ JDBC, database, CPU, bộ nhớ, mạng và hệ thống bên ngoài.

### Vì sao readCount khác writeCount?

Processor có thể trả về **null** để lọc item, bỏ qua item lỗi theo cấu hình skip hoặc một writer có thể gửi dữ liệu theo cơ chế gộp. Vì vậy, không được mặc định rằng:

\[
\mathrm{readCount} = \mathrm{writeCount}
\]

Ví dụ, đọc 1 triệu giao dịch nhưng chỉ 70% hợp lệ để tổng hợp; theo mô hình một item đầu vào tạo tối đa một item đầu ra, số item ghi hợp lệ chỉ khoảng **700.000**. Nếu write throughput bằng 7.000 item/s, cần hiểu đó là 7.000 **item đầu ra** mỗi giây, không phải 7.000 item đầu vào/giây.

## 2. Giới hạn throughput của cả pipeline

Mỗi công đoạn có một **năng lực phục vụ tối đa** khi được đo trong điều kiện cụ thể. Một pipeline ổn định không thể hoàn thành nhanh hơn công đoạn giới hạn của nó.

Với pipeline một-đổi-một (mỗi item đọc tạo một item ghi), giới hạn lý tưởng:

\[
R_{\mathrm{job}}
\leq \min(R_{\mathrm{read}},R_{\mathrm{process}},R_{\mathrm{write}})
\]

Trong đó mọi đại lượng có cùng đơn vị **item đầu vào tương đương/giây**. Đây là **cận trên** chứ không phải giá trị job chắc chắn đạt: read, process và write có thể tuần tự một phần, dùng chung connection hoặc cạnh tranh tài nguyên.

### Khi processor lọc hoặc nhân bản item

Gọi:

- \(R_r\): năng lực đọc nguồn tính bằng item đầu vào/giây.
- \(R_p\): năng lực xử lý tính bằng item đầu vào/giây.
- \(R_w\): năng lực ghi tính bằng item đầu ra/giây.
- \(a\): số item đầu ra trung bình trên một item đầu vào, tính theo dữ liệu nghiệp vụ đại diện.

Khi tỷ lệ chuyển đổi tương đối ổn định và không có bottleneck khác:

\[
R_{\mathrm{input,effective}}
\leq \min\left(R_r,R_p,\frac{R_w}{a}\right)
\]

Nếu processor lọc 25% đầu vào thì \(a=0{,}75\). Nếu mỗi item đầu vào tạo ba kết quả thì \(a=3\). Trường hợp \(a=0\) cần phân tích riêng vì job có thể không ghi gì; không được chia cho 0.

**Ví dụ giả định:** Reader tối đa 12.000 item đầu vào/s; processor xử lý được 18.000 item đầu vào/s; writer tối đa 7.000 item đầu ra/s; 75% item được giữ lại. Khi đó:

\[
R_{\mathrm{input,effective}}
\leq \min\left(12.000,18.000,\frac{7.000}{0{,}75}\right)
\approx 9.333\ \mathrm{item\ đầu\ vào/s}
\]

Dù reader đọc được 12.000 item/s, tốc độ đầu vào hữu ích bị giới hạn ở khoảng **9.333 item/s** vì writer là nút thắt. Nếu tăng reader lên 20.000 item/s mà writer không đổi, toàn pipeline **không** tự nhanh hơn.

### Từ throughput đến thời gian hoàn thành

Với \(N\) item đầu vào và throughput bền vững \(R\), cận dưới đơn giản:

\[
T_{\mathrm{processing}}\geq\frac{N}{R}
\]

Ví dụ 9 triệu item và giới hạn 9.333 item/s cần ít nhất khoảng **964 giây (16 phút)** cho phần xử lý theo phép ước lượng này. Thời gian thực tế còn có khởi tạo, chờ, tổng hợp, biến động tải, rollback và restart.

**Lưu ý:** Chunk-oriented step thông thường không phải pipeline ba công đoạn hoàn toàn tách rời với bộ đệm vô hạn. Trong một chunk, read/process/write phối hợp theo cách framework tổ chức transaction; tốc độ đo từng công đoạn tách biệt chỉ là thông tin năng lực và không được cộng/trừ như ba máy độc lập mà không xét cách chúng chạy thực tế.

## 3. Vì sao tăng worker không giải quyết được một nút thắt chung?

Giả sử một database đích ghi bền vững tối đa **10.000 record/s** với schema, transaction và tải hiện tại. Một worker xử lý 4.000 record/s; ba worker lý tưởng có thể tạo 12.000 record/s nhưng database vẫn không thể nhận bền vững quá mức tối đa giả định.

~~~mermaid
flowchart TB
    W1["Worker 1<br/>4k/s"] --> D["DB đích<br/>trần 10k/s"]
    W2["Worker 2<br/>4k/s"] --> D
    W3["Worker 3<br/>4k/s"] --> D
    W4["Worker 4<br/>4k/s"] --> D
    D --> O["Throughput hoàn thành<br/>không vượt trần DB"]
~~~

Khi tăng worker, các hiện tượng có thể xuất hiện:

- Connection pool chạm giới hạn và thời gian chờ connection tăng.
- Truy vấn đọc cùng bảng quét quá nhiều hàng, cạnh tranh CPU và I/O của DB.
- Các transaction ghi giữ khóa lâu hơn, gây lock wait và deadlock.
- Transaction log hoặc thiết bị lưu trữ bão hòa.
- Retry do timeout tăng; tổng công việc phải làm có thể lớn hơn trước.
- Broker hoặc API ngoài có queue lớn dần, tăng latency dù số worker tăng.

Cần phân biệt **năng lực của một worker** với **năng lực tổng của tài nguyên chia sẻ**. Nâng số replica chỉ mở rộng phần việc thực sự độc lập và có tài nguyên đáp ứng.

### Công thức cận trên theo ngân sách

Nếu có \(p\) worker và một worker xử lý tối đa \(r\) item/s khi chạy đơn lẻ, trong khi nguồn và đích có trần \(R_r\) và \(R_w\) ở cùng đơn vị, có thể ước lượng:

\[
R_{\mathrm{job}}\leq\min(p\,r,R_r,R_w)
\]

Đây là cận trên thô, giả định xử lý một-đổi-một. Trong thực tế \(r\) có thể **giảm khi \(p\) tăng** vì các worker cùng cạnh tranh CPU, DB và network.

## 4. Các nút thắt thường gặp ở ItemReader

### 4.1. Query plan và index

Một reader chậm có thể thực hiện query phải quét hàng triệu dòng dù mỗi lần chỉ lấy vài nghìn record. Ví dụ:

~~~sql
SELECT id, customer_id, amount_cents
FROM orders
WHERE business_date = :businessDate
  AND id > :lastSeenId
ORDER BY id
LIMIT :pageSize;
~~~

Truy vấn minh họa cho keyset pagination; điều kiện, cú pháp LIMIT và index phù hợp phụ thuộc hệ quản trị. Cần kiểm tra **EXPLAIN/EXPLAIN ANALYZE**, số hàng scan, độ chọn lọc, sort, truy cập index và thời gian chờ I/O. Với truy vấn trên, index liên quan đến business_date và id có thể cần được đánh giá, nhưng không có chỉ mục đúng cho mọi phân bố dữ liệu.

**Tăng số luồng đọc không chữa được query plan kém.** Nếu mỗi worker thực hiện full table scan, thêm worker nhân tải lên hệ thống nguồn.

### 4.2. Cursor và paging có chi phí khác nhau

**JdbcCursorItemReader** đọc theo ResultSet/cursor, thường giữ tài nguyên đọc trong thời gian step hoạt động. Nó phù hợp với dữ liệu lớn nếu driver và DB hỗ trợ streaming hiệu quả và cấu hình được kiểm chứng, nhưng cần chú ý connection, timeout, khả năng restart và cursor state.

**JdbcPagingItemReader** lấy dữ liệu theo trang; mỗi trang có query, thường cần sort key rõ ràng và duy nhất để hạn chế trùng/mất dữ liệu. Mức độ hiệu quả phụ thuộc chiến lược paging, index và độ ổn định của tập dữ liệu. Với một số cách phân trang sử dụng OFFSET lớn, database có thể tốn công bỏ qua nhiều hàng; keyset/range có thể hiệu quả hơn tùy reader và DB.

**FlatFileItemReader** bị giới hạn bởi tốc độ đọc file, decoding, parsing và việc chia nhỏ file. Một file dùng con trỏ chung không tự an toàn khi nhiều thread cùng đọc; có thể phải tạo nhiều file/range độc lập hoặc thay kiến trúc đọc.

**Reader gọi API** còn chịu latency, quota, phân trang phía dịch vụ và chính sách retry. Nếu nguồn áp dụng rate limit 500 request/s, thêm 20 worker có thể chỉ dẫn đến lỗi HTTP 429 và backoff.

### 4.3. JDBC fetch size và page size

**Fetch size** thường là gợi ý cho JDBC driver về số hàng lấy trong một lượt trao đổi. **Page size** của paging reader là quy mô một trang query. Hai thông số không đồng nghĩa với **commit interval** của chunk.

| Thông số | Ý nghĩa chính | Rủi ro nếu chọn không phù hợp |
| --- | --- | --- |
| JDBC fetch size | Hành vi lấy hàng qua driver | Quá nhỏ tăng round trip; quá lớn tăng buffer/memory |
| Paging page size | Số hàng yêu cầu trong một trang | Quá nhỏ tăng số query; quá lớn tăng latency và memory |
| Commit interval | Lượng input mục tiêu/chunk và ranh giới transaction | Quá nhỏ tăng commit; quá lớn kéo dài transaction và rollback |
| Reader concurrency | Số reader hoạt động cùng lúc | Tranh chấp DB, pool, API quota; sai checkpoint nếu chia sẻ state |

Không mặc định fetch size luôn được driver tôn trọng hoặc mọi DB driver đều streaming với cùng cấu hình. Cần kiểm chứng hành vi thật bằng metric và profiler.

### 4.4. Phần xử lý nằm ngay trong reader

Đôi khi Bottleneck “đọc chậm” thực ra là **RowMapper**, JSON/XML parsing, chuyển timezone, decompress hoặc ánh xạ entity tốn CPU. Nếu query DB trả về nhanh nhưng ứng dụng tiêu tốn CPU khi tạo object, thêm index sẽ không giúp nhiều.

Hãy đo riêng **thời gian DB thực thi query**, **thời gian truyền dữ liệu** và **thời gian ánh xạ/parsing**. Với dữ liệu hàng chục triệu item, nhiều allocation nhỏ có thể gây GC đáng kể.

## 5. Các nút thắt thường gặp ở ItemWriter

### 5.1. Ghi từng dòng và ghi theo batch

Writer ghi một SQL statement mỗi item thường tạo nhiều round trip hơn writer hỗ trợ JDBC batch. Chẳng hạn việc ghi 1 triệu record bằng 1 triệu request riêng có thể tốn nhiều thời gian chờ mạng và transaction hơn khi gửi các nhóm câu lệnh phù hợp.

Spring Batch hỗ trợ các writer như **JdbcBatchItemWriter** để gom batch update. Tuy nhiên **gọi writer một lần cho 500 item** chưa bảo đảm DB sẽ xử lý thành một thao tác vật lý duy nhất: driver, loại SQL, cấu hình batch, index và DB vẫn ảnh hưởng.

Ví dụ logic:

~~~java
@Bean
public JdbcBatchItemWriter<OrderSummary> orderSummaryWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<OrderSummary>()
            .dataSource(dataSource)
            .sql("""
                 INSERT INTO order_summary
                     (order_id, total_cents)
                 VALUES (?, ?)
                 ON CONFLICT (order_id)
                 DO UPDATE SET total_cents = EXCLUDED.total_cents
                 """)
            .itemPreparedStatementSetter((item, ps) -> {
                ps.setLong(1, item.orderId());
                ps.setLong(2, item.totalCents());
            })
            .build();
}
~~~

Đây là ví dụ **PostgreSQL** theo API Spring Batch 5.x và Java 17; cần có lớp/record OrderSummary cùng các import tương ứng và ràng buộc **UNIQUE/PRIMARY KEY** trên order_id. Việc upsert chỉ an toàn nếu nghiệp vụ cho phép ghi lại giá trị theo cùng khóa. Nếu writer cộng dồn tiền hoặc phát sinh side effect, phải thiết kế idempotency riêng.

### 5.2. Commit interval có điểm bão hòa

Chunk quá nhỏ thường trả chi phí transaction nhiều lần. Chunk quá lớn có thể:

- Giữ kết nối/giao dịch và khóa lâu hơn.
- Dùng nhiều heap hơn khi lưu item đầu ra.
- Tăng thời gian rollback/retry khi lỗi xảy ra gần cuối chunk.
- Làm transaction log/undo chịu áp lực lớn hơn.
- Chạm timeout khi DB đang chịu tải.

Ví dụ thử chunk size **50, 100, 250, 500, 1.000** và quan sát throughput **cùng** transaction duration, rollback và peak heap. Không có một commit interval tối ưu cho mọi workload.

### 5.3. Index, constraint và xung đột ghi

Ghi vào bảng có nhiều index, foreign key hoặc trigger sẽ có chi phí duy trì cấu trúc dữ liệu. Một số job chậm vì các worker cùng cập nhật một business key, ngay cả khi chúng đọc các partition khác nhau.

Ví dụ, tám worker đều cập nhật một dòng **daily_total** thì các transaction có thể phải chờ cùng một row lock. Một kiến trúc thay thế là worker ghi kết quả theo partition vào vùng riêng, sau đó step tổng hợp tuần tự hoặc gộp có kiểm soát.

Giảm index hoặc thay đổi constraint không phải hành động tuning tự động: chúng có thể phục vụ tính đúng và truy vấn nghiệp vụ khác. Cần xem toàn bộ chi phí, kế hoạch triển khai và rủi ro dữ liệu trước khi thay đổi schema.

### 5.4. Writer gọi dịch vụ ngoài

Nếu writer gọi API HTTP, tốc độ thường bị giới hạn bởi latency, số kết nối, quota và giới hạn của đối tác. Transaction manager của DB **không tự rollback** một API call đã thành công.

Khi tăng worker, cần dùng giới hạn concurrency, rate limiter, retry/backoff hợp lý, idempotency key nếu API hỗ trợ và có thể cân nhắc ghi yêu cầu vào transactional outbox để xử lý bất đồng bộ khi phù hợp với nghiệp vụ.

## 6. Khi đọc nhanh hơn ghi: tồn đọng và backpressure

Giả sử nguồn cung cấp **15.000 item/s**, trong khi hệ thống đích chỉ nhận bền vững **9.000 item/s**, và mỗi item đầu vào tương ứng một item đầu ra.

Nếu có **hàng đợi trung gian không giới hạn**, tồn đọng tăng lý tưởng khoảng:

\[
15.000-9.000=6.000\ \mathrm{item/s}
\]

Sau 10 phút, số item đợi có thể đạt **3,6 triệu** nếu các tốc độ được duy trì và không có điều tiết. Với mỗi item trung bình 1 KiB trước overhead, riêng dữ liệu thô đã cỡ **3,43 GiB**. Thực tế kích thước memory/disk còn cao hơn do metadata, serialization và replication.

Trong **chunk-oriented step đồng bộ**, người đọc thường không tiếp tục bơm dữ liệu vô hạn khi writer chưa xong; chu trình chunk tự tạo một mức điều tiết. Nhưng trong **remote chunking**, producer/broker/worker có thể có số lượng message đang chờ lớn, và cần backpressure rõ ràng.

Các cách kiểm soát:

- Giới hạn số chunk/message đang chờ (inflight).
- Dùng queue có capacity và chính sách chờ/điều tiết.
- Giới hạn số worker và connection tới DB đích.
- Theo dõi queue depth, message age, retry rate và thời gian xử lý.
- Định nghĩa quy tắc xử lý khi worker chậm hoặc đích tạm thời không sẵn sàng.

**Queue dài hơn không phải throughput cao hơn.** Nó có thể chỉ cho thấy producer nhanh hơn consumer, đồng nghĩa thời gian hoàn tất ngày càng trễ.

## 7. Khi ghi nhanh hơn đọc: writer và worker chờ input

Ở chiều ngược lại, nếu reader chỉ cung cấp 3.000 item/s mà writer có thể xử lý 20.000 item/s, writer sẽ dành nhiều thời gian chờ dữ liệu. Các cách cải thiện cần xem xét:

1. **Tối ưu query và index** của nguồn, xác nhận số hàng scan và thứ tự đọc.
2. **Tăng hiệu quả fetch/paging** nếu driver/query đang mất nhiều round trip.
3. **Giảm parsing/mapping nặng** ở reader nếu CPU ứng dụng là bottleneck.
4. **Chia nguồn thành partition độc lập** nếu DB chịu được nhiều reader đồng thời.
5. **Đổi phương thức trích xuất dữ liệu** khi nguồn hỗ trợ bulk export, snapshot hoặc file theo partition tốt hơn gọi API từng item.

Trong remote chunking, manager đọc toàn bộ item trước khi gửi tới worker. Nếu reader ở manager là nút thắt, thêm worker process/write thường ít giá trị. Trong remote partitioning, các worker tự đọc phạm vi của mình, nhưng có thể chuyển bottleneck từ manager sang tổng tải của DB nguồn.

## 8. Concurrency, latency và Little's law

Một hệ thống I/O-bound có thể dùng concurrency để bù thời gian chờ, nhưng concurrency không đồng nghĩa throughput tăng vô hạn.

**Little's law** cho hệ thống ổn định:

\[
L=\lambda W
\]

Trong đó:

- \(L\) là số công việc trung bình đang nằm trong hệ thống;
- \(\lambda\) là tốc độ hoàn tất trung bình (công việc/giây);
- \(W\) là thời gian trung bình một công việc lưu lại trong hệ thống (giây).

Ví dụ một API ghi trung bình mất **0,2 giây/request**. Để duy trì **100 request/s** nếu mỗi request xử lý một công việc, số request đang hoạt động trung bình cần khoảng **20** trong một mô hình ổn định.

Phép tính không bảo đảm API hỗ trợ 100 request/s: còn có rate limit, quota DB, retry, response variability và tải của server. Nếu server đã bão hòa, tăng concurrency làm **W** tăng và \(\lambda\) có thể đứng yên hoặc giảm.

### Connection pool đặt trần concurrency thực tế

Giả sử bốn worker JVM, mỗi worker có connection pool tối đa 12. Tổng **cấu hình pool tối đa** của bốn worker là 48 connection, chưa kể manager và các ứng dụng khác. Không đồng nghĩa lúc nào có 48 kết nối đang mở; đây là ngân sách có thể tiêu thụ.

Khi step sử dụng nhiều transaction đồng thời, nên so các số đo:

- Active connections và idle connections.
- Thời gian chờ lấy connection.
- Thời gian query/commit.
- Số transaction, lock wait và throughput toàn DB.

Một pool quá nhỏ gây hàng chờ; pool quá lớn có thể làm DB tốn CPU/memory và tăng contention. Lựa chọn cần căn cứ trên **tổng hệ thống**, không chỉ một JVM.

## 9. Multi-threaded step: tăng tải đọc/ghi trong cùng JVM

**Multi-threaded step** dùng TaskExecutor để xử lý các chunk đồng thời. Nó phù hợp khi workload có phần việc độc lập, component được kiểm chứng thread-safe và nguồn/đích còn dư năng lực.

~~~java
@Bean
public Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager tx,
        ItemReader<InputOrder> reader,
        ItemProcessor<InputOrder, OrderSummary> processor,
        ItemWriter<OrderSummary> writer,
        @Qualifier("batchExecutor") TaskExecutor executor) {

    return new StepBuilder("importStep", jobRepository)
            .<InputOrder, OrderSummary>chunk(250, tx)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(executor)
            .build();
}
~~~

Đoạn mã minh họa kiểu Spring Batch 5.x; cần bổ sung import, DTO, bean và cấu hình executor phù hợp trong ứng dụng thực tế.

**Rủi ro quan trọng:** nhiều ItemReader có trạng thái mutable như cursor hoặc vị trí file không mặc định thread-safe. Việc đặt TaskExecutor không bảo đảm reader đọc đúng một lần, không bảo đảm thứ tự commit và không tự làm restart an toàn. Phải kiểm tra reader, processor, writer, connection pool, giao dịch và checkpoint trước khi tăng thread.

Một phép đo hữu ích là tăng 1 → 2 → 4 → 8 thread, theo dõi đồng thời **read throughput**, **write throughput**, **query latency**, **rollback** và **data reconciliation**. Nếu read throughput tăng nhưng write throughput không đổi, writer hoặc đích có thể là nút thắt.

## 10. Partitioning: nhiều reader độc lập, nhưng cùng chia tài nguyên nguồn

Partitioning giúp mỗi worker sở hữu phạm vi dữ liệu riêng, tránh chia sẻ một con trỏ đọc mutable:

~~~mermaid
flowchart TB
    M[Manager + Partitioner] --> P1["Partition A<br/>ID [1, 100001)"]
    M --> P2["Partition B<br/>ID [100001, 200001)"]
    M --> P3["Partition C<br/>ID [200001, 300001)"]
    P1 --> W1[Worker Step 1]
    P2 --> W2[Worker Step 2]
    P3 --> W3[Worker Step 3]
    W1 --> DB[(Nguồn / đích dùng chung)]
    W2 --> DB
    W3 --> DB
~~~

Với **local partitioning**, worker chạy trên thread trong một JVM. Với **remote partitioning**, chúng có thể chạy ở các JVM/máy khác nhau. Cả hai đều cần Partitioner/ExecutionContext, tên partition ổn định và truy vấn phù hợp với phạm vi.

### Ví dụ worker reader nhận phạm vi ID

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<InputOrder> orderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minIdInclusive']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    if (minId == null || maxId == null || minId >= maxId) {
        throw new IllegalArgumentException("Invalid partition bounds");
    }

    return new JdbcCursorItemReaderBuilder<InputOrder>()
            .name("orderReader")
            .dataSource(dataSource)
            .sql("""
                 SELECT id, amount_cents
                 FROM orders
                 WHERE id >= ? AND id < ?
                 ORDER BY id
                 """)
            .preparedStatementSetter(ps -> {
                ps.setLong(1, minId);
                ps.setLong(2, maxId);
            })
            .rowMapper((rs, rowNum) ->
                    new InputOrder(
                            rs.getLong("id"),
                            rs.getLong("amount_cents")))
            .saveState(true)
            .build();
}
~~~

Ví dụ Spring Batch 5.x này giả định InputOrder là record với hai trường **id** và **amountCents**, các import và bean hạ tầng đã được khai báo. **@StepScope** gắn một reader với ngữ cảnh của StepExecution hiện tại; framework không tự tạo các khoảng ID nếu không có Partitioner.

Các phạm vi dùng quy tắc **bao gồm cận dưới, loại trừ cận trên**. Phải chốt phạm vi dữ liệu và high-watermark đủ ổn định qua restart. Nếu nguồn bị sửa trong lúc chạy, cần đánh giá snapshot/isolation hoặc chiến lược xử lý thay đổi; phân vùng theo ID một mình chưa đảm bảo cùng một ảnh chụp dữ liệu.

### Cân bằng partition và throughput

Nếu partition A có 1 triệu item, partition B có 5.000 item và partition C có 3.000 item, thời gian job vẫn bị kéo dài bởi partition A. Chia range ID bằng nhau không bảo đảm số hàng bằng nhau vì ID có khoảng trống hoặc phân bố dữ liệu lệch.

Có thể tạo nhiều partition hơn số worker để cân bằng, nhưng quá nhiều partition nhỏ làm tăng metadata, khởi tạo reader và chi phí điều phối. Hãy đo **thời gian mỗi partition** cùng số item đọc/ghi để phát hiện lệch tải.

## 11. Remote chunking và remote partitioning gặp giới hạn khác nhau

| Đặc điểm | Remote chunking | Remote partitioning |
| --- | --- | --- |
| Ai đọc nguồn? | Manager đọc item | Mỗi worker tự đọc phần được giao |
| Dữ liệu gửi qua mạng | Item/chunk và phản hồi | Yêu cầu phần việc/định danh partition; metadata liên quan |
| Nút thắt đọc thường gặp | Reader trung tâm, serialization, broker | DB nguồn chịu nhiều reader, query/index |
| Nút thắt ghi thường gặp | DB/API đích của các worker | DB/API đích của các worker |
| Khả năng tăng worker | Có ích khi process/write chậm hơn reader | Có ích khi nguồn chịu được nhiều reader độc lập |
| Complexity vận hành | Message queue, ack, retry, payload | Partition ownership, StepExecution, repository, điều phối |
| Yêu cầu tính đúng | Idempotent write khi message được giao lại | Phân vùng không chồng lấn, checkpoint và idempotency |

**Remote chunking:** nếu manager đọc tối đa 6.000 item/s, worker có tổng năng lực 30.000 item/s cũng không biến đầu vào thành 30.000 item/s. Thêm worker chỉ có ích nếu ban đầu process/write là phần giới hạn.

**Remote partitioning:** có thể tách reader trung tâm, nhưng nếu bốn worker cùng khiến DB nguồn full scan hoặc quá tải I/O, tổng read throughput có thể thấp hơn một reader được tối ưu.

Ngoài throughput, hai mô hình đều cần xử lý sự cố worker commit thành công nhưng thông tin xác nhận chưa tới manager, kết nối broker mất và metadata không cập nhật đồng thời. Không dựa vào số worker hoặc trạng thái ack để mặc định “exactly once”; cần idempotency và đối soát nghiệp vụ.

## 12. Commit interval ảnh hưởng cả tốc độ đọc và ghi

Trong chunk-oriented step, **commit interval** quyết định số item đầu vào mục tiêu của mỗi chunk. Interval quá nhỏ có thể tạo rất nhiều commit, khiến write throughput giảm do overhead. Interval quá lớn có thể tăng memory, thời gian transaction, lock và lượng công việc phải xử lý lại khi rollback.

Ví dụ với 2 triệu item đầu vào, nếu không filter/skip/retry:

| Commit interval | Số chunk xấp xỉ | Điều cần quan sát |
| ---: | ---: | --- |
| 10 | 200.000 | Commit overhead có cao không? |
| 100 | 20.000 | Writer có gom batch tốt hơn không? |
| 500 | 4.000 | Throughput/transaction duration cân bằng thế nào? |
| 2.000 | 1.000 | Heap, lock, rollback có tăng đáng kể không? |
| 10.000 | 200 | Transaction quá dài hoặc timeout không? |

Không suy ra **số lần commit DB chính xác** từ bảng vì metadata, lỗi/retry và cấu hình giao dịch có thể tạo thêm thao tác. Không có một interval tối ưu cố định; phải đo đúng workload.

**Phân biệt:** một reader có page size 200, writer có JDBC batch size khác và step có commit interval 500 là cấu hình hoàn toàn có thể xảy ra. Page/fetch/batch size thuộc tầng reader/driver/writer, còn commit interval điều khiển chu kỳ chunk.

## 13. Đo đúng bottleneck bằng số liệu

### 13.1. Metric của Spring Batch

Một phép thống kê cơ bản:

\[
\mathrm{ReadRate}=\frac{\mathrm{readCount}}{T_{\mathrm{step}}},\qquad
\mathrm{WriteRate}=\frac{\mathrm{writeCount}}{T_{\mathrm{step}}}
\]

Đơn vị tương ứng item/s; \(T_{\mathrm{step}}\) là thời gian step tính bằng giây, bao gồm chờ, retry và phần kết thúc. Khi so sánh, phải dùng dataset và cùng chính sách filter/skip tương đương.

Thông tin StepExecution hữu ích:

| Chỉ số | Cách diễn giải |
| --- | --- |
| readCount | Số item được reader ghi nhận là đã đọc |
| writeCount | Số item đầu ra được step ghi nhận ghi thành công |
| filterCount | Item bị processor lọc |
| commitCount | Số commit ở mức thống kê StepExecution |
| rollbackCount | Tín hiệu rollback/retry cần truy nguyên |
| readSkipCount/processSkipCount/writeSkipCount | Item bị skip ở các giai đoạn |
| startTime/endTime | Mốc tính thời gian step khi có đủ dữ liệu |

Một truy vấn **đọc metadata** có thể hỗ trợ điều tra, tùy schema và phiên bản JobRepository:

~~~sql
SELECT STEP_NAME,
       STATUS,
       READ_COUNT,
       WRITE_COUNT,
       FILTER_COUNT,
       COMMIT_COUNT,
       ROLLBACK_COUNT,
       START_TIME,
       END_TIME
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId;
~~~

**Lưu ý:** đọc thống kê commitCount không cho biết mọi DB transaction hay chính xác thời gian chờ. Phải kết hợp metric DB/driver, log ứng dụng và tracing.

### 13.2. Metric nguồn/đích

**Phía đọc:**

- p50/p95 query latency, rows scanned/returned, số query và execution plan.
- JDBC connection wait, fetch/page latency, network receive throughput.
- CPU parser/mapper, GC và allocation rate.
- Thời gian đọc mỗi partition, tỷ lệ worker bị idle.

**Phía ghi:**

- Thời gian batch write, commit latency, transaction duration.
- DB log I/O, active connections, lock wait, deadlock.
- Số item/batch, lỗi constraint và retry.
- Thời gian chờ API/quota, số response 429/5xx khi dùng dịch vụ ngoài.

**Từ đầu đến cuối:**

- Job/step elapsed time và throughput thực tế.
- CPU, heap, GC của mỗi JVM; disk/network của host.
- Queue depth, message age và worker utilization nếu phân tán.
- Số business key duy nhất đã ghi, dữ liệu thiếu/trùng sau restart.

### 13.3. Không nhầm latency với throughput

Một request DB chậm 100 ms không nhất thiết khiến hệ thống chỉ xử lý 10 item/s nếu có nhiều request hợp lệ chạy đồng thời. Ngược lại, nhiều request đang xử lý không đảm bảo throughput cao nếu DB đã bão hòa. Cần đo **cả số hoạt động đồng thời, thời gian phản hồi và số item hoàn tất/giây**.

Với workload có item lớn nhỏ khác nhau, nên bổ sung **MB/s** và phân bố kích thước item. Hai lần chạy cùng 10.000 item/s nhưng item trung bình 1 KiB và 50 KiB có thể tạo tải mạng/heap rất khác nhau.

## 14. Quy trình benchmark có kiểm soát

Một thí nghiệm tốt trả lời được: **bottleneck là gì, một thay đổi cải thiện ở đâu và đổi lại chi phí gì?**

### Bước 1 — Chọn dữ liệu đại diện

Sử dụng khối lượng, kích thước item, phân bố key, tỷ lệ filter/skip, tỷ lệ cập nhật và index gần thực tế. Chỉ chạy vài nghìn record trên database rỗng có thể khiến phần khởi tạo chiếm phần lớn thời gian và đánh lừa về tốc độ bền vững.

### Bước 2 — Đo baseline ít concurrency

Bắt đầu với một step và số thread thấp, ghi:

- Thời gian read/process/write trên tập dữ liệu đại diện.
- ReadCount, writeCount, filterCount, commit/rollback.
- CPU/GC, query latency, batch write latency, connection wait, lock.
- Tốc độ đọc/ghi bền vững theo từng cửa sổ thời gian thay vì chỉ tốc độ tức thời.

### Bước 3 — Tối ưu đúng tầng đang chậm

Nếu **đọc chậm**, thử query/index, lọc tại nguồn, cột cần lấy, fetch/page size, parsing hoặc chia range. Nếu **ghi chậm**, kiểm tra JDBC batching, số index, lock, transaction duration, writer logic và commit interval.

Sau mỗi thay đổi, đo lại bottleneck: đôi khi khi reader nhanh hơn, writer sẽ trở thành phần giới hạn tiếp theo.

### Bước 4 — Tăng concurrency từng nấc

Thử 1 → 2 → 4 → 8 thread/partition/worker khi tài nguyên cho phép. Cố định dataset, code và các tham số khác. Theo dõi speedup, throughput thực tế, DB saturation và rollback.

### Bước 5 — Thử lỗi và restart

Dừng worker giữa chunk, làm chậm DB, tạo lỗi kết nối, kiểm tra retry/backoff. Sau khi restart, đối soát business key, không chỉ tổng số record. Chỉ chấp nhận cấu hình nhanh hơn nếu không làm sai đầu ra hoặc khiến phục hồi vượt SLA.

### Bảng kết quả minh họa

Số liệu dưới đây hoàn toàn **giả định**. Hai cột tốc độ mô tả **năng lực đo riêng** của phần đọc và phần ghi trong các bài thử có điều kiện tương đương, không phải hai bộ đếm của cùng một StepExecution:

| Cấu hình | Năng lực đọc (input/s) | Năng lực ghi (output/s) | DB lock wait | Kết luận tạm |
| --- | ---: | ---: | --- | --- |
| 1 worker, chunk 100 | 4.000 | 4.000 | Thấp | Baseline |
| 2 worker, chunk 100 | 7.200 | 7.100 | Thấp | Song song có ích |
| 4 worker, chunk 100 | 12.500 | 9.300 | Trung bình | Writer bắt đầu nghẽn |
| 8 worker, chunk 100 | 14.000 | 9.100 | Cao | Tăng worker phản tác dụng |
| 4 worker, chunk 500 + writer tối ưu | 14.000 | 12.300 | Trung bình | Cải thiện bottleneck ghi |

Bảng cho thấy năng lực đọc có thể cao hơn năng lực ghi mà **throughput hoàn tất của toàn job vẫn bị giới hạn bởi phần ghi**. Đây là kết quả đo công đoạn tách biệt: khi chạy một step chunk-oriented một-đổi-một đến khi COMPLETED, **readCount và writeCount cuối kỳ thường gần nhau**; không dùng hai năng lực đo riêng để suy ra rằng job đã đọc nhiều item hơn số item ghi mà không có filter, skip hoặc lỗi.

Bài học từ bảng: khi tăng lên tám worker mà write rate không tăng, hãy tìm bottleneck ở đích, thay vì tiếp tục nhân worker.

## 15. Tình huống thực tế: tám triệu bản ghi trong mười phút

Một doanh nghiệp xử lý **8 triệu giao dịch** sau khi chốt ngày. Processor lọc khoảng **20%** bản ghi không cần ghi vào kho phân tích. SLA là hoàn thành trong **10 phút**, tức 600 giây.

Số item đầu ra kỳ vọng:

\[
8.000.000 \times 0{,}8 = 6.400.000
\]

Theo phép chia lý tưởng, mục tiêu tối thiểu là:

\[
R_{\mathrm{input,required}}\geq\frac{8.000.000}{600}
\approx13.333\ \mathrm{input/s}
\]

\[
R_{\mathrm{output,required}}\geq\frac{6.400.000}{600}
\approx10.667\ \mathrm{output/s}
\]

Giả sử nhóm đo được các năng lực bền vững sau; đây là **số liệu giả định**, chưa tính mọi overhead:

| Thành phần | Năng lực đo được | Ảnh hưởng |
| --- | ---: | --- |
| Nguồn đọc hiện tại | 14.000 input/s | Trần đọc |
| Processor nhiều worker | 18.000 input/s | Chưa nghẽn |
| Đích ghi hiện tại | 9.000 output/s | Trần ghi |
| Tỷ lệ tạo output | 0,8 output/input | Cần quy đổi đơn vị |

Writer 9.000 output/s tương đương:

\[
9.000 / 0{,}8 = 11.250\ \mathrm{input/s}
\]

Do đó, throughput đầu vào tối đa của pipeline theo mô hình là **11.250 input/s** và thời gian tối thiểu **khoảng 711 giây (11 phút 51 giây)**, vượt SLA 10 phút.

**Phương án A: chỉ thêm reader/worker.** Nếu read rate tăng lên 20.000 input/s nhưng writer vẫn 9.000 output/s, trần hiệu quả **không đổi**. Không nên chọn giải pháp tăng worker chỉ vì nguồn có thể đọc nhanh hơn.

**Phương án B: tối ưu writer và commit interval.** Nhóm cải thiện JDBC batch write, query/update phù hợp và giảm tranh chấp để đạt 12.000 output/s. Trần quy đổi của writer là 15.000 input/s; lúc này reader **14.000 input/s** trở thành giới hạn. Thời gian tối thiểu **khoảng 571 giây (9 phút 31 giây)**, chỉ còn rất ít thời gian cho khởi tạo và retry.

**Phương án C: đo lại reader, cân nhắc partitioning.** Nếu DB nguồn chịu được nhiều reader độc lập và tổng read rate tăng tới 18.000 input/s, writer **12.000 output/s** trở thành giới hạn; tốc độ tương đương 15.000 input/s và thời gian lý tưởng **khoảng 533 giây (8 phút 53 giây)**. Khi đó có thêm dư địa cho overhead, nhưng vẫn cần benchmark end-to-end và thử lỗi.

### Lựa chọn kiến trúc trong tình huống

- Nếu một JVM chưa dùng hết CPU và reader/processor/writer phù hợp concurrency, thử multi-threaded step hoặc local partitioning.
- Nếu các khoảng ID độc lập, một JVM bị giới hạn tài nguyên và DB nguồn còn dư, thử remote partitioning.
- Nếu manager đọc nguồn đủ nhanh còn process/write là nút thắt, cân nhắc remote chunking; tuy nhiên writer/DB đích vẫn có trần chung.
- Nếu API/DB đích đã bão hòa, ưu tiên tối ưu ghi và điều tiết tải hơn là nhân worker.

Không lựa chọn kiến trúc chỉ dựa trên thời gian của lần chạy không lỗi. SLA có thể yêu cầu dư địa đủ để restart, xử lý lỗi tạm thời và đối soát đầu ra.

## 16. Retry, restart và tính đúng dữ liệu khi tối ưu đọc/ghi

### 16.1. Tăng read throughput phải giữ tập dữ liệu nhất quán

Khi nhiều reader đọc các range khác nhau, cần bảo đảm:

- Mỗi business key thuộc đúng một partition.
- Không có khoảng trống hoặc chồng lấn ở ranh giới ID/ngày/tenant.
- Thứ tự đọc ổn định nếu reader dựa vào vị trí để restart.
- High-watermark hoặc snapshot logic nhất quán khi dữ liệu thay đổi.
- Partition name và input phù hợp với StepExecution được lưu khi restart.

Nếu job đang đọc bảng thay đổi liên tục, một record có thể chuyển trạng thái hoặc điều kiện lọc giữa hai lần quét. Chia range theo ID chưa đủ để giải quyết vấn đề snapshot; cần chính sách nghiệp vụ và cô lập dữ liệu phù hợp.

### 16.2. Tăng write throughput phải giữ idempotency

Worker có thể commit ghi xuống DB thành công nhưng chết trước khi manager nhận xác nhận. Tùy kiến trúc, hệ thống có thể thử lại chunk hoặc partition. Writer cần có khả năng chạy lại an toàn, ví dụ:

- Unique constraint trên khóa nghiệp vụ.
- Upsert có ngữ nghĩa đúng.
- Idempotency key cho API bên ngoài.
- Outbox nếu phải phối hợp DB và message.
- Đối soát số business key và trạng thái sau retry.

Không dùng trạng thái **COMPLETED** của job như bằng chứng duy nhất rằng không có dữ liệu trùng hoặc thiếu. Phải kiểm tra kết quả nghiệp vụ.

### 16.3. Tuning cùng retry/restart

Commit interval lớn giảm số commit nhưng có thể tăng lượng việc phải làm lại khi rollback. Nhiều worker tăng tổng transaction đồng thời nhưng cũng có thể tăng deadlock và timeout. Khi thử cấu hình mới, nên có bài kiểm tra:

1. Dừng một worker giữa chunk.
2. Bật lại và restart theo cách vận hành dự kiến.
3. Đo số item được xử lý lại, lỗi skip/retry và thời gian hoàn thành.
4. So sánh tập business key đầu ra với đầu vào hợp lệ.
5. Kiểm tra connection, lock và hàng đợi trở lại ổn định sau sự cố.

**Throughput đạt mục tiêu khi không lỗi** chưa đủ để chứng minh kiến trúc phù hợp production.

## 17. Những nhầm lẫn thường gặp

| Nhận định | Điều cần hiểu |
| --- | --- |
| “Có 8 worker thì tốc độ đọc/ghi phải tăng 8 lần.” | Nguồn/đích, CPU, DB connection, lock và mạng có trần chung. |
| “ReadCount lớn hơn WriteCount chứng tỏ mất dữ liệu.” | Processor có thể lọc/skip; phải xem filterCount, skipCount và nghiệp vụ. |
| “Chỉ cần đo item/giây là đủ.” | Còn cần byte/s, latency, p95 query/commit, heap, contention và tính đúng. |
| “Tăng fetch size tức là tăng commit interval.” | Fetch size thuộc JDBC driver, commit interval thuộc chunk transaction. |
| “Đọc bằng nhiều partition chắc chắn nhanh hơn một cursor.” | Có thể làm DB quá tải hoặc tạo full scan nếu query/index kém. |
| “Remote chunking chia việc đọc cho nhiều worker.” | Trong mô hình phổ biến, manager đọc và chuyển item/chunk; worker process/write. |
| “Remote partitioning giảm tải DB nguồn.” | Worker tự đọc song song; tổng tải lên nguồn có thể **tăng**. |
| “Writer được gọi một lần cho 500 item tức chỉ có một SQL statement.” | Writer/driver có thể gửi batch nhiều statement; cách DB thực thi phụ thuộc cấu hình. |
| “Queue càng dài nghĩa là throughput càng cao.” | Queue tăng thường báo producer vượt consumer, tạo backlog và latency. |
| “Rollback DB sẽ hoàn tác request HTTP đã gửi.” | Side effect ngoài transaction cần idempotency và điều phối riêng. |
| “Writer nhanh hơn nên job chắc chắn nhanh hơn.” | Nếu reader hoặc processor đã là giới hạn, cải thiện writer có thể không đổi thời gian job. |

## 18. Checklist xác nhận giới hạn đọc/ghi

- [ ] Định nghĩa rõ read/write throughput theo **input** hay **output** item và thời gian đo.
- [ ] Có readCount, writeCount, filter/skip, commit/rollback cho cùng tập dữ liệu đại diện.
- [ ] Đã đo query plan, rows scanned, JDBC fetch/page latency và CPU parsing ở reader.
- [ ] Đã đo batch write/commit latency, index cost, lock wait, DB log I/O và connection pool.
- [ ] Biết có giới hạn quota/rate API hoặc broker/network hay không.
- [ ] Chunk size và reader fetch/page size được điều chỉnh độc lập, có benchmark.
- [ ] Đã kiểm chứng thread safety trước khi dùng multi-threaded step.
- [ ] Nếu partitioning, input không chồng lấn, tên partition ổn định và restartable.
- [ ] Nếu remote, đã theo dõi message backlog, worker state, ack/retry và JobRepository.
- [ ] Có idempotency, retry/backoff và đối soát dữ liệu sau sự cố.
- [ ] Đã đo speedup khi tăng concurrency và xác định bottleneck mới.
- [ ] Cấu hình đạt SLA với dự phòng tài nguyên và thời gian khôi phục chấp nhận được.

## 19. Câu hỏi tự kiểm tra

**1. Reader đọc được 20.000 item/s nhưng writer chỉ ghi được 8.000 item/s, một item đọc tạo đúng một item ghi. Thêm reader có giúp tăng throughput toàn job không?**

Không đáng kể nếu writer vẫn giữ trần 8.000 item/s. Cần tối ưu writer/đích hoặc thay đổi yêu cầu nghiệp vụ trước.

**2. Tại sao cần quy đổi tỷ lệ filter khi so read throughput và write throughput?**

Vì readRate có đơn vị item đầu vào/giây, writeRate là item đầu ra/giây. Nếu chỉ 50% item được ghi, năng lực writer 5.000 output/s tương đương 10.000 input/s theo mô hình một đầu vào tạo tối đa một đầu ra.

**3. Có thể dùng một JdbcCursorItemReader singleton với TaskExecutor 16 thread mà mặc định an toàn không?**

Không. Reader có state/cursor có thể không thread-safe; cần đánh giá reader và checkpoint, hoặc dùng partitioning với reader độc lập theo phạm vi dữ liệu.

**4. Vì sao remote partitioning đôi khi làm tốc độ đọc giảm?**

Nhiều worker cùng quét nguồn gây tải query, index, connection, I/O và lock lớn hơn, đặc biệt khi mỗi partition có query không hiệu quả.

**5. Vì sao phải đo connection wait cùng query duration?**

Một step có thể chậm vì chờ lấy connection trước khi query bắt đầu, dù bản thân SQL chạy nhanh. Tăng thread khi pool/DB đã đầy thường không tăng throughput.

**6. Nếu chunk 100 nhanh hơn chunk 10, có nên thử chunk 100.000 ngay không?**

Không có cơ sở để khẳng định tốt hơn. Cần tăng từng nấc và đo heap, thời gian transaction, lock, rollback, retry và restart; chunk lớn có thể gây chậm hoặc lỗi.

**7. Job đạt throughput mục tiêu khi chạy bình thường nhưng sau khi kill worker ghi trùng 2.000 record, cấu hình có được xem là đạt không?**

Không. Tính đúng của dữ liệu là điều kiện bắt buộc. Cần writer idempotent, metadata/checkpoint chính xác và thử lại quy trình restart.

---

**Ghi nhớ:** Tốc độ hoàn thành Spring Batch bị giới hạn bởi **công đoạn có năng lực phục vụ thấp nhất sau khi quy đổi cùng đơn vị dữ liệu** và bởi chi phí phối hợp giữa các công đoạn. Thêm thread, partition hay worker chỉ giúp khi phần việc song song thực sự giảm bottleneck mà không làm nguồn/đích quá tải. Hãy đo read/write throughput cùng latency, DB contention và retry/restart, rồi lựa chọn kiến trúc dựa trên giới hạn tài nguyên được xác minh.
