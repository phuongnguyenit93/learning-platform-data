# Tập dữ liệu hoạt động, tỷ lệ trúng bộ đệm và giới hạn suy luận

## Vì sao cần hiểu working set và cache hit ratio?

Một hệ quản trị cơ sở dữ liệu thường không đọc dữ liệu trực tiếp từ thiết bị lưu trữ cho mỗi lần truy vấn. Nó giữ các trang dữ liệu và chỉ mục được sử dụng trong bộ nhớ để những lần truy cập tiếp theo có thể được phục vụ nhanh hơn. Tập trang thường xuyên được workload truy cập được gọi là working set (tập dữ liệu hoạt động). Nếu working set phù hợp với dung lượng cache hữu dụng và được giữ lại đủ lâu, nhiều yêu cầu đọc có thể được phục vụ từ bộ nhớ. Nếu working set lớn hơn cache, hoặc workload liên tục thay đổi vùng dữ liệu truy cập, trang cần thiết có thể bị đẩy ra trước khi được dùng lại.

Cache hit ratio (tỷ lệ trúng bộ đệm) là một chỉ số thường dùng để mô tả tỷ lệ yêu cầu đọc được phục vụ từ một tầng cache. Chỉ số này hữu ích khi được xác định đúng mẫu số, đúng tầng cache và đúng khoảng thời gian. Tuy nhiên, một tỷ lệ hit cao không tự chứng minh cơ sở dữ liệu đang nhanh; tỷ lệ thấp cũng không luôn đồng nghĩa với vấn đề. Một workload quét tuần tự hàng triệu trang có thể có hit ratio thấp nhưng vẫn đạt thông lượng tốt, trong khi workload có hit ratio 99,9% vẫn có thể chậm vì số lượng yêu cầu rất lớn, trang nóng bị tranh chấp hoặc các lần cache miss có độ trễ cao.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần kết hợp working set và cache hit ratio với kế hoạch thực thi, số trang đọc, I/O latency, CPU, bộ nhớ, concurrency và đặc điểm truy cập. Mục tiêu là xác định dữ liệu nào thực sự cần nằm trong bộ nhớ, tầng cache nào đang phục vụ yêu cầu, và cache miss có ảnh hưởng đáng kể đến độ trễ hay throughput hay không.

Bài học này trình bày cách hình thành working set, đo hit/miss, hiểu các tầng cache, nhận diện cache churn và scan pollution, so sánh số liệu giữa các hệ quản trị, đồng thời chỉ ra giới hạn của việc suy luận từ một tỷ lệ tổng hợp.

## Các tầng cache trong đường đọc dữ liệu

### Buffer pool hoặc shared buffer của hệ quản trị

Hầu hết hệ quản trị quan hệ duy trì vùng bộ nhớ riêng để lưu các trang dữ liệu và chỉ mục. Tên gọi khác nhau theo sản phẩm:

- SQL Server sử dụng buffer pool để giữ các data page và index page.
- PostgreSQL sử dụng shared buffers cho các block được quản lý trong vùng bộ nhớ dùng chung.
- MySQL/InnoDB sử dụng InnoDB buffer pool để lưu data page, index page và một số cấu trúc liên quan.

Khi truy vấn cần một trang, hệ quản trị kiểm tra trang có sẵn trong buffer pool hay không. Nếu có, yêu cầu có thể được phục vụ từ bộ nhớ của database engine. Nếu không, engine phải yêu cầu đọc từ tầng thấp hơn rồi đưa trang vào vùng đệm theo chính sách quản lý cache.

Đây là tầng cache quan trọng đối với hiệu năng truy cập dữ liệu, nhưng không phải tầng cache duy nhất. Việc một trang không có trong buffer pool không chứng minh thiết bị vật lý phải đọc đĩa; hệ điều hành hoặc cache của thiết bị có thể đã giữ dữ liệu.

### Cache của hệ điều hành

Một số hệ quản trị dựa nhiều vào cache của hệ điều hành; một số cấu hình hoặc đường I/O có thể bypass hoặc hạn chế page cache của hệ điều hành. PostgreSQL thường đọc file thông qua hệ điều hành, vì vậy một block không có trong shared buffers vẫn có thể được phục vụ từ OS page cache.

Do đó, thống kê block read ở tầng database không nhất thiết tương đương một lần đọc vật lý từ ổ đĩa. Nó có thể chỉ có nghĩa database engine phải yêu cầu tầng hệ điều hành cung cấp block.

Khi phân tích, cần biết engine đang dùng buffered I/O, direct I/O hay cơ chế tương đương. Không so sánh một chỉ số buffer read của database với số physical disk read của hệ điều hành như thể chúng có cùng định nghĩa.

### Cache của thiết bị và tầng lưu trữ

SSD, controller, storage array, hypervisor và dịch vụ lưu trữ cloud có thể có cache riêng. Một yêu cầu đọc đi xuống tầng này có thể được đáp ứng từ cache của thiết bị hoặc vùng cache phân tán mà hệ điều hành không quan sát trực tiếp.

Các tầng này ảnh hưởng latency và throughput, nhưng số liệu cache hit có thể không được database engine nhìn thấy. Khi database báo một lần physical read, thời gian thực tế vẫn có thể thấp nếu thiết bị hoặc tầng lưu trữ có cache nóng. Ngược lại, một lần đọc có thể chậm khi hàng đợi thiết bị cao dù dữ liệu có trong cache tầng thấp.

### Cache ở ứng dụng

Ứng dụng có thể cache kết quả truy vấn, đối tượng, metadata hoặc dữ liệu tham chiếu. Cache ứng dụng có thể giảm số truy vấn đến database, nhưng tạo thêm yêu cầu về invalidation, TTL, nhất quán và cập nhật sau ghi.

Không gộp cache ứng dụng với buffer pool khi tính cache hit ratio. Một request được phục vụ từ Redis hoặc local memory không đi qua database buffer pool; hai chỉ số đo hai tầng khác nhau.

### Đường đi khái quát

~~~mermaid
flowchart TD
    A[Ứng dụng gửi truy vấn] --> B[Database engine yêu cầu trang]
    B --> C{Trang có trong buffer pool?}
    C -->|Có| D[Phục vụ từ bộ nhớ database]
    C -->|Không| E[Đọc từ tầng hệ điều hành hoặc I/O]
    E --> F{Tầng dưới có cache?}
    F -->|Có| G[Phục vụ từ OS hoặc storage cache]
    F -->|Không| H[Đọc từ thiết bị lưu trữ]
    G --> I[Đưa trang vào buffer pool]
    H --> I
    I --> D
    D --> J[Thực thi phép lọc và trả kết quả]
~~~

Sơ đồ chỉ mô tả đường đọc đơn giản. Một số hệ quản trị dùng direct I/O, asynchronous I/O, read-ahead, parallel read hoặc các tầng cache riêng. Truy vấn cũng có thể đọc nhiều trang và đi qua nhiều đường khác nhau trong cùng một lần thực thi.

## Working set là gì?

### Tập dữ liệu được workload sử dụng trong một khoảng thời gian

Working set là tập trang hoặc dữ liệu được một workload truy cập thường xuyên trong khoảng thời gian quan sát. Nó không nhất thiết bằng toàn bộ kích thước database. Một database có dung lượng 5 TB có thể có working set đọc nóng chỉ vài chục GB nếu phần lớn truy vấn tập trung vào dữ liệu gần đây và một số bảng tham chiếu. Ngược lại, một workload phân tích quét rộng có thể cần truy cập một phần rất lớn dữ liệu trong thời gian ngắn.

Working set phụ thuộc vào:

- Tập truy vấn thực tế và tần suất từng truy vấn.
- Phân bố khóa và độ lệch dữ liệu (skew).
- Thời gian nhìn lại của workload, chẳng hạn vài phút, một giờ hoặc một ngày.
- Mức độ tái sử dụng trang theo thời gian.
- Kích thước trang và số trang được truy cập.
- Tỷ lệ đọc/ghi và cách engine xử lý dirty page.
- Mức concurrency và sự cạnh tranh giữa các workload.
- Các tác vụ nền như backup, vacuum, checkpoint, index maintenance hoặc báo cáo.

Vì vậy, working set không phải một con số bất biến. Nó thay đổi theo giờ cao điểm, ngày trong tuần, mùa vụ, batch job và thay đổi của ứng dụng.

### Working set của dữ liệu và working set của chỉ mục

Một truy vấn có thể đọc nhiều trang chỉ mục nhưng chỉ lấy một số ít trang dữ liệu. Một workload khác có thể quét bảng lớn mà gần như không dùng chỉ mục. Do đó, nên xem xét riêng:

- Trang của bảng hoặc heap.
- Trang của clustered index hoặc cấu trúc lưu trữ chính.
- Trang của secondary index.
- Trang metadata và cấu trúc nội bộ có liên quan.
- Trang tạm hoặc dữ liệu trung gian khi truy vấn sort/hash.

Một chỉ mục nhỏ và nóng có thể chiếm phần đáng kể working set. Nếu thêm nhiều chỉ mục không cần thiết, chúng có thể cạnh tranh buffer pool với trang dữ liệu và chỉ mục quan trọng. Chỉ mục giúp giảm số hàng phải đọc nhưng cũng tiêu thụ bộ nhớ cache và tăng chi phí ghi.

### Working set theo thời gian

Một cách nhìn hữu ích là theo dõi số trang duy nhất được truy cập trong các cửa sổ thời gian khác nhau. Ví dụ:

- Trong 1 phút: các trang đang được truy cập liên tục.
- Trong 15 phút: vùng dữ liệu phục vụ workload ngắn hạn.
- Trong 1 giờ: tập trang thường dùng trong giờ làm việc.
- Trong 24 giờ: bao gồm cả báo cáo định kỳ và tác vụ nền.

Cửa sổ quá ngắn có thể bỏ sót truy vấn theo chu kỳ. Cửa sổ quá dài có thể gộp dữ liệu lạnh và nóng thành một tập lớn, làm khó xác định dung lượng cache hữu dụng.

Nếu có tracing hoặc telemetry theo page access, có thể ước lượng working set theo cửa sổ. Nếu không, hãy dùng các chỉ số gián tiếp như buffer residency, page reads, query fingerprint, tần suất truy cập bảng/chỉ mục và mức độ tái sử dụng.

### Working set không đồng nghĩa với dung lượng database

Không nên yêu cầu RAM bằng tổng dung lượng database. Một database lớn có thể hoạt động tốt nếu workload có locality cao và working set nhỏ. Một database nhỏ cũng có thể gây I/O nhiều nếu workload truy cập ngẫu nhiên liên tục và cache bị cạnh tranh.

Ngược lại, chỉ dựa vào working set ước lượng để quyết định RAM cũng chưa đủ. Hệ quản trị còn cần bộ nhớ cho connection, sort, hash join, aggregation, plan cache, lock, background tasks và hệ điều hành. Phải tính tổng ngân sách bộ nhớ và mức sử dụng đồng thời.

## Cache hit ratio và cách tính

### Công thức cơ bản

Ở mức khái niệm, nếu một tầng cache ghi nhận số yêu cầu đọc trang được phục vụ từ cache là hits và số yêu cầu không tìm thấy trang trong cache là misses, có thể tính:

~~~text
hit_ratio = hits / (hits + misses)
miss_ratio = misses / (hits + misses)
~~~

Ví dụ, trong một khoảng đo có 9.900.000 cache hits và 100.000 misses:

~~~text
hit_ratio = 9.900.000 / 10.000.000 = 99%
miss_ratio = 1%
~~~

Tỷ lệ 99% nghe có vẻ cao, nhưng 100.000 misses trong khoảng đo vẫn có thể tạo I/O đáng kể. Nếu mỗi miss cần đọc một trang 8 KB, tổng dữ liệu yêu cầu ở tầng dưới có thể vào khoảng 800 MB trước khi tính read-ahead, cache tầng thấp, nén và các yếu tố khác. Nếu các lần miss có latency cao hoặc xảy ra trên critical path của truy vấn, chúng có thể chi phối p95/p99.

### Tỷ lệ phải gắn với tầng cache

Cần nêu rõ hit ratio đang đo ở đâu:

- Database buffer pool hit ratio.
- OS page cache hit ratio.
- Storage cache hit ratio.
- Application cache hit ratio.
- Cache hit của một dịch vụ phân tán.

Một tỷ lệ hit 99% ở application cache không thể so trực tiếp với 99% ở database buffer pool. Mỗi tầng có tập yêu cầu, kích thước đơn vị, cơ chế eviction và cách đo khác nhau.

### Tỷ lệ phải gắn với khoảng thời gian

Một counter tích lũy từ lúc database khởi động có thể che giấu vấn đề mới xuất hiện. Ví dụ, hệ thống đã chạy nhiều tuần với cache nóng, sau đó một báo cáo nặng làm cache churn trong 10 phút. Tỷ lệ tích lũy vẫn có thể rất cao vì lịch sử trước đó chiếm phần lớn mẫu số.

Khi chẩn đoán, nên tính delta counter trong một khoảng đo xác định:

~~~text
hits_delta = hits_end - hits_start
misses_delta = misses_end - misses_start

interval_hit_ratio =
    hits_delta / (hits_delta + misses_delta)
~~~

Ghi rõ thời điểm bắt đầu/kết thúc, workload đang chạy và việc counter có bị reset do restart hoặc failover không. Nếu counter reset, phép trừ đơn giản sẽ cho kết quả sai.

### Hit ratio không cho biết mức độ nghiêm trọng của miss

Hai workload cùng hit ratio 99% có thể có chi phí rất khác:

| Workload | Hits | Misses | Hit ratio | Nhận xét |
|---|---:|---:|---:|---|
| A | 99.000 | 1.000 | 99% | Chỉ 1.000 misses trong khoảng đo |
| B | 99.000.000 | 1.000.000 | 99% | Một triệu misses có thể tạo I/O lớn |
| C | 9.900 | 100 | 99% | Ít misses, nhưng mỗi miss có thể rất chậm |
| D | 99.900.000 | 100.000 | 99,9% | Tỷ lệ cao hơn nhưng vẫn cần xét tổng lượng đọc |

Cần xem thêm số misses tuyệt đối, byte đọc, IOPS, latency, queue depth, số truy vấn bị ảnh hưởng và độ trễ của từng truy vấn.

### Không phải mọi cache miss đều là đọc vật lý từ thiết bị

Một miss ở database buffer pool có thể được OS page cache phục vụ. Một lần đọc từ database có thể được storage cache đáp ứng. Vì vậy, không lấy buffer miss nhân với kích thước trang rồi khẳng định đó là lượng đọc vật lý trên đĩa.

Để xác định I/O thực tế, đối chiếu số liệu ở nhiều tầng: database read counters, OS disk I/O, storage latency và công cụ giám sát hạ tầng. Hãy hiểu định nghĩa của từng bộ đếm trước khi cộng hoặc so sánh.

## Đo working set và cache theo hệ quản trị

### PostgreSQL

PostgreSQL sử dụng shared_buffers để cache các block trong database engine và thường còn được hưởng lợi từ OS page cache. Các view thống kê có thể cung cấp số block được tìm thấy trong shared buffers và số block cần đọc từ tầng hệ điều hành.

Các nguồn thường dùng gồm:

- pg_stat_database: các bộ đếm block hit/read theo database.
- pg_statio_user_tables và pg_statio_user_indexes: thống kê I/O theo bảng và chỉ mục.
- pg_stat_io ở các phiên bản hỗ trợ: thống kê I/O theo loại backend/object/context.
- pg_buffercache extension: quan sát các block hiện đang nằm trong shared buffers nếu extension được cài và quyền cho phép.
- Wait events và OS metrics: bổ sung thời gian chờ và I/O thực tế.

Ví dụ truy vấn tổng hợp ở cấp database:

~~~sql
SELECT
    datname,
    blks_hit,
    blks_read,
    ROUND(
        100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0),
        2
    ) AS shared_buffer_hit_pct
FROM pg_stat_database
WHERE datname = current_database();
~~~

Chỉ số trên phản ánh tỷ lệ block hit so với block read được thống kê ở tầng database/shared buffers theo định nghĩa của PostgreSQL. blks_read không nhất thiết là lần đọc vật lý từ thiết bị vì OS page cache có thể đáp ứng. Đây cũng là counter tích lũy; để đánh giá một khoảng đo, cần lấy hai snapshot và tính delta.

Nếu cần biết trang nào đang chiếm shared buffers, pg_buffercache có thể cung cấp ảnh chụp trạng thái tại thời điểm truy vấn. Đây không phải lịch sử truy cập hoàn chỉnh và việc quét thông tin cache cũng có chi phí. Không cài extension hoặc chạy truy vấn giám sát nặng trên production nếu chưa theo quy trình vận hành.

### SQL Server

SQL Server sử dụng buffer pool để cache data page và index page. Có thể xem các bộ đếm hiệu năng, DMV và execution plan để đánh giá buffer cache, page reads, memory pressure và các truy vấn tạo nhiều logical reads.

Các nguồn thường dùng:

- Performance counters như Buffer Manager và Memory Manager.
- sys.dm_os_performance_counters để đọc các bộ đếm engine.
- sys.dm_os_buffer_descriptors để quan sát page hiện có trong buffer pool theo database/file/object khi có quyền phù hợp.
- sys.dm_exec_query_stats và plan cache để tìm truy vấn có nhiều logical reads.
- Wait statistics để phân biệt chờ I/O với các loại chờ khác.

SQL Server có counter Buffer cache hit ratio. Counter này thường được diễn giải cùng Buffer cache hit ratio base và khoảng lấy mẫu; giá trị tích lũy hoặc một snapshot đơn lẻ không đủ để kết luận về workload hiện tại. Cần xem số liệu theo thời gian và đối chiếu với page reads, physical reads, page life expectancy, memory grants và wait events.

Page life expectancy không phải thời gian sống cố định của mọi trang và không nên dùng một ngưỡng phổ quát cho mọi máy. Giá trị giảm nhanh có thể là dấu hiệu memory pressure hoặc workload scan lớn, nhưng phải xem NUMA node, kích thước bộ nhớ, workload và các counter liên quan.

### MySQL/InnoDB

InnoDB buffer pool cache data page và index page. Một số bộ đếm hữu ích:

- Innodb_buffer_pool_read_requests: yêu cầu đọc logic từ buffer pool.
- Innodb_buffer_pool_reads: số lần InnoDB phải đọc page từ đĩa theo định nghĩa bộ đếm.
- Innodb_buffer_pool_read_ahead và các bộ đếm liên quan: hoạt động đọc trước.
- Buffer pool pages data/free/dirty: trạng thái sử dụng vùng đệm.
- Performance Schema: hỗ trợ quan sát I/O và hoạt động của các đối tượng.

Có thể xem nhanh một số status variables:

~~~sql
SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read%';
~~~

Một tỷ lệ tham khảo có thể được ước lượng từ delta read_requests và reads:

~~~text
estimated_hit_ratio =
    1 - (delta_Innodb_buffer_pool_reads /
         delta_Innodb_buffer_pool_read_requests)
~~~

Đây là cách ước lượng dựa trên các counter nêu trên, không phải định nghĩa duy nhất cho mọi phiên bản hoặc mọi mục đích giám sát. Hãy lấy delta trong cùng khoảng thời gian, kiểm tra counter reset và đọc tài liệu phiên bản đang chạy. InnoDB có read-ahead, eviction và nhiều đường đọc khác nên không diễn giải từng counter như một lần I/O vật lý độc lập nếu chưa hiểu semantics.

### Không so sánh trực tiếp các hệ quản trị

PostgreSQL, SQL Server và MySQL có kiến trúc cache, kích thước page, cách đếm request, cách sử dụng OS cache và tên counter khác nhau. Một tỷ lệ 99% ở sản phẩm này không nhất thiết tương đương 99% ở sản phẩm khác.

Khi so sánh, hãy chuẩn hóa câu hỏi thay vì chỉ so con số:

- Bao nhiêu trang được yêu cầu trong cùng một khoảng thời gian?
- Bao nhiêu lần yêu cầu không được phục vụ từ buffer pool?
- Bao nhiêu byte hoặc I/O request thực sự đi xuống storage?
- I/O latency p50/p95/p99 là bao nhiêu?
- Truy vấn nào tạo miss và chúng ảnh hưởng đến SLO nào?
- Có cache ở OS hoặc storage đang đáp ứng các miss không?

## Dấu hiệu working set không phù hợp với cache

### Cache churn

Cache churn xảy ra khi các trang liên tục được nạp và đẩy ra do vùng đệm không giữ được tập trang được tái sử dụng. Dấu hiệu có thể gồm:

- Buffer misses hoặc page reads tăng liên tục.
- Cùng một nhóm bảng/chỉ mục bị đọc lại nhiều lần.
- Hit ratio giảm trong giờ cao điểm hoặc khi chạy batch.
- I/O latency và queue depth tăng cùng thời điểm.
- Truy vấn vốn nhanh khi cache nóng chậm lại sau workload khác.
- Page eviction tăng hoặc các chỉ số memory pressure thay đổi.

Để xác nhận churn, cần biết trang nào được tái sử dụng và trang nào bị đẩy ra. Một snapshot cache không đủ để chứng minh trang bị eviction liên tục. Có thể kết hợp tracing, query stats, page access telemetry, OS metrics và so sánh theo khoảng thời gian.

### Scan pollution

Một truy vấn quét tuần tự bảng lớn có thể đưa nhiều trang ít được tái sử dụng vào buffer pool, đẩy các trang nóng của OLTP ra ngoài. Đây thường được gọi là scan pollution hoặc cache pollution.

Một số engine có chiến lược quản lý cache để giảm ảnh hưởng của scan dài, nhưng hành vi khác nhau. Cần kiểm tra loại scan, kích thước dữ liệu, tần suất batch và các trang nóng bị ảnh hưởng.

Biện pháp có thể gồm:

- Lọc dữ liệu sớm để giảm phạm vi scan.
- Dùng chỉ mục phù hợp nếu điều kiện chọn lọc đủ cao.
- Chạy báo cáo nặng trên replica hoặc hệ thống phân tích riêng khi phù hợp.
- Lên lịch batch tránh giờ OLTP cao điểm.
- Dùng partition pruning để tránh đọc phân vùng không cần.
- Tối ưu projection để giảm độ rộng hàng và lượng dữ liệu đọc.
- Đo lại cache churn và độ trễ OLTP sau điều chỉnh.

Không phải scan nào cũng xấu. Nếu truy vấn cần phần lớn bảng, sequential scan có thể rẻ hơn nhiều lookup rời rạc. Cần đánh giá tổng workload và ảnh hưởng đến cache nóng.

### Working set lớn hơn cache hữu dụng

Nếu workload thường xuyên truy cập tập trang lớn hơn nhiều so với cache hữu dụng, cache miss có thể xảy ra liên tục. Tuy nhiên, tăng RAM chỉ có lợi khi:

- Database engine có thể sử dụng phần bộ nhớ tăng thêm.
- Máy chủ không bị giới hạn bởi memory cap hoặc cấu hình container.
- Bộ nhớ không bị các sort/hash/connection chiếm hết.
- Tầng lưu trữ hoặc CPU chưa phải nút thắt chi phối.
- Workload có locality đủ để cache lớn hơn giữ được trang sẽ được tái sử dụng.

Nếu truy vấn chỉ đọc mỗi trang một lần theo kiểu streaming, tăng buffer pool có thể không làm hit ratio tăng đáng kể. Nếu dữ liệu nóng tập trung và được tái sử dụng nhiều, tăng cache có thể giảm I/O rõ rệt.

### Hot set và skew

Một số tenant, khách hàng hoặc sản phẩm có thể được truy cập thường xuyên hơn phần còn lại. Working set của nhóm nóng có thể nhỏ nhưng tần suất truy cập rất cao. Nếu cache eviction không ưu tiên đúng trang nóng hoặc nhiều workload cạnh tranh, trang quan trọng có thể bị đẩy ra.

Hãy đo phân bố theo query, tenant, bảng, index và khoảng thời gian. Không chỉ xem hit ratio tổng của cả database; một nhóm truy vấn quan trọng có thể bị cache miss nhiều trong khi các truy vấn khác có hit ratio rất cao.

## Giới hạn suy luận từ cache hit ratio

### Một tỷ lệ cao không chứng minh truy vấn nhanh

Hit ratio chỉ mô tả một phần đường đọc. Truy vấn có thể vẫn chậm vì:

- CPU tiêu tốn nhiều cho join, sort, expression hoặc aggregation.
- Logical reads quá lớn dù tất cả trang đều ở buffer pool.
- Lock wait hoặc latch contention.
- Memory grant thiếu và sort/hash spill ra đĩa tạm.
- Kết quả quá lớn, truyền mạng chậm hoặc ứng dụng xử lý chậm.
- Nhiều request đồng thời tranh chấp cùng buffer/page hoặc CPU.
- I/O ghi, checkpoint, WAL flush hoặc replication là nút thắt thay vì đọc.
- Một vài cache miss có độ trễ rất cao nằm trên critical path.

Một truy vấn có hit ratio 100% vẫn có thể đọc hàng triệu trang từ buffer pool. Đọc bộ nhớ nhanh hơn storage nhưng không miễn phí; CPU và băng thông bộ nhớ vẫn bị tiêu thụ.

### Một tỷ lệ thấp không nhất thiết là sự cố

Cache hit ratio thấp có thể xuất hiện trong các tình huống hợp lý:

- Quét tuần tự một bảng lớn chỉ một lần.
- Workload phân tích đọc dữ liệu lạnh theo batch.
- Database mới khởi động và cache chưa ấm.
- Dữ liệu tăng nhanh khiến working set thay đổi.
- Truy vấn chỉ chạy một lần nên không có tái sử dụng.
- Hệ thống sử dụng OS cache hoặc storage cache ngoài buffer pool.

Nếu scan có thông lượng cao, I/O latency thấp và không ảnh hưởng workload quan trọng, tỷ lệ thấp có thể chấp nhận được. Mục tiêu không phải ép mọi truy vấn đạt 100% hit ratio.

### Tỷ lệ tổng hợp che giấu truy vấn quan trọng

Giả sử 99% số request thuộc một workload tham chiếu nhỏ có hit ratio 99,99%, trong khi 1% truy vấn báo cáo quan trọng có hit ratio 50% và thời gian chạy rất dài. Hit ratio tổng có thể vẫn rất cao nhưng người dùng báo cáo vẫn gặp độ trễ lớn.

Hãy phân tích theo:

- Query fingerprint hoặc nhóm truy vấn.
- Database, schema, table và index.
- Tenant hoặc nhóm dữ liệu.
- Khoảng thời gian và giờ cao điểm.
- Loại workload: OLTP, reporting, batch.
- Độ trễ p50/p95/p99 và số request bị ảnh hưởng.

Không suy ra trải nghiệm của một API từ tỷ lệ cache tổng toàn database.

### Counter tích lũy che giấu biến động

Một counter tích lũy kể từ lúc khởi động có thể làm mờ sự cố ngắn hạn. Nếu hệ thống chạy tốt 10 ngày rồi có 30 phút cache churn, tỷ lệ tổng vẫn có thể gần như không đổi. Dùng delta theo khoảng đo và biểu đồ thời gian để tìm tương quan với deploy, batch job, backup hoặc giờ cao điểm.

### Hit ratio không đo dung lượng working set

Một tỷ lệ hit cao không cho biết chính xác working set là bao nhiêu GB. Muốn ước lượng working set cần biết tập trang duy nhất, tần suất tái sử dụng, thời gian tái sử dụng và mức độ cạnh tranh. Cache hit ratio là tỷ lệ yêu cầu, không phải tỷ lệ dung lượng.

Một trang được truy cập hàng triệu lần có thể làm hit ratio tăng mạnh dù hàng triệu trang khác chỉ được đọc một lần. Vì vậy, không nhân hit ratio với tổng dung lượng database để ước lượng working set.

## Phương pháp đo working set trong thực tế

### Bước 1: xác định workload và cửa sổ đo

Chia workload thành các nhóm có hành vi tương đối giống nhau: giao dịch trực tuyến, báo cáo, batch, backup hoặc truy vấn quản trị. Ghi lại giờ cao điểm, chu kỳ hàng ngày/tuần và các sự kiện đặc biệt.

Chọn cửa sổ đo đủ dài để bao phủ hành vi tái sử dụng nhưng đủ ngắn để nhìn thấy biến động. Có thể bắt đầu với các khoảng 5 phút, 15 phút, 1 giờ và 24 giờ, sau đó điều chỉnh theo workload.

### Bước 2: lấy delta counter

Ghi counter đầu và cuối của cùng khoảng đo. Tính delta hits, misses, reads, bytes và latency nếu có. Kiểm tra restart, failover, counter reset và đơn vị đo.

Không lấy một giá trị tổng từ lúc khởi động rồi so với một workload mới mà không chuẩn hóa thời gian hoạt động.

### Bước 3: đo số lượng và chi phí miss

Ghi cả số miss tuyệt đối và lượng dữ liệu đọc. Một miss có thể đọc một page, nhiều page do read-ahead hoặc một request lớn. Cần xem I/O requests, bytes, average latency và tail latency.

Ưu tiên truy vấn hoặc nhóm truy vấn tạo nhiều misses trên critical path. Có thể một truy vấn có số miss nhỏ nhưng latency rất cao vì chờ thiết bị hoặc queue.

### Bước 4: xác định nguồn tạo áp lực cache

Đối chiếu thời điểm hit ratio giảm với:

- Query fingerprint mới hoặc truy vấn chạy thường xuyên hơn.
- Table scan hoặc index scan lớn.
- Batch/reporting job.
- Index rebuild, vacuum, checkpoint hoặc backup.
- Thay đổi tham số, plan regression hoặc deploy.
- Tăng số connection và concurrency.
- Thay đổi kích thước dữ liệu hoặc phân bố tenant.

Nếu một báo cáo lớn trùng với cache churn, kiểm tra số trang đọc và ảnh hưởng đến các truy vấn OLTP trước khi tăng RAM.

### Bước 5: ước lượng working set và tái sử dụng

Nếu có telemetry theo page hoặc object, xác định tập trang duy nhất được truy cập trong cửa sổ và tần suất lặp. Nếu không có page-level tracing, dùng thống kê theo bảng/index, query stats, cache residency snapshot và số lần đọc để ước lượng.

Phân biệt:
- Dữ liệu được truy cập thường xuyên và có reuse.
- Dữ liệu được quét một lần.
- Dữ liệu nóng theo thời điểm.
- Dữ liệu lạnh hoặc archive.
- Dữ liệu của tenant lớn hoặc nhóm truy vấn đặc biệt.

Ước lượng working set nên được trình bày như một khoảng hoặc phân bố theo thời gian, không phải một con số chính xác tuyệt đối nếu telemetry không đầy đủ.

### Bước 6: thay đổi một yếu tố và đo lại

Có thể thử giảm phạm vi truy vấn, tối ưu chỉ mục, chia workload, điều chỉnh cache allocation hoặc tăng bộ nhớ nếu có bằng chứng. Giữ cùng dữ liệu, tham số và tải đại diện; đo lại misses, bytes read, I/O latency, p95/p99, CPU và ảnh hưởng đến workload khác.

Không xóa cache production để tạo phép đo lạnh. Nếu cần so sánh cold cache và warm cache, dùng môi trường thử nghiệm hoặc bản sao dữ liệu được kiểm soát.

## Cách cải thiện hiệu quả sử dụng cache

### Giảm số trang cần truy cập

Tối ưu truy vấn và chỉ mục để giảm logical reads thường hữu ích hơn việc chỉ cố tăng hit ratio. Các biện pháp:

- Chọn cột cần thiết thay vì SELECT *.
- Dùng điều kiện lọc có thể tận dụng chỉ mục.
- Tạo composite/covering index khi workload chứng minh có lợi.
- Tránh lookup lặp lại quá nhiều hàng.
- Dùng partition pruning để bỏ qua dữ liệu không liên quan.
- Tổng hợp dữ liệu ở mức phù hợp nếu báo cáo lặp lại cùng phép tính.

Giảm số trang đọc có thể giảm CPU và áp lực cache ngay cả khi hit ratio không đổi.

### Giảm scan pollution

Nếu một truy vấn báo cáo quét lượng dữ liệu lớn và ít tái sử dụng, cân nhắc chạy trên replica hoặc hệ thống phân tích riêng, giới hạn phạm vi, chia batch hoặc dùng partition pruning. Một số engine có cơ chế scan-resistant cache, nhưng vẫn cần kiểm chứng tác động thực tế.

Không thêm chỉ mục chỉ để tránh mọi scan. Nếu truy vấn cần phần lớn bảng, scan có thể hiệu quả hơn. Mục tiêu là tránh scan không cần thiết và tránh để workload một lần làm mất các trang nóng quan trọng.

### Duy trì working set phù hợp

Có thể cải thiện bằng cách:
- Giữ buffer pool đủ lớn cho trang nóng và workload chính.
- Giới hạn memory grant hoặc concurrency của truy vấn nặng khi phù hợp.
- Tách workload phân tích khỏi workload giao dịch.
- Lên lịch batch và maintenance hợp lý.
- Dùng cache ứng dụng cho dữ liệu tham chiếu ít thay đổi nếu có cơ chế invalidation rõ ràng.
- Archive dữ liệu lạnh và giảm phạm vi quét.
- Theo dõi index bloat, fragmentation và các chỉ mục ít được dùng.

Không tăng buffer pool đến mức hệ điều hành thiếu bộ nhớ hoặc sort/hash không còn đủ memory. Database cache chỉ là một phần ngân sách RAM.

### Kiểm tra tác động của chỉ mục

Chỉ mục mới có thể làm truy vấn đọc ít trang hơn nhưng cũng chiếm buffer pool và làm tăng log generation khi ghi. Một bảng ghi nhiều với nhiều chỉ mục có thể gây cache pressure, write amplification và thời gian commit tăng.

Sau khi tạo chỉ mục, đo cả:
- Logical reads và physical/buffer reads của truy vấn mục tiêu.
- Buffer residency và hit/miss theo thời gian.
- Chi phí INSERT/UPDATE/DELETE.
- Dung lượng chỉ mục.
- Cache hit của workload khác.
- CPU, I/O và p95/p99 tổng thể.

## Ví dụ diễn giải một tình huống

Một hệ thống OLTP có buffer cache hit ratio 99,7% trong ngày. Tuy nhiên, p95 của API tra cứu tăng từ 40 ms lên 180 ms vào đầu mỗi giờ. Nhóm vận hành ban đầu cho rằng hit ratio cao chứng minh cache không phải nguyên nhân.

Khi phân tích theo cửa sổ 5 phút, nhóm thấy:

- Hit ratio tổng vẫn cao do các truy vấn tham chiếu nhỏ tạo rất nhiều hits.
- Một báo cáo đầu giờ quét hàng triệu trang, tạo lượng read lớn.
- Các trang nóng của bảng orders bị cạnh tranh trong buffer pool.
- Một số truy vấn OLTP có buffer misses tăng và I/O latency p95 tăng.
- CPU của báo cáo cũng làm tăng thời gian chờ của các truy vấn khác.

Nhóm tách số liệu theo query fingerprint và thời gian. Sau đó họ giới hạn báo cáo theo partition thời gian, giảm cột đọc, chạy báo cáo trên replica phù hợp và đo lại. API OLTP giảm p95 mà hit ratio tổng chỉ thay đổi nhẹ.

Kết luận của tình huống không phải “cache hit ratio vô dụng”. Chỉ số vẫn giúp nhận ra thay đổi ở tầng buffer, nhưng phải phân tích theo workload và kết hợp số miss tuyệt đối, bytes đọc, I/O latency và độ trễ truy vấn.

## Những sai lầm thường gặp

- **Coi database size là working set:** phần lớn dữ liệu có thể lạnh và không cần ở RAM cùng lúc.
- **Dùng hit ratio tích lũy để đánh giá giờ hiện tại:** counter dài hạn che giấu cache churn ngắn hạn.
- **Cho rằng buffer miss luôn là physical disk read:** OS hoặc storage cache có thể đáp ứng.
- **Cho rằng hit ratio 100% nghĩa truy vấn nhanh:** logical reads, CPU, lock và memory pressure vẫn có thể cao.
- **Cho rằng hit ratio thấp luôn là lỗi:** scan một lần hoặc workload phân tích có thể chấp nhận miss.
- **Chỉ xem tỷ lệ mà bỏ qua số miss tuyệt đối:** 1% của một tỷ yêu cầu vẫn là lượng lớn.
- **Gộp tất cả workload:** truy vấn quan trọng có thể bị chậm dù tỷ lệ tổng cao.
- **Nhân hit ratio với dung lượng database để suy ra working set:** hit ratio đo yêu cầu, không đo byte duy nhất.
- **Tăng RAM trước khi tìm nguyên nhân:** nút thắt có thể là CPU, lock, I/O queue hoặc scan không cần thiết.
- **Xóa cache production để benchmark:** có thể gây cold-cache storm và ảnh hưởng dịch vụ.
- **Thêm chỉ mục mà không đo chi phí ghi:** chỉ mục có thể làm buffer pool và log chịu thêm áp lực.
- **So sánh counter giữa các hệ quản trị như cùng định nghĩa:** kiến trúc và cách đếm khác nhau.

## Checklist đánh giá working set và cache

- [ ] Xác định tầng cache đang đo: application, database buffer pool, OS hay storage.
- [ ] Ghi rõ định nghĩa hits, misses và đơn vị trang của hệ quản trị.
- [ ] Lấy delta counter theo khoảng thời gian, xử lý restart/reset.
- [ ] Đo hit ratio cùng số miss tuyệt đối và byte đọc.
- [ ] Phân tích theo query fingerprint, database, table/index và workload.
- [ ] Ước lượng working set theo cửa sổ thời gian và mức độ tái sử dụng.
- [ ] Phân biệt trang dữ liệu, chỉ mục, dữ liệu tạm và trang metadata.
- [ ] Theo dõi cache churn, scan pollution, hot set và dữ liệu skew.
- [ ] Đối chiếu buffer reads với OS/storage I/O và latency.
- [ ] Kiểm tra CPU, lock/latch, memory grant, spill và queue depth.
- [ ] Không suy ra working set từ tổng dung lượng database hoặc hit ratio đơn lẻ.
- [ ] Đo lại cả workload đọc và ghi sau khi thay đổi cache, query hoặc index.

## Kết luận

Working set mô tả tập trang mà workload thực sự tái sử dụng trong một khoảng thời gian; cache hit ratio mô tả tỷ lệ yêu cầu được phục vụ từ một tầng cache theo định nghĩa của hệ thống. Hai khái niệm có liên quan nhưng không thể thay thế cho nhau. Hit ratio không cho biết chính xác working set lớn bao nhiêu, không chứng minh truy vấn nhanh và cũng không trực tiếp cho biết số lần đọc vật lý từ thiết bị.

Để chẩn đoán đúng, hãy xác định tầng cache, lấy delta counter theo thời gian, đo số miss tuyệt đối và byte đọc, phân tích theo workload rồi đối chiếu với I/O latency, CPU, lock và kế hoạch thực thi. Khi tối ưu, ưu tiên giảm số trang phải đọc và bảo vệ working set quan trọng; chỉ tăng bộ nhớ hoặc thay đổi cache allocation sau khi có bằng chứng về memory pressure và lợi ích dự kiến. Mọi điều chỉnh cần được kiểm chứng trên workload đại diện để cải thiện độ trễ và throughput tổng thể, không chỉ làm đẹp một tỷ lệ hit.