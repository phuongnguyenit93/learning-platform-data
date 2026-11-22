# Đo tải theo mẫu truy cập thay vì chỉ benchmark một lệnh

Redis rất nhanh đối với nhiều thao tác đơn giản, nhưng **một lệnh `GET` chạy nhanh trong benchmark không có nghĩa cả ứng dụng Spring Data Redis sẽ đáp ứng tốt dưới tải thật**. Một request nghiệp vụ có thể đọc nhiều key, cập nhật Hash, đặt TTL, gọi Lua script, giải mã JSON, truy vấn database khi cache miss và phát thêm công việc bất đồng bộ. Tại giờ cao điểm, các request còn tranh nhau connection, CPU, băng thông mạng và những key được truy cập thường xuyên.

Vì vậy, đo hiệu năng Redis cần bắt đầu từ **mẫu truy cập thực tế (access pattern/workload)**: ai gọi, dùng loại command nào, tỷ lệ đọc–ghi ra sao, key phân bố thế nào, payload lớn bao nhiêu, tỷ lệ hit/miss và hết hạn là bao nhiêu, có burst hay không, và mỗi request tạo ra bao nhiêu lượt tương tác với Redis.

Bài học này trình bày cách thiết kế một phép đo tải có ý nghĩa cho **Spring Data Redis**: dựng workload đại diện, tạo dữ liệu kiểm thử, phát tải với mô hình phù hợp, đo throughput và độ trễ ở nhiều tầng, nhận diện điểm nghẽn, so sánh các phương án và tránh những kết luận sai từ microbenchmark một lệnh.

> Nguyên tắc xuyên suốt: **benchmark một command chỉ đo command trong điều kiện của bài benchmark; benchmark một mẫu truy cập đo hệ thống sẽ hành xử thế nào khi workload có hình dạng gần với sản xuất**. Hai loại phép đo đều hữu ích nhưng trả lời những câu hỏi khác nhau.

## 1. Benchmark đơn lệnh trả lời được gì?

Redis có công cụ `redis-benchmark` để tạo các lệnh và đo hiệu năng trong một cấu hình cụ thể. Ví dụ:

~~~bash
redis-benchmark -h 127.0.0.1 -p 6379 -t get,set -n 100000 -c 50 -d 256
~~~

Ví dụ này chạy một tập lệnh GET/SET với số request, mức concurrency và kích thước payload đã chọn. Nó có ích khi cần:

- Xác nhận một Redis node phản hồi trong điều kiện tiêu chuẩn.
- So sánh tác động của mạng, TLS hoặc thay đổi hạ tầng trong cùng một phép thử.
- Ước lượng giới hạn tương đối của một loại command với số connection nhất định.
- Phát hiện cấu hình Redis hoặc client quá chậm ngay cả ở workload rất đơn giản.

Nhưng kết quả **không tự đại diện cho throughput của Spring Boot service**. Một HTTP request thực tế có thể trải qua:

~~~text
                     HTTP request / Scheduled job
                                  |
                                  v
                     Controller / Business logic
                                  |
                     Serializer / JSON mapping
                                  |
                                  v
                       Spring Data Redis API
                                  |
                       Lettuce / Jedis driver
                                  |
                     Connection / Queue / Network
                                  |
                                  v
                            Redis server
                         /      |       \
                       GET    HGETALL   SET EX
                         \      |       /
                                  |
                        Deserialize / Aggregation
                                  |
                     Có cache miss? Gọi nguồn khác?
                                  |
                                  v
                            HTTP response
~~~

Benchmark `GET` trực tiếp bỏ qua phần lớn những tầng này. Nếu service tạo ra 5 lệnh Redis cho một HTTP request, **100.000 Redis operations/giây không đồng nghĩa 100.000 HTTP requests/giây**. Chưa kể kết quả lệnh, dữ liệu và thứ tự phụ thuộc nhau.

## 2. Phân biệt bốn cấp đo hiệu năng

| Cấp độ | Đo đối tượng nào? | Câu hỏi trả lời được | Điều chưa chứng minh |
| --- | --- | --- | --- |
| **Microbenchmark command** | Một lệnh như `GET`, `SET`, `HGET` trên Redis | Command nhanh ra sao trong điều kiện đã chọn? | Chuỗi nghiệp vụ tổng thể |
| **Client/driver benchmark** | Lettuce/Jedis, connection, pipeline, serializer | Ứng dụng Java gửi/nhận lệnh Redis thế nào? | Toàn bộ request qua service |
| **Workload benchmark** | Tổ hợp lệnh, key, payload, TTL, concurrency | Redis và client chịu được mẫu truy cập đại diện không? | Những phần hệ thống nằm ngoài phạm vi mô phỏng |
| **End-to-end load test** | HTTP/API/event/job đi qua toàn bộ dependency | Người dùng thấy latency, errors, throughput thế nào? | Nguyên nhân cụ thể nếu thiếu metrics theo tầng |

Nên phối hợp các cấp đo. Microbenchmark giúp có **baseline** của Redis; workload benchmark kiểm tra phân bố lệnh/dữ liệu; end-to-end test xác định năng lực ứng dụng hoàn chỉnh.

Ví dụ, một nhóm đo thấy:

~~~text
redis-benchmark GET:   throughput rất cao
Spring API /products:  p99 vẫn lớn khi QPS tăng
~~~

Không thể vội kết luận Redis vô can hay Spring Data Redis quá chậm. Cần đo thêm thời gian chờ connection, serialization, số round trip, cache hit ratio, mức tải database và khả năng một số key bị truy cập quá tập trung.

## 3. Bước đầu tiên: mô tả mẫu truy cập thật

Một workload đại diện không chỉ là `80% GET + 20% SET`. Nên ghi lại ít nhất các chiều sau:

| Chiều workload | Câu hỏi cần trả lời | Ảnh hưởng hiệu năng |
| --- | --- | --- |
| **Command mix** | GET, SET, HGETALL, ZRANGE, EVAL, XADD chiếm bao nhiêu? | CPU Redis, số round trip, dạng response |
| **Key cardinality** | Có vài nghìn hay vài triệu key? | Memory, hit ratio, bộ nhớ cache và eviction |
| **Key popularity** | Truy cập đều hay 80% request tập trung vào 1% key? | Hot key, phân tán tải, bottleneck theo shard |
| **Payload size** | P50/P95/P99 của value, hash field, stream entry bao nhiêu? | Serialization, network, output buffer, GC |
| **Cache hit/miss** | Tỷ lệ miss theo nhóm key hoặc theo thời điểm là bao nhiêu? | Tải DB, cache fill, throughput tổng thể |
| **TTL/expiration** | TTL cố định hay trải rộng, có hết hạn đồng loạt không? | Active expiration, miss burst, tái tạo dữ liệu |
| **Arrival pattern** | Request đều, cao điểm, burst, diurnal, spike? | Queueing, tail latency và overload |
| **Concurrency** | Bao nhiêu request đang chạy và connection được chia sẻ thế nào? | Connection contention, thread và event-loop |
| **Operation dependency** | GET xong mới SET, hay các lệnh độc lập? | Mức độ có thể pipeline/batch |
| **Read consistency** | Đọc primary hay replica, có yêu cầu read-your-writes? | Routing, độ trễ, kết quả đọc |
| **Failure behavior** | Timeout, retry, fallback, failover gây thêm bao nhiêu lệnh? | Load amplification khi có sự cố |

Thu thập phân bố thay vì chỉ lấy trung bình. “Payload trung bình 1 KB” có thể che tình huống 95% payload chỉ 100 B nhưng 5% payload 20 KB. Năm phần trăm dữ liệu lớn đôi khi chi phối băng thông, phân bổ bộ nhớ và độ trễ phần đuôi.

**Bảo vệ dữ liệu nhạy cảm:** khi xây workload từ log/trace, chỉ giữ metadata cần thiết như command family, kích thước, nhóm key, TTL bucket và khoảng thời gian. Không đưa value thật, token, session ID, thông tin cá nhân hay khóa định danh khách hàng vào bộ test khi chưa có yêu cầu và biện pháp bảo vệ phù hợp.

### 3.1. Ví dụ một request nghiệp vụ thực sự

API `GET /products/{id}` có thể thực hiện:

~~~text
GET cache:product:<id>                (~90% request cache hit)
  |
  +-- hit:
  |    Deserialize JSON → trả HTTP
  |
  +-- miss:
       SELECT product FROM database
       SET cache:product:<id> EX <ttl>
       Deserialize/serialize → trả HTTP
~~~

Benchmark GET trực tiếp sẽ không mô phỏng được nhánh cache miss. Nếu tỷ lệ hit thật giảm từ 90% xuống 50%, tải lên database và thời gian phản hồi API có thể biến đổi mạnh dù tốc độ Redis `GET` gần như không đổi.

Một API khác có thể thực hiện:

~~~text
POST /checkout
   |
   +-- GET cart:<id>
   +-- HGETALL inventory:<sku>
   +-- EVAL script kiểm tra hạn mức
   +-- XADD orders:events
   +-- DELETE cart:<id>
   |
   +-- HTTP response
~~~

Chỉ benchmark `GET` hoặc `SET` không mô phỏng lượng lệnh, kích thước response, dependency và những thao tác có side effect của flow này.

## 4. Xây một workload profile có thể đo lặp lại

Đặt một **profile cố định có version**, lưu trong tài liệu kiểm thử để lần đo sau tái lập được. Một ví dụ hoàn toàn minh họa:

| Thành phần | Profile A: Cache thường ngày | Profile B: Giờ cao điểm | Profile C: TTL burst |
| --- | --- | --- | --- |
| Operation mix | 80% GET, 15% SET EX, 5% HGETALL | 85% GET, 10% SET EX, 5% HGETALL | 75% GET, 20% SET EX, 5% HGETALL |
| Keyspace | 100.000 key | 100.000 key | 100.000 key |
| Hot key | 80% lượt truy cập ở 2% key | 95% lượt truy cập ở 1% key | Tập trung vào nhóm key vừa hết hạn |
| Payload | Chủ yếu 128 B–1 KB, đuôi 8 KB | Tỷ lệ payload lớn tăng | Có thêm payload tái tạo từ DB |
| Cache miss | 10% GET | 15% GET | Tăng đột ngột trong cửa sổ hết TTL |
| Tốc độ đến | Đều, tăng dần | Có burst | Burst có tương quan theo thời gian |
| Dependency | Redis read/write độc lập phần lớn | Concurrent reads tập trung | Miss → DB → SET lại cache |

Các tỷ lệ trên **không phải số liệu mặc định của Redis hay Spring**. Chúng chỉ là mẫu để xây thí nghiệm. Profile production phải lấy từ số liệu đo của ứng dụng, rồi được ẩn danh và chuẩn hóa.

Với mỗi profile, ghi thêm:

- Phiên bản ứng dụng, Spring Boot, Spring Data Redis, Lettuce/Jedis và Redis.
- Topology: standalone, Sentinel hay Cluster, số node và loại kết nối.
- Serializer và kích thước payload thực tế.
- Chính sách TTL, persistence/eviction, pool và timeout.
- Mức tải nền của các dependency khác.
- Điều kiện bắt đầu, thời gian warm-up, ramp-up, steady-state, số lần lặp và quy tắc dừng.

Nếu các yếu tố này thay đổi giữa hai lượt benchmark, so sánh kết quả có thể không còn công bằng.

## 5. Phân bố key: một yếu tố dễ bị bỏ qua

Không phải tất cả key đều được truy cập đều nhau. Một cách phát key hoàn toàn ngẫu nhiên đồng đều (*uniform*) có thể tạo kết quả rất khác môi trường sản xuất với hot key, key theo tenant hoặc key mới sinh liên tục.

### 5.1. Phân bố đồng đều và phân bố lệch

~~~text
Uniform workload:

Key 1  ███
Key 2  ███
Key 3  ███
Key 4  ███
Key 5  ███

Skewed workload:

Key 1  ████████████████████
Key 2  ███████
Key 3  ██
Key 4  █
Key 5  █
~~~

Một số phương pháp:

- **Uniform:** mỗi key có xác suất tương đương, hữu ích làm baseline.
- **Hotset:** phần lớn request rơi vào một tập key nhỏ, dễ mô phỏng bằng hai tầng lựa chọn.
- **Zipf-like:** mức phổ biến giảm theo thứ hạng, dùng để mô phỏng phân bố lệch liên tục.
- **Temporal locality:** một key vừa được truy cập có khả năng được truy cập lại trong một thời gian ngắn.
- **Tenant-specific:** nhiều request tập trung vào một tenant lớn, còn các tenant nhỏ có ít truy cập.

Với Redis Cluster, hot key hoặc một key chứa Hash lớn có thể khiến một shard bị nghẽn dù tổng số node trong cụm còn nhiều CPU. Benchmark uniform có thể chia tải đều theo slot và che mất vấn đề đó.

### 5.2. Kích thước keyspace quyết định hit ratio

Nếu benchmark chỉ dùng 100 key đã nạp sẵn, gần như mọi lần GET đều hit; workload có thể quá dễ. Nếu keyspace có hàng triệu key nhưng Redis chỉ chứa một phần, sẽ có miss và eviction.

Một phép thử đúng nên nêu rõ:

~~~text
Key được chọn từ tập nào?
Bao nhiêu key đã preload?
Tỷ lệ GET vào key không có là bao nhiêu?
Số key hết TTL trong khoảng thử?
Có write làm thay đổi tập key đang tồn tại không?
~~~

Đừng tự nhiên tăng keyspace lên 10 triệu mà giữ nguyên `maxmemory` rồi kết luận Redis chậm hơn: có thể môi trường vừa chuyển từ “tất cả nằm trong RAM” sang “eviction liên tục”, là một workload khác.

## 6. Kích thước payload và cấu trúc dữ liệu thay đổi chi phí

Redis xử lý `GET key` trả 64 byte khác đáng kể với `GET key` trả 1 MB. Kích thước payload ảnh hưởng:

1. Số byte qua mạng mỗi request.
2. Số object/byte array mà Java tạo hoặc copy.
3. Chi phí UTF-8, JSON và mapping object.
4. Áp lực garbage collector.
5. Output buffer phía Redis và các queue của client.

Trong Spring Data Redis, phép đo nên phân biệt:

~~~text
GET key → byte[] Redis → deserialize → Java DTO
            |                 |
         Network           CPU / GC
~~~

Nếu benchmark thuần Redis chỉ phát value 64 byte nhưng ứng dụng sử dụng JSON 20 KB, chênh lệch p99 có thể xuất phát từ mạng và serialization chứ không phải Redis command logic.

### Command khác nhau có độ phức tạp khác nhau

| Mẫu truy cập | Điểm cần mô phỏng |
| --- | --- |
| `GET` / `SET` | Value size, hit/miss, TTL, write amplification |
| `MGET` / `MSET` | Số key mỗi batch, kích thước phản hồi, slot constraints trong Cluster |
| `HGET` / `HGETALL` | Số field trong Hash, kích thước từng field, tỷ lệ đọc toàn bộ |
| `SMEMBERS` | Cardinality của Set và nguy cơ phản hồi rất lớn |
| `ZRANGE` / `ZREVRANGE` | Số phần tử được lấy, score distribution và phân trang |
| `EVAL` / Lua | Số key/logic trong script, thời gian giữ Redis xử lý script |
| `XADD` / `XREADGROUP` | Entry size, batch size, consumer count, pending/ACK |
| `PUBLISH` | Số subscriber thực, fan-out và khối lượng callback phía ứng dụng |

Không nên so throughput của `GET 64B` với `HGETALL Hash 5.000 field` rồi nói một cách tuyệt đối rằng “Hash chậm”. Hai phép thử có lượng dữ liệu, số phần tử và hành vi khác nhau.

## 7. TTL, eviction và cache miss phải là một phần của workload

TTL không chỉ là metadata. Một workload có nhiều key hết hạn cùng lúc có thể làm tỷ lệ miss tăng đột ngột:

~~~text
Nhiều key được SET EX 300 tại 10:00
                    |
                    v
              10:05 đến hạn
                    |
                    v
       Hàng loạt GET trả cache miss
                    |
                    v
             DB query tăng mạnh
                    |
                    v
       Nhiều request SET lại cùng key
~~~

Đây là hiện tượng **cache stampede**. Một benchmark chạy GET trên key được preload và không bao giờ hết hạn sẽ không thấy rủi ro đó.

Khi mô phỏng TTL, cần biết:

- TTL có cố định cho mọi key hay có jitter?
- Bao nhiêu key được tạo cùng thời điểm?
- Có sliding expiration (gia hạn sau khi truy cập) không?
- Có key không có TTL?
- Khi key hết hạn, service đi database, hàng đợi hoặc API nào?
- Có cơ chế single-flight/lock để tránh nhiều request cùng tái tạo cache?

`maxmemory` và eviction policy cũng ảnh hưởng mạnh. Khi dữ liệu vượt giới hạn bộ nhớ, Redis có thể xóa key theo chính sách; benchmark phải đo **evicted_keys**, **expired_keys**, memory usage và hit/miss đồng thời với độ trễ.

Một hệ thống có throughput cao nhưng eviction liên tục làm database quá tải chưa phải là hệ thống hoạt động tốt.

## 8. Mô hình phát tải: closed-loop và open-loop

Cách tạo request ảnh hưởng trực tiếp đến phép đo. Hai mô hình thường gặp:

### 8.1. Closed-loop: cố định số worker đồng thời

Trong mô hình closed-loop, mỗi worker gửi request, chờ hoàn tất rồi mới gửi request tiếp:

~~~text
Worker 1:  request → wait → request → wait → ...
Worker 2:  request → wait → request → wait → ...
Worker 3:  request → wait → request → wait → ...
~~~

Khi hệ thống chậm, mỗi worker chờ lâu hơn nên **tốc độ gửi request tự giảm**. Điều này phù hợp để đo sức chịu tải dưới một số client đồng thời, nhưng có thể che việc hệ thống không đáp ứng nổi một tốc độ request đến thực tế.

### 8.2. Open-loop: giữ tốc độ request đến mục tiêu

Trong mô hình open-loop, bộ phát tải cố gửi request theo lịch, chẳng hạn 2.000 request/giây, bất kể request trước đã kết thúc chưa:

~~~text
Arrivals:  | | | | | | | | | | | | ...
Responses: |   |      |       |  ...
Queue:     0 1 3 5 8 12 ...
~~~

Khi Redis hoặc service không đủ năng lực xử lý, số request pending tăng, p95/p99 và timeout tăng; kết quả cho thấy rõ điểm quá tải.

### 8.3. Coordinated omission

**Coordinated omission** xảy ra khi bộ đo chỉ ghi latency của những request thực sự được phát sau khi request trước hoàn tất, làm mất những khoảng request *lẽ ra phải tới* nhưng không được phát vì load generator cũng đang chờ.

Ví dụ request mất 2 giây, closed-loop worker đứng chờ và không tạo thêm các arrival dự kiến. Nếu hệ thống thật có request đến liên tục, một số người dùng phải chờ trong queue nhưng phép đo closed-loop không ghi được độ trễ chờ đó.

Để tránh kết luận sai:

- Xác định phép thử đang dùng open-loop hay closed-loop.
- Với mục tiêu capacity ở một QPS cố định, sử dụng arrival schedule độc lập và đo cả thời gian chờ queue.
- Đo **offered load** (request được đưa vào) và **achieved throughput** (request hoàn tất thành công) riêng.
- Giám sát số in-flight, rejected, timed out và thời gian nằm trong queue.
- Chọn công cụ load test có hỗ trợ ghi nhận hoặc hiệu chỉnh coordinated omission khi phù hợp.

Đừng so sánh p99 của một phép thử open-loop 3.000 QPS với phép thử closed-loop 50 workers như thể chúng có cùng hình dạng tải.

## 9. Đo cái gì: throughput, latency và kết quả nghiệp vụ

Một benchmark tốt không chỉ in ra một số “requests/second”. Hãy theo dõi đồng thời:

| Metric | Ý nghĩa | Cần chú ý |
| --- | --- | --- |
| **Offered RPS** | Tốc độ request bộ tạo tải cố đưa vào | Có thể cao hơn năng lực xử lý |
| **Completed RPS** | Request hoàn tất mỗi giây, kể cả lỗi nếu được tính riêng | Không đồng nghĩa thành công |
| **Successful RPS** | Request thành công mỗi giây | Phải kèm error rate |
| **p50 latency** | Một nửa request có độ trễ nhỏ hơn hoặc bằng | Chỉ phản ánh trải nghiệm điển hình |
| **p95/p99/p99.9 latency** | Độ trễ ở đuôi phân bố | Nhạy với queue, GC, payload lớn và burst |
| **Error/timeout rate** | Tỷ lệ thao tác không hoàn tất đúng yêu cầu | Nếu bỏ request lỗi khỏi histogram, latency có thể trông “đẹp” giả |
| **In-flight/queue depth** | Số request đang thực hiện hoặc xếp hàng | Dùng để tìm điểm quá tải |
| **Hit/miss ratio** | Tỷ lệ truy cập cache có/không có dữ liệu | Cần đo cùng DB fallback |
| **Bytes in/out** | Lưu lượng mạng thực tế | Đặc biệt quan trọng với payload lớn |
| **Redis CPU/memory** | Độ sử dụng server | Phân biệt Redis bottleneck với client bottleneck |
| **GC/heap/client CPU** | Chi phí phía JVM | Có thể chi phối kết quả dù Redis CPU thấp |

### Độ trễ cần đo ở đâu?

Với một HTTP request:

~~~text
HTTP ingress
   |
   +-- Routing / filter / authentication
   +-- Business logic
   +-- Serialization trước Redis
   +-- Chờ connection / client queue
   +-- Network request + Redis execution + response
   +-- Deserialization
   +-- Database/API fallback nếu miss
   +-- Build response
   |
HTTP response
~~~

Nên có ít nhất ba loại độ trễ:

1. **End-to-end latency:** từ lúc request tới ứng dụng đến lúc response hoàn tất.
2. **Redis client operation latency:** khoảng thời gian bao gồm lệnh Redis đi qua template/driver và trở về.
3. **Redis server command latency:** thời gian Redis thực thi command, quan sát qua các công cụ và metric của Redis.

Các thời gian này **không nhất thiết cộng lại đơn giản** do concurrency, queueing, overlap và asynchronous operations. Nếu độ trễ phía ứng dụng cao nhưng Redis server có CPU thấp và slow log gần như trống, cần điều tra mạng, connection wait, serializer và client queue.

### Báo cáo latency theo từng nhóm operation

Một phân bố p99 chung có thể che hiện tượng phần lớn GET nhanh nhưng 5% `HGETALL` có payload lớn rất chậm. Nên đo riêng:

~~~text
GET hit         p50 / p95 / p99
GET miss        p50 / p95 / p99
SET EX          p50 / p95 / p99
HGETALL         p50 / p95 / p99
Service request p50 / p95 / p99
~~~

Không chỉ báo “p99 = 25 ms”; phải gắn con số với **đơn vị, phạm vi đo, profile, offered load, success rate và giai đoạn thử**.

## 10. Quan hệ giữa concurrency, latency và throughput

Trong trạng thái ổn định, **định luật Little** mô tả quan hệ xấp xỉ:

\[
L = \lambda W
\]

Trong đó:

- `L`: số công việc trung bình đang ở trong hệ thống.
- `\lambda`: tốc độ công việc hoàn tất hoặc đến hệ thống trong điều kiện ổn định.
- `W`: thời gian trung bình một công việc ở trong hệ thống.

Ví dụ, nếu 1.000 request/giây hoàn tất ổn định với thời gian đầu-cuối trung bình 20 ms:

\[
L \approx 1000 \times 0{,}020 = 20
\]

Số request đang xử lý trung bình xấp xỉ 20. Đây là quan hệ giúp **kiểm tra tính hợp lý** của số liệu, không phải công thức dự báo throughput tối đa chỉ từ số thread. Khi hệ thống overload và queue tăng liên tục, giả định steady state không còn đúng.

Một phép thử với 32 worker closed-loop và latency trung bình tăng từ 10 ms lên 100 ms sẽ phát request **chậm đi rõ rệt**, ngay cả khi không cố ý giảm tải. Do đó phải báo cả concurrency và achieved throughput, không nhìn latency một mình.

### Nhận diện điểm gãy của hệ thống

Khi tăng offered load qua từng mức:

~~~text
Offered RPS      500   1000  1500  2000  2500
Success RPS      500   1000  1490  1940  1930
p99 latency      thấp  tăng  tăng  vọt   rất cao
Timeout rate     0%    0%    nhỏ  tăng   tăng mạnh
~~~

Đây là **số minh họa**, không phải benchmark đã chạy. Khi success throughput không tăng nữa dù offered RPS tiếp tục tăng, còn p99 và lỗi leo thang, hệ thống có thể đã chạm một giới hạn quan trọng. Cần xem bottleneck nằm ở Redis CPU, memory bandwidth, network, client connection, serializer hay dependency khác.

## 11. Chuẩn bị tập dữ liệu trước khi đo

Nếu workload đọc chủ yếu những key không tồn tại, kết quả sẽ khác hẳn một cache có tỷ lệ hit cao. Trước khi phát tải, hãy **seed data** theo profile và kiểm tra số key, kích thước payload và cấu trúc dữ liệu đại diện.

Ví dụ một namespace tách biệt:

~~~text
bench:run-20261113:value:0
bench:run-20261113:value:1
bench:run-20261113:hash:0
bench:run-20261113:hash:1
...
~~~

Trong môi trường thật nên tạo `runId` duy nhất cho mỗi lượt đo. Không dùng key cùng tên với dữ liệu sản xuất; không gọi `FLUSHALL` để “dọn sạch môi trường” dùng chung.

### Dữ liệu phải đủ lớn để thử đúng đường xử lý

- **Warm-cache profile:** preload trước khi bắt đầu đo, sau đó warm-up Spring và Redis.
- **Cold-cache profile:** không preload nhóm key sẽ bị miss, đo riêng tải fallback.
- **Payload-mix profile:** seed value 128 B, 1 KB, 8 KB theo phân bố mong muốn; không chỉ dùng một chuỗi `"hello"`.
- **Hash profile:** tạo Hash có số field và kích thước đại diện; `HGETALL` với 3 field khác 3.000 field.
- **TTL profile:** chọn khoảng TTL, jitter và thời điểm tạo key phản ánh sản xuất.
- **Skew profile:** phát access theo hotset hoặc Zipf-like distribution, không chỉ random uniform.

Quá trình seed và cleanup phải được **tách khỏi cửa sổ đo tải ổn định**. Nếu vừa seed 100.000 key vừa đo GET, số liệu sẽ bao gồm tải chuẩn bị và có thể không phản ánh steady state cần nghiên cứu.

## 12. Ví dụ Java: phát workload kết hợp qua `StringRedisTemplate`

Ví dụ sau minh họa một harness nhỏ chạy trong **môi trường test/staging**, không phải một benchmark framework hoàn chỉnh. Nó dùng:

- `StringRedisTemplate` để đưa vào đường đi Spring Data Redis và driver thật.
- Nhiều worker thread, mỗi thread gọi command nối tiếp (*closed-loop*).
- Mix 80% `GET`, 15% `SET` kèm TTL, 5% `HGETALL`.
- 80% lượt truy cập tập trung vào 2% key để mô phỏng hotset.
- Khoảng 10% GET dùng key cố ý không tồn tại để mô phỏng cache miss.
- `HdrHistogram Recorder` để ghi latency theo microsecond từ nhiều thread.
- Bộ đếm thành công, lỗi và cache hit/miss.

**Các tỷ lệ chỉ là tham số minh họa**; thay bằng phân bố đã quan sát từ ứng dụng.

Dependency bổ sung cho code đo ở bộ test/harness:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.hdrhistogram:HdrHistogram:2.2.2'
}
~~~

Ví dụ code dưới có thể đặt trong `src/test/java` hoặc một module load-testing riêng. Không đưa logic chạy benchmark vào `@PostConstruct` hoặc auto-run khi ứng dụng production khởi động.

### 12.1. Tạo dữ liệu có phân bố kích thước

~~~java
package com.example.redis.performance;

import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class BenchmarkDataSeeder {

    private static final String SMALL = "x".repeat(128);
    private static final String MEDIUM = "x".repeat(1024);
    private static final String LARGE = "x".repeat(8192);

    private final StringRedisTemplate redis;

    public BenchmarkDataSeeder(StringRedisTemplate redis) {
        this.redis = Objects.requireNonNull(redis);
    }

    public void seed(String namespace, int keyCount) {
        if (!namespace.startsWith("bench:") || keyCount <= 0) {
            throw new IllegalArgumentException(
                "Use isolated benchmark namespace and positive keyCount"
            );
        }

        for (int i = 0; i < keyCount; i++) {
            String payload = i % 20 == 0
                ? LARGE
                : (i % 5 == 0 ? MEDIUM : SMALL);

            redis.opsForValue().set(
                namespace + ":value:" + i,
                payload,
                Duration.ofMinutes(30)
            );

            redis.opsForHash().putAll(
                namespace + ":hash:" + i,
                Map.of(
                    "id", Integer.toString(i),
                    "status", "READY",
                    "category", "STANDARD",
                    "description", payload
                )
            );
            redis.expire(
                namespace + ":hash:" + i,
                Duration.ofMinutes(30)
            );
        }
    }
}
~~~

Đoạn seed cố tình làm Hash có ít field nhưng value không đồng nhất về kích thước. Nếu production có Hash hàng nghìn field, hãy xây thêm profile riêng cho phân bố đó. Đừng tự đánh giá `HGETALL` trên Hash 4 field là đại diện cho mọi Hash.

Lưu ý về TTL: mã minh họa tạo value và Hash với TTL 30 phút; nếu một bài soak test chạy lâu hơn, nhiều key có thể hết hạn, khiến workload chuyển từ warm-cache sang miss-heavy. Muốn đo steady state, phải kiểm soát TTL hoặc chọn một profile cố ý quan sát expiration.

### 12.2. Class tạo tải và ghi latency

~~~java
package com.example.redis.performance;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;

import org.HdrHistogram.Histogram;
import org.HdrHistogram.Recorder;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisPatternBenchmark {

    private static final long MAX_RECORDED_MICROS = 60_000_000L;
    private static final String SMALL = "x".repeat(128);
    private static final String MEDIUM = "x".repeat(1024);
    private static final String LARGE = "x".repeat(8192);

    private final StringRedisTemplate redis;

    public RedisPatternBenchmark(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public record Scenario(
            String namespace, int clients, int callsPerClient,
            int keyCount, long seed) {
        public Scenario {
            if (!namespace.startsWith("bench:")
                    || clients <= 0
                    || callsPerClient <= 0
                    || keyCount <= 0) {
                throw new IllegalArgumentException(
                    "Invalid benchmark scenario"
                );
            }
        }
    }

    public record Result(
            long successful,
            long failures,
            long hits,
            long misses,
            double elapsedSeconds,
            double successfulOpsPerSecond,
            long p50Micros,
            long p95Micros,
            long p99Micros) {
    }

    public Result run(Scenario cfg) throws Exception {
        Recorder recorder = new Recorder(
            1L, MAX_RECORDED_MICROS, 3
        );
        LongAdder successes = new LongAdder();
        LongAdder failures = new LongAdder();
        LongAdder hits = new LongAdder();
        LongAdder misses = new LongAdder();

        ExecutorService pool =
            Executors.newFixedThreadPool(cfg.clients());
        CountDownLatch ready = new CountDownLatch(cfg.clients());
        CountDownLatch go = new CountDownLatch(1);
        List<Future<?>> futures = new ArrayList<>();

        try {
            for (int worker = 0; worker < cfg.clients(); worker++) {
                final int workerId = worker;

                futures.add(pool.submit(() -> {
                    SplittableRandom random =
                        new SplittableRandom(
                            cfg.seed() + workerId
                        );
                    ready.countDown();
                    go.await();

                    for (int n = 0; n < cfg.callsPerClient(); n++) {
                        long started = System.nanoTime();
                        try {
                            executeOne(
                                cfg, random, hits, misses
                            );
                            successes.increment();
                        } catch (RuntimeException error) {
                            failures.increment();
                            // Production harness nên ghi loại lỗi
                            // nhưng không log một stack trace mỗi request.
                        } finally {
                            long elapsedMicros = Math.max(
                                1L,
                                TimeUnit.NANOSECONDS.toMicros(
                                    System.nanoTime() - started
                                )
                            );
                            recorder.recordValue(
                                Math.min(
                                    elapsedMicros,
                                    MAX_RECORDED_MICROS
                                )
                            );
                        }
                    }
                    return null;
                }));
            }

            if (!ready.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Workers did not become ready"
                );
            }

            long begin = System.nanoTime();
            go.countDown();

            for (Future<?> future : futures) {
                future.get(5, TimeUnit.MINUTES);
            }

            double seconds =
                (System.nanoTime() - begin) / 1_000_000_000.0;
            Histogram snapshot = recorder.getIntervalHistogram();

            return new Result(
                successes.sum(),
                failures.sum(),
                hits.sum(),
                misses.sum(),
                seconds,
                successes.sum() / seconds,
                snapshot.getValueAtPercentile(50),
                snapshot.getValueAtPercentile(95),
                snapshot.getValueAtPercentile(99)
            );
        } finally {
            go.countDown();
            pool.shutdownNow();
            pool.awaitTermination(10, TimeUnit.SECONDS);
        }
    }

    private void executeOne(
            Scenario cfg,
            SplittableRandom random,
            LongAdder hits,
            LongAdder misses) {

        int hotsetSize = Math.max(1, cfg.keyCount() / 50);
        int index = random.nextDouble() < 0.80
            ? random.nextInt(hotsetSize)
            : random.nextInt(cfg.keyCount());

        int operation = random.nextInt(100);

        if (operation < 80) {
            boolean deliberatelyMissing =
                random.nextInt(10) == 0;

            String key = deliberatelyMissing
                ? cfg.namespace() + ":missing:" + index
                : cfg.namespace() + ":value:" + index;

            String value = redis.opsForValue().get(key);
            if (value == null) {
                misses.increment();
            } else {
                hits.increment();
            }
        } else if (operation < 95) {
            String payload = random.nextInt(20) == 0
                ? LARGE
                : (random.nextInt(5) == 0 ? MEDIUM : SMALL);

            redis.opsForValue().set(
                cfg.namespace() + ":value:" + index,
                payload,
                Duration.ofMinutes(10)
            );
        } else {
            redis.opsForHash().entries(
                cfg.namespace() + ":hash:" + index
            );
        }
    }
}
~~~

Ví dụ này minh họa **một harness closed-loop**: mỗi worker chờ lệnh Redis hoàn tất rồi mới gọi lệnh tiếp theo. Các thread cùng bắt đầu qua `CountDownLatch` để cửa sổ đo không bị lệch do thời điểm khởi tạo worker.

`Recorder` của HdrHistogram chấp nhận ghi từ nhiều thread và cho phép lấy histogram kết quả. Ở ví dụ này, mọi operation thành công hoặc lỗi đều được ghi latency. Các thời gian vượt 60 giây được **clamp** về giới hạn histogram; một benchmark production nên đếm riêng số mẫu bị clamp và chọn giới hạn lớn hơn nếu cần, để không làm sai tail latency.

Với kết quả của class, `hits/misses` chỉ đếm **GET**; không phải hit ratio của cả các Hash hoặc mọi business operation. `successfulOpsPerSecond` tính tất cả operation không ném exception, bao gồm GET trả null. Nếu nghiệp vụ coi cache miss là thất bại, cần thêm metric riêng chứ không tự đổi nghĩa của số successful operations.

### 12.3. Gọi harness từ integration test riêng

~~~java
BenchmarkDataSeeder seeder =
    new BenchmarkDataSeeder(stringRedisTemplate);

RedisPatternBenchmark benchmark =
    new RedisPatternBenchmark(stringRedisTemplate);

String namespace = "bench:" + java.util.UUID.randomUUID();
int keys = 10_000;

seeder.seed(namespace, keys); // Không tính vào thời gian đo.

RedisPatternBenchmark.Scenario scenario =
    new RedisPatternBenchmark.Scenario(
        namespace,
        20,       // Số worker closed-loop
        2_000,    // Số lệnh mỗi worker
        keys,
        42L       // Random seed để có thể tái lập profile
    );

// Chạy warm-up riêng trước khi lấy kết quả chính thức.
RedisPatternBenchmark.Result result = benchmark.run(scenario);

System.out.printf(
    "ok=%d errors=%d tps=%.1f p50=%d us p95=%d us p99=%d us%n",
    result.successful(),
    result.failures(),
    result.successfulOpsPerSecond(),
    result.p50Micros(),
    result.p95Micros(),
    result.p99Micros()
);
~~~

Đây là **đoạn minh họa cách gọi**, không phải benchmark đã được chạy. Không công bố một con số hiệu năng giả định từ đoạn này. Với profile thật, phải có nhiều lần lặp, warm-up, giai đoạn steady-state và cấu hình runtime/hạ tầng kèm theo.

**Giới hạn của harness mẫu:**

- Là closed-loop; không giữ một offered RPS cố định khi Redis chậm đi.
- Tỷ lệ command và payload là gần đúng do lấy mẫu ngẫu nhiên, không phải đếm quota chính xác.
- Chưa tách latency theo từng command; để phân tích bottleneck phải tạo histogram riêng cho GET, SET và HGETALL.
- Không có giải pháp load-generator phân tán nhiều host và không mô phỏng HTTP/controller/auth.
- Chưa mô phỏng Redis Cluster routing, Sentinel failover, Stream consumer hay Pub/Sub subscribers.
- Không phải công cụ benchmark có khả năng tự chẩn đoán coordinated omission.
- Không đo trực tiếp cost của JSON serializer vì `StringRedisTemplate` sử dụng string serialization.

Với hệ thống thực tế, cần bổ sung những chiều còn thiếu hoặc dùng một công cụ chuyên dụng. Ví dụ vẫn hữu ích vì nó **đo tổ hợp thao tác qua Spring Data Redis** thay vì chỉ gửi một command trực tiếp tới Redis.

## 13. Kiểm thử luồng ứng dụng hoàn chỉnh

Nếu mục tiêu là biết API của Spring Boot chịu được bao nhiêu request với SLO cụ thể, hãy bổ sung **HTTP load test** chạy xuyên qua controller, authentication, serialization, Redis, database và response.

Ví dụ hai lớp thử:

~~~text
                [A] Redis Pattern Benchmark

Benchmark Java → StringRedisTemplate → Lettuce → Redis
             (chủ yếu đo đường truy cập Redis)

                [B] End-to-End Load Test

Load generator → HTTP/WebFlux/MVC → Service
                                     |
                           +---------+----------+
                           |                    |
                           v                    v
                  Spring Data Redis         Database/API
                           |                    |
                           +---------+----------+
                                     |
                                HTTP response
           (đo trải nghiệm thực và các dependency)
~~~

Khi API có nhiều endpoint, phân bố endpoint phải gần sản xuất:

| Endpoint minh họa | Tỷ trọng traffic | Redis pattern |
| --- | --- | --- |
| `GET /products/{id}` | 60% | GET cache; miss → DB → SET EX |
| `GET /users/{id}/cart` | 20% | HGETALL hoặc nhiều HGET |
| `POST /cart/items` | 12% | HSET/EXPIRE và kiểm tra dữ liệu |
| `POST /checkout` | 8% | Đọc cart, script điều kiện, ghi sự kiện |

Các tỷ lệ là ví dụ, không phải profile mặc định. Nếu chỉ test endpoint cache hit dễ nhất, báo cáo sẽ đánh giá thiếu tải DB, Redis write và tail latency của những endpoint hiếm nhưng nặng.

### Công cụ tạo tải có thể lựa chọn

- **`redis-benchmark`:** baseline command đơn giản.
- **`memtier_benchmark`:** đo tải Redis với client và tùy chọn workload hỗn hợp theo khả năng công cụ/phiên bản; cần xác nhận cách tạo key, ratio, data size và pipeline để diễn giải đúng.
- **JMeter, k6, Gatling hoặc công cụ HTTP tương đương:** kiểm tra API đầu-cuối, arrival pattern, response và SLO.
- **Harness Spring tùy biến:** kiểm tra chuỗi command đặc thù như GET → HGETALL → EVAL → SET EX mà công cụ command generic không mô tả đủ.

Chọn công cụ theo câu hỏi nghiên cứu, không theo mức độ “đẹp” của một con số throughput. Hai công cụ sử dụng mô hình phát tải khác nhau có thể cho p99 khác nhau dù thử cùng hệ thống.

## 14. Thread, connection, pipeline và Reactive Redis

Spring Data Redis không chỉ có một kiểu client. `RedisTemplate` đồng bộ và `ReactiveRedisTemplate` có mô hình thực thi khác nhau; Lettuce/Jedis cũng có cách quản lý connection, command queue và threading khác.

### 14.1. Đồng bộ với `RedisTemplate`

Một worker thread gọi:

~~~java
String value = redis.opsForValue().get(key);
~~~

Thread chờ kết quả trước khi tiếp tục. Nếu số thread đồng thời tăng mà Redis operation mất thời gian, ứng dụng có thể tạo nhiều thread chờ hoặc áp lực lên connection/pool. Tuy nhiên, số thread không tự bằng số TCP connection: cách chia sẻ và pool connection phụ thuộc driver/configuration.

### 14.2. Reactive với `ReactiveRedisTemplate`

Một pipeline:

~~~java
Flux<String> values = Flux.fromIterable(ids)
    .flatMap(
        id -> reactiveRedis.opsForValue().get("cache:product:" + id),
        16
    );
~~~

`flatMap(..., 16)` giới hạn số inner publisher đang hoạt động **trong pipeline đó**. Nó có thể giúp sử dụng non-blocking I/O tốt hơn, nhưng không bảo đảm hệ thống xử lý nhanh hơn trong mọi profile. Nếu Redis server/network đã bão hòa, tăng concurrency chỉ làm tăng queue, latency và timeout.

Khi so sánh đồng bộ và reactive:

- Giữ **cùng command mix, keyspace, payload, hit/miss và TTL**.
- So latency ở cả đầu-cuối và Redis operation.
- Đo CPU, thread count, heap, GC và mức in-flight.
- Không đặt `block()` trong event-loop khi benchmark reactive.
- Không so 20 synchronous worker với một reactive pipeline không giới hạn concurrency rồi kết luận về API framework.

### 14.3. Pipeline thay đổi số round trip

Nếu có nhiều lệnh Redis độc lập, pipeline có thể giảm round trip:

~~~text
Không pipeline:

SEND GET A → WAIT → SEND GET B → WAIT → SEND GET C → WAIT

Pipeline:

SEND GET A, GET B, GET C → nhận các phản hồi
~~~

Một phép so sánh phải ghi rõ:

- Batch size `P` hoặc số command mỗi pipeline.
- Kích thước tổng request/response.
- Redis connection và cách driver flush command.
- Bộ nhớ được dùng để giữ lệnh/response đang chờ.
- Latency **mỗi batch** và latency **mỗi operation**; không nhầm hai đơn vị.

Pipeline không mặc định biến nhiều lệnh thành một transaction. Nếu command B phụ thuộc kết quả của command A, không thể áp dụng pipeline như đối với hai lệnh độc lập mà vẫn giữ nguyên semantics.

### 14.4. Batch quá lớn không luôn tốt

Nếu pipeline 10.000 command trong một lượt, có thể tăng throughput theo command/giây nhưng cũng:

- Làm tăng kích thước buffer.
- Khiến một batch có tail latency lớn.
- Tăng thời gian giữ dữ liệu trong memory.
- Làm các request ngắn khác bị ảnh hưởng.
- Tạo đỉnh network traffic và memory allocation.

Nên thử nhiều batch size hữu hạn trong cùng workload: chẳng hạn 1, 8, 32, 128. Không có một giá trị tối ưu tuyệt đối cho mọi topology hoặc kích thước payload.

## 15. Đo từ cả ứng dụng và Redis server

Để tìm bottleneck, cần quan sát cả hai bên kết nối.

### 15.1. Phía Spring Boot/JVM

Các chỉ số nên có:

| Nhóm | Chỉ số |
| --- | --- |
| HTTP/API | Requests, success/error rate, p50/p95/p99, timeouts |
| Redis client | Command latency, reconnect count, command timeout, queue/pool wait |
| Workload | GET hit/miss, SET count, Hash/Set/Stream operation mix |
| Runtime | JVM CPU, heap usage, allocation rate, GC pause, thread count |
| Concurrency | Active request, queued task, rejection, reactive in-flight |
| Fallback | DB query rate khi cache miss, upstream latency, circuit-breaker status |

Nếu đã bật Micrometer/Actuator, có thể xuất những metric phù hợp và tự instrument business operation còn thiếu. Không giả định mọi chỉ số Redis client hoặc per-command histogram có sẵn chỉ nhờ thêm một starter: phạm vi instrument phụ thuộc Spring Boot, driver và configuration.

### 15.2. Phía Redis

Lệnh quan sát hữu ích trong môi trường được phép:

~~~bash
redis-cli -h redis.internal -p 6379 INFO stats
redis-cli -h redis.internal -p 6379 INFO commandstats
redis-cli -h redis.internal -p 6379 INFO memory
redis-cli -h redis.internal -p 6379 INFO clients
redis-cli -h redis.internal -p 6379 INFO cpu
redis-cli -h redis.internal -p 6379 SLOWLOG GET 10
redis-cli -h redis.internal -p 6379 LATENCY LATEST
~~~

Các trường đáng theo dõi gồm:

- `instantaneous_ops_per_sec` và tổng số command đã xử lý, với cách diễn giải phù hợp sampling interval.
- Keyspace hits/misses, expired keys và evicted keys.
- `used_memory`, `used_memory_peak`, fragmentation và memory policy.
- `connected_clients`, blocked clients, output buffer pressure.
- Commandstats theo loại lệnh: số lượt, thời gian thực thi tích lũy, mức lỗi nếu phiên bản Redis cung cấp.
- Slow log và latency events nếu đã cấu hình ngưỡng thích hợp.

`SLOWLOG` tập trung vào thời gian Redis xử lý command và không phản ánh đầy đủ mạng, serialization hoặc thời gian đợi connection ở client. Nếu ứng dụng thấy p99 Redis operation cao nhưng Redis server execution time thấp, hãy điều tra các lớp bên ngoài command execution.

Không dùng `MONITOR` liên tục trên production để đo tải; nó có thể tạo overhead lớn và phát lộ command arguments. Không dump payload nhạy cảm từ SLOWLOG sang báo cáo công khai.

### 15.3. Với Redis Sentinel hoặc Cluster

Trong Sentinel, cần xem primary/replica role và replication lag; benchmark đọc replica có thể khác về tính nhất quán lẫn latency. Trong Redis Cluster, lấy metric **từng shard**, không chỉ trung bình toàn cluster:

~~~text
Cluster tổng CPU trung bình: 45%

Shard A CPU: 95%   ← hot key / hot slot
Shard B CPU: 20%
Shard C CPU: 20%
~~~

Một giá trị trung bình “45%” có thể che shard A quá tải. Hãy xem phân bố hash slot, key popularity, kích thước key và command mix trên từng node khi đánh giá khả năng scale.

## 16. Thiết kế một chuỗi thí nghiệm có thể so sánh

Một phép thử đơn lẻ dễ dẫn tới kết luận quá tự tin. Nên tổ chức từng giai đoạn:

1. **Baseline:** kiểm tra hạ tầng Redis và lệnh đơn giản trong điều kiện chuẩn; ghi cấu hình và version.

2. **Seed:** tạo dữ liệu đúng keyspace, payload, TTL và loại cấu trúc dữ liệu; xác minh không có eviction ngoài dự kiến.

3. **Warm-up:** cho JVM/JIT, connection, cache và Redis đi vào trạng thái gần ổn định. Tách dữ liệu warm-up khỏi báo cáo chính.

4. **Ramp-up:** tăng tải qua từng mức, ví dụ 10, 25, 50, 75, 100% mục tiêu.

5. **Steady-state:** giữ một mức tải đủ lâu để quan sát latency, throughput, resource và error.

6. **Burst:** thử peak ngắn, một đợt nhiều key hết hạn hoặc cache miss tăng.

7. **Soak:** giữ tải lâu để thấy GC, leak, memory growth, pool exhaustion hoặc eviction.

8. **Recovery:** giảm tải về bình thường và xem backlog/error/latency phục hồi hay không.

9. **Repeat:** chạy lại các profile với thứ tự hoặc random seed đã ghi, đối chiếu độ biến động giữa những lần đo.

Trong cùng một vòng so sánh, hãy hạn chế thay **nhiều biến đồng thời**. Ví dụ, nếu đổi từ Jedis sang Lettuce, đồng thời tăng pool size, thêm pipeline và đổi serializer thì việc throughput tăng không cho biết nguyên nhân chính.

### Mẫu bảng kết quả

| Profile | Offered RPS | Success RPS | Error % | p50 | p95 | p99 | Redis CPU | JVM GC pause |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A / low | 500 | 500 | 0 | 4 ms | 11 ms | 18 ms | 23% | 2 ms |
| A / mid | 1.000 | 996 | 0,4 | 6 ms | 23 ms | 55 ms | 52% | 4 ms |
| A / peak | 1.500 | 1.400 | 6,7 | 12 ms | 100 ms | 350 ms | 89% | 20 ms |

**Toàn bộ số trong bảng chỉ là dữ liệu giả định để minh họa cách báo cáo**, không phải kết quả đo của Redis hoặc Spring Data Redis trong một môi trường cụ thể.

Một báo cáo thực tế nên bổ sung số operation theo loại, tỷ lệ hit/miss, payload distribution, network throughput, connection utilization, hash slot/shard và cấu hình tải. Chỉ như vậy mới so được hai lần đo với nhau.

### So sánh phải có độ tin cậy

Nếu kết quả p99 lần 1 là 25 ms và lần 2 là 23 ms, chưa đủ để tuyên bố “tối ưu thành công 8%” khi test có thể biến động 10–20% theo GC, load generator hoặc network. Hãy:

- Chạy nhiều lượt độc lập.
- So cùng workload profile và cùng điều kiện hạ tầng.
- Ghi phân bố kết quả giữa các lượt (median, min/max hoặc interval phù hợp).
- Phân biệt thay đổi lớn có ý nghĩa với dao động ngẫu nhiên.
- Đo thêm CPU/memory/queue để giải thích vì sao cải thiện xảy ra.

Đặc biệt, **một giá trị p99 tính trên quá ít mẫu** không ổn định. Nếu cần đánh giá tail latency, lấy đủ lượng request và thời gian quan sát; không chỉ dùng vài trăm lệnh.

## 17. Đọc kết quả để tìm đúng bottleneck

Nhìn vào **mẫu nhiều metric** thay vì chỉ một con số:

| Dấu hiệu | Giả thuyết có thể | Việc cần kiểm tra |
| --- | --- | --- |
| Redis CPU cao, command latency tăng | Redis server bị giới hạn CPU hoặc command nặng | Command mix, slow log, script, big key |
| Redis CPU thấp, application p99 cao | Client queue, network, serializer hoặc dependency khác | Pool wait, JVM CPU/GC, network, API tracing |
| RPS không tăng dù tăng worker | Đã chạm giới hạn xử lý hoặc queueing | Achieved throughput, inflight, latency, thread/pool saturation |
| Hit ratio giảm, DB QPS tăng | TTL/eviction/cache miss thay đổi | Expired/evicted keys, cache fill, hot key |
| Lỗi timeout tăng khi burst | Queue/backpressure/connection limits | Arrival profile, pool, command timeout, overload protection |
| Một node Cluster p99 rất cao | Hot shard, skew hoặc key lớn | Slot distribution, key popularity, node-level metrics |
| p99 tăng theo kích thước payload | Network/serialization/GC | Bytes in/out, allocation, response size |
| Pipeline tăng ops/s nhưng API chậm hơn | Batch quá lớn, head-of-line effects hoặc memory | Batch latency, queues, peak memory |
| Retry làm traffic Redis tăng mạnh | Retry amplification trong lúc lỗi | Retry attempt metrics, backoff, idempotency |
| TTL burst gây error ở API | Cache stampede lên database | Miss cohort, single-flight, fallback saturation |

Mỗi giả thuyết nên dẫn tới một thí nghiệm **thay đổi một yếu tố** và đo lại profile giống nhau. Ví dụ, nếu nghi serializer:

~~~text
Run A: StringRedisTemplate với payload 1 KB
Run B: RedisTemplate với JSON DTO có byte size tương đương

Giữ nguyên key distribution, offered load và Redis topology.
Đo JVM CPU, allocation, GC và end-to-end latency.
~~~

Nếu nghi round trip:

~~~text
Run A: 5 GET độc lập theo thứ tự
Run B: MGET tương đương khi keys phù hợp
Run C: pipeline 5 GET độc lập

Giữ nguyên số key, bytes trả về và mức arrival load.
Đánh giá sự khác nhau về semantics, đặc biệt trên Cluster.
~~~

Không tối ưu mù dựa trên câu “Redis là in-memory nên chắc chắn không chậm”. Redis cũng bị giới hạn CPU, network, memory bandwidth, command complexity và topology.

## 18. Những sai lầm làm benchmark thiếu giá trị

| Sai lầm | Vì sao kết luận có thể sai? | Cách khắc phục |
| --- | --- | --- |
| Chỉ đo một `GET` với payload nhỏ | Không phản ánh mix command, serialization hoặc cache miss | Dựng nhiều profile và đo cả business flow |
| Dùng 100 key lặp đi lặp lại | Hit ratio và working set quá dễ | Keyspace đủ lớn, popularity có phân bố |
| Chọn key hoàn toàn uniform | Che hot key/hot shard | Thử hotset/Zipf-like/tenant-specific profile |
| Chỉ báo requests/second | Không thấy p99 và error | Kèm percentiles, success/error, in-flight |
| Tăng số worker rồi gọi đó là RPS | Closed-loop tự giảm arrival khi chậm | Báo offered và achieved load; dùng open-loop khi cần |
| Chỉ tính latency của request thành công | Timeout/rejection bị bỏ khỏi mẫu | Thống kê lỗi và timeout riêng, công bố chính sách histogram |
| Không warm-up JVM hoặc connection | JIT, DNS và tạo connection làm méo phép thử | Warm-up riêng, ghi rõ cold-start nếu đó là mục tiêu |
| Seed dữ liệu trong cửa sổ đo | Tải chuẩn bị làm thay đổi operation mix | Seed trước khi đo steady-state |
| Benchmark luôn cache hit | Bỏ qua DB fallback và cache stampede | Có miss ratio/expiration profile |
| Không mô phỏng TTL | Bỏ qua expired keys và tái tạo cache | Dùng TTL distribution, kiểm tra TTL burst |
| Chỉ nhìn CPU Redis trung bình cả Cluster | Có thể có một shard quá tải | Xem metric mỗi node/slot |
| So batch pipeline với single command nhưng chỉ đo số batch | Khác đơn vị đo | Báo cả batch/s, command/s, latency batch |
| Cùng lúc đổi serializer, pool và pipeline | Không biết cải thiện do đâu | Thử một biến tại một thời điểm |
| Test client ở máy rất mạnh, Redis ở localhost | Không phản ánh RTT/cross-zone/TLS thực | Đặt load generator/topology gần môi trường mục tiêu |
| Load generator chạy hết CPU | Tốc độ tải thực thấp hơn lịch phát | Đo CPU, backlog, dropped schedules của generator |
| Dữ liệu thật bị copy vào test | Rủi ro bảo mật và privacy | Dùng metadata ẩn danh, payload giả có phân bố tương tự |
| Benchmark trên Redis production dùng chung | Có thể gây eviction, timeout hoặc tác động khách hàng | Dùng test/staging riêng, giới hạn tải và namespace |
| Coi microbenchmark là SLA sản phẩm | Không có HTTP, DB, queue, serializer, auth | Kiểm thử end-to-end theo SLO |
| Kết luận từ một lần đo | Jitter, GC và network ngẫu nhiên | Lặp lại, ghi phân bố giữa các run |
| Retry được bật nhưng không tính vào tải | Một request logic có thể gửi nhiều Redis command | Đo retry amplification và command count |

### Một phép thử nhanh không đồng nghĩa hệ thống đủ năng lực

Giả sử `redis-benchmark` cho kết quả vượt mục tiêu ops/s, nhưng request thật cần ba lượt Redis và một DB fallback khi miss. Khi tới giờ cao điểm, hiệu năng có thể bị quyết định bởi DB pool, kết nối giữa availability zones, mức tải serializer hoặc thời gian chờ queue.

Vì vậy, câu hỏi đúng không phải “Redis chạy được bao nhiêu GET/giây?” mà là:

> Với phân bố request, key, dữ liệu và sự cố phù hợp thực tế, hệ thống có duy trì được **success rate, throughput và p99 latency** đã cam kết hay không?

## 19. Đặt tiêu chí đánh giá bằng SLO

Để benchmark có thể dẫn đến một quyết định, cần xác định trước **ngưỡng chấp nhận**. Ví dụ giả định cho API cache-backed:

~~~text
Profile: Product Read Peak v3
Offered load: 1.200 request/giây trong 15 phút
Success rate: >= 99,9%
End-to-end p95: <= 80 ms
End-to-end p99: <= 150 ms
Không có Redis eviction ngoài chính sách đã dự kiến
Database fallback không vượt ngưỡng an toàn
Tải giảm xuống bình thường thì backlog phải phục hồi
~~~

Các số này **chỉ dùng để minh họa cách đặt SLO**, không phải mức đạt được hay tiêu chuẩn chung của Spring Data Redis.

Một quyết định capacity nên quan tâm:

1. Tải đại diện mà hệ thống chịu được trong thời gian dài là bao nhiêu?
2. Có **headroom** cho tăng trưởng, burst và failover không?
3. Khi một Redis node hoặc application instance mất, phần còn lại có đáp ứng mức degraded SLO chấp nhận được không?
4. Khi latency vượt ngưỡng, lỗi xuất hiện ở tầng Redis, driver, JVM, network hay dependency khác?
5. Thay đổi tối ưu hóa có làm sai semantics nghiệp vụ như TTL, read consistency, ordering hoặc transaction không?

Nếu chỉ tối ưu để tăng ops/s nhưng làm xấu p99 hoặc gây nhiều retry/write duplicate hơn, đó không nhất thiết là một cải thiện thực.

### Xây capacity margin có lý do

Giả sử một profile đạt SLO ở offered load 1.500 request/giây trong staging. Đừng mặc định production có thể an toàn chạy liên tục đúng mức 1.500 RPS. Còn nhiều yếu tố biến đổi:

- Mẫu truy cập production thay đổi theo giờ.
- Dữ liệu/keyspace tăng theo thời gian.
- Một số request dùng payload lớn hơn.
- Failover làm giảm số replica/shard phục vụ trong một khoảng.
- Log, tracing, backups, persistence và tác vụ nền cùng dùng CPU/network.
- Hệ thống bên ngoài Redis đôi khi chậm hơn bình thường.

Chọn headroom dựa trên risk assessment và những thử nghiệm burst/soak/failover, thay vì lấy một tỷ lệ cố định áp dụng cho mọi hệ thống.

## 20. Checklist chuẩn bị một phép đo tải có thể tái lập

Trước khi bắt đầu, hãy trả lời những câu hỏi dưới đây trong test plan.

**Workload**

- Có mô tả operation mix theo số lượt **command** và theo số lượt **request nghiệp vụ** không?
- Keyspace, hotset, hit/miss, payload P50/P95/P99 và TTL đã được ghi rõ chưa?
- Có phân biệt read primary và read replica, cũng như topology Redis không?
- Có mô phỏng dependency giữa các command và nhánh cache miss không?
- Retry, timeout, cache rebuild và background jobs có nằm trong phạm vi thử không?

**Hạ tầng và bộ phát tải**

- Phiên bản Redis, Spring Data Redis, driver, cấu hình serialization và pool/timeout đã được ghi lại chưa?
- Load generator có đủ CPU/network, không tự trở thành bottleneck không?
- Mô hình open-loop/closed-loop và arrival schedule đã được xác định chưa?
- Có namespace benchmark riêng, TTL/cleanup và giới hạn bộ nhớ để không đụng production không?
- Có thiết kế warm-up, ramp, steady-state, burst, soak và repeat chưa?

**Đo lường**

- Có offered RPS, successful RPS, error rate, latency p50/p95/p99 và in-flight không?
- Có metric Redis commandstats, memory, eviction, hit/miss và từng shard không?
- Có metric JVM CPU, heap/GC, connection wait và database fallback không?
- Có theo dõi các request timeout, bị hủy hoặc bị từ chối không?
- Có thể truy vết một request chậm qua service, Redis operation và dependency khác không?

**Đánh giá**

- SLO cần đạt đã được xác định **trước** khi xem kết quả chưa?
- Các lần so sánh có giữ cố định profile và điều kiện môi trường không?
- Có đủ nhiều mẫu và số lượt chạy để nhận biết biến động không?
- Kết luận có phân biệt **thực tế đã đo** với **giả thuyết bottleneck** không?
- Những thay đổi như pipeline, batch, serializer hay replica reads có giữ nguyên semantics nghiệp vụ không?

Danh sách này giúp bài test trả lời câu hỏi capacity thay vì tạo một bảng số nhiều chữ số nhưng thiếu bối cảnh.

## 21. Quy trình áp dụng cho một dự án Spring Data Redis

Một nhóm phát triển có thể thực hiện theo đường đi sau:

~~~text
                  Production metrics / tracing
                               |
                               v
                Mô tả access pattern thực tế
             command mix / key / payload / TTL
                               |
                               v
                   Định nghĩa workload profile
                               |
                               v
                 Seed dữ liệu ở staging riêng
                               |
                               v
                     Warm-up và ramp-up
                               |
                               v
             Closed-loop + open-loop khi phù hợp
                               |
                               v
             Đo throughput / errors / p95 / p99
                     /                 \
                    v                   v
           Spring/JVM metrics       Redis/node metrics
                    \                   /
                     +--------+--------+
                              |
                              v
                    Xác định bottleneck
                              |
                              v
                     Thay một yếu tố
                              |
                              v
                    Chạy lại cùng profile
                              |
                              v
                   So sánh với SLO và rủi ro
~~~

Ví dụ một vòng tối ưu hóa có thể diễn ra như sau:

**Giả thuyết:** API đọc sản phẩm có p99 cao vì nhiều key Redis được GET nối tiếp qua mạng.

**Phép thử:** so sánh bản hiện tại với phiên bản gom những lượt đọc **thực sự độc lập** thành batch/pipeline; giữ cùng traffic, keyspace, payload, hit/miss và Redis topology.

**Quan sát:** đo thời gian Redis operation, network round trips, p99 HTTP và bộ nhớ/connection ở cả hai phiên bản.

**Kết luận:** chỉ chấp nhận thay đổi nếu cải thiện được SLO mà không làm hỏng yêu cầu đọc nhất quán, TTL, semantics khi lệnh thất bại hoặc thứ tự phụ thuộc dữ liệu.

Trong một trường hợp khác, phép đo có thể chỉ ra **cache stampede** khi TTL hết hạn, khiến DB quá tải. Khi ấy tối ưu `GET` chưa chắc giúp nhiều; can thiệp phù hợp hơn có thể là TTL jitter, single-flight, giới hạn cache rebuild hoặc tối ưu query nguồn.

## 22. Tổng kết

Benchmark một lệnh như `GET` hoặc `SET` hữu ích để đo baseline, nhưng **hiệu năng của ứng dụng Spring Data Redis bị quyết định bởi mẫu truy cập toàn hệ thống**, bao gồm command mix, phân bố key, kích thước dữ liệu, tỷ lệ cache miss, TTL, concurrency, serialization, network, topology và dependency khác.

Một bài đo tải đáng tin cậy cần:

1. **Định nghĩa workload từ dữ liệu quan sát được**, không dựa vào một mix lệnh tùy ý rồi coi đó là production.
2. **Seed và phát tải có kiểm soát**, phân biệt warm-up, steady-state, burst, soak và mô hình closed-loop/open-loop.
3. **Đo nhiều chiều**, gồm offered load, throughput thành công, lỗi/timeout, p50/p95/p99, Redis server, driver và JVM.
4. **Giữ nguyên ngữ nghĩa nghiệp vụ** khi thử pipeline, batch, serializer, read replica hoặc retry.
5. **So sánh với SLO và lặp lại thí nghiệm**, thay vì công bố một con số ops/s cao nhất rồi coi là đủ.

Kết quả tốt nhất không phải “Redis đạt nhiều lệnh mỗi giây nhất” mà là **ứng dụng đáp ứng được traffic đại diện với độ trễ, độ tin cậy và chi phí tài nguyên nằm trong giới hạn chấp nhận được**. Khi đo theo access pattern, nhóm phát triển mới có đủ dữ liệu để quyết định nên tối ưu Redis command, Spring Data Redis client, cache strategy, network hay chính business workflow.
