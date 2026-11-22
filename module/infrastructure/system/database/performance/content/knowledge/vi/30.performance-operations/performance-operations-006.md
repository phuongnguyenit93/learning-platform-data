# Nâng cấp hệ quản trị hoặc trình điều khiển và kiểm tra hồi quy kế hoạch

Nâng cấp hệ quản trị cơ sở dữ liệu (DBMS) hoặc JDBC driver có thể mang lại bản vá bảo mật, sửa lỗi, tính năng mới và cải thiện hiệu năng. Tuy nhiên, cùng một câu SQL có thể được optimizer lập kế hoạch khác sau nâng cấp. Driver mới cũng có thể thay đổi cách bind kiểu dữ liệu, dùng server-side prepare, gửi batch, đọc ResultSet hoặc quản lý timeout. Một thay đổi được xem là tương thích ở mức kết nối vẫn có thể làm latency tăng, CPU cao hơn hoặc khiến truy vấn chọn access path kém.

Trong phạm vi **DATABASE_PERFORMANCE**, vận hành hiệu năng phải dựa trên đo đạc tải, execution plan, thống kê và cơ chế truy cập dữ liệu. Vì vậy, nâng cấp DBMS hoặc driver cần có baseline trước thay đổi, bộ truy vấn đại diện, kiểm tra hồi quy kế hoạch và theo dõi sau triển khai. Mục tiêu là xác nhận phiên bản mới hoạt động đúng với workload thực tế, duy trì SLO và không tạo regression về CPU, I/O, lock, memory hoặc throughput.

Bài học này trình bày sự khác nhau giữa nâng cấp DBMS và JDBC driver, các nguyên nhân làm plan thay đổi, cách thu thập baseline, kiểm tra plan và runtime, kiểm thử driver, triển khai theo giai đoạn, xử lý regression và chuẩn bị rollback cho PostgreSQL, MySQL InnoDB và SQL Server.

## 1. Phân biệt nâng cấp DBMS và nâng cấp JDBC driver

DBMS và JDBC driver nằm ở hai phần khác nhau của đường truy cập dữ liệu.

~~~text
Java application
      |
      v
JDBC driver
      |
      | protocol, bind, prepare, fetch, timeout
      v
Database server
      |
      | parse, optimize, execute, lock, buffer, storage
      v
Data files / transaction log
~~~

### Nâng cấp DBMS

Nâng cấp server có thể thay đổi:

- Parser, optimizer và cost model.
- Cardinality estimation, histogram và statistics.
- Access path, join order, join algorithm và parallel execution.
- Cách quản lý plan cache và prepared statement.
- Transaction, locking, MVCC và concurrency control.
- Buffer/cache, memory grant, sort/hash và temp I/O.
- WAL/redo/log, checkpoint và recovery.
- System catalog, data type, collation và SQL behavior.
- Protocol, authentication, TLS, replication và monitoring views.

Một major upgrade thường có phạm vi tác động lớn hơn một minor/patch upgrade, nhưng không thể giả định patch upgrade không làm thay đổi hành vi. Hãy đọc release notes, upgrade notes và compatibility notes của đúng phiên bản.

### Nâng cấp JDBC driver

Driver là cầu nối giữa ứng dụng Java và giao thức database. Driver mới có thể thay đổi:

- Cách ánh xạ Java type sang SQL type.
- Cách bind NULL, date/time, decimal, UUID, JSON hoặc binary.
- Server-side prepare và ngưỡng chuyển từ client-side sang server-side prepare.
- Statement cache, parameter metadata và plan reuse.
- Batch execution hoặc rewrite batch thành multi-row statement.
- Fetch size, cursor và streaming ResultSet.
- Query cancellation, socket timeout và network timeout.
- Connection establishment, TLS, authentication và failover.
- Cách xử lý warning, exception, generated keys và update counts.

Driver upgrade thường không thay optimizer của database, nhưng có thể khiến database nhận kiểu tham số, câu SQL hoặc protocol khác. Điều đó có thể dẫn đến plan khác hoặc làm ứng dụng gửi nhiều round trip hơn.

### Hai nâng cấp có thể tương tác

Nếu cùng lúc nâng DBMS và JDBC driver, khi hiệu năng thay đổi sẽ khó xác định nguyên nhân. Khi có thể, kiểm tra từng thay đổi độc lập:

1. DBMS mới với driver hiện tại đã được hỗ trợ.
2. Driver mới với DBMS hiện tại.
3. Tổ hợp DBMS và driver dự kiến đưa vào production.

Một số phiên bản driver không hỗ trợ server cũ hoặc server mới yêu cầu driver tối thiểu. Ma trận tương thích của vendor là điều kiện bắt buộc trước khi tách thử nghiệm.

## 2. Vì sao execution plan có thể thay đổi sau nâng cấp?

Optimizer lựa chọn plan dựa trên SQL, schema, index, statistics, cấu hình, tham số và phiên bản engine. Khi một trong các yếu tố thay đổi, plan có thể khác.

### Thay đổi optimizer hoặc cost model

Phiên bản mới có thể:

- Ước lượng cardinality khác.
- Chọn join order khác.
- Chọn Nested Loop thay Hash Join hoặc ngược lại.
- Chọn index scan thay table scan.
- Thay đổi parallelism.
- Thay đổi memory grant hoặc chiến lược sort/hash.
- Áp dụng transformation hoặc rewrite mới.

Một plan mới có thể tốt hơn cho một nhóm dữ liệu nhưng kém hơn với tham số khác. Không đánh giá chỉ bằng việc plan tree có khác hay không; phải xem runtime trên workload đại diện.

### Thống kê thay đổi

Nâng cấp có thể tạo yêu cầu hoặc cơ hội thu thập lại statistics. Sau khi restore, migrate hoặc bulk load, thống kê có thể khác về thời điểm, sample, histogram hoặc metadata. Optimizer dùng thống kê để ước lượng số dòng và chọn access path.

Nếu thống kê thiếu hoặc không đại diện, plan mới có thể chọn scan, join hoặc sort đắt hơn. Ngược lại, thống kê mới chính xác hơn có thể cải thiện plan đáng kể.

### Plan cache bị tạo lại

Sau restart, upgrade hoặc thay đổi cấu hình, plan cache có thể rỗng hoặc chứa plan mới. Hiệu năng ngay sau cutover có thể khác khi cache còn lạnh. Không được so sánh một lần chạy cold cache với baseline warm cache rồi kết luận optimizer regression.

Plan cache cũng có thể bị invalidation hoặc recompile do schema, statistics, compatibility setting hoặc metadata thay đổi.

### Kiểu tham số và cách prepare thay đổi

Một driver mới có thể bind số nguyên thành BIGINT thay vì INTEGER, truyền chuỗi với độ dài/collation khác, hoặc thay cách gửi prepared statement. Implicit conversion có thể khiến index seek không còn phù hợp.

Prepared statement cũng có thể dùng custom plan hoặc generic plan tùy engine. Nếu phân bố tham số lệch, một plan dùng chung có thể không phù hợp cho mọi giá trị.

### Cấu hình và môi trường thay đổi

Plan có thể khác do:

- Compatibility level hoặc optimizer feature setting.
- Parallelism setting.
- Memory limit hoặc resource group.
- Collation, timezone hoặc SQL mode.
- Index bị thiếu, thay đổi hoặc chưa được tạo lại.
- Hardware, storage latency hoặc CPU quota khác.
- Số partition, schema hoặc data distribution thay đổi.

Khi kiểm tra hồi quy, phải ghi lại những khác biệt này để tránh quy lỗi cho phiên bản DBMS khi nguyên nhân nằm ở môi trường.

## 3. Hiểu plan regression

Plan regression xảy ra khi thay đổi môi trường, phiên bản, thống kê hoặc cách thực thi khiến truy vấn có kế hoạch mới kém hiệu quả hơn trên workload thực tế.

Dấu hiệu thường gặp:

- Query latency p95/p99 tăng sau cutover.
- CPU hoặc logical reads tăng dù query mix tương tự.
- Một query fingerprint có elapsed/worker time tăng rõ rệt.
- Estimated rows lệch xa actual rows hơn trước.
- Index seek chuyển thành scan không hợp lý.
- Nested Loop có loops tăng mạnh.
- Sort/hash spill xuất hiện hoặc tăng.
- Parallel plan tạo nhiều worker nhưng throughput không tăng.
- Planning/compile time tăng.
- Một số giá trị tham số chậm hơn nhiều so với nhóm khác.

### Khác biệt plan không đồng nghĩa regression

Một plan mới có thể có operator khác nhưng thực thi nhanh hơn. Ví dụ, optimizer chọn sequential scan thay index lookup khi cần đọc phần lớn bảng. Đó có thể là lựa chọn đúng.

Chỉ coi là regression khi bằng chứng runtime cho thấy mục tiêu hiệu năng xấu đi trong điều kiện tương đương: latency, CPU, I/O, memory, lock hoặc throughput.

### Regression có thể chỉ xuất hiện ở một nhóm tham số

Một query theo tenant nhỏ có thể nhanh hơn nhưng tenant lớn chậm hơn; trạng thái hiếm có thể tốt nhưng trạng thái phổ biến kém. Vì vậy, phải kiểm tra nhiều nhóm tham số và data skew, không chỉ một giá trị mẫu.

## 4. Xây dựng baseline trước khi nâng cấp

Baseline là bộ dữ liệu tham chiếu để so sánh trước/sau. Không có baseline, nhóm vận hành khó xác định thay đổi nào gây regression và mức độ ảnh hưởng ra sao.

### Baseline ở cấp hệ thống

Ghi nhận:

- DBMS product, edition, version, build và patch level.
- JDBC driver name, version và URL properties liên quan.
- Java runtime, framework, ORM và connection pool version.
- CPU quota/core, RAM, storage class và network topology.
- Connection pool size, active/idle/pending và timeout.
- Database configuration quan trọng.
- Schema, index, partition và compatibility setting.
- Statistics collection time và plan cache state.

Không ghi password, token hoặc credential vào báo cáo baseline. Connection URL có thể chứa thông tin nhạy cảm; cần mask trước khi lưu.

### Baseline workload

Chọn workload đại diện cho:

- Giao dịch đọc ngắn.
- Giao dịch ghi và commit.
- Truy vấn join nhiều bảng.
- Báo cáo/aggregate.
- Truy vấn có tham số hiếm và phổ biến.
- Batch insert/update.
- Truy vấn trả nhiều dòng và streaming.
- Truy vấn có transaction/lock contention.

Ghi lại request rate, QPS/TPS, concurrency, tỷ lệ đọc/ghi, kích thước dữ liệu, thời điểm chạy batch và các job nền.

### Baseline hiệu năng

Các chỉ số cần lưu:

| Nhóm | Chỉ số |
|---|---|
| Ứng dụng | p50/p95/p99, error rate, timeout, throughput |
| JDBC | connection acquisition, execute, fetch, batch duration |
| Database | CPU, active sessions, query count, worker/CPU time |
| Query | calls, total/average time, rows, logical reads/buffers |
| Plan | plan shape/hash nếu có, estimated/actual rows, loops, spill |
| I/O | physical reads/writes, latency, IOPS, throughput |
| Transaction | commit latency, lock wait, deadlock, rollback |
| Memory | buffer/cache hit, memory grant, temp usage |
| Vận hành | replication lag, checkpoint, backup, maintenance activity |

Lấy mẫu trong khoảng đủ dài để bao phủ chu kỳ tải. Ghi thời điểm reset counters và cách tính delta; counter tích lũy không thể so sánh trực tiếp nếu uptime hoặc thời gian đo khác nhau.

## 5. Chọn truy vấn đại diện và bộ kiểm thử hồi quy

Không cần kiểm thử mọi câu SQL theo cùng mức ưu tiên. Chọn bộ query có tác động lớn đến SLO và đại diện các kiểu truy cập.

### Chọn theo mức đóng góp

Ưu tiên:

- Query có tổng CPU hoặc worker time cao.
- Query có tổng elapsed time cao.
- Query được gọi rất thường xuyên.
- Query có p95/p99 cao.
- Query có logical reads hoặc rows examined lớn.
- Query phục vụ giao dịch quan trọng.
- Query nhạy với tham số hoặc có plan thay đổi thường xuyên.

Một query ít chạy nhưng là bước xác nhận thanh toán có thể quan trọng hơn một query báo cáo chạy theo lịch. Cần kết hợp chi phí và mức độ quan trọng nghiệp vụ.

### Lưu SQL shape và parameter set

Với mỗi query, lưu:

- SQL fingerprint hoặc digest.
- SQL text đã mask dữ liệu nhạy cảm.
- Kiểu dữ liệu của từng bind parameter.
- Nhóm tham số đại diện: nhỏ/lớn, hiếm/phổ biến, tenant nhỏ/lớn.
- Kết quả kỳ vọng hoặc invariant nghiệp vụ.
- Execution plan trước nâng cấp.
- Runtime metrics và điều kiện cache.
- Transaction isolation và session settings có liên quan.

Không lưu giá trị nhạy cảm không cần thiết. Có thể dùng dữ liệu tổng hợp hoặc test dataset đã ẩn danh.

### Bảo đảm dữ liệu thử có tính đại diện

Dataset quá nhỏ có thể khiến optimizer chọn plan khác production. Dataset không có skew sẽ bỏ sót parameter-sensitive plan. Hãy giữ phân bố dữ liệu, tỷ lệ NULL, cardinality, độ dài chuỗi và index tương đương mức cần thiết.

## 6. So sánh execution plan đúng cách

Plan thường có nhiều trường phụ thuộc phiên bản và môi trường. So sánh nên tập trung vào cấu trúc quan trọng và chi phí thực tế.

### Những thành phần cần so sánh

- Access path: table scan, index scan, seek, bitmap hoặc partition scan.
- Join order và join algorithm.
- Estimated rows so với actual rows.
- Loops của từng operator.
- Sort/hash và spill.
- Memory grant hoặc work memory.
- Parallel workers và exchange.
- Predicate pushdown và partition pruning.
- Logical reads/buffers và physical reads.
- CPU/worker time và elapsed time.

### Không so sánh cost estimate giữa các phiên bản như số đo tuyệt đối

Optimizer cost là ước lượng nội bộ dùng để chọn plan. Cost units và cách tính có thể thay đổi giữa phiên bản hoặc cấu hình. Không kết luận plan mới chậm hơn chỉ vì cost estimate lớn hơn.

Hãy dùng actual runtime, CPU, I/O và latency trên cùng workload. Estimated cost vẫn hữu ích để hiểu quyết định optimizer trong một môi trường cụ thể.

### Plan hash và plan shape

Một số engine có plan hash hoặc query plan identifier. Hash thay đổi có thể báo hiệu plan khác, nhưng không nói plan mới tốt hay xấu. Ngược lại, plan hash giống nhau không bảo đảm runtime giống nhau nếu dữ liệu, cache, storage hoặc concurrency thay đổi.

Dùng plan hash để phát hiện thay đổi, sau đó xem plan detail và runtime metrics.

## 7. Kiểm tra các nguyên nhân hồi quy phổ biến

### Cardinality estimation thay đổi

So sánh estimated rows và actual rows ở các node quan trọng. Sai lệch lớn có thể xuất phát từ statistics, data skew, correlation hoặc parameter value. Cập nhật statistics chỉ khi có bằng chứng thống kê không còn đại diện; analyze cũng có thể làm optimizer chọn plan mới nên cần benchmark lại.

### Index không được sử dụng như trước

Kiểm tra:

- Bind type có khớp kiểu cột không?
- Có implicit conversion trên cột không?
- Collation hoặc case sensitivity thay đổi không?
- Predicate có còn SARGable không?
- Index có tồn tại, valid và được optimizer xem xét không?
- Index statistics có cập nhật không?
- Parameter value có đủ chọn lọc để dùng index không?

Không ép optimizer dùng index chỉ vì plan cũ có index. Scan có thể tốt hơn nếu tỷ lệ dòng cần đọc cao.

### Join order hoặc join algorithm thay đổi

Một join order mới có thể làm intermediate result tăng rất lớn. Kiểm tra actual rows giữa các node, loops, memory và spill. Sai cardinality ở node đầu có thể lan qua toàn bộ plan.

### Parallelism thay đổi

Phiên bản mới có thể thay điều kiện chọn parallel plan hoặc số worker. Đo tổng CPU, elapsed time, throughput và tác động lên query khác. Một truy vấn nhanh hơn nhờ parallelism có thể chiếm CPU của OLTP.

### Plan cache hoặc parameter sensitivity

Kiểm tra plan được tạo với tham số nào, dùng lại ra sao và có nhiều plan variant không. Đừng chỉ chạy một parameter set sau upgrade. Kiểm tra cơ chế custom/generic plan, parameter sniffing hoặc parameter-sensitive plan tùy engine.

### Parse/compile tăng

Nếu số SQL text hoặc số lần prepare tăng, CPU planning có thể tăng dù execution plan từng query không đổi. Kiểm tra query fingerprint, PreparedStatement lifecycle, driver statement cache và query generator.

## 8. Kiểm tra JDBC driver sau nâng cấp

Driver regression có thể xảy ra ngay cả khi DBMS không đổi. Kiểm tra các hành vi ở tầng JDBC.

### Thông tin driver và server

Ứng dụng có thể ghi thông tin phiên bản khi khởi động:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    logger.info("DB product: {} {}",
        meta.getDatabaseProductName(),
        meta.getDatabaseProductVersion());

    logger.info("JDBC driver: {} {}",
        meta.getDriverName(),
        meta.getDriverVersion());
}
~~~

Không ghi URL có credential hoặc thông tin kết nối bí mật. Ghi phiên bản một lần khi khởi động hoặc khi chẩn đoán, không gọi metadata trong mỗi request.

### Bind parameter và kiểu dữ liệu

Kiểm tra driver mới có thay đổi:

- setObject mapping.
- setNull type inference.
- BigDecimal precision/scale.
- Timestamp/timezone conversion.
- UUID, JSON, array và binary mapping.
- String length, national character và collation behavior.

Một thay đổi kiểu bind có thể tạo implicit conversion hoặc thay đổi selectivity estimation. Kiểm tra kiểu parameter metadata và plan trên server.

### Server-side prepare và statement cache

Một số driver có thể chuyển sang server-side prepare sau ngưỡng thực thi, cache statement theo physical connection hoặc thay đổi cách đóng statement. Cần xem tài liệu driver và cấu hình tương ứng.

Kiểm tra:

- Số prepared statements phía server.
- Plan reuse và plan variants.
- Parse/prepare count.
- Statement cache hit/miss nếu có.
- Open cursor và resource usage.
- Hành vi sau khi connection được trả về pool.

Không bật statement cache lớn tùy tiện. Cache quá lớn có thể làm tăng bộ nhớ server, số cursor và churn khi SQL shape quá đa dạng.

### Batch execution

Driver có thể hỗ trợ rewrite batch thành multi-row insert hoặc dùng giao thức batch. Kiểm tra:

- Số round trip.
- Rows per batch.
- Update counts.
- Generated keys.
- Xử lý BatchUpdateException.
- Transaction boundary và rollback semantics.
- Kích thước packet và giới hạn bind parameters.

Không giả định batch có cùng behavior hoặc tính nguyên tử giữa các driver.

### Fetch size và streaming

Kiểm tra driver có thay đổi cách diễn giải setFetchSize, cursor mode hoặc buffering không. Đo heap allocation, GC, network round trips và thời gian đọc ResultSet.

Một driver mới có thể buffer nhiều dòng hơn, làm throughput tốt hơn nhưng tăng heap; hoặc dùng cursor khiến transaction/connection bị giữ lâu hơn.

### Timeout, cancel và failover

Kiểm tra query timeout, socket timeout, network timeout, statement cancellation, connection validation và failover. Khi timeout xảy ra, xác minh server có dừng statement và transaction đã rollback hay chưa. Mất kết nối trong lúc commit có thể khiến kết quả không rõ; ứng dụng cần idempotency hoặc cơ chế tra cứu trạng thái.

## 9. Ma trận tương thích trước khi nâng cấp

Trước khi triển khai, lập ma trận các thành phần:

| Thành phần | Cần xác nhận |
|---|---|
| DBMS version/build | Đường nâng cấp được hỗ trợ, release notes, breaking changes |
| JDBC driver | Hỗ trợ server version, JDK, protocol và authentication |
| Java runtime | Phiên bản JDK được driver/framework hỗ trợ |
| ORM/framework | Dialect, SQL generation, type mapping và transaction behavior |
| Connection pool | Driver integration, reset state, timeout và statement cache |
| Migration tool | Hỗ trợ metadata/catalog và DDL của phiên bản mới |
| Monitoring/backup | Driver/API, catalog view và format được hỗ trợ |
| Replication/HA | Version compatibility, failover và upgrade topology |

Kiểm tra vendor support matrix và các ghi chú phát hành cụ thể. Không suy ra tương thích chỉ vì ứng dụng biên dịch thành công hoặc connection test trả về thành công.

### Phân biệt compatibility với performance compatibility

- **Functional compatibility:** kết nối, query và transaction vẫn chạy đúng.
- **Protocol compatibility:** driver và server giao tiếp đúng.
- **Performance compatibility:** latency, throughput, CPU, I/O và plan vẫn nằm trong mục tiêu.
- **Operational compatibility:** backup, monitoring, failover, migration và rollback hoạt động.

Một smoke test chỉ chứng minh một phần functional compatibility. Nó không đủ để xác nhận performance compatibility.

## 10. PostgreSQL: kiểm tra sau major/minor upgrade

PostgreSQL có các quy trình nâng cấp khác nhau theo major và minor version. Minor upgrade thường giữ tương thích dữ liệu trong cùng major line theo chính sách phát hành; major upgrade có thể yêu cầu quy trình riêng như pg_upgrade hoặc logical replication. Hãy theo tài liệu đúng phiên bản và kiểm tra extension compatibility.

### Sau nâng cấp

- Kiểm tra extension và version.
- Kiểm tra catalog, collation version và cảnh báo liên quan.
- Chạy ANALYZE khi cần để optimizer có statistics đại diện.
- Kiểm tra partitioned table và thống kê parent/partition.
- Kiểm tra prepared statements trong session mới.
- Theo dõi pg_stat_statements và wait events.
- So sánh EXPLAIN (ANALYZE, BUFFERS) cho query đại diện.

### pg_stat_statements

Extension này cung cấp thống kê theo query identity như calls, execution time, rows và buffer counters. Nó không mặc định là kho lưu toàn bộ execution plan của từng lần chạy. Dùng nó để tìm query có thay đổi calls/time/buffers, sau đó thu plan riêng bằng EXPLAIN hoặc công cụ đã cấu hình.

Các view và cột có thể thay đổi theo phiên bản. Khi nâng cấp extension, làm theo quy trình extension update của PostgreSQL.

### Prepared statement và generic/custom plan

PostgreSQL có thể chọn custom plan hoặc generic plan cho prepared statement theo cơ chế và cấu hình của phiên bản. Khi regression chỉ xuất hiện ở một nhóm tham số, hãy kiểm tra plan thực tế trong session và cách driver sử dụng named/unnamed prepared statement. Không giả định mọi câu PreparedStatement từ JDBC đều có cùng vòng đời server-side.

## 11. MySQL InnoDB: kiểm tra sau upgrade

Sau nâng cấp MySQL, kiểm tra version-specific upgrade notes, data dictionary, plugin/component, authentication, SQL mode và optimizer behavior.

### Thống kê và optimizer

- Xác nhận persistent statistics và histogram nếu đang dùng.
- Chạy ANALYZE TABLE khi dữ liệu hoặc thống kê cần cập nhật.
- Kiểm tra EXPLAIN và EXPLAIN ANALYZE nếu phiên bản hỗ trợ.
- So sánh join order, access type, rows estimate và actual rows.
- Kiểm tra optimizer switches và SQL mode.
- Xem Performance Schema statement digest và wait/file I/O.

ANALYZE TABLE có thể làm optimizer chọn plan khác. Chạy trên staging trước, lưu baseline và so sánh workload sau khi cập nhật.

### Prepared statement và driver

Kiểm tra server-side prepared statement count, parameter type, cursor/fetch behavior và batch execution. Hành vi phụ thuộc Connector/J version và connection properties. Xác minh bằng metrics và test, không dựa trên tên cấu hình của phiên bản driver cũ.

### Partition và index

Kiểm tra partition pruning, index statistics, online DDL behavior và các giới hạn partitioning của phiên bản mới. Query plan có thể thay đổi sau khi optimizer hoặc statistics thay đổi.

## 12. SQL Server: Query Store và compatibility level

SQL Server có thể thay đổi hành vi optimizer theo database compatibility level. Sau khi nâng engine, compatibility level có thể được giữ nguyên hoặc được thay đổi theo kế hoạch nâng cấp. Cần ghi lại giá trị trước/sau và hiểu tác động của việc thay đổi.

### Query Store

Query Store có thể lưu query, plan và runtime statistics theo thời gian. Đây là công cụ quan trọng để phát hiện query/plan regression sau upgrade.

So sánh:

- Query runtime và CPU theo time interval.
- Plan id và plan changes.
- Logical reads, duration và execution count.
- Wait statistics nếu được cấu hình.
- Plan regression theo query quan trọng.

Query Store có thể hỗ trợ force plan trong một số tình huống. Chỉ dùng sau khi xác minh plan cũ còn phù hợp, dữ liệu và index không thay đổi theo cách làm plan đó kém đi. Plan forcing là biện pháp kiểm soát tạm thời hoặc có chủ đích, không thay cho điều tra nguyên nhân.

### Compatibility level và optimizer features

Thay đổi compatibility level có thể bật optimizer behavior mới. Nên thử trên bản sao database và workload đại diện trước khi đổi production. Có thể dùng Query Store để so sánh plan và runtime trước/sau.

### Driver và parameter behavior

Kiểm tra JDBC driver mới có làm thay đổi parameter metadata, prepared execution, SET options hoặc session settings không. Một số SET options có thể ảnh hưởng plan cache key hoặc optimizer behavior. Ghi lại session settings thực tế từ connection của ứng dụng.

## 13. Thiết kế test matrix trước khi cutover

Một test matrix tốt bao gồm nhiều chiều, không chỉ một truy vấn chạy một lần.

| Chiều thử | Ví dụ |
|---|---|
| Query class | OLTP read, write, join, report, batch |
| Parameter distribution | Rare/common, small/large tenant, NULL/non-NULL |
| Cache state | Warm cache, controlled cold cache |
| Concurrency | Single session, normal peak, peak + burst |
| Transaction | Autocommit, multi-statement, rollback, long transaction |
| Result size | 1 row, page-sized, large streaming result |
| Driver behavior | Prepared, batch, fetch size, timeout/cancel |
| Failure | Network reset, failover, server restart theo test plan |
| Background load | Backup, checkpoint, vacuum/analyze, replication |

Không chạy test gây phá hủy trên production. Dữ liệu thử phải được khôi phục hoặc tạo lại có kiểm soát để mỗi lần so sánh có điều kiện tương đương.

### Warm cache và cold cache

- Warm cache phản ánh steady-state khi working set đã được đọc.
- Cold/controlled cache giúp phát hiện phụ thuộc vào cache và storage.

Không thể xóa cache production chỉ để benchmark. Cold-cache test nên chạy trong môi trường riêng hoặc bằng quy trình có kiểm soát.

## 14. Quy trình nâng cấp theo giai đoạn

Một quy trình triển khai an toàn có thể gồm:

1. **Inventory:** ghi phiên bản DBMS, driver, JDK, ORM, pool, extension và cấu hình.
2. **Compatibility review:** đọc release notes, breaking changes và support matrix.
3. **Baseline:** lưu workload, plans, runtime metrics, connection behavior và SLO.
4. **Restore staging:** tạo môi trường thử có data shape và statistics gần production.
5. **Upgrade một thành phần:** thay DBMS hoặc driver theo từng thử nghiệm khi khả thi.
6. **Functional test:** xác minh query, transaction, type mapping và error handling.
7. **Plan regression test:** so sánh plan/runtime cho query quan trọng và nhóm tham số.
8. **Load test:** chạy query mix với concurrency đại diện và burst.
9. **Operational test:** backup/restore, monitoring, failover và rollback.
10. **Canary:** đưa một phần traffic hoặc một nhóm instance vào phiên bản mới.
11. **Observe:** so sánh metrics với nhóm cũ trong cùng thời điểm.
12. **Expand:** tăng dần tỷ lệ traffic khi các chỉ số đạt ngưỡng.
13. **Post-cutover:** theo dõi cache warm-up, plan changes, error, lag và background maintenance.
14. **Close:** ghi kết quả, phiên bản, cấu hình và các ngoại lệ đã chấp nhận.

### Canary cần có đối chứng

Nếu có thể, chạy một phần workload trên nhóm cũ và một phần trên nhóm mới với query mix tương đương. So sánh cùng khoảng thời gian, cùng dữ liệu hoặc dữ liệu tương đương và cùng traffic profile.

Nếu nhóm mới nhận tenant lớn còn nhóm cũ nhận tenant nhỏ, kết quả không có ý nghĩa. Phải cân bằng hoặc phân tầng theo workload/parameter distribution.

## 15. Đặt ngưỡng regression và quyết định dừng

Ngưỡng cần được xác định trước rollout, dựa trên SLO và baseline. Ví dụ minh họa:

- p95 của query quan trọng tăng quá 15% trong ba cửa sổ liên tiếp.
- CPU/request tăng quá 20% ở cùng throughput.
- Logical reads tăng gấp đôi với query fingerprint trọng yếu.
- Error/timeout vượt error budget.
- Replication lag vượt giới hạn vận hành.
- Deadlock hoặc lock wait tăng đáng kể.
- Một truy vấn critical chuyển sang plan có actual rows/loops tăng mạnh.

Các con số phải được thay bằng ngưỡng phù hợp hệ thống. Không dùng một phần trăm chung cho mọi query; query vốn có độ biến thiên cao cần đánh giá bằng nhiều mẫu và percentile.

### Stop condition

Dừng mở rộng rollout khi:

- SLO bị vi phạm.
- Có regression trên giao dịch quan trọng.
- Lỗi dữ liệu hoặc transaction semantics.
- Connection pool, memory hoặc worker saturation tăng.
- Backup/replication/recovery không đáp ứng.
- Không thể xác định nguyên nhân của regression có tác động lớn.

Không chờ hết toàn bộ rollout mới xử lý nếu canary đã cho thấy dấu hiệu rõ.

## 16. Phân tích một plan regression

Giả sử sau nâng cấp, một truy vấn lấy 20 đơn mới nhất theo tenant tăng từ 40 ms lên 900 ms.

### Baseline cũ

- Index seek trên (tenant_id, created_at).
- Actual rows khoảng 20.
- Logical reads thấp.
- Không có sort spill.
- p95 ổn định.

### Sau nâng cấp

- Plan chọn scan trên partition lớn.
- Estimated rows rất thấp nhưng actual rows hàng triệu.
- Sort xử lý nhiều dòng.
- CPU và logical reads tăng.
- Một số tenant lớn chậm hơn nhiều.

### Điều tra

1. So sánh SQL text và parameter types.
2. Kiểm tra index và trạng thái index.
3. So sánh statistics, histogram và row counts.
4. Kiểm tra collation/implicit conversion.
5. Chạy plan với tenant nhỏ và lớn.
6. Xác định plan mới được compile với tham số nào.
7. Kiểm tra optimizer/compatibility setting thay đổi.
8. Đo query trong điều kiện cache tương đương.

### Khắc phục có kiểm chứng

Tùy nguyên nhân có thể:

- Cập nhật statistics nếu thống kê không đại diện.
- Sửa kiểu bind hoặc predicate.
- Tạo/sửa index khi có bằng chứng.
- Dùng parameter-sensitive plan feature phù hợp.
- Tạm thời force plan tốt đã xác minh nếu engine hỗ trợ và có kế hoạch tháo bỏ.
- Điều chỉnh compatibility/optimizer setting theo thử nghiệm.

Sau mỗi thay đổi, chạy lại test matrix. Không ép plan cũ chỉ vì nó từng nhanh; data distribution và workload có thể đã đổi.

## 17. Phân tích driver regression

Giả sử DBMS không thay đổi nhưng sau khi cập nhật JDBC driver, p95 truy vấn tăng và số prepared statement phía server giảm.

Các giả thuyết:

- Driver thay đổi ngưỡng server-side prepare.
- Ứng dụng tạo statement mới ở mỗi lần gọi và không tận dụng cache.
- Bind type khác làm plan không dùng index.
- Fetch behavior chuyển từ cursor sang buffering hoặc ngược lại.
- Batch rewrite bị tắt hoặc không còn áp dụng.
- Connection pool reset session/statement state khác.
- Network timeout hoặc socket behavior thay đổi.

### Cách kiểm tra

1. Ghi driver name/version và connection properties.
2. So sánh SQL fingerprint và parameter metadata.
3. Đo số prepare/execute, server-side prepared statements và round trips.
4. Đo connection acquisition, execute và fetch time riêng.
5. Kiểm tra batch size, update counts và generated keys.
6. Kiểm tra heap, GC và ResultSet buffering.
7. Chạy cùng query set trên driver cũ và mới với cùng DBMS.
8. Kiểm tra error, timeout, cancel và failover.

Nếu driver mới giảm round trip nhưng tăng heap và GC, cần cân nhắc tổng latency và memory budget. Nếu plan thay đổi do bind type, ưu tiên sửa type mapping hoặc cách bind.

## 18. Plan forcing, hints và optimizer setting

Khi regression ảnh hưởng production, có thể cần biện pháp giảm tác động nhanh. Tuy nhiên, hint hoặc force plan có rủi ro dài hạn.

### Khi nào cân nhắc?

- Có plan cũ được xác minh là tốt trên dữ liệu hiện tại.
- Regression có tác động lớn và cần khôi phục SLO.
- Nguyên nhân gốc chưa thể sửa ngay.
- Engine cung cấp cơ chế plan management có thể giám sát và tháo bỏ.

### Rủi ro

- Plan cũ có thể kém khi data distribution thay đổi.
- Hint có thể bị bỏ qua hoặc không tương thích phiên bản.
- Force plan có thể che giấu statistics/index problem.
- Một query parameter group có thể cần plan khác.
- Nâng cấp tiếp theo có thể làm hint hoặc plan forcing không còn hiệu quả.

### Quy trình sử dụng

1. Lưu plan cũ và plan mới.
2. Kiểm tra actual runtime trên nhóm tham số đại diện.
3. Áp dụng trong phạm vi hẹp.
4. Theo dõi latency, CPU, I/O và errors.
5. Đặt thời hạn hoặc điều kiện xem xét lại.
6. Ghi rõ owner và phương án tháo bỏ.
7. Kiểm thử lại sau khi sửa nguyên nhân gốc.

Không dùng global optimizer switch hoặc hint diện rộng để xử lý một query đơn lẻ nếu chưa đo ảnh hưởng workload khác.

## 19. Rollback DBMS và driver

Rollback cần được thiết kế trước khi nâng cấp. Khả năng quay về phụ thuộc loại nâng cấp, định dạng dữ liệu, migration và giao thức.

### Driver rollback

Driver rollback thường dễ hơn DBMS rollback nếu:

- Driver cũ vẫn tương thích với server mới.
- Ứng dụng có thể triển khai lại dependency cũ.
- Connection pool được restart/reset đúng cách.
- Không có thay đổi application code chỉ hoạt động với driver mới.

Giữ artifact, checksum, dependency lock và cấu hình connection properties của phiên bản cũ. Kiểm thử rollback trong staging, bao gồm pool restart và statement cleanup.

### DBMS rollback

Major DBMS upgrade có thể thay đổi data files hoặc catalog khiến server cũ không mở được database. Không giả định có thể chỉ cài lại binary cũ.

Các chiến lược có thể gồm:

- Backup/restore đã kiểm chứng.
- Snapshot/clone phù hợp với consistency của database.
- Blue-green deployment với replication hoặc migration plan.
- Logical migration có thể chuyển traffic về hệ thống cũ trong điều kiện được thiết kế.
- Vendor-supported downgrade path nếu có và được xác nhận.

Phải kiểm tra write divergence sau cutover. Nếu hệ mới đã nhận ghi, quay traffic về hệ cũ có thể mất các transaction mới nếu không có cơ chế đồng bộ ngược.

### Rollback không chỉ là khôi phục binary

Cần xác minh:

- Data compatibility.
- Schema migration.
- Replication topology.
- Connection string và driver.
- Application version.
- Backup chain và recovery point.
- Session/transaction state.
- Monitoring và alerting.

Nếu không thể rollback an toàn, phải có kế hoạch forward-fix hoặc failover đã thử nghiệm.

## 20. Theo dõi sau cutover

Trong giai đoạn đầu sau nâng cấp, theo dõi sát hơn bình thường vì cache, plan cache và background tasks có thể chưa ổn định.

### Theo dõi theo query fingerprint

So sánh:

- Calls và total/average duration.
- CPU/worker time nếu có.
- Logical reads/buffers và rows examined.
- Plan hash/plan id và số plan variant.
- p95/p99 theo query quan trọng.
- Parameter group bị ảnh hưởng.

### Theo dõi hệ thống

- CPU và throttling.
- Active sessions, connection pool pending.
- Lock waits/deadlocks.
- I/O latency và throughput.
- Memory/cache pressure và temp spill.
- Commit/log flush latency.
- Replication lag.
- Backup duration và checkpoint/vacuum.
- Error, timeout và cancellation.

### Phân biệt warm-up với regression

Sau restart, cache lạnh có thể làm physical reads và latency tăng tạm thời. Plan cache mới có thể được tạo dần. Cần theo dõi xu hướng qua nhiều cửa sổ, nhưng không dùng lý do warm-up để bỏ qua regression kéo dài hoặc SLO breach.

## 21. Công cụ quan sát plan theo engine

### PostgreSQL

- pg_stat_statements: query fingerprint, calls, elapsed execution time, rows và buffer counters.
- EXPLAIN (ANALYZE, BUFFERS): plan và runtime cho truy vấn mẫu.
- pg_stat_activity: session, query và wait event.
- pg_stat_io hoặc các view I/O phù hợp phiên bản.
- auto_explain nếu được cấu hình để ghi plan truy vấn chậm.
- Extension chuyên biệt về plan history nếu tổ chức đã triển khai.

pg_stat_statements không phải kho lưu lịch sử plan đầy đủ. Cần lưu plan riêng ở thời điểm baseline và sau upgrade. auto_explain có overhead và có thể ghi SQL/plan chứa thông tin nhạy cảm; cấu hình cẩn trọng.

### MySQL InnoDB

- Performance Schema statement digest: calls, time, rows examined/sent.
- EXPLAIN và EXPLAIN ANALYZE tùy phiên bản.
- Optimizer trace khi cần hiểu quyết định optimizer.
- Slow query log với ngưỡng và chính sách mask phù hợp.
- sys schema và status counters.
- Performance Schema file I/O, waits và prepared statement metrics.

Digest summary giúp xếp hạng query nhưng không thay thế việc lưu execution plan của query đại diện. Kiểm tra reset counters và thời gian instrument.

### SQL Server

- Query Store: query, plan và runtime history.
- Actual execution plan.
- Query Store wait statistics nếu bật.
- DMVs về query stats, waits và file I/O.
- Extended Events cho sự kiện compile, timeout, deadlock và plan-related diagnostics.

Query Store là nguồn hữu ích để so sánh plan trước/sau nâng cấp. Cần xác nhận capture mode, retention, storage quota và trạng thái Query Store trước khi dùng làm bằng chứng.

## 22. Kiểm tra tính đúng và tương thích chức năng

Performance test chỉ có ý nghĩa khi kết quả vẫn đúng.

Kiểm thử:

- Giá trị NULL và type conversion.
- Decimal precision/scale.
- Date/time và timezone.
- Unicode/collation/case sensitivity.
- Generated keys và batch update counts.
- Transaction commit/rollback.
- Isolation level và locking.
- Stored procedure, function và trigger.
- Pagination/order stability.
- Error code, SQLState và exception mapping.
- Query cancellation và timeout.
- Failover và reconnect.

Một driver có thể trả kết quả đúng cho SELECT đơn giản nhưng thay đổi hành vi ở batch, cursor hoặc transaction. Phải kiểm tra cả các luồng ứng dụng thực tế.

### So sánh kết quả

Với query read, so sánh row count, key set và giá trị theo test data. Với query write, kiểm tra state sau commit/rollback và tính idempotent. Với query không có ORDER BY, không giả định thứ tự dòng giữa hai plan giống nhau.

## 23. Runbook xử lý plan regression sau nâng cấp

Khi phát hiện query quan trọng chậm hơn:

1. Xác nhận thời điểm regression và phiên bản vừa thay đổi.
2. Xác định query fingerprint, tenant và parameter group.
3. So sánh baseline/canary ở cùng workload.
4. Thu execution plan cũ và mới.
5. So sánh actual rows, loops, access path, join, sort/hash và spill.
6. Kiểm tra statistics, index, type binding và session settings.
7. Phân biệt CPU, I/O, lock, memory và network waits.
8. Kiểm tra plan cache, prepare mode và parameter sensitivity.
9. Xác định biện pháp giảm tác động có phạm vi nhỏ.
10. Thử thay đổi trong staging/canary.
11. Đo lại query và workload tổng thể.
12. Mở rộng fix khi đạt ngưỡng; rollback khi vượt stop condition.
13. Ghi root cause, phiên bản, plan id và điều kiện tái hiện.

Không xóa toàn bộ plan cache hoặc restart database như phản ứng mặc định. Việc đó có thể làm toàn bộ hệ thống compile lại và tạo đợt CPU spike mới. Chỉ thao tác cache theo hướng dẫn engine và với giả thuyết rõ ràng.

## 24. Những sai lầm thường gặp

- **Nâng DBMS và driver cùng lúc:** khó xác định nguồn regression.
- **Chỉ kiểm tra kết nối:** không chứng minh plan và runtime tương thích.
- **Không lưu baseline:** mất điểm tham chiếu để so sánh.
- **Chỉ chạy một query mẫu:** bỏ qua parameter skew và workload mix.
- **So sánh optimizer cost giữa hai phiên bản như thời gian thực:** cost unit có thể thay đổi.
- **Coi plan hash khác là regression:** plan mới có thể nhanh hơn.
- **Coi plan hash giống là không regression:** runtime vẫn đổi do data/cache/resource.
- **Chạy analyze toàn bộ ngay sau upgrade mà không thử:** statistics mới có thể đổi plan diện rộng.
- **Flush plan cache để chữa chậm:** có thể gây compile storm.
- **Force plan cũ vô thời hạn:** plan có thể không còn phù hợp với dữ liệu mới.
- **Bỏ qua parameter type:** implicit conversion có thể làm mất index access.
- **Không kiểm tra driver batch/fetch:** round trip, heap và transaction behavior có thể đổi.
- **So sánh warm cache với cold cache:** kết quả không tương đương.
- **Không kiểm tra backup/restore và failover:** upgrade có thể qua smoke test nhưng thất bại vận hành.
- **Không chuẩn bị rollback:** major upgrade có thể không downgrade trực tiếp được.
- **Không kiểm tra kết quả dữ liệu:** hiệu năng tốt hơn nhưng semantics sai vẫn là thất bại.
- **Không theo dõi sau cutover:** regression có thể chỉ xuất hiện khi cache, batch hoặc traffic đạt mức thực.

## 25. Checklist trước, trong và sau nâng cấp

### Trước nâng cấp

- Ghi đầy đủ DBMS, driver, JDK, ORM, pool và extension versions.
- Xác nhận support matrix và release notes.
- Ghi cấu hình, schema, index, statistics và compatibility settings.
- Lưu baseline query fingerprint, execution plan và runtime.
- Chọn query đại diện và parameter groups.
- Chuẩn bị dataset có data skew và quy mô phù hợp.
- Kiểm thử functional, performance và operational compatibility.
- Chuẩn bị backup/restore và rollback đã thử nghiệm.
- Định nghĩa SLO, regression threshold và stop condition.

### Trong nâng cấp

- Thực hiện theo từng thành phần và từng giai đoạn.
- Ghi timestamp và phiên bản chính xác.
- Kiểm tra connection, authentication, TLS và session settings.
- Kiểm tra prepare/bind, batch, fetch, timeout và cancel.
- Theo dõi CPU, query latency, plan changes, pool và replication.
- Dừng rollout nếu canary vượt ngưỡng.

### Sau nâng cấp

- Thu lại plan và metrics cùng điều kiện baseline.
- Kiểm tra query theo parameter group.
- Xác nhận statistics và plan cache behavior.
- Theo dõi warm-up, background maintenance và replication.
- Kiểm thử backup/restore/failover.
- Kiểm tra dữ liệu và transaction semantics.
- Ghi regression, mitigation, plan forcing nếu có và thời hạn xem xét.
- Cập nhật runbook, dashboard và inventory.

## Kết luận

Nâng cấp DBMS hoặc JDBC driver là thay đổi có thể ảnh hưởng đến optimizer, execution plan, kiểu bind, prepare, batch, fetch và transaction behavior. Một kết nối thành công hoặc một smoke test đơn giản chưa đủ chứng minh hiệu năng được giữ nguyên. Cần có baseline, query suite đại diện, parameter groups, plan comparison và load test trong điều kiện tương đương.

Khi phát hiện regression, hãy xác định nó nằm ở execution, planning, statistics, parameter sensitivity, driver behavior hay môi trường. Dùng plan và runtime metrics để chứng minh nguyên nhân, áp dụng biện pháp có phạm vi nhỏ, triển khai theo canary và giữ rollback đã kiểm chứng. Vận hành nâng cấp tốt là vận hành có thể đo được thay đổi, phát hiện sớm tác động và giữ SLO cùng tính đúng của dữ liệu trong toàn bộ quá trình.
