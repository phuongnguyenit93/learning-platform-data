# Đo tải thực tế và tránh suy luận rằng không chặn luôn nhanh hơn

Spring Data R2DBC và Spring WebFlux cho phép xây dựng ứng dụng truy cập database theo mô hình reactive, non-blocking. Mô hình này có thể giúp ứng dụng phục vụ nhiều request đang chờ I/O với ít thread hơn và sử dụng tài nguyên hiệu quả hơn. Tuy nhiên, **non-blocking không đồng nghĩa với mỗi request chạy nhanh hơn, SQL nhanh hơn hoặc hệ thống luôn có throughput cao hơn JDBC**.

Hiệu năng phải được đo trên workload gần với production. Một truy vấn có thể mất 20 ms ở cả JDBC và R2DBC; khác biệt có thể nằm ở số thread cần để phục vụ 1.000 request đồng thời, chi phí scheduler, connection pool, serialization hoặc mức bão hòa của database. Nếu database đã là nút thắt, đổi sang non-blocking không làm database xử lý thêm được nhiều câu SQL hơn.

Bài học này trình bày cách thiết kế phép đo, đọc các chỉ số latency/throughput, nhận diện giới hạn của R2DBC, so sánh công bằng với JDBC và tránh các kết luận chỉ dựa trên một benchmark nhỏ.

## 1. Non-blocking thay đổi cách chờ I/O, không tự làm I/O nhanh hơn

Trong mô hình blocking truyền thống, một thread thường bị giữ trong lúc chờ database trả kết quả:

~~~text
Request A -> Thread A -> gửi SQL -> chờ database -> nhận kết quả -> trả response
                                      |
                                      +-- Thread A đang bị giữ
~~~

Với non-blocking reactive I/O, thread không phải đứng chờ theo cách đó. Khi database chưa trả dữ liệu, pipeline có thể nhường quyền thực thi để event loop xử lý công việc khác:

~~~text
Request A -> event loop -> gửi SQL -> đăng ký tiếp tục khi có kết quả
                                      |
                                      +-- event loop xử lý request B/C

Database response -> tiếp tục pipeline A -> trả response
~~~

Lợi ích chính nằm ở việc sử dụng thread và tài nguyên hiệu quả khi có nhiều thao tác I/O đang chờ. Thời gian database thực thi câu SQL vẫn phụ thuộc vào query plan, index, lock, CPU, disk, network và tải của database.

### 1.1. Ba khái niệm không nên đánh đồng

| Khái niệm | Câu hỏi nó trả lời |
| --- | --- |
| Latency | Một request mất bao lâu từ lúc bắt đầu đến khi có kết quả? |
| Throughput | Hệ thống hoàn thành được bao nhiêu request hoặc transaction trong một đơn vị thời gian? |
| Resource efficiency | Để đạt throughput/latency đó, hệ thống tiêu thụ bao nhiêu CPU, memory, thread, connection và network? |

Non-blocking có thể cải thiện resource efficiency hoặc khả năng chịu concurrency mà không làm latency của một query giảm. Ngược lại, một pipeline reactive có thể tăng overhead và chạy chậm hơn một đường blocking đơn giản ở tải thấp.

### 1.2. Một truy vấn nhanh hơn không có nghĩa hệ thống nhanh hơn

Giả sử hai implementation cùng trả một danh sách order:

- JDBC: latency p50 là 18 ms, p95 là 45 ms.
- R2DBC: latency p50 là 19 ms, p95 là 43 ms.

Các con số này gần nhau. Nếu R2DBC dùng ít thread hơn đáng kể ở mức 1.000 request đồng thời, nó có thể đem lại lợi ích về khả năng mở rộng và tài nguyên. Nhưng không thể kết luận R2DBC làm truy vấn nhanh hơn chỉ từ hai con số p50/p95 này.

Một benchmark khác có thể cho kết quả ngược lại nếu query rất ngắn, tải thấp và chi phí reactive pipeline chiếm tỷ trọng lớn.

## 2. Đo đúng những chỉ số cần thiết

Không nên chỉ nhìn thời gian trung bình hoặc số request mỗi giây. Một báo cáo hiệu năng nên có ít nhất:

- **Throughput:** request/second hoặc transaction/second đã hoàn thành.
- **Latency percentiles:** p50, p90, p95, p99 và khi cần p99.9.
- **Error rate:** tỷ lệ timeout, HTTP 5xx, lỗi database, connection acquire timeout và request bị từ chối.
- **Concurrency:** số request đang hoạt động và số request đang chờ.
- **Resource usage:** CPU, heap, garbage collection, thread, connection, network và I/O.
- **Database health:** CPU, memory, disk IOPS, lock wait, active sessions, query latency và slow query.

### 2.1. Vì sao cần p95 và p99?

Average có thể che giấu một nhóm request rất chậm. Ví dụ 99 request mất 20 ms nhưng một request mất 2 giây. Average của 100 request vẫn có vẻ thấp, trong khi người dùng của request chậm có trải nghiệm rất tệ.

Các percentile có ý nghĩa:

- p50: một nửa request nhanh hơn hoặc bằng giá trị này.
- p95: 95% request nhanh hơn hoặc bằng giá trị này.
- p99: 99% request nhanh hơn hoặc bằng giá trị này.

Với API tương tác, p95/p99 thường hữu ích hơn average để nhìn tail latency. Cần dùng histogram hoặc dữ liệu đủ chi tiết; không tính percentile bằng cách lấy trung bình các percentile từ nhiều instance.

### 2.2. Throughput phải đi cùng error rate

Một hệ thống có thể báo throughput cao vì nhanh chóng trả lỗi hoặc từ chối request. Chỉ tính request thành công nếu mục tiêu là đo năng lực xử lý nghiệp vụ.

Ví dụ:

| Kết quả | Request/second |
| --- | ---: |
| Tổng request nhận vào | 1.000 |
| Thành công | 820 |
| Timeout hoặc lỗi | 180 |

Nếu chỉ báo 1.000 request/second, benchmark có thể tạo ấn tượng sai rằng hệ thống phục vụ được 1.000 request thành công mỗi giây.

### 2.3. Đo latency ở đúng ranh giới

Một API end-to-end có thể gồm:

1. Nhận request và xác thực.
2. Parse/validate request.
3. Chờ connection pool cấp connection.
4. Gửi SQL và chờ database.
5. Mapping row thành entity/DTO.
6. Gọi service phụ thuộc.
7. Serialize response và gửi qua network.

Nếu chỉ đo thời gian query ở repository, ta không thấy connection acquisition, serialization hoặc downstream call. Nếu chỉ đo HTTP latency, ta không biết phần nào là bottleneck.

Nên có cả metric end-to-end và metric từng thành phần. Distributed tracing hoặc observation có thể giúp phân tách thời gian, nhưng instrumentation cũng có overhead và cần được cấu hình nhất quán giữa các lần so sánh.

## 3. Thiết kế workload gần production

Một benchmark chỉ có giá trị khi workload phản ánh cách hệ thống được sử dụng. Cần xác định:

- Tỷ lệ đọc/ghi và loại query.
- Kích thước request/response.
- Số hàng được đọc hoặc cập nhật.
- Phân bố tenant, user và khóa truy cập.
- Tỷ lệ cache hit/miss.
- Số transaction và số statement trong một transaction.
- Số request đến đồng thời và tốc độ request mới đến.
- Tần suất burst và thời gian tải kéo dài.
- Các lời gọi HTTP/message phụ thuộc nếu có.

### 3.1. Đừng chỉ benchmark một câu SELECT đơn giản

Ví dụ một repository query:

~~~java
public Mono<Customer> findById(Long id) {
    return customerRepository.findById(id);
}
~~~

Đây có thể là benchmark hữu ích cho một primitive, nhưng chưa đại diện cho endpoint thật nếu production còn kiểm tra quyền truy cập, lọc theo tenant, join nhiều bảng, phân trang, mapping DTO, ghi audit hoặc gọi thêm service khác.

Hãy giữ một benchmark nhỏ để hiểu chi phí từng thành phần và một benchmark end-to-end để đánh giá hành vi thực tế.

### 3.2. Dùng dữ liệu có phân bố thực tế

Một bảng chỉ có 100 hàng dễ nằm hoàn toàn trong cache và không phản ánh production có hàng chục triệu hàng. Dữ liệu benchmark nên gần với:

- Tổng số hàng và kích thước index.
- Tỷ lệ giá trị trùng lặp.
- Phân bố hot key và cold key.
- Kích thước payload.
- Tỷ lệ hàng bị lọc.
- Độ lệch dữ liệu giữa tenant nhỏ và tenant lớn.

Nếu production có một số tenant rất lớn, test chỉ với tenant nhỏ có thể bỏ qua vấn đề index, query plan hoặc noisy neighbor.

### 3.3. Giữ query và semantics tương đương khi so sánh

Khi so sánh JDBC với R2DBC, cả hai implementation cần thực hiện cùng công việc:

- Cùng SQL hoặc query logic tương đương.
- Cùng schema, index, dữ liệu và database instance.
- Cùng transaction boundary và isolation level.
- Cùng số hàng và payload trả về.
- Cùng quy tắc mapping, validation và business logic.
- Cùng timeout, retry và connection limits.
- Cùng điều kiện cache và network.

Nếu một bên chỉ đọc một cột còn bên kia map cả entity, kết quả không phải phép so sánh công bằng.

## 4. Mô hình tải: closed workload và open workload

Cách tạo tải ảnh hưởng mạnh đến kết quả benchmark.

### 4.1. Closed workload

Closed workload thường có một số lượng virtual users cố định. Mỗi user gửi request, chờ response, nghỉ một khoảng rồi gửi request tiếp theo.

~~~text
User 1: request -> wait response -> think -> request -> ...
User 2: request -> wait response -> think -> request -> ...
...
User N: request -> wait response -> think -> request -> ...
~~~

Khi server chậm, tốc độ gửi request tự giảm vì virtual user đang chờ. Điều này có thể che giấu hiện tượng quá tải: hệ thống chậm khiến load generator cũng gửi ít request hơn.

Closed workload phù hợp với một số kịch bản người dùng tương tác, nhưng không mô phỏng tốt một nguồn traffic đến liên tục ở tốc độ độc lập với latency.

### 4.2. Open workload

Open workload tạo request theo tốc độ đến được định trước, ví dụ 200 request mỗi giây, bất kể response trước đó đã hoàn tất hay chưa.

~~~text
Arrival schedule: 200 requests/second
       |
       +--> request A đang chờ
       +--> request B đang chờ
       +--> request C bắt đầu
       +--> request D bắt đầu
~~~

Mô hình này hữu ích khi muốn biết hệ thống chịu được tốc độ traffic nào trước khi latency, queue và error tăng mạnh. Nếu server không theo kịp, số request đang chờ hoặc số virtual user cần thiết sẽ tăng.

### 4.3. Coordinated omission

Một số load generator chỉ gửi request tiếp theo sau khi request trước hoàn tất. Khi server bị chậm, chính load generator giảm số request tạo ra và bỏ lỡ khoảng thời gian hệ thống đáng lẽ phải tiếp tục nhận traffic.

Hiện tượng này có thể làm latency histogram trông đẹp hơn thực tế, vì các request không được gửi trong lúc server đang chậm không xuất hiện trong phép đo.

Để đo capacity và tail latency dưới tải đến liên tục, cân nhắc open workload/constant arrival rate và kiểm tra metric dropped iterations hoặc request không được phát đúng lịch. Đừng chỉ nhìn latency của những request đã được gửi thành công.

## 5. Little's Law và mối quan hệ giữa concurrency, throughput, latency

Little's Law mô tả quan hệ trong một hệ thống ổn định:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số request trung bình đang ở trong hệ thống.
- \(\lambda\): throughput trung bình, request mỗi giây.
- \(W\): thời gian trung bình một request ở trong hệ thống, tính bằng giây.

Ví dụ, nếu hệ thống hoàn thành 200 request/second và latency trung bình là 0,1 giây:

\[
L = 200 \times 0.1 = 20
\]

Trung bình có khoảng 20 request đang được xử lý hoặc chờ trong hệ thống.

Little's Law giúp ước lượng concurrency cần thiết, nhưng không phải công thức dự đoán throughput tối đa. Khi hệ thống gần bão hòa, queueing delay có thể tăng rất nhanh và giả định ổn định không còn phù hợp.

### 5.1. Tăng concurrency không phải lúc nào cũng tăng throughput

Khi tăng số request đồng thời:

1. Database có thêm việc để xử lý.
2. CPU hoặc I/O có thể được sử dụng tốt hơn nếu trước đó còn nhàn rỗi.
3. Đến một mức nào đó, database bão hòa.
4. Request mới phải chờ connection, lock hoặc CPU.
5. Latency tăng nhanh trong khi throughput gần như không tăng.

Đây là lý do benchmark cần tìm điểm bão hòa thay vì chỉ tăng concurrency đến mức cao nhất.

## 6. Connection pool là một phần của phép đo

R2DBC thường dùng connection pool để tái sử dụng connection database. Pool size tác động tới số statement có thể sử dụng connection đồng thời, thời gian chờ acquire connection, số connection database đang hoạt động, tải lên database server và tài nguyên socket.

Pool lớn hơn không tự động tốt hơn. Nếu database chỉ xử lý hiệu quả 80 query đồng thời, mở 500 connection có thể làm lock contention, context switching và memory pressure tăng lên.

### 6.1. Phân biệt pool wait với query latency

Một request có thể mất 150 ms, trong đó:

| Thành phần | Thời gian |
| --- | ---: |
| Chờ acquire connection | 90 ms |
| Database thực thi query | 35 ms |
| Mapping và phần còn lại | 25 ms |

Nếu chỉ nhìn tổng latency, ta có thể đổ lỗi cho SQL. Nhưng phần lớn thời gian thực tế nằm ở connection pool.

Theo dõi các chỉ số:

- Acquired/active connections.
- Idle connections.
- Pending acquire requests.
- Acquire latency và timeout.
- Pool max size.
- Thời gian connection được giữ.

Tên metric cụ thể phụ thuộc pool, phiên bản Spring Boot và Micrometer integration đang dùng.

### 6.2. Tính tổng connection từ nhiều instance

Nếu ứng dụng chạy nhiều replica, giới hạn connection thực tế là tổng pool của tất cả replica:

\[
\text{Potential connections}
= \text{replicas} \times \text{pool max size}
\]

Ví dụ 6 replica, mỗi replica có max pool size 30:

\[
6 \times 30 = 180
\]

Database cần chịu được tối đa khoảng 180 connection từ ứng dụng, chưa tính worker, migration, monitoring và admin. Cần phân bổ giới hạn connection ở cấp toàn hệ thống.

### 6.3. Pool exhaustion

Nếu tất cả connection đều đang được giữ, request mới phải chờ. Nguyên nhân thường gặp:

- Pool quá nhỏ so với workload.
- Query hoặc transaction chạy lâu.
- Một publisher giữ connection trong lúc chờ service HTTP.
- Consumer đọc Flux rất chậm khiến result stream giữ tài nguyên lâu.
- Có blocking hoặc logic đồng bộ nằm trong transaction.
- Connection bị rò do lifecycle/subscription sai.

Đừng tăng pool ngay khi thấy acquire timeout. Trước tiên, đo thời gian giữ connection, query latency và database saturation để tìm nguyên nhân.

## 7. Backpressure và tốc độ tiêu thụ dữ liệu

Reactive Streams hỗ trợ backpressure: downstream có thể yêu cầu số phần tử mà nó sẵn sàng xử lý. Điều này giúp điều tiết luồng dữ liệu khi producer nhanh hơn consumer.

Ví dụ:

~~~java
public Flux<OrderSummary> streamOrders(Long customerId) {
    return orderRepository.findAllByCustomerId(customerId)
            .map(OrderSummary::from);
}
~~~

Nếu downstream tiêu thụ chậm, backpressure có thể giới hạn tốc độ phát phần tử ở những publisher hỗ trợ demand. Tuy nhiên, backpressure không làm query SQL nhanh hơn và không loại bỏ mọi loại queue trong hệ thống.

### 7.1. collectList có thể phá lợi ích streaming

~~~java
return orderRepository.findAllByStatus("OPEN")
        .collectList()
        .map(this::buildResponse);
~~~

collectList giữ toàn bộ phần tử trong memory trước khi phát kết quả. Với tập dữ liệu lớn, heap có thể tăng mạnh và garbage collection gây tail latency.

Nếu API cần trả danh sách lớn, cân nhắc pagination, giới hạn kết quả hoặc streaming response phù hợp. Streaming cũng có chi phí: connection/result cursor có thể được giữ lâu trong khi client nhận dữ liệu.

### 7.2. Giới hạn concurrency trong flatMap

~~~java
return orderRepository.findAllByStatus("READY")
        .flatMap(order -> inventoryClient.check(order.getId()), 16);
~~~

Tham số concurrency giới hạn số publisher con hoạt động đồng thời trong ví dụ này. Không nên mặc định tăng concurrency để tối đa hóa throughput; downstream service hoặc connection pool có thể bị quá tải.

Đo với nhiều mức concurrency và theo dõi latency, pending work, error rate và resource utilization.

### 7.3. Fetch size và streaming phụ thuộc driver

Hành vi fetch row theo batch, cursor và buffering có thể phụ thuộc R2DBC driver/database. Nếu ứng dụng đọc kết quả lớn, hãy đo số hàng mỗi lần fetch, memory tăng theo kích thước kết quả, thời gian giữ connection, ảnh hưởng của downstream chậm và cancellation khi client ngắt kết nối.

Không giả định mọi driver có cùng fetch-size semantics chỉ vì code dùng cùng Flux<T>.

## 8. Thread và scheduler trong ứng dụng reactive

WebFlux thường chạy trên event loop. Event-loop thread cần được giải phóng nhanh để xử lý nhiều connection/request.

### 8.1. Blocking call có thể phá hỏng mô hình non-blocking

Tránh gọi API blocking trong event loop:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return Mono.fromCallable(() -> blockingCustomerClient.fetch(id));
}
~~~

Đoạn code trên vẫn blocking thread thực hiện callable. Mono không tự biến một API blocking thành non-blocking.

Nếu chưa thể thay thế thư viện blocking, có thể cô lập công việc trên scheduler phù hợp:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return Mono.fromCallable(() -> blockingCustomerClient.fetch(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây là cách cô lập blocking work, không phải biến nó thành non-blocking. Scheduler có giới hạn tài nguyên và cần được theo dõi.

### 8.2. Không chuyển mọi thao tác sang boundedElastic

R2DBC driver non-blocking không cần bọc mỗi repository call trong subscribeOn(boundedElastic()). Làm vậy có thể thêm queue/scheduler overhead và làm mất lợi ích của event-loop model.

Dùng scheduler cho công việc cần thiết như API blocking legacy, file I/O blocking, thư viện không có reactive API hoặc công việc CPU-bound cần scheduler phù hợp.

### 8.3. CPU-bound work vẫn cần CPU

Một pipeline reactive có thể thực hiện parse JSON lớn, mã hóa, tính toán hoặc nén dữ liệu. Những bước này tiêu thụ CPU bất kể I/O non-blocking.

Nếu CPU đã bão hòa, thêm request concurrency không làm hệ thống xử lý nhanh hơn. Cần profile CPU, giảm công việc, tối ưu thuật toán hoặc mở rộng CPU capacity.

## 9. Thiết kế benchmark R2DBC và JDBC công bằng

So sánh hai công nghệ cần kiểm soát biến số. Nếu thay đổi cả driver, pool, SQL, schema, số thread và serialization cùng lúc, không thể biết nguyên nhân tạo khác biệt.

### 9.1. Giữ môi trường tương đương

| Yếu tố | Cách giữ công bằng |
| --- | --- |
| Database | Cùng instance hoặc môi trường có cấu hình tương đương |
| Schema/index | Cùng migration và execution plan tương đương |
| Dataset | Cùng số hàng và phân bố dữ liệu |
| Query | Cùng câu SQL hoặc logic tương đương |
| Transaction | Cùng isolation và boundary |
| Pool | Ghi rõ max connections và cấu hình timeout của mỗi bên |
| Application | Cùng CPU/memory limit và replica count |
| Response | Cùng payload và serialization |
| Load | Cùng arrival rate, duration và scenario |
| Cache | Cùng chính sách warm/cold cache |

Không nhất thiết cấu hình JDBC và R2DBC phải giống nhau từng tham số nếu mô hình khác nhau, nhưng phải ghi lại các khác biệt và so sánh trong giới hạn tài nguyên tương đương.

### 9.2. So sánh ở hai cấp độ

**Microbenchmark** có thể đo chi phí một hàm thuần Java, converter hoặc mapping nhỏ. JMH phù hợp với benchmark CPU/micro-operation có kiểm soát.

**End-to-end benchmark** đo request thực qua HTTP, application, connection pool, driver và database. Đây mới là phép đo chính để đánh giá API production.

Không dùng một microbenchmark converter để kết luận R2DBC nhanh hơn JDBC trên workload database.

### 9.3. Kiểm tra query plan trước khi so sánh driver

Nếu hai implementation chạy cùng SQL nhưng một lần có query plan khác vì statistics, parameterization hoặc cache state, kết quả không phản ánh riêng driver.

Kiểm tra execution plan bằng công cụ của database, ví dụ EXPLAIN hoặc EXPLAIN ANALYZE tùy hệ quản trị. Xác nhận index được dùng như dự kiến, không có full table scan ngoài ý muốn và không có lock wait bất thường.

## 10. Quy trình chạy một load test đáng tin cậy

Một lần đo nên có các giai đoạn:

1. **Chuẩn bị:** tạo dataset, chạy migration, cấu hình pool và xác nhận database khỏe.
2. **Warm-up:** gửi tải tăng dần để JVM JIT, connection pool và cache đạt trạng thái ổn định.
3. **Baseline:** đo tải thấp để xác nhận latency và correctness.
4. **Steady load:** giữ một arrival rate cố định đủ lâu để quan sát hệ thống ổn định.
5. **Step load:** tăng dần traffic để tìm điểm latency/error bắt đầu tăng nhanh.
6. **Stress:** tăng quá capacity có kiểm soát để xem hệ thống suy giảm như thế nào.
7. **Soak:** giữ tải dài để phát hiện leak, pool exhaustion hoặc memory drift.
8. **Recovery:** giảm tải và quan sát hệ thống phục hồi.

Không gộp warm-up vào số liệu chính. Lặp lại các lượt benchmark và ghi nhận biến động giữa các lần.

### 10.1. Ví dụ kịch bản k6 với arrival rate cố định

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_api_load: {
      executor: 'constant-arrival-rate',
      rate: 200,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 500,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<250', 'p(99)<500'],
  },
};

export default function () {
  const response = http.get('http://localhost:8080/api/orders?limit=20');
  check(response, {
    'status is 200': (res) => res.status === 200,
  });
}
~~~

Các giá trị rate, duration và threshold chỉ là ví dụ. Hãy thay bằng SLO và traffic profile thực tế. Theo dõi dropped iterations và số virtual users được sử dụng; nếu load generator không phát đủ arrival rate, kết quả không đại diện cho tải đã định.

### 10.2. Tăng tải theo từng nấc

Ví dụ một ma trận:

| Giai đoạn | Arrival rate | Thời lượng | Mục tiêu |
| --- | ---: | ---: | --- |
| Warm-up | 20 req/s | 2 phút | Làm nóng JVM/pool |
| Step 1 | 50 req/s | 3 phút | Baseline |
| Step 2 | 100 req/s | 3 phút | Tải trung bình |
| Step 3 | 200 req/s | 5 phút | Tải mục tiêu |
| Step 4 | 300 req/s | 5 phút | Tìm vùng bão hòa |
| Soak | 150 req/s | 30 phút | Theo dõi drift/leak |

Không dùng cùng một con số cho mọi hệ thống. Điều chỉnh theo traffic dự kiến, SLO, database capacity và giới hạn môi trường.

## 11. Theo dõi ứng dụng, Reactor và database cùng lúc

Chỉ đo HTTP không đủ để giải thích vì sao hệ thống chậm. Cần đặt các metric cạnh nhau trên cùng timeline.

### 11.1. Chỉ số ở application

- CPU utilization và throttling.
- Heap usage, allocation rate và GC pause.
- Thread count và thread state.
- Event-loop utilization/lag.
- Scheduler queue và rejected task.
- HTTP request latency, throughput và error rate.
- Serialization time nếu đo được.
- Số request đang hoạt động.

### 11.2. Chỉ số ở connection pool

- Active/acquired connection.
- Idle connection.
- Pending acquire.
- Acquire latency.
- Acquire timeout.
- Connection hold time.
- Pool max size và số connection được tạo.

### 11.3. Chỉ số ở database

- CPU, memory và disk I/O.
- Active session và query đang chạy.
- Lock wait/deadlock.
- Slow query và execution plan.
- Buffer/cache hit.
- Connection count và connection churn.
- Transaction duration và rollback rate.

Nếu application CPU thấp nhưng pool pending cao, có thể bottleneck nằm ở database hoặc pool. Nếu event-loop lag cao dù database nhanh, hãy tìm blocking call hoặc CPU-bound work trên event loop.

### 11.4. Dùng Micrometer/Observation có chọn lọc

Spring Boot và Micrometer có thể cung cấp HTTP, JVM và một số database/pool metrics tùy cấu hình. Observation/tracing có thể giúp theo dõi một request qua các thành phần.

Hãy bật metric cần thiết thay vì thu thập mọi thứ; dùng histogram cho latency cần tính percentile; tránh gắn tenant ID, user ID hoặc request ID có cardinality rất lớn làm metric tag; dùng trace/log để tìm một request cụ thể thay vì tạo metric label cho từng request; và giữ cùng cấu hình instrumentation khi so sánh JDBC và R2DBC.

Instrumentation có chi phí CPU, memory và network. Ghi lại cấu hình observability trong benchmark report.

## 12. Nhận diện các kiểu bottleneck

### 12.1. Database saturation

Dấu hiệu:

- Database CPU hoặc I/O cao.
- Query latency tăng.
- Active session và lock wait tăng.
- Throughput không tăng dù arrival rate tăng.

Cách xử lý: xem execution plan và index, giảm số round trip, giảm số hàng đọc/ghi, tối ưu transaction và lock scope, điều tiết concurrency và connection pool, hoặc scale database/read replica khi phù hợp.

Chuyển từ JDBC sang R2DBC không làm query plan tốt hơn.

### 12.2. Connection pool saturation

Dấu hiệu:

- Pending acquire tăng.
- Acquire latency chiếm phần lớn request latency.
- Database vẫn còn capacity hoặc active connections thấp hơn dự kiến.
- Nhiều request timeout trước khi SQL bắt đầu.

Cách xử lý: tìm publisher giữ connection quá lâu, rút ngắn transaction, tránh chờ HTTP service trong transaction database, điều chỉnh pool sau khi hiểu giới hạn database và kiểm tra tổng pool trên tất cả replica.

### 12.3. Event loop bị block

Dấu hiệu:

- Event-loop lag tăng.
- HTTP latency tăng dù database query nhanh.
- Thread dump cho thấy event-loop thread đang chờ I/O blocking hoặc monitor.
- CPU có thể thấp hoặc cao tùy blocking operation.

Cách xử lý: loại bỏ block/JDBC/API blocking khỏi event loop, cô lập blocking legacy trên scheduler phù hợp, profile CPU và lock contention. Có thể dùng BlockHound trong môi trường test để phát hiện một số blocking call không mong muốn.

BlockHound là công cụ phát hiện, không phải bằng chứng mọi đường code đều non-blocking. Cần kiểm thử các path quan trọng và kiểm tra driver/client thực tế.

### 12.4. CPU-bound mapping/serialization

Dấu hiệu:

- Application CPU cao.
- Database query nhanh.
- Response lớn hoặc mapping phức tạp.
- GC/allocation tăng.

Cách xử lý: giảm dữ liệu trả về, dùng projection/DTO phù hợp, tránh collectList với tập dữ liệu lớn, tối ưu serializer và thuật toán, đưa CPU-heavy work ra scheduler thích hợp nếu cần sau khi đo.

### 12.5. Tail latency do downstream

Một endpoint có thể gọi database nhanh nhưng chờ service ngoài chậm. p50 có thể tốt trong khi p99 tăng mạnh khi downstream có spike.

Đo riêng từng dependency, đặt timeout hợp lý, giới hạn concurrency và thiết kế fallback theo nghiệp vụ. Non-blocking giúp không giữ thread trong lúc chờ nhưng không loại bỏ latency của dependency.

## 13. R2DBC có thể chậm hơn trong trường hợp nào?

Một số tình huống R2DBC có thể không nhanh hơn JDBC:

- Tải thấp, ít request đồng thời và query rất ngắn; overhead reactive pipeline chiếm tỷ trọng lớn.
- Mapping phức tạp hoặc converter tốn CPU.
- Có nhiều operator/context propagation không cần thiết.
- Dùng driver hoặc feature chưa tối ưu cho workload.
- Connection pool quá nhỏ hoặc cấu hình acquire timeout không phù hợp.
- Pipeline tạo quá nhiều publisher con hoặc concurrency quá cao.
- Code vẫn chứa blocking call trên event loop.
- Database đã bão hòa nên lợi thế giải phóng thread không tăng throughput.

Ngược lại, JDBC có thể dùng thread-per-request hoặc virtual threads trong một số kiến trúc và vẫn đáp ứng workload tốt. So sánh phải dựa trên mục tiêu hệ thống, không dựa trên nhãn reactive/non-reactive.

### 13.1. Reactive có chi phí riêng

Một pipeline reactive có thể bao gồm tạo và điều phối publisher/subscriber, context propagation, operator fusion hoặc boundary, scheduler hop nếu dùng, mapping từng phần tử và backpressure coordination.

Reactor được tối ưu cho nhiều trường hợp, nhưng các chi phí vẫn tồn tại. Không thêm publishOn/subscribeOn ở mọi chỗ nếu không có lý do và số liệu.

### 13.2. Non-blocking không có nghĩa zero thread

Ứng dụng vẫn có thread cho event loop, database driver, scheduler, callback và công việc phụ. Lợi ích là không cần một thread bị giữ riêng cho mỗi thao tác I/O đang chờ theo cách blocking truyền thống; không phải hệ thống chạy không có thread.

## 14. Tránh các anti-pattern làm sai kết quả benchmark

| Anti-pattern | Vì sao kết quả sai hoặc code chậm | Cách cải thiện |
| --- | --- | --- |
| Chỉ đo average latency | Che giấu tail latency | Báo p50/p95/p99 và histogram |
| Benchmark 1 request tuần tự | Không tạo concurrency như production | Dùng workload song song phù hợp |
| Dùng closed workload cho traffic đến liên tục | Server chậm khiến load generator tự giảm tốc | Dùng open arrival-rate scenario |
| Chỉ đo khi database rỗng | Không phản ánh index/cache/data distribution | Dùng dataset gần production |
| Chỉ đo một SELECT đơn giản | Bỏ qua auth, mapping, transaction và downstream | Có microbenchmark và end-to-end benchmark |
| So sánh query khác nhau | Không cô lập biến số | Giữ SQL/semantics tương đương |
| Tăng pool tối đa | Có thể làm database quá tải | Đo pool wait và DB capacity |
| collectList toàn bộ kết quả lớn | Tăng memory và GC | Pagination hoặc streaming có giới hạn |
| block trong event loop | Làm nghẽn các request khác | Dùng non-blocking client hoặc cô lập blocking work |
| Thêm scheduler ở mọi operator | Tạo queue và context-switch overhead | Chỉ chuyển scheduler khi cần |
| Không warm-up JVM | Đo cả JIT/connection initialization | Warm-up trước giai đoạn đo |
| Chỉ chạy một lần | Dễ bị nhiễu bởi môi trường | Lặp lại và ghi nhận biến động |
| Bỏ qua lỗi/dropped iterations | Throughput nhìn cao hoặc latency nhìn thấp giả tạo | Theo dõi error và dropped work |
| Không đo database | Quy nhầm bottleneck cho driver | Thu thập DB metrics cùng timeline |
| Chạy load generator trên cùng máy quá tải | Load generator trở thành bottleneck | Tách máy hoặc xác nhận nó còn dư capacity |

## 15. Ví dụ đọc kết quả benchmark

Giả sử hai implementation được chạy với cùng workload 200 request/second, cùng database và cùng payload:

| Chỉ số | JDBC | R2DBC |
| --- | ---: | ---: |
| Successful throughput | 198 req/s | 199 req/s |
| p50 | 24 ms | 25 ms |
| p95 | 61 ms | 60 ms |
| p99 | 120 ms | 118 ms |
| Error rate | 0.2% | 0.1% |
| Application threads | 220 | 48 |
| Application CPU | 52% | 49% |
| Database CPU | 68% | 69% |

Đây là số liệu giả định để minh họa cách diễn giải, không phải benchmark phổ quát.

Có thể kết luận:

- Latency và throughput gần tương đương ở workload này.
- R2DBC dùng ít application thread hơn trong cấu hình đã đo.
- Database CPU gần như không đổi, phù hợp với việc cùng workload SQL.
- Chưa có bằng chứng R2DBC làm query nhanh hơn.
- Nếu mục tiêu là giảm thread/resource ở concurrency cao, R2DBC có thể có lợi; cần kiểm tra thêm ở tải lớn hơn và soak test.

Không thể kết luận R2DBC luôn tốt hơn vì workload, driver, pool, hardware và cấu hình có thể thay đổi kết quả.

### 15.1. Khi throughput tăng nhưng p99 xấu đi

Ví dụ tăng arrival rate từ 200 lên 350 req/s:

| Chỉ số | 200 req/s | 350 req/s |
| --- | ---: | ---: |
| Successful throughput | 199 req/s | 320 req/s |
| p95 | 60 ms | 240 ms |
| p99 | 118 ms | 1.100 ms |
| Error rate | 0.1% | 4.5% |
| Pool pending | Thấp | Cao |

Throughput tăng nhưng hệ thống đã gần hoặc vượt capacity. p99 và error rate tăng mạnh; không nên chỉ nhìn số request/second để quyết định rằng cấu hình mới tốt hơn.

## 16. Đặt SLO và capacity target

Benchmark cần trả lời một câu hỏi vận hành cụ thể, ví dụ:

- Hệ thống phục vụ 250 req/s với p95 dưới 200 ms được không?
- Ở mức 500 req/s, error rate có dưới 0,5% không?
- Một replica cần bao nhiêu CPU, memory và connection?
- Khi một dependency chậm gấp đôi, API suy giảm như thế nào?
- Hệ thống có phục hồi sau spike mà không restart không?

SLO nên xác định latency percentile và ngưỡng, error budget hoặc error rate, throughput tối thiểu, phạm vi endpoint và loại request, cùng cửa sổ thời gian đo.

Capacity target nên có headroom. Không vận hành liên tục ở đúng điểm bão hòa nếu traffic có burst hoặc database có workload khác.

## 17. Kiểm tra khả năng chịu tải và phục hồi

Ngoài steady load, nên có các kịch bản:

### 17.1. Spike test

Traffic tăng đột ngột trong thời gian ngắn. Quan sát pool pending tăng nhanh đến mức nào, queue có tích lũy không, timeout/error có tăng không và sau khi spike kết thúc latency có trở về baseline không.

### 17.2. Soak test

Giữ tải ổn định trong thời gian dài để phát hiện connection không được trả về pool, heap tăng dần, thread hoặc scheduler queue tăng, cache phình to, database transaction kéo dài và latency xấu dần theo thời gian.

### 17.3. Dependency degradation

Giả lập database chậm, connection acquire chậm hoặc service ngoài trả response trễ. Xác nhận timeout, concurrency limit, retry và backpressure hoạt động theo thiết kế.

Không tạo retry vô hạn cho thao tác ghi. Retry có thể làm tải tăng thêm đúng lúc dependency đang suy giảm.

### 17.4. Recovery test

Sau khi dependency phục hồi, kiểm tra pending queue có giảm không, pool có tái sử dụng connection bình thường không, error rate có trở về mức bình thường không và request mới có bị ảnh hưởng bởi backlog cũ không.

## 18. Dùng BlockHound để tìm blocking call

BlockHound có thể phát hiện một số lời gọi blocking chạy trên thread được đánh dấu non-blocking, ví dụ Reactor event loop. Có thể tích hợp vào test:

~~~java
@BeforeAll
static void installBlockHound() {
    BlockHound.install();
}
~~~

Sau đó chạy các đường code quan trọng trong test để tìm blocking call. Tùy phiên bản thư viện, có thể cần allowlist cho một số hoạt động đã biết hoặc tích hợp plugin tương thích.

BlockHound giúp phát hiện vi phạm trong đường code được thực thi. Nó không chứng minh toàn bộ ứng dụng non-blocking, không đo throughput và không thay thế load test.

## 19. Lập báo cáo benchmark có thể lặp lại

Mỗi lượt đo nên lưu:

| Nhóm | Thông tin |
| --- | --- |
| Build | Commit, phiên bản Java, Spring Boot, Spring Data, Reactor và driver |
| Runtime | CPU/memory limit, JVM flags, replica count |
| Database | Phiên bản, cấu hình, schema, index và dataset |
| Pool | Pool type, max size, timeout và số replica |
| Workload | Scenario, arrival rate, concurrency, duration và request mix |
| Observability | Metric/tracing được bật, sampling rate |
| Results | Throughput, p50/p95/p99, errors, CPU, heap, thread, pool và DB |
| Notes | Warm-up, cache state, nhiễu môi trường và bất thường |

Khi so sánh nhiều lần, dùng cùng phiên bản code và cấu hình. Nếu thay đổi pool hoặc query giữa các lượt, ghi rõ thay đổi để người đọc không nhầm tác động của driver với tác động của cấu hình.

### 19.1. Không chọn kết quả tốt nhất trong nhiều lần chạy

Nếu chạy benchmark năm lần và chỉ báo lần nhanh nhất, kết quả có thể bị thiên lệch. Hãy báo tất cả lần chạy hoặc thống kê trung vị/phạm vi, đồng thời giải thích biến động.

Nếu môi trường dùng chung với workload khác, đo và ghi nhận nhiễu. Với kết quả sát nhau, có thể chưa đủ bằng chứng để nói một implementation tốt hơn.

## 20. Quy trình điều tra khi R2DBC không đạt mục tiêu

1. Xác nhận load generator thực sự phát đúng arrival rate.
2. Kiểm tra request thành công, error rate và dropped work.
3. So sánh p50/p95/p99 theo endpoint và theo từng dependency.
4. Kiểm tra pending acquire và thời gian giữ connection.
5. Kiểm tra database CPU, query plan, lock và I/O.
6. Kiểm tra application CPU, GC, thread và event-loop lag.
7. Tìm blocking call hoặc CPU-heavy work trong reactive pipeline.
8. Kiểm tra số hàng trả về, collectList, pagination và downstream demand.
9. Thay đổi một biến mỗi lần, chạy lại cùng workload.
10. Ghi nhận kết quả và xác nhận cải thiện không làm xấu error rate hoặc tail latency.

Không tăng pool, concurrency hoặc số replica cùng lúc rồi kết luận đã tìm ra nguyên nhân. Thay đổi từng yếu tố giúp hiểu mối quan hệ nhân quả.

## 21. Những câu hỏi cần trả lời trước khi kết luận

- Workload có gần với production không?
- Arrival rate có được giữ độc lập với response latency không?
- Load generator có đủ tài nguyên không?
- Đã warm-up JVM và pool chưa?
- Đã đo p95/p99 và error rate chưa?
- Có đo connection pool wait và database metrics không?
- SQL, index, data và transaction có tương đương khi so sánh không?
- Có blocking call trên event loop không?
- Throughput có tăng trong khi tail latency vẫn nằm trong SLO không?
- Kết quả có lặp lại qua nhiều lần chạy không?

Nếu chưa trả lời được các câu hỏi quan trọng, kết luận nên được xem là giả thuyết cần đo thêm.

## 22. Kết luận

Non-blocking là mô hình sử dụng tài nguyên khi chờ I/O, không phải cam kết rằng mỗi thao tác database sẽ hoàn tất nhanh hơn. R2DBC có thể giúp ứng dụng chịu được nhiều request I/O đồng thời với ít thread hơn, nhưng latency và throughput vẫn bị chi phối bởi query, database, connection pool, CPU, network, mapping và các dependency.

Hãy đo cả throughput, p50/p95/p99, error rate, concurrency, application resource, pool wait và database health. Dùng workload, dataset và transaction gần production; chọn open hoặc closed model theo câu hỏi cần trả lời; warm-up, tăng tải theo nấc, chạy soak test và lặp lại phép đo. Khi so sánh JDBC với R2DBC, giữ SQL và semantics tương đương, kiểm soát tài nguyên và ghi rõ khác biệt cấu hình.

Kết luận tốt phải gắn với một workload và một mục tiêu cụ thể: hệ thống đạt bao nhiêu request thành công mỗi giây, với tail latency và error rate nào, tiêu thụ bao nhiêu tài nguyên và còn bao nhiêu headroom. Không có một kết quả benchmark đơn lẻ nào chứng minh non-blocking luôn nhanh hơn blocking trong mọi ứng dụng.
